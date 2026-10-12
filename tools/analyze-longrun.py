#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""长跑账本行为分析器（task-25）。

读 `brain/agentfarm/longrun.py` 写的 JSONL 账本（每行一个事件），自动产出：
  1. 该做没做（cancel 后再没做过 / 没目标却还有待办 / day_end.checks 为 false）
  2. 白做（阶段 ok>0 但后置条件未成立；同格反复白试；失败却自称 VERIFIED 的"洗白"）
  3. 无效挥动（stages[].failed 按 action 分组 + blocked 记账的格与理由）
  4. 睡觉时机（睡前体力/时刻/还有活；sleep 失败与 intent_vetoed）
外加：每天一行摘要、3-8 条带证据行的改进建议、"本账本无法判定"清单。

只读、纯标准库。退出码：0 = 成功产出报告（**不表示"跑得好"**）；2 = 账本不可读/没有可解析事件。

用法：
  python tools\\analyze-longrun.py                      # 默认取 logs\\longrun-*.jsonl 里 mtime 最新
  python tools\\analyze-longrun.py --journal logs\\longrun-3day-llm-run2.jsonl
  python tools\\analyze-longrun.py --days 3 --top 10 --json
  python tools\\analyze-longrun.py --stamina-full 270 --sleep-pct 0.6
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 阶段 → farmwork 层的动作（用于"无效挥动"按 action 归组）
STAGE_ACTION = {
    "clear_area": "clear",
    "till_area": "till",
    "plant_area": "sow",
    "water_area": "water",
    "harvest": "harvest",
    "refill": "refill",
    "recover_stamina": "recover_stamina",
}
ACTION_TOOL_HINT = {
    "clear": "weed→hoe / twig→axe / stone→pickaxe / grass→scythe（镰刀是 MeleeWeapon，入口见 docs\\_analyze-longrun-run1.md 三层根因）",
    "till": "hoe（失败先看寻路/落点，再看等级与格子）",
    "sow": "seeds（先看背包种子与 plantable）",
    "water": "watering_can（先看 waterLeft）",
    "harvest": "手（interact）",
}
CHECK_MEANING = {
    "slept_by_us": "不是由我们成功睡觉结束的这天",
    "no_hard_failures": "这一天存在硬失败",
    "crops_watered": "收工时仍有作物没浇水",
    "day_justified": "收工理由不在允许集（night/stamina/no_work/no_plot）",
}
# 账本里"应该有、但没有就只能写无法判定"的字段/事件
FIELD_PROBES = [
    ("day_end.final_water", "final_water", "收工时的浇水状态（task-19/22 计划新增）"),
    ("day_end.stages[].proven_inert", "proven_inert", "逐格'动了没用'的精确计数"),
    ("event:env_fail", "env_fail", "环境级失败（task-15 计划新增）"),
    ("event:inconclusive_fail", "inconclusive_fail", "无法定论的失败（task-15 计划新增）"),
    ("event:stage_exhausted", "stage_exhausted", "阶段级'没有目标'的显式记录"),
    ("event:stage_no_target", "stage_no_target", "阶段级'没有目标'的旧记录"),
    ("event:plot_exhausted", "plot_exhausted", "片区级'没有目标'的换片记录"),
    ("event:idle", "idle", "无意图空转轮次"),
]
OUTCOME_RE = re.compile(
    r"目标\s*(\d+)\s*步：做成\s*(\d+)、跳过\s*(\d+)、失败\s*(\d+)"
)
LEFTOVER_RE = re.compile(r"还剩\s*(\d+)\s*格")
STOPPED_RE = re.compile(r"提前停：([^；;]+)")

EVENT_BUCKETS = {
    "outcome": "outcomes",
    "blocked": "blocked",
    "sleep": "sleeps",
    "review": "reviews",
    "intent_vetoed": "vetoeds",
    "intent_verdict": "verdicts",
    "decision": "decisions",
    "policy": "policies",
    "plot": "plots",
    "refill": "refills",
    "stage_no_target": "no_targets",
    "stage_exhausted": "exhausted",
    "plot_exhausted": "plot_exhausted",
    "idle": "idles",
    "no_intents": "no_intents",
    "env_fail": "env_fails",
    "inconclusive_fail": "inconclusive",
}


# ---------------------------------------------------------------- 基础工具
def as_list(value):
    return value if isinstance(value, list) else []


def as_dict(value):
    return value if isinstance(value, dict) else {}


def as_int(value, default=0):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def as_num(value, default=0.0):
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def finding(line, event, summary, hint="", subject=""):
    return {
        "line": line,
        "event": event,
        "subject": subject or event,
        "summary": summary,
        "hint": hint,
    }


def day_label(ev):
    if not isinstance(ev, dict):
        return "?"
    text = ev.get("day_text")
    if text:
        return str(text)
    day = ev.get("day")
    if isinstance(day, list) and day:
        return "/".join(str(x) for x in day)
    return "?"


