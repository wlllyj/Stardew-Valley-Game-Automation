"""task-194 只读对账：HEAD 版 vs 新版 analyzer 在六本旧账本上的 rc/红数 + 【无法判定】条数。

用法（在仓库根）：
  git show HEAD:tools/analyze-longrun.py | Set-Content -Encoding utf8 scratch\\_t172_old_analyze.py
  python scratch\\_t194_undec.py

为什么单独量【无法判定】：task-194 顺手修了「子字段探针（`event:名字.键`）恒判缺失」的老 bug ——
它**只影响【无法判定】文案条数，不影响 rc / 红数**，所以要两边都量、把差异写清楚。
"""
import json
import subprocess
import sys
from pathlib import Path

PY = sys.executable
ROOT = Path(__file__).resolve().parent.parent
LEDGERS = [
    "logs/longrun-runA-0732.jsonl",
    "logs/longrun-runB-0732.jsonl",
    "logs/longrun-3day-llm-run9.jsonl",
    "logs/longrun-3day-llm-run9b.jsonl",
    "logs/longrun-3day-llm-run9c.jsonl",
    "logs/longrun-3day-llm-run9d.jsonl",
]


def measure(script: str, ledger: str):
    out = subprocess.run(
        [PY, str(ROOT / script), "--journal", str(ROOT / ledger), "--json"],
        capture_output=True, text=True, encoding="utf-8")
    if out.returncode not in (0, 1):
        return ("rc=%d" % out.returncode, None, None)
    try:
        rep = json.loads(out.stdout)
    except Exception as exc:  # noqa: BLE001
        return ("解析失败: %s" % exc, None, None)
    return (out.returncode, int((rep.get("red") or {}).get("total") or 0),
            len(rep.get("undecidable") or []))


def main() -> int:
    old = ROOT / "scratch" / "_t172_old_analyze.py"
    if not old.exists():
        print("缺 scratch/_t172_old_analyze.py（先从 HEAD 导出）")
        return 2
    print(f"{'ledger':34} {'old rc/red/#undec':>22}   {'new rc/red/#undec':>22}")
    for led in LEDGERS:
        a = measure("scratch/_t172_old_analyze.py", led)
        b = measure("tools/analyze-longrun.py", led)
        print(f"{Path(led).name:34} {str(a):>22}   {str(b):>22}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
