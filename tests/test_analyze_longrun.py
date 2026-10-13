#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""`tools/analyze-longrun.py` 的回归测试（task-25）。

判据分三层：
  1. 真实账本：run2 必须自动重现 5 项验收事实；run1（缺 day_end/finish）必须不崩且如实标注"无法判定"。
  2. 自造账本：全绿的一天不能报问题；cancel→fallback 与"leftover 却自称 verified"必须被点名。
  3. CLI 契约：不可读/空账本退出码 2；`--json` 能产出可解析 JSON（含 mapping）。

跑法：python -m unittest discover -s tests
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "analyze-longrun.py")
BRAIN_LONG_RUN = os.path.join(ROOT, "brain", "agentfarm", "longrun.py")

_spec = importlib.util.spec_from_file_location("analyze_longrun", TOOL)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

RUN1 = os.path.join(ROOT, "logs", "longrun-3day-llm-run1.jsonl")
RUN2 = os.path.join(ROOT, "logs", "longrun-3day-llm-run2.jsonl")
RUN5 = os.path.join(ROOT, "logs", "longrun-3day-llm-run5.jsonl")
GREEN = os.path.join(ROOT, "scratch", "_ledger_green.jsonl")
FALLBACK = os.path.join(ROOT, "scratch", "_ledger_fallback.jsonl")
WASH = os.path.join(ROOT, "scratch", "_ledger_leftover_verified.jsonl")


def report_for(path, days=3, top=50):
    rows, bad_lines = mod.load_journal(path)
    args = mod.parse_args(["--journal", path, "--days", str(days), "--top", str(top)])
    return mod.build_report(rows, path, args, bad_lines)


def subjects(items):
    return [item["subject"] for item in items]


class TestRealRun2(unittest.TestCase):
    """run2 是 task-25 的验收账本：5 项事实必须自动重现。"""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(RUN2):
            raise unittest.SkipTest(f"缺少账本 {RUN2}")
        cls.rep = report_for(RUN2)

    def test_acceptance_five_facts(self):
        rep = self.rep
        self.assertEqual(rep["verified_days"], 0, "run2 应为 0 天 VERIFIED")
        self.assertEqual(rep["day_end_count"], 2, "run2 应有 2 条 day_end")
        ended = [d["ended_by"] for d in rep["days"] if d["ended_by"]]
        self.assertEqual(ended, ["sleep_failed", "sleep_failed"], f"两天都该是 sleep_failed，实际 {ended}")
        self.assertEqual(rep["failed_steps_total"], 14, "failed_steps 合计应为 14")
        self.assertEqual(len(rep["no_day_progress"]), 1, "应恰有 1 次 no_day_progress")
        self.assertGreaterEqual(rep["events"].get("blocked", 0), 1, "应存在 blocked（草格无效挥动）")
        self.assertEqual(rep["blocked_grass"], 12, "理由含 grass 的 blocked 应为 12 条")
        self.assertEqual(rep["sleep_failed"], 2, "应有 2 次睡觉失败")

    def test_four_categories_carry_evidence_lines(self):
        rep = self.rep
        for key in ("missed", "wasted", "ineffective", "sleep"):
            self.assertGreater(rep["categories_total"][key], 0, f"{key} 类应至少 1 条")
            self.assertTrue(
                any(item["line"] is not None for item in rep["categories"][key]),
                f"{key} 类应至少一条带证据行号",
            )
        wet = subjects(rep["categories"]["wasted"])
        self.assertTrue(any(s.startswith("wasted:whitewash") for s in wet), "应点名'失败却 VERIFIED'的洗白")
        self.assertIn("ineffective:grass", subjects(rep["categories"]["ineffective"]))
        advice_lines = [ln for adv in rep["advice"] for ln in adv["lines"]]
        self.assertTrue(advice_lines, "建议必须带证据行号")

    def test_undecidable_states_limits(self):
        blob = "\n".join(self.rep["undecidable"])
        self.assertIn("没有逐格 before/after", blob)
        self.assertIn("isInBed", blob)


class TestRealRun1(unittest.TestCase):
    """run1 没有 day_end/finish：不许崩，且必须如实说'无法判定'。"""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(RUN1):
            raise unittest.SkipTest(f"缺少账本 {RUN1}")
        cls.rep = report_for(RUN1)

    def test_missing_day_level_fields_survive(self):
        rep = self.rep
        self.assertEqual(rep["day_end_count"], 0)
        self.assertEqual(rep["verified_days"], 0)
        self.assertIsNone(rep["finish"])
        self.assertTrue(all(d["ended_by"] is None for d in rep["days"]))
        for key in ("missed", "wasted", "ineffective", "sleep"):
            self.assertIn(key, rep["categories_total"])

    def test_undecidable_names_missing_records(self):
        blob = "\n".join(self.rep["undecidable"])
        self.assertIn("没有任何 day_end", blob)
        self.assertIn("没有 finish", blob)

    def test_day_line_marks_unknown(self):
        text = mod.render_text(self.rep, 5)
        self.assertIn("<无 day_end>", text)
        self.assertIn("finish: <缺失>", text)


class TestSyntheticLedgers(unittest.TestCase):
    def test_green_day_reports_nothing(self):
        rep = report_for(GREEN, days=1)
        self.assertEqual(rep["verified_days"], 1)
        self.assertEqual(rep["failed_steps_total"], 0)
        self.assertEqual(
            {k: v for k, v in rep["categories_total"].items()
             if k in ("missed", "wasted", "ineffective", "sleep")},
            {"missed": 0, "wasted": 0, "ineffective": 0, "sleep": 0},
        )
        # task-30 新增两类：干净账本也必须都是 0
        self.assertEqual(rep["categories_total"]["manual"], 0)
        self.assertEqual(rep["categories_total"]["environment"], 0)
        self.assertEqual(rep["manual_intervention"]["total"], 0)
        self.assertTrue(rep["advice"], "干净账本也要给一句结论")

    def test_fallback_ledger_is_flagged(self):
        rep = report_for(FALLBACK, days=1)
        cancels = [s for s in subjects(rep["categories"]["missed"]) if s.startswith("missed:cancel")]
        self.assertEqual(len(cancels), 2, "两个 cancel 都应被点名")
        self.assertIn("missed:stage_no_target", subjects(rep["categories"]["missed"]))
        self.assertEqual(rep["categories_total"]["wasted"], 1)
        self.assertIn("ineffective:till", subjects(rep["categories"]["ineffective"]))
        self.assertIn("sleep:failed", subjects(rep["categories"]["sleep"]))
        self.assertIn("sleep:early", subjects(rep["categories"]["sleep"]))
        self.assertTrue(
            any("max_tokens" in adv["text"] for adv in rep["advice"]), "fallback 应出现在建议里"
        )

    def test_leftover_but_verified_is_flagged(self):
        rep = report_for(WASH, days=1)
        wet = subjects(rep["categories"]["wasted"])
        self.assertTrue(any(s.startswith("wasted:whitewash") for s in wet), "failed>0 却 verified 要被抓")
        self.assertTrue(any(s.startswith("wasted:leftover") for s in wet), "ok>0 但 leftover>0 要被抓")
        self.assertEqual(rep["verified_days"], 1, "账本自己声称 verified，工具照读（但要点名矛盾）")
        self.assertIn("ineffective:grass", subjects(rep["categories"]["ineffective"]))
        self.assertIn("missed:check:no_hard_failures", subjects(rep["categories"]["missed"]))
        self.assertIsNotNone(rep["finish"])


