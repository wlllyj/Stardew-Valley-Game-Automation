# -*- coding: utf-8 -*-
"""【task-35 / 0.7.47 快修】背包升级对话购买**默认关闭**的变异自检。

对 `brain/agentfarm/longrun.py` 注入 3 条变异，验证
`tests/test_longrun.py::TestTask35BackpackGate + ::TestTask25BackpackUpgrade` 能全部杀掉：

* `m1_default_back_on`：`backpack_upgrade_enabled` 默认值改回 True
  ⇒ 默认零请求/零 goto 的判据被破坏（又变成每天进 SeedShop）；
* `m2_enabled_drops_double_diff`：开启后判定从"钱/容量双差分"退回"收到 applied 回执就算买成"
  ⇒ task-25 的负向差分用例（钱没少 / 容量没变）被杀；
* `m3_disabled_branch_removed`：默认关闭分支被拆 ⇒ 默认仍会 goto/talk（安全降级失效）。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t35_backpack.py

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
TARGETS = [
    "tests.test_longrun.TestTask35BackpackGate",
    "tests.test_longrun.TestTask25BackpackUpgrade",
]
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

#: (id, relpath, old, new, why)；每条变异的 old 在基线源码里必须恰好出现 1 次。
MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    (
        "m1_default_back_on",
        LONGRUN_REL,
        "        backpack_upgrade_enabled: bool = False,\n",
        "        backpack_upgrade_enabled: bool = True,\n",
        "默认值改回 True ⇒ 默认每天又进 SeedShop 触发过场/污染证据",
    ),
    (
        "m2_enabled_drops_double_diff",
        LONGRUN_REL,
        "        if money_ok and cap_ok:\n",
        "        if talk.get(\"applied\"):\n",
        "开启后丢双差分 ⇒ 钱没少/容量没变也认买成（回执判据复活）",
    ),
    (
        "m3_disabled_branch_removed",
        LONGRUN_REL,
        "        if not self.backpack_upgrade_enabled:\n"
        "            self._backpack_skip(rep, \"disabled\", obs)\n"
        "            return False\n",
        "        if False:\n"
        "            self._backpack_skip(rep, \"disabled\", obs)\n"
        "            return False\n",
        "默认关闭分支被拆 ⇒ 默认仍发 goto/talk（安全降级失效）",
    ),
]


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(cwd / "brain")
    # 每个子进程都显式清掉 opt-in env，保证"默认关闭"的判据不被外部环境翻转。
    env.pop("AGENTFARM_ENABLE_BACKPACK_UPGRADE", None)
    return subprocess.run(cmd, cwd=str(cwd), env=env, text=True,
                          encoding="utf-8", errors="replace",
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _unittest(tree: Path) -> tuple[bool, int, list[str]]:
    proc = _run([sys.executable, "-m", "unittest", *TARGETS, "-v"], tree)
    out = proc.stdout or ""
    ran = re.search(r"^Ran (\d+) tests? in ", out, re.M)
    failures = re.findall(r"^(?:FAIL|ERROR): (\S+)", out, re.M)
    ok = bool(ran) and "OK" in out and proc.returncode == 0
    return ok, int(ran.group(1)) if ran else 0, failures


def _extract_head(dest: Path) -> None:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=zip", "HEAD",
         "brain", "tests", "tools/run-longrun.py"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise SystemExit("git archive 失败：" + proc.stderr.decode("utf-8", "replace")[:500])
    with zipfile.ZipFile(io.BytesIO(proc.stdout)) as zf:
        zf.extractall(dest)


def _copy_worktree(dest: Path) -> None:
    for name in ("brain", "tests"):
        shutil.copytree(ROOT / name, dest / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (dest / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tools" / "run-longrun.py", dest / "tools" / "run-longrun.py")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-worktree", action="store_true",
                    help="用当前工作树的 brain/ + tests/ 当基线（提交前自检用）")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="t35-mutate-") as tmp:
        tree = Path(tmp) / "frozen"
        tree.mkdir()
        if args.from_worktree:
            _copy_worktree(tree)
        else:
            _extract_head(tree)
        originals: dict[Path, str] = {}
        for _mid, rel, _old, _new, _why in MUTATIONS:
            originals.setdefault(rel, (tree / rel).read_text(encoding="utf-8"))

        ok, ran, _ = _unittest(tree)
        if not ok:
            print(f"[baseline] × 基线不是绿的（Ran {ran}）——先修测试再谈变异")
            return 2
        print(f"[baseline] OK（{' + '.join(TARGETS)}：Ran {ran} tests）")

        killed_total = 0
        survived: list[str] = []
        for mid, rel, old, new, why in MUTATIONS:
            original = originals[rel]
            count = original.count(old)
            if count != 1:
                print(f"[{mid}] × 变异锚点出现 {count} 次（要求恰好 1 次）——脚本已过期")
                return 2
            target = tree / rel
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
