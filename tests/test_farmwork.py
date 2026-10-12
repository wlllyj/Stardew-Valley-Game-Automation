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
    FarmWorker, KIND_TOOL, MAX_CLEAR_SWINGS, StepResult as SR, StageResult, till_blocked_by,
    tool_missing_reason, tool_presence,
)

DROP = object()          # "这一格的障碍没了"（观测里那条记录消失）


class MiniWorld:
    """只有一格或几格的假世界：`use_tool` 真的改它、`obs()` 真的反映它。"""

    def __init__(self, *, records=None, tillable=(), inventory=None, tools=None,
                 farming_level: int = 0, stamina: float = 270.0) -> None:
        self.records = [dict(r) for r in (records or [])]
        self.tillable = {tuple(t) for t in tillable}
        self.inventory = [dict(i) for i in (inventory or [])]
        self.tools = tools
        self.farming_level = farming_level
        self.stamina = stamina
        self.player_tile = [62, 14]
        self.calls: list[tuple[tuple[int, int], str | None]] = []   # 每一次 use_tool 都被记下
        self.stuck: set[tuple[int, int]] = set()                    # 挥了也白挥的格子（真机 run1 的草）
        self.result: dict[tuple[int, int], object] = {}             # 动作后这一格变成什么（默认：记录消失）
        #: 这一格要**第几刀**才变（默认 1）—— 草是多刀特征：普通镰刀一刀只把 numberOfWeeds 减 1。
        self.swings_needed: dict[tuple[int, int], int] = {}
        #: 回执说"成了"但世界一动不动（真机 run1 镰刀假 ok 的复现）。
        self.lie: set[tuple[int, int]] = set()
        #: 这一格固定回哪个失败状态码（`tool_ineffective` / `no_save` / …）；给 list 则按顺序发。
        self.fail_status: dict[tuple[int, int], str | list[str]] = {}
        self.counts: dict[tuple[int, int], int] = {}                # 每格被挥了几次
        # ---- 睡觉（task-8）：床、提问、跨日 ----
        self.location_name = "FarmHouse"      # 默认已在卧室 ⇒ 省掉 ensure_location 那段
        self.bed = (62, 13)
        self.day = 9
        self.tod = 1300
        self.in_bed = False
        self.question: str | None = None       # None / "sleep" / "other"
        #: 踩床格（`allow_bed=True`）能不能引出游戏自己的提问 —— 真机 run2 就是**没引出来**。
        self.step_opens_question = True
        #: Mod `SleepSkill.Step()` 的离线替身：cross / no_day / no_question / timeout
        self.sleep_mode = "cross"
        self.moves: list[dict] = []            # 每一次 move_to（含 allow_bed）
        self.sleep_calls: list[int | None] = []
        self.interacts = 0

    # ---- 观测 ----
    def obs(self) -> dict:
        player: dict = {"name": "测试员", "tile": list(self.player_tile),
                        "stamina": self.stamina, "money": 500,
                        "farmingLevel": self.farming_level,
                        "inventory": [dict(i) for i in self.inventory]}
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
                                        "name": "Bed", "furnitureType": "bed"}]},
            # `ui` 块（v3 起才有）：睡觉判据看的就是它（`dialogueIsQuestion`）。
            "ui": {"activeMenu": ("DialogueBox" if self.question else None),
                   "activeMenuText": ("Go to sleep for the night?"
                                      if self.question == "sleep" else
                                      ("要卖掉手里的东西吗？" if self.question == "other" else "")),
                   "dialogueResponses": (["Yes", "No"] if self.question else []),
                   "dialogueIsQuestion": self.question is not None,
                   "isModal": self.question is not None},
        }

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
        if t in self.lie:
            return {"ok": True, "status": "ok",
                    "reason": f"已用「{tool}」对 {t} 动手 1 次，现在**已经空了**（假回执）"}
        if n < int(self.swings_needed.get(t, 1)):
            return {"ok": True, "status": "ok",
                    "reason": f"已用「{tool}」对 {t} 动手 1 次"}
        new = self.result.get(t, DROP)
        if new is DROP:
            self.records = [r for r in self.records if tuple(r["tile"]) != t]
        else:
            for r in self.records:
                if tuple(r["tile"]) == t:
                    r["kind"] = new
        return {"ok": True, "status": "ok",
                "reason": f"已用「{tool}」对 {t} 动手 {n} 次"}


class MiniBridge:
    """`FarmWorker` 要的最小桥面：observe / move_to / use_tool。"""

    def __init__(self, world: MiniWorld) -> None:
        self.w = world

    def observe(self, detail: str = "summary", *, timeout=None):
        return self.w.obs()

    def move_to(self, x, y, *, timeout_ms=None, based_on_seq=None, allow_bed=False):
        self.w.moves.append({"tile": [int(x), int(y)], "allow_bed": bool(allow_bed)})
        self.w.player_tile = [int(x), int(y)]
        # 踩到床格 ⇒ 游戏自己的 `checkAction(bed)` 会弹出睡觉提问（`allow_bed=False` 时 Mod 直接拒绝）。
        if allow_bed and (int(x), int(y)) == self.w.bed and self.w.step_opens_question:
            self.w.in_bed = True
            self.w.question = "sleep"
        return {"ok": True, "status": "ok"}

    def move_to_location(self, location, *, tile=None, timeout_ms=None, based_on_seq=None,
                         allow_bed=False):
        self.w.location_name = str(location)
        return {"ok": True, "status": "ok"}

    def interact(self, tile=None, *, timeout_ms=None):
        self.w.interacts += 1
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
    return FarmWorker(MiniBridge(world), log=lambda _s: None)


