# -*- coding: utf-8 -*-
"""【task-26 / 0.7.46 卡 B】回片区走路预算口径 + 收工理由自洽的**变异自检**。

对 `brain/agentfarm/longrun.py` 注入 3 条变异，验证
`tests/test_longrun.py::TestTask26ResumeBudget` 能全部杀掉：

* `m1_failed_walks_burn_success_budget`：把"走失败也计成功预算"的旧口径塞回去
  （走路前就 `resume_walks += 1`）⇒ 冬 27 的 7 次失败又会把 10/10 提前烧光；
* `m2_relax_justification`：`claim_exhausted = True`（无证据也写 `resume_exhausted`，
  账本仍有 7 格可执行却冒充"没有可执行目标"）⇒ 放宽判据的写法必须被杀；
* `m3_attempt_cap_removed`：`_resume_walk_available` 去掉尝试上限 ⇒ 全部走不动时无限空走。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t26_budget.py --from-worktree

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
TARGET = "tests.test_longrun.TestTask26ResumeBudget"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "m1_failed_walks_burn_success_budget",
        "        self.resume_walk_attempts += 1\n"
        "        self.no_progress_cycles += 1                                  # 【task-134 A】\n",
        "        self.resume_walk_attempts += 1\n"
        "        self.resume_walks += 1\n"
        "        self.no_progress_cycles += 1                                  # 【task-134 A】\n",
        "走失败也计成功预算（旧口径）⇒ 冬 27 的 7 次失败再次烧掉 10/10",
    ),
    (
        "m2_relax_justification",
        "        claim_exhausted = (int(snap[\"executable\"]) == 0\n"
        "                           and int(snap.get(\"malformed\", 0)) == 0)\n",
        "        claim_exhausted = True\n",
        "无证据也写 resume_exhausted ⇒ 7 格可执行却冒充「没有可执行目标」（放宽判据）",
    ),
    (
        "m3_attempt_cap_removed",
        "        return (self.resume_walks < self.max_plots_per_day\n"
        "                and self.resume_walk_attempts < 2 * self.max_plots_per_day)\n",
        "        return self.resume_walks < self.max_plots_per_day\n",
        "尝试预算上限被删 ⇒ 全部走不动时无限空走",
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

    with tempfile.TemporaryDirectory(prefix="t26-mutate-") as tmp:
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
            print(f"[baseline] × 基线不是绿的（Ran {ran}）——先修测试再谈变异")
            return 2
        print(f"[baseline] OK（{TARGET}：Ran {ran} tests）")

        killed_total = 0
        survived: list[str] = []
        for mid, old, new, why in MUTATIONS:
            count = original.count(old)
            if count != 1:
                print(f"[{mid}] × 变异锚点出现 {count} 次（要求恰好 1 次）——脚本已过期")
                return 2
            try:
                target.write_text(original.replace(old, new, 1), encoding="utf-8")
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

        print(f"\n结论：{killed_total}/{len(MUTATIONS)} 条变异被杀；存活 {survived or '无'}")
        return 0 if not survived else 1


if __name__ == "__main__":
    raise SystemExit(main())
