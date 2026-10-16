"""task-150 对抗验收探针：task-149（farm 级耕地理由 + 日初重试 + 0 动作日闸门）。

用法（`T150_ROOT` 切树）：
  $env:T150_ROOT = "<repo>\\scratch\\_t150_pre149"    # pre-149 基线（应看到 fail-open）
  $env:T150_ROOT = "<repo>"                           # post-149（工作树 == 928d3d2）
  python scratch\\_t150_probe.py

复刻 run9c summer 20 现场：雨天清晨人在 FarmHouse（室内、窗口里没有一格农场）、
farm 块自述 `dry/ripe/dead = 0` 但**有耕地空着**、手上有种子，日初 `goto_farm` 被
`ShippingMenu` 挡成 `ui_modal` —— 真实现场里 `_location_failed` 写的是
`code="failed"` + `env_block=True`（`status` 才是 `ui_modal`），本探针逐字复刻。

B 段：B1 = 该日不许 `no_work`+VERIFIED（pre 应 FAIL、post 应 PASS），B2 = 真没活的正对照。
C 段：C1 字段缺失 fail-closed / C2 字段说谎 / C3 重试有界 / C4 跨天有界 / C5 体力诚实收工 /
      C6 够不着的空地不许空转（有界）/ C7 0 动作 VERIFIED 的独立证据交叉核对。
"""
import json
import os
import sys

