# -*- coding: utf-8 -*-
"""task-17 文档读数：冒烟账本 guard_count/各聚合/逐日表 -> stdout。"""
import json
import sys

sys.path.insert(0, "tests")
import test_analyze_longrun as T

rep = T.report_for("logs/longrun-smoke-0744.jsonl", days=5)
for key in ("guard_count", "resume_exhausted", "stage_realloc", "leftover_split",
            "slept_ok", "budget_suppressed", "already_aware",
            "work_spot_resume_exhausted", "stage_churn", "stuck_without_sleep"):
    print("=" * 20, key)
    obj = rep[key]
    if key == "guard_count":
        for d in obj["days"]:
            print(json.dumps({k: v for k, v in d.items() if k != "midway_events"},
                             ensure_ascii=False))
            print("   midway:", d["midway_events"])
    elif key == "resume_exhausted":
        print(json.dumps({k: obj[k] for k in ("state", "days_count", "labels", "legacy_count",
                                              "legacy_labels", "burst_exhausted_events")},
                         ensure_ascii=False))
        for d in obj["days"]:
            print("   day:", json.dumps(d, ensure_ascii=False))
    elif key == "already_aware":
        print(json.dumps({k: obj[k] for k in ("state", "totals", "window")}, ensure_ascii=False))
        for d in obj["days"]:
            print("   day:", json.dumps({k: d[k] for k in
                                         ("label", "stages", "ok0", "ok0_already", "ok_sum",
                                          "already_sum", "already_stages")}, ensure_ascii=False))
    elif key == "leftover_split":
        print(json.dumps({k: obj[k] for k in ("state", "totals", "days_count")}, ensure_ascii=False))
        for d in obj["days"]:
            print("   day:", json.dumps({k: d[k] for k in
                                         ("label", "stages", "with_split", "exec_sum",
                                          "blocked_sum", "leftover_sum", "mismatch")},
                                        ensure_ascii=False))
    elif key == "work_spot_resume_exhausted":
        print(json.dumps({k: obj.get(k) for k in
                          ("state", "days_count", "max_consecutive", "labels",
                           "burst_mismatch_days", "undecidable_days")}, ensure_ascii=False, default=str))
    else:
        print(json.dumps({k: v for k, v in obj.items() if k != "days"}, ensure_ascii=False))
print("=" * 20, "red")
print({k: rep["red"].get(k) for k in ("total", "subjects", "settled_total")})
print("=" * 20, "undecidable", len(rep["undecidable"]))
print("== window:", json.dumps(rep.get("window"), ensure_ascii=False))
