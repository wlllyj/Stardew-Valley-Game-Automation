#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""`tools/analyze-longrun.py` 的回归测试（task-25）。

判据分三层：
  1. 真实账本：run2 必须自动重现 5 项验收事实；run1（缺 day_end/finish）必须不崩且如实标注"无法判定"。
  2. 自造账本：全绿的一天不能报问题；cancel→fallback 与"leftover 却自称 verified"必须被点名。
  3. CLI 契约：不可读/空账本退出码 2；`--json` 能产出可解析 JSON（含 mapping）；
     退出码见 task-65：0 = 无红、1 = 有红、2 = 跑不动（`--advisory` 恒 0）。

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
RUN_A8 = os.path.join(ROOT, "logs", "longrun-runA8-0743.jsonl")
GREEN = os.path.join(ROOT, "scratch", "_ledger_green.jsonl")
FALLBACK = os.path.join(ROOT, "scratch", "_ledger_fallback.jsonl")
WASH = os.path.join(ROOT, "scratch", "_ledger_leftover_verified.jsonl")

#: task-3：区分「字段缺失」与「字段值为 false」的哨兵（缺 `slept_by_us` 必须【无法判定】）。
_MISSING = object()


def report_for(path, days=3, top=50, window=None):
    rows, bad_lines = mod.load_journal(path)
    argv = ["--journal", path, "--days", str(days), "--top", str(top)]
    if window is not None:
        argv += ["--window", str(window)]
    args = mod.parse_args(argv)
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
        # task-65：这本账本有红（模态/职业选择）⇒ 默认严格 rc=1；JSON 结构与旧键都不变
        self.assertEqual(code, 1)
        payload = json.loads(buf.getvalue())
        self.assertIn("manual_intervention", payload)
        self.assertIn("env_inconclusive", payload)
        self.assertGreaterEqual(payload["red"]["total"], 1)
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


class TestUnreachableAccounting(unittest.TestCase):
    """task-52：不可达（四邻都站不过去 / A* 算不出路）的三级留痕与日级豁免上界。

    口径（与 `tools/verify-run3.py:415-448` 同向）：
      * `unreachable` / `unreachable_stage` / `unreachable_summary` = **环境挡路信息项**：
        **不计当天硬失败**、当天记 blocked、次日重试；
      * 日级豁免有上界 `max(5, 20%×attempted)`：`checks.unreachable_within_bound=false` ⇒ 0 类红；
      * 阶段账目差额允许被 `unreachable_count` 解释（不判"账目不可信"）。
    """

    U_TILE = {"event": "unreachable", "t": 4.0, "tile": [72, 51], "action": "clear",
              "stage": "clear_area", "zone": "field_ne", "reason": "四邻都站不过去",
              "note": "当天记 blocked、次日重试"}
    U_STAGE = {"event": "unreachable_stage", "t": 4.1, "stage": "clear_area", "zone": "field_ne",
               "tiles": 3, "in_leftover": 3, "coords": [[72, 51], [73, 51], [74, 51]],
               "note": "阶段收尾：走不到的格"}
    U_SUM = {"event": "unreachable_summary", "t": 9.5, "count": 3, "bound": 5, "attempted": 20,
             "exempted": 3, "raw_unmet": 3, "unmet": 0,
             "tiles": [[72, 51], [73, 51], [74, 51]], "note": "日级豁免上界"}

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def _events(self, *, bound_ok=True, unreach=3, bound=5, stage_unreach=3, stage_failed=3,
                failed_steps=0, with_fields=True):
        stage = {"stage": "clear_area", "tiles": 3, "ok": 0, "skipped": 0, "failed": stage_failed,
                 "proven_inert": 0, "env_block": 0, "inconclusive": 0, "stopped": "", "leftover": 0}
        if stage_unreach is not None:
            stage["unreachable_count"] = stage_unreach
        overrides = {
            "ended_reason": "night", "verified": bool(bound_ok), "failed_steps": failed_steps,
            "stages": [stage],
            "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                       "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                       "unreachable_within_bound": bound_ok},
        }
        if with_fields:
            overrides.update({
                "unreachable": unreach, "unreachable_bound": bound,
                "unreachable_exempt": min(unreach, bound),
                "unreachable_tiles": [[72, 51], [73, 51], [74, 51]],
            })
        return integrity_ledger(extra_events=[self.U_TILE, self.U_STAGE, self.U_SUM],
                                day_end_overrides=overrides)

    def test_three_events_have_buckets_and_are_not_unmapped(self):
        for name in ("unreachable", "unreachable_stage", "unreachable_summary"):
            self.assertIn(name, mod.EVENT_BUCKETS, f"task-52 的 {name} 没有桶 ⇒ 计数会漏")
        rep = self._report(self._events(), "unreach.jsonl")
        self.assertEqual(rep["unmapped_events"], {},
                         f"task-52 的三个事件都已进桶，不许再出现未映射：{rep['unmapped_events']}")
        for bucket in ("unreachable", "unreachable_stages", "unreachable_summaries"):
            self.assertIn(bucket, mod.NEW_EVENT_BUCKETS, "新桶要在头部'新事件计数'里可见")

    def test_inside_bound_is_info_only_and_visible(self):
        rep = self._report(self._events(stage_unreach=0, stage_failed=0), "unreach_ok.jsonl")
        env = rep["env_inconclusive"]
        self.assertEqual(env["unreachable_events"], 1)
        self.assertEqual(env["unreachable_tile_count"], 1)
        self.assertEqual(env["unreachable_stage_events"], 1)
        self.assertEqual(env["unreachable_summary_events"], 1)
        self.assertEqual(env["unreachable_count"], 3)
        self.assertEqual(env["unreachable_bound"], 5)
        self.assertEqual(env["unreachable_exempt"], 3)
        self.assertEqual(env["unreachable_attempted"], 20)
        self.assertIs(env["unreachable_within_bound"], True)
        subs = subjects(rep["categories"]["environment"])
        self.assertIn("environment:unreachable", subs)
        self.assertIn("environment:unreachable_stage", subs)
        self.assertNotIn("manual:check:unreachable_within_bound", subjects(rep["categories"]["manual"]))
        # 信息项：不许并进"该做没做"
        for s in subjects(rep["categories"]["missed"]):
            self.assertNotIn("unreachable", s, "不可达是环境挡路信息项，不该进'该做没做'")
        text = mod.render_text(rep, 50)
        self.assertIn("不可达", text)
        self.assertTrue(any("不可达" in a["text"] for a in rep["advice"]))
        self.assertIn("exempt=3", text)
        # 上界内且账目自洽（stages[].failed 不含被豁免格）⇒ 不出现"账目不可信"
        self.assertNotIn("missed:stage_account", subjects(rep["categories"]["missed"]))

    def test_unreachable_is_not_part_of_stage_account_allowance(self):
        """账目差额口径与 `tools\\verify-run3.py:388-404` 逐字一致：只认 env_block + inconclusive。

        把不可达格计进 `stages[].failed`（正常实现不会：exempt 后它们已从 leftover 移除）⇒ 差额
        解释不完 ⇒ 两边同向判红，**不许**用 `unreachable` 去把它洗平。
        """
        rep = self._report(self._events(stage_unreach=3), "unreach_delta.jsonl")
        self.assertIn("missed:stage_account", subjects(rep["categories"]["missed"]),
                      "unreachable 不许进账目差额口径（verify-run3.py:388-404 只认 env+inconclusive）")

    def test_over_bound_is_manual_red(self):
        rep = self._report(self._events(bound_ok=False, unreach=9, bound=5), "unreach_bad.jsonl")
        subs = subjects(rep["categories"]["manual"])
        self.assertIn("manual:check:unreachable_within_bound", subs)
        text = mod.render_text(rep, 50)
        self.assertIn("unreachable_within_bound=false", text)
        self.assertTrue(any("0 类红" in a["text"] for a in rep["advice"]))

    def test_missing_task52_fields_render_nothing_and_never_pass_by_accident(self):
        rep = self._report(integrity_ledger(), "unreach_absent.jsonl")
        env = rep["env_inconclusive"]
        self.assertEqual(env["unreachable_events"], 0)
        self.assertIsNone(env["unreachable_count"])
        self.assertIsNone(env["unreachable_within_bound"])
        self.assertNotIn("manual:check:unreachable_within_bound", subjects(rep["categories"]["manual"]))
        self.assertFalse(any("不可达（四邻" in a["text"] for a in rep["advice"]))


class TestRefusedAccounting(unittest.TestCase):
    """task-63/task-66：被**游戏拒绝**（till 的 `tool_ineffective`/`precondition_failed`）的三级留痕、
    独立豁免上界与硬闸门。口径与 `tools\\verify-run3.py:518-521` 同向：

      * `tool_refused` / `refused_stage` / `refused_summary` = 5 环境挡路信息项（**不计当天硬失败**、
        当天封格、**次日重试**），**不并进"该做没做"**；
      * 日级 `refused_bound = max(5, 20%×attempted)`；`checks.refused_within_bound=false` ⇒ 0 类红；
      * 与 task-52 的 `unreachable` 是**两套集合 / 两套界**，各自扣减、**不许互相掩护**；
      * `day_end.refused*` / `checks.refused_within_bound` 缺失 ⇒ 只进【无法判定】（缺失 ≠ 通过）。
    """

    R_TILE = {"event": "tool_refused", "t": 4.0, "tile": [72, 51], "action": "till",
              "stage": "till_area", "zone": "field_ne", "status": "tool_ineffective",
              "kind": "grass", "reason": "锄不动（这一格还是 grass）"}
    R_TILE2 = {"event": "tool_refused", "t": 4.05, "tile": [73, 51], "action": "till",
               "stage": "till_area", "zone": "field_ne", "status": "tool_ineffective",
               "kind": "grass", "reason": "锄不动（这一格还是 grass）"}
    R_STAGE = {"event": "refused_stage", "t": 4.1, "stage": "till_area", "zone": "field_ne",
               "tiles": 3, "in_leftover": 3, "coords": [[72, 51], [73, 51], [74, 51]],
               "note": "阶段收尾：被游戏拒绝的格"}
    R_SUM = {"event": "refused_summary", "t": 9.5, "count": 3, "bound": 5, "attempted": 20,
             "exempted": 3, "raw_unmet": 3, "unmet": 0,
             "tiles": [[72, 51], [73, 51], [74, 51]], "note": "日级拒绝豁免上界"}
    BASE_CHECKS = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                   "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                   "watered_outdoor": True, "unreachable_within_bound": True}

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def _events(self, *, bound_ok=True, refused=3, bound=5, stage_refused=3, stage_failed=0,
                stage_ok=5, env_block=0, failed_steps=0, with_fields=True, extra_events=()):
        stage = {"stage": "till_area", "tiles": 3, "ok": stage_ok, "skipped": 0,
                 "failed": stage_failed, "proven_inert": 0, "env_block": env_block,
                 "inconclusive": 0, "stopped": "", "leftover": 0}
        if stage_refused is not None:
            stage["refused"] = stage_refused
        overrides = {
            "ended_reason": "night", "verified": bool(bound_ok), "failed_steps": failed_steps,
            "stages": [stage],
            "checks": dict(self.BASE_CHECKS, refused_within_bound=bound_ok),
            "final_water": {"t": 590.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0,
                            "scope": "farm"},
        }
        if with_fields:
            overrides.update({
                "refused": refused, "refused_bound": bound,
                "refused_exempt": min(refused, bound),
                "refused_tiles": [[72, 51], [73, 51], [74, 51]],
            })
        return integrity_ledger(
            extra_events=[self.R_TILE, self.R_STAGE, self.R_SUM] + list(extra_events),
            day_end_overrides=overrides)

    def test_events_have_buckets_and_are_not_unmapped(self):
        for name in ("tool_refused", "refused_stage", "refused_summary"):
            self.assertIn(name, mod.EVENT_BUCKETS, f"task-66 的 {name} 没有桶 ⇒ 计数会漏")
        for bucket in ("tool_refused", "refused_stages", "refused_summaries"):
            self.assertIn(bucket, mod.NEW_EVENT_BUCKETS, "新桶要在头部'新事件计数'里可见")
        rep = self._report(self._events(), "refused.jsonl")
        self.assertEqual(rep["unmapped_events"], {},
                         f"task-66 三个事件都已进桶，不许再出现未映射：{rep['unmapped_events']}")

    def test_inside_bound_is_info_only_and_visible(self):
        rep = self._report(self._events(), "refused_ok.jsonl")
        env = rep["env_inconclusive"]
        self.assertEqual(env["refused_events"], 1)
        self.assertEqual(env["refused_tile_count"], 1)
        self.assertEqual(env["refused_stage_events"], 1)
        self.assertEqual(env["refused_summary_events"], 1)
        self.assertEqual(env["refused_count"], 3)
        self.assertEqual(env["refused_bound"], 5)
        self.assertEqual(env["refused_exempt"], 3)
        self.assertEqual(env["refused_attempted"], 20)
        self.assertIs(env["refused_within_bound"], True)
        subs = subjects(rep["categories"]["environment"])
        self.assertIn("environment:refused", subs)
        self.assertIn("environment:refused_stage", subs)
        self.assertNotIn("manual:check:refused_within_bound",
                         subjects(rep["categories"]["manual"]))
        for s in subjects(rep["categories"]["missed"]):
            self.assertNotIn("refused", s, "被游戏拒绝是环境挡路信息项，不该进'该做没做'")
        text = mod.render_text(rep, 50)
        self.assertIn("游戏拒绝", text)
        self.assertIn("exempt=3", text)
        self.assertTrue(any("被游戏拒绝" in a["text"] for a in rep["advice"]))
        self.assertNotIn("missed:stage_account", subjects(rep["categories"]["missed"]))

    def test_over_bound_is_manual_red(self):
        rep = self._report(self._events(bound_ok=False, refused=9, bound=5), "refused_bad.jsonl")
        subs = subjects(rep["categories"]["manual"])
        self.assertIn("manual:check:refused_within_bound", subs)
        text = mod.render_text(rep, 50)
        self.assertIn("refused_within_bound=false", text)
        self.assertTrue(any("0 类红" in a["text"] for a in rep["advice"]))

    def test_missing_fields_is_undecidable_not_pass(self):
        rep = self._report(integrity_ledger(), "refused_absent.jsonl")
        env = rep["env_inconclusive"]
        self.assertEqual(env["refused_events"], 0)
        self.assertIsNone(env["refused_count"])
        self.assertIsNone(env["refused_within_bound"])
        self.assertNotIn("manual:check:refused_within_bound",
                         subjects(rep["categories"]["manual"]))
        self.assertTrue(any("day_end.refused" in u for u in rep["undecidable"]),
                        "缺字段必须进【无法判定】，不许静默丢弃：" + "; ".join(rep["undecidable"]))
        self.assertFalse(any("被游戏拒绝（tool_ineffective" in a["text"] for a in rep["advice"]))

    def test_refused_and_unreachable_counts_do_not_mix(self):
        unreach = [
            {"event": "unreachable", "t": 5.0, "tile": [10, 10], "action": "till",
             "stage": "till_area", "zone": "field_ne", "reason": "四邻都站不过去", "note": ""},
            {"event": "unreachable", "t": 5.1, "tile": [11, 10], "action": "till",
             "stage": "till_area", "zone": "field_ne", "reason": "四邻都站不过去", "note": ""},
        ]
        rep = self._report(self._events(extra_events=[self.R_TILE2] + unreach), "both.jsonl")
        env = rep["env_inconclusive"]
        self.assertEqual(env["refused_tile_count"], 2, "拒绝格只认 tool_refused 的坐标")
        self.assertEqual(env["unreachable_tile_count"], 2, "不可达格只认 unreachable 的坐标")
        subs = subjects(rep["categories"]["environment"])
        self.assertIn("environment:refused", subs)
        self.assertIn("environment:unreachable", subs)

    def test_refused_is_not_part_of_stage_account_allowance(self):
        """账目差额解释口径与 `tools\\verify-run3.py:388-404` 逐字一致：只认 env_block + inconclusive。

        拒绝格被 `refused_exempt` 扣掉后本就不该出现在 `stages[].failed`；不许拿 `refused` 去把差额
        洗平（两套豁免互不掩护）。
        """
        ok = self._report(self._events(stage_refused=3, stage_failed=5, failed_steps=3, env_block=2),
                          "refused_delta_ok.jsonl")
        self.assertNotIn("missed:stage_account", subjects(ok["categories"]["missed"]))
        bad = self._report(self._events(stage_refused=3, stage_failed=5, failed_steps=3, env_block=0),
                           "refused_delta_bad.jsonl")
        self.assertIn("missed:stage_account", subjects(bad["categories"]["missed"]),
                      "refused 不许进账目差额口径（verify-run3.py:388-404 只认 env+inconclusive）")


class TestVacuumDayGate(unittest.TestCase):
    """task-64（Lead m02981）：真空日闸门与 `tools/verify-run3.py:604-625` 同口径、不许更宽。

    口径：
      * ``day_end.verified is True`` + **有阶段记录** + ``Σ stage.ok == 0`` ⇒ 红
        ``wasted:verified_zero_steps``（文案含"自称 VERIFIED 但当天成功动作 0 步"）；
      * ``0 < Σ ok < 5`` ⇒ 顶部"弱日"信息项（不判红）；
      * 阶段记录可来自 ``day_end.stages[]`` 或**独立** ``stage`` 事件（对照夹具的形态）；
      * ``stages`` 与 ``ok_steps`` 都缺 ⇒ 只进【无法判定】，既不判通过也不误判红；
      * 既有的 ``wasted:verified_without_work``（当天 0 阶段 + 无"无活可做"证据）**不许放宽**。
    """

    OK_CHECKS = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                 "crops_watered": True, "day_justified": True, "no_unmet_stages": True}

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    @staticmethod
    def _stage(ok, stage="till_area", failed=0):
        return {"stage": stage, "tiles": max(ok, failed), "ok": ok, "skipped": 0, "failed": failed,
                "proven_inert": 0, "env_block": 0, "inconclusive": 0, "stopped": "", "leftover": 0}

    def _events_with_stages(self, ok):
        return integrity_ledger(day_end_overrides={
            "verified": True, "ended_reason": "night", "checks": dict(self.OK_CHECKS),
            "stages": [self._stage(ok)], "ok_steps": ok,
        })

    def test_zero_ok_with_stage_records_is_red(self):
        rep = self._report(self._events_with_stages(0), "vacuum_zero.jsonl")
        subs = subjects(rep["categories"]["wasted"])
        self.assertIn("wasted:verified_zero_steps", subs)
        text = mod.render_text(rep, 50)
        self.assertIn("自称 VERIFIED 但当天成功动作 0 步", text)
        self.assertTrue(any("0 步（有阶段记录" in a["text"] for a in rep["advice"]))

    def test_standalone_stage_events_are_counted_too(self):
        # Lead 的 vacuum 夹具形态：阶段记录是独立 `stage` 事件、`day_end.stages` 为空。
        rep = self._report(
            integrity_ledger(extra_events=[{"event": "stage", "t": 5.0, "stage": "water_area",
                                            "tiles": 3, "ok": 0, "skipped": 0, "failed": 0,
                                            "leftover": 0}],
                             day_end_overrides={"verified": True, "stages": [], "checks": dict(self.OK_CHECKS)}),
            "vacuum_standalone.jsonl",
        )
        self.assertIn("wasted:verified_zero_steps", subjects(rep["categories"]["wasted"]))
        self.assertNotIn("stage", rep["unmapped_events"], "独立 stage 事件必须有桶、不许落进未映射清单")

    def test_weak_day_is_info_and_enough_steps_is_clean(self):
        clean = self._report(self._events_with_stages(5), "vacuum_ok5.jsonl")
        self.assertNotIn("wasted:verified_zero_steps", subjects(clean["categories"]["wasted"]))
        self.assertEqual(clean["weak_days"], [])
        weak = self._report(self._events_with_stages(2), "vacuum_weak.jsonl")
        self.assertNotIn("wasted:verified_zero_steps", subjects(weak["categories"]["wasted"]))
        self.assertEqual(len(weak["weak_days"]), 1)
        self.assertIn("弱日: 1 天", mod.render_text(weak, 50))

    def test_missing_stage_fields_is_undecidable_not_red(self):
        end = {"event": "day_end", "t": 9.0, "day": MODAL_DAY, "day_text": "1年 spring 12日",
               "ended_by": "sleep", "ended_reason": "night", "verified": True,
               "checks": dict(self.OK_CHECKS), "final": final([MODAL_DAY[0], MODAL_DAY[1], MODAL_DAY[2] + 1])}
        rep = self._report([day_start(MODAL_DAY), end], "vacuum_missing.jsonl")
        self.assertNotIn("wasted:verified_zero_steps", subjects(rep["categories"]["wasted"]))
        undec = " ".join(rep["undecidable"])
        self.assertIn("既没有 stages 也没有 ok_steps", undec)


VACUUM = os.path.join(ROOT, "scratch", "_t5x_vacuum.jsonl")


class TestExitCodes(unittest.TestCase):
    """task-65（Lead）：退出码必须能表达"有红"（默认严格），否则就是"工具永远绿"。

    语义：``0`` = 无红；``1`` = 有红（`manual:*` / `missed:*` / 显式判红的 `wasted:*`）；
    ``2`` = 跑不动（读不到账本 / 空账本 / 参数错）；``--advisory`` 保留老行为（恒 0）。
    判决权威仍是 `tools\\verify-run3.py`：本工具的退出码只表达"有没有红"。
    """

    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mod.main(argv)
        return rc, buf.getvalue()

    def _vacuum_ledger(self, name):
        # 与 scratch\_t5x_vacuum.jsonl 同形：verified=true + **独立 stage 事件** ok=0 ⇒ 白做（红）
        stage = {"event": "stage", "t": 5.0, "stage": "water_area", "tiles": 3, "ok": 0,
                 "skipped": 0, "failed": 0, "leftover": 0}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return write_ledger(tmp.name, name, integrity_ledger(
            extra_events=[stage],
            day_end_overrides={
                "verified": True,
                "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                           "crops_watered": True, "day_justified": True},
            }))

    def _green_ledger(self, name):
        # 真·0 红：浇水证据齐（watered_outdoor=true + farm 口径 final_water/dry=0）、有活干、无红条
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return write_ledger(tmp.name, name, integrity_ledger(day_end_overrides={
            "verified": True, "ended_reason": "night",
            "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                       "crops_watered": True, "day_justified": True, "watered_outdoor": True,
                       "no_unmet_stages": True},
            "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0,
                            "scope": "farm"},
        }))

    def test_no_red_ledger_exits_zero(self):
        path = self._green_ledger("exit_green.jsonl")
        rc, text = self._run(["--journal", path])
        self.assertEqual(rc, 0, "0 红的账本必须 rc=0")
        self.assertIn("退出码: 0", text)
        self.assertIn("有红 0 条", text)

    def test_red_ledger_exits_one(self):
        path = self._vacuum_ledger("exit_vacuum.jsonl")
        rc, text = self._run(["--journal", path])
        self.assertEqual(rc, 1, "有红必须返回 1（工具不能永远绿）")
        self.assertIn("退出码: 1", text)
        self.assertIn("wasted:verified_zero_steps", text)

    def test_advisory_keeps_old_zero(self):
        path = self._vacuum_ledger("exit_advisory.jsonl")
        rc, text = self._run(["--journal", path, "--advisory"])
        self.assertEqual(rc, 0)
        self.assertIn("--advisory 已开 ⇒ 恒 0", text)

    def test_bad_journal_exits_two(self):
        rc, _ = self._run(["--journal", os.path.join(ROOT, "scratch", "_no_such_ledger_t65.jsonl")])
        self.assertEqual(rc, 2)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        empty = os.path.join(tmp.name, "empty.jsonl")
        with open(empty, "w", encoding="utf-8"):
            pass
        rc2, _ = self._run(["--journal", empty])
        self.assertEqual(rc2, 2, "空账本 ⇒ 2（没有可解析事件）")

    def test_help_documents_the_three_codes_and_authority(self):
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stdout(buf):
                mod.parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = buf.getvalue()
        self.assertIn("0 = 没有红", text)
        self.assertIn("2 = 跑不动", text)
        self.assertIn("判决权威仍是 tools\\verify-run3.py", text)
        self.assertIn("--advisory", text)

    def test_red_rule_and_report_key(self):
        rep = report_for(self._green_ledger("exit_green_rule.jsonl"))
        self.assertEqual(rep["red"]["total"], 0)
        self.assertFalse(rep["red"]["advisory"])
        self.assertTrue(mod.is_red_finding({"subject": "manual:modal_blocked"}))
        self.assertTrue(mod.is_red_finding({"subject": "missed:check:watered_outdoor"}))
        self.assertTrue(mod.is_red_finding({"subject": "wasted:verified_zero_steps"}))
        self.assertTrue(mod.is_red_finding({"subject": "wasted:whitewash:clear_area"}))
        self.assertFalse(mod.is_red_finding({"subject": "environment:env_fail"}))
        self.assertFalse(mod.is_red_finding({"subject": "wasted:leftover:clear_area"}))

    @unittest.skipUnless(os.path.exists(VACUUM), "Lead 的真空夹具不在（scratch\\_t5x_vacuum.jsonl）")
    def test_real_vacuum_fixture_exits_one(self):
        rc, text = self._run(["--journal", VACUUM])
        self.assertEqual(rc, 1)
        self.assertIn("wasted:verified_zero_steps", text)


RUN6 = os.path.join(ROOT, "logs", "longrun-3day-llm-run6.jsonl")


class TestSameDayRetryAndBuyAccounting(unittest.TestCase):
    """task-69（Lead）：run6 的两处呈现。

    ① 同一天重复起跑：2 个会话只有 1 个不同日历日 ⇒ 不许读成跨日/多天（跨日证据只对
       ``ended_by=sleep`` 生效），也不许因此发 ``missed:cross_day``。
    ② ``buy`` 事件：桶 ``buys`` 存在 ≠ 买成了；「没成交（receipt=item_not_sold）」必须如实
       计成**失败**，同一回执连续失败 = 守卫死锁指纹（run6 死因）。
    """

    def _report(self, events, name, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=days)

    def _stuck_end(self):
        return {
            "event": "day_end", "t": 9.0, "day": MODAL_DAY, "day_text": "1年 spring 12日",
            "ended_by": "stuck", "ended_reason": "stuck", "verified": False,
            "checks": {"slept_by_us": False, "no_blocking_modal": True, "no_hard_failures": True,
                       "crops_watered": True, "day_justified": False},
            "stages": [], "outcomes": [], "ok_steps": 0, "skipped_steps": 0, "failed_steps": 0,
            "final": final(MODAL_DAY),
        }

    def test_same_day_retry_is_one_calendar_day(self):
        rep = self._report([
            day_start(MODAL_DAY),
            self._stuck_end(),
            day_start(MODAL_DAY),
            self._stuck_end(),
            {"event": "finish", "t": 9.5, "code": 1, "verified_streak": 0, "actions": 3,
             "minutes": 0.1},
        ], "same_day.jsonl", days=3)
        sdr = rep["same_day_retries"]
        self.assertEqual(sdr["sessions"], 2)
        self.assertEqual(sdr["distinct_days"], 1, "同一个日历日的两次起跑只能算 1 天")
        self.assertEqual(sdr["retry_lines"], [1, 3])
        text = mod.render_text(rep, 50)
        self.assertIn("同日重试: 2 个会话只有 1 个不同日历日", text)
        self.assertIn("不算跨日、不算多天", text)
        # ended_by=stuck 不是 sleep ⇒ 跨日证据一律 n/a，绝不发 missed:cross_day
        self.assertTrue(all(d["cross_day_verdict"] == "n/a" for d in rep["days"]))
        self.assertNotIn("missed:cross_day", rep["red"]["subjects"])
        self.assertEqual(rep["verified_days"], 0)
        self.assertIn("同一天重复起跑 ×2", " ".join(a["text"] for a in rep["advice"]))

    def test_buy_failure_is_counted_as_failure_not_success(self):
        bad = {"event": "buy", "t": 1.0, "ok": False, "code": "failed",
               "receipt": "item_not_sold: [item_not_sold] (HTTP 200) 商店「SeedShop」里没有「472」。",
               "reason": "没成交：物品 0→0，钱 956→956；回执=item_not_sold"}
        rep = self._report(integrity_ledger(extra_events=[
            dict(bad), dict(bad, t=2.0),
        ]), "buy_bad.jsonl")
        b = rep["buy"]
        self.assertEqual((b["total"], b["ok"], b["failed"]), (2, 0, 2))
        self.assertEqual(b["codes"], {"item_not_sold": 2},
                         "回执码优先于桥的粗分类 code=failed")
        self.assertTrue(b["same_receipt"])
        self.assertEqual(b["failed_lines"], [2, 3])
        text = mod.render_text(rep, 50)
        self.assertIn("购买: 2 次（成功 0 / 没成交 2）", text)
        self.assertIn("item_not_sold×2", text)
        self.assertIn("守卫死锁嫌疑", text)
        self.assertIn("购买没成交 ×2", " ".join(a["text"] for a in rep["advice"]))

    def test_buy_success_is_not_flagged(self):
        rep = self._report(integrity_ledger(extra_events=[
            {"event": "buy", "t": 1.0, "ok": True, "code": "ok", "receipt": "ok",
             "reason": "买成了"},
        ]), "buy_ok.jsonl")
        b = rep["buy"]
        self.assertEqual((b["ok"], b["failed"], b["unknown"]), (1, 0, 0))
        self.assertFalse(b["same_receipt"])
        text = mod.render_text(rep, 50)
        self.assertIn("购买: 1 次（成功 1 / 没成交 0）", text)
        self.assertNotIn("守卫死锁嫌疑", text)
        self.assertNotIn("购买没成交", " ".join(a["text"] for a in rep["advice"]))

    @unittest.skipUnless(os.path.exists(RUN6), "run6 账本不在（logs\\longrun-3day-llm-run6.jsonl）")
    def test_real_run6_buy_and_unmapped(self):
        rep = report_for(RUN6, days=3)
        self.assertEqual(rep["unmapped_events"], {},
                         "run6 的每个事件名都必须有桶（含 clear_dead_scope / buy / idle）")
        b = rep["buy"]
        self.assertEqual((b["total"], b["ok"], b["failed"]), (6, 0, 6))
        self.assertEqual(b["codes"], {"item_not_sold": 6})
        self.assertTrue(b["same_receipt"])
        self.assertEqual(rep["same_day_retries"]["distinct_days"], 1)
        self.assertEqual(rep["verified_days"], 0)
        text = mod.render_text(rep, 50)
        self.assertIn("item_not_sold×6", text)
        self.assertIn("同日重试", text)
        self.assertIn("守卫死锁嫌疑", text)


class TestSeedEconomy(unittest.TestCase):
    """task-70 / task-67：种子经济三事件（没货 / 买不起 / 买不到结论当天失效留痕）。

    政策：归**同一类**（种子/经济）但分开计数；三者都**不是硬失败**；真正的指纹是
    「买不到却没有失效留痕 ⇒ 守卫还在要『去买』」= run6 那种 stuck 死锁。
    """

    NO_SEED = {"event": "no_seed_for_sale", "t": 1.0, "code": "no_seed_for_sale",
               "money": 956, "seed_price": 20, "keep_factor": 3,
               "offers": "Melon Seeds(80g)、Tomato Seeds(50g)", "note": "今天不再发起 buy"}
    CANNOT = {"event": "cannot_afford", "t": 2.0, "code": "cannot_afford",
              "money": 10, "seed_price": 80, "keep_factor": 3,
              "offers": "Melon Seeds(80g)", "note": "今天不再发起 buy"}
    UNAVAIL = {"event": "seed_unavailable_today", "t": 3.0, "code": "no_seed_for_sale",
               "money": 956, "seed_price": 20, "note": "不再把「该去买种子」当活"}

    def _report(self, events, name, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=days)

    def test_seed_events_have_buckets_and_are_not_unmapped(self):
        for n in ("no_seed_for_sale", "cannot_afford", "seed_unavailable_today"):
            self.assertIn(n, mod.EVENT_BUCKETS, f"brain 会发 {n}，没有桶就会静默消失")
        rep = self._report(integrity_ledger(extra_events=[
            dict(self.NO_SEED), dict(self.CANNOT), dict(self.UNAVAIL),
        ]), "seed_buckets.jsonl")
        self.assertEqual(rep["unmapped_events"], {}, "三个种子事件都必须有桶")
        ev = rep["events"]
        self.assertEqual(ev["no_seed_for_sale"], 1)
        self.assertEqual(ev["cannot_afford"], 1)
        self.assertEqual(ev["seed_unavailable_today"], 1)
        text = mod.render_text(rep, 50)
        for key in ("no_seed_for_sales=1", "cannot_affords=1", "seed_unavailable_today=1"):
            self.assertIn(key, text, "新事件计数要点名（不许静默）")

    def test_seed_economy_grouped_but_counted_separately(self):
        rep = self._report(integrity_ledger(extra_events=[
            dict(self.NO_SEED), dict(self.CANNOT), dict(self.CANNOT, t=2.5), dict(self.UNAVAIL),
        ]), "seed_grouped.jsonl")
        se = rep["seed_economy"]
        self.assertEqual(se["total"], 4)
        self.assertEqual((se["no_seed_for_sale"], se["cannot_afford"],
                          se["seed_unavailable_today"]), (1, 2, 1),
                         "同属种子经济但三个计数必须分开（不许互相掩护）")
        self.assertEqual(se["money"], 956)
        self.assertEqual(se["seed_price"], 20)
        self.assertIn("Melon Seeds(80g)", se["offers"])
        self.assertFalse(se["deadlock_risk"], "有当天失效留痕 ⇒ 不是死锁形态")
        text = mod.render_text(rep, 50)
        self.assertIn("种子经济: 买不到 3 次（没货 1 / 买不起 2）", text)
        self.assertIn("seed_unavailable_today 1 次", text)
        self.assertNotIn("守卫可能还在要", text)
        self.assertIn("种子经济 ×4", " ".join(a["text"] for a in rep["advice"]))

    def test_missing_seed_unavailable_is_deadlock_risk(self):
        rep = self._report(integrity_ledger(extra_events=[
            dict(self.NO_SEED), dict(self.NO_SEED, t=1.5),
        ]), "seed_deadlock.jsonl")
        se = rep["seed_economy"]
        self.assertEqual((se["no_seed_for_sale"], se["seed_unavailable_today"]), (2, 0))
        self.assertTrue(se["deadlock_risk"], "买不到却没有失效留痕 ⇒ run6 死锁形态")
        text = mod.render_text(rep, 50)
        self.assertIn("守卫可能还在要「去买」", text)
        advice = " ".join(a["text"] for a in rep["advice"])
        self.assertIn("让「该去买种子」这条守卫理由当天失效", advice)
        self.assertFalse([s for s in rep["red"]["subjects"] if "seed" in s],
                         "种子事件本身不是红（买不到是环境事实）")

    def test_no_seed_events_means_no_line_and_no_advice(self):
        rep = self._report(integrity_ledger(day_end_overrides={
            "verified": True, "ended_reason": "night",
            "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                       "crops_watered": True, "day_justified": True, "watered_outdoor": True,
                       "no_unmet_stages": True},
            "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0,
                            "scope": "farm"},
        }), "seed_absent.jsonl")
        se = rep["seed_economy"]
        self.assertEqual(se["total"], 0)
        self.assertFalse(se["deadlock_risk"])
        text = mod.render_text(rep, 50)
        self.assertNotIn("种子经济:", text, "没有事件就不许编造这一行")
        self.assertNotIn("种子经济", " ".join(a["text"] for a in rep["advice"]))
        self.assertEqual(rep["red"]["total"], 0, "干净账本不该因为缺种子事件而变红")


