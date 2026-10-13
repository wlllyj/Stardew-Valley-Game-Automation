"""变异自检（run3「睡醒在屋里」修复）：单独关掉 A 或 B，TestMorningIndoor 必须红。

用法（仓库根目录）：$env:PYTHONUTF8=1; python scratch\\_t32b_mutate.py

  A = `LongRun._ensure_on_farm`（当天开工前回户外农场）
  B = `LongRun._farm_scope_work`（人在室内时用 farm 口径补"还有活"）
"""
from __future__ import annotations

import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "brain"))

from agentfarm.longrun import LongRun                       # noqa: E402
from tests.test_longrun import TestMorningIndoor            # noqa: E402

ORIG_ENSURE = LongRun._ensure_on_farm
ORIG_SCOPE = LongRun._farm_scope_work


def off_A(self, obs, rep):
    return obs                                              # 关掉"先回农场"


def off_B(self, obs):
    return None                                             # 关掉 farm 口径的"还有活"


def run_class() -> tuple[unittest.TestResult, str]:
    buf = io.StringIO()
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMorningIndoor)
    res = unittest.TextTestRunner(stream=buf, verbosity=2).run(suite)
    return res, buf.getvalue()


def show(tag: str, res: unittest.TestResult) -> None:
    bad = [t.id().split(".")[-1] for t, _ in list(res.failures) + list(res.errors)]
    print(f"[{tag}] 跑 {res.testsRun} 条：失败/错误 = {bad or '（无）'}"
          f" ⇒ {'红' if bad else '绿'}")
    for t, tb in list(res.failures) + list(res.errors):
        lines = [ln for ln in tb.strip().splitlines() if ln.strip()]
        print(f"    · {t.id().split('.')[-1]}：{lines[-1][:300]}")
        for ln in lines:
            if ln.strip().startswith(("AssertionError", "Assertion")):
                print(f"      {ln.strip()[:300]}")


def main() -> int:
    print("=" * 72)
    res, _ = run_class()
    show("基线（A、B 都开）", res)

    LongRun._ensure_on_farm = off_A
    try:
        res, _ = run_class()
        show("变异 A：只关 _ensure_on_farm", res)
    finally:
        LongRun._ensure_on_farm = ORIG_ENSURE

    LongRun._farm_scope_work = off_B
    try:
        res, _ = run_class()
        show("变异 B：只关 _farm_scope_work", res)
    finally:
        LongRun._farm_scope_work = ORIG_SCOPE
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
