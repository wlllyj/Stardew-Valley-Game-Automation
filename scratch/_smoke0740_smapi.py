# -*- coding: utf-8 -*-
"""0.7.40 冒烟 step6 细查：SMAPI 窗口六串 + 第三次跨日前后原文（只读）。"""
from __future__ import annotations

import os
import re

TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")
P = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
L = open(P, encoding="utf-8", errors="replace").read().splitlines()
print(f"total_lines={len(L)}")

win = [(i, s) for i, s in enumerate(L, 1) if TS.match(s) and "12:08:30" <= TS.match(s).group(1) <= "12:24:00"]
print(f"window_12:08:30-12:24:00_lines={len(win)}")
pats = {
    "NewDay": "Synchronizing 'NewDay' task",
    "before_save": "Context: before save.",
    "Save_called": "SaveGame.Save() called.",
    "Save_task": "Synchronizing 'Save' task",
    "completed": "completed without exceptions",
    "after_save": "after save, starting",
}
for k, v in pats.items():
    hits = [(i, TS.match(s).group(1)) for i, s in win
            if v in s and not (" by AgentFarm " in s or "| v0." in s)]
    print(f"{k:12} = {len(hits)}  {hits}")
print("\n--- 第三次 NewDay 前后（L3295-L3345）---")
for i in range(3295, 3346):
    if i <= len(L):
        print(f"{i}: {L[i-1][:150]}")
print("\n--- 跑到 12:24 之间是否还有 Save called / after save（跑完后迟到的落盘）---")
for i, s in win:
    if "SaveGame.Save() called." in s or "after save, starting" in s or "ShippingMenu" in s or "LevelUpMenu" in s:
        print(f"{i}: {s[:160]}")