class TestReachabilityAndOpenPath(unittest.TestCase):
    """task-76 / task-68：可达性/开路五事件（encircled 三级留痕 + frontier_clear + clear_neighbor）。

    政策：与 `unreachable`（物理走不到）**分开计数**；整类**没有硬闸门**（不存在
    `encircled_within_bound`）⇒ 一律不判红、不并进"该做没做"；价值是让 run6 那种
    「`stuck` + 成功动作 0 步 + 开路 `acted=false`」的**零动作收工**一眼可见。
    """

    ENC1 = {"event": "encircled", "t": 1.0, "tile": [61, 20], "action": "clear",
            "stage": "clear_area", "zone": "field_se", "reason": "四邻没有可站+可清的突破口"}
    ENC2 = {"event": "encircled", "t": 2.0, "tile": [62, 20], "action": "clear",
            "stage": "clear_area", "zone": "field_se", "reason": "同上"}
    ENC_STAGE = {"event": "encircled_stage", "t": 3.0, "stage": "clear_area", "zone": "field_se",
                 "tiles": 2, "in_leftover": 2, "coords": [[61, 20], [62, 20]], "note": "被围住"}
    ENC_SUM = {"event": "encircled_summary", "t": 8.0, "count": 2, "attempted": 42, "engaged": 7,
               "tiles": [[61, 20], [62, 20]], "note": "只记证据"}
    FRONTIER_FAIL = {"event": "frontier_clear", "t": 4.0, "tile": [70, 20], "acted": False,
                     "attempt": 1, "limit": 20, "why": "目标都够不着", "note": ""}
    FRONTIER_FAIL2 = dict(FRONTIER_FAIL, t=4.5, tile=[71, 20], attempt=2)
    FRONTIER_OK = {"event": "frontier_clear", "t": 5.0, "tile": [72, 20], "acted": True,
                   "attempt": 3, "limit": 20, "why": "开路", "note": ""}
    NEIGHBOR = {"event": "clear_neighbor", "t": 6.0, "stage": "clear_area", "zone": "field_se",
                "opens": 1, "targets": [{"target": [61, 20]}], "note": "为开路清邻格"}

    def _report(self, events, name, overrides=None, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        body = integrity_ledger(extra_events=list(events),
                                day_end_overrides=dict(overrides or {}))
        return report_for(write_ledger(tmp.name, name, body), days=days)

    def test_five_events_have_buckets_and_are_not_unmapped(self):
        for n in ("encircled", "encircled_stage", "encircled_summary",
                  "frontier_clear", "clear_neighbor"):
            self.assertIn(n, mod.EVENT_BUCKETS, f"brain 会发 {n}，没有桶就会静默消失")
        rep = self._report([self.ENC1, self.ENC2, self.ENC_STAGE, self.ENC_SUM,
                            self.FRONTIER_FAIL, self.FRONTIER_FAIL2, self.NEIGHBOR],
                           "reach_buckets.jsonl",
                           overrides={"encircled": 2, "encircled_tiles": [[61, 20], [62, 20]]})
        self.assertEqual(rep["unmapped_events"], {}, "五个事件都必须有桶")
        ev = rep["events"]
        self.assertEqual(ev["encircled"], 2)
        self.assertEqual(ev["encircled_stage"], 1)
        self.assertEqual(ev["encircled_summary"], 1)
        self.assertEqual(ev["frontier_clear"], 2)
        self.assertEqual(ev["clear_neighbor"], 1)
        text = mod.render_text(rep, 50)
        for key in ("encircled=2", "encircled_stages=1", "encircled_summaries=1",
                    "frontier_clears=2", "clear_neighbors=1"):
            self.assertIn(key, text, "新事件计数必须点名（不许静默）")

    def test_encircled_is_info_only_and_separate_from_unreachable(self):
        rep = self._report([self.ENC1, self.ENC2, self.ENC_STAGE, self.ENC_SUM],
                           "reach_info.jsonl",
                           overrides={"encircled": 2, "encircled_tiles": [[61, 20], [62, 20]],
                                      "unreachable": 42, "unreachable_bound": 8,
                                      "unreachable_exempt": 8})
        reach = rep["reachability"]
        self.assertEqual(reach["encircled_events"], 2)
        self.assertEqual(reach["encircled_tile_count"], 2)
        self.assertEqual(reach["encircled_count"], 2)
        self.assertEqual(reach["encircled_engaged"], 7)
        env = rep["env_inconclusive"]
        self.assertIn("unreachable_engaged", env, "task-68 的 engaged 只作证据，也要可见")
        self.assertEqual(env["unreachable_count"], 42, "被围住不许并进不可达计数")
        self.assertFalse([s for s in rep["red"]["subjects"] if "encircled" in s],
                         "可达性/开路没有硬闸门 ⇒ 一律不判红")
        text = mod.render_text(rep, 50)
        self.assertIn("可达性/开路:", text)
        self.assertIn("被围住 2 次 / 2 格", text)
        advice = " ".join(a["text"] for a in rep["advice"])
        self.assertIn("不进不可达豁免", advice)

    def test_frontier_clear_all_failed_is_visible(self):
        rep = self._report([self.ENC1, self.FRONTIER_FAIL, self.FRONTIER_FAIL2],
                           "reach_frontier_fail.jsonl",
                           overrides={"encircled": 1, "encircled_tiles": [[61, 20]]})
        reach = rep["reachability"]
        self.assertEqual((reach["frontier_clear_attempts"], reach["frontier_clear_acted"],
                          reach["frontier_clear_failed"]), (2, 0, 2))
        text = mod.render_text(rep, 50)
        self.assertIn("开路全部 acted=false", text)
        self.assertIn("至少一轮零动作", text)
        advice = " ".join(a["text"] for a in rep["advice"])
        self.assertIn("想清但没清掉", advice)
        self.assertFalse([s for s in rep["red"]["subjects"] if "frontier" in s],
                         "开路失败是信息项，不是红")

    def test_frontier_clear_success_and_clear_neighbor_opens(self):
        rep = self._report([self.ENC1, self.FRONTIER_OK, self.NEIGHBOR],
                           "reach_frontier_ok.jsonl")
        reach = rep["reachability"]
        self.assertEqual((reach["frontier_clear_attempts"], reach["frontier_clear_acted"],
                          reach["frontier_clear_failed"]), (1, 1, 0))
        self.assertEqual(reach["clear_neighbor_events"], 1)
        self.assertEqual(reach["clear_neighbor_opens"], 1)
        text = mod.render_text(rep, 50)
        self.assertIn("真清掉 1 / 没清掉 0", text)
        self.assertIn("为开路清邻格 opens=1", text)
        self.assertNotIn("开路全部 acted=false", text)

    def test_zero_action_stuck_day_is_named(self):
        stages = [{"stage": "clear_dead", "tiles": 30, "ok": 0, "skipped": 0, "failed": 0,
                   "proven_inert": 0, "env_block": 0, "inconclusive": 0, "stopped": False,
                   "leftover": 30}]
        rep = self._report([self.ENC1, self.ENC2, self.FRONTIER_FAIL],
                           "reach_zero_action.jsonl",
                           overrides={"ended_by": "stuck", "ended_reason": "stuck",
                                      "verified": False, "stages": stages, "ok_steps": 0,
                                      "encircled": 2,
                                      "encircled_tiles": [[61, 20], [62, 20]]})
        reach = rep["reachability"]
        self.assertEqual(len(reach["zero_action_days"]), 1, "stuck + 成功动作 0 步要点名")
        text = mod.render_text(rep, 50)
        self.assertIn("零动作收工", text)
        advice = " ".join(a["text"] for a in rep["advice"])
        self.assertIn("零动作收工", advice)
        self.assertFalse([s for s in rep["red"]["subjects"] if "encircled" in s or "frontier" in s],
                         "零动作收工是信息项（改由 verify-run3 的 problem 口径判验收）")

    SF_OK = {"event": "stuck_flush", "t": 9.0, "ok": True, "count": 1, "limit": 3,
             "day_after": [1, "summer", 5], "detail": "sleep",
             "note": "绕 sleep_guard 有界翻篇，让整轮继续跑下一天"}
    SF_SKIP = {"event": "stuck_flush_skipped", "t": 9.5, "reason": "eventUp=true",
               "note": "task-41：游戏事件挂住必须人来处理"}
    SF_SKIP_MENU = {"event": "stuck_flush_skipped", "t": 9.6, "reason": "activeMenu=SaveGameMenu",
                    "note": "task-11：存档类模态只等不关"}
    SF_RESNAP = {"event": "stuck_flush_resnap_failed", "t": 9.7, "error": "bridge timeout"}

    def test_stuck_flush_events_are_mapped_and_visible(self):
        for n in ("stuck_flush", "stuck_flush_skipped", "stuck_flush_resnap_failed"):
            self.assertIn(n, mod.EVENT_BUCKETS, f"brain 会发 {n}（task-73），没有桶就会静默消失")
        rep = self._report([self.SF_OK, self.SF_SKIP], "stuck_flush.jsonl",
                           overrides={"ended_by": "stuck", "ended_reason": "stuck",
                                      "verified": False})
        self.assertEqual(rep["unmapped_events"], {}, "task-73 三个事件都必须有桶")
        sf = rep["stuck_flush"]
        self.assertEqual((sf["events"], sf["ok"], sf["not_ok"], sf["skipped"]), (1, 1, 0, 1))
        self.assertEqual(sf["skip_reasons"], ["eventUp=true"])
        text = mod.render_text(rep, 50)
        self.assertIn("stuck 翻篇: 1 次（睡成功 1 / 没成功 0）；被跳过 1 次（原因 eventUp=true）", text)
        self.assertIn("有跳过 ⇒ 那天没能睡过去", text)
        self.assertFalse([s for s in rep["red"]["subjects"] if "stuck_flush" in s],
                         "有界翻篇是信息项：本日仍如实 stuck ⇒ 绝不判红")

    def test_stuck_flush_resnap_failure_and_skip_reasons_are_named(self):
        rep = self._report([self.SF_OK, self.SF_SKIP_MENU, self.SF_RESNAP],
                           "stuck_flush_resnap.jsonl",
                           overrides={"ended_by": "stuck", "ended_reason": "stuck",
                                      "verified": False})
        sf = rep["stuck_flush"]
        self.assertEqual(sf["skip_reasons"], ["activeMenu=SaveGameMenu"])
        self.assertEqual(sf["resnap_failed"], 1)
        text = mod.render_text(rep, 50)
        self.assertIn("翻篇后重观测失败 1 次", text)
        advice = " ".join(a["text"] for a in rep["advice"])
        self.assertIn("绝不放宽验收", advice, "翻篇不许被读成'放行了'")
        self.assertNotIn("stuck_flush", rep["red"]["subjects"])


class TestBoundBasisAccounting(unittest.TestCase):
    """task-80：上界基数 = `bound_basis = attempted − encircled`，**绝不采信比自算更大的账本上界**。

    背景：deputy 的伪造账本 V5 把 `encircled` 步计进 `attempted` ⇒ 20% 上界被抬到 200
    ⇒ 200 格真不可达被豁免、exit 0。与 `tools/verify-run3.py`（`2ce830b`）同向。
    """

    def _report(self, name, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, integrity_ledger(**kw)), days=1)

    def test_deputy_v5_inflated_basis_is_red(self):
        """V5 打法：encircled 撑大 attempted，账本 bound_basis 比自算大 ⇒ 判红、绝不采信。"""
        rep = self._report("v5.jsonl", day_end_overrides={
            "attempted": 1000, "encircled": 800, "bound_basis": 800, "unreachable_bound": 160,
            "unreachable": 160, "unreachable_exempt": 160, "unreachable_tiles": [[1, 1]],
        })
        self.assertIn("missed:bound_inflated", subjects(rep["categories"]["missed"]))
        env = rep["env_inconclusive"]
        self.assertEqual(env["unreachable_bound_status"], "inflated")
        self.assertEqual(env["bound_basis_ledger"], 800)
        self.assertEqual(env["unreachable_basis_self"], 200)  # 1000 − 800
        self.assertEqual(env["unreachable_bound_self"], 40)   # max(5, 20%×200)
        text = mod.render_text(rep, 50)
        self.assertIn("missed:bound_inflated", text)

    def test_ledger_bound_bigger_than_self_bound_is_red(self):
        """账本没写 bound_basis，但上界比自算大 ⇒ 同样判红。"""
        rep = self._report("big-bound.jsonl", day_end_overrides={
            "attempted": 42, "encircled": 2, "unreachable_bound": 20,
            "unreachable": 20, "unreachable_exempt": 8, "unreachable_tiles": [[1, 1]],
        })
        self.assertIn("missed:bound_inflated", subjects(rep["categories"]["missed"]))
        self.assertEqual(rep["env_inconclusive"]["unreachable_bound_self"], 8)

    def test_same_basis_is_clean_and_rendered(self):
        rep = self._report("ok.jsonl",
                           extra_events=[{"event": "unreachable", "t": 5.0, "tile": [1, 1],
                                          "action": "clear", "stage": "clear_area",
                                          "zone": "field_ne", "reason": "四邻都站不过去"}],
                           day_end_overrides={
            "attempted": 42, "encircled": 2, "bound_basis": 40, "unreachable_bound": 8,
            "unreachable": 3, "unreachable_exempt": 3, "unreachable_tiles": [[1, 1]],
            "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                       "crops_watered": True, "day_justified": True,
                       "unreachable_within_bound": True, "no_unmet_stages": True},
        })
        self.assertNotIn("missed:bound_inflated", subjects(rep["categories"]["missed"]))
        self.assertEqual(rep["env_inconclusive"]["unreachable_bound_status"], "ok")
        self.assertIn("bound_basis=40（自算基数 40、上界 8）", mod.render_text(rep, 50))

    def test_old_ledger_without_basis_is_undecidable_not_red(self):
        """run6 等旧账本没有 bound_basis ⇒ 只记【无法判定】，不许当 0、不许当通过。"""
        rep = self._report("old.jsonl")
        self.assertNotIn("missed:bound_inflated", subjects(rep["categories"]["missed"]))
        self.assertIsNone(rep["env_inconclusive"]["bound_basis_ledger"])
        undec = " ".join(str(u) for u in rep["undecidable"])
        self.assertIn("day_end.bound_basis", undec)

    def test_refused_side_uses_the_same_basis(self):
        """refused 与 unreachable 共用同一基数；账本 refused_bound 比自算大 ⇒ 也判红。"""
        rep = self._report("refused.jsonl", day_end_overrides={
            "attempted": 42, "encircled": 0, "refused_bound": 30,
            "refused": 30, "refused_exempt": 8, "refused_tiles": [[2, 2]],
        })
        self.assertIn("missed:bound_inflated", subjects(rep["categories"]["missed"]))
        self.assertEqual(rep["env_inconclusive"]["refused_bound_status"], "inflated")

    def test_caliber_text_never_says_20pct_attempted(self):
        """口径文字必须改成 bound_basis：报告里不许再出现"20% × attempted"。”"""
        rep = self._report("text.jsonl", day_end_overrides={
            "attempted": 42, "encircled": 2, "bound_basis": 40, "unreachable_bound": 8,
        })
        text = mod.render_text(rep, 50)
        self.assertNotIn("20%×attempted", text)
        self.assertNotIn("20% × attempted", text)
        self.assertIn("20%×bound_basis", text)
        self.assertIn("被围住的格不参与起界", text)


