"""task-135 独立对抗验收探针（task-133 water_far 补水/逐格判据 + task-134 resume 有界与 leftover 口径拆分）。

用法（只写 scratch/，绝不改生产代码）：
    $env:PYTHONUTF8="1"
    $env:T135_ROOT="<repo>\\scratch\\_t135_head"   # 或 _t135_pre133 / _t135_pre134
    & $py scratch\\_t135_probe.py

head 树应尽量全 PASS；pre 树在对应项上 FAIL（就是 FAIL→PASS 的原文证据）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(os.environ.get("T135_ROOT") or Path(__file__).resolve().parents[1]).resolve()
TREE = os.environ.get("T135_TREE") or ROOT.name
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "brain"))

import test_longrun as TL  # noqa: E402
from agentfarm.farmwork import StepResult  # noqa: E402
from agentfarm.longrun import DayReport  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((tag, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {tag}" + (f" :: {detail}" if detail else ""))


def info(tag: str, detail: str) -> None:
    print(f"[INFO] {tag} :: {detail}")


def ev(run, name: str) -> list[dict]:
    return [e for e in run.entries if e.get("event") == name]


def load_tool(path: Path):
    spec = importlib.util.spec_from_file_location("vr135", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


VR = load_tool(ROOT / "tools" / "verify-run3.py")
VR_REPO = load_tool(REPO / "tools" / "verify-run3.py")
IS_HEAD = "head" in TREE.lower()

FAR = (61, 10)
OTHER = (63, 13)


def rep_of(day: int = 12) -> DayReport:
    return DayReport(day_key=(1, "summer", day), started_at=0.0)


class Shims(TL.FakeWorker):
    """补 `TL.FakeWorker` 缺的方法（sleep/refill/water），并让 `water()` 真的改世界。"""

    def __init__(self, world, **kw):
        super().__init__(world, log=lambda *_: None)
        self.refill_calls = 0
        self.sleep_calls = 0
        self.refill_works = True
        self.water_target = None  # None = 真浇请求的那一格

    def refill_can(self, *, timeout_ms=15000):
        self.refill_calls += 1
        if self.refill_works:
            self.w.water_left = 40
        return StepResult("refill_can", ok=self.refill_works,
                          code="ok" if self.refill_works else "unreachable", reason="假回执：补水")

    def sleep(self, *, home="FarmHouse", **kw):
        self.sleep_calls += 1
        return self.w.sleep()

    def water(self, tile, *, timeout_ms=15000):
        t = tuple(tile)
        target = tuple(self.water_target) if self.water_target else t
        if not hasattr(self.w, "crops"):
            self.w.crops = {}
        self.w.crops.setdefault(target, {"watered": False, "ripe": False})
        self.w.crops[target]["watered"] = True
        self.w.water_left = max(0, int(getattr(self.w, "water_left", 40)) - 1)
        st = StepResult("water", t, ok=True, code="ok", reason="假回执：浇上了")
        self.steps.append(st)
        return st


class NeedRefillOnce(Shims):
    def __init__(self, world):
        super().__init__(world)
        self.once = True
        self.water_tiles: list[tuple[int, int]] = []

    def water(self, tile, *, timeout_ms=15000):
        self.water_tiles.append(tuple(tile))
        if self.once:
            self.once = False
            st = StepResult("water", tuple(tile), code="need_refill", reason="假回执：走到跟前壶空")
            self.steps.append(st)
            return st
        return super().water(tile, timeout_ms=timeout_ms)


class FakeIsland(Shims):
    """`water()` 只把**别的格**浇上（本格不动）⇒ 全局 dryCrops 掉、本格仍在 dryTiles。"""

    def __init__(self, world):
        super().__init__(world)
        self.water_target = OTHER

    def water(self, tile, *, timeout_ms=15000):
        other = OTHER if tuple(tile) != OTHER else (62, 12)
        self.water_target = other
        return super().water(tile, timeout_ms=timeout_ms)


class RefillOkButEmpty(Shims):
    """补水永远"成功"但壶里水位不变 ⇒ 验补水自旋有界。"""

    def refill_can(self, *, timeout_ms=15000):
        self.refill_calls += 1
        return StepResult("refill_can", ok=True, code="ok", reason="假回执：补水点说补好了")


class StoppedWorker(Shims):
    """每轮：少做一格（最后一格不派活，也不给 step）并写指定 `stopped` ⇒ 逼出"分配内少做"。

    `night_after_first=True` 时第一轮结束后把时钟拨到 2300，用来构造"夜里收工 + stopped=''"。
    """

    def __init__(self, world, stopped_name: str, *, night_after_first: bool = False):
        super().__init__(world)
        self.stopped_name = stopped_name
        self.night_after_first = night_after_first
        self.rounds = 0

    def run_stage(self, stage, tiles, **kw):
        tl = list(tiles)
        keep = tl[:-1] if len(tl) >= 2 else tl          # 最后一格**不派活**（既不 ok 也不 skipped）
        res = super().run_stage(stage, keep, **kw)
        res.stopped = self.stopped_name
        res.stopped_reason = f"假：{self.stopped_name}"
        self.rounds += 1
        if self.night_after_first and self.rounds == 1:
            self.w.time_of_day = 2300
        for t in keep:                                  # 把做过的格"还回去"⇒ 目标池每轮都一样，
            self.w.dirt.discard(tuple(t))               # 免得最后一轮退化成 tiles<=0 的干净记录
            self.w.tillable.add(tuple(t))
        return res


def far_world(*, water_left: int = 0, with_dry_tiles: bool = True, truncated: bool = False,
              extra_dry: bool = False):
    w = TL.DryTilesWorld(seeds=0, money=0, weeds=0, water_left=water_left,
                         with_dry_tiles=with_dry_tiles, truncated=truncated)
    w.dirt.add(FAR)
    w.crops[FAR] = {"watered": False, "ripe": False}
    if extra_dry:
        w.dirt.add(OTHER)
        w.crops[OTHER] = {"watered": False, "ripe": False}
    w.player_tile = [62, 14]
    w.location = "Farm"
    w.is_outdoor_farm = True
    return w


def far_run(w, worker):
    run = TL.make_run(w, target_days=1, max_days=1, client_factory=lambda: TL.FakeClient(w),
                      worker_factory=lambda _c: worker)
    run.worker = worker
    return run, rep_of()


def farm_run(w, worker, *, tasks=("till_area", "sleep"), time_of_day: int | None = None,
             journal: Path | None = None):
    w.time_of_day = time_of_day if time_of_day is not None else 600
    planner = TL.FakePlanner(*[TL.TaskIntent(t, "anchor:current_location", t) for t in tasks])
    kw = {}
    if journal is not None:
        journal.parent.mkdir(parents=True, exist_ok=True)
        kw["journal_path"] = str(journal)
    run = TL.make_run(w, planner=planner, target_days=1, max_days=1,
                      worker_factory=lambda _c: worker, **kw)
    code = run.run()
    rep = run.days[-1] if run.days else None
    return run, rep, code


# ---------------------------------------------------------------- B 段
def b1_refill_retry() -> None:
    w = far_world(water_left=0)
    worker = NeedRefillOnce(w)
    run, rep = far_run(w, worker)
    run._water_far_dry(w.obs(), rep)
    rf, wf = ev(run, "water_far_refill"), ev(run, "water_far")
    watered = bool(w.crops[FAR]["watered"])
    if IS_HEAD:
        check("B1 壶空 ⇒ 补水后重试同一格并浇成（head）",
              len(wf) == 1 and wf[0]["ok"] and wf[0].get("try_") == 1 and watered and len(rf) >= 1,
              f"refills={len(rf)} water_far={[(e.get('ok'), e.get('try_'), e.get('retried_after_refill')) for e in wf]} watered={watered}")
    else:
        check("B1 壶空 ⇒ 补水后重试同一格并浇成（pre133：应复现缺陷）",
              bool(rf) and watered,
              f"refill 事件={len(rf)} water_far={[(e.get('ok'), e.get('code')) for e in wf]} watered={watered}")


def b2_global_diff_is_not_evidence() -> None:
    w = far_world(water_left=40, extra_dry=True)
    run, rep = far_run(w, FakeIsland(w))
    run._water_far_dry(w.obs(), rep)
    wf = ev(run, "water_far")
    check("B2 别格被浇（全局 dryCrops 掉）不算本格证据",
          bool(wf) and not wf[0]["ok"],
          f"water_far={[(e.get('ok'), e.get('dry_before'), e.get('dry_after'), e.get('cause'), e.get('evidence')) for e in wf]}")


def b3_resume_bounded() -> None:
    w = TL.FakeWorld(weeds=4, seeds=0, money=0, water_left=40)
    worker = Shims(w)
    run = TL.make_run(w, target_days=1, max_days=1, worker_factory=lambda _c: worker)
    run.worker = worker
    rep = rep_of()
    run.leftover_targets = {(70, 20), (71, 20)}
    calls = 0
    for _ in range(12):
        calls += 1
        run._review_only_fallback(w.obs(), rep)
        if rep.ended_by:
            break
    burst = ev(run, "no_progress_burst")
    left = set(run.leftover_targets or ())
    if IS_HEAD:
        check("B3 resume 空转有界（head：≤5 次 + burst + leftover 不许归零）",
              calls <= 5 and bool(burst) and rep.ended_by == "stuck" and bool(left),
              f"calls={calls} burst={len(burst)} ended_by={rep.ended_by!r} leftover={sorted(left)}")
    else:
        check("B3 resume 空转有界（pre134：应复现无界空转）",
              calls <= 5 and bool(burst),
              f"calls={calls}（12 次仍在转） burst={len(burst)} ended_by={rep.ended_by!r}")


# ---------------------------------------------------------------- C 段
def c1_evidence_never_guessed() -> None:
    w = far_world(water_left=40, with_dry_tiles=False)
    run, rep = far_run(w, FakeIsland(w))
    run._water_far_dry(w.obs(), rep)
    check("C1 缺 dryTiles ⇒ 不许判 ok（且留 water_far_unavailable）",
          not any(e["ok"] for e in ev(run, "water_far")) and bool(ev(run, "water_far_unavailable")),
          f"water_far={len(ev(run, 'water_far'))} unavailable={len(ev(run, 'water_far_unavailable'))}")
    w = far_world(water_left=40, truncated=True)
    run, rep = far_run(w, FakeIsland(w))
    run._water_far_dry(w.obs(), rep)
    wf = ev(run, "water_far")
    check("C1 dryTiles 被截断 ⇒ 不许判 ok（cause=no_evidence）",
          bool(wf) and not any(e["ok"] for e in wf),
          f"water_far={[(e.get('ok'), e.get('cause'), e.get('evidence')) for e in wf]}")


def c2_refill_spin_bounded() -> None:
    w = far_world(water_left=0)
    worker = RefillOkButEmpty(w)
    run, rep = far_run(w, worker)
    for _ in range(6):
        run._water_far_dry(w.obs(), rep)
    rf, wf = ev(run, "water_far_refill"), ev(run, "water_far")
    check("C2 补水自称成功但水位不变 ⇒ 有界（≤2 次）且认输写壶空",
          len(rf) <= 2 and len(wf) <= 2 and bool(run.far_dry_given_up),
          f"refills={len(rf)} water_far={len(wf)} given_up={sorted(run.far_dry_given_up)}")


def c3_ok_givenup_mutex() -> None:
    w = far_world(water_left=0)
    run, rep = far_run(w, RefillOkButEmpty(w))
    for _ in range(6):
        run._water_far_dry(w.obs(), rep)
    bad = [e for e in ev(run, "water_far") if e.get("ok") and e.get("given_up")]
    check("C3 同格不许同时 ok=true 且 given_up=true", not bad, f"违规事件={bad}")


def _shortfall_world():
    w = TL.FakeWorld(weeds=0, seeds=10, money=500, water_left=40)
    return w


def _day_shortfall(stopped: str, tod: int, *, night_after_first: bool = False, tag: str = ""):
    w = _shortfall_world()
    worker = StoppedWorker(w, stopped, night_after_first=night_after_first)
    jp = REPO / "scratch" / "_t135_j" / f"{TREE}_{tag or stopped or 'night'}_{tod}.jsonl"
    run, rep, code = farm_run(w, worker, time_of_day=tod, journal=jp)
    return run, rep, code


def c4_stopped_shortfall() -> None:
    for stopped in ("no_target", "world", "sow_failed"):
        _, rep, _ = _day_shortfall(stopped, 600)
        stages = rep.stages if rep else []
        undone = [s.get("assigned_undone") for s in stages if int(s.get("assigned_undone") or 0) > 0]
        unmet = (rep.checks or {}).get("no_unmet_stages") if rep else None
        check(f"C4 stopped={stopped!r} + assigned_undone>0 ⇒ 必须仍判 unmet",
              bool(undone) and unmet is False,
              f"assigned_undone={[s.get('assigned_undone') for s in stages]} "
              f"tiles={[s.get('tiles') for s in stages]} "
              f"stopped={[s.get('stopped') for s in stages]} no_unmet_stages={unmet} "
              f"assigned_unmet={getattr(rep, 'assigned_undone', None)} "
              f"deferred={getattr(rep, 'deferred_tiles', None)} plot_pending={getattr(rep, 'plot_pending', None)}")


def c4b_night_empty_stopped() -> None:
    """夜里收工 + `stopped==""`（阶段没被任何上限打断，但有格没做成）⇒ 算诚实延后吗？"""
    _, rep, code = _day_shortfall("", 600, night_after_first=True, tag="night")
    stages = rep.stages if rep else []
    unmet = (rep.checks or {}).get("no_unmet_stages")
    short = any(int(s.get("assigned_undone") or 0) > 0 for s in stages)
    info("C4b 夜里 + stopped='' + 短少（防御性形态，生产不可达：undone>0 而 stopped='' 只可能来自硬失败，硬失败 ⇒ no_hard_failures=False）",
         f"short={short} ended_by={getattr(rep, 'ended_by', None)!r} reason={str(getattr(rep, 'ended_reason', ''))[:40]!r} "
         f"tiles={[s.get('tiles') for s in stages]} assigned_undone={[s.get('assigned_undone') for s in stages]} "
         f"stopped={[s.get('stopped') for s in stages]} deferred={getattr(rep, 'deferred_tiles', None)} "
         f"no_unmet_stages={unmet} verified={getattr(rep, 'verified', None)} code={code}")


def c5_honest_stamina_deferred() -> None:
    _, rep, _ = _day_shortfall("stamina", 600)
    stages = rep.stages if rep else []
    unimplemented = not hasattr(rep, "deferred_tiles")
    check("C5 诚实上限（stamina）⇒ deferred_tiles>0 且不进 unmet",
          (not unimplemented) and getattr(rep, "deferred_tiles", 0) > 0
          and (rep.checks or {}).get("no_unmet_stages") is True,
          f"deferred={getattr(rep, 'deferred_tiles', None)} plot_pending={getattr(rep, 'plot_pending', None)} "
          f"no_unmet_stages={(rep.checks or {}).get('no_unmet_stages')} "
          f"stage(tiles,leftover,undone,stopped)={[(s.get('tiles'), s.get('leftover'), s.get('assigned_undone'), s.get('stopped')) for s in stages]}")


def _ledger_of(rep, journal: Path | None = None) -> tuple[bool, dict]:
    if journal is not None and journal.exists():
        rows = VR.load(str(journal))
    else:
        end = rep.as_dict()
        rows = [{"event": "day_start", "t": 0.0, "day": end.get("day")},
                {"event": "sleep", "t": 10.0, "day": end.get("day"), "ok": True},
                {"event": "day_end", "t": 20.0, "_lineno": 1, **end}]
    return VR.report(rows, target_days=1)


def c_tool_reconcile() -> None:
    for tag, stopped, tod, naf in (("no_target", "no_target", 600, False),
                                   ("night+stopped=''", "", 600, True),
                                   ("night+stamina", "stamina", 600, True),
                                   ("stamina", "stamina", 600, False)):
        run, rep, _ = _day_shortfall(stopped, tod, night_after_first=naf, tag=tag.replace("'", ""))
        jp = Path(str(getattr(run, "journal_path", "") or ""))
        ok, summary = _ledger_of(rep, jp if jp.name else None)
        brain = (rep.checks or {}).get("no_unmet_stages")
        flagged = any("no_unmet_stages" in p for p in summary["problems"])
        stage_undone = sum(int(s.get("assigned_undone") or 0) for s in (rep.stages or []))
        deferred = int(getattr(rep, "deferred_tiles", 0) or 0)
        same_dir = (brain is True and not flagged) or (brain is False and flagged)
        check(f"C-tool 同向：{tag}（脑 no_unmet={brain} / 工具={summary['verdict']} / stage_undone={stage_undone} deferred={deferred}）",
              same_dir,
              f"problems={summary['problems']} :: infos={[i for i in summary['infos'] if '诚实上限' in i or 'plot_pending' in i]}")


def c_tool_forged_journal_shortfall() -> None:
    """账本自称分配内做净（assigned_undone=0）但 journal 有 stage_shortfall{undone:5} ⇒ 工具抓不抓？"""
    jp = REPO / "scratch" / "_ledger_green.jsonl"
    if not jp.exists():
        info("C-tool 伪造", "缺 scratch/_ledger_green.jsonl")
        return
    rows = VR.load(str(jp))
    ends = [r for r in rows if r.get("event") == "day_end"]
    if not ends:
        return
    end = dict(ends[0])
    end["stages"] = [{"stage": "till_area", "tiles": 10, "leftover": 5, "assigned": 10,
                      "assigned_undone": 0, "stopped": "no_target",
                      "ok": 10, "failed": 0, "skipped": 0}]
    end["checks"] = dict(end.get("checks") or {})
    end["checks"]["no_unmet_stages"] = True
    end["checks"]["no_hard_failures"] = True
    end["assigned_undone"] = 0
    end["plot_pending"] = 5
    end["deferred_tiles"] = 0
    forged = [r for r in rows if r is not ends[0]] + [end]
    forged.append({"event": "stage_shortfall", "t": 15.0, "stage": "till_area", "zone": "z",
                   "assigned": 10, "undone": 5, "stopped": "no_target", "leftover": 5})
    _, head = VR.report(forged, target_days=1)
    pre_tool = load_tool(REPO / "scratch" / "_t135_pre134" / "tools" / "verify-run3.py")
    _, pre = pre_tool.report(forged, target_days=1)
    info("C-tool 伪造（账本 assigned_undone=0 + journal stage_shortfall{undone:5} + checks=True）",
         f"head={head['verdict']} problems={head['problems']} || pre134={pre['verdict']} problems={pre['problems']}")
    check("C-tool 伪造：工具必须能抓出「journal 说少做 5 格、账本说做净」",
          bool(head["problems"]),
          f"head={head['verdict']} problems={head['problems']}（pre134 口径={pre['verdict']}）")


def c7_run9b_replay() -> None:
    jp = REPO / "logs" / "longrun-3day-llm-run9b.jsonl"
    if not jp.exists():
        info("C7", "run9b 账本不存在")
        return
    rows = VR.load(str(jp))
    _, summary = VR.report(rows, target_days=3)
    days = {str(d["day"]): bool((d.get("checks") or {}).get("no_unmet_stages")) for d in summary["days"]}
    print(f"[INFO] C7 {TREE} verdict={summary['verdict']} problems={len(summary['problems'])} days_no_unmet={days}")
    check("C7 run9b 三天 no_unmet_stages 仍为 false（与卡面 §0 一致）",
          days.get("summer 13") is False and days.get("summer 14") is False and days.get("summer 15") is False,
          f"days={days}")


def main() -> int:
    print(f"=== task-135 探针 tree={TREE} root={ROOT} ===")
    for fn in (b1_refill_retry, b2_global_diff_is_not_evidence, b3_resume_bounded,
               c1_evidence_never_guessed, c2_refill_spin_bounded, c3_ok_givenup_mutex,
               c4_stopped_shortfall, c4b_night_empty_stopped, c5_honest_stamina_deferred,
               c_tool_reconcile, c_tool_forged_journal_shortfall, c7_run9b_replay):
        try:
            fn()
        except Exception:
            check(fn.__name__, False, "异常：" + traceback.format_exc(limit=3).replace("\n", " | "))
    n_ok = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n=== {TREE}: {n_ok}/{len(RESULTS)} PASS ===")
    for tag, ok, detail in RESULTS:
        if not ok:
            print(f"  FAIL {tag} :: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
