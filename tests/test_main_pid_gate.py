#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""task-26：`agentfarm shutdown --force-after` 的判活必须是**三态**，`None` 不是 `False`。

背景：`brain\\agentfarm\\__main__.py:517` 旧写法 `if pid_alive(info.pid) is not True:` 把 `None`
（= **不知道**，`bridge.json` 缺 pid 或平台不支持）一并当成"游戏进程已退出"，于是**立刻** `return 0`，
跳过整个强杀兜底 —— 无人值守时游戏可能还挂着，部署脚本却以为它已经关了。

本文件只断言**行为**（是否强杀、睡了几次、返回码），不依赖日志文本措辞。
"""
import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm import __main__ as main_mod  # noqa: E402
from agentfarm.bridge import SCHEMA_BRIDGE, BridgeError, BridgeInfo  # noqa: E402


def _info(pid: int | None) -> BridgeInfo:
    return BridgeInfo(
        schema=SCHEMA_BRIDGE,
        port=17890,
        token="deadbeef",
        pid=pid,
        mod_version="0.7.22",
        game_version="1.6.15",
        smapi_version="4.5.2",
        started_at="2026-10-13T00:00:00+07:00",
        path=Path("bridge.json"),
    )


class _Recorder:
    """记录 `out` 的每一行，并统计 sleep / kill 调用（行为断言用）。"""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.slept: list[float] = []
        self.killed: list[int] = []

    # 与 await_game_exit 的注入点一一对应
    def out(self, line: str) -> None:
        self.lines.append(line)

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def kill(self, pid: int) -> bool:
        self.killed.append(pid)
        return True

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def declared_exit(self) -> bool:
        """是否报了"游戏进程已退出"（成功判据只以 `[OK]  游戏进程…已退出` 这一行出现；
        警告文案里的"存活未知 ≠ 已退出"不算）。"""
        return f"{main_mod.OK} 游戏进程" in self.text

    def gate(self, info: BridgeInfo, seconds: int, *, responds: bool | None = None) -> int:
        """用同一个 Recorder 跑一次 await_game_exit；`responds=None` = 不提供 HTTP 探测。"""
        probe = None if responds is None else (lambda: responds)
        return main_mod.await_game_exit(
            info, seconds, sleep=self.sleep, kill=self.kill, out=self.out, bridge_responds=probe,
        )


class AwaitGameExitTest(unittest.TestCase):
    # ---------- ① pid_alive 返回 True：确实活着 → 等满 + 强杀 ----------
    def test_alive_true_waits_full_time_then_kills(self) -> None:
        rec = _Recorder()
        with mock.patch.object(main_mod, "pid_alive", return_value=True):
            rc = rec.gate(_info(24444), 3)
        self.assertEqual(rc, 0)
        self.assertEqual(rec.slept, [1, 1, 1])          # 每秒一次，等满
        self.assertEqual(rec.killed, [24444])           # 超时后强杀
        self.assertFalse(rec.declared_exit)             # 不许误报退出

    # ---------- ② pid_alive 返回 False：确实不在了 → 立即报退出、不杀 ----------
    def test_alive_false_reports_exit_without_kill(self) -> None:
        rec = _Recorder()
        with mock.patch.object(main_mod, "pid_alive", return_value=False):
            rc = rec.gate(_info(24444), 5)
        self.assertEqual(rc, 0)
        self.assertEqual(rec.slept, [])                 # 第一拍就确认，不用等
        self.assertEqual(rec.killed, [])                # 已经没了，不该强杀
        self.assertTrue(rec.declared_exit)              # 这一态才是真的"已退出"

    # ---------- ③ pid_alive 返回 None（缺 pid）：不得走"已退出/return 0 跳过强杀" ----------
    def test_unknown_and_missing_pid_never_declares_exit(self) -> None:
        rec = _Recorder()
        with mock.patch.object(main_mod, "pid_alive", return_value=None):
            rc = rec.gate(_info(None), 3, responds=False)
        self.assertNotEqual(rc, 0)                      # 没确认进程消失 ⇒ 不许报成功
        self.assertEqual(rec.slept, [1, 1, 1])          # 必须把时间等满，而不是立刻收场
        self.assertEqual(rec.killed, [])                # 没有 pid，杀不了
        self.assertFalse(rec.declared_exit)             # **核心断言**：不知道 ≠ 已退出
        self.assertIn("未知", rec.text)                  # 但不许沉默：要如实说"存活未知"
        self.assertIn("缺 pid", rec.text)

    def test_unknown_but_real_pid_still_runs_kill_fallback(self) -> None:
        """`pid` 有值、只是平台不支持判活（`pid_alive` → None）：兜底强杀**必须**照跑。"""
        rec = _Recorder()
        with mock.patch.object(main_mod, "pid_alive", return_value=None):
            rc = rec.gate(_info(24444), 2, responds=False)
        self.assertEqual(rc, 0)
        self.assertEqual(rec.slept, [1, 1])
        self.assertEqual(rec.killed, [24444])           # 旧写法在这里会 return 0 跳过强杀
        self.assertFalse(rec.declared_exit)

    # ---------- ④ None + HTTP 探测成功 ⇒ 正常继续 ----------
    def test_unknown_with_bridge_answering_keeps_waiting(self) -> None:
        rec = _Recorder()
        with mock.patch.object(main_mod, "pid_alive", return_value=None) as alive:
            rc = rec.gate(_info(None), 2, responds=True)
        self.assertTrue(alive.called)
        self.assertEqual(rec.slept, [1, 1])             # 继续等，而不是当场退出
        self.assertEqual(rec.killed, [])
        self.assertFalse(rec.declared_exit)
        self.assertIn("仍在应答", rec.text)              # 有独立证据说明进程活着
        self.assertNotEqual(rc, 0)                      # 但没有 pid，仍然无法强杀

    # ---------- 状态迁移：先在 → 后不在，应提前收工 ----------
    def test_alive_turns_false_mid_loop_returns_early(self) -> None:
        rec = _Recorder()
        with mock.patch.object(main_mod, "pid_alive", side_effect=[True, False]):
            rc = rec.gate(_info(24444), 10)
        self.assertEqual(rc, 0)
        self.assertEqual(rec.slept, [1])                # 第二拍就确认退出，不再空等
        self.assertEqual(rec.killed, [])
        self.assertTrue(rec.declared_exit)

    def test_no_timeout_expiry_no_sleep_no_kill(self) -> None:
        """`seconds=0`：循环不跑，但（有 pid 时）仍走强杀兜底，与旧行为一致。"""
        rec = _Recorder()
        with mock.patch.object(main_mod, "pid_alive", return_value=True):
            rc = rec.gate(_info(24444), 0)
        self.assertEqual(rc, 0)
        self.assertEqual(rec.slept, [])
        self.assertEqual(rec.killed, [24444])


class BridgeRespondsProbeTest(unittest.TestCase):
    def test_health_maps_to_bool(self) -> None:
        class Client:
            def __init__(self, ok: bool) -> None:
                self.ok = ok

            def health(self, *, timeout: float | None = None) -> dict:
                if not self.ok:
                    raise BridgeError("连不上 127.0.0.1:17890", status="unreachable_bridge")
                return {"ok": True}

        self.assertTrue(main_mod._bridge_responds(Client(True)))
        self.assertFalse(main_mod._bridge_responds(Client(False)))


class CmdShutdownWiringTest(unittest.TestCase):
    def test_force_after_goes_through_three_state_gate(self) -> None:
        """`--force-after` 分支必须把控制权交给 await_game_exit（并带上 HTTP 探测回调）。"""
        seen: dict = {}

        class Client:
            def quit_game(self) -> dict:
                return {"status": "quitting", "reason": "已置 Game1.quit = true"}

        def fake_gate(info, seconds, **kwargs):
            seen["info"] = info
            seen["seconds"] = seconds
            seen["probe"] = kwargs.get("bridge_responds")
            return 7

        args = argparse.Namespace(force_after=5, no_force=False)
        with mock.patch.object(main_mod, "BridgeClient", lambda *a, **k: Client()), \
                mock.patch.object(main_mod, "load_bridge_info", lambda *a, **k: _info(24444)), \
                mock.patch.object(main_mod, "await_game_exit", fake_gate):
            rc = main_mod.cmd_shutdown(args)

        self.assertEqual(rc, 7)                          # 返回码由闸门决定，不再内联 return 0
        self.assertEqual(seen["seconds"], 5)
        self.assertEqual(seen["info"].pid, 24444)
        self.assertTrue(callable(seen["probe"]))          # pid 不确定时要用得上 HTTP 探测

    def test_no_force_after_does_not_touch_the_gate(self) -> None:
        class Client:
            def quit_game(self) -> dict:
                return {"status": "quitting", "reason": "ok"}

        args = argparse.Namespace(force_after=0, no_force=False)
        with mock.patch.object(main_mod, "BridgeClient", lambda *a, **k: Client()), \
                mock.patch.object(main_mod, "await_game_exit") as gate:
            rc = main_mod.cmd_shutdown(args)
        self.assertEqual(rc, 0)
        self.assertFalse(gate.called)


if __name__ == "__main__":
    unittest.main()
