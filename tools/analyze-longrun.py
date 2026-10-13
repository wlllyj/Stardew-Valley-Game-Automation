#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""长跑账本行为分析器（task-25）。

读 `brain/agentfarm/longrun.py` 写的 JSONL 账本（每行一个事件），自动产出：
  0. 必须人工介入（红：模态挡住 / 不可逆职业选择 / 存档模态超时 ⇒ 当天一律不判通过）
  1. 该做没做（cancel 后再没做过 / 没目标却还有待办 / day_end.checks 为 false）
  2. 白做（阶段 ok>0 但后置条件未成立；同格反复白试；失败却自称 VERIFIED 的"洗白"）
  3. 无效挥动（stages[].failed 按 action 分组 + blocked 记账的格与理由）
  4. 睡觉时机（睡前体力/时刻/还有活；sleep 失败与 intent_vetoed）
  5. 环境挡路（env_fail，statuses=busy/渐黑/模态/没存档）、**自旋到上限**（env_spin_capped：
     同一格被挡住超过 MAX_ENV_ATTEMPTS=2 后改按"没结论"占配额）与没拿到结论（inconclusive_fail，
     占配额 ⇒ "配额被吃掉 N 格"）
外加：每天一行摘要、3-8 条带证据行的改进建议、"本账本无法判定"清单。

与 `tools\\verify-run3.py` 的关系：两者**独立读数、交叉核对**。本工具只做分析、不判验收；
但下列口径与它对齐（同一本账本给出相反结论 ⇒ 停下来人工对账，别单方面改口径）：
  * `blocked_modal` / `checks.no_blocking_modal=false` 一律**不判通过**（红）；
  * 0 个阶段却自称 VERIFIED 必须有"无活可做"的证据（`no_intents`/`plot_exhausted`/
    `policy_fallback` 事件，或 sleep/ended_reason 以 `no_work`/`night`/`stamina` 开头）；
  * `failed_steps` 与 `sum(stages[].failed)` 的差额必须被 `env_block(+count)` + `inconclusive(+count)`
    完全解释（否则"账目不可信"）；
  * 浇水证据（task-19/task-36，与 `tools\verify-run3.py` 四个闸门同向）：`checks.watered_outdoor`
    **缺失 = 红（缺失 ≠ 通过）**、`false` = 红、`true` + `final_water.scope=="window"` + `tiles==0` = 红
    （当天没有户外快照 ⇒ 这个 true 没有证据来源）、`true` + `final_water.dry>0` = 红（自相矛盾）；
    而 `true` 但整条没写 `final_water` 只在【无法判定】里点名（verify-run3.py 记信息项）。跨日必须恰好 +1 天；
  * `t` 回退只记信息项；环境挡路**不算硬失败**。

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
    # task-11：被"不敢关/不可逆"的模态挡住（职业选择、存档模态超时）⇒ 当天不算数，等人处理。
    "no_blocking_modal": "这一天被模态挡住并停下等人（职业选择/存档模态超时/连关不完）"
                         "—— 不是代码能自愈的那种，必须人工介入",
    "no_hard_failures": "这一天存在硬失败",
    "crops_watered": "收工时仍有作物没浇水",
    "day_justified": "收工理由不在允许集（night/stamina/no_work/no_plot）",
    # task-19/task-36：窗口口径在室内恒 0，不能当浇水证据 ⇒ 必须由 farm 级字段作证（缺失 ≠ 通过）
    "watered_outdoor": "缺 farm 级/户外浇水证据、或自述还有没浇的作物（缺失 ≠ 通过；"
                       "窗口 unwatered_crops 在室内恒 0，不作证据）",
    # task-15：阶段后置条件未成立的显式汇总（缺失时本工具按 day_end.stages 自算兜底）
    "no_unmet_stages": "有目标阶段留下了没做完的格子（leftover>0）",
}
# 账本里"应该有、但没有就只能写无法判定"的字段/事件
FIELD_PROBES = [
    ("day_end.final_water", "final_water", "收工时的浇水状态（task-19：dry 与 checks.watered_outdoor 互检）"),
    ("day_end.stages[].proven_inert", "proven_inert", "逐格'动了没用'的精确计数"),
    ("event:env_fail", "env_fail", "环境级失败（task-22：busy/渐黑/模态/没存档）"),
    ("event:inconclusive_fail", "inconclusive_fail", "无法定论的失败（task-22：超时/异常/stale）"),
    # task-28：同格被环境挡住累计超过 MAX_ENV_ATTEMPTS 的显式留痕（tile/streak/limit）
    ("event:env_spin_capped", "env_spin_capped", "同一格反复被环境挡住到上限的留痕（task-28）"),
    # task-22/28：stages[] 里的环境挡路/无结论**计数**（verify-run3 读 env_block_count 或 env_block）
    ("day_end.stages[].env_block", "env_block",
     "逐阶段'被环境挡住'的步数计数（task-22；与 failed_steps 差额同源）"),
    ("day_end.stages[].inconclusive", "inconclusive",
     "逐阶段'没拿到结论'的步数计数（task-22；占尝试配额）"),
    ("day_end.checks.watered_outdoor", "watered_outdoor",
     "户外浇水证据（task-19；缺失 ≠ 通过）"),
    ("day_end.checks.no_unmet_stages", "no_unmet_stages",
     "阶段后置条件是否全部成立（task-15；缺失时按 stages 自算）"),
    ("event:stage_exhausted", "stage_exhausted", "阶段级'没有目标'的显式记录"),
    ("event:stage_no_target", "stage_no_target", "阶段级'没有目标'的旧记录"),
    ("event:plot_exhausted", "plot_exhausted", "片区级'没有目标'的换片记录"),
    ("event:idle", "idle", "无意图空转轮次"),
    # task-11：缺失只能算"没记账"，绝不能当"没被模态挡过"（verify-run3.py 同口径）。
    ("day_end.checks.no_blocking_modal", "no_blocking_modal",
     "当天是否被'不敢关/不可逆'的模态挡住（task-11 新增）"),
]
OUTCOME_RE = re.compile(
    r"目标\s*(\d+)\s*步：做成\s*(\d+)、跳过\s*(\d+)、失败\s*(\d+)"
)
LEFTOVER_RE = re.compile(r"还剩\s*(\d+)\s*格")
STOPPED_RE = re.compile(r"提前停：([^；;]+)")