class TestWindowAndSettledClassification(unittest.TestCase):
    """task-88：窗口降级（窗口外的日级红 → history_problems，不进 rc）/"瞬间态已结清"/
    finish 的达标目标 = 目标窗口 / `seed_gate` 钱不够不是购买任务失败。"""

    RUN7 = os.path.join(ROOT, "logs", "longrun-3day-llm-run7.jsonl")

    def _day_events(self, day, *, verified, stage_ok=None, checks_over=None, extra=()):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": verified,
                  "watered_outdoor": True}
        checks.update(checks_over or {})
        stages = ([{"stage": "clear_area", "ok": stage_ok, "skipped": 0, "failed": 0,
                    "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}]
                  if stage_ok else [])
        end = {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": "night", "verified": verified, "checks": checks,
               "stages": stages, "outcomes": [], "ok_steps": stage_ok or 0,
               "skipped_steps": 0, "failed_steps": 0, "notes": [], "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1, window=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=days, window=window)

    def test_out_of_window_red_becomes_history_and_exit_goes_clean(self):
        events = self._day_events([1, "summer", 3], verified=False,
                                  checks_over={"crops_watered": False})
        for dom in (4, 5, 6):
            events += self._day_events([1, "summer", dom], verified=True, stage_ok=5)
        rep = self._report(events, "win3.jsonl", days=3, window=3)
        self.assertTrue(rep["window"]["active"], "尾部连续 3 天 VERIFIED ⇒ 窗口生效")
        self.assertEqual(rep["red"]["total"], 0, "窗口外的日级红不进退出码")
        self.assertIn("missed:check:crops_watered", rep["history_problems"]["subjects"])
        self.assertEqual(rep["history_problems"]["total"], len(rep["history_problems"]["items"]))
        text = mod.render_text(rep, 50)
        self.assertIn("窗口外历史问题", text)
        self.assertIn("窗口内红 0 条", text)
        # `--window 0` = task-88 之前的旧行为：同一条红照旧 fatal
        old = self._report(events, "win0.jsonl", days=3, window=0)
        self.assertGreater(old["red"]["total"], 0)
        self.assertEqual(old["history_problems"]["total"], 0)

    def test_short_streak_keeps_reds_fatal(self):
        events = self._day_events([1, "summer", 3], verified=False,
                                  checks_over={"crops_watered": False})
        events += self._day_events([1, "summer", 4], verified=False,
                                   checks_over={"crops_watered": False})
        events += self._day_events([1, "summer", 5], verified=True, stage_ok=5)
        events += self._day_events([1, "summer", 6], verified=True, stage_ok=5)
        rep = self._report(events, "streak2.jsonl", days=3, window=3)
        self.assertEqual(rep["window"]["tail_streak"], 2)
        self.assertFalse(rep["window"]["active"], "连续 VERIFIED < 窗口 ⇒ 不降级")
        self.assertGreater(rep["red"]["total"], 0)
        self.assertEqual(rep["history_problems"]["total"], 0)

    def test_global_red_is_never_demoted(self):
        events = self._day_events([1, "summer", 3], verified=False,
                                  checks_over={"crops_watered": False})
        # 账目自相矛盾（全局红）：failed_steps 与 stages[].failed 的差额无 env/inconclusive 解释
        events[-1]["failed_steps"] = 3
        events[-1]["stages"] = [{"stage": "clear_area", "ok": 0, "failed": 0,
                                 "env_block": 0, "inconclusive": 0, "leftover": 3}]
        for dom in (4, 5, 6):
            events += self._day_events([1, "summer", dom], verified=True, stage_ok=5)
        rep = self._report(events, "global.jsonl", days=3, window=3)
        self.assertTrue(rep["window"]["active"])
        self.assertIn("missed:stage_account", rep["red"]["subjects"],
                      "全局红（账目自相矛盾）永远 fatal")
        self.assertIn("missed:check:crops_watered", rep["history_problems"]["subjects"])

    def test_settled_momentary_event_is_info_only(self):
        events = self._day_events([1, "summer", 3], verified=True, stage_ok=5, extra=[
            {"event": "stage_exhausted", "t": 4.0, "stage": "clear_area", "leftover": 2,
             "capped": 0, "tiles": [[61, 26]]},
        ])
        rep = self._report(events, "settled.jsonl", days=1)
        self.assertEqual(rep["red"]["total"], 0, "瞬间态事件被同日结清 ⇒ 不进 rc")
        self.assertIn("missed:stage_exhausted", rep["settled"]["subjects"])
        self.assertIn("已结清", mod.render_text(rep, 50))
        self.assertIn("已结清：当天 VERIFIED",
                      " ".join(str(i["summary"]) for i in rep["settled"]["items"]))

    def test_settled_not_applied_when_day_not_settled(self):
        events = self._day_events([1, "summer", 3], verified=False,
                                  checks_over={"no_unmet_stages": False}, extra=[
            {"event": "stage_exhausted", "t": 4.0, "stage": "clear_area", "leftover": 2,
             "capped": 0, "tiles": [[61, 26]]},
        ])
        rep = self._report(events, "notsettled.jsonl", days=1)
        self.assertIn("missed:stage_exhausted", rep["red"]["subjects"])
        self.assertEqual(rep["settled"]["total"], 0)

    def test_finish_self_report_uses_target_window(self):
        # 账本记录 7 天（窗口上限 = 账本天数），finish 自述 streak=3：
        #   --window 3 ⇒ 目标 3、streak 3 达标 ⇒ 不报；
        #   --window 7 ⇒ 目标 7 > streak 3 ⇒ 自述"code=0 达标"不成立 ⇒ 报。
        finish = {"event": "finish", "t": 20.0, "code": 0, "verified_streak": 3, "actions": 9,
                  "minutes": 1.0, "stages_seen": ["clear_area"]}
        events = []
        for dom in range(3, 10):
            events += self._day_events([1, "summer", dom], verified=True, stage_ok=5)
        events.append(finish)
        rep3 = self._report(events, "fin3.jsonl", days=3, window=3)
        self.assertNotIn("wasted:finish_incoherent", rep3["red"]["subjects"],
                         "streak 3 >= 目标窗口 3 ⇒ 不该报自述不自洽")
        rep7 = self._report(events, "fin7.jsonl", days=7, window=7)
        self.assertIn("wasted:finish_incoherent", rep7["red"]["subjects"],
                      "目标窗口 7 > streak 3 ⇒ 自述达标不成立")

    def test_seed_gate_afford_is_not_a_failed_purchase(self):
        events = self._day_events([1, "summer", 3], verified=True, stage_ok=5, extra=[
            {"event": "seed_gate", "t": 5.0, "seeds": 0, "money": 14, "seed_price": 20,
             "tillable": 12},
        ])
        rep = self._report(events, "seed.jsonl", days=1)
        se = rep["seed_economy"]
        self.assertEqual(se["seed_gate"], 1)
        self.assertEqual(se["afford_blocked"], 1)
        self.assertEqual(se["afford_blocked_lines"], [2])
        text = mod.render_text(rep, 50)
        self.assertIn("缺种子钱（money=14 < seed_price=20）", text)
        self.assertIn("未发起购买，不是任务失败", text)
        self.assertEqual(rep["buy"]["total"], 0, "run7 没有 buy 事件")
        self.assertEqual(rep["red"]["total"], 0, "买不起不是失败，不许判红")
        advice = " ".join(str(a["text"]) for a in rep["advice"])
        self.assertIn("不是任务失败", advice)

    @unittest.skipUnless(os.path.isfile(os.path.join(ROOT, "logs", "longrun-3day-llm-run7.jsonl")),
                         "缺少 run7 账本")
    def test_real_run7_window_switch_keeps_history(self):
        rep3 = report_for(self.RUN7, days=7, top=0)
        self.assertEqual(rep3["window"]["days"], 3)
        self.assertEqual(rep3["red"]["total"], 0, "默认窗口 3：run7 是达标运行，红必须为 0")
        self.assertGreater(rep3["history_problems"]["total"], 100)
        self.assertIn("missed:check:watered_outdoor", rep3["history_problems"]["subjects"])
        rep7 = report_for(self.RUN7, days=7, top=0, window=7)
        self.assertFalse(rep7["window"]["active"])
        self.assertEqual(rep7["history_problems"]["total"], 0)
        self.assertGreater(sum(1 for ln in rep7["red"]["lines"] if 435 <= ln <= 1013), 50,
                           "summer 6 的历史红条不许因为窗口切换而消失")


class TestSurplusSellAccounting(unittest.TestCase):
    """task-91 / task-55：盈余材料换种子钱（`surplus_sell` / `surplus_sell_skip` / `sell` / `cannot_afford`）。

    政策：`cannot_afford` / `surplus_sell_skip` / `below_keep` **都不是失败**；`sell` 成交当天
    `money` 不变是**设计**（钱等下一次 `NewDay` 结算）⇒ 一律不判红；漂移测试要求有桶（不许静默）。
    """

    SELL_OK = {"event": "sell", "t": 1.0, "ok": True, "code": "ok", "strategy": "surplus_materials",
               "slot": 3, "qid": "(O)390", "stack": 12, "keep": 3, "below_keep": False,
               "trigger": {"money": 14, "threshold": 20, "emptyDirt": 0},
               "before": {"slot": 3, "qid": "(O)390", "stack": 12, "money": 14},
               "after": {"slot": 3, "qid": None, "stack": 0, "money": 14},
               "reason": "已出货", "receipt": "ok"}
    SURPLUS = {"event": "surplus_sell", "t": 2.0, "ok": True, "strategy": "surplus_materials",
               "keep": 3, "slots": [3], "whitelist": ["(O)390"], "items": [],
               "trigger": {"money": 14, "threshold": 20, "emptyDirt": 0},
               "sold": 12, "ok_count": 1, "fail_count": 0, "below_keep": False,
               "note": "钱要等下一次 NewDay 才由游戏结算（当天 money 不变是正常的）"}
    SKIP = {"event": "surplus_sell_skip", "t": 3.0, "short": 6, "below_keep": True,
            "reason": "唯一一大叠也补不上种子钱（short=6g）",
            "trigger": {"money": 14, "threshold": 20, "emptyDirt": 0}, "items": []}
    CANNOT = {"event": "cannot_afford", "t": 4.0, "code": "cannot_afford", "money": 12,
              "seed_price": 80, "keep_factor": 3, "offers": "Melon Seeds(80g)",
              "note": "今天不再发起 buy"}

    def _report(self, events, name, *, days=1, window=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=days, window=window)

    def _day(self, day, *, verified=True, stage_ok=5, extra=(), final_money=14):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": verified,
                  "watered_outdoor": True}
        fin = final(nxt)
        fin["money"] = final_money
        end = {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": "night", "verified": verified, "checks": checks,
               "stages": [{"stage": "clear_area", "ok": stage_ok, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": stage_ok, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": fin,
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def test_surplus_events_have_buckets_and_are_never_red(self):
        for n in ("surplus_sell", "surplus_sell_skip"):
            self.assertIn(n, mod.EVENT_BUCKETS, f"brain 会发 {n}，没有桶就会静默消失")
        events = self._day([1, "summer", 3], extra=[dict(self.SELL_OK), dict(self.SURPLUS),
                                                    dict(self.SKIP), dict(self.CANNOT)])
        rep = self._report(events, "surplus_buckets.jsonl")
        self.assertEqual(rep["unmapped_events"], {}, "盈余卖出事件必须有桶")
        self.assertEqual(rep["events"]["surplus_sell"], 1)
        self.assertEqual(rep["events"]["surplus_sell_skip"], 1)
        self.assertEqual(rep["red"]["total"], 0,
                         "below_keep / skip / cannot_afford / 当天钱不变都不是失败 ⇒ 不判红")
        text = mod.render_text(rep, 50)
        self.assertIn("surplus_sells=1", text)
        self.assertIn("surplus_sell_skips=1", text)

    def test_sell_money_unchanged_on_same_day_is_by_design(self):
        ev = dict(self.SELL_OK)
        ev["after"] = dict(ev["after"], money=14)   # 当天钱一分没变（设计）
        rep = self._report(self._day([1, "summer", 3], extra=[ev, dict(self.SURPLUS)]),
                           "surplus_money.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        sl = rep["sell"]
        self.assertEqual((sl["total"], sl["ok"], sl["failed"]), (1, 1, 0))
        self.assertEqual(sl["surplus_sold"], 12)
        self.assertEqual(sl["money_at_sell"], 14)
        text = mod.render_text(rep, 50)
        self.assertIn("种子经济/出货: sell 1 次（成交 1 / 失败 0", text)
        self.assertIn("sold 12 件", text)

    def test_sell_then_next_day_without_buy_lists_two_candidates_only(self):
        day1 = self._day([1, "summer", 3], extra=[dict(self.SELL_OK), dict(self.SURPLUS)])
        gate = {"event": "seed_gate", "t": 20.0, "stage": "till_area", "seeds": 0, "money": 14,
                "seed_price": 20, "zone": "field_ne", "in_plot": False}
        day2 = self._day([1, "summer", 4], extra=[gate], final_money=14)
        rep = self._report(day1 + day2, "surplus_nobuy.jsonl", days=2)
        sl = rep["sell"]
        self.assertEqual(len(sl["sold_days_with_no_buy_next"]), 1,
                         "第 1 天卖出、第 2 天 buy 0 ⇒ 命中")
        self.assertEqual(rep["buy"]["total"], 0)
        advice = " ".join(str(a["text"]) for a in rep["advice"])
        self.assertIn("钱没到账", advice)
        self.assertIn("货架没有当季种子", advice)
        self.assertIn("不下结论", advice)
        for bad in ("买入失败",):
            self.assertNotIn(bad, advice, "只给候选，不许下结论")
        # "购买任务失败"只允许出现在否定式「不是购买任务失败」里
        self.assertTrue(all(advice[max(0, m.start() - 2):m.start()] == "不是"
                            for m in re.finditer("购买任务失败", advice)),
                        "只给候选，不许把'没买种子'写成购买任务失败")
        text = mod.render_text(rep, 50)
        self.assertIn("卖了但次日 buy 仍 0", text)

    def test_seed_line_combines_sell_buy_and_seed_gate(self):
        day1 = self._day([1, "summer", 3], extra=[dict(self.SELL_OK), dict(self.SURPLUS),
                                                  dict(self.SKIP), dict(self.CANNOT)])
        rep = self._report(day1, "surplus_line.jsonl")
        text = mod.render_text(rep, 50)
        for frag in ("sell 1 次", "surplus_sell 1 次", "surplus_sell_skip 1 次",
                     "short 最大 6g", "buy 0 次", "seed_gate"):
            self.assertIn(frag, text, f"种子经济/出货行要能一眼看到 {frag}")

    @unittest.skipUnless(os.path.isfile(os.path.join(ROOT, "logs", "longrun-3day-llm-run7.jsonl")),
                         "缺少 run7 账本")
    def test_run7_has_no_surplus_events_and_is_still_clean(self):
        rep = report_for(os.path.join(ROOT, "logs", "longrun-3day-llm-run7.jsonl"), days=7, top=0)
        self.assertEqual(rep["sell"]["total"], 0, "run7 早于 task-55，没有 sell 事件")
        self.assertEqual(rep["red"]["total"], 0, "没有这些事件不该引入任何红")


class TestDeadCropsAccounting(unittest.TestCase):
    """task-95 / task-84：死苗不浇水（`dead_crops` / `dry_dead` / `gave_up_tiles`）。

    口径：`dry_dead > 0` 且 `ended_reason` 以 `no_work` 开头 ⇒ 红 `missed:dry_dead_uncleared`；
    `dry_dead` 不是整数 ⇒ 红（账目不可信）；`gave_up_tiles` 非空却自称 VERIFIED ⇒ 红
    `missed:verified_with_gave_up`（本工具比 `tools/verify-run3.py` 严一格：它对 gave_up 只记 info，
    两边相反时以它为准并报 Lead）；字段缺失 ⇒ 只进【无法判定】，**缺失 ≠ 0，绝不当通过**。
    `dead_crops_summary` 必须有桶（不许静默丢弃）。
    """

    SUM_OK = {"event": "dead_crops_summary", "t": 8.0, "dead_crops": 3, "dry_dead": 0,
              "dry_dead_status": "ok", "gave_up": 0, "tiles": [], "note": "死苗不计浇水证据"}
    DEAD_OK = {"dead_crops": 3, "dead_crops_status": "ok", "dry_dead": 0, "dry_dead_status": "ok",
               "gave_up_tiles": []}

    def _report(self, events, name, *, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=days, top=50)

    def _day(self, day, *, verified=True, ended_reason="night", stage_ok=5, extra=(), dead=None):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": verified,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": ended_reason, "verified": verified, "checks": checks,
               "stages": [{"stage": "clear_dead", "ok": stage_ok, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": stage_ok, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        if dead:
            end.update(dead)
        return [day_start(day), *extra, end]

    def test_summary_event_has_bucket_and_is_not_unmapped(self):
        self.assertIn("dead_crops_summary", mod.EVENT_BUCKETS,
                      "brain 会发 dead_crops_summary，没有桶就会静默消失")
        rep = self._report(self._day([1, "summer", 3], extra=[dict(self.SUM_OK)]), "dc_bucket.jsonl")
        self.assertEqual(rep["unmapped_events"], {})
        self.assertEqual(rep["events"]["dead_crops_summary"], 1)

    def test_clean_dead_crops_day_is_not_red_and_visible(self):
        rep = self._report(self._day([1, "summer", 3], dead=dict(self.DEAD_OK)), "dc_clean.jsonl")
        self.assertTrue(rep["dead_crops"]["has_fields"])
        self.assertEqual(rep["red"]["total"], 0, "死苗已清、没有认输格 ⇒ 不判红")
        text = mod.render_text(rep, 50)
        self.assertIn("死苗/放弃格: 枯死 3 格", text)
        self.assertIn("其中没浇 0 格", text)

    def test_dry_dead_with_no_work_reason_is_red(self):
        dead = dict(self.DEAD_OK, dry_dead=1)
        rep = self._report(self._day([1, "summer", 3], ended_reason="no_work:确实找不到可做的活",
                                     dead=dead), "dc_nowork.jsonl")
        self.assertIn("missed:dry_dead_uncleared", rep["red"]["subjects"],
                      "死苗没清却拿 no_work 收工 ⇒ 必须判红（verify-run3.py:803-808 同判 problem）")

    def test_non_int_dry_dead_is_red(self):
        dead = dict(self.DEAD_OK, dry_dead="1")
        rep = self._report(self._day([1, "summer", 3], dead=dead), "dc_bad.jsonl")
        self.assertIn("missed:dry_dead_bad_field", rep["red"]["subjects"],
                      "dry_dead 不是整数 ⇒ 账目不可信，必须判红")

    def test_gave_up_tiles_with_verified_is_warning_not_red(self):
        dead = dict(self.DEAD_OK, gave_up_tiles=[[12, 30]])
        rep = self._report(self._day([1, "summer", 3], dead=dead), "dc_gaveup.jsonl")
        self.assertNotIn("missed:verified_with_gave_up", rep["red"]["subjects"],
                         "Lead m04997：认输格 + VERIFIED 只作警告不判红（认输格当天被解决时是假红）")
        self.assertEqual(rep["red"]["total"], 0)
        self.assertEqual(rep["dead_crops"]["verified_with_gave_up"], [2],
                         "警告行号仍要留下（day_end 在第 2 行）")
        text = mod.render_text(rep, 50)
        self.assertIn("warn:verified_with_gave_up", text, "警告必须在头部一眼可见")
        advice = " ".join(str(a["text"]) for a in rep["advice"])
        self.assertIn("只作警告、不判红", advice, "建议 0m 也要点明它不判红")
        self.assertIn("放弃格非空", advice)

    def test_missing_fields_is_undecidable_never_pass(self):
        rep = self._report(self._day([1, "summer", 3]), "dc_missing.jsonl")
        self.assertFalse(rep["dead_crops"]["has_fields"])
        self.assertEqual(rep["red"]["total"], 0, "字段缺失既不算通过也不算失败 ⇒ 不许判红")
        self.assertIn("缺失 ≠ 0", str(rep["undecidable"]),
                      "缺 task-84 字段要进【无法判定】，绝不能当'没有死苗'通过")
        self.assertIn("<缺失>", mod.render_text(rep, 50))


class TestBagSpaceDeadlock(unittest.TestCase):
    """task-102（`9b09735`）+ task-104：背包空格死锁闭环。

    口径（Lead m05068）：**买不到不是失败** —— `buy_no_space`（没空格）、钱不够、没货架一律不判红；
    `slept_without_work` = 0 农场动作又有活 ⇒ 拒绝睡觉、当天不推进（守卫生效的证据，**不是睡眠失败**）；
    `modal_dismiss_failed` 只点名次数（`tools\\verify-run3.py` 不判它 ⇒ 判红会两边反向）；
    `water_far_skipped` = 人不在户外农场（不扣额度、不认输，不是失败）；
    `free_slots` 缺证据 ⇒ 写 `<缺失>` + 【无法判定】（缺失 ≠ 0）。
    """

    NO_SPACE = {"event": "buy_no_space", "t": 5.0, "item": "472", "price": 20, "attempt": 1,
                "free_slots_status": "ok", "reason": "no_space"}
    SLEPT_NO_WORK = {"event": "slept_without_work", "t": 6.0, "why": "still_work",
                     "farm_actions": 0, "reasons": ["背包没空格"], "note": "0 农场动作 ⇒ 拒绝睡觉"}
    DISMISS_FAILED = {"event": "modal_dismiss_failed", "t": 7.0, "menu": "ShippingMenu",
                      "reason": "bridge error"}
    WATER_FAR_SKIP = {"event": "water_far_skipped", "t": 7.5, "reason": "not_on_farm",
                      "tiles": [[12, 30]], "count": 1, "where": "window"}
    SLOT_SELL = {"event": "surplus_sell", "t": 8.0, "ok": True, "why": "need_slot",
                 "strategy": "surplus_materials", "keep": 10, "sold": 12, "ok_count": 1,
                 "fail_count": 0, "below_keep": False,
                 "trigger": {"money": 188, "freeSlots": 0, "freeSlotsStatus": "ok",
                             "slotsNeeded": 1, "threshold": 200, "emptyDirt": 30}}

    def _report(self, events, name, *, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=days, top=50)

    def _day(self, day, *, extra=(), money=None):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": "night", "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        if money is not None:
            end["final"] = dict(final(nxt), money=money)
        return [day_start(day), *extra, end]

    def test_mechanical_enumeration_has_no_unmapped_event(self):
        """机械枚举 brain 两个文件的 `_journal("…")` 字面量 ⇒ 一个都不许漏桶（task-106 ①）。"""
        src = ""
        for name in ("longrun.py", "farmwork.py"):
            with open(os.path.join(ROOT, "brain", "agentfarm", name), encoding="utf-8") as fh:
                src += fh.read()
        names = sorted(set(re.findall(r'_journal\(\s*"([a-z0-9_]+)"', src)))
        self.assertGreater(len(names), 50, "正则失效？brain 的 journal 事件远不止这些")
        missing = [n for n in names
                   if n not in mod.EVENT_BUCKETS and n not in mod.STRUCTURAL_EVENTS]
        self.assertEqual(missing, [], f"brain 写了但本工具没有桶的事件：{missing}（不许静默丢弃）")

    def test_new_events_have_buckets_and_are_not_unmapped(self):
        for name in ("buy_no_space", "slept_without_work", "modal_dismiss_failed",
                     "water_far_skipped"):
            self.assertIn(name, mod.EVENT_BUCKETS, f"{name} 必须有桶，否则 run8 复核数不到")
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.NO_SPACE),
                                                              dict(self.SLEPT_NO_WORK),
                                                              dict(self.DISMISS_FAILED),
                                                              dict(self.WATER_FAR_SKIP)]),
                           "bag_bucket.jsonl")
        self.assertEqual(rep["unmapped_events"], {})
        for name in ("buy_no_space", "slept_without_work", "modal_dismiss_failed",
                     "water_far_skipped"):
            self.assertEqual(rep["events"][name], 1, f"{name} 要能被数到")

    def test_buy_no_space_is_not_a_failure_and_is_visible(self):
        buy_fail = {"event": "buy", "t": 4.0, "ok": False, "code": "failed",
                    "receipt": "no_inventory_space: [no_inventory_space] (HTTP 200) 背包没空格"}
        rep = self._report(self._day([1, "summer", 5], extra=[dict(buy_fail), dict(self.NO_SPACE),
                                                              dict(self.SLOT_SELL)], money=188),
                           "bag_nospace.jsonl")
        self.assertEqual(rep["red"]["total"], 0,
                         "买不到（没空格）不是失败 ⇒ 绝不判红；腾格卖出当天钱不变也是设计")
        text = mod.render_text(rep, 50)
        for frag in ("种子经济/背包:", "free_slots 0", "buy_no_space 1 次", "腾格卖出 1 次",
                     "买不到不是失败", "100 → 188"):
            self.assertIn(frag, text, f"头部行要能一眼看到 {frag}")
        advice = " ".join(str(a["text"]) for a in rep["advice"])
        self.assertIn("买不到不是失败", advice, "建议 0n 要点明它不是失败")

    def test_old_ledger_without_event_is_recognised_from_receipt_code(self):
        """run8 形态：brain 还没发 `buy_no_space`，只有回执码 `no_inventory_space` ⇒ 也要认出来。"""
        buy_fail = {"event": "buy", "t": 4.0, "ok": False, "code": "failed",
                    "receipt": "no_inventory_space: [no_inventory_space] (HTTP 200) 空格 0"}
        rep = self._report(self._day([1, "summer", 5], extra=[dict(buy_fail)]), "bag_old.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "买不到不是失败 ⇒ 不判红")
        self.assertEqual(rep["bag_space"]["buy_no_space_receipts"], 1)
        text = mod.render_text(rep, 50)
        self.assertIn("回执 no_inventory_space×1", text, "旧账本要从回执码补认，不许看不见")
        self.assertIn("买不到不是失败", " ".join(str(a["text"]) for a in rep["advice"]))

    def test_slept_without_work_is_visible_and_not_red(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.SLEPT_NO_WORK)]),
                           "bag_slept.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "0 动作拒绝睡觉是守卫生效 ⇒ 不判红")
        text = mod.render_text(rep, 50)
        self.assertIn("slept_without_work 1 次", text)
        self.assertIn("不是睡眠失败", text)
        advice = " ".join(str(a["text"]) for a in rep["advice"])
        self.assertIn("拒绝睡觉", advice)
        self.assertIn("不是睡眠失败", advice)

    def test_missing_free_slots_is_undecidable_not_pass(self):
        rep = self._report(self._day([1, "summer", 5]), "bag_missing.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "缺证据既不算通过也不算失败 ⇒ 不许判红")
        text = mod.render_text(rep, 50)
        self.assertIn("free_slots <缺失>", text)
        self.assertIn("free_slots 证据", str(rep["undecidable"]),
                      "缺 free_slots 证据要进【无法判定】（缺失 ≠ 0）")

    def test_modal_dismiss_failed_is_info_not_red(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.DISMISS_FAILED)]),
                           "bag_dismiss.jsonl")
        self.assertEqual(rep["red"]["total"], 0,
                         "verify-run3 不判 modal_dismiss_failed ⇒ 本工具也不判红（免得两边反向）")
        self.assertNotIn("modal_dismiss_failed", rep["red"]["subjects"])
        self.assertIn("modal_dismiss_failed 1 次", mod.render_text(rep, 50))


class TestLlmReviewAndLessons(unittest.TestCase):
    """task-111（Lead m05325）：LLM 收工复盘（task-59）+ 跨日教训库（task-58/82）。

    口径：**"模型没学到东西"不是失败**（空 notes / 空库 / 0 新增 / 复盘失败 / 写失败都只记信息）；
    只有三条完整性红 —— ①`review_llm` 声称成功却 0 条 notes ②教训库条数超上限
    ③教训库读不了/文件损坏。旧账本没有这些事件 ⇒ 头部 `<缺失>` + 【无法判定】（缺失 ≠ 0）。
    """

    REVIEW = {"event": "review_llm", "t": 8.0, "day_key": [1, "summer", 5],
              "notes": ["先清枯死苗再浇水", "别在下雨前买种子"],
              "text": "{\"notes\": [...]}", "usage": {"total_tokens": 123},
              "duration_ms": 900, "model": "deepseek-flash", "rejected": [], "truncated": False,
              "note": "只写 journal 与次日 recent_notes；不参与任何判定"}
    LESSONS = {"event": "lessons", "t": 8.1, "day_key": [1, "summer", 5],
               "added": ["no_inventory_space|buy", "stage_incomplete|till_area"],
               "total": 5, "dropped": 0, "path": "<journal>-lessons.json",
               "note": "只有客观账本事实"}

    def _day(self, day, *, extra=()):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": "night", "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_ledger(tmp.name, name, events)
        self._tmp = tmp
        self._journal_path = path
        rep = report_for(path, days=days, top=50)
        return rep

    def test_five_events_have_buckets_and_are_not_unmapped(self):
        for name in ("review_llm", "review_llm_failed", "lessons", "lessons_load_failed",
                     "lessons_save_failed"):
            self.assertIn(name, mod.EVENT_BUCKETS, f"{name} 必须有桶，否则 run9 复核数不到")
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.REVIEW),
                                                              dict(self.LESSONS)]),
                           "llm_bucket.jsonl")
        self.assertEqual(rep["unmapped_events"], {})
        for name in ("review_llm", "lessons"):
            self.assertEqual(rep["events"][name], 1, f"{name} 要能被数到")

    def test_review_with_notes_is_info_and_visible(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.REVIEW),
                                                              dict(self.LESSONS)]),
                           "llm_ok.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "有 notes 的正常复盘 ⇒ 不判红")
        self.assertEqual(rep["llm_review"]["notes_count"], 2)
        self.assertEqual(rep["llm_review"]["lessons_total"], 5)
        text = mod.render_text(rep, 50)
        self.assertIn("LLM 复盘/教训库:", text)
        self.assertIn("notes 2 条", text)
        self.assertIn("教训库 total 5 条", text)

    def test_review_claims_success_without_notes_is_red(self):
        no_notes = dict(self.REVIEW, notes=[])
        rep = self._report(self._day([1, "summer", 5], extra=[no_notes]), "llm_nonotes.jsonl")
        self.assertIn("missed:review_llm_without_notes", rep["red"]["subjects"])
        self.assertGreaterEqual(rep["red"]["total"], 1)
        text = mod.render_text(rep, 50)
        self.assertIn("复盘声称成功却 0 条 notes", text)
        self.assertIn("LLM 复盘/教训库（task-111）",
                      " ".join(a["text"] for a in rep["advice"]))

    def test_lessons_over_limit_is_red(self):
        over = dict(self.LESSONS, total=21, added=["x|y"])
        rep = self._report(self._day([1, "summer", 5], extra=[over]), "llm_over.jsonl")
        self.assertIn("missed:lessons_over_limit", rep["red"]["subjects"])
        self.assertIn("教训库超上限", mod.render_text(rep, 50))

    def test_corrupt_lessons_file_is_red(self):
        self._report(self._day([1, "summer", 5], extra=[dict(self.LESSONS)]), "llm_corrupt.jsonl")
        # 与 brain `_derive_lessons_path` 同约定：`X.jsonl` ⇒ `X-lessons.json`
        lp = str(self._journal_path)[:-len(".jsonl")] + "-lessons.json"
        with open(lp, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        rep = report_for(self._journal_path, days=1, top=50)
        self.assertEqual(rep["llm_review"]["file_status"], "corrupt")
        self.assertIn("missed:lessons_load_failed", rep["red"]["subjects"])
        self.assertIn("教训库文件损坏", mod.render_text(rep, 50))

    def test_lessons_load_failed_event_is_red(self):
        ev = {"event": "lessons_load_failed", "t": 8.2,
              "path": "<journal>-lessons.json", "error": "read_failed:JSONDecodeError: bad",
              "note": "教训库读不了 ⇒ 本次当作没有教训"}
        rep = self._report(self._day([1, "summer", 5], extra=[ev]), "llm_loadfail.jsonl")
        self.assertIn("missed:lessons_load_failed", rep["red"]["subjects"])
        self.assertIn("教训库读不了", mod.render_text(rep, 50))

    def test_review_failed_and_save_failed_are_info_not_red(self):
        failed = {"event": "review_llm_failed", "t": 8.3, "day_key": [1, "summer", 5],
                  "reason": "llm_timeout", "called": True, "rejected": [],
                  "note": "复盘失败无害：睡觉与跨日照常"}
        save_failed = {"event": "lessons_save_failed", "t": 8.4, "path": "<journal>-lessons.json",
                       "error": "write_failed:PermissionError", "note": "写不进去 ⇒ 跑批照常"}
        rep = self._report(self._day([1, "summer", 5], extra=[failed, save_failed]),
                           "llm_failinfo.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "复盘失败/写失败都是'失败无害' ⇒ 不判红")
        self.assertEqual(rep["llm_review"]["failed_events"], 1)
        self.assertEqual(rep["llm_review"]["save_failed"], 1)
        text = mod.render_text(rep, 50)
        self.assertIn("复盘失败 1 次", text)
        self.assertIn("读写失败 load 0 / save 1", text)

    def test_old_ledger_is_undecidable_not_pass(self):
        rep = self._report(self._day([1, "summer", 5]), "llm_missing.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "缺证据既不算通过也不算失败 ⇒ 不许判红")
        text = mod.render_text(rep, 50)
        self.assertIn("LLM 复盘/教训库: <缺失>", text)


class TestLessonsRejected(unittest.TestCase):
    """task-116（Lead m05592）：task-114 F1 的教训库拒收留痕（`lessons_rejected`）。

    口径：**拒收本身不判红**（文件被外部改过/结构不符时，拒收是**正确**行为 ⇒ 信息项）；
    只有 `dropped>0` 且 `kept==0` **连续 ≥2 天**才给 `warn:lessons_all_rejected` 可视行
    （只警告、不判红、不进 rc）；缺字段 ⇒ 【无法判定】（缺失 ≠ 0，绝不当"没被拒收"通过）。
    """

    REJECT = {"event": "lessons_rejected", "t": 8.5, "path": "<journal>-lessons.json",
              "dropped": 2, "kept": 5, "reasons": ["unknown_kind:foo", "too_long:hint"],
              "note": "schema 校验丢条留痕（task-114 F1）"}
    ALL_GONE = {"event": "lessons_rejected", "t": 8.5, "path": "<journal>-lessons.json",
                "dropped": 3, "kept": 0, "reasons": ["bad_schema:x"],
                "note": "整版都不合格 ⇒ 全丢"}

    def _day(self, day, *, extra=()):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": "night", "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_ledger(tmp.name, name, events)
        self._tmp = tmp
        return report_for(path, days=days, top=50)

    def test_event_has_bucket_and_is_not_unmapped(self):
        self.assertIn("lessons_rejected", mod.EVENT_BUCKETS,
                      "task-114 的 lessons_rejected 必须有桶，否则漂移红")
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.REJECT)]),
                           "lr_bucket.jsonl")
        self.assertEqual(rep["unmapped_events"], {})
        self.assertEqual(rep["events"]["lessons_rejected"], 1)
        self.assertEqual(rep["llm_review"]["rejected_events"], 1)
        self.assertEqual(rep["llm_review"]["rejected_dropped"], 2)

    def test_rejection_itself_is_info_not_red(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.REJECT)]),
                           "lr_info.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "拒收本身是正确行为 ⇒ 绝不判红")
        text = mod.render_text(rep, 50)
        self.assertIn("拒收 1 次 / 2 条", text)
        self.assertIn("unknown_kind:foo", text)
        self.assertNotIn("⚠ warn:lessons_all_rejected", text, "只有一天 ⇒ 不给连续警告")

    def test_all_rejected_two_days_is_warning_not_red(self):
        events = (self._day([1, "summer", 5], extra=[dict(self.ALL_GONE)])
                  + self._day([1, "summer", 6], extra=[dict(self.ALL_GONE)]))
        rep = self._report(events, "lr_warn.jsonl", days=2)
        self.assertEqual(rep["red"]["total"], 0, "warn 不是红：不进 rc")
        self.assertGreaterEqual(rep["llm_review"]["warn_all_rejected_run"], 2)
        text = mod.render_text(rep, 50)
        self.assertIn("warn:lessons_all_rejected", text)
        self.assertIn("拒收 2 次 / 6 条", text)
        self.assertIn("只作警告、不判红", text)
        self.assertIn("连续整版被拒", " ".join(a["text"] for a in rep["advice"]))

    def test_all_rejected_single_day_has_no_warning(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.ALL_GONE)]),
                           "lr_single.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        self.assertLess(rep["llm_review"]["warn_all_rejected_run"], 2)
        self.assertNotIn("⚠ warn:lessons_all_rejected", mod.render_text(rep, 50))

    def test_missing_kept_is_undecidable_not_warning(self):
        no_kept = {k: v for k, v in self.ALL_GONE.items() if k != "kept"}
        events = (self._day([1, "summer", 5], extra=[dict(no_kept)])
                  + self._day([1, "summer", 6], extra=[dict(no_kept)]))
        rep = self._report(events, "lr_nokept.jsonl", days=2)
        self.assertEqual(rep["red"]["total"], 0)
        self.assertIsNone(rep["llm_review"]["rejected_kept"], "缺 kept ⇒ 不许当成 0")
        self.assertNotIn("⚠ warn:lessons_all_rejected", mod.render_text(rep, 50))
        self.assertIn("缺 `kept` 字段", " ".join(rep["undecidable"]))
        self.assertIn("复盘/教训库", str(rep["undecidable"]),
                      "旧账本要进【无法判定】（缺失 ≠ 0）")


class TestUntrustedLessonsAccounting(unittest.TestCase):
    """task-120（Lead m05784）：task-118 的不可信条目证据（`lessons.written` /
    `skipped_untrusted` / `lessons_rejected.untrusted`）。

    口径：**不加红**。`skipped_untrusted>0` 是**好事**（回写只持久化可信条目 ⇒ 防洗白生效）；
    只有 `skipped_untrusted>0 且 written==0` **连续 ≥2 天**才给 `warn:lessons_all_untrusted`
    可视行（不进 rc）；缺字段 ⇒ 【无法判定】（缺失 ≠ 0，绝不当"没有不可信条目"通过）。
    """

    WRITE_OK = {"event": "lessons", "t": 8.4, "day_key": [1, "summer", 5], "added": ["a1"],
                "total": 7, "dropped": 0, "written": 4, "skipped_untrusted": 3,
                "path": "<journal>-lessons.json", "note": "只写可信条目（task-118 A.4）"}
    WRITE_ALL_UNTRUSTED = {"event": "lessons", "t": 8.4, "day_key": [1, "summer", 5],
                           "added": [], "total": 2, "dropped": 0, "written": 0,
                           "skipped_untrusted": 2, "path": "<journal>-lessons.json",
                           "note": "整库都是外部条目 ⇒ 一条也没回写"}
    REJECT_UNTRUSTED = {"event": "lessons_rejected", "t": 8.5, "path": "<journal>-lessons.json",
                        "dropped": 0, "kept": 7, "untrusted": 3,
                        "reasons": ["clamped:last_seq"], "note": "不可信条目上界被钳（task-118 A.2）"}

    def _day(self, day, *, extra=()):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": "night", "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_ledger(tmp.name, name, events)
        self._tmp = tmp
        return report_for(path, days=days, top=50)

    def test_written_and_skipped_untrusted_are_visible_and_never_red(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.WRITE_OK), dict(self.REJECT_UNTRUSTED)]),
                           "lu_ok.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "防洗白生效是好事 ⇒ 绝不判红")
        lr = rep["llm_review"]
        self.assertEqual(lr["lessons_written"], 4)
        self.assertEqual(lr["lessons_skipped_untrusted"], 3)
        self.assertEqual(lr["rejected_untrusted"], 3)
        self.assertEqual(lr["rejected_untrusted_lines"], [3])
        text = mod.render_text(rep, 50)
        self.assertIn("教训库写入 4 条 / 跳过 3 条（不可信）/ 拒收 1 条（其中不可信 3 条）", text)
        self.assertNotIn("⚠ warn:lessons_all_untrusted", text)
        self.assertIn("跳过不可信", " ".join(a["text"] for a in rep["advice"]))
        self.assertIn("防洗白生效", " ".join(a["text"] for a in rep["advice"]))

    def test_all_untrusted_two_days_is_warning_not_red(self):
        events = (self._day([1, "summer", 5], extra=[dict(self.WRITE_ALL_UNTRUSTED)])
                  + self._day([1, "summer", 6], extra=[dict(self.WRITE_ALL_UNTRUSTED)]))
        rep = self._report(events, "lu_warn.jsonl", days=2)
        self.assertEqual(rep["red"]["total"], 0, "warn 不是红：不进 rc")
        self.assertGreaterEqual(rep["llm_review"]["warn_all_untrusted_run"], 2)
        text = mod.render_text(rep, 50)
        self.assertIn("warn:lessons_all_untrusted", text)
        self.assertIn("只作警告、不判红", text)
        self.assertIn("整版不可信", " ".join(a["text"] for a in rep["advice"]))

    def test_all_untrusted_single_day_has_no_warning(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.WRITE_ALL_UNTRUSTED)]),
                           "lu_single.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        self.assertLess(rep["llm_review"]["warn_all_untrusted_run"], 2)
        self.assertNotIn("⚠ warn:lessons_all_untrusted", mod.render_text(rep, 50))

    def test_missing_written_is_undecidable_not_zero(self):
        no_w = {k: v for k, v in self.WRITE_OK.items()
                if k not in ("written", "skipped_untrusted")}
        events = (self._day([1, "summer", 5], extra=[dict(no_w)])
                  + self._day([1, "summer", 6], extra=[dict(no_w)]))
        rep = self._report(events, "lu_nofield.jsonl", days=2)
        self.assertEqual(rep["red"]["total"], 0)
        self.assertIsNone(rep["llm_review"]["lessons_written"], "缺 written ⇒ 不许当成 0")
        self.assertIsNone(rep["llm_review"]["lessons_skipped_untrusted"])
        text = mod.render_text(rep, 50)
        self.assertIn("教训库写入 <缺失> 条 / 跳过 <缺失> 条（不可信）", text)
        self.assertNotIn("⚠ warn:lessons_all_untrusted", text)
        self.assertIn("缺 `written`/`skipped_untrusted` 字段", " ".join(rep["undecidable"]))

    def test_rejected_without_untrusted_field_is_undecidable(self):
        no_u = {k: v for k, v in self.REJECT_UNTRUSTED.items() if k != "untrusted"}
        rep = self._report(self._day([1, "summer", 5], extra=[dict(no_u)]), "lu_nountrusted.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        self.assertEqual(rep["llm_review"]["rejected_untrusted_lines"], [])
        self.assertIn("没有 `untrusted` 字段", " ".join(rep["undecidable"]))


class TestReviewFallbackAndBurst(unittest.TestCase):
    """task-124 / task-130：review 兜底（`review_only_fallback`）、弃权（`review_only_no_target`）、
    换片连发（`plot_exhausted_burst`）、兜底失败（`review_only_fallback_failed`）。

    口径：这些事件是**修复生效的证据**，本身一律**不判红**（`tools\\verify-run3.py` 对这四个名字
    零命中 ⇒ 判红会两边反向）；只给三条可证伪形态的 ⚠ 警告：burst 当天却自称 VERIFIED /
    弃权后 `ended_reason` 仍说"守卫仍说还有活" / 兜底抛异常。缺事件 ⇒ 头部 `<缺失>` +
    【无法判定】（缺失 ≠ 0 = 没发生过）。
    """

    FALLBACK = {"event": "review_only_fallback", "t": 5.0, "source": "work_spot",
                "plot_tiles": 3, "intents": ["water_area", "harvest"],
                "reasons": ["field_ne还有地要清"], "note": "只有 review 却有活"}
    PENDING_WALK = {"event": "review_only_fallback", "t": 5.2, "source": "pending_walk",
                    "tiles": 4, "walked": True, "attempt": 1,
                    "reasons": ["field_se还有地要清"], "note": "回到跨片地 leftover 旁边再看一次"}
    NO_TARGET = {"event": "review_only_no_target", "t": 5.4, "pending": 6,
                 "tiles": [[61, 20], [62, 20]], "reasons": ["field_se还有地要清"],
                 "note": "确定性计划也拿不出目标"}
    BURST = {"event": "plot_exhausted_burst", "t": 6.0, "count": 12, "zone": "field_ne",
             "note": "同一秒内连发换片"}
    FALLBACK_FAILED = {"event": "review_only_fallback_failed", "t": 6.5, "source": "work_spot",
                       "error": "KeyError: 'tiles'"}

    def _day(self, day, *, extra=(), ended_reason="night"):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": ended_reason, "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_ledger(tmp.name, name, events)
        self._tmp = tmp
        return report_for(path, days=days, top=50)

    def test_new_events_have_buckets_and_are_not_unmapped(self):
        for name in ("review_only_fallback", "review_only_fallback_failed",
                     "review_only_no_target", "plot_exhausted_burst"):
            self.assertIn(name, mod.EVENT_BUCKETS, f"{name} 必须有桶（不许改名/藏事件）")
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.FALLBACK)]),
                           "rf_bucket.jsonl")
        self.assertEqual(rep["unmapped_events"], {}, "四个事件都已入桶 ⇒ 不许再出现未映射")

    def test_fallback_no_target_and_burst_are_info_and_visible(self):
        events = self._day([1, "summer", 5],
                           extra=[dict(self.FALLBACK), dict(self.PENDING_WALK),
                                  dict(self.NO_TARGET), dict(self.BURST)])
        rep = self._report(events, "rf_info.jsonl")
        self.assertEqual(rep["red"]["total"], 0,
                         "兜底/弃权/连发是修复生效的证据 ⇒ 绝不判红")
        rf = rep["review_fallback"]
        self.assertTrue(rf["has_events"])
        self.assertEqual(rf["fallback_events"], 2)
        self.assertEqual(rf["fallback_work_spot"], 1)
        self.assertEqual(rf["fallback_pending_walk"], 1)
        self.assertEqual(rf["fallback_walked"], 1)
        self.assertEqual(rf["fallback_tiles"], 7)
        self.assertEqual(rf["fallback_intents"], {"water_area": 1, "harvest": 1})
        self.assertEqual(rf["no_target_events"], 1)
        self.assertEqual(rf["no_target_pending"], 6)
        self.assertEqual(rf["no_target_tiles"], [[61, 20], [62, 20]])
        self.assertEqual(rf["burst_events"], 1)
        self.assertEqual(rf["burst_max"], 12)
        self.assertEqual(rf["burst_zones"], ["field_ne"])
        text = mod.render_text(rep, 50)
        self.assertIn("review 兜底/换片连发: 兜底 2 次", text)
        self.assertIn("弃权 1 次（6 格当日放弃、次日重试）", text)
        self.assertIn("换片连发 1 次（最多一次 count=12、zone=['field_ne']）", text)
        self.assertIn("task-124/task-130 修复生效的证据", " ".join(a["text"] for a in rep["advice"]))

    def test_burst_with_verified_is_warning_not_red(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.BURST)]),
                           "rf_burst_verified.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "警告不是红：不进 rc")
        self.assertNotIn("wasted:", rep["red"]["subjects"])
        rf = rep["review_fallback"]
        self.assertEqual(rf["warn_burst_verified_lines"], [2])
        self.assertEqual(rf["warn_burst_verified_days"], [rep["days"][-1]["label"]])
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ burst 当天却自称 VERIFIED", text)
        self.assertIn("只警告、不判红", text)
        self.assertIn("burst 当天却自称 VERIFIED", " ".join(a["text"] for a in rep["advice"]))

    def test_no_target_then_guard_still_complains_is_warning(self):
        rep = self._report(
            self._day([1, "summer", 5], extra=[dict(self.NO_TARGET)],
                      ended_reason="stuck:换过 3 片地都没有目标（守卫仍说还有活：field_se还有地要清）"),
            "rf_guard.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "警告不是红：不进 rc")
        rf = rep["review_fallback"]
        self.assertEqual(rf["warn_no_target_still_guarded_lines"], [2])
        self.assertEqual(rf["warn_no_target_still_guarded_days"], [rep["days"][-1]["label"]])
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ 弃权后守卫仍抱怨同批 leftover", text)
        self.assertIn("弃权没生效", " ".join(a["text"] for a in rep["advice"]))

    def test_fallback_failed_is_warning_not_red(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.FALLBACK_FAILED)]),
                           "rf_failed.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        rf = rep["review_fallback"]
        self.assertEqual(rf["failed_lines"], [2])
        self.assertEqual(rf["failed_errors"], ["KeyError: 'tiles'"])
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ 兜底抛异常 1 次", text)

    def test_old_ledger_without_events_is_undecidable_not_zero(self):
        rep = self._report(self._day([1, "summer", 5]), "rf_missing.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        self.assertFalse(rep["review_fallback"]["has_events"])
        text = mod.render_text(rep, 50)
        self.assertIn("review 兜底/换片连发: <缺失>", text)
        self.assertIn("缺失 ≠ 0", text)
        self.assertIn("没有任何 review 兜底/弃权/连发/无产出触顶事件",
                      " ".join(rep["undecidable"]))


class TestBuyPartialAccounting(unittest.TestCase):
    """task-123（在制）/ task-132：量力而行买种子 —— `n = min(buy_count, money//price)`，`n >= 1` 就买下，
    `n < wanted` 时另记 `buy_partial`（**不是失败**、不进 `failed`）；`n == 0` 一个都买不起 ⇒
    `cannot_afford` 且一个请求都不发。

    口径：`tools\\verify-run3.py` 对 `buy_partial` 零命中 ⇒ 本工具**不判红、不进 rc**，只给两条
    可证伪形态的 ⚠ 警告（`buy` 自称成交却买少且没有对应 `buy_partial` / 同日既有 `buy_partial`
    又有 `cannot_afford`）；旧账本没有该事件、`buy` 也没有 `wanted` 字段 ⇒ 头部 `<缺失>` +
    【无法判定】（缺失 ≠ 0 ≠ 没发生）。
    """

    BUY_PARTIAL = {"event": "buy", "t": 4.0, "ok": True, "code": "ok", "reason": "买到了",
                   "item": "472", "count": 3, "wanted": 10, "price": 20, "price_shelf": 20,
                   "price_cfg": 20, "source": "day_start", "attempt": 1, "limit": 3,
                   "receipt": "ok: [ok] (HTTP 200)", "available": 5}
    PARTIAL = {"event": "buy_partial", "t": 4.1, "item": "472", "bought": 3, "wanted": 10,
               "price": 20, "price_shelf": 20, "price_cfg": 20, "money": 60,
               "source": "day_start", "ok": True, "code": "ok",
               "note": "钱只够买 3 个（想买 10 个，单价 20g）⇒ 量力而行，这不是失败"}
    BUY_FULL = {"event": "buy", "t": 4.0, "ok": True, "code": "ok", "reason": "买到了",
                "item": "472", "count": 10, "wanted": 10, "price": 20, "price_shelf": 20,
                "price_cfg": 20, "source": "day_start", "attempt": 1, "limit": 3,
                "receipt": "ok: [ok] (HTTP 200)", "available": 12}
    BUY_SHORT_NO_PARTIAL = {"event": "buy", "t": 4.0, "ok": True, "code": "ok",
                            "reason": "买到了", "item": "472", "count": 2, "wanted": 10,
                            "price": 20, "price_shelf": 20, "price_cfg": 20,
                            "source": "day_start", "attempt": 1, "limit": 3,
                            "receipt": "ok: [ok] (HTTP 200)", "available": 5}
    CANNOT_AFFORD = {"event": "cannot_afford", "t": 4.2, "code": "cannot_afford", "money": 10,
                     "seed_price": 20, "keep_factor": 1, "offers": "Parsnip Seeds(20g)",
                     "note": "一个都买不起 ⇒ 今天不再发起 buy"}
    BUY_OLD = {"event": "buy", "t": 4.0, "ok": True, "code": "ok", "reason": "买到了",
               "item": "472", "count": 10, "price": 20, "source": "day_start",
               "attempt": 1, "limit": 3, "receipt": "ok: [ok] (HTTP 200)", "available": 12}

    def _day(self, day, *, extra=(), ended_reason="night"):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": ended_reason, "verified": True, "checks": checks,
               "stages": [{"stage": "plant_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_ledger(tmp.name, name, events)
        self._tmp = tmp
        return report_for(path, days=days, top=50)

    def test_buy_partial_has_bucket_and_is_not_unmapped(self):
        self.assertIn("buy_partial", mod.EVENT_BUCKETS, "buy_partial 必须有桶（不许改名/藏事件）")
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.BUY_PARTIAL), dict(self.PARTIAL)]),
                           "bp_bucket.jsonl")
        self.assertEqual(rep["unmapped_events"], {}, "buy_partial 已入桶 ⇒ 不许再出现未映射")
        self.assertIn("buy_partial", rep)

    def test_partial_buy_is_not_a_failure_and_is_visible(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.BUY_PARTIAL), dict(self.PARTIAL)]),
                           "bp_info.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "买一半不是失败 ⇒ 绝不判红")
        bp = rep["buy_partial"]
        self.assertTrue(bp["has_events"])
        self.assertEqual(bp["events"], 1)
        self.assertEqual(bp["lines"], [3])
        self.assertEqual(bp["bought_total"], 3)
        self.assertEqual(bp["wanted_total"], 10)
        self.assertEqual(bp["short_total"], 7)
        self.assertEqual(bp["plans"], {"472": [3, 10]})
        self.assertEqual(bp["buy_ok_full"], 0)
        self.assertEqual(bp["warn_missing_partial_lines"], [], "有对应 buy_partial ⇒ 不该警告")
        text = mod.render_text(rep, 50)
        self.assertIn("部分购买: 1 次（买到 3 个 / 想要 10 个；还缺 7 个", text)
        self.assertIn("买一半不是失败", text)
        self.assertIn("买一半不是失败", " ".join(a["text"] for a in rep["advice"]))

    def test_full_buy_counts_as_buy_ok_full_and_is_not_partial(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.BUY_FULL)]),
                           "bp_full.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        bp = rep["buy_partial"]
        self.assertTrue(bp["buy_has_wanted"], "有 wanted 字段 ⇒ 0 次是真 0，不是 <缺失>")
        self.assertFalse(bp["has_events"])
        self.assertEqual(bp["buy_ok_full"], 1, "买满 wanted 的整笔才算成交")
        self.assertEqual(bp["warn_missing_partial_lines"], [])
        text = mod.render_text(rep, 50)
        self.assertIn("部分购买: 0 次（买到 0 个 / 想要 0 个", text)
        self.assertNotIn("部分购买: <缺失>", text)

    def test_buy_claiming_full_but_short_without_partial_is_warning(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.BUY_SHORT_NO_PARTIAL)]),
                           "bp_warn.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "警告不是红：不进 rc")
        self.assertNotIn("buy_partial", rep["red"]["subjects"])
        bp = rep["buy_partial"]
        self.assertEqual(bp["warn_missing_partial_lines"], [2])
        self.assertEqual(bp["warn_missing_partial_days"], [rep["days"][-1]["label"]])
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ buy 自称成交却买少", text)
        self.assertIn("只警告、不判红", text)

    def test_partial_and_cannot_afford_same_day_is_warning(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.PARTIAL), dict(self.CANNOT_AFFORD)]),
                           "bp_conflict.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "警告不是红：不进 rc")
        bp = rep["buy_partial"]
        self.assertEqual(bp["cannot_afford_events"], 1)
        self.assertEqual(bp["warn_cannot_afford_same_day_lines"], [3])
        self.assertEqual(bp["warn_cannot_afford_same_day_days"], [rep["days"][-1]["label"]])
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ 同日既有 buy_partial 又有 cannot_afford", text)
        self.assertIn("只提示人工核对", text)

    def test_old_ledger_without_fields_is_undecidable_not_zero(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.BUY_OLD)]),
                           "bp_old.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        bp = rep["buy_partial"]
        self.assertFalse(bp["buy_has_wanted"], "旧账本没有 wanted 字段")
        self.assertEqual(bp["buy_ok_missing_wanted"], 1, "如实标注、不硬当买满")
        text = mod.render_text(rep, 50)
        self.assertIn("部分购买: <缺失>", text)
        self.assertIn("缺失 ≠ 0", text)
        self.assertIn("没有 `buy_partial` 事件", " ".join(rep["undecidable"]))


