#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""task-238（0.7.38 delta 复核）独立探针：F3 取回死锁 + 通道⑤ 等待日留痕 + GAP-2/GAP-1 核对。

只写 scratch/；用 T238_ROOT 切树（冻结树 `scratch/_t238` = `2ca6dc8`，pre 树 `scratch/_t206_pre` = 0.7.37）。

跑法（仓库根）：
    $env:PYTHONUTF8="1"; $env:T238_ROOT="$PWD\scratch\_t238"; python scratch\_t238_probe.py
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(os.environ.get("T238_ROOT") or ".").resolve()

PASS: list[str] = []
FAIL: list[str] = []
INFO: list[str] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(tag)
    print(("  PASS " if ok else "  FAIL ") + tag + (f" :: {detail}" if detail else ""))


def info(tag: str, detail: str = "") -> None:
    INFO.append(tag)
    print("  info " + tag + (f" :: {detail}" if detail else ""))


def _load():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    sys.path.insert(0, str(ROOT / "brain"))
    import test_longrun as TL  # noqa: E402

    return TL


TL = _load()


def has_216() -> bool:
    try:
        import agentfarm.longrun as LR

        return hasattr(LR.LongRun, "_tool_upgrade_skip_reason") and hasattr(LR.LongRun, "_urgent_farm_work")
    except Exception:
        return False


def events(run, name: str):
    return [e for e in run.entries if e.get("event") == name]


def day(w, *, max_steps: int = 60):
    run = TL.make_run(w, target_days=1, max_days=1)
    run.client = TL.FakeClient(w)
    run.worker = TL.FakeWorker(w)
    run.max_steps = max_steps
    rc = run.run()
    return run, (run.days[0] if run.days else None), rc


def world(**kw):
    return TL.FakeWorld(**kw)


# ---------- P1：主循环级 F3（壶在途 days=0 + 未浇活苗） ----------
def p1_main_loop_f3() -> None:
    print("[P1] 主循环级 F3：can 在途 days=0 + 2 格未浇活苗 ⇒ 当天必须去取回")
    w = world(weeds=0, seeds=0, money=0)
    w.dirt = {(60, 10), (61, 10)}
    w.crops = {(60, 10): {"ripe": False, "watered": False},
               (61, 10): {"ripe": False, "watered": False}}
    w.being_upgraded = {"kind": "can", "name": "Watering Can"}
    w.tool_upgrade_days_left = 0
    run, rep, rc = day(w)
    picks = [e for e in events(run, "pickup_tool")]
    check("P1a 主循环真的调了 pickup_tool", w.pickup_calls >= 1, f"pickup_calls={w.pickup_calls}")
    check("P1b pickup 回执 ok", bool(picks) and all(e.get("ok") for e in picks),
          f"pickup_tool={[ (e.get('ok'), e.get('code')) for e in picks ]}")
    check("P1c 收尾不是 stuck（F3 旧形态）", "stuck" not in str(getattr(rep, "ended_by", "")),
          f"ended_by={getattr(rep, 'ended_by', None)} reason={str(getattr(rep, 'ended_reason', ''))[:60]}")
    info("P1d 账本条数", f"events={len(run.entries)} rc={rc} verified={getattr(rep, 'verified', None)}")


# ---------- P2：通道⑤ wait 日（主循环级） ----------
def p2_wait_day_journal() -> None:
    print("[P2] 通道⑤：axe 在途 days=2（wait）⇒ 当天账本必须有一条 tool_upgrade_skipped{which:wait}")
    w = world(weeds=0, seeds=2, money=0)
    w.being_upgraded = {"kind": "axe", "name": "Axe"}
    w.tool_upgrade_days_left = 2
    run, rep, rc = day(w)
    sk = events(run, "tool_upgrade_skipped")
    check("P2a 有 tool_upgrade_skipped", len(sk) == 1, f"count={len(sk)}")
    check("P2b which=wait", (sk[0].get("which") if sk else None) == "wait",
          f"which={(sk[0].get('which') if sk else None)}")
    check("P2c reason 写明 wait", bool(sk) and "wait" in str(sk[0].get("reason")),
          f"reason={(sk[0].get('reason') if sk else None)}")
    check("P2d 同一天只记一条", len(sk) <= 1, f"count={len(sk)}")
    info("P2e 当天收尾", f"ended_by={getattr(rep, 'ended_by', None)} rc={rc}")


