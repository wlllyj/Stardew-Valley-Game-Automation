# -*- coding: utf-8 -*-
"""只读：从 SMAPI 日志里挖出 run2 两次失败 sleep 的上下文，回答
"脑到底有没有先对床 interact"。不碰游戏/桥，只读文本。
"""
from __future__ import annotations

import os
import re
import sys

SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "smapi-sleep-window.txt")
OUT = os.path.abspath(OUT)

INTEREST = re.compile(r"sleep|interact|exec|move_to|checkAction|answerDialogue|startSleep|NewDay|SaveGame")


def main() -> int:
    with open(SMAPI, "r", encoding="utf-8", errors="replace") as fh:
        lines = [ln.rstrip("\n") for ln in fh]

    print(f"SMAPI 日志共 {len(lines)} 行：{SMAPI}")

    # 1) 所有 sleep 行 + 前后窗口
    idx = [i for i, ln in enumerate(lines) if "sleep" in ln.lower()]
    print(f"\n含 'sleep' 的行：{len(idx)} 条")
    for i in idx:
        print(f"  [{i + 1}] {lines[i][:200]}")

    # 2) 每次 sleep 前 30 行里，所有 /v1/exec（即 Mod 收到的技能请求）
    print("\n" + "=" * 72)
    print("每次 sleep 前 30 行内的 POST /v1/exec 与 interact")
    print("=" * 72)
    for i in idx:
        lo = max(0, i - 30)
        print(f"\n--- sleep 行 [{i + 1}] {lines[i][:120]}")
        for j in range(lo, i + 1):
            ln = lines[j]
            if "exec" in ln or "interact" in ln or "move_to" in ln or "skill=" in ln:
                print(f"  [{j + 1}] {ln[:220]}")

    # 3) 全文计数
    print("\n" + "=" * 72)
    print("全文计数")
    print("=" * 72)
    for pat in ["skill=interact", "interact", "skill=sleep", "answerDialogueAction",
                "answerDialogue(", "startSleep", "Synchronizing 'NewDay'", "SaveGame.Save()"]:
        n = sum(1 for ln in lines if pat in ln)
        print(f"  {pat!r}: {n}")

    # 4) 落盘窗口
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(f"SMAPI={SMAPI} 共 {len(lines)} 行\n\n")
        for i in idx:
            lo = max(0, i - 30)
            hi = min(len(lines), i + 12)
            fh.write(f"===== sleep 行 [{i + 1}] 窗口 {lo + 1}..{hi} =====\n")
            for j in range(lo, hi):
                fh.write(f"[{j + 1}] {lines[j]}\n")
            fh.write("\n")
    print(f"\n窗口已写入 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
