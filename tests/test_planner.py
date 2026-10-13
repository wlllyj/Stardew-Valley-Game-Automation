# -*- coding: utf-8 -*-
"""P3 第⑤步 · 边界决策层（`brain/agentfarm/planner.py`）单测。

覆盖点（对应 docs/_p3-kickoff.md ⑤ 与 docs/01-架构设计.md §5.2.1/§5.4/§5.5）：

1. **LLM 输出校验**：合法意图解析通过；带格坐标、未知锚点、多余/缺失字段、
   未知 task、空列表、畸形 JSON 一律**整条拒收**；
2. **坐标红线**：`find_coordinate_like()` 抓各种坐标写法；系统提示词 + 情境简报里
   **一个坐标都没有**（旧项目就是把硬编码坐标泄漏进 prompt 才翻车的）；
3. **边界状态机**：换任务类型 / 异常恢复 / 跨日复盘各自触发；常规区间与
   "刚处理过的同一个失败"都是 0 次调用（用调用计数断言）；
4. **确定性降级**：`LlmError`、任意异常、坐标被拒 → 退回纯代码策略，**不崩**；
   关掉开关（`llm_enabled=False`，真机默认）时边界也 0 次调用；
5. **重问 1 次**：坏输出 → 带原因重问 → 仍坏才降级（§5.5 的校验链）；
6. **终态只有 VERIFIED / needs_review**：未完成 / 跳过 / 异常都不得报成功；
7. **简报生成**：`Brief.from_observe()` 从 `detail=full` 快照取逐格真值，
   summary 快照退回 farm 段计数，且 ≤2 KB。

⚠️ 本文件**绝不触发真实 LLM 调用**：所有 planner 都注入假 chat，且假 chat 只返回
硬编码字符串；模块级只 import `llm` 的类型（`LlmError` / `LlmResult`），
import 本身不发请求。
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm import planner as P  # noqa: E402
from agentfarm.llm import LlmError, LlmResult, Usage  # noqa: E402


# --------------------------------------------------------------------------- 工具
def make_counts(**over: int) -> dict:
    counts = dict(P._EMPTY_COUNTS)
    counts.update(over)
    return counts


def make_brief(**over) -> P.Brief:
    """默认：露天农场、存档已加载、体力充足、无障碍、无可锄空地 → 确定性策略给 review。"""
    base = dict(
        location="Farm",
        is_farm=True,
        has_save=True,
        day_key=(1, "spring", 5),
        stamina=200.0,
        max_stamina=270.0,
        counts=make_counts(),
        seed_ids=("472",),
        seed_count=15,
        inventory_size=3,
        tiles_present=True,
        target_tiles=9,
    )
    base.update(over)
    return P.Brief(**base)


def till_brief(**over) -> P.Brief:
    return make_brief(counts=make_counts(tillable=12), **over)


def valid_payload(task: str = "till_area", area: str = "tillable[0:9]") -> str:
    return json.dumps({
        "tasks": [{
            "task": task,
            "area_hint": area,
            "reason": "地块还差几格没开垦",
            "expected_evidence": "location.tiles[].kind 中 dirt 数量上升",
        }]
    }, ensure_ascii=False)


class FakeChat:
    """假 LLM seam：记录每次调用（消息 + kwargs），按脚本回放，可回放异常。"""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []
        self.kwargs: list[dict] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def __call__(self, messages, **kwargs):
        self.calls.append([dict(m) for m in messages])
        self.kwargs.append(dict(kwargs))
        index = min(len(self.calls) - 1, len(self.replies) - 1)
        reply = self.replies[index] if self.replies else ""
        if isinstance(reply, BaseException):
            raise reply
        return reply


# ------------------------------------------------------------------- 坐标红线
class CoordinateRejectionTests(unittest.TestCase):
    """解析层必须拒收一切带格坐标的输出（P3 的 P1 级决策：坐标由技能层现场算）。"""

    def test_find_coordinate_like_catches_common_forms(self):
        """各种坐标写法都要被抓住（形状判断，不做语义猜测）。"""
        hits = [
            "先走到 [56,19]",
            "(56, 19)",
            "56,19",
            "x=56",
            "Y = 19",
            "tile 56 19",
            "格 60 20",
            "坐标 64 15",
        ]
        for text in hits:
            with self.subTest(text=text):
                self.assertIsNotNone(P.find_coordinate_like(text), text)

    def test_find_coordinate_like_allows_reference_slice(self):
        """`tillable[0:9]` 这种切片**不能**被误判成坐标（否则合法引用全废）。"""
        for text in ("tillable[0:9]", "tiles.plantable", "anchor:player", "near:player", "farm.weeds"):
            with self.subTest(text=text):
                self.assertIsNone(P.find_coordinate_like(text), text)

    def test_area_hint_with_coordinate_is_rejected(self):
        """合法 JSON 但 area_hint 是坐标 → 整条拒收。"""
        raw = valid_payload(area="[56,19]")
        intents, problems = P.parse_intents(raw, allowed_anchors=("player",))
        self.assertEqual(intents, [])
        self.assertTrue(any("coordinate_in_intent" in p for p in problems), problems)

    def test_reason_with_coordinate_is_rejected(self):
        """坐标藏在 reason/expected_evidence 里同样拒收（别只想堵 area_hint）。"""
        raw = json.dumps({"tasks": [{
            "task": "till_area",
            "area_hint": "tillable[0:9]",
            "reason": "先走到 (64,15) 再锄",
            "expected_evidence": "dirt 上升",
        }]}, ensure_ascii=False)
        intents, problems = P.parse_intents(raw, allowed_anchors=("player",))
        self.assertEqual(intents, [])
        self.assertTrue(any("coordinate_in_intent:reason" in p for p in problems), problems)

    def test_schema_forbids_extra_fields_like_tile(self):
        """schema 只有 4 个字段：多出 `tile`/`x`/`y` 一律拒收（没地方放坐标）。"""
        self.assertEqual(set(P.INTENT_FIELDS), {"task", "area_hint", "reason", "expected_evidence"})
        raw = json.dumps({"tasks": [{
            "task": "till_area", "area_hint": "tillable[0:9]", "reason": "r",
            "expected_evidence": "e", "tile": [56, 19],
        }]}, ensure_ascii=False)
        intents, problems = P.parse_intents(raw, allowed_anchors=("player",))
        self.assertEqual(intents, [])
        self.assertTrue(any("extra_fields" in p and "tile" in p for p in problems), problems)


# --------------------------------------------------------------- 输出校验/解析
class ParseValidationTests(unittest.TestCase):
    def test_valid_intent_parses(self):
        intents, problems = P.parse_intents(valid_payload(), allowed_anchors=("player",))
        self.assertEqual(problems, [])
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].task, "till_area")
        self.assertEqual(intents[0].area_hint, "tillable[0:9]")

    def test_accepts_fenced_json_and_prose_wrapped_json(self):
        """LLM 常把 JSON 包在 ``` 围栏或解释文字里，解析层要能抠出来。"""
        fenced = "好的，如下：\n```json\n" + valid_payload() + "\n```\n以上。"
        intents, problems = P.parse_intents(fenced, allowed_anchors=("player",))
        self.assertEqual(problems, [])
        self.assertEqual(len(intents), 1)

    def test_unknown_anchor_is_rejected(self):
        """引用不存在的东西 = 幻觉，必须退（防幻觉校验链）。"""
        raw = valid_payload(area="anchor:greenhouse")
        intents, problems = P.parse_intents(raw, allowed_anchors=("player", "current_location"))
        self.assertEqual(intents, [])
        self.assertTrue(any("unknown_anchor" in p for p in problems), problems)

    def test_anchor_present_in_brief_is_accepted(self):
        allowed = P.allowed_area_hints(make_brief())
        self.assertIn("player", allowed)
        intents, problems = P.parse_intents(valid_payload(task="recover_stamina", area="anchor:player"),
                                           allowed_anchors=allowed)
        self.assertEqual(problems, [])
        self.assertEqual(intents[0].area_hint, "anchor:player")

    def test_named_zone_reference_is_accepted_when_brief_lists_it(self):
        """用户 m00601：大模型要能给出"大致方向"（哪片田区），但坐标一律由代码落。

        田区名写在简报里（`Brief.areas`）⇒ 裸 `field_nw` 与 `anchor:field_nw` 都必须接受；
        简报里没有的名字（编造的田区）必须拒收，不能让它凭空指一块地。
        """
        brief = make_brief(areas=("field_nw", "field_ne"))
        allowed = P.allowed_area_hints(brief)
        self.assertIn("field_nw", allowed)

        # 与 `BoundaryPlanner.decide()` 的真实调用口径一致（锚点 + 动态引用名两路都给）
        def parse(raw):
            return P.parse_intents(raw, allowed_anchors=allowed, allowed_refs=brief.areas)

        bare, problems = parse(valid_payload(area="field_nw"))
        self.assertEqual(problems, [], problems)
        self.assertEqual(bare[0].area_hint, "field_nw")

        anchored, problems2 = parse(valid_payload(area="anchor:field_ne"))
        self.assertEqual(problems2, [], problems2)
        self.assertEqual(anchored[0].area_hint, "anchor:field_ne")

        invented, problems3 = parse(valid_payload(area="field_sw"))
        self.assertEqual(invented, [])
        self.assertTrue(any("unknown_reference" in p or "unknown_anchor" in p for p in problems3),
                        problems3)

    def test_unknown_task_and_bad_reference_are_rejected(self):
        raw = valid_payload(task="mine_diamonds")
        intents, problems = P.parse_intents(raw, allowed_anchors=("player",))
        self.assertEqual(intents, [])
        self.assertTrue(any("unknown_task" in p for p in problems), problems)
        raw2 = valid_payload(area="somewhere_else")
        _, problems2 = P.parse_intents(raw2, allowed_anchors=("player",))
        self.assertTrue(any("unknown_reference" in p for p in problems2), problems2)

    def test_missing_fields_and_empty_and_broken_json_are_rejected(self):
        cases = {
            "missing": json.dumps({"tasks": [{"task": "till_area", "area_hint": "tillable[0:9]"}]}),
            "empty": json.dumps({"tasks": []}),
            "broken": "我认为应该先锄地。",
            "not_object": json.dumps({"tasks": ["till_area"]}),
        }
        for name, raw in cases.items():
            with self.subTest(case=name):
                intents, problems = P.parse_intents(raw, allowed_anchors=("player",))
                self.assertEqual(intents, [])
                self.assertTrue(problems)

    def test_all_deterministic_intents_pass_their_own_validation(self):
        """自洽性：纯代码策略给出的每条意图都必须能通过 LLM 那套校验。

        否则"降级"就会被自己的校验链拒掉 —— 降级路径必须也是合法路径。
        """
        briefs = [
            make_brief(has_save=False),
            make_brief(stamina=0.0),
            make_brief(counts=make_counts(blockers=3, weeds=3)),
            till_brief(),
            make_brief(counts=make_counts(dirt=9, plantable=9, tillable=0)),
            make_brief(counts=make_counts(dirt=9, crops=9, unwatered_crops=9)),
            make_brief(counts=make_counts(dirt=9, crops=9, unwatered_crops=0, ripe=2)),
            make_brief(),
        ]
        for brief in briefs:
            for intent in P.deterministic_plan(brief):
                with self.subTest(task=intent.task, area=intent.area_hint):
                    self.assertEqual(P.validate_intent(intent, allowed_anchors=P.allowed_area_hints(brief)), [])

    # ---- 真机回归：提示词允许的写法，校验器必须原样接受 -------------------------------
    def test_current_location_plain_reference_is_accepted(self):
        """`{"area_hint": "current_location"}` 必须合法。

        真机复现（2026-10-11, logs/plan-llm-manual-2.log）：系统提示词把 `current_location`
        列为合法 area_hint，模型就老实用了它，却被判 `unknown_reference`，整条拒收、白烧一次重问。
        原因：`current_location` 只在 `_BASE_ANCHORS`（`anchor:current_location`）里，
        不在 `AREA_REF_PREFIXES` 里。**照提示词写就被罚**，这类不一致必须在测试里钉住。
        """
        raw = valid_payload(area="current_location")
        intents, problems = P.parse_intents(raw, allowed_anchors=P.allowed_area_hints(make_brief()))
        self.assertEqual(problems, [])
        self.assertEqual(intents[0].area_hint, "current_location")

    def test_every_reference_advertised_in_prompt_is_accepted(self):
        """提示词里报出的每个引用前缀 / 相对锚点，校验器都必须接受（防再次漂移）。

        这是"提示词 ↔ 校验器"的契约测试：以后谁往 `AREA_REF_PREFIXES` 或锚点里加东西
        却忘了让 `build_messages` 报出来（或反过来），这条会红。
        """
        brief = till_brief()
        allowed = P.allowed_area_hints(brief)
        system, user = (m["content"] for m in P.build_messages(brief, boundary=P.BOUNDARY_NEW_DAY))

        for prefix in P.AREA_REF_PREFIXES:
            with self.subTest(kind="prefix", name=prefix):
                self.assertIn(prefix, system)
                intents, problems = P.parse_intents(valid_payload(area=prefix), allowed_anchors=allowed)
                self.assertEqual(problems, [], f"提示词报了前缀 {prefix}，校验器却拒收")
                self.assertEqual(len(intents), 1)
        for anchor in allowed:
            with self.subTest(kind="anchor", name=anchor):
                self.assertIn(anchor, system)
                intents, problems = P.parse_intents(valid_payload(area=f"anchor:{anchor}"),
                                                    allowed_anchors=allowed)
                self.assertEqual(problems, [], f"提示词报了锚点 {anchor}，校验器却拒收")
                self.assertEqual(len(intents), 1)
        # 反过来：系统提示词里不应还留着没被替换掉的占位符（会误导模型照抄 __REFS__）。
        for token in ("__KINDS__", "__PREFIXES__", "__ANCHORS__", "__SCHEMA__", "__REFS__"):
            self.assertNotIn(token, system)
        self.assertTrue(user.strip())


# ------------------------------------------------------------- 确定性策略
class DeterministicPlanTests(unittest.TestCase):
    """纯代码策略：LLM 不可用时的底座，必须给出**可执行**的下一步。"""

    def test_no_save_comes_first(self):
        intent = P.deterministic_plan(make_brief(has_save=False))[0]
        self.assertEqual(intent.task, "wait_for_save")
        self.assertEqual(intent.area_hint, "anchor:current_location")

    def test_zero_stamina_recovers(self):
        self.assertEqual(P.deterministic_plan(make_brief(stamina=0.0))[0].task, "recover_stamina")

    def test_unknown_stamina_does_not_trigger_recovery(self):
        """stamina 缺失（None）不能当成 0，否则一上来就误判"体力耗尽"。"""
        self.assertNotEqual(P.deterministic_plan(make_brief(stamina=None))[0].task, "recover_stamina")

    def test_clear_then_till_then_plant_then_water(self):
        """农务自然顺序：清障 → 开垦 → 播种 → 浇水。"""
        clear = P.deterministic_plan(make_brief(counts=make_counts(blockers=5, weeds=5, tillable=12)))[0]
        self.assertEqual((clear.task, clear.area_hint), ("clear_area", "near:player"))

        till = P.deterministic_plan(till_brief())[0]
        self.assertEqual((till.task, till.area_hint), ("till_area", "tillable[0:9]"))

        plant = P.deterministic_plan(make_brief(counts=make_counts(dirt=9, plantable=9)))[0]
        self.assertEqual((plant.task, plant.area_hint), ("plant_area", "tiles.plantable"))

        water = P.deterministic_plan(make_brief(counts=make_counts(dirt=9, crops=9, unwatered_crops=9)))[0]
        self.assertEqual((water.task, water.area_hint), ("water_area", "tiles.unwatered_crops"))

    def test_plant_without_seeds_still_plans_and_says_so(self):
        """没种子也照样把 plant_area 提出来（让技能层 precondition_failed ⇒ 触发恢复边界）。"""
        brief = make_brief(counts=make_counts(dirt=9, plantable=9), seed_ids=(), seed_count=0)
        intent = P.deterministic_plan(brief)[0]
        self.assertEqual(intent.task, "plant_area")
        self.assertIn("没有种子", intent.reason)

    def test_ripe_harvest_and_review_fallback(self):
        harvest = P.deterministic_plan(make_brief(counts=make_counts(dirt=9, crops=9, ripe=2)))[0]
        self.assertEqual((harvest.task, harvest.area_hint), ("harvest", "tiles.ripe"))
        self.assertEqual(P.deterministic_plan(make_brief())[0].task, "review")

    def test_deterministic_plan_never_returns_empty(self):
        self.assertTrue(P.deterministic_plan(make_brief()))
        self.assertTrue(P.deterministic_plan(make_brief(has_save=False, stamina=0.0)))

    def test_sellable_loot_ships_before_tilling_or_planting(self):
        """task-42：今天亲手收获的东西**先出掉**（卖了才有钱买种子），且排在开垦/播种前。

        `sellable` 不是观测推出来的字段（白名单在 `FarmWorker.harvested`，由长跑控制器注入），
        所以这里钉死两件事：①它 >0 时才出现 `ship`；②它排在"清障/开垦/播种"之前。
        """
        brief = make_brief(counts=make_counts(tillable=12, dirt=9, plantable=9), sellable=3)
        intent = P.deterministic_plan(brief)[0]
        self.assertEqual(intent.task, "ship")
        self.assertIn("3 件", intent.reason)
        self.assertIn("NewDay", intent.expected_evidence)
        no_loot = make_brief(counts=make_counts(tillable=12, dirt=9, plantable=9), sellable=0)
        self.assertNotEqual(P.deterministic_plan(no_loot)[0].task, "ship")

    def test_dry_crops_still_outrank_shipping(self):
        """浇水永远第一优先：地里有干作物时不许先去卖东西。"""
        brief = make_brief(counts=make_counts(dirt=9, crops=9, unwatered_crops=4), sellable=3)
        self.assertEqual(P.deterministic_plan(brief)[0].task, "water_area")


# --------------------------------------------------------- 终态只有两个
class TerminalStateTests(unittest.TestCase):
    def test_verified_requires_met_postcondition(self):
        self.assertEqual(P.classify_outcome(postcondition_met=True), P.TERMINAL_VERIFIED)
        outcome = P.TaskOutcome(kind="till_area", postcondition_met=True, reason="dirt 由 0 → 1")
        self.assertEqual(outcome.terminal, P.TERMINAL_VERIFIED)
        self.assertTrue(outcome.verified)

    def test_unfinished_never_reports_success(self):
        """未完成 / 跳过 / 异常 / 只有进度 ⇒ 一律 needs_review（"跳过 ≠ 完成"）。"""
        cases = {
            "未达成后置条件": P.TaskOutcome(kind="till_area", postcondition_met=False, progress=True),
            "被跳过": P.TaskOutcome(kind="till_area", postcondition_met=True, skipped=True),
            "工具报错": P.TaskOutcome(kind="till_area", postcondition_met=True, error="tool_ineffective"),
        }
        for name, outcome in cases.items():
            with self.subTest(case=name):
                self.assertEqual(outcome.terminal, P.TERMINAL_NEEDS_REVIEW)
                self.assertFalse(outcome.verified)

    def test_terminal_states_are_exactly_two(self):
        self.assertEqual(set(P.TERMINAL_STATES), {"VERIFIED", "needs_review"})
        self.assertNotIn("progress", P.TERMINAL_STATES)
        self.assertNotIn("done", P.TERMINAL_STATES)

    def test_task_outcome_is_json_serializable(self):
        payload = P.TaskOutcome(kind="water_area", postcondition_met=True, evidence=("watered 上升",)).as_dict()
        self.assertEqual(json.loads(json.dumps(payload, ensure_ascii=False))["terminal"], P.TERMINAL_VERIFIED)


# --------------------------------------------------------- 边界状态机
class BoundaryStateMachineTests(unittest.TestCase):
    """LLM 调用次数 == 边界次数：非边界 0 次，每个边界恰好 1 次。"""

    def make_planner(self, chat, **kwargs):
        kwargs.setdefault("max_llm_attempts", 1)
        return P.BoundaryPlanner(llm_chat=chat, llm_enabled=True, **kwargs)

    def test_steady_state_makes_zero_llm_calls(self):
        """常规区间（同一任务阶段、无新失败、同一天）→ 纯代码，一次都不喊慢脑。"""
        chat = FakeChat(valid_payload())
        planner = self.make_planner(chat)
        state = P.PlannerState(day_key=(1, "spring", 5), last_task_kind="till_area", last_seen_failures=0)
        decision = planner.decide(state, till_brief())
        self.assertIsNone(decision.boundary)
        self.assertEqual(decision.source, P.SOURCE_DETERMINISTIC)
        self.assertFalse(decision.llm_called)
        self.assertEqual(chat.call_count, 0)
        self.assertEqual(state.llm_calls, 0)
        self.assertEqual(decision.task_kind, "till_area")

    def test_new_day_boundary_makes_exactly_one_call(self):
        """跨日复盘：day_key 变了 ⇒ 边界，且只调 1 次。"""
        chat = FakeChat(valid_payload(task="review", area="anchor:current_location"))
        planner = self.make_planner(chat)
        state = P.PlannerState(day_key=(1, "spring", 5), last_task_kind="till_area", last_seen_failures=0)
        decision = planner.decide(state, till_brief(day_key=(1, "spring", 6)))
        self.assertEqual(decision.boundary, P.BOUNDARY_NEW_DAY)
        self.assertEqual(decision.source, P.SOURCE_LLM)
        self.assertTrue(decision.llm_called)
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(state.llm_calls, 1)
        self.assertEqual(state.last_boundary, P.BOUNDARY_NEW_DAY)

    def test_recovery_boundary_makes_exactly_one_call(self):
        """异常恢复：连续失败计数上升 ⇒ 边界。"""
        chat = FakeChat(valid_payload())
        planner = self.make_planner(chat)
        state = P.PlannerState(day_key=(1, "spring", 5), last_task_kind="till_area", last_seen_failures=0)
        decision = planner.decide(state, till_brief(consecutive_failures=2, last_failure="tool_ineffective"))
        self.assertEqual(decision.boundary, P.BOUNDARY_RECOVERY)
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(state.last_seen_failures, 2)

    def test_same_failure_after_recovery_does_not_call_again(self):
        """已经为这次失败喊过一次慢脑，同样的失败计数不该每步都喊（否则边界形同虚设）。"""
        chat = FakeChat(valid_payload())
        planner = self.make_planner(chat)
        state = P.PlannerState(day_key=(1, "spring", 5), last_task_kind="till_area", last_seen_failures=0)
        brief = till_brief(consecutive_failures=3, last_failure="vetoed")
        self.assertEqual(planner.decide(state, brief).boundary, P.BOUNDARY_RECOVERY)
        second = planner.decide(state, brief)
        self.assertIsNone(second.boundary)
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(state.llm_calls, 1)

    def test_task_kind_change_boundary_makes_exactly_one_call(self):
        """换任务类型：代码策略的阶段从 clear_area 进到 till_area ⇒ 边界。"""
        chat = FakeChat(valid_payload())
        planner = self.make_planner(chat)
        state = P.PlannerState(day_key=(1, "spring", 5), last_task_kind="clear_area", last_seen_failures=0)
        decision = planner.decide(state, till_brief())
        self.assertEqual(decision.boundary, P.BOUNDARY_TASK_CHANGE)
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(state.last_task_kind, "till_area")

    def test_first_ever_decision_is_not_a_task_change(self):
        """首次决策没有"上一个任务阶段"，不该凭空造一个边界。"""
        chat = FakeChat(valid_payload())
        planner = self.make_planner(chat)
        state = P.PlannerState()
        decision = planner.decide(state, till_brief())
        self.assertIsNone(decision.boundary)
        self.assertEqual(chat.call_count, 0)
        self.assertEqual(state.day_key, (1, "spring", 5))
        self.assertEqual(state.last_task_kind, "till_area")

    def test_llm_disabled_switch_makes_zero_calls_even_on_boundary(self):
        """真机默认：开关关着，边界也只跑纯代码策略（用户 m01184 的"先告知再介入"）。"""
        chat = FakeChat(valid_payload())
        planner = P.BoundaryPlanner(llm_chat=chat, llm_enabled=False)
        state = P.PlannerState(day_key=(1, "spring", 5), last_task_kind="till_area", last_seen_failures=0)
        decision = planner.decide(state, till_brief(day_key=(1, "spring", 6)))
        self.assertEqual(decision.boundary, P.BOUNDARY_NEW_DAY)
        self.assertEqual(decision.source, P.SOURCE_DETERMINISTIC_FALLBACK)
        self.assertFalse(decision.llm_called)
        self.assertEqual(decision.fallback_reason, "llm_disabled")
        self.assertEqual(chat.call_count, 0)
        self.assertTrue(decision.intents)

    def test_llm_calls_equal_boundaries_over_a_run(self):
        """跑一段连续决策：调用次数必须恰好等于边界次数。"""
        chat = FakeChat(valid_payload())
        planner = self.make_planner(chat)
        state = P.PlannerState()
        days = [(1, "spring", 5), (1, "spring", 5), (1, "spring", 6), (1, "spring", 6), (1, "spring", 7)]
        boundaries = 0
        for day in days:
            decision = planner.decide(state, till_brief(day_key=day))
            if decision.boundary:
                boundaries += 1
            state.last_task_kind = "till_area"  # 技能层持续在锄地
        self.assertEqual(boundaries, 2)  # 两次跨日（5→6、6→7）
        self.assertEqual(chat.call_count, boundaries)


# --------------------------------------------------------- 降级路径
class DegradationTests(unittest.TestCase):
    """LLM 不可用/输出非法 → 确定性降级，绝不崩。"""

    def boundary_state(self) -> P.PlannerState:
        return P.PlannerState(day_key=(1, "spring", 5), last_task_kind="till_area", last_seen_failures=0)

    def test_llm_error_degrades_to_deterministic(self):
        chat = FakeChat(LlmError("密钥不存在", status="no_api_key"))
        planner = P.BoundaryPlanner(llm_chat=chat, max_llm_attempts=1)
        decision = planner.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6)))
        self.assertEqual(decision.boundary, P.BOUNDARY_NEW_DAY)
        self.assertEqual(decision.source, P.SOURCE_DETERMINISTIC_FALLBACK)
        self.assertTrue(decision.llm_called)
        self.assertIn("llm_error:no_api_key", decision.fallback_reason or "")
        self.assertEqual([i.task for i in decision.intents], ["till_area"])

    def test_unexpected_exception_degrades_without_raising(self):
        chat = FakeChat(RuntimeError("boom"))
        planner = P.BoundaryPlanner(llm_chat=chat, max_llm_attempts=1)
        decision = planner.decide(self.boundary_state(), till_brief(consecutive_failures=1))
        self.assertEqual(decision.source, P.SOURCE_DETERMINISTIC_FALLBACK)
        self.assertIn("llm_exception:RuntimeError", decision.fallback_reason or "")

    def test_coordinate_output_degrades(self):
        """含坐标的输出 → 拒收 → 降级（同时保留拒收原因便于事后复盘）。"""
        chat = FakeChat(valid_payload(area="[56,19]"))
        planner = P.BoundaryPlanner(llm_chat=chat, max_llm_attempts=1)
        decision = planner.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6)))
        self.assertEqual(decision.source, P.SOURCE_DETERMINISTIC_FALLBACK)
        self.assertIn("coordinate_in_intent", decision.fallback_reason or "")
        self.assertEqual([i.task for i in decision.intents], ["till_area"])

    def test_retry_once_then_accept(self):
        """坏输出 → 带原因重问 1 次 → 第二次合法就采用（§5.5 的校验链）。"""
        chat = FakeChat(valid_payload(area="[56,19]"), valid_payload(task="review", area="anchor:current_location"))
        planner = P.BoundaryPlanner(llm_chat=chat, max_llm_attempts=2)
        decision = planner.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6)))
        self.assertEqual(decision.source, P.SOURCE_LLM)
        self.assertEqual(decision.attempts, 2)
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(decision.task_kind, "review")
        # 重问必须把那次的拒收原因带上，否则模型只能瞎猜
        self.assertIn("上一次输出被拒收", chat.calls[1][-1]["content"])
        self.assertIn("coordinate_in_intent", chat.calls[1][-1]["content"])

    def test_retry_exhausted_then_degrades(self):
        chat = FakeChat("不是 JSON", "还是不是 JSON")
        planner = P.BoundaryPlanner(llm_chat=chat, max_llm_attempts=2)
        decision = planner.decide(self.boundary_state(), till_brief(consecutive_failures=1))
        self.assertEqual(decision.source, P.SOURCE_DETERMINISTIC_FALLBACK)
        self.assertEqual(chat.call_count, 2)
        self.assertTrue(decision.problems)
        self.assertTrue(decision.degraded)

    def test_result_object_and_plain_string_both_work(self):
        """seam 返回值既支持 `LlmResult`（默认 `llm.chat` 的返回）也支持裸字符串。"""
        as_result = FakeChat(LlmResult(content=valid_payload()))
        planner = P.BoundaryPlanner(llm_chat=as_result, max_llm_attempts=1)
        self.assertEqual(planner.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6))).source, P.SOURCE_LLM)

        as_text = FakeChat(valid_payload())
        planner2 = P.BoundaryPlanner(llm_chat=as_text, max_llm_attempts=1)
        self.assertEqual(planner2.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6))).source, P.SOURCE_LLM)

    def test_result_without_content_degrades(self):
        chat = FakeChat(object())
        planner = P.BoundaryPlanner(llm_chat=chat, max_llm_attempts=1)
        decision = planner.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6)))
        self.assertEqual(decision.source, P.SOURCE_DETERMINISTIC_FALLBACK)
        self.assertIn("llm_result_without_content", decision.fallback_reason or "")

    def test_decision_is_json_serializable(self):
        chat = FakeChat(LlmError("超时", status="network"))
        planner = P.BoundaryPlanner(llm_chat=chat, max_llm_attempts=1)
        payload = planner.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6))).as_dict()
        round_tripped = json.loads(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(round_tripped["source"], P.SOURCE_DETERMINISTIC_FALLBACK)
        self.assertEqual(round_tripped["tasks"][0]["task"], "till_area")

    def test_planner_does_not_touch_default_seam_when_injected(self):
        """注入假实现后，`planner.llm_chat` 必须就是我给的那个（绝不偷偷用会联网的默认实现）。"""
        chat = FakeChat(valid_payload())
        planner = P.BoundaryPlanner(llm_chat=chat)
        self.assertIs(planner.llm_chat, chat)
        self.assertIsNot(planner.llm_chat, P.default_llm_chat)

    def test_default_seam_is_the_network_one_but_lazily(self):
        """默认实现指向 `default_llm_chat`（唯一会联网的路），但构造它不产生任何请求。"""
        planner = P.BoundaryPlanner(llm_enabled=False)
        self.assertIs(planner.llm_chat, P.default_llm_chat)
        self.assertEqual(planner.llm_enabled, False)

    def test_prompt_never_contains_coordinates(self):
        """系统提示词与用户消息里一个坐标都没有（旧项目正是栽在这）。"""
        chat = FakeChat(valid_payload())
        planner = P.BoundaryPlanner(llm_chat=chat, max_llm_attempts=1)
        planner.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6)))
        system, user = chat.calls[0][0], chat.calls[0][1]
        self.assertIsNone(P.find_coordinate_like(system["content"]))
        self.assertIsNone(P.find_coordinate_like(user["content"]))
        self.assertIn("area_hint", system["content"])  # schema 讲清楚了
        self.assertIn("tillable", system["content"])   # 允许的引用列出来了


# --------------------------------------------------------- 简报（Brief）
class BriefTests(unittest.TestCase):
    SNAPSHOT = {
        "hasSaveLoaded": True,
        "clock": {"year": 1, "season": "spring", "day": 5, "time": 640},
        "player": {
            "stamina": 180.0, "maxStamina": 270.0, "location": "Farm",
            "inventory": [
                {"slot": 0, "id": "Hoe", "name": "Hoe", "stack": 1, "isTool": True},
                {"slot": 1, "id": "472", "name": "Parsnip Seeds", "stack": 15, "isTool": False},
            ],
        },
        "location": {
            "name": "Farm", "isOutdoorFarm": True, "isFarm": True,
            "tillable": [[60, 20], [61, 20], [62, 20]],
            "doors": [{"tile": [64, 15], "type": "Farmhouse"}],
            "tiles": [
                {"tile": [60, 20], "kind": "weed", "tool": "hoe", "standable": False, "actionable": True},
                {"tile": [61, 20], "kind": "stone", "tool": "pickaxe"},
                {"tile": [62, 20], "kind": "twig", "tool": "axe"},
                {"tile": [63, 20], "kind": "dirt", "feature": "HoeDirt", "plantable": True, "watered": False},
                {"tile": [64, 20], "kind": "dirt", "feature": "HoeDirt", "plantable": False,
                 "crop": "24", "ripe": True, "watered": True},
                {"tile": [65, 20], "kind": "dirt", "feature": "HoeDirt", "plantable": False,
                 "crop": "24", "ripe": False, "watered": False},
            ],
        },
        "farm": {"weeds": 3, "stones": 1, "twigs": 1, "trees": 0, "hoeDirt": 3, "crops": 2},
    }

    def test_from_observe_uses_per_tile_truth(self):
        brief = P.Brief.from_observe(self.SNAPSHOT)
        self.assertTrue(brief.tiles_present)
        self.assertEqual(brief.location, "Farm")
        self.assertTrue(brief.is_farm)
        self.assertEqual(brief.day_key, (1, "spring", 5))
        self.assertEqual(brief.counts["weeds"], 1)
        self.assertEqual(brief.counts["stones"], 1)
        self.assertEqual(brief.counts["twigs"], 1)
        self.assertEqual(brief.counts["blockers"], 3)
        self.assertEqual(brief.counts["dirt"], 3)
        self.assertEqual(brief.counts["plantable"], 1)
        self.assertEqual(brief.counts["crops"], 2)
        self.assertEqual(brief.counts["ripe"], 1)
        self.assertEqual(brief.counts["unwatered_crops"], 1)
        self.assertEqual(brief.counts["wet_crops"], 1)
        self.assertEqual(brief.counts["tillable"], 3)

    def test_from_observe_reads_seeds_and_anchors(self):
        brief = P.Brief.from_observe(self.SNAPSHOT)
        self.assertEqual(brief.seed_ids, ("472",))
        self.assertEqual(brief.seed_count, 15)
        self.assertTrue(brief.has_seeds)
        self.assertEqual(brief.inventory_size, 2)
        self.assertIn("farm", brief.anchors)
        self.assertIn("farmhouse_door", brief.anchors)
        self.assertTrue(set(P.allowed_area_hints(brief)) >= {"player", "current_location", "farmhouse_door"})

    def test_summary_snapshot_falls_back_to_farm_counts(self):
        """summary 快照没有 tiles[]：退回 farm 段整场计数，并标记粒度为粗。"""
        snapshot = dict(self.SNAPSHOT)
        snapshot["location"] = {"name": "Farm", "isOutdoorFarm": True}
        brief = P.Brief.from_observe(snapshot)
        self.assertFalse(brief.tiles_present)
        self.assertEqual(brief.counts["weeds"], 3)
        self.assertEqual(brief.counts["stones"], 1)
        self.assertEqual(brief.counts["blockers"], 5)
        self.assertEqual(brief.counts["dirt"], 3)

    def test_situation_text_has_no_coordinates_and_is_bounded(self):
        """简报进 prompt：不许有坐标，且 ≤2 KB（§5.5）。"""
        brief = P.Brief.from_observe(self.SNAPSHOT)
        text = brief.situation_text()
        self.assertIsNone(P.find_coordinate_like(text), text)
        self.assertLessEqual(len(text), P.PROMPT_BRIEF_MAX_CHARS)
        self.assertIn("Farm", text)

    def test_brief_carries_failure_context_for_recovery(self):
        brief = P.Brief.from_observe(self.SNAPSHOT, consecutive_failures=2, last_failure="vetoed:no_seed")
        self.assertEqual(brief.consecutive_failures, 2)
        self.assertIn("vetoed:no_seed", brief.situation_text())

    def test_build_messages_is_two_roles_and_lists_boundary(self):
        brief = make_brief()
        messages = P.build_messages(brief, boundary=P.BOUNDARY_NEW_DAY, problems=["task[0]: unknown_anchor:'x'"])
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("new_day", messages[1]["content"])
        self.assertIn("unknown_anchor", messages[1]["content"])

    def test_brief_does_not_expose_player_tile(self):
        """简报里刻意没有玩家坐标（放了就等于给 LLM 示范"坐标可以出现"）。"""
        brief = P.Brief.from_observe(self.SNAPSHOT)
        for name in ("tile", "x", "y", "pos"):
            self.assertFalse(hasattr(brief, name), name)


# --------------------------------------------------------- CLI（默认关闭开关）
class PlanCommandCliTests(unittest.TestCase):
    """`python -m agentfarm plan` 的开关语义：**默认不碰大模型**。

    用户 m01184 要求"大模型开始介入的时候告诉我一下"，所以 CLI 侧 `--boundary-llm`
    默认 False；这里连"默认实现有没有被调用"都用计数替身盯着。
    """

    def test_parser_defaults_llm_off(self):
        from agentfarm import __main__ as M

        args = M.build_parser().parse_args(["plan"])
        self.assertFalse(args.boundary_llm)
        self.assertIs(args.func, M.cmd_plan)
        self.assertIsNone(args.boundary)
        self.assertTrue(M.build_parser().parse_args(["plan", "--boundary-llm"]).boundary_llm)

    def _run_plan(self, argv):
        import contextlib
        import io
        from unittest import mock

        from agentfarm import __main__ as M

        snapshot = BriefTests.SNAPSHOT

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def observe(self, detail="summary", timeout=None):
                return snapshot

        calls = []

        def fake_default_chat(messages, **kwargs):
            calls.append(messages)
            return valid_payload()

        buf = io.StringIO()
        with mock.patch.object(M, "BridgeClient", FakeClient), \
                mock.patch.object(P, "default_llm_chat", fake_default_chat), \
                contextlib.redirect_stdout(buf):
            code = M.main(argv)
        return code, buf.getvalue(), calls

    def test_plan_without_switch_never_calls_llm_even_on_boundary(self):
        code, out, calls = self._run_plan(["plan", "--boundary", "new_day"])
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])                       # 关着开关 ⇒ 默认 seam 一次都不许被调
        self.assertIn(P.SOURCE_DETERMINISTIC_FALLBACK, out)
        self.assertIn("默认关闭", out)
        # 降级到纯代码策略仍然给出可执行意图；顺序上"浇水优先"（用户 m01770/m01774：
        # 作物当天不浇就补不回来，而清障/开垦哪天都能做），所以第一条就是 water_area。
        self.assertIn("water_area", out)
        self.assertIn("tiles.unwatered_crops", out)       # 且 area 只用观测真值引用，绝无格坐标

    def test_plan_with_switch_calls_seam_once(self):
        code, out, calls = self._run_plan(["plan", "--boundary", "new_day", "--boundary-llm"])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn(P.SOURCE_LLM, out)


class FarmAreasTests(unittest.TestCase):
    """`farm_areas`：让"从快照建简报"的调用方也能把具名田区喂给模型（演练/CLI 与长跑同口径）。"""

    @staticmethod
    def _outdoor_obs() -> dict:
        tiles = []
        tillable = []
        for x in range(40, 60):
            for y in range(10, 30):
                tiles.append({"tile": [x, y], "kind": "weed", "standable": True})
                tillable.append([x, y])
        return {
            "hasSaveLoaded": True,
            "clock": {"year": 1, "season": "spring", "day": 9, "timeOfDay": 1110},
            "player": {"stamina": 270, "maxStamina": 270, "tile": [50, 20], "money": 14,
                       "inventory": [{"slot": 0, "id": "472", "name": "Parsnip Seeds", "stack": 1}]},
            "location": {"name": "Farm", "isOutdoorFarm": True, "tiles": tiles, "tillable": tillable},
        }

    def test_farm_areas_lists_named_zones_on_outdoor_farm(self):
        obs = self._outdoor_obs()
        names, lines = P.farm_areas(obs, split=2)
        self.assertEqual(set(names), {"field_nw", "field_ne", "field_sw", "field_se"})
        self.assertTrue(all("田区" in line for line in lines), lines)

        brief = P.Brief.from_observe(obs, areas=names, area_lines=lines)
        self.assertIn("field_nw", P.allowed_area_hints(brief))
        text = brief.situation_text()
        self.assertIn("field_nw", text)                 # 简报里真的写了田区名和它的活
        self.assertIn("money=14", text)
        self.assertIn("time_of_day=1110", text)
        # 系统提示词的 `__AREAS__` 占位必须换成真田区名（模型才可能合法引用它）
        messages = P.build_messages(brief, boundary=P.BOUNDARY_NEW_DAY)
        self.assertIn("field_nw", messages[0]["content"])
        self.assertNotIn("__AREAS__", messages[0]["content"])

    def test_farm_areas_empty_for_indoor_snapshot(self):
        obs = {"hasSaveLoaded": True,
               "location": {"name": "FarmHouse", "isOutdoorFarm": False,
                            "tiles": [{"tile": [3, 3], "kind": "dirt"}]},
               "player": {"stamina": 100, "tile": [3, 3]}}
        self.assertEqual(P.farm_areas(obs), ((), ()))
        brief = P.Brief.from_observe(obs)
        self.assertEqual(brief.areas, ())
        # 没有具名田区时提示词必须**明说**（否则模型会瞎编田区名，白烧一次重问）
        messages = P.build_messages(brief, boundary=P.BOUNDARY_NEW_DAY)
        self.assertIn("本轮没有具名田区", messages[0]["content"])


class LlmTraceTests(unittest.TestCase):
    """【task-56 决策留痕】每次**真实** LLM 调用落一行 JSON，`decision` 上带路径 + 哈希。

    用户今天问的原话是"每次决策有没有记录和反馈机制"⇒ 留痕只负责**如实记录**：
    它绝不能改变决策逻辑，写盘失败也必须照常返回决策（只把原因挂在 `llm_trace_error`）。
    """

    def boundary_state(self) -> P.PlannerState:
        return P.PlannerState(day_key=(1, "spring", 5), last_task_kind="till_area", last_seen_failures=0)

    def test_real_call_writes_one_line_with_every_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run-llm.jsonl"
            chat = FakeChat(LlmResult(content=valid_payload(), model="deepseek-flash",
                                      finish_reason="stop",
                                      usage=Usage(prompt_tokens=11, completion_tokens=22), elapsed_ms=7))
            planner = P.BoundaryPlanner(llm_chat=chat, max_llm_attempts=1, llm_trace_path=path)
            decision = planner.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6)))

            self.assertEqual(decision.source, P.SOURCE_LLM)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            rec = json.loads(lines[0])
            # 卡面点名的字段一个不少、一个不多（多出来的都是没被要求的臆造）
            self.assertEqual(set(rec), {
                "t", "boundary", "model", "prompt_chars", "prompt", "prompt_truncated",
                "raw", "usage", "finish_reason", "duration_ms", "attempts",
                "rejected", "accepted", "fallback",
            })
            self.assertEqual(rec["boundary"], P.BOUNDARY_NEW_DAY)
            self.assertEqual(rec["model"], "deepseek-flash")
            self.assertEqual(rec["attempts"], 1)
            self.assertEqual([i["task"] for i in rec["accepted"]], ["till_area"])
            self.assertIs(rec["fallback"], False)             # 没降级 ⇒ False（不是空串）
            self.assertEqual(rec["rejected"], [])
            self.assertEqual(rec["raw"], valid_payload())
            self.assertEqual(rec["finish_reason"], "stop")
            # 卡面口径 `{prompt,completion,total}`
            self.assertEqual(rec["usage"], {"prompt": 11, "completion": 22, "total": 33})
            self.assertEqual(rec["prompt"], chat.calls[0][1]["content"])
            self.assertEqual(rec["prompt_chars"], len(rec["prompt"]))
            self.assertEqual(rec["prompt_truncated"], False)
            self.assertIsInstance(rec["t"], float)
            self.assertGreaterEqual(rec["duration_ms"], 0)
            # decision 上的两个新字段：路径 + **该行**的 sha256 前 12 位
            self.assertEqual(decision.llm_trace, str(path))
            self.assertEqual(decision.llm_trace_hash,
                             hashlib.sha256(lines[0].encode("utf-8")).hexdigest()[:12])
            self.assertEqual(decision.llm_trace_error, "")

    def test_over_8000_chars_prompt_is_truncated_and_flagged(self):
        rec = P.BoundaryPlanner(llm_chat=FakeChat(""), llm_trace_path=None)._trace_record(
            P.BOUNDARY_NEW_DAY, "长" * (P.LLM_TRACE_MAX_PROMPT_CHARS + 500), 2,
            accepted_intents=(), rejected=["x"])
        self.assertEqual(len(rec["prompt"]), P.LLM_TRACE_MAX_PROMPT_CHARS)
        self.assertEqual(rec["prompt_truncated"], True)
        self.assertEqual(rec["prompt_chars"], P.LLM_TRACE_MAX_PROMPT_CHARS + 500)
        self.assertEqual(rec["attempts"], 2)
        self.assertEqual(rec["accepted"], [])
        self.assertEqual(rec["rejected"], ["x"])
        # 没拿到 LlmResult（纯字符串 seam）⇒ 用量写 null，绝不臆造 0
        self.assertEqual(rec["usage"], {"prompt": None, "completion": None, "total": None})

    def test_trace_write_failure_never_changes_the_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            planner = P.BoundaryPlanner(llm_chat=FakeChat(valid_payload()), max_llm_attempts=1,
                                        llm_trace_path=Path(tmp))   # 指向一个目录 ⇒ 写盘必失败
            decision = planner.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6)))
            self.assertEqual(decision.source, P.SOURCE_LLM)          # 决策照常
            self.assertEqual(decision.intents[0].task, "till_area")
            self.assertTrue(decision.llm_trace_error)                 # 但失败如实带出来
            self.assertEqual(decision.llm_trace_hash, "")

    def test_llm_error_still_leaves_a_trace_line(self):
        """**失败的那次调用也要留痕**：否则"为什么降级"只能靠猜。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run-llm.jsonl"
            planner = P.BoundaryPlanner(llm_chat=FakeChat(LlmError("超时", status="network")),
                                        max_llm_attempts=1, llm_trace_path=path)
            decision = planner.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6)))
            self.assertEqual(decision.source, P.SOURCE_DETERMINISTIC_FALLBACK)
            rec = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[0])
            self.assertEqual(rec["accepted"], [])
            # 降级时 `fallback` 是"是 + 原因"的可读串（没降级时是 False）
            self.assertIn("deterministic_fallback", rec["fallback"])
            self.assertIn("llm_error:network", rec["fallback"])
            self.assertEqual(rec["raw"], "")
            self.assertTrue(rec["rejected"][0].startswith("llm_error:network"))

    def test_no_trace_when_no_real_call(self):
        """确定性决策（无边界 / 关掉 LLM）一行都不许写。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run-llm.jsonl"
            # ①常规区间：连 seam 都不碰
            steady = P.PlannerState(day_key=(1, "spring", 5), last_task_kind="till_area",
                                    last_seen_failures=0)
            planner = P.BoundaryPlanner(llm_chat=FakeChat(valid_payload()), llm_trace_path=path)
            self.assertEqual(planner.decide(steady, till_brief(day_key=(1, "spring", 5))).source,
                             P.SOURCE_DETERMINISTIC)
            # ②边界 + 开关关掉：`llm_disabled`，同样不碰网络、不留痕
            off = P.BoundaryPlanner(llm_chat=FakeChat(valid_payload()), llm_enabled=False,
                                    llm_trace_path=path)
            self.assertEqual(off.decide(self.boundary_state(), till_brief(day_key=(1, "spring", 6))).source,
                             P.SOURCE_DETERMINISTIC_FALLBACK)
            self.assertEqual(off.llm_chat.call_count, 0)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
