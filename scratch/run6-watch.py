# -*- coding: utf-8 -*-
"""run6 短回合只读监视器：在**一个**受预算约束的调用里轮询，发现结束就提前返回。

    python scratch\\run6-watch.py --minutes 4 [--interval 15]
    python scratch\\run6-watch.py --once          # 只取一次状态（起跑后 90 秒汇报用）

退出码：0=预算用尽仍在跑；10=账本出现 finish；11=PID 消失；12=找不到 PID 文件（还没起跑/已被清理）。
只读：进程存活 / 账本行数与末事件 / console 行数与尾行 / err 字节数 / 存档 size+mtime / 桥 modVersion。

复用（run7 等）：传 `--journal logs\\longrun-3day-llm-run7.jsonl` 即自动把 console / err / PID 候选
（`<journal>.pid` → `logs\\run7.pid`）都按它推导；`--pid-file` 仍可显式覆盖。

路径按 `tools\\start-detached-longrun.py` 的真实落盘规则：
    PID     logs\\longrun-3day-llm-run6.pid（回退 logs\\run6.pid）
    console logs\\longrun-3day-llm-run6.console.log / …console.err.log
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
PID_CANDIDATES = (REPO / "logs" / "longrun-3day-llm-run6.pid", REPO / "logs" / "run6.pid")
JOURNAL = REPO / "logs" / "longrun-3day-llm-run6.jsonl"
CONSOLE = REPO / "logs" / "longrun-3day-llm-run6.console.log"
ERR = REPO / "logs" / "longrun-3day-llm-run6.console.err.log"
RUN6_JOURNAL = JOURNAL  # argparse 默认值用（避免在 global 声明之前引用 JOURNAL）
SAVE_DIR = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"
SAVE = SAVE_DIR / "Wahaha_450799035"
BRIDGE = Path(os.environ["APPDATA"]) / "StardewValley" / "AgentFarm" / "bridge.json"


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


def mod_version() -> str:
    try:
        return str(json.loads(BRIDGE.read_text(encoding="utf-8", errors="replace")).get("modVersion"))
    except (OSError, json.JSONDecodeError):
        return "?"


def sample(t0: float) -> tuple[bool, int, str | None, dict | None, str]:
    n, last, fin = journal_state()
    cl = CONSOLE.read_text(encoding="utf-8", errors="replace").splitlines() if CONSOLE.exists() else []
    err = ERR.stat().st_size if ERR.exists() else -1
    try:
        st = SAVE.stat()
        save = f"{st.st_size}/{time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}"
    except OSError:
        save = "?"
    line = (f"t+{time.time() - t0:5.1f}s journal={n}行 last={last} console={len(cl)}行 err={err}B "
            f"save={save} mod={mod_version()}")
    if cl:
        line += f"\n        console尾: {cl[-1][:200]}"
    if err > 0:
        try:
            e = ERR.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
            line += "\n        err尾: " + " | ".join(x[:160] for x in e)
        except OSError:
            pass
    return True, n, last, fin, line


def main() -> int:
    global JOURNAL, CONSOLE, ERR, PID_CANDIDATES
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=4.0)
    ap.add_argument("--interval", type=float, default=15.0)
    ap.add_argument("--once", action="store_true", help="只采样一次（起跑后 90 秒汇报用）")
    ap.add_argument("--journal", default=str(RUN6_JOURNAL),
                    help="长跑账本路径；console/err/PID 候选都按它推导（默认 run6 的账本）")
    ap.add_argument("--pid-file", default="", help="留空则自动认 <journal>.pid → logs\\run6.pid")
    args = ap.parse_args()

    # 允许重复用于其它 run：按 --journal 重算 console / err / PID 候选
    JOURNAL = Path(args.journal)
    CONSOLE = JOURNAL.with_suffix(".console.log")
    ERR = JOURNAL.with_suffix(".console.err.log")
    short = JOURNAL.stem.replace("longrun-3day-llm-", "")
    PID_CANDIDATES = (JOURNAL.with_suffix(".pid"), REPO / "logs" / f"{short}.pid")

    pid_file = Path(args.pid_file) if args.pid_file else next((p for p in PID_CANDIDATES if p.exists()), None)
    if pid_file is None or not pid_file.exists():
        print(f"[x] 找不到 PID 文件（候选：{' / '.join(str(p) for p in PID_CANDIDATES)}）—— 还没起跑，或已被清理")
        return 12
    pid = int(pid_file.read_text(encoding="utf-8").strip())
    print(f"PID 文件 {pid_file} → pid={pid} / alive={alive(pid)}")

    t0 = time.time()
    if args.once:
        _, n, last, fin, line = sample(t0)
        print(line)
        if fin is not None:
            print("*** FINISH ***\n" + json.dumps(fin, ensure_ascii=False))
            return 10
        if not alive(pid):
            print("*** PID_GONE ***")
            return 11
        return 0

    deadline = t0 + args.minutes * 60
    last_sig = None
    while True:
        a = alive(pid)
        _, n, last, fin, line = sample(t0)
        sig = (a, n, last, line)
        if sig != last_sig:
            print(("alive=True  " if a else "alive=False ") + line)
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
