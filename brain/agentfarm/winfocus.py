"""把《星露谷》窗口拉到前台（**可选兜底**；v0.5.0 起不再是任何技能的前置条件）。

【为什么曾经需要它 —— 2026-10-11 实机 A/B 实测结论（`tools/diag-focus-ab.py`）】
游戏窗口**不激活**（`health.game.windowActive=false`）时，**两件事同时坏掉**：
  * `PathFindController` **不驱动角色移动** —— 实测 10 次移动全部在 1.5 秒卡死
    检测后失败，角色坐标一动不动；
  * **世界时钟也不走** —— 三段时间对照：游戏前台 1020→1040（+2 拍）、
    把焦点给别的窗口 1040→1040（冻结 12 秒）、游戏回前台 1040→1100。
而同一时刻：`runtime.ticks` 仍以 ~62/s 增长、`shouldTimePass()` 恒为 true、
`paused` 恒为 false、角色是否在床上（全程 `isInBed=true`）**都不影响**。
⇒ **"时钟走不走"取决于窗口是否被激活**，与游戏循环、`shouldTimePass`、
   `paused`、角色是否在床上都无关。

（⚠️ 本文件早期版本写过"失焦时世界时间照常推进"—— 那是错的，已被上面的实验证伪：
  当时把"世界没推进"误归因成别的原因。同样被撤回的还有"躺在床上所以时间不走"。）

【⚠️ 2026-10-11 晚更新：根因已被 IL 定死并被 v0.5.0 消除】
`Game1._update` **IL_0444–IL_0480** 在"窗口不活跃 且 `Game1.options.pauseWhenOutOfFocus`
为 true"时直接 `ret`，跳过 `UpdateGameClock`(IL_12C3) 与 `UpdateLocations`(IL_12D1)
—— 这才是"时钟不走 + 角色不动"的**唯一一道门**（见 `docs/_il-oof-pause.md`）。
Mod v0.5.0 每帧把该选项扳回 false；真机验收（`tools/verify-no-pause.py`）：
**失焦 30 秒时钟照走 620→700、失焦下 `move_to` 位移 4 格 / 0.9 秒**。
⇒ **失焦不再是故障原因**，本模块因此降级为**可选兜底**（例如某个技能将来真的依赖
   "窗口在激活态"时才用），而不再是移动的前置条件。

`focus_window()` 只用 Windows 窗口 API（5 种策略 × 2 轮），**不合成任何键鼠事件** ——
合成输入会真的操作游戏（曾实测把体力从 270 打到 266，见 docs/01-架构设计.md §2 原则 7）。

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


def _wait_foreground(hwnd: int, timeout: float = 1.2) -> bool:
    """轮询等待窗口真的成为前台（SetForegroundWindow 是异步生效的）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if foreground_window() == hwnd:
            return True
        time.sleep(0.05)
    return foreground_window() == hwnd


def _attach_and_activate(hwnd: int) -> None:
    """把自己线程的输入队列挂到前台线程与目标线程上，再激活。"""
    fg = foreground_window()
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


def focus_window(hwnd: int, verbose: bool = False) -> bool:
    """把窗口拉到前台并激活。成功返回 True。

    【为什么要多套策略】2026-10-11 实测：单独用 `AttachThreadInput` 这一套会**时好时坏**
    —— 同一天里两次成功、一次失败（`SetForegroundWindow` 受 Windows 前台锁限制，
    后台进程不一定被允许抢焦点）。**v0.5.0 起焦点已不再是移动的前提**（见文件头），
    这里仍保留多策略是为了在"确实需要窗口处于激活态"的场合尽量可靠。

    所有策略都只改 Windows 窗口状态，不碰游戏状态，也不合成键鼠事件
    （架构 §2 原则 7：脑绝不伪造输入）。
    """
    if not hwnd:
        return False

    SW_RESTORE, SW_MINIMIZE, SW_SHOW = 9, 6, 5
    HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
    SWP_NOSIZE, SWP_NOMOVE = 0x0001, 0x0002

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    if _wait_foreground(hwnd, 0.05):
        return True

    def _minimize_restore():
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        time.sleep(0.12)
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)

    def _topmost_flip():
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE)
        time.sleep(0.05)
        user32.SetForegroundWindow(hwnd)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE)

    def _switch_to_this():
        user32.SwitchToThisWindow(hwnd, True)

    def _show_and_activate():
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetForegroundWindow(hwnd)

    strategies = (
        ("attach+activate", _attach_and_activate),
        ("minimize+restore", _minimize_restore),
        ("topmost flip", _topmost_flip),
        ("SwitchToThisWindow", _switch_to_this),
        ("ShowWindow+activate", _show_and_activate),
    )

    for attempt in range(2):                      # 整体再轮一遍，容忍瞬时失败
        for name, fn in strategies:
            try:
                fn(hwnd)
            except Exception:
                continue
            if _wait_foreground(hwnd, 0.6):
                if verbose:
                    print(f"      抢焦点成功（策略 {name}，第 {attempt + 1} 轮）")
                return True
    return _wait_foreground(hwnd, 0.2)


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
