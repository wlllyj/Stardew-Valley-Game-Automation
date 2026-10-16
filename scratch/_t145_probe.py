"""task-145 独立对抗验收探针（只写 scratch/；T145_ROOT 切树）。

用法：
  $env:T145_ROOT = "<repo>\\scratch\\_t145_post"      # 或 _t145_pre143 / _t145_pre144
  python scratch\\_t145_probe.py

B 段：复现 run9c 两条形态（plant 分配额超种子数 / water 壶空停半路）⇒ pre FAIL → post PASS。
C 段：六组对抗（谎报 seeds / 上限掩盖真没种完 / 壶空无补水点 / 补水异常 / ""+undone 共存 / 两卡交叉）。
"""
import os
import sys
import json

ROOT = os.environ.get("T145_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "brain"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import test_longrun as TL  # noqa: E402

FakeWorld = TL.FakeWorld
FakeWorker = TL.FakeWorker
StepResult = TL.StepResult
StageResult = TL.StageResult
DayReport = TL.DayReport
make_run = TL.make_run
STAGE_ACTION = TL.STAGE_ACTION

RESULTS = []


def check(tag, ok, detail=""):
    RESULTS.append((tag, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {tag}" + (f" :: {detail}" if detail else ""))
    return bool(ok)


def plot(*tiles):
    tiles = [tuple(int(c) for c in t) for t in tiles]
    return {"zone": "", "label": "", "anchor": list(tiles[0]),
            "tiles": [list(t) for t in tiles], "note": ""}


def put_crops(w, tiles, watered=False, ripe=False):
    out = []
    for t in tiles:
        tt = (int(t[0]), int(t[1]))
        w.dirt.add(tt)
        w.crops[tt] = {"watered": watered, "ripe": ripe}
        out.append(tt)
    return out


def mk_run(w, worker=None, **kw):
    worker = worker or FakeWorker(w, log=lambda *_: None)
    client = TL._CountingClient(w) if hasattr(TL, "_CountingClient") else TL.FakeClient(w)
    run = make_run(w, target_days=1, max_days=1,
                   client_factory=lambda: client, worker_factory=lambda c: worker, **kw)
    run.worker = worker
    run.client = client
    run.plot_size = 5
    return run


def events(run, name):
    return [e for e in run.entries if e.get("event") == name]


def stage_recs(rep, stage):
    return [s for s in rep.stages if s.get("stage") == stage]


def one_stage(task, w, worker=None, tiles=None, rep_day=18):
    """直接跑一个阶段（不做整天），返回 (rep, out, stage_record)。"""
    run = mk_run(w, worker=worker)
    rep = DayReport(day_key=("summer", rep_day, 12), started_at=0.0)
    tiles = list(tiles if tiles is not None else sorted(w.dirt))
    out = run._step_stage(task, w.obs(), plot(*tiles), rep)
    recs = stage_recs(rep, task)
    return run, rep, out, (recs[-1] if recs else None)


def fmt(s):
    if s is None:
        return "<无 stage 记录>"
    return (f"assigned={s.get('assigned')} ok={s.get('ok')} skipped={s.get('skipped')} "
            f"failed={s.get('failed')} undone={s.get('assigned_undone')} "
            f"leftover={s.get('leftover')} stopped={s.get('stopped')!r}")


# ---------------------------------------------------------------- B 段
GRID12 = [(60 + i % 4, 10 + i // 4) for i in range(12)]
GRID30 = [(60 + i % 6, 10 + i // 6) for i in range(30)]


def b1_plant_quota():
    """run9c day1 形态 ①：手上 11 粒种子、12 格空地 ⇒ 分配额必须 ≤11、assigned_undone==0。"""
    w = FakeWorld(seeds=11, money=0, weeds=0)
    w.dirt = set(GRID12)
    run = mk_run(w)
    pool = run._stage_tiles("plant_area", w.obs(), plot(*GRID12))
    run2, rep, _out, rec = one_stage("plant_area", w, tiles=GRID12)
    detail = f"pool={len(pool)} {fmt(rec)} crops={len(w.crops)}"
    ok = (rec is not None and rec.get("assigned") == 11 and rec.get("assigned_undone") == 0
          and rec.get("ok") == 11 and len(pool) == 11)
    return check("B1 plant 分配额 ≤ 种子数（assigned==11 / undone==0）", ok, detail), detail


def b2_water_refill():
    """run9c 形态 ②：壶 25、30 格待浇、有补水点 ⇒ 补水 ≥1、≤2，阶段做完、undone==0。"""
    w = FakeWorld(weeds=0, seeds=0, money=0, water_left=25)
    put_crops(w, GRID30)
    run, rep, _out, rec = one_stage("water_area", w, tiles=GRID30)
    retries = events(run, "refill_retry")
    refills = events(run, "refill")
    detail = (f"refills={w.refills} refill_ev={len(refills)} retry_ev={len(retries)} "
              f"{fmt(rec)} unwatered={sum(1 for c in w.crops.values() if not c['watered'])}")
    ok = (rec is not None and rec.get("assigned_undone") == 0
          and 1 <= w.refills <= 2 and rec.get("ok") == 30)
    return check("B2 water 壶空⇒补水续做（undone==0、1≤refills≤2）", ok, detail), detail


class RadiusWorld(FakeWorld):
    """观测恒以玩家为中心（不像 MyopicWorld 有 revealed 逃逸）⇒ 复刻真机窗口漂移。"""

    radius = 3

    def obs(self):
        o = super().obs()
        pt = tuple(self.player_tile)
        loc = o["location"]
        loc["tillable"] = [c for c in loc["tillable"]
                           if abs(c[0] - pt[0]) + abs(c[1] - pt[1]) <= self.radius]
        loc["tiles"] = [t for t in loc["tiles"]
                        if abs(t["tile"][0] - pt[0]) + abs(t["tile"][1] - pt[1]) <= self.radius]
        return o


class WalkingWorker(FakeWorker):
    """每格动作前先"走到格边"（真 `FarmWorker` 的行为）⇒ 观测窗口跟着漂移。"""

    def run_stage(self, stage, tiles, *, min_stamina=12.0, max_steps=200):
        action = STAGE_ACTION.get(stage, stage)
        res = StageResult(stage=stage, tiles=list(tiles))
        for i, tile in enumerate(tiles):
            if i >= max_steps:
                res.stopped, res.stopped_reason = "budget", f"达到格数上限 {max_steps}"
                break
            self.w.player_tile = [int(tile[0]), int(tile[1]) + 1]
            if action in ("clear", "clear_dead", "till", "water", "harvest", "sow") and self.w.stamina < min_stamina:
                res.stopped, res.stopped_reason = "stamina", "体力不足"
                break
            st = getattr(self.w, action)(tuple(int(c) for c in tile))
            self.steps.append(st)
            res.steps.append(st)
            if st.code in ("no_seed", "need_refill"):
                res.stopped, res.stopped_reason = st.code, st.reason
                break
        return res


def b2b_window_drift():
    """窗口漂移形态：补水后必须"原样重跑"这一批（forced），否则漂出窗口的格没人浇。"""
    wide = [(60 + i % 10, 10 + i // 10) for i in range(30)]
    w = RadiusWorld(weeds=0, seeds=0, money=0, water_left=8)
    w.player_tile = [62, 11]
    put_crops(w, wide)
    worker = WalkingWorker(w, log=lambda *_: None)
    run = mk_run(w, worker=worker)
    rep = DayReport(day_key=("summer", 18, 12), started_at=0.0)
    run._step_stage("water_area", w.obs(), plot(*wide), rep)
    rec = stage_recs(rep, "water_area")
    rec = rec[-1] if rec else None
    bad = [s for s in rep.stages if s.get("stopped") == "" and int(s.get("assigned_undone") or 0) > 0]
    detail = f"{fmt(rec)} refills={w.refills} \"\"+undone 阶段={len(bad)}"
    ok = (rec is not None and rec.get("assigned_undone") == 0 and not bad)
    return check("B2b 窗口漂移下补水原样重跑（undone==0 且无 \"\"+undone）", ok, detail), detail


# ---------------------------------------------------------------- C 段
class FailSowWorker(FakeWorker):
    """指定格 sow 永不成功（世界不变）⇒ "分配额 ≤ 种子数"也救不了"真没种完"。"""

    def __init__(self, world, *, fail_tiles=()):
        super().__init__(world, log=lambda *_: None)
        self.fail_tiles = {tuple(int(c) for c in t) for t in fail_tiles}

    def run_stage(self, stage, tiles, *, min_stamina=12.0, max_steps=200):
        action = STAGE_ACTION.get(stage, stage)
        res = StageResult(stage=stage, tiles=list(tiles))
        for i, tile in enumerate(tiles):
            if i >= max_steps:
                res.stopped = "budget"
                break
            t = tuple(int(c) for c in tile)
            if t in self.fail_tiles:
                st = StepResult(action, t, code="failed", reason="这一格今天没做成（探针桩）")
            else:
                st = getattr(self.w, action)(t)
            self.steps.append(st)
            res.steps.append(st)
            if st.code in ("no_seed", "need_refill"):
                res.stopped = st.code
                break
        return res


class NoRefillWorker(FakeWorker):
    def refill_can(self, *, timeout_ms=15000):
        return StepResult("refill_can", code="failed", reason="补水点走不到（探针桩）")


class LiarRefillWorker(FakeWorker):
    """回执 ok=True 但壶真没补上（回执说谎）⇒ 必须有界停止、不洗白。"""

    def __init__(self, world):
        super().__init__(world, log=lambda *_: None)
        self.calls = 0

    def refill_can(self, *, timeout_ms=15000):
        self.calls += 1
        return StepResult("refill_can", ok=True, reason="回执说补上了（但世界没变）")


class BoomRefillWorker(FakeWorker):
    def refill_can(self, *, timeout_ms=15000):
        raise RuntimeError("refill 探针桩：桥异常穿出")


class FakeNightWorker(FakeWorker):
    """跑完把时间推到夜里（≥ sleep_at=2200）⇒ 检验诚实上限与 §4-6 不变量的边界。"""

    def __init__(self, world, *, fail_tiles=()):
        super().__init__(world, log=lambda *_: None)
        self.fail_tiles = {tuple(int(c) for c in t) for t in fail_tiles}

    def run_stage(self, stage, tiles, *, min_stamina=12.0, max_steps=200):
        res = super().run_stage(stage, tiles, min_stamina=min_stamina, max_steps=max_steps)
        action = STAGE_ACTION.get(stage, stage)
        for i, tile in enumerate(res.steps):
            t = tuple(int(c) for c in tile.tile) if tile.tile else None
            if t in self.fail_tiles:
                tile.ok = False
                tile.code = "failed"
                tile.reason = "这一格今天没做成（探针桩）"
        self.w.time_of_day = 2510
        return res


def c1_seed_underreport():
    """C1：种子的真值只有自述（名字不在 SEED_NAME_HINTS 里 ⇒ 脑当 0）⇒ 分派 0 却可能全绿。"""
    w = FakeWorld(seeds=0, money=0, weeds=0)
    w.dirt = set(GRID12)
    # 把种子叠改名成中文（id 仍是当季种子），模拟"名字认不出来"的自述形态
    for it in w.inventory:
        if it.get("slot") == 5:
            it["name"] = "麦种"
    run = mk_run(w)
    pool = run._stage_tiles("plant_area", w.obs(), plot(*GRID12))
    seeds, money, can_plant = run._seed_outlook(w.obs())
    # 世界本身能不能种？（假世界的 plant 用 SEED_ID 认叠，与脑侧名字口径不同）
    probe = FakeWorld(seeds=3, money=0, weeds=0)
    probe.dirt.add((60, 10))
    world_can_plant = probe.plant((60, 10)).ok
    detail = f"脑侧 seeds={seeds} can_plant={can_plant} pool={len(pool)}；世界 plant() 可行={world_can_plant}"
    # 不断言"必须分派"（名字识别是既有边界），只把它记为信息项：分派 0 且无 stage ⇒ 不算 unmet
    return check("C1 种子名认不出时 plant_area 静默 0 目标（既有边界，非本卡引入）",
                 len(pool) == 0, detail), detail


def c2_cap_hides_incomplete():
    """C2：种子够、格子够，但 4 格真没种成 ⇒ 上限不许把它洗成 0。"""
    w = FakeWorld(seeds=20, money=0, weeds=0)
    w.dirt = set(GRID12)
    worker = FailSowWorker(w, fail_tiles=GRID12[8:12])
    run = mk_run(w, worker=worker)
    rep = DayReport(day_key=("summer", 18, 12), started_at=0.0)
    run._step_stage("plant_area", w.obs(), plot(*GRID12), rep)
    rec = (stage_recs(rep, "plant_area") or [None])[-1]
    run2 = mk_run(FakeWorld(seeds=20, money=0, weeds=0), worker=FailSowWorker(
        FakeWorld(seeds=20, money=0, weeds=0), fail_tiles=GRID12[8:12]))
    # 判据：undone 必须 >0（且 day 级 unmet ⇒ checks false 由 C5/C6 的整天用例覆盖）
    ok = rec is not None and int(rec.get("assigned_undone") or 0) > 0
    return check("C2 上限不许掩盖真没种完（4 格 failed ⇒ undone>0）", ok, fmt(rec)), fmt(rec)


def c3_no_refill_point():
    """C3：壶空且没有补水点 ⇒ 如实 need_refill + undone>0（不算诚实上限）。"""
    w = FakeWorld(weeds=0, seeds=0, money=0, water_left=2)
    put_crops(w, GRID12[:6])
    run, rep, _out, rec = one_stage("water_area", w, worker=NoRefillWorker(w), tiles=GRID12[:6])
    detail = fmt(rec) + f" calls_refill≈{len(events(run, 'refill_retry'))}"
    ok = (rec is not None and rec.get("stopped") == "need_refill"
          and int(rec.get("assigned_undone") or 0) > 0)
    return check("C3 壶空且无补水点 ⇒ stopped=need_refill + undone>0", ok, detail), detail


def c4_refill_anomalies():
    """C4：补水回执说谎 / refill_can 抛异常 ⇒ 有界、不崩、不洗白。"""
    w1 = FakeWorld(weeds=0, seeds=0, money=0, water_left=2)
    put_crops(w1, GRID12[:6])
    worker1 = LiarRefillWorker(w1)
    _run1, _rep1, _o1, rec1 = one_stage("water_area", w1, worker=worker1, tiles=GRID12[:6])
    ok1 = (worker1.calls <= 2 and rec1 is not None
           and rec1.get("stopped") == "need_refill"
           and int(rec1.get("assigned_undone") or 0) > 0)
    check("C4a 补水回执说谎(ok=True 但没补上) ⇒ ≤2 次、stopped=need_refill、undone>0", ok1,
          f"calls={worker1.calls} {fmt(rec1)}")

    w2 = FakeWorld(weeds=0, seeds=0, money=0, water_left=2)
    put_crops(w2, GRID12[:6])
    raised = ""
    try:
        one_stage("water_area", w2, worker=BoomRefillWorker(w2), tiles=GRID12[:6])
    except BaseException as exc:            # noqa: BLE001 —— 就是要看异常会不会穿出
        raised = f"{type(exc).__name__}: {exc}"
    # 这是"桩里塞了一个 Python 异常"的信息项（不是卡面口径里的"回执异常"）：
    # 生产 `FarmWorker.refill_can` 只捕 `BridgeError`，任何别的异常本来就没兜底。
    print(f"      [INFO] C4b 桩异常（RuntimeError）穿出 `_step_stage`：{raised or '未抛'}")
    return ok1, raised


def c4c_real_refill_bridge_error():
    """C4c：**真实** `FarmWorker.refill_can` 遇桥异常 ⇒ 会不会把 `BridgeError` 抛给调用方？

    `refill_can`（`farmwork.py:2360` 与 `:2387`）里的 `self.snap()` **没有 try**；而
    `_step_stage` 的 refill 分支（post `longrun.py:3580` / pre `:3504`）也是裸调
    `self.worker.refill_can()`，`_run_stage_intent`→`_run_day`→`run()` 三处都没有
    `BridgeError` 兜底 ⇒ 一旦抛出，整轮长跑直接带栈退出（而不是 graceful
    `ended_by="bridge_down"`）。本项只做**可达性**取证，三棵树同形即"既有缺口、非本卡引入"。
    """
    BridgeError = getattr(TL, "BridgeError", None)
    if BridgeError is None:
        from agentfarm.bridge import BridgeError as _BE  # type: ignore
        BridgeError = _BE

    class DeadObserveClient(TL.FakeClient):
        def observe(self, detail="summary", *, timeout=None):
            raise BridgeError("桥断了（探针桩）", status="bridge_down")

    w = FakeWorld(weeds=0, seeds=0, money=0, water_left=0)
    put_crops(w, GRID12[:6])
    worker = TL.FarmWorker(DeadObserveClient(w), log=lambda *_: None, pause=lambda _s: None)
    escaped = ""
    try:
        worker.refill_can()
    except BridgeError as exc:
        escaped = f"BridgeError 穿出 refill_can：{exc}"
    except BaseException as exc:            # noqa: BLE001
        escaped = f"{type(exc).__name__}: {exc}"
    ok = check("C4c 真实 refill_can 遇桥异常是否穿出（穿出 ⇒ 会一路穿到 run()）",
               not escaped, escaped or "内部消化")
    return ok, escaped


def c5_invariant_and_cause():
    """C5：`stopped=="" ∧ assigned_undone>0` 不许共存；归因四类认得。"""
    ok_cause = True
    cases = [(StepResult("water", tile=(60, 10), code="need_refill"), "need_refill"),
             (StepResult("clear", tile=(60, 10), code="unreachable"), "unreachable"),
             (StepResult("sow", tile=(60, 10), code="no_seed"), "no_seed"),
             (StepResult("till", tile=(60, 10), code="failed"), "incomplete")]
    got = []
    for step, want in cases:
        try:
            g = TL.LongRun._stage_undone_cause([step], [(60, 10)])
        except Exception as exc:            # noqa: BLE001
            g = f"<{type(exc).__name__}>"
        got.append(f"{step.code}->{g}(want {want})")
        if g != want:
            ok_cause = False
    check("C5a `_stage_undone_cause` 四类归因", ok_cause, "; ".join(got))

    # 三形态世界（true 失败 / 壶空无补水点 / 夜里失败）扫不变式
    offenders = []
    w1 = FakeWorld(seeds=20, money=0, weeds=0)
    w1.dirt = set(GRID12)
    run1 = mk_run(w1, worker=FailSowWorker(w1, fail_tiles=GRID12[8:12]))
    rep1 = DayReport(day_key=("summer", 18, 12), started_at=0.0)
    run1._step_stage("plant_area", w1.obs(), plot(*GRID12), rep1)
    w2 = FakeWorld(weeds=0, seeds=0, money=0, water_left=2)
    put_crops(w2, GRID12[:6])
    run2, rep2, _o, _r = one_stage("water_area", w2, worker=NoRefillWorker(w2), tiles=GRID12[:6])
    w3 = FakeWorld(weeds=0, seeds=0, money=0)
    for t in GRID12[:3]:
        w3.blockers[tuple(t)] = "weed"
    run3 = mk_run(w3, worker=FakeNightWorker(w3, fail_tiles=GRID12[:1]))
    rep3 = DayReport(day_key=("summer", 18, 12), started_at=0.0)
    run3._step_stage("clear_area", w3.obs(), plot(*GRID12[:3]), rep3)
    for tag, rep in (("plant/failed", rep1), ("water/need_refill", rep2), ("clear/night-failed", rep3)):
        for s in rep.stages:
            if s.get("stopped") == "" and int(s.get("assigned_undone") or 0) > 0:
                offenders.append(f"{tag}: {fmt(s)}")
    check("C5b `stopped==""` 与 `assigned_undone>0` 不共存（3 形态）", not offenders,
          "; ".join(offenders) or "三形态均无该组合")
    return ok_cause, offenders


def c6_cross_day():
    """C6：种子用尽与壶空（无补水点）同一天 ⇒ 两处都不能把 undone 洗成 0，当天不达标。

    * `plant_area`：task-143 把分配额收窄到手上种子数 ⇒ "种子用尽"本身不再产生 unmet（设计目标）；
    * `water_area`：壶空且补水不成 ⇒ 必须如实 `stopped=need_refill` + `assigned_undone>0`；
    * 日级：`checks["no_unmet_stages"]` 必须为 False（不许洗白）。
    """
    w = FakeWorld(seeds=3, money=0, weeds=0, water_left=2)
    w.dirt = set(GRID12)
    put_crops(w, GRID12[:5])
    for t in GRID12[:5]:
        w.crops[t]["watered"] = False
    worker = NoRefillWorker(w)              # 壶只有 2、没有补水点
    run = mk_run(w, worker=worker)
    code = run.run()
    rep = run.days[0] if run.days else None
    checks = dict(rep.checks) if rep is not None else {}
    stages = [(s.get("stage"), fmt(s)) for s in (rep.stages if rep is not None else [])]
    detail = (f"rc={code} no_unmet_stages={checks.get('no_unmet_stages')} "
              f"assigned_undone={getattr(rep, 'assigned_undone', None)} "
              f"deferred={getattr(rep, 'deferred_tiles', None)}")
    ok = checks.get("no_unmet_stages") is False
    check("C6 种子用尽+壶空(无补水点)同一天 ⇒ no_unmet_stages=False（不洗白）", ok, detail)
    print("      stages: " + " | ".join(f"{n}: {d}" for n, d in stages))
    return ok, detail


def main():
    print(f"=== tree: {ROOT} ===")
    b1_plant_quota()
    b2_water_refill()
    b2b_window_drift()
    c1_seed_underreport()
    c2_cap_hides_incomplete()
    c3_no_refill_point()
    c4_refill_anomalies()
    c4c_real_refill_bridge_error()
    c5_invariant_and_cause()
    c6_cross_day()
    npass = sum(1 for _t, ok, _d in RESULTS if ok)
    print(f"\n=== {npass}/{len(RESULTS)} PASS ===")
    for tag, ok, detail in RESULTS:
        if not ok:
            print(f"  FAIL {tag} :: {detail}")
    return 0 if npass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
