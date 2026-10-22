# -*- coding: utf-8 -*-
r"""T16: 全量测试 ID 差集 —— `git archive <ref>` 冻结树 vs 工作树。

目的：解释「冻结树 Ran N ≠ 工作树 Ran 1410」的 14 条差额到底缺在哪、为什么缺
（判据：缺失原因必须是 **gitignored 夹具缺失**，而不是产品代码差异）。

用法：$env:PYTHONUTF8='1'; & <DSH python> scratch\_t16_ids_full.py [ref]
输出：archive/worktree 各自收集到的测试 ID 数、only-in-worktree / only-in-archive 清单。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
PY = (r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime"
      r"\dependencies\python\python.exe")
REF = sys.argv[1] if len(sys.argv) > 1 else "daceb48"
DEST = Path(tempfile.gettempdir()) / f"t16ids_{REF}"
IDRE = re.compile(r"^(\S+ \([^)]+\)) \.\.\. ")


def ids(cwd: Path):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(cwd / "brain")
    p = subprocess.run(
        [PY, "-m", "unittest", "discover", "-v", "-s", "tests", "-p", "test_*.py"],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr or "")
    got = {m.group(1) for m in (IDRE.match(l) for l in out.splitlines()) if m}
    tail = [l for l in out.splitlines() if l.startswith("Ran ") or l.startswith("OK")
            or l.startswith("FAILED")]
    return got, tail


def main() -> int:
    if DEST.exists():
        shutil.rmtree(DEST, ignore_errors=True)
    DEST.mkdir(parents=True)
    subprocess.run(["git", "archive", "--format=tar", "-o", str(DEST / "a.tar"), REF],
                   cwd=str(REPO), check=True)
    subprocess.run(["tar", "-xf", str(DEST / "a.tar")], cwd=str(DEST), check=True)
    (DEST / "a.tar").unlink()
    arch, at = ids(DEST)
    print(f"[archive {REF}] 收集到测试 ID = {len(arch)}  tail={at}")
    work, wt = ids(REPO)
    print(f"[worktree HEAD] 收集到测试 ID = {len(work)}  tail={wt}")
    only_w = sorted(work - arch)
    only_a = sorted(arch - work)
    print(f"\nonly-in-worktree ({len(only_w)}):")
    for x in only_w:
        print("  +", x)
    print(f"\nonly-in-archive ({len(only_a)}):")
    for x in only_a:
        print("  -", x)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
