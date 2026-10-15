# task-88 调试：打印 green 夹具与合成账本的 red subjects / history / settled。
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import test_analyze_longrun as T  # noqa: E402

mod = T.mod

rep = T.report_for(T.GREEN, days=3, top=0)
print("GREEN red:", rep["red"]["total"], rep["red"]["subjects"])
print("GREEN window:", rep["window"])

t = T.TestWindowAndSettledClassification("test_seed_gate_afford_is_not_a_failed_purchase")

win3 = t._day_events([1, "summer", 3], verified=False, checks_over={"crops_watered": False})
for dom in (4, 5, 6):
    win3 += t._day_events([1, "summer", dom], verified=True, stage_ok=5)
r = t._report(win3, "dbg_win3.jsonl", days=3, window=3)
print("WIN3 red:", r["red"]["total"], r["red"]["subjects"], "hist:", r["history_problems"]["subjects"])

settled = t._day_events([1, "summer", 3], verified=True, stage_ok=5, extra=[
    {"event": "stage_exhausted", "t": 4.0, "stage": "clear_area", "leftover": 2,
     "capped": 0, "tiles": [[61, 26]]}])
r2 = t._report(settled, "dbg_settled.jsonl", days=1)
print("SETTLED red:", r2["red"]["total"], r2["red"]["subjects"], "settled:", r2["settled"]["subjects"])

seed = t._day_events([1, "summer", 3], verified=True, stage_ok=5, extra=[
    {"event": "seed_gate", "t": 5.0, "seeds": 0, "money": 14, "seed_price": 20, "tillable": 12}])
r3 = t._report(seed, "dbg_seed.jsonl", days=1)
print("SEED red:", r3["red"]["total"], r3["red"]["subjects"])
print("SEED line:", [i["summary"][:120] for i in
                     (mod.cat_wasted([s for s in r3["_sessions"]], 0)
                      + mod.cat_self_report(r3) + mod.cat_missed(r3["_sessions"], 0))]
      if False else "")
for key in ("wasted", "missed"):
    for item in r3["categories"][key]:
        print("   ", key, item["subject"], item["summary"][:110])
print("SEED finish:", r3["finish"])
