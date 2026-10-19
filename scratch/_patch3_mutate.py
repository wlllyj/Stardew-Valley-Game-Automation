# -*- coding: utf-8 -*-
"""【卡 T8 / lead 补丁3】新增测试的变异实测装置（在 `git archive HEAD` 冻结树上复跑）。

用法（必须 DSH python + PYTHONUTF8=1）：
  $env:PYTHONUTF8="1"; & <DSH python> "scratch\\_patch3_mutate.py"

补丁3 只加了测试（观察三形态 + buy 不双买），所以这里变异的是**生产代码**，
证明新测试确实盯住了那些行为：把每个被断言的行为改坏，至少一条用例必须变红。
锚点命中数 != 期望值 ⇒ ADAPTER-ERROR（**不当 PASS**）。
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

# (名字, 相对路径, 原文, 变异后, 期望命中数, [定向用例模块...])
MUTANTS = [
    (
        "M5_f1_zblocker_revert_new_shape",
        "brain/agentfarm/fields.py",
        'ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS | {CLUMP_KIND})',
        'ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS | {"stump", "log", "boulder", "rockPile", "greenRain"})',
        1,
        ["tests.test_fields.ZoneBlockerKindsTest"],
    ),
    (
        "M6_zone_total_truncated_not_failclosed",
        "brain/agentfarm/fields.py",
        '    if loc.get("tilesTruncated"):\n        return None',
        '    if loc.get("tilesTruncated"):\n        return 0',
        1,
        ["tests.test_fields.ZoneBlockerKindsTest", "tests.test_fields.VerifyZoneRetentionCliTest"],
    ),
    (
        "M7_buy_plantable_early_return_removed",
        "brain/agentfarm/longrun.py",
        "        if plantable > 0:\n            return False",
        "        if False:\n            return False",
        1,
        ["tests.test_longrun.TestBuyUpgradeDispatch"],
    ),
    (
        "M8_buy_daily_cap_off_by_one",
        "brain/agentfarm/longrun.py",
        "self.buy_attempts_today >= MAX_BUY_TRIES_PER_DAY",
        "self.buy_attempts_today > MAX_BUY_TRIES_PER_DAY",
        2,
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
    tmp = Path(tempfile.mkdtemp(prefix="p3mut_"))
    tree = tmp / "tree"
    tree.mkdir()
    tar = tmp / "frozen.tar"
    subprocess.run(["git", "archive", "--format=tar", "HEAD", "-o", str(tar)],
                   cwd=str(REPO), check=True)
    subprocess.run(["tar", "-xf", str(tar), "-C", str(tree)], check=True)
    print(f"[tree] {tree}")

    base_mods = sorted({m for _, _, _, _, _, ms in MUTANTS for m in ms})
    ran, failed, ok, out = run_tests(tree, base_mods)
    print(f"[baseline] Ran {ran} / failed={failed} / OK={ok}")
    if not ok:
        print(out[-4000:])
        print("!! 冻结树基线不是绿的 —— 装置不可信，中止")
        return 2

    results = []
    for name, rel, old, new, want, mods in MUTANTS:
        f = tree / rel
        src = f.read_text(encoding="utf-8")
        n = src.count(old)
        if n != want:
            results.append((name, "ADAPTER-ERROR", f"锚点命中 {n} 次（期望 {want}）", 0, 0))
            print(f"[{name}] ADAPTER-ERROR 锚点命中 {n} 次（期望 {want}）")
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

    print("\n================ 变异实测汇总（补丁3） ================")
    for name, verdict, detail, failed, ran in results:
        print(f"{verdict:12s} {name:44s} {detail}")
    killed = sum(1 for _, v, _, _, _ in results if v == "KILL")
    print(f"杀数 = {killed} / {len(results)}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
