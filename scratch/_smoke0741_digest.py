# -*- coding: utf-8 -*-
"""0.7.41 七步冒烟 · 账本摘要（只读；打印并落 logs/smoke-0741-digest.txt）。"""
from __future__ import annotations

import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
JL = os.path.join(ROOT, "logs", "longrun-smoke-0741.jsonl")
OUT = os.path.join(ROOT, "logs", "smoke-0741-digest.txt")

recs = [json.loads(x) for x in open(JL, encoding="utf-8") if x.strip()]
buf: list[str] = []


def p(s: str = "") -> None:
    buf.append(s)
    print(s)


p(f"总记录 = {len(recs)}")
p("\n=== day_end ===")
for i, r in enumerate(recs):
    if r.get("event") != "day_end":
        continue
    fin = r.get("final") or {}
    fw = r.get("final_water") or {}
    stages = r.get("stages") or []
    bad = [k for k, v in (r.get("checks") or {}).items() if v is False]
    ic = r.get("intent_coverage") or []
    ic_brief = []
    for e in ic:
        if isinstance(e, dict):
            name = e.get("intent") or e.get("name") or e.get("kind")
            ic_brief.append((name, e.get("req"), e.get("ok"), e.get("failed"), (e.get("reasons") or {})))
    p(f"#{i:3} day={r.get('day')} ended_by={r.get('ended_by')} verified={r.get('verified')} "
      f"ok={r.get('ok_steps')}/skip={r.get('skipped_steps')}/fail={r.get('failed_steps')} "
      f"day_after={r.get('day_after')}")
    p(f"     reason={(r.get('ended_reason') or '')[:160]}")
    p(f"     bad_checks={bad}")
    p(f"     stages={[(s.get('stage'), s.get('ok'), s.get('failed'), s.get('cleared_tiles') and len(s.get('cleared_tiles'))) for s in stages]}")
    p(f"     intent_coverage={ic_brief}")
    p(f"     final_water={json.dumps(fw, ensure_ascii=False)[:200]}")
    p(f"     final.loc={((fin.get('location') if isinstance(fin.get('location'), str) else (fin.get('location') or {}).get('name')))} "
      f"money={fin.get('money')} stamina={fin.get('stamina')} counts={(fin.get('counts') if isinstance(fin.get('counts'), dict) else None)}")

p("\n=== 其它关键事件 ===")
for i, r in enumerate(recs):
    ev = r.get("event")
    if ev in ("finish", "day_cap", "stamina_budget", "deferred_by_budget", "encircled_summary",
              "no_progress_burst", "blocked", "scope_shed_refused", "tool_upgrade_skipped"):
        p(f"#{i:3} {json.dumps(r, ensure_ascii=False)[:300]}")

p("\n=== slot_relief / sell / harvest ===")
for i, r in enumerate(recs):
    blob = json.dumps(r, ensure_ascii=False)
    if any(k in blob for k in ("slot_relief", '"sell"', "harvest")):
        p(f"#{i:3} {blob[:260]}")

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(buf) + "\n")
print(f"\n已写 {OUT}")
