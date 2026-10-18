# -*- coding: utf-8 -*-
"""【task-6 / 0.7.44】收工口径两处修复的**变异自检**。

对 `brain/agentfarm/longrun.py` 注入 4 条变异，验证
`tests/test_longrun.py::TestTask6CloseoutCaliber` 全部杀掉：

* `checks.slept_by_us` 退回"只看 ended_by"（stuck 翻篇的真睡眠被误报 false）；
* `_do_sleep` 成功后不记 `rep.slept_ok`（真睡眠真相丢失）；
* `_flush_budget_deferrals` 不看浇水证据、一律落事件（与"户外浇水达标"同真）；
* 反方向：一律压制事件（没浇完也不留"只因预算延后"证据）。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t6_closeout.py

默认基线 = `git archive HEAD` 冻结树（只取 `brain/` 与 `tests/`）；`--from-worktree` 供提交前自检。
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = "tests.test_longrun.TestTask6CloseoutCaliber"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "m1_slept_by_us_from_ended_by_only",
        '        return bool(rep.slept_ok or rep.ended_by in ("sleep", "inventory_blocked"))',
        '        return bool(rep.ended_by in ("sleep", "inventory_blocked"))',
        "slept_by_us 退回只看 ended_by ⇒ stuck 翻篇真睡眠被误报 false",
    ),
    (
        "m2_sleep_success_not_recorded",
        "            rep.slept_ok = True",
        "            rep.slept_ok = False",
        "_do_sleep 成功后不记 slept_ok ⇒ 真值丢失",
    ),
    (
        "m3_flush_ignores_water_evidence",
        "        if watered_outdoor:",
        "        if False:",
        "日终落账不看浇水证据 ⇒ 『只因预算延后』与『户外浇水达标』同真复发",
    ),
    (
        "m4_flush_always_suppresses",
        "        if watered_outdoor:",
        "        if True:",
        "一律压制事件 ⇒ 没浇完的日子也丢『只因预算延后』证据",
    ),
]


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(cwd / "brain")
    return subprocess.run(cmd, cwd=str(cwd), env=env, text=True,
                          encoding="utf-8", errors="replace",
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _unittest(tree: Path) -> tuple[bool, int, list[str]]:
    proc = _run([sys.executable, "-m", "unittest", TARGET, "-v"], tree)
    out = proc.stdout or ""
    ran = re.search(r"^Ran (\d+) tests? in ", out, re.M)
    failures = re.findall(r"^(?:FAIL|ERROR): (\S+)", out, re.M)
    ok = bool(ran) and "OK" in out and proc.returncode == 0
    return ok, int(ran.group(1)) if ran else 0, failures


def _extract_head(dest: Path) -> None:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=zip", "HEAD", "brain", "tests"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise SystemExit("git archive 失败：" + proc.stderr.decode("utf-8", "replace")[:500])
    with zipfile.ZipFile(io.BytesIO(proc.stdout)) as zf:
        zf.extractall(dest)


def _copy_worktree(dest: Path) -> None:
    for name in ("brain", "tests"):
        shutil.copytree(ROOT / name, dest / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-worktree", action="store_true",
                    help="用当前工作树的 brain/ + tests/ 当基线（提交前自检用）")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="t6-mutate-") as tmp:
        tree = Path(tmp) / "frozen"
        tree.mkdir()
        if args.from_worktree:
            _copy_worktree(tree)
        else:
            _extract_head(tree)
        target = tree / LONGRUN_REL
        original = target.read_text(encoding="utf-8")

        ok, ran, _ = _unittest(tree)
        if not ok:
            print(f"[baseline] ✗ 基线不是绿的（Ran {ran}）——先修测试再谈变异")
            return 2
        print(f"[baseline] OK（{TARGET}：Ran {ran} tests）")

        killed_total = 0
        survived: list[str] = []
        for mid, old, new, why in MUTATIONS:
            count = original.count(old)
            if count != 1:
                print(f"[{mid}] ✗ 变异锚点出现 {count} 次（要求恰好 1 次）——脚本已过期")
                return 2
            target.write_text(original.replace(old, new, 1), encoding="utf-8")
            try:
                ok_mut, ran_mut, failures = _unittest(tree)
            finally:
                target.write_text(original, encoding="utf-8")
            if ok_mut:
                survived.append(mid)
                print(f"[{mid}] SURVIVED（Ran {ran_mut} tests）——{why}")
            else:
                killed_total += 1
                names = "、".join(f.split(".")[-1] for f in failures) or "（见输出）"
                print(f"[{mid}] killed（Ran {ran_mut} tests，红 {len(failures)} 条：{names}）")

        print(f"\n结论：{killed_total}/{len(MUTATIONS)} 条变异被杀死；存活 {survived or '无'}")
        return 0 if not survived else 1


if __name__ == "__main__":
    raise SystemExit(main())
