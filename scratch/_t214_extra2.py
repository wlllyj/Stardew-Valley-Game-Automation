# -*- coding: utf-8 -*-
"""task-214 补充取证（只读，第二轮）：邮件里有没有授予 Furnace 配方的入口、object 13 是不是 Furnace、
以及 trigger_actions 为什么取不到（把支持的/不支持的表都记下来）。

不写世界、不调写技能。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402


def main() -> int:
    c = BridgeClient()
    out: dict = {}

    # ① mail 全表：找 value 里含 Furnace / recipe 的邮件
    r = c.debug_dump("mail", limit=2000, timeout_ms=60000)
    (REPO / "scratch" / "run10f-mail-full.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    hits = []
    for row in (r.get("entries") or []):
        if isinstance(row, list) and len(row) >= 2:
            k, v = str(row[0]), str(row[1])
            if "Furnace" in v or "furnace" in v or "%item recipe" in v or "recipe" in v.lower():
                hits.append({"id": k, "excerpt": v[:300]})
    out["mail_total"] = r.get("count")
    out["mail_recipe_hits"] = hits
    print(f"[1] mail 共 {r.get('count')} 条；含 Furnace/recipe 关键字 {len(hits)} 条：")
    for h in hits[:12]:
        print(f"    {h['id']:20} {h['excerpt'][:160]}")

    # ② object id 13 是什么（确认 Furnace 的 result id 映射）
    for table, key in (("big_craftables", "13"), ("objects", "13")):
        try:
            rr = c.debug_dump(table, key=key, timeout_ms=30000)
            val = (rr.get("matched") or [None])[0]
            out[f"{table}_13"] = val
            print(f"[2] {table} key=13 -> {str(val)[:200]}")
        except BridgeError as exc:
            out[f"{table}_13_error"] = f"{exc.status}: {str(exc)[:200]}"
            print(f"[2] {table} key=13 失败：{exc.status}: {str(exc)[:200]}")

    # ③ trigger_actions 失败原文（复现一遍，留档）
    try:
        c.debug_dump("trigger_actions", timeout_ms=60000)
        out["trigger_actions"] = "ok(未预期)"
    except BridgeError as exc:
        out["trigger_actions_error"] = f"{exc.status}: {str(exc)[:500]}"
        print(f"[3] trigger_actions 仍失败：{exc.status}: {str(exc)[:300]}")

    # ④ 支持的表清单（从 table_unknown 的 reason 抄出来，不是猜的）
    try:
        c.debug_dump("__list__", timeout_ms=15000)
    except BridgeError as exc:
        out["supported_tables_reason"] = str(exc)[:400]
        print(f"[4] 支持表清单（来自 reason）：{str(exc)[:260]}")

    p = REPO / "logs" / "run10f-extra2.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写 {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
