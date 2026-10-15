# task-95 只读探针：确认 report["red"]["subjects"] 与 undecidable 的形态（不写生产文件）
import contextlib
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("analyze_longrun", os.path.join(ROOT, "tools", "analyze-longrun.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

EV = [
    {"event": "day_start", "t": 0.1, "day": [1, "summer", 3], "timeOfDay": 600, "stamina": 270.0,
     "money": 14, "crops": 31, "unwatered": 31, "location": "Farm", "weather": "sunny"},
    {"event": "day_end", "t": 9.0, "day": [1, "summer", 3], "day_text": "", "ended_by": "sleep",
     "ended_reason": "night", "verified": True,
     "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                "watered_outdoor": True},
     "stages": [{"stage": "clear_dead", "ok": 5, "skipped": 0, "failed": 0, "env_block": 0,
                 "inconclusive": 0, "stopped": None, "leftover": 0}],
     "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0, "notes": [],
     "final": {"day": [1, "summer", 4], "timeOfDay": 600, "location": "Farm", "tile": [64, 15],
               "stamina": 270.0, "money": 14, "isInBed": False, "crops": 31, "unwatered_crops": 0,
               "ripe": 0, "tillable": 200, "waterLeft": 40, "seeds": []},
     "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0, "scope": "farm"}},
]
ledger = os.path.join(HERE, "_t95_probe.jsonl")
with open(ledger, "w", encoding="utf-8") as fh:
    fh.write("\n".join(json.dumps(e, ensure_ascii=False) for e in EV) + "\n")

out = os.path.join(HERE, "_t95_probe_out.json")
buf = io.BytesIO()
wrapper = io.TextIOWrapper(buf, encoding="utf-8", write_through=True)
with contextlib.redirect_stdout(wrapper):
    rc = mod.main(["--journal", ledger, "--json", "--days", "1"])
    wrapper.flush()
    raw = buf.getvalue().decode("utf-8")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(raw)
print("RC", rc, "OUT", out)

rep = json.loads(raw)
print("RED keys:", sorted(rep["red"].keys()))
print("RED total:", rep["red"]["total"], "subjects:", rep["red"]["subjects"])
print("dead_crops keys:", sorted((rep.get("dead_crops") or {}).keys()))
print("undecidable[0]:", rep["undecidable"][0] if rep["undecidable"] else None)
print("undecidable count:", len(rep["undecidable"]))
print("--- header 死苗 line ---")
for line in mod.render_text(rep, 50).splitlines():
    if "死苗" in line:
        print(line)
