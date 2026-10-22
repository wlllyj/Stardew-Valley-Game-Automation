# A9-0749 三跑深挖：为什么拿不到 5 天连 VERIFIED（T-3 / log-analyst）

> 对象：`logs/runA9-0749.jsonl`（run1，HEAD `0221ca1`）、`logs/runA9-0749-fix.jsonl`（fix，HEAD `c383a0e`）、`logs/runA9-0749-spring.jsonl`（spring，HEAD `c383a0e`）、`logs/run-test-space.jsonl`（test-space，HEAD `c383a0e` + 工作树未提交的 task-240b 补丁）。
> 四跑装机 dll 同为 `C9B3BD6C…`（0.7.49 冻结产物），`farmwork.py`/`bridge.py`/manifest 四跑未变 ⇒ 行为差异全部来自 `brain/agentfarm/longrun.py` 的 `c383a0e`（encircled 空转硬上限）与工作树补丁。
> 所有结论带 journal 行号；缺失写【无法判定】。本文件只读代码与账本后的分析，不改任何判据。

---

## 0. 结论速览

三跑+test-space 全部拿不到 5 天连 VERIFIED，根因不是"没活干"，而是三重结构性死锁叠加：

1. **背包死锁**：12 格背包从 winter 26 起 0 空格、无可卖盈余叠（白名单只剩 Sap/Slime，工具/武器/种子/未知物永不卖）、手里 11 颗是夏季作物 Wheat Seeds ⇒ 零 seed buy、零种植、零作物、零收入 ⇒ money 六天恒 3042、free_slots 恒 0。
2. **走路预算空转**：每天 `resume_walk` 10/10 全部烧在"走回 leftover 锚点 → 观测 → 拿不出意图 → 再走"上；productive stage（till 每轮上限 12 格）一结束，确定性兜底只提 `clear_area`（必被满包清障闸 cancel），LLM 又无边界可唤回 ⇒ 白天 13:00–13:30 就收工，体力剩 130–230。
3. **判据 fail-closed**：`day_justified` 要求日终 `pending_executable==0`；只要账本还有"看得见+可执行"的格（多在别的片区或当前 25 格作业区窗口外），`resume_budget_exhausted` 收工日永远不 VERIFIED。

spring 3/5 两天 VERIFIED 不是机制保证，是"LLM 在 task_kind_change 边界被反复唤回、持续在同一片区锄到眼前无可执行格"的运气形态（§3.3）。

---

## 1. 四个跑的形态总览

| 跑 | HEAD / longrun.py | 行数 | 完成天 | 判决 |
|---|---|---|---|---|
| runA9-0749 | `0221ca1`（c383a0e 之前） | 575 = 544 首跑 + 31 重跑 | winter26 FAIL、winter27 VERIFIED；winter28 在 t=435.81 被中途杀（无 day_end）；L545-575 是同 journal 追加的 winter26 重跑（11 秒后又被杀） | 无 finish（从未闭环） |
| runA9-0749-fix | `c383a0e` | 496 | winter26 FAIL、winter27 VERIFIED、winter28 VERIFIED、spring1 FAIL（blocked_event） | finish code=1、verified_streak=0、unmet_days=["2年 spring 1日"]、actions=269 |
| runA9-0749-spring | `c383a0e` | 729 | spring1-6：F/F/V/F/V/F | finish code=1、verified_streak=0、actions=297、minutes=10.32 |
| run-test-space | `c383a0e` + 工作树 task-240b 在制补丁 | 197 | winter26 FAIL；winter27 无 day_end（被杀） | 无 finish |

---

## 2. ① 逐日 stage 统计：每天到底干成了什么

### 2.1 spring 跑逐日（`day_end.stages` 聚合 + analyzer 新增"走路预算燃烧"字段）

