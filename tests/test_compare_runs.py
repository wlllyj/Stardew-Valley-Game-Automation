"""`tools/compare-runs.py` 的回归测试（Lead 2026-10-16 补）。

为什么值得单独有：run9/run10 的「决策演进」验收（task-113）与 task-112 的独立复核
都要靠这个工具把两本账本 + 两份留痕并排取证。它自己如果悄悄数错（事件名/阶段口径/
教训命中），验收结论就会跟着错 —— 而且错的方向是"看起来证明了演进"。

跑法：`python -m unittest tests.test_compare_runs`
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("compare_runs", _ROOT / "tools" / "compare-runs.py")
assert _spec is not None and _spec.loader is not None
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)


def write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                    encoding="utf-8")


def decision(*tasks, llm=False, boundary="task_kind_change"):
    return {"event": "decision", "day": [1, "summer", 3], "boundary": boundary,
            "source": "llm" if llm else "deterministic", "llm": llm,
            "intents": [{"task": t, "area_hint": "field_ne", "reason": "r",
                         "expected_evidence": "e"} for t in tasks]}


def day_end(day, *, verified, stages, ended_by="sleep", ok_steps=5):
    return {"event": "day_end", "t": 9.0, "day_key": list(day), "ended_by": ended_by,
            "verified": verified, "ok_steps": ok_steps, "failed_steps": 0,
            "stages": stages}


class HarvestTests(unittest.TestCase):
    def test_counts_decisions_shapes_and_stage_tiles(self):
        rows = [
            {"event": "day_start", "day": [1, "summer", 3], "t": 0.1},
            decision("clear_area", "water_area"),
            decision("water_area", llm=True, boundary="new_day"),
            {"event": "intent_verdict", "zone": "field_ne",
             "verdicts": [{"task": "clear_area", "verdict": "cancel", "reason": "没目标"},
                          {"task": "water_area", "verdict": "keep", "reason": "ok"}]},
            day_end([1, "summer", 3], verified=False, stages=[
                {"stage": "clear_area", "ok": 12, "failed": 0, "stopped": ""},
                {"stage": "water_area", "ok": 3, "failed": 0, "stopped": "need_refill"},
            ]),
            {"event": "finish", "code": 1, "verified_streak": 0, "actions": 20, "minutes": 3.0,
             "stuck_flushes": 1, "no_unmet_stages": False},
        ]
        info = cr.harvest(rows)
        self.assertEqual(info["day_start"], 1)
        self.assertEqual(info["day_end"], 1)
        self.assertEqual(info["decisions"], 2)
        self.assertEqual(info["decisions_llm"], 1)
        self.assertEqual(info["shapes"]["clear_area+water_area"], 1)
        self.assertEqual(info["shapes"]["water_area"], 1)
        self.assertEqual(info["cancel_by_task"], {"clear_area": 1})
        self.assertEqual(info["stage_ok_by_task"], {"clear_area": 12, "water_area": 3})
        # need_refill 只影响该阶段的"异常收尾"计数，格数照算
        self.assertEqual(info["stage_fail_by_task"], {"water_area": 1})
        self.assertEqual(info["finish"]["verified_streak"], 0)
        self.assertFalse(info["finish"]["no_unmet_stages"])

    def test_stages_are_read_from_day_end_not_stage_events(self):
        """阶段结果在 day_end.stages[]；账本里没有独立的 stage 事件。"""
        rows = [day_end([1, "summer", 4], verified=True,
                        stages=[{"stage": "till_area", "ok": 7, "failed": 1, "stopped": ""}])]
        info = cr.harvest(rows)
        self.assertEqual(info["stage_ok_by_task"], {"till_area": 7})
        self.assertEqual(info["stage_fail_by_task"], {"till_area": 1})


class LessonInjectionTests(unittest.TestCase):
    def _run(self, tmp: pathlib.Path, lessons: list[dict] | None, prompts: list[str]):
        ja = tmp / "runA.jsonl"
        jb = tmp / "runB.jsonl"
        write_jsonl(ja, [day_end([1, "summer", 3], verified=False,
                                 stages=[{"stage": "clear_area", "ok": 1, "failed": 0}])])
        write_jsonl(jb, [day_end([1, "summer", 4], verified=True,
                                 stages=[{"stage": "clear_area", "ok": 2, "failed": 0}])])
        if lessons is not None:
            (tmp / "runA-lessons.json").write_text(
                json.dumps({"lessons": lessons}, ensure_ascii=False), encoding="utf-8")
        if prompts:
            write_jsonl(tmp / "runB-llm.jsonl",
                        [{"prompt": p, "boundary": "new_day"} for p in prompts])
        out = tmp / "report.json"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cr.main(["--run-a", str(ja), "--run-b", str(jb), "--json", str(out)])
        return code, buf.getvalue(), json.loads(out.read_text(encoding="utf-8"))

    def test_lesson_present_in_b_prompt_is_marked_hit(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = pathlib.Path(raw)
            lessons = [{"lesson": "不要给够不着的格子反复派活"},
                       {"lesson": "先浇水再开新地"}]
            code, text, report = self._run(
                tmp, lessons,
                prompts=["当前简报：\n教训：不要给够不着的格子反复派活\n请决定。"])
            self.assertEqual(code, 0)
            self.assertIn("1/2 条教训文本出现在", text)
            self.assertTrue(report["lessons"][0]["in_b_prompt"])
            self.assertFalse(report["lessons"][1]["in_b_prompt"])

    def test_prompt_carriage_is_not_required_for_exit_zero(self):
        """run B 没开 --boundary-llm（无留痕）不算工具失败，只如实报"无法核对"。"""
        with tempfile.TemporaryDirectory() as raw:
            tmp = pathlib.Path(raw)
            code, text, report = self._run(tmp, [{"lesson": "x"}], prompts=[])
            self.assertEqual(code, 0)
            self.assertIn("读不到 run B 的 LLM 留痕", text)
            self.assertEqual(report["b_prompt_calls"], 0)

    def test_missing_lessons_file_is_reported_as_unproven(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = pathlib.Path(raw)
            code, text, report = self._run(tmp, None, prompts=["随便什么提示词"])
            self.assertEqual(code, 0)
            self.assertIn("读不到 run A 的教训库", text)
            self.assertEqual(report["lessons"], [])

    def test_lessons_jsonl_variant_is_accepted(self):
        """卡面允许 `<journal>-lessons.jsonl`；两种形态都必须读得出来。"""
        with tempfile.TemporaryDirectory() as raw:
            tmp = pathlib.Path(raw)
            ja = tmp / "runA.jsonl"
            write_jsonl(ja, [day_end([1, "summer", 3], verified=False,
                                     stages=[{"stage": "clear_area", "ok": 1, "failed": 0}])])
            write_jsonl(tmp / "runA-lessons.jsonl",
                        [{"day_key": [1, "summer", 3], "kind": "cancel",
                          "lesson": "别给够不着的格子派活"}])
            entries, path = cr.lessons_of(ja)
            self.assertEqual(len(entries), 1)
            self.assertTrue(path.endswith("-lessons.jsonl"))
            self.assertEqual(cr.lesson_text(entries[0]), "别给够不着的格子派活")

    def test_lessons_written_but_never_injected_is_flagged(self):
        """有教训、有 LLM 调用、却一条都没进提示词 ⇒ 必须报「根本没送到」，不是「未观察到演进」。"""
        with tempfile.TemporaryDirectory() as raw:
            tmp = pathlib.Path(raw)
            code, text, report = self._run(
                tmp, [{"lesson": "不要给够不着的格子反复派活"}],
                prompts=["当前简报：\n请决定。"])
            self.assertEqual(code, 0)
            self.assertIn("注入口径警告", text)
            self.assertFalse(report["injection_effective"])
            self.assertEqual(report["lessons_hits"], 0)

    def test_injection_effective_flag_when_lesson_is_present(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = pathlib.Path(raw)
            code, _text, report = self._run(
                tmp, [{"lesson": "先浇水再开新地"}],
                prompts=["简报：教训=先浇水再开新地"])
            self.assertEqual(code, 0)
            self.assertTrue(report["injection_effective"])
            self.assertEqual(report["lessons_hits"], 1)


class CriteriaTests(unittest.TestCase):
    """L0–L5（`docs/_run10-criteria.md`）：机械可算的部分不许漏、不许自证演进。"""

    def _info(self, days, ended_by, checks_false=(), decision_texts=()):
        return {"days": list(days), "ended_by": dict(ended_by),
                "checks_false": list(checks_false), "decision_texts": list(decision_texts),
                "event_counts": {}}

    def _lesson(self, kind="stuck_with_leftover", scope="till_area"):
        return {"id": f"{kind}|{scope}", "symptom": "有格没做完", "evidence": "leftover=12",
                "hint": "换片地再试"}

    def test_tail_verified_counts_only_trailing_true(self):
        days = [{"verified": True}, {"verified": False}, {"verified": True}, {"verified": True}]
        self.assertEqual(cr.tail_verified(days), 2)
        self.assertEqual(cr.tail_verified([{"verified": True}, {"verified": None}]), 0)
        self.assertEqual(cr.tail_verified([]), 0)

    def test_l5_reports_evolution_evidence_when_lesson_shape_drops(self):
        info_a = self._info([{"verified": False}], {"stuck": 3}, ["no_unmet_stages"])
        info_b = self._info([{"verified": True}] * 3, {"stuck": 0})
        crit = cr.criteria(info_a, info_b, [self._lesson()], 1, ["提示词里有教训"],
                           "run9c", "run10")
        self.assertTrue(crit["l0_lessons_exist"])
        self.assertTrue(crit["l1_injection_effective"])
        self.assertTrue(crit["l2_same_shape_decreased"])
        self.assertTrue(crit["l4_no_regression"])
        self.assertIn("有演进证据", crit["l5_verdict"])
        self.assertEqual(crit["signals"][0]["a"], 3)
        self.assertEqual(crit["signals"][0]["b"], 0)

    def test_l5_says_insufficient_when_injection_failed(self):
        info_a = self._info([{"verified": True}] * 3, {"stuck": 3})
        info_b = self._info([{"verified": True}] * 3, {"stuck": 0})
        crit = cr.criteria(info_a, info_b, [self._lesson()], 0, [], "run9c", "run10")
        self.assertFalse(crit["l1_injection_effective"])
        self.assertIn("教训没有进", crit["l5_verdict"])

    def test_l5_says_insufficient_when_run_a_has_no_lessons(self):
        info_a = self._info([{"verified": False}], {"stuck": 2})
        info_b = self._info([{"verified": True}] * 3, {"stuck": 0})
        crit = cr.criteria(info_a, info_b, [], 0, ["x"], "run9c", "run10")
        self.assertFalse(crit["l0_lessons_exist"])
        self.assertIn("没产出教训", crit["l5_verdict"])

    def test_l2_false_when_same_shape_does_not_drop(self):
        info_a = self._info([{"verified": False}], {"stuck": 3})
        info_b = self._info([{"verified": True}] * 3, {"stuck": 4})
        crit = cr.criteria(info_a, info_b, [self._lesson()], 1, ["x"], "run9c", "run10")
        self.assertFalse(crit["l2_same_shape_decreased"])
        self.assertIn("同形态", crit["l5_verdict"])

    def test_l4_flags_new_false_check_in_b(self):
        info_a = self._info([{"verified": True}] * 3, {"sleep": 3})
        info_b = self._info([{"verified": True}] * 3, {"sleep": 3}, ["day_justified"])
        crit = cr.criteria(info_a, info_b, [self._lesson()], 1, ["x"], "run9c", "run10")
        self.assertFalse(crit["l4_no_regression"])
        self.assertEqual(crit["new_false_checks_in_b"], ["day_justified"])

    def test_l3_evidence_counts_decision_mentions(self):
        info_a = self._info([{"verified": False}], {"stuck": 3})
        info_b = self._info([{"verified": True}] * 3, {"stuck": 0},
                            decision_texts=["先去 field_ne 把 leftover 12 格做完"])
        crit = cr.criteria(info_a, info_b, [self._lesson()], 1, ["x"], "run9c", "run10")
        self.assertEqual(crit["l3_influence_evidence"][0]["decision_mentions"], 1)

    def test_harvest_collects_ended_by_and_false_checks(self):
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "run.jsonl"
            write_jsonl(path, [
                {"event": "day_end", "day_key": [1, "summer", 3], "ended_by": "stuck",
                 "verified": False, "ok_steps": 5, "failed_steps": 0,
                 "checks": {"no_unmet_stages": False, "day_justified": True},
                 "stages": []},
                {"event": "buy_no_space", "t": 2.0},
            ])
            rows = cr.load_rows(path)
            info = cr.harvest(rows)
            self.assertEqual(info["ended_by"], {"stuck": 1})
            self.assertEqual(info["event_counts"]["buy_no_space"], 1)
            self.assertEqual(info["checks_false"], ["no_unmet_stages"])
            self.assertEqual(info["days"][0]["checks_false"], ["no_unmet_stages"])


class CliTests(unittest.TestCase):
    def test_missing_journal_exits_two(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = pathlib.Path(raw)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cr.main(["--run-a", str(tmp / "nope.jsonl"),
                                "--run-b", str(tmp / "nope2.jsonl")])
            self.assertEqual(code, 2)
            self.assertIn("[exit 2]", buf.getvalue())

    def test_norm_strips_whitespace_and_punctuation(self):
        self.assertEqual(cr.norm("不要 反复\n派活，。"), "不要反复派活")


class BrainLessonFieldTests(unittest.TestCase):
    """2026-10-17 事故回归：brain 的教训条目用 `symptom/evidence/hint`，不是 `lesson/text`。

    事故经过：run A/B 对照里工具报 `injection_effective=false`（"教训根本没送到"），
    而 machine-runner 直查同一份 `-llm.jsonl` 得到 47/47 决策提示词都含教训节 ——
    两把尺子量的不是同一个东西：`lesson_text()` 只认 `lesson/text/summary/...`，
    对 brain 的字段取不到值，退化成"把所有字段拼成长串"，那当然不是提示词的子串。
    """

    _ENTRY = {
        "id": "stuck_with_leftover|harvest",
        "symptom": "harvest 收尾时还剩 1 格没做成、当天以 stuck 结束",
        "evidence": "leftover=1 failed=1 stopped=incomplete",
        "hint": "体力已归零，明天别一早就硬撑，留出回程和补给的余量。",
        "count": 3,
    }
    _PROMPT = ("简报…\nlessons（从过去几天的账本里总结的教训，只作参考）:\n"
               "- harvest 收尾时还剩 1 格没做成、当天以 stuck 结束"
               "〈leftover=1 failed=1 stopped=incomplete〉[模型自述·未验证] "
               "体力已归零，明天别一早就硬撑，留出回程和补给的余量。\n请给意图。")

    def test_lesson_text_prefers_hint_for_brain_entries(self):
        self.assertEqual(cr.lesson_text(self._ENTRY), self._ENTRY["hint"])

    def test_lesson_text_still_accepts_legacy_keys(self):
        self.assertEqual(cr.lesson_text({"lesson": "旧格式"}), "旧格式")
        self.assertEqual(cr.lesson_text({"symptom": "只有症状"}), "只有症状")

    def test_lesson_section_present_detects_header(self):
        self.assertTrue(cr.lesson_section_present([self._PROMPT]))
        self.assertFalse(cr.lesson_section_present(["没有教训节"]))
        self.assertFalse(cr.lesson_section_present([]))

    def _run(self, tmp: pathlib.Path, prompt: str) -> tuple[int, str, dict]:
        write_jsonl(tmp / "a.jsonl", [day_end([1, "summer", 3], verified=False, stages=[])])
        write_jsonl(tmp / "b.jsonl", [day_end([1, "summer", 4], verified=False, stages=[])])
        (tmp / "a-lessons.json").write_text(
            json.dumps({"lessons": [self._ENTRY]}, ensure_ascii=False), encoding="utf-8")
        write_jsonl(tmp / "b-llm.jsonl", [{"kind": "decision", "prompt": prompt}])
        out_json = tmp / "verdict.json"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cr.main(["--run-a", str(tmp / "a.jsonl"), "--run-b", str(tmp / "b.jsonl"),
                            "--json", str(out_json)])
        return code, buf.getvalue(), json.loads(out_json.read_text(encoding="utf-8"))

    def test_brain_style_lessons_count_as_injected(self):
        with tempfile.TemporaryDirectory() as raw:
            code, out, verdict = self._run(pathlib.Path(raw), self._PROMPT)
        self.assertEqual(code, 0)
        self.assertIn("✅ 进提示词", out)
        self.assertIn("1/1 条教训文本", out)
        self.assertTrue(verdict["injection_effective"])
        self.assertTrue(verdict["lesson_section_present"])
        self.assertEqual(verdict["lessons_hits"], 1)

    def test_section_present_without_text_hit_warns_about_caliber_not_missing_injection(self):
        """节在、逐条文本没命中 ⇒ 必须报「比对口径」，不许断言「教训根本没送到」。"""
        with tempfile.TemporaryDirectory() as raw:
            code, out, verdict = self._run(
                pathlib.Path(raw),
                "简报…\nlessons（从过去几天的账本里总结的教训，只作参考）:\n- 被改写过的另一段文本\n")
        self.assertEqual(code, 0)
        self.assertIn("比对口径警告", out)
        self.assertNotIn("教训根本没送到", out)
        self.assertFalse(verdict["injection_effective"])
        self.assertTrue(verdict["lesson_section_present"])
        self.assertEqual(verdict["lessons_hits"], 0)


if __name__ == "__main__":
    unittest.main()
