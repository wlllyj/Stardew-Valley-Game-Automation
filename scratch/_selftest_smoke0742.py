# -*- coding: utf-8 -*-
"""smoke-0742.py 步 8 的**正向对照**自测（离线、零游戏）。

目的：证明 0.7.42 三条硬判据不是"恒红"——
  1) 构造一份**合规**账本：day_end 有 verified=true、没有"该去种"文案、
     blocked 带 `tool_ineffective_bound` 且 calls=3、deferred_by_budget 理由含「预算 6 棵 / 已砍 6 棵」；
  2) 造两份同日 `observe?detail=full` 快照（farm.trees 804 → 780，日降幅 −24 棵）；
  3) 直接调用 smoke-0742.py 的 `step8()`，期望 **PASS**，并打印四个子判据读数；
  4) 顺带把 `_step8_trees` 的 FAIL 分支也测一次（两份快照 804 → 803，降幅只有 1 棵 ⇒ FAIL）。
所有临时文件都写在 logs/ 与 scratch/ 下并**按名字断言后删除**（不碰真实产物、不碰存档、不碰游戏）。
退出码：0 = 两个方向都符合预期；13 = 不符。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
LOGS = os.path.join(REPO, "logs")
SMOKE = os.path.join(HERE, "smoke-0742.py")

FIXTURE_JOURNAL = os.path.join(HERE, "_selftest_smoke0742_journal.jsonl")
OBS_A = os.path.join(LOGS, "smoke-0742-observe-winter2-aa.json")
OBS_B = os.path.join(LOGS, "smoke-0742-observe-winter2-bb.json")
OBS_C = os.path.join(LOGS, "smoke-0742-observe-winter3-cc.json")  # 用**另一天**，避免污染 winter2 的日降幅


def load_smoke():
    spec = importlib.util.spec_from_file_location("smoke0742_mod", SMOKE)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def obs_doc(trees: int, world_seq: int, day: int = 2) -> dict:
    return {"captured_at": "2026-10-18T15:00:00", "tag": "selftest", "observe": {
        "ok": True, "worldSeq": world_seq,
        "clock": {"year": 1, "season": "winter", "day": day, "timeOfDay": 1000,
                  "weather": "sunny", "weatherOnFarm": "sunny"},
        "farm": {"trees": trees, "weeds": 10, "stones": 10, "twigs": 10},
        "player": {"name": "Jay", "inventory": []},
        "location": {"name": "Farm", "tiles": []},
    }}


def make_journal() -> list[dict]:
    """合规账本：2 天、至少一天 verified=true、无守卫文案、合法 bound 放弃、预算理由合规。"""
    recs = [
        {"event": "day_start", "t": 0.1, "t": 0},
        {"event": "blocked", "t": 12.0, "kind": "clear_area", "tile": [36, 10],
         "reason": "use_tool 3 次仍无效 ⇒ tool_ineffective_bound（已到上界）", "calls": 3},
        {"event": "deferred_by_budget", "t": 28.74, "task": "clear_area_tree",
         "why": "今天砍树预算 6 棵 / 已砍 6 棵，明天继续"},
        {"event": "day_end", "t": 60.0, "day": [1, "winter", 2], "ended_by": "night",
         "verified": True, "checks": {"day_justified": True, "no_hard_failures": True},
         "day_after": [1, "winter", 3]},
        {"event": "day_end", "t": 120.0, "day": [1, "winter", 3], "ended_by": "night",
         "verified": True, "checks": {"day_justified": True}, "day_after": [1, "winter", 4]},
        {"event": "finish", "t": 121.0, "code": 0, "verified_streak": 2},
    ]
    return recs


def main() -> int:
    ok = True
    mod = load_smoke()
    print(f"[load] smoke-0742.py → {SMOKE}")

    # 写夹具
    recs = make_journal()
    with open(FIXTURE_JOURNAL, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OBS_A, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obs_doc(804, 10), ensure_ascii=False))
    with open(OBS_B, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obs_doc(780, 40), ensure_ascii=False))
    with open(OBS_C, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obs_doc(803, 60, day=3), ensure_ascii=False))
    print(f"[fixture] journal={FIXTURE_JOURNAL} obs={os.path.basename(OBS_A)},{os.path.basename(OBS_B)}")

    try:
        args = types.SimpleNamespace(journal=FIXTURE_JOURNAL)
        rec = mod.step8({}, args)
        ev = rec.get("evidence") or {}
        rows = [("8.1 冬季可验证性", ev.get("winter")), ("8.2① 清障单发封格", ev.get("clear_throughput")),
                ("8.2② farm.trees 日降幅", ev.get("trees")), ("8.2③ 预算理由", ev.get("budget_reason"))]
        for name, sub in rows:
            sub = sub or {}
            print(f"  {name:22} = {sub.get('status')} · {str(sub.get('reason'))[:150]}")
        print(f"[正向] 步 8 verdict = {rec.get('verdict')}（期望 PASS）")
        if rec.get("verdict") != "PASS":
            print("!! 正向对照未 PASS"); ok = False
        if (ev.get("trees") or {}).get("per_day_delta"):
            print(f"        per_day_delta = {ev['trees']['per_day_delta']}")

        # FAIL 分支：把 trees 改成 804 → 803（降幅仅 1 棵）
        with open(OBS_B, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(obs_doc(803, 41), ensure_ascii=False))
        t_fail = mod._step8_trees([__import__("pathlib").Path(OBS_A), __import__("pathlib").Path(OBS_B)])
        print(f"[反向] farm.trees 降幅只有 1 棵 ⇒ {t_fail.get('status')}（期望 FAIL）· "
              f"{str(t_fail.get('reason'))[:120]}")
        if t_fail.get("status") != "FAIL":
            print("!! 反向对照未 FAIL"); ok = False

        # 反向：守卫文案出现 ⇒ 8.1 FAIL
        guard = [dict(recs[3])]
        guard[0]["checks"] = {"day_justified": False,
                             "note": "农场口径还有 29 格耕地空着（手上有 10 粒种子）⇒ 该去种"}
        w_fail = mod._step8_winter(guard)
        print(f"[反向] 旧守卫文案出现 ⇒ 8.1 {w_fail.get('status')}（期望 FAIL）")
        if w_fail.get("status") != "FAIL":
            print("!! 守卫文案反向对照未 FAIL"); ok = False

        # 反向：单发 tool_ineffective（无 bound）⇒ 8.2① FAIL
        c_fail = mod._step8_clear_illegal([{"event": "blocked", "t": 5.0, "tile": [1, 2],
                                           "reason": "tool_ineffective：单发 use_tool 试过的工具都无效（Axe 挥 6 次）"}])
        print(f"[反向] 单发 tool_ineffective ⇒ 8.2① {c_fail.get('status')}（期望 FAIL）")
        if c_fail.get("status") != "FAIL":
            print("!! 单发反向对照未 FAIL"); ok = False

        print(f"\nSELFTEST-8 {'PASS' if ok else 'FAIL'}（正向 4 子判据全 PASS + 3 个反向分支全 FAIL；"
              f"无游戏、无网络、无存档写入）")
        return 0 if ok else 13
    finally:
        for p in (FIXTURE_JOURNAL, OBS_A, OBS_B, OBS_C):
            if not os.path.abspath(p).startswith((LOGS, HERE)):
                raise SystemExit(f"拒绝删除可疑路径：{p}")
            if os.path.exists(p):
                os.unlink(p)
        print("[cleanup] 临时夹具已删除")


if __name__ == "__main__":
    sys.exit(main())
