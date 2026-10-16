# -*- coding: utf-8 -*-
"""逐日摘要（任意账本）：事件计数 / day_start / day_end 全字段 / finish-day_cap。

用法：python scratch\\run9d-days.py <journal 路径>
只读，不碰桥。
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
jl = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "logs", "longrun-3day-llm-run9d.jsonl")

recs = []
with open(jl, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            recs.append(json.loads(line))

print(f"journal = {jl}")
print(f"行数 = {len(recs)}")
counts: dict[str, int] = {}
for r in recs:
    ev = r.get("event") or "?"
    counts[ev] = counts.get(ev, 0) + 1
print("事件计数 = " + json.dumps(counts, ensure_ascii=False, sort_keys=True))

print("\n=== 逐日 ===")
for i, r in enumerate(recs):
    ev = r.get("event")
    if ev == "day_start":
        f = r.get("final") or r
        print(f"#{i:4} day_start t={r.get('t')} day={r.get('day')} money={f.get('money')} "
              f"loc={f.get('location')} crops={f.get('crops')}")
    elif ev == "day_end":
        f = r.get("final") or {}
        fw = r.get("final_water") or {}
        chk = r.get("checks") or {}
        bad = [k for k, v in chk.items() if v is False]
        print(f"#{i:4} day_end   t={r.get('t')} day={r.get('day')} ended_by={r.get('ended_by')} "
              f"verified={r.get('verified')} day_after={r.get('day_after')} "
              f"ok={r.get('ok_steps')} skip={r.get('skipped_steps')} fail={r.get('failed_steps')}")
        print(f"       final.loc={f.get('location')} final.money={f.get('money')} tile={f.get('tile')} "
              f"tod={f.get('timeOfDay')} crops={f.get('crops')} unwatered={f.get('unwatered_crops')}")
        print(f"       final_water loc={fw.get('location')} tiles={fw.get('tiles')} crops={fw.get('crops')} dry={fw.get('dry')}")
        print(f"       坏判据={bad}")
        print(f"       reason={(r.get('ended_reason') or '')[:220]}")

print("\n=== 终点 / 异常 ===")
for i, r in enumerate(recs):
    if r.get("event") in ("finish", "day_cap", "no_day_progress", "slept_without_work",
                          "gave_up_dry", "blocked_modal", "stuck_flush", "watchdog_stop"):
        print(f"#{i:4} {json.dumps(r, ensure_ascii=False)[:420]}")
