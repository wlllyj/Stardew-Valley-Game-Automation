"""task-159 对抗验收探针：task-157（water_far 够不着先有界开路）+ task-158（浇水优先体力预算）。

用法（`T159_ROOT` 切树，旧树 = `ef59f30^`=`54f8d07`，新树 = HEAD）：
  $env:T159_ROOT = "<repo>\\scratch\\_t159_pre"
  $env:T159_ROOT = "<repo>"
  python scratch\\_t159_probe.py

设计要点：
* B1 = task-157 的 run9d summer 25 形态（`[12,30]` 够不着）：新树必须出现**有界开路**证据
  （`water_far_open`）+ 仍走不到时 `water_far_blocked`，且当天**仍然**不 VERIFIED；
  另给"开路后站得到 ⇒ 真浇上"的可救形态与"开路成功≠浇水"的撒谎形态。
* B2 = task-158 的超载日（run9d summer 27/28、fall 1 的 `stamina 0` 形态）：新树必须在
  reserve 耗尽前停手（`deferred_by_budget`）、未浇完的格数如实留在 `assigned_undone`、
  `checks` 键集不许新增可洗白项。
* B3 = 正对照（预算充足、无干作物）⇒ 新旧树产物逐字相同。
* C 段 = 伪造 dryCrops / reserve 说谎或缺失 / 开路当浇水 / blocked 日自称 VERIFIED /
  有界性 / 与 task-102/149 不打架 / `checks` 键集。
"""
import copy
import json
import os
import subprocess
import sys

