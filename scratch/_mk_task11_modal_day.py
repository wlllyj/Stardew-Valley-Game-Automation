#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""task-11 口径一致性探针（deputy-lead，只写 scratch/）：
把绿账本的最后一天改成 ended_by="blocked_modal" + checks.no_blocking_modal=false + verified=false，
看两个工具怎么读这一天（verify-run3 是否判问题、analyze-longrun 的 checks 文案是否认得这个键）。
"""
from __future__ import annotations

import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "journal-green.jsonl")
DST = os.path.join(HERE, "review-task11-modal-day.jsonl")


def main() -> int:
    rows = []
    with io.open(SRC, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    end = [r for r in rows if r.get("event") == "day_end"][-1]
    end["ended_by"] = "blocked_modal"
    end["ended_reason"] = "职业选择弹窗（候选 [0, 1]）等人处理"
    end["verified"] = False
    end["checks"]["no_blocking_modal"] = False
    end["checks"]["slept_by_us"] = False
    with io.open(DST, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote", DST, os.path.getsize(DST), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
