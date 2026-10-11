# -*- coding: utf-8 -*-
"""一次性排查：为什么"昨天种下、没浇"的作物没有让 water_area 排在最前。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brain"))
sys.path.insert(0, str(ROOT / "tests"))

from test_longrun import FakeWorld, make_run  # noqa: E402

w = FakeWorld(weeds=4, seeds=10, money=500)
w.dirt.add((60, 10))
w.crops[(60, 10)] = {"watered": False, "ripe": False}
run = make_run(w, target_days=1)
run.max_days = 1
code = run.run()
print("code =", code)
print("days =", len(run.days))
rep = run.days[0]
print("ended_by =", rep.ended_by, "|", rep.ended_reason[:120])
print("stages =", [(s["stage"], s["ok"], s["skipped"], s["failed"], s["leftover"]) for s in rep.stages])
print("notes =", rep.notes)
print("checks =", rep.checks)
print("blocked =", run.blocked)
for e in run.entries:
    ev = e.get("event")
    if ev == "decision":
        print("  decision", e.get("zone"), e.get("boundary"), e.get("source"),
              [i.get("task") for i in e.get("intents", [])])
    elif ev == "policy":
        print("  policy", e.get("note"), e.get("intents"))
    elif ev == "idle":
        print("  idle", e.get("rounds"), e.get("intents"), e.get("acted"))
    elif ev == "stage_no_target":
        print("  no_target", e.get("stage"), e.get("leftover"), e.get("zone"))
    elif ev == "blocked":
        print("  blocked", e.get("tile"), e.get("action"), str(e.get("reason"))[:60])

print("--- 收尾诊断 ---")
obs = w.obs()
plot = run.plot or {}
print("plot =", plot.get("zone"), len(plot.get("tiles") or []))
brief = run._plot_brief(obs, plot)
print("brief.blockers =", brief.blockers, "tillable =", brief.tillable,
      "unprepared =", brief.unprepared, "counts =", brief.counts, "target =", brief.target_tiles)
print("stage_tiles(clear) =", run._stage_tiles("clear_area", obs, plot))
print("stage_tiles(till)  =", run._stage_tiles("till_area", obs, plot))
print("plot_has_work =", run._plot_has_work(obs, plot.get("tiles") or []))
tmap = __import__("agentfarm.farmwork", fromlist=["x"]).FarmWorker.tiles_of(obs)
print("plot 里的格 kind =", [(t, (tmap.get(t) or {}).get("kind")) for t in (plot.get("tiles") or [])][:30])
print("obs 里有 kind 的格 =", sorted((t, v.get("kind")) for t, v in tmap.items())[:30])

