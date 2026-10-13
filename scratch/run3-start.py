# -*- coding: utf-8 -*-
"""run3 起跑前快照（**只读**，不改世界、不 load、不 quit）。

1) pid 双向取证：原始 bridge.json 的 `pid` 键 + `load_bridge_info()` 读出的 pid（钉死 task-13 的大小写容错）。
2) observe("full") 落盘 logs\\run3-observe-start.json（跑完后做观测差分的起点）。
3) 打印紧凑摘要 + 四处硬判据（hasSaveLoaded / isOutdoorFarm / isModal / modVersion）。
"""
from __future__ import annotations

import json
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "brain"))

from agentfarm.bridge import BridgeClient, BridgeError, load_bridge_info, pid_alive  # noqa: E402

BRIDGE = os.path.join(os.environ["APPDATA"], "StardewValley", "AgentFarm", "bridge.json")
OUT = os.path.join(REPO, "logs", "run3-observe-start.json")


def dig(obj, *path, default=None):
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


print("=== pid 双向取证（同一份 bridge.json）===")
with open(BRIDGE, "r", encoding="utf-8") as fh:
    raw_text = fh.read()
raw = json.loads(raw_text)
print(f"原始文件文本          : {raw_text.strip()}")
print(f"原始 pid 键           : {raw.get('pid')!r}   (pid_alive={pid_alive(raw.get('pid')) if raw.get('pid') else '?'})")
try:
    info = load_bridge_info()
    print(f"load_bridge_info() 类型: {type(info).__name__}")
    print(f"load_bridge_info().pid : {getattr(info, 'pid', '<无该属性>')!r}")
    print(f"info 全文              : {repr(info)[:400]}")
except Exception as exc:  # noqa: BLE001
    print(f"load_bridge_info() 抛异常: {type(exc).__name__}: {exc}")

print("\n=== 起跑前观测 ===")
try:
    c = BridgeClient(timeout=15.0)
    h = c.health(timeout=10.0)
except BridgeError as exc:
    print(f"❌ 桥不可达 status={exc.status}: {exc}")
    raise SystemExit(2)

obs = c.observe("full", timeout=25.0)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(obs, fh, ensure_ascii=False, indent=1)
print(f"已落盘：{OUT}  ({os.path.getsize(OUT)} bytes)")

clock = obs.get("clock") or {}
player = obs.get("player") or {}
farm = obs.get("farm") or {}
loc = obs.get("location") or {}
ui = obs.get("ui") or {}
live = obs.get("liveness") or {}
inv = player.get("inventory") or []
seeds = [[it.get("index"), it.get("name"), it.get("stack")] for it in inv if "seed" in str(it.get("name", "")).lower()]

print(f"worldSeq      : {obs.get('worldSeq')}   generatedAt={obs.get('generatedAt')}")
print(f"modVersion    : {h.get('modVersion')}   (health.ok={h.get('ok')})  runtime={h.get('runtime')}")
print(f"hasSaveLoaded : {obs.get('hasSaveLoaded')}")
print(f"clock         : year={clock.get('year')} season={clock.get('season')} day={clock.get('day')} tod={clock.get('timeOfDay')} weather={clock.get('weather')}")
print(f"location      : name={loc.get('name')} isOutdoorFarm={loc.get('isOutdoorFarm')} isFarmHouse={loc.get('isFarmHouse')}")
print(f"player        : {player.get('name')} tile={player.get('tile')} facing={player.get('facing')} stamina={player.get('stamina')}/{player.get('maxStamina')} money={player.get('money')} farmingLevel={player.get('farmingLevel')} isInBed={player.get('isInBed')} canMove={player.get('canMove')} invCount={player.get('inventoryCount')}")
print(f"wateringCan   : {player.get('wateringCan')}")
print(f"seeds         : {seeds}")
print(f"farm          : crops={farm.get('crops')} unwatered={farm.get('unwateredCrops')} dry={farm.get('dryCrops')} ripe={farm.get('ripeCrops')} hoeDirt={farm.get('hoeDirt')} emptyDirt={farm.get('emptyDirt')} weeds={farm.get('weeds')} stones={farm.get('stones')} twigs={farm.get('twigs')} complete={farm.get('complete')} scanSeq={farm.get('scanSeq')}")
print(f"ui            : activeMenu={ui.get('activeMenu')!r} isModal={ui.get('isModal')} onScreenMenus={ui.get('onScreenMenus')} dialogueIsQuestion={ui.get('dialogueIsQuestion')}")
print(f"liveness      : worldAdvancing={live.get('worldAdvancing')} secondsSinceClockMoved={live.get('secondsSinceClockMoved')}")
print(f"game          : paused={dig(obs, 'game', 'paused')} shouldTimePass={dig(obs, 'game', 'shouldTimePass')}")
print(f"tiles         : count={len(loc.get('tiles') or [])} truncated={loc.get('tilesTruncated')}")

print("\n=== 四项硬判据 ===")
expect = "0.7.23"
ok1 = h.get("modVersion") == expect
ok2 = bool(obs.get("hasSaveLoaded"))
ok3 = bool(loc.get("isOutdoorFarm"))
ok4 = not bool(ui.get("isModal"))
for ok, label in ((ok1, f"装机版本 == {expect}（实测 {h.get('modVersion')}）"),
                  (ok2, "hasSaveLoaded == true"),
                  (ok3, f"location.isOutdoorFarm == true（实测 {loc.get('isOutdoorFarm')}）"),
                  (ok4, f"ui.isModal == false（activeMenu={ui.get('activeMenu')!r}）")):
    print(f"{'✅' if ok else '❌'} {label}")
print("\n结论：" + ("✅ 可以起跑" if all((ok1, ok2, ok3, ok4)) else "❌ 不要起跑"))
print(f"记录时刻：{time.strftime('%Y-%m-%d %H:%M:%S')}")
raise SystemExit(0 if all((ok1, ok2, ok3, ok4)) else 1)
