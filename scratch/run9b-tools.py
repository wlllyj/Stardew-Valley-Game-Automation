# -*- coding: utf-8 -*-
"""run9b 收工取证（只读）：
① 从冻结的 SMAPI 窗口里按行号抽出每次跨日的「五串落盘链」→ logs/run9b-smapi-chain.txt
② 用 subprocess(encoding='utf-8') 跑两个检查器 → logs/run9b-verify.txt / logs/run9b-analyze.txt
   并把两侧的 verdict / strict_verdict 行打出来。

注意：pwsh 的 `>`/`*>` 会写 UTF-16，所以一律用 python 落盘。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOGS = os.path.join(ROOT, "logs")
SMAPI = os.path.join(LOGS, "run9b-smapi-window.txt")
JOURNAL = os.path.join(LOGS, "longrun-3day-llm-run9b.jsonl")

PATTERNS = [
    ("NewDay", r"Synchronizing 'NewDay' task"),
    ("before_save", r"Context: before save\."),
    ("save_called", r"SaveGame\.Save\(\) called\."),
    ("saving", r"Saving without compression"),
    ("completed", r"completed without exceptions"),
    ("after_save", r"after save, starting"),
    ("newgame", r"starting (spring|summer|fall|winter) \d+ Y1"),
]

lines = []
with open(SMAPI, encoding="utf-8", errors="replace") as fh:
    for i, line in enumerate(fh, 1):
        lines.append((i, line.rstrip("\n")))


def ts(line: str) -> str:
    m = re.match(r"\[(\d{2}:\d{2}:\d{2})", line)
    return m.group(1) if m else "??:??:??"


hits = {name: [] for name, _ in PATTERNS}
for i, line in lines:
    for name, pat in PATTERNS:
        if re.search(pat, line):
            hits[name].append((i, ts(line), line))

out = []
out.append(f"SMAPI 冻结窗口: {SMAPI}")
out.append(f"总行数: {len(lines)}")
out.append("")
out.append("=== 计数 ===")
for name, _ in PATTERNS:
    out.append(f"{name:12s} = {len(hits[name])}")
out.append("")
out.append("=== 逐条（行号 / 时间 / 原文） ===")
for name, _ in PATTERNS:
    out.append(f"\n--- {name} ({len(hits[name])}) ---")
    for i, t, line in hits[name]:
        # 去掉行首时间戳后面的 TRACE/INFO 前缀过长内容仍保留
        out.append(f"L{i} {t} {line}")

text = "\n".join(out)
with open(os.path.join(LOGS, "run9b-smapi-chain.txt"), "w", encoding="utf-8") as fh:
    fh.write(text + "\n")
print(text)

print("\n=== 两侧检查器 ===")
PY = sys.executable
for script, args, outfile in (
    ("tools/verify-run3.py", ["--journal", JOURNAL, "--days", "3"], "run9b-verify.txt"),
    ("tools/analyze-longrun.py", ["--journal", JOURNAL, "--window", "3"], "run9b-analyze.txt"),
):
    cmd = [PY, "-W", "error::SyntaxWarning", os.path.join(ROOT, script)] + args
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    body = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    with open(os.path.join(LOGS, outfile), "w", encoding="utf-8") as fh:
        fh.write(body)
    print(f"\n--- {script} rc={proc.returncode} → logs/{outfile} ({len(body)} 字符) ---")
    for line in body.splitlines():
        if re.search(r"verdict|VERIFIED|needs_review|尾部|达标|结论|history_problems|严格", line, re.I):
            print("   " + line)
