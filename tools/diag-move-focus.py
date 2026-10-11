"""角色移动到底需不需要游戏窗口在前台？—— 当场 A/B 定因，不靠记忆。

起因（m01369）：用户说「刚刚我看到人物在动，但是时间一直没有变，有意思」。
这与我此前的结论冲突：
  * 结论甲（真机 1 测出）：失焦时 `PathFindController` 完全不驱动角色（10/10 失败，6.6 秒一格未动）；
  * 结论乙（A/B 实验测出）：失焦时**世界时钟**不推进。
用户看到的现象说明甲、乙可能被混为一谈：**"时钟不走"和"角色不动"是两件事**。

本脚本把两件事分开测：
  A 段（**不抢焦点**）：直接调 `BridgeClient.move_to`（不带任何 focus 调用），
     每次移动前后记录 windowActive / 玩家格 / timeOfDay / hasController / 位移。
  B 段（抢焦点）：每次移动前 `ensure_game_foreground()`，同样记录。
结束时把前台窗口还给原来的窗口。

判据：
  * A 段出现位移 ⇒ 「失焦时角色不动」**被证伪**，当初 10/10 失败另有原因，必须重新定因；
  * A 段零位移、B 段有位移 ⇒ 结论维持（但"时钟不走"仍可与移动解耦）。
运行期间请不要点游戏或打字（B 段会把焦点抢到游戏上）。

用法：
    python tools\\diag-move-focus.py            # 默认 A/B 各 3 次，交替走 (6,8)/(8,9)
    python tools\\diag-move-focus.py 6,8 5,8 4,8   # 指定一轮的格子序列
"""
from __future__ import annotations

import sys
import time

from agentfarm import winfocus as wf
from agentfarm.bridge import BridgeClient, BridgeError

DEFAULT_TILES = [(6, 8), (8, 9), (6, 8)]


def snap(c: BridgeClient) -> dict:
    """一次现场采样：游戏自报的焦点 + 玩家格 + 世界时刻 + 控制器。"""
    h = c.health(timeout=5.0)
    o = c.observe("summary", timeout=8.0)
    p = o.get("player") or {}
    return {
        "active": (h.get("game") or {}).get("windowActive"),
        "ticks": (h.get("runtime") or {}).get("ticks"),
        "tile": tuple(p.get("tile") or ()),
        "tod": (o.get("clock") or {}).get("timeOfDay"),
        "controller": p.get("hasController"),
        "canMove": p.get("canMove"),
        "stall": (o.get("liveness") or {}).get("secondsSinceClockMoved"),
    }


def move(c: BridgeClient, x: int, y: int, timeout_ms: int = 2500) -> tuple[str, str]:
    try:
        res = c.move_to(x, y, timeout_ms=timeout_ms)
        return str(res.get("status")), str(res.get("reason") or "")
    except BridgeError as exc:
        return str(exc.status), str(exc.reason or "")


def run_phase(c: BridgeClient, name: str, tiles: list[tuple[int, int]], steal_focus: bool) -> list[dict]:
    print(f"\n===== {name}（{'每次移动前抢焦点' if steal_focus else '**不抢焦点**'}）=====")
    rows: list[dict] = []
    for (x, y) in tiles:
        if steal_focus:
            wf.ensure_game_foreground()
        before = snap(c)
        t0 = time.monotonic()
        status, reason = move(c, x, y)
        dt = time.monotonic() - t0
        after = snap(c)
        moved = before["tile"] != after["tile"]
        displaced = abs(after["tile"][0] - before["tile"][0]) + abs(after["tile"][1] - before["tile"][1]) \
            if before["tile"] and after["tile"] else 0
        clock_moved = before["tod"] != after["tod"]
        rows.append({"target": (x, y), "status": status, "reason": reason[:70], "moved": moved,
                     "displaced": displaced, "clock_moved": clock_moved, "dt": dt,
                     "active_before": before["active"], "active_after": after["active"],
                     "tile": f"{before['tile']}→{after['tile']}", "tod": f"{before['tod']}→{after['tod']}",
                     "ticks": f"{before['ticks']}→{after['ticks']}"})
        r = rows[-1]
        print(f"  →({x},{y}) {status:18s} 位移={displaced}格 ({r['tile']})  "
              f"时钟={'动了' if clock_moved else '没动'} ({r['tod']})  "
              f"active {r['active_before']}→{r['active_after']}  ticks {r['ticks']}  {dt:.1f}s  {reason[:60]!r}")
    return rows


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    tiles = list(DEFAULT_TILES)
    if len(sys.argv) > 1:
        tiles = []
        for raw in sys.argv[1:]:
            x, y = raw.split(",")
            tiles.append((int(x), int(y)))

    original_fg = wf.foreground_window()
    game = wf.find_game_window()
    c = BridgeClient()
    s0 = snap(c)
    print(f"游戏窗口 hwnd={game} 当前前台 hwnd={original_fg}"
          f"（{'游戏在前台' if original_fg == game else '**游戏不在前台**'}）")
    print(f"起始：玩家格={s0['tile']} tod={s0['tod']} active={s0['active']} "
          f"ticks={s0['ticks']} stall={s0['stall']}s")

    a = run_phase(c, "A 段", tiles, steal_focus=False)
    b = run_phase(c, "B 段", tiles, steal_focus=True)

    a_moved = sum(1 for r in a if r["moved"])
    b_moved = sum(1 for r in b if r["moved"])
    a_clock = sum(1 for r in a if r["clock_moved"])
    b_clock = sum(1 for r in b if r["clock_moved"])
    print(f"\n===== 判据 =====")
    print(f"  A 段（不抢焦点）：位移 {a_moved}/{len(a)} 次，时钟推进 {a_clock}/{len(a)} 次")
    print(f"  B 段（抢焦点）  ：位移 {b_moved}/{len(b)} 次，时钟推进 {b_clock}/{len(b)} 次")
    if a_moved:
        print("  ⇒ 「失焦时角色完全不动」被证伪：**移动与时钟是两件被不同条件门控的事**，需重新定因。")
    elif b_moved:
        print("  ⇒ 结论维持：移动需要游戏窗口在前台；但「时钟不走」不能拿「角色不动」来间接推断。")
    else:
        print("  ⇒ A、B 段都没位移：别急着下结论，先查模态/家具/卡死（reason 里有原始信息）。")

    if original_fg and original_fg != wf.foreground_window():
        wf.focus_window(original_fg)
        print(f"已把焦点还给原前台 hwnd={original_fg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
