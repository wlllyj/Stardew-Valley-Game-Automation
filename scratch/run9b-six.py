# -*- coding: utf-8 -*-
"""run9b 六问取证（只读）→ logs/run9b-six.txt

按 task-131 §8 的六问，从账本里把每条可证伪的原文抓出来：
① 落盘配对（已在 run9b-smapi-chain.txt / 快照里）
② 经济闭环四腿（sell / surplus_sell / buy / buy_partial / plant_area stage ok）
③ 死苗（dead_crops / dry_dead / gave_up_tiles）
④ review_only_fallback / review_only_no_target / plot_exhausted_burst 生效与有界
⑤ farm_evidence_unavailable 是否伴随假 VERIFIED
⑥ buy_partial / no_space 读数
另附：起止快照原文两行；两侧工具 verdict / strict_verdict 两行。
"""
from __future__ import annotations

import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOGS = os.path.join(ROOT, "logs")
JOURNAL = os.path.join(LOGS, "longrun-3day-llm-run9b.jsonl")
SNAPSHOTS = os.path.join(ROOT, "scratch", "run9b-external-snapshots.jsonl")

out: list[str] = []


def dump(title: str, obj) -> None:
    out.append(f"\n--- {title} ---")
    out.append(json.dumps(obj, ensure_ascii=False, indent=1))


recs = []
with open(JOURNAL, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            recs.append(json.loads(line))
out.append(f"账本 {JOURNAL}：{len(recs)} 行")

# ③ 死苗 / 认输格（逐日）
out.append("\n=== ③ 死苗 / dry_dead / gave_up_tiles（逐日 day_end） ===")
for i, r in enumerate(recs):
    if r.get("event") != "day_end":
        continue
    out.append(
        f"#{i} day_after={r.get('day_after')} ended_by={r.get('ended_by')} "
        f"dead_crops={r.get('dead_crops')} dry_dead={r.get('dry_dead')} "
        f"gave_up_tiles={r.get('gave_up_tiles')} final(dead/drydead)="
        f"{ {k: v for k, v in (r.get('final') or {}).items() if 'dead' in k or 'gave' in k} }"
    )
for name in ("dead_crops_summary", "clear_dead_scope"):
    for i, r in enumerate(recs):
        if r.get("event") == name:
            dump(f"#{i} {name}", r)

# ④ review 兜底 / 换片连发
out.append("\n=== ④ review 兜底 / 换片连发（原文） ===")
for name in ("review_only_fallback", "review_only_fallback_failed", "review_only_no_target",
             "plot_exhausted_burst", "plot_exhausted", "intent_vetoed"):
    hits = [(i, r) for i, r in enumerate(recs) if r.get("event") == name]
    out.append(f"\n[{name}] 共 {len(hits)} 条")
    for i, r in hits[:8]:
        dump(f"#{i} {name}", r)

# ⑤ farm_evidence_unavailable
out.append("\n=== ⑤ farm_evidence_unavailable / 证据可用性 ===")
for name in ("farm_evidence_unavailable", "farm_evidence"):
    hits = [(i, r) for i, r in enumerate(recs) if r.get("event") == name]
    out.append(f"[{name}] {len(hits)} 条")
    for i, r in hits[:5]:
        dump(f"#{i} {name}", r)
# 关键词扫描（任何字段里出现）
kw = "farm_evidence"
hits_kw = [(i, r.get("event")) for i, r in enumerate(recs) if kw in json.dumps(r, ensure_ascii=False)]
out.append(f"含关键字 {kw!r} 的记录：{hits_kw}")

# ⑥ buy_partial / no_space
out.append("\n=== ⑥ buy / buy_partial / 空格 相关（原文） ===")
for name in ("buy_partial", "buy_no_space", "cannot_afford", "seed_unavailable_today", "buy"):
    hits = [(i, r) for i, r in enumerate(recs) if r.get("event") == name]
    out.append(f"\n[{name}] 共 {len(hits)} 条")
    for i, r in hits[:6]:
        dump(f"#{i} {name}", r)
hits_ns = [(i, r.get("event")) for i, r in enumerate(recs) if "no_space" in json.dumps(r, ensure_ascii=False) or "no_inventory_space" in json.dumps(r, ensure_ascii=False)]
out.append(f"含 no_space / no_inventory_space 的记录：{hits_ns}")

# ② 经济闭环四腿
out.append("\n=== ② 经济闭环四腿 ===")
for name in ("sell", "surplus_sell", "surplus_sell_skip", "sell_failed"):
    for i, r in enumerate(recs):
        if r.get("event") == name:
            dump(f"#{i} {name}", r)
out.append("\n[逐日 day_start 的钱/种子]")
for i, r in enumerate(recs):
    if r.get("event") == "day_start":
        fin = r.get("final") or {}
        out.append(f"#{i} t={r.get('t')} day={r.get('day')} money={fin.get('money')} seeds={fin.get('seeds')} loc={(fin.get('location') if not isinstance(fin.get('location'), dict) else fin['location'].get('name'))}")
out.append("\n[逐日 stages 里 plant_area / water_area 的 ok]")
for i, r in enumerate(recs):
    if r.get("event") != "day_end":
        continue
    st = r.get("stages") or []
    agg: dict[str, dict] = {}
    for s in st:
        k = s.get("stage")
        a = agg.setdefault(k, {"tiles": 0, "ok": 0, "skipped": 0, "failed": 0, "leftover": 0})
        for f in ("tiles", "ok", "skipped", "failed", "leftover"):
            a[f] += s.get(f) or 0
    out.append(f"#{i} day_after={r.get('day_after')}: {json.dumps(agg, ensure_ascii=False)}")

# lessons 注入与 LLM 复盘
out.append("\n=== LLM 演进（review_llm / review_llm_failed / lessons） ===")
for name in ("review_llm", "review_llm_failed", "lessons", "lessons_rejected"):
    hits = [(i, r) for i, r in enumerate(recs) if r.get("event") == name]
    out.append(f"[{name}] {len(hits)} 条")
    for i, r in hits[:4]:
        dump(f"#{i} {name}", r)

# 起止快照原文
out.append("\n=== 起止快照原文（scratch/run9b-external-snapshots.jsonl） ===")
if os.path.exists(SNAPSHOTS):
    with open(SNAPSHOTS, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.append(json.dumps(json.loads(line), ensure_ascii=False, indent=1))
else:
    out.append("（文件不存在）")

# 两侧工具的 verdict / strict_verdict 行
out.append("\n=== 两侧工具判决行 ===")
import re  # noqa: E402
for fname in ("run9b-verify.txt", "run9b-analyze.txt"):
    p = os.path.join(LOGS, fname)
    out.append(f"\n--- {fname} ---")
    if not os.path.exists(p):
        out.append("（不存在）")
        continue
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            if re.search(r"verdict|VERIFIED|结论|达标|尾部|history_problems|严格|strict", line, re.I):
                out.append(line.rstrip())

text = "\n".join(out)
with open(os.path.join(LOGS, "run9b-six.txt"), "w", encoding="utf-8") as fh:
    fh.write(text + "\n")
print(text)
