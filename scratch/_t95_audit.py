"""task-95 只读审计：枚举 brain 的 journal 事件名 vs 分析器 EVENT_BUCKETS，
并拉平 task-84（死苗/放弃格）相关字段与事件形状。

用法: python scratch/_t95_audit.py scratch/_t95_audit.txt
输出 UTF-8（不经 pwsh 重定向，避免 UTF-16LE）。
"""
import io
import re
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAIN = [
    os.path.join(ROOT, "brain", "agentfarm", "longrun.py"),
    os.path.join(ROOT, "brain", "agentfarm", "farmwork.py"),
]
TOOL = os.path.join(ROOT, "tools", "analyze-longrun.py")
PAT = re.compile(r'_journal\(\s*"([a-z0-9_]+)"')


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def main():
    out = io.StringIO()
    w = out.write

    names = {}
    for p in BRAIN:
        src = read(p)
        for m in PAT.finditer(src):
            ln = src.count("\n", 0, m.start()) + 1
            names.setdefault(m.group(1), []).append((os.path.basename(p), ln))
    w("=== brain journal 事件名（%d 个）===\n" % len(names))
    for n in sorted(names):
        locs = ", ".join("%s:%d" % t for t in names[n])
        w("  %-28s %s\n" % (n, locs))

    tool_src = read(TOOL)
    # EVENT_BUCKETS 区间
    m = re.search(r"EVENT_BUCKETS\s*=\s*\{(.*?)\n\}", tool_src, re.S)
    buckets = dict(re.findall(r'"([a-z0-9_]+)"\s*:\s*"([a-z0-9_]+)"', m.group(1))) if m else {}
    m2 = re.search(r"NEW_EVENT_BUCKETS\s*=\s*\((.*?)\)", tool_src, re.S)
    new_b = re.findall(r'"([a-z0-9_]+)"', m2.group(1)) if m2 else []
    struct = re.search(r"STRUCTURAL_EVENTS\s*=\s*\((.*?)\)", tool_src, re.S)
    structural = re.findall(r'"([a-z0-9_]+)"', struct.group(1)) if struct else []

    missing = [n for n in sorted(names) if n not in buckets and n not in structural]
    w("\n=== 桶（EVENT_BUCKETS）%d 个 ===\n" % len(buckets))
    w("  " + ", ".join(sorted(buckets)) + "\n")
    w("\n=== 结构性白名单 STRUCTURAL_EVENTS ===\n  %s\n" % ", ".join(structural))
    w("\n=== 未映射（%d 个）===\n" % len(missing))
    for n in missing:
        w("  %-28s %s\n" % (n, ", ".join("%s:%d" % t for t in names[n])))
    w("\n=== NEW_EVENT_BUCKETS 里不在桶值中的（脏条目）===\n")
    vals = set(buckets.values())
    w("  " + ", ".join(sorted(b for b in new_b if b not in vals)) + "\n")

    w("\n=== task-84 相关行（brain 侧）===\n")
    keys = ("dead_crops_summary", "dead_crops", "dry_dead", "dryDead", "gave_up", "given_up")
    for p in BRAIN + [TOOL]:
        src = read(p)
        lines = src.split("\n")
        hits = [(i + 1, l) for i, l in enumerate(lines) if any(k in l for k in keys)]
        if hits:
            w("\n-- %s (%d hits) --\n" % (os.path.relpath(p, ROOT), len(hits)))
            for ln, l in hits:
                w("  %5d: %s\n" % (ln, l.strip()[:220]))

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(out.getvalue())
        print("wrote", sys.argv[1], len(out.getvalue()), "chars")
    else:
        print(out.getvalue())


if __name__ == "__main__":
    main()
