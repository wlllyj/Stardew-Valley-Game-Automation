# -*- coding: utf-8 -*-
"""task-24：smoke-0745 细节证据（day_end 字段、slot_relief/loot/stage_midway 行号与原文、already 坐标）。"""
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "logs" / "longrun-smoke-0745.jsonl"
spec = importlib.util.spec_from_file_location("an", str(REPO / "tools" / "analyze-longrun.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

raw = {}
for i, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
    if line.strip():
        raw[i] = json.loads(line)

# 1) day_end 关键字段
for ln in (231, 647):
    ev = raw[ln]
    keys = ("pending_ledger", "pending_guard", "pending_stalled", "pending_executable",
            "pending_blocked", "pending_unobserved", "pending_malformed",
            "free_slots_start", "free_slots_last", "free_slots_min", "free_slots_status",
            "loot_lost_steps", "loot_lost_items", "plot_pending", "plot_pending_executable",
            "plot_pending_blocked", "verified", "ended_by", "ended_reason")
    print(f"\n===== day_end L{ln} =====")
    for k in keys:
        print(f"  {k} = {json.dumps(ev.get(k), ensure_ascii=False)}")
    print("  checks =", json.dumps(ev.get("checks"), ensure_ascii=False))
    print("  stage_midway_leftover =", json.dumps(ev.get("stage_midway_leftover"), ensure_ascii=False))
    print("  loot_lost_tiles[:8] =", json.dumps((ev.get("loot_lost_tiles") or [])[:8], ensure_ascii=False))
    print("  stages n =", len(ev.get("stages") or []))
    print("  outcomes n =", len(ev.get("outcomes") or []))

# 2) 关键事件原文
print("\n===== slot_relief / inventory_blocked / no_progress_burst / stage_midway / plot_exhausted 尾部 =====")
want = {"slot_relief", "slot_relief_noted", "inventory_blocked", "no_progress_burst",
        "stage_midway_leftover", "plots_capped", "plot_exhausted", "resume_walk"}
shown = 0
for ln, ev in raw.items():
    if ev.get("event") in want:
        txt = json.dumps(ev, ensure_ascii=False)
        if len(txt) > 420:
            txt = txt[:420] + " …"
        print(f"L{ln} {ev.get('event')}: {txt}")
        shown += 1
print("shown:", shown)

# 3) 每天 stage 汇总（exec/blocked/ok/already/leftover 合计与末轮）
print("\n===== stages 汇总 =====")
for ln in (231, 647):
    ev = raw[ln]
    st = ev.get("stages") or []
    print(f"L{ln}: stages={len(st)}")
    for i, s in enumerate(st):
        if i < 3 or i >= len(st) - 2:
            print(f"  [{i}] stage={s.get('stage')} tiles={s.get('tiles')} ok={s.get('ok')} "
                  f"already={s.get('already')} leftover={s.get('leftover')} "
                  f"exec={s.get('leftover_executable')} blocked={s.get('leftover_blocked')} "
                  f"alloc_capped={s.get('alloc_capped_tiles')} stopped={s.get('stopped')!r} "
                  f"assigned={s.get('assigned')} undone={s.get('assigned_undone')}")
        elif i == 3:
            print("  …")
    tot_exec = sum(int(s.get("leftover_executable") or 0) for s in st)
    tot_blk = sum(int(s.get("leftover_blocked") or 0) for s in st)
    tot_ok = sum(int(s.get("ok") or 0) for s in st)
    tot_alr = sum(int(s.get("already") or 0) for s in st)
    ok0al = [s for s in st if int(s.get("ok") or 0) == 0 and int(s.get("already") or 0) > 0]
    print(f"  totals: ok={tot_ok} already={tot_alr} exec={tot_exec} blocked={tot_blk} "
          f"ok0_already={len(ok0al)}")
    print("  ok0al names/coords:", [(s.get("stage"), s.get("already_tiles")) for s in ok0al])

# 4) loot / pressure 行号
print("\n===== 背包/压力行号 =====")
for ln, ev in raw.items():
    if ev.get("event") == "slot_relief":
        print(f"L{ln}: pressure={ev.get('pressure')} need={ev.get('need')} freed={ev.get('freed')} "
              f"trigger={ev.get('trigger')!r} demand_basis={ev.get('demand_basis')!r} "
              f"note={str(ev.get('note'))[:120]}")
