# -*- coding: utf-8 -*-
"""task-18 冒烟（smoke-0745）证据抽取器：只读，不碰游戏。

输入：logs/longrun-smoke-0745.jsonl、logs/smoke-0745-smapi-window.txt、
      scratch/smoke-0745.json、logs/longrun-smoke-0745.version.json
输出：scratch/_t18_smoke_lines.txt（逐行/逐字段摘要）、
      scratch/_t18_smoke_dayend.txt（两日 day_end 结构化摘要）
"""
import hashlib
import json
import os
import re
import collections

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOURNAL = os.path.join(REPO, "logs", "longrun-smoke-0745.jsonl")
SMAPI = os.path.join(REPO, "logs", "smoke-0745-smapi-window.txt")
RESULT = os.path.join(REPO, "scratch", "smoke-0745.json")
SIDECAR = os.path.join(REPO, "logs", "longrun-smoke-0745.version.json")
OUT_LINES = os.path.join(REPO, "scratch", "_t18_smoke_lines.txt")
OUT_DAYEND = os.path.join(REPO, "scratch", "_t18_smoke_dayend.txt")

DAYEND_KEYS = [
    "event", "t", "day", "day_text", "started_at", "ended_by", "ended_reason",
    "verified", "checks", "day_after", "ok_steps", "skipped_steps", "failed_steps",
    "unreachable", "unreachable_bound", "unreachable_exempt",
    "refused", "refused_bound", "refused_exempt", "bound_basis",
    "encircled", "encircled_tiles", "stuck_flushed", "slept_without_work", "slept_ok",
    "dead_crops", "dry_dead", "gave_up_tiles", "assigned_undone",
    "plot_pending", "plot_pending_by_kind", "plot_pending_executable", "plot_pending_blocked",
    "pending_ledger", "pending_guard", "pending_stalled", "pending_executable",
    "pending_blocked", "pending_unobserved", "pending_malformed",
    "stage_midway_leftover", "free_slots_start", "free_slots_last", "free_slots_min",
    "free_slots_status", "loot_lost_steps", "loot_lost_items", "deferred_tiles",
    "scope_shed", "scope_shed_tiles", "stamina_budget", "stamina_calibration",
    "gaps_problem",
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load_journal():
    rows = []
    with open(JOURNAL, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((i, json.loads(line)))
            except json.JSONDecodeError as e:
                rows.append((i, {"event": "_BAD_LINE", "error": str(e)}))
    return rows


def shrink(v, limit=700):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "...<truncated>"


def day_event_counts(rows):
    counts = collections.Counter()
    per_day = collections.defaultdict(collections.Counter)
    for _, ev in rows:
        name = ev.get("event")
        counts[name] += 1
        day = ev.get("day")
        if isinstance(day, list):
            per_day["%s%s" % (day[1], day[2])][name] += 1
    return counts, per_day


def main():
    rows = load_journal()
    counts, per_day = day_event_counts(rows)
    out = []
    out.append("== 文件 ==")
    for p in (JOURNAL, SMAPI, RESULT, SIDECAR):
        if os.path.exists(p):
            st = os.stat(p)
            out.append("  %-70s %8d B  sha256=%s" % (os.path.basename(p), st.st_size, sha256(p)))
        else:
            out.append("  MISSING %s" % p)
    out.append("")
    out.append("== 账本总览 ==")
    out.append("  journal lines = %d / 坏行 = %d" % (len(rows), counts.get("_BAD_LINE", 0)))
    out.append("  event counts = %s" % json.dumps(dict(counts), ensure_ascii=False))
    for day, c in sorted(per_day.items()):
        out.append("  [%s] %s" % (day, json.dumps(dict(c), ensure_ascii=False)))
    out.append("")

    out.append("== 关键行 ==")
    for i, ev in rows:
        if ev.get("event") in ("day_start", "sleep", "day_cap", "finish",
                               "inventory_blocked", "no_progress_burst",
                               "stage_midway_leftover", "lessons"):
            if ev.get("event") == "lessons":
                out.append("  L%-4d %-20s %s" % (i, ev["event"], shrink({k: ev.get(k) for k in ("t", "day_key", "total")})))
            else:
                out.append("  L%-4d %-20s %s" % (i, ev["event"], shrink(ev, 500)))
    out.append("")

    # day_end 摘要
    de = [(i, ev) for i, ev in rows if ev.get("event") == "day_end"]
    out.append("== day_end 摘要（第 1 日）==")
    for i, ev in de:
        out.append("  line=%d" % i)
        for k in DAYEND_KEYS:
            if k not in ev:
                continue
            v = ev[k]
            if k in ("stamina_calibration",):
                v = {kk: {"actions": vv.get("actions"), "stamina_spent": vv.get("stamina_spent")}
                     for kk, vv in (v or {}).items()}
            out.append("    %-26s = %s" % (k, shrink(v)))
        out.append("    stages(n=%d) = %s" % (len(ev.get("stages") or []),
                                              shrink([{kk: s.get(kk) for kk in ("stage", "tiles", "ok", "skipped", "failed", "already")}
                                                      for s in (ev.get("stages") or [])], 1500)))
        plots = ev.get("plots") or []
        out.append("    plots(n=%d) = %s" % (len(plots),
                                             shrink([{kk: p.get(kk) for kk in ("zone", "anchor", "tiles")} for p in plots], 900)))
        for j, ic in enumerate(ev.get("intent_coverage") or []):
            out.append("    intent_coverage[%d] = %s" % (j, shrink(ic, 800)))
        out.append("    notes = %s" % shrink(ev.get("notes"), 1600))
        out.append("    final = %s" % shrink(ev.get("final"), 900))
        out.append("")

    out.append("== finish ==")
    for i, ev in rows:
        if ev.get("event") == "finish":
            out.append("  L%d %s" % (i, shrink(ev, 900)))
    out.append("")

    out.append("== smoke-0745.json 步骤 ==")
    if os.path.exists(RESULT):
        d = json.load(open(RESULT, encoding="utf-8"))
        out.append("  phases_run=%s expect=%s journal=%s" % (d.get("phases_run"), d.get("expect_version"), d.get("journal")))
        for st in d.get("results_all_steps") or []:
            out.append("  step %s verdict=%s reason=%s" % (st.get("step"), st.get("verdict"), st.get("reason")))
            ev = st.get("evidence") or {}
            if st.get("step") in (3, 4, 6, 7, 8):
                out.append("    evidence=%s" % shrink(ev, 4000 if st.get("step") == 8 else 2500))
    out.append("")

    out.append("== SMAPI 窗口 ==")
    if os.path.exists(SMAPI):
        data = open(SMAPI, "r", encoding="utf-8", errors="replace").read().splitlines()
        out.append("  lines=%d size=%d sha256=%s" % (len(data), os.path.getsize(SMAPI), sha256(SMAPI)))
        for pat in ("Inventory", "HUD", "No space", "inventory full", "Inventory Full"):
            hits = [(i + 1, ln) for i, ln in enumerate(data) if pat.lower() in ln.lower()]
            out.append("  grep %-15s hits=%d %s" % (pat, len(hits), shrink([[i, ln[:200]] for i, ln in hits[:6]], 900)))
        bridge = [ln for ln in data if "AgentFarm Bridge" in ln]
        out.append("  bridge lines=%d" % len(bridge))
        times = {"health": 0, "exec": 0, "observe": 0}
        slow = []
        for ln in bridge:
            m = re.search(r"(health|exec|observe).*?(\d+)ms", ln)
            if not m:
                continue
            kind = m.group(1)
            times[kind] = times.get(kind, 0) + 1
            if kind == "exec" and int(m.group(2)) >= 5000:
                ts = re.match(r"\[(\d\d:\d\d:\d\d)", ln)
                slow.append((int(m.group(2)), ts.group(1) if ts else "?", ln[:160]))
        out.append("  bridge kinds=%s slow_exec(>=5s)=%d" % (json.dumps(times), len(slow)))
        for ms, ts, ln in sorted(slow, reverse=True):
            out.append("    %6dms %s %s" % (ms, ts, ln))
    out.append("")
    out.append("== argv / 五文件 ==")
    if os.path.exists(SIDECAR):
        sc = json.load(open(SIDECAR, encoding="utf-8"))
        out.append("  head=%s started_at=%s pid=%s worktree_clean=%s" % (sc.get("head"), sc.get("started_at"), sc.get("pid"), sc.get("worktree_clean")))
        out.append("  argv=%s" % json.dumps(sc.get("argv"), ensure_ascii=False))
        out.append("  boundary_llm=%s" % sc.get("boundary_llm"))
        for name, meta in (sc.get("files") or {}).items():
            out.append("  %-52s sha256=%s mtime=%s" % (name, meta.get("sha256"), meta.get("mtime")))

    text = "\n".join(out) + "\n"
    with open(OUT_LINES, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    # day_end 单独文件
    dayend_text = "\n".join("=== day_end L%d ===\n%s" % (i, json.dumps(ev, ensure_ascii=False, indent=2)) for i, ev in de)
    with open(OUT_DAYEND, "w", encoding="utf-8", newline="\n") as f:
        f.write(dayend_text + "\n")
    print("WROTE", OUT_LINES, len(text), "chars")
    print("WROTE", OUT_DAYEND, len(dayend_text), "chars")


if __name__ == "__main__":
    main()
