"""一次性探针：看游戏当前是不是被弹窗/菜单挡住（level up 之类）。

只读，不发任何技能。用法：
    PYTHONPATH=<repo>/brain python scratch/ui_state.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402


def main() -> int:
    client = BridgeClient(timeout=15.0)
    health = client.health()
    print("health:", json.dumps(health, ensure_ascii=False, indent=2))
    obs = client.observe("full")
    print("worldSeq:", obs.get("worldSeq"), "schema:", obs.get("schema"))
    print("clock:", json.dumps(obs.get("clock"), ensure_ascii=False))
    print("ui:", json.dumps(obs.get("ui"), ensure_ascii=False, indent=2))
    print("player:", json.dumps(obs.get("player"), ensure_ascii=False)[:1200])
    loc = obs.get("location") or {}
    print("location:", loc.get("name"), "isOutdoorFarm:", loc.get("isOutdoorFarm"))
    print("liveness:", json.dumps(obs.get("liveness"), ensure_ascii=False))
    print("game:", json.dumps(obs.get("game"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
