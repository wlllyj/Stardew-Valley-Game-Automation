# -*- coding: utf-8 -*-
"""跑 run7 的两侧检查器并把 UTF-8 输出落盘（pwsh 的 `*>` 会写成 UTF-16，别用）。

用法：python scratch\\run7-tools.py [--journal logs\\longrun-3day-llm-run7.jsonl]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PY = sys.executable

ap = argparse.ArgumentParser()
ap.add_argument("--journal", default=os.path.join("logs", "longrun-3day-llm-run7.jsonl"))
args = ap.parse_args()
journal = args.journal if os.path.isabs(args.journal) else os.path.join(REPO, args.journal)

env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

for tool, out in (("tools\\verify-run3.py", "logs\\run7-verify.txt"),
                  ("tools\\analyze-longrun.py", "logs\\run7-analyze.txt")):
    cmd = [PY, os.path.join(REPO, tool), "--journal", journal]
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    outp = os.path.join(REPO, out)
    with open(outp, "w", encoding="utf-8") as fh:
        fh.write(f"$ {' '.join(cmd)}\n")
        fh.write(f"=== rc={p.returncode} ===\n")
        fh.write("--- stdout ---\n" + (p.stdout or ""))
        fh.write("--- stderr ---\n" + (p.stderr or ""))
    lines = (p.stdout or "").splitlines()
    print(f"### {tool}  rc={p.returncode}  stdout={len(lines)} 行  stderr={len((p.stderr or '').splitlines())} 行  -> {out}")
    n = 80 if "verify" in tool else 60
    print("\n".join(lines[-n:]))
    if p.stderr:
        print("[stderr tail]")
        print("\n".join((p.stderr or "").splitlines()[-15:]))
    print()
