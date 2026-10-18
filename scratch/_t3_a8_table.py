"""task-3 只读取数：A8 逐日 churn 表 + 三类聚合原文（供 docs/_analyze-A8.md 引用）。

用法（仓库根）：$env:PYTHONUTF8=1; python scratch\\_t3_a8_table.py
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("analyze_longrun", ROOT / "tools" / "analyze-longrun.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

LED = str(ROOT / "logs" / "longrun-runA8-0743.jsonl")


def main() -> int:
    rows, bad = mod.load_journal(LED)
    args = mod.parse_args(["--journal", LED, "--days", "12"])
    rep = mod.build_report(rows, LED, args, bad)
    print(f"rows={rep['lines']} parsed={rep['parsed_events']} day_end={rep['day_end_count']} "
          f"verified={rep['verified_days']} red={rep['red']['total']} "
          f"undec={len(rep['undecidable'])}")
    print("\n== 逐日 churn 表（|day|ended_by|verified|stages|runs|churn_stages|max_run|undecidable|day_end L|）")
    for ln, ev in rows:
        if ev.get("event") != "day_end":
            continue
        stages = ev.get("stages") or []
        sc = mod.scan_stage_churn(stages)
        print("| {} | {} | {} | {} | {} | {} | {} | {} | L{} |".format(
            ev.get("day_text"), ev.get("ended_by"), ev.get("verified"), len(stages),
            len(sc["runs"]), sum(r["count"] for r in sc["runs"]),
            max([r["count"] for r in sc["runs"]] or [0]), sc["undecidable"], ln))

    print("\n== 两类 ended_by=stuck 的日子（stuck_without_sleep 原文）")
    for d in rep["stuck_without_sleep"]["days"]:
        print(f"[{d['label']} L{d['line']}] slept_by_us={d['slept_by_us']} verified={d['verified']}")
        print(f"  原文: {d['ended_reason']}")

    print("\n== work_spot_resume_exhausted 三天原文")
    for d in rep["work_spot_resume_exhausted"]["days"]:
        print(f"[{d['label']} L{d['line']}] ended_by={d['ended_by']} verified={d['verified']} "
              f"连续={d['consecutive']} burst=L{d['burst_lines'][0] if d['burst_lines'] else '-'} "
              f"burst_tiles={d['burst_tiles']}")
        print(f"  原文: {d['ended_reason']}")

    print("\n== 头部一行（render_text 摘要行）")
    text = mod.render_text(rep, 20).splitlines()
    for line in text:
        if line.startswith(("阶段 churn", "回片区死循环", "stuck 未睡", "退出码:", "VERIFIED:")):
            print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
