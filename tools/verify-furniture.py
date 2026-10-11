"""家具修复的真机验收：**哪些格能走、哪些格被拒、理由是什么**。

背景（`docs/00-开发日志.md` 条目 013/015）：v0.3.0 用"家具像素包围盒 ∩ 目标格"自己猜阻挡，
把 FarmHouse 里 13 格判成"有家具"（**含玩家出生点 (9,9)**），而 `(7,9)` 在 v0.2.0 明明
`OK 350ms` 走上去过。v0.4.0 改成**问游戏**：只有 `!Furniture.isPassable()` 才算阻挡；
**床（BedFurniture）无条件阻挡**（可踩，但会触发睡觉确认框冻结世界）。

本脚本做三件事：
  1. 打印契约证据：`detail=full` 必须有 `location.furniture[]`，`detail=summary` 必须**没有**；
  2. 把逐格判定结果打出来（OK / 被拒 + 原始 reason），用于和日志里的旧结论**逐格对照**；
  3. 结束时把前台窗口还给原来的窗口（不把焦点留在游戏上）。

注意：**v0.5.0 起移动不再需要游戏窗口在前台**（失焦停摆已被每帧兜底消除，证据见
`docs/00-开发日志.md` 条目 015 与 `tools/verify-no-pause.py`）。脚本这里**习惯性**仍会
先抢一次焦点，只是为了让结果与历史记录可比、并非必要条件；运行期间请不要在游戏窗口里
打字（键盘会落到游戏里）。

用法：
    python tools\\verify-furniture.py                 # 默认测试 7 个关键格
    python tools\\verify-furniture.py 4,8 5,8 6,8     # 指定格子
"""
from __future__ import annotations

import sys

from agentfarm import winfocus as wf
from agentfarm.bridge import BridgeClient, BridgeError

# 关键格：来自日志条目 013 的旧扫描（x=4..11 / y=6..11）
DEFAULT_TILES = [
    (7, 9),    # v0.3.0 被误判"有家具"，但 v0.2.0 实测 OK 350ms —— 必须恢复可走
    (9, 9),    # 玩家出生点，v0.3.0 被判"有家具"（荒谬）—— 不能再报"有家具"
    (10, 9),   # 床 —— **必须仍被拒**（放行就会触发睡觉弹窗）
    (6, 9), (8, 9), (5, 8), (6, 8),   # 旧扫描里被误判/超时的格
]


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
    c = BridgeClient()

    h = c.health(timeout=5.0)
    print(f"Mod {h.get('modVersion')} | 游戏 {(h.get('game') or {}).get('version')} "
          f"| SMAPI {(h.get('game') or {}).get('smapi')} | 端口 {h.get('server', {}).get('port')}")

    # ---- 1) 契约证据：full 有家具清单，summary 没有 ----
    full = c.observe("full", timeout=10.0)
    summary = c.observe("summary", timeout=8.0)
    print(f"schema full={full.get('schema')}  summary={summary.get('schema')}")
    loc_full = full.get("location") or {}
    loc_sum = summary.get("location") or {}
    print(f"location.furniture 在 full 里：{'furniture' in loc_full}"
          f"（{len(loc_full.get('furniture') or [])} 件）"
          f" / 在 summary 里：{'furniture' in loc_sum}"
          f"   player=({(full.get('player') or {}).get('tile')})")

    print("\n家具清单（full）：")
    for f in (loc_full.get("furniture") or []):
        print(f"    tile={f.get('tile')} bbox={f.get('bbox')} passable={f.get('passable')} "
              f"ground={f.get('ground')} isBed={f.get('isBed')} "
              f"**blocking={f.get('blocking')}** type={f.get('type')} name={f.get('name')!r}")

    # ---- 2) 逐格移动判定 ----
    if not wf.focus_window(wf.find_game_window()):
        print("\n⚠️ 抢焦点失败 —— 移动结果不可信（失焦时 PathFindController 不驱动角色）")
    else:
        print("\n逐格判定（timeout 2000ms；`timeout` 表示「远」，不代表「不通」）：")
        for (x, y) in tiles:
            try:
                res = c.move_to(x, y, timeout_ms=2000)
                print(f"    ({x},{y}) -> OK {res.get('elapsedMs')}ms  "
                      f"reason={res.get('reason')!r}  "
                      f"tileAfter={(res.get('playerAfter') or {}).get('tile') if isinstance(res.get('playerAfter'), dict) else res.get('playerTile')}")
            except BridgeError as exc:
                print(f"    ({x},{y}) -> {exc.status}  reason={exc.reason!r}")

    if original_fg and original_fg != wf.foreground_window():
        wf.focus_window(original_fg)
        print(f"\n已把焦点还给原前台 hwnd={original_fg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
