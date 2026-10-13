"""真机探针：睡觉提问到底是"哪一格 / 哪个入口"弹出来的。

背景（task-31 / task-33）：
- 0.7.22 彩排第 2 天 `sleep_no_question`：人已到 FarmHouse，`lastQuestionKey=(空)`，
  脑侧 `move_to(9,8)` 报 A* unreachable，兜底 `interact((9,8))` 也没让游戏弹提问。
- Lead 现场取证：FarmHouse 唯一床 = furniture `{"tile":[9,8],"bbox":[576,512,128,192],"isBed":true,...}`，
  即实际占 x∈{9,10} × y∈{8,9,10}（2×3 格），[9,8] 只是**原点**。
- 读档后玩家默认就站在床上（playerTile [9,9]、isInBed=true）。

本探针只做**读 + 发交互**，判据一律用 `observe?detail=full` 前后差分：
  对床占位的每个格子依次 `interact(cell)`，看 `ui.dialogueIsQuestion` / `location.lastQuestionKey`
  有没有真的变成"睡觉提问"（前缀 Sleep）。
命中后**不替用户选**，只如实报告；是否要真的 sleep 由调用方决定（--sleep 才发）。

用法：
  python scratch\probe_bed_live.py            # 只探测哪一格能弹提问
  python scratch\probe_bed_live.py --sleep    # 命中后紧接着发一次 sleep 技能，验证跨日
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


def snap(client: BridgeClient) -> dict:
    return client.observe("full", timeout=15.0)


def ui_of(obs: dict) -> dict:
    ui = obs.get("ui") or {}
    return {
        "isModal": ui.get("isModal"),
        "dialogueIsQuestion": ui.get("dialogueIsQuestion"),
        "dialogueResponses": ui.get("dialogueResponses"),
        "activeMenuText": ui.get("activeMenuText"),
    }


def quest_of(obs: dict) -> str:
    loc = obs.get("location") or {}
    return loc.get("lastQuestionKey")


def player_tile(obs: dict) -> list[int] | None:
    p = obs.get("player") or {}
    t = p.get("tile")
    return list(t) if t else None


def bed_cells(obs: dict) -> list[list[int]]:
    loc = obs.get("location") or {}
    cells: list[list[int]] = []
    for f in loc.get("furniture") or []:
        if not f.get("isBed"):
            continue
        tile = f.get("tile") or [0, 0]
        bbox = f.get("bbox") or [0, 0, 64, 64]
        x0 = int(bbox[0]) // 64
        y0 = int(bbox[1]) // 64
        w = max(1, int(bbox[2]) // 64)
        h = max(1, int(bbox[3]) // 64)
        for dx in range(w):
            for dy in range(h):
                cells.append([x0 + dx, y0 + dy])
        print(f"[床] tile={tile} bbox={bbox} type={f.get('type')} name={f.get('name')} "
              f"passable={f.get('passable')} 占位格={cells}")
    return cells


def try_interact(client: BridgeClient, cell: list[int]) -> tuple[bool, str, dict]:
    """发一次 interact，返回 (是否弹出提问, 回执文本, 观测)。"""
    receipt = ""
    try:
        r = client.interact(tuple(cell), timeout_ms=8000)
        receipt = f"ok status={r.get('status')} reason={str(r.get('reason'))[:160]}"
    except BridgeError as exc:
        receipt = f"ERR {exc.status}: {str(exc)[:200]}"
    time.sleep(0.6)
    obs = snap(client)
    hit = bool((obs.get("ui") or {}).get("dialogueIsQuestion")) or str(quest_of(obs) or "").startswith("Sleep")
    return hit, receipt, obs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", action="store_true", help="命中提问后接着发 sleep 技能验证跨日")
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args()

    client = BridgeClient(timeout=args.timeout)
    print("== 探针开始 ==")
    print(f"存档（前）：{save_stat()}")

    obs = snap(client)
    print("worldSeq", obs.get("worldSeq"), "day", obs.get("clock"), "player", player_tile(obs),
          "isInBed", (obs.get("player") or {}).get("isInBed"))
    print("ui（前）：", json.dumps(ui_of(obs), ensure_ascii=False))
    print("lastQuestionKey（前）：", repr(quest_of(obs)))

    cells = bed_cells(obs)
    if not cells:
        print("❌ 没有 isBed 家具 ⇒ 无从探测；把这份输出交给 Lead")
        return 2

    order = sorted(cells, key=lambda c: (abs(c[0] - (player_tile(obs) or [0, 0])[0])
                                         + abs(c[1] - (player_tile(obs) or [0, 0])[1])))
    hit_cell = None
    for cell in order:
        hit, receipt, after = try_interact(client, cell)
        print(f"[interact {cell}] 回执 {receipt}")
        print(f"    → ui={json.dumps(ui_of(after), ensure_ascii=False)} lastQuestionKey={quest_of(after)!r} "
              f"isInBed={(after.get('player') or {}).get('isInBed')} playerTile={player_tile(after)}")
        if hit:
            hit_cell = cell
            print(f"✅ 命中：interact({cell}) 让游戏弹出了睡觉提问")
            break

    if hit_cell is None:
        print("❌ 六格逐个 interact 都没有弹出睡觉提问（见上逐格读数）⇒ 入口不是 interact/checkAction，"
              "需要 IL 侧定案（task-31）")
        return 1

    if not args.sleep:
        print("（未发 sleep；加 --sleep 才会真的试着跨日）")
        return 0

    print("\n== 发 sleep 技能 ==")
    before = snap(client)
    try:
        r = client.sleep(timeout_ms=180000)
        print("sleep 回执：", json.dumps(r, ensure_ascii=False, default=str)[:600])
    except BridgeError as exc:
        print(f"sleep 失败：{exc.status}: {str(exc)[:300]}")
    time.sleep(2.0)
    after = snap(client)
    print("day before/after:", before.get("clock"), "->", after.get("clock"))
    print("ui（后）：", json.dumps(ui_of(after), ensure_ascii=False))
    print(f"存档（后）：{save_stat()}")
    day_moved = (before.get("clock") or {}).get("day") != (after.get("clock") or {}).get("day")
    print("结论：", "跨日成功 ✅" if day_moved else "跨日未发生 ❌")
    return 0 if day_moved else 1


if __name__ == "__main__":
    raise SystemExit(main())
