#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""task-34 只读探针：0.7.46 `talk` 原语能否在 SeedShop 对 Pierre 开出背包升级对话。

前提
----
- 0.7.46 已冻结并装机（Mod dll 含 talk），游戏已由 `python tools\\deploy-mod.py --no-quit`
  起好、桥 /v1/exec 可达（本脚本**不负责起游戏/装机**）。
- 冻结装机前请先核 `mod\\AgentFarm.Bridge\\bin\\Release\\AgentFarm.Bridge.dll` 的 SHA256
  是否等于冻结产物（WIP 构建 `F05289C9…` 不是冻结产物）——本脚本可传 `--expect-dll-sha`
  做只读断言，不通过就只记录、不运行探针。

红线（task-34 卡 / Lead m01332）
--------------------------------
- **永不回答 Purchase**：对提问只用 `dismiss_modal()` **无参**（选否/关对话），或
  `load_save(force=True)` 退出对话；绝不传 answerText/answerIndex，绝不选购买项。
- 只读：不买、不种、不卖、不改世界、不写存档、不 restore A9、不 load 别的档
  （唯一例外：事件卡死时的 `load_save(force=True)` 重读**同一个**存档做自愈，已计入证据）。
- 优雅退：默认收尾调 `tools/stop-game.py --wait 45`，并复核进程 0 / bridge.json 删 /
  17890 无 LISTENING；存档四件退前退后 SHA256 记录在证据里。

快速通道（比"进店后乱走"更省时，已在代码里实现）
------------------------------------------------
1. `talk` 自带相邻校验（切比雪夫距离 ≤1）。先直接 `talk {"npc":"Pierre"}`；若回
   `not_adjacent`，回执里带 `npcTile`，再用 `move_to` 逐个试 8 邻格，走到相邻后再 talk。
2. 进店前先 `observe` 看 `ui.activeMenuText`：若店门锁着（9:00 前/21:00 后）就等时钟到
   9:00 再进，省得白跑。
3. 对话推进只用 `advance_dialogue`（它只推非提问对话、绝不替玩家选选项）；一旦
   `dialogueIsQuestion=true` 立刻停手记录，然后 `dismiss_modal()` 无参退出。

用法
----
    set PYTHONUTF8=1
    python scratch\\_t34_talk_probe.py --minutes 10
    python scratch\\_t34_talk_probe.py --dry-run          # 只查环境/装机哈希/存档哈希，不碰桥
    python scratch\\_t34_talk_probe.py --no-stop          # 调试用：不收尾，留给人工

产物
----
- `scratch\\_t34_talk_probe.json`：完整证据（每步回执原文/observe ui 摘要/存档四件前后/装机哈希/
  SMAPI 窗口副本哈希/结论字段）。
