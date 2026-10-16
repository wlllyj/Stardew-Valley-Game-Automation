# -*- coding: utf-8 -*-
"""run9c 账本逐日摘要（只读，不碰桥）。

用法：python scratch\\run9c-days.py [账本路径]
输出：行数、事件计数、逐日 day_start/day_end（checks/final_water/ended_reason）、
      finish/no_day_progress/slept_without_work/gave_up_dry/stuck_flush 原文、
      sell/surplus_sell/buy/buy_partial/cannot_afford/seed_unavailable_today 原文（截断）。
"""
from __future__ import annotations

import collections
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
JL = os.path.join(ROOT, "logs", "longrun-3day-llm-run9c.jsonl")
if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
    JL = sys.argv[1]

rows = [json.loads(l) for l in open(JL, encoding="utf-8") if l.strip()]
print(f"journal = {JL}")
print(f"行数 = {len(rows)}")
cnt = collections.Counter(r.get("event") for r in rows)
print("事件计数 = " + json.dumps(dict(sorted(cnt.items(), key=lambda kv: -kv[1])), ensure_ascii=False))

print("\n=== 逐日 ===")
for i, r in enumerate(rows):
    e = r.get("event")
    if e == "day_start":
        print(f"#{i:4} day_start t={r.get('t')} day={r.get('day')} money={r.get('money')} seeds={r.get('seeds')} "
              f"location={r.get('location')} crops={r.get('crops')}")
    elif e == "day_end":
        print(f"#{i:4} day_end t={r.get('t')} day={r.get('day')} ended_by={r.get('ended_by')} "
              f"verified={r.get('verified')} day_after={r.get('day_after')} "
              f"ok={r.get('ok_steps')} skip={r.get('skipped_steps')} fail={r.get('failed_steps')}")
        print(f"      checks={json.dumps(r.get('checks'), ensure_ascii=False)}")
        print(f"      final_water={json.dumps(r.get('final_water'), ensure_ascii=False)[:400]}")
        print(f"      reason={(r.get('ended_reason') or '')[:240]}")

print("\n=== 终点/异常事件 ===")
for i, r in enumerate(rows):
    if r.get("event") in ("finish", "no_day_progress", "slept_without_work", "gave_up_dry",
                          "stuck_flush", "review_only_fallback", "plot_exhausted_burst"):
        print(f"#{i:4} {json.dumps(r, ensure_ascii=False)[:400]}")

print("\n=== 经济闭环 ===")
for name in ("sell", "surplus_sell", "buy", "buy_partial", "cannot_afford", "seed_unavailable_today",
             "plant", "sow"):
    sel = [r for r in rows if r.get("event") == name]
    print(f"[{name}] {len(sel)} 条")
    for r in sel[:10]:
        print("    " + json.dumps(r, ensure_ascii=False)[:300])