MODAL_DAY = [1, "spring", 12]


def write_ledger(tmp, name, events):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return path


def day_start(day):
    return {"event": "day_start", "t": 1.0, "day": day, "timeOfDay": 610, "stamina": 270, "money": 100}


def final(day):
    return {"day": day, "timeOfDay": 1200, "location": "Farm", "stamina": 200, "money": 100,
            "isInBed": False, "crops": 0, "unwatered_crops": 0, "ripe": 0, "tillable": 0,
            "waterLeft": 10, "seeds": []}


def modal_ledger_events():
    """task-11/22 的新事件全来一遍：模态红 + 模态信息 + env_fail 未补做 + inconclusive_fail。"""
    day = MODAL_DAY
    return [
        day_start(day),
        {"event": "decision", "t": 2.0, "day": day, "source": "llm", "llm": True,
         "intents": [{"task": "clear_area", "area_hint": "field_ne", "reason": "清障"}],
         "problems": [], "fallback": None, "zone": "field_ne"},
        {"event": "modal_wait_start", "t": 3.0, "menu": "SaveGameMenu", "limit_s": 120},
        {"event": "modal_gone", "t": 4.0, "menu": "SaveGameMenu", "waited_s": 12.5},
        {"event": "modal_dismissed", "t": 5.0, "kind": "question", "menu": "DialogueBox",
         "menuText": "要做什么？", "receipt": {"ok": True}},
        {"event": "env_fail", "t": 6.0, "stage": "clear_area", "zone": "field_ne", "tiles": 3,
         "statuses": ["busy"], "note": "环境挡路（渐黑/模态/没存档）⇒ 不算干不动"},
        {"event": "inconclusive_fail", "t": 7.0, "stage": "till_area", "zone": "field_ne", "tiles": 2,
         "statuses": ["timeout"], "note": "不封格，但占本日尝试配额"},
        {"event": "levelup_profession_pending", "t": 8.0, "menu": "LevelUpMenu", "ids": [0, 1],
         "menuText": "选择职业"},
        {"event": "modal_blocked", "t": 9.0, "menu": "LevelUpMenu",
         "reason": "职业选择弹窗（候选 [0, 1]）等人处理"},
        {"event": "outcome", "t": 9.5, "kind": "clear_area", "terminal": "needs_review",
         "postcondition_met": False,
         "reason": "作业区 field_ne；目标 3 步：做成 0、跳过 0、失败 0；后置条件未成立（还剩 3 格）",
         "detail": []},
        {"event": "outcome", "t": 9.6, "kind": "till_area", "terminal": "needs_review",
         "postcondition_met": False,
         "reason": "作业区 field_ne；目标 2 步：做成 0、跳过 0、失败 0；后置条件未成立（还剩 2 格）",
         "detail": []},
        {"event": "day_end", "t": 10.0, "day": day, "day_text": "1年 spring 12日",
         "ended_by": "blocked_modal", "ended_reason": "职业选择弹窗（候选 [0, 1]）等人处理",
         "verified": False,
         "checks": {"slept_by_us": False, "no_blocking_modal": False, "no_hard_failures": True,
                    "crops_watered": True, "day_justified": False},
         "stages": [
             {"stage": "clear_area", "tiles": 3, "ok": 0, "skipped": 0, "failed": 0, "proven_inert": 0,
              "env_block": 3, "inconclusive": 0, "stopped": "", "leftover": 3},
             {"stage": "till_area", "tiles": 2, "ok": 0, "skipped": 0, "failed": 0, "proven_inert": 0,
              "env_block": 0, "inconclusive": 2, "stopped": "", "leftover": 2},
         ],
         "outcomes": [], "ok_steps": 0, "skipped_steps": 0, "failed_steps": 0, "notes": [],
         "final": final(day)},
        {"event": "finish", "t": 11.0, "code": 1, "verified_streak": 0, "actions": 5, "minutes": 0.2},
    ]


