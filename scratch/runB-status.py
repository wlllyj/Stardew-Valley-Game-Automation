# -*- coding: utf-8 -*-
"""run B 进行中只读状态（task-169 harvest 反复失败现场）：
两份 `observe?detail=full`（相隔 ~20 秒）→ 时钟/世界推进/体力钱/农场计数 + 目标格 [60,29] 与其四邻的原始 tile 记录
+ 用两次读数算 worldSeq / timeOfDay / secondsSinceClockMoved / 账本行数的增量（判断"在推进"还是"原地打转"）。
不改任何参数、不碰游戏状态；产出 JSON 落 scratch\\runB-0732-status-<ts>.json。
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402

JOURNAL = os.path.join(ROOT, "logs", "longrun-runB-0732.jsonl")
TARGETS = [(60, 29), (59, 29), (61, 29), (60, 28), (60, 30)]


def journal_lines() -> int:
    try:
        with open(JOURNAL, "rb") as fh:
            return sum(1 for _ in fh)
    except Exception:  # noqa: BLE001
        return -1


def pick(o: dict, *keys, default=None):
    cur = o
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def summarize(o: dict, tag: str) -> None:
    print(f"--- 观测 {tag} @ {time.strftime('%H:%M:%S')} ---")
    print(f"  clock                = {json.dumps(o.get('clock'), ensure_ascii=False)}")
    print(f"  liveness             = {json.dumps(o.get('liveness'), ensure_ascii=False)}")
    print(f"  game                 = {json.dumps(o.get('game'), ensure_ascii=False)}")
    print(f"  ui.activeMenu/isModal= {pick(o,'ui','activeMenu')} / {pick(o,'ui','isModal')} / "
          f"q={pick(o,'ui','dialogueIsQuestion')} professions={pick(o,'ui','professionsToChoose')}")
    print(f"  player               = name={pick(o,'player','name')} loc={pick(o,'player','location')} tile={pick(o,'player','tile')} "
          f"stamina={pick(o,'player','stamina')} money={pick(o,'player','money')} isInBed={pick(o,'player','isInBed')} "
          f"farmingLevel={pick(o,'player','farmingLevel')} waterLeft={pick(o,'player','wateringCan','waterLeft')}")
    farm = o.get("farm") or {}
    keep = {k: farm.get(k) for k in ("crops", "ripeCrops", "unwateredCrops", "dryCrops", "deadCrops", "dryDeadCrops",
                                     "hoeDirt", "emptyDirt", "weeds", "stones", "twigs", "trees", "grass",
                                     "complete", "scanSeq")}
    print(f"  farm                 = {json.dumps(keep, ensure_ascii=False)}")
    loc = o.get("location") or {}
    tiles = loc.get("tiles") or []
    idx = {}
    for t in tiles:
        tv = t.get("tile")
        if isinstance(tv, list) and len(tv) == 2:
            idx[(tv[0], tv[1])] = t
    print(f"  location             = name={loc.get('name')} isOutdoorFarm={loc.get('isOutdoorFarm')} tiles={len(tiles)}")
    for tt in TARGETS:
        rec = idx.get(tt)
        mark = "在窗口内" if rec is not None else "**不在窗口内**"
        print(f"    tile {list(tt)} {mark}：{json.dumps(rec, ensure_ascii=False) if rec is not None else '—'}")
    print(f"  worldSeq={o.get('worldSeq')} journal_lines={journal_lines()} "
          f"save_main_size={os.path.getsize(os.path.join(ROOT,'logs','..','logs')) if False else ''}")


def main() -> int:
    c = BridgeClient()
    a = c.observe("full")
    summarize(a, "A")
    time.sleep(20)
    b = c.observe("full")
    summarize(b, "B")

    print("\n--- 两次读数增量（判断推进 / 打转）---")
    d_seq = (b.get("worldSeq") or 0) - (a.get("worldSeq") or 0)
    ta, tb = pick(a, "clock", "timeOfDay"), pick(b, "clock", "timeOfDay")
    print(f"  worldSeq        {a.get('worldSeq')} → {b.get('worldSeq')}（Δ={d_seq}）")
    print(f"  clock.timeOfDay {ta} → {tb}（Δ={None if None in (ta, tb) else tb - ta}，20 秒墙钟）")
    print(f"  worldAdvancing  {pick(a,'liveness','worldAdvancing')} → {pick(b,'liveness','worldAdvancing')}")
    print(f"  secondsSinceClockMoved {pick(a,'liveness','secondsSinceClockMoved')} → {pick(b,'liveness','secondsSinceClockMoved')}")
    print(f"  player.tile     {pick(a,'player','tile')} → {pick(b,'player','tile')}")
    print(f"  player.stamina  {pick(a,'player','stamina')} → {pick(b,'player','stamina')}")
    print(f"  farm.crops      {pick(a,'farm','crops')} → {pick(b,'farm','crops')}；farm.dryCrops {pick(a,'farm','dryCrops')} → {pick(b,'farm','dryCrops')}")

    out = os.path.join(ROOT, "scratch", f"runB-0732-status-{time.strftime('%H%M%S')}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "observe_a": a, "observe_b": b,
                   "delta": {"worldSeq": d_seq, "timeOfDay": None if None in (ta, tb) else tb - ta}}, fh, ensure_ascii=False)
    print(f"\n原始两份观测已落 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
