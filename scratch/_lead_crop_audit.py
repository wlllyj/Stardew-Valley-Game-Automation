"""Lead 只读探针：当前农场里 作物/枯死/干格 的真实分布（一次 observe，不改世界）。

用法：python scratch/_lead_crop_audit.py
"""
import json
import sys

sys.path.insert(0, r"brain")
from agentfarm.bridge import BridgeClient  # noqa: E402

c = BridgeClient()
obs = c.observe("full")
loc = obs.get("location") or {}
farm = obs.get("farm") or {}
player = obs.get("player") or {}
clock = obs.get("clock") or {}

print("day=%s %s %s tod=%s loc=%s player=%s" % (
    clock.get("year"), clock.get("season"), clock.get("day"), clock.get("timeOfDay"),
    loc.get("name"), player.get("tile")))
print("farm:", json.dumps({k: farm.get(k) for k in
                           ("complete", "loaded", "crops", "ripeCrops", "deadCrops",
                            "dryCrops", "unwateredCrops", "hoeDirt", "emptyDirt", "tillable")},
                          ensure_ascii=False))
tiles = loc.get("tiles") or []
print("window tiles=%d truncated=%s" % (len(tiles), loc.get("tilesTruncated")))

crop_tiles = [t for t in tiles if t.get("crop")]
dead = [t for t in crop_tiles if t.get("dead")]
dry = [t for t in crop_tiles if not t.get("watered")]
ripe = [t for t in crop_tiles if t.get("ripe")]
print("窗口内：crop 格 %d / dead %d / ripe %d / dry %d" % (len(crop_tiles), len(dead), len(ripe), len(dry)))
for t in crop_tiles[:12]:
    print("   %s crop=%s dead=%s ripe=%s watered=%s kind=%s" % (
        (t.get("x"), t.get("y")) if "x" in t else t.get("tile"),
        t.get("crop"), t.get("dead"), t.get("ripe"), t.get("watered"), t.get("kind")))
print("dryTiles 字段存在？", "dryTiles" in farm)
