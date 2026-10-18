# -*- coding: utf-8 -*-
"""product-observer: 抽 day_end / review_llm / policy / day_start 读数（只读账本）。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "end-reads.txt"
lines = []


def load(name):
    with open(ROOT / "logs" / name, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def day_key(ev):
    d = ev.get("day") or ev.get("day_key")
    if isinstance(d, dict):
        return f"{d.get('year')}/{d.get('season')}/{d.get('day')}"
    return str(d)


for name in ("longrun-runA8-0743.jsonl", "longrun-smoke-0744.jsonl"):
    lines.append("=" * 30 + " " + name)
    evs = load(name)
    starts = {}
    for ev in evs:
        if ev.get("event") == "day_start":
            starts[day_key(ev)] = ev
    for ev in evs:
        e = ev.get("event")
        if e == "day_end":
            fin = ev.get("final") or {}
            ch = ev.get("checks") or {}
            plots = ev.get("plots") or {}
            st = ev.get("stages") or []
            ok = sum(int(s.get("ok") or 0) for s in st if isinstance(s, dict))
            bad = sum(int(s.get("failed") or 0) for s in st if isinstance(s, dict))
            lines.append(
                f"[DAY_END {day_key(ev)}] ended_by={ev.get('ended_by')} verified={ev.get('verified')}"
                f" day_justified={ch.get('day_justified')} time={fin.get('timeOfDay')}"
                f" stamina={fin.get('stamina')} money={fin.get('money')} inBed={fin.get('isInBed')}"
                f" stages={len(st)} ok_steps={ev.get('ok_steps')} failed_steps={ev.get('failed_steps')}"
                f" plots={plots}"
            )
            lines.append("    false_checks=" + str([k for k, v in ch.items() if v is False]))
            lines.append("    reason=" + str(ev.get("ended_reason"))[:200])
            st0 = starts.get(day_key(ev)) or {}
            lines.append(
                f"    start: time={st0.get('timeOfDay')} stamina={st0.get('stamina')}"
                f" money={st0.get('money')} crops={st0.get('crops')} weather={st0.get('weather')}"
            )
        elif e == "review_llm":
            lines.append(f"[REVIEW_LLM {day_key(ev)}] notes={json.dumps(ev.get('notes'), ensure_ascii=False)}")
        elif e == "policy":
            lines.append(f"[POLICY md={day_key(ev)}] {json.dumps(ev.get('note'), ensure_ascii=False)}")
        elif e == "tool_upgrade_skipped":
            lines.append(
                f"[UPG {day_key(ev)}] which={ev.get('which')} money={ev.get('money')}"
                f" free_slots={ev.get('free_slots')} reason={json.dumps(ev.get('reason'), ensure_ascii=False)}"
            )

OUT.write_text("\n".join(lines), encoding="utf-8")
print("wrote", OUT, len(lines), "lines")
