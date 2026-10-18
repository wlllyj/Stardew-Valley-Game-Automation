# -*- coding: utf-8 -*-
"""task-8 冒烟取证：从日志/账本里抽读数，供 docs/_smoke-0744.md 使用（只读，不改跑法）。

用法：
  PYTHONUTF8=1 python scratch\\_t8_smoke_evidence.py
输出：stdout 摘要；完整逐行素材写 scratch/_t8_smoke_lines.txt。
"""
import json
import os
import sys
from collections import Counter

JOURNAL = os.path.join("logs", "longrun-smoke-0744.jsonl")
OUT = os.path.join("scratch", "_t8_smoke_lines.txt")

KEY_EVENTS = (
    "work_spot", "resume_walk", "resume_reevaluate", "plot", "plot_walk",
    "plot_exhausted", "plot_exhausted_burst", "stage_exhausted",
    "stage_stop_named", "stage_shortfall", "stage_midway_leftover",
    "no_progress_burst", "stage_no_target", "unreachable", "unreachable_stage",
    "unreachable_summary", "encircled", "encircled_stage", "encircled_summary",
    "frontier_clear", "clear_neighbor", "idle", "stuck", "stamina_budget",
)


def load_rows(path):
    rows = []
    bad = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                bad += 1
    return rows, bad


def brief(r):
    keep = {}
    for k in ("event", "t", "day", "timeOfDay", "stage", "ok", "leftover",
              "count", "bound", "attempted", "tiles", "tile", "anchor", "spot",
              "reason", "note", "verified", "ended_by", "ended_reason",
              "plot_pending", "plot_pending_executable", "plot_pending_blocked",
              "bound_basis", "tilesTruncated", "guard", "pending"):
        if k in r and r[k] not in (None, "", [], {}):
            v = r[k]
            if isinstance(v, str) and len(v) > 200:
                v = v[:200] + "…"
            if isinstance(v, list) and len(v) > 12:
                v = v[:12] + ["…%d more" % (len(r[k]) - 12)]
            keep[k] = v
    return json.dumps(keep, ensure_ascii=False)


def main():
    rows, bad = load_rows(JOURNAL)
    out = []
    out.append("journal=%s rows=%d bad=%d" % (JOURNAL, len(rows), bad))

    # 事件计数
    cnt = Counter(r.get("event") for r in rows)
    out.append("events=" + json.dumps(dict(sorted(cnt.items())), ensure_ascii=False))

    # 逐日
    for i, r in enumerate(rows, 1):
        if r.get("event") == "day_start":
            out.append("L%d day_start %s timeOfDay=%s" % (i, r.get("day"), r.get("timeOfDay")))
        if r.get("event") == "day_end":
            out.append("L%d day_end %s" % (i, r.get("day")))
        if r.get("event") == "finish":
            out.append("L%d finish %s" % (i, json.dumps({k: r.get(k) for k in (
                "code", "verified_streak", "actions", "minutes", "stages_seen",
                "no_unmet_stages", "unmet_days", "stuck_flushes")}, ensure_ascii=False)))

    # day_end 全文（存文件）
    dayends = [(i, r) for i, r in enumerate(rows, 1) if r.get("event") == "day_end"]
    with open(os.path.join("scratch", "_t8_smoke_dayend.txt"), "w", encoding="utf-8") as fh:
        for i, r in dayends:
            fh.write("===== L%d =====\n" % i)
            fh.write(json.dumps(r, ensure_ascii=False, indent=2))
            fh.write("\n")

    # day_end 关键字段
    for i, r in dayends:
        checks = r.get("checks") or {}
        false_keys = [k for k, v in checks.items() if v is False]
        plots = r.get("plots") or []
        out.append("L%d day_end keys=%s" % (i, sorted(r.keys())))
        out.append("L%d day_end compact day=%s verified=%s false_checks=%s ended_by=%s" % (
            i, r.get("day"), r.get("verified"), false_keys, r.get("ended_by")))
        out.append("L%d day_end reason=%s" % (i, r.get("ended_reason")))
        out.append("L%d day_end plot_pending=%s exec=%s blocked=%s bound_basis=%s" % (
            i, r.get("plot_pending"), r.get("plot_pending_executable"),
            r.get("plot_pending_blocked"), r.get("bound_basis")))
        if plots:
            out.append("L%d day_end plots=%s" % (i, json.dumps(plots, ensure_ascii=False)[:600]))

    # 关键事件行
    key_rows = []
    for i, r in enumerate(rows, 1):
        ev = r.get("event")
        if ev in KEY_EVENTS:
            line = "L%-4d t=%-8s %-16s %s" % (i, r.get("t"), ev, brief(r))
            key_rows.append(line)
    out.append("--- key event lines (%d) ---" % len(key_rows))
    out.extend(key_rows)

    # tilesTruncated 出现位置
    tr = []
    for i, r in enumerate(rows, 1):
        if "tilesTruncated" in json.dumps(r, ensure_ascii=False):
            tr.append("L%d %s tilesTruncated=%s" % (i, r.get("event"), r.get("tilesTruncated")))
    out.append("--- tilesTruncated lines (%d) ---" % len(tr))
    out.extend(tr[:40])

    text = "\n".join(out)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
