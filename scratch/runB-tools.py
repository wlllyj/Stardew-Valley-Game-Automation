# -*- coding: utf-8 -*-
"""run B（runB-0732，提前叫停）收尾取证（只读）：
1) 冻结 SMAPI-latest.txt → logs\\runB-0732-smapi-window.txt（记 size/mtime/sha256）
2) 窗口内六串计数 + 行号 + Warping/噪声计数
3) 跑 tools\\verify-run3.py / tools\\analyze-longrun.py / scratch\\run9-lead-check.py，UTF-8 落盘

用法：python scratch\\runB-tools.py [--after HH:MM:SS] [--before HH:MM:SS] [--no-freeze]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PY = sys.executable
SMAPI_SRC = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
SMAPI_DST = os.path.join(ROOT, "logs", "runB-0732-smapi-window.txt")
JOURNAL = os.path.join(ROOT, "logs", "longrun-runB-0732.jsonl")
SNAPSHOTS = os.path.join(ROOT, "scratch", "runB-0732-external-snapshots.jsonl")
TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")


def sha256(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


def try_sha256(p: str) -> str:
    try:
        return sha256(p)
    except Exception as exc:  # noqa: BLE001
        return f"<无法读取：{type(exc).__name__}>"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", default="04:27:17")
    ap.add_argument("--before", default="04:50:42")
    ap.add_argument("--no-freeze", action="store_true")
    args = ap.parse_args()

    if not args.no_freeze:
        shutil.copy2(SMAPI_SRC, SMAPI_DST)
    st = os.stat(SMAPI_DST)
    print("=== SMAPI 冻结（run B）===")
    print(f"dst = {SMAPI_DST}")
    print(f"size = {st.st_size} B / mtime = {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))} / sha256 = {sha256(SMAPI_DST)}")
    src_sha = try_sha256(SMAPI_SRC)
    print(f"src sha256 = {src_sha}（与 dst 一致 = {src_sha == sha256(SMAPI_DST)}）")

    lines = open(SMAPI_DST, encoding="utf-8", errors="replace").read().splitlines()
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
    pats = {
        "NewDay": lambda s: "Synchronizing 'NewDay' task" in s,
        "before_save": lambda s: "Context: before save." in s,
        "Save_called": lambda s: ("SaveGame.Save() called." in s and TS.match(s) is not None
                                  and " by AgentFarm " not in s and "| v0." not in s),
        "Save_called_raw": lambda s: ("SaveGame.Save() called." in s and TS.match(s) is not None),
        "Save_task": lambda s: "Synchronizing 'Save' task" in s,
        "completed": lambda s: "completed without exceptions" in s,
        "after_save": lambda s: "after save, starting" in s,
    }
    counts = {}
    for name, fn in pats.items():
        hits = [(i, t) for i, t, s in inwin if fn(s)]
        counts[name] = len(hits)
        print(f"{name:16} = {len(hits):2}  行号 {[i for i, _ in hits]}")
    print(f"  >>> NewDay {counts['NewDay']} vs 修正 Save_called {counts['Save_called']} ⇒ "
          f"{'⚠ 有 NewDay 无 Save（硬问题）' if counts['NewDay'] > counts['Save_called'] else '配对齐全'}")
    for kw in ["Warping to Farm", "ERROR", "Disconnected", "ClosedGame", "Disposing", "soft_oal", "Exception", "GET /v1/observe"]:
        print(f"  {kw:20} = {sum(1 for _i, _t, s in inwin if kw in s)}")

    jobs = [
        ("verify-run3", [PY, "-X", "utf8", os.path.join(ROOT, "tools", "verify-run3.py"),
                         "--journal", JOURNAL, "--days", "3", "--json"],
         os.path.join(ROOT, "logs", "runB-0732-verify.txt")),
        ("analyze-longrun", [PY, "-X", "utf8", os.path.join(ROOT, "tools", "analyze-longrun.py"),
                             "--journal", JOURNAL, "--window", "3"],
         os.path.join(ROOT, "logs", "runB-0732-analyze.txt")),
        ("lead-check", [PY, "-X", "utf8", os.path.join(ROOT, "scratch", "run9-lead-check.py"),
                        "--journal", JOURNAL, "--snapshots", SNAPSHOTS, "--smapi", SMAPI_DST],
         os.path.join(ROOT, "logs", "runB-0732-lead-check.txt")),
    ]
    print("\n=== 检查器（run B 提前叫停，无 finish ⇒ 结论只作旁证）===")
    for name, cmd, out in jobs:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(r.stdout or "")
            if r.stderr:
                fh.write("\n--- stderr ---\n" + r.stderr)
        print(f"[{name}] rc={r.returncode} → {out}")
        for ln in [x for x in (r.stdout or "").splitlines() if x.strip()][-14:]:
            print("    " + ln[:190])
    return 0


if __name__ == "__main__":
    sys.exit(main())
