# 一次性排查：cancel 分支为什么走到 no_plot（本文件可删）
import json
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "brain"))
sys.path.insert(0, os.path.join(HERE, ".."))

from agentfarm.planner import TaskIntent                      # noqa: E402
from tests.test_longrun import FakeWorld, make_run, FakePlanner, FakeWorker  # noqa: E402

w = FakeWorld(weeds=0, seeds=0, money=500)
run = make_run(w, target_days=1,
               planner=FakePlanner(TaskIntent("harvest", "tiles.ripe", "收成熟的", "ripe>0")))
code = run.run()
print("code", code, "sleeps", w.sleeps, "buys", w.buys, "money", w.money)
print("seeds", [(i["id"], i["stack"]) for i in w.inventory])
for e in run.entries:
    ev = e.get("event")
    if ev in ("day_start", "plot", "decision", "policy", "intent_verdict", "plot_exhausted",
              "no_intents", "stage_no_target", "outcome", "idle", "sleep", "day_end"):
        print(json.dumps({k: v for k, v in e.items() if k != "t"}, ensure_ascii=False, default=str)[:400])
