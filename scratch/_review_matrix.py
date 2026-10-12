# -*- coding: utf-8 -*-
"""deputy-lead 的账本矩阵复跑器（只读 tools/verify-run3.py，不改它）。

用法（必须带 UTF-8，否则中文路径打印会炸）：
    $env:PYTHONUTF8="1"; <py> scratch\\_review_matrix.py            # 一行一本
    $env:PYTHONUTF8="1"; <py> scratch\\_review_matrix.py --verbose  # 追加逐条 problems/infos
"""
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "verify-run3.py")

# 期望读数（Lead 的裁定：绿账本必须 exit 0，负例必须 exit 1）
EXPECT0 = {
    "scratch/journal-green.jsonl",
    "scratch/review-neg-G-env-info-item.jsonl",
    "scratch/review-neg-I-env-explained.jsonl",
    "scratch/review-neg-K-forged-consistent.jsonl",
    "scratch/review-neg-K2-forged-empty.jsonl",
    "scratch/review-neg-P-t15-last-round-done.jsonl",
}


def books():
    out = []
    for pat in ("scratch/*.jsonl", "logs/*.jsonl"):
        out += glob.glob(os.path.join(ROOT, pat))
    return sorted(out)


def main():
    verbose = "--verbose" in sys.argv
    mismatch = 0
    for p in books():
        r = subprocess.run(
            [sys.executable, TOOL, "--journal", p, "--json", "--days", "3"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        try:
            s = json.loads(r.stdout)
        except Exception:  # noqa: BLE001
            print(f"{rel:<52} PARSE-FAIL exit={r.returncode} out={r.stdout[:100]!r} err={r.stderr[:200]!r}")
            mismatch += 1
            continue
        want0 = rel in EXPECT0
        ok_expect = (r.returncode == 0) == want0
        if not ok_expect:
            mismatch += 1
        tag = "  <== 读数变了" if not ok_expect else ""
        print(f"{rel:<52} exit={r.returncode} {s['verdict']:<13} problems={len(s['problems']):<3} infos={len(s['infos'])}{tag}")
        if verbose:
            for x in s["problems"]:
                print(f"      P: {x}")
            for x in s["infos"]:
                print(f"      i: {x}")
    print(f"\n不符期望的账本数 = {mismatch}（期望 exit0 集合：{sorted(os.path.basename(x) for x in EXPECT0)}）")
    return 1 if mismatch else 0


if __name__ == "__main__":
    raise SystemExit(main())
