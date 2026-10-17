r"""task-192 delta 复核（只写 `scratch/`）：释放认输区时的记账 + 上界不放宽 + 工具净额对账。

对象：`1246cdd`（"释放认输区时同步扣减当天认输记账"）。

复用的三件事（Lead 的 delta 口径）：
  ① 释放后不许当天对同区再认输、**累计上界**不许因释放归零（持久层不许被洗回 0）；
  ② 净额与工具 `3ccc29b` 一致：`journal 毛 − 释放 = 账本末态`；
  ③ 部分释放（6→2）末态 = 4。

用法：`& $py -W error::SyntaxWarning scratch\_t192_delta.py`（`T185_ROOT` 可切树，缺省 = 本仓库）
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("t185", WS / "scratch" / "_t185_probe.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)                                # 复用其夹具/断言/工具调用

check = T.check
info = T.info
events = T.events
ROOT = T.ROOT


def _shed(w, *, tag: str, zone_split: int = 2, crops: int = 200):
    run = T.mk(w, journal=T.JOURNALS / f"{tag}.jsonl", zone_split=zone_split)
    obs = w.obs()
    names = T.zone_names(run, obs)
    assert names, "夹具没造出田区"
    z0 = names[0]
    rep = T.rep_for(10)
    ok = run._shed_scope(z0, obs, rep)
    assert ok, f"认输没成功（z0={z0}）"
    return run, obs, rep, z0


def case_D1() -> None:
    """真流程：认输整区 → 释放 ⇒ 末态 0，且累计量不因释放归零。"""
    print("== D1 释放 ⇒ 日终末态 0（毛−释放=净），累计上界不放宽 ==")
    if not T.has_168():
        return T.skip("D1", "task-168 未落地")
    w = T.world(200)
    run, _obs, rep, z0 = _shed(w, tag="d1")
    held = set(run.shed_zone_tiles.get(z0) or ())
    n = len(held)
    check("D1-pre 认输后当天记账 = 该区格数", rep.scope_shed_tiles == n and n > 0,
          f"n={n} rep.scope_shed_tiles={rep.scope_shed_tiles}")
    ever_before = dict(run.shed_ever_tiles)
    run._release_zone(z0, "delta_release", rep)
    rel = (events(run, "scope_released") or [{}])[-1]
    check("D1a 释放后 day_end.scope_shed_tiles = 0（日终末态语义）",
          rep.scope_shed_tiles == 0 and int(run.scope_shed_tiles_today) == 0,
          f"rep={rep.scope_shed_tiles} today={run.scope_shed_tiles_today}")
    check("D1b 释放后 day_end.scope_shed 快照清空", rep.scope_shed == {}, f"{rep.scope_shed}")
    check("D1c scope_released.tiles = 毛（本次释放格数）且 remaining=0",
          int(rel.get("tiles") or 0) == n and int(rel.get("shed_tiles_remaining") or 0) == 0,
          f"rel={ {k: rel.get(k) for k in ('zone', 'tiles', 'shed_tiles_remaining')} }")
    check("D1d 累计量（34% 上界依据）不因释放归零",
          int(run.shed_ever_tiles.get(z0) or 0) == int(ever_before.get(z0) or 0) == n,
          f"ever={run.shed_ever_tiles}")
    check("D1e 释放后该区回到目标池（shed_zone_tiles 已 pop）",
          z0 not in run.shed_zone_tiles and z0 not in run.shed_zones, "")


def case_D2() -> None:
    """部分释放：释放时仍持有 2 格 ⇒ 只扣 2（末态 = 毛−2）。"""
    print("== D2 部分释放（仍持有 2 格）⇒ 只扣 2 ==")
    if not T.has_168():
        return T.skip("D2", "task-168 未落地")
    w = T.world(200)
    run, _obs, rep, z0 = _shed(w, tag="d2")
    n = len(run.shed_zone_tiles.get(z0) or ())
    keep = sorted(run.shed_zone_tiles[z0])[:2]
    run.shed_zone_tiles[z0] = set(keep)                     # 模拟其余格已收敛（不再处于认输态）
    run._release_zone(z0, "delta_partial", rep)
    rel = (events(run, "scope_released") or [{}])[-1]
    check("D2a 释放量 = 释放时仍持有数（2）", int(rel.get("tiles") or 0) == 2, f"rel={rel.get('tiles')}")
    check("D2b 日终末态 = 毛 − 2", int(rep.scope_shed_tiles) == n - 2 and n >= 2,
          f"n={n} 末态={rep.scope_shed_tiles}")
    check("D2c 快照保留剩余并记 released_tiles",
          int(rep.scope_shed.get("tiles") or 0) == n - 2 and int(rep.scope_shed.get("released_tiles") or 0) == 2,
          f"{rep.scope_shed}")


def case_D2b() -> None:
    """卡面字面口径：6 → 2 ⇒ 末态 4（合成构造：毛 6、释放时持有 2）。"""
    print("== D2b 卡面字面：6 → 2 ⇒ 末态 4 ==")
    if not T.has_168():
        return T.skip("D2b", "task-168 未落地")
    w = T.world(200)
    run, _obs, rep, z0 = _shed(w, tag="d2b")
    run.scope_shed_tiles_today = 6
    rep.scope_shed_tiles = 6
    rep.scope_shed = {"zone": z0, "tiles": 6, "reason": "合成：毛 6"}
    run.shed_zone_tiles[z0] = set(sorted(run.shed_zone_tiles[z0])[:2])
    run._release_zone(z0, "delta_partial_6_2", rep)
    rel = (events(run, "scope_released") or [{}])[-1]
    check("D2b 6→2 ⇒ 末态 4，且 scope_released.tiles=2 / remaining=4",
          int(rep.scope_shed_tiles) == 4 and int(rel.get("tiles") or 0) == 2
          and int(rel.get("shed_tiles_remaining") or 0) == 4,
          f"末态={rep.scope_shed_tiles} rel={{tiles:{rel.get('tiles')}, "
          f"remaining:{rel.get('shed_tiles_remaining')}}}")


def case_D3() -> None:
    """上界不放宽：释放后累计量仍计入 34% 上界，换区再认输会被 cap 拦住；同区再认输被 already_today 拦。"""
    print("== D3 释放后上界不放宽（cap 仍看累计量）==")
    if not T.has_168():
        return T.skip("D3", "task-168 未落地")
    w = T.world(200)
    run, obs, rep, z0 = _shed(w, tag="d3")
    n = len(run.shed_zone_tiles.get(z0) or ())
    run._release_zone(z0, "delta_release", rep)
    # (a) 当天同区再认输 ⇒ already_today
    rep2 = T.rep_for(10)
    again = run._shed_scope(z0, obs, rep2)
    refused = (events(run, "scope_shed_refused") or [{}])[-1]
    check("D3a 释放后当天同区再认输被拦（already_today / scope_shed_today 未复位）",
          again is False and str(refused.get("reason") or "") in ("already_today", "cap"),
          f"again={again} reason={refused.get('reason')}")
    # (b) 累计量抬高到 cap−1 ⇒ 换区认输被 cap 拦
    workable = len(run._farm_workable_tiles(obs))
    cap_tiles = int(T.api()["max_fraction"] * workable)
    names = T.zone_names(run, obs)
    z1 = next((z for z in names if z != z0), None)
    if z1 is None:
        return T.skip("D3b", "只有一个田区，无法换区构造")
    run.shed_ever_tiles = {"(bogus)": max(0, cap_tiles - 1)}
    run.scope_shed_today = False                              # 只测 cap 通道，不测 already_today
    run.scope_cap_refused_today = False
    run.shed_zones.pop(z1, None)
    run.shed_zone_tiles.pop(z1, None)
    blocked = run._shed_scope(z1, obs, T.rep_for(10))
    refused2 = (events(run, "scope_shed_refused") or [{}])[-1]
    check("D3b 累计量接近上界 ⇒ 换区认输被 cap 拦住（释放不清累计量）",
          blocked is False and str(refused2.get("reason") or "") == "cap",
          f"blocked={blocked} reason={refused2.get('reason')} cap={cap_tiles} workable={workable}")
    # (c) 对照：累计量清零（= 旧行为）⇒ 同一请求会成功 ⇒ 证明 (b) 是被累计量挡住的
    run.shed_ever_tiles = {}
    run.scope_cap_refused_today = False
    allowed = run._shed_scope(z1, obs, T.rep_for(10))
    check("D3c 对照：累计量清零后同一请求成功（证明 D3b 挡的是累计量）",
          allowed is True, f"allowed={allowed}")


def case_D4() -> None:
    """工具侧净额对账：`journal 毛 − 释放 = 账本末态`（run9c 基准账本 + 伪事件）。"""
    print("== D4 工具侧净额对账（verify-run3 CLI）==")
    base = T.BASE_LEDGER
    if not base.exists():
        return T.skip("D4", "缺基准账本 logs/longrun-3day-llm-run9c.jsonl")
    rc0, out0 = T.tool_run(base, days=3)
    ev = [{"event": "scope_shed", "t": 1200.0, "zone": "field_ne", "tiles": 6,
           "live_crops": 20, "water_capacity": 129, "deficit": 71, "reason": "伪造"}]
    rel = [{"event": "scope_released", "t": 1300.0, "zone": "field_ne", "reason": "伪造释放",
            "tiles": 6}]
    rel2 = [{"event": "scope_released", "t": 1300.0, "zone": "field_ne", "reason": "伪造部分释放",
             "tiles": 2}]
    # (e) 毛 6 − 释放 6 = 0 ⇒ 与账本末态 0 一致 ⇒ 不许判"对不上"
    e = T.forge(base, T.JOURNALS / "d4e.jsonl",
                patch_day_end={"scope_shed_tiles": 0, "scope_shed": {}},
                add_events=ev + rel, which="last")
    rce, oute = T.tool_run(e, days=3)
    check("D4e 释放干净（毛 6 − 释放 6 = 末态 0）⇒ 不判「认输量对不上」",
          "认输量对不上" not in oute, f"rc={rce}")
    # (f) 毛 6 − 释放 2 = 4，而账本写 0 ⇒ 净额对不上 ⇒ 必须判红
    f = T.forge(base, T.JOURNALS / "d4f.jsonl",
                patch_day_end={"scope_shed_tiles": 0, "scope_shed": {}},
                add_events=ev + rel2, which="last")
    rcf, outf = T.tool_run(f, days=3)
    check("D4f 净额对不上（毛 6 − 释放 2 = 4，账本写 0）⇒ problem",
          rcf != 0 and "对不上" in outf,
          f"rc={rcf} :: " + " / ".join(ln for ln in outf.splitlines() if "认输" in ln)[:300])
    # (g) 一致（毛 6 − 释放 2 = 4，账本写 4）⇒ 与基准同码
    g = T.forge(base, T.JOURNALS / "d4g.jsonl",
                patch_day_end={"scope_shed_tiles": 4,
                               "scope_shed": {"field_ne": {"tiles": 4}}},
                add_events=ev + rel2, which="last")
    rcg, outg = T.tool_run(g, days=3)
    check("D4g 净额一致（4 = 6 − 2）⇒ 不判「对不上」（基准 rc 不变）",
          "认输量对不上" not in outg and rcg == rc0, f"rc={rcg} 基准={rc0}")


def main() -> int:
    print(f"ROOT={ROOT}")
    print(f"markers: has_168={T.has_168()}")
    for fn in (case_D1, case_D2, case_D2b, case_D3, case_D4):
        try:
            fn()
        except Exception as exc:                          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} 跑完不抛异常", False, f"{type(exc).__name__}: {exc}")
    print(f"\n== 汇总：PASS={T.PASS} FAIL={T.FAIL} SKIP={T.SKIP} ==")
    return 1 if T.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
