# -*- coding: utf-8 -*-
"""run4 起跑前：处置挂在游戏事件里的 DialogueBox（Lead m00603 授权的 (A) 方案 + 护栏）。

规则（脚本自己强制，触发任一即停手，不留判断余地）：
  - 每轮关框前先拍快照并记一行（round / activeMenuText / eventUp / isModal / worldAdvancing / canMove / clock）
  - 只调 dismiss_modal（Mod 自己走 closeDialogue()/exitThisMenu()，不合成键鼠）
  - 出现 dialogueIsQuestion=true 或 dialogueResponses 非空 ⇒ 立刻停（绝不替游戏选）
  - activeMenu 不是 DialogueBox（冒出新菜单类型）⇒ 立刻停
  - activeMenuText 命中剧情/选择关键词 ⇒ 立刻停
  - 最多 5 次；5 次后 eventUp 仍 true 或又冒新框 ⇒ 停
  - 记录落 logs\\run4-unblock.jsonl
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

try:
    from agentfarm.bridge import MOD_VERSION_EXPECTED  # type: ignore
except Exception:  # noqa: BLE001
    MOD_VERSION_EXPECTED = None

OUT = os.path.join(REPO, "logs", "run4-unblock.jsonl")
STOP_WORDS = (
    "cave", "mushroom", "bat", "gift", "festival", "marry", "adopt", "spouse", "choose", "select",
    "洞", "蘑菇", "蝙蝠", "赠", "礼物", "节日", "结婚", "求婚", "领养", "选择", "要不要",
)


def snap(c: BridgeClient):
    d = c.observe()
    pl = d.get("player") or {}
    ui = d.get("ui") or {}
    live = d.get("liveness") or {}
    clock = d.get("clock") or {}
    loc = d.get("location") or {}
    s = {
        "activeMenu": ui.get("activeMenu"),
        "isModal": ui.get("isModal"),
        "eventUp": ui.get("eventUp"),
        "activeMenuText": ui.get("activeMenuText"),
        "dialogueIsQuestion": ui.get("dialogueIsQuestion"),
        "dialogueResponses": ui.get("dialogueResponses") or [],
        "canMove": pl.get("canMove"),
        "worldAdvancing": live.get("worldAdvancing"),
        "secondsSinceClockMoved": live.get("secondsSinceClockMoved"),
        "clock": f"{clock.get('season')} {clock.get('day')} tod={clock.get('timeOfDay')} {clock.get('weather')}",
        "location": loc.get("name"),
        "tile": pl.get("tile"),
        "stamina": pl.get("stamina"),
        "money": pl.get("money"),
        "worldSeq": d.get("worldSeq"),
        "hasSaveLoaded": d.get("hasSaveLoaded"),
        "isOutdoorFarm": loc.get("isOutdoorFarm"),
    }
    return d, s


def show(tag: str, s: dict) -> None:
    print(
        f"{tag} activeMenu={s['activeMenu']!r} text={s['activeMenuText']!r} "
        f"eventUp={s['eventUp']} isModal={s['isModal']} q={s['dialogueIsQuestion']} "
        f"resp={s['dialogueResponses']} canMove={s['canMove']} worldAdvancing={s['worldAdvancing']} "
        f"secsSince={s['secondsSinceClockMoved']} clock={s['clock']} loc={s['location']} {s['tile']} stamina={s['stamina']} money={s['money']}"
    )


def guard_stop(s: dict) -> str | None:
    if s["dialogueIsQuestion"] or s["dialogueResponses"]:
        return "出现 dialogueIsQuestion=true 或 dialogueResponses 非空（事件里的选择）⇒ 绝不替游戏选"
    if s["activeMenu"] not in (None, "DialogueBox"):
        return f"冒出新的菜单类型 activeMenu={s['activeMenu']!r} ⇒ 停手上报"
    text = (s["activeMenuText"] or "").lower()
    hit = [w for w in STOP_WORDS if w in text]
    if hit:
        return f"activeMenuText 命中剧情/选择关键词 {hit} ⇒ 停手上报"
    return None


def main() -> int:
    c = BridgeClient()
    rows = []
    dismissals = 0
    stop_reason = None

    _, s0 = snap(c)
    print("=== 关框前快照 ===")
    show("before", s0)

    for rnd in range(1, 6):
        _, s = snap(c)
        if s["isModal"] is False and s["worldAdvancing"]:
            print(f"[第 {rnd} 轮] 已无模态且世界在推进 ⇒ 不需要再关框")
            break
        reason = guard_stop(s)
        if reason:
            stop_reason = reason
            print(f"*** HARD STOP（关框前）：{reason}")
            break

        print(f"\n--- 第 {dismissals + 1} 次 dismiss_modal（第 {rnd} 轮检查）---")
        t0 = time.time()
        try:
            rec = c.dismiss_modal(timeout_ms=5000)
            rec_txt = json.dumps(rec, ensure_ascii=False)[:600]
        except BridgeError as exc:
            rec = {"error": str(exc)}
            rec_txt = f"BridgeError: {str(exc)[:400]}"
        dismissals += 1
        print(f"回执（{time.time() - t0:.2f}s）：{rec_txt}")

        _, s2 = snap(c)
        show("after ", s2)
        row = {"round": rnd, "dismissal": dismissals, "before": s, "receipt": rec, "after": s2, "t": time.time()}
        rows.append(row)
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        if s2["dialogueIsQuestion"] or s2["dialogueResponses"]:
            stop_reason = "关框后冒出提问/选项 ⇒ 停手上报"
            print(f"*** HARD STOP：{stop_reason}")
            break
        if s2["isModal"] is False and s2["worldAdvancing"]:
            print("=> 模态已清且世界在推进")
            break
        if dismissals >= 5:
            stop_reason = "已关框 5 次仍未清干净 ⇒ 停手上报"
            print(f"*** HARD STOP：{stop_reason}")
            break

    print("\n=== 终态 ===")
    health = {}
    try:
        health = c.health()
    except BridgeError as exc:
        print(f"health 失败：{exc}")
    _, sf = snap(c)
    show("final ", sf)
    checks = {
        "modVersionMatches": (MOD_VERSION_EXPECTED is None) or (str(health.get("modVersion")) == str(MOD_VERSION_EXPECTED)),
        "hasSaveLoaded": bool(sf["hasSaveLoaded"]),
        "isOutdoorFarm": bool(sf["isOutdoorFarm"]),
        "isModalFalse": sf["isModal"] is False,
        "worldAdvancing": bool(sf["worldAdvancing"]),
    }
    print(f"装机 modVersion={health.get('modVersion')!r} / 期望 {MOD_VERSION_EXPECTED!r}")
    print("四判据+推进=" + json.dumps(checks, ensure_ascii=False))
    print(f"dismiss 次数={dismissals}  HARD STOP 原因={stop_reason!r}")
    verdict = "可起跑" if all(checks.values()) else "仍不可起跑"
    print(f"VERDICT: {verdict}")
    print(f"记录：{OUT}（{len(rows)} 行）")
    return 0 if verdict == "可起跑" else 3


if __name__ == "__main__":
    sys.exit(main())
