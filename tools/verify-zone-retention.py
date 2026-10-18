#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verify-zone-retention：跨日对比指定田区的 blocker 计数（P0-3）。

用法：
  python tools/verify-zone-retention.py --before obs_before.json --after obs_after.json [--zone field_nw] [--all]

判定：
  - 对每个指定 zone，before 与 after 的 zone_blockers_total 都必须 == 0
    才算"连续保持清空"。
  - 任一观测 tilesTruncated=True ⇒ 该 zone 【无法判定】（不计 PASS）。
  - 任一 zone 不满足 ⇒ exit 1。

只读观测 JSON，不采信 journal 自述。zone bounds 由 before 观测推导（fields.zones_from_observe）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.fields import (  # noqa: E402
    ZONE_BLOCKER_KINDS,
    zone_blockers_total,
    zones_from_observe,
)


def load_obs(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description="verify zone retention across two observes")
    ap.add_argument("--before", required=True, help="Day N observe JSON (full)")
    ap.add_argument("--after", required=True, help="Day N+1 observe JSON (full)")
    ap.add_argument("--zone", action="append", default=[], help="zone name (repeatable)")
    ap.add_argument("--all", action="store_true", help="check all zones present in --before")
    ap.add_argument("--split", type=int, default=2)
    args = ap.parse_args()

    before = load_obs(args.before)
    after = load_obs(args.after)

    zones = zones_from_observe(before, split=args.split)
    if args.all or not args.zone:
        target_names = [z.name for z in zones]
    else:
        target_names = list(args.zone)

    zone_by_name = {z.name: z for z in zones}

    print("zone        before  after   verdict")
    print("-" * 40)
    all_ok = True
    for name in target_names:
        z = zone_by_name.get(name)
        if z is None:
            print(f"{name:<11}  ?       ?       【无法判定】zone not found in before obs")
            all_ok = False
            continue
        b = zone_blockers_total(z, before)
        a = zone_blockers_total(z, after)
        if b is None or a is None:
            verdict = "【无法判定】tilesTruncated"
            all_ok = False
        elif b == 0 and a == 0:
            verdict = "PASS (retained clear)"
        else:
            verdict = "FAIL"
            all_ok = False
        bb = "NA" if b is None else str(b)
        aa = "NA" if a is None else str(a)
        print(f"{name:<11}  {bb:<6}  {aa:<6}  {verdict}")

    print()
    print("ZONE_BLOCKER_KINDS =", sorted(ZONE_BLOCKER_KINDS))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
