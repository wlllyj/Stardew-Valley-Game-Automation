# -*- coding: utf-8 -*-
"""task-17 只读对账：HEAD（a1d23b8，含 task-13）vs 工作树 analyzer。

六本旧账本 rc/红数必须一字不变；`#无法判定` 只允许按 task-17 新增的 3 条探针增加
（`day_end.verified` / `day_end.checks.day_justified` / `day_end.plot_pending`）。
A8 单独打印 rc/红/无法判定 + guard_count 状态（0.7.43 应【无法判定】）。

用法（仓库根，PYTHONUTF8=1）：python scratch/_t17_cmp.py
只读：只写 scratch/_t17_head_analyze.py 这一份 HEAD 导出。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PY = sys.executable
ROOT = Path(__file__).resolve().parent.parent
HEAD_EXPORT = ROOT / "scratch" / "_t17_head_analyze.py"
LEDGERS = [
    "logs/longrun-runA-0732.jsonl",
    "logs/longrun-runB-0732.jsonl",
    "logs/longrun-3day-llm-run9.jsonl",
    "logs/longrun-3day-llm-run9b.jsonl",
    "logs/longrun-3day-llm-run9c.jsonl",
    "logs/longrun-3day-llm-run9d.jsonl",
]
A8 = "logs/longrun-runA8-0743.jsonl"
SMOKE = "logs/longrun-smoke-0744.jsonl"
ENV = {**os.environ, "PYTHONUTF8": "1"}


def export_head() -> None:
    blob = subprocess.run(["git", "cat-file", "-p", "HEAD:tools/analyze-longrun.py"],
                          cwd=ROOT, capture_output=True, check=True).stdout
    HEAD_EXPORT.write_bytes(blob)
    print(f"HEAD analyzer -> {HEAD_EXPORT.relative_to(ROOT)} ({len(blob)} B)")


def measure(script, ledger):
    out = subprocess.run([PY, str(script), "--journal", str(ROOT / ledger), "--json"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=ENV)
    if out.returncode not in (0, 1):
        return (out.returncode, None, None, None)
    try:
        rep = json.loads(out.stdout)
    except Exception as exc:  # noqa: BLE001
        return (out.returncode, f"parse:{exc}", None, None)
    return (out.returncode, int((rep.get("red") or {}).get("total") or 0),
            len(rep.get("undecidable") or []), rep)


def main() -> int:
    export_head()
    bad = 0
    print(f"{'ledger':32} {'old rc/red/#u':>18}  {'new rc/red/#u':>18}  d#u  added_undec")
    for led in LEDGERS:
        old = measure(HEAD_EXPORT, led)
        new = measure(ROOT / "tools" / "analyze-longrun.py", led)
        delta = (new[2] - old[2]) if isinstance(old[2], int) and isinstance(new[2], int) else "?"
        same = (old[0], old[1]) == (new[0], new[1])
        if not same:
            bad += 1
        added = [x for x in (new[3].get("undecidable") or [])
                 if x not in (old[3].get("undecidable") or [])]
        print(f"{Path(led).name:32} {str(old[:3]):>18}  {str(new[:3]):>18}  {delta}  "
              f"{'SAME' if same else 'CHANGED!!'}")
        for line in added:
            print(f"    新增【无法判定】: {line[:120]}")
    for path in (A8, SMOKE):
        old = measure(HEAD_EXPORT, path)
        new = measure(ROOT / "tools" / "analyze-longrun.py", path)
        print(f"\n{Path(path).name}: old rc={old[0]} red={old[1]} #u={old[2]} | "
              f"new rc={new[0]} red={new[1]} #u={new[2]}")
        rep = new[3] or {}
        print("  guard_count:", {k: rep.get("guard_count", {}).get(k) for k in
                                 ("state", "days_count", "guard_pending_max",
                                  "stalled_marked_max", "residual_max",
                                  "midway_events", "truncated_plot_events")})
        print("  stage_realloc:", {k: rep.get("stage_realloc", {}).get(k) for k in
                                   ("state", "events", "stage_capped")})
    print(f"\n六本旧账本 rc/红变化本数: {bad}（必须 0）")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
