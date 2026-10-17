# -*- coding: utf-8 -*-
"""task-209 §2 交叉验证：从**存档 XML**里读农场已放置的 object（只读，不碰游戏）。

背景：真机 3×3 网格只走到 3 个点（6 个锚点 unreachable），3 个窗口里 `kind=="object"` 都是 0，
但 `location.objects=689`（几乎全是石/枝/杂草）。为了给出"农场到底有没有熔炉/炭窑/箱子"的
**可复核清单**，直接解析存档主文件 `<locations>` 里 Farm 的 `<objects>` —— 这是游戏自己的真值。

用法：python scratch\\t210-save-objects.py [--save <path>] [--out scratch\\t210-farm-objects.json]
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


def localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(el, name):
    for c in list(el):
        if localname(c.tag) == name:
            return c
    return None


def text_of(el, name, default=None):
    c = child(el, name)
    return (c.text or "").strip() if c is not None and c.text is not None else default


def main() -> int:
    save = DEFAULT_SAVE
    out_path = os.path.join(REPO, "scratch", "t210-farm-objects.json")
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--save" and i + 1 < len(args):
            save = args[i + 1]
        if a == "--out" and i + 1 < len(args):
            out_path = args[i + 1]
    print(f"save = {save}  ({os.path.getsize(save)} B, mtime={os.path.getmtime(save):.3f})")
    raw = open(save, "rb").read()
    head = raw[:200].decode("utf-8", "replace")
    print(f"head = {head[:120]!r}")
    print(f"含 'Furnace' 字样 = {b'Furnace' in raw}；含 '<objects' = {b'<objects' in raw}；含 'BigCraftable' = {b'BigCraftable' in raw}")
    root = ET.fromstring(raw)
    print(f"root = {localname(root.tag)}")
    locs = child(root, "locations")
    if locs is None:
        print("!! 找不到 <locations>")
        return 2
    farm = None
    kinds = []
    for loc in list(locs):
        t = loc.get("{http://www.w3.org/2001/XMLSchema-instance}type") or ""
        name = text_of(loc, "name") or text_of(loc, "Name") or ""
        kinds.append((localname(loc.tag), t, name))
        if t == "Farm" or name == "Farm":
            farm = loc
    print(f"<locations> 子元素 {len(kinds)} 个；前 8 个 = {kinds[:8]}")
    if farm is None:
        print("!! 找不到 Farm location")
        return 3
    objs = child(farm, "objects")
    if objs is None:
        print("!! Farm 没有 <objects>")
        return 4
    rows = []
    for item in list(objs):
        key = child(item, "key")
        val = child(item, "value")
        if key is None or val is None:
            continue
        vec = child(key, "Vector2") or key
        x = text_of(vec, "X")
        y = text_of(vec, "Y")
        inner = val
        # 有些存档是 <value><Object ...>，有些直接是 <value xsi:type="Object">
        for cand in list(val):
            if localname(cand.tag) in ("Object", "Item", "BigCraftable", "Furniture", "Chest"):
                inner = cand
                break
        item_id = text_of(inner, "itemId") or text_of(inner, "ItemId") or ""
        name = text_of(inner, "name") or text_of(inner, "Name") or ""
        qid = text_of(inner, "qualifiedItemId") or text_of(inner, "QualifiedItemId") or ""
        is_bc = (text_of(inner, "bigCraftable") or text_of(inner, "BigCraftable") or "").lower()
        ready = text_of(inner, "minutesUntilReady")
        held = child(inner, "heldObject")
        held_id = ""
        held_name = ""
        if held is not None:
            hv = held
            for cand in list(held):
                if localname(cand.tag) in ("Object", "Item"):
                    hv = cand
                    break
            held_id = text_of(hv, "itemId") or text_of(hv, "ItemId") or ""
            held_name = text_of(hv, "name") or text_of(hv, "Name") or ""
        rows.append({"x": int(x) if x and x.lstrip("-").isdigit() else x,
                     "y": int(y) if y and y.lstrip("-").isdigit() else y,
                     "itemId": item_id, "qualifiedItemId": qid, "name": name,
                     "bigCraftable": is_bc, "minutesUntilReady": ready,
                     "heldObject": {"itemId": held_id, "name": held_name} if held is not None else None})
    print(f"\nFarm <objects> 条目 = {len(rows)}")
    by_id = Counter((r["qualifiedItemId"] or r["itemId"], r["name"]) for r in rows)
    print("按 itemId/name 计数：")
    for (iid, nm), cnt in by_id.most_common(25):
        print(f"   {str(iid):16} {nm[:34]:34} × {cnt}")
    # 机器类：有 minutesUntilReady / heldObject / 名字匹配常见机器
    MACHINE_NAMES = ("Furnace", "Charcoal Kiln", "Chest", "Stone Chest", "Tapper", "Keg", "Preserves Jar",
                     "Mayonnaise", "Cheese Press", "Loom", "Oil Maker", "Crystalarium", "Lightning Rod",
                     "Recycling Machine", "Seed Maker", "Sprinkler", "Scarecrow", "Silo", "Junimo Hut",
                     "Cask", "Dehydrator", "Fish Smoker", "Bait And Bobber", "Wood Chipper", "Heavy Furnace")
    machines = [r for r in rows if any(m.lower() in (r["name"] or "").lower() for m in MACHINE_NAMES)]
    print(f"\n机器/家具类条目 = {len(machines)}")
    for r in machines[:40]:
        print(f"   ({r['x']:>3},{r['y']:>3}) {str(r['qualifiedItemId'] or r['itemId']):12} {r['name']}")
    payload = {
        "source": "save-xml（只读解析，游戏真值）",
        "save_file": save,
        "save_size": os.path.getsize(save),
        "save_mtime": os.path.getmtime(save),
        "farm_location_type": "Farm",
        "objects_total": len(rows),
        "by_item": [{"itemId": i, "name": n, "count": c} for (i, n), c in by_id.most_common()],
        "machines": machines,
        "objects": rows,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"\n已写出 {out_path}（{os.path.getsize(out_path)} B）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
