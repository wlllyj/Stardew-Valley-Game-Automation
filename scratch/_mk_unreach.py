#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""task-62 证据：造两本带 task-52 不可达字段的账本（上界内 / 越界），同时喂给
`tools/analyze-longrun.py` 与 `tools/verify-run3.py`，核对"不可达"一栏是否同向。

字段形状取自 dev-coder 的 task-52（commit `294daea`）：
  unreachable        = {event,tile,action,stage,zone,reason,note}
  unreachable_stage  = {event,stage,zone,tiles,in_leftover,coords,note}
  unreachable_summary= {event,count,bound,attempted,exempted,raw_unmet,unmet,tiles,note}
  day_end            = unreachable / unreachable_tiles / unreachable_bound / unreachable_exempt
  checks             = unreachable_within_bound / no_unmet_stages

只写 `scratch\\`（本 agent 的写范围）。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DAY = [1, "spring", 20]
NEXT = [1, "spring", 21]
COORDS = [[72, 51], [73, 51], [74, 51]]


def ledger(*, count, bound, attempted, exempted, raw_unmet, unmet, within_bound, verified,
           failed_steps, stage_failed, leftover, streak, code):
    return [
        {"event": "day_start", "t": 1.0, "day": DAY, "timeOfDay": 610, "stamina": 270.0, "money": 100},
        {"event": "decision", "t": 2.0, "day": DAY, "source": "deterministic", "llm": False,
         "intents": [{"task": "clear_area", "area_hint": "field_ne", "reason": "清地"}], "problems": []},
        {"event": "unreachable", "t": 4.0, "tile": [72, 51], "action": "clear", "stage": "clear_area",
         "zone": "field_ne", "reason": "四邻都站不过去", "note": "当天记 blocked、次日重试"},
        {"event": "unreachable_stage", "t": 7.0, "stage": "clear_area", "zone": "field_ne",
         "tiles": count, "in_leftover": leftover, "coords": COORDS, "note": "阶段收尾：走不到的格"},
        {"event": "outcome", "t": 7.5, "kind": "clear_area", "terminal": "needs_review",
         "postcondition_met": bool(not leftover),
         "reason": f"作业区 field_ne；目标 3 步：做成 0、跳过 0、失败 {stage_failed}；"
                   f"后置条件{'成立' if not leftover else f'未成立（还剩 {leftover} 格）'}",
         "detail": [f"{COORDS[0]}: 清不掉：四邻都站不过去"]},
        {"event": "sleep", "t": 8.0, "ok": True, "code": "ok",
         "reason": "night:时间 2210 已经到夜里（≥2200）"},
        {"event": "unreachable_summary", "t": 8.5, "count": count, "bound": bound,
         "attempted": attempted, "exempted": exempted, "raw_unmet": raw_unmet, "unmet": unmet,
         "tiles": COORDS, "note": "日级豁免上界 max(5, 20%×attempted)"},
        {"event": "day_end", "t": 9.0, "day": DAY, "day_text": "1年 spring 20日", "ended_by": "sleep",
         "ended_reason": "night:时间 2210 已经到夜里（≥2200）", "verified": verified,
         "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                    "no_unmet_stages": bool(not unmet), "crops_watered": True, "watered_outdoor": True,
                    "day_justified": True, "unreachable_within_bound": within_bound},
         "stages": [{"stage": "clear_area", "tiles": len(COORDS), "ok": 0, "skipped": 0,
                     "failed": stage_failed, "failed_any": stage_failed, "proven_inert": 0,
                     "env_block": 0, "inconclusive": 0, "unreachable": count,
                     "stopped": "", "leftover": leftover}],
         "outcomes": [], "ok_steps": 0, "skipped_steps": 0, "failed_steps": failed_steps,
         "notes": [],
         "unreachable": count, "unreachable_tiles": COORDS, "unreachable_bound": bound,
         "unreachable_exempt": exempted,
         "final": {"day": DAY, "timeOfDay": 2200, "location": "Farm", "stamina": 40.0, "money": 100,
                   "isInBed": False, "crops": 31, "unwatered_crops": 0, "ripe": 0, "tillable": 0,
                   "waterLeft": 10, "seeds": []},
         "final_water": {"t": 8.4, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0,
                         "scope": "farm"},
         "day_after": NEXT},
        {"event": "finish", "t": 10.0, "code": code, "verified_streak": streak, "actions": 6,
         "minutes": 1.0, "stages_seen": ["clear_area"], "days": 1},
    ]


def write(name, events):
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print("wrote", path, len(events), "events")


# 上界内：3 ≤ max(5, 20%×20=4) ⇒ 豁免 3、unmet 0，当天算过；
# 账目自洽：被豁免的格**不算** stages[].failed（failed=0、failed_steps=0）
write("_ledger_unreach_ok.jsonl", ledger(
    count=3, bound=5, attempted=20, exempted=3, raw_unmet=3, unmet=0, within_bound=True,
    verified=True, failed_steps=0, stage_failed=0, leftover=0, streak=1, code=0))
# 越界：9 > 5 ⇒ 只豁免 5、unmet 4（4 格留在 leftover = 真失败），checks.unreachable_within_bound=false
write("_ledger_unreach_bad.jsonl", ledger(
    count=9, bound=5, attempted=20, exempted=5, raw_unmet=9, unmet=4, within_bound=False,
    verified=False, failed_steps=4, stage_failed=4, leftover=4, streak=0, code=1))
