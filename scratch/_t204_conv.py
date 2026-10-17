r"""只读：把 Probe26 的 IL 转储（UTF-16LE，可能无 BOM）转成 UTF-8，便于用 read 工具看区间。

用法：
  python scratch\_t204_conv.py scratch\il-up-3.txt scratch\t204-il-up-3-u8.txt
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "utf-16-le"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("latin-1")


def main() -> int:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    text = load_bytes(src.read_bytes())
    dst.write_text(text, encoding="utf-8")
    print(f"{src} -> {dst} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
