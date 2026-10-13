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

    def test_failed_underreport_is_problem(self):
        """洗账：stage 侧 2 格失败，日级 failed_steps=0，且无环境/无结论可解释。"""
        rows = tweak(green_rows(), "day_end", ok_steps=5, failed_steps=0,
                     stages=[stage("clear_area", tiles=5, ok=5, failed=2)])
        ok, s = self.check(rows)
        self.assertFalse(ok)
        self.assertTrue(any("账目不可信" in p for p in s["problems"]), s["problems"])

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


if __name__ == "__main__":
    unittest.main()
