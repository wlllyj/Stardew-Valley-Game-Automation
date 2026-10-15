# -*- coding: utf-8 -*-
"""长跑控制器（`brain\\agentfarm\\longrun.py`）的离线单元测试。

原则与前几份一样：**不连游戏、不联网、不睡觉** —— 假桥 + 假执行层 + 假时钟。
而且这里更进一步：`FakeWorld` 是一个**真会变**的微型农场（清障/锄地/播种/浇水/买种子/
补水/睡觉都会改世界，观测也真的反映变化），所以长跑控制器能被端到端地跑完一整天甚至三天，
断言的正是"世界有没有真的被改"。

覆盖点（对应"无人值守 3 天"最怕的几件事）：
  1. 决策的**输入必须限定在作业区**（否则永远停在清障）—— `plot_observe` / `_plot_brief`；
  2. 作物格在 `tiles[]` 里 kind 也是 dirt，**不能把作物算两遍**（否则 `unprepared` 提前归零 → stuck）；
  3. "没种子又买不起"时**不许再锄新地**（纯烧体力），而且守卫与策略必须同口径；
  4. **没事就睡**要被否决（用户 2026-10-11 的明确要求）；
  5. 一整天只有在"我们主动睡 + 0 硬失败 + 作物全浇过"时才算 VERIFIED，被系统 pass-out 不算；
  6. 连续 N 天达标才返回 0；起不来返回 2；watchdog 判 STOP 时落事故报告并停。

运行：`python -m unittest discover -s tests -v`
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import MOD_VERSION_EXPECTED, BridgeError  # noqa: E402
from agentfarm.llm import LlmError  # noqa: E402
from agentfarm.farmwork import (  # noqa: E402
    MAX_CLEAR_SWINGS, FarmWorker, STAGE_ACTION, StepResult, StageResult, seed_items,
)
from agentfarm.longrun import (  # noqa: E402
    DEFAULT_LLM_MAX_TOKENS, ENDED_BY_EVENT, ENDED_BY_MODAL, FRONTIER_CLEAR_MAX,
    JUSTIFIED_END_REASONS, MAX_BUY_TRIES_PER_DAY, MAX_ENV_ATTEMPTS, MAX_STUCK_FLUSH,
    MAX_TILE_ATTEMPTS, DayReport, LongRun, _till_blocked_by, is_justified_end, plot_observe,
)
from agentfarm.planner import BoundaryPlanner, Brief, TaskIntent, deterministic_plan  # noqa: E402

SEED_ID = "472"
SEED_NAME = "Parsnip Seeds"

#: 【task-99 ② / NIT-6】`None` = **证据不可用**（等价于 `{}`：桥没给 farm 块）。
#: task-96 曾经把 `None` 解释成"按世界状态自动生成 `farm_scan()`" ⇒ 任何用 `None` 表示
#: "证据不可用"的用例/探针会**静默变成"证据可用"**（deputy 的 C6d/C8c 就是这样看着像修好了）。
#: 现在要"世界一致的真实扫描"必须**显式**写 `w.farm = w.farm_scan()`。
_EMPTY_FARM_SCAN = {
    "loaded": True, "complete": True,
    "crops": 0, "ripeCrops": 0, "deadCrops": 0,
    "dryCrops": 0, "dryDeadCrops": 0,
    "dryTiles": [], "dryTilesTruncated": False,
    "unwateredCrops": 0, "hoeDirt": 0, "emptyDirt": 0,
}


# --------------------------------------------------------------------------- 假世界
class FakeWorld:
    """25 格微型农场（60..64 × 10..14）：技能真的改它，`obs()` 真的反映它。"""

    STAMINA_COST = {"clear": 2.0, "till": 5.0, "plant": 1.0, "water": 1.0, "harvest": 1.0}

    def __init__(self, *, seeds: int = 10, money: int = 500, weeds: int = 4,
                 water_left: int = 40, stamina: float = 270.0, scythe: bool = False) -> None:
        self.year, self.season, self.day, self.time_of_day = 1, "spring", 6, 600
        self.stamina, self.max_stamina = stamina, 270.0
        self.money = money
        self.water_left = water_left
        self.tillable = {(60 + x, 10 + y) for x in range(5) for y in range(5)}
        self.blockers: dict[tuple[int, int], str] = {}
        for t in sorted(self.tillable)[:weeds]:
            self.blockers[t] = "weed"
        self.dirt: set[tuple[int, int]] = set()
        self.crops: dict[tuple[int, int], dict[str, bool]] = {}
        self.player_tile = [62, 14]
        self.is_in_bed = True
        #: 当前地点名 —— `FarmWorker.ensure_location/sleep` 会读它（task-15 让真 `FarmWorker`
        #: 也能在假世界里睡下去）。
        self.location = "Farm"
        #: task-19：`location.isOutdoorFarm`（浇水证据要区分室内/户外快照）与 `farm` 块
        #: （`FarmView` 的字段）。
        self.is_outdoor_farm = True
        #: 【task-96 / task-99 ②】`farm` 块（`FarmView` 字段）。默认 = **「桥在线、扫描完整、
        #: 农场级无事可报」的空计数块** —— 真机 0.7.27 的桥每张快照都会发 `farm`
        #: （`complete=true`），脑侧的 fail-closed 判据（人在农场 + 证据不可用 ⇒ 不许收工）
        #: 因此不该在"普通日"用例里触发。
        #: **`None` = 证据不可用**（等价 `{}`，NIT-6：不许再被解释成"自动扫描"）；
        #: 想测**证据不可用**就显式赋 `None` / `{}` / `{"complete": False}` / `{"loaded": False}`；
        #: 想要一份**与世界状态一致**的真实扫描必须显式调 `self.farm_scan()`。
        self.farm: dict | None = _EMPTY_FARM_SCAN
        self.seq = 1
        self.sleeps = 0
        self.refills = 0
        self.buys: list[int] = []
        # ---- task-67：买种子的货架（`availableItems`）----
        #: 空 = 旧桥（脑走"拿配置项探一次"的老路，与改动前行为一致）；非空 = 回执带货架清单。
        self.buy_offers: list[dict] = []
        self.buy_calls: list[dict] = []      # 每一次 `buy` 请求的 item/count（证明不再硬编码 472）
        self.buy_price = 20                  # 配置项（默认 472）的单价
        #: 【task-102】非空 = 每一次 `buy` 都回这个 Mod status（复刻 run8 day 12/13 的
        #: `no_inventory_space`：钱够、种子在售、背包 0 空格）。
        self.buy_fail_status: str = ""
        #: 【task-102】背包容量（`player.inventoryCount`）；占格 = `len(inventory)` ⇒ 空格 = 差。
        self.inventory_capacity = 12
        # 睡前那一刻"还有几格没浇" —— 跨日会把 watered 全部清零（世界语义），
        # 所以"这天有没有浇完"只能在睡前问，事后问必然为假。
        self.unwatered_at_sleep: list[int] = []
        # task-4：`use_tool` 的计数与"白挥"集合（真机 run1：镰刀在背包里、挥了世界不变）。
        self.swings: dict[tuple[int, int], int] = {}
        self.stuck: set[tuple[int, int]] = set()
        #: task-22：环境挡路 / 没结论的注入队列（见 `take_fail_status`）。
        self.fail_status: dict[tuple[int, int], str | list[str]] = {}
        # ---- task-11：模态脚本（mode guard）----
        #: 依次出现的 `ui` 片段；队首就是"现在挡路的模态"，`dismiss()` 关掉它就露下一个。
        #: 片段里以 `_` 开头的键是脚本元数据（`_autoGoneAfterPolls`），不发给脑。
        self.ui_script: list[dict] = []
        self.dismiss_calls = 0
        self.dismissed: list[str] = []
        self.modal_polls = 0
        self.scythe = scythe
        self.inventory = [
            {"slot": 0, "id": "Axe", "qualifiedId": "(T)Axe", "name": "Axe", "stack": 1, "isTool": True},
            {"slot": 1, "id": "Hoe", "qualifiedId": "(T)Hoe", "name": "Hoe", "stack": 1, "isTool": True},
            {"slot": 2, "id": "WateringCan", "qualifiedId": "(T)WateringCan",
             "name": "Watering Can", "stack": 1, "isTool": True},
            {"slot": 5, "id": SEED_ID, "qualifiedId": f"(O){SEED_ID}",
             "name": SEED_NAME, "stack": seeds, "isTool": False},
        ]
        if scythe:
            # 真机快照口径（`logs\\observe-farm-sample.json`）：镰刀 id "47" 在背包 slot4。
            self.inventory.insert(3, {"slot": 4, "id": "47", "qualifiedId": "(W)47",
                                      "name": "Scythe", "stack": 1, "isTool": True})

    # ---- 观测 ----
    def obs(self) -> dict:
        tiles: list[dict] = []
        for t, kind in sorted(self.blockers.items()):
            tiles.append({"tile": list(t), "kind": kind, "standable": True, "actionable": True})
        for t in sorted(self.dirt):
            tv: dict = {"tile": list(t), "kind": "dirt", "feature": "HoeDirt",
                        "standable": True, "actionable": True}
            c = self.crops.get(t)
            if c:
                tv.update({"crop": "24", "ripe": bool(c["ripe"]), "watered": bool(c["watered"]),
                           "dead": bool(c.get("dead")), "plantable": False})
            else:
                tv.update({"plantable": True, "watered": False})
            tiles.append(tv)
        free = sorted(self.tillable - self.dirt - set(self.blockers))
        return {
            "ok": True, "status": "ok", "schema": "agentfarm-world/6",
            "worldSeq": self.seq, "hasSaveLoaded": True,
            "clock": {"year": self.year, "season": self.season, "day": self.day,
                      "timeOfDay": self.time_of_day, "weather": "sunny", "weatherOnFarm": "sunny"},
            "player": {"name": "测试员", "location": self.location, "tile": list(self.player_tile), "facing": 2,
                       "stamina": self.stamina, "maxStamina": self.max_stamina, "money": self.money,
                       "isInBed": self.is_in_bed, "inventory": [dict(i) for i in self.inventory],
                       # 【task-102】`inventoryCount` = 背包**容量**（真机 `WorldSnapshot.cs:260`
                       # 读 `p.Items.Count`）；空格 = `inventoryCount - len(inventory)`。
                       "inventoryCount": self.inventory_capacity,
                       "wateringCan": {"present": True, "waterLeft": self.water_left,
                                       "max": 40, "bottomless": False, "upgradeLevel": 0}},
            "location": {"name": self.location, "isOutdoorFarm": self.is_outdoor_farm, "tiles": tiles,
                         "tilesTruncated": False,
                         "tillable": [list(t) for t in free], "refillTiles": [[70, 10], [70, 11]],
                         "refillTilesTruncated": False, "furniture": [], "doors": []},
            # task-19：真机观测里 `farm` 永远存在（未加载时 loaded=false/complete=true/全 0）。
            # 【task-96 / task-99 ②】默认 `_EMPTY_FARM_SCAN`（桥在线、扫描完整、农场级无事可报）；
            # 显式赋值（含 `{}` / `complete=false` / `loaded=false`）原样发出；
            # **`None` = 证据不可用 ⇒ 发 `{}`**（NIT-6：task-96 曾把它当"自动 farm_scan()"，
            # 会让用 `None` 表示"不可用"的用例/探针静默变绿）；要世界一致的扫描必须显式
            # `self.farm = self.farm_scan()`。
            "farm": {} if self.farm is None else dict(self.farm),
            "ui": self.current_ui(),
            "liveness": {"worldAdvancing": True, "secondsSinceClockMoved": 1.0},
        }

    # ---- 技能（真的改世界）----
    def spend(self, action: str) -> None:
        self.stamina -= self.STAMINA_COST[action]

    def farm_scan(self) -> dict:
        """【task-96】按世界状态生成一份**良构**的 `farm` 扫描（模拟 0.7.27 真桥）。

        默认**不用**它（默认是 `_EMPTY_FARM_SCAN`，见类属性的注释）：把世界真实计数喂给脑
        会让"普通日"用例的决策路径变化（`planner.Brief.from_observe` 在局部观测没有
        `tiles` 时会退回 farm 计数，见 `planner.py:541-549`），所以只有**明确要世界一致
        扫描**的用例才调它（`w.farm = w.farm_scan()`）。
        口径与 Mod `FarmScan` 一致：
        - `crops`/`hoeDirt`/`ripeCrops`/`dryCrops`/`dryTiles` **只算活苗**（`crop != null && !dead`）；
        - 死苗进 `deadCrops`；"死苗且没浇"进 `dryDeadCrops`；
        - `emptyDirt` = 有耕地但没作物的格数。
        为什么默认要给良构块：fail-closed（task-96 ①②）要求"人在农场 + 证据不可用"不许收工，
        而真机 0.7.27 的桥永远会发 `farm`；旧默认"永远没有 farm 块"会把每个普通日用例
        变成"证据不可用"，与真机不符（21 条普通日用例因此红过）。
        """
        crops = ripe = dry = dead = dry_dead = 0
        dry_tiles: list[list[int]] = []
        for t, c in self.crops.items():
            crops += 1
            if c.get("dead"):
                dead += 1
                if not c.get("watered"):
                    dry_dead += 1
                continue
            if c.get("ripe"):
                ripe += 1
            if not c.get("watered"):
                dry += 1
                dry_tiles.append([int(t[0]), int(t[1])])
        return {
            "loaded": True, "complete": True,
            "crops": crops, "ripeCrops": ripe, "deadCrops": dead,
            "dryCrops": dry, "dryDeadCrops": dry_dead,
            "dryTiles": sorted(dry_tiles), "dryTilesTruncated": False,
            "unwateredCrops": crops, "hoeDirt": len(self.dirt),
            "emptyDirt": len(self.dirt - set(self.crops)),
        }

    # ---- task-22：注入"环境挡路 / 没结论"的假回执 ----
    #: `{格: status}`：该格**每次都**回这个 status（用于"持续没结论"这类用例）。
    #: `{格: [status, ...]}`：按顺序发出去，发完即删（后面的请求恢复正常）。
    #: 真桥对 `ok=false` 是**抛** `BridgeError`，所以由 `FakeClient.use_tool` 抛，脑侧必须按
    #: `exc.status` 分类打标；`world_fading`/`no_save`/`ui_modal` 算环境挡路，`timeout`/`error`
    #: 算"没拿到结论"。默认为空 ⇒ 不影响任何既有用例。
    def take_fail_status(self, tile: tuple[int, int]) -> str:
        v = self.fail_status.get(tuple(tile))
        if not v:
            return ""
        if isinstance(v, str):
            return v
        status = v.pop(0)
        if not v:
            self.fail_status.pop(tuple(tile), None)
        return status

    # ---- task-11：模态脚本（模态守卫用）----
    def current_ui(self) -> dict:
        """当前挡路的 `ui` 片段（脚本队首），没有脚本就是干净世界。

        `_autoGoneAfterPolls=N` = 这个模态**在玩家第 N 次看它之后自己消失**（第 N+1 次观察就看不到了），
        用来复刻真机 `SaveGameMenu` 那种"只等不关、约 30s 自己走完"的行为。以 `_` 开头的键
        是脚本元数据，不会发给脑。
        """
        if not self.ui_script:
            return {"isModal": False, "eventUp": False}
        head = self.ui_script[0]
        auto = head.get("_autoGoneAfterPolls")
        if auto is not None and self.modal_polls >= int(auto):
            self.ui_script.pop(0)
            self.modal_polls = 0
            return self.current_ui()
        self.modal_polls += 1
        ui = {k: v for k, v in head.items() if not k.startswith("_")}
        ui.setdefault("isModal", True)
        ui.setdefault("eventUp", False)
        return ui

    def dismiss(self) -> dict:
        """`dismiss_modal` 的假世界版：关掉队首模态（露出下一个）并如实返回回执。"""
        self.dismiss_calls += 1
        name = ""
        if self.ui_script:
            name = str(self.ui_script[0].get("activeMenu") or "")
            self.ui_script.pop(0)
        self.modal_polls = 0
        self.dismissed.append(name)
        return {"ok": True, "status": "ok", "worldResumed": True, "worldSeq": self.seq}

    def clear(self, tile):
        kind = self.blockers.get(tile)
        if kind is None:
            return StepResult("clear", tile, code="already", reason="本来就没障碍")
        del self.blockers[tile]
        self.spend("clear")
        return StepResult("clear", tile, ok=True, reason=f"清掉 {kind}")

    def clear_dead(self, tile):
        """【task-51】清枯死作物：只删 `dead=true` 的 crop；**活苗绝不动**。"""
        c = self.crops.get(tile)
        if c is None:
            return StepResult("clear_dead", tile, code="already", reason="这格没有作物")
        if not c.get("dead"):
            return StepResult("clear_dead", tile, code="skipped",
                              reason="这一格是活苗 —— 清死苗动作绝不碰它")
        del self.crops[tile]
        self.spend("clear")
        return StepResult("clear_dead", tile, ok=True, reason="清掉这一格的枯死作物")

    def use_tool(self, tile, tool=None):
        """`use_tool` 的假世界版（与 Mod 同口径：**成功=这一格真的变了**，回执不算数）。

        `stuck` 里的格子模拟真机 run1 的镰刀白挥：回执 `status="tool_ineffective"`、
        世界一动不动。`swings` 记每格被挥了几次 —— task-4 的验收证据就在这里。

        task-15 起**按工具真的改世界**：真 `FarmWorker.till/water` 走的是 `client.use_tool`
        （不是 `FakeWorker` 的 `w.till/w.water`）；如果这里只删 `blockers`，环境重试的第 2 轮
        就会落成"非环境失败"并占配额、还会被 `_mark_blocked` 封格（实测假红）。
        """
        t = tuple(tile)
        self.swings[t] = self.swings.get(t, 0) + 1
        if t in self.stuck:
            return {"ok": True, "status": "tool_ineffective", "reason": f"工具对 {t} 无效"}
        _c = self.crops.get(t)
        if _c is not None and _c.get("dead") and tool in (None, "scythe", "hoe"):
            # 【task-51】枯死作物：真机 `destroyCrop(true)`（镰刀/锄头，IL 见
            # `scratch\il-dead-hoedirt.txt`）⇒ **crop 消失、耕地留下**（`dirt` 不动）。
            del self.crops[t]
            self.spend("clear")
            return {"ok": True, "status": "ok", "reason": "清掉这一格的枯死作物"}
        if tool == "hoe":                                  # 镜像 `till()`
            if t in self.dirt:
                return {"ok": True, "status": "ok", "reason": "已经是耕地"}
            if t not in self.tillable or t in self.blockers:
                return {"ok": True, "status": "tool_ineffective", "reason": f"{t} 现在锄不了"}
            self.dirt.add(t)
            self.spend("till")
            return {"ok": True, "status": "ok", "reason": "锄成耕地"}
        if tool == "can":                                  # 镜像 `water()`
            c = self.crops.get(t)
            if c is None:
                return {"ok": True, "status": "tool_ineffective", "reason": f"{t} 没有作物"}
            if c["watered"]:
                return {"ok": True, "status": "ok", "reason": "已经浇过"}
            if self.water_left <= 0:
                return {"ok": False, "status": "need_refill", "reason": "水壶空了"}
            c["watered"] = True
            self.water_left -= 1
            self.spend("water")
            return {"ok": True, "status": "ok", "reason": "浇过"}
        if self.blockers.pop(t, None) is None:
            return {"ok": True, "status": "ok", "reason": "挥了，但这格本来就没东西"}
        self.spend("clear")
        return {"ok": True, "status": "ok", "reason": "清掉"}

    def till(self, tile):
        if tile in self.dirt:
            return StepResult("till", tile, code="already", reason="已经是耕地")
        if tile not in self.tillable or tile in self.blockers:
            return StepResult("till", tile, code="skipped", reason="这格不能锄")
        self.dirt.add(tile)
        self.spend("till")
        return StepResult("till", tile, ok=True, reason="锄成耕地")

    def plant(self, tile):
        if self.crops.get(tile):
            return StepResult("plant", tile, code="already", reason="已经有作物")
        slot = self._seed_slot()
        if slot is None:
            return StepResult("plant", tile, code="no_seed", reason=f"没种子了（item {SEED_ID} 堆叠 0）")
        slot["stack"] -= 1
        self.crops[tile] = {"watered": False, "ripe": False}
        self.spend("plant")
        return StepResult("plant", tile, ok=True, reason="种下")

    def water(self, tile):
        c = self.crops.get(tile)
        if c is None:
            return StepResult("water", tile, code="skipped", reason="这格没作物")
        if c["watered"]:
            return StepResult("water", tile, code="already", reason="已经浇过")
        if self.water_left <= 0:
            return StepResult("water", tile, code="need_refill", reason="水壶空了（0），得先去补水")
        c["watered"] = True
        self.water_left -= 1
        self.spend("water")
        return StepResult("water", tile, ok=True, reason="浇过")

    def sow(self, tile):
        """播种 + 立刻浇这一格（`farmwork.sow` 的假世界版，语义与生产代码对齐）。"""
        pr = self.plant(tile)
        if not pr.ok:
            return pr
        wr = self.water(tile)
        if wr.ok:
            pr.reason = f"{pr.reason}；紧接着浇水：{wr.reason}"
            return pr
        pr.ok = False
        pr.code = "need_refill" if wr.code == "need_refill" else "failed"
        pr.reason = f"{pr.reason}；但浇水没成：{wr.reason}"
        return pr

    def harvest(self, tile):
        c = self.crops.get(tile)
        if not c or not c["ripe"]:
            return StepResult("harvest", tile, code="skipped", reason="还没熟")
        del self.crops[tile]
        return StepResult("harvest", tile, ok=True, reason="收了")

    def refill(self):
        self.water_left = 40
        self.refills += 1
        return StepResult("refill_can", ok=True, reason="补到 40")

    def sleep(self):
        self.sleeps += 1
        self.unwatered_at_sleep.append(sum(1 for c in self.crops.values() if not c["watered"]))
        self.day += 1
        self.time_of_day = 600
        self.stamina = self.max_stamina
        for c in self.crops.values():
            c["watered"] = False
        return StepResult("sleep", ok=True, reason=f"跨到第 {self.day} 天")

    def buy(self, item, count, shop):
        # 【task-67】回执带回来的货架清单（空 = 旧桥/探路模式，行为与改动前完全一致）。
        # 记下**每一次请求的 item**：`TestTask67SeedChoice` 就是靠它证明"不再硬编码 472"。
        self.buy_calls.append({"item": str(item), "count": int(count)})
        price = self.buy_price
        offers = [dict(o) for o in self.buy_offers]
        if self.buy_fail_status:
            # 【task-102】背包含量卡死等 Mod 侧的失败码：回执带 status + 在售清单。
            return StepResult("buy", code="failed", status=self.buy_fail_status,
                              reason=f"没成交（Mod status={self.buy_fail_status}）",
                              available=offers)
        if offers:
            want = "".join(ch for ch in str(item) if ch.isdigit())
            on_shelf = any(want and want == "".join(ch for ch in str(o.get("id") or "") if ch.isdigit())
                           for o in offers)
            if not on_shelf:
                # 真机在这里回 `item_not_sold` + 在售清单（脑必须照清单换一个 id 重挑）
                return StepResult("buy", code="failed", status="item_not_sold",
                                  reason=f"商店「{shop}」里没有「{item}」",
                                  available=offers)
        can = min(int(count), self.money // price)
        if can < 1:
            return StepResult("buy", code="failed", reason=f"钱不够（{self.money}g < {price}g）",
                              available=offers)
        self.money -= price * can
        slot = self._seed_slot()
        if slot is None:
            self.inventory.append({"slot": 9, "id": SEED_ID, "qualifiedId": f"(O){SEED_ID}",
                                   "name": SEED_NAME, "stack": can, "isTool": False})
        else:
            slot["stack"] += can
        self.buys.append(can)
        return StepResult("buy", ok=True, reason=f"买到 {can} 个，钱 {self.money}g",
                          available=offers)

    def _seed_slot(self):
        for it in self.inventory:
            if SEED_ID in (str(it.get("id")), str(it.get("qualifiedId"))) and int(it.get("stack") or 0) > 0:
                return it
        return None


class MyopicWorld(FakeWorld):
    """观测**以玩家为中心**的假世界：离得远的格子根本不在观测里（真机行为）。

    真机证据（`scratch\\obs-full.json`，spring 9 11:10）：151 个可锄格，`tillable[]` 只覆盖
    玩家周围一带，`tiles[]`（上限 400、近处优先）里一个都没有。`revealed=True` 表示"人已经
    走进作业区" —— 这时候传感器才看得见那片地。
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.revealed = False
        self.radius = 3

    def obs(self) -> dict:
        o = super().obs()
        if self.revealed:
            return o
        pt = tuple(self.player_tile)
        loc = o["location"]
        loc["tillable"] = [c for c in loc["tillable"]
                           if abs(c[0] - pt[0]) + abs(c[1] - pt[1]) <= self.radius]
        loc["tiles"] = [t for t in loc["tiles"]
                        if abs(t["tile"][0] - pt[0]) + abs(t["tile"][1] - pt[1]) <= self.radius]
        return o


class FakeClient:
    def __init__(self, world: FakeWorld, *, mod_version: str = MOD_VERSION_EXPECTED) -> None:
        self.w = world
        self.mod_version = mod_version
        self.details: list[str] = []

    def health(self, *, timeout=None):
        return {"ok": True, "status": "ok", "modVersion": self.mod_version,
                "runtime": {"worldSeq": self.w.seq, "hasSaveLoaded": True}}

    def observe(self, detail="summary", *, timeout=None):
        self.details.append(detail)
        return self.w.obs()

    # ---- 供**真的** FarmWorker 直接驱动的两个动作（task-4 端到端复现用）----
    def move_to(self, x, y, *, timeout_ms=None, allow_bed=None):
        self.w.player_tile = [int(x), int(y)]
        if hasattr(self.w, "revealed"):
            self.w.revealed = True
        return {"ok": True, "status": "ok", "tile": [int(x), int(y)]}

    # ---- task-15：真 `FarmWorker.sleep()` 要的三件套（`ensure_location` → 踩床 → `sleep`）----
    def move_to_location(self, name, *, tile=None, timeout_ms=None):
        """换地点名（`FarmWorker.ensure_location` 会**复核观测**里的 `location.name`）。"""
        self.w.location = str(name)
        return {"ok": True, "status": "ok", "location": str(name)}

    def interact(self, tile, *, timeout_ms=None):
        return {"ok": True, "status": "ok", "reason": "假世界：交互不影响跨日"}

    def sleep(self, *, timeout_ms=None):
        """真跨日：世界自己走 `w.sleep()`（day+1、体力回满、watered 清零）。"""
        self.w.sleep()
        return {"ok": True, "status": "ok", "day": self.w.day, "timeOfDay": self.w.time_of_day}

    def use_tool(self, tile, *, tool=None, timeout_ms=None):
        # task-22：真桥对 `ok=false` 是**抛** `BridgeError`（带 status）—— 注入队列复刻这条口径，
        # 逼着脑侧按 `exc.status` 分类（环境挡路 vs 没拿到结论）。
        status = self.w.take_fail_status(tuple(tile))
        if status:
            raise BridgeError(f"假世界注入：这一格这次没做成（{status}）", status=status)
        return self.w.use_tool(tuple(tile), tool)

    # ---- task-11：模态守卫用 ----
    def dismiss_modal(self, *, timeout_ms=5000):
        return self.w.dismiss()

    # ---- 供**真** `FarmWorker.plant`/`sow` 驱动（task-22 的播种/浇水集成用例）----
    def plant(self, seed, tile, *, timeout_ms=None):
        status = self.w.take_fail_status(tuple(tile))
        if status:
            raise BridgeError(f"假世界注入：这一格这次没种下（{status}）", status=status)
        return self.w.plant(tuple(tile))


class FakeWorker:
    """假执行层：把 `run_stage` 直接落到 `FakeWorld` 上（语义与 farmwork 对齐）。"""

    def __init__(self, world: FakeWorld, *, log=print) -> None:
        self.w = world
        self.log = log
        self.steps: list[StepResult] = []
        self.walk_steps = 0

    def snap(self):
        return self.w.obs()

    def run_stage(self, stage, tiles, *, min_stamina=12.0, max_steps=200):
        action = STAGE_ACTION.get(stage, stage)
        res = StageResult(stage=stage, tiles=list(tiles))
        for i, tile in enumerate(tiles):
            if i >= max_steps:
                res.stopped, res.stopped_reason = "budget", f"达到格数上限 {max_steps}"
                break
            if action in ("clear", "clear_dead", "till", "water", "harvest", "sow") and self.w.stamina < min_stamina:
                res.stopped, res.stopped_reason = "stamina", f"体力 {self.w.stamina:g} < {min_stamina:g}"
                break
            st = getattr(self.w, action)(tile)
            self.steps.append(st)
            res.steps.append(st)
            if st.code in ("no_seed", "need_refill"):
                res.stopped, res.stopped_reason = st.code, st.reason
                break
        return res

    def stand_next_to(self, tile, *, timeout_ms=15000):
        self.walk_steps += 1
        # 走到目标格旁边：对"近视世界"来说，这一步之后传感器才看得见那片地
        x, y = tile
        self.w.player_tile = [x, y + 1]
        if hasattr(self.w, "revealed"):
            self.w.revealed = True
        return True

    def move_to(self, tile, *, timeout_ms=15000, **kw):
        self.walk_steps += 1
        self.w.player_tile = [int(tile[0]), int(tile[1])]
        if hasattr(self.w, "revealed"):
            self.w.revealed = True
        return StepResult("move_to", tuple(tile), ok=True, reason="假世界瞬移到位")

    def refill_can(self, *, timeout_ms=15000):
        st = self.w.refill()
        self.steps.append(st)
        return st

    def water(self, tile, *, timeout_ms=15000):
        """task-50：脑侧 `_water_far_dry` 要驱动"走到**观测窗口之外**那一格再浇"。

        真 `FarmWorker.water()` 走 `client.use_tool(tool="can")`；假执行层直接落到
        `FakeWorld.water()`（真改世界），这样"窗口外干格浇没浇成"仍由观测差分证明。
        """
        st = self.w.water(tuple(tile))
        self.steps.append(st)
        return st

    def sleep(self, *, home="FarmHouse", timeout_ms=180000):
        st = self.w.sleep()
        self.steps.append(st)
        return st

    def buy(self, item, count=10, *, shop="SeedShop", timeout_ms=25000):
        st = self.w.buy(item, count, shop)
        self.steps.append(st)
        return st

    def load_save(self, save=None):
        return StepResult("load_save", ok=True, reason="假世界已经在存档里了")

    def ensure_location(self, name, *, tile=None, timeout_ms=30000):
        return StepResult("move_to_location", ok=True, reason=f"假世界已经在 {name}")


class FakePlanner:
    """固定意图的假策略层（用来逼出"边界决策说了不该说的话"这类分支）。"""

    def __init__(self, *intents: TaskIntent) -> None:
        self.intents = list(intents)
        self.calls = 0

    def decide(self, state, brief):
        self.calls += 1
        return SimpleNamespace(boundary="recovery", intents=list(self.intents), source="llm",
                               llm_called=True, problems=[], fallback_reason=None)


def make_run(world: FakeWorld | None = None, **kw) -> LongRun:
    world = world if world is not None else FakeWorld()
    logs: list[str] = []
    params = dict(
        client_factory=lambda: FakeClient(world),
        worker_factory=lambda c: FakeWorker(world),
        target_days=1, plot_size=5, zone_split=2,
        log=logs.append, sleep_fn=lambda _s: None, supervise_every=0,
        # 生产默认是"大模型开着"（用户 m02320），但单测**绝不允许碰网络**：
        # 这里显式关掉，要测 LLM 路径的用例自己注入假 seam 并把 llm_enabled 打开。
        llm_enabled=False,
    )
    params.update(kw)
    run = LongRun(**params)
    run.logs = logs
    return run


