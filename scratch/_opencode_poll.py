# -*- coding: utf-8 -*-
"""只读轮询长跑：PID 存活 / 账本行数 / 尾条 / console 尾部。绝不写账本、绝不碰游戏。"""
import ctypes
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = "longrun-trial-opencode-1"
journal = ROOT / "logs" / f"{TAG}.jsonl"
pidf = ROOT / "logs" / f"{TAG}.pid"
console = ROOT / "logs" / f"{TAG}.console.log"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def alive(pid: int) -> bool:
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
    if not h:
        return False
    ctypes.windll.kernel32.CloseHandle(h)
    return True


pid = int(pidf.read_text(encoding="ascii").strip())
print(f"脑 PID={pid}  guardian 见 logs/{TAG}-guardian.pid")

ROUNDS = 9
for i in range(ROUNDS):
    time.sleep(60)
    lines = [ln for ln in journal.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    kinds = []
    for ln in lines:
        try:
            kinds.append(json.loads(ln).get("event") or json.loads(ln).get("kind") or "?")
        except Exception:
            kinds.append("?")
    tail = lines[-1][:220] if lines else ""
    fin = [k for k in kinds if k == "finish"]
    day_end = [k for k in kinds if k == "day_end"]
    print(f"[+{(i+1)*60:>4}s] alive={alive(pid)} lines={len(lines)} day_end={len(day_end)} finish={len(fin)}")
    print(f"          尾条: {tail}")
    if fin or not alive(pid):
        print("=> 结束（finish 出现或进程消失）")
        break

print("=== console 尾部 15 行 ===")
if console.exists():
    for ln in console.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]:
        print("  " + ln)
