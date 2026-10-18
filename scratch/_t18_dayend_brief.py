# -*- coding: utf-8 -*-
"""task-18 冒烟（smoke-0745）两日 day_end 简报抽取（只读）。输出 scratch/_t18_dayend_brief.txt。"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = os.path.join(REPO, "logs", "longrun-smoke-0745.jsonl")
OUT = os.path.join(REPO, "scratch", "_t18_dayend_brief.txt")

rows = []
for i, line in enumerate(open(J, encoding="utf-8"), 1):
    line = line.strip()
    if line:
        rows.append((i, json.loads(line)))

de = [(i, e) for i, e in rows if e.get("event") == "day_end"]
out = []
for i, e in de:
    out.append("== day_end L%d day=%s ended_by=%s verified=%s ok=%s skipped=%s failed=%s" % (
        i, e.get("day"), e.get("ended_by"), e.get("verified"), e.get("ok_steps"),
        e.get("skipped_steps"), e.get("failed_steps")))
    out.append("checks=" + json.dumps(e.get("checks"), ensure_ascii=False))
    out.append("reason=" + str(e.get("ended_reason")))
    out.append("stages=" + json.dumps([{k: s.get(k) for k in ("stage", "tiles", "ok", "skipped", "failed")}
                                       for s in (e.get("stages") or [])], ensure_ascii=False))
    out.append("stage_midway_leftover=" + json.dumps(e.get("stage_midway_leftover"), ensure_ascii=False))
    out.append("loot_lost=" + json.dumps({k: e.get(k) for k in ("loot_lost_steps", "loot_lost_tiles", "loot_lost_items")}, ensure_ascii=False))
    out.append("free_slots=" + json.dumps({k: e.get(k) for k in ("free_slots_start", "free_slots_last", "free_slots_min", "free_slots_status")}, ensure_ascii=False))
    out.append("stamina_budget=" + json.dumps(e.get("stamina_budget"), ensure_ascii=False))
    out.append("unreachable=%s refused=%s encircled=%s assigned_undone=%s" % (
        json.dumps(e.get("unreachable")), json.dumps(e.get("refused")),
        json.dumps(e.get("encircled")), json.dumps(e.get("assigned_undone"))))
    out.append("plots=" + json.dumps([{k: p.get(k) for k in ("zone", "anchor")} for p in (e.get("plots") or [])], ensure_ascii=False))
    out.append("")

text = "\n".join(out) + "\n"
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
print("WROTE", OUT, len(text), "chars")
