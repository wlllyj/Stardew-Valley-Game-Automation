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


if __name__ == "__main__":
    unittest.main()