def find_default_journal():
    pattern = os.path.join(ROOT, "logs", "longrun-*.jsonl")
    cands = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    if not cands:
        return None
    return max(cands, key=lambda p: os.path.getmtime(p))


def load_journal(path):
    """返回 (rows, bad_lines)；rows = [(lineno, event_dict)]。"""
    rows = []
    bad = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except Exception as exc:  # 坏行不致命，只在报告里列出
                bad.append((lineno, f"{type(exc).__name__}: {exc}"))
                continue
            if not isinstance(ev, dict):
                bad.append((lineno, f"不是对象：{type(ev).__name__}"))
                continue
            ev.setdefault("event", "<missing:event>")
            rows.append((lineno, ev))
    return rows, bad


# ---------------------------------------------------------------- 会话切分
def new_bucket():
    bucket = {"start_line": None, "start": None, "events": [], "day_ends": []}
    for key in EVENT_BUCKETS.values():
        bucket[key] = []
    return bucket


def build_sessions(rows):
    """按 day_start 切天（run2 一天可能有两个 day_start/day_end，例如睡觉失败后再睡）。"""
    sessions = []
    prelude = new_bucket()
    cur = None
    for lineno, ev in rows:
        name = ev.get("event")
        if name == "day_start":
            cur = new_bucket()
            cur["start_line"] = lineno
            cur["start"] = ev
            cur["events"].append((lineno, ev))
            sessions.append(cur)
            continue
        sink = cur if cur is not None else prelude
        sink["events"].append((lineno, ev))
        if name == "day_end":
            sink["day_ends"].append((lineno, ev))
        key = EVENT_BUCKETS.get(name)
        if key:
            sink[key].append((lineno, ev))
    return sessions, prelude


# ---------------------------------------------------------------- 四类判定
def cat_missed(sessions, top):
    out = []
    for sess in sessions:
        # 1a: intent_verdict=cancel，且该任务当天再没做成过
        for lineno, ev in sess["verdicts"]:
            for verdict in as_list(ev.get("verdicts")):
                if verdict.get("verdict") != "cancel":
                    continue
                task = verdict.get("task") or "?"
                later = [
                    (ln, o)
                    for ln, o in sess["outcomes"]
                    if ln > lineno and o.get("kind") == task
                ]
                if later:
                    note = f"；当天后来又跑过 {task}（L{later[0][0]}）"
                else:
                    end_line = sess["day_ends"][-1][0] if sess["day_ends"] else None
                    note = f"；当天再没做过（直到 L{end_line}）" if end_line else "；当天再没做过（这天没有 day_end）"
                out.append(
                    finding(
                        lineno,
                        "intent_verdict",
                        f"cancel：{task} @ zone={ev.get('zone')} —— {verdict.get('reason')}{note}",
                        hint="cancel 的依据是'看得见却没有一格可动目标'；若该任务其实有事可做，"
                             "问题在 _verify_intents 的观测范围（OBSERVE_REACH）或目标口径",
                        subject=f"missed:cancel:{task}",
                    )
                )
        # 1b: 阶段没目标 / 换片，且收工时还有待办
        for key, hint in (
            ("no_targets", "该阶段当天没有目标；若收工时该阶段仍有待办，就是'该做没做'"),
            ("exhausted", "阶段被记为'没有目标'"),
            ("plot_exhausted", "片区没目标 ⇒ 换片地；注意这可能掩盖'其实还有活'"),
        ):
            for lineno, ev in sess[key]:
                leftover = ev.get("leftover", ev.get("recovered"))
                out.append(
                    finding(
                        lineno,
                        ev.get("event"),
                        f"{ev.get('event')}：stage={ev.get('stage') or '-'} zone={ev.get('zone')} "
                        f"leftover/recovered={leftover} note={str(ev.get('note') or '')[:60]}",
                        hint=hint,
                        subject=f"missed:{ev.get('event')}",
                    )
                )
        end = sess["day_ends"][-1][1] if sess["day_ends"] else None
        end_line = sess["day_ends"][-1][0] if sess["day_ends"] else None
        oks = {}
        for _, ev in sess["outcomes"]:
            if ev.get("postcondition_met"):
                oks[ev.get("kind")] = oks.get(ev.get("kind"), 0) + 1
        final = as_dict(end.get("final")) if end else {}
        if final:
            unwatered = as_int(final.get("unwatered_crops"))
            if unwatered > 0 and not oks.get("water_area"):
                out.append(
                    finding(
                        end_line, "day_end",
                        f"收工时还有 {unwatered} 格作物没浇水（final.unwatered_crops={unwatered}），"
                        f"而当天 water_area 一次都没成立",
                        hint="先看 waterLeft / 水井路径 / water_area 的目标口径；这是最直接的作物损失",
                        subject="missed:unwatered",
                    )
                )
            seeds = as_list(final.get("seeds"))
            if seeds and as_int(final.get("tillable")) > 0 and not oks.get("plant_area"):
                out.append(
                    finding(
                        end_line, "day_end",
                        f"收工时背包仍有 {len(seeds)} 种种子、还有 {as_int(final.get('tillable'))} 格可锄，"
                        f"而当天 plant_area 一次都没成立",
                        hint="钱少买不起种子时不是问题；否则看 plantable 口径与种子选择",
                        subject="missed:seeds",
                    )
                )
            if as_int(final.get("ripe")) > 0 and not oks.get("harvest"):
                out.append(
                    finding(
                        end_line, "day_end",
                        f"收工时还有 {as_int(final.get('ripe'))} 格成熟作物没收（final.ripe>0），当天没有 harvest 记录",
                        hint="WIDE_TASKS 里的 harvest 是否被 plot 口径挡住",
                        subject="missed:harvest",
                    )
                )
        # 1c: checks 为 false
        for lineno, ev in sess["day_ends"]:
            for name, value in as_dict(ev.get("checks")).items():
                if value is False:
                    out.append(
                        finding(
                            lineno, "day_end",
                            f"checks.{name}=false —— {CHECK_MEANING.get(name, '未定义的检查项')}"
                            f"（ok/skipped/failed = {ev.get('ok_steps')}/{ev.get('skipped_steps')}/{ev.get('failed_steps')}，"
                            f"ended_by={ev.get('ended_by')}）",
                            hint="这一项 false 就等于整天不 VERIFIED；要看清是哪一步先崩的",
                            subject=f"missed:check:{name}",
                        )
                    )
    return out[:top] if top else out


