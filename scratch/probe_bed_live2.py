"""真机探针 #2：睡觉提问是不是"踩上床格"（touch action）触发的？

探针 #1（`scratch\probe_bed_live.py`）结论：对床占位的 6 格逐个 `interact`（= 游戏 `checkAction`）
全部返回 **False**、且 `lastQuestionKey=None` ⇒ **睡觉提问不是 checkAction 弹的**。

IL 证据（`scratch\il-bed-5.txt:1283-1300`，`GameLocation.performTouchAction` 的 `"Sleep"` 分支）：
    IL_0FCB: ldsfld Game1.newDay            ; newDay ⇒ 跳过
    IL_0FD2: shouldTimePass(false)          ; 时间不走 ⇒ 跳过
    IL_0FDA: player.hasMoved                ; **没移动过 ⇒ 跳过**
    IL_0FE6: player.passedOut               ; pass-out ⇒ 跳过
    IL_0FF2: LoadString("Strings\\Locations:FarmHouse_Bed_GoToSleep")
⇒ 睡觉由 **map 的 touch action** 触发（`GameLocation.UpdateWhenCurrentLocation → performTouchAction`），
   也就是"玩家**移动着踩到**那格"才会评估；`checkAction` 与它无关。

本探针：先保证 `hasMoved=true`（走开一步），再逐格试着**踩上去**，每步看
`ui.dialogueIsQuestion` / `lastQuestionKey` 是否变成睡觉提问。命中后可选 `--sleep` 真跨日。

用法：
  python scratch\probe_bed_live2.py
  python scratch\probe_bed_live2.py --sleep
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


def save_stat() -> str:
    try:
        st = SAVE.stat()
        return f"{st.st_size} B / mtime {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}"
    except OSError as exc:  # noqa: BLE001
        return f"<读不到：{exc}>"


def quest(obs: dict) -> tuple[bool, bool, str | None, list]:
    ui = obs.get("ui") or {}
    loc = obs.get("location") or {}
    return (bool(ui.get("dialogueIsQuestion")), bool((obs.get("player") or {}).get("isInBed")),
            loc.get("lastQuestionKey"), list(ui.get("dialogueResponses") or []))


def line(obs: dict) -> str:
    q, bed, key, rs = quest(obs)
    p = (obs.get("player") or {}).get("tile")
    return f"playerTile={p} isInBed={bed} dialogueIsQuestion={q} lastQuestionKey={key!r} responses={rs}"


def bed_cells(obs: dict) -> list[list[int]]:
    cells: list[list[int]] = []
    for f in (obs.get("location") or {}).get("furniture") or []:
        if not f.get("isBed"):
            continue
        bbox = f.get("bbox") or [0, 0, 64, 64]
        x0, y0 = int(bbox[0]) // 64, int(bbox[1]) // 64
        w = max(1, int(bbox[2]) // 64)
        h = max(1, int(bbox[3]) // 64)
        for dx in range(w):
            for dy in range(h):
                cells.append([x0 + dx, y0 + dy])
    return cells


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", action="store_true")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--off", nargs=2, type=int, default=None, help="先走到这个可站立格（保证 hasMoved）")
    args = ap.parse_args()

    c = BridgeClient(timeout=args.timeout)
    print("== 探针 #2：踩床格（touch action）==")
    print("存档（前）：", save_stat())
    obs = c.observe("full")
    print("起手：", line(obs))
    cells = bed_cells(obs)
    print("床占位格：", cells)
    if not cells:
        print("❌ 没找到 isBed 家具")
        return 2

    pt = (obs.get("player") or {}).get("tile")
    off = list(args.off) if args.off else ([pt[0] - 1, pt[1]] if pt else [8, 8])
    print(f"\n[第 0 步] 先走到床外 {off}（让 hasMoved=true，且离开床格）")
    try:
        r = c.move_to(off[0], off[1], timeout_ms=15000)
        print("  move_to 回执：", str(r.get("reason"))[:200])
    except BridgeError as exc:
        print(f"  move_to 失败：{exc.status}: {str(exc)[:200]}")
    time.sleep(0.8)
    obs = c.observe("full")
    print("  现在：", line(obs))

    hit = None
    for cell in cells:
        print(f"\n[踩 {cell}] move_to(allow_bed=True)")
        try:
            r = c.move_to(cell[0], cell[1], allow_bed=True, timeout_ms=15000)
            print("  move_to ok：", str(r.get("reason"))[:220])
        except BridgeError as exc:
            print(f"  move_to 失败：{exc.status}: {str(exc)[:220]}")
        time.sleep(0.8)
        obs = c.observe("full")
        print("  →", line(obs))
        if quest(obs)[0] or str(quest(obs)[2] or "").startswith("Sleep"):
            hit = cell
            print(f"✅ 命中：踩上 {cell} 让游戏弹出了睡觉提问")
            break

    if hit is None:
        print("\n❌ 六格逐个踩都没弹出提问（逐格读数见上）")
        return 1

    if not args.sleep:
        print("（未发 sleep；加 --sleep 才真的跨日）")
        return 0

    print("\n== 发 sleep 技能（游戏提问已经开着）==")
    before = c.observe("full")
    try:
        r = c.sleep(timeout_ms=180000)
        print("sleep 回执：", json.dumps(r, ensure_ascii=False, default=str)[:800])
    except BridgeError as exc:
        print(f"sleep 失败：{exc.status}: {str(exc)[:400]}")
    time.sleep(3.0)
    after = c.observe("full")
    print("day:", (before.get("clock") or {}).get("day"), "->", (after.get("clock") or {}).get("day"),
          (before.get("clock") or {}).get("season"), "->", (after.get("clock") or {}).get("season"))
    print("位置：", (before.get("player") or {}).get("tile"), "->", (after.get("player") or {}).get("tile"))
    print("存档（后）：", save_stat())
    moved = ((before.get("clock") or {}).get("day") != (after.get("clock") or {}).get("day"))
    print("结论：", "跨日成功 ✅" if moved else "跨日未发生 ❌")
    return 0 if moved else 1


if __name__ == "__main__":
    raise SystemExit(main())
