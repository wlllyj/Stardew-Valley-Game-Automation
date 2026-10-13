"""task-54 对抗实验：造"豁免洗白"类账本，喂 `tools/verify-run3.py` 看能不能白过。

基座 = `scratch/journal-green.jsonl` 的第 1 天（已知 exit 0 的形态），逐变体改写 day_end/stages
并把 journal 事件补齐（让工具的自算值与账本自述一致 —— 攻击者的目标就是"自洽"）。

用法：python scratch/_t54_forge.py            # 生成全部变体
"""
from __future__ import annotations

import copy
import json
import os

BASE = os.path.join("scratch", "journal-green.jsonl")
OUT = "scratch"


def load(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def base_day() -> tuple[list[dict], dict, dict]:
    """返回 (第 1 天的全部行, day_start, day_end)。"""
    rows = load(BASE)
    day: list[dict] = []
    for r in rows:
        day.append(copy.deepcopy(r))
        if r.get("event") == "day_end":
            break
    ds = next(r for r in day if r.get("event") == "day_start")
    de = next(r for r in day if r.get("event") == "day_end")
    return day, ds, de


def all_true_checks() -> dict:
    return {
        "slept_by_us": True,
        "no_blocking_modal": True,
        "no_hard_failures": True,
        "no_unmet_stages": True,
        "crops_watered": True,
        "watered_outdoor": True,
        "day_justified": True,
    }


def finish_line(days: int = 1) -> dict:
    return {"event": "finish", "t": 600.0, "code": 0, "verified_streak": days,
            "days": days, "actions": 96, "minutes": 10.0}


def set_stage(de: dict, stage: str, **kw) -> dict:
    st = {"stage": stage, "tiles": 0, "ok": 0, "skipped": 0, "failed": 0, "leftover": 0,
          "attempted": 0, "stopped": ""}
    st.update(kw)
    return st


def coords(n: int, x0: int = 30, y0: int = 10) -> list[list[int]]:
    return [[x0 + i, y0] for i in range(n)]


def unreach_events(day: list[dict], n: int, *, stage: str, reason: str,
                   note: str = "无落脚点") -> list[dict]:
    return [{"event": "unreachable", "t": 2000.0 + i, "action": "till", "stage": stage,
             "tile": [30 + i, 10], "zone": "field", "reason": reason, "note": note}
            for i in range(n)]


def refused_events(n: int, *, stage: str, tiles: list[list[int]]) -> list[dict]:
    return [{"event": "tool_refused", "t": 2100.0 + i, "stage": stage, "tile": list(t),
             "zone": "field", "code": "tool_ineffective",
             "reason": "锄完不是 dirt（kind=未知）"} for i, t in enumerate(tiles)]


def blocked_events(n: int, *, stage: str, reason: str) -> list[dict]:
    return [{"event": "blocked", "t": 2200.0 + i, "stage": stage, "tile": [40 + i, 12],
             "zone": "field", "reason": reason, "note": "封格"} for i in range(n)]


def write(tag: str, day: list[dict], de: dict) -> str:
    # 注入事件的 t 从 2000 起、day_end 收在最后 ⇒ 时间轴单调，免得掺进"t 回退"的 info 噪声。
    de["t"] = 2400.0
    path = os.path.join(OUT, f"review-t54-{tag}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in day:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.write(json.dumps(finish_line(), ensure_ascii=False) + "\n")
    return path


def drop(day: list[dict], *events: str) -> list[dict]:
    return [r for r in day if r.get("event") not in events]


def body(day: list[dict]) -> list[dict]:
    """基座第 1 天的行，去掉要重写的事件（stage/day_end）⇒ 之后自己拼。

    注意**保留 `sleep` 事件**：否则每个变体都会先因为 "ended_by=sleep 但 journal 里没有
    成功的 sleep 证据" 被判红，掩盖掉我们真正要测的豁免通道。
    """
    return drop(day, "stage", "day_end")


# ---------------------------------------------------------------- 变体
def v_vacuum() -> str:
    """(a') 一天全部目标不可达 + 0 成功动作 + 自称 VERIFIED（反空洞控制组）。"""
    day, ds, de = base_day()
    day = body(day)
    c = coords(8)
    st = set_stage(de, "till_area", tiles=8, leftover=0, attempted=8, unreachable=8,
                   unreachable_leftover=8)
    st["unreachable_tiles"] = c
    de.update({"verified": True, "ok_steps": 0, "failed_steps": 0, "skipped_steps": 0,
               "day_after": ["1", "spring", 11], "stages": [st],
               "unreachable": 8, "unreachable_tiles": c, "unreachable_bound": 8,
               "unreachable_exempt": 8, "refused": 0, "refused_tiles": [],
               "refused_bound": 8, "refused_exempt": 0,
               "checks": all_true_checks()})
    day += unreach_events(day, 8, stage="till_area", reason="四邻都站不过去")
    day.append(de)
    return write("vacuum-all-unreachable", day, de)


def v_inflate() -> str:
    """(c) 抬高 attempted/bound：42 格不可达却把 bound 写成 9999，且自称界内。"""
    day, ds, de = base_day()
    day = body(day)
    c = coords(42)
    st = set_stage(de, "till_area", tiles=42, leftover=0, attempted=30, ok=0,
                   unreachable=42, unreachable_leftover=42)
    st["unreachable_tiles"] = c
    ok_st = set_stage(de, "water_area", tiles=20, ok=20, leftover=0, attempted=20)
    de.update({"verified": True, "ok_steps": 20, "failed_steps": 0, "skipped_steps": 0,
               "day_after": ["1", "spring", 11], "stages": [st, ok_st],
               "unreachable": 42, "unreachable_tiles": c, "unreachable_bound": 9999,
               "unreachable_exempt": 42, "refused": 0, "refused_tiles": [],
               "refused_bound": 9999, "refused_exempt": 0,
               "checks": all_true_checks()})
    day += unreach_events(day, 42, stage="till_area", reason="四邻都站不过去")
    day.append(de)
    return write("inflate-bound-attempted", day, de)


def v_no_coords() -> str:
    """(③) 扣了豁免却没写坐标、也没有 journal 事件（缺失≠通过 应该判问题）。"""
    day, ds, de = base_day()
    day = body(day)
    st = set_stage(de, "till_area", tiles=8, leftover=3, attempted=8, unreachable=3,
                   unreachable_leftover=3)
    st["unreachable_tiles"] = []
    ok_st = set_stage(de, "water_area", tiles=25, ok=25, leftover=0, attempted=25)
    de.update({"verified": True, "ok_steps": 25, "failed_steps": 0, "skipped_steps": 0,
               "day_after": ["1", "spring", 11], "stages": [st, ok_st],
               "unreachable": 3, "unreachable_tiles": [], "unreachable_bound": 8,
               "unreachable_exempt": 3, "refused": 0, "refused_tiles": [],
               "refused_bound": 8, "refused_exempt": 0,
               "checks": all_true_checks()})
    day.append(de)
    return write("exempt-without-coords", day, de)


def v_relabel() -> str:
    """(b) 把真失败（锄完不是 dirt）改写成不可达达成自洽 ⇒ 账本层看不出。"""
    day, ds, de = base_day()
    day = body(day)
    c = coords(4, x0=40, y0=12)
    st = set_stage(de, "till_area", tiles=4, leftover=0, attempted=4, ok=0,
                   unreachable=4, unreachable_leftover=4)
    st["unreachable_tiles"] = c
    ok_st = set_stage(de, "water_area", tiles=20, ok=20, leftover=0, attempted=20)
    de.update({"verified": True, "ok_steps": 20, "failed_steps": 0, "skipped_steps": 0,
               "day_after": ["1", "spring", 11], "stages": [st, ok_st],
               "unreachable": 4, "unreachable_tiles": c, "unreachable_bound": 8,
               "unreachable_exempt": 4, "refused": 0, "refused_tiles": [],
               "refused_bound": 8, "refused_exempt": 0,
               "checks": all_true_checks()})
    day += blocked_events(4, stage="till_area", reason="锄完不是 dirt（kind=未知）")
    day += unreach_events(day, 4, stage="till_area", reason="四邻都站不过去")
    day.append(de)
    return write("failed-relabeled-unreachable", day, de)


def v_overlap(*, inconsistent: bool) -> str:
    """(d) 同一批坐标同时算进 unreachable 与 refused（两套豁免互相掩护）。"""
    day, ds, de = base_day()
    day = body(day)
    c = coords(2, x0=50, y0=14)
    st = set_stage(de, "till_area", tiles=8, leftover=2, attempted=8, ok=6,
                   unreachable=2, unreachable_leftover=2, refused=2, refused_leftover=2)
    st["unreachable_tiles"] = c
    st["refused_tiles"] = c
    checks = all_true_checks()
    if inconsistent:
        checks["no_unmet_stages"] = False
    de.update({"verified": True, "ok_steps": 6, "failed_steps": 0, "skipped_steps": 0,
               "day_after": ["1", "spring", 11], "stages": [st],
               "unreachable": 2, "unreachable_tiles": c, "unreachable_bound": 8,
               "unreachable_exempt": 2, "refused": 2, "refused_tiles": c,
               "refused_bound": 8, "refused_exempt": 2, "checks": checks})
    day += unreach_events(day, 2, stage="till_area", reason="四邻都站不过去")
    day += refused_events(2, stage="till_area", tiles=c)
    day.append(de)
    tag = "overlap-two-sets-inconsistent" if inconsistent else "overlap-two-sets"
    return write(tag, day, de)


def main() -> None:
    made = [
        v_vacuum(),
        v_inflate(),
        v_no_coords(),
        v_relabel(),
        v_overlap(inconsistent=False),
        v_overlap(inconsistent=True),
    ]
    for p in made:
        print(f"{os.path.getsize(p):6d}  {p}")


if __name__ == "__main__":
    main()
