#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一次性排查：列出 journal 里每个 event 的字段集合与各 event 的首条样例。"""
import json
import sys
from collections import OrderedDict

path = sys.argv[1]
seen = OrderedDict()
with open(path, "r", encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        ev = obj.get("event")
        if ev not in seen:
            seen[ev] = obj
for ev, obj in seen.items():
    print(f"--- {ev}: {sorted(k for k in obj if k != 'event')}")
    print("   ", json.dumps(obj, ensure_ascii=False)[:600])
