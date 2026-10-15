# -*- coding: utf-8 -*-
"""run8 全量取证（只读）：账本分析 + SMAPI 窗口冻结与计数 + 两个检查器输出。

产出：
  logs/run8-journal-extract.txt   账本结构化摘要（事件计数 / 点名事件原文 / 逐日 / 决策来源）
  logs/run8-smapi-window.txt      SMAPI-latest.txt 的冻结副本（字节复制）
  logs/run8-verify.txt            tools/verify-run3.py 输出
  logs/run8-analyze.txt           tools/analyze-longrun.py 输出
控制台只打印紧凑摘要。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOGS = os.path.join(ROOT, "logs")
PY = sys.executable

WATCH_EVENTS = [
    "buy", "sell", "surplus_sell", "seed_gate", "money", "economy",
    "sleep", "day_start", "day_end", "no_day_progress", "finish", "day_cap",
    "modal_dismissed", "modal_blocked", "event_blocked", "policy",
    "blocked", "stuck_flush", "stage_exhausted", "plot_exhausted",
    "unreachable_summary", "review", "refill", "goto_farm",
]
KEYWORDS = ["eventUp", "modal", "ShopMenu", "LevelUp", "DialogueBox", "ShippingMenu", "professionsToChoose"]


def jdump(obj, limit=4000):
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + f"…（截断，原长 {len(s)}）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=os.path.join(LOGS, "longrun-3day-llm-run8.jsonl"))
    args = ap.parse_args()
    journal = args.journal if os.path.isabs(args.journal) else os.path.join(ROOT, args.journal)

    recs = []
    with open(journal, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    out = []
    w = out.append
    w(f"账本：{journal}")
    w(f"总记录 = {len(recs)}")
    w("\n=== 事件计数 ===")
    w(jdump(dict(sorted(Counter(r.get("event") for r in recs).items())), 6000))

    w("\n=== 点名事件原文（全量） ===")
    for i, r in enumerate(recs):
        if r.get("event") in WATCH_EVENTS:
            w(f"#{i:3} {jdump(r, 3000)}")

    w("\n=== 决策来源 ===")
    dec = [r for r in recs if r.get("event") == "decision"]
    w(f"decision 条数 = {len(dec)}")
    w(f"llm==true = {sum(1 for r in dec if r.get('llm') is True)} / source=llm = {sum(1 for r in dec if r.get('source') == 'llm')}")
    w(f"truncated = {sum(1 for r in dec if r.get('truncated'))} / fallback 非空 = {sum(1 for r in dec if r.get('fallback'))}")
    w(f"boundary = {jdump(dict(Counter(str(r.get('boundary')) for r in dec)))}")
    w(f"intent = {jdump(dict(Counter(r.get('intent') or r.get('intent_kind') or '?' for r in dec)))}")

    w("\n=== 逐日 day_start / day_end ===")
    for i, r in enumerate(recs):
        ev = r.get("event")
        if ev == "day_start":
            fin = r.get("final") or r
            w(f"day_start #{i:3} t={r.get('t')} {jdump({k: fin.get(k) for k in ('day', 'timeOfDay', 'location', 'stamina', 'money', 'crops', 'unwatered_crops', 'dryCrops', 'seeds', 'waterLeft', 'tile')}, 800)}")
        elif ev == "day_end":
            fin = r.get("final") or {}
            w(f"day_end #{i:3} t={r.get('t')} day={r.get('day')} day_text={r.get('day_text')} ended_by={r.get('ended_by')} verified={r.get('verified')} day_after={r.get('day_after')}")
            w(f"    started_at={r.get('started_at')} ok={r.get('ok_steps')} skip={r.get('skipped_steps')} fail={r.get('failed_steps')}")
            w(f"    checks={jdump(r.get('checks'), 1200)}")
            w(f"    final={jdump(fin, 1500)}")
            w(f"    final_water={jdump(r.get('final_water'), 1200)}")
            st = r.get("stages") or []
            agg = Counter()
            for s in st:
                agg["tiles"] += s.get("tiles", 0) or 0
                agg["ok"] += s.get("ok", 0) or 0
                agg["failed"] += s.get("failed", 0) or 0
                agg["failed_any"] += s.get("failed_any", 0) or 0
                agg["leftover"] += s.get("leftover", 0) or 0
            w(f"    stages={len(st)} 段汇总={jdump(dict(agg))}")
            w(f"    ended_reason={(r.get('ended_reason') or '')[:900]}")
            w(f"    notes={jdump(r.get('notes'), 1200)}")

    w("\n=== 关键词扫描（整份账本） ===")
    raw = open(journal, encoding="utf-8").read().splitlines()
    for kw in KEYWORDS:
        hits = [(i + 1, ln) for i, ln in enumerate(raw) if kw in ln]
        w(f"{kw!r}: {len(hits)} 行")
        for no, ln in hits[:6]:
            w(f"    L{no} {ln[:400]}")

    with open(os.path.join(LOGS, "run8-journal-extract.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"[i] 账本摘要已写 logs/run8-journal-extract.txt（{len(out)} 行）")
    print("\n".join(out[:40]))

    # --- SMAPI 冻结 + 计数 ---
    src = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
    dst = os.path.join(LOGS, "run8-smapi-window.txt")
    shutil.copyfile(src, dst)
    data = open(dst, encoding="utf-8", errors="replace").read().splitlines()
    sha = hashlib.sha256(open(dst, "rb").read()).hexdigest().upper()
    st = os.stat(dst)
    lines = [f"SMAPI 冻结副本：{dst}",
             f"大小 = {st.st_size} B / mtime_ns = {st.st_mtime_ns} / SHA256 = {sha}",
             f"行数 = {len(data)}"]
    for pat in ["Synchronizing 'NewDay' task", "Context: before save.", "SaveGame.Save() called.",
                "Synchronizing 'Save' task", "completed without exceptions", "after save, starting",
                "ERROR", "Disconnected", "ClosedGame", "Disposing", "Exception", "soft_oal",
                "Warping to Farm", "checkForEvents", "eventUp", "DialogueBox", "LevelUpMenu",
                "ShopMenu", "ShippingMenu", "TouchAction"]:
        hits = [(i + 1, ln) for i, ln in enumerate(data) if pat in ln]
        lines.append(f"\n=== {pat!r}: {len(hits)} 次")
        for no, ln in hits[:14]:
            m = re.match(r"\[(\d\d:\d\d:\d\d)", ln)
            lines.append(f"  L{no} {(m.group(1) if m else '??')} {ln.split('] ', 1)[-1][:160]}")
    with open(os.path.join(LOGS, "run8-smapi-counts.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"[i] SMAPI 冻结 = {st.st_size} B / {len(data)} 行 / SHA256 {sha[:16]}…")
    print("[i] SMAPI 计数已写 logs/run8-smapi-counts.txt")

    # --- 两个检查器 ---
    for name, cmd in [
        ("run8-verify.txt", [PY, os.path.join(ROOT, "tools", "verify-run3.py"), "--journal", journal, "--days", "3"]),
        ("run8-analyze.txt", [PY, os.path.join(ROOT, "tools", "analyze-longrun.py"), "--journal", journal]),
    ]:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        with open(os.path.join(LOGS, name), "w", encoding="utf-8") as fh:
            fh.write(f"$ {' '.join(cmd)}\n# exit code = {p.returncode}\n\n{p.stdout}\n\n[stderr]\n{p.stderr}\n")
        print(f"[i] {name} → exit code = {p.returncode}（全文见 logs\\{name}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
