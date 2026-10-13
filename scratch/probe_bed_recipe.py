r"""真机探针 #5：把"跨日"固化成**可重复配方**并连跑验证。

## 今天定下的机制（真机 + IL 双向对上）
1. 睡觉提问**不是** `interact`/`checkAction` 弹的（`GameLocation.checkAction` 只查 `Action`，不查 `TouchAction`）。
   它由 map 的 `TouchAction="Sleep"` 在**玩家移动着踩到触发格**时评估：
   `GameLocation.UpdateWhenCurrentLocation → performTouchAction("Sleep", ...)`
   （`scratch\il-bed-5.txt:1283-1303`）：前置 `!Game1.newDay && shouldTimePass(false) && player.hasMoved && !player.passedOut`。
2. 触发格 = `(bed.X + bedTileOffset, bed.Y + 1)`，`bedTileOffset ∈ {0,1}` 逐帧翻转
   （`scratch\il-bed-6.txt` / `il-bed-1.txt:1028-1133`）⇒ FarmHouse 床 (9,8) 的触发格是 **(9,9)/(10,9)**。
   真机实测：`(9,8)/(9,10)/(10,8)` A* unreachable，**(10,9) 踩上去弹出 `Go to sleep for the night?`（Yes/No）**。
3. `sleep` 技能（`AnswerWith("Yes")`）⇒ `answerDialogueAction("Sleep_Yes")` → `startSleep` → `doSleep`
   → **`Game1.NewDay(0f)`（`newDay=true`）** —— 真机诊断证实（`Game1.newDay=True`）。
4. **卡点**：`answerDialogue` 只跑回调、**不关提问框** ⇒ `activeMenu=DialogueBox` 一直挂着，
   180s 内日期不走。真机实测：**关掉框（游戏自己的 `closeDialogue()`+`exitThisMenu()`）⇒ 当天立刻落地**
   （spring 11 → spring 12，`SaveGameMenu` 出现，存档 mtime/size 双前进）。

## 本探针
在**已经跨过一次日**的世界里（spring 12 06:00、人回床上 (9,9)）把 1→4 连跑一遍，验证配方**可重复**：
  走去床外 → 踩触发格 → 观测到提问 → `sleep` 应答 → 关框 → 轮询 `day` 前进 + 存档 mtime/size 前进。

用法：
  python scratch\probe_bed_recipe.py
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
HINTS = [(10, 9), (9, 9)]  # 触发格候选（bedTileOffset=1 / 0）


def stat() -> tuple[int, float]:
    try:
        st = SAVE.stat()
        return st.st_size, st.st_mtime
    except OSError:
        return -1, -1.0


def fmt(s: tuple[int, float]) -> str:
    return f"{s[0]} B / mtime {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s[1]))}"


def day_of(obs: dict) -> tuple:
    c = obs.get("clock") or {}
    return (c.get("year"), c.get("season"), c.get("day"))


def brief(obs: dict) -> str:
    clk = obs.get("clock") or {}
    pl = obs.get("player") or {}
    ui = obs.get("ui") or {}
    return (
        f"day={list(day_of(obs))} tod={clk.get('timeOfDay')} tile={pl.get('tile')} "
        f"stam={pl.get('stamina')} money={pl.get('money')} q={ui.get('dialogueIsQuestion')} "
        f"menu={str(ui.get('activeMenuText'))[:48]!r}"
    )


def question_open(obs: dict) -> bool:
    ui = obs.get("ui") or {}
    return bool(ui.get("dialogueIsQuestion")) and bool(ui.get("dialogueResponses"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=float, default=90.0)
    args = ap.parse_args()

    c = BridgeClient(timeout=10.0)
    s0 = stat()
    obs = c.observe("full")
    d0 = day_of(obs)
    print("== 探针 #5：跨日配方连跑 ==")
    print("起手：", brief(obs))
    print("存档（前）：", fmt(s0))
    if not (obs.get("player") or {}).get("location") == "FarmHouse":
        print(f"❌ 现在不在 FarmHouse（在 {(obs.get('player') or {}).get('location')}），本探针需要站在床边")
        return 2

    # 1) 走开一步（满足 hasMoved，并离开床）
    pt = (obs.get("player") or {}).get("tile") or [9, 9]
    off = [pt[0] - 1, pt[1]]
    print(f"\n[1] 走去床外 {off}（置 hasMoved、离开床格）")
    try:
        c.move_to(off[0], off[1], timeout_ms=15000)
    except BridgeError as exc:
        print(f"  → {exc.status}: {str(exc)[:160]}")
    time.sleep(0.6)
    print("  现在：", brief(c.observe("full")))

    # 2) 踩触发格
    opened = False
    for cell in HINTS:
        print(f"\n[2] 踩触发格 {cell}（allow_bed=True）")
        try:
            r = c.move_to(cell[0], cell[1], allow_bed=True, timeout_ms=15000)
            print("  move_to ok：", str(r.get("reason"))[:150])
        except BridgeError as exc:
            print(f"  move_to 回：{exc.status}: {str(exc)[:150]}")
        time.sleep(0.8)
        obs = c.observe("full")
        print("   →", brief(obs))
        if question_open(obs):
            opened = True
            print(f"  ✅ 提问已弹出（{cell}）")
            break

    if not opened:
        print("\n❌ 没引出提问")
        return 1

    # 3) sleep 应答（短预算即可：它只负责回答 Yes，跨日在关框后才落地）
    print("\n[3] sleep 技能：应答 Yes（预期 15s 内 timeout，但 Game1.newDay 已置位）")
    try:
        r = c.sleep(timeout_ms=15000)
        print("  回执：", json.dumps(r, ensure_ascii=False, default=str)[:400])
    except BridgeError as exc:
        print(f"  → {exc.status}: {str(exc)[:300]}")
    mid = c.observe("full")
    print("  此刻：", brief(mid))

    # 4) 关掉提问框（游戏自己的关框路径）——这一步才是让 newDay 落地的关键
    if question_open(mid) or (mid.get("ui") or {}).get("activeMenuText"):
        print("\n[4] dismiss_modal()：关掉挂着的提问框")
        try:
            r = c.dismiss_modal(timeout_ms=8000)
            print("  回执：", json.dumps(r, ensure_ascii=False, default=str)[:500])
        except BridgeError as exc:
            print(f"  → {exc.status}: {str(exc)[:200]}")
    else:
        print("\n[4] 提问框已经不在（可能 Mod 侧已自行关闭），直接等跨日")

    # 5) 轮询
    print(f"\n[5] 轮询观测最多 {args.wait:.0f}s")
    t0 = time.time()
    moved = False
    last = None
    while time.time() - t0 < args.wait:
        try:
            obs = c.observe("full")
        except BridgeError as exc:
            print(f"  t+{time.time() - t0:5.1f}s observe 中断（渐黑/重载？）：{exc.status}")
            time.sleep(3.0)
            continue
        line = brief(obs)
        if line != last:
            print(f"  t+{time.time() - t0:5.1f}s  {line}")
            last = line
        if day_of(obs) != d0:
            moved = True
            break
        time.sleep(2.0)

    time.sleep(2.0)
    fin = c.observe("full")
    s1 = stat()
    print("\n== 结果 ==")
    print("结束后：", brief(fin))
    print("存档（后）：", fmt(s1))
    day_ok = day_of(fin) != d0
    save_ok = s1[1] > s0[1] or s1[0] != s0[0]
    print(f"跨日：{'✅' if day_ok else '❌'}（{list(d0)} → {list(day_of(fin))}）   存档前进：{'✅' if save_ok else '❌'}")
    print("结论：", "VERIFIED —— 跨日配方可重复 🎉" if (day_ok and save_ok) else "needs_review")
    return 0 if (day_ok and save_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
