"""v0.5.0 失焦验收：**窗口不在前台时，世界是否照常推进、角色是否照常能走**。

背景（`docs/00-开发日志.md` 条目 015）：
  * 实测（2026-10-11 A/B）：游戏窗口失焦时，世界时钟与 `PathFindController` **都不工作**；
    但游戏循环照跑、`shouldTimePass()` 仍返回 true、`paused` 仍 false —— 看起来在跑，其实全停。
  * IL 定因（`docs/_il-oof-pause.md`）：`Game1._update` IL_0444–IL_0480 在
    "窗口不活跃 且 `Game1.options.pauseWhenOutOfFocus == true`" 时直接 `ret`，跳过
    `UpdateGameClock`(IL_12C3) 与 `UpdateLocations`(IL_12D1 → `PathFindController.update`)。
    ⇒ 时钟不走与角色不动是**同一道门**。
  * v0.5.0 的修法：Mod 每帧（`OnUpdateTicked` 第一行）把该选项扳回 false，并把它被扳回的
    次数记在 `game.oofFixCount` 里当证据。

本脚本**全程不抢焦点**（与 `tools/diag-move-focus.py` 的 A/B 相反），就是要把"失焦"作为
被测条件。三条判据：
  A 证据字段：`game.pauseWhenOutOfFocus == false` 且 Mod ≥ 0.5.0（`oofFixCount` 为旁证）；
  B 失焦时钟：把焦点挪到**别的窗口**后，N 秒内 `clock.timeOfDay` 至少推进 20 分钟；
  C 失焦移动：焦点仍在别的窗口时直接 `move_to`，位移必须 > 0。
三条全过 ⇒ "游戏窗口必须保持前台"这条部署硬约束可以移除。

运行期间**不要碰键盘鼠标**（尤其别点游戏窗口，会把焦点抢回去、污染 B/C 判据）。

用法：
    python tools\\verify-no-pause.py              # 失焦采样 30 秒
    python tools\\verify-no-pause.py 60           # 采样 60 秒
    python tools\\verify-no-pause.py 30 6,8 8,9   # 再指定失焦移动的目标格
"""
from __future__ import annotations

import ctypes
import sys
import time

from agentfarm import winfocus as wf
from agentfarm.bridge import BridgeClient, BridgeError

_user32 = ctypes.windll.user32
DEFAULT_TILES = [(6, 8), (8, 9)]


def find_other_window(exclude: int | None) -> int | None:
    """找一个"不是游戏"的可见顶层窗口，用来把焦点挪走。

    纯粹是给 A/B 实验用的，不属于业务代码；因此不往 `brain/agentfarm/winfocus.py` 里加 API。
    """
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _lparam):
        if hwnd == exclude or not _user32.IsWindowVisible(hwnd):
            return True
        if _user32.GetWindow(hwnd, 4):        # GW_OWNER=4：跳过工具窗口
            return True
        if _user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        found.append(hwnd)
        return False                          # 找到第一个就停

    _user32.EnumWindows(_cb, None)
    return found[0] if found else None


def sample(c: BridgeClient) -> dict:
    h = c.health(timeout=5.0)
    o = c.observe("summary", timeout=8.0)
    g = h.get("game") or {}
    return {
        "active": g.get("windowActive"),
        "oof": g.get("pauseWhenOutOfFocus"),
        "fixes": g.get("oofFixCount"),
        "tod": (o.get("clock") or {}).get("timeOfDay"),
        "stall": (o.get("liveness") or {}).get("secondsSinceClockMoved"),
        "tile": tuple((o.get("player") or {}).get("tile") or ()),
    }


