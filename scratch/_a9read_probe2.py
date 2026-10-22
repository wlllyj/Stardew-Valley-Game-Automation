# -*- coding: utf-8 -*-
"""Read-only: dump first Object item block + look for seeds."""
import io

p = r"logs/ab-backup/A9-start/Wahaha_450799035"
s = io.open(p, encoding="utf-8", errors="replace").read()
needle = 'xsi:type="Object"'
i = s.find(needle)
print("first Object at", i)
print(repr(s[i - 40 : i + 900]))
print("=== count of <Stack>", s.count("<Stack>"))
print("=== 'Wheat' occurrences:", s.count("Wheat"))
