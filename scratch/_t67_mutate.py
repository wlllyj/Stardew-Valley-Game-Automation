"""task-67 变异自检（跑完即弃）：把 brain/tests 复制到临时目录 + 打补丁 + 跑指定用例。

用法（两处补丁各跑一次）：

  python scratch\\_t67_mutate.py m67a   # is_seed_offer 恒 True（不筛名字）
  python scratch\\_t67_mutate.py m67b   # _seed_outlook 丢掉 `not seed_dead_today` 的门

预期：m67a ⇒ `TestTask67SeedChoice.test_shelf_without_seeds_is_not_bought` 红；
      m67b ⇒ `TestTask67SeedChoice.test_seed_dead_today_disarms_the_reason` 红。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

MUTATIONS = {
    "m67a": (
        "brain/agentfarm/farmwork.py",
        "    return any(hint in low for hint in SEED_NAME_HINTS)",
        "    return True",
        "tests.test_longrun.TestTask67SeedChoice.test_shelf_without_seeds_is_not_bought",
    ),
    "m67b": (
        "brain/agentfarm/longrun.py",
        "        can = seeds > 0 or (self.allow_buy and money >= self.seed_price\n"
        "                            and not self.seed_dead_today)",
        "        can = seeds > 0 or (self.allow_buy and money >= self.seed_price)",
        "tests.test_longrun.TestTask67SeedChoice.test_seed_dead_today_disarms_the_reason",
    ),
}


def main() -> int:
    name = sys.argv[1]
    rel, old, new, test = MUTATIONS[name]
    with tempfile.TemporaryDirectory(prefix=f"t67_{name}_") as tmp:
        dst = Path(tmp)
        for part in ("brain", "tests"):
            shutil.copytree(REPO / part, dst / part, ignore=shutil.ignore_patterns("__pycache__"))
        target = dst / rel
        text = target.read_text(encoding="utf-8")
        if old not in text:
            print(f"[{name}] 补丁锚点没找到：{rel}")
            return 2
        target.write_text(text.replace(old, new, 1), encoding="utf-8")
        env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(dst / "brain"))
        proc = subprocess.run([sys.executable, "-m", "unittest", test],
                              cwd=str(dst), env=env, capture_output=True, text=True)
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        print(f"[{name}] {test} exit={proc.returncode}")
        for line in tail:
            print("   ", line)
        return 0 if proc.returncode != 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
