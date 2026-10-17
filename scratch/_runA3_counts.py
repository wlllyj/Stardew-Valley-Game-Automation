# -*- coding: utf-8 -*-
"""run A′ 叫停：精确计数复核（只读账本）。用于核对 Lead 引用的数字口径。"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

JL = sys.argv[1] if len(sys.argv) > 1 else os.path.join("logs", "longrun-runA3-0736.jsonl")
recs = [json.loads(l) for l in open(JL, encoding="utf-8") if l.strip()]

PHRASE = "背包满"

print(f"总记录 {len(recs)}")

# 1) 任何位置提到「背包满」的记录，按 event 分组
hits = [(i, r) for i, r in enumerate(recs) if PHRASE in json.dumps(r, ensure_ascii=False)]
print(f"\n[1] 提到『{PHRASE}』的记录 = {len(hits)} 条，按 event：{dict(Counter(r.get('event') for _, r in hits))}")
out_hits = [(i, r) for i, r in hits if r.get("event") == "outcome"]
print(f"    其中 outcome = {len(out_hits)}；detail 样例：")
for i, r in out_hits[:3]:
    print(f"      #{i} t={r.get('t')} kind={r.get('kind')} ok={r.get('ok')} code={r.get('code')} detail={(r.get('detail') or '')[:110]}")

# 2) outcome 里 kind=harvest 的全量
oh = [(i, r) for i, r in enumerate(recs) if r.get("event") == "outcome" and r.get("kind") == "harvest"]
print(f"\n[2] outcome[kind=harvest] = {len(oh)} 条；ok 分布 = {dict(Counter(r.get('ok') for _, r in oh))}")
print(f"    其中含『{PHRASE}』= {sum(1 for _, r in oh if PHRASE in json.dumps(r, ensure_ascii=False))}；"
      f"code 分布 = {dict(Counter(r.get('code') for _, r in oh))}")
fails = [(i, r) for i, r in oh if r.get("ok") is False]
print(f"    ok=False = {len(fails)}；reason/detail 前 3：")
for i, r in fails[:3]:
    print(f"      #{i} t={r.get('t')} code={r.get('code')} reason={(r.get('reason') or '')[:70]} detail={(r.get('detail') or '')[:110]}")

# 3) harvest_gave_up
gu = [(i, r) for i, r in enumerate(recs) if r.get("event") == "harvest_gave_up"]
print(f"\n[3] harvest_gave_up = {len(gu)} 条；t 前 8 = {[r.get('t') for _, r in gu[:8]]}")
print(f"    tile/attempt 字段样例：{json.dumps(gu[0][1], ensure_ascii=False)[:300] if gu else 'N/A'}")

# 4) stage_stop_named 按 stage
ss = [(i, r) for i, r in enumerate(recs) if r.get("event") == "stage_stop_named"]
print(f"\n[4] stage_stop_named = {len(ss)} 条，按 stage：{dict(Counter(r.get('stage') for _, r in ss))}")
h = [(i, r) for i, r in ss if r.get("stage") == "harvest"]
print(f"    stage=harvest = {len(h)}；样例：{json.dumps(h[0][1], ensure_ascii=False)[:260] if h else 'N/A'}")

# 5) 经济：sell / surplus_sell / buy / ship
for ev in ("sell", "surplus_sell", "surplus_sell_skip", "sell_failed", "buy", "cannot_afford", "refill"):
    rows = [r for r in recs if r.get("event") == ev]
    if rows:
        print(f"\n[5] {ev} = {len(rows)} 条；样例 {json.dumps(rows[0], ensure_ascii=False)[:220]}")

# 6) day_end 的 ended_reason 是否含 stuck
de = [r for r in recs if r.get("event") == "day_end"]
print(f"\n[6] day_end = {len(de)}，ended_by={dict(Counter(r.get('ended_by') for r in de))}，"
      f"verified={dict(Counter(r.get('verified') for r in de))}，reason 以 stuck: 开头 = {sum(1 for r in de if (r.get('ended_reason') or '').startswith('stuck'))}")

# 7) 钱与日进度（从 day_start 的 final.money 或 buy/sell 记录里找）
print("\n[7] 逐日 day_start 的 final.money / clock：")
for i, r in enumerate(recs):
    if r.get("event") == "day_start":
        f = r.get("final") or {}
        print(f"    #{i} t={r.get('t')} day={r.get('day')} money={f.get('money')} stamina={f.get('stamina')} "
              f"location={(f.get('location') or {}).get('name') if isinstance(f.get('location'), dict) else f.get('location')} "
              f"crops={f.get('crops')} seeds={f.get('seeds')}")
