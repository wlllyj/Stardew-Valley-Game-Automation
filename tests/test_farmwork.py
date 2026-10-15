# -*- coding: utf-8 -*-
"""执行层（`brain\\agentfarm\\farmwork.py`）的离线单元测试 —— 一格一动的判据与"先判后动"。

【为什么单独测这一层】`farmwork` 是**唯一真的花体力的地方**。真机 run1 的教训（用户 m01758/m01804
"工具等级不够要判断一下，不要白白浪费很多体力"）：`clear()` 对着割不掉的草连挥两下、`till()` 对着
Mod 说可锄但有未知地形特征的格子锄了 16 下，世界纹丝不动。所以这里的断言全部围绕"**判据**"：
  * 动手**之前**能用观测判出来的（缺工具 / 有 feature / 有 objId / 有作物）⇒ 一次都不挥；
  * 挥了一次世界没变 ⇒ 记 `skipped` + `proven_inert`（不是 failed），让上层当天封格；
  * 判不准（观测里没有工具信息）⇒ 宁可放行，不能因为脑看不准就整天不动手。

原则与其它测试文件一致：**不连游戏、不联网、不睡觉** —— 假桥 + 假世界，观测与回执都由测试自己造。

运行：`python -m unittest discover -s tests -v`
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import BridgeError  # noqa: E402
from agentfarm.farmwork import (  # noqa: E402
    NEIGHBORS, FarmWorker, KIND_TOOL, MAX_CLEAR_SWINGS, StepResult as SR, StageResult,
    SURPLUS_MATERIAL_IDS, farm_dead_crops, farm_dry_tiles, farm_empty_dirt, is_seed_offer,
    is_unreachable, pick_seed_offer, seed_offers_from, surplus_sell_plan, till_blocked_by,
    tool_missing_reason, tool_presence,
)

DROP = object()          # "这一格的障碍没了"（观测里那条记录消失）


class MiniWorld:
    """只有一格或几格的假世界：`use_tool` 真的改它、`obs()` 真的反映它。"""

    def __init__(self, *, records=None, tillable=(), inventory=None, tools=None,
                 farming_level: int = 0, stamina: float = 270.0, money: int = 500) -> None:
        self.records = [dict(r) for r in (records or [])]
        self.tillable = {tuple(t) for t in tillable}
        self.inventory = [dict(i) for i in (inventory or [])]
        self.tools = tools
        self.farming_level = farming_level
        self.stamina = stamina
        self.money = int(money)
        self.player_tile = [62, 14]
        self.calls: list[tuple[tuple[int, int], str | None]] = []   # 每一次 use_tool 都被记下
        self.stuck: set[tuple[int, int]] = set()                    # 挥了也白挥的格子（真机 run1 的草）
        self.result: dict[tuple[int, int], object] = {}             # 动作后这一格变成什么（默认：记录消失）
        #: 这一格要**第几刀**才变（默认 1）—— 草是多刀特征：普通镰刀一刀只把 numberOfWeeds 减 1。
        self.swings_needed: dict[tuple[int, int], int] = {}
        # ---- task-51：枯死作物（`crop` 在、`dead=true`）----
        #: 这些格**是枯死作物**：`use_tool` 命中后把 `crop`/`dead`/`ripe` 摘掉、`kind` 留 `dirt`
        #: （真机 `destroyCrop(true)`）。活苗绝不进这个集合 ⇒ 用来证明"清死苗动作不碰活苗"。
        self.dead_crops: set[tuple[int, int]] = set()
        #: 回执说"成了"但世界一动不动（真机 run1 镰刀假 ok 的复现）。
        self.lie: set[tuple[int, int]] = set()
        #: 这一格固定回哪个失败状态码（`tool_ineffective` / `no_save` / …）；给 list 则按顺序发。
        self.fail_status: dict[tuple[int, int], str | list[str]] = {}
        self.counts: dict[tuple[int, int], int] = {}                # 每格被挥了几次
        # ---- 睡觉（task-8 / task-33）：床、**触发格**、提问、跨日 ----
        self.location_name = "FarmHouse"      # 默认已在卧室 ⇒ 省掉 ensure_location 那段
        self.bed = (62, 13)                   # 床**原点**（踩它什么都不会发生，真机定案）
        #: 睡觉**触发格**（`TouchAction == "Sleep"`）：踩中才会弹出提问。
        #: 默认给两格候选，对应桥的 `furniture[].bedCells`（task-33 起观测里有这一项）。
        self.bed_cells = [(62, 14), (63, 14)]
        #: 关掉提问框之后日期会不会跟着前进（真机定案：会，~3s；置 False 用来测"仍不动"）。
        self.dismiss_finishes_day = True
        self.dismiss_calls = 0
        self.dismiss_errors: list[str] = []   # 每次 dismiss_modal 的说明（单测直接看）
        self.day = 9
        self.tod = 1300
        self.in_bed = False
        self.question: str | None = None       # None / "sleep" / "other"
        #: 踩**触发格**（`allow_bed=True`）能不能引出游戏自己的提问 —— 真机 run2 就是**没引出来**。
        self.step_opens_question = True
        #: Mod `SleepSkill.Step()` 的离线替身：cross / no_day / no_question / timeout
        self.sleep_mode = "cross"
        self.moves: list[dict] = []            # 每一次 move_to（含 allow_bed）
        self.sleep_calls: list[int | None] = []
        self.interacts = 0
        #: 非空 ⇒ `move_to_location` 照这个 reason 抛 `unreachable`（造"门走不通"的现场）。
        self.move_to_location_fail = ""
        # ---- task-52：走不到的格子（没有落脚点 / 寻路到不了）----
        #: 这些格**走不上去**：`MiniBridge.move_to` 抛 `BridgeError(status="unreachable")`
        #: （真机 run5 那 8 格是 `stand_next_to` 直接判"四邻都站不过去"，脑侧连 Mod 都没问到）。
        self.unwalkable: set[tuple[int, int]] = set()
        # ---- task-43：长距离进建筑（每跳预算与路径长度无关 + 两段式接近）----
        #: `move_to_location` 的**回执脚本**（按顺序 pop，空则照 `move_to_location_fail` 走）：
        #:   `{"fail": {"status": "timeout", "reason": "…warp 源格 (64,14)…剩余 52 步未走完"}}`
        #:   `{"ok": True}`（真的把 `location_name` 换掉）
        self.move_to_location_script: list[dict] = []
        self.move_to_location_calls: list[dict] = []   # 每次调用的 location/tile/timeout_ms
        # ---- NIT-3：桥**中途沉默**（睡觉过程中掉线）----
        #: 非空 ⇒ 让 `observe` 抛 `BridgeError(status=observe_fail_status)`。
        self.observe_fail_status = ""
        #: "mid" = 第 2 次观察起每次都抛（踩床途中桥死）；"after_sleep" = `sleep` 回执后的
        #: 第一次观察抛一次（跨日已发生、之后桥死）。
        self.observe_fail_mode = ""
        self.observe_calls = 0
        self.observe_failed_once = False
        # ---- task-42：出货箱（`sell`）----
        #: 出货箱里的条目（`obs()["shippingBin"]["items"]` 直接反映它）。
        self.shipping_bin: list[dict] = []
        self.sell_calls: list[dict] = []          # 每次 `sell` 请求的参数
        #: "ship" = 真把那一格搬进箱子；"no_effect" = 回执 ok 但世界一动不动；
        #: 其它非空值 ⇒ 抛 `BridgeError(status=...)`（造"没拿到结论"的现场）。
        self.sell_mode = "ship"
        # ---- task-42：收获（`interact` 真的把作物摘下来并放一件进背包）----
        #: 摘下来的作物进背包的条目（None ⇒ 收获成功但**什么都没进背包**，用来测白名单不许凭空生成）。
        self.harvest_item: dict | None = {"slot": 5, "id": "24", "qualifiedId": "(O)24",
                                          "name": "Parsnip", "stack": 1, "isTool": False}
        self.harvests: list[tuple[int, int]] = []
        # ---- task-67：买种子（`buy`）----
        #: 回执里带的货架清单（`availableItems`）。默认照 run6 的夏季真机货架（只有当季种子，
        #: **没有**春季的防风草 `472`）—— 这正是"硬编码 472 必失败"的现场。
        self.buy_offers: list[dict] | None = [
            {"id": "(O)254", "name": "Melon Seeds", "price": 80},
            {"id": "(O)479", "name": "Tomato Seeds", "price": 50},
            {"id": "(O)481", "name": "Blueberry Seeds", "price": 80},
            {"id": "(O)482", "name": "Pepper Seeds", "price": 40},
            {"id": "(O)483", "name": "Wheat Seeds", "price": 10},
        ]
        self.buy_calls: list[dict] = []
        #: 非空 ⇒ `buy` 抛 `BridgeError(status=…)`（回执里**照样**带 `availableItems`）。
        self.buy_fail_status = ""
        #: 非空 ⇒ 该品类买不到（缺省 `item_not_sold`），用来演 run6 的"硬编码 472"。
        self.buy_missing_item = ""
        self.buy_price = 20            # 配置项（默认 472）的单价：按它扣钱、加背包
        # ---- task-55：`farm` 级计数（`emptyDirt` 是"卖盈余材料换种子钱"的门闸之一）----
        #: 默认 None ⇒ `obs()["farm"] == {}` ⇒ farm 证据不可用（既有用例不受影响）。
        self.farm: dict | None = None

    # ---- 观测 ----
    def obs(self) -> dict:
        player: dict = {"name": "测试员", "tile": list(self.player_tile),
                        "stamina": self.stamina, "money": self.money,
                        "farmingLevel": self.farming_level,
                        "inventory": [dict(i) if isinstance(i, dict) else None
                                      for i in self.inventory]}
        if self.tools is not None:
            player["tools"] = dict(self.tools)
        player["isInBed"] = self.in_bed
        return {
            "ok": True, "status": "ok",
            "clock": {"year": 1, "season": "spring", "day": self.day, "timeOfDay": self.tod},
            "player": player,
            "location": {"name": self.location_name, "isOutdoorFarm": False,
                         "tiles": [dict(r) for r in self.records],
                         "tillable": [list(t) for t in sorted(self.tillable)],
                         "refillTiles": [],
                         "furniture": [{"tile": list(self.bed), "isBed": True,
                                        "bedCells": [list(c) for c in self.bed_cells],
                                        "name": "Bed", "furnitureType": "bed"}]},
            # `ui` 块（v3 起才有）：睡觉判据看的就是它（`dialogueIsQuestion`）。
            "ui": {"activeMenu": ("DialogueBox" if self.question else None),
                   "activeMenuText": ("Go to sleep for the night?"
                                      if self.question == "sleep" else
                                      ("要卖掉手里的东西吗？" if self.question == "other" else "")),
                   "dialogueResponses": (["Yes", "No"] if self.question else []),
                   "dialogueIsQuestion": self.question is not None,
                   "isModal": self.question is not None},
            # 出货箱（task-42）：快照顶层的 `shippingBin`（Mod 的 `ReadShippingBin()`）。
            "shippingBin": {"present": True, "count": len(self.shipping_bin),
                            "items": [dict(i) for i in self.shipping_bin],
                            "lastItemShipped": "", "separateWallets": False},
            # farm 级计数（task-55）：默认空 ⇒ farm 证据不可用（`farm_empty_dirt` 报 unavailable）。
            "farm": dict(self.farm) if self.farm else {},
        }

    def harvest(self, tile: tuple[int, int]) -> None:
        """Mod `interact` 的离线替身（只对成熟作物）：摘掉作物，按 `harvest_item` 决定进不进背包。"""
        self.harvests.append((int(tile[0]), int(tile[1])))
        found = False
        for r in self.records:
            if tuple(r["tile"]) == (int(tile[0]), int(tile[1])) and r.get("crop"):
                found = True
                r.pop("crop", None)
                r.pop("ripe", None)
        if found and self.harvest_item:
            self.inventory.append(dict(self.harvest_item))

    def ship(self, slot: int, whitelist) -> dict:
        """Mod `ShipSkill` 的离线替身：白名单外拒绝；白名单内把**那一格整件**搬进箱子。

        真机纪律（`docs/_il-sell-path.md`）：钱当天**不变**（下一次 `NewDay` 才结算），
        所以这里也绝不动 `money` —— 正好用来证明脑侧判据不是"钱变了"。
        """
        self.sell_calls.append({"slot": int(slot),
                                "whitelist": [str(x) for x in (whitelist or [])]})
        if self.sell_mode and self.sell_mode not in ("ship", "no_effect"):
            raise BridgeError(f"sell 失败（{self.sell_mode}）：没有拿到结论",
                              status=str(self.sell_mode))
        if not (0 <= int(slot) < len(self.inventory)):
            raise BridgeError("槽位越界", status="bad_args")
        item = self.inventory[int(slot)]
        if item is None:
            raise BridgeError("槽位是空的", status="empty_slot")
        allow = [str(x) for x in (whitelist or [])]
        qid = str(item.get("qualifiedId") or item.get("id") or "")
        if not allow or qid not in allow:
            raise BridgeError(f"{qid} 不在白名单里", status="not_whitelisted")
        if str(self.sell_mode) == "no_effect":
            return {"ok": True, "status": "ok", "reason": "回执说卖了，其实什么都没动"}
        # 真出货：整格搬走（真机 `shipItem` 没有"出一部分"的能力）
        self.inventory[int(slot)] = None
        self.shipping_bin.append(dict(item))
        return {"ok": True, "status": "ok", "reason": "已放进出货箱（钱等 NewDay）"}

    def do_buy(self, item, count) -> dict:
        """Mod `BuySkill` 的离线替身（task-67）。

        行为照真机：`availableItems` **成功与失败都带**；要买的品类不在货架上 ⇒ 抛
        `item_not_sold`（回执里照样带清单 —— run6 就是靠这一条才知道夏季货架上有什么）。
        """
        self.buy_calls.append({"item": str(item), "count": int(count)})
        # `None` = 旧桥（0.7.24 及之前）：没有 `availableItems` 字段，买得成也没清单可带。
        offers = None if self.buy_offers is None else [dict(o) for o in self.buy_offers]

        def _digits(v) -> str:
            s = "".join(ch for ch in str(v or "") if ch.isdigit())
            return s or str(v or "")

        # 货架上有没有这一件（按 id 数字比：`(O)483` 与 `483` 是同一件）。
        on_shelf = bool(offers is not None and any(
            _digits(o.get("id")) == _digits(item) for o in offers))
        missing = str(self.buy_missing_item or ("" if on_shelf or offers is None else str(item)))
        if self.buy_fail_status or missing:
            status = str(self.buy_fail_status or "item_not_sold")
            raise BridgeError(f"{status}：商店里没有「{item}」", status=status,
                              payload=({"availableItems": offers} if offers is not None else {}))
        price = int(self.buy_price)
        can = min(int(count), self.money // price) if price > 0 else int(count)
        if can < 1:
            raise BridgeError(f"钱不够（{self.money}g < {price}g）", status="purchase_no_effect",
                              payload=({"availableItems": offers} if offers is not None else {}))
        self.money -= price * can
        slot = None
        for it in self.inventory:
            if it and "Seed" in str(it.get("name") or ""):
                slot = it
                break
        if slot is None:
            self.inventory.append({"slot": 5, "id": str(item).replace("(O)", ""),
                                   "qualifiedId": str(item) if str(item).startswith("(")
                                   else f"(O){item}",
                                   "name": "Parsnip Seeds", "stack": can, "isTool": False})
        else:
            slot["stack"] = int(slot.get("stack") or 0) + can
        reply = {"ok": True, "status": "ok",
                 "reason": f"买到了 {can} 个「{item}」，共花 {price * can}g"}
        if offers is not None:
            reply["availableItems"] = offers          # 旧桥没有这个字段
        return reply

    def do_sleep(self) -> None:
        """Mod `SleepSkill` 的离线替身：**只有"人已在床上 / 提问已弹出"才可能跨日**。

        真机定案（`docs/_il-sleep-path.md`）：`answerDialogueAction("Sleep_Yes")` 是字面量分派，
        别的键**静默 no-op** ⇒ 没引出提问时，Mod 要么秒级报 `sleep_no_question`，要么白等到超时。
        这里把三种失败都造出来：`no_question`（抛带现场的回执）、`timeout`（抛超时回执）、
        `no_day`（回执 ok 但世界一动不动 —— 只认观测差分的判据就是这么来的）。
        """
        if self.sleep_mode == "no_question":
            raise BridgeError(
                "睡觉提问没弹出来，拒绝盲发应答（盲发在 IL 上是静默 no-op）："
                f"当前地点 {self.location_name} 的 lastQuestionKey=(空)；"
                f"诊断：isInBed={str(self.in_bed).lower()}, Game1.newDay=False, pauseTime=False, "
                "activeClickableMenu=(无), dialogueUp=False, canMove=True, gameMode=3, "
                "timeOfDay=1300, newDaySync.readyForSave?=?, newDaySync.hasSaved?=?"
                "。先让玩家**踩到床格**触发游戏自己的 checkAction(bed)",
                status="sleep_no_question")
        if self.sleep_mode == "timeout":
            raise BridgeError(
                "已发起睡觉但 15000ms 内日期没有前进（发起时第 9 天，现在第 9 天）；"
                "当前诊断：isInBed=false, Game1.newDay=False, pauseTime=True, "
                "activeClickableMenu=(无), dialogueUp=False, canMove=False, gameMode=3, "
                "timeOfDay=1300, newDaySync.readyForSave?=False, newDaySync.hasSaved?=False",
                status="timeout")
        if self.sleep_mode == "no_day":
            return                      # 回执 ok，但日期不动 ⇒ 脑必须记 failed
        if self.sleep_mode == "bridge_down":
            # 桥在"发 sleep"这一步就没了（NIT-3）：异常要变成有界返回，不许穿出 sleep()。
            raise BridgeError("sleep 请求发不出去：桥连接中断", status="connection_broken")
        if self.in_bed or self.question == "sleep":
            self.day += 1
            self.tod = 600
            self.in_bed = False
            self.question = None

    # ---- 回执（只是声明，判据看观测差分）----
    def take_fail_status(self, tile) -> str:
        """取出这一格**这次**该回的失败码：str ⇒ 每次都回；list ⇒ 按顺序发（空串 = 这次真动手）。

        task-22 用 list 造"先真白挥一次、之后的请求都没结论"的混合场景。
        """
        v = self.fail_status.get(tuple(tile))
        if not v:
            return ""
        if isinstance(v, str):
            return v
        status = v.pop(0)
        if not v:
            self.fail_status.pop(tuple(tile), None)
        return status

    def use_tool(self, tile, tool=None) -> dict:
        """返回 Mod `use_tool` 那样的回执（`ok/status/reason`）；失败由 `MiniBridge` 抛 `BridgeError`。

        与真 Mod 同口径：`ok=false` + 状态码（`tool_ineffective`/`no_save`/…）。
        世界变不变只看 `swings_needed` —— **回执说成了不算成**（`lie` 就是真机 run1 的假 ok）。
        """
        t = tuple(tile)
        self.calls.append((t, tool))
        n = self.counts[t] = self.counts.get(t, 0) + 1
        want = self.take_fail_status(t) or ("tool_ineffective" if t in self.stuck else "")
        if want:
            return {"ok": False, "status": want,
                    "reason": f"use_tool 试过的工具都无效：目标格 {t} 上仍有东西（起手=否）"}
        if t in self.dead_crops:
            # 【task-51】枯死作物：真机是 `destroyCrop(true)`（镰刀或锄头，IL 见
            # `scratch\il-dead-hoedirt.txt`）⇒ 这一格的 **crop 消失、耕地留下**。
            self.dead_crops.discard(t)
            for r in self.records:
                if tuple(r["tile"]) == t:
                    r.pop("crop", None)
                    r.pop("dead", None)
                    r.pop("ripe", None)
                    r["kind"] = "dirt"
            return {"ok": True, "status": "ok",
                    "reason": f"已用「{tool}」清掉这一格的枯死作物"}
        if t in self.lie:
            return {"ok": True, "status": "ok",
                    "reason": f"已用「{tool}」对 {t} 动手 1 次，现在**已经空了**（假回执）"}
        if n < int(self.swings_needed.get(t, 1)):
            return {"ok": True, "status": "ok",
                    "reason": f"已用「{tool}」对 {t} 动手 1 次"}
        new = self.result.get(t, DROP)
        if new is DROP:
            self.records = [r for r in self.records if tuple(r["tile"]) != t]
            # 【task-68】清掉挡路物以后这一格就**能站了**（真机是障碍消失 ⇒ A* 有路）。
            self.unwalkable.discard(t)
        else:
            for r in self.records:
                if tuple(r["tile"]) == t:
                    r["kind"] = new
            self.unwalkable.discard(t)
        return {"ok": True, "status": "ok",
                "reason": f"已用「{tool}」对 {t} 动手 {n} 次"}


class MiniBridge:
    """`FarmWorker` 要的最小桥面：observe / move_to / use_tool。"""

    def __init__(self, world: MiniWorld) -> None:
        self.w = world

    def observe(self, detail: str = "summary", *, timeout=None):
        w = self.w
        w.observe_calls += 1
        if w.observe_fail_status:
            if w.observe_fail_mode == "mid" and w.observe_calls >= 2:
                raise BridgeError("observe 失败：桥连接中断（模拟踩床途中掉线）",
                                  status=w.observe_fail_status)
            if (w.observe_fail_mode == "after_sleep" and w.sleep_calls
                    and not w.observe_failed_once):
                w.observe_failed_once = True
                raise BridgeError("observe 失败：桥连接中断（模拟跨日之后掉线）",
                                  status=w.observe_fail_status)
        return w.obs()

    def move_to(self, x, y, *, timeout_ms=None, based_on_seq=None, allow_bed=False):
        self.w.moves.append({"tile": [int(x), int(y)], "allow_bed": bool(allow_bed)})
        tile = (int(x), int(y))
        if tile in self.w.unwalkable:
            # 【task-52】走不到的格子：真机是 Mod 回 `unreachable`（A* 没算出路径）
            # ⇒ 脑侧 `stand_next_to` 四邻全抛 ⇒ 返回 False ⇒ `clear()/till()/water()/…`
            # 记 `unreachable`（**不是** `failed`）。
            raise BridgeError(f"走向 ({int(x)}, {int(y)}) 时寻路无法到达", status="unreachable")
        # 踩睡觉**触发格** ⇒ 游戏自己的 `performTouchAction("Sleep")` 弹出提问；真机回执是
        # `ui_modal`（`MoveToLocationSkill.Begin()` 的模态闸门先命中）—— 这是**命中信号**不是失败
        # （task-33 施工单第 2 条 / task-37 真机复核）。
        if allow_bed and self.w.step_opens_question and tile in self.w.bed_cells:
            self.w.player_tile = [int(x), int(y)]
            self.w.in_bed = True
            self.w.question = "sleep"
            raise BridgeError(
                "移动过程中被菜单/对话/过场打断，已停止移动"
                f"（当前 DialogueBox，目标 {x},{y}）", status="ui_modal")
        # 床**原点**格：真机踩它什么都不会发生（静默 no-op），不许当触发格。
        self.w.player_tile = [int(x), int(y)]
        return {"ok": True, "status": "ok"}

    def dismiss_modal(self, *, timeout_ms=None):
        """`dismiss_modal`：关掉挂着的提问框。真机定案：关框 ~3s 内当天落地。"""
        self.w.dismiss_calls += 1
        note = "已关掉提问框"
        if self.w.question is not None:
            self.w.question = None
            self.w.in_bed = False
            if self.w.dismiss_finishes_day:
                self.w.day += 1
                self.w.tod = 600
                note += f"；关框后当天落地（第 {self.w.day} 天）"
            else:
                note += "；关框后日期仍没动"
        else:
            note += "（当时没有提问框）"
        self.w.dismiss_errors.append(note)
        return {"ok": True, "status": "ok", "reason": note}

    def move_to_location(self, location, *, tile=None, timeout_ms=None, based_on_seq=None,
                         allow_bed=False):
        self.w.move_to_location_calls.append(
            {"location": str(location), "tile": tile, "timeout_ms": timeout_ms,
             "allow_bed": bool(allow_bed)})
        # task-43：按脚本发回执（造"长路径单跳超时 + warp 源格 + 剩余 N 步"的现场）。
        if self.w.move_to_location_script:
            step = self.w.move_to_location_script.pop(0)
            fail = step.get("fail")
            if fail:
                raise BridgeError(str(fail.get("reason") or "move_to_location 失败"),
                                  status=str(fail.get("status") or "timeout"))
        if self.w.move_to_location_fail:
            raise BridgeError(self.w.move_to_location_fail, status="unreachable")
        self.w.location_name = str(location)
        return {"ok": True, "status": "ok"}

    def interact(self, tile=None, *, timeout_ms=None):
        self.w.interacts += 1
        if tile is not None:
            self.w.harvest(tuple(tile))       # task-42：收获真的把作物摘下来（并可能进背包）
        return {"ok": True, "status": "ok"}

    def sleep(self, *, timeout_ms=None):
        self.w.sleep_calls.append(timeout_ms)
        self.w.do_sleep()                       # 真桥失败是抛 BridgeError（带 status），这里照做
        return {"ok": True, "status": "ok",
                "reason": f"已跨日：第 9 天 → 第 {self.w.day} 天（timeOfDay {self.w.tod}）"}

    def use_tool(self, tile, *, tool=None, timeout_ms=None):
        """真桥对 `ok=false` 是**抛** `BridgeError`（带机器可读 `status`），这里照做。"""
        res = self.w.use_tool(tuple(tile), tool)
        if not res.get("ok", True):
            raise BridgeError(str(res.get("reason") or res.get("status") or "use_tool 失败"),
                              status=str(res.get("status") or "error"))
        return res

    def sell(self, slot, *, whitelist=None, timeout_ms=None):
        """`sell`（task-42）：真桥对拒绝/失败是**抛** `BridgeError`（带 `status`），这里照做。"""
        return self.w.ship(int(slot), whitelist)

    def buy(self, item, count=1, *, shop="SeedShop", timeout_ms=None):
        """`buy`（task-67）：真桥失败时抛 `BridgeError`，**回执原文（含货架清单）在 `payload`**。"""
        return self.w.do_buy(item, count)


TOOLS_WITH_SCYTHE = {"axe": True, "pickaxe": True, "hoe": True, "wateringCan": True,
                     "fishingRod": False, "weapon": True}
#: 真机 `logs\\observe-farm-sample.json` 的背包（slot 4 = `(W)47` Scythe）—— 镰刀**在背包里**。
INV_WITH_SCYTHE = [
    {"slot": 0, "id": "Axe", "qualifiedId": "(T)Axe", "name": "Axe", "stack": 1, "isTool": True},
    {"slot": 1, "id": "Hoe", "qualifiedId": "(T)Hoe", "name": "Hoe", "stack": 1, "isTool": True},
    {"slot": 2, "id": "WateringCan", "qualifiedId": "(T)WateringCan", "name": "Watering Can",
     "stack": 1, "isTool": True},
    {"slot": 3, "id": "Pickaxe", "qualifiedId": "(T)Pickaxe", "name": "Pickaxe",
     "stack": 1, "isTool": True},
    {"slot": 4, "id": "47", "qualifiedId": "(W)47", "name": "Scythe", "stack": 1, "isTool": True},
    {"slot": 5, "id": "472", "qualifiedId": "(O)472", "name": "Parsnip Seeds",
     "stack": 10, "isTool": False},
]


def make_worker(world: MiniWorld) -> FarmWorker:
    # `pause` 注入 no-op：`_await_question`/`_await_day_change` 的等待轮询绝不能真睡（否则每条
    # 睡觉用例白等好几秒）。
    return FarmWorker(MiniBridge(world), log=lambda _s: None, pause=lambda _s: None)


def grass_rec(tile=(60, 10)) -> dict:
    return {"tile": list(tile), "kind": "grass", "feature": "Grass", "tool": "scythe",
            "standable": True, "actionable": True}


def weed_rec(tile=(60, 10)) -> dict:
    return {"tile": list(tile), "kind": "weed", "standable": True, "actionable": True}


def dead_crop_rec(tile=(60, 10)) -> dict:
    """枯死作物格（task-51）：耕地 + `crop` 存在 + `dead=true`（真机审计的形态）。"""
    return {"tile": list(tile), "kind": "dirt", "feature": "HoeDirt", "crop": "24",
            "dead": True, "ripe": False, "watered": True, "standable": False}


def live_crop_rec(tile=(60, 10)) -> dict:
    """活苗格（task-51 的负例）：`crop` 存在但 `dead=false` ⇒ 清死苗动作**绝不许碰**。"""
    return {"tile": list(tile), "kind": "dirt", "feature": "HoeDirt", "crop": "264",
            "dead": False, "ripe": False, "watered": True, "standable": False}


class TestToolPresence(unittest.TestCase):
    """工具判据：观测里只有"有没有"，没有等级（升级等级 Mod 没上报）。"""

    def test_reads_scythe_from_real_snapshot_shape(self):
        """真机快照：`tools{}` 里没有 scythe 位，但 `weapon=true` **且**背包里有 `(W)47`。"""
        player = {"tools": dict(TOOLS_WITH_SCYTHE), "inventory": [dict(i) for i in INV_WITH_SCYTHE]}
        pres = tool_presence(player)
        for want in ("axe", "pickaxe", "hoe", "can", "scythe"):
            self.assertTrue(pres.get(want), f"{want} 应判为「有」：{pres}")
        self.assertEqual(tool_missing_reason(player, "scythe"), "")
        self.assertEqual(tool_missing_reason(player, "hoe"), "")

    def test_missing_tool_reported(self):
        player = {"tools": {"axe": True, "pickaxe": False, "hoe": False,
                            "wateringCan": True, "weapon": False}, "inventory": []}
        self.assertIn("hoe", tool_missing_reason(player, "hoe"))
        self.assertEqual(tool_missing_reason(player, "axe"), "")

    def test_unknown_tool_state_passes(self):
        """判不准（观测里压根没有工具信息）⇒ 必须放行：宁可多挥一次，也不能整天不动手。"""
        self.assertEqual(tool_presence({}), {})
        self.assertEqual(tool_missing_reason({}, "hoe"), "")
        self.assertEqual(tool_missing_reason({}, "scythe"), "")
        self.assertEqual(tool_missing_reason({}, "auto"), "")

    def test_pickaxe_is_not_confused_with_axe(self):
        """子串坑："pickaxe" 里含 "axe"，按子串匹配会把镐误认成斧。"""
        player = {"inventory": [{"id": "Pickaxe", "qualifiedId": "(T)Pickaxe",
                                 "name": "Pickaxe", "stack": 1, "isTool": True}]}
        pres = tool_presence(player)
        self.assertTrue(pres.get("pickaxe"))
        self.assertFalse(pres.get("axe"))

    def test_auto_needs_any_tool(self):
        none = {"tools": {"axe": False, "pickaxe": False, "hoe": False,
                          "wateringCan": False, "weapon": False}, "inventory": []}
        self.assertNotEqual(tool_missing_reason(none, "auto"), "")
        self.assertEqual(tool_missing_reason({"tools": dict(TOOLS_WITH_SCYTHE)}, "auto"), "")


class TestTillBlockedBy(unittest.TestCase):
    def test_judgements_in_order(self):
        self.assertEqual(till_blocked_by(None), "")
        self.assertEqual(till_blocked_by({"kind": "dirt", "feature": "HoeDirt"}), "")
        self.assertEqual(till_blocked_by({"kind": "dirt", "crop": "24"}), "")
        # 作物判据要看**非耕地**：kind=dirt 已经是耕地，第 1 条就返回"不挡着"（`till()` 自己
        # 在更前面判 crop，见 `test_crop_tile_is_skipped_without_swinging`）。
        self.assertEqual(till_blocked_by({"kind": "unknown", "crop": "24"}), "有作物")
        self.assertIn("未知", till_blocked_by({"kind": "unknown", "feature": "Stone"}))
        self.assertEqual(till_blocked_by({"kind": "weed", "objId": "42"}), "weed")
        self.assertEqual(till_blocked_by({"kind": "unknown", "objId": "-1"}), "")

    def test_hoe_clause_only_when_player_given(self):
        player = {"tools": {"hoe": False}, "inventory": []}
        self.assertEqual(till_blocked_by({"kind": "unknown", "objId": "-1"}), "")
        self.assertIn("hoe", till_blocked_by({"kind": "unknown", "objId": "-1"}, player))


class TestClearKeepsJudgement(unittest.TestCase):
    def test_crop_tile_is_skipped_without_swinging(self):
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "dirt", "crop": "24"}],
                      inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        r = make_worker(w).clear((60, 10))
        self.assertEqual((r.code, r.proven_inert), ("skipped", False))
        self.assertEqual(w.calls, [])
        self.assertIn("作物", r.reason)

    def test_missing_tool_never_swings_and_says_why(self):
        """有 feature/objId 之外，**缺这件工具**也必须前置拦下（`FindToolSlot` 只会回 precondition_failed）。"""
        w = MiniWorld(records=[weed_rec()], tools={"axe": True, "pickaxe": False,
                                                  "hoe": False, "wateringCan": True,
                                                  "weapon": False}, inventory=[])
        r = make_worker(w).clear((60, 10))
        self.assertEqual(w.calls, [], "判据命中时一次都不许挥")
        self.assertEqual((r.code, r.proven_inert, r.failed), ("skipped", True, False))
        self.assertIn(KIND_TOOL["weed"], r.reason)
        self.assertIn("判据", r.reason)          # 判据进 reason（journal 直接抄这一行）

    def test_unknown_tool_state_swings_once_and_succeeds(self):
        """判不准 ≠ 干不了：没有工具信息的观测照样去挥，世界变了就算成。"""
        w = MiniWorld(records=[weed_rec()], inventory=[])
        r = make_worker(w).clear((60, 10))
        self.assertTrue(r.ok)
        self.assertEqual(len(w.calls), 1)
        self.assertEqual(w.calls[0][1], "auto")   # 非草障碍交给 Mod 的 auto 自己挑工具

    def test_grass_success_is_kind_change(self):
        """grass 成：判据 = 观测前后 `kind` **离开 grass**（回执说 ok 不算数）。"""
        w = MiniWorld(records=[grass_rec()], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        r = make_worker(w).clear((60, 10))
        self.assertTrue(r.ok, r.reason)
        self.assertEqual((r.code, r.proven_inert), ("ok", False))
        self.assertEqual(w.calls, [((60, 10), "scythe")])
        self.assertIn("→", r.reason)               # "kind grass → ''"：差分写进 reason

    def test_grass_swung_once_then_skipped_not_failed(self):
        """grass 败：挥了镰刀世界没变 ⇒ 记 `skipped` + `proven_inert`（**不是 failed**），只挥一次。"""
        w = MiniWorld(records=[grass_rec()], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.stuck.add((60, 10))
        r = make_worker(w).clear((60, 10))
        self.assertEqual(w.calls, [((60, 10), "scythe")], "Mod 一次调用内部自己会换工具重试，脑不许补第二刀")
        self.assertEqual((r.code, r.skipped, r.failed), ("skipped", True, False))
        self.assertTrue(r.proven_inert)
        self.assertTrue(r.attempted)
        self.assertIn("判据", r.reason)
        self.assertIn("farmingLevel", r.reason)    # 现场诊断（等级/体力/身上工具）进 reason

    def test_no_cut_grass_flag_skips_grass(self):
        """调用方明确"别割草"（镰刀会连作物一起割）⇒ 不动手，且当天封格。"""
        w = MiniWorld(records=[grass_rec()], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        r = make_worker(w).clear((60, 10), cut_grass=False)
        self.assertEqual(w.calls, [])
        self.assertEqual((r.code, r.proven_inert), ("skipped", True))

    def test_tree_is_skipped_as_wrong_tool_kind(self):
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "tree"}],
                      inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        r = make_worker(w).clear((60, 10))
        self.assertEqual((r.code, w.calls), ("skipped", []))


class TestClearSwingsUntilKindChanges(unittest.TestCase):
    """task-7：草是**多刀**地形特征 ⇒ 脑要带着新观测重试到 `kind` 变化，但**只在证明干不动时**才封格。

    背景（`docs/_analyze-longrun-run1.md`）：`Grass.performToolAction` 一次只把 `numberOfWeeds` 减 1
    （金镰刀 2），减到 0 才移除特征；而 Mod 的 `Done()` 原来漏了 Grass 判据 ⇒ 空挥也会回 ok。
    所以这层的纪律是：**回执不算证据，观测差分才算**；重试有上限（`MAX_CLEAR_SWINGS`），
    只有挥满上限、或 Mod 明确回"这一格挥不动"（`TILE_INERT_STATUSES`）才 `proven_inert` 封格。
    """

    def test_kind_changes_on_third_swing_is_ok_and_not_sealed(self):
        """① 第 3 刀才把草割掉 ⇒ ok（不封格），且每刀之后的 kind 都写进 reason。"""
        w = MiniWorld(records=[grass_rec()], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.swings_needed[(60, 10)] = 3
        r = make_worker(w).clear((60, 10))
        self.assertTrue(r.ok, r.reason)
        self.assertEqual((r.code, r.proven_inert), ("ok", False))
        self.assertEqual(len(w.calls), 3, "要挥到第 3 刀才变：前两刀不许当成失败")
        self.assertTrue(all(c[1] == "scythe" for c in w.calls))
        self.assertIn("第3次请求", r.reason)
        self.assertIn("第1次请求→grass", r.reason)     # 每次请求后的观测都在，事后可复核
        self.assertIn("第2次请求→grass", r.reason)

    def test_never_changes_hits_cap_then_inert(self):
        """② 挥满 `MAX_CLEAR_SWINGS` 刀世界仍不动 ⇒ 记 skipped + proven_inert（上层当天封格）。"""
        w = MiniWorld(records=[grass_rec()], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.swings_needed[(60, 10)] = 99          # 永远不变
        r = make_worker(w).clear((60, 10))
        self.assertEqual(len(w.calls), MAX_CLEAR_SWINGS)
        self.assertEqual((r.code, r.proven_inert, r.failed), ("skipped", True, False))
        self.assertTrue(r.attempted)
        self.assertIn(f"连挥 {MAX_CLEAR_SWINGS} 刀", r.reason)
        self.assertIn(f"第{MAX_CLEAR_SWINGS}次请求→grass", r.reason)
        self.assertIn("kind 离开 grass", r.reason)

    def test_ok_receipt_without_world_change_is_never_ok(self):
        """③ 回执说"已经空了"但观测没变 ⇒ 绝不算 ok（真机 run1 的镰刀假 ok）。"""
        w = MiniWorld(records=[grass_rec()], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.lie.add((60, 10))
        r = make_worker(w).clear((60, 10))
        self.assertFalse(r.ok, r.reason)
        self.assertEqual((r.code, r.proven_inert), ("skipped", True))
        self.assertEqual(len(w.calls), MAX_CLEAR_SWINGS, "假 ok 不能让它提前收工")
        self.assertIn("还是 grass", r.reason)

    def test_tool_ineffective_stops_immediately(self):
        """Mod 明确回「工具全无效」（它自己已换遍工具）⇒ 立刻停手，不补第二刀。"""
        w = MiniWorld(records=[weed_rec()], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.fail_status[(60, 10)] = "tool_ineffective"
        r = make_worker(w).clear((60, 10))
        self.assertEqual(len(w.calls), 1)
        self.assertEqual((r.code, r.proven_inert, r.failed), ("skipped", True, False))
        self.assertIn("Mod 回「工具全无效」", r.reason)

    def test_env_block_is_failed_and_not_sealed(self):
        """环境挡住（没存档/模态/渐黑）不是"这一格干不动" ⇒ failed、`env_block` 打标且**不封格**。"""
        for status in ("no_save", "world_fading"):
            with self.subTest(status=status):
                w = MiniWorld(records=[weed_rec()], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
                w.fail_status[(60, 10)] = status
                r = make_worker(w).clear((60, 10))
                self.assertEqual(len(w.calls), 1)
                self.assertEqual((r.code, r.proven_inert, r.failed), ("failed", False, True))
                self.assertTrue(r.env_block, "环境挡路必须显式打标（task-22）")
                self.assertFalse(r.inconclusive)
                self.assertTrue(r.as_dict().get("env_block"))
                self.assertIn(status, r.reason)

    def test_inconclusive_never_claims_conclusive_and_spends_quota(self):
        """整轮**一次结论都没拿到**（全 timeout）⇒ failed + `inconclusive`（不封格，但占配额）。

        task-22：以前这类 status 既不是 `TILE_INERT_STATUSES` 也不是 `ENV_BLOCK_STATUSES`，
        会掉进"连挥 N 刀还是 X"的 `proven_inert` 出口 ⇒ 上层当天封格，还与 clear() 自己写的
        "环境挡路不算干不动"自相矛盾。现在必须：①`failed`；②`inconclusive`；③**不**`proven_inert`；
        ④文案说"没拿到结论"而不是"连挥 N 刀还是 X"。
        """
        w = MiniWorld(records=[grass_rec()], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.fail_status[(60, 10)] = "timeout"
        r = make_worker(w).clear((60, 10))
        self.assertEqual(len(w.calls), MAX_CLEAR_SWINGS, "没拿到结论 ⇒ 补请求到上限，但不是封格")
        self.assertEqual((r.code, r.failed, r.proven_inert), ("failed", True, False))
        self.assertTrue(r.inconclusive)
        self.assertFalse(r.env_block)
        self.assertTrue(r.as_dict().get("inconclusive"))
        self.assertIn("没有拿到结论", r.reason)
        self.assertIn("timeout", r.reason)
        self.assertNotIn("连挥", r.reason, "没拿到结论时不许写成「连挥 N 刀还是 X」")
        self.assertNotIn("干不动", r.reason.split("⇒")[0], "前半句不许断言它干不动")

    def test_one_real_swing_then_timeouts_is_still_conclusive_cap(self):
        """先真白挥一次、随后请求都超时 ⇒ **已经拿到过一次结论**，仍按"挥满了没变"封格。

        判据只看"有没有真挥到上限而世界没变"：一次真白挥已经证明这一格不吃这套工具，
        后面的超时不该把它降级成"没拿到结论"（否则格子会被无限重试，白烧体力）。
        """
        w = MiniWorld(records=[grass_rec()], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.swings_needed[(60, 10)] = 99          # 永远不变 ⇒ 第一次是"真白挥"
        # 第一次真发出去（空串），之后的请求报 timeout
        w.fail_status[(60, 10)] = ["", "timeout", "timeout", "timeout"]
        r = make_worker(w).clear((60, 10))
        self.assertEqual(len(w.calls), MAX_CLEAR_SWINGS)
        self.assertEqual((r.code, r.proven_inert, r.failed), ("skipped", True, False))
        self.assertFalse(r.inconclusive)
        self.assertFalse(r.env_block)
        self.assertIn("连挥", r.reason)

    def test_status_classes_cover_mod_codes_are_disjoint(self):
        """三类 status 集合：**两两互斥** + 并集覆盖"bridge 层通用码 + `use_tool` 的码"（task-22 ④ / task-28）。

        `world_fading` 是 task-7 新增的"渐黑不可起手"码；`timeout`/`error` 是"一次都没挥出去/
        没拿到结论"；`busy`（task-28）是 `MainThreadDispatcher.RejectBusy()` 的"已有技能在跑"；
        `stale`（task-28）是我们传了过旧 `based_on_seq` 的**自己犯的错**；剩下的是结论类。
        任何一类漏掉都会让格子被错误地封格或错误地吃配额。

        ⚠️ 覆盖范围**不是**"Mod 全部 status"：其它 skill 专属的码（`sleep_no_question`、
        `precondition_failed` 之外的 plant/buy 码……）**有意**落进兜底桶，由各自调用点处理。
        """
        from agentfarm import farmwork as fw
        env = set(fw.ENV_BLOCK_STATUSES)
        inert = set(fw.TILE_INERT_STATUSES)
        incon = set(fw.INCONCLUSIVE_STATUSES)
        self.assertFalse(env & inert, env & inert)
        self.assertFalse(env & incon, env & incon)
        self.assertFalse(inert & incon, inert & incon)
        mod_codes = {
            "timeout", "world_fading", "tool_ineffective", "error",
            "no_save", "ui_modal", "precondition_failed",
            "busy",       # MainThreadDispatcher.cs:159-169（task-28 N4-1）
            "stale",      # BridgeHost.cs:538-553（based_on_seq 过旧）
        }
        self.assertEqual(mod_codes - (env | inert | incon), set(),
                         "bridge 通用码 + use_tool 的码必须被三类之一覆盖")
        self.assertEqual(incon, {"timeout", "error", "stale"})
        self.assertEqual(env, {"no_save", "ui_modal", "world_fading", "busy"})
        self.assertEqual(inert, {"tool_ineffective", "precondition_failed"})
        # 只有 timeout/error/stale 算"没结论"（Lead m01763 + task-28）：回执 ok / 缺 status /
        # 没见过的码都是**真实回应** ⇒ 世界没变就是"这一刀白挥"，走结论（封格）路径。
        self.assertEqual(fw._classify_status("ok"), (False, False))
        self.assertEqual(fw._classify_status(""), (False, False))
        self.assertEqual(fw._classify_status("brand_new_code"), (False, False))
        self.assertEqual(fw._classify_status("timeout"), (False, True))
        self.assertEqual(fw._classify_status("error"), (False, True))
        self.assertEqual(fw._classify_status("stale"), (False, True))
        self.assertEqual(fw._classify_status("no_save"), (True, False))
        # `busy` 必须算环境挡路（不是"这一格干不动"，也不占配额）：run2 真机 180s 超时期间
        # 任何 exec 都会被零成本拒绝，把它当结论就会**白丢一天**。
        self.assertEqual(fw._classify_status("busy"), (True, False))

    def test_busy_is_env_and_never_seals_the_tile(self):
        """`busy`（Mod 队列积压）⇒ 一次都不再补刀、`env_block=True`、**不许** `proven_inert`。"""
        w = MiniWorld(records=[weed_rec((60, 10))], tillable=[(60, 10)],
                      inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.fail_status[(60, 10)] = "busy"
        r = make_worker(w).clear((60, 10))
        self.assertEqual(len(w.calls), 1, "环境挡路就该立刻收手，不是连挥 4 刀")
        self.assertTrue(r.env_block)
        self.assertFalse(r.proven_inert)
        self.assertFalse(r.inconclusive)
        self.assertEqual(r.code, "failed", "failed 但当天不封格（下轮还能试）")
        self.assertIn("busy", r.reason)

    def test_till_busy_is_env_not_sealed(self):
        """`till` 一次 `busy` ⇒ `env_block=True`、`proven_inert=False`（否则当天就被 `_mark_blocked` 封格）。"""
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "unknown", "standable": True}],
                      tillable=[(60, 10)], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.fail_status[(60, 10)] = "busy"
        r = make_worker(w).till((60, 10))
        self.assertTrue(r.env_block)
        self.assertFalse(r.proven_inert)
        self.assertEqual(r.code, "failed")
        self.assertIn("busy", r.reason)

    def test_stale_is_inconclusive_and_spends_quota(self):
        """`stale`（我们传了过旧 `based_on_seq`）⇒ `inconclusive=True`（占配额、不封格）。"""
        w = MiniWorld(records=[weed_rec((60, 10))], tillable=[(60, 10)],
                      inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.fail_status[(60, 10)] = "stale"
        r = make_worker(w).clear((60, 10))
        self.assertTrue(r.inconclusive)
        self.assertFalse(r.env_block)
        self.assertFalse(r.proven_inert)
        self.assertEqual(len(w.calls), MAX_CLEAR_SWINGS, "没结论要补刀到上限")
        self.assertIn("stale", r.reason)


class TestTillKeepsJudgement(unittest.TestCase):
    def test_feature_tile_never_swings(self):
        """真机 (73,25) 一带：Mod 说可锄、观测里有未知地形特征 ⇒ 锄不动，一次都别挥。"""
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "unknown", "feature": "Stone"}],
                      tillable=[(60, 10)], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        r = make_worker(w).till((60, 10))
        self.assertEqual(w.calls, [])
        self.assertEqual((r.code, r.proven_inert), ("skipped", True))
        self.assertIn("判据", r.reason)
        self.assertIn("未知", r.reason)

    def test_objid_tile_never_swings(self):
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "unknown", "objId": "42"}],
                      tillable=[(60, 10)], inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        r = make_worker(w).till((60, 10))
        self.assertEqual(w.calls, [])
        self.assertEqual((r.code, r.proven_inert), ("skipped", True))

    def test_missing_hoe_never_swings(self):
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "unknown"}], tillable=[(60, 10)],
                      tools={"axe": True, "pickaxe": True, "hoe": False,
                             "wateringCan": True, "weapon": True}, inventory=[])
        r = make_worker(w).till((60, 10))
        self.assertEqual(w.calls, [])
        self.assertEqual((r.code, r.proven_inert), ("skipped", True))
        self.assertIn("锄不了", r.reason)
        self.assertIn("hoe", r.reason)

    def test_clean_tile_tills_and_judges_by_kind(self):
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "unknown"}], tillable=[(60, 10)],
                      inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.result[(60, 10)] = "dirt"
        r = make_worker(w).till((60, 10))
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(w.calls, [((60, 10), "hoe")])
        self.assertIn("dirt", r.reason)

    def test_till_without_effect_is_failed_with_context(self):
        """锄了世界没变：till 的判据是**世界真的变成 dirt**，所以这里如实记 failed（带现场诊断）。"""
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "unknown"}], tillable=[(60, 10)],
                      inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.result[(60, 10)] = "unknown"
        r = make_worker(w).till((60, 10))
        self.assertEqual((r.code, r.failed), ("failed", True))
        self.assertIn("dirt", r.reason)
        self.assertIn("身上工具", r.reason)


class TestTask63Refused(unittest.TestCase):
    """【task-63】游戏**拒绝**（`tool_ineffective`/`precondition_failed`）≠"我试了没做成"。

    真机 run5 `spring 26`：4 格 `till` 回 `tool_ineffective` 被判 `failed` ⇒ 当天
    `no_hard_failures=false` ⇒ 连续 3 日的验收必挂。而 `tool_ineffective` 的语义是"游戏挥满
    `MaxSwings=6` 仍拒绝这个工具对这格动手"（`UseToolSkill.cs` / `Contracts.cs:269`）—— 这是
    **世界给的前置事实**，只能记 `skipped`+`proven_inert`（当天封格、次日重试），日级另按
    `refused_bound = max(5, floor(0.2×attempted))` 有界豁免。

    ⚠️ 与它**必须分开**的一条：Mod 回执 `ok` 但世界没变 = 真"挥了没效果" ⇒ 仍 `failed`。
    """

    def test_game_refusal_is_skipped_and_proven_inert(self):
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "unknown"}], tillable=[(60, 10)],
                      inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.fail_status[(60, 10)] = "tool_ineffective"
        r = make_worker(w).till((60, 10))
        self.assertEqual((r.code, r.ok), ("skipped", False))
        self.assertTrue(r.proven_inert)
        self.assertTrue(r.refused)
        self.assertFalse(r.failed, r.reason)
        self.assertEqual(r.status, "tool_ineffective")
        self.assertIn("游戏判定这格锄不动", r.reason)
        self.assertIn("tool_ineffective", r.reason)
        self.assertEqual(w.calls, [((60, 10), "hoe")], "被拒绝也只挥一次，不许每轮重试")

    def test_precondition_failed_is_also_a_refusal(self):
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "unknown"}], tillable=[(60, 10)],
                      inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.fail_status[(60, 10)] = "precondition_failed"
        r = make_worker(w).till((60, 10))
        self.assertTrue(r.refused)
        self.assertFalse(r.failed, r.reason)
        self.assertEqual(r.status, "precondition_failed")

    def test_ok_receipt_but_world_unchanged_is_still_failed(self):
        """回执说成了、格子没变 ⇒ 仍 `failed`（真"挥了没效果"，与"游戏拒绝"分开）。"""
        w = MiniWorld(records=[{"tile": [60, 10], "kind": "unknown"}], tillable=[(60, 10)],
                      inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.result[(60, 10)] = "unknown"          # 回执 ok，但 kind 没变
        r = make_worker(w).till((60, 10))
        self.assertEqual((r.code, r.failed), ("failed", True))
        self.assertFalse(r.refused)
        self.assertFalse(r.proven_inert)
        self.assertEqual(r.status, "")

    def test_refused_is_visible_in_step_and_stage_dicts(self):
        r = SR("till", (60, 10), code="skipped", proven_inert=True, refused=True,
               status="tool_ineffective", reason="游戏判定这格锄不动（Mod status=tool_ineffective）")
        d = r.as_dict()
        self.assertTrue(d["refused"])
        self.assertEqual(d["status"], "tool_ineffective")
        # 没被拒绝的步不许写这两个键（免得工具把"拒绝"当默认）
        plain = SR("till", (60, 10), code="failed", reason="挥了没变").as_dict()
        self.assertNotIn("refused", plain)
        self.assertNotIn("status", plain)
        st = StageResult(stage="till_area", tiles=[(60, 10)], steps=[r])
        self.assertEqual(st.refused_count, 1)
        self.assertEqual(st.refused_steps, [r])
        self.assertEqual(st.failed_steps, [], "被拒绝的格**不算**硬失败")
        self.assertEqual(st.as_dict()["refused"], 1)


class TestStepResult(unittest.TestCase):
    def test_attempted_semantics(self):
        """`attempted` = "这一格的动作被发起过"：纯跳过（没花体力）不算。"""
        self.assertFalse(SR("clear", (1, 2), code="skipped", reason="不该动").attempted)
        self.assertTrue(SR("clear", (1, 2), code="skipped", reason="挥了没变",
                           proven_inert=True).attempted)
        self.assertTrue(SR("till", (1, 2), code="failed").attempted)
        self.assertTrue(SR("till", (1, 2), ok=True).attempted)

    def test_proven_inert_lands_in_as_dict(self):
        d = SR("clear", (1, 2), code="skipped", reason="割不动", proven_inert=True).as_dict()
        self.assertTrue(d["proven_inert"])
        self.assertEqual(d["tile"], [1, 2])
        self.assertFalse("proven_inert" in SR("clear", (1, 2), code="skipped").as_dict())


class TestRunStage(unittest.TestCase):
    def test_stops_at_stamina_gate(self):
        """体力见底时**停下并说清停在哪**，别让每一格都失败一遍。"""
        recs = [weed_rec((60 + i, 10)) for i in range(3)]
        w = MiniWorld(records=recs, inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE,
                      stamina=4.0)
        res = make_worker(w).run_stage("clear_area", [(60, 10), (61, 10), (62, 10)],
                                       min_stamina=12.0)
        self.assertEqual(res.stopped, "stamina")
        self.assertEqual(res.steps, [])
        self.assertIsInstance(res, StageResult)

    def test_reports_each_tile_honestly(self):
        recs = [weed_rec((60, 10)), weed_rec((61, 10))]
        w = MiniWorld(records=recs, inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.stuck.add((61, 10))
        res = make_worker(w).run_stage("clear_area", [(60, 10), (61, 10)])
        self.assertEqual([s.code for s in res.steps], ["ok", "skipped"])
        self.assertEqual(res.ok_count, 1)
        self.assertEqual(res.skipped_count, 1)
        self.assertEqual(len(w.calls), 2)          # 每格只挥一次
        self.assertEqual(len(res.failed_steps), 0)


class TestWorkContext(unittest.TestCase):
    def test_reason_carries_现场诊断(self):
        from agentfarm.farmwork import _work_context
        text = _work_context({"player": {"farmingLevel": 0, "stamina": 204.0,
                                         "tools": {"axe": True, "hoe": True}}})
        self.assertIn("farmingLevel=0", text)
        self.assertIn("204", text)
        self.assertIn("axe", text)


class TestSleepCrossDay(unittest.TestCase):
    """task-8 + task-33：睡觉走"先走离床一步 → 踩**触发格** → 游戏自己弹提问 → 应答"。

    真机 run2 的教训：`interact(bed)`/踩床**原点**从来没把提问弹出来（全日志 `answerDialogue(` 0 次），
    Mod 却照样白等 180s ⇒ 日期一天没跨。task-33 的真机配方（`docs/_il-bed-interaction.md`）：
    触发格是 `TouchAction == "Sleep"` 的那格（本存档 (9,9)/(10,9)，**绝不是床原点 (9,8)**），
    踩中时 `move_to` 回 `ui_modal` = **命中信号**；答 Yes 后提问框不关就永远不落地。
    """

    def test_steps_onto_bed_then_crosses_day(self):
        w = MiniWorld()
        r = make_worker(w).sleep()
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(w.day, 10)
        # ① 先**走离**床格一步（游戏只认"移动中"踩到触发格：`Farmer.hasMoved` 前置）。
        off = [m for m in w.moves if not m["allow_bed"]]
        self.assertTrue(off, w.moves)
        self.assertNotIn(tuple(off[0]["tile"]), w.bed_cells, w.moves)
        # ② 再踩**触发格**（allow_bed=True 是必须的：桥把床判为 blocking）。
        self.assertTrue(any(m["allow_bed"] and tuple(m["tile"]) in w.bed_cells for m in w.moves), w.moves)
        # ③ 踩中的回执是 `ui_modal` ⇒ 命中信号，不许当失败。
        self.assertIn("命中信号", r.reason)
        self.assertIn("触发格", r.reason)
        self.assertEqual(w.sleep_calls, [15000])          # 预算已从 180s 收到 15s
        self.assertEqual(r.before["isInBed"], False)
        self.assertEqual(r.before["question"], "none")
        self.assertEqual(r.after["day"][2], 10)
        self.assertIn("已跨日", r.reason)

    def test_travels_home_before_stepping_on_bed(self):
        w = MiniWorld()
        w.location_name = "Farm"
        r = make_worker(w).sleep()
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(w.location_name, "FarmHouse")
        self.assertEqual(w.day, 10)

    def test_no_question_fails_fast_without_asking_mod(self):
        """踩了触发格仍然没提问 ⇒ 脑侧**立即**判 `sleep_no_question`，连 `sleep` 请求都不发。

        真机 run2 的 180s 就白等在这种情形上（Mod 侧另有 15s 上限；这里只管"别白等、别盲发"）。
        """
        w = MiniWorld()
        w.step_opens_question = False          # 踩了触发格也没弹出提问（真机 run2 的实情）
        r = make_worker(w).sleep()
        self.assertFalse(r.ok)
        self.assertEqual(r.code, "sleep_no_question")     # 与 Mod 的码同名，调用方一处判据
        self.assertFalse(r.receipt)                       # 没发请求 ⇒ 没有 Mod 回执
        self.assertEqual(w.sleep_calls, [])               # **绝不盲发**（IL 上是静默 no-op）
        self.assertEqual(w.interacts, 0)                  # 旧的 interact(床) 兜底已删除
        self.assertIn("触发格候选", r.reason)
        self.assertIn("脑侧现场", r.reason)
        self.assertFalse(r.proven_inert)

    def test_timeout_then_dismiss_rescues_the_day(self):
        """Mod 回 timeout（答了 Yes、`newDay` 已置位、框还挂着）⇒ 脑侧 `dismiss_modal` 兜底**促成**跨日。

        真机定案（`logs/probe-bed-close-run1.log`）：关框 ~3s 当天落地 ⇒ 不许把这种情形记成失败。
        """
        w = MiniWorld()
        w.sleep_mode = "timeout"
        r = make_worker(w).sleep()
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(w.dismiss_calls, 1)
        self.assertEqual(w.day, 10)
        self.assertIn("关框兜底", r.reason)
        self.assertEqual(r.code, "")

    def test_timeout_without_day_change_stays_timeout(self):
        """关框也没救回来 ⇒ 如实 `timeout`，且 Mod 的 `Diagnose()` 原文要留在 reason 里。"""
        w = MiniWorld()
        w.sleep_mode = "timeout"
        w.dismiss_finishes_day = False
        r = make_worker(w).sleep()
        self.assertFalse(r.ok)
        self.assertEqual(r.code, "timeout")
        self.assertIn("newDaySync", r.reason)             # Diagnose() 的原文进 reason
        self.assertTrue(r.receipt)
        self.assertEqual(w.dismiss_calls, 1)

    def test_ok_receipt_without_day_change_is_failed(self):
        """回执说成了但日期没动 ⇒ 必须 failed：判据只认观测差分（IL 定案：回执只是声明）。"""
        w = MiniWorld()
        w.sleep_mode = "no_day"
        r = make_worker(w).sleep()
        self.assertFalse(r.ok)
        self.assertEqual(r.code, "failed")
        self.assertIn("日期没变", r.reason)
        self.assertIn("脑侧判据", r.reason)
        self.assertTrue(r.receipt)

    def test_question_already_open_skips_bed_step(self):
        """提问已经开着（task-6 PASS 探针那种情形）⇒ 不必再踩床，直接应答。"""
        w = MiniWorld()
        w.in_bed = True
        r = make_worker(w).sleep()
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(w.moves, [])
        self.assertEqual(r.before["isInBed"], True)

    # ---- 触发格从哪来（task-33 第 5 条：不许硬编码 (9,9)/(10,9)）----

    def test_bed_cells_prefer_bridge_over_fallback(self):
        """桥报的 `furniture[].bedCells` 是权威（它用游戏自己的 `doesTileHaveProperty` 现算）。"""
        w = MiniWorld()
        w.bed_cells = [(62, 14)]                 # 只有一格是真的（另一格这一帧不是触发格）
        self.assertEqual(FarmWorker.bed_cells(w.obs()), [(62, 14)])

    def test_bed_cells_fall_back_to_two_slots_when_bridge_silent(self):
        """旧 Mod / 桥没报 `bedCells` ⇒ 退回床原点的两个兜底槽位（`(x,y+1)`/`(x+1,y+1)`）。"""
        from agentfarm.farmwork import BED_CELL_FALLBACK
        w = MiniWorld()
        obs = w.obs()
        obs["location"]["furniture"][0].pop("bedCells")
        self.assertEqual(FarmWorker.bed_cells(obs), [(62 + dx, 13 + dy) for dx, dy in BED_CELL_FALLBACK])

    def test_bed_found_from_furniture_even_when_absent_from_tiles(self):
        """床格常常**不在** `location.tiles[]` 里（不可站/不可动就不上报）⇒ 判据必须只看 furniture。"""
        w = MiniWorld()                          # records 默认空
        self.assertNotIn((62, 13), [tuple(r["tile"]) for r in w.records])   # tiles 里没有床
        self.assertEqual(FarmWorker.bed_cells(w.obs()), [(62, 14), (63, 14)])

    def test_door_failure_receipt_is_reported_verbatim(self):
        """门走不通时（`Edge.Source` 是触发锚点、不是可站格）Mod 的现场要**原样**上报，不许吞。

        ⚠ C# 侧"门旁可站格优先"（`MoveToLocationSkill.BuildCandidates`）没法用 Python 单测钉住，
        这里只钉住脑侧不吞回执：真机配方见 task-33 第 4 条。
        """
        door_note = ("第 1 跳失败（timeout）：走向 Farm → FarmHouse 的 warp 源格 (64,14) 超时；"
                     "本跳试过的格子：(64,14)(source)=unreachable、(65,14)(cross)=unreachable")
        w = MiniWorld()
        w.location_name = "Farm"
        w.move_to_location_fail = door_note
        r = make_worker(w).sleep()
        self.assertFalse(r.ok)
        self.assertIn("(64,14)", r.reason)
        self.assertIn("(65,14)", r.reason)
        self.assertEqual(w.sleep_calls, [])      # 人到不了床边 ⇒ 不发 sleep

    # ---- NIT-3：桥中途沉默 ⇒ 有界返回，不许 traceback 穿出（deputy-lead task-33 验收）----

    def test_bridge_down_mid_bed_step_returns_bounded_result(self):
        """NIT-3①：**踩床途中**桥死 ⇒ 不抛异常，`ok=False` + `code="bridge_down"` + 最后一步。"""
        w = MiniWorld()
        w.observe_fail_status = "bridge_down"
        w.observe_fail_mode = "mid"              # 第 1 次观察（初始 snap）成功，之后每次抛
        r = make_worker(w).sleep()               # ← 会抛的话这条用例直接 ERROR
        self.assertFalse(r.ok)
        self.assertEqual(r.code, "bridge_down")
        self.assertIn("睡觉过程中桥失败", r.reason)
        self.assertIn("跨日未完成，请按桥掉线处理", r.reason)
        self.assertIn("最后一步=", r.reason)
        self.assertIn("先走离一步再踩触发格", r.reason)     # 现场说明"死在哪一步"
        self.assertEqual(w.day, 9)                        # 确实没跨日
        self.assertNotEqual(r.after.get("stage"), None)

    def test_bridge_down_after_day_change_still_counts_as_crossed(self):
        """NIT-3②：跨日**已经发生**之后桥才死 ⇒ 仍按成功返回（判据是观测差分，不看桥活着）。"""
        w = MiniWorld()
        w.observe_fail_status = "bridge_down"
        w.observe_fail_mode = "after_sleep"      # sleep 回执之后那次观察抛，且只抛一次
        r = make_worker(w).sleep()
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(w.day, 10)
        self.assertIn("已跨日", r.reason)
        self.assertIn("之后桥失败", r.reason)
        self.assertEqual(r.code, "")

    def test_sleep_call_bridge_down_is_bounded_and_normalized(self):
        """NIT-3③：桥自己的码（`connection_broken`）也要折成 `bridge_down`，且不走"兜底关框"。"""
        w = MiniWorld()
        w.sleep_mode = "bridge_down"             # MiniWorld.do_sleep 抛 status="connection_broken"
        r = make_worker(w).sleep()
        self.assertFalse(r.ok)
        self.assertEqual(r.code, "bridge_down")
        self.assertIn("睡觉过程中桥失败", r.reason)
        self.assertEqual(w.dismiss_calls, 0)     # 桥都死了 ⇒ 不做需要桥的补救
        self.assertEqual(w.day, 9)


class TestTask43LongPathRecovery(unittest.TestCase):
    """task-43：长距离进建筑走不到 ⇒ 两段式接近 + 默认 60000ms + 有界重试。

    真机证据（run4，Lead 现场三连复现）：从田里 `Farm [47,29]` 回农舍，A* 真实路径 ≈88 步
    （被草/石/枝/树逼得绕路 3 倍），Mod 每跳只有 8s ⇒ 门口那一跳 `timeout（8000ms，剩余 58 步
    未走完）`，两次睡觉都 `sleep_failed`；同一候选连走两次分别剩 52/16 步 ⇒ **人在推进**。
    Mod 侧改成"跳预算按剩余步数 + 有进展就续跳"（`MoveToLocationSkill.HopBudget` /
    `StepMover.Tick`，本仓库没有 C# 测试工程，那部分由 build + 真机三连命令验收）；
    本用例类钉住的是**脑侧契约**：能解析回执、只重试一次、默认 60000、失败原因如实落账。
    """

    def _worker(self, w: MiniWorld) -> FarmWorker:
        return make_worker(w)

    def _long_path_fail(self, *, src=(64, 14), steps=52, status="timeout"):
        """Mod 失败回执的原文（照 run4/Lead 复现的措辞）。"""
        return {"fail": {
            "status": status,
            "reason": (f"第 1 跳失败（{status}）：走向 Farm → FarmHouse 的 warp 源格 "
                       f"({src[0]},{src[1]}) 超时（单跳预算 8000ms，剩余 {steps} 步未走完）。"),
        }}

    def test_timeout_is_recovered_by_two_phase_approach(self):
        """①长路径单跳超时 ⇒ 先走到 warp 源格旁的可站格，再只重试一次 ⇒ 到达。"""
        w = MiniWorld()
        w.location_name = "Farm"
        w.move_to_location_script = [self._long_path_fail(), {"ok": True}]
        r = self._worker(w).ensure_location("FarmHouse")
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(w.location_name, "FarmHouse")
        self.assertIn("两段式救回", r.reason)
        # 第一次 60000（task-43 新默认），重试用一半预算（≥15000）⇒ 必 ≤ 第一次
        calls = w.move_to_location_calls
        self.assertEqual([c["timeout_ms"] for c in calls], [60000, 30000])
        self.assertEqual(len(calls), 2)                     # 只重试一次，绝不风暴
        # 先接近：四邻里挑一格（观测没覆盖 ⇒ 按 NEIGHBORS 第一顺位 (64,13)）
        self.assertTrue(any(m["tile"] == [64, 13] for m in w.moves), w.moves)

    def test_default_request_budget_is_sixty_seconds(self):
        """③Mod 侧单请求上限 60000 ⇒ 脑侧默认也必须传 60000（否则 30s 又饿死）。"""
        w = MiniWorld()
        w.location_name = "Farm"
        w.move_to_location_script = [{"ok": True}]
        r = self._worker(w).ensure_location("FarmHouse")
        self.assertTrue(r.ok)
        self.assertEqual(w.move_to_location_calls[0]["timeout_ms"], 60000)

    def test_both_attempts_failing_is_bounded_and_honest(self):
        """④两次都超时 ⇒ 有界停手（恰 2 次请求），原因带 剩余步数/warp 源格/玩家坐标。"""
        w = MiniWorld()
        w.location_name = "Farm"
        w.move_to_location_script = [self._long_path_fail(steps=52),
                                     self._long_path_fail(steps=16)]
        r = self._worker(w).ensure_location("FarmHouse")
        self.assertFalse(r.ok)
        self.assertEqual(r.code, "failed")
        self.assertTrue(r.inconclusive)                     # timeout ⇒ 没结论（不封格、不占额）
        self.assertEqual(len(w.move_to_location_calls), 2)  # 有界：1 次 + 1 次重试
        self.assertIn("剩余 16 步未走完", r.reason)
        self.assertIn("(64,14)", r.reason)
        self.assertIn("脑侧现场：人在", r.reason)
        self.assertIn("两段式", r.reason)
        self.assertTrue(r.receipt)

    def test_receipt_without_source_tile_is_still_bounded(self):
        """没有 `warp 源格` 的回执（例如 `unreachable`）⇒ 不做两段式，如实记明原因。"""
        w = MiniWorld()
        w.location_name = "Farm"
        w.move_to_location_script = [{"fail": {"status": "unreachable",
                                               "reason": "本跳试过的格子：(64,14)=unreachable"}}]
        r = self._worker(w).ensure_location("FarmHouse")
        self.assertFalse(r.ok)
        self.assertEqual(len(w.move_to_location_calls), 1)
        self.assertIn("回执里没有 warp 源格", r.reason)
        self.assertIn("脑侧现场：人在", r.reason)

    def test_neighbour_pick_prefers_observed_standable(self):
        """源格四邻里，观测**明说能站**的那一格优先（不许乱赌）。"""
        w = MiniWorld()
        w.location_name = "Farm"
        # 观测里 (64,15) 可站、(65,14) 不可站；NEIGHBORS 顺序是 上/下/右/左
        w.records = [{"tile": [64, 15], "kind": "dirt", "standable": True},
                     {"tile": [65, 14], "kind": "stone", "standable": False, "blocking": True}]
        obs = w.obs()
        self.assertEqual(FarmWorker._neighbour_to_walk(obs, (64, 14)), (64, 15))

    def test_neighbour_pick_gives_up_when_all_four_are_blocked(self):
        """四邻全被观测标成不可站 ⇒ 不硬走（返回 None，让上层如实报失败）。"""
        w = MiniWorld()
        w.records = [{"tile": [64, 13], "kind": "stone", "standable": False, "blocking": True},
                     {"tile": [64, 15], "kind": "stone", "standable": False, "blocking": True},
                     {"tile": [65, 14], "kind": "stone", "standable": False, "blocking": True},
                     {"tile": [63, 14], "kind": "stone", "standable": False, "blocking": True}]
        self.assertIsNone(FarmWorker._neighbour_to_walk(w.obs(), (64, 14)))

    def test_receipt_parsers_read_the_real_machine_wording(self):
        """回执解析必须认 run4/Lead 复现的逐字措辞。"""
        text = ("第 1 跳失败（timeout）：走向 Farm → FarmHouse 的 warp 源格 (64,14) 超时"
                "（单跳预算 8000ms，剩余 58 步未走完）。本跳试过的格子：(64,14)(source)=unreachable")
        self.assertEqual(FarmWorker._warp_source_of(text), (64, 14))
        self.assertEqual(FarmWorker._remaining_steps_of(text), 58)
        self.assertIsNone(FarmWorker._warp_source_of("没有源格的老回执"))
        self.assertIsNone(FarmWorker._remaining_steps_of("没有步数的老回执"))


class TestTask42Sell(unittest.TestCase):
    """task-42 出货闭环：**白名单只认"亲眼看见进了背包"的东西**，判据只看观测差分。

    用户 m08335 的原话是"怎么到现在一分钱也没挣到呀？"，但修法**不是**让脑去点钱：
    钱只能由游戏下一次 `NewDay` 结算，所以这里钉死三件事：
    ① 收货没进背包 ⇒ 不进白名单（不许凭空生成"可卖物"）；
    ② 白名单外的东西（工具/种子/建材）一格都不许出；
    ③ 回执 ok 但世界没动 ⇒ 如实记失败（回执只是声明）。
    """

    def _worker(self, w: MiniWorld) -> FarmWorker:
        return make_worker(w)

    @staticmethod
    def _ripe(tile=(62, 15)) -> dict:
        return {"tile": list(tile), "kind": "dirt", "feature": "HoeDirt", "crop": "24",
                "ripe": True, "watered": True, "standable": True, "actionable": True}

    def test_harvest_records_loot_only_when_inventory_grows(self):
        """①作物摘下来 + 背包多了一件 ⇒ 进白名单；只摘下来而背包没多 ⇒ **不进**白名单。"""
        w = MiniWorld(records=[self._ripe()])
        worker = self._worker(w)
        st = worker.harvest((62, 15))
        self.assertTrue(st.ok)
        self.assertEqual(worker.harvested, {"(O)24": 1})
        self.assertEqual((st.after or {}).get("harvested"), {"(O)24": 1})
        self.assertIn("进背包", st.reason)

        w2 = MiniWorld(records=[self._ripe()])
        w2.harvest_item = None                      # 收了，但什么都没进背包（真机有这种丢货情形）
        worker2 = self._worker(w2)
        st2 = worker2.harvest((62, 15))
        self.assertTrue(st2.ok)
        self.assertEqual(worker2.harvested, {})
        self.assertIn("背包没有新增物品", st2.reason)

    def test_sell_loot_ships_whitelisted_loot_and_shrinks_the_list(self):
        """②白名单里的东西**整件**进箱；工具在旁边一动不动；**钱当天不变**（等 NewDay 结算）。"""
        w = MiniWorld()
        w.inventory = [
            {"slot": 0, "id": "24", "qualifiedId": "(O)24", "name": "Parsnip",
             "stack": 2, "isTool": False},
            {"slot": 1, "id": "47", "qualifiedId": "(W)47", "name": "Scythe",
             "stack": 1, "isTool": True},
        ]
        worker = self._worker(w)
        worker.harvested = {"(O)24": 2}
        steps = worker.sell_loot()
        self.assertEqual(len(steps), 1)
        st = steps[0]
        self.assertTrue(st.ok)
        self.assertEqual(w.sell_calls[0]["whitelist"], ["(O)24"])
        self.assertEqual(w.sell_calls[0]["slot"], 0)
        self.assertEqual(len(w.shipping_bin), 1)
        self.assertEqual(w.shipping_bin[0]["qualifiedId"], "(O)24")
        self.assertIsNone(w.inventory[0])
        self.assertEqual(w.inventory[1]["qualifiedId"], "(W)47")   # 工具没被动
        self.assertEqual(worker.harvested, {})                      # 出光 ⇒ 白名单清空
        # 钱当天不变：判据必须落在背包/箱子差分上，而不是钱
        self.assertEqual(st.before["money"], 500)
        self.assertEqual(st.after["money"], 500)
        self.assertIn("NewDay", st.reason)
        self.assertIn("出货箱", st.reason)

    def test_whitelist_empty_means_not_one_item_is_shipped(self):
        """③白名单空 ⇒ 连一次请求都不发（绝不做"除工具以外都能卖"的黑名单）。"""
        w = MiniWorld()
        w.inventory = [{"slot": 0, "id": "24", "qualifiedId": "(O)24", "name": "Parsnip",
                        "stack": 3, "isTool": False}]
        worker = self._worker(w)
        self.assertEqual(worker.sellable_slots(w.obs()), [])
        self.assertEqual(worker.sell_loot(), [])
        self.assertEqual(w.sell_calls, [])
        self.assertEqual(w.shipping_bin, [])

    def test_not_whitelisted_is_reported_with_status_and_receipt(self):
        """④白名单外的物品：Mod 回 `not_whitelisted` ⇒ 如实失败、背包不变、回执留着。"""
        w = MiniWorld()
        w.inventory = [{"slot": 0, "id": "47", "qualifiedId": "(W)47", "name": "Scythe",
                        "stack": 1, "isTool": True}]
        worker = self._worker(w)
        st = worker.sell(0, whitelist=["(O)24"])
        self.assertFalse(st.ok)
        self.assertEqual(st.code, "failed")
        self.assertTrue(st.receipt)
        self.assertIn("not_whitelisted", st.receipt)
        self.assertIn("出货没有生效", st.reason)
        self.assertEqual(st.before["count"], 1)
        self.assertEqual(st.after["count"], 1)
        self.assertEqual(len(w.shipping_bin), 0)

    def test_ok_receipt_without_world_change_is_never_ok(self):
        """⑤回执 ok 但格子没空、箱子没变 ⇒ 判失败（回执只是声明）。"""
        w = MiniWorld()
        w.inventory = [{"slot": 0, "id": "24", "qualifiedId": "(O)24", "name": "Parsnip",
                        "stack": 1, "isTool": False}]
        w.sell_mode = "no_effect"
        worker = self._worker(w)
        worker.harvested = {"(O)24": 1}
        st = worker.sell(0, whitelist=["(O)24"])
        self.assertFalse(st.ok)
        self.assertEqual(st.code, "failed")
        self.assertIn("出货没有生效", st.reason)
        self.assertEqual(len(w.shipping_bin), 0)
        self.assertEqual(worker.harvested, {"(O)24": 1})     # 失败不洗白名单
        self.assertEqual(st.after["shipping_bin"], 0)

    def test_sell_loot_stops_at_the_first_failure(self):
        """⑥第一件就失败 ⇒ 停手（有界，不把剩下的格子一个个撞上去）。"""
        w = MiniWorld()
        w.inventory = [
            {"slot": 0, "id": "24", "qualifiedId": "(O)24", "name": "Parsnip",
             "stack": 1, "isTool": False},
            {"slot": 1, "id": "24", "qualifiedId": "(O)24", "name": "Parsnip",
             "stack": 1, "isTool": False},
        ]
        w.sell_mode = "timeout"
        worker = self._worker(w)
        worker.harvested = {"(O)24": 2}
        steps = worker.sell_loot()
        self.assertEqual(len(steps), 1)
        self.assertFalse(steps[0].ok)
        self.assertEqual(len(w.sell_calls), 1)


class TestFarmDryTiles(unittest.TestCase):
    """task-50：`farm.dryTiles`（Mod 报的窗口外干作物坐标）的**三态**读取。

    run5 的病灶是"窗口外还有 1 格干作物，脑侧既看不见也没坐标 ⇒ `no_work` 收工"。
    这三态必须分清：能用（ok）/ 只报了一部分（truncated）/ **不可用**（旧 Mod 缺字段）。
    最后一态最关键：缺字段**不许**当成"没有干格"，但也不许瞎猜坐标去浇。
    """

    def test_ok_returns_deduped_tiles_in_report_order(self):
        obs = {"farm": {"complete": True, "dryTiles": [[61, 10], [40, 3], [61, 10]]}}
        tiles, status = farm_dry_tiles(obs)
        self.assertEqual(tiles, [(61, 10), (40, 3)], "去重但保持 Mod 报的顺序（y→x 已排好）")
        self.assertEqual(status, "ok")

    def test_truncated_is_reported_as_such(self):
        obs = {"farm": {"complete": True, "dryTiles": [[61, 10]],
                        "dryTilesTruncated": True}}
        tiles, status = farm_dry_tiles(obs)
        self.assertEqual(tiles, [(61, 10)])
        self.assertEqual(status, "truncated", "截断要如实说，免得把「报了 64 格」当全集")

    def test_missing_or_untrusted_farm_is_unavailable_never_empty(self):
        """旧 Mod / 未加载 / 没扫完 ⇒ `unavailable`，绝不等于"没有干格"。"""
        cases = [
            {},                                                        # 完全没有 farm 块
            {"farm": {}},                                              # 老 Mod 的 farm 块
            {"farm": {"complete": True}},                              # 有 complete、没 dryTiles
            {"farm": {"complete": False, "dryTiles": [[61, 10]]}},     # 没扫完 ⇒ 不信
            {"farm": {"loaded": False, "complete": True, "dryTiles": [[61, 10]]}},
        ]
        for obs in cases:
            with self.subTest(obs=obs):
                self.assertEqual(farm_dry_tiles(obs), ([], "unavailable"),
                                 f"{obs} 必须判「不可用」，不许判成「没有干格」")

    def test_dirty_entries_are_skipped_not_trusted(self):
        obs = {"farm": {"complete": True,
                        "dryTiles": [[61, 10], [61], "6,1", None, [61, "x"], [63, 12]]}}
        tiles, status = farm_dry_tiles(obs)
        self.assertEqual(tiles, [(61, 10), (63, 12)], "脏数据跳过，好数据照收")
        self.assertEqual(status, "ok")


class TestTask52Unreachable(unittest.TestCase):
    """task-52：`unreachable`（没有落脚点 / 寻路到不了）是**独立一类**，`failed` 对它为 False。

    真机依据（run5 summer 1）：那天做成 109 步、`final_water.dry=0`，却因 8 格 `clear` 全报
    「四邻都站不过去」⇒ `no_hard_failures=false` ⇒ 高产的一天拿不到 `verified`。
    它**不是**成功：`longrun` 当天记进 `blocked`（当天不再白试、**次日重试**），日级豁免有上界。
    """

    def _worker_on(self, tile, *, unwalkable=None, fail_status=None):
        w = MiniWorld(records=[weed_rec(tile)], inventory=INV_WITH_SCYTHE,
                      tools=TOOLS_WITH_SCYTHE)
        w.unwalkable = {tuple(t) for t in (unwalkable or [])}
        if fail_status:
            w.fail_status[tuple(tile)] = fail_status
        return w, make_worker(w)

    def test_stand_next_to_failure_is_unreachable_not_failed(self):
        """四邻都站不过去 ⇒ `code=unreachable`、`failed=False`、`attempted=True`。"""
        tile = (60, 10)
        nb = [(tile[0] + dx, tile[1] + dy) for dx, dy in NEIGHBORS]
        w, worker = self._worker_on(tile, unwalkable=nb)
        r = worker.clear(tile)
        self.assertEqual(r.code, "unreachable")
        self.assertIs(r.failed, False, "走不到不是硬失败（run5 那 8 格就是这么被误判的）")
        self.assertIs(r.unreachable, True)
        self.assertIs(r.attempted, True, "它确实发起过（花了寻路与观察），不算 skip")
        self.assertIn("四邻都站不过去", r.reason)
        self.assertEqual(w.calls, [], "根本没挥出去：use_tool 一次都不许发")

    def test_till_stand_next_to_failure_is_unreachable(self):
        tile = (60, 10)
        nb = [(tile[0] + dx, tile[1] + dy) for dx, dy in NEIGHBORS]
        w = MiniWorld(records=[{"tile": list(tile), "kind": "unknown", "standable": True}],
                      tillable=[tile], tools=TOOLS_WITH_SCYTHE)
        w.unwalkable = {tuple(t) for t in nb}
        r = make_worker(w).till(tile)
        self.assertEqual(r.code, "unreachable")
        self.assertIs(r.failed, False)
        self.assertEqual(w.calls, [])

    def test_mod_unreachable_status_is_classified_too(self):
        """Mod 自己回 `unreachable`（A* 没算出路径）同样归这一类。"""
        tile = (60, 10)
        w, worker = self._worker_on(tile, fail_status="unreachable")
        r = worker.clear(tile)
        self.assertEqual(r.code, "unreachable")
        self.assertIs(r.failed, False)
        self.assertIn("走不到", r.reason)

    def test_is_unreachable_reads_both_status_and_machine_wording(self):
        self.assertTrue(is_unreachable("unreachable"))
        self.assertTrue(is_unreachable("", "本跳试过的格子：(64,14)(source)=unreachable"))
        self.assertTrue(is_unreachable("", "四邻都站不过去（没有落脚点）"))
        self.assertTrue(is_unreachable("", "A* 未算出路径"))
        self.assertFalse(is_unreachable("timeout"))
        self.assertFalse(is_unreachable("tool_ineffective"))
        self.assertFalse(is_unreachable(""))

    def test_unreachable_step_is_not_in_failed_steps_and_survives_as_dict(self):
        tile = (60, 10)
        nb = [(tile[0] + dx, tile[1] + dy) for dx, dy in NEIGHBORS]
        w, worker = self._worker_on(tile, unwalkable=nb)
        r = worker.clear(tile)
        stage = StageResult(stage="clear_area", tiles=[tile], steps=[r])
        self.assertEqual(stage.failed_steps, [])
        self.assertEqual(stage.unreachable_count, 1)
        self.assertEqual(stage.as_dict()["unreachable"], 1)
        self.assertIs(r.as_dict().get("unreachable"), True)
        self.assertNotIn("proven_inert", r.as_dict(), "走不到不许被当成「证明干不动」")


class TestFarmDeadCrops(unittest.TestCase):
    """task-51：`farm_dead_crops` 三态 —— 旧 Mod 缺字段**绝不许**当 0。"""

    def test_reads_count_only_when_complete(self):
        self.assertEqual(farm_dead_crops({"farm": {"loaded": True, "complete": True,
                                                  "deadCrops": 23}}), (23, "ok"))
        self.assertEqual(farm_dead_crops({"farm": {"loaded": True, "complete": True,
                                                   "deadCrops": 0}}), (0, "ok"))
        self.assertEqual(farm_dead_crops({"farm": {"loaded": True, "complete": True,
                                                   "deadCrops": -4}}), (0, "ok"))

    def test_missing_field_is_unavailable_not_zero(self):
        """旧 Mod 没有 `deadCrops` ⇒ `unavailable`（不是"没有死苗"）。"""
        self.assertEqual(farm_dead_crops({"farm": {"loaded": True, "complete": True}}),
                         (0, "unavailable"))
        self.assertEqual(farm_dead_crops({"farm": {"filled": True, "complete": False,
                                                   "deadCrops": 9}}), (0, "unavailable"))
        self.assertEqual(farm_dead_crops({"farm": {"loaded": False, "complete": True,
                                                   "deadCrops": 9}}), (0, "unavailable"))
        self.assertEqual(farm_dead_crops({}), (0, "unavailable"))


class TestTask51ClearDead(unittest.TestCase):
    """task-51：清枯死作物。**活苗绝不碰**；判据只看观测差分（`crop` 消失）。

    真机依据：summer 2 的窗口 400 格里 24 个作物有 23 个 `dead=True`，而 `till_blocked_by`
    见到 crop 就回「有作物」⇒ 不清死苗就永远种不上（`till` 也永远被拒）。
    """

    def _worker(self, rec, *, inventory=None, tools=None, dead=True, **kw):
        tile = tuple(rec["tile"])
        w = MiniWorld(records=[dict(rec)],
                      inventory=INV_WITH_SCYTHE if inventory is None else inventory,
                      tools=TOOLS_WITH_SCYTHE if tools is None else tools, **kw)
        if dead:
            w.dead_crops.add(tile)
        return w, make_worker(w)

    def test_dead_crop_is_cleared_and_diff_proves_it(self):
        """死苗 ⇒ `ok`，**判据是 crop 从观测里消失**（回执只是声明）。"""
        tile = (60, 10)
        w, worker = self._worker(dead_crop_rec(tile))
        r = worker.clear_dead(tile)
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(r.code, "")
        self.assertIs(r.failed, False)
        self.assertIs(r.proven_inert, False)
        self.assertIn("已清掉枯死作物", r.reason)
        self.assertIn("第1次请求→无作物", r.reason)
        self.assertEqual(w.calls, [(tile, "scythe")], "先镰刀（不毁耕地），一次就够")
        self.assertNotIn("crop", FarmWorker.tiles_of(w.obs())[tile])
        self.assertEqual(r.after.get("requests"), 1)
        self.assertEqual(r.after.get("statuses"), ["ok"])

    def test_live_seedling_is_never_touched(self):
        """活苗 ⇒ `skipped` 且**一次都不挥**（本卡的红线）。"""
        tile = (60, 10)
        w, worker = self._worker(live_crop_rec(tile), dead=False)
        r = worker.clear_dead(tile)
        self.assertIs(r.ok, False)
        self.assertEqual(r.code, "skipped")
        self.assertIs(r.proven_inert, False, "活苗不是「证明干不动」，是「不该动」")
        self.assertIn("活苗", r.reason)
        self.assertEqual(w.calls, [])
        self.assertIn("crop", FarmWorker.tiles_of(w.obs())[tile], "活苗必须原样在")

    def test_missing_tools_means_no_swing_and_the_tile_is_sealed(self):
        """镰刀与锄头**都明确不在**（`tools` 位也是 false）⇒ 先判后动：一次不挥，封格。

        注意：观测里**读不到**工具信息是「判不准 ⇒ 放行」，只有 Mod 明确说 false 才拦
        （`tool_missing_reason` 的口径，用户 m01758/m01804 要的正是这条）。
        """
        tile = (60, 10)
        none_tools = {k: False for k in ("axe", "pickaxe", "hoe", "wateringCan", "weapon")}
        w, worker = self._worker(dead_crop_rec(tile), inventory=[], tools=none_tools)
        r = worker.clear_dead(tile)
        self.assertEqual(r.code, "skipped")
        self.assertIs(r.proven_inert, True)
        self.assertIs(r.failed, False)
        self.assertIn("清不掉", r.reason)
        self.assertIn("scythe", r.reason)
        self.assertEqual(w.calls, [])

    def test_mod_tool_ineffective_is_sealed_not_failed(self):
        """Mod 说「工具全无效」（世界给的前置事实）⇒ `skipped`+封格，**不是**硬失败。"""
        tile = (60, 10)
        w, worker = self._worker(dead_crop_rec(tile))
        w.fail_status[tile] = "tool_ineffective"
        r = worker.clear_dead(tile)
        self.assertEqual(r.code, "skipped")
        self.assertIs(r.proven_inert, True)
        self.assertIs(r.failed, False, "run5 就是被这类「拒绝」烧成 no_hard_failures=false")
        self.assertIn("工具全无效", r.reason)
        self.assertEqual(len(w.calls), 1, "回「无效」是结论性的：不必挥满上限")

    def test_unreachable_is_its_own_class(self):
        """四邻都站不过去 ⇒ task-52 的 `unreachable`（不是清死苗失败，也不封格）。"""
        tile = (60, 10)
        w, worker = self._worker(dead_crop_rec(tile))
        w.unwalkable = {(tile[0] + dx, tile[1] + dy) for dx, dy in NEIGHBORS}
        r = worker.clear_dead(tile)
        self.assertEqual(r.code, "unreachable")
        self.assertIs(r.unreachable, True)
        self.assertIs(r.failed, False)
        self.assertEqual(w.calls, [])

    def test_no_crop_at_all_is_already_done(self):
        """格子上没作物（别人已经清过）⇒ `ok/already`，不挥。"""
        tile = (60, 10)
        rec = {"tile": list(tile), "kind": "dirt", "feature": "HoeDirt", "standable": False}
        w, worker = self._worker(rec, dead=False)
        r = worker.clear_dead(tile)
        self.assertTrue(r.ok)
        self.assertEqual(r.code, "already")
        self.assertEqual(w.calls, [])


class TestSeedOffers(unittest.TestCase):
    """task-67 选品三件套：解析回执 → 认种子 → 挑"最便宜且买得起"的。"""

    def test_parses_available_items_and_tolerates_junk(self):
        rows = [{"id": "(O)483", "name": "Wheat Seeds", "price": 10},
                {"id": "", "name": "坏条目（没有 id）", "price": 5},
                {"id": "(O)24", "name": "Parsnip", "price": "20"},
                "不是字典",
                {"id": "(O)400", "name": "没价"}]          # 缺 price ⇒ 按 0
        offers = seed_offers_from({"availableItems": rows})
        self.assertEqual([o["id"] for o in offers], ["(O)483", "(O)24", "(O)400"])
        self.assertEqual(offers[1]["price"], 20)
        self.assertEqual(offers[2]["price"], 0)
        # 旧键 `available` 也认（桥面刚加字段时的兼容）
        self.assertEqual(seed_offers_from({"available": rows[:1]})[0]["id"], "(O)483")
        self.assertEqual(seed_offers_from(None), [])

    def test_is_seed_offer_matches_english_and_chinese(self):
        self.assertTrue(is_seed_offer({"name": "Melon Seeds"}))
        self.assertTrue(is_seed_offer({"name": "小麦种子"}))
        self.assertFalse(is_seed_offer({"name": "Parsnip"}))
        self.assertFalse(is_seed_offer(None))

    def test_pick_three_codes(self):
        """夏季货架（run6 现场）：认得出种子、挑最便宜的、春季硬编码那条路不再是唯一出路。"""
        summer = [{"id": "(O)254", "name": "Melon Seeds", "price": 80},
                  {"id": "(O)483", "name": "Wheat Seeds", "price": 10},
                  {"id": "(O)24", "name": "Parsnip", "price": 20}]
        pick, code = pick_seed_offer(summer, 500)
        self.assertEqual(code, "ok")
        self.assertEqual(pick["id"], "(O)483", "要挑最便宜的可买种子")
        # 一条种子都没有（货架只有作物/矿物）⇒ no_seed_for_sale，绝不下单
        pick, code = pick_seed_offer([{"id": "(O)24", "name": "Parsnip", "price": 20}], 500)
        self.assertIsNone(pick)
        self.assertEqual(code, "no_seed_for_sale")
        # 有种子但按"留够 10 包"的口径买不起 ⇒ cannot_afford（钱 100 ⇒ 预算 10 < 40）
        pick, code = pick_seed_offer([{"id": "(O)482", "name": "Pepper Seeds", "price": 40}], 100)
        self.assertIsNone(pick)
        self.assertEqual(code, "cannot_afford")


class TestTask67BuyAvailable(unittest.TestCase):
    """`FarmWorker.buy` 必须把回执里的货架清单带回来 —— **成功与失败两条路都要**。"""

    def test_success_receipt_carries_the_shelf(self):
        w = MiniWorld(tools={"hoe": True}, inventory=[])
        worker = make_worker(w)
        r = worker.buy("(O)483", 10)
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(len(r.available), 5)
        self.assertEqual(r.available[4]["name"], "Wheat Seeds")
        self.assertEqual(r.as_dict()["available"], r.available)
        self.assertEqual(r.after.get("available"), 5)

    def test_item_not_sold_still_carries_the_shelf(self):
        """run6 的死锁解药：买不到时，回执（`BridgeError.payload`）里必须有货架，脑才能改买。"""
        w = MiniWorld(tools={"hoe": True}, inventory=[])
        worker = make_worker(w)
        r = worker.buy("472", 10)                      # 夏季货架上没有 472（春季种子）
        self.assertFalse(r.ok)
        self.assertEqual(r.code, "failed")
        self.assertEqual([o["id"] for o in r.available], ["(O)254", "(O)479", "(O)481",
                                                          "(O)482", "(O)483"])
        self.assertEqual(seed_offers_from({"availableItems": r.available})[0]["id"], "(O)254")

    def test_old_bridge_without_the_field_gives_empty_shelf(self):
        """旧桥（0.7.24 及之前）没有这个字段 ⇒ 空表（"没有清单"），绝不能伪造货架。"""
        w = MiniWorld(tools={"hoe": True}, inventory=[])
        w.buy_offers = None                            # 旧桥：没有 availableItems 字段
        worker = make_worker(w)
        r = worker.buy("472", 10)
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(r.available, [])
        self.assertNotIn("available", r.as_dict())


class TestTask68OpenWay(unittest.TestCase):
    """task-68（Lead m06336）：判"走不到"之前**先开路** —— 清掉四邻里"可清 + 自己够得着"的邻格。

    真机依据（run6）：`field_ne` 被草 432/石 169/枝 92/树 356 堵住 ⇒ `clear_dead` 一次 ok 都没有、
    `unreachable 42 / bound 8`，最后 19 秒就 `stuck` 收工。修法分三态：
    `ok`（清邻格后站到了）/ `encircled`（四邻**连落脚点都没有**：树/桩/大石一类 ⇒ 不封格、
    不进不可达豁免）/ `exhausted`（有可清的、清了上限还不通 ⇒ 仍按 `unreachable`，有界）。
    变异自检（**实测**，脚本 `scratch\\_t68_mutate.py`：复制 brain+tests 到临时目录做文本替换；
    基线 11/11 绿 —— 本类 4 条 + `test_longrun.TestTask68*` 7 条）：
    * `m68a`：`_ensure_reachable` 里的 `open_way` 短路成 `"exhausted"` ⇒ **5 条红**
      （本类两条 + `test_surrounded_by_unclearable_is_encircled`，以及 longrun 的 encircled 两条）。
    * `m68b`：`open_way` 的 `encircled` 分支并进 `exhausted` ⇒ **3 条红**（encircled 被当成走不到）。
    * `m68c`：`longrun._mark_blocked` 不认 `s.encircled` ⇒ **1 条红**
      （`test_encircled_never_enters_blocked`：被围住就封格了）。
    """

    TARGET = (62, 10)

    def _world(self, records, *, unwalkable=(), player=(60, 10)):
        w = MiniWorld(records=records, inventory=INV_WITH_SCYTHE, tools=TOOLS_WITH_SCYTHE)
        w.player_tile = list(player)
        w.unwalkable = {tuple(t) for t in unwalkable}
        return w

    def test_clearing_a_neighbour_opens_the_way(self):
        """唯一落脚点是丛杂草、而且走不过去 ⇒ 先清掉它，再站过去把目标清了。"""
        nb = [(self.TARGET[0] + dx, self.TARGET[1] + dy) for dx, dy in NEIGHBORS]
        w = self._world([weed_rec(self.TARGET), weed_rec(nb[0])], unwalkable=nb)
        worker = make_worker(w)
        r = worker.clear(self.TARGET)
        self.assertTrue(r.ok, r.reason)
        self.assertIs(r.stood, True, "开路成功后必须真的站到了目标格旁边")
        opened = r.opened
        self.assertTrue(opened, r.as_dict())
        self.assertEqual(opened[0]["neighbour"], [nb[0][0], nb[0][1]])
        self.assertEqual(opened[0]["kind"], "weed")
        self.assertEqual(opened[0]["result"], "ok")
        self.assertEqual(r.as_dict().get("clear_neighbor"), opened)
        # 目标格自己也被清掉了（先清邻格，再清目标）
        self.assertNotIn(self.TARGET, {tuple(x["tile"]) for x in w.records})

    def test_surrounded_by_unclearable_is_encircled(self):
        """四邻全是树/桩一类（`FRONTIER_KINDS` 之外、且没有落脚点）⇒ `encircled`，不是走不到。"""
        nb = [(self.TARGET[0] + dx, self.TARGET[1] + dy) for dx, dy in NEIGHBORS]
        recs = [weed_rec(self.TARGET)]
        recs += [{"tile": list(t), "kind": "tree" if i % 2 else "clump",
                  "standable": False, "actionable": False} for i, t in enumerate(nb)]
        w = self._world(recs, unwalkable=nb)
        r = make_worker(w).clear(self.TARGET)
        self.assertEqual(r.code, "encircled")
        self.assertIs(r.encircled, True)
        self.assertIs(r.failed, False, "被围住不是硬失败，也不是「走不到」")
        self.assertIs(r.unreachable, False)
        self.assertIs(r.stood, False)
        self.assertEqual(w.calls, [], "邻格都清不了 ⇒ 一次工具都不许挥")
        # 【task-78 NIT-2】reason 照实写四邻**真实 kind**，不许再断言"是树/桩/大石"。
        self.assertIn("tree", r.reason)
        self.assertIn("clump", r.reason)
        self.assertNotIn("树/桩/大石", r.reason)
        self.assertIn("试开路 0 次", r.reason)
        self.assertEqual(r.tried_open, 0)
        self.assertEqual(r.encircled_kinds,
                         ["tree" if i % 2 else "clump" for i in range(len(NEIGHBORS))])

    def test_weed_neighbour_that_cannot_be_stood_on_is_told_truthfully(self):
        """【task-78 NIT-2 实证场景】四邻是 `weed`、但 `standable=false` ⇒ 0 次挥动却曾写成
        "树/桩/大石"（与事实不符）。现在 reason 必须照实写 `weed`，且不得出现"树/桩/大石"。"""
        nb = [(self.TARGET[0] + dx, self.TARGET[1] + dy) for dx, dy in NEIGHBORS]
        # deputy 实证的形态：目标格（枯死作物，`standable=False`）四邻是 `weed`，但那些邻格
        # **自己也没法站上去**（半径 3 内都观测成 `standable=False`）⇒ 没有"可清障 + 够得着"的
        # 突破口 ⇒ `encircled`，且一次都不挥（而不是像以前那样写成"树/桩/大石"）。
        ring = [(self.TARGET[0] + dx, self.TARGET[1] + dy)
                for dx in (-3, -2, -1, 0, 1, 2, 3) for dy in (-3, -2, -1, 0, 1, 2, 3)
                if (dx, dy) != (0, 0)]
        recs = [dead_crop_rec(self.TARGET)]
        recs += [{"tile": list(t), "kind": "weed", "actionable": True,
                  "standable": False} for t in ring]
        w = self._world(recs, unwalkable=ring)
        r = make_worker(w).clear_dead(self.TARGET)
        self.assertEqual(r.code, "encircled")
        self.assertEqual(w.calls, [], "四邻够不着 ⇒ 一次都不许挥")
        self.assertIn("weed", r.reason)
        self.assertNotIn("树/桩/大石", r.reason)
        self.assertIn("没有「可清障 + 自己够得着」的突破口", r.reason)
        self.assertEqual(r.encircled_kinds, ["weed"] * len(NEIGHBORS))
        self.assertEqual(r.tried_open, 0)

    def test_open_way_is_bounded_then_still_unreachable(self):
        """有可清的邻格、但清掉也没用（邻格自己被拒）⇒ 有界地退回 `unreachable`。"""
        nb = [(self.TARGET[0] + dx, self.TARGET[1] + dy) for dx, dy in NEIGHBORS]
        w = self._world([weed_rec(self.TARGET), weed_rec(nb[0])], unwalkable=nb)
        w.fail_status[nb[0]] = "tool_ineffective"       # 邻格自己清不动 ⇒ 换不了突破口
        r = make_worker(w).clear(self.TARGET)
        self.assertEqual(r.code, "unreachable")
        self.assertIs(r.failed, False)
        self.assertEqual(len(w.calls), 1, "只试一次就停（有界），不许在同一格死磕")
        self.assertIn("上限 4 次", r.reason)

    def test_stood_is_true_only_when_really_beside_target(self):
        """`stood` 的口径：真的站到目标格旁边才 True（日级不可达上界的分母靠它）。"""
        w = self._world([weed_rec(self.TARGET)], player=self.TARGET)
        r = make_worker(w).clear(self.TARGET)
        self.assertTrue(r.ok)
        self.assertIs(r.stood, True)
        # 走不到时不许把它算成"站过"
        nb = [(self.TARGET[0] + dx, self.TARGET[1] + dy) for dx, dy in NEIGHBORS]
        w2 = self._world([weed_rec(self.TARGET)], unwalkable=nb)
        r2 = make_worker(w2).clear(self.TARGET)
        self.assertEqual(r2.code, "unreachable")
        self.assertIs(r2.stood, False)


class TestTask55SurplusPlan(unittest.TestCase):
    """task-55：`surplus_sell_plan()`（卖盈余材料换种子钱的**纯决策**）。

    为什么单独测这一层：这是"卖 → 到账 → 买 → 种"闭环的第一步，而它必须**在发请求之前**就把
    "卖哪几叠、留多少"算清楚（整叠出货没有"卖一部分"的能力）。四条纪律各有对应用例：
    三条门闸、fail-closed 白名单、留够 K、以及"唯一一大叠"时的如实标记。

    变异自检（`%TEMP%\\t55_mutate.py`，复制 brain+tests 到临时目录做文本替换、跑完即弃）：
    基线 14/14 绿；**m55a**（去掉门闸里的 `money < threshold` 条件）⇒ 红 2
    （`test_no_sell_when_money_seeds_or_dirt_are_fine` + `test_three_gates_decide_whether_to_sell`）；
    **m55b**（去掉 `_sell_surplus_for_seeds` 的"当天只卖一次"守卫）⇒ 红 1；
    **m55c**（`cannot_afford` 事件改名藏证据）⇒ 红 1。
    """

    #: 材料叠（`ItemView` 形态）。Wood 25 / Stone 3 / Fiber 10。
    MATERIALS = [
        {"slot": 6, "id": "388", "qualifiedId": "(O)388", "name": "Wood", "stack": 25, "isTool": False},
        {"slot": 7, "id": "390", "qualifiedId": "(O)390", "name": "Stone", "stack": 3, "isTool": False},
        {"slot": 8, "id": "771", "qualifiedId": "(O)771", "name": "Fiber", "stack": 10, "isTool": False},
    ]
    FARM = {"loaded": True, "complete": True, "emptyDirt": 40, "hoeDirt": 0, "crops": 0}

    def _world(self, *, money=14, seeds=0, farm="default", inventory=None):
        if inventory is None:
            inventory = [{"slot": 5, "id": "472", "qualifiedId": "(O)472",
                          "name": "Parsnip Seeds", "stack": seeds, "isTool": False}] + self.MATERIALS
        w = MiniWorld(records=[], tillable=[], money=money, inventory=inventory)
        w.farm = dict(self.FARM) if farm == "default" else farm
        return w

    def test_three_gates_decide_whether_to_sell(self):
        """门闸三条同时成立才卖：钱 < 5×seed_price、种子 0、空耕地 > 0（且证据可信）。"""
        w = self._world()
        self.assertTrue(surplus_sell_plan(w.obs())["gate"])
        for kw, why in (({"money": 500}, "钱够（>=100g）"),
                        ({"seeds": 5}, "还有种子"),
                        ({"farm": {"loaded": True, "complete": True, "emptyDirt": 0}}, "没有空地"),
                        ({"farm": {"loaded": True, "complete": True}}, "Mod 没给 emptyDirt"),
                        ({"farm": None}, "farm 证据不可用")):
            plan = surplus_sell_plan(self._world(**kw).obs())
            self.assertFalse(plan["gate"], why)
            self.assertFalse(plan["should"], why)
            self.assertEqual(plan["slots"], [], why)

    def test_sells_only_the_excess_above_keep(self):
        """每 id 留够 K=10：**整叠**出货 ⇒ 只有"卖掉这叠后仍 >=K"的叠才进名单。

        Wood 共 30（25 + 5 两叠）⇒ 卖 5 那叠、留 25；Stone 3、Fiber 恰好 10 一件不动。
        """
        inv = [
            {"slot": 6, "id": "388", "qualifiedId": "(O)388", "name": "Wood", "stack": 25, "isTool": False},
            {"slot": 7, "id": "388", "qualifiedId": "(O)388", "name": "Wood", "stack": 5, "isTool": False},
            {"slot": 8, "id": "390", "qualifiedId": "(O)390", "name": "Stone", "stack": 3, "isTool": False},
            {"slot": 9, "id": "771", "qualifiedId": "(O)771", "name": "Fiber", "stack": 10, "isTool": False},
        ]
        plan = surplus_sell_plan(self._world(inventory=inv).obs())
        self.assertTrue(plan["should"])
        self.assertEqual(plan["slots"], [7])
        self.assertEqual(plan["whitelist"], ["(O)388"])
        self.assertFalse(plan["belowKeep"])
        by_id = {i["id"]: i for i in plan["items"]}
        self.assertEqual((by_id["(O)388"]["total"], by_id["(O)388"]["sell"],
                          by_id["(O)388"]["left"]), (30, 5, 25))
        self.assertEqual(by_id["(O)390"]["sell"], 0)
        self.assertEqual((by_id["(O)771"]["total"], by_id["(O)771"]["sell"]), (10, 0))
        self.assertEqual(plan["trigger"], {"money": 14, "seeds": 0, "emptyDirt": 40,
                                           "emptyDirtStatus": "ok", "seedPrice": 20,
                                           "threshold": 100, "keep": 10})

    def test_never_offers_tools_seeds_crops_or_artisan_goods(self):
        """fail-closed：材料 id 表外的一律不卖（工具/种子/作物/工匠品）。

        账本 `items` 只列**材料表里出现过的 id**；工具/种子/作物/工匠品连条目都不该有。
        """
        inv = [
            {"slot": 0, "id": "Axe", "qualifiedId": "(T)Axe", "name": "Axe", "stack": 1, "isTool": True},
            {"slot": 4, "id": "47", "qualifiedId": "(W)47", "name": "Scythe", "stack": 1, "isTool": True},
            {"slot": 5, "id": "472", "qualifiedId": "(O)472", "name": "Parsnip Seeds",
             "stack": 0, "isTool": False},
            {"slot": 6, "id": "24", "qualifiedId": "(O)24", "name": "Parsnip", "stack": 50, "isTool": False},
            {"slot": 7, "id": "348", "qualifiedId": "(O)348", "name": "Wine", "stack": 60, "isTool": False},
            {"slot": 8, "id": "390", "qualifiedId": "(O)390", "name": "Stone", "stack": 99, "isTool": False},
        ]
        plan = surplus_sell_plan(self._world(inventory=inv).obs())
        self.assertTrue(plan["gate"])
        # 只有材料表里的 Stone 能卖；99-99=0 < K ⇒ 走"唯一一大叠"的如实标记路径
        self.assertEqual(plan["whitelist"], ["(O)390"])
        self.assertEqual(plan["slots"], [8])
        self.assertTrue(plan["belowKeep"])
        self.assertEqual({i["id"] for i in plan["items"]}, {"(O)390"})
        for foreign in ("(O)24", "(O)348", "(O)472", "(T)Axe", "(W)47"):
            self.assertNotIn(foreign, plan["whitelist"], foreign)
            self.assertNotIn(foreign, [i["id"] for i in plan["items"]], foreign)

    def test_lone_oversized_stack_is_flagged_not_silently_kept(self):
        """整叠出货没有"卖一部分"的能力：唯一一大叠（> K）要么卖、要么永远换不到种子钱。

        这里钉死选"卖"并把"卖完低于 K"如实标进账本 —— 而不是悄悄留着不卖（run7 里那 5 次
        `seed_gate {seeds:0, money:14}` 就是这么来的）。
        """
        inv = [{"slot": 6, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
                "stack": 200, "isTool": False}]
        plan = surplus_sell_plan(self._world(inventory=inv).obs())
        self.assertEqual(plan["slots"], [6])
        self.assertTrue(plan["belowKeep"])
        self.assertEqual(plan["items"][0]["left"], 0)
        self.assertTrue(plan["items"][0]["keptBelowKeep"])
        # 小叠（< K）不动：12 件分成 4+4+4 ⇒ 没有任何一叠大到值得破坏保留线
        small = [{"slot": 6, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
                  "stack": 4, "isTool": False},
                 {"slot": 7, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
                  "stack": 4, "isTool": False},
                 {"slot": 8, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
                  "stack": 4, "isTool": False}]
        plan2 = surplus_sell_plan(self._world(inventory=small).obs())
        self.assertEqual(plan2["should"], False)
        self.assertEqual(plan2["slots"], [])
        self.assertFalse(plan2["belowKeep"])

    def test_keep_line_is_respected_when_a_small_stack_can_be_sold(self):
        """多叠时优先卖**大叠**、但绝不跌破 K（Stone 190+10 ⇒ 卖 190、留 10 == K）。"""
        inv = [{"slot": 6, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
                "stack": 190, "isTool": False},
               {"slot": 7, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
                "stack": 10, "isTool": False}]
        plan = surplus_sell_plan(self._world(inventory=inv).obs())
        self.assertEqual(plan["slots"], [6])
        self.assertFalse(plan["belowKeep"])
        by_id = {i["id"]: i for i in plan["items"]}
        self.assertEqual((by_id["(O)390"]["total"], by_id["(O)390"]["sell"],
                          by_id["(O)390"]["left"]), (200, 190, 10))
        # 反过来：只有小叠能卖（25 + 5 两叠）⇒ 卖 5、留 25（保住 K 且尽量少动材料）
        inv2 = [{"slot": 6, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
                 "stack": 25, "isTool": False},
                {"slot": 7, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
                 "stack": 5, "isTool": False}]
        plan2 = surplus_sell_plan(self._world(inventory=inv2).obs())
        self.assertEqual(plan2["slots"], [7])
        self.assertFalse(plan2["belowKeep"])

    def test_farm_empty_dirt_requires_trustworthy_evidence(self):
        """`farm_empty_dirt` 三态：可信才给数，不可信一律 `unavailable`（绝不当成 0）。"""
        w = MiniWorld(records=[], tillable=[])
        w.farm = {"loaded": True, "complete": True, "emptyDirt": 7}
        self.assertEqual(farm_empty_dirt(w.obs()), (7, "ok"))
        for bad in ({"loaded": False, "complete": True, "emptyDirt": 7},
                    {"loaded": True, "complete": False, "emptyDirt": 7},
                    {"loaded": True, "complete": True},
                    {"loaded": True, "complete": True, "emptyDirt": "x"},
                    {"loaded": True, "complete": True, "emptyDirt": -3}):
            w.farm = bad
            got = farm_empty_dirt(w.obs())
            if bad.get("emptyDirt") == -3:
                self.assertEqual(got, (0, "ok"), bad)      # 负数归零但口径仍然可信
            else:
                self.assertEqual(got, (0, "unavailable"), bad)

    def test_lone_oversized_stack_is_skipped_when_even_the_floor_cannot_cover_it(self):
        """【Lead m08064 硬要求】唯一一大叠也只有"**真能把钱补到 `seed_price`**"时才卖。

        脑侧看不到售价（`ItemView` 没有 `sellToStorePrice`）⇒ 用 `SURPLUS_MIN_UNIT_PRICE`
        （1g/件）做**最保守下界**：下界都够不上缺口（这里钱 0g、缺口 20g、一大叠 11 件 ⇒ 11g）
        就干脆不动，并把缺口原文写进 `skipReason`（fail-closed：宁可少卖，不做"卖了还是买不起"）。
        反过来，下界够得上时仍照旧整叠卖并标 `belowKeep`（见下一条断言）。
        """
        tiny = [{"slot": 6, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
                 "stack": 11, "isTool": False}]
        plan = surplus_sell_plan(self._world(money=0, inventory=tiny).obs())
        self.assertTrue(plan["gate"])
        self.assertFalse(plan["should"])
        self.assertFalse(plan["belowKeep"])
        self.assertEqual(plan["slots"], [])
        self.assertEqual(plan["short"], 20)
        self.assertIn("补不上", plan["skipReason"])
        self.assertIn("缺口 20g", plan["skipReason"])
        # 够得上：同样钱 0g、一大叠 30 件 ⇒ 30g >= 20g ⇒ 卖
        enough = [{"slot": 6, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
                   "stack": 30, "isTool": False}]
        plan2 = surplus_sell_plan(self._world(money=0, inventory=enough).obs())
        self.assertTrue(plan2["should"])
        self.assertEqual(plan2["slots"], [6])
        self.assertTrue(plan2["belowKeep"])
        self.assertEqual(plan2["skipReason"], "")

    def test_seed_like_names_are_structurally_kept_out_of_the_whitelist(self):
        """【Lead m08064 硬要求】白名单必须**结构性**排除种子：id 表 + 名字双保险。

        两道闸门是同一个判据的两侧：`surplus_sell_plan` 只认材料 id 表，且名字带
        seed/种子 的叠**既不算材料、又会被 `seed_items()` 当成种子** ⇒ 只要背包里出现
        种子（或名字像种子的东西），门闸里的 `seeds_total == 0` 当场不成立、整条卖货路径
        直接关掉。这里把这两种形态都钉死：种子 id 472、材料 id 却起名 "Stone Seeds"。
        `isTool=True` 的材料 id 同样永远不进白名单（工具不卖）。
        """
        # ① 种子 id（哪怕 stack 99）⇒ 门闸关闭（seeds_total=99）、一件不卖
        with_seed = self._world(inventory=[
            {"slot": 5, "id": "472", "qualifiedId": "(O)472", "name": "Parsnip Seeds",
             "stack": 99, "isTool": False}])
        plan = surplus_sell_plan(with_seed.obs())
        self.assertFalse(plan["gate"])
        self.assertFalse(plan["should"])
        self.assertEqual(plan["slots"], [])
        self.assertEqual(plan["whitelist"], [])
        # ② 名字像种子的材料 id（"Stone Seeds" + (O)390）⇒ 同样按种子计数 ⇒ 门闸关闭
        fake = self._world(inventory=[
            {"slot": 6, "id": "390", "qualifiedId": "(O)390", "name": "Stone Seeds",
             "stack": 99, "isTool": False}])
        plan2 = surplus_sell_plan(fake.obs())
        self.assertFalse(plan2["gate"])
        self.assertEqual(plan2["slots"], [])
        self.assertEqual([i["id"] for i in plan2["items"]], [])
        # ③ 只有真材料才算：工具（isTool=True，id 388）+ Stone 99 ⇒ 白名单只有 Stone
        mixed = self._world(inventory=[
            {"slot": 5, "id": "388", "qualifiedId": "(O)388", "name": "Wood",
             "stack": 99, "isTool": True},
            {"slot": 8, "id": "390", "qualifiedId": "(O)390", "name": "Stone",
             "stack": 99, "isTool": False}])
        plan3 = surplus_sell_plan(mixed.obs())
        self.assertTrue(plan3["gate"])
        self.assertEqual(plan3["whitelist"], ["(O)390"])
        self.assertEqual(plan3["slots"], [8])
        self.assertEqual({i["id"] for i in plan3["items"]}, {"(O)390"})

    def test_material_id_table_is_documented_and_small(self):
        """白名单表必须是"已知资源 id"的小表（防止有人顺手加个通配规则把种子也算进去）。"""
        self.assertIn("390", SURPLUS_MATERIAL_IDS)
        self.assertIn("388", SURPLUS_MATERIAL_IDS)
        self.assertNotIn("472", SURPLUS_MATERIAL_IDS)     # 防风草种子
        self.assertNotIn("24", SURPLUS_MATERIAL_IDS)      # 防风草（作物）


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
