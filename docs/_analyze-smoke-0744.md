# 0.7.44 首个真机冒烟账本分析（task-17）

**一句话**：`logs/longrun-smoke-0744.jsonl`（308 行、2 天、坏行 0）两天都 `verified=false / checks.day_justified=false`
却被判红，**不是农务失败**，而是三套计数口径不一致：守卫 `_pending_work()` 的累计账（263 / 217 格）≠ 日级
`plot_pending*`（取每阶段种类**最后一轮**，两天都是 0 ⇒ 中间轮 223/220 被遮蔽）≠ 观测片（`plot` 事件每片 25 格，
`tilesTruncated=true` 只在 note 原文、**不是结构键**）。本卡只做 info 聚合，不改 rc（冒烟仍 rc=1 / 红 33，与 HEAD 一致）。

## 1. 账本与两日读数

- 账本：`logs/longrun-smoke-0744.jsonl`（0.7.44；308 行；2 天：1年 winter 26/27；坏行 0）；
  console：`logs/longrun-smoke-0744.console.log` 58 行（两日收工分别在 :25/:37，收尾 :57 code=1）。
- `finish` L308：`code=1 verified_streak=0 actions=156 minutes=8.54 stages_seen=['clear_area','plant_area','till_area']`；
  `day_cap` L307：`days=2 max_days=2`。
- 两天统一形态：`ended_by=sleep`、`checks.no_unmet_stages=true`、`zero_action_evidenced=true`、`slept_ok=true`、
  `stamina_budget.deferred_by_budget_suppressed=1`（当天已浇完户外水 ⇒ 推迟事件一条不发，是设计）。

| 日 | ended_reason 前缀 | verified | day_justified | no_unmet_stages | ok/skip/fail | plot_pending（exec/blocked） | 阶段轮数 | 中间轮 max leftover（exec/blocked） | 最后一轮 leftover | slept_ok | 守卫 pending | stalled_total | 残余 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| winter 26（L240） | `stuck:` | false | false | true | 71/0/0 | 0（0/0） | 40 | **223（211/12）** | 0 | true | **263** | 261 | 2 |
| winter 27（L306） | `resume_exhausted:` | false | false | true | 20/0/0 | 0（0/0） | 7 | **220（220/0）** | 0 | true | **217** | 217 | 0 |

`stage_midway_leftover` 自己就警告了「最后一轮遮蔽」：冬 26 是 **L238**（round=39、leftover=2）、
冬 27 是 **L304**（round=1、leftover=220）——注意 L238 只报了最后一轮**之前**那轮 leftover=2，
更早的 211/223（round 0/1）连这条警告都没进，只能从 `stages[]` 里读。

## 2. 263 / 217 归属数字表（task-15 输入）

口径说明：各桶**不相加**（挡死与走不到有重叠；stalled 是「已标记看过」的格数，不是第三类格）；数字全部来自账本，
无坐标/无来源者一律【无法判定】，不猜。

### 冬 26（守卫 263 格）

| 桶 | 数字 | 证据（行号） |
| --- | --- | --- |
| 已做（`stage.ok`） | **71 步**（40 轮合计） | stages[]（day_end L240）；`ok_steps=71` |
| 已清（`stage.already`） | **22 步 / 11 段**（already_tiles 22 格） | stages[]；already 双列读数 |
| 挡死（blocked∪encircled） | **17 格** | 逐格可核：`gaps.json` 4 类 `first_seen` 全 = 冬 26（tree 12 / grass 3 / stone 1 / twig 1）；账本 blocked 坐标并集 17 格 |
| 走不到（unreachable） | **16 格** | `unreachable` 事件 16 次 + `unreachable_tiles` 16 坐标（去重后 16；与挡死有重叠，**不是相加**） |
| 停滞标记（`stalled_total`） | **261**（120/42/43/25/31） | `plot_exhausted` L62/79/94/97/103 + 守卫换片 burst L216/220/224/228/232 |
| 未标记残余 | **2**（263−261） | 同上（最后一条 L103 stalled_total=31 后不再增长） |
| 机制性无法判定 | **40 格**（263−223） | 守卫累计集合含 `stages[]` 快照之外的格：观测片 10 片×25=250 < 263（差 13 也不在片内）；这 40 格的坐标/归属账本里没有 ⇒【无法判定】 |

归因小结（冬 26）：263 中可核的「已有归处」部分 = 停滞标记 261（含已做/已清/挡死/走不到的重复记账），
**账本级唯一解释不了的是那 40 格**：`plots_capped` L81（`plots_today=10/limit=10`，冻结作业区后不再累计新片）
之后守卫仍保留当天早些时候的累计账，而每片观测只有 25 格、10 条 `plot` 事件全部带 `tilesTruncated=true`
（note 原文）⇒ 逐格核对不可能。**结论：263 是「累计账」，不是「当前可执行活」。**
（另：`unreachable` 事件 16 次 / 阶段 `unreachable_tiles` 16 格，与 gaps.json 17 格挡死的差 1 = encircled 1 格
`[32,20]` 的归类口径差，不是新格。）

