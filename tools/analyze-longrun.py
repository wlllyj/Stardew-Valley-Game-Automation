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
     **不计当天硬失败**、当天记 blocked、**次日重试**，日级豁免有上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)）、
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
    max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)）⇒ 0 类红（豁免越界＝可能把真失败当"走不到"洗白）；
    `unreachable`/`unreachable_stage`/`unreachable_summary` 本身只作信息项、**不并进"该做没做"**
    （tools\verify-run3.py:415-448 同向：上界内是 info、越界才是 problem）。
  * 被游戏拒绝（task-63/task-66）：`checks.refused_within_bound=false`（当天被拒绝格数超过
    max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)）⇒ 0 类红 `manual:check:refused_within_bound`（可能把真失败混进
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
  * 死苗/放弃格（task-84，与 `tools\verify-run3.py:793-818` 对齐）：**死苗不浇水**（Mod 的
     `farm.dryCrops`/`dryTiles` 自 0.7.27 起只算活苗；死苗的“干”看 `farm.dryDeadCrops`）——
     `dry_dead > 0` 而 `ended_reason` 以 `no_work` 开头 ⇒ **判红** `missed:dry_dead_uncleared`
     （死苗不许当“今天没活”的借口；正确归宿是 `clear_dead`，够不着要如实 `stuck`/`gave_up_dry`）；
     `dry_dead` 不是整数 ⇒ 红（账目不可信）；`gave_up_tiles` 非空却自称 `verified=true` ⇒
     **只作警告 `warn:verified_with_gave_up`，不判红**（Lead m04997：真洗白通道已被 verify-run3 的
     `watered_outdoor=true` + `final_water.dry>0` 自相矛盾闸门堵住；认输格当天后来被解决、`dry==0`
     时判红就是假红）。`day_end.dead_crops`/`dead_crops_status`/
     `dry_dead`/`dry_dead_status`/`gave_up_tiles`（以及 `dead_crops_summary` 事件）**缺失 ⇒ 只进
     【无法判定】，既不算通过也不算失败**（缺失 ≠ 0）。
  * 背包空格死锁（task-102 `9b09735` / task-104，run8 day 2/12/13 形态）：**买不到不是失败** ——
    `buy_no_space`（回执 `no_space`/`no_inventory_space` ⇒ 当天不再重试 buy）、`slept_without_work`
    （当天 **0 农场动作**又有活 ⇒ 拒绝睡觉、当天不推进；是**守卫生效**的证据，不是"睡眠失败"）、
    `modal_dismiss_failed`（关模态时桥报错 ⇒ **只点名次数**，`tools\verify-run3.py` 不判它，
    判红会两边反向）、`water_far_skipped`（task-104：人不在户外农场 ⇒ 不扣额度、不认输）
    **一律不判红**，只作信息项：头部「种子经济/背包」一行 + 建议 0n。
    `free_slots` 取自 `sell`/`surplus_sell`/`surplus_sell_skip` 的 `trigger.freeSlots`，
    **缺失 ⇒ 写 `<缺失>` + 进【无法判定】（缺失 ≠ 0）**；旧账本没有 `buy_no_space` 事件时
    从 `buy.receipt` 的 `no_inventory_space` 回执码补认（run8 就是这样被看见的）。
    `sell`/`surplus_sell` 成交**当天 `money` 不变是设计**（钱等下一次 `NewDay` 结算）⇒ 绝不判红。
  * LLM 复盘 / 教训库（task-58/59/82，Lead m05325）：`review_llm`（收工复盘：notes/text/usage/
    rejected/truncated）、`review_llm_failed`（复盘失败 ⇒ **失败无害**，只记信息）、`lessons`
    （日终落盘：added/total/dropped/path）、`lessons_load_failed` / `lessons_save_failed`。
    **「模型没学到东西」不是失败**（空 notes / 空库 / 0 新增只记信息）；只有三条完整性红：
    ①`review_llm` 声称成功却 0 条 notes（`missed:review_llm_without_notes`）②教训库条数超上限
    （`missed:lessons_over_limit`；事件 `total` 或落盘 `<journal>-lessons.json` 条数 > brain
    `LESSONS_MAX=20`）③教训库读不了/文件损坏（`missed:lessons_load_failed`）。教训库路径由
    journal 推导（`X.jsonl` ⇒ `X-lessons.json`，与 brain `_derive_lessons_path` 同约定，
    **不新增命令行开关**）；旧账本没有这些事件 ⇒ 头部 `<缺失>` + 【无法判定】（缺失 ≠ 0）。
  * 教训库拒收（task-114 F1，`lessons_rejected`）：schema 校验丢条**必须留痕**，但**拒收本身不判红**
    （文件被外部改过/结构不符时拒收是**正确**行为）⇒ 头部可 grep 的 `拒收 N 次 / M 条（原因…）`；
    只有 `dropped>0` 且 `kept==0` **连续 ≥2 天**给 `warn:lessons_all_rejected` 可视行（不判红、不进 rc）；
    缺 `kept`/缺事件 ⇒ 只进【无法判定】（缺失 ≠ 0，绝不当"没被拒收"通过）。
  * 不可信条目与防洗白（task-118 A / task-120）：`lessons_rejected.untrusted`（这次载入被判不可信的
    条数）、`lessons.written` / `lessons.skipped_untrusted`（回写只持久化 `src=agentfarm` 的可信条目 ⇒
    这一对就是"防洗白生效"的直接证据；不可信条目在注入行里带 `[外部条目·未验证]` 前缀、**绝不回写**）。
    头部 `LLM 复盘/教训库` 行给可 grep 的 `教训库写入 N 条 / 跳过 M 条（不可信）/ 拒收 K 条（其中不可信 J 条）`；
    **全部不判红**（`skipped_untrusted>0` 是好事），只有 `skipped_untrusted>0 且 written==0` **连续 ≥2 天**
    给 `warn:lessons_all_untrusted` 可视行；缺字段 ⇒ 只进【无法判定】（缺失 ≠ 0，绝不当"没有不可信条目"通过）。
  * 教训素材质量（task-136 C / task-139）：`lessons.hint_dropped` = 当天被"矛盾判据"
    （`planner.hint_contradicts_evidence(symptom, evidence, hint)`）丢掉的 `hint` 条数（每日重置）
    ⇒ **丢弃是设计行为、防污染生效的正面证据，不判红**（verify-run3.py 对该字段零命中）。
    头部 `教训素材质量` 行给可 grep 的 `入库 N 条 / hint 丢弃 M 条 / 拒收 K 次（原因…） / 库大小 J` + 建议 0o；
    只给三条可证伪形态的 ⚠（不进 rc）：字段缺失/非整数、某天丢弃数 > 当天新增条数（口径打架）、
    库文件里有 `hint` 为空的条目却没有 `hint_dropped` 计数（疑字段被摘/没记账）；
    缺事件/缺字段 ⇒ 头部 `<缺失>` +【无法判定】（缺失 ≠ 0，绝不当"没有矛盾 hint"通过）。
  * review 兜底与换片连发（task-124 / task-130）：`review_only_fallback`（review 独苗却有活 ⇒
    换成能落地的意图 `source=work_spot` / 把人带回跨片 leftover `source=pending_walk`）、
    `review_only_no_target`（兜底也拿不出目标 ⇒ 把守卫抱怨的 leftover 如实记为"今天放弃"，
    `pending`/`tiles`，次日重试、不碰判定字段）、`plot_exhausted_burst`（同一秒 ≥5 次换片 ⇒
    按有界机制收尾；brain `PLOT_EXHAUSTED_BURST=5`）、`review_only_fallback_failed`（防御性）。
    头部 `review 兜底/换片连发` 行 + 建议 0p。**本身一律不判红**（它们是修复生效的证据，
    `tools\verify-run3.py` 对这四个名字零命中 ⇒ 判红会两边反向）；只给三条**可证伪形态**的 ⚠ 警告：
    ①burst 当天却自称 `verified=true`（连发=没目标的证据，与 VERIFIED 互斥）；②弃权后当天
    `ended_reason` 仍说"守卫仍说还有活"（弃权没生效）；③兜底出简报抛异常。旧账本没有这些事件
    ⇒ 头部 `<缺失>` + 【无法判定】（**缺失 ≠ 0 = 没发生过**，绝不当"没发生"通过）。
  * 部分购买 / 量力而行（task-123 在制 / task-132）：下单量 `n = min(buy_count, money//price)`，
    `n >= 1` 就买下（`n < wanted` 时另记 `buy_partial`：`item`/`bought`/`wanted`/`price`/
    `price_shelf`/`price_cfg`/`money`/`source`/`ok`/`code`），`n == 0` 一个都买不起 ⇒ 记
    `cannot_afford` 且**一个请求都不发**。头部 `部分购买` 行 + 建议 0p-2；口径 = **买一半不是失败**
    （`buy_ok` 类成交只算**买满 `wanted`** 的整笔；`tools\verify-run3.py` 对 `buy_partial` 零命中
    ⇒ 本工具不判红、不进 rc）。只给两条**可证伪形态**的 ⚠ 警告：①`buy` 自称成交却
    `count < wanted` 且当天没有对应 `buy_partial`（量力而行必须留痕）；②同日既有 `buy_partial`
    又有 `cannot_afford`（可能是不同货品单价差、也可能判据打架，只提示人工核对）。
    旧账本没有该事件、`buy` 也没有 `wanted` 字段 ⇒ 头部 `<缺失>` + 【无法判定】（缺失 ≠ 0）。
  * 窗口外浇水 + 壶空补水（task-133）：`water_far` 新增 `cause`（**`need_refill` = 壶空 ⇒
    "不是够不着"**）/`evidence`/`refills`/`retried_after_refill`/`in_dry_tiles_before|after`/
    `dry_tiles_status`；壶空时先记 `water_far_refill`（`tile`/`ok`/`code`/`water_before`/
    `water_after`/`tries`/`limit`/`reason`/`receipt`，一天有界 ≤ `FAR_DRY_REFILL_MAX`=2），
    补上后回浇同一格。头部 `窗口外浇水/补水` 行 + 建议 0q；口径 = **两个事件都不是失败**
    （`tools\verify-run3.py` 对 `water_far_refill` 零命中 ⇒ 本工具不判红、不进 rc）。只给两条
    **可证伪形态**的 ⚠：①补水没成（回执不 ok 且水位没涨）当天却把那格浇成了（回执/水位有一边
    不可信）；②当天补水预算用尽（`tries >= limit`）⇒ 剩下的干格今天注定浇不上。
    旧账本没有 `water_far_refill`、`water_far` 也没有 `cause` ⇒ 头部 `<缺失>` + 【无法判定】
    （缺失 ≠ 0）。
  * 阶段自愈 + 如实收工（task-144，dev-coder 在制）：`refill_retry` = 阶段内壶空 ⇒ 补水后把这一轮
    没成事的**已分配格原样重跑**（`stage`/`zone`/`ok`/`refills_today`/`limit`/`tiles`/`targets`；
    不再重算窗口把格子从目标里丢掉）；`stage_stop_named` = 阶段自然走完（`stopped==""`）却仍有
    分配未成事的格 ⇒ 补**如实** stop 原因（`cause`∈`need_refill`/`unreachable`/`no_seed`/`incomplete`；
    `assigned`/`assigned_undone`/`tiles`/`codes`）。头部 `阶段自愈/如实收工` 行 + 建议 0s；
    口径 = **两者都不是失败**（`tools\verify-run3.py` 对两名零命中 ⇒ 本工具不判红、不进 rc）。
    只给三条 **可证伪形态**的 ⚠（不进 red / 不进 rc）：①当天重跑条数 > 当天 `refill` 条数；
    ②`refill_retry{ok=true, tiles=0}`（说重跑却没格子）；③`stage_stop_named` 的 `cause` 缺失/未知、
    `assigned_undone<=0`、或有过失却 `codes` 全空。**增量（`2438cae`）**：`refill_retry` 另带
    `stage_refills`（该阶段已补水几次）/`stage_limit`（= `STAGE_REFILL_MAX`，brain 现值 2），头部
    「阶段补水 <stage> N/M 次」呈现；`stage_refills > stage_limit` ⇒ 第四条 ⚠（同样不进 rc）。
    旧账本没有这两个事件 ⇒ 头部 `<缺失>` +【无法判定】（缺失 ≠ 0）。
  * task-157（够不着 ⇒ **有界开路**再重试）：`water_far_open`（为够不着的干格清掉挡路邻格；
    **开路成功 ≠ 浇上水**）与 `water_far_blocked`（开路后仍站不到 ⇒ **如实**记没浇上，cause ∈
    no_route/unreachable/need_refill/truncated/no_evidence/not_watered）；`water_far` 另带
    `opens`/`opened_count`。头部 `开路/够不着` 行；**都不是失败**（`verify-run3.py` 对两名零命中
    ⇒ 不判红、不进 rc；当天达不达标由 `checks.watered_outdoor` 说话），只两条可证伪 ⚠：
    ①开路成功但那格当天最后仍在 dryTiles 里；②有格 blocked 而当天却自称户外浇水达标（dry=0）。
  * task-158（体力预算）：`stamina_budget`（每天一条：max/stamina/live_crops/dry/water_reserve/
    water_cost_est/path_allowance/capacity/basis/deferred_by_budget/deferred[]，basis ∈
    farm/conservative，证据不足 fail-closed）与 `deferred_by_budget`（某任务**只因预算**被延后），
    日级另有 `day_end.stamina_budget`。头部 `体力预算` 行 + 建议 0u；同样**不判红**（没浇完就是
    `crops_watered=false`），只两条可证伪 ⚠：①说「只因预算延后」却当天自称浇完（dry=0）；
    ②日级 `deferred_by_budget>0` 却没有对应事件。旧账本没有这两个事件/字段 ⇒ `<缺失>` +
    【无法判定】（缺失 ≠ 0，绝不当作「今天没用预算」）。
  * task-163（预算延后的活不再算「还有活」+ 容量命中可见）：`budget_deferred_tiles`（日级/日初，
    某任务有 count 格被**体力预算**显式延后 ⇒ 守卫不再把它们算作"还有活"；`{task: n}` 语义在
    `day_end.stamina_budget.deferred_tiles` 里）与 `stage_capped_by_capacity`（stage 级：分配额被
    当天容量上限卡住 ⇒ 只分配 capacity 格）。日级子键还有 `capacity_capped_tasks` /
    `capped_by_capacity{task:{limit,capacity}}`。两条都是**诚实留痕、不判红、不进 rc**
    （`tools\verify-run3.py` 对这两名零命中）；只两条可证伪 ⚠（不进 rc）：①当天有
    `budget_deferred_tiles` 却自称"该做的都做了"（`no_work` + `verified=true`）⇒ 人工核对
    「延后是否真的只发生在体力 ≤ water_reserve **且** 有浇水债时」（task-163 的红线锚点）；
    ②同日有延后但 `stamina_budget` 显示没有浇水债（`live_crops<=0` 或 `dry<=0`）⇒ 延后可能
    已经变成"免罚额度"。缺失 ⇒ `<缺失>` +【无法判定】（缺失 ≠ 0）。
  * task-20 / task-164（clump 工具门槛）：`blocked_by_tool`（逐格：工具等级/种类不够、或 `toolOk`
    判不出 ⇒ fail-closed）与 `blocked_by_tool_summary`（日级汇总）只作**信息项** —— 它们是**动手
    之前**就拦下的诚实跳过（0 次 `use_tool`、不进 `unreachable`/`refused` 两套豁免、也不算"活"、
    不进守卫理由），头部 `工具门槛` 行 + 建议 0v；**不判红、不进 rc**（`tools\verify-run3.py` 对
    这两名零命中，判红会两边反向）；只一条可证伪 ⚠（不进 rc）：当天自称 `no_work` 却存在工具门槛
    封格 ⇒ 人工核对「真敲不动 vs 工具够却判不出」。旧账本 ⇒ `<缺失>` +【无法判定】（缺失 ≠ 0）；
    `min_level` 缺失 ⇒【无法判定】等级，绝不默认 0 级。
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
    "unreachable_within_bound": "当天'unreachable'格数超过上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)"
                                "—— 可能把真失败/不可动格混进不可达来洗白，必须人工核对 unreachable_tiles",
    # task-63/task-66：被**游戏拒绝**（till 的 tool_ineffective / precondition_failed）的硬上界
    "refused_within_bound": "当天'被游戏拒绝'的格数超过上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)"
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
     "不可达豁免上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)（task-52）"),
    # task-78 / task-80：上界**基数**（= 发起过动作且不是 encircled 的步数）。deputy 的伪造账本 V5
    # 曾用 `encircled` 把旧分母 `attempted` 抬到 800 ⇒ 20% 上界 200 ⇒ 200 格真不可达被豁免、exit 0。
    ("day_end.bound_basis", "bound_basis",
     "豁免上界基数 = attempted − encircled（task-78；**被围住的格不参与起界**）；本工具按它自算上界，"
     "绝不采信比自算更大的账本上界"),
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
     "拒绝豁免上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)（task-63）"),
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
    # task-73（dev 在制 working tree）：stuck 日**有界翻篇** —— 本日仍如实 stuck / 不 VERIFIED，
    # 而不是 19 秒终止。**绝不放宽验收**（本日仍 ended_by=stuck / day_justified=False / 不 VERIFIED）
    # ⇒ 只作信息项：翻篇成功、被跳过（eventUp/存档模态/次数上限）、翻篇后重观测失败。
    ("event:stuck_flush", "stuck_flush",
     "stuck 日有界翻篇（task-73：ok/count/limit/day_after/detail；不判红、不洗白 stuck）"),
    ("event:stuck_flush_skipped", "stuck_flush_skipped",
     "翻篇被跳过（task-73：reason=eventUp / 存档类模态 / 次数达 limit）"),
    ("event:stuck_flush_resnap_failed", "stuck_flush_resnap_failed",
     "翻篇后重观测失败（task-73：error；只作诊断）"),
    # task-55/task-91：盈余材料换种子钱（钱次日 NewDay 结算；缺字段记【无法判定】、绝不判红）
    ("event:surplus_sell", "surplus_sell",
     "本轮卖盈余材料汇总（task-55：sold 件数/ok_count 叠数/below_keep/trigger{money,threshold,emptyDirt}；"
     "**钱要等下一次 NewDay ⇒ 当天 money 不变是设计**）"),
    ("event:surplus_sell_skip", "surplus_sell_skip",
     "想卖盈余材料但没有材料超过保留线（task-55：short=缺口 g、below_keep、trigger、items）⇒ **不是失败**"),
    ("event:sell.strategy", "sell_strategy",
     "逐叠出货字段（task-55/task-42：strategy=surplus_materials / keep / below_keep / slot / qid / stack）"),
    ("event:cannot_afford.money", "cannot_afford_money",
     "钱不够买当季种子（task-55：money/seed_price/short 缺口；**不是失败**、当天不走 buy）"),
    # task-84（死苗不浇水 + `given_up` 守卫）：Mod `farm.deadCrops`（枯死格数）与 `farm.dryDeadCrops`
    # （枯死**且没浇**）；brain 侧日级字段 `dead_crops`/`dead_crops_status`/`dry_dead`/`dry_dead_status`/
    # `gave_up_tiles` 见 `longrun.py:3390-3406`。缺失 ⇒【无法判定】（缺失 ≠ 0），绝不因此判通过；
    # `dry_dead>0` 且 `ended_reason` 以 `no_work` 开头 ⇒ 判红（见 cat_missed 1i）。
    ("day_end.dead_crops", "dead_crops",
     "Mod farm.deadCrops：全农场枯死作物格数（task-84；死苗不浇水、等 clear_dead 清，不计浇水证据）"),
    ("day_end.dead_crops_status", "dead_crops_status",
     "死苗计数的可信状态（ok / unavailable；task-84；缺失 ⇒ 死苗总数无法判定）"),
    ("day_end.dry_dead", "dry_dead",
     "枯死**且没浇**的格数（Mod farm.dryDeadCrops，0.7.27 新字段，task-84）；>0 且 ended_reason "
     "以 no_work 开头 ⇒ 判红（死苗不许当『今天没活』的借口，应走 clear_dead / 如实 stuck/gave_up_dry）"),
    ("day_end.dry_dead_status", "dry_dead_status",
     "枯死没浇计数的可信状态（ok / unavailable；task-84）"),
    ("day_end.gave_up_tiles", "gave_up_tiles",
     "当天认输的窗口外干格坐标 [[x,y],…]（task-84：不再当『还有活』，按 gave_up_dry 如实收尾）；"
     "非空且自称 VERIFIED ⇒ **只警告不判红**（`warn:verified_with_gave_up`，Lead m04997）"),
    ("event:dead_crops_summary", "dead_crops_summary",
     "日级死苗汇总（task-84：dead_crops/dry_dead/dry_dead_status/gave_up/tiles；只在 dead_crops>0 "
     "且状态 ok 时写）"),
    # task-102（背包空格死锁）：三个新事件都**不是失败**，缺失 ⇒【无法判定】（缺失 ≠ 0 / ≠ "没发生"）。
    ("event:buy_no_space", "buy_no_space",
     "回执 `no_space`（`no_inventory_space`，task-102：item/price/attempt/free_slots_status/reason）"
     "⇒ 当天不再重试 buy；**买不到不是失败**（钱不够、没货架、没空格一律不判红）"),
    ("event:slept_without_work", "slept_without_work",
     "当天 0 农场动作又有活 ⇒ **拒绝睡觉、当天不推进**（task-102：why/farm_actions/reasons/note）；"
     "这是守卫生效的证据，**不是睡眠失败**，那天会以 needs_review / no_day_progress 如实停住"),
    ("event:modal_dismiss_failed", "modal_dismiss_failed",
     "关模态时桥报错（task-102：menu/reason）；`tools\\verify-run3.py` 不判它 ⇒ 本工具只点名次数、"
     "**不判红**（免得两边反向——Lead m05068 的『两边判决一致』要求）"),
    ("event:water_far_skipped", "water_far_skipped",
     "窗口外有干作物、但**人不在户外农场**（task-104：reason=not_on_farm/tiles/count/where/note）"
     "⇒ 不扣该格当日额度、不进 `given_up`，**不是失败**；先回农场再说（run8 day 12 形态）"),
    # task-133：壶空是**前置条件**，不是「够不着」——动手前先补水（一天有界 ≤2 次），补水后回浇同一格。
    # 这些事件都**不是失败**；只有"补不上水却浇成了""预算用尽"这两条可证伪形态才给 ⚠（不判红）。
    ("event:water_far_refill", "water_far_refill",
     "窗口外浇水前的一次补水（task-133：tile/ok/code/water_before/water_after/tries/limit/reason/"
     "receipt）⇒ **不是失败**，是'壶空=前置条件'的直接证据；补水没成才是那格今天浇不上的因由"),
    ("event:water_far_refill.water_after", "water_far_refill_water_after",
     "补水后的壶内水量（`None` = 无尽壶/读不到）；`water_after > water_before` 即使回执不 ok 也算"
     "补上了 —— brain 的判据同此（回执可能不准）"),
    ("event:water_far.cause", "water_far_cause",
     "窗口外干格没浇成的因由（task-133：`need_refill`=壶空 ⇒ **不是够不着**；`not_watered` 等）；"
     "缺失 ⇒ `<缺失>`（旧账本形态，不当 0）"),
    ("event:water_far.refills", "water_far_refills",
     "该次尝试时当天已用掉的窗口外补水次数（task-133；与 `refill_limit` 一起看预算是否用尽）"),
    ("event:water_far.retried_after_refill", "water_far_retried_after_refill",
     "补水后是否回浇了同一格（task-133：true = 壶空→补水→回浇这条链真跑完，不是空转）"),
    ("event:water_far.dry_tiles_status", "water_far_dry_tiles_status",
     "`farm.dryTiles` 可信度（task-104/133：ok / unavailable）；unavailable ⇒ 判不了那格是否还干"),
    ("event:water_far.in_dry_tiles_after", "water_far_in_dry_tiles_after",
     "浇完后该格是否**仍在** dryTiles 里（判据 = 该格 watered=true 或已不在 dryTiles，"
     "绝不用全局 dryCrops 差值）"),
    ("event:goto_farm.where", "goto_farm_where",
     "进农场/走位的原因（task-49/task-102：`day_start` = 日初入场；`day_start_retry` = 早晨被模态挡下"
     "后的重试入场 —— run8 day 12 的 goto_farm 就是被晨间 ShippingMenu 挡成 ui_modal）"),
    ("event:surplus_sell.trigger.freeSlots", "free_slots",
     "背包空格数（`surplus_sell` / `surplus_sell_skip` / `sell` 的 `trigger.freeSlots` + "
     "`trigger.freeSlotsStatus`；task-102 腾格路径的门闸就是这个数；缺失 ⇒ 写 `<缺失>`、不当 0）"),
    ("event:surplus_sell.why", "sell_why",
     "卖出触发路径（task-102：`need_money`=钱不够 / `need_slot`=钱够但背包没空格 ⇒ 卖一叠腾格）"),
    ("event:review_llm", "review_llm",
     "收工 LLM 复盘（task-59：day_key/notes(≤3 条)/text/usage/duration_ms/model/rejected/"
     "truncated/note）；**声称成功却没有任何 notes ⇒ 判红**（`missed:review_llm_without_notes`，"
     "task-111）；notes 为空列表、rejected 非空、truncated=true 都只记信息"),
    ("event:review_llm_failed", "review_llm_failed",
     "收工复盘失败（task-59：day_key/reason/called/rejected/note）⇒ **失败无害**（睡觉与跨日照常，"
     "只是次日看不到笔记）⇒ 只记信息、不判红"),
    ("event:lessons", "lessons_event",
     "跨日教训库落盘（task-82：day_key/added(id 列表)/total/dropped/path/note）；`total` 超过"
     f"上限 ⇒ 判红（`missed:lessons_over_limit`，上限见 brain planner.LESSONS_MAX）；"
     "空库/本日 0 新增只记信息（**不因'模型没学到东西'判红**）"),
    ("event:lessons_load_failed", "lessons_load_failed",
     "教训库读不了（task-82：path/error/note：`read_failed:`=JSON 坏 / `not_a_list`=结构坏 / "
     "`bad_path:`）⇒ 文件损坏/不可信 ⇒ 判红（`missed:lessons_load_failed`；brain 的'失败无害'"
     "指不中断跑批，不指账目可信）"),
    ("event:lessons_save_failed", "lessons_save_failed",
     "教训库写不进去（task-82：path/error/note）⇒ 只记信息（本批教训只在内存里，跑批照常）"),
    ("event:lessons_rejected", "lessons_rejected",
     "教训库被拒收（task-114 F1：path/dropped/reasons/kept/note）⇒ **拒收本身不判红** —— 文件被外部"
     "改过/结构不符时，拒收是**正确**行为；只有「dropped>0 且 kept==0」连续 ≥2 天时给 "
     "`warn:lessons_all_rejected` 可视行（只警告、不判红、不进 rc）"),
    ("event:lessons_rejected.kept", "lessons_rejected_kept",
     "task-114：这次载入后**留下来**的教训条数（`kept==0` 表示这一版库一条都没通过 schema 校验）"),
    ("event:lessons_rejected.dropped", "lessons_rejected_dropped",
     "task-114：这次载入被**丢掉**的条数（>0 且 kept==0 ⇒ 整库不可用；两侧都要看，别只看一边）"),
    ("event:lessons_rejected.untrusted", "lessons_rejected_untrusted",
     "task-118 A：这次载入被判为**不可信**的条数（没有 `src` 标记 / 旧格式 / 外部改过）⇒ 不抢 20 名额、"
     "注入行带 `[外部条目·未验证]` 前缀、**绝不回写**（防洗白）⇒ 只记信息、不判红"),
    ("event:lessons.written", "lessons_written",
     "task-118 A.4：这一轮真正**落盘**的教训条数（只写 `src=agentfarm` 的可信条目；"
     "写不进去/空库都只记信息）"),
    ("event:lessons.skipped_untrusted", "lessons_skipped_untrusted",
     "task-118 A.4：落盘时**跳过**的不可信条数 —— (written, skipped_untrusted) 这一对就是"
     "『防洗白生效』的直接证据：跳过多说明库里有外部条目、而它们绝不会被重新盖戳写回 ⇒ "
     "只记信息、不判红；`skipped_untrusted>0 且 written==0` 连续 ≥2 天 ⇒ "
     "`warn:lessons_all_untrusted` 可视行（库被外部整版污染，只警告不进 rc）"),
    ("event:lessons.hint_dropped", "lessons_hint_dropped",
     "task-136 C（task-139）：当天被『矛盾判据』（`hint_contradicts_evidence(symptom, evidence, hint)`）"
     "丢掉的 hint 条数（每日重置）⇒ **丢弃是设计行为、防污染生效的正面证据，不判红**；"
     "缺失/非整数 ⇒ ⚠ +【无法判定】（缺失 ≠ 0，绝不当'没有矛盾 hint'通过）"),
    # task-172（dev task-170 `d88498d`）：**「看着熟」与「真能收」分家** + 逐格如实放弃。
    #     `tiles[].ready` = Mod 反射游戏自己的 `HoeDirt.readyForHarvest()`（authoritative；
    #     `null` = 读不到 ⇒ 只记【无法判定】，**绝不当 false**）；`farm.readyCrops` 与旧的
    #     `farm.ripeCrops`（= `Crop.fullyGrown`）并列 ⇒ 差值 = 「看着熟其实不能收」= task-169 病根。
    #     `harvest_gave_up` = 逐格如实放弃（试满 attempts/limit、当天不再回头）⇒ **不是豁免分子**：
    #     brain 把它从目标池/守卫里扣掉，但 `_leftover("harvest")` 不扣 ⇒ 它就是「该做没做」的证据。
    ("event:harvest_gave_up", "harvest_gave_up",
     "task-170：逐格如实放弃（tile/attempts/limit/codes/note）⇒ 当天不再回头、目标池与守卫都把它"
     "扣掉，但 `_leftover(\"harvest\")` **不扣** ⇒ **如实放弃 ≠ 已做完**，绝不当豁免配额；"
     "头部'收获放弃'行 + 建议 0s-2；缺失 ⇒【无法判定】（缺失 ≠ 0）"),
    ("tiles[].ready", "tile_ready",
     "task-170 新观测：游戏口径「可收」= Mod 反射 `HoeDirt.readyForHarvest()`（`Crop.fullyGrown` "
     "之外还排 regrow 期 `dayOfCurrentPhase>0` / `dead` / `forageCrop==\"2\"`）；true=真能收、"
     "false=不能收、**null=读不到（≠不能收）**"),
    ("tiles[].fullyGrown / harvestMethod / currentPhase / phaseDays / dayOfCurrentPhase / "
     "forageCrop / whichForageCrop / regrowsAfterHarvest", "tile_crop_meta",
     "task-170 逐格作物元数据（`ready` 的输入，用于解释「为什么看着熟却不能收」）；缺失 ⇒【无法判定】，"
     "**不许用 ripe 顶替 ready**"),
    # task-179（dev task-176 `037e599`）：`ready` 的**来源**必须落账 —— 没有它就无法定案
    #     "到底是游戏说的、还是我们兜底猜的"（task-173 的 FAIL 正是这样被掩盖的）。
    #     `"game"` = 真的调用了 `HoeDirt.readyForHarvest()`；`"fields"` = 反射不可用、退回
    #     **与该 IL 逐条等价**的字段判据 ⇒ **这是正常的等价路径，不是 fail-open**；
    #     `null` = 判不了 ⇒【无法判定】。旧账本缺这个键 ⇒【无法判定·旧 Mod】，绝不当通过。
    ("tiles[].readySource", "tile_ready_source",
     "task-176：`ready` 的来源（`\"game\"`/`\"fields\"`/`null`）。`fields` = 反射不可用但字段判据与 "
     "`HoeDirt.readyForHarvest()` 的 IL **逐条等价**（**不是 fail-open**，`ready=true` 对「末阶段未熟」"
     "的格是游戏口径的真相）；只有 `null` 判不了 ⇒【无法判定】；缺键 = 旧 Mod 形态 ⇒"
     "【无法判定·旧 Mod】、绝不当通过；null 占比高 = fail-closed 过头风险（只给 ⚠）"),
    ("tiles[].harvestMethod", "tile_harvest_method",
     "task-176：`harvestMethod` 改由 public 无参 `Crop.GetHarvestMethod()` 提供（`\"Grab\"`/`\"Scythe\"`/"
     "未知值照实写数字；旧写法按字段名读 ⇒ 1.6.15 上恒 null ⇒ 镰刀类作物永远走 `interact`、永远摘不到）；"
     "`Contracts.cs` 用 `JsonIgnore(Never)` ⇒ **该键必须存在**（值可为 null）；缺键 ⇒ 旧 Mod 形态、【无法判定】"),
    ("farm.readyCrops", "farm_readyCrops",
     "task-170 全农场「真能收」计数（与旧 `farm.ripeCrops` 并列）；两者差值 = 看着熟其实不能收"),
    ("day_end.final.farm.readyCrops / ripeCrops", "final_farm_ready_ripe",
     "日级 `final.farm` 白名单里**没有** ripeCrops/readyCrops（brain `longrun.py:1690-1692`）"
     "⇒ 账本层对账缺证据，只能记【无法判定】+ 建议（要 brain 补白名单）"),
    ("exec.acted", "exec_acted",
     "task-170：skill 回执新增 `acted`（`mod\\AgentFarm.Bridge\\Skills.cs:237-241`："
     "`Ok = err == null && acted`）⇒ task-3 那次「回执只保证没抛异常」的坑在 0.7.33 后应可见"),
    ("event:decision", "decision_memory",
     "决策史条数（task-58 的 `Brief.recent_decisions` 注入 = 账本里 `decision` 事件数；每条还补了 "
     "terminal/leftover/unreachable/refused/where 具名田区，**无坐标**）⇒ 头部`决策:`行已给总数；"
     "复盘/教训库是否被注入要看 `review_llm.notes` / `lessons.total`"),
    # task-124 / task-130：review 兜底（决策被换成能落地的意图）+ 弃权 + 换片连发。
    # ⇒ 这些事件是**修复生效的证据**，本身不判红（verify-run3.py 对这四个名字零命中
    # ⇒ 判红会两边反向）；只有可证伪形态才给 ⚠ 警告（burst 连发当天却自称 VERIFIED /
    # 弃权后守卫仍抱怨同批 leftover / 兜底路径抛异常）。缺失 ⇒【无法判定】（缺失 ≠ 0）。
    ("event:review_only_fallback", "review_only_fallback",
     "review 独苗却有活 ⇒ 换成能落地的意图（source=work_spot）或把人带回跨片 leftover"
     "（source=pending_walk）（task-124：plot_tiles|tiles/walked/attempt/reasons/intents）"
     "⇒ **修复生效的证据，不判红**"),
    ("event:review_only_fallback_failed", "review_only_fallback_failed",
     "兜底时出简报抛异常（task-124：source/error）⇒ 防御性事件，正常路径不该出现 ⇒ 只给 ⚠ 警告"),
    ("event:review_only_no_target", "review_only_no_target",
     "确定性计划也拿不出目标 ⇒ 把守卫据以抱怨的 leftover 如实记为「今天放弃」（task-124："
     "pending/tiles/reasons）⇒ 弃权本身不判红；当天 ended_reason 仍说『守卫仍说还有活』⇒ ⚠ 警告"),
    ("event:plot_exhausted_burst", "plot_exhausted_burst",
     "同一秒 ≥5 次换片（task-124：count/zone；brain PLOT_EXHAUSTED_BURST=5）⇒ 按既有有界机制"
     "收尾，不判红；burst 当天仍自称 VERIFIED ⇒ ⚠ 警告（连发=没目标的证据，与 VERIFIED 互斥）"),
    # task-134 A（与 task-124/task-130 同族）：`resume_reevaluate` = 回跨片区 leftover 前清掉任务级
    # `no_target`（走路→空转→再走路的死循环的解药；`verify-run3.py` 对该名零命中 ⇒ 不判红）；
    # `no_progress_burst` = 回片区/换作业区连续无产出触顶 ⇒ 按既有有界机制**诚实收尾**（stuck、
    # leftover 如实保留）⇒ 本身不是失败；只有"当天却自称 VERIFIED"这条可证伪形态给 ⚠。
    ("event:resume_reevaluate", "resume_reevaluate",
     "回跨片区 leftover 之前清掉**任务级** `no_target`（where/cleared；`no_target_global` 不动）"
     "⇒ 死循环被解药的直接证据，**不判红**（缺失 ⇒【无法判定】）"),
    ("event:no_progress_burst", "no_progress_burst",
     "回片区/换作业区**连续**无产出触顶 ⇒ 有界机制诚实收尾（count/source/tiles/reasons；"
     "收尾理由必为 `stuck:`，leftover 如实保留）⇒ **不判红**；当天却自称 VERIFIED ⇒ ⚠ 警告"),
    # task-134 B（分配额口径）：阶段"分下去的格没做完" vs 片区 leftover vs 诚实上限留下的 deferred。
    ("event:stage_shortfall", "stage_shortfall",
     "阶段分下去的格**没做完**（stage/zone/assigned/undone/stopped/leftover）⇒ 本身不是失败事件，"
     "当天的 unmet 由日级 `stage_shortfall_day` + `checks.no_unmet_stages` 说话"),
    ("event:stage_shortfall_day", "stage_shortfall_day",
     "日级：`unmet`=Σ assigned_undone（非诚实上限）、`stages`、`plot_pending`=片区还剩几格、"
     "`stopped_night`（task-134 B）⇒ **分离两个口径**、本身不判红（红由 no_unmet_stages=false 说）"),
    ("event:deferred_tiles", "deferred_tiles",
     "诚实上限（体力用尽/夜里收工/分配额做完后撞 budget）留下的片区待办（tiles/night/by_kind/stages）"
     "⇒ **只作 info、绝不当'没做完还硬说达标'**（brain 明确不进 no_unmet_stages）"),
    ("day_end.assigned_undone", "assigned_undone",
     "当天 Σ 阶段 assigned_undone（分下去没做完的格数，task-134 B；日级 `no_unmet_stages` 看它）"),
    ("day_end.deferred_tiles", "deferred_tiles",
     "当天诚实上限留下的片区待办格数（task-134 B；info、不进 no_unmet_stages）"),
    # task-157（够不着 ⇒ 有界开路，再重试同一格）。两者都**不是失败**：
    # 当天「户外的活有没有干完」由 `checks.watered_outdoor` / `no_unmet_stages` 说话，本工具不重复判。
    ("event:water_far_open", "water_far_open",
     "有界开路：把够不着的干格旁边的挡路格清掉再重试同一格（tile/code/attempt/limit/"
     "cleared_count/cleared ≤8）⇒ **不判红**；开路成功（code=ok）也**不等于**浇上了水"),
    ("event:water_far_blocked", "water_far_blocked",
     "有界开路之后**仍然站不到**这一格 ⇒ 如实记 blocked（tile/cause/attempts/limit/opens/"
     "cleared_count；cause ∈ no_route/unreachable/need_refill/truncated/no_evidence/not_watered）"
     "⇒ **不判红**（如实承认没浇上）"),
    ("event:water_far.opens", "water_far_opens",
     "该格当天开过几次路（task-157 新增字段，与 opened_count 配套 ⇒ 可看出「一直在开路却从没浇上」）"),
    # task-158（体力预算）：不浇水是**因为体力**而不是没活 ⇒ 只做呈现 + 可证伪 ⚠，绝不判红。
    ("event:stamina_budget", "stamina_budget",
     "每天一条体力预算（max/stamina/live_crops/dry/water_reserve/water_cost_est/path_allowance/"
     "capacity/basis/deferred_by_budget/deferred[]）⇒ 解释「为什么今天不浇」"),
    ("event:stamina_budget.basis", "stamina_budget_basis",
     "预算依据：`farm` = 有完整户外农场证据；`conservative` = 证据不足时的保守下界（fail-closed）"),
    ("event:deferred_by_budget", "deferred_by_budget",
     "某任务**只因预算**被延后（task/why/stamina/water_reserve/dry/live_crops/basis）⇒ **不判红**；"
     "但同一批格当天仍被算成浇完 / 自称 crops_watered=true 而 dry>0 ⇒ 账本自相矛盾（⚠ 不进 rc）"),
    ("day_end.stamina_budget", "stamina_budget_day",
     "日级体力预算留痕（dict，task-158；缺字段 ⇒【无法判定】，绝不当作「今天没用预算」）"),
    # task-163（预算延后的活不再算「还有活」+ 容量命中可见）：两个**诚实留痕**事件 + 日级子键。
    # 都不判红、不进 rc；唯一要人工核对的红线是「延后只在体力 ≤ water_reserve **且** 有浇水债时生效」。
    ("event:budget_deferred_tiles", "budget_deferred_tiles",
     "日级/日初：某任务有 count 格被**体力预算**显式延后（task/count/total/targets）⇒ 守卫不再把它们"
     "算作『还有活』；**不判红**，但当天自称 `no_work`+`verified=true` ⇒ ⚠ 人工核对延后前提"),
    ("event:stage_capped_by_capacity", "stage_capped_by_capacity",
     "stage 级：分配额被当天体力预算的容量上限卡住（task/limit/capacity/live_crops/dry/water_reserve）"
     "⇒ 只分配 capacity 格；**不是失败、不判红**，一天每类只发一条"),
    ("day_end.stamina_budget.deferred_tiles", "stamina_budget_deferred_tiles",
     "日级 `{task: n}`：每个任务当天被预算延后的格数（缺 ⇒【无法判定】，缺失 ≠ 0）"),
    ("day_end.stamina_budget.capacity_capped_tasks", "stamina_budget_capacity_capped_tasks",
     "日级 int：当天有几类任务的分配额被容量上限卡住（配 `capped_by_capacity{task:{limit,capacity}}`）"),
    # task-144（dev-coder 在制）：壶空先补水、再把"这一轮没成事的已分配格"原样重跑；以及
    # `stopped==""` 与"分配过却没成事"不再共存（补如实 stop 原因）。两者都**不判红**。
    ("event:refill_retry", "refill_retry",
     "阶段内壶空 ⇒ 补水后把这一轮没成事的格子**原样**重跑（stage/zone/ok/refills_today/limit/"
     "tiles/targets）⇒ **不是失败**；`ok=true` 当天却没有成功 `refill`、或 `tiles=0` 空转 ⇒ ⚠ 警告"),
    ("event:stage_stop_named", "stage_stop_named",
     "阶段自然走完（`stopped==\"\"`）却仍有分配未成事的格 ⇒ 补**如实** stop 原因（cause∈need_refill/"
     "unreachable/no_seed/incomplete；assigned/assigned_undone/tiles/codes）⇒ **不判红**；"
     "cause 缺失/未知、`assigned_undone<=0`、或有过失却 `codes` 全空 ⇒ ⚠ 警告"),
    # task-144 增量（dev-coder `2438cae` 定稿）：阶段内补水的次数与上界（`STAGE_REFILL_MAX`）。
    ("event:refill_retry.stage_refills", "refill_retry_stage_refills",
     "该阶段已为「壶空」补过几次水（task-144 增量；同日/阶段上界见 `stage_limit`；"
     "`stage_refills > stage_limit` ⇒ ⚠ 警告、**不进 rc**）"),
    ("event:refill_retry.stage_limit", "refill_retry_stage_limit",
     "该阶段补水上界（`STAGE_REFILL_MAX`，brain 现值 2；日级另有 `limit` = `max_refills_per_day` 兜底）"),
    # task-132（task-123 在制）：量力而行买种子 —— 钱只够买 `bought < wanted` 时照样买，**不是失败**。
    # 只有"自称买满却 count<wanted 且没有对应 buy_partial"或"同日既有 buy_partial 又有 cannot_afford"
    # 这类**可证伪**形态才给 ⚠ 警告（verify-run3.py 对 `buy_partial` 零命中 ⇒ 判红会两边反向）。
    ("event:buy_partial", "buy_partial",
     "钱只够买一部分 ⇒ 量力而行买下这些（task-123：item/bought/wanted/price/price_shelf/price_cfg/"
     "money/source/ok/code）⇒ **不是失败**，不进 failed；缺 `wanted` 字段的旧账本 ⇒【无法判定】"),
    ("event:buy_partial.bought", "buy_partial_bought",
     "实际买到的手数（task-123）；与 `wanted` 一起才能算出还缺多少（缺失 ≠ 0）"),
    # task-20 / task-164（工具门槛）：clump 工具等级/种类不够（或观测判不出）⇒ **动手之前就拦下**
    # （0 次 use_tool、不白烧体力）。逐格 `blocked_by_tool`（tile/action/stage/zone/kind/**need**/
    # min_level/reason/note）+ 日级汇总 `blocked_by_tool_summary`（count/tiles/kinds/tools/note）。
    ("event:blocked_by_tool", "blocked_by_tool",
     "逐格：工具不够格（或 `toolOk` 判不出 ⇒ fail-closed 不挥）⇒ 当天封格、**0 次 use_tool**；"
     "`need` 是「<tool>≥<等级>」文本（**不是** `tool` 字段，以账本实测为准）、`min_level` 可缺 ⇒ 只提示"),
    ("event:blocked_by_tool.kind", "blocked_by_tool_kind",
     "被封格的 kind（`clump` 一族；判不出时写「未知」⇒ 不许替观测断言树/桩/大石）"),
    ("event:blocked_by_tool.need", "blocked_by_tool_need",
     "所需工具与等级文本（形如 `pickaxe≥2`；缺字段 ⇒【无法判定】该格到底要什么工具）"),
    ("event:blocked_by_tool.min_level", "blocked_by_tool_min_level",
     "所需工具最低等级（int；缺 ⇒【无法判定】，绝不默认 0 级）"),
    ("event:blocked_by_tool_summary", "blocked_by_tool_summary",
     "日级汇总（count/tiles ≤6/kinds/tools/note）⇒ 这些格**不算活、不进守卫理由**（否则一块"
     "暂时敲不动的巨石会让人永远收不了工）；本工具**不判红、不进 rc**"),
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
    # task-133（run9b 的 need_refill 病）：窗口外浇水前壶空 ⇒ **先补水再浇**（一天有界），
    # 壶空是前置条件、**不是「够不着」**。这条是"试过补水"的直接证据，本身不是失败。
    "water_far_refill": "water_far_refills",
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
    #     当天记 blocked、**次日重试**，日级豁免有上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)
    #     （tools\verify-run3.py:254-258/415-448 同口径：越界才是 problem）。
    "unreachable": "unreachable",
    "unreachable_stage": "unreachable_stages",
    "unreachable_summary": "unreachable_summaries",
    # --- task-63/task-66：`till` 被**游戏拒绝**（tool_ineffective/precondition_failed）的三级留痕。
    #     政策：不算当天硬失败、当天封格、**次日重试**；日级豁免有上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)；
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
    # task-55/task-91：**盈余材料换种子钱**（`_sell_surplus_for_seeds`，brain/agentfarm/longrun.py:1680-1740）。
    #     `sell`/`sell_failed` 逐叠出货（task-42 已在桶里）；`surplus_sell` = 本轮汇总
    #     （sold 件数 / ok_count 叠数 / below_keep / trigger{money,threshold,emptyDirt}；
    #      **钱要等下一次 NewDay 才结算 ⇒ 当天 money 不变是设计，绝不判红**）；
    #     `surplus_sell_skip` = 想卖但没有材料超过保留线（带 short 缺口）⇒ **不是失败**。
    # task-172（dev task-170 `d88498d`）：**收获如实放弃**（试满 MAX_TILE_ATTEMPTS ⇒ 当天不再回头）。
    #     brain 在 :4065 写 `tile/attempts/limit/codes/note`；目标池与守卫把它扣掉，
    #     但 `_leftover("harvest")` **不扣** ⇒ **如实放弃不是豁免**、不进任何豁免分子。
    "harvest_gave_up": "harvest_gave_ups",
    "surplus_sell": "surplus_sells",
    "surplus_sell_skip": "surplus_sell_skips",
    # task-84：日级死苗汇总（`dead_crops_summary`，只在 `dead_crops>0` 且状态 ok 时写一条）。
    "dead_crops_summary": "dead_crops_summaries",
    # task-102（`9b09735`）：**背包空格死锁**的三个新事件（run8 day 2/12/13）—— 都不是失败：
    #     `buy_no_space` = 回执 `no_space`（`no_inventory_space`）⇒ 当天不再重试 buy；
    #     `slept_without_work` = 当天 0 农场动作又有活 ⇒ **拒绝睡觉、当天不推进**（守卫生效的
    #     证据，不是"睡眠失败"；那天会以 needs_review/no_day_progress 如实停住）；
    #     `modal_dismiss_failed` = 关模态时桥报错（`verify-run3` 不判它 ⇒ 本工具只点名次数，
    #     不判红，免得两边反向）。
    "buy_no_space": "buy_no_spaces",
    "slept_without_work": "slept_without_works",
    "modal_dismiss_failed": "modal_dismiss_failures",
    # task-104（run8 day 12 的 `water_far` 前置）：窗口外有干作物但**人不在户外农场** ⇒ 不扣该格当日
    # 额度、不进 `given_up`，只记一条（`reason=not_on_farm`）⇒ **不是失败**。
    "water_far_skipped": "water_far_skips",
    # task-58/59/82（Lead m05325）：收工 LLM 复盘 + 跨日教训库。**"模型没学到东西"不是失败**
    # （空 notes / 空教训库只记信息）——只有两条完整性红线进来看：声称成功却一条 notes 都没有、
    # 教训库条数超上限 / 文件损坏。复盘失败（`review_llm_failed`）与教训库读写失败（load/save）
    # 按 brain 的"失败无害"契约只记信息（睡觉与跨日照常）。
    "review_llm": "review_llms",
    "review_llm_failed": "review_llm_failures",
    "lessons": "lessons_events",
    "lessons_load_failed": "lessons_load_failures",
    "lessons_save_failed": "lessons_save_failures",
    # task-114 F1：教训库 schema 校验丢条留痕 ⇒ **拒收本身不判红**（外部篡改/损坏时拒收是正确行为），
    # 只有「dropped>0 且 kept==0 连续 ≥2 天」给 `warn:` 可视行（不判红、不进 rc）
    "lessons_rejected": "lessons_rejections",
    # task-124（`08a2ae0`）/ task-130：**review 兜底与换片连发** —— 不是失败，是修复生效的证据：
    #     `review_only_fallback` = review 独苗却有活 ⇒ 换成能落地的意图（work_spot）或把人带回
    #     跨片 leftover（pending_walk）；`review_only_no_target` = 兜底也拿不出目标 ⇒ 把守卫抱怨的
    #     leftover 如实记为"今天放弃"（次日重试、不碰判定字段）；`plot_exhausted_burst` = 同一秒
    #     ≥5 次换片 ⇒ 按既有有界机制收尾；`review_only_fallback_failed` = 防御性（抛异常）。
    #     `verify-run3.py` 对这四个名字零命中 ⇒ 本工具**不判红**，只给可证伪形态的 ⚠ 警告。
    "review_only_fallback": "review_only_fallbacks",
    "review_only_fallback_failed": "review_only_fallback_failures",
    "review_only_no_target": "review_only_no_targets",
    "plot_exhausted_burst": "plot_exhausted_bursts",
    # task-134 A（同族）：`resume_reevaluate` = 回跨片 leftover 前清任务级 no_target（死循环解药）；
    # `no_progress_burst` = 连续无产出触顶 ⇒ 有界机制诚实收尾（stuck）。两者都**不是失败**，
    # `verify-run3.py` 对这两个名字零命中 ⇒ 本工具不判红，只给可证伪形态的 ⚠ 警告。
    "resume_reevaluate": "resume_reevaluates",
    "no_progress_burst": "no_progress_bursts",
    # task-134 B（分配额口径）：阶段 assigned_undone / 日级 shortfall / 诚实上限 deferred_tiles。
    # 三者都不是失败（红由 `checks.no_unmet_stages=false` 说话；deferred 明确不进该检查）。
    "stage_shortfall": "stage_shortfalls",
    "stage_shortfall_day": "stage_shortfall_days",
    "deferred_tiles": "deferred_tiles",
    # task-157（够不着 ⇒ 有界开路 water_far_open / 开路后仍站不到 water_far_blocked）与
    # task-158（体力预算 stamina_budget / 只因预算被延后 deferred_by_budget）。四个都不是失败；
    # `tools/verify-run3.py` 对这四个名字零命中 ⇒ 判红会两边反向 ⇒ 本工具只做呈现 + 可证伪 ⚠；
    # 当天达不达标一律由 `checks.watered_outdoor` / `checks.no_unmet_stages` 说话。
    "water_far_open": "water_far_opens",
    "water_far_blocked": "water_far_blocks",
    "stamina_budget": "stamina_budgets",
    "deferred_by_budget": "deferred_by_budgets",
    # task-163：预算延后的活不再算「还有活」（`budget_deferred_tiles`，日级/日初，`{task: n}` 语义）
    # + 容量上限命中可见（`stage_capped_by_capacity`，stage 级）。都是**诚实留痕、不判红、不进 rc**
    # （`tools/verify-run3.py` 对这两名零命中 ⇒ 判红会两边反向）；唯一 ⚠ 是「当天有延后却自称
    # no_work+VERIFIED ⇒ 核对延后前提：体力 ≤ water_reserve **且** 有浇水债」。
    "budget_deferred_tiles": "budget_deferred_tiles_events",
    "stage_capped_by_capacity": "stage_capped_by_capacities",
    # task-20 / task-164（工具门槛）：clump 工具等级/种类不够（或判不出）⇒ 当天封格、0 次 use_tool。
    # 逐格 `blocked_by_tool` + 日级 `blocked_by_tool_summary`。**诚实跳过、不判红、不进 rc**
    # （`tools/verify-run3.py` 对这两名零命中 ⇒ 判红会两边反向），只提示人工核对。
    "blocked_by_tool": "blocked_by_tools",
    "blocked_by_tool_summary": "blocked_by_tool_summaries",
    # task-144（dev-coder 在制）：阶段内壶空 ⇒ 补水后把"这一轮没成事的已分配格"**原样**重跑
    # （`refill_retry`，不再重算窗口把那几格丢掉）；阶段自然走完（`stopped==""`）却仍有分配未成事的
    # 格 ⇒ 补一个**如实** stop 原因的留痕（`stage_stop_named`）。两者都是**修复生效的证据**、不是失败；
    # `verify-run3.py` 对这两个名字零命中 ⇒ 本工具不判红，只给可证伪形态的 ⚠ 警告。
    "refill_retry": "refill_retries",
    "stage_stop_named": "stage_stop_names",
    # task-132（task-123 在制）：量力而行买种子 —— 钱只够买一半照样买（`buy_partial`），
    # **不是失败**（不进 failed、不判红；`tools\verify-run3.py` 对该名零命中），只作信息项 +
    # 两条可证伪 ⚠ 警告（自称买满却买少且无留痕 / 同日 `buy_partial` 与 `cannot_afford` 同时出现）。
    "buy_partial": "buy_partials",
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
    # task-55/task-91：盈余材料换种子钱（钱次日 NewDay 结算；skips/below_keep 都不是失败）
    "surplus_sells", "surplus_sell_skips",
    # task-172：收获如实放弃（不是豁免分子；一眼看出"今天放了 N 格没收"）
    "harvest_gave_ups",
    # task-84：死苗汇总（一眼看出"还有 N 格枯死、其中 M 格没浇、今天认输 K 格"）
    "dead_crops_summaries",
    # task-102：背包空格死锁（买不到不是失败；0 动作拒绝睡觉是有界停住，不是睡眠失败）
    "buy_no_spaces", "slept_without_works", "modal_dismiss_failures",
    # task-104：窗口外浇水被人不在农场挡下（不扣额度、不认输 ⇒ 不是失败）
    "water_far_skips",
    # task-134 A：回跨片区 leftover 前清任务级 no_target（死循环解药）+ 连续无产出触顶诚实收尾
    "resume_reevaluates", "no_progress_bursts",
    # task-134 B：分配额口径（阶段没做完 / 日级 unmet / 诚实上限留下的 deferred，均 info）
    "stage_shortfalls", "stage_shortfall_days", "deferred_tiles",
    # task-133：窗口外浇水前补水（壶空=前置条件，不是够不着；补水没成才是那格浇不上的因由）
    "water_far_refills",
    # task-111：LLM 复盘 / 教训库（本日 notes、复盘失败、教训库新增/淘汰、读写失败）
    "review_llms", "review_llm_failures", "lessons_events",
    "lessons_load_failures", "lessons_save_failures",
    # task-114：教训库拒收留痕（拒收本身不是失败；连续全丢才给 warn）
    "lessons_rejections",
    # task-124/task-130：review 兜底（work_spot/pending_walk）+ 弃权留痕 + 换片连发
    "review_only_fallbacks", "review_only_fallback_failures",
    "review_only_no_targets", "plot_exhausted_bursts",
    # task-132（task-123 在制）：量力而行买种子（买一半不是失败；只给可证伪形态的 ⚠ 警告）
    "buy_partials",
    # task-144（dev-coder 在制）：壶空先补水再"原样重跑"这一轮没成事的格（refill_retries）
    # + 阶段自然走完却仍有分配未成事的格 ⇒ 补如实 stop 原因（stage_stop_names）；均不判红
    "refill_retries", "stage_stop_names",
    # task-157：够不着 ⇒ 有界开路（开路成功 ≠ 浇上水）后重试；开路后仍站不到 ⇒ 如实 blocked
    "water_far_opens", "water_far_blocks",
    # task-158：体力预算（每天一条 + 只因预算被延后；都不是失败，只解释"为什么今天不浇"）
    "stamina_budgets", "deferred_by_budgets",
    "budget_deferred_tiles_events", "stage_capped_by_capacities",
    # task-20 / task-164：工具门槛封格（逐格 + 日级汇总；诚实跳过、不进守卫理由、不判红）
    "blocked_by_tools", "blocked_by_tool_summaries",
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


