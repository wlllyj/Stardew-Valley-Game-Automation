"""task-242 账本离线分析：列出 clear_area 阶段 ok != len(cleared_tiles) 的形状。"""
import json
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "logs/longrun-smoke-0742.jsonl")
rows = []
with p.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
print("rows", len(rows))
miss = 0
for r in rows:
    if r.get("event") != "day_end":
        continue
    day = r.get("day_key")
    for st in r.get("stages") or []:
        if st.get("stage") != "clear_area":
            continue
        ok = st.get("ok")
        cl = st.get("cleared_tiles") or []
        if ok == len(cl):
            continue
        miss += 1
        print("DAY", day, "ok", ok, "cleared", len(cl), "tiles", st.get("tiles"),
              "skipped", st.get("skipped"), "failed", st.get("failed"),
              "unreach", st.get("unreachable"), "refused", st.get("refused"),
              "env", st.get("env_block"), "inc", st.get("inconclusive"),
              "attempted", st.get("attempted"), "stopped", st.get("stopped"),
              "leftover", st.get("leftover"))
print("mismatch stages", miss)
# 打印所有 key，确认账本里有没有 already/opens 字段
keys = set()
for r in rows:
    if r.get("event") != "day_end":
        continue
    for st in r.get("stages") or []:
        keys.update(st.keys())
print("stage keys:", sorted(keys))
