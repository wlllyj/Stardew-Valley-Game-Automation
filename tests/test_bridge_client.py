"""桥接客户端的离线单元测试（不需要游戏、不需要 Mod）。

思路：用标准库 http.server 起一个**假 Mod**，把 bridge.json 写进临时目录，
再用 AGENTFARM_BRIDGE_JSON 指过去。这样"脑"可以在没有游戏的情况下开发和回归——
这正是架构 §9 测试策略里的「mock 世界」的第一步。

运行：
    cd "D:\\Deepseek Harness Workspace\\星露谷游戏自动化"
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import (  # noqa: E402
    BridgeClient,
    BridgeError,
    load_bridge_info,
)

TOKEN = "0123456789abcdef0123456789abcdef"


class FakeBridgeHandler(BaseHTTPRequestHandler):
    """假 Mod。可用类属性调整行为，让每个测试构造不同场景。"""

    token = TOKEN
    world_schema = "agentfarm-world/2"
    exec_status = "ok"
    require_token = True

    def log_message(self, *args: object) -> None:  # 静音
        pass

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self) -> bool:
        if not self.require_token:
            return True
        if self.headers.get("X-Auth-Token") == self.token:
            return True
        self._send(401, {"ok": False, "status": "unauthorized", "reason": "令牌不匹配"})
        return False

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/v1/health":
            self._send(200, {
                "ok": True, "status": "ok", "schema": "agentfarm-bridge/1", "modVersion": "0.1.0",
                "game": {"version": "1.6.15", "smapi": "4.5.2"},
                "runtime": {"ticks": 10, "uptimeSeconds": 1.5, "worldSeq": 3,
                            "hasSaveLoaded": True, "onTitleScreen": False},
                "server": {"port": self.server.server_address[1], "requestsServed": 1},
            })
            return
        if parsed.path == "/v1/observe":
            if not self._auth_ok():
                return
            detail = parse_qs(parsed.query).get("detail", ["summary"])[0]
            self._send(200, {
                "ok": True, "status": "ok", "schema": self.world_schema,
                "worldSeq": 42, "generatedAt": "2026-10-11T17:00:00+07:00", "hasSaveLoaded": True,
                "clock": {"year": 1, "season": "spring", "day": 3, "timeOfDay": 1230, "weather": "rain"},
                "player": {"name": "Jay", "location": "FarmHouse", "tile": [2, 11], "facing": 0,
                           "stamina": 268.0, "maxStamina": 270.0, "health": 100, "maxHealth": 100,
                           "money": 482, "farmingLevel": 0, "inventoryCount": 12,
                           "tools": {"hoe": True, "axe": True, "pickaxe": True,
                                     "wateringCan": True, "fishingRod": False, "weapon": True}},
                "location": {"name": "FarmHouse", "isFarm": False, "isFarmhouse": True,
                             "isOutdoors": False, "objects": 1, "debris": 0,
                             "terrainFeatures": 1, "characters": 0},
                "farm": {"loaded": True, "hoeDirt": 0, "emptyDirt": 0, "crops": 0, "ripeCrops": 0,
                         "unwateredCrops": 0, "weeds": 443, "stones": 241, "twigs": 114,
                         "trees": 148, "grass": 458, "sprinklers": 0, "machinesTotal": 0,
                         "machinesReady": 0, "animals": 0},
                "ui": {"isModal": False, "eventUp": False, "onScreenMenus": 4,
                       "dialogueResponses": [], "dialogueIsQuestion": False},
                "liveness": {"worldAdvancing": True, "secondsSinceClockMoved": 7.3},
                "detail": detail,
            })
            return
        self._send(404, {"ok": False, "status": "not_found", "reason": f"未知路径 {parsed.path}"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/v1/exec":
            self._send(404, {"ok": False, "status": "not_found", "reason": "未知路径"})
            return
        if not self._auth_ok():
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        skill = body.get("skill")
        if skill == "noop":
            self._send(200, {"ok": True, "status": "ok", "skill": "noop", "reason": "",
                             "elapsedMs": 1, "worldSeqBefore": 42, "worldSeqAfter": 42})
            return
        if self.exec_status != "ok":
            self._send(200, {"ok": False, "status": self.exec_status,
                             "skill": skill, "reason": "目标不可达（假 Mod 构造）",
                             "elapsedMs": 500, "worldSeqBefore": 42, "worldSeqAfter": 42})
            return
        self._send(200, {"ok": True, "status": "ok", "skill": skill, "reason": "",
                         "elapsedMs": 3210, "worldSeqBefore": 42, "worldSeqAfter": 57})


class BridgeClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeBridgeHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.bridge_json = Path(cls.tmp.name) / "bridge.json"
        os.environ["AGENTFARM_BRIDGE_JSON"] = str(cls.bridge_json)
        cls._write_bridge_json()

    @classmethod
    def _write_bridge_json(cls) -> None:
        cls.bridge_json.write_text(json.dumps({
            "schema": "agentfarm-bridge/1", "port": cls.port, "token": TOKEN, "pid": 4242,
            "modVersion": "0.1.0", "gameVersion": "1.6.15", "smapiVersion": "4.5.2",
            "startedAt": "2026-10-11T17:00:00+07:00",
        }), encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()
        os.environ.pop("AGENTFARM_BRIDGE_JSON", None)

    def setUp(self) -> None:
        FakeBridgeHandler.world_schema = "agentfarm-world/2"
        FakeBridgeHandler.exec_status = "ok"
        FakeBridgeHandler.require_token = True
        self._write_bridge_json()

    # ---------- 发现与校验 ----------
    def test_load_bridge_info(self) -> None:
        info = load_bridge_info()
        self.assertEqual(info.port, self.port)
        self.assertEqual(info.token, TOKEN)
        self.assertEqual(info.game_version, "1.6.15")

    def test_missing_bridge_file_is_actionable(self) -> None:
        os.environ["AGENTFARM_BRIDGE_JSON"] = str(self.bridge_json.parent / "nope.json")
        try:
            with self.assertRaises(BridgeError) as ctx:
                load_bridge_info()
            self.assertEqual(ctx.exception.status, "bridge_file_missing")
            self.assertIn("SMAPI", ctx.exception.reason)  # 提示要可操作
        finally:
            os.environ["AGENTFARM_BRIDGE_JSON"] = str(self.bridge_json)

    def test_bad_schema_in_bridge_file(self) -> None:
        self.bridge_json.write_text(json.dumps({"schema": "agentfarm-bridge/999", "port": self.port,
                                                "token": TOKEN}), encoding="utf-8")
        with self.assertRaises(BridgeError) as ctx:
            load_bridge_info()
        self.assertEqual(ctx.exception.status, "schema_mismatch")

    # ---------- 正常路径 ----------
    def test_health(self) -> None:
        h = BridgeClient().health()
        self.assertTrue(h["ok"])
        self.assertEqual(h["game"]["version"], "1.6.15")

    def test_observe_summary(self) -> None:
        obs = BridgeClient().observe("summary")
        self.assertEqual(obs["schema"], "agentfarm-world/2")
        self.assertEqual(obs["player"]["tile"], [2, 11])
        self.assertEqual(obs["farm"]["weeds"], 443)

    def test_noop_and_move(self) -> None:
        c = BridgeClient()
        self.assertEqual(c.noop()["status"], "ok")
        res = c.move_to(64, 15, timeout_ms=3000, based_on_seq=42)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["worldSeqBefore"], 42)
        self.assertEqual(res["worldSeqAfter"], 57)

    # ---------- 失败路径（旧方案的教训：失败必须显式） ----------
    def test_unauthorized_surfaces_reason(self) -> None:
        self.bridge_json.write_text(json.dumps({"schema": "agentfarm-bridge/1", "port": self.port,
                                                "token": "wrong-token", "modVersion": "0.1.0",
                                                "gameVersion": "1.6.15", "smapiVersion": "4.5.2",
                                                "startedAt": ""}), encoding="utf-8")
        with self.assertRaises(BridgeError) as ctx:
            BridgeClient().observe("summary")
        self.assertEqual(ctx.exception.status, "unauthorized")
        self.assertEqual(ctx.exception.http_status, 401)

    def test_world_schema_mismatch_is_rejected(self) -> None:
        FakeBridgeHandler.world_schema = "agentfarm-world/3"
        with self.assertRaises(BridgeError) as ctx:
            BridgeClient().observe("summary")
        self.assertEqual(ctx.exception.status, "schema_mismatch")

    def test_exec_failure_status_is_not_swallowed(self) -> None:
        FakeBridgeHandler.exec_status = "unreachable"
        with self.assertRaises(BridgeError) as ctx:
            BridgeClient().move_to(64, 15)
        self.assertEqual(ctx.exception.status, "unreachable")
        self.assertIn("不可达", ctx.exception.reason)

    def test_unknown_path_404(self) -> None:
        with self.assertRaises(BridgeError) as ctx:
            BridgeClient()._request("GET", "/v1/nope")
        self.assertEqual(ctx.exception.status, "not_found")

    def test_connection_reset_becomes_bridge_error(self) -> None:
        """对端强制重置连接时必须抛 BridgeError。

        实机踩到的坑：游戏进程抖动/退出时 socket 被 RST，抛出来的是**裸**
        ConnectionResetError（`http.client.RemoteDisconnected` 是它的子类），
        它不是 URLError，不捕就会让整个"脑"带 traceback 崩掉 —— 无人值守时致命。
        """
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        def accept_and_reset() -> None:
            try:
                conn, _ = srv.accept()
                # SO_LINGER=0 ⇒ close() 直接发 RST，制造"远程主机强迫关闭连接"
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                conn.close()
            except OSError:
                pass

        t = threading.Thread(target=accept_and_reset, daemon=True)
        t.start()
        self.bridge_json.write_text(json.dumps({
            "schema": "agentfarm-bridge/1", "port": port, "token": TOKEN, "pid": 1,
            "modVersion": "0.2.0", "gameVersion": "1.6.15", "smapiVersion": "4.5.2",
            "startedAt": "",
        }), encoding="utf-8")
        try:
            try:
                BridgeClient().health(timeout=3.0)
            except BridgeError as exc:
                self.assertIn(exc.status, ("connection_broken", "bad_response", "unreachable_bridge"))
            except OSError as exc:  # 裸异常逃逸即失败
                self.fail(f"裸异常逃逸到调用方：{type(exc).__name__}: {exc}")
            else:
                self.fail("连接被重置却当成成功了")
        finally:
            t.join(timeout=2)
            srv.close()

    def test_connection_refused_is_actionable(self) -> None:
        self.bridge_json.write_text(json.dumps({"schema": "agentfarm-bridge/1", "port": 1,
                                                "token": TOKEN, "modVersion": "0.1.0",
                                                "gameVersion": "1.6.15", "smapiVersion": "4.5.2",
                                                "startedAt": ""}), encoding="utf-8")
        with self.assertRaises(BridgeError) as ctx:
            BridgeClient().health(timeout=1.0)
        self.assertEqual(ctx.exception.status, "unreachable_bridge")


if __name__ == "__main__":
    unittest.main(verbosity=2)
