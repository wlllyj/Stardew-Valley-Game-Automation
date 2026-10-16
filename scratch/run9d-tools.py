# -*- coding: utf-8 -*-
"""run9d 收尾取证（只读）：
1) 冻结 SMAPI-latest.txt → logs\\run9d-smapi-window.txt（记 size/mtime/sha256）
2) 窗口内六串计数 + 行号（NewDay / before save / Save called / Save task / completed / after save）
   + Warping to Farm / 噪声关键词
3) 用 python subprocess(encoding="utf-8") 跑三个检查器，输出落 logs\\run9d-*.txt 并打印 rc 与判决行

用法：python scratch\\run9d-tools.py [--after HH:MM:SS] [--before HH:MM:SS]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PY = sys.executable
SMAPI_SRC = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
SMAPI_DST = os.path.join(ROOT, "logs", "run9d-smapi-window.txt")
JOURNAL = os.path.join(ROOT, "logs", "longrun-3day-llm-run9d.jsonl")
SNAPSHOTS = os.path.join(ROOT, "scratch", "run9d-external-snapshots.jsonl")

TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", default="01:32:58")
    ap.add_argument("--before", default="02:11:45")
    args = ap.parse_args()

    # 1) 冻结
    shutil.copy2(SMAPI_SRC, SMAPI_DST)
    st = os.stat(SMAPI_DST)
    print("=== SMAPI 冻结 ===")
    print(f"src = {SMAPI_SRC}")
    print(f"dst = {SMAPI_DST}")
    print(f"size = {st.st_size} B / mtime = {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))} / sha256 = {sha256(SMAPI_DST)}")
    print(f"src sha256 = {sha256(SMAPI_SRC)}（与 dst 一致 = {sha256(SMAPI_SRC) == sha256(SMAPI_DST)}）")

    # 2) 六串计数
    lines = open(SMAPI_DST, encoding="utf-8", errors="replace").read().splitlines()
    pats = {
        "NewDay": lambda s: "Synchronizing 'NewDay' task" in s,
        "before_save": lambda s: "Context: before save." in s,
        "Save_called": lambda s: ("SaveGame.Save() called." in s and TS.match(s) is not None
                                  and " by AgentFarm " not in s and "| v0." not in s),
        "Save_task": lambda s: "Synchronizing 'Save' task" in s,
        "completed": lambda s: "completed without exceptions" in s,
        "after_save": lambda s: "after save, starting" in s,
    }
    inwin = []
    for i, s in enumerate(lines, 1):
        m = TS.match(s)
        if not m:
            continue
        t = m.group(1)
        if args.after <= t <= args.before:
            inwin.append((i, t, s))
    print(f"\n=== 窗口 {args.after}–{args.before} ===")
    print(f"带时间戳行数 = {len(inwin)}（文件总行 {len(lines)}）")
    for name, fn in pats.items():
        hits = [(i, t) for i, t, s in inwin if fn(s)]
        print(f"{name:12} = {len(hits):2}  行号 {[i for i, _ in hits]}")
    for kw in ["Warping to Farm", "ERROR", "Disconnected", "ClosedGame", "Disposing", "soft_oal", "Exception"]:
        n = sum(1 for _i, _t, s in inwin if kw in s)
        print(f"  {kw:20} = {n}")

    # 3) 检查器
    jobs = [
        ("verify-run3", [PY, "-X", "utf8", os.path.join(ROOT, "tools", "verify-run3.py"),
                         "--journal", JOURNAL, "--days", "5", "--json"],
         os.path.join(ROOT, "logs", "run9d-verify.txt")),
        ("analyze-longrun", [PY, "-X", "utf8", os.path.join(ROOT, "tools", "analyze-longrun.py"),
                             "--journal", JOURNAL, "--window", "5"],
         os.path.join(ROOT, "logs", "run9d-analyze.txt")),
        ("lead-check", [PY, "-X", "utf8", os.path.join(ROOT, "scratch", "run9-lead-check.py"),
                        "--journal", JOURNAL, "--snapshots", SNAPSHOTS, "--smapi", SMAPI_DST],
         os.path.join(ROOT, "logs", "run9d-lead-check.txt")),
    ]
    print("\n=== 检查器 ===")
    for name, cmd, out in jobs:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(r.stdout or "")
            if r.stderr:
                fh.write("\n--- stderr ---\n" + r.stderr)
        print(f"[{name}] rc={r.returncode} → {out}（stdout {len(r.stdout or '')} 字符）")
        tail = [ln for ln in (r.stdout or "").splitlines() if ln.strip()][-25:]
        for ln in tail:
            print("    " + ln[:200])
        if r.stderr and r.stderr.strip():
            print("    stderr:", r.stderr.strip()[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
