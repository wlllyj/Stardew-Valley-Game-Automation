r"""task-103 对抗脚本：task-102（`9b09735`，0.7.28 空格死锁 + 早睡防线）能不能被打穿。

全部用**真代码**（真 `FarmWorker` + 真 `LongRun` + 进程内 `tools/verify-run3.py`），只写 scratch/。

B 段（复跑 run8 的两个病灶）：
  B3  背包 0 空格 + 钱 188g + 无种子 + 石头大叠 + 农场有干作物 ⇒ 卖一叠腾格（why=need_slot）
      然后当天买到**当季在售**种子；buy 尝试 ≤3
  B4  钱够但买不到（item_not_sold）+ 干作物够不着 ⇒ 不许 no_work 睡过去 / 不许 day+1 而 0 动作

C 段（朝修法本身进攻）：
  C5  把 `no_space` 说成成功（回执 ok 但钱/背包没变）⇒ 会不会被当买到了
  C6  腾格卖出会不会卖掉**种子/工具/武器**（结构性排除 + 负例）
  C7  腾格卖出会不会破 K=10（`belowKeep` 是否如实记账）
  C8  连续两天 no_space ⇒ 每天重试几次（有界性跨天）
  C9  睡前清理模态失败（异常 / ok=False）⇒ 是否 fail-closed（不许假装睡成功）
  C10 两条卖货门闸同时成立（钱 < 5×单价 但 ≥ 单价 + 0 空格）⇒ 是否无限循环/重复卖

用法：`python scratch\_t103_adv.py`
"""
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _t92_adv import TL, VR, as_ledger, brief  # noqa: E402

from agentfarm.bridge import BridgeError          # noqa: E402
from agentfarm.farmwork import (                  # noqa: E402
    FarmWorker, StepResult, player_free_slots, surplus_sell_plan,
    SURPLUS_MATERIAL_IDS,
)

ROOT = Path(__file__).resolve().parent.parent
JDIR = ROOT / "scratch" / "_t103_j"
_JSEQ = {"n": 0}

CHECKS: list[tuple[bool, str]] = []


def check(ok: bool, msg: str) -> None:
    CHECKS.append((bool(ok), msg))
    print(f"  [{'PASS' if ok else 'FAIL'}] {msg}")


def mat(slot: int, iid: str, name: str, stack: int, *, tool: bool = False) -> dict:
    return {"slot": slot, "id": iid, "qualifiedId": f"({'T' if tool else 'O'}){iid}",
            "name": name, "stack": stack, "isTool": tool}


