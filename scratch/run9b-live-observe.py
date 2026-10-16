# -*- coding: utf-8 -*-
"""run9b 收尾现场只读观测 → scratch/run9b-live-observe.json

只调 observe(detail=full)，不下发任何技能；打印六项重点字段。
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402

OUT = os.path.join(ROOT, "scratch", "run9b-live-observe.json")

client = BridgeClient()
health = client.health()
obs = client.observe("full")

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump({"health": health, "observe": obs}, fh, ensure_ascii=False, indent=1)

ui = obs.get("ui") or {}
player = obs.get("player") or {}
farm = obs.get("farm") or {}
clock = obs.get("clock") or {}
loc = obs.get("location") or {}
life = obs.get("liveness") or {}
game = obs.get("game") or {}

print(f"落盘 → {OUT}（{os.path.getsize(OUT)} B）")
print(f"health: modVersion={health.get('modVersion')} port={health.get('port')} runtime={json.dumps(health.get('runtime'), ensure_ascii=False)}")
print(f"clock: {json.dumps(clock, ensure_ascii=False)}")
print(f"ui: activeMenu={ui.get('activeMenu')!r} isModal={ui.get('isModal')} eventUp={ui.get('eventUp')} "
      f"dialogueIsQuestion={ui.get('dialogueIsQuestion')} onScreenMenus={ui.get('onScreenMenus')} "
      f"activeMenuText={ui.get('activeMenuText')!r} professionsToChoose={ui.get('professionsToChoose')}")
print(f"game: {json.dumps(game, ensure_ascii=False)}")
print(f"liveness: {json.dumps(life, ensure_ascii=False)}")
print(f"player: name={player.get('name')} loc={player.get('location')} tile={player.get('tile')} "
      f"stamina={player.get('stamina')}/{player.get('maxStamina')} money={player.get('money')} "
      f"isInBed={player.get('isInBed')} canMove={player.get('canMove')} farmingLevel={player.get('farmingLevel')} "
      f"waterLeft={(player.get('wateringCan') or {}).get('waterLeft')}")
inv = player.get("inventory") or []
print(f"inventory({len(inv)}): {json.dumps(inv, ensure_ascii=False)[:600]}")
print(f"farm: crops={farm.get('crops')} ripe={farm.get('ripeCrops')} dryCrops={farm.get('dryCrops')} "
      f"deadCrops={farm.get('deadCrops')} dryDeadCrops={farm.get('dryDeadCrops')} unwatered={farm.get('unwateredCrops')} "
      f"hoeDirt={farm.get('hoeDirt')} complete={farm.get('complete')} scanSeq={farm.get('scanSeq')}")
print(f"location: name={loc.get('name')} isOutdoorFarm={loc.get('isOutdoorFarm')} "
      f"objects={len(loc.get('objects') or [])} tiles={len(loc.get('tiles') or [])} tilesTruncated={loc.get('tilesTruncated')}")
