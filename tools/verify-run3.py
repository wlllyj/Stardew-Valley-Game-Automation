#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""独立复核 longrun 的 journal（Lead 侧验收工具，不信执行者的口头结论）。

用法：
    python tools\\verify-run3.py                     # 默认读最新一份 logs\\longrun-*.jsonl
    python tools\\verify-run3.py --journal logs\\longrun-3day-llm-run3.jsonl
    python tools\\verify-run3.py --days 3 --json

它只读 journal（JSONL，每行一条事件，字段含 event/t/day/...），核对：

1. **跨日证据**：每个 `day_end` 的 `ended_by == "sleep"` 必须能在 journal 里找到
   一次成功的 sleep（`event=="sleep" and ok==true`），且 `final.day` 与 `day_start` 的
   day_key 不同 —— 回执不算证据，观测里的日期变化才算。
2. **睡前未浇为 0**：`day_end.final.unwatered_crops == 0`（全局口径）。
3. **无硬失败**：当天 stages 的 failed 之和为 0。
4. **LLM 覆盖**：`decision` 条数与其中 `llm==true` 的条数（长跑默认开 LLM）。
5. **尾部连续 VERIFIED 天数** >= `--days`；存在 `finish` 事件时核对 `code`。

退出码：0 = 达标；1 = 未达标；2 = journal 读不出来。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from typing import Any


