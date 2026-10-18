"""task-3 只读对账：HEAD 版 vs 新版 analyzer 在六本旧账本上的 rc/红数 + 【无法判定】条数。

用法（在仓库根，PYTHONUTF8=1）：
  python scratch\\_t3_cmp.py
  # 若缺 scratch/_t3_head_analyze.py，本脚本会自己从 `HEAD:tools/analyze-longrun.py` 导出

口径（task-3 验收要求）：
  * 六本旧账本 rc/红数**一字不变**：runA 1/117、runB 1/84、run9 1/84、run9b 1/45、run9c 0/0、run9d 1/29；
  * `#无法判定` **只允许按新增探针增加**：本任务 5 条新探针里只有 `day_end.stages[].assigned`
    在 run9/run9b（0.7.36 形态）缺键 ⇒ 各 +1，其余 0。
只读：不写任何生产文件（只写 scratch/_t3_head_analyze.py 这一份 HEAD 导出）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PY = sys.executable
ROOT = Path(__file__).resolve().parent.parent
HEAD_EXPORT = ROOT / "scratch" / "_t3_head_analyze.py"
LEDGERS = [
    "logs/longrun-runA-0732.jsonl",
    "logs/longrun-runB-0732.jsonl",
    "logs/longrun-3day-llm-run9.jsonl",
    "logs/longrun-3day-llm-run9b.jsonl",
    "logs/longrun-3day-llm-run9c.jsonl",
    "logs/longrun-3day-llm-run9d.jsonl",
]
A8 = "logs/longrun-runA8-0743.jsonl"
ENV = {**os.environ, "PYTHONUTF8": "1"}


def export_head() -> None:
    if HEAD_EXPORT.exists():
        return
    blob = subprocess.run(["git", "cat-file", "-p", "HEAD:tools/analyze-longrun.py"],
                          cwd=ROOT, capture_output=True, check=True).stdout
    HEAD_EXPORT.write_bytes(blob)
    print(f"已导出 HEAD 版 analyzer：{HEAD_EXPORT.relative_to(ROOT)}（{len(blob)} B）")


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
    print(f"{'ledger':34} {'old rc/red/#undec':>22}   {'new rc/red/#undec':>22}  delta#undec")
    for led in LEDGERS:
        old = measure(HEAD_EXPORT, led)
        new = measure(ROOT / "tools" / "analyze-longrun.py", led)
        delta = (new[2] - old[2]) if isinstance(old[2], int) and isinstance(new[2], int) else "?"
        print(f"{Path(led).name:34} {str(old[:3]):>22}   {str(new[:3]):>22}  {delta}")
        if isinstance(old[2], int) and isinstance(new[2], int):
            added = [x for x in new[3].get("undecidable") or []
                     if x not in (old[3].get("undecidable") or [])]
            for line in added:
                print(f"    新增【无法判定】: {line}")

    a8 = measure(ROOT / "tools" / "analyze-longrun.py", A8)
    print(f"\nA8: rc={a8[0]} red={a8[1]} #undec={a8[2]}")
    if a8[3]:
        rep = a8[3]
        print("  stage_churn:", {k: rep["stage_churn"][k] for k in
                                 ("runs", "days_with_runs", "stages_total", "max_run",
                                  "coords", "undecidable_days", "has_assigned")})
        print("  work_spot_resume_exhausted:", {k: rep["work_spot_resume_exhausted"][k]
                                                for k in ("state", "days_count", "max_consecutive")})
        print("  stuck_without_sleep:", {k: rep["stuck_without_sleep"][k]
                                         for k in ("stuck_days", "flagged", "coherent",
                                                   "undecidable", "flagged_days")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
