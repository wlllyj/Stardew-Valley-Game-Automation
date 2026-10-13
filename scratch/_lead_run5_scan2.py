"""Lead 只读：run5 的 plant/sell/water/dry 轨迹（不写生产文件）。"""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "logs/longrun-3day-llm-run5.jsonl"
rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

print("=== outcome 按 kind 汇总 ===")
import collections
agg = collections.defaultdict(lambda: [0, 0, 0])
for r in rows:
    if r.get("event") == "outcome":
        k = r.get("kind")
        agg[k][0] += 1
        if r.get("postcondition_met"):
            agg[k][1] += 1
        else:
            agg[k][2] += 1
for k, v in agg.items():
    print("  %-14s 次数 %-3d 达成 %-3d 未达成 %-3d" % (k, v[0], v[1], v[2]))

print("=== sell / buy / refill / sleep ===")
for r in rows:
    ev = r.get("event")
    if ev in ("sell", "sell_failed", "buy", "refill", "sleep"):
        print("t=%-7s %-12s %s" % (r.get("t"), ev, str({k: v for k, v in r.items() if k not in ("event", "t", "before", "after")})[:200]))

print("=== plant_area 未达成明细 ===")
for r in rows:
    if r.get("event") == "outcome" and r.get("kind") == "plant_area" and not r.get("postcondition_met"):
        print("t=%-7s %s | detail %s" % (r.get("t"), str(r.get("reason"))[:150], str(r.get("detail"))[:200]))

print("=== plot note 出现 tilesTruncated 的次数 ===")
n = sum(1 for r in rows if r.get("event") == "plot" and "tilesTruncated" in str(r.get("note", "")))
print("  ", n, "/", sum(1 for r in rows if r.get("event") == "plot"))
