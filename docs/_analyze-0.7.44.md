# 0.7.44 新字段/形态接入 + already-aware 双列（task-13，2026-10-18）

**一行摘要**：analyzer 新增六类 0.7.44 聚合（`resume_exhausted` / `stage_realloc` / `leftover_split` / `slept_ok` / `budget_suppressed` / `already_aware`），**全部默认 info 或【无法判定】、不进 rc**；A8 真账本 `logs/longrun-runA8-0743.jsonl` 读数 **rc=1 / 红 35 / `#无法判定` 118**（红数与 103→118 的 +15 全部来自新增 18 条探针在 0.7.43 账本里的缺失，属允许增加）；六本旧账本 rc/红数**一字未变**（runA 1/117、runB 1/84、run9 1/84、run9b 1/45、run9c 0/0、run9d 1/29），`#无法判定` 每本 **+17**（新增探针在旧账本缺失，如实【无法判定】）；already 双列在 A8 = `ok==0 && already>0` **0 段 / 0 天**（ok 合计 289 / already 合计 50；尾部窗口 3 天 ok 47 / already 3）——即 A8 的 `ok=0` 段**不是** already 空转，判决时仍须两列并读。

## 1. 背景与口径（为什么是 info/【无法判定】）

0.7.44 新增字段/形态（写点见 `brain/agentfarm/longrun.py`，本文件只引用行号）：

| 0.7.44 字段/形态 | brain 写点 | 语义 |
| --- | --- | --- |
| `ended_reason` 前缀 `resume_exhausted:` | `longrun.py:4019-4022` | 换片 + 回片区穷尽后的**诚实收工**，取代 A8 的 `stuck:回片区（work_spot_resume）`；不在 `JUSTIFIED_END_REASONS` 白名单 ⇒ 当天不 VERIFIED |
| `plot_exhausted{source,stalled_tiles,switches,…}` | `longrun.py:3948-3980` | 换片穷尽入口（`source=resume_ledger` / `resume_observation`） |
| `no_progress_burst{exhausted,switches,…}` | `longrun.py:4004-4015` | `_resume_exhausted` 唯一写 `exhausted=True` |
| `resume_walk{switched}` | `longrun.py:8496-8501`（work_spot_resume 路径） | 三态 true/false/缺字段（guard_leftover 路径 `:5076-5079` 不写该键） |
| `blocked{action=stage_realloc,alloc_no_progress,limit}` | `longrun.py:7080-7084`，常量 `MAX_ALLOC_NO_PROGRESS=3`（`:244`） | 同格反复重分仍无产出 ⇒ 封格（A8 冬 9/14 的 28/62 次 1 格余量重分是它前身） |
| 阶段记录 `leftover_executable/leftover_blocked` | `longrun.py:7325-7329` | `leftover` 语义一字不动，`leftover_executable + leftover_blocked == leftover` |
| `day_end.slept_ok` | `DayReport` 字段 `:668-669`，as_dict `:840`，`_do_sleep` `:6379-6381` | 扫钟是否真成功，与 `ended_by` 解耦；`checks.slept_by_us = slept_ok or ended_by∈{sleep,inventory_blocked}` |
| `day_end.plot_pending_executable/blocked` | as_dict `:855-856`；求和 `:8824-8830` | 二者之和恒等于 `plot_pending` |
| `stamina_budget.deferred_by_budget_suppressed` | `longrun.py:3440-3447` | `watered_outdoor=True` 时预算推迟**不发事件**、改记该计数；与 `deferred_by_budget > 0` **不得同真** |
| `stage.already_cause` | `longrun.py:7266-7285` | already 成因归类（0.7.44 起 `ok` = 真世界变化数） |

**设计口径（task-13 硬要求）**：新形态**默认 info /【无法判定】**，除非有硬证据否则不进 rc。
本任务没有发现任何会误进 rc 的新形态硬证据 ⇒ 六类聚合一律不进 `report["red"]`、不改 rc；
只在结构化字段在场且**自相矛盾**时给 ⚠ 提示（仍不进 rc）。缺失字段一律【无法判定】（缺失 ≠ 0、缺失 ≠ false），
`#无法判定` 只按新增探针增加、**不动任何旧探针判定路径**。

## 2. 新增聚合（报告键 + 三态 + 渲染）

