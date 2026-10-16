# -*- coding: utf-8 -*-
r"""task-178 独立对抗验收探针（只写 scratch/）。

对象：`037e599`（0.7.34 task-176：harvestMethod 来源 / readySource / acted 诚实化）。
覆盖卡面六条作弊通道 + 我自己的补充；源码契约部分**独立解析**（不复用作者断言）。

用法：
    $env:T178_ROOT = "<树根>"      # 可选，默认仓库根
    & $py -W error::SyntaxWarning scratch\_t178_probe.py
"""
import os
import sys

ROOT = os.environ.get("T178_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "tests"), os.path.join(ROOT, "brain"), os.path.join(ROOT, "scratch")):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_longrun as TL  # noqa: E402
from agentfarm.farmwork import FarmWorker, harvest_tool, tile_ready  # noqa: E402

MOD = os.path.join(ROOT, "mod", "AgentFarm.Bridge")
CROP = (60, 10)
FAILS = []
PASSES = []


def check(tag, ok, detail=""):
    (PASSES if ok else FAILS).append(tag)
    print(("  ok   " if ok else "  FAIL ") + tag + ("  :: " + str(detail) if detail else ""))


def src(name):
    with open(os.path.join(MOD, name), encoding="utf-8") as fh:
        return fh.read()


def block_after(text, marker, size=400):
    parts = text.split(marker)
    return parts[1][:size] if len(parts) > 1 else ""


def plot(*tiles):
    tiles = list(tiles) or [CROP]
    return {"zone": "", "label": "", "anchor": list(tiles[0]),
            "tiles": [list(t) for t in tiles], "note": "task-178 probe"}


def world(*, ready=True, method="Grab", ready_source="game", drop_ready=False,
          drop_method=False, **kw):
    w = TL.FakeWorld(weeds=0, seeds=0, money=0, water_left=40, **kw)
    w.player_tile = [62, 14]
    w.dirt.add(CROP)
    c = {"watered": True, "ripe": True, "ready": ready, "harvestMethod": method,
         "readySource": ready_source}
    w.crops[CROP] = c
    w.drop_ready_fields = drop_ready
    w.drop_harvest_method = drop_method
    w.farm = w.farm_scan()
    return w


class Client(TL.FakeClient):
    """TL.FakeClient 没有 buy/sell（真 FarmWorker 走 ship 路径时会调 sell）。"""

    def __init__(self, w):
        super().__init__(w)
        self.sold = []

    def sell(self, slot, *, whitelist=None, timeout_ms=None):
        self.sold.append((slot, tuple(whitelist or ())))
        return {"ok": True, "status": "ok", "slot": slot, "qid": "probe",
                "stack": 0, "reason": "probe sell"}


def mk_run(w):
    client = Client(w)
    worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
    run = TL.make_run(w, target_days=1, max_days=1,
                      client_factory=lambda: client, worker_factory=lambda c: worker)
    run.worker = worker
    run.client = client
    return run, client, worker


def tile_view(w):
    return next(t for t in w.obs()["location"]["tiles"] if tuple(t["tile"]) == CROP)


print("== ① 源码契约：harvestMethod 来源 / 无条件出键 ==")
cm = src("CropMeta.cs")
ct = src("Contracts.cs")
sk = src("Skills.cs")
ws = src("WorldSnapshot.cs")
check("1a CropMeta 调 public 方法 crop.GetHarvestMethod()（不再按字段名读）",
      "crop.GetHarvestMethod()" in cm and 'ReadMember(crop, "HarvestMethod")' not in cm)
check("1b harvestMethod 标了 JsonIgnoreCondition.Never（无条件出键）",
      "JsonIgnoreCondition.Never" in block_after(ct, 'JsonPropertyName("harvestMethod")'),
      block_after(ct, 'JsonPropertyName("harvestMethod")', 120).replace("\n", " ")[:100])
check("1c readySource 标了 Never 且从 Ready() 的 Source 落进快照",
      "JsonIgnoreCondition.Never" in block_after(ct, 'JsonPropertyName("readySource")')
      and "t.ReadySource = readyInfo.Source" in ws)
check("1d 未知枚举值照实写数字（不吃默认 Grab）",
      "((int)crop.GetHarvestMethod()).ToString()" in cm)

print("== ② 源码契约：readySource 与等价兜底 ==")
check("2a 反射成功 ⇒ (direct, \"game\")", 'return (direct, "game")' in cm)
check("2b 字段齐全 ⇒ 仍给结论（(true/false, \"fields\")，不是 null）",
      '(true, "fields")' in cm and '(false, "fields")' in cm)
check("2c 判据缺项 ⇒ (null, null)，且 gate 里点名了 forage",
      "(null, null)" in cm and "forage == null" in cm)

print("== ③ 源码契约：acted 只认本调用内可观测的变化 ==")
check("3a 有 TileSig 前后对比 + observedChange 判据",
      "TileSig(tx, ty)" in sk and "observedChange" in sk)
check("3b acted = err == null && observedChange（不是 checkAction 返回值）",
      "bool acted = err == null && observedChange;" in sk
      and "Ok = err == null && handled" not in sk)
check("3c Status 三态 ok/no_action/error、Acted 字段机器可读",
      '(acted ? "ok" : "no_action")' in sk and "Acted = acted" in sk)

print("== ④ 脑侧：伪造 readySource 骗不过 ==")
w = world(ready=None, ready_source="game")
run, client, worker = mk_run(w)
tv = tile_view(w)
check("4a ready=null + readySource=\"game\" ⇒ 不是目标、不摘、零 interact",
      tile_ready(tv) is False
      and run._stage_tiles("harvest", w.obs(), plot()) == []
      and worker.harvest(CROP).code == "skipped" and w.interacted == [],
      f"tile_ready={tile_ready(tv)} code={worker.harvest(CROP).code}")
w = world(ready=False, ready_source="fields")
run, client, worker = mk_run(w)
check("4b ready=false + readySource=\"fields\" ⇒ 不是目标（来源标签不能翻案）",
      run._stage_tiles("harvest", w.obs(), plot()) == [] and w.interacted == [])

print("== ⑤ 脑侧：harvestMethod 缺键 / null / Scythe ==")
w = world(method="Scythe")
run, client, worker = mk_run(w)
check("5a method=Scythe ⇒ harvest_tool 给 scythe、是目标", harvest_tool(tile_view(w)) == "scythe"
      and run._stage_tiles("harvest", w.obs(), plot()) == [CROP])
st = worker.harvest(CROP)
check("5b Scythe 走 use_tool：interacted 空、真的挥镰、作物消失",
      st.ok and w.interacted == [] and w.swings.get(CROP) and CROP not in w.crops,
      f"ok={st.ok} interacted={w.interacted} swings={w.swings}")
w = world(method="Scythe", drop_method=True)
run, client, worker = mk_run(w)
tv = tile_view(w)
check("5c 0.7.33 形态（harvestMethod 整键缺失）⇒ 判不了工法，不默认 Grab，仍可试 interact",
      "harvestMethod" not in tv and harvest_tool(tv) is None and tile_ready(tv) is True)
st = worker.harvest(CROP)
check("5d 缺键形态的 harvest 如实失败且作物还在（284×0 的形态被复现并被判失败）",
      st.ok is False and w.interacted == [CROP] and CROP in w.crops,
      f"ok={st.ok} code={st.code} 作物还在={CROP in w.crops}")
w = world(method=None)
tv = tile_view(w)
check("5e 显式 null（0.7.34 的\"拿不到写 null\"）⇒ harvest_tool None，不默认 Scythe/Grab",
      "harvestMethod" in tv and tv["harvestMethod"] is None and harvest_tool(tv) is None)

print("== ⑥ 脑侧：回执谎报 acted=true 但世界没变 ==")
w = world(method="Grab")
run, client, worker = mk_run(w)
run.client.interact = lambda tile=None, timeout_ms=None: {
    "ok": True, "status": "ok", "acted": True, "reason": "谎报：checkAction 返回 true"}
st = worker.harvest(CROP)
check("6a acted=true 但格子没变 ⇒ 仍 failed（观测差分兜住）",
      st.ok is False and CROP in w.crops, f"ok={st.ok} code={st.code} reason={st.reason[:60]}")
w = world(method="Grab")
run, client, worker = mk_run(w)
run.client.interact = lambda tile=None, timeout_ms=None: {"ok": True, "status": "ok",
                                                          "reason": "无 acted 键"}
st = worker.harvest(CROP)
check("6b 回执缺 acted 键且世界没变 ⇒ failed（缺键不许当成功）",
      st.ok is False and CROP in w.crops, f"ok={st.ok}")
w = world(method="Grab")
run, client, worker = mk_run(w)
st = worker.harvest(CROP)
check("6c 正对照：Grab 真摘到 ⇒ ok + 作物消失", st.ok and CROP not in w.crops, f"ok={st.ok}")

print("== ⑦ 脑侧：等价兜底不许 fail-closed 过头（fields 仍是合法目标）==")
w = world(ready=True, ready_source="fields")
run, client, worker = mk_run(w)
check("7a readySource=\"fields\" + ready=true ⇒ 是目标且能摘到",
      run._stage_tiles("harvest", w.obs(), plot()) == [CROP]
      and worker.harvest(CROP).ok and CROP not in w.crops)
w = world(ready=True, ready_source="fields", drop_ready=True)
run, client, worker = mk_run(w)
tv = tile_view(w)
check("7b ready/readySource 键缺失 ⇒ 不摘（缺失 ≠ 通过）",
      tile_ready(tv) is False and worker.harvest(CROP).code == "skipped")

print("== ⑧ 脑侧：整天（Scythe 作物）==")
w = world(method="Scythe")
run, client, worker = mk_run(w)
code = run.run()
end = run.days[-1]
check("8a 整天跑完：Scythe 作物被真挥镰摘走、零 interact（日级 verdict 作 info 记录）",
      CROP not in w.crops and w.interacted == [] and bool(w.swings.get(CROP)),
      f"code={code} verified={end.verified} ended_by={end.ended_by} "
      f"checks={getattr(end, 'checks', None)}")

print("\n== 汇总（%s）== PASS=%d FAIL=%d" % (os.path.basename(ROOT), len(PASSES), len(FAILS)))
for f in FAILS:
    print("  FAIL: " + f)
sys.exit(1 if FAILS else 0)
