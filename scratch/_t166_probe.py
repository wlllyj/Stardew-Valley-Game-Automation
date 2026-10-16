# -*- coding: utf-8 -*-
"""task-166 探针：task-163（体力预算延后口径）的对抗验收。

用法：
    $env:T166_ROOT = "<树根>"    # 不设则用当前工作树
    & $py scratch\\_t166_probe.py
输出：逐项 [PASS]/[FAIL]/[note] + 末尾汇总 JSON（写入 scratch\\_t166_<树名>.json）。
只写 scratch/；不改生产代码。
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import traceback

ROOT = pathlib.Path(os.environ.get("T166_ROOT") or pathlib.Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "brain"))
sys.path.insert(0, str(ROOT / "tests"))

from agentfarm import longrun as LR  # noqa: E402
import test_longrun as TL  # noqa: E402

TAG = ROOT.name
HAS163 = hasattr(LR.LongRun, "_budget_deferred_tasks")
JDIR = pathlib.Path(__file__).resolve().parent / "_t166_j"
JDIR.mkdir(exist_ok=True)

KNOWN10 = {
    "slept_by_us", "no_blocking_modal", "no_hard_failures", "unreachable_within_bound",
    "refused_within_bound", "no_unmet_stages", "crops_watered", "watered_outdoor",
    "day_justified", "zero_action_evidenced",
}

RES: list[dict] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    RES.append({"tag": tag, "ok": bool(ok), "detail": str(detail)[:400]})
    print(f"[{'PASS' if ok else 'FAIL'}] {tag} :: {str(detail)[:280]}")


def note(tag: str, detail: str = "") -> None:
    RES.append({"tag": tag, "ok": None, "detail": str(detail)[:400]})
    print(f"[note] {tag} :: {str(detail)[:280]}")


def case(fn):
    def wrapper():
        try:
            fn()
        except Exception as exc:  # 单个用例崩掉不拖垮整轮
            traceback.print_exc()
            check(f"{fn.__name__}.no_exception", False, f"{type(exc).__name__}: {exc}")
    wrapper.__name__ = fn.__name__
    return wrapper


def journal(name: str) -> str:
    p = JDIR / f"{TAG}_{name}.jsonl"
    if p.exists():
        p.unlink()
    return str(p)


def events(run, name: str) -> list[dict]:
    return [e for e in run.entries if e.get("event") == name]


def ev_names(run) -> list[str]:
    seen = []
    for e in run.entries:
        n = e.get("event")
        if n and n not in seen:
            seen.append(n)
    return seen


MICRO = [(60 + x, 10 + y) for x in range(5) for y in range(5)]


def dist(t, p=(62, 14)):
    return abs(t[0] - p[0]) + abs(t[1] - p[1])


WINDOW = [t for t in MICRO if dist(t) <= 3]  # 14 格（半径 3 的观测窗口）


class BlockedWaterWorld(TL.DryTilesWorld):
    """指定格永远浇不上（世界层失败），但仍留在阶段 tiles 里 ⇒ 计入 assigned_undone。"""

    blocked: set = set()

    def water(self, tile, *a, **kw):
        if tuple(tile) in getattr(self, "blocked", set()):
            return TL.StepResult("water", tuple(tile), ok=False, code="failed",
                                 reason="probe: 这一格真浇不上")
        return super().water(tile, *a, **kw)


def run_day(w, *, days=1, max_days=1, name="day", patch=None, worker_factory=None):
    client = TL.FakeClient(w)
    factory = worker_factory or (lambda c: TL.FakeWorker(w, log=lambda *a: None))
    worker = factory(client)
    run = TL.make_run(
        w, target_days=days, max_days=max_days,
        client_factory=lambda: client, worker_factory=lambda c: worker,
        journal_path=journal(name),
    )
    if patch is not None:
        patch(run)
    code = run.run()
    return run, code, worker


def overload_world(*, far_watered=140, dry_near=12, empty_near=2, stamina=200,
                   seeds=20, money=0, water_left=40, farm_unavailable=False,
                   world_cls=None):
    """超载农场：活苗总数 > 129 ⇒ reserve(=2*live+12) > 270(max) ⇒ 必然触发预算延后。"""
    cls = world_cls or TL.DryTilesWorld
    w = cls(weeds=0, seeds=seeds, money=money, water_left=water_left, stamina=stamina)
    w.player_tile = [62, 14]
    w.dirt = set(MICRO)
    w.crops = {}
    for t in list(WINDOW)[:dry_near]:
        w.crops[t] = {"watered": False, "ripe": False, "dead": False}
    for i in range(far_watered):
        t = (100 + i, 50 + (i % 3))
        w.dirt.add(t)
        w.crops[t] = {"watered": True, "ripe": False, "dead": False}
    if farm_unavailable:
        w.farm = None
    return w, list(WINDOW)[:dry_near]


def brief_day(rep):
    if rep is None:
        return "no day report"
    return (f"ended_by={rep.ended_by} reason={str(rep.ended_reason)[:90]} verified={rep.verified} "
            f"ok={rep.ok_steps} assigned_undone={rep.assigned_undone} plot_pending={rep.plot_pending} "
            f"deferred_tiles={rep.deferred_tiles}")


def tool_run(path, days=1):
    tool = ROOT / "tools" / "verify-run3.py"
    p = subprocess.run([sys.executable, str(tool), "--journal", str(path), "--days", str(days)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    verdict = "VERIFIED" if "结论：VERIFIED" in out else "needs_review"
    return p.returncode, verdict, out


# --------------------------------------------------------------------------- B 段
@case
def b1_overload_day_must_go_green():
    w, dry = overload_world()
    run, code, _ = run_day(w, name="b1")
    rep = run.days[-1] if run.days else None
    dep = events(run, "deferred_by_budget")
    dep_t = events(run, "budget_deferred_tiles")
    cap = events(run, "stage_capped_by_capacity")
    burst = events(run, "plot_exhausted_burst")
    note("B1.facts", f"code={code} days={len(run.days)} {brief_day(rep)} "
                     f"deferred={[e.get('task') for e in dep]} tile_ev={len(dep_t)} "
                     f"cap={len(cap)} burst={len(burst)} events={ev_names(run)}")
    note("B1.budget", json.dumps({k: v for k, v in (getattr(rep, "stamina_budget", {}) or {}).items()
                                 if k != "deferred"}, ensure_ascii=False)[:400])
    check("B1.run_code_0", code == 0, f"code={code}")
    check("B1.verified_true", bool(rep and rep.verified), brief_day(rep))
    check("B1.reason_no_work", bool(rep and str(rep.ended_reason).startswith("no_work")), brief_day(rep))
    check("B1.day_justified_true", bool(rep and rep.checks.get("day_justified")), brief_day(rep))
    check("B1.watered_outdoor_true", bool(rep and rep.checks.get("watered_outdoor")), brief_day(rep))
    check("B1.crops_watered_true", bool(rep and rep.checks.get("crops_watered")), brief_day(rep))
    check("B1.no_unmet_stages_true", bool(rep and rep.checks.get("no_unmet_stages")), brief_day(rep))
    check("B1.assigned_undone_zero", bool(rep and rep.assigned_undone == 0), brief_day(rep))
    check("B1.no_plot_burst", not burst, f"plot_exhausted_burst={len(burst)}")
    check("B1.deferral_recorded", len(dep) >= 1 and len(dep_t) >= 1,
          f"deferred_by_budget={len(dep)} budget_deferred_tiles={len(dep_t)}")
    check("B1.checks_keys_known", bool(rep and set(rep.checks) == KNOWN10),
          f"extra={sorted(set(rep.checks) - KNOWN10) if rep else '?'} missing={sorted(KNOWN10 - set(rep.checks)) if rep else '?'}")
    check("B1.watered_really_happened", bool(rep and rep.ok_steps > 0), brief_day(rep))
    # 延后格不进任何 stage ⇒ 既不计 assigned_undone 也不计 plot_pending（"没被分派"而不是"被豁免"）
    check("B1.deferred_not_in_accounting",
          bool(rep and rep.assigned_undone == 0 and rep.deferred_tiles == 0 and rep.plot_pending == 0),
          f"assigned_undone={None if rep is None else rep.assigned_undone} "
          f"deferred_tiles={None if rep is None else rep.deferred_tiles} "
          f"plot_pending={None if rep is None else rep.plot_pending}")
    # 延后必须在 day_end 快照 + journal 两处可见
    snap_dt = ((getattr(rep, "stamina_budget", None) or {}).get("deferred_tiles") or {})
    jrn = {e.get("task"): e.get("count") for e in dep_t}
    check("B1.deferred_visible_snapshot_and_journal", bool(snap_dt) and snap_dt == jrn,
          f"snapshot={snap_dt} journal={jrn}")
    # 非空转：抹掉当天记录的延后，守卫必须重新抱怨 ⇒ 守卫沉默确实来自延后
    if HAS163:
        keep = dict(run.budget_today)
        run.budget_today = {}
        words = " ".join(run.work_reasons(w.obs()))
        run.budget_today = keep
        check("B1.guard_silence_comes_from_deferral",
              ("耕地空着" in words) or ("清/开/种" in words),
              f"cleared_budget_reasons={words[:220]}")


@case
def b2_one_unwatered_crop_must_stay_red():
    w, dry = overload_world(far_watered=5, dry_near=2, empty_near=0, world_cls=BlockedWaterWorld)
    stuck_tile = dry[0]
    w.blocked = {stuck_tile}
    run, code, _ = run_day(w, name="b2")
    rep = run.days[-1] if run.days else None
    note("B2.facts", f"code={code} blocked={stuck_tile} {brief_day(rep)}")
    check("B2.verified_false", bool(rep and rep.verified is False), brief_day(rep))
    check("B2.crops_watered_false", bool(rep and rep.checks.get("crops_watered") is False), brief_day(rep))
    check("B2.watered_outdoor_false", bool(rep and rep.checks.get("watered_outdoor") is False), brief_day(rep))
    check("B2.no_unmet_false", bool(rep and rep.checks.get("no_unmet_stages") is False), brief_day(rep))


@case
def b3_no_debt_no_deferral():
    w = TL.DryTilesWorld(weeds=10, seeds=20, money=0, water_left=40, stamina=200)
    w.player_tile = [62, 14]
    w.dirt = set(MICRO)
    w.crops = {}
    for t in list(WINDOW)[:5]:
        w.crops[t] = {"watered": True, "ripe": False, "dead": False}
    obs = w.obs()
    run = TL.make_run(w, target_days=1, max_days=1,
                      client_factory=lambda: TL.FakeClient(w),
                      worker_factory=lambda c: TL.FakeWorker(w, log=lambda *a: None),
                      journal_path=journal("b3direct"))
    budget = run._stamina_budget(obs)
    note("B3.budget", json.dumps({k: v for k, v in budget.items() if k != "deferred"}, ensure_ascii=False)[:300])
    reasons = {}
    for task in ("clear_area", "till_area", "plant_area"):
        try:
            reasons[task] = run._budget_defer_reason(task, obs)
        except Exception as exc:
            reasons[task] = f"<{type(exc).__name__}: {exc}>"
    check("B3.no_defer_without_debt", all(v == "" for v in reasons.values()), f"reasons={reasons}")
    run2, code, _ = run_day(w, name="b3")
    rep = run2.days[-1] if run2.days else None
    dep = events(run2, "deferred_by_budget")
    note("B3.facts", f"code={code} {brief_day(rep)} deferred={len(dep)} events={ev_names(run2)}")
    check("B3.no_deferral_events", not dep, f"deferred_by_budget={len(dep)}")
    check("B3.still_works", bool(rep and rep.ok_steps > 0), brief_day(rep))


# --------------------------------------------------------------------------- C 段
@case
def c1_fake_deferral_without_debt():
    w = TL.FakeWorld(weeds=10, seeds=0, money=0, water_left=40, stamina=5)
    w.player_tile = [62, 14]
    w.dirt = set(MICRO)
    w.crops = {}
    obs = w.obs()
    run = TL.make_run(w, target_days=1, max_days=1,
                      client_factory=lambda: TL.FakeClient(w),
                      worker_factory=lambda c: TL.FakeWorker(w, log=lambda *a: None),
                      journal_path=journal("c1"))
    run.budget_today = run._stamina_budget(obs)
    note("C1.budget", json.dumps({k: v for k, v in run.budget_today.items() if k != "deferred"}, ensure_ascii=False)[:300])
    before = dict(getattr(run, "budget_deferred_tiles", {}) or {})
    if HAS163:
        run._note_budget_deferrals(obs)
    after = dict(getattr(run, "budget_deferred_tiles", {}) or {})
    dep_keys = sorted(str(t) for t in (run.budget_today.get("deferred") or []))
    check("C1.no_deferral_recorded", not dep_keys and after == before and not after,
          f"deferred={dep_keys} tiles_before={before} tiles_after={after} "
          f"basis={run.budget_today.get('basis')} stam={run.budget_today.get('stamina')} "
          f"reserve={run.budget_today.get('water_reserve')}")


@case
def c2_list_vs_guard_consistency():
    w, dry = overload_world()
    run, code, _ = run_day(w, name="c2")
    rep = run.days[-1] if run.days else None
    deferred = sorted(run._budget_deferred_tasks()) if HAS163 else []
    tiles = sorted(run._budget_deferred_tile_set()) if HAS163 else []
    note("C2.facts", f"deferred={deferred} tiles={tiles[:6]} n_tiles={len(tiles)} {brief_day(rep)}")
    check("C2.deferred_tasks_recorded", bool(deferred), f"deferred={deferred}")
    if deferred:
        obs = w.obs()
        words = " ".join(run.work_reasons(obs))
        check("C2.guard_silent_for_deferred",
              not any(t in words for t in deferred),
              f"work_reasons={words[:200]}")
        pend = run._pending_work()
        check("C2.deferred_tiles_not_pending", all(t not in pend for t in tiles),
              f"pending={pend[:6]} n={len(pend)}")
    # 反向伪造：只有 tiles、没有 deferred_by_budget ⇒ 两套账不自洽（但不产生假绿）
    if HAS163:
        run.budget_today = {}
        run.budget_deferred_tiles = {"clear_area": [(62, 13)]}
        tset = run._budget_deferred_tile_set()
        ttask = run._budget_deferred_tasks()
        obs = w.obs()
        words = " ".join(run.work_reasons(obs))
        check("C2.tiles_only_forge_is_inert",
              tset == {(62, 13)} and ttask == set(),
              f"tile_set={sorted(tset)} tasks={sorted(ttask)} guard_words={words[:120]}")


@case
def c3_accounting_not_subtracted():
    w, dry = overload_world()
    run, code, _ = run_day(w, name="c3")
    rep = run.days[-1] if run.days else None
    dep = events(run, "deferred_by_budget")
    dep_t = events(run, "budget_deferred_tiles")
    stages = [s.get("stage") for s in (rep.stages if rep else [])]
    note("C3.facts", f"{brief_day(rep)} deferred_ev={len(dep)} tile_ev={len(dep_t)} "
                     f"stage_names={stages} budget={json.dumps({k: v for k, v in (getattr(rep, 'stamina_budget', {}) or {}).items() if k in ('deferred_tiles','capped_by_capacity','capacity_capped_tasks')}, ensure_ascii=False)}")
    check("C3.checks_keys_known", bool(rep and set(rep.checks) == KNOWN10),
          f"keys={sorted(rep.checks) if rep else '?'}")
    check("C3.deferred_tasks_have_no_stage", not any(s in ("clear_area", "till_area", "plant_area") for s in stages),
          f"stage_names={stages}")
    check("C3.deferral_not_subtracted",
          bool(rep and rep.assigned_undone == 0 and rep.plot_pending == 0),
          f"assigned_undone={None if rep is None else rep.assigned_undone} "
          f"plot_pending={None if rep is None else rep.plot_pending}"
          "（延后格不进 stage ⇒ 既不计 assigned_undone 也不计 plot_pending，属「未分派」）")
    if dep_t:
        counts = {e.get("task"): e.get("count") for e in dep_t}
        snap = (getattr(rep, "stamina_budget", {}) or {}).get("deferred_tiles")
        note("C3.journal_vs_snapshot", f"journal_counts={counts} snapshot={snap}")
        check("C3.journal_matches_snapshot", counts == snap, f"journal={counts} snapshot={snap}")


@case
def c4_water_harvest_dead_never_deferred():
    w, dry = overload_world(far_watered=140, dry_near=6, empty_near=2)
    w.crops[WINDOW[10]] = {"watered": True, "ripe": True, "dead": False}
    w.crops[WINDOW[11]] = {"watered": True, "ripe": False, "dead": True}
    obs = w.obs()
    run = TL.make_run(w, target_days=1, max_days=1,
                      client_factory=lambda: TL.FakeClient(w),
                      worker_factory=lambda c: TL.FakeWorker(w, log=lambda *a: None),
                      journal_path=journal("c4direct"))
    run.budget_today = run._stamina_budget(obs)
    reasons = {task: run._budget_defer_reason(task, obs)
               for task in ("water_area", "water_far", "harvest", "clear_dead")}
    check("C4.protected_tasks_never_deferred", all(v == "" for v in reasons.values()), f"reasons={reasons}")
    deferred = sorted(run._budget_deferred_tasks()) if HAS163 else []
    check("C4.deferred_excludes_protected",
          not any(t in deferred for t in ("harvest", "clear_dead", "water_area", "water_far")),
          f"deferred={deferred}")
    w2, _ = overload_world(far_watered=140, dry_near=6, empty_near=2)
    w2.crops[WINDOW[10]] = {"watered": True, "ripe": True, "dead": False}
    w2.crops[WINDOW[11]] = {"watered": True, "ripe": False, "dead": True}
    run2, code, _ = run_day(w2, name="c4")
    rep = run2.days[-1] if run2.days else None
    names = [s.get("stage") for s in (rep.stages if rep else [])]
    note("C4.facts", f"code={code} stages={names} {brief_day(rep)}")
    check("C4.harvest_and_dead_still_ran",
          "harvest" in names and "clear_dead" in names, f"stages={names}")


@case
def c5_capacity_journal_matches_limit():
    w = TL.DryTilesWorld(weeds=0, seeds=20, money=0, water_left=40, stamina=270)
    w.player_tile = [62, 14]
    w.dirt = set(MICRO)
    w.crops = {}
    for i in range(115):
        t = (100 + i, 50 + (i % 3))
        w.dirt.add(t)
        w.crops[t] = {"watered": True, "ripe": False, "dead": False}
    obs = w.obs()
    run = TL.make_run(w, target_days=1, max_days=1,
                      client_factory=lambda: TL.FakeClient(w),
                      worker_factory=lambda c: TL.FakeWorker(w, log=lambda *a: None),
                      journal_path=journal("c5direct"))
    budget = run._stamina_budget(obs)
    note("C5.budget", json.dumps({k: v for k, v in budget.items() if k != "deferred"}, ensure_ascii=False)[:300])
    run2, code, _ = run_day(w, name="c5")
    rep = run2.days[-1] if run2.days else None
    cap = events(run2, "stage_capped_by_capacity")
    plant_assigned = [int(s.get("assigned") or 0) for s in (rep.stages if rep else []) if s.get("stage") == "plant_area"]
    note("C5.facts", f"capacity={budget.get('capacity')} cap_events={[(e.get('task'), e.get('limit'), e.get('capacity')) for e in cap]} "
                     f"plant_assigned={plant_assigned} snap={json.dumps((getattr(rep, 'stamina_budget', {}) or {}).get('capped_by_capacity'), ensure_ascii=False)}")
    if int(budget.get("capacity") or 0) < 12:
        ok = bool(cap) and cap[0].get("task") == "plant_area" and int(cap[0].get("limit")) == 12
        check("C5.capacity_journal_fires", ok,
              f"cap={[(e.get('task'), e.get('limit'), e.get('capacity')) for e in cap]}")
        snap = (getattr(rep, "stamina_budget", {}) or {}).get("capped_by_capacity") or {}
        check("C5.snapshot_matches_journal",
              bool(cap) and snap.get("plant_area") == {"limit": int(cap[0].get("limit")), "capacity": int(cap[0].get("capacity"))},
              f"snapshot={snap} cap={[(e.get('task'), e.get('limit'), e.get('capacity')) for e in cap]}")
        check("C5.applied_limit_is_capacity",
              bool(plant_assigned) and max(plant_assigned) <= int(budget.get("capacity") or 0),
              f"plant_assigned={plant_assigned} capacity={budget.get('capacity')}")
    else:
        note("C5.probe_design", f"capacity={budget.get('capacity')} ≥12 ⇒ 本树未触发容量上限")


@case
def c6_boundedness_control():
    w, dry = overload_world()
    run, code, _ = run_day(w, name="c6")
    rep = run.days[-1] if run.days else None
    burst = events(run, "plot_exhausted_burst")
    noprog = events(run, "no_progress_burst")
    flush = [e for e in run.entries if str(e.get("event", "")).startswith("stuck_flush")]
    check("C6.fixed_day_bounded", not burst and not noprog and not flush and len(run.days) == 1,
          f"burst={len(burst)} no_progress={len(noprog)} flush={len(flush)} days={len(run.days)}")
    if HAS163:
        w2, _ = overload_world()
        run2, code2, _ = run_day(w2, name="c6ctrl", patch=lambda r: setattr(r, "_budget_deferred_tasks", lambda: set()))
        rep2 = run2.days[-1] if run2.days else None
        burst2 = events(run2, "plot_exhausted_burst")
        note("C6.control_facts", f"code={code2} burst={len(burst2)} {brief_day(rep2)}")
        check("C6.control_still_bounded_and_red",
              len(burst2) <= 2 and code2 != 0 and bool(rep2 and rep2.verified is False),
              f"burst={len(burst2)} code={code2} verified={None if rep2 is None else rep2.verified}")


@case
def c7_no_farm_evidence_never_green():
    w = TL.FakeWorld(weeds=0, seeds=20, money=0, water_left=40, stamina=200)
    w.player_tile = [62, 14]
    w.dirt = set(MICRO)
    w.crops = {WINDOW[0]: {"watered": False, "ripe": False, "dead": False},
               WINDOW[1]: {"watered": False, "ripe": False, "dead": False}}
    w.farm = None
    run, code, _ = run_day(w, name="c7")
    rep = run.days[-1] if run.days else None
    names = ev_names(run)
    note("C7.facts", f"code={code} {brief_day(rep)} events={names}")
    check("C7.not_green_without_farm_evidence", bool(rep and rep.verified is False), brief_day(rep))
    check("C7.evidence_journal_present", "farm_evidence_unavailable" in names, f"events={names}")


@case
def c8_tool_audit_of_deferral():
    path = JDIR / f"{TAG}_b1.jsonl"
    if not path.exists():
        check("C8.ledger_exists", False, f"{path} 不存在（B1 没跑成）")
        return
    rc, verdict, _ = tool_run(path)
    note("C8.real_ledger", f"rc={rc} verdict={verdict} path={path.name}")
    check("C8.real_deferred_day_is_green", rc == 0 and verdict == "VERIFIED", f"rc={rc} verdict={verdict}")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("event") in ("deferred_by_budget", "budget_deferred_tiles"):
            continue
        if obj.get("event") == "day_end":
            sb = obj.get("stamina_budget")
            if isinstance(sb, dict):
                sb.pop("deferred_by_budget", None)
                sb.pop("deferred_tiles", None)
        rows.append(json.dumps(obj, ensure_ascii=False))
    stripped = JDIR / f"{TAG}_b1_stripped.jsonl"
    stripped.write_text("\n".join(rows) + "\n", encoding="utf-8")
    rc2, v2, _ = tool_run(stripped)
    note("C8.stripped_traces", f"rc={rc2} verdict={v2}（抹掉延后留痕后工具的判决）")
    check("C8.tool_cannot_audit_deferral_traces", rc2 == 0 and v2 == "VERIFIED",
          f"rc={rc2} verdict={v2} ⇒ 工具不核 stamina_budget.deferred_by_budget/budget_deferred_tiles")


def main() -> int:
    print(f"== task-166 probe == TREE={TAG} HAS163={HAS163} root={ROOT}")
    for fn in (b1_overload_day_must_go_green, b2_one_unwatered_crop_must_stay_red,
               b3_no_debt_no_deferral, c1_fake_deferral_without_debt,
               c2_list_vs_guard_consistency, c3_accounting_not_subtracted,
               c4_water_harvest_dead_never_deferred, c5_capacity_journal_matches_limit,
               c6_boundedness_control, c7_no_farm_evidence_never_green,
               c8_tool_audit_of_deferral):
        fn()
    passed = sum(1 for r in RES if r["ok"] is True)
    failed = sum(1 for r in RES if r["ok"] is False)
    print(f"== {TAG}: {passed} PASS / {failed} FAIL (checks) + {sum(1 for r in RES if r['ok'] is None)} notes ==")
    out = pathlib.Path(__file__).resolve().parent / f"_t166_{TAG}.json"
    out.write_text(json.dumps({"tree": TAG, "has163": HAS163, "passed": passed,
                               "failed": failed, "results": RES}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"summary -> {out}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
