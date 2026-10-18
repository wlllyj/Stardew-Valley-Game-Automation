# -*- coding: utf-8 -*-
"""【task-4 / 0.7.44】回片区拿不出目标（换片 / 观测清一格 / 诚实收工）的**变异自检**。

背景：0.7.43 的 `work_spot_resume` 在"账本残留格都不可执行"时连续走 5 次同一片、把整天判成
`stuck:回片区（work_spot_resume）`（冬 7/12/18 三天）。本脚本对 `brain/agentfarm/longrun.py`
注入 4 条有针对性的变异，验证 `tests/test_longrun.py::TestTask4ResumeNoOutput` 能把它们全部杀掉。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t4_resume.py

默认基线 = `git archive HEAD` 冻结树（只取 `brain/` 与 `tests/`，与冻结验收同口径）。
提交前自检可用 `--from-worktree`（用当前工作树当基线；变异仍只写临时目录，不碰工作树）。

输出：每条变异 `killed` / `survived` + 杀掉的测试名；全部杀死时退出码 0。
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
TARGET = "tests.test_longrun.TestTask4ResumeNoOutput"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

#: (id, 旧文本, 新文本, 说明)。每条的旧文本必须在冻结树里**恰好出现一次**。
MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "m1_no_area_switch",
        "            alt = self._resume_plot(obs, avoid_area=from_area)",
        "            alt = None",
        "关掉『换到另一片账本待做格』⇒ 只剩“回同一片/诚实收工”，should kill 换片用例",
    ),
    (
        "m2_exhausted_written_as_stuck",
        '        why = (f"resume_exhausted:回片区 {len(self.resume_stall_tiles)} 格都回去看过、',
        '        why = (f"stuck:回片区 {len(self.resume_stall_tiles)} 格都回去看过、',
        "把『真没有可执行目标』写回 stuck ⇒ 缺陷误报复发，should kill 诚实收工/日终用例",
    ),
    (
        "m3_encircled_treated_as_executable",
        "        skip = set(self.resume_stall_tiles) | set(self.encircled_day)",
        "        skip = set(self.resume_stall_tiles)",
        "把被围住的格当可执行目标 ⇒ should kill encircled 用例",
    ),
    (
        "m4_no_frontier_clear",
        "\n        if self._frontier_clear(obs, rep):",
        "\n        if False and self._frontier_clear(obs, rep):",
        "去掉『先清观测里可达的一格』⇒ should kill frontier 用例",
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

    with tempfile.TemporaryDirectory(prefix="t4-mutate-") as tmp:
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
                print(f"[{mid}] SURVIVED（Ran {ran_mut} tests，测试没抓到）——{why}")
            else:
                killed_total += 1
                names = "、".join(f.split(".")[-1] for f in failures) or "（见输出）"
                print(f"[{mid}] killed（Ran {ran_mut} tests，红 {len(failures)} 条：{names}）")

        print(f"\n结论：{killed_total}/{len(MUTATIONS)} 条变异被杀死；存活 {survived or '无'}")
        return 0 if not survived else 1


if __name__ == "__main__":
    raise SystemExit(main())
