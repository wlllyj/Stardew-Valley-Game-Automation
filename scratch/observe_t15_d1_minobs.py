# -*- coding: utf-8 -*-
"""T15-A 最小观测复算：ZONE_BLOCKER_KINDS 是否漏掉 ResourceClump。

只读探针：直接调用真实函数 fields.zones_from_observe / fields.zone_blockers_total。
不写生产代码、不碰游戏。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

import agentfarm.fields as F  # noqa: E402

# 最小观测：x/y 各 0..19 ⇒ split=2 切成 nw/ne/sw/se（每区 10×10）。
TILES = [
    {"tile": [5, 5],  "kind": "clump", "clumpKind": "stump",   "clumpIndex": 600, "toolOk": True},
    {"tile": [6, 5],  "kind": "weed"},
    {"tile": [15, 5], "kind": "stone"},
    {"tile": [15, 6], "kind": "clump", "clumpKind": "boulder", "clumpIndex": 672, "toolOk": False},
]
# tillable 只是为了让坐标包络覆盖 0..19（真实观测里 tillable 常与 tiles 并存）。
TILLABLE = [[x, y] for x in range(0, 20) for y in (0, 19)]

OBS = {
    "player": {"tile": [0, 0]},
    "location": {
        "isOutdoorFarm": True,
        "tilesTruncated": False,
        "tiles": TILES,
        "tillable": TILLABLE,
    },
}


def main() -> int:
    print("ZONE_BLOCKER_KINDS =", sorted(F.ZONE_BLOCKER_KINDS))
    print("BLOCKER_KINDS      =", sorted(F.BLOCKER_KINDS))
    print("'clump' in ZONE_BLOCKER_KINDS =", "clump" in F.ZONE_BLOCKER_KINDS)
    print("'stump' in ZONE_BLOCKER_KINDS =", "stump" in F.ZONE_BLOCKER_KINDS)
    print()

    zones = F.zones_from_observe(OBS, split=2)
    print("zones_from_observe ->")
    for z in zones:
        print(f"  {z.name:10s} bounds={z.bounds} blockers={z.blockers} tillable={z.tillable}")
    print()

    print("zone_blockers_total(zone, obs) ->")
    for z in zones:
        print(f"  {z.name:10s} -> {F.zone_blockers_total(z, OBS)}")
    print()

    # 反事实：若把 'clump' 并入口径，数值会变成多少（证明"漏计"的量级）。
    orig = F.ZONE_BLOCKER_KINDS
    patched = frozenset(orig | {"clump"})
    F.ZONE_BLOCKER_KINDS = patched
    try:
        print("反事实补 'clump' 后 ->")
        for z in F.zones_from_observe(OBS, split=2):
            print(f"  {z.name:10s} blockers={z.blockers} "
                  f"zone_blockers_total={F.zone_blockers_total(z, OBS)}")
    finally:
        F.ZONE_BLOCKER_KINDS = orig
    print()

    # tilesTruncated 必须 fail-closed。
    trunc = json.loads(json.dumps(OBS))
    trunc["location"]["tilesTruncated"] = True
    z2 = F.zones_from_observe(trunc, split=2)
    print("tilesTruncated=True 时 zone_blockers_total ->",
          [F.zone_blockers_total(z, trunc) for z in z2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
