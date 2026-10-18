# -*- coding: utf-8 -*-
"""smoke-0742 账本摘要（只读）：给 `docs/_smoke-0742.md` 与给 Lead 的报数用。

输出落 `logs/smoke-0742-digest.txt`，同时在 stdout 打印关键段。
"""
from __future__ import annotations

import json
import re
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
JOURNAL = os.path.join(REPO, "logs", "longrun-smoke-0742.jsonl")
OUT = os.path.join(REPO, "logs", "smoke-0742-digest.txt")
GUARD = re.compile(r"耕地空着（手上有\s*\d+\s*粒种子）⇒\s*该去种")

recs = []
bad = 0
with open(JOURNAL, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except Exception:  # noqa: BLE001
            bad += 1

buf: list[str] = []


def w(s: str = "") -> None:
    buf.append(s)
    print(s)


w(f"账本 {JOURNAL}")
w(f"记录 {len(recs)} 条 / JSON 解析失败 {bad} 条 / mtime {os.path.getmtime(JOURNAL):.3f}")

cnt = collections.Counter(r.get("event") for r in recs)
w("\n=== 事件计数 ===")
for k, v in cnt.most_common():
    w(f"  {k:24} {v}")

fin = [r for r in recs if r.get("event") == "finish"]
w("\n=== finish ===")
w(json.dumps(fin, ensure_ascii=False, indent=2)[:1200])

w("\n=== day_end ===")
for r in [r for r in recs if r.get("event") == "day_end"]:
    day = r.get("day")
    w(f"- day={day} ended_by={r.get('ended_by')} verified={r.get('verified')} t={r.get('t')}")
    w(f"  day_after={r.get('day_after')} ok={r.get('ok_steps')} skip={r.get('skipped_steps')} fail={r.get('failed_steps')}")
    w(f"  ended_reason = {(r.get('ended_reason') or '')[:300]}")
    w(f"  checks = {json.dumps(r.get('checks'), ensure_ascii=False)}")
    fw = r.get("final_water") or {}
    w(f"  final_water = {json.dumps({k: fw.get(k) for k in ('scope', 'tiles', 'crops', 'dry')}, ensure_ascii=False)}")
    st = r.get("stages") or []
    for s in st:
        if s.get("stage") == "clear_area":
            w(f"  clear_area: ok={s.get('ok')} cleared_tiles={s.get('cleared_tiles')} "
              f"failed={s.get('failed')} leftover={s.get('leftover')} stopped={s.get('stopped')!r}")
    ic = r.get("intent_coverage")
    w(f"  intent_coverage = {json.dumps(ic, ensure_ascii=False)[:900] if ic else None}")

guard_hits = []
for r in recs:
    blob = json.dumps(r, ensure_ascii=False)
    for m in GUARD.finditer(blob):
        guard_hits.append({"event": r.get("event"), "t": r.get("t"), "day": r.get("day"), "text": m.group(0)})
w(f"\n=== 旧守卫文案「该去种」命中 {len(guard_hits)} 次 ===")
for h in guard_hits[:6]:
    w(f"  {h}")

w("\n=== blocked 记录 ===")
blocked = [r for r in recs if r.get("event") == "blocked"]
w(f"共 {len(blocked)} 条")
for r in blocked:
    blob = json.dumps(r, ensure_ascii=False)
    w(f"- t={r.get('t')} kind={r.get('kind')} tile={r.get('tile') or r.get('tiles')} "
      f"calls={r.get('calls')} bound={'tool_ineffective_bound' in blob} "
      f"tool_ineffective={'tool_ineffective' in blob}")
    w(f"  reason = {(r.get('reason') or '')[:280]}")

w("\n=== deferred_by_budget ===")
for r in [r for r in recs if r.get("event") == "deferred_by_budget"]:
    w(f"- t={r.get('t')} task={r.get('task')} why={r.get('why')!r} "
      f"预算匹配={bool(re.search(r'预算\s*\d+', json.dumps(r, ensure_ascii=False)))} "
      f"已砍匹配={bool(re.search(r'已砍\s*\d+', json.dumps(r, ensure_ascii=False)))}")

w("\n=== slot_relief / harvest / 其它关键事件 ===")
for name in ("slot_relief", "slot_relief_skip", "no_progress_burst", "policy_fallback",
             "seed_unavailable_today", "harvest_gave_up", "tool_ineffective"):
    hit = [r for r in recs if r.get("event") == name]
    w(f"  {name:22} {len(hit)}")
    for r in hit[:3]:
        w(f"    {json.dumps(r, ensure_ascii=False)[:300]}")

w("\n=== clear_area ok vs cleared_tiles（步 5 证据面）===")
tot_ok = tot_clear = 0
bad_rows = []
for r in [r for r in recs if r.get("event") == "day_end"]:
    for s in (r.get("stages") or []):
        if s.get("stage") != "clear_area":
            continue
        ok = s.get("ok") or 0
        cl = s.get("cleared_tiles")
        n_cl = len(cl) if isinstance(cl, list) else (cl if isinstance(cl, int) else None)
        tot_ok += ok
        tot_clear += (n_cl or 0)
        if n_cl is None or n_cl != ok:
            bad_rows.append({"day": r.get("day"), "ok": ok, "cleared": n_cl,
                             "failed": s.get("failed"), "leftover": s.get("leftover")})
w(f"  clear_area ok 合计 {tot_ok} / cleared_tiles 合计 {tot_clear}")
w(f"  ok != cleared 的阶段 {len(bad_rows)} 段：{bad_rows}")

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(buf) + "\n")
print(f"\n[digest] 已写 {OUT}")
sys.exit(0)
