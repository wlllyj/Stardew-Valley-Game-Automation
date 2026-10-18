# -*- coding: utf-8 -*-
"""task-18 冒烟（smoke-0745）补充证据：代码锚点 + 交易/背包读数（只读，不碰游戏）。

输出 scratch/_t18_anchor_notes.txt
"""
import glob
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LONGRUN = os.path.join(REPO, "brain", "agentfarm", "longrun.py")
JOURNAL = os.path.join(REPO, "logs", "longrun-smoke-0745.jsonl")
OUT = os.path.join(REPO, "scratch", "_t18_anchor_notes.txt")

PATS = [
    "JUSTIFIED_END_REASONS", "def is_justified_end", "inventory_blocked",
    "pending_executable", "day_justified", "resume_exhausted",
    "_pending_work", "plot_pending_executable",
]

out = []
out.append("== longrun.py 锚点（当前工作树，生产五文件未改）==")
src = open(LONGRUN, encoding="utf-8").read().splitlines()
for i, line in enumerate(src, 1):
    if any(p in line for p in PATS):
        out.append("%5d %s" % (i, line.rstrip()))
out.append("")

out.append("== 账本交易事件（sell/buy/slot_relief*/inventory_blocked）==")
rows = []
for i, line in enumerate(open(JOURNAL, encoding="utf-8"), 1):
    line = line.strip()
    if line:
        rows.append((i, json.loads(line)))
for i, e in rows:
    if e.get("event") in ("sell", "buy", "slot_relief", "slot_relief_noted", "inventory_blocked"):
        out.append("L%-4d %-18s %s" % (i, e["event"], json.dumps(
            {k: e.get(k) for k in ("t", "day", "item", "items", "count", "unit_price",
                                   "price", "total", "free_slots", "reserve", "rounds",
                                   "limit", "reason", "note", "source", "channel",
                                   "available", "available_items", "availableItems")},
            ensure_ascii=False)))
out.append("")

out.append("== buy 原始行 ==")
for i, e in rows:
    if e.get("event") == "buy":
        out.append("L%d %s" % (i, json.dumps(e, ensure_ascii=False)[:3000]))
out.append("")

out.append("== 最新观测里的背包（observe 文件 payload.player.inventory*）==")
files = sorted(glob.glob(os.path.join(REPO, "scratch", "smoke-0742-observe-*25651.json")))
for f in files:
    d = json.load(open(f, encoding="utf-8"))
    pl = (d.get("observe") or d).get("player") or {}
    out.append("file=%s captured_at=%s" % (os.path.basename(f), d.get("captured_at")))
    for k in sorted(pl):
        if "invent" in k.lower() or k in ("money", "stamina", "slot"):
            out.append("  player.%s = %s" % (k, json.dumps(pl[k], ensure_ascii=False)[:1500]))
    # inventory list if present
    inv = pl.get("inventory") or (d.get("observe") or {}).get("inventory")
    out.append("  inventory=%s" % json.dumps(inv, ensure_ascii=False)[:3000])

text = "\n".join(out) + "\n"
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
print("WROTE", OUT, len(text), "chars")
