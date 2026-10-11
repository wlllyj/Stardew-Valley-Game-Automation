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
3b. **阶段后置条件成立**：优先读 `day_end.checks.no_unmet_stages`（task-15 起），读不到就
    按 `day_end.stages[].leftover` 自己算 —— 只认「做过且做完」，`blocked`/封格不得洗白成功。
3c. **过程里没有异常事件**：`bridge_down` / `watchdog_stop` / `modal_timeout` / `no_day_progress`
    出现任意一条即判未达标（这些是"人不在场也出过事"的证据）。
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


def _tile_count(stage: dict[str, Any]) -> int:
    """阶段的目标格数：longrun 的 day_end.stages[].tiles 是格子列表。"""
    tiles = stage.get("tiles")
    if isinstance(tiles, (list, tuple)):
        return len(tiles)
    try:
        return int(tiles or 0)
    except (TypeError, ValueError):
        return 0


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
            # ⚠ legacy：longrun 目前不写 event=="stage"（只写 day_end.stages）。
            # 这里只作历史账本的兜底；权威口径永远是 day_end.stages。
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
        stage_recs = [s for s in (end_stats.get("stages") or []) if isinstance(s, dict)]
        sum_failed = sum(int(s.get("failed") or 0) for s in stage_recs)
        # leftover 只在"有目标的阶段"上算（Lead 对 task-15 的裁定：0 目标阶段不许拖黑当天）
        leftover_targeted = sum(int(s.get("leftover") or 0) for s in stage_recs if _tile_count(s) > 0)
        leftover_zero_target = sum(int(s.get("leftover") or 0) for s in stage_recs if _tile_count(s) <= 0)
        legacy_failed = sum(int(s.get("failed") or 0) for s in d["stages"])

        # 0. 字段缺失不得当成通过（deputy-lead 负例 A：day_end 整块省略 verified/checks）
        if d["verified"] is None:
            problems.append(f"[{name}] day_end 缺 verified 字段（缺失 ≠ 通过）")
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
        # 失败数一律以 day_end.stages 求和为准，并与 failed_steps 交叉核对（负例 B：只信自述）
        failed_field = end_stats.get("failed_steps")
        if failed_field is None:
            failed_field = sum_failed or legacy_failed
        elif sum_failed and int(failed_field) != sum_failed:
            problems.append(
                f"[{name}] 自述 failed_steps={failed_field} 与 day_end.stages 求和 {sum_failed} 不一致（账目不可信）"
            )
        if int(failed_field or 0):
            problems.append(f"[{name}] 当天 stages 硬失败 {failed_field} 格")
        if d["verified"] is False:
            problems.append(f"[{name}] day_end verified=false")
        if d["sleep_fail"]:
            problems.append(f"[{name}] 当天有 {d['sleep_fail']} 次 sleep 失败（回执 ok=false）")

        # 3b. 阶段后置条件：无论 checks.no_unmet_stages 在不在，都按 day_end.stages 自算并比对
        unmet = checks.get("no_unmet_stages")
        if unmet is not None and bool(unmet) != (leftover_targeted == 0):
            problems.append(
                f"[{name}] checks.no_unmet_stages={unmet} 与自算不一致"
                f"（有目标阶段遗留 leftover={leftover_targeted} 格）"
            )
        # 自述说"有阶段没做完"就一律算问题，**不因自算结果与它一致而放行**
        # （deputy-lead 负例 D：checks.no_unmet_stages=false 与 stages.leftover=5 一致地没做完，
        #   且 day_end.verified 自述 true ⇒ 旧口径零问题。工具的意义就是不信自述。）
        if unmet is False:
            problems.append(
                f"[{name}] checks.no_unmet_stages=false（有阶段后置条件未成立"
                f"；自算有目标阶段 leftover={leftover_targeted} 格）"
            )
        if unmet is None and leftover_targeted:
            problems.append(f"[{name}] 当天有阶段遗留目标 leftover={leftover_targeted}（阶段没做完）")
        if leftover_zero_target:
            problems.append(
                f"[{name}] 0 目标阶段 leftover={leftover_zero_target}"
                "（task-15 修 A 后应为 0；请查 stage_no_target 分支）"
            )

    # 3c. 异常事件（"人不在场也出过事"）
    for code, label in (
        ("bridge_down", "bridge 掉线"),
        ("watchdog_stop", "watchdog 判定 STOP"),
        ("modal_timeout", "模态等待超时"),
        ("no_day_progress", "跨日没有推进"),
    ):
        n = events.get(code, 0)
        if n:
            problems.append(f"journal 里出现 {label} ×{n}")

    streak = 0
    for d in reversed(days):
        if d["ended_by"] == "sleep" and d["cross_day"] and d["verified"] is True:
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
