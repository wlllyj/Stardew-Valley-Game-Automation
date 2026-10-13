# -*- coding: utf-8 -*-
"""run5 收工取证：逐日 day_end 表 + finish 原文 + 阶段/失败步汇总（只读账本）。"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[1]
JL = REPO / "logs" / "longrun-3day-llm-run5.jsonl"

recs = [json.loads(ln) for ln in JL.read_text(encoding="utf-8").splitlines() if ln.strip()]
print(f"账本 = {JL.name}  总记录 {len(recs)} 行")


def dd(v):
    return "/".join(str(x) for x in v) if isinstance(v, list) else str(v)


def summ(x):
    return json.dumps(x, ensure_ascii=False) if not isinstance(x, int) else f"<int {x}>"


print("\n=== day_start（原始字段名）===")
first_ds = next((r for r in recs if r.get("event") == "day_start"), None)
print(f"键 = {sorted(first_ds.keys())}")
for i, r in enumerate(recs):
    if r.get("event") != "day_start":
        continue
    print(f"#{i:3} t={r.get('t')} " + json.dumps({k: v for k, v in r.items() if k != "event"},
                                                ensure_ascii=False)[:400])

print("\n=== day_end ===")
for i, r in enumerate(recs):
    if r.get("event") != "day_end":
        continue
    f = r.get("final") or {}
    fw = r.get("final_water") or {}
    st = r.get("stages") or []
    ok = sum(s.get("ok", 0) for s in st)
    failed = sum(s.get("failed", 0) for s in st)
    print(f"#{i:3} t={r.get('t')} day={dd(r.get('day'))} ended_by={r.get('ended_by')} verified={r.get('verified')} "
          f"day_after={dd(r.get('day_after'))} ok={r.get('ok_steps')} skipped={r.get('skipped_steps')} "
          f"failed={r.get('failed_steps')} stages_ok={ok} stages_failed={failed}")
    print(f"     ended_reason={(r.get('ended_reason') or '')[:160]}")
    print(f"     final: loc={f.get('location')} tile={f.get('tile')} tod={f.get('timeOfDay')} "
          f"isInBed={f.get('isInBed')} stamina={f.get('stamina')} money={f.get('money')} "
          f"waterLeft={f.get('waterLeft')} crops={f.get('crops')} unwatered={f.get('unwatered_crops')} "
          f"tillable={f.get('tillable')} seeds={f.get('seeds')} scope={f.get('counts_scope')}")
    print(f"     farm={json.dumps(f.get('farm'), ensure_ascii=False)[:260]}")
    print(f"     final_water={json.dumps(fw, ensure_ascii=False)[:300]}")
    print(f"     checks={json.dumps(r.get('checks'), ensure_ascii=False)}")
    notes = r.get("notes") or []
    if notes:
        print(f"     notes({len(notes)})={json.dumps(notes, ensure_ascii=False)[:700]}")
    fs = r.get("failed_steps")
    if fs:
        print(f"     failed_steps={summ(fs)[:600]}")
    stages = [f"{s.get('stage')}:{s.get('tiles')}/{s.get('ok')}ok/{s.get('failed')}fail/{s.get('leftover')}left" for s in st]
    if stages:
        print(f"     stages({len(st)})={stages}")

print("\n=== sleep ===")
for i, r in enumerate(recs):
    if r.get("event") != "sleep":
        continue
    print(f"#{i:3} t={r.get('t')} ok={r.get('ok')} code={r.get('code')} reason={(r.get('reason') or '')[:200]}")

print("\n=== blocked / 点名事件 ===")
for i, r in enumerate(recs):
    if r.get("event") == "blocked":
        print(f"#{i:3} {json.dumps(r, ensure_ascii=False)[:400]}")

print("\n=== 事件计数 ===")
print(json.dumps(Counter(r.get("event") for r in recs).most_common(), ensure_ascii=False))
src, llm = Counter(), Counter()
for r in recs:
    if r.get("event") == "decision":
        src[r.get("source")] += 1
        llm[bool(r.get("llm"))] += 1
        if r.get("truncated"):
            llm["truncated"] += 1
print(f"decision source={dict(src)} llm_true={llm[True]} llm_false={llm[False]} truncated={llm.get('truncated', 0)}")

print("\n=== finish / day_cap ===")
for i, r in enumerate(recs):
    if r.get("event") in ("finish", "day_cap"):
        print(f"#{i:3} {json.dumps(r, ensure_ascii=False)}")