def pair_stages_outcomes(stages, outcomes):
    """day_end.stages 与 day_end.outcomes 一一对应；对不上就按 kind 顺序配对。"""
    if len(stages) == len(outcomes):
        return list(zip(stages, outcomes))
    queues = {}
    for oc in outcomes:
        queues.setdefault(oc.get("kind"), []).append(oc)
    pairs = []
    for st in stages:
        queue = queues.get(st.get("stage")) or []
        pairs.append((st, queue.pop(0) if queue else None))
    return pairs


def stage_failed_from_reason(reason):
    match = OUTCOME_RE.search(str(reason or ""))
    if not match:
        return None
    return {
        "targets": int(match.group(1)),
        "ok": int(match.group(2)),
        "skipped": int(match.group(3)),
        "failed": int(match.group(4)),
        "leftover": (int(LEFTOVER_RE.search(reason).group(1)) if LEFTOVER_RE.search(reason) else 0),
        "met": "后置条件成立" in str(reason),
        "stopped": (STOPPED_RE.search(reason).group(1) if STOPPED_RE.search(reason) else ""),
    }


def cat_wasted(sessions, top):
    out = []
    for sess in sessions:
        for lineno, ev in sess["day_ends"]:
            stages = as_list(ev.get("stages"))
            outcomes = as_list(ev.get("outcomes"))
            if not stages and outcomes:
                # 旧账本/day_end 没写 stages 时退回 reason 文本
                stages = []
                for oc in outcomes:
                    parsed = stage_failed_from_reason(oc.get("reason")) or {}
                    stages.append(
                        {
                            "stage": oc.get("kind"),
                            "tiles": parsed.get("targets", 0),
                            "ok": parsed.get("ok", 0),
                            "skipped": parsed.get("skipped", 0),
                            "failed": parsed.get("failed", 0),
                            "stopped": parsed.get("stopped", ""),
                            "leftover": parsed.get("leftover", 0),
                            "_from_reason": True,
                        }
                    )
            for st, oc in pair_stages_outcomes(stages, outcomes):
                ok = as_int(st.get("ok"))
                failed = as_int(st.get("failed"))
                leftover = as_int(st.get("leftover"))
                met = None if oc is None else bool(oc.get("postcondition_met"))
                stage_name = st.get("stage") or (oc or {}).get("kind") or "?"
                if ok > 0 and (leftover > 0 or met is False):
                    out.append(
                        finding(
                            lineno, "day_end",
                            f"白做：{stage_name} 做成 {ok} 步，但后置条件未成立"
                            f"（targets={st.get('tiles')} leftover={leftover} stopped={st.get('stopped') or '-'}）",
                            hint="做成与'问题解决'不是一回事：完成的目标没能清掉全部待办（口径/目标池问题）",
                            subject=f"wasted:leftover:{stage_name}",
                        )
                    )
                if failed > 0 and met is True:
                    out.append(
                        finding(
                            lineno, "day_end",
                            f"被洗白：{stage_name} 有 {failed} 格失败，却记为 VERIFIED "
                            f"（做成 {ok}/{st.get('tiles')}）",
                            hint="blocked 封格把失败从 leftover 里排除了 ⇒ met=True ⇒ VERIFIED；"
                                 "修 _mark_blocked/_leftover/验收（task-9）",
                            subject=f"wasted:whitewash:{stage_name}",
                        )
                    )
        counts = {}
        for lineno, ev in sess["blocked"]:
            tile = tuple(as_list(ev.get("tile")))
            key = (tile, ev.get("action"))
            counts.setdefault(key, []).append(lineno)
        for (tile, action), lns in counts.items():
            if len(lns) > 1:
                out.append(
                    finding(
                        lns[-1], "blocked",
                        f"同格反复白试：{list(tile)} action={action} ×{len(lns)} 次（行 {lns}）",
                        hint="MAX_TILE_ATTEMPTS / blocked 记账没有真正阻止重复尝试",
                        subject="wasted:repeat_tile",
                    )
                )
    return out[:top] if top else out


