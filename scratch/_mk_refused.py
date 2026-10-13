"""task-66 合成账本：被游戏拒绝（`tool_refused`）的"界内 / 越界"两态。

用途：与 `tools\\verify-run3.py:518-521` 交叉核对（越界两边都要红；界内两边都只是信息项），
并给 `tools\\analyze-longrun.py` 的 refused 三级留痕/豁免口径留可复算证据。

用法：`python scratch\\_mk_refused.py`
产出：`scratch\\_ledger_refused_ok.jsonl`（count=3/bound=5/exempt=3，`refused_within_bound=true`）
      `scratch\\_ledger_refused_bad.jsonl`（count=9/bound=5/exempt=5/unmet=4，`false` ⇒ 0 类红）
"""
import json
import os

DAY = [1, "spring", 12]
NXT = [1, "spring", 13]
FARM_WATER = {"t": 590.0, "location": "Farm", "tiles": 84, "crops": 31, "dry": 0, "scope": "farm"}


def day_start():
    return {"event": "day_start", "t": 1.0, "day": DAY, "timeOfDay": 610, "stamina": 270,
            "money": 14, "crops": 31, "unwatered": 31, "location": "Farm", "weather": "sunny"}


def decision():
    return {"event": "decision", "t": 1.5, "day": DAY, "boundary": "new_day",
            "source": "llm", "llm": True,
            "intents": [{"task": "till_area", "area_hint": "field_ne", "reason": "开地",
                         "expected_evidence": "tiles[].kind"}],
            "problems": [], "zone": "field_ne"}


def refused_events(n_tiles, status="tool_ineffective"):
    coords = [[70 + i, 51] for i in range(n_tiles)]
    out = [{"event": "tool_refused", "t": 4.0 + i * 0.05, "tile": c, "action": "till",
            "stage": "till_area", "zone": "field_ne", "status": status, "kind": "grass",
            "reason": "锄不动（这一格还是 grass）"} for i, c in enumerate(coords)]
    out.append({"event": "refused_stage", "t": 5.0, "stage": "till_area", "zone": "field_ne",
                "tiles": n_tiles, "in_leftover": n_tiles, "coords": coords[:12],
                "note": "阶段收尾：被游戏拒绝的格（tool_ineffective）"})
    return out


def build(*, bound_ok, refused, bound, exempt, raw_unmet, unmet, failed):
    events = [day_start(), decision()]
    events += refused_events(refused)
    events.append({"event": "refused_summary", "t": 9.0, "count": refused, "bound": bound,
                   "attempted": 25, "exempted": exempt, "raw_unmet": raw_unmet, "unmet": unmet,
                   "tiles": [[70 + i, 51] for i in range(refused)][:12],
                   "note": "游戏拒绝的格：当天封格、次日重试；界内不影响 verified"})
    events.append({"event": "sleep", "t": 9.2, "ok": True, "code": "ok",
                   "reason": "night：时间 2210 已到夜里（≥2200）",
                   "before": {"day": DAY, "timeOfDay": 2210, "stamina": 100},
                   "after": {"day": NXT, "timeOfDay": 600, "stamina": 270}})
    events.append({
        "event": "day_end", "t": 10.0, "day": DAY, "day_text": "1年 spring 12日",
        "ended_by": "sleep", "ended_reason": "night", "verified": bool(bound_ok),
        "checks": {"slept_by_us": True, "no_blocking_modal": True,
                   "no_hard_failures": bool(bound_ok), "crops_watered": True,
                   "day_justified": True, "no_unmet_stages": True, "watered_outdoor": True,
                   "unreachable_within_bound": True, "refused_within_bound": bool(bound_ok)},
        "stages": [{"stage": "till_area", "tiles": refused, "ok": 5, "skipped": 0,
                    "failed": failed, "failed_any": failed, "proven_inert": 0, "env_block": 0,
                    "inconclusive": 0, "unreachable": 0, "unreachable_tiles": [],
                    "unreachable_leftover": 0, "refused": refused,
                    "refused_tiles": [[70 + i, 51] for i in range(refused)],
                    "refused_leftover": exempt, "attempted": 25, "stopped": "", "leftover": 0}],
        "outcomes": [{"kind": "till_area", "terminal": "VERIFIED" if bound_ok else "needs_review",
                      "postcondition_met": bool(bound_ok),
                      "reason": "作业区 field_ne；后置条件" + ("成立" if bound_ok else "未成立"),
                      "detail": []}],
        "ok_steps": 5, "skipped_steps": 0, "failed_steps": failed,
        "notes": [], "final": {"event": "final", "t": 900.0, "day": NXT, "timeOfDay": 2210,
                               "stamina": 100, "location": "FarmHouse", "tile": [9, 9],
                               "isInBed": True, "crops": 0, "unwatered_crops": 0, "ripe": 0,
                               "tillable": 0, "waterLeft": 40, "seeds": []},
        "refused": refused, "refused_bound": bound, "refused_exempt": exempt,
        "refused_tiles": [[70 + i, 51] for i in range(refused)],
        "final_water": FARM_WATER,
    })
    events.append({"event": "finish", "t": 11.0, "code": 1, "verified_streak": 0,
                   "actions": 40, "minutes": 4.0, "stages_seen": ["till_area"]})
    return events


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ok = build(bound_ok=True, refused=3, bound=5, exempt=3, raw_unmet=3, unmet=0, failed=0)
    bad = build(bound_ok=False, refused=9, bound=5, exempt=5, raw_unmet=9, unmet=4, failed=0)
    for name, events in (("_ledger_refused_ok.jsonl", ok), ("_ledger_refused_bad.jsonl", bad)):
        path = os.path.join(here, name)
        with open(path, "w", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        print(f"wrote {path} ({len(events)} events)")


if __name__ == "__main__":
    main()
