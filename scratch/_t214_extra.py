# -*- coding: utf-8 -*-
"""task-214 补充取证（只读）：① 落盘整张 Data/CraftingRecipes（150 条）② 比几条同类配方
③ 从存档 XML 读玩家已学配方，确认 Furnace 是否在玩家字典里。

不写世界、不调任何写技能。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

SAVE = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035" / "Wahaha_450799035"
INTEREST = ["Furnace", "Charcoal Kiln", "Chest", "Scarecrow", "Torch", "Bee House"]


def main() -> int:
    out = {}
    try:
        r = BridgeClient().debug_dump("crafting_recipes", limit=2000, timeout_ms=60000)
        (REPO / "scratch" / "run10f-crafting-recipes-full.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        entries = r.get("entries") or []
        print(f"[1] 整表落盘：count={r.get('count')} truncated={r.get('truncated')} entries={len(entries)}")
        d = {}
        for row in entries:
            if isinstance(row, list) and len(row) >= 2:
                d[str(row[0])] = str(row[1])
            elif isinstance(row, dict):
                k = row.get("key") or row.get("id")
                if k:
                    d[str(k)] = str(row.get("value"))
        out["table_count"] = r.get("count")
        out["interested"] = {k: d.get(k) for k in INTEREST}
        for k in INTEREST:
            print(f"    {k:14} -> {d.get(k)}")
        print(f"[1] 表里含 'Furnace' 键 = {'Furnace' in d}")
    except BridgeError as exc:
        print(f"!! debug_dump 失败：{exc.status}: {str(exc)[:300]}")
        out["table_error"] = str(exc)[:400]

    # ② 玩家已学配方（存档 XML 真值）
    raw = SAVE.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<craftingRecipes>(.*?)</craftingRecipes>", raw, re.S)
    learned = re.findall(r"<string>(.*?)</string>", m.group(1)) if m else []
    out["player_crafting_recipes_count"] = len(learned)
    out["player_crafting_recipes"] = learned
    out["player_has_furnace"] = any("Furnace" in x for x in learned)
    print(f"\n[2] 存档 player.craftingRecipes：{len(learned)} 条，含 Furnace = {out['player_has_furnace']}")
    print("    已学清单：" + (" | ".join(learned) if learned else "(空)"))
    m2 = re.search(r"<mailReceived>(.*?)</mailReceived>", raw, re.S)
    mail = re.findall(r"<string>(.*?)</string>", m2.group(1)) if m2 else []
    out["mail_received"] = mail
    print(f"    mailReceived：{len(mail)} 条 {mail[:12]}")

    p = REPO / "logs" / "run10f-extra.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写 {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
