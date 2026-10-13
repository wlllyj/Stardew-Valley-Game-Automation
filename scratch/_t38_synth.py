#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""task-38 取证脚本：给"真实彩排账本"补上修好后才会写的 `day_after`，看验收工具是否认。

为什么需要：彩排账本是**修之前**的代码写的（没有 `day_after`），验收工具只能退回读 `final`
（睡前快照）⇒ 必然报"缺跨日证据"。这里只做一件事：把 `ended_by=="sleep"` 的那条 `day_end`
补一个 `day_after`（值取该行 ended_reason 里明写的目标日），然后 `--days 1` 复核。
不改任何生产代码、不改原账本（只写 `scratch/`）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC = Path("logs/longrun-rehearsal-0.7.23.jsonl")
DST = Path("scratch/review-t38-with-day-after.jsonl")

rows: list[dict] = []
for line in SRC.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line:
        rows.append(json.loads(line))

patched = 0
for r in rows:
    if r.get("event") != "day_end" or r.get("ended_by") != "sleep":
        continue
    m = re.search(r"spring\s*(\d+)\s*日\s*→\s*spring\s*(\d+)\s*日", str(r.get("ended_reason") or ""))
    day_before = int(r["final"]["day"][2]) if isinstance(r.get("final", {}).get("day"), list) else None
    target = int(m.group(2)) if m else (day_before + 1 if day_before else None)
    if target is None:
        print(f"!! 无法推断 {r.get('day')} 的目标日，跳过")
        continue
    r["day_after"] = [1, "spring", target]
    patched += 1
    print(f"patch day_end {r.get('day')} ended_by=sleep → day_after={r['day_after']}")

DST.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
print(f"patched={patched}  →  {DST}")
sys.exit(0 if patched else 1)
