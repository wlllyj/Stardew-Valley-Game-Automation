#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""task-38 证据：造两本"睡后重取观测"的账本（`day_after` = +1 天 / +2 天，且 `final` 故意
留在睡前那一天），同时喂给 `tools/analyze-longrun.py` 与 `tools/verify-run3.py`，核对跨日一栏是否同向。

只写 `scratch\\`（本 agent 的写范围）。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DAY = [1, "spring", 12]


def ledger(after):
    return [
        {"event": "day_start", "t": 1.0, "day": DAY, "timeOfDay": 610, "stamina": 270.0, "money": 100},
        {"event": "decision", "t": 2.0, "day": DAY, "source": "deterministic", "llm": False,
         "intents": [{"task": "water_area", "area_hint": "field_ne", "reason": "浇水"}], "problems": []},
        {"event": "outcome", "t": 3.0, "kind": "water_area", "terminal": "VERIFIED",
         "postcondition_met": True,
         "reason": "作业区 field_ne；目标 1 步：做成 1、跳过 0、失败 0；后置条件成立", "detail": []},
        {"event": "sleep", "t": 8.0, "ok": True, "code": "ok",
         "reason": "night:时间 2210 已经到夜里（≥2200）"},
        {"event": "day_end", "t": 9.0, "day": DAY, "day_text": "1年 spring 12日", "ended_by": "sleep",
         "ended_reason": "night:时间 2210 已经到夜里（≥2200）", "verified": True,
         "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                    "no_unmet_stages": True, "crops_watered": True, "watered_outdoor": True,
                    "day_justified": True},
         "stages": [], "outcomes": [], "ok_steps": 0, "skipped_steps": 0, "failed_steps": 0, "notes": [],
         # final = 睡前快照，故意停在当天（真机 0.7.23 彩排就是这么写的）
         "final": {"day": DAY, "timeOfDay": 2200, "location": "Farm", "stamina": 40.0, "money": 100,
                   "isInBed": False, "crops": 31, "unwatered_crops": 0, "ripe": 0, "tillable": 0,
                   "waterLeft": 10, "seeds": []},
         "final_water": {"t": 8.5, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0, "scope": "farm"},
         "day_after": after},
        {"event": "finish", "t": 10.0, "code": 0, "verified_streak": 3, "actions": 5, "minutes": 1.0,
         "stages_seen": ["water_area"], "days": 3},
    ]


def write(name, events):
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print("wrote", path, len(events), "events")


write("_ledger_dayafter_ok.jsonl", ledger([1, "spring", 13]))
write("_ledger_dayafter_bad.jsonl", ledger([1, "spring", 14]))
