# -*- coding: utf-8 -*-
"""task-214 复跑（0.7.38）：四步内省取证，逐步落盘，第 1 步失败就**绝不**执行写档动作。

顺序（与卡面一致）：
  1. debug_dump table=crafting_recipes key=Furnace   ← 白名单验活：不许再出现 unknown_skill
  2. debug_dump table=trigger_actions               ← 触发器原文
  3. add_missed_recipes  （**只调一次**，禁止循环）  ← 写玩家字典，看是否补出 Furnace
  4. debug_dump table=crafting_recipes key=Furnace   ← 补发后复核

每一步的 stdout/stderr 原文写 `logs/run10f-step<N>.txt`；汇总写 `logs/run10f-steps.json`。
本脚本自己不调 craft/place/buy/sell/load_save，只做上面四条。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
PROBE = str(REPO / "scratch" / "_t213_probe.py")
LOGS = REPO / "logs"

STEPS = [
    ("step1_crafting_recipes", ["--table", "crafting_recipes", "--key", "Furnace"]),
    ("step2_trigger_actions", ["--table", "trigger_actions"]),
    ("step3_add_missed", ["--add-missed"]),
    ("step4_crafting_recipes_again", ["--table", "crafting_recipes", "--key", "Furnace"]),
]


def main() -> int:
    summary = {"steps": []}
    for name, args in STEPS:
        cmd = [PY, "-u", PROBE, *args]
        print(f"\n===== {name}: {' '.join(cmd[1:])} =====")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=180, cwd=str(REPO))
        out = (proc.stdout or "") + (("\n--- stderr ---\n" + proc.stderr) if proc.stderr else "")
        path = LOGS / f"run10f-{name}.txt"
        path.write_text(out, encoding="utf-8")
        print(out.strip()[:1800])
        exit_ok = proc.returncode == 0
        entry = {"name": name, "argv": args, "exit": proc.returncode,
                 "unknown_skill": "unknown_skill" in out, "log": str(path.relative_to(REPO))}
        summary["steps"].append(entry)
        print(f"[{name}] exit={proc.returncode} unknown_skill={'unknown_skill' in out} -> {entry['log']}")
        if name == "step1_crafting_recipes" and (not exit_ok or entry["unknown_skill"]):
            print("!! 第 1 步验活失败 —— 绝不执行 add_missed_recipes（写档动作）。停手。")
            summary["aborted_at"] = name
            break
    path = LOGS / "run10f-steps.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n汇总已写 {path.relative_to(REPO)}")
    return 0 if "aborted_at" not in summary else 3


if __name__ == "__main__":
    raise SystemExit(main())