ROOT = os.environ.get("T150_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (ROOT, os.path.join(ROOT, "brain"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import test_longrun as TL  # noqa: E402

FakeWorld = TL.FakeWorld
FakeWorker = TL.FakeWorker
StepResult = TL.StepResult
make_run = TL.make_run

RESULTS = []
DIAG = os.environ.get("T150_DIAG") == "1"


def check(tag, ok, detail=""):
    RESULTS.append((tag, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {tag}" + (f" :: {detail}" if detail else ""))
    return bool(ok)


def events(run, name):
    return [e for e in run.entries if e.get("event") == name]


def mk_world(cls=None, *, farm=None, **kw):
    """`farm=` 不是所有版本 `FakeWorld.__init__` 的参数（task-96 前是属性）⇒ 构造后赋值。"""
    w = (cls or FakeWorld)(**kw)
    w.farm = dict(farm) if farm is not None else None
    return w


RAIN_FARM = {
    "loaded": True, "complete": True, "crops": 5, "dryCrops": 0, "dryDeadCrops": 0,
    "deadCrops": 0, "unwateredCrops": 0, "ripeCrops": 0,
    "hoeDirt": 8, "emptyDirt": 3, "dryTiles": [], "dryTilesTruncated": False,
}
ZERO_FARM = {
    "loaded": True, "complete": True, "crops": 0, "dryCrops": 0, "dryDeadCrops": 0,
    "deadCrops": 0, "unwateredCrops": 0, "ripeCrops": 0,
    "hoeDirt": 0, "emptyDirt": 0, "dryTiles": [], "dryTilesTruncated": False,
}
OLD_MOD_FARM = {
    "loaded": True, "complete": True, "crops": 5, "dryCrops": 0, "deadCrops": 0,
    "unwateredCrops": 0, "ripeCrops": 0, "dryTiles": [], "dryTilesTruncated": False,
}
UNREACHABLE_DIRT_FARM = dict(RAIN_FARM, emptyDirt=5)


class IndoorWindowWorld(FakeWorld):
    """室内窗口看不见任何农场格（真机行为）⇒ 工作理由只能来自 farm 块。"""

    def obs(self):
        o = super().obs()
        if not self.is_outdoor_farm:
            loc = o["location"]
            loc["tillable"] = []
            loc["tiles"] = []
        return o


class StuckIndoorsWorker(FakeWorker):
    """日初 `goto_farm` 被 ShippingMenu 挡掉 —— 复刻 `_location_failed` 的真实形状。"""

    def __init__(self, world, *, fail_from=2):
        super().__init__(world, log=lambda *_: None)
        self.ensure_calls = 0
        self.fail_from = int(fail_from)

    def ensure_location(self, name, *, tile=None, timeout_ms=60000):
        self.ensure_calls += 1
        r = StepResult("move_to_location", tile=tile)
        if self.ensure_calls < self.fail_from:
            r.ok, r.code, r.reason = True, "ok", f"已经在 {name}"
            return r
        r.ok = False
        r.code = "failed"                      # farmwork._location_failed:1521 的真实写法
        r.status = "ui_modal"
        r.env_block = True                     # _mark_status(r, _exc_status(exc)):1537
        r.receipt = "ui_modal"
        r.reason = ("去 Farm 失败：[ui_modal] 有菜单/对话挡着（'ShippingMenu'），所有技能都会被拒；"
                    "脑侧现场：人在 (9, 9)（FarmHouse）")
        return r


class ReturnFarmWorker(FakeWorker):
    """日初回农场真的成功（正对照用）。"""

    def ensure_location(self, name, *, tile=None, timeout_ms=60000):
        self.w.location = "Farm"
        self.w.is_outdoor_farm = True
        self.w.player_tile = [62, 14]
        r = StepResult("move_to_location", tile=tile)
        r.ok, r.code, r.reason = True, "ok", f"已到 {name}"
        return r


class FlakyEnsureWorker(FakeWorker):
    """call #1（预备）回 ok 但**不挪世界**（人还在室内）；日初那次被模态挡住；重试那次成功回农场。"""

    def __init__(self, world):
        super().__init__(world, log=lambda *_: None)
        self.ensure_calls = 0

    def ensure_location(self, name, *, tile=None, timeout_ms=60000):
        self.ensure_calls += 1
        r = StepResult("move_to_location", tile=tile)
        if self.ensure_calls == 1:
            r.ok, r.code, r.reason = True, "ok", f"已经在 {name}"
            return r
        if self.ensure_calls == 2:
            r.ok = False
            r.code = "failed"
            r.status = "ui_modal"
            r.env_block = True
            r.receipt = "ui_modal"
            r.reason = "去 Farm 失败：[ui_modal] 有菜单/对话挡着（'ShippingMenu'），所有技能都会被拒"
            return r
        self.w.location = "Farm"
        self.w.is_outdoor_farm = True
        self.w.player_tile = [62, 14]
        r.ok, r.code, r.reason = True, "ok", f"已到 {name}"
        return r


def indoor_world(*, farm, seeds=2, money=465, water_left=40, stamina=270.0):
    w = mk_world(IndoorWindowWorld, farm=farm, weeds=0, seeds=seeds, money=money,
                 water_left=water_left, stamina=stamina)
    w.location = "FarmHouse"
    w.is_outdoor_farm = False
    w.player_tile = [9, 9]
    w.weather = "lightning"
    w.dirt = set()
    w.tillable = set()
    w.weeds = 0
    w.crops = {}
    return w


def run_day(w, worker, *, max_days=1, journal_path=None):
    run = make_run(w, target_days=1, max_days=max_days,
                   client_factory=lambda: TL.FakeClient(w), worker_factory=lambda c: worker,
                   sleep_fn=lambda _s: None, supervise_every=0, llm_enabled=False,
                   journal_path=journal_path)
    run.worker = worker
    run.client = TL.FakeClient(w)
    run.plot_size = 5
    code = run.run()
    return run, code


def last_day(run):
    return run.days[-1] if run.days else None


def fixt(run):
    """日志。"""
    for r in run.days:
        print(f"      [diag] day {r.day_key} ended_by={r.ended_by!r} reason={str(r.ended_reason)[:110]!r} "
              f"ok_steps={r.ok_steps} verified={r.verified} checks.no_unmet={r.checks.get('no_unmet_stages')} "
              f"zero_ev={r.checks.get('zero_action_evidenced')!r}")
    if DIAG:
        print("      [diag] events: " + ", ".join(
            f"{e.get('event')}{'(' + str(e.get('where')) + ')' if e.get('where') else ''}"
            for e in run.entries[:60]))


# ------------------------------------------------------------------ B 段
def b1_rain_indoor_fail_open():
    w = indoor_world(farm=RAIN_FARM)
    worker = StuckIndoorsWorker(w, fail_from=2)
    run, code = run_day(w, worker)
    fixt(run)
    rep = last_day(run)
    gf = events(run, "goto_farm")
    retry = [e for e in gf if e.get("where") == "day_start_retry"]
    if rep is None:
        return check("B1 雨天室内 fail-open（run9c summer 20 形态）", False, "没有当日报告"), ""
    reason = str(rep.ended_reason or "")
    no_work = reason.startswith("no_work")
    detail = (f"ended_by={rep.ended_by!r} no_work={no_work} verified={rep.verified} ok_steps={rep.ok_steps} "
              f"rc={code} goto_farm={len(gf)} retry={len(retry)} ensure_calls={worker.ensure_calls}")
    ok = (not no_work) and (rep.verified is False) and bool(retry)
    return check("B1 雨天室内：不许 no_work 收尾 + verified=False + 真的重试过一次", ok, detail), detail


def b2_positive_truly_no_work():
    w = indoor_world(farm=ZERO_FARM, seeds=0, money=0)
    worker = ReturnFarmWorker(w, log=lambda *_: None)
    run, code = run_day(w, worker)
    fixt(run)
    rep = last_day(run)
    if rep is None:
        return check("B2 正对照：真没活 ⇒ 允许 no_work + VERIFIED", False, "没有当日报告"), ""
    reason = str(rep.ended_reason or "")
    detail = (f"ended_by={rep.ended_by!r} reason={reason[:40]!r} verified={rep.verified} "
              f"ok_steps={rep.ok_steps} rc={code} zero_ev={rep.checks.get('zero_action_evidenced')}")
    ok = (rep.verified is True) and rep.ended_by == "sleep" and reason.startswith("no_work")
    return check("B2 正对照：真没活 ⇒ 允许 no_work + VERIFIED", ok, detail), detail


# ------------------------------------------------------------------ C 段
def c1_fields_missing():
    w = indoor_world(farm=OLD_MOD_FARM)
    worker = StuckIndoorsWorker(w, fail_from=2)
    run, code = run_day(w, worker)
    fixt(run)
    rep = last_day(run)
    if rep is None:
        return check("C1 farm 字段缺失（旧 Mod）⇒ fail-closed", False, "没有当日报告"), ""
    reason = str(rep.ended_reason or "")
    detail = (f"ended_by={rep.ended_by!r} no_work={reason.startswith('no_work')} "
              f"verified={rep.verified} ok_steps={rep.ok_steps} rc={code}")
    ok = (rep.verified is False) and not reason.startswith("no_work")
    return check("C1 farm 字段缺失（旧 Mod）⇒ fail-closed（不许当选 0）", ok, detail), detail


def c2_fields_lie():
    """农场块谎报 hoeDirt/emptyDirt=0，而窗口里其实有可锄/空地 ⇒ 不许靠自述 VERIFIED。"""
    w = mk_world(IndoorWindowWorld, farm=ZERO_FARM, weeds=4, seeds=2, money=465, water_left=40)
    w.location = "Farm"
    w.is_outdoor_farm = True
    worker = ReturnFarmWorker(w, log=lambda *_: None)
    run, code = run_day(w, worker)
    fixt(run)
    rep = last_day(run)
    if rep is None:
        return check("C2 farm 字段说谎（0 但窗口有活）", False, "没有当日报告"), ""
    detail = (f"ended_by={rep.ended_by!r} verified={rep.verified} ok_steps={rep.ok_steps} "
              f"stages={[s.get('stage') for s in rep.stages]}")
    ok = (int(rep.ok_steps or 0) > 0) or (rep.verified is False)
    return check("C2 farm 字段说谎（0 但窗口有活）⇒ 干活或至少不 VERIFIED", ok, detail), detail


def c3_retry_bounded():
    w = indoor_world(farm=RAIN_FARM)
    worker = StuckIndoorsWorker(w, fail_from=2)
    run, code = run_day(w, worker)
    gf = events(run, "goto_farm")
    retry = [e for e in gf if e.get("where") == "day_start_retry"]
    detail = (f"ensure_calls={worker.ensure_calls}（=1 预备 + 日初）goto_farm={len(gf)} retry={len(retry)}")
    ok = (worker.ensure_calls <= 4) and (len(retry) <= 1) and (len([e for e in gf if e.get("where") == "day_start"]) <= 1)
    return check("C3 日初重试有界（≤1 次、不重复轰炸）", ok, detail), detail


def c4_bounded_across_days():
    w = indoor_world(farm=RAIN_FARM)
    worker = StuckIndoorsWorker(w, fail_from=2)
    run, code = run_day(w, worker, max_days=3)
    fixt(run)
    bad = [r for r in run.days if int(r.ok_steps or 0) == 0 and r.verified is True]
    detail = (f"days={len(run.days)} rc={code} ensure_calls={worker.ensure_calls} "
              f"0动作却VERIFIED={len(bad)} ended_by={[r.ended_by for r in run.days]}")
    ok = (not bad) and code == 1
    return check("C4 一直回不去：0 动作日绝不许 VERIFIED、跑批有界收尾", ok, detail), detail


def c5_stamina_honesty():
    """体力收工不被新理由顶成硬 stuck（`sleep_guard` 里 stamina 在 farm 理由之前）。"""
    w = indoor_world(farm=RAIN_FARM, stamina=8.0)
    worker = ReturnFarmWorker(w, log=lambda *_: None)
    run, code = run_day(w, worker)
    fixt(run)
    rep = last_day(run)
    if rep is None:
        return check("C5 体力收工（stamina）不被新理由顶成硬 stuck", False, "没有当日报告"), ""
    detail = (f"ended_by={rep.ended_by!r} reason={str(rep.ended_reason)[:50]!r} verified={rep.verified}")
    ok = rep.ended_by in ("sleep", "slept_without_work") and str(rep.ended_reason or "").startswith("stamina")
    return check("C5 体力收工（stamina）不被新理由顶成硬 stuck", ok, detail), detail


def c6_unreachable_plot_work_bounded():
    """农场说有 5 格空地 + 手上有种子，但那些格在窗口外、也回不去 ⇒ 必须有界、不许空转。"""
    w = indoor_world(farm=UNREACHABLE_DIRT_FARM)
    worker = StuckIndoorsWorker(w, fail_from=2)
    run, code = run_day(w, worker)
    fixt(run)
    rep = last_day(run)
    if rep is None:
        return check("C6 够不着的空地：有界、不许空转", False, "没有当日报告"), ""
    rounds = len(events(run, "decision"))
    detail = (f"ended_by={rep.ended_by!r} decision轮数={rounds} ok_steps={rep.ok_steps} "
              f"verified={rep.verified} rc={code} stuck_flush={len(events(run, 'stuck_flush'))}")
    ok = rounds <= 40 and (rep.verified is False) and rep.ended_by not in ("", None)
    return check("C6 够不着的空地：有界收尾、不许空转、不许 VERIFIED", ok, detail), detail


def vr_module():
    """加载 `tools/verify-run3.py`（只读，用来做独立闸门的交叉核对）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("vr150", os.path.join(ROOT, "tools", "verify-run3.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_ledger(rows, name):
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def c8_tool_cross_check():
    """与 `tools/verify-run3.py` 的**独立**在场证据闸门交叉核对。

    拿 post 树真跑出来的一天账本（0 动作 + `slept_without_work`）伪造成"绿"：
    (a) 抹掉全部在场证据/失败痕迹、把 `verified` 说成 true、理由写 `no_work` ⇒ 工具**必须判红**；
    (b) 同一条假账本只补一条成功的 `goto_farm` ⇒ 工具**不该**再报"没有在场证据"。
    """
    jp = os.path.join(HERE, "_t150_c8_raw.jsonl")
    try:
        os.remove(jp)                     # 账本是追加写的：每次跑前先清，免得跨次累积
    except OSError:
        pass
    w = indoor_world(farm=RAIN_FARM)
    worker = StuckIndoorsWorker(w, fail_from=2)
    run, code = run_day(w, worker, journal_path=jp)
    try:
        rows = [json.loads(l) for l in open(jp, encoding="utf-8") if l.strip()]
    except OSError as exc:
        return check("C8 工具独立闸门交叉核对", False, f"读不到账本：{exc}"), ""
    drop = {"goto_farm", "slept_without_work", "stage_shortfall", "plot", "work_spot",
            "work_spot_resume", "resume_walk", "water_far", "water_far_skipped", "farm_evidence_unavailable",
            "idle", "decision", "review", "intent_verdict", "outcome", "stage_stopped"}
    all_true = {k: True for k in ("slept_by_us", "no_blocking_modal", "no_hard_failures",
                                  "unreachable_within_bound", "refused_within_bound", "no_unmet_stages",
                                  "crops_watered", "watered_outdoor", "day_justified")}
    base, signals = [], []
    for r in rows:
        ev = r.get("event")
        if ev in drop:
            if ev == "goto_farm":
                signals.append({"event": "goto_farm", "t": float(r.get("t") or 0) + 0.5, "ok": True,
                                "where": "day_start_retry", "code": "ok", "reason": "已到 Farm"})
            continue
        r = dict(r)
        if ev == "day_end":
            r["verified"] = True
            r["ok_steps"] = 0
            r["stages"] = []
            r["ended_by"] = "sleep"
            r["ended_reason"] = "no_work:确实找不到可做的活（地里的活干完了、也没法/没必要买种子）"
            r["checks"] = dict(all_true)
        if ev == "finish":
            r["code"] = 0
            r["verified_streak"] = 1
        base.append(r)
    no_idx = next((i for i, r in enumerate(base) if r.get("event") == "day_end"), len(base))
    p_no = write_ledger(base, "_t150_c8_no_evidence.jsonl")
    p_sig = write_ledger(base[:no_idx] + signals + base[no_idx:], "_t150_c8_with_signal.jsonl")
    try:
        vr = vr_module()
        _ok1, s1 = vr.report(vr.load(p_no), target_days=1)
        _ok2, s2 = vr.report(vr.load(p_sig), target_days=1)
    except Exception as exc:                      # noqa: BLE001
        return check("C8 工具独立闸门交叉核对", False, f"工具调用异常：{type(exc).__name__}: {exc}"), ""
    key = "没有任何户外农场的在场证据"
    hit1 = [p for p in s1.get("problems", []) if key in p]
    hit2 = [p for p in s2.get("problems", []) if key in p]
    detail = (f"(a) 抹证据 ⇒ 命中「{key}」{len(hit1)} 条（verdict={s1.get('verdict')}）；"
              f"(b) 补成功 goto_farm ⇒ 命中 {len(hit2)} 条（verdict={s2.get('verdict')}）")
    ok = bool(hit1) and not hit2
    return check("C8 工具独立闸门：抹掉在场证据 ⇒ 判红；补一条成功 goto_farm ⇒ 不再报", ok, detail), detail


def c9_retry_success_then_works():
    """B 段第二形态：日初被模态挡住、清框后重试**成功** ⇒ 当天照常干活、可以 VERIFIED。"""
    w = mk_world(IndoorWindowWorld, farm=ZERO_FARM, weeds=4, seeds=2, money=465, water_left=40)
    w.location = "FarmHouse"
    w.is_outdoor_farm = False
    w.player_tile = [9, 9]
    w.weather = "lightning"
    worker = FlakyEnsureWorker(w)
    run, code = run_day(w, worker)
    fixt(run)
    rep = last_day(run)
    gf = events(run, "goto_farm")
    retry = [e for e in gf if e.get("where") == "day_start_retry"]
    if rep is None:
        return check("C9 重试成功 ⇒ 当天照常干活", False, "没有当日报告"), ""
    detail = (f"retry={len(retry)} ok={[e.get('ok') for e in retry]} ensure_calls={worker.ensure_calls} "
              f"ok_steps={rep.ok_steps} verified={rep.verified} rc={code} ended_by={rep.ended_by!r}")
    ok = bool(retry) and retry[-1].get("ok") is True and int(rep.ok_steps or 0) > 0 and rep.verified is True
    return check("C9 重试成功 ⇒ 当天照常干活、可 VERIFIED", ok, detail), detail


def c7_zero_action_independent_evidence():
    """0 动作 + VERIFIED 的日子，必须同时有 (a) `zero_action_evidenced` 为真、(b) 当天独立在场证据。

    (b) 与 `tools/verify-run3.py` 的独立闸门口径对齐（成功 `goto_farm` / 农场动作类事件）。
    """
    on_farm_events = {"plot", "work_spot", "water_far", "tool_refused", "unreachable",
                      "refuse", "goto_farm", "stage_shortfall"}
    w = indoor_world(farm=RAIN_FARM)
    worker = StuckIndoorsWorker(w, fail_from=2)
    run, code = run_day(w, worker)
    rep = last_day(run)
    w2 = indoor_world(farm=ZERO_FARM, seeds=0, money=0)
    run2, code2 = run_day(w2, ReturnFarmWorker(w2, log=lambda *_: None))
    rep2 = last_day(run2)
    bad = []
    for r, rr in ((run, rep), (run2, rep2)):
        if r is None or rr is None:
            continue
        if rr.verified is True and int(rr.ok_steps or 0) == 0:
            ev = {e.get("event") for e in r.entries}
            has_indep = bool(ev & on_farm_events) or any(
                e.get("event") == "goto_farm" and e.get("ok") for e in r.entries)
            if not (rr.checks.get("zero_action_evidenced") and has_indep):
                bad.append((str(rr.day_key), rr.checks.get("zero_action_evidenced"), sorted(ev & on_farm_events)))
    detail = f"0动作VERIFIED的日={bad or '无'}"
    return check("C7 0 动作 VERIFIED：自述证据 + 独立在场证据都要有", not bad, detail), detail


def main():
    print(f"=== tree: {ROOT} ===")
    print(f"=== longrun blob: {os.path.getsize(os.path.join(ROOT, 'brain', 'agentfarm', 'longrun.py'))} B ===")
    b1_rain_indoor_fail_open()
    b2_positive_truly_no_work()
    c1_fields_missing()
    c2_fields_lie()
    c3_retry_bounded()
    c4_bounded_across_days()
    c5_stamina_honesty()
    c6_unreachable_plot_work_bounded()
    c7_zero_action_independent_evidence()
    c8_tool_cross_check()
    c9_retry_success_then_works()
    npass = sum(1 for _t, ok, _d in RESULTS if ok)
    print(f"\n=== {npass}/{len(RESULTS)} PASS ===")
    for tag, ok, detail in RESULTS:
        if not ok:
            print(f"  FAIL {tag} :: {detail}")
    return 0 if npass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
