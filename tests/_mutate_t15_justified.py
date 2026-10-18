# -*- coding: utf-8 -*-
"""【task-15 / 0.7.45】`day_justified` 收口口径的**变异自检**。

对 `brain/agentfarm/longrun.py` 注入 4 条变异，验证
`tests/test_longrun.py::TestTask15PendingCaliber` 能全部杀掉：

* `m1_honest_reasons_emptied`：`HONEST_EXHAUSTED_END_REASONS` 清空 ⇒
  `resume_exhausted` 再也不会被判"有证据的诚实收工"（冬 27 的形态被误判）；
* `m2_pending_work_counts_stalled`：`_pending_work()` 重新把"已标记停滞/被围"的格
  算成"还有活" ⇒ 0.7.44 冒烟 263/217 的旧账本口径复活；
* `m3_day_justified_no_evidence`：日终传 `pending_executable` 时漏掉证据 kwarg ⇒
  fail-closed 退化成"永远不 justified"（或反过来，若白名单被放宽就会洗白）；
* `m4_burst_stuck_text`：冬 26 同秒 burst 收尾改回写 `stuck:` 文案 ⇒ 有界 ≠ 可放行被破坏。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t15_justified.py

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
TARGET = "tests.test_longrun.TestTask15PendingCaliber"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "m1_honest_reasons_emptied",
        'HONEST_EXHAUSTED_END_REASONS = ("resume_exhausted",)',
        'HONEST_EXHAUSTED_END_REASONS = ()',
        "honest 白名单清空 ⇒ resume_exhausted 永不放行（冬 27 形态被误判）",
    ),
    (
        "m2_pending_work_counts_stalled",
        "                      and t not in self.harvest_gave_up and t not in shed\n"
        "                      and t not in self.resume_stall_tiles\n"
        "                      and t not in self.encircled_day)",
        "                      and t not in self.harvest_gave_up and t not in shed\n"
        "                      and t not in self.encircled_day)",
        "守卫重新把已标记停滞/被围的格算成'还有活' ⇒ 263/217 旧口径复活",
    ),
    (
        "m3_day_justified_no_evidence",
        '            "day_justified": is_justified_end(\n'
        '                rep.ended_by, rep.ended_reason,\n'
        '                pending_executable=rep.pending_executable),',
        '            "day_justified": is_justified_end(rep.ended_by, rep.ended_reason),',
        "日终漏掉 pending_executable 证据 ⇒ 诚实收工被 fail-closed 误杀",
    ),
    (
        "m4_burst_stuck_text",
        "                        self._resume_exhausted(\n"
        "                            obs, rep, plot=self._resume_plot(obs),\n"
        '                            where="plot_exhausted_burst")',
        '                        self._do_sleep(obs, rep, "stuck:变异 burst 收尾")',
        "冬 26 同秒 burst 收尾改回 stuck: 文案 ⇒ 有界 ≠ 可放行被破坏",
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

    with tempfile.TemporaryDirectory(prefix="t15-mutate-") as tmp:
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

        print(f"\n结论：{killed_total}/{len(MUTATIONS)} 条变异被杀；存活 {survived or '无'}")
        return 0 if not survived else 1


if __name__ == "__main__":
    raise SystemExit(main())