| 日 | till_area ok/skip/fail | till proven_inert/refused | clear_area | plant_area | water_area | frontier_clear | 走路 成功/尝试 | 换片 | farm_actions | 收工（verified） |
|---|---|---|---|---|---|---|---|---|---|---|
| spring 1 | 12 / 0 / 0（1 轮 12 格） | 0 / 0 | 1 轮 0  engaged（leftover 129） | 0 目标 | 0 目标 | 7（单格） | 10 / 10 | 2 | **19** | resume_budget_exhausted（F） |
| spring 2 | 56 / 1 / 0（5 轮） | 1 / 1 | 0 | 1 轮 leftover 12 | 0 | 6 | 10 / 10 | 0 | **62** | resume_budget_exhausted（F） |
| spring 3 | 60 / 0 / 0（6 轮） | 0 / 0 | 0 | 1 轮 leftover 5 | 1 轮 0 目标 | 5 | 10 / 10 | 0 | **65** | resume_exhausted（**V**） |
| spring 4 | 23 / 4 / 0（3 轮，reasons gated×4） | 4 / 4 | 1 轮 leftover 115 | 0 | 0 | 18 | 10 / 10 | 1 | **41** | resume_budget_exhausted（F） |
| spring 5 | 29 / 7 / 0（3 轮） | 7 / 7 | 0 | 1 轮 leftover 25 | 1 轮 0 目标 | 2 | 10 / 10 | 0 | **31** | resume_exhausted（**V**） |
| spring 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 / 0 | 0 | **0** | slept_without_work（F） |

合计 farm_actions=**218**（12+56+60+23+29）；runner 的 `finish.actions=297` 另含走路/观测/决策。**六天零 already**（没有"本来就不用做"的格）、零 plant、零 water——`stages_seen` 里出现 plant/water 只是因为跑过 0 目标空轮。

**为什么 6 天只有 ~300 个 action**（四个机制，均有行号证据）：

1. **每轮 till 上限 12 格**：`per_stage_tiles=12`（`longrun.py:1072`，runner 未覆盖）——不是体力上限（`stamina_budget.capacity=126`，L2/L449/L697）。
2. **每天只有 1–2 个 productive stage**：其余轮次全在"decision → verdict cancel → resume_reevaluate → resume_walk → 再 decision"里空转（spring 1 一天 24 次决策只有 1 次 llm，其余 deterministic）。
3. **收工极早**：spring 1 在 13:30（stamina 237.7/270，L118）、spring 5 在 13:10（145.7，L691）就睡——触发条件是走路预算 10/10 烧光（`no_progress_burst` L116/L250/L387/L577/L689），**不是**体力或时间到点。
4. **作业区窗口只有 25 格**：`_stage_tiles` 只取 `plot["tiles"] ∩ tillable`（`longrun.py:4835-4836`），看得见的其余可锄格要换片/重锚才够得着，而换片只在 plot_exhausted 时发生且有日限 10。

### 2.2 其余三跑逐日摘要

- **run1**：winter26 clear_area 3 轮合计 ok=8 / unreachable=12（bound=max(5,20%×20)=5 ⇒ `unreachable_within_bound=false` 红）+ 1 encircled_prefiltered；till/plant 各 1 轮 0 目标；ended `resume_budget_exhausted`（128 可执行余格，L435）。winter27 till ok=25 ⇒ **VERIFIED**（pending 全零，L499）。winter28 进行中 6 个 outcome（4 needs_review + 2 VERIFIED）后被中途杀。
- **fix**：winter26 clear ok=8 / unreachable=12 / encircled_prefiltered=1，ended `stuck:连续走路无进展`（`c383a0e` 的连续走路硬上限先 fire，L106）；winter27 till ok=137（16 轮）⇒ VERIFIED；winter28 till ok=41 ⇒ VERIFIED；spring1 全部 12 个 till 目标 unreachable + event_blocked（见 §6 A5）。
- **test-space**：winter26 clear ok=12 + 1 encircled_prefiltered、**till 0 格**（原因见 §5）、ended `resume_budget_exhausted`（43 可执行余格，L150）；winter27 进行中被杀（无 day_end）。

---

## 3. ② 那 38/12/17 格是什么；走路预算被什么烧光；spring 3/5 凭什么 verified

### 3.1 "可执行余格"的定义与坐标

口径来自 `_pending_snapshot`（`longrun.py:5299-5414`）：**最后一张户外观测里**"看得见 + 确实要做 + 预算/工具允许 + 四邻站得到"的账本格（`leftover_targets` 子集）。坐标证据（`no_progress_burst.pending_executable_tiles`，各只给前 8 个样本）：

| 日 | exec | 样本坐标 | 归属 | 性质 |
|---|---|---|---|---|
| spring 1（L116） | 38 | [50,28][50,30][51,27][51,28][52,26][52,28][52,33][53,27] | field_sw（`from_area=field_sw`，锚 [59,37]） | **跨片地**——玩家当天在 field_ne/field_se 干活，只换过 2 次片（ne→se→sw，L89/L94）就没预算了 |
| spring 2（L250） | 12 | [62,28][62,29][62,30][62,31][63,29][63,30][63,31][64,30] | field_ne 内、当前 25 格作业区窗口外 | **同片不同窗口** |
| spring 4（L577） | 17 | [49,37][50,34][51,33][51,35][52,33][52,34][52,36][53,35] | field_nw（`from_area=field_nw`） | **跨片地** |
| spring 3（L387） | 0 | — | — | 剩余全 blocked/unobserved |
| spring 5（L689） | 0 | — | — | 剩余全 blocked/unobserved |

