# -*- coding: utf-8 -*-
"""run4 账本取证（只读 logs\\longrun-3day-llm-run4.jsonl）。

打印 finish / day_start / day_end / sleep 的**原文 JSON**（供文档逐字引用）。
"""
from __future__ import annotations

import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
JL = os.path.join(REPO, "logs", "longrun-3day-llm-run4.jsonl")

recs = []
with open(JL, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            recs.append(json.loads(line))

print(f"文件 = {JL}")
print(f"行数 = {len(recs)}")

from collections import Counter

print(f"事件计数 = {dict(Counter(r.get('event') for r in recs))}")
print(f"点名事件 = {sorted({r.get('event') for r in recs})}")

for want in ("day_start", "day_end", "sleep", "finish", "day_cap", "no_day_progress",
             "blocked_modal", "modal_loop_capped", "watchdog_stop", "bridge_down"):
    hit = [(i, r) for i, r in enumerate(recs) if r.get("event") == want]
    if not hit:
        continue
    print(f"\n===== {want}（{len(hit)} 条）=====")
    for i, r in hit:
        print(f"--- #{i} ---")
        print(json.dumps(r, ensure_ascii=False, indent=2))

print("\n===== 末 5 条事件名 =====")
for i, r in enumerate(recs[-5:], start=len(recs) - 5):
    print(f"#{i} {r.get('event')} t={r.get('t')}")
