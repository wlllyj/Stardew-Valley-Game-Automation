# -*- coding: utf-8 -*-
"""步 5（task-242 逐格判据）的正/反向对照自测 —— 只读、离线、不碰游戏。

三个夹具：
  A 等值        ：每段 ok == len(cleared_tiles)            ⇒ 期望 PASS
  B 可解释      ：ok 比 cleared 多，但账本给了结构化区分     ⇒ 期望 PASS（记 explained）
  C 不可解释    ：ok 比 cleared 多且无任何区分字段/文案      ⇒ 期望 FAIL（列差异）

另有 D：整跑没有 clear_area ok 格 ⇒ 期望【无法判定】（不是失败）。
真实反向夹具见 `--only 5 --journal logs/longrun-smoke-0742.jsonl`（0.7.42 跑，应 FAIL rc=10）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SMOKE = os.path.join(HERE, "smoke-0742.py")
TMP = os.path.join(HERE, "_selftest_step5")


def load_smoke():
    spec = importlib.util.spec_from_file_location("smoke0742", SMOKE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def day_end(stages: list[dict]) -> dict:
    return {"event": "day_end", "day": [1, "winter", 5], "stages": stages}


def stage(ok: int, cleared: list, **kw) -> dict:
    s = {"stage": "clear_area", "ok": ok, "cleared_tiles": scanned(cleared)}
    s.update(kw)
    return s


def scanned(n: int) -> list:
    return [[10 + i, 20 + i] for i in range(n)]


def run_case(mod, name: str, rows: list[dict], want: str) -> bool:
    path = os.path.join(TMP, f"{name}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    mod.SMOKE_JOURNAL = type(mod.SMOKE_JOURNAL)(path)
    rec = {"evidence": {}}
    out = mod.step5(rec)
    got = out.get("verdict")
    ev = out.get("evidence") or {}
    line = (f"[{name}] verdict={got}（期望 {want}）"
            f" total_ok={ev.get('clear_stage_total_ok')}"
            f" conform={len(ev.get('conforming_stages') or [])}"
            f" explained={ev.get('explained_total')}"
            f" unexplained={ev.get('unexplained_total')}")
    print(line)
    print("    reason:", str(out.get("reason"))[:220])
    for it in (ev.get("explained_stages") or [])[:2]:
        print("    explained item:", json.dumps(it, ensure_ascii=False)[:200])
    for it in (ev.get("unexplained_stages") or [])[:3]:
        print("    unexplained item:", json.dumps(it, ensure_ascii=False)[:240])
    return got == want


def main() -> int:
    if not os.path.exists(SMOKE):
        print(f"缺 {SMOKE}", file=sys.stderr)
        return 3
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    mod = load_smoke()
    results = []

    # A 等值 ⇒ PASS
    results.append(run_case(mod, "A_equal", [day_end([
        stage(3, 3), stage(1, 1),
    ])], "PASS"))

    # B 可解释（结构化区分：target 2 + collateral 3 = 5 = cleared 3 + delta 2）⇒ PASS
    results.append(run_case(mod, "B_explained", [day_end([
        stage(5, 3, target_tiles=scanned(2), collateral_tiles=scanned(3)),
    ])], "PASS"))

    # B2 可解释（文案说明）⇒ PASS
    results.append(run_case(mod, "B2_note", [day_end([
        stage(4, 2, note="一次多格：顺手清了 2 格连带物"),
    ])], "PASS"))

    # C 不可解释 ⇒ FAIL
    results.append(run_case(mod, "C_unexplained", [day_end([
        stage(5, 3),
    ])], "FAIL"))

    # D 没有 clear_area ok 格 ⇒ 无法判定
    results.append(run_case(mod, "D_none", [day_end([
        {"stage": "water_area", "ok": 5, "cleared_tiles": []},
    ])], "无法判定"))

    shutil.rmtree(TMP, ignore_errors=True)
    ok = all(results)
    print(f"\nSTEP5 SELFTEST {'PASS' if ok else 'FAIL'}"
          f"（{sum(1 for r in results if r)}/{len(results)} 用例符合预期；离线、无游戏）")
    return 0 if ok else 13


if __name__ == "__main__":
    sys.exit(main())
