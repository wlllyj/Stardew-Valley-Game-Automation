"""task-86：把两侧工具冻到 scratch/（可重生成，因此不入库大文件）。

- `scratch/_t86_tool_old.py` = `7c4ff68^` 的 `tools/verify-run3.py`
- `scratch/_t86_tool_new.py` = `7c4ff68`（= 现行 HEAD 的 `tools/verify-run3.py`）

用法：python scratch/_t86_freeze.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = [("7c4ff68^", "_t86_tool_old.py"), ("7c4ff68", "_t86_tool_new.py")]


def main() -> int:
    for rev, name in PAIRS:
        text = subprocess.run(["git", "-C", ROOT, "show", f"{rev}:tools/verify-run3.py"],
                              capture_output=True, text=True, encoding="utf-8", check=True).stdout
        out = os.path.join(ROOT, "scratch", name)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest().upper()
        print(f"{name}: rev={rev} lines={len(text.splitlines())} sha256={sha[:16]}… ({sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
