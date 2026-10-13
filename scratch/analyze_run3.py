# -*- coding: utf-8 -*-
"""run3 账本分析（只读）。把 logs\\longrun-3day-llm-run3.jsonl 渲染成：
- 事件计数（含任务书点名的那批事件）
- 决策统计（source / llm / fallback / truncated / intent 分布）
- 逐日时间线（day_start → day_end：ended_by / verified / checks / final_water / stages / 成败格数）
- 首个异常事件 + 末 10 条记录
输出：logs\\run3-journal-summary.txt（utf-8）并打印同样内容。
"""
from __future__ import annotations

import collections
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
JR = os.path.join(REPO, "logs", "longrun-3day-llm-run3.jsonl")
OUT = os.path.join(REPO, "logs", "run3-journal-summary.txt")

WATCH = [
    "intent_verdict", "policy_fallback", "plot_exhausted", "plots_capped", "work_spot",
    "blocked", "env_fail", "inconclusive_fail", "modal_dismissed", "sleep", "no_day_progress",
    "levelup_profession_pending", "levelup_profession_unknown", "day_cap", "day_justified_fail",
    "finish", "day_start", "day_end", "decision", "refill", "goto_farm", "plot", "note",
]

lines: list[str] = []


def p(s: str = "") -> None:
    lines.append(s)


def short(v, n: int = 260) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n})"


with open(JR, "r", encoding="utf-8") as fh:
    recs = [json.loads(ln) for ln in fh if ln.strip()]

p(f"账本：{JR}")
p(f"记录数：{len(recs)}   时间跨度：t={recs[0].get('t')} → {recs[-1].get('t')}（秒）")
p(f"首条 t={recs[0].get('t')} {recs[0].get('event')}   末条 {json.dumps(recs[-1], ensure_ascii=False, default=str)[:300]}")
p("")

# ---- 1. 事件计数 ----
cnt = collections.Counter(r.get("event") for r in recs)
p("== 全部事件计数（按次数降序）==")
for ev, n in cnt.most_common():
    p(f"  {ev:<28} {n}")
p("")
p("== 任务书点名的事件 ==")
for ev in WATCH:
    p(f"  {ev:<28} {cnt.get(ev, 0)}")
p("")

# ---- 2. 决策统计 ----
decs = [r for r in recs if r.get("event") == "decision"]
srcs = collections.Counter(str(d.get("source")) for d in decs)
p(f"== 决策：{len(decs)} 条 ==")
p(f"  source 分布：{dict(srcs)}")
p(f"  llm=true 条数：{sum(1 for d in decs if d.get('llm'))}；truncated：{sum(1 for d in decs if d.get('truncated'))}；fallback 非空：{sum(1 for d in decs if d.get('fallback'))}")
p(f"  boundary 分布：{dict(collections.Counter(str(d.get('boundary')) for d in decs))}")
intents = collections.Counter()
for d in decs:
    for it in (d.get("intents") or []):
        if isinstance(it, dict):
            intents[str(it.get("task"))] += 1
p(f"  intent 任务分布：{dict(intents)}")
for d in decs:
    if d.get("fallback") or d.get("truncated"):
        p(f"  · t={d.get('t')} boundary={d.get('boundary')} source={d.get('source')} llm={d.get('llm')} truncated={d.get('truncated')} fallback={short(d.get('fallback'), 240)}")
p("")

# ---- 3. 逐日时间线 ----
p("== day_start ==")
for r in recs:
    if r.get("event") == "day_start":
        p(f"  t={r.get('t'):>7} {str(r.get('day')):<20} tod={r.get('timeOfDay'):<5} loc={str(r.get('location')):<10} 体力={r.get('stamina')} 钱={r.get('money')} 作物={r.get('crops')} 未浇={r.get('unwatered')} 天气={r.get('weather')}")
p("")
p("== day_end 逐条 ==")
for i, r in enumerate(recs):
    if r.get("event") != "day_end":
        continue
    checks = r.get("checks") or {}
    bad = [k for k, v in checks.items() if v is False]
    p(f"--- #{i} t={r.get('t')} ---")
    p(f"  day={r.get('day')} day_after={r.get('day_after')} ended_by={r.get('ended_by')!r} verified={r.get('verified')}")
    p(f"  reason: {short(r.get('reason'), 300)}")
    p(f"  stages={r.get('stages')} done={r.get('done')} skipped={r.get('skipped')} failed={r.get('failed')}")
    p(f"  checks: {json.dumps(checks, ensure_ascii=False, default=str)}")
    if bad:
        p(f"  ❌ 未通过的判据：{bad}")
    else:
        p("  ✅ 全部判据通过")
    for k in ("final_water", "watered", "dry", "unwatered", "work"):
        if k in r:
            p(f"  {k}: {short(r.get(k), 400)}")
    for k in ("notes", "note"):
        if k in r:
            v = r[k]
            if isinstance(v, list):
                for x in v[:4]:
                    p(f"  note: {short(x, 300)}")
            else:
                p(f"  note: {short(v, 300)}")
    other = {k: v for k, v in r.items() if k not in {"event", "t", "day", "day_after", "ended_by", "verified", "reason", "stages", "done", "skipped", "failed", "checks", "final_water", "watered", "dry", "unwatered", "work", "notes", "note"}}
    if other:
        p(f"  其它字段: {short(other, 400)}")
p("")

# ---- 4. sleep / 异常 ----
p("== sleep 记录 ==")
for r in recs:
    if r.get("event") == "sleep":
        p(f"  t={r.get('t'):>7} day={r.get('day')} ok={r.get('ok')} code={r.get('code')!r} reason={short(r.get('reason'), 200)}")
        for k in ("before", "after", "tries", "note"):
            if k in r:
                p(f"      {k}: {short(r.get(k), 220)}")
p("")
first_bad = next((r for r in recs if r.get("event") == "day_end" and r.get("ended_by") != "sleep"), None)
p("== 首个异常事件（第一个 ended_by != sleep 的 day_end）==")
p("  " + (short(first_bad, 1200) if first_bad else "无"))
p("")
p("== 末 10 条记录 ==")
for r in recs[-10:]:
    p("  " + short(r, 500))
p("")

text = "\n".join(lines) + "\n"
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(text)
print(text)
print(f"已写入：{OUT} ({os.path.getsize(OUT)} bytes)")
