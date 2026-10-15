# -*- coding: utf-8 -*-
"""在冻结的 run7 SMAPI 窗口文件里按行号重数跨日标记（只读，用于核对 docs/_run7-evidence.md §3.2 表）。"""
from __future__ import annotations

import re

P = r"logs\run7-smapi-window.txt"
PATS = [
    "Synchronizing 'NewDay' task",
    "Context: before save.",
    "SaveGame.Save() called.",
    "Synchronizing 'Save' task",
    "completed without exceptions",
    "after save, starting",
]

lines = open(P, encoding="utf-8", errors="replace").read().splitlines()
print(f"文件行数 = {len(lines)}")
for pat in PATS:
    hits = [(i + 1, ln) for i, ln in enumerate(lines) if pat in ln]
    print(f"\n=== {pat!r}: {len(hits)} 次")
    for no, txt in hits:
        m = re.match(r"\[(\d\d:\d\d:\d\d)", txt)
        ts = m.group(1) if m else "??"
        tail = txt.split("] ", 1)[-1][:90]
        print(f"  L{no} {ts} {tail}")
