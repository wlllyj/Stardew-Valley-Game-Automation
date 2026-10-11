# -*- coding: utf-8 -*-
"""只读：现在这一刻的真实状态（observe summary），用于核对 run2 之后世界有没有自己前进。"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brain")))

from agentfarm.bridge import BridgeClient, load_bridge_info, pid_alive  # noqa: E402


def main() -> int:
    info = load_bridge_info()
    pid = info.get("pid") if isinstance(info, dict) else None
    print(f"bridge.json pid={pid} modVersion={info.get('modVersion') if isinstance(info, dict) else None} "
          f"pid_alive={pid_alive(pid) if pid else '?'}")

    c = BridgeClient()
    h = c.health()
    print("health.runtime =", json.dumps(h.get("runtime"), ensure_ascii=False))

    o = c.observe("summary")
    print("worldSeq =", o.get("worldSeq"), " generatedAt =", o.get("generatedAt"))
    print("clock    =", json.dumps(o.get("clock"), ensure_ascii=False))
    p = o.get("player") or {}
    print("player   =", json.dumps({k: p.get(k) for k in
                                    ("name", "location", "tile", "stamina", "maxStamina",
                                     "money", "inventoryCount", "isInBed", "canMove")},
                                   ensure_ascii=False))
    print("watering =", json.dumps(p.get("wateringCan"), ensure_ascii=False))
    print("farm     =", json.dumps({k: v for k, v in (o.get("farm") or {}).items() if k != "tiles"},
                                   ensure_ascii=False))
    print("liveness =", json.dumps(o.get("liveness"), ensure_ascii=False))
    print("game     =", json.dumps(o.get("game"), ensure_ascii=False))
    inv = p.get("inventory") or []
    print("inventory =", "、".join(f"{e.get('name')}x{e.get('stack')}" for e in inv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
