"""task-218 离线复现：带树快照证明 (a) 树成目标且不再说"没活" (b) 预算挡下可执行、不进 hard failure。

只读本地假世界（不碰游戏/桥/存档）。用法：`python scratch/_t218_replay.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))
sys.path.insert(0, str(REPO / "tests"))

from agentfarm.farmwork import FarmWorker  # noqa: E402
from agentfarm.longrun import (CLEARABLE_KINDS, TREE_CLEAR_MAX_PER_DAY,  # noqa: E402
                               LongRun)
from test_longrun import FakeClient, FakeWorld, make_run  # noqa: E402


def build(world: FakeWorld) -> tuple[LongRun, dict]:
    client = FakeClient(world)
    worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
    run = make_run(world, client_factory=lambda: client, worker_factory=lambda c: worker)
    run.worker = worker
    run.client = client
    plot = {"zone": "field_se", "label": "field_se",
            "anchor": [60, 10], "tiles": [[60, 10], [61, 10]]}
    return run, plot


def main() -> int:
    print("== A：田里有一棵树（0 级斧可砍） ==")
    w = FakeWorld(weeds=0, seeds=10, money=500)
    w.blockers[(60, 10)] = "tree"
    run, plot = build(w)
    obs = w.obs()
    tiles = run._stage_tiles("clear_area", obs, plot)
    has_work = run._plot_has_work(obs, [tuple(t) for t in plot["tiles"]])
    brief = run._plot_brief(obs, plot)
    print(f"  CLEARABLE_KINDS 含 tree: {'tree' in CLEARABLE_KINDS}")
    print(f"  clear_area 目标池: {sorted(tiles)}")
    print(f"  _plot_has_work（旧实现=False，因为树被静默跳过）: {has_work}")
    print(f"  简报 counts: trees={brief.counts.get('trees')} blockers={brief.counts.get('blockers')}")
    print(f"  简报里 tree 有公告/计数: {'tree' in brief.situation_text() or brief.counts.get('trees')}")

    print("\n== B：树日预算用满（TREE_CLEAR_MAX_PER_DAY=2） ==")
    run.trees_cleared_today = TREE_CLEAR_MAX_PER_DAY
    obs = w.obs()
    tiles2 = run._stage_tiles("clear_area", obs, plot)
    leftover = run._leftover("clear_area", obs, plot)
    reasons = run.work_reasons(obs)
    allow, code, text = run.sleep_guard(obs)
    budget_events = [e for e in run.entries if e.get("event") == "deferred_by_budget"]
    print(f"  预算用满后 clear_area 目标池（不应含树）: {sorted(tiles2)}")
    print(f"  _leftover（预算挡下的树不算 leftover ⇒ 不进 unmet/hard failure）: {sorted(leftover)}")
    print(f"  work_reasons 里还提树吗: {any('树' in r for r in reasons)} / reasons={reasons}")
    print(f"  deferred_by_budget 留痕: {[(e.get('task'), e.get('note', '')[:24]) for e in budget_events]}")
    print(f"  sleep_guard: allow={allow} code={code} text={text[:40]}")

    print("\n== C：预算用满 + 没有别的活（没钱/没种子） ⇒ 收工理由如实、不是 hard failure ==")
    w3 = FakeWorld(weeds=0, seeds=0, money=0)
    w3.blockers[(60, 10)] = "tree"
    run3, plot3 = build(w3)
    run3.trees_cleared_today = TREE_CLEAR_MAX_PER_DAY
    obs3 = w3.obs()
    allow3, code3, text3 = run3.sleep_guard(obs3)
    print(f"  work_reasons: {run3.work_reasons(obs3)}")
    print(f"  sleep_guard: allow={allow3} code={code3} text={text3[:60]}")
    print(f"  deferred_by_budget: {[e.get('task') for e in run3.entries if e.get('event') == 'deferred_by_budget']}")

    print("\n结论：树在有预算时是**可执行目标**（不再是静默跳过）；预算挡下时是"
          "**被记录的延后**（既有事件加字段、非 hard failure、不会让守卫空转）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
