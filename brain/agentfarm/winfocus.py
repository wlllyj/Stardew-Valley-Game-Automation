"""把《星露谷》窗口拉到前台（无人值守的必需能力）。

【为什么需要它 —— 2026-10-11 实机实测结论】
游戏窗口**失焦**时：
  * 世界时间照常推进（我们已把 `pauseWhenOutOfFocus` 关掉）；
  * 但 `PathFindController` **不会真正驱动角色移动** —— 实测 10 次移动全部
    在 1.5 秒卡死检测后失败，角色坐标一动不动；
  * 一旦窗口回到前台，同样的移动 5/5 成功（每次约 216ms）。
=> 结论：**执行动作前必须确保游戏窗口是前台窗口。**

这只动 Windows 的窗口焦点，不碰任何游戏状态 —— 与决策 D4
（"全程只做合法游戏操作，不做瞬移/改状态"）不冲突。

纯标准库（ctypes），零依赖。
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# 常见窗口标题（SMAPI 启动的窗口标题就是游戏标题）
TITLE_HINTS = ("stardew valley",)

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def find_game_window(title_hints: tuple[str, ...] = TITLE_HINTS) -> int | None:
    """按标题找游戏主窗口。返回 HWND 或 None。"""
    found: list[int] = []

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        if not title:
            return True
        low = title.lower()
        if any(h in low for h in title_hints):
            # 排除工具窗口（无标题栏的辅助窗口通常没有 WS_CAPTION）
            style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
            if style & 0x00C00000:  # WS_CAPTION
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    return found[0] if found else None


def foreground_window() -> int:
    return int(user32.GetForegroundWindow())


def focus_window(hwnd: int) -> bool:
    """把窗口拉到前台并尝试激活。

    Windows 会阻止后台进程随意抢焦点，所以这里用三步组合：
      1) 若最小化先还原；
      2) 把自己线程的输入队列挂到前台窗口线程上（AttachThreadInput），
         这是绕开前台锁最常用的合法做法；
      3) SetForegroundWindow。
    """
    if not hwnd:
        return False
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    fg = foreground_window()
    if fg == hwnd:
        return True

    cur_thread = kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    tgt_thread = user32.GetWindowThreadProcessId(hwnd, None)

    attached_fg = attached_tgt = False
    try:
        if fg_thread and fg_thread != cur_thread:
            attached_fg = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))
        if tgt_thread and tgt_thread != cur_thread:
            attached_tgt = bool(user32.AttachThreadInput(cur_thread, tgt_thread, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached_tgt:
            user32.AttachThreadInput(cur_thread, tgt_thread, False)
        if attached_fg:
            user32.AttachThreadInput(cur_thread, fg_thread, False)

    time.sleep(0.15)
    return foreground_window() == hwnd


def ensure_game_foreground(verbose: bool = True) -> bool:
    """确保游戏在前台；成功返回 True。找不到窗口或抢焦点失败返回 False。"""
    hwnd = find_game_window()
    if hwnd is None:
        if verbose:
            print("找不到《星露谷》窗口（游戏没启动？窗口标题不含 'Stardew Valley'？）")
        return False
    if foreground_window() == hwnd:
        if verbose:
            print(f"游戏已在前后台（hwnd={hwnd}）")
        return True
    ok = focus_window(hwnd)
    if verbose:
        print(f"{'已把游戏拉到前台' if ok else '抢焦点失败'}（hwnd={hwnd}）")
    return ok


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    hwnd = find_game_window()
    if hwnd is None:
        print("未找到游戏窗口")
        return 1
    print(f"游戏窗口 hwnd={hwnd}  标题={_window_title(hwnd)!r}")
    print(f"当前前台 hwnd={foreground_window()}")
    ok = ensure_game_foreground()
    print(f"结果：{'成功' if ok else '失败'}  前台 hwnd={foreground_window()}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
