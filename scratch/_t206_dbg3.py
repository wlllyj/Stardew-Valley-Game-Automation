"""task-206 调试 3：把杂草和熟作物放进同一块地（强制 _ensure_plot），验证暂停阶段 leftover 是否被洗成 no_unmet_stages=True。"""
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

TILES = [(60, 10), (60, 11), (60, 12), (61, 10)]


def build(being):
    w = TL.FakeWorld(weeds=0, seeds=0, money=3000)
    w.tillable = set(TILES)
    w.blockers = {(60, 10): "weed", (60, 11): "weed", (60, 12): "weed"}
    w.dirt = {(61, 10)}
    w.crops = {(61, 10): {"ripe": True, "watered": True}}
    w.tool_tiers = {"axe": 0, "hoe": 0, "can": 0}
    if being:
        w.being_upgraded = {"kind": being, "name": being.title()}
        w.tool_upgrade_days_left = 2
    return w


for tag, being in (("S4 axe 在途（clear_area 暂停）", "axe"), ("S5 对照：无在途", None)):
    w = build(being)
    run, client, worker = P.mk(w)
    fixed = P.plot(TILES)
    run._ensure_plot = lambda obs, rep, _p=fixed: _p
    code = run.run()
    rep = run.days[-1]
    obs = w.obs()
    left = {t: len(run._leftover(t, obs, fixed)) for t in ("clear_area", "harvest", "till_area")}
    print(f"\n=== {tag} ===")
    print("code=", code, "ended_by=", rep.ended_by, "verified=", rep.verified)
    print("reason=", str(rep.ended_reason)[:150])
    print("checks=", rep.checks)
    print("leftover=", left, "suspended=", run._tool_suspended_stages(obs),
          "farm_actions=", run.farm_actions_today, "ok_steps=", rep.ok_steps)
    print("stages=", [(s.get("stage"), s.get("ok"), s.get("leftover"), s.get("stopped")) for s in rep.stages])
    print("events=", dict(Counter(e.get("event") for e in run.entries)))