- `logs\\probe-talk-0746-smapi-window.txt`：收尾后冻结的 SMAPI 窗口副本（源=最新 SMAPI-latest.txt）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
BRIDGE_PATH = os.path.join(APPDATA, "StardewValley", "AgentFarm", "bridge.json")
SMAPI_LATEST = os.path.join(APPDATA, "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
SAVE_DIR = os.path.join(APPDATA, "StardewValley", "Saves", "Wahaha_450799035")
SAVE_FILES = ["Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old"]
GAME_DIR = r"D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley"
MOD_DIR = os.path.join(GAME_DIR, "Mods", "AgentFarm.Bridge")
MOD_FILES = ["AgentFarm.Bridge.dll", "manifest.json"]
SMAPI_COPY = os.path.join(REPO, "logs", "probe-talk-0746-smapi-window.txt")
OUT_DEFAULT = os.path.join(REPO, "scratch", "_t34_talk_probe.json")

# 事件卡死门限（docs/_probe-backpack-dialogue.md §3.4 + 实跑校准：task-32 A#2 从进 Town
# 到「提问」约 56s，故 no_dialogue 连续 12 次 / 90s 无进展才判 hang）
HANG_CONSEC_NO_DIALOGUE = 12
HANG_SECONDS = 90.0
SELF_HEAL_LIMIT = 2
OPEN_TIME = 900  # 店门 9:00 开；之前进店 Pierre 不在柜台（task-32 实测 7:50 锁门）

# 8 邻格偏移（切比雪夫距离 1），用于 talk 的 not_adjacent 后贴近 NPC
NEIGHBOR_OFFSETS = [(0, 1), (1, 0), (-1, 0), (1, 1), (-1, 1), (0, -1), (1, -1), (-1, -1)]

LOG: list[dict] = []


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log(msg: str, **kw) -> None:
    entry = {"t": now_iso(), "msg": msg}
    entry.update(kw)
    LOG.append(entry)
    print(f"[{entry['t']}] {msg}", flush=True)


def sha256_file(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def file_info(path: str) -> dict:
    try:
        st = os.stat(path)
    except OSError:
        return {"path": path, "exists": False}
    return {
        "path": path,
        "exists": True,
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds"),
        "sha256": sha256_file(path),
    }


def save_hashes() -> dict:
    return {name: file_info(os.path.join(SAVE_DIR, name)) for name in SAVE_FILES}


def mod_hashes() -> dict:
    return {name: file_info(os.path.join(MOD_DIR, name)) for name in MOD_FILES}


def bridge_info() -> dict | None:
    if not os.path.isfile(BRIDGE_PATH):
        return None
    try:
        with open(BRIDGE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def port_listening(port: int = 17890) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def process_count() -> dict:
    """只读数进程（不杀、不写）。tasklist 解析失败时如实写 unknown。"""
    out = {}
    for name in ("StardewModdingAPI.exe", "Stardew Valley.exe"):
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=20,
            )
            text = (r.stdout or "").strip()
            out[name] = 0 if (not text or text.lower().startswith("info:")) else len(
                [ln for ln in text.splitlines() if name.lower() in ln.lower()]
            )
        except Exception:  # noqa: BLE001 - 读不到就写 unknown，不猜
            out[name] = "unknown"
    return out


def wait_for_bridge(seconds: float) -> dict | None:
    """等 bridge.json 出现（deploy-mod --no-quit 的桥就绪信号）。"""
    deadline = time.time() + max(0.0, seconds)
    while time.time() < deadline:
        info = bridge_info()
        if info:
            return info
        time.sleep(2.0)
    return None


def observe(c: BridgeClient, detail: str = "full") -> dict:
    try:
        return c.observe(detail)
    except BridgeError:
        if detail != "summary":
            return c.observe("summary")
        raise


def ui_snapshot(obs: dict) -> dict:
    loc = obs.get("location") or {}
    player = obs.get("player") or {}
    ui = obs.get("ui") or {}
    clock = obs.get("clock") or {}
    liveness = obs.get("liveness") or {}
    return {
        "location": (loc.get("name") or loc.get("displayName") or loc.get("id")),
        "clock": clock.get("timeOfDay"),
        "season": clock.get("season"),
        "day": clock.get("day"),
        "player_tile": player.get("tile"),
        "canMove": player.get("canMove"),
        "money": player.get("money"),
        "ui": {
            "isModal": ui.get("isModal"),
            "eventUp": ui.get("eventUp"),
            "eventId": ui.get("eventId"),
            "activeMenu": ui.get("activeMenu"),
            "activeMenuText": ui.get("activeMenuText"),
            "dialogueIsQuestion": ui.get("dialogueIsQuestion"),
            "dialogueResponses": ui.get("dialogueResponses"),
            "onScreenMenus": ui.get("onScreenMenus"),
        },
        "liveness": {
            "worldAdvancing": liveness.get("worldAdvancing"),
            "secondsSinceClockMoved": liveness.get("secondsSinceClockMoved"),
        },
    }


def safe_payload(exc: BaseException) -> dict:
    payload = getattr(exc, "payload", None)
    return {
        "error_type": type(exc).__name__,
        "message": str(exc)[:800],
        "status": getattr(exc, "status", None),
        "payload": payload if isinstance(payload, dict) else None,
    }


def exec_raw(c: BridgeClient, skill: str, args: dict | None, timeout_ms: int) -> dict:
    """执行技能并返回完整回执（成功=响应 JSON；失败=BridgeError 的 status/payload 原文）。"""
    t0 = time.time()
    try:
        result = c.exec_skill(skill, args, timeout_ms=timeout_ms)
        return {"skill": skill, "args": args, "http_ok": True, "elapsed_ms": int((time.time() - t0) * 1000),
                "result": result}
    except BridgeError as exc:
        return {"skill": skill, "args": args, "http_ok": False, "elapsed_ms": int((time.time() - t0) * 1000),
                **safe_payload(exc)}
    except Exception as exc:  # noqa: BLE001 - 非桥异常也要留原文
        return {"skill": skill, "args": args, "http_ok": False, "elapsed_ms": int((time.time() - t0) * 1000),
                **safe_payload(exc)}


def receipt_code(rec: dict) -> str:
    """从成功回执或错误回执里取 stable code/status。"""
    body = rec.get("result") if rec.get("http_ok") else rec.get("payload")
    if isinstance(body, dict):
        return str(body.get("code") or body.get("status") or "")
    return ""


def clear_cutscene(c: BridgeClient, out: dict, deadline: float, max_s: float = 110.0) -> bool:
    """推进"事件态过场"（含无对话盒的走位/定格段），直到 eventUp=false 或超时。

    只调 advance_dialogue（受控推进原语）：绝不 dismiss（那会 closeDialogue 跳句）、
    绝不替玩家选选项（提问 ⇒ 立即停并返回 False）。
    """
    t0 = time.time()
    rounds = 0
    out.setdefault("cutscene_advance", [])
    while time.time() - t0 < max_s and time.time() < deadline:
        o = observe(c)
        snap = ui_snapshot(o)
        ui = snap.get("ui") or {}
        if not ui.get("eventUp"):
            return True
        rec = exec_raw(c, "advance_dialogue", {"maxSteps": 10}, 20000)
        code = receipt_code(rec)
        rounds += 1
        out["cutscene_advance"].append({"t": now_iso(), "ui": ui, "receipt": rec})
        log("cutscene advance", round=rounds, code=code,
            eventId=ui.get("eventId"), menu=ui.get("activeMenu"))
        if code in ("question", "is_question"):
            return False
        if code == "no_dialogue":
            time.sleep(2.0)
    return False


def wait_modal_clear(c: BridgeClient, rounds: int = 3, out: dict | None = None) -> bool:
    """无参 dismiss_modal 清模态（永不回答 Purchase、不选 Yes）。"""
    for i in range(1, rounds + 1):
        obs = observe(c)
        snap = ui_snapshot(obs)
        if not snap["ui"]["isModal"]:
            return True
        if snap["ui"].get("eventUp"):
            return False  # 事件对话归 advance_dialogue；dismiss 会 closeDialogue() 跳句
        rec = exec_raw(c, "dismiss_modal", None, 5000)
        if out is not None:
            out.setdefault("dismiss_receipts", []).append({"round": i, "before": snap["ui"], "receipt": rec})
        log("dismiss_modal no-arg", round=i, http_ok=rec["http_ok"], code=receipt_code(rec))
        time.sleep(1.5)
    obs = observe(c)
    return not ui_snapshot(obs)["ui"]["isModal"]


def wait_until_open(c: BridgeClient, out: dict, deadline: float, open_tod: int = OPEN_TIME) -> bool:
    """只读等待游戏时钟到开门时间（不睡觉、不用调试命令）。"""
    t0 = time.time()
    while time.time() < deadline:
        snap = ui_snapshot(observe(c))
        if snap["location"] == "SeedShop":
            return True
        tod = snap["clock"]
        if isinstance(tod, int) and tod >= open_tod:
            return True
        if int(time.time() - t0) % 30 < 5:
            log("waiting for shop open", clock=tod, waited_s=round(time.time() - t0, 1))
        time.sleep(5.0)
    out.setdefault("notes", []).append("等待开门超时（deadline）")
    return False


def wait_event_and_modal_clear(c: BridgeClient, out: dict, deadline: float,
                               heal_limit: int = SELF_HEAL_LIMIT) -> str:
    """等事件/对话结束；卡死时按门限判 hang 并 load_save(force=True) 自愈。

    返回: 'cleared' | 'healed' | 'question' | 'deadline'
    """
    no_dialogue = 0
    t_no_progress = time.time()
    heals = 0
    while time.time() < deadline:
        obs = observe(c)
        snap = ui_snapshot(obs)
        loc = snap["location"]
        ui = snap["ui"]
        if not ui["isModal"] and not ui["eventUp"]:
            return "cleared"
        if ui["dialogueIsQuestion"]:
            # 红线：绝不回答 Purchase/Yes；无参 dismiss = 游戏自己的「选否/关对话」
            rec = exec_raw(c, "dismiss_modal", None, 8000)
            out.setdefault("question_dismiss", []).append({"t": now_iso(), "loc": loc, "ui": ui, "receipt": rec})
            log("question seen -> dismiss_modal no-arg", loc=loc, code=receipt_code(rec))
            time.sleep(2.5)
            continue
        if loc == "BusStop":
            # BusStop 的 520702 是过场：通常几秒自己结束，只等不点，不计入 hang 门限
            time.sleep(3.0)
            continue
        if (ui["eventUp"] or ui["isModal"]) and not ui["activeMenu"]:
            rec = exec_raw(c, "advance_dialogue", {"maxSteps": 10}, 20000)
            code = receipt_code(rec)
            body = rec.get("result") if rec.get("http_ok") else (rec.get("payload") or {})
            stepped = 0
            if isinstance(body, dict):
                try:
                    stepped = int(body.get("stepped") or 0)
                except (TypeError, ValueError):
                    stepped = 0
            progress = code in ("max_steps_reached", "ok", "advanced", "typing") or stepped > 0
            out.setdefault("event_advance", []).append({"t": now_iso(), "loc": loc, "ui": ui, "receipt": rec})
            if progress:
                no_dialogue = 0
                t_no_progress = time.time()
            else:
                no_dialogue += 1
            stalled_for = time.time() - t_no_progress
            log("event advance", loc=loc, code=code, stepped=stepped, no_dialogue=no_dialogue,
                stalled_s=round(stalled_for, 1))
            if no_dialogue >= HANG_CONSEC_NO_DIALOGUE or stalled_for >= HANG_SECONDS:
                # 先试一次无参 dismiss（个别"无对话盒的等待"其实是模态提示）
                if out.get("stall_dismiss_tried") != loc:
                    rec2 = exec_raw(c, "dismiss_modal", None, 5000)
                    out.setdefault("stall_dismiss", []).append({"at": now_iso(), "loc": loc, "receipt": rec2})
                    out["stall_dismiss_tried"] = loc
                    time.sleep(3.0)
                    no_dialogue = 0
                    t_no_progress = time.time()
                    continue
                if heals < heal_limit:
                    heals += 1
                    log("EVENT HANG -> load_save(force=True) self-heal", attempt=heals, loc=loc,
                        stalled_s=round(stalled_for, 1))
                    heal = exec_raw(c, "load_save", {"save": "Wahaha_450799035", "force": True}, 90000)
                    out.setdefault("self_heals", []).append(
                        {"at": now_iso(), "loc": loc, "ui_before": ui, "heal": heal})
                    time.sleep(3.0)
                    return "healed"
                out.setdefault("notes", []).append("事件卡死且自愈次数用尽，停止推进")
                return "deadline"
            time.sleep(2.5)
        elif ui["activeMenu"] == "DialogueBox":
            rec = exec_raw(c, "advance_dialogue", {"maxSteps": 10}, 20000)
            out.setdefault("dialogue_advance", []).append({"t": now_iso(), "ui": ui, "receipt": rec})
            no_dialogue = 0
            t_no_progress = time.time()
            time.sleep(1.5)
        else:
            # 有活动菜单但不是对话（锁门提示/商店等）：只用无参 dismiss，不选任何选项
            rec = exec_raw(c, "dismiss_modal", None, 5000)
            out.setdefault("dismiss_receipts", []).append({"at": now_iso(), "ui": ui, "receipt": rec})
            time.sleep(2.0)
    return "deadline"


def goto_seedshop(c: BridgeClient, out: dict, deadline: float) -> bool:
    heals_used = 0
    # 店门 9:00 开、Pierre 9:00 才在柜台：先在城里等时钟（只读），别在 6:00 白跑
    wait_until_open(c, out, deadline)
    for attempt in range(1, 6):
        if time.time() >= deadline:
            return False
        obs = observe(c)
        snap = ui_snapshot(obs)
        loc = snap["location"]
        if loc == "SeedShop":
            log("already in SeedShop", attempt=attempt)
            return True
        rec = exec_raw(c, "move_to_location", {"location": "SeedShop"}, 90000)
        out.setdefault("goto_attempts", []).append({"attempt": attempt, "before": snap, "receipt": rec})
        log("goto SeedShop", attempt=attempt, http_ok=rec["http_ok"], code=receipt_code(rec), loc=loc)
        if rec["http_ok"]:
            time.sleep(1.0)
            if ui_snapshot(observe(c))["location"] == "SeedShop":
                return True
            continue
        # 失败：先看是不是门锁/事件
        state = wait_event_and_modal_clear(c, out, deadline)
        if state == "healed":
            heals_used += 1
            if heals_used >= SELF_HEAL_LIMIT:
                out.setdefault("notes", []).append("进店被事件反复阻断，自愈用尽")
                return False
            # 自愈 = 重读存档（回到 06:00）：等开门再试，避免又撞店门/事件时序问题
            wait_until_open(c, out, deadline)
            continue
        if state == "question":
            out.setdefault("notes", []).append("进店路径上出现提问对话（已按无参 dismiss 退出）")
            wait_modal_clear(c, rounds=2, out=out)
            continue
        if state == "deadline":
            return False
        obs = observe(c)
        snap = ui_snapshot(obs)
        if snap["location"] == "SeedShop":
            return True
        text = str((snap["ui"].get("activeMenuText") or ""))
        if "locked" in text.lower() or "9:00" in text:
            # 店门锁着：等游戏时钟到 9:00（只读等待，最多 180s）
            log("shop locked, waiting for 9:00", menu_text=text[:120])
            t0 = time.time()
            while time.time() - t0 < 180 and time.time() < deadline:
                time.sleep(5.0)
                obs2 = observe(c)
                tod = (obs2.get("clock") or {}).get("timeOfDay")
                if isinstance(tod, int) and tod >= 900:
                    break
            wait_modal_clear(c, rounds=2, out=out)
            continue
        time.sleep(2.0)
    obs = observe(c)
    return ui_snapshot(obs)["location"] == "SeedShop"


def move_adjacent(c: BridgeClient, npc_tile: list[int], out: dict) -> bool:
    """talk 回 not_adjacent 时，按 8 邻格贴近 NPC（move_to 只走可站立格）。"""
    nx, ny = int(npc_tile[0]), int(npc_tile[1])
    for dx, dy in NEIGHBOR_OFFSETS:
        tile = [nx + dx, ny + dy]
        rec = exec_raw(c, "move_to", {"tile": tile}, 30000)
        out.setdefault("adjacent_attempts", []).append({"tile": tile, "receipt": rec})
        log("move adjacent", tile=tile, http_ok=rec["http_ok"], code=receipt_code(rec))
        if rec["http_ok"]:
            time.sleep(0.8)
            return True
        out.setdefault("adjacent_snaps", []).append({"tile": tile, "snap": ui_snapshot(observe(c))})
        if receipt_code(rec) == "ui_modal":
            # 观测说"没有菜单/事件"但 move_to 仍报 ui_modal：把两条恢复车道都各试一次
            for skill, args in (("dismiss_modal", None), ("advance_dialogue", {"maxSteps": 5})):
                rec2 = exec_raw(c, skill, args, 10000)
                out.setdefault("unstick_attempts", []).append({"tile": tile, "skill": skill, "receipt": rec2})
                log("unstick try", tile=tile, skill=skill, code=receipt_code(rec2))
                time.sleep(0.5)
            rec3 = exec_raw(c, "move_to", {"tile": tile}, 30000)
            out["adjacent_attempts"].append({"tile": tile, "retry": True, "receipt": rec3})
            log("move adjacent retry", tile=tile, http_ok=rec3["http_ok"], code=receipt_code(rec3))
            if rec3["http_ok"]:
                time.sleep(0.8)
                return True
    return False


def talk_pierre(c: BridgeClient, out: dict, deadline: float) -> dict:
    """talk {"npc":"Pierre"}；not_adjacent 时先贴近再重试。返回最后一条回执。"""
    last = None
    for attempt in range(1, 7):
        if time.time() >= deadline:
            break
        # 进店/落点后事件可能延迟 1-2 秒才触发：先稳 2s 再判断
        time.sleep(2.0)
        for _ in range(12):
            snap = ui_snapshot(observe(c))
            if not (snap.get("ui") or {}).get("eventUp"):
                break
            clear_cutscene(c, out, deadline, max_s=110.0)
            time.sleep(1.0)
        wait_modal_clear(c, rounds=2, out=out)
        rec = exec_raw(c, "talk", {"npc": "Pierre"}, 20000)
        out.setdefault("talk_receipts", []).append({"attempt": attempt, "receipt": rec})
        last = rec
        code = receipt_code(rec)
        log("talk Pierre", attempt=attempt, http_ok=rec["http_ok"], code=code)
        body = rec.get("result") if rec["http_ok"] else (rec.get("payload") or {})
        if rec["http_ok"] and str((body or {}).get("code") or "") == "ok":
            return rec
        if code == "not_adjacent":
            npc_tile = (body or {}).get("npcTile")
            if isinstance(npc_tile, list) and len(npc_tile) == 2:
                before_n = len(out.get("adjacent_attempts") or [])
                ok_move = move_adjacent(c, npc_tile, out)
                tries = (out.get("adjacent_attempts") or [])[before_n:]
                if (not ok_move) and tries and all(
                        str(((t.get("receipt") or {}).get("status") or "")) == "ui_modal"
                        for t in tries):
                    clear_cutscene(c, out, deadline, max_s=110.0)
                    wait_modal_clear(c, rounds=2, out=out)
                    time.sleep(1.0)
                    move_adjacent(c, npc_tile, out)
            continue
        if code in ("npc_not_found", "not_supported", "no_action"):
            break
        if code in ("not_implemented", "unknown_skill", "skill_not_found"):
            out.setdefault("notes", []).append("桥不认识 talk：0.7.46 未装机/未生效")
            break
        time.sleep(2.0)
    return out["talk_receipts"][-1]["receipt"] if out.get("talk_receipts") else {}


def explore_dialogue(c: BridgeClient, out: dict, deadline: float, rounds: int = 8) -> list[dict]:
    """talk 成功后的对话：只记录 + advance_dialogue 推非提问；提问立即停、不选选项。"""
    snaps = []
    for i in range(1, rounds + 1):
        if time.time() >= deadline:
            break
        obs = observe(c)
        snap = ui_snapshot(obs)
        snaps.append(snap)
        out.setdefault("dialogue_snapshots", []).append({"round": i, **snap})
        ui = snap["ui"]
        log("dialogue snap", round=i, menu=ui["activeMenu"], question=ui["dialogueIsQuestion"],
            responses=len(ui["dialogueResponses"] or []))
        if ui["dialogueIsQuestion"]:
            break
        if ui["activeMenu"] != "DialogueBox" or not ui["isModal"]:
            break
        rec = exec_raw(c, "advance_dialogue", {"maxSteps": 10}, 20000)
        out.setdefault("dialogue_advance", []).append({"round": i, "receipt": rec})
        if not rec["http_ok"]:
            break
        time.sleep(1.0)
    return snaps


def teardown(c: BridgeClient | None, out: dict, minutes: float, no_stop: bool) -> None:
    out["teardown"] = {"no_stop": no_stop}
    if no_stop:
        log("teardown skipped (--no-stop)")
        return
    t0 = time.time()
    r = subprocess.run([sys.executable, "-u", os.path.join(REPO, "tools", "stop-game.py"), "--wait", "45"],
                       cwd=REPO, capture_output=True, text=True, timeout=180)
    out["teardown"]["stop_game"] = {"rc": r.returncode, "stdout_tail": (r.stdout or "")[-4000:],
                                    "stderr_tail": (r.stderr or "")[-2000:], "elapsed_s": round(time.time() - t0, 1)}
    log("stop-game", rc=r.returncode)
    time.sleep(2.0)
    deadline = time.time() + 60
    while time.time() < deadline and (bridge_info() or port_listening()):
        time.sleep(2.0)
    out["teardown"].update({
        "processes_after": process_count(),
        "bridge_json_after": bridge_info(),
        "port_17890_listening_after": port_listening(),
        "save_hashes_after": save_hashes(),
        "mod_hashes_after": mod_hashes(),
    })
    log("teardown verify", processes=out["teardown"]["processes_after"],
        bridge=out["teardown"]["bridge_json_after"] is not None,
        port=out["teardown"]["port_17890_listening_after"])


def freeze_smapi(out: dict) -> None:
    if not os.path.isfile(SMAPI_LATEST):
        out["smapi_window"] = {"path": SMAPI_COPY, "freeze": False, "reason": "SMAPI-latest.txt 不存在"}
        return
    os.makedirs(os.path.dirname(SMAPI_COPY), exist_ok=True)
    shutil.copyfile(SMAPI_LATEST, SMAPI_COPY)
    out["smapi_window"] = {"path": SMAPI_COPY, "freeze": True,
                           "source": file_info(SMAPI_LATEST), "copy": file_info(SMAPI_COPY)}
    log("SMAPI window frozen", path=SMAPI_COPY, sha256=out["smapi_window"]["copy"]["sha256"])


def git_head() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def dry_run(out: dict) -> int:
    out["mode"] = "dry-run"
    out["bridge_json"] = bridge_info()
    out["port_17890_listening"] = port_listening()
    out["processes"] = process_count()
    out["mod_hashes"] = mod_hashes()
    out["save_hashes_before"] = save_hashes()
    out["git_head"] = git_head()
    out["smapi_latest"] = file_info(SMAPI_LATEST)
    log("dry-run: 不碰桥/不碰游戏（只读环境+装机哈希+存档哈希）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="task-34 talk 原语只读探针（0.7.46）")
    ap.add_argument("--minutes", type=float, default=10.0, help="探针总时长上限（分钟，默认 10）")
    ap.add_argument("--wait-bridge", type=float, default=120.0, help="等待 bridge.json 就绪的秒数（默认 120）")
    ap.add_argument("--expect-version", default="0.7.46", help="期望 Mod 版本；不符则只记录不探针（默认 0.7.46）")
    ap.add_argument("--expect-dll-sha", default=None, help="期望装机 dll 的 SHA256；不符则只记录不探针")
    ap.add_argument("--dry-run", action="store_true", help="只读环境/装机哈希/存档哈希，不碰桥")
    ap.add_argument("--no-stop", action="store_true", help="调试：不收尾（不优雅退游戏）")
    ap.add_argument("--out", default=OUT_DEFAULT, help="证据 JSON 路径")
    args = ap.parse_args(argv)

    started = time.time()
    deadline = started + max(1.0, args.minutes) * 60.0
    out: dict = {
        "task": "task-34",
        "started_at": now_iso(),
        "python": sys.version.split()[0],
        "repo": REPO,
        "git_head": git_head(),
        "argv": sys.argv,
        "mod_hashes_before": mod_hashes(),
        "save_hashes_before": save_hashes(),
        "smapi_latest_before": file_info(SMAPI_LATEST),
        "log": LOG,
    }
    bridge = bridge_info()
    out["bridge_json_before"] = bridge

    # 只读装机断言：dll 哈希/Mod 版本不符 ⇒ 记证据、不探针
    if args.expect_dll_sha:
        got = (out["mod_hashes_before"].get("AgentFarm.Bridge.dll") or {}).get("sha256")
        if got != args.expect_dll_sha.upper():
            out["aborted"] = f"装机 dll SHA256={got} != 期望 {args.expect_dll_sha.upper()}（WIP/旧版），不探针"
            log(out["aborted"])
            _write(out, args)
            return 2
    if args.dry_run:
        rc = dry_run(out)
        _write(out, args)
        return rc
    if not bridge:
        bridge = wait_for_bridge(args.wait_bridge)
        out["bridge_json_after_wait"] = bridge
    if not bridge:
        out["aborted"] = "bridge.json 不存在：游戏未起或桥未就绪（本脚本不负责起游戏）"
        log(out["aborted"])
        _write(out, args)
        return 2
    out["mod_version"] = bridge.get("modVersion")
    log("bridge ready", modVersion=bridge.get("modVersion"), pid=bridge.get("pid"))
    if args.expect_version and str(bridge.get("modVersion") or "") != args.expect_version:
        out["aborted"] = f"桥自报 modVersion={bridge.get('modVersion')} != 期望 {args.expect_version}，不探针"
        log(out["aborted"])
        _write(out, args)
        return 2

    c = None
    try:
        c = BridgeClient()
        obs = observe(c)
        out["observe_start"] = ui_snapshot(obs)
        log("observe start", **{k: out["observe_start"][k] for k in ("location", "clock")})
        # 0) talk 原语可用性先验：当前地点（FarmHouse）没有 Pierre ⇒ 期望 npc_not_found，
        #    证明 0.7.46 装机 dll 里 talk 已注册（否则会 not_implemented/unknown_skill）。
        out["initial_talk"] = exec_raw(c, "talk", {"npc": "Pierre"}, 15000)
        log("initial talk probe", code=receipt_code(out["initial_talk"]),
            loc=out["observe_start"]["location"])
        # 1) 清模态（无参，绝不选 Yes/Purchase）
        wait_modal_clear(c, rounds=3, out=out)
        # 2) 进店
        reached = goto_seedshop(c, out, deadline)
        out["seedshop_reached"] = reached
        log("SeedShop reached", reached=reached)
        if not reached:
            out.setdefault("notes", []).append("未能进 SeedShop（事件/门锁/寻路），talk 无法验证")
        else:
            # 2.5) 进店常驻过场（如 SeedShop 开店事件）会挡住移动：先受控推进到 eventUp=false。
            #      只推非提问对话；提问立即停；超时/无变化就如实记录后继续（talk 会报 not_adjacent/ui_modal）。
            # 进店常驻过场（SeedShop 开店事件 3102768）会挡住一切移动/talk；
            # 该事件在进店后约 1-2 秒才触发 ⇒ 先稳 8s 或观察到 eventUp 再清。
            t_settle = time.time() + 8.0
            out.setdefault("shop_entry_observes", [])
            while time.time() < t_settle and time.time() < deadline:
                snap0 = ui_snapshot(observe(c))
                out["shop_entry_observes"].append({"t": now_iso(), "snap": snap0})
                if (snap0.get("ui") or {}).get("eventUp"):
                    break
                time.sleep(1.0)
            out["shop_entry_observes"].append({"t": now_iso(), "snap": ui_snapshot(observe(c))})
            clear_cutscene(c, out, deadline, max_s=120.0)
            wait_modal_clear(c, rounds=2, out=out)
            # 3) talk Pierre
            rec = talk_pierre(c, out, deadline)
            code = receipt_code(rec)
            out["talk_code"] = code
            body = rec.get("result") if rec.get("http_ok") else (rec.get("payload") or {})
            out["talk_receipt"] = rec
            # 4) 若开出了对话：只记录/推非提问；提问立即停、无参 dismiss
            if code == "ok":
                explore_dialogue(c, out, deadline)
                wait_modal_clear(c, rounds=3, out=out)
                # 退出对话后世界是否恢复（读事实，不写）
                obs2 = observe(c)
                out["observe_after"] = ui_snapshot(obs2)
                log("observe after", **{k: out["observe_after"][k] for k in ("location", "clock")})
    except BaseException as exc:  # noqa: BLE001 - 探针自身异常也必须留证据并收尾
        out["exception"] = safe_payload(exc)
        out["traceback_tail"] = traceback.format_exc()[-3000:]
        log("PROBE EXCEPTION", type=type(exc).__name__, message=str(exc)[:300])
    finally:
        out["elapsed_s"] = round(time.time() - started, 1)
        try:
            freeze_smapi(out)
        except Exception as exc:  # noqa: BLE001
            out["smapi_window"] = {"freeze": False, "error": safe_payload(exc)}
        try:
            teardown(c, out, args.minutes, args.no_stop)
        except Exception as exc:  # noqa: BLE001
            out["teardown"] = {"error": safe_payload(exc)}
        out["deadline_hit"] = time.time() >= deadline
        out["finished_at"] = now_iso()
        out["elapsed_s"] = round(time.time() - started, 1)
        # 结论字段（供人复核；不做通过/失败判定）
        bodies = out.get("talk_receipts") or []
        body = (bodies[-1].get("receipt") if bodies else {}).get("result") or {}
        out["conclusion"] = {
            "seedshop_reached": out.get("seedshop_reached"),
            "talk_http_ok": bool(bodies and bodies[-1]["receipt"].get("http_ok")),
            "talk_code": out.get("talk_code") or receipt_code(bodies[-1]["receipt"] if bodies else {}),
            "npc": body.get("npc"),
            "npc_tile": body.get("npcTile"),
            "distance": body.get("distance"),
            "active_menu": body.get("activeMenu"),
            "dialogue_is_question": body.get("dialogueIsQuestion"),
            "dialogue_responses": body.get("dialogueResponses"),
            "responses_join": " | ".join(str(x) for x in (body.get("dialogueResponses") or [])),
        }
        _write(out, args)
    return 0


def _write(out: dict, args: argparse.Namespace) -> None:
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"[evidence] {args.out}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
