# -*- coding: utf-8 -*-
"""读存档 player 的 experiencePoints / maxStamina / toolBeingUpgraded 等原值（只读）。"""
from __future__ import annotations

import os
import re
import sys

APPDATA = os.environ.get("APPDATA", "")
SAVE = os.path.join(APPDATA, "StardewValley", "Saves", "Wahaha_450799035", "Wahaha_450799035")
SKILLS = ["farming", "fishing", "foraging", "mining", "combat", "luck"]
LEVELS = [100, 380, 770, 1300, 2150, 3300, 5300, 8500, 14000, 25000]


def level_of(xp: int) -> int:
    n = 0
    for t in LEVELS:
        if xp >= t:
            n += 1
    return n


def main() -> int:
    save = SAVE
    raw = open(save, "rb").read().decode("utf-8", "replace")
    m = re.search(r"<player>(.*?)</player>", raw, re.S)
    body = m.group(1) if m else ""
    xp = re.search(r"<experiencePoints>(.*?)</experiencePoints>", body, re.S)
    vals = re.findall(r"<int>(.*?)</int>", xp.group(1), re.S) if xp else []
    vals = [int(v) for v in vals[:6]]
    print("experiencePoints =", vals)
    for i, v in enumerate(vals):
        name = SKILLS[i] if i < len(SKILLS) else f"idx{i}"
        print(f"  {name:9} xp={v:>6} level={sum(1 for t in LEVELS if v >= t)}")
    for tag in ("maxStamina", "maxItems", "toolBeingUpgraded", "daysLeftForToolUpgrade", "deepestMineLevel",
                "totalMoneyEarned", "houseUpgradeLevel", "canUnderstandDwarves"):
        mm = re.search(rf"<{tag}>(.*?)</{tag}>", body, re.S)
        print(f"{tag} = {mm.group(1) if mm else None}")
    mining = vals[3] if len(vals) > 3 else 0
    print(f"\n⇒ 采矿等级 = {level_of(mining)}（熔炉配方在采矿 1 级解锁；当前配方表里没有 Furnace）")
    print(f"   从 0 到 1 级还需 {max(0, 100 - mining)} 点采矿经验（普通石头约 5 XP/块 ⇒ 约 {max(0, (100 - mining + 4) // 5)} 块石头）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