ROOT = os.environ.get("T159_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (ROOT, os.path.join(ROOT, "brain"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import test_longrun as TL  # noqa: E402
from agentfarm import longrun as LR  # noqa: E402

FakeWorld = TL.FakeWorld
FakeWorker = TL.FakeWorker
FakeClient = TL.FakeClient
make_run = TL.make_run
StepResult = TL.StepResult

FAR = (61, 10)          # MyopicWorld 半径 3、玩家 [62,14] ⇒ 窗口外（与作者用例同款）
JOURNAL_DIR = os.path.join(HERE, "_t159_j")
OPEN_MAX = int(getattr(LR, "FAR_DRY_OPEN_MAX", 0) or 0)
TRY_MAX = int(getattr(LR, "FAR_DRY_MAX_TRIES", 0) or 0)
HAS_157 = hasattr(LR, "FAR_DRY_OPEN_MAX")
HAS_158 = hasattr(LR.LongRun, "_stamina_budget")

RESULTS = []
DIAG = os.environ.get("T159_DIAG") == "1"


def check(tag, ok, detail=""):
    RESULTS.append((tag, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {tag}" + (f" :: {detail}" if detail else ""))
    return bool(ok)


def events(run, name):
    return [e for e in run.entries if e.get("event") == name]


def jpath(name):
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    p = os.path.join(JOURNAL_DIR, f"{name}.jsonl")
    if os.path.exists(p):
        os.remove(p)
    return p


def canon(day, run):
    return {
        "verified": bool(day.verified),
        "ended_by": str(day.ended_by),
        "reason_head": str(day.ended_reason).split(":", 1)[0],
        "checks": {k: day.checks[k] for k in sorted(day.checks)},
        "stages": sorted(str(s.get("stage")) for s in day.stages),
        "ok_steps": int(day.ok_steps),
    }


# --------------------------------------------------------------------------- 夹具
class OpenWayWorker(FakeWorker):
    """task-157 夹具（本探针自建，不复用作者夹具）：

    `stand_next_to(FAR)` 第一次站不到；`open_way` 按 `open_code` 返回 `ok`/`exhausted`；
    `lie=True` ⇒ 开路成功但 `water()` 只回 ok 回执、世界一动不动。
    """

    def __init__(self, world, *, tile=FAR, open_code="exhausted", cleared=1, lie=False):
        super().__init__(world)
        self.tile = tuple(tile)
        self.open_code = str(open_code)
        self.cleared_n = int(cleared)
        self.lie = bool(lie)
        self.open_calls = []
        self._reachable = False

    def stand_next_to(self, tile, *, timeout_ms=15000):
        if tuple(tile) == self.tile:
            return self._reachable
        return super().stand_next_to(tile, timeout_ms=timeout_ms)

    def open_way(self, tile, *, timeout_ms=None):
        self.open_calls.append(tuple(tile))
        cleared = [{"neighbour": [self.tile[0], self.tile[1] + 1], "kind": "weed",
                    "result": "cleared"} for _ in range(self.cleared_n)]
        self._reachable = self.open_code == "ok"
        return self.open_code, cleared, ["假世界：为 [12,30] 开路"]

    def water(self, tile, *, timeout_ms=15000):
        if self.lie:
            st = StepResult("water", tuple(tile), ok=True, reason="假回执：浇过了（其实没有）")
            self.steps.append(st)
            return st
        return super().water(tile, timeout_ms=timeout_ms)


def far_world(*, with_dry_tiles=True, water_left=40):
    w = TL.DryTilesWorld(seeds=0, money=0, weeds=0, water_left=water_left,
                         with_dry_tiles=with_dry_tiles)
    w.dirt.add(FAR)
    w.crops[FAR] = {"watered": False, "ripe": False}
    w.player_tile = [62, 14]
    return w


def run_far(w, worker, *, name, max_days=1):
    return make_run(w, target_days=1, max_days=max_days,
                    client_factory=lambda: FakeClient(w),
                    worker_factory=lambda _c: worker, journal_path=jpath(name))


def mk_run_day(w, name, *, worker=None):
    """`make_run` 只在 `run()` 里造 worker/client ⇒ 直调 `_run_day()` 的用例必须自己装。"""
    client = FakeClient(w)
    worker = worker or FakeWorker(w, log=lambda *_: None)
    run = make_run(w, target_days=1, max_days=1,
                   client_factory=lambda: client,
                   worker_factory=lambda _c: worker, journal_path=jpath(name))
    run.worker, run.client = worker, client
    # 直调 `_run_day()` 不经过 `run()` ⇒ `started` 仍是 0，日分钟预算按 epoch 秒算
    # （实测 ended_by=budget「到预算上限（29869671.7 分钟 / 0 个动作）」）⇒ 自己对齐时间起点。
    run.started = run.now()
    return run


def overload_world(*, stamina=60.0):
    """run9d summer 27/28/fall 1 形态：窗口内 5 格干苗 + 农场口径 dry=17、12 丛杂草、20 格空地。

    用 `MyopicWorld` 让**窗口**只看得见玩家附近（真机 `OBSERVE_REACH` 半径），farm 块给全农场计数。
    """
    w = TL.MyopicWorld(weeds=12, seeds=20, money=0, stamina=stamina, water_left=40)
    w.max_stamina = 270.0
    w.dirt = {(60 + i, 10) for i in range(25)}          # 5 格种了 + 20 格空地
    w.crops = {(60 + i, 10): {"watered": False, "ripe": False} for i in range(5)}
    w.player_tile = [60, 10]
    w.farm = {
        "loaded": True, "complete": True, "crops": 146, "dryCrops": 17,
        "ripeCrops": 0, "deadCrops": 0, "dryDeadCrops": 0,
        "hoeDirt": 220, "emptyDirt": 74,
        "dryTiles": [[60 + i, 10] for i in range(5)], "dryTilesTruncated": False,
    }
    return w


# --------------------------------------------------------------------------- B 段
def case_b1():
    """B1：够不着 ⇒ 有界开路 + blocked + 当天不许 VERIFIED（pre 应 FAIL）。"""
    w = far_world()
    worker = OpenWayWorker(w, open_code="exhausted", cleared=1)
    run = run_far(w, worker, name="b1_blocked")
    code = run.run()
    opens = events(run, "water_far_open")
    blocked = events(run, "water_far_blocked")
    wf = events(run, "water_far")
    day = run.days[0] if run.days else None
    detail = (f"code={code} opens={len(opens)} blocked={len(blocked)} "
              f"wf_ok={[bool(e.get('ok')) for e in wf]} "
              f"watered_outdoor={day.checks.get('watered_outdoor') if day else None} "
              f"verified={day.verified if day else None} reason={str(day.ended_reason)[:48]!r}")
    check("B1a 有界开路留痕（water_far_open ≥1 且 ≤ 上限）",
          bool(opens) and len(opens) <= max(1, OPEN_MAX), detail)
    check("B1b 仍走不到 ⇒ water_far_blocked 且 cleared_tiles 如实",
          bool(blocked) and int(blocked[0].get("cleared_count") or 0) >= 1,
          f"blocked={blocked[:1]}")
    check("B1c 开路不算浇水（watered_outdoor=False）",
          day is not None and day.checks.get("watered_outdoor") is False, detail)
    check("B1d 当天不 VERIFIED", day is not None and day.verified is False, detail)
    check("B1e 收尾如实 gave_up_dry", day is not None and "gave_up_dry" in str(day.ended_reason),
          str(day.ended_reason)[:70] if day else "")
    check("B1f 该格从未被浇", w.watered_tiles == [], f"watered_tiles={w.watered_tiles}")
    return run, w


def case_b1b():
    """B1b：开路后站得到 ⇒ 那一格真浇上、当天可 VERIFIED。"""
    w = far_world()
    worker = OpenWayWorker(w, open_code="ok", cleared=1)
    run = run_far(w, worker, name="b1b_recovered")
    code = run.run()
    day = run.days[0] if run.days else None
    wf = events(run, "water_far")
    detail = (f"code={code} opens={len(events(run, 'water_far_open'))} "
              f"watered_tiles={w.watered_tiles} wf={[bool(e.get('ok')) for e in wf]} "
              f"watered_outdoor={day.checks.get('watered_outdoor') if day else None}")
    check("B1g 开路后可救形态真的浇上", w.watered_tiles == [FAR], detail)
    check("B1h 可救形态当天可 VERIFIED（checks.watered_outdoor=True）",
          day is not None and day.checks.get("watered_outdoor") is True, detail)
    check("B1i 可救形态不许有 blocked", events(run, "water_far_blocked") == [], detail)


def case_b1c():
    """B1c：开路成功但世界没变（撒谎回执）⇒ 逐格判据必须判失败。"""
    w = far_world()
    worker = OpenWayWorker(w, open_code="ok", cleared=1, lie=True)
    run = run_far(w, worker, name="b1c_lie")
    run.run()
    day = run.days[0] if run.days else None
    wf = events(run, "water_far")
    detail = (f"opens={len(events(run, 'water_far_open'))} "
              f"wf_ok={[bool(e.get('ok')) for e in wf]} "
              f"cause={[e.get('cause') for e in wf]} watered_tiles={w.watered_tiles}")
    check("B1j 开路成功≠浇水（回执撒谎 ⇒ ok=False）",
          bool(wf) and all(not e.get("ok") for e in wf), detail)
    check("B1k 撒谎形态当天不 VERIFIED",
          day is not None and day.verified is False, detail)


def case_b2():
    """B2：run9d summer 27/28/fall 1 形态（超大农场 + 干苗 + 杂草）⇒ 必须在 reserve 耗尽前停手。"""
    w = overload_world()
    run = mk_run_day(w, "b2_overload")
    rep = run._run_day()
    defer = events(run, "deferred_by_budget")
    tasks = sorted({str(e.get("task")) for e in defer})
    stages_ok = {}
    for s in rep.stages:
        stages_ok[str(s.get("stage"))] = int(s.get("ok") or 0)
    b = dict(getattr(rep, "stamina_budget", {}) or {})
    detail = (f"ended_by={rep.ended_by} reason={str(rep.ended_reason)[:40]!r} "
              f"stamina={w.stamina:g} defer={tasks} capacity={b.get('capacity')} "
              f"reserve={b.get('water_reserve')} dry={b.get('dry')} stages_ok={stages_ok} "
              f"crops_watered={rep.checks.get('crops_watered')} "
              f"watered_outdoor={rep.checks.get('watered_outdoor')} assigned_undone={rep.assigned_undone}")
    if HAS_158:
        check("B2a 预算闸门留痕（deferred_by_budget 只点名 clear/till/plant）",
              bool(defer) and set(tasks) <= {"clear_area", "till_area", "plant_area"}, detail)
        planted = len([t for t in w.dirt if t not in w.crops])
        check("B2b 有干苗 + reserve>体力 ⇒ capacity=0、当天零播种（空地保持空）",
              int(b.get("capacity") or 0) == 0 and stages_ok.get("plant_area", 0) == 0
              and planted == 20, f"{detail} planted={planted}")
        check("B2c 体力在 reserve 线之上停手（不是挥到 0）",
              w.stamina > 0 and float(b.get("water_reserve") or 0) >= 0, detail)
        check("B2d 没浇完就如实不达标（crops_watered/watered_outdoor 不为真）",
              rep.checks.get("watered_outdoor") is not True or rep.verified is False, detail)
        check("B2e day_end 带 stamina_budget 快照且 checks 无新可洗白键",
              bool(b) and not ({"stamina_budget", "deferred_by_budget", "budget"} & set(rep.checks)),
              detail)
    else:
        planted = len([t for t in w.dirt if t not in w.crops])
        check("B2a 旧树没有预算闸门（不得出现 stamina_budget/deferred_by_budget，也不受 reserve 约束）",
              not (getattr(rep, "stamina_budget", None) or defer), f"{detail} planted={planted}")
    # B2f：体力在浇水途中耗尽（run9d summer 27 形态）⇒ 未浇完必须如实留在 assigned_undone
    w2 = FakeWorld(weeds=0, seeds=0, money=0, stamina=20.0)
    w2.dirt = {(60 + i, 12) for i in range(25)}
    w2.crops = {(60 + i, 12): {"watered": False, "ripe": False} for i in range(25)}
    w2.player_tile = [60, 12]
    w2.farm = {"loaded": True, "complete": True, "crops": 25, "dryCrops": 25, "ripeCrops": 0,
               "deadCrops": 0, "dryDeadCrops": 0, "hoeDirt": 25, "emptyDirt": 0,
               "unwateredCrops": 25, "dryTiles": [[60 + i, 12] for i in range(25)],
               "dryTilesTruncated": False}
    run2 = mk_run_day(w2, "b2_starved")
    rep2 = run2._run_day()
    ws = [s for s in rep2.stages if str(s.get("stage")) == "water_area"]
    au = max([int(s.get("assigned_undone") or 0) for s in ws] or [0])
    check("B2f 体力中途耗尽 ⇒ 未浇完如实留在 assigned_undone、crops_watered 不为真、当天不 VERIFIED",
          au > 0 and rep2.checks.get("crops_watered") is not True and rep2.verified is False,
          f"assigned_undone={au} crops_watered={rep2.checks.get('crops_watered')} "
          f"watered_outdoor={rep2.checks.get('watered_outdoor')} verified={rep2.verified} "
          f"ended_by={rep2.ended_by} stamina={w2.stamina:g}")
    return run, w


def case_b3():
    """B3 正对照：预算充足、无干作物 ⇒ 新旧树产物逐字相同。"""
    def one():
        w = FakeWorld(weeds=4, seeds=10, money=500, stamina=270.0)
        w.farm = w.farm_scan()
        run = make_run(w, target_days=1, max_days=1,
                       client_factory=lambda: FakeClient(w),
                       worker_factory=lambda c: FakeWorker(w, log=lambda *_: None),
                       journal_path=jpath("b3_control"))
        code = run.run()
        day = run.days[0] if run.days else None
        c = canon(day, run) if day else {"none": True}
        c["code"] = code
        return c
    c = one()
    # 与 task-158 之前的"旧树"对照由外层 pre/post 两次运行完成；这里落一份规范快照供 diff。
    with open(os.path.join(HERE, f"_t159_b3_{os.environ.get('T159_TAG', 'x')}.json"), "w",
              encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1, sort_keys=True)
    check("B3 正对照跑完并落盘快照", bool(c) and "checks" in c, f"code={c.get('code')} "
          f"verified={c.get('verified')} ok_steps={c.get('ok_steps')}")
    return c


# --------------------------------------------------------------------------- C 段
def case_c1():
    """C1：伪造 farm.dryCrops=0（窗口里却有干苗）⇒ 不许因此白过。"""
    w = overload_world()
    w.farm = dict(w.farm, dryCrops=0, unwateredCrops=0)
    run = mk_run_day(w, "c1_lie_dry")
    rep = run._run_day()
    watered_now = sum(1 for v in w.crops.values() if v.get("watered"))
    detail = (f"verified={rep.verified} watered_outdoor={rep.checks.get('watered_outdoor')} "
              f"farm_dry_claim=0 实际窗口干苗=5 已浇={watered_now} ok={rep.ok_steps}")
    # 谎报 dry=0 只会让"农场口径"看起来干净；判据要求当天不许在**还有干苗**时自称 VERIFIED。
    check("C1 伪造 dryCrops=0 不许让「还有干苗」的一天变绿",
          not (rep.verified and watered_now < 5), detail)


def case_c2():
    """C2：reserve 字段说谎/缺失 ⇒ fail-closed（保守上界，不许放开播种）。"""
    w = overload_world()
    w.farm = {"loaded": True, "complete": False}
    run = make_run(w, target_days=1, max_days=1,
                   client_factory=lambda: FakeClient(w),
                   worker_factory=lambda c: FakeWorker(w, log=lambda *_: None),
                   journal_path=jpath("c2_missing"))
    b = run._stamina_budget(w.obs()) if HAS_158 else {}
    why_till = run._budget_defer_reason("till_area", w.obs()) if HAS_158 else "n/a"
    why_plant = run._budget_defer_reason("plant_area", w.obs()) if HAS_158 else "n/a"
    tiles = run._stage_tiles("plant_area", w.obs(), {"zone": "", "label": "",
                                                     "anchor": [60, 10],
                                                     "tiles": [[60 + i, 10] for i in range(25)],
                                                     "note": ""})
    check("C2a farm 不可用 ⇒ basis=conservative 且 reserve 不小于现有体力",
          HAS_158 and b.get("basis") == "conservative" and b.get("water_reserve") == b.get("stamina"),
          f"basis={b.get('basis')} reserve={b.get('water_reserve')} stamina={b.get('stamina')}")
    check("C2b 保守模式下不许播种（plant_area 目标为空）",
          HAS_158 and tiles == [], f"tiles={len(tiles)} why_plant={why_plant[:40]!r}")
    check("C2c 保守模式下 clear/till 停手留痕", HAS_158 and bool(why_till),
          f"why_till={why_till[:50]!r}")
    # 字段是字符串/负数也不许崩
    w2 = overload_world()
    w2.farm = dict(w2.farm, crops="many", dryCrops=-3)
    try:
        b2 = run._stamina_budget(w2.obs()) if HAS_158 else {}
        ok = True
    except Exception as exc:                      # noqa: BLE001
        b2, ok = {}, False
        detail = f"{type(exc).__name__}: {exc}"
    else:
        detail = f"basis={b2.get('basis')} reserve={b2.get('water_reserve')}"
    check("C2d 畸形字段（字符串/负数）不崩且 fail-closed", ok and HAS_158, detail)


def case_c3():
    """C3：`cleared_tiles>0` 但该格 watered=false ⇒ 不许 ok（与 B1j 不同夹具再打一次）。"""
    w = far_world()
    worker = OpenWayWorker(w, open_code="ok", cleared=2, lie=True)
    run = run_far(w, worker, name="c3_cleared_not_watered")
    run.run()
    wf = events(run, "water_far")
    opens = events(run, "water_far_open")
    check("C3 开路 2 格但没浇上 ⇒ 全部 ok=False",
          bool(wf) and all(not e.get("ok") for e in wf),
          f"opens_cleared={[o.get('cleared_count') for o in opens]} "
          f"wf_ok={[bool(e.get('ok')) for e in wf]} cause={[e.get('cause') for e in wf]}")
    check("C3b 该格不在 dryTiles 里才算成功（本次仍在 ⇒ 失败）",
          all(e.get("cause") != "ok" for e in wf), f"{[e.get('cause') for e in wf]}")


def case_c4():
    """C4：有界性 —— 同格开路 ≤2 轮、water_far 尝试 ≤2 次、全天动作有上界、不许死循环。"""
    w = far_world()
    worker = OpenWayWorker(w, open_code="exhausted", cleared=1)
    run = run_far(w, worker, name="c4_bounded")
    run.run()
    opens = events(run, "water_far_open")
    wf = events(run, "water_far")
    check("C4a 同格开路 ≤ FAR_DRY_OPEN_MAX",
          len(opens) <= max(1, OPEN_MAX) and len(worker.open_calls) <= max(1, OPEN_MAX),
          f"opens={len(opens)} open_calls={len(worker.open_calls)} limit={OPEN_MAX}")
    check("C4b water_far 尝试 ≤ FAR_DRY_MAX_TRIES",
          len(wf) <= max(1, TRY_MAX), f"tries={len(wf)} limit={TRY_MAX}")
    check("C4c 全天总动作有界（≤ 开路上限×清障 + 尝试上限×动作）",
          len(worker.steps) <= 12, f"steps={len(worker.steps)}")


def case_c5():
    """C5：与 task-102/task-149 不打架 + harvest/clear_dead 永不被预算延后。"""
    w = overload_world()
    run = mk_run_day(w, "c5_devote")
    if HAS_158:
        why_h = run._budget_defer_reason("harvest", w.obs())
        why_d = run._budget_defer_reason("clear_dead", w.obs())
        why_w = run._budget_defer_reason("water_area", w.obs())
        check("C5a harvest/clear_dead/water_area 永不被预算延后",
              why_h == "" and why_d == "" and why_w == "",
              f"harvest={why_h[:30]!r} clear_dead={why_d[:30]!r} water={why_w[:30]!r}")
    else:
        check("C5a harvest/clear_dead/water_area 永不被预算延后", False, "旧树无预算闸门")
    # 0 动作 + 有活 ⇒ 不许睡（task-102/149 口径）：体力已低于 reserve、只剩被延后的活
    w2 = overload_world(stamina=5.0)
    run2 = mk_run_day(w2, "c5_zero")
    rep2 = run2._run_day()
    check("C5b 0 农场动作 + 有活 ⇒ 不许以 no_work 收尾",
          rep2.ended_by != "sleep" or "no_work" not in str(rep2.ended_reason),
          f"ended_by={rep2.ended_by} reason={str(rep2.ended_reason)[:50]!r} "
          f"zero_ev={rep2.checks.get('zero_action_evidenced')}")


def case_c6():
    """C6：`checks` 键集不许新增可洗白项（新旧树同世界对比由外层 pre/post 完成）。"""
    w = overload_world()
    run = mk_run_day(w, "c6_keys")
    rep = run._run_day()
    keys = sorted(rep.checks)
    with open(os.path.join(HERE, f"_t159_keys_{os.environ.get('T159_TAG', 'x')}.json"), "w",
              encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=1)
    check("C6 checks 键集里没有 budget/deferred/stamina_budget 之类可洗白项",
          not ({"budget", "deferred_by_budget", "stamina_budget"} & set(keys)), f"{keys}")
    known = ["crops_watered", "day_justified", "no_blocking_modal", "no_hard_failures",
             "no_unmet_stages", "refused_within_bound", "slept_by_us",
             "unreachable_within_bound", "watered_outdoor", "zero_action_evidenced"]
    check("C6b checks 键集与既有 10 项完全一致（task-158 未新增键）", keys == known, f"{keys}")


# --------------------------------------------------------------------------- 工具侧
def _cli_verify(path):
    """工具侧一律走它自己的 CLI（进程内 `load/build_days/report` 语义不同，会得出 problems=[]）。"""
    tool = os.path.join(ROOT, "tools", "verify-run3.py")
    proc = subprocess.run([sys.executable, tool, "--journal", path, "--days", "1"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = [ln.strip() for ln in out.splitlines()
            if ln.strip().startswith("[") or "结论" in ln]
    return proc.returncode, tail


def case_tool():
    """工具侧：把"blocked + gave_up_dry"的一天伪造成 VERIFIED ⇒ 工具必须判红；
    缺字段一律【无法判定】（不许当通过）。"""
    src = os.path.join(JOURNAL_DIR, "b1_blocked.jsonl")
    if not os.path.exists(src):
        check("T1 工具侧前置账本存在", False, f"缺 {src}")
        return
    rows = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]

    def patch(tag, mutate):
        forged = copy.deepcopy(rows)
        for e in forged:
            if e.get("event") == "day_end":
                mutate(e)
        p = os.path.join(JOURNAL_DIR, f"tool_forged_{tag}.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for e in forged:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return p

    def all_true(e):
        e["verified"] = True
        e["checks"] = {k: True for k in (e.get("checks") or {}).keys()} or {"watered_outdoor": True}
        e["ended_by"] = "sleep"

    f1 = patch("green", all_true)
    rc1, tail1 = _cli_verify(f1)
    check("T1 blocked/gave_up_dry 的一天伪造成 VERIFIED ⇒ 工具判红",
          rc1 != 0, f"rc={rc1} :: {tail1[:3]}")

    f3 = patch("green_finish", all_true)
    rows3 = [json.loads(l) for l in open(f3, encoding="utf-8") if l.strip()]
    for e in rows3:
        if e.get("event") == "finish":
            e["code"] = 0
            e["verified_streak"] = 1
            e["days"] = 1
    with open(f3, "w", encoding="utf-8") as f:
        for e in rows3:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    rc3, tail3 = _cli_verify(f3)
    check("T3 连 finish 一起伪造成达标 ⇒ 工具仍判红（final_water.dry>0 vs watered_outdoor=true）",
          rc3 != 0, f"rc={rc3} :: {tail3[:3]}")

    def strip(e):
        all_true(e)
        e.get("checks", {}).pop("watered_outdoor", None)
        e.pop("final_water", None)

    f2 = patch("nostrip", strip)
    rc2, tail2 = _cli_verify(f2)
    check("T2 缺 watered_outdoor/final_water ⇒ 缺失即问题（不许当通过）",
          rc2 != 0, f"rc={rc2} :: {tail2[:3]}")


# --------------------------------------------------------------------------- main
def main():
    print(f"ROOT={ROOT}")
    print(f"task-157 present={HAS_157} (FAR_DRY_OPEN_MAX={OPEN_MAX}) "
          f"task-158 present={HAS_158}")
    case_b1()
    case_b1b()
    case_b1c()
    case_b2()
    case_b3()
    case_c1()
    case_c2()
    case_c3()
    case_c4()
    case_c5()
    case_c6()
    case_tool()
    passed = sum(1 for _t, ok, _d in RESULTS if ok)
    print(f"=== {passed}/{len(RESULTS)} PASS ===")
    for tag, ok, detail in RESULTS:
        if not ok:
            print(f"  FAIL {tag} :: {detail}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
