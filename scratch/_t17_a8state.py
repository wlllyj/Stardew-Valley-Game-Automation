# -*- coding: utf-8 -*-
"""task-17：打印 A8/冒烟账本 guard_count 状态与渲染行（UTC-8 输出）。"""
import sys

sys.path.insert(0, "tests")
import test_analyze_longrun as T

for path in (T.RUN_A8, "logs/longrun-smoke-0744.jsonl"):
    rep = T.report_for(path, days=3)
    gc = rep["guard_count"]
    print("=" * 30, path)
    print("state:", gc["state"], "days:", gc["days_count"],
          "has_dj:", gc["has_day_justified"], "has_pp:", gc["has_plot_pending"])
    for d in gc["undecidable_days"]:
        print("  undec:", d)
    text = T.mod.render_text(rep, 20)
    for line in text.splitlines():
        if "守卫计数口径" in line:
            print("  render:", line[:160])
