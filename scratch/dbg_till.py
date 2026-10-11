# -*- coding: utf-8 -*-
"""一次性排查：为什么 `till_area` 拿到 0 个目标（跑完即弃）。

用法：python scratch\\dbg_till.py scratch\\obs-full.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.farmwork import FarmWorker  # noqa: E402
from agentfarm.longrun import LongRun, _till_blocked_by, plot_observe  # noqa: E402


def main() -> int:
    obs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    run = LongRun(client_factory=lambda: None, log=lambda _s: None)
    run.worker = None

    tillable = FarmWorker.tillable_of(obs)
    tmap = FarmWorker.tiles_of(obs)
    print(f"tillable_of={len(tillable)}  tiles_of={len(tmap)}  玩家={FarmWorker.player_tile(obs)}")

    for cand in run._plot_candidates(obs):
        tiles = [tuple(t) for t in cand["tiles"]]
        pool = run._stage_tiles("till_area", obs, cand)
        local = plot_observe(obs, tiles)
        ltill = FarmWorker.tillable_of(local)
        reasons = {t: _till_blocked_by(tmap.get(t)) for t in tiles if t in tillable}
        blocked = {t: r for t, r in reasons.items() if r}
        print(f"\n田区={cand.get('zone')} 锚点={cand.get('anchor')} 格数={len(tiles)} "
              f"本地可锄={len(ltill)} 全局可锄∩= {len([t for t in tiles if t in tillable])} "
              f"被 _till_blocked_by 挡住={blocked}")
        print(f"  _stage_tiles(till_area) = {pool}")
        print(f"  _leftover(till_area)    = {run._leftover('till_area', obs, cand)}")
        print(f"  _stage_tiles(plant)     = {run._stage_tiles('plant_area', obs, cand)}")
        print(f"  _stage_tiles(clear)     = {run._stage_tiles('clear_area', obs, cand)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
