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
     同一格被挡住超过 MAX_ENV_ATTEMPTS=2 后改按"没结论"占配额）、**不可达**（unreachable /
     unreachable_stage / unreachable_summary，task-52：四邻都站不过去 / A* 算不出路；政策是
     **不计当天硬失败**、当天记 blocked、**次日重试**，日级豁免有上界 max(5, 20%×attempted)）、
     **被游戏拒绝**（tool_refused / refused_stage / refused_summary，task-63/task-66：
     till 的 tool_ineffective/precondition_failed；政策同上但**独立起界**，两套豁免不许互相掩护）
     与没拿到结论（inconclusive_fail，占配额 ⇒ "配额被吃掉 N 格"）
外加：每天一行摘要、3-8 条带证据行的改进建议、"本账本无法判定"清单。

与 `tools\\verify-run3.py` 的关系：两者**独立读数、交叉核对**。本工具只做分析、不判验收；
但下列口径与它对齐（同一本账本给出相反结论 ⇒ 停下来人工对账，别单方面改口径）：
  * `blocked_modal` / `checks.no_blocking_modal=false` 一律**不判通过**（红）；
  * 0 个阶段却自称 VERIFIED 必须有"无活可做"的证据（`no_intents`/`plot_exhausted`/
    `policy_fallback` 事件，或 sleep/ended_reason 以 `no_work`/`night`/`stamina` 开头）；
  * `failed_steps` 与 `sum(stages[].failed)` 的差额必须被 `env_block(+count)` + `inconclusive(+count)`
    完全解释（否则"账目不可信"；`unreachable` **不在**这个差额口径里 —— verify-run3.py:388-404 只认前两者，
    不可达格被 exempt 后本就不该出现在 `stages[].failed`）；
  * 浇水证据（task-19/task-36，与 `tools\verify-run3.py` 四个闸门同向）：`checks.watered_outdoor`
    **缺失 = 红（缺失 ≠ 通过）**、`false` = 红、`true` + `final_water.scope=="window"` + `tiles==0` = 红
    （当天没有户外快照 ⇒ 这个 true 没有证据来源）、`true` + `final_water.dry>0` = 红（自相矛盾）；
    而 `true` 但整条没写 `final_water` 只在【无法判定】里点名（verify-run3.py 记信息项）。
  * 没活却还有干地（task-60）：`ended_reason` 以 `no_work` 开头 **且** `final_water.dry>0` ⇒ 判红
    （`missed:no_work_with_dry`），并让 `checks.day_justified` 在该形态下**不成立**
    （`day_justified_effective=false`）；`final_water` 缺失 ⇒ 只进【无法判定】（缺失 ≠ 通过，
    也不凭空判红）—— 与 `tools\verify-run3.py` 的同一专判同向。
  * 跨日证据（task-38）：权威字段是 `day_end.day_after`（睡后**重取**的观测）——有它就必须"恰好 +1 天"，
    否则记 `missed:cross_day`；**没有它**（旧账本）时只在 `final` 明确指向另一天时才退回旧口径；
    `final` 还停在 `day_start` 那一天时只能记【无法判定】（`final` 是**睡前**快照，
    真机 0.7.23 彩排就是这一档：回执写"已跨日 spring 17→18"、`final` 还是 17 日 ⇒ **缺失 ≠ 没做**）；
  * `t` 回退只记信息项；环境挡路**不算硬失败**。
  * 不可达豁免（task-52）：`checks.unreachable_within_bound=false`（当天不可达格数超过
    max(5, 20%×attempted)）⇒ 0 类红（豁免越界＝可能把真失败当"走不到"洗白）；
    `unreachable`/`unreachable_stage`/`unreachable_summary` 本身只作信息项、**不并进"该做没做"**
    （tools\verify-run3.py:415-448 同向：上界内是 info、越界才是 problem）。
  * 被游戏拒绝（task-63/task-66）：`checks.refused_within_bound=false`（当天被拒绝格数超过
    max(5, 20%×attempted)）⇒ 0 类红 `manual:check:refused_within_bound`（可能把真失败混进
    "游戏拒绝"洗白）；`tool_refused`/`refused_stage`/`refused_summary` 本身只作信息项（5 环境挡路）、
    **不并进"该做没做"**，日级看 `refused_bound`/`refused_exempt`（与 `unreachable`
    **独立起界、各自扣减、不许互相掩护**）；`day_end.refused*` / `checks.refused_within_bound`
    **缺失 ⇒ 只进【无法判定】**（缺失 ≠ 通过；tools\verify-run3.py:518-521 同向）。
  * 可达性/开路（task-68/task-76，verify-run3.py:307-332/613-643 同向）：`encircled` /
    `encircled_stage` / `encircled_summary`（被树/桩/大石围住 ⇒ 四邻没有「可站+可清」的突破口）
    与 `frontier_clear`（目标都够不着时至少清一格可达的可清障格；**`acted=false` = 想清没清掉**）、
    `clear_neighbor`（开路清掉的邻格）**没有硬闸门**（不存在 `encircled_within_bound`）⇒ 一律
    **只作 5 环境挡路·可达性/开路信息项、不判红、不并进"该做没做"**；与 `unreachable`（物理走不到）
    **分开计数**、不进任何豁免分子、不封格；`day_end.encircled*` **缺失 ⇒ 只进【无法判定】**。
    额外把 `stuck` + `Σ stage.ok == 0` 的"零动作收工"单列（头部 ⚠ + 建议 0j），让 run6 那种
    "19 秒零动作收工"下次一眼可见。
  * 事件映射不许漂移（Lead m02395）：brain 里 `_journal("<name>"` 的**每个**事件名都要在
    `EVENT_BUCKETS` 里有桶（结构性事件 `day_start`/`day_end`/`finish` 除外，见 `STRUCTURAL_EVENTS`）；
    账本里出现没桶的事件 ⇒ 报告头部逐条点名（名字×次数+行号）+ 建议 0a，**绝不静默丢弃**。
    `decision` 的 LLM 计数与 `tools\verify-run3.py:588-589` 同口径，且按 Lead m02565 拆两档
    （同名同义）：`decisions_llm` = 发起过模型调用（`llm` 为真，含被拒/截断）；
    `decisions_llm_used` = 模型结果真被采纳（`llm` 为真且 `source=="llm"`）；
    二者之差 = `decisions_llm_fallback`（= `deterministic_fallback`，模型答了没用）。
    **判据说"LLM 覆盖"一律指 `decisions_llm_used`**；并把 `llm` 与 `source=llm` 不一致的行单列出来
    （四路对账要停下核对）。
  * 真空日/弱日（task-64，Lead m02981）：`day_end.verified=true` 且**当天有阶段记录**且
    `Σ stage.ok == 0` ⇒ 红 `wasted:verified_zero_steps`（文案含"自称 VERIFIED 但当天成功动作 0 步"，
    与 `tools\verify-run3.py:604-625` 的 problem 逐字对账）；`0 < Σ ok < 5` ⇒ 顶部"弱日"信息项；
    `stages` 与 `ok_steps` 都缺 ⇒ 只进【无法判定】（缺失 ≠ 通过，也不当 0 步判红）。
    **不许放宽**既有的 `wasted:verified_without_work`（它只管"当天 0 阶段 + 无'无活可做'证据"），两条并存。

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
    # task-32/task-38：白名单只有 night/stamina/no_work（longrun.JUSTIFIED_END_REASONS）；
    # `no_plot`（作业区配额到顶）是**我们自己设的软上限**，不许当"正当收工理由"。
    "day_justified": "收工理由不在允许集（night/stamina/no_work；no_plot 不是正当理由）",
    # task-19/task-36：窗口口径在室内恒 0，不能当浇水证据 ⇒ 必须由 farm 级字段作证（缺失 ≠ 通过）
    "watered_outdoor": "缺 farm 级/户外浇水证据、或自述还有没浇的作物（缺失 ≠ 通过；"
                       "窗口 unwatered_crops 在室内恒 0，不作证据）",
    # task-15：阶段后置条件未成立的显式汇总（缺失时本工具按 day_end.stages 自算兜底）
    "no_unmet_stages": "有目标阶段留下了没做完的格子（leftover>0）",
    # task-52：不可达豁免的**硬上界**（与 tools\verify-run3.py:445-448 同向：越界直接判 problem）
    "unreachable_within_bound": "当天'unreachable'格数超过上界 max(5, 20%×attempted)"
                                "—— 可能把真失败/不可动格混进不可达来洗白，必须人工核对 unreachable_tiles",
    # task-63/task-66：被**游戏拒绝**（till 的 tool_ineffective / precondition_failed）的硬上界
    "refused_within_bound": "当天'被游戏拒绝'的格数超过上界 max(5, 20%×attempted)"
                            "—— 可能把真失败混进'游戏拒绝'来洗白，必须人工核对 refused_tiles"
                            "（与 unreachable 是两套独立豁免，互不掩护）",
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
    # task-38：睡后重取的观测才是跨日权威证据（`final` 是**睡前**快照）
    ("day_end.day_after", "day_after",
     "睡后重取的观测 [年,季,日]（task-38：权威跨日证据；缺失 ⇒ 只能记【无法判定】，不能当'没跨日'）"),
    # task-32：两种新事件的可见性（deputy `docs\_review-task32.md` NIT-②）
    ("event:plots_capped", "plots_capped",
     "作业区软上限触顶的留痕（task-32：plots_today/limit/zone/tiles；纯信息项，不改 VERIFIED）"),
    ("event:work_spot", "work_spot",
     "收尾作业区（task-32：拿不出田区、守卫却说还有活时用的容器；zone/tiles；不如 no_plot 收工）"),
    ("event:stage_exhausted", "stage_exhausted", "阶段级'没有目标'的显式记录"),
    ("event:stage_no_target", "stage_no_target", "阶段级'没有目标'的旧记录"),
    ("event:plot_exhausted", "plot_exhausted", "片区级'没有目标'的换片记录"),
    ("event:idle", "idle", "无意图空转轮次"),
    # task-11：缺失只能算"没记账"，绝不能当"没被模态挡过"（verify-run3.py 同口径）。
    ("day_end.checks.no_blocking_modal", "no_blocking_modal",
     "当天是否被'不敢关/不可逆'的模态挡住（task-11 新增）"),
    # task-52：不可达（四邻都站不过去 / A* 算不出路）的三级留痕与日级豁免证据
    ("event:unreachable_summary", "unreachable_summary",
     "日级不可达汇总（task-52：count/bound/attempted/exempted/raw_unmet/unmet；tiles 可查）"),
    ("day_end.unreachable", "unreachable",
     "当天不可达格数（task-52；与 unreachable_bound/unreachable_exempt 互检）"),
    ("day_end.unreachable_tiles", "unreachable_tiles",
     "当天不可达格坐标 [[x,y],…]（task-52；越界时人工核对用）"),
    ("day_end.unreachable_bound", "unreachable_bound",
     "不可达豁免上界 max(5, 20%×attempted)（task-52）"),
    ("day_end.unreachable_exempt", "unreachable_exempt",
     "真正从 no_unmet_stages 里扣掉的不可达格数（task-52：先扣它再比 checks.no_unmet_stages）"),
    ("day_end.checks.unreachable_within_bound", "unreachable_within_bound",
     "不可达计数是否在上界内（task-52；false ⇒ 可能把真失败当不可达洗白，verify-run3 判 problem）"),
    # task-63/task-66：被游戏拒绝（till 的 tool_ineffective/precondition_failed）的三级留痕 + 日级豁免
    ("event:refused_summary", "refused_summary",
     "日级拒绝汇总（task-63：count/bound/attempted/exempted/raw_unmet/unmet；tiles 可查）"),
    ("day_end.refused", "refused",
     "当天被游戏拒绝的格数（task-63；与 refused_bound/refused_exempt 互检）"),
    ("day_end.refused_tiles", "refused_tiles",
     "当天被拒绝的格坐标 [[x,y],…]（task-63；越界时人工核对用）"),
    ("day_end.refused_bound", "refused_bound",
     "拒绝豁免上界 max(5, 20%×attempted)（task-63）"),
    ("day_end.refused_exempt", "refused_exempt",
     "真正从 no_unmet_stages 里扣掉的拒绝格数（task-63；与 unreachable_exempt 各自扣减）"),
    ("day_end.checks.refused_within_bound", "refused_within_bound",
     "拒绝计数是否在上界内（task-63；false ⇒ 可能把真失败当'游戏拒绝'洗白，verify-run3 判 problem；"
     "缺失 ≠ 通过）"),
    # task-67/task-70：种子经济（run6 死锁链的第一环）；行内含 code/money/seed_price/keep_factor/offers
    ("event:no_seed_for_sale", "no_seed_for_sale",
     "今天货架上一条种子都没有（task-67；看 code/money/seed_price/offers —— run6 就是这一环）"),
    ("event:cannot_afford", "cannot_afford",
     "有种子但按 keep_factor 买不起（task-67；看 money/seed_price/offers）"),
    ("event:seed_unavailable_today", "seed_unavailable_today",
     "今天已确认买不到 ⇒ 不再把「该去买种子」当活（task-67；防 run6 那种 stuck 死锁的解药留痕）"),
    # task-68/task-76：可达性/开路（无硬闸门 ⇒ 缺失只记【无法判定】、绝不判红也不当通过）
    ("event:encircled_summary", "encircled_summary",
     "日级'被围住'汇总（task-68：count/attempted/engaged；不进不可达豁免、不封格）"),
    ("day_end.encircled", "encircled",
     "当天被不可清障物围住的格数（task-68；与 unreachable 分开计数）"),
    ("day_end.encircled_tiles", "encircled_tiles",
     "当天被围住的格坐标 [[x,y],…]（task-68；开路/次日重试用）"),
    ("event:frontier_clear", "frontier_clear",
     "开路尝试（task-68：tile/acted/attempt/limit/why；**acted=false = 想清但没清掉**）"),
    ("event:clear_neighbor", "clear_neighbor",
     "为开路清掉的邻格汇总（task-68：opens/targets；逐格在 StepResult.after）"),
    # task-73（dev 在制 working tree）：stuck 日**有界翻篇**——绕过 sleep_guard 睡过去让整轮继续，
    # 而不是 19 秒终止。**绝不放宽验收**（本日仍 ended_by=stuck / day_justified=False / 不 VERIFIED）
    # ⇒ 只作信息项：翻篇成功、被跳过（eventUp/存档模态/次数上限）、翻篇后重观测失败。
    ("event:stuck_flush", "stuck_flush",
     "stuck 日有界翻篇（task-73：ok/count/limit/day_after/detail；不判红、不洗白 stuck）"),
    ("event:stuck_flush_skipped", "stuck_flush_skipped",
     "翻篇被跳过（task-73：reason=eventUp / 存档类模态 / 次数达 limit）"),
    ("event:stuck_flush_resnap_failed", "stuck_flush_resnap_failed",
     "翻篇后重观测失败（task-73：error；只作诊断）"),
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
    # task-32：作业区软上限触顶 / 收尾作业区（都是信息项，只数形态与次数）
    "plots_capped": "plots_capped",
    "work_spot": "work_spots",
    # --- Lead m02395 机械核对：brain 里 `_journal("<name>"` 发出的**每个**事件名都要有桶，
    #     否则 run6 复盘会把新证据当"未映射"漏掉。下列 = task-15/41/42/49/50 等新事件。
    "event_blocked": "event_blocked",
    "farm_evidence_unavailable": "farm_evidence_unavailable",
    "sell": "sells",
    "sell_failed": "sell_failures",
    "goto_farm": "goto_farm",
    "plot_walk": "plot_walks",
    "resume_walk": "resume_walks",
    "water_far": "water_fars",
    "water_far_unavailable": "water_far_unavailable",
    "seed_gate": "seed_gates",
    "stage_midway_leftover": "stage_midway_leftover",
    "buy": "buys",
    "env_retry": "env_retries",
    "intent_unknown": "intent_unknowns",
    "zones_failed": "zones_failed",
    "day_key_resnap_failed": "day_key_resnap_failed",
    "load_save": "load_saves",
    "llm_on": "llm_on",
    "day_cap": "day_caps",
    "budget_exhausted": "budget_exhausted",
    "bridge_unavailable": "bridge_unavailable",
    "watchdog_stop": "watchdog_stops",
    "mod_version_mismatch": "mod_version_mismatch",
    "llm_trace_failed": "llm_trace_failures",
    "no_day_progress": "no_day_progress",
    # --- task-52：不可达（四邻都站不过去 / A* 算不出路）三级留痕。政策：**不计当天硬失败**、
    #     当天记 blocked、**次日重试**，日级豁免有上界 max(5, 20%×attempted)
    #     （tools\verify-run3.py:254-258/415-448 同口径：越界才是 problem）。
    "unreachable": "unreachable",
    "unreachable_stage": "unreachable_stages",
    "unreachable_summary": "unreachable_summaries",
    # --- task-63/task-66：`till` 被**游戏拒绝**（tool_ineffective/precondition_failed）的三级留痕。
    #     政策：不算当天硬失败、当天封格、**次日重试**；日级豁免有上界 max(5, 20%×attempted)；
    #     与 task-52 的 unreachable 是**两套集合、两套界**，各自扣减、互不掩护
    #     （tools\verify-run3.py:518-521 同向：越界才是 problem）。
    "tool_refused": "tool_refused",
    "refused_stage": "refused_stages",
    "refused_summary": "refused_summaries",
    # --- task-64：`stage` 是**独立事件**形态的阶段记录（brain 现在把阶段写进 `day_end.stages`；
    #     但对照夹具/旧账本可能用独立事件）⇒ 收进桶，供真空日闸门统计 Σ stage.ok。
    "stage": "stage_events",
    # --- task-63（dev 在制）：枯死作物清理范围 + 农场级 deadCrops 证据；只计数，等 run6 形态再定分类
    "clear_dead_scope": "clear_dead_scopes",
    # --- task-67/task-70：**种子经济**三事件（run6 死锁链的第一环）。归同一类（种子/经济）但
    #     **分开计数**（不许互相掩护）：
    #     `no_seed_for_sale` = 货架一条种子都没有（run6 夏季只有当季种子、硬编码 472 不在架）；
    #     `cannot_afford` = 有种子但按 keep_factor（留够 K 包）买不起；
    #     `seed_unavailable_today` = "今天买不到"的**当天失效**留痕（sleep_guard 不再把「该去买」当活）
    #     ⇒ 它是 run6 死锁的**解药证据**：出现它却仍 stuck，就得去查别的守卫条件，别再怪种子。
    #     三者都**不是硬失败**（买不到是环境事实）；判据要看它和 buy/stuck 的组合。
    "no_seed_for_sale": "no_seed_for_sales",
    "cannot_afford": "cannot_affords",
    "seed_unavailable_today": "seed_unavailable_today",
    # --- task-68/task-76：**可达性/开路**新类（与 task-52 的 `unreachable` **分开计数**：
    #     不可达 = 物理上走不到；被围住 = 现在开不了路（四邻没有"可站+可清"的突破口）。
    #     这一整类**没有硬闸门**（不存在 `encircled_within_bound`）⇒ 一律不判红、不进任何豁免分子，
    #     只作信息项 + 让 run6 那种"19 秒零动作收工"下次一眼可见：
    #     `encircled`/`encircled_stage`/`encircled_summary` = 三级留痕（逐格/阶段/日级）；
    #     `frontier_clear` = "目标都够不着时至少清一格可达的可清障格"的尝试，`acted=false` = 想清没清掉；
    #     `clear_neighbor` = 为开路清掉的邻格（阶段级，逐格在 `StepResult.after["clear_neighbor"]`）。
    "encircled": "encircled",
    "encircled_stage": "encircled_stages",
    "encircled_summary": "encircled_summaries",
    "frontier_clear": "frontier_clears",
    "clear_neighbor": "clear_neighbors",
    # task-73（dev 在制 working tree）：stuck 日**有界翻篇** —— 本日仍如实 stuck / 不 VERIFIED，
    #     只是"睡过去让整轮继续"，所以本工具只作信息项（成功/跳过/重观测失败），一律不判红。
    "stuck_flush": "stuck_flushes",
    "stuck_flush_skipped": "stuck_flush_skips",
    "stuck_flush_resnap_failed": "stuck_flush_resnap_failures",
}

