"""只读：把 run6 账本的事件形状拉平（task-69）。

用法: python scratch\_t69_fields.py [账本路径]
"""
import collections
import json
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"logs\longrun-3day-llm-run6.jsonl"

evs = [json.loads(l) for l in open(P, encoding="utf-8") if l.strip()]
print("账本:", P)
print("事件行:", len(evs))
c = collections.Counter(e.get("event") for e in evs)
print("--- 事件计数")
for k, v in c.most_common():
    print("  %-24s %d" % (k, v))

print("--- day_start")
for i, e in enumerate(evs, 1):
    if e.get("event") == "day_start":
        print("  L%d day=%s tod=%s loc=%s t=%s" % (i, e.get("day"), e.get("timeOfDay"), e.get("location"), e.get("t")))

print("--- day_end")
for i, e in enumerate(evs, 1):
    if e.get("event") == "day_end":
        print("  L%d day=%s ended_by=%s day_after=%s verified=%s stages=%d" % (
            i, e.get("day"), e.get("ended_by"), e.get("day_after"), e.get("verified"),
            len(e.get("stages") or [])))
        for k, v in (e.get("checks") or {}).items():
            print("      checks.%-28s %s" % (k, v))
        for k in sorted(e):
            if k.startswith("unreach") or k.startswith("refused"):
                val = e[k]
                if isinstance(val, list) and len(val) > 8:
                    val = "%d 项(head=%s)" % (len(val), val[:4])
                print("      %-28s %s" % (k, val))

print("--- 关键事件全文")
KEYS = ("buy", "sell", "sell_failed", "idle", "seed_gate", "stage_exhausted", "intent_vetoed",
        "no_day_progress", "finish", "sleep", "budget_exhausted", "day_cap", "stage_no_target",
        "plot_exhausted", "unreachable_summary", "refused_summary")
for i, e in enumerate(evs, 1):
    if e.get("event") in KEYS:
        body = {k: v for k, v in e.items() if k != "event"}
        txt = json.dumps(body, ensure_ascii=False)
        print("  L%-4d %-20s %s" % (i, e.get("event"), txt[:520]))
