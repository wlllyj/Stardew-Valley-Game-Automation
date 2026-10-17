r"""task-206 独立对抗验收探针：task-205 铁匠铺升级闭环（`8ee33cb`）。

只写 scratch/；不碰生产代码、不跑真机。
用 `T206_ROOT` 指向 `git archive` 冻结树（`scratch\_t206_post` / `_t206_pre`），
默认用工作树。

覆盖卡面 8 通道：
  1 回执洗白（回执 ok 但世界没变 / 反向回执 ok=false 但世界真变）
  2 钱不够 fail-closed 且钱一分不动
  3 在途 daysLeft>0 仍重复购买 ⇒ 必须 already_upgrading / wait，不许再扣
  4 选错工具 ⇒ tool_not_offered，不扣钱
  5 在途两天诚实留痕：不算 hard failure、不算升级成功、不吃 gave_up 配额
  6 checks/_leftover/JUSTIFIED_END_REASONS 口径不许污染
  7 变异实测（另见 scratch\_t206_mutate.py）
  8 真机序列可复核性（本探针只能查“证据包/脚本是否存在”，真机未跑 ⇒ 无法判定）
外加 Lead 追加的 A/B 两条关注点。
"""

from __future__ import annotations

import os
import subprocess
import sys
import traceback

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.environ.get("T206_ROOT") or WORKSPACE
if not os.path.isdir(os.path.join(ROOT, "brain", "agentfarm")):
    ROOT = WORKSPACE