# ---------- P3：通道⑤ need_slot 日（主循环级） ----------
def p3_need_slot_day_journal() -> None:
    print("[P3] 通道⑤：背包满 + axe 在途 days=0（need_slot）+ 当天有活 ⇒ 留痕且绝不 pickup")
    w = world(weeds=3, seeds=0, money=0)          # 有活（清理杂草）⇒ 日循环会走到工具升级块
    w.inventory_capacity = 12
    w.inventory = [{"slot": i, "id": "388", "qualifiedId": "(O)388",
                    "name": "Wood", "stack": 1, "isTool": False} for i in range(12)]
    w.being_upgraded = {"kind": "axe", "name": "Axe"}
    w.tool_upgrade_days_left = 0
    run, rep, rc = day(w, max_steps=40)
    sk = events(run, "tool_upgrade_skipped")
    check("P3a 有 tool_upgrade_skipped", len(sk) == 1, f"count={len(sk)}")
    check("P3b which=need_slot", (sk[0].get("which") if sk else None) == "need_slot",
          f"which={(sk[0].get('which') if sk else None)}")
    check("P3c 没有空格 ⇒ 一次 pickup 都不发", w.pickup_calls == 0, f"pickup_calls={w.pickup_calls}")
    info("P3d 当天收尾", f"ended_by={getattr(rep, 'ended_by', None)} rc={rc}")
    # P3e：纯"无活"日的留痕缺口（结构性限制，只记录不判红）
    w2 = world(weeds=0, seeds=0, money=0)
    w2.inventory_capacity = 12
    w2.inventory = [{"slot": i, "id": "388", "qualifiedId": "(O)388",
                     "name": "Wood", "stack": 1, "isTool": False} for i in range(12)]
    w2.being_upgraded = {"kind": "axe", "name": "Axe"}
    w2.tool_upgrade_days_left = 0
    run2, rep2, rc2 = day(w2, max_steps=20)
    sk2 = events(run2, "tool_upgrade_skipped")
    info("P3e 纯无活日（sleep_guard=no_work 早退）留痕条数",
         f"count={len(sk2)} ended_by={getattr(rep2, 'ended_by', None)}（早退点在 _maybe_tool_upgrade 之前 ⇒ 结构性缺口，记 NIT）")


# ---------- P4：upgrade 仍让位于紧急农活（F3 放行只针对 pickup） ----------
def p4_upgrade_still_yields() -> None:
    print("[P4] upgrade 不许被 F3 修复顺手放行：钱/材料够 + 窗口有未浇活苗 ⇒ 先干农活/先留跳过，升级只能在后")
    w = world(weeds=0, seeds=0, money=3000)
    w.inventory.append({"slot": 6, "id": "334", "qualifiedId": "(O)334",
                        "name": "Copper Bar", "stack": 5, "isTool": False})
    w.dirt = {(60, 10)}
    w.crops = {(60, 10): {"ripe": False, "watered": False}}
    run, rep, rc = day(w, max_steps=40)
    ents = list(run.entries)
    names = [e.get("event") for e in ents]
    i_up = names.index("upgrade_tool") if "upgrade_tool" in names else None
    i_sk = names.index("tool_upgrade_skipped") if "tool_upgrade_skipped" in names else None
    sk = events(run, "tool_upgrade_skipped")
    check("P4a 当天有紧急农活时先记跳过或先干活",
          i_sk is not None or i_up is None,
          f"skipped_idx={i_sk} upgrade_idx={i_up}")
    if i_sk is not None and sk:
        info("P4b 跳过理由", str(sk[0].get("reason"))[:90])
    if i_up is not None and i_sk is not None:
        check("P4c 升级发生在跳过留痕之后（未抢在紧急农活前）", i_sk < i_up, f"{i_sk} < {i_up}")
    check("P4d 没有 pickup（本世界没有在途）", w.pickup_calls == 0, f"pickup_calls={w.pickup_calls}")


# ---------- P5：GAP-1 / GAP-2 静态与行为证据 ----------
def p5_gap_evidence() -> None:
    print("[P5] GAP-1（变异脚本在库）+ GAP-2（C# 断言面）")
    mut = ROOT / "scratch" / "_t205_mutate.py"
    check("P5a GAP-1：`scratch/_t205_mutate.py` 在库", mut.is_file(), str(mut))
    if mut.is_file():
        src = mut.read_text(encoding="utf-8")
        names = [n for n in ("m205a", "m205b", "m205c", "m205d") if n in src]
        check("P5b 脚本含 m205a–d 定义", len(names) == 4, f"命中={names}")
        check("P5c 脚本含还原校验", "restore" in src or "还原" in src, "字节级备份/还原")
    prog = ROOT / "mod" / "AgentFarm.Bridge.Tests" / "Program.cs"
    src = prog.read_text(encoding="utf-8")
    for name in ("t205_unique_offer_is_selected", "t205_wrong_tier_fails_closed",
                 "t205_duplicate_offers_fail_closed", "t205_kind_normalization"):
        check(f"P5d GAP-2 断言存在：{name}", name in src, "Program.cs")
    rules = (ROOT / "mod" / "AgentFarm.Bridge" / "ToolUpgradeRules.cs").read_text(encoding="utf-8")
    check("P5e 规则源码含 tier 连续判据", "tierBefore + 1" in rules, "Tier == tierBefore + 1")


CASES = [("P1", p1_main_loop_f3), ("P2", p2_wait_day_journal), ("P3", p3_need_slot_day_journal),
         ("P4", p4_upgrade_still_yields), ("P5", p5_gap_evidence)]


def main() -> int:
    print(f"T238_ROOT={ROOT}  has_216={has_216()}")
    only = os.environ.get("T238_ONLY")
    for name, fn in CASES:
        if only and name != only:
            continue
        try:
            fn()
        except Exception:
            FAIL.append(name + "-EXC")
            traceback.print_exc()
    print(f"\n== 合计 PASS={len(PASS)} FAIL={len(FAIL)} ==")
    if FAIL:
        print("FAIL 明细：" + ", ".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
