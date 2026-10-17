# -*- coding: utf-8 -*-
"""task-214 四步内省取证的可复用版（0.7.38 首发 → 0.7.39 复跑直接换 `--tag`）。

顺序（与卡面一致）：
  1. debug_dump table=crafting_recipes key=Furnace   ← 白名单验活：不许再出现 unknown_skill
  2. debug_dump table=<table> [--also-tables ...]    ← 触发器原文（0.7.39 起可多表）
  3. add_missed_recipes  （**只调一次**，禁止循环）  ← 写玩家字典，看是否补出 Furnace
  4. debug_dump table=crafting_recipes key=Furnace   ← 补发后复核

安全约束（保留）：第 1 步失败 ⇒ **绝不**执行第 3 步（写档动作），直接停手。
第 2 步失败**不**阻断后续（读不到只是证据缺口，不是状态风险）。
本脚本自己不调 craft/place/buy/sell/load_save。

产物：`logs/<tag>-step<N>_<name>.txt`、`logs/<tag>-steps.json`（默认 tag=run10g，绝不覆盖 0.7.38 的 run10f 证据）。

用法：
  python scratch\\_t214_run.py --tag run10g
  python scratch\\_t214_run.py --tag run10g --also-tables objects,big_craftables,machines
  python scratch\\_t214_run.py --tag run10g --only 1,2        # 只跑指定步（3=写档动作，独立决定）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):  # 中文输出不能依赖调用方的 PYTHONUTF8/代码页
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
PROBE = str(REPO / "scratch" / "_t213_probe.py")
LOGS = REPO / "logs"

STEP_NAMES = {1: "step1_crafting_recipes", 2: "step2_trigger_actions",
              3: "step3_add_missed", 4: "step4_crafting_recipes_again"}


def build_steps(args) -> list[tuple[str, list[str], int]]:
    tables = ["trigger_actions", *[t.strip() for t in (args.also_tables or "").split(",") if t.strip()]]
    steps: list[tuple[str, list[str], int]] = [
        (STEP_NAMES[1], ["--table", "crafting_recipes", "--key", "Furnace"], 1),
        (STEP_NAMES[2], ["--table", tables[0]], 2),
        *[(f"{STEP_NAMES[2]}__{t}", ["--table", t], 2) for t in tables[1:]],
        (STEP_NAMES[3], ["--add-missed"], 3),
        (STEP_NAMES[4], ["--table", "crafting_recipes", "--key", "Furnace"], 4),
    ]
    if args.only:
        wanted = {int(x) for x in args.only.split(",") if x.strip()}
        steps = [s for s in steps if s[2] in wanted]
    return steps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="run10g", help="产物前缀（默认 run10g，避免覆盖 run10f）")
    ap.add_argument("--also-tables", default="", help="step2 额外表，逗号分隔（如 objects,big_craftables,machines）")
    ap.add_argument("--only", default="", help="只跑指定步骤号，逗号分隔（1,2,3,4）")
    ap.add_argument("--probe", default=PROBE, help="探针脚本路径（默认 scratch\\_t213_probe.py）")
    args = ap.parse_args()

    summary = {"tag": args.tag, "probe": args.probe, "steps": []}
    for name, cargs, num in build_steps(args):
        cmd = [PY, "-u", args.probe, *cargs]
        print(f"\n===== {name}: {' '.join(cmd[1:])} =====")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=180, cwd=str(REPO))
        out = (proc.stdout or "") + (("\n--- stderr ---\n" + proc.stderr) if proc.stderr else "")
        path = LOGS / f"{args.tag}-{name}.txt"
        path.write_text(out, encoding="utf-8")
        print(out.strip()[:1800])
        exit_ok = proc.returncode == 0
        entry = {"name": name, "step": num, "argv": cargs, "exit": proc.returncode,
                 "unknown_skill": "unknown_skill" in out, "load_failed": "load_failed" in out,
                 "log": str(path.relative_to(REPO))}
        summary["steps"].append(entry)
        print(f"[{name}] exit={proc.returncode} unknown_skill={entry['unknown_skill']} "
              f"load_failed={entry['load_failed']} -> {entry['log']}")
        if num == 1 and (not exit_ok or entry["unknown_skill"]):
            print("!! 第 1 步验活失败 —— 绝不执行 add_missed_recipes（写档动作）。停手。")
            summary["aborted_at"] = name
            break
    path = LOGS / f"{args.tag}-steps.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n汇总已写 {path.relative_to(REPO)}")
    return 0 if "aborted_at" not in summary else 3


if __name__ == "__main__":
    raise SystemExit(main())
