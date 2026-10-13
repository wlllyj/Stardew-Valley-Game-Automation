"""对比两份 analyze 文本输出：建议条数 / 浇水建议计数 / 是否出现新红条（只读）。"""
import os
import re

PAIRS = [
    ("run5 BEFORE", "scratch/_run5_analyze.txt", "scratch/_run5_analyze_after2.txt"),
    ("run2 BEFORE", "scratch/_run2_analyze4.txt", "scratch/_run2_analyze_after2.txt"),
]


def load(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def advice(t):
    return [l.strip() for l in t.splitlines() if re.match(r"^  \d+\. ", l)]


def counts(t):
    out = {}
    for key in ("VERIFIED",):
        m = re.search(key + r"[^\n]*", t)
        out[key] = m.group(0) if m else None
    return out


for tag, pb, pa in PAIRS:
    if not (os.path.exists(pb) and os.path.exists(pa)):
        print(f"== {tag}: MISSING FILE {pb if not os.path.exists(pb) else pa}")
        continue
    tb, ta = load(pb), load(pa)
    ab, aa = advice(tb), advice(ta)
    print(f"== {tag}: chars {len(tb)} -> {len(ta)}; advice {len(ab)} -> {len(aa)}")
    for l in aa[:4]:
        print("   A:", l[:130])
    for name, txt in (("before", tb), ("after2", ta)):
        m = re.search(r"浇水证据有问题 ×(\d+)[^\n]*", txt)
        n = re.search(r"没活却还有干地 ×(\d+)[^\n]*", txt)
        print(f"   {name}: water={m.group(1) if m else '-'} nowork_dry={n.group(1) if n else '-'}")
        mv = re.search(r"VERIFIED[^\n]*", txt)
        print(f"   {name}: {mv.group(0)[:80] if mv else 'VERIFIED?'}")
