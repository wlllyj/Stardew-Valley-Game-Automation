"""task-90：三副本并排复跑（进程内调用工具 API，避免 3×N 次子进程）。

用法：
  python scratch/_t90_replay.py                     # 默认复跑 task-86 的 7 本伪造账本
  python scratch/_t90_replay.py <book.jsonl> [...]  # 指定账本

输出：每本账本 × 三副本的 rc / verdict / #problems / #history，并对 a4a/a4b 打印问题归类。
"""
from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = [
    ("old(7c4ff68^)", os.path.join(ROOT, "scratch", "_t90_tool_old.py")),
    ("buggy(7c4ff68)", os.path.join(ROOT, "scratch", "_t90_tool_buggy.py")),
    ("fixed(c6d2a7a)", os.path.join(ROOT, "scratch", "_t90_tool_fixed.py")),
]
DEFAULT_BOOKS = [
    "review-t86-a1-window-ok-history-bad.jsonl",
    "review-t86-a2-inwindow-contradiction.jsonl",
    "review-t86-a3-stop-on-bad-day.jsonl",
    "review-t86-a4a-inwindow-contradiction-normal-key.jsonl",
    "review-t86-a4b-inwindow-contradiction-injected-key.jsonl",
    "review-t86-a5-global-event-with-clean-window.jsonl",
    "review-t86-a6-systematic-27-bad-3-clean.jsonl",
]


def load_tool(tag: str, path: str):
    spec = importlib.util.spec_from_file_location(f"vr3_{tag}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def run_one(mod, book: str, days: int) -> dict:
    rows = mod.load(book)
    ok, summary = mod.report(rows, target_days=days)
    return {
        "rc": 0 if ok else 1,
        "verdict": summary.get("verdict"),
        "n_problems": len(summary.get("problems") or []),
        "n_history": len(summary.get("history_problems") or []),
        "problems": list(summary.get("problems") or []),
        "history": list(summary.get("history_problems") or []),
        "streak": summary.get("verified_streak_tail"),
    }


def main(argv: list[str]) -> int:
    books = argv or DEFAULT_BOOKS
    mods = [(tag, load_tool(tag.split("(")[0], p)) for tag, p in TOOLS]
    print(f"{'book':<52}{'tool':<18}{'rc':<4}{'verdict':<14}{'#prob':<7}{'#hist':<7}streak")
    for b in books:
        path = b if os.path.isabs(b) else os.path.join(ROOT, "scratch", b)
        for tag, mod in mods:
            r = run_one(mod, path, 3)
            print(f"{os.path.basename(b):<52}{tag:<18}{r['rc']:<4}{str(r['verdict']):<14}"
                  f"{r['n_problems']:<7}{r['n_history']:<7}{r['streak']}")
        print("")
    # a4a/a4b 细节：那条问题到底被留在 problems 还是被降级
    for name in ("review-t86-a4a-inwindow-contradiction-normal-key.jsonl",
                 "review-t86-a4b-inwindow-contradiction-injected-key.jsonl"):
        path = os.path.join(ROOT, "scratch", name)
        if not os.path.exists(path):
            continue
        print(f"=== {name} ===")
        for tag, mod in mods:
            r = run_one(mod, path, 3)
            print(f"[{tag}] rc={r['rc']} verdict={r['verdict']} problems={r['n_problems']} history={r['n_history']}")
            for p in r["problems"]:
                print(f"    PROBLEM: {p}")
            for p in r["history"]:
                print(f"    history: {p}")
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
