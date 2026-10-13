# -*- coding: utf-8 -*-
"""UTF-8 安全地打印文件尾部/行数（避免 pwsh Get-Content 乱码）。

用法：python scratch\\tail.py --file logs\\run5-console.log --lines 20
"""
from __future__ import annotations

import argparse
import os


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--lines", type=int, default=20)
    args = ap.parse_args()
    if not os.path.exists(args.file):
        print(f"（文件不存在：{args.file}）")
        return 1
    st = os.stat(args.file)
    with open(args.file, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    import time
    print(f"== {args.file} 行数={len(lines)} size={st.st_size} mtime={time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}")
    for ln in lines[-args.lines:]:
        print("   ", ln)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
