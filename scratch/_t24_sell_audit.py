# -*- coding: utf-8 -*-
"""task-24：smoke-0745 出货（sell）逐件表 + 建材/建造预留冲突证据 + 钱差分。"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "logs" / "longrun-smoke-0745.jsonl"

BUILDING = {"(O)388": "木材 Wood", "(O)330": "黏土 Clay", "(O)390": "石头 Stone",
            "(O)378": "铜矿石 Copper Ore", "(O)380": "铁矿石 Iron Ore",
            "(O)709": "硬木 Hardwood", "(O)771": "纤维 Fiber"}

rows = []
for i, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
    if line.strip():
        rows.append((i, json.loads(line)))

day_starts = [(ln, ev) for ln, ev in rows if ev.get("event") == "day_start"]
day_ends = [(ln, ev) for ln, ev in rows if ev.get("event") == "day_end"]


def day_of(line):
    cur = None
    for ln, ev in day_starts:
        if ln <= line:
            cur = ev.get("day")
    return cur


print("== day_start money / day_end money ==")
for ln, ev in day_starts:
    print(f"  L{ln} day_start {ev.get('day')} money={ev.get('money')} stamina={ev.get('stamina')}")
for ln, ev in day_ends:
    print(f"  L{ln} day_end {ev.get('day')} ended_by={ev.get('ended_by')}")

print("\n== sell 逐件（成功/失败） ==")
tot = {}
for ln, ev in rows:
    if ev.get("event") != "sell":
        continue
    d = day_of(ln)
    qid = ev.get("qid")
    name = (ev.get("before") or {}).get("name") or ""
    stack = ev.get("stack")
    ok = ev.get("ok")
    bin_after = (ev.get("after") or {}).get("shipping_bin")
    wl = (ev.get("before") or {}).get("whitelist")
    strat = ev.get("strategy")
    mark = "★建材" if qid in BUILDING else ""
    print(f"  L{ln} day={d} qid={qid} name={name} stack={stack} ok={ok} bin_after={bin_after} "
          f"strategy={strat} whitelist={wl} {mark}")
    if ok:
        key = (tuple(d) if isinstance(d, list) else d, qid, name)
        tot[key] = tot.get(key, 0) + int(stack or 0)

print("\n== 成功出货按天/物品合计 ==")
for (d, qid, name), n in sorted(tot.items()):
    mark = "★建材" if qid in BUILDING else ""
    print(f"  day={d} {qid} {name}: {n} 件 {mark}")

print("\n== 建材冲突汇总 ==")
b_tot = {}
for (d, qid, name), n in tot.items():
    if qid in BUILDING:
        b_tot[(d, qid, name)] = n
for k, n in sorted(b_tot.items()):
    print(f"  day={k[0]} {k[1]} {k[2]}: {n}")
print("  建材合计:", sum(b_tot.values()))

print("\n== slot_relief reason 里出现『建造预留』的行 ==")
for ln, ev in rows:
    if ev.get("event") == "slot_relief":
        s = json.dumps(ev, ensure_ascii=False)
        if "建造" in s or "预留" in s:
            print(f"  L{ln} {s[:600]}")

print("\n== money 事件（shipping 结算线索） ==")
for ln, ev in rows:
    if ev.get("event") in ("money", "shipping_settle", "new_day", "ship_settle", "gold"):
        print(f"  L{ln} {json.dumps(ev, ensure_ascii=False)[:300]}")
