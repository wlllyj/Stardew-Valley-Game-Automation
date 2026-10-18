import json, collections
p = r"logs\longrun-smoke-0739.jsonl"
rows=[json.loads(l) for l in open(p,encoding="utf-8") if l.strip()]
print("rows", len(rows), "events", dict(collections.Counter(r.get("event") for r in rows)))
de=[r for r in rows if r.get("event")=="day_end"]
fin=[r for r in rows if r.get("event")=="finish"]
print("days", len(de), "finish", fin[-1] if fin else None)
for r in de:
    print("day_key", r.get("day"), "verified", r.get("verified"), "ended_by", r.get("ended_by"),
          "coverage", len(r.get("intent_coverage") or []), "gaps_problem", repr(r.get("gaps_problem")))
    for st in r.get("stages") or []:
        if st.get("stage")=="clear_area" and (st.get("cleared_tiles") or []):
            print("  clear_area cleared_tiles", st.get("cleared_tiles"), "blocker_drop", st.get("blocker_drop"))
    for rec in (r.get("intent_coverage") or [])[:3]:
        print("  rec", rec.get("intent_id"), rec.get("task"), rec.get("executed_steps"), rec.get("reasons"))