#: task-88（Lead m04300）：窗口口径（与 `tools\verify-run3.py` 的"尾部窗口"同义）。
#: * 窗口 = 账本最后 `--window N` 天（默认 3）。窗口**内**的日级红照常 fatal；
#:   窗口**外**的日级红降级为 `history_problems`（**逐条列出、不进退出码**）。
#: * `连续 VERIFIED 天数 < N` ⇒ 本跑没达标，**不降级**（历史问题不能替它开脱），维持原判。
#: * 无日期归属的**全局红**（finish 自述不一致 / 账目自相矛盾 / journal 损坏）**永远 fatal**。
#: * `--window 0` = 关闭窗口（task-88 之前的旧行为）。
GLOBAL_RED_SUBJECTS = (
    "wasted:finish_incoherent",
    "wasted:finish_vs_days",
    "missed:stage_account",
    # task-111：复盘/教训库的三条完整性红 —— 不能被窗口降级（旧账本升级后也一眼可见）
    "missed:review_llm_without_notes",
    "missed:lessons_over_limit",
    "missed:lessons_load_failed",
)
#: task-88：事件级"瞬间态"class-1 —— 当天 `day_end.verified=true` 且 `checks.no_unmet_stages=true`
#: ⇒ 降级为 info（逐条列出并标"已结清"，不进 rc）。理由：这些事件记录的是**某一轮的瞬间状态**
#: （阶段这一刻没目标 / 意图被取消），当天随后结清时 verify-run3 的日级口径不会判它问题。
SETTLED_SUBJECT_PREFIXES = (
    "missed:cancel:",
    "missed:stage_no_target",
    "missed:stage_exhausted",
    "missed:plot_exhausted",
)


def is_settleable(item):
    """这条 finding 是否属于"瞬间态 class-1"（可能被同日结清降级）。"""
    subject = str((item or {}).get("subject") or "")
    return any(subject.startswith(prefix) for prefix in SETTLED_SUBJECT_PREFIXES)


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


def llm_review_findings(lr):
    """task-111：LLM 收工复盘 / 教训库的**三条完整性红**（其余一律信息项）。

    * `review_llm` 声称成功却一条 notes 都没有 ⇒ 红（声称学到东西却什么都没写）；
    * 教训库条数超上限（brain `LESSONS_MAX = 20`；事件 `total` 或落盘文件条数）⇒ 红；
    * 教训库读不了/文件损坏（`lessons_load_failed` 或落盘 JSON 解析失败）⇒ 红。
    复盘失败（`review_llm_failed`）、教训库写失败（`lessons_save_failed`）、notes 为空列表、
    空库 / 本日 0 新增 ⇒ **都不判红**（与 brain 的"失败无害"契约一致）。
    """
    lr = lr or {}
    out = []
    for ln in lr.get("without_notes_lines") or []:
        out.append(finding(
            ln, "review_llm",
            f"复盘声称成功却一条 notes 都没有（notes={lr.get('notes_count')} 条）"
            "⇒ 声称学到了东西却什么都没写（task-111：只有'没学到'不算失败，'假称学到'才算）",
            hint="看 review_llm 的 rejected/truncated；模型输出被拒或被截断时 notes 会是空 —— "
                 "要么修提示词，要么让调用如实记成 review_llm_failed",
            subject="missed:review_llm_without_notes"))
    for ln in lr.get("over_limit_lines") or []:
        out.append(finding(
            ln, "lessons",
            f"教训库条数超上限：total={lr.get('lessons_total')} / 落盘文件 "
            f"{lr.get('file_count')} 条 > {lr.get('lessons_max')}（brain `LESSONS_MAX`）"
            "⇒ 淘汰逻辑没生效，库会无限膨胀（提示词预算被吃光）",
            hint="brain/agentfarm/planner.py: prune_lessons(max_lessons=LESSONS_MAX)；"
                 "本工具直接读 `<journal>-lessons.json`（路径同 brain 的推导约定，不加命令行开关）",
            subject="missed:lessons_over_limit"))
    if lr.get("load_failed"):
        errs = "；".join(str(e) for e in (lr.get("load_errors") or [])[:3])
        out.append(finding(
            (lr.get("load_failed_lines") or [None])[0], "lessons_load_failed",
            f"教训库读不了 ×{lr.get('load_failed')}（error={errs}）⇒ 教训库不可信："
            "brain 的'失败无害'只保证不中断跑批，不保证账目可信 ⇒ 必须人工看这个文件",
            hint="路径 = `<journal>-lessons.json`；`read_failed:` = JSON 坏、`not_a_list` = 结构坏、"
                 "`bad_path:` = 路径用不了（task-111 判红）",
            subject="missed:lessons_load_failed"))
    if lr.get("file_status") == "corrupt":
        out.append(finding(
            None, "lessons_file",
            f"教训库文件损坏（{lr.get('file_path')}：{lr.get('file_error')}）"
            "⇒ 本工具按同一路径推导读它，读不动 ⇒ 教训库不可信（task-111 判红）",
            hint="brain 写盘是 tmp+replace（planner.save_lessons_file），出现损坏说明被外部改过/截断过",
            subject="missed:lessons_load_failed"))
    return out


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


def dry_dead_check(ev):
    """task-84：死苗/放弃格字段的 fail-closed 判定（与 `tools/verify-run3.py:793-818` 同向）。

    brain 侧日级字段（`brain/agentfarm/longrun.py:351-355` 声明、`:424-428` as_dict、
    `:3390-3406` 汇总/留痕）：`dead_crops` + `dead_crops_status`（Mod `farm.deadCrops`）、
    `dry_dead` + `dry_dead_status`（Mod `farm.dryDeadCrops`，枯死**且没浇**）、
    `gave_up_tiles`（当天认输的窗口外干格坐标）。

    口径：
      * 字段缺失（task-84 之前的旧账本）⇒ `"missing"`：只作【无法判定】，**既不算通过也不算失败**；
      * `dry_dead` 不是整数 ⇒ `"bad"`（账目不可信 ⇒ 判红）；
      * `dry_dead > 0` 且 `ended_reason` 以 `no_work` 开头 ⇒ `"no_work_uncleared"`（判红）：
        "还有枯死作物没清却判今天没活" = 拿死苗当没活的借口（用户 m11003 第 3 条抱怨的形态），
        正确归宿是 `clear_dead`，够不着要如实 `stuck`/`gave_up_dry`。
      * 其余 ⇒ `"ok"`。

    返回 `(status, dry_dead, gave_up_tiles, note)`。
    """
    if not any(k in ev for k in ("dead_crops", "dry_dead", "gave_up_tiles")):
        return ("missing", None, None, "")
    gave_up = ev.get("gave_up_tiles")
    raw = ev.get("dry_dead")
    if raw is None:
        return ("missing", None, gave_up, "")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return ("bad", None, gave_up,
                f"day_end.dry_dead 不是整数（{raw!r}）⇒ 账目不可信")
    dd = int(raw)
    if dd > 0 and str(ev.get("ended_reason") or "").startswith("no_work"):
        return ("no_work_uncleared", dd, gave_up,
                f"ended_reason 以 no_work 开头，但 day_end.dry_dead={dd}"
                "（还有枯死作物没清却判『今天没活』⇒ 死苗被当成没活的借口；"
                "应走 `clear_dead`，够不着应如实 `stuck`/`gave_up_dry`，见 task-84）")
    return ("ok", dd, gave_up, "")


def bound_self_check(*, basis_field, attempted, encircled, ledger_bound):
    """task-78 / task-80：上界基数自算 + "**绝不采信比自算更大的账本上界**"。

    公式与 brain（`longrun.py:3082`）和 `tools\\verify-run3.py`（`2ce830b`）**同式**：
    `bound = max(5, floor(0.2 × (attempted − encircled)))` —— 被围住的格既不是"走不到"也不是
    "干了没成"，不该为豁免额度做贡献；deputy 的伪造账本 V5 正是拿 `encircled` 把旧分母 `attempted`
    抬到 800 ⇒ 20% 上界 200 ⇒ 200 格真不可达被豁免、当天 exit 0。

    返回 `(status, basis_self, bound_self, note)`：
      `"ok"`（账本不更大）；`"inflated"`（账本基数或上界比自算大 ⇒ **判红**）；
      `"no_bound"`（账本没写上界 ⇒ 只报自算，不判红也不当通过）；
      `"undecidable"`（账本没写 `attempted` ⇒ 无法自算；缺失 ≠ 通过）。
    """
    if isinstance(attempted, bool) or not isinstance(attempted, (int, float)):
        return "undecidable", None, None, "账本没写 attempted ⇒ 无法自算上界基数"
    enc = encircled if (isinstance(encircled, (int, float))
                        and not isinstance(encircled, bool)) else 0
    basis_self = max(0, int(attempted) - int(enc))
    bound_self = max(5, int(0.2 * basis_self))
    if isinstance(basis_field, (int, float)) and not isinstance(basis_field, bool):
        if int(basis_field) > int(attempted):
            return ("inflated", basis_self, bound_self,
                    f"账本 bound_basis={int(basis_field)} > attempted={int(attempted)}"
                    "（抬高基数就能放宽 20% 上界 ⇒ 账目不可信）")
        if int(basis_field) > basis_self:
            return ("inflated", basis_self, bound_self,
                    f"账本 bound_basis={int(basis_field)} > 自算={basis_self}"
                    f"（attempted={int(attempted)} − encircled={int(enc)}）⇒ 基数被放宽")
    if isinstance(ledger_bound, bool) or not isinstance(ledger_bound, (int, float)):
        return "no_bound", basis_self, bound_self, "账本没写上界 ⇒ 只报自算"
    if int(ledger_bound) > bound_self:
        return ("inflated", basis_self, bound_self,
                f"账本上界 {int(ledger_bound)} > 自算上界 {bound_self}"
                f"（bound_basis 自算={basis_self} = attempted {int(attempted)} − encircled {int(enc)}）")
    return "ok", basis_self, bound_self, ""


