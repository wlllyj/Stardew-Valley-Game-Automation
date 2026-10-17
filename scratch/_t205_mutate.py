#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""task-216 GAP-1：变异体实测（原 task-205 的 m205a–d 在库里没有定义，deputy task-206 点名）。

跑法（仓库根）：

    set PYTHONUTF8=1 & set PYTHONPATH=<repo>\\brain & python scratch\\_t205_mutate.py

每条变异：**就地**改一个文件 → 跑指定测试集 → 统计红（failures+errors）→ 立刻还原。
还原用字节级备份，异常也会 restore（finally），跑完再断言四处文件与备份逐字节一致。

为什么必须实测：deputy 的对抗验收（task-180/190/206）会照抄这些数字复核；
作者自报的杀数不算数（task-205 的自报就与库里的变异定义对不上）。
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable

LONGRUN = REPO / "brain" / "agentfarm" / "longrun.py"
FARMWORK = REPO / "brain" / "agentfarm" / "farmwork.py"
CATALOG = REPO / "mod" / "AgentFarm.Bridge" / "SkillCatalog.cs"

PY_TARGETS = [
    "tests.test_farmwork.TestTask205ToolUpgrade",
    "tests.test_longrun.TestTask205ToolUpgradePlan",
    "tests.test_longrun.TestTask216ToolUpgradeDeadlockAndJournal",
]

# (名字, 文件, 原文, 替换, 期望杀数)
MUTATIONS = [
    ("m205a_run_day_not_wired", LONGRUN,
     "            if self._maybe_tool_upgrade(obs, rep):\n                continue",
     "            if False and self._maybe_tool_upgrade(obs, rep):\n                continue",
     3),
    ("m205b_suspended_stages_empty", LONGRUN,
     "        return tool_suspended_stages(obs)",
     "        return set()   # MUTANT: 装作没有暂停阶段",
     3),
    ("m205c_plan_ignores_in_flight", LONGRUN,
     "        if being:\n            if days is None:",
     "        if False and being:\n            if days is None:",
     4),
    ("m205d_pickup_ignores_days_left", FARMWORK,
     "        if days > 0:",
     "        if False and days > 0:   # MUTANT",
     1),
    ("m216a_pickup_not_prioritized", LONGRUN,
     '        if action == "pickup":\n            return True                          # 【F3】取回一律放行',
     '        if False and action == "pickup":\n            return True                          # MUTANT',
     1),    ("m216b_skip_journal_removed", LONGRUN,
     "            if not self.tool_upgrade_skipped_noted:",
     "            if False and not self.tool_upgrade_skipped_noted:   # MUTANT",
     2),
    ("m216c_money_only_counts_as_upgrade", FARMWORK,
     "        if appeared or tier_next:",
     "        if appeared or tier_next or money_down:   # MUTANT",
     1),
    ("m216d_pickup_clears_without_tool_back", FARMWORK,
     "        if being_after is None and tool_back:",
     "        if being_after is None:   # MUTANT",
     1),
]


def run_python_tests() -> int:
    proc = subprocess.run(
        [PY, "-m", "unittest", *PY_TARGETS],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return count_red(proc.stderr + proc.stdout)


def run_csharp_selftest() -> int:
    proc = subprocess.run(
        ["dotnet", "run", "--project", str(REPO / "mod" / "AgentFarm.Bridge.Tests"), "-c", "Release"],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    red = count_red(proc.stdout + proc.stderr)
    if proc.returncode != 0 and red == 0:
        red = 1
    return red


def count_red(output: str) -> int:
    """从 unittest / 自检输出数红：`FAIL: `/`ERROR: ` 行数 + `FAILED (failures=N, errors=M)`。"""
    red = 0
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAIL: ") or stripped.startswith("ERROR: "):
            red += 1
    marker = "FAILED ("
    if marker in output:
        # 兜底：输出被截断时用汇总行（取 fail/err 两个数字）
        import re
        m = re.search(r"FAILED \(failures=(\d+), errors=(\d+)\)", output) or re.search(
            r"FAILED \(failures=(\d+)\)", output) or re.search(r"FAILED \(errors=(\d+)\)", output)
        if m:
            red = max(red, sum(int(g) for g in m.groups() if g))
    return red


def main() -> int:
    if not (LONGRUN.is_file() and FARMWORK.is_file() and CATALOG.is_file()):
        print("找不到源文件（请在仓库根跑）")
        return 2

    backups = {p: p.read_bytes() for p in (LONGRUN, FARMWORK, CATALOG)}

    py_mutations = [m for m in MUTATIONS]
    results: list[tuple[str, int, int]] = []

    # 基线：不改变异时必须 0 红（否则后面的数字没意义）
    base = run_python_tests()
    print(f"baseline(python)            -> red {base}")
    if base != 0:
        print("基线就是红的：先修好再跑变异（变异数字没有意义）")
        return 2

    for name, path, old, new, expected in py_mutations:
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            print(f"{name:34s} -> SKIP（原文命中 {text.count(old)} 次，期望 1 次）")
            continue
        path.write_text(text.replace(old, new), encoding="utf-8")
        try:
            red = run_python_tests()
        finally:
            path.write_bytes(backups[path])
        results.append((name, red, expected))
        print(f"{name:34s} -> 杀 {red}（期望 ≥{expected}）{'  ❌ 没杀够' if red < expected else ''}")

    # ---- SkillCatalog 的 C# 护栏变异：删掉 Executable 里的 machine ----
    # 期望：`t216_create_cases_match_catalog`（Skills.Create 的 case 与表不一致）必红。
    text = CATALOG.read_text(encoding="utf-8")
    if text.count('"machine",') == 1:
        CATALOG.write_text(text.replace('"machine",', ""), encoding="utf-8")
        try:
            red = run_csharp_selftest()
        finally:
            CATALOG.write_bytes(backups[CATALOG])
        results.append(("m216e_catalog_drops_machine(C#)", red, 1))
        print(f"{'m216e_catalog_drops_machine(C#)':34s} -> 杀 {red}（期望 ≥1）{'  ❌ 没杀够' if red < 1 else ''}")
    else:
        print("m216e_catalog_drops_machine(C#)    -> SKIP（`\"machine\",` 不唯一）")

    # ---- 还原校验：逐字节一致 ----
    dirty = [str(p.relative_to(REPO)) for p, blob in backups.items() if p.read_bytes() != blob]
    print("restore check:", "OK（源文件已逐字节还原）" if not dirty else f"FAIL {dirty}")
    total = sum(r for _n, r, _e in results)
    weak = [n for n, r, e in results if r < e]
    print(f"合计杀 {total}；偏弱变异：{weak or '无'}")
    return 0 if (not dirty and not weak) else 1


if __name__ == "__main__":
    raise SystemExit(main())
