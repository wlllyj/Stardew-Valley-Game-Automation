# -*- coding: utf-8 -*-
"""task-36 证据账本：一天一个"浇水证据"案例（合成，只喂 tools\\analyze-longrun.py 做演示/回归）。

A 天：checks 里**没有** watered_outdoor（缺失 = 红 + 无法判定，该天不判通过）
B 天：watered_outdoor=true 但 final_water.scope=window / tiles=0（当天没有户外快照 ⇒ 不可采信）
C 天：watered_outdoor=true 但 final_water.dry=5（自相矛盾）
D 天：watered_outdoor=true + scope=farm + crops>0 + dry=0（干净，不许报红）
E 天：watered_outdoor=false（睡前还有没浇的 ⇒ 红，verify-run3.py:317-318 同向）
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "scratch", "_ledger_water_gates.jsonl")
D11 = [1, "spring", 11]
BASE = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
        "no_unmet_stages": True, "crops_watered": True, "day_justified": True}
FARM_OK = {"t": 590.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0, "scope": "farm"}


def day_start(day):
    return {"event": "day_start", "t": 1.0, "day": day, "timeOfDay": 610, "stamina": 270,
            "money": 100, "crops": 31, "unwatered": 31, "location": "Farm", "weather": "sunny"}


def nxt(day):
    return [day[0], day[1], day[2] + 1]


def day_end(day, checks, final_water=None):
    ev = {"event": "day_end", "t": 600.0, "day": day, "day_text": f"1年 {day[1]} {day[2]}日",
          "started_at": 1.0, "ended_by": "sleep", "ended_reason": "night", "verified": True,
          "checks": checks,
          "stages": [{"stage": "water_area", "tiles": 31, "ok": 31, "skipped": 0, "failed": 0,
                      "proven_inert": 0, "env_block": 0, "inconclusive": 0, "stopped": "",
                      "leftover": 0}],
          "outcomes": [], "ok_steps": 31, "skipped_steps": 0, "failed_steps": 0, "notes": [],
          "final": {"day": nxt(day), "timeOfDay": 600, "location": "FarmHouse", "stamina": 270,
                    "money": 512, "crops": 0, "unwatered_crops": 0, "ripe": 0, "tillable": 0,
                    "seeds": []}}
    if final_water is not None:
        ev["final_water"] = final_water
    return ev


events = [
    day_start(D11), day_end(D11, dict(BASE)),                                  # A 缺失
    day_start([1, "spring", 12]),
    day_end([1, "spring", 12], dict(BASE, watered_outdoor=True),
            {"t": 590.0, "location": "", "tiles": 0, "crops": 0, "dry": None, "scope": "window"}),
    day_start([1, "spring", 13]),
    day_end([1, "spring", 13], dict(BASE, watered_outdoor=True),
            {"t": 590.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 5, "scope": "farm"}),
    day_start([1, "spring", 14]),
    day_end([1, "spring", 14], dict(BASE, watered_outdoor=True), FARM_OK),     # D 干净
    day_start([1, "spring", 15]),
    day_end([1, "spring", 15], dict(BASE, watered_outdoor=False), FARM_OK),    # E false
    {"event": "finish", "t": 601.0, "code": 0, "verified_streak": 5, "actions": 155,
     "minutes": 8.0, "stages_seen": ["water_area"]},
]

with open(OUT, "w", encoding="utf-8") as fh:
    for ev in events:
        fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
print("wrote", OUT, len(events), "events")
