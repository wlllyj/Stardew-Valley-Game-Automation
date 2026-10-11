"""诊断：时钟停摆到底是"游戏循环停了"还是"循环在跑但时间不累积"？

关键：`/v1/health` 早就有 `runtime.ticks`（游戏 Update 的 tick 计数）与
`game.windowActive`（`Game1.game1.IsActive`），把它们和 `clock.timeOfDay`、
`game.shouldTimePass` 一起采样，就能二分定位：

  * ticks 不涨            → **游戏循环真的停了**（进程被挂起/被暂停渲染）
  * ticks 在涨但时间不涨   → 循环在跑，是 `shouldTimePass` / `gameTimeInterval` 的问题
  * ticks 在涨 + 一次跳多档 → 循环有几十秒的"长帧"，MonoGame 把积压的真实耗时
                            一次补给 `gameTimeInterval`，于是连跳好几个 10 分钟

只读状态，不动焦点、不发任何输入。
"""
from __future__ import annotations

import sys
import time

from agentfarm.bridge import BridgeClient, BridgeError


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    c = BridgeClient()

    start = time.time()
    prev_tod = prev_ticks = None
    last_change_t = 0.0
    jumps: list[str] = []
    frozen_with_ticks = 0
    frozen_no_ticks = 0

    print("t(s)   时刻  shouldTimePass paused  ticks     窗口在前台  停滞s   Δticks/s")
    while time.time() - start < seconds:
        t = time.time() - start
        try:
            h = c.health(timeout=5.0)
            o = c.observe("summary", timeout=8.0)
        except BridgeError as exc:
            print(f"{t:5.1f}  采样失败 {exc.status}")
            time.sleep(1.0)
            continue

        tod = (o.get("clock") or {}).get("timeOfDay")
        g = o.get("game") or {}
        ticks = ((h.get("runtime") or {}).get("ticks"))
        active = ((h.get("game") or {}).get("windowActive"))
        gap = (o.get("liveness") or {}).get("secondsSinceClockMoved")

        dt = 1.0 if prev_ticks is None else (t - last_change_t if False else 1.0)
        dps = "" if prev_ticks is None else f"{(ticks - prev_ticks):.0f}"
        mark = ""
        if prev_tod is not None and tod != prev_tod:
            delta_min = 0
            try:
                a, b = int(prev_tod), int(tod)
                delta_min = (b // 100) * 60 + b % 100 - ((a // 100) * 60 + a % 100)
            except Exception:
                pass
            mark = f"  ↑ +{delta_min} 分钟（停滞 {t - last_change_t:.1f}s）"
            jumps.append(f"t={t:.1f}s {prev_tod}→{tod} (+{delta_min} 分钟, 停滞 {t - last_change_t:.1f}s)")
            last_change_t = t
        elif prev_tod is not None:
            if prev_ticks is not None and ticks == prev_ticks:
                frozen_no_ticks += 1
            else:
                frozen_with_ticks += 1

        print(f"{t:5.1f}  {tod}  {str(g.get('shouldTimePass')):5}  {str(g.get('paused')):5}  "
              f"{ticks:<9}  {str(active):5}  {gap}{mark}")
        prev_tod, prev_ticks = tod, ticks
        time.sleep(1.0)

    print("\n== 汇总 ==")
    for j in jumps:
        print("  " + j)
    print(f"时钟不动的采样里：ticks 仍在涨 = {frozen_with_ticks} 次，ticks 原地不动 = {frozen_no_ticks} 次")
    print("判读：ticks 原地不动 => 游戏循环被停；ticks 在涨 => 循环在跑，问题在时间累积逻辑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
