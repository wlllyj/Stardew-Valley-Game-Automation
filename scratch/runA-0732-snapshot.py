# -*- coding: utf-8 -*-
"""run A（0.7.32 上的 runA-0732）外部快照 —— run9b-snapshot.py 的默认值包装。

卡面口径（Lead m02261 / task-162）：
  - 起跑后立刻：`python scratch\\runA-0732-snapshot.py --tag start`
  - 收工后：    `python scratch\\runA-0732-snapshot.py --tag end --pid-file logs\\longrun-runA-0732.pid`

默认：--journal logs/longrun-runA-0732.jsonl、--out scratch/runA-0732-external-snapshots.jsonl、
      --expected-mod-version 0.7.32；用户显式传的同名参数**覆盖**这里的默认值（argparse 后者胜）。
其余参数原样透传给 run9b-snapshot.py（--smapi-before / --pid-file / --save-* / --journal-lines / --note…）。
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TARGET = os.path.join(ROOT, "scratch", "run9b-snapshot.py")
DEFAULTS = [
    "--journal", "logs/longrun-runA-0732.jsonl",
    "--out", "scratch/runA-0732-external-snapshots.jsonl",
    "--expected-mod-version", "0.7.32",
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