class CapClient(TL.FakeClient):
    """`FakeClient` + **背包含量语义** + 出货箱：真 `FarmWorker` 的 buy/sell 才能跑。

    容量满且没有同类堆叠可并入 ⇒ 复刻真桥的 `no_inventory_space`（脑侧应映射成 `no_space`）。
    """

    def __init__(self, world: TL.FakeWorld, *, sell_mode: str = "ship",
                 refuse_sleep_modals: bool = False) -> None:
        super().__init__(world)
        self.sell_mode = sell_mode
        self.refuse_sleep_modals = refuse_sleep_modals
        self.bin: list[dict] = []
        self.sleep_calls = 0

    def buy(self, item, count=10, *, shop="SeedShop", timeout_ms=25000):
        """**复刻桥的返回形状（dict）** + 按**请求的那个 id** 入库（`FakeWorld.buy` 硬编码 472）。"""
        w = self.w
        item = str(item)
        want = "".join(ch for ch in item if ch.isdigit())
        offers = [dict(o) for o in w.buy_offers]
        w.buy_calls.append({"item": item, "count": int(count)})
        if offers and not any(want == "".join(ch for ch in str(o.get("id") or "") if ch.isdigit())
                              for o in offers):
            return {"ok": False, "status": "item_not_sold",
                    "reason": f"商店「{shop}」里没有「{item}」", "availableItems": offers}
        if w.buy_fail_status:
            return {"ok": False, "status": w.buy_fail_status,
                    "reason": f"没成交（Mod status={w.buy_fail_status}）", "availableItems": offers}
        same = next((i for i in w.inventory
                     if want and want in (str(i.get("id") or ""), str(i.get("qualifiedId") or ""))), None)
        free = int(w.inventory_capacity) - len(w.inventory)
        if same is None and free <= 0:
            return {"ok": False, "status": "no_inventory_space",
                    "reason": "没成交（Mod status=no_inventory_space）", "availableItems": offers}
        row = next((o for o in offers
                    if want == "".join(ch for ch in str(o.get("id") or "") if ch.isdigit())), None)
        price = int((row or {}).get("price") or w.buy_price)
        can = min(int(count), int(w.money) // price) if price > 0 else int(count)
        if can < 1:
            return {"ok": False, "status": "failed",
                    "reason": f"钱不够（{w.money}g < {price}g）", "availableItems": offers}
        w.money -= price * can
        if same is not None:
            same["stack"] = int(same.get("stack") or 0) + can
        else:
            slot_no = max([int(i.get("slot", 0)) for i in w.inventory] + [-1]) + 1
            w.inventory.append({"slot": slot_no, "id": want, "qualifiedId": item,
                                "name": str((row or {}).get("name") or "Wheat Seeds"),
                                "stack": can, "isTool": False})
        w.buys.append(can)
        return {"ok": True, "status": "ok",
                "reason": f"买到 {can} 个，钱 {w.money}g", "availableItems": offers}

    def sell(self, slot, *, whitelist=None, timeout_ms=8000):
        """**复刻桥的返回形状（dict）**；判据在 `FarmWorker.sell` 里靠观测差分，不靠回执。"""
        w = self.w
        slot = int(slot)
        allow = [str(x) for x in (whitelist or [])]
        item = next((i for i in w.inventory if int(i.get("slot", -1)) == slot), None)
        if self.sell_mode != "ship":
            return {"ok": False, "status": self.sell_mode,
                    "reason": f"假世界 sell 失败（{self.sell_mode}）"}
        if item is None:
            return {"ok": False, "status": "empty_slot", "reason": "槽位是空的"}
        qid = str(item.get("qualifiedId") or item.get("id") or "")
        if qid not in allow:
            return {"ok": False, "status": "not_whitelisted", "reason": f"{qid} 不在白名单里"}
        w.inventory.remove(item)
        self.bin.append(dict(item))
        return {"ok": True, "status": "ok", "reason": "已放进出箱（钱要下一次 NewDay 才结算）"}

    def sleep(self, *, timeout_ms=None):
        self.sleep_calls += 1
        if self.refuse_sleep_modals and (self.w.current_ui() or {}).get("activeMenu"):
            raise BridgeError("假世界：有模态挡着，睡不成", status="ui_modal")
        self.w.sleep()
        return {"ok": True, "status": "ok", "day": self.w.day, "timeOfDay": self.w.time_of_day}


class LiveFarmWorld(TL.FakeWorld):
    """`farm` 块与真实世界状态一致的假世界（task-96 的 `farm_scan()`）。"""

    def obs(self):
        o = super().obs()
        o["farm"] = self.farm_scan()
        return o


class MyopicWorld(TL.FakeWorld):
    """只有玩家周围 radius 格看得见（`farm` 块由调用方按真机形状显式给，**不**自动扫描）。"""

    def __init__(self, radius: int = 3, **kw) -> None:
        super().__init__(**kw)
        self.radius = int(radius)

    def obs(self):
        o = super().obs()
        pt = tuple(self.player_tile)
        o["location"]["tillable"] = [t for t in o["location"]["tillable"]
                                     if abs(t[0] - pt[0]) + abs(t[1] - pt[1]) <= self.radius]
        o["location"]["tiles"] = [t for t in o["location"]["tiles"]
                                  if abs(t["tile"][0] - pt[0]) + abs(t["tile"][1] - pt[1]) <= self.radius]
        return o


class MyopicLiveFarmWorld(MyopicWorld):
    """窗口 + `farm` 块 = 与世界一致的 `farm_scan()`。"""

    def obs(self):
        o = super().obs()
        o["farm"] = self.farm_scan()
        return o


class UnreachableClient(CapClient):
    """真机 run8 形态：某些格子 `move_to` 直接回 `unreachable`（够不着）。"""

    def __init__(self, world, *, unreachable=(), **kw) -> None:
        super().__init__(world, **kw)
        self.unreachable = {tuple(t) for t in unreachable}

    def move_to(self, x, y, *, timeout_ms=None, allow_bed=None):
        if (int(x), int(y)) in self.unreachable:
            raise BridgeError(f"假世界：({x},{y}) 走不到（unreachable）", status="unreachable")
        return super().move_to(x, y, timeout_ms=timeout_ms, allow_bed=allow_bed)


def run_real(w, client=None, *, days: int = 1):
    client = client if client is not None else CapClient(w)
    JDIR.mkdir(parents=True, exist_ok=True)
    _JSEQ["n"] += 1
    jpath = JDIR / f"case{_JSEQ['n']:02d}.jsonl"
    if jpath.exists():
        jpath.unlink()
    run = TL.make_run(w, target_days=1, max_days=days, journal_path=str(jpath),
                      client_factory=lambda: client,
                      worker_factory=lambda c: FarmWorker(c, log=lambda _s: None,
                                                          pause=lambda _s: None))
    run.run()
    run._probe_journal = str(jpath)
    return run, client


def ev(run, name: str) -> list[dict]:
    return [e for e in run.entries if e.get("event") == name]


def report(tag: str, run) -> None:
    ends = ev(run, "day_end")
    print(f"\n--- {tag} ---")
    for d in ends:
        print(f"  day={d['final'].get('day')} day_after={d.get('day_after')} "
              f"ended_by={d.get('ended_by')!r} reason={str(d.get('ended_reason'))[:110]!r}")
        print(f"  verified={d.get('verified')} checks={d.get('checks')} "
              f"ok_steps={d.get('ok_steps')} failed={d.get('failed_steps')} "
              f"slept_without_work={d.get('slept_without_work')}")
    for name in ("sell", "surplus_sell", "surplus_sell_skip", "buy", "buy_no_space",
                 "slept_without_work", "modal_dismissed", "modal_dismiss_failed", "sleep",
                 "stuck_flush", "stuck_flush_skipped", "no_day_progress"):
        got = ev(run, name)
        if got:
            print(f"  journal {name} ×{len(got)}: "
                  f"{[{k: v for k, v in e.items() if k in ('why','code','ok','attempt','limit','slot','qid','stack','below_keep','tried','sold','menu','where')} for e in got]}")
    jpath = getattr(run, "_probe_journal", None)
    if jpath and Path(jpath).exists():
        rows = VR.load(jpath)
        ok, summary = VR.report(rows, target_days=1)
        print(f"  [工具·真账本 {Path(jpath).name} {len(rows)} 行] ok={ok} verdict={summary.get('verdict')} "
              f"problems={json.dumps(summary.get('problems'), ensure_ascii=False)}")
        print(f"  [工具·真账本] infos={json.dumps(summary.get('infos'), ensure_ascii=False)}")
    elif ends:
        as_ledger(run, ends[-1])


# ---------------------------------------------------------------- B 段
def b3_slot_deadlock() -> None:
    print("\n" + "=" * 78)
    print("B3  0 空格 + 钱 188g + 无种子 + 石头 200 一叠 + 农场有干作物")
    w = LiveFarmWorld(weeds=0, seeds=0, money=188)
    w.buy_offers = [{"id": "(O)483", "name": "Wheat Seeds", "price": 10}]
    w.buy_price = 10
    w.inventory.append(mat(6, "390", "Stone", 200))
    w.inventory_capacity = len(w.inventory)              # 0 空格
    w.dirt.add((60, 10))
    w.crops[(60, 10)] = {"ripe": False, "watered": False, "dead": False}
    run, client = run_real(w)
    report("B3", run)
    plain = [e for e in ev(run, "surplus_sell") if e.get("why") == "need_slot"]
    check(bool(plain), f"出现 `surplus_sell{{why:'need_slot'}}`（{len(plain)} 条）")
    check(all(e.get("below_keep") is True for e in ev(run, "sell")),
          f"单一大叠 ⇒ 如实标 `below_keep`（sell={[e.get('below_keep') for e in ev(run, 'sell')]}）")
    buys = ev(run, "buy")
    check(len(buys) <= 3, f"buy 尝试 {len(buys)} ≤ 3")
    real_ok = [b for b in buys if b.get("ok")]
    check(bool(real_ok) and real_ok[-1].get("item") == "(O)483",
          f"当天真买到**当季在售**种子：{[(b.get('item'), b.get('ok'), b.get('after', {}).get('money')) for b in buys]}")
    check(client.bin and len(client.bin[0]) > 0, f"石头真的进了出货箱（{len(client.bin)} 叠）")
    check(w.money < 188 and any(str(x.get("id")) == "483" for x in w.inventory),
          f"钱 188 → {w.money}，种子进背包")


def b4_early_sleep() -> None:
    print("\n" + "=" * 78)
    print("B4  钱够但买不到（item_not_sold）+ 干作物够不着 ⇒ 不许『0 动作还推进游戏日』")
    far = (60, 12)
    unreach = [far, (far[0] - 1, far[1]), (far[0] + 1, far[1]), (far[0], far[1] - 1), (far[0], far[1] + 1)]
    w = MyopicWorld(weeds=0, seeds=0, money=188, radius=3)
    w.dirt.add(far)
    w.crops[far] = {"ripe": False, "watered": False, "dead": False}
    w.player_tile = [64, 14]
    w.farm = {"loaded": True, "complete": True, "crops": 1, "dryCrops": 1, "deadCrops": 0,
              "emptyDirt": 0, "hoeDirt": 1, "dryTiles": [list(far)], "dryTilesTruncated": False}
    w.buy_offers = []
    w.buy_fail_status = "item_not_sold"
    client = UnreachableClient(w, unreachable=unreach)
    day_before = w.day
    run, _ = run_real(w, client)
    report("B4", run)
    ends = ev(run, "day_end")
    check(bool(ends), "账本里有 day_end")
    if ends:
        d = ends[0]
        ok_steps = int(d.get("ok_steps") or 0)
        advanced = bool(d.get("day_after"))
        print(f"  · day={day_before}→{w.day} advanced={advanced} ok_steps={ok_steps} "
              f"ended_by={d.get('ended_by')!r} verified={d.get('verified')} "
              f"slept_without_work={len(ev(run, 'slept_without_work'))}")
        check(not (advanced and ok_steps == 0 and d.get("verified") is True),
              "0 动作**且有活**的日子绝不算达标（advanced / ok_steps==0 / verified=True 三者不可同时成立）")
        buys = ev(run, "buy")
        check(len(buys) <= 3 and all(b.get("ok") is False for b in buys),
              f"钱够但买不到 ⇒ 当天 buy 尝试 {len(buys)} 次、全失败（{[b.get('code') for b in buys]}）")
        check(d.get("ended_by") in ("sleep", "stuck", "sleep_failed", "gave_up_dry",
                                    "slept_without_work")
              and str(d.get("ended_reason") or "") != "",
              f"收尾诚实：ended_by={d.get('ended_by')!r} reason={str(d.get('ended_reason'))[:70]!r}")
    # 卡面 ④ 的直接证据：调 `_do_sleep`（0 农场动作 + 有活）⇒ 必须拒绝睡
    w2 = TL.FakeWorld(weeds=0, seeds=0, money=0)
    w2.dirt.add((60, 10))
    w2.crops[(60, 10)] = {"ripe": False, "watered": False, "dead": False}
    client2 = CapClient(w2)
    run2 = TL.make_run(w2, target_days=1, max_days=1,
                       client_factory=lambda: client2,
                       worker_factory=lambda c: FarmWorker(c, log=lambda *_: None,
                                                            pause=lambda _s: None))
    run2.worker = FarmWorker(client2, log=lambda *_: None, pause=lambda _s: None)
    run2.client = client2
    rep = TL.DayReport(day_key=("spring", 1, 6), started_at=0.0)
    run2.farm_actions_today = 0
    before = w2.day
    by, why = run2._do_sleep(w2.obs(), rep, "no_work:守卫说没活了")
    check(by == "slept_without_work" and rep.slept_without_work and w2.day == before,
          f"`_do_sleep`（0 动作 + 有活）⇒ 拒绝睡（by={by!r} "
          f"slept_without_work={rep.slept_without_work} day {before}→{w2.day}）")
    check(bool(ev(run2, "slept_without_work")),
          f"journal `slept_without_work` 落盘（{len(ev(run2, 'slept_without_work'))} 条）")


# ---------------------------------------------------------------- C 段
def c5_lying_no_space_is_not_a_purchase() -> None:
    print("\n" + "=" * 78)
    print("C5  回执自称成功但钱/背包没变 ⇒ 会不会被当买到了")
    w = LiveFarmWorld(weeds=0, seeds=0, money=188)
    w.buy_offers = [{"id": "(O)483", "name": "Wheat Seeds", "price": 10}]

    class LyingBuy(CapClient):
        def buy(self, item, count=10, *, shop="SeedShop", timeout_ms=25000):
            self.w.buy_calls.append({"item": str(item), "count": int(count)})
            return StepResult("buy", ok=True, code="ok", status="ok",
                              reason="假世界：回执说买到了，世界没变",
                              available=[dict(o) for o in self.w.buy_offers])

    w.inventory_capacity = len(w.inventory)
    client = LyingBuy(w)
    w.dirt.add((60, 10))
    w.crops[(60, 10)] = {"ripe": False, "watered": False, "dead": False}
    day_before = w.day
    run, _ = run_real(w, client)
    report("C5", run)
    buys = ev(run, "buy")
    check(all(b.get("ok") is False for b in buys),
          f"自称成功的 buy 全被判失败（{[b.get('ok') for b in buys]}）")
    check(len(buys) <= 3, f"谎报不产生无限重试（buy 尝试 {len(buys)} ≤ 暂存 3 次上限）")
    check(w.money == 188, f"钱没变（{w.money}）")


def c6_never_sells_seeds_tools_weapons() -> None:
    print("\n" + "=" * 78)
    print("C6  腾格卖出会不会碰种子/工具/武器")
    print(f"  · 白名单原文 SURPLUS_MATERIAL_IDS={sorted(SURPLUS_MATERIAL_IDS)}")
    # ① 只有工具 + 作物（表外）+ 空种子叠 ⇒ 一格都不卖，skipReason 必须点名白名单
    player = {"inventory": [
        mat(0, "Axe", "Axe", 1, tool=True),
        mat(1, "47", "Scythe", 1, tool=True),
        {"slot": 3, "id": "24", "qualifiedId": "(O)24", "name": "Radish", "stack": 300, "isTool": False},
        {"slot": 4, "id": "472", "qualifiedId": "(O)472", "name": "Parsnip Seeds",
         "stack": 0, "isTool": False},
    ], "inventoryCount": 4, "money": 200}
    plan = surplus_sell_plan({"player": player}, seed_price=10, need_slot=True, free_slots=0,
                             free_slots_status="ok", slots_needed=1)
    check(plan["slots"] == [], f"只有工具/作物/空叠 ⇒ 一格都不卖（slots={plan['slots']}）")
    check(bool(plan["skipReason"]), f"skip 原因原文：{plan['skipReason'][:90]!r}")
    # ② 材料 + 工具混装（各 id 只有一叠）⇒ 只挑材料、绝不挑工具；单叠全是 belowKeep 兜底
    player2 = {"inventory": [
        mat(0, "Axe", "Axe", 1, tool=True),
        mat(5, "388", "Wood", 300, tool=False),
        mat(6, "390", "Stone", 200, tool=False),
    ], "inventoryCount": 3, "money": 200}
    plan2 = surplus_sell_plan({"player": player2}, seed_price=10, need_slot=True,
                              free_slots=0, free_slots_status="ok", slots_needed=1)
    check(plan2["slots"] == [6] and plan2["belowKeep"] is True,
          f"各 id 只有一叠 ⇒ 走 belowKeep 兜底、挑**最小**的一叠（slots={plan2['slots']} "
          f"belowKeep={plan2['belowKeep']}）")
    check(all("(T)" not in q for q in plan2["whitelist"]),
          f"白名单里没有工具（{plan2['whitelist']}）")


def c7_keep_factor() -> None:
    print("\n" + "=" * 78)
    print("C7  腾格卖出会不会破 K=10")
    # 同 id 两叠：卖任一叠后剩余仍 ≥ keep ⇒ 两叠都算"真盈余" ⇒ 应挑最小的那叠（slot 4）
    two = {"inventory": [
        mat(4, "390", "Stone", 40, tool=False),
        mat(6, "390", "Stone", 200, tool=False),
    ], "inventoryCount": 2, "money": 200}
    p2 = surplus_sell_plan({"player": two}, seed_price=10, need_slot=True, free_slots=0,
                           free_slots_status="ok", slots_needed=1)
    check(p2["belowKeep"] is False
          and all(int(i["left"]) >= 10 for i in p2["items"] if int(i["sell"]) > 0),
          f"同 id 两叠 ⇒ K=10 **不破**（items={p2['items']}）")
    print(f"  · NIT-1 复核：docstring 说腾格路径『真盈余里挑最小的一叠』(=slot4)，实测 slots={p2['slots']}"
          f"（挑了**最大**的一叠）；belowKeep={p2['belowKeep']} why={p2['why']!r}")
    # NIT-2：只缺 1 个格子，却按"每个 id 一叠"卖出多叠
    many = {"inventory": [
        mat(1, "388", "Wood", 300, tool=False), mat(2, "388", "Wood", 300, tool=False),
        mat(4, "390", "Stone", 200, tool=False), mat(5, "390", "Stone", 200, tool=False),
        mat(7, "771", "Fiber", 100, tool=False), mat(8, "771", "Fiber", 100, tool=False),
    ], "inventoryCount": 6, "money": 30}
    p3 = surplus_sell_plan({"player": many}, seed_price=10, need_slot=True, free_slots=0,
                           free_slots_status="ok", slots_needed=1)
    check(len(p3["slots"]) > 1,
          f"NIT-2 复核：只缺 1 格却计划卖 {len(p3['slots'])} 叠（slots={p3['slots']}）"
          f" ⇒ 与 docstring『need_slot 只卖一叠』不符（K 仍未破："
          f"{[(i['id'], i['sell'], i['left']) for i in p3['items'] if int(i['sell']) > 0]}）")
    one = {"inventory": [mat(4, "390", "Stone", 200, tool=False)],
           "inventoryCount": 1, "money": 200}
    p1 = surplus_sell_plan({"player": one}, seed_price=10, need_slot=True, free_slots=0,
                           free_slots_status="ok", slots_needed=1)
    check(p1["slots"] == [4] and p1["belowKeep"] is True,
          f"唯一一大叠（整叠不可分）⇒ 卖它但**如实标** belowKeep（slots={p1['slots']}）")
    print(f"  · 记账：items={p1['items']}")
    # 真代码验证 journal 里也带 below_keep
    w = LiveFarmWorld(weeds=0, seeds=0, money=188)
    w.buy_offers = [{"id": "(O)483", "name": "Wheat Seeds", "price": 10}]
    w.buy_price = 10
    w.inventory.append(mat(6, "390", "Stone", 200))
    w.inventory_capacity = len(w.inventory)
    run, _ = run_real(w)
    sells = ev(run, "sell")
    check(bool(sells) and all(s.get("below_keep") is True for s in sells),
          f"journal 如实记 below_keep（{[s.get('below_keep') for s in sells]}）")


def c8_bounded_across_days() -> None:
    print("\n" + "=" * 78)
    print("C8  连续两天 no_space（且腾格卖出失败）⇒ 每天重试几次")
    w = LiveFarmWorld(weeds=0, seeds=0, money=188)
    w.buy_offers = [{"id": "(O)483", "name": "Wheat Seeds", "price": 10}]
    w.buy_price = 10
    w.inventory.append(mat(6, "390", "Stone", 200))
    w.inventory_capacity = len(w.inventory)
    client = CapClient(w, sell_mode="not_whitelisted")
    run, _ = run_real(w, client, days=2)
    report("C8", run)
    ends = ev(run, "day_end")
    per_day = [e.get("attempt") for e in ev(run, "buy")]
    print(f"  · 每天 buy 的 attempt 序列 = {per_day}")
    check(all(int(a) <= 3 for a in per_day if a), f"每天 buy 尝试 ≤ 3（{per_day}）")
    check(len(per_day) <= 2 * 1 + 2, f"两天总共只发了 {len(per_day)} 次 buy（run8 是 13+11 次）")
    check(len(ev(run, "surplus_sell_skip")) >= 1 or len(ev(run, "sell_failed")) >= 1,
          "腾格卖不出去时如实记 skip/failed（不静默）")
    check(bool(ends), "连跑 2 天有账本")


def c9_sleep_modal_fail_closed() -> None:
    print("\n" + "=" * 78)
    print("C9  睡前清模态失败 ⇒ 不许假装睡成功")

    class RaiseDismiss(CapClient):
        def dismiss_modal(self, *, timeout_ms=5000):
            raise BridgeError("假世界：关框失败", status="ui_modal")

    class UiModalSleepWorker(TL.FakeWorker):
        def __init__(self, world):
            super().__init__(world)
            self.sleep_ok = 0

        def sleep(self, *, home="FarmHouse", timeout_ms=180000):
            if (self.w.current_ui() or {}).get("activeMenu"):
                return StepResult("sleep", code="ui_modal", status="ui_modal",
                                  reason="[ui_modal] 有菜单挡着，睡不成")
            self.sleep_ok += 1
            return self.w.sleep()

    for label, dismiss_raises in (("dismiss 抛异常", True), ("dismiss 回 ok=False", False)):
        w = LiveFarmWorld(weeds=0, seeds=0, money=0)
        w.ui_script = [{"activeMenu": "ShopMenu", "isModal": True}]
        client = RaiseDismiss(w) if dismiss_raises else CapClient(w)
        if not dismiss_raises:
            w.dismiss = lambda: {"ok": False, "status": "ui_modal"}   # 关不掉
        run = TL.make_run(w, target_days=1, max_days=1,
                          client_factory=lambda: client,
                          worker_factory=lambda c: UiModalSleepWorker(w))
        run.worker = UiModalSleepWorker(w)
        run.client = client
        rep = TL.DayReport(day_key=("spring", 1, 6), started_at=0.0)
        day_before = w.day
        by, why = run._do_sleep(w.obs(), rep, "no_work:确实找不到可做的活")
        print(f"  · {label}: _do_sleep → by={by!r} w.day={w.day}（睡前 {day_before}）"
              f" slept_without_work={rep.slept_without_work}")
        check(by == "sleep_failed", f"{label} ⇒ `_do_sleep` 判 sleep_failed（{by!r}）")
        check(w.day == day_before, f"{label} ⇒ 游戏日没被推进")
        check(bool(ev(run, "sleep")) and ev(run, "sleep")[0].get("ok") is False,
              f"{label} ⇒ sleep journal 记 ok=False")
        if dismiss_raises:
            check(bool(ev(run, "modal_dismiss_failed")),
                  f"{label} ⇒ 记 `modal_dismiss_failed`（{len(ev(run, 'modal_dismiss_failed'))} 条）")
        else:
            check(bool(ev(run, "modal_dismissed")),
                  f"{label} ⇒ 记 `modal_dismissed ok=False`"
                  f"（{[e.get('ok') for e in ev(run, 'modal_dismissed')]}）")


def c10_both_gates() -> None:
    print("\n" + "=" * 78)
    print("C10 两条门闸同时成立（钱 30g < 5×10 但 ≥ 10 + 0 空格 + 有耕地）⇒ 会不会重复卖/空转")
    w = LiveFarmWorld(weeds=0, seeds=0, money=30)
    w.buy_offers = [{"id": "(O)483", "name": "Wheat Seeds", "price": 10}]
    w.buy_price = 10
    w.inventory.append(mat(8, "388", "Wood", 300))
    w.inventory.append(mat(9, "390", "Stone", 200))
    w.inventory_capacity = len(w.inventory)
    w.dirt.add((60, 10))
    w.tillable.discard((60, 10))
    run, client = run_real(w)
    report("C10", run)
    sells = ev(run, "sell")
    qids = [s.get("qid") for s in sells]
    print(f"  · sell 槽位序列 = {[s.get('slot') for s in sells]}，why = {[s.get('why') for s in sells]}，"
          f"qid = {qids}")
    check(all((not q) or any(str(q).endswith(i) for i in SURPLUS_MATERIAL_IDS) for q in qids),
          f"腾格卖出**只碰白名单材料**，从不碰种子/工具/武器（{qids}；空 qid = 槽位已被前一次卖出腾空）")
    check(len(sells) <= 3, f"同一天卖货尝试有界（{len(sells)} 次 ≤ 3）")
    check(len(ev(run, "surplus_sell")) <= 3, f"卖货 summary ≤3（{len(ev(run, 'surplus_sell'))}）")
    check(len(ev(run, "buy")) <= 3, f"buy 尝试 ≤3（{len(ev(run, 'buy'))}）")
    ends = ev(run, "day_end")
    check(bool(ends), "一天跑完并落了 day_end（没有空转死循环）")
    print(f"  · 当天事件计数：{ {e: sum(1 for x in run.entries if x.get('event') == e) for e in ('stuck_flush', 'stuck_flush_skipped', 'slot_sold', 'surplus_sell', 'sell', 'buy', 'sleep')} }")


def main() -> None:
    for fn in (b3_slot_deadlock, b4_early_sleep, c5_lying_no_space_is_not_a_purchase,
               c6_never_sells_seeds_tools_weapons, c7_keep_factor, c8_bounded_across_days,
               c9_sleep_modal_fail_closed, c10_both_gates):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {fn.__name__} 抛异常：{type(exc).__name__}: {exc}")
            print(traceback.format_exc())
            check(False, f"{fn.__name__} 不应抛异常")
    bad = [m for ok, m in CHECKS if not ok]
    print("\n" + "=" * 78)
    print(f"合计 {len(CHECKS)} 条断言：PASS {len(CHECKS) - len(bad)} / FAIL {len(bad)}")
    for m in bad:
        print(f"  FAIL: {m}")


if __name__ == "__main__":
    main()
