# -*- coding: utf-8 -*-
"""run6 起跑前的**操作员预置**：把清障攒下的盈余战利品换成本钱（Lead 独占，2026-10-14）。

为什么要做（`docs/_release-0.7.25.md` §7）：run6 起跑前 `seeds==0` 且 `money=14g < 种子价 20g`
⇒ 脑侧买不了种子、`plant_area` 整条腿永远空转，而 P3 ⑥ 的目标链本身就含"播种"。
清障战利品（石/木/纤维/煤/黏土/晶洞）堆在背包里对目标没有价值，出货换钱让脑侧自己 `buy` 种子。

纪律：
- **只走游戏自己的出货链**（Mod `sell` 技能 → `Farm.shipItem`），钱由下一次 `NewDay` 结算，
  本脚本**绝不碰 money**（全仓 `grep "Money +="` 生产代码零命中是项目铁律）。
- 工具（`(T)*`）/武器（`(W)*`）/种子（名字含"种子/seed"）**永不卖**。
- ⚠️ Mod 的 `ShipSkill` 出货的是 `Items[slot]` **整叠**，没有"只卖超额部分"的能力
  ⇒ 本脚本只能整叠卖（"每 id 保留 K=10" 在操作员层也实现不了，这是 task-55 的已知缺口，记在 §7）。
- 只读观测 + 出货，不改存档文件；`--dry-run` 只打印计划。

用法：
    python scratch/run6-preseed.py --dry-run
    python scratch/run6-preseed.py                 # 真出货
    python scratch/run6-preseed.py --skip "(O)382" # 明确不卖的 qualifiedId
"""

from __future__ import annotations

import argparse
import sys

from agentfarm.bridge import BridgeClient, BridgeError

#: 名字里带这些字样的永不卖（种子）。
SEED_HINTS = ("种子", "seed")
#: qualifiedId 前缀：工具与武器。
NEVER_PREFIX = ("(T)", "(W)")


def inventory_of(obs: dict) -> list[dict]:
    player = obs.get("player") or {}
    return list(player.get("inventory") or player.get("items") or [])


def bin_of(obs: dict) -> dict:
    return dict(obs.get("shippingBin") or {})


def money_of(obs: dict) -> int | None:
    m = (obs.get("player") or {}).get("money")
    return int(m) if isinstance(m, (int, float)) else None


def main() -> int:
    ap = argparse.ArgumentParser(description="run6 起跑前预置：盈余战利品出货换种子钱")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不出货")
    ap.add_argument("--skip", action="append", default=[], help="不卖的 qualifiedId（可重复）")
    ap.add_argument("--keep-slots", default="", help="不卖的槽位号，逗号分隔（例如 5,6）")
    ap.add_argument("--timeout-ms", type=int, default=8000)
    args = ap.parse_args()
    skip_ids = set(args.skip)
    keep_slots = {int(s) for s in args.keep_slots.split(",") if s.strip().isdigit()}

    client = BridgeClient()
    obs = client.observe("full")
    money0 = money_of(obs)
    bin0 = bin_of(obs)
    print(f"出货前：money={money0} 箱子件数={bin0.get('count')}")
    print("背包：")
    plan: list[tuple[int, str, str, int]] = []
    for it in inventory_of(obs):
        slot = int(it.get("slot") or 0)
        qid = str(it.get("qualifiedId") or "")
        name = str(it.get("name") or "")
        stack = int(it.get("stack") or 0)
        is_tool = bool(it.get("isTool")) or qid.startswith(NEVER_PREFIX)
        is_seed = any(h in name.lower() for h in SEED_HINTS)
        line = f"  [{slot:>2}] {qid:<10} {name} x{stack}"
        if is_tool:
            print(line + "  —— 工具/武器，跳过")
            continue
        if is_seed:
            print(line + "  —— 种子，跳过")
            continue
        if slot in keep_slots or qid in skip_ids:
            print(line + "  —— 按参数跳过")
            continue
        print(line + "  ⇒ 计划出货（整叠）")
        plan.append((slot, qid, name, stack))

    if not plan:
        print("没有可出货的格子；什么都不做。")
        return 0
    if args.dry_run:
        print(f"[dry-run] 将出货 {len(plan)} 叠：{[(q, s) for _, q, _, s in plan]}")
        return 0

    ok = 0
    for slot, qid, name, stack in plan:
        try:
            rec = client.sell(slot, whitelist=[qid], timeout_ms=args.timeout_ms)
            status = rec.get("status")
            reason = str(rec.get("reason") or "")[:160]
            # 判据只看观测差分：槽位不再有这件 + 箱子件数变化
            after = client.observe("full")
            still = any(
                int(i.get("slot") or -1) == slot and str(i.get("qualifiedId") or "") == qid
                for i in inventory_of(after)
            )
            bin_now = int(bin_of(after).get("count") or 0)
            good = (not still) and bin_now > int(bin0.get("count") or 0)
            print(f"  sell slot={slot} {qid} x{stack} → status={status} 槽位还有={still} "
                  f"箱子件数={bin_now} ⇒ {'OK' if good else '未确认'}")
            if good:
                ok += 1
            bin0 = bin_of(after)
        except BridgeError as exc:
            print(f"  sell slot={slot} {qid} 失败：{status_of(exc)} {str(exc)[:160]}")
    final = client.observe("full")
    print(f"出货后：money={money_of(final)}（当天不变，等下一次 NewDay 结算）"
          f" 箱子件数={bin_of(final).get('count')}，成功 {ok}/{len(plan)}")
    return 0 if ok else 1


def status_of(exc: BridgeError) -> str:
    return str(getattr(exc, "status", "") or "bridge_error")


if __name__ == "__main__":
    raise SystemExit(main())
