r"""task-77 对抗实验 B：伪造账本打 `encircled` 的洗白通道（只写 scratch/，工具只读）。

用法：$env:PYTHONUTF8="1"; python scratch\_t77_forge.py
工具 = `scratch\_t77_snap\tools\verify-run3.py`（干净快照 8ceea87 = task-75 的版本）。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SNAP = os.path.join(HERE, "_t77_snap")
TOOL = os.path.join(SNAP, "tools", "verify-run3.py")
PY = sys.executable


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


F = _load("t54f", os.path.join(HERE, "_t54_forge.py"))

OUT = os.path.join(HERE)


def write(tag: str, day: list[dict], de: dict, days: int = 1) -> str:
    de["t"] = 2400.0
    path = os.path.join(OUT, f"review-t77-{tag}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in day:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.write(json.dumps(F.finish_line(days), ensure_ascii=False) + "\n")
    return path


def enc_events(n: int, *, stage: str = "clear_dead", x0: int = 30, y0: int = 20) -> list[dict]:
    return [{"event": "encircled", "t": 2000.0 + i, "action": "clear", "stage": stage,
             "tile": [x0 + i, y0], "zone": "field", "reason": "四邻被不可清障物占住",
             "note": "被围住：不算走不到、不封格、不进豁免"} for i in range(n)]


def day_one(day: list[dict]) -> list[dict]:
    return [copy.deepcopy(r) for r in F.body(day)]


# ------------------------------------------------------------------ V1 / V1'
def v1(with_field: bool) -> str:
    """(B5) encircled 很大 + unreachable=0 + 当天 0 动作 + verified=true + no_work 收工。"""
    day, ds, de = F.base_day()
    day = day_one(day)
    c = F.coords(5)
    de.update({"verified": True, "ok_steps": 0, "failed_steps": 0, "skipped_steps": 0,
               "stages": [], "ended_by": "sleep",
               "ended_reason": "no_work:确实找不到可做的活（地里的活干完了）",
               "checks": F.all_true_checks(),
               "unreachable": 0, "unreachable_tiles": [], "unreachable_bound": 5,
               "unreachable_exempt": 0, "refused": 0, "refused_tiles": [],
               "refused_bound": 5, "refused_exempt": 0})
    if with_field:
        de["encircled"] = 5
        de["encircled_tiles"] = c
        day += enc_events(5)
    day.append(de)
    return write("v1-encircled-no-work-verified" if with_field else "v1c-control-no-encircled",
                 day, de)


# ------------------------------------------------------------------ V2
def v2() -> str:
    """遮蔽：encircled 格在更早的 clear_area 里 leftover=1，最后一轮 clear_area 干净 ⇒ 白拿 VERIFIED。"""
    day, ds, de = F.base_day()
    day = day_one(day)
    c = F.coords(1)
    st1 = F.set_stage(de, "clear_area", tiles=1, leftover=1, attempted=1, encircled=1,
                      encircled_leftover=1, stopped="encircled")
    st1["encircled_tiles"] = c
    st2 = F.set_stage(de, "clear_area", tiles=10, ok=10, leftover=0, attempted=10)
    de.update({"verified": True, "ok_steps": 10, "failed_steps": 0, "skipped_steps": 0,
               "stages": [st1, st2], "ended_by": "sleep",
               "ended_reason": "night:到点了", "checks": F.all_true_checks(),
               "encircled": 1, "encircled_tiles": c,
               "unreachable": 0, "unreachable_tiles": [], "unreachable_bound": 5,
               "unreachable_exempt": 0, "refused": 0, "refused_tiles": [],
               "refused_bound": 5, "refused_exempt": 0})
    day += enc_events(1)
    day.append(de)
    return write("v2-encircled-masked-by-later-clean-stage", day, de)


# ------------------------------------------------------------------ V3 / V4
def v3(lie: bool) -> str:
    """如实红（对照）/ 自称 no_unmet_stages=true 的谎报：encircled 格留在 leftover 里。"""
    day, ds, de = F.base_day()
    day = day_one(day)
    c = F.coords(1)
    st = F.set_stage(de, "clear_area", tiles=1, leftover=1, attempted=1, encircled=1,
                     encircled_leftover=1, stopped="encircled")
    st["encircled_tiles"] = c
    checks = F.all_true_checks()
    if lie:
        checks["no_unmet_stages"] = True
        de["verified"] = True
    else:
        checks["no_unmet_stages"] = False
        de["verified"] = False
    de.update({"ok_steps": 0, "failed_steps": 0, "skipped_steps": 0, "stages": [st],
               "ended_by": "sleep", "ended_reason": "stuck:守卫说还有活（被围住）",
               "checks": checks, "encircled": 1, "encircled_tiles": c,
               "unreachable": 0, "unreachable_tiles": [], "unreachable_bound": 5,
               "unreachable_exempt": 0, "refused": 0, "refused_tiles": [],
               "refused_bound": 5, "refused_exempt": 0})
    day += enc_events(1)
    day.append(de)
    return write("v3-encircled-leftover-honest-red" if not lie else "v4-encircled-lie-no-unmet",
                 day, de)


# ------------------------------------------------------------------ V5
def v5() -> str:
    """用 encircled 反复被选中把 attempted 抬高 ⇒ 真·不可达的豁免上界跟着膨胀。"""
    day, ds, de = F.base_day()
    day = day_one(day)
    enc_n, unreach_n = 800, 200
    enc_c = enc_events(enc_n)
    un_c = [[100 + i, 30] for i in range(unreach_n)]
    st_enc = F.set_stage(de, "clear_dead", tiles=0, attempted=enc_n, encircled=enc_n)
    st_enc["encircled_tiles"] = [[e["tile"][0], e["tile"][1]] for e in enc_c]
    st_un = F.set_stage(de, "till_area", tiles=unreach_n, leftover=unreach_n,
                        attempted=unreach_n, unreachable=unreach_n,
                        unreachable_leftover=unreach_n, ok=1, stopped="unreachable")
    st_un["unreachable_tiles"] = un_c
    attempted = enc_n + unreach_n
    bound = max(5, int(0.2 * attempted))
    de.update({"verified": True, "ok_steps": 1, "failed_steps": 0, "skipped_steps": 0,
               "stages": [st_enc, st_un], "ended_by": "sleep",
               "ended_reason": "night:到点了", "checks": F.all_true_checks(),
               "encircled": enc_n, "encircled_tiles": st_enc["encircled_tiles"],
               "unreachable": unreach_n, "unreachable_tiles": un_c,
               "unreachable_bound": bound, "unreachable_exempt": unreach_n,
               "refused": 0, "refused_tiles": [], "refused_bound": bound, "refused_exempt": 0})
    day += enc_c
    day += [{"event": "unreachable", "t": 4000.0 + i, "action": "till", "stage": "till_area",
             "tile": un_c[i], "zone": "field", "reason": "四邻都站不过去"} for i in range(unreach_n)]
    day.append(de)
    return write("v5-encircled-inflates-unreachable-bound", day, de)


print("生成变体：")
paths = [v1(True), v1(False), v2(), v3(False), v3(True), v5()]
for p in paths:
    print("  ", os.path.basename(p), os.path.getsize(p), "B")

print()
print("=" * 78)
print("逐本跑 tools/verify-run3.py --days 1")
print("=" * 78)
for p in paths:
    cp = subprocess.run([PY, TOOL, "--journal", p, "--days", "1"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (cp.stdout or "") + (cp.stderr or "")
    probs = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("[") and "]" in ln
             and ("不一致" in ln or "problem" in ln.lower())]
    infos = [ln.strip() for ln in out.splitlines() if "信息" in ln or "encircled" in ln
             or "frontier_clear" in ln or "零动作" in ln or "阶段" in ln]
    print(f"--- {os.path.basename(p)} ⇒ exit={cp.returncode}")
    for ln in probs[:6]:
        print("    ! " + ln[:170])
    for ln in infos[:6]:
        print("    i " + ln[:170])
print()
print("DONE")
