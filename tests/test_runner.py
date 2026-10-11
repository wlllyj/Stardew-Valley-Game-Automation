# -*- coding: utf-8 -*-
"""监督循环（`brain\\agentfarm\\runner.py`）的离线单元测试。

原则与 `test_watchdog.py` 一致：**不连游戏、不发网络请求** —— 用鸭子类型的假 client，
把"时钟/睡眠"也注入进去，于是整个循环可以在毫秒级跑完并断言每个分支。

覆盖点（对应无人值守最怕的几件事）：
  1. 一切正常时**跑满时长/次数**并正常退出（不能自己把自己停掉）；
  2. `watchdog` 判 stop 时：**必须落事故报告**（人不在，屏幕上说什么都没用）并退出码 2；
  3. `on_stop=quit` 时真的去调 `quit_game`（让游戏自己退，不留半死不活的进程）；
  4. **连不上桥 = stop**（游戏可能崩了；继续等只是浪费时间），报告里要有 `bridge_unreachable`；
  5. 取数抛**任何**异常都不许把循环带崩。

运行：`python -m unittest discover -s tests -v`
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import BridgeError  # noqa: E402
from agentfarm.runner import (  # noqa: E402
    ON_STOP_NOTHING,
    ON_STOP_QUIT,
    ON_STOP_REPORT,
    SupervisedRunner,
)


def healthy_health() -> dict:
    return {
        "ok": True, "status": "ok", "modVersion": "0.7.3",
        "game": {"version": "1.6.15", "smapi": "4.5.2", "windowActive": True,
                 "pauseWhenOutOfFocus": False, "oofFixCount": 2},
        "runtime": {"ticks": 100, "uptimeSeconds": 2.0, "worldSeq": 10,
                    "hasSaveLoaded": True, "onTitleScreen": False},
    }


def healthy_observe() -> dict:
    return {
        "ok": True, "status": "ok", "schema": "agentfarm-world/5", "worldSeq": 10,
        "hasSaveLoaded": True,
        "clock": {"year": 1, "season": "spring", "day": 5, "timeOfDay": 800},
        "player": {"name": "Jay", "location": "FarmHouse", "tile": [9, 9],
                   "stamina": 270.0, "maxStamina": 270.0, "canMove": True},
        "ui": {"isModal": False, "eventUp": False},
        "liveness": {"worldAdvancing": True, "secondsSinceClockMoved": 1.0},
    }


class FakeClient:
    """鸭子类型的假桥：只实现 runner 用到的那几个方法。"""

    def __init__(self, health=None, observe=None, error: Exception | None = None) -> None:
        self._health = health
        self._observe = observe
        self._error = error
        self.quit_calls = 0

    def health(self, *, timeout: float | None = None) -> dict:
        if self._error is not None:
            raise self._error
        return dict(self._health or {})

    def observe(self, detail: str = "summary", *, timeout: float | None = None) -> dict:
        if self._error is not None:
            raise self._error
        return dict(self._observe or {})

    def quit_game(self, *, timeout_ms: int = 3000) -> dict:
        self.quit_calls += 1
        return {"ok": True, "status": "assumed_quitting", "reason": "假桥：已请求退出"}


def make_runner(fake: FakeClient, tmp: Path, **kw) -> SupervisedRunner:
    logs: list[str] = []
    defaults = dict(
        client_factory=lambda: fake,
        interval=0.0,
        duration_seconds=None,
        sleep=lambda _s: None,
        log=logs.append,
        report_dir=tmp,
        mod_version_expected="0.7.3",
    )
    defaults.update(kw)
    r = SupervisedRunner(**defaults)
    r.logs = logs  # type: ignore[attr-defined]
    return r


class TestSupervisedRunner(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ---------- 1. 正常跑满 ----------
    def test_healthy_run_finishes_normally(self) -> None:
        fake = FakeClient(healthy_health(), healthy_observe())
        r = make_runner(fake, self.tmp, max_samples=3)
        self.assertEqual(r.run(), 0)
        self.assertEqual(fake.quit_calls, 0)
        self.assertEqual(len(list(self.tmp.glob("stop-*.json"))), 0)
        self.assertTrue(any("verdict=ok" in line for line in r.logs))  # type: ignore[attr-defined]

    # ---------- 2. stop 落报告并退出 2 ----------
    def test_stop_writes_report_and_exits_2(self) -> None:
        h = healthy_health()
        h["runtime"]["onTitleScreen"] = True          # 标题界面 = STOP
        fake = FakeClient(h, healthy_observe())
        r = make_runner(fake, self.tmp)
        self.assertEqual(r.run(), 2)

        reports = list(self.tmp.glob("stop-*.json"))
        self.assertEqual(len(reports), 1)
        payload = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["verdict"], "stop")
        self.assertIn("title_screen", [f["code"] for f in payload["findings"]])
        # 报告必须带上"当时世界长什么样"，否则人回来无从复盘
        self.assertEqual(payload["observe"]["clock"]["timeOfDay"], 800)
        self.assertEqual(fake.quit_calls, 0)          # on_stop 默认 report：不动游戏

    # ---------- 3. on_stop=quit 真的去关游戏 ----------
    def test_on_stop_quit_calls_quit_game(self) -> None:
        h = healthy_health()
        h["runtime"]["hasSaveLoaded"] = False
        fake = FakeClient(h, {**healthy_observe(), "hasSaveLoaded": False})
        r = make_runner(fake, self.tmp, on_stop=ON_STOP_QUIT)
        self.assertEqual(r.run(), 2)
        self.assertEqual(fake.quit_calls, 1)

        fake2 = FakeClient(h, {**healthy_observe(), "hasSaveLoaded": False})
        r2 = make_runner(fake2, self.tmp, on_stop=ON_STOP_NOTHING)
        self.assertEqual(r2.run(), 2)
        self.assertEqual(fake2.quit_calls, 0)

    # ---------- 4. 连不上桥 = stop ----------
    def test_bridge_unreachable_is_stop(self) -> None:
        err = BridgeError("连不上 http://127.0.0.1:17890/v1/health", status="unreachable_bridge")
        fake = FakeClient(error=err)
        r = make_runner(fake, self.tmp)
        self.assertEqual(r.run(), 2)

        payload = json.loads(list(self.tmp.glob("stop-*.json"))[0].read_text(encoding="utf-8"))
        codes = [f["code"] for f in payload["findings"]]
        self.assertIn("bridge_unreachable", codes)
        self.assertIn("unreachable_bridge", json.dumps(payload, ensure_ascii=False))

    # ---------- 5. 任何取数异常都不许带崩循环 ----------
    def test_arbitrary_exception_becomes_stop_not_crash(self) -> None:
        fake = FakeClient(error=RuntimeError("socket exploded"))
        r = make_runner(fake, self.tmp)
        self.assertEqual(r.run(), 2)   # 不是抛异常

    # ---------- 6. 时长到期也能正常结束 ----------
    def test_duration_exit_is_normal(self) -> None:
        fake = FakeClient(healthy_health(), healthy_observe())
        ticks = {"t": 0.0}

        def now() -> float:
            ticks["t"] += 100.0
            return ticks["t"]

        r = make_runner(fake, self.tmp, duration_seconds=50.0, now=now)
        self.assertEqual(r.run(), 0)
        self.assertEqual(fake.quit_calls, 0)

    # ---------- 7. 钩子抛异常不许带崩监督 ----------
    def test_on_sample_hook_exception_is_ignored(self) -> None:
        fake = FakeClient(healthy_health(), healthy_observe())

        def boom(_s) -> None:
            raise ValueError("planner bug")

        r = make_runner(fake, self.tmp, max_samples=2, on_sample=boom)
        self.assertEqual(r.run(), 0)
        self.assertTrue(any("on_sample 钩子抛异常" in line for line in r.logs))  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main(verbosity=2)
