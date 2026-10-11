"""一眼看清当前真机状态（读 brain\\run\\observe-full.json，不连桥）。"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "brain" / "run" / "observe-full.json"
obs = json.loads(path.read_text(encoding="utf-8"))

clock = obs.get("clock") or {}
loc = obs.get("location") or {}
player = obs.get("player") or {}
inv = player.get("inventory") or []
tiles = loc.get("tiles") or []

print(f"schema={obs.get('schema')} hasSaveLoaded={obs.get('hasSaveLoaded')}")
print(f"时间：第{clock.get('year')}年 {clock.get('season')} {clock.get('day')}日 {clock.get('timeOfDay')}  "
      f"天气 {clock.get('weather')}")
print(f"地点：{loc.get('name')}（户外农场={loc.get('isOutdoorFarm')}） 玩家 {player.get('tile')} "
      f"体力 {player.get('stamina')}/{player.get('maxStamina')} 钱 {player.get('money')}g "
      f"在床={player.get('isInBed')}")
wc = player.get("wateringCan") or {}
print(f"水壶：{wc.get('waterLeft')}/{wc.get('max')} 无尽={wc.get('bottomless')}")
print(f"背包 {len(inv)} 格：")
for it in inv:
    print(f"  slot{it.get('slot'):>2} {it.get('name')} ({it.get('id')}) x{it.get('stack')}"
          f"{' [工具]' if it.get('isTool') else ''}")
print(f"tiles {len(tiles)} 格（tilesTruncated={loc.get('tilesTruncated')}）"
      f" tillable {len(loc.get('tillable') or [])} 格"
      f"（truncated={loc.get('tillableTruncated')}）")
kinds: dict[str, int] = {}
for t in tiles:
    kinds[t.get("kind")] = kinds.get(t.get("kind"), 0) + 1
print("  kinds:", dict(sorted(kinds.items(), key=lambda kv: -kv[1])))
crops = [t for t in tiles if t.get("crop")]
print(f"  作物 {len(crops)} 格；未浇 {sum(1 for t in crops if not t.get('watered'))}"
      f"；成熟 {sum(1 for t in crops if t.get('ripe'))}")
print(f"  可种（plantable）{sum(1 for t in tiles if t.get('plantable'))} 格")
print(f"refillTiles {len(loc.get('refillTiles') or [])} 个；furniture {len(loc.get('furniture') or [])} 件")
