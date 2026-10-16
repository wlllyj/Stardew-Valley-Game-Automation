# -*- coding: utf-8 -*-
"""run B 提前叫停：留档停止点 + 保住 [60,29] 现场（只读游戏，不动游戏进程）。

产出：
- `scratch\\runB-0732-tile6029-live.json`：当前的 [60,29] 及四邻完整 tile 记录 + clock/player/farm/ui/liveness + 完整 observe
- 屏幕输出：停止点（PID 存活、账本行数、last 记录、逐日 day_end、是否有 finish、console/err 字节）
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "brain"))

from agentfarm.bridge import BridgeClient, pid_alive  # noqa: E402

JOURNAL = os.path.join(ROOT, "logs", "longrun-runB-0732.jsonl")
PIDFILE = os.path.join(ROOT, "logs", "longrun-runB-0732.pid")
CONSOLE = os.path.join(ROOT, "logs", "longrun-runB-0732.console.log")
CONSOLE_ERR = os.path.join(ROOT, "logs", "longrun-runB-0732.console.err.log")
OUT = os.path.join(ROOT, "scratch", "runB-0732-tile6029-live.json")
TARGETS = [(60, 29), (59, 29), (61, 29), (60, 28), (60, 30)]


def size_of(p: str) -> int:
    try:
        return os.path.getsize(p)
    except Exception:  # noqa: BLE001
        return -1


def main() -> int:
    pid = None
    if os.path.exists(PIDFILE):
        pid = int(open(PIDFILE, encoding="utf-8").read().strip())
    print("=== 停止点 ===")
    print(f"停止时刻（本脚本运行时刻） = {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    print(f"logs\\longrun-runB-0732.pid = {pid}；pid_alive = {pid_alive(pid) if pid else '?'}")
    print(f"console = {size_of(CONSOLE)} B；console.err = {size_of(CONSOLE_ERR)} B")

    recs = []
    with open(JOURNAL, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    print(f"账本行数 = {len(recs)}")
    last = recs[-1]
    print(f"last 记录 = {json.dumps(last, ensure_ascii=False)[:400]}")
    print(f"last t = {last.get('t')}；last event = {last.get('event')}")
    fin = [r for r in recs if r.get("event") == "finish"]
    print(f"finish 记录数 = {len(fin)} {'（没有 finish 行 —— 如实记录，不补造）' if not fin else json.dumps(fin[0], ensure_ascii=False)}")
    days = [r for r in recs if r.get("event") == "day_end"]
    print(f"\nday_end 共 {len(days)} 条：")
    for r in days:
        fin_w = r.get("final_water") or {}
        print(f"  t={r.get('t')} day={r.get('day')} ended_by={r.get('ended_by')} verified={r.get('verified')} "
              f"day_after={r.get('day_after')} ok={r.get('ok_steps')} skip={r.get('skipped_steps')} fail={r.get('failed_steps')} "
              f"final_water(dry={fin_w.get('dry')}/{fin_w.get('crops')}) "
              f"checks={json.dumps(r.get('checks'), ensure_ascii=False)}")
        print(f"      reason={(r.get('ended_reason') or '')[:220]}")
    ds = [r for r in recs if r.get("event") == "day_start"]
    print(f"\nday_start 共 {len(ds)} 条：")
    for r in ds:
        print(f"  t={r.get('t')} day={r.get('day')} money={r.get('money')} loc={r.get('location')} crops={r.get('crops')}")

    c = BridgeClient()
    o = c.observe("full")
    loc = o.get("location") or {}
    idx = {}
    for t in loc.get("tiles") or []:
        tv = t.get("tile")
        if isinstance(tv, list) and len(tv) == 2:
            idx[(tv[0], tv[1])] = t
    tiles = {f"{x},{y}": idx.get((x, y)) for x, y in TARGETS}
    print("\n=== 现场（保住 [60,29] 作修复后对照基线）===")
    print(f"clock = {json.dumps(o.get('clock'), ensure_ascii=False)}")
    print(f"player = {json.dumps({k: (o.get('player') or {}).get(k) for k in ('name','location','tile','stamina','money','isInBed','farmingLevel')}, ensure_ascii=False)}")
    print(f"farm = {json.dumps({k: (o.get('farm') or {}).get(k) for k in ('crops','ripeCrops','unwateredCrops','dryCrops','deadCrops','hoeDirt','emptyDirt','complete','scanSeq')}, ensure_ascii=False)}")
    for k, v in tiles.items():
        print(f"  tile {k} {'在窗口内' if v else '**不在窗口内**'}：{json.dumps(v, ensure_ascii=False)}")

    payload = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "purpose": "run B 提前叫停时的 [60,29] 现场；作为 harvest 修复后的同格前后对照基线",
        "journal_lines": len(recs),
        "journal_last_t": last.get("t"),
        "journal_last_event": last.get("event"),
        "finish_records": len(fin),
        "brain_pid": pid,
        "brain_pid_alive": pid_alive(pid) if pid else None,
        "console_bytes": size_of(CONSOLE),
        "console_err_bytes": size_of(CONSOLE_ERR),
        "clock": o.get("clock"),
        "liveness": o.get("liveness"),
        "ui": o.get("ui"),
        "player": o.get("player"),
        "farm": o.get("farm"),
        "target_tiles": tiles,
        "observe_full": o,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    print(f"\n已落 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