排除项（三天 `encircled_pending` 均为 0）：**不是被围**（encircled 只发生在 winter26 的 [67,36] 四树格，run1 L15 / test-space L31）；**不是 tool_ineffective 那 8 格**（[73,25][74,25][73,26][74,26][67,30][68,30][67,31][68,31] 已被封进 `pending_blocked`/`proven_inert`，见 §6 A4）；**不是隔季种子格**（不可种的种子格根本不进目标池）。run1 winter26 的 128 格样本是地图边缘 [11,40][13,38]…（L435），fix winter26 只剩 5 格 [75,41]…[76,45]（L106）。

### 3.2 走路预算被什么烧光（spring 1 标本，L12-116）

1. L12：第一轮 till 12 格做成（还剩 11 格）。
2. L13 起：确定性兜底只提 `clear_area near:player`（`planner.py:2076-2081`：`brief.blockers>0` ⇒ 清障；注意 blockers 是**全场**计数，日志里出现"玩家周围还有 1220 处障碍"这种荒谬文案）。
3. `clear_area` 每轮都被**满包清障闸**打空目标池（`longrun.py:4767-4774`；`slot_relief{trigger=clear_gate}` L10/L51…）⇒ verdict 恒 cancel「看得见却没有一格可动目标」。
4. `resume_reevaluate{where=guard_leftover}` 清掉任务级 no_target → `resume_walk` 走回 leftover 锚点 → 重新观测 → 决策 → 又只有 clear_area → cancel → **再走**……×10（L16/L20/L24/L28/L73/L77/L81/L85/L90/L95；attempt 计数 11 但只有 10 条事件 ⇒ 有 1 次尝试未落盘， instrumentation 小缺口）。
5. 期间 7 次 `frontier_clear` 单格清障（L32-64）——真动作但每轮只 1 格，且会重置 `c383a0e` 的连续走路 streak。
6. 换片 2 次（L89 ne→se、L94 se→sw）后同一形态重演；L115 `plot_exhausted_burst`（1 秒 5 次换片）→ L116 `no_progress_burst` ⇒ `resume_budget_exhausted`。

**为什么 LLM 不再被唤回**：`task_kind_change` 边界只比"确定性计划的 kind"与"上次决策的意图集"——spring 1 的 new_day 决策里已有 clear_area（L9），之后确定性计划一直提 clear_area ⇒ 判不出"变化" ⇒ `boundary=None` ⇒ 全程 deterministic。对照 spring 2/3/5：LLM 在多个 task_kind_change 边界被唤回（spring 2 L136/L140/L145/L173/L180/L183）、持续提 till_area，才锄得动。

analyzer 新增字段实测（`tools/analyze-longrun.py` 本次改动）：**5/6 天命中 10/10 走路上限**（spring 6 为 0 次但也是 0 动作），六天走路 50 次 vs 真农场动作 218 次。

### 3.3 spring 3/5 凭什么 verified

判据链（`is_justified_end`，`longrun.py:606-643`）：`ended_by=sleep` + `ended_reason` 前缀 `resume_exhausted` + `pending_executable==0` + `pending_malformed==0` ⇒ `day_justified=true`；当天其余 9 项 checks 也全绿 ⇒ verified。

- spring 3（L391）：pending 20 = guard 7 + blocked 13；guard = exec **0** + unobserved 7；当天 till 60 格（6 轮），LLM 在 L280/L306/L346 等边界反复唤回续锄。
- spring 5（L694）：pending 33 = guard 6 + blocked 27；guard = exec **0** + unobserved 6；当天 till 29 格。
- 本质：两天把"当前观测里看得见的可执行格"锄完了，剩下的全判死/看不见 ⇒ 诚实收工。1/2/4 是预算烧光时可执行格还有 38/12/17 ⇒ `resume_budget_exhausted` 不在任何白名单 ⇒ 永不 VERIFIED。

---

## 4. ③ money 恒 3042 / free_slots 恒 0 / 零 seed buy / 零 upgrade 的完整因果链

