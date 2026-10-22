# -*- coding: utf-8 -*-
"""T16: diff the exact set of test IDs between frozen-tree archive and worktree."""
from __future__ import annotations
import os, re, subprocess
from pathlib import Path

REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
PY = (r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime"
      r"\dependencies\python\python.exe")
ARCH = Path(r"C:\Users\admin\AppData\Local\Temp\opencode\t16tree")
IDRE = re.compile(r"^(\S+ \([^)]+\)) \.\.\. ")


def ids(cwd: Path, pypath: Path, args: list[str]):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(pypath)
    p = subprocess.run([PY, "-m", "unittest", "-v", *args], cwd=str(cwd),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr or "")
    return {m.group(1) for m in (IDRE.match(l) for l in out.splitlines()) if m}, out


a, oa = ids(ARCH / "tests", ARCH / "brain", ["test_analyze_longrun"])
w, ow = ids(REPO / "tests", REPO / "brain", ["test_analyze_longrun"])
print(f"archive ids={len(a)}  worktree ids={len(w)}")
only_a = sorted(a - w)
only_w = sorted(w - a)
print(f"\nonly-in-archive ({len(only_a)}):")
for x in only_a:
    print("  " + x)
print(f"\nonly-in-worktree ({len(only_w)}):")
for x in only_w:
    print("  " + x)
(REPO / "scratch" / "_t16_id_diff.txt").write_text(
    "\n".join([f"archive={len(a)} worktree={len(w)}"] + ["A: " + x for x in only_a]
              + ["W: " + x for x in only_w]), encoding="utf-8")
