# -*- coding: utf-8 -*-
"""task-72 取证：造**上界自洽**的豁免洗白账本，把三条通道各自隔离出来。

`_t54_forge.py` 的变体把 `unreachable_bound` 写成 8（而工具自算 = max(5, 0.2*attempted)），
于是拿到 task-71 的 WIP 工具上一跑，**每条都先撞"上界被放宽"**，看不出通道本身是否被堵。
本脚本每个变体都把 `unreachable_bound`/`refused_bound` 设成工具的自算值
（`max(5, int(0.2 * Σ stages.attempted))`）——即"攻击者把账本做到完全自洽"。

用法：python scratch/_t72_forge.py
产出：scratch/review-t72-*.jsonl（5 个变体；基座见 `scratch/journal-green.jsonl`）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _t54_forge as F  # noqa: E402  （复用基座/构造辅助，不改它的产物）

OUT = "scratch"


def tool_bound(attempted: int) -> int:
    """复刻 `tools/verify-run3.py` 的自算上界：max(5, int(0.2 * attempted))。"""
    return max(5, int(0.2 * attempted))


def write_t72(tag: str, day: list[dict], de: dict) -> str:
    de["t"] = 2400.0
    path = os.path.join(OUT, f"review-t72-{tag}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in day:
            fh.write(F.json.dumps(r, ensure_ascii=False) + "\n")
        fh.write(F.json.dumps(F.finish_line(), ensure_ascii=False) + "\n")
    return path


def v_bound_inflate() -> str:
    """通道 (c)：42 格不可达，账本把上界抬到 9999 并自称界内。

    自算上界 = max(5, 0.2*50) = 10 ⇒ 账本 9999 比它宽 1000 倍。
    """
    day, ds, de = F.base_day()
    day = F.body(day)
    c = F.coords(42)
    st = F.set_stage(de, "till_area", tiles=42, leftover=0, attempted=30, ok=0,
                     unreachable=42, unreachable_leftover=42)
    st["unreachable_tiles"] = c
    ok_st = F.set_stage(de, "water_area", tiles=20, ok=20, leftover=0, attempted=20)
    de.update({"verified": True, "ok_steps": 20, "failed_steps": 0, "skipped_steps": 0,
               "day_after": ["1", "spring", 11], "stages": [st, ok_st],
               "unreachable": 42, "unreachable_tiles": c, "unreachable_bound": 9999,
               "unreachable_exempt": 42, "refused": 0, "refused_tiles": [],
               "refused_bound": 9999, "refused_exempt": 0,
               "checks": F.all_true_checks()})
    day += F.unreach_events(day, 42, stage="till_area", reason="四邻都站不过去")
    day.append(de)
    return write_t72("bound-inflate", day, de)


def v_no_coords() -> str:
    """通道 (e)：扣了 3 格不可达豁免，却不写坐标、也没有逐格 journal 事件。

    上界自洽（attempted=33 ⇒ 6），所以工具不该拿"上界"当借口，只能抓"没写坐标"。
    """
    day, ds, de = F.base_day()
    day = F.body(day)
    st = F.set_stage(de, "till_area", tiles=8, leftover=3, attempted=8, unreachable=3,
                     unreachable_leftover=3)
    st["unreachable_tiles"] = []
    ok_st = F.set_stage(de, "water_area", tiles=25, ok=25, leftover=0, attempted=25)
    b = tool_bound(33)
    de.update({"verified": True, "ok_steps": 25, "failed_steps": 0, "skipped_steps": 0,
               "day_after": ["1", "spring", 11], "stages": [st, ok_st],
               "unreachable": 3, "unreachable_tiles": [], "unreachable_bound": b,
               "unreachable_exempt": 3, "refused": 0, "refused_tiles": [],
               "refused_bound": b, "refused_exempt": 0,
               "checks": F.all_true_checks()})
    day.append(de)
    return write_t72("exempt-no-coords", day, de)


def v_overlap() -> str:
    """通道 (f)：同一批 2 格同时进 unreachable 与 refused 两套豁免（重复扣减）。"""
    day, ds, de = F.base_day()
    day = F.body(day)
    c = F.coords(2, x0=50, y0=14)
    st = F.set_stage(de, "till_area", tiles=8, leftover=2, attempted=8, ok=6,
                     unreachable=2, unreachable_leftover=2, refused=2, refused_leftover=2)
    st["unreachable_tiles"] = c
    st["refused_tiles"] = c
    b = tool_bound(8)
    de.update({"verified": True, "ok_steps": 6, "failed_steps": 0, "skipped_steps": 0,
               "day_after": ["1", "spring", 11], "stages": [st],
               "unreachable": 2, "unreachable_tiles": c, "unreachable_bound": b,
               "unreachable_exempt": 2, "refused": 2, "refused_tiles": c,
               "refused_bound": b, "refused_exempt": 2, "checks": F.all_true_checks()})
    day += F.unreach_events(day, 2, stage="till_area", reason="四邻都站不过去")
    day += F.refused_events(2, stage="till_area", tiles=c)
    day.append(de)
    return write_t72("overlap-two-sets", day, de)


def v_relabel_clean() -> str:
    """开放盲区：把真失败（'锄完不是 dirt'）改写成不可达，且**所有账目字段自洽**。

    上界 = 自算（attempted=24 ⇒ 5）、坐标齐、journal 事件齐 ⇒ 账本层没有任何矛盾可抓。
    """
    day, ds, de = F.base_day()
    day = F.body(day)
    c = F.coords(4, x0=40, y0=12)
    st = F.set_stage(de, "till_area", tiles=4, leftover=0, attempted=4, ok=0,
                     unreachable=4, unreachable_leftover=4)
    st["unreachable_tiles"] = c
    ok_st = F.set_stage(de, "water_area", tiles=20, ok=20, leftover=0, attempted=20)
    b = tool_bound(24)
    de.update({"verified": True, "ok_steps": 20, "failed_steps": 0, "skipped_steps": 0,
               "day_after": ["1", "spring", 11], "stages": [st, ok_st],
               "unreachable": 4, "unreachable_tiles": c, "unreachable_bound": b,
               "unreachable_exempt": 4, "refused": 0, "refused_tiles": [],
               "refused_bound": b, "refused_exempt": 0,
               "checks": F.all_true_checks()})
    day += F.blocked_events(4, stage="till_area", reason="锄完不是 dirt（kind=未知）")
    day += F.unreach_events(day, 4, stage="till_area", reason="四邻都站不过去")
    day.append(de)
    return write_t72("relabel-clean", day, de)


def v_vacuum_clean() -> str:
    """已生效防线：8 格全不可达 + 0 成功动作 + 自称 VERIFIED，且上界自洽（attempted=8 ⇒ 5）。"""
    day, ds, de = F.base_day()
    day = F.body(day)
    c = F.coords(8)
    st = F.set_stage(de, "till_area", tiles=8, leftover=0, attempted=8, unreachable=8,
                     unreachable_leftover=8)
    st["unreachable_tiles"] = c
    b = tool_bound(8)
    de.update({"verified": True, "ok_steps": 0, "failed_steps": 0, "skipped_steps": 0,
               "day_after": ["1", "spring", 11], "stages": [st],
               "unreachable": 8, "unreachable_tiles": c, "unreachable_bound": b,
               "unreachable_exempt": 8, "refused": 0, "refused_tiles": [],
               "refused_bound": b, "refused_exempt": 0,
               "checks": F.all_true_checks()})
    day += F.unreach_events(day, 8, stage="till_area", reason="四邻都站不过去")
    day.append(de)
    return write_t72("vacuum-clean", day, de)


def main() -> None:
    made = [v_bound_inflate(), v_no_coords(), v_overlap(), v_relabel_clean(), v_vacuum_clean()]
    for p in made:
        print(f"{os.path.getsize(p):6d}  {p}")


if __name__ == "__main__":
    main()
