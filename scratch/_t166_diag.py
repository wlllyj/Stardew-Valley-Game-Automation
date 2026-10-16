# -*- coding: utf-8 -*-
"""task-166 诊断：B3 那个 stuck 日到底是"守卫 vs 作业区口径"还是别的东西。"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("T166_ROOT") or pathlib.Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "brain"))
sys.path.insert(0, str(ROOT / "tests"))

from agentfarm import longrun as LR  # noqa: E402
import test_longrun as TL  # noqa: E402

MICRO = [(60 + x, 10 + y) for x in range(5) for y in range(5)]
WINDOW = [t for t in MICRO if abs(t[0] - 62) + abs(t[1] - 14) <= 3]

w = TL.DryTilesWorld(weeds=10, seeds=20, money=0, water_left=40, stamina=200)
w.player_tile = [62, 14]
w.dirt = set(MICRO)
w.crops = {}
for t in list(WINDOW)[:5]:
    w.crops[t] = {"watered": True, "ripe": False, "dead": False}
obs = w.obs()
run = TL.make_run(w, target_days=1, max_days=1,
                  client_factory=lambda: TL.FakeClient(w),
                  worker_factory=lambda c: TL.FakeWorker(w, log=lambda *a: None))

print("tillable n=", len(w.tillable if isinstance(w.tillable, (set, list)) else []))
print("dirt n=", len(w.dirt), "crops n=", len(w.crops))
try:
    print("blockers=", dict(list(getattr(w, "blockers", {}).items())[:12]))
except Exception as exc:
    print("blockers?", exc)
print("farm_plot_work:", run._farm_plot_work(obs))
b = run._stamina_budget(obs)
print("budget:", json.dumps({k: v for k, v in b.items() if k != "deferred"}, ensure_ascii=False))
run.budget_today = b
for task in ("clear_area", "till_area", "plant_area", "water_area", "harvest", "clear_dead"):
    try:
        why = run._budget_defer_reason(task, obs)
    except Exception as exc:
        why = f"<{exc}>"
    try:
        scan = run._deferred_scan(task, obs)[:10]
    except Exception as exc:
        scan = f"<{exc}>"
    print(f"  {task:11s} defer_reason={why!r:60s} deferred_scan={scan}")
plot = None
try:
    plot = LR.plot_observe(obs)
except Exception as exc:
    print("plot_observe exc:", exc)
print("plot:", json.dumps(plot, ensure_ascii=False)[:600] if plot else None)
if plot:
    for task in ("clear_area", "till_area", "plant_area", "water_area"):
        try:
            tiles = run._stage_tiles(task, obs, plot)
        except Exception as exc:
            tiles = f"<{exc}>"
        print(f"  stage_tiles {task:11s} = {tiles[:10] if isinstance(tiles, list) else tiles}")
print("work_reasons:", run.work_reasons(obs))
print("pending_work:", run._pending_work())