### 冬 27（守卫 217 格）

| 桶 | 数字 | 证据（行号） |
| --- | --- | --- |
| 中间轮余格（round 0，执行前） | **220**（exec 220 / blocked 0） | `stage_midway_leftover` L304（round=1）；stages[] round 0 `leftover=220, leftover_executable=220` |
| 挡死（unreachable） | **3 格**：`[39,32]` `[39,31]` `[40,32]` | `unreachable` L294/296/298 |
| 守卫 pending | **217**（= 220 − 3） | `ended_reason` L306；`no_progress_burst` L300 `stalled_tiles=217` |
| 已做 | **20 步** | stages[]（day_end L306）；`ok_steps=20` |
| 已清（already） | **0**（本日 already 合计 0） | stages[] |
| 停滞标记 | **217/217（100%）** | `plot_exhausted` L272=71 / L275=23 / L288=43 / L291=75；L300 stalled=217 |
| 换片/回看 | 4 次换片、回片区 217 格 | `plot_exhausted` L272/275/288/291；`resume_exhausted` L306 原文 |

归因小结（冬 27）：**217 全部可逐格解释** —— 220（round 0 的片外累计）− 3 格挡死 = 217，
且 217/217 全部已标停滞（`stalled_tiles` 累计到 217）⇒ 守卫依赖的「活」= 已经回去看过、当前观测里没有可执行目标的格。
`resume_exhausted:` 前缀正是这一形态的诚实收工（brain 0.7.44 新口径）；它**不应**被当成 stuck/失败。
（`plot_exhausted` 的 `recovered` 与 `switches` 同值、`recovered` 单列不再另计；`plot` 只保留区/anchor/tiles 三个结构键。）

## 3. 三套口径为什么不一致（task-15 根因输入）

| 口径 | 数据源 | 冒烟两天读数 | 能不能证明「没活」 |
| --- | --- | --- | --- |
| A 守卫 | `work_reasons` 的 `pending = self._pending_work()`（brain `longrun.py:4802-4803` 原文「今天早些时候还有 N 格没做完（跨片地…）」） | **263 / 217**，换片过程中**不变** | 不能：它是当天累计账，含停滞/已回去看过的格，且不随当前观测收缩 |
| B 日级 | `day_end.plot_pending*` = 每个阶段种类**最后一条记录**的 leftover 之和（brain `:8813-8829`） | **0 / 0**（最后一轮 leftover=0；中间轮 223/220 被遮蔽） | 不能：只取最后一轮，`stage_midway_leftover`（L238/L304）就是为此警告 |
| C 观测 | `day_end.plots[]`（每片 25 格）+ `plot` 事件 note | 10 片 / 4 片；15 条 `plot` 事件全部带 `tilesTruncated=true`（**note 原文，非结构键**） | 不能：观测截断（400 格上限）后无法逐格核对；`plots[]` 只有 zone/anchor/tiles 三个键，没有截断标志字段 |

因此 `day_justified=false`（及既有 `missed:check:day_justified` 红）在冒烟两天**不是**农务失败证据，而是口径缺口。
本工具新增 `guard_count` 聚合把这三种读数**并排**列出：`guard_pending_max=263`、`stalled_marked_max=261`、
`residual_max=2`、`midway_events=2`、`truncated_plot_events=14`、`plots_capped_events=1`；
每一天给 `stage_leftover_max/exec/blocked`、`stage_leftover_last`、`midway_masked`、`plots_today/limit` 与原文行号。

## 4. 0.7.44 其余新形态在冒烟账本上的读数（info）

| 聚合 | 读数 |
| --- | --- |
| `resume_exhausted` | `found` 1 天：冬 27（L306，`switches=4`，burst L300 `count=1`、`switches=4`、`stalled_tiles=217`）；旧 `stuck:` 前缀 0 天 |
| `stage_realloc` | `zero`：`blocked{action=stage_realloc}` 事件 0 条、`alloc_capped_tiles` 全为 `[]` ⇒ **0 次封格**（旧实现把「键在场」当封过格，误算 47，本卡已修） |
| `leftover_split` | `ok`：47 段全带拆分，`exec_sum=632` + `blocked_sum=29` == `leftover_sum=661`，不变式 0 违背（冬 26：412+29=441；冬 27：220+0=220） |
| `slept_ok` | `true` 2 天（与 `checks.slept_by_us=true` 一致；`stuck_without_sleep` 0 天） |
| `budget_suppressed` | `found` 2 天：各 `suppressed=1`、`deferred_by_budget=false`、事件 0 条、`watered_outdoor=true` ⇒「日级>0 且无事件」是设计 |
| `already_aware` 双列 | 47 段：`ok_sum=91` / `already_sum=22`（`already_stages=11`）、`ok0=6`、**`ok0_already=0`** ⇒ 冒烟账本没有「ok=0 且 already>0」的段（判决仍要求两列并读） |
| `work_spot_resume_exhausted`（task-3 旧块） | `found` 1 天（冬 27）但 `burst_mismatch_days=[冬27]`：新前缀原文不含旧块要求的 `work_spot_resume`/`拿不出目标` ⇒ 旧块如实给⚠，新聚合 `resume_exhausted` 负责新前缀（两代形态**分开**、不混算） |
| `plot_exhausted` | 冬 26 五条换片（L62/79/94/97/103，`source=resume_ledger`，`pending=263`、`stalled_total` 120/42/43/25/31）+ 守卫换片 burst 五条（L216/220/224/228/232）+ 同一秒 5 次收尾（L233）；冬 27 四条（L272/275/288/291） |
| `resume_walk` | 冬 26 十条（`switched` true/false 混合、L123 guard 路径**缺** `switched`）；冬 27 六条；三态探针 `event:resume_walk.switched` 记录缺字段证据 |

