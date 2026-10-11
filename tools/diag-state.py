"""一行一条地打印"此刻到底发生了什么"：焦点 / 时钟 / 角色 / 模态 / tick。

用来把"世界时钟不走"这类现象**当场定因**，而不是事后猜。
每行同时给出：

  * `fg`  —— Windows 层面当前前台窗口的 hwnd（`user32.GetForegroundWindow`，真值）
  * `game`—— 游戏窗口 hwnd
  * `active` —— **游戏自己报告的** `Game1.game1.IsActive`（= `/v1/health` 的 `game.windowActive`）
  * `tod` / `stall` —— 世界时刻 / 距上次时钟推进过了多少秒
  * `ticks` —— 游戏 Update tick 计数（判断循环是否在跑）
  * `canMove` / `inBed` / `modal` —— 角色是否能动 / 是否在床上 / 是否有模态

`fg` 与 `active` 同时看，才能区分两种完全不同的情况：
  ① `fg != game` 且 `active=false` —— 常规失焦（已知：时钟不走、寻路不驱动）；
  ② `fg == game` 但 `active=false` **或** `active=true` 而时钟仍不走 —— 是我们还没定因的状态，
     必须当场记录下来（别再写成"已知原因"）。

用法：
    python tools\\diag-state.py            # 默认 8 次，间隔 3 秒
    python tools\\diag-state.py 5 2        # 5 次，间隔 2 秒
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

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    gap = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0

    game = wf.find_game_window()
    print(f"游戏窗口 hwnd={game}")
    c = BridgeClient()
    last_tod: int | None = None

    for i in range(n):
        fg = wf.foreground_window()
        try:
            h = c.health(timeout=5.0)
            o = c.observe("summary", timeout=8.0)
        except BridgeError as exc:
            print(f"[{i}] {exc}")
            time.sleep(gap)
            continue
        tod = (o.get("clock") or {}).get("timeOfDay")
        advance = "" if last_tod is None or tod == last_tod else f"  (+{(tod - last_tod) % 2400} 分钟)"
        last_tod = tod
        print(
            f"[{i}] fg={fg}{'（=游戏）' if fg == game else ''} "
            f"active={str((h.get('game') or {}).get('windowActive')):5s} "
            f"tod={tod}{advance:16s} stall={(o.get('liveness') or {}).get('secondsSinceClockMoved')}s "
            f"ticks={(h.get('runtime') or {}).get('ticks')} "
            f"canMove={(o.get('player') or {}).get('canMove')} "
            f"inBed={(o.get('player') or {}).get('isInBed')} "
            f"modal={(o.get('ui') or {}).get('isModal')} "
            f"worldAdvancing={(o.get('liveness') or {}).get('worldAdvancing')}"
        )
        time.sleep(gap)
    return 0


if __name__ == "__main__":
    sys.exit(main())
