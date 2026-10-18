# -*- coding: utf-8 -*-
"""【task-5 / 0.7.44】A8 冬 9/14「挡死格被当天反复重分」形态的**修前红复跑**。

背景：A8（`logs/longrun-runA8-0743.jsonl`）冬 9：同格 `encircled` 28 条、1 格阶段 28 轮；
冬 14：63 条 / 62 轮 1 格阶段（`encircled[37,35]`、`unreachable[40,30]/[40,31]/[41,32]`）。
旧代码里 `encircled` 步不吃 `tile_attempts` 配额、也不进 `blocked` ⇒ `_stage_tiles` 每轮把
同一格重新分下去，世界不变 ⇒ 3 轮 idle 判 stuck、整天报废。

本脚本把**当前工作树的 `tests/test_longrun.py`**（含 `TestTask5EncircledRealloc`）盖到
`git archive <rev>` 的冻结树（`brain/` 用该 rev 的代码）上，验证：

* `--rev b702708`（卡 1 修完、卡 2 修前）⇒ 该测试类**必须红**（复现 A8 形态）；
* `--rev HEAD`   （卡 2 修后）       ⇒ **必须绿**。

用法（仓库根；PYTHONUTF8=1 + DSH python）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_repro_t5_encircled.py

默认 `--rev b702708 --post HEAD`；只写临时目录，不碰仓库与工作树。
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
TEST_FILE = Path("tests") / "test_longrun.py"


def _extract(rev: str, dest: Path) -> None:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=zip", rev, "brain", "tests"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise SystemExit(f"git archive {rev} 失败："
                         + proc.stderr.decode("utf-8", "replace")[:500])
    with zipfile.ZipFile(io.BytesIO(proc.stdout)) as zf:
        zf.extractall(dest)


def _run_tests(tree: Path) -> tuple[int, str, list[str]]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(tree / "brain")
    proc = subprocess.run([sys.executable, "-m", "unittest", TARGET, "-v"],
                          cwd=str(tree), env=env, text=True, encoding="utf-8",
                          errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout or ""
    ran = re.search(r"^Ran (\d+) tests? in ", out, re.M)
    fails = re.findall(r"^(?:FAIL|ERROR): (\S+)", out, re.M)
    tail = "\n".join(out.strip().splitlines()[-4:])
    print(f"  rc={proc.returncode}  Ran {ran.group(1) if ran else '?'} 红 {len(fails)}")
    if proc.returncode != 0:
        print("  ── 输出尾部 ──")
        for line in out.strip().splitlines()[-15:]:
            print("  |", line)
    return proc.returncode, out, fails


def _prepare(rev: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="t5-repro-"))
    tree = root / "frozen"
    tree.mkdir()
    if rev.upper() == "WORKTREE":
        # 提交前自检用：直接用**当前工作树**的 brain/ + tests/（不碰仓库，只复制）。
        for name in ("brain", "tests"):
            shutil.copytree(ROOT / name, tree / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return tree
    _extract(rev, tree)
    # 测试跟着修复走：用当前工作树的测试文件覆盖（代码仍是 rev 的）。
    shutil.copy2(ROOT / TEST_FILE, tree / TEST_FILE)
    return tree


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="b702708",
                    help="修前 rev（默认卡 1 提交 b702708：卡 2 之前、且已有卡 1 记账复用）")
    ap.add_argument("--post", default="HEAD",
                    help="修后 rev（默认 HEAD；提交前自检可用 WORKTREE）")
    args = ap.parse_args()

    expected_bad = True
    ok = True
    for rev, want_red in ((args.rev, True), (args.post, False)):
        print(f"\n== {rev}（期望：{'红（复现修前缺陷）' if want_red else '绿（修后）'}）")
        root = _prepare(rev)
        try:
            rc, out, fails = _run_tests(root)
        finally:
            shutil.rmtree(root.parent, ignore_errors=True)
        red = rc != 0
        if want_red and not red:
            print(f"!! {rev} 竟然是绿的 ⇒ 修前缺陷没有复现，本脚本的证据不成立")
            ok = False
        elif (not want_red) and red:
            print(f"!! {rev} 有红 ⇒ 修后测试没通过：{fails}")
            ok = False
        else:
            print("  ✓ 符合预期", "（红的用例：" + "、".join(f.split(".")[-1] for f in fails) + "）"
                  if want_red and fails else "")
    print("\n结论：", "修前红 / 修后绿 —— 离线复现成立" if ok else "不成立（见上）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
