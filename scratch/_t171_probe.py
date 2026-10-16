r"""task-171 探针：task-170（harvest 判据/回执/同格上限/守卫解钉）六条作弊通道的实测。

只读生产代码；只写 scratch/。`T171_ROOT` 可切换到另一棵树（做 pre/post 对照）。
用法：`& $py -W error::SyntaxWarning scratch\_t171_probe.py`
"""
import os
import sys

ROOT = os.environ.get("T171_ROOT") or r"D:\Deepseek Harness Workspace\星露谷游戏自动化"
for _p in (ROOT, os.path.join(ROOT, "brain"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import test_longrun as TL  # noqa: E402
from agentfarm.farmwork import FarmWorker, tile_ready, harvest_tool  # noqa: E402
from agentfarm.longrun import DayReport, MAX_TILE_ATTEMPTS  # noqa: E402

PASS, FAIL = [], []


def check(tag, ok, detail=""):
    (PASS if ok else FAIL).append(tag)
    print(("  ok   " if ok else "  FAIL ") + tag + (("  :: " + detail) if detail else ""))


T = (60, 10)


def mk(ready=True, ripe=True, method="Grab", extra=None, world_cls=TL.FakeWorld,
       player=(60, 12), seeds=0, **kw):
    w = world_cls(weeds=0, seeds=seeds, money=0, water_left=40, **kw)
    w.player_tile = list(player)
    w.dirt.add(T)
    c = {"watered": True, "ripe": ripe, "ready": ready, "harvestMethod": method}
    if extra:
        c.update(extra)
    w.crops[T] = c
    w.farm = w.farm_scan()
    return w


def plot(*tiles):
    tiles = list(tiles) or [T]
    return {"zone": "", "label": "", "anchor": list(tiles[0]),
            "tiles": [list(t) for t in tiles], "note": "task-171 探针"}


def mk_run(w, client=None, worker=None):
    client = client or TL.FakeClient(w)
    worker = worker or FarmWorker(client, log=lambda *_: None)
    run = TL.make_run(w, target_days=1, max_days=1,
                      client_factory=lambda: client, worker_factory=lambda c: worker)
    run.worker = worker
    run.client = client
    return run


def rep():
    return DayReport(day_key=("spring", 1, 6), started_at=0.0)


def events(run, name):
    return [e for e in run.entries if e.get("event") == name]


def ripe_reasons(run, obs):
    return [r for r in run.work_reasons(obs) if "熟" in r]


def attempts(run, w, times):
    """把 harvest 阶段真跑 `times` 轮（用真 FarmWorker + 桥回执）。"""
    r = rep()
    for _ in range(times):
        run._step_stage("harvest", w.obs(), plot(T), r)
    return r


# ============================================================ ① 回执洗白
class _NoActionClient(TL.FakeClient):
    def interact(self, tile, *, timeout_ms=None):
        return {"ok": False, "status": "no_action", "acted": False,
                "reason": "这一格现在收不了（checkAction=false）"}


class _OkButNotActed(TL.FakeClient):
    def interact(self, tile, *, timeout_ms=None):
        return {"ok": True, "status": "no_action", "acted": False, "reason": "没动手但报 ok"}


class _ActedButNotOk(TL.FakeClient):
    """真摘到了（世界变了）但回执 ok=false —— 测"回执优先于观测"的代价。"""

    def interact(self, tile, *, timeout_ms=None):
        self.w.crops.pop(tuple(tile), None)
        return {"ok": False, "status": "ok", "acted": True, "reason": "摘到了但 ok=false"}


class _NoneReceipt(TL.FakeClient):
    def interact(self, tile, *, timeout_ms=None):
        return None


class _NoneReceiptButWorks(TL.FakeClient):
    def interact(self, tile, *, timeout_ms=None):
        self.w.crops.pop(tuple(tile), None)
        return None


print("== ① 回执洗白 ==")
w = mk()
st = FarmWorker(_NoActionClient(w), log=lambda *_: None).harvest(T)
check("1a acted=false/ok=false ⇒ failed", st.code == "failed" and T in w.crops,
      f"code={st.code} reason={st.reason[:60]}")
w = mk()
st = FarmWorker(_OkButNotActed(w), log=lambda *_: None).harvest(T)
check("1b ok=true 但 acted=false ⇒ 仍 failed", st.code == "failed" and T in w.crops, f"code={st.code}")
w = mk()
wk = FarmWorker(_ActedButNotOk(w), log=lambda *_: None)
st = wk.harvest(T)
check("1c【INFO】ok=false 且世界已变 ⇒ 记 failed（回执优先于观测，误报失败）",
      st.code == "failed" and T not in w.crops and wk.harvested == {},
      f"code={st.code} loot={wk.harvested}")
w = mk()
st = FarmWorker(_NoneReceipt(w), log=lambda *_: None).harvest(T)
check("1d 回执不是 dict ⇒ 观测差分仍然判 failed", st.code == "failed" and T in w.crops, f"code={st.code}")
w = mk()
wk = FarmWorker(_NoneReceiptButWorks(w), log=lambda *_: None)
st = wk.harvest(T)
check("1e 回执不是 dict 但作物真没了 ⇒ ok（观测兜底）", st.ok and T not in w.crops, f"code={st.code}")

# ============================================================ ② 判据偷换
print("== ② 判据偷换（ready vs 裸 ripe）==")
w = mk(ripe=True, ready=False)
run = mk_run(w)
check("2a 裸 ripe=true/ready=false ⇒ 不是目标、无守卫理由、harvest skipped",
      run._stage_tiles("harvest", w.obs(), plot()) == [] and not ripe_reasons(run, w.obs())
      and run.worker.harvest(T).code == "skipped")
w = mk(ripe=False, ready=True)
run = mk_run(w)
check("2b ripe=false/ready=true ⇒ 是目标（旧口径会漏掉）",
      run._stage_tiles("harvest", w.obs(), plot()) == [T], "ready 才是权威")
w = mk()
w.farm = {"loaded": True, "complete": True, "dryCrops": 0, "readyCrops": 0, "ripeCrops": 5,
          "crops": 5, "hoeDirt": 1, "emptyDirt": 0}
run = mk_run(w)
check("2c farm: readyCrops=0/ripeCrops=5 ⇒ 农场级熟作物=0（不吃旧字段）",
      run._farm_scope_work(w.obs()) == (0, 0), str(run._farm_scope_work(w.obs())))
w = mk()
w.farm = {"loaded": True, "complete": True, "dryCrops": 0, "readyCrops": 5, "ripeCrops": 0,
          "crops": 5, "hoeDirt": 1, "emptyDirt": 0}
run = mk_run(w)
check("2d farm: readyCrops=5/ripeCrops=0 ⇒ 农场级熟作物=5",
      run._farm_scope_work(w.obs()) == (0, 5), str(run._farm_scope_work(w.obs())))
w = mk()
w.farm = {"loaded": True, "complete": True, "dryCrops": 0, "ripeCrops": 3, "crops": 3,
          "hoeDirt": 1, "emptyDirt": 0}
run = mk_run(w)
check("2e【口径】旧 Mod 缺 readyCrops ⇒ 退回 ripeCrops=3（作者用例⑩，兼容性代价）",
      run._farm_scope_work(w.obs()) == (0, 3))

# ============================================================ ③ 缺字段 fail-closed
print("== ③ 缺字段 fail-closed ==")
w = mk()
w.drop_ready_fields = True
run = mk_run(w)
st = run.worker.harvest(T)
check("3a 缺 ready ⇒ 无目标 + skipped + reason 提到 ready",
      run._stage_tiles("harvest", w.obs(), plot()) == [] and st.code == "skipped"
      and "ready" in st.reason and w.interacted == [], f"reason={st.reason[:70]}")
w = mk(ready=None)
run = mk_run(w)
check("3b ready=null（Mod 判不了）⇒ 不摘", run._stage_tiles("harvest", w.obs(), plot()) == []
      and run.worker.harvest(T).code == "skipped")
check("3c tile_ready/harvest_tool 纯函数语义",
      tile_ready({"ready": True}) and not tile_ready({"ready": None}) and not tile_ready({})
      and not tile_ready(None) and harvest_tool({"harvestMethod": "Scythe"}) == "scythe"
      and harvest_tool({"harvestMethod": "Grab"}) is None and harvest_tool({}) is None)

# ============================================================ ④ 同格上限 + 不许当豁免
print("== ④ 同格上限 ==")
w = mk()
w.harvest_on_interact = False          # 回执 ok 但世界不动（run A/B 的形态）
run = mk_run(w)
attempts(run, w, MAX_TILE_ATTEMPTS)
j = events(run, "harvest_gave_up")
check("4a 试满 2 次 ⇒ 进 harvest_gave_up + 恰 1 条 journal",
      T in run.harvest_gave_up and len(j) == 1 and j[0]["limit"] == MAX_TILE_ATTEMPTS,
      f"gave_up={sorted(run.harvest_gave_up)} attempts={run.tile_attempts.get(T)}")
check("4b 之后不再是目标、不在 _pending_work、无守卫理由",
      run._stage_tiles("harvest", w.obs(), plot()) == [] and T not in run._pending_work()
      and not ripe_reasons(run, w.obs()))
lx = run._leftover("harvest", w.obs(), plot())
check("4c【核心】_leftover 仍如实算它（不洗成豁免）", lx == [T], f"leftover={lx}")
allowed, code, why = run.sleep_guard(w.obs())
check("4d 守卫解钉：允许收工且理由 no_work", allowed and code == "no_work", f"code={code} why={why[:50]}")
check("4e 该格不在任何豁免集合里（blocked/deferred 都空）",
      T not in run.blocked and T not in run._budget_deferred_tile_set())

# 4f【我自造】放弃后玩家走开（格子离开观测窗口）⇒ 诚实性是否还在？
print("== ④f【自造】放弃后离开窗口 ==")
w = mk(world_cls=TL.MyopicWorld, player=(60, 12))
w.harvest_on_interact = False
run = mk_run(w)
attempts(run, w, MAX_TILE_ATTEMPTS)
in_window = run._leftover("harvest", w.obs(), plot()) == [T]
w.player_tile = [70, 20]              # 人走开：窗口里没有这一格了
w.revealed = False                   # FakeClient.move_to 会把 revealed 置真，这里显式关掉
obs = w.obs()
window_has_tile = any(tuple(t.get("tile") or ()) == T for t in (obs.get("location") or {}).get("tiles") or [])
lx2 = run._leftover("harvest", obs, plot())
reasons2 = ripe_reasons(run, obs)
allowed2, code2, _ = run.sleep_guard(obs)
farm_ready = w.farm_scan()["readyCrops"]
wash = (not window_has_tile and farm_ready == 1 and lx2 == [] and not reasons2
        and allowed2 and code2 == "no_work")
check("4f【自造】放弃格离开窗口 ⇒ farm 还有 1 格可收却可 no_work 收工（诚实性只在窗口内）",
      wash, f"window_has_tile={window_has_tile} in_window_leftover={in_window} now_leftover={lx2} "
            f"reasons={reasons2} guard={code2} farm_readyCrops={farm_ready} "
            f"gave_up={sorted(run.harvest_gave_up)}")

# ============================================================ ⑤ 守卫解钉 vs 假阴
print("== ⑤ 守卫：不许被钉 / 不许变假阴 ==")
w = mk()
w.harvest_on_interact = False
run = mk_run(w)
attempts(run, w, MAX_TILE_ATTEMPTS)
# 5a【INFO】: _unfinished_work 用的是未扣 harvest_gave_up 的 farm 级计数 ⇒ 仍为 True。
# 与 work_reasons（已扣）口径不一致；但 gave_up 需要同格 >=2 次非 skipped 失败，而这些失败步
# 都会计入 farm_actions_today ⇒ _do_sleep 的 require_work 分支实际恒过 ⇒ 属潜在/防御性不一致。
check("5a【INFO】_unfinished_work 仍被 farm 级熟作物钉住（未扣 harvest_gave_up；require_work 实际恒过）",
      run._unfinished_work(w.obs()) is True,
      f"unfinished={run._unfinished_work(w.obs())} reasons={ripe_reasons(run, w.obs())} "
      f"farm_actions_today={run.farm_actions_today}")
w2 = mk()
run2 = mk_run(w2)
check("5b 真可收且没试过 ⇒ 守卫仍拒绝收工（没修成假阴）",
      bool(ripe_reasons(run2, w2.obs())) and run2.sleep_guard(w2.obs())[0] is False,
      f"reasons={ripe_reasons(run2, w2.obs())}")
w3 = mk()
w3.crops[(61, 10)] = {"watered": True, "ripe": True, "ready": True, "harvestMethod": "Grab"}
w3.dirt.add((61, 10))
w3.farm = w3.farm_scan()
run3 = mk_run(w3)
# 只放弃 T，另一格 (61,10) 仍可收 ⇒ farm 级计数扣 1 后还剩 1 ⇒ 必须仍然抱怨
attempts(run3, w3, MAX_TILE_ATTEMPTS)
check("5c 只放弃 1 格、另 1 格真可收 ⇒ 守卫照样抱怨（按数量扣不许抹平别的格）",
      bool(ripe_reasons(run3, w3.obs())), f"reasons={ripe_reasons(run3, w3.obs())}")

# ============================================================ ⑥ 镰刀类
print("== ⑥ 镰刀类（工具路径）==")
w = mk(method="Scythe")
wk = FarmWorker(TL.FakeClient(w), log=lambda *_: None)
st = wk.harvest(T)
check("6a method=Scythe ⇒ 走 use_tool，不 interact，作物消失",
      st.ok and w.interacted == [] and w.swings.get(T) == 1 and T not in w.crops,
      f"code={st.code} swings={w.swings} interacted={w.interacted}")
w = mk(method="Scythe", ready=False, ripe=True)
wk = FarmWorker(TL.FakeClient(w), log=lambda *_: None)
st = wk.harvest(T)
check("6b 镰刀类但 ready=false ⇒ 一刀都不挥（不许新造挥空）",
      st.code == "skipped" and not w.swings and T in w.crops, f"code={st.code}")


class _ScytheRefused(TL.FakeClient):
    def use_tool(self, tile, *, tool=None, timeout_ms=None):
        return {"ok": False, "status": "no_action", "acted": False, "reason": "镰刀被拒"}


w = mk(method="Scythe")
st = FarmWorker(_ScytheRefused(w), log=lambda *_: None).harvest(T)
check("6c 镰刀路径回执 acted=false ⇒ failed", st.code == "failed" and T in w.crops, f"code={st.code}")

print(f"\n== 汇总（{os.path.basename(ROOT)}）== PASS={len(PASS)} FAIL={len(FAIL)}")
for t in FAIL:
    print("  FAIL: " + t)
sys.exit(1 if FAIL else 0)
