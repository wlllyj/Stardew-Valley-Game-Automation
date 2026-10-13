# -*- coding: utf-8 -*-
"""只读取证：从存档 XML 里列出 FarmHouse / Farm 的家具（含 isBed）与 warp 表。

用法：
    python scratch\\_probe_save_bed.py [存档路径...]
默认读 %APPDATA%\\StardewValley\\Saves\\Wahaha_450799035\\Wahaha_450799035
（以及同名 _old 存档，便于对比）。

只读：不写游戏目录、不发任何 HTTP。
"""
from __future__ import annotations

import os
import pathlib
import sys
import xml.etree.ElementTree as ET

DEFAULT_SAVE_DIR = pathlib.Path(os.environ.get("APPDATA", "")) / "StardewValley" / "Saves" / "Wahaha_450799035"

WANT = ("FarmHouse", "Farm", "FarmCave", "Greenhouse")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def type_attr(el: ET.Element) -> str:
    for k, v in el.attrib.items():
        if k.endswith("}type") or k == "type":
            return v
    return ""


def find_child(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if local(c.tag) == name:
            return c
    return None


def find_locations(root: ET.Element) -> ET.Element | None:
    # <locations> 可能在根下，也可能嵌在 <gameState> 之类里；递归找第一个。
    for el in root.iter():
        if local(el.tag) == "locations":
            return el
    return None


def dump_furniture(loc: ET.Element) -> None:
    furns = [c for c in loc if local(c.tag) == "furniture"]
    items: list[ET.Element] = []
    for holder in furns:
        items.extend(list(holder))
    print(f"  家具 {len(items)} 件：")
    for i, f in enumerate(items):
        fields = {local(c.tag): (c.text or "").strip() for c in f}
        keep = {k: v for k, v in fields.items() if k in (
            "tileX", "tileY", "TileX", "TileY", "isBed", "furniture_type", "furnitureType",
            "name", "bedType", "currentRotation", "rotation", "heldObject", "sourceRect",
            "defaultSourceRect", "drawHeldObjectLow", "canBeRemoved", "modData")}
        print(f"    [{i}] tag={local(f.tag)} type={type_attr(f)!r} "
              f"tile=({fields.get('tileX')},{fields.get('tileY')}) "
              f"isBed={fields.get('isBed')} furniture_type={fields.get('furniture_type')} "
              f"name={fields.get('name')!r}")
        print(f"        全字段: {keep}")


def dump_warps(loc: ET.Element, label: str) -> None:
    holders = [c for c in loc if local(c.tag) == "warps"]
    warps: list[ET.Element] = []
    for h in holders:
        warps.extend(list(h))
    print(f"  {label} warp {len(warps)} 条：")
    for w in warps:
        fields = {local(c.tag): (c.text or "").strip() for c in w}
        print(f"    ({fields.get('X') or fields.get('x')},{fields.get('Y') or fields.get('y')})"
              f" -> {fields.get('TargetName') or fields.get('targetName')!r}"
              f"@({fields.get('TargetX') or fields.get('targetX')},{fields.get('TargetY') or fields.get('targetY')})"
              f" 全字段={fields}")


def dump_doors(loc: ET.Element) -> None:
    for name in ("doors", "Doors"):
        holder = find_child(loc, name)
        if holder is None:
            continue
        items = list(holder)
        print(f"  doors {len(items)} 条：")
        for d in items:
            fields = {local(c.tag): (c.text or "").strip() for c in d}
            print(f"    tag={local(d.tag)} type={type_attr(d)!r} {fields}")
        return
    print("  doors: (无)")


def dump_tiles_summary(loc: ET.Element) -> None:
    holder = find_child(loc, "tiles") or find_child(loc, "map")
    if holder is None:
        print("  tiles: (无该节点)")
        return
    kids = [local(c.tag) for c in holder]
    print(f"  {local(holder.tag)} 子节点 {len(kids)} 个，前 20 种：{sorted(set(kids))[:20]}")


def main(argv: list[str]) -> int:
    paths: list[pathlib.Path] = []
    if argv:
        paths = [pathlib.Path(a) for a in argv]
    else:
        paths = [DEFAULT_SAVE_DIR / "Wahaha_450799035",
                 DEFAULT_SAVE_DIR / "Wahaha_450799035_old"]
    for p in paths:
        print("=" * 78)
        print(f"存档：{p}  存在={p.exists()}")
        if not p.exists():
            continue
        try:
            tree = ET.parse(p)
        except Exception as exc:  # noqa: BLE001
            print(f"  解析失败：{exc!r}")
            continue
        root = tree.getroot()
        print(f"  根节点：{local(root.tag)}")
        locs = find_locations(root)
        if locs is None:
            print("  找不到 <locations>")
            continue
        print(f"  locations 子节点：{len(list(locs))}")
        for loc in locs:
            t = type_attr(loc)
            short = t.split(".")[-1] if t else local(loc.tag)
            if not any(w in short for w in WANT):
                continue
            print("-" * 74)
            print(f"地点：type={t!r} name={find_child(loc, 'name').text if find_child(loc, 'name') is not None else '?'}")
            dump_furniture(loc)
            dump_warps(loc, short)
            dump_doors(loc)
            dump_tiles_summary(loc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
