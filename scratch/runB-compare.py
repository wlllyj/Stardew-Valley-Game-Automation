# -*- coding: utf-8 -*-
"""跑 tools\\compare-runs.py（run A vs run B）并把 UTF-8 输出落盘（避免 pwsh 重定向写成 UTF-16）。"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "logs", "runB-0732-compare.txt")

cmd = [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "compare-runs.py"),
       "--run-a", os.path.join(ROOT, "logs", "longrun-runA-0732.jsonl"),
       "--run-b", os.path.join(ROOT, "logs", "longrun-runB-0732.jsonl"),
       "--label-a", "runA-0732", "--label-b", "runB-0732"]
r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(r.stdout or "")
    if r.stderr:
        fh.write("\n--- stderr ---\n" + r.stderr)
print((r.stdout or "").strip())
print(f"\n[rc={r.returncode}] 已落 {OUT}")
if r.stderr and r.stderr.strip():
    print("stderr:", r.stderr.strip()[:500])
sys.exit(0)
