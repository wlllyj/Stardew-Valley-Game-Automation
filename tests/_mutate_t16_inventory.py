# -*- coding: utf-8 -*-
"""【task-16 / 0.7.45】背包空格口径 + 清障掉落留痕 + 满包腾格的**变异自检**。

对 `brain/agentfarm/farmwork.py` / `brain/agentfarm/longrun.py` 注入 5 条变异，
验证 `tests/test_longrun.py::TestTask16InventoryFull` 能全部杀掉：

* `m1_free_slots_uses_capacity`：`player_free_slots` 直接把 `inventoryCount` 当空格
  （容量 12、背包 12 行 ⇒ 误报 12 格）⇒ 满包掉落的证据链整体失效（run8 根因复活）；
* `m2_clear_loot_detection_off`：`clear()` 不再判 `loot_risk` ⇒ 掉落被拒收也不留 `loot_lost`；
* `m3_pressure_channel_off`：`_slot_relief` 的 `need<=0` 早退恢复 ⇒ 冬季 clear-only 的
  真满背包永远不会触发腾格；
* `m4_free_slots_trace_not_updated`：`_observe_free_slots` 漏写 `free_slots_last`
  ⇒ day_end 的空格 trace 恒为 None（读数缺失当 PASS 的反面案例）；
* `m5_buy_before_free_off`：`_preconditions_apply` 买种子前不再先腾格 ⇒
  `no_inventory_space` 空转复活。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t16_inventory.py

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
TARGET = "tests.test_longrun.TestTask16InventoryFull"
FARMWORK_REL = Path("brain") / "agentfarm" / "farmwork.py"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

# (id, 相对路径, 原文, 变异后, 说明)
MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    (
        "m1_free_slots_uses_capacity",
        FARMWORK_REL,
        '    return max(0, int(cap) - len(inv)), "ok"',
        '    return max(0, int(cap)), "ok"',
        "把容量当空格 ⇒ 满包(12/12)误报 12 格，掉落留痕/腾格全部失效",
    ),
    (
        "m2_clear_loot_detection_off",
        FARMWORK_REL,
        '        loot_risk = free_status0 == "ok" and int(free0) <= 0',
        "        loot_risk = False",
        "clear() 不再判背包满 ⇒ 掉落被游戏拒收也不留 loot_lost",
    ),
    (
        "m3_pressure_channel_off",
        LONGRUN_REL,
        "        if need <= 0 and not space_pressure:",
        "        if need <= 0:",
        "0 空格压力通道早退复活 ⇒ 冬季 clear-only 真满背包永不腾格",
    ),
    (
        "m4_free_slots_trace_not_updated",
        LONGRUN_REL,
        "        rep.free_slots_last = value",
        "        rep.free_slots_last = None",
        "day_end 的空格 trace 漏写 last（读数缺失不许当 PASS）",
    ),
    (
        "m5_buy_before_free_off",
        LONGRUN_REL,
        '        if fs_status == "ok" and int(free_slots) < 1:\n'
        "            if (seeds_total == 0 and money >= self.seed_price",
        "        if False:\n"
        "            if (seeds_total == 0 and money >= self.seed_price",
        "买种子前不再先腾格 ⇒ no_inventory_space 空转（run8 day12/13 形态）复活",
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

    with tempfile.TemporaryDirectory(prefix="t16-mutate-") as tmp:
        tree = Path(tmp) / "frozen"
        tree.mkdir()
        if args.from_worktree:
            _copy_worktree(tree)
        else:
            _extract_head(tree)

        originals: dict[Path, str] = {}
        for _mid, rel, _old, _new, _why in MUTATIONS:
            target = tree / rel
            if rel not in originals:
                originals[rel] = target.read_text(encoding="utf-8")

        ok, ran, _ = _unittest(tree)
        if not ok:
            print(f"[baseline] × 基线不是绿的（Ran {ran}）——先修测试再谈变异")
            return 2
        print(f"[baseline] OK（{TARGET}：Ran {ran} tests）")

        killed_total = 0
        survived: list[str] = []
        for mid, rel, old, new, why in MUTATIONS:
            target = tree / rel
            original = originals[rel]
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
