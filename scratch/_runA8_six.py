# -*- coding: utf-8 -*-
"""A″/B″ 跨日六串进度（只读）：按起点基准行号统计本跑窗口内的六串。

用法：
  python scratch\\_runA8_six.py [--tag runA8-0743] [--label "cross#1"] [--baseline logs\\<tag>-smapi-baseline.json]
每次调用追加一行到 logs/<tag>-sixchain-progress.jsonl，并打印：
  六串计数 + 行号 + NewDay>Save 硬问题判定 + 被排除的插件描述行(L16)明细。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOGS = os.path.join(ROOT, "logs")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")
PATS = {
    "newday": "Synchronizing 'NewDay' task",
    "before_save": "Context: before save.",
    "save_called": "SaveGame.Save() called.",
    "save_task": "Synchronizing 'Save' task",
    "completed": "completed without exceptions",
    "after_save": "after save, starting",
}


def l16_real(line: str) -> bool:
    if TS.match(line) is None:
        return False
    return (" by AgentFarm " not in line) and ("| v0." not in line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="runA8-0743")
    ap.add_argument("--label", default="")
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--journal", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-append", action="store_true")
    args = ap.parse_args()

    baseline_path = args.baseline or os.path.join(LOGS, f"{args.tag}-smapi-baseline.json")
    base = {}
    if os.path.exists(baseline_path):
        base = json.load(open(baseline_path, encoding="utf-8"))
    start_line = int(((base.get("smapi") or {}).get("window_starts_at_line")) or 1)
    journal = args.journal or os.path.join(LOGS, f"longrun-{args.tag}.jsonl")
    out = args.out or os.path.join(LOGS, f"{args.tag}-sixchain-progress.jsonl")

    if not os.path.exists(SMAPI):
        print(f"!! SMAPI 不存在：{SMAPI}", file=sys.stderr)
        return 2
    lines = open(SMAPI, encoding="utf-8", errors="replace").read().splitlines()

    hits: dict[str, list] = {k: [] for k in PATS}
    excluded: list[dict] = []
    for idx, s in enumerate(lines, 1):
        if idx < start_line:
            continue
        for key, needle in PATS.items():
            if needle in s:
                if not l16_real(s):
                    excluded.append({"key": key, "line": idx, "text": s[:160]})
                    continue
                hits[key].append({"line": idx, "time": (TS.match(s).group(1) if TS.match(s) else None),
                                  "text": s[:200]})
    counts = {k: len(v) for k, v in hits.items()}
    reasons: list[str] = []
    if counts["newday"] == 0:
        verdict = "本窗口还没跨日"
    elif counts["newday"] > counts["save_called"]:
        verdict = "FAIL：NewDay > Save called（有跨日没落盘）"
        reasons.append(f"NewDay {counts['newday']} > Save called {counts['save_called']}")
    elif counts["newday"] == counts["save_called"] == counts["after_save"]:
        verdict = "PASS：六串配对齐全"
    else:
        verdict = f"无法判定：NewDay {counts['newday']} / Save {counts['save_called']} / after {counts['after_save']}"

    # 存档四件（实时）
    save_dir = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
    saves = {}
    for name in ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old"):
        p = os.path.join(save_dir, name)
        if os.path.exists(p):
            st = os.stat(p)
            saves[name] = {"size": st.st_size,
                           "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))}
    # 账本末态
    jl = {}
    if os.path.exists(journal):
        recs = [json.loads(x) for x in open(journal, encoding="utf-8").read().splitlines() if x.strip()]
        de = [r for r in recs if r.get("event") == "day_end"]
        fin = [r for r in recs if r.get("event") == "finish"]
        jl = {"lines": len(recs), "day_end_n": len(de),
              "day_end": [{"day": r.get("day"), "ended_by": r.get("ended_by"),
                           "verified": r.get("verified"), "day_after": r.get("day_after")} for r in de],
              "finish": fin[-1] if fin else None}

    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "label": args.label, "tag": args.tag,
           "window_starts_at_line": start_line, "smapi_total_lines": len(lines),
           "counts": counts, "verdict": verdict, "reasons": reasons,
           "lines": {k: [h["line"] for h in v] for k, v in hits.items()},
           "times": {k: [h["time"] for h in v] for k, v in hits.items()},
           "excluded_l16": excluded[:10], "excluded_l16_total": len(excluded),
           "saves": saves, "journal": jl}
    if not args.no_append:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[{args.label or '进度'}] 窗口起点行 {start_line}（SMAPI 现 {len(lines)} 行）")
    print(f"  六串 = {json.dumps(counts, ensure_ascii=False)}")
    print(f"  行号 = " + json.dumps({k: v for k, v in rec['lines'].items() if v}, ensure_ascii=False))
    print(f"  L16 排除 {len(excluded)} 行" + (f"（例 {excluded[0]['text'][:100]}）" if excluded else ""))
    print(f"  判定 = {verdict}" + (f"；{'；'.join(reasons)}" if reasons else ""))
    print(f"  存档 = " + json.dumps(saves, ensure_ascii=False))
    print(f"  账本 = " + json.dumps(jl, ensure_ascii=False)[:600])
    print(f"已追加 {out}")
    return 0 if verdict.startswith("PASS") or verdict.startswith("本窗口") else 10


if __name__ == "__main__":
    sys.exit(main())