1. **A9-start 存档**：money=2767、12 格背包、0 空格、内含 11 颗 Wheat Seeds（**夏季作物，冬/春都不可种**）（各跑 day_start L1）。
2. **winter 26 开局腾格**：`slot_relief` 卖 Wheat×5（125g）+ Geode×3（150g）（低于 keep=10 的整叠，run1 L6-7 / test-space L6-7）⇒ 腾出 2 格、进货出货箱。
3. **同日唯一一次 buy 探测**：item 472（Parsnip Seeds）⇒ 冬季货架没有（在售只有 Grass Starter/肥料/糖/面粉/米/油/醋/壁纸/地板…）⇒ `no_seed_for_sale` ⇒ `seed_dead_today` ⇒ `seed_unavailable_today`（run1 L9-10/L42；test-space L9-10/L28）。
4. **NewDay 结算**：2767+275=**3042**（test-space 当天又卖 Acorn 20g + Hay 0g ⇒ 次日 3062，L36-37）。
5. **此后每一天**：`slot_relief{space_pressure}`「背包里没有可卖的盈余叠 ⇒ 腾不出格子」（spring L5/L125/L261/L396/L587/L699，六天六条一字不差）——白名单经 task-28 收窄为 {Sap, Slime}，工具/武器/种子/升级材料/未知物永不卖，而包里恰好只剩这些。
6. **种子买永远走不到"尝试"那一步**：`free_slots<1` ⇒ `_maybe_buy_seeds` 在 `longrun.py:7486-7525` 直接记 `slot_relief{demand_basis=buy_full}`「买种子前背包满且腾不出格子 ⇒ **不买**」并 return（spring L6/L126/L262/L397/L588/L700）。⇒ 春天 Pierre 明明有 Parsnip，一次都没下单。
7. **plant_area 因此恒 0 目标**：分配额 = `min(per_stage_tiles, 当季可种种子数=0)`（`longrun.py:4860`）⇒ 六天零种植 ⇒ 零作物 ⇒ 零收获 ⇒ 零新收入 ⇒ money 恒 3042、free_slots 恒 0 自我锁死。
8. **upgrade 两条全断**：背包升级默认关闭（task-35 opt-in；task-34 探针判入口不可达）⇒ 每天一条 `buy{status:skipped, code:disabled}`（spring L4/L124/L260/L395/L586/L698）；工具升级「没有可做的升级（钱/材料不够…）」六天六条（无铜锭，L7/L127/L263/L398/L589/L701）。
9. **而 till_area 照跑**：`can_plant` 走"钱 ≥ 种子价（春天货架清单陈旧 ⇒ 回落配置价 20g）且今天没确认买不到"的口径（`_seed_outlook`，`longrun.py:3851-3870`；春天 buy 被闸在探测之前 ⇒ `seed_dead_today` 从未置位）⇒ 锄了约 180 格**永远种不下去**的地——正是 `longrun.py:4842-4847` 注释自己警告的"锄了种不下去 = 纯烧体力"。

**结论**：12 格背包 + 无过季种子处置 + 无跨日种子计划 = 结构性死锁。dev-coder 在制的 task-240b（腾格后立刻买种子）只补"腾出格后买不买"这一环，解决不了"整个 run 没有一个可卖的叠"这一层（详见 §6 A2）。

---

## 5. ④ winter26（test-space）vs spring 起跑差异

| 维度 | winter26（test-space / run1 / fix） | spring（spring 跑） |
|---|---|---|
| 货架 | 无作物种子 ⇒ buy 探到 `item_not_sold` | 有 Parsnip，但 buy 被满包闸拦在尝试之前 |
| `seed_dead_today` | 当天置位 ⇒ `can_plant=False` ⇒ **till_area 目标池直接空**（test-space winter26 till 0 格，L15/L19 seed_gate seeds=0 plantable=0） | 从未置位 ⇒ `can_plant=True` ⇒ till 照跑 |
| 守卫"该去买" | `seed_unavailable_today` 后不再当活（task-67 解药生效） | 天天喊"没种子但钱够，该去买" ⇒ 持续喂养走路循环 |
| 首日形态 | clear 12 ok + 12 unreachable（run1）/ 8 ok + 12 unreachable（fix）/ 12 ok + 1 encircled（test-space）；stalled 223–337 格 | till 为主（12–60 格/天），clear 几乎全被满包闸挡住 |
| 收工理由 | run1: resume_budget_exhausted（exec 128）；fix: `stuck:连续走路无进展`（c383a0e 硬上限先 fire）；test-space: resume_budget_exhausted（exec 43） | 3 天 resume_budget_exhausted（38/12/17）+ 2 天 resume_exhausted（exec=0）+ 1 天 slept_without_work |
| 对热身三天的意义 | winter 27/28 两天可 VERIFIED（fix：till 137/41，exec=0）——冬天没有种子，反而让"锄完眼前地"更容易达成 exec=0 | 春天"该去买"的守卫天天否决收工 ⇒ 三天拿不到 justified |

