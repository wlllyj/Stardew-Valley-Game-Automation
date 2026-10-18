# -*- coding: utf-8 -*-
"""run 收工取证（只读）：三检查器 + SMAPI 五联计数。

统一用 python subprocess(encoding="utf-8") 落盘（pwsh 的 `>`/`*>` 会写 UTF-16）。

参数化（task-209 之后的 mechanical 改造，默认值保持 run9c 原行为）：
  python scratch\\run9c-tools.py                       # 等价原行为（tag=run9c, days=3）
  python scratch\\run9c-tools.py --tag runA5-0739 --journal logs/longrun-runA5-0739.jsonl --days 5

输出：logs\\<tag>-verify.json / <tag>-verify.txt / <tag>-analyze.txt /
      <tag>-lead-check.txt / <tag>-smapi-counts.txt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PY = sys.executable

_ap = argparse.ArgumentParser(description="run 收工取证：三检查器 + SMAPI 五联（默认保持 run9c 原行为）")
_ap.add_argument("--tag", default="run9c", help="产物前缀（默认 run9c）")
_ap.add_argument("--journal", default=None, help="账本（默认 logs/longrun-3day-llm-<tag>.jsonl）")
_ap.add_argument("--smapi", default=None, help="SMAPI 副本（默认 logs/<tag>-smapi-window.txt）")
_ap.add_argument("--snapshots", default=None, help="外部快照（默认 scratch/<tag>-external-snapshots.jsonl）")
_ap.add_argument("--days", type=int, default=3, help="--days 透传（默认 3，保持原行为）")
_args = _ap.parse_args()

TAG = _args.tag
DAYS = str(_args.days)
JOURNAL = _args.journal or f"logs/longrun-3day-llm-{TAG}.jsonl"
SNAPS = _args.snapshots or f"scratch/{TAG}-external-snapshots.jsonl"
SMAPI = _args.smapi or os.path.join(ROOT, "logs", f"{TAG}-smapi-window.txt")


def run(args, out_name, title):
    p = subprocess.run([PY, "-X", "utf8"] + args, cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    body = (f"### {title}\n$ {' '.join(args)}\n--- stdout ---\n{p.stdout}\n"
            f"--- stderr ---\n{p.stderr}\n--- rc={p.returncode} ---\n")
    path = os.path.join(ROOT, "logs", out_name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    print(f"[{out_name}] rc={p.returncode}")
    return p


pj = run(["tools/verify-run3.py", "--journal", JOURNAL, "--days", DAYS, "--json"],
         f"{TAG}-verify.json", "verify-run3.py --json")
try:
    j = json.loads(pj.stdout)
    print("  verdict =", j.get("verdict"), "| strict_verdict =", j.get("strict_verdict"),
          "| problems =", len(j.get("problems") or []),
          "| strict_problem_count =", j.get("strict_problem_count"),
          "| history_problems =", len(j.get("history_problems") or []))
except Exception as exc:  # noqa: BLE001
    print("  [!] --json 解析失败：", type(exc).__name__, exc)

run(["tools/verify-run3.py", "--journal", JOURNAL, "--days", DAYS], f"{TAG}-verify.txt", "verify-run3.py")
run(["tools/analyze-longrun.py", "--journal", JOURNAL, "--days", DAYS], f"{TAG}-analyze.txt", "analyze-longrun.py")
run(["scratch/run9-lead-check.py", "--journal", JOURNAL, "--snapshots", SNAPS,
     "--smapi", SMAPI, "--days", DAYS], f"{TAG}-lead-check.txt", "run9-lead-check.py")

# --- SMAPI 五联计数（含 L16 插件描述行假阳性判别）---
ts_re = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")
plug_re = re.compile(r" by AgentFarm |\| v0\.")

if not os.path.exists(SMAPI):
    print(f"[!] SMAPI 副本不存在：{SMAPI} ⇒ 五联计数跳过（如实记缺失，不猜）")
    sys.exit(0)
lines = open(SMAPI, encoding="utf-8", errors="replace").read().splitlines()


def hit(pat):
    return [i + 1 for i, l in enumerate(lines) if re.search(pat, l)]


newday = hit(r"Synchronizing 'NewDay' task")
before = hit(r"Context: before save\.")
called_raw = hit(r"SaveGame\.Save\(\) called\.")
called_fix = [i for i in called_raw if not plug_re.search(lines[i - 1])]
false_pos = [i for i in called_raw if i not in called_fix]
task = hit(r"Synchronizing 'Save' task")
comp = hit(r"completed without exceptions")
after = hit(r"after save, starting")

out = [
    f"tag = {TAG}  journal = {JOURNAL}",
    f"SMAPI 冻结文件 = {SMAPI}",
    f"总行数 = {len(lines)}",
    f"Synchronizing 'NewDay' task  : {len(newday)}  行号={newday}",
    f"Context: before save.        : {len(before)}  行号={before}",
    f"SaveGame.Save() called. 原始  : {len(called_raw)}  行号={called_raw}",
    f"  └ 插件描述行假阳性剔除      : {false_pos}",
    f"SaveGame.Save() called. 修正  : {len(called_fix)}  行号={called_fix}",
    f"Synchronizing 'Save' task    : {len(task)}  行号={task}",
    f"completed without exceptions : {len(comp)}  行号={comp}",
    f"after save, starting         : {len(after)}  行号={after}",
    f"(时间戳前缀匹配数 = {len([l for l in lines if ts_re.match(l)])})",
]
for i in false_pos:
    out.append(f"    [假阳性 L{i}] {lines[i - 1][:220]}")
text = "\n".join(out)
with open(os.path.join(ROOT, "logs", f"{TAG}-smapi-counts.txt"), "w", encoding="utf-8") as fh:
    fh.write(text + "\n")
print("\n" + text)
