# -*- coding: utf-8 -*-
"""run 收尾取证（只读，参数化版）：
1) 冻结 SMAPI-latest.txt → logs\\<tag>-smapi-window.txt（一次性读源→写副本→双侧 SHA256）
2) 窗口内六串计数 + 行号（NewDay / before save / Save called(含 L16 判别) / Save task / completed / after save）
   + Warping to Farm / 噪声关键词
3) 用 python subprocess(encoding="utf-8") 跑三个检查器，输出落 logs\\<tag>-*.txt 并打印 rc 与判决行

参数化（mechanical 改造，默认值保持 run9d 原行为）：
  python scratch\\run9d-tools.py                            # 等价原行为（tag=run9d）
  python scratch\\run9d-tools.py --tag runA5-0739 --journal logs/longrun-runA5-0739.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PY = sys.executable
SMAPI_SRC = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")

TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> int:
    ap = argparse.ArgumentParser(description="run 收尾取证（默认保持 run9d 原行为）")
    ap.add_argument("--tag", default="run9d", help="产物前缀（默认 run9d）")
    ap.add_argument("--journal", default=None, help="账本（默认 logs/longrun-3day-llm-<tag>.jsonl）")
    ap.add_argument("--smapi", default=None, help="SMAPI 副本（默认 logs/<tag>-smapi-window.txt）")
    ap.add_argument("--snapshots", default=None, help="外部快照（默认 scratch/<tag>-external-snapshots.jsonl）")
    ap.add_argument("--after", default=None, help="窗口起点 HH:MM:SS（默认整文件首个时间戳）")
    ap.add_argument("--before", default=None, help="窗口终点 HH:MM:SS（默认整文件末个时间戳）")
    ap.add_argument("--days", type=int, default=5, help="verify-run3 --days（默认 5）")
    ap.add_argument("--window", type=int, default=5, help="analyze-longrun --window（默认 5）")
    args = ap.parse_args()

    tag = args.tag
    smapi_dst = args.smapi or os.path.join(ROOT, "logs", f"{tag}-smapi-window.txt")
    journal = args.journal or os.path.join(ROOT, "logs", f"longrun-3day-llm-{tag}.jsonl")
    snapshots = args.snapshots or os.path.join(ROOT, "scratch", f"{tag}-external-snapshots.jsonl")

    # 1) 冻结：一次性读源 → 用同一份字节写副本 → 双侧 SHA256
    print("=== SMAPI 冻结 ===")
    if not os.path.exists(SMAPI_SRC):
        print(f"!! 源不存在：{SMAPI_SRC}", file=sys.stderr)
        return 12
    with open(SMAPI_SRC, "rb") as fh:
        src_bytes = fh.read()
    with open(smapi_dst, "wb") as fh:
        fh.write(src_bytes)
    st = os.stat(smapi_dst)
    src_sha = hashlib.sha256(src_bytes).hexdigest().upper()
    dst_sha = sha256(smapi_dst)
    print(f"src = {SMAPI_SRC}")
    print(f"dst = {smapi_dst}")
    print(f"size = {st.st_size} B / mtime = {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))} / sha256 = {dst_sha}")
    print(f"src sha256 = {src_sha}（与 dst 一致 = {src_sha == dst_sha}）")

    # 2) 六串计数
    lines = open(smapi_dst, encoding="utf-8", errors="replace").read().splitlines()
    if args.after is None or args.before is None:
        stamps = [TS.match(s).group(1) for s in lines if TS.match(s)]
        args.after = args.after or (stamps[0] if stamps else "00:00:00")
        args.before = args.before or (stamps[-1] if stamps else "23:59:59")
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
                         "--journal", journal, "--days", str(args.days), "--json"],
         os.path.join(ROOT, "logs", f"{tag}-verify.txt")),
        ("analyze-longrun", [PY, "-X", "utf8", os.path.join(ROOT, "tools", "analyze-longrun.py"),
                             "--journal", journal, "--window", str(args.window)],
         os.path.join(ROOT, "logs", f"{tag}-analyze.txt")),
        ("lead-check", [PY, "-X", "utf8", os.path.join(ROOT, "scratch", "run9-lead-check.py"),
                        "--journal", journal, "--snapshots", snapshots, "--smapi", smapi_dst],
         os.path.join(ROOT, "logs", f"{tag}-lead-check.txt")),
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
