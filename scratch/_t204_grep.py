r"""只读：在 IL 转储（可能是 UTF-16LE）里按正则找行，打印 `文件:行号: 内容`。

用法：
  python scratch\_t204_grep.py scratch\il-up-2.txt "getPlayerCurrencyAmount|moneyShakeTimer"
  python scratch\_t204_grep.py scratch\il-up-3.txt "actionWhenPurchased" -n 5
"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    path = args[0]
    pattern = args[1]
    ctx = 0
    if "-n" in sys.argv:
        ctx = int(sys.argv[sys.argv.index("-n") + 1])
    text = load(path)
    lines = text.splitlines()
    rx = re.compile(pattern)
    hits = 0
    for i, line in enumerate(lines, 1):
        if rx.search(line):
            hits += 1
            lo = max(1, i - ctx)
            hi = min(len(lines), i + ctx)
            for j in range(lo, hi + 1):
                mark = ">>" if j == i else "  "
                print(f"{mark} {path}:{j}: {lines[j - 1].strip()}")
            if ctx:
                print("   " + "-" * 60)
    print(f"[{path}] 命中 {hits} 行 / 共 {len(lines)} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
