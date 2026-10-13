# -*- coding: utf-8 -*-
"""run5 短回合只读监视器：在**一个**受预算约束的调用里轮询，发现结束就提前返回。

    python scratch\\run5-watch.py --minutes 4 [--interval 15]

退出码：0=预算用尽仍在跑；10=账本出现 finish；11=PID 消失（进程退出）。
只读：进程存活 / 账本行数与事件 / console 行数 / err 大小 / 存档 mtime。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
PID_FILE = REPO / "logs" / "run5.pid"
JOURNAL = REPO / "logs" / "longrun-3day-llm-run5.jsonl"
CONSOLE = REPO / "logs" / "run5-console.log"
ERR = REPO / "logs" / "run5-console.err.log"
SAVE = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035" / "Wahaha_450799035"


def alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                         capture_output=True, text=True, timeout=15)
    return str(pid) in (out.stdout or "")


def journal_state() -> tuple[int, str | None, dict | None]:
    if not JOURNAL.exists():
        return 0, None, None
    rows = [ln for ln in JOURNAL.read_text(encoding="utf-8").splitlines() if ln.strip()]
    last = fin = None
    for ln in rows:
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        last = r.get("event")
        if r.get("event") == "finish":
            fin = r
    return len(rows), last, fin


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=4.0)
    ap.add_argument("--interval", type=float, default=15.0)
    args = ap.parse_args()

    pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    t0 = time.time()
    deadline = t0 + args.minutes * 60
    last_sig = None
    while True:
        a = alive(pid)
        n, last, fin = journal_state()
        cl = CONSOLE.read_text(encoding="utf-8", errors="replace").splitlines() if CONSOLE.exists() else []
        err = ERR.stat().st_size if ERR.exists() else -1
        try:
            st = SAVE.stat()
            save = f"{st.st_size}/{time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}"
        except OSError:
            save = "?"
        sig = (a, n, last, len(cl), err, save)
        if sig != last_sig:
            print(f"t+{time.time() - t0:5.1f}s alive={a} journal={n} last={last} console={len(cl)}行 err={err}B save={save}")
            if cl:
                print(f"        console尾: {cl[-1][:160]}")
            last_sig = sig
        if fin is not None:
            print("\n*** FINISH ***")
            print(json.dumps(fin, ensure_ascii=False))
            return 10
        if not a:
            print("\n*** PID_GONE ***")
            return 11
        if time.time() >= deadline:
            print(f"\n预算 {args.minutes} 分钟用尽：仍在跑（PID {pid} 存活，账本 {n} 行）")
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
