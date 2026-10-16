# analyze-longrun 口径卡（与 `tools\verify-run3.py` 的同口径约定）

适用：`tools\analyze-longrun.py`（task-60 之后）。裁定来源：Lead m02565 / m02395（commit `69513b8`），
验收标准见 `docs\_run6-criteria.md` §3.1。本文件只回答一件事：
**从这份报告里读出来的数字，和 `tools\verify-run3.py` 是同一口径吗？**

## 1. 决策 / LLM 两档（Lead m02565，两边**同名同义**）

| 键 | 定义 | 含义 | run2 | run5 |
|---|---|---|---|---|
| `decisions_llm` | `event=="decision"` 且 `llm == true` | **发起过**模型调用（含被拒/截断/兜底） | 7 | 33 |
| `decisions_llm_used` | 且 `source == "llm"` | 模型结果**真被采纳** | 6 | 33 |
| `decisions_llm_fallback` | 二者之差 | `deterministic_fallback`：模型答了没用 | 1 | 0 |
| `llm_by_source`（旧键） | `source=="llm"`（不看 `llm` 键） | 只用于四路对账 | 6 | 33 |
| `llm_disagree_lines`（旧键） | `bool(llm) != (source=="llm")` | 不一致的行逐行点名 | [17] | — |

**判据说"LLM 覆盖 / 覆盖率"一律指 `decisions_llm_used`** —— 否则兜底会把 run6 的覆盖率刷虚高。

run2 的 `decisions_llm=7` 里有 1 条是兜底：`logs\longrun-3day-llm-run2.jsonl:17` =
`llm=true` + `source=deterministic_fallback` + `fallback="llm_error:truncated: …"`。
头部渲染（已核对 run2/run5 原文）：

```
决策: 17 次（decisions_llm=7，其中模型产出 decisions_llm_used=6，兜底 decisions_llm_fallback=1 见 [17]）；…
决策: 114 次（decisions_llm=33，其中模型产出 decisions_llm_used=33，无兜底）；…
```

`decision` 只有 `source`/`llm`/`boundary`/`truncated`/`fallback` 五键，**没有 token/usage** ⇒
本工具不报 token 消耗（`tests\test_analyze_longrun.py::TestDecisionSourceAccounting` :546）。

## 1.5 退出码（task-65，Lead m03207）—— 工具不能"永远绿"

默认**严格**：`0` = 本工具没抓到红；`1` = 有红；`2` = 跑不动（读不到 journal / 空账本 / 参数错）。
`--advisory` 保留老行为（恒 `0`，只当诊断用）。`--help` 里写同一段话（`parse_args` 的 epilog）。

"红"的口径（`is_red_finding()`）= 下面三类之一：

- `manual:*` —— 0 类"必须人工介入（红）"（模态挡住 / 职业选择 / `no_blocking_modal=false` /
  `unreachable_within_bound=false`）；
- `missed:*` —— 1 类"该做没做"（含 `missed:check:*`、`missed:no_work_with_dry`、`missed:cross_day`、账目差额）；
- 显式判红的 `wasted:*` —— `verified_zero_steps`、`verified_without_work`、`whitewash*`、
  `water_contradiction`、`water_scope_empty`、`finish_incoherent`、`finish_vs_days`
  （`wasted:leftover:*` **不算红**：它是"没做完"，由 `missed:*` 说话）。

**计数走全量、不走 `report["categories"]`**（后者被 `--top` 截断）—— 否则会出现"有红但 rc=0"的假绿。
`--json` 里新增 `report["red"] = {total, subjects, lines, advisory}`。

改前/改后 rc 对照（同一本账本，两工具并排；判决权威仍是 `verify-run3.py`）：

| 账本 | analyze 改前 | analyze 改后 | `--advisory` | verify-run3 |
|---|---|---|---|---|
| `scratch\journal-green.jsonl` | 0 | **0**（red=0） | 0 | 0 / VERIFIED |
| `logs\longrun-3day-llm-run2.jsonl` | 0 | **1**（red=19） | 0 | 1 / needs_review |
| `logs\longrun-3day-llm-run3.jsonl` | 0 | **1**（red=17） | 0 | 1 / needs_review |
| `logs\longrun-3day-llm-run5.jsonl` | 0 | **1**（red=62） | 0 | 1 / needs_review |
| `scratch\_t5x_vacuum.jsonl` | 0 | **1**（red=3） | 0 | 1 / needs_review |

⚠ 改后 run2/run3/run5/vacuum 变 `1` **不是回归**，是语义修正（改前那个 `0` 是"恒 0"假绿）。
**本工具的退出码只表达"有没有红"，不表达"整跑是否达标"**；达标看 `verify-run3.py` 与
`docs\_run6-criteria.md`。单测：`tests\test_analyze_longrun.py::TestExitCodes`。

## 2. 事件映射不许漂移（Lead m02395）

- brain 里 `_journal("<name>"` 的**每个**事件名都要在 `EVENT_BUCKETS` 里有桶；
  结构性事件 `day_start`/`day_end`/`finish` 记在 `STRUCTURAL_EVENTS` 白名单（不重复计数）。
- 账本里出现没桶的事件 ⇒ `report["unmapped_events"]`（名字 × 次数 + 行号）+ 头部
  「未映射事件（…绝不静默丢弃，先补 EVENT_BUCKETS 再读报告）」+ 建议 0a 排最前。
- 单测 `tests\test_analyze_longrun.py::TestEventMappingDrift` :856 直接对 **brain 源码**做机械核对
  ⇒ dev 一加新 `_journal` 名字，测试立刻红（写它时当场抓到 dev 新加的 `llm_trace_failed`）。
- run6 重点看的新事件**目前只计数、不分类**（等 run6 实际形态再定桶）：
  `goto_farm`、`stage_midway_leftover` —— run5 里分别是 5 与 7，此前被静默丢弃。

## 3. 与 `verify-run3.py` 的其余对齐 / 有意不同向

- 浇水证据四闸门**同向**：`checks.watered_outdoor` 缺失、`false`、`true + scope=="window" + tiles==0`、
  `true + final_water.dry>0`。
- `ended_reason` 以 `no_work` 开头且 `final_water.dry>0` ⇒ `missed:no_work_with_dry`（task-60），
  与它的 problem 同向；这类天的 `day_justified` 记 `day_justified_effective=false`。
- 跨日证据**有意不同向**：它把缺 `day_after` 记 problem（验收入口：缺失 ≠ 通过），
  本工具记 `undecidable`（行为分析口径）；两者都**不**把缺失当通过。
- `mod_version_mismatch`：它在验收里升为问题，本工具只记次数（分工见 `docs\_run6-criteria.md`）。
- **一眼相反时以 `verify-run3.py` 的 problem 为准，并停下报 Lead**（Lead m01934 规则）。

## 3.5 不可达（task-52，dev commit `294daea`）—— 环境挡路的第三种形态

