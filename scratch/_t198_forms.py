# -*- coding: utf-8 -*-
"""task-198 日级形态探针 v2：打印 slot_relief 事件与 stage 账本原文。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))
sys.path.insert(0, str(REPO / "tests"))

import test_longrun as T  # noqa: E402


class LootClient(T.FakeClient):
    def __init__(self, world):
        super().__init__(world)
        self.sell_rows = []

    def sell(self, slot, *, whitelist=None, timeout_ms=8000):
        row = next((r for r in self.w.inventory
                    if int(r.get("slot") or 0) == int(slot)), None)
        allow = list(whitelist or [])
        if row is None or (allow and str(row.get("qualifiedId")) not in allow):
            return {"ok": False, "status": "not_whitelisted", "reason": "假世界：不在白名单"}
        self.w.inventory.remove(row)
        self.sell_rows.append(str(row.get("qualifiedId")))
        return {"ok": True, "status": "ok", "reason": "假出货"}


def world(*, rows: int, ripe: int, loot: int) -> T.FakeWorld:
    w = T.FakeWorld(seeds=0, money=0, weeds=0)
    tiles = [(60 + i, 10) for i in range(ripe)]
    w.dirt = set(tiles)
    w.crops = {t: {"ripe": True, "watered": True} for t in tiles}
    inv = [{"slot": 0, "id": "Axe", "qualifiedId": "(T)Axe", "name": "Axe",
            "stack": 1, "isTool": True},
           {"slot": 1, "id": "Hoe", "qualifiedId": "(T)Hoe", "name": "Hoe",
            "stack": 1, "isTool": True}]
    for _ in range(loot):
        inv.append({"slot": len(inv), "id": "24", "qualifiedId": "(O)24",
                    "name": "Parsnip", "stack": 1, "isTool": False})
    while len(inv) < rows:
        inv.append({"slot": len(inv), "id": "388", "qualifiedId": "(O)388",
                    "name": "Wood", "stack": 99, "isTool": False})
    w.inventory = inv[:rows]
    return w


def run_day(label: str, w: T.FakeWorld, *, loot: int) -> None:
    run = T.make_run(w)
    client = LootClient(w)
    # run() 会用工厂重建 client/worker ⇒ 必须改工厂，不能只赋属性
    run.client_factory = lambda: client
    run.worker_factory = lambda c: T.FarmWorker(c, log=lambda *_: None, pause=lambda *_: None)
    if loot:
        run.worker_factory = (lambda c, _n=loot: (lambda wk: (setattr(wk, "harvested", {"(O)24": _n}), wk)[1])(
            T.FarmWorker(c, log=lambda *_: None, pause=lambda *_: None)))
    print(f"--- {label}: rows_before={len(w.inventory)}")
    run.run()
    rep = run.days[0] if run.days else None
    print(f"  ended_by={rep.ended_by!r} verified={rep.verified} failed_steps={rep.failed_steps} ok_steps={rep.ok_steps}")
    print(f"  reason={rep.ended_reason!r}")
    print(f"  rows_after={len(w.inventory)} sell_rows={client.sell_rows}")
    for st in rep.stages:
        print(f"  stage {st.get('stage')}: ok={st.get('ok')} failed={st.get('failed')} "
              f"env={st.get('env_block')} leftover={st.get('leftover')} stopped={st.get('stopped')!r} "
              f"assigned_undone={st.get('assigned_undone')}")
    for e in run.entries:
        if e["event"] in ("slot_relief", "inventory_blocked"):
            print("  ev", e["event"], json.dumps({k: v for k, v in e.items() if k != "event"}, ensure_ascii=False))
    print(f"  crops_left={len(w.crops)}")


def main() -> None:
    run_day("A 满包+8熟+腾不出", world(rows=12, ripe=8, loot=0), loot=0)
    run_day("B 满包+8熟+可腾(3)", world(rows=12, ripe=8, loot=3), loot=3)
    run_day("C 满包+8熟+可腾(8)", world(rows=12, ripe=8, loot=8), loot=8)
    run_day("D 1空格+8熟+可腾(8)", world(rows=11, ripe=8, loot=8), loot=8)
    run_day("E 1空格+1熟+可腾(1)", world(rows=11, ripe=1, loot=1), loot=1)


if __name__ == "__main__":
    main()
