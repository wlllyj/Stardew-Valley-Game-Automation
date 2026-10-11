# -*- coding: utf-8 -*-
"""只读分析：把 obs-full.json 里两个"清不掉"的 grass 格及周边口径打出来。"""
import json
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else r"scratch\obs-full.json")
obs = json.loads(p.read_text(encoding="utf-8"))

print("top keys:", sorted(obs.keys()))
clock = obs.get("clock") or {}
print("clock:", json.dumps(clock, ensure_ascii=False))
loc = obs.get("location") or {}
print("location.name:", loc.get("name"), "isOutdoorFarm:", loc.get("isOutdoorFarm"))
print("tilesTruncated:", loc.get("tilesTruncated"))
print("location keys:", sorted(loc.keys()))
tiles = loc.get("tiles") or []
print("tiles count:", len(tiles))
if tiles:
    print("tile sample[0]:", json.dumps(tiles[0], ensure_ascii=False))

player = obs.get("player") or {}
print("player.tile:", player.get("tile"), "stamina:", player.get("stamina"),
      "money:", player.get("money"), "isInBed:", player.get("isInBed"))
print("player keys:", sorted(player.keys()))
inv = player.get("inventory") or player.get("items")
print("inventory:", json.dumps(inv, ensure_ascii=False)[:2000])
print("wateringCan:", json.dumps(player.get("wateringCan"), ensure_ascii=False))


def show(tx, ty):
    for v in tiles:
        t = v.get("tile") or []
        if len(t) == 2 and t[0] == tx and t[1] == ty:
            print("TILE", (tx, ty), json.dumps(v, ensure_ascii=False))
            return
    print("TILE", (tx, ty), "NOT RETURNED (truncated)")


for tx, ty in [(58, 21), (56, 21)]:
    show(tx, ty)

# 周边 7x7，看 grass/weed/twig 的分布与 feature 字段
print("--- neighbourhood 53..61 x 18..24 ---")
for ty in range(18, 25):
    row = []
    for tx in range(53, 62):
        hit = None
        for v in tiles:
            t = v.get("tile") or []
            if len(t) == 2 and t[0] == tx and t[1] == ty:
                hit = v
                break
        if hit is None:
            row.append(f"{tx},{ty}:--")
        else:
            row.append("%d,%d:%s/%s" % (tx, ty, hit.get("kind"), hit.get("feature")))
    print(" | ".join(row))

# kind 直方图 + feature 直方图
import collections
kc = collections.Counter(str(v.get("kind")) for v in tiles)
fc = collections.Counter(str(v.get("feature")) for v in tiles)
print("kind histogram:", kc.most_common())
print("feature histogram:", fc.most_common())
print("grass tiles:", [v for v in tiles if v.get("kind") == "grass"])