def _bound_basis_text(env, side):
    """task-80：把上界**基数**口径写进头部；run6 等旧账本没有 `bound_basis` ⇒ 只报缺失。

    缺失**不许当 0、不许当通过**：`attempted` 也缺 ⇒ 【无法判定】；账本数比自算大 ⇒ 标红口径。
    """
    led = env.get("bound_basis_ledger")
    status = env.get(f"{side}_bound_status")
    basis_self = env.get(f"{side}_basis_self")
    bound_self = env.get(f"{side}_bound_self")
    if led is None:
        if status == "undecidable":
            return ("；bound_basis=<缺失>（无法自算：账本没写 attempted/bound_basis"
                    " ⇒ 【无法判定】，缺失 ≠ 通过）")
        return (f"；bound_basis=<缺失>（自算基数 {basis_self}、上界 {bound_self}，缺失 ≠ 通过）")
    txt = f"；bound_basis={led}（自算基数 {basis_self}、上界 {bound_self}）"
    if status == "inflated":
        txt += (f"  ⚠ {env.get(f'{side}_bound_note') or '账本上界比自算大'}"
                " ⇒ 0 类红（missed:bound_inflated）")
    return txt


def _settle(item, settled):
    """task-88：给"瞬间态 class-1"finding 打 `settled` 标记（同日结清 ⇒ info，不进 rc）。"""
    if settled:
        item["settled"] = True
        item["summary"] = (str(item.get("summary") or "")
                           + "（已结清：当天 VERIFIED 且 no_unmet_stages=true ⇒ 只作 info）")
    return item


