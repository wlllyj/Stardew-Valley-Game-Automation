# -*- coding: utf-8 -*-
"""只读：看看游戏现在卡在哪个界面（Pass-out 提示？模态对话框？），用于判断能否直接开跑。"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brain")))

from agentfarm.bridge import BridgeClient  # noqa: E402


def main() -> int:
    c = BridgeClient()
    o = c.observe("full")
    for key in ("worldSeq", "generatedAt", "hasSaveLoaded", "clock", "ui", "location", "game", "liveness"):
        v = o.get(key)
        if key == "location" and isinstance(v, dict):
            v = {k: v.get(k) for k in ("name", "isOutdoors", "isFarm", "isGreenhouse",
                                       "tilesTruncated", "furnitureTruncated")}
            v["furniture"] = (o.get("location") or {}).get("furniture")
        print(f"{key:15s} = {json.dumps(v, ensure_ascii=False)[:900]}")
    p = o.get("player") or {}
    print("player.tools   =", json.dumps(p.get("tools"), ensure_ascii=False)[:400])
    keep = {k: v for k, v in p.items() if k != "inventory"}
    print("player(full)   =", json.dumps(keep, ensure_ascii=False)[:1400])
    print("player.keys    =", sorted(p.keys()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