for _p in (os.path.join(ROOT, "brain"), ROOT, os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import test_longrun as TL  # noqa: E402
from agentfarm import bridge as BR  # noqa: E402
from agentfarm import farmwork as FW  # noqa: E402
from agentfarm import longrun as LR  # noqa: E402
from agentfarm.farmwork import FarmWorker  # noqa: E402

PASS = 0
FAIL = 0
SKIP = 0
NOTES: list[tuple[str, bool, str]] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {tag}" + (f" :: {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  FAIL {tag}" + (f" :: {detail}" if detail else ""))


def note(tag: str, ok: bool, detail: str = "") -> None:
    NOTES.append((tag, ok, detail))
    print(("  info " if ok else "  WARN ") + tag + (f" :: {detail}" if detail else ""))


def skip(tag: str, why: str = "") -> None:
    global SKIP
    SKIP += 1
    print(f"  skip {tag}" + (f" :: {why}" if why else ""))


def has_205() -> bool:
    return (hasattr(FW, "UPGRADE_KINDS") and hasattr(FW, "tool_being_upgraded")
            and hasattr(FW.FarmWorker, "upgrade_tool") and hasattr(FW.FarmWorker, "pickup_tool")
            and hasattr(LR, "TOOL_UPGRADE_MAX_PER_DAY")
            and hasattr(LR.LongRun, "_maybe_tool_upgrade"))


def events(run, name: str) -> list[dict]:
    return [e for e in getattr(run, "entries", []) if e.get("event") == name]


def plot(tiles) -> dict:
    tiles = [tuple(t) for t in tiles]
    return {"zone": "", "label": "", "anchor": list(tiles[0]), "tiles": [list(t) for t in tiles], "note": ""}


def copper(w, stack: int = 5) -> None:
    w.inventory.append({"slot": 20, "id": "334", "qualifiedId": "(O)334",
                        "name": "Copper Bar", "stack": stack, "isTool": False})


def mk(w, **kw):
    client = kw.pop("client", None) or BaseClient(w)
    worker = kw.pop("worker", None) or FarmWorker(client, log=lambda _s: None, pause=lambda _s: None)
    kw.setdefault("target_days", 1)
    kw.setdefault("max_days", 1)
    run = TL.make_run(w, client_factory=lambda: client,
                      worker_factory=lambda c: worker, **kw)
    run.client = client
    run.worker = worker
    return run, client, worker


def run_day(w, **kw):
    run, client, worker = mk(w, **kw)
    code = run.run()
    rep = run.days[-1] if getattr(run, "days", None) else None
    return run, client, worker, code, rep


# ---------------------------------------------------------------- 假客户端：按真桥形状（dict）补齐
class BaseClient(TL.FakeClient):
    """真桥（BridgeClient）返回 **dict**；测试夹具 FakeClient 的 upgrade/pickup 返回 StepResult、
    且没有 buy/sell ⇒ 接真 FarmWorker 会 AttributeError。这里按真桥形状补齐。"""

    def buy(self, item, count=10, *, shop="SeedShop", timeout_ms=25000):
        return {"ok": False, "status": "item_not_sold", "reason": "假世界不卖种子"}

    def sell(self, slot, *, whitelist=None, timeout_ms=8000):
        return {"ok": False, "status": "empty_slot", "reason": "假世界不出货"}

    def _do_upgrade(self, kind: str) -> dict:
        tier = int(self.w.tool_tiers.get(kind, 0))
        before = int(self.w.money)
        self.w.money = before - 2000
        self.w.tool_tiers[kind] = tier + 1
        self.w.being_upgraded = {"kind": kind, "name": kind, "qualifiedId": f"(T){kind}"}
        self.w.tool_upgrade_days_left = 2
        return {"ok": True, "status": "ok", "price": 2000, "tradeItem": "(O)334",
                "tradeCount": 5, "moneyBefore": before, "moneyAfter": self.w.money,
                "tierAfter": tier + 1, "reason": "已买下（假世界）"}

    def upgrade_tool(self, which, *, timeout_ms=60000):
        kind = str(which)
        self.w.upgrade_calls.append(kind)
        return self._do_upgrade(kind)

    def pickup_tool(self, *, home="Blacksmith", timeout_ms=30000):
        self.w.pickup_calls += 1
        self.w.being_upgraded = None
        self.w.tool_upgrade_days_left = 0
        return {"ok": True, "status": "ok", "reason": "已取回（假世界）"}


class NoEffectClient(BaseClient):
    """回执 ok、世界一动不动（通道①正向）。"""

    def upgrade_tool(self, which, *, timeout_ms=60000):
        self.w.upgrade_calls.append(str(which))
        return {"ok": True, "status": "ok", "reason": "回执 ok（世界没动）"}

    def pickup_tool(self, *, home="Blacksmith", timeout_ms=30000):
        self.w.pickup_calls += 1
        return {"ok": True, "status": "ok", "reason": "回执 ok（世界没动）"}


class LyingFailClient(BaseClient):
    """回执 ok=false，但世界真的升级了（通道①反向：必须认）。"""

    def upgrade_tool(self, which, *, timeout_ms=60000):
        kind = str(which)
        self.w.upgrade_calls.append(kind)
        self._do_upgrade(kind)
        return {"ok": False, "status": "error", "reason": "回执 ok=false（世界却真变了）"}


class MoneyOnlyClient(BaseClient):
    """回执 ok、只扣钱：没升级、没在途、等级不变。"""

    def upgrade_tool(self, which, *, timeout_ms=60000):
        self.w.upgrade_calls.append(str(which))
        self.w.money -= 2000
        return {"ok": True, "status": "ok", "reason": "扣了钱没升级"}


class ClearNoGainClient(BaseClient):
    """取回：清掉在途但背包没多出工具。"""

    def pickup_tool(self, *, home="Blacksmith", timeout_ms=30000):
        self.w.pickup_calls += 1
        self.w.being_upgraded = None
        self.w.tool_upgrade_days_left = 0
        return {"ok": True, "status": "ok", "reason": "在途清了但工具没进包"}


class RaisedClient(TL.FakeClient):
    def __init__(self, w, status):
        super().__init__(w)
        self._status = status

    def upgrade_tool(self, which, *, timeout_ms=60000):
        raise BR.BridgeError(f"Mod 拒绝：{self._status}", status=self._status)


# ---------------------------------------------------------------- A 段：静态口径
def case_a():
    print("\n[A] 口径/范围")
    ver = None
    try:
        import json
        with open(os.path.join(ROOT, "mod", "AgentFarm.Bridge", "manifest.json"), encoding="utf-8") as fh:
            ver = json.load(fh).get("Version")
    except Exception as exc:  # noqa: BLE001
        note("A-version", False, f"读不到 manifest：{exc}")
    note("A1 未 bump（本批冻结前应仍 0.7.36）", ver == "0.7.36", f"manifest Version={ver}")
    try:
        exp = open(os.path.join(ROOT, "brain", "agentfarm", "bridge.py"), encoding="utf-8").read()
        line = [ln for ln in exp.splitlines() if "MOD_VERSION_EXPECTED" in ln][0].strip()
        note("A2 MOD_VERSION_EXPECTED", '"0.7.36"' in line, line[:80])
    except Exception as exc:  # noqa: BLE001
        note("A2 MOD_VERSION_EXPECTED", False, f"{exc}")

    check("A3 JUSTIFIED_END_REASONS 未变（无 tool_upgrade*）",
          tuple(getattr(LR, "JUSTIFIED_END_REASONS", ())) == ("night", "stamina", "no_work"),
          repr(getattr(LR, "JUSTIFIED_END_REASONS", None)))
    check("A4 TOOL_UPGRADE_MAX_PER_DAY == 1", int(getattr(LR, "TOOL_UPGRADE_MAX_PER_DAY", -1)) == 1)
    check("A5 价格/材料/暂停表与卡面一致",
          FW.UPGRADE_PRICES == {0: 2000, 1: 5000, 2: 10000, 3: 25000}
          and FW.UPGRADE_KINDS == ("axe", "pickaxe", "hoe", "can", "pan")
          and FW.UPGRADE_SUSPENDS.get("hoe") == ("till_area",)
          and FW.UPGRADE_SUSPENDS.get("can") == ("water_area",)
          and FW.UPGRADE_SUSPENDS.get("axe") == ("clear_area",),
          f"prices={FW.UPGRADE_PRICES}")
    check("A6 长跑暂停表与 farmwork 表同口径",
          dict(getattr(LR, "TOOL_UPGRADE_SUSPENDED", {})) == dict(FW.UPGRADE_SUSPENDS))
    check("A7 bridge 薄包装齐（upgrade_tool/pickup_tool）",
          hasattr(BR.BridgeClient, "upgrade_tool") and hasattr(BR.BridgeClient, "pickup_tool"))
    src_bridge = open(os.path.join(ROOT, "brain", "agentfarm", "bridge.py"), encoding="utf-8").read()
    check("A8 bridge 包装透传 tool / timeout_ms",
          "def upgrade_tool(self, tool: str" in src_bridge
          and "def pickup_tool(self, *, timeout_ms: int" in src_bridge
          and '"upgrade_tool",' in src_bridge and "self.exec_skill(\"pickup_tool\"" in src_bridge
          and '{"tool": str(tool)}' in src_bridge,
          "multi-line exec_skill(upgrade_tool) + 单行 pickup")

    # checks 键集：跑一个空世界日
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    _, _, _, _, rep = run_day(w)
    keys = set((rep.checks or {}).keys()) if rep is not None else set()
    check("A9 checks 键集仍是 10 键（不许新增可洗白键）",
          keys == {"slept_by_us", "no_blocking_modal", "no_hard_failures", "unreachable_within_bound",
                   "refused_within_bound", "no_unmet_stages", "crops_watered", "watered_outdoor",
                   "day_justified", "zero_action_evidenced"},
          f"keys={sorted(keys)}")


# ---------------------------------------------------------------- B 通道①：回执洗白
def case_b1():
    print("\n[B1] 回执洗白（upgrade）")
    w = TL.FakeWorld(weeds=0, seeds=0, money=5000)
    copper(w)
    w.location = "Blacksmith"
    worker = FarmWorker(NoEffectClient(w), log=lambda _s: None, pause=lambda _s: None)
    st = worker.upgrade_tool("axe")
    check("B1a 回执 ok 但世界没变 ⇒ failed", st.ok is False and st.code == "failed",
          f"ok={st.ok} code={st.code} reason={st.reason[:100]}")
    check("B1b 理由点明“观测上什么都没变”", "观测" in st.reason and "没变" in st.reason, st.reason[:120])
    check("B1c 钱/等级/在途都没变", w.money == 5000 and w.tool_tiers.get("axe") == 0 and w.being_upgraded is None)

    w2 = TL.FakeWorld(weeds=0, seeds=0, money=5000)
    copper(w2)
    w2.location = "Blacksmith"
    st2 = FarmWorker(LyingFailClient(w2), log=lambda _s: None, pause=lambda _s: None).upgrade_tool("axe")
    check("B1d 反向：回执 ok=false 但世界真升级 ⇒ 必须认（ok=True）", st2.ok is True,
          f"ok={st2.ok} reason={st2.reason[:120]}")

    w3 = TL.FakeWorld(weeds=0, seeds=0, money=5000)
    copper(w3)
    w3.location = "Blacksmith"
    st3 = FarmWorker(MoneyOnlyClient(w3), log=lambda _s: None, pause=lambda _s: None).upgrade_tool("axe")
    note("B1e [INFO] 只扣钱没升级时脑侧判 ok（判据含 money_down）",
         st3.ok is True, f"ok={st3.ok} reason={st3.reason[:140]}")


def case_b2():
    print("\n[B2] 回执洗白（pickup）")
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    w.location = "Blacksmith"
    w.being_upgraded = {"kind": "axe", "name": "Axe"}
    w.tool_upgrade_days_left = 0
    st = FarmWorker(NoEffectClient(w), log=lambda _s: None, pause=lambda _s: None).pickup_tool()
    check("B2a 取回回执 ok 但世界没变 ⇒ failed", st.ok is False and st.code == "failed",
          f"ok={st.ok} code={st.code}")
    w2 = TL.FakeWorld(weeds=0, seeds=0, money=0)
    w2.location = "Blacksmith"
    w2.being_upgraded = {"kind": "axe", "name": "Axe"}
    w2.tool_upgrade_days_left = 0
    before = len(w2.inventory)
    st2 = FarmWorker(ClearNoGainClient(w2), log=lambda _s: None, pause=lambda _s: None).pickup_tool()
    note("B2b [NIT] 在途清了但背包没多出工具时脑侧仍判 ok", st2.ok is True,
         f"ok={st2.ok} inventory {before}->{len(w2.inventory)} reason={st2.reason[:120]}")


# ---------------------------------------------------------------- C 通道②：钱不够
def case_c():
    print("\n[C] 钱不够 / 材料不够")
    w = TL.FakeWorld(weeds=0, seeds=0, money=1999)
    copper(w)
    run, _, _ = mk(w)
    plan = run._tool_upgrade_plan(w.obs())
    check("C1a 钱 1999 < 2000 ⇒ 计划 None（不跑腿）", plan is None, repr(plan))
    rep = TL.DayReport(day_key=("summer", 13, 1), started_at=0.0)
    moved = run._maybe_tool_upgrade(w.obs(), rep)
    check("C1b 不发起请求、钱一分不动", moved is False and w.upgrade_calls == [] and w.money == 1999,
          f"upgrade_calls={w.upgrade_calls} money={w.money}")
    check("C1c 留痕 tool_upgrade_skipped", len(events(run, "tool_upgrade_skipped")) == 1)

    w2 = TL.FakeWorld(weeds=0, seeds=0, money=1999)
    copper(w2)
    w2.location = "Blacksmith"
    st = FarmWorker(RaisedClient(w2, "no_money"), log=lambda _s: None, pause=lambda _s: None).upgrade_tool("axe")
    check("C2 Mod 回 no_money ⇒ failed 且钱不动",
          st.ok is False and w2.money == 1999 and st.status == "no_money",
          f"ok={st.ok} status={st.status} money={w2.money}")

    w3 = TL.FakeWorld(weeds=0, seeds=0, money=5000)
    run3, _, _ = mk(w3)
    plan3 = run3._tool_upgrade_plan(w3.obs())
    check("C3 钱够但材料 0 ⇒ 计划 None", plan3 is None, repr(plan3))
    copper(w3, stack=5)
    plan4 = run3._tool_upgrade_plan(w3.obs())
    check("C4 钱 + 5 锭 ⇒ 计划 upgrade axe",
          bool(plan4) and plan4.get("action") == "upgrade" and plan4.get("kind") == "axe"
          and plan4.get("price") == 2000, repr(plan4))


# ---------------------------------------------------------------- D 通道③：在途再买
def case_d():
    print("\n[D] 在途再买 / 取回优先")
    w = TL.FakeWorld(weeds=0, seeds=0, money=5000)
    copper(w)
    w.being_upgraded = {"kind": "hoe", "name": "Hoe"}
    w.tool_upgrade_days_left = 1
    run, _, _ = mk(w)
    plan = run._tool_upgrade_plan(w.obs())
    check("D1 在途 daysLeft=1 ⇒ 计划 wait", bool(plan) and plan.get("action") == "wait", repr(plan))
    rep = TL.DayReport(day_key=("summer", 13, 1), started_at=0.0)
    run._maybe_tool_upgrade(w.obs(), rep)
    check("D2 在途不许再买（0 请求、钱不变）",
          w.upgrade_calls == [] and w.money == 5000, f"calls={w.upgrade_calls} money={w.money}")
    check("D3 留痕 tool_upgrade_skipped{action:wait}",
          any(e.get("action") == "wait" for e in events(run, "tool_upgrade_skipped")),
          repr([e.get("action") for e in events(run, "tool_upgrade_skipped")]))

    w.location = "Blacksmith"
    st = FarmWorker(TL.FakeClient(w), log=lambda _s: None, pause=lambda _s: None).upgrade_tool("axe")
    check("D4 worker 层在途 ⇒ failed 且 0 请求", st.ok is False and w.upgrade_calls == [],
          f"ok={st.ok} code={st.code} calls={w.upgrade_calls}")

    w2 = TL.FakeWorld(weeds=0, seeds=0, money=5000)
    copper(w2)
    w2.being_upgraded = {"kind": "axe", "name": "Axe"}
    w2.tool_upgrade_days_left = None          # 键缺失 ⇒ 不许当 0
    run2, _, _ = mk(w2)
    plan2 = run2._tool_upgrade_plan(w2.obs())
    check("D5 daysLeft 缺失 ⇒ fail-closed wait（不许当 0 去取回）",
          bool(plan2) and plan2.get("action") == "wait" and "读不到" in str(plan2.get("reason")),
          repr(plan2))

    w3 = TL.FakeWorld(weeds=0, seeds=0, money=5000)
    copper(w3)
    w3.being_upgraded = {"kind": "axe", "name": "Axe"}
    w3.tool_upgrade_days_left = 0
    w3.tool_tiers = {"axe": 1, "hoe": 0, "can": 0}
    run3, _, _ = mk(w3)
    plan3 = run3._tool_upgrade_plan(w3.obs())
    check("D6 daysLeft=0 + 有空格 ⇒ 计划 pickup（取回优先）",
          bool(plan3) and plan3.get("action") == "pickup", repr(plan3))
    w3.inventory = [{"slot": i, "id": "X", "qualifiedId": f"(O)9{i}", "name": "x",
                     "stack": 1, "isTool": False} for i in range(w3.inventory_capacity)]
    plan4 = run3._tool_upgrade_plan(w3.obs())
    check("D7 daysLeft=0 + 背包满 ⇒ 计划 need_slot",
          bool(plan4) and plan4.get("action") == "need_slot", repr(plan4))


# ---------------------------------------------------------------- E 通道④：选错工具
def case_e():
    print("\n[E] 选错工具 / Mod 侧规则")
    w = TL.FakeWorld(weeds=0, seeds=0, money=5000)
    copper(w)
    w.location = "Blacksmith"
    st = FarmWorker(RaisedClient(w, "tool_not_offered"), log=lambda _s: None, pause=lambda _s: None).upgrade_tool("axe")
    check("E1 店里只有别的工具 ⇒ tool_not_offered、钱不动",
          st.ok is False and st.status == "tool_not_offered" and w.money == 5000,
          f"ok={st.ok} status={st.status} money={w.money}")
    rules_path = os.path.join(ROOT, "mod", "AgentFarm.Bridge", "ToolUpgradeRules.cs")
    rules = open(rules_path, encoding="utf-8").read() if os.path.exists(rules_path) else ""
    check("E2 Select 要求同 kind + tierBefore+1 + 唯一命中",
          "SameKind" in rules and "Tier == tierBefore + 1" in rules and "hits.Count == 1" in rules,
          f"rules 长度={len(rules)}")
    check("E3 Precheck 顺序：already_upgrading/still_working/read_only/no_money/no_trade_item",
          all(tok in rules for tok in ("StatusAlreadyUpgrading", "StatusStillWorking", "StatusReadOnly",
                                       "StatusNoMoney", "StatusNoTradeItem")))
    check("E4 NormalizeKind 归一 wateringcan/fishingrod",
          "wateringcan" in rules and '"can"' in rules and "fishingRod" in rules)
    # 源码级：U2 兜底按价格+材料匹配、不按 kind 过滤
    src = open(os.path.join(ROOT, "mod", "AgentFarm.Bridge", "ToolUpgradeSkill.cs"), encoding="utf-8").read() if os.path.exists(
        os.path.join(ROOT, "mod", "AgentFarm.Bridge", "ToolUpgradeSkill.cs")) else ""
    fallback = src[src.find("MatchByExpectedData"):src.find("ReadIntProperty")]
    note("E5 [NIT] MatchByExpectedData 只按 price+trade 匹配、不加 kind 过滤",
         "SameKind" not in fallback and "offers[i].Price != price" in fallback,
         "U2 兜底路径可能选中同类价格/材料的别的工具条目（源码级；真机可达性未证）")


# ---------------------------------------------------------------- F 通道⑤/A：在途两天
def case_f():
    print("\n[F] 在途两天：诚实留痕 / 不吃 gave_up / 不洗白")
    # F1: axe 在途（days=2）+ 田里有可清障物 —— 一天
    w = TL.FakeWorld(weeds=4, seeds=0, money=3000)
    w.being_upgraded = {"kind": "axe", "name": "Axe"}
    w.tool_upgrade_days_left = 2
    run, _, _, code, rep = run_day(w)
    blocked = events(run, "tool_upgrade_blocked_work")
    ups = events(run, "upgrade_tool")
    check("F1a 在途期不误报升级成功", ups == [], f"upgrade_tool={ups}")
    check("F1b 在途期不许把暂停阶段算 hard failure",
          rep is not None and rep.checks.get("no_hard_failures") is True and rep.failed_steps == 0,
          f"failed_steps={getattr(rep, 'failed_steps', None)} checks={getattr(rep, 'checks', None)}")
    obs = w.obs()
    pl = plot(sorted(w.tillable))
    left = {t: len(run._leftover(t, obs, pl)) for t in
            ("clear_area", "till_area", "plant_area", "water_area", "harvest", "clear_dead")}
    total_left = sum(left.values())
    check("F1c1 _leftover 如实：暂停阶段的目标不被扣减", left["clear_area"] > 0, f"leftover={left}")
    check("F1c2 no_unmet_stages 与 _leftover 诚实口径一致（无阶段记录也不许丢）",
          rep is not None and bool(rep.checks.get("no_unmet_stages")) == (total_left == 0),
          f"leftover={left} no_unmet={rep.checks.get('no_unmet_stages') if rep else None} "
          f"stages={[(s.get('stage'), s.get('leftover')) for s in (rep.stages if rep else [])]}")
    check("F1d 不吃 gave_up 配额（harvest_gave_up 空）",
          getattr(rep, "harvest_gave_up", []) == [], repr(getattr(rep, "harvest_gave_up", None)))
    check("F1e 在途 wait 日必须留痕（blocked_work 或 skipped 至少一条）",
          bool(blocked) or bool(events(run, "tool_upgrade_skipped")),
          f"blocked_work={len(blocked)} skipped={len(events(run, 'tool_upgrade_skipped'))} "
          f"due={run._tool_upgrade_due(obs)} ended_by={getattr(rep, 'ended_by', None)} "
          f"reason={str(getattr(rep, 'ended_reason', ''))[:90]}")

    # F2: 两天
    w2 = TL.FakeWorld(weeds=4, seeds=0, money=3000)
    w2.being_upgraded = {"kind": "axe", "name": "Axe"}
    w2.tool_upgrade_days_left = 2
    run2, _, _ = mk(w2, target_days=2, max_days=2)
    run2.run()
    per_day = {}
    for e in events(run2, "tool_upgrade_blocked_work"):
        per_day[e.get("t")] = per_day.get(e.get("t"), 0) + 1
    check("F2a 两天内 blocked_work 每天至多一条", all(v <= 1 for v in per_day.values()),
          f"per_t={per_day}")
    check("F2b 两天都不 VERIFIED", all(not d.verified for d in run2.days),
          repr([(d.verified, d.ended_by) for d in run2.days]))

    # F3: 壶在途 + daysLeft=0 + 窗口有干作物 ⇒ 取回会不会被“紧急农活优先”永久挡住
    w3 = TL.FakeWorld(weeds=0, seeds=0, money=3000)
    w3.being_upgraded = {"kind": "can", "name": "Watering Can"}
    w3.tool_upgrade_days_left = 0
    w3.dirt = {(60, 10)}
    w3.crops = {(60, 10): {"ripe": False, "watered": False}}
    w3.tool_tiers = {"axe": 0, "hoe": 0, "can": 0}
    run3, _, _ = mk(w3, target_days=2, max_days=2)
    run3.run()
    pickups = getattr(w3, "pickup_calls", 0)
    check("F3a 壶在途做完 + 窗口干作物 ⇒ 仍必须去取回（否则死锁）",
          pickups >= 1, f"pickup_calls={pickups} ended={[(d.ended_by, str(d.ended_reason)[:40]) for d in run3.days]}")
    obs3 = w3.obs()
    plan3 = run3._tool_upgrade_plan(obs3)
    due3 = run3._tool_upgrade_due(obs3)
    check("F3c 计划=取回但 due=False ⇒ 取回永远到不了（死锁根因）",
          not (isinstance(plan3, dict) and plan3.get("action") == "pickup" and due3 is False),
          f"plan={plan3} due={due3}")
    note("F3b [判定] 取回被挡时的当日理由",
         pickups >= 1, f"reason0={str(run3.days[0].ended_reason)[:110]}")

    # F4: due 与紧急农活
    w4 = TL.FakeWorld(weeds=0, seeds=0, money=3000)
    copper(w4)
    w4.dirt = {(60, 10)}
    w4.crops = {(60, 10): {"ripe": True, "watered": True}}
    run4, _, _ = mk(w4)
    check("F4a 有熟作物 ⇒ due False（先干农活）", run4._tool_upgrade_due(w4.obs()) is False)
    w4.crops = {}
    w4.dirt = set()
    check("F4b 没紧急农活 + 可升级 ⇒ due True", run4._tool_upgrade_due(w4.obs()) is True)

    # F5: 每天最多一次
    w5 = TL.FakeWorld(weeds=0, seeds=0, money=3000)
    copper(w5)
    run5, _, _ = mk(w5)
    rep5 = TL.DayReport(day_key=("summer", 13, 1), started_at=0.0)
    first = run5._maybe_tool_upgrade(w5.obs(), rep5)
    second = run5._maybe_tool_upgrade(w5.obs(), rep5)
    check("F5 每天最多一次（第二次不动作）",
          first is True and second is False and len(w5.upgrade_calls) == 1,
          f"first={first} second={second} calls={w5.upgrade_calls}")

    # F6: 背包满取回 ⇒ no_slot，工具不许“丢”
    w6 = TL.FakeWorld(weeds=0, seeds=0, money=0)
    w6.location = "Blacksmith"
    w6.being_upgraded = {"kind": "axe", "name": "Axe"}
    w6.tool_upgrade_days_left = 0
    w6.inventory = [{"slot": i, "id": "X", "qualifiedId": f"(O)9{i}", "name": "x",
                     "stack": 1, "isTool": False} for i in range(w6.inventory_capacity)]
    st = FarmWorker(TL.FakeClient(w6), log=lambda _s: None, pause=lambda _s: None).pickup_tool()
    check("F6a 背包满 ⇒ code=no_slot（fail-closed）", st.code == "no_slot", f"code={st.code} ok={st.ok}")
    check("F6b 工具不许因取回失败消失（在途仍在、0 请求）",
          w6.being_upgraded is not None and w6.pickup_calls == 0,
          f"being={w6.being_upgraded} pickup_calls={w6.pickup_calls}")


# ---------------------------------------------------------------- G 通道⑥：口径
def case_g():
    print("\n[G] checks/_leftover 口径污染")
    w = TL.FakeWorld(weeds=0, seeds=0, money=3000)
    w.being_upgraded = {"kind": "can", "name": "Watering Can"}
    w.tool_upgrade_days_left = 2
    w.dirt = {(60, 10), (61, 10)}
    w.crops = {(60, 10): {"ripe": False, "watered": False},
               (61, 10): {"ripe": False, "watered": False}}
    obs = w.obs()
    pl = plot(sorted(w.dirt))
    run, _, _ = mk(w)
    left = run._leftover("water_area", obs, pl)
    check("G1 暂停阶段 _leftover 不被扣减（仍报没做完）", len(left) > 0, f"leftover={left}")
    tiles = run._stage_tiles("water_area", obs, pl)
    check("G2 暂停阶段目标池为空（如实：工具不在身上）", tiles == [], repr(tiles))
    reasons = run.work_reasons(obs)
    check("G3 壶暂停期守卫不再拿“没浇水”钉死（理由里无该条）",
          not [r for r in reasons if "没浇水" in r], repr(reasons))

    # 升级成功 + 有剩余农活 ⇒ 不许 VERIFIED
    w2 = TL.FakeWorld(weeds=0, seeds=0, money=3000)
    copper(w2)
    w2.dirt = {(60, 10)}
    w2.crops = {(60, 10): {"ripe": False, "watered": False}}
    w2.being_upgraded = {"kind": "can", "name": "Watering Can"}   # 壶不在 ⇒ 浇不了
    w2.tool_upgrade_days_left = 0
    run2, _, _, _, rep2 = run_day(w2)
    check("G4 有未浇活苗 + 壶在途 ⇒ 当天不许 VERIFIED",
          rep2 is not None and rep2.verified is False, f"verified={getattr(rep2, 'verified', None)} "
                                                       f"ended={getattr(rep2, 'ended_by', None)}")


# ---------------------------------------------------------------- H 通道⑧：真机可复核性
def case_h():
    print("\n[H] 真机序列可复核性")
    il = os.path.join(ROOT, "docs", "_il-tool-upgrade.md")
    il_src = open(il, encoding="utf-8").read() if os.path.exists(il) else ""
    check("H1 IL 文档存在且写了前置条件/真机调试步骤",
          bool(il_src) and "前置条件" in il_src and "首次真机" in il_src,
          f"{len(il_src)} 字符")
    logs = os.path.join(ROOT, "logs")
    hits = []
    if os.path.isdir(logs):
        hits = [n for n in os.listdir(logs) if "tool" in n.lower() or "upgrade" in n.lower()]
    note("H2 [无法判定] 真机未跑：没有前置/后置观测与 upgrade_tool 中间日志",
         not hits, f"logs 里 tool/upgrade 相关文件={hits}")
    src = open(os.path.join(ROOT, "mod", "AgentFarm.Bridge", "ToolUpgradeSkill.cs"), encoding="utf-8").read() if os.path.exists(
        os.path.join(ROOT, "mod", "AgentFarm.Bridge", "ToolUpgradeSkill.cs")) else ""
    check("H3 Mod 回执带可复核字段（moneyBefore/After/price/trade/tierAfter/actedEvidence）",
          all(tok in src for tok in ("MoneyBefore", "MoneyAfter", "Price =", "TradeItem =",
                                     "TierAfter", "ActedEvidence")),
          f"src {len(src)} 字符")


CASES = {
    "A": case_a,
    "B1": case_b1,
    "B2": case_b2,
    "C": case_c,
    "D": case_d,
    "E": case_e,
    "F": case_f,
    "G": case_g,
    "H": case_h,
}


def main() -> int:
    print(f"task-206 探针 | ROOT={ROOT} | has_205={has_205()}")
    if not has_205():
        print("该树没有 task-205 接口（pre 树）⇒ 只跑静态段，其余 SKIP")
    for name, fn in CASES.items():
        try:
            if name != "A" and not (has_205() or os.environ.get("T206_FORCE")):
                skip(f"{name} 段", "pre 树无 task-205 接口")
                continue
            fn()
        except Exception:  # noqa: BLE001
            global FAIL
            FAIL += 1
            print(f"  FAIL {name} 段抛异常")
            traceback.print_exc()
    print(f"\n=== PASS={PASS} FAIL={FAIL} SKIP={SKIP} | info/WARN={len(NOTES)} ===")
    for tag, ok, detail in NOTES:
        print(f"  [{'info' if ok else 'WARN'}] {tag} :: {detail}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
