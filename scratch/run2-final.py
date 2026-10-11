# -*- coding: utf-8 -*-
"""run2 结束态快照 + 与起点（logs/run2-observe-start.json）的观测差分。

只用 observe?detail=full 作为证据；回执不作证据。
输出：logs/run2-observe-end.json（原始响应）+ logs/run2-final-report.txt（人类可读）
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError, load_bridge_info, pid_alive  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
START_JSON = REPO / "logs" / "run2-observe-start.json"
END_JSON = REPO / "logs" / "run2-observe-end.json"
OUT_TXT = REPO / "logs" / "run2-final-report.txt"
SMAPI_LOG = Path(os.environ.get("APPDATA", "")) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"

OUT: list[str] = []


def p(t: str = "") -> None:
    print(t, flush=True)
    OUT.append(str(t))


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clock_key(c: dict) -> tuple:
    return (c.get("year") or 0, str(c.get("season") or ""), c.get("day") or 0)


def inv_brief(player: dict) -> list:
    out = []
    for it in (player.get("inventory") or []):
        if isinstance(it, dict):
            out.append({k: it.get(k) for k in ("name", "displayName", "count", "stack", "category", "itemId") if k in it})
        else:
            out.append(it)
    return out


def farm_brief(farm: dict) -> dict:
    if not isinstance(farm, dict):
        return {}
    keys = ("loaded", "hoeDirt", "emptyDirt", "crops", "ripeCrops", "unwateredCrops", "deadCrops",
            "weeds", "stones", "twigs", "trees", "grass", "sprinklers", "animals", "complete", "scanSeq")
    return {k: farm.get(k) for k in keys if k in farm}


def main() -> int:
    p("== run2 结束态（观测差分）==")
    p(f"取样 {stamp()}")
    try:
        info = load_bridge_info()
    except BridgeError as exc:
        p(f"[FATAL] bridge.json 读不到：{exc}")
        _flush()
        return 2
    p(f"[bridge.json] port={info.port} pid={info.pid} modVersion={info.mod_version}")
    p(f"[pid_alive] {pid_alive(info.pid)}")

    client = BridgeClient(timeout=15.0)
    try:
        h = client.health()
    except BridgeError as exc:
        p(f"[FATAL] 桥不健康：{exc}")
        _flush()
        return 2
    p(f"[health] ok={h.get('ok')} status={h.get('status')} modVersion={h.get('modVersion')} "
      f"hasSaveLoaded={h.get('hasSaveLoaded')} worldSeq={h.get('worldSeq')}")
    p(f"[health.runtime] {json.dumps(h.get('runtime'), ensure_ascii=False)}")

    end = client.observe("full")
    END_JSON.write_text(json.dumps(end, ensure_ascii=False, indent=2), encoding="utf-8")
    p(f"[saved] {END_JSON}")

    ec = end.get("clock") or {}
    ep = end.get("player") or {}
    p("")
    p("--- 结束态 ---")
    p(f"clock      : {json.dumps(ec, ensure_ascii=False)}")
    p(f"player     : name={ep.get('name')} location={ep.get('location')} tile={ep.get('tile')} "
      f"stamina={ep.get('stamina')}/{ep.get('maxStamina')} money={ep.get('money')} "
      f"inventoryCount={ep.get('inventoryCount')} isInBed={ep.get('isInBed')}")
    p(f"wateringCan: {json.dumps(ep.get('wateringCan'), ensure_ascii=False)}")
    p(f"farm       : {json.dumps(farm_brief(end.get('farm') or {}), ensure_ascii=False)}")
    p(f"inventory  : {json.dumps(inv_brief(ep), ensure_ascii=False)}")
    p(f"location   : {json.dumps(end.get('location'), ensure_ascii=False)[:600]}")

    if START_JSON.exists():
        start = json.loads(START_JSON.read_text(encoding="utf-8"))
        sc = start.get("clock") or {}
        sp = start.get("player") or {}
        sf = start.get("farm") or {}
        p("")
        p("--- 与起点（run2-observe-start.json）差分 ---")
        p(f"clock      : {clock_key(sc)} -> {clock_key(ec)}")
        p(f"money      : {sp.get('money')} -> {ep.get('money')}")
        p(f"stamina    : {sp.get('stamina')}/{sp.get('maxStamina')} -> {ep.get('stamina')}/{ep.get('maxStamina')}")
        p(f"location   : {sp.get('location')} {sp.get('tile')} -> {ep.get('location')} {ep.get('tile')}")
        p(f"waterCan   : {json.dumps((sp.get('wateringCan') or {}).get('waterLeft'), ensure_ascii=False)}"
          f" -> {json.dumps((ep.get('wateringCan') or {}).get('waterLeft'), ensure_ascii=False)}")
        ef = end.get("farm") or {}
        for k in ("crops", "unwateredCrops", "ripeCrops", "hoeDirt", "emptyDirt", "weeds", "stones", "twigs", "grass", "sprinklers"):
            if k in sf or k in ef:
                p(f"farm.{k:<15}: {sf.get(k)} -> {ef.get(k)}")
        p(f"inventory  : {json.dumps(inv_brief(sp), ensure_ascii=False)}")
        p(f"          -> {json.dumps(inv_brief(ep), ensure_ascii=False)}")
    else:
        p(f"[warn] 起点快照不存在：{START_JSON}")

    p("")
    p(f"[SMAPI] mtime={datetime.fromtimestamp(SMAPI_LOG.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S') if SMAPI_LOG.exists() else 'N/A'}")
    _flush()
    return 0


def _flush() -> None:
    try:
        OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
        OUT_TXT.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"[warn] 写 {OUT_TXT} 失败：{exc}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
