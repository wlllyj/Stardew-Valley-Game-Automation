# -*- coding: utf-8 -*-
"""task-226 被动观察：事件挂住后**不动任何东西**，只 observe 60s，看它自己会不会继续推进。

判据：`eventUp` / `activeMenuText` / `activeMenu` / `worldSeq` / `tod` 任一变化 ⇒ 事件仍在自行推进
（说明刚才只是 `pause` 等待，需要更长的间隔继续点）；全都不变 ⇒ 真卡住，换原语。
产物：`scratch/t226-passive.json`
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

DURATION = 60.0


def snap(obs: dict) -> dict:
    c = obs.get("clock") or {}
    p = obs.get("player") or {}
    ui = obs.get("ui") or {}
    lv = obs.get("liveness") or {}
    return {"at": time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}",
            "day": [c.get("year"), c.get("season"), c.get("day")], "tod": c.get("timeOfDay"),
            "loc": p.get("location"), "activeMenu": ui.get("activeMenu"),
            "activeMenuText": ui.get("activeMenuText") or "", "eventUp": ui.get("eventUp"),
            "dialogueIsQuestion": ui.get("dialogueIsQuestion"),
            "dialogueResponses": ui.get("dialogueResponses"),
            "canMove": p.get("canMove"), "worldAdvancing": lv.get("worldAdvancing"),
            "worldSeq": obs.get("worldSeq"), "onScreenMenus": ui.get("onScreenMenus")}


def main() -> int:
    c = BridgeClient(timeout=20.0)
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "duration_s": DURATION, "samples": []}
    t0 = time.time()
    prev = None
    changes = 0
    while time.time() - t0 < DURATION:
        try:
            s = snap(c.observe("summary"))
        except BridgeError as exc:
            out["samples"].append({"t": round(time.time() - t0, 1), "observe_error": f"{exc.status}"})
            time.sleep(2.0)
            continue
        s["t"] = round(time.time() - t0, 1)
        out["samples"].append(s)
        key = (s["eventUp"], s["activeMenu"], s["activeMenuText"], s["worldSeq"], s["tod"])
        if prev is not None and key != prev:
            changes += 1
            print(f"  [{s['t']:5.1f}s] **变化** eventUp={s['eventUp']} menu={s['activeMenu']} "
                  f"text={s['activeMenuText']!r} tod={s['tod']} worldSeq={s['worldSeq']} canMove={s['canMove']}")
        elif prev is None:
            print(f"  [{s['t']:5.1f}s] 起：eventUp={s['eventUp']} menu={s['activeMenu']} "
                  f"text={s['activeMenuText']!r} tod={s['tod']} worldSeq={s['worldSeq']} "
                  f"worldAdvancing={s['worldAdvancing']} canMove={s['canMove']}")
        prev = key
        time.sleep(1.0)
    out["changes"] = changes
    out["final"] = prev and {"eventUp": prev[0], "activeMenu": prev[1], "text": prev[2],
                             "worldSeq": prev[3], "tod": prev[4]}
    (REPO / "scratch" / "t226-passive.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n60s 内变化次数={changes}；末态={json.dumps(out['final'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
