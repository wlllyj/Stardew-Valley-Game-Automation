# -*- coding: utf-8 -*-
"""只打印需要的东西（避免把整份 XML 打出来）：配方前后、Furnace 上下文子串、六串、SMAPI 冻结、存档四条、邮件旗标。"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
R = json.loads((REPO / "scratch" / "t226-receipts.json").read_text(encoding="utf-8"))
SAVE = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"

print("=== SMAPI 冻结 ===")
f = R["smapi_frozen"]
print(f"  src {f['src']['size']} B / {f['src']['mtime']} / sha256={f['sha256_src']}")
print(f"  dst {f['dst']['size']} B / {f['dst']['mtime']} / sha256={f['sha256_dst']}")
print(f"  BYTE_IDENTICAL={f['byte_identical']}  总行数={R['chains']['lines']}")
print("=== 六串累计（行号@时刻）===")
for k, hits in R["chains"]["total"].items():
    print(f"  {k}: {len(hits)} -> " + ", ".join(f"L{h['line']}@{h['t']}" for h in hits))

for tag in ("recipes_before", "recipes_after"):
    r = R[tag]
    print(f"\n=== {tag} === {r['count']} 条 / has_Furnace={r['has_furnace']} / {r['size']} B / mtime {r['mtime']}")
    for it in r["items"]:
        mark = "  <== NEW" if (tag == "recipes_after" and it not in R["recipes_before"]["items"]) else ""
        print(f"   - {it}{mark}")

print("\n=== 存档四条 ===")
for k, v in R["save_four"].items():
    print(f"  {k}: {v['size']} B / {v['at']}")

# Furnace 在 <craftingRecipes> 里的确切键名与上下文子串
after = SAVE / "Wahaha_450799035"
root = after.read_text(encoding="utf-8", errors="replace")
m = re.search(r"<craftingRecipes>(.*?)</craftingRecipes>", root, re.S)
block = m.group(1) if m else ""
print(f"\n=== <craftingRecipes> 块长度={len(block)} 字符；含 'Furnace' = {'Furnace' in block} ===")
for mm in re.finditer(r"Furnace", block):
    a, b = max(0, mm.start() - 160), min(len(block), mm.end() + 160)
    print(f"  上下文子串: ...{block[a:b]}...")
# 邮件旗标
for key in ("copperFound", "mailReceived", "mailbox", "mailForTomorrow"):
    hits = [mm.start() for mm in re.finditer(re.escape(key), root)]
    print(f"  '{key}' 出现 {len(hits)} 次")
    for pos in hits[:3]:
        a, b = max(0, pos - 120), min(len(root), pos + 200)
        print(f"    上下文: ...{root[a:b]}...")
