# -*- coding: utf-8 -*-
"""0.7.40 冒烟现场抢救（Lead m04068 步骤 1-2）：
1) 只读确认现场 + 存档四件（size/mtime/SHA256）
2) 发**一次** dismiss_modal（okClicked() 路径）→ 最多等 10s
   → 复核 SMAPI 保存链 / 存档主档是否前进 / ui.isModal 与 worldAdvancing
只读 + 一次 dismiss_modal；不 load_save、不强杀、不退出游戏（退出由下一步单独做）。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brain")))
from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
FILES = ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
MARKERS = ("SaveGame.Save() called", "Synchronizing 'Save' task", "completed without exceptions",
           "after save, starting", "Context: before save.")


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def saves() -> dict:
    out = {}
    for f in FILES:
        p = os.path.join(SAVE_DIR, f)
        if not os.path.exists(p):
            out[f] = None
            continue
        st = os.stat(p)
        out[f] = {"size": st.st_size,
                  "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                  "sha256": sha(p)}
    return out


def smapi_lines() -> list[str]:
    return open(SMAPI, encoding="utf-8", errors="replace").read().splitlines()


def snapshot(c: BridgeClient) -> dict:
    o = c.observe(detail="summary")
    return {
        "worldSeq": o.get("worldSeq"),
        "clock": o.get("clock"),
        "player": {k: (o.get("player") or {}).get(k) for k in ("location", "tile", "stamina", "money", "isInBed")},
        "ui": {k: (o.get("ui") or {}).get(k) for k in ("activeMenu", "isModal", "eventUp", "activeMenuText",
                                                       "dialogueIsQuestion", "dialogueResponses")},
        "liveness": o.get("liveness"),
    }


def main() -> int:
    c = BridgeClient()
    print("=== 1) 只读确认（关框前）===")
    s0 = snapshot(c)
    print("observe:", json.dumps(s0, ensure_ascii=False))
    before = saves()
    for f, v in before.items():
        print(f"save {f:22} {v and (str(v['size']) + ' B / ' + v['mtime'] + ' / ' + v['sha256'][:16] + '…')}")
    lines0 = smapi_lines()
    n0 = len(lines0)
    print(f"smapi_lines={n0}")

    print("\n=== 2) 发一次 dismiss_modal（okClicked 路径）===")
    t0 = time.time()
    try:
        r = c.dismiss_modal(timeout_ms=8000)
        print(f"receipt({time.time() - t0:.1f}s): {json.dumps(r, ensure_ascii=False)[:700]}")
    except BridgeError as exc:
        # 已知形态：okClicked() 已生效但菜单要等游戏自己关 ⇒ 回执可能超时
        print(f"BridgeError({time.time() - t0:.1f}s，可能是'已 okClicked 但等游戏关框'的超时): {str(exc)[:600]}")

    print("\n=== 2) 等最多 10 秒，只在本地读文件/观测（不抢写）===")
    save_landed = False
    ui_freed = None
    deadline = time.time() + 10
    seen: list[str] = []
    while time.time() < deadline:
        new = smapi_lines()[n0:]
        hits = [ln for ln in new if any(m in ln for m in MARKERS)]
        if hits and not seen:
            seen = hits
        cur = saves()
        main_now = cur.get("Wahaha_450799035") or {}
        main_before = before.get("Wahaha_450799035") or {}
        advanced = (main_now.get("size") != main_before.get("size")
                    or main_now.get("mtime") != main_before.get("mtime"))
        print(f"  t+{time.time() - t0:4.1f}s markers={len(hits)} main={main_now.get('size')}/{main_now.get('mtime')} "
              f"advanced={advanced}")
        if advanced and len(hits) >= 3:
            save_landed = True
            break
        time.sleep(1.0)
    new = smapi_lines()[n0:]
    hits = [ln for ln in new if any(m in ln for m in MARKERS)]
    print(f"\nSMAPI 新增 {len(new)} 行，其中保存链行 {len(hits)} 条：")
    for ln in hits[:12]:
        print("   " + ln[:190])
    print("\n--- SMAPI 尾部 6 行（原文）---")
    for ln in smapi_lines()[-6:]:
        print("   " + ln[:190])

    s1 = snapshot(c)
    print("\n=== 2) 关框后现场 ===")
    print("observe:", json.dumps(s1, ensure_ascii=False))
    after = saves()
    for f, v in after.items():
        b = before.get(f) or {}
        same = (b.get("size") == v.get("size") and b.get("mtime") == v.get("mtime"))
        print(f"save {f:22} {v and (str(v['size']) + ' B / ' + v['mtime'])}  "
              f"{'未变' if same else '★已前进'} (before {b.get('size')}/{b.get('mtime')})")

    ui_freed = not (s1["ui"] or {}).get("isModal")
    wa = (s1["liveness"] or {}).get("worldAdvancing")
    print("\n=== 判定 ===")
    print(f"save_landed={save_landed}  ui.isModal→{(s1['ui'] or {}).get('isModal')} (freed={ui_freed})  "
          f"worldAdvancing={wa}  clock={json.dumps((s1['clock'] or {}), ensure_ascii=False)}")
    verdict = "SAVED_OK" if save_landed else "NOT_SAVED_YET"
    print(f"VERDICT: {verdict}")
    out = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "before": before, "after": after,
        "observe_before": s0, "observe_after": s1,
        "smapi_new_lines": len(new), "smapi_save_markers": hits,
        "save_landed": save_landed, "verdict": verdict,
    }
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "t-save-winter1.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"已写出 {p}")
    return 0 if save_landed else 10


if __name__ == "__main__":
    sys.exit(main())