- 三级留痕：`unreachable`（逐格：`tile`/`action`/`stage`/`zone`/`reason`/`note`）、
  `unreachable_stage`（阶段收尾：`stage`/`zone`/`tiles`/`in_leftover`/`coords`）、
  `unreachable_summary`（日级：`count`/`bound`/`attempted`/`exempted`/`raw_unmet`/`unmet`/`tiles`）。
- 政策口径（**两边同向**）：**不计当天硬失败**、当天记 blocked、**次日重试**；日级豁免上界
  `max(5, int(0.2×attempted_steps))`，豁免只扣 `no_unmet_stages` 的 leftover。
- 本工具归类：`unreachable`/`unreachable_stage` 进 **5 环境挡路（信息项）**，**不并进"该做没做"**；
  头部「不可达」行 + 建议 0e 报 次数/格数/`count`/`bound`/`attempted`/`exempt`。
- **账目差额口径不扩**：`missed:stage_account`（`failed_steps` vs `sum(stages[].failed)`）仍只认
  `env_block(+count)` + `inconclusive(+count)`，与 `tools\verify-run3.py:388-404` 逐字一致；
  `unreachable` **不算**进差额解释（不可达格被 exempt 后本就不该出现在 `stages[].failed` 里，
  真出现说明自述在重复计数 ⇒ 两边同向判红）。
- **硬闸门**：`checks.unreachable_within_bound == false` ⇒ 本工具 **0 类"必须人工介入（红）"**
  （`manual:check:unreachable_within_bound`），与 `tools\verify-run3.py:415-448` 的 problem 同向
  （豁免越界＝可能把真失败当"走不到"洗白）。
- 缺失这些字段（task-52 之前的旧账本）⇒ `unreachable_*` 计数为 0/`None`，**不判通过、也不凭空判红**。
- 单测：`tests\test_analyze_longrun.py::TestUnreachableAccounting`（5 条：桶/上界内信息项+解释差额/
  越界红/无计数解释仍红/缺字段不误报）。

## 3.6 真空日闸门（task-64，Lead m02981 / m03030）—— 与 `verify-run3.py:604-625` 同口径、不许更宽

- 规则（**两边同向**）：`day_end.verified is True` 且**当天有阶段记录**且 `Σ stage.ok == 0` ⇒
  本工具 `wasted:verified_zero_steps`（文案含"自称 VERIFIED 但当天成功动作 0 步"），
  它在同一形态下判 problem「自称 VERIFIED 但当天成功动作 0 步（有阶段记录、ok 全 0）」。
- **有阶段记录时不吃豁免**：`no_intents` / `plot_exhausted` / `policy_fallback` 只豁免
  `wasted:verified_without_work`（当天 0 阶段 + 没有"无活可做"证据）那条；两条并存、
  `verified_without_work` **不放宽**，新条**不更宽也不更窄**。
- 阶段记录两种形态都收：`day_end.stages[]`（brain 现在的写法）与**独立 `stage` 事件**
  （对照夹具 `scratch\_t5x_vacuum.jsonl` 的写法）⇒ 已给 `stage` 单独开桶 `stage_events`，
  并进【无法判定】清单的反面（不落 `unmapped_events`）。
- `0 < Σ stage.ok < 5` ⇒ 只记**弱日**信息项（头部「弱日: N 天（…）」），不判红（与它同）。
- `stages` 与 `ok_steps` **都缺** ⇒ 只进【无法判定】（"既没有 stages 也没有 ok_steps …
  缺失 ≠ 通过"）：既不判通过、也不当 0 步判红。
- 单测：`tests\test_analyze_longrun.py::TestVacuumDayGate`（4 条：真空日判红 / 独立 `stage`
  事件同样计数且不落未映射 / 弱日只记信息项 + `ok>=5` 干净 / 缺字段只进无法判定）。
- 顺带：`EVENT_BUCKETS` 同步收了 dev task-63 的 `clear_dead_scope`（只计数，等 run6 形态再定分类）。

## 3.7 被游戏拒绝（task-63 / task-66，dev commit `0d4d1c0` / Lead `2f088d9`）—— 环境挡路的第四种形态

- 事件（brain 钉死）：逐格 `tool_refused`（`tile`/`action`/`stage`/`zone`/`status`/`kind`/`reason`）、
  阶段级 `refused_stage`（`stage`/`zone`/`tiles`/`in_leftover`/`coords`）、日级 `refused_summary`
  （`count`/`bound`/`attempted`/`exempted`/`raw_unmet`/`unmet`/`tiles`）。
  三个名字都进了 `EVENT_BUCKETS`（桶名 `tool_refused` / `refused_stages` / `refused_summaries`）
  和 `NEW_EVENT_BUCKETS` ⇒ 不落 `unmapped_events`（漂移单测 `TestEventMappingDrift` 现在过）。
- **归因**：`till` 被游戏拒绝（`tool_ineffective` / `precondition_failed`）是**世界的前置事实**
  （不可锄的地 / 工具等级不够），不是"我试了没做成" ⇒ 本工具归 **5 环境挡路信息项**
  （`environment:refused` 逐日聚合 + `environment:refused_stage` 逐阶段），**不计当天硬失败、
  不并进"该做没做"**；政策是当天封格、**次日重试**。
- **两套豁免互不掩护**：`unreachable`（task-52）与 `refused`（task-63）各有自己的
  `bound = max(5, 20%×bound_basis（= attempted − encircled；见 §3.11）)` 与 `exempt`，各自从 `no_unmet_stages` 里扣减；
  本工具的账目差额口径仍与 `tools\verify-run3.py:388-404` 逐字一致（**只认
  `env_block`+`inconclusive`**）⇒ 拿 `refused` 去把 `stages[].failed` 差额洗平会被判
  `missed:stage_account`（有单测证伪）。
- **硬闸门（同向）**：`day_end.checks.refused_within_bound === false` ⇒ 本工具 0 类红
  `manual:check:refused_within_bound`（文案含 count/bound/exempt，提示人工核对 `refused_tiles`）；
  `tools\verify-run3.py:518-521` 把它判 problem「锄不动豁免超出上界 bound=…」⇒ 两边同向。
- **缺失行为**：`day_end.refused*` / `checks.refused_within_bound` 缺失 ⇒ 只进【无法判定】
  （6 条探针：`event:refused_summary`、`day_end.refused`/`_tiles`/`_bound`/`_exempt`、
  `day_end.checks.refused_within_bound`），**缺失 ≠ 通过**、也不静默丢弃。
- **交叉核对（合成账本，留档 `scratch\_t66_*`）**：`scratch\_mk_refused.py` 造
  `scratch\_ledger_refused_ok.jsonl`（count=3/bound=5/exempt=3/true）与
  `scratch\_ledger_refused_bad.jsonl`（count=9/bound=5/exempt=5/false）：
  界内 ⇒ 我 rc=0（0 红）、它只有一条复核信息行；越界 ⇒ 我 rc=1（3 红，含
  `manual:check:refused_within_bound`）、它 problem「checks.refused_within_bound=false」⇒ 同向。