class _BoomChat:
    """【task-56】假 LLM seam：每次调用都抛 `LlmError`（**真的调了一次**，但绝不联网）。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, messages, **kwargs):
        self.calls += 1
        raise LlmError("单测假 seam：故意失败（不联网）", status="network")


# --------------------------------------------------------------------------- 测试
class TestPlotObserve(unittest.TestCase):
    def test_clips_to_plot_and_drops_unactionable(self):
        w = FakeWorld(weeds=0)
        obs = w.obs()
        # 塞一棵树进去：它不是"活"（farmwork 会跳过它），不该进局部简报
        obs["location"]["tiles"].append({"tile": [60, 10], "kind": "tree", "standable": False})
        local = plot_observe(obs, [(60, 10), (60, 11)])
        kinds = {tuple(t["tile"]): t["kind"] for t in local["location"]["tiles"]}
        self.assertEqual(kinds, {})                      # 树被丢掉、空格子本来就不在 tiles 里
        self.assertEqual(len(local["location"]["tillable"]), 2)
        self.assertFalse(local["location"]["tilesTruncated"])


class TestSleepGuard(unittest.TestCase):
    def test_vetoes_when_work_remains(self):
        w = FakeWorld(weeds=4, money=100)
        run = make_run(w)
        run.worker = FakeWorker(w)
        allow, code, text = run.sleep_guard(w.obs())
        self.assertFalse(allow)
        self.assertEqual(code, "keep_working")
        self.assertIn("清", text)

    def test_vetoes_when_seeds_runnable_and_money_enough(self):
        w = FakeWorld(weeds=0, seeds=0, money=100)
        run = make_run(w)
        run.worker = FakeWorker(w)
        allow, code, text = run.sleep_guard(w.obs())
        self.assertFalse(allow)
        self.assertIn("买", text)

    def test_allows_no_work(self):
        w = FakeWorld(weeds=0, seeds=0, money=0)
        for t in sorted(w.tillable)[:6]:
            w.dirt.add(t)
            w.crops[t] = {"watered": True, "ripe": False}
        # 剩下的可锄格也锄掉，才算"真的没活"
        for t in sorted(w.tillable):
            w.dirt.add(t)
        run = make_run(w)
        run.worker = FakeWorker(w)
        allow, code, _ = run.sleep_guard(w.obs())
        self.assertTrue(allow)
        self.assertEqual(code, "no_work")

    def test_night_and_stamina(self):
        w = FakeWorld(weeds=0)
        run = make_run(w)
        run.worker = FakeWorker(w)
        w.time_of_day = 2300
        self.assertEqual(run.sleep_guard(w.obs())[:2], (True, "night"))
        w.time_of_day = 700
        w.stamina = 5.0
        self.assertEqual(run.sleep_guard(w.obs())[:2], (True, "stamina"))


class TestPlotBrief(unittest.TestCase):
    def _plot(self, w, run):
        cands = run._plot_candidates(w.obs())
        self.assertTrue(cands, "假农场应该切得出田区")
        return cands[0]

    def test_does_not_double_count_crop_tiles(self):
        w = FakeWorld(weeds=0, seeds=10, money=500)
        run = make_run(w)
        run.worker = FakeWorker(w)
        plot = self._plot(w, run)
        # 先在这片地里锄 4 格并种下（作物格的 kind 也是 dirt，真机证据一致）
        done = 0
        for t in plot["tiles"]:
            if done >= 4:
                break
            w.dirt.add(t)
            # 浇过水的作物：这样策略不会先被"浇水优先"（用户 m01774 的政策）挡在前面，
            # 这条用例要验的是 dirt 不把作物格算两遍 ⇒ unprepared 仍然 > 0。
            w.crops[t] = {"watered": True, "ripe": False}
            done += 1
        brief = run._plot_brief(w.obs(), plot)
        self.assertEqual(brief.counts["crops"], 4)
        self.assertEqual(brief.counts["dirt"], 0)        # 作物格不算"空地"
        # 目标 = min(可用格, 已种 + 种子)；未开垦 = 目标 - 空地 - 作物 ⇒ 应该 > 0
        self.assertGreater(brief.target_tiles, 4)
        self.assertGreater(brief.unprepared, 0)
        self.assertIn("till_area", [i.task for i in deterministic_plan(brief)])

    def test_broken_when_no_seed_and_no_money(self):
        w = FakeWorld(weeds=0, seeds=0, money=5)
        run = make_run(w)
        run.worker = FakeWorker(w)
        plot = self._plot(w, run)
        for t in plot["tiles"][:3]:
            w.dirt.add(t)
            w.crops[t] = {"watered": True, "ripe": False}
        brief = run._plot_brief(w.obs(), plot)
        self.assertEqual(brief.counts["plantable"], 0)
        self.assertEqual(brief.target_tiles, brief.counts["crops"])
        self.assertNotIn("till_area", [i.task for i in deterministic_plan(brief)])

    def test_plot_work_ignores_tillable_without_affordable_seed(self):
        """守卫与策略同口径：没种子又买不起 ⇒ 可锄格不算"活"（否则一整天耗成 stuck）。"""
        w = FakeWorld(weeds=0, seeds=0, money=5)
        run = make_run(w)
        run.worker = FakeWorker(w)
        plot = run._plot_candidates(w.obs())[0]
        self.assertFalse(run._plot_has_work(w.obs(), plot["tiles"]))
        w.money = 100
        self.assertTrue(run._plot_has_work(w.obs(), plot["tiles"]))

    def test_plot_work_sees_blockers_and_unwatered(self):
        w = FakeWorld(weeds=1, seeds=0, money=0)
        run = make_run(w)
        run.worker = FakeWorker(w)
        self.assertIn("weed", {t["kind"] for t in w.obs()["location"]["tiles"]})
        # 有障碍 ⇒ 是活（清障不花种子）。注意：要按**候选作业区逐个**判 ——
        # 障碍在哪个区由切区算法决定（障碍可能在第一个候选区之外），守卫是逐区问的。
        obs = w.obs()
        self.assertTrue(any(run._plot_has_work(obs, c["tiles"]) for c in run._plot_candidates(obs)))

        w2 = FakeWorld(weeds=0, seeds=0, money=0)
        w2.dirt.add((60, 10))
        w2.crops[(60, 10)] = {"watered": False, "ripe": False}
        run2 = make_run(w2)
        run2.worker = FakeWorker(w2)
        obs2 = w2.obs()
        cands2 = run2._plot_candidates(obs2)
        self.assertTrue(any(run2._plot_has_work(obs2, c["tiles"]) for c in cands2))
        # 那格所在的区必须被认成"有活"（未浇水的作物）
        with_crop = [c for c in cands2 if (60, 10) in {tuple(t) for t in c["tiles"]}]
        self.assertTrue(with_crop, "应该有一个候选区包含那格作物")
        self.assertTrue(all(run2._plot_has_work(obs2, c["tiles"]) for c in with_crop))


class TestOneDay(unittest.TestCase):
    def test_single_day_verified_and_world_changed(self):
        w = FakeWorld(weeds=4, seeds=10, money=500)
        run = make_run(w, target_days=1)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertEqual(len(run.days), 1)
        rep = run.days[0]
        self.assertEqual(rep.ended_by, "sleep")
        self.assertTrue(rep.verified, f"{rep.checks} notes={rep.notes}")
        # 世界真的变了：障碍清光、25 格全种下
        self.assertEqual(w.blockers, {})
        self.assertEqual(len(w.crops), 25)
        self.assertEqual(w.day, 7)
        self.assertEqual(w.sleeps, 1)
        # "这天浇完了"只能在睡前问 —— 跨日会把 watered 清零（第二天要重浇）
        self.assertEqual(w.unwatered_at_sleep, [0])
        self.assertEqual(rep.final["unwatered_crops"], 0)
        self.assertTrue(rep.checks["crops_watered"])
        # 阶段走全了三步：浇水不再单独出现 —— `plant_area` 走 `sow`（种一个立刻浇一个，
        # 用户 m01847），所以"浇过"体现在 `unwatered_at_sleep == [0]` 上（上一行）。
        self.assertEqual(set(rep.stages_seen), {"clear_area", "till_area", "plant_area"})

    def test_water_first_when_crops_are_dry(self):
        """用户 m01774/m01770：每天第一个任务就是浇水（除雨天）。

        昨天种下、今天还没浇的作物 ⇒ 睡觉闸门必须否决，且当天的第一个阶段就是 `water_area`。
        """
        w = FakeWorld(weeds=4, seeds=10, money=500)
        # ⚠️ 干作物必须放在**不是障碍**的格子上：(60,10) 同时是 weed 障碍格，`obs()` 会对同一格
        # 产出两条 tiles 记录（weed + dirt），`Brief.from_observe` 按列表都算（blockers=1）而
        # `tiles_of` 按 dict 只认最后一条（dirt）⇒ 策略一直喊 clear_area 而执行层一格都拿不出来。
        # 假世界的 bug 不该用来考生产代码：换到干净的 (61,10)。
        w.dirt.add((61, 10))
        w.crops[(61, 10)] = {"watered": False, "ripe": False}
        run = make_run(w, target_days=1)
        allow, code, text = run.sleep_guard(w.obs())
        self.assertFalse(allow, f"{code}: {text}")
        self.assertEqual(code, "keep_working")
        self.assertIn("没浇水", text)
        self.assertEqual(run.run(), 0, run.logs)
        # ⚠️ `stages_seen` 是**去重后按字母排序**的集合（给人看的），不是执行顺序 ——
        # "谁先做的"只能看 `rep.stages` 的追加顺序。
        self.assertEqual(run.days[0].stages[0]["stage"], "water_area")
        self.assertEqual(run.days[0].final["unwatered_crops"], 0)

    def test_till_targets_skip_unknown_feature_tiles(self):
        """真机 (73,25) 一带：Mod 的 `tillable[]` 会把"有未知特征"的格也算进来，锄不动。"""
        self.assertIn("未知", _till_blocked_by({"kind": "unknown", "feature": "Stone", "objId": "-1"}))
        self.assertEqual(_till_blocked_by({"kind": "dirt", "feature": "HoeDirt"}), "")
        self.assertEqual(_till_blocked_by(None), "")
        w = FakeWorld(weeds=0, seeds=10, money=500)
        run = make_run(w, target_days=1)
        # 作业区得挑**含 (60,10) 的那一片**：`_plot_candidates` 的第一片是另一区（真机同理）。
        candidates = run._plot_candidates(w.obs())
        plot = next(p for p in candidates
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})
        self.assertIn((60, 10), run._stage_tiles("till_area", w.obs(), plot))
        run.blocked[(60, 10)] = "till 无效：锄完不是 dirt"
        # 封格只免掉**重试**：目标集合里不再出现这一格……
        self.assertNotIn((60, 10), run._stage_tiles("till_area", w.obs(), plot))
        # ……但后置条件复核**必须**看得见它。否则"动了没用"会被从剩余集合里抹掉 ⇒
        # `met=true` ⇒ 硬失败洗成 VERIFIED（task-9：真机 run2 第 1 天就是这么中的招）。
        self.assertIn((60, 10), run._leftover("till_area", w.obs(), plot))

    def test_mark_blocked_records_only_no_effect_groundwork(self):
        """一格最多白试一次；但浇水失败**不封格**（封掉就成了自欺）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        run = make_run(w, target_days=1)
        before = w.obs()
        rep = DayReport(day_key=("spring", 1, 6), started_at=0.0)
        run._mark_blocked(before, w.obs(),
                          [StepResult("till", (60, 10), code="failed", reason="锄完不是 dirt（kind=未知）")],
                          rep)
        self.assertIn((60, 10), run.blocked)
        run.blocked.clear()
        run._mark_blocked(before, w.obs(),
                          [StepResult("water", (61, 10), code="failed", reason="水少了但没浇上")],
                          rep)
        self.assertNotIn((61, 10), run.blocked)

    def test_day_start_asks_llm_then_only_on_boundaries(self):
        """用户 m01860：**一天的第一次决策**要让大模型先判断今天做什么。

        判据：注入的假 seam 调用次数 + 决策事件里的 `boundary`/`source`/`llm`。
        设计上只有三种边界会联网（跨日 / 失败计数上升 / 代码策略阶段切换），
        所以一天是"1 次跨日 + 每次换阶段 1 次"，**不是每个动作都问**。
        """
        w = FakeWorld(weeds=4, seeds=10, money=500)
        calls: list[str] = []

        def fake_chat(messages, **kwargs):
            calls.append("".join(str(m.get("content", "")) for m in messages))
            return json.dumps({"tasks": [
                {"task": "water_area", "area_hint": "tiles.unwatered_crops",
                 "reason": "作物要浇水", "expected_evidence": "unwatered_crops 数量下降"},
                {"task": "clear_area", "area_hint": "field_nw",
                 "reason": "这片田区还有草", "expected_evidence": "blockers 数量下降"},
            ]}, ensure_ascii=False)

        planner = BoundaryPlanner(llm_enabled=True, llm_chat=fake_chat)
        run = make_run(w, target_days=2, planner=planner)
        self.assertEqual(run.run(), 0, run.logs)

        decisions = [e for e in run.entries if e["event"] == "decision"]
        self.assertTrue(decisions)
        # 第一天的第一次决策就是跨日边界，且真的用了大模型
        self.assertEqual(decisions[0]["boundary"], "new_day")
        self.assertEqual(decisions[0]["source"], "llm")
        self.assertTrue(decisions[0]["llm"])
        # 大模型给的意图被原样采纳（含具名田区引用），没有任何一次降级
        self.assertEqual(decisions[0]["intents"][1]["area_hint"], "field_nw")
        self.assertTrue(all(not d["fallback"] for d in decisions),
                        [d["fallback"] for d in decisions if d["fallback"]])
        # 联网次数 = 真调了 LLM 的决策数，且**远少于**决策总数（不是每步都问）
        llm_decisions = [d for d in decisions if d["llm"]]
        self.assertEqual(len(calls), len(llm_decisions))
        self.assertLess(len(calls), len(decisions))
        self.assertTrue(any(not d["llm"] for d in decisions), "常规区间必须一次都不联网")
        # 方向由模型给、坐标由代码落：被点名的田区排在尝试顺序第一位
        run.pending_zone_hint = "field_nw"
        zones = run._zones(w.obs())
        self.assertEqual(run._ordered_zones(zones)[0].name, "field_nw")

    def test_three_days_streak_returns_zero(self):
        w = FakeWorld(weeds=4, seeds=10, money=500, water_left=12)
        run = make_run(w, target_days=3)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertEqual([d.ended_by for d in run.days], ["sleep", "sleep", "sleep"])
        self.assertTrue(all(d.verified for d in run.days), [d.checks for d in run.days])
        # 水壶会空：必须走"补水"这条路（而不是让每一格都 tool_ineffective）
        self.assertGreaterEqual(w.refills, 1)
        self.assertEqual(w.day, 9)

    def test_buys_seeds_when_run_out(self):
        w = FakeWorld(weeds=0, seeds=0, money=100)
        run = make_run(w, target_days=1)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertTrue(w.buys, "没种子时应该去买")
        self.assertGreater(len(w.crops), 0)
        self.assertTrue(any(e["event"] == "buy" for e in run.entries))

    def test_no_buy_flag(self):
        w = FakeWorld(weeds=0, seeds=0, money=100)
        # 真机观测里 `farm` **永远存在**（`FarmScan` 每次扫描都发；未加载时 loaded=false/complete=true/全 0）。
        # 这个假世界一块障碍/耕地都没有 ⇒ `location.tiles` 是空列表；若同时不给 `farm`，这一天就只剩
        # "空窗口"这一条证据，而空窗口已按 task-19 NIT-1 如实判 False ⇒ 会把"本来就没作物可浇"的
        # 合法零工作日误判成 needs_review。补一份真机口径的 farm 快照（0 作物 ⇒ dryCrops=0 ⇒ 浇水证据成立）。
        w.farm = {"loaded": True, "complete": True, "crops": 0, "dryCrops": 0,
                  "unwateredCrops": 0, "hoeDirt": 0}
        run = make_run(w, target_days=1, allow_buy=False)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertEqual(w.buys, [])
        self.assertEqual(w.crops, {})

    def test_pass_out_day_is_not_verified(self):
        """日期自己变了（不是我们睡的）⇒ 这天不算数。"""
        w = FakeWorld(weeds=4, seeds=10, money=500)
        run = make_run(w, target_days=1)

        # 【为什么假的是 worker 而不是 client】生产代码 `LongRun._snap()` 走的是 `self.worker.snap()`
        # （worker 再去问桥），所以测试里装假 worker 时，观测就地产生 —— 在 client 上做手脚根本不会被调用。
        class PassingOutWorker(FakeWorker):
            def __init__(self, world):
                super().__init__(world)
                self.n = 0

            def snap(self):
                obs = super().snap()
                self.n += 1
                # 第 3 次观测 = _prepare 1 次 + _run_day 开头 1 次 + 循环里第 1 次
                if self.n == 3:            # 中途被系统 pass-out（昏倒/强制跨日）
                    self.w.day += 1
                    self.w.time_of_day = 600
                    return self.w.obs()
                return obs

        run.worker_factory = lambda c: PassingOutWorker(w)
        # 用 max_days=1 把长跑限死在"那一天"上：被动跨日 ⇒ 没有一天是我们自己睡过去的 ⇒ 达不了标。
        # （若不限天数，长跑会继续下一天，而那一天是我们正常睡的 ⇒ 仍会返回 0，这是对的。）
        run.max_days = 1
        code = run.run()
        self.assertEqual(code, 1)
        self.assertEqual(run.days[0].ended_by, "pass_out")
        self.assertFalse(run.days[0].verified)
        self.assertEqual(w.unwatered_at_sleep, [], "我们没睡过 —— 这天不能算")

    def test_mod_version_mismatch_refuses_to_run(self):
        w = FakeWorld()
        run = make_run(w, client_factory=lambda: FakeClient(w, mod_version="0.7.20"))
        code = run.run()
        self.assertEqual(code, 2)
        self.assertIn("0.7.20", run.summary.get("prepare_error", ""))
        self.assertEqual(run.days, [])


class TestTask38DayProgressAfterSleepRetry(unittest.TestCase):
    """【task-38】"上一天报告没跨日、这一天报告跨了"不许被 `no_day_progress` 误杀。

    真机来源：0.7.23 彩排（`logs\\longrun-rehearsal-0.7.23.jsonl`）—— 22:10 第一次回家寻路超时
    （`ended_by=sleep_failed`，游戏日仍是 spring 17），第二次（人已经走近）才跨到 spring 18。
    旧代码把 `_last_day_key` 记成**睡前**那一天（`last_obs` 正是特意冻结的睡前快照），于是总控
    看到"前一天报告结束在 17 日、这一天报告也结束在 17 日" ⇒ 误判"游戏日没有前进"当场停：
    `--days 1` 靠 streak 侥幸仍返 0，`--days 3` 会在第 1 天就退出并判 1（run3 会白烧）。
    """

    def test_sleep_retry_after_a_failed_night_still_counts(self):
        class FlakySleepWorld(FakeWorld):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.fail_sleeps = 1
                self.sleep_attempts = 0

            def sleep(self):
                self.sleep_attempts += 1
                if self.fail_sleeps > 0:
                    self.fail_sleeps -= 1
                    self.unwatered_at_sleep.append(
                        sum(1 for c in self.crops.values() if not c["watered"]))
                    return StepResult("sleep", code="failed",
                                      reason="回不了 FarmHouse：寻路超时（假世界第一次）")
                return super().sleep()

        # 没种子、没钱、没障碍 ⇒ 守卫按 `no_work` 放行睡觉，两次都发生在同一个游戏日里。
        w = FlakySleepWorld(weeds=0, seeds=0, money=0)
        # 真机口径的 farm 快照（0 作物 ⇒ dryCrops=0）：本世界没有任何 tile，空窗口按 task-19
        # NIT-1 如实判 False，会把这天误伤成 needs_review —— 与 `test_no_buy_flag` 同一个坑。
        w.farm = {"loaded": True, "complete": True, "crops": 0, "dryCrops": 0,
                  "unwateredCrops": 0, "hoeDirt": 0}
        run = make_run(w, target_days=1)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertEqual(w.sleep_attempts, 2, "第一次失败后必须再试一次，不能当场收工")
        self.assertEqual([d.ended_by for d in run.days], ["sleep_failed", "sleep"])
        self.assertTrue(run.days[-1].verified, run.days[-1].checks)
        self.assertFalse(any(e["event"] == "no_day_progress" for e in run.entries),
                         "睡成功了就不许判'游戏日没有前进'（这正是彩排里那行误报）")
        # task-38 第二半：睡后的**观测**（不是回执）必须落进账本 —— `final` 是睡前快照，
        # `tools\verify-run3.py` 的跨日证据只能读 `day_after`。
        self.assertEqual(run.days[-1].day_after, [1, "spring", 7])
        self.assertIsNone(run.days[0].day_after, "没睡成的那天不许有睡后观测")
        ends = [e for e in run.entries if e["event"] == "day_end"]
        self.assertEqual(ends[-1]["day_after"], [1, "spring", 7])


class TestDiscipline(unittest.TestCase):
    def test_sleep_intent_is_vetoed_while_work_remains(self):
        """慢脑说"睡"，但地里还有活 ⇒ 必须否决并记 intent_vetoed（用户 2026-10-11 的要求）。"""
        w = FakeWorld(weeds=4, seeds=10, money=500)
        planner = FakePlanner(TaskIntent(task="sleep", area_hint="", reason="模型想睡"))
        run = make_run(w, target_days=1, planner=planner)
        code = run.run()
        self.assertEqual(code, 1)
        rep = run.days[0]
        self.assertNotEqual(rep.ended_by, "sleep")
        self.assertTrue(any(e["event"] == "intent_vetoed" for e in run.entries))
        # task-73 之后：判 `stuck` 的日子会走**有界翻篇**（`_stuck_flush`，整轮 ≤ MAX_STUCK_FLUSH 次），
        # 所以这里允许出现 sleep —— 但必须**全部来自翻篇**，绝不许来自那个被否决的睡眠意图。
        flushes = [e for e in run.entries if e["event"] == "stuck_flush"]
        self.assertEqual(w.sleeps, len(flushes),
                         "睡觉只能来自 stuck 翻篇；被否决的睡眠意图一次都不许落地")
        self.assertLessEqual(len(flushes), MAX_STUCK_FLUSH)
        # 不是假装干完了：如实报 stuck
        self.assertEqual(rep.ended_by, "stuck")

    def test_review_intent_is_recorded(self):
        w = FakeWorld(weeds=4, seeds=10, money=500)
        planner = FakePlanner(TaskIntent(task="review", area_hint="anchor:current_location",
                                         reason="复盘"))
        run = make_run(w, target_days=1, planner=planner)
        code = run.run()
        self.assertEqual(code, 1)                 # 只复盘不干活 ⇒ 不算数
        self.assertEqual(run.days[0].ended_by, "stuck")

    def test_zone_hint_from_llm_is_used_next_time(self):
        w = FakeWorld(weeds=0, seeds=4, money=20)
        # 先让 LLM 给一个具名田区：应被记进 pending_zone_hint，而不是被当成坐标
        planner = FakePlanner(TaskIntent(task="plant_area", area_hint="field_se", reason="种东南"))
        run = make_run(w, target_days=1, planner=planner)
        run.run()
        self.assertTrue(any(e["event"] == "decision" for e in run.entries))

    def test_watchdog_stop_aborts_and_reports(self):
        import agentfarm.longrun as lr
        from agentfarm.watchdog import Finding

        w = FakeWorld(weeds=4, seeds=10, money=500)
        reports: list[dict] = []
        orig = (lr.assess, lr.verdict, lr.write_stop_report)
        lr.assess = lambda health, observe, **kw: [
            Finding("world_stuck", lr.LEVEL_STOP, "世界不动了", "假造")]
        lr.verdict = lambda findings: lr.LEVEL_STOP
        lr.write_stop_report = lambda findings, **kw: reports.append(kw)
        try:
            run = make_run(w, target_days=1, supervise_every=1, report_dir="logs")
            code = run.run()
        finally:
            lr.assess, lr.verdict, lr.write_stop_report = orig
        self.assertEqual(code, 1)
        self.assertEqual(run.days[0].ended_by, "stop")
        self.assertTrue(reports, "watchdog 判 STOP 必须落事故报告")
        self.assertTrue(any(e["event"] == "watchdog_stop" for e in run.entries))

    def test_journal_jsonl_written(self):
        w = FakeWorld(weeds=4, seeds=10, money=500)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "longrun.jsonl"
            run = make_run(w, target_days=1, journal_path=path)
            run.run()
            self.assertTrue(path.exists())
            lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        events = [x["event"] for x in lines]
        self.assertIn("day_start", events)
        self.assertIn("day_end", events)
        self.assertIn("finish", events)
        self.assertTrue(all("t" in x for x in lines))

    def test_sleep_journal_keeps_mod_receipt(self):
        """task-8 D：`sleep` 事件必须带 Mod 回执原文。

        真机 run2 的 journal 里只剩一句 `"睡觉请求失败"`（`farmwork.sleep()` 把 Mod 的
        `Diagnose()` 固定掉了），事后再也看不出是"没上床"还是"提问没弹"。这条把它钉死：
        回执原文（含 `sleep_no_question` 的 lastQuestionKey/isInBed 现场）必须进事件。
        """
        w = FakeWorld(weeds=0, seeds=0, money=0)
        for t in sorted(w.tillable):
            w.dirt.add(t)                       # 真没活干 ⇒ 睡觉闸门放行，能走到 _do_sleep
        run = make_run(w, target_days=1)
        receipt = ("sleep_no_question: 睡觉提问没弹出来，拒绝盲发应答；"
                   "诊断：isInBed=false, lastQuestionKey=(空), activeClickableMenu=(无)")
        # 假世界这一天的 sleep 如实回一条 Mod 风格的失败（`FakeWorker.sleep()` 转调 `world.sleep()`）
        w.sleep = lambda: StepResult(
            "sleep", code="sleep_no_question",
            reason=f"睡觉失败（sleep_no_question）：{receipt}", receipt=receipt)
        run.run()
        sleeps = [e for e in run.entries if e["event"] == "sleep"]
        self.assertGreaterEqual(len(sleeps), 1, run.entries)
        ev = sleeps[0]
        self.assertFalse(ev["ok"])
        self.assertEqual(ev["code"], "sleep_no_question")
        self.assertEqual(ev["receipt"], receipt)
        self.assertIn("lastQuestionKey", ev["receipt"])
        # 睡不成 ⇒ 这一天不算数（如实收尾，不许当成功）
        self.assertEqual(run.days[-1].ended_by, "sleep_failed")

    def test_budget_exhausted_stops(self):
        w = FakeWorld(weeds=4, seeds=10, money=500)
        run = make_run(w, target_days=1, max_minutes=0.0, max_steps=1)
        code = run.run()
        self.assertEqual(code, 1)
        self.assertTrue(run.days[0].ended_by in ("budget", "stuck", "sleep"))

    def test_stage_refill_retry_uses_worker_refill(self):
        w = FakeWorld(weeds=0, seeds=10, money=500, water_left=2)
        run = make_run(w, target_days=1)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertGreaterEqual(w.refills, 1)
        # 补水之后要把这一天的作物浇完才睡（睡前口径，不是第二天）
        self.assertEqual(w.unwatered_at_sleep, [0])


class TestHelpers(unittest.TestCase):
    def test_seed_items_reads_names_not_ids(self):
        player = {"inventory": [{"id": "999", "name": "Rare Seed", "stack": 3},
                                {"id": SEED_ID, "name": SEED_NAME, "stack": 4},
                                {"id": "1", "name": "Hoe", "stack": 1, "isTool": True}]}
        got = seed_items(player)
        self.assertEqual(sum(n for _i, _n, n in got), 7)

    def test_run_returns_two_when_bridge_missing(self):
        run = make_run(client_factory=lambda: (_ for _ in ()).throw(
            __import__("agentfarm.bridge", fromlist=["BridgeError"]).BridgeError("no file")))
        self.assertEqual(run.run(), 2)


class TestLlmDefaultOn(unittest.TestCase):
    """用户 m02320："大模型改成长跑默认开启"；m01184：开始介入时必须明确告知。"""

    def test_longrun_defaults_to_llm_enabled(self):
        w = FakeWorld(weeds=2, seeds=10, money=500)
        run = LongRun(client_factory=lambda: FakeClient(w),
                      worker_factory=lambda c: FakeWorker(w),
                      target_days=1, log=lambda _s: None, sleep_fn=lambda _s: None,
                      supervise_every=0)
        self.assertTrue(run.llm_enabled)
        self.assertTrue(run.planner.llm_enabled)

    def test_token_budget_is_consistent_across_modules(self):
        """三处默认值必须一致：真机上 4096 被推理吃光过（plan-llm-manual-5）。"""
        from agentfarm import llm
        from agentfarm.planner import BoundaryPlanner
        self.assertEqual(DEFAULT_LLM_MAX_TOKENS, llm.DEFAULT_MAX_TOKENS)
        self.assertEqual(BoundaryPlanner().max_tokens, llm.DEFAULT_MAX_TOKENS)

    def test_llm_on_is_announced_before_anything_else(self):
        w = FakeWorld(weeds=2, seeds=10, money=500)
        run = make_run(w, llm_enabled=False)
        self.assertEqual(run.run(), 0, run.logs)
        self.assertTrue(any("大模型已关闭" in line for line in run.logs), run.logs[:4])
        self.assertFalse(any(e["event"] == "llm_on" for e in run.entries))

        w2 = FakeWorld(weeds=2, seeds=10, money=500)
        calls: list[dict] = []

        def fake_chat(messages, **kwargs):
            calls.append(kwargs)
            return json.dumps({"tasks": [
                {"task": "water_area", "area_hint": "tiles.unwatered_crops",
                 "reason": "作物要浇水", "expected_evidence": "unwatered_crops 下降"},
            ]}, ensure_ascii=False)

        run2 = make_run(w2, llm_enabled=True, llm_chat=fake_chat)
        self.assertEqual(run2.run(), 0, run2.logs)
        self.assertTrue(any("大模型已开启" in line for line in run2.logs), run2.logs[:4])
        self.assertTrue(any(e["event"] == "llm_on" for e in run2.entries), run2.entries[:3])
        # 播报里给的 token 上限就是真正发出去的那个
        self.assertTrue(all(c["max_tokens"] == DEFAULT_LLM_MAX_TOKENS for c in calls), calls)