| 报告键 | 判据 | 三态 / 呈现 |
| --- | --- | --- |
| `report["resume_exhausted"]` | `day_end.ended_reason` 前缀 `resume_exhausted:`（正则 `^resume_exhausted[:：]`）；旧前缀 `stuck:回片区（…）` 只计入 `legacy_days`（**不吞进新聚合**）；`no_progress_burst{exhausted=true}` 为旁证 | `state∈found/zero/undecidable`；有命中=found；无命中但 reason 字段或穷尽 burst 在场=zero；两者都缺=undecidable 且逐日进 `undecidable_days`；只有 burst 没原文 ⇒ `burst_mismatch_days`（⚠、不编原文）。头部「回片区穷尽（resume_exhausted 前缀，0.7.44）:」 |
| `report["stage_realloc"]` | `blocked{action="stage_realloc"}` 事件（结构化字段 `alloc_no_progress/limit/tile/stage/zone`）+ 阶段记录 `alloc_capped_tiles` | `state∈found/zero/undecidable`：有封格记录=found；`blocked` 事件或阶段记录带 `alloc_no_progress`/`alloc_capped_tiles` 机制字段但 0 命中=zero（机制在场 ⇒ 0 是真的）；两者都无=undecidable。头部「阶段重分配封格（stage_realloc，0.7.44）:」 |
| `report["leftover_split"]` | `day_end.stages[]` 的 `leftover_executable/leftover_blocked`；硬不变式 `exec+blocked == leftover` | `state∈found/zero/undecidable`：有 split 字段=found；无 split 但 `leftover`/`plot_pending` 在场=zero；全缺=undecidable。`mismatch` 逐阶段留痕（**违反不变式只记 info ⚠，不判红**，brain 侧语义由 brain 负责）；`cap_tiles` = `alloc_capped_tiles` 坐标并集。头部「余格拆分（leftover_executable/blocked，0.7.44）:」 |
| `report["slept_ok"]` | `day_end.slept_ok` 三态；与 `checks.slept_by_us` 交叉 | `true_count/false_count/undecidable_count`；`has_field=False` ⇒ 每一天【无法判定】；`slept_ok=false` 但 `slept_by_us=true`（或反之）⇒ ⚠ 自相形态（0.7.44 起 slept_by_us 由 slept_ok 兜底，正常不会自相）。头部「睡成功标志（slept_ok，0.7.44）:」 |
| `report["budget_suppressed"]` | `day_end.stamina_budget.deferred_by_budget_suppressed`；与同日 `deferred_by_budget>0` 交叉 | 字段缺失=undecidable；字段在场=total 计数；**抑制与推迟同日都 >0 ⇒ ⚠（设计不得同真）、不判红**。头部「预算抑制（deferred_by_budget_suppressed，0.7.44）:」 |
| `report["already_aware"]` | `day_end.stages[].ok == 0 && already > 0`（task-10 #1） | `state∈ok/undecidable`；**并列读数**：`totals{stages,ok0,ok0_already,ok_sum,already_sum,already_stages,names,coords}` + `window{labels,stages,ok0,ok0_already,ok_sum,already_sum}`（尾部 `--window` 天）；逐日给 `ok0/ok0_already/ok_sum/already_sum/already_stages`。口径：0.7.44 起 `ok` = 真世界变化数，`ok=0 && already>0` = 那一阶段一格没做成、但本来就没事可做；**不是白干、不是失败**。头部「already-aware 双列（ok=0 且 already>0，0.7.44 口径）:」 |
| 新增字段（进 `report["slept_ok"]`/探针，不单列聚合） | `plot_exhausted{source,stalled_tiles,switches}`、`no_progress_burst{exhausted,switches}`、`resume_walk{switched}`、`day_end.plot_pending_executable/blocked`、`stage.already_cause` | 只按 `FIELD_PROBES` 缺失判【无法判定】+ 供上述聚合旁证；不单独判红 |

**新增 18 条 `FIELD_PROBES`**（`#无法判定` 的唯一合法增量来源）：
`event:plot_exhausted.source` / `.switches` / `.stalled_tiles`、`event:no_progress_burst.exhausted` / `.switches`、
`event:resume_walk.switched`、`event:blocked.alloc_no_progress` / `.limit`、
`day_end.slept_ok`、`day_end.plot_pending_executable`、`day_end.plot_pending_blocked`、
`day_end.stamina_budget.deferred_by_budget_suppressed`、
`day_end.stages[].leftover_executable` / `.leftover_blocked` / `.alloc_capped_tiles` / `.ok` / `.already` / `.already_cause`。

