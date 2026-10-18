# -*- coding: utf-8 -*-
"""task-24：看 smoke-0745 是否已收尾（finish 事件 / 最后一行）。"""
import json
from pathlib import Path

p = Path("logs/longrun-smoke-0745.jsonl")
lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
print("lines:", len(lines))
for line in lines[-3:]:
    try:
        ev = json.loads(line)
        print(ev.get("event"), ev.get("t"), str(ev)[:220])
    except Exception as e:
        print("BAD", str(e)[:120])
evs = {}
for line in lines:
    try:
        ev = json.loads(line)
    except Exception:
        continue
    evs[ev.get("event")] = evs.get(ev.get("event"), 0) + 1
print("event counts:", sorted(evs.items(), key=lambda kv: -kv[1])[:12])
print("has finish:", "finish" in evs, "day_end:", evs.get("day_end"), "day_start:", evs.get("day_start"))
