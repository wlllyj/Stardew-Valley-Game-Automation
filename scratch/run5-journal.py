# -*- coding: utf-8 -*-
"""run5 账本取证（只读 logs\\longrun-3day-llm-run5.jsonl）。

打印紧凑摘要到 stdout，并把完整摘要写到 logs\\run5-journal-summary.txt。
用它可以复核：逐日 day_end（checks / final / final_water / 阶段汇总 / 失败格）、sleep 记录、
结束记录（finish / day_cap）、以及点名事件计数。
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
JL = os.path.join(REPO, "logs", "longrun-3day-llm-run5.jsonl")
OUT = os.path.join(REPO, "logs", "run5-journal-summary.txt")

recs = []
with open(JL, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            recs.append(json.loads(line))

ev = Counter(r.get("event") for r in recs)
lines: list[str] = []


def emit(s: str = "") -> None:
    lines.append(s)


emit(f"账本 {JL}")
emit(f"总记录 = {len(recs)}")
emit(f"事件计数 = {dict(ev.most_common())}")
named = ["policy_fallback", "modal_dismissed", "modal_loop_capped", "blocked_modal", "event_blocked",
         "no_day_progress", "bridge_down", "modal_timeout", "watchdog_stop", "env_fail",
         "inconclusive_fail", "work_spot", "goto_farm", "refill", "seed_gate", "plots_capped",
         "stage_exhausted", "stage_no_target", "stage_midway_leftover", "plot_exhausted", "idle",
         "levelup_profession_pending", "levelup_profession_unknown", "day_justified_fail"]
emit("点名事件 = " + json.dumps({k: ev.get(k, 0) for k in named if ev.get(k, 0)}, ensure_ascii=False))
dec = [r for r in recs if r.get("event") == "decision"]
src = Counter(r.get("source") for r in dec)
intents: Counter = Counter()
for r in dec:
    for it in r.get("intents") or []:
        intents[(it.get("task") if isinstance(it, dict) else it)] += 1
emit(f"决策 {len(dec)} 条：source={dict(src)}，llm={sum(1 for r in dec if r.get('llm'))}，"
     f"truncated={sum(1 for r in dec if r.get('truncated'))}，fallback非空={sum(1 for r in dec if r.get('fallback'))}")
emit(f"intent 分布 = {dict(intents.most_common())}")
emit(f"boundary 分布 = {dict(Counter(r.get('boundary') for r in dec))}")
emit()

emit("=== day_start ===")
for i, r in enumerate(recs):
    if r.get("event") == "day_start":
        emit(f"#{i:3} t={r.get('t')} " + json.dumps({k: r.get(k) for k in
             ("day", "day_text", "location", "clock", "crops", "unwatered_crops", "stamina", "money", "seeds")},
             ensure_ascii=False)[:400])

emit()
emit("=== day_end ===")
for i, r in enumerate(recs):
    if r.get("event") != "day_end":
        continue
    fin = r.get("final") or {}
    emit(f"#{i:3} t={r.get('t')} ended_by={r.get('ended_by')} verified={r.get('verified')}")
    emit(f"     ended_reason={(r.get('ended_reason') or '')[:180]}")
    emit(f"     day={r.get('day')} day_after={r.get('day_after')} day_text={r.get('day_text')}")
    emit(f"     ok_steps={r.get('ok_steps')} skipped_steps={r.get('skipped_steps')} failed_steps={r.get('failed_steps')}")
    emit(f"     checks={json.dumps(r.get('checks'), ensure_ascii=False)}")
    emit(f"     final={json.dumps(fin, ensure_ascii=False)[:700]}")
    emit(f"     final_water={json.dumps(r.get('final_water'), ensure_ascii=False)[:360]}")
    st = r.get("stages") or []
    agg: Counter = Counter()
    for s in st:
        agg["segments"] += 1
        for k in ("tiles", "ok", "skipped", "failed"):
            agg[k] += s.get(k) or 0
    emit(f"     stages 段数={len(st)} 汇总={dict(agg)} stopped={[s.get('stopped') for s in st if s.get('stopped')][:6]}")
    if r.get("notes"):
        emit(f"     notes={json.dumps(r['notes'], ensure_ascii=False)[:400]}")

emit()
emit("=== sleep ===")
for i, r in enumerate(recs):
    if r.get("event") == "sleep":
        emit(f"#{i:3} t={r.get('t')} ok={r.get('ok')} code={r.get('code')} reason={(r.get('reason') or '')[:200]}")
        emit(f"     receipt={json.dumps(r.get('receipt'), ensure_ascii=False)[:400]}")

emit()
emit("=== finish / day_cap / 其它终结 ===")
for i, r in enumerate(recs):
    if r.get("event") in ("finish", "day_cap", "no_day_progress", "blocked_modal", "event_blocked"):
        emit(f"#{i:3} {json.dumps(r, ensure_ascii=False)[:600]}")

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")

# stdout：紧凑摘要（事件计数 + 逐日一行 + 终结）
print("\n".join(lines[:6]))
print()
for i, r in enumerate(recs):
    if r.get("event") == "day_end":
        fin = r.get("final") or {}
        fw = r.get("final_water") or {}
        print(f"day_end #{i:3} t={r.get('t')} ended_by={r.get('ended_by')} verified={r.get('verified')} "
              f"day_after={r.get('day_after')} checks={json.dumps(r.get('checks'), ensure_ascii=False)}")
        print(f"    dry={fw.get('dry')}/{fw.get('crops')} scope={fw.get('scope')} "
              f"final.location={fin.get('location')} final.clock=day{fin.get('day')} tod{fin.get('timeOfDay')} "
              f"final.crops={fin.get('crops')} final.unwatered={fin.get('unwatered_crops')} scope={fin.get('counts_scope')}")
        print(f"    ok={r.get('ok_steps')} skipped={r.get('skipped_steps')} failed={r.get('failed_steps')} "
              f"reason={(r.get('ended_reason') or '')[:120]}")
for i, r in enumerate(recs):
    if r.get("event") in ("finish", "day_cap"):
        print(f"{r.get('event')} #{i}: {json.dumps(r, ensure_ascii=False)[:300]}")
print(f"\n完整摘要 -> {OUT}")
