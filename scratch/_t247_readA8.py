"""task-247 只读取证：从 A8 真账本提取 winter 7 的收尾死循环现场。

只读：不改任何生产文件；输出供设计/夹具用。
用法：$env:PYTHONUTF8=1; python scratch\\_t247_readA8.py [日志名] [winter 7]
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
LOG = REPO / "logs" / (sys.argv[1] if len(sys.argv) > 1 else "longrun-runA8-0743.jsonl")
TARGET = sys.argv[2] if len(sys.argv) > 2 else "winter 7"


def day_tag(row: dict) -> str | None:
    day = row.get("day")
    if isinstance(day, list) and len(day) == 3:
        return f"{day[1]} {day[2]}"
    return None


def brief(row: dict, limit: int = 900) -> str:
    keep = ("t", "event", "day", "stage", "zone", "tiles", "leftover", "doomed", "capped",
            "attempted", "unreachable", "unreachable_tiles", "encircled", "encircled_tiles",
            "encircled_tried", "count", "why", "note", "verified", "ended_by", "ended_reason",
            "unreachable_bound", "unreachable_exempt", "bound_basis", "checks", "stages",
            "intent_coverage", "work_reasons", "tasks", "reason", "mode", "task")
    out = {k: row.get(k) for k in keep if k in row}
    return json.dumps(out, ensure_ascii=False)[:limit]


def main() -> int:
    rows = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"# {LOG.name}: {len(rows)} rows")

    days: list[tuple[str, list[dict]]] = []
    for row in rows:
        tag = day_tag(row)
        if row.get("event") == "day_start":
            days.append((tag or "?", [row]))
        elif days:
            days[-1][1].append(row)

    print("\n== 所有 day ==")
    for tag, day_rows in days:
        end = next((r for r in day_rows if r.get("event") == "day_end"), None)
        print(f"day={tag} rows={len(day_rows)}")
        if end:
            print(f"   verified={end.get('verified')} ended_by={end.get('ended_by')} "
                  f"unreachable={end.get('unreachable')} bound={end.get('unreachable_bound')} "
                  f"exempt={end.get('unreachable_exempt')} encircled={end.get('encircled')} "
                  f"bound_basis={end.get('bound_basis')}")
            print(f"   reason={str(end.get('ended_reason'))[:220]}")
            print(f"   checks={end.get('checks')}")
            print(f"   plot_pending={end.get('plot_pending')} assigned_undone={end.get('assigned_undone')} "
                  f"deferred_tiles={end.get('deferred_tiles')}")

    match = [(tag, rs) for tag, rs in days if tag == TARGET]
    if not match:
        print(f"\n!! 未找到 {TARGET}；可用: {[t for t, _ in days]}")
        return 0
    tag, day_rows = match[-1]
    print(f"\n== day {tag}：{len(day_rows)} 条，关键事件 ==")
    for row in day_rows:
        ev = str(row.get("event"))
        if ("resume" in ev or "work_spot" in ev or "progress" in ev or "unreach" in ev
                or "encircl" in ev or "plot_exhausted" in ev or "frontier" in ev
                or ev in ("day_start", "day_end", "idle", "stage_exhausted", "blocked")):
            print(brief(row))

    print(f"\n== day {tag} stages ==")
    for row in day_rows:
        for st in row.get("stages") or []:
            print(json.dumps(st, ensure_ascii=False)[:800])

    print(f"\n== day {tag} unreachable 明细（全量） ==")
    for row in day_rows:
        if row.get("event") in ("unreachable", "unreachable_stage", "unreachable_summary"):
            print(brief(row, 1500))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
