# -*- coding: utf-8 -*-
"""SMAPI 日志只读计数 + 尾部 N 行（UTF-8 安全）。"""
from __future__ import annotations

import argparse
import os

SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
KEYS = [
    "Synchronizing 'NewDay' task",
    "SaveGame.Save() called",
    "after save, starting",
    "Disconnected: ClosedGame",
    "Disposing",
    "soft_oal",
    "ERROR",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tail", type=int, default=14)
    args = ap.parse_args()
    lines = open(SMAPI, encoding="utf-8", errors="replace").read().splitlines()
    print(f"SMAPI-latest.txt 总行数 = {len(lines)}")
    for k in KEYS:
        print(f"  {k!r:42} = {sum(1 for l in lines if k in l)}")
    print(f"尾部 {args.tail} 行：")
    for l in lines[-args.tail:]:
        print("   ", l)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
