# -*- coding: utf-8 -*-
"""run A′（提前叫停）账本摘要 —— 只读 logs\\longrun-runA3-0736.jsonl。

输出：总行数 / 是否有 finish（必须为无）/ day_start 与 day_end 表 / 关键事件计数 /
"背包满" harvest 失败计数与时间戳样例 / 末条记录。
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

JL = sys.argv[1] if len(sys.argv) > 1 else os.path.join("logs", "longrun-runA3-0736.jsonl")

recs = []
with open(JL, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            recs.append(json.loads(line))

print(f"账本 = {JL}")
print(f"总记录 = {len(recs)}")
fin = [r for r in recs if r.get("event") == "finish"]
print(f"finish 条数 = {len(fin)}" + ("（无 finish ⇒ 提前叫停）" if not fin else f"：{json.dumps(fin[-1], ensure_ascii=False)}"))

ev = Counter(r.get("event") for r in recs)
print("\n=== 事件计数（降序）===")
print(", ".join(f"{k} {v}" for k, v in ev.most_common()))

print("\n=== day_start ===")
for i, r in enumerate(recs):
    if r.get("event") != "day_start":
        continue
    fin_d = r.get("final") or {}
    print(f"#{i:4} t={r.get('t')} day={r.get('day')} loc={(fin_d.get('location') or {}).get('name') if isinstance(fin_d.get('location'), dict) else fin_d.get('location')} "
          f"clock={fin_d.get('clock')} crops_w={fin_d.get('crops')}")

print("\n=== day_end ===")
for i, r in enumerate(recs):
    if r.get("event") != "day_end":
        continue
    fin_d = r.get("final") or {}
    fw = r.get("final_water") or {}
    print(f"#{i:4} t={r.get('t')} day={r.get('day')} ended_by={r.get('ended_by')} verified={r.get('verified')} "
          f"ok={r.get('ok_steps')} skip={r.get('skipped_steps')} fail={r.get('failed_steps')} day_after={r.get('day_after')}")
    print(f"      final_water: dry={fw.get('dry')}/{fw.get('crops')} scope={fw.get('scope')} tiles={fw.get('tiles')}")
    print(f"      checks={json.dumps(r.get('checks'), ensure_ascii=False)}")
    print(f"      ended_reason={(r.get('ended_reason') or '')[:220]}")
    st = r.get("stages") or []
    print(f"      stages({len(st)})=" + json.dumps(st, ensure_ascii=False)[:400])

print("\n=== 关键计数 ===")
harvest_fail, full_msgs = [], []
buy, sell, ship, surplus, water_far, gave_up, stuck = 0, 0, 0, 0, 0, 0, 0
for i, r in enumerate(recs):
    e = r.get("event")
    blob = json.dumps(r, ensure_ascii=False)
    if e == "buy":
        buy += 1
    if e in ("sell", "surplus_sell"):
        sell += 1
    if e == "ship":
        ship += 1
    if e == "surplus_sell":
        surplus += 1
    if e == "water_far":
        water_far += 1
    if e == "harvest_gave_up":
        gave_up += 1
    if isinstance(e, str) and e.startswith("stuck"):
        stuck += 1
    if "背包满" in blob:
        full_msgs.append((i, r.get("t"), r.get("event"), (r.get("kind") or r.get("detail") or "")[:60]))
    if r.get("kind") == "harvest" and r.get("ok") is False:
        harvest_fail.append((i, r.get("t"), (r.get("reason") or r.get("detail") or "")[:90]))

print(f"buy={buy} sell/surplus_sell={sell}（surplus={surplus}）ship={ship} water_far={water_far} harvest_gave_up={gave_up} stuck*={stuck}")
print(f"含『背包满』的记录 = {len(full_msgs)} 条；前 12 个 (idx,t,event)：{full_msgs[:12]}")
print(f"harvest 且 ok=False 的记录 = {len(harvest_fail)}；前 6 个：")
for row in harvest_fail[:6]:
    print(f"   #{row[0]} t={row[1]} {row[2]}")

print("\n=== 末 3 条 ===")
for r in recs[-3:]:
    print(json.dumps(r, ensure_ascii=False)[:600])
