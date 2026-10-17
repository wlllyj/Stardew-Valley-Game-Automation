"""Lead 一次性只读探针：查农场上的机器/容器（特别是熔炉 114）+ 可采矿资源。

用途：判断「升级工具需要的 5 条铜锭」能否就近生产（有没有熔炉、有没有铜矿/煤）。
只读，不改世界。
"""
from __future__ import annotations

import json

from agentfarm.bridge import BridgeClient

MACHINE_IDS = {
    "114": "Furnace 熔炉",
    "12": "Charcoal Kiln",
    "13": "Furnace?",  # 仅为占位，实际以名字为准
    "15": "Preserves Jar",
    "16": "Cheese Press",
    "17": "Loom",
    "19": "Keg",
    "20": "Oil Maker",
    "21": "Cask",
    "105": "Tapper",
    "10": "Chest?",
    "130": "Chest",
    "232": "Chest",
}
ORE_IDS = {"378": "Copper Ore", "380": "Iron Ore", "382": "Coal", "334": "Copper Bar"}


def dump_objs(loc: dict, tag: str) -> None:
    objs = loc.get("objects") or []
    print(f"--- {tag} objects: {len(objs)} ---")
    named = {}
    for o in objs:
        qid = str(o.get("id") or o.get("itemId") or "")
        name = o.get("name")
        key = (qid, str(name))
        named[key] = named.get(key, 0) + 1
    for (qid, name), n in sorted(named.items(), key=lambda kv: -kv[1])[:40]:
        mark = ""
        if qid in MACHINE_IDS:
            mark = f"  <== {MACHINE_IDS[qid]}"
        if qid in ORE_IDS:
            mark = f"  <== {ORE_IDS[qid]}"
        print(f"  x{n:3d}  id={qid:6s} name={name!r}{mark}")


def main() -> int:
    c = BridgeClient()
    o = c.observe("full")
    loc = o.get("location") or {}
    farm = o.get("farm") or {}
    print("loc", loc.get("name"), "isOutdoorFarm", loc.get("isOutdoorFarm"))
    dump_objs(loc, str(loc.get("name")))
    print(
        "--- farm 计数 ---",
        {k: farm.get(k) for k in ("crops", "readyCrops", "dryCrops", "deadCrops", "hoeDirt", "emptyDirt", "complete")},
    )
    tiles = loc.get("tiles") or []
    kinds = {}
    for t in tiles:
        kinds[(t.get("kind"), t.get("feature"))] = kinds.get((t.get("kind"), t.get("feature")), 0) + 1
    print("--- 窗口 tiles 前 12 类 ---")
    for k, n in sorted(kinds.items(), key=lambda kv: -kv[1])[:12]:
        print("  ", k, "x", n)
    # 顺手看看 bridges/locations 图里有没有矿山/铁匠铺
    bridges = o.get("bridges") or []
    names = []
    for b in bridges:
        for side in ("from", "to"):
            nm = b.get(side) or (b.get(side + "Loc") if isinstance(b, dict) else None)
            if nm:
                names.append(nm)
    for want in ("Mine", "Blacksmith", "Mountain", "Town", "Forest"):
        hits = [n for n in set(names) if want.lower() in str(n).lower()]
        print(f"  graph 含 {want}: {hits[:5]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
