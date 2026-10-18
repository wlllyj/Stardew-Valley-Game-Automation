# -*- coding: utf-8 -*-
"""task-12 §7 取证：0.7.44 真机冒烟账本（smoke-0744）独立读数，只读账本。

用法：python scratch/_t0744_smoke_read.py
输出：stdout + scratch/_t0744_c2_smoke.txt（UTF-8，不用 PowerShell 重定向）。
"""
import json
import pathlib
from collections import Counter

REPO = pathlib.Path(__file__).resolve().parents[1]
LEDGER = REPO / "logs" / "longrun-smoke-0744.jsonl"
OUT = REPO / "scratch" / "_t0744_c2_smoke.txt"
_OUT = []


def emit(s=""):
    _OUT.append(s)
    print(s)


def main() -> int:
    rows = []
    with open(LEDGER, "r", encoding="utf-8", errors="replace") as f:
        for i, ln in enumerate(f, 1):
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append((i, json.loads(ln)))
            except json.JSONDecodeError:
                rows.append((i, None))
    emit(f"# smoke-0744 独立读数（task-12 §7） ledger={LEDGER.name} rows={len(rows)}")
    emit(f"event_counts={Counter((r or {}).get('event') for _, r in rows).most_common()}")
    for ln, r in rows:
        if not r or r.get("event") != "day_end":
            continue
        checks = r.get("checks") or {}
        emit("=" * 100)
        emit(f"line {ln}: day={r.get('day')} ended_by={r.get('ended_by')!r} verified={r.get('verified')}")
        emit(f"  ended_reason={r.get('ended_reason')!r}")
        emit(f"  false_checks={[k for k, v in checks.items() if v is False]}")
        emit(f"  plot_pending={r.get('plot_pending')} plot_pending_by_kind={r.get('plot_pending_by_kind')}")
        emit(f"  assigned_undone={r.get('assigned_undone')} unreachable={r.get('unreachable')}")
        for p in r.get("plots") or []:
            if isinstance(p, dict):
                note = str(p.get("note") or "")
                emit(f"  plot zone={p.get('zone')!r} anchor={p.get('anchor')!r} tiles={p.get('tiles')!r} "
                     f"has_trunc_note={'location.tilesTruncated=true' in note}")
    emit("#" * 100)
    for ln, r in rows:
        if not r:
            continue
        ev = r.get("event")
        if ev in ("plot_exhausted_burst", "no_progress_burst", "plot_exhausted", "sleep",
                  "resume_walk", "stage_stop_named", "stage_shortfall", "stage_exhausted"):
            keep = {k: v for k, v in r.items() if k != "event"}
            s = json.dumps(keep, ensure_ascii=False)
            if len(s) > 700:
                s = s[:700] + "…"
            emit(f"line {ln}: {ev} :: {s}")
    OUT.write_text("\n".join(_OUT) + "\n", encoding="utf-8")
    print(f"\n[evidence] {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