class TestIntentBackstop(unittest.TestCase):
    """用户 m02591：策略/大模型的决定必须先过校验 —— 做得了就继续，做不了就取消换任务，
    绝不能"啥也没做就掉头睡觉"（m02532 当场抓到的现象）。"""

    def test_verify_intents_cancels_when_visible_and_keeps_unknown_when_far(self):
        w = MyopicWorld(weeds=0)
        run = make_run(w, target_days=1)
        plot = {"anchor": [60, 10], "tiles": [list(t) for t in sorted(w.tillable)]}
        # 玩家就在旁边、看得见 25 格可锄地 ⇒ 继续
        kept, verdicts = run._verify_intents([TaskIntent("till_area", "", "", ())], w.obs(), plot)
        self.assertEqual([i.task for i in kept], ["till_area"])
        self.assertEqual(verdicts[0]["verdict"], "keep")
        self.assertGreater(verdicts[0]["targets"], 0)
        # 看得见、但一格熟作物都没有 ⇒ 取消（不是"今天收工"）
        kept, verdicts = run._verify_intents([TaskIntent("harvest", "", "", ())], w.obs(), plot)
        self.assertEqual(kept, [])
        self.assertEqual(verdicts[0]["verdict"], "cancel")
        # 走远了：观测看不见这片地，"没有目标"这句话不可信 ⇒ 继续（由执行层走过去再看）
        w.player_tile = [90, 40]
        kept, verdicts = run._verify_intents([TaskIntent("till_area", "", "", ())], w.obs(), plot)
        self.assertEqual([i.task for i in kept], ["till_area"])
        self.assertEqual(verdicts[0]["verdict"], "unknown")
        # review / sleep 这类意图不按"有没有目标格"判，永远放行
        kept, verdicts = run._verify_intents([TaskIntent("review", "", "", ())], w.obs(), plot)
        self.assertEqual([i.task for i in kept], ["review"])
        self.assertEqual(verdicts, [])

    def test_stage_walks_into_plot_when_targets_are_invisible(self):
        w = MyopicWorld(weeds=0)                 # 25 格全是可锄空地
        w.player_tile = [90, 40]                 # 站在很远的地方 ⇒ 观测里一格可锄都看不见
        run = make_run(w, target_days=1)
        run.worker = FakeWorker(w)
        rep = DayReport(day_key=("spring", 1, 6), started_at=0.0)
        plot = {"anchor": [60, 10], "tiles": [list(t) for t in sorted(w.tillable)]}
        self.assertEqual(run._stage_tiles("till_area", w.obs(), plot), [])
        met = False
        for _ in range(5):                        # 每轮最多 12 格（per_stage_tiles）
            out = run._step_stage("till_area", w.obs(), plot, rep)
            met = met or out.postcondition_met
            if met:
                break
        self.assertTrue(met, out.reason)
        self.assertEqual(len(w.dirt), 25, "走过去之后应当把这一片全锄开")
        self.assertGreaterEqual(run.worker.walk_steps, 1)
        self.assertTrue(any(e["event"] == "plot_walk" for e in run.entries), run.entries)
        self.assertNotIn("till_area", run.no_target)

    def test_empty_intents_does_not_sleep_when_guard_says_keep_working(self):
        # 没种子但买得起 ⇒ 守卫认为"还有活"（该去补种子），绝不允许直接回屋睡
        w = FakeWorld(weeds=0, seeds=0, money=500)
        run = make_run(w, target_days=1,
                       planner=FakePlanner(TaskIntent("harvest", "tiles.ripe", "收成熟的", "ripe>0")))
        code = run.run()
        self.assertGreaterEqual(len(w.buys), 1, ("应当去补种子，而不是掉头睡觉", run.entries))
        self.assertEqual(run.days[0].ended_by, "sleep")   # 一天如实收尾（不是崩在半路）
        self.assertEqual(code, 0, run.logs)

    def test_cancel_falls_back_to_another_task_instead_of_sleeping(self):
        """校验取消之后要**换别的任务**（用户 m02591）：不是原地空转，更不是掉头睡觉。

        这里的假策略永远只要 `harvest`（一格熟作物都没有）⇒ 校验必须取消它，并且由确定性策略
        接手把地真的开出来。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        run = make_run(w, target_days=1,
                       planner=FakePlanner(TaskIntent("harvest", "tiles.ripe", "收成熟的", "ripe>0")))
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        rep = run.days[0]
        self.assertEqual(rep.ended_by, "sleep")
        # harvest 是**全场级**任务 ⇒ 取消一次就当天不再要（换片地也不该重问）
        self.assertIn("harvest", run.no_target_global)
        verdicts = [e for e in run.entries if e["event"] == "intent_verdict"][0]["verdicts"]
        self.assertEqual(verdicts[0], {"task": "harvest", "verdict": "cancel",
                                       "reason": verdicts[0]["reason"]})
        self.assertTrue(any(e["event"] == "policy_fallback" for e in run.entries), run.entries)
        self.assertGreaterEqual(len(w.dirt), 1, ("取消之后必须换任务真干活", run.entries))


class RestlessWorld(FakeWorld):
    """(60,10) 上的障碍每挥一次就换个样子：状态**一直在变** ⇒ `_mark_blocked` 永远封不掉它。

    `blocked` 的判据是"动手前后这一格没变"。世界在变、但目标状态永远达不到"是判据盖不住的
    缝隙（真机上也可能出现：工具等级/特征不匹配时 Mod 反复换工具、世界被搅动却没清掉）。
    这条缝由兜底不变量 `MAX_TILE_ATTEMPTS` 兜住：同一格一天最多被发起 2 次。
    """

    def __init__(self, **kw) -> None:
        super().__init__(weeds=0, **kw)
        self.blockers[(60, 10)] = "weed"

    def clear(self, tile):
        t = tuple(tile)
        if t == (60, 10):
            self.blockers[t] = "twig" if self.blockers.get(t) == "weed" else "weed"
            return StepResult("clear", t, code="failed", reason="挥了没清掉（这格换了样子）")
        return super().clear(t)


class TestDoomedWorkIsNotRepeated(unittest.TestCase):
    """task-4：注定失败的动作不重复发起（用户 m01758/m01804）。

    真机 run1：clear_area 的两格 grass 被连挥两次、随后两轮策略又各喊一次"周围还有 2 处障碍"，
    白烧体力之后这个阶段还判了 VERIFIED。把三件事钉住：判据前置、同一格一天最多发起 2 次、
    grass 成/败如实记。
    """

    def test_judged_impossible_tiles_never_enter_targets(self):
        """判据在**观测**里就成立 ⇒ 这些格根本不进目标池（不是"发起了再失败"）。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        run = make_run(w, target_days=1)
        obs = w.obs()
        obs["location"]["tiles"] = [
            {"tile": [60, 10], "kind": "unknown", "feature": "Stone", "standable": True, "actionable": True},
            {"tile": [60, 11], "kind": "unknown", "objId": "42", "standable": True, "actionable": True},
            {"tile": [60, 12], "kind": "unknown", "objId": "-1", "standable": True, "actionable": True},
        ]
        obs["location"]["tillable"] = [[60, 10], [60, 11], [60, 12]]
        plot = {"anchor": [60, 10], "tiles": [[60, 10], [60, 11], [60, 12]]}
        # 有 feature / 有 objId 的格：Mod 说"可锄"，但观测判据说锄不动 ⇒ 0 次发起
        self.assertEqual(run._stage_tiles("till_area", obs, plot), [(60, 12)])
        self.assertEqual(run._leftover("till_area", obs, plot), [(60, 12)])

    def test_tile_at_attempt_cap_is_not_attempted_again(self):
        """同一格连续失败两次之后不再发起第三次（兜底不变量）。"""
        w = RestlessWorld()
        run = make_run(w, target_days=1)
        run.worker = FakeWorker(w)
        plot = next(p for p in run._plot_candidates(w.obs())
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})
        rep = DayReport(day_key=("spring", 1, 6), started_at=0.0)
        for _ in range(4):
            run._step_stage("clear_area", w.obs(), plot, rep)
        self.assertEqual(run.tile_attempts.get((60, 10)), MAX_TILE_ATTEMPTS)
        # 状态一直在变 ⇒ 封格判据不成立；拦住重复发起的是次数上限，不是 blocked
        self.assertNotIn((60, 10), run.blocked)
        self.assertNotIn((60, 10), run._stage_tiles("clear_area", w.obs(), plot))
        # 地还是没清掉 ⇒ 后置条件如实为"未成立"（没有假进展）
        self.assertEqual(len(run._leftover("clear_area", w.obs(), plot)), 1)

    def test_stuck_grass_is_swung_once_then_blocked_for_the_day(self):
        """真机 run1（spring 9，(58,21)/(56,21)）复现：镰刀在背包，割了世界不变。

        验收：只挥**一次**（不是连挥两次、也不是下一轮策略再喊一次）、当天封格、
        如实记 skipped/proven_inert（不是 failed），并把判据写进 reason 与 journal。
        """
        w = FakeWorld(weeds=0, seeds=0, money=0, scythe=True)
        w.blockers[(60, 10)] = "grass"
        w.stuck.add((60, 10))
        run = make_run(w, target_days=1)
        run.worker = FarmWorker(FakeClient(w), log=lambda *_: None)
        plot = next(p for p in run._plot_candidates(w.obs())
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)

        out = run._step_stage("clear_area", w.obs(), plot, rep)
        self.assertEqual(w.swings.get((60, 10)), 1, "这一格只允许白挥一次")
        stage = rep.stages[-1]
        self.assertEqual((stage["stage"], stage["ok"], stage["skipped"], stage["failed"]),
                         ("clear_area", 0, 1, 0), stage)
        self.assertEqual(stage["proven_inert"], 1, stage)
        self.assertIn("干不动", out.reason)
        self.assertIn((60, 10), run.blocked)
        # 判据进 journal：`blocked` 事件带 tile/action/no_effect/reason（可事后复核）
        ev = [e for e in run.entries if e["event"] == "blocked"]
        self.assertEqual(len(ev), 1, run.entries)
        self.assertEqual(ev[0]["tile"], [60, 10])
        self.assertEqual(ev[0]["action"], "clear")
        self.assertFalse(ev[0]["no_effect"], "proven_inert 不是「花了体力没变」")
        # 判据本身（"kind 离开 grass"没满足）+ 现场（体力/工具）都进了 journal
        self.assertIn("kind 离开 grass", ev[0]["reason"])
        self.assertIn("scythe", ev[0]["reason"])
        # ⚠️ task-9：封格**只免掉重试**，不许把这次"没做成"洗成功。这一格世界 0 变化、
        # 目标 kind 仍是 grass ⇒ 后置条件必须**不成立**，阶段终态是 needs_review。
        # 判据（哪条判据说它干不动）留在 reason/`proven_inert`/journal `blocked` 里供复核。
        self.assertFalse(out.postcondition_met, out.reason)
        self.assertNotEqual(out.terminal, "VERIFIED", out.reason)
        self.assertIn("还剩 1 格", out.reason)
        self.assertIn("1 格已判定干不动", out.reason)
        self.assertIn("kind 离开 grass", out.reason)
        self.assertNotIn("还剩 0 格", out.reason, "不许出现自相矛盾的文案")
        # 干不动的原因也进 journal（单独一条 `stage_exhausted`，带格与理由）
        ex = [e for e in run.entries if e["event"] == "stage_exhausted"]
        self.assertEqual(len(ex), 1, run.entries)
        self.assertEqual((ex[0]["stage"], ex[0]["leftover"], ex[0]["doomed"]),
                         ("clear_area", 1, 1), ex[0])

        # 策略下一轮再要 clear_area：该格当天已封 ⇒ 一次都不再发起
        run._step_stage("clear_area", w.obs(), plot, rep)
        self.assertEqual(w.swings.get((60, 10)), 1, "当天不允许第二次发起")
        self.assertEqual(run.tile_attempts.get((60, 10)), 1)

    def test_grass_clear_success_is_recorded_as_ok(self):
        """grass 成：镰刀割掉、kind 变了 ⇒ ok（不是 skipped/proven_inert）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0, scythe=True)
        w.blockers[(60, 10)] = "grass"
        run = make_run(w, target_days=1)
        run.worker = FarmWorker(FakeClient(w), log=lambda *_: None)
        plot = next(p for p in run._plot_candidates(w.obs())
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        out = run._step_stage("clear_area", w.obs(), plot, rep)
        self.assertEqual(w.swings.get((60, 10)), 1)
        self.assertNotIn((60, 10), w.blockers)
        stage = rep.stages[-1]
        self.assertEqual((stage["ok"], stage["failed"], stage["proven_inert"]), (1, 0, 0), stage)
        self.assertTrue(out.postcondition_met)


class CountingWorker(FakeWorker):
    """假执行层 + 记下 `run_stage` 被叫过几次。

    "没种子不垦地"的验收不能只看"世界没变"（锄了地世界就变了）：必须证明执行层**根本没人叫**，
    所以要在 `run_stage` 上挂计数器。真机 run2 的教训正是"上层说要垦、执行层就真锄"。
    """

    def __init__(self, world: FakeWorld) -> None:
        super().__init__(world)
        self.stage_calls: list[tuple[str, list[tuple[int, int]]]] = []

    def run_stage(self, stage, tiles, *, min_stamina=12.0, max_steps=200):
        self.stage_calls.append((stage, [tuple(t) for t in tiles]))
        return super().run_stage(stage, tiles, min_stamina=min_stamina, max_steps=max_steps)


class TestAccountingTask9(unittest.TestCase):
    """task-9 的三处账目/资源缺陷（全部来自真机 run2）：

    ① `blocked` 只许"不再重试"，**不许**把"没做成"洗成 VERIFIED；
    ② 没种子又买不起时**不许**再开垦/播种（白烧体力 270→74、60 格空 dirt）；
    ③ 提示词预算 8192 被推理吃光（`LlmError:truncated`）⇒ 默认 16384 且降级要标出"是不是截断"。
    """

    def test_blocked_leftover_is_not_verified(self):
        """只剩"已判定干不动"的格子 ⇒ 后置条件不成立、needs_review，且文案不说"还剩 0 格"。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        w.tillable = {(60, 10)}          # 只留一格：它一封，整个阶段就只剩"干不动"的格子
        run = make_run(w, target_days=1)
        run.worker = FakeWorker(w)
        plot = {"zone": "", "label": "", "anchor": [60, 10], "tiles": [(60, 10)], "note": ""}
        run.blocked[(60, 10)] = "till 无效：锄完不是 dirt"
        rep = DayReport(day_key=("spring", 1, 6), started_at=0.0)

        out = run._step_stage("till_area", w.obs(), plot, rep)

        # 这一格世界 0 变化、目标 kind 也没达标 ⇒ 后置条件必须**不成立**
        self.assertFalse(out.postcondition_met, out.reason)
        self.assertEqual(out.terminal, "needs_review", out.reason)
        self.assertNotEqual(out.terminal, "VERIFIED")
        # 文案：报剩余格数 + 其中几格干不动（判据留在 reason 里供复核），且不许自相矛盾
        n = len(run._leftover("till_area", w.obs(), plot))
        self.assertEqual(n, 1, "复核集合必须看得见被封的格子")
        self.assertIn("还剩 1 格", out.reason)
        self.assertIn("1 格已判定干不动", out.reason)
        self.assertIn("锄完不是 dirt", out.reason)
        self.assertNotIn("还剩 0 格", out.reason)
        self.assertNotIn("后置条件成立", out.reason)
        # 记账的**唯一**作用是不再空转：策略这天不再要 till_area（但它不是"成功"）
        self.assertIn("till_area", run.no_target)
        ex = [e for e in run.entries if e["event"] == "stage_exhausted"]
        self.assertEqual(len(ex), 1, run.entries)
        self.assertEqual((ex[0]["stage"], ex[0]["leftover"], ex[0]["doomed"]),
                         ("till_area", 1, 1), ex[0])

    def test_no_seed_no_money_never_tills(self):
        """种子 0 且钱 < 单价 ⇒ 三道口径都说"没活"，`run_stage` 一次都不被叫。

        task-15 §② 追加：复核集合（`_leftover`）**也必须归零** —— 否则"0 目标 + leftover>0"
        的阶段会被 `no_unmet_stages` 当成"没做完"，run3 开局就被自己判死。
        """
        w = FakeWorld(weeds=0, seeds=0, money=5)
        w.dirt = {(60, 10)}              # 留一格已锄开的地：不设闸门时 plant_area 本会去播种
        run = make_run(w, target_days=1)
        run.worker = CountingWorker(w)
        plot = next(p for p in run._plot_candidates(w.obs())
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})

        # ① 目标集合：两阶段都空（不是因为"本来就没地"，地还在——但复核也照同口径归零）
        self.assertEqual(run._stage_tiles("till_area", w.obs(), plot), [])
        self.assertEqual(run._stage_tiles("plant_area", w.obs(), plot), [])
        self.assertEqual(run._leftover("plant_area", w.obs(), plot), [],
                         "task-15 §②：0 目标的阶段 leftover 必须归零，别造出假剩余")
        self.assertEqual(run._leftover("till_area", w.obs(), plot), [])
        # ② 守卫层同口径：这片地"没活"
        self.assertFalse(run._plot_has_work(w.obs(), [tuple(t) for t in plot["tiles"]]))

        rep = DayReport(day_key=("spring", 1, 6), started_at=0.0)
        out = run._step_stage("till_area", w.obs(), plot, rep)
        # ③ 执行层：一格都没动（`run_stage` 根本没被叫）
        self.assertEqual(run.worker.stage_calls, [], "没种子还去垦地 = 白烧体力")
        self.assertFalse(out.postcondition_met)
        self.assertNotEqual(out.terminal, "VERIFIED")
        self.assertNotIn("后置条件成立", out.reason)
        self.assertEqual(rep.stages[-1]["leftover"], 0, rep.stages[-1])
        # 人话 + 判据都留下：播报一次、journal 带 seeds/money/单价
        self.assertTrue(any("不再开垦" in n for n in rep.notes), rep.notes)
        gate = [e for e in run.entries if e["event"] == "seed_gate"]
        self.assertEqual(len(gate), 1, run.entries)
        self.assertEqual((gate[0]["seeds"], gate[0]["money"], gate[0]["seed_price"]),
                         (0, 5, run.seed_price), gate[0])
        # task-15 §③：`in_plot` 如实回答"是不是已经在田里才发现没种子"（最贵的那条路）
        pt = tuple(run._snap()["player"]["tile"])
        self.assertEqual(gate[0]["in_plot"], pt in {tuple(t) for t in plot["tiles"]}, gate[0])
        run.seed_gate_noted.clear()
        w.player_tile = list(plot["tiles"][0])
        run._step_stage("till_area", w.obs(), plot, rep)
        gate2 = [e for e in run.entries if e["event"] == "seed_gate"]
        self.assertTrue(gate2[-1]["in_plot"], "人站在作业区里 ⇒ in_plot 必须为真")

    def test_default_max_tokens_is_16384(self):
        """提示词预算：默认 16384（三处同一个真值源），且降级要能标出"是不是被截断"。"""
        from agentfarm import llm
        from agentfarm.llm import LlmError
        from agentfarm.planner import Brief, PlannerState

        self.assertEqual(llm.DEFAULT_MAX_TOKENS, 16384)
        self.assertEqual(DEFAULT_LLM_MAX_TOKENS, llm.DEFAULT_MAX_TOKENS)
        self.assertEqual(BoundaryPlanner().max_tokens, llm.DEFAULT_MAX_TOKENS)
        self.assertEqual(BoundaryPlanner(max_tokens=4096).max_tokens, 4096)
        # 播报/journal 报的是**生效值**（用户 `--max-tokens` 调小了，日志不许还写 16384）
        self.assertEqual(make_run(FakeWorld(), llm_max_tokens=4096).llm_max_tokens, 4096)

        def boom(*_a, **_kw):
            raise LlmError("回答被 max_tokens 截断（reasoning 吃光预算、content 为空）",
                           status="truncated")

        planner = BoundaryPlanner(llm_chat=boom, max_llm_attempts=1)
        decision = planner.decide(PlannerState(day_key=(1, "spring", 5)),
                                  Brief(day_key=(1, "spring", 6), counts={"blockers": 1}))
        self.assertEqual(decision.source, "deterministic_fallback")
        self.assertIn("truncated", decision.fallback_reason or "")
        self.assertTrue(decision.truncated, "降级原因里有 truncated ⇒ 必须标出来")
        self.assertTrue(decision.as_dict()["truncated"])
        # 反例：网络类失败不许被误标成"该调大预算"
        def boom2(*_a, **_kw):
            raise LlmError("超时", status="network")

        d2 = BoundaryPlanner(llm_chat=boom2, max_llm_attempts=1).decide(
            PlannerState(day_key=(1, "spring", 5)),
            Brief(day_key=(1, "spring", 6), counts={"blockers": 1}))
        self.assertFalse(d2.truncated)
        self.assertFalse(d2.as_dict()["truncated"])


class LyingClient(FakeClient):
    """回执说"已经空了"，世界一动不动 —— 真机 run1 镰刀"假 ok"的复现（task-7 回归钉子）。"""

    def use_tool(self, tile, *, tool=None, timeout_ms=None):
        t = tuple(tile)
        self.w.swings[t] = self.w.swings.get(t, 0) + 1
        return {"ok": True, "status": "ok",
                "reason": f"已用「Scythe」对 {t} 动手 1 次，现在**已经空了**"}


class TestTask7ScytheSwings(unittest.TestCase):
    """task-7：**回执 ok ≠ 做成了** —— 观测没变就绝不许 VERIFIED。

    真机 run1 的 (58,21)/(56,21)：Mod 的 `Done()` 少了 Grass 判据，空挥也回"已经空了"，
    上层若信回执就会把"草还在"记成成功。这里用假 ok 把这条回归钉住。
    """

    def test_lying_ok_receipt_never_verifies_clear_area(self):
        w = FakeWorld(weeds=0, seeds=0, money=0, scythe=True)
        w.blockers[(60, 10)] = "grass"
        run = make_run(w, target_days=1)
        run.worker = FarmWorker(LyingClient(w), log=lambda *_: None)
        plot = next(p for p in run._plot_candidates(w.obs())
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)

        out = run._step_stage("clear_area", w.obs(), plot, rep)

        self.assertEqual(w.swings.get((60, 10)), MAX_CLEAR_SWINGS,
                         "回执说成了、观测没变 ⇒ 要挥满上限才认，不许一票通过")
        self.assertEqual(w.blockers.get((60, 10)), "grass", "世界 0 变化：这一格还是草")
        self.assertFalse(out.postcondition_met, out.reason)
        self.assertNotEqual(out.terminal, "VERIFIED", out.reason)
        self.assertIn("kind 离开 grass", out.reason)
        self.assertIn((60, 10), run.blocked)
        stage = rep.stages[-1]
        self.assertEqual((stage["ok"], stage["proven_inert"]), (0, 1), stage)


class TestTask22EnvAccounting(unittest.TestCase):
    """task-22：**任意 skill** 的一次瞬时渐黑/模态，都不封格、都不吃配额（inconclusive 仍吃）。

    背景（`longrun.py` 的 `_mark_blocked`/`_count_attempts` 准入都是 `s.failed or s.proven_inert`，
    而 `_count_attempts` **不带动作过滤**）：浇水/播种/收获/走路上的一次 `world_fading`/`ui_modal`
    （这些 status 是全桥通用的）会把格子推到 `MAX_TILE_ATTEMPTS` → `capped` → `stage_exhausted`，
    当天被杀。所以 `FarmWorker` 给这些出口打 `env_block`/`inconclusive` 标，`longrun` 据此
    **不封格、不占配额**；`inconclusive`（超时/异常/未知码）仍占配额并如实 capped。
    """

    @staticmethod
    def _plot() -> dict:
        return {"zone": "", "label": "", "anchor": [60, 10], "tiles": [(60, 10)], "note": ""}

    @staticmethod
    def _events(run: LongRun, event: str) -> list:
        return [e for e in run.entries if e["event"] == event]

    def test_clear_env_block_retried_inside_the_same_stage_call(self):
        """渐黑挡了第一次清障 ⇒ **同一次 `_step_stage` 里就重跑同一批格子**（task-15 §④）、
        事后做成 ⇒ 不封格、不占配额、**不算硬失败**。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.fail_status[(60, 10)] = ["world_fading"]      # 只挡第一次，之后恢复正常
        run = make_run(w, target_days=1)
        run.worker = FarmWorker(FakeClient(w), log=lambda *_: None)
        plot = self._plot()
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)

        out = run._step_stage("clear_area", w.obs(), plot, rep)

        self.assertNotIn((60, 10), w.blockers, "环境挡路只该延后，不该让这一格当天做不成")
        self.assertTrue(out.postcondition_met, out.reason)
        self.assertNotIn((60, 10), run.blocked, "环境挡路不是这一格的属性")
        self.assertIsNone(run.tile_attempts.get((60, 10)), "环境挡路不占本日尝试配额")
        self.assertEqual(self._events(run, "blocked"), [], run.entries)
        env = self._events(run, "env_fail")
        self.assertEqual(len(env), 1, run.entries)
        self.assertEqual(env[0]["statuses"], ["world_fading"], env[0])
        self.assertEqual(env[0]["tiles"], 1, env[0])
        # §④ 要求 1：重试过程必须留痕（轮次/重跑格数/挡路模态/状态码）
        retry = self._events(run, "env_retry")
        self.assertEqual(len(retry), 1, run.entries)
        self.assertEqual((retry[0]["stage"], retry[0]["round"], retry[0]["limit"],
                          retry[0]["tiles"], retry[0]["statuses"], retry[0]["targets"]),
                         ("clear_area", 1, run.max_env_retries, 1, ["world_fading"], [[60, 10]]), retry[0])
        # §④ 要求 2：这一次环境挡路**不进硬失败**（目标已达成），但要单独说出来
        stage = rep.stages[-1]
        self.assertEqual((stage["failed"], stage["failed_any"]), (0, 1), stage)
        self.assertIn("另有 1 次环境挡路已重试做成（不计硬失败）", out.reason)

    def test_inconclusive_spends_quota_and_caps_without_sealing(self):
        """一直没结论（全 timeout）⇒ 不封格但**占配额**；两轮后如实 `capped`、当天 needs_review。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.fail_status[(60, 10)] = "timeout"             # 一直没结论
        run = make_run(w, target_days=1)
        run.worker = FarmWorker(FakeClient(w), log=lambda *_: None)
        plot = self._plot()
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)

        run._step_stage("clear_area", w.obs(), plot, rep)
        self.assertEqual(run.tile_attempts.get((60, 10)), 1)
        self.assertNotIn((60, 10), run.blocked)
        inc = self._events(run, "inconclusive_fail")
        self.assertEqual(len(inc), 1, run.entries)
        self.assertEqual(inc[0]["statuses"], ["timeout"], inc[0])

        out2 = run._step_stage("clear_area", w.obs(), plot, rep)
        self.assertEqual(run.tile_attempts.get((60, 10)), MAX_TILE_ATTEMPTS)
        self.assertNotIn((60, 10), run.blocked, "没拿到结论也不许封格")
        self.assertIn("尝试上限", out2.reason)
        self.assertFalse(out2.postcondition_met, out2.reason)
        self.assertEqual(out2.terminal, "needs_review", out2.reason)
        ex = self._events(run, "stage_exhausted")
        self.assertEqual(ex[-1]["capped"], 1, ex)

    def test_sow_env_block_never_seals_or_spends_quota(self):
        """`sow`（plant_area）遇一次 `ui_modal` ⇒ 标记继承到底层、不封格、不吃配额；
        模态收掉后重跑同一批格子，当天照样种下去（task-15 §④）。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        w.dirt = {(60, 10)}
        w.fail_status[(60, 10)] = ["ui_modal"]
        run = make_run(w, target_days=1)
        run.worker = FarmWorker(FakeClient(w), log=lambda *_: None)
        plot = self._plot()
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)

        out = run._step_stage("plant_area", w.obs(), plot, rep)

        self.assertNotIn((60, 10), run.blocked, "模态挡住播种 ≠ 这一格种不下去")
        self.assertIsNone(run.tile_attempts.get((60, 10)), "环境挡路不该占播种配额")
        self.assertTrue(out.postcondition_met, out.reason)
        env = self._events(run, "env_fail")
        self.assertEqual(len(env), 1, run.entries)
        self.assertEqual(env[0]["statuses"], ["ui_modal"], env[0])
        self.assertEqual(len(self._events(run, "env_retry")), 1, run.entries)

    def test_water_env_block_never_spends_quota(self):
        """`water` 遇一次 `world_fading` ⇒ 不封格且 `tile_attempts` 不增（`_count_attempts` 无动作过滤）；
        重跑之后真的浇上（task-15 §④）。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        w.dirt = {(60, 10)}
        w.crops[(60, 10)] = {"watered": False, "ripe": False}
        w.fail_status[(60, 10)] = ["world_fading"]
        run = make_run(w, target_days=1)
        run.worker = FarmWorker(FakeClient(w), log=lambda *_: None)
        plot = self._plot()
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)

        out = run._step_stage("water_area", w.obs(), plot, rep)

        self.assertIsNone(run.tile_attempts.get((60, 10)), "渐黑挡住浇水不该吃掉本日配额")
        self.assertNotIn((60, 10), run.blocked)
        self.assertTrue(out.postcondition_met, out.reason)
        env = self._events(run, "env_fail")
        self.assertEqual(len(env), 1, run.entries)
        self.assertEqual(env[0]["statuses"], ["world_fading"], env[0])
        self.assertEqual(env[0]["stage"], "water_area", env[0])
        self.assertEqual(len(self._events(run, "env_retry")), 1, run.entries)


