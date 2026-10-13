"""task-40 A 补充：`_ensure_on_farm` **失败分支**（提交里没有用例覆盖的那条）是否有界、是否如实记账。

只读生产代码；用 tests/test_longrun.py 的假世界 + 一个"永远走不到农场"的 worker。
用法：python scratch/_t40_probe.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "brain"))

from agentfarm.farmwork import StepResult  # noqa: E402
from tests.test_longrun import (  # noqa: E402
    FakeClient,
    MorningIndoorWorker,
    MorningIndoorWorld,
    make_run,
)


class FailGotoWorker(MorningIndoorWorker):
    """`ensure_location` 永远失败（模拟 run3 现场"夜里回不了 FarmHouse"那类寻路失败）。"""

    def ensure_location(self, name, *, tile=None, timeout_ms=30000):
        self.w.goto_calls += 1
        return StepResult("move_to_location", ok=False, code="timeout",
                          reason=f"A* 未算出到 {name} 的路径")


w = MorningIndoorWorld(weeds=0, seeds=0, money=0)
t = (61, 10)
w.dirt.add(t)
w.crops[t] = {"watered": False, "ripe": False}
run = make_run(w, target_days=2, max_days=2,
               client_factory=lambda: FakeClient(w),
               worker_factory=lambda c: FailGotoWorker(w))
code = run.run()
print(f"code={code} goto_calls={w.goto_calls} days={len(run.days)} actions={run._actions}")
for r in run.days:
    print(f"  [{r.day_text}] ended_by={r.ended_by!r} reason={r.ended_reason!r} verified={r.verified}")
    print(f"    notes={r.notes}")
goto = [e for e in run.entries if e["event"] == "goto_farm"]
print(f"goto_farm 事件 {len(goto)} 条：ok={[e.get('ok') for e in goto]} "
      f"where={[e.get('where') for e in goto]} codes={[e.get('code') for e in goto]}")
print("stuck/keep_working 痕迹：",
      [e.get("event") for e in run.entries if e.get("event") in ("intent_vetoed", "idle", "stage_no_target")])
print("回不去 notes 命中：", [r.day_text for r in run.days if any("回不去" in n for n in r.notes)])
