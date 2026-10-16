"""task-111 合成夹具：造「LLM 复盘/教训库」的正常形态与红形态各一本（只读工具用）。

用法：`python scratch/_t111_demo.py`
产出：
* `scratch/_t111_demo.jsonl` + `scratch/_t111_demo-lessons.json`（复盘 2 条 notes、教训库 5 条 ⇒ 0 红）
* `scratch/_t111_demo_bad.jsonl` + `scratch/_t111_demo_bad-lessons.json`（复盘 0 条 notes、
  教训库 21 条 > 上限 ⇒ 两条红）
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _day_start(day, money=100):
    return {"event": "day_start", "t": 1.0, "day": day, "timeOfDay": 610, "stamina": 270,
            "money": money}


def _final(day, money=100):
    return {"event": "day_end", "t": 9.0, "day": day, "day_text": "", "ended_by": "sleep",
            "ended_reason": "night", "verified": True,
            "checks": {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                       "crops_watered": True, "day_justified": True, "no_unmet_stages": True,
                       "watered_outdoor": True},
            "stages": [{"stage": "water_area", "tiles": 22, "ok": 22, "skipped": 0, "failed": 0,
                        "env_block": 0, "inconclusive": 0, "stopped": None, "leftover": 0}],
            "outcomes": [], "ok_steps": 22, "skipped_steps": 0, "failed_steps": 0, "notes": [],
            "final": {"day": day, "timeOfDay": 2200, "location": "Farm", "money": money,
                      "stamina": 200, "crops": 30, "unwatered_crops": 0, "tillable": 200,
                      "seeds": []},
            "final_water": {"t": 9.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0,
                            "scope": "farm"}}


def _review(day, notes):
    return {"event": "review_llm", "t": 8.0, "day_key": day, "notes": notes,
            "text": json.dumps({"notes": notes}, ensure_ascii=False),
            "usage": {"prompt_tokens": 900, "completion_tokens": 60}, "duration_ms": 1400,
            "model": "deepseek-flash", "rejected": [], "truncated": False,
            "note": "只写 journal 与次日 recent_notes；不参与任何判定"}


def _lessons(day, added, total, dropped=0, path=""):
    return {"event": "lessons", "t": 8.2, "day_key": day, "added": added, "total": total,
            "dropped": dropped, "path": path,
            "note": "只有客观账本事实；hint 仅来自收工复盘的笔记；只喂提示词、不参与判定"}


def write(name, events, lessons):
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    lp = path[: -len(".jsonl")] + "-lessons.json"
    with open(lp, "w", encoding="utf-8") as fh:
        json.dump({"lessons": lessons}, fh, ensure_ascii=False, indent=1)
    return path, lp


def _lesson(i):
    return {"id": f"unreachable|field_ne{i}", "kind": "unreachable", "scope": f"field_ne{i}",
            "symptom": "某格四邻都站不过去", "evidence": "unreachable=2 leftover=3", "hint": "",
            "count": 1, "first_day": [1, "summer", 5], "last_day": [1, "summer", 5],
            "last_seq": 5, "severity": 3}


def main():
    day1, day2 = [1, "summer", 5], [1, "summer", 6]
    good = [
        _day_start(day1),
        _review(day1, ["先清枯死苗再浇水", "别在下雨前买种子"]),
        _lessons(day1, ["unreachable|field_ne", "stage_incomplete|till_area"], 5, 0,
                 os.path.join(HERE, "_t111_demo-lessons.json")),
        _final(day1),
        _day_start(day2, money=140),
        _final(day2, money=140),
        {"event": "finish", "t": 20.0, "code": 0, "verified_streak": 2, "actions": 40,
         "minutes": 1.0, "stages_seen": ["water_area"], "days": 2},
    ]
    bad = [
        _day_start(day1),
        _review(day1, []),
        _lessons(day1, ["x|y"], 21, 0, os.path.join(HERE, "_t111_demo_bad-lessons.json")),
        _final(day1),
        {"event": "finish", "t": 20.0, "code": 0, "verified_streak": 1, "actions": 22,
         "minutes": 0.5, "stages_seen": ["water_area"], "days": 1},
    ]
    p1, l1 = write("_t111_demo.jsonl", good, [_lesson(i) for i in range(5)])
    p2, l2 = write("_t111_demo_bad.jsonl", bad, [_lesson(i) for i in range(21)])
    print("wrote", p1, l1)
    print("wrote", p2, l2)


if __name__ == "__main__":
    main()
