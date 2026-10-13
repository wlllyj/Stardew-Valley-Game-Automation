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

    def test_single_day_green_is_not_enough_for_three(self):
        ok, s = self.check(green_rows(days=1), days=3)
        self.assertFalse(ok)
        self.assertEqual(s["verified_streak_tail"], 1)


if __name__ == "__main__":
    unittest.main()