def to_minutes(tod) -> int | None:
    """游戏时刻格式 630 / 1230 -> 从 0:00 起的分辨率更细的分钟数（用于算差值）。"""
    if not isinstance(tod, int):
        return None
    return (tod // 100) * 60 + (tod % 100)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    seconds = 30
    tiles = list(DEFAULT_TILES)
    args = sys.argv[1:]
    if args:
        try:
            seconds = int(args[0])
        except ValueError:
            tiles = []
            args = sys.argv[1:]
        for raw in args[1:]:
            x, y = raw.split(",")
            tiles.append((int(x), int(y)))
    if not tiles:
        tiles = list(DEFAULT_TILES)

    c = BridgeClient()
    original_fg = wf.foreground_window()
    game = wf.find_game_window()

    h = c.health(timeout=5.0)
    g = h.get("game") or {}
    print(f"Mod {h.get('modVersion')} | 游戏 {g.get('version')} | SMAPI {g.get('smapi')} "
          f"| 端口 {(h.get('server') or {}).get('port')}")
    print(f"游戏窗口 hwnd={game}  当前前台 hwnd={original_fg}")

    s0 = sample(c)
    print(f"\n===== 判据 A：证据字段 =====")
    print(f"  game.pauseWhenOutOfFocus = {s0['oof']}（期望 False）")
    print(f"  game.oofFixCount         = {s0['fixes']}（每帧兜底扳回该选项的次数，>0 即「被改回过」）")
    print(f"  game.windowActive        = {s0['active']}  tod={s0['tod']}  玩家格={s0['tile']}")
    a_ok = s0["oof"] is False and str(h.get("modVersion", "")).startswith("0.5")
    if s0["oof"] is None:
        print("  ✘ health 里没有 pauseWhenOutOfFocus —— 游戏里装的还是旧版 Mod（需重启游戏换 dll）")
    print(f"  {'✔ 判据 A 通过' if a_ok else '✘ 判据 A 未通过'}")

    other = find_other_window(game)
    if other is None:
        print("\n找不到可用的「别的窗口」来做失焦对照；请先把焦点切到浏览器/终端再运行本脚本。")
        return 1
    print(f"\n把焦点挪到非游戏窗口 hwnd={other}（本脚本全程不抢焦点）…")
    wf.focus_window(other)
    time.sleep(1.5)

    s = sample(c)
    if s["active"] is not False:
        print(f"  ⚠️ 焦点没挪走（game.windowActive={s['active']}）——B/C 判据不可信。"
              f"请确认没有别的程序在抢焦点。")

    print(f"\n===== 判据 B：失焦 {seconds} 秒内世界时钟是否推进 =====")
    print(f"  {'时刻':>9} {'active':>7} {'oof':>7} {'oofFix':>7} {'tod':>6} {'停滞':>7}  玩家格")
    first = sample(c)
    rows = [first]
    print(f"  {time.strftime('%H:%M:%S'):>9} {str(first['active']):>7} {str(first['oof']):>7} "
          f"{str(first['fixes']):>7} {str(first['tod']):>6} {str(first['stall']):>7}  {first['tile']}")
    t_end = time.monotonic() + seconds
    while time.monotonic() < t_end:
        time.sleep(2.0)
        r = sample(c)
        rows.append(r)
        print(f"  {time.strftime('%H:%M:%S'):>9} {str(r['active']):>7} {str(r['oof']):>7} "
              f"{str(r['fixes']):>7} {str(r['tod']):>6} {str(r['stall']):>7}  {r['tile']}")
    last = rows[-1]
    m0, m1 = to_minutes(first["tod"]), to_minutes(last["tod"])
    gained = (m1 - m0) if (m0 is not None and m1 is not None) else None
    all_unfocused = all(r["active"] is False for r in rows)
    b_ok = bool(gained is not None and gained >= 20 and all_unfocused)
    print(f"  失焦期间采样 {len(rows)} 次，windowActive 全程 False：{all_unfocused}")
    print(f"  时钟 {first['tod']} → {last['tod']}（+{gained} 分钟，要求 ≥ 20）")
    print(f"  {'✔ 判据 B 通过' if b_ok else '✘ 判据 B 未通过：失焦时世界仍然停摆'}")

    print(f"\n===== 判据 C：失焦状态下能否移动 =====")
    c_ok = False
    for (x, y) in tiles:
        before = sample(c)
        t0 = time.monotonic()
        try:
            res = c.move_to(x, y, timeout_ms=3000)
            status, reason = str(res.get("status")), str(res.get("reason") or "")
        except BridgeError as exc:
            status, reason = str(exc.status), str(exc.reason or "")
        dt = time.monotonic() - t0
        after = sample(c)
        moved = abs(after["tile"][0] - before["tile"][0]) + abs(after["tile"][1] - before["tile"][1]) \
            if (before["tile"] and after["tile"]) else 0
        print(f"  →({x},{y}) {status:18s} 位移={moved}格 ({before['tile']}→{after['tile']})  "
              f"active {before['active']}→{after['active']}  {dt:.1f}s  {reason[:60]!r}")
        if moved > 0:
            c_ok = True
    print(f"  {'✔ 判据 C 通过' if c_ok else '✘ 判据 C 未通过：失焦时角色仍然不能动'}")

    print(f"\n===== 结论 =====")
    if a_ok and b_ok and c_ok:
        print("  ✔ 三条全过：失焦不再是停摆原因 ⇒ **「游戏窗口必须保持前台」这条部署硬约束可以移除**。")
        print("    （`brain/agentfarm/winfocus.py` 的抢焦点仍可作为兜底保留，但不再是必需前置。）")
    else:
        print(f"  ✘ A={a_ok} B={b_ok} C={c_ok} —— 有判据未过，先看上面每行原始数据，别急着改代码。")

    if original_fg and original_fg != wf.foreground_window():
        wf.focus_window(original_fg)
        print(f"\n已把焦点还给原前台 hwnd={original_fg}")
    return 0 if (a_ok and b_ok and c_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
