"""Print the enclosing '--- Type.Method ---' header (and a few context lines)
for given 1-based line numbers in an IL dump.

usage: python scratch\\_which_method.py <file> <line> [<line> ...]
"""
import io
import sys


def main(argv):
    path = argv[1]
    targets = [int(x) for x in argv[2:]]
    lines = io.open(path, encoding="utf-8", errors="replace").read().splitlines()
    heads = [i for i, l in enumerate(lines) if l.startswith("--- ")]
    for t in targets:
        prior = [h for h in heads if h < t]
        idx = prior[-1] if prior else None
        print("target line %d: %s" % (t, lines[t - 1].strip()))
        print("  header(line %d): %s" % (
            (idx + 1) if idx is not None else -1,
            lines[idx].strip() if idx is not None else "<none>",
        ))
        start = max(0, t - 9)
        for i in range(start, t):
            print("    %d| %s" % (i + 1, lines[i]))
        print()


if __name__ == "__main__":
    main(sys.argv)
