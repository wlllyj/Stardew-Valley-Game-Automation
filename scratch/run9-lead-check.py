#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Lead 侧独立复核器（run9/run10 用；只读，不碰游戏、不改任何文件）。

与 `tools/verify-run3.py`（账本内部一致性 + 尾部窗口）**互补**：
本脚本专查"账本自述之外"的东西，以及"自述与自算"的交叉核对：

1. **跨日链**：把 `sleep`/`day_start` 串起来，逐次核 `day_after` 恰好 +1 天
   （春/夏/秋/冬 28 天、年递增）。
2. **存档链**：`scratch/runN-external-snapshots.jsonl` 的 start/end 两行 + 当前存档
   size/mtime；**只报事实，不做"没变就是失败"的推断**（日终菜单期存档不动是设计行为）。
3. **SMAPI 配对**：冻结窗口里数 `Synchronizing 'NewDay'` / `Context: before save.` /
   `SaveGame.Save() called.` / `completed without exceptions`，给出逐条链号；
   **有 NewDay 无 save 的缺口要单列**（run5/run6 出过，run7/run8 没有）。
4. **自述 vs 自算**：每个 `day_end` 的 `ok_steps` 与 `stages[].ok` 之和比对；
   `failed_steps` 与 `stages[].failed` 之和比对。不一致 ⇒ 报红（这是"账本自相矛盾"）。
5. **尾部窗口**：最后 N 天 `verified is True` 才算达标；并打印每天 `checks` 里为 False 的项。

退出码：0 = 尾部窗口达标且无矛盾；1 = 未达标或有矛盾；2 = 账本读不到。

用法：
  python scratch/run9-lead-check.py --journal logs/longrun-3day-llm-run9.jsonl \
      --smapi logs/run9-smapi-window.txt --snapshots scratch/run9-external-snapshots.jsonl --days 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SEASONS = ("spring", "summer", "fall", "winter")


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # 半截行（跑批进行中）⇒ 忽略，但要如实报数
                rows.append({"event": "__partial__"})
    return rows


