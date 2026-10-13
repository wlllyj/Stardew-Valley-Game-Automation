# -*- coding: utf-8 -*-
"""run6 快速取证（只读）：console 尾部 + 账本 day_start/day_end/finish + 异常事件 + SMAPI 跨日行号 + 存档。

    python scratch\\run6-quick.py [--tail 25]
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JOURNAL = REPO / "logs" / "longrun-3day-llm-run6.jsonl"
CONSOLE = REPO / "logs" / "longrun-3day-llm-run6.console.log"
ERR = REPO / "logs" / "longrun-3day-llm-run6.console.err.log"
SAVE_DIR = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"
SMAPI = Path(os.environ["APPDATA"]) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tail", type=int, default=25)
    ap.add_argument("--since", default="21:41:21", help="SMAPI 只统计该时刻之后的行（起跑时刻）")
    args = ap.parse_args()

    print("=== console 尾部 ===")
    if CONSOLE.exists():
        for ln in CONSOLE.read_text(encoding="utf-8", errors="replace").splitlines()[-args.tail:]:
            print("  " + ln)
    print(f"\n=== stderr：{ERR.stat().st_size if ERR.exists() else '缺失'} 字节 ===")

    rows = [json.loads(x) for x in JOURNAL.read_text(encoding="utf-8").splitlines() if x.strip()] \
        if JOURNAL.exists() else []
    print(f"\n=== 账本：{len(rows)} 条 ===")
    from collections import Counter
    print("事件计数：" + json.dumps(dict(Counter(r.get('event') for r in rows)), ensure_ascii=False))

    print("\n--- day_start / day_end / finish ---")
    for i, r in enumerate(rows):
        ev = r.get("event")
        if ev == "day_start":
            print(f"#{i} day_start t={r.get('t')} {json.dumps(r, ensure_ascii=False)[:400]}")
        elif ev == "day_end":
            keep = {k: r.get(k) for k in ("t", "ended_by", "verified", "day", "day_after", "day_text",
                                          "ended_reason", "ok_steps", "skipped_steps", "failed_steps",
                                          "final_water", "checks")}
            s = json.dumps(keep, ensure_ascii=False)
            print(f"#{i} day_end {s[:1500]}")
        elif ev == "finish":
            print(f"#{i} finish {json.dumps(r, ensure_ascii=False)}")

    print("\n--- 异常类事件（点名）---")
    blame = ("stuck", "blocked", "unreachable", "no_day_progress", "modal_blocked", "stage_exhausted",
             "stage_no_target", "refused", "tool_refused", "env_fail", "inconclusive", "buy", "policy_fallback")
    for i, r in enumerate(rows):
        ev = str(r.get("event"))
        if any(k in ev for k in blame):
            print(f"#{i} {json.dumps(r, ensure_ascii=False)[:600]}")

    print("\n--- 最后 10 条原文 ---")
    for i, r in enumerate(rows[-10:]):
        print(f"#{len(rows) - 10 + i} {json.dumps(r, ensure_ascii=False)[:700]}")

    print("\n=== SMAPI（> %s）===" % args.since)
    if SMAPI.exists():
        pat = re.compile(r"^\[(\d\d:\d\d:\d\d)")
        kept = [ln for ln in SMAPI.read_text(encoding="utf-8", errors="replace").splitlines()
                if (m := pat.match(ln)) and m.group(1) >= args.since]
        print(f"窗口行数 {len(kept)} / 全文 {sum(1 for _ in SMAPI.open(encoding='utf-8', errors='replace'))}")
        for kw in ("Synchronizing 'NewDay'", "SaveGame.Save()", "after save, starting", "Disconnected", "ERROR"):
            hits = [ln for ln in kept if kw in ln]
            print(f"  {kw!r}: {len(hits)}")
            for ln in hits[:6]:
                print("     " + ln[:180])
    else:
        print("SMAPI 日志缺失")

    print("\n=== 存档 ===")
    for name in ("Wahaha_450799035", "SaveGameInfo"):
        p = SAVE_DIR / name
        if p.exists():
            import datetime as dt
            st = p.stat()
            print(f"  {name}: {st.st_size} B / {dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec='milliseconds')}")
        else:
            print(f"  {name}: 缺失")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
