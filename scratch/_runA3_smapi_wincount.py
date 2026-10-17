# -*- coding: utf-8 -*-
"""run A′ 叫停后的「窗口内」SMAPI 计数（**只读、不冻结**：文件仍被游戏继续写，哈希会变）。

窗口 = 2026-10-17 08:37:40（A′ 起跑）～ 08:46:52.7（脑进程被杀、账本停止）。
SMAPI 行时间戳只有 [HH:MM:SS，无日期 ⇒ 按跨日假设：窗口在 08:xx:xx 之间。
"""
from __future__ import annotations

import hashlib
import os
import re
import sys

SRC = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
START, END = "08:37:40", "08:46:53"

TS = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})")
PATTERNS = {
    "newday_task": "Synchronizing 'NewDay' task",
    "before_save": "Context: before save.",
    "save_called": "SaveGame.Save() called.",
    "save_task": "Synchronizing 'Save' task",
    "save_completed": "completed without exceptions",
    "after_save": "after save, starting",
    "warping_farm": "Warping to Farm",
    "exec_post": "POST /v1/exec",
    "observe_get": "GET /v1/observe",
    "error": "ERROR",
    "disconnected": "Disconnected",
    "exception": "Exception",
}


def hms(s: str) -> int:
    h, m, sec = (int(x) for x in s.split(":"))
    return h * 3600 + m * 60 + sec


lo, hi = hms(START), hms(END)

raw = open(SRC, "rb").read()
text = raw.decode("utf-8", "replace")
lines = text.splitlines()
in_win, first, last = [], None, None
total_ts = 0
for ln in lines:
    m = TS.match(ln)
    if not m:
        continue
    total_ts += 1
    t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    if lo <= t <= hi:
        in_win.append(ln)
        if first is None:
            first = ln[:9]
        last = ln[:9]

print(f"源文件 = {SRC}")
print(f"size = {len(raw)} B  mtime = {os.path.getmtime(SRC):.3f}  总行数 = {len(lines)}  带时间戳行 = {total_ts}")
print(f"文件 SHA256（**会随游戏继续写而变化，不作冻结证据**）= {hashlib.sha256(raw).hexdigest()}")
print(f"窗口 {START}–{END}：命中行 = {len(in_win)}  首/末时间戳 = {first} / {last}")
print("\n窗口内六串 + 噪声计数：")
for name, needle in PATTERNS.items():
    n = sum(1 for ln in in_win if needle in ln)
    print(f"  {name:14} = {n}")

print("\n窗口内 NewDay / Save 逐行（最多 12 行）：")
for ln in in_win:
    if "Synchronizing 'NewDay' task" in ln or "Synchronizing 'Save' task" in ln:
        print("  " + ln[:160])
