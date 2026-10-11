"""把 longrun 的 jsonl 日志压成"计数/排行"，绝不整表打印（避免刷屏烧上下文）。

用法：
    python tools\\longrun-report.py logs\\longrun-3day-run1.jsonl [--top 12]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys


def key_of(d: dict) -> str:
    t = d.get("tile")
    if isinstance(t, list):
        return "%d,%d" % (t[0], t[1])
    return str(t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    events = collections.Counter()
    keys: dict[str, list[str]] = {}
    decisions = collections.Counter()
    stages = collections.Counter()
    steps: collections.Counter = collections.Counter()
    days: list[dict] = []
    outcomes: list[dict] = []
    n = 0
    for raw in open(args.path, encoding="utf-8"):
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except Exception:
            continue
        n += 1
        e = str(d.get("event", "?"))
        events[e] += 1
        keys.setdefault(e, sorted(k for k in d if k != "t"))
        if e == "decision":
            decisions[json.dumps(d.get("intents"), ensure_ascii=False,
                                 sort_keys=True)] += 1
        elif e == "stage":
            stages["%s ok=%s skip=%s fail=%s stop=%s left=%s"
                   % (d.get("stage"), d.get("ok"), d.get("skipped"),
                      d.get("failed"), d.get("stopped"), d.get("leftover"))] += 1
        elif e == "step":
            steps["%s %s %s %s" % (key_of(d), d.get("action"), d.get("code"),
                                   str(d.get("reason"))[:28])] += 1
        elif e == "day_end":
            days.append(d)
        elif e == "outcome":
            outcomes.append(d)

    print("行数 %d" % n)
    print("事件 %s" % (events.most_common(),))
    for e in ("decision", "stage", "step", "day_start", "day_end", "idle", "stuck"):
        if e in keys:
            print("  %-10s 字段 %s" % (e, keys[e]))
    print("决策 top%d" % args.top)
    for k, v in decisions.most_common(args.top):
        print("  %3d  %s" % (v, k[:300]))
    print("阶段 top%d" % args.top)
    for k, v in stages.most_common(args.top):
        print("  %3d  %s" % (v, k))
    print("步 top%d（格, 动作, 结论, 理由）" % args.top)
    for k, v in steps.most_common(args.top):
        print("  %3d  %s" % (v, k))
    for d in days:
        print("day_end %s" % json.dumps(d, ensure_ascii=False)[:400])
    if outcomes:
        print("结果（kind/met/progress/reason/error/evidence）")
        for d in outcomes:
            print("  %s" % json.dumps(d, ensure_ascii=False)[:420])
    return 0


if __name__ == "__main__":
    sys.exit(main())
