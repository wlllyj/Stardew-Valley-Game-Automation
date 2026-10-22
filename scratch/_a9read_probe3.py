# -*- coding: utf-8 -*-
"""Read-only: locate Wheat Seeds (472) and all item stacks in the A9-start save."""
import io
import re

p = r"logs/ab-backup/A9-start/Wahaha_450799035"
s = io.open(p, encoding="utf-8", errors="replace").read()

print("=== itemId 472 blocks ===")
for m in re.finditer(r"<itemId>472</itemId>", s):
    i = m.start()
    print(repr(s[i - 120 : i + 120]))

print("=== Wheat contexts ===")
for m in re.finditer("Wheat", s):
    i = m.start()
    print(repr(s[i - 80 : i + 80]))

print("=== inventory item summary (name/stack) ===")
for m in re.finditer(
    r"<name>([^<]{0,40})</name>(?:(?!</Item>).){0,600}?<stack>(\d+)</stack>", s, re.S
):
    print(" ", m.group(1), "x", m.group(2))
