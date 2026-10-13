"""task-41 探针：把绿账本最后一天改成 `ended_by="blocked_event"`，看两个工具各怎么处理。

用法（cwd = 仓库根）：python scratch/_t41_event_day.py
产物：scratch/review-t41-blocked-event-day.jsonl（伪造，仅供工具口径对照，不入库）
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
src = ROOT / "scratch" / "journal-green.jsonl"
dst = ROOT / "scratch" / "review-t41-blocked-event-day.jsonl"

rows = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]

last_end = max(i for i, r in enumerate(rows) if r.get("event") == "day_end")
end = rows[last_end]
day = end.get("day")

rows.insert(last_end, {
    "t": 1715.0, "event": "event_blocked", "day": day,
    "activeMenu": "DialogueBox", "activeMenuText": "Hello Jay!",
    "dialogueIsQuestion": False, "dialogueResponses": [],
    "tile": [64, 15], "timeOfDay": 1010, "worldSeq": 4242,
    "note": "游戏事件挂住（ui.eventUp=true）：不 dismiss / 不 sleep / 不 load_save，当天不判 VERIFIED，等人处理",
})

checks = dict(end.get("checks") or {})
checks["slept_by_us"] = False
checks["no_blocking_modal"] = False
end["ended_by"] = "blocked_event"
end["ended_reason"] = "游戏事件挂住（eventUp=true）：DialogueBox「Hello Jay!」"
end["verified"] = False
end["checks"] = checks
end["notes"] = list(end.get("notes") or []) + [
    "游戏事件挂住（eventUp），按政策停下等人：不 dismiss / 不 sleep / 不 load_save"
]

finish = [r for r in rows if r.get("event") == "finish"]
if finish:
    finish[-1]["code"] = 1
    finish[-1]["verified_streak"] = 0

dst.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
print(f"WROTE {dst} rows={len(rows)} day_end_ended_by={end['ended_by']}")