class TestWaterFarRefillAccounting(unittest.TestCase):
    """task-133：窗口外浇水（`water_far`）遇到壶空 ⇒ **先补水再回浇同一格**（`water_far_refill`）。

    口径：壶空是**前置条件**、**不是「够不着」**；两个事件都**不是失败**，
    `tools\\verify-run3.py` 对 `water_far_refill` 零命中 ⇒ 本工具**不判红、不进 rc**，只给两条
    可证伪形态的 ⚠ 警告（补水没成却把那格浇成了 / 当天补水预算用尽）；旧账本没有
    `water_far_refill`、`water_far` 也没有 `cause` ⇒ 头部 `<缺失>` + 【无法判定】（缺失 ≠ 0 ≠ 没发生）。
    """

    REFILL_OK = {"event": "water_far_refill", "t": 3.0, "tile": [12, 30], "ok": True,
                 "code": "ok", "water_before": 0, "water_after": 40, "tries": 1, "limit": 2,
                 "reason": "补水成功（waterLeft 0 → 40）", "receipt": "refilled: [ok] (HTTP 200)",
                 "note": "壶空是前置条件，不是够不着"}
    REFILL_FAIL = {"event": "water_far_refill", "t": 3.0, "tile": [12, 30], "ok": False,
                   "code": "failed", "water_before": 0, "water_after": 0, "tries": 2, "limit": 2,
                   "reason": "补水失败", "receipt": "failed: [failed] (HTTP 200)", "note": ""}
    FAR_OK = {"event": "water_far", "t": 4.0, "tile": [12, 30], "ok": True, "code": "ok",
              "cause": "need_refill", "refills": 1, "retried_after_refill": True,
              "dry_tiles_status": "ok", "in_dry_tiles_after": False, "walked": True,
              "watered": True, "receipt_ok": True, "reason": "已浇（水 4→3）"}
    FAR_NEED = {"event": "water_far", "t": 4.0, "tile": [12, 30], "ok": False,
                "code": "need_refill", "cause": "need_refill", "refills": 2,
                "retried_after_refill": False, "dry_tiles_status": "ok",
                "in_dry_tiles_after": True, "walked": True, "watered": False,
                "reason": "壶空且补不上"}
    FAR_OLD = {"event": "water_far", "t": 4.0, "tile": [12, 30], "ok": False, "code": "timeout",
               "walked": True, "watered": False, "receipt_ok": False, "reason": "够不着"}
    # task-134 A（与 task-124/130 同族）：回跨片区重评 + 连续无产出触顶 —— 都不是失败
    RESUME = {"event": "resume_reevaluate", "t": 5.0, "where": "resume_walk_leftover",
              "cleared": ["clear_area", "plant_area"],
              "note": "回到跨片区 leftover 之前清掉任务级 no_target"}
    NO_PROGRESS = {"event": "no_progress_burst", "t": 6.0, "count": 10,
                   "source": "resume_walk", "tiles": 9,
                   "reasons": ["field_ne还有地要清/开/种"],
                   "note": "回片区/换作业区连续无产出 ⇒ 诚实收尾"}

    def _day(self, day, *, extra=(), ended_reason="night"):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": ended_reason, "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_ledger(tmp.name, name, events)
        self._tmp = tmp
        return report_for(path, days=days, top=50)

    def test_water_far_refill_has_bucket_and_is_not_unmapped(self):
        self.assertIn("water_far_refill", mod.EVENT_BUCKETS,
                      "water_far_refill 必须有桶（不许改名/藏事件）")
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.REFILL_OK), dict(self.FAR_OK)]),
                           "wf_bucket.jsonl")
        self.assertEqual(rep["unmapped_events"], {}, "已入桶 ⇒ 不许再出现未映射")
        self.assertIn("water_far", rep)

    def test_refill_and_far_are_info_only_and_visible(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.REFILL_OK), dict(self.FAR_OK)]),
                           "wf_info.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "补水和窗口外浇水都不是失败 ⇒ 绝不判红")
        wf = rep["water_far"]
        self.assertTrue(wf["has_events"])
        self.assertEqual(wf["refill_events"], 1)
        self.assertEqual(wf["refill_ok"], 1)
        self.assertEqual(wf["far_events"], 1)
        self.assertEqual(wf["far_ok"], 1)
        self.assertEqual(wf["far_causes"], {"need_refill": 1})
        self.assertEqual(wf["far_retried_after_refill"], 1)
        self.assertEqual(wf["warn_refill_failed_but_watered_lines"], [])
        text = mod.render_text(rep, 50)
        self.assertIn("窗口外浇水/补水: water_far 1 次（浇成 1 / 没成 0", text)
        self.assertIn("补水 water_far_refill 1 次（成功 1 / 没成 0", text)
        self.assertIn("壶空是前置条件、不是「够不着」", text)
        self.assertIn("壶空", " ".join(a["text"] for a in rep["advice"]))

    def test_refill_failed_but_watered_same_day_is_warning(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.REFILL_FAIL), dict(self.FAR_OK)]),
                           "wf_warn.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "警告不是红：不进 rc")
        wf = rep["water_far"]
        self.assertEqual(wf["warn_refill_failed_but_watered_lines"], [2])
        self.assertEqual(wf["budget_exhausted_lines"], [2])
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ 补水没成却把那格浇成了：行 [2]", text)
        self.assertIn("只警告、不判红", text)
        self.assertIn("⚠ 当天补水预算用尽", text)

    def test_budget_exhausted_alone_is_warning_not_red(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.REFILL_FAIL), dict(self.FAR_NEED)]),
                           "wf_budget.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        wf = rep["water_far"]
        self.assertEqual(wf["warn_refill_failed_but_watered_lines"], [], "当天没有浇成的格 ⇒ 不报这条")
        self.assertEqual(wf["warn_budget_exhausted_lines"], [2])
        text = mod.render_text(rep, 50)
        self.assertIn("当天补水预算用尽（tries ≥ limit，行 [2]）", text)

    def test_need_refill_cause_is_named_and_not_red(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.FAR_NEED)]),
                           "wf_need.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "壶空不是够不着 ⇒ 不判红")
        wf = rep["water_far"]
        self.assertEqual(wf["far_need_refill_lines"], [2])
        self.assertEqual(wf["far_causes"], {"need_refill": 1})
        advice = " ".join(a["text"] for a in rep["advice"])
        self.assertIn("need_refill", advice)
        self.assertIn("壶空**不是够不着**", advice)
        self.assertIn("verify-run3.py 对 `water_far_refill` / `water_far_open` / `water_far_blocked` 零命中",
                      advice)

    def test_old_ledger_without_refill_event_is_undecidable_not_zero(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.FAR_OLD)]),
                           "wf_old.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        wf = rep["water_far"]
        self.assertEqual(wf["far_cause_missing"], 1, "旧账本没有 cause 字段 ⇒ 如实计数")
        self.assertEqual(wf["refill_events"], 0)
        und = " ".join(rep["undecidable"])
        self.assertIn("没有任何 `water_far_refill`", und)
        self.assertIn("1 条 `water_far` 没有 `cause` 字段", und)
        self.assertIn("缺失 ≠ 0", und)
        text = mod.render_text(rep, 50)
        self.assertIn("1 条 water_far 没有 cause 字段（旧账本形态）", text)

    def test_task134_events_have_buckets_and_are_visible(self):
        self.assertIn("resume_reevaluate", mod.EVENT_BUCKETS)
        self.assertIn("no_progress_burst", mod.EVENT_BUCKETS)
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.RESUME), dict(self.NO_PROGRESS)]),
                           "np_info.jsonl")
        self.assertEqual(rep["unmapped_events"], {}, "task-134 的两个事件已入桶 ⇒ 不许未映射")
        self.assertEqual(rep["red"]["total"], 0, "死循环解药/有界收尾都不是失败 ⇒ 不判红")
        rf = rep["review_fallback"]
        self.assertTrue(rf["has_events"])
        self.assertEqual(rf["resume_events"], 1)
        self.assertEqual(rf["resume_cleared"], {"clear_area": 1, "plant_area": 1})
        self.assertEqual(rf["no_progress_events"], 1)
        self.assertEqual(rf["no_progress_max"], 10)
        self.assertEqual(rf["no_progress_tiles"], 9)
        text = mod.render_text(rep, 50)
        self.assertIn("回跨片区重评 1 次", text)
        self.assertIn("连续无产出触顶 1 次（最多 count=10", text)

    def test_no_progress_verified_is_warning_not_red(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.NO_PROGRESS)]),
                           "np_warn.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "⚠ 警告不是红：不进 rc")
        rf = rep["review_fallback"]
        self.assertEqual(rf["warn_no_progress_verified_lines"], [2])
        self.assertEqual(rf["warn_no_progress_verified_days"], [rep["days"][-1]["label"]])
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ 连续无产出触顶当天却自称 VERIFIED", text)
        self.assertIn("与 VERIFIED 互斥", text)


class TestStageShortfallAndDeferred(unittest.TestCase):
    """task-134 B：分配额口径 —— `stage_shortfall`（阶段分下去的格没做完）/`stage_shortfall_day`
    （日级 unmet=assigned_undone）/`deferred_tiles`（诚实上限留下的片区待办）。

    口径：三者都不是失败事件（红由 `checks.no_unmet_stages=false` 说话；`deferred_tiles` 明确不进
    该检查）⇒ 本工具只作信息项；只有"日级说 `stopped_night=false` 而当天 `ended_reason` 是 night"
    这条可证伪形态给 ⚠（不判红）；旧账本没有这些事件与字段 ⇒【无法判定】（缺失 ≠ 0）。
    """

    STAGE_SHORTFALL = {"event": "stage_shortfall", "t": 5.0, "stage": "till_area",
                       "zone": "field_ne", "assigned": 12, "undone": 3, "stopped": "",
                       "leftover": 7, "note": "阶段分下去的格没做完"}
    SHORTFALL_DAY = {"event": "stage_shortfall_day", "t": 9.5, "unmet": 3,
                     "stages": [{"stage": "till_area", "undone": 3, "assigned": 12,
                                 "leftover": 7}],
                     "plot_pending": 7, "stopped_night": True, "note": "日级 unmet"}
    DEFERRED = {"event": "deferred_tiles", "t": 9.6, "tiles": 5, "night": True,
                "by_kind": {"till": 5}, "stages": [], "note": "诚实上限留下的片区待办"}
    SHORTFALL_DAY_MISMATCH = {"event": "stage_shortfall_day", "t": 9.5, "unmet": 2,
                              "stages": [{"stage": "plant_area", "undone": 2}],
                              "plot_pending": 2, "stopped_night": False,
                              "note": "日级口径打架形态"}

    def _day(self, day, *, extra=(), ended_reason="night"):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.9, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": ended_reason, "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.9, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_ledger(tmp.name, name, events)
        self._tmp = tmp
        return report_for(path, days=days, top=50)

    def test_task134b_events_have_buckets_and_are_not_unmapped(self):
        for _name in ("stage_shortfall", "stage_shortfall_day", "deferred_tiles"):
            self.assertIn(_name, mod.EVENT_BUCKETS, f"{_name} 必须有桶（不许改名/藏事件）")
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.STAGE_SHORTFALL),
                                                             dict(self.SHORTFALL_DAY),
                                                             dict(self.DEFERRED)]),
                           "sf_bucket.jsonl")
        self.assertEqual(rep["unmapped_events"], {}, "已入桶 ⇒ 不许再出现未映射")
        self.assertIn("shortfall", rep)

    def test_shortfall_and_deferred_are_info_only_and_visible(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.STAGE_SHORTFALL),
                                                             dict(self.SHORTFALL_DAY),
                                                             dict(self.DEFERRED)]),
                           "sf_info.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "分配额/诚实上限都只作信息项 ⇒ 绝不判红")
        sf = rep["shortfall"]
        self.assertTrue(sf["has_events"])
        self.assertEqual(sf["stage_events"], 1)
        self.assertEqual(sf["assigned_total"], 12)
        self.assertEqual(sf["undone_total"], 3)
        self.assertEqual(sf["day_events"], 1)
        self.assertEqual(sf["unmet_max"], 3)
        self.assertEqual(sf["plot_pending_max"], 7)
        self.assertEqual(sf["deferred_tiles"], 5)
        self.assertEqual(sf["warn_stopped_night_mismatch_lines"], [])
        text = mod.render_text(rep, 50)
        self.assertIn("阶段分配额/诚实上限: 阶段没做完 1 次", text)
        self.assertIn("诚实上限留下 1 次 / 5 格", text)
        self.assertIn("只作 info、**不进** no_unmet_stages", text)
        self.assertIn("分配额", " ".join(a["text"] for a in rep["advice"]))

    def test_stopped_night_mismatch_is_warning_not_red(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.SHORTFALL_DAY_MISMATCH)]),
                           "sf_warn.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "⚠ 警告不是红：不进 rc")
        sf = rep["shortfall"]
        self.assertEqual(sf["warn_stopped_night_mismatch_lines"], [2])
        self.assertEqual(sf["warn_stopped_night_mismatch_days"], [rep["days"][-1]["label"]])
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ 日级说 stopped_night=false 但当天 ended_reason 是 night", text)
        self.assertIn("只警告、不判红", text)

    def test_old_ledger_without_fields_is_undecidable_not_zero(self):
        rep = self._report(self._day([1, "summer", 5]), "sf_old.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        sf = rep["shortfall"]
        self.assertFalse(sf["has_events"])
        self.assertIn("阶段分配额/诚实上限: <缺失>", mod.render_text(rep, 50))
        self.assertIn("没有任何 task-134 B 分配额字段", " ".join(rep["undecidable"]))


class TestLessonQualityHintDrop(unittest.TestCase):
    """task-136 C / task-139：`lessons.hint_dropped`（与 evidence 矛盾的 hint 被丢弃）。

    口径：**丢弃是设计行为**（防污染生效的正面证据）⇒ 一律不判红；只有三条可证伪形态给 ⚠（不进 rc）：
    ①字段缺失/非整数；②某天丢弃数 > 当天 `added` 条数（口径打架）；③库文件里有 `hint` 为空的条目
    却没有 `hint_dropped` 计数（疑字段被摘/没记账）。旧账本 ⇒ `<缺失>` +【无法判定】（缺失 ≠ 0）。
    """

    def _build(self, name, *, dropped=0, added=("L1", "L2"), with_lessons=True,
               lessons_json=None, extra=()):
        day = [1, "summer", 5]
        nxt = [day[0], day[1], day[2] + 1]
        ls = {"event": "lessons", "t": 9.0, "day_key": day, "added": list(added),
              "total": 7, "dropped": 0, "written": len(added), "skipped_untrusted": 0,
              "path": "", "note": ""}
        if dropped is not None:
            ls["hint_dropped"] = dropped
        end = {"event": "day_end", "t": 10.0, "day": day, "day_text": "1年 summer 5日",
               "ended_by": "sleep", "ended_reason": "night", "verified": True,
               "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                          "crops_watered": True, "day_justified": True,
                          "watered_outdoor": True, "no_unmet_stages": True},
               "stages": [{"stage": "water_area", "tiles": 1, "ok": 1, "skipped": 0, "failed": 0}],
               "outcomes": [], "ok_steps": 1, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 1, "dry": 0,
                               "scope": "farm"}}
        events = [day_start(day)]
        if with_lessons:
            events.append(ls)
        events.append(end)
        events.extend(extra)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_ledger(tmp.name, name, events)
        if lessons_json is not None:
            lpath = os.path.join(tmp.name, os.path.splitext(name)[0] + "-lessons.json")
            with open(lpath, "w", encoding="utf-8") as fh:
                json.dump(lessons_json, fh, ensure_ascii=False)
        return report_for(path, days=1)

    def test_hint_dropped_is_info_not_red_and_visible(self):
        rep = self._build("hq_ok.jsonl", dropped=2, added=("L1", "L2", "L3"))
        self.assertEqual(rep["red"]["total"], 0, "hint 被丢是设计行为 ⇒ 绝不判红")
        lr = rep["llm_review"]
        self.assertEqual(lr["hint_dropped_total"], 2)
        self.assertEqual(lr["hint_dropped_lines"], [2])
        self.assertEqual(lr["hint_dropped_bad_lines"], [])
        self.assertEqual(lr["hint_dropped_gt_added_lines"], [])
        text = mod.render_text(rep, 50)
        self.assertIn("教训素材质量: 入库 3 条 / hint 丢弃 2 条", text)
        self.assertIn("不判红", text)

    def test_missing_hint_dropped_is_warning_and_undecidable(self):
        rep = self._build("hq_missing.jsonl", dropped=None)
        self.assertEqual(rep["red"]["total"], 0, "缺失只给 ⚠ +【无法判定】，不判红")
        lr = rep["llm_review"]
        self.assertEqual(lr["hint_dropped_bad_lines"], [2])
        text = mod.render_text(rep, 50)
        self.assertIn("hint 丢弃 <缺失>", text)
        self.assertIn("⚠ `lessons.hint_dropped` 缺失或非整数", text)
        self.assertIn("`lessons` 缺 `hint_dropped` 字段", " ".join(rep["undecidable"]))
        self.assertIn("绝不当'没有矛盾 hint'通过", " ".join(rep["undecidable"]))

    def test_non_integer_hint_dropped_is_warning_not_red(self):
        rep = self._build("hq_bad.jsonl", dropped="很多")
        self.assertEqual(rep["red"]["total"], 0)
        self.assertEqual(rep["llm_review"]["hint_dropped_bad_lines"], [2])
        self.assertIn("⚠ `lessons.hint_dropped` 缺失或非整数", mod.render_text(rep, 50))

    def test_dropped_more_than_added_is_warning(self):
        rep = self._build("hq_gt.jsonl", dropped=5, added=("L1",))
        self.assertEqual(rep["red"]["total"], 0, "口径打架只给 ⚠，不判红")
        self.assertEqual(rep["llm_review"]["hint_dropped_gt_added_lines"], [2])
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ hint 丢弃数 > 当天新增条数", text)
        self.assertIn("只警告不判红", text)

    def test_empty_hint_in_file_without_count_is_warning(self):
        rep = self._build("hq_file.jsonl", dropped=0, added=("L1",),
                          lessons_json=[{"id": "L1", "src": "agentfarm", "hint": "",
                                         "symptom": "s", "evidence": "e"}])
        self.assertEqual(rep["red"]["total"], 0)
        lr = rep["llm_review"]
        self.assertEqual(lr["file_empty_hint"], 1)
        self.assertTrue(lr["warn_empty_hint_no_count"])
        self.assertIn("⚠ 库里有条目 hint 为空", mod.render_text(rep, 50))

    def test_empty_hint_with_count_is_not_warned(self):
        rep = self._build("hq_file_ok.jsonl", dropped=1, added=("L1",),
                          lessons_json=[{"id": "L1", "src": "agentfarm", "hint": "",
                                         "symptom": "s", "evidence": "e"}])
        self.assertEqual(rep["llm_review"]["file_empty_hint"], 1)
        self.assertEqual(rep["llm_review"]["warn_empty_hint_no_count"], [])
        self.assertNotIn("⚠ 库里有条目 hint 为空", mod.render_text(rep, 50))

    def test_no_lessons_event_is_missing_not_zero(self):
        rep = self._build("hq_none.jsonl", with_lessons=False)
        self.assertEqual(rep["red"]["total"], 0)
        self.assertFalse(rep["llm_review"]["has_events"])
        text = mod.render_text(rep, 50)
        self.assertIn("教训素材质量: <缺失>", text)
        self.assertIn("绝不当'没有矛盾 hint'通过", text)


class TestStageRefillRetryAndStopNamed(unittest.TestCase):
    """task-144（dev-coder 在制）：`refill_retry` / `stage_stop_named` 收录 + 三条可证伪 ⚠（**不判红**）。"""

    REFILL = {"event": "refill", "t": 9.1, "ok": True, "reason": "补水成功",
              "before": {"waterLeft": 0}, "after": {"waterLeft": 40}}
    RETRY_OK = {"event": "refill_retry", "t": 9.2, "stage": "water_area", "zone": "field_ne",
                "ok": True, "refills_today": 1, "limit": 2, "tiles": 3,
                "targets": [[61, 20], [62, 20], [63, 20]], "note": "原样重跑这一轮没成事的格"}
    RETRY_FAIL = {"event": "refill_retry", "t": 9.25, "stage": "water_area", "zone": "field_ne",
                  "ok": False, "refills_today": 1, "limit": 2, "tiles": 3,
                  "targets": [[61, 20]], "note": "补水不成 ⇒ 保持 stopped=need_refill"}
    RETRY_EMPTY = {"event": "refill_retry", "t": 9.3, "stage": "water_area", "zone": "field_ne",
                   "ok": True, "refills_today": 1, "limit": 2, "tiles": 0, "targets": [],
                   "note": "说重跑却没有格子"}
    STOP_NAMED = {"event": "stage_stop_named", "t": 9.4, "stage": "till_area", "zone": "field_se",
                  "cause": "need_refill", "assigned": 12, "assigned_undone": 3,
                  "tiles": [[61, 20], [62, 20]], "codes": ["need_refill"],
                  "note": "阶段自然结束却仍有分配未成事的格 ⇒ 补如实 stop 原因"}
    STOP_BAD_CAUSE = {"event": "stage_stop_named", "t": 9.5, "stage": "till_area",
                      "zone": "field_se", "cause": "wat", "assigned": 12,
                      "assigned_undone": 1, "tiles": [[61, 20]], "codes": ["tool_ineffective"],
                      "note": "未知 cause"}
    STOP_NO_UNDONE = {"event": "stage_stop_named", "t": 9.6, "stage": "till_area",
                      "zone": "field_se", "cause": "incomplete", "assigned": 12,
                      "assigned_undone": 0, "tiles": [], "codes": [],
                      "note": "没有未成事的格却命名 stop"}
    STOP_NO_CODES = {"event": "stage_stop_named", "t": 9.7, "stage": "till_area",
                     "zone": "field_se", "cause": "incomplete", "assigned": 12,
                     "assigned_undone": 2, "tiles": [[61, 20]], "codes": [],
                     "note": "有过失却没有任何 codes"}
    RETRY_STAGE = {"event": "refill_retry", "t": 9.35, "stage": "water_area", "zone": "field_ne",
                   "ok": True, "refills_today": 1, "limit": 2, "tiles": 2,
                   "stage_refills": 1, "stage_limit": 2, "targets": [[61, 20], [62, 20]],
                   "note": "阶段内第一次补水"}
    RETRY_STAGE_OVER = {"event": "refill_retry", "t": 9.37, "stage": "water_area",
                        "zone": "field_ne", "ok": True, "refills_today": 2, "limit": 2,
                        "tiles": 2, "stage_refills": 3, "stage_limit": 2,
                        "targets": [[61, 20]], "note": "阶段补水越界形态"}

    def _day(self, day, *, extra=(), ended_reason="night"):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.9, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": ended_reason, "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.9, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_ledger(tmp.name, name, events)
        self._tmp = tmp
        return report_for(path, days=days, top=50)

    def test_events_have_buckets_and_are_not_unmapped(self):
        for _name in ("refill_retry", "stage_stop_named"):
            self.assertIn(_name, mod.EVENT_BUCKETS, f"{_name} 必须有桶（不许改名/藏事件）")
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.REFILL), dict(self.RETRY_OK),
                                            dict(self.STOP_NAMED)]),
                           "t144_bucket.jsonl")
        self.assertEqual(rep["unmapped_events"], {}, "已入桶 ⇒ 不许再出现未映射")
        self.assertTrue(rep["refill_retry"]["has_events"])
        self.assertTrue(rep["stage_stop_named"]["has_events"])

    def test_refill_retry_and_stop_named_are_info_only_and_visible(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.REFILL), dict(self.RETRY_OK),
                                            dict(self.STOP_NAMED)]),
                           "t144_info.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "两者都是修复生效的证据 ⇒ 不判红")
        rr, sn = rep["refill_retry"], rep["stage_stop_named"]
        self.assertEqual((rr["events"], rr["ok"], rr["failed"], rr["tiles_total"]), (1, 1, 0, 3))
        self.assertEqual(rr["warn_over_retry_lines"], [])
        self.assertEqual(rr["warn_empty_lines"], [])
        self.assertEqual(sn["causes"], {"need_refill": 1})
        self.assertEqual((sn["assigned_total"], sn["undone_total"]), (12, 3))
        text = mod.render_text(rep, 50)
        self.assertIn("阶段自愈/如实收工: 壶空重跑 1 次", text)
        self.assertIn("如实 stop 命名 1 次", text)
        self.assertIn("不是失败", text)

    def test_over_retry_without_refill_is_warning_not_red(self):
        """当天重跑条数 > 当天 refill 条数 ⇒ 口径打架，只给 ⚠。"""
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.RETRY_OK), dict(self.RETRY_FAIL)]),
                           "t144_over.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        self.assertEqual(len(rep["refill_retry"]["warn_over_retry_lines"]), 2)
        self.assertIn("重跑条数多于当天 refill", mod.render_text(rep, 50))

    def test_empty_refill_retry_is_warning_not_red(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.REFILL), dict(self.RETRY_EMPTY)]),
                           "t144_empty.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        self.assertEqual(len(rep["refill_retry"]["warn_empty_lines"]), 1)
        self.assertIn("补水成功却 0 格可重跑", mod.render_text(rep, 50))

    def test_stop_named_self_contradictions_are_warnings(self):
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.STOP_BAD_CAUSE), dict(self.STOP_NO_UNDONE),
                                            dict(self.STOP_NO_CODES)]),
                           "t144_stop.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "三条可证伪形态都只给 ⚠、不进 rc")
        sn = rep["stage_stop_named"]
        self.assertEqual(len(sn["warn_bad_cause_lines"]), 1)
        self.assertEqual(len(sn["warn_no_undone_lines"]), 1)
        self.assertEqual(len(sn["warn_no_codes_lines"]), 1)
        self.assertIn("stage_stop_named 自相矛盾", mod.render_text(rep, 50))

    def test_stage_refill_fields_are_visible(self):
        """task-144 增量：`stage_refills`/`stage_limit` 必须在头部「阶段补水 N/M 次」里可见。"""
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.REFILL), dict(self.RETRY_STAGE)]),
                           "t144_stage.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        rr = rep["refill_retry"]
        self.assertEqual(rr["stage_refills"], [1])
        self.assertEqual(rr["stage_limits"], [2])
        self.assertEqual(rr["stage_refill_by_stage"],
                         {"water_area": {"stage_refills": 1, "stage_limit": 2}})
        self.assertEqual(rr["warn_over_stage_refill_lines"], [])
        self.assertIn("阶段补水 water_area 1/2 次", mod.render_text(rep, 50))

    def test_over_stage_refill_limit_is_warning_not_red(self):
        """`stage_refills > stage_limit` ⇒ 只给 ⚠（第四条可证伪形态），不进 rc。"""
        rep = self._report(self._day([1, "summer", 5],
                                     extra=[dict(self.REFILL), dict(self.RETRY_STAGE),
                                            dict(self.RETRY_STAGE_OVER)]),
                           "t144_stage_over.jsonl")
        self.assertEqual(rep["red"]["total"], 0, "越界只给 ⚠、不进 rc")
        rr = rep["refill_retry"]
        self.assertEqual(len(rr["warn_over_stage_refill_lines"]), 1)
        self.assertEqual(rr["stage_refill_by_stage"]["water_area"]["stage_refills"], 3)
        text = mod.render_text(rep, 50)
        self.assertIn("阶段补水次数超过该阶段上界", text)
        self.assertIn("只警告、不判红", text)

    def test_old_ledger_without_events_is_undecidable_not_zero(self):
        rep = self._report(self._day([1, "summer", 5]), "t144_old.jsonl")
        self.assertEqual(rep["red"]["total"], 0)
        self.assertFalse(rep["refill_retry"]["has_events"])
        self.assertFalse(rep["stage_stop_named"]["has_events"])
        text = mod.render_text(rep, 50)
        self.assertIn("阶段自愈/如实收工: <缺失>", text)
        self.assertIn("缺失 ≠ 0", text)
        self.assertIn("没有任何 task-144", " ".join(rep["undecidable"]))


