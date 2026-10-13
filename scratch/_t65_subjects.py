"""task-65 取证：列出各账本里"疑似红"的 subject，用来定"有红"的口径（只读）。"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "analyze_longrun", os.path.join(ROOT, "tools", "analyze-longrun.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

LEDGERS = [
    r"scratch\journal-green.jsonl",
    r"logs\longrun-3day-llm-run2.jsonl",
    r"logs\longrun-3day-llm-run3.jsonl",
    r"logs\longrun-3day-llm-run5.jsonl",
    r"scratch\_t5x_vacuum.jsonl",
]

for rel in LEDGERS:
    path = os.path.join(ROOT, rel)
    rows, bad = mod.load_journal(path)
    args = mod.parse_args(["--journal", path])
    rep = mod.build_report(rows, path, args, bad)
    print("=" * 70)
    print(rel, "| manual_total=", rep["manual_intervention"]["total"])
    for key in ("manual", "missed", "wasted"):
        subs = {}
        for f in rep["categories"][key]:
            subs.setdefault(f["subject"], 0)
            subs[f["subject"]] += 1
        print(f"  {key} total={rep['categories_total'][key]}: {subs}")