class TestModalAndEnvironmentEvents(unittest.TestCase):
    """task-30：模态 / 环境挡路 / 没拿到结论 的归类与计数（口径必须与 verify-run3.py 不冲突）。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.path = write_ledger(cls._tmp.name, "modal.jsonl", modal_ledger_events())
        cls.rep = report_for(cls.path, days=1)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_modal_red_events_are_flagged(self):
        rep = self.rep
        man = subjects(rep["categories"]["manual"])
        self.assertIn("manual:levelup_profession_pending", man)
        self.assertIn("manual:modal_blocked", man)
        self.assertIn("manual:ended_by_blocked_modal", man)
        mi = rep["manual_intervention"]
        self.assertEqual(mi["by_event"], {"levelup_profession_pending": 1, "modal_blocked": 1})
        self.assertGreaterEqual(mi["total"], 3)
        self.assertIn("manual:levelup_profession_pending", mi["red_subjects"])
        self.assertTrue(mi["red_lines"], "红类必须带证据行号")

    def test_modal_info_events_count_interrupts(self):
        rep = self.rep
        mi = rep["manual_intervention"]
        self.assertEqual(mi["modal_events"]["modal_wait_start"], 1)
        self.assertEqual(mi["modal_events"]["modal_gone"], 1)
        self.assertEqual(mi["modal_events"]["modal_switched"], 0)
        self.assertEqual(mi["modal_events"]["modal_dismissed"], 1)
        self.assertEqual(mi["modal_interrupts_total"], 2, "wait_start + dismissed 各算一次打断")
        self.assertEqual(len(mi["modal_interrupt_lines"]), 2)
        self.assertEqual(rep["days"][0]["modal_interrupts"], 2)

    def test_blocked_modal_day_is_never_a_pass(self):
        rep = self.rep
        self.assertEqual(rep["verified_days"], 0)
        self.assertEqual(rep["days"][0]["ended_by"], "blocked_modal")
        # no_blocking_modal=false 同时必须落进"该做没做"（缺失/false 都不等于通过）
        self.assertIn("missed:check:no_blocking_modal", subjects(rep["categories"]["missed"]))

    def test_env_and_inconclusive_accounting(self):
        rep = self.rep
        env = rep["env_inconclusive"]
        self.assertEqual(env["env_fail_events"], 1)
        self.assertEqual(env["env_fail_tiles"], 3)
        self.assertEqual(env["env_fail_unfinished_tiles"], 3, "该阶段最终没做成 ⇒ 这些格并进'该做没做'")
        self.assertEqual(env["inconclusive_events"], 1)
        self.assertEqual(env["inconclusive_tiles"], 2)
        self.assertEqual(env["statuses"], ["busy", "timeout"])
        subs = subjects(rep["categories"]["environment"])
        self.assertIn("environment:env_fail:unfinished", subs)
        self.assertIn("environment:inconclusive:unfinished", subs)
        self.assertEqual(rep["categories_total"]["environment"], 2,
                         "env_fail 一条信息项 + inconclusive 一条（未做成的那条算进'1 该做没做'）")
        self.assertIn("missed:env_fail", subjects(rep["categories"]["missed"]))
        # 旧四类计数键不能消失
        for key in ("missed", "wasted", "ineffective", "sleep", "manual", "environment"):
            self.assertIn(key, rep["categories_total"])

    def test_advice_and_render_expose_new_classes(self):
        rep = self.rep
        texts = [adv["text"] for adv in rep["advice"]]
        blob = " ".join(texts)
        self.assertIn("必须人工介入（红）", blob)
        self.assertIn("模态", blob)
        self.assertIn("环境挡路", blob)
        self.assertIn("配额", blob)
        text = mod.render_text(rep, 5)
        self.assertIn("【0 必须人工介入（红）】", text)
        self.assertIn("【5 环境挡路 / 没拿到结论】", text)
        self.assertIn("模态: 打断 2 次", text)
        self.assertIn("no_blocking_modal=False", text.replace(" ", ""))

    def test_json_gains_keys_without_renaming_old_ones(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = mod.main(["--journal", self.path, "--days", "1", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertIn("manual_intervention", payload)
        self.assertIn("env_inconclusive", payload)
        for key in ("manual", "missed", "wasted", "ineffective", "sleep", "environment"):
            self.assertIn(key, payload["categories"])
            self.assertIn(key, payload["categories_total"])
        self.assertEqual(payload["env_inconclusive"]["env_fail_tiles"], 3)

    def test_check_false_without_blocked_modal_is_still_red(self):
        """ended_by 不是 blocked_modal，但 checks.no_blocking_modal=false ⇒ 仍必须人工介入。"""
        day = [1, "spring", 13]
        events = [
            day_start(day),
            {"event": "sleep", "t": 5.0, "ok": True, "code": "ok", "reason": "",
             "before": {"day": day, "timeOfDay": 2200, "stamina": 8},
             "after": {"day": [1, "spring", 14], "timeOfDay": 600, "stamina": 270}},
            {"event": "day_end", "t": 6.0, "day": day, "day_text": "1年 spring 13日",
             "ended_by": "sleep", "ended_reason": "夜间", "verified": False,
             "checks": {"slept_by_us": True, "no_blocking_modal": False, "no_hard_failures": True,
                        "crops_watered": True, "day_justified": True},
             "stages": [], "outcomes": [], "ok_steps": 0, "skipped_steps": 0, "failed_steps": 0,
             "notes": [], "final": final(day)},
            {"event": "finish", "t": 7.0, "code": 1, "verified_streak": 0, "actions": 1, "minutes": 0.1},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            rep = report_for(write_ledger(tmp, "check.jsonl", events), days=1)
        man = subjects(rep["categories"]["manual"])
        self.assertIn("manual:check:no_blocking_modal", man)
        self.assertNotIn("manual:ended_by_blocked_modal", man)
        self.assertEqual(rep["verified_days"], 0)

    def test_env_fail_recovered_is_pure_info(self):
        """env_fail 之后该阶段最终做成了 ⇒ 只报信息项，不进'该做没做'。"""
        day = [1, "spring", 14]
        events = [
            day_start(day),
            {"event": "env_fail", "t": 2.0, "stage": "clear_area", "zone": "field_ne", "tiles": 2,
             "statuses": ["world_fading"], "note": "环境挡路"},
            {"event": "outcome", "t": 3.0, "kind": "clear_area", "terminal": "VERIFIED",
             "postcondition_met": True,
             "reason": "作业区 field_ne；目标 2 步：做成 2、跳过 0、失败 0；后置条件成立", "detail": []},
            {"event": "day_end", "t": 4.0, "day": day, "day_text": "1年 spring 14日",
             "ended_by": "sleep", "ended_reason": "夜间", "verified": True,
             "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                        "crops_watered": True, "day_justified": True},
             "stages": [{"stage": "clear_area", "tiles": 2, "ok": 2, "skipped": 0, "failed": 0,
                         "proven_inert": 0, "env_block": 2, "inconclusive": 0, "stopped": "",
                         "leftover": 0}],
             "outcomes": [], "ok_steps": 2, "skipped_steps": 0, "failed_steps": 0, "notes": [],
             "final": final(day)},
            {"event": "finish", "t": 5.0, "code": 0, "verified_streak": 1, "actions": 2, "minutes": 0.3},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            rep = report_for(write_ledger(tmp, "env_ok.jsonl", events), days=1)
        env = rep["env_inconclusive"]
        self.assertEqual(env["env_fail_events"], 1)
        self.assertEqual(env["env_fail_unfinished_tiles"], 0)
        subs = subjects(rep["categories"]["environment"])
        self.assertIn("environment:env_fail", subs)
        self.assertNotIn("environment:env_fail:unfinished", subs)
        self.assertNotIn("missed:env_fail", subjects(rep["categories"]["missed"]))
        self.assertEqual(rep["categories_total"]["manual"], 0)
        self.assertEqual(rep["verified_days"], 1)


class TestCliContract(unittest.TestCase):
    def test_unreadable_and_empty_journal_exit_2(self):
        self.assertEqual(mod.main(["--journal", os.path.join(ROOT, "logs", "_no_such.jsonl")]), 2)
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "empty.jsonl")
            with open(empty, "w", encoding="utf-8"):
                pass
            self.assertEqual(mod.main(["--journal", empty]), 2)

    def test_bad_lines_are_tolerated_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mixed.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"event": "day_start", "t": 1.0, "day": [1, "spring", 1]}\n')
                fh.write("{ 这不是 json\n")
                fh.write('["不是对象"]\n')
                fh.write('{"event": "finish", "code": 0}\n')
            rep = report_for(path, days=1)
            self.assertEqual(rep["parsed_events"], 2)
            self.assertEqual(len(rep["bad_lines"]), 2)
            self.assertEqual(rep["lines"], 4)

    def test_json_mode_is_parseable(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = mod.main(["--journal", GREEN, "--days", "1", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["verified_days"], 1)
        self.assertIn("mapping", payload)
        self.assertIn("categories", payload)
        self.assertNotIn("_sessions", payload)
        self.assertIn("blocked", payload["mapping"])
        # task-30：新增键只增不改（旧四类键名必须还在）
        self.assertIn("manual_intervention", payload)
        self.assertIn("env_inconclusive", payload)
        self.assertIn("manual", payload["categories"])
        self.assertIn("environment", payload["categories"])
        self.assertIn("missed", payload["categories"])
        # task-30 第二批：新键（自旋计数 / t 回退）
        self.assertIn("env_spin_events", payload["env_inconclusive"])
        self.assertIn("env_blocked_total", payload["env_inconclusive"])
        self.assertIn("t_regressions", payload)
        # 彩排实测：decision 只有 source/llm/boundary/truncated，顶部统计单独成块
        self.assertIn("decision_counts", payload)
        self.assertIn("total", payload["decision_counts"])


def integrity_ledger(*, extra_events=(), day_end_overrides=None, finish=None):
    """task-30 第二批：造一天"干净但可逐项污染"的账本（默认：睡觉跨日 +1 天、0 阶段但有无活可做的理由）。"""
    day = MODAL_DAY
    nxt = [day[0], day[1], day[2] + 1]
    end = {
        "event": "day_end", "t": 9.0, "day": day, "day_text": "1年 spring 12日",
        "ended_by": "sleep", "ended_reason": "night", "verified": True,
        "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                   "crops_watered": True, "day_justified": True},
        "stages": [], "outcomes": [], "ok_steps": 0, "skipped_steps": 0, "failed_steps": 0,
        "notes": [], "final": final(nxt),
    }
    if day_end_overrides:
        end.update(day_end_overrides)
    events = [day_start(day)]
    events.extend(extra_events)
    events.append(end)
    if finish is not None:
        events.append(finish)
    return events


class TestIntegrityAndSpinAccounting(unittest.TestCase):
    """task-30 第二批：env_spin_capped 计数、阶段账目自洽、跨日恰好 +1 天、0 步 VERIFIED、
    浇水矛盾、finish 自述 —— 口径必须与 `tools/verify-run3.py` 一致。"""

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def test_env_spin_capped_is_info_but_counted(self):
        rep = self._report(integrity_ledger(extra_events=[
            {"event": "env_spin_capped", "t": 5.0, "tile": [61, 26], "streak": 3, "limit": 2,
             "note": "同一格被环境挡住超过上限 ⇒ 从下一次起按'没结论'占配额"},
        ]), "spin.jsonl")
        env = rep["env_inconclusive"]
        self.assertEqual(env["env_spin_events"], 1)
        self.assertEqual(env["env_spin_tiles"], [[61, 26]])
        self.assertEqual(env["env_blocked_total"], 1, "自旋也计入'当天被环境挡住'的次数")
        self.assertIn("environment:env_spin_capped", subjects(rep["categories"]["environment"]))
        self.assertTrue(any("自旋到上限" in a["text"] for a in rep["advice"]))
        # 信息项：不能因为它多算成"该做没做"
        self.assertNotIn("missed:env_spin_capped", subjects(rep["categories"]["missed"]))

    def test_stage_ledger_must_balance_with_env_and_inconclusive(self):
        bad = self._report(integrity_ledger(day_end_overrides={
            "verified": False, "ended_reason": "hard", "failed_steps": 5,
            "stages": [{"stage": "clear_area", "tiles": 5, "ok": 0, "skipped": 0, "failed": 1,
                        "proven_inert": 0, "env_block": 0, "inconclusive": 0, "stopped": "",
                        "leftover": 4}],
        }), "account_bad.jsonl")
        self.assertIn("missed:stage_account", subjects(bad["categories"]["missed"]))
        ok = self._report(integrity_ledger(day_end_overrides={
            "verified": False, "ended_reason": "hard", "failed_steps": 3,
            "stages": [{"stage": "clear_area", "tiles": 5, "ok": 0, "skipped": 0, "failed": 5,
                        "proven_inert": 0, "env_block": 2, "inconclusive": 0, "stopped": "",
                        "leftover": 2}],
        }), "account_ok.jsonl")
        self.assertNotIn("missed:stage_account", subjects(ok["categories"]["missed"]),
                         "差额 5-3=2 被 env_block=2 解释完 ⇒ 不算账目不可信")

    def test_cross_day_must_be_exactly_one_day(self):
        # task-38：`final` 是**睡前**快照 ⇒ 它停在当天**不能**证明"没跨日"（旧口径就是这么假报警的）
        stale = self._report(integrity_ledger(day_end_overrides={"final": final(MODAL_DAY)}),
                             "cross_stale_final.jsonl")
        self.assertNotIn("missed:cross_day", subjects(stale["categories"]["missed"]),
                         "没有 day_after 且 final 停在当天 ⇒ 只能【无法判定】，不算'该做没做'")
        # `final` 明确指向另一天（旧账本兜底）但不是 +1 天 ⇒ 仍然报红
        twice = self._report(integrity_ledger(
            day_end_overrides={"final": final([MODAL_DAY[0], MODAL_DAY[1], MODAL_DAY[2] + 2])}),
            "cross_twice.jsonl")
        self.assertIn("missed:cross_day", subjects(twice["categories"]["missed"]))
        good = self._report(integrity_ledger(), "cross_ok.jsonl")
        self.assertNotIn("missed:cross_day", subjects(good["categories"]["missed"]))
        self.assertEqual(good["days"][0]["cross_day_verdict"], "crossed")
        self.assertEqual(good["days"][0]["cross_day_source"], "final")

    def test_zero_step_verified_needs_no_work_excuse(self):
        ok = self._report(integrity_ledger(), "zero_ok.jsonl")
        self.assertNotIn("wasted:verified_without_work", subjects(ok["categories"]["wasted"]),
                         "ended_reason=night ⇒ 属于'无活可做'的豁免")
        bad = self._report(integrity_ledger(day_end_overrides={"ended_reason": "mystery"}),
                           "zero_bad.jsonl")
        self.assertIn("wasted:verified_without_work", subjects(bad["categories"]["wasted"]))
        quiet = self._report(integrity_ledger(extra_events=[
            {"event": "no_intents", "t": 5.0, "reason": "确实找不到可做的活"},
        ]), "zero_no_intents.jsonl")
        self.assertNotIn("wasted:verified_without_work", subjects(quiet["categories"]["wasted"]),
                         "no_intents 事件 = 明确的'无活可做'证据")

    def test_water_contradiction_is_flagged(self):
        rep = self._report(integrity_ledger(day_end_overrides={
            "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                       "crops_watered": True, "day_justified": True, "watered_outdoor": True},
            "final_water": {"dry": 2, "watered": 10},
        }), "water_contradiction.jsonl")
        self.assertIn("wasted:water_contradiction", subjects(rep["categories"]["wasted"]))

    def test_finish_self_report_must_be_coherent(self):
        incoherent = self._report(integrity_ledger(finish={
            "event": "finish", "t": 10.0, "code": 0, "verified_streak": 0,
            "actions": 3, "minutes": 0.1}), "fin_incoherent.jsonl")
        self.assertIn("wasted:finish_incoherent", subjects(incoherent["categories"]["wasted"]))
        vs_days = self._report(integrity_ledger(
            day_end_overrides={"verified": False},
            finish={"event": "finish", "t": 10.0, "code": 0, "verified_streak": 1,
                    "actions": 3, "minutes": 0.1}), "fin_vs_days.jsonl")
        self.assertIn("wasted:finish_vs_days", subjects(vs_days["categories"]["wasted"]))
        self.assertTrue(any("自述与正文对不上" in a["text"] for a in vs_days["advice"]))
        coherent = self._report(integrity_ledger(finish={
            "event": "finish", "t": 10.0, "code": 1, "verified_streak": 0,
            "actions": 3, "minutes": 0.1}), "fin_ok.jsonl")
        self.assertNotIn("wasted:finish_incoherent", subjects(coherent["categories"]["wasted"]))

    def test_t_regression_is_info_only(self):
        rep = self._report(integrity_ledger(extra_events=[
            {"event": "plot", "t": 5.0, "zone": "field_ne", "anchor": [1, 1], "tiles": 1},
            {"event": "plot", "t": 3.0, "zone": "field_ne", "anchor": [1, 1], "tiles": 1},
        ]), "t_regression.jsonl")
        self.assertEqual(len(rep["t_regressions"]), 1)
        self.assertEqual(rep["t_regressions"][0]["t0"], 5.0)
        self.assertEqual(rep["t_regressions"][0]["t1"], 3.0)
        self.assertIn("t 回退", mod.render_text(rep, 10))
        self.assertNotIn("missed:t_regression", subjects(rep["categories"]["missed"]))


class TestDecisionSourceAccounting(unittest.TestCase):
    """彩排实测（`logs\\longrun-rehearsal-0.7.22.jsonl`）：`decision` 只写 source/llm/boundary/truncated
    四键、**没有 token/usage** ⇒ 顶部统计只能给"次数 + 来源 + 边界 + 是否截断"，不能报 token 消耗。"""

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def _decisions(self):
        return [
            {"event": "decision", "t": 1.0, "day": MODAL_DAY, "boundary": "new_day",
             "source": "llm", "llm": True, "intents": [], "problems": [], "fallback": None,
             "truncated": False},
            {"event": "decision", "t": 2.0, "day": MODAL_DAY, "boundary": None,
             "source": "deterministic", "llm": False, "intents": [], "problems": [],
             "fallback": None},
            {"event": "decision", "t": 3.0, "day": MODAL_DAY, "boundary": "task_kind_change",
             "source": "llm", "llm": True, "intents": [], "problems": [], "fallback": None,
             "truncated": True},
        ]

    def test_decision_counts_split_by_source_and_boundary(self):
        rep = self._report(integrity_ledger(extra_events=self._decisions()), "decision.jsonl")
        dc = rep["decision_counts"]
        self.assertEqual(dc["total"], 3)
        self.assertEqual(dc["llm"], 2)
        self.assertEqual(dc["by_source"], {"llm": 2, "deterministic": 1})
        self.assertEqual(dc["by_boundary"], {"new_day": 1, "task_kind_change": 1, "(none)": 1})
        self.assertEqual(len(dc["truncated_lines"]), 1)
        # Lead m02565：两档口径与 tools\verify-run3.py 同名同义
        self.assertEqual(dc["decisions_llm"], 2)
        self.assertEqual(dc["decisions_llm_used"], 2)
        self.assertEqual(dc["decisions_llm_fallback"], 0)
        self.assertEqual(dc["llm_used"], dc["decisions_llm_used"])
        self.assertEqual(dc["llm_fallback_lines"], [])

    def test_render_and_advice_expose_llm_boundary(self):
        rep = self._report(integrity_ledger(extra_events=self._decisions()), "decision.jsonl")
        text = mod.render_text(rep, 50)
        self.assertIn("决策: 3 次（decisions_llm=2，其中模型产出 decisions_llm_used=2，无兜底）", text)
        self.assertIn("truncated=1 行", text)
        self.assertIn("LLM 回答被 max_tokens 截断", " ".join(a["text"] for a in rep["advice"]))

    def test_fallback_is_named_but_not_counted_as_used(self):
        """run2 L17 的形态（Lead m02565）：`llm=true` + `source=deterministic_fallback`
        ⇒ 发起过调用算 1（`decisions_llm`），但**模型产出算 0**（`decisions_llm_used`），
        兜底 1 行必须点名（判据说"LLM 覆盖"只能取 `decisions_llm_used`）。"""
        events = integrity_ledger(extra_events=[
            {"event": "decision", "t": 1.0, "day": MODAL_DAY, "boundary": "new_day",
             "source": "deterministic_fallback", "llm": True, "intents": [], "problems": [],
             "fallback": "llm_error:truncated: 空回答", "truncated": False},
        ])
        rep = self._report(events, "fallback.jsonl")
        dc = rep["decision_counts"]
        self.assertEqual(dc["decisions_llm"], 1)
        self.assertEqual(dc["decisions_llm_used"], 0)
        self.assertEqual(dc["decisions_llm_fallback"], 1)
        self.assertEqual(len(dc["llm_fallback_lines"]), 1)
        text = mod.render_text(rep, 50)
        self.assertIn("decisions_llm=1", text)
        self.assertIn("decisions_llm_used=0", text)
        self.assertIn("兜底 decisions_llm_fallback=1 见", text)

    def test_clean_ledger_has_no_truncation_advice(self):
        rep = self._report(integrity_ledger(), "decision_clean.jsonl")
        self.assertEqual(rep["decision_counts"]["total"], 0)
        self.assertNotIn("max_tokens", " ".join(a["text"] for a in rep["advice"]))

    def test_truncated_false_is_not_flagged(self):
        events = integrity_ledger(extra_events=[
            {"event": "decision", "t": 1.0, "day": MODAL_DAY, "boundary": "new_day",
             "source": "llm", "llm": True, "intents": [], "problems": [], "fallback": None,
             "truncated": False},
        ])
        rep = self._report(events, "decision_ok.jsonl")
        self.assertEqual(rep["decision_counts"]["truncated_lines"], [])
        self.assertNotIn("max_tokens", " ".join(a["text"] for a in rep["advice"]))


class TestWaterEvidenceGates(unittest.TestCase):
    """task-36：浇水证据的两个新字段（`checks.watered_outdoor` + `day_end.final_water`）必须与
    `tools\\verify-run3.py` 的四个闸门同向：缺失 = 红（缺失 ≠ 通过）、false = 红、
    true + scope=window + tiles=0 = 红、true + dry>0 = 红；true 但没写 final_water 只记信息项。"""

    OK_CHECKS = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                 "no_unmet_stages": True, "crops_watered": True, "day_justified": True,
                 "watered_outdoor": True}
    FARM_OK = {"t": 590.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0, "scope": "farm"}

    def _report(self, name, *, checks=None, final_water="absent", **overrides):
        end = {"checks": self.OK_CHECKS if checks is None else checks}
        if final_water != "absent":
            end["final_water"] = final_water
        end.update(overrides)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, integrity_ledger(day_end_overrides=end)), days=1)

    def test_farm_scope_with_crops_and_no_dry_is_clean(self):
        rep = self._report("water_farm_ok.jsonl", final_water=self.FARM_OK)
        self.assertNotIn("missed:check:watered_outdoor", subjects(rep["categories"]["missed"]))
        self.assertEqual(
            [s for s in subjects(rep["categories"]["wasted"]) if s.startswith("wasted:water_")], []
        )
        self.assertIn("浇水证据=farm/Farm dry=0/31 tiles=84", mod.render_text(rep, 20))

    def test_window_scope_with_zero_tiles_is_flagged(self):
        rep = self._report(
            "water_window_empty.jsonl",
            final_water={"t": 590.0, "location": "", "tiles": 0, "crops": 0, "dry": None, "scope": "window"},
        )
        self.assertIn("wasted:water_scope_empty", subjects(rep["categories"]["wasted"]))
        self.assertEqual(rep["categories_total"]["wasted"], 1)

    def test_dry_greater_than_zero_contradicts_checks(self):
        rep = self._report(
            "water_dry.jsonl",
            final_water={"t": 590.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 5, "scope": "farm"},
        )
        self.assertIn("wasted:water_contradiction", subjects(rep["categories"]["wasted"]))
        bad = [f for f in rep["categories"]["wasted"] if f["subject"] == "wasted:water_contradiction"]
        self.assertIn("final_water.dry=5", bad[0]["summary"])

    def test_missing_check_is_red_and_undecidable_never_a_pass(self):
        checks = {k: v for k, v in self.OK_CHECKS.items() if k != "watered_outdoor"}
        rep = self._report("water_missing.jsonl", checks=checks, final_water=self.FARM_OK)
        self.assertIn("missed:check:watered_outdoor", subjects(rep["categories"]["missed"]))
        self.assertTrue(
            any("watered_outdoor" in u for u in rep["undecidable"]),
            "缺失必须同时进【无法判定】：" + "; ".join(rep["undecidable"]),
        )
        # 账本自己写 verified=true，但本工具必须点明"该天不判通过"
        self.assertTrue(rep["days"][0]["verified"])
        self.assertIn("不判该天通过", mod.render_text(rep, 20))

    def test_false_is_flagged_as_problem(self):
        checks = dict(self.OK_CHECKS, watered_outdoor=False)
        rep = self._report("water_false.jsonl", checks=checks, final_water=self.FARM_OK)
        self.assertIn("missed:check:watered_outdoor", subjects(rep["categories"]["missed"]))
        self.assertIn("浇水证据=false", mod.render_text(rep, 20))

    def test_whole_field_absent_is_listed_as_undecidable(self):
        rep = self._report("water_no_field.jsonl")  # final_water 整条不写
        self.assertTrue(
            any("本账本没有 day_end.final_water" in u for u in rep["undecidable"]),
            "; ".join(rep["undecidable"]),
        )
        self.assertTrue(
            any("但没写 final_water" in u for u in rep["undecidable"]),
            "true 却没有 final_water 可核对的天数要单列：" + "; ".join(rep["undecidable"]),
        )
        self.assertIn("浇水证据=true 但无 final_water 可核对", mod.render_text(rep, 20))
        # 缺证据 ≠ 通过，但也不额外判红（与 verify-run3.py:414-418 同向）
        self.assertNotIn("wasted:water_contradiction", subjects(rep["categories"]["wasted"]))
        self.assertNotIn("missed:check:watered_outdoor", subjects(rep["categories"]["missed"]))

    def test_water_advice_names_the_lines(self):
        rep = self._report("water_advice.jsonl", final_water=self.FARM_OK, checks=dict(
            self.OK_CHECKS, watered_outdoor=False))
        water_advice = [a for a in rep["advice"] if "浇水证据有问题" in a["text"]]
        self.assertTrue(water_advice, "浇水问题必须进建议清单")
        self.assertTrue(water_advice[0]["lines"], "建议必须带证据行号")


class TestCrossDayDayAfterAndTask32(unittest.TestCase):
    """task-38：跨日以 `day_end.day_after`（睡后重取的观测）为权威证据；`plots_capped`/`work_spot`
    入桶且只算信息项；`no_plot` 不再是正当收工理由。"""

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def test_day_after_plus_one_is_the_authority(self):
        rep = self._report(integrity_ledger(day_end_overrides={
            "day_after": [1, "spring", 13],
            # final 故意留在当天（睡前快照）：有 day_after 时不许拿 final 判"没跨日"
            "final": final(MODAL_DAY),
        }), "day_after_ok.jsonl")
        self.assertNotIn("missed:cross_day", subjects(rep["categories"]["missed"]))
        day = rep["days"][0]
        self.assertEqual(day["cross_day_verdict"], "crossed")
        self.assertEqual(day["cross_day_source"], "day_after")
        self.assertEqual(day["day_after"], [1, "spring", 13])
        text = mod.render_text(rep, 20)
        self.assertIn("跨日=day_after 1/spring/13", text)
        self.assertIn("跨日证据 day_after: 1/1 天", text)
        self.assertNotIn("跨日=无法判定", text)

    def test_day_after_plus_two_is_red_and_unparsable_is_undecidable(self):
        twice = self._report(integrity_ledger(day_end_overrides={"day_after": [1, "spring", 14]}),
                             "day_after_twice.jsonl")
        self.assertIn("missed:cross_day", subjects(twice["categories"]["missed"]))
        self.assertEqual(twice["days"][0]["cross_day_source"], "day_after")
        weird = self._report(integrity_ledger(day_end_overrides={"day_after": ["?", "spring", 13]}),
                             "day_after_weird.jsonl")
        self.assertNotIn("missed:cross_day", subjects(weird["categories"]["missed"]),
                         "认不出的 day_after ⇒ 【无法判定】，绝不当'没跨日'")
        self.assertEqual(weird["days"][0]["cross_day_verdict"], "undecidable")
        self.assertTrue(any("无法判定是否跨日" in u for u in weird["undecidable"]))

    def test_missing_day_after_is_undecidable_in_report_and_render(self):
        rep = self._report(integrity_ledger(day_end_overrides={"final": final(MODAL_DAY)}),
                           "cross_no_after.jsonl")
        day = rep["days"][0]
        self.assertEqual(day["cross_day_verdict"], "undecidable")
        self.assertEqual(day["cross_day_source"], "final")
        self.assertEqual(day["day_after"], [])
        self.assertNotIn("missed:cross_day", subjects(rep["categories"]["missed"]))
        text = mod.render_text(rep, 20)
        self.assertIn("跨日=无法判定（缺 day_after，final 是睡前快照；缺失 ≠ 没做）", text)
        self.assertIn("跨日证据 day_after: 0/1 天", text)
        self.assertIn("⚠", text, "跨日证据不齐必须在 header 里显式标注")
        self.assertTrue(any("无法判定是否跨日（缺失 ≠ 没做）×1 天" in u and "L2" in u
                            for u in rep["undecidable"]),
                        "缺失必须进【无法判定】并带行号：" + "; ".join(rep["undecidable"]))

    def test_plots_capped_and_work_spot_are_info_counts(self):
        rep = self._report(integrity_ledger(extra_events=[
            {"event": "plots_capped", "t": 3.0, "plots_today": 10, "limit": 10, "zone": "field_ne",
             "tiles": 25, "note": "一天 10 片到顶"},
            {"event": "work_spot", "t": 4.0, "zone": "field_se", "tiles": 4, "note": "收尾作业区"},
        ]), "task32_events.jsonl")
        self.assertEqual(rep["events"]["plots_capped"], 1)
        self.assertEqual(rep["events"]["work_spot"], 1)
        text = mod.render_text(rep, 20)
        self.assertIn("plots_capped 1 次", text)
        self.assertIn("work_spot 1 次", text)
        missed = subjects(rep["categories"]["missed"])
        self.assertNotIn("missed:plots_capped", missed)
        self.assertNotIn("missed:work_spot", missed)
        self.assertTrue(any(name == "plots_capped / work_spot" for name, _ in mod.MAPPING_TEXT))

    def test_no_plot_is_not_a_justified_reason(self):
        meaning = mod.CHECK_MEANING["day_justified"]
        for kw in ("night", "stamina", "no_work"):
            self.assertIn(kw, meaning)
        self.assertIn("no_plot", meaning)
        self.assertIn("不是正当理由", meaning)


class TestNoWorkWithDry(unittest.TestCase):
    """task-60：`ended_reason` 以 `no_work` 开头 **且** `final_water.dry>0` = "没活却还有干地"
    （run3 连睡病形态）⇒ 必须判红，且 `checks.day_justified` 在该形态下不成立；
    与 `tools\\verify-run3.py` 的同一专判同向；`final_water` 缺失 ⇒ 只记【无法判定】（缺失 ≠ 通过）。"""

    DRY = {"t": 590.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 1, "scope": "farm"}
    CHECKS = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
              "crops_watered": True, "day_justified": True, "watered_outdoor": False}

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1, top=50)

    def test_no_work_with_dry_is_red(self):
        rep = self._report(integrity_ledger(day_end_overrides={
            "ended_reason": "no_work:确实找不到可做的活（地里的活干完了）",
            "final_water": dict(self.DRY),
            "checks": dict(self.CHECKS),
        }), "no_work_dry.jsonl")
        self.assertIn("missed:no_work_with_dry", subjects(rep["categories"]["missed"]))
        self.assertFalse(rep["days"][0]["day_justified_effective"], "dry>0 时 day_justified 不成立")
        self.assertEqual(rep["days"][0]["no_work_with_dry"], 1)
        text = mod.render_text(rep, 20)
        self.assertIn("day_justified 不成立：dry>0", text)
        self.assertTrue(any("没活却还有干地" in a["text"] for a in rep["advice"]),
                        "必须进建议清单：" + "; ".join(a["text"] for a in rep["advice"]))
        red = [a for a in rep["advice"] if "没活却还有干地" in a["text"]]
        self.assertTrue(red[0]["lines"], "建议必须带证据行号")

    def test_no_work_with_dry_zero_is_not_red(self):
        rep = self._report(integrity_ledger(day_end_overrides={
            "ended_reason": "no_work:确实找不到可做的活",
            "final_water": dict(self.DRY, dry=0),
            "checks": dict(self.CHECKS, watered_outdoor=True),
        }), "no_work_ok.jsonl")
        self.assertNotIn("missed:no_work_with_dry", subjects(rep["categories"]["missed"]))
        self.assertTrue(rep["days"][0]["day_justified_effective"], "dry==0 时白名单照常生效")
        self.assertIsNone(rep["days"][0]["no_work_with_dry"])
        self.assertNotIn("不成立：dry>0", mod.render_text(rep, 20))

    def test_missing_final_water_is_undecidable_not_pass(self):
        checks = {k: v for k, v in self.CHECKS.items() if k != "watered_outdoor"}  # 也没有 final_water
        rep = self._report(integrity_ledger(day_end_overrides={
            "ended_reason": "no_work:今天没活",
            "checks": checks,
        }), "no_work_missing_fw.jsonl")
        subs = subjects(rep["categories"]["missed"])
        self.assertNotIn("missed:no_work_with_dry", subs, "缺失 ≠ 判红（也不许当通过）")
        self.assertIn("missed:check:watered_outdoor", subs, "缺失 ≠ 通过：照 CHECK_MEANING 口径判红")
        self.assertTrue(any(("watered_outdoor" in u) or ("final_water" in u) for u in rep["undecidable"]),
                        "缺失必须同时进【无法判定】：" + "; ".join(rep["undecidable"]))
        self.assertIsNone(rep["days"][0]["no_work_with_dry"])

    def test_run5_three_hits_regression(self):
        if not os.path.isfile(RUN5):
            self.skipTest(f"缺少账本 {RUN5}")
        rep = report_for(RUN5, days=3, top=500)
        hits = [f for f in rep["categories"]["missed"] if f["subject"] == "missed:no_work_with_dry"]
        detail = [(f["line"], f["summary"][:60]) for f in hits]
        self.assertEqual(len(hits), 3, f"run5 应恰有 3 天命中（spring 26/27/28），实际 {detail}")
        by_line = {d["day_end_lines"][-1]: d["label"] for d in rep["days"] if d["day_end_lines"]}
        labels = [by_line.get(f["line"]) for f in hits]
        self.assertTrue(all(lbl and "summer" not in lbl for lbl in labels),
                        f"命中的必须是 spring 26/27/28，不能含 summer：{labels}")
        self.assertEqual(rep["verified_days"], 0, "run5 仍是 0/3")


class TestEventMappingDrift(unittest.TestCase):
    """Lead m02395 机械核对：`EVENT_BUCKETS` 不许落后于 brain 里 `_journal("<name>"` 发出的事件名。

    run6 复盘靠桶计数，漏映射 = 新证据静默消失，所以既做"brain × 桶"的漂移测试，
    也验证"账本里出现没桶的事件 ⇒ 报告点名 + 建议"，还要把 decision 计数钉死在
    `tools/verify-run3.py` 的口径上（四路对账不许两边数字不同源）。
    """

    RUN6_NEW_EVENTS = ("event_blocked", "farm_evidence_unavailable", "sell", "sell_failed",
                       "goto_farm", "plot_walk", "resume_walk", "water_far",
                       "water_far_unavailable", "seed_gate", "stage_midway_leftover")

    def _report(self, events, name, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=days)

    def test_event_buckets_cover_every_brain_journal_name(self):
        if not os.path.isfile(BRAIN_LONG_RUN):
            self.skipTest(f"缺少 {BRAIN_LONG_RUN}")
        with open(BRAIN_LONG_RUN, encoding="utf-8") as fh:
            src = fh.read()
        names = sorted(set(re.findall(r'_journal\(\s*"([a-z0-9_]+)"', src)))
        self.assertTrue(names, "没扫到任何 _journal 事件名（正则或文件结构变了？）")
        missing = [n for n in names if n not in mod.EVENT_BUCKETS]
        self.assertEqual(missing, sorted(mod.STRUCTURAL_EVENTS),
                         f"EVENT_BUCKETS 落后于 {BRAIN_LONG_RUN}：{missing}")

    def test_run6_events_are_mapped(self):
        for name in self.RUN6_NEW_EVENTS:
            self.assertIn(name, mod.EVENT_BUCKETS, f"run6 要看的事件 {name} 没有桶 ⇒ 计数会漏")

    def test_unknown_event_is_listed_and_advised(self):
        events = integrity_ledger(extra_events=[
            {"event": "mystery_event", "t": 3.0, "day": MODAL_DAY, "note": "账本里有、工具没桶"},
        ])
        rep = self._report(events, "unknown_event.jsonl")
        info = rep["unmapped_events"].get("mystery_event")
        self.assertIsNotNone(info, f"未映射事件必须点名，不许静默丢弃：{rep['unmapped_events']}")
        self.assertEqual(info["count"], 1)
        self.assertTrue(info["lines"], "要点名行号")
        text = mod.render_text(rep, 50)
        self.assertIn("未映射事件", text)
        self.assertIn("mystery_event×1", text)
        self.assertIn("mystery_event×1", " ".join(a["text"] for a in rep["advice"]))
        self.assertEqual(mod.build_advice(rep)[0]["lines"], info["lines"], "未映射事件要排在最前面")

    def test_real_ledgers_have_no_unmapped_events(self):
        for path in (RUN2, RUN5):
            if not os.path.isfile(path):
                self.skipTest(f"缺少账本 {path}")
            rep = report_for(path, days=3, top=50)
            self.assertEqual(rep["unmapped_events"], {},
                             f"{os.path.basename(path)} 出现未映射事件：{rep['unmapped_events']}")

    def test_decision_counts_match_verify_run3_rule(self):
        """verify-run3.py:588-589 口径：decisions = event=="decision"；llm = 其中 r.get("llm") 为真。

        `llm` 键与 `source=="llm"` 在真账本上**可能不一致**（run2 L17 = `llm=true` +
        `source=deterministic_fallback` + `fallback=llm_error:truncated`）——这正是四路对账要看见的东西：
        计数按 verify-run3 口径，同时把不一致的行单列出来（本工具不替它改口径）。
        """
        for path in (RUN2, RUN5):
            if not os.path.isfile(path):
                self.skipTest(f"缺少账本 {path}")
            rows, _ = mod.load_journal(path)
            decisions = [(ln, ev) for ln, ev in rows if ev.get("event") == "decision"]
            want_total = len(decisions)
            want_llm = sum(1 for _, ev in decisions if ev.get("llm"))
            want_by_source = sum(1 for _, ev in decisions if ev.get("source") == "llm")
            want_dis = [ln for ln, ev in decisions
                        if bool(ev.get("llm")) != (ev.get("source") == "llm")]
            dc = report_for(path, days=3, top=50)["decision_counts"]
            want_used = sum(1 for _, ev in decisions
                            if ev.get("llm") and ev.get("source") == "llm")
            want_fb_lines = [ln for ln, ev in decisions
                             if ev.get("llm") and ev.get("source") != "llm"]
            self.assertEqual(dc["total"], want_total, f"{path}: decision 条数口径不一致")
            self.assertEqual(dc["llm"], want_llm, f"{path}: LLM 条数口径不一致（verify-run3 只看 llm 键）")
            # Lead m02565：decisions_llm（发起过调用）/ decisions_llm_used（真被采纳）/ 差值=兜底
            self.assertEqual(dc["decisions_llm"], want_llm, f"{path}: decisions_llm 口径不一致")
            self.assertEqual(dc["decisions_llm_used"], want_used, f"{path}: decisions_llm_used 口径不一致")
            self.assertEqual(dc["decisions_llm_fallback"], want_llm - want_used,
                             f"{path}: 兜底差值口径不一致")
            self.assertEqual(dc["llm_fallback_lines"], want_fb_lines,
                             f"{path}: 兜底必须逐行点名")
            self.assertEqual(dc["llm_by_source"], want_by_source, f"{path}: source=llm 计数不一致")
            self.assertEqual(dc["llm_disagree_lines"], want_dis,
                             f"{path}: llm 与 source=llm 不一致的行必须逐行点名")
            text = mod.render_text(report_for(path, days=3, top=50), 50)
            if want_dis:
                self.assertIn("不一致的行", text, f"{path}: 不一致必须在报告里可见")
            if want_fb_lines:
                self.assertIn(f"decisions_llm_fallback={len(want_fb_lines)}", text,
                              f"{path}: 兜底数必须出现在头部（LLM 覆盖率不能虚高）")


if __name__ == "__main__":
    unittest.main()