class TestTask11ModalGuard(unittest.TestCase):
    """task-11 模态守卫（真机：`LevelUpMenu` 把时钟冻住、整天静默卡死）。

    三条硬口径：
      * 普通 `LevelUpMenu`（`professionsToChoose` 空数组）⇒ dismiss，**可连关**；
      * `SaveGameMenu`/`NewDaySavingMenu`（新一天的自动存档）⇒ **只等不关**，超时如实停下；
      * `LevelUpMenu` 带职业候选（不可逆）或**读不到该字段**（旧 Mod / 未知）⇒ **绝不 dismiss**，
        当天不判 VERIFIED（用户 m03224 拍板了职业路线，静默丢档不可接受）。
    """

    def _run(self, w: FakeWorld) -> LongRun:
        run = make_run(w, target_days=1)
        run.worker = FakeWorker(w)
        run.client = FakeClient(w)
        return run

    @staticmethod
    def _rep() -> DayReport:
        return DayReport(day_key=("spring", 1, 9), started_at=0.0)

    @staticmethod
    def _events(run: LongRun, event: str) -> list[dict]:
        return [e for e in run.entries if e["event"] == event]

    def test_plain_levelup_dismissed_save_menu_only_waited(self):
        """普通升级关掉、随后自走的存档模态只等不关 ⇒ 世界回干净、`dismiss_calls == 1`。"""
        w = FakeWorld(weeds=0)
        w.ui_script = [
            {"activeMenu": "LevelUpMenu", "activeMenuText": "LevelUpMenu",
             "professionsToChoose": []},
            # `_autoGoneAfterPolls`：看两次之后就自己走完（复刻真机 SaveGameMenu 约 30s 自走）
            {"activeMenu": "SaveGameMenu", "activeMenuText": "SaveGameMenu",
             "_autoGoneAfterPolls": 2},
        ]
        run = self._run(w)
        rep = self._rep()

        obs, blocked = run._clear_modals(w.obs(), rep)

        self.assertFalse(blocked, rep.ended_reason)
        self.assertEqual(w.dismissed, ["LevelUpMenu"], "存档模态不许被 dismiss")
        self.assertEqual(w.dismiss_calls, 1)
        self.assertFalse(run._modal_info(obs)[0], "清完之后不该还有模态")
        self.assertEqual(run._modal_info(obs)[1], "")
        # 回执与判据都留痕：关一个、等走一个
        dis = self._events(run, "modal_dismissed")
        self.assertEqual(len(dis), 1, run.entries)
        self.assertEqual((dis[0]["kind"], dis[0]["menu"]), ("levelup", "LevelUpMenu"), dis[0])
        self.assertEqual(dis[0]["receipt"].get("ok"), True, dis[0])
        self.assertEqual(len(self._events(run, "modal_gone")), 1, run.entries)
        self.assertEqual(self._events(run, "modal_gone")[0]["menu"], "SaveGameMenu")

    def test_consecutive_levelups_are_both_dismissed(self):
        """多个技能同时升级会**连出** `LevelUpMenu` ⇒ 要一直关到干净。"""
        w = FakeWorld(weeds=0)
        w.ui_script = [
            {"activeMenu": "LevelUpMenu", "professionsToChoose": []},
            {"activeMenu": "LevelUpMenu", "professionsToChoose": []},
        ]
        run = self._run(w)
        rep = self._rep()

        obs, blocked = run._clear_modals(w.obs(), rep)

        self.assertFalse(blocked, rep.ended_reason)
        self.assertEqual(w.dismiss_calls, 2)
        self.assertEqual(w.dismissed, ["LevelUpMenu", "LevelUpMenu"])
        self.assertFalse(run._modal_info(obs)[0])

    def test_profession_choice_is_never_dismissed_and_day_is_not_verified(self):
        """职业选择弹窗（非空候选）⇒ 一次都不许 dismiss，当天 `blocked_modal` 且不判 VERIFIED。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        w.ui_script = [{"activeMenu": "LevelUpMenu", "activeMenuText": "LevelUpMenu",
                        "professionsToChoose": [0, 1]}]
        run = self._run(w)

        code = run.run()

        self.assertEqual(code, 1, "被模态挡住 ⇒ 当天没跨日，非 0 收尾")
        self.assertEqual(w.dismiss_calls, 0, "dismiss 职业弹窗 = 永久丢掉 Tiller/Artisan 选择")
        pend = self._events(run, "levelup_profession_pending")
        self.assertEqual(len(pend), 1, run.entries)
        self.assertEqual(pend[0]["ids"], [0, 1], pend[0])
        rep = run.days[0]
        self.assertEqual(rep.ended_by, ENDED_BY_MODAL, rep.ended_reason)
        self.assertFalse(rep.checks.get("no_blocking_modal", True), rep.checks)
        self.assertFalse(rep.verified, f"{rep.checks} notes={rep.notes}")

    def test_missing_professions_field_is_treated_as_unknown(self):
        """字段缺失（旧 Mod / 反射失败）⇒ 按未知处理：不 dismiss、journal 记 `..._unknown`、不 VERIFIED。"""
        w = FakeWorld(weeds=0)
        w.ui_script = [{"activeMenu": "LevelUpMenu", "activeMenuText": "LevelUpMenu"}]   # 没有该字段
        run = self._run(w)
        rep = self._rep()

        obs, blocked = run._clear_modals(w.obs(), rep)

        self.assertTrue(blocked)
        self.assertEqual(w.dismiss_calls, 0, "拿不准就不许动不可逆的东西")
        self.assertEqual(rep.ended_by, ENDED_BY_MODAL)
        unknown = self._events(run, "levelup_profession_unknown")
        self.assertEqual(len(unknown), 1, run.entries)
        self.assertEqual(unknown[0]["menu"], "LevelUpMenu")

    def test_question_modal_dismissed_with_no_key_injection(self):
        """开着提问（`dialogueIsQuestion`）⇒ 交给 Mod 的 dismiss（它的口径是"选否"）。"""
        w = FakeWorld(weeds=0)
        w.ui_script = [{"activeMenu": "DialogueBox", "dialogueIsQuestion": True,
                        "dialogueResponses": ["是", "否"]}]
        run = self._run(w)
        rep = self._rep()

        obs, blocked = run._clear_modals(w.obs(), rep)

        self.assertFalse(blocked, rep.ended_reason)
        self.assertEqual(w.dismiss_calls, 1)
        dis = self._events(run, "modal_dismissed")
        self.assertEqual(len(dis), 1, run.entries)
        self.assertEqual(dis[0]["kind"], "question", dis[0])

    def test_wait_only_modal_timeout_stops_the_day(self):
        """只等不关的模态永远不消失（存档卡住）⇒ journal `modal_timeout` + 当天停下等人。"""
        w = FakeWorld(weeds=0)
        w.ui_script = [{"activeMenu": "SaveGameMenu", "activeMenuText": "SaveGameMenu"}]
        run = self._run(w)
        run.modal_wait_timeout_s = 0.0           # 不真等：第一次轮询就判超时
        rep = self._rep()

        obs, blocked = run._clear_modals(w.obs(), rep)

        self.assertTrue(blocked)
        self.assertEqual(w.dismiss_calls, 0, "存档模态绝不许 dismiss（会打断存档）")
        self.assertEqual(rep.ended_by, ENDED_BY_MODAL)
        to = self._events(run, "modal_timeout")
        self.assertEqual(len(to), 1, run.entries)
        self.assertEqual(to[0]["menu"], "SaveGameMenu")


class _CountingClient(FakeClient):
    """数 `use_tool` 次数的假桥 —— task-28 要证明"持续 busy 下请求次数有界"。"""

    def __init__(self, world: FakeWorld) -> None:
        super().__init__(world)
        self.use_tool_calls = 0

    def use_tool(self, tile, *, tool=None, timeout_ms=None):
        self.use_tool_calls += 1
        return super().use_tool(tile, tool=tool, timeout_ms=timeout_ms)


class TestTask28BusySpin(unittest.TestCase):
    """task-28（deputy-lead N4-1）：`busy` 算环境挡路、`stale` 算没结论，且**必须有界**。

    `busy` = `MainThreadDispatcher.RejectBusy()`（"已有技能正在执行"，队列积压时零成本快速
    拒绝，**任何 skill 都可能拿到**）。它不是"这一格干不动"，所以不许封格；但它也**不占**
    `_count_attempts` 配额 ⇒ 若 Mod 一直回 busy，`_stage_tiles` 每轮都会把同一格重新选出来，
    一天耗在同一格上。所以 `_count_attempts` 按格记 `env_streak`：连续被挡超过
    `MAX_ENV_ATTEMPTS` 次后不再免费，按"没结论"占配额（`env_spin_capped` 留痕）。
    """

    @staticmethod
    def _plot() -> dict:
        return {"zone": "", "label": "", "anchor": [60, 10], "tiles": [(60, 10)], "note": ""}

    @staticmethod
    def _events(run: LongRun, event: str) -> list:
        return [e for e in run.entries if e["event"] == event]

    def _run(self, w: FakeWorld):
        """真 `FarmWorker` + 数数假桥；**同时挂到 factories 上**——`run()` 会用工厂重建
        `self.client`/`self.worker`，只赋值属性的话端到端用例会跑回 `FakeWorker`（task-28 踩过）。"""
        client = _CountingClient(w)
        worker = FarmWorker(client, log=lambda *_: None)
        run = make_run(w, target_days=1, max_days=1,
                       client_factory=lambda: client, worker_factory=lambda c: worker)
        run.worker = worker
        run.client = client
        return run, client

    def test_clear_busy_is_env_and_never_seals(self):
        """`clear` 一次 `busy` ⇒ 不封格、不吃配额，收掉挡路之后重跑同一批格子**真清掉**（task-15 §④）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.fail_status[(60, 10)] = ["busy"]          # 只挡第一次：重试就该做成
        run, client = self._run(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)

        out = run._step_stage("clear_area", w.obs(), self._plot(), rep)

        self.assertNotIn((60, 10), run.blocked, "队列积压不是这一格的属性")
        self.assertIsNone(run.tile_attempts.get((60, 10)), "环境挡路不占本日尝试配额")
        self.assertEqual(self._events(run, "blocked"), [], run.entries)
        env = self._events(run, "env_fail")
        self.assertEqual(len(env), 1, run.entries)
        self.assertEqual(env[0]["statuses"], ["busy"], env[0])
        self.assertNotIn((60, 10), w.blockers, "busy 只该延后，重试要真做掉")
        self.assertTrue(out.postcondition_met, out.reason)
        self.assertEqual(len(self._events(run, "env_retry")), 1, run.entries)

    def test_till_busy_is_env_not_sealed(self):
        """`till` 一次 `busy` ⇒ 不封格（否则 `_mark_blocked` 一道就把这一格判死一整天），重试后锄成 dirt。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        w.fail_status[(60, 10)] = ["busy"]
        run, client = self._run(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)

        out = run._step_stage("till_area", w.obs(), self._plot(), rep)

        self.assertNotIn((60, 10), run.blocked)
        self.assertIsNone(run.tile_attempts.get((60, 10)))
        env = self._events(run, "env_fail")
        self.assertEqual([e["statuses"] for e in env], [["busy"]], run.entries)
        self.assertIn((60, 10), w.dirt, "重试之后这一格该锄开了")
        self.assertTrue(out.postcondition_met, out.reason)

    def test_endless_busy_requests_are_bounded(self):
        """**防自旋**：永远回 busy ⇒ 请求次数有上界、如实 `capped`、全程不封格。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.fail_status[(60, 10)] = "busy"          # 常量：永远回 busy
        run, client = self._run(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        plot = self._plot()

        out = None
        for _ in range(10):                        # 有界循环：真无限的话这里也只会转 10 次
            out = run._step_stage("clear_area", w.obs(), plot, rep)
            if not run._stage_tiles("clear_area", w.obs(), plot):
                break

        # task-15 §④ 之后"一次 `_step_stage`"最多跑 `1 + max_env_retries` 轮（第 1 轮 + 2 轮重试），
        # 配额到 `MAX_TILE_ATTEMPTS` 后 `_stage_tiles` 就空了。实测这次循环：
        #   第 1 次 _step_stage = 3 次请求（env 免费 2 次 + 配额 1 次）
        #   第 2 次 _step_stage = 3 次请求（重试 2 轮 + 配额推到 4）⇒ 共 6 次后目标集合为空。
        per_call = 1 + run.max_env_retries
        bound = per_call * (1 + MAX_TILE_ATTEMPTS)
        self.assertEqual(client.use_tool_calls, 6,
                         f"持续 busy 下请求次数必须恰好有界（实测 {client.use_tool_calls}，上界 {bound}；"
                         f"免费 {MAX_ENV_ATTEMPTS} 次 + 配额 {MAX_TILE_ATTEMPTS} 次）")
        self.assertLessEqual(client.use_tool_calls, bound)
        self.assertEqual(run.tile_attempts.get((60, 10)), 4, "越界之后每次都占配额，直到封顶")
        self.assertEqual(len(self._events(run, "env_retry")), 4, run.entries)
        self.assertEqual(run.blocked, {}, "环境挡路永远不许写 blocked")
        self.assertEqual(self._events(run, "blocked"), [], run.entries)
        self.assertEqual(sum(int(s.get("proven_inert") or 0) for s in rep.stages), 0,
                         "没有 `proven_inert` ⇒ 没把环境问题当成'这一格干不动'")
        spin = self._events(run, "env_spin_capped")
        self.assertEqual(len(spin), 1, run.entries)
        self.assertEqual((spin[0]["tile"], spin[0]["limit"]), ([60, 10], MAX_ENV_ATTEMPTS), spin[0])
        self.assertFalse(out.postcondition_met, out.reason)
        self.assertEqual(out.terminal, "needs_review", out.reason)

    def test_endless_busy_full_run_is_not_verified(self):
        """端到端：`run()` 在持续 busy 下停下、非 0 收尾、当天 `verified=False`。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.fail_status[(60, 10)] = "busy"
        run, client = self._run(w)

        code = run.run()

        self.assertNotEqual(code, 0, "一天没做成 ⇒ 不许 0 收尾")
        bound = (1 + run.max_env_retries) * (1 + MAX_TILE_ATTEMPTS)
        self.assertLessEqual(client.use_tool_calls, bound,
                             f"请求次数必须有界，实测 {client.use_tool_calls}")
        self.assertEqual(run.blocked, {}, "环境挡路永远不许写 blocked")
        self.assertTrue(self._events(run, "env_retry"), run.entries)
        self.assertTrue(self._events(run, "env_spin_capped"), run.entries)
        self.assertFalse(run.days[0].verified, f"{run.days[0].checks} notes={run.days[0].notes}")


class TestTask15DayAccounting(unittest.TestCase):
    """task-15 §②/§③/§④：日级验收要看得见"未完成的阶段"，环境挡路不许把一整天判死。"""

    @staticmethod
    def _plot() -> dict:
        return {"zone": "", "label": "", "anchor": [60, 10], "tiles": [(60, 10)], "note": ""}

    @staticmethod
    def _events(run: LongRun, event: str) -> list:
        return [e for e in run.entries if e["event"] == event]

    def _run_with(self, w: FakeWorld):
        """真 `FarmWorker` + 数数假桥，并**同时挂到 factories**（`run()` 会重建，见 task-28 教训）。"""
        client = _CountingClient(w)
        worker = FarmWorker(client, log=lambda *_: None)
        run = make_run(w, target_days=1, max_days=1,
                       client_factory=lambda: client, worker_factory=lambda c: worker)
        run.worker = worker
        run.client = client
        return run, client

    def test_env_retry_exhausted_keeps_leftover_and_day_is_not_verified(self):
        """§④ 要求 2 + §② ：环境挡路重试满 2 轮还是没做成 ⇒ leftover>0 ⇒
        `no_unmet_stages=False`、`no_hard_failures=False`、当天不 VERIFIED，但**始终不封格**。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.fail_status[(60, 10)] = "world_fading"        # 一直渐黑：重试也做不成
        run, client = self._run_with(w)

        code = run.run()

        self.assertNotEqual(code, 0, "一格没清掉 ⇒ 不许 0 收尾")
        rep = run.days[0]
        self.assertFalse(rep.verified, f"{rep.checks} notes={rep.notes}")
        self.assertFalse(rep.checks["no_unmet_stages"], rep.checks)
        self.assertFalse(rep.checks["no_hard_failures"], rep.checks)
        self.assertEqual(run.blocked, {}, "环境挡路（渐黑）永远不许写成「这格干不动」")
        self.assertGreaterEqual(len(self._events(run, "env_retry")), 2,
                                "重试轮次要留痕（上限默认 2）")
        stages = [s for s in rep.stages if s["stage"] == "clear_area"]
        self.assertTrue(stages, rep.stages)
        self.assertGreater(stages[-1]["leftover"], 0, stages[-1])
        self.assertEqual(stages[-1]["proven_inert"], 0, stages[-1])

    def test_zero_target_day_still_verifies_with_no_unmet_stages(self):
        """§② ：只有"0 目标"的阶段（没种子又买不起）**不算未完成** ⇒ 当天仍可 VERIFIED。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.dirt = {(60, 10)}          # 地还在，但种子闸门把 till/plant 目标掐掉 ⇒ 0 目标阶段
        run, _client = self._run_with(w)

        code = run.run()

        rep = run.days[0]
        self.assertTrue(rep.checks["no_unmet_stages"], f"{rep.checks} stages={rep.stages}")
        self.assertTrue(rep.checks["no_hard_failures"], rep.checks)
        self.assertEqual(code, 0, f"没活可做而睡 ⇒ 该判达标：{rep.checks} notes={rep.notes}")
        self.assertTrue(rep.verified, f"{rep.checks} notes={rep.notes}")

    def test_env_retry_clears_the_blocking_modal(self):
        """§④ 要求 3：`ui_modal` 挡路时**确实调用了模态守卫**，收掉之后重跑同一批格子做成。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.fail_status[(60, 10)] = ["ui_modal"]
        w.ui_script = [{"activeMenu": "DialogueBox", "dialogueIsQuestion": True,
                        "dialogueResponses": ["是", "否"]}]
        run, _client = self._run_with(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)

        out = run._step_stage("clear_area", w.obs(), self._plot(), rep)

        self.assertEqual(w.dismiss_calls, 1, "模态挡路时要先收掉它，再重跑同一批格子")
        retry = self._events(run, "env_retry")
        self.assertEqual(len(retry), 1, run.entries)
        self.assertEqual((retry[0]["modal"], retry[0]["statuses"]),
                         ("DialogueBox", ["ui_modal"]), retry[0])
        self.assertNotIn((60, 10), w.blockers, "收掉模态之后这一格该清掉")
        self.assertTrue(out.postcondition_met, out.reason)
        self.assertEqual(rep.stages[-1]["failed"], 0, rep.stages[-1])


class TestTask19WaterEvidence(unittest.TestCase):
    """task-19：日级浇水证据 `checks.watered_outdoor` + `day_end.final_water` 的双口径。

    真值只有两处：`farm.dryCrops`（全农场 `crop!=null && !HoeDirt.isWatered()`）或**当天最后一张
    `isOutdoorFarm==true` 快照**的逐格 `watered`。窗口计数在室内（FarmHouse）恒 0 —— run2 的
    `checks.crops_watered=true` 就是这么白过的，所以它只作旁证、不算证据。
    """

    def _run(self, w: FakeWorld) -> LongRun:
        return make_run(w, target_days=1, max_days=1)

    @staticmethod
    def _events(run: LongRun, event: str) -> list:
        return [e for e in run.entries if e["event"] == event]

    def _with_crop(self, *, watered: bool) -> FakeWorld:
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.dirt.add((60, 10))
        w.crops[(60, 10)] = {"ripe": False, "watered": watered}
        # 【task-96】本类专测**窗口口径/退回路径**：显式关掉 farm 证据（默认的
        # `_EMPTY_FARM_SCAN` 是"桥在线、农场级无事可报"，会让 `_water_evidence` 走 farm 口径）。
        w.farm = {}
        return w

    @staticmethod
    def _indoor(w: FakeWorld) -> dict:
        """玩家回到 FarmHouse：窗口 tiles/crops 恒 0（run2 日终的真实处境）。"""
        obs = w.obs()
        obs["location"] = {"name": "FarmHouse", "isOutdoorFarm": False, "tiles": [],
                           "tillable": [], "furniture": [], "doors": []}
        return obs

    def test_indoor_final_snapshot_does_not_white_pass(self):
        """① 最后一张是室内快照、户外快照里有未浇作物 ⇒ `watered_outdoor=False`（**不许白过**）。"""
        w = self._with_crop(watered=False)
        run = self._run(w)

        ok, info = run._water_evidence(self._indoor(w), outdoor_obs=w.obs(),
                                       outdoor_t=12.5, outdoor_name="Farm")

        self.assertFalse(ok, info)
        self.assertEqual(info["scope"], "window", info)
        self.assertEqual((info["crops"], info["dry"]), (1, 1), info)
        self.assertGreater(info["tiles"], 0, info)

    def test_all_watered_is_true(self):
        """② 全部浇过 ⇒ True（窗口口径也要有 coverage：`tiles>0`）。"""
        w = self._with_crop(watered=True)
        run = self._run(w)

        ok, info = run._water_evidence(self._indoor(w), outdoor_obs=w.obs(),
                                       outdoor_t=12.5, outdoor_name="Farm")

        self.assertTrue(ok, info)
        self.assertEqual(info["scope"], "window", info)
        self.assertEqual((info["crops"], info["dry"]), (1, 0), info)
        self.assertGreater(info["tiles"], 0, info)

    def test_farm_incomplete_or_old_mod_falls_back_to_window(self):
        """③ `farm.complete==false`（扫没扫完）或旧 Mod 没有 `dryCrops` ⇒ 退回窗口口径，
        **绝不采信 farm 的 0**。"""
        w = self._with_crop(watered=False)
        run = self._run(w)
        obs = w.obs()
        obs["farm"] = {"loaded": True, "complete": False, "crops": 5, "dryCrops": 0,
                       "unwateredCrops": 5, "hoeDirt": 5}

        ok, info = run._water_evidence(obs, outdoor_obs=w.obs(), outdoor_t=3.0, outdoor_name="Farm")

        self.assertFalse(ok, "complete=false 时 dryCrops=0 是「没扫完」，不是「没干格」")
        self.assertEqual(info["scope"], "window", info)
        self.assertGreater(info["tiles"], 0, info)
        # 旧 Mod（没有 dryCrops 字段）同理
        obs["farm"] = {"loaded": True, "complete": True, "crops": 5, "unwateredCrops": 5, "hoeDirt": 5}
        ok2, info2 = run._water_evidence(obs, outdoor_obs=w.obs(), outdoor_t=3.0, outdoor_name="Farm")
        self.assertFalse(ok2, info2)
        self.assertEqual(info2["scope"], "window", info2)

    def test_no_outdoor_snapshot_is_false_never_default_true(self):
        """④ 没有任何户外快照 ⇒ 如实 False + notes 说明（**禁止默认 true**）；
        `farm.loaded==false`（Mod 未加载时 `complete=true` 且全 0）同样不是证据。"""
        w = self._with_crop(watered=True)      # 作物其实浇好了，但没有户外快照 ⇒ 依然不许自称浇过
        run = self._run(w)

        ok, info = run._water_evidence(self._indoor(w))

        self.assertFalse(ok, info)
        self.assertEqual(info["scope"], "window", info)
        self.assertEqual((info["tiles"], info["dry"]), (0, None), info)
        self.assertIn("没有任何 location.isOutdoorFarm==true 的快照", info["note"])
        # farm 未加载：complete=true 但 loaded=false、全 0 ⇒ 不许当成"没干格"（户外快照里明明有未浇作物）
        w2 = self._with_crop(watered=False)
        run2 = self._run(w2)
        obs = w2.obs()
        obs["farm"] = {"loaded": False, "complete": True, "crops": 0, "dryCrops": 0, "hoeDirt": 0}
        ok2, info2 = run2._water_evidence(obs, outdoor_obs=w2.obs(), outdoor_t=1.0, outdoor_name="Farm")
        self.assertFalse(ok2, "farm 没加载时的 0 不是证据")
        self.assertEqual(info2["scope"], "window", info2)

    def test_empty_outdoor_window_is_false_never_true(self):
        """④b NIT-1：户外快照存在但窗口 **0 格** ⇒ 逐格判据 `len(dry_t)==0` 恒真，
        必须如实 False + notes 说明（空窗口不是"全浇过"的证据）。"""
        w = self._with_crop(watered=True)
        run = self._run(w)
        obs = w.obs()
        obs["location"] = {"name": "Farm", "isOutdoorFarm": True, "tiles": [],
                           "tillable": [], "furniture": [], "doors": []}
        obs["farm"] = {"loaded": True, "complete": False, "crops": 0, "hoeDirt": 0}

        ok, info = run._water_evidence(obs, outdoor_obs=obs, outdoor_t=9.0, outdoor_name="Farm")

        self.assertFalse(ok, "0 格窗口下 dry 必然为 0，不许据此自称浇过")
        self.assertEqual(info["scope"], "window", info)
        self.assertEqual((info["tiles"], info["crops"], info["dry"]), (0, 0, 0), info)
        self.assertIn("没有任何户外窗口观测格", info["note"])

    def test_farm_scope_uses_dry_crops(self):
        """⑤ `farm.complete==true` ⇒ 以 `dryCrops` 为唯一证据（`scope=="farm"`、
        `tiles=farm.hoeDirt`、`crops=farm.crops`）。"""
        w = self._with_crop(watered=False)
        run = self._run(w)
        obs = w.obs()
        obs["farm"] = {"loaded": True, "complete": True, "crops": 5, "dryCrops": 3,
                       "unwateredCrops": 5, "hoeDirt": 5}

        ok, info = run._water_evidence(obs, outdoor_obs=w.obs(), outdoor_t=5.0, outdoor_name="Farm")

        self.assertFalse(ok, info)
        self.assertEqual(info["scope"], "farm", info)
        self.assertEqual((info["tiles"], info["crops"], info["dry"]), (5, 5, 3), info)
        # dryCrops 归零 ⇒ True（即使 `unwateredCrops` 还是 5：那个不是干格数）
        obs["farm"] = dict(obs["farm"], dryCrops=0)
        ok2, info2 = run._water_evidence(obs, outdoor_obs=w.obs(), outdoor_t=5.0, outdoor_name="Farm")
        self.assertTrue(ok2, info2)
        self.assertEqual((info2["scope"], info2["dry"]), ("farm", 0), info2)

    def test_day_end_carries_watered_outdoor_and_final_water(self):
        """端到端：`day_end` 事件里 `checks.watered_outdoor` 与 `final_water` 的键名逐字对齐
        `tools\\verify-run3.py` 的闸门（farm 口径要 `tiles>0/crops>0/dry==0`）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {"loaded": True, "complete": True, "crops": 25, "dryCrops": 0,
                  "unwateredCrops": 25, "hoeDirt": 25}
        client = _CountingClient(w)
        worker = FarmWorker(client, log=lambda *_: None)
        run = make_run(w, target_days=1, max_days=1,
                       client_factory=lambda: client, worker_factory=lambda c: worker)
        run.worker = worker
        run.client = client

        run.run()

        rep = run.days[0]
        self.assertIs(rep.checks["watered_outdoor"], True, rep.checks)
        fw = rep.final_water
        self.assertTrue({"t", "location", "tiles", "crops", "dry", "scope"} <= set(fw), fw)
        self.assertEqual((fw["scope"], fw["tiles"], fw["crops"], fw["dry"]), ("farm", 25, 25, 0), fw)
        self.assertNotIn("unwateredCrops", fw, "两套仪器不许混列")
        end = self._events(run, "day_end")[-1]
        self.assertEqual(end["final_water"], fw)
        self.assertIs(end["checks"]["watered_outdoor"], True, end["checks"])


class TestTask32PlotsCap(unittest.TestCase):
    """task-32：作业区配额触顶**不许当收工理由**（真机彩排 09:40、体力 144.7/270 就回家睡）。

    真机形态：`plots_today >= max_plots_per_day` ⇒ 旧的 `_ensure_plot` 直接 return None ⇒
    `_do_sleep("no_plot")`，而同一时刻 `work_reasons` 还在说"还有地要清/开/种"。
    新语义：配额只限制"换到**新的**作业区"，不限制"当天继续干活"。
    """

    @staticmethod
    def _events(run, event):
        return [e for e in run.entries if e["event"] == event]

    def test_capped_with_work_in_zone_keeps_the_day_going(self):
        """触顶（`max_plots_per_day=0` 等价于"一片新地都不许开"）但区内还有活 ⇒ 当天照常做完。"""
        w = FakeWorld(weeds=4, seeds=10, money=500)
        run = make_run(w, target_days=1, max_plots_per_day=0)
        code = run.run()
        rep = run.days[0]

        self.assertEqual(code, 0, run.logs)
        # 活是真干完的（不是"睡过去"）：草清掉、25 格全种下
        self.assertEqual(w.blockers, {}, run.logs)
        self.assertEqual(len(w.crops), 25, run.logs)
        # 触顶留痕：每天最多一条，且**不计入换区配额**
        capped = self._events(run, "plots_capped")
        self.assertEqual(len(capped), 1, [e for e in run.entries if e["event"].startswith("plot")])
        self.assertEqual(capped[0]["plots_today"], 0, capped[0])
        self.assertEqual(capped[0]["limit"], 0, capped[0])
        self.assertEqual(rep.plots, [], "触顶后不该再有新作业区")
        self.assertTrue(any("已开满" in str(n) for n in rep.notes), rep.notes)
        # 收工理由必须是正当三种之一 —— 而 `no_plot` 已经不在白名单里
        self.assertEqual(rep.ended_by, "sleep")
        self.assertIn(rep.ended_reason.split(":", 1)[0], ("night", "stamina", "no_work"),
                      rep.ended_reason)
        self.assertTrue(rep.checks["day_justified"], rep.checks)
        self.assertTrue(rep.verified, f"{rep.checks}｜{rep.notes}")
        self.assertEqual(set(rep.stages_seen), {"clear_area", "till_area", "plant_area"})

    def test_capped_and_no_work_anywhere_still_sleeps_no_work(self):
        """触顶 + 真的没活 + 守卫放行 ⇒ 仍要能收工，且理由是 `no_work`（不是 `no_plot`）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        # 真机 `FarmScan` 每次扫描都发 `farm`（0 作物 ⇒ `dryCrops=0` ⇒ 浇水证据成立）；
        # 不放这块的话本用例会因为"缺 farm 级浇水证据"被 task-19 的闸门判 needs_review，
        # 而这里要钉的是"触顶 + 没活 ⇒ 仍然正当收工"，与浇水无关。
        w.farm = {"loaded": True, "complete": True, "crops": 0, "dryCrops": 0,
                  "unwateredCrops": 0, "hoeDirt": 0}
        run = make_run(w, target_days=1, max_plots_per_day=0)
        obs = w.obs()
        rep0 = DayReport(day_key=("spring", 1, 6), started_at=0.0)
        self.assertIsNone(run._ensure_plot(obs, rep0), "没有有活的候选区 ⇒ 必须返回 None 而不是硬撑")

        self.assertEqual(run.run(), 0, run.logs)
        rep = run.days[0]
        self.assertEqual(rep.ended_by, "sleep")
        self.assertTrue(rep.ended_reason.startswith("no_work"), rep.ended_reason)
        self.assertTrue(rep.checks["day_justified"], rep.checks)
        self.assertTrue(rep.verified, f"{rep.checks}｜{rep.notes}")

    def test_work_outside_any_zone_is_done_instead_of_sleeping_no_plot(self):
        """区里一格目标都拿不到 + 守卫说"有作物没浇水" ⇒ **不许 `no_plot` 收工**：拿"活所在的
        格子"当收尾作业区把水浇掉（journal `work_spot`，不计入换区配额）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        t = (70, 20)
        w.dirt.add(t)                     # ⚠ 必须同时进 dirt，否则这一格不进观测
        w.crops[t] = {"watered": False, "ripe": False}
        run = make_run(w, target_days=1, max_plots_per_day=0)
        # 钉住前提："候选作业区一个都拿不出活"（真机形态是活落在 `fields` 切不出来的角落）
        run._plot_candidates = lambda obs: []
        self.assertIsNone(run._ensure_plot(w.obs(), DayReport(day_key=("spring", 1, 6), started_at=0.0)))
        self.assertIsNotNone(run._work_spot_plot(w.obs()))

        self.assertEqual(run.run(), 0, run.logs)
        rep = run.days[0]
        # ⚠ `w.sleep()` 会把 `watered` 清零，所以不能直接看 `w.crops[t]["watered"]`；
        # 看"睡前那一刻"的记录（既有 `unwatered_at_sleep` 口径）与当天的浇水证据。
        self.assertEqual(w.unwatered_at_sleep, [0], "睡前那一刻这 1 格作物已经浇过了")
        self.assertIs(rep.checks["watered_outdoor"], True, rep.checks)
        self.assertNotIn("no_plot", rep.ended_reason)
        self.assertEqual(rep.ended_by, "sleep")
        self.assertTrue(rep.checks["day_justified"], rep.checks)
        spots = self._events(run, "work_spot")
        self.assertTrue(spots, [e["event"] for e in run.entries])
        # `work_spot` 记的是这一片收尾活里有几格（= 那 1 格作物），且**不计入换区配额**
        self.assertEqual(spots[0]["tiles"], 1, spots[0])
        self.assertEqual(rep.plots, [], "收尾活不是新作业区")

    def test_no_plot_is_not_a_justified_reason(self):
        """白名单钉死：`no_plot` 永远不是正当收工理由（真机彩排就是被它洗白的）。"""
        self.assertNotIn("no_plot", JUSTIFIED_END_REASONS)
        self.assertEqual(set(JUSTIFIED_END_REASONS), {"night", "stamina", "no_work"})
        self.assertFalse(is_justified_end("sleep", "no_plot:找不到有活的作业区"))
        self.assertTrue(is_justified_end("sleep", "no_work:确实找不到可做的活"))
        self.assertTrue(is_justified_end("sleep", "night:已经到点了"))
        self.assertFalse(is_justified_end("sleep_failed", "no_work:…"))
        self.assertFalse(is_justified_end("stuck", "no_work:…"))


class MorningIndoorWorld(FakeWorld):
    """睡完**醒在屋里**的假世界（run3 真实现场：`final.location='FarmHouse'`、`tile=[9,9]`）。

    跨日把玩家丢回 FarmHouse：室内窗口一格都看不见（`tiles=[]`/`tillable=[]`），而 `farm`
    块仍是全场口径（`dryCrops` = 假世界里没浇的作物数）—— 正是 run3 里"窗口说没活、
    farm 说还有 33 格干作物"的那对矛盾读数。
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.goto_calls = 0

    def sleep(self):
        st = super().sleep()
        self.location, self.is_outdoor_farm = "FarmHouse", False
        self.player_tile = [9, 9]
        return st

    def obs(self):
        crops = list(self.crops.values())
        dry = sum(1 for c in crops if not c.get("watered"))
        ripe = sum(1 for c in crops if c.get("ripe"))
        # 真机 `FarmScan` 的 farm 口径：全场作物（与窗口无关）。`unwateredCrops` 数的是
        # `NeedsWatering`、**不是**干格数，所以只信 `dryCrops`/`ripeCrops`。
        self.farm = {"loaded": True, "complete": True, "crops": len(crops),
                     "dryCrops": dry, "ripeCrops": ripe,
                     "unwateredCrops": dry, "hoeDirt": len(self.dirt)}
        o = super().obs()
        if not self.is_outdoor_farm:
            o["location"]["tiles"] = []
            o["location"]["tillable"] = []
            o["location"]["furniture"] = []
        return o


class MorningIndoorWorker(FakeWorker):
    """`ensure_location` 真的换地点（`FakeWorker` 的版本是空动作，测不了"回农场"）。"""

    def ensure_location(self, name, *, tile=None, timeout_ms=30000):
        self.w.goto_calls += 1
        self.w.location = str(name)
        self.w.is_outdoor_farm = (str(name) == "Farm")
        self.w.player_tile = [62, 14]
        return StepResult("move_to_location", ok=True, reason=f"回到 {name}")


class TestMorningIndoor(unittest.TestCase):
    """run3 真 bug：睡醒在 FarmHouse ⇒ 窗口 `crops=0` ⇒ 判 `no_work`，连睡 4 天。

    **变异自检**（临时把 A 或 B 单独关掉，本类必须红；脚本 `scratch\\_t32b_mutate.py`，实测 2026-10-13）：
      * 变异 A（`_ensure_on_farm` 改成直接 `return obs`）⇒ `test_wakes_up_indoor_and_goes_back_to_the_farm`
        红：`run.run()` 返回 1（`AssertionError: 1 != 0`）—— 第 2 天人在屋里，守卫因 farm 口径
        "还有活"否决了睡觉，而 `_ensure_plot`/`_work_spot_plot` 在室内窗口拿不出任何目标 ⇒
        当天以 `stuck:守卫说还有活（…）但没有任何作业区拿得出目标` 收尾、不可验证（`goto_calls==0`）。
      * 变异 B（`_farm_scope_work` 恒 `None`）⇒ `test_no_work_is_never_asserted_from_an_indoor_window`
        红：`sleep_guard` 直接放行 `(True, 'no_work', '确实找不到可做的活…')` —— 这就是 run3
        连睡 4 天的判据本身。
    """

    def _two_days(self):
        w = MorningIndoorWorld(weeds=0, seeds=0, money=0)
        t = (61, 10)
        w.dirt.add(t)                       # ⚠ 必须同时进 dirt 才进观测
        w.crops[t] = {"watered": False, "ripe": False}
        run = make_run(w, target_days=2, max_days=3,
                       client_factory=lambda: FakeClient(w),
                       worker_factory=lambda c: MorningIndoorWorker(w))
        return w, run

    def test_wakes_up_indoor_and_goes_back_to_the_farm(self):
        w, run = self._two_days()
        code = run.run()
        reps = run.days
        self.assertEqual(code, 0, run.logs)
        self.assertEqual(len(reps), 2, [r.day_text for r in reps])
        # ① 不许出现"`no_work` 却还有干作物"的一天（run3 的连睡就是这条被违反）
        for rep in reps:
            if rep.ended_reason.split(":", 1)[0] == "no_work":
                self.assertEqual(int((rep.final_water or {}).get("dry") or 0), 0,
                                 f"{rep.day_text}：{rep.ended_reason}｜{rep.final_water}")
        # ② 跨日后必须真的回过农场（worker 计数 + journal）
        self.assertGreaterEqual(w.goto_calls, 1, run.logs)
        self.assertTrue([e for e in run.entries
                         if e["event"] == "goto_farm" and e.get("where") == "day_start"], run.entries)
        # ③ 两天都 VERIFIED（第 2 天正是"睡醒在屋里"那一天）
        self.assertTrue(all(r.verified for r in reps), [r.checks for r in reps])

    def test_no_work_is_never_asserted_from_an_indoor_window(self):
        """C：人在室内 + farm 说还有干作物 ⇒ `sleep_guard` 必须否决，不许放行 `no_work`。"""
        w, run = self._two_days()
        run.worker = MorningIndoorWorker(w)
        w.location, w.is_outdoor_farm = "FarmHouse", False
        obs = w.obs()                        # 室内窗口（tiles=[]）、farm.dryCrops=1
        self.assertFalse(run._is_farm(obs))
        allow, code, text = run.sleep_guard(obs)
        self.assertFalse(allow, (allow, code, text))
        self.assertEqual(code, "keep_working")
        self.assertIn("人在室内", text)
        self.assertIn("先回农场", text)
        self.assertTrue(run.work_reasons(obs), run.work_reasons(obs))   # B：farm 口径也算"有活"
        self.assertEqual(run._farm_scope_work(obs), (1, 0), obs.get("farm"))


class TestTask41EventBlocked(unittest.TestCase):
    """task-41：`ui.eventUp=true`（游戏事件/剧情对话）**一律硬停**，绝不代游戏做选择。

    真机证据（2026-10-13 19:16–19:19，run4 起跑前）：农场里弹出流浪宠物认养事件
    （`eventUp=true`、`DialogueBox`「Hello Jay!」、`worldAdvancing=false` 135 秒零推进）。
    Mod 用游戏自己的 `closeDialogue()` 关掉第一句时，事件反而把它算作"这句说完了"而**推进**
    一句；事件里带 `Yes/No` 时还会被 `ModalDismiss` 默认选"否" —— 两条都不可逆、账本看不出来。
    ⇒ 政策：`eventUp=true` 时 **一次都不动手**，当天 `blocked_event` 停下等人。
    `eventUp=false` 的老四类行为（提问/普通对话/LevelUpMenu/存档只等）一字不改。

    变异自检（2026-10-13，`%TEMP%\\t41_mutate.py`）：去掉 `eventUp` 判断（`_event_blocked` 直接
    `(obs, False)`）⇒ 本类 `test_event_dialogue_…` 与 `test_event_question_…` **两条皆红**；
    基线（无变异）7/7 绿。
    """

    def _run(self, w: FakeWorld) -> LongRun:
        run = make_run(w, target_days=1)
        run.worker = FakeWorker(w)
        run.client = FakeClient(w)
        return run

    @staticmethod
    def _rep() -> DayReport:
        return DayReport(day_key=("spring", 1, 9), started_at=0.0)

    @staticmethod
    def _events(run: LongRun, event: str) -> list[dict]:
        return [e for e in run.entries if e["event"] == event]

    def test_event_dialogue_is_never_dismissed_and_day_is_not_verified(self):
        """①`eventUp=true` + 普通 DialogueBox ⇒ 不 dismiss、`blocked_event`、`run()` 非 0。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        w.ui_script = [{"activeMenu": "DialogueBox", "activeMenuText": "Hello Jay!",
                        "dialogueResponses": [], "dialogueIsQuestion": False, "eventUp": True}]
        run = self._run(w)

        code = run.run()

        self.assertEqual(code, 1, run.logs)
        self.assertEqual(w.dismiss_calls, 0, "游戏事件一次都不许关（关框=替游戏做选择）")
        ev = self._events(run, "event_blocked")
        self.assertEqual(len(ev), 1, run.entries)
        self.assertEqual((ev[0]["activeMenu"], ev[0]["activeMenuText"]),
                         ("DialogueBox", "Hello Jay!"), ev[0])
        self.assertEqual(ev[0]["dialogueResponses"], [], ev[0])
        self.assertEqual(ev[0]["dialogueIsQuestion"], False, ev[0])
        self.assertIsNotNone(ev[0]["tile"], ev[0])
        self.assertIsInstance(ev[0]["timeOfDay"], int, ev[0])
        self.assertIsNotNone(ev[0]["worldSeq"], ev[0])
        rep = run.days[0]
        self.assertEqual(rep.ended_by, ENDED_BY_EVENT, rep.ended_reason)
        self.assertFalse(rep.checks.get("no_blocking_modal", True), rep.checks)
        self.assertFalse(rep.verified, f"{rep.checks} notes={rep.notes}")
        self.assertTrue(any("eventUp" in n for n in rep.notes), rep.notes)
        # `run()` 早退：不许对同一天再来一遍（同一条 journal 会写两次）
        self.assertEqual(len(run.days), 1, [d.day_text for d in run.days])

    def test_event_question_is_never_answered(self):
        """②`eventUp=true` + **提问**对话 ⇒ 同样一次都不许碰（否则被默认选"否"）。"""
        w = FakeWorld(weeds=0)
        w.ui_script = [{"activeMenu": "DialogueBox", "activeMenuText": "领养这只宠物吗？",
                        "dialogueIsQuestion": True, "dialogueResponses": ["Yes", "No"],
                        "eventUp": True}]
        run = self._run(w)
        rep = self._rep()

        obs, blocked = run._clear_modals(w.obs(), rep)

        self.assertTrue(blocked)
        self.assertEqual(w.dismiss_calls, 0, "事件里的提问绝不许代选（Mod 口径是选否）")
        self.assertEqual(rep.ended_by, ENDED_BY_EVENT)
        self.assertEqual(len(self._events(run, "event_blocked")), 1, run.entries)
        self.assertEqual(len(self._events(run, "modal_dismissed")), 0, run.entries)
        self.assertTrue(run._modal_info(obs)[0], "事件还开着：不许假装清干净了")

    def test_eventup_false_plain_dialogue_still_dismissed_once(self):
        """③回归：`eventUp=false` 的普通 DialogueBox 仍按 cancel 关掉一次。"""
        w = FakeWorld(weeds=0)
        w.ui_script = [{"activeMenu": "DialogueBox", "activeMenuText": "普通对话",
                        "eventUp": False}]
        run = self._run(w)
        rep = self._rep()

        obs, blocked = run._clear_modals(w.obs(), rep)

        self.assertFalse(blocked, rep.ended_reason)
        self.assertEqual(w.dismiss_calls, 1)
        self.assertEqual(len(self._events(run, "event_blocked")), 0, run.entries)

    def test_eventup_false_sleep_question_still_goes_the_old_way(self):
        """④回归：`eventUp=false` + 睡觉提问 ⇒ 仍走 Mod 的"选否"口径（老行为不改）。"""
        w = FakeWorld(weeds=0)
        w.ui_script = [{"activeMenu": "DialogueBox", "activeMenuText": "上床睡觉？",
                        "dialogueIsQuestion": True, "dialogueResponses": ["是", "否"],
                        "eventUp": False}]
        run = self._run(w)
        rep = self._rep()

        obs, blocked = run._clear_modals(w.obs(), rep)

        self.assertFalse(blocked, rep.ended_reason)
        self.assertEqual(w.dismiss_calls, 1)
        dis = self._events(run, "modal_dismissed")
        self.assertEqual(len(dis), 1, run.entries)
        self.assertEqual(dis[0]["kind"], "question", dis[0])


class _IndoorNoFarmEvidenceWorld(FakeWorld):
    """室内 + `farm` 证据不可用（`complete=false`/`loaded=false`）的假世界（task-41 NIT-2）。

    室内窗口按真机口径**是空的**（`location.tiles/tillable/furniture` 全清）⇒ `_ensure_plot`/
    `_work_spot_plot`/`_near_player_plot` 都拿不出目标；`farm` 块又不可用 ⇒ 判据只能 fail-closed。
    复刻 run3 那 4 天：若 `sleep_guard` 退回窗口口径，就会放行 `no_work` 连睡。
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.farm = {"loaded": False, "complete": False, "crops": 0,
                     "dryCrops": None, "ripeCrops": None}

    def obs(self) -> dict:
        obs = super().obs()
        obs["player"]["location"] = "FarmHouse"
        obs["location"]["name"] = "FarmHouse"
        obs["location"]["isOutdoorFarm"] = False
        obs["location"]["tiles"] = []
        obs["location"]["tillable"] = []
        obs["location"]["furniture"] = []
        return obs


class TestTask41FarmEvidenceFailClosed(unittest.TestCase):
    """task-41 NIT-2：室内 + farm 证据不可用 ⇒ **fail-closed**，绝不放行 `no_work`。

    为什么必须这么严（Lead rev4 §10 的硬要求）：`_run_day` 里 `why` 是
    `("no_work" if not reasons else "stuck:守卫说还有活（…）")` ⇒ 只要 `work_reasons()` **没给出**
    这条理由，`reasons` 为空就会落回 `no_work`，run3 连睡 4 天的路径原地复活（改了等于没改）。
    有界性**不靠** `idle_rounds`：`spot is None` 那条单次分支一天只走一次、不空转。

    变异自检（2026-10-13，`%TEMP%\\t41_mutate.py`）：m41a（`sleep_guard` 把 fail-closed 退回
    `no_work` 放行）与 m41b（`_farm_scope_work` 恒 None 且 `work_reasons()` 不加那条理由）
    ⇒ 本类**两条用例皆红**（后者正是 rev4 §10 说的"只改 sleep_guard 等于没改"）；基线 7/7 绿。
    """

    @staticmethod
    def _events(run: LongRun, event: str) -> list[dict]:
        return [e for e in run.entries if e["event"] == event]

    def test_indoor_without_farm_evidence_never_says_no_work(self):
        w = _IndoorNoFarmEvidenceWorld(weeds=0, seeds=0, money=0)
        run = make_run(w, target_days=1)
        run.worker = FakeWorker(w)
        run.client = FakeClient(w)
        obs = w.obs()

        allow, code, text = run.sleep_guard(obs)

        self.assertFalse(allow, (allow, code, text))
        self.assertEqual(code, "keep_working")
        self.assertNotEqual(code, "no_work")
        self.assertIn("farm 证据不可用", text)
        # `work_reasons()` 也必须给出这条（否则 `_run_day` 的 `why` 会落回 `no_work`）
        reasons = run.work_reasons(obs)
        self.assertTrue(any("farm 证据不可用" in r for r in reasons), reasons)
        ev = self._events(run, "farm_evidence_unavailable")
        self.assertEqual(len(ev), 1, run.entries)
        self.assertEqual((ev[0]["complete"], ev[0]["loaded"], ev[0]["location"]),
                         (False, False, "FarmHouse"), ev[0])

    def test_day_never_ends_with_no_work_when_farm_evidence_is_missing(self):
        """整日跑完：`ended_reason` 前缀**不是** `no_work`（m41a/m41b 两态变异都该在这条上红）。"""
        w = _IndoorNoFarmEvidenceWorld(weeds=0, seeds=0, money=0)
        run = make_run(w, target_days=1, max_days=1)

        code = run.run()

        self.assertEqual(code, 1, run.logs)
        rep = run.days[0]
        self.assertNotEqual(rep.ended_reason.split(":", 1)[0], "no_work",
                            f"run3 连睡路径复活：{rep.ended_reason}｜notes={rep.notes}")
        self.assertFalse(rep.checks.get("day_justified", True),
                         f"白天被当成正当收工了：{rep.ended_reason}｜{rep.checks}")
        self.assertFalse(rep.verified, f"{rep.checks} notes={rep.notes}")
        self.assertEqual(len(self._events(run, "farm_evidence_unavailable")), 1, run.entries)


class FlipIndoorWorld(FakeWorld):
    """`_prepare` 期间"人在农场"（好让它别失败），日循环一开始就翻成室内（复刻 run3 睡醒现场）。"""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.obs_calls = 0

    def obs(self) -> dict:
        self.obs_calls += 1
        if self.obs_calls > 1:            # 第 1 次是 `_prepare()` 的观测
            self.location = "FarmHouse"
            self.is_outdoor_farm = False
        return super().obs()


class _CannotGoHomeWorker(FakeWorker):
    """`ensure_location` 恒失败（回不去农场）+ `run_stage` 一格都动不了（世界指纹不变）。

    后者让日循环走到 `idle_rounds>=3` ⇒ 当天如实 `stuck`（task-41 NIT-1 的"动作数有界"）。
    """

    def __init__(self, world: FakeWorld) -> None:
        super().__init__(world)
        self.goto_calls = 0

    def ensure_location(self, name, *, tile=None, timeout_ms=30000):
        self.goto_calls += 1
        return StepResult("move_to_location", ok=False, code="timeout",
                          reason=f"去 {name} 失败：timeout（本跳试过的格子：(64,14)=unreachable）")

    def run_stage(self, stage, tiles, *, min_stamina=12.0, max_steps=200):
        steps = [StepResult(STAGE_ACTION.get(stage, stage), tuple(t), ok=False, code="failed",
                            reason="假世界：这一格干不动") for t in tiles]
        return StageResult(stage=stage, steps=steps, stopped="", stopped_reason="")


class TestTask41CannotGoHome(unittest.TestCase):
    """task-41 NIT-1：把"回不去农场"分支固化成用例（不许只靠探针）。"""

    @staticmethod
    def _events(run: LongRun, event: str) -> list[dict]:
        return [e for e in run.entries if e["event"] == event]

    def test_cannot_go_home_ends_stuck_with_one_failed_goto(self):
        w = FlipIndoorWorld(weeds=4, seeds=10, money=500)
        # farm 证据可用（不是 NIT-2 那条路）：这里要测的是"回不去农场 + 干不动 ⇒ 如实 stuck"
        w.farm = {"loaded": True, "complete": True, "crops": 0, "dryCrops": 0,
                  "ripeCrops": 0, "unwateredCrops": 0, "hoeDirt": 0}
        run = make_run(w, target_days=1, max_days=1,
                       client_factory=lambda: FakeClient(w),
                       worker_factory=lambda c: _CannotGoHomeWorker(w))

        code = run.run()

        self.assertEqual(code, 1, run.logs)
        rep = run.days[0]
        goto = self._events(run, "goto_farm")
        self.assertEqual(len(goto), 1, run.entries)
        self.assertEqual(goto[0].get("where"), "day_start", goto[0])
        self.assertFalse(goto[0]["ok"], goto[0])
        self.assertEqual(goto[0]["code"], "timeout", goto[0])
        self.assertTrue(any("回不去 Farm" in n for n in rep.notes), rep.notes)
        self.assertEqual(rep.ended_by, "stuck", rep.ended_reason)
        self.assertFalse(rep.verified, f"{rep.checks} notes={rep.notes}")
        # 有界：一天只有一次 goto 尝试；动作数被 `idle_rounds>=3` 那三条决策轮钉住
        # （本夹具实测 26：3 轮 × 每轮至多 `per_stage_tiles` 步；deputy 探针的 4 是零障碍夹具）。
        self.assertLessEqual(run.summary.get("actions", 0), 40, run.summary.get("actions"))
        self.assertEqual(len(run.days), 1, [d.day_text for d in run.days])


class _ShippingWorker(FakeWorker):
    """带"出货白名单"的假执行层（task-42）：白名单只由 `harvest()` 亲手喂进来。"""

    def __init__(self, world: FakeWorld, *, loot: tuple[str, ...] = ("(O)24",)) -> None:
        super().__init__(world)
        self.loot = list(loot)
        self.ship_calls = 0

    def sellable_slots(self, obs):
        return [5] * len(self.loot)

    def sell_loot(self, *, timeout_ms=8000, max_items=24):
        self.ship_calls += 1
        out: list[StepResult] = []
        for qid in list(self.loot):
            self.loot.remove(qid)
            st = StepResult("sell", None, ok=True, code="ok",
                            reason="已放进出货箱（钱要下一次 NewDay 才结算）")
            st.before = {"slot": 5, "qid": qid, "name": "Parsnip", "stack": 1,
                         "count": 1, "shipping_bin": 0, "money": 500}
            st.after = {"slot": 5, "qid": qid, "count": 0, "shipping_bin": 1, "money": 500}
            st.receipt = f"slot=5 qid={qid}"
            out.append(st)
        return out


class TestTask42Ship(unittest.TestCase):
    """task-42：`ship` 意图的接线与账本（用户 m08335"一分钱也没挣到"）。

    这里钉死的是**接线**而不是出货技能本身（技能在 `tests/test_farmwork.py::TestTask42Sell`）：
    ① `ship` 意图真的会调到 `worker.sell_loot()` 并写 journal `sell`；
    ② 白名单为空 ⇒ 计划里**不出现** `ship`（绝不"背包里有东西就卖"）；
    ③ 账本必须说清"钱要等下一次 NewDay"，免得看日报告的人以为没生效。
    """

    @staticmethod
    def _plot() -> dict:
        return {"zone": "", "label": "", "anchor": [62, 14], "tiles": [(62, 14)], "note": ""}

    def test_ship_intent_ships_loot_and_journals_it(self):
        w = FakeWorld(weeds=0, seeds=0, money=0)
        run = make_run(w, target_days=1)
        run.worker = _ShippingWorker(w)
        run.client = FakeClient(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        decision = SimpleNamespace(intents=[
            TaskIntent("ship", "anchor:current_location", "卖了才有钱买种子", "箱子件数上升")])
        acted = run._execute(decision, w.obs(), self._plot(), rep)
        self.assertTrue(acted)
        self.assertEqual(run.worker.ship_calls, 1)
        sells = [e for e in run.entries if e.get("event") == "sell"]
        self.assertEqual(len(sells), 1, run.entries)
        self.assertTrue(sells[0]["ok"])
        self.assertEqual(sells[0]["slot"], 5)
        self.assertEqual(sells[0]["qid"], "(O)24")
        self.assertEqual(sells[0]["before"]["money"], 500)
        self.assertEqual(sells[0]["after"]["money"], 500)      # 钱当天不变是**正常**的
        self.assertTrue(any("NewDay" in n for n in rep.notes), rep.notes)
        self.assertEqual(run._actions, 1)

    def test_plan_offers_ship_only_when_whitelist_is_not_empty(self):
        w = FakeWorld(weeds=0, seeds=0, money=0)
        run = make_run(w, target_days=1)
        run.worker = _ShippingWorker(w)
        run.client = FakeClient(w)
        obs = w.obs()
        brief = run._plot_brief(obs, self._plot())
        self.assertEqual(brief.sellable, 1)
        self.assertEqual(deterministic_plan(brief)[0].task, "ship")

        run.worker = _ShippingWorker(w, loot=())
        brief2 = run._plot_brief(obs, self._plot())
        self.assertEqual(brief2.sellable, 0)
        self.assertNotEqual(deterministic_plan(brief2)[0].task, "ship")

    def test_failed_ship_is_journalled_and_never_blocks_the_day(self):
        """出货失败 ⇒ 记 `sell_failed`、当天照常继续（不许因为卖不掉就撂挑子）。"""

        class _Broken(_ShippingWorker):
            def sell_loot(self, *, timeout_ms=8000, max_items=24):
                self.ship_calls += 1
                st = StepResult("sell", None, ok=False, code="failed",
                                reason="出货没有生效：Mod status=timeout")
                st.before = {"slot": 5, "qid": "(O)24", "name": "Parsnip", "stack": 1,
                             "count": 1, "shipping_bin": 0, "money": 500}
                st.after = {"slot": 5, "qid": "(O)24", "count": 1, "shipping_bin": 0, "money": 500}
                return [st]

        w = FakeWorld(weeds=0, seeds=0, money=0)
        run = make_run(w, target_days=1)
        run.worker = _Broken(w)
        run.client = FakeClient(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        decision = SimpleNamespace(intents=[
            TaskIntent("ship", "anchor:current_location", "卖了才有钱买种子", "箱子件数上升")])
        self.assertFalse(run._execute(decision, w.obs(), self._plot(), rep))
        self.assertEqual(len([e for e in run.entries if e.get("event") == "sell"]), 1)
        self.assertEqual(len([e for e in run.entries if e.get("event") == "sell_failed"]), 1)
        self.assertTrue(any("没能出货" in n or "失败" in n for n in rep.notes), rep.notes)


class TestTask49CrossPlotNoWork(unittest.TestCase):
    """task-49：run5 第 1 天「还有能做的活，却在中途判 `no_work` 去睡觉」（脑侧）。

    真机证据（Lead 逐行读 `logs\\longrun-3day-llm-run5.jsonl`，spring 26 第 1 天）：
    `t=205.46 till_area field_nw` 还剩 13 格（其中 4 格 `tool_ineffective` 已封）；`t=265.56
    plots_capped 10/10 zone=field_se`；之后人在 field_se、玩家窗口里看不见 field_nw 的格子 ⇒
    `t=304.78 sleep ok`、`ended_reason=no_work:…`（体力还剩 62.3）⇒ `day_end.verified=false`，
    且 `final_water.dry=1` 这条"还有一格没浇"也一起被丢掉。第 2 天同型。

    变异自检（**实测**，脚本 `%TEMP%\t49_mutate.py`，跑完即弃；基线 4/4 绿）：
    * `m49a`：把 `LongRun._pending_work` 换成恒返回 `[]`（等于关掉跨片地记账）⇒
      `test_unfinished_tile_elsewhere_blocks_no_work` **红**（`assertTrue(any("没做完"…))` 失败
      ⇒ 守卫放行了 `no_work`）。
    * `m49b`：把 `LongRun._farm_totals` 换成恒返回 `None`（等于去掉 `sleep_guard` 的 on-farm
      `farm.dryCrops` 分支）⇒ `test_dry_crops_on_farm_without_water_are_not_plain_no_work`
      **红**（`False is not true`：壶空但能补水时也放行睡觉了）。
    """

    @staticmethod
    def _plot_nw() -> dict:
        """"今天开过、还剩格子没做完"的那片地（field_nw）。"""
        return {"zone": "field_nw", "label": "", "anchor": [60, 10],
                "tiles": [(60, 10), (60, 11)], "note": ""}

    def _run_for(self, w: FakeWorld, *, target_days: int = 1, max_days: int = 1):
        """真 `FarmWorker` + 数数假桥；同时挂到 factories（`run()` 会用工厂重建，task-28 踩过）。"""
        client = _CountingClient(w)
        worker = FarmWorker(client, log=lambda *_: None)
        run = make_run(w, target_days=target_days, max_days=max_days,
                       client_factory=lambda: client, worker_factory=lambda c: worker)
        run.worker = worker
        run.client = client
        return run, worker, client

    def test_unfinished_tile_elsewhere_blocks_no_work(self):
        """跨片地：field_nw 还有一格没做完，人站在别处 ⇒ 守卫**不许**放行睡觉。"""
        w = MyopicWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.blockers[(60, 11)] = "weed"
        w.fail_status[(60, 11)] = ["timeout"] * 8      # 拿不到结论 ⇒ 不封格，但占本日配额
        run, _worker, _client = self._run_for(w)
        w.player_tile = [60, 12]                       # 先站在那片地旁边（看得见）
        rep = DayReport(day_key=("spring", 6, 1), started_at=0.0)

        run._step_stage("clear_area", w.obs(), self._plot_nw(), rep)

        self.assertEqual(run.blocked, {}, "timeout 是「没拿到结论」，绝不许封格")
        self.assertEqual(run.leftover_targets, {(60, 11)}, "没做成的格子必须进跨片地记账")

        w.player_tile = [70, 20]                       # 换到另一片地：窗口里看不见它了
        w.revealed = False
        obs = w.obs()
        seen = {(int(t["tile"][0]), int(t["tile"][1])) for t in obs["location"]["tiles"]}
        self.assertNotIn((60, 11), seen, "前提：换片地之后玩家窗口看不见留下的格子")

        reasons = run.work_reasons(obs)
        self.assertTrue(any("没做完" in r for r in reasons), reasons)
        allow, code, text = run.sleep_guard(obs)
        self.assertFalse(allow, f"还有没做完的格子却放行睡觉：{code} {text}")
        resume = run._resume_plot(obs)
        self.assertIsNotNone(resume, "有遗留就应给得出「回去接着做」的作业区")
        self.assertEqual(resume["tiles"][0], (60, 11))

    def test_all_leftovers_sealed_still_allows_no_work(self):
        """反向：片里目标**全部**被证明干不动（封格）⇒ 才允许 `no_work` 收工（不许过度乐观）。"""
        w = MyopicWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.blockers[(60, 11)] = "weed"
        w.fail_status[(60, 11)] = "tool_ineffective"   # Mod 回「工具全无效」⇒ 判据成立
        run, _worker, _client = self._run_for(w)
        w.player_tile = [60, 12]
        rep = DayReport(day_key=("spring", 6, 1), started_at=0.0)

        run._step_stage("clear_area", w.obs(), self._plot_nw(), rep)

        self.assertIn((60, 11), run.blocked, "「工具全无效」是这一格的结论，必须封到当天结束")
        self.assertEqual(run.leftover_targets, set(), "封掉的格子不算「今天还有活」")

        w.player_tile = [70, 20]
        w.revealed = False
        obs = w.obs()
        self.assertEqual(run._pending_work(), [])
        allow, code, _text = run.sleep_guard(obs)
        self.assertTrue(allow, "片里目标全封了却仍不放行睡觉")
        self.assertEqual(code, "no_work")

    def test_dry_crops_on_farm_without_water_are_not_plain_no_work(self):
        """农场口径还有干作物：能补水就继续干；**确实没水**才允许睡，且必须写成 `no_water`。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {"loaded": True, "complete": True, "crops": 37, "dryCrops": 1,
                  "ripeCrops": 0, "unwateredCrops": 0, "hoeDirt": 30}
        w.water_left = 0                                # 壶空，但观测里有补水点
        run, _worker, _client = self._run_for(w)

        allow, code, text = run.sleep_guard(w.obs())
        self.assertFalse(allow, "壶空但能去补水 ⇒ 必须先补水再浇")
        self.assertEqual(code, "keep_working")
        self.assertIn("干作物", text)

        class _NoRefill(FakeWorld):
            def obs(self):
                o = super().obs()
                o["location"]["refillTiles"] = []
                return o

        w2 = _NoRefill(weeds=0, seeds=0, money=0)
        w2.farm = dict(w.farm)
        w2.water_left = 0
        run2, _w2, _c2 = self._run_for(w2)

        allow2, code2, text2 = run2.sleep_guard(w2.obs())
        self.assertTrue(allow2, "打不到水 ⇒ 允许睡（但必须如实记账）")
        self.assertEqual(code2, "no_water")
        self.assertIn("想浇但无水", text2)
        self.assertNotIn(code2, JUSTIFIED_END_REASONS,
                         "「想浇但无水」不是「没活可做」，不许洗成 day_justified")

    def test_persistent_unfinishable_work_is_bounded_and_never_no_work(self):
        """有界性：永远做不成的活 ⇒ 当天可以收尾，但**不许**以 `no_work` 洗白，且动作数有上界。"""
        w = MyopicWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.fail_status[(60, 10)] = "timeout"             # 每轮都拿不到结论
        w.player_tile = [60, 12]                        # 站在这片地旁边：观测看得见它（真机口径）
        w.farm = {"loaded": True, "complete": True, "crops": 0, "dryCrops": 0,
                  "ripeCrops": 0, "unwateredCrops": 0, "hoeDirt": 0}
        run, _worker, _client = self._run_for(w)

        code = run.run()

        rep = run.days[-1]
        self.assertNotEqual(code, 0, "没做成任何事 ⇒ 不许报达标")
        self.assertFalse(str(rep.ended_reason).startswith("no_work"),
                         f"守卫一直说还有活 ⇒ 不许洗成 no_work：{rep.ended_reason}")
        self.assertLessEqual(run._actions, 40, f"动作数必须收敛：{run._actions}")
        self.assertLessEqual(run.resume_walks, run.max_plots_per_day)


# --------------------------------------------------------------- task-50：窗口外干作物
class DryTilesWorld(MyopicWorld):
    """task-50 夹具：`farm.dryTiles` 报出"玩家观测窗口之外"的干作物坐标（run5 真机形态）。

    三个关键点（缺一不可，否则用例证明不了 run5 那个 bug）：

    * 观测仍是**以玩家为中心**的（`MyopicWorld`，半径 3）⇒ 远处的干格既看不见、
      `location.tiles`/`tillable` 里也没有它 —— 这正是 run5 三天 `dry=1` 却
      `leftover=0`、只能 `no_work` 收工的现场；
    * `farm` 块**按真实作物状态现算**（`dryCrops`/`dryTiles`/`truncated`），所以
      "走过去浇没浇成"能由 farm 口径的观测差分证明（生产代码的判据就是这条）；
    * `with_dry_tiles=False` 复刻**旧 Mod**：没有坐标字段 ⇒ 脑侧不许把它当成"没有干格"。
    """

    def __init__(self, *, with_dry_tiles: bool = True, truncated: bool = False, **kw) -> None:
        super().__init__(**kw)
        self.with_dry_tiles = with_dry_tiles
        self.truncated = truncated
        self.watered_tiles: list[tuple[int, int]] = []

    def obs(self) -> dict:
        dry = sorted(t for t, c in self.crops.items() if not c["watered"])
        self.farm = {"loaded": True, "complete": True, "crops": len(self.crops),
                     "ripeCrops": sum(1 for c in self.crops.values() if c["ripe"]),
                     "dryCrops": len(dry), "unwateredCrops": len(dry),
                     "hoeDirt": len(self.dirt)}
        if self.with_dry_tiles:
            self.farm["dryTiles"] = [list(t) for t in dry[:64]]
            self.farm["dryTilesTruncated"] = bool(self.truncated)
        return super().obs()

    def water(self, tile):
        st = super().water(tile)
        if st.ok:
            self.watered_tiles.append(tuple(tile))
        return st


class NoWalkFarDryWorker(FakeWorker):
    """`stand_next_to` 对指定格子永远失败 ⇒ 复刻"干作物在农场另一头、今天走不到"。"""

    def __init__(self, world: DryTilesWorld, *, unreachable: Iterable[tuple[int, int]]) -> None:
        super().__init__(world)
        self.unreachable = {tuple(t) for t in unreachable}

    def stand_next_to(self, tile, *, timeout_ms=15000):
        if tuple(tile) in self.unreachable:
            return False
        return super().stand_next_to(tile, timeout_ms=timeout_ms)

    def water(self, tile, *, timeout_ms=15000):
        st = self.w.water(tuple(tile))
        self.steps.append(st)
        return st


class LyingWaterWorker(FakeWorker):
    """回执 `ok=true` 但**世界一动不动**（run1/run2 的"回执不算证据"形态）。

    只覆写 `water()` 不够：日循环里 `_policy_intents` 看到未浇作物会强推 `water_area`，
    而 `FakeWorker.run_stage` 会**真去浇**（落到 `FakeWorld.water()`）⇒ 这天会"合法地"
    变达标，判据就证不出来了。所以 `run_stage` 一并哑掉：全天唯一动过手的地方就是
    那次撒谎的 `water()`。
    """

    def run_stage(self, stage, tiles, *, min_stamina=12.0, max_steps=200):
        return StageResult(stage=stage, tiles=list(tiles), stopped="world")

    def water(self, tile, *, timeout_ms=15000):
        return StepResult("water", tuple(tile), ok=True, reason="假回执：浇过了（其实没有）")


class TestTask50FarDryTiles(unittest.TestCase):
    """task-50：`farm.dryTiles` 让"窗口外那一格干作物"变得**可行动**。

    为什么这条重要（run5 三天全挂的病灶）：脑侧观测只有玩家周围最近的 400 格，
    农场另一头那 1 格干作物既看不见、也没有坐标 ⇒ `work_reasons` 拿不出目标 ⇒
    `no_work` 收工（还白拿 `day_justified=true`），只有 `watered_outdoor` 把 `verified`
    拽下来。Mod 补 `dryTiles` 坐标之后，脑侧必须**走过去浇**，走不到就 `stuck:` 点名坐标。

    变异自检（`%TEMP%\\t50_mutate.py`，跑完即弃、不入库；基线 5/5 绿）：
    - m50a（`_water_far_dry` 直接返回 False，等于没实现"跨窗口浇水"）⇒ 5 条全红；
    - m50b（`_far_dry_tiles` 不认 `far_dry_given_up`，等于"永远重试"）⇒ 有界性 +
      不可达两条红；
    - m50c（判据把 Mod 回执 `st.ok` 算成证据）⇒ `test_ok_receipt_without_observation_change_is_never_watered`
      红 —— 这正是 run1/run2 "回执 ok、世界没变" 的形态。
    """

    #: 离玩家 [62,14] 曼哈顿距离 5 > 半径 3 ⇒ 一开始不在观测窗口里（run5 的真实形态）。
    FAR = (61, 10)

    def _world(self, *, with_dry_tiles: bool = True, truncated: bool = False) -> DryTilesWorld:
        w = DryTilesWorld(seeds=0, money=0, weeds=0, water_left=40,
                          with_dry_tiles=with_dry_tiles, truncated=truncated)
        w.dirt.add(self.FAR)
        w.crops[self.FAR] = {"watered": False, "ripe": False}
        w.player_tile = [62, 14]
        return w

    def _run_for(self, w, worker_factory, *, max_days: int = 2):
        return make_run(w, target_days=1, max_days=max_days,
                        client_factory=lambda: FakeClient(w),
                        worker_factory=worker_factory)

    def _events(self, run, event):
        return [e for e in run.entries if e["event"] == event]

    def test_far_dry_tile_is_walked_to_and_watered(self):
        """①窗口外干格在 `farm.dryTiles` 里 ⇒ 真的走过去浇，farm 口径归零，绝不 `no_work` 洗白。"""
        w = self._world()
        # 跑之前那一格确实不在观测窗口里（否则这条用例证明不了"窗口外"）
        self.assertNotIn(self.FAR, set(FarmWorker.tiles_of(w.obs())))
        run = self._run_for(w, lambda _c: FakeWorker(w))

        code = run.run()

        rep = run.days[0]
        self.assertEqual(code, 0, "唯一那格干作物被浇了 ⇒ 这天该达标")
        self.assertEqual(w.watered_tiles, [self.FAR], "窗口外那格必须被真的浇到")
        self.assertEqual(rep.final_water.get("dry"), 0, "farm 口径必须归零")
        self.assertTrue(rep.checks.get("watered_outdoor"))
        ev = self._events(run, "water_far")
        self.assertEqual(len(ev), 1, f"应当恰有一次『走过去浇窗口外干格』：{ev}")
        self.assertEqual(ev[0]["tile"], list(self.FAR))
        self.assertTrue(ev[0]["ok"])
        self.assertTrue(ev[0]["walked"])
        self.assertTrue(ev[0]["watered"])
        self.assertEqual((ev[0]["dry_before"], ev[0]["dry_after"]), (1, 0))
        self.assertFalse(ev[0]["given_up"])

    def test_ok_receipt_without_observation_change_is_never_watered(self):
        """回执不算证据：回执 `ok=true` 但世界没变 ⇒ `ok=false`，当天绝不 VERIFIED。

        这是全项目的铁律（run1 白挥、run3 连睡都是"回执 ok ≠ 世界变了"）。
        """
        w = self._world()
        run = self._run_for(w, lambda _c: LyingWaterWorker(w))

        code = run.run()

        rep = run.days[0]
        ev = self._events(run, "water_far")
        self.assertTrue(ev, "应当至少试过一次")
        self.assertTrue(ev[0]["receipt_ok"], "前提：执行层回执确实是 ok=true")
        self.assertFalse(ev[0]["ok"], "世界没变 ⇒ 不许算浇过")
        self.assertFalse(ev[0]["watered"])
        self.assertEqual((ev[0]["dry_before"], ev[0]["dry_after"]), (1, 1))
        self.assertNotEqual(code, 0, "干作物还在 ⇒ 不许报达标")
        self.assertEqual(rep.final_water.get("dry"), 1)
        self.assertFalse(rep.checks.get("watered_outdoor"))
        self.assertFalse(str(rep.ended_reason).startswith("no_work"),
                         f"干作物还在时不许 no_work 收工：{rep.ended_reason}")
        self.assertTrue(str(rep.ended_reason).startswith("stuck:"), rep.ended_reason)
        self.assertEqual(w.watered_tiles, [], "全场没有任何一条路径真的浇过")

    def test_unreachable_far_dry_tile_ends_stuck_with_coordinates(self):
        """②走不到 ⇒ 当天**如实收尾并点名坐标**，绝不是 `no_work`。

        【task-84 ①】收尾理由从 `stuck:` 改成 `gave_up_dry`：那一格试满 `FAR_DRY_MAX_TRIES`
        次仍够不着之后进了 `far_dry_given_up`，此时 `work_reasons` 不再把"够不着的干格"当活
        （run7 的 summer 3/5 就是靠"还有活"整天换片地空转），改由 `sleep_guard` 用
        `gave_up_dry` 一次性如实收尾 —— 该理由**不在** `JUSTIFIED_END_REASONS` 里，
        所以 `day_justified=False`、当天 `verified=false`，既不是 `no_work` 洗白、也不再空转。
        """
        w = self._world()
        run = self._run_for(w, lambda _c: NoWalkFarDryWorker(w, unreachable=[self.FAR]),
                            max_days=1)

        code = run.run()

        rep = run.days[0]
        self.assertNotEqual(code, 0, "那一格始终干着 ⇒ 不许报达标")
        self.assertFalse(str(rep.ended_reason).startswith("no_work"),
                         f"干作物还在时不许 no_work 收工：{rep.ended_reason}")
        self.assertTrue(str(rep.ended_reason).startswith("gave_up_dry"),
                        f"task-84：够不着的干格必须如实记 gave_up_dry：{rep.ended_reason}")
        self.assertIn("[61, 10]", rep.ended_reason, "坐标必须点名（task-50 硬要求延续）")
        self.assertIn("干作物", rep.ended_reason)
        self.assertIn("够不着", rep.ended_reason)
        self.assertFalse(rep.checks.get("watered_outdoor"))
        self.assertFalse(rep.checks.get("day_justified"),
                         "gave_up_dry 不在 JUSTIFIED_END_REASONS 里 ⇒ 绝不许算达标收工")
        self.assertFalse(rep.verified)
        ev = self._events(run, "water_far")
        self.assertEqual(len(ev), 2, f"同一格最多试 {2} 次（有界，不空转）：{ev}")
        self.assertFalse(any(e["walked"] for e in ev))
        self.assertTrue(ev[-1]["given_up"])
        self.assertEqual(rep.gave_up_tiles, [list(self.FAR)],
                         "【task-84】认输的干格要进日账本（带坐标）")

    def test_old_mod_without_dry_tiles_is_not_no_dry_tiles(self):
        """③旧 Mod 没有 `dryTiles` ⇒ 不许当成"没有干格"：不判 `no_work`，但如实记"不可用"。"""
        w = self._world(with_dry_tiles=False)
        run = self._run_for(w, lambda _c: FakeWorker(w), max_days=1)

        run.run()

        rep = run.days[0]
        self.assertFalse(str(rep.ended_reason).startswith("no_work"),
                         f"缺字段不等于没活：{rep.ended_reason}")
        self.assertTrue(str(rep.ended_reason).startswith("stuck:"), rep.ended_reason)
        self.assertEqual(self._events(run, "water_far"), [], "没有坐标就没法行动，不该瞎走")
        unavail = self._events(run, "water_far_unavailable")
        self.assertEqual(len(unavail), 1, f"一天只提醒一次：{unavail}")
        self.assertTrue(unavail[0]["loaded"])
        self.assertEqual(unavail[0]["dryCrops"], 1)
        self.assertTrue(run.far_dry_unavailable_noted)
        self.assertFalse(rep.checks.get("watered_outdoor"))

    def test_far_dry_retries_are_bounded_per_day(self):
        """有界性：一直浇不成也不可能无限重试 —— 每格 2 次、动作数有上界。"""
        w = self._world()
        run = self._run_for(w, lambda _c: NoWalkFarDryWorker(w, unreachable=[self.FAR]),
                            max_days=1)

        run.run()

        ev = self._events(run, "water_far")
        self.assertEqual(len(ev), 2, f"每格一天最多 {2} 次：{len(ev)}")
        self.assertLessEqual(run._actions, 40, f"整天动作数必须收敛：{run._actions}")
        self.assertTrue(all(not e["ok"] for e in ev))
        self.assertTrue(ev[-1]["given_up"])


class TestTask56LlmTraceWiring(unittest.TestCase):
    """【task-56】长跑把"决策留痕"接起来：journal 路径 ⇒ `<stem>-llm.jsonl` ⇒ planner。

    真实 LLM 调用的现场由 planner 落一行 JSON；`decision` journal 只多两个字段
    （路径 + 该行 sha256 前 12 位）。这里用**抛 `LlmError` 的假 seam**：它也算"真的调了一次"
    （进入 `_ask` 即计数），所以既能验证留痕链路，又完全不联网。
    """

    def test_decision_journal_carries_trace_path_and_hash(self):
        w = FakeWorld(weeds=4, seeds=10, money=500)
        chat = _BoomChat()

        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "run-llm-test.jsonl"
            run = make_run(w, target_days=1, max_days=1, journal_path=str(journal),
                           llm_enabled=True, planner=BoundaryPlanner(
                               llm_chat=chat, llm_enabled=True, max_llm_attempts=1))
            # 钉住一个边界：上一次的 task 种类与本次确定性首选不同 ⇒ 必然问一次 LLM
            run.state.last_task_kind = "review"

            run.run()

            trace_path = Path(tmp) / "run-llm-test-llm.jsonl"
            self.assertTrue(trace_path.exists(), "留痕文件必须写在 journal 旁边（同前缀 + -llm）")
            rows = [e for e in run.entries if e["event"] == "decision"]
            called = [e for e in rows if e.get("llm_trace")]
            self.assertTrue(called, f"边界上的 decision 行必须带 llm_trace：{rows[:2]}")
            row = called[0]
            self.assertEqual(row["llm_trace"], str(trace_path))
            # 既有字段语义一个字没动
            self.assertIn(row["source"], ("llm", "deterministic_fallback"))
            self.assertIn("intents", row)
            # 哈希必须就是 trace 文件里对应那一行的 sha256 前 12 位
            lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertTrue(lines)
            hashes = {hashlib.sha256(ln.encode("utf-8")).hexdigest()[:12] for ln in lines}
            for called_row in called:
                self.assertIn(called_row["llm_trace_hash"], hashes)
            # 每行 trace 都是一次**真实**调用：行数 == 假 seam 被调次数（不多不少）
            self.assertEqual(len(lines), chat.calls)
            recs = [json.loads(ln) for ln in lines]
            self.assertTrue(all(r["accepted"] == [] for r in recs))
            self.assertTrue(all(r["fallback"] for r in recs))    # 降级 ⇒ 可读原因串（真值）

    def test_llm_trace_failed_is_journalled_when_the_path_is_unusable(self):
        """写盘失败：决策照常跑完，journal 多一条 `llm_trace_failed`（用户才不会以为有留痕）。"""
        w = FakeWorld(weeds=4, seeds=10, money=500)
        chat = _BoomChat()

        with tempfile.TemporaryDirectory() as tmp:
            # 把"留痕文件"指向一个目录 ⇒ 写盘必失败，但 journal 本身照常写
            journal = Path(tmp) / "run-llm-test.jsonl"
            run = make_run(w, target_days=1, max_days=1, journal_path=str(journal),
                           llm_enabled=True, planner=BoundaryPlanner(
                               llm_chat=chat, llm_enabled=True, max_llm_attempts=1))
            run.state.last_task_kind = "review"
            run.planner.set_trace_path(Path(tmp))            # 目录，不是文件

            run.run()

            failed = [e for e in run.entries if e["event"] == "llm_trace_failed"]
            self.assertTrue(failed, "写盘失败必须留下 llm_trace_failed")
            self.assertTrue(failed[0]["reason"])
            # 决策本身没被影响：该问的问了、该降级降级了
            self.assertGreaterEqual(chat.calls, 1)
            self.assertTrue([e for e in run.entries if e["event"] == "decision"])


_NB4 = ((0, -1), (0, 1), (1, 0), (-1, 0))


class _UnreachableClient(FakeClient):
    """task-52：这些格**走不上去**（真机是 Mod 回 `unreachable`，或脑侧四邻全抛）。"""

    def __init__(self, world: FakeWorld, *, unreachable=()) -> None:
        super().__init__(world)
        cells: set[tuple[int, int]] = set()
        for t in unreachable:
            t = (int(t[0]), int(t[1]))
            cells.add(t)
            cells.update((t[0] + dx, t[1] + dy) for dx, dy in _NB4)
        self.unreachable_cells = cells

    def move_to(self, x, y, *, timeout_ms=None, allow_bed=None):
        if (int(x), int(y)) in self.unreachable_cells:
            raise BridgeError(f"走向 ({int(x)}, {int(y)}) 时寻路无法到达", status="unreachable")
        return super().move_to(x, y, timeout_ms=timeout_ms, allow_bed=allow_bed)

    def buy(self, item, count=10, *, shop="SeedShop", timeout_ms=25000):
        """真 `FarmWorker` 会走 `c.buy(...)`；`FakeClient` 没有，这里补上（落到 `FakeWorld.buy`）。"""
        return self.w.buy(item, count, shop)


class UnreachableWorld(FakeWorld):
    """指定格子是世界里的障碍，但**四邻都走不到** —— run5 summer 1 那 8 格的复现。"""

    def __init__(self, *, unreachable=(), **kw) -> None:
        kw.setdefault("weeds", 0)
        super().__init__(**kw)
        self.unreachable = {tuple(t) for t in unreachable}
        for t in sorted(self.unreachable):
            self.blockers[t] = "weed"


class TestTask52Unreachable(unittest.TestCase):
    """task-52：run5 里「8 格 clear 走不到」把一整天判死（`no_hard_failures=false` ⇒ 不 VERIFIED）。

    真机证据（`logs\\longrun-3day-llm-run5.jsonl` t=809.5/917.59，summer 1）：那天做成 109 步、
    `final_water.dry=0`，却因 8 格 `clear` 报「四邻都站不过去」⇒ 达标线被一票否决。客观走不到
    不是硬失败：当天记进 `blocked`（不再白试）、**次日重试**、日级豁免有 `max(5, 20%)` 上界，
    且**不许把真空日洗成达标**（`ok_steps==0` 时豁免不生效）。

    变异自检（**实测**，脚本 `%TEMP%\\t52_mutate.py`，跑完即弃；基线 10/10 绿）：
    * `m52a`：把 `StepResult.unreachable` 换成恒 False（等于关掉归类，退回 failed）⇒ **7 条红**
      （含 `test_eight_unreachable_tiles_do_not_break_an_otherwise_good_day`）。
    * `m52b`：把 `LongRun._leftover` 改成排除 `self.blocked`（task-9 条款①明令禁止的洗白写法）
      ⇒ **3 条红**，其中 `test_within_bound_but_zero_success_is_still_never_verified` 正是防这条的。
    """

    U8 = [(60, 10), (61, 10), (62, 10), (63, 10), (64, 10), (60, 11), (61, 11), (62, 11)]
    WEEDS4 = [(60, 13), (62, 13), (64, 13), (61, 14)]

    def _mixed_world(self) -> UnreachableWorld:
        w = UnreachableWorld(unreachable=self.U8, seeds=10, money=500)
        for t in self.WEEDS4:
            w.blockers[t] = "weed"
        return w

    def _run(self, w: FakeWorld, **kw):
        client = _UnreachableClient(w, unreachable=getattr(w, "unreachable", ()))
        worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
        kw.setdefault("target_days", 1)
        kw.setdefault("max_days", 1)
        run = make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker, **kw)
        run.worker = worker
        run.client = client
        return run, client

    @staticmethod
    def _events(run: LongRun, event: str) -> list:
        return [e for e in run.entries if e.get("event") == event]

    def test_eight_unreachable_tiles_do_not_break_an_otherwise_good_day(self):
        """8 格走不到 + 其余全做成 ⇒ `no_hard_failures`/`no_unmet_stages` 都真、当天 VERIFIED。"""
        w = self._mixed_world()
        run, _ = self._run(w)
        self.assertEqual(run.run(), 0)
        rep = run.days[0]
        self.assertEqual(rep.failed_steps, 0, rep.stages)
        self.assertEqual(rep.unreachable, 8)
        self.assertEqual({tuple(t) for t in rep.unreachable_tiles}, set(self.U8))
        self.assertTrue(rep.checks["no_hard_failures"], rep.checks)
        self.assertTrue(rep.checks["unreachable_within_bound"], rep.checks)
        self.assertTrue(rep.checks["no_unmet_stages"], rep.checks)
        self.assertTrue(rep.verified, f"{rep.checks} / stages={rep.stages}")
        per = self._events(run, "unreachable")
        self.assertEqual({tuple(e["tile"]) for e in per}, set(self.U8), per)
        self.assertTrue(all(e["stage"] == "clear_area" for e in per))
        self.assertTrue(all("四邻都站不过去" in str(e["reason"]) for e in per), per)
        day_end = self._events(run, "day_end")[-1]
        for key in ("unreachable", "unreachable_tiles", "unreachable_bound", "unreachable_exempt"):
            self.assertIn(key, day_end, f"day_end 缺 {key}")
        self.assertEqual(day_end["unreachable"], 8)
        self.assertGreater(day_end["unreachable_bound"], 0)

    def test_exceeding_the_bound_trips_the_check_and_kills_verification(self):
        """8 格全走不到、0 成功 ⇒ 8 > `max(5, 20%×attempted)` ⇒ 越界判据亮、不得 VERIFIED。"""
        w = UnreachableWorld(unreachable=self.U8, seeds=0, money=0)
        run, _ = self._run(w)
        run.run()
        rep = run.days[0]
        self.assertEqual(rep.ok_steps, 0)
        self.assertIs(rep.checks["unreachable_within_bound"], False, rep.checks)
        self.assertIs(rep.checks["no_unmet_stages"], False, rep.checks)
        self.assertIs(rep.verified, False)
        self.assertTrue(any("走不到" in n for n in rep.notes), rep.notes)

    def test_within_bound_but_zero_success_is_still_never_verified(self):
        """防真空：5 格走不到（正好在上界内）+ 0 成功 ⇒ 豁免不许把这一天洗成达标。"""
        w = UnreachableWorld(unreachable=self.U8[:5], seeds=0, money=0)
        run, _ = self._run(w)
        run.run()
        rep = run.days[0]
        self.assertEqual(rep.ok_steps, 0)
        self.assertEqual(rep.unreachable, 5)
        self.assertGreaterEqual(rep.unreachable_bound, 5)
        self.assertTrue(rep.checks["unreachable_within_bound"], rep.checks)
        self.assertIs(rep.checks["no_unmet_stages"], False,
                      "全走不到 + 0 成功：豁免再宽也不许自证")
        self.assertIs(rep.verified, False)

    def test_next_day_retries_the_same_unreachable_tiles(self):
        """`blocked` 每天清空 ⇒ 次日必须**再试**（不许像 `proven_inert` 那样永久封格）。"""
        w = self._mixed_world()
        run, _ = self._run(w, target_days=2, max_days=3)
        run.run()
        self.assertGreaterEqual(len(run.days), 2)
        self.assertEqual({tuple(t) for t in run.days[0].unreachable_tiles}, set(self.U8))
        self.assertEqual({tuple(t) for t in run.days[1].unreachable_tiles}, set(self.U8),
                         "次日没有重试这 8 格 ⇒ 变成了永久封格")
        self.assertGreaterEqual(len(self._events(run, "unreachable")), 16)

    def test_stage_counts_match_the_per_tile_journal(self):
        """阶段账本与逐格 journal 必须同一组坐标，且`unreachable` 绝不进 `failed`。"""
        two = [(60, 10), (61, 10)]
        w = UnreachableWorld(unreachable=two, seeds=0, money=0)
        w.blockers[(63, 13)] = "weed"
        run, _ = self._run(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        plot = {"zone": "", "label": "", "anchor": [60, 10],
                "tiles": [(60, 10), (61, 10), (63, 13)], "note": ""}
        run._step_stage("clear_area", w.obs(), plot, rep)
        st = rep.stages[-1]
        self.assertEqual(st["unreachable"], 2, st)
        self.assertEqual(st["failed"], 0, st)
        self.assertEqual({tuple(t) for t in st["unreachable_tiles"]}, set(two))
        self.assertGreaterEqual(st["attempted"], 3)
        ev = self._events(run, "unreachable_stage")
        self.assertEqual(len(ev), 1, ev)
        self.assertEqual(ev[0]["tiles"], 2)
        self.assertEqual(ev[0]["in_leftover"], 2)
        self.assertEqual({tuple(t) for t in ev[0]["coords"]}, set(two))


class TestTask51ClearDead(unittest.TestCase):
    """task-51：枯死作物 —— Mod 报 `farm.deadCrops`，脑侧新增 `clear_dead`（镰刀）。**活苗绝不碰**。

    真机依据（`scratch/_lead_crop_audit.py`，summer 2）：窗口 400 格里 24 个作物有 23 个
    `dead=True`（唯一活苗 `[73,37]`），而 `till_blocked_by` 见 crop 就回「有作物」⇒ 不清死苗就
    永远种不上（`till` 也永远被拒）。窗口外的死苗**没有坐标**（Mod 只给计数），只留痕不假装清完。
    """

    def _plot(self, w, run):
        cands = run._plot_candidates(w.obs())
        self.assertTrue(cands, "假农场应该切得出田区")
        return cands[0]

    @staticmethod
    def _events(run: LongRun, event: str) -> list:
        return [e for e in run.entries if e.get("event") == event]

    def test_stage_tiles_leftover_and_plot_work_see_dead_crops_only(self):
        """死苗进目标池；活苗不进；窗口里有死苗 ⇒ 这片地算"有活"（否则一整天零动作）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        dead, live = (60, 10), (62, 12)
        w.dirt |= {dead, live}
        w.crops[dead] = {"watered": True, "ripe": False, "dead": True}
        w.crops[live] = {"watered": True, "ripe": False, "dead": False}
        run = make_run(w)
        run.worker = FakeWorker(w)
        # 死苗所在的田区（`_plot_candidates` 会切出 4 片；守卫只对"这一片"回答）
        plots = run._plot_candidates(w.obs())
        plot = next(p for p in plots if tuple(dead) in {tuple(t) for t in p["tiles"]})
        obs = w.obs()
        self.assertEqual(run._stage_tiles("clear_dead", obs, plot), [dead])
        self.assertEqual(run._leftover("clear_dead", obs, plot), [dead])
        self.assertTrue(run._plot_has_work(obs, plot["tiles"]))

    def test_day_clears_dead_crops_and_never_touches_the_live_seedling(self):
        """跑一天：死苗被清掉、活苗原样在、`clear_dead_scope` 留痕、当天照常 VERIFIED。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        dead = [(60, 10), (62, 12)]
        live = (64, 14)
        for t in dead + [live]:
            w.dirt.add(t)
            w.crops[t] = {"watered": True, "ripe": False, "dead": t in dead}
        # 【task-96】给一份**与世界一致**的 farm 扫描：新的 fail-closed 规定"人在农场 + farm
        # 证据不可用 ⇒ 不许收工（不许 `no_work`）"，本用例要验的是"清完死苗这一天照常
        # VERIFIED"，所以证据必须可用（真机 0.7.27 的桥永远发 `farm`）。
        # "缺字段不许当 0" 由 `farm_dead_crops` 三态用例与 `TestTask84DeadCropWatering` ⑥ 覆盖。
        w.farm = w.farm_scan()
        run = make_run(w, target_days=1, max_days=1)
        self.assertEqual(run.run(), 0, run.days)
        for t in dead:
            self.assertNotIn(t, w.crops, "死苗必须被清掉")
        self.assertIn(live, w.crops, "活苗绝不许被碰")
        scopes = self._events(run, "clear_dead_scope")
        self.assertEqual(len(scopes), 1, run.entries)
        self.assertEqual(scopes[0]["in_view"], 2)
        self.assertEqual(scopes[0]["farm_status"], "ok", "farm 证据可用（本用例显式给了扫描）")
        self.assertEqual(scopes[0]["farm"], 2, "farm 口径的死苗数（清之前是 2，清完才变 0）")
        rep = run.days[0]
        self.assertEqual(rep.failed_steps, 0, rep.stages)
        self.assertTrue(rep.checks["no_unmet_stages"], rep.checks)
        self.assertTrue(rep.verified, f"{rep.checks} / {rep.stages}")

    def test_planner_puts_clear_dead_between_harvest_and_ship(self):
        """策略顺序（【task-84】改序）：收获 → **清死苗** → 浇水 → 出货 → 清障 → 开垦 → 播种。

        `deterministic_plan` 每次只回**最高优先级**那一条，所以顺序用"同时有几件事时先挑谁"来验。

        改序理由（Lead task-84 卡面建议序 + 用户 m11003）：枯死作物浇水是**纯浪费**
        （run7 追着 `[12,30]` 那株够不着的死苗浇了一整天），必须先清掉，
        当天的浇水目标集合才只剩活苗。收获仍排在最前（熟作物不等人、收完腾地）。
        """

        def top(*, sellable: int = 0, **counts) -> str:
            base = {"dead": 0, "ripe": 0, "unwatered_crops": 0,
                    "blockers": 0, "dirt": 0, "plantable": 0}
            base.update(counts)
            return deterministic_plan(
                Brief(day_key=(1, "spring", 6), has_save=True, counts=base,
                      sellable=sellable))[0].task

        self.assertEqual(top(dead=3), "clear_dead")
        self.assertEqual(top(dead=3, ripe=2), "harvest", "收获压过清死苗")
        self.assertEqual(top(dead=3, unwatered_crops=1), "clear_dead",
                         "【task-84】清死苗压过浇水：死苗浇了也没用（改序前是 water_area）")
        self.assertEqual(top(unwatered_crops=1), "water_area", "没有死苗时浇水仍是第一优先的日常活")
        self.assertEqual(top(dead=3, sellable=5), "clear_dead", "清死苗压过出货")
        self.assertEqual(top(sellable=5), "ship", "没有死苗时才轮到出货")
        self.assertEqual(top(dead=3, sellable=5, blockers=2), "clear_dead", "清障排在最后")


class RefusedWorld(FakeWorld):
    """【task-63】这些 tillable 格子被**游戏拒绝**（真机 run5 的 4 格不可锄：`kind=未知`）。

    真机形态：Mod 对 `use_tool` 回 `tool_ineffective`（"挥满 `MaxSwings=6` 仍拒绝这个工具动这格"），
    观测纹丝不动。`FakeClient.use_tool` 会把它抛成 `BridgeError(status="tool_ineffective")`，
    逼脑侧按 `exc.status` 分类 —— 这正是本卡要的复现路径。
    """

    def __init__(self, *, refused=(), tillable=None, **kw) -> None:
        kw.setdefault("weeds", 0)
        super().__init__(**kw)
        self.refused = {tuple(t) for t in refused}
        if tillable is not None:
            self.tillable = {tuple(t) for t in tillable}
        for t in sorted(self.refused):
            self.fail_status[t] = "tool_ineffective"     # str ⇒ 每次请求都拒绝


class _RefusalClient(FakeClient):
    """真 `FarmWorker` 会走 `c.buy(...)`（`FakeClient` 没有）⇒ 补一个落到 `FakeWorld.buy`。"""

    def buy(self, item, count=10, *, shop="SeedShop", timeout_ms=25000):
        return self.w.buy(item, count, shop)


class TestTask63Refused(unittest.TestCase):
    """【task-63】`till` 的 `tool_ineffective`（游戏拒绝）不算硬失败。

    真机 run5 `spring 26`：4 格 `till` 回 `tool_ineffective`（`(38,20)(38,19)(37,20)(37,19)`、
    `kind=未知`、体力 140→102）被判 `failed` ⇒ 当天 `no_hard_failures=false`。但那是**世界给的
    前置事实**（游戏自己拒绝这个工具动这格），与项目纪律"跳过 ≠ 失败，前者不污染终态"一致 ⇒
    记 `skipped`+`proven_inert`（当天封格、次日重试），日级豁免按 `refused_bound = max(5, 20%×attempted)`
    **有界**（超界照实 `no_hard_failures=false`），且与 task-52 的 `unreachable` 两套计数**互不覆盖**。

    变异自检（**实测**，脚本 `%TEMP%\\t63_mutate.py`，跑完即弃；基线 `TestTask63Refused`
    （farmwork 4 条 + longrun 5 条共 9 条）全绿）：
    * `m63a`：把 `till()` 的拒绝分支关掉（`status ∈ TILE_INERT_STATUSES` 退回 `failed`）⇒ **7 条红**。
    * `m63b`：把上界去掉（`refused_within_bound` 恒 True、`no_hard_failures` 不计 refused）
      ⇒ **1 条红**（`test_exceeding_the_bound_trips_the_check_and_kills_verification`）。
    """

    REFUSED3 = [(60, 10), (61, 10), (62, 10)]
    FIVE = [(60, 10), (61, 10), (62, 10), (63, 10), (64, 10)]

    def _run(self, w: FakeWorld, *, client=None, **kw):
        client = client if client is not None else _RefusalClient(w)
        worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
        kw.setdefault("target_days", 1)
        kw.setdefault("max_days", 1)
        run = make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker, **kw)
        run.worker = worker
        run.client = client
        return run

    @staticmethod
    def _events(run: LongRun, event: str) -> list:
        return [e for e in run.entries if e.get("event") == event]

    def test_refused_tiles_do_not_hard_fail_an_otherwise_good_day(self):
        """3 格被游戏拒绝 + 其余全做成 ⇒ `failed_steps==0`、`refused_within_bound` 真、当天 VERIFIED。"""
        w = RefusedWorld(refused=self.REFUSED3, seeds=10, money=500)
        run = self._run(w)
        self.assertEqual(run.run(), 0, [d.checks for d in run.days])
        rep = run.days[0]
        self.assertEqual(rep.failed_steps, 0, rep.stages)
        self.assertEqual(rep.refused, 3, rep.stages)
        self.assertEqual({tuple(t) for t in rep.refused_tiles}, set(self.REFUSED3))
        self.assertTrue(rep.checks["refused_within_bound"], rep.checks)
        self.assertIs(rep.checks["no_hard_failures"], True, rep.checks)
        self.assertIs(rep.checks["no_unmet_stages"], True,
                      "拒绝格在界内 ⇒ 不许因为「还剩 3 格」把好日子判死")
        self.assertTrue(rep.verified, f"{rep.checks} / {rep.stages}")
        per = self._events(run, "tool_refused")
        self.assertEqual({tuple(e["tile"]) for e in per}, set(self.REFUSED3), per)
        self.assertTrue(all(e["status"] == "tool_ineffective" for e in per), per)
        self.assertTrue(all("游戏判定这格锄不动" in str(e["reason"]) for e in per), per)
        day_end = self._events(run, "day_end")[-1]
        for key in ("refused", "refused_tiles", "refused_bound", "refused_exempt"):
            self.assertIn(key, day_end, f"day_end 缺 {key}")
        self.assertEqual(day_end["refused"], 3)
        self.assertGreater(day_end["refused_bound"], 0)

    def test_exceeding_the_bound_trips_the_check_and_kills_verification(self):
        """25 格全被拒绝、0 成功 ⇒ 25 > `max(5, 20%×attempted)` ⇒ 越界判据亮、不得 VERIFIED。"""
        all_tiles = [(60 + i, 10 + j) for i in range(5) for j in range(5)]
        w = RefusedWorld(refused=all_tiles, seeds=10, money=500)
        run = self._run(w)
        run.run()
        rep = run.days[0]
        self.assertEqual(rep.ok_steps, 0, rep.stages)
        self.assertGreater(rep.refused, rep.refused_bound, (rep.refused, rep.refused_bound))
        self.assertIs(rep.checks["refused_within_bound"], False, rep.checks)
        self.assertIs(rep.checks["no_hard_failures"], False,
                      "超界不许靠「游戏全拒绝」换来 no_hard_failures=true")
        self.assertIs(rep.verified, False)

    def test_within_bound_but_zero_success_is_still_never_verified(self):
        """防真空：5 格被拒绝（正好在上界内）+ 0 成功 ⇒ 豁免不许把这一天洗成达标。"""
        w = RefusedWorld(refused=self.FIVE, seeds=10, money=500, tillable=self.FIVE)
        run = self._run(w)
        run.run()
        rep = run.days[0]
        self.assertEqual(rep.ok_steps, 0, rep.stages)
        self.assertEqual(rep.refused, 5)
        self.assertTrue(rep.checks["refused_within_bound"], rep.checks)
        self.assertIs(rep.checks["no_unmet_stages"], False,
                      "全是拒绝 + 0 成功：豁免再宽也不许自证")
        self.assertIs(rep.verified, False)

    def test_next_day_retries_the_same_refused_tiles(self):
        """`blocked` 每天清空 ⇒ 次日必须**再试**（工具等级/前置条件可能变了，不许永久封格）。"""
        refused = [(60, 10), (61, 10)]
        # 只留 4 格可开垦（2 格被拒 + 2 格正常）：第二天不会有"一片还没浇完的作物"把一整天
        # 都吃掉，`till_area` 一定轮得到这 2 格（否则测的就不是"次日重试"了）。
        w = RefusedWorld(refused=refused, seeds=10, money=500,
                         tillable=[(60, 10), (61, 10), (62, 10), (63, 10)])
        run = self._run(w, target_days=2, max_days=3)
        run.run()
        self.assertGreaterEqual(len(run.days), 2, run.days)
        self.assertEqual({tuple(t) for t in run.days[0].refused_tiles}, set(refused))
        self.assertEqual({tuple(t) for t in run.days[1].refused_tiles}, set(refused),
                         "次日没有重试这 2 格 ⇒ 变成了永久封格")
        self.assertGreaterEqual(len(self._events(run, "tool_refused")), 4)
        self.assertEqual(len(self._events(run, "refused_summary")), 2, run.entries)

    def test_refused_and_unreachable_are_counted_separately(self):
        """两套豁免**互不覆盖**：被拒绝的格与走不到的格各记各的，journal/账本都不串。"""
        refused = [(60, 10), (61, 10)]
        unreach = [(63, 12)]
        w = RefusedWorld(refused=refused, seeds=10, money=500)
        w.blockers[unreach[0]] = "weed"
        client = _UnreachableClient(w, unreachable=unreach)
        run = self._run(w, client=client)
        run.run()
        rep = run.days[0]
        self.assertEqual(rep.refused, 2, rep.stages)
        self.assertEqual({tuple(t) for t in rep.refused_tiles}, set(refused))
        self.assertEqual(rep.unreachable, 1, rep.stages)
        self.assertEqual({tuple(t) for t in rep.unreachable_tiles}, set(unreach))
        self.assertEqual(rep.failed_steps, 0, rep.stages)
        refused_ev = {tuple(e["tile"]) for e in self._events(run, "tool_refused")}
        unreach_ev = {tuple(e["tile"]) for e in self._events(run, "unreachable")}
        self.assertEqual(refused_ev, set(refused), run.entries)
        self.assertEqual(unreach_ev, set(unreach), run.entries)
        self.assertEqual(refused_ev & unreach_ev, set())
        sums = self._events(run, "refused_summary")
        self.assertEqual(len(sums), 1, run.entries)
        self.assertEqual(sums[0]["count"], 2)
        self.assertNotEqual(sums[0]["exempted"], rep.unreachable_exempt + 999,
                            "两套豁免各扣各的：refused_summary 只报 refused 的实扣")


class TestTask67SeedChoice(unittest.TestCase):
    """task-67：脑自己挑"当季、买得起"的种子（run6 死锁：夏季硬买春季 `472`，每天白试 6 次）。

    变异自检（脚本 `scratch/_t67_mutate.py`，跑完即弃）：

    * **m67a**（`is_seed_offer` 恒 True：不按名字筛）⇒ `test_shelf_without_seeds_is_not_bought` 红；
    * **m67b**（`_seed_outlook` 去掉 `not self.seed_dead_today` 的门）⇒
      `test_seed_dead_today_disarms_the_reason` 红（守卫又被"该去买"钉死）。
    """

    SUMMER = [{"id": "(O)254", "name": "Melon Seeds", "price": 80},
              {"id": "(O)483", "name": "Wheat Seeds", "price": 10}]
    TOOL_OFFERS = [{"id": "(O)24", "name": "Parsnip", "price": 20},
                   {"id": "(O)60", "name": "Emerald", "price": 250}]

    @staticmethod
    def _run(w: FakeWorld) -> LongRun:
        run = make_run(w, target_days=1)
        run.worker = FakeWorker(w)
        return run

    @staticmethod
    def _events(run: LongRun, event: str) -> list[dict]:
        return [e for e in run.entries if e.get("event") == event]

    def test_picks_a_shelf_item_instead_of_hardcoded_472(self):
        """夏季货架 ⇒ 买货架上最便宜的那件（`(O)483`），**不是**配置里的 472。"""
        w = FakeWorld(weeds=0, seeds=0, money=500)
        w.buy_offers = list(self.SUMMER)
        run = self._run(w)
        run._preconditions(w.obs(), DayReport(day_key=("spring", 1, 5), started_at=0.0))
        self.assertEqual([c["item"] for c in w.buy_calls], ["472", "(O)483"],
                         "先探一次配置项（被商店拒绝），再照货架换一个 id")
        self.assertEqual(run.shop_offers, self.SUMMER, "回执里的货架要留下（跨天保留）")
        buy = self._events(run, "buy")
        self.assertEqual(len(buy), 2, "被拒那次 + 真买到那次都留痕")
        self.assertEqual(buy[-1]["item"], "(O)483")
        self.assertEqual(buy[-1]["price"], 10)
        self.assertEqual(buy[-1]["source"], "shelf")
        self.assertFalse(buy[0]["ok"], "探测失败要如实记")
        self.assertTrue(w.buys, "真买到了")

    def test_cached_shelf_is_used_without_probing(self):
        """手上有货架清单 ⇒ 直接挑，连"探一次"都不用（旧桥的探路请求是纯浪费）。"""
        w = FakeWorld(weeds=0, seeds=0, money=500)
        run = self._run(w)
        run.shop_offers = list(self.SUMMER)
        run._preconditions(w.obs(), DayReport(day_key=("spring", 1, 5), started_at=0.0))
        self.assertEqual([c["item"] for c in w.buy_calls], ["(O)483"])

    def test_shelf_without_seeds_is_not_bought(self):
        """货架只有作物/矿物 ⇒ `no_seed_for_sale` + **一次买都不发**（run6 一天 6 次就这么浪费的）。"""
        w = FakeWorld(weeds=0, seeds=0, money=500)
        w.buy_offers = list(self.TOOL_OFFERS)
        run = self._run(w)
        run._preconditions(w.obs(), DayReport(day_key=("spring", 1, 5), started_at=0.0))
        self.assertEqual([c["item"] for c in w.buy_calls], ["472"],
                         "只探一次（探完就知道货架没种子），不再重复发请求")
        self.assertEqual(run.seed_dead_today, "no_seed_for_sale")
        self.assertEqual(len(self._events(run, "no_seed_for_sale")), 1)

    def test_cannot_afford_does_not_buy(self):
        """有种子但攒不够 10 包的钱 ⇒ `cannot_afford`，不买。"""
        w = FakeWorld(weeds=0, seeds=0, money=100)     # 预算 10 < 最便宜的 40
        w.buy_offers = [{"id": "(O)482", "name": "Pepper Seeds", "price": 40}]
        run = self._run(w)
        run._preconditions(w.obs(), DayReport(day_key=("spring", 1, 5), started_at=0.0))
        self.assertEqual([c["item"] for c in w.buy_calls], ["472"], "探了一次就够")
        self.assertEqual(run.seed_dead_today, "cannot_afford")
        self.assertEqual(len(self._events(run, "cannot_afford")), 1)

    def test_seed_dead_today_disarms_the_reason(self):
        """run6 死锁的解药：确认买不到之后，"该去买种子"这条理由**当天失效**。"""
        w = FakeWorld(weeds=0, seeds=0, money=500)
        w.buy_offers = list(self.TOOL_OFFERS)
        run = self._run(w)
        run._preconditions(w.obs(), DayReport(day_key=("spring", 1, 5), started_at=0.0))
        reasons = run.work_reasons(w.obs())
        self.assertNotIn("该去买", "；".join(reasons), f"买不到就不该再要求去买：{reasons}")
        # 只留痕一次（`work_reasons` 每轮都被调用，不刷屏）
        run.work_reasons(w.obs())
        self.assertEqual(len(self._events(run, "seed_unavailable_today")), 1)
        # 守卫不再被这条不可满足的理由钉死
        _can, _code, why = run.sleep_guard(w.obs())
        self.assertNotIn("该去买", why)
        # 当天也不再发 buy（`_preconditions` 直接返回；只剩最开始那一次探测）
        run._preconditions(w.obs(), DayReport(day_key=("spring", 1, 5), started_at=0.0))
        self.assertEqual([c["item"] for c in w.buy_calls], ["472"], "当天不再发起 buy")

    def test_next_day_retries_once(self):
        """次日重试一次：`_run_day` 每天清空 `seed_dead_today`（明天可能上架新种子）。"""
        w = FakeWorld(weeds=0, seeds=0, money=500)
        w.buy_offers = list(self.SUMMER)
        run = self._run(w)
        rep = DayReport(day_key=("spring", 1, 5), started_at=0.0)
        run._preconditions(w.obs(), rep)
        first = len(w.buy_calls)
        self.assertEqual(first, 2, "探测被拒一次 + 照货架买到一次")
        run._preconditions(w.obs(), rep)               # 同一天再问：已有种子 ⇒ 不动
        self.assertEqual(len(w.buy_calls), first)
        # 模拟跨日重置（`_run_day` 每天做的事）
        run.seed_dead_today = ""
        run.seed_dead_noted = False
        w.money = 500
        w.inventory = [i for i in w.inventory
                       if not i or "Seed" not in str(i.get("name") or "")]
        run._preconditions(w.obs(), rep)
        self.assertEqual(len(w.buy_calls), first + 1, "次日应该再试一次")


class EncircledWorld(FakeWorld):
    """run6 的「被围住」：目标格（枯死作物）四邻是树/桩一类 —— 不在 `FRONTIER_KINDS`、也没落脚点。

    真机依据（`logs\\longrun-3day-llm-run6.jsonl`）：`field_ne` 的 42 格枯死作物全部"走不到"，
    农场被草 432/石 169/枝 92/树 356 堵住 ⇒ `clear_dead` 一次 ok 都没有。其中"四邻是树、连落脚
    点都没有"的那些**不是**不可达（明天/开路后就可能变）：归 `encircled` 单独计数、不封格、
    也不许进 `unreachable_exempt` 分子。
    """

    def __init__(self, *, enclosed=(), ring="tree", **kw) -> None:
        kw.setdefault("weeds", 0)
        super().__init__(**kw)
        self.enclosed = {tuple(t) for t in enclosed}
        self.ring_kind = ring
        for t in sorted(self.enclosed):
            self.dirt.add(t)
            self.crops[t] = {"ripe": False, "watered": True, "dead": True}
            for dx, dy in _NB4:
                self.blockers[(t[0] + dx, t[1] + dy)] = ring

    def obs(self) -> dict:
        o = super().obs()
        for tv in o["location"]["tiles"]:
            if tv.get("kind") in ("tree", "clump"):
                tv["standable"] = False          # 树/桩上站不住（`_standable_near` 的判据）
        return o


class TestTask68Encircled(unittest.TestCase):
    """task-68（Lead m06336）：`encircled` 是与 `unreachable` **并列的新类**，口径必须分得清。

    * `encircled`：四邻**连落脚点都没有**（树/桩/大石）⇒ 不封格、不进 `blocked`、
      不进 `unreachable_exempt` 分子（否则"被围住"会吃掉不可达的豁免额度，把真·不可达洗白）。
    * `exhausted`：有落脚点、但开路到上限仍不通 ⇒ 仍按 task-52 的 `unreachable`（**有界**）。

    变异自检（**实测**，脚本 `scratch\\_t68_mutate.py`，基线 11/11 绿）：
    `m68a`（短路 `open_way`）**5 条红**；`m68b`（`encircled` 并进 `exhausted`）**3 条红**；
    `m68c`（`_mark_blocked` 不认 `s.encircled`）**1 条红** = `test_encircled_never_enters_blocked`。
    """

    ENCLOSED = (62, 12)

    def _world(self) -> EncircledWorld:
        return EncircledWorld(enclosed=[self.ENCLOSED], seeds=0, money=0)

    def _run(self, w: FakeWorld):
        client = _UnreachableClient(w, unreachable=getattr(w, "enclosed", ()))
        worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
        run = make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker,
                       target_days=1, max_days=1)
        run.worker = worker
        run.client = client
        return run

    @staticmethod
    def _events(run: LongRun, event: str) -> list:
        return [e for e in run.entries if e.get("event") == event]

    def _plot(self) -> dict:
        return {"zone": "", "label": "", "anchor": list(self.ENCLOSED),
                "tiles": [tuple(self.ENCLOSED)], "note": ""}

    def test_encircled_never_enters_blocked(self):
        """四邻全树 ⇒ `code=encircled`、逐格 journal `encircled`、**不写 `blocked`**、不算失败。"""
        w = self._world()
        run = self._run(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        out = run._step_stage("clear_dead", w.obs(), self._plot(), rep)
        tile = tuple(self.ENCLOSED)
        self.assertNotIn(tile, run.blocked, "encircled 不许封格（明天/开路后可能变可达）")
        st = rep.stages[-1]
        self.assertEqual(st["encircled"], 1, st)
        self.assertEqual({tuple(t) for t in st["encircled_tiles"]}, {tile})
        self.assertEqual(st["failed"], 0, "被围住不是硬失败")
        self.assertEqual(st["unreachable"], 0, "encircled 与 unreachable 是两套独立计数")
        self.assertFalse(out.postcondition_met)
        per = self._events(run, "encircled")
        self.assertEqual([tuple(e["tile"]) for e in per], [tile], per)
        self.assertNotIn("unreachable", [e.get("event") for e in run.entries], run.entries[-3:])

    def test_encircled_is_reported_but_does_not_exempt_unreachable(self):
        """跑完一天：`day_end` 有 `encircled` 两键、有 `encircled_summary`，且不进不可达豁免。"""
        w = self._world()
        run = self._run(w)
        run.run()
        rep = run.days[0]
        self.assertEqual(rep.encircled, 1, rep.stages)
        self.assertEqual({tuple(t) for t in rep.encircled_tiles}, {tuple(self.ENCLOSED)})
        self.assertEqual(rep.unreachable, 0, "围住 ≠ 走不到：不许混进 unreachable 账本")
        self.assertEqual(rep.unreachable_exempt, 0, "encircled 不许占不可达豁免额度")
        self.assertEqual(rep.failed_steps, 0)
        day_end = self._events(run, "day_end")[-1]
        for key in ("encircled", "encircled_tiles"):
            self.assertIn(key, day_end, f"day_end 缺 {key}")
        self.assertEqual(day_end["encircled"], 1)
        summary = self._events(run, "encircled_summary")
        self.assertEqual(len(summary), 1, summary)
        self.assertEqual(summary[0]["count"], 1)
        for key in ("attempted", "engaged"):
            self.assertIn(key, summary[0], "分母与「站过」的证据都要留痕（口径可复核）")


class TestTask68FrontierClear(unittest.TestCase):
    """task-68「一轮不许零动作」：目标全够不着时，先清一格**可达的**可清障格（有界 ≤20/天）。

    三个层次都测：`_frontier_clear` 真清一格 / 到日上限就停 / 没有可达候选时**不硬造动作**；
    再加一条 day 级：作业区里的目标恒被 `ui_modal` 挡住（不封格、不占配额、世界不变）⇒ 走到
    `idle_rounds>=3` 那一支时必须转去 `frontier_clear`，而不是像 run6 那样 19 秒收工。
    """

    def _run(self, w: FakeWorld):
        client = FakeClient(w)
        worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
        run = make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker)
        run.worker = worker
        run.client = client
        return run

    @staticmethod
    def _events(run: LongRun, event: str) -> list:
        return [e for e in run.entries if e.get("event") == event]

    def test_clears_one_reachable_blocker(self):
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.blockers[(61, 10)] = "weed"
        w.player_tile = [62, 12]
        run = self._run(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        self.assertTrue(run._frontier_clear(w.obs(), rep))
        self.assertEqual(run.frontier_clears, 1)
        self.assertNotIn((61, 10), w.blockers, "frontier_clear 必须真的清掉一格")
        ev = self._events(run, "frontier_clear")
        self.assertEqual(len(ev), 1, ev)
        self.assertEqual(ev[0]["tile"], [61, 10])
        self.assertIs(ev[0]["acted"], True)
        self.assertEqual(ev[0]["limit"], FRONTIER_CLEAR_MAX)

    def test_bounded_by_daily_cap(self):
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.blockers[(61, 10)] = "weed"
        w.player_tile = [62, 12]
        run = self._run(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        run.frontier_clears = FRONTIER_CLEAR_MAX
        self.assertFalse(run._frontier_clear(w.obs(), rep))
        self.assertIn((61, 10), w.blockers, "到上限就该停手，不许无限清障")
        self.assertEqual(self._events(run, "frontier_clear"), [])

    def test_no_reachable_frontier_means_no_action(self):
        """没有任何可达的可清障格 ⇒ 不许硬造动作（那天该按诚实理由收尾）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        run = self._run(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        self.assertFalse(run._frontier_clear(w.obs(), rep))
        self.assertEqual(run.frontier_clears, 0)

    def test_all_targets_unreachable_still_clears_a_reachable_one(self):
        """Lead m06336③「一轮不许零动作」：守卫说有活、却拿不出作业区目标 ⇒ 必须去清一格可达的。

        复现 run6 的形态：`field_ne` 的目标全够不着（`unreachable`），而农场里还有可达的杂草。
        为了确定性地打中那条接线（而不是让 `_ensure_plot` 换片地把它当阶段目标），这里把
        `_ensure_plot` 钉成 `None`、`work_reasons` 钉成"还有活" —— 正是 run6 那两句旁白。
        """
        w = UnreachableWorld(unreachable=[(60, 10)], seeds=0, money=0)
        w.blockers[(70, 10)] = "weed"
        # 作业区那一格"环境挡路"（`ui_modal`）：它**不封格、不占配额**（task-22 口径）⇒ 每轮都被
        # 重新选中、世界却一点都不变 ⇒ 正是"指定目标够不着 + 有可达的可清障格"的僵局。
        w.fail_status[(60, 10)] = "ui_modal"
        client = _UnreachableClient(w, unreachable=w.unreachable)
        worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
        run = make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker,
                       target_days=1, max_days=1)
        run.worker = worker
        run.client = client
        # 把作业区钉在这一格上：否则 `_ensure_plot` 会换片地，走的是另一条"换 11 片地"的守卫。
        run._ensure_plot = lambda obs, rep: {"zone": "", "label": "", "anchor": [62, 12],
                                             "tiles": [(60, 10)], "note": ""}
        run.run()
        ev = self._events(run, "frontier_clear")
        self.assertTrue(ev, f"目标够不着 + 有可达的可清障格却零动作：{run.days[0].ended_reason}")
        self.assertEqual(ev[0]["tile"], [70, 10])
        self.assertIs(ev[0]["acted"], True)
        self.assertNotIn((70, 10), w.blockers, "frontier_clear 必须真的清掉那一格")
        self.assertGreaterEqual(run.frontier_clears, 1)
        self.assertNotEqual(run.days[0].ended_by, "no_work", "有可达的活就不许按「没活」收工")

    def test_engaged_is_evidence_not_the_bound_denominator(self):
        """`engaged`（真站到过目标旁边）只作证据：`unreachable_summary` 同时带 `attempted` 与 `engaged`。"""
        w = UnreachableWorld(unreachable=[(60, 10), (61, 10)], seeds=0, money=0)
        client = _UnreachableClient(w, unreachable=w.unreachable)
        worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
        run = make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker,
                       target_days=1, max_days=1)
        run.worker = worker
        run.client = client
        run.run()
        summary = self._events(run, "unreachable_summary")
        self.assertEqual(len(summary), 1, summary)
        self.assertEqual(summary[0]["attempted"], 2)
        self.assertEqual(summary[0]["engaged"], 0, "压根没走到跟前 ⇒ engaged 必须为 0")
        rep = run.days[0]
        self.assertEqual(rep.unreachable, 2)
        # 分母仍是既有口径 `attempted`（工具/分析器按它对账），没有换成 engaged
        self.assertGreaterEqual(rep.unreachable_bound, max(5, int(0.2 * 2)))
        st = [s for s in rep.stages if s.get("attempted")][0]
        self.assertIn("engaged", st)
        self.assertLessEqual(st["engaged"], st["attempted"])


class TestTask73StuckFlush(unittest.TestCase):
    """task-73：stuck 日**有界翻篇** —— 睡过去让整轮继续，而不是 run6 那样 19 秒终止。

    背景（run6 真机 `logs/longrun-3day-llm-run6.jsonl`）：两个 `day_end` 都是 `ended_by=stuck`
    （42 格够不着、`clear_dead` 一格 ok 都没有），随后外层 `run()` 命中
    `prev_key == self._last_day_key` ⇒ 写 `no_day_progress` 并 **break 整轮**：游戏日根本没往前
    走（没睡），一次「撞上一片走不到的簇」就让无人值守在 19 秒内结束，连"明天再试"的机会都没有。

    这里补的正是"翻篇"：`_stuck_flush` 刻意**绕过 `sleep_guard`**（守卫此刻仍会说有活）睡一觉、
    把游戏日推一格，让外层继续；但**验收一个字不放宽** —— 这一天 `ended_by` 仍是 `stuck`、
    `checks["day_justified"] is False`、`verified is False`，绝不许洗成 `no_work`/`night`/`stamina`。

    变异自检（`%TEMP%\t73_mutate.py`，复制 brain+tests 到临时目录做文本替换，跑完即删；实测
    2026-10-14）：

    * `m73a`：把 `if self.stuck_flushes >= MAX_STUCK_FLUSH:` 改成 `if False:`（去掉整轮上界）
      ⇒ **红 2**（`test_flush_is_bounded_by_max_stuck_flush` + `test_flushed_day_is_still_stuck_and_never_verified`）。
    * `m73b`：翻篇成功后把 `rep.ended_by` 改写成 `"sleep"`（把"睡过去"洗成正常收工）
      ⇒ **红 1**（`test_flushed_day_is_still_stuck_and_never_verified`）。
    * 基线：本类 4 条全绿。
    """

    @staticmethod
    def _events(run: LongRun, event: str) -> list[dict]:
        return [e for e in run.entries if e.get("event") == event]

    @staticmethod
    def _day_key_of(world: FakeWorld) -> list:
        return [int(v) if str(v).isdigit() else str(v) for v in FarmWorker.day_key(world.obs())]

    def _run_for(self, w: FakeWorld):
        client = FakeClient(w)
        worker = FakeWorker(w)
        run = make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker,
                       target_days=1, max_days=1)
        run.worker = worker
        run.client = client
        return run

    def test_flush_sleeps_and_advances_the_game_day(self):
        """翻篇 = 真的睡了一觉、游戏日 +1，且账本（`stuck_flushes`/`day_after`）落下来。"""
        w = FakeWorld()
        run = self._run_for(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        self.assertTrue(run._stuck_flush(w.obs(), rep, "stuck:测试"))
        self.assertEqual(run.stuck_flushes, 1)
        self.assertEqual(w.day, 7, "翻篇必须真的把游戏日推一格（默认 spring 6）")
        self.assertIs(rep.stuck_flushed, True)
        self.assertEqual(rep.day_after, self._day_key_of(w))
        ev = self._events(run, "stuck_flush")
        self.assertEqual(len(ev), 1, ev)
        self.assertIs(ev[0]["ok"], True)
        self.assertEqual(ev[0]["count"], 1)
        self.assertEqual(ev[0]["limit"], MAX_STUCK_FLUSH)
        self.assertEqual(ev[0]["day_after"], self._day_key_of(w))
        self.assertIn("sleep_guard", ev[0]["note"], "绕过 sleep_guard 的理由必须写进 journal")

    def test_flush_is_bounded_by_max_stuck_flush(self):
        """整轮最多 `MAX_STUCK_FLUSH` 次：到顶后不再睡，如实维持现状（外层照旧终止）。"""
        w = FakeWorld()
        run = self._run_for(w)
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        run.stuck_flushes = MAX_STUCK_FLUSH
        self.assertFalse(run._stuck_flush(w.obs(), rep, "stuck:到顶"))
        self.assertEqual(w.day, 6, "到顶后绝不许再睡一天")
        self.assertIs(rep.stuck_flushed, False)
        self.assertEqual(self._events(run, "stuck_flush"), [])
        skipped = self._events(run, "stuck_flush_skipped")
        self.assertEqual(len(skipped), 1, skipped)
        self.assertEqual(skipped[0]["count"], MAX_STUCK_FLUSH)
        self.assertEqual(skipped[0]["limit"], MAX_STUCK_FLUSH)

    def test_never_flushes_during_a_game_event_or_a_save_modal(self):
        """task-41/task-11 不回归：`eventUp=true` 与只等不关的存档模态期间**绝不**翻篇。"""
        w = FakeWorld()
        run = self._run_for(w)
        base = w.obs()
        event_obs = {**base, "ui": {**base.get("ui", {}), "eventUp": True}}
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        self.assertFalse(run._stuck_flush(event_obs, rep, "stuck:事件"))
        self.assertEqual(w.day, 6)
        self.assertEqual(run.stuck_flushes, 0)
        self.assertEqual(self._events(run, "stuck_flush_skipped")[0]["reason"], "eventUp=true")
        # 存档类模态（只等不关）：同样一次都不许睡
        run2 = self._run_for(FakeWorld())
        save_obs = {**base, "ui": {**base.get("ui", {}), "activeMenu": "SaveGameMenu"}}
        rep2 = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        self.assertFalse(run2._stuck_flush(save_obs, rep2, "stuck:存档"))
        self.assertEqual(run2.stuck_flushes, 0)
        self.assertIn("SaveGameMenu", self._events(run2, "stuck_flush_skipped")[0]["reason"])

    def test_flushed_day_is_still_stuck_and_never_verified(self):
        """day 级：stuck 日翻篇后整轮**继续**（不再 19 秒 `no_day_progress` 终止）。

        复现 run6 的形态：作业区目标恒被 `ui_modal` 挡住（env 挡路 ⇒ 不封格、不占配额、世界
        永不变），而且**没有**任何可达的可清障格 ⇒ `_frontier_clear` 也拿不出动作 ⇒ 走到
        `idle_rounds>=3` 那一支。翻篇把游戏日推了一格（第 6 天 → 第 7 天），所以总控**不该**
        在第 1 天就写 `no_day_progress`；但这一天仍如实算 `stuck`：`day_justified is False`、
        `verified is False`。到了整轮上限（`MAX_STUCK_FLUSH`）之后才允许终止。
        """
        w = FakeWorld(weeds=0, seeds=0, money=0)
        # 作业区那一格"环境挡路"（`ui_modal`）：**不封格、不占配额**（task-22 口径）⇒ 每轮都被
        # 重新选中、世界却一点都不变 ⇒ 累计 `idle_rounds`，正是 run6 的僵局形态。而且这里**没有**
        # 任何可达的可清障格 ⇒ `_frontier_clear` 也拿不出动作，只能靠 task-73 的"翻篇"。
        w.blockers[(60, 10)] = "weed"
        w.fail_status[(60, 10)] = "ui_modal"
        client = FakeClient(w)
        worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
        run = make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker,
                       target_days=1, max_days=4)
        run.worker = worker
        run.client = client
        # 三个 seam，把"三轮下来世界一点没变"这件事**确定化**（`idle_rounds` 量的正是它）：
        #   ① 作业区钉在那一格（否则 `_ensure_plot` 会换片地，走的是 task-49 那条"换 11 片地"出口）；
        #   ② `_execute` 不落地任何动作（真机里对应"目标恒被环境挡住 ⇒ 每次都没改变世界"）；
        #   ③ 世界指纹冻结（`changed` 恒假 ⇒ 连续 3 轮后进 idle 分支）。
        # 被 seam 掉的只有"执行/指纹"这两件事，"判 stuck 之后干什么"完全走生产代码。
        run._ensure_plot = lambda obs, rep: {"zone": "", "label": "", "anchor": [62, 12],
                                             "tiles": [(60, 10)], "note": ""}
        run._execute = lambda decision, obs, plot, rep: True
        run._fingerprint = lambda obs: "frozen"
        run.run()
        first = run.days[0]
        self.assertEqual(first.ended_by, "stuck", "翻篇不许把这一天洗成别的结局")
        self.assertIs(first.checks["day_justified"], False, "翻篇不是「收工有正当理由」")
        self.assertIs(first.verified, False)
        self.assertIs(first.stuck_flushed, True)
        flushes = self._events(run, "stuck_flush")
        self.assertEqual(len(flushes), MAX_STUCK_FLUSH, flushes)
        self.assertIs(flushes[0]["ok"], True)
        self.assertEqual(flushes[0]["day_after"], [1, "spring", 7])
        self.assertEqual(flushes[1]["day_after"], [1, "spring", 8])
        # 翻篇把游戏日一天一天推着走 ⇒ 整轮**没有**在第 1 天就 19 秒终止（run6 的病灶）
        self.assertGreaterEqual(len(run.days), 3, "翻篇后必须继续跑下一天，而不是当场终止")
        self.assertEqual(w.day, 6 + MAX_STUCK_FLUSH, "每个翻篇日推一格游戏日")
        # 有界：到整轮上限后如实维持现状终止（不是无限睡），并且 `no_day_progress` 只出现在最后
        self.assertEqual(run.stuck_flushes, MAX_STUCK_FLUSH)
        self.assertEqual(len(self._events(run, "no_day_progress")), 1)
        self.assertEqual(run.summary["stuck_flushes"], run.stuck_flushes)


class TestTask78BoundBasis(unittest.TestCase):
    """task-78 NIT-1（deputy 的伪造账本 V5）：豁免上界的**分母**必须是 `bound_basis`。

    病灶：两套 bound 原来都用 `max(5, floor(0.2×attempted))`，而 `attempted` 把 `encircled`
    步也算进去 ⇒ 800 次 `encircled` 能把上界抬到 200，200 格真不可达被豁免、当天 VERIFIED。
    修法：`bound_basis = Σ(阶段里 attempted 且**不是** encircled 的步数)`，两套 bound 改用它；
    `attempted` 的语义一字不动（它仍是"发起过的步数"的**证据**）。

    本用例把两个数**都造出来**：20 格被围住（`encircled`，会被重试 ⇒ 实际几十次）+ 2 格真
    不可达 ⇒ 按 `bound_basis`（=2）算界是 `max(5, 0) = 5`，按旧的 `attempted` 算界会到 8+。
    """

    def _world(self):
        enclosed = [(60 + 3 * i, 30) for i in range(20)]
        w = EncircledWorld(enclosed=enclosed, seeds=0, money=0)
        # 2 格真不可达：目标格周围**没有观测**（`_standable_near` 为真 ⇒ 不是 encircled），
        # 但四邻都在 `_UnreachableClient` 的"移动必被拒"名单里 ⇒ 开路也没得清 ⇒ `exhausted`
        # ⇒ 归 task-52 的 `unreachable`（有界、当日封格、次日重试）。
        far = [(66, 40), (70, 40)]
        for t in far:
            w.dirt.add(t)
            w.crops[t] = {"ripe": False, "watered": True, "dead": True}
        blocked_moves = set(far)
        for t in far:
            for dx, dy in _NB4:
                blocked_moves.add((t[0] + dx, t[1] + dy))
        return w, set(far), blocked_moves

    def _run(self, w, blocked_moves):
        # `_UnreachableClient` 会把名单里每一格的**四邻**也拉黑 ⇒ 把被围住的也算进去，
        # 它们才走得进"站不过去 ⇒ 先开路 ⇒ 没突破口 ⇒ encircled"这条路。
        client = _UnreachableClient(w, unreachable=blocked_moves | set(w.enclosed))
        worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
        run = make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker,
                       target_days=1, max_days=1, per_stage_tiles=200, max_stage_rounds=2)
        run.worker = worker
        run.client = client
        return run

    @staticmethod
    def _events(run, event: str) -> list:
        return [e for e in run.entries if e.get("event") == event]

    def test_encircled_never_inflates_the_exemption_bound(self):
        """20 格 encircled + 2 格真 unreachable ⇒ 界仍按 5 算，那 2 格才被豁免。"""
        w, far, blocked = self._world()
        run = self._run(w, blocked)
        targets = sorted(w.enclosed | far)
        run._ensure_plot = lambda obs, rep: {"zone": "", "label": "",
                                             "anchor": list(targets[0]),
                                             "tiles": targets, "note": ""}
        run.run()
        rep = run.days[0]
        attempted = sum(int(st.get("attempted") or 0) for st in rep.stages)
        encircled = sum(int(st.get("encircled") or 0) for st in rep.stages)
        self.assertGreaterEqual(encircled, 20, f"被围住的格子必须真的被记成 encircled：{rep.stages}")
        self.assertEqual(rep.unreachable, 2, "只有那 2 格是真·走不到")
        self.assertEqual(rep.bound_basis, attempted - encircled, "bound_basis = attempted − encircled")
        self.assertEqual(rep.unreachable_bound, 5, "界按 bound_basis 算（2 ⇒ 下限 5）")
        self.assertLess(rep.unreachable_bound, max(5, int(0.2 * attempted)),
                        "旧口径（attempted 当分母）会把界抬高 ⇒ 这条断言就是 NIT-1 的证伪点")
        self.assertEqual(rep.unreachable_exempt, 2, "那 2 格才该被豁免")
        self.assertEqual({tuple(t) for t in rep.unreachable_tiles}, far)

    def test_bound_basis_is_written_to_the_ledger(self):
        """`day_end` 与三个 summary 都要带 `bound_basis`（工具侧照它复核）。"""
        w, far, blocked = self._world()
        run = self._run(w, blocked)
        targets = sorted(w.enclosed | far)
        run._ensure_plot = lambda obs, rep: {"zone": "", "label": "",
                                             "anchor": list(targets[0]),
                                             "tiles": targets, "note": ""}
        run.run()
        rep = run.days[0]
        day_end = self._events(run, "day_end")[-1]
        self.assertEqual(day_end["bound_basis"], rep.bound_basis)
        for name in ("unreachable_summary", "encircled_summary"):
            got = self._events(run, name)
            self.assertEqual(len(got), 1, (name, got))
            self.assertEqual(got[0]["bound_basis"], rep.bound_basis, name)
        # 记账口径可复核：阶段账本里也留着 `bound_basis`
        for st in rep.stages:
            self.assertIn("bound_basis", st, st)
        # 既有闸门的方向与存在性一个字没改（task-52/task-63 的断言口径）
        self.assertIn("unreachable_within_bound", rep.checks)
        self.assertIsInstance(rep.checks["unreachable_within_bound"], bool)

    def test_bound_formula_matches_the_ledger(self):
        """两套界都必须**逐字**从 `bound_basis` 推出来（不是从 `attempted`）。

        `attempted` 的语义一字没动（它仍是"发起过多少步"的证据，`unreachable_summary` 里
        与 `engaged` 并列）；这里把公式钉死，防止哪天被人改回 `attempted` 当分母。
        """
        w, far, blocked = self._world()
        run = self._run(w, blocked)
        targets = sorted(w.enclosed | far)
        run._ensure_plot = lambda obs, rep: {"zone": "", "label": "",
                                             "anchor": list(targets[0]),
                                             "tiles": targets, "note": ""}
        run.run()
        rep = run.days[0]
        attempted = sum(int(st.get("attempted") or 0) for st in rep.stages)
        self.assertLessEqual(rep.bound_basis, attempted)
        self.assertEqual(rep.unreachable_bound, max(5, int(0.2 * rep.bound_basis)))
        self.assertEqual(rep.refused_bound, max(5, int(0.2 * rep.bound_basis)))
        self.assertNotEqual(rep.unreachable_bound, max(5, int(0.2 * attempted)),
                            "这条差值就是 NIT-1 的证伪点：分母不能是 attempted")


