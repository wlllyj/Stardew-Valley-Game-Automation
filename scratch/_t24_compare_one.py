# -*- coding: utf-8 -*-
"""task-24：单本账本 HEAD~1（0.7.45 前 analyzer）vs 新版 analyzer 的 rc/红/#无法判定 对照。"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ANALYZE = REPO / "tools" / "analyze-longrun.py"
LEDGER = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "logs" / "longrun-smoke-0745.jsonl"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def snap(mod, path):
    rows, bad = mod.load_journal(str(path))
    args = mod.parse_args(["--journal", str(path), "--days", "3"])
    rep = mod.build_report(rows, str(path), args, bad)
    return {"rc": 1 if rep["red"]["total"] else 0,
            "red": rep["red"]["total"],
            "subjects": rep["red"]["subjects"],
            "undec": len(rep["undecidable"])}


old_src = subprocess.run(["git", "cat-file", "-p", "HEAD~1:tools/analyze-longrun.py"],
                         cwd=str(REPO), capture_output=True, check=True).stdout
tmp = Path(tempfile.mkdtemp(prefix="t24_old_"))
old_p = tmp / "_old_analyze.py"
old_p.write_bytes(old_src)
old = load(old_p, "t24_old")
new = load(ANALYZE, "t24_new")
a, b = snap(old, LEDGER), snap(new, LEDGER)
print("ledger:", LEDGER)
print("HEAD~1:", a["rc"], a["red"], a["undec"])
print("NEW   :", b["rc"], b["red"], b["undec"])
print("delta red:", b["red"] - a["red"], "delta undec:", b["undec"] - a["undec"])
print("red subjects same:", a["subjects"] == b["subjects"])
print("HEAD~1 subjects:", a["subjects"])
print("NEW    subjects:", b["subjects"])
