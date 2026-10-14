r"""task-81 B 段：跑**真代码**一天 —— 大片 encircled + 5 格真 unreachable 混在一起。

要证的事（卡面第 4 条）：
  * `unreachable_bound == max(5, floor(0.2 * bound_basis))`，**不许被 encircled 抬高**
    （旧口径 `0.2 * attempted` 会被抬到几十）；
  * 真不可达那 5 格仍在界内 ⇒ `unreachable_exempt == 5`（豁免没被 encircled 吃掉）；
  * `bound_basis == attempted - encircled`，四个出口（day_end / unreachable_summary /
    refused_summary / encircled_summary）都写 `bound_basis`。

世界是我自己搭的（`T81_ROOT` 可指向别的树，用来证明本探针能变红）。
"""
import os
import sys
import json

ROOT = os.environ.get("T81_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "tests"), os.path.join(ROOT, "brain"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_longrun as TL                                     # noqa: E402
from agentfarm.farmwork import ENCIRCLED_CODE, UNREACHABLE_CODE   # noqa: E402
from agentfarm.bridge import BridgeError                      # noqa: E402

OX, OY, N = 60, 8, 14          # 14x14 的杂草海
DEAD = [(OX + i, OY + 5) for i in range(5)]      # 5 格：北邻没有落脚点 ⇒ 真"走不到"
NORTH = {(x, y - 1) for x, y in DEAD}


class WeedSea(TL.FakeWorld):
    """整片杂草海：海里的每一格四邻都是"观测到但站不上去"的杂草 ⇒ 全部 encircled。"""

    def __init__(self, *, extra_ring: bool = True) -> None:
        super().__init__(weeds=0)
        self.tillable = {(OX + x, OY + y) for x in range(N) for y in range(N)}
        self.blockers = {t: "weed" for t in self.tillable}
        if extra_ring:                     # 外圈也铺满：保证棋盘边缘的格子四邻都"观测到"
            for x in range(OX - 1, OX + N + 1):
                for y in range(OY - 1, OY + N + 1):
                    if (x, y) not in self.tillable:
                        self.blockers[(x, y)] = "weed"
        for t in NORTH:                    # 这 5 格的北邻留空（未观测 ⇒ 脑认为"能站"）
            self.blockers.pop(t, None)
        self.dead_targets = list(DEAD)
        self.player_tile = [OX - 2, OY - 2]

    def obs(self):
        o = super().obs()
        for tv in o["location"]["tiles"]:
            tv["standable"] = False        # 观测说：这些东西上站不住
        return o


class SeaClient(TL.FakeClient):
    """整片海 + 5 个北邻都"走不上去"（真机是 Mod 回 unreachable）。"""

    def __init__(self, world: WeedSea) -> None:
        super().__init__(world)
        self.unwalkable = set(world.blockers) | set(NORTH)

    def move_to(self, x, y, *, timeout_ms=None, allow_bed=None):
        if (int(x), int(y)) in self.unwalkable:
            raise BridgeError(f"走向 ({int(x)}, {int(y)}) 时寻路无法到达", status="unreachable")
        return super().move_to(x, y, timeout_ms=timeout_ms, allow_bed=allow_bed)

    def buy(self, item, count=10, *, shop="SeedShop", timeout_ms=25000):
        return self.w.buy(item, count, shop)


def run_one(plot_size: int = N):
    w = WeedSea()
    client = SeaClient(w)
    from agentfarm.farmwork import FarmWorker
    worker = FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
    run = TL.make_run(w, client_factory=lambda: client, worker_factory=lambda c: worker,
                      target_days=1, max_days=1, plot_size=plot_size, zone_split=2)
    run.worker = worker
    run.client = client
    code = run.run()
    return w, run, code


def main() -> int:
    w, run, code = run_one()
    rep = run.days[0]
    entries = list(run.entries)
    day_end = [e for e in entries if e.get("event") == "day_end"][-1]

    attempted = sum(int(s.get("attempted") or 0) for s in rep.stages)
    basis = sum(int(s.get("bound_basis") or 0) for s in rep.stages)
    encircled = sum(int(s.get("encircled") or 0) for s in rep.stages)
    tried = sum(int(s.get("encircled_tried") or 0) for s in rep.stages)
    enc_ev = [e for e in entries if e.get("event") == "encircled"]
    enc_sum = [e for e in entries if e.get("event") == "encircled_summary"]
    un_ev = [e for e in entries if e.get("event") == "unreachable"]
    un_sum = [e for e in entries if e.get("event") == "unreachable_summary"]
    ref_sum = [e for e in entries if e.get("event") == "refused_summary"]

    print("== 汇总 ==")
    print(f"exit={code} verified={rep.verified}")
    print(f"attempted={attempted} bound_basis(Σ stage)={basis} encircled_steps={encircled} "
          f"encircled_tried={tried}")
    print(f"rep.bound_basis={rep.bound_basis} rep.unreachable={rep.unreachable} "
          f"rep.unreachable_bound={rep.unreachable_bound} exempt={rep.unreachable_exempt}")
    print(f"旧口径 0.2*attempted -> {max(5, int(0.2 * attempted))}；"
          f"新口径 0.2*bound_basis -> {max(5, int(0.2 * basis))}")
    print("checks:", json.dumps(rep.checks, ensure_ascii=False, sort_keys=True))
    for key in ("attempted", "bound_basis", "unreachable", "unreachable_bound",
                "unreachable_exempt", "encircled", "encircled_tiles", "encircled_bound"):
        print(f"  day_end[{key}] = {day_end.get(key)!r}")
    print("day_end keys 含 bound_basis:", "bound_basis" in day_end)
    print(f"encircled 逐格事件 {len(enc_ev)} 条；样例 keys={sorted(enc_ev[0].keys()) if enc_ev else None}")
    if enc_ev:
        e0 = enc_ev[0]
        print("  样例:", json.dumps({k: e0.get(k) for k in
                                    ("stage", "tile", "kinds", "tried_open", "reason")},
                                   ensure_ascii=False))
    print(f"encircled_summary {len(enc_sum)} 条:",
          json.dumps({k: enc_sum[0].get(k) for k in
                      ("count", "attempted", "bound_basis", "engaged", "tried_open_steps")},
                     ensure_ascii=False) if enc_sum else None)
    print(f"unreachable 逐格事件 {len(un_ev)} 条；样例 tile="
          f"{un_ev[0].get('tile') if un_ev else None} reason={un_ev[0].get('reason') if un_ev else None}")
    print(f"unreachable_summary {len(un_sum)} 条:",
          json.dumps({k: un_sum[0].get(k) for k in
                      ("count", "bound", "attempted", "bound_basis", "exempted", "engaged")},
                     ensure_ascii=False) if un_sum else None)
    print(f"refused_summary {len(ref_sum)} 条（本世界应该 0）")
    print(f"玩家最终位置: {w.player_tile}")

    # 逐条判定
    fails = []
    if basis != attempted - encircled:
        fails.append(f"bound_basis != attempted - encircled（{basis} != {attempted} - {encircled}）")
    unreach_tiles = {tuple(t) for t in rep.unreachable_tiles}
    enc_tiles = {tuple(t) for t in rep.encircled_tiles}
    hit = [t for t in DEAD if t in unreach_tiles]
    print(f"我造的 5 格真走不到里、真被试到的: {hit}")
    print(f"unreachable ∩ encircled = {sorted(unreach_tiles & enc_tiles)}")
    if not hit:
        fails.append("我造的 5 格真走不到一格都没进 unreachable_tiles")
    if unreach_tiles & enc_tiles:
        fails.append("同一格同时进 unreachable 与 encircled：" + repr(sorted(unreach_tiles & enc_tiles)))
    if rep.unreachable_bound != max(5, int(0.2 * basis)):
        fails.append(f"bound != max(5, floor(0.2*bound_basis))（{rep.unreachable_bound}）")
    if rep.unreachable_bound >= max(5, int(0.2 * attempted)) and attempted > basis:
        fails.append("新上界没有比旧口径更严（没有被 encircled 抬高这条没被证到）")
    if rep.unreachable_exempt != 5:
        fails.append(f"5 格真不可达没被豁免（exempt={rep.unreachable_exempt}）")
    if "bound_basis" not in day_end:
        fails.append("day_end 缺 bound_basis")
    if not enc_sum or enc_sum[0].get("bound_basis") != basis:
        fails.append("encircled_summary 缺 bound_basis 或值不对")
    if enc_sum and "tried_open_steps" not in enc_sum[0]:
        fails.append("encircled_summary 缺 tried_open_steps")
    if un_sum and (un_sum[0].get("bound_basis") != basis or "attempted" not in un_sum[0]):
        fails.append("unreachable_summary 的 bound_basis/attempted 不对")
    if enc_ev and not {"kinds", "tried_open"} <= set(enc_ev[0]):
        fails.append("逐格 encircled 事件缺 kinds/tried_open")
    print()
    if fails:
        print("B 段判定：FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("B 段判定：PASS（encircled 没有抬高上界；5 格真不可达仍被豁免）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
