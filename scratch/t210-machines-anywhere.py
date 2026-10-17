# -*- coding: utf-8 -*-
"""task-209 补充：全地点机器扫描 + 熔炉配方/技能/材料盘点（只读解析存档 XML）。

回答四个问题：
1. 任何地点（含 FarmHouse / FarmCave / 其它已解锁地点）里有没有机器（Furnace / Charcoal Kiln / Chest …）；
2. 玩家会不会造熔炉（`craftingRecipes` 里有没有 "Furnace"）；
3. 玩家采矿手艺（`skills`/`miningLevel`）与当前材料（背包 + 存档里 Farm 的石头数）；
4. `Data/Shops`-side 能买到的与"必须自采"的分界。
"""
from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

APPDATA = os.environ.get("APPDATA", "")
DEFAULT_SAVE = os.path.join(APPDATA, "StardewValley", "Saves", "Wahaha_450799035", "Wahaha_450799035")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))

MACHINE_WORDS = ("furnace", "charcoal kiln", "chest", "keg", "preserves jar", "mayonnaise", "cheese press",
                 "loom", "oil maker", "crystalarium", "lightning rod", "recycling machine", "seed maker",
                 "sprinkler", "scarecrow", "cask", "dehydrator", "fish smoker", "wood chipper", "tapper",
                 "silo", "junimo", "auto-grabber", "auto-grabber", "crab pot", "furniture")


def ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(el, name):
    for c in list(el):
        if ln(c.tag) == name:
            return c
    return None


def text_of(el, name, default=None):
    c = child(el, name)
    return (c.text or "").strip() if c is not None and c.text is not None else default


def main() -> int:
    save = DEFAULT_SAVE
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--save" and i + 1 < len(args):
            save = args[i + 1]
    raw = open(save, "rb").read()
    root = ET.fromstring(raw)
    locs = child(root, "locations")
    report = {"save": save, "save_size": len(raw), "locations": {}, "machines_anywhere": [],
              "player": {}, "farm_debris": {}}
    for loc in list(locs):
        t = loc.get("{http://www.w3.org/2001/XMLSchema-instance}type") or ""
        name = text_of(loc, "name") or text_of(loc, "Name") or ln(loc.tag)
        objs = child(loc, "objects")
        if objs is None:
            continue
        rows = []
        for item in list(objs):
            key = child(item, "key")
            val = child(item, "value")
            if key is None or val is None:
                continue
            vec = child(key, "Vector2")
            vec = vec if vec is not None else key
            x, y = text_of(vec, "X"), text_of(vec, "Y")
            inner = val
            for cand in list(val):
                if ln(cand.tag) in ("Object", "Item", "BigCraftable", "Chest", "Furniture"):
                    inner = cand
                    break
            iid = text_of(inner, "itemId") or text_of(inner, "ItemId") or ""
            nm = text_of(inner, "name") or text_of(inner, "Name") or ""
            rows.append({"x": x, "y": y, "itemId": iid, "name": nm})
        if not rows:
            continue
        by = Counter((r["itemId"], r["name"]) for r in rows)
        report["locations"][name or t] = {"type": t, "objects": len(rows),
                                          "by_item": [{"itemId": i, "name": n, "count": c} for (i, n), c in by.most_common(12)]}
        hits = [r for r in rows if any(w in (r["name"] or "").lower() for w in MACHINE_WORDS)]
        if hits:
            report["machines_anywhere"].append({"location": name or t, "count": len(hits), "rows": hits[:20]})
        if (name or t) == "Farm":
            report["farm_debris"] = {"objects": len(rows),
                                     "by_item": [{"itemId": i, "name": n, "count": c} for (i, n), c in by.most_common(12)]}
    # 玩家侧：配方 / 技能 / 背包
    player = child(root, "player")
    if player is not None:
        rec = child(player, "craftingRecipes")
        recipes = [ln(c.tag) for c in list(rec)] if rec is not None else []
        try:
            keys = [ (c.get("xsi:key") or c.get("key") or ln(c.tag)) for c in list(rec)] if rec is not None else []
        except Exception:  # noqa: BLE001
            keys = []
        skills = child(player, "skills")
        skill_vals = {}
        if skills is not None:
            for k in ("farming", "fishing", "foraging", "mining", "combat", "luck"):
                skill_vals[k] = text_of(skills, k)
        inv = child(player, "items")
        inv_rows = []
        if inv is not None:
            for it in list(inv):
                inner = it
                for cand in list(it):
                    if ln(cand.tag) in ("Object", "Item", "Tool", "BigCraftable"):
                        inner = cand
                        break
                inv_rows.append({"id": text_of(inner, "itemId") or text_of(inner, "ItemId") or "",
                                 "qid": text_of(inner, "qualifiedItemId") or "",
                                 "name": text_of(inner, "name") or text_of(inner, "Name") or "",
                                 "stack": text_of(inner, "stack")})
        report["player"] = {"name": text_of(player, "name"), "money": text_of(player, "money"),
                            "skills": skill_vals,
                            "crafting_recipe_nodes": recipes[:60],
                            "has_furnace_recipe": any("furnace" in (r or "").lower() for r in recipes),
                            "inventory": inv_rows}
    print(json.dumps({k: report[k] for k in ("machines_anywhere", "player")}, ensure_ascii=False, indent=2)[:4000])
    print("\n各地点 objects（只列非空）：")
    for k, v in report["locations"].items():
        print(f"  {k:22} {v['objects']:>4}  {v['by_item'][:4]}")
    print(f"\nFarm 杂物汇总：{json.dumps(report['farm_debris'], ensure_ascii=False)}")
    out = os.path.join(REPO, "scratch", "t210-machines-anywhere.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"已写出 {out}（{os.path.getsize(out)} B）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
