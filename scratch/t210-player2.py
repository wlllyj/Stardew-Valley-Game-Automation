# -*- coding: utf-8 -*-
"""把存档里 player 的 craftingRecipes / skills / 背包原始 XML 片段打出来（只读）。

上一版脚本把 `<item>` 的**标签名**当配方名（全是 "item"）⇒ has_furnace_recipe 是解析假象。
这里直接抓原文，按文本判定。
"""
from __future__ import annotations

import os
import re
import sys

APPDATA = os.environ.get("APPDATA", "")
SAVE = os.path.join(APPDATA, "StardewValley", "Saves", "Wahaha_450799035", "Wahaha_450799035")


def main() -> int:
    save = SAVE
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--save" and i + 1 < len(args):
            save = args[i + 1]
    raw = open(save, "rb").read().decode("utf-8", "replace")
    for tag in ("craftingRecipes", "cookingRecipes", "skills", "basicShipped"):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", raw, re.S)
        if not m:
            print(f"[{tag}] 未找到")
            continue
        body = m.group(1)
        print(f"[{tag}] 长度 {len(body)}，出现 <item> {body.count('<item>')} 次")
        items = re.findall(r"<item>(.*?)</item>", body, re.S)
        print(f"  前 40 个条目原文: {items[:40]}")
        ints = re.findall(r"<int>(.*?)</int>", body, re.S)
        if ints:
            print(f"  <int> 共 {len(ints)} 个: {ints[:20]}")
        strs = re.findall(r"<string>(.*?)</string>", body, re.S)
        if strs:
            print(f"  <string> 共 {len(strs)} 个: {strs[:40]}")
    # 关键词直查
    for kw in ("Furnace", "Charcoal Kiln", "114", "Copper Bar", "(O)334", "MineShaft", "Blast Furnace"):
        print(f"含 {kw!r} = {kw in raw}")
    # 配方里有没有"熔炉"
    m = re.search(r"<craftingRecipes>(.*?)</craftingRecipes>", raw, re.S)
    if m:
        rec = re.findall(r"<item>(.*?)</item>", m.group(1), re.S)
        hit = [r for r in rec if "furnace" in r.lower()]
        print(f"\n配方里含 furnace 的条目: {hit}")
        print(f"（若为空则确实不会造熔炉；理论熔炉配方名 = 'Furnace'）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
