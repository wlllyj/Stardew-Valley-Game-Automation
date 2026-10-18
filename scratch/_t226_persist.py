# -*- coding: utf-8 -*-
"""task-226 落盘：事件已跑完（"Learned how to craft a 'Furnace'"），但**配方只在内存** ——
`addCraftingRecipe` 必须经过一次 `NewDay` 落盘才能进存档，否则 `stop-game.py` 退出即丢。
本脚本只做一件事：**睡一夜**（`FarmWorker.sleep`），确认日切 + 存档 size/mtime 前进；
白天太早会 sleep_no_question/太早 —— 则等到 18:00 之后重试一次。

不 load_save、不改档、不点 GUI。
产物：`scratch/t226-persist.json`
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

SAVE = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"
SMAPI = Path(os.environ["APPDATA"]) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
REAL_LINE = re.compile(r"^\[\d{2}:\d{2}:\d{2} [A-Z]+ [^\]]+\]")


def sig() -> dict:
    out = {}
    for name in ("Wahaha_450799035", "SaveGameInfo"):
        try:
            st = (SAVE / name).stat()
            out[name] = {"size": st.st_size, "mtime": round(st.st_mtime, 3),
                         "at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))}
        except OSError:
            out[name] = None
    return out


def chain() -> dict:
    out = {"newday": 0, "before_save": 0, "save_called": 0, "after_save": 0, "lines": 0}
    if not SMAPI.exists():
        return out
    lines = SMAPI.read_text(encoding="utf-8", errors="replace").splitlines()
    out["lines"] = len(lines)
    for ln in lines:
        if not REAL_LINE.match(ln) or " by AgentFarm " in ln or "| v0." in ln:
            continue
        if "Synchronizing 'NewDay' task" in ln:
            out["newday"] += 1
        elif "Context: before save." in ln:
            out["before_save"] += 1
        elif "SaveGame.Save() called." in ln:
            out["save_called"] += 1
        elif "after save, starting" in ln:
            out["after_save"] += 1
    return out


def clock(obs: dict) -> dict:
    c = obs.get("clock") or {}
    p = obs.get("player") or {}
    ui = obs.get("ui") or {}
    return {"day": [c.get("year"), c.get("season"), c.get("day")], "tod": c.get("timeOfDay"),
            "loc": p.get("location"), "isInBed": p.get("isInBed"), "money": p.get("money"),
            "stamina": p.get("stamina"), "eventUp": ui.get("eventUp"),
            "activeMenu": ui.get("activeMenu"), "canMove": p.get("canMove"),
            "worldSeq": obs.get("worldSeq")}


def main() -> int:
    c = BridgeClient(timeout=30.0)
    w = FarmWorker(c)
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "save_before": sig(),
                 "chain_before": chain(), "attempts": []}
    obs = c.observe("full")
    out["start"] = clock(obs)
    print("起始：", json.dumps(out["start"], ensure_ascii=False))
    if (obs.get("ui") or {}).get("eventUp"):
        print("!! eventUp 仍为 true —— 不睡，停手")
        return 2

    try:
        day0 = [obs["clock"]["year"], obs["clock"]["season"], obs["clock"]["day"]]
        tod0 = obs["clock"]["timeOfDay"]
    except Exception:  # noqa: BLE001
        day0, tod0 = None, None
    out["day_before"], out["tod_before"] = day0, tod0

    # 等到 18:00（1080）之后再睡 —— 白天太早游戏可能不给睡；等到上限 240s
    t_waited = 0.0
    while True:
        obs = c.observe("summary")
        tod = (obs.get("clock") or {}).get("timeOfDay") or 0
        if tod >= 1060 or t_waited >= 240:
            break
        time.sleep(10.0)
        t_waited += 10.0
    print(f"等待 {t_waited:.0f}s，tod={tod} ⇒ 开始尝试睡觉")

    ok = False
    for attempt in (1, 2):
        print(f"\n[sleep 第 {attempt} 次] FarmWorker.sleep()")
        try:
            st = w.sleep(timeout_ms=180000)
            rec = {"attempt": attempt, "ok": st.ok, "code": st.code,
                   "reason": str(st.reason)[:600],
                   "receipt": st.receipt if isinstance(st.receipt, dict) else str(st.receipt)[:600]}
            print(f"  ok={st.ok} code={st.code} reason={str(st.reason)[:300]}")
            print(f"  receipt={json.dumps(rec['receipt'], ensure_ascii=False)[:400]}")
        except BridgeError as exc:
            rec = {"attempt": attempt, "error": f"{exc.status}: {(exc.reason or '')[:600]}"}
            print(f"  BridgeError {exc.status}: {(exc.reason or '')[:300]}")
        out["attempts"].append(rec)
        time.sleep(1.0)
        obs = c.observe("full")
        out[f"after_sleep_{attempt}"] = clock(obs)
        print("  之后：", json.dumps(out[f"after_sleep_{attempt}"], ensure_ascii=False))
        d = out[f"after_sleep_{attempt}"]["day"]
        if day0 and d and d != day0:
            print("  ✅ 日已推进")
            ok = True
            break
        if attempt == 1:
            print("  日未推进 ⇒ 等 90s 再试一次（可能提问/菜单/太早）")
            time.sleep(90.0)

    print("\n[等落盘] 最多 90s")
    t0 = time.time()
    landed = False
    while time.time() - t0 < 90.0:
        s = sig()
        if s["Wahaha_450799035"] and out["save_before"]["Wahaha_450799035"] and \
                (s["Wahaha_450799035"]["mtime"] > out["save_before"]["Wahaha_450799035"]["mtime"]):
            landed = True
            break
        time.sleep(1.5)
    out["save_after"] = sig()
    out["chain_after"] = chain()
    out["landed"] = landed
    out["day_changed"] = ok
    print(f"落盘={landed}；save_after={json.dumps(out['save_after'], ensure_ascii=False)}")
    print(f"chain: {json.dumps(out['chain_after'], ensure_ascii=False)}")
    (REPO / "scratch" / "t226-persist.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if (ok and landed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
