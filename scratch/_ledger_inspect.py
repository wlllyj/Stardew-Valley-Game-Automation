"""只读：把 longrun 账本的**每行事件与关键字段**拉平，用于核对映射（不进库、不改 logs）。

用途（task-25）：
  python scratch\\_ledger_inspect.py logs\\longrun-3day-llm-run2.jsonl
  python scratch\\_ledger_inspect.py logs\\longrun-3day-llm-run1.jsonl

read 工具会把超长行截断到 2000 字符，所以 day_end 尾部字段（failed_steps 等）必须用本脚本看。
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    counts = {}
    for i, raw in enumerate(lines, 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except Exception as exc:
            print(f"L{i}: 解析失败 {exc}")
            continue
        name = ev.get("event")
        counts[name] = counts.get(name, 0) + 1
        bits = [f"L{i}", f"{name}", f"t={ev.get('t')}"]
        for key in ("ok", "code", "reason", "zone", "boundary", "source", "fallback",
                    "ended_by", "ended_reason", "verified", "checks",
                    "ok_steps", "skipped_steps", "failed_steps",
                    "kind", "terminal", "postcondition_met",
                    "tile", "action", "recovered", "targets"):
            if key in ev:
                bits.append(f"{key}={json.dumps(ev[key], ensure_ascii=False)[:220]}")
        for key in ("day", "intents", "verdicts", "stages", "final", "final_water",
                    "before", "after", "work_reasons", "notes", "stamina", "money",
                    "crops", "unwatered", "timeOfDay", "location"):
            if key in ev:
                bits.append(f"{key}={json.dumps(ev[key], ensure_ascii=False)[:300]}")
        print(" | ".join(bits))
    print()
    print("事件计数:", json.dumps(counts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
