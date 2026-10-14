# -*- coding: utf-8 -*-
r"""task-77 对抗实验 A：encircled 分类 / frontier_clear / 当日重试（只读生产代码，跑在干净快照 8ceea87 上）。

用法：$env:PYTHONUTF8="1"; python scratch\_t77_a.py
快照目录：scratch\_t77_snap（git archive 8ceea87 解出，避免工作树里 task-73 的在制改动干扰）。
"""
from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_t77_snap")
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "brain"))
sys.path.insert(0, ROOT)


def load(name: str, rel: str):
    path = os.path.join(ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fw = load("t_fw", os.path.join("tests", "test_farmwork.py"))
lr = load("t_lr", os.path.join("tests", "test_longrun.py"))

from agentfarm.farmwork import NEIGHBORS, FarmWorker  # noqa: E402
from agentfarm.longrun import FRONTIER_CLEAR_MAX, DayReport  # noqa: E402


def p(label, value):
    print(f"  {label}: {value}")


def rec(tile, kind, standable, **extra):
    d = {"tile": [int(tile[0]), int(tile[1])], "kind": kind, "standable": bool(standable),
         "actionable": True}
    d.update(extra)
    return d


print("=" * 78)
print("P1a 四邻全是【可清障的杂草】但观测说站不过去 ⇒ 判 encircled？（1 层启发式的边界）")
print("=" * 78)
T = (62, 10)
block = [(x, y) for x in range(60, 65) for y in range(8, 13)]
recs = [rec(t, "weed", False) for t in block]
w = fw.MiniWorld(records=recs, inventory=fw.INV_WITH_SCYTHE, tools=fw.TOOLS_WITH_SCYTHE)
w.player_tile = [60, 15]          # 玩家在块外；块内全观测为 standable=false
w.unwalkable = set(block)
r = fw.make_worker(w).clear(T)
print(f"  code={r.code!r} ok={r.ok} stood={r.stood}")
p("reason", r.reason)
p("cleared/opened", r.opened)
p("use_tool 调用次数", len(w.calls))
p("4 邻 kind", [rec((T[0] + dx, T[1] + dy), "weed", False)["kind"] for dx, dy in NEIGHBORS])
print("  ⇒ 判定解释：四邻都是 weed（FRONTIER_KINDS，可清），但观测把它们标 standable=false，"
      "且它们各自的四邻也全被观测为不可站 ⇒ `_openable_neighbours` 空 ⇒ `_standable_near(T)` 假 "
      "⇒ 归 encircled（**没挥一次工具**）。")

print()
print("=" * 78)
print("P1b 对照组：只记录 1 个可清邻格、其余未观测 ⇒ 上限内清不掉也应归 unreachable（不是 encircled）")
print("=" * 78)
nb = [(T[0] + dx, T[1] + dy) for dx, dy in NEIGHBORS]
w2 = fw.MiniWorld(records=[fw.weed_rec(T), fw.weed_rec(nb[0])],
                  inventory=fw.INV_WITH_SCYTHE, tools=fw.TOOLS_WITH_SCYTHE)
w2.player_tile = [60, 15]
w2.unwalkable = {nb[0]}                 # 邻格走不过去 ⇒ 清不动
w2.fail_status[nb[0]] = "tool_ineffective"   # 游戏拒绝清这一格（"干得动但今天没干成"的形态）
r2 = fw.make_worker(w2).clear(T)
p("code", r2.code)
p("unreachable/failed/encircled", (r2.unreachable, r2.failed, r2.encircled))
p("reason", r2.reason)

print()
print("=" * 78)
print("P2a 假世界跑完整一天（目标格被树围住）⇒ 当天能不能拿到 verified？encircled 进不进 blocked？")
print("=" * 78)
ENCLOSED = (62, 12)
w3 = lr.EncircledWorld(enclosed=[ENCLOSED], seeds=0, money=0)
client3 = lr._UnreachableClient(w3, unreachable=getattr(w3, "enclosed", ()))
worker3 = FarmWorker(client3, log=lambda *_: None, pause=lambda _s: None)
run3 = lr.make_run(w3, client_factory=lambda: client3, worker_factory=lambda c: worker3,
                   target_days=1, max_days=1)
run3.worker = worker3
run3.client = client3
run3.run()
rep3 = run3.days[0]
p("ended_by / reason", (rep3.ended_by, str(rep3.ended_reason)[:90]))
p("checks", rep3.checks)
p("verified", rep3.verified)
p("ok_steps / failed_steps", (rep3.ok_steps, rep3.failed_steps))
p("unreachable / encircled / exempt", (rep3.unreachable, rep3.encircled, rep3.unreachable_exempt))
p("attempted / engaged / bound", (rep3.unreachable_bound,
                                  [(s.get("attempted"), s.get("engaged"), s.get("leftover"),
                                    s.get("encircled"), s.get("unreachable")) for s in rep3.stages]))
p("encircled 格进 blocked 了吗", (tuple(ENCLOSED) in run3.blocked, run3.blocked.get(tuple(ENCLOSED))))
p("encircled 事件数", len([e for e in run3.entries if e.get("event") == "encircled"]))
p("day_end.encircled(_tiles)", [ (e.get("encircled"), e.get("encircled_tiles"))
                                 for e in run3.entries if e.get("event") == "day_end"])
print("  ⇒ 关键：`no_unmet_stages` 是否因为 encircled 格留在 leftover 里而为 False。")

print()
print("=" * 78)
print("P2b 次日会不会重试（encircled 不许永久封格）")
print("=" * 78)
w4 = lr.EncircledWorld(enclosed=[ENCLOSED], seeds=0, money=0)
client4 = lr._UnreachableClient(w4, unreachable=getattr(w4, "enclosed", ()))
worker4 = FarmWorker(client4, log=lambda *_: None, pause=lambda _s: None)
run4 = lr.make_run(w4, client_factory=lambda: client4, worker_factory=lambda c: worker4,
                   target_days=2, max_days=4)
run4.worker = worker4
run4.client = client4
run4.run()
starts = [e for e in run4.entries if e.get("event") == "day_start"]
encs = [e for e in run4.entries if e.get("event") == "encircled"]
p("跑了几天", len(run4.days))
p("encircled 事件总数 / 涉及天数", (len(encs), len({tuple(e.get("day", [])) for e in encs})))
for d in run4.days:
    p("day", (d.day_text, d.ended_by, d.encircled, d.checks.get("no_unmet_stages"), d.verified))
p("末态 blocked", run4.blocked)
p("encircled_day 末值", sorted(run4.encircled_day))

print()
print("=" * 78)
print("P2c 零动作防线：目标够不着 + 有可达可清障格 ⇒ frontier_clear 必须真清一格")
print("=" * 78)
w5 = lr.UnreachableWorld(unreachable=[(60, 10)], seeds=0, money=0)
w5.blockers[(70, 10)] = "weed"
w5.fail_status[(60, 10)] = "ui_modal"
client5 = lr._UnreachableClient(w5, unreachable=w5.unreachable)
worker5 = FarmWorker(client5, log=lambda *_: None, pause=lambda _s: None)
run5 = lr.make_run(w5, client_factory=lambda: client5, worker_factory=lambda c: worker5,
                   target_days=1, max_days=1)
run5.worker = worker5
run5.client = client5
run5._ensure_plot = lambda obs, rep: {"zone": "", "label": "", "anchor": [62, 12],
                                      "tiles": [(60, 10)], "note": ""}
run5.run()
ev5 = [e for e in run5.entries if e.get("event") == "frontier_clear"]
p("frontier_clear 事件", [(e.get("tile"), e.get("acted"), e.get("attempt")) for e in ev5])
p("weed 还在吗", (70, 10) in w5.blockers)
p("ok_steps / ended_by", (run5.days[0].ok_steps, run5.days[0].ended_by))
p("上限常量", FRONTIER_CLEAR_MAX)

print()
print("=" * 78)
print("P2d 零动作路径（诚实收尾）：整个农场没有任何可达可清障格 ⇒ 允许 0 动作，但必须不是 VERIFIED")
print("=" * 78)
w6 = lr.UnreachableWorld(unreachable=[(60, 10)], seeds=0, money=0)
w6.fail_status[(60, 10)] = "ui_modal"
client6 = lr._UnreachableClient(w6, unreachable=w6.unreachable)
worker6 = FarmWorker(client6, log=lambda *_: None, pause=lambda _s: None)
run6 = lr.make_run(w6, client_factory=lambda: client6, worker_factory=lambda c: worker6,
                   target_days=1, max_days=1)
run6.worker = worker6
run6.client = client6
run6._ensure_plot = lambda obs, rep: {"zone": "", "label": "", "anchor": [62, 12],
                                      "tiles": [(60, 10)], "note": ""}
run6.run()
rep6 = run6.days[0]
p("frontier_clear 事件数", len([e for e in run6.entries if e.get("event") == "frontier_clear"]))
p("ok_steps / ended_by", (rep6.ok_steps, rep6.ended_by))
p("reason", str(rep6.ended_reason)[:110])
p("checks.no_unmet_stages / verified", (rep6.checks.get("no_unmet_stages"), rep6.verified))
print("  ⇒ 这条路径允许 0 动作（诚实），但 `no_unmet_stages=False`/`verified=False` 必须成立。")
print()
print("ALL PROBES DONE")
