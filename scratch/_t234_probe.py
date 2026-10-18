"""task-234：0.7.40 delta 独立对抗验收探针（task-233 + task-232 + 建造预留）。

只在 scratch/ 里建点，**只读**冻结树（`git archive 6f9b797`），不碰游戏/桥/生产码。
用法（在真仓库根）：
    $env:PYTHONUTF8="1"; python scratch\\_t234_probe.py
    $env:T234_ROOT="<冻结树路径>"   # 默认 %TEMP%\\t234_frozen
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("T234_ROOT") or (REPO / "scratch" / "_t234_frozen"))
if not ROOT.is_dir():
    ROOT = Path(os.environ.get("TEMP", r"C:\Users\admin\AppData\Local\Temp")) / "t234_frozen"
for p in (str(ROOT / "tests"), str(ROOT / "brain"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_longrun as TL  # noqa: E402
import test_farmwork as TF  # noqa: E402
from agentfarm import farmwork as FW  # noqa: E402
from agentfarm import longrun as LR  # noqa: E402
from agentfarm import planner as PL  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []
INFO: list[str] = []
PY = sys.executable


def check(tag: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(tag)
    print(("  PASS  " if ok else "  FAIL  ") + tag + (f" :: {detail}" if detail else ""))
    return bool(ok)


def info(tag: str, detail: str = "") -> None:
    INFO.append(tag)
    print(f"  INFO  {tag} :: {detail}")


def skip(tag: str, why: str) -> None:
    print(f"  SKIP  {tag} :: {why}")


def _row(slot: int, qid: str, name: str, stack: int, *, tool: bool = False) -> dict:
    bare = qid.rsplit(")", 1)[-1] if qid.startswith("(") else qid
    return {"slot": slot, "id": bare, "qualifiedId": qid, "name": name,
            "stack": stack, "isTool": tool}


TOOLS = [_row(0, "(T)Axe", "Axe", 1, tool=True),
         _row(1, "(T)Hoe", "Hoe", 1, tool=True),
         _row(2, "(T)WateringCan", "Watering Can", 1, tool=True)]


class SpaceWorker(TL.FakeWorker):
    """卖成功就把行搬走（钱当天不动）；可配"回执 ok 但没搬"与"顺手加钱"。"""

    def __init__(self, world, *, move: bool = True, add_money: bool = False):
        super().__init__(world)
        self.move = move
        self.add_money = add_money
        self.sell_calls: list[dict] = []

    def sell(self, slot, *, whitelist=None, timeout_ms=8000):
        self.sell_calls.append({"slot": int(slot), "whitelist": [str(x) for x in (whitelist or [])]})
        row = next((r for r in self.w.inventory if int(r.get("slot") or 0) == int(slot)), None)
        if row is None:
            return FW.StepResult("sell", None, ok=False, code="not_whitelisted",
                                 reason="假世界：这格没东西")
        st = FW.StepResult("sell", None, ok=True, code="ok", reason="假世界：卖出整叠（钱等 NewDay）")
        st.before = {"slot": int(slot), "qid": row.get("qualifiedId"), "stack": row.get("stack")}
        st.after = {"slot": int(slot), "qid": row.get("qualifiedId"), "stack": 0}
        if self.move:
            self.w.inventory.remove(row)
            if self.add_money:
                self.w.money = int(self.w.money) + int(row.get("stack") or 0)
        return st


def _space_world(*, surplus: bool = True, ripe: int = 3) -> TL.FakeWorld:
    w = TL.FakeWorld(seeds=10, money=1977, weeds=0)
    tiles = [(60 + i, 10) for i in range(ripe)]
    w.dirt = set(tiles)
    w.crops = {t: {"ripe": True, "watered": True} for t in tiles}
    inv = list(TOOLS)
    if surplus:
        inv += [_row(3, "(O)388", "Wood", 99), _row(4, "(O)388", "Wood", 99),
                _row(6, "(O)262", "Wheat", 10), _row(7, "(O)178", "Hay", 5),
                _row(8, "(O)Moss", "Moss", 2), _row(10, "(O)390", "Stone", 3),
                _row(11, "(O)535", "Geode", 3)]
    else:
        inv += [_row(3, "(O)178", "Hay", 5), _row(4, "(O)Moss", "Moss", 2),
                _row(5, "(O)999", "Mystery Thing", 1), _row(6, "(O)999", "Mystery Thing", 2),
                _row(7, "(O)178", "Hay", 5), _row(8, "(O)Moss", "Moss", 2),
                _row(10, "(O)999", "Mystery Thing", 1), _row(11, "(O)178", "Hay", 5)]
    inv.append(_row(9, "(O)472", "Wheat Seeds", 10))
    w.inventory = inv[:12]
    return w


def _mk(w, worker=None):
    run = TL.make_run(w, target_days=1, max_days=1)
    run.client = TL.FakeClient(w)
    run.worker = worker or TL.FakeWorker(w)
    run.started = 0.0
    return run


def _rep(day: int = 9):
    return TL.DayReport(day_key=("spring", 1, day), started_at=0.0)


def _events(run, name: str) -> list[dict]:
    return [e for e in run.entries if e.get("event") == name]


def _obs_with_inventory(w, inv) -> dict:
    w.inventory = list(inv)
    return w.obs()


# ---------------------------------------------------------------- A 段 task-233
def case_a1() -> None:
    tag = "A1 ship 无货 ⇒ unknown_evidence + unknown_why，无裸 no_target"
    class NoLoot(TL.FakeWorker):
        def __init__(self, world):
            super().__init__(world)
            self.calls = 0
        def sell_loot(self, *, timeout_ms=8000, max_items=24):
            self.calls += 1
            return False
    w = TL.FakeWorld(weeds=0, seeds=10, money=500)
    run = _mk(w, NoLoot(w))
    intent = TL.TaskIntent("ship", "inventory", "把今天收的货放进出货箱", "shipping>0")
    run._plan_intents(SimpleNamespace(intents=[intent], source="llm", boundary="daily"))
    run._execute(SimpleNamespace(intents=[intent]), run._snap(), None, _rep())
    rec = next((r for r in run.intent_coverage if r.get("task") == "ship"), None)
    if not check(tag + "（记录存在）", rec is not None, str(run.intent_coverage)[:200]):
        return
    ev = rec.get("evidence") or {}
    check(tag + " reasons", rec.get("reasons") == {"unknown_evidence": 1}, str(rec.get("reasons")))
    check(tag + " 无 no_target", "no_target" not in (rec.get("reasons") or {}), str(rec.get("reasons")))
    check(tag + " unknown_why=non_plot_task", ev.get("unknown_why") == "non_plot_task", str(ev))
    check(tag + " 自带可判证据", "whitelist_count" in ev and "free_slots" in ev, str(ev))
    check(tag + " coverage 不变式", LR._intent_coverage_ok(rec), "")


def case_a2() -> None:
    tag = "A2 片区任务取消仍产 no_target + stage_tiles_empty=True"
    w = TL.FakeWorld(weeds=0, seeds=10, money=500)
    run = TL.make_run(w, target_days=1, max_days=1,
                      planner=TL.FakePlanner(TL.TaskIntent("harvest", "tiles.ripe", "收成熟的", "ripe>0")))
    code = run.run()
    recs = [r for r in run.days[0].intent_coverage
            if r.get("task") == "harvest" and "no_target" in (r.get("reasons") or {})]
    check(tag + "（run 正常结束）", code == 0, str(code)[:80])
    if not check(tag + "（有 no_target 记录）", bool(recs), str(run.days[0].intent_coverage)[:220]):
        return
    ok = all((r.get("evidence") or {}).get("stage_tiles_empty") is True for r in recs)
    check(tag, ok, str([r.get("evidence") for r in recs])[:200])
    check(tag + " coverage 不变式", all(LR._intent_coverage_ok(r) for r in recs), "")


def _load_analyzer():
    spec = importlib.util.spec_from_file_location("_t234_analyzer", ROOT / "tools" / "analyze-longrun.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case_a3() -> None:
    tag = "A3 旧账本（无 evidence 字段）⇒ 不判 intent_no_target_evidence 红"
    ledger = None
    for cand in ("logs/longrun-3day-llm-run9c.jsonl", "logs/longrun-run9c.jsonl"):
        if (ROOT / cand).is_file():
            ledger = ROOT / cand
            break
    if ledger is None:
        skip(tag, "冻结树里没有旧账本")
        return
    proc = subprocess.run([PY, str(ROOT / "tools" / "analyze-longrun.py"),
                           "--journal", str(ledger), "--days", "3"],
                          cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONUTF8": "1"})
    out = (proc.stdout or "") + (proc.stderr or "")
    check(tag, "intent_no_target_evidence" not in out, ledger.name)
    if "无法判定" in out:
        info(tag + "（旧账本进无法判定）", "analyzer 输出了无法判定")


def case_a4() -> None:
    tag = "A4 analyzer §8.3.7：裸 no_target 红、带 unknown_why 的非片区证据不红"
    mod = _load_analyzer()
    base = {"intent_id": "spring 9#01", "task": "ship", "area_hint": "inventory",
            "area": "", "source": "llm", "boundary": "daily",
            "requested_tiles": 0, "ok_tiles": 0, "failed_tiles": 0, "unexecuted_tiles": 0,
            "executed_steps": 0, "actionless": False, "reasons_are_intent_level": True}
    bare = dict(base, reasons={"no_target": 1})
    f1 = mod.cat_intent([], [{"events": [(1, {"event": "day_end",
                                               "intent_coverage": [bare]})]}], [], 10)
    reds1 = [str(f.get("subject") or "") for f in f1]
    good = dict(base, reasons={"unknown_evidence": 1},
                evidence={"unknown_why": "non_plot_task", "whitelist_count": 0,
                          "free_slots": 0, "inventory_full": True, "no_sellable_stack": True})
    f2 = mod.cat_intent([], [{"events": [(1, {"event": "day_end",
                                               "intent_coverage": [good]})]}], [], 10)
    reds2 = [str(f.get("subject") or "") for f in f2]
    check(tag + "（裸 no_target 判红）",
          any(s.startswith("missed:intent_no_target_evidence") for s in reds1), str(reds1))
    check(tag + "（非片区证据不红）",
          not any(s.startswith("missed:intent_no_target_evidence") for s in reds2), str(reds2))
    # D②：用 unknown_evidence 掩盖真失败时，缺 unknown_why 能不能被工具抓住
    vague = dict(base, reasons={"unknown_evidence": 1}, evidence={})
    f3 = mod.cat_intent([], [{"events": [(1, {"event": "day_end",
                                               "intent_coverage": [vague]})]}], [], 10)
    reds3 = [str(f.get("subject") or "") for f in f3]
    if any("no_target_evidence" in s for s in reds3):
        check(tag + "（缺失 unknown_why 也被抓）", True, str(reds3))
    else:
        info(tag + "（缺失 unknown_why ⇒ 工具不判红）",
             "§8.3.7 只校验 no_target 的证据；unknown_evidence 的降级理由在账本层不可验证 ⇒ 记录为已知边界")


# ---------------------------------------------------------------- B 段 task-232
def case_b1() -> None:
    tag = "B1 满包 + 熟作物 + 有盈余 ⇒ 空格压力卖掉一叠、腾出≥1 格"
    w = _space_world(surplus=True)
    worker = SpaceWorker(w)
    run = _mk(w, worker)
    obs = run._snap()
    before = FW.player_free_slots(FW.FarmWorker.player_of(obs))[0]
    rep = _rep()
    ok = run._slot_relief(obs, rep)
    ev = (_events(run, "slot_relief") or [{}])[-1]
    check(tag + "（触发腾格）", ok is True, f"ok={ok} before={before}")
    check(tag + " trigger=space_pressure", ev.get("trigger") == "space_pressure", str(ev.get("trigger")))
    check(tag + " sold 非空", bool(ev.get("sold")), str(ev.get("sold")))
    check(tag + " freed>=1", int(ev.get("freed") or 0) >= 1, str(ev.get("freed")))
    check(tag + " 只卖已知盈余（Wood）",
          all(str(it.get("qid")) == "(O)388" for it in (ev.get("sold") or [])),
          str([it.get("qid") for it in (ev.get("sold") or [])]))
    check(tag + " 有空格后 harvest 不再必然 no_slot",
          FW.player_free_slots(FW.FarmWorker.player_of(run._snap()))[0] >= 1, "")


def case_b2() -> None:
    tag = "B2 满包 + 熟作物 + 无盈余（表外/工具/种子）⇒ 如实 inventory_blocked 且无 failed"
    w = _space_world(surplus=False)
    worker = SpaceWorker(w)
    run = _mk(w, worker)
    rep = _rep()
    ok = run._slot_relief(run._snap(), rep)
    ev = (_events(run, "slot_relief") or [{}])[-1]
    check(tag + "（腾不出 ⇒ False）", ok is False, f"ok={ok}")
    check(tag + " inventory_blocked_today", run.inventory_blocked_today is True, "")
    check(tag + " 一笔没卖", not ev.get("sold"), str(ev.get("sold")))
    blocked = (_events(run, "inventory_blocked") or [{}])[-1]
    reason = str(blocked.get("reason") or "")
    check(tag + " 理由如实",
          ("没有可卖的盈余叠" in reason) or ("腾不出格子" in reason), reason[:200])
    check(tag + " failed_steps==0", int(rep.failed_steps) == 0, str(rep.failed_steps))


def case_b3() -> None:
    tag = "B3 工具/武器/种子/升级锭/表外物品一件不卖（fail-closed）"
    w = _space_world(surplus=True)
    inv = list(w.inventory) + [  # 12 格已满，但 plan 是纯函数：多给几行也一样
        _row(20, "(T)Pickaxe", "Pickaxe", 1, tool=True),
        _row(21, "(O)334", "Copper Bar", 10),
        _row(22, "(O)338", "Refined Quartz", 10),
        _row(23, "(O)787", "Battery Pack", 4),
        _row(24, "(O)999", "Mystery Thing", 9),
        _row(25, "(O)207", "Hay", 9),          # 表外（Hay 不在三张表里）
        _row(26, "(O)472", "Wheat Seeds", 10),
    ]
    obs = _obs_with_inventory(w, inv)
    plan = FW.slot_relief_plan(obs, free_slots=0, free_slots_status="ok",
                               trigger_free_slots=1, max_stacks=1)
    banned = {"(T)Pickaxe", "(O)334", "(O)338", "(O)787", "(O)999", "(O)207", "(O)472"}
    sold = set(plan.get("whitelist") or [])
    check(tag, not (sold & banned), f"sold={sorted(sold)}")
    check(tag + "（卖的是盈余 Wood）", sold == {"(O)388"}, f"sold={sorted(sold)}")


def case_b4() -> None:
    tag = "B4 建造预留：铜矿 30 只卖 5 留 25 / 石头 28 一件不卖 / 单叠 30 不许整叠卖空"
    # (a) 铜矿叠 5 + 叠 25 ⇒ 只能卖 5（留 25）。世界里不放别的可卖叠，否则按 tier 排序会先卖别的。
    w = TL.FakeWorld(seeds=0, money=0)
    obs = _obs_with_inventory(w, list(TOOLS) + [
        _row(3, "(O)378", "Copper Ore", 5), _row(4, "(O)378", "Copper Ore", 25)])
    plan = FW.slot_relief_plan(obs, free_slots=0, free_slots_status="ok",
                               trigger_free_slots=1, max_stacks=1)
    items = plan.get("items") or []
    check(tag + "（a 卖 5）",
          bool(items) and int(items[0]["stack"]) == 5 and int(items[0].get("keep") or 0) == 25,
          str(items))
    # (b) 石头单叠 28 ⇒ 预留 30 ⇒ 一件不卖
    obs2 = _obs_with_inventory(w, list(TOOLS) + [_row(3, "(O)390", "Stone", 28)])
    plan2 = FW.slot_relief_plan(obs2, free_slots=0, free_slots_status="ok",
                                trigger_free_slots=1, max_stacks=1)
    check(tag + "（b 石头一件不卖）", not plan2.get("slots"),
          f"slots={plan2.get('slots')} skip={plan2.get('skipReason')}")
    # (c) 铜矿单叠 30 ⇒ 不许整叠卖空
    obs3 = _obs_with_inventory(w, list(TOOLS) + [_row(3, "(O)378", "Copper Ore", 30)])
    plan3 = FW.slot_relief_plan(obs3, free_slots=0, free_slots_status="ok",
                                trigger_free_slots=1, max_stacks=1)
    check(tag + "（c 单叠 30 不整叠卖空）", not plan3.get("slots"),
          f"slots={plan3.get('slots')} skip={plan3.get('skipReason')}")
    check(tag + "（c 理由提建造预留）", "建造预留" in str(plan3.get("skipReason") or ""),
          str(plan3.get("skipReason"))[:120])


def case_b5() -> None:
    tag = "B5 有界：每天 ≤3 轮、≤5 叠"
    w = TL.FakeWorld(seeds=0, money=0)
    inv = list(TOOLS) + [_row(3 + i, "(O)388", "Wood", 20) for i in range(8)]
    obs = _obs_with_inventory(w, inv)
    worker = SpaceWorker(w)
    run = _mk(w, worker)
    run.worker = worker
    rep = _rep()
    for _ in range(8):
        run._slot_relief(run._snap(), rep)
    check(tag + "（叠数 ≤5）", int(run.slot_relief_stacks_today) <= 5,
          str(run.slot_relief_stacks_today))
    check(tag + "（轮数 ≤3）", int(run.slot_relief_today) <= 3, str(run.slot_relief_today))
    check(tag + "（sell 未被无限调用）", len(worker.sell_calls) <= 5, str(len(worker.sell_calls)))


def case_b6() -> None:
    tag = "B6 钱/背包行数双差分"
    # (i) 回执 ok 但没搬走 ⇒ 不判成功
    w = _space_world(surplus=True)
    liar = SpaceWorker(w, move=False)
    run = _mk(w, liar)
    ok = run._slot_relief(run._snap(), _rep())
    ev = (_events(run, "slot_relief") or [{}])[-1]
    check(tag + "（没搬走 ⇒ 不成功）", ok is False, f"ok={ok}")
    check(tag + "（failed=true）", ev.get("failed") is True, str(ev.get("failed")))
    check(tag + "（理由提行数）", "行数" in str(ev.get("blocked_reason") or ""),
          str(ev.get("blocked_reason"))[:160])
    check(tag + "（如实 inventory_blocked）", run.inventory_blocked_today is True, "")
    # (ii) 卖的时候给自己加钱 ⇒ 蓝线
    w2 = _space_world(surplus=True)
    cheat = SpaceWorker(w2, add_money=True)
    run2 = _mk(w2, cheat)
    run2._slot_relief(run2._snap(), _rep())
    ev2 = (_events(run2, "slot_relief") or [{}])[-1]
    check(tag + "（脑侧加钱被抓）", ev2.get("failed") is True, str(ev2.get("failed")))
    check(tag + "（理由提钱）", "钱" in str(ev2.get("blocked_reason") or ""),
          str(ev2.get("blocked_reason"))[:160])


def case_b6b() -> None:
    tag = "B6b（附加）第二轮卖无可卖时，累计 sold 会不会让双差分误报"
    inv = list(TOOLS) + [_row(3, "(O)388", "Wood", 99), _row(4, "(O)388", "Wood", 99),
                         _row(5, "(O)178", "Hay", 5), _row(6, "(O)999", "Mystery", 2),
                         _row(7, "(O)178", "Hay", 5), _row(8, "(O)178", "Hay", 5),
                         _row(9, "(O)999", "Mystery", 1),
                         _row(10, "(O)178", "Hay", 5), _row(11, "(O)178", "Hay", 5)]
    w = TL.FakeWorld(seeds=0, money=100)
    tiles = [(60 + i, 10) for i in range(3)]
    w.dirt = set(tiles)
    w.crops = {t: {"ripe": True, "watered": True} for t in tiles}
    obs = _obs_with_inventory(w, inv)
    worker = SpaceWorker(w)
    run = _mk(w, worker)
    run.worker = worker
    rep = _rep()
    run._slot_relief(run._snap(), rep)          # 第一轮：卖出盈余
    first_sold = list(run.slot_relief_sold)
    if not first_sold:
        skip(tag, "第一轮没卖成，无法构造")
        return
    # 第二轮：把剩下可卖的都换掉（只剩工具/种子/表外）⇒ 本轮必然卖不出东西
    w.inventory = list(TOOLS) + [_row(3, "(O)178", "Hay", 5), _row(4, "(O)178", "Hay", 5),
                                 _row(5, "(O)999", "Mystery", 2), _row(6, "(O)178", "Hay", 5),
                                 _row(7, "(O)178", "Hay", 5), _row(8, "(O)178", "Hay", 5),
                                 _row(9, "(O)999", "Mystery", 1),
                                 _row(10, "(O)178", "Hay", 5),
                                 _row(11, "(O)472", "Wheat Seeds", 10)]
    run.inventory_blocked_today = False
    run._slot_relief(run._snap(), _rep())
    ev2 = (_events(run, "slot_relief") or [{}])[-1]
    if ev2.get("failed") is True and "行数" in str(ev2.get("blocked_reason") or ""):
        info(tag, "第二轮卖无可卖却报 failed（本轮 sold 空、累计 sold>0 被当本轮）"
                  f" ⇒ blocked_reason={str(ev2.get('blocked_reason'))[:110]}")
    else:
        info(tag, f"第二轮未误报（failed={ev2.get('failed')}，本轮 sold={ev2.get('sold')}）")


# ---------------------------------------------------------------- D 段杂项
def case_d5() -> None:
    tag = "D5 脑侧没有把自己加钱的代码（只允许写进账本 dict）"
    bad = []
    for rel in ("brain/agentfarm/farmwork.py", "brain/agentfarm/longrun.py"):
        for lineno, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'\[["\']money["\']\]\s*[-+]?=', line):
                # 写进 facts/trigger/sold 这类账本 dict 是允许的；写进 player/玩家态是红线。
                if "facts" in line or "trigger" in line or "sold" in line:
                    continue
                bad.append(f"{rel}:{lineno}: {line.strip()[:80]}")
            if re.search(r'(player|world|obs)\s*\[\s*["\']money["\']\s*\]\s*[-+]?=', line):
                bad.append(f"{rel}:{lineno}: {line.strip()[:80]}")
    check(tag, not bad, str(bad[:5]))


def case_d7() -> None:
    tag = "D7 checks 键集不新增（10 键）+ 不新增事件名"
    w = TL.FakeWorld(weeds=0, seeds=10, money=500)
    run = TL.make_run(w, target_days=1, max_days=1)
    run.run()
    checks = run.days[0].checks
    expect = {"slept_by_us", "no_blocking_modal", "no_hard_failures", "unreachable_within_bound",
              "refused_within_bound", "no_unmet_stages", "crops_watered", "watered_outdoor",
              "day_justified", "zero_action_evidenced"}
    check(tag + "（checks 10 键）", set(checks) == expect,
          f"多={sorted(set(checks) - expect)} 少={sorted(expect - set(checks))}")
    names = {e.get("event") for e in run.entries}
    check(tag + "（无 slot_relief_space 之类新事件名）",
          not any(n and "space" in str(n) for n in names), str(sorted(n for n in names if n)[:8]))


def case_c() -> None:
    tag = "C 真机冒烟 0.7.40 读数对账"
    doc = REPO / "docs" / "_smoke-0740.md"
    ledger = REPO / "logs" / "longrun-smoke-0740.jsonl"
    if not doc.is_file() and not ledger.is_file():
        skip(tag, "docs/_smoke-0740.md 与 logs/longrun-smoke-0740.jsonl 都还没生成（machine-runner 在跑）")
        return
    if ledger.is_file():
        lines = [json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()]
        ends = [r for r in lines if r.get("event") == "day_end"]
        sell_ev = [r for r in lines if r.get("event") == "slot_relief"]
        finished = any(r.get("event") == "finish" for r in lines)
        freed = sum(int(r.get("freed") or 0) for r in sell_ev)
        solds = [it for r in sell_ev for it in (r.get("sold") or [])]
        if not ends:
            skip(tag, f"{ledger.name} 还没有 day_end（跑批进行中）⇒【无法判定】")
            return
        blocked = [r for r in ends if r.get("ended_by") == "inventory_blocked"]
        info(tag + "（中局读数）",
             f"day_end={len(ends)} finish={'是' if finished else '否'} "
             f"inventory_blocked={len(blocked)} slot_relief={len(sell_ev)} "
             f"freed合计={freed} sold={len(solds)}")
        for r in sell_ev:
            if r.get("failed"):
                info(tag + "（slot_relief failed 明细）",
                     f"round={r.get('round')} trigger={r.get('trigger')} freed={r.get('freed')} "
                     f"blocked_reason={str(r.get('blocked_reason'))[:120]}")
        if not finished:
            skip(tag, "跑批还没 finish ⇒ C 段判据（日报告不全 blocked / freed>0 / sold 可核）待跑完再判")
            return
        check(tag + "（日报告不全 inventory_blocked）", len(blocked) < max(1, len(ends)),
              f"ends={len(ends)} blocked={len(blocked)}")
        check(tag + "（slot_relief.freed>0 且 sold 明细）",
              freed > 0 and bool(solds), f"freed={freed} sold={len(solds)}")
    if doc.is_file():
        text = doc.read_text(encoding="utf-8")
        check(tag + "（文档无 missed:intent_no_target_evidence:ship）",
              "missed:intent_no_target_evidence:ship" not in text, "docs/_smoke-0740.md")
        check(tag + "（A2 证据链：kind_trace/use_tool_calls）",
              ("kind_trace" in text) and ("use_tool_calls" in text), "docs/_smoke-0740.md")


def main() -> int:
    print(f"ROOT={ROOT}")
    print(f"版本：{LR.MOD_VERSION_EXPECTED}")
    for fn in (case_a1, case_a2, case_a3, case_a4,
               case_b1, case_b2, case_b3, case_b4, case_b5, case_b6, case_b6b,
               case_d5, case_d7, case_c):
        print(f"\n== {fn.__name__} ==")
        try:
            fn()
        except Exception as exc:  # 探针自身异常不许静默
            import traceback
            traceback.print_exc()
            FAIL.append(fn.__name__ + ":EXC")
            print(f"  FAIL  {fn.__name__} 抛异常: {exc!r}")
    print(f"\n汇总：PASS={len(PASS)} FAIL={len(FAIL)} INFO={len(INFO)}")
    if FAIL:
        print("FAIL 明细：")
        for x in FAIL:
            print("  - " + x)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
