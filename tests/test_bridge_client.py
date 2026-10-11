"""桥接客户端的离线单元测试（不需要游戏、不需要 Mod）。

思路：用标准库 http.server 起一个**假 Mod**，把 bridge.json 写进临时目录，
再用 AGENTFARM_BRIDGE_JSON 指过去。这样"脑"可以在没有游戏的情况下开发和回归——
这正是架构 §9 测试策略里的「mock 世界」的第一步。

运行：
    cd "D:\\Deepseek Harness Workspace\\星露谷游戏自动化"
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import io
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
    world_schema = "agentfarm-world/6"
    exec_status = "ok"
    require_token = True
    # 失败回执上额外挂的字段（用来测"失败也带 path/hops"这类审计要求）
    exec_fail_extra = None

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
        # 记下最近一次请求体，供测试断言"客户端到底发了什么"（例如 allow_bed 是否只在 True 时出现）
        type(self).last_body = body
        skill = body.get("skill")
        if skill == "noop":
            self._send(200, {"ok": True, "status": "ok", "skill": "noop", "reason": "",
                             "elapsedMs": 1, "worldSeqBefore": 42, "worldSeqAfter": 42})
            return
        if self.exec_status != "ok":
            payload = {"ok": False, "status": self.exec_status,
                       "skill": skill, "reason": "目标不可达（假 Mod 构造）",
                       "elapsedMs": 500, "worldSeqBefore": 42, "worldSeqAfter": 42}
            if type(self).exec_fail_extra:
                payload.update(type(self).exec_fail_extra)
            self._send(200, payload)
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
        FakeBridgeHandler.world_schema = "agentfarm-world/6"   # 与脑侧 SCHEMA_WORLD 一致
        FakeBridgeHandler.exec_status = "ok"
        FakeBridgeHandler.require_token = True
        FakeBridgeHandler.exec_fail_extra = None
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
        self.assertEqual(obs["schema"], "agentfarm-world/6")
        self.assertEqual(obs["player"]["tile"], [2, 11])
        self.assertEqual(obs["farm"]["weeds"], 443)

    def test_noop_and_move(self) -> None:
        c = BridgeClient()
        self.assertEqual(c.noop()["status"], "ok")
        res = c.move_to(64, 15, timeout_ms=3000, based_on_seq=42)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["worldSeqBefore"], 42)
        self.assertEqual(res["worldSeqAfter"], 57)

    def test_move_to_allow_bed_only_when_true(self) -> None:
        """allow_bed 默认不得出现在请求里：无人值守踩床会触发睡觉流程（破坏性副作用）。

        只有显式 allow_bed=True 才发这个字段，且它只影响 Mod 对"床"的判定。
        """
        c = BridgeClient()
        c.move_to(10, 9, timeout_ms=2000)
        self.assertEqual(FakeBridgeHandler.last_body["args"]["tile"], [10, 9])
        self.assertNotIn("allow_bed", FakeBridgeHandler.last_body["args"])

        c.move_to(10, 9, timeout_ms=2000, allow_bed=True)
        self.assertIs(FakeBridgeHandler.last_body["args"]["allow_bed"], True)

    def test_move_to_location_request_shape(self) -> None:
        """跨地点移动：location 必发；tile/allow_bed 只在显式给出时才出现。"""
        c = BridgeClient()
        c.move_to_location("Farm", timeout_ms=20000)
        body = FakeBridgeHandler.last_body
        self.assertEqual(body["skill"], "move_to_location")
        self.assertEqual(body["args"], {"location": "Farm"})
        self.assertEqual(body["timeout_ms"], 20000)

        c.move_to_location("Farm", tile=(64, 15), timeout_ms=20000)
        self.assertEqual(FakeBridgeHandler.last_body["args"], {"location": "Farm", "tile": [64, 15]})

        c.move_to_location("Farm", timeout_ms=20000, allow_bed=True)
        self.assertIs(FakeBridgeHandler.last_body["args"]["allow_bed"], True)

    def test_move_to_location_failure_exposes_hops(self) -> None:
        """失败回执也必须能拿到 path/hops：脑要看出"走到哪一步断的"才能换策略。

        Mod 侧把 path/hops 放在 ok=false 的响应里，客户端 `_request` 把它转成 BridgeError
        时必须把**完整 payload** 留在异常上（否则这些审计信息就丢了）。
        """
        FakeBridgeHandler.exec_status = "hop_failed"
        FakeBridgeHandler.exec_fail_extra = {
            "path": ["FarmHouse", "Farm"],
            "hops": [{"from": "FarmHouse", "to": "Farm", "result": "hop_failed",
                      "sourceTile": [12, 3], "landingTile": [64, 15], "ms": 500}],
            "reachedLocation": "FarmHouse",
        }
        with self.assertRaises(BridgeError) as ctx:
            BridgeClient().move_to_location("Farm", timeout_ms=20000)
        self.assertEqual(ctx.exception.status, "hop_failed")
        payload = ctx.exception.payload or {}
        self.assertEqual(payload["hops"][0]["result"], "hop_failed")
        self.assertEqual(payload["path"], ["FarmHouse", "Farm"])

    def test_load_save_request_shape(self) -> None:
        """读档：save/force 只在显式给出时才出现（默认让 Mod 自己挑最近存档、且不 force）。"""
        c = BridgeClient()
        c.load_save(timeout_ms=60000)
        body = FakeBridgeHandler.last_body
        self.assertEqual(body["skill"], "load_save")
        self.assertNotIn("args", body)          # 空 args 不发，保持请求最小
        self.assertEqual(body["timeout_ms"], 60000)

        c.load_save("Wahaha_450799035", timeout_ms=60000)
        self.assertEqual(FakeBridgeHandler.last_body["args"], {"save": "Wahaha_450799035"})

        c.load_save("Wahaha_450799035", force=True, timeout_ms=60000)
        self.assertIs(FakeBridgeHandler.last_body["args"]["force"], True)

    def test_load_save_already_in_save_is_rejected(self) -> None:
        """已经在存档里时 Mod 报 precondition_failed；脑必须原样把它当成失败（不静默）。"""
        FakeBridgeHandler.exec_status = "precondition_failed"
        with self.assertRaises(BridgeError) as ctx:
            BridgeClient().load_save(timeout_ms=60000)
        self.assertEqual(ctx.exception.status, "precondition_failed")

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
        """未知 schema 必须显式失败，绝不"看起来像成功"（旧项目缺陷 D5）。

        注意：这里必须用一个**比当前版本更高**的 schema（当前是 /5），
        否则它会被当成"合法的旧版本"而只警告不报错（见下一个用例）。
        """
        FakeBridgeHandler.world_schema = "agentfarm-world/7"
        with self.assertRaises(BridgeError) as ctx:
            BridgeClient().observe("summary")
        self.assertEqual(ctx.exception.status, "schema_mismatch")

    def test_legacy_world_schema_is_accepted_with_loud_warning(self) -> None:
        """升级窗口：游戏里还是上一版 Mod（dll 被锁、必须重启游戏才能换）。

        此时 /3 快照要**能用**（否则脑在新 Mod 装机前完全瞎掉），但必须**大声警告**
        且警告里点明缺哪个字段、怎么消除。
        """
        import agentfarm.bridge as bridge_mod

        bridge_mod._warned_once.clear()
        FakeBridgeHandler.world_schema = "agentfarm-world/3"
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            obs = BridgeClient().observe("summary")
        self.assertEqual(obs["schema"], "agentfarm-world/3")
        text = err.getvalue()
        self.assertIn("agentfarm-world/3", text)
        self.assertIn("location.furniture[]", text)

        # 只警告一次：第二次调用不再刷屏
        err2 = io.StringIO()
        with contextlib.redirect_stderr(err2):
            BridgeClient().observe("summary")
        self.assertEqual(err2.getvalue(), "")

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
