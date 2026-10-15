# -*- coding: utf-8 -*-
"""run7 §3 外部证据 + §1 版本核对（只读）。

- SMAPI-latest.txt：run7 窗口（22:53:17–23:18:29）内的 NewDay / Save 行号与计数；
  以及窗口之后那次自动过夜（`starting summer 11 Y1`）单独列出。
- 存档目录：主文件 / SaveGameInfo / _old / SaveGameInfo_old 的 size+mtime。
- 版本：与被测文件现盘的 SHA256+mtime（与 version sidecar 对照）。
用法：python scratch\\run7-smapi.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SIDE = os.path.join(REPO, "logs", "longrun-3day-llm-run7.version.json")

WIN_START = "22:53:17"
WIN_END = "23:18:29"

KEYS = [
    ("newday", "Synchronizing 'NewDay' task"),
    ("before_save", "Context: before save."),
    ("save_called", "SaveGame.Save() called."),
    ("save_sync", "Synchronizing 'Save' task"),
    ("save_done", "SaveGame.Save() completed without exceptions."),
    ("after_save", "Context: after save, starting"),
]
NOISE = ["Disconnected", "ERROR", "soft_oal", "ClosedGame", "Exception", "Disposing", "Warping to Farm"]


def sha256(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


print("=== §3.1 SMAPI 窗口 ===")
lines = open(SMAPI, encoding="utf-8", errors="replace").read().splitlines()
print(f"{SMAPI}\n行数={len(lines)}  mtime={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.stat(SMAPI).st_mtime))}")
stamp = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")
all_ts = [m.group(1) for m in (stamp.match(ln) for ln in lines) if m]
print(f"日志时间跨度 = {all_ts[0] if all_ts else '-'} … {all_ts[-1] if all_ts else '-'}（共 {len(all_ts)} 条带时间戳的行）")
in_win = 0
hits = {k: [] for k, _ in KEYS}
after_windows = []
for i, ln in enumerate(lines, 1):
    m = stamp.match(ln)
    ts = m.group(1) if m else ""
    inside = WIN_START <= ts <= WIN_END if ts else False
    if inside:
        in_win += 1
    for k, pat in KEYS:
        if pat in ln:
            (hits[k].append((i, ts, ln.strip()[:110])) if inside else None)
            if k == "after_save" and not inside:
                after_windows.append((i, ts, ln.strip()[:140]))
print(f"窗口内行数 = {in_win}（窗口 {WIN_START} – {WIN_END}）")
for k, _ in KEYS:
    v = hits[k]
    print(f"  {k:12} 窗口内 {len(v):2} 次；首/末行号 = {v[0][0] if v else '-'} / {v[-1][0] if v else '-'}")
    for i, ts, txt in v:
        print(f"      L{i} {ts} {txt}")
print("  窗口之外的 `after save, starting …`（= run7 之后的游戏自动过夜等）：")
for i, ts, txt in after_windows:
    print(f"      L{i} {ts} {txt}")
for pat in NOISE:
    n_in = sum(1 for ln in lines if pat in ln and (lambda m: bool(m) and WIN_START <= m.group(1) <= WIN_END)(stamp.match(ln)))
    print(f"  噪声计数（窗口内）{pat!r} = {n_in}")
print("  run7 窗口内的时间段行数分布：")
band = {}
for ln in lines:
    m = stamp.match(ln)
    if m and WIN_START <= m.group(1) <= WIN_END:
        band[m.group(1)[:5]] = band.get(m.group(1)[:5], 0) + 1
print(f"      {json.dumps(band, ensure_ascii=False)}")

print("\n=== §3.2 存档四条 ===")
if os.path.isdir(SAVE_DIR):
    for name in ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old"):
        p = os.path.join(SAVE_DIR, name)
        if os.path.exists(p):
            stt = os.stat(p)
            print(f"  {name:24} {stt.st_size:>9} B  {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stt.st_mtime))}"
                  f".{stt.st_mtime_ns % 1_000_000_000:09d}")
        else:
            print(f"  {name:24} 不存在")
else:
    print(f"  存档目录不存在：{SAVE_DIR}")

print("\n=== §1 现盘被测文件（与 sidecar 对照）===")
side = json.load(open(SIDE, encoding="utf-8"))
print(f"sidecar: head={side['head']} pid={side['pid']} started_at={side['started_at']} worktree_clean={side['worktree_clean']}")
print(f"sidecar git_status_short={json.dumps(side.get('git_status_short'), ensure_ascii=False)}")
for rel, meta in side["files"].items():
    p = os.path.join(REPO, rel.replace("/", os.sep))
    if not os.path.exists(p):
        print(f"  {rel}\n      现盘缺失")
        continue
    stt = os.stat(p)
    now_sha = sha256(p)
    now_mt = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stt.st_mtime)) + f".{stt.st_mtime_ns % 1_000_000_000:09d}"
    ok = "一致" if now_sha == meta["sha256"] else "**不一致**"
    print(f"  {rel}\n      sidecar sha={meta['sha256']} mtime={meta['mtime']}")
    print(f"      现盘   sha={now_sha} mtime={now_mt}  => {ok}")

print("\n=== 外部快照文件 ===")
for name in ("run6-external-snapshots.jsonl", "run7-external-snapshots.jsonl"):
    p = os.path.join(REPO, "scratch", name)
    if os.path.exists(p):
        print(f"  {name}: {os.path.getsize(p)} B / {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.stat(p).st_mtime))}")
        for ln in open(p, encoding="utf-8"):
            ln = ln.strip()
            if ln:
                print(f"      {ln[:400]}")
    else:
        print(f"  {name}: 不存在")
