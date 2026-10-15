"""task-90：三副本并排（全部账本，默认 --days 3）。

用法：python scratch/_t90_side.py [days]
输出：`scratch/_t90_side_d<days>.txt` —— 每本账本 × old/buggy/fixed 的 rc / verdict / #prob / #hist；
      末尾列出"三副本判决不一致"的账本（预期：只有 run7 在 old↔buggy 之间不一致，且 buggy==fixed 逐字）。
"""
from __future__ import annotations

import glob
import hashlib
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COPIES = [
    ("old", "_t90_tool_old.py"),
    ("buggy", "_t90_tool_buggy.py"),
    ("fixed", "_t90_tool_fixed.py"),
]


def load(path: str):
    spec = importlib.util.spec_from_file_location("vr3_" + os.path.basename(path), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def run(mod, path: str, days: int):
    try:
        rows = mod.load(path)
    except Exception as exc:  # noqa: BLE001
        return {"err": str(exc)[:60]}
    ok, s = mod.report(rows, target_days=days)
    return {"rc": 0 if ok else 1, "verdict": s.get("verdict"),
            "n_problems": len(s.get("problems") or []), "n_history": len(s.get("history_problems") or []),
            "streak": s.get("verified_streak_tail")}


def main(argv: list[str]) -> int:
    days = int(argv[0]) if argv else 3
    mods = [(tag, load(os.path.join(ROOT, "scratch", name))) for tag, name in COPIES]
    books = sorted(glob.glob(os.path.join(ROOT, "scratch", "*.jsonl")) +
                   glob.glob(os.path.join(ROOT, "logs", "*.jsonl")))
    lines: list[str] = []
    diff_old_buggy: list[str] = []
    diff_buggy_fixed: list[str] = []
    for b in books:
        rel = os.path.relpath(b, ROOT)
        res = {tag: run(mod, b, days) for tag, mod in mods}
        row = f"{rel:<58}" + "".join(
            f"{res[tag].get('rc')}/{res[tag].get('n_problems')}/{res[tag].get('n_history'):<8}"
            for tag, _ in COPIES)
        lines.append(row)
        o, g, f = res["old"], res["buggy"], res["fixed"]
        if (o.get("rc"), o.get("n_problems"), o.get("n_history")) != \
           (g.get("rc"), g.get("n_problems"), g.get("n_history")):
            diff_old_buggy.append(f"{rel}: old={o} buggy={g}")
        if (g.get("rc"), g.get("n_problems"), g.get("n_history")) != \
           (f.get("rc"), f.get("n_problems"), f.get("n_history")):
            diff_buggy_fixed.append(f"{rel}: buggy={g} fixed={f}")
    header = (f"账本数 {len(books)}  --days {days}\n"
              f"{'账本':<58}{'old rc/p/h':<20}{'buggy rc/p/h':<20}fixed rc/p/h\n")
    body = "\n".join([header] + lines +
                     ["", f"old↔buggy 判决/问题数不同的账本：{len(diff_old_buggy)} 本"] + diff_old_buggy +
                     ["", f"buggy↔fixed 判决/问题数不同的账本：{len(diff_buggy_fixed)} 本"] + diff_buggy_fixed)
    out = os.path.join(ROOT, "scratch", f"_t90_side_d{days}.txt")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body + "\n")
    print(body)
    print(f"\n写到 {os.path.relpath(out, ROOT)}")
    for tag, name in COPIES:
        p = os.path.join(ROOT, "scratch", name)
        print(f"{name}: sha256={hashlib.sha256(open(p, 'rb').read()).hexdigest().upper()[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
