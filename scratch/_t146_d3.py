r"""task-146：逐日关键字段（只写 scratch/）。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "logs" / "longrun-3day-llm-run9c.jsonl"
rows = [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()]

KEYS = [
    "ended_by", "ended_reason", "verified", "ok_steps", "skipped_steps", "failed_steps",
    "assigned_undone", "plot_pending", "deferred_tiles", "unreachable", "unreachable_bound",
    "refused", "refused_bound", "bound_basis", "final_water", "dead_crops", "dead_crops_status",
    "dry_dead", "dry_dead_status", "gave_up_tiles", "final", "notes",
]

for i, r in enumerate(rows):
    if r.get("event") == "day_start":
        print(f"--- day_start L{i+1} {r.get('day')} timeOfDay={r.get('timeOfDay')} "
              f"loc={r.get('location')} weather={r.get('weather')} money={r.get('money')} "
              f"crops={r.get('crops')} unwatered={r.get('unwatered')} stamina={r.get('stamina')}")
    elif r.get("event") == "day_end":
        print(f"--- day_end  L{i+1} {r.get('day')} verified={r.get('verified')}")
        for k in KEYS:
            if k in r:
                v = r[k]
                s = json.dumps(v, ensure_ascii=False)
                print(f"      {k} = {s[:400]}")
        ch = r.get("checks") or {}
        print(f"      checks = {json.dumps(ch, ensure_ascii=False)}")
print("DONE3")
