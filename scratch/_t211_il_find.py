r"""只读：在 il-probe 的 IL 转储里按「方法头切片」+ 正则只打匹配行。

用法：
  python scratch\_t211_il_find.py <dump.txt> <正则> [方法头子串]

方法头 = 以 '--- ' 开头的行；给了第 3 个参数时只在该方法头含该子串的方法内匹配。
"""
import re
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    path, pattern = sys.argv[1], sys.argv[2]
    only = sys.argv[3] if len(sys.argv) > 3 else None
    pat = re.compile(pattern)
    cur = ""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if line.startswith("--- "):
                cur = line.rstrip()
            if only and only not in cur:
                continue
            if pat.search(line):
                print("%d: %s" % (i, line.rstrip()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