class TestOpenPathAndStaminaBudget(unittest.TestCase):
    """task-157/158：够不着 ⇒ **有界开路**（`water_far_open`）后重试同一格；开路后仍站不到 ⇒
    如实 `water_far_blocked`；体力预算 `stamina_budget` / 只因预算被延后 `deferred_by_budget`。

    口径：四个事件都**不是失败**（`tools\\verify-run3.py` 对它们零命中 ⇒ 本工具**不判红、不进 rc**）；
    当天达不达标一律由 `checks.watered_outdoor` / `checks.no_unmet_stages` 说话。只给四条可证伪
    ⚠（只警告）：①开路成功但那格当天最后仍在 dryTiles 里；②有格 blocked 而当天却自称户外浇水达标；
    ③说「只因预算延后」却当天自称浇完；④日级 `deferred_by_budget>0` 却没有对应事件。
    旧账本没有这些事件/字段 ⇒ 头部 `<缺失>` +【无法判定】（缺失 ≠ 0 ≠ 没发生）。
    """

    OPEN_OK = {"event": "water_far_open", "t": 3.0, "tile": [12, 30], "code": "ok",
               "attempt": 1, "limit": 2, "cleared_count": 2, "cleared": [[11, 30], [13, 30]],
               "note": "开路后已站到目标旁（open_way 内部复核 stand_next_to 通过）"}
    BLOCKED = {"event": "water_far_blocked", "t": 3.5, "tile": [40, 40], "cause": "no_route",
               "attempts": 2, "limit": 2, "opens": 2, "cleared_count": 3, "cleared": [[39, 40]],
               "note": "有界开路之后仍然站不到这一格 ⇒ 如实记 blocked"}
    FAR_STILL_DRY = {"event": "water_far", "t": 4.0, "tile": [12, 30], "ok": False,
                     "code": "timeout", "walked": True, "watered": False,
                     "in_dry_tiles_after": True, "dry_tiles_status": "ok",
                     "reason": "开路成功但那格仍在 dryTiles 里"}
    BUDGET = {"event": "stamina_budget", "t": 5.0, "max": 270, "stamina": 120, "live_crops": 8,
              "dry": 34, "water_reserve": 100, "water_cost_est": 96, "path_allowance": 25,
              "capacity": 100, "basis": "farm", "deferred_by_budget": 4,
              "deferred": ["water_area"]}
    DEFER = {"event": "deferred_by_budget", "t": 5.5, "task": "till_area", "why": "budget",
             "stamina": 120, "water_reserve": 100, "dry": 34, "live_crops": 8, "basis": "farm",
             "note": "只因预算而不做（不是没活）"}

    def _day(self, day, *, extra=(), checks_over=None, budget=None):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        if checks_over:
            checks.update(checks_over)
        end = {"event": "day_end", "t": 9.0, "day": day, "ended_by": "sleep",
               "ended_reason": "night", "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0, "notes": [],
               "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        if budget is not None:
            end["stamina_budget"] = budget
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ledger(tmp, name, events)
            return report_for(path, days=days)

    def test_new_events_have_buckets_and_are_not_unmapped(self):
        for ev in ("water_far_open", "water_far_blocked", "stamina_budget", "deferred_by_budget"):
            self.assertIn(ev, mod.EVENT_BUCKETS)
        rep = self._report(self._day([1, "fall", 3], extra=[self.OPEN_OK, self.BLOCKED,
                                                            self.BUDGET, self.DEFER]),
                           "t160_buckets.jsonl")
        self.assertEqual(rep["unmapped_events"], {})
        self.assertEqual(rep["events"].get("water_far_open"), 1)
        self.assertEqual(rep["events"].get("water_far_blocked"), 1)
        self.assertEqual(rep["events"].get("stamina_budget"), 1)
        self.assertEqual(rep["events"].get("deferred_by_budget"), 1)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_open_and_blocked_are_info_only_and_visible(self):
        rep = self._report(self._day([1, "fall", 3], extra=[self.OPEN_OK, self.BLOCKED]),
                           "t160_open.jsonl")
        text = mod.render_text(rep, 50)
        self.assertIn("开路/够不着: 开路 1 次", text)
        self.assertIn("开路后仍站不到 1 格", text)
        self.assertIn("no_route×1", text)
        self.assertEqual((rep["red"] or {}).get("total"), 0)
        self.assertEqual(rep["water_far"]["open_events"], 1)
        self.assertEqual(rep["water_far"]["open_cleared_total"], 2)
        self.assertEqual(rep["water_far"]["blocked_causes"], {"no_route": 1})

    def test_open_ok_but_still_dry_is_warning_not_red(self):
        rep = self._report(self._day([1, "fall", 3], extra=[self.OPEN_OK, self.FAR_STILL_DRY]),
                           "t160_stilldry.jsonl")
        wf = rep["water_far"]
        self.assertEqual(len(wf["warn_open_but_still_dry_lines"]), 1)
        advice = mod.render_text(rep, 50)
        self.assertIn("⚠ 开路成功但那格当天最后仍在 dryTiles 里", advice)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_stamina_budget_and_deferred_are_visible_not_red(self):
        rep = self._report(self._day([1, "fall", 3], extra=[self.BUDGET, self.DEFER],
                                     budget={"deferred_by_budget": 4, "water_reserve": 100,
                                             "capacity": 100}),
                           "t160_budget.jsonl")
        sb = rep["stamina_budget"]
        self.assertEqual(sb["events"], 1)
        self.assertEqual(sb["defer_events"], 1)
        self.assertEqual(sb["defer_tasks"], {"till_area": 1})
        self.assertEqual(sb["basis"], {"farm": 1})
        text = mod.render_text(rep, 50)
        self.assertIn("体力预算: reserve 100 / capacity 100", text)
        self.assertIn("by_budget 延后 1 条", text)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_deferred_but_watered_and_missing_event_are_warnings(self):
        day1 = self._day([1, "fall", 3], extra=[self.DEFER])
        # 第 2 天：日级说 deferred_by_budget>0，却没有任何 deferred_by_budget 事件（留痕不一致）
        day2 = self._day([1, "fall", 4], budget={"deferred_by_budget": 3, "water_reserve": 100,
                                                 "capacity": 100})
        rep = self._report(day1 + day2, "t160_defer.jsonl", days=2)
        sb = rep["stamina_budget"]
        self.assertEqual(len(sb["warn_deferred_but_watered_lines"]), 1)
        self.assertEqual(len(sb["warn_defer_missing_lines"]), 1)
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ 说「只因预算延后」但当天却自称户外浇水达标", text)
        self.assertIn("⚠ 日级 deferred_by_budget>0 却没有对应的 deferred_by_budget 事件", text)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_old_ledger_without_fields_is_undecidable_not_zero(self):
        rep = self._report(self._day([1, "fall", 3]), "t160_old.jsonl")
        text = mod.render_text(rep, 50)
        self.assertIn("开路/够不着: <缺失>", text)
        self.assertIn("体力预算: <缺失>", text)
        blob = " ".join(rep.get("undecidable") or [])
        self.assertIn("task-157", blob)
        self.assertIn("task-158", blob)
        self.assertIn("缺失 ≠ 0", blob)
        self.assertEqual((rep["red"] or {}).get("total"), 0)


class TestToolGateBlockedByTool(unittest.TestCase):
    """task-20 / task-164：clump 工具门槛 ⇒ `blocked_by_tool`（逐格）+ `blocked_by_tool_summary`（日级）。

    口径：**诚实跳过、不是失败**（工具等级/种类不够或 `toolOk` 判不出 ⇒ 动手之前就封格、0 次
    `use_tool`；当天 `blocked`、次日升级后自动重试），**不判红、不进 rc**（`tools/verify-run3.py`
    对这两名零命中，判红会两边反向）；只一条可证伪 ⚠（不进 rc）：当天自称 `no_work` 却存在工具门槛
    封格。旧账本没有这两事件 ⇒ `<缺失>` +【无法判定】（缺失 ≠ 0）；`min_level` 缺失 ⇒【无法判定】。
    """

    BLOCKED = {"event": "blocked_by_tool", "t": 3.0, "tile": [72, 35], "action": "clear",
               "stage": "clear_area", "zone": "field_ne", "kind": "clump",
               "need": "pickaxe≥2", "min_level": 2, "reason": "工具不够格，先不动",
               "note": "0 次 use_tool"}
    BLOCKED2 = {"event": "blocked_by_tool", "t": 3.2, "tile": [73, 35], "action": "clear",
                "stage": "clear_area", "zone": "field_ne", "kind": "clump",
                "need": "pickaxe≥2", "min_level": 2, "reason": "工具不够格，先不动",
                "note": "0 次 use_tool"}
    BLOCKED_NOLEVEL = {"event": "blocked_by_tool", "t": 3.4, "tile": [72, 36], "action": "clear",
                       "stage": "clear_area", "zone": "field_ne", "kind": "clump",
                       "need": "pickaxe≥2", "reason": "等级判不出", "note": "0 次 use_tool"}
    SUMMARY = {"event": "blocked_by_tool_summary", "t": 8.0, "count": 2,
               "tiles": [[72, 35], [73, 35]], "kinds": ["clump"],
               "tools": ["pickaxe"], "note": "日级汇总"}

    def _day(self, day, *, extra=(), ended_reason="night"):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.9, "day": day, "day_text": "", "ended_by": "sleep",
               "ended_reason": ended_reason, "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "outcomes": [], "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0,
               "notes": [], "final": final(nxt),
               "final_water": {"t": 9.9, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ledger(tmp, name, events)
            return report_for(path, days=days)

    def test_new_events_have_buckets_and_are_not_unmapped(self):
        for ev in ("blocked_by_tool", "blocked_by_tool_summary"):
            self.assertIn(ev, mod.EVENT_BUCKETS, f"{ev} 必须有桶（不许改名/藏事件）")
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.BLOCKED),
                                                             dict(self.BLOCKED2),
                                                             dict(self.SUMMARY)]),
                           "t164_buckets.jsonl")
        self.assertEqual(rep["unmapped_events"], {}, "已入桶 ⇒ 不许再出现未映射")
        self.assertEqual(rep["events"].get("blocked_by_tool"), 2)
        self.assertEqual(rep["events"].get("blocked_by_tool_summary"), 1)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_tool_gate_is_info_only_and_visible(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.BLOCKED),
                                                             dict(self.BLOCKED2),
                                                             dict(self.SUMMARY)]),
                           "t164_info.jsonl")
        tg = rep["tool_gate"]
        self.assertTrue(tg["has_events"])
        self.assertEqual(tg["events"], 2)
        self.assertEqual(tg["kinds"], {"clump": 2})
        self.assertEqual(tg["needs"], {"pickaxe≥2": 2})
        self.assertEqual(tg["min_levels"], {"2": 2})
        self.assertEqual(tg["min_level_missing"], 0)
        self.assertEqual(tg["tiles"], [[72, 35], [73, 35]])
        self.assertEqual(tg["summary_events"], 1)
        self.assertEqual(tg["summary_counts"], [2])
        self.assertEqual(tg["summary_tools"], {"pickaxe": 1})
        self.assertEqual(tg["summary_kinds"], {"clump": 1})
        self.assertEqual(tg["warn_no_work_with_gate_lines"], [])
        text = mod.render_text(rep, 50)
        self.assertIn("工具门槛: 当天因工具等级/种类不够封格 2 格", text)
        self.assertIn("需要 pickaxe≥2×2", text)
        self.assertIn("kind clump×2", text)
        self.assertIn("日级汇总 blocked_by_tool_summary 1 次", text)
        self.assertIn("诚实跳过", text)
        self.assertIn("不进守卫理由", text)
        blob = " ".join(a["text"] for a in rep["advice"])
        self.assertIn("工具门槛封格（信息项，**诚实跳过、不是失败**）", blob)
        self.assertEqual((rep["red"] or {}).get("total"), 0, "工具门槛只作信息项 ⇒ 绝不判红")

    def test_no_work_with_gate_is_warning_not_red(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.BLOCKED), dict(self.SUMMARY)],
                                     ended_reason="no_work:今天已经没有任何可做的目标"),
                           "t164_nowork.jsonl")
        tg = rep["tool_gate"]
        self.assertEqual(len(tg["warn_no_work_with_gate_lines"]), 1)
        self.assertEqual((rep["red"] or {}).get("total"), 0, "⚠ 警告不是红：不进 rc")
        text = mod.render_text(rep, 50)
        self.assertIn("⚠ 当天自称 no_work（没活）却存在工具门槛封格", text)
        self.assertIn("真敲不动 vs 工具够却判不出", text)

    def test_missing_min_level_is_undecidable_not_zero(self):
        rep = self._report(self._day([1, "summer", 5], extra=[dict(self.BLOCKED_NOLEVEL),
                                                             dict(self.SUMMARY)]),
                           "t164_nolevel.jsonl")
        tg = rep["tool_gate"]
        self.assertEqual(tg["min_level_missing"], 1)
        self.assertEqual(tg["min_levels"], {})
        blob = " ".join(rep.get("undecidable") or [])
        self.assertIn("没写 `min_level`", blob)
        self.assertIn("绝不默认 0 级", blob)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_old_ledger_without_events_is_undecidable_not_zero(self):
        rep = self._report(self._day([1, "summer", 5]), "t164_old.jsonl")
        tg = rep["tool_gate"]
        self.assertFalse(tg["has_events"])
        text = mod.render_text(rep, 50)
        self.assertIn("工具门槛: <缺失>", text)
        self.assertIn("缺失 ≠ 0", text)
        blob = " ".join(rep.get("undecidable") or [])
        self.assertIn("task-20", blob)
        self.assertIn("没有任何 task-20 的 `blocked_by_tool`", blob)
        self.assertEqual((rep["red"] or {}).get("total"), 0)


