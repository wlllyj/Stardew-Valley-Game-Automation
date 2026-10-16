# -*- coding: utf-8 -*-
"""task-177 step3/4: ONE harvest attempt on (60,29) at 0.7.34, with full before/after observe.

- FarmWorker.harvest() itself routes to use_tool(scythe) when harvestMethod == "Scythe",
  otherwise interact; the proxy records which entry point was actually used + the raw receipt.
- Criteria readouts printed, conclusion is written in the doc (script only reports).
- Read-only + exactly one harvest attempt. No load_save, no day crossing.
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

TILE = (60, 29)
NEIGHBOURS = [(60, 28), (59, 29), (61, 29), (60, 30)]
SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
OUT_BEFORE = os.path.join(ROOT, "scratch", "run10b-tile6029-before.json")
OUT_AFTER = os.path.join(ROOT, "scratch", "run10b-tile6029-after.json")

TILE_KEYS = ("kind", "tool", "feature", "crop", "ripe", "ready", "readySource", "harvestMethod",
             "fullyGrown", "currentPhase", "phaseDays", "dayOfCurrentPhase", "dead", "watered",
             "standable", "actionable", "plantable", "objId", "regrowsAfterHarvest")
FARM_KEYS = ("readyCrops", "ripeCrops", "crops", "dryCrops", "deadCrops", "unwateredCrops",
             "hoeDirt", "emptyDirt", "complete", "scanSeq")


class Rec:
    """Thin proxy: records which entry point was used + the raw receipt."""

    def __init__(self, client: BridgeClient) -> None:
        self._c = client
        self.used: list[str] = []
        self.raw: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def interact(self, *a: Any, **k: Any) -> Any:
        self.used.append("interact")          # record BEFORE the call: no_action raises BridgeError
        try:
            r = self._c.interact(*a, **k)
        except Exception as exc:  # noqa: BLE001
            self.raw["interact_error"] = {"type": type(exc).__name__, "msg": str(exc)[:600]}
            raise
        self.raw["interact"] = r
        return r

    def use_tool(self, *a: Any, **k: Any) -> Any:
        self.used.append("use_tool")
        try:
            r = self._c.use_tool(*a, **k)
        except Exception as exc:  # noqa: BLE001
            self.raw["use_tool_error"] = {"type": type(exc).__name__, "msg": str(exc)[:600]}
            raise
        self.raw["use_tool"] = r
        return r


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
            "save_called": "SaveGame.Save() called.", "save_task": "Synchronizing 'Save' task",
            "save_completed": "SaveGame.Save() completed without exceptions."}
    counts = {k: 0 for k in pats}
    for ln in lines:
        for k, p in pats.items():
            if p in ln:
                counts[k] += 1
    corrected = sum(1 for ln in lines if pats["save_called"] in ln and ln.startswith("[")
                    and "]" in ln[:30] and " by AgentFarm " not in ln and "| v0." not in ln)
    st = os.stat(SMAPI)
    return {"exists": True, "lines": len(lines), "size": st.st_size,
            "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds"),
            "newday": counts["newday"], "before_save": counts["before_save"],
            "save_called_raw": counts["save_called"], "save_called_corrected": corrected,
            "save_task": counts["save_task"], "save_completed": counts["save_completed"]}


def tvf(w, obs, tile):
    tv = w.tile_view(obs, tile)
    if tv is None:
        return {"__out_of_window__": True}
    return {k: tv.get(k, "__KEY_MISSING__") for k in TILE_KEYS}


def farmf(obs):
    """Farm pool lives at TOP-LEVEL obs['farm'] (verified 0.7.34); fall back to location.farm."""
    top = obs.get("farm") if isinstance(obs.get("farm"), dict) else None
    loc = (obs.get("location") or {}).get("farm")
    loc = loc if isinstance(loc, dict) else None
    farm = top or loc or {}
    out = {k: farm.get(k, "__KEY_MISSING__") for k in FARM_KEYS}
    out["_source"] = "obs.farm" if top else ("location.farm" if loc else "none")
    return out


def ready_tile_count(obs):
    tiles = ((obs.get("location") or {}).get("tiles")) or []
    return {"window_tiles": len(tiles),
            "ready_true": sum(1 for t in tiles if isinstance(t, dict) and t.get("ready") is True),
            "with_crop": sum(1 for t in tiles if isinstance(t, dict) and t.get("crop"))}


def main() -> int:
    c = BridgeClient()
    proxy = Rec(c)
    w = FarmWorker(proxy, log=lambda *_: None)
    h = c.health()
    print(f"=== [0] env === modVersion={h.get('modVersion')} port={h.get('port')} "
          f"hasSaveLoaded={h.get('hasSaveLoaded')}")

    obs0 = c.observe("full")
    with io.open(OUT_BEFORE, "w", encoding="utf-8") as fh:
        json.dump(obs0, fh, ensure_ascii=False, indent=1)
    pl0 = obs0.get("player") or {}
    tv0 = w.tile_view(obs0, TILE)
    if tv0 is None:
        print(f"!! {TILE} not in window (player {pl0.get('tile')}) -> move closer")
        return 3
    inv0 = w._inventory_counts(w.player_of(obs0))
    print(f"\n=== [1] BEFORE === clock={jprint(obs0.get('clock'))} worldSeq={obs0.get('worldSeq')}")
    print(f"player tile={pl0.get('tile')} stamina={pl0.get('stamina')} money={pl0.get('money')} "
          f"inventoryCount={pl0.get('inventoryCount')}")
    print(f"farm: {jprint(farmf(obs0))}")
    print(f"window: {jprint(ready_tile_count(obs0))}")
    print(f"inv: {jprint(inv0)}")
    print(f"{TILE}: harvestMethod PRESENT={'harvestMethod' in tv0} value={tv0.get('harvestMethod', '__KEY_MISSING__')!r} "
          f"readySource PRESENT={'readySource' in tv0} value={tv0.get('readySource', '__KEY_MISSING__')!r}")
    print(f"{TILE}: {jprint(tvf(w, obs0, TILE))}")
    print(f"tile_ready={tile_ready(tv0)} ready_note={_ready_note(tv0)!r} harvest_tool={harvest_tool(tv0)!r}")
    save0 = [stat_of(n) for n in ('Wahaha_450799035', 'SaveGameInfo')]
    smapi0 = smapi_counts()
    print(f"saves: {jprint(save0)}")
    print(f"smapi: {jprint(smapi0)}")

    print(f"\n=== [2] ONE harvest({TILE}) ===")
    t0 = time.time()
    r = w.harvest(TILE)
    print(f"elapsed={time.time() - t0:.1f}s  ok={r.ok} code={r.code} status={r.status!r} "
          f"proven_inert={r.proven_inert} env_block={r.env_block} inconclusive={r.inconclusive}")
    print(f"reason = {r.reason}")
    print(f"receipt = {r.receipt}")
    print(f"before = {jprint(r.before)}")
    print(f"after  = {jprint(r.after)}")
    print(f"entry points used = {proxy.used}")
    print(f"raw receipt = {jprint(proxy.raw)}")

    time.sleep(2.0)
    obs1 = c.observe("full")
    with io.open(OUT_AFTER, "w", encoding="utf-8") as fh:
        json.dump(obs1, fh, ensure_ascii=False, indent=1)
    pl1 = obs1.get("player") or {}
    inv1 = w._inventory_counts(w.player_of(obs1))
    print(f"\n=== [3] AFTER === worldSeq={obs1.get('worldSeq')} (was {obs0.get('worldSeq')})")
    print(f"farm: {jprint(farmf(obs1))}")
    print(f"window: {jprint(ready_tile_count(obs1))}")
    print(f"inv: {jprint(inv1)}")

    print(f"\n=== [4] per-field diff ===")
    f0, f1 = farmf(obs0), farmf(obs1)
    for k in FARM_KEYS:
        mark = "   <== CHANGED" if f0[k] != f1[k] else ""
        print(f"farm.{k:16} {f0[k]!r:>10} -> {f1[k]!r}{mark}")
    a0, a1 = tvf(w, obs0, TILE), tvf(w, obs1, TILE)
    for k in TILE_KEYS:
        mark = "   <== CHANGED" if a0[k] != a1[k] else ""
        print(f"[{TILE}].{k:20} {a0[k]!r:>22} -> {a1[k]!r}{mark}")
    for t in NEIGHBOURS:
        n1 = tvf(w, obs1, t)
        print(f"nbr {t}: crop={n1.get('crop')!r} ready={n1.get('ready')!r} "
              f"readySource={n1.get('readySource', '__MISSING__')!r}")
    gained = {k: v for k, v in inv1.items() if v != inv0.get(k)}
    print(f"inventory diff: {jprint(gained)} (loot_delta={jprint(w._loot_delta(inv0, inv1))})")
    save1 = [stat_of(n) for n in ('Wahaha_450799035', 'SaveGameInfo')]
    smapi1 = smapi_counts()
    print(f"saves after: {jprint(save1)}")
    print(f"smapi after: {jprint(smapi1)}")

    print(f"\n=== [5] criteria readout ===")
    print(f"(1) keys present: harvestMethod={'harvestMethod' in tv0} readySource={'readySource' in tv0}")
    print(f"(2) path taken: used={proxy.used} harvest_tool={harvest_tool(tv0)!r} "
          f"harvestMethod={tv0.get('harvestMethod', '__KEY_MISSING__')!r}")
    print(f"(3) success? readyCrops {f0['readyCrops']}->{f1['readyCrops']} ; "
          f"ripeCrops {f0['ripeCrops']}->{f1['ripeCrops']} ; crop {a0['crop']!r}->{a1['crop']!r} ; "
          f"inv gained={jprint(gained)} ; worldSeq {obs0.get('worldSeq')}->{obs1.get('worldSeq')}")
    print(f"(4) honest receipt? r.ok={r.ok} code={r.code} status={r.status!r} ; "
          f"receipt acted={jprint((proxy.raw.get('interact') or proxy.raw.get('use_tool') or {}).get('acted'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