class WeedRingWorld(FakeWorld):
    """task-78 NIT-2 的 deputy 实证形态：目标格是枯死作物，四邻是 `weed`，**但那些邻格自己也站不上去**。

    与 `EncircledWorld`（四邻是树/桩）的区别就在这里：被围住的原因**不是**树/桩/大石，
    而是"可清障类邻格 + 没有落脚点" ⇒ 一次都没挥过。所以 reason/journal 不许再断言
    "树/桩/大石一类"，要照观测写真实 kind（这里四邻都是 `weed`）。
    """

    def __init__(self, *, tile) -> None:
        super().__init__(weeds=0, seeds=0, money=0)
        self.target = (int(tile[0]), int(tile[1]))
        self.dirt.add(self.target)
        self.crops[self.target] = {"ripe": False, "watered": True, "dead": True}
        # 半径 3 内的每一格都观测成"站不住"（目标格自己也是 —— 枯死作物格上站不上去），
        # 这样四邻既清不了（没有落脚点去站它旁边）也当不了"可站"的参照。
        self.cold = {(self.target[0] + dx, self.target[1] + dy)
                     for dx in range(-3, 4) for dy in range(-3, 4)}
        self.ring = [(self.target[0] + dx, self.target[1] + dy) for dx, dy in _NB4]
        for t in self.ring:
            self.blockers[t] = "weed"
        # 半径 3 内**除目标格与那 4 个 `weed` 之外**的每一格都用 `tree` 占上（`tree` **不在**
        # `FRONTIER_KINDS` ⇒ 不会变成开路候选），只为让观测**覆盖**它们：否则"窗口里没有这一格"
        # 会被 `_standable_near` 当成"也许能站"，四邻就又变回"可清障 + 够得着"了。
        for t in sorted(self.cold):
            if t != self.target and t not in self.ring:
                self.blockers[t] = "tree"

    def obs(self) -> dict:
        o = super().obs()
        for tv in o["location"]["tiles"]:
            if tuple(tv["tile"]) in self.cold:
                tv["standable"] = False
        return o


