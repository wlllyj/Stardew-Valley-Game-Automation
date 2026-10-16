# -*- coding: utf-8 -*-
"""run9d 教训库 → run10 教训库 的原样拷贝（run A→run B 的唯一"记忆"通道）。

卡面口径（task-147 交付后第 2 条 / Lead m02099）：
  跑完 run9d 后把 `logs\\longrun-3day-llm-run9d-lessons.json` **原样**拷成
  `logs\\longrun-3day-llm-run10-lessons.json`，并记「拷贝时刻 + 两侧 SHA256」写进
  `docs\\_run10-evidence.md` §1。

用法：
  python scratch\\run9d-copy-lessons.py --dry-run     # 只看会不会做（默认，安全）
  python scratch\\run9d-copy-lessons.py               # 真的拷（目标已存在则拒绝，需 --force）
退出码：0=成功（或 dry-run 可做）/ 2=源不存在 / 3=目标已存在且未给 --force / 4=拷贝后 SHA256 不一致
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SRC_DEFAULT = "logs/longrun-3day-llm-run9d-lessons.json"
DST_DEFAULT = "logs/longrun-3day-llm-run10-lessons.json"


def sha256(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC_DEFAULT)
    ap.add_argument("--dst", default=DST_DEFAULT)
    ap.add_argument("--dry-run", action="store_true", help="只检查与打印，不写文件")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的目标")
    args = ap.parse_args()

    src = args.src if os.path.isabs(args.src) else os.path.join(ROOT, args.src)
    dst = args.dst if os.path.isabs(args.dst) else os.path.join(ROOT, args.dst)

    if not os.path.exists(src):
        print(f"[x] 源不存在：{src}", file=sys.stderr)
        print("    （run9d 还没跑完，或教训库路径不是这个名字）", file=sys.stderr)
        return 2
    src_sha = sha256(src)
    src_size = os.path.getsize(src)
    print(f"源  {src}\n    size={src_size} B  SHA256={src_sha}")

    if os.path.exists(dst) and not args.force:
        print(f"[x] 目标已存在，拒绝覆盖：{dst}", file=sys.stderr)
        print(f"    现有 SHA256={sha256(dst)}（要覆盖请显式 --force）", file=sys.stderr)
        return 3

    if args.dry_run:
        print(f"[dry-run] 将原样拷贝 → {dst}（未写盘）")
        print("         真实执行：去掉 --dry-run（目标已存在时再加 --force）")
        return 0

    shutil.copyfile(src, dst)
    dst_sha = sha256(dst)
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    print(f"目标 {dst}\n    size={os.path.getsize(dst)} B  SHA256={dst_sha}")
    ok = dst_sha == src_sha
    print(f"[{'OK' if ok else 'x'}] 两侧 SHA256 {'一致' if ok else '不一致'}")
    print("\n--- 供 docs\\_run10-evidence.md §1 直接粘贴 ---")
    print(f"- 教训库拷贝：`{SRC_DEFAULT}` → `{DST_DEFAULT}`（**原样字节拷贝**）")
    print(f"  - 拷贝时刻：`{now}`")
    print(f"  - 两侧 SHA256：`{src_sha}`（源 {src_size} B） / `{dst_sha}`（目标 {os.path.getsize(dst)} B）")
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
