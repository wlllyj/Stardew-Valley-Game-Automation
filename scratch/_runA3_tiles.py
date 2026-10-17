# -*- coding: utf-8 -*-
"""逐格计数：outcome[kind=harvest] 的 detail 是 per-tile 列表 ⇒ 统计"被背包满拒收的格数"。"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

JL = sys.argv[1] if len(sys.argv) > 1 else os.path.join("logs", "longrun-runA3-0736.jsonl")
recs = [json.loads(l) for l in open(JL, encoding="utf-8") if l.strip()]

tiles_full = 0
recs_full = 0
tiles_other = 0
by_day = Counter()
for r in recs:
    if r.get("event") != "outcome" or r.get("kind") != "harvest":
        continue
    det = r.get("detail") or []
    if isinstance(det, str):
        det = [det]
    n_full = sum(1 for d in det if "背包满" in str(d))
    if n_full:
        recs_full += 1
        tiles_full += n_full
        by_day[tuple(r.get("day") or [])] += n_full
    tiles_other += len(det) - n_full

print(f"outcome[kind=harvest] 记录 = {sum(1 for r in recs if r.get('event') == 'outcome' and r.get('kind') == 'harvest')}")
print(f"含『背包满』的记录 = {recs_full}；**逐格计数 = {tiles_full} 格**（每条 detail 是一格）")
print(f"其它 harvest detail 格数 = {tiles_other}")
print(f"按 day 分布：{dict(by_day)}")

gu = [r for r in recs if r.get("event") == "harvest_gave_up"]
print(f"\nharvest_gave_up = {len(gu)} 条；attempts 分布 = {dict(Counter(r.get('attempts') for r in gu))}")
print(f"涉及格数（去重）= {len({tuple(r.get('tile') or []) for r in gu})}")
bysay = Counter(tuple(r.get("day") or []) for r in gu)
print(f"按 day：{dict(bysay)}")

ss = [r for r in recs if r.get("event") == "stage_stop_named" and r.get("stage") == "harvest"]
print(f"\nstage_stop_named[harvest] = {len(ss)}；assigned 合计 = {sum(r.get('assigned') or 0 for r in ss)}，"
      f"undone 合计 = {sum(r.get('assigned_undone') or 0 for r in ss)}")
print(f"zone 分布 = {dict(Counter(r.get('zone') for r in ss))}")

o = [r for r in recs if r.get("event") == "outcome" and r.get("kind") == "harvest"]
print(f"\n其余 {len(o) - recs_full} 条 harvest outcome 的 detail 摘要：")
for r in o:
    det = r.get("detail") or []
    if isinstance(det, str):
        det = [det]
    if not any("背包满" in str(d) for d in det):
        print(f"  t={r.get('t')} day={r.get('day')} n={len(det)} 首条={str(det[0])[:120] if det else ''}")