另注：run1 的 winter28 在 t=435.81 被中途杀（无 day_end），同 journal 又追加 31 行 winter26 重跑（L545-575，重启 11 秒后被杀）⇒ run1 实际没有完整 5 天闭环；`runA9-0749-run1-partial.jsonl` 是主 journal 前 544 行的备份（逐字节一致）。

---

## 6. ⑤ 给 dev-coder 的修复建议清单（按证据强度排序）

### A. 产品缺陷（可立项）

**A1【P0】走路预算空转（本跑最大浪费）**。productive stage 结束后确定性兜底只提 `clear_area`（必被满包闸 cancel），LLM 无边界可唤回 ⇒ 10/10 走路全烧、白天 13:00 收工。证据：spring L13-116；5/6 天命中 10/10；farm_actions 218 vs 走路 50。建议：① stage 以 needs_review 收场且 `leftover_executable>0` 时，兜底重提**同一 task kind**（retry till_area）而非只提 clear_area；② `task_kind_change` 边界增加"上一个执行完的任务还有可执行余格"触发条件（让 LLM 重新评估）；③ `c383a0e` 的连续走路硬上限应把单格 `frontier_clear` 视为弱进展（现在一次 acted 就清零 streak，spring 1 一天 7 次）。

**A2【P0】种子购买 catch-22（task-240b 在制，只修了一半）**。满包 ⇒ 不 buy；不 buy ⇒ 永远没种子 ⇒ 包永远满。工作树补丁让"腾格后立刻买"，但整个 run 没有可卖的叠（白名单 {Sap,Slime} + 工具/种子/未知不卖）⇒ 春季六天一次 buy 都没发起（spring 无任何 seed buy 事件；对比 winter 有 `buy{failed,item_not_sold}`）。建议：把"过季种子 Wheat×11"纳入可处置集合（吃掉/保留是产品决策，需 Lead 拍板）；最低要求：buy_full 闸之前先探一次货架，别让"春天有货"也被挡掉（春天 `shop_offers` 还是冬天陈旧清单 ⇒ `seed_price` 回落 20g ⇒ `can_plant` 恒真，锄了也白锄）。

**A3【P1】Brief 季度盲**。`seed_count` 只数堆叠不标季节（`planner.py:1754-1763`）⇒ LLM 六天里多次误判"背包里有春季种子"（spring L265/L280/L306/L703 的 intent reason 原文）。建议 brief 增加"当季可种 N / 过季 M（名字+季节）"。

**A4【P1】tool_ineffective 八格跨日重试**。[73,25][74,25][73,26][74,26][67,30][68,30][67,31][68,31] 每天试、每天被游戏拒（spring 2×1、4×4、5×7；analyzer 计 12 事件 / 8 格；reason 原文"目标格上仍有东西（现在还是 none）" ⇒ Mod `tillable[]` 假阳性，代码注释自认 m01804）。建议做跨日 game-refused 记忆（与我方 heuristic 封格分开记）。

**A5【P1】事件挂起鲁棒性（fix spring 1，L450-495）**。开局 `eventId=63` DialogueBox「Well, I just wanted to introduce myself...」冻住世界（`eventUp=true`、`canMove=false`）⇒ 12 个 till 目标全 unreachable、`event_wait`×2（各 15s）、`modal_dismiss_failed`×2 ⇒ `blocked_event` + 6 红 checks。事件来源【无法判定】（journal 无记录、SMAPI 日志不在仓）。建议：eventUp 期间不派农务目标（省下 unreachable 额度与日级豁免），或复用 task-25 的 `load_save(force)` 自愈路径。

**A6【P2】观测截断时的 unreachable 计口径**。run1 winter26 的 12 格 unreachable（bound=max(5,20%×20)=5）变红，但那片区四邻未全覆盖观测（`tilesTruncated=true`）⇒ task-27 的 `_known_enclosed` 不预过滤、执行层试不到就记 unreachable。建议截断观测下"四邻未全覆盖"的失败 reach 记 unobserved/encircled 候选。（此条同时碰判据口径，见 B2。）

