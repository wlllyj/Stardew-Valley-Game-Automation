# -*- coding: utf-8 -*-
"""彩排前后状态读数（**只读**：不发起任何 exec、不改游戏状态）。

用途：run-longrun 起跑前 / 结束后各跑一次，作为"外部证据"对照——
journal 是 longrun 自己写的（同源），存档 mtime/size 与这里的世界读数才是独立证据。

用法：
    python scratch\rehearsal_state.py            # 人类可读
    python scratch\rehearsal_state.py --json     # 单行 JSON（便于事后 diff）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402

SAVE = pathlib.Path.home() / "AppData" / "Roaming" / "StardewValley" / "Saves" / "Wahaha_450799035"


def save_stat() -> dict:
    out = {}
    for name in ("Wahaha_450799035", "SaveGameInfo"):
        p = SAVE / name
        st = p.stat() if p.exists() else None
        out[name] = None if st is None else {"size": st.st_size, "mtime": st.st_mtime}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    client = BridgeClient()
    health = client.health()
    obs = client.observe("full")

    player = obs.get("player") or {}
    loc = obs.get("location") or {}
    clock = obs.get("clock") or {}
    farm = obs.get("farm") or {}
    ui = obs.get("ui") or {}
    tiles = loc.get("tiles") or []

    kinds: dict[str, int] = {}
    for t in tiles:
        k = str(t.get("kind"))
        kinds[k] = kinds.get(k, 0) + 1

    seeds = [
        {"id": i.get("id"), "name": i.get("name"), "stack": i.get("stack")}
        for i in (player.get("inventory") or [])
        if "seed" in str(i.get("name", "")).lower() or "种子" in str(i.get("name", ""))
    ]

    out = {
        "generatedAt": obs.get("generatedAt"),
        "modVersion": health.get("modVersion"),
        "hasSaveLoaded": obs.get("hasSaveLoaded"),
        "worldSeq": obs.get("worldSeq"),
        "day": [clock.get("year"), clock.get("season"), clock.get("day")],
        "timeOfDay": clock.get("timeOfDay"),
        "weather": clock.get("weather"),
        "location": loc.get("name"),
        "isOutdoorFarm": loc.get("isOutdoorFarm"),
        "playerTile": player.get("tile"),
        "isInBed": player.get("isInBed"),
        "stamina": [player.get("stamina"), player.get("maxStamina")],
        "money": player.get("money"),
        "farmingLevel": player.get("farmingLevel"),
        "waterLeft": (player.get("wateringCan") or {}).get("waterLeft"),
        "ui": {
            "activeMenu": ui.get("activeMenu"),
            "isModal": ui.get("isModal"),
            "dialogueIsQuestion": ui.get("dialogueIsQuestion"),
            "professionsToChoose": ui.get("professionsToChoose"),
        },
        "farm": {k: farm.get(k) for k in
                 ("complete", "crops", "dryCrops", "unwateredCrops", "weeds", "stones",
                  "twigs", "grass", "trees", "ripeCrops", "emptyDirt")},
        "window": {"tiles": len(tiles), "tillable": len(loc.get("tillable") or []),
                   "tilesTruncated": loc.get("tilesTruncated"), "kinds": kinds},
        "seeds": seeds,
        "save": save_stat(),
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
