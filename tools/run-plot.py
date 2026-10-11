# -*- coding: utf-8 -*-
"""P3 第⑤步（**确定性部分**）：5x5 最小闭环 —— 清障 → 开垦 → 播种 → 浇水，全程用观测差分判定。

【为什么先做"确定性"这一半】
P3 的计划里，第⑤步包含两个东西：
  1. **机械流程**（选一小块地，逐格清障/锄/种/浇）—— 不需要 LLM，纯代码；
  2. **边界决策**（换任务类型、异常恢复、跨日复盘）—— 那才是"慢脑（LLM）"该介入的地方。
用户 m01184 明确要求"大模型开始介入的时候告诉我一下"，所以本轮**只做第 1 部分**，
把 LLM（`brain/agentfarm/llm.py`）的接入留到用户点头之后。

【判据铁律（本项目的最高纪律）】
每一步都**不信回执**：动作发完立刻重新 `observe?detail=full`，用 `location.tiles[]` 差分看那一格
到底变没变。没变就是没做成 —— 记进 `failures`，绝不写成"完成"。
任务终态只有 `VERIFIED`（有差分证据）与 `needs_review`（有格子没做成），两者绝不混。

用法：
    set PYTHONPATH=D:\\...\\星露谷游戏自动化\\brain
    python tools\\run-plot.py --size 5 --seed 472
    python tools\\run-plot.py --size 3 --seed 472 --max-steps 200
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

DEBRIS_KINDS = ("weed", "twig", "stone")
# 这些格子**不能锄**（要么得用别的工具、要么根本不产耕地）——见到就跳过并记原因
SKIP_KINDS = {"grass": "草（该用镰刀割，锄头不产耕地）",
              "tree": "树（先砍）",
              "fruitTree": "果树",
              "clump": "资源堆（先敲）",
              "bush": "灌木",
              "object": "放置物/机器（不该动）"}


@dataclass
class TileResult:
    tile: tuple[int, int]
    cleared: bool = False
    tilled: bool = False
    planted: bool = False
    watered: bool = False
    skipped: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return self.planted and self.watered


class PlotRun:
    def __init__(self, client: BridgeClient, *, size: int, seed: str, verbose: bool = True,
                 anchor: tuple[int, int] | None = None) -> None:
        self.c = client
        self.size = size
        self.seed = seed
        self.verbose = verbose
        self.anchor = anchor
        self.results: list[TileResult] = []
        self.transport_errors: list[str] = []
        self.walk_steps = 0

    # ---------- 观测 ----------
    def snap(self) -> dict:
        return self.c.observe("full")

    @staticmethod
    def tiles_of(obs: dict) -> dict[tuple[int, int], dict]:
        tiles = (obs.get("location") or {}).get("tiles") or []
        return {tuple(t.get("tile") or []): t for t in tiles}

    @staticmethod
    def tillable_of(obs: dict) -> set[tuple[int, int]]:
        return {tuple(t) for t in ((obs.get("location") or {}).get("tillable") or [])}

    @staticmethod
    def player_of(obs: dict) -> dict:
        return obs.get("player") or {}

    def seed_stack(self, obs: dict) -> int:
        """背包里该种子的总堆叠（同 id 可能分几格）。"""
        total = 0
        for it in self.player_of(obs).get("inventory") or []:
            if str(it.get("id")) == str(self.seed):
                total += int(it.get("stack") or 0)
        return total

    # ---------- 选地 ----------
    def pick_plot(self, tillable: set[tuple[int, int]], pt: tuple[int, int]) -> list[tuple[int, int]]:
        """以"离玩家最近的可锄格"为左下角，取 size×size 的方块（含不可锄的格，由逐格流程再判）。

        【为什么不要求整块都可锄】农场里到处是杂草/石头，"整块都可锄"几乎不存在；
        真正的判据是**逐格**的（能清就清、不能锄就跳过并记账），这样才诚实。

        【--anchor 的用途】不指定时锚点=离玩家最近的可锄格（每次跑可能不同）；
        要"换一块地再验一遍"时就显式给锚点，避免踩在同一片已经种过的地上。
        """
        if self.anchor is not None:
            x0, y0 = self.anchor
            return [(x0 + dx, y0 + dy) for dy in range(self.size) for dx in range(self.size)]
        if not tillable:
            return []
        anchor = min(tillable, key=lambda t: abs(t[0] - pt[0]) + abs(t[1] - pt[1]))
        x0, y0 = anchor
        return [(x0 + dx, y0 + dy) for dy in range(self.size) for dx in range(self.size)]

    # ---------- 走位 ----------
    def stand_next_to(self, tile: tuple[int, int]) -> bool:
        """站到目标格的四邻之一（优先能站的）。返回是否成功。"""
        obs = self.snap()
        tiles = self.tiles_of(obs)
        pt = tuple(self.player_of(obs).get("tile") or (-99, -99))
        if pt in [(tile[0] + dx, tile[1] + dy) for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))]:
            return True

        # 优先"该格上什么都没有"的邻居（大概率能站）
        cands = [(tile[0] + dx, tile[1] + dy) for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))]
        cands.sort(key=lambda t: (0 if t not in tiles else 1, abs(t[0] - pt[0]) + abs(t[1] - pt[1])))
        for t in cands:
            try:
                self.c.move_to(t[0], t[1], timeout_ms=15000)
                self.walk_steps += 1
                return True
            except BridgeError:
                continue
        return False

    # ---------- 单格流程 ----------
    def state_of(self, obs: dict, tile: tuple[int, int]) -> dict | None:
        return self.tiles_of(obs).get(tile)

    def do_tile(self, tile: tuple[int, int]) -> TileResult:
        r = TileResult(tile=tile)
        obs = self.snap()
        cur = self.state_of(obs, tile)
        tillable = self.tillable_of(obs)

        # 0) 不能锄的（草/树/机器…）→ 跳过并记原因（**不假装做了**）
        if cur is not None and cur.get("kind") in SKIP_KINDS:
            r.skipped = SKIP_KINDS[cur["kind"]]
            return r
        if cur is None and tile not in tillable:
            r.skipped = "游戏不认为这格可锄（无 Diggable 属性）"
            return r

        if not self.stand_next_to(tile):
            r.skipped = "四邻都站不过去"
            return r

        # 1) 清障（杂草/树枝/石头；auto 会自己挑工具并失败换工具）
        for _ in range(2):
            obs = self.snap()
            cur = self.state_of(obs, tile)
            if cur is None or cur.get("kind") not in DEBRIS_KINDS:
                break
            try:
                self.c.use_tool(tile, tool="auto", timeout_ms=15000)
            except BridgeError as exc:
                r.notes.append(f"清障失败：{getattr(exc, 'status', '?')}")
                break
        obs = self.snap()
        cur = self.state_of(obs, tile)
        if cur is not None and cur.get("kind") in DEBRIS_KINDS:
            r.notes.append("清障后该格仍有障碍")
            r.skipped = "障碍清不掉"
            return r
        r.cleared = True

        # 2) 锄地（判据：kind 变成 dirt）
        try:
            self.c.use_tool(tile, tool="hoe", timeout_ms=15000)
        except BridgeError as exc:
            r.notes.append(f"锄地回执：{getattr(exc, 'status', '?')} — {str(exc)[:120]}")
        obs = self.snap()
        cur = self.state_of(obs, tile)
        if not (cur and cur.get("kind") == "dirt"):
            r.notes.append("锄地后该格不是 dirt")
            return r
        r.tilled = True

        # 3) 播种（判据：出现 crop）
        try:
            self.c.plant(self.seed, tile, timeout_ms=20000)
        except BridgeError as exc:
            r.notes.append(f"播种回执：{getattr(exc, 'status', '?')} — {str(exc)[:160]}")
        obs = self.snap()
        cur = self.state_of(obs, tile)
        if not (cur and cur.get("crop")):
            # 种子用完是**整体性缺料**，不是这一格的问题 —— 显式报出来，别让后面的格子
            # 一个个去撞墙（v0.7.19 之前"placementAction 不扣种子"把这条路掩盖了）。
            if self.seed_stack(obs) <= 0:
                r.skipped = f"种子用完（item {self.seed} 堆叠 0）"
                return r
            r.notes.append("播种后该格没有 crop")
            return r
        r.planted = True

        # 4) 浇水（判据：watered == true）
        try:
            self.c.use_tool(tile, tool="can", timeout_ms=15000)
        except BridgeError as exc:
            r.notes.append(f"浇水回执：{getattr(exc, 'status', '?')}")
        obs = self.snap()
        cur = self.state_of(obs, tile)
        if cur and cur.get("watered"):
            r.watered = True
        else:
            r.notes.append("浇水后 watered 仍为 false")
        return r

    # ---------- 主循环 ----------
    def run(self, *, max_steps: int = 400, min_stamina: float = 20.0) -> int:
        t0 = time.time()
        obs = self.snap()
        pt = tuple(self.player_of(obs).get("tile") or (0, 0))
        tillable = self.tillable_of(obs)
        plot = self.pick_plot(tillable, pt)
        if not plot:
            print("✗ 观测里给不出可锄格（location.tillable[] 为空）——先走到农场空地再试")
            return 2

        print(f"地块：{self.size}x{self.size} = {len(plot)} 格，锚点 {plot[0]}（玩家 {pt}）")
        print(f"可锄格候选 {len(tillable)} 个；stamina 下限 {min_stamina:g}")

        for i, tile in enumerate(plot, 1):
            if i > max_steps:
                print(f"达到 max_steps={max_steps}，提前结束")
                break
            obs = self.snap()
            p = self.player_of(obs)
            stam = p.get("stamina") or 0
            if stam < min_stamina:
                print(f"⚠️ 体力 {stam:g} < {min_stamina:g}，停止（剩下的格子留给下一轮/次日）")
                break

            r = self.do_tile(tile)
            self.results.append(r)
            mark = "✅" if r.done else ("⏭️" if r.skipped else "❌")
            tail = r.skipped or ("；".join(r.notes) if r.notes else "")
            print(f"[{i}/{len(plot)}] {mark} {tile} cleared={r.cleared} tilled={r.tilled} "
                  f"planted={r.planted} watered={r.watered} 体力={stam:g} {tail}")

        # ---------- 收尾统计（终态只有 VERIFIED / needs_review）----------
        good = [r for r in self.results if r.done]
        skipped = [r for r in self.results if r.skipped]
        bad = [r for r in self.results if not r.done and not r.skipped]
        print()
        print(f"完成 {len(good)} / 处理 {len(self.results)} 格；跳过 {len(skipped)}；没做成 {len(bad)}；"
              f"走位 {self.walk_steps} 次；耗时 {time.time() - t0:.0f}s")
        if skipped:
            print("跳过明细：" + "；".join(f"{r.tile}:{r.skipped}" for r in skipped))
        if bad:
            print("没做成明细：" + "；".join(f"{r.tile}:{'；'.join(r.notes)}" for r in bad))
        verdict = "VERIFIED" if (good and not bad) else ("needs_review" if bad or not good else "VERIFIED")
        print(f"终态：{verdict}（判据：observe?detail=full 的 tiles[] 差分；跳过不算完成，也不算失败）")
        return 0 if verdict == "VERIFIED" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="P3 5x5 最小闭环（确定性部分，不涉及 LLM）")
    ap.add_argument("--size", type=int, default=5, help="地块边长（默认 5 → 25 格）")
    ap.add_argument("--seed", default="472", help="种子 ItemId（默认 472 = 防风草种子）")
    ap.add_argument("--max-steps", type=int, default=400, dest="max_steps")
    ap.add_argument("--min-stamina", type=float, default=20.0, dest="min_stamina")
    ap.add_argument("--anchor", nargs=2, type=int, metavar=("X", "Y"), default=None,
                    help="地块左下角（省略=离玩家最近的可锄格；换一块地复验时显式指定）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    client = BridgeClient(timeout=120.0)
    h = client.health()
    print(f"Mod {h.get('modVersion')} runtime={json.dumps(h.get('runtime'), ensure_ascii=False)}")
    return PlotRun(client, size=args.size, seed=args.seed,
                   anchor=tuple(args.anchor) if args.anchor else None).run(
        max_steps=args.max_steps, min_stamina=args.min_stamina
    )


if __name__ == "__main__":
    raise SystemExit(main())
