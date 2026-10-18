# -*- coding: utf-8 -*-
"""task-226 触发环节摘要：读 scratch/t226-trigger.json + SMAPI 窗口 + 存档四条，打印证据要点。"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
J = REPO / "scratch" / "t226-trigger.json"
SMAPI = Path(os.environ["APPDATA"]) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
SAVE = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"

d = json.loads(J.read_text(encoding="utf-8"))
print("verdict           :", d.get("verdict"))
print("seen_event/cleared:", d.get("seen_event"), "/", d.get("event_cleared"), "blocked=", d.get("blocked"))
print("start             :", json.dumps(d.get("start"), ensure_ascii=False))
print("after_menus       :", json.dumps(d.get("after_menus"), ensure_ascii=False))
print("menus_closed      :")
for m in d.get("menus_closed") or []:
    r = m.get("receipt") or {}
    print(f"   {m.get('at')} menu={m.get('menu')} ok={r.get('ok')} status={r.get('status')} "
          f"reason={(r.get('reason') or '')[:140]} err={m.get('error')}")
print("save_landed       :", d.get("save_landed"), "save_before=", d.get("save_before"),
      "after_sleep=", d.get("save_after_sleep"), "after_event=", d.get("save_after_event"))
print("move              :", json.dumps(d.get("move"), ensure_ascii=False))
print("after_event       :", json.dumps(d.get("after_event"), ensure_ascii=False))
for k in ("smapi_before", "smapi_after_land", "smapi_after_event"):
    ch = d.get(k) or {}
    print(f"{k:18}: lines={ch.get('lines')} newday={len(ch.get('newday') or [])} "
          f"before_save={len(ch.get('before_save') or [])} save_called={len(ch.get('save_called') or [])} "
          f"after_save={len(ch.get('after_save') or [])}")
obs = d.get("observations") or []
print(f"observations      : {len(obs)}；首 {json.dumps(obs[0], ensure_ascii=False)[:200] if obs else None}")
print(f"末 {json.dumps(obs[-1], ensure_ascii=False)[:200] if obs else None}")
print("\n=== 存档四条 ===")
for name in ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old"):
    p = SAVE / name
    try:
        st = p.stat()
    except OSError:
        print(f"  {name}: (缺失)")
        continue
    import time as _t
    print(f"  {name}: {st.st_size} B / {_t.strftime('%Y-%m-%d %H:%M:%S', _t.localtime(st.st_mtime))}.{st.st_mtime % 1:.3f}")

print("\n=== SMAPI 本次窗口关键行（01:4x 之后）===")
pat = re.compile(r"^\[(0[1-9]|1[0-9]):(\d{2}):(\d{2}) ")
keep = ("Synchronizing 'NewDay'", "Context: before save.", "SaveGame.Save() called",
        "Synchronizing 'Save' task", "completed without exceptions", "after save, starting",
        "Event", "event", "anEvent", "Disconnected", "Exception")
lines = SMAPI.read_text(encoding="utf-8", errors="replace").splitlines()
shown = 0
for i, ln in enumerate(lines, 1):
    if not pat.match(ln):
        continue
    if not any(k in ln for k in keep):
        continue
    if " by AgentFarm " in ln or "| v0." in ln:
        continue
    print(f"  L{i}: {ln[:180]}")
    shown += 1
    if shown >= 40:
        break
print(f"(共 {shown} 行，SMAPI 总 {len(lines)} 行)")
