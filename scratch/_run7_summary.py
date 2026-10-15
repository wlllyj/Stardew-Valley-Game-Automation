# -*- coding: utf-8 -*-
"""run7 逐日取证（Lead 只读）。用法：python scratch/_run7_summary.py [journal]"""
import collections
import io
import json
import sys

p = sys.argv[1] if len(sys.argv) > 1 else r"logs\longrun-3day-llm-run7.jsonl"
rows = [json.loads(l) for l in io.open(p, encoding="utf-8", errors="replace") if l.strip()]
print("rows =", len(rows))

print("\n== 逐日 day_end ==")
for r in rows:
    if r.get("event") != "day_end":
        continue
    st = r.get("stages")
    items = st.items() if isinstance(st, dict) else [(s.get("stage"), s) for s in (st or [])]
    per = ", ".join(f"{k} ok{v.get('ok')}/fail{v.get('failed')}/left{v.get('leftover')}"
                    for k, v in items if isinstance(v, dict))
    day = (r.get("final") or {}).get("day")
    print(f"{day} {r.get('ended_by'):<14} verified={r.get('verified')} "
          f"ok={r.get('ok_steps')} failed={r.get('failed_steps')} act={r.get('actions')} "
          f"| checks={r.get('checks')} | {per}")
    print(f"    reason={str(r.get('ended_reason'))[:150]}")

print("\n== 事件计数 ==")
print(dict(collections.Counter(r.get("event") for r in rows)))

print("\n== 经济/播种相关 ==")
for ev in ("buy", "seed_gate", "plant", "sow", "harvest", "sell", "ship"):
    hits = [r for r in rows if r.get("event") == ev]
    if hits:
        print(f"{ev}: {len(hits)} 条")
        for h in hits[:6]:
            print("   ", {k: v for k, v in h.items() if k in ("t", "day", "ok", "code", "receipt", "seeds", "money", "item", "count")})

print("\n== water_far / plot ==")
wf = [r for r in rows if r.get("event") == "water_far"]
print("water_far:", len(wf), "ok:", sum(1 for r in wf if r.get("ok")))
print("plot:", len([r for r in rows if r.get("event") == "plot"]))

print("\n== 决策 ==")
dec = [r for r in rows if r.get("event") == "decision"]
print("decision:", len(dec), "llm:", sum(1 for r in dec if r.get("llm")))
