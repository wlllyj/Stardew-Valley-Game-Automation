# -*- coding: utf-8 -*-
"""通用账本过滤（只读）：按 event 名和/或子串过滤 JSONL 记录，逐条原样打印。

    python scratch\\jq.py --file logs\\longrun-3day-llm-run5.jsonl --event blocked
    python scratch\\jq.py --file logs\\...jsonl --contains failed --limit 6
"""
from __future__ import annotations

import argparse
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--event", default=None)
    ap.add_argument("--contains", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--keys", default=None, help="只打印这些顶层键（逗号分隔）")
    args = ap.parse_args()

    n = 0
    with open(args.file, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if args.event and r.get("event") != args.event:
                continue
            if args.contains and args.contains not in line:
                continue
            n += 1
            if args.keys:
                r = {k: r.get(k) for k in args.keys.split(",")}
            print(f"#{i:3} {json.dumps(r, ensure_ascii=False)}")
            if args.limit and n >= args.limit:
                break
    print(f"\n命中 {n} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
