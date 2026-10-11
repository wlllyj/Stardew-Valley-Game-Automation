# -*- coding: utf-8 -*-
"""落点契约诊断：**回执说 ok 的格，脑随后观测到的还是不是那一格？**

【为什么要单独测这个】
2026-10-11 18:21 的浸泡日志里出现过一次刺眼的自相矛盾：

    18:21:12  🚶 move_to(7,9) -> ok=True status=ok 1042ms reason=-
    18:21:13  samples=  42 ... tile=[7, 10] ...

回执说"到了 (7,9)"，一秒后的观测却是 (7,10)。按本项目的最高纪律——
**只信游戏证据**——回执本身不是证据，观测才是。如果"到达"判定与观测口径不一致
（例如一边用 `player.TilePoint`、另一边用包围盒中心，或控制器在跨过格线时就被清掉、
角色靠惯性多走了一格），那么 P3 会以最恶心的方式失败：脑以为站在 A 格去种地，
实际站在 B 格，种到隔壁去了。所以把它做成可复现的探针。

【口径】
对每次移动，记录回执（`status` / `elapsedMs` / `reason` / `uiOpened` / `worldSeq`）与
我们要的目标格，然后连采样若干次，记录脑**观测**到的 `player.tile`，并统计：
  * 末次观测是否等于目标格；
  * 偏差（`dx` / `dy`）——若偏移稳定出现，就是"落点系统性偏一格"的特征，而不是抖动。
⚠️ 注意 `move_to` 的**回执里没有落点格字段**（v0.5.1 实测），所以"到没到"只能靠观测；
    这本身就是为什么本项目把"回执"与"账本"分开——回执是**声明**，观测才是**证据**。

用法（游戏需在跑；建议先停掉会自己移动的 soak）：
    set PYTHONPATH=D:\\...\\星露谷游戏自动化\\brain
    python tools\\diag-landing.py 7 9 --repeat 3
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402


def tile_of(obs: dict) -> list[int] | None:
    t = (obs.get("player") or {}).get("tile")
    return list(t) if isinstance(t, (list, tuple)) and len(t) == 2 else None


def main() -> int:
    ap = argparse.ArgumentParser(description="落点契约诊断：回执 ok 之后脑观测到的是哪一格")
    ap.add_argument("x", type=int)
    ap.add_argument("y", type=int)
    ap.add_argument("--repeat", type=int, default=3, help="重复次数（每轮先回到出发点附近）")
    ap.add_argument("--samples", type=int, default=6, help="每次移动后的观测次数")
    ap.add_argument("--interval", type=float, default=0.25, help="观测间隔秒")
    ap.add_argument("--allow-bed", action="store_true", dest="allow_bed")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    target = (args.x, args.y)
    client = BridgeClient(timeout=20.0)
    print(f"目标格 {target}，重复 {args.repeat} 次，每次移动后观测 {args.samples} 次（间隔 {args.interval}s）")

    bad = 0
    try:
        for i in range(1, args.repeat + 1):
            before = tile_of(client.observe("summary"))
            t0 = time.time()
            try:
                res = client.move_to(args.x, args.y, allow_bed=args.allow_bed, timeout_ms=15000)
            except BridgeError as exc:
                print(f"[{i}] ✗ 移动请求本身失败：{exc}")
                bad += 1
                continue
            elapsed = time.time() - t0
            receipt_tile = res.get("tile")   # ⚠️ v0.5.0/0.5.1 的 move_to 回执**不回显落点格**（实测为 None）
            print(f"[{i}] 起点 {before} → 目标 {target}")
            print(f"    回执 status={res.get('status')} ok={res.get('ok')} "
                  f"{elapsed * 1000:.0f}ms reason={res.get('reason')!r} uiOpened={res.get('uiOpened')} "
                  f"worldSeq {res.get('worldSeqBefore')}→{res.get('worldSeqAfter')} "
                  f"回执 tile={receipt_tile if receipt_tile is not None else '（未回显落点格）'}")

            seen: list[list[int]] = []
            flags: list[str] = []
            for _ in range(args.samples):
                time.sleep(args.interval)
                obs = client.observe("summary")
                t = tile_of(obs)
                pl = obs.get("player") or {}
                if t is not None:
                    seen.append(t)
                # hasController 是关键：控制器没被清掉 / 又被别人装上，都会在这里露出来
                flags.append(f"{t} ctrl={pl.get('hasController')} can={pl.get('canMove')} bed={pl.get('isInBed')}")
            last = seen[-1] if seen else None
            hit_obs = last == list(target) if last else None
            print(f"    观测轨迹 {seen}")
            for f in flags:
                print(f"      · {f}")
            print(f"    末次观测=目标? {hit_obs}   末次观测={last}")
            if hit_obs is False:
                bad += 1
                dy = (last[1] - target[1]) if last else None
                dx = (last[0] - target[0]) if last else None
                print(f"    ⚠️ **契约破裂**：回执说到了，脑观测到的是 {last}（偏移 dx={dx} dy={dy}）")
    except BridgeError as exc:
        print(f"✗ 连不上桥：{exc}")
        return 2

    print()
    if bad:
        print(f"结论：{bad}/{args.repeat} 轮出现『回执 ok 但观测不在目标格』——落点契约不可信，必须先修再谈 P3。")
        return 1
    print(f"结论：{args.repeat} 轮全部『回执 ok 且观测确实在目标格』——落点契约成立。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
