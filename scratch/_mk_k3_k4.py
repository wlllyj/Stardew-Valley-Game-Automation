#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 neg-K 派生两个"内部自相矛盾但工具查不出"的账本（deputy-lead，只写 scratch/）。

K3: finish 谎报（code=1 / verified_streak=0）—— verify-run3 的 docstring 第 5 条声称"核对 finish 的 code"，
    实现里只把它显示出来，不参与 ok 判定。用来验证这个缺口。
K4: checks.watered_outdoor=true 但 final_water.scope="farm" 且 dry=5 —— 同一份账本里的两个浇水读数
    互相矛盾，工具不做交叉核对。用来验证 task-19 新字段与 checks 之间没有互检。
"""
from __future__ import annotations

import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "review-neg-K-forged-consistent.jsonl")


def read_rows(path: str) -> list[dict]:
    with io.open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_rows(name: str, rows: list[dict]) -> str:
    path = os.path.join(HERE, name)
    with io.open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("wrote", path, os.path.getsize(path), "bytes")
    return path


def main() -> int:
    k3 = read_rows(SRC)
    k3[-1].update({"code": 1, "verified_streak": 0})          # finish 自述"没达标"
    write_rows("review-neg-K3-forged-finish-lie.jsonl", k3)

    k4 = read_rows(SRC)
    for row in k4:
        if row.get("event") == "day_end":
            row["final_water"] = {"t": row.get("t"), "location": "Farm", "tiles": 6,
                                 "crops": 6, "dry": 5, "scope": "farm"}   # dry=5 却说浇完了
            row["checks"]["watered_outdoor"] = True
    write_rows("review-neg-K4-forged-water-contradiction.jsonl", k4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
