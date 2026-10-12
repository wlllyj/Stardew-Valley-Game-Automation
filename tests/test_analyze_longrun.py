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
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "analyze-longrun.py")

_spec = importlib.util.spec_from_file_location("analyze_longrun", TOOL)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

RUN1 = os.path.join(ROOT, "logs", "longrun-3day-llm-run1.jsonl")
RUN2 = os.path.join(ROOT, "logs", "longrun-3day-llm-run2.jsonl")
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
        self.assertEqual(rep["categories_total"], {"missed": 0, "wasted": 0, "ineffective": 0, "sleep": 0})
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


if __name__ == "__main__":
    unittest.main()