class TestTask78HonestEncircledWording(unittest.TestCase):
    """task-78 NIT-2：判 `encircled` 时要说**实话** —— 真实四邻 kind + 试过开路几次。

    病灶：四邻是 `weed` 但站不上去 ⇒ 0 次挥动也判 `encircled`，reason 却断言"树/桩/大石一类"。
    """

    TILE = (62, 12)

    def _run(self, w):
        client = _UnreachableClient(w, unreachable=[self.TILE])
        worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
        run = make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker,
                       target_days=1, max_days=1)
        run.worker = worker
        run.client = client
        return run

    @staticmethod
    def _events(run, event: str) -> list:
        return [e for e in run.entries if e.get("event") == event]

    def test_reason_names_the_real_neighbour_kinds(self):
        w = WeedRingWorld(tile=self.TILE)
        run = self._run(w)
        run.run()
        per = self._events(run, "encircled")
        # 被围住的格子**不封格**（次日/开路后可能变可达）⇒ 同一天会被重试若干轮，事件会多条。
        self.assertGreaterEqual(len(per), 1, per)
        self.assertEqual({tuple(e["tile"]) for e in per}, {self.TILE})
        for e in per:
            self.assertEqual(e["kinds"], ["weed"] * len(_NB4), "逐格 journal 要写四邻真实 kind")
            self.assertEqual(e["tried_open"], 0, "一次都没挥过就照实写 0")
            self.assertIn("weed", e["reason"])
            self.assertNotIn("树/桩/大石", e["reason"], "没证据就不许暗示是树/桩/大石")
            self.assertIn("突破口", e["reason"])

    def test_summary_reports_tried_open_steps(self):
        w = WeedRingWorld(tile=self.TILE)
        run = self._run(w)
        run.run()
        summary = self._events(run, "encircled_summary")
        self.assertEqual(len(summary), 1, summary)
        self.assertEqual(summary[0]["tried_open_steps"], 0, "开路尝试次数要能被复核")
        self.assertIn("bound_basis", summary[0])
        self.assertNotIn("树/桩/大石", str(summary[0].get("note") or ""))


