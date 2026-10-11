"""诊断：时钟不走到底是谁的锅？（焦点 × shouldTimePass × 时钟）

背景：我们发现 `shouldTimePass=False` 时时钟确实不动，但那 12 秒里
`paused=False`、`canMove=True`、`isInBed=False` —— 所以"躺在床上所以时间不走"
这个解释站不住（用户实测：开局人就在床上，时间照样走）。

本脚本做**受控对照实验**：同一个角色、同一地点，只切换窗口焦点，观察
`health.game.windowActive` / `game.shouldTimePass` / `clock.timeOfDay` 三者的关系。

只读游戏状态 + 只动 Windows 窗口焦点（不合成键鼠事件），符合架构 §2 原则 7。
"""
from __future__ import annotations

import json
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


def sample(c: BridgeClient, game: int) -> dict:
    row: dict = {}
    try:
        row["windowActive"] = (c.health(timeout=5.0).get("game") or {}).get("windowActive")
    except BridgeError as exc:
        row["windowActive"] = f"err:{exc.status}"
    try:
        o = c.observe("summary", timeout=8.0)
    except BridgeError as exc:
        row["observe"] = f"err:{exc.status}"
        return row
    row["timeOfDay"] = (o.get("clock") or {}).get("timeOfDay")
    row["shouldTimePass"] = (o.get("game") or {}).get("shouldTimePass")
    row["paused"] = (o.get("game") or {}).get("paused")
    row["canMove"] = (o.get("player") or {}).get("canMove")
    row["isInBed"] = (o.get("player") or {}).get("isInBed")
    row["worldSeq"] = o.get("worldSeq")
    row["fgIsGame"] = wf.foreground_window() == game
    return row


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
    print(f"游戏 hwnd={game}  当前前台 hwnd={original_fg}")

    cands = other_windows(game)
    print("可作对照的窗口：")
    for hwnd, title in cands[:8]:
        print(f"  hwnd={hwnd}  title={title[:60]!r}")

    def pick() -> int | None:
        for want in ("deepseek", "chrome", "edge", "explorer"):
            for hwnd, title in cands:
                if want in title.lower():
                    return hwnd
        return cands[0][0] if cands else None

    other = pick()
    print(f"对照组窗口 hwnd={other}")

    c = BridgeClient()

    def phase(name: str, target: int | None, n: int) -> None:
        print(f"\n--- {name} ---")
        if target is not None:
            ok = wf.focus_window(target)
            print(f"    抢焦点({'游戏' if target == game else '对照窗口'}) -> {'成功' if ok else '失败'}")
        for i in range(n):
            row = sample(c, game)
            print("    " + json.dumps(row, ensure_ascii=False))
            time.sleep(2.0)

    phase("阶段 1：游戏在前台", game, 4)
    if other is not None:
        phase("阶段 2：把焦点给别的窗口（游戏失焦）", other, 4)
    phase("阶段 3：把游戏拉回前台", game, 3)

    if original_fg and original_fg != wf.foreground_window():
        wf.focus_window(original_fg)
        print(f"\n已把焦点还给原前台 hwnd={original_fg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
