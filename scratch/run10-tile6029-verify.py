# -*- coding: utf-8 -*-
"""task-173：0.7.33 装机后对固定样本 `(60,29)` 做**一次** harvest 定点取证。

- 前置：玩家要站在样本附近（脚本要求 `[60,29]` 出现在 `observe?detail=full` 的窗口里，
  否则打印提示并 exit 3 —— 窗口是玩家中心的 400 格）。
- 只做一次 `FarmWorker.harvest((60,29))`；前后各取一份 full 观测；逐字段差分。
- 回执原文（Mod 的 `status`/`acted`/`ok`/`reason`）通过代理客户端原样截获。
- 只读 + 一次 harvest；不写任何游戏状态文件。
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
from agentfarm.farmwork import (  # noqa: E402
    FarmWorker,
    _ready_note,
    harvest_tool,
    tile_ready,
)

TILE = (60, 29)
NEIGHBOURS = [(60, 28), (59, 29), (61, 29), (60, 30)]
SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SAVE_MAIN = os.path.join(SAVE_DIR, "Wahaha_450799035")
SAVE_INFO = os.path.join(SAVE_DIR, "SaveGameInfo")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
OUT_BEFORE = os.path.join(ROOT, "scratch", "run10-tile6029-before.json")
OUT_AFTER = os.path.join(ROOT, "scratch", "run10-tile6029-after.json")

TILE_KEYS = ("kind", "tool", "feature", "crop", "ripe", "ready", "fullyGrown", "harvestMethod",
             "currentPhase", "phaseDays", "dayOfCurrentPhase", "dead", "watered", "standable",
             "actionable", "plantable", "objId")
FARM_KEYS = ("readyCrops", "ripeCrops", "crops", "dryCrops", "deadCrops", "unwateredCrops",
             "hoeDirt", "emptyDirt", "complete", "scanSeq")


class Rec:
    """薄代理：拦截 interact/use_tool 的**原始回执**，其余属性直通。"""

    def __init__(self, client: BridgeClient) -> None:
        self._c = client
        self.raw: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def interact(self, *a: Any, **k: Any) -> Any:
        r = self._c.interact(*a, **k)
        self.raw["interact"] = r
        return r

    def use_tool(self, *a: Any, **k: Any) -> Any:
        r = self._c.use_tool(*a, **k)
        self.raw["use_tool"] = r
        return r


def jprint(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def stat_of(path: str) -> dict[str, Any]:
    try:
        st = os.stat(path)
    except OSError as exc:
        return {"path": path, "error": type(exc).__name__}
    return {
        "path": os.path.basename(path),
        "size": st.st_size,
        "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds"),
    }


def smapi_stats() -> dict[str, Any]:
    out: dict[str, Any] = {"exists": os.path.exists(SMAPI)}
    if not out["exists"]:
        return out
    with io.open(SMAPI, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    newday = 0
    called = 0
    called_raw = 0
    for ln in lines:
        if "Synchronizing 'NewDay' task" in ln:
            newday += 1
        if "SaveGame.Save() called." in ln:
            called_raw += 1
            # L16 假阳性判别式（task-140）：有 [HH:MM:SS LVL CHAN] 前缀且不含插件描述标记
            has_prefix = len(ln) > 1 and ln[0] == "[" and "]" in ln[:30]
            plugin = (" by AgentFarm " in ln) or ("| v0." in ln)
            if has_prefix and not plugin:
                called += 1
    st = os.stat(SMAPI)
    out.update({
        "lines": len(lines),
        "size": st.st_size,
        "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds"),
        "newday": newday,
        "save_called_raw": called_raw,
        "save_called_corrected": called,
    })
    return out


def tv_fields(w: FarmWorker, obs: dict[str, Any], tile: tuple[int, int]) -> dict[str, Any]:
    tv = w.tile_view(obs, tile)
    if tv is None:
        return {"__missing__": True}
    return {k: tv.get(k, "__缺失__") for k in TILE_KEYS}


def farm_fields(obs: dict[str, Any]) -> dict[str, Any]:
    farm = ((obs.get("location") or {}).get("farm")) or obs.get("farm") or {}
    return {k: farm.get(k, "__缺失__") for k in FARM_KEYS}


def main() -> int:
    c = BridgeClient()
    proxy = Rec(c)
    w = FarmWorker(proxy, log=lambda *_: None)
    h = c.health()
    print("=== [0] 环境 ===")
    print(f"health: modVersion={h.get('modVersion')} port={h.get('port')} "
          f"hasSaveLoaded={h.get('hasSaveLoaded')} runtime={jprint(h.get('runtime'))}")

    obs0 = c.observe("full")
    ui = obs0.get("ui") or {}
    pl = obs0.get("player") or {}
    print(f"clock={jprint(obs0.get('clock'))} ui={jprint({k: ui.get(k) for k in ('activeMenu','isModal','eventUp','professionsToChoose')})}")
    print(f"player tile={pl.get('tile')} stamina={pl.get('stamina')} money={pl.get('money')} farmingLevel={pl.get('farmingLevel')}")

    if tv_fields(w, obs0, TILE).get("__missing__"):
        print(f"❌ [60,29] 不在观测窗口内（玩家在 {pl.get('tile')}）⇒ 先走到样本附近再跑本脚本")
        return 3

    with io.open(OUT_BEFORE, "w", encoding="utf-8") as fh:
        json.dump(obs0, fh, ensure_ascii=False, indent=1)
    print(f"\n=== [1] 动手前基线（{OUT_BEFORE}）===")
    print(f"farm: {jprint(farm_fields(obs0))}")
    inv0 = w._inventory_counts(w.player_of(obs0))
    print(f"背包: {jprint(inv0)}")
    for t in [TILE] + NEIGHBOURS:
        print(f"  {t}: {jprint(tv_fields(w, obs0, t))}")
    tv0 = w.tile_view(obs0, TILE)
    print(f"  tile_ready([60,29])={tile_ready(tv0)}  ready_note={_ready_note(tv0)!r}  harvest_tool={harvest_tool(tv0)!r}")
    save0 = {"main": stat_of(SAVE_MAIN), "info": stat_of(SAVE_INFO)}
    smapi0 = smapi_stats()
    print(f"存档: {jprint(save0)}")
    print(f"SMAPI: {jprint(smapi0)}")

    print("\n=== [2] 只做一次 harvest((60,29)) ===")
    t0 = time.time()
    r = w.harvest(TILE)
    elapsed = time.time() - t0
    print(f"StepResult: action={r.action} tile={r.tile} ok={r.ok} code={r.code} "
          f"status={r.status!r} proven_inert={r.proven_inert} env_block={r.env_block} "
          f"inconclusive={r.inconclusive} 用时={elapsed:.1f}s")
    print(f"reason = {r.reason}")
    print(f"receipt = {r.receipt}")
    print(f"before  = {jprint(r.before)}")
    print(f"after   = {jprint(r.after)}")
    print(f"原始回执 = {jprint(proxy.raw)}")

    time.sleep(2.0)
    obs1 = c.observe("full")
    with io.open(OUT_AFTER, "w", encoding="utf-8") as fh:
        json.dump(obs1, fh, ensure_ascii=False, indent=1)
    print(f"\n=== [3] 动手后观测（{OUT_AFTER}）===")
    print(f"farm: {jprint(farm_fields(obs1))}")
    inv1 = w._inventory_counts(w.player_of(obs1))
    print(f"背包: {jprint(inv1)}")
    for t in [TILE] + NEIGHBOURS:
        print(f"  {t}: {jprint(tv_fields(w, obs1, t))}")

    print("\n=== [4] 逐字段差分 ===")
    f0, f1 = farm_fields(obs0), farm_fields(obs1)
    for k in FARM_KEYS:
        mark = "  <== 变化" if f0[k] != f1[k] else ""
        print(f"farm.{k:16} {f0[k]!r:>12} → {f1[k]!r}{mark}")
    tf0, tf1 = tv_fields(w, obs0, TILE), tv_fields(w, obs1, TILE)
    for k in TILE_KEYS:
        mark = "  <== 变化" if tf0[k] != tf1[k] else ""
        print(f"[60,29].{k:18} {tf0[k]!r:>18} → {tf1[k]!r}{mark}")
    gained = {k: v for k, v in inv1.items() if v != inv0.get(k)}
    print(f"背包差分: {jprint(gained)}（也可看 w._loot_delta: {jprint(w._loot_delta(inv0, inv1))}）")

    save1 = {"main": stat_of(SAVE_MAIN), "info": stat_of(SAVE_INFO)}
    smapi1 = smapi_stats()
    print("\n=== [5] 存档与 SMAPI 增量 ===")
    print(f"存档: {jprint(save1)}")
    print(f"SMAPI: {jprint(smapi1)}")
    print(f"Δsmapi lines {smapi1.get('lines', 0) - smapi0.get('lines', 0)} / "
          f"lines_newday {smapi0.get('newday')}→{smapi1.get('newday')} / "
          f"save_called(corrected) {smapi0.get('save_called_corrected')}→{smapi1.get('save_called_corrected')}")

    print("\n=== 判据对照（脚本只报读数，结论由文档判） ===")
    print(f"(a) 真摘到? readyCrops {f0.get('readyCrops')}→{f1.get('readyCrops')} ; "
          f"[60,29].crop {tf0.get('crop')!r}→{tf1.get('crop')!r} ; "
          f"r.ok={r.ok} r.code={r.code} r.status={r.status!r}")
    print(f"(b) 判据纠正? readyCrops={f1.get('readyCrops')} ; [60,29].ready={tf1.get('ready')!r} ; "
          f"tile_ready={tile_ready(w.tile_view(obs1, TILE))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
