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
        same = self._report(integrity_ledger(day_end_overrides={"final": final(MODAL_DAY)}),
                            "cross_same.jsonl")
        self.assertIn("missed:cross_day", subjects(same["categories"]["missed"]))
        twice = self._report(integrity_ledger(
            day_end_overrides={"final": final([MODAL_DAY[0], MODAL_DAY[1], MODAL_DAY[2] + 2])}),
            "cross_twice.jsonl")
        self.assertIn("missed:cross_day", subjects(twice["categories"]["missed"]))
        good = self._report(integrity_ledger(), "cross_ok.jsonl")
        self.assertNotIn("missed:cross_day", subjects(good["categories"]["missed"]))

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


if __name__ == "__main__":
    unittest.main()
