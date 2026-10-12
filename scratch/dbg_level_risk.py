# -*- coding: utf-8 -*-
"""一次性排查：run3 期间升到 5/10 级（职业弹窗）的风险有多大。

判据：职业弹窗只在等级 5 与 10 出现；普通升级（1-4、6-9）是普通 LevelUpMenu，
task-11 会自动关掉。所以只需要看"当前 farmingLevel / 离 5 级还差多少 XP"。
SDV 累计经验门槛：100/380/770/1300/2150/3300/4800/6900/10000/15000。
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

THRESHOLDS = [100, 380, 770, 1300, 2150, 3300, 4800, 6900, 10000, 15000]
PARSNIP_XP = 8  # 收获一个防风草 8 XP

p = "scratch/obs-full.json"
if os.path.exists(p):
    d = json.load(open(p, encoding="utf-8"))
    pl = d.get("player", {})
    print("obs-full.json: name=%s farmingLevel=%s clock=%s money=%s location=%s"
          % (pl.get("name"), pl.get("farmingLevel"), d.get("clock"), pl.get("money"), pl.get("location")))
else:
    print("no scratch/obs-full.json")

for f in sorted(glob.glob("logs/longrun-*.jsonl")):
    hits = []
    lines = open(f, encoding="utf-8", errors="replace").read().splitlines()
    for ln in lines:
        low = ln.lower()
        if "farminglevel" in low or "profession" in low or "levelup" in low or "level_up" in low:
            hits.append(ln[:200])
    print("%s lines=%d level-hits=%d" % (os.path.basename(f), len(lines), len(hits)))
    for h in hits[:3]:
        print("   ", h)

print("\n注意：observe 的 player 里只有 farmingLevel（等级），没有累计经验。")
print("要算风险必须再拿 runningTotalExperience/farmingExperience（若观测没有，需真机读一次或加字段）。")
print("参考：3 天最多收 %d 个作物 ⇒ 最多 %d XP。" % (31, 31 * PARSNIP_XP))
