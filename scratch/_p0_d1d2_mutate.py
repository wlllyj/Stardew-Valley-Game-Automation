# -*- coding: utf-8 -*-
"""【0.7.48 P0 批 / 卡 T8】D1+D2 变异实测装置（独立于产物；在 `git archive` 冻结树上复跑）。

用法（必须 DSH python + PYTHONUTF8=1）：
  $env:PYTHONUTF8="1"; & <DSH python> "scratch\\_p0_d1d2_mutate.py"

做三件事：
  1. `git archive HEAD` 取冻结树（不含工作树改动）；
  2. 逐条变异：改一字 → 跑定向用例 → 还原；锚点找不到就报 ADAPTER ERROR（**不当 PASS**）；
  3. 打印每个变异杀的用例数（FAILED/ERROR 计数）与判定。

判据：变异**必须**让至少一条用例变红（杀≥1）；否则该变异是"活的"（测试没盯住）。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
PY = (r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime"
      r"\dependencies\python\python.exe")

# (名字, 相对路径, 原文, 变异后, [定向用例模块...])
MUTANTS = [
    (
        "M1_f1_d1_zblocker_revert",
        "brain/agentfarm/fields.py",
        'ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS | {CLUMP_KIND})',
        'ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS | {"stump", "log", "boulder", "rockPile", "greenRain"})',
        ["tests.test_fields.ZoneBlockerKindsTest", "tests.test_fields.VerifyZoneRetentionCliTest"],
    ),
    (
        "M2_d2_buy_dict_truthiness",
        "brain/agentfarm/longrun.py",
        "changed = self._preconditions_apply(obs, rep)",
        "changed = self._preconditions(obs, rep)",
        ["tests.test_longrun.TestBuyUpgradeDispatch"],
    ),
    (
        "M3_zone_blockers_total_failclosed_returns_zero",
        "brain/agentfarm/fields.py",
        '    if loc.get("tilesTruncated"):\n        return None',
        '    if loc.get("tilesTruncated"):\n        return 0',
        ["tests.test_fields.ZoneBlockerKindsTest", "tests.test_fields.VerifyZoneRetentionCliTest"],
    ),
    (
        "M4_upgrade_tool_journal_drop_hardcoded_axe",
        "brain/agentfarm/longrun.py",
        'tool="axe", tool_hardcoded=True,\n                                  before=getattr(st, "before", None)',
        'before=getattr(st, "before", None)',
        ["tests.test_longrun.TestBuyUpgradeDispatch"],
    ),
]

COUNT_RE = re.compile(r"Ran (\d+) tests?")
BAD_RE = re.compile(r"^(FAILED|ERROR)\b", re.M)


def run_tests(tree: Path, mods: list[str]):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(tree / "brain")
    p = subprocess.run([PY, "-m", "unittest", "-v", *mods],
                       cwd=str(tree), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr or "")
    ran = int(COUNT_RE.search(out).group(1)) if COUNT_RE.search(out) else -1
    failed = len(re.findall(r"^(?:FAIL|ERROR): ", out, re.M))
    ok = bool(re.search(r"^OK\b", out, re.M))
    return ran, failed, ok, out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p0mut_"))
    tree = tmp / "tree"
    tree.mkdir()
    tar = tmp / "frozen.tar"
    subprocess.run(["git", "archive", "--format=tar", "HEAD", "-o", str(tar)],
                   cwd=str(REPO), check=True)
    subprocess.run(["tar", "-xf", str(tar), "-C", str(tree)], check=True)
    print(f"[tree] {tree}")

    # ---- 基线：冻结树必须全绿，否则后面所有"杀"都不可信 ----
    base_mods = sorted({m for _, _, _, _, ms in MUTANTS for m in ms})
    ran, failed, ok, out = run_tests(tree, base_mods)
    print(f"[baseline] Ran {ran} / failed={failed} / OK={ok}")
    if not ok:
        print(out[-4000:])
        print("!! 冻结树基线不是绿的 —— 装置不可信，中止")
        return 2

    results = []
    for name, rel, old, new, mods in MUTANTS:
        f = tree / rel
        src = f.read_text(encoding="utf-8")
        n = src.count(old)
        if n != 1:
            results.append((name, "ADAPTER-ERROR", f"锚点命中 {n} 次（应为 1）", 0, 0))
            print(f"[{name}] ADAPTER-ERROR 锚点命中 {n} 次")
            continue
        f.write_text(src.replace(old, new), encoding="utf-8", newline="")
        try:
            ran, failed, ok, out = run_tests(tree, mods)
        finally:
            f.write_text(src, encoding="utf-8", newline="")
        verdict = "KILL" if (failed > 0 or not ok) else "ALIVE(测试没盯住!)"
        results.append((name, verdict, f"Ran {ran} failed={failed}", failed, ran))
        print(f"[{name}] {verdict}  Ran={ran} failed={failed}")
        if verdict.startswith("ALIVE"):
            print(out[-2500:])

    print("\n================ 变异实测汇总 ================")
    for name, verdict, detail, failed, ran in results:
        print(f"{verdict:12s} {name:46s} {detail}")
    killed = sum(1 for _, v, _, _, _ in results if v == "KILL")
    print(f"杀数 = {killed} / {len(results)}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
