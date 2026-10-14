# -*- coding: utf-8 -*-
"""task-72 取证：这些豁免闸门是哪一版 verify-run3.py 加进来的？

用法：python scratch\\_t72_when.py
只读 git 对象，不改任何文件。
"""
import subprocess
import sys

REVS = [
    "69513b8", "98fce88", "6b24118", "3bd7b9b", "727a767", "678c7ef",
    "2f088d9", "d290509", "13f5a16", "6b9ebfb", "fcf0116", "HEAD",
]
MARKERS = [
    "上界被放宽",
    "却没写任何坐标",
    "同一格同时进两套豁免",
    "被拒豁免扣了",
    "unreachable_within_bound",
    "refused_within_bound",
    "unreachable_exempt",
]


def show(rev: str) -> str:
    if rev == "HEAD":
        with open("tools/verify-run3.py", encoding="utf-8") as fh:
            return fh.read()
    p = subprocess.run(["git", "show", f"{rev}:tools/verify-run3.py"],
                       capture_output=True)
    if p.returncode != 0:
        return ""
    return p.stdout.decode("utf-8", "replace")


def main() -> int:
    base = None
    for rev in REVS:
        txt = show(rev)
        if not txt:
            print(f"{rev:9s} <读不到>")
            continue
        counts = [txt.count(m) for m in MARKERS]
        flags = "".join("Y" if c else "." for c in counts)
        print(f"{rev:9s} {len(txt.splitlines()):4d} 行  {flags}  "
              + "  ".join(f"{m}={c}" for m, c in zip(MARKERS, counts) if c))
        if base is None:
            base = flags
    print("\nflags 顺序 = " + " | ".join(MARKERS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
