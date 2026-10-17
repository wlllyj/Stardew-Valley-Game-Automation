# -*- coding: utf-8 -*-
"""task-184 探针（0.7.35 同格复测）：fields / sell / harvest / control。

离线判定交给 `scratch\\_t184_triple_check.py`（脑 StepResult × Mod 原始回执 × 世界差分）。

用法（每次只跑一条子命令）：
    python scratch\\_t184_probe.py fields
    python scratch\\_t184_probe.py sell --qid "(O)Moss"
    python scratch\\_t184_probe.py harvest --tile 60,29
    python scratch\\_t184_probe.py control --tile 60,28

纪律：不做 load_save、不跨日、不改生产代码；产物全部写在 scratch/_t184_*。
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import sys
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "brain"))
sys.path.insert(0, HERE)

from agentfarm.bridge import BridgeClient  # noqa: E402
from agentfarm.farmwork import FarmWorker, _ready_note, harvest_tool, tile_ready  # noqa: E402
import _t184_triple_check as tc  # noqa: E402

SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
TILE = (60, 29)
NEIGHBOURS = [(60, 28), (59, 29), (61, 29), (60, 30)]

TILE_KEYS = ("kind", "tool", "feature", "crop", "ripe", "ready", "readySource", "harvestMethod",
             "fullyGrown", "currentPhase", "phaseDays", "dayOfCurrentPhase", "dead", "watered",
             "standable", "actionable", "plantable", "objId", "regrowsAfterHarvest")
FARM_KEYS = ("readyCrops", "ripeCrops", "crops", "dryCrops", "deadCrops", "unwateredCrops",
             "hoeDirt", "emptyDirt", "complete", "scanSeq")


def jp(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, sort_keys=True)


def path(name: str) -> str:
    return os.path.join(HERE, name)


def dump(name: str, obj: Any) -> str:
    p = path(name)
    with io.open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    return p


class Rec:
    """薄代理：调用前记账 + 截获 Mod 原始回执（no_action 会让客户端抛 BridgeError）。"""

    def __init__(self, client: BridgeClient) -> None:
        self._c = client
        self.used: list[str] = []
        self.raw: dict[str, Any] = {}
        self.errors: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def interact(self, *a: Any, **k: Any) -> Any:
        self.used.append("interact")
        try:
            r = self._c.interact(*a, **k)
        except Exception as exc:  # noqa: BLE001
            self.errors["interact"] = {"type": type(exc).__name__, "msg": str(exc)[:800]}
            raise
        self.raw["interact"] = r
        return r

    def use_tool(self, *a: Any, **k: Any) -> Any:
        self.used.append("use_tool")
        try:
            r = self._c.use_tool(*a, **k)
        except Exception as exc:  # noqa: BLE001
            self.errors["use_tool"] = {"type": type(exc).__name__, "msg": str(exc)[:800]}
            raise
        self.raw["use_tool"] = r
        return r

    def action_receipt(self) -> dict | None:
        return self.raw.get("use_tool") or self.raw.get("interact")


def save_stats() -> list[dict]:
    out = []
    for n in ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old"):
        p = os.path.join(SAVE_DIR, n)
        try:
            st = os.stat(p)
        except OSError as exc:
            out.append({"name": n, "error": type(exc).__name__})
            continue
        out.append({"name": n, "size": st.st_size,
                    "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds")})
    return out


def smapi_counts() -> dict:
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
    return {"exists": True, "lines": len(lines), "mtime":
            datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds"),
            "newday": counts["newday"], "before_save": counts["before_save"],
            "save_called_raw": counts["save_called"], "save_called_corrected": corrected,
            "save_task": counts["save_task"], "save_completed": counts["save_completed"]}


def farmf(obs: dict) -> dict:
    top = obs.get("farm") if isinstance(obs.get("farm"), dict) else None
    loc = (obs.get("location") or {}).get("farm")
    loc = loc if isinstance(loc, dict) else None
    farm = top or loc or {}
    out = {k: farm.get(k, "__KEY_MISSING__") for k in FARM_KEYS}
    out["_source"] = "obs.farm" if top else ("location.farm" if loc else "none")
    return out


def tvf(w: FarmWorker, obs: dict, tile: tuple[int, int]) -> dict | None:
    tv = w.tile_view(obs, tile)
    if tv is None:
        return None
    return {k: tv.get(k, "__KEY_MISSING__") for k in TILE_KEYS}


def window_counts(obs: dict) -> dict:
    tiles = ((obs.get("location") or {}).get("tiles")) or []
    return {"window_tiles": len(tiles),
            "ready_true": sum(1 for t in tiles if isinstance(t, dict) and t.get("ready") is True),
            "with_crop": sum(1 for t in tiles if isinstance(t, dict) and t.get("crop"))}


def inv_rows(obs: dict) -> list[dict]:
    inv = ((obs.get("player") or {}).get("inventory")) or []
    rows = []
    for i, s in enumerate(inv):
        if not isinstance(s, dict):
            continue
        rows.append({"slot": i, "itemId": s.get("itemId") or s.get("qid") or s.get("id"),
                     "name": s.get("name"), "stack": s.get("stack")})
    return rows


def shipping_bin(obs: dict) -> dict:
    cands = {"obs.shippingBin": obs.get("shippingBin"),
             "location.shippingBin": (obs.get("location") or {}).get("shippingBin"),
             "farm.shippingBin": (obs.get("farm") or {}).get("shippingBin")}
    found = {k: v for k, v in cands.items() if v is not None}
    if not found:
        keys = sorted((obs.get("location") or {}).keys())
        return {"__not_found__": True, "location_keys": keys[:40]}
    return found


def solo_inv(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        if r.get("itemId"):
            out[str(r["itemId"])] = out.get(str(r["itemId"]), 0) + int(r.get("stack") or 0)
    return out


def env_line(c: BridgeClient, w: FarmWorker) -> dict:
    h = c.health()
    rt = h.get("runtime") or {}
    print(f"=== env === modVersion={h.get('modVersion')} port={h.get('port')} "
          f"hasSaveLoaded={h.get('hasSaveLoaded')} ticks={rt.get('ticks')}")
    return h


# ------------------------------------------------------------------ subcommands
def cmd_fields(c: BridgeClient, w: FarmWorker, args) -> int:
    env_line(c, w)
    obs = c.observe("full")
    p = dump("_t184_observe-fields.json", obs)
    pl = obs.get("player") or {}
    rows = inv_rows(obs)
    print(f"worldSeq={obs.get('worldSeq')} clock={jp(obs.get('clock'))} "
          f"player={pl.get('tile')} stamina={pl.get('stamina')} money={pl.get('money')}")
    print(f"ui={jp(obs.get('ui'))} liveness={jp(obs.get('liveness'))}")
    print(f"farm: {jp(farmf(obs))}")
    print(f"window: {jp(window_counts(obs))}")
    print(f"inventory ROWS={len(rows)} (player.inventoryCount={pl.get('inventoryCount')} 是容量字段)")
    print(f"inv: {jp(rows)}")
    print(f"qid totals: {jp(solo_inv(rows))}")
    print(f"shippingBin: {jp(shipping_bin(obs))}")
    for t in [TILE] + NEIGHBOURS:
        tv = tvf(w, obs, t)
        if tv is None:
            print(f"  {t}: NOT IN WINDOW")
            continue
        print(f"  {t}: crop={tv['crop']!r} ready={tv['ready']!r} readySource={tv['readySource']!r} "
              f"harvestMethod={tv['harvestMethod']!r} ripe={tv['ripe']!r} fullyGrown={tv['fullyGrown']!r} "
              f"regrows={tv['regrowsAfterHarvest']!r}")
    tv0 = tvf(w, obs, TILE)
    print(f"TILE {TILE}: harvestMethod key={'harvestMethod' in (w.tile_view(obs, TILE) or {})} "
          f"readySource key={'readySource' in (w.tile_view(obs, TILE) or {})}")
    if tv0:
        print(f"TILE {TILE}: tile_ready={tile_ready(w.tile_view(obs, TILE))} "
              f"ready_note={_ready_note(w.tile_view(obs, TILE))!r} harvest_tool={harvest_tool(w.tile_view(obs, TILE))!r}")
    print(f"saves: {jp(save_stats())}")
    print(f"smapi: {jp(smapi_counts())}")
    print(f"dumped: {p}")
    return 0


def cmd_sell(c: BridgeClient, w: FarmWorker, args) -> int:
    env_line(c, w)
    qid = args.qid
    # 观测里的 itemId 是无前缀的（"Moss"/"262"），而 sell 的 whitelist 用带类型前缀的（"(O)Moss"）
    # ⇒ 匹配时归一化，白名单参数按脑侧约定补 "(O)"。
    def norm(x: Any) -> str:
        return str(x or "").replace("(O)", "").replace("(T)", "").replace("(W)", "")
    wl = qid if str(qid).startswith("(") else f"(O){qid}"
    obs0 = c.observe("full")
    rows0 = inv_rows(obs0)
    slot = next((r["slot"] for r in rows0 if norm(r.get("itemId")) == norm(qid)), None)
    if slot is None:
        print(f"!! 背包里没有白名单 qid {qid}（归一化匹配）；现有：{jp(solo_inv(rows0))}")
        return 3
    qid = wl
    dump("_t184_sell-before.json", obs0)
    print(f"=== SELL BEFORE === rows={len(rows0)} slot={slot} stack={rows0[slot].get('stack')} "
          f"qid={qid} money={(obs0.get('player') or {}).get('money')}")
    print(f"shippingBin before: {jp(shipping_bin(obs0))}")
    t0 = time.time()
    try:
        r = w.sell(slot, whitelist=[qid])
        print(f"sell: ok={r.ok} code={r.code} status={r.status!r} elapsed={time.time() - t0:.1f}s")
        print(f"reason = {r.reason}")
        print(f"receipt = {r.receipt}")
    except Exception as exc:  # noqa: BLE001
        print(f"!! sell raised {type(exc).__name__}: {str(exc)[:400]}")
        return 4
    time.sleep(1.5)
    obs1 = c.observe("full")
    dump("_t184_sell-after.json", obs1)
    rows1 = inv_rows(obs1)
    print(f"=== SELL AFTER === rows={len(rows1)} (was {len(rows0)}) "
          f"money={(obs1.get('player') or {}).get('money')} (was {(obs0.get('player') or {}).get('money')})")
    print(f"qid totals after: {jp(solo_inv(rows1))}")
    print(f"shippingBin after: {jp(shipping_bin(obs1))}")
    print(f"saves: {jp(save_stats())}")
    return 0


def _one_action(c: BridgeClient, w: FarmWorker, proxy: Rec, tile: tuple[int, int], tag: str) -> dict:
    obs0 = c.observe("full")
    dump(f"_t184_{tag}-before.json", obs0)
    tv0 = tvf(w, obs0, tile)
    print(f"\n=== [{tag}] BEFORE === worldSeq={obs0.get('worldSeq')} "
          f"player={(obs0.get('player') or {}).get('tile')} farm={jp(farmf(obs0))}")
    print(f"  window={jp(window_counts(obs0))} invRows={len(inv_rows(obs0))} "
          f"qid={jp(solo_inv(inv_rows(obs0)))}")
    print(f"  {tile}: {jp(tv0)}")
    if tv0 is None:
        print(f"  !! {tile} 不在观测窗口内")
        return {"error": "out_of_window"}
    tv_raw = w.tile_view(obs0, tile)
    print(f"  tile_ready={tile_ready(tv_raw)} ready_note={_ready_note(tv_raw)!r} "
          f"harvest_tool={harvest_tool(tv_raw)!r}")

    brain: dict[str, Any] = {}
    t0 = time.time()
    try:
        r = w.harvest(tile)
        brain = {"ok": r.ok, "code": r.code, "status": r.status, "reason": r.reason,
                 "proven_inert": getattr(r, "proven_inert", None),
                 "env_block": getattr(r, "env_block", None),
                 "inconclusive": getattr(r, "inconclusive", None),
                 "before": getattr(r, "before", None), "after": getattr(r, "after", None)}
        print(f"  brain: ok={r.ok} code={r.code} status={r.status!r} elapsed={time.time() - t0:.1f}s")
        print(f"  reason = {r.reason}")
    except Exception as exc:  # noqa: BLE001
        brain = {"ok": None, "code": "raised", "status": "", "reason": f"{type(exc).__name__}: {str(exc)[:600]}"}
        print(f"  !! harvest raised {type(exc).__name__}: {str(exc)[:400]}")
    receipt = proxy.action_receipt()
    print(f"  entry points used = {proxy.used}")
    print(f"  Mod raw receipt = {jp(receipt)}")
    if proxy.errors:
        print(f"  proxy errors = {jp(proxy.errors)}")
    time.sleep(2.0)
    obs1 = c.observe("full")
    dump(f"_t184_{tag}-after.json", obs1)
    print(f"  AFTER worldSeq={obs1.get('worldSeq')} farm={jp(farmf(obs1))} "
          f"window={jp(window_counts(obs1))} qid={jp(solo_inv(inv_rows(obs1)))}")
    print(f"  {tile} after: {jp(tvf(w, obs1, tile))}")
    print(f"  saves: {jp(save_stats())}")

    payload = {"tag": tag, "tile": list(tile), "brain": brain, "receipt": receipt,
               "entry_points": proxy.used, "proxy_errors": proxy.errors,
               "brain_step_reason": brain.get("reason")}
    dump(f"_t184_{tag}-receipt.json", payload)
    world = tc.world_diff(obs0, obs1, tile)
    verdict = tc.report(brain, receipt, world, title=f"task-184 {tag} {tile}")
    dump(f"_t184_{tag}-verdict.json", {"verdict": verdict, "world": world, "plate": payload})
    print(f"  three_way_consistent = {verdict['three_way_consistent']}")
    return verdict


def cmd_harvest(c: BridgeClient, w: FarmWorker, args) -> int:
    env_line(c, w)
    proxy = Rec(c)
    w2 = FarmWorker(proxy, log=lambda *_: None)
    tile = tuple(int(x) for x in args.tile.split(","))
    print(f"=== start snapshot ===\n{jp(save_stats())}\nsmapi: {jp(smapi_counts())}")
    v = _one_action(c, w2, proxy, tile, args.tag)
    return 0 if isinstance(v, dict) and v.get("three_way_consistent") else 10


def cmd_control(c: BridgeClient, w: FarmWorker, args) -> int:
    return cmd_harvest(c, w, args)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fields")
    ps = sub.add_parser("sell")
    ps.add_argument("--qid", default="(O)Moss")
    for name in ("harvest", "control"):
        p = sub.add_parser(name)
        p.add_argument("--tile", required=True)
        p.add_argument("--tag", default=None)
    args = ap.parse_args()
    if args.cmd in ("harvest", "control") and not args.tag:
        args.tag = "harvest-6029" if args.cmd == "harvest" else "control-6028"
    c = BridgeClient()
    w = FarmWorker(c, log=lambda *_: None)
    return {"fields": cmd_fields, "sell": cmd_sell,
            "harvest": cmd_harvest, "control": cmd_control}[args.cmd](c, w, args)


if __name__ == "__main__":
    sys.exit(main())
