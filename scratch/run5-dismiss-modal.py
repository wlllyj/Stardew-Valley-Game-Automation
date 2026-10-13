# -*- coding: utf-8 -*-
"""关掉当前挡路模态（默认只关一次），只用于非事件/非提问的普通菜单（如 ShippingMenu）。

判据：关完 `ui.activeMenu` 变空 + `liveness.worldAdvancing` 恢复 + 存档 mtime 前进。
用法：python scratch\\run5-dismiss-modal.py [--rounds 1] [--wait 25]
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brain")))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SAVE_MAIN = os.path.join(SAVE_DIR, "Wahaha_450799035")


def snap(c: BridgeClient) -> dict:
    obs = c.observe(detail="summary")
    p, ui, live, clk = obs.get("player") or {}, obs.get("ui") or {}, obs.get("liveness") or {}, obs.get("clock") or {}
    return {"menu": ui.get("activeMenu"), "isModal": ui.get("isModal"), "eventUp": ui.get("eventUp"),
            "q": ui.get("dialogueIsQuestion"), "resp": ui.get("dialogueResponses"),
            "text": ui.get("activeMenuText"), "worldAdvancing": live.get("worldAdvancing"),
            "secsSince": live.get("secondsSinceClockMoved"), "day": [clk.get("season"), clk.get("day")],
            "tod": clk.get("timeOfDay"), "canMove": p.get("canMove"), "money": p.get("money"),
            "saveMain": (os.path.getsize(SAVE_MAIN), round(os.path.getmtime(SAVE_MAIN), 3)) if os.path.exists(SAVE_MAIN) else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--wait", type=int, default=25)
    args = ap.parse_args()
    c = BridgeClient()

    before = snap(c)
    print(f"关框前：{before}")
    if not before["isModal"]:
        print("当前没有模态，无需关闭。")
        return 0
    if before["eventUp"] is True or before["q"] or before["resp"]:
        print("⛔ 这是游戏事件/提问（eventUp 或对话选项非空）⇒ 按 task-41 政策**不动手**，停下等人。")
        return 3

    for i in range(1, args.rounds + 1):
        try:
            r = c.dismiss_modal()
        except BridgeError as exc:
            print(f"第 {i} 次 dismiss_modal 异常：{exc}")
            return 2
        print(f"第 {i} 次回执：{r}")
        time.sleep(2.0)
        cur = snap(c)
        print(f"   关后：menu={cur['menu']} isModal={cur['isModal']} worldAdvancing={cur['worldAdvancing']} "
              f"secsSince={cur['secsSince']} canMove={cur['canMove']}")
        if not cur["isModal"]:
            break

    t0 = time.time()
    while time.time() - t0 < args.wait:
        cur = snap(c)
        if cur["worldAdvancing"] and not cur["isModal"]:
            break
        time.sleep(2.0)
    after = snap(c)
    print(f"关框后：{after}")
    save_moved = bool(before["saveMain"] and after["saveMain"] and after["saveMain"][1] > before["saveMain"][1])
    ok = (not after["isModal"]) and after["worldAdvancing"] is True
    print(f"模态清空={not after['isModal']} 世界推进={after['worldAdvancing']} 存档 mtime 前进={save_moved}")
    print("VERDICT:", "模态已清、世界恢复" if ok else "仍未恢复，停手上报")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
