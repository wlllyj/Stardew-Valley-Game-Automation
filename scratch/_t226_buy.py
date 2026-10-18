# -*- coding: utf-8 -*-
"""task-226 步骤 2：走游戏自己的商店链**只买 1 个铜矿**（(O)378，Blacksmith 75g）。

纪律
- 只允许**一次成功交易**；探测 shopId 用 `item_not_sold`/`shop_unavailable` 的失败回执（不成交）。
- 判据一律**观测差分**（回执只作诊断）：money 应 −75、背包 `(O)378` 应 +1、其它槽位不动。
- 买完把可能残留的 ShopMenu 收掉（它不是事件，只是我开的店），否则下一步走不动。

产物：`scratch/t226-buy.json`
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

SAVE_DIR = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"
SMAPI = Path(os.environ["APPDATA"]) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
ORE_QID = "(O)378"
SHOPS = ["Blacksmith", "Clint"]
REAL_LINE = re.compile(r"^\[\d{2}:\d{2}:\d{2} [A-Z]+ [^\]]+\]")


def save_sig() -> list[dict]:
    out = []
    for name in ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old"):
        p = SAVE_DIR / name
        try:
            st = p.stat()
        except OSError:
            out.append({"name": name, "size": None, "mtime": None})
            continue
        out.append({"name": name, "size": st.st_size,
                    "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime))})
    return out


def smapi_counts() -> dict:
    if not SMAPI.exists():
        return {"error": "SMAPI-latest.txt 不存在"}
    text = SMAPI.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    def real(pat: str) -> list[int]:
        hits = []
        for i, ln in enumerate(lines, 1):
            if pat in ln and REAL_LINE.match(ln) and " by AgentFarm " not in ln and "| v0." not in ln:
                hits.append(i)
        return hits

    return {"lines": len(lines),
            "newday": real("Synchronizing 'NewDay' task"),
            "before_save": real("Context: before save."),
            "save_called": real("SaveGame.Save() called."),
            "save_task": real("Synchronizing 'Save' task"),
            "save_completed": real("completed without exceptions")}


def inv_map(obs: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in ((obs.get("player") or {}).get("inventory") or []):
        q = s.get("qualifiedId") or s.get("itemId")
        if q:
            out[str(q)] = out.get(str(q), 0) + int(s.get("stack") or 0)
    return out


def brief(obs: dict) -> dict:
    c = obs.get("clock") or {}
    p = obs.get("player") or {}
    ui = obs.get("ui") or {}
    return {"clock": c, "money": p.get("money"), "stamina": p.get("stamina"),
            "location": p.get("location"), "tile": p.get("tile"),
            "inv_rows": len((p.get("inventory") or [])),
            "activeMenu": ui.get("activeMenu"), "isModal": ui.get("isModal"),
            "eventUp": ui.get("eventUp"), "worldSeq": obs.get("worldSeq")}


def close_menu(c: BridgeClient) -> dict:
    obs = c.observe("summary")
    ui = obs.get("ui") or {}
    if not ui.get("isModal") and ui.get("activeMenu") is None:
        return {"closed": False, "ui": ui}
    r = c.dismiss_modal()
    obs2 = c.observe("summary")
    return {"closed": True, "receipt": r, "ui_after": obs2.get("ui")}


def main() -> int:
    c = BridgeClient(timeout=20.0)
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "ore_qid": ORE_QID,
                 "shops_tried": [], "attempts": []}
    h = c.health()
    out["health"] = {k: h.get(k) for k in ("ok", "status", "modVersion", "schema")}
    obs0 = c.observe("full")
    out["before"] = brief(obs0)
    out["inv_before"] = inv_map(obs0)
    out["save_before"] = save_sig()
    out["smapi_before"] = smapi_counts()
    print(f"before: money={out['before']['money']} inv_rows={out['before']['inv_rows']} "
          f"ore={out['inv_before'].get(ORE_QID, 0)} clock={out['before']['clock']}")
    ui0 = obs0.get("ui") or {}
    if ui0.get("eventUp"):
        print("!! 当前 eventUp=true（事件进行中）—— 按纪律不再发任何请求，停手")
        out["aborted"] = "eventUp_before_buy"
        (REPO / "scratch" / "t226-buy.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return 4
    if ui0.get("isModal"):
        print(f"!! 买前有模态 activeMenu={ui0.get('activeMenu')} ⇒ 先收掉（不是事件）")
        out["pre_menu"] = close_menu(c)

    ok_shop = None
    for shop in SHOPS:
        out["shops_tried"].append(shop)
        att: dict = {"shop": shop, "at": time.strftime("%H:%M:%S")}
        t0 = time.time()
        try:
            res = c.buy(ORE_QID, 1, shop=shop, timeout_ms=25000)
            att["result"] = "returned"; att["receipt"] = res
            print(f"[{shop}] 返回：{json.dumps(res, ensure_ascii=False)[:400]}")
        except BridgeError as exc:
            att["result"] = "BridgeError"; att["status"] = exc.status
            att["reason"] = (exc.reason or "")[:300]
            att["payload"] = exc.payload if isinstance(exc.payload, dict) else str(exc.payload)[:300]
            print(f"[{shop}] BridgeError status={exc.status} reason={(exc.reason or '')[:200]}")
        att["elapsed_s"] = round(time.time() - t0, 2)
        att["smapi_after_attempt"] = smapi_counts()
        obs1 = c.observe("full")
        att["after_attempt"] = brief(obs1)
        att["money_delta"] = (obs1.get("player") or {}).get("money", 0) - (obs0.get("player") or {}).get("money", 0)
        out["attempts"].append(att)
        if att["money_delta"] != 0:
            ok_shop = shop
            break
        if att.get("status") not in ("item_not_sold", "shop_unavailable", "shop_timeout", None):
            print(f"!! 失败状态 {att.get('status')} 不是探测型失败 ⇒ 停手")
            break
        print(f"[{shop}] 未成交（探测型失败），继续下一个候选 shopId")

    obs2 = c.observe("full")
    out["after"] = brief(obs2)
    out["inv_after"] = inv_map(obs2)
    out["save_after"] = save_sig()
    out["smapi_after"] = smapi_counts()
    out["menu_after"] = close_menu(c)
    obs3 = c.observe("full")
    out["final"] = brief(obs3)
    out["inv_final"] = inv_map(obs3)

    inv_diff = {q: out["inv_final"].get(q, 0) - out["inv_before"].get(q, 0)
                for q in set(out["inv_before"]) | set(out["inv_final"])
                if out["inv_final"].get(q, 0) - out["inv_before"].get(q, 0) != 0}
    money_delta = (out["final"].get("money") or 0) - (out["before"].get("money") or 0)
    out["money_delta_total"] = money_delta
    out["inv_diff_total"] = inv_diff
    bought = inv_diff.get(ORE_QID, 0) == 1 and money_delta == -75
    out["verdict"] = ("PASS_BUY_ONE_ORE" if bought else
                      ("FAIL_DELTA" if money_delta != 0 or inv_diff else "FAIL_NOT_PURCHASED"))
    out["shop_used"] = ok_shop
    path = REPO / "scratch" / "t226-buy.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nafter : money={out['final'].get('money')} ore={out['inv_final'].get(ORE_QID, 0)} "
          f"money_delta={money_delta} inv_diff={inv_diff}")
    print(f"shop_used={ok_shop} verdict={out['verdict']} -> {path}")
    return 0 if bought else 1


if __name__ == "__main__":
    raise SystemExit(main())
