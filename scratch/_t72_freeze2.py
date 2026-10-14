# -*- coding: utf-8 -*-
"""task-72 取证（第二步）：把 task-71 的提交 `9f554d7` 版本冻结，并给出闸门行号。

用法：python scratch\\_t72_freeze2.py
只读 git/工作树，只写 scratch\\_t72_tool_fix.py 与 scratch\\_t72_tests_tool.py。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys

REV = "9f554d7"
MARKERS = [
    "上界被放宽",
    "抬高分母",
    "却没写任何坐标",
    "同一格同时进两套豁免",
    "只按账本" ,
    "自算上界",
]


def show(rev: str, path: str) -> bytes:
    p = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True)
    if p.returncode != 0:
        return b""
    return p.stdout


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True).stdout.decode().strip()
    st = subprocess.run(["git", "status", "--short"], capture_output=True).stdout.decode("utf-8", "replace")
    print(f"HEAD={head}  git status --short:\n{st or '  （干净）'}")

    tool = show(REV, "tools/verify-run3.py")
    tests = show(REV, "tests/test_verify_run3.py")
    with open("scratch/_t72_tool_fix.py", "wb") as fh:
        fh.write(tool)
    with open("scratch/_t72_tests_tool.py", "wb") as fh:
        fh.write(tests)
    wip = open("scratch/_t72_tool_wip.py", "rb").read()
    print(f"\n{REV}:tools/verify-run3.py   {len(tool):6d} B  {len(tool.splitlines()):4d} 行  sha256={sha(tool)}")
    print(f"我先前冻结的在制副本        {len(wip):6d} B  {len(wip.splitlines()):4d} 行  sha256={sha(wip)}")
    print("⇒ " + ("与提交版逐字节相同" if sha(tool) == sha(wip) else "与提交版不同（Lead 之后又改过）"))
    print(f"{REV}:tests/test_verify_run3.py  {len(tests):6d} B  {len(tests.splitlines()):4d} 行  sha256={sha(tests)}")

    text = tool.decode("utf-8", "replace")
    lines = text.splitlines()
    print("\n闸门定位（行号 : 原文前 96 字）：")
    for i, ln in enumerate(lines, 1):
        if any(m in ln for m in MARKERS):
            print(f"  {i:4d} : {ln.strip()[:96]}")

    ttext = tests.decode("utf-8", "replace").splitlines()
    print("\ntests/test_verify_run3.py 里与豁免相关的用例：")
    for i, ln in enumerate(ttext, 1):
        s = ln.strip()
        if s.startswith("def test") and any(k in s for k in ("bound", "coord", "overlap", "exempt", "inflate", "gap")):
            print(f"  {i:4d} : {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
