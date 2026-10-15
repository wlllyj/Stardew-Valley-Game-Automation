"""task-87：把 run7 的 analyze --json 报告按天拉平（只读）。

用法: python scratch\\_r7_map.py [scratch/_r7_analyze.json] [logs/longrun-3day-llm-run7.jsonl]
"""
import io
import json
import sys

rep_path = sys.argv[1] if len(sys.argv) > 1 else "scratch/_r7_analyze.json"
led_path = sys.argv[2] if len(sys.argv) > 2 else "logs/longrun-3day-llm-run7.jsonl"

rep = json.load(io.open(rep_path, encoding="utf-8"))

# ---- 事件行 → 事件体
rows = []
with io.open(led_path, encoding="utf-8") as fh:
    for i, line in enumerate(fh, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append((i, json.loads(line)))
        except ValueError:
            pass

# ---- 按 day_start 切天（行号区间）
bounds = []
for ln, ev in rows:
    if ev.get("event") == "day_start":
        bounds.append([ln, ev.get("day"), None])
for idx, b in enumerate(bounds):
    nxt = bounds[idx + 1][0] if idx + 1 < len(bounds) else 10 ** 9
    b[2] = nxt - 1


def day_of(ln):
    for start, day, end in bounds:
        if start <= ln <= end:
            return f"{day[0]}年 {day[1]} {day[2]}日"
    return "<prelude>"


print("== 天边界 ==")
for start, day, end in bounds:
    print(f"  {day[0]}年 {day[1]} {day[2]}日: L{start}..L{end}")
print("prelude 行数:", rep.get("prelude_lines"))

print("\n== 红条目按天 ==")
by_day = {}
for ln in rep["red"]["lines"]:
    by_day.setdefault(day_of(ln), []).append(ln)
for day, lns in by_day.items():
    print(f"  {day}: {len(lns)} 条 {lns[:12]}{' …' if len(lns) > 12 else ''}")

print("\n== 六类条目（subject / 行 / 天）==")
subj_by_line = {}
for key in ("manual", "missed", "wasted", "ineffective", "sleep", "environment"):
    items = rep["categories"].get(key) or []
    print(f"  [{key}] 全量 {rep['categories_total'].get(key)} 条，显示 {len(items)}")
    for it in items:
        ln = it.get("line")
        subj_by_line.setdefault(ln, []).append((key, it.get("subject")))
        if key != "environment":
            print(f"    L{ln} {it.get('subject')} | keys={sorted(it.keys())}")

print("\n== 尾部窗口（summer 7/8/9）红条目逐条 ==")
for ln in rep["red"]["lines"]:
    d = day_of(ln)
    if d.endswith(("7日", "8日", "9日")):
        print(f"  L{ln} [{d}] {subj_by_line.get(ln)}")
        for key in ("missed", "wasted"):
            for it in rep["categories"].get(key) or []:
                if it.get("line") == ln:
                    print(f"      {key}: {json.dumps(it, ensure_ascii=False)[:400]}")

print("\n== 每天事件计数 ==")
per_day = {}
for ln, ev in rows:
    per_day.setdefault(day_of(ln), {}).setdefault(ev.get("event"), []).append((ln, ev))
for start, day, end in bounds:
    label = f"{day[0]}年 {day[1]} {day[2]}日"
    counts = {k: len(v) for k, v in per_day.get(label, {}).items()}
    reds = sum(1 for ln in rep["red"]["lines"] if day_of(ln) == label)
    print(f"  {label}: red={reds} {counts}")

print("\n== 关键链路明细 ==")
for name in ("water_far", "idle", "stuck_flush", "seed_gate", "buy", "sell", "no_day_progress",
             "plot_exhausted", "stage_exhausted", "stage_no_target"):
    hits = [(ln, ev) for ln, ev in rows if ev.get("event") == name]
    if not hits:
        print(f"  [{name}] 0 条")
        continue
    print(f"  [{name}] {len(hits)} 条，前 8 条：")
    for ln, ev in hits[:8]:
        keep = {k: v for k, v in ev.items() if k not in ("event",)}
        print(f"    L{ln} {json.dumps(keep, ensure_ascii=False)[:300]}")