- 5 个既有账本判决**不变**：green 0 / run2 1（red=19） / run3 1（red=17） / run5 1（red=62） /
  vacuum 1（red=3），与 `verify-run3.py` 并排 rc 一致（0/1/1/1/1）。
- 单测：`tests\test_analyze_longrun.py::TestRefusedAccounting`（6 条：两桶+不落未映射 /
  界内只 info 且可见 / 越界 ⇒ 0 类红 / 缺字段 ⇒ 无法判定不通过 / refused 与 unreachable
  计数不串 / refused 不进账目差额口径）。

## 3.8 守卫死锁类失败（task-69：run6 = `summer 4` 的 37 秒快速失败）

**形态**：脑侧守卫要求一个**现实不可满足**的条件（run6：「没种子但钱够 ⇒ 该去买」，而夏季 SeedShop
不卖硬编码的 `472`=防风草）⇒ 策略每轮都回到同一动作、世界零变化 ⇒ `ended_by=stuck`。
既不是环境挡路、也不是硬失败，**重跑无用**，必须改守卫条件（task-67 买种子按在售清单 /
task-68 枯死作物可达性）。

**run6 指纹（逐条可 grep，`logs\longrun-3day-llm-run6.jsonl`，143 行）**

| 指纹 | run6 实测 | 行 |
|---|---|---|
| 空转到第 3 轮 | `idle{rounds:3, acted:false}` ×2 | L68、L139 |
| 收尾方式 | `day_end.ended_by="stuck"`（两条日报告都是） | L70、L141 |
| 购买连续失败、**同一回执** | `buy{ok:false, code:"failed", receipt:"item_not_sold: …"}` ×6 | L2、37、56、73、108、127 |
| 唯一实体阶段全 0 成功 | `stage_exhausted{stage:"clear_dead", leftover:30, doomed:30, capped:0}` | L66、L137 |
| 不可达越界 | `unreachable_summary{count:42, bound:8, attempted:42, exempted:8, unmet:46}` ⇒ `checks.unreachable_within_bound=false` | L69、L140 |
| 自述死因 | `no_day_progress.reason = "stuck:连续 3 轮世界没有任何变化…守卫仍说还有活：没种子但钱够（956g ≥ 20g），该去买"` | L142 |
| 同日重试 | 2 个 `day_start`/`day_end` 都是 `[1,"summer",4]`、`day_after=null` ⇒ **1 个日历日**，不算跨日 | L1/L71、L70/L141 |

grep 配方（run7 起快速定位）：

```
# 1) 死锁三件套：stuck / 空转到第 3 轮 / 自述
rg -n '"ended_by": ?"stuck"|"rounds": ?3|连续 3 轮世界没有任何变化' logs\longrun-*.jsonl
# 2) 守卫要的条件是不是现实不可满足（买不到同一物品）
rg -o '"event": ?"buy".{0,200}' logs\longrun-*.jsonl
# 3) 唯一实体阶段全 0 ok（doomed=走不到 / capped=配额到顶，两者差别要看 stage_exhausted 字段）
rg -n '"stage_exhausted".{0,140}' logs\longrun-*.jsonl
# 4) 不可达越界（豁免把真失败洗白的风险）
rg -n '"unreachable_within_bound": ?false' logs\longrun-*.jsonl
```

**本工具怎么报（task-69 新增）**
- 头部 `同日重试: N 个会话只有 M 个不同日历日（…；**不算跨日、不算多天**；起跑行 […]）`——
  多份 `day_end` 来自同日重试，不是跨日；`ended_by != sleep` 时跨日证据一律 `n/a`，绝不发 `missed:cross_day`。
- 头部 `购买: N 次（成功 a / 没成交 b）；回执 item_not_sold×b ⚠ 同一回执连续失败 ⇒ 守卫死锁嫌疑（行 […]）`——
  **`buy` 桶存在 ≠ 买成了**：`ok=false`（或 `code` 非 ok）如实计成"没成交"，**回执码优先于桥的 `code`**
  （run6 的 `code` 恒为 `failed`，真正的指纹是 `receipt` 前缀 `item_not_sold`）。
- 建议 0g「购买没成交 ×N」+ 0h「同一天重复起跑 ×N」（排在最前，不会被 `--top` 截掉）。
- `buy` 没成交**不判红**（它不是验收口径违规，而是死因之一）；判红仍靠 checks 与 `stuck` 这类硬结论。

**与 `tools\verify-run3.py` 的分工（run6 实测同向）**：它 `needs_review`（problem：两条日报告的
`ended_by=stuck`、`verified=false`、`unreachable_within_bound=false`、`no_unmet_stages=false`，
外加 info「跨日没有推进 ×1」）；本工具 rc=1、0/3 VERIFIED、0 类红 2 条
（`manual:check:unreachable_within_bound` ×2）+【1 该做没做】12 条 +【5 环境挡路】10 条。
两边都把两个会话读成**同一个日历日**（`summer 4`），都不判通过。

**判据（可写进 run7 口径）**：当天出现 `ended_by=stuck`（或 `idle{rounds≥3}`），且
**没有任何成交类动作**（`buy`/`sell` 全失败或 0 次），且唯一实体阶段的 `ok` 全 0
⇒ 判"守卫死锁"：不判通过、重跑无效、必须改守卫条件或数据（种子 id / 在售清单 / 可达性）。

## 3.9 种子经济（task-70 / task-67，dev `2f4d03f`）—— 守卫死锁链的第一环

**三个事件（brain 只在"今天确认买不到"时发一次）**

| 事件 | 出处 | 含义 | 字段 |
|---|---|---|---|
| `no_seed_for_sale` | `brain/agentfarm/longrun.py:1605-1622` `_seed_dead`（名字按 `seed_dead_today` 选） | 货架上**一条种子都没有**（run6 夏季只有当季种子、硬编码 `472` 不在架） | `code`/`money`/`seed_price`/`keep_factor`/`offers`/`note` |
| `cannot_afford` | 同上（`pick_seed_offer` 返回 `cannot_afford`，`farmwork.py:717-744`） | 有种子，但按"留够 `keep_factor` 包"的口径**买不起** | 同上 |
| `seed_unavailable_today` | `brain/agentfarm/longrun.py:1381-1383` | "今天买不到"的**当天失效**留痕：`sleep_guard` 不再把「该去买种子」当活（否则永不可满足 ⇒ 3 轮零变化 ⇒ `stuck`） | `code`/`money`/`seed_price`/`note` |

**归类（Lead m03600 建议采纳）**：三个都算**同一类"种子/经济"**（环境事实，**不是硬失败、不判红**），
但**分开计数、不许互相掩护**：`EVENT_BUCKETS` → `no_seed_for_sales` / `cannot_affords` /
`seed_unavailable_today`（三个都在 `NEW_EVENT_BUCKETS` 里点名；`FIELD_PROBES` 也各有探针）。
漂移测试 `TestEventMappingDrift` 已覆盖（含独立事件形态）。

