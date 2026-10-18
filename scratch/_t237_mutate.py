"""task-237 变异自检（跑完保留作审计证据）。

用法：`python scratch/_t237_mutate.py`
做法：把 `brain/`、`tests/` 拷到临时目录，逐条施加变异，跑定向用例，
按 `FAIL:`/`ERROR:` 行数统计杀掉多少条。基线必须 0 红。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGETS = [
    "tests.test_farmwork.TestTask232SlotReliefPlan",
    "tests.test_longrun.TestTask232SpacePressure",
    "tests.test_longrun.TestTask198InventoryDay",
]
#: (名字, 相对路径, 原文, 变异后)
MUTATIONS = [
    # 需求驱动退回"固定 +1 格"
    ("m237a_target_back_to_reserve_plus_one",
     "brain/agentfarm/longrun.py",
     "        target_free = min(SLOT_RESERVE + max(0, int(demand)), SLOT_FREE_CAP)",
     "        target_free = SLOT_RESERVE + 1"),
    # 需求上限压到 3（等于不按需求腾）
    ("m237b_demand_cap_three",
     "brain/agentfarm/longrun.py",
     "HARVEST_DEMAND_CAP = 12",
     "HARVEST_DEMAND_CAP = 3"),
    # 关掉"今天的收获产物优先"
    ("m237c_ignore_prefer_qids",
     "brain/agentfarm/farmwork.py",
     '        hit = 0 if (str(st["qid"]) in prefer or str(st["bareId"]) in prefer_bare) else 1',
     "        hit = 0"),
    # 关掉"没有可腾来源就不消耗轮数"的早退（0.7.40 A2 的无效轮）
    ("m237d_consume_round_without_source",
     "brain/agentfarm/longrun.py",
     '        if not harvested_now and not pre_plan.get("slots"):',
     "        if False:"),
]


def run_suite(root: Path) -> tuple[int, str]:
    env = {"PYTHONUTF8": "1", "PYTHONPATH": str(root / "brain"),
           "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    proc = subprocess.run([sys.executable, "-m", "unittest", *TARGETS],
                          cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    out = (proc.stdout or "") + (proc.stderr or "")
    fails = sum(1 for line in out.splitlines()
                if line.startswith("FAIL:") or line.startswith("ERROR:"))
    return fails, out


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for sub in ("brain", "tests"):
            shutil.copytree(REPO / sub, root / sub,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        fails, out = run_suite(root)
        print(f"baseline: {fails} red")
        for line in out.splitlines():
            if line.startswith("FAIL:") or line.startswith("ERROR:"):
                print("   ", line)
        if fails:
            print("基线本应是 0 红 —— 先修基线，别用变异掩盖")
            return 1
        total = 0
        for name, rel, old, new in MUTATIONS:
            path = root / rel
            original = path.read_text(encoding="utf-8")
            if old not in original:
                print(f"{name}: 锚点没命中 ⇒ 变异无效")
                return 2
            path.write_text(original.replace(old, new, 1), encoding="utf-8")
            fails, out = run_suite(root)
            path.write_text(original, encoding="utf-8")
            total += fails
            print(f"{name}: kills {fails}")
            for line in out.splitlines():
                if line.startswith("FAIL:") or line.startswith("ERROR:"):
                    print("   ", line)
        print(f"total kills: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
