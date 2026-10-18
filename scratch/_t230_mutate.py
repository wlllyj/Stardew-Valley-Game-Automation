"""task-230 变异自检：把 brain/ + tests/ 拷到临时目录，逐个注入"看起来合理"的缺陷，
跑 task-230 的两组用例，数杀掉的条数。

跑法：python scratch/_t230_mutate.py
基线必须 0 红；每个变异必须杀到 ≥1 条（否则说明用例没钉住）。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ["tests.test_longrun.TestTask230ReasonAndGapsIntegrity",
         "tests.test_planner.Task230GapsArchive"]

MUTANTS: list[tuple[str, str, str, str]] = [
    # (名字, 文件, 原文, 替换)
    ("m230a_reason_codes_eleven", "brain/agentfarm/longrun.py",
     '"superseded", "gated",\n    "failed",', '"superseded", "gated",'),
    ("m230b_mapping_drops_not_ready", "brain/agentfarm/longrun.py",
     '"not_ready": "gated"', '"not_ready_typo": "gated"'),
    ("m230c_no_target_without_plot", "brain/agentfarm/longrun.py",
     "        if plot is None:\n            return None",
     "        if plot is None:\n            plot = {\"tiles\": []}"),
    ("m230d_no_archive", "brain/agentfarm/planner.py",
     "        path.replace(dest)", "        _ = dest"),
    ("m230e_write_failure_not_judged", "brain/agentfarm/longrun.py",
     "            rep.gaps_problem = msg\n            rep.notes.append(msg)\n"
     "            self._journal(\"gaps_write_failed\"",
     "            rep.notes.append(msg)\n"
     "            self._journal(\"gaps_write_failed\""),
    ("m230f_validator_no_membership", "brain/agentfarm/longrun.py",
     "    for code in reasons:\n        if str(code) not in INTENT_REASON_CODES:\n            return False",
     "    pass"),
]


def run_suite(base: Path) -> tuple[int, int]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", *TESTS],
        cwd=base, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={"PYTHONUTF8": "1", "PYTHONPATH": str(base / "brain"), "PATH": ""},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    fails = sum(1 for ln in out.splitlines() if ln.startswith("FAIL:") or ln.startswith("ERROR:"))
    return fails, proc.returncode


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "repo"
        base.mkdir()
        for name in ("brain", "tests"):
            shutil.copytree(ROOT / name, base / name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        fails, rc = run_suite(base)
        print(f"baseline: fails={fails} rc={rc}")
        if fails or rc != 0:
            print("基线不干净，先修好再跑变异")
            return 2
        total = 0
        for name, relpath, old, new in MUTANTS:
            target = base / relpath
            original = target.read_text(encoding="utf-8")
            if old not in original:
                print(f"{name}: 锚点没命中（跳过）")
                continue
            target.write_text(original.replace(old, new, 1), encoding="utf-8")
            try:
                killed, rc2 = run_suite(base)
            finally:
                target.write_text(original, encoding="utf-8")
            total += killed
            print(f"{name}: killed={killed} rc={rc2}")
        print(f"合计杀掉 {total} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