**本工具怎么报**
- 头部（有事件才打）：`种子经济: 买不到 N 次（没货 a / 买不起 b）；当天失效留痕 seed_unavailable_today M 次（money=…、seed_price=…、货架：…）`，
  当**有买不到结论却 M=0** 时追加 `⚠ 有买不到结论但没有当天失效留痕 ⇒ 守卫可能还在要「去买」（run6 死锁形态）`。
- 建议 **0i**「种子经济 ×N」：M=0 ⇒ 去查 `_seed_dead` / `seed_unavail_noted` 的退路；M>0 ⇒
  "防死锁路径走到了，此时再 `stuck` 就得查别的守卫条件（别继续怪种子）"。
- **缺失行为**：账本里没有这三个事件 ⇒ `report["seed_economy"]["total"] == 0`、**不打头部行、不出建议**
  （不编造、不当通过）；旧账本（run6 及之前）就是这一形态。
- 判据（与 §3.8 合看）：`no_seed_for_sale`/`cannot_afford` > 0 **且** `buy` 没成交 **且** `ended_by=stuck`
  ⇒ 守卫死锁；若同时有 `seed_unavailable_today`，死锁原因**不再是种子**，去查其它守卫条件。

**grep 配方（run7 快速定位）**

```
rg -n '"event": ?"(no_seed_for_sale|cannot_afford|seed_unavailable_today)"' logs\longrun-*.jsonl
rg -n '"event": ?"buy"' logs\longrun-*.jsonl          # 与上一条合看：买不到 + 买不成 = 死锁
rg -n '"ended_by": ?"stuck"' logs\longrun-*.jsonl
rg -n '"offers"' logs\longrun-*.jsonl                 # 架上到底有什么（run6 是 Melon/Tomato Seeds）
```

**顺带修的一个真 bug（task-70 发现）**：头部"新事件计数"以前拿**桶名**去查按**事件名**计数的
`report["events"]` ⇒ `buy→buys`、`sell→sells`、`plot_walk→plot_walks`、`unreachable_stage→unreachable_stages`
这类非同名映射**恒为 0**（run6 的 6 次 `buy` 就是这样在头部隐形的，靠 task-69 的专行才补回来）。
现在加了 `BUCKET_TO_EVENT` 反查：run3/run5/run6 头部立刻能看见
`plot_walks=…`、`seed_gates=…`、`buys=6`、`unreachable_stages=8`、`unreachable_summaries=2`（**纯呈现，rc 不变**）。

## 3.10 可达性/开路（task-76 / task-68）与 stuck 日有界翻篇（task-73，dev 在制）

**一句话**：`encircled`（被树/桩/大石围住 = 四邻没有「可站+可清」的突破口）、`frontier_clear`
（目标都够不着时至少清一格可达的可清障格；**`acted=false` = 想清没清掉**）、`clear_neighbor`
（开路清掉的邻格）与 `stuck_flush*`（stuck 日有界翻篇）**一律不判红**，只作信息项；
与 `unreachable`（物理走不到）**分开计数**、不封格、不进任何豁免分子。

