# -*- coding: utf-8 -*-
"""只读取证：打印存档里某个 GameLocation 的原始 XML 片段（默认 FarmHouse 的 furniture）。

用法：
    python scratch\\_probe_save_raw.py FarmHouse furniture 3
    python scratch\\_probe_save_raw.py FarmHouse warps 3
"""
from __future__ import annotations

import os
import pathlib
import sys
import xml.etree.ElementTree as ET

SAVE = (pathlib.Path(os.environ.get("APPDATA", "")) / "StardewValley" / "Saves"
        / "Wahaha_450799035" / "Wahaha_450799035")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def type_attr(el: ET.Element) -> str:
    for k, v in el.attrib.items():
        if k.endswith("}type") or k == "type":
            return v
    return ""


def main(argv: list[str]) -> int:
    loc_name = argv[0] if argv else "FarmHouse"
    section = argv[1] if len(argv) > 1 else "furniture"
    limit = int(argv[2]) if len(argv) > 2 else 2
    tree = ET.parse(SAVE)
    root = tree.getroot()
    for locs in root.iter():
        if local(locs.tag) != "locations":
            continue
        for loc in locs:
            if type_attr(loc) == loc_name:
                for holder in loc:
                    if local(holder.tag) != section:
                        continue
                    print(f"### {loc_name} / {section}  子节点 {len(list(holder))} 个")
                    for i, child in enumerate(list(holder)[:limit]):
                        print(f"--- [{i}] {ET.tostring(child, encoding='unicode')[:1500]}")
                print(f"### {loc_name} 的直接子节点：{[local(c.tag) + ('(' + type_attr(c) + ')') if type_attr(c) else '' for c in loc]}")
        break
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