class _SurplusWorker(FakeWorker):
    """task-55：给假执行层补 `sell(slot, *, whitelist=…)`（真 `FarmWorker.sell` 的最小替身）。

    `ShipSkill` 的语义照搬：白名单是**精确 qualifiedId** 列表，出货当天钱**不变**
    （钱要等游戏下一次 `NewDay` 结算）。
    """

    def __init__(self, world: FakeWorld, *, mode: str = "ship") -> None:
        super().__init__(world)
        self.mode = mode
        self.sell_calls: list[dict] = []
        self.shipped: list[dict] = []

    def _slot_item(self, slot: int):
        """按 **slot 字段**找，而不是列表下标 —— 真桥收到的 `args.slot` 就是快照里的 slot 号。"""
        for it in self.w.inventory:
            if int(it.get("slot", -1)) == slot:
                return it
        return None

    def sell(self, slot, *, whitelist=None, timeout_ms=8000):
        slot = int(slot)
        allow = [str(x) for x in (whitelist or [])]
        item = self._slot_item(slot)
        before = {"slot": slot, "qid": (item or {}).get("qualifiedId"),
                  "stack": int((item or {}).get("stack") or 0),
                  "count": len(self.shipped), "money": self.w.money}
        self.sell_calls.append({"slot": slot, "whitelist": allow})
        if self.mode != "ship":
            st = StepResult("sell", None, ok=False, code=self.mode,
                            reason=f"假执行层：sell 失败（{self.mode}）")
            st.before = before
            return st
        if item is None:
            st = StepResult("sell", None, ok=False, code="empty_slot", reason="槽位是空的")
            st.before = before
            return st
        qid = str(item.get("qualifiedId") or item.get("id") or "")
        if qid not in allow:
            st = StepResult("sell", None, ok=False, code="not_whitelisted",
                            reason=f"{qid} 不在白名单里")
            st.before = before
            return st
        self.w.inventory.remove(item)
        self.shipped.append(dict(item))
        st = StepResult("sell", None, ok=True, code="ok",
                        reason="已放进出货箱（钱要下一次 NewDay 才结算）")
        st.before = before
        st.after = {"slot": slot, "qid": qid, "stack": 0, "count": len(self.shipped),
                    "money": self.w.money}
        st.receipt = f"slot={slot} qid={qid}"
        return st


class TestTask55SurplusSell(unittest.TestCase):
    """task-55：`_preconditions` 里"卖盈余材料换种子钱"这条腿的接线与账本。

    铁律（task-42 起）：绝不自己写 `Money +=`，判据一律观测差分；出货当天钱不变，
    要等游戏下一次 `NewDay`。

    变异自检（`%TEMP%\\t55_mutate.py`，跑完即弃；结论同 `test_farmwork.TestTask55SurplusPlan`）：
    基线 14/14 绿；m55a 红 2、m55b 红 1（`test_sells_at_most_once_per_day`）、m55c 红 1
    （`test_cannot_afford_trail_is_written_once_with_the_shortfall`）。
    """

    K = 10

    @staticmethod
    def _material(slot: int, iid: str, name: str, stack: int) -> dict:
        return {"slot": slot, "id": iid, "qualifiedId": f"(O){iid}", "name": name,
                "stack": stack, "isTool": False}

    def _world(self, *, money: int = 14, seeds: int = 0, empty_dirt: int = 40,
               materials: tuple = (), farm: bool = True) -> FakeWorld:
        w = FakeWorld(weeds=0, seeds=seeds, money=money)
        if farm:
            w.farm = {"loaded": True, "complete": True, "emptyDirt": empty_dirt,
                      "dryCrops": 0, "crops": 0, "ripeCrops": 0, "deadCrops": 0, "hoeDirt": 0}
        for m in materials:
            w.inventory.append(dict(m))
        return w

    def _run(self, w: FakeWorld, **kw):
        run = make_run(w, target_days=1, **kw)
        run.worker = _SurplusWorker(w)
        run.client = FakeClient(w)
        return run

    @staticmethod
    def _events(run, name: str) -> list[dict]:
        return [e for e in run.entries if e.get("event") == name]

    def test_gate_sells_surplus_materials_and_writes_journal(self):
        w = self._world(materials=(self._material(6, "388", "Wood", 25),
                                   self._material(7, "388", "Wood", 5),
                                   self._material(8, "390", "Stone", 3)))
        run = self._run(w)
        rep = DayReport(day_key=("summer", 1, 7), started_at=0.0)
        run._preconditions(w.obs(), rep)
        # 只有"卖掉后仍 >= K"的那叠（5 件）进白名单；整叠出货 ⇒ 卖 5 留 25
        self.assertEqual(run.worker.sell_calls,
                         [{"slot": 7, "whitelist": ["(O)388"]}])
        self.assertIsNone(run.worker._slot_item(7), "卖出去的那叠要从背包消失")
        self.assertEqual(len(run.worker.shipped), 1)
        self.assertEqual(w.money, 14, "出货当天钱不变（NewDay 才由游戏结算）")
        sells = self._events(run, "sell")
        self.assertEqual(len(sells), 1, run.entries)
        self.assertEqual(sells[0]["strategy"], "surplus_materials")
        self.assertEqual(sells[0]["keep"], self.K)
        self.assertEqual(sells[0]["qid"], "(O)388")
        self.assertEqual(sells[0]["trigger"]["money"], 14)
        self.assertEqual(sells[0]["trigger"]["threshold"], 5 * 20)
        summary = self._events(run, "surplus_sell")
        self.assertEqual(len(summary), 1, run.entries)
        self.assertEqual(summary[0]["sold"], 5)
        self.assertFalse(summary[0]["below_keep"])
        self.assertEqual(summary[0]["trigger"]["emptyDirt"], 40)
        self.assertTrue(any("NewDay" in n for n in rep.notes), rep.notes)
        self.assertTrue(run.surplus_sold_today)

    def test_no_sell_when_money_seeds_or_dirt_are_fine(self):
        for kw, why in (({"money": 500}, "钱够"),
                        ({"seeds": 5}, "还有种子"),
                        ({"empty_dirt": 0}, "没有空地"),
                        ({"farm": False}, "farm 证据不可用")):
            w = self._world(materials=(self._material(6, "390", "Stone", 200),), **kw)
            run = self._run(w)
            rep = DayReport(day_key=("summer", 1, 7), started_at=0.0)
            run._preconditions(w.obs(), rep)
            self.assertEqual(run.worker.sell_calls, [], why)
            self.assertEqual(self._events(run, "sell"), [], why)
            self.assertEqual(self._events(run, "surplus_sell"), [], why)
            self.assertFalse(run.surplus_sold_today, why)

    def test_sells_at_most_once_per_day(self):
        # 两叠 Wood：第 1 轮卖 5（留 25）；若"当天只卖一次"的守卫失效，第 2 轮会把 25 也卖掉
        w = self._world(materials=(self._material(6, "388", "Wood", 25),
                                   self._material(7, "388", "Wood", 5)))
        run = self._run(w)
        rep = DayReport(day_key=("summer", 1, 7), started_at=0.0)
        run._preconditions(w.obs(), rep)
        run._preconditions(w.obs(), rep)
        self.assertEqual([c["slot"] for c in run.worker.sell_calls], [7],
                         "同一天只许卖一次（每轮都会跑 _preconditions）")
        self.assertEqual(len(run.worker.shipped), 1)
        # 次日 `_run_day` 会清零 ⇒ 还能再来一次
        run.surplus_sold_today = False
        run._preconditions(w.obs(), rep)
        self.assertGreater(len(run.worker.sell_calls), 1)

    def test_lone_oversized_stack_is_sold_and_flagged_honestly(self):
        w = self._world(materials=(self._material(6, "390", "Stone", 200),))
        run = self._run(w)
        rep = DayReport(day_key=("summer", 1, 7), started_at=0.0)
        run._preconditions(w.obs(), rep)
        self.assertEqual([c["slot"] for c in run.worker.sell_calls], [6])
        summary = self._events(run, "surplus_sell")[0]
        self.assertTrue(summary["below_keep"], "唯一一大叠整叠出货 ⇒ 必须如实标 below_keep")
        self.assertEqual(summary["items"][0]["left"], 0)
        self.assertTrue(any("K=10" in n for n in rep.notes), rep.notes)

    def test_lone_stack_is_skipped_when_it_cannot_cover_the_seed_price(self):
        """【Lead m08064 硬要求】唯一一大叠"卖了也买不起种子"时**不许卖**，如实记 skip + 缺口。

        钱 0g、缺口 20g、一大叠 11 件 ⇒ 最低价下界只有 11g < 20g ⇒ skip，并把缺口原文写进
        `surplus_sell_skip`（`short`/`reason`），不要制造"卖了还是买不起"的假动作。
        """
        w = self._world(money=0, materials=(self._material(6, "390", "Stone", 11),))
        run = self._run(w)
        rep = DayReport(day_key=("summer", 1, 7), started_at=0.0)
        run._preconditions(w.obs(), rep)
        self.assertEqual(run.worker.sell_calls, [])
        self.assertEqual(self._events(run, "sell"), [])
        skips = self._events(run, "surplus_sell_skip")
        self.assertEqual(len(skips), 1, run.entries)
        self.assertEqual(skips[0]["short"], 20)
        self.assertIn("缺口 20g", skips[0]["reason"])
        self.assertFalse(skips[0]["below_keep"])
        self.assertTrue(run.surplus_sold_today, "门闸成立就算处理过，别每轮重算")
        self.assertTrue(any("买不起" in n or "补不上" in n for n in rep.notes), rep.notes)

    def test_sell_failure_is_recorded_but_never_a_hard_failure(self):
        w = self._world(materials=(self._material(6, "388", "Wood", 25),
                                   self._material(7, "388", "Wood", 5)))
        run = self._run(w)
        run.worker.mode = "not_whitelisted"
        rep = DayReport(day_key=("summer", 1, 7), started_at=0.0)
        run._preconditions(w.obs(), rep)
        sells = self._events(run, "sell")
        self.assertEqual(len(sells), 1, run.entries)
        self.assertFalse(sells[0]["ok"])
        self.assertEqual(sells[0]["code"], "not_whitelisted")
        self.assertEqual(self._events(run, "sell_failed")[0]["strategy"], "surplus_materials")
        self.assertEqual(w.money, 14)
        self.assertFalse(self._events(run, "surplus_sell")[0]["ok"])
        self.assertEqual(run.worker.sell_calls, [{"slot": 7, "whitelist": ["(O)388"]}] * 1)

    def test_cannot_afford_trail_is_written_once_with_the_shortfall(self):
        w = self._world()          # 没材料、没货架、钱 14 < seed_price 20
        run = self._run(w)
        run.shop_offers = []
        rep = DayReport(day_key=("summer", 1, 7), started_at=0.0)
        run._preconditions(w.obs(), rep)
        run._preconditions(w.obs(), rep)
        ev = self._events(run, "cannot_afford")
        self.assertEqual(len(ev), 1, run.entries)
        self.assertEqual((ev[0]["money"], ev[0]["seed_price"], ev[0]["short"]), (14, 20, 6))
        self.assertEqual(self._events(run, "buy"), [], "钱不够时不该发注定失败的 buy")
        self.assertEqual(self._events(run, "sell_failed"), [])

    def test_money_arrived_next_day_then_buys_and_never_calls_it_a_failure(self):
        w = self._world(materials=(self._material(6, "390", "Stone", 200),))
        run = self._run(w)
        rep = DayReport(day_key=("summer", 1, 7), started_at=0.0)
        run._preconditions(w.obs(), rep)                    # 第 1 天：卖；钱当天没到账
        self.assertEqual(len(self._events(run, "sell")), 1)
        self.assertEqual(self._events(run, "buy"), [])
        self.assertEqual(self._events(run, "sell_failed"), [],
                         "「钱要等 NewDay」绝不许被记成失败")
        # 游戏结算（假世界手动模拟 NewDay）⇒ 次日必须真的能买
        w.money = 414
        w.day = 8
        run.surplus_sold_today = False
        run.seed_dead_today = ""
        run.cannot_afford_noted = False
        rep2 = DayReport(day_key=("summer", 1, 8), started_at=0.0)
        run._preconditions(w.obs(), rep2)
        buys = self._events(run, "buy")
        self.assertEqual(len(buys), 1, run.entries)
        self.assertTrue(buys[0]["ok"], buys[0])
        self.assertEqual(w.money, 214, "买了 10 包 × 20g")
        self.assertGreaterEqual(run._seed_outlook(w.obs())[0], 1)


class TestTask84DeadCropWatering(unittest.TestCase):
    """【task-84】死苗不浇水：窗口目标 / 窗口证据 / 策略 / 日账本 四条链口径一致（用户 m11003）。

    真机 run7 形态：`[12,30]` 一株死苗既不可达、又被算成"该浇水" —— Mod 的 `TileView.Tool`
    是 `watered ? "none" : "can"`（不看 `crop.dead`），`farm.dryCrops`/`dryTiles` 也把死苗算"干"
    ⇒ `water_far` 追它 10 次（8 次 `unreachable`＋2 次回执 ok 但 `dry 6→6`），`given_up=true`，
    summer 3/5 整天换片地、summer 6 空转 4.5 分钟才靠 `stuck_flush` 翻篇。

    0.7.27 的修法：Mod 拆开干/死（`dryCrops`/`dryTiles` 只算活苗 + 新 `dryDeadCrops` +
    `tool` 对死苗给 `none`），脑侧**所有**"该浇水"的口径只认活苗，死苗单独进日账本。

    变异自检（脚本复制 brain+tests 到临时目录做文本替换、跑完即弃；基线 6/6 绿）：
    `m84a`（`longrun._stage_tiles("water_area")` 的 `and not v.get("dead")` 去掉）⇒
    `test_water_targets_and_leftover_exclude_dead_crops` 红；
    `m84c`（`planner` 的 `elif not tile.get("dead"):` 改成 `elif True:`）⇒
    `test_planner_never_calls_a_dead_crop_unwatered` 红。
    """

    DEAD = (60, 10)
    LIVE = (61, 10)

    def _world(self, **kw):
        kw.setdefault("weeds", 0)
        w = FakeWorld(**kw)
        self._add(w, self.DEAD, dead=True)
        return w

    @staticmethod
    def _add(w, tile, *, dead, watered=False, ripe=False):
        w.crops[tile] = {"ripe": ripe, "watered": watered, "dead": dead}
        w.dirt.add(tile)

    def _plot(self):
        return {"zone": "", "label": "", "anchor": [62, 12],
                "tiles": [self.DEAD, self.LIVE], "note": ""}

    def test_water_targets_and_leftover_exclude_dead_crops(self):
        """死苗既不进浇水目标池，也不算"该浇而没浇"的剩余（与 `_stage_tiles` 同口径）。"""
        w = self._world()
        run = make_run(w)
        obs = w.obs()
        self.assertEqual(run._stage_tiles("water_area", obs, self._plot()), [],
                         "死苗不许进浇水目标池")
        self.assertEqual(run._leftover("water_area", obs, self._plot()), [],
                         "死苗不算『该浇而没浇』的剩余（否则当天永远判定没做完）")
        reasons = run.work_reasons(obs)
        self.assertFalse([r for r in reasons if "没浇水" in r],
                         f"工作理由里不许出现『没浇水』：{reasons}")

    def test_window_water_evidence_counts_only_live_crops(self):
        """窗口口径的浇水证据也只数活苗：只有死苗时 `dry=0`，不许判"没浇完"。"""
        w = self._world()          # 【task-96】显式清空 `farm` 块 ⇒ 走窗口口径
        w.farm = {}
        run = make_run(w)
        obs = w.obs()
        ok, info = run._water_evidence(obs, outdoor_obs=obs, outdoor_t=0.0,
                                       outdoor_name="Farm")
        self.assertEqual(info["scope"], "window", info)
        self.assertEqual(info["dry"], 0, "死苗的『干』不算没浇完（task-84 口径）")
        self.assertTrue(ok, "只有死苗时不许判『浇水证据不足』")
        ess = run._essence(obs)
        self.assertEqual(ess["unwatered_crops"], 0)
        self.assertEqual(ess["dead_crops"], 1, "死苗单独一列，不许混进 unwatered_crops")

    def test_planner_never_calls_a_dead_crop_unwatered(self):
        """`Brief` 的计数与策略序：死苗走 `clear_dead`，不会伪装成 `water_area`。"""
        w = self._world()
        brief = Brief.from_observe(w.obs())
        self.assertEqual(int(brief.counts.get("unwatered_crops") or 0), 0, brief.counts)
        self.assertEqual(int(brief.counts.get("dead") or 0), 1, brief.counts)
        self.assertEqual(deterministic_plan(brief)[0].task, "clear_dead")

    def test_policy_intents_put_clear_dead_before_water(self):
        """政策层（`_policy_intents`）同样把 `clear_dead` 排在 `water_area` 之前。"""
        w = self._world()
        self._add(w, self.LIVE, dead=False)
        run = make_run(w)
        out, _notes = run._policy_intents([], w.obs())
        self.assertEqual([i.task for i in out][:2], ["clear_dead", "water_area"],
                         f"政策顺序必须是清死苗 → 浇水：{[i.task for i in out]}")

    def test_day_end_carries_dead_crop_evidence(self):
        """日账本：`dead_crops`/`dry_dead`/`gave_up_tiles` 进 `day_end`（带状态，供对账）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {"loaded": True, "complete": True, "crops": 5, "dryCrops": 0,
                  "dryDeadCrops": 3, "deadCrops": 4, "unwateredCrops": 5, "hoeDirt": 5}
        run = make_run(w, target_days=1, max_days=1)

        run.run()

        rep = run.days[0]
        self.assertEqual((rep.dead_crops, rep.dead_crops_status), (4, "ok"))
        self.assertEqual((rep.dry_dead, rep.dry_dead_status), (3, "ok"))
        ev = [e for e in run.entries if e.get("event") == "dead_crops_summary"]
        self.assertEqual(len(ev), 1, f"应当恰有一条 dead_crops_summary：{run.entries}")
        end = [e for e in run.entries if e.get("event") == "day_end"][0]
        for key in ("dead_crops", "dead_crops_status", "dry_dead", "dry_dead_status",
                    "gave_up_tiles"):
            self.assertIn(key, end, f"`day_end` 必须有 {key}")
        self.assertEqual((end["dead_crops"], end["dry_dead"]), (4, 3))

    def test_old_mod_without_the_field_is_unavailable_not_zero(self):
        """旧 Mod 没有 `deadCrops`/`dryDeadCrops` ⇒ 状态必须是 `unavailable`，不是"没有"。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {"loaded": True, "complete": True, "crops": 5, "dryCrops": 0, "hoeDirt": 5}
        run = make_run(w, target_days=1, max_days=1)

        run.run()

        rep = run.days[0]
        self.assertEqual((rep.dead_crops, rep.dead_crops_status), (0, "unavailable"),
                         "缺字段 = 不知道，绝不许当成 0（『没有死苗』）")
        self.assertEqual(rep.dry_dead_status, "unavailable")
        end = [e for e in run.entries if e.get("event") == "day_end"][0]
        self.assertEqual(end["dead_crops_status"], "unavailable")