| 事件 | 桶 | 归因 | 判红？ |
|---|---|---|---|
| `encircled` | `encircled` | 逐格被不可清障物围住（task-68 单独成类） | 否 |
| `encircled_stage` | `encircled_stages` | 阶段级 tiles/in_leftover/coords（**不进 `unreachable_exempt` 分子**） | 否 |
| `encircled_summary` | `encircled_summaries` | 日级 count/attempted/**engaged**（engaged 仅证据） | 否 |
| `frontier_clear` | `frontier_clears` | 开路尝试 tile/acted/attempt/limit/why | 否 |
| `clear_neighbor` | `clear_neighbors` | 为开路清掉的邻格（阶段级 opens/targets） | 否 |
| `stuck_flush` | `stuck_flushes` | task-73：绕过 `sleep_guard` 睡过去让整轮继续（ok/count/limit/day_after） | 否 |
| `stuck_flush_skipped` | `stuck_flush_skips` | 翻篇被跳过：`reason` = `eventUp=true` / `activeMenu=<存档类>` / 次数达 limit | 否 |
| `stuck_flush_resnap_failed` | `stuck_flush_resnap_failures` | 翻篇后重观测失败（只作诊断） | 否 |

- **没有硬闸门**：task-68 不存在 `encircled_within_bound`（不像 `unreachable_within_bound` /
  `refused_within_bound`）⇒ 本类**不产 0 类红**，`report["red"]` 里不会出现 `manual:check:encircled*`。
- **缺失行为**：`day_end.encircled*` / `encircled_summary` 缺失 ⇒ 逐条进【无法判定】（缺失 ≠ 通过），
  且**绝不静默丢弃**（`unmapped_events` 必须为空）；`stuck_flush*` 缺失就是 0 次、不打行、不出建议。
- **呈现**：头部两行 —— `可达性/开路: 被围住 N 次 / M 格；日级 count=…、engaged=…；开路尝试 N 次
  （真清掉 a / 没清掉 b）；为开路清邻格 opens=…`（开路全 `acted=false` ⇒ `⚠ 开路全部 acted=false`；
  `stuck` 且当天有阶段记录但成功动作 0 步 ⇒ `⚠ 零动作收工: <日>(L行)`）与 `stuck 翻篇: N 次
  （睡成功 a / 没成功 b）；被跳过 s 次（原因 …）；翻篇后重观测失败 c 次`；建议 **0j**（可达性/开路）
  与 **0k**（有界翻篇，含"绝不放宽验收"一句）。
- **与 `tools\verify-run3.py` 对齐（task-75，`8ceea87`）**：它侧白名单含 `encircled`/`encircled_tiles`，
  会话级自算 + info（`verify-run3.py:307-332` / `613-643`，含 `stuck` 且 `ok_steps==0` 的"零动作收工"）
  —— **两侧都只作信息项、都不判红**，口径同向、不必逐字相同。`stuck_flush*` 那边**尚未接**
  （task-73 的在制工作），本工具先收，避免漂移测试红。
- **判据**：被围住/开路失败/翻篇**都不能当通过**——尤其 `stuck_flush` 成功后当天仍是 `ended_by=stuck`、
  `day_justified=False`、**不 VERIFIED**（task-73 刻意绕过 `sleep_guard`，但没放宽验收）。
- **单测**：`tests/test_analyze_longrun.py::TestReachabilityAndOpenPath`（7 条：五事件有桶不落未映射 /
  被围住只 info 且与不可达分开 / 开路全失败可见 / 开路成功 + 邻格 opens / 零动作 stuck 日点名 /
  `stuck_flush` 有桶且可见 / 跳过原因与重观测失败点名且不判红）。

```
# run6 那种「19 秒零动作收工」下次一眼可见
rg -n '"frontier_clear"' logs\longrun-*.jsonl
rg -n '"encircled_summary"|"encircled_stage"' logs\longrun-*.jsonl
rg -n '"stuck_flush"' logs\longrun-*.jsonl
rg -n '"stuck_flush_skipped"' logs\longrun-*.jsonl   # reason=eventUp / activeMenu=存档类 / 次数达 limit
```

## 3.11 上界基数 `bound_basis`（task-78 / task-80，dev 在制 + Lead `2ce830b`）

### 为什么改
旧口径把日级豁免上界写成 `max(5, 20% × attempted)`，而 `attempted` **含被围住的格**。
deputy 的伪造账本 **V5** 就是这么打穿的：把 `encircled` 步计进 `attempted` ⇒ 分母被抬到 1000
⇒ 20% 上界 = 200 ⇒ **200 格真不可达被"豁免"、当天 exit 0**（`docs/_verify-run3-limits.md` v5）。

**Lead 裁定**：上界基数 = `bound_basis = attempted − encircled`（被围住的格既不是"走不到"也不是
"干了没成"，不该为豁免额度做贡献）。脑侧 dev-coder 在 **task-78** 落地该字段（`brain/agentfarm/longrun.py`：
stage 级 `bound_basis` = `attempted and not encircled` 的步数求和，日级 `rep.bound_basis`；
`unreachable_bound`/`refused_bound` 都改用它），工具侧 Lead 镜像提交 **`2ce830b`**（`tools/verify-run3.py`）。

### 本工具口径（与 `verify-run3.py` 同式）
- `FIELD_PROBES` 收 `day_end.bound_basis`；报告/文档里所有"上界 = 20% × attempted"字样改为
  **`20% × bound_basis`**（含本文件与 `MAPPING_TEXT`）。
- **自算 + 绝不采信更大的账本上界**：`bound_self_check()` 用
  `basis_self = max(0, attempted − encircled)`、`bound_self = max(5, floor(0.2 × basis_self))`；
  - 账本 `bound_basis > attempted` 或 `> basis_self` ⇒ **判红** `missed:bound_inflated`；
  - 账本 `unreachable_bound`/`refused_bound > bound_self` ⇒ 同样判红；
  - 账本没写上界 ⇒ 只报自算（不判红、不当通过）；连 `attempted` 都没有 ⇒ status=`undecidable`。
- `day_end` 缺 `attempted`/上界时退回同一天的 `unreachable_summary`/`refused_summary` 事件
  （run6 就是 `day_end` 缺 `attempted`、summary 里 `attempted=42` 的形状），两边都没有才算【无法判定】。
- 头部两行（`不可达:` / `游戏拒绝:`）追加 `；bound_basis=<ledger>（自算基数 a、上界 b）`；
  旧账本没有该字段时写 `bound_basis=<缺失>（自算基数 …，缺失 ≠ 通过）`，**不许当 0、不许当通过**。
- 两套豁免（unreachable / refused）**共用同一基数**，但各自的上界与 exempt 独立，不许互相掩护。

### 单测与回归
`tests/test_analyze_longrun.py::TestBoundBasisAccounting` 5 条：V5 抬高基数 ⇒ 红（自算基数 200、
上界 40 出现在报告里）/ 账本上界更大 ⇒ 红 / 同基数 ⇒ 干净且头部可读 / 旧账本缺字段 ⇒ 只进【无法判定】
不判红 / refused 侧同一基数。
6 本既有账本 rc 与判决**不变**：green 0(red=0)、run2 1(19)、run3 1(17)、run5 1(62)、run6 1(14)、
vacuum 1(3)（run6 ⇒ `bound_basis=<缺失>（自算基数 42、上界 8，缺失 ≠ 通过）`）。

### grep 配方
```
rg -n '"bound_basis"' logs\longrun-*.jsonl
rg -n 'bound_basis' docs\_verify-run3-limits.md
python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run6.jsonl | rg 'bound_basis|上界自检'
```

## 3.12 窗口口径 + 瞬间态已结清（task-88，Lead m04300）

### 两个病
- run7 有 7 天 / 683 个动作：summer 3–5 的红绝大多数是"当天后来真做成了"的**事件瞬间态**（阶段那一刻没目标、意图被取消），summer 6 的 74 条 `stage_exhausted` 里 70 条当晚被 `water_far` 补做；而 run7 的验收判据本来就是**尾部窗口**（`tools\verify-run3.py` 只要求窗口内达标）⇒ 旧行为"一条历史红就 rc=1"既误导（把已结清的历史当成当前问题）又挡住窗口验收。
- run7 的 `finish` 自述 `verified_streak=3`，而 task-65 的 finish 自洽检查拿 `--days`（默认 3）当目标 ⇒ 在 `--days 7` 下 `streak 3 < 7` ⇒ 误报 `wasted:finish_incoherent`。

### 口径（默认 `--window 3`，与 `verify-run3.py` 的尾部窗口同义）
1. **窗口** = 账本最后 N 天（默认 3；`--window 0` 关闭 = task-88 之前的行为）。窗口**内**的日级红照常 fatal；窗口**外**的日级红降级 `history_problems`：**逐条列出、不进退出码**（报告新增第 6 节「历史问题（窗口外，不进 rc）」）。
2. **不降级**的两种：①`连续 VERIFIED 天数 < N`（本跑没达标，历史问题不能替它开脱）；②**无日期归属的全局红**（`wasted:finish_incoherent` / `wasted:finish_vs_days` / `missed:stage_account`）永远 fatal。
3. **瞬间态 class-1**（`missed:cancel:*` / `missed:stage_no_target` / `missed:stage_exhausted` / `missed:plot_exhausted`）：当天 `day_end.verified=true` 且 `checks.no_unmet_stages=true` ⇒ 降级为 info（报告新增第 7 节「已结清」，文案带`（已结清…）`）。缺 `no_unmet_stages` ⇒ **不降级**（缺失 ≠ 结清）。
4. **finish 目标窗口** = `min(--window, 账本实际天数)`（`--window 0` 时退回 `--days`）⇒ `streak >= 目标窗口` 就不该报；`--window 7` 对 run7（7 天全 VERIFIED）不报自述问题。
5. **`seed_gate` 钱不够**：`seed_gate` 带 `money`/`seed_price`；`money < seed_price` 或 `seeds==0` ⇒ 呈现行点名「缺种子钱（money=14 < seed_price=20）」+「**未发起购买，不是任务失败**」（与 task-70 的 `cannot_afford` 同类语义）。缺字段 ⇒ 不加这半句（绝不臆断）。

### run7 读数（验收）
- `python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run7.jsonl --days 7` ⇒ **rc=0、红 0**（窗口内 0、窗口外历史问题 129、已结清 9）。
- `--window 7` ⇒ rc=1、红 130（严格口径，与 `tools\verify-run3.py --days 7` 的 rc=1 同向）；`--window 0` ⇒ rc=1（旧行为）。
- 五账本不变：green 0(0)、run2 1(19)、run3 1(17)、run5 1(62)、run6 1(14)、vacuum 1(3)。

### 单测
`tests/test_analyze_longrun.py::TestWindowAndSettledClassification`（9 条）：`test_window_demotes_out_of_window_reds` / `test_short_streak_keeps_reds_fatal` / `test_global_red_is_never_demoted` / `test_settled_momentary_event_is_info` / `test_settled_needs_no_unmet_stages` / `test_finish_self_report_uses_target_window` / `test_seed_gate_shortfall_line` / `test_real_run7_window_zero_red`。

### grep 配方
```
python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run7.jsonl --days 7 | rg "窗口|历史问题|已结清"
python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run7.jsonl --days 7 --window 0   # 旧口径对照
rg -n '"seed_gate' logs\longrun-*.jsonl
```

## 3.13 盈余材料换种子钱（task-55 / task-91，dev `6948bb4`）—— 种子经济闭环的后半段

| 事件 | 关键字段 | 归因 |
| --- | --- | --- |
| `surplus_sell` | `ok` / `sold` / `ok_count` / `fail_count` / `below_keep` / `trigger{money,threshold,emptyDirt}` / `keep` / `slots` / `whitelist` / `items` / `note` | 种子经济（信息项，**绝不判红**）：钱要等下一次 `NewDay` 结算 ⇒ **当天 `money` 不变是设计** |
| `surplus_sell_skip` | `short`（缺口 g）/ `below_keep` / `trigger` / `items` / `reason` | 想卖但没有材料超过保留线 ⇒ **不是失败** |
| `sell`（task-42 已有桶） | `strategy=surplus_materials` / `keep` / `below_keep` / `slot` / `qid` / `stack` / `before` / `after` | 逐叠出货；`ok=false` 才失败（另有 `sell_failed`） |
| `cannot_afford`（task-67） | `money` / `seed_price` / `short` / `offers` | 钱不够 ⇒ 当天不走 `buy`，**不是失败** |

- **呈现**：头部 `种子经济/出货:` 一行 —— `sell` 次数与成交/失败、`below_keep` 叠数、`surplus_sell` 汇总（sold 件数 / below_keep 叠）、`surplus_sell_skip` 次数与最大 `short`、`buy` 成交/未成交、`seed_gate` 次数。
- **建议 0i-3**：`sell` 有成交而**次日** `buy` 仍 0 ⇒ 只列**两个候选**（①**钱没到账**：出货钱要等下一次 `NewDay` 由游戏结算；②**货架没有当季种子**：看 `no_seed_for_sale.offers` 与 `cannot_afford.short`），**不下结论**。
- **缺失行为**：这些事件没出现 ⇒ 照既有规则进【无法判定】（`本账本没有 event:…`），不判红、不当通过。
- **单测**：`tests/test_analyze_longrun.py::TestSurplusSellAccounting`（5 条：有桶不判红 / 当天钱不变是设计 / 次日没买只给两候选 / 种子经济行齐全 / run7 无这些事件且仍干净）。

```
rg -n '"surplus_sell|"sell"|"cannot_afford' logs/longrun-*.jsonl
python tools/analyze-longrun.py --journal <ledger> | rg "种子经济/出货"
```

## 3.14 死苗 / 放弃格（task-84，dev `a29b170` Mod + `3b00761` 脑侧）—— 死苗不浇水

**为什么**：run7 的 `water_far [12,30]` 被记了 8 次 `unreachable` + 2 次「回执说浇了但 `farm.dryCrops` 没降」，为了一株够不着的**死苗**烧掉两个整天。task-84 起：`farm.dryCrops`/`dryTiles` **只算活苗**（死苗的"干"另走 `farm.dryDeadCrops`），`clear_dead` 排在浇水之前，够不着的干格如实 `gave_up_dry`。

| 字段 / 事件 | 关键键 | 本工具怎么读 |
| --- | --- | --- |
| `day_end.dead_crops` | Mod `farm.deadCrops`（全农场枯死格数） | 头部「死苗/放弃格:」；缺失 ⇒ 该字段记 `<缺失>` |
| `day_end.dead_crops_status` | `ok` / `unavailable` | 死苗计数的可信状态；缺失 ⇒ 总数【无法判定】 |
| `day_end.dry_dead` | Mod `farm.dryDeadCrops`（枯死**且没浇**，0.7.27 新字段） | `>0` 且 `ended_reason` 以 `no_work` 开头 ⇒ 红 |
| `day_end.dry_dead_status` | `ok` / `unavailable` | 同上；缺失 ⇒ 【无法判定】 |
| `day_end.gave_up_tiles` | 当天认输的窗口外干格坐标 | 非空却自称 `verified=true` ⇒ **只警告（`warn:verified_with_gave_up`），不判红** |
| `dead_crops_summary`（事件） | `dead_crops` / `dry_dead` / `dry_dead_status` / `gave_up` / `tiles[]` / `note` | 日级汇总（只在 `dead_crops>0` 且状态 ok 时写） |

- **两条红口径**：①`missed:dry_dead_uncleared` —— `dry_dead > 0` 且 `ended_reason` 以 `no_work` 开头（死苗不许当"今天没活"的借口；正确归宿是 `clear_dead`，够不着就如实 `stuck`/`gave_up_dry`；`tools\verify-run3.py:803-808` 同判 problem）。②`missed:dry_dead_bad_field`：`dry_dead` 不是整数 ⇒ 账目不可信、判红（`verify-run3.py:802` 同判 problem）。
- **一条警告（曾经是红，Lead m04997 裁定降级）**：`warn:verified_with_gave_up` —— `gave_up_tiles` 非空却自称 `verified=true`。**为什么只警告**：(1) 真洗白通道已被 `verify-run3` 更根本的闸门堵住 —— 认输格上的作物是干的 ⇒ `farm.dryCrops > 0`，脑若仍写 `watered_outdoor=true` 会被「`checks.watered_outdoor=true` 但 `final_water.dry>0` ⇒ 账本自相矛盾」判红，脑若不写 true 那天就 `verified=false`；(2) 能走到"VERIFIED + 认输格非空"的只剩"那些格当天后来被别的动作解决了、`dry==0`"的干净情形 ⇒ 判红是**假红**；(3) 两工具纪律是"同向"，**假红和假绿一样会让人不再信工具**（task-88 修的就是这个）。可见性不变：头部 `⚠ ...（warn:verified_with_gave_up；行 …）` + 建议 `0m`，`report["dead_crops"]["verified_with_gave_up"]` 保留行号，`rg` 可查。
- **缺失行为**：五个字段与 `dead_crops_summary` 都没有 ⇒ 头部写 `死苗/放弃格: <缺失>`，并进【无法判定】（`缺失 ≠ 0，绝不当"没有死苗"通过`），**不判红也不当通过**；部分缺 ⇒ 逐字段显示 `<缺失>`（看 `report["dead_crops"]["missing_fields"]`）。
- **呈现**：头部一行「死苗/放弃格: 枯死 N 格（状态 ok）、其中没浇 M 格（状态 ok）、当天认输格 K 格（坐标…）；口径：死苗不计浇水证据」+ 建议 `0m`；命中红口径或警告时追加 `⚠` 与行号。
- **单测**：`tests/test_analyze_longrun.py::TestDeadCropsAccounting`（6 条：`dead_crops_summary` 有桶不落未映射 / 干净日不判红且头部可见 / `dry_dead>0`+`no_work` ⇒ 红 / `dry_dead` 非整数 ⇒ 红 / **认输格 + VERIFIED ⇒ 只警告不判红且头部/建议可见** / 字段缺失 ⇒ 只进【无法判定】且头部 `<缺失>`）。
- **回归**：7 本账本（green/run2/run3/run5/run6/run7/vacuum）的 rc 与红数**一个没变**（旧账本全无 task-84 字段 ⇒ 只多【无法判定】行，不判红也不变绿）。

```
rg -n '"dead_crops_summary' logs/longrun-*.jsonl
rg -n 'dead_crops|dry_dead|gave_up_tiles' logs/longrun-*.jsonl
python tools/analyze-longrun.py --journal <ledger> | rg "死苗/放弃格"
```

## 3.15 背包空格死锁（task-102 `9b09735` / task-104）—— 买不到不是失败

**病**：run8 day 2/12/13 的形态 —— 卖盈余材料卖了钱（`money 14 → 188`）、货架上有当季种子（Wheat 10g），
但**背包空格 0** ⇒ `buy` 一直撞回执 `no_inventory_space`（run8 实测 26 次尝试里 **25 次**是这个回执），
守卫却还说"还有活" ⇒ 空转到 stuck。task-102 给脑侧加了三条留痕，task-104 又加了"人不在农场就别浇水"。

**四个新事件（全都不判红、绝不静默丢弃）**

| 事件 | 语义 | 本工具 |
|---|---|---|
| `buy_no_space` | 回执 `no_space`/`no_inventory_space`（背包放不下）⇒ **当天不再重试 buy**；字段 `item/price/attempt/free_slots_status/reason` | 信息项；头部「种子经济/背包」+ 建议 0n |
| `slept_without_work` | 当天 **0 农场动作**又有活 ⇒ **拒绝睡觉、当天不推进**（`why/farm_actions/reasons/note`） | 信息项；**不是"睡眠失败"**（那天会以 needs_review / `no_day_progress` 如实停住，`ended_by` 不是 sleep） |
| `modal_dismiss_failed` | 关模态时桥报错（`menu/reason`） | **只点名次数**：`tools\verify-run3.py` 不判它 ⇒ 判红会两边反向 |
| `water_far_skipped` | 窗口外有干作物但**人不在户外农场**（task-104，`reason=not_on_farm`）⇒ 不扣额度、不进 `given_up` | 信息项（桶 `water_far_skips`，见头部"新事件计数"）；不是失败 |

**呈现（头部一行 + 建议 0n）**：`种子经济/背包: free_slots …；buy 尝试 N 次；buy_no_space M 次；腾格卖出 K 次（why=need_slot）；当日钱 A → B；slept_without_work S 次`。

- `free_slots` 取自 `sell` / `surplus_sell` / `surplus_sell_skip` 的 `trigger.freeSlots`（task-102 起）
  —— **缺失 ⇒ 写 `<缺失>` + 进【无法判定】，绝不当 0**（run8 早于 task-102 ⇒ 就是 `<缺失>`）。
- **旧账本兜底**：run8 没有 `buy_no_space` 事件（当时代码没发），只有回执码 ⇒ 本工具从 `buy.receipt`
  里补认 `no_inventory_space`/`no_space`，并按**回执码**列出（`回执 no_inventory_space×25`）。
  没有这层兜底，run8 的头只会写 `buy_no_space 0 次`、把真正的死锁藏掉。
- 钱：`sell`/`surplus_sell` 成交**当天 `money` 不变是设计**（钱等下一次 `NewDay` 由游戏结算）
  ⇒ 本工具只呈现 `当日钱 A → B`，绝不判红；`buy` 为 0 条时也不许暗示"购买任务失败"。

**与 `verify-run3.py` 的同向性**：这四个事件它都不判 problem（它只看 `buy`/`sell` 的成/败与
`no_day_progress`）⇒ 本工具也一律不判红，只点名；`modal_dismiss_failed` 尤其不许判红（否则同一本账本
会出现"我红它绿"的反向）。缺 `day_end.refused*` 一类的字段照旧【无法判定】。

**读数（task-106，2026-10-15）**：`tests.test_analyze_longrun` **122 OK**；全量 `discover -s tests`
**618 OK（0 红）**；8 本账本 rc 并排（本工具/`verify-run3.py`）：green 0/0、run2 1/1、run3 1/1、
run5 1/1、run6 1/1、run7 0/0、vacuum 1/1、**run8 1/1**（两边都 FAIL ⇒ 同向）。

```
rg -n '"event": ?"(buy_no_space|slept_without_work|modal_dismiss_failed|water_far_skipped)"' logs/longrun-*.jsonl
rg -n 'no_inventory_space|no_space' logs/longrun-3day-llm-run8.jsonl
python tools/analyze-longrun.py --journal logs/longrun-3day-llm-run8.jsonl | rg "种子经济/背包|slept_without_work"
```

## 3.16 LLM 收工复盘 / 跨日教训库（task-58/59/82，Lead m05325）—— 「没学到东西」不是失败

**背景**：0.7.28 要装「决策演进」（用户 m12553）：夜里一次独立 LLM 复盘写 1–3 条笔记，次日注入
`Brief.recent_notes`；客观教训由代码从账本写进 `<journal>-lessons.json`，次日注入 ≤3 条。
brain 新增 5 个 journal 事件（机械枚举 `brain/agentfarm/{planner,longrun}.py` 得到，**一个都不能漏**）。

| 事件 | 字段（brain 权威） | 本工具 |
|---|---|---|
| `review_llm` | `day_key` / `notes`(≤3 条) / `text` / `usage` / `duration_ms` / `model` / `rejected` / `truncated` / `note` | 信息项；**声称成功却 0 条 notes ⇒ 红** `missed:review_llm_without_notes` |
| `review_llm_failed` | `day_key` / `reason` / `called` / `rejected` / `note` | 信息项（**失败无害**：睡觉与跨日照常） |
| `lessons` | `day_key` / `added`(id 列表) / `total` / `dropped` / `path` / `note` | 信息项；`total` 超上限 ⇒ 红 `missed:lessons_over_limit` |
| `lessons_load_failed` | `path` / `error` / `note`（`read_failed:`=JSON 坏、`not_a_list`=结构坏、`bad_path:`） | **红** `missed:lessons_load_failed`（教训库不可信） |
| `lessons_save_failed` | `path` / `error` / `note` | 信息项（本批教训只在内存里，跑批照常） |

**红口径（只有三条完整性红；全部进 `GLOBAL_RED_SUBJECTS` ⇒ 不被窗口降级）**
1. `review_llm` 声称成功却一条 `notes` 都没有 ⇒ 红。**与"没学到"严格分开**：`notes` 是空列表、
   模型输出被 `rejected`、`truncated=true` 都只记信息 —— 只有"事件声称成功、结果什么都没写"才红。
2. 教训库条数超上限：`lessons.total > 20`（brain `planner.LESSONS_MAX`）**或**落盘
   `<journal>-lessons.json` 条数 > 20 ⇒ 红（淘汰逻辑没生效，提示词预算会被吃光）。
3. 教训库读不了/文件损坏：`lessons_load_failed` 事件，**或**本工具按同一路径推导读该文件失败
   （JSON 坏 / 不是 list）⇒ 红。brain 的"失败无害"只保证**不中断跑批**，不保证账目可信。

**呈现**：头部一行 `LLM 复盘/教训库: 复盘 N 次、notes M 条（…字；被拒 R 条、截断 T 次）；复盘失败 F 次；
教训库 total X 条（上限 20；本日新增 A / 淘汰 D）；读写失败 load L / save S；落盘文件 …`，
并带 `⚠ 复盘声称成功却 0 条 notes` / `⚠ 教训库超上限`；建议 0o（红时点名行号，正常时只记一行信息项）。
**旧账本没有这些事件 ⇒ 头部 `<缺失>` + 【无法判定】（缺失 ≠ 0，绝不当"模型没学到东西"通过）。**

**教训库路径**：本工具用与 brain `_derive_lessons_path`（`longrun.py:761-771`）**完全相同的推导**
（`logs/run9.jsonl` ⇒ `logs/run9-lessons.json`），**不新增命令行开关**（Lead m05325 明确要求）。
`recent_decisions` 的条数/长度看头部`决策:`行（task-58 给每条补了 terminal/leftover/unreachable/
refused/where 具名田区、无坐标）；`recent_notes`/`recent_lessons` 是 `Brief` 的注入字段（同源于
`review_llm.notes` 与 `lessons`），账本里没有独立事件。

**读数（task-111，2026-10-16）**：`tests.test_analyze_longrun` **130 OK**（+8）；全量
`discover -s tests` **665 OK（0 红）** ⇒ 0.7.28 放行条件的两条漂移红清零。八账本 rc 并排
（本工具 / `verify-run3.py`）：green 0/0、run2 1/1、run3 1/1、run5 1/1、run6 1/1、run7 0/0、
run8 1/1、vacuum 1/1 —— **一字未变**。

```
rg -n '"event": ?"(review_llm|review_llm_failed|lessons|lessons_load_failed|lessons_save_failed)"' logs/longrun-*.jsonl
python tools/analyze-longrun.py --journal logs/<run>.jsonl | rg "LLM 复盘/教训库"
python -c "import json;d=json.load(open('logs/<run>-lessons.json',encoding='utf-8'));print(len(d.get('lessons',[])))"
```

## 3.17 教训库拒收留痕（task-114 F1，task-116 收录）—— 拒收不是失败，连续整版不可用才是警告

**背景**：task-114（commit `c135edc`）给跨日教训库加了 schema 校验：读回来的每条都过
`planner._sanitize_lesson()`（只认自己写出去的格式；未知 kind / 结构不符 / 超长 / 多行 /
抬高 severity 一律洗掉），**丢条必须留痕** ⇒ `brain/agentfarm/longrun.py:1674` 写
`lessons_rejected`（懒加载一次/进程）。analyzer 不收就出现漂移红（全量 2 条），卡住 0.7.28 冻结。

| 事件 | 字段（brain 权威，`longrun.py:1674-1677`） | 本工具 |
|---|---|---|
| `lessons_rejected` | `path` / `dropped`（丢掉几条）/ `reasons`（原因串）/ `kept`（这次载入**留下来**的条数）/ `note` | **信息项，拒收本身绝不判红**；头部 `拒收 N 次 / M 条（原因…）`；只有 `dropped>0 && kept==0` **连续 ≥2 天** ⇒ `warn:lessons_all_rejected` 可视行（不判红、不进 rc） |

**红口径（本卡不加任何红，只加一条警告）**
1. 拒收 = **正确行为**：文件被外部改过/结构不符时就该拒 ⇒ `dropped>0` 本身只记信息
   （与 task-111 的"没学到东西不是失败"同一家族）。
2. `dropped>0 && kept==0` 一天 ⇒ 仍只是信息（可能这一版库整体过期）；**连续 ≥2 天**
   （按行号归属到 `day_start` 分天、要求相邻两天的日序连续）⇒ 头部 + 建议给
   `warn:lessons_all_rejected`（文案写明"只作警告、不判红"）。
3. 缺 `kept`（或事件缺失）⇒ 只进【无法判定】（**缺失 ≠ 0，绝不当"没被拒收"通过**）。
4. `warn:` 是**可视行**不是红：`report["red"]` 不含它，`rc` 不变（退出码只表达有没有红）。

**呈现**：`LLM 复盘/教训库:` 行尾部追加 `；拒收 N 次 / M 条（原因 r1、r2）`（可 grep `拒收`）；
连续整版被拒时再追加 `⚠ warn:lessons_all_rejected（连续 K 天 dropped>0 且 kept==0：…；只作警告、不判红）`；
建议 0o 在无红时也会给一条 warn 文案（有红时并入红那条）。

**读数（task-116，2026-10-16）**：`py_compile -W error::SyntaxWarning` → `RC=0`；
`tests.test_analyze_longrun` **135 OK**（+5：`TestLessonsRejected` —— 入桶不漂移 / 拒收本身不判红 /
两连续天全丢只给警告 / 单天全丢不给警告 / 缺 `kept` ⇒ 无法判定）；全量 `discover -s tests`
**677 OK（0 红）** ⇒ 0.7.28 放行条件的漂移红清零。八账本 rc 并排（本工具 / `verify-run3.py`）：
green 0/0、run2 1/1、run3 1/1、run5 1/1、run6 1/1、run7 0/0、run8 1/1、vacuum 1/1 —— **一字未变**。

```
rg -n '"event": ?"lessons_rejected"' logs/longrun-*.jsonl
python tools/analyze-longrun.py --journal logs/<run>.jsonl | rg "拒收|warn:lessons_all_rejected"
python -c "import json;d=json.load(open('logs/<run>-lessons.json',encoding='utf-8'));print(type(d))"
```

## 4. 复核命令

```
python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run5.jsonl   # 有红 ⇒ rc=1（--advisory 才恒 0）
python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run6.jsonl   # run6：守卫死锁 + 同日重试
python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run7.jsonl --days 7   # run7：窗口口径 ⇒ rc=0；死苗字段缺失 ⇒ <缺失> + 【无法判定】
python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run8.jsonl   # run8：背包空格死锁 ⇒ rc=1（回执 no_inventory_space×25）
python tools\verify-run3.py      --journal logs\longrun-3day-llm-run7.jsonl   # 判决权威（同一尾部窗口口径）
python scratch\_mk_refused.py                                               # 造 refused 界内/越界两态夹具
python tools\analyze-longrun.py --journal scratch\_t111_demo.jsonl  # task-111 合成：复盘 notes + 教训库正常形态
python -m unittest tests.test_analyze_longrun  # 当前 135 OK（task-116）
python -m unittest discover -s tests           # 当前 677 OK（0 红；0.7.28 装机放行条件）
```
