# -*- coding: utf-8 -*-
"""Read-only probe: extract start-of-arm readings from the A9-start backup save."""
import io
import re
import sys

p = r"logs/ab-backup/A9-start/Wahaha_450799035"
s = io.open(p, encoding="utf-8", errors="replace").read()
print("file_len_chars", len(s))

print("money:", re.findall(r"<money>(\d+)</money>", s)[:3])
print("dayOfMonth:", re.findall(r"<dayOfMonth>(\d+)</dayOfMonth>", s)[:3])
print("currentSeason:", re.findall(r"<currentSeason>(\w+)</currentSeason>", s)[:3])
print("year:", re.findall(r"<year>(\d+)</year>", s)[:3])
print("WaterLeft:", re.findall(r"<WaterLeft>(\d+)</WaterLeft>", s)[:8])
print("waterLeft:", re.findall(r"<waterLeft>(\d+)</waterLeft>", s)[:8])
print("stamina:", re.findall(r"<stamina>(\d+)</stamina>", s)[:3])

# Object items: capture ItemId + Stack pairs
pairs = re.findall(
    r'<Item xsi:type="Object">\s*<ItemId>(\d+)</ItemId>.*?<Stack>(\d+)</Stack>',
    s,
    re.S,
)
print("object_item_pairs(total):", len(pairs))
for iid, st in pairs:
    print("  obj", iid, "stack", st)

# Tools (stype) with WaterLeft handled above
print("ItemId472_count:", s.count("<ItemId>472</ItemId>"))