def cat_ineffective(sessions, top):
    out = []
    per_action = {}
    grass_tiles = set()
    grass_lines = []
    inert_total = 0
    for sess in sessions:
        for lineno, ev in sess["day_ends"]:
            for st in as_list(ev.get("stages")):
                failed = as_int(st.get("failed"))
                if failed <= 0:
                    continue
                action = STAGE_ACTION.get(st.get("stage"), st.get("stage"))
                rec = per_action.setdefault(action, {"failed": 0, "lines": [], "blocked": [], "reasons": {}})
                rec["failed"] += failed
                rec["lines"].append(lineno)
            for st in as_list(ev.get("stages")):
                inert_total += as_int(st.get("proven_inert"))
        for lineno, ev in sess["blocked"]:
            action = ev.get("action") or "?"
            reason = str(ev.get("reason") or "")
            rec = per_action.setdefault(action, {"failed": 0, "lines": [], "blocked": [], "reasons": {}})
            rec["blocked"].append(lineno)
            rec["reasons"][reason] = rec["reasons"].get(reason, 0) + 1
            tile = tuple(as_list(ev.get("tile")))
            if "grass" in reason:
                if tile:
                    grass_tiles.add(tile)
                grass_lines.append(lineno)
    for action in sorted(per_action):
        rec = per_action[action]
        lines = sorted(set(rec["lines"] + rec["blocked"]))
        top_reasons = sorted(rec["reasons"].items(), key=lambda kv: -kv[1])[:3]
        reason_text = "；".join(f"{r}×{n}" for r, n in top_reasons) or "-"
        out.append(
            finding(
                lines[0] if lines else None, "stage/blocked",
                f"无效挥动 {action}：stages[].failed 合计 {rec['failed']} 格，"
                f"blocked 记账 {len(rec['blocked'])} 次，理由：{reason_text}",
                hint=ACTION_TOOL_HINT.get(action, "看该动作的工具/等级/寻路"),
                subject=f"ineffective:{action}",
            )
        )
    if grass_tiles:
        out.append(
            finding(
                grass_lines[0] if grass_lines else None, "blocked",
                f"草格（grass）无效挥动：{len(grass_tiles)} 格被记 blocked "
                f"（行 {sorted(set(grass_lines))}），其中 0 格成功",
                hint="grass 需要 scythe，而 MeleeWeapon 在 Game1.pressUseToolButton 里要求真实输入边沿 ⇒ "
                     "程序化挥动恒为空挥（IL 定案见 docs\\_analyze-longrun-run1.md / _il-sell 系列）",
                subject="ineffective:grass",
            )
        )
    if inert_total:
        out.append(
            finding(None, "day_end", f"proven_inert 合计 {inert_total} 次（'动了没用'）",
                    hint="这些格当天的动作没有改变世界状态", subject="ineffective:proven_inert")
        )
    return out[:top] if top else out


def cat_sleep(sessions, top, stamina_full, sleep_pct):
    out = []
    for sess in sessions:
        if not sess["day_ends"]:
            continue
        for lineno, ev in sess["day_ends"]:
            ended_by = str(ev.get("ended_by") or "")
            if ended_by not in ("sleep", "sleep_failed"):
                continue
            end_line = lineno
            last_sleep = sess["sleeps"][-1][1] if sess["sleeps"] else {}
            sleep_line = sess["sleeps"][-1][0] if sess["sleeps"] else end_line
            before = as_dict(last_sleep.get("before"))
            final = as_dict(ev.get("final"))
            stamina = as_num(before.get("stamina", final.get("stamina")), -1.0)
            tod = as_int(before.get("timeOfDay", final.get("timeOfDay")), -1)
            if stamina >= 0 and stamina_full > 0:
                pct = stamina / stamina_full
                if pct > sleep_pct:
                    out.append(
                        finding(
                            sleep_line, "sleep",
                            f"睡前体力仍有 {stamina:.0f}/{stamina_full:.0f}（{pct * 100:.0f}%，"
                            f"阈值 {sleep_pct * 100:.0f}%）就去睡了",
                            hint="sleep_guard 的 stamina 阈值（默认 min_stamina=12）太低或收工条件太早",
                            subject="sleep:stamina",
                        )
                    )
            if 0 <= tod < 2200:
                out.append(
                    finding(
                        sleep_line, "sleep",
                        f"睡前 timeOfDay={tod} < 2200，天还早",
                        hint="sleep_at 默认 2200；若提前收工要给出理由（no_work/no_plot/stamina）",
                        subject="sleep:early",
                    )
                )
            work_reasons = []
            if sess["reviews"]:
                work_reasons = as_list(sess["reviews"][-1][1].get("work_reasons"))
            if work_reasons:
                out.append(
                    finding(
                        sess["reviews"][-1][0], "review",
                        f"睡前最后一次 review 仍说还有活：{work_reasons}",
                        hint="守卫说还有活却去睡 ⇒ sleep_guard/收工判据自相矛盾",
                        subject="sleep:work_reasons",
                    )
                )
            if ended_by == "sleep_failed":
                code = last_sleep.get("code") or "?"
                out.append(
                    finding(
                        sleep_line, "sleep",
                        f"睡觉请求失败（code={code}，reason={last_sleep.get('reason')}）⇒ 这天没有跨日",
                        hint="先修跨日路径（task-6/task-8），否则后续所有天的账本都不可比",
                        subject="sleep:failed",
                    )
                )
        vetoed = sess["vetoeds"]
        if vetoed and sess["day_ends"]:
            out.append(
                finding(
                    vetoed[0][0], "intent_vetoed",
                    f"intent_vetoed ×{len(vetoed)}："
                    + "；".join(f"{ev.get('task')}（{str(ev.get('reason'))[:40]}）" for _, ev in vetoed),
                    hint="政策否决了 LLM 的意图（例如 recover_stamina），说明政策与 LLM 判断不一致",
                    subject="sleep:vetoed",
                )
            )
    return out[:top] if top else out


