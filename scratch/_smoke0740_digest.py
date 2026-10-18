# -*- coding: utf-8 -*-
"""0.7.40 冒烟 step4/6/7 取证摘要（只读，离线）。"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
JL = os.path.join(ROOT, "logs", "longrun-smoke-0740.jsonl")
SMAPI = os.path.join(ROOT, "logs", "smoke-0740-smapi-window.txt")
SRC = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")

L = [json.loads(x) for x in open(JL, encoding="utf-8")]
print(f"journal_lines={len(L)}")
c = collections.Counter(r.get("event") for r in L)
print("events=" + json.dumps(dict(c), ensure_ascii=False))

print("\n=== finish ===")
for r in L:
    if r.get("event") == "finish":
        print(json.dumps(r, ensure_ascii=False))

print("\n=== day_end ===")
for r in L:
    if r.get("event") != "day_end":
        continue
    de = r
    ic = de.get("intent_coverage") or []
    print(f"{de.get('day')} ended_by={de.get('ended_by')} verified={de.get('verified')} "
          f"ok/skip/fail={de.get('ok_steps')}/{de.get('skipped_steps')}/{de.get('failed_steps')} "
          f"intent_coverage_n={len(ic)} checks={json.dumps(de.get('checks'), ensure_ascii=False)}")
    print("   reason=" + str(de.get("ended_reason"))[:260])
    for e in ic:
        print(f"   ic {e.get('intent')}: req={e.get('requested_tiles')} ok={e.get('ok_tiles')} "
              f"failed={e.get('failed_tiles')} unexec={e.get('unexecuted_tiles')} steps={e.get('executed_steps')} "
              f"reasons={e.get('reasons')}")

print("\n=== slot_relief ===")
for r in L:
    if r.get("event") != "slot_relief":
        continue
    print(json.dumps({k: r.get(k) for k in ("t", "need", "freed", "shipped", "freeSlots_before", "freeSlots_after",
                                            "round", "before_free", "after_free", "money_before", "money_after",
                                            "rows_before", "rows_after", "failed", "blocked_reason", "sold")},
                     ensure_ascii=False)[:900])
print("\n=== sell ===")
for r in L:
    if r.get("event") == "sell":
        print(json.dumps({k: r.get(k) for k in ("t", "qid", "stack", "slot", "ok", "money_before", "money_after",
                                                "rows_before", "rows_after", "why", "error")}, ensure_ascii=False)[:400])
print("\n=== inventory_blocked ===")
for r in L:
    if r.get("event") == "inventory_blocked":
        print(json.dumps(r, ensure_ascii=False)[:500])

print("\n=== step5 clear_area ===")
for r in L:
    if r.get("event") != "day_end":
        continue
    for st in (r.get("stages") or []):
        if st.get("stage") == "clear_area":
            print(f"{r.get('day')} clear_area tiles={st.get('tiles')} ok={st.get('ok')} "
                  f"cleared_tiles={len(st.get('cleared_tiles') or [])}")

print("\n=== SMAPI 六串 ===")
if os.path.exists(SMAPI):
    st = os.stat(SMAPI)
    h = hashlib.sha256(open(SMAPI, "rb").read()).hexdigest().upper()
    hsrc = hashlib.sha256(open(SRC, "rb").read()).hexdigest().upper() if os.path.exists(SRC) else "<no src>"
    print(f"frozen size={st.st_size} mtime={st.st_mtime} sha256={h}  byte_identical={h == hsrc} (src_sha={hsrc[:16]}…)")
    lines = open(SMAPI, encoding="utf-8", errors="replace").read().splitlines()
    pats = {
        "NewDay": lambda s: "Synchronizing 'NewDay' task" in s,
        "before_save": lambda s: "Context: before save." in s,
        "Save_called": lambda s: ("SaveGame.Save() called." in s and TS.match(s) and " by AgentFarm " not in s and "| v0." not in s),
        "Save_called_raw": lambda s: ("SaveGame.Save() called." in s and TS.match(s)),
        "Save_task": lambda s: "Synchronizing 'Save' task" in s,
        "completed": lambda s: "completed without exceptions" in s,
        "after_save": lambda s: "after save, starting" in s,
    }
    for name, fn in pats.items():
        hits = [(i, (TS.match(s).group(1) if TS.match(s) else "?")) for i, s in enumerate(lines, 1) if fn(s)]
        print(f"  {name:16} = {len(hits):2}  {hits}")
    for kw in ("Warping to Farm", "ERROR", "Disconnected", "ClosedGame", "Disposing", "soft_oal", "Exception",
               "GET /v1/observe"):
        print(f"  {kw:18} = {sum(1 for s in lines if kw in s)}")

print("\n=== analyze / verify 摘要 ===")
for name in ("smoke-0740-analyze.txt", "smoke-0740-verify.txt"):
    p = os.path.join(ROOT, "logs", name)
    if not os.path.exists(p):
        print(f"{name}: 不存在")
        continue
    txt = open(p, encoding="utf-8", errors="replace").read()
    print(f"--- {name} ({len(txt)} chars) ---")
    keep = []
    for ln in txt.splitlines():
        if any(k in ln for k in ("意图", "intent", "§8", "missed:intent", "VERIFIED", "verdict", "0 步",
                                 "原因码", "红", "无法判定")):
            keep.append(ln.strip())
    for ln in keep[:40]:
        print("   " + ln[:220])

print("\n=== gaps ===")
g = os.path.join(ROOT, "logs", "longrun-smoke-0740-gaps.json")
if os.path.exists(g):
    d = json.load(open(g, encoding="utf-8"))
    print(f"exists size={os.path.getsize(g)} keys={list(d.keys())}")
    print(json.dumps(d, ensure_ascii=False)[:1200])
else:
    print("不存在")
