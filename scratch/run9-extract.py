# -*- coding: utf-8 -*-
"""run9 全量取证（只读）：账本结构化摘要 + SMAPI 窗口计数 + 两个检查器输出。

另含一步**订正**：run8-snapshot.py 的默认输出文件是 run8 那份，run9 的 end 行被误追加到
`scratch/run8-external-snapshots.jsonl`；本脚本把 journal_path 含 run9 的行搬回
`scratch/run9-external-snapshots.jsonl`，并原样重写 run8 那份（不改内容）。

产出：
  logs/run9-journal-extract.txt   账本摘要
  logs/run9-smapi-counts.txt      SMAPI 冻结窗口的计数与行号
  logs/run9-verify.txt            tools/verify-run3.py 输出
  logs/run9-analyze.txt           tools/analyze-longrun.py 输出
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOGS = os.path.join(ROOT, "logs")
SCRATCH = os.path.join(ROOT, "scratch")
PY = sys.executable

WATCH_EVENTS = [
    "buy", "sell", "surplus_sell", "seed_gate", "cannot_afford", "economy",
    "sleep", "day_start", "day_end", "no_day_progress", "finish", "day_cap",
    "modal_dismissed", "modal_blocked", "event_blocked", "policy", "blocked",
    "stuck_flush", "stage_exhausted", "plot_exhausted", "unreachable_summary",
    "review_llm", "review_llm_failed", "lessons", "lessons_rejected",
    "plant_area", "sow", "refill", "goto_farm", "water_far", "clear_dead",
    "clear_neighbor", "frontier_clear", "resume_walk", "idle", "plot_walk",
]
KEYWORDS = ["eventUp", "modal", "ShopMenu", "LevelUp", "DialogueBox", "ShippingMenu",
            "professionsToChoose", "farm_evidence_unavailable"]


def fix_snapshots(log=print) -> None:
    """把误落到 run8 文件里的 run9 行搬回 run9 文件。"""
    r8 = os.path.join(SCRATCH, "run8-external-snapshots.jsonl")
    r9 = os.path.join(SCRATCH, "run9-external-snapshots.jsonl")
    if not os.path.exists(r8):
        log("[订正] run8 快照文件不存在，跳过")
        return
    keep, moved = [], []
    with open(r8, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            obj = json.loads(line)
            if "run9" in str(obj.get("journal_path", "")):
                moved.append(line)
            else:
                keep.append(line)
    if not moved:
        log("[订正] run8 文件里没有 run9 行，无需订正")
        return
    with open(r8, "w", encoding="utf-8", newline="\n") as fh:
        for line in keep:
            fh.write(line + "\n")
    existing = []
    if os.path.exists(r9):
        with open(r9, encoding="utf-8") as fh:
            existing = [ln.rstrip("\n") for ln in fh if ln.strip()]
    with open(r9, "w", encoding="utf-8", newline="\n") as fh:
        for line in existing + moved:
            fh.write(line + "\n")
    log(f"[订正] run8 保留 {len(keep)} 行 / run9 现有 {len(existing)} 行 + 搬入 {len(moved)} 行 = {len(existing) + len(moved)} 行")


def clock_of(fin):
    if not isinstance(fin, dict):
        return "?"
    return fin.get("day")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=os.path.join(LOGS, "longrun-3day-llm-run9.jsonl"))
    ap.add_argument("--smapi", default=os.path.join(LOGS, "run9-smapi-window.txt"))
    ap.add_argument("--window-start", default="20:40:40")
    ap.add_argument("--window-end", default="21:04:17")
    args = ap.parse_args()

    fix_snapshots()

    recs = []
    with open(args.journal, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))

    out = []
    out.append(f"账本 = {args.journal}（{len(recs)} 行）")
    counts = Counter(r.get("event") for r in recs)
    out.append("事件计数：" + json.dumps(dict(sorted(counts.items())), ensure_ascii=False))
    decisions = [r for r in recs if r.get("event") == "decision"]
    llm = [r for r in decisions if r.get("llm") is True]
    src = Counter(r.get("source") for r in decisions)
    out.append(f"decision = {len(decisions)} 条；llm=true {len(llm)}；source={dict(src)}；"
               f"truncated={sum(1 for r in decisions if r.get('truncated'))}；"
               f"fallback 非空={sum(1 for r in decisions if r.get('fallback'))}")
    bnd = Counter(r.get("boundary") for r in decisions)
    out.append(f"boundary = {dict(bnd)}")

    out.append("\n=== 经济闭环（sell / surplus_sell / buy / seed_gate / cannot_afford）===")
    for i, r in enumerate(recs):
        e = r.get("event")
        if e in ("sell", "surplus_sell", "buy", "seed_gate", "cannot_afford", "plant_area", "sow"):
            out.append(f"#{i} {e} t={r.get('t')} " + json.dumps(
                {k: v for k, v in r.items() if k not in ("event", "t")}, ensure_ascii=False)[:600])

    out.append("\n=== 逐日 day_start / day_end ===")
    for i, r in enumerate(recs):
        e = r.get("event")
        if e == "day_start":
            fin = r.get("final") or {}
            out.append(f"#{i} day_start t={r.get('t')} loc={fin.get('location')} money={fin.get('money')} "
                       f"crops={fin.get('crops')} unwatered={fin.get('unwatered_crops')} scope={fin.get('counts_scope')}")
        elif e == "day_end":
            fin = r.get("final") or {}
            st = r.get("stages") or []
            per = Counter()
            for s in st:
                per[s.get("stage")] += s.get("ok", 0)
            out.append(f"#{i} day_end t={r.get('t')} ended_by={r.get('ended_by')} verified={r.get('verified')} "
                       f"day_after={r.get('day_after')} ok={r.get('ok_steps')} skip={r.get('skipped_steps')} "
                       f"fail={len(r.get('failed_steps') or [])}")
            out.append(f"    reason: {(r.get('ended_reason') or '')[:400]}")
            out.append(f"    checks: {json.dumps(r.get('checks'), ensure_ascii=False)}")
            out.append(f"    final: money={fin.get('money')} crops={fin.get('crops')} dead={fin.get('dead_crops')} "
                       f"unwatered={fin.get('unwatered_crops')} seeds={fin.get('seeds')} tile={fin.get('tile')} "
                       f"tod={fin.get('timeOfDay')} loc={fin.get('location')} scope={fin.get('counts_scope')}")
            farm = fin.get("farm") or {}
            out.append(f"    farm: crops={farm.get('crops')} dry={farm.get('dryCrops')} dryDead={farm.get('dryDeadCrops')} "
                       f"unwatered={farm.get('unwateredCrops')} hoeDirt={farm.get('hoeDirt')}")
            out.append(f"    final_water: {json.dumps(r.get('final_water'), ensure_ascii=False)[:300]}")
            out.append(f"    stages={len(st)} 汇总 tiles={sum(s.get('tiles', 0) for s in st)} "
                       f"ok={sum(s.get('ok', 0) for s in st)} fail={sum(s.get('failed_any', 0) for s in st)} "
                       f"leftover={sum(s.get('leftover', 0) for s in st)}；stage ok={dict(per)}")

    out.append("\n=== 点名事件 / 关键词 ===")
    for ev in ("modal_dismissed", "modal_blocked", "event_blocked", "stuck_flush", "no_day_progress",
               "review_llm", "review_llm_failed", "lessons", "lessons_rejected", "policy", "finish", "day_cap"):
        hits = [(i, r) for i, r in enumerate(recs) if r.get("event") == ev]
        out.append(f"[{ev}] {len(hits)} 条")
        for i, r in hits[:6]:
            out.append(f"    #{i} t={r.get('t')} " + json.dumps(
                {k: v for k, v in r.items() if k not in ("event", "t")}, ensure_ascii=False)[:300])
    raw = open(args.journal, encoding="utf-8").read()
    out.append("原文关键词命中：" + json.dumps({k: raw.count(k) for k in KEYWORDS}, ensure_ascii=False))

    jtext = "\n".join(out)
    with open(os.path.join(LOGS, "run9-journal-extract.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(jtext + "\n")
    print(jtext[:6000])

    # ---- SMAPI 窗口 ----
    pat_ts = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")
    lines = open(args.smapi, encoding="utf-8", errors="replace").read().splitlines()
    in_win = []
    for idx, ln in enumerate(lines, 1):
        m = pat_ts.match(ln)
        if not m:
            continue
        ts = m.group(1)
        if args.window_start <= ts <= args.window_end:
            in_win.append((idx, ts, ln))
    pats = {
        "newday": "Synchronizing 'NewDay' task",
        "before_save": "Context: before save.",
        "save_called": "SaveGame.Save() called.",
        "save_task": "Synchronizing 'Save' task",
        "completed": "completed without exceptions",
        "after_save": "after save, starting",
    }
    noise = ["ERROR", "Disconnected", "ClosedGame", "Disposing", "soft_oal", "Warping to Farm"]
    s = [f"SMAPI 冻结文件 = {args.smapi}", f"总行数 = {len(lines)}；窗口 {args.window_start}–{args.window_end} 内 {len(in_win)} 行"]
    for k, needle in pats.items():
        hits = [(i, ts) for i, ts, ln in in_win if needle in ln]
        s.append(f"[{k}] {len(hits)} 次：行号/时间 {hits}")
    s.append("噪声计数：" + json.dumps({n: sum(1 for _, _, ln in in_win if n in ln) for n in noise}, ensure_ascii=False))
    stext = "\n".join(s)
    with open(os.path.join(LOGS, "run9-smapi-counts.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(stext + "\n")
    print("\n" + stext)

    # ---- 两个检查器 ----
    for name, cmd, dst in (
        ("verify-run3", [PY, os.path.join(ROOT, "tools", "verify-run3.py"), "--journal", args.journal, "--days", "3"],
         os.path.join(LOGS, "run9-verify.txt")),
        ("analyze-longrun", [PY, os.path.join(ROOT, "tools", "analyze-longrun.py"), "--journal", args.journal],
         os.path.join(LOGS, "run9-analyze.txt")),
    ):
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        body = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
        with open(dst, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        print(f"\n=== {name} rc={p.returncode} → {os.path.relpath(dst, ROOT)} ===")
        print(body[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
