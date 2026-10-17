# -*- coding: utf-8 -*-
"""task-209 §1 v2：Clint 两店的只读货架 dump（修正三个坑）。

v1 踩到的坑（真机实测）：
1. `buy` 失败时**抛 BridgeError**，原始回执在 `exc.payload`（`available` 在这里），不在返回值里；
2. 失败后 **ShopMenu 会留在打开状态**（`ui.activeMenu="ShopMenu"`），而 `buy` 遇到已开的 ShopMenu 会**复用它**
   ⇒ 第二次 dump `ClintUpgrade` 实际读的是 Blacksmith 的货架（v1 两店清单完全相同就是证据）；
3. 所以每次 dump 前必须确认"没有任何模态"，dump 后立即 `dismiss_modal` 收店。

安全：探测商品用 `472`（Parsley/Parsnip Seeds，两店都不卖）⇒ 只走 `item_not_sold` 提前返回，
**不会**进 `tryToPurchaseItem`。每次前后断言 money/inventory 未变。
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

SLUG = {"Blacksmith": "blacksmith", "ClintUpgrade": "upgrade"}


def snap(c: BridgeClient) -> dict:
    o = c.observe("summary")
    p = o.get("player") or {}
    ui = o.get("ui") or {}
    inv = p.get("inventory") or []
    return {"at": time.strftime("%H:%M:%S"), "clock": o.get("clock"), "worldSeq": o.get("worldSeq"),
            "money": p.get("money"), "stamina": p.get("stamina"), "inv_rows": len(inv),
            "inv": [{"slot": s.get("slot"), "qid": s.get("qualifiedId"), "stack": s.get("stack")} for s in inv],
            "activeMenu": ui.get("activeMenu"), "isModal": ui.get("isModal")}


def close_any_menu(c: BridgeClient, tag: str) -> dict:
    s = snap(c)
    if s["activeMenu"] is None and not s["isModal"]:
        return s
    print(f"  [close] {tag}: 当前 activeMenu={s['activeMenu']} isModal={s['isModal']} ⇒ dismiss_modal")
    try:
        r = c.dismiss_modal()
        print(f"  [close] 回执 status={r.get('status')} ok={r.get('ok')} reason={(r.get('reason') or '')[:200]}")
    except BridgeError as exc:
        print(f"  [close] dismiss_modal 失败：{exc}  payload={(exc.payload or {}).get('status')}")
    return snap(c)


def main() -> int:
    shops = sys.argv[1].split(",") if len(sys.argv) > 1 else ["Blacksmith", "ClintUpgrade"]
    probe = sys.argv[2] if len(sys.argv) > 2 else "472"
    c = BridgeClient()
    os.makedirs(os.path.join(REPO, "scratch"), exist_ok=True)
    summary = []
    for shop in [s.strip() for s in shops if s.strip()]:
        print(f"\n{'='*74}\n[shop] {shop}  probe={probe}（绝不成交）")
        before = close_any_menu(c, "dump 前")
        print(f"before: money={before['money']} inv_rows={before['inv_rows']} activeMenu={before['activeMenu']} "
              f"clock={before['clock']} worldSeq={before['worldSeq']}")
        t0 = time.time()
        payload = None
        err = None
        try:
            res = c.buy(probe, 1, shop=shop, timeout_ms=25000)
            payload = dict(res or {})
            print(f"返回值（意外：本应失败）：{json.dumps(res, ensure_ascii=False)[:300]}")
        except BridgeError as exc:
            payload = dict(exc.payload or {})
            payload.setdefault("status", exc.status)
            payload.setdefault("reason", exc.reason)
            err = f"{exc.status}: {exc.reason[:200]}"
            print(f"BridgeError status={exc.status} reason={exc.reason[:300]}")
        elapsed = round(time.time() - t0, 2)
        after = close_any_menu(c, "dump 后")
        print(f"after : money={after['money']} inv_rows={after['inv_rows']} activeMenu={after['activeMenu']} ({elapsed}s)")
        avail = payload.get("available")
        if isinstance(avail, list):
            print(f"available: {len(avail)} 条（价格升序、最多 30）")
            for row in avail:
                print(f"   {str(row.get('id')):16} {str(row.get('name'))[:36]:36} {row.get('price')}g")
        else:
            print(f"available: 缺失 —— 回执键 = {sorted(payload.keys())}")
        money_changed = before["money"] != after["money"]
        inv_changed = before["inv"] != after["inv"]
        if money_changed or inv_changed:
            print(f"!!! ALERT 世界被改：money_changed={money_changed} inv_changed={inv_changed}")
        out = {
            "shop": shop, "probe_item": probe, "probe_item_meaning": "472 = Parsnip Seeds，绝不在这两个店里",
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "elapsed_s": elapsed,
            "shelf_row_cap": 30, "shelf_sorted_by": "price asc（Mod Shelf() 既有行为）",
            "receipt_payload": payload, "available": avail, "bridge_error": err,
            "before": before, "after": after, "world_unchanged": not (money_changed or inv_changed),
        }
        path = os.path.join(REPO, "scratch", f"t210-{SLUG.get(shop, shop.lower())}-stock.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print(f"已写出 {path}（{os.path.getsize(path)} B）")
        summary.append({"shop": shop, "rows": len(avail) if isinstance(avail, list) else None,
                        "money_changed": money_changed, "inv_changed": inv_changed})
        if money_changed or inv_changed:
            print("!! 停手：世界被改")
            return 3
        time.sleep(0.5)
    print(f"\n{'='*74}\n汇总：{json.dumps(summary, ensure_ascii=False)}")
    ok = all(r["rows"] for r in summary) and not any(r["money_changed"] or r["inv_changed"] for r in summary)
    print(f"VERDICT: {'两店货架都 dump 到、世界未变' if ok else '有店货架为空/缺失（见上）'}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
