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
GREEN = os.path.join(ROOT, "scratch", "_ledger_green.jsonl")
FALLBACK = os.path.join(ROOT, "scratch", "_ledger_fallback.jsonl")
WASH = os.path.join(ROOT, "scratch", "_ledger_leftover_verified.jsonl")


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


if __name__ == "__main__":
    unittest.main()
