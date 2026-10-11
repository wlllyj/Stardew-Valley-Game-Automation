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

from agentfarm.farmwork import (  # noqa: E402
    FarmWorker, KIND_TOOL, StepResult as SR, StageResult, till_blocked_by,
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

    # ---- 观测 ----
    def obs(self) -> dict:
        player: dict = {"name": "测试员", "tile": list(self.player_tile),
                        "stamina": self.stamina, "money": 500,
                        "farmingLevel": self.farming_level,
                        "inventory": [dict(i) for i in self.inventory]}
        if self.tools is not None:
            player["tools"] = dict(self.tools)
        return {
            "ok": True, "status": "ok",
            "clock": {"year": 1, "season": "spring", "day": 9, "timeOfDay": 1300},
            "player": player,
            "location": {"name": "Farm", "isOutdoorFarm": True,
                         "tiles": [dict(r) for r in self.records],
                         "tillable": [list(t) for t in sorted(self.tillable)],
                         "refillTiles": [], "furniture": []},
        }

    # ---- 回执（只是声明，判据看观测差分）----
    def use_tool(self, tile, tool=None):
        t = tuple(tile)
        self.calls.append((t, tool))
        if t in self.stuck:
            return {"ok": True, "status": "tool_ineffective"}
        new = self.result.get(t, DROP)
        if new is DROP:
            self.records = [r for r in self.records if tuple(r["tile"]) != t]
        else:
            for r in self.records:
                if tuple(r["tile"]) == t:
                    r["kind"] = new
        return {"ok": True, "status": "ok"}


class MiniBridge:
    """`FarmWorker` 要的最小桥面：observe / move_to / use_tool。"""

    def __init__(self, world: MiniWorld) -> None:
        self.w = world

    def observe(self, detail: str = "summary", *, timeout=None):
        return self.w.obs()

    def move_to(self, x, y, *, timeout_ms=None):
        self.w.player_tile = [int(x), int(y)]
        return {"ok": True, "status": "ok"}

    def use_tool(self, tile, *, tool=None, timeout_ms=None):
        return self.w.use_tool(tuple(tile), tool)


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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
