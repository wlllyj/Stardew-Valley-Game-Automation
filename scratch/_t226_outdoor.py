# -*- coding: utf-8 -*-
"""task-226 步骤 4：次日清晨 `6:00–11:30` **正常走出农舍**，只等 + 只看，绝不点/不 dismiss/不替游戏选。

纪律（`User said (m02865)` 事件政策）
- 只要出现 `eventUp=true` / `isModal=true`：**不发任何交互请求**（不 dismiss、不 answer、不 move），
  只 `observe(detail=summary)` 轮询等待，最多 **90 秒**。
- 过场自行结束（`eventUp=false` 且无模态）⇒ 记 `event_auto_finished`；
  90 秒后仍在 / 出现需要选项的对话（`dialogueIsQuestion=true` 或 `dialogueResponses` 非空）⇒ `BLOCKED`，停手。
- 出门动作用脑侧 `FarmWorker.ensure_location("Farm")`（= 走游戏自己的门格 warp），不手搓。

产物：`scratch/t226-outdoor.json` + 每次观测 `scratch/t226-event-obs-NNN.json`
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402
from agentfarm.farmwork import FarmWorker  # noqa: E402

SAVE_DIR = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"
SMAPI = Path(os.environ["APPDATA"]) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
REAL_LINE = re.compile(r"^\[\d{2}:\d{2}:\d{2} [A-Z]+ [^\]]+\]")
WINDOW = (600, 1130)  # 6:00–11:30
MAX_WAIT_S = 90.0


def save_sig() -> list[dict]:
    out = []
    for name in ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old"):
        p = SAVE_DIR / name
        try:
            st = p.stat()
        except OSError:
            out.append({"name": name, "size": None, "mtime": None})
            continue
        out.append({"name": name, "size": st.st_size,
                    "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime))})
    return out


def smapi_event_lines() -> list[str]:
    """SMAPI 里与事件/cutscene 相关的行（只作旁证，不改判定）。"""
    if not SMAPI.exists():
        return []
    keep = []
    for i, ln in enumerate(SMAPI.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        low = ln.lower()
        if ("event" in low or "cutscene" in low or "clintevent" in low) and REAL_LINE.match(ln):
            keep.append(f"L{i}: {ln[:300]}")
    return keep[-40:]


def snap(obs: dict) -> dict:
    c = obs.get("clock") or {}
    p = obs.get("player") or {}
    ui = obs.get("ui") or {}
    lv = obs.get("liveness") or {}
    g = obs.get("game") or {}
    return {
        "at": time.strftime("%H:%M:%S"),
        "clock": {"year": c.get("year"), "season": c.get("season"), "day": c.get("day"),
                  "timeOfDay": c.get("timeOfDay")},
        "location": p.get("location"), "tile": p.get("tile"), "isInBed": p.get("isInBed"),
        "canMove": p.get("canMove"),
        "activeMenu": ui.get("activeMenu"), "isModal": ui.get("isModal"), "eventUp": ui.get("eventUp"),
        "dialogueIsQuestion": ui.get("dialogueIsQuestion"),
        "dialogueResponses": ui.get("dialogueResponses"),
        "activeMenuText": ui.get("activeMenuText"),
        "worldAdvancing": lv.get("worldAdvancing"),
        "secondsSinceClockMoved": lv.get("secondsSinceClockMoved"),
        "shouldTimePass": g.get("shouldTimePass"), "paused": g.get("paused"),
        "worldSeq": obs.get("worldSeq"),
    }


def main() -> int:
    c = BridgeClient(timeout=20.0)
    worker = FarmWorker(c)
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "window": WINDOW, "max_wait_s": MAX_WAIT_S,
                 "observations": [], "blocked": None}
    h = c.health()
    out["health"] = {k: h.get(k) for k in ("ok", "status", "modVersion")}
    obs = c.observe("full")
    before = snap(obs)
    out["before"] = before
    out["save_before"] = save_sig()
    print(f"出门前：{json.dumps(before, ensure_ascii=False)}")
    if (before["location"] or "") != "FarmHouse":
        print(f"!! 期望在 FarmHouse 出门，实际 location={before['location']} ⇒ 停手（不猜）")
        out["blocked"] = f"not_in_FarmHouse:{before['location']}"
        (REPO / "scratch" / "t226-outdoor.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2
    tod = before["clock"].get("timeOfDay") or 0
    if not (WINDOW[0] <= tod <= WINDOW[1]):
        print(f"!! 出门时刻 tod={tod} 不在 {WINDOW} 窗口内 ⇒ 停手（等窗口，不硬来）")
        out["blocked"] = f"outside_window:{tod}"
        (REPO / "scratch" / "t226-outdoor.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return 3

    print("[1] 走出农舍：worker.ensure_location('Farm', timeout_ms=20000)（游戏自己的门格 warp）")
    t0 = time.time()
    try:
        mv = worker.ensure_location("Farm", timeout_ms=20000)
        out["move"] = {"ok": mv.ok, "code": mv.code, "reason": str(mv.reason)[:500],
                       "elapsed_s": round(time.time() - t0, 2)}
    except Exception as exc:  # noqa: BLE001  事件可能把走位打断
        out["move"] = {"exception": f"{type(exc).__name__}: {exc}", "elapsed_s": round(time.time() - t0, 2)}
    print(f"    -> {json.dumps(out['move'], ensure_ascii=False)[:500]}")

    print(f"[2] 只等 + 只看：每 1s（前 30s）/ 5s 观测，最多 {MAX_WAIT_S:.0f}s；出现 eventUp 也**不发任何请求**")
    seen_event = False
    event_cleared = False
    deadline = time.time() + MAX_WAIT_S
    n = 0
    poll_t0 = time.time()
    while time.time() < deadline:
        n += 1
        try:
            obs = c.observe("summary")
        except BridgeError as exc:
            out["observations"].append({"n": n, "at": time.strftime("%H:%M:%S"),
                                        "observe_error": f"{exc.status}: {(exc.reason or '')[:200]}"})
            time.sleep(1.0)
            continue
        s = snap(obs)
        s["n"] = n
        s["t_after_move_s"] = round(time.time() - t0, 1)
        out["observations"].append(s)
        (REPO / "scratch" / f"t226-event-obs-{n:03d}.json").write_text(
            json.dumps({"snap": s, "observe": obs}, ensure_ascii=False, indent=2), encoding="utf-8")
        if s["eventUp"]:
            seen_event = True
            print(f"    [n={n} t+{s['t_after_move_s']}s] **eventUp=true** menu={s['activeMenu']} "
                  f"menuText={(s['activeMenuText'] or '')[:60]!r} q={s['dialogueIsQuestion']} "
                  f"resp={s['dialogueResponses']} canMove={s['canMove']} :: 只等，不点")
            if s["dialogueIsQuestion"] or (s["dialogueResponses"] or []):
                out["blocked"] = "event_wants_input"
                print("!! 过场要求玩家选择 —— 按纪律停手，不替游戏选")
                break
        elif seen_event and s["activeMenu"] is None and not s["isModal"]:
            event_cleared = True
            print(f"    [n={n} t+{s['t_after_move_s']}s] 过场已自行结束（eventUp=false、无模态）")
            break
        else:
            if n <= 5 or n % 6 == 0:
                print(f"    [n={n} t+{s['t_after_move_s']}s] eventUp=false loc={s['location']} "
                      f"tod={s['clock'].get('timeOfDay')} canMove={s['canMove']} worldAdvancing={s['worldAdvancing']}")
        time.sleep(1.0 if (time.time() - poll_t0) < 30.0 else 5.0)

    after = snap(c.observe("full"))
    out["after"] = after
    out["save_after"] = save_sig()
    out["seen_event"] = seen_event
    out["event_cleared"] = event_cleared
    out["smapi_event_lines"] = smapi_event_lines()
    out["observations_count"] = len(out["observations"])
    if out["blocked"]:
        out["verdict"] = "BLOCKED"
    elif seen_event and event_cleared:
        out["verdict"] = "EVENT_PLAYED_AND_FINISHED"
    elif seen_event:
        out["verdict"] = "EVENT_STILL_UP_AFTER_90S"
    else:
        out["verdict"] = "NO_EVENT_OBSERVED"
    path = REPO / "scratch" / "t226-outdoor.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n观测 {out['observations_count']} 次；seen_event={seen_event} cleared={event_cleared} "
          f"blocked={out['blocked']} verdict={out['verdict']}")
    print(f"after: {json.dumps(after, ensure_ascii=False)[:400]}")
    print(f"-> {path}")
    return 0 if out["verdict"] == "EVENT_PLAYED_AND_FINISHED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
