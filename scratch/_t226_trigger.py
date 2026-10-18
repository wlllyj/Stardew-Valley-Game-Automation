# -*- coding: utf-8 -*-
"""task-226 步骤 3b–4（按 task-223 定案精确化）：清掉晨间 ShippingMenu → 等落盘 → **进 Farm 地图**触发
`Data/Events/Farm` 键 `992553/t 600 1130/n copperFound`（Clint 送 Furnace 蓝图）。

纪律
- 只关 **ShippingMenu / SaveGameMenu 这类晨间结算框**（不是事件）；`eventUp=true` 时**一律不发**任何请求。
- 若 `professionsToChoose` 非空 ⇒ 停手上报（不许替游戏选职业）。
- 进 Farm 后只 `observe` 轮询，最多 120s；事件自行结束 `eventUp=false` ⇒ 记录；要求选项 ⇒ BLOCKED。

产物：`scratch/t226-trigger.json` + `scratch/t226-event-obs-NNN.json`
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
SAFE_MENUS = {"ShippingMenu", "SaveGameMenu", "NewDaySavingMenu", "LevelUpMenu", "DialogueBox"}
WIN_LO, WIN_HI = 600, 1130
MAX_WAIT = 120.0


def save_sig() -> tuple[int, float]:
    total, newest = 0, 0.0
    for name in ("Wahaha_450799035", "SaveGameInfo"):
        try:
            st = (SAVE_DIR / name).stat()
        except OSError:
            continue
        total += st.st_size
        newest = max(newest, st.st_mtime)
    return total, newest


def smapi_chain() -> dict:
    out: dict = {"lines": 0, "newday": [], "before_save": [], "save_called": [], "after_save": []}
    if not SMAPI.exists():
        return out
    lines = SMAPI.read_text(encoding="utf-8", errors="replace").splitlines()
    out["lines"] = len(lines)

    def real(pat: str) -> list[dict]:
        hits = []
        for i, ln in enumerate(lines, 1):
            if pat in ln and REAL_LINE.match(ln) and " by AgentFarm " not in ln and "| v0." not in ln:
                hits.append({"line": i, "text": ln[:160]})
        return hits

    out["newday"] = real("Synchronizing 'NewDay' task")
    out["before_save"] = real("Context: before save.")
    out["save_called"] = real("SaveGame.Save() called.")
    out["after_save"] = real("after save, starting")
    return out


def snap(obs: dict) -> dict:
    c = obs.get("clock") or {}
    p = obs.get("player") or {}
    ui = obs.get("ui") or {}
    lv = obs.get("liveness") or {}
    return {"at": time.strftime("%H:%M:%S"),
            "day": [c.get("year"), c.get("season"), c.get("day")], "tod": c.get("timeOfDay"),
            "loc": p.get("location"), "tile": p.get("tile"), "isInBed": p.get("isInBed"),
            "canMove": p.get("canMove"), "money": p.get("money"),
            "activeMenu": ui.get("activeMenu"), "isModal": ui.get("isModal"),
            "activeMenuText": (ui.get("activeMenuText") or "")[:120],
            "eventUp": ui.get("eventUp"), "dialogueIsQuestion": ui.get("dialogueIsQuestion"),
            "dialogueResponses": ui.get("dialogueResponses"),
            "professionsToChoose": ui.get("professionsToChoose"),
            "worldAdvancing": lv.get("worldAdvancing"),
            "secondsSinceClockMoved": lv.get("secondsSinceClockMoved"),
            "worldSeq": obs.get("worldSeq")}


def main() -> int:
    c = BridgeClient(timeout=20.0)
    w = FarmWorker(c)
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "window": [WIN_LO, WIN_HI],
                 "save_before": list(save_sig()), "menus_closed": [], "observations": []}
    obs = c.observe("full")
    out["start"] = snap(obs)
    print("起始：", json.dumps(out["start"], ensure_ascii=False))
    out["smapi_before"] = smapi_chain()

    # --- 清晨间结算框（不是事件）---
    for attempt in range(1, 4):
        s = snap(obs)
        if s["eventUp"]:
            print("!! eventUp=true —— 按纪律不发任何请求，停手")
            out["blocked"] = "eventUp_while_clearing_menu"
            break
        if (s["professionsToChoose"] or []):
            print("!! professionsToChoose 非空 —— 停手上报（不替游戏选职业）")
            out["blocked"] = "profession_choice_pending"
            break
        if not (s["isModal"] or s["activeMenu"]):
            break
        menu = s["activeMenu"]
        print(f"[清框 {attempt}] activeMenu={menu} isModal={s['isModal']} menuText={s['activeMenuText']!r} ⇒ dismiss_modal 一次")
        try:
            r = c.dismiss_modal()
            out["menus_closed"].append({"menu": menu, "receipt": r, "at": time.strftime("%H:%M:%S")})
            print(f"    回执 ok={r.get('ok')} status={r.get('status')} reason={(r.get('reason') or '')[:200]}")
        except BridgeError as exc:
            out["menus_closed"].append({"menu": menu, "error": f"{exc.status}: {(exc.reason or '')[:200]}"})
            print(f"    BridgeError {exc.status}: {(exc.reason or '')[:200]}")
        time.sleep(1.0)
        obs = c.observe("full")
        print("    之后：", json.dumps(snap(obs), ensure_ascii=False)[:400])
    out["after_menus"] = snap(obs)

    # --- 等落盘（task-47：菜单链不关完就不落盘）---
    print("\n[等落盘] 最多 60s（判据：存档 size/mtime 前进 + SMAPI NewDay/before save/Save called 链）")
    t0 = time.time()
    sig0 = save_sig()
    landed = False
    while time.time() - t0 < 60.0:
        sig1 = save_sig()
        chain = smapi_chain()
        if sig1[1] > sig0[1] or sig1[0] != sig0[0]:
            landed = True
            print(f"  ✅ 已落盘 t+{time.time() - t0:.1f}s  {sig1[0]} B / mtime "
                  f"{time.strftime('%H:%M:%S', time.localtime(sig1[1]))}；"
                  f"NewDay={len(chain['newday'])} before_save={len(chain['before_save'])} "
                  f"Save called={len(chain['save_called'])}")
            break
        time.sleep(1.5)
    out["save_landed"] = landed
    out["save_after_sleep"] = list(save_sig())
    out["smapi_after_land"] = smapi_chain()
    if not landed:
        print("  ⚠ 60s 内没看到落盘 —— 继续进 Farm（但 §3 会如实记为未落盘）")

    # --- 进 Farm 触发事件 ---
    obs = c.observe("full")
    s = snap(obs)
    if s["eventUp"]:
        print("!! 进 Farm 前 eventUp=true，停手")
        out["blocked"] = "eventUp_before_enter_farm"
        (REPO / "scratch" / "t226-trigger.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return 3
    print(f"\n[进 Farm] ensure_location('Farm')（地点={s['loc']} tod={s['tod']}）")
    t1 = time.time()
    try:
        mv = w.ensure_location("Farm", timeout_ms=60000)
        out["move"] = {"ok": mv.ok, "code": mv.code, "reason": str(mv.reason)[:600],
                       "elapsed_s": round(time.time() - t1, 2)}
    except BridgeError as exc:
        out["move"] = {"error": f"{exc.status}: {(exc.reason or '')[:400]}",
                       "elapsed_s": round(time.time() - t1, 2)}
    print("  ->", json.dumps(out["move"], ensure_ascii=False)[:500])

    print(f"\n[等事件] 每 1s/5s observe，最多 {MAX_WAIT:.0f}s；eventUp=true 时只等不点")
    seen_event, cleared = False, False
    deadline = time.time() + MAX_WAIT
    n = 0
    while time.time() < deadline:
        n += 1
        try:
            obs = c.observe("summary")
        except BridgeError as exc:
            out["observations"].append({"n": n, "observe_error": f"{exc.status}"})
            time.sleep(1.0)
            continue
        s = snap(obs)
        s["n"] = n
        s["t_s"] = round(time.time() - t1, 1)
        out["observations"].append(s)
        (REPO / "scratch" / f"t226-event-obs-{n:03d}.json").write_text(
            json.dumps({"snap": s, "observe": obs}, ensure_ascii=False, indent=2), encoding="utf-8")
        if s["eventUp"]:
            seen_event = True
            print(f"  [n={n} t+{s['t_s']}s] **eventUp=true** menu={s['activeMenu']} "
                  f"text={s['activeMenuText']!r} q={s['dialogueIsQuestion']} resp={s['dialogueResponses']} "
                  f":: 只等，不点")
            if s["dialogueIsQuestion"] or (s["dialogueResponses"] or []):
                out["blocked"] = "event_wants_input"
                break
        elif seen_event and not s["activeMenu"] and not s["isModal"]:
            cleared = True
            print(f"  [n={n} t+{s['t_s']}s] 事件已自行结束（eventUp=false 且无模态）")
            break
        elif n <= 6 or n % 6 == 0:
            print(f"  [n={n} t+{s['t_s']}s] eventUp=false loc={s['loc']} tod={s['tod']} "
                  f"worldAdvancing={s['worldAdvancing']}")
        time.sleep(1.0 if (time.time() - t1) < 30 else 5.0)

    out["after_event"] = snap(c.observe("full"))
    out["seen_event"] = seen_event
    out["event_cleared"] = cleared
    out["save_after_event"] = list(save_sig())
    out["smapi_after_event"] = smapi_chain()
    if out.get("blocked"):
        out["verdict"] = "BLOCKED"
    elif seen_event and cleared:
        out["verdict"] = "EVENT_PLAYED_AND_FINISHED"
    elif seen_event:
        out["verdict"] = "EVENT_STILL_UP"
    else:
        out["verdict"] = "NO_EVENT_OBSERVED"
    (REPO / "scratch" / "t226-trigger.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nseen_event={seen_event} cleared={cleared} blocked={out.get('blocked')} verdict={out['verdict']}")
    print("after:", json.dumps(out["after_event"], ensure_ascii=False)[:400])
    return 0 if out["verdict"] == "EVENT_PLAYED_AND_FINISHED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
