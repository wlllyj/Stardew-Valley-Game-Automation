# -*- coding: utf-8 -*-
"""run9b 取证精简摘要（给证据文档用）：只打关键字段，输出 <200 行 → logs/run9b-brief.txt"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOGS = os.path.join(ROOT, "logs")
JOURNAL = os.path.join(LOGS, "longrun-3day-llm-run9b.jsonl")

recs = [json.loads(l) for l in open(JOURNAL, encoding="utf-8") if l.strip()]
out: list[str] = [f"账本 {len(recs)} 行"]

# 六问③：死苗/认输
out.append("\n[③ 逐日 dead/dry_dead/gave_up]")
for i, r in enumerate(recs):
    if r.get("event") == "day_end":
        out.append(f"#{i} day_after={r.get('day_after')} dead_crops={r.get('dead_crops')} "
                   f"dry_dead={r.get('dry_dead')} gave_up_tiles={r.get('gave_up_tiles')}")

# 六问④：兜底/连发
out.append("\n[④ review_only_fallback / burst / no_target]")
for name in ("review_only_fallback", "review_only_no_target", "plot_exhausted_burst", "intent_vetoed"):
    hits = [(i, r) for i, r in enumerate(recs) if r.get("event") == name]
    out.append(f"-- {name} ({len(hits)}) --")
    for i, r in hits[:4]:
        out.append(f"#{i} {json.dumps(r, ensure_ascii=False)[:400]}")

# 六问⑤：farm_evidence_unavailable
out.append("\n[⑤ farm_evidence_unavailable]")
hits = [(i, r) for i, r in enumerate(recs) if "farm_evidence" in json.dumps(r, ensure_ascii=False)]
out.append(f"命中 {len(hits)} 条 → {[i for i, _ in hits]}")

# 六问⑥：buy_partial / no_space
out.append("\n[⑥ buy / buy_partial / cannot_afford / seed_unavailable_today]")
for name in ("buy", "buy_partial", "cannot_afford", "seed_unavailable_today"):
    hits = [r for r in recs if r.get("event") == name]
    out.append(f"-- {name} ({len(hits)}) --")
    for r in hits[:5]:
        out.append("   " + json.dumps(r, ensure_ascii=False)[:300])
ns = [i for i, r in enumerate(recs) if "no_space" in json.dumps(r, ensure_ascii=False)]
out.append(f"含 no_space 的记录号：{ns}")

# 六问②：经济四腿
out.append("\n[② sell / surplus_sell]")
for name in ("sell", "surplus_sell", "surplus_sell_skip", "sell_failed"):
    for i, r in enumerate(recs):
        if r.get("event") == name:
            out.append(f"#{i} {name} {json.dumps(r, ensure_ascii=False)[:400]}")

# 教训库
out.append("\n[L0 教训库]")
lp = os.path.join(LOGS, "longrun-3day-llm-run9b-lessons.json")
data = json.load(open(lp, encoding="utf-8"))
out.append(f"size={os.path.getsize(lp)} total={len(data.get('lessons', []))}")
for it in data.get("lessons", []):
    out.append(f"  {it['id']} count={it['count']} day={it['first_day']}→{it['last_day']} sev={it['severity']} "
               f"evidence={it.get('evidence')!r} hint={it.get('hint')!r}")

# 两侧工具判决行
out.append("\n[两侧工具判决行]")
for fname in ("run9b-verify.txt", "run9b-analyze.txt"):
    p = os.path.join(LOGS, fname)
    out.append(f"-- {fname} --")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if re.search(r"verdict|结论|尾部连续|VERIFIED:|窗口:|红 \d+ 条|达标", line):
                out.append("   " + line.rstrip())

# Lead 复核器
out.append("\n[scratch/run9-lead-check.py --help]")
proc = subprocess.run([sys.executable, os.path.join(ROOT, "scratch", "run9-lead-check.py"), "--help"],
                      cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
out.append((proc.stdout or "") + (proc.stderr or ""))

text = "\n".join(out)
with open(os.path.join(LOGS, "run9b-brief.txt"), "w", encoding="utf-8") as fh:
    fh.write(text + "\n")
print(text)
