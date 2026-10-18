# -*- coding: utf-8 -*-
"""【task-5 / 0.7.44】挡死格重分 / leftover 拆分 / 轮次有界的**变异自检**。

对 `brain/agentfarm/longrun.py` 注入 5 条有针对性的变异，验证
`tests/test_longrun.py::TestTask5EncircledRealloc` 能把它们全部杀掉：

* 挡死格重新进入分配（`_stage_tiles` 的 encircled 排除被关掉）；
* 守卫口径把被围格当"活"（`_plot_has_work` 的 encircled 排除被关掉）；
* leftover 不拆（挡死格数恒 0）；
* 重分轮次无界（alloc cap 被关掉）；
* 整片只剩挡死格时不再走卡 1 的换片/诚实收工（dead-only 路由被短路）。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t5_encircled.py

默认基线 = `git archive HEAD` 冻结树（只取 `brain/` 与 `tests/`）；`--from-worktree` 供提交前自检。
输出：每条变异 killed / survived + 杀掉的测试名；全部 killed 时退出码 0。
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
TARGET = "tests.test_longrun.TestTask5EncircledRealloc"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

#: (id, 旧文本, 新文本, 说明)。每条的旧文本必须在冻结树里**恰好出现一次**。
MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "m1_dead_tiles_reenter_allocation",
        "        if self.encircled_day:\n"
        "            pool = [t for t in pool if t not in self.encircled_day]",
        "        if False:\n"
        "            pool = [t for t in pool if t not in self.encircled_day]",
        "关掉『被围格不进目标池』⇒ 1 格阶段死循环复发，should kill 排除用例",
    ),
    (
        "m2_guard_counts_encircled_as_work",
        "            if t in self.blocked or t in shed or t in self.encircled_day:",
        "            if t in self.blocked or t in shed:",
        "守卫把被围格当『还有活』⇒ should kill _plot_has_work 用例",
    ),
    (
        "m3_leftover_not_split",
        '            "leftover_blocked": len(leftover_blocked),',
        '            "leftover_blocked": 0,',
        "leftover 不拆『物理挡死格』⇒ should kill 拆分用例",
    ),
    (
        "m4_realloc_unbounded",
        "            if n >= MAX_ALLOC_NO_PROGRESS and key not in self.blocked:",
        "            if False and n >= MAX_ALLOC_NO_PROGRESS and key not in self.blocked:",
        "关掉『同格重分无产出』有界保护 ⇒ should kill 有界用例",
    ),
    (
        "m5_dead_only_keeps_churning",
        "                    dead_pending = self._dead_end_pending()",
        "                    dead_pending = []",
        "整片只剩挡死格时不再走卡 1 换片/诚实收工 ⇒ should kill 日终用例",
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

    with tempfile.TemporaryDirectory(prefix="t5-mutate-") as tmp:
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
