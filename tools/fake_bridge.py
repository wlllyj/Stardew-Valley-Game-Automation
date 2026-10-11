"""假 Mod：在没有游戏的情况下验证"脑"。

用途（架构 §9「mock 世界」的最小实现）：
- 开发期验证 bridge 客户端、CLI、doctor 全链路；
- 真机出问题时做对照实验（"是脑的问题还是 Mod 的问题？"）。

用法：
    python tools/fake_bridge.py                      # 监听 17899，写 bridge.json 到临时目录
    python tools/fake_bridge.py --port 17899 --out D:\\tmp\\bridge.json
    # 另开一个终端：
    $env:AGENTFARM_BRIDGE_JSON = "D:\\tmp\\bridge.json"
    .\\tools\\agentfarm.ps1 doctor

⚠️ 它**不是**游戏：玩家名会显示为 MOCK-Jay，modVersion 带 -fake 后缀，避免与真机混淆。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = "fake" + "0" * 28

# 假世界的可变状态：让 move_to 真的"记住"玩家走到哪，这样 mock 才像真 Mod
STATE: dict = {"tile": [2, 11], "move_calls": 0}


def _hmm(total_minutes: int) -> int:
    """把"从 6:00 起的分钟数"转成游戏时钟格式：6:00 -> 600, 12:30 -> 1230, 13:05 -> 1305。

    直接用 1230 + n 会算出 1280 这种不存在的时刻（游戏里分钟逢 60 进位）。
    """
    hours = 6 + total_minutes // 60
    minutes = total_minutes % 60
    return hours * 100 + minutes


def world_snapshot(detail: str, tick: int) -> dict:
    """一个会缓慢变化的世界：时钟每 4 秒推进 10 分钟，move_to 会真的改变玩家坐标。"""
    time_of_day = _hmm((tick // 4) * 10)
    tile = list(STATE["tile"])
    return {
        "ok": True,
        "status": "ok",
        "schema": "agentfarm-world/3",
        "worldSeq": 100 + tick,
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "hasSaveLoaded": True,
        "clock": {"year": 1, "season": "spring", "day": 3,
                  "timeOfDay": time_of_day, "weather": "rain", "weatherOnFarm": "rain"},
        "player": {"name": "MOCK-Jay", "location": "FarmHouse", "tile": tile, "facing": 0,
                   "canMove": True, "hasController": False, "isInBed": False,
                   "stamina": 268.0, "maxStamina": 270.0, "health": 100, "maxHealth": 100,
                   "money": 482, "farmingLevel": 0, "inventoryCount": 12,
                   "tools": {"hoe": True, "axe": True, "pickaxe": True,
                             "wateringCan": True, "fishingRod": False, "weapon": True}},
        "location": {"name": "FarmHouse", "isFarm": False, "isFarmhouse": True,
                     "isOutdoorFarm": False, "isOutdoors": False, "objects": 1, "debris": 0,
                     "terrainFeatures": 1, "characters": 0},
        "farm": {"loaded": True, "hoeDirt": 0, "emptyDirt": 0, "crops": 0, "ripeCrops": 0,
                 "unwateredCrops": 0, "weeds": 443, "stones": 241, "twigs": 114,
                 "trees": 148, "grass": 458, "sprinklers": 0, "machinesTotal": 0,
                 "machinesReady": 0, "animals": 0},
        # v2：dialogsOnScreen 已删除（它是常驻 HUD，名字误导），改为 onScreenMenus
        #     并按协议"null 字段省略"的约定，没有菜单时不写 activeMenuText
        "ui": {"isModal": False, "eventUp": False, "onScreenMenus": 4,
               "dialogueResponses": [], "dialogueIsQuestion": False},
        # v3：新增 game 段诊断（paused / shouldTimePass）
        "game": {"paused": False, "shouldTimePass": True},
        "liveness": {"worldAdvancing": True, "secondsSinceClockMoved": 0.5},
        "_fake": {"detail": detail, "note": "这是假 Mod，不是真实游戏数据"},
    }


class Handler(BaseHTTPRequestHandler):
    started = time.time()

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write(f"[fake-bridge] {fmt % args}\n")

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        tick = int(time.time() - Handler.started)
        if parsed.path == "/v1/health":
            self._send(200, {
                "ok": True, "status": "ok", "schema": "agentfarm-bridge/1",
                "modVersion": "0.1.0-fake",
                "game": {"version": "1.6.15", "smapi": "4.5.2", "windowActive": True},
                "runtime": {"ticks": tick * 60, "uptimeSeconds": float(tick), "worldSeq": 100 + tick,
                            "hasSaveLoaded": True, "onTitleScreen": False},
                "server": {"port": self.server.server_address[1], "requestsServed": 0},
            })
            return
        if parsed.path == "/v1/observe":
            if self.headers.get("X-Auth-Token") != TOKEN:
                self._send(401, {"ok": False, "status": "unauthorized", "reason": "令牌不匹配"})
                return
            detail = parse_qs(parsed.query).get("detail", ["summary"])[0]
            self._send(200, world_snapshot(detail, tick))
            return
        self._send(404, {"ok": False, "status": "not_found", "reason": f"未知路径 {parsed.path}"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/v1/exec":
            self._send(404, {"ok": False, "status": "not_found", "reason": "未知路径"})
            return
        if self.headers.get("X-Auth-Token") != TOKEN:
            self._send(401, {"ok": False, "status": "unauthorized", "reason": "令牌不匹配"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        skill = body.get("skill")
        timeout_ms = int(body.get("timeout_ms", 8000))
        if skill == "noop":
            # 带 schema：验证客户端"存在才校验"的分支
            self._send(200, {"ok": True, "status": "ok", "skill": "noop", "reason": "",
                             "schema": "agentfarm-exec/2", "worldResumed": True,
                             "elapsedMs": 1, "worldSeqBefore": 100, "worldSeqAfter": 100})
            return
        if skill == "move_to":
            # 假装走一小会儿；目标越界则报 precondition_failed；否则真的更新假世界坐标
            tile = (body.get("args") or {}).get("tile") or [0, 0]
            elapsed = min(timeout_ms, 1200)
            time.sleep(elapsed / 1000.0)
            if not (0 <= int(tile[0]) <= 80 and 0 <= int(tile[1]) <= 80):
                self._send(200, {"ok": False, "status": "precondition_failed", "skill": skill,
                                 "reason": f"目标 {tile} 不在当前地点内（跨地点移动尚未实现）",
                                 "elapsedMs": elapsed, "worldSeqBefore": 100, "worldSeqAfter": 101})
                return
            STATE["tile"] = [int(tile[0]), int(tile[1])]
            STATE["move_calls"] += 1
            self._send(200, {"ok": True, "status": "ok", "skill": skill, "reason": "",
                             "schema": "agentfarm-exec/2", "worldResumed": True,
                             "elapsedMs": elapsed, "worldSeqBefore": 100, "worldSeqAfter": 104})
            return
        self._send(200, {"ok": False, "status": "unknown_skill", "skill": skill,
                         "reason": f"假 Mod 不认识技能 {skill!r}", "elapsedMs": 0,
                         "worldSeqBefore": 100, "worldSeqAfter": 100})


def main() -> int:
    # 本机 Python 在重定向场景下默认 cp1252，打印中文会崩；入口处强制 UTF-8
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="假 Mod：在没有游戏时验证脑")
    ap.add_argument("--port", type=int, default=17899)
    ap.add_argument("--out", default=None, help="bridge.json 写出路径")
    args = ap.parse_args()

    out = args.out or os.path.join(os.environ.get("TEMP", "."), "agentfarm-fake-bridge.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    port = server.server_address[1]
    info = {
        "schema": "agentfarm-bridge/1", "port": port, "token": TOKEN, "pid": os.getpid(),
        "modVersion": "0.1.0-fake", "gameVersion": "1.6.15", "smapiVersion": "4.5.2",
        "startedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, out)

    print(f"假 Mod 已启动：http://127.0.0.1:{port}/   (令牌 {TOKEN})")
    print(f"bridge.json 已写入：{out}")
    print("验证方式（另开终端）：")
    print(f'  $env:AGENTFARM_BRIDGE_JSON = "{out}"')
    print("  .\\tools\\agentfarm.ps1 doctor")
    print("  .\\tools\\agentfarm.ps1 observe")
    print("Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        server.server_close()
        try:
            os.remove(out)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
