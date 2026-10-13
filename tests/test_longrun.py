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

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import MOD_VERSION_EXPECTED, BridgeError  # noqa: E402
from agentfarm.farmwork import (  # noqa: E402
    MAX_CLEAR_SWINGS, FarmWorker, STAGE_ACTION, StepResult, StageResult, seed_items,
)
from agentfarm.longrun import (  # noqa: E402
    DEFAULT_LLM_MAX_TOKENS, ENDED_BY_MODAL, JUSTIFIED_END_REASONS, MAX_ENV_ATTEMPTS,
    MAX_TILE_ATTEMPTS, DayReport, LongRun, _till_blocked_by, is_justified_end, plot_observe,
)
from agentfarm.planner import BoundaryPlanner, TaskIntent, deterministic_plan  # noqa: E402

SEED_ID = "472"
SEED_NAME = "Parsnip Seeds"


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
        #: （`FarmView` 的字段）。默认为空 ⇒ 走窗口口径，既有用例不受影响。
        self.is_outdoor_farm = True
        self.farm: dict | None = None
        self.seq = 1
        self.sleeps = 0
        self.refills = 0
        self.buys: list[int] = []
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
                           "plantable": False})
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
                       "wateringCan": {"present": True, "waterLeft": self.water_left,
                                       "max": 40, "bottomless": False, "upgradeLevel": 0}},
            "location": {"name": self.location, "isOutdoorFarm": self.is_outdoor_farm, "tiles": tiles,
                         "tilesTruncated": False,
                         "tillable": [list(t) for t in free], "refillTiles": [[70, 10], [70, 11]],
                         "refillTilesTruncated": False, "furniture": [], "doors": []},
            # task-19：真机观测里 `farm` 永远存在（未加载时 loaded=false/complete=true/全 0）。
            "farm": dict(self.farm) if self.farm else {},
            "ui": self.current_ui(),
            "liveness": {"worldAdvancing": True, "secondsSinceClockMoved": 1.0},
        }

    # ---- 技能（真的改世界）----
    def spend(self, action: str) -> None:
        self.stamina -= self.STAMINA_COST[action]

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
        price = 20
        can = min(int(count), self.money // price)
        if can < 1:
            return StepResult("buy", code="failed", reason=f"钱不够（{self.money}g < {price}g）")
        self.money -= price * can
        slot = self._seed_slot()
        if slot is None:
            self.inventory.append({"slot": 9, "id": SEED_ID, "qualifiedId": f"(O){SEED_ID}",
                                   "name": SEED_NAME, "stack": can, "isTool": False})
        else:
            slot["stack"] += can
        self.buys.append(can)
        return StepResult("buy", ok=True, reason=f"买到 {can} 个，钱 {self.money}g")

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
            if action in ("clear", "till", "water", "harvest", "sow") and self.w.stamina < min_stamina:
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
        self.assertEqual(w.sleeps, 0)
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


if __name__ == "__main__":
    unittest.main()

