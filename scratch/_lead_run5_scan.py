"""Lead 只读扫描 run5 账本：决策来源/意图/政策事件（不写任何生产文件）。"""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "logs/longrun-3day-llm-run5.jsonl"
rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

print("=== decision ===")
for r in rows:
    if r.get("event") != "decision":
        continue
    intents = r.get("intents") or []
    s = ", ".join("%s@%s" % (i.get("task"), i.get("area_hint")) for i in intents)
    print("t=%-7s day=%-14s src=%-13s llm=%-5s b=%-16s trunc=%-5s | %s"
          % (r.get("t"), r.get("day"), r.get("source"), r.get("llm"),
             r.get("boundary"), r.get("truncated"), s[:120]))

print()
print("=== 事件（policy / *_no_target / exhausted / capped / blocked / sell） ===")
for r in rows:
    ev = r.get("event")
    if ev in ("policy", "stage_no_target", "plot_exhausted", "stage_exhausted",
              "plots_capped", "blocked", "sell", "sell_failed", "goto_farm", "sleep"):
        d = {k: v for k, v in r.items() if k not in ("event", "t")}
        print("t=%-7s %-18s %s" % (r.get("t"), ev, str(d)[:170]))
