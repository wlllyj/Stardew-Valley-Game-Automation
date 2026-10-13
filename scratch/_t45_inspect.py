import json, pathlib
p = pathlib.Path("logs/longrun-3day-llm-run5.jsonl")
evs = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
print("总事件", len(evs), "类型计数:", {k: sum(1 for e in evs if e.get("event")==k) for k in sorted({e.get("event") for e in evs})})
for i,e in enumerate(evs,1):
    if e.get("event") in ("day_start","day_end","sleep","finish"):
        if e.get("event")=="day_end":
            print(i, "day_end keys:", sorted(e.keys()))
            print("   day_start=", e.get("day_start"), "final.day=", (e.get("final") or {}).get("day"),
                  "cross_day=", e.get("cross_day"), "ended_by=", e.get("ended_by"), "t=", e.get("t"))
        elif e.get("event")=="day_start":
            print(i, "day_start", e.get("day"), "t=", e.get("t"), "money=", e.get("money"))
        elif e.get("event")=="finish":
            print(i, "finish", e)
        else:
            print(i, "sleep", {k:v for k,v in e.items() if k!="receipt"})
