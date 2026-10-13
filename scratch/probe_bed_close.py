r"""真机探针 #4：睡觉提问已经引出且 `Game1.newDay=True` 了，但 DialogueBox 还挂着
（探针 #3 诊断：`isInBed=True, Game1.newDay=True, pauseTime=600, activeMenu=DialogueBox,
dialogueUp=True, canMove=False, newDaySync.readyForSave?=True, hasSaved?=False`，180s 日期不走）。

假设：`Game1.NewDay()` 已经被触发（newDay=true），但**提问框没关** ⇒ 跨日流程走不下去。
（脑侧 `sleep` 走的是 `GameLocation.answerDialogue(Response)`，绕过了 `DialogueBox.receiveLeftClick`，
而游戏自己的收尾 —— `closeDialogue()` / `exitThisMenu()` —— 没被执行。）

本探针只做一件事：**用游戏自己的关框路径把提问框关掉**（`dismiss_modal`：先应答否〔对
`answerDialogueAction("Sleep_No")` 是静默 no-op〕再 `closeDialogue()`+`exitThisMenu()`），
然后轮询观测，看 `Game1.newDay` 之后的那天是否真的落下来。

判据（可观测即证据）：`clock.day` 前进 **且** 存档 size/mtime 前进。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

SAVE = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035" / "Wahaha_450799035"


def save_stat() -> tuple[int, float]:
    try:
        st = SAVE.stat()
        return st.st_size, st.st_mtime
    except OSError:
        return -1, -1.0


def fmt(st: tuple[int, float]) -> str:
    return f"{st[0]} B / mtime {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st[1]))}"


def brief(obs: dict) -> str:
    clk = obs.get("clock") or {}
    pl = obs.get("player") or {}
    ui = obs.get("ui") or {}
    return (
        f"day={[clk.get('year'), clk.get('season'), clk.get('day')]} tod={clk.get('timeOfDay')} "
        f"loc={pl.get('location')} tile={pl.get('tile')} stam={pl.get('stamina')} money={pl.get('money')} "
        f"question={ui.get('dialogueIsQuestion')} menu={str(ui.get('activeMenuText'))[:60]!r}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=float, default=90.0, help="关框后轮询等待跨日的秒数")
    args = ap.parse_args()

    c = BridgeClient(timeout=10.0)
    before_stat = save_stat()
    print("== 探针 #4：关掉睡觉提问框，看 newDay 是否落地 ==")
    print("存档（前）：", fmt(before_stat))
    obs = c.observe("full")
    print("关框前：", brief(obs))
    print("health.runtime：", json.dumps((c.health() or {}).get("runtime"), ensure_ascii=False)[:400])

    print("\n[1] dismiss_modal()（游戏自己的关框路径）")
    try:
        r = c.dismiss_modal(timeout_ms=8000)
        print("  回执：", json.dumps(r, ensure_ascii=False, default=str)[:600])
    except BridgeError as exc:
        print(f"  失败：{exc.status}: {str(exc)[:300]}")
    time.sleep(1.5)

    print(f"\n[2] 轮询观测最多 {args.wait:.0f}s（跨日时会长时间渐黑/存档）")
    t0 = time.time()
    last = None
    moved = False
    while time.time() - t0 < args.wait:
        try:
            obs = c.observe("full")
        except BridgeError as exc:
            print(f"  observe 失败（可能正在渐黑/重载）：{exc.status}")
            time.sleep(3.0)
            continue
        line = brief(obs)
        if line != last:
            print(f"  t+{time.time() - t0:5.1f}s  {line}")
            last = line
        b, a = (before_stat_clock.get("day")), (obs.get("clock") or {}).get("day")
        if a is not None and b is not None and a != b:
            moved = True
            print("  ✅ 日期前进")
            break
        time.sleep(2.0)

    after = c.observe("full")
    after_stat = save_stat()
    print("\n== 结果 ==")
    print("关框后：", brief(after))
    print("存档（后）：", fmt(after_stat))
    print("跨日（观测）：", "✅" if moved else "❌")
    print("存档前进：", "✅" if (after_stat[1] > before_stat[1] or after_stat[0] != before_stat[0]) else "❌")
    print("结论：", "VERIFIED —— newDay 落地 🎉" if moved else "needs_review")
    return 0 if moved else 1


before_stat_clock: dict = {}

if __name__ == "__main__":
    # 起手记下 day，供轮询比对
    _c = BridgeClient(timeout=10.0)
    before_stat_clock.update((_c.observe("full").get("clock") or {}))
    raise SystemExit(main())
