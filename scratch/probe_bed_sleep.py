r"""真机探针 #3：踩上**床格 (10,9)** 引出睡觉提问 → 发 `sleep` 技能 → 验证真跨日。

探针 #2（`scratch\probe_bed_live2.py`）的决定性发现（`logs\probe-bed-live2-run1.log`）：
  - 先走到床外 (8,9)（`hasMoved=true`、`isInBed=False`）后，
    逐个踩床占位格：[9,8] unreachable / [9,9] ok 但**无提问** / [9,10] unreachable /
    [10,8] unreachable / **[10,9] ⇒ `move_to` 回 `ui_modal`（移动被菜单打断），
    随后 `ui.dialogueIsQuestion=true`、`dialogueResponses=['Yes','No']`** ⇒ 命中。
  - 与 IL 一致（`scratch\il-bed-5.txt:1283-1300`）：`performTouchAction` 的 `"Sleep"` 分支要求
    `!Game1.newDay && shouldTimePass(false) && player.hasMoved && !player.passedOut`，
    由 `GameLocation.UpdateWhenCurrentLocation` 在**移动着踩到**该格时触发；`checkAction` 无关。

本探针：需要时先把提问引出来（走去 (8,9) 再踩 (10,9)），打印 ui 详情，然后发 `sleep(180s)`，
按【可观测即证据】核对 `day` 是否 +1 与存档 size/mtime 是否前进。

用法：
  python scratch\probe_bed_sleep.py
  python scratch\probe_bed_sleep.py --trigger-cell 10 9 --off 8 9
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
    except OSError as exc:  # noqa: BLE001
        print("读存档失败：", exc)
        return -1, -1.0


def fmt(st: tuple[int, float]) -> str:
    return f"{st[0]} B / mtime {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st[1]))}"


def ui_of(obs: dict) -> dict:
    return obs.get("ui") or {}


def brief(obs: dict) -> str:
    clk = obs.get("clock") or {}
    pl = obs.get("player") or {}
    ui = ui_of(obs)
    return (
        f"day={[clk.get('year'), clk.get('season'), clk.get('day')]} tod={clk.get('timeOfDay')} "
        f"tile={pl.get('tile')} isInBed={pl.get('isInBed')} "
        f"question={ui.get('dialogueIsQuestion')} responses={ui.get('dialogueResponses')} "
        f"menuText={str(ui.get('activeMenuText'))[:80]!r}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--off", nargs=2, type=int, default=[8, 9])
    ap.add_argument("--trigger-cell", nargs=2, type=int, default=[10, 9])
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args()

    c = BridgeClient(timeout=args.timeout)
    before_stat = save_stat()
    print("== 探针 #3：踩床 → sleep → 真跨日 ==")
    print("存档（前）：", fmt(before_stat))
    obs = c.observe("full")
    print("起手：", brief(obs))

    if not ui_of(obs).get("dialogueIsQuestion"):
        print(f"\n[引出提问] 先走去床外 {args.off}")
        try:
            c.move_to(args.off[0], args.off[1], timeout_ms=15000)
        except BridgeError as exc:
            print(f"  → {exc.status}: {str(exc)[:160]}")
        time.sleep(0.6)
        print("   现在：", brief(c.observe("full")))
        print(f"[引出提问] 踩上床格 {args.trigger_cell}（allow_bed=True，预期回 ui_modal）")
        try:
            r = c.move_to(args.trigger_cell[0], args.trigger_cell[1], allow_bed=True, timeout_ms=15000)
            print("  move_to ok：", str(r.get("reason"))[:180])
        except BridgeError as exc:
            print(f"  move_to 回：{exc.status}: {str(exc)[:180]}")
        time.sleep(0.8)
        obs = c.observe("full")
        print("   →", brief(obs))

    if not ui_of(obs).get("dialogueIsQuestion"):
        print("\n❌ 没引出睡觉提问（无法验证 sleep 链路）")
        return 1

    print("\nui 详情：", json.dumps(ui_of(obs), ensure_ascii=False, default=str)[:600])
    loc = obs.get("location") or {}
    print("lastQuestionKey：", repr(loc.get("lastQuestionKey")))

    print("\n== 发 sleep 技能（180s 预算）==")
    t0 = time.time()
    try:
        r = c.sleep(timeout_ms=180000)
        print(f"sleep 回执（{time.time() - t0:.1f}s）：", json.dumps(r, ensure_ascii=False, default=str)[:900])
    except BridgeError as exc:
        print(f"sleep 失败（{time.time() - t0:.1f}s）：{exc.status}: {str(exc)[:500]}")
    time.sleep(3.0)

    after = c.observe("full")
    after_stat = save_stat()
    print("\n== 观测（睡后）==")
    print("day/tile：", brief(after))
    print("存档（后）：", fmt(after_stat))

    b, a = (obs.get("clock") or {}), (after.get("clock") or {})
    day_moved = (b.get("day") != a.get("day")) or (b.get("season") != a.get("season")) or (
        b.get("year") != a.get("year")
    )
    save_moved = after_stat[1] > before_stat[1] or after_stat[0] != before_stat[0]
    print("\n跨日（观测）：", "✅ 是" if day_moved else "❌ 否")
    print("存档前进：", "✅ 是" if save_moved else "❌ 否")
    verdict = day_moved and save_moved
    print("结论：", "VERIFIED —— sleep 链路真跨日 🎉" if verdict else "needs_review")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