# ---------------------------------------------------------------- 建议 / 无法判定
def build_advice(report, top=8):
    advice = []
    events = report["events"]
    sessions = report["_sessions"]
    # 1) 睡觉失败
    sleep_failed = [f for f in report["categories"]["sleep"] if f["subject"] == "sleep:failed"]
    if sleep_failed:
        advice.append({
            "text": "睡觉请求整段失败：先修跨日路径，否则「每天」的账本都不可比（本轮 run2 一整天的活白干）",
            "lines": [f["line"] for f in sleep_failed],
        })
    # 2) 草格无效挥动
    grass = [f for f in report["categories"]["ineffective"] if f["subject"] == "ineffective:grass"]
    if grass:
        advice.append({
            "text": "grass 格 0 成功、非 grass 全成功：修镰刀入口（Mod 真挥）或把 grass 从 ACTIONABLE_KINDS 摘掉并显式记为'今天不做'",
            "lines": [grass[0]["line"]],
        })
    # 3) 被洗白
    white = [f for f in report["categories"]["wasted"] if f["subject"].startswith("wasted:whitewash")]
    if white:
        advice.append({
            "text": f"验收被'封格'洗白 ×{len(white)}：blocked 的格必须仍算 leftover（或单独记 inconclusive_fail），否则任务级 VERIFIED 不可信",
            "lines": [f["line"] for f in white],
        })
    # 4) 白做（有做成但没解决）
    leftover = [f for f in report["categories"]["wasted"] if f["subject"].startswith("wasted:leftover")]
    if leftover:
        advice.append({
            "text": f"有阶段'做成若干步但后置条件未成立' ×{len(leftover)}：目标池口径要收紧（一遍只做能做完的，或把 leftover 当失败）",
            "lines": [f["line"] for f in leftover],
        })
    # 5) till 不可达
    till = [f for f in report["categories"]["ineffective"] if f["subject"] == "ineffective:till"]
    if till:
        advice.append({
            "text": "till 失败里有'四邻都站不过去'：寻路/落点选得不对（stand_next_to 全失败），先补可站格再谈等级",
            "lines": [till[0]["line"]],
        })
    # 6) cancel
    cancels = [f for f in report["categories"]["missed"] if f["subject"].startswith("missed:cancel")]
    if cancels:
        advice.append({
            "text": f"cancel 判定砍掉了 {len(cancels)} 个任务：确认'看不见 ⇒ cancel'是否把可做的事砍了（先走过去再判）",
            "lines": [f["line"] for f in cancels],
        })
    # 7) LLM fallback
    fallback = []
    for sess in sessions:
        for lineno, ev in sess["decisions"]:
            if ev.get("fallback") or str(ev.get("source") or "").endswith("fallback"):
                fallback.append(lineno)
    if fallback:
        advice.append({
            "text": f"LLM 回答被 max_tokens 截断 / 走了确定性兜底 ×{len(fallback)}：调大 max_tokens 或缩短观察文本",
            "lines": fallback,
        })
    # 8) 观测截断
    truncated = []
    for sess in sessions:
        for lineno, ev in sess["plots"]:
            if "截断" in str(ev.get("note") or ""):
                truncated.append(lineno)
        for lineno, ev in sess["day_ends"]:
            for plot in as_list(ev.get("plots")):
                if "截断" in str(as_dict(plot).get("note") or ""):
                    truncated.append(lineno)
    if truncated:
        advice.append({
            "text": f"观测被 400 格上限截断 ×{len(set(truncated))}：田区统计与锚点打分建立在残缺 tiles[] 上，分区观测或提高上限",
            "lines": sorted(set(truncated))[:top],
        })
    # 9) 硬失败
    hard = [f for f in report["categories"]["missed"] if f["subject"] == "missed:check:no_hard_failures"]
    if hard:
        advice.append({
            "text": "存在'有硬失败'的一天：先按上面'无效挥动/白做'逐条修，再看 failed_steps 是否归零",
            "lines": [f["line"] for f in hard],
        })
    if not advice and report["days"]:
        advice.append({"text": "四类判定都没抓到硬问题：本账本这天基本干净（仍然建议人工抽查观测口径）", "lines": []})
    return advice[:top]


