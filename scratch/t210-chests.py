# -*- coding: utf-8 -*-
"""看存档里所有箱子/冰箱的内容（只读）。

城镇/农场都没有铜锭，但 FarmHouse 有 1 个 Chest @ (3,7) —— 先看它装了什么，
这直接决定「5 条铜锭最省路径」有没有捷径（A′：箱子里本来就有锭/矿/煤）。
"""
from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET

APPDATA = os.environ.get("APPDATA", "")
SAVE = os.path.join(APPDATA, "StardewValley", "Saves", "Wahaha_450799035", "Wahaha_450799035")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))


def ln(t):
    return t.rsplit("}", 1)[-1]


def child(el, name):
    for c in list(el):
        if ln(c.tag) == name:
            return c
    return None


def txt(el, name, default=None):
    c = child(el, name)
    return (c.text or "").strip() if c is not None and c.text is not None else default


def inv_items(inv):
    out = []
    if inv is None:
        return out
    for it in list(inv):
        inner = it
        for cand in list(it):
            if ln(cand.tag) in ("Object", "Item", "Tool", "BigCraftable"):
                inner = cand
                break
        iid = txt(inner, "itemId") or txt(inner, "ItemId") or ""
        nm = txt(inner, "name") or txt(inner, "Name") or ""
        st = txt(inner, "stack") or "0"
        pr = txt(inner, "price")
        if iid or nm:
            out.append({"id": iid, "name": nm, "stack": int(st or 0), "price": pr})
    return out


def main() -> int:
    raw = open(SAVE, "rb").read()
    root = ET.fromstring(raw)
    locs = child(root, "locations")
    found = []
    for loc in list(locs):
        name = txt(loc, "name") or txt(loc, "Name") or ln(loc.tag)
        # 直接在所有后代里找 name == Chest 的节点
        for el in loc.iter():
            if ln(el.tag) in ("Chest",) or (txt(el, "name") == "Chest"):
                items = []
                for tag in ("items", "Items"):
                    c = child(el, tag)
                    if c is not None:
                        items = inv_items(c)
                        break
                found.append({"location": name, "items": items, "n_items": len(items)})
        # 冰箱
        fr = child(loc, "fridge")
        if fr is not None:
            found.append({"location": name, "kind": "fridge", "items": inv_items(fr), "n_items": len(inv_items(fr))})
    # 去重（Chest 节点可能被遍历两次）
    uniq = []
    seen = set()
    for f in found:
        key = (f["location"], f.get("kind", "chest"), json.dumps(f["items"], ensure_ascii=False, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)
    print(json.dumps(uniq, ensure_ascii=False, indent=2)[:6000])
    out = os.path.join(REPO, "scratch", "t210-chest-contents.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(uniq, fh, ensure_ascii=False, indent=2)
    print(f"\n已写出 {out}（{os.path.getsize(out)} B）")
    # 直查关键词
    for kw in ("Copper Bar", "(O)334", "334", "Copper Ore", "Coal"):
        print(f"save 含 {kw!r} = {kw in raw.decode('utf-8', 'replace')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
