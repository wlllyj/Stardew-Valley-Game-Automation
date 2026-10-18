"""task-244 基线夹具：从 0.7.42 冒烟账本复现「ok != len(cleared_tiles)」的 9 个阶段。

只读 logs/，输出到 stdout（不写文件）。用法：
    python scratch/_t244_baseline.py [--journal logs/longrun-smoke-0742.jsonl]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter


def load(path: str) -> list[tuple[int, dict]]:
    rows: list[tuple[int, dict]] = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((i, json.loads(line)))
            except json.JSONDecodeError as exc:  # noqa: BLE001
                print(f"[bad line {i}] {exc}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default="logs/longrun-smoke-0742.jsonl")
    args = ap.parse_args()
    rows = load(args.journal)
    print(f"journal={args.journal} rows={len(rows)}")

    ev_counter: Counter[str] = Counter()
    for _, r in rows:
        ev_counter[str(r.get("event"))] += 1
    print("events:", dict(ev_counter))

    stage_keys: Counter[str] = Counter()
    for _, r in rows:
        if r.get("event") == "stage":
            stage_keys.update(r.keys())
    print("stage record keys:", sorted(stage_keys))

    mismatches: list[dict] = []
    for i, r in rows:
        if r.get("event") != "stage":
            continue
        ok = r.get("ok")
        cleared = r.get("cleared_tiles")
        if not isinstance(ok, int) or not isinstance(cleared, (list, type(None))):
            continue
        got = len(cleared or [])
        if ok == got:
            continue
        tiles = [tuple(t) for t in (r.get("tiles") or [])]
        cleared_set = {tuple(t) for t in (cleared or [])}
        extra = sorted(cleared_set - set(tiles))
        mismatches.append(
            {
                "line": i,
                "day": r.get("day"),
                "t": r.get("t"),
                "stage": r.get("stage"),
                "zone": r.get("zone"),
                "ok": ok,
                "cleared": got,
                "diff": ok - got,
                "failed": r.get("failed"),
                "skipped": r.get("skipped"),
                "stopped": r.get("stopped"),
                "assigned": r.get("assigned"),
                "assigned_undone": r.get("assigned_undone"),
                "tiles_n": len(tiles),
                "cleared_not_in_tiles": extra,
                "codes": r.get("codes"),
                "note": (r.get("note") or "")[:120],
            }
        )
    # 账本里阶段记录实际在 `day_end.stages[]`（不是独立 stage 事件）
    day_stage_mismatches: list[dict] = []
    for i, r in rows:
        if r.get("event") != "day_end":
            continue
        for idx, st in enumerate(r.get("stages") or []):
            if not isinstance(st, dict):
                continue
            ok = st.get("ok")
            cleared = st.get("cleared_tiles")
            if not isinstance(ok, int) or not isinstance(cleared, (list, type(None))):
                continue
            got = len(cleared or [])
            if ok == got:
                continue
            tiles_n = st.get("tiles") if isinstance(st.get("tiles"), int) else None
            ok_tiles_raw = st.get("ok_tiles")
            ok_tiles = [tuple(t) for t in ok_tiles_raw] if isinstance(ok_tiles_raw, list) else []
            cleared_set = {tuple(t) for t in (cleared or [])}
            extra = sorted(cleared_set - set(ok_tiles)) if ok_tiles else None
            day_stage_mismatches.append(
                {
                    "line": i,
                    "stage_index": idx,
                    "day": st.get("day") or (r.get("day_key") or r.get("day")),
                    "stage": st.get("stage"),
                    "zone": st.get("zone"),
                    "ok": ok,
                    "cleared": got,
                    "diff": ok - got,
                    "failed": st.get("failed"),
                    "skipped": st.get("skipped"),
                    "stopped": st.get("stopped"),
                    "assigned": st.get("assigned"),
                    "assigned_undone": st.get("assigned_undone"),
                    "tiles_n": tiles_n,
                    "ok_tiles_raw": ok_tiles_raw,
                    "cleared_not_in_ok_tiles": extra,
                    "codes": st.get("codes"),
                    "note": (st.get("note") or "")[:120],
                }
            )
    print(f"\nday_end.stages 里的 mismatches={len(day_stage_mismatches)} (ok != len(cleared_tiles))")
    for m in day_stage_mismatches:
        print(json.dumps(m, ensure_ascii=False, default=str))
    total_ok = sum(int(m["ok"]) for m in day_stage_mismatches)
    total_cleared = sum(int(m["cleared"]) for m in day_stage_mismatches)
    print(f"  这些阶段合计 ok={total_ok} cleared={total_cleared} 差={total_ok - total_cleared}")

    print(f"\nmismatches={len(mismatches)} (事件=stage, ok != len(cleared_tiles))")
    for m in mismatches:
        print(json.dumps(m, ensure_ascii=False, default=str))

    print("\n按阶段汇总：")
    agg: Counter[tuple[str, str]] = Counter()
    diff_total = 0
    for m in mismatches:
        agg[(str(m["stage"]), str(m["zone"]))] += 1
        diff_total += int(m["diff"])
    for k, v in sorted(agg.items()):
        print(f"  {k[0]} / {k[1]}: {v} 阶段")
    print(f"  ok 合计与清单合计的差 = {diff_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
