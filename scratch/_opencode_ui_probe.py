# -*- coding: utf-8 -*-
"""只读探针：把 observe 的 ui / clock / location 原样打出来（不改世界）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from agentfarm.bridge import BridgeClient  # noqa: E402

c = BridgeClient(timeout=30.0)
obs = c.observe(detail="full")
print("=== ui ===")
print(json.dumps(obs.get("ui"), ensure_ascii=False, indent=2))
print("=== clock ===")
print(json.dumps(obs.get("clock"), ensure_ascii=False))
print("=== player(部分) ===")
p = obs.get("player") or {}
print(json.dumps({k: p.get(k) for k in ("location", "tile", "canMove", "isInBed", "stamina", "money")}, ensure_ascii=False))
print("=== location 摘要 ===")
loc = obs.get("location") or {}
print(json.dumps({k: loc.get(k) for k in ("name", "isOutdoorFarm", "isFarm", "objects", "debris", "terrainFeatures")}, ensure_ascii=False))
print("=== worldSeq ===", obs.get("worldSeq"))
