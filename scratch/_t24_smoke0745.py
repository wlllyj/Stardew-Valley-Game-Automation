# -*- coding: utf-8 -*-
"""task-24：smoke-0745 首验读数（新四聚合 + 老聚合 + 红/无法判定 + already 双列）。"""
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "logs" / "longrun-smoke-0745.jsonl"
spec = importlib.util.spec_from_file_location("an", str(REPO / "tools" / "analyze-longrun.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

rows, bad = mod.load_journal(str(LEDGER))
args = mod.parse_args(["--journal", str(LEDGER), "--days", "3"])
rep = mod.build_report(rows, str(LEDGER), args, bad)

print("=== 账本 ===")
print("lines:", rep["lines"], "parsed:", rep["parsed_events"], "bad:", rep["bad_lines"])
print("day_start:", rep["day_start_count"], "day_end:", rep["day_end_count"])
print("events:", json.dumps({k: v for k, v in rep["events"].items() if v}, ensure_ascii=False))
print("rc:", 1 if rep["red"]["total"] else 0, "red_total:", rep["red"]["total"],
      "subjects:", rep["red"]["subjects"])
print("undecidable:", len(rep["undecidable"]))
print("window:", {k: rep["window"].get(k) for k in ("days", "tail_streak", "active", "labels")})
for d in rep["days"]:
    print(f"DAY {d['label']} L{d.get('start_line')} day_end={d.get('day_end_lines')} "
          f"ended_by={d.get('ended_by')} verified={d.get('verified')} "
          f"reason={str(d.get('ended_reason'))[:90]}")

for key in ("pending_caliber", "justified_evidence", "bag_pressure", "midway_masking"):
    print(f"\n=== {key} ===")
    print(json.dumps(rep[key], ensure_ascii=False, indent=1)[:6000])

print("\n=== 老聚合（未变项） ===")
print("resume_exhausted state/days/legacy:", rep["resume_exhausted"]["state"],
      rep["resume_exhausted"]["days_count"], rep["resume_exhausted"]["legacy_count"],
      rep["resume_exhausted"]["labels"], rep["resume_exhausted"]["legacy_labels"])
print("stage_realloc state/events/capped:", rep["stage_realloc"]["state"],
      rep["stage_realloc"]["events"], rep["stage_realloc"]["stage_capped"])
print("leftover_split state/totals:", rep["leftover_split"]["state"],
      rep["leftover_split"]["totals"], "mismatch:",
      sum(1 for d in rep["leftover_split"]["days"] if d.get("mismatch")))
print("slept_ok:", {k: rep["slept_ok"].get(k) for k in ("state", "true_count", "false_count",
                                                        "undecidable_count", "inconsistent_days")})
print("budget_suppressed:", {k: rep["budget_suppressed"].get(k) for k in
                             ("state", "days_count", "total", "conflict_days", "labels")})
print("already_aware totals:", rep["already_aware"]["totals"])
print("already_aware window:", rep["already_aware"]["window"])
print("already_aware days:", [(d["label"], d.get("stages"), d.get("ok0"), d.get("ok0_already"),
                               d.get("ok_sum"), d.get("already_sum"))
                              for d in rep["already_aware"]["days"]])
print("guard_count:", rep["guard_count"]["state"], rep["guard_count"]["days_count"])
print("stage_churn:", (rep["stage_churn"]["runs"], rep["stage_churn"]["days_with_runs"],
                       rep["stage_churn"]["stages_total"]))
print("work_spot_resume_exhausted:", (rep["work_spot_resume_exhausted"]["state"],
                                      rep["work_spot_resume_exhausted"]["days_count"]))
print("stuck_without_sleep:", (rep["stuck_without_sleep"]["stuck_days"],
                               rep["stuck_without_sleep"]["flagged"]))

text = mod.render_text(rep, 50)
print("\n=== render 头部新行 ===")
for line in text.splitlines():
    if any(k in line for k in ("pending 七口径", "justified 证据", "背包压力/留痕",
                               "中途遮蔽", "already-aware 双列", "余格拆分", "睡成功标志",
                               "预算抑制", "阶段重分配封格", "回片区穷尽")):
        print(line)

out = REPO / "scratch" / "_t24_smoke0745_readings.json"
out.write_text(json.dumps({k: rep[k] for k in ("pending_caliber", "justified_evidence",
                                              "bag_pressure", "midway_masking",
                                              "already_aware", "resume_exhausted",
                                              "slept_ok", "budget_suppressed",
                                              "leftover_split", "guard_count")},
                          ensure_ascii=False, indent=1), encoding="utf-8")
print("\nreadings ->", out)