def day_key_of(value) -> tuple[int, str, int] | None:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return (int(value[0]), str(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return None
    return None


def next_day(key: tuple[int, str, int]) -> tuple[int, str, int]:
    year, season, day = key
    if day < 28:
        return (year, season, day + 1)
    idx = SEASONS.index(season) if season in SEASONS else -1
    if idx < 0:
        return (year, season, day + 1)
    if idx == len(SEASONS) - 1:
        return (year + 1, SEASONS[0], 1)
    return (year, SEASONS[idx + 1], 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", required=True)
    ap.add_argument("--smapi", default="")
    ap.add_argument("--snapshots", default="")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--save-main", default="")
    args = ap.parse_args()

    jpath = Path(args.journal)
    if not jpath.exists():
        print(f"[exit 2] 账本不存在：{jpath}")
        return 2
    rows = load_rows(jpath)
    partial = sum(1 for r in rows if r.get("event") == "__partial__")
    day_starts = [r for r in rows if r.get("event") == "day_start"]
    day_ends = [r for r in rows if r.get("event") == "day_end"]
    sleeps = [r for r in rows if r.get("event") == "sleep"]
    finishes = [r for r in rows if r.get("event") == "finish"]

    print("=" * 78)
    print(f"Lead 独立复核  journal={jpath}")
    print(f"  行 {len(rows)}（半截行 {partial}）｜ day_start {len(day_starts)} ｜ day_end {len(day_ends)} "
          f"｜ sleep {len(sleeps)} ｜ finish {len(finishes)}")
    print("=" * 78)

    problems: list[str] = []

    # 1. 跨日链：day_end.day → day_end.day_after 必须恰好 +1
    #    字段事实：day_after 只在 day_end 行（sleep 行没有 day/day_after）。
    #    day_after=None ⇒ 当天没跨日（sleep_failed / 0 动作不推进），如实列出、不算失败。
    print("[1] 跨日链（day_end.day → day_after 恰好 +1；None = 当天没跨日）")
    chain = 0
    crossdays = 0
    for r in day_ends:
        before = day_key_of(r.get("day"))
        after = day_key_of(r.get("day_after"))
        if after is None:
            print(f"    · {before} day_after=None（{r.get('ended_by')}）⇒ 当天没跨日，不计入")
            continue
        crossdays += 1
        if before is None:
            print(f"    · day_after={after} 但 day 缺失 ⇒ 无法判定（不是失败）")
            continue
        ok = after == next_day(before)
        chain += 1 if ok else 0
        if not ok:
            problems.append(f"跨日链断裂：{before} → {after}")
        print(f"    · {before} → {after}  {'+1 ✅' if ok else '+1 ❌'}  ended_by={r.get('ended_by')}")
    print(f"    合计 跨日 {crossdays} 次，其中恰好 +1 的 {chain}/{crossdays}")

    # 2. 存档链
    print("[2] 存档链（快照 + 当前存档）")
    snap = Path(args.snapshots) if args.snapshots else None
    if snap and snap.exists():
        try:
            for line in snap.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    sm = row.get("save_main")
                    if isinstance(sm, dict):
                        sm_txt = f"exists={sm.get('exists')} size={sm.get('size')} mtime={sm.get('mtime')}"
                    else:
                        sm_txt = str(sm)
                    print(f"    · tag={row.get('tag')} at={row.get('at')} save_main[{sm_txt}] "
                          f"mod_version_matches={row.get('mod_version_matches')}")
        except Exception as exc:  # noqa: BLE001
            print(f"    · 快照读不了：{exc!r} ⇒ 无法判定")
    else:
        print("    · 没有起止快照 ⇒ 无法判定（缺失 ≠ 通过）")
    save_main = args.save_main or ""
    if save_main and Path(save_main).exists():
        st = os.stat(save_main)
        print(f"    · 当前存档 {Path(save_main).name} size={st.st_size} "
              f"mtime={__import__('time').strftime('%Y-%m-%d %H:%M:%S', __import__('time').localtime(st.st_mtime))}")

    # 3. SMAPI 配对
    print("[3] SMAPI 配对（NewDay ↔ before save ↔ SaveGame.Save() called. ↔ completed）")
    spath = Path(args.smapi) if args.smapi else None
    if spath and spath.exists():
        text = spath.read_text(encoding="utf-8", errors="replace").splitlines()
        newday, before, called, done = [], [], [], []
        for i, line in enumerate(text):
            if "Synchronizing 'NewDay' task" in line:
                newday.append(i)
            elif "Context: before save." in line:
                before.append(i)
            elif "SaveGame.Save() called." in line:
                called.append(i)
            elif "completed without exceptions" in line:
                done.append(i)
        print(f"    · 窗口 {spath.name} 行 {len(text)}｜ NewDay {len(newday)} / before save {len(before)} "
              f"/ Save called {len(called)} / completed {len(done)}")
        if len(before) != len(called):
            problems.append(f"SMAPI 里 before save({len(before)}) != Save called({len(called)})")
        if len(called) > len(newday):
            problems.append(f"有 save({len(called)}) 无 NewDay({len(newday)}) —— 保存没有对应的跨日")
        if len(newday) != len(before):
            # 口径（2026-10-16 收紧，引 task-126）：run9 实测 4 NewDay / 0 save
            # ⇒ 5 个游戏日一次都没落盘（存档 start==end），进度全丢。
            # 既然主目标要求"真机连续 3 个游戏日"，就**必须**每次跨日配一次保存：
            # 有出货时游戏会把保存推迟到 ShippingMenu 之后，而我们关菜单的方式会掐断它。
            # 因此这不再是 INFO，而是**硬问题**（除非修好 task-126）。
            problems.append(f"跨日未落盘：SMAPI 里 NewDay={len(newday)} 而 save={len(before)} "
                            f"（每次跨日必须完成一次 SaveGame.Save()；见 task-126 与 docs/_run6-criteria.md §2）")
        print(f"    · NewDay 行号 {[i + 1 for i in newday][:12]}")
        print(f"    · before-save 行号 {[i + 1 for i in before][:12]}")
    else:
        print("    · 没有冻结的 SMAPI 窗口 ⇒ 无法判定（缺失 ≠ 通过）")

    # 4. 自述 vs 自算
    print("[4] 自述 vs 自算（day_end.ok_steps ↔ Σ stages[].ok ；failed 同理）")
    for r in day_ends:
        stages = r.get("stages") or []
        sum_ok = sum(int(s.get("ok") or 0) for s in stages)
        sum_failed = sum(int(s.get("failed") or 0) for s in stages)
        ok_steps = r.get("ok_steps")
        failed_steps = r.get("failed_steps")
        mismatch = (ok_steps is not None and int(ok_steps) != sum_ok) or \
                   (failed_steps is not None and int(failed_steps) != sum_failed)
        if mismatch:
            problems.append(f"{r.get('day')} 自述/自算不符 ok {ok_steps}≠{sum_ok} failed {failed_steps}≠{sum_failed}")
        print(f"    · {r.get('day')} ok_steps={ok_steps} vs Σok={sum_ok} ｜ failed_steps={failed_steps} "
              f"vs Σfailed={sum_failed}  {'❌ 不符' if mismatch else '✅'}")

    # 5. 尾部窗口
    print(f"[5] 尾部窗口（最后 {args.days} 天 verified）")
    tail = day_ends[-args.days:] if day_ends else []
    tail_ok = len(tail) == args.days and all(r.get("verified") is True for r in tail)
    for r in tail:
        bad = [k for k, v in (r.get("checks") or {}).items() if v is not True]
        print(f"    · {r.get('day')} ended_by={r.get('ended_by')} verified={r.get('verified')} "
              f"未通过项={bad}")
    if len(day_ends) < args.days:
        print(f"    · 只有 {len(day_ends)} 天，不足 {args.days} 天 ⇒ 未达标")
    print(f"    结论：{'达标 ✅' if tail_ok else '未达标 ❌'}")

    if finishes:
        f = finishes[-1]
        print(f"[6] finish: code={f.get('code')} streak={f.get('verified_streak')} "
              f"actions={f.get('actions')} minutes={f.get('minutes')} "
              f"no_unmet_stages={f.get('no_unmet_stages')}")
    else:
        print("[6] finish: 没有（跑批未收尾或被中断）⇒ 无法判定（不是通过）")

    if problems:
        print("\n发现问题：")
        for p in problems:
            print(f"  ❌ {p}")
        return 1
    return 0 if tail_ok else 1


if __name__ == "__main__":
    sys.exit(main())
