"""task-54 复核用：打印一本账本的事件序列 + 每种事件的键（+ day_end 关键字段值）。

用法：python scratch/_t54_ledger_shape.py <journal.jsonl> [max_events]
"""
from __future__ import annotations

import json
import sys
from collections import Counter

path = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 40

rows = []
with open(path, "r", encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

kinds = Counter(str(r.get("event")) for r in rows)
print(f"file={path} lines={len(rows)}")
print("events:", dict(kinds))

seen: set[str] = set()
for r in rows:
    ev = str(r.get("event"))
    if ev in seen:
        continue
    seen.add(ev)
    print(f"\n--- first {ev} keys: {sorted(r.keys())}")

for r in rows[:limit]:
    if r.get("event") != "day_end":
        continue
    print("\n=== first day_end (key -> value, 截断 120 字符) ===")
    for k in sorted(r.keys()):
        v = json.dumps(r[k], ensure_ascii=False)
        print(f"  {k} = {v[:120]}{'…' if len(v) > 120 else ''}")
    break

for r in rows:
    if r.get("event") == "finish":
        print("\n=== finish ===")
        print(json.dumps(r, ensure_ascii=False)[:900])
        break