# ---------------------------------------------------------------- task-11 模态记账
#: 红（必须人工介入）：这些事件的唯一产生路径是 longrun 的 `_modal_blocked`（不可逆职业选择 /
#: 存档模态超时 / 连关不完）或"只记录、停下等人"。它们**不是**能自愈的情况。
MODAL_RED_EVENTS = (
    "modal_blocked",
    "modal_timeout",
    "modal_loop_capped",
    "modal_wait_error",
    "levelup_profession_pending",
    "levelup_profession_unknown",
)
#: 信息项（自愈过程）：关掉/等到/换成别的模态 ⇒ 记"当天被模态打断几次"，不改变结论。
MODAL_INFO_EVENTS = (
    "modal_wait_start",
    "modal_gone",
    "modal_switched",
    "modal_dismissed",
)
MODAL_RED_HINT = {
    "levelup_profession_pending": "职业选择不可逆（dismiss = 永久丢档）⇒ 必须人工来选；当天不判通过",
    "levelup_profession_unknown": "观测里读不到 professionsToChoose（旧 Mod / 反射失败）⇒ 按未知处理，等人确认",
    "modal_timeout": "只等不关的模态（新一天自动存档）超时 ⇒ 可能没落盘，必须人工看一眼",
    "modal_loop_capped": "连关多个模态后还有模态 ⇒ 世界在弹窗循环，必须人工处理",
    "modal_blocked": "当天被模态挡住的留痕（ended_by=blocked_modal）⇒ 人工处理过后才算数",
    "modal_wait_error": "等待模态时桥报错 ⇒ 模态状态未知，必须人工确认",
}
#: `ended_by` 的模态取值（longrun.ENDED_BY_MODAL）；verify-run3.py 把 `ended_by != "sleep"`
#: 直接判为不达标 ⇒ 这里也**绝不许**把这种账本判成通过。
ENDED_BY_MODAL = "blocked_modal"

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
    # verify-run3.py 把 policy_fallback 也算作"无活可做"的证据（0 步 VERIFIED 的豁免之一）
    "policy_fallback": "policy_fallbacks",
    "env_fail": "env_fails",
    "inconclusive_fail": "inconclusive",
    # task-28：同格被环境挡住累计超过 MAX_ENV_ATTEMPTS ⇒ 不再免费（按"没结论"占配额）
    "env_spin_capped": "env_spins",
    "modal_wait_start": "modal_starts",
    "modal_gone": "modal_gones",
    "modal_switched": "modal_switches",
    "modal_dismissed": "modal_dismissals",
    "modal_timeout": "modal_timeouts",
    "modal_blocked": "modal_blockeds",
    "modal_loop_capped": "modal_caps",
    "modal_wait_error": "modal_errors",
    "levelup_profession_pending": "levelup_pending",
    "levelup_profession_unknown": "levelup_unknown",
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


#: 季节顺序（跨日校验用：每季固定 28 天）
SEASON_ORDER = ("spring", "summer", "fall", "winter")


