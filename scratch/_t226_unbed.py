# -*- coding: utf-8 -*-
"""task-226 步骤 3a：把玩家从"读档即在床上"（isInBed=true，2:00 昏睡存档）的状态里弄出来。

观察（真机已证）：in-bed 状态下 `move_to` 寸步难行（`unreachable` / `precondition_failed`），
脑侧 `sleep()` 也只会得到 `sleep_no_question`。所以先用**地点 warp**（游戏自己的门）离开农舍，
看 warp 是否顺带复位 `isInBed`；复位后再走回农舍，用脑侧真实 sleep 路径睡觉。

只做两次正常走动（`ensure_location`），不 dismiss、不点对话、不改存档。

产物：`scratch/t226-unbed.json`
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402
from agentfarm.farmwork import FarmWorker  # noqa: E402


def brief(obs: dict) -> dict:
    c = obs.get("clock") or {}
    p = obs.get("player") or {}
    ui = obs.get("ui") or {}
    return {"day": [c.get("year"), c.get("season"), c.get("day")], "tod": c.get("timeOfDay"),
            "loc": p.get("location"), "tile": p.get("tile"), "isInBed": p.get("isInBed"),
            "canMove": p.get("canMove"), "stamina": p.get("stamina"), "money": p.get("money"),
            "activeMenu": ui.get("activeMenu"), "isModal": ui.get("isModal"), "eventUp": ui.get("eventUp"),
            "worldSeq": obs.get("worldSeq")}


def main() -> int:
    c = BridgeClient(timeout=20.0)
    w = FarmWorker(c)
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "steps": []}
    obs = c.observe("full")
    out["before"] = brief(obs)
    print("before:", json.dumps(out["before"], ensure_ascii=False))

    for target in ("Farm", "FarmHouse"):
        try:
            r = w.ensure_location(target, timeout_ms=60000)
            res = {"target": target, "ok": r.ok, "code": r.code, "reason": str(r.reason)[:400]}
        except BridgeError as exc:
            res = {"target": target, "error": f"{exc.status}: {(exc.reason or '')[:300]}"}
        obs = c.observe("full")
        res["after"] = brief(obs)
        out["steps"].append(res)
        print(f"[ensure_location {target}] -> {json.dumps(res, ensure_ascii=False)[:600]}")
        if res["after"]["activeMenu"] or res["after"]["isModal"] or res["after"]["eventUp"]:
            print("!! 出现模态/事件 —— 按纪律不发任何请求，停手")
            out["blocked"] = {"target": target, "after": res["after"]}
            (REPO / "scratch" / "t226-unbed.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            return 3

    obs = c.observe("full")
    out["after"] = brief(obs)
    in_bed = bool((obs.get("player") or {}).get("isInBed"))
    out["isInBed_after"] = in_bed
    out["verdict"] = "STILL_IN_BED" if in_bed else "OUT_OF_BED"
    print(f"\n最终: {json.dumps(out['after'], ensure_ascii=False)}")
    print(f"verdict={out['verdict']}")
    (REPO / "scratch" / "t226-unbed.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if not in_bed else 2


if __name__ == "__main__":
    raise SystemExit(main())
