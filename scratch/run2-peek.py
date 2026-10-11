# -*- coding: utf-8 -*-
"""只看关键字段：day_end 的 final/stages、review 记录、plot_exhausted、结束态里的水/作物真值。"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
J = REPO / "logs" / "longrun-3day-llm-run2.jsonl"
END = REPO / "logs" / "run2-observe-end.json"

recs = [json.loads(l) for l in J.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]

print("=== day_end[88].final ===")
print(json.dumps(recs[88].get("final"), ensure_ascii=False, indent=1))
print("=== day_end[88].stages ===")
print(json.dumps(recs[88].get("stages"), ensure_ascii=False))
print("=== day_end[91].final ===")
print(json.dumps(recs[91].get("final"), ensure_ascii=False, indent=1))
print("=== day_end[91].notes ===")
print(json.dumps(recs[91].get("notes"), ensure_ascii=False))

print("=== review 记录 ===")
for r in recs:
    if r.get("event") == "review":
        print(json.dumps(r, ensure_ascii=False))

print("=== plot_exhausted 记录 ===")
for r in recs:
    if r.get("event") == "plot_exhausted":
        print(json.dumps(r, ensure_ascii=False))

end = json.loads(END.read_text(encoding="utf-8"))
farm = end.get("farm") or {}
print("=== 结束态 farm（原始键值）===")
print(json.dumps(farm, ensure_ascii=False))
tiles = ((end.get("location") or {}).get("tiles")) or []
print(f"=== 结束态 location.tiles: {len(tiles)} 格；tilesTruncated="
      f"{(end.get('location') or {}).get('tilesTruncated')} ===")
crop_tiles = [t for t in tiles if t.get("crop")]
print(f"其中带 crop 的格：{len(crop_tiles)}")
for t in crop_tiles[:12]:
    print("  " + json.dumps(t, ensure_ascii=False)[:300])
watered = [t for t in tiles if t.get("kind") in ("dirt", "hoeDirt", "tilled")]
print(f"kind 像耕地的格：{len(watered)}；样本：")
for t in watered[:6]:
    print("  " + json.dumps(t, ensure_ascii=False)[:300])
