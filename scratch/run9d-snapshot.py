# -*- coding: utf-8 -*-
"""run9d 外部快照（run9b-snapshot.py 的 run9d 默认值包装）。

卡面口径（task-147）：
  - 起跑后立刻：`python scratch\\run9d-snapshot.py --tag start`
  - 收工后：    `python scratch\\run9d-snapshot.py --tag end --pid-file logs\\longrun-3day-llm-run9d.pid`

默认：--journal logs/longrun-3day-llm-run9d.jsonl、--out scratch/run9d-external-snapshots.jsonl、
      --expected-mod-version 0.7.31；用户显式传的同名参数**覆盖**这里的默认值（argparse 后者胜）。
所有其余参数原样透传给 run9b-snapshot.py（--smapi-before / --save-* / --journal-lines / --note…）。
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TARGET = os.path.join(ROOT, "scratch", "run9b-snapshot.py")
DEFAULTS = [
    "--journal", "logs/longrun-3day-llm-run9d.jsonl",
    "--out", "scratch/run9d-external-snapshots.jsonl",
    "--expected-mod-version", "0.7.31",
]


def main() -> int:
    if not os.path.exists(TARGET):
        print(f"找不到 {TARGET}", file=sys.stderr)
        return 2
    argv = [sys.executable, "-X", "utf8", TARGET] + DEFAULTS + sys.argv[1:]
    print("$ " + " ".join(["python", "scratch/run9b-snapshot.py"] + DEFAULTS + sys.argv[1:]))
    return subprocess.call(argv, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
