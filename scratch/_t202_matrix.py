"""task-202 回归矩阵：旧版（HEAD 导出）vs 新版对每本旧账本的 rc / 红数 / #无法判定。

用法（在仓库根目录）：
  python scratch\\_t202_matrix.py

旧版由 `git show HEAD:tools/analyze-longrun.py` 导出到 `scratch\\_t202_old_analyze.py`
（交付前删除；`.gitignore` = `scratch/*` + `!scratch/*.py` ⇒ 这个临时导出会露头，别提交）。
"""
import json
import os
import subprocess
import sys

PY = sys.executable
OLD = os.path.join("scratch", "_t202_old_analyze.py")
NEW = os.path.join("tools", "analyze-longrun.py")
LEDGERS = [
    "logs/longrun-runA-0732.jsonl",
    "logs/longrun-runB-0732.jsonl",
    "logs/longrun-runA3-0736.jsonl",
    "logs/longrun-3day-llm-run8.jsonl",
    "logs/longrun-3day-llm-run9.jsonl",
    "logs/longrun-3day-llm-run9b.jsonl",
    "logs/longrun-3day-llm-run9c.jsonl",
    "logs/longrun-3day-llm-run9d.jsonl",
]


def probe(tool: str, ledger: str) -> tuple:
    proc = subprocess.run(
        [PY, tool, "--journal", ledger, "--days", "7", "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = proc.stdout or ""
    start = out.find("{")
    if start < 0:
        return (proc.returncode, -1, -1)
    try:
        rep = json.loads(out[start:])
    except Exception:
        return (proc.returncode, -1, -1)
    red = (rep.get("red") or {}).get("total")
    und = len(rep.get("undecidable") or [])
    return (proc.returncode, red, und)


def main() -> int:
    print(f"{'ledger':26} {'old(rc/红/#无法判定)':>22} {'new(rc/红/#无法判定)':>22}  变化")
    for ledger in LEDGERS:
        if not os.path.exists(ledger):
            print(f"{os.path.basename(ledger):26} <缺账本>")
            continue
        old = probe(OLD, ledger)
        new = probe(NEW, ledger)
        delta = new[2] - old[2]
        print(f"{os.path.basename(ledger):26} {str(old):>22} {str(new):>22}  #无法判定 {delta:+d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
