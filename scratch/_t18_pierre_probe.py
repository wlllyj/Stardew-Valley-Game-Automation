"""task-32 只读探针 A 段：直起已装 0.7.45 → load → 进 SeedShop → 走到 Pierre 邻格 → interact。

只读纪律：不买、不改世界、不 restore；对话一律"不选 Yes"（dismiss_modal 自动挑否）。
用法：PYTHONUTF8=1 python scratch\\_t18_pierre_probe.py
"""
from __future__ import annotations

import json
import time

from agentfarm.bridge import BridgeClient

PIERRE_TILE = [4, 17]  # 来自存档 XML：Position X=256 Y=1088 ⇒ tile (4,17)
NEAR_TILES = [[4, 19], [5, 19], [3, 19], [4, 18], [5, 20], [6, 20]]


def snap(c, tag):
    o = c.observe("full")
    ui = o.get("ui") or {}
    p = o.get("player") or {}
    loc = o.get("location") or {}
    print(
        tag, "loc=", loc.get("name"), "tile=", p.get("tile"), "canMove=", p.get("canMove"),
        "clock=", (o.get("clock") or {}).get("timeOfDay"),
        "eventUp=", ui.get("eventUp"), "eventId=", ui.get("eventId"),
        "menu=", ui.get("activeMenu"), "modal=", ui.get("isModal"),
        "isQ=", ui.get("dialogueIsQuestion"),
        "text=", str(ui.get("activeMenuText"))[:120],
        "responses=", json.dumps(ui.get("dialogueResponses"), ensure_ascii=False),
    )
    return o


def clear_event_or_modal(c, tag, rounds=40):
    """把当前地点的事件/对话推到结束：提问用 dismiss_modal（自动挑否），非提问用 advance_dialogue。"""
    for i in range(rounds):
        o = snap(c, f"{tag}-{i}") if i == 0 else c.observe("full")
        ui = o.get("ui") or {}
        if not ui.get("eventUp") and not ui.get("isModal"):
            return True
        menu = ui.get("activeMenu")
        if menu == "DialogueBox":
            if ui.get("dialogueIsQuestion"):
                try:
                    r = c.dismiss_modal(timeout_ms=10000)
                    print("  DISMISS-Q ok=", getattr(r, "ok", None), str(getattr(r, "reason", None))[:200])
                except Exception as exc:  # noqa: BLE001
                    print("  DISMISS-Q ERR", type(exc).__name__, str(exc)[:250])
            else:
                try:
                    c.advance_dialogue(max_steps=10, timeout_ms=15000)
                except Exception as exc:  # noqa: BLE001
                    print("  ADV", type(exc).__name__, str(exc)[:160])
            time.sleep(1.2)
        elif menu:
            try:
                c.dismiss_modal(timeout_ms=8000)
            except Exception as exc:  # noqa: BLE001
                print("  DISMISS ERR", type(exc).__name__, str(exc)[:200])
            time.sleep(0.8)
        else:
            time.sleep(2.0)
    return False


def main() -> int:
    c = BridgeClient()
    ok = False
    for attempt in range(4):
        print(f"=== goto SeedShop attempt {attempt} ===")
        try:
            r = c.move_to_location("SeedShop", timeout_ms=150000)
            print("MOVE_LOC ok=", getattr(r, "ok", None), str(getattr(r, "reason", None))[:160])
        except Exception as exc:  # noqa: BLE001
            print("MOVE_LOC ERR", type(exc).__name__, str(exc)[:300])
        o = c.observe("full")
        if (o.get("location") or {}).get("name") == "SeedShop":
            ok = True
            break
        clear_event_or_modal(c, f"clear{attempt}")
    print("in_seedshop=", ok)
    if not ok:
        return 2
    snap(c, "arrived")
    time.sleep(1.0)
    clear_event_or_modal(c, "shopintro")
    snap(c, "after-intro")
    # walk to tiles adjacent to Pierre, then interact on Pierre's tile
    near = (c.observe("full").get("player") or {}).get("tile") or [0, 0]
    for t in NEAR_TILES:
        try:
            r = c.exec_skill("move_to", {"tile": t}, timeout_ms=60000)
            print("MOVE", t, "ok=", getattr(r, "ok", None), str(getattr(r, "reason", None))[:120])
        except Exception as exc:  # noqa: BLE001
            print("MOVE", t, "ERR", type(exc).__name__, str(exc)[:150])
        p = (c.observe("summary").get("player") or {}).get("tile")
        if p == t:
            break
    snap(c, "before-interact")
    tgt = PIERRE_TILE
    try:
        r = c.exec_skill("interact", {"tile": tgt}, timeout_ms=10000)
        print("INTERACT pierre tile", tgt, "ok=", getattr(r, "ok", None), "status=", getattr(r, "status", None),
              "reason=", str(getattr(r, "reason", None))[:300])
    except Exception as exc:  # noqa: BLE001
        print("INTERACT ERR", type(exc).__name__, str(exc)[:300])
    time.sleep(1.0)
    snap(c, "after-interact")
    print("RESULT done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