def build_undecidable(rows, sessions, prelude, report):
    out = []
    names = set(ev.get("event") for _, ev in rows)
    blob = "\n".join(json.dumps(ev, ensure_ascii=False) for _, ev in rows)
    for label, probe, meaning in FIELD_PROBES:
        if probe.startswith("event:"):
            absent = probe.split(":", 1)[1] not in names
        elif probe == "final_water":
            absent = "\"final_water\"" not in blob
        else:
            absent = probe not in blob
        if absent:
            out.append(f"本账本没有 {label}：无法判定 {meaning}")
    day_ends = [lineno for lineno, ev in rows if ev.get("event") == "day_end"]
    if not day_ends:
        out.append("整个账本没有任何 day_end：日级验收（checks/verified/final）、收工理由、睡觉时机都无法判定"
                   "（账本可能是被外部终止的，例如 run1 停在最后一条 decision 之后）")
    if not any(ev.get("event") == "finish" for _, ev in rows):
        out.append("没有 finish：无法判定这次长跑是否正常收尾（是否为崩溃/被 kill）")
    if not any(ev.get("event") == "day_start" for _, ev in rows):
        out.append("没有 day_start：无法按时段切天，只能按平面事件统计")
    out.append("账本只有 step 级计数、没有逐格 before/after 的 kind 差分：'无效挥动'只能由 blocked 记账文本 + "
               "stages[].failed 推断，不能证明每格确实没变（真正差分要另跑 tiles[] 对比）")
    out.append("账本没有睡觉前的 isInBed / 当前模态状态：无法区分'没上床'与'桥超时'（task-6 只能用 SMAPI 日志旁证）")
    out.append("账本没有每步耗时：无法判定时间预算（t 只给出事件时刻）")
    if any(ev.get("event") == "plot" and "截断" in str(ev.get("note") or "") for _, ev in rows):
        out.append("plot 事件自称观测被 400 格上限截断：田区统计/锚点打分基于残缺 tiles[]，"
                   "所以'可锄 N / 待清理 M'只能当参考")
    return out


# ---------------------------------------------------------------- 报告渲染
def build_report(rows, path, args, bad_lines):
    sessions, prelude = build_sessions(rows)
    events = {}
    for _, ev in rows:
        name = ev.get("event")
        events[name] = events.get(name, 0) + 1
    days = []
    verified_days = 0
    failed_steps_total = 0
    ok_steps_total = 0
    skipped_steps_total = 0
    for sess in sessions:
        start = as_dict(sess["start"])
        end = as_dict(sess["day_ends"][-1][1]) if sess["day_ends"] else {}
        if end.get("verified"):
            verified_days += 1
        if end:
            failed_steps_total += as_int(end.get("failed_steps"))
            ok_steps_total += as_int(end.get("ok_steps"))
            skipped_steps_total += as_int(end.get("skipped_steps"))
        days.append({
            "label": day_label(end) if end else day_label(start),
            "start_line": sess["start_line"],
            "day_end_lines": [ln for ln, _ in sess["day_ends"]],
            "ended_by": end.get("ended_by"),
            "ended_reason": end.get("ended_reason"),
            "verified": end.get("verified"),
            "ok_steps": end.get("ok_steps"),
            "skipped_steps": end.get("skipped_steps"),
            "failed_steps": end.get("failed_steps"),
            "checks": as_dict(end.get("checks")),
            "final": as_dict(end.get("final")),
            "outcomes": len(sess["outcomes"]),
            "blocked": len(sess["blocked"]),
        })
    finish = None
    for lineno, ev in rows:
        if ev.get("event") == "finish":
            finish = dict(ev)
            finish["line"] = lineno
    sleep_ok = sum(1 for _, ev in rows if ev.get("event") == "sleep" and ev.get("ok"))
    sleep_failed = sum(1 for _, ev in rows if ev.get("event") == "sleep" and not ev.get("ok"))
    blocked_by_action = {}
    blocked_grass = 0
    for _, ev in rows:
        if ev.get("event") != "blocked":
            continue
        action = ev.get("action") or "?"
        blocked_by_action[action] = blocked_by_action.get(action, 0) + 1
        if "grass" in str(ev.get("reason") or ""):
            blocked_grass += 1
    report = {
        "journal": path,
        "lines": max((ln for ln, _ in rows), default=0),
        "parsed_events": len(rows),
        "bad_lines": bad_lines,
        "days_requested": args.days,
        "events": events,
        "verified_days": verified_days,
        "day_start_count": events.get("day_start", 0),
        "day_end_count": events.get("day_end", 0),
        "ok_steps_total": ok_steps_total,
        "skipped_steps_total": skipped_steps_total,
        "failed_steps_total": failed_steps_total,
        "no_day_progress": [
            {"line": ln, "reason": ev.get("reason"), "ended_by": ev.get("ended_by")}
            for ln, ev in rows if ev.get("event") == "no_day_progress"
        ],
        "sessions": [
            {
                "start_line": s["start_line"],
                "day_end_lines": [ln for ln, _ in s["day_ends"]],
                "outcomes": [{"line": ln, "kind": ev.get("kind"), "terminal": ev.get("terminal"),
                              "postcondition_met": ev.get("postcondition_met")} for ln, ev in s["outcomes"]],
            }
            for s in sessions
        ],
        "prelude_lines": [ln for ln, _ in prelude["events"]],
        "finish": finish,
        "sleep_ok": sleep_ok,
        "sleep_failed": sleep_failed,
        "blocked_by_action": blocked_by_action,
        "blocked_grass": blocked_grass,
        "days": days,
        "_sessions": sessions,
    }
    report["categories"] = {
        "missed": cat_missed(sessions, args.top),
        "wasted": cat_wasted(sessions, args.top),
        "ineffective": cat_ineffective(sessions, args.top),
        "sleep": cat_sleep(sessions, args.top, args.stamina_full, args.sleep_pct),
    }
    report["categories_total"] = {
        "missed": len(cat_missed(sessions, 0)),
        "wasted": len(cat_wasted(sessions, 0)),
        "ineffective": len(cat_ineffective(sessions, 0)),
        "sleep": len(cat_sleep(sessions, 0, args.stamina_full, args.sleep_pct)),
    }
    report["advice"] = build_advice(report)
    report["undecidable"] = build_undecidable(rows, sessions, prelude, report)
    return report


