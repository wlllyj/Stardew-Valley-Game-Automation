"""task-90：三副本冻结（old = 洞口之前 / buggy = 带洞 / fixed = c6d2a7a）。

用法：python scratch/_t90_freeze.py
产物（scratch/ 下，可随时重生成；不入库大文件）：
  _t90_tool_old.py   = 7c4ff68^  的 tools/verify-run3.py（口径变更之前）
  _t90_tool_buggy.py = 7c4ff68   的 tools/verify-run3.py（尾部窗口口径，带标签注入洞）
  _t90_tool_fixed.py = c6d2a7a   的 tools/verify-run3.py（修好：净化 + 最长前缀 + 未知标签 fatal）
"""
from __future__ import annotations

import hashlib
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = [
    ("7c4ff68^", "_t90_tool_old.py"),
    ("7c4ff68", "_t90_tool_buggy.py"),
    ("c6d2a7a", "_t90_tool_fixed.py"),
]


def main() -> int:
    for rev, name in PAIRS:
        text = subprocess.run(["git", "-C", ROOT, "show", f"{rev}:tools/verify-run3.py"],
                              capture_output=True, text=True, encoding="utf-8", check=True).stdout
        out = os.path.join(ROOT, "scratch", name)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        print(f"{name}: rev={rev} lines={len(text.splitlines())} sha256={sha.upper()[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
