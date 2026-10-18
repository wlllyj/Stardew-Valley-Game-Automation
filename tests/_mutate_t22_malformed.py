# -*- coding: utf-8 -*-
"""【task-22 / 0.7.45】残缺 tile 记录 fail-closed 的**变异自检**。

对 `brain/agentfarm/longrun.py` 注入 3 条变异，验证
`tests/test_longrun.py::TestTask22MalformedTiles` 能全部杀掉（deputy NIT-1 洗白通道）：

* `m1_malformed_back_to_unobserved`：把"tiles[] 里出现但缺 kind/crop"的记录改回 unobserved
  ⇒ executable=0 ⇒ 诚实收工日被放行（原始 fail-open 复活）；
* `m2_malformed_count_removed`：保留 malformed 分支但**不计数**（`malformed` 恒 0）⇒
  不变式 `guard == executable + unobserved + malformed` 被破坏、日终读数缺失；
* `m3_justified_guard_removed`：`is_justified_end` 不再因 `malformed_tiles > 0` 一票否决
  ⇒ 残缺观测下 `day_justified` 仍可能为真（洗白通道）。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t22_malformed.py

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
TARGET = "tests.test_longrun.TestTask22MalformedTiles"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "m1_malformed_back_to_unobserved",
        "            if not tv.get(\"crop\") and not kind and t not in tillable:\n"
        "                malformed += 1\n"
        "                continue\n",
        "            if False:\n"
        "                malformed += 1\n"
        "                continue\n",
        "残缺记录改回 unobserved ⇒ exec=0 ⇒ 诚实收工日被放行（NIT-1 原形复活）",
    ),
    (
        "m2_malformed_count_removed",
        "            if not tv.get(\"crop\") and not kind and t not in tillable:\n"
        "                malformed += 1\n"
        "                continue\n",
        "            if not tv.get(\"crop\") and not kind and t not in tillable:\n"
        "                continue\n",
        "malformed 计数被删 ⇒ 不变式与日终读数缺失",
    ),
    (
        "m3_justified_guard_removed",
        "    if int(malformed_tiles) > 0:\n"
        "        return False\n",
        "    if False:\n"
        "        return False\n",
        "is_justified_end 不再因 malformed>0 一票否决 ⇒ 残客观测仍可能洗白放行",
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

    with tempfile.TemporaryDirectory(prefix="t22-mutate-") as tmp:
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
