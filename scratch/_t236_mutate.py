"""task-236 变异自检（跑完保留作审计证据）。

用法：`python scratch/_t236_mutate.py`
做法：把 `brain/`、`tests/`、`tools/` 拷到临时目录，逐条施加变异，跑定向用例，
按 `FAIL:`/`ERROR:` 行数统计杀掉多少条。基线必须 0 红。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGETS = [
    "tests.test_verify_run3",
    "tests.test_longrun.TestTask236CleanupGuard",
]
#: (名字, 相对路径, 原文, 变异后)
MUTATIONS = [
    ("m236a_no_cleanup",
     "brain/agentfarm/longrun.py",
     "        cleanup = self._cleanup_modals_before_finish()",
     '        cleanup = {"attempts": 0, "menu": None, "stuck": False}'),
    ("m236b_plugin_lines_as_judge",
     "tools/verify-run3.py",
     '_PLUGIN_LINE_MARKERS = (" by ", "| v")',
     "_PLUGIN_LINE_MARKERS = ()"),
    ("m236c_no_order_check",
     "tools/verify-run3.py",
     "    if newday_line and save_line and newday_line > save_line:",
     "    if False:"),
    ("m236d_dismiss_profession_choice",
     "brain/agentfarm/longrun.py",
     "                if pending is None or list(pending):",
     "                if False:"),
]


def run_suite(root: Path) -> tuple[int, str]:
    env = {"PYTHONUTF8": "1", "PYTHONPATH": str(root / "brain"),
           "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
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
        for sub in ("brain", "tests", "tools"):
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
