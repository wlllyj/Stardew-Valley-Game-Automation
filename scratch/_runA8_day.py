# -*- coding: utf-8 -*-
"""A″/B″ 逐日读数提取（只读）：给 Lead m04705 要求的每个数字。

  python scratch\\_runA8_day.py --journal logs\\longrun-runA8-0743.jsonl           # 全部日报告
  python scratch\\_runA8_day.py --journal ... --day 2                              # 只看第 2 个日报告
打印每天：ended_by / verified / ok-skip-fail / checks / unreachable* counts / encircled /
refused_bound / deferred_tiles / plot_pending / assigned_undone / unreachable_tiles 坐标 /
no_progress_burst 次数与原文 / stuck ended_reason / 阶段汇总 / final_water。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

COUNT_KEYS = ("unreachable", "unreachable_tiles", "unreachable_bound", "unreachable_exempt",
              "unreachable_leftover", "encircled", "encircled_tiles", "refused", "refused_tiles",
              "refused_bound", "refused_exempt", "deferred_tiles", "deferred",
              "plot_pending", "assigned_undone", "assigned", "qualified", "no_progress_burst",
              "gated", "blocked_tile", "tool_ineffective")


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


def counter_view(d: dict) -> dict:
    return {k: d[k] for k in COUNT_KEYS if k in d}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default="logs/longrun-runA8-0743.jsonl")
    ap.add_argument("--day", type=int, default=None, help="第 N 个日报告（1-based；默认全部）")
    args = ap.parse_args()
    recs = load(args.journal)
    ends = [r for r in recs if r.get("event") == "day_end"]
    if not ends:
        print("账本里没有 day_end")
        return 2
    idxs = range(len(ends)) if args.day is None else [args.day - 1]
    for i in idxs:
        r = ends[i]
        lo = 0.0
        for prev in ends[:i]:
            lo = max(lo, prev.get("t") or 0)
        hi = r.get("t") or 0
        bursts = [x for x in recs if x.get("event") == "no_progress_burst" and lo <= (x.get("t") or 0) <= hi]
        print(f"=== day #{i + 1}：{r.get('day')} ===")
        print(f"  ended_by={r.get('ended_by')} verified={r.get('verified')} "
              f"day_after={r.get('day_after')} ok/skip/fail={r.get('ok_steps')}/{r.get('skipped_steps')}/{r.get('failed_steps')}")
        print("  ended_reason:", str(r.get("ended_reason"))[:300])
        print("  checks:", json.dumps(r.get("checks"), ensure_ascii=False))
        top = counter_view(r)
        print("  顶层计数:", json.dumps(top, ensure_ascii=False))
        fw = r.get("final_water")
        if fw:
            print("  final_water:", json.dumps({k: fw.get(k) for k in ("tiles", "crops", "dry", "scope")}, ensure_ascii=False))
        print(f"  no_progress_burst({lo:.1f}-{hi:.1f}s) = {len(bursts)} 次:", 
              json.dumps([{k: b.get(k) for k in ("t", "count", "tiles", "note", "reason")}
                          for b in bursts[:6]], ensure_ascii=False)[:600])
        # unreachable 坐标
        tiles = r.get("unreachable_tiles") or r.get("unreachable_coords")
        if tiles is None:
            for s in (r.get("stages") or []):
                if s.get("stage") in ("clear_area", "clear_dead", "clear_neighbor", "frontier_clear") and s.get("unreachable_tiles"):
                    tiles = (tiles or []) + list(s["unreachable_tiles"])
        print(f"  unreachable_tiles = {len(tiles) if isinstance(tiles, list) else '缺失'}：",
              json.dumps(tiles, ensure_ascii=False)[:600] if tiles else "—")
        # leftover 目标
        for k in ("leftover_targets", "pending_targets", "deferred_by_budget", "stamina_budget"):
            if k in r:
                print(f"  {k}:", json.dumps(r[k], ensure_ascii=False)[:500])
        st = r.get("stages") or []
        agg: dict[str, dict] = {}
        for s in st:
            k = s.get("stage")
            a = agg.setdefault(k, {"n": 0, "tiles": 0, "ok": 0, "failed": 0, "cleared": 0,
                                   "unreachable": 0, "stopped": []})
            a["n"] += 1
            a["tiles"] += int(s.get("tiles") or 0)
            a["ok"] += int(s.get("ok") or 0)
            a["failed"] += int(s.get("failed") or 0)
            a["cleared"] += len(s.get("cleared_tiles") or [])
            a["unreachable"] += int(s.get("unreachable") or 0)
            if s.get("stopped"):
                a["stopped"].append(s["stopped"])
        print("  阶段汇总:", json.dumps(agg, ensure_ascii=False)[:900])
        print("  步 5 视角（clear 类 ok vs cleared）:",
              json.dumps([{"stage": s.get("stage"), "ok": s.get("ok"),
                           "cleared": len(s.get("cleared_tiles") or [])}
                          for s in st if s.get("stage") in ("clear_area", "clear_dead", "clear_neighbor", "frontier_clear")
                          and (s.get("ok") or 0) > 0], ensure_ascii=False)[:600])
    return 0


if __name__ == "__main__":
    sys.exit(main())
