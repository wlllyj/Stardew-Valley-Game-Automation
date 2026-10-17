"""Lead 一次性只读探针：查背包里的工具升级材料（铜锭 334 / 铜矿 378 / 煤 382 / 石头 390 / 木 388 / 熔炉 114）。

用途：task-205 真机验收的前置判断 —— 升级 0→1 铜需要 2000g + 5 条铜锭(334)。
只读，不改世界。
"""
from __future__ import annotations

import json

from agentfarm.bridge import BridgeClient

WANT = {
    "334": "Copper Bar 铜锭",
    "335": "Iron Bar 铁锭",
    "336": "Gold Bar 金锭",
    "337": "Iridium Bar 铱锭",
    "378": "Copper Ore 铜矿",
    "380": "Iron Ore 铁矿",
    "382": "Coal 煤",
    "390": "Stone 石头",
    "388": "Wood 木头",
}


def main() -> int:
    c = BridgeClient()
    o = c.observe("full")
    clk = o.get("clock") or {}
    loc = o.get("location") or {}
    p = o.get("player") or {}
    print(
        "day",
        clk.get("year"),
        clk.get("season"),
        clk.get("day"),
        "tod",
        clk.get("timeOfDay"),
        "| loc",
        loc.get("name"),
        "tile",
        p.get("tile"),
    )
    print(
        "money",
        p.get("money"),
        "stamina",
        p.get("stamina"),
        "farmingLevel",
        p.get("farmingLevel"),
        "toolUpgradeDaysLeft",
        p.get("toolUpgradeDaysLeft"),
        "toolBeingUpgraded",
        json.dumps(p.get("toolBeingUpgraded"), ensure_ascii=False),
    )
    inv = p.get("inventory") or []
    print("inventoryCount", p.get("inventoryCount"), "rows", len(inv))
    totals = {}
    for r in inv:
        qid = str(r.get("id"))
        print(
            "  row",
            r.get("slot"),
            "id",
            qid,
            repr(r.get("name")),
            "stack",
            r.get("stack"),
        )
        totals[qid] = totals.get(qid, 0) + int(r.get("stack") or 0)
    print("--- 升级相关材料盘点 ---")
    for qid, label in WANT.items():
        print(f"  {label:22s} id={qid:4s} 持有 {totals.get(qid, 0)}")
    tools = (p.get("tools") or {}).get("tools") or []
    print("--- 工具等级 ---")
    for t in tools:
        print(
            "  ",
            t.get("kind"),
            t.get("name"),
            "upgradeLevel",
            t.get("upgradeLevel"),
            "equipped",
            t.get("isEquipped"),
        )
    farm = o.get("farm") or {}
    print(
        "--- farm 计数 ---",
        {k: farm.get(k) for k in ("crops", "readyCrops", "dryCrops", "deadCrops", "hoeDirt", "emptyDirt", "complete")},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
