"""task-90：非空转证明 —— 把 `tests/test_verify_run3.py` 的两条新用例放到三副本上跑。

做法：测试模块把工具模块绑在全局 `vr` 上（`tests/test_verify_run3.py:18-21`），
所以这里把 `vr` 换成冻结副本，再跑那两条用例：
  - `test_bracket_in_day_label_cannot_hide_an_in_window_problem`
  - `test_unknown_problem_day_label_is_never_demoted`
预期：old/fixed ⇒ PASS；buggy(7c4ff68) ⇒ 第一条 FAIL（洞在，用例确实会红）。

用法：python scratch/_t90_nonvacuous.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tests.test_verify_run3 as T  # noqa: E402

CASES = [
    "test_bracket_in_day_label_cannot_hide_an_in_window_problem",
    "test_unknown_problem_day_label_is_never_demoted",
]
COPIES = [
    ("old(7c4ff68^)", "_t90_tool_old.py"),
    ("buggy(7c4ff68)", "_t90_tool_buggy.py"),
    ("fixed(c6d2a7a)", "_t90_tool_fixed.py"),
]


def load(path: str):
    spec = importlib.util.spec_from_file_location("vr3_" + os.path.basename(path), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def main() -> int:
    original = T.vr
    failures = 0
    for tag, name in COPIES:
        T.vr = load(os.path.join(ROOT, "scratch", name))
        for case in CASES:
            res = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w")).run(
                unittest.TestSuite([T.TestVerifyRun3(case)]))
            ok = res.wasSuccessful()
            failures += 0 if ok else 1
            detail = ""
            if not ok:
                first = (res.failures + res.errors)[0][1].strip().splitlines()
                detail = " | " + (first[-1] if first else "")[:150]
            print(f"{tag:<18}{case:<62}{'PASS' if ok else 'FAIL'}{detail}")
        print("")
    T.vr = original
    print(f"合计非通过项：{failures}（预期：buggy 的 bracket 那条 = 1）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
