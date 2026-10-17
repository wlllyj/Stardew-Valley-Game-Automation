"""真机内省探针（task-213）：把游戏自己加载的数据表读出来 / 调一次补发入口。

背景（`docs\\_il-furnace-recipe.md`，task-212）：
  * 0.7.38 的机器链被卡住 —— 存档的 `player.craftingRecipes` 里**没有 Furnace**；
  * 唯一合法的授予通道是「玩家技能升级时构造 `LevelUpMenu` → `AddMissedMailAndRecipes()`」；
    `LearnDefaultRecipes` 每日只给默认配方（Furnace 不在其中）；`Farmer.LevelUp(int)` 不存在；
  * 而自动化从未构造过 `LevelUpMenu` ⇒ 配方没被补发；
  * 条件串在打包 xnb 里读不到 ⇒ **必须真机运行时内省一次**一锤定音。

本探针只做两件事（都走 `dismiss_modal` 之前的 Mod 内省面，Mod ≥ 0.7.39）：
  1. `debug_dump <table> [--key K] [--limit N]`：只读，把 Data 表读出来；
  2. `--add-missed`：调一次游戏自己的 `Farmer.AddMissedMailAndRecipes()`（**会写玩家字典**，
     只调一次、不循环），看 `craftingRecipesAdded` 是否含 `Furnace`。

建议取证顺序（Lead 装 0.7.39 后由 machine-runner 跑）：
  python scratch\\_t213_probe.py --table crafting_recipes --key Furnace
  python scratch\\_t213_probe.py --table trigger_actions
  python scratch\\_t213_probe.py --add-missed
  python scratch\\_t213_probe.py --table crafting_recipes --key Furnace   # 补发后再看一次

注意：探针**不判断"该不该补发"**，只如实打印回执与前后计数；写档动作是否执行由调用方决定。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402


def dump_table(client: BridgeClient, table: str, key: str | None, limit: int | None) -> int:
    """只读：打一张表（给了 key 就只看命中项）。"""
    try:
        r = client.debug_dump(table, key=key, limit=limit, timeout_ms=60000)
    except BridgeError as exc:
        print(f"❌ debug_dump({table}) 失败：{exc.status}: {str(exc)[:400]}")
        return 1
    print(f"== debug_dump table={table!r} key={key!r} limit={limit!r} ==")
    print("回执：", json.dumps(r, ensure_ascii=False, default=str)[:1200])
    print(f"  ok={r.get('ok')} status={r.get('status')!r} table={r.get('table')!r} "
          f"count={r.get('count')} truncated={r.get('truncated')}")
    print(f"  matchMode={r.get('matchMode')!r} matchedCount={r.get('matchedCount')} "
          f"matchedTruncated={r.get('matchedTruncated')}")
    rows = r.get("matched") if key is not None else r.get("entries")
    for row in (rows or [])[:20]:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            print(f"    {row[0]} -> {str(row[1])[:600]}")
    if not rows:
        print("    （没有条目：key 没命中、表为空、或字段缺失 —— 看上面的 status/reason）")
    return 0 if r.get("status") in ("ok", None) else 2


def add_missed(client: BridgeClient) -> int:
    """写档：调一次游戏补发入口，打印前后差分。"""
    try:
        r = client.add_missed_recipes(timeout_ms=60000)
    except BridgeError as exc:
        print(f"❌ add_missed_recipes 失败：{exc.status}: {str(exc)[:400]}")
        return 1
    print("== add_missed_recipes（调一次 Farmer.AddMissedMailAndRecipes）==")
    print("回执：", json.dumps(r, ensure_ascii=False, default=str)[:1600])
    print(f"  ok={r.get('ok')} status={r.get('status')!r}")
    print(f"  beforeCounts={r.get('beforeCounts')}")
    print(f"  afterCounts={r.get('afterCounts')}")
    for field in ("craftingRecipesAdded", "cookingRecipesAdded", "mailAdded"):
        added = r.get(field) or []
        print(f"  {field}（{len(added)}）：{added[:20]}")
    furnace = "Furnace" in [str(x) for x in (r.get("craftingRecipesAdded") or [])]
    print("结论：", "✅ 本次补发**包含 Furnace**" if furnace
          else "⚠️ 本次补发**没有** Furnace（看 craftingRecipesAdded 与 reason）")
    return 0 if r.get("ok") else 2


def main() -> int:
    ap = argparse.ArgumentParser(description="task-213 真机内省探针（只读表 / 一次补发）")
    ap.add_argument("--table", default=None,
                    help="crafting_recipes / cooking_recipes / trigger_actions / mail / machines / "
                         "objects / big_craftables（也接受 Data/CraftingRecipes 这类资产名）")
    ap.add_argument("--key", default=None, help="可选键过滤（精确优先，否则子串）")
    ap.add_argument("--limit", type=int, default=None, help="最多多少条（默认 200、上限 2000）")
    ap.add_argument("--add-missed", action="store_true",
                    help="调一次 Farmer.AddMissedMailAndRecipes()（会写玩家字典）")
    ap.add_argument("--timeout", type=float, default=10.0, help="HTTP 超时（秒）")
    args = ap.parse_args()

    if not args.table and not args.add_missed:
        ap.print_help()
        print("\n❌ 至少给 --table 或 --add-missed（两个都给就先 dump 再补发）")
        return 2

    client = BridgeClient(timeout=args.timeout)
    rc = 0
    if args.table:
        rc = max(rc, dump_table(client, args.table, args.key, args.limit))
    if args.add_missed:
        rc = max(rc, add_missed(client))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