def grass_rec(tile=(60, 10)) -> dict:
    return {"tile": list(tile), "kind": "grass", "feature": "Grass", "tool": "scythe",
            "standable": True, "actionable": True}


def weed_rec(tile=(60, 10)) -> dict:
    return {"tile": list(tile), "kind": "weed", "standable": True, "actionable": True}


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
        """三类 status 集合：**两两互斥** + **并集覆盖 Mod 会返回的全部 status**（task-22 ④）。

        `world_fading` 是 task-7 新增的"渐黑不可起手"码；`timeout`/`error` 是"一次都没挥出去/
        没拿到结论"；剩下的是结论类。任何一类漏掉都会让格子被错误地封格或错误地吃配额。
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
        }
        self.assertEqual(mod_codes - (env | inert | incon), set(),
                         "Mod 会返回的 status 必须被三类之一覆盖")
        self.assertEqual(incon, {"timeout", "error"})
        self.assertEqual(env, {"no_save", "ui_modal", "world_fading"})
        self.assertEqual(inert, {"tool_ineffective", "precondition_failed"})
        # 只有 timeout/error 算"没结论"（Lead m01763）：回执 ok / 缺 status / 没见过的码都是
        # **真实回应** ⇒ 世界没变就是"这一刀白挥"，走结论（封格）路径，不算 inconclusive。
        self.assertEqual(fw._classify_status("ok"), (False, False))
        self.assertEqual(fw._classify_status(""), (False, False))
        self.assertEqual(fw._classify_status("brand_new_code"), (False, False))
        self.assertEqual(fw._classify_status("timeout"), (False, True))
        self.assertEqual(fw._classify_status("error"), (False, True))
        self.assertEqual(fw._classify_status("no_save"), (True, False))


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
    """task-8：睡觉走"踩床引出游戏自己的提问"，失败要快、要把 Mod 回执原文带出来。

    真机 run2 的教训：`interact(bed)` 从来没把提问弹出来（全日志 `answerDialogue(` 0 次），
    Mod 却照样白等 180s ⇒ 日期一天没跨。所以这里的断言全是"上床方式 / 失败多快 / 现场留没留"。
    """

    def test_steps_onto_bed_then_crosses_day(self):
        w = MiniWorld()
        r = make_worker(w).sleep()
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(w.day, 10)
        # 必须先**踩到床格**（allow_bed=True）—— 那是唯一能引出游戏自己 checkAction(bed) 的路。
        self.assertTrue(any(m["allow_bed"] and tuple(m["tile"]) == w.bed for m in w.moves), w.moves)
        self.assertEqual(w.sleep_calls, [15000])          # 预算已从 180s 收到 15s
        self.assertEqual(r.before["isInBed"], False)
        self.assertEqual(r.before["question"], "none")
        self.assertEqual(r.after["day"][2], 10)
        self.assertIn("已跨日", r.reason)
        self.assertIn("踩床格", r.reason)                  # 走了哪条路要能一眼看出来

    def test_travels_home_before_stepping_on_bed(self):
        w = MiniWorld()
        w.location_name = "Farm"
        r = make_worker(w).sleep()
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(w.location_name, "FarmHouse")
        self.assertEqual(w.day, 10)

    def test_no_question_fails_fast_with_mod_现场(self):
        """没引出提问 ⇒ Mod 秒级 `sleep_no_question`，而且现场（lastQuestionKey/isInBed）要带出来。"""
        w = MiniWorld()
        w.step_opens_question = False          # 踩床也没弹出提问（真机 run2 的实情）
        w.sleep_mode = "no_question"
        r = make_worker(w).sleep()
        self.assertFalse(r.ok)
        self.assertEqual(r.code, "sleep_no_question")     # Mod 的 status 原样透传，不许折成 failed
        self.assertEqual(r.receipt.split(":")[0], "sleep_no_question")
        for probe in ("lastQuestionKey", "isInBed", "activeClickableMenu"):
            self.assertIn(probe, r.reason)
        self.assertEqual(w.sleep_calls[-1], 15000)        # 请求预算 ≤15s：不许再白等 3 分钟
        self.assertEqual(w.interacts, 1)                  # 兜底 interact(床) 发过（旧路径）
        self.assertIn("脑侧现场", r.reason)
        self.assertFalse(r.proven_inert)

    def test_timeout_keeps_mod_diagnosis(self):
        w = MiniWorld()
        w.sleep_mode = "timeout"
        r = make_worker(w).sleep()
        self.assertFalse(r.ok)
        self.assertEqual(r.code, "timeout")
        self.assertIn("newDaySync", r.reason)             # Diagnose() 的原文进 reason
        self.assertTrue(r.receipt)

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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
