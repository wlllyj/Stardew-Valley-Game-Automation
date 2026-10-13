# -*- coding: utf-8 -*-
"""run5 状态只读打印（不写游戏状态）：clock / location / money / 背包 / farm / ui。

用法：python scratch\\run5-state.py --label 睡前
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brain")))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="")
    ap.add_argument("--detail", default="full")
    args = ap.parse_args()

    try:
        h = BridgeClient().health()
    except BridgeError as exc:
        print(f"[{args.label}] 桥不可达：{exc}")
        return 2
    print(f"[{args.label}] modVersion={h.get('modVersion')} hasSaveLoaded={h.get('hasSaveLoaded')}")

    obs = BridgeClient().observe(detail=args.detail)
    p = obs.get("player") or {}
    loc = obs.get("location") or {}
    farm = obs.get("farm") or {}
    clk = obs.get("clock") or {}
    ui = obs.get("ui") or {}
    live = obs.get("liveness") or {}
    print(f"  clock={clk.get('year')}/{clk.get('season')}/{clk.get('day')} tod={clk.get('timeOfDay')} weather={clk.get('weather')}")
    print(f"  location={loc.get('name')} outdoor={loc.get('isOutdoorFarm')} tile={p.get('tile')} "
          f"isInBed={p.get('isInBed')} stamina={p.get('stamina')}/{p.get('maxStamina')} money={p.get('money')}")
    inv = p.get("inventory") or []
    print(f"  背包 {len(inv)} 格：")
    for it in inv:
        print(f"     slot={it.get('slot')} qid={it.get('qid')} name={it.get('name')} stack={it.get('stack')}")
    print(f"  wateringCan={p.get('wateringCan')}")
    print(f"  farm: crops={farm.get('crops')} dry={farm.get('dryCrops')} unwatered={farm.get('unwateredCrops')} "
          f"ripe={farm.get('ripeCrops')} hoeDirt={farm.get('hoeDirt')} complete={farm.get('complete')} scanSeq={farm.get('scanSeq')}")
    print(f"  ui={json.dumps(ui, ensure_ascii=False)[:200]}")
    print(f"  liveness={json.dumps(live, ensure_ascii=False)[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
