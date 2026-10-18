"""task-242 变异自检：在真实 `brain/agentfarm/longrun.py` 上做文本变异，
跑定向用例 `tests.test_longrun.TestTask242ClearAreaEvidence`，报每条变异的实测杀数。

用法：PYTHONUTF8=1 python scratch/_t242_mutate.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "brain" / "agentfarm" / "longrun.py"
TESTS = ["tests.test_longrun.TestTask242ClearAreaEvidence"]

MUTATIONS = [
    (
        "m242a_ok_counts_already",
        """            oks = [s for s in ok_all
                   if str(getattr(s, "code", "") or "") != "already"]""",
        """            oks = ok_all""",
    ),
    (
        "m242b_guardrail_counts_already",
        """            ok_steps = [s for s in all_steps
                        if s.ok and str(getattr(s, "code", "") or "") != "already"]""",
        """            ok_steps = [s for s in all_steps if s.ok]""",
    ),
    (
        "m242c_ok_tiles_drops_already",
        """        ok_tiles_set = {tuple(s.tile) for s in ok_all if s.tile} & assigned_set""",
        """        ok_tiles_set = {tuple(s.tile) for s in oks if s.tile} & assigned_set""",
    ),
    (
        "m242d_collateral_cause_lost",
        """            bucket = "cleared_by_neighbor" if key in neighbor_open else "no_target\"""",
        """            bucket = "no_target\"""",
    ),
]


def run_tests() -> tuple[bool, str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(REPO / "brain")
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", *TESTS],
        cwd=str(REPO), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"^Ran (\d+) tests", out, re.M)
    ran = int(m.group(1)) if m else 0
    failed = re.findall(r"^(?:FAIL|ERROR): (\w+)", out, re.M)
    ok = "OK" in out and not failed
    return ok, f"Ran {ran} / {'OK' if ok else 'FAILED'}: {sorted(set(failed))}"


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    ok, detail = run_tests()
    print(f"基线: {detail}")
    if not ok:
        print("基线不是绿的 ⇒ 变异自检无效，先修用例")
        return 2
    killed = 0
    try:
        for name, old, new in MUTATIONS:
            if original.count(old) != 1:
                print(f"{name}: 变异锚点不唯一/不存在（count="
                      f"{original.count(old)}）⇒ 无法判定")
                continue
            TARGET.write_text(original.replace(old, new), encoding="utf-8")
            try:
                ok, detail = run_tests()
            finally:
                TARGET.write_text(original, encoding="utf-8")
            status = "绿（未被杀）" if ok else "红（被杀）"
            killed += 0 if ok else 1
            print(f"{name}: {status} — {detail}")
    finally:
        TARGET.write_text(original, encoding="utf-8")
    total = len(MUTATIONS)
    print(f"结论：{killed}/{total} 被杀")
    return 0 if killed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
