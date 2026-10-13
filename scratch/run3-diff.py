# -*- coding: utf-8 -*-
"""run3 起跑前 vs 跑完后的观测差分（只读两个落盘 JSON）。"""
from __future__ import annotations

import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
A = os.path.join(REPO, "logs", "run3-observe-start.json")
B = os.path.join(REPO, "logs", "run3-observe-end.json")

with open(A, encoding="utf-8") as fh:
    a = json.load(fh)
with open(B, encoding="utf-8") as fh:
    b = json.load(fh)


def dig(o, *path, default=None):
    cur = o
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


rows = [
    ("generatedAt", a.get("generatedAt"), b.get("generatedAt")),
    ("worldSeq", a.get("worldSeq"), b.get("worldSeq")),
    ("clock", dig(a, "clock"), dig(b, "clock")),
    ("location.name", dig(a, "location", "name"), dig(b, "location", "name")),
    ("location.isOutdoorFarm", dig(a, "location", "isOutdoorFarm"), dig(b, "location", "isOutdoorFarm")),
    ("player.tile", dig(a, "player", "tile"), dig(b, "player", "tile")),
    ("player.isInBed", dig(a, "player", "isInBed"), dig(b, "player", "isInBed")),
    ("player.stamina", dig(a, "player", "stamina"), dig(b, "player", "stamina")),
    ("player.money", dig(a, "player", "money"), dig(b, "player", "money")),
    ("player.farmingLevel", dig(a, "player", "farmingLevel"), dig(b, "player", "farmingLevel")),
    ("player.wateringCan", dig(a, "player", "wateringCan"), dig(b, "player", "wateringCan")),
    ("player.inventoryCount", dig(a, "player", "inventoryCount"), dig(b, "player", "inventoryCount")),
    ("farm.crops", dig(a, "farm", "crops"), dig(b, "farm", "crops")),
    ("farm.unwateredCrops", dig(a, "farm", "unwateredCrops"), dig(b, "farm", "unwateredCrops")),
    ("farm.dryCrops", dig(a, "farm", "dryCrops"), dig(b, "farm", "dryCrops")),
    ("farm.ripeCrops", dig(a, "farm", "ripeCrops"), dig(b, "farm", "ripeCrops")),
    ("farm.hoeDirt", dig(a, "farm", "hoeDirt"), dig(b, "farm", "hoeDirt")),
    ("farm.emptyDirt", dig(a, "farm", "emptyDirt"), dig(b, "farm", "emptyDirt")),
    ("farm.weeds", dig(a, "farm", "weeds"), dig(b, "farm", "weeds")),
    ("farm.stones", dig(a, "farm", "stones"), dig(b, "farm", "stones")),
    ("farm.twigs", dig(a, "farm", "twigs"), dig(b, "farm", "twigs")),
    ("farm.trees", dig(a, "farm", "trees"), dig(b, "farm", "trees")),
    ("farm.grass", dig(a, "farm", "grass"), dig(b, "farm", "grass")),
    ("farm.complete", dig(a, "farm", "complete"), dig(b, "farm", "complete")),
    ("ui.isModal", dig(a, "ui", "isModal"), dig(b, "ui", "isModal")),
    ("liveness.worldAdvancing", dig(a, "liveness", "worldAdvancing"), dig(b, "liveness", "worldAdvancing")),
]

print(f"{'字段':<26} {'起跑前(19:04:25)':<52} {'跑完后(19:11:06)'}")
print("-" * 130)
for name, va, vb in rows:
    sa = json.dumps(va, ensure_ascii=False) if isinstance(va, (dict, list)) else str(va)
    sb = json.dumps(vb, ensure_ascii=False) if isinstance(vb, (dict, list)) else str(vb)
    mark = "  <== 变化" if sa != sb else ""
    print(f"{name:<26} {sa:<52} {sb}{mark}")

inv_a = [f"{i.get('name')}x{i.get('stack')}" for i in (dig(a, "player", "inventory") or [])]
inv_b = [f"{i.get('name')}x{i.get('stack')}" for i in (dig(b, "player", "inventory") or [])]
print(f"\n起跑前背包：{inv_a}")
print(f"跑完后背包：{inv_b}")
