"""`tools/verify-run3.py` 的回归测试（Lead 2026-10-14 补）。

为什么值得单独有：这个工具是 P3 ⑥ 真机验收的**唯一判据入口**（run5/run6 都靠它出结论），
而它自己一直没有单测 —— `docs/_verify-run3-limits.md` 只能证明"历史上挡住过某些假账本"。
本文件把那条负例矩阵固化成用例：**绿账本必须过，六类伪造/走火/缺失账本必须红**，
这样以后（Lead 或队友）改这个工具时，把闸门改松会当场被测出来。

跑法：`python -m unittest tests.test_verify_run3`
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verify_run3", _ROOT / "tools" / "verify-run3.py")
assert _spec is not None and _spec.loader is not None
vr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vr)


# ------------------------------------------------------------------ 造账本
def day_start(day, *, t=0.0, lineno=1):
    return {"event": "day_start", "day": list(day), "t": t, "_lineno": lineno, "final": {"day": list(day)}}


def sleep_ok(*, t=100.0, reason="night:到点了", lineno=2):
    return {"event": "sleep", "ok": True, "reason": reason, "t": t, "_lineno": lineno}


def stage(name="water_area", *, tiles=5, ok=5, failed=0, skipped=0, leftover=0, **extra):
    row = {"stage": name, "tiles": tiles, "ok": ok, "failed": failed, "skipped": skipped,
           "leftover": leftover, "env_block_count": 0, "inconclusive_count": 0, "failed_any": failed}
    row.update(extra)
    return row


def day_end(day, next_day, *, t=200.0, ok_steps=10, failed_steps=0, stages=None, dry=0,
            checks=None, verified=True, ended_by="sleep", ended_reason="night:到点了",
            unreachable=None, **extra):
    checks_all = {
        "slept_by_us": True,
        "no_blocking_modal": True,
        "no_hard_failures": failed_steps == 0,
        "no_unmet_stages": True,
        "crops_watered": True,
        "watered_outdoor": dry == 0,
        "day_justified": True,
    }
    if checks:
        checks_all.update(checks)
    row = {
        "event": "day_end",
        "t": t,
        "ended_by": ended_by,
        "ended_reason": ended_reason,
        "verified": verified,
        "checks": checks_all,
        "final": {"day": list(day), "unwatered_crops": dry, "crops": 5, "money": 100},
        "final_water": {"t": t - 1, "location": "Farm", "tiles": 30, "crops": 5, "dry": dry,
                        "scope": "farm"},
        "day_after": list(next_day) if next_day else None,
        "ok_steps": ok_steps,
        "skipped_steps": 0,
        "failed_steps": failed_steps,
        "stages": stages if stages is not None else [stage(ok=ok_steps, failed=failed_steps)],
        "notes": [],
        "outcomes": [],
    }
    if unreachable is not None:
        row["unreachable"] = unreachable
    row.update(extra)
    return row


def finish(*, code=0, streak=3, days=3, lineno=99):
    return {"event": "finish", "t": 900.0, "code": code, "verified_streak": streak,
            "days": days, "actions": 30, "minutes": 10, "_lineno": lineno}


def green_rows(days: int = 3):
    rows: list[dict] = []
    base = [1, "spring", 10]
    for i in range(days):
        d = [base[0], base[1], base[2] + i]
        nd = [base[0], base[1], base[2] + i + 1]
        rows += [day_start(d, t=i * 300.0), sleep_ok(t=i * 300.0 + 100),
                 day_end(d, nd, t=i * 300.0 + 200)]
    rows.append(finish())
    return rows


def tweak(rows, event, **fields):
    """把第一条该 `event` 的行改字段（其余不动）。"""
    out = []
    done = False
    for r in rows:
        if r.get("event") == event and not done:
            nr = dict(r)
            nr.update(fields)
            out.append(nr)
            done = True
        else:
            out.append(r)
    return out


class TestVerifyRun3(unittest.TestCase):
    def check(self, rows, *, days=3):
        ok, summary = vr.report(rows, target_days=days)
        return ok, summary

    # ------------------------------------------------------------ 正例
    def test_green_ledger_passes(self):
        ok, s = self.check(green_rows())
        self.assertTrue(ok, f"绿账本不该判红：{s.get('problems')}")
        self.assertEqual(s["verified_streak_tail"], 3)
        self.assertEqual(s["problems"], [])

    def test_missing_finish_marks_the_verdict_provisional(self):
        """没有 finish 的账本（run 仍在进行/被中断）⇒ `finish_present=False` + info 明说判决为临时。

        事故来源：Lead 曾在长跑器写盘途中读账本，读到半行 `day_end`（缺 verified）而误判。
        """
        rows = [r for r in green_rows() if r.get("event") != "finish"]
        ok, s = self.check(rows)
        self.assertFalse(s["finish_present"])
        self.assertTrue(
            any("判决为临时" in i for i in s["infos"]),
            f"缺 finish 时必须提示判决为临时：{s['infos']}",
        )
        ok2, s2 = self.check(green_rows())
        self.assertTrue(s2["finish_present"])
        self.assertFalse(any("判决为临时" in i for i in s2["infos"]))

    # ------------------------------------------------------------ 负例矩阵
    def test_no_work_with_dry_crops_is_problem(self):
        """run3 连睡病灶：以 no_work 收尾却还有干作物（户外证据 dry>0）。"""
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end":
                rows[i] = day_end(r["final"]["day"], r["day_after"],
                                  ended_reason="no_work:确实找不到可做的活", dry=1,
                                  checks={"watered_outdoor": False})
                break
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(any("run3 连睡病复发" in p for p in s["problems"]), s["problems"])

    def test_vacuum_verified_day_is_problem(self):
        """真空日：有阶段记录却 0 成功动作，不许自称 VERIFIED。"""
        rows = tweak(green_rows(), "day_end", ok_steps=0, stages=[stage(ok=0, failed=0)])
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(any("成功动作 0 步" in p for p in s["problems"]), s["problems"])

    # ------------------------------------------- 在场证据（Lead 2026-10-17，task-146 CAVEAT-1）
    def _zero_stage_day(self, *, with_farm_signal: bool):
        """0 阶段 + 自称 VERIFIED + `no_work` 理由的一天（run9c summer 20 的形态）。"""
        rows = [
            day_start([1, "spring", 10], t=0.0, lineno=1),
            sleep_ok(t=100.0, reason="no_work:确实找不到可做的活", lineno=2),
        ]
        if with_farm_signal:
            rows.append({"event": "plot", "t": 50.0, "zone": "field_ne", "_lineno": 3})
        rows.append(
            day_end([1, "spring", 10], [1, "spring", 11], t=200.0, stages=[], ok_steps=0,
                    ended_reason="no_work:确实找不到可做的活")
        )
        rows.append(finish(streak=1, days=1))
        return rows

    def test_zero_stage_day_without_farm_evidence_is_problem(self):
        """run9c summer 20：雨日醒在室内、日初 goto_farm 被模态挡住、22.81 秒 0 动作却 VERIFIED。

        旧的真空日闸门只认 `ended_reason` 前缀 `no_work` ⇒ 放过了这种"室内自述没活"的假达标。
        现在必须有**户外农场的在场证据**（plot / work_spot / water_far / tool_refused … 或成功的
        goto_farm）才算，否则判红。
        """
        ok, s = self.check(self._zero_stage_day(with_farm_signal=False), days=1)
        self.assertFalse(ok, "0 阶段 + 无在场证据 + 自称 VERIFIED 必须判红")
        self.assertTrue(any("在场证据" in p for p in s["problems"]), s["problems"])

    def test_zero_stage_day_with_farm_evidence_is_accepted(self):
        """正对照：确实上过农场（有 plot 证据）且理由是无活可做 ⇒ 允许 0 阶段 VERIFIED。"""
        ok, s = self.check(self._zero_stage_day(with_farm_signal=True), days=1)
        self.assertTrue(ok, f"有在场证据的真空日不该判红：{s['problems']}")
        self.assertTrue(any("在场证据" in i for i in s["infos"]), s["infos"])

    def test_failed_underreport_is_problem(self):
        """洗账：stage 侧 2 格失败，日级 failed_steps=0，且无环境/无结论可解释。"""
        rows = tweak(green_rows(), "day_end", ok_steps=5, failed_steps=0,
                     stages=[stage("clear_area", tiles=5, ok=5, failed=2)])
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(any("账目不可信" in p for p in s["problems"]), s["problems"])

    # --------------------------------------------------- task-84（死苗不浇水）口径
    def test_no_work_with_uncleared_dead_crops_is_problem(self):
        """死苗不许当"今天没活"的借口：`no_work` 收尾 + `dry_dead>0` ⇒ 判红。"""
        rows = tweak(green_rows(), "day_end",
                     ended_reason="no_work:确实找不到可做的活", dry=0, dry_dead=2,
                     checks={"watered_outdoor": True})
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(any("dry_dead=2" in p for p in s["problems"]), s["problems"])

    def test_window_evidence_without_any_crop_is_problem(self):
        """task-92 NIT-2：`scope=window` 且窗口里 `crops==0` 时，`dry==0 ⇒ watered_outdoor=true` 不可采信
        —— 没看到的干作物（run7 的 `[12,30]`）正是被这条放过去的。"""
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end":
                rows[i] = day_end(r["final"]["day"], r["day_after"], dry=0,
                                  checks={"watered_outdoor": True},
                                  final_water={"t": r["t"] - 1, "location": "Farm", "tiles": 1,
                                               "crops": 0, "dry": 0, "scope": "window"})
                break
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(any("crops=0" in p for p in s["problems"]), s["problems"])

    def test_farm_scope_evidence_is_still_fine(self):
        """正对照：farm 口径（真扫全场）依旧被信任，不许把 NIT-2 修成"凡 window 就红"。"""
        rows = tweak(green_rows(), "day_end",
                     final_water={"t": 199.0, "location": "Farm", "tiles": 30, "crops": 5,
                                  "dry": 0, "scope": "farm"})
        ok, s = self.check(rows)
        self.assertTrue(ok, s["problems"])

    def test_on_farm_evidence_gap_is_reported_as_info(self):
        """task-96 配套：发生在**农场里**的 farm 证据缺口必须可见
        （fail-closed 的可观测面 —— task-92 打穿的 fail-open 入口就在这条上）。"""
        rows = green_rows()
        rows.insert(1, {"event": "farm_evidence_unavailable", "t": 1.0, "on_farm": True,
                        "complete": False})
        ok, s = self.check(rows)
        self.assertTrue(ok, s["problems"])
        self.assertTrue(any("人在农场且 farm 口径不可用" in i for i in s["infos"]), s["infos"])

    def test_gave_up_dry_is_honest_info_not_problem(self):
        """`gave_up_dry` 是如实收尾（当天不达标），工具不许把它当异常。"""
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end":
                rows[i] = day_end(r["final"]["day"], r["day_after"],
                                  ended_reason="gave_up_dry:窗外干格全部认输",
                                  verified=False, dry=1, dry_dead=0,
                                  checks={"watered_outdoor": False, "day_justified": False},
                                  gave_up_tiles=[[12, 30]])
                break
        ok, s = self.check(rows)          # 尾部 streak 归零 ⇒ 整体不达标，但问题应来自跨界/未达标而非"异常"
        self.assertFalse(ok)
        self.assertTrue(any("gave_up_dry" in i for i in s["infos"]), s["infos"])
        self.assertFalse(any("dry_dead" in p for p in s["problems"]), s["problems"])

    def test_missing_dry_dead_is_info_not_pass(self):
        """旧账本缺 `dry_dead` ⇒ 只记 info（不算通过、也不算失败）。"""
        ok, s = self.check(green_rows())
        self.assertTrue(ok, s.get("problems"))
        self.assertTrue(any("dry_dead" in i for i in s["infos"]), s["infos"])

    def test_missing_verified_field_is_problem(self):
        """字段整体缺失（不是 null）也必须判红：缺失 ≠ 通过。"""
        rows = green_rows()
        for r in rows:
            if r.get("event") == "day_end":
                r.pop("verified", None)
                break
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(any("缺 verified" in p for p in s["problems"]), s["problems"])

    def test_mod_version_mismatch_is_problem(self):
        """版本不符的账本不能当验收证据（v0.7.17 教训）。"""
        rows = green_rows()
        rows.append({"event": "mod_version_mismatch", "t": 1.0, "_lineno": 4})
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(any("Mod 版本" in p for p in s["problems"]), s["problems"])

    # ------------------------------------------------------------ 信息项（不许误杀）
    def test_unreachable_is_info_not_a_fail(self):
        """task-52：不可达格不许算硬失败；工具要独立自算并记 info。"""
        rows = green_rows()
        rows.insert(1, {"event": "blocked", "reason": "清不掉：四邻都站不过去", "tile": [71, 34],
                        "t": 50.0, "_lineno": 2})
        ok, s = self.check(rows)
        self.assertTrue(ok, f"不可达不该判红：{s.get('problems')}")
        self.assertTrue(any("不可达" in i for i in s["infos"]), s["infos"])

    def test_unreachable_ledger_field_mismatch_is_info_only(self):
        rows = tweak(green_rows(), "day_end", unreachable=3)
        rows.insert(1, {"event": "blocked", "reason": "四邻都站不过去", "tile": [71, 34],
                        "t": 50.0, "_lineno": 2})
        ok, s = self.check(rows)
        self.assertTrue(ok, f"计数不一致只许记 info：{s.get('problems')}")
        self.assertTrue(any("不一致" in i for i in s["infos"]), s["infos"])

    def test_unreachable_exemption_explains_leftover(self):
        """task-52：账本把"不可达且在上界内"的遗留格从 unmet 里扣掉 ⇒ 自算也必须扣同一笔，
        否则 run6 会被误判成「check 与自算不一致」。"""
        rows = tweak(
            green_rows(),
            "day_end",
            stages=[stage(tiles=10, ok=8, leftover=2)],
            ok_steps=8,
            unreachable=2,
            unreachable_bound=5,
            unreachable_exempt=2,
            unreachable_tiles=[[71, 34], [74, 34]],
            attempted=10,
        )
        ok, s = self.check(rows)
        self.assertTrue(ok, f"豁免已解释 leftover，不该判红：{s.get('problems')}")
        self.assertFalse(any("no_unmet_stages" in p for p in s["problems"]), s["problems"])

    def test_unreachable_leaves_unexplained_leftover_as_problem(self):
        """同一构造但不给 `unreachable_exempt` ⇒ 那 2 格遗留无人解释 ⇒ 必须判红。"""
        rows = tweak(
            green_rows(),
            "day_end",
            stages=[stage(tiles=10, ok=8, leftover=2)],
            ok_steps=8,
            unreachable=2,
            unreachable_bound=5,
            attempted=10,
        )
        ok, s = self.check(rows)
        self.assertFalse(ok, "没写豁免就必须把遗留格算作没做完")
        self.assertTrue(any("no_unmet_stages" in p for p in s["problems"]), s["problems"])

    def test_unreachable_over_bound_is_problem(self):
        """`checks.unreachable_within_bound=false` ＝ 豁免越界 ⇒ 洗白风险，必须判红。"""
        rows = tweak(green_rows(), "day_end", checks={"unreachable_within_bound": False})
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(any("unreachable_within_bound" in p for p in s["problems"]), s["problems"])

    def test_single_day_green_is_not_enough_for_three(self):
        ok, s = self.check(green_rows(days=1), days=3)
        self.assertFalse(ok)
        self.assertEqual(s["verified_streak_tail"], 1)


    # ------------------------------------------------------------ LLM 覆盖口径（Lead 2026-10-14 裁定）
    def test_llm_fallback_is_not_counted_as_model_output(self):
        """run2 L17 分歧：`llm=true` + `source=deterministic_fallback` 只算"发起过调用"。

        两个数都要有：`decisions_llm`（调用）与 `decisions_llm_used`（模型结果真被采纳），
        否则 run6 的"LLM 覆盖"会把截断后的兜底也算成模型产出。
        """
        rows = green_rows()
        rows.insert(1, {"event": "decision", "llm": True, "source": "llm", "boundary": "new_day",
                        "t": 5.0, "_lineno": 2})
        rows.insert(2, {"event": "decision", "llm": True, "source": "deterministic_fallback",
                        "boundary": "new_day", "fallback": "llm_error:truncated", "t": 6.0,
                        "_lineno": 3})
        rows.insert(3, {"event": "decision", "llm": False, "source": "deterministic",
                        "t": 7.0, "_lineno": 4})
        ok, s = self.check(rows)
        self.assertTrue(ok, f"决策计数不该影响结论：{s.get('problems')}")
        self.assertEqual(s["decisions"], 3)
        self.assertEqual(s["decisions_llm"], 2)          # 发起过调用
        self.assertEqual(s["decisions_llm_used"], 1)     # 真采用模型结果
        self.assertEqual(s["decisions_llm_fallback"], 1)
        self.assertTrue(any("兜底" in i for i in s["infos"]), s["infos"])

    def test_no_fallback_means_no_extra_info(self):
        rows = green_rows()
        rows.insert(1, {"event": "decision", "llm": True, "source": "llm", "t": 5.0, "_lineno": 2})
        ok, s = self.check(rows)
        self.assertTrue(ok)
        self.assertEqual((s["decisions_llm"], s["decisions_llm_used"], s["decisions_llm_fallback"]),
                         (1, 1, 0))
        self.assertFalse(any("兜底" in i for i in s["infos"]), s["infos"])

    def test_llm_error_without_flag_is_still_counted_as_called_only(self):
        """即使 `llm` 字段缺失/为假，只要 `source==llm` 也不该被算成"没调用" —— 口径各算各的。"""
        rows = green_rows()
        rows.insert(1, {"event": "decision", "source": "llm", "t": 5.0, "_lineno": 2})
        ok, s = self.check(rows)
        self.assertTrue(ok)
        self.assertEqual(s["decisions_llm"], 0)
        self.assertEqual(s["decisions_llm_used"], 0)

    # ------------------------------------------------------------ 留痕完整性（task-56）
    def test_missing_trace_file_is_info(self):
        """账本引用了一个不存在的留痕文件 ⇒ 只记 info，不改结论（复盘材料缺了 ≠ 当天不达标）。"""
        rows = green_rows()
        rows.insert(1, {"event": "decision", "llm": True, "source": "llm", "t": 5.0,
                        "_lineno": 2, "llm_trace": "logs/_no_such_trace_file.jsonl",
                        "llm_trace_hash": "abc123"})
        ok, s = self.check(rows)
        self.assertTrue(ok, f"缺留痕不该判红：{s.get('problems')}")
        self.assertTrue(any("留痕缺失" in i for i in s["infos"]), s["infos"])

    def test_trace_line_count_must_match_references(self):
        """留痕行数与账本引用数不符（多/少）都要记 info —— 否则"一一对应"只是口号。"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "run6-llm.jsonl"
            p.write_text('{"a":1}\n', encoding="utf-8")  # 只有 1 行
            rows = green_rows()
            for i in (1, 2):
                rows.insert(i, {"event": "decision", "llm": True, "source": "llm", "t": float(i),
                                "_lineno": 10 + i, "llm_trace": str(p), "llm_trace_hash": "h"})
            ok, s = self.check(rows)
            self.assertTrue(ok, f"行数不符只记 info：{s.get('problems')}")
            self.assertTrue(any("留痕行数与引用数不符" in i for i in s["infos"]), s["infos"])

    def test_matching_trace_lines_are_silent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "run6-llm.jsonl"
            p.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
            rows = green_rows()
            for i in (1, 2):
                rows.insert(i, {"event": "decision", "llm": True, "source": "llm", "t": float(i),
                                "_lineno": 10 + i, "llm_trace": str(p), "llm_trace_hash": "h"})
            ok, s = self.check(rows)
            self.assertTrue(ok)
            self.assertFalse(any("留痕" in i for i in s["infos"]), s["infos"])

    def test_review_rows_do_not_break_the_decision_line_count(self):
        """task-136：复盘调用也写同一个留痕文件（`kind="review"`）⇒ 只对决策行数做比对，
        复盘行单独说明，不许报"行数与引用数不符"的假问题。"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "run9c-llm.jsonl"
            p.write_text('{"kind":"decision","a":1}\n{"kind":"decision","b":2}\n'
                         '{"kind":"review","notes":["x"]}\n', encoding="utf-8")
            rows = green_rows()
            for i in (1, 2):
                rows.insert(i, {"event": "decision", "llm": True, "source": "llm", "t": float(i),
                                "_lineno": 10 + i, "llm_trace": str(p), "llm_trace_hash": "h"})
            ok, s = self.check(rows)
            self.assertTrue(ok, s.get("problems"))
            self.assertFalse(any("不符" in i for i in s["infos"]), s["infos"])
            self.assertTrue(any("复盘行 1 行" in i for i in s["infos"]), s["infos"])

    def test_review_rows_do_not_mask_a_real_decision_mismatch(self):
        """复盘行不能把真缺口洗白：决策行只有 1 行而账本引用 2 条 ⇒ 仍要报不符。"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "run9c-llm.jsonl"
            p.write_text('{"kind":"decision","a":1}\n{"kind":"review","notes":["x"]}\n'
                         '{"kind":"review","notes":["y"]}\n', encoding="utf-8")
            rows = green_rows()
            for i in (1, 2):
                rows.insert(i, {"event": "decision", "llm": True, "source": "llm", "t": float(i),
                                "_lineno": 10 + i, "llm_trace": str(p), "llm_trace_hash": "h"})
            ok, s = self.check(rows)
            self.assertTrue(ok)
            self.assertTrue(any("决策行 1 行、账本引用 2 条" in i for i in s["infos"]), s["infos"])


    # ------------------------------------------------------------ no_water 诚实收尾（task-49 通道）
    def test_no_water_day_is_not_verified_and_only_info(self):
        """`no_water`（想浇但打不到水）是合法解释：当天不达标，但工具不该判红。

        它也是唯一可能被拿来早睡的通道 —— 所以必须同时验两件事：
        ①`day_justified` 为假 ⇒ 当天 `verified` 不可能为真；②工具记一条 info 让人看得见。
        """
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 11:  # 中间那天
                rows[i] = day_end(r["final"]["day"], r["day_after"],
                                  ended_reason="no_water:想浇但拿不到水",
                                  dry=1, verified=False,
                                  checks={"watered_outdoor": False, "day_justified": False})
        ok, s = self.check(rows)
        self.assertFalse(ok, "中间那天没达标，尾部连续天数应为 1")
        self.assertEqual(s["verified_streak_tail"], 1)
        self.assertFalse(any("连睡病复发" in p for p in s["problems"]), s["problems"])
        self.assertTrue(any("no_water" in i for i in s["infos"]), s["infos"])

    def test_no_water_claim_cannot_yield_a_verified_day(self):
        """防洗白：即使账本硬说自己 verified，`day_justified=false` 也必须被 tools 抓住。"""
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 11:
                # 故意伪造：ended_reason=no_water 却 verified=true + day_justified=true
                rows[i] = day_end(r["final"]["day"], r["day_after"],
                                  ended_reason="no_water:想浇但拿不到水",
                                  dry=1, verified=True,
                                  checks={"watered_outdoor": False, "day_justified": True})
        ok, s = self.check(rows)
        self.assertFalse(ok, "水面证据缺失（dry=1）时不许出现达标日")
        self.assertTrue(any("dry" in p or "watered_outdoor" in p or "干" in p for p in s["problems"]),
                        s["problems"])


    # ------------------------------------------------------------ 三腿覆盖（P3 ⑥ 的四步里哪几步真跑过）
    def test_missing_legs_are_listed_as_info(self):
        """绿账本只跑浇水腿 ⇒ 必须点出"清障/开垦"与"播种"全程 0 步（否则"三层过=四层过"）。"""
        ok, s = self.check(green_rows())
        self.assertTrue(ok, s.get("problems"))
        self.assertEqual(s["leg_ok"]["浇水"], 30)      # 3 天 × 10 步
        self.assertEqual(s["leg_ok"]["播种"], 0)
        self.assertTrue(any("三腿覆盖" in i and "播种" in i for i in s["infos"]), s["infos"])
        self.assertTrue(any("三腿覆盖" in i and "清障" in i for i in s["infos"]), s["infos"])

    def test_all_three_legs_covered_silently(self):
        """四类阶段都真做过 ⇒ 三腿覆盖不再刷 info，且计数逐腿可查。"""
        rows: list[dict] = []
        for i in range(3):
            d = [1, "spring", 10 + i]
            nd = [1, "spring", 11 + i]
            stages = [stage("clear_area", tiles=2, ok=2), stage("till_area", tiles=2, ok=2),
                      stage("plant_area", tiles=2, ok=2), stage("water_area", tiles=2, ok=2)]
            rows += [day_start(d, t=i * 300.0), sleep_ok(t=i * 300.0 + 100),
                     day_end(d, nd, t=i * 300.0 + 200, ok_steps=8, stages=stages)]
        rows.append(finish())
        ok, s = self.check(rows)
        self.assertTrue(ok, s.get("problems"))
        self.assertEqual(s["leg_ok"], {"清障/开垦": 12, "播种": 6, "浇水": 6})
        self.assertFalse(any("三腿覆盖" in i for i in s["infos"]), s["infos"])


    # ------------------------------------------------------------ task-63：锄不动（tool_ineffective）豁免
    def test_refused_within_bound_false_is_a_problem(self):
        """防洗白：账本自称"游戏全拒绝"并越界 ⇒ 必须判红（不能靠拒绝换一个达标日）。"""
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 11:
                rows[i] = day_end(r["final"]["day"], r["day_after"], dry=0,
                                  checks={"refused_within_bound": False},
                                  refused=9, refused_bound=5)
        ok, s = self.check(rows)
        self.assertFalse(ok, "拒绝豁免越界必须判红")
        self.assertTrue(any("refused_within_bound" in p for p in s["problems"]), s["problems"])

    def test_tool_refused_journal_newer_than_ledger_is_a_problem(self):
        """账目可信：journal 有 `tool_refused` 事件而账本计数更少 ⇒ 判红。"""
        rows = green_rows()
        rows.insert(2, {"event": "tool_refused", "t": 50.0, "_lineno": 90,
                        "tile": [38, 20], "status": "tool_ineffective"})
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 10:
                rows[i] = day_end(r["final"]["day"], r["day_after"], dry=0,
                                  refused=0, refused_bound=5)
        ok, s = self.check(rows)
        self.assertFalse(ok, "账本拒绝计数少于 journal 自算 ⇒ 账目不可信")
        self.assertTrue(any("拒绝计数" in p for p in s["problems"]), s["problems"])

    def test_tool_refused_matching_ledger_is_only_info(self):
        """口径一致时只记信息项，不改结论（绿账本仍达标）。"""
        rows = green_rows()
        rows.insert(2, {"event": "tool_refused", "t": 50.0, "_lineno": 90,
                        "tile": [38, 20], "status": "tool_ineffective"})
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 10:
                rows[i] = day_end(r["final"]["day"], r["day_after"], dry=0,
                                  refused=1, refused_bound=5)
        ok, s = self.check(rows)
        self.assertTrue(ok, s.get("problems"))
        self.assertTrue(any("锄不动被拒" in i for i in s["infos"]), s["infos"])

    # ---------------------------------------------- task-52+63：两笔豁免都要从 unmet 里各自扣掉
    def test_both_exemptions_are_subtracted_from_unmet(self):
        """leftover 2 格、别人不可达 1 格 + 锄不动 1 格、当天有成功动作 ⇒ 不许报"自算不一致"。

        这是 run6 最可能踩的误报：longrun 写 `no_unmet_stages=true`（两笔豁免各自扣完为 0），
        而工具若只扣 unreachable 一笔，就会把合法的一天判成"自述与自算不一致"。
        """
        rows: list[dict] = []
        for i in range(3):
            d = [1, "spring", 10 + i]
            nd = [1, "spring", 11 + i]
            stages = [stage("till_area", tiles=3, ok=1, skipped=2, leftover=2)]
            rows += [
                day_start(d, t=i * 300.0), sleep_ok(t=i * 300.0 + 100),
                day_end(d, nd, t=i * 300.0 + 200, ok_steps=1, stages=stages,
                        checks={"unreachable_within_bound": True, "refused_within_bound": True},
                        unreachable=1, unreachable_bound=5, unreachable_exempt=1,
                        unreachable_tiles=[[38, 20]],
                        refused=1, refused_bound=5, refused_exempt=1,
                        refused_tiles=[[39, 20]]),
            ]
        rows.append(finish())
        ok, s = self.check(rows)
        self.assertFalse(any("自算不一致" in p for p in s["problems"]), s["problems"])
        self.assertTrue(ok, s.get("problems"))

    def test_vacuum_exempt_day_is_not_a_mismatch(self):
        """全被豁免 + 0 成功动作：longrun 会写 `no_unmet_stages=false`（防真空），工具不许当成"自算不一致"。"""
        rows: list[dict] = []
        for i in range(3):
            d = [1, "spring", 10 + i]
            nd = [1, "spring", 11 + i]
            stages = [stage("clear_area", tiles=3, ok=0, skipped=3, leftover=3)]
            rows += [
                day_start(d, t=i * 300.0), sleep_ok(t=i * 300.0 + 100),
                day_end(d, nd, t=i * 300.0 + 200, ok_steps=0, stages=stages, verified=False,
                        started_by="sleep",
                        checks={"no_unmet_stages": False, "no_hard_failures": False,
                                "unreachable_within_bound": True, "refused_within_bound": True},
                        unreachable=3, unreachable_bound=5, unreachable_exempt=3,
                        unreachable_tiles=[[60, 20], [61, 20], [62, 20]],
                        refused=0, refused_bound=5, refused_exempt=0),
            ]
        rows.append(finish(code=1, streak=0))
        ok, s = self.check(rows)
        self.assertFalse(any("自算不一致" in p for p in s["problems"]), s["problems"])
        self.assertFalse(ok, "全被豁免且 0 成功的一天不可能构成达标链")

    # ---------------------------------------------- 同日重试：自算计数必须按"会话"而不是按"日"比
    def test_same_day_retry_does_not_fake_unreachable_mismatch(self):
        """run6 实测形态：同一天跑两轮，每轮 `day_end.unreachable=2`，逐格事件两会话各 2 条。

        日级合并会拿 4 去比单轮的 2 ⇒ 假"账本与自算不一致"。本用例锁死"按会话比"。
        """
        d = [1, "summer", 4]
        rows: list[dict] = []
        for i in range(2):
            rows += [
                day_start(d, t=i * 100.0, lineno=1 + i * 10),
                {"event": "unreachable", "t": i * 100.0 + 10, "_lineno": 2 + i * 10,
                 "tile": [60 + i, 20], "reason": "四邻都站不过去（没有落脚点）"},
                {"event": "unreachable", "t": i * 100.0 + 11, "_lineno": 3 + i * 10,
                 "tile": [61 + i, 20], "reason": "四邻都站不过去（没有落脚点）"},
                sleep_ok(t=i * 100.0 + 20, reason="no_work:确实找不到可做的活", lineno=4 + i * 10),
                day_end(d, None, t=i * 100.0 + 30, ok_steps=0, verified=False,
                        ended_by="stuck", ended_reason="stuck:连续 3 轮世界没有任何变化",
                        stages=[stage("clear_dead", tiles=2, ok=0, skipped=0, leftover=2)],
                        checks={"no_unmet_stages": False, "no_hard_failures": True,
                                "unreachable_within_bound": True, "refused_within_bound": True},
                        unreachable=2, unreachable_bound=5, unreachable_exempt=2,
                        refused=0, refused_bound=5, refused_exempt=0),
            ]
        ok, s = self.check(rows, days=3)
        self.assertFalse(ok, "0 跨日、同一天两轮 stuck 不可能是达标跑")
        self.assertFalse(
            any("不可达计数账本" in i and "不一致" in i for i in s["infos"]), s["infos"]
        )
        self.assertTrue(any("不可达" in i and "自算=2 次/2 格" in i for i in s["infos"]), s["infos"])

    def test_same_day_retry_still_catches_real_missing_unreachable_count(self):
        """反向：journal 里有不可达事件、但账本 `unreachable` 少写 ⇒ 仍要报"不一致"（防缺失当通过）。"""
        d = [1, "summer", 4]
        rows: list[dict] = [
            day_start(d, t=0.0, lineno=1),
            {"event": "unreachable", "t": 10.0, "_lineno": 2, "tile": [60, 20],
             "reason": "四邻都站不过去（没有落脚点）"},
            sleep_ok(t=20.0, reason="no_work:确实找不到可做的活", lineno=3),
            day_end(d, None, t=30.0, ok_steps=0, verified=False, ended_by="stuck",
                    ended_reason="stuck:连续 3 轮世界没有任何变化",
                    stages=[stage("clear_dead", tiles=1, ok=0, skipped=0, leftover=1)],
                    checks={"no_unmet_stages": False, "no_hard_failures": True,
                            "unreachable_within_bound": True, "refused_within_bound": True},
                    unreachable=0, unreachable_bound=5, unreachable_exempt=0,
                    refused=0, refused_bound=5, refused_exempt=0),
        ]
        ok, s = self.check(rows, days=1)
        self.assertFalse(ok)
        self.assertTrue(
            any("不可达计数账本" in i and "不一致" in i for i in s["infos"]), s["infos"]
        )

    # ---------------------------------------------- task-71：对抗加固（deputy task-54 实测打穿的三条通道）
    def test_forged_large_unreachable_bound_is_problem(self):
        """账本把豁免上界写成 9999（attempted=10 ⇒ 自算应为 5）⇒ 必须判红，不许无条件采信账本。"""
        rows = tweak(green_rows(), "day_end", attempted=10, unreachable=0,
                     unreachable_bound=9999, unreachable_exempt=0,
                     checks={"unreachable_within_bound": True})
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(
            any("上界" in p and "自算" in p for p in s["problems"]), s["problems"]
        )

    def test_forged_large_refused_bound_is_problem(self):
        """同一通道的被拒侧：`refused_bound` 也不许被账本放宽。"""
        rows = tweak(green_rows(), "day_end", attempted=10, refused=0,
                     refused_bound=9999, refused_exempt=0,
                     checks={"refused_within_bound": True})
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(
            any("被拒豁免上界" in p and "自算" in p for p in s["problems"]), s["problems"]
        )

    def test_exemption_without_coordinates_is_problem(self):
        """扣了豁免却没有任何坐标（journal 无逐格事件、账本 tiles 也空）⇒ 判红（缺失≠通过）。"""
        rows = tweak(green_rows(), "day_end", attempted=10, unreachable=2,
                     unreachable_bound=5, unreachable_exempt=2,
                     checks={"unreachable_within_bound": True})
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(
            any("没写任何坐标" in p for p in s["problems"]), s["problems"]
        )

    def test_overlapping_exemption_tiles_is_problem(self):
        """同一格同时进 unreachable 与 refused（可重复扣减）⇒ 判红。"""
        rows = green_rows()
        rows.insert(2, {"event": "unreachable", "t": 40.0, "_lineno": 80, "tile": [40, 20],
                        "reason": "四邻都站不过去（没有落脚点）"})
        rows.insert(3, {"event": "tool_refused", "t": 41.0, "_lineno": 81, "tile": [40, 20],
                        "status": "tool_ineffective"})
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 10:
                rows[i] = day_end(r["final"]["day"], r["day_after"], attempted=10,
                                  unreachable=1, unreachable_bound=5, unreachable_exempt=1,
                                  refused=1, refused_bound=5, refused_exempt=1,
                                  checks={"unreachable_within_bound": True,
                                          "refused_within_bound": True})
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(
            any("同一格同时进两套豁免" in p for p in s["problems"]), s["problems"]
        )

    def test_disjoint_exemptions_with_coordinates_stay_green(self):
        """反向：两套豁免坐标不相交、各带上界内实扣 ⇒ 只记 info，不误报。"""
        rows = green_rows()
        rows.insert(2, {"event": "unreachable", "t": 40.0, "_lineno": 80, "tile": [40, 20],
                        "reason": "四邻都站不过去（没有落脚点）"})
        rows.insert(3, {"event": "tool_refused", "t": 41.0, "_lineno": 81, "tile": [41, 20],
                        "status": "tool_ineffective"})
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 10:
                rows[i] = day_end(r["final"]["day"], r["day_after"], attempted=10,
                                  unreachable=1, unreachable_bound=5, unreachable_exempt=1,
                                  refused=1, refused_bound=5, refused_exempt=1,
                                  checks={"unreachable_within_bound": True,
                                          "refused_within_bound": True})
        ok, s = self.check(rows)
        self.assertFalse(any("同时进两套豁免" in p for p in s["problems"]), s["problems"])
        self.assertFalse(any("没写任何坐标" in p for p in s["problems"]), s["problems"])
        self.assertTrue(ok, s.get("problems"))

    # —— task-68（encircled / frontier_clear / clear_neighbor）：只做自算 + info，不许误判成 problem。
    def test_encircled_is_info_only_and_mismatch_is_info(self):
        """被围住（encircled）单独成类：账本与 journal 对不上只记 info，绝不升 problem。"""
        rows = green_rows()
        rows.insert(2, {"event": "encircled", "t": 40.0, "_lineno": 80, "tile": [50, 20],
                        "action": "clear_dead", "stage": "clear_dead"})
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 10:
                rows[i] = day_end(r["final"]["day"], r["day_after"], encircled=1,
                                  encircled_tiles=[[50, 20], [51, 20]])
        ok, s = self.check(rows)
        self.assertTrue(
            any("被围住（encircled" in i for i in s["infos"]), s["infos"]
        )
        self.assertFalse(
            any("encircled" in p for p in s["problems"]), s["problems"]
        )
        self.assertFalse(
            any("坐标对不上" in p for p in s["problems"]), s["problems"]
        )

    def test_frontier_clear_and_clear_neighbor_are_reported(self):
        """run6 的"零动作收工"要让下一次一眼看得见：frontier_clear 尝试/成功数 + 开路格数。"""
        rows = green_rows()
        rows.insert(2, {"event": "frontier_clear", "t": 40.0, "_lineno": 80, "tile": [60, 20],
                        "acted": False, "attempt": 1, "limit": 20})
        rows.insert(3, {"event": "frontier_clear", "t": 41.0, "_lineno": 81, "tile": [61, 20],
                        "acted": True, "attempt": 2, "limit": 20})
        rows.insert(4, {"event": "clear_neighbor", "t": 42.0, "_lineno": 82, "stage": "clear_dead"})
        ok, s = self.check(rows)
        blob = " | ".join(s["infos"])
        self.assertIn("frontier_clear 尝试 2 次", blob)
        self.assertIn("真清掉 1 次", blob)
        self.assertIn("为开路清掉邻格 1 次", blob)

    def test_stuck_day_with_zero_actions_is_flagged_as_info(self):
        """stuck + 当天 ok_steps=0（run6 形态）⇒ info 点名，且不因此改判（verified 由 day_end 决定）。"""
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 10:
                rows[i] = day_end(r["final"]["day"], None, ok_steps=0, ended_by="stuck",
                                  ended_reason="stuck:连续 3 轮世界没有任何变化",
                                  verified=False, stages=[stage(ok=0, leftover=3)])
        ok, s = self.check(rows)
        self.assertTrue(
            any("零动作收工" in i for i in s["infos"]), s["infos"]
        )
        self.assertFalse(ok)


    def test_encircled_steps_do_not_inflate_the_exemption_bound(self):
        """task-78：上界分母是 `bound_basis = attempted − encircled`。

        deputy-lead 的对抗验收用伪造账本 V5 打穿过旧口径：800 次 `encircled` 把
        `max(5, floor(0.2 × attempted))` 抬到 200 ⇒ 200 格真不可达被豁免、exit 0。
        现在被围住的格不给豁免额度：账本若仍按 `attempted` 写一个更大的 bound ⇒ problem。
        """
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 10:
                rows[i] = day_end(
                    r["final"]["day"], r["day_after"],
                    stages=[stage("clear_dead", tiles=100, ok=0, skipped=0,
                                  attempted=100, encircled=90, unreachable=5,
                                  leftover=95)],
                    attempted=100, encircled=90, unreachable=5,
                    unreachable_bound=20, unreachable_exempt=5,
                    unreachable_tiles=[[50, 20]] * 5,
                )
        ok, s = self.check(rows)
        blob = " | ".join(s["problems"])
        self.assertIn("上界被放宽", blob)
        self.assertFalse(ok)

    def test_bound_basis_field_is_honoured_when_consistent(self):
        """账本写对 `bound_basis`（= attempted − encircled）时不许误报，且上界按它算。"""
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 10:
                rows[i] = day_end(
                    r["final"]["day"], r["day_after"],
                    stages=[stage("clear_dead", tiles=50, ok=10, attempted=50,
                                  encircled=45, unreachable=0, leftover=0)],
                    attempted=50, encircled=45, unreachable=0, bound_basis=5,
                    unreachable_bound=5,
                )
        ok, s = self.check(rows)
        self.assertFalse(any("上界" in p for p in s["problems"]), s["problems"])

    def test_lying_bound_basis_is_reported_even_though_it_gets_clamped(self):
        """task-81 NIT-1：账本谎报 `bound_basis` 必须**留痕**（先比较、再钳）。

        旧写法 `basis = min(_basis, basis_self)` 之后才判 `basis != basis_self`，只要自算 > 0
        就被钳平 ⇒ 这条 problem 永不触发（deputy 的 ADV-4 实测点名 0 行）。这里 stage 自算
        `bound_basis = 50 − 45 = 5`，账本谎报 50 ⇒ 必须报 problem（并仍按自算 5 算上界）。
        """
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 10:
                rows[i] = day_end(
                    r["final"]["day"], r["day_after"],
                    stages=[stage("clear_dead", tiles=50, ok=10, attempted=50,
                                  encircled=45, unreachable=0, leftover=0)],
                    attempted=50, encircled=45, unreachable=0, bound_basis=50,
                    unreachable_bound=10,
                )
        ok, s = self.check(rows)
        blob = " | ".join(s["problems"])
        self.assertIn("上界基数账本", blob)
        self.assertIn("> 自算=5", blob)
        self.assertFalse(ok)

    def test_early_bad_day_does_not_invalidate_the_tail_streak(self):
        """口径（Lead 2026-10-15，run7 定）：验收是"尾部连续 N 天"，窗口外的问题只算历史。

        run7 现场：summer 3/5 被窗口外那 1 格干作物卡住、summer 6 靠 stuck 翻篇自己过去，
        之后 summer 7/8/9 连续三天全绿 ⇒ 必须判达标，并把早期问题列进 `history_problems`。
        """
        bad = [
            day_start([1, "spring", 8], t=0.0),
            sleep_ok(t=100.0),
            day_end([1, "spring", 8], [1, "spring", 9], t=200.0, verified=False,
                    ended_by="stuck", ended_reason="stuck:换过 11 片地都没有目标",
                    dry=1, checks={"watered_outdoor": False, "day_justified": False}),
        ]
        rows = bad + green_rows(3)
        ok, s = self.check(rows)
        self.assertTrue(ok, s["problems"])
        self.assertEqual(s["verified_streak_tail"], 3)
        self.assertEqual(s["problems"], [])
        self.assertTrue(any("spring 8" in p for p in s["history_problems"]), s["history_problems"])

    def test_strict_verdict_is_reported_but_does_not_change_the_tail_verdict(self):
        """严格口径第二判决：窗口外历史问题只进 `strict_verdict`，**不许**改变 rc / `verdict`。

        动机（deputy-lead task-90 §顺带①）："窗口外不计"不能变成默认沉默 —— run8 的
        `_run8-evidence.md` §4 要能一条命令抄到"严格口径是什么"。
        """
        bad = [
            day_start([1, "spring", 8], t=0.0),
            sleep_ok(t=100.0),
            day_end([1, "spring", 8], [1, "spring", 9], t=200.0, verified=False,
                    ended_by="stuck", ended_reason="stuck:换过 11 片地都没有目标",
                    dry=1, checks={"watered_outdoor": False, "day_justified": False}),
        ]
        ok, s = self.check(bad + green_rows(3))
        self.assertTrue(ok, s["problems"])
        self.assertEqual(s["verdict"], "VERIFIED")
        self.assertEqual(s["strict_verdict"], "needs_review")
        self.assertEqual(s["strict_problem_count"], len(s["history_problems"]))
        # 反面：整本干净时两个判决必须一致（不许无病呻吟）。
        ok2, s2 = self.check(green_rows(3))
        self.assertTrue(ok2)
        self.assertEqual(s2["strict_verdict"], "VERIFIED")
        self.assertEqual(s2["strict_problem_count"], 0)

    def test_run_ending_on_a_bad_day_is_still_not_ok(self):
        """窗口没打满时不降级：尾部一天坏 ⇒ streak 0 ⇒ 仍判未达标，问题不许被搬进 history。"""
        rows = green_rows(3) + [
            day_start([1, "spring", 13], t=900.0),
            sleep_ok(t=1000.0),
            day_end([1, "spring", 13], [1, "spring", 14], t=1100.0, verified=False,
                    ended_by="stuck", ended_reason="stuck:连续 3 轮世界没有任何变化",
                    dry=1, checks={"watered_outdoor": False, "day_justified": False}),
        ]
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertEqual(s["verified_streak_tail"], 0)
        self.assertEqual(s["history_problems"], [])
        self.assertTrue(any("spring 13" in p for p in s["problems"]), s["problems"])

    def test_stuck_flushed_day_must_not_be_verified(self):
        """task-73：卡死翻篇只许翻页，不许洗白 —— `stuck_flushed=true` 的日子记 verified ⇒ problem。"""
        rows = green_rows()
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 11:
                rows[i] = day_end(r["final"]["day"], r["day_after"], stuck_flushed=True)
        ok, s = self.check(rows)
        self.assertTrue(
            any("stuck 翻篇" in p and "verified" in p for p in s["problems"]), s["problems"]
        )
        self.assertFalse(ok)

    def test_stuck_flush_day_is_reported_as_info(self):
        """翻篇日如实 rejected（verified=false）⇒ 只记 info，并报次数供"连续 3 天"复核。"""
        rows = green_rows()
        rows.insert(2, {"event": "stuck_flush", "t": 41.0, "_lineno": 80,
                        "ok": True, "count": 1, "limit": 2})
        for i, r in enumerate(rows):
            if r.get("event") == "day_end" and r["final"]["day"][2] == 11:
                rows[i] = day_end(r["final"]["day"], None, ok_steps=0, ended_by="stuck",
                                  ended_reason="stuck:连续 3 轮世界没有任何变化",
                                  verified=False, stages=[stage(ok=0, leftover=2)],
                                  stuck_flushed=True)
        ok, s = self.check(rows)
        blob = " | ".join(s["infos"])
        self.assertIn("stuck 日翻篇", blob)
        self.assertFalse(any("stuck 翻篇" in p for p in s["problems"]), s["problems"])


    # ------------------------------------------------------------ 窗口口径健壮性（task-86 FAIL 回归）
    def test_bracket_in_day_label_cannot_hide_an_in_window_problem(self):
        """task-86 FAIL 回归：日期标签里塞 `]` 不许把**窗口内**的问题骗成 history。

        对抗验收（deputy-lead，2026-10-15）打穿的形态：尾部 3 天里的一天 `verified=true`、
        但账目自相矛盾（stage `leftover=2` 而 `checks.no_unmet_stages=true`），同时该日
        `day[1]` 写成 `spring]x`。旧解析 `p[1:].split("]", 1)[0]` 按**第一个 `]`** 截断 ⇒
        标签被截成 `spring`、与真实日标签 `spring]x 10` 不匹配 ⇒ 降级进 `history_problems`
        ⇒ **假 VERIFIED**（该通道在口径变更 `7c4ff68` 之后才出现）。

        现在：标签生成时净化（`_clean_label`）+ 解析时按已知日标签最长前缀匹配
        （`problem_day`）+ 头部标签不在已知日集合时一律 fatal ⇒ 这条问题必须留在 problems。
        """
        rows = tweak(
            green_rows(),
            "day_end",
            stages=[stage(tiles=10, ok=8, leftover=2)],
            ok_steps=8,
            unreachable=2,
            unreachable_bound=5,
            attempted=10,
        )
        out: list[dict] = []
        for r in rows:
            nr = dict(r)
            if nr.get("event") == "day_start" and list(nr.get("day") or [None, None, None])[2] == 10:
                nr["day"] = [1, "spring]x", 10]
                nr["final"] = {"day": [1, "spring]x", 10]}
            if nr.get("event") == "day_end" and nr["final"]["day"][2] == 10:
                damaged = dict(nr)
                damaged["final"] = dict(nr["final"], day=[1, "spring]x", 10])
                damaged["day_after"] = [1, "spring]x", 11]
                nr = damaged
            out.append(nr)
        ok, s = self.check(out)
        self.assertEqual(s["verified_streak_tail"], 3, "尾部仍应是 3 天（这是攻击成立的前提）")
        self.assertFalse(ok, "窗口内的问题带 `]` 标签也必须 fatal")
        self.assertEqual(s["history_problems"], [], s["history_problems"])
        self.assertTrue(any("no_unmet_stages" in p for p in s["problems"]), s["problems"])

    def test_unknown_problem_day_label_is_never_demoted(self):
        """头部标签解析不出 / 不在已知日集合 ⇒ 当全局问题（fatal），不许降级。

        `problem_day()` 先按已知标签最长前缀匹配；匹配不到才退回朴素截断，而调用方要求
        "解析出的标签必须属于某个已知日"才允许降级 —— 伪造一个不存在的日标签不能绕过窗口。
        """
        known = {"spring 10", "springx 11"}
        self.assertEqual(vr.day_key({"day": [1, "spring]x", 11]}), "springx 11")
        self.assertEqual(vr.problem_day("[spring 10] boom", known), "spring 10")
        self.assertEqual(vr.problem_day("[springx 11] boom", known), "springx 11")
        self.assertEqual(vr.problem_day("全局问题不带前缀", known), "")
        self.assertNotIn(vr.problem_day("[spring] 11] boom", known), known)
        self.assertNotIn(vr.problem_day("[summer 99] boom", known), known)

    # ------------------------------------------------------------ task-134：assigned_undone 口径
    def test_assigned_done_with_plot_pending_is_not_unmet(self):
        """分配内做净、片区还剩（run9b 的假红形态）⇒ 新口径不许判 mismatch、只记信息。

        run9b 真账本样例行：`{'stage':'till_area','tiles':12,'ok':12,'leftover':12,
        'assigned':12,'assigned_undone':0}` —— 旧 leftover 口径会算出 effective_leftover=12
        而账本写 `no_unmet_stages=true`，于是报"自述与自算不一致"。
        """
        rows = green_rows()
        for r in rows:
            if r.get("event") == "day_end":
                r["stages"] = [stage("till_area", tiles=12, ok=12, leftover=12,
                                     assigned=12, assigned_undone=0)]
        ok, s = self.check(rows)
        self.assertTrue(ok, s.get("problems"))
        self.assertEqual(s["problems"], [])
        self.assertTrue(any("plot_pending" in i for i in s["infos"]), s["infos"])

    def test_assigned_undone_positive_matches_no_unmet_false(self):
        """分配内真没做完（非诚实上限）+ 账本如实写 false ⇒ 不报 mismatch（但 false 本身仍是问题）。"""
        rows = green_rows()
        for r in rows:
            if r.get("event") == "day_end":
                r["stages"] = [stage("till_area", tiles=12, ok=9, leftover=15, stopped="no_target",
                                     assigned=12, assigned_undone=3)]
                r["checks"]["no_unmet_stages"] = False
                r["verified"] = False
        ok, s = self.check(rows, days=0)
        self.assertFalse(any("与自算不一致" in p for p in s["problems"]), s["problems"])
        self.assertTrue(any("no_unmet_stages=false" in p for p in s["problems"]), s["problems"])

    def test_assigned_undone_lying_true_is_still_caught(self):
        """账本谎报 true 而分配内还有 3 格没做完（非诚实上限）⇒ mismatch 必须被抓住。"""
        rows = green_rows()
        for r in rows:
            if r.get("event") == "day_end":
                r["stages"] = [stage("till_area", tiles=12, ok=9, leftover=15, stopped="no_target",
                                     assigned=12, assigned_undone=3)]
        ok, s = self.check(rows, days=0)
        self.assertTrue(any("assigned_undone=3" in p and "与自算不一致" in p for p in s["problems"]),
                        s["problems"])

    def test_honest_limit_stage_is_not_an_unmet_mismatch(self):
        """deputy task-135 F1 的假红形态：体力/夜里收尾的诚实上限阶段**不许**报 mismatch。

        旧写法把 honest 阶段的 `assigned_undone` 也加进基数 ⇒ 同一份输出上既说"与自算不一致"
        又说"其中诚实上限延后 N 格"，自相矛盾。
        """
        rows = green_rows()
        for r in rows:
            if r.get("event") == "day_end":
                r["ended_reason"] = "stamina:体力 4 < 12"
                r["stages"] = [stage("till_area", tiles=12, ok=11, skipped=0, leftover=9,
                                     stopped="stamina", assigned=12, assigned_undone=1)]
                r["deferred_tiles"] = 9
        ok, s = self.check(rows)
        self.assertTrue(ok, s.get("problems"))
        self.assertFalse(any("与自算不一致" in p for p in s["problems"]), s["problems"])
        self.assertTrue(any("诚实上限延后 9 格" in i for i in s["infos"]), s["infos"])

    def test_forged_assigned_undone_is_caught_by_journal(self):
        """deputy task-135 F2：`assigned_undone` 是纯自述 ⇒ 账本少报必须被 journal 落痕抓住。"""
        # journal 里留着"阶段自报少做 5 格"的落痕（与账本的 0 打架）；插在第一天会话内。
        rows = green_rows()
        for r in rows:
            if r.get("event") == "day_end":
                r["stages"] = [stage("till_area", tiles=12, ok=12, leftover=0, stopped="no_target",
                                     assigned=12, assigned_undone=0)]
        rows.insert(1, {"event": "stage_shortfall_day", "unmet": 5, "stages": [], "t": 150.0,
                        "plot_pending": 5, "stopped_night": False})
        ok, s = self.check(rows, days=0)
        self.assertTrue(
            any("stage_shortfall_day.unmet=5" in p and "assigned_undone=0" in p for p in s["problems"]),
            s["problems"],
        )

    def test_deferred_tiles_is_reported_as_info(self):
        """诚实上限延后的片区待办：`deferred_tiles` 只作信息，不许变成 unmet。"""
        rows = green_rows()
        for r in rows:
            if r.get("event") == "day_end":
                r["stages"] = [stage("till_area", tiles=12, ok=11, skipped=1, leftover=11,
                                     assigned=12, assigned_undone=0)]
                r["deferred_tiles"] = 11
        ok, s = self.check(rows)
        self.assertTrue(ok, s.get("problems"))
        self.assertTrue(any("诚实上限延后 11 格" in i for i in s["infos"]), s["infos"])

    def test_legacy_ledger_without_assigned_still_uses_leftover(self):
        """无 `assigned_undone` 的旧账本 ⇒ 退回 leftover 口径（历史判决不许翻案）。"""
        rows = green_rows()
        for r in rows:
            if r.get("event") == "day_end":
                r["stages"] = [stage("till_area", tiles=12, ok=12, leftover=12)]
        ok, s = self.check(rows, days=0)
        self.assertTrue(any("与自算不一致" in p and "leftover=12" in p for p in s["problems"]),
                        s["problems"])

    # ------------------------------------------- task-168 规模取舍（`scope_shed`）口径
    def _shed_rows(self, *, tiles=6, zone="field_ne", write_field=True, verified=False):
        """造一个「当天认输了 N 格」的账本：journal 有 `scope_shed` 事件，账本按需写字段。"""
        rows = green_rows(days=1)
        rows.insert(1, {"event": "scope_shed", "t": 50.0, "zone": zone, "tiles": tiles,
                        "live_crops": 40, "reason": "水预算不够：今天浇不完 40 株活苗",
                        "note": "本区认输，明天再补", "_lineno": 1})
        end = next(r for r in rows if r.get("event") == "day_end")
        end["verified"] = verified
        if write_field:
            end["scope_shed_tiles"] = tiles
            end["scope_shed"] = {zone: {"tiles": tiles, "since_day": [1, "spring", 10]}}
        return rows

    def test_scope_shed_without_ledger_field_is_caught(self):
        """journal 里认输过而账本没写 `scope_shed_tiles` ⇒ 账目不可信（缺失≠通过）。"""
        rows = self._shed_rows(write_field=False)
        ok, s = self.check(rows, days=0)
        self.assertTrue(
            any("scope_shed" in p and "账本没写 scope_shed_tiles" in p for p in s["problems"]),
            s["problems"],
        )

    def test_scope_shed_while_verified_is_a_contradiction(self):
        """认输过却自称 VERIFIED ⇒ 自相矛盾（认输格仍留在会计里、当天如实不 VERIFIED）。"""
        rows = self._shed_rows(verified=True)
        ok, s = self.check(rows, days=0)
        self.assertTrue(any("认输 6 格却自称 VERIFIED" in p for p in s["problems"]), s["problems"])

    def test_scope_shed_self_consistent_day_is_info_only(self):
        """如实认输（账本有字段、journal 对得上、当天 verified=false）⇒ 只作 info、不加问题。"""
        rows = self._shed_rows(verified=False)
        ok, s = self.check(rows, days=0)
        self.assertFalse(any("scope_shed" in p for p in s["problems"]), s["problems"])
        self.assertTrue(any("规模取舍：主动认输 6 格" in i for i in s["infos"]), s["infos"])

    def test_legacy_ledger_without_scope_shed_is_not_flagged(self):
        """task-168 之前的旧账本（既无事件也无字段）⇒ 不表态，历史判决不许翻案。"""
        ok, s = self.check(green_rows())
        self.assertTrue(ok, s.get("problems"))
        self.assertFalse(any("规模取舍" in i for i in s["infos"]), s["infos"])
        self.assertFalse(any("scope_shed" in p for p in s["problems"]), s["problems"])


    def _shed_released_rows(self, *, tiles=6, released=6, zone="field_ne",
                            ledger_tiles=None, verified=True):
        """认输后又释放：journal 有 `scope_shed` + `scope_released`；账本写**末态**净格数。"""
        rows = self._shed_rows(tiles=tiles, zone=zone, write_field=False, verified=verified)
        rows.insert(2, {"event": "scope_released", "t": 60.0, "zone": zone,
                        "reason": "下雨把该区浇好了", "tiles": released, "_lineno": 1})
        end = next(r for r in rows if r.get("event") == "day_end")
        net = tiles if ledger_tiles is None else ledger_tiles
        end["scope_shed_tiles"] = net
        if net:
            end["scope_shed"] = {zone: {"tiles": net, "since_day": [1, "spring", 10]}}
        return rows

    def test_shed_then_released_same_day_is_not_flagged(self):
        """认输 6 格后当天又释放 6 格（末态 0）且自称 VERIFIED ⇒ 不算矛盾（NIT-1 回归）。"""
        rows = self._shed_released_rows(tiles=6, released=6, ledger_tiles=0, verified=True)
        ok, s = self.check(rows, days=0)
        self.assertFalse(any("scope_shed" in p for p in s["problems"]), s["problems"])

    def test_partial_release_is_checked_against_net(self):
        """部分释放：账本必须写净格数（6−2=4）；写成毛格数 6 ⇒ 账目不可信。"""
        good = self._shed_released_rows(tiles=6, released=2, ledger_tiles=4, verified=False)
        ok, s = self.check(good, days=0)
        self.assertFalse(any("scope_shed" in p for p in s["problems"]), s["problems"])
        bad = self._shed_released_rows(tiles=6, released=2, ledger_tiles=6, verified=False)
        ok, s = self.check(bad, days=0)
        self.assertTrue(
            any("scope_shed" in p and "自算净 4 格" in p for p in s["problems"]), s["problems"]
        )


if __name__ == "__main__":
    unittest.main()
