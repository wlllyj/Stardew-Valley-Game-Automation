# -*- coding: utf-8 -*-
"""task-177 step1: read-only field check on 0.7.34 (harvestMethod key + readySource + farm pool).

Dumps the full observation to scratch/run10b-tile6029-fields.json and prints:
  - key EXISTENCE (not just value) for harvestMethod / readySource on the sample tile
  - sample + neighbours tile fields, farm pool counts, window ready==true tile count
  - inventory (count + per-slot), save 4 files, SMAPI six counters
Read-only: no game action at all.
"""
from __future__ import annotations

import datetime
import io
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402
from agentfarm.farmwork import FarmWorker, _ready_note, harvest_tool, tile_ready  # noqa: E402

TILE = (60, 29)
NEIGHBOURS = [(60, 28), (59, 29), (61, 29), (60, 30)]
SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
OUT = os.path.join(ROOT, "scratch", "run10b-tile6029-fields.json")

TILE_KEYS = ("kind", "tool", "feature", "crop", "ripe", "ready", "readySource", "harvestMethod",
             "fullyGrown", "currentPhase", "phaseDays", "dayOfCurrentPhase", "dead", "watered",
             "standable", "actionable", "plantable", "objId", "regrowsAfterHarvest")
FARM_KEYS = ("readyCrops", "ripeCrops", "crops", "dryCrops", "deadCrops", "unwateredCrops",
             "hoeDirt", "emptyDirt", "complete", "scanSeq")


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
    out = {"exists": os.path.exists(SMAPI)}
    if not out["exists"]:
        return out
    with io.open(SMAPI, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    pats = {
        "newday": "Synchronizing 'NewDay' task",
        "before_save": "Context: before save.",
        "save_called": "SaveGame.Save() called.",
        "save_task": "Synchronizing 'Save' task",
        "save_completed": "SaveGame.Save() completed without exceptions.",
    }
    counts = {k: 0 for k in pats}
    raw_called = 0
    for ln in lines:
        for k, p in pats.items():
            if p in ln:
                counts[k] += 1
        if pats["save_called"] in ln:
            raw_called += 1
    # L16 false positive rule (task-140): timestamped line AND not the plugin description
    has_prefix = any(("SaveGame.Save() called." in ln) and ln.startswith("[") and "]" in ln[:30]
                     and (" by AgentFarm " not in ln) and ("| v0." not in ln) for ln in lines)
    st = os.stat(SMAPI)
    out.update({"lines": len(lines), "size": st.st_size,
                "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds"),
                "newday": counts["newday"], "before_save": counts["before_save"],
                "save_called_raw": raw_called,
                "save_called_corrected": raw_called - (1 if (raw_called and not has_prefix) else 0),
                "save_task": counts["save_task"], "save_completed": counts["save_completed"]})
    return out


def keyreport(tv):
    """Existence, not just value (task-177 requirement: keys must be emitted)."""
    rep = {}
    for k in ("harvestMethod", "readySource"):
        rep[k] = {"key_present": (k in tv), "value": tv.get(k, "__KEY_MISSING__")}
    rep["_all_keys"] = sorted(tv.keys())
    return rep


def main() -> int:
    c = BridgeClient()
    w = FarmWorker(c, log=lambda *_: None)
    h = c.health()
    print("=== [0] env ===")
    print(f"modVersion={h.get('modVersion')} port={h.get('port')} hasSaveLoaded={h.get('hasSaveLoaded')}")

    obs = c.observe("full")
    with io.open(OUT, "w", encoding="utf-8") as fh:
        json.dump(obs, fh, ensure_ascii=False, indent=1)

    pl = obs.get("player") or {}
    ui = obs.get("ui") or {}
    print(f"clock={jprint(obs.get('clock'))} worldSeq={obs.get('worldSeq')}")
    print(f"player tile={pl.get('tile')} stamina={pl.get('stamina')} money={pl.get('money')} "
          f"farmingLevel={pl.get('farmingLevel')} inventoryCount={pl.get('inventoryCount')}")
    print(f"ui={jprint({k: ui.get(k) for k in ('activeMenu', 'isModal', 'eventUp', 'professionsToChoose')})}")

    tv = w.tile_view(obs, TILE)
    if tv is None:
        print(f"!! {TILE} NOT in window (player at {pl.get('tile')}) -> move closer and rerun")
        return 3

    print(f"\n=== [1] sample {TILE} ===")
    print(f"KEY REPORT: {jprint(keyreport(tv))}")
    print(f"fields: {jprint({k: tv.get(k, '__KEY_MISSING__') for k in TILE_KEYS})}")
    print(f"tile_ready={tile_ready(tv)} ready_note={_ready_note(tv)!r} harvest_tool={harvest_tool(tv)!r}")

    print(f"\n=== [2] neighbours ===")
    for t in NEIGHBOURS:
        n = w.tile_view(obs, t)
        if n is None:
            print(f"  {t}: OUT-OF-WINDOW")
            continue
        print(f"  {t}: crop={n.get('crop')!r} ripe={n.get('ripe')!r} ready={n.get('ready')!r} "
              f"readySource={n.get('readySource', '__MISSING__')!r} "
              f"harvestMethod={n.get('harvestMethod', '__MISSING__')!r} fullyGrown={n.get('fullyGrown')!r}")

    farm_top = obs.get("farm") if isinstance(obs.get("farm"), dict) else None
    farm_loc = (obs.get("location") or {}).get("farm")
    farm_loc = farm_loc if isinstance(farm_loc, dict) else None
    farm = farm_top or farm_loc or {}
    print(f"\n=== [3] farm pool === (obs['farm']={'yes' if farm_top else 'no'}, location.farm={'yes' if farm_loc else 'no'})")
    print(f"farm: {jprint({k: farm.get(k, '__MISSING__') for k in FARM_KEYS})}")
    print(f"observe top-level keys: {jprint(sorted(obs.keys()))}")
    tiles = ((obs.get("location") or {}).get("tiles")) or []
    ready_true = [t for t in tiles if isinstance(t, dict) and t.get("ready") is True]
    with_crop = [t for t in tiles if isinstance(t, dict) and t.get("crop")]
    print(f"window tiles={len(tiles)} ready==true {len(ready_true)} with_crop {len(with_crop)}")
    print(f"ready==true sample coords (first 8): {jprint([t.get('tile') for t in ready_true[:8]])}")

    print(f"\n=== [4] inventory ===")
    inv = pl.get("inventory") or []
    print(f"inventoryCount={pl.get('inventoryCount')} slots={len(inv)}")
    for it in inv:
        if isinstance(it, dict):
            print(f"  slot={it.get('slot')} qid={it.get('qualifiedId')!r} name={it.get('name')!r} stack={it.get('stack')}")

    print(f"\n=== [5] saves / smapi ===")
    print(f"saves: {jprint([stat_of(n) for n in ('Wahaha_450799035', 'SaveGameInfo', 'Wahaha_450799035_old', 'SaveGameInfo_old')])}")
    print(f"smapi: {jprint(smapi_counts())}")
    print(f"\ndumped full observe -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
