#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""独立复核 longrun 的 journal（Lead 侧验收工具，不信执行者的口头结论）。

用法：
    python tools\\verify-run3.py                     # 默认读最新一份 logs\\longrun-*.jsonl
    python tools\\verify-run3.py --journal logs\\longrun-3day-llm-run3.jsonl
    python tools\\verify-run3.py --days 3 --json

它只读 journal（JSONL，每行一条事件，字段含 event/t/day/...），核对：

1. **跨日证据**：每个 `day_end` 的 `ended_by == "sleep"` 必须能在 journal 里找到
   一次成功的 sleep（`event=="sleep" and ok==true`），且**睡后重新观测到的日期**与
   `day_start` 的 day_key 不同 —— 回执不算证据，观测里的日期变化才算。
   【task-38】权威字段是 `day_end.day_after`（睡后重取的观测）；旧账本/合成账本没有它时
   才退回 `day_end.final.day`（那是**睡前**快照，"跨日"只有 `day_after` 才是真观测）。
2. **睡前未浇为 0**：`day_end.final.unwatered_crops == 0`（全局口径）。
3. **无硬失败**：当天 stages 的 failed 之和为 0。
3b. **阶段后置条件成立**：优先读 `day_end.checks.no_unmet_stages`（task-15 起），读不到就
    按 `day_end.stages[].leftover` 自己算 —— 只认「做过且做完」，`blocked`/封格不得洗白成功。
3c. **过程里没有异常事件**：`bridge_down` / `watchdog_stop` / `modal_timeout` / `no_day_progress`
    出现任意一条即判未达标（这些是"人不在场也出过事"的证据）。
4. **LLM 覆盖**：`decision` 条数与其中 `llm==true` 的条数（长跑默认开 LLM）。
5. **尾部连续 VERIFIED 天数** >= `--days`；存在 `finish` 事件时**核对自述**：`code` 必须与
   本工具结论同向（自称达标而判未达标、或反之，都算账本自相矛盾）、`verified_streak` 不同则记信息项。
6. **账本内部自洽**（deputy-lead `docs/_verify-run3-limits.md` §6 加固项）：
   - `t` 不许回退（全局），每天 `day_start.t <= day_end.t`；
   - 跨日必须**恰好 +1 天**（按 28 天/季折算绝对日序），不是"日期字符串不一样"（盲区 B5）；
   - `checks.watered_outdoor=true` 与 `final_water.dry>0` 不许同时出现（盲区 B4）；
   - 当天 0 个阶段也自称 VERIFIED ⇒ 信息项（盲区 B6：0 步不能自证做过事）；
   - 没有 `finish` 事件 ⇒ 信息项（长跑可能被中断）。

**能力边界（必读）**：本工具是**账本检查器，不是世界校验器** —— 完全自洽的伪造账本
（K 系列）照样通过。真机验收必须叠加外部证据：存档 `mtime`/`size` 每天前进、SMAPI
`Synchronizing 'NewDay'` / `SaveGame.Save()` 次数与天数一致、quit 前 live `/observe`
与末尾 `day_end.final` 对账。详见 `docs/_verify-run3-limits.md` §5/§7。

退出码：0 = 达标；1 = 未达标；2 = journal 读不出来。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from typing import Any


