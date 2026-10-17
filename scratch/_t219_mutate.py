# -*- coding: utf-8 -*-
"""task-219 变异自检（作者自证：新用例真的能抓回退）。

做法：把 `brain/` + `tests/` 拷到临时目录，逐条把**生产代码**改坏，跑定向用例，
数 `FAIL:`/`ERROR:` 行。基线必须 0 红。任何一条变异"杀 0"都说明用例没咬住。

用法：`python scratch/_t219_mutate.py`
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET_TESTS = [
    "tests.test_longrun.TestTask219IntentCoverage",
    "tests.test_planner.Task219GapsGuard",
]

#: (名字, 文件, 原文, 替换)
MUTATIONS: list[tuple[str, str, str, str]] = [
    ("m219a_no_plans", "brain/agentfarm/longrun.py",
     "            plans = self._plan_intents(decision)",
     "            plans = []"),
    ("m219b_no_coverage_fill", "brain/agentfarm/longrun.py",
     "        seen = {str(r.get(\"intent_id\") or \"\") for r in self.intent_coverage}",
     "        return  # 变异：日终不补记没进执行的意图\n        seen = set()"),
    ("m219c_cancel_as_gated", "brain/agentfarm/longrun.py",
     "                reason = \"no_target\" if verdict == \"cancel\" else \"unknown_evidence\"",
     "                reason = \"gated\""),
    ("m219d_no_gaps_flush", "brain/agentfarm/longrun.py",
     "        self._gaps_flush(rep)",
     "        pass  # 变异：缺口清单不落盘"),
    ("m219e_gaps_uncapped", "brain/agentfarm/longrun.py",
     "        for it in items[:GAPS_INJECT_MAX]:",
     "        for it in items[:GAPS_INJECT_MAX + 3]:"),
    ("m219f_reason_outside_set", "brain/agentfarm/longrun.py",
     "            return \"unknown_evidence\"\n        if steps and all(getattr(s, \"skipped\", False) for s in steps):",
     "            return \"mystery_reason\"\n        if steps and all(getattr(s, \"skipped\", False) for s in steps):"),
]


def _run_tests(cwd: Path) -> str:
    env = {"PYTHONUTF8": "1", "PYTHONPATH": str(cwd / "brain"), "PATH": ""}
    env["PATH"] = str(Path(sys.executable).parent) + ";" + __import__("os").environ.get("PATH", "")
    proc = subprocess.run([sys.executable, "-m", "unittest", *TARGET_TESTS],
                          cwd=cwd, env=env, capture_output=True, text=True)
    return proc.stdout + proc.stderr


def _count_red(out: str) -> int:
    return sum(1 for line in out.splitlines()
               if line.startswith("FAIL:") or line.startswith("ERROR:"))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "mut"
        shutil.copytree(REPO / "brain", work / "brain")
        shutil.copytree(REPO / "tests", work / "tests")
        base = _run_tests(work)
        red = _count_red(base)
        print(f"baseline: red={red}")
        if red:
            print(base[-3000:])
            return 1
        rc = 0
        for name, rel, old, new in MUTATIONS:
            target = work / rel
            original = target.read_text(encoding="utf-8")
            if old not in original:
                print(f"{name}: ANCHOR-NOT-FOUND（变异没打上 ⇒ 读数无效）")
                rc = 1
                continue
            target.write_text(original.replace(old, new, 1), encoding="utf-8")
            out = _run_tests(work)
            kills = _count_red(out)
            print(f"{name}: kills={kills}")
            if kills == 0:
                print("  ⚠️ 杀 0 ⇒ 用例没咬住这条回退")
                rc = 1
            target.write_text(original, encoding="utf-8")
        return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