**A7【P2】兜底理由文本误导**。deterministic 的「玩家周围还有 1220 处障碍」用的是全场 blockers 计数（`planner.py:1746-1747`），既喂错 LLM 也喂错日志读者。建议改口径或改文案。

### B. 判据口径问题（只能建议，由 Lead 裁决）

**B1. `resume_budget_exhausted` 的 `day_justified`**。现行 fail-closed（exec>0 必不 VERIFIED）在"可执行格全在别的片区/窗口外、当天预算已用尽"时会把诚实收工日判死（spring 1/2/4 即此形态）。若放宽（如"本片区 exec=0 即 justified"）会直接削弱 task-15 的防洗白设计 ⇒ **建议不动判据、改产品（A1）**；如 Lead 认为热身三天需要通融，可考虑"跨片不可达单独记一行证据"而非改判据本身。

**B2. unreachable 上界基数在截断观测日偏小**（见 A6）——改口径涉及 `unreachable_within_bound` 既有定义，需 Lead 裁决。

**B3. analyzer 的 ⚠「burst 当天却自称 VERIFIED」在本形态是误报**。spring 3/5（L386/L688）的 burst + `no_progress_burst{exhausted=true, exec=0}` 恰是诚实收工的证据链。建议把该警告收敛为"burst 且 ended_reason 无 exhausted 形态"才警告（若批准，我可在 analyzer 内实现——属 log-analyst 写范围）。

---

## 7. 已知限制 / 无法判定清单

- fix 跑 spring 1 的 `eventId=63` 来源【无法判定】（journal 无记录、SMAPI 日志不在仓内）。
- 各"可执行格"到底该 till 还是 clear，只能从坐标+zone 推断；journal 不存逐格目标种类。
- 38/12/17 的完整坐标只有前 8 个样本（`no_progress_burst` 截断），全量清单【无法判定】。
- test-space 用的是工作树未提交的 longrun.py（task-240b 在制），且 winter27 无 day_end（被杀）⇒ 该跑结论只取 winter26。
- runner 的 `actions=297` 与本文 `farm_actions=218` 口径不同（前者含走路/观测/决策），未逐项对账。
- spring 6 的 5 次"换片"反复选中同一锚点（field_se [67,23]，L706-722）——为何换片机制没有真正换区【无法判定】（plot 选择逻辑未在本文深挖）。

---

## 8. 证据索引（关键 journal 行号）

- spring 1 空转标本：`runA9-0749-spring.jsonl` L12（till 12 ok）→ L13-31（clear_area cancel ×4 + walk ×4）→ L32-64（frontier_clear ×7）→ L89/L94（换片 ×2）→ L115（burst）→ L116（no_progress_burst，exec=38）→ L118（sleep 730 / stamina 237.7）。
- spring 3/5 verified：同文件 L387 / L689（no_progress_burst exhausted=true、exec=0）、L391 / L694（day_end verified=true）。
- 满包三闸：spring L5（space_pressure 无可卖叠）、L6（buy_full 不买）、L10（clear_gate 不新开 clear_area）；六天同型 L125-137 / L261-276 / L396-408 / L587-592 / L699-704。
- 经济链：run1 L6-10（卖 Wheat/Geode + buy 472 失败）、L435（128 exec）；spring L4/L7（每日 buy disabled + tool_upgrade_skipped）。
- 事件挂起：fix L450（event_wait）→ L459-470（12 unreachable）→ L477/L490（dismiss failed）→ L491（event_blocked）→ L495（day_end 6 红）。
- 判据代码：`brain/agentfarm/longrun.py:606-643`（is_justified_end）、`:5299-5414`（_pending_snapshot）、`:7486-7525`（buy_full 闸）、`:4860`（plant 分配额）、`:1072`（per_stage_tiles=12）；`brain/agentfarm/planner.py:2076-2081`（deterministic clear_area 兜底）、`:1746-1747`（blockers 全场计数）、`:1754-1763`（seed_count 无季节）。
- 本次 analyzer 改动（tools/analyze-longrun.py + tests/test_analyze_longrun.py）：新增"走路预算燃烧"段与每日行片段；单测 `tests.test_analyze_longrun` **Ran 338 / OK**（新增 4 条）；全量 `Ran 1416` 中 7 失败 + 2 错误全部落在 `tests.test_longrun` / `tests.test_bridge_client`（dev-coder task-240b 在制补丁与已知环境假红所致，与本改动无关——两文件不 import analyzer；本文件只读代码未回滚任何在制改动）。