MAPPING_TEXT = [
    ("day_start", "会话/天边界（每天一行摘要）"),
    ("decision", "意图来源（llm/deterministic/…_fallback）→ 建议：fallback 计数"),
    ("intent_verdict", "1 该做没做（verdict=cancel 且当天再没做过）；unknown 是'看不见先走过去'"),
    ("policy", "1 该做没做（'今天不再要 XX'把任务整类砍掉）"),
    ("plot_exhausted / stage_no_target / stage_exhausted", "1 该做没做（阶段/片区没目标）；也可能掩盖'其实还有活'"),
    ("blocked", "2 白做（同格反复）+ 3 无效挥动（action 分组、草格理由）"),
    ("outcome", "2 白做（postcondition_met=false）+ 洗白（failed>0 但 terminal=VERIFIED）"),
    ("day_end.stages[]", "3 无效挥动（failed 按 stage→action 归组）"),
    ("day_end.checks{}", "1 该做没做（为 false 的项）"),
    ("day_end.final{}", "1 该做没做（unwatered_crops/ripe/seeds 还有待办却没对应阶段成功）"),
    ("sleep", "4 睡觉时机（睡前体力/时刻）+ sleep_failed"),
    ("review.work_reasons", "4 睡觉时机（还有活却去睡）"),
    ("intent_vetoed", "4 睡觉时机（政策否决 LLM 意图）"),
    ("no_day_progress", "日级：这天没有任何进度（睡觉失败/空转）"),
    ("refill / goto_farm / plot", "辅助：补水、回农场、观测（截断警告）"),
    ("finish", "长跑收尾（code/verified_streak/actions/minutes）"),
]


