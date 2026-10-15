# -*- coding: utf-8 -*-
"""run7 账本取证（只读）—— 为 docs/_run7-evidence.md 的 §1–§5 取数。

用法：python scratch\\run7-extract.py [--journal logs\\longrun-3day-llm-run7.jsonl]
输出：完整取证落 logs\\run7-journal-extract.txt；屏幕上只打紧凑摘要。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

ap = argparse.ArgumentParser()
ap.add_argument("--journal", default=os.path.join("logs", "longrun-3day-llm-run7.jsonl"))
ap.add_argument("--out", default=os.path.join("logs", "run7-journal-extract.txt"))
args = ap.parse_args()

jp = args.journal if os.path.isabs(args.journal) else os.path.join(REPO, args.journal)
out = args.out if os.path.isabs(args.out) else os.path.join(REPO, args.out)

recs = []
with open(jp, encoding="utf-8") as fh:
    for i, line in enumerate(fh):
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except Exception as exc:  # noqa: BLE001
            recs.append({"event": "__bad__", "line": i + 1, "err": str(exc)})

W = []
P = print


def w(s=""):
    W.append(s)


def g(d, *ks, default=None):
    cur = d
    for k in ks:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def clock(c):
    if not isinstance(c, dict):
        return c
    return f"{c.get('season')} {c.get('day')} tod={c.get('timeOfDay')} {c.get('weather')}"


w(f"账本 = {jp}")
w(f"总记录 = {len(recs)}")
kinds = collections.Counter(r.get("event") for r in recs)
w(f"事件计数 = {dict(kinds)}")

# ---- decision / LLM 覆盖 ----
dec = [r for r in recs if r.get("event") == "decision"]
src = collections.Counter(r.get("source") for r in dec)
llm_true = sum(1 for r in dec if r.get("llm") is True)
llm_used = sum(1 for r in dec if r.get("llm") is True and r.get("source") == "llm")
trunc = sum(1 for r in dec if r.get("truncated"))
fallback = sum(1 for r in dec if r.get("fallback"))
w("")
w("=== decision / LLM 覆盖（§3.1 口径）===")
w(f"decision 条数 = {len(dec)}；source 分布 = {dict(src)}")
w(f"decisions_llm(llm==true) = {llm_true}；decisions_llm_used(llm==true and source=='llm') = {llm_used}；差 = {llm_true - llm_used}")
w(f"truncated = {trunc}；fallback 非空 = {fallback}")
boundary = collections.Counter(r.get("boundary") for r in dec)
w(f"boundary 分布 = {dict(boundary)}")
intents = collections.Counter()
for r in dec:
    it = r.get("intents") or []
    if isinstance(it, list):
        for x in it:
            intents[g(x, "task") if isinstance(x, dict) else str(x)] += 1
w(f"intent 分布 = {dict(intents)}")
trace_failed = [r for r in recs if r.get("event") == "llm_trace_failed"]
w(f"llm_trace_failed = {len(trace_failed)}")

# ---- day_start ----
w("")
w("=== day_start ===")
for i, r in enumerate(recs):
    if r.get("event") != "day_start":
        continue
    final = r.get("final") if isinstance(r.get("final"), dict) else r
    w(f"#{i:4} t={r.get('t')} day={r.get('day')} started_at={r.get('started_at')} "
      f"clock={clock(final.get('clock'))} loc={g(final, 'location', 'name')} "
      f"tile={g(final, 'player', 'tile')} stamina={g(final, 'player', 'stamina')} money={g(final, 'player', 'money')} "
      f"crops={g(final, 'counts', 'crops')} unwatered={g(final, 'counts', 'unwatered_crops')} "
      f"scope={g(final, 'counts_scope')} seeds={g(final, 'player', 'seeds')}")

# ---- day_end ----
w("")
w("=== day_end ===")
day_rows = []
for i, r in enumerate(recs):
    if r.get("event") != "day_end":
        continue
    fin = r.get("final") or {}
    fw = r.get("final_water") or {}
    row = {
        "i": i, "t": r.get("t"), "day": r.get("day"), "day_text": r.get("day_text"),
        "ended_by": r.get("ended_by"), "ended_reason": r.get("ended_reason"),
        "verified": r.get("verified"), "day_after": r.get("day_after"),
        "ok": r.get("ok_steps"), "skip": r.get("skipped_steps"), "fail": r.get("failed_steps"),
        "checks": r.get("checks"), "fw": fw,
        "loc": g(fin, "location", "name"), "tile": g(fin, "player", "tile"),
        "tod": g(fin, "clock", "timeOfDay") if isinstance(fin.get("clock"), dict) else fin.get("timeOfDay"),
        "counts_scope": g(fin, "counts_scope"),
        "unreachable": r.get("unreachable"), "unreachable_tiles": r.get("unreachable_tiles"),
        "unreachable_bound": r.get("unreachable_bound"), "unreachable_exempt": r.get("unreachable_exempt"),
        "refused": r.get("refused"), "refused_tiles": r.get("refused_tiles"),
        "refused_bound": r.get("refused_bound"), "refused_exempt": r.get("refused_exempt"),
        "attempted": r.get("attempted"), "notes": r.get("notes"), "failed_list": r.get("failed_steps_list"),
    }
    day_rows.append(row)
    w(f"#{i:4} t={row['t']} day={row['day']} ended_by={row['ended_by']} verified={row['verified']} "
      f"ok/skip/fail={row['ok']}/{row['skip']}/{row['fail']} day_after={row['day_after']}")
    w(f"      ended_reason={(row['ended_reason'] or '')[:200]}")
    w(f"      final: loc={row['loc']} tile={row['tile']} tod={row['tod']} scope={row['counts_scope']}")
    w(f"      final_water={json.dumps(fw, ensure_ascii=False)[:300]}")
    w(f"      checks={json.dumps(row['checks'], ensure_ascii=False)}")
    if row["unreachable"] is not None or row["refused"] is not None:
        w(f"      unreachable={row['unreachable']} tiles={json.dumps(row['unreachable_tiles'], ensure_ascii=False)[:300]} "
          f"bound={row['unreachable_bound']} exempt={row['unreachable_exempt']}")
        w(f"      refused={row['refused']} tiles={json.dumps(row['refused_tiles'], ensure_ascii=False)[:300]} "
          f"bound={row['refused_bound']} exempt={row['refused_exempt']} attempted={row['attempted']}")
    if row["notes"]:
        w(f"      notes={json.dumps(row['notes'], ensure_ascii=False)[:500]}")
    st = r.get("stages") or []
    if st:
        agg = collections.Counter()
        for s in st:
            agg[s.get("stage")] += 1
        w(f"      stages({len(st)}) by name={dict(agg)}")
        tot = collections.Counter()
        for s in st:
            tot["tiles"] += s.get("tiles") or 0
            tot["ok"] += s.get("ok") or 0
            tot["skip"] += s.get("skipped") or 0
            tot["fail"] += s.get("failed") or 0
            tot["leftover"] += s.get("leftover") or 0
        w(f"      stage totals = {dict(tot)}")
        for s in st:
            if (s.get("failed") or 0) or (s.get("leftover") or 0) or s.get("stopped"):
                w(f"        - {s.get('stage')} tiles={s.get('tiles')} ok={s.get('ok')} skip={s.get('skipped')} "
                  f"fail={s.get('failed')} leftover={s.get('leftover')} stopped={s.get('stopped')!r} "
                  f"unreachable={s.get('unreachable')} refused={s.get('refused')}")

# ---- 逐日事件时间线（只看非日常事件） ----
ROUTINE = {"decision", "outcome", "intent_verdict", "plot", "day_start", "day_end", "review", "stage_exhausted", "stage_midway_leftover"}
w("")
w("=== 非日常事件时间线（含 idle/blocked/stuck_flush/unreachable/buy/sell/water_far 等）===")
for i, r in enumerate(recs):
    ev = r.get("event")
    if ev in ROUTINE or ev is None:
        continue
    if ev in ("finish", "day_cap"):
        w(f"#{i:4} t={r.get('t')} {ev} {json.dumps(r, ensure_ascii=False)[:400]}")
        continue
    extra = {k: v for k, v in r.items() if k not in ("event", "t")}
    w(f"#{i:4} t={r.get('t')} {ev} {json.dumps(extra, ensure_ascii=False)[:400]}")

# ---- sleep ----
w("")
w("=== sleep ===")
for i, r in enumerate(recs):
    if r.get("event") != "sleep":
        continue
    w(f"#{i:4} t={r.get('t')} ok={r.get('ok')} code={r.get('code')} reason={(str(r.get('reason'))[:180])}")

# ---- blocked 明细 ----
w("")
w("=== blocked ===")
for i, r in enumerate(recs):
    if r.get("event") != "blocked":
        continue
    w(f"#{i:4} t={r.get('t')} {json.dumps({k: v for k, v in r.items() if k != 'event'}, ensure_ascii=False)[:400]}")

os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as fh:
    fh.write("\n".join(W) + "\n")

P(f"账本 {jp}")
P(f"总记录 {len(recs)}；事件计数 {dict(kinds)}")
P(f"decision={len(dec)} llm={llm_true} llm_used={llm_used} truncated={trunc} fallback={fallback} boundary={dict(boundary)}")
P(f"day_end 条数 = {len(day_rows)}")
for row in day_rows:
    ck = row["checks"] or {}
    bad = [k for k, v in ck.items() if v is False]
    P(f"  t={row['t']} day={row['day']} {row['ended_by']} verified={row['verified']} "
      f"ok/skip/fail={row['ok']}/{row['skip']}/{row['fail']} day_after={row['day_after']} "
      f"dry={g(row['fw'], 'dry')}/{g(row['fw'], 'crops')} bad_checks={bad}")
P(f"完整取证已写入 {out}")
