# -*- coding: utf-8 -*-
r"""task-125 探针：0.7.29 批次（task-121 复盘预算 / task-122 教训覆盖 / task-124 review-only 兜底）。

用法：
    $env:PYTHONUTF8="1"; python scratch/_t125_probe.py                        # post 树（仓库根）
    $env:T125_ROOT="$PWD\scratch\_t125_pre"; python scratch/_t125_probe.py     # pre 树（FAIL→PASS 对照）

只读生产代码；产物只写 stdout / scratch/。判定口径见 docs/_review-0.7.29.md。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("T125_ROOT") or Path(__file__).resolve().parents[1])
for _p in (ROOT / "tests", ROOT / "brain", str(ROOT)):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import test_longrun as TL  # noqa: E402
from agentfarm import farmwork as FW  # noqa: E402
from agentfarm import planner as P  # noqa: E402

REVIEW_SIG = "收工复盘助手"
RESULTS: list[tuple[str, bool, str]] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((tag, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {tag}" + (f" :: {detail}" if detail else ""))


def ev(run, name):
    return [e for e in run.entries if e.get("event") == name]


def canon(run):
    out = []
    for d in run.days:
        fw = dict(d.final_water or {})
        fw.pop("t", None)
        out.append({
            "verified": bool(d.verified),
            "day_justified": bool((d.checks or {}).get("day_justified")),
            "ended_by": d.ended_by,
            "checks": dict(d.checks or {}),
            "final_water": fw,
            "final": dict(d.final or {}),
            "stages": [dict(s) for s in (d.stages or [])],
            "intents": [e.get("intents") for e in run.entries if e.get("event") == "decision"],
        })
    return out


class Client(TL.FakeClient):
    """补上 `buy`/`sell`（`FakeClient` 没有，真 `FarmWorker` 会调）。"""

    def __init__(self, world, *, offers=None):
        super().__init__(world)
        self.offers = list(offers or [])

    def buy(self, item, count, *, shop=None, timeout_ms=None, **kw):
        price = int(getattr(self.w, "buy_price", 0) or 0)
        self.w.buys.append({"item": item, "count": count, "shop": shop, "price": price})
        return {"status": "", "availableItems": list(self.offers), "item": item,
                "count": count, "price": price, "reason": "假客户端：只记不发"}

    def sell(self, slot, *, whitelist=None, timeout_ms=None, **kw):
        return {"status": "ok", "slot": slot, "whitelist": list(whitelist or []),
                "reason": "假客户端：只记不发"}


class Chat:
    """假 LLM：`script` 逐次指定复盘行为（notes/truncated/network/empty/garbage）。"""

    def __init__(self, script=None, notes=("先把水壶补满",)):
        self.script = list(script or [])
        self.notes = list(notes)
        self.review_calls = 0
        self.budgets: list = []

    def __call__(self, messages, **kwargs):
        text = "".join(str(m.get("content", "")) for m in messages)
        if REVIEW_SIG in text:
            self.review_calls += 1
            self.budgets.append(kwargs.get("max_tokens"))
            act = self.script.pop(0) if self.script else "notes"
            if act == "truncated":
                raise TL.LlmError("截断且内容为空", status="truncated")
            if act == "network":
                raise TL.LlmError("网络异常", status="network")
            if act == "empty":
                return json.dumps({"notes": []}, ensure_ascii=False)
            if act == "garbage":
                return "{这不是 JSON"
            return json.dumps({"notes": self.notes}, ensure_ascii=False)
        return json.dumps({"tasks": [{"task": "water_area", "area_hint": "tiles.unwatered_crops",
                                      "reason": "浇水", "expected_evidence": "下降"}]},
                          ensure_ascii=False)


def make(w, *, planner=None, offers=None, **kw):
    client = Client(w, offers=offers)
    worker = TL.FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
    kw.setdefault("client_factory", lambda: client)
    kw.setdefault("worker_factory", lambda c: worker)
    if planner is not None:
        kw["planner"] = planner
    run = TL.make_run(w, **kw)
    run.worker = worker
    run.client = client
    return run


def plot_of(tiles):
    return {"zone": "", "label": "", "anchor": [tiles[0][0], tiles[0][1]],
            "tiles": list(tiles), "note": ""}


REVIEW_PLANNER = lambda: TL.FakePlanner(  # noqa: E731
    TL.TaskIntent("review", "anchor:current_location", "复盘"))


# ---------------------------------------------------------------- B 段：FAIL→PASS
def b1a() -> None:
    """B-① 政策层能落地时的分工：观测里看得见的活 ⇒ 政策层直接换成真意图（不必兜底）。"""
    w = TL.FakeWorld(weeds=0, seeds=10, money=500)
    w.tillable = set()
    w.dirt.add((70, 20))
    w.crops[(70, 20)] = {"ripe": False, "watered": False}
    run = make(w, target_days=1, max_days=1, planner=REVIEW_PLANNER())
    run._ensure_plot = lambda obs, rep: plot_of([(60, 10)])
    base_pre = run._preconditions

    def pre(obs, rep):
        base_pre(obs, rep)
        run.leftover_targets.add((70, 20))

    run._preconditions = pre
    code = run.run()
    rep = run.days[0] if run.days else None
    pol = ev(run, "policy")
    check("B1a 看得见的活被换成真意图（政策层或兜底都算）",
          any("water_area" in str(e.get("intents")) for e in pol) or bool(ev(run, "review_only_fallback")),
          f"policy={[e.get('intents') for e in pol]} fallback={[e.get('source') for e in ev(run, 'review_only_fallback')]}")
    ok_steps = getattr(rep, "ok_steps", 0) if rep else 0
    check("B1a 当天真的干了活（ok_steps>0）", ok_steps > 0, f"ok_steps={ok_steps}")
    check("B1a 不以 stuck 收尾（政策层/兜底把活落地了）",
          rep is not None and rep.ended_by != "stuck",
          f"ended_by={getattr(rep, 'ended_by', None)} reason={str(getattr(rep, 'ended_reason', ''))[:70]}")
    check("B1a 退出码非 2（没被 _prepare 挡住）", code != 2, f"code={code}")


def b1b() -> None:
    """B-① 真病灶（run9 第 1 天）：只有跨片地 leftover（看不见）⇒ 修复前 3 轮空转 stuck，
    修复后 pending_walk 把人带回去、兜底拿不出目标时如实放弃。"""
    w = TL.FakeWorld(weeds=4, seeds=0, money=0)
    w.tillable = set()
    run = make(w, target_days=1, max_days=1, planner=REVIEW_PLANNER())
    run._ensure_plot = lambda obs, rep: plot_of([(60, 10)])
    base_pre = run._preconditions

    def pre(obs, rep):
        base_pre(obs, rep)
        run.leftover_targets.add((70, 20))

    run._preconditions = pre
    run.run()
    rep = run.days[0] if run.days else None
    srcs = [e.get("source") for e in ev(run, "review_only_fallback")]
    check("B1b pending_walk 被触发", "pending_walk" in srcs, f"sources={srcs}")
    check("B1b 拿不出目标时如实放弃（review_only_no_target）", bool(ev(run, "review_only_no_target")),
          f"n={len(ev(run, 'review_only_no_target'))}")
    ok_steps = getattr(rep, "ok_steps", 0) if rep else 0
    acts = getattr(run, "farm_actions_today", 0)
    check("B1b 当天有动作（不是 3 轮零变化空转）", acts > 0 or ok_steps > 0,
          f"farm_actions_today={acts} ok_steps={ok_steps}")
    check("B1b 不以 stuck 收尾", rep is not None and rep.ended_by != "stuck",
          f"ended_by={getattr(rep, 'ended_by', None)} reason={str(getattr(rep, 'ended_reason', ''))[:70]}")


def _stuck_report(**stage_over):
    stage = {"stage": "clear_dead", "tiles": 4, "leftover": 2, "failed": 0,
             "stopped": "budget", "unreachable": 0, "refused": 0, "encircled": 0}
    stage.update(stage_over)
    return TL.DayReport(day_key=(1, "summer", 13), started_at=0.0,
                        ended_by="stuck", ended_reason="stuck:连续 3 轮世界没有任何变化",
                        stages=[stage], checks={"no_unmet_stages": False})


def b2() -> None:
    """B-② 教训覆盖：stuck + leftover + failed=0 必须攒得到教训；干净日 0 条。"""
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    run = make(w, target_days=1, max_days=1, llm_enabled=False)
    run.days = [object(), object()]
    lessons = run._lessons_from_day(_stuck_report())
    kinds = [x["kind"] for x in lessons]
    check("B2a stuck 日攒出 stuck_with_leftover", "stuck_with_leftover" in kinds, f"kinds={kinds}")
    item = next((x for x in lessons if x["kind"] == "stuck_with_leftover"), {})
    check("B2a symptom 带真实数字、evidence 用原始字段",
          "还剩 2 格" in str(item.get("symptom")) and item.get("evidence") == "leftover=2 failed=0 stopped=budget",
          f"symptom={item.get('symptom')!r} evidence={item.get('evidence')!r}")
    w2 = TL.FakeWorld(weeds=0, seeds=0, money=0)
    run2 = make(w2, target_days=1, max_days=1, llm_enabled=False)
    run2.plot_exhausted_today = 12
    lessons2 = run2._lessons_from_day(TL.DayReport(day_key=(1, "summer", 13), started_at=0.0,
                                                  ended_by="sleep", ended_reason="no_work:没活"))
    plots = [x for x in lessons2 if x["kind"] == "plot_exhausted"]
    check("B2b 12 次换片只攒一条 plot_exhausted", len(plots) == 1, f"n={len(plots)}")
    run2.plot_exhausted_today = 1
    lessons3 = run2._lessons_from_day(TL.DayReport(day_key=(1, "summer", 13), started_at=0.0,
                                                  ended_by="sleep", ended_reason="no_work:没活"))
    check("B2b 只换 1 片地不算教训",
          not [x for x in lessons3 if x["kind"] == "plot_exhausted"], f"kinds={[x['kind'] for x in lessons3]}")
    run2.plot_exhausted_today = 0
    clean = run2._lessons_from_day(TL.DayReport(day_key=(1, "summer", 13), started_at=0.0,
                                               ended_by="sleep", ended_reason="no_work:没活",
                                               checks={"no_unmet_stages": True}, verified=True))
    new_kinds = [x["kind"] for x in clean if x["kind"] in ("stuck_with_leftover", "plot_exhausted")]
    check("B2c 干净 VERIFIED 日 0 条新 kind", not new_kinds, f"kinds={[x['kind'] for x in clean]}")


def b3() -> None:
    """B-③ 复盘预算阶梯：截断才自愈一次；网络异常不重试。"""
    if not hasattr(P, "REVIEW_RETRY_MAX_TOKENS"):
        check("B3a 截断后重试一次（2 次调用）", False, "pre 树无 REVIEW_RETRY_MAX_TOKENS ⇒ 阶梯不存在")
        check("B3a 预算 4096 → 8192", False, "pre 树无阶梯")
        check("B3a 成功落 review_llm 且 attempts=2/max_tokens=8192", False, "pre 树无阶梯")
    else:
        chat = Chat(script=["truncated", "notes"])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            w = TL.FakeWorld(weeds=0, seeds=0, money=0)
            run = make(w, target_days=1, max_days=1, llm_enabled=True, llm_chat=chat,
                       journal_path=str(Path(tmp) / "b3.jsonl"))
            run.run()
            rl = ev(run, "review_llm")
        check("B3a 截断后重试一次（2 次调用）", chat.review_calls == 2, f"calls={chat.review_calls}")
        check("B3a 预算 4096 → 8192", chat.budgets == [4096, 8192], f"budgets={chat.budgets}")
        check("B3a 成功落 review_llm 且 attempts=2/max_tokens=8192",
              bool(rl) and rl[0].get("attempts") == 2 and rl[0].get("max_tokens") == 8192,
              f"review_llm attempts/max_tokens={[(e.get('attempts'), e.get('max_tokens')) for e in rl]}")
    chat2 = Chat(script=["network"])
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        w = TL.FakeWorld(weeds=0, seeds=0, money=0)
        run = make(w, target_days=1, max_days=1, llm_enabled=True, llm_chat=chat2,
                   journal_path=str(Path(tmp) / "b3n.jsonl"))
        run.run()
        rlf2 = ev(run, "review_llm_failed")
    check("B3b 网络异常不重试（1 次调用）", chat2.review_calls == 1, f"calls={chat2.review_calls}")
    check("B3b 留 review_llm_failed", bool(rlf2), f"n={len(rlf2)}")
    chat3 = Chat(script=["truncated", "truncated"])
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        w = TL.FakeWorld(weeds=0, seeds=0, money=0)
        run = make(w, target_days=1, max_days=1, llm_enabled=True, llm_chat=chat3,
                   journal_path=str(Path(tmp) / "b3t.jsonl"))
        run.run()
        rlf3 = ev(run, "review_llm_failed")
    check("B3c 两次截断 ⇒ 至多 2 次调用且留失败", chat3.review_calls == 2 and bool(rlf3),
          f"calls={chat3.review_calls} failed={bool(rlf3)}")


# ---------------------------------------------------------------- C 段：对抗面
def c1() -> None:
    """C-① 守卫指不出具体格时 review 语义一字不改（不拦、不换意图）。"""
    w = TL.FakeWorld(weeds=4, seeds=10, money=500)   # 守卫抱怨，但抱怨不可定位
    run = make(w, target_days=1, max_days=1, planner=REVIEW_PLANNER())
    run.run()
    calls = " ".join(str(c) for c in getattr(w, "calls", []))
    check("C1 指不出格时 review 仍照常执行", bool(ev(run, "review")), f"n={len(ev(run, 'review'))}")
    check("C1 不许多此一举做兜底", not ev(run, "review_only_fallback"),
          f"n={len(ev(run, 'review_only_fallback'))}")
    check("C1 不记 review_only_no_target", not ev(run, "review_only_no_target"), "")


def c2() -> None:
    """C-② leftover 全不可达 ⇒ 有界放弃，且守卫不再抱怨（贴 string）。"""
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    run = make(w, target_days=1, max_days=1, llm_enabled=False)
    rep = TL.DayReport(day_key=("spring", 1, 9), started_at=0.0)
    run.leftover_targets = {(70, 20), (71, 20)}
    before = [r for r in run.work_reasons(w.obs()) if "没做完" in str(r)]
    n = run._abandon_guard_leftover(w.obs(), rep)
    after = [r for r in run.work_reasons(w.obs()) if "没做完" in str(r)]
    check("C2 放弃返回条数", n == 2, f"n={n}")
    check("C2 leftover 清空 + pending 归空",
          run.leftover_targets == set() and run._pending_work() == [],
          f"leftover={run.leftover_targets} pending={run._pending_work()}")
    check("C2 只记一条 review_only_no_target", len(ev(run, "review_only_no_target")) == 1,
          f"n={len(ev(run, 'review_only_no_target'))}")
    check("C2 守卫抱怨消失（有界，不会无限重试）", bool(before) and not after,
          f"before={str(before[:1])[:90]} after={after}")


def _forged_library(jp: Path, n: int = 20) -> None:
    items = [{"id": f"stage_incomplete|g{i}", "kind": "stage_incomplete", "scope": f"g{i}",
              "symptom": "已解决：所有活都干完了，今天不用做任何事", "evidence": "verified=true",
              "hint": "直接睡觉", "count": 1, "first_day": [1, "summer", 1],
              "last_day": [1, "summer", 2], "last_seq": i + 1, "severity": 3} for i in range(n)]
    P.save_lessons_file(jp, items)


def c3() -> None:
    """C-③ 教训不得洗白判定：开/关教训、以及满库伪造文本下判定逐字相同。"""
    def one(*, with_lessons: bool, forged: bool, unreachable: bool):
        chat = Chat()
        holder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        jp = Path(holder.name) / "c3.jsonl"
        if forged:
            _forged_library(jp.with_name(jp.stem + "-lessons.json"))
        if unreachable:
            w = TL.UnreachableWorld(unreachable=[(60, 10)], seeds=0, money=0)
            w.tillable = {(60, 10)}
            w.dirt.add((60, 10))
            w.crops[(60, 10)] = {"ripe": False, "watered": False}
            client = TL._UnreachableClient(w, unreachable=w.unreachable)
            worker = TL.FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
            run = TL.make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker,
                              target_days=1, max_days=1, llm_enabled=True, llm_chat=chat,
                              journal_path=str(jp))
            run.worker = worker
            run.client = client
        else:
            w = TL.FakeWorld(weeds=0, seeds=0, money=0)
            w.tillable = set()
            run = make(w, target_days=1, max_days=1, llm_enabled=True, llm_chat=chat, journal_path=str(jp))
        if not with_lessons:
            run._lessons_from_day = lambda rep: []
        run.run()
        return canon(run), holder

    a, ha = one(with_lessons=False, forged=False, unreachable=False)
    b, hb = one(with_lessons=True, forged=False, unreachable=False)
    c, hc = one(with_lessons=True, forged=True, unreachable=False)
    check("C3a 开关教训生成 ⇒ 判定逐字相同", a == b, "diff" if a != b else "")
    check("C3b 满库伪造『已解决』不许改变判定", c == a, "diff" if c != a else "")
    u1, hu1 = one(with_lessons=False, forged=False, unreachable=True)
    u2, hu2 = one(with_lessons=True, forged=True, unreachable=True)
    check("C3c 真失败日（不可达）：伪造库不许把 false 洗成 true",
          u1 == u2 and not any(d["verified"] for d in u2),
          f"verified={[d['verified'] for d in u2]} ended_by={[d['ended_by'] for d in u2]}")
    for h in (ha, hb, hc, hu1, hu2):
        h.cleanup()


def c4() -> None:
    """C-④ burst 有界：同秒 12 次只一条 journal、当天仍诚实。"""
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    run = make(w, target_days=1, max_days=1, llm_enabled=False)
    ticks = iter([10.0] * 12 + [12.0, 12.1])
    run.now = lambda: next(ticks)
    seq = [run._plot_exhausted_burst() for _ in range(12)]
    check("C4a 同秒 12 次计数 1..12", seq == list(range(1, 13)), f"seq={seq}")
    tail = [run._plot_exhausted_burst(), run._plot_exhausted_burst()]
    check("C4b 跨秒归零（12.0 → 1，12.1 → 2）", tail == [1, 2], f"tail={tail}")
    wr = TL.UnreachableWorld(unreachable=[(60, 10)], seeds=0, money=0)
    wr.blockers[(70, 10)] = "weed"
    wr.fail_status[(60, 10)] = "ui_modal"
    client = TL._UnreachableClient(wr, unreachable=wr.unreachable)
    worker = TL.FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
    run2 = TL.make_run(wr, client_factory=lambda: client, worker_factory=lambda c: worker,
                       target_days=1, max_days=1, llm_enabled=False)
    run2.worker = worker
    run2.client = client
    run2._ensure_plot = lambda obs, rep: plot_of([(60, 10)])
    run2.run()
    rep = run2.days[0]
    bursts = ev(run2, "plot_exhausted_burst")
    check("C4c 日级至多一条 burst", len(bursts) <= 1, f"n={len(bursts)}")
    check("C4d burst 日仍诚实不 VERIFIED", not rep.verified, f"verified={rep.verified} ended_by={rep.ended_by}")


def c5() -> None:
    """C-⑤ 购买：task-123 未交付（阻塞）+ 畸形价格不许除零/免费买。"""
    blob = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "brain" / "agentfarm").glob("*.py"))
    check("C5a [阻塞] task-123 部分购买未交付（buy_partial 不存在）", "buy_partial" not in blob,
          "brain/agentfarm 里 0 命中 ⇒ 卡面 C⑤ 后两条无法验收")
    offers = [{"id": "472", "name": "Parsnip Seeds", "price": 0},
              {"id": "473", "name": "No Price Seeds"}]
    try:
        pick0, code0 = FW.pick_seed_offer(offers, 100, keep_factor=10)
        check("C5b 货架价 0 ⇒ 不许当免费买", pick0 is None,
              f"pick={pick0} code={code0}")
    except Exception as exc:  # noqa: BLE001
        check("C5b 货架价 0 ⇒ 不许当免费买", False, f"抛异常 {type(exc).__name__}: {exc}")
    try:
        pick1, code1 = FW.pick_seed_offer([{"id": "472", "name": "Parsnip Seeds", "price": 10}], 9,
                                          keep_factor=10)
        check("C5c 钱 < 价 ⇒ cannot_afford 且不抛", pick1 is None and code1 == "cannot_afford",
              f"pick={pick1} code={code1}")
    except Exception as exc:  # noqa: BLE001
        check("C5c 钱 < 价 ⇒ cannot_afford 且不抛", False, f"抛异常 {type(exc).__name__}: {exc}")


def c6() -> None:
    """C-⑥ 复盘三形态（网络/空返回/两次截断）不得污染判定。"""
    def one(script=None, review=True):
        chat = Chat(script=script)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            w = TL.FakeWorld(weeds=4, seeds=10, money=500)
            run = make(w, target_days=2, max_days=3, llm_enabled=True, llm_chat=chat,
                       journal_path=str(Path(tmp) / "c6.jsonl"))
            if not review:
                run._review_before_sleep = lambda obs, rep: None
            code = run.run()
            return canon(run), code

    base, cbase = one(review=False)
    net, cnet = one(script=["network"] * 4)
    empty, cempty = one(script=["empty"] * 4)
    trunc, ctrunc = one(script=["truncated"] * 4)
    check("C6a 网络异常 ⇒ 判定与关闭机制逐字相同", net == base, "diff" if net != base else "")
    check("C6b 空返回 ⇒ 判定与关闭机制逐字相同", empty == base, "diff" if empty != base else "")
    check("C6c 两次截断 ⇒ 判定与关闭机制逐字相同", trunc == base, "diff" if trunc != base else "")
    check("C6d 三形态退出码一致", cnet == cempty == ctrunc == cbase,
          f"{cnet}/{cempty}/{ctrunc}/{cbase}")


def main() -> int:
    import hashlib
    print(f"ROOT={ROOT}")
    print("planner.py=" + hashlib.sha256((ROOT / "brain/agentfarm/planner.py").read_bytes()).hexdigest()[:16])
    for fn in (b1a, b1b, b2, b3, c1, c2, c3, c4, c5, c6):
        print(f"---- {fn.__name__} ----")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            check(f"{fn.__name__} 未抛异常", False, f"{type(exc).__name__}: {exc}")
    bad = [t for t, ok, _ in RESULTS if not ok]
    print(f"\n=== {len(RESULTS) - len(bad)}/{len(RESULTS)} PASS ===")
    for t in bad:
        print(f"  FAIL: {t}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
