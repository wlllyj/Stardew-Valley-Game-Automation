"""task-37: 把 logs/probe-bed-*-run1.log 清成 scratch/ 下的纯文本（去 ANSI、统一 UTF-8），只读原始日志。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
OUT = ROOT / "scratch"
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

NAMES = [
    "probe-bed-live2-run1.log",
    "probe-bed-sleep-run1.log",
    "probe-bed-close-run1.log",
    "probe-bed-recipe-run1.log",
    "probe-bed-live-run1.log",
]


def main() -> int:
    for name in NAMES:
        p = LOGS / name
        raw = p.read_bytes()
        for enc in ("utf-8-sig", "utf-16", "gbk", "latin-1"):
            try:
                text = raw.decode(enc)
                used = enc
                break
            except UnicodeDecodeError:
                continue
        text = ANSI.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
        dst = OUT / ("t37_" + name.replace(".log", ".txt"))
        dst.write_text(text, encoding="utf-8")
        print(f"{name}: enc={used} bytes={len(raw)} -> {dst.name} lines={text.count(chr(10)) + 1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
