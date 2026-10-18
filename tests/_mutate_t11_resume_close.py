# -*- coding: utf-8 -*-
"""【task-11 / 0.7.44】两条老 resume 入口统一路由（deputy GAP-1/GAP-2）的**变异自检**。

对 `brain/agentfarm/longrun.py` 注入 3 条变异，验证
`tests/test_longrun.py::TestTask11UnifiedResumeClose` 全部杀掉：

* `_review_only_fallback` 触顶不再走卡 1 路由（回退成"直接收口"）；
* `_guard_leftover_resume` 触顶不再走卡 1 路由；
* `guard_leftover` 的"只剩挡死格"分支被短路（不走去换片/诚实收工）。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t11_resume_close.py

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
TARGET = "tests.test_longrun.TestTask11UnifiedResumeClose"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "m1_review_burst_no_routing",
        "                    action, alt = self._resume_switch_or_exhaust(\n"
        "                        obs, rep, plot=resume, where=\"review_only_fallback\")",
        "                    action, alt = (\"ended\", None)",
        "review 兜底触顶不走卡 1 路由 ⇒ 拿不出目标又回到 stuck 形态",
    ),
    (
        "m2_guard_leftover_burst_no_routing",
        "            action, alt = self._resume_switch_or_exhaust(\n"
        "                obs, rep, plot=resume, where=\"guard_leftover\")",
        "            action, alt = (\"none\", None)",
        "guard_leftover 触顶不走卡 1 路由 ⇒ 不换片、不诚实收工",
    ),
    (
        "m3_guard_dead_only_shortcut",
        "            dead = self._dead_end_pending()\n"
        "            if not dead:\n"
        "                return \"none\", False",
        "            dead = []\n"
        "            if not dead:\n"
        "                return \"none\", False",
        "guard_leftover 的『只剩挡死格』分支被短路 ⇒ 不换片/不诚实收工",
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

    with tempfile.TemporaryDirectory(prefix="t11-mutate-") as tmp:
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
