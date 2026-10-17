"""task-206 调试 5：axe 在途（clear_area 暂停）+ 壶可用（当天有浇水动作）+ 地里有杂草 ⇒ 会不会 VERIFIED。"""
import importlib.util
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("T206_ROOT", os.path.join(ROOT, "scratch", "_t206_post"))
os.environ.setdefault("PYTHONUTF8", "1")

spec = importlib.util.spec_from_file_location("p206", os.path.join(ROOT, "scratch", "_t206_probe.py"))
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
TL = P.TL

TILES = [(60, 10), (60, 11), (60, 12), (60, 13)]


def build(being):
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    w.tillable = set(TILES)
    w.blockers = {(60, 11): "weed", (60, 12): "weed", (60, 13): "weed"}
    w.dirt = {(60, 10)}
    w.crops = {(60, 10): {"ripe": False, "watered": False}}
    w.tool_tiers = {"axe": 0, "hoe": 0, "can": 0}
    if being:
        w.being_upgraded = {"kind": being, "name": being.title()}
        w.tool_upgrade_days_left = 2
    return w


for tag, being in (("S8 axe 在途（clear_area 暂停）+ 待浇活苗 + 3 杂草", "axe"), ("S9 对照：无在途", None)):
    w = build(being)
    run, client, worker = P.mk(w)
    fixed = P.plot(TILES)
    run._ensure_plot = lambda obs, rep, _p=fixed: _p
    code = run.run()
    rep = run.days[-1]
    obs = w.obs()
    left = {t: len(run._leftover(t, obs, fixed)) for t in ("clear_area", "till_area", "plant_area", "water_area")}
    print(f"\n=== {tag} ===")
    print("code=", code, "ended_by=", rep.ended_by, "verified=", rep.verified)
    print("reason=", str(rep.ended_reason)[:150])
    print("checks=", rep.checks)
    print("leftover=", left, "suspended=", run._tool_suspended_stages(obs),
          "farm_actions=", run.farm_actions_today, "ok_steps=", rep.ok_steps)
    print("stages=", [(s.get("stage"), s.get("ok"), s.get("leftover"), s.get("stopped")) for s in rep.stages])
    print("events=", dict(Counter(e.get("event") for e in run.entries)))
