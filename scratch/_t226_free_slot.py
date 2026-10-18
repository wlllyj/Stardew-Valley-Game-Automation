# -*- coding: utf-8 -*-
"""task-226 前置：背包 12/12 满 ⇒ 买不了东西（`no_inventory_space`）。
用受制裁路径（`FarmWorker.sell` → 游戏自己的 `Farm.shipItem` 进出货箱）**只腾一格**，
物种限定为盈余材料（Moss / Stone 这类），绝不卖工具/武器/种子/建材构件。

判据（观测差分）：`player.inventory[]` 行数 12→11、`shippingBin.count` +1、money 不变。

产物：`scratch/t226-free-slot.json`
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402
from agentfarm.farmwork import FarmWorker  # noqa: E402

# 优先级：先 Moss（纯盈余、无配方依赖），再 Stone（同属盈余）。
PREFER = ["(O)Moss", "(O)390"]


def inv_rows(obs: dict) -> list[dict]:
    return [{"slot": s.get("slot"), "qid": s.get("qualifiedId") or s.get("itemId"),
             "stack": s.get("stack"), "name": s.get("name")}
            for s in ((obs.get("player") or {}).get("inventory") or [])]


def main() -> int:
    c = BridgeClient(timeout=20.0)
    w = FarmWorker(c)
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "prefer": PREFER}
    obs0 = c.observe("full")
    rows0 = inv_rows(obs0)
    out["rows_before"] = rows0
    out["rows_before_count"] = len(rows0)
    out["money_before"] = (obs0.get("player") or {}).get("money")
    out["shipping_bin_before"] = obs0.get("shippingBin")
    print(f"rows={len(rows0)} money={out['money_before']} shippingBin={out['shipping_bin_before']}")
    for r in rows0:
        print(f"   slot {r['slot']:>2}  {str(r['qid']):16} x{r['stack']:<4} {r['name']}")

    target = None
    for qid in PREFER:
        for r in rows0:
            if str(r["qid"]) == qid:
                target = r
                break
        if target:
            break
    if target is None:
        print("!! 没找到可卖的盈余材料 → 停手")
        out["verdict"] = "NO_SURPLUS_FOUND"
        (REPO / "scratch" / "t226-free-slot.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2
    out["target"] = target
    print(f"\n[腾格] FarmWorker.sell(slot={target['slot']}, whitelist=[{target['qid']!r}])")
    r = w.sell(target["slot"], whitelist=[target["qid"]])
    out["sell_result"] = {"ok": r.ok, "code": r.code, "reason": str(r.reason)[:400],
                          "receipt": getattr(r, "receipt", None)}
    print(f"  ok={r.ok} code={r.code} reason={str(r.reason)[:300]}")

    obs1 = c.observe("full")
    rows1 = inv_rows(obs1)
    out["rows_after"] = rows1
    out["rows_after_count"] = len(rows1)
    out["money_after"] = (obs1.get("player") or {}).get("money")
    out["shipping_bin_after"] = obs1.get("shippingBin")
    freed = len(rows1) < len(rows0)
    out["freed"] = freed
    out["verdict"] = "FREED_ONE_SLOT" if freed else "FAIL_NOT_FREED"
    print(f"rows {len(rows0)}→{len(rows1)} money {out['money_before']}→{out['money_after']} "
          f"shippingBin {out['shipping_bin_before']}→{out['shipping_bin_after']}")
    print(f"verdict={out['verdict']}")
    (REPO / "scratch" / "t226-free-slot.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if freed else 1


if __name__ == "__main__":
    raise SystemExit(main())
