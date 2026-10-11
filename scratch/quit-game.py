# -*- coding: utf-8 -*-
"""按 Lead 指令优雅退出游戏（quit_game），并逐项确认"进程消失 + 桥消失"。

只做 Lead 明确授权的 quit_game；不 close/杀进程、不 taskkill（除非脚本最后如实报告"进程还在"）。
用法：python scratch\\quit-game.py [--pid 24444]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brain")))

from agentfarm.bridge import BridgeClient, BridgeError, pid_alive  # noqa: E402

BRIDGE_JSON = os.path.join(os.environ["APPDATA"], "StardewValley", "AgentFarm", "bridge.json")
PORT = 17890


def bridge_json_state() -> str:
    if not os.path.exists(BRIDGE_JSON):
        return "不存在（已删除）"
    st = os.stat(BRIDGE_JSON)
    ts = time.strftime("%H:%M:%S", time.localtime(st.st_mtime))
    try:
        with open(BRIDGE_JSON, "r", encoding="utf-8") as fh:
            raw = fh.read()
        obj = json.loads(raw)
        pid = obj.get("pid")
        return f"存在 mtime={ts} size={st.st_size} pid={pid} modVersion={obj.get('modVersion')}"
    except Exception as exc:  # noqa: BLE001
        return f"存在 mtime={ts} size={st.st_size} 但解析失败：{type(exc).__name__}: {exc}"


def port_open() -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        s.close()


def pid_from_bridge_json() -> int | None:
    try:
        with open(BRIDGE_JSON, "r", encoding="utf-8") as fh:
            return json.load(fh).get("pid")
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--wait", type=int, default=90, help="等进程消失的最长秒数")
    args = ap.parse_args()

    pid = args.pid or pid_from_bridge_json()
    print("=== 退出前 ===")
    print(f"bridge.json : {bridge_json_state()}")
    print(f"pid         : {pid}  pid_alive={pid_alive(pid) if pid else '?'}")
    print(f"端口 {PORT}   : {'开着' if port_open() else '关着'}")
    try:
        h = BridgeClient().health()
        print(f"health      : {json.dumps({k: h.get(k) for k in ('ok', 'status', 'modVersion', 'runtime')}, ensure_ascii=False)[:300]}")
    except BridgeError as exc:
        print(f"health      : BridgeError {str(exc)[:200]}")

    print("\n=== 下发 quit_game ===")
    t0 = time.time()
    try:
        res = BridgeClient().quit_game()
        print(f"回执（{time.time() - t0:.1f}s）：{json.dumps(res, ensure_ascii=False)[:500]}")
    except BridgeError as exc:
        # 游戏自己退出会让回执收不到 —— bridge.py:572 明说这是预期行为
        print(f"回执异常（{time.time() - t0:.1f}s，可能是『游戏先退导致收不到回执』这一预期情形）：{str(exc)[:400]}")

    print(f"\n=== 等待退出（最多 {args.wait}s）===")
    deadline = time.time() + args.wait
    last = None
    gone_at = None
    while time.time() < deadline:
        alive = pid_alive(pid) if pid else False
        po = port_open()
        try:
            BridgeClient().health(timeout=1.5)
            heal = "OK"
        except BridgeError:
            heal = "unreachable"
        snap = (alive, po, heal, bridge_json_state())
        if snap != last:
            print(f"  t+{time.time() - t0:5.1f}s  pid_alive={alive}  port={po}  health={heal}  bridge.json: {snap[3]}")
            last = snap
        if not alive and not po:
            gone_at = time.time() - t0
            break
        time.sleep(2.0)

    print("\n=== 终态 ===")
    alive = pid_alive(pid) if pid else False
    po = port_open()
    print(f"pid {pid} pid_alive = {alive}")
    print(f"端口 {PORT} 监听      = {po}")
    print(f"bridge.json          : {bridge_json_state()}")
    print(f"进程消失用时          : {gone_at if gone_at is not None else '未在预算内消失'}")
    verdict = "已退出（进程消失 + 桥不可达）" if (not alive and not po) else "未确认退出（进程或端口仍在）"
    print(f"VERDICT: {verdict}")
    return 0 if verdict.startswith("已退出") else 2


if __name__ == "__main__":
    sys.exit(main())
