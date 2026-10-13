# -*- coding: utf-8 -*-
"""run4 账本精炼取证（只读）：写 logs\\run4-journal-extract.txt，供文档逐字引用。"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
JL = os.path.join(REPO, "logs", "longrun-3day-llm-run4.jsonl")
OUT = os.path.join(REPO, "logs", "run4-journal-extract.txt")

recs = []
with open(JL, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            recs.append(json.loads(line))

L: list[str] = []
ap = L.append

ap(f"文件 = {JL}")
ap(f"行数 = {len(recs)}")
ap(f"事件计数 = {dict(Counter(r.get('event') for r in recs))}")

for i, r in enumerate(recs):
    ev = r.get("event")
    if ev == "day_start":
        ap(f"\n===== day_start #{i} 原文 =====")
        ap(json.dumps(r, ensure_ascii=False, indent=2))

for i, r in enumerate(recs):
    if r.get("event") != "day_end":
        continue
    ap(f"\n===== day_end #{i} 关键字段（原文片段）=====")
    ap(f"t={r.get('t')} day={r.get('day')} day_text={r.get('day_text')} started_at={r.get('started_at')}")
    ap(f"ended_by={r.get('ended_by')} verified={r.get('verified')} day_after={r.get('day_after')}")
    ap(f"ended_reason=\n{r.get('ended_reason')}")
    ap(f"checks={json.dumps(r.get('checks'), ensure_ascii=False)}")
    ap(f"final={json.dumps(r.get('final'), ensure_ascii=False)}")
    ap(f"final_water={json.dumps(r.get('final_water'), ensure_ascii=False)}")
    ap(f"ok_steps={r.get('ok_steps')} skipped_steps={r.get('skipped_steps')} failed_steps={r.get('failed_steps')}")
    ap(f"failed_steps 明细={json.dumps(r.get('failed_steps'), ensure_ascii=False)[:800]}")
    ap(f"notes={json.dumps(r.get('notes'), ensure_ascii=False)[:600]}")
    st = r.get("stages") or []
    agg: dict[str, Counter] = defaultdict(Counter)
    for s in st:
        c = agg[s.get("stage")]
        for k in ("tiles", "ok", "skipped", "failed", "failed_any", "proven_inert", "env_block", "inconclusive", "leftover"):
            c[k] += s.get(k) or 0
        if s.get("stopped"):
            c[f"stopped:{s['stopped']}"] += 1
    ap(f"stages 段数={len(st)}；按 stage 汇总：")
    for name, c in agg.items():
        ap(f"   {name}: {dict(c)}")
    ap(f"plots 数={len(r.get('plots') or [])}")
    for p in (r.get("plots") or []):
        ap(f"   plot {p.get('zone')} anchor={p.get('anchor')} tiles={p.get('tiles')}")

for i, r in enumerate(recs):
    if r.get("event") in ("sleep", "finish", "day_cap", "no_day_progress"):
        ap(f"\n===== {r.get('event')} #{i} 原文 =====")
        ap(json.dumps(r, ensure_ascii=False, indent=2))

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")
print(f"written {OUT} ({len(L)} lines)")
