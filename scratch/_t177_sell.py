# -*- coding: utf-8 -*-
"""task-177 step2: free exactly ONE inventory slot via the sanctioned shipping-bin path.

Uses FarmWorker.sell(slot, whitelist=[qid]) -- Farm.shipItem, money settles next NewDay.
Whitelist limited to surplus materials (never tools/weapons/seeds/building mats).
Read-only apart from that single sanctioned sell. Prints before/after evidence.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402
from agentfarm.farmwork import FarmWorker  # noqa: E402

# surplus materials only (task-24/42 sanctioned shipping whitelist style)
CANDIDATES = ["(O)Moss", "(O)390", "(O)388", "(O)771", "(O)382", "(O)330"]
SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")


def jprint(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def stat_of(name):
    p = os.path.join(SAVE_DIR, name)
    try:
        st = os.stat(p)
    except OSError as exc:
        return {"name": name, "error": type(exc).__name__}
    return {"name": name, "size": st.st_size,
            "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds")}


def shipbin(obs):
    for holder in (obs.get("shippingBin"), (obs.get("location") or {}).get("shippingBin"),
                   (obs.get("location") or {}).get("farm", {}).get("shippingBin") if isinstance((obs.get("location") or {}).get("farm"), dict) else None):
        if isinstance(holder, dict):
            items = holder.get("items")
            return {"found_at": "top/location/farm", "keys": sorted(holder.keys()),
                    "items": len(items) if isinstance(items, list) else items}
    return {"found_at": None}


def inv_summary(pl):
    inv = pl.get("inventory") or []
    rows = [{"slot": it.get("slot"), "qid": it.get("qualifiedId"), "name": it.get("name"),
             "stack": it.get("stack")} for it in inv if isinstance(it, dict)]
    return {"inventoryCount": pl.get("inventoryCount"), "slots": len(inv), "rows": rows}


def main() -> int:
    c = BridgeClient()
    w = FarmWorker(c, log=lambda *_: None)
    print("=== [0] before ===")
    obs0 = c.observe("full")
    pl0 = obs0.get("player") or {}
    s0 = inv_summary(pl0)
    print(f"money={pl0.get('money')} inventoryCount={s0['inventoryCount']}")
    for r in s0["rows"]:
        print(f"  slot={r['slot']} qid={r['qid']!r} name={r['name']!r} stack={r['stack']}")
    print(f"shippingBin before: {jprint(shipbin(obs0))}")

    # pick the largest-stack surplus candidate
    best = None
    for it in pl0.get("inventory") or []:
        if not isinstance(it, dict):
            continue
        qid = str(it.get("qualifiedId") or "")
        if qid in CANDIDATES:
            stack = int(it.get("stack") or 0)
            if best is None or stack > best[1]:
                best = (it, stack, qid)
    if best is None:
        print("!! no whitelisted surplus material in inventory -> cannot free a slot")
        return 4
    item, stack, qid = best
    slot = w._slot_of(item)
    if slot is None:
        print("!! cannot resolve slot index for the chosen item")
        return 4
    print(f"\n=== [1] chosen: qid={qid} name={item.get('name')!r} stack={stack} slot={slot} (ONE slot only) ===")

    r = w.sell(slot, whitelist=[qid], timeout_ms=8000)
    print(f"StepResult: ok={r.ok} code={r.code} status={r.status!r}")
    print(f"reason = {r.reason}")
    print(f"receipt = {r.receipt}")
    print(f"before = {jprint(r.before)}")
    print(f"after  = {jprint(r.after)}")

    obs1 = c.observe("full")
    pl1 = obs1.get("player") or {}
    s1 = inv_summary(pl1)
    print(f"\n=== [2] after ===")
    print(f"money={pl1.get('money')} inventoryCount={s1['inventoryCount']} (was {s0['inventoryCount']})")
    for row in s1["rows"]:
        print(f"  slot={row['slot']} qid={row['qid']!r} name={row['name']!r} stack={row['stack']}")
    print(f"shippingBin after : {jprint(shipbin(obs1))}")
    print(f"\nsaves: {jprint([stat_of(n) for n in ('Wahaha_450799035', 'SaveGameInfo')])}")
    # NOTE 0.7.34 finding: player.inventoryCount is the CAPACITY (12), NOT the occupied-slot count.
    # Proof: after shipping the whole Moss stack (slot 10 emptied, 11 rows left) it still reads 12.
    occupied0, occupied1 = len(s0["rows"]), len(s1["rows"])
    freed = occupied0 - occupied1
    print(f"\nNOTE: player.inventoryCount {s0['inventoryCount']}->{s1['inventoryCount']} "
          f"(CAPACITY field, not occupancy)")
    print(f"VERDICT: occupied slots {occupied0}->{occupied1} (freed {freed}); r.ok={r.ok}; "
          f"money {pl0.get('money')}->{pl1.get('money')} (settles next NewDay)")
    return 0 if (r.ok and freed >= 1) else 5


if __name__ == "__main__":
    sys.exit(main())
