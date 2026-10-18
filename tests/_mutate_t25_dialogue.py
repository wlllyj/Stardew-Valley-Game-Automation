# -*- coding: utf-8 -*-
"""【task-25 rev4 / 0.7.46 卡 A 脑侧】对话购买判据的**变异自检**。

对 `brain/agentfarm/longrun.py` 注入 4 条变异，验证
`tests/test_longrun.py::TestTask25BackpackUpgrade` 能全部杀掉：

* `m1_trust_receipt_not_diff`：判定从"钱/容量双差分"退回"收到 applied 回执就算买成"
  （= 旧货架判据的失效模式：升级不占格，回执成功≠能力真的变了）；
* `m2_direct_money_write`：绕过 `talk`/`dismiss_modal`，脑侧直接改世界的钱与容量
  （红线：禁直写 money/Items/MaxItems、禁直调 increaseBackpackSize）；
* `m3_no_response_guard`：选项里没有精确「Purchase」也照发应答
  （fail-closed 失效：替游戏猜选项）；
* `m4_attempt_limit_removed`：每天 ≤2 次 talk 的上界失效
  （失败后无限重试，等于卡死在店里）。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t25_dialogue.py

默认基线 = `git archive HEAD` 冻结树（只取 `brain/` 与 `tests/`）；`--from-worktree` 供提交前自检
（本卡尚未提交时用后者；提交后默认冻结树应同样 4/4 被杀）。
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
TARGET = "tests.test_longrun.TestTask25BackpackUpgrade"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

#: (id, relpath, old, new, why)；每条变异的 old 在基线源码里必须恰好出现 1 次。
MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    (
        "m1_trust_receipt_not_diff",
        LONGRUN_REL,
        "        money_ok = (money_b is not None and money_a is not None\n"
        "                    and money_a == money_b - BACKPACK_UPGRADE_PRICE)\n"
        "        cap_ok = (cap_b == BACKPACK_BASE_CAPACITY\n"
        "                  and cap_a == BACKPACK_UPGRADE_CAPACITY)\n"
        "        if money_ok and cap_ok:\n",
        "        money_ok = (money_b is not None and money_a is not None\n"
        "                    and money_a == money_b - BACKPACK_UPGRADE_PRICE)\n"
        "        cap_ok = (cap_b == BACKPACK_BASE_CAPACITY\n"
        "                  and cap_a == BACKPACK_UPGRADE_CAPACITY)\n"
        "        if talk.get(\"applied\"):\n",
        "判据退回「回执 applied 就算买成」⇒ 钱没少/容量没变也会被认成功",
    ),
    (
        "m2_direct_money_write",
        LONGRUN_REL,
        "        start = time.monotonic()\n"
        "        self.backpack_tried_today = True\n",
        "        start = time.monotonic()\n"
        "        self.backpack_tried_today = True\n"
        "        # 变异：绕过 talk/dismiss_modal，直接改世界的钱与容量（红线）\n"
        "        _w = getattr(self.client, \"w\", None)\n"
        "        if _w is not None:\n"
        "            _w.money = int(getattr(_w, \"money\", 0)) - BACKPACK_UPGRADE_PRICE\n"
        "            _w.inventory_capacity = BACKPACK_UPGRADE_CAPACITY\n"
        "        self.backpack_ok_today = True\n"
        "        rep.backpack_upgrade_ok = True\n"
        "        rep.backpack_capacity_after = BACKPACK_UPGRADE_CAPACITY\n"
        "        rep.notes.append(\"变异：直接改钱/容量\")\n"
        "        return True\n",
        "绕过游戏入口直写钱/容量（红线），必须被「talk 调用次数/应答」判据杀掉",
    ),
    (
        "m3_no_response_guard",
        LONGRUN_REL,
        "        matches = [r for r in responses if r.strip().casefold() == needle]\n"
        "        if not matches:\n",
        "        matches = [r for r in responses if r.strip().casefold() == needle]\n"
        "        if False:\n",
        "选项里没有精确「Purchase」也照发应答 ⇒ 替游戏猜选项（fail-closed 失效）",
    ),
    (
        "m4_attempt_limit_removed",
        LONGRUN_REL,
        "        if self.backpack_tried_today or self.backpack_attempts_today >= BACKPACK_UPGRADE_MAX_ATTEMPTS:\n",
        "        if False:\n",
        "每天 ≤2 次 talk 上界失效 ⇒ 失败后在店里无限重试",
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

    with tempfile.TemporaryDirectory(prefix="t25-mutate-") as tmp:
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
        print(f"[baseline] OK（{TARGET}：Ran {ran} tests）")

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
