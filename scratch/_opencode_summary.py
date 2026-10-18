import json
from pathlib import Path
j = Path("logs/longrun-trial-opencode-1.jsonl")
lines = [json.loads(l) for l in j.read_text(encoding="utf-8").splitlines() if l.strip()]
from collections import Counter
print("事件计数:", dict(Counter(e.get("event") for e in lines)))
for e in lines:
    if e.get("event") == "day_end":
        print("\n--- day_end ---")
        for k in ("day_text","ended_by","verified","ok_steps","skipped_steps","failed_steps",
                  "stages_seen","no_unmet_stages","free_slots","inventory_blocked","loot_lost_steps"):
            if k in e: print(f"  {k} = {e[k]}")
        ch = e.get("checks") or {}
        red = [k for k,v in ch.items() if v is False]
        print(f"  checks 红键 = {red or '无'}")
    if e.get("event") == "finish":
        print("\n--- finish ---")
        for k in ("code","verified_streak","target_days","actions","minutes","stages_seen",
                  "no_unmet_stages","unmet_days","stuck_flushes"):
            if k in e: print(f"  {k} = {e[k]}")
