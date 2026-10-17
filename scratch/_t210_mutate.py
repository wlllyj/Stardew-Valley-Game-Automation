# -*- coding: utf-8 -*-
"""task-210 变异自检：机器链三件套的用例真的能抓住回退吗（作者自证）。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = "tests.test_farmwork.TestTask210MachineChain"

MUTATIONS: list[tuple[str, str, str, str]] = [
    ("m210a_craft_always_ok", "brain/agentfarm/farmwork.py",
     "        if qid and self._count_in_map(gained, qid) > 0:",
     "        if True:"),
    ("m210b_place_trusts_receipt", "brain/agentfarm/farmwork.py",
     "        if placed and consumed:",
     "        if True:"),
    ("m210c_machine_ignores_held_object", "brain/agentfarm/farmwork.py",
     "        if held_changed:",
     "        if False and held_changed:"),
    ("m210d_collect_skips_ready_gate", "brain/agentfarm/farmwork.py",
     "        if act == \"collect\" and ready_before is not True:",
     "        if False:"),
    ("m210e_place_skips_occupied_gate", "brain/agentfarm/farmwork.py",
     "        if tv_before.get(\"objId\") or tv_before.get(\"kind\") in (\"object\",):",
     "        if False:"),
]


def _run_tests(cwd: Path) -> str:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(cwd / "brain")
    proc = subprocess.run([sys.executable, "-m", "unittest", TARGET],
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
                print(f"{name}: ANCHOR-NOT-FOUND")
                rc = 1
                continue
            target.write_text(original.replace(old, new, 1), encoding="utf-8")
            kills = _count_red(_run_tests(work))
            print(f"{name}: kills={kills}")
            if kills == 0:
                print("  ⚠️ 杀 0 ⇒ 用例没咬住这条回退")
                rc = 1
            target.write_text(original, encoding="utf-8")
        return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
