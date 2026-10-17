# -*- coding: utf-8 -*-
"""从 scratch/t210-machines-anywhere.json 紧凑打印玩家侧与地点汇总（只读）。"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(HERE, "t210-machines-anywhere.json")
d = json.load(open(p, encoding="utf-8"))
pl = d.get("player") or {}
print("== player ==")
for k in ("name", "money", "skills", "has_furnace_recipe", "crafting_recipe_nodes"):
    print(f"{k} = {pl.get(k)}")
print("\n== inventory ==")
for r in pl.get("inventory") or []:
    print(f"  id={r.get('id'):>6} qid={r.get('qid')!r:>12} name={r.get('name')!r:22} stack={r.get('stack')}")
print("\n== locations（objects 非空）==")
for k, v in (d.get("locations") or {}).items():
    print(f"  {k:22} n={v.get('objects'):>4} type={v.get('type')!r}")
    print(f"       {json.dumps(v.get('by_item')[:6], ensure_ascii=False)}")
print("\n== farm_debris ==")
print(json.dumps(d.get("farm_debris"), ensure_ascii=False))
