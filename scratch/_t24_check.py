# -*- coding: utf-8 -*-
"""task-24 回归核对：六旧账本 + A8 + smoke-0744 + smoke-0745 的 rc/红数/#无法判定 与基线提交对照。

基线默认 `80488c8~1`（task-24 第一个实现提交的父，即未收 0.7.45 字段的 analyzer）。
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ANALYZE = REPO / "tools" / "analyze-longrun.py"
LEDGERS = [
    ("runA", "logs/longrun-runA-0732.jsonl"),
    ("runB", "logs/longrun-runB-0732.jsonl"),
    ("run9", "logs/longrun-3day-llm-run9.jsonl"),
    ("run9b", "logs/longrun-3day-llm-run9b.jsonl"),
    ("run9c", "logs/longrun-3day-llm-run9c.jsonl"),
    ("run9d", "logs/longrun-3day-llm-run9d.jsonl"),
    ("A8", "logs/longrun-runA8-0743.jsonl"),
    ("smoke0744", "logs/longrun-smoke-0744.jsonl"),
    ("smoke0745", "logs/longrun-smoke-0745.jsonl"),
]
BASE_REF = sys.argv[1] if len(sys.argv) > 1 else "80488c8~1"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_rows(path):
    rows, bad = [], 0
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append((i, json.loads(line)))
        except Exception:
            bad += 1
    return rows, bad


def snapshot(mod, path):
    rows, bad = read_rows(path)
    rep = mod.build_report(rows, str(path), mod.parse_args(["--journal", str(path)]), bad)
    red = rep.get("red") or {}
    total = int(red.get("total") or 0)
    return {
        "rc": 1 if total > 0 else 0,
        "red": total,
        "settled": red.get("settled_total"),
        "undec": len(rep.get("undecidable") or []),
    }


def main():
    head_src = subprocess.run(
        ["git", "cat-file", "-p", f"{BASE_REF}:tools/analyze-longrun.py"],
        cwd=str(REPO), capture_output=True, check=True,
    ).stdout
    tmpdir = Path(tempfile.mkdtemp(prefix="t24_head_"))
    head_path = tmpdir / "_head_analyze.py"
    head_path.write_bytes(head_src)
    old = load_module(head_path, "t24_head_analyze")
    new = load_module(ANALYZE, "t24_new_analyze")
    print(f"{'ledger':<10} {'HEAD rc/red/undec':<22} {'NEW rc/red/undec':<22} {'delta_red':>9} {'delta_undec':>11}")
    for name, rel in LEDGERS:
        p = REPO / rel
        if not p.exists():
            print(f"{name:<10} <缺失> {rel}")
            continue
        a = snapshot(old, p)
        b = snapshot(new, p)
        print(f"{name:<10} {a['rc']}/{a['red']}/{a['undec']:<12} {b['rc']}/{b['red']}/{b['undec']:<12} "
              f"{b['red'] - a['red']:+9d} {b['undec'] - a['undec']:+11d}")
    print("done")


if __name__ == "__main__":
    main()
