# -*- coding: utf-8 -*-
"""task-210 真机自证链探针：造熔炉 → 放置 → 投料(5 铜矿+1 煤) → 等 → 收 1 铜锭。

**只读 + 一次显式动作链**（每一步都打印观测差分，绝不"造材料/改存档"）：
- 依赖 0.7.39+ 的 Mod 技能 `craft_item` / `place_object` / `machine`（缺 ⇒ 桥会回 `unknown_skill`，
  探针立刻停手并如实报）。
- 材料必须**事先备好**（熔炉 = 20 铜矿 + 25 石；投料 = 5 铜矿 + 1 煤）。缺料时本探针只报缺什么，
  不会买东西、不会造材料。
- 判据一律观测差分（背包逐 qid / 熔炉格 heldObject / readyForHarvest），Mod 回执只当线索。

用法（机器上、游戏已开、桥已就绪）：
    python scratch/_t210_chain_probe.py --tile 62,12
    python scratch/_t210_chain_probe.py --tile 62,12 --dry-run      # 只看现状，不发动作
    python scratch/_t210_chain_probe.py --list                       # 只打印背包/熔炉候选格

退出码：0 = 全链成功（或 dry-run 正常）；2 = 前置不满足（缺料/没配方/没空格）；3 = 某一步观测上没生效。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

FURNACE_QID = "(BC)114"
FURNACE_RECIPE = "Furnace"
ORE_QID = "(O)334"
COAL_QID = "(O)382"
BAR_QID = "(O)337"


def inv_counts(obs: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in (obs.get("player") or {}).get("inventory") or []:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("qualifiedId") or item.get("id") or "")
        if qid:
            out[qid] = out.get(qid, 0) + int(item.get("stack") or 1)
    return out


def tile_of(obs: dict, tile: tuple[int, int]) -> dict:
    for tv in (obs.get("location") or {}).get("tiles") or []:
        if isinstance(tv, dict) and tuple(tv.get("tile") or ()) == tile:
            return tv
    return {}


def show_inv(tag: str, obs: dict, qids=(FURNACE_QID, ORE_QID, COAL_QID, BAR_QID)) -> dict:
    counts = inv_counts(obs)
    print(f"  [{tag}] " + "、".join(f"{q}={counts.get(q, 0)}" for q in qids))
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tile", default="", help="放置熔炉的格子 x,y（默认自动找玩家脚下一格空地）")
    ap.add_argument("--dry-run", action="store_true", help="只读现状，不发任何动作")
    ap.add_argument("--list", action="store_true", help="只打印背包与候选格")
    ap.add_argument("--wait-minutes", type=float, default=35.0,
                    help="投料后最多等多少**游戏分钟**（默认 35，熔炉 30）")
    args = ap.parse_args(argv)

    client = BridgeClient()
    obs = client.observe("full", timeout=15.0)
    counts = show_inv("initial", obs)
    player = (obs.get("player") or {})
    tile = tuple(player.get("tile") or (62, 14))
    print(f"  玩家格={tile} 钱={player.get('money')} 空格="
          f"{sum(1 for i in player.get('inventory') or [] if not i)}")
    if args.list or args.dry_run:
        known = (player.get("knownCraftingRecipes") or [])
        print(f"  已学配方 {len(known)} 条；含 {FURNACE_RECIPE}={FURNACE_RECIPE in known}")
        print(f"  熔炉={counts.get(FURNACE_QID, 0)} 铜矿={counts.get(ORE_QID, 0)} "
              f"煤={counts.get(COAL_QID, 0)} 铜锭={counts.get(BAR_QID, 0)}")
        return 0

    target = (int(args.tile.split(",")[0]), int(args.tile.split(",")[1])) if args.tile else (tile[0], tile[1] + 1)
    print(f"  目标放置格={target}（当前={tile_of(obs, target) or '空'}）")

    # 0) 前置：材料/配方/空格 —— 缺什么就报什么，绝不"造材料"
    if counts.get(FURNACE_QID, 0) < 1:
        need = {"ore": max(0, 20 - counts.get(ORE_QID, 0)), "stone": 25}
        if FURNACE_RECIPE not in (player.get("knownCraftingRecipes") or []):
            print("  ✗ 没学会 Furnace 配方（先备料/走合法授予路径），退出")
            return 2
        print(f"  炉子 0 个、材料缺口 ore={need['ore']} stone={need['stone']}（"
              f"现有 ore={counts.get(ORE_QID, 0)} stone={counts.get('(O)390', 0)}）")
        if need["ore"] > 0 or counts.get("(O)390", 0) < 25:
            print("  ✗ 材料不足（本探针只报缺口，不买东西/不造材料），退出")
            return 2
        print("  → craft_item(Furnace)")
        st = client.exec_skill("craft_item", {"item": FURNACE_RECIPE}, timeout_ms=30000)
        print(f"    回执 ok={st.get('ok')} status={st.get('status')} craftedQid={st.get('craftedQid')}")
        obs = client.observe("full", timeout=15.0)
        show_inv("after craft", obs)
        if not inv_counts(obs).get(FURNACE_QID):
            print("  ✗ 观测里背包没有熔炉 ⇒ 这一步没生效，停手")
            return 3

    # 1) 放置
    obs = client.observe("full", timeout=15.0)
    if tile_of(obs, target).get("objId"):
        print(f"  ✗ 目标格 {target} 上已经有物体（objId={tile_of(obs, target).get('objId')}），换一格")
        return 2
    print(f"  → place_object({FURNACE_QID} @ {target})")
    st = client.exec_skill("place_object", {"item": FURNACE_QID, "tile": list(target)}, timeout_ms=30000)
    print(f"    回执 ok={st.get('ok')} status={st.get('status')} placed={st.get('placed')} "
          f"consumed={st.get('consumed')}")
    obs = client.observe("full", timeout=15.0)
    show_inv("after place", obs)
    if not tile_of(obs, target).get("objId"):
        print("  ✗ 观测里目标格没有物体 ⇒ 放置没生效，停手（不补放）")
        return 3

    # 2) 投料：铜矿 + 煤（一次 drop-in，游戏自己扣）
    counts = inv_counts(obs)
    if counts.get(ORE_QID, 0) < 5 or counts.get(COAL_QID, 0) < 1:
        print(f"  ✗ 投料不足：铜矿 {counts.get(ORE_QID, 0)}/5、煤 {counts.get(COAL_QID, 0)}/1，退出")
        return 2
    for item in (ORE_QID, COAL_QID):
        print(f"  → machine(feed {item} @ {target})")
        st = client.exec_skill("machine", {"action": "feed", "tile": list(target), "item": item},
                               timeout_ms=30000)
        print(f"    回执 ok={st.get('ok')} status={st.get('status')} "
              f"held={((st.get('heldObject') or {}).get('id'))} ready={st.get('machineReady')}")
        obs = client.observe("full", timeout=15.0)
        tv = tile_of(obs, target)
        print(f"    观测：heldObject={(tv.get('heldObject') or {}).get('id')} "
              f"ready={tv.get('readyForHarvest')} minutes={tv.get('minutesUntilReady')}")
        if not tv.get("heldObject"):
            print("  ✗ 观测里机器 heldObject 还空 ⇒ 投料没生效，停手（不重复投）")
            return 3

    # 3) 等游戏分钟走完（熔炉 30）
    deadline = time.time() + 1800
    waited = 0
    while time.time() < deadline:
        obs = client.observe("full", timeout=15.0)
        tv = tile_of(obs, target)
        if tv.get("readyForHarvest") is True:
            print("  观测：readyForHarvest=true ⇒ 可以取货")
            break
        mins = tv.get("minutesUntilReady")
        time.sleep(15.0)
        waited += 15
        print(f"  ……等产出（minutesUntilReady={mins}，已等 {waited}s 墙钟）")
        if isinstance(mins, int) and mins <= 0:
            break
    else:
        print("  ✗ 等不到 readyForHarvest，停手")
        return 3

    # 4) 取货
    print(f"  → machine(collect @ {target})")
    st = client.exec_skill("machine", {"action": "collect", "tile": list(target)}, timeout_ms=30000)
    print(f"    回执 ok={st.get('ok')} status={st.get('status')}")
    obs = client.observe("full", timeout=15.0)
    after = show_inv("after collect", obs)
    tv = tile_of(obs, target)
    print(f"  熔炉观测：heldObject={(tv.get('heldObject') or {}).get('id')} "
          f"ready={tv.get('readyForHarvest')}")
    if after.get(BAR_QID, 0) < counts.get(BAR_QID, 0) + 1:
        print("  ✗ 观测里铜锭没有 +1 ⇒ 取货没生效（如实失败，不补账）")
        return 3
    print("  ✓ 全链成功：背包铜锭 +1、熔炉 heldObject 清空")
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        raise SystemExit(main())
    except BridgeError as exc:  # pragma: no cover
        print(f"桥错误：{exc}（status={getattr(exc, 'status', '')}）")
        raise SystemExit(4)
