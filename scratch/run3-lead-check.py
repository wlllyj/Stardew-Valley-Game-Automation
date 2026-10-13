#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run3 的 Lead 侧**外部证据**核查（只读，不信账本自述）。

账本（journal）是 longrun 自己写的，`tools/verify-run3.py` 只是**账本检查器**（
`docs/_verify-run3-limits.md`）。这里补的是"账本之外"的证据：

  1. 存档 `%APPDATA%\\StardewValley\\Saves\\<名>\\<名>` 与 `SaveGameInfo` 的 size/mtime；
  2. SMAPI 日志里 `Synchronizing 'NewDay' task` 与 `SaveGame.Save` 的出现次数/行号；
  3. 账本里 `day_end.day_after` 与下一天 `day_start.day` 是否逐日对齐、是否恰好 +1 天；
  4. 三者互相之间是否自洽（跨日次数 = NewDay 次数 ≈ 存档前进次数）。

用法：
    python scratch\\run3-lead-check.py                                  # 默认最新 logs\\longrun-*.jsonl
    python scratch\\run3-lead-check.py --journal logs\\longrun-3day-llm-run3.jsonl
    python scratch\\run3-lead-check.py --smapi-lines 4000
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SAVE_NAME = "Wahaha_450799035"
SEASONS = {"spring": 1, "summer": 2, "fall": 3, "winter": 4,
           "春": 1, "夏": 2, "秋": 3, "冬": 4}


def latest_journal() -> Path:
    cands = sorted(glob.glob("logs/longrun-*.jsonl"), key=os.path.getmtime)
    return Path(cands[-1])


def save_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
    return Path(appdata) / "StardewValley" / "Saves" / SAVE_NAME


def stat_line(p: Path) -> str:
    if not p.exists():
        return f"{p}  ✗ 不存在"
    st = p.stat()
    return (f"{p.name}  {st.st_size} B  mtime {datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M:%S}")


def ordinal(day) -> int | None:
    """[year, season, day] → 绝对日序（28 天/季，4 季/年）。认不出返回 None。"""
    if not isinstance(day, (list, tuple)) or len(day) != 3:
        return None
    try:
        y, s, d = int(day[0]), SEASONS.get(str(day[1]).lower().strip()), int(day[2])
    except (TypeError, ValueError):
        return None
    if s is None or not (1 <= d <= 28):
        return None
    return ((y - 1) * 4 + (s - 1)) * 28 + (d - 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=None)
    ap.add_argument("--smapi", default=str(Path(os.environ.get("APPDATA", "")) / "StardewValley"
                                          / "ErrorLogs" / "SMAPI-latest.txt"))
    ap.add_argument("--smapi-lines", type=int, default=6000,
                    help="只看 SMAPI 日志末尾多少行（默认 6000）")
    args = ap.parse_args()

    jp = Path(args.journal) if args.journal else latest_journal()
    print("=" * 78)
    print("run3 外部证据核查（Lead 侧，只读）")
    print("=" * 78)
    print(f"账本：{jp}")
    if not jp.exists():
        print("✗ 账本不存在")
        return 2

    rows = []
    for i, line in enumerate(jp.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"  !! 第 {i} 行不是 JSON")

    # ---- 1. 账本自述：逐日 day_after 链 ----
    print("\n[1] 账本里的跨日链（day_start → day_after → 下一天 day_start）")
    cur = None
    chain = []
    for r in rows:
        ev = r.get("event")
        if ev == "day_start":
            if cur is not None:
                chain.append(cur)
            cur = {"start": r.get("day"), "ended_by": None, "day_after": None,
                   "verified": None, "sleep_ok": None, "final": None}
        elif cur is not None and ev == "day_end":
            cur["ended_by"] = r.get("ended_by")
            cur["day_after"] = r.get("day_after")
            cur["verified"] = r.get("verified")
            cur["final"] = (r.get("final") or {}).get("day")
        elif cur is not None and ev == "sleep" and r.get("ok"):
            cur["sleep_ok"] = True
    if cur is not None:
        chain.append(cur)

    cross_ok = 0
    for i, d in enumerate(chain, 1):
        o0, o1 = ordinal(d["start"]), ordinal(d["day_after"])
        delta = (o1 - o0) if (o0 is not None and o1 is not None) else None
        mark = "跨日+1 ✅" if delta == 1 else ("未跨日" if d["ended_by"] != "sleep" else f"跨日异常({delta})")
        if delta == 1:
            cross_ok += 1
        print(f"  {i}. start={d['start']} ended_by={str(d['ended_by']):<12} day_after={d['day_after']} "
              f"verified={d['verified']} sleep_ok={d['sleep_ok']} → {mark}")
    print(f"  账本自述：{len(chain)} 个日报告，其中 {cross_ok} 次跨日 +1")

    # ---- 2. 存档外部证据 ----
    print("\n[2] 存档文件（外部证据：每次跨日应前进）")
    sd = save_dir()
    if not sd.exists():
        print(f"  ✗ 存档目录不存在：{sd}")
    else:
        for name in (SAVE_NAME, "SaveGameInfo"):
            print("  " + stat_line(sd / name))

    # ---- 3. SMAPI 日志 ----
    print(f"\n[3] SMAPI 日志末尾 {args.smapi_lines} 行里的跨日/保存痕迹")
    sp = Path(args.smapi)
    if not sp.exists():
        print(f"  ✗ 不存在：{sp}")
    else:
        lines = sp.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-args.smapi_lines:]
        pat_newday = re.compile(r"Synchronizing 'NewDay'")
        pat_save = re.compile(r"SaveGame\.Save|SaveGameMenu|save.*completed", re.I)
        hits_new = [i for i, l in enumerate(tail) if pat_newday.search(l)]
        hits_save = [i for i, l in enumerate(tail) if pat_save.search(l)]
        base = len(lines) - len(tail)
        print(f"  SMAPI 共 {len(lines)} 行（查 {base + 1}..{len(lines)}）")
        print(f"  Synchronizing 'NewDay' task：{len(hits_new)} 次"
              + (f"  行号 {[base + i + 1 for i in hits_new[:10]]}" if hits_new else ""))
        print(f"  SaveGame.Save/SaveGameMenu 命中：{len(hits_save)} 次"
              + (f"  行号 {[base + i + 1 for i in hits_save[:10]]}" if hits_save else ""))
        if hits_new:
            for i in hits_new[:6]:
                print("    | " + tail[i].strip()[:150])

    # ---- 4. 结论 ----
    print("\n[4] 结论（必要不充分：账本自述与外部证据必须同向；不同向时以外部证据为准）")
    print(f"  · 账本跨日 +1 次数：{cross_ok}")
    if cross_ok == 0:
        print("  ✗ 账本里没有任何一次'恰好 +1 天'的跨日 ⇒ 不达标（不要把回执当证据）")
        return 1
    print("  · 请人工核对：SMAPI 的 NewDay 次数 ≈ 账本跨日次数 ≈ 存档 mtime 前进次数；")
    print("    任何一项对不上 ⇒ 结论只能写 needs_review。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