#: 结构性事件：由报告的其他字段单独统计（day_start/day_end 切会话与验收、finish 自述），
#: 不进桶、也不算"未映射"。
STRUCTURAL_EVENTS = ("day_start", "day_end", "finish")

#: 桶名 → 事件名 的反查表。`report["events"]` 数的是**事件名**，而 `NEW_EVENT_BUCKETS` 里写的是
#: **桶名**；对 `buy→buys`/`sell→sells`/`unreachable_stage→unreachable_stages` 这类非同名映射，
#: 直接拿桶名去查会恒为 0 ⇒ 新事件在头部"隐形"（run6 的 6 次 `buy` 就是这么消失的，task-70 修）。
BUCKET_TO_EVENT = {}
for _ev_name, _bucket_name in EVENT_BUCKETS.items():
    BUCKET_TO_EVENT.setdefault(_bucket_name, _ev_name)

#: run6 要看次数的新事件桶（task-15/41/42/49/50）：只在计数非 0 时打印，便于一眼点名。
NEW_EVENT_BUCKETS = (
    "event_blocked", "farm_evidence_unavailable", "sells", "sell_failures",
    "goto_farm", "plot_walks", "resume_walks", "water_fars", "water_far_unavailable",
    "seed_gates", "stage_midway_leftover",
    "buys", "env_retries", "intent_unknowns", "zones_failed", "day_key_resnap_failed",
    "load_saves", "llm_on", "day_caps", "budget_exhausted", "bridge_unavailable",
    "watchdog_stops", "mod_version_mismatch", "llm_trace_failures", "no_day_progress",
    # task-52：不可达三级留痕（一眼看出哪几格/哪个阶段/当天豁免多少）
    "unreachable", "unreachable_stages", "unreachable_summaries",
    # task-66：被游戏拒绝（till 的 tool_ineffective）三级留痕
    "tool_refused", "refused_stages", "refused_summaries",
    # task-70：种子经济（买不到 / 买不起 / 当天失效留痕）
    "no_seed_for_sales", "cannot_affords", "seed_unavailable_today",
    # task-76：可达性/开路（被围住三级留痕 + 开路尝试/结果 + 清邻格；无硬闸门、不判红）
    "encircled", "encircled_stages", "encircled_summaries",
    "frontier_clears", "clear_neighbors",
    # task-73（dev 在制）：stuck 日有界翻篇（不经 sleep_guard，但绝不放宽验收、不判红）
    "stuck_flushes", "stuck_flush_skips", "stuck_flush_resnap_failures",
)


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


#: task-65（Lead）：退出码口径 —— "有红"= 必须人工介入（`manual:*`）或"该做没做"（`missed:*`）
#: 或 `wasted:` 里显式判红的那几类（洗白/0 步 VERIFIED/浇水自相矛盾或不可采信/账目自述不一致）。
RED_SUBJECT_PREFIXES = ("manual:", "missed:")
RED_SUBJECTS = (
    "wasted:verified_zero_steps",
    "wasted:verified_without_work",
    "wasted:whitewash",
    "wasted:water_contradiction",
    "wasted:water_scope_empty",
    "wasted:finish_incoherent",
    "wasted:finish_vs_days",
)


def is_red_finding(item):
    """这条 finding 算不算"红"（退出码 1 的依据）。口径写进 `--help` 与口径卡 §1.5。"""
    subject = str((item or {}).get("subject") or "")
    if subject.startswith(RED_SUBJECT_PREFIXES):
        return True
    return any(subject == s or subject.startswith(s + ":") for s in RED_SUBJECTS)


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
#: 季节别名（与 `tools\verify-run3.py` 的 `_SEASON_INDEX` 逐字同口径：认英文与中文）
SEASON_ALIASES = {"spring": 0, "summer": 1, "fall": 2, "winter": 3,
                  "春": 0, "夏": 1, "秋": 2, "冬": 3}


def day_index(day):
    """把 `[year, season, day]` 折成绝对日序（每季 28 天）；认不出返回 None。

    只用来做"跨日必须恰好 +1 天"这条校验。task-38：口径逐字对齐
    `tools\\verify-run3.py:_day_ordinal` —— 季节认 spring/summer/fall/winter 与春秋夏冬
    （大小写/空白不敏感，也接受 0-3 的整数），日必须是 1..28。
    认不出返回 None ⇒ 调用方只能记【无法判定】，**绝不许**把"认不出"当成"没跨日"。
    """
    seq = as_list(day)
    if len(seq) != 3:
        return None
    season = seq[1]
    if isinstance(season, str):
        idx = SEASON_ALIASES.get(season.strip().lower())
    elif isinstance(season, int) and not isinstance(season, bool):
        idx = season
    else:
        idx = None
    try:
        year = int(seq[0])
        dom = int(seq[2])
    except (TypeError, ValueError):
        return None
    if idx is None or not (0 <= idx <= 3) or not (1 <= dom <= 28):
        return None
    return ((year - 1) * 4 + idx) * 28 + (dom - 1)


#: 跨日判定的三种结论 + "不适用"（只看我们主动睡过去的日子）
CROSS_DAY_CROSSED = "crossed"
CROSS_DAY_WRONG = "wrong"
CROSS_DAY_UNDECIDABLE = "undecidable"
CROSS_DAY_NA = "n/a"


