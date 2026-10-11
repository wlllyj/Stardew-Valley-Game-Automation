#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""造一份"应当判 VERIFIED"的合成 journal，用来证明 tools/verify-run3.py 不是只会报错的空检查。

只用于 Lead 侧自检（真机 journal 在 logs\\ 下）。
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "scratch", "journal-green.jsonl")

DAYS = [
    (["1", "spring", 10], ["1", "spring", 11]),
    (["1", "spring", 11], ["1", "spring", 12]),
    (["1", "spring", 12], ["1", "spring", 13]),
]

rows = []
for i, (start_day, end_day) in enumerate(DAYS):
    rows.append({"t": i * 600 + 1.0, "event": "day_start", "day": start_day,
                 "final": {"day": start_day, "stamina": 270.0, "crops": 32, "unwatered_crops": 32, "money": 200}})
    rows.append({"t": i * 600 + 5.0, "event": "decision", "day": start_day, "boundary": "new_day",
                 "source": "llm", "llm": True, "intents": [{"task": "water_area", "area_hint": "anchor:field_ne"}]})
    rows.append({"t": i * 600 + 300.0, "event": "stage", "day": start_day, "stage": "water_area",
                 "tiles": 32, "ok": 32, "skipped": 0, "failed": 0, "stopped": "", "leftover": 0})
    rows.append({"t": i * 600 + 500.0, "event": "sleep", "day": start_day, "ok": True,
                 "before": {"day": start_day, "timeOfDay": 2200}, "after": {"day": end_day, "timeOfDay": 600}})
    rows.append({"t": i * 600 + 520.0, "event": "day_end", "day": start_day, "ended_by": "sleep",
                 "ended_reason": "night:到点了", "verified": True,
                 "final": {"day": end_day, "timeOfDay": 600, "stamina": 270.0, "crops": 33,
                           "unwatered_crops": 0, "money": 200},
                 "checks": {"slept_by_us": True, "no_hard_failures": True, "crops_watered": True,
                            "day_justified": True, "no_unmet_stages": True},
                 "day_text": "spring 10：phase water_area...", "ok_steps": 32, "skipped_steps": 0,
                 "failed_steps": 0, "stages": [{"stage": "water_area", "leftover": 0, "ok": 32}],
                 "outcomes": [], "notes": []})

rows.append({"t": 1900.0, "event": "finish", "code": 0, "verified_streak": 3, "days": 3,
             "actions": 96, "minutes": 31.6})

with open(OUT, "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"wrote {OUT} ({len(rows)} rows)")
