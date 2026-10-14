r"""task-79：用我自己的复现脚本重跑 V5 / V1 / V2 / B11 + 六本既有账本，对比两个工具。

旧工具 = `scratch/_t77_snap/tools/verify-run3.py`（快照 8ceea87，task-78 之前）
新工具 = 仓库 `tools/verify-run3.py`（= `2ce830b`）
账本 = `scratch/_t77_forge.py` 生成的那批（V1…V5）+ `scratch/review-t72-relabel-clean.jsonl`（B11）+ 既有真机账本。

用法：$env:PYTHONUTF8="1"; python scratch\_t79_replay.py
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
OLD = os.path.join(HERE, "_t77_snap", "tools", "verify-run3.py")
NEW = os.path.join(ROOT, "tools", "verify-run3.py")

CASES = [
    ("V1  encircled 大 + 0 动作 + verified（卡面要求仍 0）",
     os.path.join(HERE, "review-t77-v1-encircled-no-work-verified.jsonl"), 1),
    ("V1' 控制组（不写 encircled）",
     os.path.join(HERE, "review-t77-v1c-control-no-encircled.jsonl"), 1),
    ("V2  遮蔽（更早 leftover>0、最后一轮 0）",
     os.path.join(HERE, "review-t77-v2-encircled-masked-by-later-clean-stage.jsonl"), 1),
    ("V3  诚实红（encircled 留在 leftover）",
     os.path.join(HERE, "review-t77-v3-encircled-leftover-honest-red.jsonl"), 1),
    ("V4  谎报 no_unmet_stages",
     os.path.join(HERE, "review-t77-v4-encircled-lie-no-unmet.jsonl"), 1),
    ("V5  encircled 抬高上界分母（本次要关的通道）",
     os.path.join(HERE, "review-t77-v5-encircled-inflates-unreachable-bound.jsonl"), 1),
    ("B11 真失败改写成 unreachable（账本层不可判）",
     os.path.join(HERE, "review-t72-relabel-clean.jsonl"), 1),
    ("真机 green", os.path.join(HERE, "journal-green.jsonl"), 3),
    ("_t5x_vacuum（Lead 的）", os.path.join(HERE, "_t5x_vacuum.jsonl"), 1),
    ("run2", os.path.join(ROOT, "logs", "longrun-3day-llm-run2.jsonl"), 3),
    ("run3", os.path.join(ROOT, "logs", "longrun-3day-llm-run3.jsonl"), 3),
    ("run5", os.path.join(ROOT, "logs", "longrun-3day-llm-run5.jsonl"), 3),
    ("run6", os.path.join(ROOT, "logs", "longrun-3day-llm-run6.jsonl"), 3),
]


def run(tool: str, ledger: str, days: int):
    cp = subprocess.run([PY, tool, "--journal", ledger, "--days", str(days)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (cp.stdout or "") + (cp.stderr or "")
    probs, seen = [], False
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith("问题"):
            seen = True
            continue
        if seen:
            if s.startswith("结论"):
                break
            if s.startswith("-"):
                probs.append(s)
            continue
    return cp.returncode, probs


print(f"旧工具 = {OLD}\n新工具 = {NEW}\n")
warn = []
for label, ledger, days in CASES:
    if not os.path.exists(ledger):
        print(f"— 缺文件：{ledger}")
        continue
    rc_o, p_o = run(OLD, ledger, days)
    rc_n, p_n = run(NEW, ledger, days)
    flag = ""
    if label.startswith("V5") and rc_n != 1:
        flag = "  ★V5 未关闭★"
        warn.append(label)
    print(f"--- {label}")
    print(f"    exit：旧={rc_o} 新={rc_n}   问题数：{len(p_o)}→{len(p_n)}{flag}")
    for x in p_n[:3]:
        print("      新问题：" + x[:165])
    only_old = [x for x in p_o if x not in p_n]
    only_new = [x for x in p_n if x not in p_o]
    for x in only_new[:3]:
        print("      +（新有旧无）" + x[:165])
    for x in only_old[:2]:
        print("      -（旧有新无）" + x[:165])
print()
print(f"V5 判定：{'未关闭，见上' if warn else '已关闭（新工具 exit 1）'}")
print("DONE")
