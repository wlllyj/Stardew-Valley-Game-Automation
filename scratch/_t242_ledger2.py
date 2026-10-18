"""task-242 账本离线分析 2：打印不匹配阶段的完整记录 + 同一天的相关事件。"""
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

print("events:", sorted({str(r.get("event")) for r in rows}))
# 找 day_end 行里的 day 标识
for r in rows:
    if r.get("event") == "day_end":
        print("day_end keys:", sorted(r.keys())[:40])
        break
mismatch_idx = []
for i, r in enumerate(rows):
    if r.get("event") != "day_end":
        continue
    for j, st in enumerate(r.get("stages") or []):
        if st.get("stage") == "clear_area" and st.get("ok") != len(st.get("cleared_tiles") or []):
            mismatch_idx.append((i, j))
print("mismatch", len(mismatch_idx))
for i, j in mismatch_idx[:3]:
    r = rows[i]
    st = r["stages"][j]
    print("=" * 70)
    print("row idx", i, "day-related:", {k: r.get(k) for k in ("day", "day_key", "t", "ts")})
    print(json.dumps(st, ensure_ascii=False, indent=1)[:1800])
    # 打印该行之前 6 条事件的 event 名与关键字段
    for k in range(max(0, i - 6), i):
        e = rows[k]
        keep = {kk: e.get(kk) for kk in ("event", "stage", "zone", "ok", "code", "stopped",
                                         "cleared", "opens", "tiles", "reason", "kind")
                if e.get(kk) is not None}
        print("  ev", k, json.dumps(keep, ensure_ascii=False)[:300])
