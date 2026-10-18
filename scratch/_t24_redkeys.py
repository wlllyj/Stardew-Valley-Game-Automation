# -*- coding: utf-8 -*-
"""看 report['red'] 结构与 rc 口径。"""
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("an", str(REPO / "tools" / "analyze-longrun.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
rows, bad = [], 0
for i, line in enumerate((REPO / "logs/longrun-runA-0732.jsonl").read_text(encoding="utf-8").splitlines(), 1):
    if line.strip():
        rows.append((i, json.loads(line)))
rep = mod.build_report(rows, "x", mod.parse_args(["--journal", "x"]), bad)
print("report keys:", sorted(rep.keys()))
print("rc:", rep.get("rc"))
red = rep["red"]
print("red keys:", sorted(red.keys()))
for k, v in red.items():
    if isinstance(v, list):
        print(k, "list len", len(v))
    else:
        print(k, "=", v)
print("advice n:", len(rep.get("advice") or []))
