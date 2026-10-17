"""task-218 变异自检：把工作树拷到临时目录、逐个打变异，跑定向用例数"杀了几条"。

用法：`python scratch/_t218_mutate.py`
输出：每个变异杀掉几条（0 = 变异逃逸，必须改用例或改修法）。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGETS = [
    "tests.test_farmwork.TestClearKeepsJudgement",
    "tests.test_farmwork.TestTask20ToolGatedClumps",
    "tests.test_longrun.TestTask218TreeClearing",
    "tests.test_longrun.TestPlotObserve",
    "tests.test_planner.Task218CapabilityGuards",
]

MUTATIONS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("m218a_tree_back_in_skip_kinds", [
        ("brain/agentfarm/farmwork.py",
         'SKIP_KINDS = {\n    "fruitTree":',
         'SKIP_KINDS = {\n    "tree": "旧行为：静默跳过树",\n    "fruitTree":'),
    ]),
    ("m218b_no_per_tile_guardrail_b", [
        ("brain/agentfarm/longrun.py",
         "if ok_steps and not cleared_tiles and not unclear_steps and not budget_or_tool:",
         "if False:"),
    ]),
    ("m218c_tree_budget_always_true", [
        ("brain/agentfarm/longrun.py",
         "if int(self.trees_cleared_today or 0) >= int(TREE_CLEAR_MAX_PER_DAY):",
         "if False:"),
        ("brain/agentfarm/longrun.py",
         "if (stam - reserve) <= float(TREE_STAMINA_ESTIMATE):",
         "if False:"),
    ]),
    ("m218d_plot_has_work_ignores_tree", [
        ("brain/agentfarm/longrun.py",
         'if (kind == TREE_KIND and "clear_area" not in deferred',
         'if (False and "clear_area" not in deferred'),
    ]),
    ("m218e_plot_observe_drops_trees_again", [
        ("brain/agentfarm/longrun.py",
         'if not t.get("crop") and str(t.get("kind") or "") not in CLEARABLE_KINDS + ("dirt",):',
         'if not t.get("crop") and str(t.get("kind") or "") not in ACTIONABLE_KINDS + ("dirt",):'),
    ]),
    ("m218f_no_per_tile_ledger", [
        ("brain/agentfarm/longrun.py",
         '"cleared_tiles": [list(t) for t in cleared_tiles],',
         '"cleared_tiles": [],'),
    ]),
    ("m218g_skip_kinds_not_subset", [
        ("brain/agentfarm/farmwork.py",
         'SKIP_KINDS = {\n    "fruitTree":',
         'SKIP_KINDS = {\n    "bushOnlyTest": "故意漏登记种类",\n    "fruitTree":'),
    ]),
]


def run_suite(root: Path) -> tuple[int, int]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(root / "brain")
    proc = subprocess.run([sys.executable, "-m", "unittest", *TARGETS],
                          cwd=str(root), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = proc.stderr or ""
    fails = 0
    for line in tail.splitlines():
        if line.startswith("FAIL:") or line.startswith("ERROR:"):
            fails += 1
    return fails, proc.returncode


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("brain", "tests"):
            shutil.copytree(REPO / name, root / name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        base_fails, base_rc = run_suite(root)
        print(f"基线：{base_fails} 条红（rc={base_rc}）")
        if base_fails or base_rc != 0:
            print("基线不绿，变异读数无意义；先修用例")
            return 2
        for name, patches in MUTATIONS:
            for rel, old, new in patches:
                path = root / rel
                text = path.read_text(encoding="utf-8")
                if old not in text:
                    print(f"{name}: 锚点找不到（{rel}）—— 变异无效")
                    return 2
                path.write_text(text.replace(old, new, 1), encoding="utf-8")
            fails, _rc = run_suite(root)
            print(f"{name}: 杀死 {fails} 条")
            for rel, old, new in patches:
                path = root / rel
                path.write_text(path.read_text(encoding="utf-8").replace(new, old, 1),
                                encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
