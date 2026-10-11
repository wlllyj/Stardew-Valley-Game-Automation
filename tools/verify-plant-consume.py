# -*- coding: utf-8 -*-
"""验收：**种一格 → 种子堆叠 -1**（v0.7.19 修「播种不扣种子」）。

【这个 bug 是怎么来的】（用户 2026-10-11 在 5x5 试点里发现）
真机现象：5x5 里 20 格全部 planted=True、作物都在，但背包里那包防风草种子**一直显示 10 个**。
IL 定案（`docs/_il-plant-consume.md`）：
  * `Object.placementAction` 的 IL 里**没有**任何扣物品的调用
    （`FIND|consumeObject` 命中 0 个调用方法；`FIND|reduceActiveItemByOne` 的 25 处里没有它）；
  * 真正扣物品的是 **`Game1.pressActionButton`**：放置前把 `ActiveObject.Stack` 存进局部变量（IL_0658），
    放置后只在「Stack 比存下来的值小」时才认为消耗成功（IL_0752–IL_0776）；
  * 路径③绕过鼠标直调 `placementAction`，就丢掉了这一步 ⇒ 种子永不减少。
修法（Mod 0.7.19）：放置后若 Stack 没变小，调游戏自己的 `Farmer.reduceActiveItemByOne()` 补扣。

【判据（铁律）】不信回执：
  1. 先 `observe?detail=full` 取播种前堆叠 `n0`；
  2. 挑一个可锄格 → 锄地 → `plant(472)`；
  3. 再 observe：
     * 该格 `tiles[]` 必须出现 `crop`（**种下了**）；
     * 背包里 472 的堆叠必须**恰好** == n0 - 1（**扣了**）。
  两个条件缺一即失败。回执里的「种子堆叠 n→m」只作对照，不作证据。

用法（先设 PYTHONPATH=<repo>\brain）：
    python tools\\verify-plant-consume.py
    python tools\\verify-plant-consume.py --seed 472 --tile 64 19
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402


def stack_of(obs: dict, item_id: str) -> int:
    """背包里某 id 的总堆叠（同一个 id 可能分几格，全部加起来）。"""
    total = 0
    for it in (obs.get("player") or {}).get("inventory") or []:
        if str(it.get("id")) == str(item_id):
            total += int(it.get("stack") or 0)
    return total


def tile_of(obs: dict, tile: tuple[int, int]) -> dict | None:
    for t in (obs.get("location") or {}).get("tiles") or []:
        if tuple(t.get("tile") or []) == tile:
            return t
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="验收：种一格 → 种子堆叠 -1")
    ap.add_argument("--seed", default="472", help="种子 ItemId（默认 472 = 防风草种子）")
    ap.add_argument("--tile", nargs=2, type=int, default=None, help="指定要种的可锄格；省略=自动挑最近的可锄格")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    c = BridgeClient(timeout=120.0)
    h = c.health()
    print(f"Mod {h.get('modVersion')}  runtime={json.dumps(h.get('runtime'), ensure_ascii=False)}")

    obs = c.observe("full")
    if not obs.get("hasSaveLoaded"):
        print("[FAIL] 尚未加载存档")
        return 1
    p = obs.get("player") or {}
    loc = obs.get("location") or {}
    print(f"玩家 {p.get('location')} {tuple(p.get('tile') or [])}  时间 {obs.get('clock', {}).get('timeOfDay')}")

    n0 = stack_of(obs, args.seed)
    print(f"播种前：item {args.seed} 堆叠 = {n0}")
    if n0 <= 0:
        print(f"[FAIL] 背包里没有 item {args.seed}，测试无意义（先买/拿种子）")
        return 1

    # ---- 挑格 ----
    if args.tile:
        tile = tuple(args.tile)
    else:
        tillable = [tuple(t) for t in (loc.get("tillable") or [])]
        if not tillable:
            print("[FAIL] location.tillable[] 为空（人不在农场可锄区？）")
            return 1
        pt = tuple(p.get("tile") or (0, 0))
        tile = min(tillable, key=lambda t: abs(t[0] - pt[0]) + abs(t[1] - pt[1]))
    print(f"目标格 {tile}（tillable 候选 {len(loc.get('tillable') or [])}）")

    # ---- 走位：工具只作用于**面朝的那一格**，且要在范围内 ⇒ 先站到目标格四邻 ----
    # （第一版漏了这一步，真机直接报 tool_ineffective：人在 (64,15)、目标 (64,18) 太远。）
    def stand_next_to(target: tuple[int, int]) -> bool:
        o = c.observe("full")
        pt = tuple((o.get("player") or {}).get("tile") or (-99, -99))
        if abs(pt[0] - target[0]) + abs(pt[1] - target[1]) == 1:
            return True
        tiles = {tuple(t.get("tile") or []) for t in (o.get("location") or {}).get("tiles") or []}
        cands = [(target[0] + dx, target[1] + dy) for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))]
        cands.sort(key=lambda t: (0 if t not in tiles else 1, abs(t[0] - pt[0]) + abs(t[1] - pt[1])))
        for t in cands:
            try:
                c.move_to(t[0], t[1], timeout_ms=15000)
                return True
            except BridgeError:
                continue
        return False

    if not stand_next_to(tile):
        print(f"[FAIL] 站不到 {tile} 的四邻（走位失败）")
        return 1
    obs = c.observe("full")
    print(f"站好位：玩家 {tuple((obs.get('player') or {}).get('tile') or [])}")

    # ---- 锄地（若已是耕地就跳过）----
    cur = tile_of(obs, tile)
    if not (cur and cur.get("kind") == "dirt"):
        try:
            res = c.use_tool(tile, tool="hoe", timeout_ms=15000)
            print(f"锄地回执：status={res.get('status')} {res.get('elapsedMs')}ms")
        except BridgeError as exc:
            print(f"[FAIL] 锄地失败：{getattr(exc, 'status', '?')} — {str(exc)[:200]}")
            return 1
        obs = c.observe("full")
        cur = tile_of(obs, tile)
        if not (cur and cur.get("kind") == "dirt"):
            print(f"[FAIL] 锄地后该格不是 dirt：{cur}")
            return 1
        print(f"锄地差分 ✅ kind={cur.get('kind')} plantable={cur.get('plantable')}")

    # ---- 播种 ----
    n_before = stack_of(obs, args.seed)
    t0 = time.time()
    try:
        res = c.plant(args.seed, tile, timeout_ms=20000)
        print(f"播种回执：status={res.get('status')} {res.get('elapsedMs')}ms")
        print(f"  回执 reason：{res.get('reason')}")
    except BridgeError as exc:
        print(f"[FAIL] 播种失败：{getattr(exc, 'status', '?')} — {str(exc)[:300]}")
        return 1

    # ---- 差分复核（权威）----
    obs2 = c.observe("full")
    n_after = stack_of(obs2, args.seed)
    t2 = tile_of(obs2, tile)
    crop = (t2 or {}).get("crop")
    print()
    print(f"播种后：item {args.seed} 堆叠 = {n_after}（前 {n_before}，差 {n_after - n_before}）")
    print(f"        {tile} tiles[] = {json.dumps(t2, ensure_ascii=False)}")
    print(f"耗时 {time.time() - t0:.1f}s")

    ok_crop = bool(crop)
    ok_consume = (n_after == n_before - 1)
    print()
    print(f"{'✅' if ok_crop else '❌'} 作物出现：crop={crop}")
    print(f"{'✅' if ok_consume else '❌'} 种子扣减：{n_before} → {n_after}（期望 {n_before - 1}）")
    if ok_crop and ok_consume:
        print("结论：VERIFIED —— 种一格、扣一个，与游戏自己的口径一致。")
        return 0
    print("结论：needs_review —— 上面有 ❌ 的判据没通过（回执不算证据）。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