`build_undecidable` 只加了**嵌套 dict** `day_end.stamina_budget.<键>` 的解析分支（通用分支会把 `stamina_budget.x`
当成 day_end 顶层字段名）；`day_end.stages[].<键>` 与 `event:<名>.<字段>` 走既有分支，未改任何旧路径。

## 3. A8 真账本读数（0.7.43，新字段全缺 ⇒ 回归证据）

命令：`python tools\analyze-longrun.py --journal logs\longrun-runA8-0743.jsonl --days 12`
（1322 行 / 0 坏行 / 12 day_end / 172 条 stage 记录 / VERIFIED 7/12）

| 聚合 | A8 读数（头部渲染原文） |
| --- | --- |
| `resume_exhausted` | `0 天（旧 stuck 前缀 3 天；ended_reason 在场且无新前缀 ⇒ 0 是真实读数）`；`state=zero`、`legacy_count=3`（冬 7 L139 / 冬 12 L581 / 冬 18 L1320）、`burst_exhausted_events=0` |
| `stage_realloc` | `<缺失>（本账本没有 blocked{action=stage_realloc}/alloc_capped_tiles 机制 ⇒ 无法判定重分配是否被封过；缺失 ≠ 0）`；`state=undecidable`、`events=0`、`stage_capped=0`、`has_blocked_events=false` |
| `leftover_split` | `<缺失>（0.7.43 前没有拆分字段 ⇒ 分不清「可执行余格」与「物理挡死格」；缺失 ≠ 0，绝不把 leftover 全当可执行）`；`state=undecidable`、12 天全部 `missing_split`、`stages=172/with_split=0`、`mismatch=0`、`cap_stages=0` |
| `slept_ok` | `<缺失>（12 天没有该字段 ⇒ 无法判定是否真睡成；缺失 ≠ 0；0.7.43 的 stuck 日没有这个真相字段）`；`true=0/false=0/undecidable=12` |
| `budget_suppressed` | `<缺失>（本账本没有该日级字段 ⇒ 无法判定「已浇过户外水导致预算延后被抑制」过没有；缺失 ≠ 0）`；`state=undecidable` |
| `already_aware` | `0 段 / 0 天；ok 合计 289 / already 合计 50（ok=0 的段 105 / 总段 172；窗口 3 天：ok=0&already>0 0 段、ok 47 / already 3）⇒ ok=0 不代表白干：already>0 = 那些格本来就不用做；两列必须并读（0.7.44 起 ok = 真世界变化数）；info、不进 rc` |

**already 双列逐日（A8，尾部窗口 = winter 16/17/18）**：

| 日 | stages | ok=0 | ok=0&already>0 | ok 合计 | already 合计 | already 段 |
| --- | --- | --- | --- | --- | --- | --- |
| winter 7 | 20 | 2 | 0 | 46 | 12 | 6 |
| winter 8 | 21 | 1 | 0 | 69 | 21 | 10 |
| winter 9 | 34 | 27 | 0 | 21 | 2 | 1 |
| winter 10 | 1 | 0 | 0 | 12 | 0 | 0 |
| winter 11 | 2 | 1 | 0 | 12 | 0 | 0 |
| winter 12 | 2 | 0 | 0 | 13 | 0 | 0 |
| winter 13 | 3 | 2 | 0 | 12 | 0 | 0 |
| winter 14 | 75 | 65 | 0 | 45 | 12 | 6 |
| winter 15 | 3 | 2 | 0 | 12 | 0 | 0 |
| winter 16 | 3 | 2 | 0 | 12 | 0 | 0 |
| winter 17 | 5 | 3 | 0 | 16 | 2 | 1 |
| winter 18 | 3 | 0 | 0 | 19 | 1 | 1 |
| **合计** | **172** | **105** | **0** | **289** | **50** | **25** |

⇒ **A8 预期 0 个 `ok=0 & already>0`，实测 0**。冬 9/14 的 ok=0 段（27/65）是 churn/挡死形态，不是 already 空转；
判决时**禁止**只看 `ok` 一列说「A8 白干」——必须并读 already 列（这 105 段里 already>0 的 0 段，两列都给了）。
0.7.44 真账本（A9/B9）到手后同一行会直接给出 `ok=0&already>0` 段数/坐标，作为 task-10 #1 的判决读数。

## 4. 六本旧账本回归（HEAD vs 新版，`scratch\_t3_cmp.py`）