def day_index(day):
    """把 `[year, season, day]` 折成可比较的序号（每季 28 天）；解析不了返回 None。

    只用来做"跨日必须恰好 +1 天"这条校验（与 `tools\\verify-run3.py` 同口径）。
    """
    seq = as_list(day)
    if len(seq) != 3:
        return None
    year = as_int(seq[0], -1)
    season = str(seq[1] or "")
    dom = as_int(seq[2], -1)
    if year < 0 or dom <= 0 or season not in SEASON_ORDER:
        return None
    return year * 112 + SEASON_ORDER.index(season) * 28 + (dom - 1)


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
        # 1c-2: task-36 —— `checks.watered_outdoor` **缺失 ≠ 通过**（与 tools\verify-run3.py:311-316 同向：
        #       它把"缺字段"直接记 problem）。缺失同时会进【无法判定】；这里负责点名到具体 day_end 行。
        #       旧账本（task-19 之前）会整片命中，这是如实读数，不是误报。
        for lineno, ev in sess["day_ends"]:
            checks = as_dict(ev.get("checks"))
            if "watered_outdoor" in checks:
                continue
            out.append(
                finding(
                    lineno, "day_end",
                    f"checks.watered_outdoor 未写（缺失 ≠ 通过）：窗口口径的 unwatered_crops/crops_watered "
                    f"在室内恒 0，不能替它作证（ended_by={ev.get('ended_by')}）；该天不得判通过",
                    hint="task-19 之后应由 longrun._water_evidence 写 farm 级 bool（farm.dryCrops）；"
                         "verify-run3.py:311-316 把缺失直接判问题 —— 两边同向",
                    subject="missed:check:watered_outdoor",
                )
            )
        # 1d: 环境挡路（env_fail）后该阶段最终没做成 ⇒ 活没干成，且不是"格子干不动"（task-30）
        idx = _stage_outcome_index(sess)
        for lineno, ev in sess["env_fails"]:
            stage = ev.get("stage") or "?"
            oc = idx.get(stage)
            if oc is None or oc[1].get("postcondition_met"):
                continue
            statuses = ",".join(str(x) for x in as_list(ev.get("statuses"))) or "-"
            out.append(
                finding(
                    lineno, "env_fail",
                    f"该做没做（环境挡路）：{stage} 有 {as_int(ev.get('tiles'))} 格被 [{statuses}] 挡住后没再补做，"
                    f"该阶段后置条件最终未成立（outcome L{oc[0]}）",
                    hint="重试没覆盖到这些格 ⇒ 看 _stage_tiles 的目标池与 MAX_ENV_ATTEMPTS 的限流",
                    subject="missed:env_fail",
                )
            )
        # 1e: 自述 failed_steps 与 stages[].failed 求和必须对得上；差额只能由环境挡路/无结论解释
        #     （与 tools\verify-run3.py 同源口径：只信 day_end.stages 求和，自述是派生字段）
        for lineno, ev in sess["day_ends"]:
            stages = as_list(ev.get("stages"))
            failed_field = ev.get("failed_steps")
            if not stages or failed_field is None:
                continue
            sum_failed = sum(as_int(s.get("failed")) for s in stages)
            sum_env = sum(as_int(s.get("env_block_count") or s.get("env_block")) for s in stages)
            sum_incon = sum(as_int(s.get("inconclusive_count") or s.get("inconclusive")) for s in stages)
            delta = sum_failed - as_int(failed_field)
            if delta < 0:
                out.append(
                    finding(
                        lineno, "day_end",
                        f"账目不可信：自述 failed_steps={failed_field} 比 stages[].failed 求和 {sum_failed} 还多",
                        hint="只信 day_end.stages 求和；自述 failed_steps 是派生字段",
                        subject="missed:stage_account",
                    )
                )
            elif delta > sum_env + sum_incon:
                out.append(
                    finding(
                        lineno, "day_end",
                        f"账目不可信：自述 failed_steps={failed_field} 比 stages[].failed 求和 {sum_failed} 少 {delta}，"
                        f"而 env_block={sum_env} + inconclusive={sum_incon} 解释不完",
                        hint="差额必须被环境挡路/无结论计数完全解释，否则是自述在洗账"
                             "（verify-run3.py 同口径）别把环境挡路当硬失败",
                        subject="missed:stage_account",
                    )
                )
        # 1f: 主动睡过去了却没跨到"次日"（verify-run3.py：ended_by=sleep 必须有跨日证据）
        if end and end.get("ended_by") == "sleep":
            start = as_dict(sess["start"])
            fin = as_dict(end.get("final"))
            i0 = day_index(start.get("day"))
            i1 = day_index(fin.get("day"))
            if i0 is not None and i1 is not None and i1 != i0 + 1:
                out.append(
                    finding(
                        end_line, "day_end",
                        f"缺跨日证据：ended_by=sleep，但 final 日期 {fin.get('day')!r} 不是 "
                        f"day_start {start.get('day')!r} 的次日",
                        hint="跨日必须恰好 +1 天（verify-run3.py 同口径）；+2 天或倒退都说明账本/世界不对",
                        subject="missed:cross_day",
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
        # 2d: 0 个阶段却自称 VERIFIED ⇒ 必须有"确实无活可做"的证据（verify-run3.py 盲区 B6 同口径）
        for lineno, ev in sess["day_ends"]:
            if not ev.get("verified"):
                continue
            if as_list(ev.get("stages")) or as_int(ev.get("ok_steps")) > 0:
                continue
            reason = str(ev.get("ended_reason") or "")
            excused = bool(sess["no_intents"] or sess["plot_exhausted"] or sess["policy_fallbacks"])
            if not excused:
                excused = any(
                    str(e2.get("reason") or "").startswith(("no_work", "night", "stamina"))
                    for _, e2 in sess["sleeps"]
                )
            if not excused and not reason.startswith(("no_work", "night", "stamina")):
                out.append(
                    finding(
                        lineno, "day_end",
                        f"自称 VERIFIED，但当天 0 个阶段、0 步做成，也没有'无活可做'的证据"
                        f"（ended_reason={reason or '-'}、ok_steps=0）",
                        hint="0 步不能自证做过事。'无活可做'的证据 = no_intents / plot_exhausted / "
                             "policy_fallback 事件，或 sleep/ended_reason 以 no_work/night/stamina 开头"
                             "（verify-run3.py 盲区 B6 同口径）",
                        subject="wasted:verified_without_work",
                    )
                )
        # 2e: checks.watered_outdoor=true 与 final_water.dry>0 不许同时出现（verify-run3.py 盲区 B4）
        for lineno, ev in sess["day_ends"]:
            checks = as_dict(ev.get("checks"))
            dry = as_dict(ev.get("final_water")).get("dry")
            if checks.get("watered_outdoor") is True and isinstance(dry, (int, float)) and dry > 0:
                out.append(
                    finding(
                        lineno, "day_end",
                        f"账本自相矛盾：checks.watered_outdoor=true 但 final_water.dry={dry}",
                        hint="两份自述不许自相矛盾（verify-run3.py 同口径）；dry>0 = 还有没浇的，别信 checks",
                        subject="wasted:water_contradiction",
                    )
                )
        # 2f: task-36 —— `checks.watered_outdoor=true` 但证据来源是"窗口 0 格"（当天根本没有户外快照）
        #     ⇒ 这个 true 不可采信（tools\verify-run3.py:404-413 同向；task-19 卡面 5④ 规定此时必须如实
        #     False/缺省，禁止默认 true）。
        for lineno, ev in sess["day_ends"]:
            checks = as_dict(ev.get("checks"))
            fw = as_dict(ev.get("final_water"))
            if (
                checks.get("watered_outdoor") is True
                and fw.get("scope") == "window"
                and as_int(fw.get("tiles")) == 0
            ):
                out.append(
                    finding(
                        lineno, "day_end",
                        "账本不可信：checks.watered_outdoor=true 但 final_water.scope=window 且覆盖 0 格"
                        "（当天没有任何户外快照）⇒ 这个 true 没有证据来源",
                        hint="task-19 卡面 5④：没有户外快照时必须如实 False/缺省，禁止默认 true"
                             "（verify-run3.py:404-413 同口径）",
                        subject="wasted:water_scope_empty",
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


# ---------------------------------------------------------------- 0/5 模态与环境
def _stage_outcome_index(sess):
    """会话内每个 stage 的**最终** outcome（后写的覆盖先写的）→ {stage: (lineno, ev)}。"""
    idx = {}
    for lineno, ev in sess["outcomes"]:
        kind = ev.get("kind")
        if kind:
            idx[kind] = (lineno, ev)
    return idx


def _env_verdict_text(oc):
    """按"该阶段最终做成了没有"给出可判定结论（不猜）。"""
    if oc is None:
        return "本会话没有该阶段的 outcome ⇒ 无法判定这轮最终做成了没有"
    ln, ev = oc
    if ev.get("postcondition_met"):
        return f"该阶段最终后置条件成立（outcome L{ln}）⇒ 重试成功，纯信息项"
    return f"该阶段最终后置条件未成立（outcome L{ln}）⇒ 这些格计入「1 该做没做」的成因"


def cat_manual(sessions, top):
    """0 必须人工介入（红）：不可逆/等不到人的模态，以及 `ended_by=blocked_modal` 的当天。

    可判定判据（只看账本，不靠猜）：
      * 事件名命中 `MODAL_RED_EVENTS` —— 这些事件的产生路径就是 longrun 的
        `_modal_blocked`（职业选择不可逆 / 存档模态超时 / 连关不完 / 等模态时报错）；
      * `day_end.ended_by == "blocked_modal"`；
      * `day_end.checks.no_blocking_modal is False`（**不允许**当通过，与 `tools\\verify-run3.py`
        的 `ended_by != "sleep"` ⇒ 不达标同口径）。
    """
    out = []
    for sess in sessions:
        for name in MODAL_RED_EVENTS:
            for lineno, ev in sess[EVENT_BUCKETS[name]]:
                ids = as_list(ev.get("ids"))
                detail = f"menu={ev.get('menu') or '-'}"
                if ev.get("reason"):
                    detail += f"，reason={str(ev.get('reason'))[:80]}"
                if ids:
                    detail += f"，候选职业={ids}"
                out.append(
                    finding(
                        lineno, name,
                        f"必须人工介入：{name}（{detail}）",
                        hint=MODAL_RED_HINT.get(name, "不可逆/状态未知的模态 ⇒ 停下等人，当天不判通过"),
                        subject=f"manual:{name}",
                    )
                )
        for lineno, ev in sess["day_ends"]:
            checks = as_dict(ev.get("checks"))
            ended_by = ev.get("ended_by")
            if ended_by == ENDED_BY_MODAL:
                out.append(
                    finding(
                        lineno, "day_end",
                        f"必须人工介入：这一天以 ended_by={ENDED_BY_MODAL} 收尾"
                        f"（{str(ev.get('ended_reason'))[:80]}）；verified={ev.get('verified')}、"
                        f"no_blocking_modal={checks.get('no_blocking_modal')}",
                        hint="verify-run3.py 把 ended_by != sleep 直接判不达标；这里也不许当通过",
                        subject="manual:ended_by_blocked_modal",
                    )
                )
            elif checks.get("no_blocking_modal") is False:
                out.append(
                    finding(
                        lineno, "day_end",
                        f"必须人工介入：checks.no_blocking_modal=false（ended_by={ended_by}）"
                        f"—— {CHECK_MEANING.get('no_blocking_modal')}",
                        hint="缺失 ≠ 没挡过；false 更不许当通过（与 verify-run3.py 同口径）",
                        subject="manual:check:no_blocking_modal",
                    )
                )
    return out[:top] if top else out


def cat_environment(sessions, top):
    """5 环境挡路 / 没拿到结论（信息项，口径可判定 —— 不拍脑袋）。

    判据来自 longrun/farmwork（task-22）：
      * `env_fail`（= `stages[].env_block`，statuses ∈ `busy`/`world_fading`/`ui_modal`/`no_save`）：
        环境挡路**不是这一格的属性** ⇒ 不封格、也不占本日尝试配额。归类规则 = 看**同一会话里该
        stage 的最终 outcome**：成立 ⇒ 重试成功（纯信息项）；未成立 ⇒ 这些格并进"该做没做"
        （活没干成，且不是格子干不动）；没有 outcome ⇒ 如实写"无法判定"。
      * `inconclusive_fail`（= `stages[].inconclusive`，statuses ∈ `timeout`/`error`/`stale`）：
        连结论都没拿到 ⇒ **占本日尝试配额**（连续发生会把格子推到 capped ⇒ 当天 needs_review），
        所以永远额外记一句"配额被吃掉 N 格"。
    """
    out = []
    for sess in sessions:
        idx = _stage_outcome_index(sess)
        for key, name in (("env_fails", "env_fail"), ("inconclusive", "inconclusive_fail")):
            for lineno, ev in sess[key]:
                stage = ev.get("stage") or "?"
                tiles = as_int(ev.get("tiles"))
                statuses = ",".join(str(x) for x in as_list(ev.get("statuses"))) or "-"
                oc = idx.get(stage)
                verdict = _env_verdict_text(oc)
                unfinished = oc is not None and not oc[1].get("postcondition_met")
                if name == "env_fail":
                    out.append(
                        finding(
                            lineno, name,
                            f"环境挡路：{stage} @ zone={ev.get('zone')} 有 {tiles} 格被 [{statuses}] 挡住"
                            f"（不封格、不占配额）；{verdict}",
                            hint="env_block（busy/渐黑/模态/没存档）不是'格子干不动'；"
                                 "只有最终没做成时才并进'该做没做'（见'1 该做没做'的 missed:env_fail）",
                            subject=("environment:env_fail:unfinished" if unfinished
                                     else "environment:env_fail"),
                        )
                    )
                else:
                    out.append(
                        finding(
                            lineno, name,
                            f"没拿到结论：{stage} @ zone={ev.get('zone')} 有 {tiles} 格 [{statuses}]"
                            f"（占本日尝试配额 ⇒ 配额被吃掉 {tiles} 格）；{verdict}",
                            hint="inconclusive（timeout/error/stale）连结论都没拿到；连续发生会把格子"
                                 "推到 capped ⇒ 当天 needs_review",
                            subject=("environment:inconclusive:unfinished" if unfinished
                                     else "environment:inconclusive"),
                        )
                    )
        # task-28：同一格反复被环境挡住到上限 ⇒ 从这次起按"没结论"占配额（信息项，但要能看出是哪几格）
        for lineno, ev in sess["env_spins"]:
            tile = as_list(ev.get("tile"))
            out.append(
                finding(
                    lineno, "env_spin_capped",
                    f"环境挡路自旋到上限：格 {tile} 连续被挡 {ev.get('streak')} 次"
                    f"（limit={ev.get('limit')}）⇒ 从这次起按「没结论」占本日尝试配额；"
                    f"{str(ev.get('note') or '')[:60]}",
                    hint="不是'格子干不动'（不封格），但一直 busy/渐黑会把这一格推到 capped ⇒ 当天 "
                         "needs_review；先对着同 stage 的 env_fail.statuses 看当时在忙什么",
                    subject="environment:env_spin_capped",
                )
            )
    return out[:top] if top else out


# ---------------------------------------------------------------- 建议 / 无法判定
def cat_self_report(report):
    """账本**自述之间**的自相矛盾（与 `tools\\verify-run3.py` 盲区 B1 同口径）。

    只做两条纯自洽检查，不重复它的验收判定：
      * `finish` 自身自洽：`code==0 ⇔ verified_streak >= days`；
      * `finish.code` 与"账本正文里 verified 的天数"同向（且两边目标天数相同才比，避免误报）。
    """
    out = []
    finish = report.get("finish") or {}
    if not finish:
        return out
    line = finish.get("line")
    code = finish.get("code")
    streak = as_int(finish.get("verified_streak"))
    requested = as_int(report.get("days_requested"))
    days = as_int(finish.get("days"), requested)
    verified_days = as_int(report.get("verified_days"))
    if days > 0 and (code == 0) != (streak >= days):
        out.append(
            finding(
                line, "finish",
                f"finish 自身不自洽：code={code} 与 verified_streak={streak}/days={days} 不符",
                hint="finish 是自述字段：code==0 必须等价于连续 VERIFIED 天数达标"
                     "（verify-run3.py 同口径）",
                subject="wasted:finish_incoherent",
            )
        )
    elif days > 0 and days == requested and (code == 0) != (verified_days >= days):
        out.append(
            finding(
                line, "finish",
                f"finish 自述 code={code}，但账本正文里 verified 天数只有 {verified_days}/{days}（应同向）",
                hint="自述与正文必须同向（verify-run3.py 盲区 B1）；自述达标而正文一天没达标 "
                     "= 自述在洗账",
                subject="wasted:finish_vs_days",
            )
        )
    return out


def build_advice(report, top=8):
    advice = []
    events = report["events"]
    sessions = report["_sessions"]
    # 0) 必须人工介入（红）：放最前面，别被 --top 截掉
    manual = report.get("manual_intervention") or {}
    if manual.get("total"):
        advice.append({
            "text": f"有 {manual['total']} 条「必须人工介入（红）」记录"
                    f"（模态挡住 / 职业选择 / 存档超时）：当天一律不判通过，先人工处理再跑",
            "lines": manual.get("red_lines") or [],
        })
    # 0b) 模态打断次数（自愈信息项）
    if manual.get("modal_interrupts_total"):
        advice.append({
            "text": f"模态打断 {manual['modal_interrupts_total']} 次（等待/关闭/换人）："
                    "本身是自愈信息项，但次数异常偏高说明世界在弹窗循环，值得看一眼",
            "lines": manual.get("modal_interrupt_lines") or [],
        })
    # 0c) 环境挡路 / 没拿到结论（task-22 记账）
    env = report.get("env_inconclusive") or {}
    if env.get("env_fail_events"):
        advice.append({
            "text": f"环境挡路 ×{env['env_fail_events']}（{env.get('env_fail_tiles', 0)} 格，"
                    f"statuses={env.get('statuses') or '-'}）：不封格但吃掉当天时间；"
                    f"当天被环境挡住共 {env.get('env_blocked_total', env['env_fail_events'])} 次（含自旋）；"
                    f"其中 {env.get('env_fail_unfinished_tiles', 0)} 格所在阶段最终没做成（并入'该做没做'）",
            "lines": env.get("env_fail_lines") or [],
        })
    if env.get("inconclusive_events"):
        advice.append({
            "text": f"没拿到结论 ×{env['inconclusive_events']}（配额被吃掉 {env.get('inconclusive_tiles', 0)} 格）："
                    "timeout/error/stale 连续发生会把格子推到 capped ⇒ 当天 needs_review",
            "lines": env.get("inconclusive_lines") or [],
        })
    # 0d) 环境挡路自旋到上限（task-28；信息项，但要看得出哪几格在反复被挡）
    if env.get("env_spin_events"):
        tiles = env.get("env_spin_tiles") or []
        advice.append({
            "text": f"环境挡路自旋到上限 ×{env['env_spin_events']}（同一格被挡住超过 MAX_ENV_ATTEMPTS=2 次后"
                    f"改按'没结论'占配额）：本身是信息项，但要一眼看出是哪几格在反复被挡"
                    f"（{tiles[:top] or '-'}）；同一格反复出现就先查渐黑/模态循环",
            "lines": env.get("env_spin_lines") or [],
        })
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
    # 3b) 账本自述自相矛盾（finish 自身 / 自述 vs 正文；verify-run3.py 盲区 B1）
    integrity = [
        f for f in report["categories"]["wasted"]
        if f["subject"] in ("wasted:finish_incoherent", "wasted:finish_vs_days")
    ]
    if integrity:
        advice.append({
            "text": f"账本自述与正文对不上 ×{len(integrity)}：finish 的 code/verified_streak 与正文里 verified 的"
                    "天数不同向 ⇒ 先别信自述字段，以正文为准（与 verify-run3.py 独立交叉核对，冲突就停下来对账）",
            "lines": [f["line"] for f in integrity if f["line"] is not None],
        })
    # 3c) task-36：浇水证据缺失/自相矛盾（与 tools\verify-run3.py 四个闸门同向）
    water_bad = [f for f in report["categories"]["missed"] if f["subject"] == "missed:check:watered_outdoor"]
    water_bad += [f for f in report["categories"]["wasted"] if f["subject"].startswith("wasted:water_")]
    if water_bad:
        advice.append({
            "text": f"浇水证据有问题 ×{len(water_bad)}：缺 watered_outdoor（缺失 ≠ 通过）或自述 true 与 "
                    "final_water 打架 ⇒ 别信窗口口径，按 farm.dryCrops（task-19）复核"
                    "（verify-run3.py 同向；run3 前必须把这条清零）",
            "lines": [f["line"] for f in water_bad if f["line"] is not None],
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
    # 7) LLM fallback / 截断
    fallback = []
    for sess in sessions:
        for lineno, ev in sess["decisions"]:
            # brain 把 LLM 侧截断单独写成 `truncated=true`（run2 另有 source=…_fallback）
            if ev.get("fallback") or str(ev.get("source") or "").endswith("fallback") or ev.get("truncated"):
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
            # task-36：以 day_end 的键为准（整本都没有 ⇒ 单列"本账本没有该字段"）
            ends = [ev for _, ev in rows if ev.get("event") == "day_end"]
            absent = (not any("final_water" in ev for ev in ends)) if ends else ("\"final_water\"" not in blob)
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
    # task-11：没有模态记账 ≠ 没被模态挡过（只能算"无法判定"）
    has_modal_event = any(name in names for name in MODAL_RED_EVENTS + MODAL_INFO_EVENTS)
    has_modal_check = any(
        "no_blocking_modal" in as_dict(ev.get("checks"))
        for _, ev in rows if ev.get("event") == "day_end"
    )
    if not has_modal_event and not has_modal_check:
        out.append("本账本没有任何模态事件（modal_*/levelup_*）、也没有 checks.no_blocking_modal："
                   "无法判定当天是否被模态打断过（task-11 之前的账本）—— **缺失不等于没被挡过**")
    # task-36：自称浇过、却没有 final_water 可核对的那些天（verify-run3.py:414-418 同口径：只记信息项）
    no_fw = [
        lineno for lineno, ev in rows
        if ev.get("event") == "day_end"
        and as_dict(ev.get("checks")).get("watered_outdoor") is True
        and not isinstance(ev.get("final_water"), dict)
    ]
    if no_fw:
        out.append(f"有 {len(no_fw)} 天 checks.watered_outdoor=true 但没写 final_water（行 {no_fw[:8]}）："
                   "无法核对浇水证据来自哪张快照（缺证据 ≠ 通过；verify-run3.py:414-418 同口径只记信息项、"
                   "不额外判问题）")
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
            # task-36：浇水证据（scope/tiles/crops/dry）随天带出来，供"每天一行"与测试核对
            "final_water": as_dict(end.get("final_water")),
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
    # LLM 边界：`decision` 的 source/llm/boundary/truncated（brain 实写这四键，无 token/usage）
    decisions = [ev for _, ev in rows if ev.get("event") == "decision"]
    decision_by_source = {}
    decision_by_boundary = {}
    for ev in decisions:
        src = str(ev.get("source") or "?")
        decision_by_source[src] = decision_by_source.get(src, 0) + 1
        boundary = str(ev.get("boundary") or "(none)")
        decision_by_boundary[boundary] = decision_by_boundary.get(boundary, 0) + 1
    decision_counts = {
        "total": len(decisions),
        "llm": sum(1 for ev in decisions if ev.get("llm") or ev.get("source") == "llm"),
        "by_source": decision_by_source,
        "by_boundary": decision_by_boundary,
        "truncated_lines": [ln for ln, ev in rows
                            if ev.get("event") == "decision" and ev.get("truncated")],
    }
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
        "decision_counts": decision_counts,
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
    # task-11/22：模态与环境记账（prelude 也算 —— day_start 之前也可能被模态挡住）
    all_sessions = [prelude] + list(sessions)
    for day, sess in zip(days, sessions):
        day["modal_interrupts"] = len(sess["modal_starts"]) + len(sess["modal_dismissals"])
    manual_all = cat_manual(all_sessions, 0)
    env_all = cat_environment(all_sessions, 0)
    env_fail_tiles = 0
    env_unfinished_tiles = 0
    inconclusive_tiles = 0
    env_fail_lines = []
    inconclusive_lines = []
    statuses = set()
    env_spin_lines = []
    env_spin_tiles = set()
    t_regressions = []
    for sess in all_sessions:
        idx = _stage_outcome_index(sess)
        for ln, ev in sess["env_fails"]:
            env_fail_lines.append(ln)
            env_fail_tiles += as_int(ev.get("tiles"))
            statuses.update(str(x) for x in as_list(ev.get("statuses")))
            oc = idx.get(ev.get("stage") or "?")
            if oc is not None and not oc[1].get("postcondition_met"):
                env_unfinished_tiles += as_int(ev.get("tiles"))
        for ln, ev in sess["inconclusive"]:
            inconclusive_lines.append(ln)
            inconclusive_tiles += as_int(ev.get("tiles"))
            statuses.update(str(x) for x in as_list(ev.get("statuses")))
        for ln, ev in sess["env_spins"]:
            env_spin_lines.append(ln)
            tile = ev.get("tile")
            if isinstance(tile, (list, tuple)) and len(tile) == 2:
                env_spin_tiles.add((as_int(tile[0]), as_int(tile[1])))
        # `t` 只该单调不减；回退只记信息项（verify-run3.py 同口径，不当失败）
        prev_t = None
        for ln, ev in sess["events"]:
            t = ev.get("t")
            if not isinstance(t, (int, float)):
                continue
            if prev_t is not None and t < prev_t:
                t_regressions.append(
                    {"line": ln, "day": day_label(sess.get("start") or {}), "t0": prev_t, "t1": t}
                )
            prev_t = t
    env_blocked_total = sum(len(s["env_fails"]) for s in all_sessions) + sum(
        len(s["env_spins"]) for s in all_sessions
    )
    report["manual_intervention"] = {
        "total": len(manual_all),
        "red_lines": sorted({f["line"] for f in manual_all if f["line"] is not None}),
        "red_subjects": sorted({f["subject"] for f in manual_all}),
        "by_event": {name: events.get(name, 0) for name in MODAL_RED_EVENTS if events.get(name)},
        "modal_events": {name: events.get(name, 0) for name in MODAL_RED_EVENTS + MODAL_INFO_EVENTS},
        "modal_interrupts_total": sum(len(s["modal_starts"]) + len(s["modal_dismissals"])
                                     for s in all_sessions),
        "modal_interrupt_lines": sorted(
            {ln for s in all_sessions
             for key in ("modal_starts", "modal_dismissals") for ln, _ in s[key]}
        ),
    }
    report["env_inconclusive"] = {
        "env_fail_events": sum(len(s["env_fails"]) for s in all_sessions),
        "env_fail_tiles": env_fail_tiles,
        "env_fail_unfinished_tiles": env_unfinished_tiles,
        "env_fail_lines": sorted(set(env_fail_lines)),
        "inconclusive_events": sum(len(s["inconclusive"]) for s in all_sessions),
        "inconclusive_tiles": inconclusive_tiles,
        "inconclusive_lines": sorted(set(inconclusive_lines)),
        # task-28：同一格被环境挡住累计超过 MAX_ENV_ATTEMPTS 后只写一次；信息项，但计入被挡次数
        "env_spin_events": sum(len(s["env_spins"]) for s in all_sessions),
        "env_spin_lines": sorted(set(env_spin_lines)),
        "env_spin_tiles": sorted([list(t) for t in env_spin_tiles]),
        "env_blocked_total": env_blocked_total,
        "statuses": sorted(statuses),
    }
    # `t` 回退（只记信息项）
    report["t_regressions"] = t_regressions
    self_report = cat_self_report(report)
    report["categories"] = {
        "manual": cat_manual(all_sessions, args.top),
        "missed": cat_missed(sessions, args.top),
        "wasted": (cat_wasted(sessions, args.top) + self_report)[:args.top],
        "ineffective": cat_ineffective(sessions, args.top),
        "sleep": cat_sleep(sessions, args.top, args.stamina_full, args.sleep_pct),
        "environment": cat_environment(all_sessions, args.top),
    }
    report["categories_total"] = {
        "manual": len(manual_all),
        "missed": len(cat_missed(sessions, 0)),
        "wasted": len(cat_wasted(sessions, 0)) + len(self_report),
        "ineffective": len(cat_ineffective(sessions, 0)),
        "sleep": len(cat_sleep(sessions, 0, args.stamina_full, args.sleep_pct)),
        "environment": len(env_all),
    }
    report["advice"] = build_advice(report)
    report["undecidable"] = build_undecidable(rows, sessions, prelude, report)
    return report


MAPPING_TEXT = [
    ("day_start", "会话/天边界（每天一行摘要）"),
    ("decision",
     "顶部统计：总次数/LLM 次数/来源/边界（new_day、task_kind_change、recovery…）；"
     "fallback 或 truncated=true ⇒ 建议 7（LLM 截断/兜底）"),
    ("decision.truncated=true", "信息项（LLM 回答被截断；并入建议 7）"),
    ("blocked.no_effect / stage_exhausted.capped|doomed",
     "辅助字段（本工具现用 reason/action/tile；no_effect=true 表示世界无变化）"),
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
    ("modal_blocked / modal_timeout / modal_loop_capped / modal_wait_error",
     "0 必须人工介入（红：模态挡住/超时 ⇒ ended_by=blocked_modal，当天不判通过）"),
    ("levelup_profession_pending / levelup_profession_unknown",
     "0 必须人工介入（红：不可逆职业选择 ⇒ 停下等人）"),
    ("day_end.checks.no_blocking_modal=false / ended_by=blocked_modal",
     "0 必须人工介入（红：一律不判通过，与 verify-run3.py 同口径）"),
    ("modal_wait_start / modal_gone / modal_switched / modal_dismissed",
     "顶部统计：模态打断 N 次（信息项，自愈过程；不改结论）"),
    ("env_fail / day_end.stages[].env_block",
     "5 环境挡路（信息项；同 stage 最终没做成 ⇒ 并入'1 该做没做'）"),
    ("env_spin_capped",
     "5 环境挡路自旋到上限（信息项，但计入当天被环境挡住的总次数；能一眼看出哪几格在反复被挡）"),
    ("inconclusive_fail / day_end.stages[].inconclusive",
     "5 没拿到结论（信息项 + 配额被吃掉 N 格 ⇒ 可能 capped/needs_review）"),
    ("day_end.checks.watered_outdoor",
     "1 该做没做（红）：**缺失 = 没有 farm 级证据（≠ 通过）**、false = 睡前还有没浇的"
     "（verify-run3.py:311-318 同向）"),
    ("day_end.checks.watered_outdoor / day_end.final_water",
     "2 白做：true 与 final_water.dry>0 互斥（自相矛盾）；true 且 scope=window/tiles=0 不可采信"
     "（当天没有户外快照）；true 但整条没写 final_water ⇒ 只进【无法判定】"
     "（verify-run3.py:393-418 同向）"),
    ("day_end.checks.no_unmet_stages",
     "1 该做没做（false = 有阶段没达成；不与自算一致时以自算为准）"),
    ("finish",
     "收尾自述：code/verified_streak 必须自身自洽、并与正文 verified 天数同向（不同向 ⇒ 自述在洗账）"),
    ("t 回退",
     "信息项：同一会话内 t 倒退只记录，不判失败（verify-run3.py 同口径）"),
    ("本工具与 tools\\verify-run3.py", "独立读数、交叉核对：同一本账本给出相反结论 ⇒ 停下来人工对账，别单方面改口径"),
    ("refill / goto_farm / plot", "辅助：补水、回农场、观测（截断警告）"),
    ("idle", "辅助：一整轮没动作（acted/rounds）⇒ 空转，常与'该做没做'并看"),
    ("seed_gate", "辅助：种子/钱不够 ⇒ till/plant 被跳过（不算硬失败）"),
    ("plot_walk", "辅助：换片地（zone/stage）"),
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
    dc = report.get("decision_counts") or {}
    if dc.get("total"):
        src_txt = "、".join(f"{k}={v}" for k, v in sorted(dc["by_source"].items()))
        bnd_txt = "、".join(f"{k}={v}" for k, v in sorted(dc["by_boundary"].items()))
        add(f"决策: {dc['total']} 次（LLM {dc['llm']}）；来源 {src_txt}；边界 {bnd_txt}"
            + (f"；truncated={len(dc['truncated_lines'])} 行 {dc['truncated_lines'][:5]}"
               if dc["truncated_lines"] else "；无 truncated"))
    mi = report.get("manual_intervention") or {}
    red_total = mi.get("total", 0)
    add(f"模态: 打断 {mi.get('modal_interrupts_total', 0)} 次（信息项）"
        f"；必须人工介入（红）{red_total} 条"
        + ("  ⚠ 当天不判通过" if red_total else "")
        + (f"；by_event={mi.get('by_event')}" if mi.get("by_event") else ""))
    env = report.get("env_inconclusive") or {}
    add(f"环境挡路: {env.get('env_fail_events', 0)} 条（{env.get('env_fail_tiles', 0)} 格，"
        f"其中 {env.get('env_fail_unfinished_tiles', 0)} 格所在阶段最终没做成）；"
        f"自旋到上限 {env.get('env_spin_events', 0)} 次"
        + (f"（tiles={env.get('env_spin_tiles')}）" if env.get("env_spin_tiles") else "")
        + f"；没拿到结论: {env.get('inconclusive_events', 0)} 条（配额被吃掉 {env.get('inconclusive_tiles', 0)} 格）"
        + (f"；statuses={env.get('statuses')}" if env.get("statuses") else ""))
    t_reg = report.get("t_regressions") or []
    if t_reg:
        add(f"t 回退: {len(t_reg)} 次（信息项，行 {[r['line'] for r in t_reg][:8]}"
            "；只说明日志里 t 抖动，不判失败）")
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
            # task-36：浇水证据单独摆出来（缺失/自相矛盾不许被 verified=true 掩盖）
            fw = day.get("final_water") if isinstance(day.get("final_water"), dict) else {}
            if "watered_outdoor" not in day["checks"]:
                water_text = " | 浇水证据=缺（缺失 ≠ 通过，本工具不判该天通过）"
            elif day["checks"].get("watered_outdoor") is False:
                water_text = " | 浇水证据=false（睡前还有没浇的作物）"
            elif fw:
                water_text = (f" | 浇水证据={fw.get('scope')}/{fw.get('location')} dry={fw.get('dry')}"
                              f"/{fw.get('crops')} tiles={fw.get('tiles')}")
            else:
                water_text = " | 浇水证据=true 但无 final_water 可核对"
            add(f"  - {day['label']}: ended_by={day['ended_by']} verified={day['verified']} "
                f"ok/skip/fail={day['ok_steps']}/{day['skipped_steps']}/{day['failed_steps']} "
                f"checks[{checks}] 模态打断={day.get('modal_interrupts', 0)}{water_text} "
                f"L{day['day_end_lines']}{final_text}")
    add("")
    sections = [
        ("0 必须人工介入（红）", "manual", "必须人工介入"),
        ("1 该做没做", "missed", "该做没做"),
        ("2 白做", "wasted", "白做"),
        ("3 无效挥动", "ineffective", "无效挥动"),
        ("4 睡觉时机", "sleep", "睡觉时机"),
        ("5 环境挡路 / 没拿到结论", "environment", "环境挡路 / 没拿到结论"),
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
