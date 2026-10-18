# -*- coding: utf-8 -*-
"""task-226 受控推进：用 `dismiss_modal` 逐句推进**非提问** DialogueBox，把挂住的 Furnace 事件跑完。

严格按 Lead 授权的循环（每步先 observe 再动）：
1) observe(summary)：确认 eventUp==true、activeMenu=="DialogueBox"、记 activeMenuText；
2) 每次动之前判停手：dialogueIsQuestion==true 或 dialogueResponses 非空 ⇒ 停手上报；
   professionsToChoose 非空 ⇒ 停手上报；eventUp==false ⇒ 事件结束；
3) 否则 dismiss_modal **一次** → 等 0.8s → observe → 比较 activeMenuText/activeMenu/eventUp：
   有变化 ⇒ 计一次有效推进继续；**连续 3 次无变化** ⇒ 停手上报；上限 **25 次**；
4) 事件结束后：observe(full) 记 tools/money/day/worldAdvancing，**不再发起任何技能**。
本脚本**不退出游戏、不 load_save、不 interact/use_tool/sleep**。

产物：`scratch/t226-advance.json`（逐步日志，activeMenuText 原文）+ `scratch/t226-advance-obs-NNN.json`
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

MAX_TRIES = 25
MAX_NO_PROGRESS = 3
# 事件脚本里有 `pause`；0.8s 的间隔会在 pause 窗口里"空推"三次被误判卡死（第一次 run 就是这样停的）。
# 3.0s 留够 pause 余量，仍然保留"连续 3 次无变化 ⇒ 停手"的规则。
WAIT_AFTER_DISMISS = 3.0


def snap(obs: dict) -> dict:
    c = obs.get("clock") or {}
    p = obs.get("player") or {}
    ui = obs.get("ui") or {}
    lv = obs.get("liveness") or {}
    return {"at": time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}",
            "day": [c.get("year"), c.get("season"), c.get("day")], "tod": c.get("timeOfDay"),
            "loc": p.get("location"), "tile": p.get("tile"), "money": p.get("money"),
            "canMove": p.get("canMove"),
            "activeMenu": ui.get("activeMenu"), "isModal": ui.get("isModal"),
            "activeMenuText": ui.get("activeMenuText") or "",
            "eventUp": ui.get("eventUp"),
            "dialogueIsQuestion": ui.get("dialogueIsQuestion"),
            "dialogueResponses": ui.get("dialogueResponses"),
            "professionsToChoose": ui.get("professionsToChoose"),
            "onScreenMenus": ui.get("onScreenMenus"),
            "worldAdvancing": lv.get("worldAdvancing"),
            "secondsSinceClockMoved": lv.get("secondsSinceClockMoved"),
            "worldSeq": obs.get("worldSeq")}


def main() -> int:
    c = BridgeClient(timeout=20.0)
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "max_tries": MAX_TRIES,
                 "steps": [], "stop_reason": None}
    obs = c.observe("summary")
    s = snap(obs)
    out["start"] = s
    (REPO / "scratch" / "t226-advance-obs-000.json").write_text(
        json.dumps({"snap": s}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"起始：eventUp={s['eventUp']} menu={s['activeMenu']} text={s['activeMenuText']!r} "
          f"tod={s['tod']} canMove={s['canMove']} worldAdvancing={s['worldAdvancing']}")

    if not s["eventUp"]:
        out["stop_reason"] = "event_already_over"
        print("!! eventUp 已经是 false —— 事件不在进行中，停手（不改现场）")
        (REPO / "scratch" / "t226-advance.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    no_progress = 0
    advances = 0
    ended = False
    for i in range(1, MAX_TRIES + 1):
        s = snap(obs)
        # --- 第 2 步：动之前判停手 ---
        if (s["dialogueIsQuestion"] is True) or (s["dialogueResponses"] or []):
            out["stop_reason"] = "dialogue_is_question"
            print(f"!! [第 {i} 次前] 出现选择题（q={s['dialogueIsQuestion']} resp={s['dialogueResponses']}）"
                  f" ⇒ 停手上报，绝不替游戏选")
            break
        if (s["professionsToChoose"] or []):
            out["stop_reason"] = "profession_choice_pending"
            print(f"!! 出现职业选择（{s['professionsToChoose']}）⇒ 停手上报")
            break
        if not s["eventUp"]:
            ended = True
            out["stop_reason"] = "event_ended"
            print(f"✅ [第 {i} 次前] eventUp 已 false —— 事件结束")
            break

        before_text, before_menu = s["activeMenuText"], s["activeMenu"]
        step = {"try": i, "before": {"menu": before_menu, "text": before_text,
                                     "tod": s["tod"], "worldSeq": s["worldSeq"]}}
        try:
            r = c.dismiss_modal()
            step["receipt"] = {"ok": r.get("ok"), "status": r.get("status"),
                               "reason": (r.get("reason") or "")[:300],
                               "worldResumed": r.get("worldResumed")}
            print(f"[{i:02d}] dismiss → ok={r.get('ok')} status={r.get('status')} "
                  f"reason={(r.get('reason') or '')[:120]}")
        except BridgeError as exc:
            step["receipt"] = {"error": f"{exc.status}: {(exc.reason or '')[:300]}"}
            print(f"[{i:02d}] dismiss → BridgeError {exc.status}: {(exc.reason or '')[:120]}")
        time.sleep(WAIT_AFTER_DISMISS)
        try:
            obs = c.observe("summary")
        except BridgeError as exc:
            step["after"] = {"observe_error": f"{exc.status}"}
            out["steps"].append(step)
            print(f"      observe 失败 {exc.status} ⇒ 停手")
            break
        s2 = snap(obs)
        (REPO / "scratch" / f"t226-advance-obs-{i:03d}.json").write_text(
            json.dumps({"snap": s2}, ensure_ascii=False, indent=2), encoding="utf-8")
        changed = (s2["activeMenuText"] != before_text or s2["activeMenu"] != before_menu
                   or s2["eventUp"] != s["eventUp"] or s2["worldSeq"] != s["worldSeq"])
        step["after"] = {"menu": s2["activeMenu"], "text": s2["activeMenuText"], "tod": s2["tod"],
                         "eventUp": s2["eventUp"], "worldSeq": s2["worldSeq"], "changed": changed}
        out["steps"].append(step)
        print(f"      → menu={s2['activeMenu']} text={s2['activeMenuText']!r} "
              f"eventUp={s2['eventUp']} tod={s2['tod']} changed={changed}")
        if changed:
            advances += 1
            no_progress = 0
        else:
            no_progress += 1
            if no_progress >= MAX_NO_PROGRESS:
                out["stop_reason"] = f"no_progress_x{MAX_NO_PROGRESS}"
                print(f"!! 连续 {MAX_NO_PROGRESS} 次无变化 ⇒ 停手上报")
                break
        if not s2["eventUp"]:
            ended = True
            out["stop_reason"] = "event_ended"
            print("✅ eventUp 变 false —— 事件结束")
            break
        if (s2["dialogueIsQuestion"] is True) or (s2["dialogueResponses"] or []):
            out["stop_reason"] = "dialogue_is_question_after"
            print("!! 下一句是选择题 ⇒ 停手上报，不再动")
            break

    out["advances"] = advances
    out["ended"] = ended
    if out["stop_reason"] is None:
        out["stop_reason"] = f"max_tries_{MAX_TRIES}"

    # --- 第 4 步：事件结束后只 observe，不发任何技能 ---
    obs_full = c.observe("full")
    sf = snap(obs_full)
    out["after"] = sf
    out["after_full"] = {"day": sf["day"], "tod": sf["tod"], "money": sf["money"],
                         "tools": (obs_full.get("player") or {}).get("tools"),
                         "invCount": (obs_full.get("player") or {}).get("inventoryCount"),
                         "inventory": (obs_full.get("player") or {}).get("inventory")}
    (REPO / "scratch" / "t226-advance.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n推进次数={advances} ended={ended} stop_reason={out['stop_reason']}")
    print(f"结束后：eventUp={sf['eventUp']} menu={sf['activeMenu']} tod={sf['tod']} "
          f"money={sf['money']} worldAdvancing={sf['worldAdvancing']} loc={sf['loc']}")
    print(f"工具：{json.dumps(out['after_full']['tools'], ensure_ascii=False)[:300]}")
    ok = ended and not sf["eventUp"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
