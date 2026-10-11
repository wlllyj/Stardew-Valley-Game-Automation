"""测量：时钟真实的推进速率 + 卡顿间隔（判断"时钟不走"是常态还是故障）。

用法：把游戏保持在前台、角色站定不动，跑 60 秒。
输出每次采样的 timeOfDay 与 liveness.secondsSinceClockMoved，
最后给出：观测窗口内推进了多少游戏分钟、最长一次停滞多少秒。

预期基准：星露谷单机 `Game1.gameTimeInterval` 累计到 7000ms 推进 10 分钟，
即**每 7 秒游戏时间走 10 分钟**（1 小时 ≈ 42 秒真实时间）。
"""
from __future__ import annotations

import sys
import time

from agentfarm import winfocus as wf
from agentfarm.bridge import BridgeClient, BridgeError


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    game = wf.find_game_window()
    if game is not None and wf.foreground_window() != game:
        wf.focus_window(game)
    c = BridgeClient()

    start = time.time()
    first_tod = None
    last_tod = None
    last_change = None
    max_gap = 0.0
    n_ticks = 0
    print("t(s)  时刻  active fg=游戏 isInBed canMove isModal 距上次走秒  间隔内推进")
    while time.time() - start < seconds:
        t = time.time() - start
        try:
            o = c.observe("summary", timeout=8.0)
            h = c.health(timeout=5.0)
        except BridgeError as exc:
            print(f"{t:5.1f}  采样失败 {exc.status}")
            time.sleep(1.0)
            continue
        tod = (o.get("clock") or {}).get("timeOfDay")
        p = o.get("player") or {}
        ui = o.get("ui") or {}
        lv = o.get("liveness") or {}
        active = (h.get("game") or {}).get("windowActive")
        fg_is_game = wf.foreground_window() == game
        gap = lv.get("secondsSinceClockMoved")
        if first_tod is None:
            first_tod = tod
            last_change = t
        if last_tod is not None and tod != last_tod:
            delta = (t - (last_change or 0))
            max_gap = max(max_gap, delta)
            n_ticks += 1
            last_change = t
            print(f"{t:5.1f}  {tod}  {active} {fg_is_game}  {p.get('isInBed')}  {p.get('canMove')}  {ui.get('isModal')}  {gap}  "
                  f"↑ 上次推进距今 {delta:.1f}s")
        else:
            print(f"{t:5.1f}  {tod}  {active} {fg_is_game}  {p.get('isInBed')}  {p.get('canMove')}  {ui.get('isModal')}  {gap}")
        last_tod = tod
        time.sleep(1.0)

    elapsed = time.time() - start
    print("\n== 汇总 ==")
    print(f"观测 {elapsed:.1f}s，时钟推进 {n_ticks} 次，{first_tod} → {last_tod}")
    print(f"最长一次停滞 {max_gap:.1f}s（基准：每 7s 应推进一次 10 分钟）")
    if n_ticks:
        print(f"实际速率 ≈ 每 {elapsed / n_ticks:.1f}s 推进 10 分钟")
    return 0


if __name__ == "__main__":
    sys.exit(main())
