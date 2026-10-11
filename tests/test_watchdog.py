# -*- coding: utf-8 -*-
"""无人值守体检（watchdog）的离线单元测试——不需要游戏、不需要 Mod。

这些用例的**每一条都对应一次真机观察**（见 brain/agentfarm/watchdog.py 的模块说明），
所以它们同时是"判据的可执行规格"：改判据时这些用例必须跟着改，否则就是偷偷放宽了标准。

    cd "D:\\Deepseek Harness Workspace\\星露谷游戏自动化"
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.watchdog import (  # noqa: E402
    Finding,
    UnattendedStop,
    assess,
    format_findings,
    require_healthy,
    verdict,
    write_stop_report,
)


def healthy_health(**over: object) -> dict:
    h = {
        "ok": True,
        "schema": "agentfarm-bridge/1",
        "modVersion": "0.5.1",
        "game": {"version": "1.6.15", "smapi": "4.5.2",
                 "windowActive": False, "pauseWhenOutOfFocus": False, "oofFixCount": 2},
        "runtime": {"ticks": 20000, "uptimeSeconds": 300.0, "worldSeq": 70,
                    "hasSaveLoaded": True, "onTitleScreen": False},
        "server": {"port": 17890, "requestsServed": 100},
    }
    h.update(over)
    return h


def healthy_observe(**over: object) -> dict:
    o = {
        "ok": True,
        "schema": "agentfarm-world/6",
        "worldSeq": 70,
        "hasSaveLoaded": True,
        "clock": {"year": 1, "season": "spring", "day": 3, "timeOfDay": 1450, "weather": "rain"},
        "player": {"name": "Jay", "location": "FarmHouse", "tile": [7, 4], "stamina": 270,
                   "canMove": True, "hasController": False, "isInBed": False},
        "location": {"name": "FarmHouse", "isOutdoorFarm": False},
        "ui": {"isModal": False, "onScreenMenus": 4, "dialogueResponses": [],
               "dialogueIsQuestion": False},
        "liveness": {"worldAdvancing": True, "secondsSinceClockMoved": 3.2},
    }
    o.update(over)
    return o


def codes(findings: list[Finding]) -> list[str]:
    return [f.code for f in findings]


class TestHealthy(unittest.TestCase):
    def test_normal_world_yields_nothing(self) -> None:
        """正常世界必须**零发现**——否则脑会学会忽略告警（狼来了）。"""
        self.assertEqual(assess(healthy_health(), healthy_observe()), [])
        self.assertEqual(verdict([]), "ok")

    def test_canMove_false_while_clock_running_is_not_flagged(self) -> None:
        """canMove=false 且时钟正常**不算**异常：过场/传送瞬间就是这样，误报会害死人。"""
        o = healthy_observe()
        o["player"]["canMove"] = False
        self.assertEqual(assess(healthy_health(), o), [])

    def test_stale_window_active_false_is_fine(self) -> None:
        """v0.5.0 之后窗口不在前台是**正常部署形态**，绝不能因此报警。"""
        h = healthy_health()
        self.assertIs(h["game"]["windowActive"], False)
        self.assertEqual(assess(h, healthy_observe()), [])


class TestStopLevel(unittest.TestCase):
    def test_half_deadlock_is_the_entry_013_pattern(self) -> None:
        """013 事故：模态已关、canMove=false、时钟 45s 不动 → 必须 stop。"""
        o = healthy_observe()
        o["player"]["canMove"] = False
        o["ui"]["isModal"] = False
        o["liveness"]["secondsSinceClockMoved"] = 45.0
        found = assess(healthy_health(), o)
        self.assertIn("half_deadlock", codes(found))
        self.assertIn("clock_stalled", codes(found))   # 两条同时命中是**期望**行为
        self.assertEqual(verdict(found), "stop")

    def test_modal_open_is_not_half_deadlock(self) -> None:
        """弹窗开着时 canMove=false 是**正常**的（世界被对话冻结），不能报半卡死。"""
        o = healthy_observe()
        o["player"]["canMove"] = False
        o["ui"]["isModal"] = True
        o["ui"]["activeMenu"] = "DialogueBox"
        o["ui"]["dialogueIsQuestion"] = True
        o["liveness"]["secondsSinceClockMoved"] = 45.0
        found = assess(healthy_health(), o)
        self.assertNotIn("half_deadlock", codes(found))
        self.assertIn("modal_blocking", codes(found))
        # 提问类对话框必须带"禁止盲按确认键"的警告（013 的教训）
        self.assertIn("禁止盲按确认键", [f.message for f in found if f.code == "modal_blocking"][0])
        # 但世界确实停着 —— 时钟停滞仍然是 stop
        self.assertEqual(verdict(found), "stop")

    def test_world_advancing_false_is_stop(self) -> None:
        o = healthy_observe()
        o["liveness"]["worldAdvancing"] = False
        found = assess(healthy_health(), o)
        self.assertIn("world_stalled", codes(found))
        self.assertEqual(verdict(found), "stop")

    def test_clock_stall_threshold(self) -> None:
        o = healthy_observe()
        o["liveness"]["secondsSinceClockMoved"] = 41.0
        self.assertIn("clock_stalled", codes(assess(healthy_health(), o)))
        o["liveness"]["secondsSinceClockMoved"] = 39.0
        self.assertNotIn("clock_stalled", codes(assess(healthy_health(), o)))

    def test_oof_regression_is_stop(self) -> None:
        """失焦暂停被改回 true = 世界随时会在失焦时整段停摆（IL_0444–IL_0480）。"""
        h = healthy_health()
        h["game"]["pauseWhenOutOfFocus"] = True
        found = assess(h, healthy_observe())
        self.assertIn("oof_pause_regression", codes(found))
        self.assertEqual(verdict(found), "stop")

    def test_no_save_loaded_is_stop(self) -> None:
        o = healthy_observe()
        o["hasSaveLoaded"] = False
        found = assess(healthy_health(), o)
        self.assertIn("no_save_loaded", codes(found))
        self.assertEqual(verdict(found), "stop")

    def test_title_screen_is_stop(self) -> None:
        h = healthy_health()
        h["runtime"]["onTitleScreen"] = True
        self.assertIn("title_screen", codes(assess(h, healthy_observe())))
        self.assertEqual(verdict(assess(h, healthy_observe())), "stop")


class TestWarnLevel(unittest.TestCase):
    def test_oof_field_missing_warns_about_old_mod(self) -> None:
        h = healthy_health()
        del h["game"]["pauseWhenOutOfFocus"]
        found = assess(h, healthy_observe())
        self.assertIn("oof_field_missing", codes(found))
        self.assertEqual(verdict(found), "warn")

    def test_mod_version_mismatch_is_warn_not_stop(self) -> None:
        """版本不符只警告：脑已升级、游戏里还是旧 dll 是**正常中间态**（我们接受它）。"""
        found = assess(healthy_health(), healthy_observe(), mod_version_expected="0.6.0")
        self.assertIn("mod_version_mismatch", codes(found))
        self.assertEqual(verdict(found), "warn")

    def test_matching_mod_version_is_silent(self) -> None:
        found = assess(healthy_health(), healthy_observe(), mod_version_expected="0.5.1")
        self.assertEqual(found, [])

    def test_stamina_zero_warns(self) -> None:
        o = healthy_observe()
        o["player"]["stamina"] = 0
        found = assess(healthy_health(), o)
        self.assertIn("stamina_exhausted", codes(found))
        self.assertEqual(verdict(found), "warn")


class TestRequireHealthy(unittest.TestCase):
    def test_returns_warnings_without_raising(self) -> None:
        h = healthy_health()
        del h["game"]["pauseWhenOutOfFocus"]
        found = require_healthy(h, healthy_observe())
        self.assertIn("oof_field_missing", codes(found))

    def test_raises_on_stop_and_carries_findings(self) -> None:
        h = healthy_health()
        h["game"]["pauseWhenOutOfFocus"] = True
        with self.assertRaises(UnattendedStop) as ctx:
            require_healthy(h, healthy_observe())
        self.assertIn("oof_pause_regression", codes(ctx.exception.findings))
        self.assertIn("无人值守安全检查未通过", str(ctx.exception))

    def test_missing_fields_do_not_crash(self) -> None:
        """Mod 旧版/字段缺失时不许抛 KeyError——体检本身不能成为故障源。

        注意：字段缺失**会**留下一条 warn（`oof_field_missing`），这是**故意**的：
        "拿不到证据"必须被说出来，而不是当成健康。这里只断言"不崩、不误判成 stop"。
        """
        for empty in ({}, None):
            found = assess(empty, empty)          # 不抛异常
            self.assertNotEqual(verdict(found), "stop")
            self.assertIn("oof_field_missing", codes(found))
        self.assertEqual(assess(healthy_health(), healthy_observe()), [])


class TestReporting(unittest.TestCase):
    def test_format_findings_says_ok_when_empty(self) -> None:
        self.assertIn("没发现异常", format_findings([]))

    def test_write_stop_report_lands_on_disk(self) -> None:
        h = healthy_health()
        h["game"]["pauseWhenOutOfFocus"] = True
        found = assess(h, healthy_observe())
        with tempfile.TemporaryDirectory() as tmp:
            path = write_stop_report(found, health=h, observe=healthy_observe(),
                                     directory=Path(tmp), note="单元测试")
            self.assertTrue(path.exists())
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["verdict"], "stop")
        self.assertEqual(payload["note"], "单元测试")
        self.assertIn("oof_pause_regression", [f["code"] for f in payload["findings"]])
        self.assertEqual(payload["health"]["modVersion"], "0.5.1")

    def test_verdict_priority(self) -> None:
        warn = Finding("a", "warn", "w")
        stop = Finding("b", "stop", "s")
        ok = Finding("c", "ok", "o")
        self.assertEqual(verdict([ok]), "ok")
        self.assertEqual(verdict([ok, warn]), "warn")
        self.assertEqual(verdict([warn, stop, ok]), "stop")


if __name__ == "__main__":
    unittest.main()
