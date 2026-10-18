"""task-228 变异自检：把 brain+tests 拷到临时目录，逐条打变异并数红。

跑法（仓库根目录）：

    python scratch/_t228_mutate.py

基线应 0 红；每条变异都应至少杀掉 1 条用例。变异锚点全部是**生产代码里的真判据**
（不是测试里的文本），所以杀数能说明用例真的钉住了行为。

四条变异：
  * m228a_questions_are_advanced —— 去掉"提问不许推进"（`_event_advance_possible` 不看 is_question）
  * m228b_no_stall_limit      —— 去掉连续 stalled 上限（点不动也一直点）
  * m228c_no_daily_budget     —— 去掉每日步数额度
  * m228d_no_streak_reset     —— 真推进后不清零 stalled 连续计数
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LONGRUN = Path("brain") / "agentfarm" / "longrun.py"
TARGETS = ["tests.test_longrun.TestTask228DialogueAdvance",
           "tests.test_longrun.TestTask41EventBlocked"]

MUTATIONS: list[tuple[str, str, str]] = [
    ("m228a_questions_are_advanced",
     "        if not event_up or not has_dialogue or is_question:\n            return False",
     "        if not event_up or not has_dialogue:\n            return False"),
    ("m228b_no_stall_limit",
     "        if self.event_stall_streak >= EVENT_STALL_GIVE_UP:\n            return False",
     "        if False:\n            return False"),
    ("m228c_no_daily_budget",
     "        if self.event_advance_steps_today >= EVENT_ADVANCE_DAY_STEPS:\n            return False",
     "        if False:\n            return False"),
    ("m228d_no_streak_reset",
     "            self.event_advance_steps_today += stepped\n            self.event_stall_streak = 0",
     "            self.event_advance_steps_today += stepped"),
]


def run_suite(root: Path) -> tuple[int, str]:
    env = {"PYTHONUTF8": "1", "PYTHONPATH": str(root / "brain"),
           "PATH": shutil.os.environ.get("PATH", "")}
    proc = subprocess.run([sys.executable, "-m", "unittest", *TARGETS],
                          cwd=str(root), env=env, capture_output=True, text=True,
                          errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    return out.count("\nFAIL: ") + out.count("\nERROR: "), out


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="t228_mut_") as tmp:
        root = Path(tmp)
        shutil.copytree(REPO / "brain", root / "brain")
        shutil.copytree(REPO / "tests", root / "tests")
        src = (REPO / LONGRUN).read_text(encoding="utf-8")
        base_fail, base_out = run_suite(root)
        print(f"基线：{base_fail} 红")
        if base_fail:
            print(base_out[-2000:])
            return 1
        for name, old, new in MUTATIONS:
            assert old in src, f"变异锚点找不到：{name}"
            mutated = src.replace(old, new, 1)
            (root / LONGRUN).write_text(mutated, encoding="utf-8")
            fails, out = run_suite(root)
            (root / LONGRUN).write_text(src, encoding="utf-8")
            print(f"{name}: 杀 {fails}")
            if fails == 0:
                print("  !! 这条变异没被杀掉 —— 用例没钉住这个判据")
                print(out[-1500:])
                return 1
    print("全部变异都被杀掉")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
