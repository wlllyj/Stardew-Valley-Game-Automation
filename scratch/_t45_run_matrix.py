# -*- coding: utf-8 -*-
"""跑 task-45 夹具矩阵：对每个夹具调 `_t45_three_source.py`，比对期望退出码并打印判红原文。

用法：& $py scratch/_t45_run_matrix.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "scratch" / "_t45_fx"
TOOL = ROOT / "scratch" / "_t45_three_source.py"
PY = sys.executable
SAVE_NAME = "Wahaha_450799035"

CASES = [
    ("ok", 0),
    ("pos-E-save-one-day-behind", 0),
    ("pos-G-one-day-no-save", 0),
    ("pos-I-midrun-last-day-open", 0),
    ("neg-A-ledger-cut", 1),
    ("neg-B-smapi-short", 1),
    ("neg-C-no-save", 1),
    ("neg-D-save-behind", 1),
    ("neg-F-two-days-no-save", 1),
    ("neg-H-cross-day-without-sleep-event", 1),
]


def main() -> int:
    bad = 0
    for name, expect in CASES:
        d = FX / name
        cmd = [PY, str(TOOL),
               "--ledger", str(d / "ledger.jsonl"),
               "--smapi", str(d / "smapi.txt"),
               "--save-dir", str(d / "Saves" / SAVE_NAME),
               "--snapshots", str(d / "snapshots.jsonl"),
               "--baseline", str(d / "baseline.json"),
               "--date", "2026-10-13"]
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        verdict = "OK" if r.returncode == expect else "MISMATCH"
        if verdict != "OK":
            bad += 1
        problems = [ln.strip() for ln in (r.stdout or "").splitlines() if "[PROBLEM]" in ln]
        infos = [ln.strip() for ln in (r.stdout or "").splitlines() if "[info]" in ln]
        print(f"=== {name}: exit={r.returncode} 期望={expect} {verdict}（problem {len(problems)} / info {len(infos)}）")
        for ln in problems:
            print("    " + ln)
        if name.startswith("pos") and infos:
            for ln in infos:
                print("    " + ln)
    print(f"\n矩阵结论：{'全部符合期望' if bad == 0 else f'{bad} 个不符期望'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