def load(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as exc:  # noqa: BLE001 - 复核工具要如实报告坏行
                rows.append({"event": "_bad_line", "lineno": lineno, "error": str(exc)})
                continue
            obj["_lineno"] = lineno
            rows.append(obj)
    return rows


def latest_journal(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.exists(explicit) else None
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cands = glob.glob(os.path.join(here, "logs", "longrun-*.jsonl"))
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def day_key(row: dict[str, Any]) -> str:
    day = row.get("day")
    if isinstance(day, (list, tuple)) and len(day) >= 3:
        return f"{day[1]} {day[2]}"
    if day is not None:
        return str(day)
    for holder in ("final", "before", "after", "decision"):
        sub = row.get(holder)
        if isinstance(sub, dict) and isinstance(sub.get("day"), (list, tuple)):
            d = sub["day"]
            return f"{d[1]} {d[2]}" if len(d) >= 3 else str(d)
    return "?"


def build_days(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    days: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for row in rows:
        ev = row.get("event")
        if ev == "day_start":
            cur = {
                "key": day_key(row),
                "start_lineno": row.get("_lineno"),
                "stages": [],
                "ended_by": "",
                "ended_reason": "",
                "final": {},
                "sleep_ok": False,
                "sleep_fail": 0,
                "cross_day": False,
                "verified": None,
                "checks": {},
                "end": {},
            }
            days.append(cur)
            continue
        if cur is None:
            continue
        if ev == "sleep":
            if row.get("ok"):
                cur["sleep_ok"] = True
            else:
                cur["sleep_fail"] += 1
        elif ev == "stage":
            cur["stages"].append(row)
        elif ev == "day_end":
            cur["ended_by"] = row.get("ended_by", "")
            cur["ended_reason"] = row.get("ended_reason", "")
            cur["final"] = row.get("final") or {}
            cur["checks"] = row.get("checks") or {}
            cur["verified"] = row.get("verified")
            # day_end 自带按日汇总（比逐条 stage 事件更权威）
            cur["end"] = {
                k: row.get(k)
                for k in ("day_text", "ok_steps", "skipped_steps", "failed_steps", "stages", "outcomes", "notes")
            }
            fin_key = day_key({"final": cur["final"]}) if cur["final"] else "?"
            cur["cross_day"] = bool(cur["final"]) and fin_key != cur["key"]
            cur["end_lineno"] = row.get("_lineno")
    return days


def report(rows: list[dict[str, Any]], *, target_days: int) -> tuple[bool, dict[str, Any]]:
    bad_lines = [r for r in rows if r.get("event") == "_bad_line"]
    events = Counter(r.get("event") for r in rows)
    days = build_days(rows)

    problems: list[str] = []
    for d in days:
        name = d["key"]
        end_stats = d.get("end") or {}
        checks = d.get("checks") or {}
        if d["ended_by"] != "sleep":
            problems.append(f"[{name}] ended_by={d['ended_by'] or '?'}（不是我们主动睡过去的）")
        else:
            if not d["sleep_ok"]:
                problems.append(f"[{name}] ended_by=sleep 但 journal 里没有一次成功的 sleep 证据")
            if not d["cross_day"]:
                problems.append(
                    f"[{name}] 缺跨日证据：final 的日期与 day_start 相同（final={d['final'].get('day')!r}）"
                )
            unwatered = d["final"].get("unwatered_crops")
            if unwatered != 0:
                problems.append(f"[{name}] 睡前 unwatered_crops={unwatered!r}（要求 0）")
            if checks.get("crops_watered") is False:
                problems.append(f"[{name}] checks.crops_watered=false（睡前还有没浇的作物）")
        if checks.get("no_hard_failures") is False:
            problems.append(f"[{name}] checks.no_hard_failures=false（当天有硬失败步骤）")
        failed = end_stats.get("failed_steps")
        if failed is None:
            failed = sum(int(s.get("failed") or 0) for s in d["stages"])
        if failed:
            problems.append(f"[{name}] 当天 stages 硬失败 {failed} 格")
        if d["verified"] is False:
            problems.append(f"[{name}] day_end verified=false")
        if d["sleep_fail"]:
            problems.append(f"[{name}] 当天有 {d['sleep_fail']} 次 sleep 失败（回执 ok=false）")

    streak = 0
    for d in reversed(days):
        if d["ended_by"] == "sleep" and d["cross_day"] and d["verified"] is not False:
            streak += 1
        else:
            break

    finish = next((r for r in reversed(rows) if r.get("event") == "finish"), None)
    decisions = [r for r in rows if r.get("event") == "decision"]
    llm_true = sum(1 for r in decisions if r.get("llm"))

    ok = streak >= target_days and not problems
    summary = {
        "journal": None,
        "bad_lines": len(bad_lines),
        "rows": len(rows),
        "events": dict(sorted(events.items(), key=lambda kv: (-kv[1], kv[0]))),
        "days": [
            {
                "day": d["key"],
                "ended_by": d["ended_by"],
                "ended_reason": d["ended_reason"],
                "cross_day": d["cross_day"],
                "sleep_ok": d["sleep_ok"],
                "sleep_fail": d["sleep_fail"],
                "unwatered": d["final"].get("unwatered_crops"),
                "crops": d["final"].get("crops"),
                "money": d["final"].get("money"),
                "stages": len((d.get("end") or {}).get("stages") or []) or len(d["stages"]),
                "ok_steps": (d.get("end") or {}).get("ok_steps")
                if (d.get("end") or {}).get("ok_steps") is not None
                else sum(int(s.get("ok") or 0) for s in d["stages"]),
                "skipped": (d.get("end") or {}).get("skipped_steps")
                if (d.get("end") or {}).get("skipped_steps") is not None
                else sum(int(s.get("skipped") or 0) for s in d["stages"]),
                "failed": (d.get("end") or {}).get("failed_steps")
                if (d.get("end") or {}).get("failed_steps") is not None
                else sum(int(s.get("failed") or 0) for s in d["stages"]),
                "checks": d.get("checks") or {},
                "verified": d["verified"],
            }
            for d in days
        ],
        "verified_streak_tail": streak,
        "target_days": target_days,
        "decisions": len(decisions),
        "decisions_llm": llm_true,
        "finish": {k: v for k, v in (finish or {}).items() if k != "_lineno"},
        "problems": problems,
        "verdict": "VERIFIED" if ok else "needs_review",
    }
    return ok, summary


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="独立复核 longrun journal 的 3 日验收")
    ap.add_argument("--journal", default=None, help="journal 路径（默认取 logs 下最新一份 longrun-*.jsonl）")
    ap.add_argument("--days", type=int, default=3, help="要求的尾部连续 VERIFIED 天数（默认 3）")
    ap.add_argument("--json", action="store_true", help="只打印 JSON")
    args = ap.parse_args(argv)

    path = latest_journal(args.journal)
    if not path:
        print("找不到 journal（--journal 指定，或 logs\\longrun-*.jsonl 不存在）")
        return 2
    rows = load(path)
    ok, summary = report(rows, target_days=args.days)
    summary["journal"] = path

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    print(f"journal: {path}")
    print(f"行数 {summary['rows']}  坏行 {summary['bad_lines']}  事件 {summary['events']}")
    print("")
    print(f"{'日':<12}{'ended_by':<14}{'跨日':<6}{'睡前未浇':<9}{'作物':<6}{'钱':<6}{'阶段':<5}{'ok':<5}{'skip':<6}{'fail':<6}verified")
    for d in summary["days"]:
        print(
            f"{d['day']:<12}{d['ended_by'] or '?':<14}{str(d['cross_day']):<6}"
            f"{str(d['unwatered']):<9}{str(d['crops']):<6}{str(d['money']):<6}"
            f"{d['stages']:<5}{d['ok_steps']:<5}{d['skipped']:<6}{d['failed']:<6}{d['verified']}"
        )
    print("")
    print(f"decision {summary['decisions']} 条（其中 LLM {summary['decisions_llm']} 条）")
    if summary["finish"]:
        print(f"finish: {summary['finish']}")
    print(f"尾部连续 VERIFIED 天数 {summary['verified_streak_tail']} / 要求 {summary['target_days']}")
    if summary["problems"]:
        print("")
        print("问题：")
        for p in summary["problems"]:
            print(f"  - {p}")
    print("")
    print(f"结论：{summary['verdict']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
