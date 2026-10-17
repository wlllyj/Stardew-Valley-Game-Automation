# -*- coding: utf-8 -*-
"""run A′ SMAPI 窗口**时点冻结**：一次性读源、写副本、算 size/mtime/SHA256/行数与 BYTE_IDENTICAL。

源 `%APPDATA%\\StardewValley\\ErrorLogs\\SMAPI-latest.txt` 仍被游戏继续写 ⇒ 这是**时点快照**，
冻结后源文件继续增长，不许再复冻覆盖。只读源、只写 dst。
"""
from __future__ import annotations

import hashlib
import os
import re
import sys

SRC = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
DST = sys.argv[1] if len(sys.argv) > 1 else os.path.join("logs", "runA3-0736-smapi-window.txt")

# 1) 一次性读源（此刻的字节）
raw = open(SRC, "rb").read()
src_size, src_mtime = os.path.getsize(SRC), os.path.getmtime(SRC)
src_sha = hashlib.sha256(raw).hexdigest()
src_lines = len(raw.splitlines())

# 2) 写副本（不截断、不改内容）
with open(DST, "wb") as fh:
    fh.write(raw)
dst_raw = open(DST, "rb").read()
dst_size, dst_mtime = os.path.getsize(DST), os.path.getmtime(DST)
dst_sha = hashlib.sha256(dst_raw).hexdigest()
dst_lines = len(dst_raw.splitlines())

print(f"src = {SRC}")
print(f"     size={src_size}  lines={src_lines}  mtime={src_mtime:.3f}  sha256={src_sha}")
print(f"dst = {DST}")
print(f"     size={dst_size}  lines={dst_lines}  mtime={dst_mtime:.3f}  sha256={dst_sha}")
print(f"BYTE_IDENTICAL = {raw == dst_raw and src_sha == dst_sha and src_size == dst_size}")
print(f"dst mtime(本地) = {__import__('datetime').datetime.fromtimestamp(dst_mtime).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

# 3) 窗口计数（与冻结同时给出，供证据文档 §3 使用）
TS = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})")
START, END = "08:37:40", "08:46:53"
PATTERNS = {
    "NewDay": "Synchronizing 'NewDay' task",
    "before_save": "Context: before save.",
    "SaveGame.Save() called": "SaveGame.Save() called.",
    "Save_task": "Synchronizing 'Save' task",
    "completed": "completed without exceptions",
    "after_save": "after save, starting",
    "Warping_to_Farm": "Warping to Farm",
    "POST_v1_exec": "POST /v1/exec",
    "GET_v1_observe": "GET /v1/observe",
    "ERROR": "ERROR",
    "Disconnected": "Disconnected",
    "Exception": "Exception",
}


def hms(s: str) -> int:
    h, m, sec = (int(x) for x in s.split(":"))
    return h * 3600 + m * 60 + sec


lo, hi = hms(START), hms(END)
win = []
for ln in dst_raw.decode("utf-8", "replace").splitlines():
    m = TS.match(ln)
    if not m:
        continue
    t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    if lo <= t <= hi:
        win.append(ln)
print(f"\n窗口 {START}–{END} 命中 {len(win)} 行：")
for k, needle in PATTERNS.items():
    print(f"  {k:22} = {sum(1 for ln in win if needle in ln)}")
