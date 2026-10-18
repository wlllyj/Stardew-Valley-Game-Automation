# -*- coding: utf-8 -*-
"""task-226 步骤 3（修正版）：读档后玩家是 `isInBed=true`（2:00 强制昏睡的存档），
脑侧 `FarmWorker.sleep()` 看到"已经在床上"就不再踩触发格 ⇒ `sleep_no_question`（提问永远不会弹）。

修法（不碰存档、不 load_save）：**先让玩家自己起床**（`move_to` 一个地板格，游戏会把 isInBed 复位），
再走脑侧真实 sleep 路径（stand_next_to(bed) → interact(bed) → 提问 → Sleep_Yes）。

判据同 verify-sleep-brain.py：day 恰好 +1、存档 size/mtime 前进、tod 回到约 06:00。
产物：`scratch/t226-getup-sleep.json`
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402
from agentfarm.farmwork import FarmWorker  # noqa: E402

SAVE_DIR = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"
CANDIDATES = [(9, 11), (10, 11), (8, 11), (10, 10), (11, 12)]
WAIT_S = 120.0


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


def fmt(sig: tuple[int, float]) -> str:
    return f"{sig[0]} B / mtime {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(sig[1]))}"


def day_key(obs: dict) -> tuple:
    c = obs.get("clock") or {}
    return (c.get("year"), c.get("season"), c.get("day"))


def brief(obs: dict) -> str:
    c = obs.get("clock") or {}
    p = obs.get("player") or {}
    return (f"day={list(day_key(obs))} tod={c.get('timeOfDay')} loc={p.get('location')} tile={p.get('tile')} "
            f"isInBed={p.get('isInBed')} canMove={p.get('canMove')} stam={p.get('stamina')} money={p.get('money')}")


def main() -> int:
    c = BridgeClient(timeout=20.0)
    w = FarmWorker(c)
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "candidates": CANDIDATES, "moves": []}
    obs = c.observe("full")
    out["before"] = brief(obs)
    print("起始：", out["before"])
    p = obs.get("player") or {}

    if bool(p.get("isInBed")):
        print("[起床] 玩家 isInBed=true（读档自 2:00 昏睡存档）⇒ 先走一步复位，否则 sleep 永远不弹提问")
        for t in CANDIDATES:
            try:
                r = c.move_to(t[0], t[1], timeout_ms=8000)
                st = r.get("status") or ("ok" if r.get("ok") else None)
                out["moves"].append({"tile": list(t), "status": st, "reason": str(r.get("reason"))[:200]})
                print(f"  move_to{t} -> status={st} reason={str(r.get('reason'))[:160]}")
            except BridgeError as exc:
                out["moves"].append({"tile": list(t), "error": f"{exc.status}: {(exc.reason or '')[:200]}"})
                print(f"  move_to{t} -> BridgeError {exc.status}")
            obs = c.observe("full")
            p = obs.get("player") or {}
            print(f"    现在 {brief(obs)}")
            if not bool(p.get("isInBed")):
                print("  ✅ 已起床（isInBed=false）")
                break
        if bool(p.get("isInBed")):
            print("!! 仍 isInBed=true ⇒ 停手（不猜、不 hack 存档）")
            out["verdict"] = "BLOCKED_STILL_IN_BED"
            (REPO / "scratch" / "t226-getup-sleep.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            return 2

    obs0 = c.observe("full")
    k0, sig0 = day_key(obs0), save_sig()
    out["sleep_before"] = brief(obs0)
    out["save_before"] = fmt(sig0)
    print("\n[1] 脑侧 worker.sleep(home='FarmHouse')")
    t0 = time.time()
    r = w.sleep(home="FarmHouse", timeout_ms=180000)
    out["sleep"] = {"ok": r.ok, "code": r.code, "reason": str(r.reason)[:600],
                    "receipt": str(getattr(r, "receipt", ""))[:400],
                    "elapsed_s": round(time.time() - t0, 2)}
    print(f"  ok={r.ok} code={r.code} {out['sleep']['elapsed_s']}s")
    print(f"  reason: {str(r.reason)[:400]}")

    print(f"[2] 轮询跨日（最多 {WAIT_S:.0f}s）")
    moved, last = False, None
    deadline = time.time() + WAIT_S
    while time.time() < deadline:
        try:
            obs = c.observe("full")
        except BridgeError as exc:
            print(f"    observe 中断：{exc.status}")
            time.sleep(3.0)
            continue
        line = brief(obs)
        if line != last:
            print(f"    t+{time.time() - t0:5.1f}s  {line}")
            last = line
        if day_key(obs) != k0:
            moved = True
            break
        time.sleep(2.0)

    sig1 = save_sig()
    o0 = None
    try:
        y0, s0, d0 = k0
        o0 = ((int(y0) - 1) * 4 + ["spring", "summer", "fall", "winter"].index(str(s0))) * 28 + int(d0)
    except Exception:  # noqa: BLE001
        pass
    k1 = day_key(obs)
    exact = False
    try:
        y1, s1, d1 = k1
        o1 = ((int(y1) - 1) * 4 + ["spring", "summer", "fall", "winter"].index(str(s1))) * 28 + int(d1)
        exact = o0 is not None and o1 - o0 == 1
    except Exception:  # noqa: BLE001
        pass
    save_ok = sig1[1] > sig0[1] or sig1[0] != sig0[0]
    out.update({"after": brief(obs), "save_after": fmt(sig1), "moved": moved,
                "day_exact_plus1": exact, "save_advanced": save_ok,
                "day_before": list(k0), "day_after": list(k1)})
    out["verdict"] = "VERIFIED_CROSS_DAY" if (moved and exact and save_ok) else "needs_review"
    print(f"\n[3] 判定：day {list(k0)} → {list(k1)} 恰好+1={exact}；存档 {out['save_after']} 前进={save_ok}")
    print(f"verdict={out['verdict']}")
    (REPO / "scratch" / "t226-getup-sleep.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if out["verdict"] == "VERIFIED_CROSS_DAY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
