# -*- coding: utf-8 -*-
"""A″/B″ 有界等待（只读）：等下一次 day_end 或 finish 或 PID 消失。

退出码：0 = 观察到新的 day_end；10 = 出现 finish；11 = PID 消失；12 = 预算用尽仍在跑。
用法：
  python scratch\\_runA8_wait.py --journal logs\\longrun-runA8-0743.jsonl --minutes 5
  （--target-day-end 可显式指定要等到的 day_end 条数；默认 当前条数+1）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOGS = os.path.join(ROOT, "logs")


def load(path: str) -> list[dict]:
    recs = []
    if not os.path.exists(path):
        return recs
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                try:
                    recs.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    continue
    return recs


def pid_alive(pid: int | None) -> bool | None:
    if not pid:
        return None
    try:
        out = os.popen(f'tasklist /FI "PID eq {pid}" /FO CSV /NH').read()
        return str(pid) in out
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=os.path.join(LOGS, "longrun-runA8-0743.jsonl"))
    ap.add_argument("--pid-file", default=os.path.join(LOGS, "longrun-runA8-0743.pid"))
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--interval", type=float, default=20.0)
    ap.add_argument("--target-day-end", type=int, default=None)
    args = ap.parse_args()

    pid = None
    if os.path.exists(args.pid_file):
        try:
            pid = int(open(args.pid_file, encoding="utf-8").read().strip())
        except Exception:  # noqa: BLE001
            pid = None

    recs0 = load(args.journal)
    de0 = sum(1 for r in recs0 if r.get("event") == "day_end")
    target = args.target_day_end if args.target_day_end is not None else de0 + 1
    t0 = time.time()
    deadline = t0 + args.minutes * 60
    print(f"等第 {target} 条 day_end（现有 {de0} 条）/ finish / PID {pid} 消失；预算 {args.minutes} 分钟", flush=True)
    while time.time() < deadline:
        recs = load(args.journal)
        de = [r for r in recs if r.get("event") == "day_end"]
        fin = [r for r in recs if r.get("event") == "finish"]
        alive = pid_alive(pid)
        last = recs[-1] if recs else {}
        print(f"  t+{time.time() - t0:5.1f}s  lines={len(recs):4d}  day_end={len(de)}  "
              f"last={last.get('event')}@{last.get('t')}  pid_alive={alive}", flush=True)
        if fin:
            print("*** FINISH ***", json.dumps(fin[-1], ensure_ascii=False), flush=True)
            return 10
        if len(de) >= target:
            r = de[-1]
            print(f"*** 新 day_end #{len(de)}：day={r.get('day')} ended_by={r.get('ended_by')} "
                  f"verified={r.get('verified')} day_after={r.get('day_after')} "
                  f"ok/skip/fail={r.get('ok_steps')}/{r.get('skipped_steps')}/{r.get('failed_steps')}", flush=True)
            print("    ended_reason:", str(r.get("ended_reason"))[:200], flush=True)
            print("    checks:", json.dumps(r.get("checks"), ensure_ascii=False), flush=True)
            return 0
        if alive is False:
            print(f"*** PID {pid} 消失（无 finish）***，账本 {len(recs)} 行", flush=True)
            return 11
        time.sleep(args.interval)
    print(f"预算用尽仍在跑：账本 {len(load(args.journal))} 行", flush=True)
    return 12


if __name__ == "__main__":
    sys.exit(main())
