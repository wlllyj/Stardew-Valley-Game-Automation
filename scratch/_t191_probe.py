# -*- coding: utf-8 -*-
"""task-191 探针（0.7.36 真机复测）：env / fields / sell / harvest / use-tool。

四条判据（Lead m02902）：
  ① `use_tool` 回执里 `acted` + `actedEvidence` 两键在（R1 修复点）
  ② 两条路（interact / use_tool）的世界证据都能对上（脑侧 ok 的依据必须是观测差分）
  ③ loot 逐 qid 与背包实测增量一致（R2 修复点）
  ④ 不可收的格不会被洗成成功（fail-closed）

离线判定交给 `scratch\\_t184_triple_check.py`（三源分类）+ `scratch\\_t191_loot_check.py`（R2 记账）。

用法（每次只跑一条子命令；产物全部写 scratch/_t191_*）：
    python scratch\\_t191_probe.py env
    python scratch\\_t191_probe.py fields --tile 60,29
    python scratch\\_t191_probe.py sell --slot 10 --qid "(O)Moss"
    python scratch\\_t191_probe.py harvest --tile 60,29      # Grab 再生作物 ⇒ interact 路径
    python scratch\\_t191_probe.py harvest --tile 60,28      # Scythe ⇒ use_tool 路径
    python scratch\\_t191_probe.py use-tool --tile 60,29 --tool scythe   # 原始技能回执（R1 键）

纪律：不做 load_save、不跨日、不改生产代码、不手改背包（腾格只走 `sell`/出货箱）。
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "brain"))
sys.path.insert(0, HERE)

from agentfarm.bridge import BridgeClient  # noqa: E402
from agentfarm.farmwork import (  # noqa: E402
    LOOT_CONFIRM_TRIES, LOOT_CONFIRM_WAIT_S, FarmWorker, harvest_tool, tile_ready)

import _t184_triple_check as tc  # noqa: E402
import _t191_loot_check as lc  # noqa: E402

SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
NEIGHBOURS = [(60, 28), (59, 29), (61, 29), (60, 30)]

TILE_KEYS = ("kind", "tool", "feature", "crop", "ripe", "ready", "readySource", "harvestMethod",
             "fullyGrown", "currentPhase", "phaseDays", "dayOfCurrentPhase", "dead", "watered",
             "standable", "actionable", "plantable", "objId", "regrowsAfterHarvest")
FARM_KEYS = ("readyCrops", "ripeCrops", "crops", "dryCrops", "deadCrops", "unwateredCrops",
             "hoeDirt", "emptyDirt", "complete", "scanSeq")
RECEIPT_KEYS = ("ok", "status", "skill", "acted", "actedEvidence", "reason",
                "worldSeqBefore", "worldSeqAfter", "elapsedMs", "tool", "uiOpened")


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
    """薄代理：调用前记账 + 截获 Mod 原始回执（no_action 时客户端会抛 BridgeError）。"""

    def __init__(self, client: BridgeClient) -> None:
        self._c = client
        self.used: list[str] = []
        self.raw: dict[str, Any] = {}
        self.errors: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def _wrap(self, name: str, *a: Any, **k: Any) -> Any:
        self.used.append(name)
        try:
            r = getattr(self._c, name)(*a, **k)
        except Exception as exc:  # noqa: BLE001
            self.errors[name] = {"type": type(exc).__name__, "msg": str(exc)[:800]}
            raise
        self.raw[name] = r
        return r

    def interact(self, *a: Any, **k: Any) -> Any:
        return self._wrap("interact", *a, **k)

    def use_tool(self, *a: Any, **k: Any) -> Any:
        return self._wrap("use_tool", *a, **k)

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
    return {"exists": True, "lines": len(lines),
            "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds"),
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


def qid_totals(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        if r.get("itemId"):
            out[str(r["itemId"])] = out.get(str(r["itemId"]), 0) + int(r.get("stack") or 0)
    return out


def shipping_bin(obs: dict) -> dict:
    cands = {"obs.shippingBin": obs.get("shippingBin"),
             "location.shippingBin": (obs.get("location") or {}).get("shippingBin"),
             "farm.shippingBin": (obs.get("farm") or {}).get("shippingBin")}
    found = {k: v for k, v in cands.items() if v is not None}
    if not found:
        return {"__not_found__": True,
                "location_keys": sorted((obs.get("location") or {}).keys())[:40]}
    return found


def receipt_view(rec: dict | None) -> dict:
    if not isinstance(rec, dict):
        return {"__receipt__": None if rec is None else str(rec)[:200]}
    return {k: rec.get(k, "__KEY_MISSING__") for k in RECEIPT_KEYS}


def step_view(st: Any) -> dict:
    return {"action": getattr(st, "action", None), "tile": list(getattr(st, "tile", ()) or ()),
            "ok": getattr(st, "ok", None), "code": getattr(st, "code", None),
            "status": getattr(st, "status", None), "reason": getattr(st, "reason", None),
            "receipt": getattr(st, "receipt", None), "after": getattr(st, "after", None),
            "seconds": getattr(st, "seconds", None)}


def env_line(c: BridgeClient) -> dict:
    h = c.health()
    rt = h.get("runtime") or {}
    print(f"=== env === modVersion={h.get('modVersion')} port={h.get('port')} "
          f"hasSaveLoaded={h.get('hasSaveLoaded')} ticks={rt.get('ticks')} uptime={rt.get('uptimeSeconds')}")
    print(f"saves: {jp(save_stats())}")
    print(f"smapi: {jp(smapi_counts())}")
    base = path(os.path.join("..", "logs", "run10d-baseline.json"))
    if os.path.exists(base):
        with io.open(base, encoding="utf-8") as fh:
            b = json.load(fh)
        ob = b.get("observe") or b
        print(f"baseline: generatedAt={b.get('generatedAt')} worldSeq={ob.get('worldSeq')} "
              f"day={jp((ob.get('clock') or {}).get('day'))} season={(ob.get('clock') or {}).get('season')} "
              f"tod={(ob.get('clock') or {}).get('timeOfDay')} money={(ob.get('player') or {}).get('money')}")
    return h


# ------------------------------------------------------------------ 一条动作的通用取证
def one_action(tag: str, tile: tuple[int, int], c: BridgeClient, w: FarmWorker, proxy: Rec, fn) -> dict:
    before = c.observe("full")
    dump(f"_t191_{tag}-before.json", before)
    print(f"  before: worldSeq={before.get('worldSeq')} farm={jp(farmf(before))} "
          f"win={jp(window_counts(before))} rows={len(inv_rows(before))}")
    st = None
    err = None
    try:
        st = fn()
    except Exception as exc:  # noqa: BLE001
        err = {"type": type(exc).__name__, "msg": str(exc)[:800]}
        print(f"  !! 调用抛异常 {jp(err)}")
    after = c.observe("full")
    dump(f"_t191_{tag}-after.json", after)
    rec = proxy.action_receipt()
    dump(f"_t191_{tag}-receipt.json", rec if rec is not None else {"__receipt__": None})
    world = tc.world_diff(before, after, tile)
    brain = step_view(st) if st is not None else None
    verdict = tc.report(brain, rec, world, title=f"{tag} {tile}")
    loot = lc.report((brain or {}).get("reason"), world["loot_qid_diff"], title=f"{tag} {tile}")
    rv = receipt_view(rec)
    r1 = {"acted_present": isinstance(rec, dict) and "acted" in rec,
          "actedEvidence_present": isinstance(rec, dict) and "actedEvidence" in rec,
          "acted": rv.get("acted"), "actedEvidence": rv.get("actedEvidence"),
          "status": rv.get("status")}
    print(f"  [R1] 回执键: acted_present={r1['acted_present']} "
          f"actedEvidence_present={r1['actedEvidence_present']} acted={r1['acted']} "
          f"actedEvidence={r1['actedEvidence']} status={r1['status']}")
    print(f"  [路径] entry points used={proxy.used} errors={jp(proxy.errors)}")
    if brain is not None:
        print(f"  [脑侧] ok={brain.get('ok')} code={brain.get('code')} reason={(brain.get('reason') or '')[:300]}")
        aft = (brain.get("after") or {}) if isinstance(brain.get("after"), dict) else {}
        print(f"  [脑侧 after] loot={jp(aft.get('loot'))} affected={jp(aft.get('affected_tiles'))} "
              f"loot_whitelisted={jp(aft.get('loot_whitelisted'))} whitelist_bound={aft.get('whitelist_bound')} "
              f"tile_seen={aft.get('tile_seen')} loot_waits={aft.get('loot_waits')} "
              f"loot_unconfirmed={aft.get('loot_unconfirmed')}")
        print(f"  [常量] LOOT_CONFIRM_TRIES={LOOT_CONFIRM_TRIES} LOOT_CONFIRM_WAIT_S={LOOT_CONFIRM_WAIT_S}")
    payload = {"tag": tag, "tile": list(tile), "step": brain, "receipt": rec, "receipt_view": rv,
               "r1": r1, "world": world, "verdict": verdict, "loot_reconcile": loot,
               "entry_points_used": proxy.used, "errors": proxy.errors, "exception": err}
    dump(f"_t191_{tag}-verdict.json", payload)
    return payload


# ------------------------------------------------------------------ subcommands
def cmd_fields(c: BridgeClient, w: FarmWorker, args) -> int:
    env_line(c)
    tile = tuple(int(p) for p in args.tile.split(","))
    obs = c.observe("full")
    dump("_t191_observe-fields.json", obs)
    pl = obs.get("player") or {}
    rows = inv_rows(obs)
    print(f"worldSeq={obs.get('worldSeq')} clock={jp(obs.get('clock'))} player={pl.get('tile')} "
          f"stamina={pl.get('stamina')} money={pl.get('money')} farmingLevel={pl.get('farmingLevel')}")
    print(f"ui={jp(obs.get('ui'))} liveness={jp(obs.get('liveness'))}")
    print(f"farm: {jp(farmf(obs))}")
    print(f"window: {jp(window_counts(obs))}")
    print(f"inventory ROWS={len(rows)} (player.inventoryCount={pl.get('inventoryCount')} 是容量字段)")
    print(f"inv: {jp(rows)}")
    print(f"qid totals: {jp(qid_totals(rows))}")
    print(f"shippingBin: {jp(shipping_bin(obs))}")
    for t in [tile] + [n for n in NEIGHBOURS if n != tile]:
        tv = tvf(w, obs, t)
        print(f"  {t}: {'NOT IN WINDOW' if tv is None else jp(tv)}")
        if tv is not None and t == tile:
            print(f"     tile_ready={tile_ready(tv)} harvest_tool={harvest_tool(tv)}")
    return 0


def cmd_sell(c: BridgeClient, w: FarmWorker, args) -> int:
    before = c.observe("full")
    dump("_t191_sell-before.json", before)
    print(f"  前: rows={len(inv_rows(before))} ship={jp(shipping_bin(before))} "
          f"money={(before.get('player') or {}).get('money')} slot{args.slot}="
          f"{jp([r for r in inv_rows(before) if r['slot'] == args.slot])}")
    st = w.sell(args.slot, whitelist=[args.qid] if args.qid else None)
    after = c.observe("full")
    dump("_t191_sell-after.json", after)
    print(f"  StepResult: ok={st.ok} code={st.code} reason={st.reason}")
    print(f"  后: rows={len(inv_rows(after))} ship={jp(shipping_bin(after))} "
          f"money={(after.get('player') or {}).get('money')}")
    return 0 if st.ok else 1


def cmd_harvest(c: BridgeClient, w: FarmWorker, args) -> int:
    tile = tuple(int(p) for p in args.tile.split(","))
    proxy = Rec(c)
    w2 = FarmWorker(proxy, log=lambda *_: None)
    p = one_action(f"harvest-{tile[0]}-{tile[1]}", tile, c, w2, proxy, lambda: w2.harvest(tile))
    return 0 if ((p.get("step") or {}).get("ok") is True) else 1


def cmd_use_tool(c: BridgeClient, w: FarmWorker, args) -> int:
    tile = tuple(int(p) for p in args.tile.split(","))
    proxy = Rec(c)
    p = one_action(f"usetool-{tile[0]}-{tile[1]}", tile, c, w, proxy,
                   lambda: proxy.use_tool(tile, tool=args.tool, timeout_ms=args.timeout_ms))
    rv = p.get("r1") or {}
    print(f"  [R1 判定] 两键都在 = {bool(rv.get('acted_present') and rv.get('actedEvidence_present'))}")
    return 0 if (rv.get("acted_present") and rv.get("actedEvidence_present")) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("env")
    pf = sub.add_parser("fields")
    pf.add_argument("--tile", default="60,29")
    ps = sub.add_parser("sell")
    ps.add_argument("--slot", type=int, required=True)
    ps.add_argument("--qid", default=None)
    for name in ("harvest", "use-tool"):
        pp = sub.add_parser(name)
        pp.add_argument("--tile", required=True)
        if name == "use-tool":
            pp.add_argument("--tool", default="scythe")
            pp.add_argument("--timeout-ms", type=int, default=15000)
    args = ap.parse_args()

    c = BridgeClient()
    w = FarmWorker(c, log=lambda *_: None)
    if args.cmd == "env":
        env_line(c)
        return 0
    if args.cmd == "fields":
        return cmd_fields(c, w, args)
    if args.cmd == "sell":
        return cmd_sell(c, w, args)
    if args.cmd == "harvest":
        return cmd_harvest(c, w, args)
    if args.cmd == "use-tool":
        return cmd_use_tool(c, w, args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
