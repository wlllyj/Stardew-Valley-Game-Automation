# -*- coding: utf-8 -*-
"""【task-28 / 0.7.46 卡 D】背包证据门槛与白名单纪律的**变异自检**。

对 `brain/agentfarm/{farmwork,longrun}.py` 注入 5 条变异，验证
`tests/test_longrun.py::TestTask28BagEvidence` 能全部杀掉：

* `m1_wood_back_to_sellable`：木材 388 加回 `SURPLUS_MATERIAL_IDS`（换种子钱并集）
  ⇒ 表级 fail-closed 判据被破坏；
* `m5_wood_back_to_pressure_tier`：木材 388 加回 `SLOT_RELIEF_MATERIAL_IDS`（空格压力分档）
  ⇒ 满包时又卖建材（卡 A 纪律反转）；
* `m2_inventory_blocked_unconditional`：`_note_inventory_blocked` 直接 `accepted = True`
  ⇒ 四门槛失效（exec>0 / 缺口径照样认"腾不出"收工，洗白）；
* `m3_clear_gate_removed`：满包清障闸被拆 ⇒ 0 空格且腾不出时仍新开 `clear_area`
  （落地即丢、loot 上界也失去意义）；
* `m4_clear_loot_cap_removed`：全天 `loot_lost_steps` 上界不再收窄阶段 limit ⇒ 丢失无界。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t28_bag.py

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
TARGET = "tests.test_longrun.TestTask28BagEvidence"
FARMWORK_REL = Path("brain") / "agentfarm" / "farmwork.py"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

#: (id, relpath, old, new, why)；每条变异的 old 在基线源码里必须恰好出现 1 次。
MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    (
        "m1_wood_back_to_sellable",
        FARMWORK_REL,
        'SURPLUS_MATERIAL_IDS = frozenset({\n'
        '    "92",    # Sap（树液，树桶副产品）\n'
        '    "766",   # Slime（史莱姆掉落）\n'
        '})\n',
        'SURPLUS_MATERIAL_IDS = frozenset({\n'
        '    "92",    # Sap（树液，树桶副产品）\n'
        '    "766",   # Slime（史莱姆掉落）\n'
        '    "388",   # Wood（变异：把建材加回可卖表）\n'
        '})\n',
        "木材加回可卖表 ⇒ 表级 fail-closed 判据被破坏（换种子钱通道会卖建材）",
    ),
    (
        "m5_wood_back_to_pressure_tier",
        FARMWORK_REL,
        'SLOT_RELIEF_MATERIAL_IDS = frozenset({\n'
        '    "92",    # Sap\n'
        '    "766",   # Slime\n'
        '})\n',
        'SLOT_RELIEF_MATERIAL_IDS = frozenset({\n'
        '    "92",    # Sap\n'
        '    "766",   # Slime\n'
        '    "388",   # Wood（变异：空格压力通道把建材加回可卖档）\n'
        '})\n',
        "木材加回压力通道分档表 ⇒ 满包时又卖建材（卡 A 纪律反转）",
    ),
    (
        "m2_inventory_blocked_unconditional",
        LONGRUN_REL,
        "        accepted = not gaps\n",
        "        accepted = True\n",
        "四门槛失效 ⇒ exec>0 / 缺口径也认「腾不出」收工（洗白）",
    ),
    (
        "m3_clear_gate_removed",
        LONGRUN_REL,
        "            if task == \"clear_area\":\n"
        "                _gate_why = self._clear_bag_gate_reason(obs)\n"
        "                if _gate_why:\n"
        "                    self._note_clear_area_bag_gate(task, _gate_why)\n"
        "                    return []\n",
        "            if False:\n"
        "                _gate_why = self._clear_bag_gate_reason(obs)\n"
        "                if _gate_why:\n"
        "                    self._note_clear_area_bag_gate(task, _gate_why)\n"
        "                    return []\n",
        "满包清障闸被拆 ⇒ 0 空格仍新开 clear_area（掉落即丢）",
    ),
    (
        "m4_clear_loot_cap_removed",
        LONGRUN_REL,
        "            if _bag_free is not None and int(_bag_free) <= 0:\n"
        "                _left = max(0, CLEAR_LOOT_LOSS_MAX_STEPS - int(self.loot_lost_steps_today))\n"
        "                if _left <= 0:\n"
        "                    self._note_clear_area_bag_gate(task, \"loot_lost_steps 已到全天上限\")\n"
        "                    return []\n"
        "                limit = min(limit, _left)\n",
        "            if False:\n"
        "                _left = max(0, CLEAR_LOOT_LOSS_MAX_STEPS - int(self.loot_lost_steps_today))\n"
        "                if _left <= 0:\n"
        "                    self._note_clear_area_bag_gate(task, \"loot_lost_steps 已到全天上限\")\n"
        "                    return []\n"
        "                limit = min(limit, _left)\n",
        "全天 loot_lost_steps 上界失效 ⇒ 满包清障丢失无界",
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

    with tempfile.TemporaryDirectory(prefix="t28-mutate-") as tmp:
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
