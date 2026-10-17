"""task-206 调试：F1（axe 在途）世界里 no_unmet_stages 与 _leftover / blocked_work 的关系。"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("T206_ROOT", os.path.join(ROOT, "scratch", "_t206_post"))
os.environ.setdefault("PYTHONUTF8", "1")

spec = importlib.util.spec_from_file_location("p206", os.path.join(ROOT, "scratch", "_t206_probe.py"))
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)

TL = P.TL
print("ROOT=", P.ROOT, "has_205=", P.has_205())

w = TL.FakeWorld(weeds=4, seeds=0, money=3000)
w.being_upgraded = {"kind": "axe", "name": "Axe"}
w.tool_upgrade_days_left = 2
run, client, worker = P.mk(w)
code = run.run()
rep = run.days[-1]
print("code=", code, "ended_by=", rep.ended_by)
print("reason=", str(rep.ended_reason)[:200])
print("checks=", rep.checks)
print("stages=", [(s.get("stage"), s.get("ok"), s.get("leftover"), s.get("stopped")) for s in rep.stages])
print("plot=", None if not run.plot else (run.plot.get("zone"), len(run.plot.get("tiles") or [])))
obs = w.obs()
print("tiles=", {k: v.get("kind") for k, v in (TL.FarmWorker.tiles_of(obs)).items()})
print("tillable=", sorted(getattr(w, "tillable", []))[:12], "weeds blockers=", list(w.blockers.items())[:6])
pl = P.plot(sorted(w.tillable))
for task in ("clear_area", "till_area", "plant_area", "water_area", "harvest", "clear_dead"):
    try:
        left = run._leftover(task, obs, pl)
        tiles = run._stage_tiles(task, obs, pl)
        print(f"  {task:12s} leftover={len(left):2d} tiles={len(tiles):2d}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {task:12s} ERROR {exc}")
print("work_reasons=", run.work_reasons(obs))
print("notes=", rep.notes)
names = [e.get("event") for e in run.entries]
from collections import Counter
print("events=", dict(Counter(names)))
print("suspended=", run._tool_suspended_stages(obs) if hasattr(run, "_tool_suspended_stages") else None)
print("due=", run._tool_upgrade_due(obs) if hasattr(run, "_tool_upgrade_due") else None)
print("slept_without_work=", getattr(rep, "slept_without_work", None))