| 账本 | rc / 红数（HEAD） | rc / 红数（新版） | `#无法判定`（HEAD→新版） |
| --- | --- | --- | --- |
| `logs\longrun-runA-0732.jsonl` | 1 / 117 | **1 / 117** | 111 → 128（+17） |
| `logs\longrun-runB-0732.jsonl` | 1 / 84 | **1 / 84** | 116 → 133（+17） |
| `logs\longrun-3day-llm-run9.jsonl` | 1 / 84 | **1 / 84** | 133 → 150（+17） |
| `logs\longrun-3day-llm-run9b.jsonl` | 1 / 45 | **1 / 45** | 133 → 150（+17） |
| `logs\longrun-3day-llm-run9c.jsonl` | 0 / 0 | **0 / 0** | 121 → 138（+17） |
| `logs\longrun-3day-llm-run9d.jsonl` | 1 / 29 | **1 / 29** | 108 → 125（+17） |
| `logs\longrun-runA8-0743.jsonl` | 1 / 35 | **1 / 35** | 103 → 118（+15） |

- **rc / 红数全部一字未变**（这是硬要求）。
- `#无法判定` 增量全部来自新增 18 条探针在旧账本里的缺失：旧六本各 **+17**（它们只有 `stages[].ok` 一条在场），
  A8 **+15**（A8 另有 `stages[].already` / `stages[].already_cause` 两条在场）。**没有一条来自旧探针判定路径的变化**。
- 复跑：`python scratch\_t3_cmp.py`（自动把 `HEAD:tools/analyze-longrun.py` 导出到 `scratch\_t3_head_analyze.py` 做并排）。

## 5. 单测与验证

- 定向：`PYTHONUTF8=1 python -m unittest tests.test_analyze_longrun` ⇒ **Ran 308 tests / OK**（task-13 新增 26 条，8 个类：
  `TestResumeExhaustedPrefix` / `TestStageReallocBlocked` / `TestLeftoverSplit` / `TestSleptOkField` /
  `TestBudgetSuppressed` / `TestAlreadyAwareDualColumn` / `TestTask13ProbesFailClosed` / `TestRealRunA8Task13`）。
- 全量：`PYTHONUTF8=1 python -m unittest discover -s tests` ⇒ **Ran 1303 tests / OK**。
- `python -m py_compile tools\analyze-longrun.py` ⇒ rc=0。
- 测试覆盖：六类聚合的正常形态夹具（0.7.44 字段在场）、三态（found/zero/undecidable）、缺字段 fail-closed
  （缺失 ⇒【无法判定】、不当 0/false）、already 双列（ok=0&already>0 命中 + 不命中 + 缺 `ok`/`already` 字段）、
  不变式违反（exec+blocked != leftover）只 ⚠ 不判红、`deferred_by_budget` 与 suppressed 同真只 ⚠ 不判红、
  A8 真账本新读数回归（`resume_exhausted` zero + legacy 3、stage_realloc/leftover_split/slept_ok/budget 全 `<缺失>`、
  already 0 段 / ok 289 / already 50、`red["subjects"]` 不含任何新聚合名）。

## 6. 已知限制

1. **本任务只有 0.7.43 的 A8 真账本**：六类新聚合在真账本上全部走【无法判定】分支（这正是 fail-closed 的证据），
   真正 0.7.44 形态（`resume_exhausted:` 前缀、`stage_realloc` 封格、真实 leftover 拆分、slept_ok、抑制计数、
   already 空转）只在**合成夹具**里验证过。A9/B9 跑完必须用本工具再核一遍真读数。
2. `plot_exhausted.source` 的取值按 brain 实写是 `resume_ledger`/`resume_observation`（任务描述里的
   `work_spot_resume/review_only_fallback/guard_leftover` 在 brain 里是 `where` 参数、进的是
   `no_progress_burst.source` 的「回片区（where）」文本）⇒ 两种都收，不按任务描述硬编码。
3. `resume_walk.switched` 在 guard_leftover 路径 brain 不写 ⇒ 该路径下是【无法判定】，不据此判红。
4. `leftover` 拆分不变式违反只给 ⚠：本工具不替 brain 判语义对错（brain 侧不变式由 brain 自检/单测保证）。
5. 尾部窗口（`--window 3`）在 A8 上 `active=false`（tail_streak 0，冬 16-18 未连续 VERIFIED）⇒ already 窗口列仍打印，
   但窗口不当作判决窗口；A9 若尾窗连续 VERIFIED 才会走窗口口径。
