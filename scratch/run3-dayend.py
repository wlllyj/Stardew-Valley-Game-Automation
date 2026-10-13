# -*- coding: utf-8 -*-
"""run3 账本逐日取证（只读 logs\\longrun-3day-llm-run3.jsonl）。

打印：day_start / day_end / sleep / finish 的关键字段，尤其是 day_end.final.location
（Lead 新增判据）与 day_after、checks、final_water、counts_scope。
"""
from __future__ import annotations

import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
JL = os.path.join(REPO, "logs", "longrun-3day-llm-run3.jsonl")

recs = []
with open(JL, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            recs.append(json.loads(line))

print(f"总记录 = {len(recs)}")

first_dayend = next((r for r in recs if r.get("event") == "day_end"), None)
print(f"\n[day_end 顶层键] {sorted(first_dayend.keys())}")
if isinstance(first_dayend.get("final"), dict):
    print(f"[final 键] {sorted(first_dayend['final'].keys())}")
if isinstance(first_dayend.get("day_start"), dict):
    print(f"[day_start 键] {sorted(first_dayend['day_start'].keys())}")


def g(d, *ks, default=None):
    cur = d
    for k in ks:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def clock(c):
    if not isinstance(c, dict):
        return c
    return f"{c.get('season')} {c.get('day')} tod={c.get('timeOfDay')} {c.get('weather')}"


print("\n=== day_start（顶层键 + 关键值）===")
for i, r in enumerate(recs):
    if r.get("event") != "day_start":
        continue
    print(f"#{i:3} t={r.get('t')} keys={sorted(r.keys())}")
    print(f"      {json.dumps({k: v for k, v in r.items() if k not in ('event',)}, ensure_ascii=False)[:700]}")

print("\n=== day_end ===")
for i, r in enumerate(recs):
    if r.get("event") != "day_end":
        continue
    fin = r.get("final") or {}
    fw = r.get("final_water") or {}
    print(f"#{i:3} t={r.get('t')} ended_by={r.get('ended_by')} verified={r.get('verified')}")
    print(f"     ended_reason={(r.get('ended_reason') or '')[:150]}")
    print(f"     day_start={r.get('day_start')} day_after={r.get('day_after')}")
    print(f"     final.location={fin.get('location')!r} final.day={fin.get('day')} "
          f"final.tod={fin.get('timeOfDay')} final.tile={fin.get('tile')} "
          f"final.stamina={fin.get('stamina')} final.isInBed={fin.get('isInBed')} "
          f"final.money={fin.get('money')} final.seeds={fin.get('seeds')} final.waterLeft={fin.get('waterLeft')}")
    print(f"     final.scope={fin.get('counts_scope')} crops={fin.get('crops')} "
          f"unwatered_crops={fin.get('unwatered_crops')} tillable={fin.get('tillable')} ripe={fin.get('ripe')}")
    print(f"     day_text={r.get('day_text')} ok_steps={r.get('ok_steps')} skipped={r.get('skipped_steps')} "
          f"failed={r.get('failed_steps')}")
    print(f"     notes={json.dumps(r.get('notes'), ensure_ascii=False)[:400]}")
    print(f"     final_water={json.dumps(fw, ensure_ascii=False)[:260]}")
    print(f"     checks={json.dumps(r.get('checks'), ensure_ascii=False)}")
    st = r.get("stages") or []
    if st:
        print(f"     stages({len(st)})={json.dumps(st, ensure_ascii=False)[:600]}")

print("\n=== sleep ===")
for i, r in enumerate(recs):
    if r.get("event") != "sleep":
        continue
    print(f"#{i:3} t={r.get('t')} ok={r.get('ok')} code={r.get('code')} reason={(r.get('reason') or '')[:120]}")
    print(f"     before={clock(g(r, 'before', 'clock'))} after={clock(g(r, 'after', 'clock'))}")

print("\n=== finish / day_cap ===")
for i, r in enumerate(recs):
    if r.get("event") in ("finish", "day_cap"):
        print(f"#{i:3} {json.dumps(r, ensure_ascii=False)[:500]}")
