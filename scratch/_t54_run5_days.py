"""run5 账本逐日关键值 dump（deputy-lead 只读复核用）。

用法: python scratch/_t54_run5_days.py [journal]
默认 logs/longrun-3day-llm-run5.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
J = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "logs" / "longrun-3day-llm-run5.jsonl"

rows = []
for i, line in enumerate(J.read_text(encoding="utf-8").splitlines(), 1):
    line = line.strip()
    if not line:
        continue
    try:
        o = json.loads(line)
    except json.JSONDecodeError:
        continue
    o["_lineno"] = i
    rows.append(o)

print(f"# {J.name}: {len(rows)} 行")
for o in rows:
    if o.get("event") != "day_end":
        continue
    de = o
    fin = de.get("final") or {}
    farm = fin.get("farm") or {}
    fw = de.get("final_water") or {}
    print(
        f"[L{o['_lineno']}] day={de.get('final', {}).get('day')} day_after={de.get('day_after')} "
        f"ended_by={de.get('ended_by')} reason={str(de.get('ended_reason'))[:70]}"
    )
    print(
        f"    window: crops={fin.get('crops')} unwatered={fin.get('unwatered_crops')} "
        f"counts_scope={fin.get('counts_scope')} tiles_kind={type(fin.get('tiles')).__name__}"
    )
    print(
        f"    farm: loaded={farm.get('loaded')} complete={farm.get('complete')} crops={farm.get('crops')} "
        f"dryCrops={farm.get('dryCrops')} unwateredCrops={farm.get('unwateredCrops')} hoeDirt={farm.get('hoeDirt')}"
    )
    print(
        f"    final_water: {fw}   watered_outdoor={de.get('checks', {}).get('watered_outdoor')} "
        f"crops_watered={de.get('checks', {}).get('crops_watered')} no_unmet={de.get('checks', {}).get('no_unmet_stages')}"
    )
    print(
        f"    unreachable={de.get('unreachable')} exempt={de.get('unreachable_exempt')} bound={de.get('unreachable_bound')} "
        f"refused={de.get('refused')} refused_exempt={de.get('refused_exempt')} bound={de.get('refused_bound')} "
        f"failed_steps={de.get('failed_steps')} attempted={de.get('attempted')}"
    )
    stages = de.get("stages") or []
    for s in stages:
        print(
            f"    stage {s.get('stage')}: ok={s.get('ok')} failed={s.get('failed')} "
            f"failed_any={s.get('failed_any')} skipped={s.get('skipped')} leftover={s.get('leftover')} "
            f"attempted={s.get('attempted')} unreachable={s.get('unreachable')} refused={s.get('refused')} "
            f"unreachable_tiles={s.get('unreachable_tiles')} refused_tiles={s.get('refused_tiles')}"
        )
    for ev in (de.get("event") or []):
        print(f"    event {ev}")

print("\n# unreachable / tool_refused / goto_farm / blocked 事件（全部）")
for o in rows:
    if o.get("event") not in ("unreachable", "tool_refused", "goto_farm", "blocked"):
        continue
    d = o
    print(f"[L{o['_lineno']}] {o.get('event')}: tile={d.get('tile')} action={d.get('action')} "
          f"stage={d.get('stage')} status={d.get('status')} kind={d.get('kind')} reason={str(d.get('reason'))[:90]}")
