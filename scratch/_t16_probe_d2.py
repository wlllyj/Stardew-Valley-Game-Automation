# -*- coding: utf-8 -*-
"""【T16 ④】D2 独立探针（不复用作者断言）：用**真实购买**做观测差分，
并证明"新接线"与"旧接线表达式"在**购买副作用**上等价（只差记账真值）。

用法：$env:PYTHONUTF8="1"; & <DSH python> scratch\\_t16_probe_d2.py
"""
from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
sys.path.insert(0, str(REPO / "brain"))
sys.path.insert(0, str(REPO / "tests"))
import test_longrun as T  # noqa: E402

DayReport = getattr(T, "DayReport")
TaskIntent = getattr(T, "TaskIntent")


def setup(money: int):
    w = T.FakeWorld(weeds=0, seeds=0, money=money)
    run = T.make_run(w, target_days=1, max_days=1)
    run.client = T.FakeClient(w)
    run.worker = T._NoLootWorker(w)
    run.started = 0.0
    run.allow_buy = True
    return w, run


def drive(run, w, intent):
    rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
    obs = run._snap()
    run._plan_intents(SimpleNamespace(intents=[intent], source="llm", boundary="daily"))
    acted = run._execute(SimpleNamespace(intents=[intent]), obs, None, rep)
    rec = [r for r in run.intent_coverage if r["task"] == intent.task][0]
    return acted, rec


def main() -> int:
    bad = 0
    buy_intent = TaskIntent("buy", "inventory", "买种子", "seeds<2")

    # ---- A) 钱够：dispatch 走真实购买（观测差分为证） ----
    w, run = setup(5000)
    m0 = w.money
    acted, rec = drive(run, w, buy_intent)
    m1 = w.money
    print(f"[A 钱够] money {m0}->{m1}  buy_calls={len(w.buy_calls)} "
          f"acted={acted} steps={rec['executed_steps']} reasons={rec['reasons']}")
    okA = (m1 < m0) and len(w.buy_calls) >= 1 and acted is True \
        and rec["executed_steps"] == 1 and rec["reasons"] == {}
    if not okA:
        bad += 1
        print("   !! A 失败：钱够却没真买/记账不对")

    # ---- B) 钱不够：不得真买，且必须如实记 unknown_evidence（不假装下单） ----
    w2, run2 = setup(1)
    m0 = w2.money
    acted2, rec2 = drive(run2, w2, buy_intent)
    m1 = w2.money
    print(f"[B 钱不够] money {m0}->{m1}  buy_calls={len(w2.buy_calls)} "
          f"acted={acted2} steps={rec2['executed_steps']} reasons={rec2['reasons']}")
    okB = (m1 == m0) and acted2 is False and rec2["executed_steps"] == 0 \
        and rec2["reasons"] == {"unknown_evidence": 1}
    if not okB:
        bad += 1
        print("   !! B 失败：钱不够却记成 acted / 或凭空扣钱")

    # ---- C) 旧接线表达式 vs 新接线：购买副作用等价（只差真值语义） ----
    # 旧: bool(self._preconditions(obs, rep))  —— 内部也调 _preconditions_apply，故真买
    wo, ro = setup(5000)
    rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
    obs = ro._snap()
    # 影子：记录 _preconditions_apply 的调用次数
    calls = {"apply": 0}
    real_apply = ro._preconditions_apply

    def counting_apply(o, r):
        calls["apply"] += 1
        return real_apply(o, r)

    ro._preconditions_apply = counting_apply
    old_truth = bool(ro._preconditions(obs, rep))       # 旧接线的真值来源
    old_buys = len(wo.buy_calls)
    old_calls = calls["apply"]

    wn, rn = setup(5000)
    rep2 = DayReport(day_key=("spring", 1, 9), started_at=0.0)
    obs2 = rn._snap()
    calls2 = {"apply": 0}
    real_apply2 = rn._preconditions_apply

    def counting_apply2(o, r):
        calls2["apply"] += 1
        return real_apply2(o, r)

    rn._preconditions_apply = counting_apply2
    new_truth = rn._preconditions_apply(obs2, rep2)     # 新接线
    new_buys = len(wn.buy_calls)
    new_calls = calls2["apply"]

    print(f"[C 等价] 旧: truth={old_truth} apply_calls={old_calls} buys={old_buys}  "
          f"| 新: truth={new_truth} apply_calls={new_calls} buys={new_buys}")
    okC = (old_calls == 1 and new_calls == 1 and old_buys == new_buys == 1
           and old_truth is True and new_truth is True)
    # 关键：更新的语义差别 —— 没买到时旧接线恒 True（假 acted），新接线 False
    wo2, ro2 = setup(1)
    obs3 = ro2._snap()
    old_truth_fail = bool(ro2._preconditions(obs3, DayReport(day_key=("spring", 1, 9), started_at=0.0)))
    wn2, rn2 = setup(1)
    obs4 = rn2._snap()
    new_truth_fail = rn2._preconditions_apply(obs4, DayReport(day_key=("spring", 1, 9), started_at=0.0))
    print(f"[C 差别] 钱不够时  旧接线真值={old_truth_fail}（恒真=假 acted）  "
          f"新接线真值={new_truth_fail}（如实）")
    okC = okC and (old_truth_fail is True and new_truth_fail is False)
    if not okC:
        bad += 1
        print("   !! C 失败：等价性/差别断言不符")

    print(f"\n结论：{'全部通过' if bad == 0 else f'{bad} 项不符'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
