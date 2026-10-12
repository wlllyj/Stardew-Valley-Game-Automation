# -*- coding: utf-8 -*-
"""临时探针（task-15）：看清 262 基线里那几条"一天达标"用例现在为什么多跑了一天。"""
import sys

REPO = r"D:\Deepseek Harness Workspace\星露谷游戏自动化"
sys.path.insert(0, REPO)
sys.path.insert(0, REPO + r"\brain")

from tests.test_longrun import FakeWorld, make_run  # noqa: E402


def show(title, w, **kw):
    run = make_run(w, **kw)
    code = run.run()
    print("=" * 70)
    print(title, "-> code", code, "days", len(run.days))
    for i, d in enumerate(run.days):
        print(f"  day{i} {d.day_text} ended_by={d.ended_by!r} reason={d.ended_reason!r}")
        print(f"    checks={d.checks}")
        for s in d.stages:
            print(f"    stage={s}")
        print(f"    final={d.final}")
        print(f"    notes={d.notes}")


show("默认世界（weeds=4/seeds=10/money=500）", FakeWorld(weeds=4, seeds=10, money=500), target_days=1)
_w2 = FakeWorld(weeds=0, seeds=0, money=0)
_w2.dirt = {(60, 10)}
show("没种子没钱 + 一格 dirt", _w2, target_days=1)
