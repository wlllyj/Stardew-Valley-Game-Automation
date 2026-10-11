# -*- coding: utf-8 -*-
"""着陆契约**验收**：连续做 N 次 move_to，逐次校验「回执 ok ⇒ 观测确实在目标格」。

【与 tools\\diag-landing.py 的分工】
* `diag-landing.py` —— **诊断**：盯住一个指定格，把回执、观测轨迹、`hasController` 全打出来，
  用来复现/研究"落点契约破裂"。
* 本脚本 —— **验收**：不需要你指定格子，自己从**玩家当前所在格**（游戏真值）出发生成候选目标，
  连续跑 N 轮，给出"通过/破裂"的结论与退出码，用来判定"修复到底有没有生效"。

【为什么目标格是"试着来"的而不是写死的】
架构 §5.2.1 禁止硬编码地名/坐标：本脚本对地图一无所知，只用玩家当前格 + 偏移量生成候选，
再按 Mod 的**回执状态码**分类：
  * `precondition_failed`（家具/不可通行/出图）⇒ 这个候选**不可用**，换下一个（不算失败）；
  * `ok` ⇒ 立刻用 `/v1/observe` 去**观测**，比对是否真的停在目标格（回执是声明，观测才是证据）；
  * 其它状态（blocked/timeout/ui_modal/...）⇒ 记为移动失败。

【先决条件（很重要）】
脚本第一步读 `/v1/health` 比对 `modVersion` 与脑侧期望值。**不匹配就直接停止并返回 3** ——
因为"着陆契约修复"是 Mod 侧代码，跑在旧 Mod 上得到的任何"通过/失败"都没有意义
（旧 Mod 的到达判据就是被修掉的那一条）。同理，停在标题界面时会提示先跑 `agentfarm load`。

用法：
    set PYTHONPATH=D:\\...\\星露谷游戏自动化\\brain
    python tools\\verify-landing.py --rounds 8
    python tools\\verify-landing.py --rounds 8 --max-radius 5 --json

退出码：0=全部通过；1=出现落点不符；2=连不上桥；3=先决条件不满足（版本/存档）；
        4=没有可用候选（无法判定，通常是周围全是障碍或地图太小）
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import MOD_VERSION_EXPECTED, BridgeClient, BridgeError  # noqa: E402


def tile_of(obs: dict) -> list[int] | None:
    t = (obs.get("player") or {}).get("tile")
    return [int(t[0]), int(t[1])] if isinstance(t, (list, tuple)) and len(t) == 2 else None


def candidates(radius: int) -> list[tuple[int, int]]:
    """按"离玩家越近越先试"的顺序生成候选偏移（不含 (0,0)）。"""
    out: list[tuple[int, int]] = []
    for d in range(1, radius + 1):
        ring = []
        for dx in range(-d, d + 1):
            for dy in range(-d, d + 1):
                if abs(dx) + abs(dy) != d:
                    continue
                if dx == 0 and dy == 0:
                    continue
                ring.append((dx, dy))
        # 同一圈里先走正方向（更容易是空地：背对墙角）
        ring.sort(key=lambda p: (-(p[0] > 0) - (p[1] > 0), abs(p[0]) + abs(p[1])))
        out.extend(ring)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="着陆契约验收：连续 N 次 move_to 是否每次都真的落在目标格")
    ap.add_argument("--rounds", type=int, default=8, help="要完成的「通过」轮数（默认 8）")
    ap.add_argument("--max-radius", type=int, default=4, dest="max_radius", help="候选偏移的最大曼哈顿距离")
    ap.add_argument("--timeout-ms", type=int, default=8000, dest="timeout_ms")
    ap.add_argument("--settle", type=float, default=0.4, help="回执 ok 之后等多久再观测（秒）")
    ap.add_argument("--max-attempts", type=int, default=14, dest="max_attempts",
                    help="每轮最多试几个候选（用完即记为无法判定）")
    ap.add_argument("--seed", type=int, default=20261011,
                    help="候选顺序的随机种子（同一种子可复现；排序按'先远后近'，同距离内随机）")
    ap.add_argument("--json", action="store_true", help="额外打印机器可读的结果 JSON")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    client = BridgeClient(timeout=25.0)

    # ---------- 先决条件 ----------
    try:
        h = client.health()
    except BridgeError as exc:
        print(f"[STOP] 连不上桥：{exc}")
        return 2

    mod_version = h.get("modVersion")
    rt = h.get("runtime") or {}
    print(f"Mod {mod_version}（脑侧期望 {MOD_VERSION_EXPECTED}）| "
          f"hasSaveLoaded={rt.get('hasSaveLoaded')} onTitleScreen={rt.get('onTitleScreen')}")

    if mod_version != MOD_VERSION_EXPECTED:
        print(f"[STOP] 游戏里跑的是 {mod_version}，不是 {MOD_VERSION_EXPECTED}。")
        print("       着陆契约修复是 Mod 侧代码；在旧 Mod 上测出来的结果没有意义。")
        print("       请先装机并重启游戏（重启后停在标题界面：tools\\agentfarm.cmd load）。")
        return 3

    if not rt.get("hasSaveLoaded"):
        print("[STOP] 尚未加载存档。先跑：tools\\agentfarm.cmd load")
        return 3

    # ---------- 逐轮验收 ----------
    offs = candidates(args.max_radius)
    rng = random.Random(args.seed)
    done = 0
    mismatches: list[dict] = []
    failures: list[dict] = []
    skipped = 0
    unreachable = 0
    attempts_total = 0
    rounds_started = 0

    print(f"目标：连续 {args.rounds} 轮『回执 ok 且观测在目标格且 hasController=false』")
    print(f"候选偏移半径 ≤ {args.max_radius}（共 {len(offs)} 个），每轮最多试 {args.max_attempts} 个\n")

    # 硬上限：每轮最多试 max_attempts 个候选，且总轮数不超过 rounds*4
    #（防"某个方向永远是死路"导致同一批候选被无限重试 —— 第一版就踩了这个）
    while done < args.rounds and rounds_started < args.rounds * 4:
        rounds_started += 1
        try:
            before = client.observe("summary")
        except BridgeError as exc:
            print(f"[STOP] 取快照失败：{exc}")
            return 2

        cur = tile_of(before)
        loc = (before.get("player") or {}).get("location")
        if cur is None:
            print(f"[STOP] 观测里读不到玩家坐标（loc={loc}）")
            return 3

        tried: set[tuple[int, int]] = set()
        usable = 0          # 这一轮里"真的尝试过移动"的候选数（precondition/unreachable 不算）
        round_ok = False

        # 每轮重新洗牌：先试**远**的（2~4 格），同距离内随机 —— 这样才真的在测"多格行走的落点"，
        # 而不是永远只测相邻一格那一两个格子（第一版就是每轮重复同样两个格子）。
        order = list(offs)
        rng.shuffle(order)
        order.sort(key=lambda p: -(abs(p[0]) + abs(p[1])))

        for dx, dy in order:
            if len(tried) >= args.max_attempts:
                break

            target = (cur[0] + dx, cur[1] + dy)
            if target in tried:
                continue
            tried.add(target)
            attempts_total += 1

            t0 = time.time()
            try:
                res = client.move_to(target[0], target[1], timeout_ms=args.timeout_ms,
                                     based_on_seq=before.get("worldSeq"))
            except BridgeError as exc:
                st = getattr(exc, "status", "")
                # 这两类 = "这个候选格根本走不得"，换下一个（不算移动失败，但记数）
                if st == "precondition_failed":
                    skipped += 1
                    print(f"  · 起点 {cur} 候选 {target} 不可用（precondition_failed）→ 换下一个")
                    continue
                if st == "unreachable":
                    unreachable += 1
                    print(f"  · 起点 {cur} 候选 {target} A* 无解（unreachable）→ 换下一个")
                    continue
                failures.append({"from": cur, "target": list(target), "status": st, "reason": str(exc)})
                print(f"  ✗ 起点 {cur} → {target} 移动失败（{st}）：{exc}")
                continue

            usable += 1
            ms = res.get("elapsedMs")
            time.sleep(args.settle)
            try:
                after = client.observe("summary")
            except BridgeError as exc:
                failures.append({"from": cur, "target": list(target), "status": "observe_failed",
                                 "reason": str(exc)})
                print(f"  ✗ 移动后取快照失败：{exc}")
                continue

            landed = tile_of(after)
            ctrl = (after.get("player") or {}).get("hasController")
            wall = (time.time() - t0) * 1000

            if landed == list(target) and ctrl is False:
                done += 1
                round_ok = True
                print(f"  ✓ [{done}/{args.rounds}] {cur} → {target} 观测确认命中"
                      f"（回执 {ms}ms / 实测 {wall:.0f}ms，hasController={ctrl}）")
            elif landed == list(target):
                mismatches.append({"from": cur, "target": list(target), "landed": landed,
                                   "hasController": ctrl, "kind": "controller_not_cleared"})
                print(f"  ✗ 命中 {target} 但 hasController={ctrl}（没停干净）")
            else:
                d = [None, None] if landed is None else [landed[0] - target[0], landed[1] - target[1]]
                mismatches.append({"from": cur, "target": list(target), "landed": landed,
                                   "hasController": ctrl, "delta": d, "kind": "landing_mismatch"})
                print(f"  ✗ **落点不符**：回执 ok（{ms}ms）但观测在 {landed}"
                      f"（目标 {target}，偏移 dx={d[0]} dy={d[1]}，hasController={ctrl}）")

            if round_ok or mismatches:
                break   # 这一轮已有结论（通过或破裂），下一轮重新选点

        if usable == 0:
            print(f"\n[STOP] 从 {cur} 出发的 {len(tried)} 个候选全部不可用/无解 ⇒ 无法判定。")
            print(f"       建议挪到更开阔的地点（例如 Farm）再跑，或加大 --max-radius。")
            return 4

    # ---------- 结论 ----------
    print()
    print(f"共 {rounds_started} 轮、{attempts_total} 次候选尝试："
          f"命中 {done}，落点不符 {len(mismatches)}，移动失败 {len(failures)}，"
          f"候选不可用跳过 precondition_failed={skipped} / unreachable={unreachable}")

    result = {
        "modVersion": mod_version,
        "roundsRequested": args.rounds,
        "roundsStarted": rounds_started,
        "landed": done,
        "mismatches": mismatches,
        "failures": failures,
        "skippedPrecondition": skipped,
        "skippedUnreachable": unreachable,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if mismatches:
        print("结论：**着陆契约不成立**——回执 ok 与观测不一致，P3 会以『种到隔壁』的方式失败。")
        return 1
    if done >= args.rounds:
        if failures:
            print("结论：着陆契约成立（每轮回执 ok 都被观测证实停在目标格、控制器已清），另有移动失败见上。")
        else:
            print("结论：着陆契约成立——每一次回执 ok 都被观测证实停在目标格上，且控制器已清干净。")
        return 0
    print(f"结论：只完成了 {done}/{args.rounds} 轮通过（其余候选不可用/无解），未出现落点不符。")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