def load(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as exc:  # noqa: BLE001 - 复核工具要如实报告坏行
                rows.append({"event": "_bad_line", "lineno": lineno, "error": str(exc)})
                continue
            obj["_lineno"] = lineno
            rows.append(obj)
    return rows


def latest_journal(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.exists(explicit) else None
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cands = glob.glob(os.path.join(here, "logs", "longrun-*.jsonl"))
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def day_key(row: dict[str, Any]) -> str:
    day = row.get("day")
    if isinstance(day, (list, tuple)) and len(day) >= 3:
        return f"{day[1]} {day[2]}"
    if day is not None:
        return str(day)
    for holder in ("final", "before", "after", "decision"):
        sub = row.get(holder)
        if isinstance(sub, dict) and isinstance(sub.get("day"), (list, tuple)):
            d = sub["day"]
            return f"{d[1]} {d[2]}" if len(d) >= 3 else str(d)
    return "?"


def _tile_count(stage: dict[str, Any]) -> int:
    """阶段的目标格数：longrun 的 day_end.stages[].tiles 是格子列表。"""
    tiles = stage.get("tiles")
    if isinstance(tiles, (list, tuple)):
        return len(tiles)
    try:
        return int(tiles or 0)
    except (TypeError, ValueError):
        return 0


_SEASON_INDEX = {
    "spring": 0,
    "summer": 1,
    "fall": 2,
    "winter": 3,
    "春": 0,
    "夏": 1,
    "秋": 2,
    "冬": 3,
}


def _day_ordinal(day: Any) -> int | None:
    """把 [年, 季, 日] 折成绝对日序（28 天/季、4 季/年）；认不出返回 None。

    用途：跨日证据要"恰好 +1 天"，不能只判"日期字符串与 day_start 不一样"
    （deputy-lead `docs/_verify-run3-limits.md` 盲区 B5：跨两天、跨月也会"不一样"）。
    """
    if not isinstance(day, (list, tuple)) or len(day) < 3:
        return None
    year, season, dom = day[0], day[1], day[2]
    if isinstance(season, str):
        idx = _SEASON_INDEX.get(season.strip().lower())
    elif isinstance(season, int):
        idx = season
    else:
        idx = None
    try:
        year_i = int(year)
        dom_i = int(dom)
    except (TypeError, ValueError):
        return None
    if idx is None or not (0 <= idx <= 3) or not (1 <= dom_i <= 28):
        return None
    return ((year_i - 1) * 4 + idx) * 28 + (dom_i - 1)


def _day_of(row: dict[str, Any]) -> Any:
    """从一行 journal 里取 [年, 季, 日]（顶层 day，或 final/before/after.day）。"""
    day = row.get("day")
    if isinstance(day, (list, tuple)):
        return day
    for holder in ("final", "before", "after"):
        sub = row.get(holder)
        if isinstance(sub, dict) and isinstance(sub.get("day"), (list, tuple)):
            return sub["day"]
    return None


def build_days(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    days: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for row in rows:
        ev = row.get("event")
        if ev == "day_start":
            cur = {
                "key": day_key(row),
                "start_lineno": row.get("_lineno"),
                "start_day": _day_of(row),
                "t_start": row.get("t"),
                "stages": [],
                "ended_by": "",
                "ended_reason": "",
                "final": {},
                "day_after": None,
                "end_day": "?",
                "sleep_ok": False,
                "sleep_fail": 0,
                "cross_day": False,
                "excuse": False,
                "verified": None,
                "checks": {},
                "end": {},
            }
            days.append(cur)
            continue
        if cur is None:
            continue
        if ev in ("no_intents", "plot_exhausted", "policy_fallback"):
            cur["excuse"] = True
        if ev == "sleep" and str(row.get("reason") or "").startswith(("no_work", "night", "stamina")):
            cur["excuse"] = True
        if ev == "sleep":
            if row.get("ok"):
                cur["sleep_ok"] = True
            else:
                cur["sleep_fail"] += 1
        elif ev == "stage":
            # ⚠ legacy：longrun 目前不写 event=="stage"（只写 day_end.stages）。
            # 这里只作历史账本的兜底；权威口径永远是 day_end.stages。
            cur["stages"].append(row)
        elif ev == "day_end":
            cur["ended_by"] = row.get("ended_by", "")
            cur["ended_reason"] = row.get("ended_reason", "")
            cur["final"] = row.get("final") or {}
            cur["checks"] = row.get("checks") or {}
            cur["verified"] = row.get("verified")
            cur["t_end"] = row.get("t")
            # day_end 自带按日汇总（比逐条 stage 事件更权威）
            cur["end"] = {
                k: row.get(k)
                for k in (
                    "day_text",
                    "ok_steps",
                    "skipped_steps",
                    "failed_steps",
                    "stages",
                    "outcomes",
                    "notes",
                    "final_water",
                )
            }
            fin_key = day_key({"final": cur["final"]}) if cur["final"] else "?"
            # task-38：`final` 是**睡前**快照（浇水的证据就存在它里面），拿它判跨日永远判不出
            # 真账本的跨日（全天都写睡觉失败时才被"整段跳过浇水检查"遮住）。睡后重新观测到的
            # 那一天在 `day_after` 里 —— 优先用它，其次才退回 `final`（兼容旧账本/合成账本）。
            cur["day_after"] = row.get("day_after")
            after_key = day_key({"final": {"day": cur["day_after"]}}) if cur["day_after"] else "?"
            if after_key != "?":
                cur["end_day"] = after_key
                cur["cross_day"] = after_key != cur["key"]
            else:
                cur["end_day"] = fin_key
                cur["cross_day"] = bool(cur["final"]) and fin_key != cur["key"]
            cur["end_lineno"] = row.get("_lineno")
    return days


def report(rows: list[dict[str, Any]], *, target_days: int) -> tuple[bool, dict[str, Any]]:
    bad_lines = [r for r in rows if r.get("event") == "_bad_line"]
    events = Counter(r.get("event") for r in rows)
    days = build_days(rows)

    problems: list[str] = []
    infos: list[str] = []

    # task-15：同一阶段种类当天跑多轮时，longrun 用 `stage_midway_leftover` 显式记录"更早一轮
    # leftover>0、最后一轮 ==0"（遮蔽）。这里按天收好，逐日只记信息项 —— 它证明遮蔽已被记录。
    midway_by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("event") == "stage_midway_leftover":
            midway_by_day.setdefault(day_key(r), []).append(r)

    # 0. 时间轴自洽（deputy-lead `docs/_verify-run3-limits.md` 盲区 B2）：t 回退只记信息项。
    #    理由：t 是 longrun 自己的 time.time() 读数，系统时钟回拨（NTP）会让真长跑也"回退"，
    #    把它判成问题会误杀真机的 3 日验收 —— 记账自洽性不能盖过验收入口。
    last_t: float | None = None
    last_lineno: Any = None
    backwards: list[str] = []
    for r in rows:
        t = r.get("t")
        if not isinstance(t, (int, float)):
            continue
        if last_t is not None and t < last_t:
            backwards.append(f"行 {r.get('_lineno')} t={t} < 行 {last_lineno} t={last_t}")
        last_t, last_lineno = t, r.get("_lineno")
    for b in backwards[:3]:
        infos.append(f"journal 时间戳回退（自述 t，可能是时钟回拨）：{b}")
    if len(backwards) > 3:
        infos.append(f"另有 {len(backwards) - 3} 处时间戳回退未逐条列出")

    for d in days:
        name = d["key"]
        end_stats = d.get("end") or {}
        checks = d.get("checks") or {}
        stage_recs = [s for s in (end_stats.get("stages") or []) if isinstance(s, dict)]
        sum_failed = sum(int(s.get("failed") or 0) for s in stage_recs)
        sum_failed_any = sum(int(s.get("failed_any") or 0) for s in stage_recs)
        # leftover 口径（Lead 对 task-15 的权威定义）= **按阶段种类取当天最后一条记录**再求和，
        # 且只算"有目标的阶段"（`tiles > 0`；0 目标阶段不许拖黑当天）。
        # 理由：同一阶段种类当天可能跑多轮（种子用完先停一次、买到种子又把同一批做完），
        # 字面相加会把世界完全达标的一天判成 needs_review —— 阶段后置条件是**日级**的。
        # longrun 侧同一口径：`brain/agentfarm/longrun.py:1754-1758`（`last_by_stage`）。
        last_by_stage: dict[str, dict[str, Any]] = {}
        for s in stage_recs:
            last_by_stage[str(s.get("stage") or "")] = s
        leftover_targeted = sum(int(s.get("leftover") or 0) for s in last_by_stage.values()
                                if _tile_count(s) > 0)
        leftover_zero_target = sum(int(s.get("leftover") or 0) for s in last_by_stage.values()
                                   if _tile_count(s) <= 0)
        legacy_failed = sum(int(s.get("failed") or 0) for s in d["stages"])
        for r in midway_by_day.get(name, []):
            infos.append(
                f"[{name}] 阶段 {r.get('stage')} 当天更早一轮 leftover={r.get('leftover')}"
                f"（tiles={r.get('tiles')}、round={r.get('round')}）而最后一轮已做净"
                " ⇒ 按日级口径以最后一轮为准（遮蔽已被显式记录）"
            )
        # 遮蔽可见性（不依赖 longrun 额外发事件）：同一阶段种类的更早记录就在 `day_end.stages` 里，
        # 直接推导 —— "更早一轮 leftover>0、最后一轮 ==0" 时把遮蔽写出来，复核的人不必自己去翻数组。
        kinds: dict[str, list[dict[str, Any]]] = {}
        for s in stage_recs:
            kinds.setdefault(str(s.get("stage") or ""), []).append(s)
        for kind, recs in kinds.items():
            if len(recs) < 2:
                continue
            earlier = max(int(s.get("leftover") or 0) for s in recs[:-1])
            if earlier > 0 and int(recs[-1].get("leftover") or 0) == 0:
                extra = "；longrun 另记了 stage_midway_leftover 事件" if midway_by_day.get(name) else ""
                infos.append(
                    f"[{name}] 阶段 {kind} 当天共 {len(recs)} 条记录：更早一轮 leftover={earlier}"
                    f"、最后一轮 0 ⇒ 按日级口径以最后一轮为准（遮蔽已显式列出）{extra}"
                )
        if sum_failed_any > sum_failed:
            infos.append(
                f"[{name}] failed_any={sum_failed_any} > failed={sum_failed}：另有 "
                f"{sum_failed_any - sum_failed} 次失败是环境挡路/无结论后重试做成（不计当天硬失败）"
            )

        def _water_problems() -> None:
            """浇水证据（log-analyst `docs/_analyze-farmcounts.md` §6/§7）：窗口 `tiles[]` 的
            crops/unwatered_crops 在室内恒 0（run2 实证：day_end.final 是 FarmHouse crops=0，
            而 checks.crops_watered=true 白过），且 Mod 的 farm.unwateredCrops 用的是
            HoeDirt.needsWatering()（只读 CropData.NeedsWatering、不看浇水状态）⇒ 两者都
            不能当浇水证据。必须由 longrun 写 `checks.watered_outdoor`（见 task-19）。

            **本检查与 `ended_by` 无关**（log-analyst 2026-10-13 彩排复核 §口径差 1）：原先它写在
            `ended_by=="sleep"` 分支里 ⇒ 睡觉失败的那天会**静默跳过**浇水验收（彩排两天都是
            `sleep_failed`，于是工具没报"缺 watered_outdoor"，而该字段当时确实缺）。"没睡成"
            不等于"浇水不用查"，故两条分支都要执行（对本来就判红的日子只是多一条明示，不会把
            任何 exit 0 的账本翻红）。
            """
            watered_outdoor = checks.get("watered_outdoor")
            if watered_outdoor is None:
                problems.append(
                    f"[{name}] 缺 farm 级/户外浇水证据：checks.watered_outdoor 未写"
                    "（窗口 unwatered_crops 在室内恒 0，不作为证据；缺失 ≠ 通过）"
                )
            elif watered_outdoor is False:
                problems.append(f"[{name}] checks.watered_outdoor=false（睡前还有没浇的作物）")
            unwatered = d["final"].get("unwatered_crops")
            if unwatered not in (0, None):
                problems.append(f"[{name}] 睡前 unwatered_crops={unwatered!r}（窗口口径，要求 0）")
            if checks.get("crops_watered") is False:
                problems.append(f"[{name}] checks.crops_watered=false（窗口口径，睡前还有没浇的作物）")

        # 0. 字段缺失不得当成通过（deputy-lead 负例 A：day_end 整块省略 verified/checks）
        if d["verified"] is None:
            problems.append(f"[{name}] day_end 缺 verified 字段（缺失 ≠ 通过）")
        if d["ended_by"] != "sleep":
            problems.append(f"[{name}] ended_by={d['ended_by'] or '?'}（不是我们主动睡过去的）")
            _water_problems()
        else:
            if not d["sleep_ok"]:
                problems.append(f"[{name}] ended_by=sleep 但 journal 里没有一次成功的 sleep 证据")
            if not d["cross_day"]:
                problems.append(
                    f"[{name}] 缺跨日证据：睡后观测到的日期与 day_start 相同"
                    f"（day_after={d.get('day_after')!r}、final={d['final'].get('day')!r}）"
                )
            _water_problems()
        if checks.get("no_hard_failures") is False:
            problems.append(f"[{name}] checks.no_hard_failures=false（当天有硬失败步骤）")
        # 失败数一律以 day_end.stages 求和为准，并与 failed_steps 交叉核对（负例 B：只信自述）
        # task-15 之后两侧同口径：stage 的 `failed` 与日级 `failed_steps` 都只数"目标仍未完成的
        # 失败"（全量另记 `failed_any`）⇒ 正常应严格相等。对 task-15 之前的旧账本（stage 侧记的是
        # 全部失败步）仍保留差额容错：**差额必须被环境挡路/无结论计数完全解释**，解释不完就是
        # 自述在洗账（负例 B 的口径不变：delta 不能被解释 ⇒ 问题）。
        sum_env = sum(int(s.get("env_block_count") or s.get("env_block") or 0) for s in stage_recs)
        sum_incon = sum(int(s.get("inconclusive_count") or s.get("inconclusive") or 0) for s in stage_recs)
        failed_field = end_stats.get("failed_steps")
        if failed_field is None:
            failed_field = sum_failed or legacy_failed
        else:
            delta = sum_failed - int(failed_field)
            if delta < 0:
                problems.append(
                    f"[{name}] 自述 failed_steps={failed_field} 比 day_end.stages 求和 {sum_failed} 还多（账目不可信）"
                )
            elif delta > sum_env + sum_incon:
                problems.append(
                    f"[{name}] 自述 failed_steps={failed_field} 比 day_end.stages 求和 {sum_failed} 少 {delta}，"
                    f"而环境挡路 {sum_env} + 无结论 {sum_incon} 解释不完（账目不可信）"
                )
            elif delta:
                infos.append(
                    f"[{name}] failed_steps={failed_field} < stages 求和 {sum_failed}；差额 {delta} = "
                    f"环境挡路 {sum_env} + 无结论 {sum_incon}（task-15 ④ 口径，不计为当天硬失败）"
                )
        if int(failed_field or 0):
            problems.append(f"[{name}] 当天 stages 硬失败 {failed_field} 格")
        if sum_env or sum_incon:
            infos.append(f"[{name}] 环境挡路失败 {sum_env} 格、无结论失败 {sum_incon} 格（信息项，不改结论）")
        if d["verified"] is False:
            problems.append(f"[{name}] day_end verified=false")
        if d["sleep_fail"]:
            problems.append(f"[{name}] 当天有 {d['sleep_fail']} 次 sleep 失败（回执 ok=false）")

        # 跨日必须是"恰好 +1 天"（盲区 B5）：只判"字符串不一样"会把跨两天/跨月放过去。
        if d["ended_by"] == "sleep" and d["cross_day"]:
            o0 = _day_ordinal(d.get("start_day"))
            o1 = _day_ordinal(d.get("day_after") or d["final"].get("day"))
            end_day_text = d.get("day_after") or d["final"].get("day")
            if o0 is None or o1 is None:
                infos.append(
                    f"[{name}] 跨日天数无法核对（day 字段不是 [年,季,日]："
                    f"start={d.get('start_day')!r} end={end_day_text!r}）"
                )
            elif o1 - o0 != 1:
                problems.append(
                    f"[{name}] 跨日不是恰好 +1 天（start={d.get('start_day')!r} → end={end_day_text!r}）"
                )
        # 当天窗口 t_start <= t_end（盲区 B2）：同样只记信息项（自述时间戳，时钟回拨会误杀）
        t0, t1 = d.get("t_start"), d.get("t_end")
        if isinstance(t0, (int, float)) and isinstance(t1, (int, float)) and t1 < t0:
            infos.append(f"[{name}] 当天时间轴倒挂（自述 t）：day_start t={t0} > day_end t={t1}")
        # final_water 与 checks.watered_outdoor 互检（盲区 B4：两份自述不许自相矛盾）
        fw = end_stats.get("final_water")
        if isinstance(fw, dict):
            dry = fw.get("dry")
            if checks.get("watered_outdoor") is True and isinstance(dry, (int, float)) and dry > 0:
                problems.append(
                    f"[{name}] checks.watered_outdoor=true 但 final_water.dry={dry}（账本自相矛盾）"
                )
            # task-19 要求 5④：**没有任何户外快照**时必须如实 False/缺省，禁止默认 true。
            # window 口径覆盖 0 格 = 当天没有户外快照 ⇒ 这条 true 在账本里自相矛盾（证据来源为空）。
            # 这不是世界校验（本工具仍是账本检查器），只是抓"自述与自己的证据口径打架"。
            if (
                checks.get("watered_outdoor") is True
                and fw.get("scope") == "window"
                and int(fw.get("tiles") or 0) == 0
            ):
                problems.append(
                    f"[{name}] checks.watered_outdoor=true 但 final_water.scope=window 且覆盖 0 格"
                    "（当天没有任何户外快照）⇒ 该 true 不可采信：task-19 要求 5④ 规定此时必须如实"
                    " False/缺省，禁止默认 true"
                )
        elif checks.get("watered_outdoor") is True:
            infos.append(
                f"[{name}] checks.watered_outdoor=true 但账本没写 final_water"
                "（无法核对证据来源；缺证据 ≠ 通过，也不额外判问题）"
            )
        # run3 病灶专用判据（Lead 2026-10-13，取代先前那条会误报的"final.location 必须是 Farm"）：
        # 以 no_work 收尾的一天，睡前**不许还有干作物**。背景：run3 的 spring 19–22 四天都是
        # "人在 FarmHouse（窗口口径），把户外 33 格干作物当成'今天没活'"，于是连续 4 天连睡、
        # 时钟空转、账本还一路 ok。正常的成功一天是"走回 FarmHouse → 上床 → 睡"，所以
        # `final.location` 本来就可能是 FarmHouse —— 位置不是判据，**"no_work 却有干作物"才是**。
        _end_reason = str(d.get("ended_reason") or "")
        if _end_reason.startswith("no_work") and isinstance(fw, dict):
            _dry = fw.get("dry")
            if isinstance(_dry, (int, float)) and _dry > 0:
                problems.append(
                    f"[{name}] ended_reason 以 no_work 开头，但 final_water.dry={_dry}"
                    "（户外还有干作物却判\"今天没活\" ⇒ run3 连睡病复发；"
                    "查 `_farm_scope_work`/`work_reasons` 的 fail-closed 路径，见 task-41 第 10 条）"
                )
        # 0 步也能 VERIFIED（盲区 B6）：当天一个阶段都没有、却自称达标 ⇒ 必须有"确实无活可做"的
        # 证据（no_intents / plot_exhausted / policy_fallback / sleep 理由是 no_work/night/stamina），
        # 否则不允许用"什么都没做"换一天达标（负例 K2）。
        if d["verified"] is True and not stage_recs and not d["stages"]:
            reason = str(d.get("ended_reason") or "")
            excused = bool(d.get("excuse")) or reason.startswith(("no_work", "night", "stamina"))
            if excused:
                infos.append(f"[{name}] 当天 0 个阶段且自称 VERIFIED，但有\"无活可做\"证据（{reason or '事件'}）⇒ 接受")
            else:
                problems.append(
                    f"[{name}] 当天 0 个阶段却自称 VERIFIED，且没有任何\"无活可做\"的证据"
                    "（0 步不能自证做过事）"
                )

        # 3b. 阶段后置条件：无论 checks.no_unmet_stages 在不在，都按 day_end.stages 自算并比对
        unmet = checks.get("no_unmet_stages")
        if unmet is not None and bool(unmet) != (leftover_targeted == 0):
            problems.append(
                f"[{name}] checks.no_unmet_stages={unmet} 与自算不一致"
                f"（有目标阶段遗留 leftover={leftover_targeted} 格）"
            )
        # 自述说"有阶段没做完"就一律算问题，**不因自算结果与它一致而放行**
        # （deputy-lead 负例 D：checks.no_unmet_stages=false 与 stages.leftover=5 一致地没做完，
        #   且 day_end.verified 自述 true ⇒ 旧口径零问题。工具的意义就是不信自述。）
        if unmet is False:
            problems.append(
                f"[{name}] checks.no_unmet_stages=false（有阶段后置条件未成立"
                f"；自算有目标阶段 leftover={leftover_targeted} 格）"
            )
        if unmet is None and leftover_targeted:
            problems.append(f"[{name}] 当天有阶段遗留目标 leftover={leftover_targeted}（阶段没做完）")
        if leftover_zero_target:
            problems.append(
                f"[{name}] 0 目标阶段 leftover={leftover_zero_target}"
                "（task-15 修 A 后应为 0；请查 stage_no_target 分支）"
            )

    # 3c. 异常事件（"人不在场也出过事"）
    for code, label in (
        ("bridge_down", "bridge 掉线"),
        ("watchdog_stop", "watchdog 判定 STOP"),
        ("modal_timeout", "模态等待超时"),
        ("no_day_progress", "跨日没有推进"),
    ):
        n = events.get(code, 0)
        if n:
            problems.append(f"journal 里出现 {label} ×{n}")

    streak = 0
    for d in reversed(days):
        if d["ended_by"] == "sleep" and d["cross_day"] and d["verified"] is True:
            streak += 1
        else:
            break

    finish = next((r for r in reversed(rows) if r.get("event") == "finish"), None)
    decisions = [r for r in rows if r.get("event") == "decision"]
    llm_true = sum(1 for r in decisions if r.get("llm"))

    # finish 自述必须与本工具的结论同向（盲区 B1：K3 账本自称 code=1/streak=0 却全绿）
    def _ok_now() -> bool:
        return streak >= target_days and not problems

    if finish is not None:
        f_code = finish.get("code")
        f_days = finish.get("days")
        f_streak = finish.get("verified_streak")
        # (a) finish 自身必须自洽：code==0 ⇔ verified_streak >= days
        if isinstance(f_code, int) and isinstance(f_streak, int) and isinstance(f_days, int):
            if (f_code == 0) != (f_streak >= f_days):
                problems.append(
                    f"finish 自身不自洽：code={f_code} 与 verified_streak={f_streak}/days={f_days} 不符"
                )
        # (b) 与本工具结论同向 —— 只在两侧目标天数可比时才算问题（否则 --days 不同会误报）
        comparable = isinstance(f_days, int) and f_days == target_days
        if comparable and _ok_now() and f_code not in (0, None):
            problems.append(f"finish 自述 code={f_code}（自称未达标）而本工具判定达标（账本自相矛盾）")
        if comparable and (not _ok_now()) and f_code == 0:
            if problems:
                # 已经有别的问题在顶着未达标 ⇒ 根因在别处，只记信息项，避免"一个根因两条"并把矛头指向 finish
                infos.append(
                    "finish 自述 code=0（自称达标）而本工具判定未达标 —— 已由上面的问题解释，不重复计为问题"
                )
            else:
                problems.append("finish 自述 code=0（自称达标）而本工具判定未达标（账本自相矛盾）")
        if (not comparable) and f_code == 0 and not _ok_now():
            infos.append(
                f"finish 自述 code=0 而本工具判定未达标，但两侧目标天数不同（--days={target_days} vs finish.days={f_days}）"
                "⇒ 只作信息项"
            )
        if isinstance(f_streak, int) and f_streak != streak:
            infos.append(
                f"finish 自述 verified_streak={f_streak} 与本工具尾部连续天数 {streak} 不同"
                "（两侧 target_days 口径可能不同，需人工核）"
            )
    elif rows:
        infos.append("journal 里没有 finish 事件（长跑可能被中断；不以它当证据）")

    ok = _ok_now()
    summary = {
        "journal": None,
        "bad_lines": len(bad_lines),
        "rows": len(rows),
        "events": dict(sorted(events.items(), key=lambda kv: (-kv[1], kv[0]))),
        "days": [
            {
                "day": d["key"],
                "ended_by": d["ended_by"],
                "ended_reason": d["ended_reason"],
                "cross_day": d["cross_day"],
                "sleep_ok": d["sleep_ok"],
                "sleep_fail": d["sleep_fail"],
                "unwatered": d["final"].get("unwatered_crops"),
                "crops": d["final"].get("crops"),
                "money": d["final"].get("money"),
                "stages": len((d.get("end") or {}).get("stages") or []) or len(d["stages"]),
                "ok_steps": (d.get("end") or {}).get("ok_steps")
                if (d.get("end") or {}).get("ok_steps") is not None
                else sum(int(s.get("ok") or 0) for s in d["stages"]),
                "skipped": (d.get("end") or {}).get("skipped_steps")
                if (d.get("end") or {}).get("skipped_steps") is not None
                else sum(int(s.get("skipped") or 0) for s in d["stages"]),
                "failed": (d.get("end") or {}).get("failed_steps")
                if (d.get("end") or {}).get("failed_steps") is not None
                else sum(int(s.get("failed") or 0) for s in d["stages"]),
                "checks": d.get("checks") or {},
                "verified": d["verified"],
            }
            for d in days
        ],
        "verified_streak_tail": streak,
        "target_days": target_days,
        "decisions": len(decisions),
        "decisions_llm": llm_true,
        "finish": {k: v for k, v in (finish or {}).items() if k != "_lineno"},
        "problems": problems,
        "infos": infos,
        "verdict": "VERIFIED" if ok else "needs_review",
    }
    return ok, summary


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="独立复核 longrun journal 的 3 日验收")
    ap.add_argument("--journal", default=None, help="journal 路径（默认取 logs 下最新一份 longrun-*.jsonl）")
    ap.add_argument("--days", type=int, default=3, help="要求的尾部连续 VERIFIED 天数（默认 3）")
    ap.add_argument("--json", action="store_true", help="只打印 JSON")
    args = ap.parse_args(argv)

    path = latest_journal(args.journal)
    if not path:
        print("找不到 journal（--journal 指定，或 logs\\longrun-*.jsonl 不存在）")
        return 2
    rows = load(path)
    ok, summary = report(rows, target_days=args.days)
    summary["journal"] = path

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    print(f"journal: {path}")
    print(f"行数 {summary['rows']}  坏行 {summary['bad_lines']}  事件 {summary['events']}")
    print("")
    print(f"{'日':<12}{'ended_by':<14}{'跨日':<6}{'睡前未浇':<9}{'作物':<6}{'钱':<6}{'阶段':<5}{'ok':<5}{'skip':<6}{'fail':<6}verified")
    for d in summary["days"]:
        print(
            f"{d['day']:<12}{d['ended_by'] or '?':<14}{str(d['cross_day']):<6}"
            f"{str(d['unwatered']):<9}{str(d['crops']):<6}{str(d['money']):<6}"
            f"{d['stages']:<5}{d['ok_steps']:<5}{d['skipped']:<6}{d['failed']:<6}{d['verified']}"
        )
    print("")
    print(f"decision {summary['decisions']} 条（其中 LLM {summary['decisions_llm']} 条）")
    if summary["finish"]:
        print(f"finish: {summary['finish']}")
    print(f"尾部连续 VERIFIED 天数 {summary['verified_streak_tail']} / 要求 {summary['target_days']}")
    if summary.get("infos"):
        print("")
        print("信息（不影响结论）：")
        for i in summary["infos"]:
            print(f"  - {i}")
    if summary["problems"]:
        print("")
        print("问题：")
        for p in summary["problems"]:
            print(f"  - {p}")
    print("")
    print(f"结论：{summary['verdict']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
