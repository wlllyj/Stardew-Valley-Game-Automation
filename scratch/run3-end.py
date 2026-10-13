# -*- coding: utf-8 -*-
"""run3 跑完后的终态观测（**只读**）。落盘 logs\\run3-observe-end.json，用于与 run3-observe-start.json 做差分。

不 quit、不 load、不写世界。
"""
from __future__ import annotations

import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "brain"))

from agentfarm.bridge import BridgeClient, BridgeError, load_bridge_info, pid_alive  # noqa: E402

BRIDGE = os.path.join(os.environ["APPDATA"], "StardewValley", "AgentFarm", "bridge.json")
OUT = os.path.join(REPO, "logs", "run3-observe-end.json")


def dig(obj, *path, default=None):
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


with open(BRIDGE, "r", encoding="utf-8") as fh:
    raw = json.load(fh)
info = load_bridge_info()
print(f"raw pid={raw.get('pid')!r}  load_bridge_info().pid={getattr(info, 'pid', None)!r}  pid_alive={pid_alive(raw.get('pid'))}")

c = BridgeClient(timeout=15.0)
h = c.health(timeout=10.0)
obs = c.observe("full", timeout=25.0)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(obs, fh, ensure_ascii=False, indent=1)
print(f"已落盘：{OUT} ({os.path.getsize(OUT)} bytes)")

clock = obs.get("clock") or {}
player = obs.get("player") or {}
farm = obs.get("farm") or {}
loc = obs.get("location") or {}
ui = obs.get("ui") or {}
live = obs.get("liveness") or {}
print(f"worldSeq={obs.get('worldSeq')} generatedAt={obs.get('generatedAt')} modVersion={h.get('modVersion')} hasSaveLoaded={obs.get('hasSaveLoaded')}")
print(f"clock={clock.get('year')}/{clock.get('season')}/{clock.get('day')} tod={clock.get('timeOfDay')} weather={clock.get('weather')}")
print(f"location={loc.get('name')} isOutdoorFarm={loc.get('isOutdoorFarm')}")
print(f"player={player.get('name')} tile={player.get('tile')} stamina={player.get('stamina')}/{player.get('maxStamina')} money={player.get('money')} farmingLevel={player.get('farmingLevel')} isInBed={player.get('isInBed')}")
print(f"wateringCan={player.get('wateringCan')}")
print(f"farm: crops={farm.get('crops')} unwatered={farm.get('unwateredCrops')} dry={farm.get('dryCrops')} ripe={farm.get('ripeCrops')} hoeDirt={farm.get('hoeDirt')} emptyDirt={farm.get('emptyDirt')} complete={farm.get('complete')} scanSeq={farm.get('scanSeq')}")
print(f"ui: activeMenu={ui.get('activeMenu')!r} isModal={ui.get('isModal')} onScreenMenus={ui.get('onScreenMenus')}")
print(f"liveness: worldAdvancing={live.get('worldAdvancing')} secondsSinceClockMoved={live.get('secondsSinceClockMoved')}")
print(f"game: paused={dig(obs,'game','paused')} shouldTimePass={dig(obs,'game','shouldTimePass')}")
