"""task-86: 旧/新口径并排跑（不改 tools/，只在 scratch 里驱动冻结副本）。

用法:
  python scratch/_t86_side.py [--days 3] [--glob "logs/*.jsonl" ...]

输出 TSV（stdout）；同时把原始 JSON 落到 scratch/_t86_json/<tag>.<old|new>.json。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = os.path.join(ROOT, "scratch", "_t86_tool_old.py")
NEW = os.path.join(ROOT, "scratch", "_t86_tool_new.py")
OUT = os.path.join(ROOT, "scratch", "_t86_json")


def run(tool: str, journal: str, days: int) -> tuple[int, dict | None]:
    p = subprocess.run([sys.executable, tool, "--journal", journal, "--days", str(days), "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        data = json.loads(p.stdout)
    except Exception:
        data = None
    return p.returncode, data


def tag_of(path: str) -> str:
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    return rel.replace("/", "__").replace(".jsonl", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--glob", action="append", default=None)
    ap.add_argument("--only", default=None, help="只跑名字含该子串的账本")
    args = ap.parse_args()
    pats = args.glob or ["scratch/*.jsonl", "logs/*.jsonl"]
    paths: list[str] = []
    for pat in pats:
        paths.extend(glob.glob(os.path.join(ROOT, pat)))
    paths = sorted(p for p in set(paths) if not os.path.basename(p).startswith("_t86"))
    if args.only:
        paths = [p for p in paths if args.only in p]
    os.makedirs(OUT, exist_ok=True)

    print("\t".join(["ledger", "old_rc", "new_rc", "old_prob", "new_prob",
                     "history", "old_streak", "new_streak", "old_verdict", "new_verdict", "changed"]))
    n_changed = 0
    for path in paths:
        tag = tag_of(path)
        rc_o, o = run(OLD, path, args.days)
        rc_n, n = run(NEW, path, args.days)
        with open(os.path.join(OUT, f"{tag}.old.json"), "w", encoding="utf-8") as fh:
            json.dump(o, fh, ensure_ascii=False, indent=2)
        with open(os.path.join(OUT, f"{tag}.new.json"), "w", encoding="utf-8") as fh:
            json.dump(n, fh, ensure_ascii=False, indent=2)
        po = len(o.get("problems", [])) if o else -1
        pn = len(n.get("problems", [])) if n else -1
        hist = len(n.get("history_problems", [])) if n else -1
        so = o.get("verified_streak_tail") if o else "?"
        sn = n.get("verified_streak_tail") if n else "?"
        vo = o.get("verdict") if o else "PARSE_FAIL"
        vn = n.get("verdict") if n else "PARSE_FAIL"
        changed = "YES" if (rc_o, po, vo) != (rc_n, pn, vn) else ""
        if changed:
            n_changed += 1
        print("\t".join([os.path.relpath(path, ROOT).replace("\\", "/"), str(rc_o), str(rc_n),
                         str(po), str(pn), str(hist), str(so), str(sn), str(vo), str(vn), changed]))
    print(f"# ledgers={len(paths)} changed={n_changed} days={args.days}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
