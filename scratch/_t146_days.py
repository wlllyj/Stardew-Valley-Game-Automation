# -*- coding: utf-8 -*-
"""task-146：run9c 账本逐日事实提取（只读；输出给 docs/_review-run9c.md 引用）。

用法：python scratch\_t146_days.py
"""
from __future__ import annotations

import json
import pathlib
import sys

LEDGER = pathlib.Path("logs/longrun-3day-llm-run9c.jsonl")
CHECK_KEYS = (
    "slept_by_us",
    "no_blocking_modal",
    "no_hard_failures",
    "no_unmet_stages",
    "crops_watered",
    "watered_outdoor",
    "day_justified",
    "unreachable_within_bound",
    "refused_within_bound",
    "event_blocked",
    "planted_something",
)
INTERESTING = (
    "modal_dismissed", "sell", "sell_failed", "surplus_sell", "buy", "buy_no_space",
    "plant", "water_far", "water_far_skipped", "water_far_unavailable", "plot",
    "review", "review_llm", "lessons", "goto_farm", "sleep", "stage_shortfall_day",
    "stage_shortfall", "stage_exhausted", "stage_no_target", "deferred_tiles",
    "idle", "plots_capped", "no_day_progress", "slept_without_work",
    "plot_exhausted_burst", "review_only_fallback", "review_only_no_target",
    "policy", "intent_vetoed", "decision", "outcome",
)


def load(path: pathlib.Path) -> list[dict]:
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            print(f"坏行 {i}")
            continue
        row["_lineno"] = i
        rows.append(row)
    return rows


def day_key_of(row: dict) -> str:
    for k in ("day_key", "day"):
        v = row.get(k)
        if isinstance(v, (list, tuple)) and len(v) == 3:
            return f"{v[0]}年 {v[1]} {v[2]}日"
    return "?"


def main() -> int:
    rows = load(LEDGER)
    print(f"=== {LEDGER} 行数={len(rows)} ===")
    starts = [r for r in rows if r.get("event") == "day_start"]
    ends = [r for r in rows if r.get("event") == "day_end"]
    print(f"day_start={len(starts)} day_end={len(ends)}")
    for st, en in zip(starts, ends):
        d = en
        chk = d.get("checks") or {}
        print(f"\n--- {day_key_of(st)}  (day_start 行 {st['_lineno']} t={st.get('t')} / "
              f"day_end 行 {d['_lineno']} t={d.get('t')}) ---")
        print(f"  ended_by={d.get('ended_by')!r} reason={str(d.get('ended_reason'))[:150]!r}")
        print(f"  verified={d.get('verified')} ok={d.get('ok_steps')} skip={d.get('skipped_steps')} "
              f"fail={d.get('failed_steps')} actions={d.get('actions')}")
        print(f"  checks={json.dumps(chk, ensure_ascii=False)}")
        print(f"  checks 未通过={[k for k, v in chk.items() if v is not True]}")
        print(f"  stage/plot 口径: plot_pending={d.get('plot_pending')} deferred={d.get('deferred_tiles')} "
              f"assigned_undone={d.get('assigned_undone')} unreachable={d.get('unreachable')}/{d.get('unreachable_bound')} "
              f"refused={d.get('refused')}/{d.get('refused_bound')} bound_basis={d.get('bound_basis')}")
        fw = d.get("final_water")
        if isinstance(fw, dict):
            print(f"  final_water={json.dumps({k: fw.get(k) for k in ('scope','location','tiles','crops','dry','status')}, ensure_ascii=False)}")
        fin = d.get("final") or {}
        print(f"  final.location={fin.get('location')} money={fin.get('money')} waterLeft={fin.get('waterLeft')} "
              f"inventory={json.dumps(fin.get('inventory'), ensure_ascii=False)[:220]}")
        print(f"  day_start 快照 location={((st.get('snapshot') or {}).get('location')) if isinstance(st.get('snapshot'), dict) else None} "
              f"money={((st.get('snapshot') or {}).get('money')) if isinstance(st.get('snapshot'), dict) else None}")
        for s in d.get("stages") or []:
            print(f"    stage {s.get('stage'):<12} tiles={s.get('tiles')} ok={s.get('ok')} skip={s.get('skipped')} "
                  f"fail={s.get('failed')} leftover={s.get('leftover')} assigned={s.get('assigned')} "
                  f"assigned_undone={s.get('assigned_undone')} stopped={s.get('stopped')!r} "
                  f"unreachable={s.get('unreachable')} refused={s.get('refused')} encircled={s.get('encircled')}")
    fin = [r for r in rows if r.get("event") == "finish"]
    print(f"\nfinish={json.dumps(fin[0] if fin else None, ensure_ascii=False)[:400]}")
    print("\n=== 关注事件 ===")
    for name in INTERESTING:
        hits = [r for r in rows if r.get("event") == name]
        if not hits:
            continue
        print(f"\n-- {name} ×{len(hits)}")
        for h in hits:
            extra = {k: v for k, v in h.items() if k not in ("event", "_lineno")}
            txt = json.dumps(extra, ensure_ascii=False)
            print(f"  行{h['_lineno']} {txt[:400]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
