"""task-206 调试 2：升级暂停会不会把当天洗成 VERIFIED（有农场动作的版本）。"""
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


def show(tag, w):
    run, client, worker = P.mk(w)
    code = run.run()
    rep = run.days[-1]
    obs = w.obs()
    pl = P.plot(sorted(w.tillable))
    left = {t: len(run._leftover(t, obs, pl)) for t in
            ("clear_area", "till_area", "plant_area", "water_area", "harvest", "clear_dead")}
    print(f"\n=== {tag} ===")
    print("code=", code, "ended_by=", rep.ended_by, "verified=", rep.verified)
    print("reason=", str(rep.ended_reason)[:160])
    print("checks=", rep.checks)
    print("leftover=", left, "suspended=", run._tool_suspended_stages(obs))
    print("farm_actions_today=", run.farm_actions_today, "ok_steps=", rep.ok_steps,
          "failed=", rep.failed_steps, "stages=", len(rep.stages))
    print("events=", dict(Counter(e.get("event") for e in run.entries)))


# S1: axe 在途 + 农场里有熟作物（当天有农场动作）+ 4 格杂草（clear_area 暂停）
w1 = TL.FakeWorld(weeds=4, seeds=0, money=3000)
w1.being_upgraded = {"kind": "axe", "name": "Axe"}
w1.tool_upgrade_days_left = 2
w1.dirt = {(60, 14)}
w1.crops = {(60, 14): {"ripe": True, "watered": True}}
show("S1 axe 在途 + 熟作物 + 4 杂草", w1)

# S2: 对照 —— 没有在途工具（对照组是不是真的能 VERIFIED）
w2 = TL.FakeWorld(weeds=4, seeds=0, money=3000)
w2.dirt = {(60, 14)}
w2.crops = {(60, 14): {"ripe": True, "watered": True}}
show("S2 对照：无在途 + 熟作物 + 4 杂草", w2)

# S3: hoe 在途（till_area 暂停）+ 熟作物 + 空地（可开垦）
w3 = TL.FakeWorld(weeds=4, seeds=0, money=3000)
w3.being_upgraded = {"kind": "hoe", "name": "Hoe"}
w3.tool_upgrade_days_left = 2
w3.dirt = {(60, 14)}
w3.crops = {(60, 14): {"ripe": True, "watered": True}}
show("S3 hoe 在途 + 熟作物", w3)
