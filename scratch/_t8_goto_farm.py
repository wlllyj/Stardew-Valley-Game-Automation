"""task-8 冒烟前置：把玩家从 FarmHouse 走到 Farm（步 3 要求 isOutdoorFarm）。
只读 + 移动，不做世界写入；用法：PYTHONUTF8=1 python scratch/_t8_goto_farm.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402


def main() -> int:
    c = BridgeClient()
    obs0 = c.observe(detail="full")
    loc0 = (obs0.get("location") or {}).get("name")
    before = {"location": loc0,
              "player": (obs0.get("player") or {}).get("tile"),
              "clock": obs0.get("clock")}
    print(json.dumps({"before": before}, ensure_ascii=False))
    if loc0 == "Farm":
        print(json.dumps({"action": "already_on_farm", "ok": True}, ensure_ascii=False))
    else:
        res = c.move_to_location("Farm", timeout_ms=120000)
        print(json.dumps({"action": "move_to_location(Farm)", "result": res}, ensure_ascii=False))
    obs1 = c.observe(detail="full")
    loc1 = obs1.get("location") or {}
    after = {"location": loc1.get("name"),
             "isOutdoorFarm": loc1.get("isOutdoorFarm"),
             "player": (obs1.get("player") or {}).get("tile"),
             "clock": obs1.get("clock"),
             "tiles": len(loc1.get("tiles") or []),
             "plots": len(loc1.get("plots") or [])}
    print(json.dumps({"after": after}, ensure_ascii=False))
    return 0 if loc1.get("isOutdoorFarm") else 1


if __name__ == "__main__":
    raise SystemExit(main())
