"""A/B 对照实验：**只有把游戏窗口"激活"，世界时钟才走**。

用户实测提示：他在游戏窗口里点了一下，时间立刻开始走。本脚本把"点击"换成
**纯窗口 API 的激活**（`winfocus.focus_window`，5 种策略、不合成任何键鼠事件），
在同一个角色、同一地点、同一存档上做三段对照：

  阶段 1  反复确保"游戏在前台"          → 预期：时刻推进（~每 7s +10 分钟）
  阶段 2  反复确保"别的窗口在前台"      → 预期：时刻冻结（ticks 仍在涨）
  阶段 3  反复确保"游戏在前台"          → 预期：时刻恢复推进

每段里每 2 秒采样一次：`health.game.windowActive` / `health.runtime.ticks`（循环是否在跑）
/ `clock.timeOfDay` / `game.shouldTimePass`。这样能同时排除三个"看起来很像"的解释：
  * "时钟停下是因为游戏循环停了"      → 看 ticks 是否仍以 ~60/s 增长
  * "时钟停下是因为 shouldTimePass=false" → 看该字段
  * "时钟停下是因为角色在床上"        → 全程不动角色，isInBed 保持不变
"""
from __future__ import annotations

import sys
import time

from agentfarm import winfocus as wf
from agentfarm.bridge import BridgeClient, BridgeError

user32 = wf.user32


def other_windows(exclude: int) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or hwnd == exclude:
            return True
        title = wf._window_title(hwnd)
        if title:
            out.append((int(hwnd), title))
        return True

    user32.EnumWindows(wf.EnumWindowsProc(cb), 0)
    return out


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    original_fg = wf.foreground_window()
    game = wf.find_game_window()
    if game is None:
        print("找不到游戏窗口")
        return 1

    cands = other_windows(game)
    other = None
    for want in ("deepseek harness", "deepseek", "edge", "chrome", "explorer"):
        for hwnd, title in cands:
            if want in title.lower():
                other = hwnd
                break
        if other:
            break
    if other is None and cands:
        other = cands[0][0]
    print(f"游戏 hwnd={game}   对照窗口 hwnd={other}   原前台 hwnd={original_fg}")

    c = BridgeClient()

    def sample() -> dict:
        row: dict = {}
        try:
            h = c.health(timeout=5.0)
            row["ticks"] = (h.get("runtime") or {}).get("ticks")
            row["windowActive"] = (h.get("game") or {}).get("windowActive")
        except BridgeError as exc:
            row["err"] = f"health:{exc.status}"
        try:
            o = c.observe("summary", timeout=8.0)
            row["timeOfDay"] = (o.get("clock") or {}).get("timeOfDay")
            row["shouldTimePass"] = (o.get("game") or {}).get("shouldTimePass")
            row["paused"] = (o.get("game") or {}).get("paused")
            row["isInBed"] = (o.get("player") or {}).get("isInBed")
        except BridgeError as exc:
            row["err2"] = f"observe:{exc.status}"
        return row

    def phase(name: str, target: int | None, n: int, gap: float = 2.0) -> list[dict]:
        print(f"\n--- {name} ---")
        rows: list[dict] = []
        for i in range(n):
            if target is not None:
                ok = wf.focus_window(target)
                if not ok:
                    print("    (抢焦点失败)")
            time.sleep(0.4)
            row = sample()
            rows.append(row)
            print(f"    [{i}] {row}")
            time.sleep(gap)
        t0, t1 = rows[0].get("ticks"), rows[-1].get("ticks")
        print(f"    小结：ticks {t0}→{t1}（{'循环在跑' if isinstance(t0, int) and isinstance(t1, int) and t1 > t0 else '循环没跑'}）"
              f"  时刻 {rows[0].get('timeOfDay')}→{rows[-1].get('timeOfDay')}")
        return rows

    r1 = phase("阶段 1：游戏在前台（每采样前重新确保）", game, 5, 2.0)
    if other is not None:
        r2 = phase("阶段 2：把焦点给别的窗口（每采样前重新确保）", other, 5, 2.0)
    r3 = phase("阶段 3：游戏回到前台（每采样前重新确保）", game, 5, 2.0)

    print("\n== 判读 ==")
    print("窗口在前台时时刻推进 / 失焦时冻结，且两条里 ticks 都在涨、shouldTimePass 都为 true，")
    print("即可判定：**时钟走不走取决于窗口是否被激活**，与游戏循环、shouldTimePass、角色是否在床上都无关。")

    if original_fg and original_fg != wf.foreground_window():
        wf.focus_window(original_fg)
        print(f"已把焦点还给原前台 hwnd={original_fg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
