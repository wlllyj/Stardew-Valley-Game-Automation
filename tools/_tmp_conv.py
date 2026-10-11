# -*- coding: utf-8 -*-
"""一次性：把 UTF-16 的 IL 转储转成 UTF-8，便于 grep/read。"""
import pathlib
import sys

src = pathlib.Path(sys.argv[1])
dst = pathlib.Path(sys.argv[2])
text = src.read_text(encoding="utf-16")
dst.write_text(text, encoding="utf-8")
print(f"{src} -> {dst} ({len(text)} chars)")