def cat_missed(sessions, top):
    out = []
    for sess in sessions:
        # task-88：本会话是否"瞬间态已结清"（当天 VERIFIED 且 checks.no_unmet_stages=true）
        # ⇒ 1a/1b 这类**事件级**红降级为 info（仍逐条列出、不进 rc）；
        #   日级红与全局红不受影响。
        _last_end = as_dict(sess["day_ends"][-1][1]) if sess["day_ends"] else {}
        settled = (_last_end.get("verified") is True
                   and as_dict(_last_end.get("checks")).get("no_unmet_stages") is True)
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
                item = finding(
                    lineno,
                    "intent_verdict",
                    f"cancel：{task} @ zone={ev.get('zone')} —— {verdict.get('reason')}{note}",
                    hint="cancel 的依据是'看得见却没有一格可动目标'；若该任务其实有事可做，"
                         "问题在 _verify_intents 的观测范围（OBSERVE_REACH）或目标口径",
                    subject=f"missed:cancel:{task}",
                )
                out.append(_settle(item, settled and is_settleable(item)))
        # 1b: 阶段没目标 / 换片，且收工时还有待办
        for key, hint in (
            ("no_targets", "该阶段当天没有目标；若收工时该阶段仍有待办，就是'该做没做'"),
            ("exhausted", "阶段被记为'没有目标'"),
            ("plot_exhausted", "片区没目标 ⇒ 换片地；注意这可能掩盖'其实还有活'"),
        ):
            for lineno, ev in sess[key]:
                leftover = ev.get("leftover", ev.get("recovered"))
                item = finding(
                    lineno,
                    ev.get("event"),
                    f"{ev.get('event')}：stage={ev.get('stage') or '-'} zone={ev.get('zone')} "
                    f"leftover/recovered={leftover} note={str(ev.get('note') or '')[:60]}",
                    hint=hint,
                    subject=f"missed:{ev.get('event')}",
                )
                out.append(_settle(item, settled and is_settleable(item)))
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
        # 1h: task-78/task-80 —— 上界自检：**绝不采信比自算更大的账本上界**（deputy 的伪造账本 V5
        #     用 `encircled` 把旧分母 `attempted` 抬到 800 ⇒ 20% 上界 200 ⇒ 200 格真不可达被豁免、
        #     exit 0）。verify-run3.py 同判 problem（`2ce830b`）；这里判红并点名两侧数字。
        for lineno, ev in sess["day_ends"]:
            _ev = as_dict(ev)
            for _side, _cnt_key, _bound_key in (("不可达", "unreachable", "unreachable_bound"),
                                                ("被拒绝", "refused", "refused_bound")):
                status, bself, bound_self, note = bound_self_check(
                    basis_field=_ev.get("bound_basis"),
                    attempted=_ev.get("attempted"),
                    encircled=_ev.get("encircled"),
                    ledger_bound=_ev.get(_bound_key),
                )
                if status != "inflated":
                    continue
                out.append(
                    finding(
                        lineno, "day_end",
                        f"上界自检（{_side}）账目不可信：{note} ⇒ 绝不采信账本上界，"
                        f"以自算 bound_basis={bself}、上界={bound_self} 为准",
                        hint="task-78：上界基数 = attempted − encircled（**被围住的格不参与起界**）；"
                             "基数/上界比自算大 ⇒ 可能把真失败洗成豁免（deputy V5 打法）；"
                             "verify-run3.py 同判 problem",
                        subject="missed:bound_inflated",
                    )
                )
        # 1i: task-84（死苗不浇水）—— 两条红 + 一条警告：
        #   ① `dry_dead > 0` 且 `ended_reason` 以 `no_work` 开头 ⇒ 红（死苗不许当"今天没活"的借口；
        #      verify-run3.py:803-808 同判 problem）；
        #   ② `dry_dead` 不是整数 ⇒ 红（账目不可信；verify-run3.py:802 同判 problem）；
        #   ③ `gave_up_tiles` 非空却自称 `verified=true` ⇒ **只作警告，不判红**（Lead m04997）：
        #      真洗白通道已被 verify-run3 的「`watered_outdoor=true` 但 `final_water.dry>0` ⇒ 账本
        #      自相矛盾」闸门堵住（干格还在 ⇒ 要么 verified=false，要么矛盾判红）；剩下能走到这种
        #      形态的是"认输格当天后来被别的动作解决了、`dry==0`" ⇒ 判红就是假红。警告仍在头部
        #      `⚠` 与建议 0m 里可见（`report["dead_crops"]["verified_with_gave_up"]`）。
        # 字段缺失（旧账本）⇒ 不在这里判红，只由 FIELD_PROBES 记【无法判定】。
        for lineno, ev in sess["day_ends"]:
            _ev = as_dict(ev)
            _status, _dd, _gave_up, _note = dry_dead_check(_ev)
            if _status == "no_work_uncleared":
                out.append(
                    finding(
                        lineno, "day_end",
                        f"死苗没清却判没活：{_note}（ended_by={_ev.get('ended_by')}）",
                        hint="死苗不浇水（dry 只算活苗）：`clear_dead` 应在 water 之前；够不着要如实 "
                             "`stuck`/`gave_up_dry`。run7 曾追着一株够不着的死苗烧掉两个整天"
                             "（用户 m11003 第 3 条）；verify-run3.py:803-808 同判 problem",
                        subject="missed:dry_dead_uncleared",
                    )
                )
            elif _status == "bad":
                out.append(
                    finding(
                        lineno, "day_end", f"死苗账目不可信：{_note}",
                        hint="task-84：`dry_dead` 必须是整数；不是整数说明账本/字段被改坏，"
                             "verify-run3.py:802 同判 problem",
                        subject="missed:dry_dead_bad_field",
                    )
                )
            elif _status == "ok" and as_list(_gave_up) and _ev.get("verified") is True:
                # task-84 ③ 经 Lead m04997 裁定：**只作警告、不判红**（假红比漏报更伤工具信任）。
                # 可见性由 `report["dead_crops"]["verified_with_gave_up"]` → 头部 ⚠ + 建议 0m 保证。
                pass
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
        # 政策：**不计当天硬失败**、当天记 blocked、**次日重试**；日级豁免有上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)。
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
                    hint="task-52：当天记 blocked、次日重试；豁免上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)，"
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
        # 政策与 task-52 同形但**独立起界**（refused_bound = max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)）：两套豁免各自扣减、
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
    window = as_int(report.get("window_days"), requested) or requested
    recorded = len(report.get("days") or [])
    days = as_int(finish.get("days"), requested)
    verified_days = as_int(report.get("verified_days"))
    # task-88：finish 自洽的达标目标 = **目标窗口**（`--window N`，默认 3），不是账本自己的
    # `finish.days`（那是自述字段）。窗口不可能大于账本记录的天数 ⇒ 取 `min(窗口, 记录天数)`。
    # `streak >= 目标` ⇒ 不报；否则报。
    target = min(window, recorded) if (window > 0 and recorded) else days
    if target > 0 and (code == 0) != (streak >= target):
        out.append(
            finding(
                line, "finish",
                f"finish 自身不自洽：code={code} 与 verified_streak={streak}/目标窗口={target} 不符"
                + (f"（finish 自述 days={days}）" if days != target else ""),
                hint="finish 是自述字段：code==0 必须等价于连续 VERIFIED 天数达到**目标窗口**"
                     "（task-88；verify-run3.py 按它的 --days 同口径）",
                subject="wasted:finish_incoherent",
            )
        )
    elif target > 0 and (code == 0) != (verified_days >= target):
        out.append(
            finding(
                line, "finish",
                f"finish 自述 code={code}，但账本正文里 verified 天数只有 {verified_days}/{target}"
                "（应同向）",
                hint="自述与正文必须同向（verify-run3.py 盲区 B1）；自述达标而正文天数不达标 "
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
    # 0i-2) task-88 ④：`seed_gate` 钱不够分叉 —— **不是任务失败**（不要读成失败）
    if se.get("afford_blocked"):
        advice.append({
            "text": f"种子经济（信息项，**不是任务失败**）：seed_gate {se.get('seed_gate')} 次里"
                    f"有 {se.get('afford_blocked')} 次是 money={se.get('seed_gate_money')} < "
                    f"seed_price={se.get('seed_gate_price')}（或背包 0 种子）⇒ 当天没发起购买。"
                    "这是经济约束，不是购买任务失败；run7 的 5 次 seed_gate 都是这个形态"
                    "（建议 3 的 brain 半边已进 task-84）",
            "lines": se.get("afford_blocked_lines", []),
        })
    # 0i-3) task-91 ③：卖了盈余材料但**次日** buy 仍 0 ⇒ 只列两个候选，**不下结论**
    sl = report.get("sell") or {}
    if sl.get("sold_days_with_no_buy_next"):
        _dn = "、".join(f"{x['day']}(L{x['line']})" for x in sl["sold_days_with_no_buy_next"][:6])
        advice.append({
            "text": f"盈余材料卖出后次日仍没买种子（{len(sl['sold_days_with_no_buy_next'])} 天：{_dn}）"
                    "：候选只有两个 —— ①**钱没到账**（出货的钱要等下一次 `NewDay` 由游戏结算；"
                    "`surplus_sell.note` 已写明「当天 money 不变是正常的」）；"
                    "②**货架没有当季种子**（看 `no_seed_for_sale` 的 offers 与 `cannot_afford` 的缺口）。"
                    "本工具只给这两个候选与证据行，**不下结论**。",
            "lines": [x["line"] for x in sl["sold_days_with_no_buy_next"] if x.get("line") is not None],
        })
    # 0m) task-84：死苗没清却判 no_work / 放弃格非空却自称 VERIFIED / dry_dead 非整数
    dci = report.get("dead_crops") or {}
    if dci.get("no_work_uncleared") or dci.get("verified_with_gave_up") or dci.get("bad_fields"):
        _parts = []
        if dci.get("no_work_uncleared"):
            _parts.append(
                f"有没清的死苗却判 no_work ×{len(dci['no_work_uncleared'])}"
                f"（行 {dci['no_work_uncleared'][:6]}）：死苗不浇水、也不许当『今天没活』的借口 —— "
                "`clear_dead` 要排在 water 之前；够不着应如实 `stuck`/`gave_up_dry`（task-84 口径）")
        if dci.get("verified_with_gave_up"):
            _parts.append(
                f"放弃格非空却自称 VERIFIED ×{len(dci['verified_with_gave_up'])}"
                f"（行 {dci['verified_with_gave_up'][:6]}）：**只作警告、不判红**（Lead m04997）—— "
                "真洗白通道已被 verify-run3 的「`watered_outdoor=true` 但 `final_water.dry>0` ⇒ "
                "账本自相矛盾」堵住；认输格当天后来被解决、`dry==0` 时判红就是假红，"
                "所以这里只点名供人工复核")
        if dci.get("bad_fields"):
            _parts.append(f"dry_dead 不是整数（账目不可信，行 {dci['bad_fields'][:6]}）")
        advice.append({
            "text": "死苗/放弃格（task-84）：" + "；".join(_parts),
            "lines": (dci.get("no_work_uncleared", []) + dci.get("verified_with_gave_up", [])
                      + dci.get("bad_fields", [])),
        })
    # 0n) task-102（`9b09735`）：背包空格死锁 —— **买不到不是失败**，也不许读成"睡眠失败"
    bsi = report.get("bag_space") or {}
    if (bsi.get("buy_no_space") or bsi.get("buy_no_space_receipts") or bsi.get("slept_without_work")
            or bsi.get("slot_sells") or bsi.get("modal_dismiss_failures")):
        _bparts = []
        if bsi.get("buy_no_space"):
            _bparts.append(
                f"买种子撞背包没空格 ×{bsi['buy_no_space']}"
                f"（行 {bsi.get('buy_no_space_lines', [])[:6]}）⇒ 当天不再重试 buy；"
                "**买不到不是失败**（真问题是格子/钱/货架，不是任务没做成）")
        elif bsi.get("buy_no_space_receipts"):
            _bparts.append(
                f"买种子撞背包没空格 ×{bsi['buy_no_space_receipts']}（旧账本形态："
                f"没有 buy_no_space 事件，从回执码 no_inventory_space 补认，行 "
                f"{bsi.get('buy_lines', [])[:6]}）：回执明说「空格 0」⇒ 真卡点是背包格子，"
                "**买不到不是失败**（task-102 之后 brain 会写 buy_no_space 事件）")
        if bsi.get("slot_sells"):
            _bparts.append(
                f"为腾格卖盈余材料 ×{bsi['slot_sells']}"
                f"（行 {bsi.get('slot_sell_lines', [])[:6]}；why=need_slot）：钱要等下一次 NewDay "
                "才由游戏结算 ⇒ **成交当天 money 不变是设计**，别判红")
        if bsi.get("slept_without_work"):
            _bparts.append(
                f"0 农场动作拒绝睡觉 ×{bsi['slept_without_work']}"
                f"（行 {bsi.get('slept_without_work_lines', [])[:6]}）⇒ 那天**不推进**（守卫生效），"
                "账本会以 needs_review / `no_day_progress` 如实停住 —— 这是**不是睡眠失败**；"
                "要查的是「为什么一整天 0 动作」（种子/格子死锁、可达性），不是睡觉协议")
        if bsi.get("modal_dismiss_failures"):
            _bparts.append(
                f"关模态失败 ×{bsi['modal_dismiss_failures']}"
                f"（行 {bsi.get('modal_dismiss_failed_lines', [])[:6]}）：只点名（verify-run3 未判它，"
                "本工具**不判红**以免两边反向）；若同日另有 modal_blocked/timeout，按那条算")
        advice.append({
            "text": "背包空格/买种子闭环（task-102）：" + "；".join(_bparts),
            "lines": (bsi.get("buy_no_space_lines", []) + bsi.get("slot_sell_lines", [])
                      + bsi.get("slept_without_work_lines", [])
                      + bsi.get("modal_dismiss_failed_lines", [])
                      + ([] if bsi.get("buy_no_space") else bsi.get("buy_lines", [])[:6])),
        })
    # 0o) LLM 收工复盘 / 教训库（task-111）：没学到东西是信息项；三条完整性红才点名
    lri = report.get("llm_review") or {}
    if (lri.get("without_notes_lines") or lri.get("over_limit_lines")
            or lri.get("load_failed") or lri.get("file_status") == "corrupt"):
        _lparts = []
        if lri.get("without_notes_lines"):
            _lparts.append(f"复盘声称成功却 0 条 notes ×{len(lri['without_notes_lines'])}"
                           f"（行 {lri['without_notes_lines'][:6]}）⇒ 假称学到东西（看 rejected/"
                           "truncated；要么修提示词、要么如实记成 review_llm_failed）")
        if lri.get("over_limit_lines"):
            _lparts.append(f"教训库超上限（total={lri.get('lessons_total')} / 落盘 "
                           f"{lri.get('file_count')} 条 > {lri.get('lessons_max')}）"
                           "⇒ 淘汰逻辑没生效，提示词预算会被吃光")
        if lri.get("load_failed"):
            _lparts.append(f"教训库读不了 ×{lri['load_failed']}（{lri.get('load_errors', [])[:2]}）"
                           "⇒ 教训库不可信（'失败无害'只指不中断跑批）")
        if lri.get("file_status") == "corrupt":
            _lparts.append(f"教训库文件损坏（{lri.get('file_path')}：{lri.get('file_error')}）")
        if (lri.get("warn_all_rejected_run") or 0) >= 2:
            _lparts.append(f"教训库连续整版被拒 ×{lri.get('warn_all_rejected_run')} 天"
                           "（warn:lessons_all_rejected，**不判红**）")
        if (lri.get("warn_all_untrusted_run") or 0) >= 2:
            _lparts.append(f"教训库连续整版不可信 ×{lri.get('warn_all_untrusted_run')} 天"
                           "（warn:lessons_all_untrusted：written==0 且 skipped_untrusted>0，**不判红**）")
        # task-136 C（task-139）：hint 丢弃的**可证伪**形态 —— 只 ⚠、不判红（丢弃本身是设计行为）
        if lri.get("hint_dropped_bad_lines"):
            _lparts.append(f"`lessons.hint_dropped` 缺失/非整数（行 "
                           f"{lri.get('hint_dropped_bad_lines', [])[:4]}）⇒ 矛盾 hint 丢弃数只能记"
                           "【无法判定】（缺失 ≠ 0）")
        elif lri.get("hint_dropped_gt_added_lines"):
            _lparts.append(f"hint 丢弃数 > 当天新增条数（行 "
                           f"{lri.get('hint_dropped_gt_added_lines', [])[:4]}）⇒ 口径打架"
                           "（丢掉的不可能多于当天拍出来的），只警告不判红")
        if lri.get("warn_empty_hint_no_count"):
            _lparts.append(f"库里有条目 `hint` 为空（丢弃已生效）却全账本没有 `hint_dropped` 计数"
                           f"（{lri.get('file_path')}）⇒ 疑字段被摘/没记账，只警告不判红")
        advice.append({
            "text": "LLM 复盘/教训库（task-111）：" + "；".join(_lparts),
            "lines": (lri.get("without_notes_lines", []) + lri.get("over_limit_lines", [])
                      + lri.get("load_failed_lines", [])),
        })
    elif (lri.get("warn_all_rejected_run") or 0) >= 2:
        advice.append({
            "text": "教训库连续整版被拒（warn:lessons_all_rejected，**不判红**）：连续 "
                    f"{lri.get('warn_all_rejected_run')} 天 dropped>0 且 kept==0（"
                    f"{'、'.join([str(x) for x in (lri.get('warn_all_rejected_days') or [])][:3])}）"
                    "⇒ 拒收本身是正确行为（外部篡改/结构不符就该拒），但连着几天一条都没留下 ⇒ "
                    "看一眼这个文件是不是被改坏、或被写成了别的 schema（task-114）；缺字段照旧【无法判定】",
            "lines": (lri.get("rejected_lines") or [])[:6],
        })
    elif (lri.get("warn_all_untrusted_run") or 0) >= 2:
        advice.append({
            "text": "教训库连续整版不可信（warn:lessons_all_untrusted，**不判红**）：连续 "
                    f"{lri.get('warn_all_untrusted_run')} 天 written==0 且 skipped_untrusted>0（"
                    f"{'、'.join([str(x) for x in (lri.get('warn_all_untrusted_days') or [])][:3])}）"
                    "⇒ 防洗白**生效**（不可信条目一条也没被写回），但整库都是外部条目 ⇒ "
                    "看一眼文件是不是被外部整版替换过（task-118 A）；缺字段照旧【无法判定】",
            "lines": (lri.get("lessons_lines") or [])[:6],
        })
    elif lri.get("has_events"):
        _rej_txt = (f"；拒收 {lri.get('rejected_events', 0)} 次 / {lri.get('rejected_dropped', 0)} 条"
                    f"（原因 {'、'.join([str(x) for x in (lri.get('rejected_reasons') or ['—'])][:2])}）"
                    + (f"（其中不可信 {lri.get('rejected_untrusted', 0)} 条）"
                       if lri.get("rejected_untrusted") else "")
                    if lri.get("rejected_events") else "")
        _wr_txt = (f"；落盘写入 {lri.get('lessons_written')} 条 / 跳过不可信 "
                   f"{lri.get('lessons_skipped_untrusted')} 条（跳过 >0 = 防洗白生效，**不是失败**）"
                   if (lri.get("lessons_written") is not None
                       or lri.get("lessons_skipped_untrusted") is not None) else "")
        advice.append({
            "text": f"LLM 复盘/教训库（信息项，**不是失败**）：复盘 {lri.get('review_events', 0)} 次 "
                    f"/ notes {lri.get('notes_count', 0)} 条；教训库 total "
                    f"{lri.get('lessons_total')} 条（本日新增 {lri.get('lessons_added')}）"
                    + _rej_txt + _wr_txt
                    + "；空库 / 0 新增 / 复盘失败 / 拒收都只记信息（task-111/114/118）",
            "lines": (lri.get("review_lines", []) + lri.get("lessons_lines", [])
                      + lri.get("rejected_lines", []))[:8],
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
    # 0p) task-124/task-130：review 兜底 / 弃权 / 换片连发 —— **修复生效的证据，不判红**；
    # 只有可证伪形态给 ⚠ 警告（burst 当天却 VERIFIED / 弃权后守卫仍抱怨 / 兜底抛异常）。
    rfa = report.get("review_fallback") or {}
    if rfa.get("has_events"):
        _rparts = [f"兜底 {rfa.get('fallback_events', 0)} 次"
                   f"（work_spot {rfa.get('fallback_work_spot', 0)} / pending_walk "
                   f"{rfa.get('fallback_pending_walk', 0)}；带路成功 {rfa.get('fallback_walked', 0)} 次）",
                   f"弃权 {rfa.get('no_target_events', 0)} 次（{rfa.get('no_target_pending', 0)} 格当日放弃、"
                   "次日重试）",
                   f"换片连发 {rfa.get('burst_events', 0)} 次（最多一次 count={rfa.get('burst_max', 0)}）"]
        if rfa.get("warn_burst_verified_lines"):
            _rparts.append(f"⚠ burst 当天却自称 VERIFIED：{'、'.join(str(x) for x in (rfa.get('warn_burst_verified_days') or [])[:3])}"
                           "（连发=没目标的证据，与 VERIFIED 互斥；只警告）")
        if rfa.get("warn_no_target_still_guarded_lines"):
            _rparts.append(f"⚠ 弃权后守卫仍抱怨同批 leftover："
                           f"{'、'.join(str(x) for x in (rfa.get('warn_no_target_still_guarded_days') or [])[:3])}"
                           "（弃权没生效；只警告）")
        if rfa.get("failed_events"):
            _rparts.append(f"⚠ 兜底抛异常 {rfa.get('failed_events')} 次（{rfa.get('failed_errors', [])[:2]}）")
        if rfa.get("resume_events"):
            _rparts.append(f"回跨片区重评 {rfa.get('resume_events')} 次"
                           f"（清掉任务级 no_target：{'、'.join(list((rfa.get('resume_cleared') or {}).keys())[:4]) or '（无）'}）"
                           "——走路→空转→再走路死循环的解药，不判红")
        if rfa.get("no_progress_events"):
            _rparts.append(f"连续无产出触顶 {rfa.get('no_progress_events')} 次（最多 count="
                           f"{rfa.get('no_progress_max', 0)}、覆盖 {rfa.get('no_progress_tiles', 0)} 格；来源 "
                           f"{'、'.join(f'{k}×{v}' for k, v in list((rfa.get('no_progress_sources') or {}).items())[:3]) or '<缺失>'}）"
                           "——按有界机制诚实收尾（stuck、leftover 如实保留），不判红")
        for _wl, _wd, _what in ((rfa.get("warn_no_progress_verified_lines") or [],
                                 rfa.get("warn_no_progress_verified_days") or [],
                                 "连续无产出触顶当天却自称 VERIFIED"),
                                (rfa.get("warn_burst_verified_lines") or [],
                                 rfa.get("warn_burst_verified_days") or [],
                                 "burst 当天却自称 VERIFIED")):
            if _wl:
                _rparts.append(f"⚠ {_what}：{'、'.join(str(x) for x in _wd[:3])}"
                               "（触顶/连发=没目标的证据，与 VERIFIED 互斥；只警告）")
                break
        advice.append({
            "text": "review 兜底/换片连发（信息项，**不是失败**）：" + "；".join(_rparts)
                    + "。这些事件是 task-124/task-130 修复生效的证据（review 独苗时改走能落地的意图 / "
                      "把人带回跨片 leftover / 把换片空转按有界机制收尾；task-134 A 另加：回跨片 leftover 前"
                      "清任务级 no_target、连续无产出触顶按有界机制诚实收尾）；verify-run3.py 对它们零命中 "
                      "⇒ 本工具只给上面这几条可证伪形态的 ⚠ 警告，**不判红、不进 rc**；"
                      "旧账本没有这些事件 ⇒ 写【无法判定】（缺失 ≠ 0）",
            "lines": sorted(set((rfa.get("fallback_lines") or []) + (rfa.get("no_target_lines") or [])
                                + (rfa.get("burst_lines") or []) + (rfa.get("failed_lines") or [])
                                + (rfa.get("resume_lines") or []) + (rfa.get("no_progress_lines") or []))),
        })
    # 0r) task-134 B：分配额口径（阶段 assigned_undone vs 片区 leftover vs 诚实上限 deferred）——
    #     三者在报告里**只作信息项**（不判红）；红由 `checks.no_unmet_stages=false` 说话。
    shfa = report.get("shortfall") or {}
    if shfa.get("has_events") or shfa.get("has_day_fields"):
        _sparts = []
        if shfa.get("stage_events"):
            _sparts.append(f"阶段没做完 {shfa.get('stage_events')} 次"
                           f"（分下去 {shfa.get('assigned_total', 0)} 格 / 没做完 "
                           f"{shfa.get('undone_total', 0)} 格；stopped "
                           f"{'、'.join(f'{k}×{v}' for k, v in list((shfa.get('stopped_kinds') or {}).items())[:3]) or '<缺失>'}）")
        if shfa.get("day_events"):
            _sparts.append(f"日级 shortfall {shfa.get('day_events')} 次（unmet 最多 {shfa.get('unmet_max', 0)}、"
                           f"片区 pending 最多 {shfa.get('plot_pending_max', 0)}）")
        if shfa.get("deferred_events"):
            _sparts.append(f"诚实上限留下 {shfa.get('deferred_tiles', 0)} 格"
                           f"（night={shfa.get('deferred_night', 0)} 次）⇒ 只作 info、**不进 no_unmet_stages**")
        if shfa.get("warn_stopped_night_mismatch_lines"):
            _sparts.append(f"⚠ 口径打架：行 {shfa.get('warn_stopped_night_mismatch_lines')[:4]}"
                           "（日级说 stopped_night=false 而当天 ended_reason 是 night，只警告、不判红）")
        advice.append({
            "text": "阶段分配额/诚实上限（信息项，**不判红**）：" + "；".join(_sparts)
                    + "。task-134 B 起日级 `no_unmet_stages` 看**分配额** `assigned_undone`"
                      "（分下去的格 − 做成/按规跳过），`plot_pending`（片区还剩几格）只供守卫/换片/resume；"
                      "体力用尽/夜里收工/做完后撞 budget 留下的片区待办记 `deferred_tiles`，"
                      "**绝不当'没做完还硬说达标'**；缺失 ⇒【无法判定】（缺失 ≠ 0）",
            "lines": sorted(set((shfa.get("stage_lines") or []) + (shfa.get("day_lines") or [])
                                + (shfa.get("deferred_lines") or [])
                                + (shfa.get("warn_stopped_night_mismatch_lines") or []))),
        })
    # 0p-2) task-132（task-123 在制）：量力而行买种子 —— **买一半不是失败**；只列两条可证伪 ⚠。
    bpv = report.get("buy_partial") or {}
    if bpv.get("has_events") or bpv.get("buy_has_wanted"):
        _bparts = [f"部分购买 {bpv.get('events', 0)} 次（买到 {bpv.get('bought_total', 0)} 个 / 想要 "
                   f"{bpv.get('wanted_total', 0)} 个；还缺 {bpv.get('short_total', 0)} 个）",
                   f"买满成交 {bpv.get('buy_ok_full', 0)} 次"
                   + (f"（另有 {bpv.get('buy_ok_missing_wanted')} 次成交没有 wanted 字段、无法区分是否买满）"
                      if bpv.get("buy_ok_missing_wanted") else ""),
                   f"cannot_afford {bpv.get('cannot_afford_events', 0)} 次（一个都买不起 ⇒ 不发请求）"]
        if bpv.get("warn_missing_partial_lines"):
            _bparts.append(f"⚠ buy 自称成交却买少（count<wanted）且当天没有对应 buy_partial：行 "
                           f"{bpv.get('warn_missing_partial_lines', [])[:6]}")
        if bpv.get("warn_cannot_afford_same_day_lines"):
            _bparts.append(f"⚠ 同日既有 buy_partial 又有 cannot_afford："
                           f"{bpv.get('warn_cannot_afford_same_day_days')}"
                           f"（行 {bpv.get('warn_cannot_afford_same_day_lines', [])[:6]}；只提示人工核对）")
        advice.append({
            "text": "部分购买/量力而行（信息项，**买一半不是失败**）：" + "；".join(_bparts)
                    + "。钱只够买 `n < wanted` 时照样买下、缺的种子等次日钱结算后再补"
                      "（`cannot_afford` 只留给'一个都买不起'）；`buy_ok` 类成交只算买满 `wanted` 的整笔。"
                      "verify-run3.py 对 `buy_partial` 零命中 ⇒ 本工具只给上面两条可证伪形态的 ⚠ 警告，"
                      "**不判红、不进 rc**；旧账本缺这些字段 ⇒【无法判定】（缺失 ≠ 0）",
            "lines": sorted(set((bpv.get("lines") or []) + (bpv.get("warn_missing_partial_lines") or [])
                                + (bpv.get("cannot_afford_lines") or []))),
        })
    # 0q) task-133：窗口外浇水 + 壶空先补水 —— **不是失败**（壶空是前置条件，不是"够不着"）；
    #     只列两条可证伪 ⚠（补水没成却浇成 / 当天补水预算用尽）。
    wfv = report.get("water_far") or {}
    if wfv.get("has_events"):
        _wparts = [f"water_far {wfv.get('far_events', 0)} 次（浇成 {wfv.get('far_ok', 0)} / "
                   f"没成 {wfv.get('far_failed', 0)}；因由 "
                   f"{'、'.join(f'{k}×{v}' for k, v in list((wfv.get('far_causes') or {}).items())[:4]) or '<缺失>'}）",
                   f"补水 water_far_refill {wfv.get('refill_events', 0)} 次（成功 "
                   f"{wfv.get('refill_ok', 0)} / 没成 {wfv.get('refill_failed', 0)}）"]
        if wfv.get("far_need_refill_lines"):
            _wparts.append(f"其中因由=need_refill（壶空）的行 {wfv.get('far_need_refill_lines')[:6]}"
                           "——壶空**不是够不着**：先补水再回浇；补水没成才是那格今天浇不上的因由")
        if wfv.get("warn_refill_failed_but_watered_lines"):
            _wparts.append(f"⚠ 补水没成却把那格浇成了：行 "
                           f"{wfv.get('warn_refill_failed_but_watered_lines')[:6]}（只警告）")
        if wfv.get("warn_budget_exhausted_lines"):
            _wparts.append(f"⚠ 当天补水预算用尽（tries ≥ limit）：行 "
                           f"{wfv.get('warn_budget_exhausted_lines')[:6]}"
                           "——剩余干格今天注定浇不上（只警告）")
        # task-157：够不着 ⇒ 有界开路（开路成功 ≠ 浇上水）；开路后仍站不到 ⇒ 如实 blocked。
        if wfv.get("has_open_events"):
            _wparts.append(
                f"开路 water_far_open {wfv.get('open_events', 0)} 次（code "
                f"{'、'.join(f'{k}×{v}' for k, v in list((wfv.get('open_codes') or {}).items())[:4]) or '<缺失>'}；"
                f"清了 {wfv.get('open_cleared_total', 0)} 格挡路格）")
            _wparts.append(
                f"开路后仍站不到 water_far_blocked {wfv.get('blocked_events', 0)} 格（因由 "
                f"{'、'.join(f'{k}×{v}' for k, v in list((wfv.get('blocked_causes') or {}).items())[:4]) or '<缺失>'}）"
                "——都是如实留痕、**不是失败**；开路成功也**不等于**那格浇上了水")
            if wfv.get("warn_open_but_still_dry_lines"):
                _wparts.append(f"⚠ 开路成功但那格当天最后仍在 dryTiles 里：行 "
                               f"{wfv['warn_open_but_still_dry_lines'][:6]}（只警告）")
            if wfv.get("warn_blocked_but_watered_lines"):
                _wparts.append(f"⚠ 有格 blocked（确实没浇上）而当天却自称户外浇水达标"
                               f"（watered_outdoor=true 且 final_water.dry=0）：行 "
                               f"{wfv['warn_blocked_but_watered_lines'][:6]}（只警告）")
        advice.append({
            "text": "窗口外浇水/壶空补水/开路（信息项，**不是失败**）：" + "；".join(_wparts)
                    + "。verify-run3.py 对 `water_far_refill` / `water_far_open` / `water_far_blocked` "
                      "零命中 ⇒ 本工具不判红、不进 rc；"
                      "旧账本没有这些事件 ⇒【无法判定】（缺失 ≠ 0）",
            "lines": sorted(set((wfv.get("far_lines") or []) + (wfv.get("refill_lines") or [])
                                + (wfv.get("open_lines") or []) + (wfv.get("blocked_lines") or [])
                                + (wfv.get("warn_refill_failed_but_watered_lines") or [])
                                + (wfv.get("warn_open_but_still_dry_lines") or [])
                                + (wfv.get("warn_blocked_but_watered_lines") or []))),
        })
    # 0u) task-158：体力预算 —— 解释「为什么今天不浇」；**不是失败**（没浇完就是 crops_watered=false），
    #     只列两条可证伪 ⚠（说延后却当天自称浇完 / 日级字段有延后数却没有对应事件）。
    sbv = report.get("stamina_budget") or {}
    if sbv.get("has_events"):
        _bparts = [
            f"体力预算 {sbv.get('events', 0)} 条（依据 "
            f"{'、'.join(f'{k}×{v}' for k, v in list((sbv.get('basis') or {}).items())[:3]) or '<缺失>'}；"
            f"reserve {sbv.get('water_reserve')} / capacity {sbv.get('capacity')}）",
            f"只因预算被延后 deferred_by_budget {sbv.get('defer_events', 0)} 条"
            f"（共 {sbv.get('deferred_total', 0)} 格"
            + ("；任务 " + "、".join(f"{k}×{v}" for k, v in list((sbv.get('defer_tasks') or {}).items())[:4])
               if sbv.get("defer_tasks") else "") + "）",
            f"预算延后 budget_deferred_tiles {sbv.get('budget_defer_events', 0)} 条"
            f"（{sbv.get('budget_defer_tiles', 0)} 格；任务 "
            f"{'、'.join(f'{k}×{v}' for k, v in list((sbv.get('budget_defer_tasks') or {}).items())[:4]) or '<缺失>'}）",
            (f"容量上限 stage_capped_by_capacity {sbv.get('capacity_events', 0)} 次"
             f"（任务 {'、'.join(list((sbv.get('capacity_tasks') or {}).keys())[:4]) or '<缺失>'}"
             f"；日级 capacity_capped_tasks {sbv.get('capacity_capped_tasks', 0)}）"
             if (sbv.get("capacity_events") or sbv.get("capacity_capped_tasks"))
             else "容量上限 stage_capped_by_capacity <缺失>（旧账本 / 当天未命中）"),
        ]
        if not sbv.get("has_day_field"):
            _bparts.append("日级 `day_end.stamina_budget` <缺失>（旧账本 ⇒ 只能看事件口径）")
        if sbv.get("warn_deferred_but_watered_lines"):
            _bparts.append(f"⚠ 说「只因预算延后」但当天却自称户外浇水达标（dry=0）：行 "
                           f"{sbv['warn_deferred_but_watered_lines'][:6]}（只警告）")
        if sbv.get("warn_defer_missing_lines"):
            _bparts.append(f"⚠ 日级 deferred_by_budget>0 却没有对应的 deferred_by_budget 事件：行 "
                           f"{sbv['warn_defer_missing_lines'][:6]}（留痕不一致，只警告）")
        if sbv.get("warn_defer_tiles_but_no_work_lines"):
            _bparts.append(f"⚠ 当天有预算延后（budget_deferred_tiles）却自称「该做的都做了」"
                           f"（no_work + VERIFIED）⇒ 人工核对「延后是否只发生在体力 ≤ water_reserve"
                           f" **且** 有浇水债时」：行 {sbv['warn_defer_tiles_but_no_work_lines'][:6]}（只警告）")
        if sbv.get("warn_defer_without_debt_lines"):
            _bparts.append(f"⚠ 当天有预算延后但 stamina_budget 显示没有浇水债（live_crops/dry ≤ 0）"
                           f"⇒ 延后可能变成「免罚额度」：行 "
                           f"{sbv['warn_defer_without_debt_lines'][:6]}（只警告）")
        advice.append({
            "text": "体力预算/只因预算而不做（信息项，**不是失败**）：" + "；".join(_bparts)
                    + "。verify-run3.py 对 `stamina_budget` / `deferred_by_budget` / "
                      "`budget_deferred_tiles` / `stage_capped_by_capacity` 零命中 ⇒ "
                      "本工具不判红、不进 rc；当天达不达标由 `checks.watered_outdoor` / "
                      "`checks.no_unmet_stages` 说话；旧账本没有这些事件 ⇒【无法判定】（缺失 ≠ 0）",
            "lines": sorted(set((sbv.get("lines") or []) + (sbv.get("defer_lines") or [])
                                + (sbv.get("budget_defer_lines") or [])
                                + (sbv.get("capacity_lines") or [])
                                + (sbv.get("warn_deferred_but_watered_lines") or [])
                                + (sbv.get("warn_defer_missing_lines") or [])
                                + (sbv.get("warn_defer_tiles_but_no_work_lines") or [])
                                + (sbv.get("warn_defer_without_debt_lines") or []))),
        })
    # 0v) task-20 / task-164：工具门槛封格（clump 工具等级/种类不够）—— **诚实跳过**（0 次 use_tool）、
    #     **不判红、不进 rc**；只一条可证伪 ⚠（自称 no_work 却存在工具门槛封格 ⇒ 人工核对）。
    tgv = report.get("tool_gate") or {}
    if tgv.get("has_events"):
        _tgparts = [
            f"工具门槛封格 {tgv.get('events', 0)} 格（需要 "
            f"{'、'.join(f'{k}×{v}' for k, v in list((tgv.get('needs') or {}).items())[:4]) or '<缺失>'}；"
            f"kind {'、'.join(f'{k}×{v}' for k, v in list((tgv.get('kinds') or {}).items())[:4]) or '<缺失>'}）",
            f"日级汇总 {tgv.get('summary_events', 0)} 次（count {(tgv.get('summary_counts') or [])[:4]}）",
        ]
        if tgv.get("min_level_missing"):
            _tgparts.append(f"{tgv['min_level_missing']} 格没写 `min_level`（判不出等级 ⇒ 不许默认 0 级）")
        if tgv.get("kind_unknown"):
            _tgparts.append(f"{tgv['kind_unknown']} 格 kind 判不出（不许替观测断言树/桩/大石）")
        if tgv.get("warn_no_work_with_gate_lines"):
            _tgparts.append(f"⚠ 当天自称 no_work（没活）却存在工具门槛封格：行 "
                            f"{tgv['warn_no_work_with_gate_lines'][:6]}（人工核对：真敲不动 vs 判不出）")
        advice.append({
            "text": "工具门槛封格（信息项，**诚实跳过、不是失败**）：" + "；".join(_tgparts)
                    + "。0 次 `use_tool`、不算活、不进守卫理由；`tools/verify-run3.py` 对 "
                      "`blocked_by_tool` / `blocked_by_tool_summary` 零命中 ⇒ 本工具不判红、不进 rc；"
                      "旧账本没有这两个事件 ⇒【无法判定】（缺失 ≠ 0）",
            "lines": sorted(set((tgv.get("lines") or []) + (tgv.get("summary_lines") or [])
                                + (tgv.get("warn_no_work_with_gate_lines") or []))),
        })
    # 0s) task-144：阶段内壶空 ⇒ 先补水再把"这一轮没成事的已分配格"**原样**重跑（refill_retry）；
    #     阶段自然走完（stopped==""）却仍有分配未成事的格 ⇒ 补**如实** stop 原因（stage_stop_named）
    #     —— 都是**修复生效的证据**，**不判红**；只有三条可证伪形态给 ⚠（不进 red / 不进 rc）。
    rrv2 = report.get("refill_retry") or {}
    snv2 = report.get("stage_stop_named") or {}
    if rrv2.get("has_events") or snv2.get("has_events"):
        _sparts2 = [
            f"壶空后原样重跑 {rrv2.get('events', 0)} 次（补水成功 {rrv2.get('ok', 0)} / 没成 "
            f"{rrv2.get('failed', 0)}；重跑 {rrv2.get('tiles_total', 0)} 格）",
            f"如实 stop 命名 {snv2.get('events', 0)} 次（cause "
            f"{'、'.join(f'{k}×{v}' for k, v in list((snv2.get('causes') or {}).items())[:4]) or '<缺失>'}；"
            f"分下去 {snv2.get('assigned_total', 0)} / 没做完 {snv2.get('undone_total', 0)} 格）",
        ]
        # task-144 增量：阶段补水次数 / 阶段上界（`STAGE_REFILL_MAX`）；越界只给 ⚠。
        _srb2 = rrv2.get("stage_refill_by_stage") or {}
        _sparts2.append(
            "阶段补水 " + "、".join(
                f"{_k} {_v.get('stage_refills') if _v.get('stage_refills') is not None else '<缺失>'}"
                f"/{_v.get('stage_limit') if _v.get('stage_limit') is not None else '<缺失>'}"
                for _k, _v in list(_srb2.items())[:3]) + " 次（stage_refills/stage_limit）"
            if _srb2 else "阶段补水 <缺失>（旧账本没有 `stage_refills`/`stage_limit` 字段 ⇒ 缺失 ≠ 0）")
        if rrv2.get("warn_over_stage_refill_lines"):
            _sparts2.append(f"⚠ 阶段补水次数超过该阶段上界（行 "
                            f"{rrv2['warn_over_stage_refill_lines'][:6]}）"
                            "——`stage_refills > stage_limit`，只警告")
        if rrv2.get("warn_over_retry_lines"):
            _sparts2.append(f"⚠ 重跑条数多于当天 refill（行 {rrv2['warn_over_retry_lines'][:6]}）"
                            "——两个口径打架，只警告")
        if rrv2.get("warn_empty_lines"):
            _sparts2.append(f"⚠ 补水成功却 0 格可重跑（行 {rrv2['warn_empty_lines'][:6]}）"
                            "——空转嫌疑，只警告")
        if (snv2.get("warn_bad_cause_lines") or snv2.get("warn_no_undone_lines")
                or snv2.get("warn_no_codes_lines")):
            _sparts2.append("⚠ stage_stop_named 自相矛盾（cause 缺失/未知 / assigned_undone≤0 / "
                            "有过失却 codes 空）——只警告")
        advice.append({
            "text": "阶段自愈/如实收工（信息项，**不是失败**）：" + "；".join(_sparts2)
                    + "。verify-run3.py 对 `refill_retry`/`stage_stop_named` 零命中 ⇒ 本工具不判红、"
                      "不进 rc；旧账本没有这两个事件 ⇒【无法判定】（缺失 ≠ 0）",
            "lines": sorted(set((rrv2.get("lines") or []) + (snv2.get("lines") or [])
                                + (rrv2.get("warn_over_retry_lines") or [])
                                + (rrv2.get("warn_over_stage_refill_lines") or [])
                                + (rrv2.get("warn_empty_lines") or []))),
        })
    # 0s-2) task-172：收获如实放弃（**不是豁免分子**）+ 「看着熟其实不能收」对账
    hg = report.get("harvest_gave_up") or {}
    cr = report.get("crop_ready") or {}
    if hg.get("has_events"):
        advice.append({
            "text": f"收获如实放弃 ×{hg['events']}（{hg.get('tile_count', 0)} 格；试满 attempts "
                    f"合计 {hg.get('attempts', 0)}）：目标池与守卫都把它扣掉，但 `_leftover(\"harvest\")` "
                    "不扣 ⇒ **这是「该做没做」的证据，不是豁免配额**；要么改掉让它摘不到的东西"
                    "（task-169：Mod 的 `ripe`=`fullyGrown` 比游戏 `HoeDirt.readyForHarvest()` 松），"
                    "要么如实按未完成验收",
            "lines": hg.get("lines") or [],
        })
    if not cr.get("has_fields"):
        advice.append({
            "text": "「看着熟其实不能收」对账缺证据：账本 `day_end.final.farm` 里没有 "
                    "`ripeCrops`/`readyCrops`（brain `longrun.py:1690-1692` 白名单不含）⇒ 只能【无法判定】；"
                    "要判这一支请用 `observe?detail=full` 的 `farm.readyCrops` 采样",
            "lines": [],
        })
    elif cr.get("diff_total", 0) > 0:
        advice.append({
            "text": f"看着熟其实不能收：ripeCrops {cr.get('ripe_total')} − readyCrops "
                    f"{cr.get('ready_total')} = {cr.get('diff_total')}（差在 regrow 期 "
                    "`fullyGrown && dayOfCurrentPhase>0`、`dead`、`forageCrop==\"2\"`）——"
                    "task-169 的真病根就在这条差值上",
            "lines": cr.get("ripe_without_ready_lines") or [],
        })
    # 0s-3) task-179：`ready` 的来源（game/fields/null/缺键）—— `fields` 是等价路径，不是 fail-open
    if cr.get("ready_source_missing_tiles"):
        advice.append({
            "text": f"`tiles[].readySource` 缺键 {cr['ready_source_missing_tiles']} 格（旧 Mod 形态）："
                    "**无法判定·旧 Mod** —— 分不清 `ready` 是游戏 `HoeDirt.readyForHarvest()` 判的、"
                    "还是我们字段兜底猜的（task-173 的 FAIL 就是这样被掩盖的）；绝不因此判通过",
            "lines": (cr.get("ready_source_missing_lines") or [])[:12],
        })
    elif not cr.get("has_ready_source"):
        advice.append({
            "text": "账本里没有 `tiles[].readySource`（task-176）：**无法判定·旧 Mod** —— `ready` 的来源"
                    "不可考（缺失 ≠ 0、更 ≠ 通过）；0.7.34 之后的账本该带这个键",
            "lines": [],
        })
    elif cr.get("warn_null_heavy"):
        advice.append({
            "text": f"`readySource=null` 占 {cr.get('ready_source_null')}/{cr.get('ready_source_seen')}"
                    "（fail-closed 过头风险：反射与字段都读不到 ⇒ 这些格既不当能收、也不当不能收，"
                    "只记【无法判定】）；若长期如此，说明反射面在 1.6.15 上不稳，值得报给 Mod 侧",
            "lines": [],
        })
    if cr.get("harvest_method_missing_lines"):
        advice.append({
            "text": f"`tiles[].harvestMethod` 键缺失 {len(cr['harvest_method_missing_lines'])} 行"
                    "（task-176 要求该键**无条件存在**，`Contracts.cs` 用 `JsonIgnore(Never)`）；"
                    "缺键 ⇒ 旧 Mod 形态，镰刀类作物到底走 `interact` 还是工具路径无法判定",
            "lines": (cr.get("harvest_method_missing_lines") or [])[:12],
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
    # task-84：旧账本没有死苗字段 ⇒ 死苗口径无法判定（缺失 ≠ 0；绝不当"没有死苗"通过）
    _dc_ends = [ev for _, ev in rows if ev.get("event") == "day_end"]
    _dc_has = [ev for ev in _dc_ends
               if any(k in ev for k in ("dead_crops", "dry_dead", "gave_up_tiles"))]
    if _dc_ends and not _dc_has:
        out.append("本账本没有任何 task-84 死苗字段（day_end.dead_crops/dead_crops_status/dry_dead/"
                   "dry_dead_status/gave_up_tiles，也没有 dead_crops_summary 事件）："
                   "无法判定死苗（枯死作物）与当天放弃格 —— **缺失 ≠ 0，绝不当'没有死苗'通过**")
    elif _dc_has:
        _dc_missing = sorted({k for ev in _dc_has
                              for k in ("dead_crops", "dry_dead", "gave_up_tiles") if k not in ev})
        if _dc_missing:
            out.append(f"死苗字段只写了一部分（缺 {_dc_missing}）：无法判定缺的那一列（缺失 ≠ 0）")
    # task-102：背包空格/买种子闭环的证据是否存在（缺失 ⇒【无法判定】，绝不因此判通过、也不判红）
    _bag_ev = [ev for _, ev in rows
               if ev.get("event") in ("sell", "surplus_sell", "surplus_sell_skip", "buy_no_space")]
    _bag_fs = [ev for ev in _bag_ev
               if as_dict(ev.get("trigger")).get("freeSlots") is not None
               or ev.get("free_slots_status")]
    if (rows and not _bag_ev) or (_bag_ev and not _bag_fs):
        out.append("本账本没有 free_slots 证据（`surplus_sell`/`surplus_sell_skip`/`sell` 的 "
                   "`trigger.freeSlots`，或 `buy_no_space.free_slots_status`）：无法判定「背包空格」"
                   "这条死锁链（缺失 ≠ 空、≠ 没发生；task-102）")
    # task-170/task-172：新观测字段是否存在（缺失 ⇒【无法判定】，绝不当"没有看着熟却不能收"通过）
    if rows and not any(ev.get("event") == "harvest_gave_up" for _, ev in rows):
        out.append("本账本没有 `harvest_gave_up` 事件（task-170）：无法判定是否发生过「如实放弃收获」"
                   "—— **缺失 ≠ 0**，也绝不当成「收获了 / 没这回事」通过")
    _has_ready = ("\"ready\"" in blob) or ("readyCrops" in blob)
    _has_ripecrops = "ripeCrops" in blob
    if rows and not _has_ready:
        out.append("本账本没有 task-170 的 `tiles[].ready` / `farm.readyCrops`（游戏口径「真能收」）："
                   "无法判定「看着熟其实不能收」这一支 —— 缺失 ≠ 0，"
                   "**绝不当「熟了就都能收」通过**")
    if rows and not _has_ripecrops:
        out.append("本账本没有 `farm.ripeCrops`（旧口径 `Crop.fullyGrown`）："
                   "无法判定「看着熟」的总量 —— 缺失 ≠ 0")
    if _has_ready and not _has_ripecrops:
        out.append("有 `ready` 但没有 `ripeCrops`：两口径无法对账（只能各看一边）")
    # task-179（dev task-176）：`ready` 的**来源**（`readySource`）是否落账 ——
    #   `fields` 是**正常等价路径**（字段判据与 `HoeDirt.readyForHarvest()` 的 IL 逐条等价），
    #   只有 `null` 判不了；旧 Mod 没有这个键 ⇒ 分不清"游戏说的"还是"我们猜的" ⇒【无法判定·旧 Mod】。
    _has_ready_source = "readySource" in blob
    if rows and not _has_ready_source:
        out.append("本账本没有 `tiles[].readySource`（task-176）：**无法判定·旧 Mod** —— "
                   "`ready` 到底是游戏 `HoeDirt.readyForHarvest()` 判的还是字段兜底猜的分不清"
                   "（task-173 的 FAIL 正是这样被掩盖的）；**缺失 ≠ 0、更绝不因此判通过**")
    # task-111：复盘/教训库的证据是否存在（缺失 ⇒【无法判定】，绝不因此判通过、也不判红）
    _lr_ev = [ev for _ln, ev in rows
              if ev.get("event") in ("review_llm", "review_llm_failed", "lessons",
                                     "lessons_load_failed", "lessons_save_failed",
                                     "lessons_rejected")]
    _lr = report.get("llm_review") or {}
    if rows and not _lr_ev:
        out.append("本账本没有任何 task-59/82/114 的复盘/教训库事件（`review_llm`/`review_llm_failed`/"
                   "`lessons`/`lessons_load_failed`/`lessons_save_failed`/`lessons_rejected`）："
                   "无法判定收工复盘与跨日教训库 —— **缺失 ≠ 0，绝不当'模型没学到东西'通过**"
                   "（task-111/114）")
    elif _lr_ev:
        _lr_missing = []
        if not _lr.get("review_events") and not _lr.get("failed_events"):
            _lr_missing.append("review_llm/review_llm_failed")
        if not _lr.get("lessons_events"):
            _lr_missing.append("lessons")
        if _lr_missing:
            out.append(f"复盘/教训库只写了一部分（缺 {_lr_missing}）：无法判定缺的那一列（缺失 ≠ 0）")
        if _lr.get("rejected_events") and _lr.get("rejected_kept") is None:
            out.append("`lessons_rejected` 缺 `kept` 字段：无法判定这次载入是否'整版被拒'"
                       "（缺失 ≠ 0；只有 dropped>0 且 kept==0 连续 ≥2 天才给 warn，task-114）")
        if _lr.get("lessons_events") and (
                _lr.get("lessons_written") is None
                or _lr.get("lessons_skipped_untrusted") is None):
            out.append("`lessons` 缺 `written`/`skipped_untrusted` 字段：无法判定这次落盘"
                       "有没有被外部不可信条目污染、以及防洗白是否生效"
                       "（缺失 ≠ 0，绝不当'没有不可信条目'通过；task-118 A / task-120）")
        if _lr.get("lessons_events") and _lr.get("hint_dropped_bad_lines"):
            out.append("`lessons` 缺 `hint_dropped` 字段（或非整数）：无法判定 task-136 的"
                       "『矛盾 hint 被丢弃』是否发生、丢了几条（缺失 ≠ 0，"
                       "绝不当'没有矛盾 hint'通过；task-136 C / task-139）")
        if _lr.get("rejected_events") and not _lr.get("rejected_untrusted_lines"):
            out.append("`lessons_rejected` 没有 `untrusted` 字段（或恒 0）：无法判定这次载入"
                       "有没有不可信条目（缺失 ≠ 0；task-118 A / task-120）")
    # task-124/task-130：review 兜底 / 弃权 / 换片连发 的证据是否存在
    # （缺失 ⇒【无法判定】；**缺失 ≠ 0 = 没发生过**，也绝不当"没有兜底/没连发"通过）
    _rf_ev = [ev for _ln, ev in rows
              if ev.get("event") in ("review_only_fallback", "review_only_fallback_failed",
                                     "review_only_no_target", "plot_exhausted_burst",
                                     "resume_reevaluate", "no_progress_burst")]
    _rf = report.get("review_fallback") or {}
    if rows and not _rf_ev:
        out.append("本账本没有任何 review 兜底/弃权/连发/无产出触顶事件（`review_only_fallback`/"
                   "`review_only_fallback_failed`/`review_only_no_target`/`plot_exhausted_burst`/"
                   "`resume_reevaluate`/`no_progress_burst`）：无法判定当天是否出现过这些机制"
                   " —— **缺失 ≠ 0，绝不当'没发生'通过**（task-124/130/134）")
    elif _rf_ev and not _rf.get("has_events"):
        out.append("task-124/134 事件存在但没进聚合（工具 bug 迹象）：无法判定兜底/弃权/连发/触顶计数")
    # task-132（task-123 在制）：量力而行买种子的证据是否存在（旧账本没有 `buy_partial`、`buy` 也
    # 没有 `wanted` 字段）—— **缺失 ≠ 0，绝不当"没出现过买一半"通过**。
    _bp_ev = [ev for _ln, ev in rows if ev.get("event") == "buy_partial"]
    _bpv = report.get("buy_partial") or {}
    if not _bp_ev and not _bpv.get("buy_has_wanted"):
        out.append("本账本没有 `buy_partial` 事件，`buy` 也没有 `wanted` 字段（task-123 之前的形态）："
                   "无法判定是否出现过「钱只够买一半」—— **缺失 ≠ 0，绝不当'没发生'通过**（task-132）")
    elif _bp_ev and not _bpv.get("has_events"):
        out.append("task-123 事件存在但没进聚合（工具 bug 迹象）：无法判定部分购买计数")
    # task-133：窗口外浇水的**补水证据**是否存在（旧账本没有 `water_far_refill`、`water_far` 也没有
    # `cause`/`retried_after_refill`）—— **缺失 ≠ 0，绝不当"没试过补水 / 不是壶空"通过**。
    _wf_ev = [ev for _ln, ev in rows if ev.get("event") == "water_far_refill"]
    _wfv = report.get("water_far") or {}
    if not _wf_ev and not _wfv.get("far_events"):
        out.append("本账本没有 `water_far` / `water_far_refill` 事件（task-133 之前的形态）："
                   "无法判定是否出现过「壶空 ⇒ 先补水再回浇」—— **缺失 ≠ 0，绝不当'没发生'通过**"
                   "（task-133）")
    else:
        _wf_missing = []
        if not _wf_ev and _wfv.get("far_events"):
            _wf_missing.append("没有任何 `water_far_refill` ⇒ 无法判定壶空时到底补没补"
                               "（task-133 之前的账本形态）")
        if _wfv.get("far_cause_missing"):
            _wf_missing.append(f"{_wfv.get('far_cause_missing')} 条 `water_far` 没有 `cause` 字段"
                               "⇒ 无法判定没浇成是壶空还是别的因由")
        if _wf_missing:
            out.append("窗口外浇水的补水证据不全：" + "；".join(_wf_missing)
                       + " —— **缺失 ≠ 0，绝不当'不是壶空'通过**（task-133）")
    # task-134 B：分配额口径的证据是否存在（旧账本没有 stage_shortfall(_day)/deferred_tiles 事件，
    # `day_end` 也没有 assigned_undone/deferred_tiles 字段）—— **缺失 ≠ 0，绝不当"没发生"通过**。
    _sf_ev = [ev for _ln, ev in rows
              if ev.get("event") in ("stage_shortfall", "stage_shortfall_day", "deferred_tiles")]
    _shf = report.get("shortfall") or {}
    if not _sf_ev and not _shf.get("has_day_fields"):
        out.append("本账本没有任何 task-134 B 分配额字段（`stage_shortfall`/`stage_shortfall_day`/"
                   "`deferred_tiles` 事件与 `day_end.assigned_undone`/`day_end.deferred_tiles` 都没有）："
                   "无法判定「分下去的格做完了没」与「诚实上限留下多少」—— "
                   "**缺失 ≠ 0，绝不当'都做完了'通过**（task-134 B）")
    elif _sf_ev and not _shf.get("has_events"):
        out.append("task-134 B 事件存在但没进聚合（工具 bug 迹象）：无法判定分配额/诚实上限计数")
    # task-144（dev-coder 在制）：壶空"原样重跑"与"如实 stop 命名"的证据是否存在 —— 缺失 ≠ 0。
    _t144_ev = [ev for _ln, ev in rows if ev.get("event") in ("refill_retry", "stage_stop_named")]
    if not _t144_ev:
        out.append("本账本没有任何 task-144 的 `refill_retry` / `stage_stop_named` 事件 ⇒ "
                   "无法判定「阶段内壶空后有没有把这一轮没成事的格**原样**重跑」与「阶段自然结束"
                   "（stopped=\"\"）却还有分配未成事的格有没有**如实命名** stop 原因」—— "
                   "**缺失 ≠ 0，绝不当'这个洞不存在'通过**（task-144）")
    elif not ((report.get("refill_retry") or {}).get("has_events")
              or (report.get("stage_stop_named") or {}).get("has_events")):
        out.append("task-144 事件存在但没进聚合（工具 bug 迹象）：无法判定阶段自愈/如实收工计数")
    # task-157/158：开路/够不着 + 体力预算 —— 缺失 ≠ 0（旧账本没有这两族事件与字段）。
    _t157_ev = [ev for _ln, ev in rows if ev.get("event") in ("water_far_open", "water_far_blocked")]
    if not _t157_ev:
        out.append("本账本没有任何 task-157 的 `water_far_open` / `water_far_blocked` 事件 ⇒ "
                   "无法判定「够不着的干格有没有先有界开路再重试」以及「开路后仍站不到的格有没有"
                   "如实记 blocked」—— **缺失 ≠ 0，绝不当'没有够不着的格'通过**（task-157）")
    elif not ((report.get("water_far") or {}).get("has_open_events")):
        out.append("task-157 事件存在但没进聚合（工具 bug 迹象）：无法判定开路/够不着计数")
    _t158_ev = [ev for _ln, ev in rows if ev.get("event") == "stamina_budget"]
    _t158_def = [ev for _ln, ev in rows if ev.get("event") == "deferred_by_budget"]
    _t163_ev = [ev for _ln, ev in rows
                if ev.get("event") in ("budget_deferred_tiles", "stage_capped_by_capacity")]
    if not _t158_ev and not _t158_def and not _t163_ev and not (report.get("stamina_budget") or {}).get("has_day_field"):
        out.append("本账本没有任何 task-158/163 的 `stamina_budget` / `deferred_by_budget` / "
                   "`budget_deferred_tiles` / `stage_capped_by_capacity` 事件、"
                   "day_end 也没有 `stamina_budget` 字段 ⇒ 无法判定「今天不浇是不是因为体力预算」"
                   "—— **缺失 ≠ 0，绝不当'今天没用预算'通过**（task-158/163）")
    elif (_t158_ev or _t158_def or _t163_ev) and not (report.get("stamina_budget") or {}).get("has_events"):
        out.append("task-158/163 事件存在但没进聚合（工具 bug 迹象）：无法判定体力预算/延后/容量计数")
    _t163_day = (report.get("stamina_budget") or {}).get("has_defer_tiles_field")
    if _t163_ev and not _t163_day:
        out.append("有 `budget_deferred_tiles` / `stage_capped_by_capacity` 事件，但 day_end 的 "
                   "`stamina_budget.deferred_tiles` / `capacity_capped_tasks` 都没读到 ⇒ "
                   "无法判定日级延后格数（缺失 ≠ 0，绝不当 0 通过；task-163）")
    # task-20 / task-164：工具门槛封格（clump 工具等级/种类不够 ⇒ 动手前拦下、0 次 use_tool）。
    _t164_ev = [ev for _ln, ev in rows if ev.get("event") == "blocked_by_tool"]
    _t164_sum = [ev for _ln, ev in rows if ev.get("event") == "blocked_by_tool_summary"]
    if not _t164_ev and not _t164_sum:
        out.append("本账本没有任何 task-20 的 `blocked_by_tool` / `blocked_by_tool_summary` 事件 ⇒ "
                   "无法判定「当天有没有格是因工具等级/种类不够而**动手前**被封的」（诚实跳过、0 次 "
                   "use_tool）—— **缺失 ≠ 0，绝不当'没有工具门槛挡路'通过**（task-20/task-164）")
    elif (_t164_ev or _t164_sum) and not (report.get("tool_gate") or {}).get("has_events"):
        out.append("task-20 事件存在但没进聚合（工具 bug 迹象）：无法判定工具门槛封格计数")
    elif (report.get("tool_gate") or {}).get("min_level_missing"):
        out.append(f"{((report.get('tool_gate') or {}).get('min_level_missing'))} 格 `blocked_by_tool` "
                   "没写 `min_level` ⇒ 无法判定那些格到底要几级工具（缺失 ≠ 0，绝不默认 0 级）")
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
            # task-158：日级体力预算留痕（缺 ⇒ 空 dict ⇒ 报告写【无法判定】，绝不当作"今天没用预算"）
            "stamina_budget": as_dict(end.get("stamina_budget")),
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
    # task-88 ④：`seed_gate` 的"钱不够"分叉 —— 买不起种子 ⇒ **未发起购买**，不是任务失败。
    seed_gate_lines = []
    seed_gate_blocked_lines = []
    seed_gate_money = None
    seed_gate_price = None
    for ln, ev in rows:
        seed_name = str(ev.get("event") or "")
        if seed_name == "seed_gate":
            seed_gate_lines.append(ln)
            gate_money = ev.get("money")
            gate_price = ev.get("seed_price")
            gate_seeds = as_int(ev.get("seeds"))
            if ((gate_money is not None and gate_price is not None
                 and as_num(gate_money) < as_num(gate_price)) or gate_seeds == 0):
                seed_gate_blocked_lines.append(ln)
                if seed_gate_money is None:
                    seed_gate_money = gate_money
                if seed_gate_price is None:
                    seed_gate_price = gate_price
            continue
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
    # task-84：死苗/放弃格（Mod `farm.deadCrops` / `farm.dryDeadCrops` + 当天认输的窗口外干格）。
    # 缺失 ⇒【无法判定】（缺失 ≠ 0）；`dry_dead>0` 且 `no_work`、`gave_up` 非空却自称 VERIFIED
    # 在 cat_missed 1i 判红；这里只做聚合与呈现。
    dc = {
        "dead_crops": None, "dead_crops_status": None,
        "dry_dead": None, "dry_dead_status": None,
        "gave_up_count": 0, "gave_up_tiles": [],
        "lines": [], "missing_fields": [],
        "no_work_uncleared": [], "verified_with_gave_up": [], "bad_fields": [],
        "summary_events": 0, "summary_lines": [],
    }
    _dc_seen = set()
    for ln, ev in rows:
        _name = str(ev.get("event") or "")
        if _name == "dead_crops_summary":
            dc["summary_events"] += 1
            dc["summary_lines"].append(ln)
            continue
        if _name != "day_end":
            continue
        dc["lines"].append(ln)
        for _k in ("dead_crops", "dead_crops_status", "dry_dead", "dry_dead_status"):
            if _k in ev:
                _dc_seen.add(_k)
                if ev.get(_k) is not None:
                    dc[_k] = ev.get(_k)
        if "gave_up_tiles" in ev:
            _dc_seen.add("gave_up_tiles")
            _tiles = as_list(ev.get("gave_up_tiles"))
            if len(_tiles) > len(dc["gave_up_tiles"]):
                dc["gave_up_tiles"] = _tiles
            dc["gave_up_count"] = max(dc["gave_up_count"], len(_tiles))
        _status, _dd, _gu, _note = dry_dead_check(ev)
        if _status == "bad":
            dc["bad_fields"].append(ln)
        elif _status == "no_work_uncleared":
            dc["no_work_uncleared"].append(ln)
        elif _status == "ok" and as_list(_gu) and ev.get("verified") is True:
            dc["verified_with_gave_up"].append(ln)
    dc["missing_fields"] = [k for k in ("dead_crops", "dead_crops_status", "dry_dead",
                                         "dry_dead_status", "gave_up_tiles") if k not in _dc_seen]
    dc["has_fields"] = bool(_dc_seen)
    dead_crops = dc
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
        # task-88 ④：`seed_gate` 这条"钱不够"分叉（≠ 购买任务失败）
        "seed_gate": len(seed_gate_lines),
        "seed_gate_lines": seed_gate_lines,
        "afford_blocked": len(seed_gate_blocked_lines),
        "afford_blocked_lines": seed_gate_blocked_lines,
        "seed_gate_money": seed_gate_money,
        "seed_gate_price": seed_gate_price,
    }
    # task-91：**盈余材料换种子钱**（task-55）—— 逐叠 `sell` + 汇总 `surplus_sell` + `surplus_sell_skip`。
    # 口径：`below_keep` / `surplus_sell_skip` / `cannot_afford` **都不是失败**；`sell` 成交当天
    # `money` 不变是**设计**（钱要等下一次 NewDay 由游戏结算）⇒ 这里只呈现，绝不判红。
    sell_ok_n = sell_failed_n = sell_below_keep = 0
    sell_lines: list[int] = []
    sell_failed_lines: list[int] = []
    sell_strategies: dict[str, int] = {}
    surplus_ok = surplus_sold = surplus_below_keep = 0
    surplus_lines: list[int] = []
    surplus_money = None
    skip_lines: list[int] = []
    skip_short_max = 0
    skip_below_keep = 0
    skip_reason = ""
    for ln, ev in rows:
        name = str(ev.get("event") or "")
        if name == "sell":
            sell_lines.append(ln)
            strat = str(ev.get("strategy") or "?")
            sell_strategies[strat] = sell_strategies.get(strat, 0) + 1
            if ev.get("ok") is True:
                sell_ok_n += 1
                if ev.get("below_keep") is True:
                    sell_below_keep += 1
            else:
                sell_failed_n += 1
                sell_failed_lines.append(ln)
        elif name == "surplus_sell":
            surplus_lines.append(ln)
            if ev.get("ok") is True:
                surplus_ok += 1
            surplus_sold += as_int(ev.get("sold"))
            if ev.get("below_keep") is True:
                surplus_below_keep += 1
            if surplus_money is None:
                surplus_money = as_dict(ev.get("trigger")).get("money")
        elif name == "surplus_sell_skip":
            skip_lines.append(ln)
            short = as_int(ev.get("short"))
            if short > skip_short_max:
                skip_short_max = short
            if ev.get("below_keep") is True:
                skip_below_keep += 1
            if not skip_reason and ev.get("reason"):
                skip_reason = str(ev.get("reason"))[:200]
    # 「卖了盈余材料、但**次日** buy 仍为 0」的两候选（task-91 ③）：只给证据行，不下结论
    _bounds = []
    for _i, _d in enumerate(days):
        _lo = _d.get("start_line") or 0
        _hi = (days[_i + 1].get("start_line") or 10 ** 9) if _i + 1 < len(days) else 10 ** 9
        _bounds.append((_lo, _hi))
    _day_sell_ok = [0] * len(days)
    _day_buy = [0] * len(days)
    for ln, ev in rows:
        name = str(ev.get("event") or "")
        if name not in ("sell", "buy"):
            continue
        for _i, (_lo, _hi) in enumerate(_bounds):
            if _lo <= ln < _hi:
                if name == "sell" and ev.get("ok") is True:
                    _day_sell_ok[_i] += 1
                elif name == "buy":
                    _day_buy[_i] += 1
                break
    sold_no_buy_next = [
        {"day": days[_i].get("label"), "line": days[_i].get("start_line")}
        for _i in range(len(days) - 1)
        if _day_sell_ok[_i] > 0 and _day_buy[_i + 1] == 0
    ]
    sell = {
        "total": sell_ok_n + sell_failed_n,
        "ok": sell_ok_n,
        "failed": sell_failed_n,
        "below_keep": sell_below_keep,
        "lines": sell_lines,
        "failed_lines": sell_failed_lines,
        "strategies": sell_strategies,
        "surplus_events": len(surplus_lines),
        "surplus_ok": surplus_ok,
        "surplus_sold": surplus_sold,
        "surplus_below_keep": surplus_below_keep,
        "surplus_lines": surplus_lines,
        "skips": len(skip_lines),
        "skip_lines": skip_lines,
        "skip_short_max": skip_short_max,
        "skip_below_keep": skip_below_keep,
        "skip_reason": skip_reason,
        "money_at_sell": surplus_money,
        "sold_days_with_no_buy_next": sold_no_buy_next,
    }
    # task-102（`9b09735`）：**背包空格死锁**闭环 —— free_slots / buy 尝试数 / `buy_no_space` /
    # 腾格卖出（`why=need_slot`）/ 当日钱变化 / `slept_without_work` / `modal_dismiss_failed`。
    # 口径（Lead m05068）：**买不到不是失败** —— 没空格（`buy_no_space`）、钱不够、没货架一律不判红；
    # `slept_without_work` 是"0 农场动作又有活 ⇒ 拒绝睡觉、当天不推进"，是守卫生效的证据（那天会以
    # needs_review / `no_day_progress` 如实停住），**不是"睡眠失败"**；`modal_dismiss_failed` 本工具
    # 只点名次数（`tools\verify-run3.py` 不判它 ⇒ 判红会造成两边反向）。
    # 缺字段 ⇒【无法判定】（缺失 ≠ 0、≠ "没发生"），见 build_undecidable。
    bag = {
        "buy_attempts": 0, "buy_lines": [],
        "buy_no_space": 0, "buy_no_space_lines": [],
        "buy_receipt_codes": {}, "buy_no_space_receipts": 0,
        "slot_sells": 0, "slot_sell_lines": [],
        "slept_without_work": 0, "slept_without_work_lines": [],
        "modal_dismiss_failures": 0, "modal_dismiss_failed_lines": [],
        "free_slots": None, "free_slots_status": "", "free_slots_lines": [],
        "why_counts": {},
    }
    for ln, ev in rows:
        name = str(ev.get("event") or "")
        if name == "buy":
            bag["buy_attempts"] += 1
            bag["buy_lines"].append(ln)
            # 旧账本（task-102 之前）没有 `buy_no_space` 事件，只有回执码 ⇒ 从回执里补认一次
            _rc = str(ev.get("receipt") or "")
            _code = (_rc.split(":")[0].strip() if ":" in _rc
                     else str(ev.get("code") or "").strip())
            if _code:
                bag["buy_receipt_codes"][_code] = bag["buy_receipt_codes"].get(_code, 0) + 1
            if _code in ("no_space", "no_inventory_space"):
                bag["buy_no_space_receipts"] += 1
        elif name == "buy_no_space":
            bag["buy_no_space"] += 1
            bag["buy_no_space_lines"].append(ln)
            if not bag["free_slots_status"]:
                bag["free_slots_status"] = str(ev.get("free_slots_status") or "")
        elif name == "slept_without_work":
            bag["slept_without_work"] += 1
            bag["slept_without_work_lines"].append(ln)
        elif name == "modal_dismiss_failed":
            bag["modal_dismiss_failures"] += 1
            bag["modal_dismiss_failed_lines"].append(ln)
        if name in ("sell", "surplus_sell", "surplus_sell_skip"):
            why = str(ev.get("why") or "")
            if why:
                bag["why_counts"][why] = bag["why_counts"].get(why, 0) + 1
            trig = as_dict(ev.get("trigger"))
            if bag["free_slots"] is None and trig.get("freeSlots") is not None:
                bag["free_slots"] = as_int(trig.get("freeSlots"))
                bag["free_slots_status"] = str(trig.get("freeSlotsStatus")
                                               or bag["free_slots_status"])
                bag["free_slots_lines"].append(ln)
            if why == "need_slot":
                bag["slot_sells"] += 1
                bag["slot_sell_lines"].append(ln)
    bag["has_free_slots_evidence"] = bag["free_slots"] is not None
    bag["slot_gate_tried"] = bag["slot_sells"] > 0
    # 当日钱变化：最后一个会话的 `day_start.money` → 最后一条 `day_end.final.money`
    _bag_money_start = None
    _bag_money_end = None
    if sessions:
        _bag_sess = sessions[-1]
        _bag_sd = as_dict(_bag_sess.get("start"))
        if "money" in _bag_sd:
            _bag_money_start = as_int(_bag_sd.get("money"))
        _bag_des = _bag_sess.get("day_ends") or []
        if _bag_des:
            _bag_fd = as_dict(as_dict(_bag_des[-1][1]).get("final"))
            if "money" in _bag_fd:
                _bag_money_end = as_int(_bag_fd.get("money"))
    bag["money_start"] = _bag_money_start
    bag["money_end"] = _bag_money_end
    bag_space = bag
    # ---- task-111：LLM 收工复盘（task-59）+ 跨日教训库（task-58/82），Lead m05325
    # 口径：**"模型没学到东西"不是失败**（空 notes / 空库 / 0 新增只记信息）；只有三条完整性红
    # 在 `llm_review_findings()` 里。教训库路径由 journal 推导（`X.jsonl` ⇒ `X-lessons.json`，
    # 与 brain `_derive_lessons_path` 同一约定；**不新增命令行开关**）。
    LESSONS_MAX = 20  # brain/agentfarm/planner.py: `LESSONS_MAX = 20`
    _rev_events = [(ln, ev) for ln, ev in rows if ev.get("event") == "review_llm"]
    _rev_failed = [(ln, ev) for ln, ev in rows if ev.get("event") == "review_llm_failed"]
    _ls_events = [(ln, ev) for ln, ev in rows if ev.get("event") == "lessons"]
    _ls_load_failed = [(ln, ev) for ln, ev in rows if ev.get("event") == "lessons_load_failed"]
    _ls_save_failed = [(ln, ev) for ln, ev in rows if ev.get("event") == "lessons_save_failed"]
    _ls_rejected = [(ln, ev) for ln, ev in rows if ev.get("event") == "lessons_rejected"]
    # task-114：拒收事件按行号归属到日（用于判「连续 ≥2 天 dropped>0 且 kept==0」）。
    # 本函数里 `day_of_line` 还定义在后面，这里自带一份只依赖 `days` 的边界表。
    _lr_bounds = []
    for _i, _d in enumerate(days):
        _bs = _d.get("start_line") or 0
        _be = (days[_i + 1].get("start_line") - 1) if _i + 1 < len(days) else 10 ** 9
        _lr_bounds.append((_bs, _be, _d.get("label"), _i))

    def _lr_day_of(lineno):
        for _bs, _be, _lab, _i in _lr_bounds:
            if _bs <= lineno <= _be:
                return _lab, _i
        return None, None
    llm_review = {
        "lessons_max": LESSONS_MAX,
        "review_events": len(_rev_events), "review_lines": [ln for ln, _ in _rev_events],
        "notes_count": 0, "notes_chars": 0, "rejected_count": 0, "truncated": 0,
        "without_notes_lines": [],
        "failed_events": len(_rev_failed), "failed_lines": [ln for ln, _ in _rev_failed],
        "failed_reasons": [], "reviewed_days": [],
        "lessons_events": len(_ls_events), "lessons_lines": [ln for ln, _ in _ls_events],
        "lessons_total": None, "lessons_added": None, "lessons_dropped": None,
        "lessons_path": "", "over_limit_lines": [],
        "load_failed": len(_ls_load_failed),
        "load_failed_lines": [ln for ln, _ in _ls_load_failed], "load_errors": [],
        "save_failed": len(_ls_save_failed),
        "save_failed_lines": [ln for ln, _ in _ls_save_failed], "save_errors": [],
        # task-114：拒收（`lessons_rejected`）—— 只记信息 + 连续全丢时给 warn，绝不判红
        "rejected_events": len(_ls_rejected), "rejected_lines": [ln for ln, _ in _ls_rejected],
        "rejected_dropped": 0, "rejected_kept": None, "rejected_reasons": [],
        "rejected_by_day": {}, "warn_all_rejected_run": 0, "warn_all_rejected_days": [],
        # task-118 A（task-120）：不可信条目的读写证据 —— skipped_untrusted>0 = 防洗白生效（好事）
        "rejected_untrusted": 0, "rejected_untrusted_lines": [],
        "lessons_written": None, "lessons_skipped_untrusted": None,
        "all_untrusted_by_day": {}, "warn_all_untrusted_run": 0, "warn_all_untrusted_days": [],
        "file_status": "unknown", "file_path": "", "file_count": None, "file_error": "",
        # task-136 C（task-139）：教训素材质量 —— `lessons.hint_dropped` = 当天被"矛盾判据"丢掉的 hint 条数
        # （每日重置）。丢弃是设计行为（防污染生效的正面证据）⇒ 不判红；只有可证伪形态给 ⚠（不进 rc）。
        "hint_dropped_total": 0, "hint_dropped_days": [], "hint_dropped_lines": [],
        "hint_dropped_bad_lines": [], "hint_dropped_gt_added_lines": [],
        "file_empty_hint": None, "warn_empty_hint_no_count": [],
        "has_events": bool(_rev_events or _rev_failed or _ls_events or _ls_load_failed
                           or _ls_save_failed or _ls_rejected),
    }
    for _ln, ev in _rev_events:
        notes = ev.get("notes")
        if isinstance(notes, list):
            llm_review["notes_count"] += len(notes)
            llm_review["notes_chars"] += sum(len(str(n)) for n in notes)
        if not (isinstance(notes, list) and any(str(n).strip() for n in notes)):
            llm_review["without_notes_lines"].append(_ln)
        rej = ev.get("rejected")
        llm_review["rejected_count"] += len(rej) if isinstance(rej, list) else 0
        if ev.get("truncated") is True:
            llm_review["truncated"] += 1
        dk = ev.get("day_key")
        if isinstance(dk, list) and dk:
            llm_review["reviewed_days"].append("/".join(str(x) for x in dk))
    for _ln, ev in _rev_failed:
        llm_review["failed_reasons"].append(str(ev.get("reason") or ""))
        rej = ev.get("rejected")
        llm_review["rejected_count"] += len(rej) if isinstance(rej, list) else 0
    for _ln, ev in _ls_events:
        _t = as_int(ev.get("total"))
        if _t is not None and _t > LESSONS_MAX:
            llm_review["over_limit_lines"].append(_ln)
        # task-120：`written==0 且 skipped_untrusted>0`（库被外部整版污染）逐日留痕，供连续 warn
        _lw = as_int(ev.get("written"), None)
        _lsu = as_int(ev.get("skipped_untrusted"), None)
        _lab, _di = _lr_day_of(_ln)
        if _di is not None and _lw == 0 and (_lsu or 0) > 0:
            llm_review["all_untrusted_by_day"][_di] = {
                "label": _lab, "written": _lw, "skipped_untrusted": _lsu, "line": _ln}
        # task-136 C（task-139）：`hint_dropped` —— 只累加/留痕，绝不判红
        _hd = as_int(ev.get("hint_dropped"), None)
        if _hd is None:
            llm_review["hint_dropped_bad_lines"].append(_ln)
        else:
            llm_review["hint_dropped_total"] += _hd
            if _hd > 0:
                llm_review["hint_dropped_days"].append(_lab or "?")
                llm_review["hint_dropped_lines"].append(_ln)
            _added_hd = ev.get("added")
            if isinstance(_added_hd, list) and _hd > len(_added_hd):
                llm_review["hint_dropped_gt_added_lines"].append(_ln)
    if _ls_events:
        _ln, _last = _ls_events[-1]
        llm_review["lessons_total"] = as_int(_last.get("total"))
        _added = _last.get("added")
        llm_review["lessons_added"] = len(_added) if isinstance(_added, list) else None
        llm_review["lessons_dropped"] = as_int(_last.get("dropped"))
        llm_review["lessons_path"] = str(_last.get("path") or "")
        llm_review["lessons_written"] = as_int(_last.get("written"), None)
        llm_review["lessons_skipped_untrusted"] = as_int(_last.get("skipped_untrusted"), None)
    for _ln, ev in _ls_load_failed:
        llm_review["load_errors"].append(str(ev.get("error") or ""))
    for _ln, ev in _ls_save_failed:
        llm_review["save_errors"].append(str(ev.get("error") or ""))
    # task-114：拒收统计（信息项）—— dropped / kept 两侧都看，只有"连续 ≥2 天全丢"才 warn
    for _ln, ev in _ls_rejected:
        _dr = as_int(ev.get("dropped"), None)
        _kp = as_int(ev.get("kept"), None)
        if _dr is not None:
            llm_review["rejected_dropped"] += _dr
        if _kp is not None:
            llm_review["rejected_kept"] = _kp
        for _rs in (ev.get("reasons") or [])[:8]:
            _rst = str(_rs)
            if _rst and _rst not in llm_review["rejected_reasons"]:
                llm_review["rejected_reasons"].append(_rst)
        # task-118 A / task-120：不可信条数（信息项；>0 = 库里有外部条目，不是失败）
        _ut = as_int(ev.get("untrusted"), None)
        if _ut is not None:
            llm_review["rejected_untrusted"] += _ut
            if _ut > 0:
                llm_review["rejected_untrusted_lines"].append(_ln)
        _lab, _di = _lr_day_of(_ln)
        if _di is not None and (_dr or 0) > 0 and _kp == 0:
            llm_review["rejected_by_day"][_di] = {
                "label": _lab, "dropped": _dr, "kept": _kp, "line": _ln}
    _run = _best = 0
    for _i in range(len(days)):
        if _i in llm_review["rejected_by_day"]:
            _run += 1
            _best = max(_best, _run)
        else:
            _run = 0
    llm_review["warn_all_rejected_run"] = _best
    if _best >= 2:
        llm_review["warn_all_rejected_days"] = [
            (llm_review["rejected_by_day"].get(_i) or {}).get("label")
            for _i in sorted(llm_review["rejected_by_day"])]
    # task-120：同一套「连续 ≥2 天」算法，判据换成 written==0 且 skipped_untrusted>0
    _run = _best2 = 0
    for _i in range(len(days)):
        if _i in llm_review["all_untrusted_by_day"]:
            _run += 1
            _best2 = max(_best2, _run)
        else:
            _run = 0
    llm_review["warn_all_untrusted_run"] = _best2
    if _best2 >= 2:
        llm_review["warn_all_untrusted_days"] = [
            (llm_review["all_untrusted_by_day"].get(_i) or {}).get("label")
            for _i in sorted(llm_review["all_untrusted_by_day"])]
    _lp = None
    try:
        _jp = os.path.abspath(str(path))
        _lp = os.path.join(os.path.dirname(_jp),
                           os.path.splitext(os.path.basename(_jp))[0] + "-lessons.json")
    except Exception:  # noqa: BLE001 - 路径怪就只记 unknown
        _lp = None
    if _lp is not None:
        llm_review["file_path"] = _lp
        if not os.path.exists(_lp):
            llm_review["file_status"] = "missing"
        else:
            try:
                with open(_lp, encoding="utf-8") as _fh:
                    _raw = json.load(_fh)
                if isinstance(_raw, dict):
                    _raw = _raw.get("lessons")
                if not isinstance(_raw, list):
                    llm_review["file_status"] = "corrupt"
                    llm_review["file_error"] = "not_a_list"
                else:
                    llm_review["file_status"] = "ok"
                    llm_review["file_count"] = len(_raw)
                    # task-139：库侧交叉核 —— `hint` 为空的条目 = "矛盾 hint 已被丢掉"的落地形态
                    _empty_hint = sum(1 for _it in _raw
                                      if isinstance(_it, dict)
                                      and not str(_it.get("hint") or "").strip())
                    llm_review["file_empty_hint"] = _empty_hint
                    if (_empty_hint > 0 and not llm_review.get("hint_dropped_bad_lines")
                            and not (llm_review.get("hint_dropped_total") or 0)):
                        # 只有"字段在位且计数恒 0"才算口径打架；字段整体缺失由 ⚠① 覆盖（老账本不重复报）
                        llm_review["warn_empty_hint_no_count"].append(_lp)
                    if len(_raw) > LESSONS_MAX:
                        llm_review["over_limit_lines"].append(None)
            except Exception as exc:  # noqa: BLE001 - 损坏就判红，别把工具带崩
                llm_review["file_status"] = "corrupt"
                llm_review["file_error"] = f"{type(exc).__name__}: {exc}"
    llm_reds = llm_review_findings(llm_review)
    # task-124/task-130：review 兜底 / 弃权 / 换片连发 —— **修复生效的证据**（本身不判红；
    # verify-run3.py 对这四个事件零命中 ⇒ 判红会两边反向）。只给可证伪形态的 ⚠ 警告：
    #   ①`plot_exhausted_burst` 当天却自称 VERIFIED（连发=没目标的证据，与 VERIFIED 互斥）；
    #   ②弃权（`review_only_no_target`）之后当天 ended_reason 仍说"守卫仍说还有活"（弃权没生效）；
    #   ③兜底路径抛异常（`review_only_fallback_failed`，防御性事件）。
    _rv_fb = [(ln, ev) for ln, ev in rows if ev.get("event") == "review_only_fallback"]
    _rv_fbf = [(ln, ev) for ln, ev in rows if ev.get("event") == "review_only_fallback_failed"]
    _rv_nt = [(ln, ev) for ln, ev in rows if ev.get("event") == "review_only_no_target"]
    _rv_burst = [(ln, ev) for ln, ev in rows if ev.get("event") == "plot_exhausted_burst"]
    # task-134 A（与 task-124/task-130 同族）：①`resume_reevaluate` = 回跨片区 leftover 前清掉
    # 任务级 `no_target`（走路→空转→再走路的死循环的**解药**，是修复生效的证据）；
    # ②`no_progress_burst` = 回片区/换作业区连续无产出触顶 ⇒ 按既有有界机制**诚实收尾**（stuck，
    # leftover 如实保留）。两者都**不是失败**，只有"当天却自称 VERIFIED"这类可证伪形态给 ⚠。
    _rv_resume = [(ln, ev) for ln, ev in rows if ev.get("event") == "resume_reevaluate"]
    _rv_np = [(ln, ev) for ln, ev in rows if ev.get("event") == "no_progress_burst"]
    review_fallback = {
        "fallback_events": len(_rv_fb), "fallback_lines": [ln for ln, _ in _rv_fb],
        "fallback_work_spot": 0, "fallback_pending_walk": 0, "fallback_walked": 0,
        "fallback_tiles": 0, "fallback_intents": {},
        "failed_events": len(_rv_fbf), "failed_lines": [ln for ln, _ in _rv_fbf],
        "failed_errors": [],
        "no_target_events": len(_rv_nt), "no_target_lines": [ln for ln, _ in _rv_nt],
        "no_target_pending": 0, "no_target_tiles": [],
        "burst_events": len(_rv_burst), "burst_lines": [ln for ln, _ in _rv_burst],
        "burst_max": 0, "burst_zones": [],
        "resume_events": len(_rv_resume), "resume_lines": [ln for ln, _ in _rv_resume],
        "resume_cleared": {},
        "no_progress_events": len(_rv_np), "no_progress_lines": [ln for ln, _ in _rv_np],
        "no_progress_max": 0, "no_progress_tiles": 0, "no_progress_sources": {},
        "warn_no_progress_verified_days": [], "warn_no_progress_verified_lines": [],
        "warn_burst_verified_days": [], "warn_burst_verified_lines": [],
        "warn_no_target_still_guarded_days": [], "warn_no_target_still_guarded_lines": [],
        "has_events": bool(_rv_fb or _rv_fbf or _rv_nt or _rv_burst or _rv_resume or _rv_np),
    }
    for _ln, ev in _rv_fb:
        _src = str(ev.get("source") or "")
        if _src == "work_spot":
            review_fallback["fallback_work_spot"] += 1
        elif _src == "pending_walk":
            review_fallback["fallback_pending_walk"] += 1
        _pt = as_int(ev.get("plot_tiles"), None)
        if _pt is None:
            _pt = as_int(ev.get("tiles"))
        review_fallback["fallback_tiles"] += _pt or 0
        if ev.get("walked") is True:
            review_fallback["fallback_walked"] += 1
        for _tk in (ev.get("intents") or []):
            _tks = str(_tk)
            review_fallback["fallback_intents"][_tks] = \
                review_fallback["fallback_intents"].get(_tks, 0) + 1
    for _ln, ev in _rv_fbf:
        review_fallback["failed_errors"].append(str(ev.get("error") or ""))
    for _ln, ev in _rv_nt:
        review_fallback["no_target_pending"] += as_int(ev.get("pending")) or 0
        for _tl in (ev.get("tiles") or [])[:12]:
            if isinstance(_tl, list) and len(_tl) >= 2:
                review_fallback["no_target_tiles"].append([_tl[0], _tl[1]])
    for _ln, ev in _rv_burst:
        review_fallback["burst_max"] = max(review_fallback["burst_max"], as_int(ev.get("count")) or 0)
        _z = str(ev.get("zone") or "")
        if _z and _z not in review_fallback["burst_zones"]:
            review_fallback["burst_zones"].append(_z)
        _lab, _di = _lr_day_of(_ln)
        if _di is not None and _di < len(days) and days[_di].get("verified") is True:
            review_fallback["warn_burst_verified_lines"].append(_ln)
            if _lab not in review_fallback["warn_burst_verified_days"]:
                review_fallback["warn_burst_verified_days"].append(_lab)
    for _ln, ev in _rv_nt:
        _lab, _di = _lr_day_of(_ln)
        if _di is None or _di >= len(days):
            continue
        _der = str(days[_di].get("ended_reason") or "")
        if "守卫仍说还有活" in _der:
            review_fallback["warn_no_target_still_guarded_lines"].append(_ln)
            if _lab not in review_fallback["warn_no_target_still_guarded_days"]:
                review_fallback["warn_no_target_still_guarded_days"].append(_lab)
    # task-134 A：①`resume_reevaluate` 清了哪些任务级 no_target（次数 = 死循环被解药的证据）；
    # ②`no_progress_burst` 的连发次数/格数/来源，以及"当天却自称 VERIFIED"这条可证伪 ⚠。
    for _ln, ev in _rv_resume:
        for _tk in (ev.get("cleared") or []):
            _tks = str(_tk)
            review_fallback["resume_cleared"][_tks] = \
                review_fallback["resume_cleared"].get(_tks, 0) + 1
    for _ln, ev in _rv_np:
        review_fallback["no_progress_max"] = max(review_fallback["no_progress_max"],
                                                 as_int(ev.get("count")) or 0)
        review_fallback["no_progress_tiles"] += as_int(ev.get("tiles")) or 0
        _src = str(ev.get("source") or "?")
        review_fallback["no_progress_sources"][_src] = \
            review_fallback["no_progress_sources"].get(_src, 0) + 1
        _lab, _di = _lr_day_of(_ln)
        if _di is not None and _di < len(days) and days[_di].get("verified") is True:
            review_fallback["warn_no_progress_verified_lines"].append(_ln)
            if _lab not in review_fallback["warn_no_progress_verified_days"]:
                review_fallback["warn_no_progress_verified_days"].append(_lab)
    # task-132（task-123 在制 `buy_partial`）：**买一半不是失败** —— `n = min(buy_count, money//price)`，
    # `n >= 1` 就买下，`n < wanted` 时另记 `buy_partial`（**不进** `failed`、不判红）。旧账本没有该事件、
    # `buy` 也没有 `wanted` 字段 ⇒【无法判定】（缺失 ≠ 0 ≠ "没发生"）。两条**可证伪** ⚠ 警告（不判红：
    # `tools\verify-run3.py` 对 `buy_partial` 零命中，判红会两边反向）：
    #   ①`buy` 自称成交（`ok=true`）却 `count < wanted`，而当天没有对应的 `buy_partial` 留痕；
    #   ②同一天既有 `buy_partial`（买到 ≥1）又有 `cannot_afford`（一个都买不起）—— 可能是不同货品的
    #     单价差，也可能判据打架 ⇒ 只提示人工核对，不下结论。
    _bp_partials = [(ln, ev) for ln, ev in rows if ev.get("event") == "buy_partial"]
    _bp_cannot = [(ln, ev) for ln, ev in rows if ev.get("event") == "cannot_afford"]
    buy_partial = {
        "events": len(_bp_partials), "lines": [ln for ln, _ in _bp_partials],
        "items": [], "plans": {}, "bought_total": 0, "wanted_total": 0, "short_total": 0,
        "prices": [], "sources": [], "money": [],
        "cannot_afford_events": len(_bp_cannot),
        "cannot_afford_lines": [ln for ln, _ in _bp_cannot],
        "warn_missing_partial_lines": [], "warn_missing_partial_days": [],
        "warn_cannot_afford_same_day_lines": [], "warn_cannot_afford_same_day_days": [],
        "has_events": bool(_bp_partials),
        "buy_has_wanted": any(ev.get("event") == "buy" and "wanted" in ev for _ln, ev in rows),
    }
    _bp_pairs = set()
    for _ln, ev in _bp_partials:
        _it = str(ev.get("item") or "")
        _b = as_int(ev.get("bought"), None)
        _w = as_int(ev.get("wanted"), None)
        if _it and _it not in buy_partial["items"]:
            buy_partial["items"].append(_it)
        if _b is not None:
            buy_partial["bought_total"] += _b
        if _w is not None:
            buy_partial["wanted_total"] += _w
        if _b is not None and _w is not None:
            buy_partial["short_total"] += max(0, _w - _b)
            _bp_pairs.add((_it, _b, _w))
            if _it:
                _cur = buy_partial["plans"].get(_it) or [0, 0]
                buy_partial["plans"][_it] = [_cur[0] + _b, _cur[1] + _w]
        _pr = as_int(ev.get("price"), None)
        if _pr is not None and _pr not in buy_partial["prices"]:
            buy_partial["prices"].append(_pr)
        _src = str(ev.get("source") or "")
        if _src and _src not in buy_partial["sources"]:
            buy_partial["sources"].append(_src)
        _mn = as_int(ev.get("money"), None)
        if _mn is not None:
            buy_partial["money"].append(_mn)
    for _ln, ev in rows:
        if ev.get("event") != "buy":
            continue
        _c = as_int(ev.get("count"), None)
        _w = as_int(ev.get("wanted"), None)
        if ev.get("ok") is True and _c is not None and _w is not None and _c < _w:
            if (str(ev.get("item") or ""), _c, _w) not in _bp_pairs:
                buy_partial["warn_missing_partial_lines"].append(_ln)
                _lab, _di = _lr_day_of(_ln)
                if _lab and _lab not in buy_partial["warn_missing_partial_days"]:
                    buy_partial["warn_missing_partial_days"].append(_lab)
    if _bp_partials and _bp_cannot:
        _bp_partial_days = {}
        for _ln, _ in _bp_partials:
            _lab, _di = _lr_day_of(_ln)
            _bp_partial_days.setdefault(_di, _lab)
        for _ln, _ in _bp_cannot:
            _lab, _di = _lr_day_of(_ln)
            if _di in _bp_partial_days:
                buy_partial["warn_cannot_afford_same_day_lines"].append(_ln)
                _pdl = _bp_partial_days[_di] or _lab
                if _pdl and _pdl not in buy_partial["warn_cannot_afford_same_day_days"]:
                    buy_partial["warn_cannot_afford_same_day_days"].append(_pdl)
    # 口径（task-132）：`buy_ok` 类"成交"只算**买满 `wanted`** 的整笔；买少了的那笔算 `buy_partial`。
    # 旧账本没有 `wanted` ⇒ 单独计数、如实标注（无法区分是否买满，不硬当"买满"）。
    buy_partial["buy_ok_full"] = 0
    buy_partial["buy_ok_missing_wanted"] = 0
    for _ln, ev in rows:
        if ev.get("event") != "buy" or ev.get("ok") is not True:
            continue
        _w = as_int(ev.get("wanted"), None)
        _c = as_int(ev.get("count"), None)
        if _w is None:
            buy_partial["buy_ok_missing_wanted"] += 1
        elif _c is not None and _c >= _w:
            buy_partial["buy_ok_full"] += 1
    # task-158（体力预算）：`stamina_budget` 每天一条（解释「为什么今天不浇」）+ `deferred_by_budget`
    # 逐任务「只因预算而不做」。两者都**不判红**（当天达不达标由 `checks.watered_outdoor` /
    # `checks.no_unmet_stages` 说话），只给两条可证伪 ⚠：
    #   ① 说"只因预算延后"但当天 `watered_outdoor=true` 且 `final_water.dry==0`（延后了却又说全浇完）；
    #   ② 日级 `day_end.stamina_budget.deferred_by_budget>0` 却没有任何 `deferred_by_budget` 事件（留痕缺）。
    # 缺字段 ⇒【无法判定】（缺失 ≠ 0，也不当作"今天没用预算"）。
    _sb_events = [(ln, ev) for ln, ev in rows if ev.get("event") == "stamina_budget"]
    _sb_defers = [(ln, ev) for ln, ev in rows if ev.get("event") == "deferred_by_budget"]
    _sb_day_field = [d.get("label") for d in days if as_dict(d.get("stamina_budget"))]
    stamina_budget = {
        "events": len(_sb_events), "lines": [ln for ln, _ in _sb_events],
        "max": None, "stamina": None, "water_reserve": None, "capacity": None,
        "water_cost_est": None, "path_allowance": None, "basis": {},
        "deferred_total": 0, "defer_events": len(_sb_defers),
        "defer_lines": [ln for ln, _ in _sb_defers], "defer_tasks": {}, "defer_whys": {},
        "day_field_days": _sb_day_field,
        "warn_deferred_but_watered_lines": [], "warn_defer_missing_lines": [],
        "has_events": bool(_sb_events or _sb_defers or _sb_day_field),
        "has_day_field": bool(_sb_day_field),
    }
    for _ln, ev in _sb_events:
        for _k in ("max", "stamina", "water_reserve", "capacity", "water_cost_est", "path_allowance"):
            _v = as_int(ev.get(_k), None)
            if _v is not None:
                stamina_budget[_k] = _v
        _b = str(ev.get("basis") or "")
        if _b:
            stamina_budget["basis"][_b] = stamina_budget["basis"].get(_b, 0) + 1
        _db = as_int(ev.get("deferred_by_budget"), None)
        if _db:
            stamina_budget["deferred_total"] += _db
    _sb_defer_days = set()
    for _ln, ev in _sb_defers:
        _task = str(ev.get("task") or "?")
        stamina_budget["defer_tasks"][_task] = stamina_budget["defer_tasks"].get(_task, 0) + 1
        _why = str(ev.get("why") or "")
        if _why:
            stamina_budget["defer_whys"][_why] = stamina_budget["defer_whys"].get(_why, 0) + 1
        _lab, _di = _lr_day_of(_ln)
        _sb_defer_days.add(_di)
        if _di < len(days):
            _d = days[_di]
            _fw = as_dict(_d.get("final_water"))
            _ok_all = as_dict(_d.get("checks")).get("watered_outdoor") is True
            try:
                _dry_zero = int(_fw.get("dry")) == 0
            except (TypeError, ValueError):
                _dry_zero = False
            if _ok_all and _dry_zero:
                stamina_budget["warn_deferred_but_watered_lines"].append(_ln)
    for _di, _d in enumerate(days):
        _dbs = as_dict(_d.get("stamina_budget"))
        if as_int(_dbs.get("deferred_by_budget"), 0) and _di not in _sb_defer_days:
            _dl = as_list(_d.get("day_end_lines"))
            if _dl:
                stamina_budget["warn_defer_missing_lines"].append(_dl[0])
    # task-20 / task-164（工具门槛）：clump 工具等级/种类不够（或 `toolOk` 判不出）⇒ **动手之前就拦下**
    # （0 次 use_tool、不白烧体力）。逐格 `blocked_by_tool`（tile/action/stage/zone/kind/need/
    # min_level/reason/note）+ 日级 `blocked_by_tool_summary`（count/tiles/kinds/tools/note）。
    # 口径：**诚实跳过、不判红、不进 rc**（不进 unreachable/refused 两套豁免、也不算"活"）；
    # 唯一可证伪 ⚠：当天自称 `no_work`（`ended_reason` 以 no_work 开头）却存在工具门槛封格 ⇒
    # 提示人工核对「是真敲不动，还是工具够却判不出」（brain 有意不让它进守卫理由，见 longrun.py:2625-2627）。
    # task-163（`budget_deferred_tiles` / `stage_capped_by_capacity`）：体力预算的两条**诚实留痕**
    # （task-158 的延伸）。口径不变：**不判红、不进 rc**（当天达不达标由 checks 说话）；两条可证伪 ⚠：
    #   ① 当天有 `budget_deferred_tiles` 却自称「该做的都做了」（`no_work` + `verified=true`）
    #      ⇒ 人工核对「延后是否真的只发生在有浇水债时」（task-163 的红线锚点）；
    #   ② 同一天有 `budget_deferred_tiles`，但 `day_end.stamina_budget` 显示 `live_crops<=0`
    #      或 `dry<=0`（没有浇水债）⇒ 延后可能已经变成「免罚额度」，同样只警告。
    #   缺字段 ⇒【无法判定】（缺失 ≠ 0）。
    _bdt_events = [(ln, ev) for ln, ev in rows if ev.get("event") == "budget_deferred_tiles"]
    _cap_events = [(ln, ev) for ln, ev in rows if ev.get("event") == "stage_capped_by_capacity"]
    stamina_budget["warn_defer_tiles_but_no_work_lines"] = []
    stamina_budget["warn_defer_without_debt_lines"] = []
    _bdt_tasks: dict[str, int] = {}
    _bdt_count = 0
    for _ln, ev in _bdt_events:
        _task = str(ev.get("task") or "?")
        _cnt = as_int(ev.get("count"), 0) or 0
        _bdt_count += int(_cnt)
        _tot = as_int(ev.get("total"), None)
        _bdt_tasks[_task] = max(_bdt_tasks.get(_task, 0), int(_cnt if _tot is None else _tot))
    _cap_tasks: dict[str, dict] = {}
    for _ln, ev in _cap_events:
        _task = str(ev.get("task") or "?")
        if _task not in _cap_tasks:
            _cap_tasks[_task] = {"limit": as_int(ev.get("limit"), None),
                                 "capacity": as_int(ev.get("capacity"), None)}
    _day_bdt: dict[str, dict] = {}
    _day_cap: dict[str, dict] = {}
    _day_cap_n = 0
    for _d in days:
        _dbs = as_dict(_d.get("stamina_budget"))
        _dt = as_dict(_dbs.get("deferred_tiles"))
        if _dt:
            _day_bdt[str(_d.get("label"))] = {str(k): (as_int(v, 0) or 0) for k, v in _dt.items()}
        _cb = as_dict(_dbs.get("capped_by_capacity"))
        if _cb:
            _day_cap[str(_d.get("label"))] = _cb
        _cc = as_int(_dbs.get("capacity_capped_tasks"), None)
        if _cc:
            _day_cap_n += int(_cc)
    _bdt_days: dict[int, list[int]] = {}
    for _ln, _ev in _bdt_events:
        _lab, _di = _lr_day_of(_ln)
        _bdt_days.setdefault(_di, []).append(_ln)
    for _di, _lns in _bdt_days.items():
        if _di >= len(days):
            continue
        _d = days[_di]
        _dl = as_list(_d.get("day_end_lines"))
        _anchor_line = _dl[0] if _dl else _lns[0]
        if str(_d.get("ended_reason") or "").startswith("no_work") and _d.get("verified") is True:
            stamina_budget["warn_defer_tiles_but_no_work_lines"].append(_anchor_line)
        _dbs = as_dict(_d.get("stamina_budget"))
        _live = as_int(_dbs.get("live_crops"), None)
        _dry = as_int(_dbs.get("dry"), None)
        if (_live is not None and _live <= 0) or (_dry is not None and _dry <= 0):
            stamina_budget["warn_defer_without_debt_lines"].append(_anchor_line)
    stamina_budget["budget_defer_events"] = len(_bdt_events)
    stamina_budget["budget_defer_lines"] = [ln for ln, _ in _bdt_events]
    stamina_budget["budget_defer_tasks"] = _bdt_tasks
    stamina_budget["budget_defer_tiles"] = _bdt_count
    stamina_budget["capacity_events"] = len(_cap_events)
    stamina_budget["capacity_lines"] = [ln for ln, _ in _cap_events]
    stamina_budget["capacity_tasks"] = _cap_tasks
    stamina_budget["capacity_capped_tasks"] = _day_cap_n
    stamina_budget["day_deferred_tiles"] = _day_bdt
    stamina_budget["day_capped_by_capacity"] = _day_cap
    stamina_budget["has_defer_tiles_field"] = bool(_day_bdt or _day_cap)
    stamina_budget["has_events"] = bool(stamina_budget["has_events"] or _bdt_events or _cap_events
                                        or _day_bdt or _day_cap)
    _tt_events = [(ln, ev) for ln, ev in rows if ev.get("event") == "blocked_by_tool"]
    _tt_summaries = [(ln, ev) for ln, ev in rows if ev.get("event") == "blocked_by_tool_summary"]
    tool_gate = {
        "events": len(_tt_events), "lines": [ln for ln, _ in _tt_events],
        "tiles": [], "actions": {}, "stages": {}, "kinds": {}, "needs": {}, "min_levels": {},
        "kind_unknown": 0, "min_level_missing": 0,
        "summary_events": len(_tt_summaries), "summary_lines": [ln for ln, _ in _tt_summaries],
        "summary_counts": [], "summary_tools": {}, "summary_kinds": {},
        "warn_no_work_with_gate_lines": [],
        "has_events": bool(_tt_events or _tt_summaries),
    }
    for _ln, ev in _tt_events:
        _t = ev.get("tile")
        if isinstance(_t, list) and _t and _t not in tool_gate["tiles"]:
            tool_gate["tiles"].append(_t)
        _k = str(ev.get("kind") or "未知")
        tool_gate["kinds"][_k] = tool_gate["kinds"].get(_k, 0) + 1
        if _k in ("未知", "", "None"):
            tool_gate["kind_unknown"] += 1
        _need = str(ev.get("need") or "")
        if _need:
            tool_gate["needs"][_need] = tool_gate["needs"].get(_need, 0) + 1
        _ml = as_int(ev.get("min_level"), None)
        if _ml is None:
            tool_gate["min_level_missing"] += 1
        else:
            tool_gate["min_levels"][str(_ml)] = tool_gate["min_levels"].get(str(_ml), 0) + 1
        _act = str(ev.get("action") or "")
        if _act:
            tool_gate["actions"][_act] = tool_gate["actions"].get(_act, 0) + 1
        _st = str(ev.get("stage") or "")
        if _st:
            tool_gate["stages"][_st] = tool_gate["stages"].get(_st, 0) + 1
    for _ln, ev in _tt_summaries:
        tool_gate["summary_counts"].append(as_int(ev.get("count"), None))
        for _x in as_list(ev.get("tools")):
            tool_gate["summary_tools"][str(_x)] = tool_gate["summary_tools"].get(str(_x), 0) + 1
        for _x in as_list(ev.get("kinds")):
            tool_gate["summary_kinds"][str(_x)] = tool_gate["summary_kinds"].get(str(_x), 0) + 1
    _tt_days = set()
    for _ln, _ev in _tt_events + _tt_summaries:
        _lab, _di = _lr_day_of(_ln)
        _tt_days.add(_di)
    for _di in sorted(_tt_days):
        if _di >= len(days):
            continue
        if str(days[_di].get("ended_reason") or "").startswith("no_work"):
            _dl = as_list(days[_di].get("day_end_lines"))
            if _dl:
                tool_gate["warn_no_work_with_gate_lines"].append(_dl[0])
    # task-134 B（分配额口径）：`stage_shortfall`（阶段分下去的格没做完）/`stage_shortfall_day`
    # （日级 unmet=assigned_undone）/`deferred_tiles`（诚实上限留下的片区待办，**只作 info、
    # 不进 no_unmet_stages**）。三者本身都**不判红**（红由 `checks.no_unmet_stages=false` 说话）；
    # 只有"日级说 `stopped_night=false` 而当天 `ended_reason` 却是 night"这条可证伪形态给 ⚠。
    _sf_stage = [(ln, ev) for ln, ev in rows if ev.get("event") == "stage_shortfall"]
    _sf_day = [(ln, ev) for ln, ev in rows if ev.get("event") == "stage_shortfall_day"]
    _sf_def = [(ln, ev) for ln, ev in rows if ev.get("event") == "deferred_tiles"]
    shortfall = {
        "stage_events": len(_sf_stage), "stage_lines": [ln for ln, _ in _sf_stage],
        "assigned_total": 0, "undone_total": 0, "stopped_kinds": {}, "stage_zones": [],
        "day_events": len(_sf_day), "day_lines": [ln for ln, _ in _sf_day],
        "unmet_max": 0, "plot_pending_max": 0,
        "deferred_events": len(_sf_def), "deferred_lines": [ln for ln, _ in _sf_def],
        "deferred_tiles": 0, "deferred_night": 0,
        "warn_stopped_night_mismatch_lines": [], "warn_stopped_night_mismatch_days": [],
        "has_events": bool(_sf_stage or _sf_day or _sf_def),
        "has_day_fields": any("assigned_undone" in _d or "deferred_tiles" in _d
                              for _s in sessions for _e in (_s.get("day_ends") or [])
                              for _d in [_e[1]]),
    }
    for _ln, _ev in _sf_stage:
        shortfall["assigned_total"] += as_int(_ev.get("assigned")) or 0
        shortfall["undone_total"] += as_int(_ev.get("undone")) or 0
        _st = str(_ev.get("stopped") or "?")
        shortfall["stopped_kinds"][_st] = shortfall["stopped_kinds"].get(_st, 0) + 1
        _z = str(_ev.get("zone") or "")
        if _z and _z not in shortfall["stage_zones"]:
            shortfall["stage_zones"].append(_z)
    for _ln, _ev in _sf_day:
        shortfall["unmet_max"] = max(shortfall["unmet_max"], as_int(_ev.get("unmet")) or 0)
        shortfall["plot_pending_max"] = max(shortfall["plot_pending_max"],
                                            as_int(_ev.get("plot_pending")) or 0)
        _lab, _di = _lr_day_of(_ln)
        if _di is None or _di >= len(days):
            continue
        _der = str(days[_di].get("ended_reason") or "")
        if _ev.get("stopped_night") is False and _der.startswith("night"):
            shortfall["warn_stopped_night_mismatch_lines"].append(_ln)
            if _lab not in shortfall["warn_stopped_night_mismatch_days"]:
                shortfall["warn_stopped_night_mismatch_days"].append(_lab)
    for _ln, _ev in _sf_def:
        shortfall["deferred_tiles"] += as_int(_ev.get("tiles")) or 0
        if _ev.get("night") is True:
            shortfall["deferred_night"] += 1
    # task-144（dev-coder 在制）：阶段内壶空 ⇒ 补水后把"这一轮没成事的已分配格"**原样**重跑
    # （`refill_retry`，不再重算窗口把那几格丢掉）；阶段自然走完（`stopped==""`）却仍有分配未成事的
    # 格 ⇒ 补一个**如实** stop 原因的留痕（`stage_stop_named`）。两者都是**修复生效的证据**、不是
    # 失败（`verify-run3.py` 对这两个名字零命中 ⇒ 判红会两边反向）；只有三条可证伪形态给 ⚠
    # （都不进 red、不进 rc）：①当天重跑条数 > 当天 `refill` 条数；②`ok=true` 却 `tiles=0`（空转）；
    # ③`stage_stop_named` 的 `cause` 缺失/未知、`assigned_undone<=0`、或有过失却 `codes` 全空。
    _rr_events = [(ln, ev) for ln, ev in rows if ev.get("event") == "refill_retry"]
    _rr_refills = [(ln, ev) for ln, ev in rows if ev.get("event") == "refill"]
    _sn_events = [(ln, ev) for ln, ev in rows if ev.get("event") == "stage_stop_named"]
    refill_retry = {
        "events": len(_rr_events), "lines": [ln for ln, _ in _rr_events],
        "ok": sum(1 for _, ev in _rr_events if ev.get("ok") is True),
        "failed": sum(1 for _, ev in _rr_events if ev.get("ok") is not True),
        "tiles_total": sum(as_int(ev.get("tiles")) or 0 for _, ev in _rr_events),
        "stages": sorted({str(ev.get("stage") or "?") for _, ev in _rr_events}),
        "zones": sorted({str(ev.get("zone") or "?") for _, ev in _rr_events}),
        "refill_events_total": len(_rr_refills),
        "refills_today": [as_int(ev.get("refills_today"), None) for _, ev in _rr_events],
        "limits": [as_int(ev.get("limit"), None) for _, ev in _rr_events],
        "stage_refills": [], "stage_limits": [], "stage_refill_by_stage": {},
        "warn_over_retry_lines": [], "warn_empty_lines": [],
        "warn_over_stage_refill_lines": [],
        "has_events": bool(_rr_events),
    }
    _rr_days, _rr_refill_days = {}, {}
    for _ln, _ev in _rr_events:
        _lab, _di = _lr_day_of(_ln)
        if _di is not None:
            _rr_days.setdefault(_di, []).append(_ln)
        if _ev.get("ok") is True and (as_int(_ev.get("tiles")) or 0) == 0:
            refill_retry["warn_empty_lines"].append(_ln)
        # task-144 增量：阶段补水次数 / 阶段上界（`STAGE_REFILL_MAX`）。越界 ⇒ ⚠（不进 rc）。
        _sr = as_int(_ev.get("stage_refills"), None)
        _sl = as_int(_ev.get("stage_limit"), None)
        if _sr is not None:
            refill_retry["stage_refills"].append(_sr)
        if _sl is not None:
            refill_retry["stage_limits"].append(_sl)
        _sr_stage = refill_retry["stage_refill_by_stage"].setdefault(
            str(_ev.get("stage") or "?"), {"stage_refills": None, "stage_limit": None})
        if _sr is not None and (_sr_stage["stage_refills"] is None
                               or _sr > _sr_stage["stage_refills"]):
            _sr_stage["stage_refills"] = _sr
        if _sl is not None:
            _sr_stage["stage_limit"] = _sl
        if _sr is not None and _sl is not None and _sr > _sl:
            refill_retry["warn_over_stage_refill_lines"].append(_ln)
    for _ln, _ev in _rr_refills:
        _lab, _di = _lr_day_of(_ln)
        if _di is not None:
            _rr_refill_days[_di] = _rr_refill_days.get(_di, 0) + 1
    for _di, _lns in _rr_days.items():
        if len(_lns) > _rr_refill_days.get(_di, 0):
            refill_retry["warn_over_retry_lines"].extend(_lns)
    _KNOWN_STOP_CAUSES = ("need_refill", "unreachable", "no_seed", "incomplete")
    stage_stop_named = {
        "events": len(_sn_events), "lines": [ln for ln, _ in _sn_events],
        "causes": {}, "assigned_total": 0, "undone_total": 0, "tiles_listed": 0,
        "codes": {}, "stages": sorted({str(ev.get("stage") or "?") for _, ev in _sn_events}),
        "zones": sorted({str(ev.get("zone") or "?") for _, ev in _sn_events}),
        "warn_bad_cause_lines": [], "warn_no_undone_lines": [], "warn_no_codes_lines": [],
        "has_events": bool(_sn_events),
    }
    for _ln, _ev in _sn_events:
        _cause = str(_ev.get("cause") or "") or "<缺失>"
        stage_stop_named["causes"][_cause] = stage_stop_named["causes"].get(_cause, 0) + 1
        stage_stop_named["assigned_total"] += as_int(_ev.get("assigned")) or 0
        _undone = as_int(_ev.get("assigned_undone")) or 0
        stage_stop_named["undone_total"] += _undone
        stage_stop_named["tiles_listed"] += len(as_list(_ev.get("tiles")))
        for _code in as_list(_ev.get("codes")):
            _c = str(_code or "")
            stage_stop_named["codes"][_c] = stage_stop_named["codes"].get(_c, 0) + 1
        if _cause not in _KNOWN_STOP_CAUSES:
            stage_stop_named["warn_bad_cause_lines"].append(_ln)
        if _undone <= 0:
            stage_stop_named["warn_no_undone_lines"].append(_ln)
        elif not as_list(_ev.get("codes")):
            stage_stop_named["warn_no_codes_lines"].append(_ln)
    # task-133（run9b 的 need_refill 病）：窗口外浇水 + 壶空先补水 —— 两个事件都**不是失败**，
    # 但两条可证伪形态要点名（都只给 ⚠ 警告、不进 red / 不进 rc，`verify-run3.py` 对
    # `water_far_refill` 零命中）：①补水没成（回执不 ok 且水位没涨）当天却把那格浇成了；
    # ②当天补水预算用尽（`tries >= limit`）⇒ 剩下的干格今天注定浇不上。
    _wf_refills = [(ln, ev) for ln, ev in rows if ev.get("event") == "water_far_refill"]
    _wf_fars = [(ln, ev) for ln, ev in rows if ev.get("event") == "water_far"]
    # task-157：够不着 ⇒ 先有界开路（`water_far_open`）再重试；开路之后仍站不到 ⇒ `water_far_blocked`。
    # 两者都**不是失败**（当天达不达标由 checks.watered_outdoor / no_unmet_stages 说话），
    # 只给可证伪形态的 ⚠（开路成功但那格仍干 / blocked 却自称浇完）。
    _wf_opens = [(ln, ev) for ln, ev in rows if ev.get("event") == "water_far_open"]
    _wf_blocks = [(ln, ev) for ln, ev in rows if ev.get("event") == "water_far_blocked"]
    water_far = {
        "refill_events": len(_wf_refills), "refill_lines": [ln for ln, _ in _wf_refills],
        "refill_ok": sum(1 for _, ev in _wf_refills if ev.get("ok") is True),
        "refill_failed": sum(1 for _, ev in _wf_refills if ev.get("ok") is not True),
        "refill_codes": {}, "refill_failed_lines": [], "refill_tiles": [],
        "water_before": [ev.get("water_before") for _, ev in _wf_refills],
        "water_after": [ev.get("water_after") for _, ev in _wf_refills],
        "refill_tries": [as_int(ev.get("tries"), None) for _, ev in _wf_refills],
        "refill_limits": [as_int(ev.get("limit"), None) for _, ev in _wf_refills],
        "budget_exhausted_lines": [],
        "far_events": len(_wf_fars), "far_lines": [ln for ln, _ in _wf_fars],
        "far_ok": sum(1 for _, ev in _wf_fars if ev.get("ok") is True),
        "far_failed": sum(1 for _, ev in _wf_fars if ev.get("ok") is not True),
        "far_causes": {}, "far_cause_missing": 0, "far_tiles": [], "far_need_refill_lines": [],
        "far_retried_after_refill": sum(1 for _, ev in _wf_fars
                                        if ev.get("retried_after_refill") is True),
        "far_tiles_status": {},
        "warn_refill_failed_but_watered_lines": [], "warn_budget_exhausted_lines": [],
        "has_events": bool(_wf_refills or _wf_fars), "has_refill_events": bool(_wf_refills),
        # task-157：开路（够不着 ⇒ 清挡路邻格后重试同一格）与"开路后仍站不到"。
        "open_events": len(_wf_opens), "open_lines": [ln for ln, _ in _wf_opens],
        "open_ok": sum(1 for _, ev in _wf_opens if str(ev.get("code") or "") == "ok"),
        "open_failed": sum(1 for _, ev in _wf_opens if str(ev.get("code") or "") != "ok"),
        "open_codes": {}, "open_cleared_total": 0, "open_tiles": [],
        "blocked_events": len(_wf_blocks), "blocked_lines": [ln for ln, _ in _wf_blocks],
        "blocked_causes": {}, "blocked_tiles": [], "blocked_tries": [],
        "warn_open_but_still_dry_lines": [], "warn_blocked_but_watered_lines": [],
        "has_open_events": bool(_wf_opens or _wf_blocks),
    }
    for _ln, _ev in _wf_refills:
        _c = str(_ev.get("code") or "?")
        water_far["refill_codes"][_c] = water_far["refill_codes"].get(_c, 0) + 1
        _t = _ev.get("tile")
        if isinstance(_t, list) and _t and _t not in water_far["refill_tiles"]:
            water_far["refill_tiles"].append(_t)
        if _ev.get("ok") is not True:
            water_far["refill_failed_lines"].append(_ln)
            _tr, _li = as_int(_ev.get("tries"), None), as_int(_ev.get("limit"), None)
            if _tr is not None and _li is not None and _tr >= _li:
                water_far["budget_exhausted_lines"].append(_ln)
                water_far["warn_budget_exhausted_lines"].append(_ln)
    _wf_ok_days = set()
    for _ln, _ev in _wf_fars:
        _lab, _di = _lr_day_of(_ln)
        if _ev.get("ok") is True:
            _wf_ok_days.add(_di)
        _cause = str(_ev.get("cause") or "")
        if _cause:
            water_far["far_causes"][_cause] = water_far["far_causes"].get(_cause, 0) + 1
            if _cause == "need_refill":
                water_far["far_need_refill_lines"].append(_ln)
        else:
            water_far["far_cause_missing"] += 1
        _st = str(_ev.get("dry_tiles_status") or "")
        if _st:
            water_far["far_tiles_status"][_st] = water_far["far_tiles_status"].get(_st, 0) + 1
        _t = _ev.get("tile")
        if isinstance(_t, list) and _t and _t not in water_far["far_tiles"]:
            water_far["far_tiles"].append(_t)
    # task-157：开路/够不着的逐条统计 + 两条可证伪 ⚠（都**不进 rc**）。
    _wf_dry_after_tiles = set()
    for _ln, _ev in _wf_opens:
        _code = str(_ev.get("code") or "")
        water_far["open_codes"][_code] = water_far["open_codes"].get(_code, 0) + 1
        water_far["open_cleared_total"] += as_int(_ev.get("cleared_count"), 0) or 0
        _t = _ev.get("tile")
        if isinstance(_t, list) and _t and _t not in water_far["open_tiles"]:
            water_far["open_tiles"].append(_t)
    for _ln, _ev in _wf_fars:
        if _ev.get("in_dry_tiles_after") is True:
            _t = _ev.get("tile")
            if isinstance(_t, list) and _t:
                _wf_dry_after_tiles.add(tuple(_t))
    for _ln, _ev in _wf_opens:
        if str(_ev.get("code") or "") != "ok":
            continue
        _t = _ev.get("tile")
        if isinstance(_t, list) and _t and tuple(_t) in _wf_dry_after_tiles:
            water_far["warn_open_but_still_dry_lines"].append(_ln)
    _wf_watered_tiles = set()
    for _ln, _ev in _wf_fars:
        if _ev.get("ok") is True:
            _t = _ev.get("tile")
            if isinstance(_t, list) and _t:
                _wf_watered_tiles.add(tuple(_t))
    _wf_blocked_by_day: dict[int, list[tuple[list[Any], int]]] = {}
    for _ln, _ev in _wf_blocks:
        _cause = str(_ev.get("cause") or "?")
        water_far["blocked_causes"][_cause] = water_far["blocked_causes"].get(_cause, 0) + 1
        _t = _ev.get("tile")
        if isinstance(_t, list) and _t and _t not in water_far["blocked_tiles"]:
            water_far["blocked_tiles"].append(_t)
        water_far["blocked_tries"].append(as_int(_ev.get("attempts"), None))
        _lab, _di = _lr_day_of(_ln)
        _wf_blocked_by_day.setdefault(_di, []).append((_t if isinstance(_t, list) else [], _ln))
    # ⚠①：开路回执 ok（或清了挡路格）但同一格当天最后一次证据仍是"还在 dryTiles 里" ⇒ 开路不等于浇上水。
    # ⚠②：某格被 blocked（确实没浇上）而当天 `watered_outdoor=true` 且 `final_water.dry==0`、
    #      且那一格当天没有任何 ok 的 `water_far` ⇒ 账本自相矛盾（谁把它浇上的？）。
    for _di, _items in _wf_blocked_by_day.items():
        if _di >= len(days):
            continue
        _d = days[_di]
        _fw = _d.get("final_water") if isinstance(_d.get("final_water"), dict) else {}
        _ok_all = (_d.get("checks") or {}).get("watered_outdoor") is True
        try:
            _dry_zero = int(_fw.get("dry")) == 0
        except (TypeError, ValueError):
            _dry_zero = False
        for _t, _ln in _items:
            if _ok_all and _dry_zero and tuple(_t) not in _wf_watered_tiles:
                water_far["warn_blocked_but_watered_lines"].append(_ln)
    # 可证伪 ⚠①：补水没成（回执不 ok、水位也没涨）当天却把那格浇成了 —— 回执/水位有一边不可信。
    for _ln, _ev in _wf_refills:
        if _ev.get("ok") is True:
            continue
        _wb, _wa = _ev.get("water_before"), _ev.get("water_after")
        if isinstance(_wb, int) and isinstance(_wa, int) and _wa > _wb:
            continue                       # 水确实变多 = 补上了（回执可能不准，brain 判据同此）
        _lab, _di = _lr_day_of(_ln)
        if _di in _wf_ok_days:
            water_far["warn_refill_failed_but_watered_lines"].append(_ln)
    # task-172：①`harvest_gave_up`（如实放弃 = 「该做没做」的证据，**不是豁免**）
    #            ②`ripeCrops`（看着熟，`Crop.fullyGrown`）vs `readyCrops`（真能收，`readyForHarvest()`）
    #              对账 + 窗口 `tiles[].ready`/`ripe` 交叉（task-169 病根一眼可见）。
    harvest_gave_up = {
        "events": 0, "lines": [], "tiles": [], "tile_count": 0, "attempts": 0,
        "limits": [], "codes": {}, "days": [],
        "warn_gave_up_but_verified_lines": [],
        "has_events": False,
    }
    for _ln, _ev in rows:
        if _ev.get("event") != "harvest_gave_up":
            continue
        harvest_gave_up["events"] += 1
        harvest_gave_up["lines"].append(_ln)
        _tl = _ev.get("tile", _ev.get("tiles"))
        if isinstance(_tl, (list, tuple)) and len(_tl) == 2 and all(isinstance(_v, int) for _v in _tl):
            _tl = [_tl]
        for _t in (_tl or []):
            if isinstance(_t, (list, tuple)) and len(_t) == 2:
                try:
                    harvest_gave_up["tiles"].append((int(_t[0]), int(_t[1])))
                except (TypeError, ValueError):
                    pass
        _at = as_int(_ev.get("attempts"), None)
        if _at is not None:
            harvest_gave_up["attempts"] += _at
        _lm = as_int(_ev.get("limit"), None)
        if _lm is not None:
            harvest_gave_up["limits"].append(_lm)
        for _c in (_ev.get("codes") or []):
            harvest_gave_up["codes"][str(_c)] = harvest_gave_up["codes"].get(str(_c), 0) + 1
        _lab, _di = _lr_day_of(_ln)
        if _di is not None:
            harvest_gave_up["days"].append(_di)
    harvest_gave_up["days"] = sorted(set(harvest_gave_up["days"]))
    harvest_gave_up["tile_count"] = len(set(harvest_gave_up["tiles"]))
    harvest_gave_up["has_events"] = harvest_gave_up["events"] > 0
    for _di in harvest_gave_up["days"]:
        _d = days[_di] if 0 <= _di < len(days) else None
        if _d is not None and _d.get("verified") is True:
            _hw = _d.get("day_end_lines") or []
            harvest_gave_up["warn_gave_up_but_verified_lines"].append(_hw[0] if _hw else _d.get("start_line"))
    crop_ready = {
        "days_with_fields": 0, "ripe_total": 0, "ready_total": 0, "diff_total": 0,
        "ripe_without_ready_lines": [], "window_tiles": 0, "window_ready_true": 0,
        "window_ready_null": 0, "window_ripe_true": 0, "window_ripe_not_ready_lines": [],
        "has_fields": False, "note": "",
    }
    for _ln, _ev in rows:
        if _ev.get("event") != "day_end":
            continue
        _farm = (_ev.get("final") or {}).get("farm") or {}
        _rp, _rd = as_int(_farm.get("ripeCrops"), None), as_int(_farm.get("readyCrops"), None)
        if _rp is None and _rd is None:
            continue
        crop_ready["days_with_fields"] += 1
        crop_ready["has_fields"] = True
        if _rp is not None:
            crop_ready["ripe_total"] += _rp
        if _rd is not None:
            crop_ready["ready_total"] += _rd
        if _rp is not None and _rd is not None:
            _diff = _rp - _rd
            crop_ready["diff_total"] += _diff
            if _diff > 0:
                crop_ready["ripe_without_ready_lines"].append(_ln)

    def _tile_dicts(node, depth=0):
        if depth > 5:
            return
        if isinstance(node, dict):
            if "ready" in node or "ripe" in node:
                yield node
            for _v in node.values():
                yield from _tile_dicts(_v, depth + 1)
        elif isinstance(node, (list, tuple)):
            for _v in node:
                yield from _tile_dicts(_v, depth + 1)

    for _ln, _ev in rows:
        for _t in _tile_dicts(_ev):
            crop_ready["window_tiles"] += 1
            if _t.get("ready") is True:
                crop_ready["window_ready_true"] += 1
            elif _t.get("ready") is None:
                crop_ready["window_ready_null"] += 1
            if _t.get("ripe") is True:
                crop_ready["window_ripe_true"] += 1
            if _t.get("ripe") is True and _t.get("ready") is False:
                crop_ready["window_ripe_not_ready_lines"].append(_ln)
    # task-179（dev task-176 `037e599`）：`tiles[].readySource` 三态记账 ——
    #   `"game"`=真调了游戏 `HoeDirt.readyForHarvest()`；`"fields"`=反射不可用、字段判据与 IL
    #   **逐条等价**（**正常等价路径，不是 fail-open**）；`None`=判不了（⇒【无法判定】，绝不当
    #   false/通过）。缺键（有 `ready` 却没有 `readySource`）= 旧 Mod 形态 ⇒【无法判定·旧 Mod】。
    #   null 占比 ≥ 半数 ⇒ fail-closed 过头风险，只给 ⚠、不进 rc。
    crop_ready.update({
        "ready_source_game": 0, "ready_source_fields": 0, "ready_source_null": 0,
        "ready_source_other": {}, "ready_source_seen": 0,
        "ready_source_missing_tiles": 0, "ready_source_missing_lines": [],
        "harvest_method_missing_lines": [], "has_ready_source": False,
        "warn_null_heavy": False,
    })
    for _ln, _ev in rows:
        for _t in _tile_dicts(_ev):
            if "readySource" in _t:
                crop_ready["has_ready_source"] = True
                _rs = _t.get("readySource")
                if _rs == "game":
                    crop_ready["ready_source_game"] += 1
                elif _rs == "fields":
                    crop_ready["ready_source_fields"] += 1
                elif _rs is None:
                    crop_ready["ready_source_null"] += 1
                else:
                    _rk = str(_rs)
                    crop_ready["ready_source_other"][_rk] = \
                        crop_ready["ready_source_other"].get(_rk, 0) + 1
            elif "ready" in _t:
                crop_ready["ready_source_missing_tiles"] += 1
                if _ln not in crop_ready["ready_source_missing_lines"]:
                    crop_ready["ready_source_missing_lines"].append(_ln)
            if ("crop" in _t) and ("harvestMethod" not in _t):
                if _ln not in crop_ready["harvest_method_missing_lines"]:
                    crop_ready["harvest_method_missing_lines"].append(_ln)
    crop_ready["ready_source_seen"] = (
        crop_ready["ready_source_game"] + crop_ready["ready_source_fields"]
        + crop_ready["ready_source_null"] + sum(crop_ready["ready_source_other"].values()))
    crop_ready["warn_null_heavy"] = bool(
        crop_ready["ready_source_seen"]
        and crop_ready["ready_source_null"] * 2 >= crop_ready["ready_source_seen"])
    if not crop_ready["has_fields"]:
        crop_ready["note"] = ("账本层没有 ripeCrops/readyCrops（`day_end.final.farm` 白名单 "
                              "brain longrun.py:1690-1692 不含）⇒ 只能记【无法判定】；"
                              "要判定请用 observe?detail=full 的 farm.readyCrops 采样")
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
        "sell": sell,
        # task-70：种子经济（task-67 的种子三事件；与 buy 一起才是守卫死锁的完整指纹）
        "seed_economy": seed_economy,
        # task-84：死苗/放弃格（`dead_crops`/`dry_dead`/`gave_up_tiles`；缺失 ⇒【无法判定】）
        "dead_crops": dead_crops,
        # task-102：背包空格死锁（free_slots / buy_no_space / 腾格卖出 / slept_without_work /
        # modal_dismiss_failed；买不到不是失败，缺失 ⇒【无法判定】）
        "bag_space": bag_space,
        # task-132（task-123 在制）：量力而行买种子 —— 买一半**不是失败**；两条可证伪 ⚠ 警告
        "buy_partial": buy_partial,
        # task-133：窗口外浇水 + 壶空先补水（壶空=前置条件、**不是「够不着」**；两条可证伪 ⚠）
        "water_far": water_far,
        # task-172：收获如实放弃（不是豁免分子）+ 「看着熟 vs 真能收」对账
        "harvest_gave_up": harvest_gave_up,
        "crop_ready": crop_ready,
        "stamina_budget": stamina_budget,
        "tool_gate": tool_gate,
        # task-134 B：分配额口径（阶段没做完 / 日级 unmet / 诚实上限 deferred；均 info、不判红）
        "shortfall": shortfall,
        # task-144（dev-coder 在制）：壶空先补水再"原样重跑"（refill_retry）+ 阶段如实 stop 原因
        # （stage_stop_named）—— 修复生效的证据，不判红；三条可证伪形态只给 ⚠
        "refill_retry": refill_retry,
        "stage_stop_named": stage_stop_named,
        # task-111：LLM 收工复盘 / 跨日教训库（task-58/59/82；只有三条完整性红，其余信息项）
        "llm_review": llm_review,
        # task-124/task-130：review 兜底（work_spot/pending_walk）/ 弃权 / 换片连发
        # —— 修复生效的证据，不判红；只有 burst+VERIFIED、弃权后守卫仍抱怨 给 ⚠ 警告
        "review_fallback": review_fallback,
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
    # 日级豁免有上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)，越界由 checks.unreachable_within_bound 说话。
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
    # task-78/task-80：上界自检（账本 bound_basis / 上界 vs 自算 attempted − encircled）。
    # day_end 没写 attempted/bound 时退回同一天的 summary 事件（run6 就是 day_end 缺 attempted、
    # summary 里有 attempted=42 的形状）；两边都没有才算【无法判定】。
    _att = _last_day_end.get("attempted")
    if _att is None:
        _att = _u_sum.get("attempted")
    _enc = _last_day_end.get("encircled")
    if _enc is None:
        _enc = _u_sum.get("encircled")
    _bounds = {
        "u": _last_day_end.get("unreachable_bound")
        if _last_day_end.get("unreachable_bound") is not None else _u_sum.get("bound"),
    }
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
    _bounds["r"] = (_last_day_end.get("refused_bound")
                    if _last_day_end.get("refused_bound") is not None else _r_sum.get("bound"))
    _b_chk_u = bound_self_check(basis_field=_last_day_end.get("bound_basis"),
                                attempted=_att, encircled=_enc,
                                ledger_bound=_bounds["u"])
    _b_chk_r = bound_self_check(basis_field=_last_day_end.get("bound_basis"),
                                attempted=_att, encircled=_enc,
                                ledger_bound=_bounds["r"])
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
        # 政策：**不计当天硬失败**、当天记 blocked、**次日重试**；日级豁免上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)。
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
        # task-78/task-80：上界**基数**（attempted − encircled）与自算上界；账本更大 ⇒ status=inflated
        "bound_basis": (_u_sum.get("bound_basis") if _u_sum.get("bound_basis") is not None
                        else _last_day_end.get("bound_basis")),
        "bound_basis_ledger": _last_day_end.get("bound_basis"),
        "unreachable_basis_self": _b_chk_u[1],
        "unreachable_bound_self": _b_chk_u[2],
        "unreachable_bound_status": _b_chk_u[0],
        "unreachable_bound_note": _b_chk_u[3],
        # task-63/task-66：被游戏拒绝（till 的 tool_ineffective/precondition_failed）＝ 环境挡路第四形态。
        # 政策：不计当天硬失败、当天封格、次日重试；日级豁免上界 max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)，
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
        "refused_basis_self": _b_chk_r[1],
        "refused_bound_self": _b_chk_r[2],
        "refused_bound_status": _b_chk_r[0],
        "refused_bound_note": _b_chk_r[3],
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
    # task-88：`cat_self_report` 要按**目标窗口**（`--window N`）而不是 `finish.days` 判自洽。
    report["window_days"] = as_int(getattr(args, "window", 3), 3)
    self_report = cat_self_report(report)
    report["categories"] = {
        "manual": cat_manual(all_sessions, args.top),
        "missed": (cat_missed(sessions, args.top) + llm_reds)[:args.top],
        "wasted": (cat_wasted(sessions, args.top) + self_report)[:args.top],
        "ineffective": cat_ineffective(sessions, args.top),
        "sleep": cat_sleep(sessions, args.top, args.stamina_full, args.sleep_pct),
        "environment": cat_environment(all_sessions, args.top),
    }
    report["categories_total"] = {
        "manual": len(manual_all),
        "missed": len(cat_missed(sessions, 0)) + len(llm_reds),
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
    #
    # task-88（Lead m04300）：窗口口径 —— 与 `tools\verify-run3.py` 的"尾部窗口"同义。
    #   * 窗口 = 最后 `--window N` 天（默认 3）；窗口**外**的日级红 ⇒ `history_problems`（逐条列出、
    #     **不进退出码**）；窗口**内**照常 fatal。
    #   * `连续 VERIFIED 天数 < N` ⇒ 本跑没达标，不降级（维持原判）。
    #   * 事件级"瞬间态"class-1（cancel / stage_no_target / stage_exhausted / plot_exhausted）
    #     当天 `verified=true` 且 `no_unmet_stages=true` ⇒ 降级 `settled`（info，逐条列出）。
    #   * 无日期归属的**全局红**（GLOBAL_RED_SUBJECTS）永远 fatal。
    windows = as_int(getattr(args, "window", 3), 3)
    tail_streak = 0
    for day_row in reversed(days):
        if day_row.get("verified") is True:
            tail_streak += 1
        else:
            break
    window_active = windows > 0 and tail_streak >= windows
    window_labels = {d.get("label") for d in days[-windows:]} if windows > 0 else set()
    day_bounds = []
    for i, sess in enumerate(sessions):
        start = sess["start_line"]
        stop = (sessions[i + 1]["start_line"] - 1) if i + 1 < len(sessions) else None
        day_bounds.append((start, stop, days[i].get("label") if i < len(days) else None))

    def day_of_line(lineno):
        if lineno is None:
            return None
        for start, stop, label in day_bounds:
            if lineno >= start and (stop is None or lineno <= stop):
                return label
        return None

    red_all, history_all, settled_all = [], [], []
    for items in (cat_manual(all_sessions, 0),
                  cat_missed(sessions, 0) + llm_reds,
                  cat_wasted(sessions, 0) + cat_self_report(report)):
        for item in items:
            if not is_red_finding(item):
                continue
            if item.get("settled"):
                settled_all.append(item)
                continue
            subject = str(item.get("subject") or "")
            label = day_of_line(item.get("line"))
            if subject in GLOBAL_RED_SUBJECTS or label is None:
                red_all.append(item)
                continue
            if window_active and label not in window_labels:
                history_all.append(item)
                continue
            red_all.append(item)
    report["window"] = {
        "days": windows,
        "tail_streak": tail_streak,
        "active": window_active,
        "labels": [d.get("label") for d in (days[-windows:] if windows > 0 else [])],
        "history_total": len(history_all),
        "settled_total": len(settled_all),
    }
    report["history_problems"] = {
        "total": len(history_all),
        "subjects": sorted({str(item.get("subject")) for item in history_all}),
        "lines": sorted({item["line"] for item in history_all if item.get("line") is not None}),
        "items": [{"line": item.get("line"), "subject": item.get("subject"),
                   "summary": item.get("summary"), "hint": item.get("hint")}
                  for item in history_all],
    }
    report["settled"] = {
        "total": len(settled_all),
        "subjects": sorted({str(item.get("subject")) for item in settled_all}),
        "lines": sorted({item["line"] for item in settled_all if item.get("line") is not None}),
        "items": [{"line": item.get("line"), "subject": item.get("subject"),
                   "summary": item.get("summary"), "hint": item.get("hint")}
                  for item in settled_all],
    }
    report["categories"]["history"] = history_all[:args.top]
    report["categories_total"]["history"] = len(history_all)
    report["categories"]["settled"] = settled_all[:args.top]
    report["categories_total"]["settled"] = len(settled_all)
    report["red"] = {
        "total": len(red_all),
        "subjects": sorted({str(item.get("subject")) for item in red_all}),
        "lines": sorted({item["line"] for item in red_all if item.get("line") is not None}),
        "advisory": bool(getattr(args, "advisory", False)),
        "window": windows,
        "tail_streak": tail_streak,
        "window_active": window_active,
        "history_total": len(history_all),
        "settled_total": len(settled_all),
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
    ("event:water_far / water_far_unavailable (task-50 / task-133)",
     "信息项：窗口外远距浇水；`ok=false` + `given_up=true` = '窗口外干格够不着'的直接证据。"
     "task-133 的新字段：`cause`（**`need_refill` = 壶空 ⇒ 不是够不着**）/`refills`/`refill_limit`/"
     "`retried_after_refill`/`in_dry_tiles_before|after`/`dry_tiles_status`；"
     "旧账本没有这些字段 ⇒ `<缺失>`（缺失 ≠ 0）"),
    ("event:water_far_refill (task-133)",
     "信息项：窗口外浇水**前**的一次补水（壶空=前置条件，一天有界 `tries/limit`；"
     "`water_after > water_before` 即算补上、回执可能不准）**不是失败**；"
     "只两条可证伪 ⚠（补水没成却浇成 / 当天补水预算用尽），本工具不判红、不进 rc"),
    ("event:stage_shortfall / stage_shortfall_day / deferred_tiles (task-134 B)",
     "信息项：分配额口径 —— 阶段 `assigned_undone>0`（非诚实上限）⇒ 当天 unmet（红由 "
     "`checks.no_unmet_stages=false` 说话，本工具不重复判）；`plot_pending` = 片区还剩几格"
     "（只供守卫/换片/resume）；`deferred_tiles` = 体力/夜里收工/撞 budget 留下的片区待办，"
     "**只作 info、绝不进 no_unmet_stages**；唯一可证伪 ⚠ = 日级 `stopped_night=false` 而当天 "
     "`ended_reason` 是 night（口径打架，只警告）"),
    ("event:water_far_open / water_far_blocked / stamina_budget / deferred_by_budget (task-157/158)",
     "信息项：**都不是失败**（`verify-run3.py` 对这四个名字零命中 ⇒ 本工具不判红、不进 rc）；"
     "当天达不达标一律由 `checks.watered_outdoor` / `checks.no_unmet_stages` 说话。"
     "`water_far_open` = 够不着的干格先**有界开路**（清掉挡路邻格）再重试同一格（code/attempt/limit/"
     "cleared_count；**开路成功 ≠ 浇上水**）；`water_far_blocked` = 开路后仍站不到 ⇒ 如实记没浇上"
     "（cause∈no_route/unreachable/need_refill/truncated/no_evidence/not_watered）；"
     "`stamina_budget` = 每天一条体力预算（reserve/capacity/basis∈farm/conservative）；"
     "`deferred_by_budget` = 某任务**只因预算**被延后。四条可证伪 ⚠（只警告）：①开路成功但那格当天"
     "最后仍在 dryTiles 里；②有格 blocked 而当天却自称户外浇水达标（dry=0）；③说「只因预算延后」"
     "却当天自称浇完；④日级 `deferred_by_budget>0` 却没有对应事件。"
     "旧账本没有这些事件/字段 ⇒ `<缺失>` +【无法判定】（缺失 ≠ 0）"),
    ("event:budget_deferred_tiles / stage_capped_by_capacity + day_end.stamina_budget 子键 (task-163)",
     "信息项：**诚实留痕、不是失败、不判红、不进 rc**（`verify-run3.py` 对这两名零命中）。"
     "`budget_deferred_tiles` = 日级/日初：某任务有 count 格被**体力预算**显式延后"
     "（task/count/total/targets；`{task: n}` 汇总在 `day_end.stamina_budget.deferred_tiles`）"
     "⇒ 守卫不再把这些格算作『还有活』；`stage_capped_by_capacity` = stage 级：分配额被当天容量"
     "上限卡住（task/limit/capacity/live_crops/dry/water_reserve ⇒ 只分配 capacity 格）；日级子键"
     "`capacity_capped_tasks`（int）与 `capped_by_capacity{task:{limit,capacity}}`。"
     "两条可证伪 ⚠（只警告、不进 rc）：①当天有延后却自称『该做的都做了』（`no_work` + "
     "`verified=true`）⇒ 核对「延后是否只在体力 ≤ water_reserve **且** 有浇水债时生效」"
     "（task-163 红线）；②同日有延后但 `stamina_budget` 没有浇水债（`live_crops<=0`/`dry<=0`）"
     "⇒ 延后可能变成免罚额度。旧账本/旧日缺字段 ⇒ `<缺失>` +【无法判定】（缺失 ≠ 0）"),
    ("event:blocked_by_tool / blocked_by_tool_summary (task-20/task-164)",
     "信息项：**诚实跳过、不是失败、不判红、不进 rc** —— clump（树桩/大木头/巨石/陨石…）的工具"
     "等级或种类不够（或 `toolOk` 判不出 ⇒ fail-closed 不挥）时，**动手之前**就封格（0 次 "
     "`use_tool`、不白烧体力），当天 `blocked`、次日工具升级后自动重试；这些格**不算活、不进守卫"
     "理由**（否则一块暂时敲不动的巨石会让人永远收不了工）。逐格 `blocked_by_tool`（tile/action/"
     "stage/zone/kind/**need**（「<tool>≥<等级>」文本，不是 `tool` 字段）/min_level/reason/note）+ "
     "日级 `blocked_by_tool_summary`（count/tiles/kinds/tools）。`tools/verify-run3.py` 对这两名"
     "零命中 ⇒ 判红会两边反向，故只给一条**可证伪 ⚠**（不进 rc）：当天自称 `no_work`（没活）却存在"
     "工具门槛封格 ⇒ 提示人工核对「真敲不动 vs 工具够却判不出」。旧账本没有这两事件 ⇒ `<缺失>` +"
     "【无法判定】（缺失 ≠ 0）；`min_level` 缺失 ⇒【无法判定】等级，绝不默认 0 级"),
    ("event:refill_retry / stage_stop_named (task-144)",
     "信息项：**修复生效的证据**、不是失败（`verify-run3.py` 对两名零命中 ⇒ 本工具不判红、不进 rc）。"
     "`refill_retry` = 阶段内壶空 ⇒ 补水后把这一轮没成事的已分配格**原样**重跑（不再重算窗口把格子丢掉）；"
     "`stage_stop_named` = 阶段自然走完（`stopped==\"\"`）却仍有分配未成事的格 ⇒ 补**如实** stop 原因"
     "（cause∈need_refill/unreachable/no_seed/incomplete）。只三条可证伪 ⚠：①当天重跑条数 > 当天 `refill` "
     "条数；②`refill_retry{ok=true, tiles=0}` 空转；③`stage_stop_named` 的 cause 缺失/未知、"
     "`assigned_undone<=0`、或有过失却 `codes` 全空。旧账本没有这两个事件 ⇒ `<缺失>` +【无法判定】（缺失 ≠ 0）"),
    ("event:seed_gate / stage_midway_leftover (task-15)",
     "信息项：种子闸门（种子/钱不够 ⇒ till/plant 被跳过，不算硬失败）+ 阶段中途遗留"),
    ("event:no_seed_for_sale / cannot_afford / seed_unavailable_today (task-67)",
     "种子经济（信息项，**不是硬失败**）：货架没种子 / 留够 K 包买不起 / 买不到结论**当天失效**留痕；"
     "与头部 `购买:` 计数一起看 —— 买不到却没有失效留痕 = run6 那种守卫死锁（建议 0i）"),
    ("surplus_sell / surplus_sell_skip（task-55、task-91）",
     "种子经济·盈余材料换钱（信息项，**不是失败、绝不判红**）：`surplus_sell` = 本轮卖盈余材料汇总"
     "（sold 件数 / ok_count 叠数 / below_keep / trigger{money,threshold,emptyDirt}；"
     "**钱要等下一次 NewDay 才结算 ⇒ 当天 money 不变是设计**）；"
     "`surplus_sell_skip` = 想卖但没有材料超过保留线（short=缺口 g）⇒ 不是失败；"
     "逐叠字段见 `sell.strategy/keep/below_keep/slot/qid/stack`"),
    ("dead_crops_summary / day_end.dead_crops|dry_dead|gave_up_tiles（task-84）",
     "死苗/放弃格（**两条红 + 一条警告**）：`dead_crops`=Mod `farm.deadCrops`（全农场枯死格数）、"
     "`dry_dead`=Mod `farm.dryDeadCrops`（枯死**且没浇**，0.7.27 新字段）、"
     "`gave_up_tiles`=当天认输的窗口外干格坐标。口径：**死苗不浇水**（`dry` 只算活苗；死苗走 `clear_dead`，"
     "且 `clear_dead` 排在 water 之前）；`dry_dead>0` 而 `ended_reason` 以 `no_work` 开头 ⇒ 判红"
     "（`missed:dry_dead_uncleared`，verify-run3.py:803-808 同判 problem）；"
     "`gave_up_tiles` 非空却自称 VERIFIED ⇒ **只警告不判红**"
     "（`warn:verified_with_gave_up`，Lead m04997：真洗白通道已被 verify-run3 的 "
     "`watered_outdoor=true` + `final_water.dry>0` 自相矛盾闸门堵住，认输格当天被解决时判红即假红）；"
     "字段缺失（旧账本）⇒ 只进【无法判定】、绝不判红也不当通过；头部'死苗/放弃格'行 + 建议 0m"),
    ("buy_no_space / slept_without_work / modal_dismiss_failed（task-102、`9b09735`）",
     "背包空格死锁闭环（**全部不判红**）；头部'种子经济/背包'行 + 建议 0n："
     "`buy_no_space` = 回执 `no_space`（背包没空格）⇒ 当天不再重试 buy（`item/price/attempt/"
     "free_slots_status/reason`）—— **买不到不是失败**；"
     "`slept_without_work` = 0 农场动作又有活 ⇒ **拒绝睡觉、当天不推进**"
     "（`why/farm_actions/reasons/note`；是守卫生效的证据、**不是睡眠失败**，那天会以 needs_review / "
     "`no_day_progress` 停住）；`modal_dismiss_failed` = 关模态时桥报错（`menu/reason`）——"
     "`tools\\verify-run3.py` 不判它 ⇒ 本工具只点名次数（判红会两边反向）；"
     "`free_slots` 取自 `sell`/`surplus_sell`/`surplus_sell_skip` 的 `trigger.freeSlots`，"
     "缺失 ⇒ 写 `<缺失>` + 【无法判定】、绝不当 0；`sell` 成交当天 `money` 不变是设计（次日结算）"),
    ("review_llm / review_llm_failed / lessons / lessons_load_failed / lessons_save_failed"
     "（task-58/59/82、Lead m05325）",
     "LLM 收工复盘 + 跨日教训库（头部'LLM 复盘/教训库'行 + 建议 0o）：**"
     "只有三条完整性红** —— ①`review_llm` 声称成功却一条 notes 都没有（`missed:review_llm_without_notes`）"
     "②教训库条数超上限（`missed:lessons_over_limit`，brain `LESSONS_MAX=20`；事件 `total` 或落盘 "
     "`<journal>-lessons.json` 条数）③教训库读不了/文件损坏（`missed:lessons_load_failed`："
     "`lessons_load_failed` 事件或落盘 JSON 解析失败）；**「模型没学到东西」不是失败**（空 notes 列表、"
     "空库、本日 0 新增、复盘失败 `review_llm_failed`、写失败 `lessons_save_failed` 一律只记信息）；"
     "`recent_decisions` 的条数/长度看头部`决策:`行（task-58 给每条补了 terminal/leftover/"
     "unreachable/refused/where，无坐标）；旧账本没有这些事件 ⇒ 头部 `<缺失>` + 【无法判定】"
     "（缺失 ≠ 0，绝不当'模型没学到东西'通过）"),
    ("lessons_rejected（task-114 F1、`brain/agentfarm/longrun.py:1674`）",
     "教训库**拒收留痕**（信息项，**拒收本身不判红** —— 文件被外部改过/结构不符时拒收是正确行为）："
     "`path/dropped/reasons/kept/note`；头部'LLM 复盘/教训库'行里有可 grep 的 `拒收 N 次 / M 条（原因…）`；"
     "只有 `dropped>0` 且 `kept==0` **连续 ≥2 天**时给 `warn:lessons_all_rejected` 可视行"
     "（只警告、不判红、不进 rc）；缺 `kept` 字段 ⇒ 只进【无法判定】（缺失 ≠ 0）"),
    ("lessons_rejected.untrusted / lessons.written|skipped_untrusted（task-118 A、task-120）",
     "不可信条目与**防洗白生效**的直接证据（**全部不判红**）：`untrusted`=这次载入被判不可信的条数"
     "（没有 `src` 标记/旧格式/外部改过 ⇒ 不抢 20 名额、注入行带 `[外部条目·未验证]` 前缀、**绝不回写**）；"
     "`written`=真正落盘的条数（只写 `src=agentfarm`）、`skipped_untrusted`=落盘时跳过的不可信条数；"
     "头部'LLM 复盘/教训库'行有可 grep 的 `教训库写入 N 条 / 跳过 M 条（不可信）/ 拒收 K 条（其中不可信 J 条）`；"
     "`skipped_untrusted>0` 是**好事**（防洗白生效），只有 `skipped_untrusted>0 且 written==0` **连续 ≥2 天**"
     "才给 `warn:lessons_all_untrusted` 可视行（库被外部整版污染，只警告、不进 rc）；"
     "缺 `written`/`skipped_untrusted`/`untrusted` ⇒ 只进【无法判定】（缺失 ≠ 0，绝不当'没有不可信条目'通过）"),
    ("review_only_fallback / review_only_fallback_failed / review_only_no_target / "
     "plot_exhausted_burst（task-124、task-130）",
     "review 兜底与换片连发（**本身一律不判红** —— 它们是 task-124 修复生效的证据，"
     "verify-run3.py 对这四个名字零命中 ⇒ 判红会两边反向）：①`review_only_fallback` = review 独苗"
     "却有活 ⇒ 换成能落地的意图（`source=work_spot`：按观测里看得见的待浇/待收/待清作物出简报）"
     "或把人带回跨片 leftover（`source=pending_walk` + `walked`）；②`review_only_no_target` = 兜底"
     "也拿不出目标 ⇒ 把守卫抱怨的 leftover 如实记为「当天放弃」（`pending`/`tiles`，次日重试、"
     "不碰判定字段）；③`plot_exhausted_burst` = 同一秒 ≥5 次换片（`count`/`zone`；brain "
     "`PLOT_EXHAUSTED_BURST=5`）⇒ 按既有有界机制收尾；④`review_only_fallback_failed` = 兜底出简报"
     "抛异常（防御性，正常路径不该出现）。头部'review 兜底/换片连发'行 + 建议 0p；**只给可证伪形态的 "
     "⚠ 警告**：burst 当天却自称 VERIFIED（连发=没目标的证据，与 VERIFIED 互斥）/ 弃权后台 `ended_reason` "
     "仍说『守卫仍说还有活』（弃权没生效）/ 兜底抛异常；旧账本没有这些事件 ⇒ 头部 `<缺失>` + "
     "【无法判定】（缺失 ≠ 0，绝不当'没发生'通过）"),
    ("buy_partial（task-123 在制、task-132 收录）",
     "种子经济·量力而行（信息项，**买一半不是失败** —— `tools\\verify-run3.py` 对该事件零命中 ⇒ "
     "本工具不判红、不进 rc）：下单量 `n = min(buy_count, money//price)`，`n >= 1` 就买下，"
     "`n < wanted` 时另记 `buy_partial`（`item`/`bought`/`wanted`/`price`/`price_shelf`/`price_cfg`/"
     "`money`/`source`/`ok`/`code`；缺的种子等次日钱结算后再补）；`n == 0` 一个都买不起 ⇒ 记 "
     "`cannot_afford` 且**一个请求都不发**。`buy_ok` 类成交只算**买满 `wanted`** 的整笔"
     "（旧账本没有 `wanted` ⇒ 单独计数、无法区分是否买满）。头部'部分购买'行 + 建议 0p-2；"
     "**只给两条可证伪形态的 ⚠ 警告**：①`buy` 自称成交却 `count < wanted` 且当天没有对应 "
     "`buy_partial`（量力而行必须留痕）；②同日既有 `buy_partial` 又有 `cannot_afford`（可能是不"
     "同货品单价差、也可能判据打架，只提示人工核对）。旧账本没有该事件/字段 ⇒ 头部 `<缺失>` + "
     "【无法判定】（缺失 ≠ 0，绝不当'没出现过买一半'通过）"),
    ("lessons.hint_dropped（task-136 C、task-139 收录）",
     "教训素材质量（信息项，**丢弃是设计行为、不判红** —— `tools\\verify-run3.py` 对该字段零命中 ⇒ "
     "本工具不判红、不进 rc）：复盘给的 `hint` 若与 `symptom`/`evidence` 矛盾，brain 用 "
     "`planner.hint_contradicts_evidence()` 把它丢掉（`hint` 置空），当天累计写进 `lessons.hint_dropped`"
     "（每日重置）⇒ 它是**防污染生效的正面证据**。头部'教训素材质量'行给可 grep 的 "
     "`入库 N 条 / hint 丢弃 M 条 / 拒收 K 次（原因…） / 库大小 J` + 建议 0o；"
     "**只给三条可证伪形态的 ⚠ 警告**：①`hint_dropped` 缺失或非整数（⇒ 丢弃数只能记【无法判定】，"
     "缺失 ≠ 0）；②某天 `hint_dropped > 当天 lessons.added 条数`（口径打架：丢掉的不可能多于拍出来的）；"
     "③库文件里有条目 `hint` 为空（= 丢弃已生效）却全账本没有 `hint_dropped` 计数（疑字段被摘/没记账）。"
     "旧账本没有 `lessons` 事件或没有该字段 ⇒ 头部 `<缺失>` +【无法判定】（缺失 ≠ 0，"
     "绝不当'没有矛盾 hint'通过）"),
    ("harvest_gave_up（task-170，task-172 收录）",
     "**收获如实放弃**（逐格：tile/attempts/limit/codes）：试满后当天不再回头 —— brain 把它"
     "从目标池与守卫里扣掉（`ripe_live = ripe − len(harvest_gave_up)`），但 "
     "`_leftover(\"harvest\")` **不扣** ⇒ 它是**「该做没做」的证据，绝不是豁免分子**"
     "（`tools\\verify-run3.py` 对 `harvest_gave_up` 零命中 ⇒ 本工具不判红、不进 rc）；"
     "头部'收获放弃'行 + 建议 0s-2；缺失 ⇒【无法判定】（缺失 ≠ 0）"),
    ("tiles[].ready / fullyGrown / harvestMethod / currentPhase / phaseDays / dayOfCurrentPhase / "
     "forageCrop / whichForageCrop / regrowsAfterHarvest / farm.readyCrops / exec.acted（task-170）",
     "**「看着熟」与「真能收」分家**（task-169 病根）：`ripe`=`Crop.fullyGrown`（旧口径，看着熟）；"
     "`ready`=Mod 反射游戏 `HoeDirt.readyForHarvest()`（真能收；`null`=读不到 ⇒ 只记【无法判定】，"
     "**绝不当 false**）；两口径差值 = 看着熟其实不能收（regrow 期 `fullyGrown && dayOfCurrentPhase>0` / "
     "`dead` / `forageCrop==\"2\"`）。头部'熟/可收对账'行 + 建议 0s-2；日级 `day_end.final.farm` "
     "白名单不含这两项（`brain longrun.py:1690-1692`）⇒ 账本层通常缺证据，要判定用 "
     "`observe?detail=full` 采样。`exec.acted` = task-170 起回执带「游戏自己有没有执行动作」"),
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
     "max(5, 20%×bound_basis（= attempted − encircled；被围住的格不参与起界，task-78）)，`checks.unreachable_within_bound=false` ⇒ 0 必须人工介入"
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
    # task-88 ④：`seed_gate` 的"钱不够"分叉 —— 未发起购买，**不是任务失败**
    if se.get("afford_blocked"):
        add(f"种子经济: 本日缺种子钱（money={se.get('seed_gate_money')} < "
            f"seed_price={se.get('seed_gate_price')}）⇒ 未发起购买，不是任务失败"
            f"（seed_gate {se.get('seed_gate')} 次、其中钱不够/背包 0 种子 "
            f"{se.get('afford_blocked')} 次；行 {se.get('afford_blocked_lines', [])[:10]}）")
    # task-91 ③：一行看懂"种子经济闭环"（出货 → 结算 → 买种子）
    sl = report.get("sell") or {}
    if sl.get("total") or sl.get("surplus_events") or sl.get("skips"):
        add(f"种子经济/出货: sell {sl.get('total', 0)} 次（成交 {sl.get('ok', 0)} / 失败 "
            f"{sl.get('failed', 0)}；below_keep {sl.get('below_keep', 0)} 叠）；盈余汇总 "
            f"surplus_sell {sl.get('surplus_events', 0)} 次（sold {sl.get('surplus_sold', 0)} 件、"
            f"below_keep {sl.get('surplus_below_keep', 0)} 叠）；想卖但没材料 "
            f"surplus_sell_skip {sl.get('skips', 0)} 次（short 最大 {sl.get('skip_short_max', 0)}g）；"
            f"buy {buy.get('total', 0)} 次（成交 {buy.get('ok', 0)} / 未成交 {buy.get('failed', 0)}）；"
            f"seed_gate {se.get('seed_gate', 0)} 次"
            + ("  ⚠ 卖了但次日 buy 仍 0 ⇒ 候选只有两个：钱没到账（次日 NewDay 才结算）/ "
               "货架没有当季种子（别下结论；行 "
               f"{[x['line'] for x in sl['sold_days_with_no_buy_next']][:10]}）"
               if sl.get("sold_days_with_no_buy_next") else ""))
    # task-32：两种新事件形态的计数（信息项）；task-38：跨日证据覆盖度
    # task-102（`9b09735`）：**背包空格闭环**一行 —— free_slots / buy 尝试 / buy_no_space /
    # 腾格卖出（`why=need_slot`）/ 当日钱变化 / `slept_without_work` / `modal_dismiss_failed`。
    # 口径：**买不到不是失败**（没空格/钱不够/没货架都不判红；缺字段写【无法判定】）；
    # `slept_without_work` 是"0 农场动作拒绝睡觉、当天不推进"（守卫生效，不是睡眠失败）。
    bs = report.get("bag_space") or {}
    fs_txt = ("<缺失>" if bs.get("free_slots") is None
              else f"{bs.get('free_slots')}（{bs.get('free_slots_status') or '状态未知'}）")
    money_txt = ("<缺失>" if bs.get("money_start") is None or bs.get("money_end") is None
                 else f"{bs.get('money_start')} → {bs.get('money_end')}")
    add(f"种子经济/背包: free_slots {fs_txt}；buy 尝试 {bs.get('buy_attempts', 0)} 次；"
        f"buy_no_space {bs.get('buy_no_space', 0)} 次（背包没空格 ⇒ 当天不再重试）；"
        + (f"回执 no_inventory_space×{bs['buy_no_space_receipts']}（旧账本形态：brain 还没发 "
           "buy_no_space 事件，从回执码补认）；"
           if bs.get("buy_no_space_receipts") and not bs.get("buy_no_space") else "")
        + f"腾格卖出 {bs.get('slot_sells', 0)} 次（why=need_slot"
        + (f"；why 分布 {bs.get('why_counts')}" if bs.get("why_counts") else "") + "）；"
        f"当日钱 {money_txt}；slept_without_work {bs.get('slept_without_work', 0)} 次"
        "（0 农场动作拒绝睡觉 ⇒ 当天不推进，是守卫生效的证据、**不是睡眠失败**）"
        "；口径：**买不到不是失败**（no_space / 钱不够 / 没货架一律不判红；缺字段写【无法判定】）"
        + (f"  ⚠ modal_dismiss_failed {bs.get('modal_dismiss_failures')} 次"
           f"（行 {bs.get('modal_dismiss_failed_lines', [])[:6]}）"
           "——关模态时桥报错，只点名（verify-run3 未判它，判红会两边反向）"
           if bs.get("modal_dismiss_failures") else ""))
    # task-132（task-123 在制）：量力而行买种子 —— 买一半**不是失败**（`buy_ok` 只算买满 `wanted`
    # 的整笔成交）；旧账本没有该事件/字段 ⇒ `<缺失>` + 【无法判定】（缺失 ≠ 0）。
    # 只给两条**可证伪**形态的 ⚠ 警告（不判红：verify-run3.py 对 `buy_partial` 零命中）。
    bp = report.get("buy_partial") or {}
    if not bp.get("has_events") and not bp.get("buy_has_wanted"):
        add("部分购买: <缺失>（本账本没有 buy_partial 事件、buy 也没有 wanted 字段 ⇒ 无法判定是否"
            "出现过「钱只够买一半」；缺失 ≠ 0）")
    else:
        _bp_plans = "、".join(f"{k} {v[0]}/{v[1]}" for k, v in (bp.get("plans") or {}).items())
        add(f"部分购买: {bp.get('events', 0)} 次（买到 {bp.get('bought_total', 0)} 个 / 想要 "
            f"{bp.get('wanted_total', 0)} 个；还缺 {bp.get('short_total', 0)} 个"
            + (f"；{_bp_plans}" if _bp_plans else "")
            + (f"；单价 {bp.get('prices')[:4]}" if bp.get("prices") else "")
            + f"）；买满成交 {bp.get('buy_ok_full', 0)} 次"
            + (f"（另有 {bp['buy_ok_missing_wanted']} 次成交没有 wanted 字段、无法区分是否买满）"
               if bp.get("buy_ok_missing_wanted") else "")
            + f"；cannot_afford {bp.get('cannot_afford_events', 0)} 次"
            "；口径：**买一半不是失败**（不进 failed、不判红；verify-run3.py 对该事件零命中）"
            + (f"  ⚠ buy 自称成交却买少（count<wanted）且当天没有对应 buy_partial：行 "
               f"{bp.get('warn_missing_partial_lines', [])[:6]}（{bp.get('warn_missing_partial_days')}）"
               "——量力而行必须留痕（只警告、不判红）"
               if bp.get("warn_missing_partial_lines") else "")
            + (f"  ⚠ 同日既有 buy_partial 又有 cannot_afford："
               f"{bp.get('warn_cannot_afford_same_day_days')}"
               f"（行 {bp.get('warn_cannot_afford_same_day_lines', [])[:6]}）"
               "——可能是不同货品单价差、也可能判据打架，只提示人工核对（不判红）"
               if bp.get("warn_cannot_afford_same_day_lines") else ""))
    # task-133：窗口外浇水 + 壶空先补水 —— 两个事件都**不是失败**（verify-run3.py 对
    # `water_far_refill` 零命中）；只有两条可证伪形态给 ⚠ 警告，旧账本一律 `<缺失>`（缺失 ≠ 0）。
    wf = report.get("water_far") or {}
    if not wf.get("has_events"):
        add("窗口外浇水/补水: <缺失>（本账本没有 water_far / water_far_refill 事件 ⇒ 无法判定"
            "是否出现过；缺失 ≠ 0）")
    else:
        _wf_b = "、".join(str(x) for x in (wf.get("water_before") or [])[:4]) or "<缺失>"
        _wf_a = "、".join(str(x) for x in (wf.get("water_after") or [])[:4]) or "<缺失>"
        _wf_c = "、".join(f"{k}×{v}" for k, v in list((wf.get("far_causes") or {}).items())[:4])
        add(f"窗口外浇水/补水: water_far {wf.get('far_events', 0)} 次（浇成 {wf.get('far_ok', 0)} / "
            f"没成 {wf.get('far_failed', 0)}；因由 {_wf_c or '<缺失>'}；补水后回浇 "
            f"{wf.get('far_retried_after_refill', 0)} 次）；补水 water_far_refill "
            f"{wf.get('refill_events', 0)} 次（成功 {wf.get('refill_ok', 0)} / 没成 "
            f"{wf.get('refill_failed', 0)}；水位 {_wf_b} → {_wf_a}；回执 "
            f"{wf.get('refill_codes') or '<缺失>'}）"
            "；口径：**壶空是前置条件、不是「够不着」**（先补水再回浇同一格；补水与窗口外浇水"
            "都不判红）"
            + (f"  ⚠ 补水没成却把那格浇成了：行 "
               f"{wf.get('warn_refill_failed_but_watered_lines', [])[:6]}"
               "（回执/水位读数有一边可信度存疑，只警告、不判红）"
               if wf.get("warn_refill_failed_but_watered_lines") else "")
            + (f"  ⚠ 当天补水预算用尽（tries ≥ limit，行 {wf.get('budget_exhausted_lines', [])[:6]}）"
               "⇒ 剩下的干格今天注定浇不上（提示换补水点或提高上限，不判红）"
               if wf.get("budget_exhausted_lines") else "")
            + (f"  ⚠ {wf.get('far_cause_missing')} 条 water_far 没有 cause 字段（旧账本形态）"
               if wf.get("far_cause_missing") else ""))
    # task-172：收获如实放弃（**不是豁免分子**）+ ripeCrops/readyCrops 对账（task-169 病根）。
    hg = report.get("harvest_gave_up") or {}
    cr = report.get("crop_ready") or {}
    if not hg.get("has_events"):
        add("收获放弃: <缺失>（本账本没有 harvest_gave_up 事件 ⇒ 无法判定是否放弃过收获；缺失 ≠ 0）")
    else:
        add(f"收获放弃（如实，**不是豁免**）: {hg.get('events', 0)} 次 / "
            f"{hg.get('tile_count', 0)} 格（试满 attempts 合计 {hg.get('attempts', 0)}；"
            f"limit {hg.get('limits') or '<缺失>'}；codes {hg.get('codes') or '<缺失>'}）"
            "；口径：目标池与守卫都会把它扣掉，但 `_leftover(\"harvest\")` 不扣 ⇒ 它就是"
            "「该做没做」的证据，**绝不当已做完**"
            + (f"  ⚠ 当天如实放弃了收获却自称 VERIFIED：行 "
               f"{hg.get('warn_gave_up_but_verified_lines', [])[:6]}（只警告，不判红）"
               if hg.get("warn_gave_up_but_verified_lines") else ""))
    if not cr.get("has_fields"):
        add("熟/可收对账: <缺失>（账本里没有 `ripeCrops`/`readyCrops` ⇒ 无法判定「看着熟其实不能收」"
            "这一支；缺失 ≠ 0）")
    else:
        add(f"熟/可收对账: ripeCrops {cr.get('ripe_total')} − readyCrops {cr.get('ready_total')} "
            f"= {cr.get('diff_total')}（{cr.get('days_with_fields')} 天有字段；窗口 "
            f"ready=true {cr.get('window_ready_true')} / ready=null {cr.get('window_ready_null')} / "
            f"ripe=true {cr.get('window_ripe_true')}）"
            "；口径：`ripe`=`Crop.fullyGrown`（看着熟）、`ready`=`HoeDirt.readyForHarvest()`（真能收）"
            + (f"  ⚠ 看着熟其实不能收（差值 >0）：行 {cr.get('ripe_without_ready_lines', [])[:6]}"
               "——task-169 病根（regrow 期/dead/forage==\"2\"），改 Mod 判据后再看"
               if cr.get("diff_total", 0) > 0 else "")
            + (f"  ⚠ 窗口里 ripe=true 但 ready=false：行 "
               f"{cr.get('window_ripe_not_ready_lines', [])[:6]}"
               if cr.get("window_ripe_not_ready_lines") else ""))
    # task-179：`ready` 的**来源**（game/fields/null/缺键）—— `fields` 是等价路径，不是 fail-open。
    if not cr.get("has_ready_source") and not cr.get("ready_source_missing_tiles"):
        add("可收来源: <缺失>（本账本没有 `tiles[].readySource` ⇒【无法判定·旧 Mod】：分不清 `ready` "
            "是游戏 `HoeDirt.readyForHarvest()` 判的、还是我们字段兜底猜的；缺失 ≠ 0，更绝不因此判通过）")
    else:
        add(f"可收来源: readySource game {cr.get('ready_source_game')} / fields "
            f"{cr.get('ready_source_fields')} / null {cr.get('ready_source_null')} / 缺键 "
            f"{cr.get('ready_source_missing_tiles')}；口径：`fields` = 反射不可用但字段判据与 "
            "`HoeDirt.readyForHarvest()` 的 IL **逐条等价**（**不是 fail-open**），"
            "只有 `null` 判不了 ⇒【无法判定】"
            + (f"  ⚠ {cr.get('ready_source_missing_tiles')} 格有 `ready` 却没有 `readySource`"
               f"（旧 Mod 形态）：行 {cr.get('ready_source_missing_lines', [])[:6]} ⇒【无法判定·旧 Mod】"
               if cr.get("ready_source_missing_tiles") else "")
            + (f"  ⚠ readySource=null 占 {cr.get('ready_source_null')}/{cr.get('ready_source_seen')}"
               "（fail-closed 过头风险：反射与字段都读不到 ⇒ 这些格既不当能收、也不当不能收，"
               "只记【无法判定】）"
               if cr.get("warn_null_heavy") else "")
            + (f"  ⚠ harvestMethod 键缺失的行 {cr.get('harvest_method_missing_lines', [])[:6]}"
               "（task-176：该键必须**无条件存在**）"
               if cr.get("harvest_method_missing_lines") else ""))
    # task-157：够不着 ⇒ 有界开路（`water_far_open`）后重试同一格；开路后仍站不到 ⇒ `water_far_blocked`。
    # 两者都**不是失败**：开路成功也**不等于**浇上水；当天达不达标由 `checks.watered_outdoor` 说话。
    if wf.get("has_open_events"):
        _wf_oc = "、".join(f"{k}×{v}" for k, v in list((wf.get("open_codes") or {}).items())[:4]) or "<缺失>"
        _wf_bc = "、".join(f"{k}×{v}" for k, v in list((wf.get("blocked_causes") or {}).items())[:4]) or "<缺失>"
        add(f"开路/够不着: 开路 {wf.get('open_events', 0)} 次（code {_wf_oc}；共清了 "
            f"{wf.get('open_cleared_total', 0)} 格挡路格；tiles {(wf.get('open_tiles') or [])[:6]}）；"
            f"开路后仍站不到 {wf.get('blocked_events', 0)} 格（因由 {_wf_bc}；tries "
            f"{(wf.get('blocked_tries') or [])[:6]}）"
            "；口径：**开路成功 ≠ 浇上水**、blocked 是如实承认没浇上（都不判红；达不达标由 "
            "checks.watered_outdoor 说话）"
            + (f"  ⚠ 开路成功但那格当天最后仍在 dryTiles 里：行 "
               f"{wf.get('warn_open_but_still_dry_lines', [])[:6]}"
               if wf.get("warn_open_but_still_dry_lines") else "")
            + (f"  ⚠ 有格 blocked（确实没浇上）而当天却自称户外浇水达标"
               f"（watered_outdoor=true 且 final_water.dry=0）：行 "
               f"{wf.get('warn_blocked_but_watered_lines', [])[:6]}"
               if wf.get("warn_blocked_but_watered_lines") else ""))
    else:
        add("开路/够不着: <缺失>（本账本没有 water_far_open / water_far_blocked 事件 ⇒ 无法判定"
            "是否出现过；缺失 ≠ 0）")
    # task-158：体力预算 —— 解释「为什么今天不浇」（不是失败；当天达不达标由 checks 说话）。
    sb = report.get("stamina_budget") or {}
    if not sb.get("has_events"):
        add("体力预算: <缺失>（本账本没有 stamina_budget / deferred_by_budget 事件、"
            "day_end 也没有 stamina_budget 字段 ⇒ 无法判定今天是否被预算限制；缺失 ≠ 0）")
    else:
        _sb_basis = "、".join(f"{k}×{v}" for k, v in list((sb.get("basis") or {}).items())[:3]) or "<缺失>"
        _sb_tasks = "、".join(f"{k}×{v}" for k, v in list((sb.get("defer_tasks") or {}).items())[:4])
        add(f"体力预算: reserve {sb.get('water_reserve')} / capacity {sb.get('capacity')}"
            f"（max {sb.get('max')}、stamina {sb.get('stamina')}、水耗估计 {sb.get('water_cost_est')}、"
            f"赶路预留 {sb.get('path_allowance')}；依据 {_sb_basis}）；by_budget 延后 "
            f"{sb.get('defer_events', 0)} 条（共 {sb.get('deferred_total', 0)} 格"
            + (f"；任务 {_sb_tasks}" if _sb_tasks else "") + "）"
            + (f"；日级字段覆盖 {len(sb.get('day_field_days') or [])} 天"
               if sb.get("has_day_field") else "；日级字段 <缺失>")
            + "；口径：**只因预算而不做不是失败**（没浇完就是 crops_watered=false）"
            + (f"  ⚠ 说「只因预算延后」但当天却自称户外浇水达标（dry=0）：行 "
               f"{sb.get('warn_deferred_but_watered_lines', [])[:6]}"
               if sb.get("warn_deferred_but_watered_lines") else "")
            + (f"  ⚠ 日级 deferred_by_budget>0 却没有对应的 deferred_by_budget 事件：行 "
               f"{sb.get('warn_defer_missing_lines', [])[:6]}"
               if sb.get("warn_defer_missing_lines") else "")
            + (f"；预算延后 budget_deferred_tiles {sb.get('budget_defer_events', 0)} 条"
               f"（{sb.get('budget_defer_tiles', 0)} 格；任务 "
               f"{'、'.join(f'{k}×{v}' for k, v in list((sb.get('budget_defer_tasks') or {}).items())[:4]) or '<缺失>'}）"
               if sb.get("budget_defer_events") else "；预算延后事件 <缺失>")
            + (f"；容量上限 stage_capped_by_capacity {sb.get('capacity_events', 0)} 次"
               f"（任务 {'、'.join(list((sb.get('capacity_tasks') or {}).keys())[:4]) or '<缺失>'}"
               f"；日级 capacity_capped_tasks {sb.get('capacity_capped_tasks', 0)}）"
               if (sb.get("capacity_events") or sb.get("capacity_capped_tasks")) else "")
            + (f"  ⚠ 当天有预算延后却自称「该做的都做了」（no_work + VERIFIED）⇒ 人工核对"
               f"「延后是否只发生在有浇水债时」：行 "
               f"{sb.get('warn_defer_tiles_but_no_work_lines', [])[:6]}"
               if sb.get("warn_defer_tiles_but_no_work_lines") else "")
            + (f"  ⚠ 当天有预算延后但 stamina_budget 显示没有浇水债（live_crops/dry ≤ 0）：行 "
               f"{sb.get('warn_defer_without_debt_lines', [])[:6]}"
               if sb.get("warn_defer_without_debt_lines") else ""))
    # task-20 / task-164：工具门槛（clump 工具等级/种类不够 ⇒ 动手前拦下、0 次 use_tool）。
    # **诚实跳过、不判红、不进 rc**（verify-run3.py 对这两名零命中）；旧账本 ⇒ `<缺失>` +【无法判定】。
    tg = report.get("tool_gate") or {}
    if not tg.get("has_events"):
        add("工具门槛: <缺失>（本账本没有 blocked_by_tool / blocked_by_tool_summary 事件 ⇒ 无法判定"
            "当天有没有格是因工具不够格被封的；缺失 ≠ 0）")
    else:
        _tg_need = "、".join(f"{k}×{v}" for k, v in list((tg.get("needs") or {}).items())[:4]) or "<缺失>"
        _tg_kind = "、".join(f"{k}×{v}" for k, v in list((tg.get("kinds") or {}).items())[:4]) or "<缺失>"
        add(f"工具门槛: 当天因工具等级/种类不够封格 {tg.get('events', 0)} 格"
            f"（需要 {_tg_need}；kind {_tg_kind}；tiles {(tg.get('tiles') or [])[:6]}）；"
            f"日级汇总 blocked_by_tool_summary {tg.get('summary_events', 0)} 次"
            f"（count {(tg.get('summary_counts') or [])[:4]}、tools "
            f"{'、'.join(sorted((tg.get('summary_tools') or {}).keys())) or '<缺失>'}）"
            "；口径：**诚实跳过**（0 次 use_tool、不算活、不进守卫理由 ⇒ 不判红、不进 rc；"
            "次日工具升级后自动重试）"
            + (f"  ⚠ 当天自称 no_work（没活）却存在工具门槛封格：行 "
               f"{tg.get('warn_no_work_with_gate_lines', [])[:6]}"
               "—— 提示人工核对「真敲不动 vs 工具够却判不出」（brain 有意不让它进守卫理由，只警告）"
               if tg.get("warn_no_work_with_gate_lines") else ""))
    pc, ws = report["events"].get("plots_capped", 0), report["events"].get("work_spot", 0)
    add(f"软上限/收尾: plots_capped {pc} 次（作业区配额到顶，信息项）；work_spot {ws} 次（收尾作业区）")
    # task-124/task-130：review 兜底 / 弃权 / 换片连发 —— 修复生效的证据（不判红），
    # 只给可证伪形态的 ⚠ 警告；旧账本没有这些事件 ⇒ `<缺失>`（缺失 ≠ 0 = 没发生过）。
    rf = report.get("review_fallback") or {}
    if not rf.get("has_events"):
        add("review 兜底/换片连发: <缺失>（本账本没有 review_only_* / plot_exhausted_burst / "
            "resume_reevaluate / no_progress_burst 事件 ⇒ 无法判定是否出现过；缺失 ≠ 0）")
    else:
        _itxt = "、".join(f"{k}×{v}" for k, v in list((rf.get("fallback_intents") or {}).items())[:4])
        add(f"review 兜底/换片连发: 兜底 {rf.get('fallback_events', 0)} 次"
            f"（work_spot {rf.get('fallback_work_spot', 0)} / pending_walk {rf.get('fallback_pending_walk', 0)}"
            f"；带路成功 {rf.get('fallback_walked', 0)} 次、覆盖 {rf.get('fallback_tiles', 0)} 格"
            + (f"；意图 {_itxt}" if _itxt else "") + "）；"
            f"弃权 {rf.get('no_target_events', 0)} 次（{rf.get('no_target_pending', 0)} 格当日放弃、次日重试）；"
            f"换片连发 {rf.get('burst_events', 0)} 次（最多一次 count={rf.get('burst_max', 0)}"
            + (f"、zone={rf.get('burst_zones')}" if rf.get("burst_zones") else "") + "）"
            + (f"  ⚠ burst 当天却自称 VERIFIED：{rf.get('warn_burst_verified_days')}"
               f"（行 {rf.get('warn_burst_verified_lines', [])[:4]}）"
               "——连发=没目标的证据，与 VERIFIED 互斥（只警告、不判红）"
               if rf.get("warn_burst_verified_lines") else "")
            + (f"  ⚠ 弃权后守卫仍抱怨同批 leftover：{rf.get('warn_no_target_still_guarded_days')}"
               f"（行 {rf.get('warn_no_target_still_guarded_lines', [])[:4]}）——弃权没生效（只警告）"
               if rf.get("warn_no_target_still_guarded_lines") else "")
            + (f"  ⚠ 兜底抛异常 {rf.get('failed_events')} 次（{rf.get('failed_errors', [])[:2]}）"
               if rf.get("failed_events") else "")
            + "；口径：这些事件**不是失败**（是 task-124 修复生效的证据）"
              "，verify-run3.py 对它们零命中 ⇒ 本工具只警告不判红")
    # task-134 B：分配额口径（阶段 assigned_undone vs 片区 leftover vs 诚实上限 deferred）——
    # 三者都不是失败（红由 `checks.no_unmet_stages=false` 说话；deferred 明确不进该检查）。
    shf = report.get("shortfall") or {}
    if not shf.get("has_events") and not shf.get("has_day_fields"):
        add("阶段分配额/诚实上限: <缺失>（本账本没有 stage_shortfall / stage_shortfall_day / "
            "deferred_tiles 事件，day_end 也没有 assigned_undone/deferred_tiles 字段 ⇒ "
            "无法判定「分下去的格做完了没」与「诚实上限留下多少」；缺失 ≠ 0）")
    else:
        add(f"阶段分配额/诚实上限: 阶段没做完 {shf.get('stage_events', 0)} 次"
            f"（分下去 {shf.get('assigned_total', 0)} 格 / 没做完 {shf.get('undone_total', 0)} 格；"
            f"stopped {'、'.join(f'{k}×{v}' for k, v in list((shf.get('stopped_kinds') or {}).items())[:4]) or '<缺失>'}）；"
            f"日级 shortfall {shf.get('day_events', 0)} 次（unmet 最多 {shf.get('unmet_max', 0)}、"
            f"片区 pending 最多 {shf.get('plot_pending_max', 0)}）；"
            f"诚实上限留下 {shf.get('deferred_events', 0)} 次 / {shf.get('deferred_tiles', 0)} 格"
            "（只作 info、**不进** no_unmet_stages）"
            + (f"  ⚠ 日级说 stopped_night=false 但当天 ended_reason 是 night（行 "
               f"{shf.get('warn_stopped_night_mismatch_lines', [])[:4]}）——两个口径打架，只警告、不判红"
               if shf.get("warn_stopped_night_mismatch_lines") else ""))
    # task-144（dev-coder 在制）：壶空先补水再"原样重跑"（`refill_retry`）+ 阶段自然走完却仍有
    # 分配未成事的格 ⇒ 如实 stop 命名（`stage_stop_named`）—— 都是**修复生效的证据**、不判红。
    rrv = report.get("refill_retry") or {}
    snv = report.get("stage_stop_named") or {}
    if not rrv.get("has_events") and not snv.get("has_events"):
        add("阶段自愈/如实收工: <缺失>（本账本没有 refill_retry / stage_stop_named 事件 ⇒ "
            "无法判定「壶空后有没有把这一轮没成事的格原样重跑」与「阶段自然结束却还有分配未成事的格"
            "有没有如实命名 stop 原因」；缺失 ≠ 0）")
    else:
        # task-144 增量（`2438cae`）：该阶段已补水几次 / 阶段上界（`STAGE_REFILL_MAX`）。
        _srb = rrv.get("stage_refill_by_stage") or {}
        _srb_txt = "、".join(
            f"{_k} {(_v.get('stage_refills') if _v.get('stage_refills') is not None else '<缺失>')}"
            f"/{(_v.get('stage_limit') if _v.get('stage_limit') is not None else '<缺失>')} 次"
            for _k, _v in list(_srb.items())[:3])
        add(f"阶段自愈/如实收工: 壶空重跑 {rrv.get('events', 0)} 次"
            f"（补水成功 {rrv.get('ok', 0)} / 没成 {rrv.get('failed', 0)}；重跑 "
            f"{rrv.get('tiles_total', 0)} 格；当天 refill {rrv.get('refill_events_total', 0)} 次"
            + (f"；阶段补水 {_srb_txt}" if _srb_txt else "") + "）；"
            + f"如实 stop 命名 {snv.get('events', 0)} 次"
            f"（cause {'、'.join(f'{k}×{v}' for k, v in list((snv.get('causes') or {}).items())[:4]) or '<缺失>'}；"
            f"分下去 {snv.get('assigned_total', 0)} 格 / 没做完 {snv.get('undone_total', 0)} 格）"
            + ("  ⚠ 重跑条数多于当天 refill（行 "
               f"{(rrv.get('warn_over_retry_lines') or [])[:4]}）——两个口径打架，只警告、不判红"
               if rrv.get("warn_over_retry_lines") else "")
            + ("  ⚠ 补水成功却 0 格可重跑（行 "
               f"{(rrv.get('warn_empty_lines') or [])[:4]}）——空转嫌疑，只警告、不判红"
               if rrv.get("warn_empty_lines") else "")
            + ("  ⚠ 阶段补水次数超过该阶段上界（行 "
               f"{(rrv.get('warn_over_stage_refill_lines') or [])[:4]}）"
               "——`stage_refills > stage_limit`，口径打架，只警告、不判红"
               if rrv.get("warn_over_stage_refill_lines") else "")
            + ("  ⚠ stage_stop_named 自相矛盾（cause 缺失/未知 行 "
               f"{(snv.get('warn_bad_cause_lines') or [])[:4]}；assigned_undone≤0 行 "
               f"{(snv.get('warn_no_undone_lines') or [])[:4]}；有过失却 codes 空 行 "
               f"{(snv.get('warn_no_codes_lines') or [])[:4]}）——只警告、不判红"
               if (snv.get("warn_bad_cause_lines") or snv.get("warn_no_undone_lines")
                   or snv.get("warn_no_codes_lines")) else ""))
    # task-111：LLM 收工复盘 / 跨日教训库（task-58/59/82）—— "模型没学到东西"不是失败，只呈现
    lri = report.get("llm_review") or {}
    if not lri.get("has_events"):
        add("LLM 复盘/教训库: <缺失>（本账本没有 review_llm/lessons 事件 ⇒ 无法判定；缺失 ≠ 0，"
            "绝不当'模型没学到东西'通过）")
    else:
        _fstat = {"ok": f"落盘 {lri.get('file_count')} 条",
                  "missing": "落盘文件不存在（还没写过）",
                  "corrupt": f"落盘文件损坏（{lri.get('file_error')}）",
                  "unknown": "落盘未知"}.get(str(lri.get("file_status")), str(lri.get("file_status")))
        add(f"LLM 复盘/教训库: 复盘 {lri.get('review_events', 0)} 次、notes "
            f"{lri.get('notes_count', 0)} 条（{lri.get('notes_chars', 0)} 字；被拒 "
            f"{lri.get('rejected_count', 0)} 条、截断 {lri.get('truncated', 0)} 次）；复盘失败 "
            f"{lri.get('failed_events', 0)} 次"
            + (f"（{lri.get('failed_reasons', [])[:2]}）" if lri.get("failed_events") else "")
            + f"；教训库 total {lri.get('lessons_total') if lri.get('lessons_total') is not None else '<缺失>'}"
            f" 条（上限 {lri.get('lessons_max')}；本日新增 {lri.get('lessons_added') if lri.get('lessons_added') is not None else '<缺失>'}"
            f" / 淘汰 {lri.get('lessons_dropped') if lri.get('lessons_dropped') is not None else '<缺失>'}）"
            f"；读写失败 load {lri.get('load_failed', 0)} / save {lri.get('save_failed', 0)}"
            f"；{_fstat}"
            + (f"；拒收 {lri.get('rejected_events', 0)} 次 / {lri.get('rejected_dropped', 0)} 条"
               f"（原因 {'、'.join([str(x) for x in (lri.get('rejected_reasons') or ['—'])][:3])}）"
               if lri.get("rejected_events") else "")
            + (f"；教训库写入 {lri.get('lessons_written') if lri.get('lessons_written') is not None else '<缺失>'}"
               f" 条 / 跳过 {lri.get('lessons_skipped_untrusted') if lri.get('lessons_skipped_untrusted') is not None else '<缺失>'}"
               f" 条（不可信）/ 拒收 {lri.get('rejected_events', 0)} 条"
               f"（其中不可信 {lri.get('rejected_untrusted', 0)} 条）")
            + ("  ⚠ 复盘声称成功却 0 条 notes"
               if lri.get("without_notes_lines") else "")
            + ("  ⚠ 教训库超上限" if lri.get("over_limit_lines") else "")
            + (f"  ⚠ warn:lessons_all_rejected（连续 {lri.get('warn_all_rejected_run')} 天 "
               f"dropped>0 且 kept==0："
               f"{'、'.join([str(x) for x in (lri.get('warn_all_rejected_days') or [])][:3])}"
               "；只作警告、不判红 —— 拒收本身是正确行为，这里只是提示'库连续整版不可用'）"
               if (lri.get("warn_all_rejected_run") or 0) >= 2 else "")
            + (f"  ⚠ warn:lessons_all_untrusted（连续 {lri.get('warn_all_untrusted_run')} 天 "
               f"skipped_untrusted>0 且 written==0："
               f"{'、'.join([str(x) for x in (lri.get('warn_all_untrusted_days') or [])][:3])}"
               "；只作警告、不判红 —— 库被外部整版污染，但不可信条目一条也没被写回）"
               if (lri.get("warn_all_untrusted_run") or 0) >= 2 else "")
            + "；口径：**没学到东西不是失败**（空 notes/空库只记信息）")
    # task-136 C（task-139）：教训素材质量 —— 入库 / hint 丢弃 / 拒收 / 库大小（缺失 ⇒ <缺失>+【无法判定】）
    if not lri.get("lessons_events"):
        add("教训素材质量: <缺失>（本账本没有 `lessons` 事件 ⇒ 无法判定入库与 hint 丢弃；"
            "缺失 ≠ 0，绝不当'没有矛盾 hint'通过）")
    else:
        _hd_bad = lri.get("hint_dropped_bad_lines") or []
        _hd_tot = ("<缺失>" if _hd_bad else lri.get("hint_dropped_total"))
        add(f"教训素材质量: 入库 {lri.get('lessons_added') if lri.get('lessons_added') is not None else '<缺失>'} 条"
            f" / hint 丢弃 {_hd_tot} 条"
            f" / 拒收 {lri.get('rejected_events', 0)} 次（原因 "
            f"{'、'.join([str(x) for x in (lri.get('rejected_reasons') or ['—'])][:3])}）"
            f" / 库大小 {lri.get('file_count') if lri.get('file_count') is not None else '<缺失>'}"
            + (f"  ⚠ `lessons.hint_dropped` 缺失或非整数（行 {_hd_bad[:4]}）⇒ 丢弃数只能记【无法判定】"
               if _hd_bad else "")
            + ("  ⚠ hint 丢弃数 > 当天新增条数（口径打架，只警告不判红）"
               if lri.get("hint_dropped_gt_added_lines") else "")
            + ("  ⚠ 库里有条目 hint 为空（丢弃已生效）却全账本没有 hint_dropped 计数 ⇒ 疑字段被摘"
               if lri.get("warn_empty_hint_no_count") else "")
            + "；口径：hint 被丢是**设计行为**（防污染生效的正面证据），不判红")
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
    # task-84：死苗/放弃格 —— 死苗不浇水（dry 只算活苗，旧口径让 run7 追着一株够不着的死苗烧两个整天）
    dci = report.get("dead_crops") or {}
    if not dci.get("has_fields"):
        add("死苗/放弃格: <缺失>（本账本没有 dead_crops/dry_dead/gave_up_tiles ⇒ 死苗口径无法判定；"
            "缺失 ≠ 0，绝不当'没有死苗'通过）")
    else:
        _dc_missing = set(dci.get("missing_fields") or [])

        def _dc_or_missing(key):
            return dci.get(key) if key not in _dc_missing else "<缺失>"

        _gu_txt = ("<缺失>" if "gave_up_tiles" in _dc_missing
                   else f"{dci.get('gave_up_count')} 格（坐标 {str(dci.get('gave_up_tiles'))[:80]}）")
        add(f"死苗/放弃格: 枯死 {_dc_or_missing('dead_crops')} 格"
            f"（状态 {_dc_or_missing('dead_crops_status')}）"
            f"、其中没浇 {_dc_or_missing('dry_dead')} 格"
            f"（状态 {_dc_or_missing('dry_dead_status')}）"
            f"；当天认输格 {_gu_txt}"
            "；口径：死苗不计浇水证据（dry 只算活苗，死苗走 clear_dead）"
            + (f"  ⚠ 死苗没清却判 no_work（行 {dci['no_work_uncleared'][:6]}）"
               if dci.get("no_work_uncleared") else "")
            + (f"  ⚠ 放弃格非空却自称 VERIFIED（warn:verified_with_gave_up；"
               f"行 {dci['verified_with_gave_up'][:6]}；"
               "**只作警告、不判红**：干格还在的话 verify-run3 的 dry>0 互斥闸门会先判红，"
               "认输格当天被解决时则为假红）"
               if dci.get("verified_with_gave_up") else "")
            + (f"  ⚠ dry_dead 不是整数（账目不可信，行 {dci['bad_fields'][:6]}）"
               if dci.get("bad_fields") else ""))
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
    # task-88：窗口口径（窗口外的日级红 → 历史问题，不进 rc）与"瞬间态已结清"
    win = report.get("window") or {}
    hist = report.get("history_problems") or {}
    settled = report.get("settled") or {}
    add(f"窗口: --window {win.get('days')}（尾部连续 VERIFIED {win.get('tail_streak')} 天"
        + ("，窗口生效" if win.get("active")
           else "，不足 ⇒ **不启用窗口降级**（窗口外也照常 fatal，历史问题不能替本跑开脱）")
        + f"）；窗口内红 {rc_total} 条；窗口外历史问题 {hist.get('total', 0)} 条"
        + (f"（行 {hist.get('lines')[:10]}）" if hist.get("total") else "")
        + f"；已结清（当天 VERIFIED）{settled.get('total', 0)} 条"
        + (f"（行 {settled.get('lines')[:10]}）" if settled.get("total") else ""))
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
            + (_bound_basis_text(env, "unreachable"))
            + ("  ⚠ checks.unreachable_within_bound=false ⇒ 0 类红"
               if env.get("unreachable_within_bound") is False else ""))
    # task-63/task-66：被游戏拒绝（不计当天硬失败、当天封格、次日重试；日级豁免有上界，越界进 0 类红）
    if env.get("refused_events") or env.get("refused_summary_events"):
        add(f"游戏拒绝: {env.get('refused_events', 0)} 次 / {env.get('refused_tile_count', 0)} 格"
            + (f"（tiles={env.get('refused_tiles')[:8]}）" if env.get("refused_tiles") else "")
            + f"；日级 count={env.get('refused_count')}、bound={env.get('refused_bound')}、"
              f"attempted={env.get('refused_attempted')}、exempt={env.get('refused_exempt')}"
            + _bound_basis_text(env, "refused")
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
        # task-88：窗口外的历史问题与"瞬间态已结清"逐条列出（都不进退出码）
        ("6 历史问题（窗口外，info 不进 rc）", "history", "历史问题（窗口外）"),
        ("7 已结清（瞬间态事件，info）", "settled", "已结清（瞬间态）"),
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
            "窗口（task-88）：`--window N`（默认 3，与 tools\\verify-run3.py 的尾部窗口同义）——\n"
            "                 窗口**外**的日级红降级为 history_problems（逐条列出、**不进退出码**）；\n"
            "                 窗口**内**照常 fatal；`连续 VERIFIED 天数 < N` 时不降级（维持原判）；\n"
            "                 事件级「瞬间态」（cancel / stage_no_target / stage_exhausted /\n"
            "                 plot_exhausted）当天 VERIFIED 且 no_unmet_stages=true ⇒ 记「已结清」（info）；\n"
            "                 无日期归属的全局红（finish 自述不一致 / 账目自相矛盾）永远 fatal。\n"
            "**判决权威仍是 tools\\verify-run3.py**：本工具是四路复核之一，退出码只表达\n"
            "\"有没有红\"，不表达\"整跑是否达标\"（达标看 verify-run3 的 0/1/2 与 docs\\_run6-criteria.md）。"
        ),
    )
    parser.add_argument("--journal", default=None,
                        help="账本路径（默认取 logs\\longrun-*.jsonl 里 mtime 最新）")
    parser.add_argument("--days", type=int, default=3, help="领跑天数（只用于 'X/N 天 VERIFIED' 的分母）")
    parser.add_argument("--window", type=int, default=3,
                        help="尾部窗口天数（默认 3，与 tools\\verify-run3.py 的尾部窗口同义）："
                             "窗口外的日级红 → history_problems（逐条列出、不进退出码）；"
                             "窗口内照常 fatal；尾部连续 VERIFIED 天数 < N 时不降级；"
                             "0 = 关闭窗口（task-88 之前的旧行为）")
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
