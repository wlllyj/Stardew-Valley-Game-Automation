# -*- coding: utf-8 -*-
"""task-177 step5: control-tile probe -- a tile whose fullyGrown=false yet ready=true.

Sample (60,29) harvested fine (crop 270, Grab). Its neighbours (60,28)/(61,29)/(60,30) are
crop "262" with ripe=false / fullyGrown=false / ready=true / readySource="game" /
harvestMethod="Scythe" -- exactly the "pool not narrowed" shape (defect B). This script runs
ONE harvest attempt on the control tile and reports whether the brain treats it as harvestable,
which entry point is used (interact vs use_tool/scythe), and what the Mod honestly reports.
Read-only + exactly one attempt.
"""
from __future__ import annotations

import datetime
import io
import json
import os
import sys
import time
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402
from agentfarm.farmwork import FarmWorker, _ready_note, harvest_tool, tile_ready  # noqa: E402

TILE = (60, 28)  # control: fullyGrown=false but ready=true, harvestMethod=Scythe
SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
OUT_BEFORE = os.path.join(ROOT, "scratch", "run10b-control-before.json")
OUT_AFTER = os.path.join(ROOT, "scratch", "run10b-control-after.json")

TILE_KEYS = ("kind", "tool", "feature", "crop", "ripe", "ready", "readySource", "harvestMethod",
             "fullyGrown", "currentPhase", "phaseDays", "dayOfCurrentPhase", "dead", "watered",
             "standable", "actionable", "plantable", "regrowsAfterHarvest")
FARM_KEYS = ("readyCrops", "ripeCrops", "crops", "dryCrops", "deadCrops", "unwateredCrops",
             "hoeDirt", "emptyDirt", "complete", "scanSeq")


class Rec:
    def __init__(self, client: BridgeClient) -> None:
        self._c = client
        self.used: list[str] = []
        self.raw: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def _wrap(self, name: str, *a: Any, **k: Any) -> Any:
        self.used.append(name)
        try:
            r = getattr(self._c, name)(*a, **k)
        except Exception as exc:  # noqa: BLE001
            self.raw[name + "_error"] = {"type": type(exc).__name__, "msg": str(exc)[:600]}
            raise
        self.raw[name] = r
        return r

    def interact(self, *a: Any, **k: Any) -> Any:
        return self._wrap("interact", *a, **k)

    def use_tool(self, *a: Any, **k: Any) -> Any:
        return self._wrap("use_tool", *a, **k)


def jprint(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def stat_of(name):
    p = os.path.join(SAVE_DIR, name)
    try:
        st = os.stat(p)
    except OSError as exc:
        return {"name": name, "error": type(exc).__name__}
    return {"name": name, "size": st.st_size,
            "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds")}


def smapi_counts():
    if not os.path.exists(SMAPI):
        return {"exists": False}
    with io.open(SMAPI, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    pats = {"newday": "Synchronizing 'NewDay' task", "before_save": "Context: before save.",
            "save_called": "SaveGame.Save() called."}
    counts = {k: sum(1 for ln in lines if p in ln) for k, p in pats.items()}
    return {"exists": True, "lines": len(lines), "newday": counts["newday"],
            "before_save": counts["before_save"], "save_called_raw": counts["save_called"]}


def tvf(w, obs, tile):
    tv = w.tile_view(obs, tile)
    if tv is None:
        return {"__out_of_window__": True}
    return {k: tv.get(k, "__KEY_MISSING__") for k in TILE_KEYS}


def farmf(obs):
    farm = obs.get("farm") if isinstance(obs.get("farm"), dict) else {}
    return {k: farm.get(k, "__KEY_MISSING__") for k in FARM_KEYS}


def main() -> int:
    c = BridgeClient()
    proxy = Rec(c)
    w = FarmWorker(proxy, log=lambda *_: None)

    obs0 = c.observe("full")
    with io.open(OUT_BEFORE, "w", encoding="utf-8") as fh:
        json.dump(obs0, fh, ensure_ascii=False, indent=1)
    tv0 = w.tile_view(obs0, TILE)
    if tv0 is None:
        print(f"!! {TILE} not in window -> move closer")
        return 3
    inv0 = w._inventory_counts(w.player_of(obs0))
    pl0 = obs0.get("player") or {}
    print(f"=== [1] BEFORE === worldSeq={obs0.get('worldSeq')} player={pl0.get('tile')} "
          f"stamina={pl0.get('stamina')} money={pl0.get('money')}")
    print(f"farm: {jprint(farmf(obs0))}")
    print(f"inv: {jprint(inv0)}")
    print(f"{TILE}: {jprint(tvf(w, obs0, TILE))}")
    print(f"tile_ready={tile_ready(tv0)} ready_note={_ready_note(tv0)!r} harvest_tool={harvest_tool(tv0)!r}")
    print(f"keys: harvestMethod present={'harvestMethod' in tv0} readySource present={'readySource' in tv0}")

    print(f"\n=== [2] ONE harvest({TILE}) ===")
    t0 = time.time()
    r = w.harvest(TILE)
    print(f"elapsed={time.time() - t0:.1f}s ok={r.ok} code={r.code} status={r.status!r}")
    print(f"reason = {r.reason}")
    print(f"receipt = {r.receipt}")
    print(f"before = {jprint(r.before)}")
    print(f"after  = {jprint(r.after)}")
    print(f"entry points used = {proxy.used}")
    print(f"raw = {jprint(proxy.raw)}")

    time.sleep(2.0)
    obs1 = c.observe("full")
    with io.open(OUT_AFTER, "w", encoding="utf-8") as fh:
        json.dump(obs1, fh, ensure_ascii=False, indent=1)
    inv1 = w._inventory_counts(w.player_of(obs1))
    pl1 = obs1.get("player") or {}
    print(f"\n=== [3] AFTER === worldSeq={obs1.get('worldSeq')} (was {obs0.get('worldSeq')}) "
          f"stamina={pl1.get('stamina')} money={pl1.get('money')}")
    print(f"farm: {jprint(farmf(obs1))}")
    print(f"inv: {jprint(inv1)}")
    print(f"{TILE}: {jprint(tvf(w, obs1, TILE))}")
    gained = {k: v for k, v in inv1.items() if v != inv0.get(k)}
    print(f"\n=== [4] diff === farm.readyCrops {farmf(obs0)['readyCrops']}->{farmf(obs1)['readyCrops']} ; "
          f"ripeCrops {farmf(obs0)['ripeCrops']}->{farmf(obs1)['ripeCrops']} ; "
          f"crop {tvf(w, obs0, TILE)['crop']!r}->{tvf(w, obs1, TILE)['crop']!r} ; "
          f"ready {tvf(w, obs0, TILE)['ready']!r}->{tvf(w, obs1, TILE)['ready']!r} ; "
          f"inv gained={jprint(gained)}")
    print(f"saves: {jprint([stat_of(n) for n in ('Wahaha_450799035', 'SaveGameInfo')])}")
    print(f"smapi: {jprint(smapi_counts())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
