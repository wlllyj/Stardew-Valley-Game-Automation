# -*- coding: utf-8 -*-
"""task-50 调试探针（一次性，不入库）：看"窗口外干作物"用例里一天到底怎么收的尾。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_longrun import (  # noqa: E402
    DryTilesWorld, FakeClient, FakeWorker, NoWalkFarDryWorker, make_run,
)


def scenario(name, *, with_dry_tiles=True, unreachable=(), water_left=40, lying=False):
    w = DryTilesWorld(seeds=0, money=0, weeds=0, water_left=water_left,
                      with_dry_tiles=with_dry_tiles)
    far = (61, 10)
    w.dirt.add(far)
    w.crops[far] = {"watered": False, "ripe": False}
    w.player_tile = [62, 14]

    if lying:
        class _Lying(FakeWorker):
            def water(self, tile, *, timeout_ms=15000):
                from agentfarm.farmwork import StepResult
                return StepResult("water", tuple(tile), ok=True, reason="假回执 ok，世界没变")

        factory = lambda c: _Lying(w)  # noqa: E731
    elif unreachable:
        factory = lambda c: NoWalkFarDryWorker(w, unreachable=unreachable)  # noqa: E731
    else:
        factory = lambda c: FakeWorker(w)  # noqa: E731

    run = make_run(w, target_days=1, max_days=2,
                   client_factory=lambda: FakeClient(w), worker_factory=factory)
    code = run.run()
    rep = run.days[0]
    print(f"=== {name} code={code}")
    print(f"  ended_by={rep.ended_by!r} ended_reason={rep.ended_reason!r}")
    print(f"  checks={rep.checks}")
    print(f"  final_water={rep.final_water}")
    print(f"  watered_tiles={getattr(w, 'watered_tiles', None)} revealed={getattr(w, 'revealed', None)}")
    print(f"  player={w.player_tile} dry_now={sum(1 for c in w.crops.values() if not c['watered'])}")
    for e in run.entries:
        if e["event"] in ("water_far", "water_far_unavailable", "work_spot", "resume_walk",
                          "plot_exhausted", "stage_exhausted", "lifecycle", "seed_gate", "sleep"):
            print(f"   [{e['t']}] {e['event']} {({k: v for k, v in e.items() if k not in ('event', 't')})}")
    for s in rep.stages:
        print(f"   stage {s}")
    print(f"  notes={rep.notes}")


scenario("① 正常：走得到")
scenario("② 走不到", unreachable=[(61, 10)])
scenario("③ 旧 Mod 无 dryTiles", with_dry_tiles=False)
scenario("④ 回执 ok 世界不变", lying=True)
scenario("⑤ 壶空", water_left=0)
