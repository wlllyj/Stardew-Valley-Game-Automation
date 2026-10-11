# -*- coding: utf-8 -*-
"""只读地图探针：把 obs-full.json 当静态地形图，验证 run1/run2 journal 里的
田区锚点与"可锄/待清理"计数，并看 clear_area 成功格/失败格的 kind。
不改任何生产文件。"""
import collections
import json
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"scratch\obs-full.json"
with open(P, "r", encoding="utf-8") as f:
    d = json.load(f)

print("clock:", d.get("clock"))
loc = d.get("location") or {}
print("location.name:", loc.get("name"), "isOutdoorFarm:", loc.get("isOutdoorFarm"),
      "tilesTruncated:", loc.get("tilesTruncated"))
pl = d.get("player") or {}
print("player:", pl.get("tile"), "stamina:", pl.get("stamina"))
tiles = loc.get("tiles") or []
tm = {}
for v in tiles:
    t = tuple(v.get("tile") or ())
    if len(t) == 2:
        tm[t] = v
till = {tuple(t) for t in (loc.get("tillable") or [])}
xs = [t[0] for t in tm]
ys = [t[1] for t in tm]
print("len(tiles)=%d  x:[%d..%d]  y:[%d..%d]  len(tillable)=%d"
      % (len(tm), min(xs), max(xs), min(ys), max(ys), len(till)))
print("kind histogram:", collections.Counter(v.get("kind") for v in tm.values()).most_common())
print("tillable: grass-overlap =",
      sum(1 for t in till if (tm.get(t) or {}).get("kind") == "grass"))

ACTION = ("weed", "twig", "stone", "grass")


def rect(label, x0, x1, y0, y1):
    cells = [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    got = [c for c in cells if c in tm]
    miss = [c for c in cells if c not in tm]
    kinds = collections.Counter((tm.get(c) or {}).get("kind") for c in got)
    clear = [c for c in got if (tm.get(c) or {}).get("kind") in ACTION]
    tillable = [c for c in got if c in till]
    print("%-26s %d 格: 返回 %d 缺 %d | 可锄(在 tillable[]) %d 待清理 %d | kinds %s"
          % (label, len(cells), len(got), len(miss), len(tillable), len(clear),
             kinds.most_common()))
    if clear:
        print("     待清理格:", [(c, (tm.get(c) or {}).get("kind")) for c in sorted(clear)])
    return clear, tillable


print("\n== run1 plot zone=field_ne anchor=[56,17] tiles=25 可锄17/待清理3 ==")
rect("anchor=左上角 56..60 x 17..21", 56, 60, 17, 21)
rect("anchor=中心   54..58 x 15..19", 54, 58, 15, 19)
rect("anchor=左下角 56..60 x 13..17", 56, 60, 13, 17)

print("\n== run2 plot zone=field_ne anchor=[71,17] tiles=25 可锄16/待清理5 ==")
rect("anchor=左上角 71..75 x 17..21", 71, 75, 17, 21)
rect("anchor=中心   69..73 x 15..19", 69, 73, 15, 19)
rect("anchor=左下角 71..75 x 13..17", 71, 75, 13, 17)

print("\n== run2 其它锚点（journal plot 事件）==")
for lb, cx, cy in [("[61,26]", 61, 26), ("[59,26]", 59, 26), ("[53,16]", 53, 16),
                   ("[48,8]", 48, 8), ("[59,22]", 59, 22)]:
    rect("anchor=左上角 " + lb, cx, cx + 4, cy, cy + 4)

print("\n== 关键格 ==")
for k in [(58, 21), (56, 21), (65, 26), (65, 27), (51, 12), (71, 17), (64, 15)]:
    v = tm.get(k)
    if v is None:
        print(k, "<不在 tiles[] 里>", "inTillable=", k in till)
    else:
        print(k, "kind=%s feature=%s tool=%s standable=%s actionable=%s inTillable=%s"
              % (v.get("kind"), v.get("feature"), v.get("tool"), v.get("standable"),
                 v.get("actionable"), k in till))