## 5. 回归：HEAD（`a1d23b8`，task-13 版）vs 本卡（`scratch/_t17_cmp.py` 实测）

| 账本 | old rc/红/#无法判定 | new rc/红/#无法判定 | 说明 |
| --- | --- | --- | --- |
| runA | 1/117/128 | **1/117/128** | 不变 |
| runB | 1/84/133 | **1/84/133** | 不变 |
| run9 | 1/84/150 | 1/84/**151** | 仅新增探针 `day_end.plot_pending` 缺失 ⇒ +1（允许） |
| run9b | 1/45/150 | 1/45/**151** | 同上 +1 |
| run9c | 0/0/138 | **0/0/138** | 不变 |
| run9d | 1/29/125 | **1/29/125** | 不变 |
| A8（0.7.43） | 1/35/118 | **1/35/118** | 不变；`guard_count=undecidable`（12 天缺 `plot_pending_executable`） |
| smoke（0.7.44） | 1/33/105 | **1/33/105** | 不变；`guard_count=found` 2 天（本卡不新增任何红） |

`#无法判定` 合法增量只有 task-17 新增的 3 条探针（`day_end.verified` / `day_end.checks.day_justified` /
`day_end.plot_pending`；`checks.day_justified` 走**新增的嵌套 dict 分支**，其余旧探针判定路径未动）。

## 6. info-only 探针建议（交给 dev-coder，本工具不改 rc）

`guard_count` 已经是分析侧的可观测项；建议产品侧（task-15）择一/组合，均属验收口径修改、需 Lead 裁决：

1. **守卫 pending 扣除已停滞/挡死格**：`_pending_work()` 里 `leftover_targets - resume_stall_tiles - dead_set`
   后再决定是否发「还有 N 格没做完」；若剩余 0 ⇒ 不发该理由（这两天会变成 0）。
2. **`day_justified` 不采信 `day_end.plots[]` 满分**：当同日出现 `stage_midway_leftover`、`plots_capped`
   或 `stages[]` 中间轮 leftover > 最后一轮时，日级 plot_pending 需同时给「最后轮 / 中间轮 max / 守卫累计」三读数，
   否则「日级 0」会被当「无活」。
3. **零可执行日走明示收工**：`resume_exhausted:` 已覆盖冬 27；冬 26 的 `stuck:同一秒连发 5 次…` 建议同样
   走向明示收工（例如 `resume_exhausted:` / `no_executable:`），并在 `day_end` 同步写
   `plot_pending_executable/blocked` 与「守卫累计」字段，别让分析侧只能从原文解析。

本卡**不**改任何判红口径；若 Lead 决定把「守卫累计 vs 当前可执行」的不一致升级为红，需另开卡并同时更新
`tools/verify-run3.py`（本卡按指令未动它）。

## 7. 已知限制

- `tilesTruncated=true` **不是结构字段**：只在 `plot` 事件 note 原文与观测事件里；本聚合只按 note 计数（14 条），
  无法据此定位截断掉的格。
- `day_end.plots[]` 只有 `zone/anchor/tiles` 三键（每片 25），与 `plot_pending` 无结构关联；`plots[]` 合计
  250 与守卫 263 的差 13 也无法核对 ⇒ 那 40 格只能【无法判定】。
- `plot_exhausted.recovered` 与 `switches` 同值（0.7.44 现状），本工具把 `switches` 当权威，`recovered` 不另计。
- 冒烟账本 2 天样本太小；`guard_count` 的 `zero` 三态只在合成夹具里验证过（A8 旧账本=【无法判定】）。
- A8 账本（0.7.43）没有 `plot_pending_executable/blocked`、`slept_ok`、拆分字段 ⇒ 六聚合仍按【无法判定】呈现
  （task-13 口径不变）。
