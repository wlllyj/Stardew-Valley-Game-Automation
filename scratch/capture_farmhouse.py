"""一次性只读探针（Lead 2026-10-13）：把玩家读档回床上，抓一份 FarmHouse 的完整观测。

用途：给 task-31/task-33（睡觉链路）与 task-32 提供权威的 `location.furniture[]` /
`location.tiles[]` / `location.doors[]` / `ui` 现场，确认"真正的床格是哪一格、
它的 bbox 与可站立邻格"。只读：不发起任何技能（除了 load_save 回到存档点）。
输出：scratch/obs-farmhouse-spring11.json
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402


def main() -> int:
    c = BridgeClient(timeout=10.0)
    print("health:", json.dumps(c.health(), ensure_ascii=False))
    print("load_save (force=True：本次读档只为回到床上抓现场，本日没有可丢的进度) ...")
    c.load_save(force=True)
    obs = c.observe("full")
    loc = obs.get("location") or {}
    player = obs.get("player") or {}
    out = {
        "generatedAt": obs.get("generatedAt"),
        "worldSeq": obs.get("worldSeq"),
        "clock": obs.get("clock"),
        "player": {k: player.get(k) for k in ("name", "location", "tile", "facing", "stamina", "money", "isInBed")},
        "ui": obs.get("ui"),
        "location": {
            "name": loc.get("name"),
            "isOutdoorFarm": loc.get("isOutdoorFarm"),
            "tileCount": len(loc.get("tiles") or []),
            "tiles": loc.get("tiles"),
            "furniture": loc.get("furniture"),
            "doors": loc.get("doors"),
        },
    }
    path = ROOT / "scratch" / "obs-farmhouse-spring11.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", path)
    print("location:", out["location"]["name"], "isOutdoorFarm:", out["location"]["isOutdoorFarm"],
          "tileCount:", out["location"]["tileCount"])
    print("player:", json.dumps(out["player"], ensure_ascii=False))
    print("ui:", json.dumps(out["ui"], ensure_ascii=False))
    print("doors:", json.dumps(out["location"]["doors"], ensure_ascii=False))
    for f in out["location"]["furniture"] or []:
        print("furniture:", json.dumps(f, ensure_ascii=False))
    beds = [f for f in (out["location"]["furniture"] or []) if f.get("isBed")]
    print("bed-tiles:", json.dumps([f.get("tile") for f in beds], ensure_ascii=False))
    print("tiles:", json.dumps(out["location"]["tiles"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