class TestTask96EvidenceFailClosed(unittest.TestCase):
    """task-96：`farm` 证据不可用时的 **fail-open 老洞**（deputy task-92 的 C8b/C8c/C6c/C6d）。

    修法（生产侧，`brain/agentfarm/longrun.py`）：
    ① `_farm_scope_work()` 在"人在农场 + farm 证据可用"时也给值（返回 `None` **只** 表示证据不可用）；
    ② 证据不可用 ⇒ `work_reasons()` 必须给"还有活"理由（journal `farm_evidence_unavailable`，
       每天一条）且 `sleep_guard` 不许放行 `no_work` —— **室内与农场一视同仁**；
    ③ `_water_evidence()` 的 window 分支只有 `crops > 0` 才允许"`dry==0` ⇒ True"（`crops==0`
       时 `dry==0` 恒真，不许据此自称浇过；farm 口径不变）。

    变异自检（`%TEMP%\t96_mutate.py`：复制 brain+tests 到临时目录、文本替换、跑本类、跑完即弃）：
    **基线 7/7 绿**；**m96a**（`_farm_scope_work` 退回"只在室内才给值"）红 **1**
    （`test_farm_evidence_available_and_dry_keeps_working`）；**m96b**（去掉 `_water_evidence`
    window 分支的 `crops==0 ⇒ False`）红 **1**（`test_window_evidence_with_zero_crops_is_false`）。
    """

    def test_on_farm_with_unavailable_farm_evidence_never_ends_no_work(self):
        """人在农场 + 桥整块没给 `farm` ⇒ 一天绝不许以 `no_work` 收场（C8b/C8c）。

        【task-99 ② / NIT-6】这里用 **`None`** 表示"没有 farm 块"（过去 `None` 会被夹具解释成
        "自动生成与世界一致的扫描" ⇒ 这一条会**静默变绿**）；变异：把夹具改回自动扫描 ⇒ 必红。
        """
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = None
        run = make_run(w, target_days=1, max_days=1)

        run.run()

        rep = run.days[0]
        self.assertFalse(str(rep.ended_reason).startswith("no_work"), rep.ended_reason)
        self.assertIn("farm 证据不可用", rep.ended_reason)
        self.assertFalse(rep.verified, f"{rep.checks} / {rep.ended_reason}")
        self.assertFalse(rep.checks["day_justified"], rep.checks)
        events = [e for e in run.entries if e.get("event") == "farm_evidence_unavailable"]
        self.assertEqual(len(events), 1, "每天最多一条")
        self.assertTrue(events[0]["on_farm"], "必须认出『人在农场』（旧口径只在室内触发）")
        self.assertIn("farm 证据不可用", " ".join(run.work_reasons(w.obs())))

    def test_sleep_guard_vetoes_no_work_on_farm_without_evidence(self):
        """直接问守卫：农场 + 证据不可用 ⇒ `keep_working`，且理由点名"农场"（不是"室内"）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {}
        run = make_run(w)

        allow, code, why = run.sleep_guard(w.obs())

        self.assertFalse(allow, why)
        self.assertEqual(code, "keep_working")
        self.assertIn("农场里", why)
        self.assertIn("farm 证据不可用", why)
        self.assertIn("crops==0 不是证据", why)

    def test_off_farm_without_evidence_still_vetoes(self):
        """task-41 回归：人在室内 + 证据不可用 ⇒ 照旧否决 `no_work`（理由写"室内"）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {}
        w.location = "FarmHouse"
        w.is_outdoor_farm = False
        run = make_run(w)

        allow, code, why = run.sleep_guard(w.obs())

        self.assertFalse(allow, why)
        self.assertEqual(code, "keep_working")
        self.assertIn("室内", why)

    def test_on_farm_complete_false_also_fails_closed(self):
        """C6c/C6d 的变体：`farm.complete=false`（扫没扫完）同样是"证据不可用"。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {"loaded": True, "complete": False, "crops": 3, "dryCrops": 0, "hoeDirt": 3}
        run = make_run(w)

        allow, code, why = run.sleep_guard(w.obs())

        self.assertFalse(allow, why)
        self.assertEqual(code, "keep_working")
        self.assertIn("farm 证据不可用", why)

    def test_farm_evidence_available_and_dry_keeps_working(self):
        """① 的反面：人在农场 + `complete=true` + `dryCrops>0`（窗口看不到）⇒ 继续干、不许睡。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {"loaded": True, "complete": True, "crops": 4, "dryCrops": 2, "ripeCrops": 0,
                  "deadCrops": 0, "dryDeadCrops": 0, "unwateredCrops": 4, "hoeDirt": 4,
                  "emptyDirt": 0, "dryTiles": [[70, 20], [71, 20]], "dryTilesTruncated": False}
        run = make_run(w)
        obs = w.obs()

        allow, code, why = run.sleep_guard(obs)

        self.assertFalse(allow, why)
        self.assertEqual(code, "keep_working")
        self.assertIn("干作物", why)
        self.assertTrue(any("干作物" in r for r in run.work_reasons(obs)),
                        run.work_reasons(obs))

    def test_window_evidence_with_zero_crops_is_false(self):
        """③ `crops==0` 时 `dry==0` 恒真 ⇒ 不许据此判 True；对照：`crops>0 & dry==0` 仍是 True。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {}                      # 退回窗口口径
        w.dirt.add((60, 10))             # 窗口里有**观测格**（耕地）但一格作物都没有
        run = make_run(w)
        obs = w.obs()
        ok, info = run._water_evidence(obs, outdoor_obs=obs, outdoor_t=1.0, outdoor_name="Farm")
        self.assertFalse(ok, info)
        self.assertEqual(info["scope"], "window", info)
        self.assertGreater(info["tiles"], 0, info)
        self.assertEqual(info["crops"], 0, info)
        self.assertIn("crops==0", str(info.get("note") or ""))

        w2 = FakeWorld(weeds=0, seeds=0, money=0)
        w2.farm = {}
        w2.dirt.add((60, 10))
        w2.crops[(60, 10)] = {"ripe": False, "watered": True}
        run2 = make_run(w2)
        obs2 = w2.obs()
        ok2, info2 = run2._water_evidence(obs2, outdoor_obs=obs2, outdoor_t=1.0, outdoor_name="Farm")
        self.assertTrue(ok2, info2)
        self.assertEqual((info2["crops"], info2["dry"]), (1, 0), info2)

    def test_farm_scope_evidence_clean_is_true(self):
        """farm 口径不变：`complete=true` + `dryCrops==0` ⇒ True（证据齐、地浇完了）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = w.farm_scan()           # 世界一致的真扫描：无作物 ⇒ dryCrops 0
        run = make_run(w)
        obs = w.obs()

        ok, info = run._water_evidence(obs, outdoor_obs=obs, outdoor_t=1.0, outdoor_name="Farm")

        self.assertTrue(ok, info)
        self.assertEqual(info["scope"], "farm", info)
        self.assertEqual(info["dry"], 0, info)


class TestTask99DryCropsMissing(unittest.TestCase):
    """task-99：`complete=true` 但 **`dryCrops` 缺失** ⇒ 干作物数**未知**（≠ 0）⇒ fail-closed。

    deputy task-97 的 C1（`docs/_review-task96.md`）：`_farm_totals()` 旧写法 `dry is None and
    ripe is None` 只在**两个字段都没有**时才返回 `None`；`<0.7.22` 的 Mod 是"`ripeCrops` 有值 +
    没有 `dryCrops`" ⇒ 返回 `(0, 0)` ⇒ 守卫拿不到"还有干作物"、`_water_evidence` 退回窗口口径
    （窗外那株没浇的活苗看不见）⇒ `no_work` + `watered_outdoor=true` + **假 VERIFIED**。
    一行修法：`dry is None ⇒ return None`。代价（Lead 明示接受）：旧 Mod 下每个在场日都
    fail-closed、拿不到 VERIFIED —— 诚实优先。

    变异自检（`%TEMP%\t99_mutate.py`，复制 brain+tests 到临时目录、文本替换、跑本类、跑完即弃）：
    **基线 6/6 绿**；**m99a**（把 `dry is None ⇒ return None` 退回 `dry is None and ripe is None` +
    `int(dry or 0)`）红 **2** = `test_farm_totals_unknown_when_dry_missing` /
    `test_missing_dry_crops_never_no_work_or_verified`（`test_missing_dry_crops_with_ripe_is_never_no_work`
    在变异下仍绿：`ripe>0` 本来就能让守卫继续干，符合预期）；
    **m99b**（夹具把 `None` 改回"自动 `farm_scan()`"）红 **1** =
    `test_fixture_none_means_evidence_unavailable`。
    """

    #: `<0.7.22` 的 Mod：`complete=true` + `ripeCrops` 有值 + **没有** `dryCrops`。
    LEGACY = {"loaded": True, "complete": True, "crops": 6, "ripeCrops": 0, "deadCrops": 0,
              "unwateredCrops": 6, "hoeDirt": 6, "emptyDirt": 0, "dryTiles": []}

    def test_farm_totals_unknown_when_dry_missing(self):
        """单元级：`dryCrops` 缺失 ⇒ `None`（未知），补上 ⇒ `(dry, ripe)`；这正是 C1 的那一行。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = dict(self.LEGACY)
        run = make_run(w)
        self.assertIsNone(run._farm_totals(w.obs()), "缺 dryCrops ⇒ 未知，不许当 0")

        w.farm = {**self.LEGACY, "dryCrops": 0}
        self.assertEqual(run._farm_totals(w.obs()), (0, 0), "补上 dryCrops 才是『没有干作物』")
        w.farm = {**self.LEGACY, "dryCrops": 3, "ripeCrops": 2}
        self.assertEqual(run._farm_totals(w.obs()), (3, 2))

    def test_missing_dry_crops_never_no_work_or_verified(self):
        """C1 反例：缺 `dryCrops` + `ripe==0` ⇒ 一天**绝不出** `no_work`、`verified` 必须 False。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = dict(self.LEGACY)               # 窗外/全农场读数不完整
        run = make_run(w, target_days=1, max_days=1)

        run.run()

        rep = run.days[0]
        self.assertFalse(str(rep.ended_reason).startswith("no_work"), rep.ended_reason)
        self.assertIn("farm 证据不可用", rep.ended_reason)
        self.assertFalse(rep.verified, f"{rep.checks} / {rep.ended_reason}")
        self.assertFalse(rep.checks["day_justified"], rep.checks)
        events = [e for e in run.entries if e.get("event") == "farm_evidence_unavailable"]
        self.assertEqual(len(events), 1, "每天最多一条")
        self.assertTrue(events[0]["on_farm"])
        ok, info = run._water_evidence(w.obs(), outdoor_obs=w.obs(), outdoor_t=1.0,
                                      outdoor_name="Farm")
        self.assertFalse(ok, info)               # 不许退回窗口口径自称浇过

    def test_missing_dry_crops_with_ripe_is_never_no_work(self):
        """缺 `dryCrops` 但 `ripeCrops>0` ⇒ 至少不许 `no_work`（熟作物也是活）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {**self.LEGACY, "ripeCrops": 2}
        run = make_run(w, target_days=1, max_days=1)

        run.run()

        rep = run.days[0]
        self.assertFalse(str(rep.ended_reason).startswith("no_work"), rep.ended_reason)
        self.assertFalse(rep.verified, rep.checks)

    def test_missing_dry_crops_positive_control_can_still_finish(self):
        """正对照：同一世界**补上** `dryCrops=0` ⇒ 证据齐、守卫不再因"证据不可用"否决。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.farm = {**self.LEGACY, "dryCrops": 0, "ripeCrops": 0, "crops": 0, "hoeDirt": 0}
        run = make_run(w)

        allow, code, why = run.sleep_guard(w.obs())

        self.assertNotIn("farm 证据不可用", why)
        self.assertTrue(allow, why)
        self.assertEqual(code, "no_work")

    def test_fixture_none_means_evidence_unavailable(self):
        """NIT-6：夹具 `farm=None` ⇒ 观测里**没有**可用的 `farm`（不再是"自动扫描"）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.dirt.add((60, 10))
        w.crops[(60, 10)] = {"ripe": False, "watered": False}
        w.farm = None
        run = make_run(w)

        obs = w.obs()

        self.assertEqual(obs["farm"], {}, "None 必须表示『证据不可用』")
        self.assertIsNone(run._farm_totals(obs))
        self.assertFalse(run.sleep_guard(obs)[0], "证据不可用 ⇒ 不许放行")
        # 显式要"世界一致扫描"时仍然拿得到（且与窗口一致：1 株没浇的活苗）
        w.farm = w.farm_scan()
        scan = w.obs()["farm"]
        self.assertIs(scan["complete"], True)
        self.assertEqual((scan["crops"], scan["dryCrops"]), (1, 1), scan)
        self.assertEqual(run._farm_totals(w.obs()), (1, 0))

    def test_default_fixture_is_a_live_bridge_with_nothing_to_report(self):
        """默认值语义：桥在线、扫描完整、农场级无事可报（普通日用例靠它才不触发 fail-closed）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        run = make_run(w)
        self.assertIs(w.obs()["farm"]["complete"], True)
        self.assertEqual(run._farm_totals(w.obs()), (0, 0))


class _NoSpaceWorker(_SurplusWorker):
    """task-102：`buy` 回 `code="no_space"`（真 `FarmWorker.buy()` 在 `no_inventory_space` 时的结果码）。

    `status` 用真桥原文（`no_inventory_space`），`code` 是脑侧分流后的结果码。
    """

    def __init__(self, world: FakeWorld, *, status: str = "no_inventory_space",
                 code: str = "no_space") -> None:
        super().__init__(world)
        self.buy_status = status
        self.buy_code = code
        self.buy_requests: list[dict] = []

    def buy(self, item, count=10, *, shop="SeedShop", timeout_ms=25000):
        self.buy_requests.append({"item": str(item), "count": int(count)})
        st = StepResult("buy", None, ok=False, code=self.buy_code,
                        reason=f"没成交：背包没有空格、也没有同类堆叠可并入（Mod status={self.buy_status}）")
        st.status = self.buy_status
        # 真桥的成败回执都带货架清单（`availableItems`）⇒ 脑才有"换 id 重挑"的依据。
        st.available = [dict(o) for o in self.w.buy_offers]
        return st


class _ModalThenFarmWorker(_SurplusWorker):
    """task-102：第一次 `ensure_location` 被晨间 `ShippingMenu` 挡成 `ui_modal`，第二次成功。

    复刻 run8 day 12：`goto_farm` 失败（`t=107.91`）→ 关掉 `ShippingMenu`（`t=107.95`）→
    本卡要求"清模态后**重试一次**"，否则玩家整天留在 FarmHouse。
    """

    def __init__(self, world: FakeWorld) -> None:
        super().__init__(world)
        self.ensure_calls = 0

    def ensure_location(self, name, *, tile=None, timeout_ms=30000):
        self.ensure_calls += 1
        st = StepResult("ensure_location", None)
        if self.ensure_calls == 1:
            st.code = "ui_modal"
            st.reason = "[ui_modal] 有菜单/对话挡着（'ShippingMenu'），所有技能都会被拒"
            st.receipt = "ui_modal"
            return st
        self.w.location = "Farm"
        self.w.is_outdoor_farm = True
        self.w.player_tile = [62, 14]
        st.ok = True
        st.code = "ok"
        st.reason = "已到 Farm"
        return st


class TestTask102BuySlotDeadlock(unittest.TestCase):
    """task-102：run8 day 12/13 的经济闭环死锁（背包 0 空格 ⇒ 26 次 buy 全废）+ 早睡防线。

    真机证据（`logs/longrun-3day-llm-run8.jsonl`）：day 12 早晨 `goto_farm` 被上一夜留下的
    `ShippingMenu` 挡掉（`t=107.91`）⇒ 人整天留 FarmHouse；`buy` 选品是对的（跳过春季 472、
    选当季 Wheat Seeds 10g，钱 188g 够），但回 `no_inventory_space` —— 当天 13 次 + 次日 11 次、
    成交 0、白开 23 个 `ShopMenu`；期间 `water_far` 全 `unreachable`、`dry 6→6`；最后 0 农场动作
    就睡（day 2 06:20 直接睡到 day 13）。

    变异自检（`%TEMP%\\t102_mutate.py`，跑完即弃）：基线 **12/12 绿**；**m102a**（空格死锁那条
    分支短路）红 `test_slot_deadlock_sells_a_stack_then_buys_once`；**m102b**（`_do_sleep` 的
    0 动作拦截短路）红 `test_do_sleep_refuses_a_day_with_work_but_no_actions`；**m102c**
    （`no_inventory_space` 不再映射成 `no_space`）红
    `test_farmwork.TestTask102BuyNoSpace.test_no_inventory_space_maps_to_its_own_code`。
    """

    SEED_OFFERS = [{"id": "(O)483", "name": "Wheat Seeds", "price": 10}]

    @staticmethod
    def _material(slot: int, iid: str, name: str, stack: int) -> dict:
        return {"slot": slot, "id": iid, "qualifiedId": f"(O){iid}", "name": name,
                "stack": stack, "isTool": False}

    def _world(self, *, money: int = 188, seeds: int = 0, materials: tuple = (),
               capacity: int | None = None) -> FakeWorld:
        w = FakeWorld(weeds=0, seeds=seeds, money=money)
        w.buy_offers = [dict(o) for o in self.SEED_OFFERS]
        for m in materials:
            w.inventory.append(dict(m))
        if capacity is not None:
            w.inventory_capacity = int(capacity)
        return w

    def _run(self, w: FakeWorld, worker=None):
        run = make_run(w, target_days=1)
        run.worker = worker if worker is not None else _NoSpaceWorker(w)
        run.client = FakeClient(w)
        return run

    @staticmethod
    def _events(run, name: str) -> list[dict]:
        return [e for e in run.entries if e.get("event") == name]

    @staticmethod
    def _rep(day: int = 12) -> DayReport:
        return DayReport(day_key=("summer", 1, day), started_at=0.0)

    # ------------------------------------------------------------------ ① no_space 独立分流
    def test_no_space_is_its_own_code_and_the_day_stops_buying(self):
        """`no_inventory_space` ⇒ `code="no_space"` + `buy_no_space` journal；当天不再重试。"""
        w = self._world()
        run = self._run(w)
        # run8 里"当季筛选本身是对的"：清单已在手（上一次回执带回来的），直接挑当季最便宜那包。
        run.shop_offers = [dict(o) for o in self.SEED_OFFERS]
        rep = self._rep()
        run._preconditions(w.obs(), rep)
        self.assertEqual(len(run.worker.buy_requests), 1)
        self.assertEqual(run.worker.buy_requests[0]["item"], "(O)483",
                         "按当季货架清单挑（不是硬编码 472）")
        buy = self._events(run, "buy")
        self.assertEqual(len(buy), 1)
        self.assertEqual(buy[0]["code"], "no_space")
        self.assertEqual(buy[0]["attempt"], 1)
        self.assertEqual(buy[0]["limit"], MAX_BUY_TRIES_PER_DAY)
        self.assertTrue(run.buy_no_space_today)
        ns = self._events(run, "buy_no_space")
        self.assertEqual(len(ns), 1)
        self.assertEqual(ns[0]["item"], "(O)483")
        self.assertTrue(any("背包没有空格" in n or "空格" in n for n in rep.notes), rep.notes)
        # run8 是"同一天撞 13 次"：这里再调 10 次，一次请求都不许发出去
        for _ in range(10):
            run._preconditions(w.obs(), rep)
        self.assertEqual(len(run.worker.buy_requests), 1, "撞到 no_space 后当天不许再试")

    # ------------------------------------------------------------------ ② 每天 buy 次数上界
    def test_buy_attempts_are_capped_at_three_per_day(self):
        """普通失败（不是 no_space）也要有每天上界：`MAX_BUY_TRIES_PER_DAY`。"""
        w = self._world()
        worker = _NoSpaceWorker(w, status="some_other_error", code="failed")
        run = self._run(w, worker)
        rep = self._rep()
        for _ in range(6):
            run._preconditions(w.obs(), rep)
        self.assertEqual(len(worker.buy_requests), MAX_BUY_TRIES_PER_DAY)
        self.assertEqual(len(self._events(run, "buy")), MAX_BUY_TRIES_PER_DAY)
        self.assertEqual(run.buy_attempts_today, MAX_BUY_TRIES_PER_DAY)
        self.assertTrue(any("上限" in n for n in rep.notes), rep.notes)

    # ------------------------------------------------------------------ ③ 空格死锁 ⇒ 卖一叠腾格
    def test_slot_deadlock_sells_a_stack_then_buys_once(self):
        """钱够但 0 空格 ⇒ 先卖一叠盈余材料腾格（`why="need_slot"`），再照常走一次 buy。"""
        w = self._world(materials=(self._material(6, "390", "Stone", 200),))
        w.inventory_capacity = len(w.inventory)          # 0 空格（run8 形态）
        run = self._run(w)
        rep = self._rep()
        run._preconditions(w.obs(), rep)
        self.assertEqual(run.worker.sell_calls and [c["slot"] for c in run.worker.sell_calls], [6])
        sells = self._events(run, "sell")
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0]["why"], "need_slot")
        self.assertEqual(sells[0]["qid"], "(O)390")
        summary = self._events(run, "surplus_sell")
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["why"], "need_slot")
        self.assertTrue(run.slot_sold_today)
        self.assertEqual(len(run.worker.buy_requests), 1, "卖掉一叠之后照常走一次 buy")
        self.assertTrue(any("腾格" in n or "腾格子" in n for n in rep.notes), rep.notes)

    # ------------------------------------------------------------------ ④ 守卫不许放行"睡过去"
    def test_sleep_guard_refuses_while_seeds_cannot_come_in(self):
        """`buy_no_space_today` ⇒ 守卫必须 keep_working（否则就是拿睡觉跳过买种子的活）。"""
        w = self._world()
        run = self._run(w)
        run.buy_no_space_today = True
        allow, why, detail = run.sleep_guard(w.obs())
        self.assertFalse(allow)
        self.assertEqual(why, "keep_working")
        self.assertIn("背包没有空格", detail)

    # ------------------------------------------------------------------ ⑤ 0 动作 + 有活 ⇒ 拒绝睡觉
    def test_do_sleep_refuses_a_day_with_work_but_no_actions(self):
        """有活却一次没干就睡 ⇒ `slept_without_work`，**不推进**游戏日（run8 day 12）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.dirt.add((60, 10))
        w.crops[(60, 10)] = {"ripe": False, "watered": False}
        w.farm = w.farm_scan()
        run = self._run(w)
        run.worker = FakeWorker(w)          # 不需要 sell/buy，只看睡觉拦截
        rep = self._rep()
        day_before = w.day
        by, why = run._do_sleep(w.obs(), rep, "no_work:确实找不到可做的活")
        self.assertEqual(by, "slept_without_work")
        self.assertTrue(rep.slept_without_work)
        self.assertEqual(w.day, day_before, "拒绝了就不许推进游戏日")
        ev = self._events(run, "slept_without_work")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["farm_actions"], 0)
        self.assertTrue(any("拒绝睡觉" in n for n in rep.notes), rep.notes)

    # ------------------------------------------------------------------ ⑥ 真空农场仍可 no_work 睡
    def test_a_genuinely_empty_farm_can_still_sleep_no_work(self):
        """反面：农场真的没活（无作物、无目标）⇒ `no_work` 睡觉照旧允许（不许把正常日憋死）。"""
        w = self._world(money=0)
        run = self._run(w)
        run.worker = FakeWorker(w)
        rep = self._rep()
        by, _why = run._do_sleep(w.obs(), rep, "no_work:确实找不到可做的活")
        self.assertEqual(by, "sleep")
        self.assertFalse(rep.slept_without_work)
        self.assertEqual(w.day, 7)

    # ------------------------------------------------------------------ ⑦ 买之前清残留菜单
    def test_a_stray_shop_menu_is_dismissed_before_buying(self):
        """`ShopMenu` 是 `buy` 自己上一次留下的：买之前必须先关掉（run8 白开 23 个）。"""
        w = self._world()
        w.ui_script = [{"activeMenu": "ShopMenu", "isModal": True}]
        run = self._run(w)
        rep = self._rep()
        run._preconditions(w.obs(), rep)
        self.assertEqual(w.dismiss_calls, 1)
        ev = self._events(run, "modal_dismissed")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["where"], "before_buy")
        self.assertEqual(ev[0]["menu"], "ShopMenu")
        self.assertEqual(len(run.worker.buy_requests), 1)

    # ------------------------------------------------------------------ ⑧ goto_farm 清模态重试一次
    def test_goto_farm_retries_once_after_clearing_a_stray_menu(self):
        """晨间 `ShippingMenu` 挡住 `goto_farm` ⇒ 清掉后**重试一次**（run8 day 12 的形态）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        w.player_tile = [9, 9]
        w.location = "FarmHouse"
        w.is_outdoor_farm = False
        w.ui_script = [{"activeMenu": "ShippingMenu", "isModal": True}]
        worker = _ModalThenFarmWorker(w)
        run = self._run(w, worker)
        rep = self._rep()
        run._ensure_on_farm(w.obs(), rep)
        self.assertEqual(worker.ensure_calls, 2, "失败后必须重试一次")
        self.assertEqual(w.dismiss_calls, 1)
        gotos = self._events(run, "goto_farm")
        self.assertEqual([g["where"] for g in gotos], ["day_start", "day_start_retry"])
        self.assertTrue(gotos[-1]["ok"])
        self.assertEqual(w.location, "Farm")
        self.assertFalse(rep.notes, rep.notes)


    # ------------------------------------------------------------------ ⑨ 睡前清残留菜单
    def test_a_stray_shop_menu_is_dismissed_before_sleeping(self):
        """run8 day 13：`ShopMenu` 残留会把 `sleep` 卡成 `sleep_failed` ⇒ 睡前先关一次。"""
        w = self._world(money=0)
        run = self._run(w)
        run.worker = FakeWorker(w)
        rep = self._rep(13)
        w.ui_script = [{"activeMenu": "ShopMenu", "isModal": True}]
        by, _why = run._do_sleep(w.obs(), rep, "no_work:确实找不到可做的活")
        self.assertEqual(by, "sleep")
        self.assertEqual(w.dismiss_calls, 1, "睡前必须关掉残留模态")
        ev = self._events(run, "modal_dismissed")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["where"], "before_sleep")
        self.assertFalse(rep.slept_without_work)


class _StuckIndoorsWorker(FakeWorker):
    """task-104：`ensure_location` 永远失败 ⇒ 玩家留在室内。"""

    def __init__(self, world: FakeWorld) -> None:
        super().__init__(world)
        self.ensure_calls = 0

    def ensure_location(self, name, *, tile=None, timeout_ms=30000):
        self.ensure_calls += 1
        st = StepResult("ensure_location", None)
        st.ok = False
        st.code = "ui_modal"
        st.reason = "[ui_modal] 有菜单/对话挡着（'ShippingMenu'），所有技能都会被拒"
        st.receipt = "ui_modal"
        return st


class _IndoorPrepareWorker(_StuckIndoorsWorker):
    """`_prepare` 那一次 `ensure_location` 放行（否则 `run()` 直接起不来，code 2），之后全失败。

    复刻 run8 day 12 的下半段：`_prepare` 之后玩家仍在 FarmHouse，晨间 `ShippingMenu`
    把当天的 `goto_farm` 挡死 ⇒ 一整天在室内、`_water_far_dry` 够不着窗口外那格。
    """

    def ensure_location(self, name, *, tile=None, timeout_ms=30000):
        self.ensure_calls += 1
        st = StepResult("ensure_location", None)
        if self.ensure_calls == 1:
            st.ok = True
            st.code = "ok"
            st.reason = "（预备阶段）已在 Farm"
            return st
        st.ok = False
        st.code = "ui_modal"
        st.reason = "[ui_modal] 有菜单/对话挡着（'ShippingMenu'），所有技能都会被拒"
        st.receipt = "ui_modal"
        return st


class _FarmOnEnsureWorker(FakeWorker):
    """第一次回农场就成功（模态清掉之后回得去）：验"清模态 + 重试一次"真的能把人送回农场。"""

    def __init__(self, world: FakeWorld) -> None:
        super().__init__(world)
        self.ensure_calls = 0

    def ensure_location(self, name, *, tile=None, timeout_ms=30000):
        self.ensure_calls += 1
        self.w.location = "Farm"
        self.w.is_outdoor_farm = True
        st = StepResult("ensure_location", None)
        st.ok = True
        st.code = "ok"
        st.reason = f"已到 {name}"
        return st


class TestTask104FarDryNotOnFarm(unittest.TestCase):
    """task-104：人不在户外农场时，`_water_far_dry` 不许消耗额度、不许认输。

    真机证据（run8 day 12）：晨间 `ShippingMenu` 把 `goto_farm` 挡成 `ui_modal` ⇒ 人整天留
    FarmHouse，而 `_water_far_dry` 照样对着窗口外坐标走过去 ⇒ 6 格 × 2 次全 `unreachable`、
    6 格当天全进 `far_dry_given_up`，喂出"守卫说还有活、但没有任何作业区拿得出目标"⇒ 8 秒后
    0 农场动作就睡。修法：入口先确认人在户外农场（复用 task-102 的"清模态 + 重试一次"），
    不在就记 `water_far_skipped{reason:"not_on_farm"}`（**不 `try_++`、不进 `given_up`**），
    并让收尾理由点名 `not_on_farm`。人在农场时的行为一字不改。

    变异自检（`%TEMP%\\t104_mutate.py`，跑完即弃）：基线 **4/4 绿**；**m104a**（把入口的
    `if not self._is_farm(obs):` 整段短路）红 **3**（`test_indoors_does_not_consume_the_tile_quota`
    + `test_the_day_names_not_on_farm` + `test_a_stray_modal_is_cleared_and_the_player_returns`）。
    """

    #: 离玩家 [62,14] 曼哈顿距离 5 > 半径 3 ⇒ 不在观测窗口里（run8 的真实形态）。
    FAR = (61, 10)

    def _indoor_world(self, **kw) -> DryTilesWorld:
        w = DryTilesWorld(seeds=0, money=0, weeds=0, water_left=40, with_dry_tiles=True, **kw)
        w.dirt.add(self.FAR)
        w.crops[self.FAR] = {"watered": False, "ripe": False}
        w.player_tile = [62, 14]
        w.location = "FarmHouse"
        w.is_outdoor_farm = False
        return w

    def _rep(self, day: int = 12) -> DayReport:
        return DayReport(day_key=("summer", day, 12), started_at=0.0)

    def _run(self, w: FakeWorld, worker: FakeWorker, *, max_days: int = 1):
        run = make_run(w, target_days=1, max_days=max_days,
                       client_factory=lambda: FakeClient(w),
                       worker_factory=lambda _c: worker)
        run.worker = worker
        run.client = FakeClient(w)
        return run

    def _events(self, run, event):
        return [e for e in run.entries if e["event"] == event]

    def test_indoors_does_not_consume_the_tile_quota(self):
        """①人在室内 ⇒ 该格当日额度一次都不扣、不认输，只记 `water_far_skipped`。"""
        w = self._indoor_world()
        run = self._run(w, _StuckIndoorsWorker(w))
        rep = self._rep()

        moved = run._water_far_dry(w.obs(), rep)

        self.assertFalse(moved)
        self.assertEqual(run.far_dry_tries, {}, "人在室内不许消耗该格当日尝试额度")
        self.assertEqual(run.far_dry_given_up, set(), "人在室内不许把格子判死")
        self.assertTrue(run.water_far_not_on_farm)
        self.assertEqual([e for e in run.entries if e["event"] == "water_far"], [],
                         "人在室内根本不该发 water_far")
        skipped = self._events(run, "water_far_skipped")
        self.assertEqual(len(skipped), 1, f"应当恰记一条 water_far_skipped：{skipped}")
        self.assertEqual(skipped[0]["reason"], "not_on_farm")
        self.assertEqual(skipped[0]["count"], 1)
        self.assertEqual(skipped[0]["tiles"], [list(self.FAR)])
        self.assertEqual(len(self._events(run, "goto_farm")), 1, "仍要先试着回农场（清模态+重试）")

    def test_the_day_names_not_on_farm(self):
        """②当天因"人在室内"颗粒无收 ⇒ `ended_reason` 点名 `not_on_farm`、零认输、不 VERIFIED。"""
        w = self._indoor_world()
        run = self._run(w, _IndoorPrepareWorker(w), max_days=2)

        code = run.run()

        self.assertTrue(run.days, "至少该跑出一天（用来验收尾理由）")
        rep = run.days[0]
        self.assertNotEqual(code, 0, "一整天没动过农场 ⇒ 不许算达标")
        self.assertIn("not_on_farm", rep.ended_reason)
        # 两条诚实出口都可能走到（"没有作业区拿得出目标" 或 "连续 3 轮世界没变"）；关键是
        # **不许**洗成 `no_work`、不许 VERIFIED —— task-73 的有界翻篇（`stuck`）不在本卡改动范围。
        self.assertIn(rep.ended_by, ("slept_without_work", "stuck"))
        self.assertNotEqual(rep.ended_by, "no_work")
        self.assertFalse(rep.checks.get("day_justified"))
        self.assertFalse(rep.verified)
        self.assertEqual(w.watered_tiles, [], "室内根本浇不到那一格")
        self.assertEqual(run.far_dry_given_up, set())
        self.assertEqual(rep.gave_up_tiles, [])
        self.assertEqual([e for e in run.entries if e["event"] == "water_far"], [])
        self.assertTrue(self._events(run, "water_far_skipped"))

    def test_a_stray_modal_is_cleared_and_the_player_returns(self):
        """③复用 task-102 的"清模态 + 重试一次"：`ShippingMenu` 挡着 ⇒ 清掉后回农场再浇。"""
        w = self._indoor_world()
        w.ui_script = [{"activeMenu": "ShippingMenu", "isModal": True}]
        run = self._run(w, _FarmOnEnsureWorker(w))
        rep = self._rep()

        moved = run._water_far_dry(w.obs(), rep)

        self.assertTrue(moved, "清掉残留模态后应当能回农场并浇到那一格")
        self.assertEqual(run.far_dry_tries.get(self.FAR), 1)
        self.assertEqual(run.far_dry_given_up, set())
        self.assertFalse(run.water_far_not_on_farm)
        self.assertEqual([e["where"] for e in self._events(run, "modal_dismissed")], ["water_far"])
        self.assertEqual([e["where"] for e in self._events(run, "goto_farm")], ["water_far"])
        ev = self._events(run, "water_far")
        self.assertEqual(len(ev), 1)
        self.assertTrue(ev[0]["ok"])

    def test_on_farm_behaviour_is_unchanged(self):
        """④人在农场时的行为一字不改（回归：照旧走过去浇、额度照扣）。"""
        w = self._indoor_world()
        w.location = "Farm"
        w.is_outdoor_farm = True
        run = self._run(w, FakeWorker(w))
        rep = self._rep()

        moved = run._water_far_dry(w.obs(), rep)

        self.assertTrue(moved)
        self.assertFalse(run.water_far_not_on_farm)
        self.assertEqual(self._events(run, "water_far_skipped"), [])
        self.assertEqual(run.far_dry_tries.get(self.FAR), 1)
        ev = self._events(run, "water_far")
        self.assertEqual(len(ev), 1)
        self.assertTrue(ev[0]["ok"])
        self.assertEqual(ev[0]["dry_before"], 1)
        self.assertEqual(ev[0]["dry_after"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
