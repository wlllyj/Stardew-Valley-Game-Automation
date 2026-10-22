# -*- coding: utf-8 -*-
"""T16: dump unittest output (archive tree vs worktree) to files for exact FAIL/ERROR text."""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
PY = (r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime"
      r"\dependencies\python\python.exe")
ARCH = Path(r"C:\Users\admin\AppData\Local\Temp\opencode\t16tree")


def run(cwd: Path, pypath: Path, args: list[str]) -> str:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(pypath)
    p = subprocess.run([PY, "-m", "unittest", *args], cwd=str(cwd),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    return (p.stdout or "") + (p.stderr or "")


# 1) archive tree: only test_analyze_longrun, verbose
out1 = run(ARCH / "tests", ARCH / "brain", ["-v", "test_analyze_longrun"])
(REPO / "scratch" / "_t16_analyze_archive.txt").write_text(out1, encoding="utf-8")

# 2) worktree: full discover
out2 = run(REPO / "tests", REPO / "brain", ["discover", "-p", "test_*.py"])
(REPO / "scratch" / "_t16_full_worktree.txt").write_text(out2, encoding="utf-8")

import re
for name, out in (("archive/test_analyze_longrun", out1), ("worktree/full", out2)):
    m = re.search(r"Ran (\d+) tests?", out)
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    print(f"[{name}] Ran={m.group(1) if m else '?'} tail={tail!r}")