def render_text(report, top):
    out = []
    add = out.append
    add("=" * 78)
    add("长跑行为分析（tools\\analyze-longrun.py）")
    add("=" * 78)
    add(f"账本: {report['journal']}")
    add(f"行数: {report['lines']}（可解析事件 {report['parsed_events']}）"
        + (f"，坏行 {len(report['bad_lines'])}: {report['bad_lines'][:3]}" if report["bad_lines"] else ""))
    add(f"天: --days {report['days_requested']}；day_start {report['day_start_count']} 次、day_end {report['day_end_count']} 次")
    add(f"VERIFIED: {report['verified_days']}/{report['days_requested']} 天"
        f"（day_end 中 verified=true {report['verified_days']} 次）")
    add(f"步数合计: ok {report['ok_steps_total']} / skipped {report['skipped_steps_total']} "
        f"/ failed {report['failed_steps_total']}")
    nd = report["no_day_progress"]
    add(f"no_day_progress: {len(nd)} 次" + (f"（行 {[d['line'] for d in nd]}）" if nd else ""))
    blocked = report["events"].get("blocked", 0)
    blocked_detail = ",".join(f"{k} {v}" for k, v in sorted(report["blocked_by_action"].items())) or "-"
    add(f"blocked: {blocked} 条（{blocked_detail}）；其中理由含 grass 的 {report['blocked_grass']} 条"
        + ("（草格无效挥动）" if report["blocked_grass"] else ""))
    add(f"sleep: {report['events'].get('sleep', 0)} 次（ok {report['sleep_ok']} / failed {report['sleep_failed']}）")
    if report["finish"]:
        fin = report["finish"]
        add(f"finish: L{fin.get('line')} code={fin.get('code')} verified_streak={fin.get('verified_streak')} "
            f"actions={fin.get('actions')} minutes={fin.get('minutes')} stages_seen={fin.get('stages_seen')}")
    else:
        add("finish: <缺失>（账本没有正常收尾记录）")
    add("")
    add("每天一行：")
    for day in report["days"]:
        final = day["final"]
        final_text = ""
        if final:
            final_text = (f" | final {final.get('location')} t={final.get('timeOfDay')} "
                          f"体力={final.get('stamina')} 钱={final.get('money')} 作物={final.get('crops')} "
                          f"未浇={final.get('unwatered_crops')} 熟={final.get('ripe')} 可锄={final.get('tillable')} "
                          f"种子={len(as_list(final.get('seeds')))}")
        if day["ended_by"] is None:
            add(f"  - {day['label']}: <无 day_end>（从 L{day['start_line']} 起，"
                f"outcome {day['outcomes']} 次、blocked {day['blocked']} 次）⇒ 无法判定")
        else:
            checks = ",".join(f"{k}={v}" for k, v in day["checks"].items()) or "-"
            add(f"  - {day['label']}: ended_by={day['ended_by']} verified={day['verified']} "
                f"ok/skip/fail={day['ok_steps']}/{day['skipped_steps']}/{day['failed_steps']} "
                f"checks[{checks}] L{day['day_end_lines']}{final_text}")
    add("")
    sections = [
        ("1 该做没做", "missed", "该做没做"),
        ("2 白做", "wasted", "白做"),
        ("3 无效挥动", "ineffective", "无效挥动"),
        ("4 睡觉时机", "sleep", "睡觉时机"),
    ]
    for title, key, _ in sections:
        items = report["categories"][key]
        total = report["categories_total"][key]
        add("-" * 78)
        add(f"【{title}】{total} 条" + (f"（显示前 {len(items)} 条）" if total > len(items) else ""))
        if not items:
            add("  （本账本这一类没抓到问题）")
        for item in items:
            line = f"L{item['line']}" if item["line"] is not None else "L-"
            add(f"  [{line}] {item['summary']}")
            if item.get("hint"):
                add(f"        建议：{item['hint']}")
    add("-" * 78)
    add("【能给 Lead 直接用的改进建议】")
    for i, adv in enumerate(report["advice"], 1):
        lines = ",".join(f"L{x}" for x in adv["lines"]) if adv["lines"] else "-"
        add(f"  {i}. {adv['text']}  （证据：{lines}）")
    add("-" * 78)
    add("【本账本无法判定】")
    for item in report["undecidable"]:
        add(f"  - {item}")
    add("-" * 78)
    add("【事件 → 判定类别映射表】")
    for name, meaning in MAPPING_TEXT:
        add(f"  {name:52s} {meaning}")
    add("=" * 78)
    return "\n".join(out)


# ---------------------------------------------------------------- CLI
def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="长跑账本行为分析器：四类判定（该做没做/白做/无效挥动/睡觉时机）+ 证据行号 + 建议"
    )
    parser.add_argument("--journal", default=None,
                        help="账本路径（默认取 logs\\longrun-*.jsonl 里 mtime 最新）")
    parser.add_argument("--days", type=int, default=3, help="领跑天数（只用于 'X/N 天 VERIFIED' 的分母）")
    parser.add_argument("--top", type=int, default=10, help="每类明细最多显示条数（默认 10）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON（同结构）")
    parser.add_argument("--stamina-full", type=float, default=270.0, help="满体力（默认 270，用于睡觉时机判定）")
    parser.add_argument("--sleep-pct", type=float, default=0.60,
                        help="睡前体力比例超过它就判'体力还充裕就睡了'（默认 0.60）")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    path = args.journal or find_default_journal()
    if not path:
        print("找不到账本：logs\\longrun-*.jsonl 为空，且未给 --journal", file=sys.stderr)
        return 2
    if not os.path.isfile(path):
        print(f"账本不可读（不是文件）：{path}", file=sys.stderr)
        return 2
    try:
        rows, bad_lines = load_journal(path)
    except OSError as exc:
        print(f"账本不可读：{path}: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print(f"账本没有可解析事件：{path}", file=sys.stderr)
        return 2
    report = build_report(rows, path, args, bad_lines)
    if args.json:
        payload = {k: v for k, v in report.items() if not k.startswith("_")}
        payload["mapping"] = {name: meaning for name, meaning in MAPPING_TEXT}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(report, args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
