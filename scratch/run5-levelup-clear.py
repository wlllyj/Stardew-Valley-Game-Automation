# -*- coding: utf-8 -*-
"""清掉 run5 收工时的空 LevelUpMenu（Lead m01045 授权，一次 dismiss + 只等不关）。

自强制护栏（照 m01045）：
  1. 先 observe 记 before：activeMenu / isModal / professionsToChoose / onScreenMenus / worldSeq / secondsSinceClockMoved
  2. 只有 `activeMenu == "LevelUpMenu"` 且 `professionsToChoose` 为空才 dismiss **一次**
     —— 非空 ⇒ 立刻停手上报（职业选择，不许替人选）；activeMenu 是别的 ⇒ 也不动手
  3. 关完若 activeMenu 变 `SaveGameMenu`/`NewDaySavingMenu` ⇒ **只等不关**（轮询到消失，上限 90s，间隔 ≥2s）
  4. 再 observe 确认 isModal==false 且 worldAdvancing==true；30s 内仍卡 ⇒ 停手上报（不连关/不 load_save/不重启）

退出码：0=已清干净且世界恢复；2=等超时仍卡（需人工）；3=professionsToChoose 非空（我未动手）；4=activeMenu 不是 LevelUpMenu（我未动手）；1=意外异常
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brain")))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

WAIT_ONLY = {"SaveGameMenu", "NewDaySavingMenu"}
WAIT_ONLY_LIMIT_S = 90.0
STUCK_LIMIT_S = 30.0


def ui_of(obs: dict) -> dict:
    ui = (obs or {}).get("ui") or {}
    return {
        "activeMenu": ui.get("activeMenu"),
        "isModal": ui.get("isModal"),
        "professionsToChoose": ui.get("professionsToChoose"),
        "onScreenMenus": ui.get("onScreenMenus"),
        "eventUp": ui.get("eventUp"),
        "activeMenuText": ui.get("activeMenuText"),
    }


def liveness_of(obs: dict) -> dict:
    lv = (obs or {}).get("liveness") or {}
    return {
        "worldAdvancing": lv.get("worldAdvancing"),
        "secondsSinceClockMoved": lv.get("secondsSinceClockMoved"),
    }


def snap(c: BridgeClient, label: str) -> dict:
    obs = c.observe("full")
    if isinstance(obs, dict) and "observation" in obs:
        obs = obs["observation"]
    row = {
        "label": label,
        "at": time.strftime("%H:%M:%S"),
        "worldSeq": obs.get("worldSeq"),
        "clock": (obs.get("clock") or {}).get("timeOfDay"),
        "ui": ui_of(obs),
        "liveness": liveness_of(obs),
        "player": {k: (obs.get("player") or {}).get(k) for k in ("location", "tile", "canMove", "stamina", "money")},
    }
    print(f"[{label}] {json.dumps(row, ensure_ascii=False)}", flush=True)
    return row


def main() -> int:
    c = BridgeClient()
    before = snap(c, "before")

    menu = (before["ui"] or {}).get("activeMenu")
    profs = (before["ui"] or {}).get("professionsToChoose")

    if menu != "LevelUpMenu":
        print(f"！activeMenu={menu!r} 不是 LevelUpMenu ⇒ 按护栏不动手，停手上报", flush=True)
        return 4
    if profs:
        print(f"！professionsToChoose={profs!r} 非空 ⇒ 这是职业选择，不许替人选，停手上报", flush=True)
        return 3

    print("→ LevelUpMenu 且 professionsToChoose 为空 ⇒ 授权条件满足，dismiss_modal 一次", flush=True)
    try:
        receipt = c.dismiss_modal()
    except BridgeError as exc:
        print(f"！dismiss_modal 抛 BridgeError：{exc}", flush=True)
        return 1
    print(f"回执：{json.dumps(receipt, ensure_ascii=False)}", flush=True)

    after = snap(c, "after-dismiss")
    t0 = time.time()
    waited_only = False

    while time.time() - t0 < WAIT_ONLY_LIMIT_S:
        menu_now = (after["ui"] or {}).get("activeMenu")
        lv = after["liveness"] or {}
        if menu_now is None and lv.get("worldAdvancing") is True:
            print(f"✅ 已清干净且世界恢复（用时 {time.time() - t0:.1f}s）", flush=True)
            return 0
        if menu_now in WAIT_ONLY:
            if not waited_only:
                print(f"→ activeMenu={menu_now} ⇒ 只等不关（上限 {WAIT_ONLY_LIMIT_S:.0f}s，间隔 ≥2s）", flush=True)
                waited_only = True
        elif menu_now is not None and menu_now != "LevelUpMenu" and time.time() - t0 > STUCK_LIMIT_S:
            print(f"！出现新的/未知的模态 {menu_now!r} ⇒ 停手上报（不连关）", flush=True)
            return 2
        elif menu_now == "LevelUpMenu" and time.time() - t0 > STUCK_LIMIT_S:
            print("！LevelUpMenu 又回来了 ⇒ 停手上报（不连关）", flush=True)
            return 2
        time.sleep(2.5)
        after = snap(c, f"poll+{time.time() - t0:.0f}s")

    print("！等待超时仍卡 ⇒ 停手上报", flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
