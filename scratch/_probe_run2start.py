# -*- coding: utf-8 -*-
"""只读探针：看 run2 开局快照里各片田区的地形构成，用于判定 run2 clear_area
"做成 4/4" 的成功格是不是 grass。不改任何生产文件。"""
import collections
import json
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"logs\run2-observe-start.json"
with open(P, "r", encoding="utf-8") as f:
    d = json.load(f)

print("== top-level keys ==")
print(sorted(d.keys()))
print("clock:", d.get("clock"))
loc = d.get("location") or {}
print("location.name:", loc.get("name"), "isOutdoorFarm:", loc.get("isOutdoorFarm"))
pl = d.get("player") or {}
print("player:", pl.get("tile"), "stamina:", pl.get("stamina"), "money:", pl.get("money"))
print("crops:", d.get("crops"), "cropsRipe:", d.get("cropsRipe"))
print("counts:", d.get("counts"))
print("tilesTruncated:", d.get("tilesTruncated"), "len(tiles):", len(d.get("tiles") or []))

tiles = d.get("tiles") or []
tm = {}
for v in tiles:
    t = tuple(v.get("tile") or ())
    if len(t) == 2:
        tm[t] = v
print("kind histogram:", collections.Counter(v.get("kind") for v in tiles).most_common())

LAB = {"grass": "g", "weed": "w", "twig": "t", "stone": "s", "tree": "T",
       "dirt": "d", "None": ".", "": ".", None: "."}


def grid(cx, cy, r, label):
    print("--- around %s (%d,%d), r=%d ---" % (label, cx, cy, r))
    xs = range(cx - r, cx + r + 1)
    print("     " + " ".join("%2d" % x for x in xs))
    for y in range(cy - r, cy + r + 1):
        cells = []
        for x in xs:
            v = tm.get((x, y))
            cells.append("%2s" % ("·" if v is None else LAB.get(v.get("kind"), "?")))
        print("%3d  " % y + " ".join(cells))
    # 汇总该窗口内可动地形
    c = collections.Counter()
    for y in range(cy - r, cy + r + 1):
        for x in xs:
            v = tm.get((x, y))
            if v is None:
                c["<not-returned>"] += 1
            else:
                c[v.get("kind")] += 1
    print("   window kinds:", c.most_common())


for lb, cx, cy in [("field_ne/L3 anchor", 71, 17), ("plot L16", 61, 26),
                   ("grass-fail", 65, 26), ("plot L25", 59, 26),
                   ("plot L49", 53, 16), ("plot L53", 48, 8),
                   ("field_se", 59, 22), ("grass-fail", 51, 12)]:
    grid(cx, cy, 3, lb)

print("== 关键格详情 ==")
for k in [(65, 26), (65, 27), (51, 12), (71, 17)]:
    print(k, json.dumps(tm.get(k), ensure_ascii=False))
print("== inventory ==")
for i, it in enumerate(d.get("inventory") or []):
    if it.get("name") or it.get("itemId"):
        print(i, json.dumps(it, ensure_ascii=False))
