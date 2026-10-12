# -*- coding: utf-8 -*-
"""打印 task-15 各处改动的行号（完工回报用）。"""
import io
import os

REPO = r"D:\Deepseek Harness Workspace\星露谷游戏自动化"
PATS = ["def is_env_blocked", "max_env_retries", "if not self._seed_outlook(obs)[2]",
        "in_plot", '"env_retry"', "failed_any", "unmet_leftover", '"no_unmet_stages"',
        "已知局限", "last_by_stage"]
for rel in ("brain\\agentfarm\\longrun.py",):
    p = os.path.join(REPO, rel)
    print("==", rel)
    for i, line in enumerate(io.open(p, encoding="utf-8").read().splitlines(), 1):
        if any(pat in line for pat in PATS):
            print(f"{i}: {line.strip()[:120]}")
