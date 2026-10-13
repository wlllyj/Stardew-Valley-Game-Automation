# -*- coding: utf-8 -*-
"""run4 起跑前取证（只读）：pid 双向取证 + 四判据 + 观测快照 + 存档/SMAPI/进程读数。

不覆盖 Lead 的 logs\\run4-baseline.json；自己的观测快照写 logs\\run4-observe-start.json。
用法：python scratch\\run4-start.py
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "brain"))

from agentfarm.bridge import BridgeClient, BridgeError, load_bridge_info, pid_alive  # noqa: E402

try:
    from agentfarm.bridge import MOD_VERSION_EXPECTED  # type: ignore
except Exception:  # noqa: BLE001
    MOD_VERSION_EXPECTED = None

APPDATA = os.environ["APPDATA"]
BRIDGE = os.path.join(APPDATA, "StardewValley", "AgentFarm", "bridge.json")
SAVEDIR = os.path.join(APPDATA, "StardewValley", "Saves", "Wahaha_450799035")
SAVEMAIN = os.path.join(SAVEDIR, "Wahaha_450799035")
SAVEINFO = os.path.join(SAVEDIR, "SaveGameInfo")
SMAPI = os.path.join(APPDATA, "StardewValley", "ErrorLogs", "SMAPI-latest.txt")


def stat_line(p: str) -> str:
    name = os.path.basename(p)
    if not os.path.exists(p):
        return f"{name}: 不存在"
    st = os.stat(p)
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
    ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)) % 10**9
    return f"{name}: size={st.st_size} mtime={ts}.{ns:09d}"


print("=== A. bridge.json 原文与 pid 双向取证 ===")
if os.path.exists(BRIDGE):
    with open(BRIDGE, encoding="utf-8") as fh:
        raw = fh.read()
    print("mtime=" + time.strftime("%H:%M:%S", time.localtime(os.stat(BRIDGE).st_mtime)))
    print("raw=" + raw.strip())
    try:
        obj = json.loads(raw)
        print(f"原始 pid 键 = {obj.get('pid')!r}   modVersion = {obj.get('modVersion')!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"JSON 解析失败：{type(exc).__name__}: {exc}")
else:
    print("bridge.json 不存在")

info = None
try:
    info = load_bridge_info()
    print(f"load_bridge_info() → {type(info).__name__}  .pid = {getattr(info, 'pid', None)!r}")
    print(f"  audit = {getattr(info, 'audit', None)!r}")
except Exception as exc:  # noqa: BLE001
    print(f"load_bridge_info() 抛异常：{type(exc).__name__}: {exc}")
print(f"MOD_VERSION_EXPECTED = {MOD_VERSION_EXPECTED!r}")

print("\n=== B. 进程与桥 ===")
pid = getattr(info, "pid", None)
print(f"pid_alive({pid}) = {pid_alive(pid) if pid else '?'}")
c = BridgeClient()
health: dict = {}
try:
    health = c.health()
    print("health = " + json.dumps({k: health.get(k) for k in ("ok", "status", "modVersion", "gameVersion", "smapiVersion", "runtime")}, ensure_ascii=False)[:700])
except BridgeError as exc:
    print(f"health 失败：{exc}")

print("\n=== C. 观测快照（full → logs/run4-observe-start.json）===")
obs = None
for detail in ("full", None):
    try:
        obs = c.observe(detail) if detail else c.observe()
        break
    except TypeError as exc:
        print(f"observe({detail!r}) TypeError: {exc}")
    except BridgeError as exc:
        print(f"observe({detail!r}) BridgeError: {exc}")
        break

if obs is not None:
    out = os.path.join(REPO, "logs", "run4-observe-start.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(obs, fh, ensure_ascii=False, indent=1)
    print(f"已写 {out} ({os.path.getsize(out)} bytes)")
    clock = obs.get("clock") or {}
    pl = obs.get("player") or {}
    loc = obs.get("location") or {}
    ui = obs.get("ui") or {}
    live = obs.get("liveness") or {}
    farm = obs.get("farm") or {}
    print(f"hasSaveLoaded={obs.get('hasSaveLoaded')} worldSeq={obs.get('worldSeq')} generatedAt={obs.get('generatedAt')}")
    print("clock=" + json.dumps(clock, ensure_ascii=False))
    print(f"location={loc.get('name')} isOutdoorFarm={loc.get('isOutdoorFarm')} tile={pl.get('tile')} isInBed={pl.get('isInBed')}")
    print(f"stamina={pl.get('stamina')}/{pl.get('maxStamina')} money={pl.get('money')} farmingLevel={pl.get('farmingLevel')} waterLeft={(pl.get('wateringCan') or {}).get('waterLeft')}")
    print(f"ui.isModal={ui.get('isModal')} activeMenu={ui.get('activeMenu')!r} worldAdvancing={live.get('worldAdvancing')}")
    print(f"farm crops={farm.get('crops')} unwatered={farm.get('unwateredCrops')} dry={farm.get('dryCrops')} ripe={farm.get('ripeCrops')} hoeDirt={farm.get('hoeDirt')} emptyDirt={farm.get('emptyDirt')} complete={farm.get('complete')} scanSeq={farm.get('scanSeq')}")
    print("inventory=" + json.dumps(pl.get("inventory"), ensure_ascii=False)[:900])
    checks = {
        "hasSaveLoaded": bool(obs.get("hasSaveLoaded")),
        "isOutdoorFarm": bool(loc.get("isOutdoorFarm")),
        "isModalFalse": ui.get("isModal") is False,
        "modVersionMatches": (MOD_VERSION_EXPECTED is None) or (str(health.get("modVersion")) == str(MOD_VERSION_EXPECTED)),
    }
    print("四判据=" + json.dumps(checks, ensure_ascii=False) + "  ALL=" + str(all(checks.values())))
else:
    print("观测失败，无可写快照")

print("\n=== D. 存档 / SMAPI / 时间 ===")
print(stat_line(SAVEMAIN))
print(stat_line(SAVEINFO))
print("_old: " + stat_line(SAVEMAIN + "_old"))
if os.path.exists(SMAPI):
    with open(SMAPI, "rb") as fh:
        n = sum(1 for _ in fh)
    print(f"SMAPI-latest.txt: {n} 行  " + stat_line(SMAPI))
else:
    print("SMAPI-latest.txt 不存在")
print("now = " + time.strftime("%Y-%m-%dT%H:%M:%S%z"))
