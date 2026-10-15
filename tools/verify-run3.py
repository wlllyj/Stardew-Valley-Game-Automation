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
4. **LLM 覆盖**：`decision` 条数、其中 `llm==true`（发起过模型调用）与 `source=="llm"`（模型结果真被采纳）
   两档口径 —— 二者之差是 `deterministic_fallback`（模型答了但被拒/截断后兜底），**不算模型产出**
   （Lead 2026-10-14 裁定，回答 log-analyst 在 run2 L17 上发现的口径分歧）。
5. **尾部连续 VERIFIED 天数** >= `--days`；存在 `finish` 事件时**核对自述**：`code` 必须与
   本工具结论同向（自称达标而判未达标、或反之，都算账本自相矛盾）、`verified_streak` 不同则记信息项。
   【口径（Lead 2026-10-15，run7 后）】**达标窗口是"尾部连续 N 天"**：只有落在窗口内的那几天的问题
   （以及不带 `[day]` 前缀的全局问题）才是 fatal；窗口**之外**日子的问题降级为 `history_problems`
   逐条列出、不影响结论。理由：长跑允许早期日子不达标后自主恢复（task-73 的 stuck 翻篇就是为此），
   否则"先坏后好"的账本永远过不了。窗口本身没打满时（streak < --days）不降级，维持原判。
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
                    "unreachable",
                    "unreachable_tiles",
                    "unreachable_bound",
                    "unreachable_exempt",
                    # task-63：`tool_ineffective`（游戏拒绝该工具动这格）的日级有界豁免
                    # —— 与 task-52 的 unreachable 是两套独立口径，各自留痕。
                    "refused",
                    "refused_tiles",
                    "refused_bound",
                    "refused_exempt",
                    "attempted",
                    # task-68：`encircled`（四邻连落脚点都没有 = 被树/桩/大石围住）**单独成类**，
                    # 不进 `unreachable_exempt` 分子；`frontier_clear`/`clear_neighbor` 只走 journal。
                    "encircled",
                    "encircled_tiles",
                    # task-78：上界基数（= 发起过动作且**不是** encircled 的步数）。账号本缺失时
                    # 工具按 `attempted − encircled` 自算，绝不采信"账本更大的上界"。
                    "bound_basis",
                    # task-73：这一天是 stuck 但已经睡过去翻篇（有界 MAX_STUCK_FLUSH）。
                    "stuck_flushed",
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

    # task-52（Lead 2026-10-14）：`unreachable`（四邻都站不过去 / A* 算不出路）按政策**不算当天
    # 硬失败**。本工具不判世界，只做两件事：①把账本里的 unreachable 计数报成信息项；
    # ②用 journal 里带"站不过去/寻路无法到达"字样的事件**独立自算**一遍，两者对不上就如实记
    # 信息项（缺失 ≠ 通过：字段缺了也要有自算值说话；防洗白靠"全不可达 + 0 成功"由真空日闸门兜）。
    _UNREACH_MARKS = ("四邻都站不过去", "寻路无法到达", "无法到达", "unreachable", "A* 未算出路径")
    # ⚠ 会话级计数（不是日级）：`build_days` 按 `day_start` 切会话，**同一天重试**会产生两条
    # 同 key 的日记录（run6 就是 summer 4 跑了两轮）。日级汇总会把两轮合计（84）去比单轮账本
    # （各 42）⇒ 假"不一致"。这里用 (day_key, start_lineno) 精确定位到会话。
    unreach_by_day: dict[tuple[str, Any], int] = {}
    unreach_tiles_by_day: dict[tuple[str, Any], set[tuple[Any, Any]]] = {}
    _cur_key: tuple[str, Any] | None = None
    for r in rows:
        if r.get("event") == "day_start":
            _cur_key = (day_key(r), r.get("_lineno"))
            continue
        if _cur_key is None or r.get("event") not in ("blocked", "stage_exhausted", "unreachable"):
            continue
        blob = " ".join(str(r.get(k) or "") for k in ("reason", "note", "tile", "tiles"))
        if not any(m in blob for m in _UNREACH_MARKS):
            continue
        unreach_by_day[_cur_key] = unreach_by_day.get(_cur_key, 0) + 1
        tile = r.get("tile")
        if isinstance(tile, (list, tuple)) and len(tile) >= 2:
            unreach_tiles_by_day.setdefault(_cur_key, set()).add((tile[0], tile[1]))

    # task-63（Lead 2026-10-14）：`till` 的 `tool_ineffective`（游戏拒绝该工具动这格）按政策
    # **不算当天硬失败** ⇒ 逐格 journal `tool_refused` / 日级 `refused_summary`。与 task-52 的
    # unreachable 是**两套独立口径**：这里只做"账本计数 vs journal 自算"的信息项 + 一条硬闸门
    # （`checks.refused_within_bound is False` ⇒ 上界越界 = 洗白风险）。缺字段只记信息项，不当通过。
    refused_by_day: dict[tuple[str, Any], int] = {}
    refused_tiles_by_day: dict[tuple[str, Any], set[tuple[Any, Any]]] = {}
    _cur_key2: tuple[str, Any] | None = None
    for r in rows:
        if r.get("event") == "day_start":
            _cur_key2 = (day_key(r), r.get("_lineno"))
            continue
        if _cur_key2 is None or r.get("event") != "tool_refused":
            continue
        refused_by_day[_cur_key2] = refused_by_day.get(_cur_key2, 0) + 1
        tile = r.get("tile")
        if isinstance(tile, (list, tuple)) and len(tile) >= 2:
            refused_tiles_by_day.setdefault(_cur_key2, set()).add((tile[0], tile[1]))

    # task-68（Lead 2026-10-14）：dev-coder 把「被围住」从 run6 的 42 格里分出来，单独成类
    # `encircled`（四邻连落脚点都没有 ⇒ 不封格、不计入 unreachable、不进任何豁免分子），
    # 并新增 `frontier_clear`（所有指定目标都不可达时，至少清一格自己够得着的可清障格）
    # 与 `clear_neighbor`（为开路清掉的邻格）。本工具只**自算 + 报信息项**：
    #   ①账本 `day_end.encircled` vs journal 逐格自算（缺失 ≠ 通过）；
    #   ②`frontier_clear` 的 acted 计数（run6 就是"19 秒零动作收工"，这一项让下次一眼看见）；
    #   ③`clear_neighbor` 次数（开路证据）。
    enc_by_day: dict[tuple[str, Any], set[tuple[Any, Any]]] = {}
    frontier_by_day: dict[tuple[str, Any], list[bool]] = {}
    neighbor_by_day: dict[tuple[str, Any], int] = {}
    _cur_key3: tuple[str, Any] | None = None
    for r in rows:
        ev = r.get("event")
        if ev == "day_start":
            _cur_key3 = (day_key(r), r.get("_lineno"))
            continue
        if _cur_key3 is None or ev not in ("encircled", "frontier_clear", "clear_neighbor"):
            continue
        if ev == "encircled":
            tile = r.get("tile")
            if isinstance(tile, (list, tuple)) and len(tile) >= 2:
                enc_by_day.setdefault(_cur_key3, set()).add((tile[0], tile[1]))
        elif ev == "frontier_clear":
            frontier_by_day.setdefault(_cur_key3, []).append(bool(r.get("acted")))
        else:
            neighbor_by_day[_cur_key3] = neighbor_by_day.get(_cur_key3, 0) + 1

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
        # 会话键（同一天重试时两条日记录同 key、不同 start_lineno）：自算计数必须按会话比。
        sess = (name, d.get("start_lineno"))
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
        # task-52：不可达格豁免（信息项，不改结论）。账本字段缺省时用 journal 自算值说话。
        self_unreach = unreach_by_day.get(sess, 0)
        self_tiles = len(unreach_tiles_by_day.get(sess) or ())
        sum_unreach = sum(int(s.get("unreachable") or 0) for s in stage_recs)
        day_unreach = end_stats.get("unreachable")
        field_unreach: int | None = None
        if isinstance(day_unreach, (int, float)):
            field_unreach = int(day_unreach)
        elif sum_unreach:
            field_unreach = sum_unreach
        # task-52 的豁免上界/实扣。**上界必须自算**（task-71：deputy 的 task-54 实测账本写
        # `unreachable_bound=9999` 会被无条件采信 ⇒ 伪造账本 exit 0）。自算公式与 longrun 一致：
        # `max(5, floor(0.2×bound_basis))`；账本值比自算值大 ⇒ problem（放宽豁免=洗白）。
        # task-78：分母从 `attempted` 换成 `bound_basis = attempted − encircled` —— deputy 的对抗
        # 验收用伪造账本 V5 打穿过旧口径（800 次 `encircled` 把上界抬到 200 ⇒ 200 格真不可达被
        # 豁免、exit 0）。被围住的格既不是"走不到"也不是"干了没成"，不该为豁免额度做贡献。
        attempted_day = end_stats.get("attempted")
        attempted_self = sum(int(s.get("attempted") or 0) for s in stage_recs)
        attempted_total = int(attempted_day) if isinstance(attempted_day, (int, float)) else 0
        if not attempted_total:
            attempted_total = attempted_self
        if isinstance(attempted_day, (int, float)) and attempted_self and int(attempted_day) > attempted_self:
            problems.append(
                f"[{name}] day_end.attempted={int(attempted_day)} > stages 求和 {attempted_self}"
                "（抬高分母就能放宽 20% 上界 ⇒ 账目不可信）"
            )
        encircled_day = end_stats.get("encircled")
        encircled_self = sum(int(s.get("encircled") or 0) for s in stage_recs)
        encircled_total = int(encircled_day) if isinstance(encircled_day, (int, float)) else 0
        if not encircled_total:
            encircled_total = encircled_self
        basis_self = max(0, attempted_total - encircled_total)
        _basis = end_stats.get("bound_basis")
        if isinstance(_basis, (int, float)):
            _basis_i = int(_basis)
            # task-81 NIT-1（deputy 对抗验收 ADV-4 实测）：旧写法**先钳后比** ——
            # `basis = min(_basis, basis_self)` 之后再判 `basis != basis_self`，只要自算 > 0
            # 就被 `min()` 钳平 ⇒「账本谎报 bound_basis」这条 problem 永不触发（说谎不留痕）。
            # 正确姿势：**先比较原始账本值，再钳**（方向仍然是 fail-closed，不构成洗白通道）。
            if _basis_i > basis_self:
                problems.append(
                    f"[{name}] 上界基数账本 bound_basis={_basis_i} > 自算={basis_self}"
                    f"（attempted={attempted_total} − encircled={encircled_total}）"
                    "⇒ 基数被放宽，可能把真失败洗成不可达"
                )
                basis = basis_self
            else:
                basis = _basis_i
        else:
            basis = basis_self
        bound_self = max(5, int(0.2 * basis)) if basis else 5
        _bound = end_stats.get("unreachable_bound")
        bound = int(_bound) if isinstance(_bound, (int, float)) else bound_self
        if isinstance(_bound, (int, float)) and bound != bound_self:
            if bound > bound_self:
                problems.append(
                    f"[{name}] 不可达豁免上界账本={bound} > 自算={bound_self}"
                    f"（bound_basis={basis} = attempted {attempted_total} − encircled {encircled_total}）"
                    "⇒ 上界被放宽，可能把真失败洗成不可达"
                )
            else:
                infos.append(
                    f"[{name}] 不可达豁免上界账本={bound} < 自算={bound_self}（更严，信息项）"
                )
        _exempt = end_stats.get("unreachable_exempt")
        if not isinstance(_exempt, (int, float)):
            _exempt = min(bound, self_unreach) if (self_unreach or field_unreach) else 0
        unreach_exempt = max(0, int(_exempt))
        field_tiles_raw = end_stats.get("unreachable_tiles")
        field_tiles = {tuple(t) for t in field_tiles_raw or [] if isinstance(t, (list, tuple)) and len(t) >= 2}
        if unreach_exempt > 0 and self_tiles == 0 and not field_tiles:
            problems.append(
                f"[{name}] 不可达豁免扣了 {unreach_exempt} 格却没写任何坐标"
                "（journal 无 unreachable 逐格事件、day_end.unreachable_tiles 也空 ⇒ 缺失≠通过）"
            )
        if field_unreach is not None or self_unreach:
            src = f"{field_unreach}" if field_unreach is not None else "未写"
            infos.append(
                f"[{name}] 不可达（四邻都站不过去/A* 算不出路）账本={src}、journal 自算={self_unreach} 次"
                f"/{self_tiles} 格、豁免上界 bound={bound}（bound_basis={basis} = attempted {attempted_total} − encircled {encircled_total}）、实际扣除 exempt={unreach_exempt}"
                "（task-52 政策：不计当天硬失败；本行只供复核）"
            )
        # 硬闸门：豁免越界＝洗白风险（把"真失败"混进不可达或抬高 attempted 分母）
        if checks.get("unreachable_within_bound") is False:
            problems.append(
                f"[{name}] checks.unreachable_within_bound=false（不可达豁免超出上界 bound={bound}）"
                "⇒ 可能把真失败/不可动格混进不可达来洗白，必须人工核对 unreachable_tiles"
            )
        if field_unreach is not None and self_unreach and field_unreach != self_unreach:
            infos.append(
                f"[{name}] 不可达计数账本={field_unreach} 与 journal 自算={self_unreach} 不一致"
                "（信息项：同一格可能多次重试，或 journal 按日去重）"
            )
        if checks.get("no_hard_failures") is False and self_unreach and int(failed_field or 0):
            infos.append(
                f"[{name}] 当天有 {failed_field} 格硬失败，其中含不可达 {self_unreach} 次：task-52 之后"
                "不可达应被豁免，请核对 checks.no_hard_failures（豁免后仍 false 才算真失败）"
            )
        # task-63：`till` 被游戏拒绝（tool_ineffective）的日级豁免 —— 与上面 unreachable 独立计数。
        self_refused = refused_by_day.get(sess, 0)
        self_refused_tiles = len(refused_tiles_by_day.get(sess) or ())
        sum_refused = sum(int(s.get("refused") or 0) for s in stage_recs)
        day_refused = end_stats.get("refused")
        field_refused: int | None = int(day_refused) if isinstance(day_refused, (int, float)) else (
            sum_refused or None
        )
        _rbound = end_stats.get("refused_bound")
        rbound_self = max(5, int(0.2 * basis)) if basis else 5
        rbound = int(_rbound) if isinstance(_rbound, (int, float)) else rbound_self
        if isinstance(_rbound, (int, float)) and rbound != rbound_self:
            if rbound > rbound_self:
                problems.append(
                    f"[{name}] 被拒豁免上界账本={rbound} > 自算={rbound_self}"
                    f"（bound_basis={basis}）⇒ 上界被放宽，可能把真失败洗成「游戏拒绝」"
                )
            else:
                infos.append(f"[{name}] 被拒豁免上界账本={rbound} < 自算={rbound_self}（更严，信息项）")
        # task-63 的实扣（账本优先；缺失时按 min(bound, 被拒格数) 自算，与 longrun 同口径）
        _rexempt = end_stats.get("refused_exempt")
        if not isinstance(_rexempt, (int, float)):
            _rexempt = min(rbound, self_refused) if (self_refused or field_refused) else 0
        refused_exempt = max(0, int(_rexempt))
        refused_tiles_raw = end_stats.get("refused_tiles")
        refused_tiles_field = {
            tuple(t) for t in refused_tiles_raw or [] if isinstance(t, (list, tuple)) and len(t) >= 2
        }
        if refused_exempt > 0 and self_refused_tiles == 0 and not refused_tiles_field:
            problems.append(
                f"[{name}] 被拒豁免扣了 {refused_exempt} 格却没写任何坐标"
                "（journal 无 tool_refused 逐格事件、day_end.refused_tiles 也空 ⇒ 缺失≠通过）"
            )
        # task-71：两套豁免不得互相掩护 —— 同一格同时进 unreachable 与 refused 会重复扣减。
        self_unreach_tiles = unreach_tiles_by_day.get(sess) or set()
        self_refused_tile_set = refused_tiles_by_day.get(sess) or set()
        overlap = (set(self_unreach_tiles) | field_tiles) & (set(self_refused_tile_set) | refused_tiles_field)
        if overlap:
            sample = "、".join(f"({int(t[0])},{int(t[1])})" for t in sorted(overlap)[:6])
            problems.append(
                f"[{name}] 同一格同时进两套豁免：{len(overlap)} 格（例 {sample}）"
                "⇒ 可被重复扣减（unreachable + refused），必须人工核对坐标来源"
            )
        if field_refused is not None or self_refused:
            src_r = f"{field_refused}" if field_refused is not None else "未写"
            infos.append(
                f"[{name}] 锄不动被拒（tool_ineffective）账本={src_r}、journal 自算={self_refused} 次"
                f"/{self_refused_tiles} 格、豁免上界 bound={rbound}（task-63 政策：不计当天硬失败；本行只供复核）"
            )
        if field_refused is not None and self_refused and field_refused != self_refused:
            if field_refused >= self_refused:
                infos.append(
                    f"[{name}] 拒绝计数账本={field_refused} ≥ journal 自算={self_refused}"
                    "（信息项：同一格可能被拒两次）"
                )
            else:
                problems.append(
                    f"[{name}] 拒绝计数账本={field_refused} < journal 自算={self_refused}"
                    "（journal 里有 tool_refused 事件而账本没记 ⇒ 账目不可信）"
                )
        if checks.get("refused_within_bound") is False:
            problems.append(
                f"[{name}] checks.refused_within_bound=false（锄不动豁免超出上界 bound={rbound}）"
                "⇒ 可能把真失败混进「游戏拒绝」来洗白，必须人工核对 refused_tiles"
            )
        if d["verified"] is False:
            problems.append(f"[{name}] day_end verified=false")

        # task-68 信息项（不改结论）：被围住 vs 真不可达要分得开；开路证据与"零动作收工"要看得见。
        self_enc = enc_by_day.get(sess) or set()
        field_enc = end_stats.get("encircled")
        field_enc_tiles = {
            tuple(t) for t in (end_stats.get("encircled_tiles") or [])
            if isinstance(t, (list, tuple)) and len(t) >= 2
        }
        if isinstance(field_enc, (int, float)) or self_enc:
            infos.append(
                f"[{name}] 被围住（encircled，四邻无落脚点）账本="
                f"{int(field_enc) if isinstance(field_enc, (int, float)) else '未写'}"
                f"、journal 自算={len(self_enc)} 格"
                f"（不进不可达豁免；单独留痕，供 task-68 口径复核）"
            )
        if len(self_enc) and field_enc_tiles and self_enc != field_enc_tiles:
            infos.append(
                f"[{name}] encircled 坐标对不上：账本 {len(field_enc_tiles)} 格 vs journal {len(self_enc)} 格"
            )
        fz = frontier_by_day.get(sess) or []
        if fz:
            infos.append(
                f"[{name}] frontier_clear 尝试 {len(fz)} 次（真清掉 {sum(1 for x in fz if x)} 次）"
            )
        nb = neighbor_by_day.get(sess) or 0
        if nb:
            infos.append(f"[{name}] 为开路清掉邻格 {nb} 次（clear_neighbor）")
        if d["ended_by"] == "stuck" and not int(end_stats.get("ok_steps") or 0):
            infos.append(
                f"[{name}] stuck 收尾且当天成功动作 0 步（run6 那种零动作收工的形态；"
                "task-68 的 frontier_clear 应让下一次至少真的清掉一格）"
            )
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
        # `no_water`（task-49 的诚实收尾：想浇但确实打不到水）**不**判失败，但要看得见 ——
        # 它是"当天没浇完"的合法解释，也是唯一可能被滥用来早睡的通道；`no_water` 不在
        # `JUSTIFIED_END_REASONS` 里 ⇒ `checks.day_justified` 必为假 ⇒ 当天不可能 verified，
        # 所以这里只记 info，不额外判红。
        if _end_reason.startswith("no_water"):
            infos.append(
                f"[{name}] 诚实收尾 no_water（想浇但拿不到水）⇒ 当天不达标；"
                f"dry={fw.get('dry') if isinstance(fw, dict) else '?'}"
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

        # 真空日/弱日（Lead 2026-10-13，run6 判据 `docs/_run6-criteria.md` §1）：
        # `verified=true` 的一天至少要真的做成过事 —— 有阶段记录但成功动作全 0 ⇒ 判红
        # （完全没有任何阶段记录的情形已由上面那条覆盖）。
        # 成功动作很少或只涉及一个阶段 ⇒ 不判红，只出 info（合法但偏弱的一天，供复核时人读）。
        _ok_self = 0
        if stage_recs:
            for _s in stage_recs:
                try:
                    _ok_self += int(_s.get("ok") or 0)
                except (TypeError, ValueError):
                    pass
        else:
            _end_ok = (d.get("end") or {}).get("ok_steps")
            if isinstance(_end_ok, int):
                _ok_self = _end_ok
        if d["verified"] is True and stage_recs and _ok_self <= 0:
            problems.append(
                f"[{name}] 自称 VERIFIED 但当天成功动作 0 步（有阶段记录、ok 全 0）"
                "（0 步不能自证做过事；查 stage_no_target / `no_work` 分支）"
            )
        elif d["verified"] is True and 0 < _ok_self < 5:
            infos.append(f"[{name}] 弱日：VERIFIED 但成功动作只有 {_ok_self} 步（供复核）")
        if d["verified"] is True and stage_recs and _ok_self >= 5:
            _kinds = {
                str(_s.get("stage") or "")
                for _s in stage_recs
                if int(_s.get("ok") or 0) > 0
            }
            if len(_kinds) < 2:
                infos.append(
                    f"[{name}] VERIFIED 但只涉及一个阶段（{sorted(_kinds)}）⇒ 供复核"
                )

        # 3b. 阶段后置条件：无论 checks.no_unmet_stages 在不在，都按 day_end.stages 自算并比对。
        # task-52/63 起：账本会把"当天不可达且在上界内"与"被游戏拒绝且在上界内"的遗留格从 unmet 里
        # **各自**扣掉 ⇒ 自算值也必须扣同样两笔，否则 run6 会被误判成"自述与自算不一致"。
        # 另有一条与 longrun 同义的防真空：扣完为 0、但当天没有任何成功动作、且两笔豁免都非零时，
        # 账本会写 no_unmet_stages=false（不能靠"全被豁免"换一个达标日）。
        unmet = checks.get("no_unmet_stages")
        effective_leftover = max(0, leftover_targeted - unreach_exempt - refused_exempt)
        _progress = int(_ok_self or 0) > 0
        _vacuum_exempt = effective_leftover == 0 and not _progress and (unreach_exempt + refused_exempt) > 0
        expected_unmet = (effective_leftover == 0) and not _vacuum_exempt
        if unmet is not None and bool(unmet) != expected_unmet:
            problems.append(
                f"[{name}] checks.no_unmet_stages={unmet} 与自算不一致"
                f"（有目标阶段遗留 leftover={leftover_targeted} 格，扣掉不可达豁免 {unreach_exempt}"
                f" + 锄不动豁免 {refused_exempt} 后剩 {effective_leftover} 格、当天成功动作 {_ok_self}"
                f"；期望 {expected_unmet}）"
            )
        # 自述说"有阶段没做完"就一律算问题，**不因自算结果与它一致而放行**
        # （deputy-lead 负例 D：checks.no_unmet_stages=false 与 stages.leftover=5 一致地没做完，
        #   且 day_end.verified 自述 true ⇒ 旧口径零问题。工具的意义就是不信自述。）
        if unmet is False:
            problems.append(
                f"[{name}] checks.no_unmet_stages=false（有阶段后置条件未成立"
                f"；自算有目标阶段 leftover={leftover_targeted} 格）"
            )
        if unmet is None and effective_leftover:
            problems.append(
                f"[{name}] 当天有阶段遗留目标 leftover={effective_leftover}"
                f"（阶段没做完；已扣不可达豁免 {unreach_exempt} + 锄不动豁免 {refused_exempt}）"
            )
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
        # task-50 期间 Lead 补：**版本不符**的账本不能当验收证据（"版本号相同内容不同"的
        # v0.7.17 教训）⇒ 升格为问题项，不是信息项。
        ("mod_version_mismatch", "Mod 版本与脑侧期望不一致（该账本不能当验收证据）"),
    ):
        n = events.get(code, 0)
        if n:
            problems.append(f"journal 里出现 {label} ×{n}")

    # 3d. 其余风险事件只记信息项（Lead 2026-10-14 补）：它们不直接判失败，但 run6 复盘必须
    #     看得见 —— 尤其 `water_far_unavailable`（farm 说还有干作物、但拿不到 dryTiles 坐标）
    #     与 `farm_evidence_unavailable`（室内 + farm 口径不可用），这两条正是 run5 连睡病灶的
    #     相邻风险面；`sell_failed` 是经济闭环的失败面。
    for code, label in (
        ("water_far_unavailable", "窗口外干作物拿不到坐标（旧 Mod/证据不可信）"),
        ("farm_evidence_unavailable", "室内且 farm 口径不可用（守卫按有活处理）"),
        ("sell_failed", "出货（sell）失败"),
        ("zones_failed", "田区划分失败（LLM 田区提示不可用）"),
        ("day_key_resnap_failed", "睡后重新观测失败（跨日证据可能缺）"),
        ("bridge_unavailable", "bridge 瞬时不可用（已重试）"),
        ("env_spin_capped", "同格环境挡路触顶（不再免费重试）"),
        ("budget_exhausted", "预算用尽收尾"),
        ("day_cap", "触发 max-days 上限收尾"),
        ("event_blocked", "游戏事件挂住（硬停等人）"),
        ("llm_trace_failed", "LLM 留痕写盘失败（决策照常，只是没原文可复盘）"),
    ):
        n = events.get(code, 0)
        if n:
            infos.append(f"风险事件：{label} ×{n}（信息项，不改结论）")

    # 3e. task-73（stuck 日有界翻篇）：`MAX_STUCK_FLUSH` 允许"卡死的日子"睡过去翻到第二天
    #     —— 翻篇那天本身 `ended_by=stuck`、`verified=false`（不许洗白），但**翻篇过的日子
    #     绝不允许被记成 verified**（那是"用睡觉绕过没做完的活"）。同时把次数呈现出来，
    #     这样"尾部连续 3 天"的达成分得清"真干活"和"靠翻篇凑天数"。
    flushed_days = [d for d in days if (d.get("end") or {}).get("stuck_flushed") is True]
    for d in flushed_days:
        if d.get("verified") is True:
            problems.append(
                f"[{d['key']}] 该日是 stuck 翻篇（`day_end.stuck_flushed=true`）却记成 verified"
                "（task-73 的翻篇只许翻页、不许洗白；查 _stuck_flush 的 ended_by/verified 写法）"
            )
    n_flush = events.get("stuck_flush", 0)
    n_flush_skip = events.get("stuck_flush_skipped", 0)
    if flushed_days or n_flush:
        infos.append(
            f"stuck 日翻篇：{len(flushed_days)} 天 / journal `stuck_flush` ×{n_flush}"
            f"、`stuck_flush_skipped` ×{n_flush_skip}"
            "（task-73 有界 MAX_STUCK_FLUSH=2；翻篇日必须 verified=false，尾部连续天数必须靠真干活的日子）"
        )
    if events.get("stuck_flush_resnap_failed", 0):
        infos.append(
            f"风险事件：stuck 翻篇后重新观测失败 ×{events['stuck_flush_resnap_failed']}"
            "（跨日证据可能缺）"
        )

    streak = 0
    for d in reversed(days):
        if d["ended_by"] == "sleep" and d["cross_day"] and d["verified"] is True:
            streak += 1
        else:
            break

    # 口径（Lead 2026-10-15，run7 后定）：验收目标是"**尾部**连续 N 个游戏日无人介入达标"，
    # **不是**"整本账本一个毛病都不许有"。run7 实测：summer 3/5 被窗口外那 1 格干作物卡住
    # （task-50 的 far-dry 追两次没够着）、summer 6 靠 task-73 的 stuck 翻篇自己翻过去，
    # 之后 summer 7/8/9 连续三天全绿 —— 早期那几天不该把已达成的连续窗口翻红。
    # 规则：**只有达标窗口内那几天的问题**（以及不带 `[day]` 前缀的全局问题：journal 损坏、
    # finish 自相矛盾、版本不符等）才算 fatal；窗口外的问题降级成 `history_problems`
    # 逐条列出（看得到、可复盘），且**只在 streak 已经够 target_days 时才降级** ——
    # 没打出窗口的失败账本维持原判，不因这条口径变松。
    history_problems: list[str] = []
    if streak >= target_days:
        tail_names = {d["key"] for d in days[-streak:]}
        kept: list[str] = []
        for p in problems:
            head = p[1:].split("]", 1)[0] if p.startswith("[") else ""
            if head and head not in tail_names:
                history_problems.append(p)
            else:
                kept.append(p)
        problems = kept

    finish = next((r for r in reversed(rows) if r.get("event") == "finish"), None)
    decisions = [r for r in rows if r.get("event") == "decision"]
    llm_true = sum(1 for r in decisions if r.get("llm"))
    # `llm=true` 只说明"发起过模型调用"：其中可能有 `source=deterministic_fallback`（模型答了但被拒/截断，
    # 最终决策并非模型产出，run2 L17 就是这种）。真正"模型产出"= `source=="llm"`。两个数都报，
    # 避免 run6 的"LLM 覆盖"虚高（Lead 2026-10-14 裁定）。
    llm_used = sum(1 for r in decisions
                   if r.get("llm") and str(r.get("source") or "") == "llm")
    llm_fallback = llm_true - llm_used
    if llm_fallback:
        infos.append(
            f"LLM 兜底 {llm_fallback} 条：发起过模型调用但最终没用模型结果"
            f"（`source != llm`，多为截断/拒收后的 deterministic_fallback）"
        )

    # 三腿覆盖（Lead 2026-10-14 补）：P3 ⑥ 的目标是"清理障碍 → 开垦 → 播种 → 浇水"，但每日 checks
    # 只盯浇水与硬失败 —— **播种腿有没有真跑过**必须单独看得见，否则"三层过了"会被当成"四层过了"。
    # 只记 info：种子/钱不足时播种腿会合法缺席（task-55 卖余料换种子钱之前就是这样）。
    _LEGS: dict[str, tuple[str, ...]] = {
        "清障/开垦": ("clear_area", "till_area"),
        "播种": ("plant_area", "sow"),
        "浇水": ("water_area",),
    }
    leg_ok: dict[str, int] = {leg: 0 for leg in _LEGS}
    for r in rows:
        if r.get("event") != "day_end":
            continue
        for s in (r.get("stages") or []):
            if not isinstance(s, dict):
                continue
            try:
                ok_n = int(s.get("ok") or 0)
            except (TypeError, ValueError):
                ok_n = 0
            if ok_n <= 0:
                continue
            name = str(s.get("stage") or "")
            for leg, names in _LEGS.items():
                if name in names:
                    leg_ok[leg] += ok_n
    for leg in _LEGS:
        if leg_ok[leg] == 0:
            infos.append(
                f"三腿覆盖：{leg} 全程 0 步成功"
                f"（种子/钱不足时合法，但目标 P3 ⑥ 要求这一腿有真机证据）"
            )

    # 留痕完整性（task-56）：账本声称的 `llm_trace` 必须真的落在盘上，且行数与引用数一一对应。
    # 只记 info：留痕是**复盘材料**，缺了不影响当天是否达标，但 run6 复盘必须有它。
    decision_traces = [r for r in decisions if str(r.get("llm_trace") or "")]
    llm_traced = len(decision_traces)
    traced_paths: dict[str, int] = {}
    for r in decision_traces:
        p = str(r.get("llm_trace"))
        traced_paths[p] = traced_paths.get(p, 0) + 1
    for p, claimed in sorted(traced_paths.items()):
        if not os.path.exists(p):
            infos.append(f"留痕缺失：账本引用了 {p}，但文件不存在（{claimed} 条决策没有可复盘的原文）")
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                lines = sum(1 for line in fh if line.strip())
        except OSError as exc:  # pragma: no cover - 只有权限/占用这类环境问题
            infos.append(f"留痕读不出：{p}（{exc}）")
            continue
        if lines != claimed:
            infos.append(
                f"留痕行数与引用数不符：{p} 实际 {lines} 行、账本引用 {claimed} 条"
                f"（多/少都说明留痕与决策不是一一对应）"
            )

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
        "decisions_llm_used": llm_used,
        "decisions_llm_fallback": llm_fallback,
        "leg_ok": leg_ok,
        "finish": {k: v for k, v in (finish or {}).items() if k != "_lineno"},
        "problems": problems,
        "history_problems": history_problems,
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
    print(f"decision {summary['decisions']} 条（LLM 调用 {summary['decisions_llm']} 条 / "
          f"其中模型产出 {summary.get('decisions_llm_used', summary['decisions_llm'])} 条）")
    if summary["finish"]:
        print(f"finish: {summary['finish']}")
    print(f"尾部连续 VERIFIED 天数 {summary['verified_streak_tail']} / 要求 {summary['target_days']}")
    if summary.get("infos"):
        print("")
        print("信息（不影响结论）：")
        for i in summary["infos"]:
            print(f"  - {i}")
    if summary.get("history_problems"):
        print("")
        print(f"历史问题（达标窗口**之外**的日子，不影响结论，共 {len(summary['history_problems'])} 条）：")
        for p in summary["history_problems"]:
            print(f"  - {p}")
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