def cross_day_evidence(start_day, end):
    """task-38：判断这一天有没有"跨日恰好 +1 天"的证据。

    返回 `(verdict, source, end_day)`；`verdict ∈ {crossed, wrong, undecidable, n/a}`。

    口径（与 `tools\\verify-run3.py:216-227`/`:391-404` 对齐 + 一条按 Lead m01723 的裁定）：
      * `day_end.ended_by != "sleep"` ⇒ `n/a`（这条校验只管我们主动睡过去的日子）；
      * 有 `day_after`（睡后**重取**的观测）⇒ 它就是权威证据：正好 +1 天 = `crossed`，
        否则 = `wrong`；认不出 `[年,季,日]` = `undecidable`；
      * 没有 `day_after`（task-38 之前的旧账本）⇒ **只在 `final` 明确指向另一天时**才退回旧口径
        （+1 = `crossed`，否则 `wrong`）；`final` 还停在 `day_start` 那一天、或缺失 ⇒ `undecidable`。
        理由：`final` 是**睡前**快照，拿它判"没跨日"就是 task-38 要修的那个假报警
        （真机 0.7.23 彩排：回执写"已跨日 spring 17→18"、`final` 还是 17 日）⇒ **缺失 ≠ 没做**。

    与 `tools\\verify-run3.py` 的分工（Lead m01934 裁定：保持不同向）：它把缺失记 problem
    （验收入口，必须贯彻"缺失 ≠ 通过"），这里记 `undecidable`（行为分析口径）。两者都**不把缺失
    当通过**，只是严重度标签不同；run3 的真账本一定有 `day_after`，这个分歧只出现在旧/合成账本上。
    """
    if not isinstance(end, dict) or end.get("ended_by") != "sleep":
        return CROSS_DAY_NA, None, None
    after = as_list(end.get("day_after"))
    if after:
        i0, i1 = day_index(start_day), day_index(after)
        if i0 is None or i1 is None:
            return CROSS_DAY_UNDECIDABLE, "day_after", after
        return (CROSS_DAY_CROSSED if i1 == i0 + 1 else CROSS_DAY_WRONG), "day_after", after
    fin_day = as_dict(end.get("final")).get("day")
    i0, i1 = day_index(start_day), day_index(fin_day)
    if i0 is None or i1 is None or i1 == i0:
        return CROSS_DAY_UNDECIDABLE, "final", fin_day
    return (CROSS_DAY_CROSSED if i1 == i0 + 1 else CROSS_DAY_WRONG), "final", fin_day


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
def no_work_with_dry(ev):
    """task-60：`ended_reason` 以 `no_work` 开头、却自述户外还有干作物（`final_water.dry > 0`）。

    这是 run3 "连睡病"的形态：`no_work`（今天没活）与 `dry>0`（还有没浇的地）不可能同时为真。
    `tools\\verify-run3.py` 对该形态直接判 problem（"户外还有干作物却判今天没活"），本工具同向判红，
    并据此让 `checks.day_justified` 在这一形态下**不成立**（`day_justified_effective`，不是只改文案）。

    返回命中的 `dry` 整数（>0 才算命中）；`final_water` 缺失或 `dry` 非数值 ⇒ `None`
    （缺失 ≠ 通过：那是 `missed:check:watered_outdoor` 与【无法判定】的职责，不许在这里凭空判红）。
    """
    if not str(ev.get("ended_reason") or "").startswith("no_work"):
        return None
    fw = ev.get("final_water")
    if not isinstance(fw, dict):
        return None
    dry = fw.get("dry")
    if isinstance(dry, bool) or not isinstance(dry, (int, float)):
        return None
    return int(dry) if dry > 0 else None


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
            # task-62：**不**把 `unreachable` 计入差额解释 —— tools\verify-run3.py:388-404 只认
            # env_block + inconclusive（账目差额口径以它为准；不可达格本来就不该出现在
            # `stages[].failed` 里：它们被 exempt 后已从 leftover 移除）。
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
                        hint="差额必须被环境挡路/无结论计数完全解释（verify-run3.py:388-404 同口径，"
                             "别把环境挡路和走不到当硬失败；`unreachable` 不在这个差额口径里）",
                        subject="missed:stage_account",
                    )
                )
        # 1f: 主动睡过去了却没跨到"次日"（verify-run3.py：ended_by=sleep 必须有跨日证据）
        #     task-38：判据统一交给 `cross_day_evidence()` —— 优先 `day_after`（睡后重取的观测），
        #     只有 `final` 明确指向另一天时才退回旧口径；`final` 还停在当天 ⇒ 【无法判定】，不报红。
        if end:
            verdict, src, end_day = cross_day_evidence(as_dict(sess["start"]).get("day"), end)
            if verdict == CROSS_DAY_WRONG:
                out.append(
                    finding(
                        end_line, "day_end",
                        f"缺跨日证据：ended_by=sleep，但 {src} 日期 {end_day!r} 不是 "
                        f"day_start {as_dict(sess['start']).get('day')!r} 的次日",
                        hint="跨日必须恰好 +1 天（verify-run3.py:391-404 同口径）；+2 天或倒退都说明"
                             "账本/世界不对。task-38 之后的日子以 `day_after` 为权威证据",
                        subject="missed:cross_day",
                    )
                )
        # 1g: task-60 —— "今天没活"（ended_reason 以 no_work 开头）与"户外还有干作物"
        #     （final_water.dry>0）不可能同时为真；verify-run3.py 对该形态直接判 problem
        #     （run3 连睡病复发）。同向口径：这里判红，且 checks.day_justified 不算正当理由。
        for lineno, ev in sess["day_ends"]:
            dry = no_work_with_dry(ev)
            if dry is None:
                continue
            out.append(
                finding(
                    lineno, "day_end",
                    f"没活却还有干地：ended_reason={str(ev.get('ended_reason') or '')[:60]!r} "
                    f"但 final_water.dry={dry}（户外还有没浇的作物）⇒ checks.day_justified "
                    f"在此形态下不成立（ended_by={ev.get('ended_by')}）",
                    hint="run3 连睡病形态：查 _farm_scope_work / work_reasons 的 fail-closed 路径"
                         "（task-41 第 10 条）；verify-run3.py 同判 problem",
                    subject="missed:no_work_with_dry",
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
        # 2g: 真空日闸门（Lead m02981 裁定；与 verify-run3.py:604-625 逐字同口径，不许更宽）——
        #     `verified=true` 且有阶段记录但 Σ stage.ok == 0 ⇒ 判红（0 步不能自证做过事）；
        #     `0 < Σ ok < 5` ⇒ 只记"弱日"信息项（合法但偏弱的一天，供复核时人读）；
        #     完全没有阶段记录的情形由上面 2d 覆盖；字段缺失由 build_undecidable 记【无法判定】。
        for lineno, ev in sess["day_ends"]:
            if not ev.get("verified"):
                continue
            stage_recs = as_list(ev.get("stages")) or [e2 for _, e2 in sess.get("stage_events") or []]
            if not stage_recs:
                continue
            ok_sum = 0
            for st in stage_recs:
                ok_sum += as_int(st.get("ok"))
            if ok_sum <= 0:
                out.append(
                    finding(
                        lineno, "day_end",
                        f"自称 VERIFIED 但当天成功动作 0 步（有阶段记录 {len(stage_recs)} 个、Σ stage.ok=0）"
                        "（0 步不能自证做过事；查 stage_no_target / `no_work` 分支）",
                        hint="真空日闸门：与 verify-run3.py:604-625 同口径；有阶段记录时不吃"
                             "no_intents/no_work 之类的豁免（豁免只覆盖'当天 0 阶段'那条）",
                        subject="wasted:verified_zero_steps",
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
                        hint="sleep_at 默认 2200；若提前收工要给出理由（night/stamina/no_work）——"
                             "`no_plot`（作业区配额到顶）**不算**正当理由（task-32）",
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
            # task-52：不可达豁免越界 = 洗白风险（把真失败/不可动格混进 unreachable）
            if checks.get("unreachable_within_bound") is False:
                out.append(
                    finding(
                        lineno, "day_end",
                        f"必须人工介入：checks.unreachable_within_bound=false"
                        f"（unreachable={ev.get('unreachable')}、bound={ev.get('unreachable_bound')}、"
                        f"exempt={ev.get('unreachable_exempt')}）—— "
                        f"{CHECK_MEANING.get('unreachable_within_bound')}",
                        hint="与 verify-run3.py:445-448 同向：豁免越界 ⇒ 可能把真失败当不可达；"
                             "人工核对 unreachable_tiles 的坐标",
                        subject="manual:check:unreachable_within_bound",
                    )
                )
            # task-63/task-66：拒绝豁免越界 = 洗白风险（把真失败混进"游戏拒绝"）
            if checks.get("refused_within_bound") is False:
                out.append(
                    finding(
                        lineno, "day_end",
                        f"必须人工介入：checks.refused_within_bound=false"
                        f"（refused={ev.get('refused')}、bound={ev.get('refused_bound')}、"
                        f"exempt={ev.get('refused_exempt')}）—— "
                        f"{CHECK_MEANING.get('refused_within_bound')}",
                        hint="与 verify-run3.py:518-521 同向：豁免越界 ⇒ 可能把真失败当'游戏拒绝'；"
                             "人工核对 refused_tiles 的坐标（与 unreachable 两套独立豁免）",
                        subject="manual:check:refused_within_bound",
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
        # task-52：不可达（四邻都站不过去 / A* 算不出路）＝ 环境挡路的第三种形态。
        # 政策：**不计当天硬失败**、当天记 blocked、**次日重试**；日级豁免有上界 max(5, 20%×attempted)。
        # 本工具只把它数成信息项（不并进"该做没做"）：是否真做成由 checks.no_unmet_stages
        # **先扣 unreachable_exempt** 后说话（tools\verify-run3.py:254-258/415-448 同口径；越界才是 problem）。
        unreach_events = sess["unreachable"]
        if unreach_events or sess["unreachable_stages"] or sess["unreachable_summaries"]:
            tile_set = set()
            for _, ev in unreach_events:
                tile = as_list(ev.get("tile"))
                if len(tile) == 2:
                    tile_set.add((as_int(tile[0]), as_int(tile[1])))
            tiles = sorted(tile_set)
            stages = sorted({str(ev.get("stage") or "?") for _, ev in unreach_events})
            summary = sess["unreachable_summaries"][-1][1] if sess["unreachable_summaries"] else {}
            first = (unreach_events or sess["unreachable_stages"] or sess["unreachable_summaries"])[0][0]
            out.append(
                finding(
                    first, "unreachable",
                    f"不可达（不计当天硬失败）：{len(unreach_events)} 次 / {len(tiles)} 格"
                    f"（阶段 {stages or '-'}；坐标 {[list(t) for t in tiles[:6]]}"
                    f"{'…' if len(tiles) > 6 else ''}）；日级 count={summary.get('count')}、"
                    f"bound={summary.get('bound')}、attempted={summary.get('attempted')}、"
                    f"raw_unmet={summary.get('raw_unmet')}、exempted={summary.get('exempted')}、"
                    f"unmet={summary.get('unmet')}",
                    hint="task-52：当天记 blocked、次日重试；豁免上界 max(5, 20%×attempted)，"
                         "越界由 checks.unreachable_within_bound=false 判红（本工具 0 类）",
                    subject="environment:unreachable",
                )
            )
        for lineno, ev in sess["unreachable_stages"]:
            out.append(
                finding(
                    lineno, "unreachable_stage",
                    f"阶段级不可达：{ev.get('stage')} @ zone={ev.get('zone')} 有 "
                    f"{as_int(ev.get('tiles'))} 格走不到（其中还留在 leftover 的 "
                    f"{as_int(ev.get('in_leftover'))} 格；坐标 {as_list(ev.get('coords'))[:6]}）",
                    hint="in_leftover>0 的格就是日级 exemption 要扣的对象；扣完仍不成立由 "
                         "checks.no_unmet_stages 说话",
                    subject="environment:unreachable_stage",
                )
            )
        # task-63/task-66：被**游戏拒绝**（till 的 tool_ineffective / precondition_failed）＝ 环境挡路的
        # 第四种形态：不是"格子走不到"（不可达），而是世界的前置事实（不可锄的地 / 工具等级不够）拒绝执行。
        # 政策与 task-52 同形但**独立起界**（refused_bound = max(5, 20%×attempted)）：两套豁免各自扣减、
        # 互不掩护；本工具只作信息项（不并进"该做没做"），是否真做成由 checks.no_unmet_stages
        # **先扣 refused_exempt** 后说话（tools\verify-run3.py:518-521：越界才是 problem）。
        refused_events = sess["tool_refused"]
        if refused_events or sess["refused_stages"] or sess["refused_summaries"]:
            r_tile_set = set()
            for _, ev in refused_events:
                tile = as_list(ev.get("tile"))
                if len(tile) == 2:
                    r_tile_set.add((as_int(tile[0]), as_int(tile[1])))
            rtiles = sorted(r_tile_set)
            rstages = sorted({str(ev.get("stage") or "?") for _, ev in refused_events})
            rstatus = sorted({str(ev.get("status") or "?") for _, ev in refused_events})
            rsummary = sess["refused_summaries"][-1][1] if sess["refused_summaries"] else {}
            rfirst = (refused_events or sess["refused_stages"] or sess["refused_summaries"])[0][0]
            out.append(
                finding(
                    rfirst, "tool_refused",
                    f"被游戏拒绝（不计当天硬失败）：{len(refused_events)} 次 / {len(rtiles)} 格"
                    f"（阶段 {rstages or '-'}；status {rstatus or '-'}；"
                    f"坐标 {[list(t) for t in rtiles[:6]]}{'…' if len(rtiles) > 6 else ''}）；"
                    f"日级 count={rsummary.get('count')}、bound={rsummary.get('bound')}、"
                    f"attempted={rsummary.get('attempted')}、raw_unmet={rsummary.get('raw_unmet')}、"
                    f"exempted={rsummary.get('exempted')}、unmet={rsummary.get('unmet')}",
                    hint="task-63：世界拒绝（tool_ineffective/precondition_failed）不是'我试了没做成'；"
                         "当天封格、次日重试；与 unreachable 是两套独立豁免、互不掩护，"
                         "越界由 checks.refused_within_bound=false 判红（本工具 0 类）",
                    subject="environment:refused",
                )
            )
        for lineno, ev in sess["refused_stages"]:
            out.append(
                finding(
                    lineno, "refused_stage",
                    f"阶段级拒绝：{ev.get('stage')} @ zone={ev.get('zone')} 有 "
                    f"{as_int(ev.get('tiles'))} 格被游戏拒绝（其中还留在 leftover 的 "
                    f"{as_int(ev.get('in_leftover'))} 格；坐标 {as_list(ev.get('coords'))[:6]}）",
                    hint="in_leftover>0 的格就是日级 refused_exempt 要扣的对象；扣完仍不成立由 "
                         "checks.no_unmet_stages 说话",
                    subject="environment:refused_stage",
                )
            )
        # task-68/task-76：**可达性/开路** ＝ 环境挡路的第五种形态，与 task-52 的 `unreachable` **分开**：
        # 不可达 = 物理上走不到（A* 算不出路 / 没有落脚点）；被围住 = 四邻没有"可站+可清"的突破口
        # （树/桩/大石）。这一整类**没有硬闸门**（不存在 `encircled_within_bound`）⇒ 只作信息项、
        # 不判红、不进任何豁免分子；三条价值：①谁被围住（三级留痕）②`frontier_clear` 的 acted 计数
        # （run6 那种"19 秒零动作收工"下次一眼可见）③`clear_neighbor` 开路证据。
        enc_events = sess["encircled"]
        if enc_events or sess["encircled_stages"] or sess["encircled_summaries"]:
            e_tile_set = set()
            for _, ev in enc_events:
                tile = as_list(ev.get("tile"))
                if len(tile) == 2:
                    e_tile_set.add((as_int(tile[0]), as_int(tile[1])))
            etiles = sorted(e_tile_set)
            estages = sorted({str(ev.get("stage") or "?") for _, ev in enc_events})
            esummary = sess["encircled_summaries"][-1][1] if sess["encircled_summaries"] else {}
            efirst = (enc_events or sess["encircled_stages"] or sess["encircled_summaries"])[0][0]
            out.append(
                finding(
                    efirst, "encircled",
                    f"被围住（可达性/开路；不计硬失败、不封格、不进不可达豁免）：{len(enc_events)} 次 / "
                    f"{len(etiles)} 格（阶段 {estages or '-'}；坐标 {[list(t) for t in etiles[:6]]}"
                    f"{'…' if len(etiles) > 6 else ''}）；日级 count={esummary.get('count')}、"
                    f"attempted={esummary.get('attempted')}、engaged={esummary.get('engaged')}",
                    hint="task-68：四邻没有「可站+可清」的突破口（树/桩/大石一类）⇒ 与 unreachable "
                         "分开计数；开路后/次日地形变了就可能可达（本类无硬闸门、不判红）",
                    subject="environment:encircled",
                )
            )
        for lineno, ev in sess["encircled_stages"]:
            out.append(
                finding(
                    lineno, "encircled_stage",
                    f"阶段级被围住：{ev.get('stage')} @ zone={ev.get('zone')} 有 "
                    f"{as_int(ev.get('tiles'))} 格（其中还留在 leftover 的 "
                    f"{as_int(ev.get('in_leftover'))} 格；坐标 {as_list(ev.get('coords'))[:6]}）",
                    hint="encircled_leftover 不参与任何豁免扣减（不进 unreachable_exempt 分子）",
                    subject="environment:encircled_stage",
                )
            )
        fz = sess["frontier_clears"]
        if fz:
            acted = [ln for ln, ev in fz if bool(ev.get("acted"))]
            failed = [ln for ln, ev in fz if not bool(ev.get("acted"))]
            flines = sorted({ln for ln, _ in fz})
            out.append(
                finding(
                    flines[0], "frontier_clear",
                    f"开路尝试 {len(fz)} 次（真清掉 {len(acted)} 次、没清掉 {len(failed)} 次；行 {flines}）"
                    + ("  ⚠ 全部 acted=false ⇒ 想清但没清掉（run6 那种零动作收工的形态）"
                       if failed and not acted else ""),
                    hint="task-68：所有指定目标都够不着时，至少要真清掉一格自己够得着的可清障格；"
                         "acted=false 的次数就是「这一轮没动作」的证据（本类不判红）",
                    subject="environment:frontier_clear",
                )
            )
        nb = sess["clear_neighbors"]
        if nb:
            opens = sum(as_int(ev.get("opens")) for _, ev in nb)
            nstages = sorted({str(ev.get("stage") or "?") for _, ev in nb})
            out.append(
                finding(
                    nb[0][0], "clear_neighbor",
                    f"为开路清掉邻格：{len(nb)} 个阶段共 opens={opens}（阶段 {nstages}）",
                    hint="task-68：开路成功证据；逐格在 StepResult.after['clear_neighbor']",
                    subject="environment:clear_neighbor",
                )
            )
        # task-73：stuck 日**有界翻篇**（绕过 sleep_guard 睡过去让整轮继续）。本日仍如实
        # `ended_by=stuck`、`day_justified=False`、不 VERIFIED ⇒ 只作信息项，绝不判红；
        # 价值：run6 那种"19 秒零动作终止"现在能一眼看到"翻篇成功 / 为什么跳过".
        sf = sess["stuck_flushes"]
        sfs = sess["stuck_flush_skips"]
        sfr = sess["stuck_flush_resnap_failures"]
        if sf or sfs or sfr:
            sf_ok = [ln for ln, ev in sf if ev.get("ok") is True]
            sf_no = [ln for ln, ev in sf if ev.get("ok") is not True]
            skip_reasons = sorted({str(ev.get("reason") or "?") for _, ev in sfs})
            sflines = sorted({ln for ln, _ in sf} | {ln for ln, _ in sfs})
            out.append(
                finding(
                    (sflines or [None])[0], "stuck_flush",
                    f"stuck 日有界翻篇：{len(sf)} 次（睡成功 {len(sf_ok)} / 没成功 {len(sf_no)}）"
                    f"；被跳过 {len(sfs)} 次"
                    + (f"（原因 {'、'.join(skip_reasons[:3])}）" if skip_reasons else "")
                    + (f"；翻篇后重观测失败 {len(sfr)} 次（L{sfr[0][0]}）" if sfr else "")
                    + ("  ⚠ 有跳过 ⇒ 那天没能睡过去（外层照旧 no_day_progress 终止）" if sfs else ""),
                    hint="task-73：绕过 sleep_guard 的有界翻篇；本日仍如实 stuck、DayReport 不 "
                         "VERIFIED ⇒ 不判红（验收口径看 ended_by/checks，不看翻篇）",
                    subject="environment:stuck_flush",
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
    # 0a) 未映射事件（Lead m02395）：本工具没桶 ⇒ 报告可能漏掉 run6 的新证据，必须先补映射
    un = report.get("unmapped_events") or {}
    if un:
        advice.append({
            "text": f"有 {len(un)} 种事件本工具没有桶（"
                    + "、".join(f"{name}×{info['count']}" for name, info in sorted(un.items()))
                    + "）：先补 `EVENT_BUCKETS`（tools\\analyze-longrun.py）再看报告，别让新证据静默消失",
            "lines": [ln for info in un.values() for ln in info["lines"]],
        })
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
    # 0b-2) 没活却还有干地（红；task-60 与 verify-run3.py 同向）
    no_work_dry = [
        (ln, ev) for sess in sessions for ln, ev in sess["day_ends"]
        if no_work_with_dry(ev) is not None
    ]
    if no_work_dry:
        advice.append({
            "text": f"没活却还有干地 ×{len(no_work_dry)}（红）：`no_work` 收工但 final_water.dry>0 ⇒ "
                    "`day_justified` 不算正当理由；先查 _farm_scope_work / work_reasons 的 "
                    "fail-closed 路径（verify-run3.py 同判 problem）",
            "lines": [ln for ln, _ in no_work_dry if ln is not None],
        })
    # 0g) 购买没成交（task-69：run6 守卫死锁的指纹之一；桶 `buys` 存在 ≠ 买成了）
    buy = report.get("buy") or {}
    if buy.get("failed"):
        codes = "、".join(f"{k}×{v}" for k, v in sorted((buy.get("codes") or {}).items())) or "无 code"
        advice.append({
            "text": f"购买没成交 ×{buy['failed']}（{codes}；共 {buy['total']} 次）"
                    + ("：同一回执反复出现 ⇒ 守卫要的条件现实不可满足（守卫死锁嫌疑：先查 task-67 的"
                       "「按在售清单买」与 sleep_guard 的「没种子但钱够 ⇒ 该去买」是否互为闭环）"
                       if buy.get("same_receipt") else "：先看钱/背包/货架是否真的满足"),
            "lines": buy.get("failed_lines") or [],
        })
    # 0h) 同一天重复起跑（task-69：run6 是 stuck 后同日重试；不许读成跨日/多天）
    sdr = report.get("same_day_retries") or {}
    if sdr:
        advice.append({
            "text": f"同一天重复起跑 ×{sdr['sessions']}（去重后只有 {sdr['distinct_days']} 个日历日："
                    f"{'、'.join(sdr['labels'])}）：账本会有多份 day_end，别读成跨日/多天；"
                    "先看上一轮为什么卡住（stuck / 守卫死锁）",
            "lines": sdr.get("retry_lines") or [],
        })
    # 0i) 种子经济（task-70：task-67 的种子三事件；run6 死锁链的第一环）
    se = report.get("seed_economy") or {}
    if se.get("total"):
        advice.append({
            "text": f"种子经济 ×{se['total']}（没货 {se['no_seed_for_sale']} / "
                    f"买不起 {se['cannot_afford']} / 当天失效留痕 {se['seed_unavailable_today']}）"
                    + (f"；货架：{str(se.get('offers') or '')[:160]}" if se.get("offers") else "")
                    + ("：买不到是**当天确认的环境事实**（不是硬失败），但必须有 "
                       "`seed_unavailable_today` 让「该去买种子」这条守卫理由当天失效，"
                       "否则守卫永远拒绝收工 ⇒ 3 轮零变化 ⇒ stuck（run6 的形态）；"
                       "留痕为 0 就先查 `_seed_dead` / `seed_unavail_noted` 的退路"
                       if se.get("deadlock_risk") else
                       "：种子经济已按当天失效处理（防死锁路径走到了），"
                       "此时再 stuck 就要查别的守卫条件（别继续怪种子）"),
            "lines": (se["lines"].get("no_seed_for_sale", [])
                      + se["lines"].get("cannot_afford", [])
                      + se["lines"].get("seed_unavailable_today", [])),
        })
    # 0j) 可达性/开路（task-76：task-68 的被围住 + frontier_clear + clear_neighbor；**不判红**）
    rc = report.get("reachability") or {}
    if (rc.get("encircled_events") or rc.get("frontier_clear_attempts")
            or rc.get("clear_neighbor_events") or rc.get("zero_action_days")):
        parts = []
        if rc.get("encircled_events"):
            parts.append(f"被围住 {rc['encircled_events']} 次 / {rc.get('encircled_tile_count', 0)} 格"
                         f"（不进不可达豁免；开路后/次日可能可达）")
        if rc.get("frontier_clear_attempts"):
            parts.append(f"开路尝试 {rc['frontier_clear_attempts']} 次（真清掉 "
                         f"{rc.get('frontier_clear_acted', 0)}、没清掉 {rc.get('frontier_clear_failed', 0)}）")
        if rc.get("clear_neighbor_events"):
            parts.append(f"为开路清掉邻格 opens={rc.get('clear_neighbor_opens', 0)}"
                         f"（{rc['clear_neighbor_events']} 个阶段）")
        if rc.get("zero_action_days"):
            parts.append("零动作收工 " + "、".join(
                f"{z.get('day')}(L{z.get('line')})" for z in rc["zero_action_days"]))
        advice.append({
            "text": "可达性/开路（信息项，**不判红**）：" + "；".join(parts)
                    + ("。⚠ 开路全部 acted=false（想清但没清掉）⇒ 至少有一轮零动作，"
                       "run6 那种「19 秒零动作收工」会在这里现形"
                       if rc.get("frontier_clear_failed") and not rc.get("frontier_clear_acted") else ""),
            "lines": sorted(set((rc.get("encircled_lines") or []) + (rc.get("frontier_clear_lines") or [])
                                + (rc.get("clear_neighbor_lines") or [])
                                + [z.get("line") for z in (rc.get("zero_action_days") or [])
                                   if z.get("line") is not None])),
        })
    # 0k) stuck 日有界翻篇（task-73；信息项，本日仍如实 stuck / 不 VERIFIED ⇒ 不判红）
    sf = report.get("stuck_flush") or {}
    if sf.get("events") or sf.get("skipped") or sf.get("resnap_failed"):
        advice.append({
            "text": f"stuck 日有界翻篇（信息项，**不判红**）：{sf.get('events', 0)} 次"
                    f"（睡成功 {sf.get('ok', 0)} / 没成功 {sf.get('not_ok', 0)}）"
                    f"；被跳过 {sf.get('skipped', 0)} 次"
                    + (f"（原因 {'、'.join((sf.get('skip_reasons') or [])[:3])}）"
                       if sf.get("skip_reasons") else "")
                    + (f"；翻篇后重观测失败 {sf.get('resnap_failed', 0)} 次"
                       if sf.get("resnap_failed") else "")
                    + "。task-73 刻意绕过 sleep_guard 让整轮继续跑下一天，但**绝不放宽验收**："
                      "那天依然如实记 stuck、day_justified=False、不 VERIFIED（验收看 ended_by/checks）"
                    + ("；⚠ 有跳过 ⇒ 那天没能睡过去，外层照旧 no_day_progress 终止"
                       if sf.get("skipped") else ""),
            "lines": sf.get("lines") or [],
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
    # 0e) 不可达（task-52：四邻都站不过去 / A* 算不出路）——不计当天硬失败、次日重试，但豁免有上界
    if env.get("unreachable_events") or env.get("unreachable_summary_events"):
        _u_tiles = env.get("unreachable_tiles") or []
        _u_marks = (f"count={env.get('unreachable_count')}、bound={env.get('unreachable_bound')}、"
                    f"attempted={env.get('unreachable_attempted')}、exempt={env.get('unreachable_exempt')}")
        advice.append({
            "text": f"不可达（四邻都站不过去 / A* 算不出路）×{env['unreachable_events']} 次 / "
                    f"{env.get('unreachable_tile_count', 0)} 格（{_u_tiles[:top] or '-'}）：task-52 政策是"
                    f"不计当天硬失败、当天记 blocked、次日重试；日级豁免 {_u_marks}；"
                    + ("⚠ checks.unreachable_within_bound=false ⇒ 0 类红：豁免越界（可能把真失败当"
                       "不可达洗白），必须人工核对这些坐标"
                       if env.get("unreachable_within_bound") is False
                       else "上界内属正常（与 verify-run3.py:415-448 同向）"),
            "lines": env.get("unreachable_lines") or [],
        })
    # 0f) 被游戏拒绝（task-63/task-66：till 的 tool_ineffective / precondition_failed）——世界的前置事实
    # 拒绝执行，不算当天硬失败、当天封格、次日重试；与 unreachable 两套独立豁免，越界进 0 类红。
    if env.get("refused_events") or env.get("refused_summary_events"):
        _r_tiles = env.get("refused_tiles") or []
        _r_marks = (f"count={env.get('refused_count')}、bound={env.get('refused_bound')}、"
                    f"attempted={env.get('refused_attempted')}、exempt={env.get('refused_exempt')}")
        advice.append({
            "text": f"被游戏拒绝（tool_ineffective/precondition_failed）×{env['refused_events']} 次 / "
                    f"{env.get('refused_tile_count', 0)} 格（{_r_tiles[:top] or '-'}）：task-63 政策是"
                    f"不计当天硬失败、当天封格、次日重试；日级豁免 {_r_marks}"
                    f"（与 unreachable 独立起界、不许互相掩护）；"
                    + ("⚠ checks.refused_within_bound=false ⇒ 0 类红：豁免越界（可能把真失败当"
                       "「游戏拒绝」洗白），必须人工核对这些坐标"
                       if env.get("refused_within_bound") is False
                       else "上界内属正常（与 verify-run3.py:518-521 同向）"),
            "lines": env.get("refused_lines") or [],
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
    # 2g-advice) 真空日（task-64）：0 步却自称 VERIFIED —— 计数走全量 day_end（同 3c 的理由）
    zero_step_lines = []
    for sess in sessions:
        for ln, ev in sess["day_ends"]:
            if not ev.get("verified"):
                continue
            recs = as_list(ev.get("stages")) or [e2 for _, e2 in sess.get("stage_events") or []]
            if not recs:
                continue
            if sum(as_int(st.get("ok")) for st in recs) <= 0:
                zero_step_lines.append(ln)
    if zero_step_lines:
        advice.append({
            "text": f"自称 VERIFIED 但当天成功动作 0 步（有阶段记录）×{len(zero_step_lines)}（红）："
                    "0 步不能自证做过事 ⇒ 与 verify-run3.py:604-625 的真空日闸门同判 problem；"
                    "先查 stage_no_target / no_work 分支（有阶段记录时不吃'无活可做'豁免）",
            "lines": zero_step_lines,
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
    #     计数走全量 day_end：报告里的 categories 会被 --top 截断，不能当计数源（会少报）
    water_bad_lines = []
    for sess in sessions:
        for ln, ev in sess["day_ends"]:
            checks = as_dict(ev.get("checks"))
            flag = checks.get("watered_outdoor")
            fw = as_dict(ev.get("final_water"))
            dry = fw.get("dry")
            if flag is None or flag is False:
                water_bad_lines.append(ln)
                continue
            if flag is True and not isinstance(dry, bool) and isinstance(dry, (int, float)) and dry > 0:
                water_bad_lines.append(ln)
            elif flag is True and fw.get("scope") == "window" and as_int(fw.get("tiles")) == 0:
                water_bad_lines.append(ln)
    if water_bad_lines:
        advice.append({
            "text": f"浇水证据有问题 ×{len(water_bad_lines)}：缺 watered_outdoor（缺失 ≠ 通过）或自述 true 与 "
                    "final_water 打架 ⇒ 别信窗口口径，按 farm.dryCrops（task-19）复核"
                    "（verify-run3.py 同向；run3 前必须把这条清零）",
            "lines": water_bad_lines,
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
    # task-38：跨日证据"无法判定"的那些天 —— 只能说无法判定，**不许**把"没写成"当"没做"
    # （真机 0.7.23 彩排：回执写"已跨日 spring 17→18"，但 day_end 没写 day_after、final 还是 17 日）
    undec_cross = []
    for sess in sessions:
        if not sess["day_ends"]:
            continue
        lineno, end = sess["day_ends"][-1]
        verdict, src, end_day = cross_day_evidence(as_dict(sess["start"]).get("day"), end)
        if verdict != CROSS_DAY_UNDECIDABLE:
            continue
        if src == "day_after":
            undec_cross.append(f"L{lineno}（day_after={end_day!r} 认不出 [年,季,日]）")
        else:
            undec_cross.append(f"L{lineno}（没有 day_after，final 是睡前快照 day={end_day!r}）")
    if undec_cross:
        out.append(f"无法判定是否跨日（缺失 ≠ 没做）×{len(undec_cross)} 天：{'、'.join(undec_cross[:8])}"
                   " —— `final` 是**睡前**快照，task-38 之后应由 `day_end.day_after`（睡后重取的观测）作证；"
                   "这段证据缺失时本工具**不判** `missed:cross_day`，只在此处如实记录")
    # task-64（Lead m02981/m03030）：真空日闸门要算"当天自我成功步数"，需要 stages 或 ok_steps；
    # 两者都缺时**无法判定**（缺失 ≠ 通过；也不许当 0 步直接判红）。
    no_step_fields = []
    for sess in sessions:
        if not sess["day_ends"]:
            continue
        lineno, ev = sess["day_ends"][-1]
        if ev.get("verified") is not True:
            continue
        if as_list(ev.get("stages")) or (sess.get("stage_events") or []):
            continue
        if "ok_steps" in ev:
            continue
        no_step_fields.append(lineno)
    if no_step_fields:
        out.append(f"有 {len(no_step_fields)} 天自称 VERIFIED，但既没有 stages 也没有 ok_steps"
                   f"（行 {no_step_fields[:8]}）：无法判定当天是否'0 步 VERIFIED'（缺失 ≠ 通过）")
    return out


# ---------------------------------------------------------------- 报告渲染
def build_report(rows, path, args, bad_lines):
    sessions, prelude = build_sessions(rows)
    events = {}
    for _, ev in rows:
        name = ev.get("event")
        events[name] = events.get(name, 0) + 1
    # Lead m02395：账本里出现、本工具既没有桶又不是结构性事件的名字 —— **绝不静默丢弃**，
    # 逐条点名（名字 + 次数 + 前若干行号），并在报告头部打印。
    unmapped = {}
    for lineno, ev in rows:
        name = ev.get("event")
        if name and name not in EVENT_BUCKETS and name not in STRUCTURAL_EVENTS:
            unmapped.setdefault(name, []).append(lineno)
    unmapped_events = {
        name: {"count": len(lines), "lines": lines[:20]}
        for name, lines in sorted(unmapped.items())
    }
    days = []
    weak_days = []
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
        cross_verdict, cross_src, cross_day = (
            cross_day_evidence(as_dict(start).get("day"), end)
            if end else (CROSS_DAY_NA, None, None)
        )
        checks_d = as_dict(end.get("checks"))
        dry_no_work = no_work_with_dry(end) if end else None
        # 真空日/弱日（Lead m02981）：当天的自我成功步数（有阶段记录时按 Σ stage.ok，否则退回 ok_steps）
        stage_recs_d = as_list(end.get("stages")) or [e2 for _, e2 in sess.get("stage_events") or []]
        if stage_recs_d:
            ok_self_d = 0
            for st_d in stage_recs_d:
                ok_self_d += as_int(st_d.get("ok"))
            ok_self_src = "stages"
        elif "ok_steps" in end:
            ok_self_d = as_int(end.get("ok_steps"))
            ok_self_src = "ok_steps"
        else:
            ok_self_d = None
            ok_self_src = None
        if end.get("verified") is True and ok_self_d is not None and 0 < ok_self_d < 5:
            weak_days.append({
                "line": sess["day_ends"][-1][0],
                "label": day_label(end),
                "ok": ok_self_d,
                "source": ok_self_src,
            })
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
            "checks": checks_d,
            # task-60：`day_justified` 的"正当理由"判定在 `no_work` + `dry>0` 时不成立
            "day_justified_effective": (checks_d.get("day_justified") is True and dry_no_work is None),
            "no_work_with_dry": dry_no_work,
            "final": as_dict(end.get("final")),
            # task-36：浇水证据（scope/tiles/crops/dry）随天带出来，供"每天一行"与测试核对
            "final_water": as_dict(end.get("final_water")),
            # task-38：跨日证据（优先 day_after；final 只是旧账本兜底，且它本身是睡前快照）
            "start_day": as_dict(start).get("day"),
            "day_after": as_list(end.get("day_after")),
            "cross_day_verdict": cross_verdict,
            "cross_day_source": cross_src,
            "cross_day_day": cross_day,
            "outcomes": len(sess["outcomes"]),
            "blocked": len(sess["blocked"]),
        })
    # task-69：同一天重复起跑（run6：stuck 后同日重试）——呈现必须正确：
    # 去重后按"日历日"数，**不算跨日、不算多天**（跨日证据只对 ended_by=sleep 生效）。
    distinct_labels = []
    for d in days:
        if d["label"] not in distinct_labels:
            distinct_labels.append(d["label"])
    same_day_retries = None
    if days and len(distinct_labels) < len(days):
        same_day_retries = {
            "sessions": len(days),
            "distinct_days": len(distinct_labels),
            "labels": distinct_labels,
            "retry_lines": [d["start_line"] for d in days],
        }
    # task-69：`buy` 事件（run6 死因之一）的如实计数 —— 桶 `buys` 早就有（Lead m02395），
    # 但它既不在 `NEW_EVENT_BUCKETS`、也没有专门呈现 ⇒ run6 的 6 次「没成交（item_not_sold）」
    # 在报告里是隐形的。这里把"没成交"如实计成**失败**（绝不因为事件存在就当成功）。
    buy_ok = 0
    buy_failed = 0
    buy_unknown = 0
    buy_codes = {}
    buy_failed_lines = []
    buy_sample = ""
    for ln, ev in rows:
        if ev.get("event") != "buy":
            continue
        ok = ev.get("ok")
        code = str(ev.get("code") or "")
        receipt = str(ev.get("receipt") or "")
        # 回执码优先（run6：`receipt` = "item_not_sold: [item_not_sold] (HTTP 200) …"）——
        # 它才是"为什么没成交"的指纹；`code` 只是桥的粗分类（run6 恒为 "failed"）。
        receipt_code = receipt.split(":")[0].strip() if ":" in receipt else ""
        code_eff = receipt_code or code
        if ok is True:
            buy_ok += 1
        elif ok is False or code not in ("", "ok", "success"):
            buy_failed += 1
            buy_failed_lines.append(ln)
            buy_codes[code_eff or "?"] = buy_codes.get(code_eff or "?", 0) + 1
            if not buy_sample:
                buy_sample = str(ev.get("reason") or "")[:220]
        else:
            buy_unknown += 1
    buy_counts = {
        "total": buy_ok + buy_failed + buy_unknown,
        "ok": buy_ok,
        "failed": buy_failed,
        "unknown": buy_unknown,
        "failed_lines": buy_failed_lines,
        "codes": buy_codes,
        # 同一回执连续失败 = 守卫要的条件现实不可满足（守卫死锁）的指纹
        "same_receipt": buy_failed >= 2 and len(buy_codes) == 1,
        "sample_reason": buy_sample,
    }
    finish = None
    for lineno, ev in rows:
        if ev.get("event") == "finish":
            finish = dict(ev)
            finish["line"] = lineno
    # task-70：种子经济（task-67）—— `no_seed_for_sale` / `cannot_afford` / `seed_unavailable_today`
    # 归**同一类**（种子/经济）但**分开计数**（不许互相掩护）。三者都不是硬失败；真正的指纹是
    # 「守卫还要求去买（buy 没成交 / ended_by=stuck）却拿不出种子」⇒ 与 buy 计数一起看。
    seed_counts = {"no_seed_for_sale": 0, "cannot_afford": 0, "seed_unavailable_today": 0}
    seed_lines = {k: [] for k in seed_counts}
    seed_offers = ""
    seed_money = None
    seed_price = None
    for ln, ev in rows:
        seed_name = str(ev.get("event") or "")
        if seed_name not in seed_counts:
            continue
        seed_counts[seed_name] += 1
        seed_lines[seed_name].append(ln)
        if seed_name in ("no_seed_for_sale", "cannot_afford"):
            if not seed_offers:
                seed_offers = str(ev.get("offers") or "")
            if seed_money is None:
                seed_money = ev.get("money")
            if seed_price is None:
                seed_price = ev.get("seed_price")
    seed_economy = {
        "total": sum(seed_counts.values()),
        "no_seed_for_sale": seed_counts["no_seed_for_sale"],
        "cannot_afford": seed_counts["cannot_afford"],
        "seed_unavailable_today": seed_counts["seed_unavailable_today"],
        "lines": seed_lines,
        "offers": seed_offers,
        "money": seed_money,
        "seed_price": seed_price,
        # run6 死锁指纹：确认买不到、却**没有**当天失效留痕 ⇒ 守卫很可能还在要"去买"
        "deadlock_risk": (seed_counts["no_seed_for_sale"] + seed_counts["cannot_afford"]) > 0
                         and seed_counts["seed_unavailable_today"] == 0,
    }
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
        # Lead m02395：口径必须与 tools\verify-run3.py:588-589 逐字一致
        # （decisions = event=="decision"；llm_true = 其中 `r.get("llm")` 为真）。
        "llm": sum(1 for ev in decisions if ev.get("llm")),
        # Lead m02565（裁定落盘 commit 69513b8，写进 docs/_run6-criteria.md §3.1）：口径拆两档，
        # 与 tools\verify-run3.py **同名同义**：
        #   decisions_llm        = `llm == true` ⇒ 发起过模型调用（含被拒/截断）
        #   decisions_llm_used   = `llm == true and source == "llm"` ⇒ 模型结果真被采纳
        #   二者之差             = deterministic_fallback（模型答了没用）
        # 判据说"LLM 覆盖"一律指 `decisions_llm_used`（否则 run6 覆盖率会被兜底刷虚高）。
        "decisions_llm": sum(1 for ev in decisions if ev.get("llm")),
        "decisions_llm_used": sum(1 for ev in decisions
                                  if ev.get("llm") and ev.get("source") == "llm"),
        "llm_fallback_lines": [ln for ln, ev in rows
                               if ev.get("event") == "decision"
                               and ev.get("llm") and ev.get("source") != "llm"],
        "llm_by_source": sum(1 for ev in decisions if ev.get("source") == "llm"),
        "llm_disagree_lines": [ln for ln, ev in rows
                               if ev.get("event") == "decision"
                               and bool(ev.get("llm")) != (ev.get("source") == "llm")],
        "by_source": decision_by_source,
        "by_boundary": decision_by_boundary,
        "truncated_lines": [ln for ln, ev in rows
                            if ev.get("event") == "decision" and ev.get("truncated")],
    }
    decision_counts["decisions_llm_fallback"] = (decision_counts["decisions_llm"]
                                                 - decision_counts["decisions_llm_used"])
    # 旧键名保留（外部脚本/既有用例在用），语义不变
    decision_counts["llm_used"] = decision_counts["decisions_llm_used"]
    decision_counts["llm_fallback"] = decision_counts["decisions_llm_fallback"]
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
        "weak_days": weak_days,
        # task-69：同日重试的呈现 + buy 事件的成/败计数（跑 run6 复核用）
        "same_day_retries": same_day_retries,
        "buy": buy_counts,
        # task-70：种子经济（task-67 的种子三事件；与 buy 一起才是守卫死锁的完整指纹）
        "seed_economy": seed_economy,
        "unmapped_events": unmapped_events,
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
    # task-52：不可达（四邻都站不过去 / A* 算不出路）——不计当天硬失败、当天记 blocked、次日重试；
    # 日级豁免有上界 max(5, 20%×attempted)，越界由 checks.unreachable_within_bound 说话。
    unreach_lines = []
    unreach_tiles = set()
    unreach_stage_lines = []
    unreach_summary_lines = []
    # task-63/task-66：被"游戏拒绝"（till 的 tool_ineffective/precondition_failed）——与不可达**并列但
    # 分开计数**（两套集合、两套界，不许互相掩护）。
    refused_lines = []
    refused_tiles = set()
    refused_stage_lines = []
    refused_summary_lines = []
    # task-68/task-76：可达性/开路（被围住 + 开路尝试 + 清邻格）——无硬闸门、不判红，只作信息项。
    enc_lines = []
    enc_tiles = set()
    enc_stage_lines = []
    enc_summary_lines = []
    frontier_lines = []
    frontier_acted = 0
    frontier_failed = 0
    neighbor_events = 0
    neighbor_opens = 0
    neighbor_lines = []
    # task-73：stuck 日有界翻篇（信息项：本日仍如实 stuck、day_justified=False、不 VERIFIED）
    stuck_flush_lines = []
    stuck_flush_ok = 0
    stuck_flush_skipped = 0
    stuck_flush_skip_reasons = set()
    stuck_flush_resnap_failed = 0
    zero_action_days = []
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
        # task-52：不可达三级留痕（逐格 / 阶段 / 日级汇总）
        for ln, ev in sess["unreachable"]:
            unreach_lines.append(ln)
            tile = ev.get("tile")
            if isinstance(tile, (list, tuple)) and len(tile) == 2:
                unreach_tiles.add((as_int(tile[0]), as_int(tile[1])))
        unreach_stage_lines.extend(ln for ln, _ in sess["unreachable_stages"])
        unreach_summary_lines.extend(ln for ln, _ in sess["unreachable_summaries"])
        # task-63/task-66：被游戏拒绝的三级留痕（逐格 / 阶段 / 日级汇总）
        for ln, ev in sess["tool_refused"]:
            refused_lines.append(ln)
            tile = ev.get("tile")
            if isinstance(tile, (list, tuple)) and len(tile) == 2:
                refused_tiles.add((as_int(tile[0]), as_int(tile[1])))
        refused_stage_lines.extend(ln for ln, _ in sess["refused_stages"])
        refused_summary_lines.extend(ln for ln, _ in sess["refused_summaries"])
        # task-68/task-76：可达性/开路（被围住三级留痕 / 开路尝试 acted 计数 / 清邻格）
        for ln, ev in sess["encircled"]:
            enc_lines.append(ln)
            tile = ev.get("tile")
            if isinstance(tile, (list, tuple)) and len(tile) == 2:
                enc_tiles.add((as_int(tile[0]), as_int(tile[1])))
        enc_stage_lines.extend(ln for ln, _ in sess["encircled_stages"])
        enc_summary_lines.extend(ln for ln, _ in sess["encircled_summaries"])
        for ln, ev in sess["frontier_clears"]:
            frontier_lines.append(ln)
            if bool(ev.get("acted")):
                frontier_acted += 1
            else:
                frontier_failed += 1
        for ln, ev in sess["clear_neighbors"]:
            neighbor_events += 1
            neighbor_lines.append(ln)
            neighbor_opens += as_int(ev.get("opens"))
        # task-73：stuck 日有界翻篇（只有 `stuck_flush` 的 ok=true 才算"睡过去成功"）
        for ln, ev in sess["stuck_flushes"]:
            stuck_flush_lines.append(ln)
            if ev.get("ok") is True:
                stuck_flush_ok += 1
        for _ln, ev in sess["stuck_flush_skips"]:
            stuck_flush_skipped += 1
            stuck_flush_skip_reasons.add(str(ev.get("reason") or "?"))
        stuck_flush_resnap_failed += len(sess["stuck_flush_resnap_failures"])
        # task-68：`stuck` 收尾且当天有阶段记录但成功动作 0 步 ⇒ "零动作收工"（run6 的形态；
        # verify-run3.py:639-643 同口径，只报信息项、不判红）。
        for _ln_end, _end_ev in sess["day_ends"]:
            _d_end = as_dict(_end_ev)
            if str(_d_end.get("ended_by") or "") != "stuck":
                continue
            _stages_d = as_list(_d_end.get("stages"))
            _ok_self = sum(as_int(as_dict(_st).get("ok")) for _st in _stages_d
                           if isinstance(_st, dict))
            if _stages_d and _ok_self == 0:
                zero_action_days.append({"line": _ln_end, "day": day_label(_d_end)})
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
    # task-52：不可达的日级豁免汇总（优先 `unreachable_summary` 事件，缺失时退回最后一天 day_end 的字段）
    unreach_summaries = [ev for s in all_sessions for _, ev in s["unreachable_summaries"]]
    _last_day_end = {}
    for _sess in reversed(all_sessions):
        if _sess["day_ends"]:
            _last_day_end = as_dict(_sess["day_ends"][-1][1])
            break
    if unreach_summaries:
        _u_sum = as_dict(unreach_summaries[-1])
    else:
        _u_sum = {
            "count": _last_day_end.get("unreachable"),
            "bound": _last_day_end.get("unreachable_bound"),
            "exempted": _last_day_end.get("unreachable_exempt"),
        }
    _u_checks = as_dict(_last_day_end.get("checks"))
    # task-63/task-66：被"游戏拒绝"的日级豁免汇总（优先 `refused_summary` 事件，缺失时退回最后一天
    # day_end 的字段）——与 unreachable 各算各的，两套豁免不互相掩护。
    refused_summaries = [ev for s in all_sessions for _, ev in s["refused_summaries"]]
    if refused_summaries:
        _r_sum = as_dict(refused_summaries[-1])
    else:
        _r_sum = {
            "count": _last_day_end.get("refused"),
            "bound": _last_day_end.get("refused_bound"),
            "exempted": _last_day_end.get("refused_exempt"),
        }
    # task-68/task-76：可达性/开路的日级汇总（优先 `encircled_summary`，缺失退回最后一天 day_end）
    enc_summaries = [ev for s in all_sessions for _, ev in s["encircled_summaries"]]
    if enc_summaries:
        _e_sum = as_dict(enc_summaries[-1])
    else:
        _e_sum = {"count": _last_day_end.get("encircled"), "engaged": None}
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
        # task-52：不可达（四邻都站不过去 / A* 算不出路）＝ 环境挡路的第三种形态。
        # 政策：**不计当天硬失败**、当天记 blocked、**次日重试**；日级豁免上界 max(5, 20%×attempted)。
        # 本工具只作信息项；越界由 checks.unreachable_within_bound=false 进 0 类红
        # （tools\verify-run3.py:415-448 把它判 problem ⇒ 两边同向）。
        "unreachable_events": sum(len(s["unreachable"]) for s in all_sessions),
        "unreachable_tiles": sorted([list(t) for t in unreach_tiles]),
        "unreachable_tile_count": len(unreach_tiles),
        "unreachable_lines": sorted(set(unreach_lines)),
        "unreachable_stage_events": sum(len(s["unreachable_stages"]) for s in all_sessions),
        "unreachable_stage_lines": sorted(set(unreach_stage_lines)),
        "unreachable_summary_events": sum(len(s["unreachable_summaries"]) for s in all_sessions),
        "unreachable_summary_lines": sorted(set(unreach_summary_lines)),
        "unreachable_count": _u_sum.get("count"),
        "unreachable_bound": _u_sum.get("bound"),
        "unreachable_attempted": _u_sum.get("attempted"),
        "unreachable_engaged": _u_sum.get("engaged"),
        "unreachable_exempt": _u_sum.get("exempted"),
        "unreachable_raw_unmet": _u_sum.get("raw_unmet"),
        "unreachable_unmet": _u_sum.get("unmet"),
        "unreachable_within_bound": _u_checks.get("unreachable_within_bound"),
        # task-63/task-66：被游戏拒绝（till 的 tool_ineffective/precondition_failed）＝ 环境挡路第四形态。
        # 政策：不计当天硬失败、当天封格、次日重试；日级豁免上界 max(5, 20%×attempted)，
        # 与 unreachable **独立起界**（各自的 bound/exempt）；越界由 checks.refused_within_bound=false
        # 进 0 类红（tools\verify-run3.py:518-521 把它判 problem ⇒ 两边同向）。
        "refused_events": sum(len(s["tool_refused"]) for s in all_sessions),
        "refused_tiles": sorted([list(t) for t in refused_tiles]),
        "refused_tile_count": len(refused_tiles),
        "refused_lines": sorted(set(refused_lines)),
        "refused_stage_events": sum(len(s["refused_stages"]) for s in all_sessions),
        "refused_stage_lines": sorted(set(refused_stage_lines)),
        "refused_summary_events": sum(len(s["refused_summaries"]) for s in all_sessions),
        "refused_summary_lines": sorted(set(refused_summary_lines)),
        "refused_count": _r_sum.get("count"),
        "refused_bound": _r_sum.get("bound"),
        "refused_attempted": _r_sum.get("attempted"),
        "refused_exempt": _r_sum.get("exempted"),
        "refused_raw_unmet": _r_sum.get("raw_unmet"),
        "refused_unmet": _r_sum.get("unmet"),
        "refused_within_bound": _u_checks.get("refused_within_bound"),
        "statuses": sorted(statuses),
    }
    # task-68/task-76：可达性/开路（**无硬闸门** ⇒ 不判红；与 unreachable 分开计数）
    report["reachability"] = {
        "encircled_events": sum(len(s["encircled"]) for s in all_sessions),
        "encircled_tiles": sorted([list(t) for t in enc_tiles]),
        "encircled_tile_count": len(enc_tiles),
        "encircled_lines": sorted(set(enc_lines)),
        "encircled_stage_events": sum(len(s["encircled_stages"]) for s in all_sessions),
        "encircled_stage_lines": sorted(set(enc_stage_lines)),
        "encircled_summary_events": sum(len(s["encircled_summaries"]) for s in all_sessions),
        "encircled_summary_lines": sorted(set(enc_summary_lines)),
        "encircled_count": _e_sum.get("count"),
        "encircled_engaged": _e_sum.get("engaged"),
        "frontier_clear_attempts": len(frontier_lines),
        "frontier_clear_acted": frontier_acted,
        "frontier_clear_failed": frontier_failed,
        "frontier_clear_lines": sorted(set(frontier_lines)),
        "clear_neighbor_events": neighbor_events,
        "clear_neighbor_opens": neighbor_opens,
        "clear_neighbor_lines": sorted(set(neighbor_lines)),
        "zero_action_days": zero_action_days,
    }
    # task-73：stuck 日**有界翻篇**（信息项；本日仍如实 stuck、day_justified=False、不 VERIFIED）
    report["stuck_flush"] = {
        "events": len(stuck_flush_lines),
        "ok": stuck_flush_ok,
        "not_ok": len(stuck_flush_lines) - stuck_flush_ok,
        "skipped": stuck_flush_skipped,
        "skip_reasons": sorted(stuck_flush_skip_reasons),
        "resnap_failed": stuck_flush_resnap_failed,
        "lines": sorted(set(stuck_flush_lines)),
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
    # task-65：退出码（默认：有红 ⇒ 1 / 0 红 ⇒ 0 / 跑不动 ⇒ 2；`--advisory` 恒 0）。
    # **计数必须走全量**：`report["categories"]` 被 `--top` 截断过，拿它当计数源会出现
    # "有红但退出码 0"的假绿（与 task-60 浇水建议同一教训）。
    red_all = []
    for items in (cat_manual(all_sessions, 0),
                  cat_missed(sessions, 0),
                  cat_wasted(sessions, 0) + cat_self_report(report)):
        red_all.extend(item for item in items if is_red_finding(item))
    report["red"] = {
        "total": len(red_all),
        "subjects": sorted({str(item.get("subject")) for item in red_all}),
        "lines": sorted({item["line"] for item in red_all if item.get("line") is not None}),
        "advisory": bool(getattr(args, "advisory", False)),
    }
    return report


MAPPING_TEXT = [
    ("day_start", "会话/天边界（每天一行摘要）"),
    ("未映射事件（任何其他 event 名）",
     "**绝不静默丢弃**：头部点名字与次数 + 建议 0a（task-15/41/42/49/50 的新事件都已进桶，"
     "见下三行；没有桶就说明映射落后于 brain/agentfarm/longrun.py）"),
    ("event:event_blocked / farm_evidence_unavailable (task-41)",
     "信息项：门口被挡 / farm 证据拿不到（次数见头部'新事件计数'；前者是硬失败的成因之一）"),
    ("event:sell / sell_failed (task-42)",
     "信息项：出货（sell_failed = 有货没卖成，run6 要单独看）"),
    ("event:goto_farm / plot_walk / resume_walk (task-49)",
     "信息项：进农场/走田区/续走 —— 路径层证据，配合 reason 看"),
    ("event:water_far / water_far_unavailable (task-50)",
     "信息项：窗口外远距浇水；`ok=false` + `given_up=true` = '窗口外干格够不着'的直接证据"),
    ("event:seed_gate / stage_midway_leftover (task-15)",
     "信息项：种子闸门（种子/钱不够 ⇒ till/plant 被跳过，不算硬失败）+ 阶段中途遗留"),
    ("event:no_seed_for_sale / cannot_afford / seed_unavailable_today (task-67)",
     "种子经济（信息项，**不是硬失败**）：货架没种子 / 留够 K 包买不起 / 买不到结论**当天失效**留痕；"
     "与头部 `购买:` 计数一起看 —— 买不到却没有失效留痕 = run6 那种守卫死锁（建议 0i）"),
    ("encircled / encircled_stage / encircled_summary（task-68、task-76）",
     "5 环境挡路·可达性/开路（信息项，**无硬闸门 ⇒ 一律不判红**）：被不可清障物围住（四邻没有"
     "「可站+可清」的突破口）＝与 `unreachable`（物理走不到）**分开计数**、不封格、不进任何豁免分子；"
     "三级留痕：逐格/阶段(encircled_leftover)/日级(count/attempted/engaged)；"
     "`day_end.encircled`/`encircled_tiles` 与它互检（缺失 ⇒ 只记【无法判定】，不当通过）"),
    ("frontier_clear / clear_neighbor（task-68、task-76）",
     "5 环境挡路·开路（信息项）：`frontier_clear` 是「所有目标都够不着时至少清一格可达的可清障格」"
     "的尝试（tile/acted/attempt/limit/why；**acted=false = 想清没清掉**）；"
     "`clear_neighbor` 是开路清掉的邻格（阶段级 opens/targets，逐格在 StepResult.after）——"
     "两者让 run6 那种「stuck + ok_steps=0 + 零动作收工」在头部与建议 0j 一眼可见"),
    ("stuck_flush / stuck_flush_skipped / stuck_flush_resnap_failed（task-73、dev 在制）",
     "5 环境挡路·解卡（信息项，**不判红**）：`stuck_flush` = stuck 日**有界翻篇**"
     "（绕过 sleep_guard 睡过去让整轮继续跑下一天；ok/count/limit/day_after/detail）；"
     "`stuck_flush_skipped` = 翻篇被跳过（reason=`eventUp`/存档类模态/次数达 limit）；"
     "`stuck_flush_resnap_failed` = 翻篇后重观测失败（只作诊断）。**绝不放宽验收**："
     "那天仍如实 ended_by=stuck、day_justified=False、不 VERIFIED ⇒ 头部'stuck 翻篇'行 + 建议 0k"),
    ("其他新事件（buy/env_retry/intent_unknown/zones_failed/day_key_resnap_failed/"
     "load_save/llm_on/day_cap/budget_exhausted/bridge_unavailable/watchdog_stop/"
     "mod_version_mismatch/llm_trace_failed/no_day_progress）",
     "信息项：只报次数（头部'新事件计数'）；no_day_progress 另有专门一行。"
     "注意 `mod_version_mismatch` 在 verify-run3.py 已被升为**问题**（能不能当验收证据），"
     "本工具不判验收、只点名次数 —— 两边分工见 docs/_run6-criteria.md"),
    ("decision",
     "顶部统计：总次数/decisions_llm（发起过调用 = llm 为真，含被拒/截断）/"
     "decisions_llm_used（真被采纳 = llm 为真且 source=='llm'）/来源/边界"
     "（new_day、task_kind_change、recovery…）；与 verify-run3.py 同名同义，"
     "差值 decisions_llm_fallback = deterministic_fallback（模型答了没用；"
     "判据说'LLM 覆盖'一律指 decisions_llm_used）；"
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
    ("day_end.ended_reason=no_work… + day_end.final_water.dry>0",
     "1 该做没做（红）：没活却还有干地（task-60）—— `day_justified` 在此形态下不成立；"
     "final_water 缺失 ⇒ 只进【无法判定】（缺失 ≠ 通过，也不凭空判红）"),
    ("day_end.checks.no_unmet_stages",
     "1 该做没做（false = 有阶段没达成；不与自算一致时以自算为准）"),
    ("day_end.day_after",
     "1 该做没做（红）：跨日证据 —— 有它就必须恰好 +1 天（+2/倒退都算）；**缺失或认不出 ⇒ 只进"
     "【无法判定】**，不许把'没写成'当'没做'（final 是睡前快照）"),
    ("plots_capped / work_spot",
     "顶部统计：作业区软上限触顶 / 收尾作业区（信息项，不改 VERIFIED；task-32）"),
    ("unreachable / unreachable_stage / unreachable_summary（task-52）",
     "5 环境挡路（信息项：**不计当天硬失败**、当天记 blocked、**次日重试**；日级豁免有上界 "
     "max(5, 20%×attempted)，`checks.unreachable_within_bound=false` ⇒ 0 必须人工介入"
     "（豁免越界＝可能把真失败当不可达洗白，verify-run3.py:415-448 判 problem ⇒ 两边同向））"),
    ("tool_refused / refused_stage / refused_summary（task-63/task-66）",
     "5 环境挡路（信息项：**不计当天硬失败**、当天封格、**次日重试**；与 unreachable 是两套独立豁免"
     "（各自的 bound/exempt，不许互相掩护），`checks.refused_within_bound=false` ⇒ 0 必须人工介入"
     "（豁免越界＝可能把真失败当「游戏拒绝」洗白，verify-run3.py:518-521 判 problem ⇒ 两边同向）；"
     "`day_end.refused*` / `checks.refused_within_bound` 缺失 ⇒【无法判定】，绝不当通过）"),
    ("day_end.verified=True + 有阶段记录 + Σ stage.ok==0（task-64）",
     "2 白做（红）：自称 VERIFIED 但当天成功动作 0 步（0 步不能自证做过事）。与 "
     "verify-run3.py:604-625 的真空日闸门同口径、**不许更宽**：有阶段记录时不吃 no_intents/"
     "no_work 类豁免（那只覆盖'当天 0 阶段'的 `wasted:verified_without_work` 那条）；"
     "`0 < Σ ok < 5` ⇒ 顶部'弱日'信息项；stages 与 ok_steps 都缺 ⇒ 只进【无法判定】"),
    ("finish",
     "收尾自述：code/verified_streak 必须自身自洽、并与正文 verified 天数同向（不同向 ⇒ 自述在洗账）"),
    ("t 回退",
     "信息项：同一会话内 t 倒退只记录，不判失败（verify-run3.py 同口径）"),
    ("本工具与 tools\\verify-run3.py", "独立读数、交叉核对：同一本账本给出相反结论 ⇒ 停下来人工对账，别单方面改口径"),
    ("refill / plot", "辅助：补水、观测（截断警告）"),
    ("idle", "辅助：一整轮没动作（acted/rounds）⇒ 空转，常与'该做没做'并看"),
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
    # task-69：同一天重复起跑（run6：stuck 后同日重试）——不许读成跨日/多天
    sdr = report.get("same_day_retries") or {}
    if sdr:
        add(f"同日重试: {sdr['sessions']} 个会话只有 {sdr['distinct_days']} 个不同日历日"
            f"（{'、'.join(sdr['labels'])}；**不算跨日、不算多天**；起跑行 {sdr['retry_lines']}）")
    add(f"步数合计: ok {report['ok_steps_total']} / skipped {report['skipped_steps_total']} "
        f"/ failed {report['failed_steps_total']}")
    nd = report["no_day_progress"]
    add(f"no_day_progress: {len(nd)} 次" + (f"（行 {[d['line'] for d in nd]}）" if nd else ""))
    blocked = report["events"].get("blocked", 0)
    blocked_detail = ",".join(f"{k} {v}" for k, v in sorted(report["blocked_by_action"].items())) or "-"
    add(f"blocked: {blocked} 条（{blocked_detail}）；其中理由含 grass 的 {report['blocked_grass']} 条"
        + ("（草格无效挥动）" if report["blocked_grass"] else ""))
    add(f"sleep: {report['events'].get('sleep', 0)} 次（ok {report['sleep_ok']} / failed {report['sleep_failed']}）")
    # task-69：`buy` 的成/败计数（run6 的 6 次没成交此前在报告里是隐形的；绝不把"事件存在"当成功）
    buy = report.get("buy") or {}
    if buy.get("total"):
        add(f"购买: {buy['total']} 次（成功 {buy.get('ok', 0)} / 没成交 {buy.get('failed', 0)}"
            + (f" / 未知 {buy['unknown']}" if buy.get("unknown") else "") + "）"
            + ("；回执 " + "、".join(f"{k}×{v}" for k, v in sorted((buy.get("codes") or {}).items()))
               if buy.get("codes") else "")
            + (f"  ⚠ 同一回执连续失败 ⇒ 守卫死锁嫌疑（行 {buy.get('failed_lines', [])[:6]}）"
               if buy.get("same_receipt") else ""))
    # task-70：种子经济（task-67）—— 买不到/买不起/当天失效留痕；与上一行的购买计数一起看
    se = report.get("seed_economy") or {}
    if se.get("total"):
        add(f"种子经济: 买不到 {se['no_seed_for_sale'] + se['cannot_afford']} 次"
            f"（没货 {se['no_seed_for_sale']} / 买不起 {se['cannot_afford']}）"
            f"；当天失效留痕 seed_unavailable_today {se['seed_unavailable_today']} 次"
            + (f"（money={se.get('money')}、seed_price={se.get('seed_price')}、"
               f"货架：{str(se.get('offers') or '')[:120]}）"
               if se.get("offers") else "")
            + ("  ⚠ 有买不到结论但没有当天失效留痕 ⇒ 守卫可能还在要「去买」（run6 死锁形态）"
               if se.get("deadlock_risk") else ""))
    # task-32：两种新事件形态的计数（信息项）；task-38：跨日证据覆盖度
    pc, ws = report["events"].get("plots_capped", 0), report["events"].get("work_spot", 0)
    add(f"软上限/收尾: plots_capped {pc} 次（作业区配额到顶，信息项）；work_spot {ws} 次（收尾作业区）")
    sleep_days = [d for d in report["days"] if d.get("ended_by") == "sleep"]
    if sleep_days:
        after_days = sum(1 for d in sleep_days if d.get("day_after"))
        add(f"跨日证据 day_after: {after_days}/{len(sleep_days)} 天（ended_by=sleep）"
            + ("" if after_days == len(sleep_days) else
               "  ⚠ 其余天没有该字段 ⇒ 跨日只能记【无法判定】（缺失 ≠ 没做；final 是睡前快照）"))
    weak = report.get("weak_days") or []
    if weak:
        add(f"弱日: {len(weak)} 天（VERIFIED 但成功动作只有 0<ok<5 步，信息项供复核）"
            f"（行 {[w['line'] for w in weak][:10]}）")
    dc = report.get("decision_counts") or {}
    if dc.get("total"):
        src_txt = "、".join(f"{k}={v}" for k, v in sorted(dc["by_source"].items()))
        bnd_txt = "、".join(f"{k}={v}" for k, v in sorted(dc["by_boundary"].items()))
        used = dc.get("decisions_llm_used", dc["llm"])
        fb = dc.get("decisions_llm_fallback", 0)
        add(f"决策: {dc['total']} 次（decisions_llm={dc['llm']}"
            + (f"，其中模型产出 decisions_llm_used={used}，"
               f"兜底 decisions_llm_fallback={fb} 见 {dc.get('llm_fallback_lines', [])[:5]}"
               if fb else f"，其中模型产出 decisions_llm_used={used}，无兜底")
            + f"）；来源 {src_txt}；边界 {bnd_txt}"
            + (f"；truncated={len(dc['truncated_lines'])} 行 {dc['truncated_lines'][:5]}"
               if dc["truncated_lines"] else "；无 truncated")
            + "；口径 = verify-run3.py:588-589（decisions_llm=发起过调用，"
              "decisions_llm_used=真被采纳；差值=deterministic_fallback = 模型答了没用）"
            + (f"  ⚠ `llm` 与 `source=llm` 不一致的行 {dc['llm_disagree_lines'][:8]}"
               f"（llm_by_source={dc['llm_by_source']}）——四路对账必须停下核对"
               if dc.get("llm_disagree_lines") else ""))
    # Lead m02395：run6 要看次数的新事件（task-15/41/42/49/50）；只在非 0 时点名，避免刷屏
    new_nz = [(k, report["events"].get(BUCKET_TO_EVENT.get(k, k), 0)) for k in NEW_EVENT_BUCKETS
              if report["events"].get(BUCKET_TO_EVENT.get(k, k), 0)]
    if new_nz:
        add("新事件计数: " + "、".join(f"{k}={v}" for k, v in new_nz))
    un = report.get("unmapped_events") or {}
    if un:
        add("未映射事件（本工具没有桶 ⇒ 绝不静默丢弃，先补 EVENT_BUCKETS 再读报告）: "
            + "、".join(f"{name}×{info['count']}（行 {info['lines'][:5]}）"
                       for name, info in sorted(un.items())))
    mi = report.get("manual_intervention") or {}
    red_total = mi.get("total", 0)
    add(f"模态: 打断 {mi.get('modal_interrupts_total', 0)} 次（信息项）"
        f"；必须人工介入（红）{red_total} 条"
        + ("  ⚠ 当天不判通过" if red_total else "")
        + (f"；by_event={mi.get('by_event')}" if mi.get("by_event") else ""))
    # task-65：退出码自述（默认严格：有红 ⇒ 1）；判决权威仍是 verify-run3.py
    rc_info = report.get("red") or {}
    rc_total = int(rc_info.get("total") or 0)
    rc_rc = 0 if rc_info.get("advisory") else (1 if rc_total else 0)
    add(f"退出码: {rc_rc}" + ("（--advisory 已开 ⇒ 恒 0）" if rc_info.get("advisory") else "")
        + f"；有红 {rc_total} 条"
        + (f"（{', '.join(rc_info.get('subjects') or [])}）" if rc_total else "")
        + "；0=无红 / 1=有红 / 2=跑不动；判决权威仍是 tools\\verify-run3.py")
    env = report.get("env_inconclusive") or {}
    add(f"环境挡路: {env.get('env_fail_events', 0)} 条（{env.get('env_fail_tiles', 0)} 格，"
        f"其中 {env.get('env_fail_unfinished_tiles', 0)} 格所在阶段最终没做成）；"
        f"自旋到上限 {env.get('env_spin_events', 0)} 次"
        + (f"（tiles={env.get('env_spin_tiles')}）" if env.get("env_spin_tiles") else "")
        + f"；没拿到结论: {env.get('inconclusive_events', 0)} 条（配额被吃掉 {env.get('inconclusive_tiles', 0)} 格）"
        + (f"；statuses={env.get('statuses')}" if env.get("statuses") else ""))
    # task-52：不可达（不计当天硬失败、次日重试；日级豁免有上界，越界进 0 类红）
    if env.get("unreachable_events") or env.get("unreachable_summary_events"):
        add(f"不可达: {env.get('unreachable_events', 0)} 次 / {env.get('unreachable_tile_count', 0)} 格"
            + (f"（tiles={env.get('unreachable_tiles')[:8]}）" if env.get("unreachable_tiles") else "")
            + f"；日级 count={env.get('unreachable_count')}、bound={env.get('unreachable_bound')}、"
              f"attempted={env.get('unreachable_attempted')}、exempt={env.get('unreachable_exempt')}"
            + ("  ⚠ checks.unreachable_within_bound=false ⇒ 0 类红"
               if env.get("unreachable_within_bound") is False else ""))
    # task-63/task-66：被游戏拒绝（不计当天硬失败、当天封格、次日重试；日级豁免有上界，越界进 0 类红）
    if env.get("refused_events") or env.get("refused_summary_events"):
        add(f"游戏拒绝: {env.get('refused_events', 0)} 次 / {env.get('refused_tile_count', 0)} 格"
            + (f"（tiles={env.get('refused_tiles')[:8]}）" if env.get("refused_tiles") else "")
            + f"；日级 count={env.get('refused_count')}、bound={env.get('refused_bound')}、"
              f"attempted={env.get('refused_attempted')}、exempt={env.get('refused_exempt')}"
            + ("  ⚠ checks.refused_within_bound=false ⇒ 0 类红"
               if env.get("refused_within_bound") is False else ""))
    # task-68/task-76：可达性/开路（**无硬闸门 ⇒ 不判红**；与不可达分开计数）
    reach = report.get("reachability") or {}
    if (reach.get("encircled_events") or reach.get("frontier_clear_attempts")
            or reach.get("clear_neighbor_events") or reach.get("zero_action_days")):
        reach_line = (f"可达性/开路: 被围住 {reach.get('encircled_events', 0)} 次 / "
                      f"{reach.get('encircled_tile_count', 0)} 格"
                      + (f"（tiles={reach.get('encircled_tiles')[:8]}）" if reach.get("encircled_tiles") else "")
                      + f"；日级 count={reach.get('encircled_count')}、engaged={reach.get('encircled_engaged')}"
                      + f"；开路尝试 {reach.get('frontier_clear_attempts', 0)} 次（真清掉 "
                        f"{reach.get('frontier_clear_acted', 0)} / 没清掉 {reach.get('frontier_clear_failed', 0)}）"
                      + (f"；为开路清邻格 opens={reach.get('clear_neighbor_opens', 0)}"
                         f"（{reach.get('clear_neighbor_events', 0)} 个阶段）"
                         if reach.get("clear_neighbor_events") else ""))
        if reach.get("frontier_clear_failed") and not reach.get("frontier_clear_acted"):
            reach_line += "  ⚠ 开路全部 acted=false（想清但没清掉 ⇒ 至少一轮零动作）"
        if reach.get("zero_action_days"):
            reach_line += ("  ⚠ 零动作收工: " + "、".join(
                f"{z.get('day')}(L{z.get('line')})" for z in reach["zero_action_days"]))
        add(reach_line)
    # task-73：stuck 日有界翻篇（信息项；本日仍如实 stuck / day_justified=False / 不 VERIFIED ⇒ 不判红）
    sf = report.get("stuck_flush") or {}
    if sf.get("events") or sf.get("skipped") or sf.get("resnap_failed"):
        sf_tail = ("  ⚠ 有跳过 ⇒ 那天没能睡过去（外层照旧 no_day_progress 终止）"
                   if sf.get("skipped")
                   else "（有界翻篇：让整轮继续跑下一天；本日仍如实 stuck、不 VERIFIED）")
        add(f"stuck 翻篇: {sf.get('events', 0)} 次（睡成功 {sf.get('ok', 0)} / 没成功 "
            f"{sf.get('not_ok', 0)}）；被跳过 {sf.get('skipped', 0)} 次"
            + (f"（原因 {'、'.join((sf.get('skip_reasons') or [])[:3])}）"
               if sf.get("skip_reasons") else "")
            + (f"；翻篇后重观测失败 {sf.get('resnap_failed', 0)} 次" if sf.get("resnap_failed") else "")
            + (f"（行 {sf.get('lines')[:6]}）" if sf.get("lines") else "")
            + sf_tail)
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
            # task-60：`no_work` + `dry>0` 时 day_justified 的正当性不成立（红条之外再在每天一行点出来）
            if day["checks"].get("day_justified") is True and not day.get("day_justified_effective", True):
                checks += "（day_justified 不成立：dry>0）"
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
            # task-38：跨日证据单独摆出来（有 day_after 以它为准；没有就说"无法判定"，不说"没跨日"）
            if day.get("cross_day_verdict") == CROSS_DAY_CROSSED:
                cross_text = (f" | 跨日={day.get('cross_day_source')} "
                              + "/".join(str(x) for x in as_list(day.get("cross_day_day"))))
            elif day.get("cross_day_verdict") == CROSS_DAY_WRONG:
                cross_text = (f" | 跨日=不是+1 天（{day.get('cross_day_source')} "
                              f"{day.get('cross_day_day')!r}）")
            elif day.get("cross_day_verdict") == CROSS_DAY_UNDECIDABLE:
                cross_text = " | 跨日=无法判定（缺 day_after，final 是睡前快照；缺失 ≠ 没做）"
            else:
                cross_text = ""
            add(f"  - {day['label']}: ended_by={day['ended_by']} verified={day['verified']} "
                f"ok/skip/fail={day['ok_steps']}/{day['skipped_steps']}/{day['failed_steps']} "
                f"checks[{checks}] 模态打断={day.get('modal_interrupts', 0)}{water_text}{cross_text} "
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
        description="长跑账本行为分析器：四类判定（该做没做/白做/无效挥动/睡觉时机）+ 证据行号 + 建议",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "退出码（task-65）：0 = 没有红；1 = 有红（`manual:*` 或 `missed:*` 或显式判红的\n"
            "                     `wasted:*`：洗白 / 0 步却 VERIFIED / 浇水矛盾 / 账目自述不一致）；\n"
            "                  2 = 跑不动（读不到 journal、空账本、参数错）。\n"
            "`--advisory` 诊断模式：无论有没有红都返回 0（老行为）。\n"
            "**判决权威仍是 tools\\verify-run3.py**：本工具是四路复核之一，退出码只表达\n"
            "\"有没有红\"，不表达\"整跑是否达标\"（达标看 verify-run3 的 0/1/2 与 docs\\_run6-criteria.md）。"
        ),
    )
    parser.add_argument("--journal", default=None,
                        help="账本路径（默认取 logs\\longrun-*.jsonl 里 mtime 最新）")
    parser.add_argument("--days", type=int, default=3, help="领跑天数（只用于 'X/N 天 VERIFIED' 的分母）")
    parser.add_argument("--top", type=int, default=10, help="每类明细最多显示条数（默认 10）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON（同结构）")
    parser.add_argument("--advisory", action="store_true",
                        help="诊断模式：恒返回 0（默认严格：有红 ⇒ 1）")
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
    red_total = int((report.get("red") or {}).get("total") or 0)
    if args.advisory:
        return 0
    return 1 if red_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
