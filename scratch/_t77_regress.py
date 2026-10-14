r"""task-77 A3 段：账本回归（task-75 前后逐字对比问题清单）。

用两个工具跑同一批账本：
  * `scratch\_t72_tool_fix.py` = `9f554d7:tools/verify-run3.py`（task-75 **之前**，由 `_t72_freeze2.py` 生成）
  * `scratch\_t77_snap\tools\verify-run3.py` = `8ceea87`（task-75 之后）
比较：退出码 + 「问题：」块（信息项允许因 task-68 新 info 而增加）。

用法：$env:PYTHONUTF8="1"; python scratch\_t77_regress.py
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
OLD = os.path.join(HERE, "_t72_tool_fix.py")
NEW = os.path.join(HERE, "_t77_snap", "tools", "verify-run3.py")

CASES = [
    (os.path.join(ROOT, "scratch", "journal-green.jsonl"), 3),
    (os.path.join(ROOT, "scratch", "_t5x_vacuum.jsonl"), 1),
    (os.path.join(ROOT, "scratch", "review-t54-vacuum-all-unreachable.jsonl"), 1),
    (os.path.join(ROOT, "logs", "longrun-3day-llm-run2.jsonl"), 3),
    (os.path.join(ROOT, "logs", "longrun-3day-llm-run3.jsonl"), 3),
    (os.path.join(ROOT, "logs", "longrun-3day-llm-run5.jsonl"), 3),
    (os.path.join(ROOT, "logs", "longrun-3day-llm-run6.jsonl"), 3),
]


def run(tool: str, ledger: str, days: int):
    cp = subprocess.run([PY, tool, "--journal", ledger, "--days", str(days)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (cp.stdout or "") + (cp.stderr or "")
    probs: list[str] = []
    seen = False
    for ln in out.splitlines():
        if ln.strip().startswith("问题"):
            seen = True
            continue
        if seen:
            if ln.strip().startswith(("结论", "信息", "-", "=")):
                if ln.strip().startswith("结论"):
                    break
                if ln.strip().startswith("-"):
                    probs.append(ln.strip())
                    continue
            break
    return cp.returncode, probs


print(f"旧工具 = {OLD}（存在：{os.path.exists(OLD)}）")
print(f"新工具 = {NEW}")
print()
bad = 0
for ledger, days in CASES:
    if not os.path.exists(ledger):
        print(f"— 缺文件 {ledger}")
        continue
    rc_old, p_old = run(OLD, ledger, days)
    rc_new, p_new = run(NEW, ledger, days)
    same = (rc_old == rc_new) and (p_old == p_new)
    name = os.path.basename(ledger)
    print(f"--- {name}  days={days}  旧 exit={rc_old} / 新 exit={rc_new}  "
          f"问题数 {len(p_old)}→{len(p_new)}  {'一致' if same else '★不一致★'}")
    if not same:
        bad += 1
        only_old = [x for x in p_old if x not in p_new]
        only_new = [x for x in p_new if x not in p_old]
        for x in only_old:
            print("    -（旧有新无）" + x[:170])
        for x in only_new:
            print("    +（新有旧无）" + x[:170])
print()
print(f"不一致账本数 = {bad}")
print("DONE")