class TestBudgetDeferralAndCapacity(unittest.TestCase):
    """task-163：`budget_deferred_tiles`（日级/日初：某任务有 count 格被**体力预算**显式延后 ⇒
    守卫不再把它们算作「还有活」）+ `stage_capped_by_capacity`（stage 级：分配额被当天容量上限卡住
    ⇒ 只分配 capacity 格），以及 `day_end.stamina_budget` 的三个子键
    （`deferred_tiles{task:n}` / `capped_by_capacity{task:{limit,capacity}}` / `capacity_capped_tasks`）。

    口径：两条都是**诚实留痕、不是失败、不判红、不进 rc**（`tools\\verify-run3.py` 对这两名零命中）；
    唯一要人工核对的红线是「延后只在体力 ≤ water_reserve **且** 有浇水债时生效」。两条可证伪 ⚠
    （只警告、不进 rc）：①当天有延后却自称「该做的都做了」（`no_work` + `verified=true`）；
    ②同日有延后但 `stamina_budget` 显示没有浇水债（`live_crops<=0` / `dry<=0`）。
    旧账本/缺字段 ⇒ `<缺失>` +【无法判定】（缺失 ≠ 0，绝不当作「今天没用预算」通过）。
    """

    BDT = {"event": "budget_deferred_tiles", "t": 6.0, "task": "till_area", "count": 3, "total": 3,
           "targets": [[60, 20], [61, 20]], "note": "这些格子今天被**体力预算**显式延后"}
    CAP = {"event": "stage_capped_by_capacity", "t": 6.5, "task": "till_area", "limit": 6,
           "capacity": 4, "live_crops": 8, "dry": 34, "water_reserve": 100,
           "note": "分配额被当天体力预算的容量上限卡住"}
    SB_DAY = {"max": 270, "stamina": 120, "live_crops": 8, "dry": 34, "water_reserve": 100,
              "capacity": 4, "basis": "farm", "deferred_by_budget": True,
              "deferred": ["till_area"], "deferred_tiles": {"till_area": 3},
              "capped_by_capacity": {"till_area": {"limit": 6, "capacity": 4}},
              "capacity_capped_tasks": 1}

    def _day(self, day, *, extra=(), ended_reason="night", verified=True, budget=None):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 9.0, "day": day, "ended_by": "sleep",
               "ended_reason": ended_reason, "verified": verified, "checks": checks,
               "stages": [{"stage": "till_area", "ok": 5, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "ok_steps": 5, "skipped_steps": 0, "failed_steps": 0, "notes": [],
               "final": final(nxt),
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        if budget is not None:
            end["stamina_budget"] = budget
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ledger(tmp, name, events)
            return report_for(path, days=days)

    def test_events_have_buckets_and_are_not_unmapped(self):
        for ev in ("budget_deferred_tiles", "stage_capped_by_capacity"):
            self.assertIn(ev, mod.EVENT_BUCKETS)
        rep = self._report(self._day([1, "fall", 3], extra=[self.BDT, self.CAP],
                                     budget=self.SB_DAY), "t165_buckets.jsonl")
        self.assertEqual(rep["unmapped_events"], {})
        self.assertEqual(rep["events"].get("budget_deferred_tiles"), 1)
        self.assertEqual(rep["events"].get("stage_capped_by_capacity"), 1)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_budget_deferral_and_capacity_are_info_only_and_visible(self):
        rep = self._report(self._day([1, "fall", 3], extra=[self.BDT, self.CAP],
                                     budget=self.SB_DAY), "t165_visible.jsonl")
        sb = rep["stamina_budget"]
        self.assertEqual(sb["budget_defer_events"], 1)
        self.assertEqual(sb["budget_defer_tiles"], 3)
        self.assertEqual(sb["budget_defer_tasks"], {"till_area": 3})
        self.assertEqual(sb["capacity_events"], 1)
        self.assertEqual(sb["capacity_tasks"], {"till_area": {"limit": 6, "capacity": 4}})
        self.assertEqual(sb["capacity_capped_tasks"], 1)
        self.assertEqual(sb["day_deferred_tiles"],
                         {rep["days"][-1]["label"]: {"till_area": 3}})
        text = mod.render_text(rep, 50)
        self.assertIn("预算延后 budget_deferred_tiles 1 条（3 格；任务 till_area×3）", text)
        self.assertIn("容量上限 stage_capped_by_capacity 1 次（任务 till_area；"
                      "日级 capacity_capped_tasks 1）", text)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_defer_tiles_with_no_work_verified_is_warning_not_red(self):
        rep = self._report(self._day([1, "fall", 3], extra=[self.BDT], ended_reason="no_work",
                                     budget=self.SB_DAY), "t165_warn_nowork.jsonl")
        sb = rep["stamina_budget"]
        self.assertTrue(sb["warn_defer_tiles_but_no_work_lines"])
        self.assertEqual((rep["red"] or {}).get("total"), 0)
        self.assertNotIn("missed:", " ".join((rep["red"] or {}).get("subjects") or []))
        text = mod.render_text(rep, 50)
        self.assertIn("当天有预算延后却自称「该做的都做了」", text)
        blob = " ".join(a.get("text", "") for a in rep.get("advice") or [])
        self.assertIn("延后是否只发生在体力 ≤ water_reserve", blob)

    def test_defer_tiles_without_water_debt_is_warning_not_red(self):
        no_debt = dict(self.SB_DAY)
        no_debt.update({"live_crops": 0, "dry": 0})
        rep = self._report(self._day([1, "fall", 3], extra=[self.BDT], budget=no_debt),
                           "t165_warn_nodebt.jsonl")
        sb = rep["stamina_budget"]
        self.assertTrue(sb["warn_defer_without_debt_lines"])
        self.assertEqual((rep["red"] or {}).get("total"), 0)
        text = mod.render_text(rep, 50)
        self.assertIn("没有浇水债（live_crops/dry ≤ 0）", text)

    def test_old_ledger_without_fields_is_undecidable_not_zero(self):
        rep = self._report(self._day([1, "summer", 5]), "t165_old.jsonl")
        sb = rep["stamina_budget"]
        self.assertFalse(sb["has_events"])
        self.assertEqual(sb["budget_defer_events"], 0)
        self.assertEqual(sb["day_deferred_tiles"], {})
        text = mod.render_text(rep, 50)
        self.assertIn("体力预算: <缺失>", text)
        self.assertIn("缺失 ≠ 0", text)
        blob = " ".join(rep.get("undecidable") or [])
        self.assertIn("task-158/163", blob)
        self.assertIn("绝不当'今天没用预算'通过", blob)
        self.assertEqual((rep["red"] or {}).get("total"), 0)


class TestHarvestGaveUpAndCropReady(unittest.TestCase):
    """task-172：`harvest_gave_up`（task-170 ②：逐格**如实放弃**收获）+ task-170 ① 的新观测字段
    （`tiles[].ready` / `farm.readyCrops` / `exec.acted` / 逐格作物元数据）。

    口径：`harvest_gave_up` **不是豁免分子** —— brain 把它从目标池与守卫里扣掉
    （`ripe_live = ripe − len(harvest_gave_up)`），但 `_leftover("harvest")` **不扣**
    （`brain\\agentfarm\\longrun.py:4046-4069` 自己写明"如实 unmet、不洗白"）⇒ 它就是
    「该做没做」的证据。`tools\\verify-run3.py` 对 `harvest_gave_up` 零命中 ⇒ 本工具不判红、
    不进 rc；唯一给 ⚠ 的形态是「当天如实放弃了收获却自称 VERIFIED」（只警告）。
    `ripe`（`Crop.fullyGrown`，看着熟）与 `ready`（`HoeDirt.readyForHarvest()`，真能收）两口径的
    差值 = task-169 病根；`ready == null` 只记【无法判定】，**绝不当 false**。
    旧账本没有这些事件/字段 ⇒ `<缺失>` +【无法判定】（缺失 ≠ 0）。
    """

    HGU = {"event": "harvest_gave_up", "t": 8.0, "tile": [60, 29], "attempts": 3, "limit": 3,
           "codes": ["failed"],
           "note": "同一格今天试满上限仍没摘下来 ⇒ 当天不再动人"}

    def _day(self, day, *, extra=(), verified=True, ended_reason="night", farm=None):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        _final = final(nxt)
        if farm is not None:
            _final = dict(_final)
            _final["farm"] = farm
        end = {"event": "day_end", "t": 9.0, "day": day, "ended_by": "sleep",
               "ended_reason": ended_reason, "verified": verified, "checks": checks,
               "stages": [{"stage": "harvest", "ok": 1, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "ok_steps": 1, "skipped_steps": 0, "failed_steps": 0, "notes": [],
               "final": _final,
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ledger(tmp, name, events)
            return report_for(path, days=days)

    def test_harvest_gave_up_has_bucket_and_is_not_unmapped(self):
        self.assertIn("harvest_gave_up", mod.EVENT_BUCKETS)
        rep = self._report(self._day([1, "fall", 7], extra=[self.HGU]), "t172_buckets.jsonl")
        self.assertEqual(rep["unmapped_events"], {})
        self.assertEqual(rep["events"].get("harvest_gave_up"), 1)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_gave_up_is_visible_and_never_an_exemption(self):
        rep = self._report(self._day([1, "fall", 7], extra=[self.HGU]), "t172_visible.jsonl")
        hg = rep["harvest_gave_up"]
        self.assertTrue(hg["has_events"])
        self.assertEqual(hg["events"], 1)
        self.assertEqual(hg["tile_count"], 1)
        self.assertEqual(hg["tiles"], [(60, 29)])
        self.assertEqual(hg["attempts"], 3)
        self.assertEqual(hg["limits"], [3])
        self.assertEqual(hg["codes"], {"failed": 1})
        text = mod.render_text(rep, 50)
        self.assertIn("收获放弃（如实，**不是豁免**）: 1 次 / 1 格", text)
        self.assertIn("绝不当已做完", text)
        blob = " ".join(a.get("text", "") for a in rep.get("advice") or [])
        self.assertIn("不是豁免配额", blob)
        self.assertIn("该做没做", blob)

    def test_gave_up_but_verified_is_warning_not_red(self):
        rep = self._report(self._day([1, "fall", 7], extra=[self.HGU], verified=True),
                           "t172_warn_verified.jsonl")
        hg = rep["harvest_gave_up"]
        self.assertTrue(hg["warn_gave_up_but_verified_lines"])
        self.assertEqual((rep["red"] or {}).get("total"), 0)
        self.assertNotIn("missed:", " ".join((rep["red"] or {}).get("subjects") or []))
        text = mod.render_text(rep, 50)
        self.assertIn("当天如实放弃了收获却自称 VERIFIED", text)

    def test_ripe_minus_ready_diff_is_reported(self):
        farm = {"loaded": True, "complete": True, "ripeCrops": 3, "readyCrops": 1}
        rep = self._report(self._day([1, "fall", 7], farm=farm), "t172_cropready.jsonl")
        cr = rep["crop_ready"]
        self.assertTrue(cr["has_fields"])
        self.assertEqual(cr["ripe_total"], 3)
        self.assertEqual(cr["ready_total"], 1)
        self.assertEqual(cr["diff_total"], 2)
        text = mod.render_text(rep, 50)
        self.assertIn("熟/可收对账: ripeCrops 3 − readyCrops 1 = 2", text)
        self.assertIn("看着熟其实不能收", text)
        blob = " ".join(a.get("text", "") for a in rep.get("advice") or [])
        self.assertIn("task-169 的真病根", blob)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_missing_task170_fields_is_undecidable_not_zero(self):
        rep = self._report(self._day([1, "summer", 5]), "t172_old.jsonl")
        self.assertFalse(rep["harvest_gave_up"]["has_events"])
        self.assertFalse(rep["crop_ready"]["has_fields"])
        text = mod.render_text(rep, 50)
        self.assertIn("收获放弃: <缺失>", text)
        self.assertIn("熟/可收对账: <缺失>", text)
        blob = " ".join(rep.get("undecidable") or [])
        self.assertIn("harvest_gave_up", blob)
        self.assertIn("tiles[].ready", blob)
        self.assertIn("缺失 ≠ 0", blob)
        self.assertEqual((rep["red"] or {}).get("total"), 0)


class TestCropReadySource(unittest.TestCase):
    """task-179（dev task-176 `037e599`）：`tiles[].readySource` 三态记账 + `harvestMethod` 键必存在。

    口径（Lead 已用 il-probe 实证）：`ready=true` 对「末阶段未熟」的格是**游戏口径的真相**
    （`HoeDirt.readyForHarvest()` 的 IL 与字段判据逐条等价）⇒ `readySource="fields"` 是
    **正常的等价路径，不是 fail-open**；只有 `null` 才是"判不了"（⇒【无法判定】，既不当失败、
    也绝不当通过）。旧账本缺这个键 ⇒【无法判定·旧 Mod】。`null` 占比高 = fail-closed 过头风险，
    只给 ⚠，一律不进 rc。
    """

    TILES_OK = [
        {"tile": [60, 29], "crop": "270", "ripe": True, "ready": True, "readySource": "game",
         "harvestMethod": "Grab"},
        {"tile": [61, 29], "crop": "262", "ripe": False, "ready": False, "readySource": "fields",
         "harvestMethod": "Grab"},
        {"tile": [62, 29], "crop": "262", "ripe": True, "ready": None, "readySource": None,
         "harvestMethod": "Scythe"},
    ]

    def _tile_event(self, tiles, t=5.0):
        return {"event": "review", "t": t, "zone": "field_ne", "tiles": tiles}

    def _day(self, day, *, extra=(), farm=None):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        _final = final(nxt)
        if farm is not None:
            _final = dict(_final)
            _final["farm"] = farm
        end = {"event": "day_end", "t": 9.0, "day": day, "ended_by": "sleep",
               "ended_reason": "night", "verified": True, "checks": checks,
               "stages": [{"stage": "harvest", "ok": 1, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "ok_steps": 1, "skipped_steps": 0, "failed_steps": 0, "notes": [],
               "final": _final,
               "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ledger(tmp, name, events)
            return report_for(path, days=days)

    def test_field_probes_cover_ready_source_and_harvest_method(self):
        probes = {p for _, p, _ in mod.FIELD_PROBES}
        self.assertIn("tile_ready_source", probes)
        self.assertIn("tile_harvest_method", probes)

    def test_ready_source_distribution_is_visible_and_not_red(self):
        rep = self._report(self._day([1, "fall", 9], extra=[self._tile_event(self.TILES_OK)]),
                           "t179_dist.jsonl")
        cr = rep["crop_ready"]
        self.assertTrue(cr["has_ready_source"])
        self.assertEqual(cr["ready_source_game"], 1)
        self.assertEqual(cr["ready_source_fields"], 1)
        self.assertEqual(cr["ready_source_null"], 1)
        self.assertEqual(cr["ready_source_missing_tiles"], 0)
        self.assertEqual(cr["harvest_method_missing_lines"], [])
        text = mod.render_text(rep, 50)
        self.assertIn("可收来源: readySource game 1 / fields 1 / null 1 / 缺键 0", text)
        self.assertIn("不是 fail-open", text)
        self.assertFalse(cr["warn_null_heavy"], "3 格里 1 格 null 没过半，不该报 fail-closed 过头")
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_fields_source_is_a_normal_equivalent_path_not_failure(self):
        tiles = [{"tile": [60, 29], "crop": "270", "ripe": True, "ready": True,
                  "readySource": "fields", "harvestMethod": "Grab"}]
        rep = self._report(self._day([1, "fall", 9], extra=[self._tile_event(tiles)]),
                           "t179_fields.jsonl")
        cr = rep["crop_ready"]
        self.assertEqual(cr["ready_source_fields"], 1)
        self.assertEqual(cr["ready_source_missing_tiles"], 0)
        self.assertEqual((rep["red"] or {}).get("total"), 0)
        blob = " ".join(rep.get("undecidable") or [])
        self.assertNotIn("`tiles[].readySource`（task-176）", blob,
                         "有来源标记 ⇒ 不该报专用【无法判定·旧 Mod】行")
        text = mod.render_text(rep, 50)
        self.assertIn("逐条等价", text)
        self.assertIn("不是 fail-open", text)

    def test_ready_without_ready_source_is_undecidable_old_mod(self):
        tiles = [{"tile": [60, 29], "crop": "270", "ripe": True, "ready": True,
                  "harvestMethod": "Grab"}]
        rep = self._report(self._day([1, "fall", 9], extra=[self._tile_event(tiles)]),
                           "t179_oldmod.jsonl")
        cr = rep["crop_ready"]
        self.assertEqual(cr["ready_source_missing_tiles"], 1)
        self.assertTrue(cr["ready_source_missing_lines"])
        text = mod.render_text(rep, 50)
        self.assertIn("缺键 1", text)
        self.assertIn("无法判定·旧 Mod", text)
        blob = " ".join(rep.get("undecidable") or [])
        self.assertIn("`tiles[].readySource`（task-176）", blob)
        self.assertIn("无法判定·旧 Mod", blob)
        advice = " ".join(a.get("text", "") for a in rep.get("advice") or [])
        self.assertIn("无法判定·旧 Mod", advice)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_null_heavy_is_warning_not_red(self):
        tiles = [{"tile": [i, 29], "crop": "262", "ripe": False, "ready": None,
                  "readySource": None, "harvestMethod": "Grab"} for i in range(60, 64)]
        rep = self._report(self._day([1, "fall", 9], extra=[self._tile_event(tiles)]),
                           "t179_null.jsonl")
        cr = rep["crop_ready"]
        self.assertEqual(cr["ready_source_null"], 4)
        self.assertTrue(cr["warn_null_heavy"])
        text = mod.render_text(rep, 50)
        self.assertIn("fail-closed 过头风险", text)
        self.assertIn("只记【无法判定】", text)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_harvest_method_key_must_exist(self):
        tiles = [{"tile": [60, 29], "crop": "270", "ripe": True, "ready": True,
                  "readySource": "game"}]
        rep = self._report(self._day([1, "fall", 9], extra=[self._tile_event(tiles)]),
                           "t179_hm.jsonl")
        cr = rep["crop_ready"]
        self.assertTrue(cr["harvest_method_missing_lines"])
        text = mod.render_text(rep, 50)
        self.assertIn("harvestMethod 键缺失", text)
        self.assertEqual((rep["red"] or {}).get("total"), 0)

    def test_no_ready_source_at_all_is_undecidable_not_pass(self):
        rep = self._report(self._day([1, "fall", 9]), "t179_none.jsonl")
        cr = rep["crop_ready"]
        self.assertFalse(cr["has_ready_source"])
        self.assertEqual(cr["ready_source_missing_tiles"], 0)
        text = mod.render_text(rep, 50)
        self.assertIn("可收来源: <缺失>", text)
        self.assertIn("无法判定·旧 Mod", text)
        blob = " ".join(rep.get("undecidable") or [])
        self.assertIn("readySource", blob)
        self.assertEqual((rep["red"] or {}).get("total"), 0)


class TestScopeShedAccounting(unittest.TestCase):
    """task-187（dev task-168 规模取舍）：`scope_*` 事件的桶 / 呈现 / 可证伪 ⚠。

    口径红线：`scope_shed` 是**策略性取舍、不是豁免额度** —— brain 把它从目标池与守卫理由里扣掉，
    但 `_leftover` 一字不改、认输格仍留在会计里 ⇒ 当天照样如实不 VERIFIED。
    ⇒ 本工具的 ⚠「有 `scope_shed` 却自称 VERIFIED」**只警告、绝不进 rc**（判决权在
    `checks.no_unmet_stages` / `checks.watered_outdoor`）；缺事件 = 旧账本 ⇒【无法判定】（缺失 ≠ 0）。
    """

    SHED_EVENTS = [
        {"event": "scope_loaded", "t": 1.0, "path": "logs/x-scope.json", "zones": ["field_nw"]},
        {"event": "scope_shed", "t": 20.0, "zone": "field_nw", "tiles": 21,
         "live_crops": 14, "water_capacity": 9, "deficit": 5, "target_tiles": 21,
         "harvested_steps": 2, "reason": "今天有 5 格活苗浇不完 ⇒ 主动放弃 field_nw"},
        {"event": "scope_shed_refused", "t": 21.0, "zone": "field_ne", "reason": "already_today",
         "limit": 1},
        {"event": "scope_shed_refused", "t": 22.0, "zone": "field_se", "reason": "cap",
         "shed_tiles": 21, "this_zone": 30, "cap_tiles": 40, "farm_workable": 118},
        {"event": "scope_released", "t": 23.0, "zone": "field_sw",
         "reason": "zone_has_no_unwatered_crops", "tiles": 3, "live_crops_now": 0},
        {"event": "scope_harvest", "t": 24.0, "zone": "field_nw", "tiles": 1,
         "targets": [[60, 29]]},
        {"event": "scope_saved", "t": 900.0, "path": "logs/x-scope.json", "zones": 1, "written": 1},
    ]

    def _day(self, day, *, extra=(), scope_end=None):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 950.0, "day": day, "ended_by": "sleep",
               "ended_reason": "night", "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 9, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "ok_steps": 9, "skipped_steps": 0, "failed_steps": 0, "notes": [],
               "final": final(nxt),
               "final_water": {"t": 949.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        if scope_end is not None:
            end.update(scope_end)
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ledger(tmp, name, events)
            return report_for(path, days=days)

    def test_events_have_buckets_and_are_not_unmapped(self):
        checks = [
            ("scope_shed", "scope_sheds"), ("scope_shed_refused", "scope_shed_refusals"),
            ("scope_released", "scope_releases"), ("scope_harvest", "scope_harvests"),
            ("scope_harvest_failed", "scope_harvest_failures"), ("scope_loaded", "scope_loads"),
            ("scope_saved", "scope_saves"), ("scope_save_failed", "scope_save_failures"),
            ("scope_rejected", "scope_rejections"),
        ]
        for ev_name, bucket in checks:
            self.assertEqual(mod.EVENT_BUCKETS.get(ev_name), bucket, ev_name)
            self.assertIn(bucket, mod.NEW_EVENT_BUCKETS, bucket)
        rep = self._report(self._day([1, "fall", 9], extra=self.SHED_EVENTS), "t187_buckets.jsonl")
        self.assertEqual(sorted((rep.get("unmapped_events") or {}).keys()), [],
                         "新事件必须全部有桶、不许静默丢弃")

    def test_shed_info_is_visible_and_not_red(self):
        rep = self._report(self._day([1, "fall", 9], extra=self.SHED_EVENTS), "t187_info.jsonl")
        ss = rep["scope_shed"]
        self.assertTrue(ss["has_events"])
        self.assertEqual(ss["shed_events"], 1)
        self.assertEqual(ss["shed_tiles"], 21)
        self.assertEqual(ss["shed_zones"], ["field_nw"])
        self.assertEqual(ss["refused_events"], 2)
        self.assertEqual(ss["refused_reasons"], {"already_today": 1, "cap": 1})
        self.assertEqual(ss["released_events"], 1)
        self.assertEqual(ss["harvest_events"], 1)
        self.assertEqual(ss["harvest_targets"], 1)
        self.assertEqual(ss["load_events"], 1)
        self.assertEqual(ss["saved_events"], 1)
        text = mod.render_text(rep, 50)
        self.assertIn("规模取舍: 主动认输 1 区次", text)
        self.assertIn("scope_shed` **只作 info、不进 checks**", text)
        self.assertEqual(rep["red"]["total"], 0, "scope_* 一律 info ⇒ 不进 rc")

    def test_shed_with_verified_is_warning_not_red(self):
        rep = self._report(self._day([1, "fall", 9], extra=self.SHED_EVENTS), "t187_warn.jsonl")
        ss = rep["scope_shed"]
        self.assertEqual(ss["warn_verified_with_shed_lines"], [3])
        text = mod.render_text(rep, 50)
        self.assertIn("有 `scope_shed` 却自称 VERIFIED", text)
        self.assertEqual(rep["red"]["total"], 0, "⚠ 只警告、绝不进 rc")

    def test_shed_without_day_end_snapshot_is_warning(self):
        rep = self._report(self._day([1, "fall", 9], extra=self.SHED_EVENTS), "t187_nosnap.jsonl")
        self.assertEqual(rep["scope_shed"]["day_end_shed_days"], 0)
        self.assertTrue(rep["scope_shed"]["warn_shed_without_day_end"])
        self.assertIn("day_end 没有 `scope_shed` 快照", mod.render_text(rep, 50))

    def test_day_end_snapshot_is_counted(self):
        rep = self._report(self._day(
            [1, "fall", 9], extra=self.SHED_EVENTS,
            scope_end={"scope_shed": {"field_nw": {"tiles": 21, "live_crops_at_shed": 14}},
                       "scope_shed_tiles": 21}), "t187_snap.jsonl")
        self.assertEqual(rep["scope_shed"]["day_end_shed_days"], 1)
        self.assertFalse(rep["scope_shed"]["warn_shed_without_day_end"])

    def test_missing_scope_events_is_undecidable_not_pass(self):
        rep = self._report(self._day([1, "fall", 9]), "t187_old.jsonl")
        self.assertFalse(rep["scope_shed"]["has_events"])
        blob = " ".join(rep.get("undecidable") or [])
        self.assertIn("没有任何 task-168 的 `scope_*` 事件", blob)
        self.assertIn("缺失 ≠ 0", blob)
        self.assertIn("规模取舍: <缺失>", mod.render_text(rep, 50))
        self.assertEqual(rep["red"]["total"], 0, "缺失 ⇒【无法判定】，既不判红也不判通过")

    def test_field_probes_cover_scope_keys(self):
        probes = {p for _, p, _ in mod.FIELD_PROBES}
        for probe in ("live_crops_at_shed", "scope_shed_tiles", "scope_shed",
                      "scope_shed_refused", "scope_released", "scope_harvest",
                      "scope_harvest_failed", "scope_loaded", "scope_saved",
                      "scope_save_failed", "scope_rejected"):
            self.assertIn(probe, probes, probe)


class TestScopeTerminalAccounting(unittest.TestCase):
    """task-194（dev task-192）：`scope_*` 末态记账（释放扣减 / `shed_ever` 释放不清）。

    口径：`day_end.scope_shed*` = **日终末态**（当天毛认输 − 当天释放）；毛−释放 ≠ 末态 ⇒ ⚠ info
    （**不进 rc**）；三个新字段（`scope_released.shed_tiles_remaining`、
    `scope_loaded.shed_ever_total`、`scope_saved.shed_ever_total`）缺失 ⇒【无法判定】（缺失 ≠ 0，
    六本旧账本据此不翻红）。
    """

    def _events(self, *, gross=21, released=3, remaining=18, terminal=None, ever=21,
                with_new_fields=True, with_scope=True):
        day = [1, "fall", 26]
        evs = [day_start(day)]
        if with_scope:
            evs.append({"event": "scope_shed", "t": 20.0, "zone": "field_nw", "tiles": gross,
                        "live_crops": 14, "water_capacity": 9, "deficit": 5,
                        "harvested_steps": 0, "reason": "今天有 5 格活苗浇不完"})
            rel = {"event": "scope_released", "t": 30.0, "zone": "field_nw",
                   "reason": "farm_deficit_zero", "tiles": released, "live_crops_now": 0}
            load = {"event": "scope_loaded", "t": 1.5, "path": "logs/x-scope.json",
                    "zones": ["field_nw"], "tiles_total": gross}
            saved = {"event": "scope_saved", "t": 900.0, "path": "logs/x-scope.json",
                     "zones": 1, "written": 1}
            if with_new_fields:
                rel["shed_tiles_remaining"] = remaining
                load["shed_ever_total"] = ever
                saved["shed_ever_total"] = ever
            evs += [load, rel, saved]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 950.0, "day": day, "ended_by": "sleep",
               "ended_reason": "night", "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 9, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
               "ok_steps": 9, "skipped_steps": 0, "failed_steps": 0, "notes": [],
               "final": final([1, "fall", 27]),
               "final_water": {"t": 949.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        if with_scope:
            _tiles = gross - released if terminal is None else terminal
            end["scope_shed"] = {"field_nw": {"tiles": _tiles, "live_crops_at_shed": 14}}
            end["scope_shed_tiles"] = _tiles
        evs.append(end)
        return evs

    def _report(self, events, name):
        with tempfile.TemporaryDirectory() as tmp:
            return report_for(write_ledger(tmp, name, events), days=1)

    def test_new_fields_are_probed_and_visible(self):
        rep = self._report(self._events(), "t194_ok.jsonl")
        ss = rep["scope_shed"]
        self.assertEqual(ss["released_remaining"], [18], "释放后的当天余额")
        self.assertEqual(ss["shed_ever_loaded"], [21])
        self.assertEqual(ss["shed_ever_saved"], [21])
        self.assertEqual(ss["warn_terminal_mismatch_lines"], [], "毛−释放=末态 ⇒ 不该报 ⚠")
        self.assertEqual(rep["red"]["total"], 0)
        text = mod.render_text(rep, 50)
        self.assertIn("末态口径（释放已扣减）", text)
        self.assertIn("累计 `shed_ever`（释放不清）载入 [21] / 写回 [21]", text)
        blob = " ".join(rep.get("undecidable") or [])
        self.assertNotIn("event:scope_released.shed_tiles_remaining", blob,
                         "字段在 ⇒ 不该报【无法判定】")

    def test_terminal_mismatch_is_warning_not_red(self):
        rep = self._report(self._events(gross=21, released=3, remaining=18, terminal=21),
                           "t194_bad.jsonl")
        ss = rep["scope_shed"]
        self.assertTrue(ss["warn_terminal_mismatch_lines"], "有 scope_released 却没下降 ⇒ ⚠")
        self.assertEqual(ss["warn_terminal_mismatch_days"], [rep["days"][-1]["label"]])
        self.assertEqual(rep["red"]["total"], 0, "末态对不上只记 ⚠、**绝不进 rc**")
        self.assertIn("末态与毛−释放对不上", mod.render_text(rep, 50))

    def test_missing_new_fields_is_undecidable_not_red(self):
        rep = self._report(self._events(with_new_fields=False), "t194_oldfields.jsonl")
        blob = " ".join(rep.get("undecidable") or [])
        self.assertIn("event:scope_released.shed_tiles_remaining", blob)
        self.assertIn("event:scope_loaded.shed_ever_total", blob)
        self.assertIn("event:scope_saved.shed_ever_total", blob)
        self.assertEqual(rep["scope_shed"]["released_remaining"], [])
        self.assertIn("累计 `shed_ever` <缺失>", mod.render_text(rep, 50))
        self.assertEqual(rep["red"]["total"], 0, "缺新字段 ⇒【无法判定】，不翻红")

    def test_old_ledger_without_scope_is_undecidable_not_red(self):
        rep = self._report(self._events(with_scope=False), "t194_noscope.jsonl")
        self.assertFalse(rep["scope_shed"]["has_events"])
        self.assertEqual(rep["red"]["total"], 0)
        self.assertIn("规模取舍: <缺失>", mod.render_text(rep, 50))

    def test_release_of_carried_zone_is_not_a_mismatch(self):
        """隔天释放前一天的区：`scope_shed_tiles` 当天是 0 ⇒ 不该误报「对不上」。"""
        events = [day_start([1, "fall", 26]),
                  {"event": "scope_released", "t": 30.0, "zone": "field_nw",
                   "reason": "zone_has_no_unwatered_crops", "tiles": 7,
                   "live_crops_now": 0, "shed_tiles_remaining": 0},
                  {"event": "scope_shed", "t": 20.0, "zone": "field_ne", "tiles": 4,
                   "live_crops": 2, "water_capacity": 1, "deficit": 1, "reason": "浇不完"}]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        events.append({"event": "day_end", "t": 950.0, "day": [1, "fall", 26], "ended_by": "sleep",
                       "ended_reason": "night", "verified": True, "checks": checks,
                       "stages": [], "ok_steps": 4, "skipped_steps": 0, "failed_steps": 0,
                       "notes": [], "final": final([1, "fall", 27]),
                       "scope_shed": {"field_ne": {"tiles": 4, "live_crops_at_shed": 2}},
                       "scope_shed_tiles": 4,
                       "final_water": {"t": 949.0, "location": "Farm", "tiles": 84, "crops": 31,
                                       "dry": 0, "scope": "farm"}})
        rep = self._report(events, "t194_carried.jsonl")
        self.assertEqual(rep["scope_shed"]["warn_terminal_mismatch_lines"], [],
                         "释放的是前一天的区 ⇒ 不参与当天扣减（4 == 4）")
        self.assertEqual(rep["red"]["total"], 0)


class TestSlotReliefAndInventoryBlocked(unittest.TestCase):
    """task-202（dev task-198 `62e9089`）：背包满 ⇒ 腾格回路 / 诚实「背包阻塞」收尾。

    口径红线：`slot_relief` = 回路真动过（**不是失败、不是豁免**，`freed==0` 的日子要点名）；
    `inventory_blocked` = **如实上限**（`ended_by=inventory_blocked`、`verified=false`、
    `failed_steps=0`），不许写成失败或豁免；唯一可证伪 ⚠ = 那天却自称 VERIFIED（不进 rc）。
    """

    def _report(self, events, name):
        with tempfile.TemporaryDirectory() as tmp:
            return report_for(write_ledger(tmp, name, events), days=1)

    def _events(self, *, relief=True, freed=3, shipped=True, blocked=False,
                ended_by="sleep", verified=True):
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        ev = [day_start([1, "spring", 12])]
        if relief:
            ev.append({"event": "slot_relief", "t": 10.0, "need": 3, "freed": freed,
                       "shipped": shipped, "freeSlots_before": 1,
                       "freeSlots_after": 1 + int(freed), "round": 1, "max_rounds": 3,
                       "reserve": 1, "note": "腾格"})
            ev.append({"event": "slot_relief_noted", "t": 9.0, "free_slots": 1, "reserve": 1,
                       "round": 1, "limit": 3, "note": "低水位先腾格"})
        if blocked:
            ev.append({"event": "inventory_blocked", "t": 20.0, "free_slots": 0, "reserve": 1,
                       "rounds": 2, "limit": 3, "reason": "no_sellable", "note": "如实收尾"})
        ev.append({"event": "day_end", "t": 950.0, "day": [1, "spring", 12],
                   "ended_by": ended_by, "ended_reason": "night", "verified": verified,
                   "checks": checks,
                   "stages": [{"stage": "water_area", "tiles": 10, "ok": 10, "skipped": 0,
                               "failed": 0}],
                   "ok_steps": 10, "skipped_steps": 0, "failed_steps": 0, "notes": [],
                   "final": final([1, "spring", 13]),
                   "final_water": {"t": 949.0, "location": "Farm", "tiles": 84, "crops": 31,
                                   "dry": 0, "scope": "farm"}})
        return ev

    def test_events_have_buckets_and_are_not_unmapped(self):
        rep = self._report(self._events(blocked=True), "t202_buckets.jsonl")
        self.assertEqual(rep["events"].get("slot_relief"), 1)
        self.assertEqual(rep["events"].get("slot_relief_noted"), 1)
        self.assertEqual(rep["events"].get("inventory_blocked"), 1)
        self.assertEqual(rep["unmapped_events"], {}, "三个新事件都必须有桶、不许落未映射")

    def test_slot_relief_is_info_not_failure(self):
        rep = self._report(self._events(), "t202_relief.jsonl")
        sr = rep["slot_relief"]
        self.assertEqual(sr["events"], 1)
        self.assertEqual(sr["freed_total"], 3)
        self.assertEqual(sr["shipped"], 1)
        self.assertEqual(sr["zero_freed_lines"], [])
        self.assertEqual(rep["red"]["total"], 0, "腾格回路是信息项 ⇒ 不判红")
        text = mod.render_text(rep, 50)
        self.assertIn("腾格回路: `slot_relief` 1 次", text)
        self.assertIn("不是失败、不是豁免", text)

    def test_freed_zero_is_flagged_not_red(self):
        rep = self._report(self._events(freed=0), "t202_zero.jsonl")
        sr = rep["slot_relief"]
        self.assertEqual(sr["freed_total"], 0)
        self.assertTrue(sr["zero_freed_lines"], "腾格尝试却没真腾出格 ⇒ 必须点名")
        self.assertEqual(rep["red"]["total"], 0)
        text = mod.render_text(rep, 50)
        self.assertIn("腾格尝试却没真腾出格（freed=0）", text)
        self.assertIn("腾格回路空转", " ".join(a["text"] for a in rep["advice"]))

    def test_inventory_blocked_is_honest_limit_not_failure(self):
        rep = self._report(self._events(relief=False, blocked=True,
                                        ended_by="inventory_blocked", verified=False),
                           "t202_blocked.jsonl")
        ib = rep["inventory_blocked"]
        self.assertEqual(ib["events"], 1)
        self.assertEqual(ib["ended_by_days"], 1)
        self.assertEqual(ib["warn_verified_lines"], [])
        self.assertEqual(rep["red"]["total"], 0, "如实上限 ⇒ **不是失败**、不判红")
        text = mod.render_text(rep, 50)
        self.assertIn("背包阻塞: `inventory_blocked` 1 次", text)
        self.assertIn("如实上限", text)

    def test_inventory_blocked_with_verified_is_warning_not_red(self):
        rep = self._report(self._events(relief=False, blocked=True,
                                        ended_by="inventory_blocked", verified=True),
                           "t202_verified.jsonl")
        ib = rep["inventory_blocked"]
        self.assertTrue(ib["warn_verified_lines"], "背包阻塞当天却自称 VERIFIED ⇒ 互斥组合 ⚠")
        self.assertEqual(rep["red"]["total"], 0, "只警告、**不进 rc**")
        self.assertIn("背包阻塞当天却自称 VERIFIED", mod.render_text(rep, 50))

    def test_old_ledger_without_events_is_missing_not_zero(self):
        rep = self._report(self._events(relief=False), "t202_old.jsonl")
        self.assertFalse(rep["slot_relief"]["has_events"])
        self.assertFalse(rep["inventory_blocked"]["has_events"])
        self.assertEqual(rep["red"]["total"], 0)
        text = mod.render_text(rep, 50)
        self.assertIn("腾格回路: <缺失>", text)
        self.assertIn("背包阻塞: <缺失>", text)
        blob = " ".join(rep.get("undecidable") or [])
        self.assertIn("event:slot_relief", blob)
        self.assertIn("event:inventory_blocked", blob)


class TestToolUpgradeAccounting(unittest.TestCase):
    """task-207（dev task-205 工具升级全链）：桶 / 可见性 / 可证伪 ⚠ /【无法判定】。

    口径红线：`upgrade_tool` 是**动作、不是豁免** —— 判据只认观测差分（钱减少 + 工具被
    `toolBeingUpgraded` 拿走 + 等级变化），回执只是声明；`tool_upgrade_skipped` 与
    `tool_upgrade_blocked_work` 是**如实跳过**（钱/材料不够、等取回、背包满、在途期间工具不在
    身上）⇒ 一律 info、绝不进 rc。唯一可证伪 ⚠ = 自报成功却 `toolBeingUpgraded` 没出现、
    或钱差与货架价对不上（只警告）。缺事件 = 旧账本 ⇒【无法判定】（缺失 ≠ 0）。
    """

    UPGRADE_EVENTS = [
        {"event": "upgrade_tool", "t": 100.0, "ok": True, "code": "ok",
         "reason": "升级成功（观测差分：钱 −2000、工具被拿走）", "tool": "pickaxe",
         "before": {"money": 4268, "tier": 0, "being": None, "days_left": 0,
                    "trade_item": "(O)334", "trade_have": 5, "location": "Blacksmith"},
         "after": {"money": 2268, "money_delta": -2000, "price": 2000,
                   "money_delta_matches_price": True, "tier": 1, "being": "Copper Pickaxe",
                   "days_left": 2, "trade_item": "(O)334", "trade_have": 0}},
        {"event": "upgrade_tool", "t": 110.0, "ok": False, "code": "failed",
         "reason": "回执 no_action（没点到 Upgrade 选项）", "tool": "axe",
         "before": {"money": 2268, "tier": 0}, "after": {"money": 2268, "money_delta": 0}},
        {"event": "pickup_tool", "t": 120.0, "ok": False, "code": "no_slot",
         "reason": "背包满，取不回", "before": {"being": "Copper Pickaxe", "days_left": 0,
                                              "tier": 0, "free_slots": 0},
         "after": {"being": "Copper Pickaxe", "days_left": 0, "tier": 0}},
        {"event": "tool_upgrade_skipped", "t": 130.0, "reason": "钱/材料不够", "money": 2268},
        {"event": "tool_upgrade_skipped", "t": 131.0, "reason": "有工具在升级中，等取回",
         "action": "wait", "being": "Copper Pickaxe", "days_left": 1, "free_slots": 8},
        {"event": "tool_upgrade_blocked_work", "t": 140.0,
         "stages": ["till_area", "clear_dead"], "being": "Copper Pickaxe",
         "note": "工具在 Clint 那里升级，相关阶段暂停（不是失败，是工具不在身上）"},
    ]

    OK_WITHOUT_BEING = {
        "event": "upgrade_tool", "t": 100.0, "ok": True, "code": "ok",
        "reason": "升级成功（但观测里没有工具被拿走）", "tool": "hoe",
        "before": {"money": 5000, "tier": 0},
        "after": {"money": 3000, "money_delta": -2000, "price": 2000, "being": None},
    }

    MONEY_MISMATCH = {
        "event": "upgrade_tool", "t": 100.0, "ok": True, "code": "ok",
        "reason": "升级成功（钱差与货架价对不上）", "tool": "can",
        "before": {"money": 5000, "tier": 0},
        "after": {"money": 3500, "money_delta": -1500, "price": 2000, "being": "Copper Watering Can"},
    }

    def _day(self, day, *, extra=()):
        nxt = [day[0], day[1], day[2] + 1]
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                  "watered_outdoor": True}
        end = {"event": "day_end", "t": 950.0, "day": day, "ended_by": "sleep",
               "ended_reason": "night", "verified": True, "checks": checks,
               "stages": [{"stage": "water_area", "ok": 9, "skipped": 0, "failed": 0,
                           "env_block": 0, "inconclusive": 0, "stopped": None,
                           "leftover": 0}],
               "ok_steps": 9, "skipped_steps": 0, "failed_steps": 0, "notes": [],
               "final": final(nxt),
               "final_water": {"t": 949.0, "location": "Farm", "tiles": 84, "crops": 31,
                               "dry": 0, "scope": "farm"}}
        return [day_start(day), *extra, end]

    def _report(self, events, name, *, days=1):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ledger(tmp, name, events)
            return report_for(path, days=days)

    def test_events_have_buckets_and_are_not_unmapped(self):
        checks = [("upgrade_tool", "tool_upgrades"), ("pickup_tool", "tool_pickups"),
                  ("tool_upgrade_skipped", "tool_upgrade_skips"),
                  ("tool_upgrade_blocked_work", "tool_upgrade_blocks")]
        for ev_name, bucket in checks:
            self.assertEqual(mod.EVENT_BUCKETS.get(ev_name), bucket, ev_name)
            self.assertIn(bucket, mod.NEW_EVENT_BUCKETS, bucket)
        rep = self._report(self._day([1, "fall", 9], extra=self.UPGRADE_EVENTS),
                           "t207_buckets.jsonl")
        self.assertEqual(sorted((rep.get("unmapped_events") or {}).keys()), [],
                         "新事件必须全部有桶、不许静默丢弃")

    def test_upgrade_info_is_visible_and_not_red(self):
        rep = self._report(self._day([1, "fall", 9], extra=self.UPGRADE_EVENTS),
                           "t207_info.jsonl")
        tu = rep["tool_upgrade"]
        self.assertTrue(tu["has_events"])
        self.assertEqual(tu["upgrade_events"], 2)
        self.assertEqual(tu["ok"], 1)
        self.assertEqual(tu["failed"], 1)
        self.assertEqual(tu["kinds"], {"pickaxe": 1, "axe": 1})
        self.assertEqual(tu["tiers_before"], {"0": 2})
        self.assertEqual(tu["tiers_after"], {"1": 1},
                         "失败那行没读到 tier ⇒ 不编造（缺失 ≠ 0；只数真实出现的值）")
        self.assertEqual(tu["prices"], {"2000": 1})
        self.assertEqual(tu["pickup_events"], 1)
        self.assertEqual(tu["pickup_failed"], 1)
        self.assertEqual(len(tu["pickup_no_slot_lines"]), 1, "取回失败要留痕（不是硬失败）")
        self.assertEqual(tu["skip_events"], 2)
        self.assertEqual(tu["skip_actions"], {"wait": 1})
        self.assertEqual(tu["blocked_events"], 1)
        self.assertEqual(tu["blocked_stages"], {"till_area": 1, "clear_dead": 1})
        self.assertEqual(tu["warn_ok_without_being_lines"], [])
        self.assertEqual(tu["warn_money_mismatch_lines"], [])
        self.assertEqual(rep["red"]["total"], 0, "升级/跳过/阻塞一律不进 rc")
        self.assertEqual(rep["red"]["subjects"], [],
                         "升级链任何形态都不该进红色 subject 清单")
        text = mod.render_text(rep, 20)
        self.assertIn("工具升级: 升级动作 2 次", text)
        self.assertIn("如实跳过 2 次", text)
        self.assertIn("在途阻塞留痕 1 次", text)
        self.assertIn("不是豁免", text)
        self.assertIn("先腾格", text, "取回 no_slot 要提示腾格，而不是判失败")

    def test_ok_without_being_is_warning_not_red(self):
        rep = self._report(self._day([1, "fall", 9], extra=[self.OK_WITHOUT_BEING]),
                           "t207_warn_being.jsonl")
        tu = rep["tool_upgrade"]
        self.assertEqual(tu["ok"], 1)
        self.assertGreaterEqual(len(tu["warn_ok_without_being_lines"]), 1)
        self.assertEqual(rep["red"]["total"], 0, "⚠ 只警告、不进 rc")
        text = mod.render_text(rep, 20)
        self.assertIn("自报升级成功却没有", text)
        adv = " ".join(a.get("text", "") for a in (rep.get("advice") or []))
        self.assertIn("观测差分对不上", adv)

    def test_money_mismatch_is_warning_not_red(self):
        rep = self._report(self._day([1, "fall", 9], extra=[self.MONEY_MISMATCH]),
                           "t207_warn_money.jsonl")
        tu = rep["tool_upgrade"]
        self.assertEqual(len(tu["warn_money_mismatch_lines"]), 1)
        self.assertEqual(tu["money_deltas"], [-1500])
        self.assertEqual(rep["red"]["total"], 0, "钱差对不上只警告、不进 rc（钱可能在别处变动）")
        self.assertIn("钱差与货架价不一致", mod.render_text(rep, 20))

    def test_blocked_then_verified_is_warning_not_red(self):
        rep = self._report(self._day([1, "fall", 9], extra=[self.UPGRADE_EVENTS[-1]]),
                           "t207_block_verified.jsonl")
        tu = rep["tool_upgrade"]
        self.assertEqual(tu["blocked_events"], 1)
        self.assertGreaterEqual(len(tu["blocked_then_verified_lines"]), 1,
                                "在途暂停却自称 VERIFIED ⇒ 互斥组合要可见")
        self.assertEqual(rep["red"]["total"], 0, "互斥组合是 ⚠，不进 rc（判决权在 checks）")

    def test_missing_events_is_undecidable_not_pass(self):
        rep = self._report(self._day([1, "fall", 9]), "t207_missing.jsonl")
        tu = rep["tool_upgrade"]
        self.assertFalse(tu["has_events"] or tu["has_pickup"] or tu["has_skip"]
                         or tu["has_blocked"])
        text = mod.render_text(rep, 20)
        self.assertIn("工具升级: <缺失>", text)
        und = " ".join(rep.get("undecidable") or [])
        self.assertIn("task-205 的工具升级事件", und)
        self.assertIn("缺失 ≠ 0", und)
        self.assertEqual(rep["red"]["total"], 0, "缺失只记【无法判定】，绝不因此判红/判通过")


class TestIntentCoverageAndGaps(unittest.TestCase):
    """task-220（Lead）：§8 意图-执行对账 + 能力缺口清单（brain task-219 `fc147a7`）。

    口径（`docs/_0.7.39-p0-patches.md` P0-4/P0-5、`docs/_run10-criteria.md` §8.2/8.2b/8.2c/8.3）：
    证据 = `day_end.intent_coverage[]` + `<journal>-gaps.json`；旧账本没有这两样 ⇒
    **一律【无法判定】，绝不判红**（缺失 ≠ 0）；`ACTIONLESS_TASKS` 不算"有动作意图"；
    缺口/原因码只作证据，**不豁免、不进 checks/rc**；§8 的红只由本工具判
    （`tools/verify-run3.py` 对 §8 只出 info）。
    """

    _CHECKS = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
               "crops_watered": True, "day_justified": True, "watered_outdoor": True,
               "no_unmet_stages": True}
    _FW = {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0, "scope": "farm"}

    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mod.main(argv)
        return rc, buf.getvalue()

    def _ledger(self, name, *, plans=None, coverage=None, gaps=None, gaps_schema=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        extra = []
        if plans is not None:
            extra.append({"event": "decision", "t": 2.0, "day": MODAL_DAY, "zone": "field_ne",
                          "source": "llm", "llm": True, "boundary": None, "intents": [],
                          "plans": plans})
        overrides = {"checks": dict(self._CHECKS), "final_water": dict(self._FW)}
        if coverage is not None:
            overrides["intent_coverage"] = coverage
        path = write_ledger(tmp.name, name, integrity_ledger(
            extra_events=extra, day_end_overrides=overrides))
        if gaps is not None:
            gp = os.path.join(tmp.name, os.path.splitext(name)[0] + "-gaps.json")
            with open(gp, "w", encoding="utf-8") as fh:
                json.dump({"schema": gaps_schema or mod.GAPS_SCHEMA, "runs": 1, "gaps": gaps},
                          fh, ensure_ascii=False)
        return path

    def _rec(self, ident="1#01", task="clear_area", *, steps=3, requested=3, ok=3, failed=0,
             unexecuted=0, reasons=None, **kw):
        rec = {"intent_id": ident, "task": task, "source": "llm", "area_hint": "field_ne",
               "boundary": "", "requested_tiles": requested, "ok_tiles": ok,
               "failed_tiles": failed, "unexecuted_tiles": unexecuted,
               "executed_steps": steps, "reasons": dict(reasons or {}),
               "reasons_are_intent_level": False}
        rec.update(kw)
        return rec

    def _gap(self, *, kind="fruitTree", tool="axe", reason="deferred_capability", count=1,
             first="1 fall 7", last="1 fall 7", tiles=None, src="agentfarm"):
        return {"kind": kind, "tool": tool, "reason": reason, "count": count,
                "first_seen": first, "last_seen": last,
                "sample_tiles": tiles if tiles is not None else [[60, 29]], "src": src}

    def _subjects(self, rep, cat):
        return subjects(rep["categories"][cat])
    # ---- 与 brain 源码同步（漂移即红，不许手抄常量） ----

    def test_reason_codes_and_actionless_match_brain_source(self):
        with open(BRAIN_LONG_RUN, encoding="utf-8") as fh:
            src = fh.read()
        m = re.search(r"INTENT_REASON_CODES[^=]*=\s*\((.*?)\)", src, re.S)
        self.assertIsNotNone(m, "brain 侧找不到 INTENT_REASON_CODES 字面量")
        brain_codes = set(re.findall(r'"([a-z_]+)"', m.group(1)))
        self.assertTrue(brain_codes)
        self.assertEqual(brain_codes - set(mod.INTENT_REASON_CODES), set(),
                         "analyzer 闭合集必须覆盖 brain 的全部原因码（否则集内码会被误判红）")
        m2 = re.search(r"ACTIONLESS_TASKS[^=]*=\s*\((.*?)\)", src, re.S)
        self.assertIsNotNone(m2)
        self.assertEqual(set(re.findall(r'"([a-z_]+)"', m2.group(1))), set(mod.ACTIONLESS_TASKS))

    def test_deferred_kinds_match_brain_source(self):
        with open(os.path.join(ROOT, "brain", "agentfarm", "planner.py"), encoding="utf-8") as fh:
            src = fh.read()
        m = re.search(r"^DEFERRED_KINDS[^=]*=\s*\{(.*?)\}", src, re.M | re.S)
        self.assertIsNotNone(m, "planner.py 找不到 DEFERRED_KINDS 字面量")
        brain_kinds = set(re.findall(r'"([A-Za-z]+)"\s*:', m.group(1)))
        self.assertEqual(brain_kinds, set(mod.DEFERRED_KINDS),
                         "DEFERRED_KINDS 两侧必须一字不差（§8.3.5 的『暂不支持』白名单）")

    # ---- 判红 7 条 ----

    def test_plan_without_coverage_is_red(self):
        path = self._ledger("plan_only.jsonl", plans=[
            {"intent_id": "1#01", "task": "clear_area", "area_hint": "field_ne", "source": "llm"}],
            coverage=[])
        rep = report_for(path, days=1)
        self.assertIn("missed:intent_no_execution", self._subjects(rep, "intent"),
                      "有计划却没有执行对账 = 无声缩水（§8.3.1）")
        rc, _ = self._run(["--journal", path, "--days", "1"])
        self.assertEqual(rc, 1)

    def test_zero_steps_without_reason_is_red(self):
        path = self._ledger("zero_steps.jsonl", coverage=[
            self._rec("1#02", "till_area", steps=0, requested=0, ok=0)])
        rep = report_for(path, days=1)
        self.assertIn("missed:intent_no_reason:till_area", self._subjects(rep, "intent"))
        _rc, out = self._run(["--journal", path, "--days", "1"])
        self.assertIn("executed_steps=0 却无原因码", out)

    def test_actionless_task_without_reason_is_not_red(self):
        path = self._ledger("actionless.jsonl", coverage=[
            self._rec("1#03", "sleep", steps=0, requested=0, ok=0)])
        rep = report_for(path, days=1)
        self.assertEqual(rep["red"]["total"], 0, "sleep/review 这类不算有动作意图（§8.2c）")
        self.assertFalse([s for s in self._subjects(rep, "intent") if s.startswith("missed:intent")])

    def test_bad_reason_code_is_red(self):
        path = self._ledger("bad_reason.jsonl", coverage=[
            self._rec("1#04", "clear_area", steps=0, requested=1, ok=0, unexecuted=1,
                      reasons={"made_up_code": 1})])
        rep = report_for(path, days=1)
        self.assertIn("missed:intent_bad_reason:clear_area", self._subjects(rep, "intent"))

    def test_capability_reason_without_gaps_is_red(self):
        path = self._ledger("cap_no_gaps.jsonl", coverage=[
            self._rec("1#05", "clear_area", steps=0, requested=1, ok=0, unexecuted=1,
                      reasons={"tool_level": 1})])
        rep = report_for(path, days=1)
        self.assertIn("missed:intent_gap_missing:clear_area", self._subjects(rep, "intent"))
        self.assertIn("gaps.json", " ".join(rep.get("undecidable") or []))

    def test_tiles_invariant_is_red(self):
        path = self._ledger("invariant.jsonl", coverage=[
            self._rec("1#06", "clear_area", steps=1, requested=5, ok=1, failed=1, unexecuted=1)])
        rep = report_for(path, days=1)
        self.assertIn("missed:intent_tiles_invariant:clear_area", self._subjects(rep, "intent"))

    def test_reason_count_mismatch_is_red(self):
        path = self._ledger("reason_count.jsonl", coverage=[
            self._rec("1#07", "clear_area", steps=1, requested=3, ok=1, failed=0, unexecuted=2,
                      reasons={"no_target": 1})])
        rep = report_for(path, days=1)
        self.assertIn("missed:intent_reason_count:clear_area", self._subjects(rep, "intent"))

    def test_gap_kind_not_deferred_is_red(self):
        path = self._ledger("bad_kind.jsonl", coverage=[self._rec("1#08")],
                            gaps=[self._gap(kind="stone", reason="deferred_capability")])
        rep = report_for(path, days=1)
        self.assertIn("missed:gap_kind_not_deferred", self._subjects(rep, "intent"))

    # ---- 缺口清单：证据可见、只提示不判红、跨日才 ⚠ ----

    def test_gaps_file_is_parsed_and_aggregated(self):
        path = self._ledger("gaps_ok.jsonl", coverage=[self._rec("1#09")],
                            gaps=[self._gap(count=3, tiles=[[60, 29], [61, 29]])],
                            gaps_schema=mod.GAPS_SCHEMA)
        rep = report_for(path, days=1)
        gaps = rep["gaps"]
        self.assertTrue(gaps["exists"])
        self.assertEqual(gaps["item_count"], 1)
        self.assertEqual(gaps["capability_count"], 1)
        self.assertEqual(gaps["runs"][0]["item_count"], 1)
        self.assertEqual(gaps["span_warn"], [], "同一天 ⇒ 不提示修复卡")
        self.assertEqual(rep["red"]["total"], 0, "缺口本身不判红")

    def test_gap_span_three_days_is_warning_not_red(self):
        path = self._ledger("gaps_span.jsonl", coverage=[self._rec("1#10")],
                            gaps=[self._gap(first="1 fall 7", last="1 fall 10")])
        rep = report_for(path, days=1)
        self.assertTrue(rep["gaps"]["span_warn"], "连续 ≥3 天没修复 ⇒ ⚠")
        self.assertEqual(rep["red"]["total"], 0, "⚠ 只提示，不进 rc")

    def test_bad_gaps_schema_is_error_not_red(self):
        path = self._ledger("gaps_bad.jsonl", coverage=[self._rec("1#11")],
                            gaps=[self._gap()], gaps_schema="agentfarm-gaps/999")
        rep = report_for(path, days=1)
        self.assertTrue(rep["gaps"]["exists"], "文件在，但 schema 认识不了")
        self.assertEqual(rep["gaps"]["error"], "bad_schema")
        self.assertEqual(rep["red"]["total"], 0, "schema 不认识 ⇒ 不采信、不判红")

    # ---- 旧账本：缺失 ⇒【无法判定】，不是 0 也不是红 ----

    def test_old_ledger_missing_coverage_is_undecidable_not_red(self):
        path = self._ledger("old.jsonl")
        rep = report_for(path, days=1)
        self.assertEqual(rep["red"]["total"], 0, "缺失 ≠ 0：旧账本不许因§8判红")
        und = " ".join(rep.get("undecidable") or [])
        self.assertIn("intent_coverage", und)
        self.assertIn("intent_coverage[*].executed_steps", und, "FIELD_PROBES 自动探针行（缺失 ≠ 0）")
        self.assertIn("decision.plans[*].intent_id", und)
        self.assertIn("gaps", und)
        rc, _ = self._run(["--journal", path, "--days", "1"])
        self.assertEqual(rc, 0)

    def test_clean_covered_day_has_no_intent_red(self):
        ident = "1#12"
        path = self._ledger("clean_cov.jsonl",
                            plans=[{"intent_id": ident, "task": "clear_area",
                                    "area_hint": "field_ne", "source": "llm"}],
                            coverage=[self._rec(ident)])
        rep = report_for(path, days=1)
        self.assertEqual(rep["red"]["total"], 0)
        self.assertEqual(rep["intent"]["rows"], 1)
        und = " ".join(rep.get("undecidable") or [])
        self.assertNotIn("intent_coverage[*].executed_steps", und,
                         "有对账记录时 FIELD_PROBES 不该再报缺失")
        self.assertNotIn("decision.plans[*].intent_id", und)

    def test_cli_accepts_gaps_dir_and_repairs(self):
        args = mod.parse_args(["--journal", "x.jsonl", "--gaps-dir", "logs",
                               "--repairs", "task-226,task-231"])
        self.assertEqual(args.gaps_dir, "logs")
        self.assertIn("task-226", args.repairs)


class TestTask231GapsProblemAndNoTargetEvidence(unittest.TestCase):
    """task-231（dev task-230 P0-4.4/4.5 + P0-3.3）：gaps 读写失败可判红 + `no_target` 证据包。

    口径（`docs/_run10-criteria.md` §8.2 / §8.3.7）：
      * `no_target` 必须带 `evidence.stage_tiles_empty is True`，否则判红；
      * gaps 读/写失败（`gaps_load_failed` / `gaps_write_failed` 事件，或 `day_end.gaps_problem` 非空）
        = problem ⇒ 判红（brain task-230 P0-4.5 明确要求"写失败必须可判红"）；
      * 旧账本没有这些字段/事件 ⇒ 【无法判定】，**缺失 ≠ 通过**，绝不判红。
    """

    _CHECKS = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
               "crops_watered": True, "day_justified": True, "watered_outdoor": True,
               "no_unmet_stages": True}
    _FW = {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0, "scope": "farm"}

    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mod.main(argv)
        return rc, buf.getvalue()

    def _ledger(self, name, *, extra=(), coverage=None, gaps_problem=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        overrides = {"checks": dict(self._CHECKS), "final_water": dict(self._FW)}
        if coverage is not None:
            overrides["intent_coverage"] = coverage
        if gaps_problem is not None:
            overrides["gaps_problem"] = gaps_problem
        return write_ledger(tmp.name, name, integrity_ledger(
            extra_events=tuple(extra), day_end_overrides=overrides))

    def _rec(self, ident="1#01", task="clear_area", *, steps=0, requested=1, ok=0, failed=0,
             unexecuted=1, reasons=None, **kw):
        rec = {"intent_id": ident, "task": task, "source": "llm", "area_hint": "field_ne",
               "boundary": "", "requested_tiles": requested, "ok_tiles": ok,
               "failed_tiles": failed, "unexecuted_tiles": unexecuted,
               "executed_steps": steps, "reasons": dict(reasons or {}),
               "reasons_are_intent_level": False}
        rec.update(kw)
        return rec

    def _subjects(self, rep):
        return subjects(rep["categories"]["intent"])

    # ---- §8.3.7：no_target 必须有证据包 ----

    def test_no_target_without_evidence_is_red(self):
        path = self._ledger("t231_nt_noev.jsonl", coverage=[
            self._rec(reasons={"no_target": 1})])
        rep = report_for(path, days=1)
        hit = [s for s in self._subjects(rep) if s.startswith("missed:intent_no_target_evidence:")]
        self.assertTrue(hit, f"no_target 无证据必须判红，实际 subjects={self._subjects(rep)}")
        rc, _ = self._run(["--journal", path, "--days", "1"])
        self.assertEqual(rc, 1, "有红 ⇒ 退出码 1（task-65）")

    def test_no_target_with_evidence_is_not_red(self):
        path = self._ledger("t231_nt_ev.jsonl", coverage=[
            self._rec(reasons={"no_target": 1},
                      evidence={"stage_tiles_empty": True, "obs_seq": 42})])
        rep = report_for(path, days=1)
        self.assertFalse([s for s in self._subjects(rep)
                          if s.startswith("missed:intent_no_target_evidence:")],
                         "有 evidence.stage_tiles_empty=true ⇒ 不判红")
        self.assertEqual(rep["red"]["total"], 0)
        und = " ".join(rep.get("undecidable") or [])
        self.assertNotIn("evidence.stage_tiles_empty", und,
                         "有证据包时 FIELD_PROBES 不该再报缺失")

    # ---- P0-4.4/4.5：gaps 读写失败 = problem（可判红） ----

    def test_gaps_load_failed_event_is_red(self):
        path = self._ledger("t231_gload.jsonl", extra=[
            {"event": "gaps_load_failed", "t": 3.0, "day": MODAL_DAY,
             "path": "logs/x-gaps.json", "error": "bad json",
             "archived": "x-gaps.json.bad.1758770000"}])
        rep = report_for(path, days=1)
        self.assertIn("missed:gaps_io_failed:gaps_load_failed", self._subjects(rep))
        rc, out = self._run(["--journal", path, "--days", "1"])
        self.assertEqual(rc, 1)
        self.assertIn("gaps_load_failed", out)

    def test_gaps_write_failed_event_is_red(self):
        path = self._ledger("t231_gwrite.jsonl", extra=[
            {"event": "gaps_write_failed", "t": 3.0, "day": MODAL_DAY,
             "path": "logs/x-gaps.json", "error": "disk full"}])
        rep = report_for(path, days=1)
        self.assertIn("missed:gaps_io_failed:gaps_write_failed", self._subjects(rep))

    def test_gaps_problem_field_is_red(self):
        path = self._ledger(
            "t231_gprob.jsonl",
            coverage=[self._rec(ok=1, requested=1, failed=0, unexecuted=0, steps=1)],
            gaps_problem="缺口清单写失败（只影响提示词，但这是缺陷）：disk full")
        rep = report_for(path, days=1)
        self.assertIn("missed:gaps_problem", self._subjects(rep))
        self.assertEqual(rep["gaps"]["gaps_problem_days"], 1)
        self.assertEqual(rep["gaps"]["io_events"], 0)

    def test_old_ledger_without_gaps_fields_is_undecidable_not_red(self):
        path = self._ledger("t231_old.jsonl")
        rep = report_for(path, days=1)
        self.assertEqual(rep["red"]["total"], 0, "缺失 ≠ 通过：旧账本不许因 gaps 字段判红")
        und = " ".join(rep.get("undecidable") or [])
        self.assertIn("day_end.gaps_problem", und)
        self.assertIn("gaps_load_failed", und)
        self.assertIn("gaps_write_failed", und)

    # ---- 源码漂移（字段/码集/映射表改名会静默失效 ⇒ 必须扫源码） ----

    def test_intent_flag_field_names_match_brain_source(self):
        with open(BRAIN_LONG_RUN, encoding="utf-8") as fh:
            src = fh.read()
        for field in ("reasons_are_intent_level", "bad_reasons", "actionless"):
            self.assertIn(f'"{field}"', src, f"brain 源码里找不到字段 {field}（改名了？）")
        with open(TOOL, encoding="utf-8") as fh:
            tool_src = fh.read()
        for field in ("reasons_are_intent_level", "bad_reasons", "actionless"):
            self.assertIn(field, tool_src, f"analyzer 侧必须引用字段 {field}")

    def test_reason_codes_match_criteria_doc(self):
        with open(os.path.join(ROOT, "docs", "_run10-criteria.md"), encoding="utf-8") as fh:
            doc = fh.read()
        m = re.search(r"目标集合 \*\*12 码\*\*：(.+)", doc)
        self.assertIsNotNone(m, "criteria §8.2 找不到『目标集合 **12 码**』一行")
        doc_codes = set(re.findall(r"`([a-z_]+)`", m.group(1)))
        self.assertEqual(doc_codes, set(mod.INTENT_REASON_CODES_DOC),
                         "analyzer 的 DOC 码集必须与 criteria §8.2 目标集合逐字一致")
        self.assertEqual(set(mod.INTENT_REASON_CODES_BRAIN), doc_codes,
                         "brain 的 12 码必须与文档目标集合一致（task-230 已补 failed）")
        self.assertEqual(set(mod.INTENT_REASON_CODES), doc_codes)

    def test_step_code_to_reason_targets_are_in_closed_set(self):
        with open(BRAIN_LONG_RUN, encoding="utf-8") as fh:
            src = fh.read()
        m = re.search(r"STEP_CODE_TO_REASON[^=]*=\s*\{(.*?)\n\}", src, re.S)
        self.assertIsNotNone(m, "brain 找不到 STEP_CODE_TO_REASON 字面量")
        vals = set(re.findall(r':\s*"([a-z_]*)"', m.group(1)))
        self.assertTrue(vals)
        bad = {v for v in vals if v and v not in mod.INTENT_REASON_CODES}
        self.assertEqual(bad, set(), f"映射表值域超出闭合集：{bad}")

    def test_capability_reason_codes_keep_tool_level(self):
        with open(BRAIN_LONG_RUN, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('return "tool_level"', src,
                      "brain 的 _tile_reason 会给工具不够格的格返回 tool_level")
        self.assertIn("_gaps_merge(reason_rows", src,
                      "这些行同路径写进 gaps ⇒ tool_level 必须算能力缺口（两侧同义）")
        self.assertEqual(tuple(mod.CAPABILITY_REASON_CODES),
                         ("deferred_capability", "tool_level"))


class TestEventWaitAccounting(unittest.TestCase):
    """task-246（dev task-245 `0a13973`）：`event_wait` 有界等待 + `event_blocked` 事件归因。

    口径：`event_wait` 是 **info**（不是失败、不是豁免）；唯一可判红 = `event_blocked` 的
    `eventWaitTries` **有键且 0** 且整本 0 条 `event_wait`（没走等待路径 ⇒ 0.7.42 冬 7 白烧复现）；
    `eventWaitTries` **整键缺失** = task-245 之前的旧 Mod ⇒ 只【无法判定】，绝不判红；
    `eventId` 三态（有值 / null=读不到 / 缺字段=旧 Mod）如实呈现，缺失不许猜。
    """

    def _events(self, *, wait=2, blocked=True, blocked_kind="waited", event_id="992553",
                event_id_key="present", with_ui_id=True):
        day = [1, "fall", 7]
        evs = [day_start(day)]
        if with_ui_id:
            evs[-1]["ui"] = {"eventId": event_id}

        def _put_id(d):
            if event_id_key == "absent":
                return
            d["eventId"] = None if event_id_key == "null" else event_id

        for i in range(wait):
            ev = {"event": "event_wait", "t": 300.0 + i, "tries": i + 1, "limit": 4,
                  "eventUp": True, "hasDialogue": False, "worldSeq": 602 + i,
                  "waitSeconds": 15.0,
                  "note": "事件进行中但没有对话盒：有界等待"}
            _put_id(ev)
            evs.append(ev)
        if blocked:
            ev = {"event": "event_blocked", "t": 340.0, "activeMenu": None,
                  "activeMenuText": None, "dialogueIsQuestion": False,
                  "dialogueResponses": [], "tile": [64, 15], "timeOfDay": 600,
                  "worldSeq": 606, "advance_steps": 0, "advance_calls": 0,
                  "stall_streak": 0, "note": "游戏事件挂住（ui.eventUp=true）"}
            _put_id(ev)
            if blocked_kind == "waited":
                ev["eventWaitTries"] = max(wait, 1)
                ev["eventWaitSeconds"] = 15.0 * max(wait, 1)
            elif blocked_kind == "zero":
                ev["eventWaitTries"] = 0
                ev["eventWaitSeconds"] = 0.0
            evs.append(ev)
        evs.append({"event": "day_end", "t": 900.0, "day": day, "day_text": "1年 fall 7日",
                    "ended_by": "blocked_event" if blocked else "sleep",
                    "ended_reason": "night", "verified": False,
                    "checks": {"slept_by_us": False, "no_blocking_modal": False,
                               "no_hard_failures": True, "crops_watered": True,
                               "day_justified": True, "no_unmet_stages": True},
                    "stages": [], "outcomes": [], "ok_steps": 0, "skipped_steps": 0,
                    "failed_steps": 0, "notes": [], "final": final([1, "fall", 8])})
        return evs

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def test_event_wait_has_bucket_and_is_info(self):
        """`event_wait` 有桶、有头部行、是 info：**不许**因为它多出一条红。"""
        rep = self._report(self._events(wait=2, blocked=False), "ew.jsonl")
        self.assertIn("event_waits", mod.NEW_EVENT_BUCKETS)
        self.assertEqual(rep["event_gate"]["wait_events"], 2)
        self.assertEqual(rep["event_gate"]["wait_ids"], ["992553"])
        text = mod.render_text(rep, 50)
        self.assertIn("事件等待: 2 轮", text)
        self.assertIn("事件已自行结束（正常）", text)
        self.assertNotIn("manual:event_blocked_without_wait", rep["red"]["subjects"])
        self.assertEqual(rep["categories_total"]["event"], 0,
                         "有 event_wait 无 event_blocked = 事件自行结束，不是问题")

    def test_blocked_without_wait_path_is_red(self):
        """`eventWaitTries=0` 且整本无 `event_wait` ⇒ 没走等待路径 ⇒ 红（手动介入）。"""
        rep = self._report(self._events(wait=0, blocked_kind="zero", event_id_key="null"),
                           "nowait.jsonl")
        self.assertEqual(rep["event_gate"]["no_wait_path_lines"], [2],
                         "event_blocked 在第 2 行（第 1 行是 day_start）")
        self.assertIn("manual:event_blocked_without_wait", subjects(rep["categories"]["event"]))
        self.assertIn("manual:event_blocked_without_wait", rep["red"]["subjects"])
        self.assertTrue(any("没走有界等待" in a["text"] for a in rep["advice"]))
        self.assertTrue(any("task-245" in a["hint"] for a in rep["categories"]["event"]))

    def test_blocked_after_wait_is_not_red(self):
        """等过再收尾 = task-245 的正常形态：只有 info（头部两数），没有红。"""
        rep = self._report(self._events(wait=3, blocked_kind="waited"), "waited.jsonl")
        self.assertEqual(rep["event_gate"]["blocked_tries"], [3])
        self.assertEqual(rep["event_gate"]["blocked_seconds_max"], 45.0)
        self.assertEqual(rep["event_gate"]["no_wait_path_lines"], [])
        self.assertNotIn("manual:event_blocked_without_wait", rep["red"]["subjects"])
        text = mod.render_text(rep, 50)
        self.assertIn("阻断 1 次", text)
        self.assertIn("eventId=992553", text)

    def test_legacy_blocked_without_wait_key_is_undecidable_not_red(self):
        """`eventWaitTries` 整键缺失（task-245 之前的旧 Mod）⇒【无法判定】，不许判红。"""
        rep = self._report(self._events(wait=0, blocked_kind="legacy", event_id_key="absent"),
                           "legacy.jsonl")
        und = " ".join(rep["undecidable"])
        self.assertIn("task-245 之前的旧 Mod", und)
        self.assertTrue(rep["event_gate"]["event_id_undecidable"])
        self.assertNotIn("manual:event_blocked_without_wait", rep["red"]["subjects"])
        self.assertEqual(rep["categories_total"]["event"], 0)

    def test_event_id_null_is_not_guessed(self):
        """`eventId: null`（读不到）⇒ 显示"无法归因"，只进【无法判定】，不许猜 id。"""
        rep = self._report(self._events(wait=1, blocked=False, event_id_key="null"), "eid.jsonl")
        eg = rep["event_gate"]
        self.assertEqual(eg["wait_id_states"]["null"], 1)
        self.assertEqual(eg["id_text"], "无法归因")
        self.assertIn("eventId=无法归因", mod.render_text(rep, 50))
        self.assertNotIn("manual:event_blocked_without_wait", rep["red"]["subjects"])

    def test_ui_event_id_probe(self):
        """`ui.eventId` 探针：有 ui 块 ⇒ 不出【无法判定】；没有 ⇒ 出。"""
        rep_has = self._report(self._events(wait=1, blocked=False, with_ui_id=True), "has.jsonl")
        self.assertFalse(any("本账本没有 ui.eventId" in u for u in rep_has["undecidable"]))
        rep_no = self._report(self._events(wait=1, blocked=False, with_ui_id=False), "no.jsonl")
        self.assertTrue(any("本账本没有 ui.eventId" in u for u in rep_no["undecidable"]))

    def test_old_ledger_without_event_events_is_undecidable(self):
        """没有 event_wait/event_blocked 的旧账本：只出【无法判定】，不判红、不加头部行。"""
        rep = self._report(integrity_ledger(), "old.jsonl")
        self.assertIn("没有任何 event_wait / event_blocked",
                      " ".join(rep["undecidable"]))
        self.assertNotIn("事件等待:", mod.render_text(rep, 50))
        self.assertNotIn("manual:event_blocked_without_wait", rep["red"]["subjects"])


class TestStageChurn(unittest.TestCase):
    """task-3 A（A8 winter 9/14）：同一天同一 stage 反复重分「1 格余量」⇒ `stage_churn` 聚合。

    口径：**纯 info、不进 rc**；判据 = 连续（数组相邻）同 stage + `assigned<=1` +
    `stopped=incomplete` + `leftover` **不降**，且连续轮数 `>= STAGE_CHURN_MIN_RUN`；
    `assigned`/`leftover` 缺失 ⇒【无法判定】（缺失 ≠ 0，绝不猜、绝不当 0）。
    """

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def _churn_stage(self, *, assigned=1, leftover=1, stopped="incomplete",
                     stage="clear_area", tiles=((37, 35),)):
        return {"stage": stage, "tiles": assigned, "ok": 0, "skipped": 0, "failed": 1,
                "proven_inert": 0, "env_block": 0, "inconclusive": 0, "stopped": stopped,
                "leftover": leftover, "assigned": assigned, "assigned_undone": assigned,
                "attempted": assigned, "requested_tiles": assigned, "ok_tiles": 0,
                "failed_tiles": 1, "unexecuted_tiles": 0,
                "reasons": {"blocked_tile": 1},
                "cleared_tiles": [], "unreachable_tiles": [], "already_tiles": [],
                "encircled_tiles": [list(t) for t in tiles]}

    def _ledger(self, stages, *, ended_by="stuck",
                reason="stuck:连续 3 轮世界没有任何变化（最后意图：['clear_area']）"):
        checks = {"slept_by_us": False, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": False}
        return integrity_ledger(day_end_overrides={
            "verified": False, "ended_by": ended_by, "ended_reason": reason,
            "checks": checks, "stages": list(stages),
            "failed_steps": sum(int(st.get("failed") or 0) for st in stages),
            "ok_steps": sum(int(st.get("ok") or 0) for st in stages),
            "skipped_steps": 0,
        })

    def test_churn_run_is_aggregated_with_coords_and_day_count(self):
        """连续 4 轮 assigned=1/incomplete/leftover=1 ⇒ 1 段 4 次，带格坐标与日级计数。"""
        stages = [self._churn_stage() for _ in range(4)]
        rep = self._report(self._ledger(stages), "churn.jsonl")
        sc = rep["stage_churn"]
        self.assertEqual(sc["min_run"], mod.STAGE_CHURN_MIN_RUN)
        self.assertEqual(sc["runs"], 1)
        self.assertEqual(sc["days_with_runs"], 1)
        self.assertEqual(sc["stages_total"], 4)
        self.assertEqual(sc["max_run"], 4)
        self.assertEqual(sc["coords"], [[37, 35]])
        self.assertEqual(sc["undecidable_days"], [])
        day = sc["days"][0]
        self.assertEqual((day["runs"], day["churn_stages"], day["max_run"]), (1, 4, 4))
        text = mod.render_text(rep, 50)
        self.assertIn("阶段 churn: 1 天 / 1 段 / 4 次", text)
        self.assertIn("[[37, 35]]", text)
        self.assertIn("纯 info：这不是失败、不进 rc", text)
        # info：不许新增任何红
        self.assertFalse([s for s in rep["red"]["subjects"] if "stage_churn" in s])
        self.assertTrue(any("A8 新形态（task-3" in a["text"] for a in rep["advice"]),
                        "新形态必须有带证据行的建议")

    def test_churn_requires_continuous_run_length(self):
        """只有 2 轮（< STAGE_CHURN_MIN_RUN）⇒ 不算 churn；单次 incomplete 是正常重试。"""
        rep = self._report(self._ledger([self._churn_stage() for _ in range(2)]), "short.jsonl")
        sc = rep["stage_churn"]
        self.assertEqual((sc["runs"], sc["stages_total"], sc["max_run"]), (0, 0, 0))
        self.assertIn("阶段 churn: 0 次", mod.render_text(rep, 50))

    def test_churn_breaks_when_leftover_decreases(self):
        """leftover 降了 = 有真实进展 ⇒ 不是空转：5→4→3→2 的 4 轮一段 churn 都不算。"""
        stages = [self._churn_stage(leftover=left) for left in (5, 4, 3, 2)]
        rep = self._report(self._ledger(stages), "decreasing.jsonl")
        sc = rep["stage_churn"]
        self.assertEqual(sc["runs"], 0)
        self.assertIn("阶段 churn: 0 次", mod.render_text(rep, 50))

    def test_churn_requires_same_stage_and_incomplete(self):
        """同 stage 才连续；`stopped` 不是 incomplete（例如 unreachable）⇒ 断开、不算空转。"""
        mixed = [self._churn_stage(stage="clear_area"), self._churn_stage(stage="till_area"),
                 self._churn_stage(stage="plant_area")]
        rep = self._report(self._ledger(mixed), "mixed.jsonl")
        self.assertEqual(rep["stage_churn"]["runs"], 0)
        stopped = [self._churn_stage(stopped="unreachable") for _ in range(4)]
        rep2 = self._report(self._ledger(stopped), "stopped.jsonl")
        self.assertEqual(rep2["stage_churn"]["runs"], 0)

    def test_churn_missing_assigned_is_undecidable_not_zero(self):
        """缺 `assigned`（旧账本 run9/run9b 形态）⇒【无法判定】+ 新增探针行；绝不当 0 次。"""
        stages = [{k: v for k, v in self._churn_stage().items() if k != "assigned"} for _ in range(4)]
        rep = self._report(self._ledger(stages), "noassigned.jsonl")
        sc = rep["stage_churn"]
        self.assertFalse(sc["has_assigned"])
        self.assertEqual(sc["runs"], 0)
        self.assertEqual(sc["undecidable_days"], ["1年 spring 12日"])
        text = mod.render_text(rep, 50)
        self.assertIn("【无法判定】", text)
        self.assertIn("assigned", text)
        self.assertIn("判据字段缺失", text)
        self.assertTrue(any("本账本没有 day_end.stages[].assigned" in u
                            for u in rep["undecidable"]),
                        "缺失字段必须走新增探针【无法判定】，缺失 ≠ 0")
        self.assertFalse([s for s in rep["red"]["subjects"] if "stage_churn" in s])

    def test_churn_missing_leftover_is_undecidable_not_zero(self):
        """`assigned` 在、`leftover` 缺 ⇒ 判不了「不降」⇒【无法判定】，不许当作 0 次通过。"""
        stages = [{k: v for k, v in self._churn_stage().items() if k != "leftover"} for _ in range(4)]
        rep = self._report(self._ledger(stages), "noleft.jsonl")
        sc = rep["stage_churn"]
        self.assertEqual(sc["runs"], 0)
        self.assertEqual(sc["undecidable_days"], ["1年 spring 12日"])
        self.assertIn("【无法判定】", mod.render_text(rep, 50))


class TestWorkSpotResumeExhausted(unittest.TestCase):
    """task-3 B（A8 winter 7/12/18）：`work_spot_resume` 连续 5 次拿不出目标而收工。

    口径：**info、不进 rc** —— 这是 task-134 A 的有界诚实收尾，不是失败；证据 = `ended_reason`
    原文 + `no_progress_burst{source=回片区（work_spot_resume）}`。两者都缺且整本没有
    `resume_reevaluate`/`no_progress_burst` ⇒【无法判定】（task-134 之前的老账本，缺失 ≠ 0）。
    """

    REASON = ("stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标"
              "（守卫仍说还有活：今天早些时候还有 11 格没做完（跨片地，最近的是 [60, 32]））")

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def _ledger(self, *, reason, extra_events=(), ended_by="sleep"):
        checks = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": True}
        return integrity_ledger(extra_events=list(extra_events), day_end_overrides={
            "verified": False, "ended_by": ended_by, "ended_reason": reason, "checks": checks,
            "stages": [], "failed_steps": 0, "ok_steps": 0, "skipped_steps": 0,
        })

    def _burst(self):
        return {"event": "no_progress_burst", "t": 5.0, "count": 5,
                "source": "回片区（work_spot_resume）", "tiles": 11,
                "reasons": ["今天早些时候还有 11 格没做完（跨片地，最近的是 [60, 32]）"],
                "note": "回片区/换作业区连续无产出 ⇒ 按既有有界机制诚实收尾，不再空转"}

    def test_exhausted_day_counted_with_raw_reason(self):
        """原文 + 结构化 burst 都在 ⇒ 日级计数 1、连续 5 次、原文逐字保留；纯 info。"""
        rep = self._report(self._ledger(reason=self.REASON, extra_events=[self._burst()]),
                           "wsr.jsonl")
        wr = rep["work_spot_resume_exhausted"]
        self.assertEqual(wr["state"], "found")
        self.assertEqual(wr["days_count"], 1)
        self.assertEqual(wr["max_consecutive"], 5)
        self.assertEqual(wr["days"][0]["ended_reason"], self.REASON, "原文不许改写")
        self.assertEqual(wr["days"][0]["burst_counts"], [5])
        self.assertEqual(wr["burst_mismatch_days"], [])
        text = mod.render_text(rep, 50)
        self.assertIn("回片区死循环（work_spot_resume）: 1 天收工", text)
        self.assertIn(self.REASON, text)
        self.assertIn("有界诚实收尾（task-134 A），不是失败、不进 rc", text)
        self.assertFalse([s for s in rep["red"]["subjects"] if "work_spot_resume" in s])

    def test_reason_only_still_counts(self):
        """只有 `ended_reason` 原文、没有 burst 事件 ⇒ 仍然算命中（原文是一等证据）。"""
        rep = self._report(self._ledger(reason=self.REASON), "reason-only.jsonl")
        wr = rep["work_spot_resume_exhausted"]
        self.assertEqual((wr["days_count"], wr["max_consecutive"]), (1, 5))
        self.assertEqual(wr["burst_mismatch_days"], [], "没有 burst 不算 mismatch")

    def test_zero_is_real_when_mechanism_present(self):
        """机制事件（resume_reevaluate）在场、原文无该形态 ⇒ 0 天是**真实读数**，不是无法判定。"""
        ev = {"event": "resume_reevaluate", "t": 3.0, "where": "guard_leftover",
              "cleared": ["clear_area"], "note": "回到跨片区 leftover 之前清掉任务级 no_target"}
        rep = self._report(self._ledger(reason="night:时间 2200 已经到夜里", extra_events=[ev]),
                           "zero.jsonl")
        wr = rep["work_spot_resume_exhausted"]
        self.assertEqual(wr["state"], "zero")
        self.assertEqual(wr["days_count"], 0)
        self.assertIn("0 天（机制事件在场", mod.render_text(rep, 50))
        self.assertFalse([s for s in rep["red"]["subjects"] if "work_spot_resume" in s])

    def test_missing_mechanism_is_undecidable(self):
        """没有 `resume_reevaluate`/`no_progress_burst`（task-134 之前的旧账本）⇒【无法判定】。"""
        rep = self._report(self._ledger(reason="night:时间 2200 已经到夜里"), "old.jsonl")
        wr = rep["work_spot_resume_exhausted"]
        self.assertEqual(wr["state"], "undecidable")
        self.assertEqual(wr["undecidable_days"], ["1年 spring 12日"])
        text = mod.render_text(rep, 50)
        self.assertIn("回片区死循环（work_spot_resume）: <缺失>", text)
        self.assertIn("缺失 ≠ 0", text)

    def test_burst_without_reason_is_flagged_not_guessed(self):
        """burst 在、原文没命中 ⇒ 不能凭 burst 编收工原文：列为 mismatch（收工结论只能无法判定）。"""
        rep = self._report(self._ledger(reason="night:时间 2200 已经到夜里",
                                        extra_events=[self._burst()]), "mismatch.jsonl")
        wr = rep["work_spot_resume_exhausted"]
        self.assertEqual(wr["days_count"], 1)
        self.assertEqual(wr["burst_mismatch_days"], ["1年 spring 12日"])
        self.assertIn("原文没命中", mod.render_text(rep, 50))


class TestStuckWithoutSleep(unittest.TestCase):
    """task-3 C（A8 winter 9/14）：`ended_by=stuck` 但 `checks.slept_by_us=false`。

    口径：**info /【无法判定】、不进 rc** —— 当天没由我们睡过去，「为什么 stuck / 是否真的收工」
    说不清；`checks.slept_by_us` 缺失同样【无法判定】（缺失 ≠ 0，绝不默认 true/false）。
    """

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def _ledger(self, *, slept, ended_by="stuck", reason="stuck:连续 3 轮世界没有任何变化"):
        checks = {"no_blocking_modal": True, "no_hard_failures": True,
                  "crops_watered": True, "day_justified": False}
        if slept is not _MISSING:
            checks["slept_by_us"] = slept
        return integrity_ledger(day_end_overrides={
            "verified": False, "ended_by": ended_by, "ended_reason": reason, "checks": checks,
            "stages": [], "failed_steps": 0, "ok_steps": 0, "skipped_steps": 0,
        })

    def test_stuck_without_sleep_is_flagged_with_raw_reason(self):
        """ended_by=stuck + slept_by_us=false ⇒ 记 1 天，原文保留；不进 rc。"""
        rep = self._report(self._ledger(slept=False), "nosleep.jsonl")
        sw = rep["stuck_without_sleep"]
        self.assertEqual((sw["stuck_days"], sw["flagged"], sw["undecidable"]), (1, 1, 0))
        self.assertEqual(sw["flagged_days"], ["1年 spring 12日"])
        self.assertEqual(sw["days"][0]["ended_reason"], "stuck:连续 3 轮世界没有任何变化")
        text = mod.render_text(rep, 50)
        self.assertIn("stuck 未睡: 1 天", text)
        self.assertIn("【无法判定】", text)
        self.assertFalse([s for s in rep["red"]["subjects"] if "stuck_without_sleep" in s])

    def test_stuck_with_sleep_is_coherent_not_flagged(self):
        """ended_by=stuck 但 slept_by_us=true ⇒ 不归入本形态（单独计 coherent，供人工核对）。"""
        rep = self._report(self._ledger(slept=True), "slept.jsonl")
        sw = rep["stuck_without_sleep"]
        self.assertEqual((sw["flagged"], sw["coherent"], sw["undecidable"]), (0, 1, 0))
        self.assertIn("stuck 未睡: 0 天", mod.render_text(rep, 50))

    def test_missing_slept_by_us_is_undecidable_not_false(self):
        """缺 `checks.slept_by_us` ⇒【无法判定】（不当 false 判命中、也不当 true 放行）。"""
        rep = self._report(self._ledger(slept=_MISSING), "missing.jsonl")
        sw = rep["stuck_without_sleep"]
        self.assertEqual((sw["flagged"], sw["coherent"], sw["undecidable"]), (0, 0, 1))
        self.assertTrue(any("本账本没有 day_end.checks.slept_by_us" in u
                            for u in rep["undecidable"]),
                        "缺失字段必须走新增探针【无法判定】")
        self.assertIn("stuck 未睡: <缺失>", mod.render_text(rep, 50))
        self.assertFalse([s for s in rep["red"]["subjects"] if "stuck_without_sleep" in s])


class TestRealRunA8Shapes(unittest.TestCase):
    """task-3 真账本读数（`logs/longrun-runA8-0743.jsonl`，0.7.43，冬 7→18）。"""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(RUN_A8):
            raise unittest.SkipTest(f"缺少账本 {RUN_A8}")
        cls.rep = report_for(RUN_A8, days=12)

    def test_stage_churn_readings(self):
        sc = self.rep["stage_churn"]
        self.assertEqual((sc["runs"], sc["days_with_runs"], sc["stages_total"]), (3, 2, 89))
        self.assertEqual((sc["max_run"], sc["coords"]), (62, [[37, 35]]))
        days = {d["label"]: d for d in sc["days"]}
        self.assertEqual(days["1年 winter 9日"]["runs"], 2)
        self.assertEqual(days["1年 winter 9日"]["churn_stages"], 27)
        self.assertEqual(days["1年 winter 14日"]["churn_stages"], 62)
        self.assertEqual(sc["undecidable_days"], [])

    def test_work_spot_resume_readings(self):
        wr = self.rep["work_spot_resume_exhausted"]
        self.assertEqual((wr["state"], wr["days_count"], wr["max_consecutive"]), ("found", 3, 5))
        labels = [d["label"] for d in wr["days"]]
        self.assertEqual(labels, ["1年 winter 7日", "1年 winter 12日", "1年 winter 18日"])
        for day in wr["days"]:
            self.assertIn("work_spot_resume", day["ended_reason"])
            self.assertIn("连续 5 次都拿不出目标", day["ended_reason"])
            self.assertTrue(day["burst_lines"], "结构化 no_progress_burst 必须在场")

    def test_stuck_without_sleep_readings(self):
        sw = self.rep["stuck_without_sleep"]
        self.assertEqual((sw["stuck_days"], sw["flagged"], sw["undecidable"]), (2, 2, 0))
        self.assertEqual(sw["flagged_days"], ["1年 winter 9日", "1年 winter 14日"])
        for day in sw["days"]:
            self.assertIs(day["slept_by_us"], False)

    def test_new_aggregations_add_no_red(self):
        subjects = self.rep["red"]["subjects"]
        for name in ("stage_churn", "work_spot_resume", "stuck_without_sleep"):
            self.assertFalse([s for s in subjects if name in s],
                             f"{name} 只允许 info /【无法判定】，绝不进 rc")
        text = mod.render_text(self.rep, 20)
        self.assertIn("阶段 churn: 2 天 / 3 段 / 89 次", text)
        self.assertIn("回片区死循环（work_spot_resume）: 3 天收工", text)
        self.assertIn("stuck 未睡: 2 天", text)


# ---------------------------------------------------------------- task-13（0.7.44 新字段/形态）
#: 0.7.44 的 `ended_reason` 原文（brain：`resume_exhausted:回片区 N 格都回去看过、换片 M 次，…`）。
T13_REASON = ("resume_exhausted:回片区 7 格都回去看过、换片 2 次，"
              "当前观测里没有可执行目标（守卫仍说：跨片地还有 3 格没做完）")
T13_LEGACY_REASON = ("stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标"
                     "（守卫仍说还有活：跨片地还有 3 格没做完）")


def t13_stage(**kw):
    """task-13：一天的阶段记录（默认：3 格、0 做成、3 余格 —— 与 A8 的「1 格余量」同形）。"""
    st = {"stage": "clear_area", "tiles": 3, "ok": 0, "skipped": 0, "failed": 0,
          "proven_inert": 0, "env_block": 0, "inconclusive": 0, "stopped": "",
          "leftover": 3}
    st.update(kw)
    return st


def t13_burst(*, count=5, exhausted=True, switches=2, stalled=7):
    return {"event": "no_progress_burst", "t": 8.0, "day": MODAL_DAY,
            "source": "回片区（work_spot_resume）", "count": count, "tiles": 3,
            "exhausted": exhausted, "switches": switches, "stalled_tiles": stalled,
            "from_area": "field_ne", "pending": 3}


def t13_ledger(*, stages=(), extra_events=(), day_end_overrides=None, drop=(),
               finish=None, verified=False):
    """task-13：造一天带 0.7.44 字段的账本（默认 ended_reason 用新前缀；`drop` 可删 day_end 键）。"""
    end = {
        "event": "day_end", "t": 9.0, "day": MODAL_DAY, "day_text": "1年 spring 12日",
        "ended_by": "sleep", "ended_reason": T13_REASON, "verified": verified,
        "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                   "crops_watered": True, "day_justified": False},
        "stages": list(stages), "outcomes": [], "ok_steps": 0, "skipped_steps": 0,
        "failed_steps": 0, "notes": [],
        "final": final([MODAL_DAY[0], MODAL_DAY[1], MODAL_DAY[2] + 1]),
    }
    if day_end_overrides:
        end.update(day_end_overrides)
    for key in drop:
        end.pop(key, None)
    events = [day_start(MODAL_DAY)]
    events.extend(extra_events)
    events.append(end)
    if finish is not None:
        events.append(finish)
    return events


class TestResumeExhaustedPrefix(unittest.TestCase):
    """task-13 D（0.7.44）：`ended_reason` 新前缀 `resume_exhausted:`。

    口径：**info /【无法判定】、不进 rc** —— 换片/回看/清障都用尽后的诚实收工，不是 stuck、不是失败；
    与 A8/0.7.43 的 `stuck:回片区（work_spot_resume）` **分开计数**（两代形态绝不混算）。
    """

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def test_new_prefix_found_and_not_red(self):
        rep = self._report(t13_ledger(extra_events=[t13_burst()]), "re.jsonl")
        re_new = rep["resume_exhausted"]
        self.assertEqual((re_new["state"], re_new["days_count"]), ("found", 1))
        self.assertEqual(re_new["labels"], ["1年 spring 12日"])
        self.assertEqual(re_new["days"][0]["switches"], 2, "换片次数从原文解析（缺失才是 None）")
        self.assertEqual((re_new["burst_exhausted_events"],
                          re_new["days"][0]["burst_count"]), (1, 5))
        self.assertEqual(re_new["legacy_count"], 0)
        text = mod.render_text(rep, 50)
        self.assertIn("回片区穷尽（resume_exhausted 前缀，0.7.44）: 1 天", text)
        self.assertIn(T13_REASON, text, "原文必须进报告")
        self.assertFalse([s for s in rep["red"]["subjects"] if "resume_exhausted" in s],
                         "新前缀只允许 info /【无法判定】，绝不进 rc")

    def test_legacy_prefix_counted_separately(self):
        rep = self._report(t13_ledger(day_end_overrides={"ended_reason": T13_LEGACY_REASON}),
                           "legacy.jsonl")
        re_new = rep["resume_exhausted"]
        self.assertEqual((re_new["state"], re_new["days_count"]), ("zero", 0))
        self.assertEqual(re_new["legacy_count"], 1, "A8 的旧前缀由本块单列，不吞进新前缀")
        self.assertEqual(re_new["legacy_labels"], ["1年 spring 12日"])
        self.assertIn("旧 stuck 前缀 1 天", mod.render_text(rep, 50))

    def test_burst_without_new_prefix_is_mismatch(self):
        """穷尽 burst 在场但原文无新前缀 ⇒ 形态对不上，收工结论只能【无法判定】。"""
        rep = self._report(t13_ledger(day_end_overrides={"ended_reason": "night:时间到夜里"},
                                      extra_events=[t13_burst()]), "mismatch.jsonl")
        self.assertEqual(len(rep["resume_exhausted"]["burst_mismatch_days"]), 1)
        self.assertIn("无新前缀", mod.render_text(rep, 50))

    def test_missing_ended_reason_is_undecidable(self):
        rep = self._report(t13_ledger(drop=("ended_reason",)), "missing.jsonl")
        re_new = rep["resume_exhausted"]
        self.assertEqual(re_new["state"], "undecidable")
        self.assertEqual(len(re_new["undecidable_days"]), 1, "缺字段 ⇒ 当天无法判定（缺失 ≠ 0）")
        self.assertIn("回片区穷尽（resume_exhausted 前缀，0.7.44）: <缺失>",
                      mod.render_text(rep, 50))


class TestStageReallocBlocked(unittest.TestCase):
    """task-13 E（0.7.44）：`blocked{action=stage_realloc}` + 阶记录 `alloc_capped_tiles`。

    口径：**info、不进 rc** —— 同格重分配仍无产出达 limit ⇒ 封格，是有界保护不是失败。
    """

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def test_stage_realloc_found(self):
        blocked = {"event": "blocked", "t": 7.0, "day": MODAL_DAY, "tile": [37, 35],
                   "action": "stage_realloc", "no_effect": False, "stage": "clear_area",
                   "zone": "field_ne", "alloc_no_progress": 3, "limit": 3,
                   "reason": "同一格当天第 3 次重分配仍无产出"}
        stage = t13_stage(alloc_capped_tiles=[[37, 35]])
        rep = self._report(t13_ledger(stages=[stage], extra_events=[blocked]), "realloc.jsonl")
        sr = rep["stage_realloc"]
        self.assertEqual((sr["state"], sr["events"], sr["days_count"], sr["stage_capped"]),
                         ("found", 1, 1, 1))
        self.assertEqual(sr["days"][0]["events"][0]["alloc_no_progress"], 3)
        self.assertEqual(sr["days"][0]["events"][0]["limit"], 3)
        self.assertEqual(sr["days"][0]["stage_capped_tiles"], [[37, 35]])
        self.assertIn("阶段重分配封格（stage_realloc，0.7.44）: 1 次 / 1 天",
                      mod.render_text(rep, 50))
        self.assertFalse([s for s in rep["red"]["subjects"] if "stage_realloc" in s])

    def test_mechanism_absent_is_undecidable_not_zero(self):
        rep = self._report(t13_ledger(stages=[t13_stage()]), "none.jsonl")
        self.assertEqual(rep["stage_realloc"]["state"], "undecidable")
        self.assertEqual(rep["stage_realloc"]["events"], 0)
        self.assertIn("阶段重分配封格（stage_realloc，0.7.44）: <缺失>",
                      mod.render_text(rep, 50))


class TestLeftoverSplit(unittest.TestCase):
    """task-13 F（0.7.44）：`leftover_executable` / `leftover_blocked`（leftover 语义不变）。

    硬不变式：`leftover_executable + leftover_blocked == leftover`；日级 `plot_pending_executable +
    plot_pending_blocked == plot_pending`。违背只警告、**不进 rc**；字段缺失 ⇒【无法判定】（缺失 ≠ 0）。
    """

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def test_split_ok(self):
        stage = t13_stage(leftover=3, leftover_executable=1, leftover_blocked=2,
                          leftover_blocked_tiles=[[40, 41], [41, 41]])
        rep = self._report(t13_ledger(stages=[stage], day_end_overrides={
            "plot_pending": 3, "plot_pending_executable": 1, "plot_pending_blocked": 2,
        }), "split_ok.jsonl")
        ls = rep["leftover_split"]
        self.assertEqual(ls["state"], "ok")
        self.assertEqual((ls["totals"]["with_split"], ls["totals"]["exec_sum"],
                          ls["totals"]["blocked_sum"], ls["totals"]["leftover_sum"]),
                         (1, 1, 2, 3))
        self.assertEqual(ls["totals"]["mismatch"], 0)
        self.assertEqual(ls["pending_days"][0]["exec"], 1)
        self.assertIn("余格拆分（leftover_executable/blocked，0.7.44）: 带拆分 1 段",
                      mod.render_text(rep, 50))
        self.assertFalse([s for s in rep["red"]["subjects"] if "leftover" in s])

    def test_split_invariant_violation_is_warning_only(self):
        stage = t13_stage(leftover=3, leftover_executable=1, leftover_blocked=1)
        rep = self._report(t13_ledger(stages=[stage]), "split_bad.jsonl")
        ls = rep["leftover_split"]
        self.assertEqual((ls["state"], ls["totals"]["mismatch"]), ("violated", 1))
        text = mod.render_text(rep, 50)
        self.assertIn("不变式违背 1 段", text)
        self.assertIn("不进 rc", text)
        self.assertFalse([s for s in rep["red"]["subjects"] if "leftover_split" in s])

    def test_day_level_plot_pending_invariant(self):
        stage = t13_stage(leftover=3, leftover_executable=1, leftover_blocked=2)
        rep = self._report(t13_ledger(stages=[stage], day_end_overrides={
            "plot_pending": 3, "plot_pending_executable": 1, "plot_pending_blocked": 1,
        }), "split_day.jsonl")
        self.assertEqual(len(rep["leftover_split"]["day_invariant_days"]), 1)
        self.assertIn("日级 plot_pending_executable+blocked != plot_pending",
                      mod.render_text(rep, 50))

    def test_split_fields_missing_is_undecidable(self):
        rep = self._report(t13_ledger(stages=[t13_stage()]), "split_missing.jsonl")
        ls = rep["leftover_split"]
        self.assertEqual(ls["state"], "undecidable")
        self.assertFalse(ls["has_split_field"])
        self.assertEqual(ls["totals"]["missing_split"], 1)
        self.assertIn("余格拆分（leftover_executable/blocked，0.7.44）: <缺失>",
                      mod.render_text(rep, 50))


class TestSleptOkField(unittest.TestCase):
    """task-13 G（0.7.44）：`day_end.slept_ok` 与 `checks.slept_by_us` 旁证。

    口径：**info、不进 rc**；字段缺失 ⇒【无法判定】（缺失 ≠ 0）；两字段打架 ⇒ ⚠ 人工核对（不进 rc）。
    """

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def test_slept_ok_true_found(self):
        rep = self._report(t13_ledger(day_end_overrides={"slept_ok": True}), "slept.jsonl")
        so = rep["slept_ok"]
        self.assertEqual((so["state"], so["true_count"], so["false_count"]), ("found", 1, 0))
        self.assertEqual(so["inconsistent_days"], [])
        self.assertIn("睡成功标志（slept_ok，0.7.44）: true 1 天", mod.render_text(rep, 50))

    def test_slept_ok_conflict_is_warning_only(self):
        rep = self._report(t13_ledger(day_end_overrides={"slept_ok": False}), "conflict.jsonl")
        so = rep["slept_ok"]
        self.assertEqual(so["false_count"], 1)
        self.assertEqual(len(so["inconsistent_days"]), 1,
                         "slept_ok=false 而 checks.slept_by_us=true ⇒ 互斥字段打架")
        self.assertIn("不一致", mod.render_text(rep, 50))
        self.assertFalse([s for s in rep["red"]["subjects"] if "slept_ok" in s])

    def test_missing_slept_ok_is_undecidable(self):
        rep = self._report(t13_ledger(), "missing.jsonl")
        so = rep["slept_ok"]
        self.assertEqual((so["state"], so["undecidable_count"], so["has_field"]),
                         ("undecidable", 1, False))
        self.assertIn("睡成功标志（slept_ok，0.7.44）: <缺失>", mod.render_text(rep, 50))
        self.assertTrue(any("本账本没有 day_end.slept_ok" in u for u in rep["undecidable"]))


class TestBudgetSuppressed(unittest.TestCase):
    """task-13 H（0.7.44）：`stamina_budget.deferred_by_budget_suppressed`。

    口径：**info、不进 rc** —— 当天已浇完户外水时「只因预算延后」事件一条不发、只留日级计数；
    所以「日级>0 且无事件」是设计、不是矛盾。与 `deferred_by_budget` 同真 ⇒ ⚠ 人工核对（不进 rc）。
    """

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def test_suppressed_found(self):
        rep = self._report(t13_ledger(day_end_overrides={"stamina_budget": {
            "deferred_by_budget": False, "deferred_by_budget_suppressed": 3,
        }}), "budget.jsonl")
        bs = rep["budget_suppressed"]
        self.assertEqual((bs["state"], bs["total"], bs["days_count"]), ("found", 3, 1))
        self.assertEqual(bs["conflict_days"], [], "浇完户外 ⇒ 不发事件是设计，不算矛盾")
        self.assertIn("预算抑制（deferred_by_budget_suppressed，0.7.44）: 3 条 / 1 天",
                      mod.render_text(rep, 50))

    def test_suppressed_and_deferred_conflict(self):
        rep = self._report(t13_ledger(day_end_overrides={"stamina_budget": {
            "deferred_by_budget": True, "deferred_by_budget_suppressed": 2,
        }}), "budget_conflict.jsonl")
        self.assertEqual(len(rep["budget_suppressed"]["conflict_days"]), 1)
        self.assertIn("本该互斥", mod.render_text(rep, 50))
        self.assertFalse([s for s in rep["red"]["subjects"] if "budget_suppressed" in s])

    def test_missing_suppressed_field_is_undecidable(self):
        rep = self._report(t13_ledger(), "budget_missing.jsonl")
        bs = rep["budget_suppressed"]
        self.assertEqual((bs["state"], bs["has_field"]), ("undecidable", False))
        self.assertIn("预算抑制（deferred_by_budget_suppressed，0.7.44）: <缺失>",
                      mod.render_text(rep, 50))
        self.assertTrue(any("deferred_by_budget_suppressed" in u for u in rep["undecidable"]))


class TestAlreadyAwareDualColumn(unittest.TestCase):
    """task-13 I / task-10 #1：`stage.ok==0 && stage.already>0` 的**并列读数**。

    口径：0.7.44 起 `ok` = 真世界变化数 ⇒ **ok=0 不代表白干**；already>0 = 那些格本来就不用做。
    判决必须 ok / already 两列并读（窗口内同时给两列）；字段缺失 ⇒【无法判定】（缺失 ≠ 0）。
    """

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def test_dual_column_counts_and_coords(self):
        stage = t13_stage(already=3, already_tiles=[[40, 40], [41, 40]],
                          already_cause={"cleared_by_neighbor": 3})
        rep = self._report(t13_ledger(stages=[stage]), "already.jsonl")
        aa = rep["already_aware"]
        self.assertEqual(aa["state"], "ok")
        self.assertEqual((aa["totals"]["ok0"], aa["totals"]["ok0_already"]), (1, 1))
        self.assertEqual(aa["days_with_ok0_already"], ["1年 spring 12日"])
        self.assertEqual(aa["days"][0]["names"], ["clear_area"])
        self.assertEqual(aa["days"][0]["coords"], [[40, 40], [41, 40]])
        self.assertEqual(aa["days"][0]["causes"], {"cleared_by_neighbor": 3})
        self.assertEqual((aa["totals"]["ok_sum"], aa["totals"]["already_sum"]), (0, 3))
        self.assertEqual(aa["window"]["ok0_already"], 1, "窗口统计必须同时给 ok 与 already 两列")
        text = mod.render_text(rep, 50)
        self.assertIn("already-aware 双列（ok=0 且 already>0，0.7.44 口径）: 1 段 / 1 天", text)
        self.assertIn("**ok=0 不代表白干**", text)
        self.assertFalse([s for s in rep["red"]["subjects"] if "already" in s])

    def test_ok0_without_already_is_not_flagged(self):
        """ok=0 但 already 也 0 ⇒ 不是「本来就不用做」，不归入本形态（不做 ok=0 就白干的推断）。"""
        rep = self._report(t13_ledger(stages=[t13_stage(already=0)]), "ok0.jsonl")
        aa = rep["already_aware"]
        self.assertEqual((aa["totals"]["ok0"], aa["totals"]["ok0_already"]), (1, 0))
        self.assertEqual(aa["days_with_ok0_already"], [])
        self.assertIn("already-aware 双列（ok=0 且 already>0，0.7.44 口径）: 0 段 / 0 天",
                      mod.render_text(rep, 50))

    def test_missing_already_is_undecidable(self):
        rep = self._report(t13_ledger(stages=[t13_stage()]), "no_already.jsonl")
        aa = rep["already_aware"]
        self.assertFalse(aa["has_already_field"])
        self.assertEqual(aa["state"], "undecidable")
        self.assertIn("already-aware 双列（ok=0 且 already>0，0.7.44 口径）: <缺失>",
                      mod.render_text(rep, 50))
        self.assertTrue(any("day_end.stages[].already" in u for u in rep["undecidable"]))


class TestTask13ProbesFailClosed(unittest.TestCase):
    """task-13 探针：0.7.44 字段缺失一律【无法判定】（缺失 ≠ 0），且新聚合绝不进 rc。"""

    def _report(self, events, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return report_for(write_ledger(tmp.name, name, events), days=1)

    def test_old_ledger_probes_are_undecidable(self):
        rep = self._report(integrity_ledger(), "old.jsonl")
        und = " ".join(rep["undecidable"])
        for label in ("event:resume_walk.switched", "day_end.slept_ok",
                      "day_end.stamina_budget.deferred_by_budget_suppressed",
                      "day_end.stages[].leftover_executable",
                      "day_end.stages[].alloc_capped_tiles",
                      "event:blocked.alloc_no_progress", "event:plot_exhausted.source",
                      "event:no_progress_burst.exhausted"):
            self.assertIn(f"本账本没有 {label}", und, f"{label} 缺失必须【无法判定】")

    def test_present_074_fields_do_not_emit_probes(self):
        rep = self._report(t13_ledger(stages=[t13_stage(
            leftover=3, leftover_executable=1, leftover_blocked=2, already=3,
            already_tiles=[[40, 40]], alloc_capped_tiles=[],
        )], extra_events=[t13_burst()], day_end_overrides={
            "slept_ok": True,
            "stamina_budget": {"deferred_by_budget": False,
                               "deferred_by_budget_suppressed": 0},
            "plot_pending": 3, "plot_pending_executable": 1, "plot_pending_blocked": 2,
        }), "full.jsonl")
        und = " ".join(rep["undecidable"])
        for label in ("day_end.slept_ok",
                      "day_end.stamina_budget.deferred_by_budget_suppressed",
                      "day_end.stages[].leftover_executable",
                      "day_end.stages[].already："):
            # 注意 `already` 是 `already_cause` 的前缀 ⇒ 必须带冒号/整行判，否则假失败。
            self.assertNotIn(f"本账本没有 {label}", und)
        self.assertNotIn("event:no_progress_burst.exhausted",
                         und, "burst 带 exhausted 字段 ⇒ 该探针不应报缺")

    def test_task13_aggregations_never_enter_red(self):
        rep = self._report(t13_ledger(stages=[t13_stage(
            leftover=3, leftover_executable=1, leftover_blocked=1, already=3,
            already_tiles=[[40, 40]],
        )], extra_events=[t13_burst(), {
            "event": "blocked", "t": 7.0, "day": MODAL_DAY, "tile": [37, 35],
            "action": "stage_realloc", "alloc_no_progress": 3, "limit": 3,
            "stage": "clear_area",
        }], day_end_overrides={
            "slept_ok": False,
            "stamina_budget": {"deferred_by_budget": False,
                               "deferred_by_budget_suppressed": 1},
        }, drop=("ended_reason",)), "allbad.jsonl")
        # 这里每一条新形态都处于自身「异常/不完整」态：但口径仍是 info/【无法判定】，绝不进 rc。
        for name in ("resume_exhausted", "stage_realloc", "leftover", "slept_ok",
                     "budget", "already"):
            self.assertFalse([s for s in rep["red"]["subjects"] if name in s],
                             f"{name} 只允许 info /【无法判定】，绝不进 rc")
        advice = " ".join(a["text"] for a in rep["advice"])
        self.assertIn("0.7.44 新字段/形态（task-13", advice)
        self.assertIn("不进 rc", advice)


class TestRealRunA8Task13(unittest.TestCase):
    """task-13：A8 真账本（0.7.43，无 0.7.44 字段）的读数必须如实写成【无法判定】。"""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(RUN_A8):
            raise unittest.SkipTest(f"缺少账本 {RUN_A8}")
        cls.rep = report_for(RUN_A8, days=12)

    def test_resume_exhausted_legacy_form_on_a8(self):
        re_new = self.rep["resume_exhausted"]
        self.assertEqual((re_new["state"], re_new["days_count"], re_new["legacy_count"]),
                         ("zero", 0, 3), "A8 是旧 `stuck:` 前缀 ⇒ 新前缀 0 天、旧前缀 3 天，分开计数")
        self.assertEqual(re_new["legacy_labels"],
                         ["1年 winter 7日", "1年 winter 12日", "1年 winter 18日"])
        self.assertIn("旧 stuck 前缀 3 天", mod.render_text(self.rep, 20))

    def test_074_fields_are_undecidable_on_a8(self):
        self.assertEqual(self.rep["stage_realloc"]["state"], "undecidable")
        self.assertEqual(self.rep["stage_realloc"]["events"], 0)
        self.assertEqual(self.rep["leftover_split"]["state"], "undecidable")
        self.assertFalse(self.rep["leftover_split"]["has_split_field"])
        self.assertEqual(self.rep["slept_ok"]["state"], "undecidable")
        self.assertEqual(self.rep["slept_ok"]["undecidable_count"], 12)
        self.assertEqual(self.rep["budget_suppressed"]["state"], "undecidable")

    def test_already_aware_dual_column_on_a8(self):
        aa = self.rep["already_aware"]
        self.assertEqual(aa["state"], "ok")
        self.assertEqual(aa["totals"]["ok0_already"], 0,
                         "A8 预期 0 个 ok=0&already>0（非 0 必须如实报，不许压成 0）")
        self.assertEqual((aa["totals"]["ok_sum"], aa["totals"]["already_sum"]), (289, 50))
        self.assertEqual(aa["window"]["ok_sum"], 47, "窗口内必须同时给 ok 与 already 两列")
        self.assertEqual(aa["window"]["already_sum"], 3)
        self.assertIn("already-aware 双列（ok=0 且 already>0，0.7.44 口径）: 0 段 / 0 天",
                      mod.render_text(self.rep, 20))

    def test_new_aggregations_add_no_red_to_a8(self):
        for name in ("resume_exhausted", "stage_realloc", "leftover", "slept_ok",
                     "budget", "already"):
            self.assertFalse([s for s in self.rep["red"]["subjects"] if name in s])


if __name__ == "__main__":
    unittest.main()
