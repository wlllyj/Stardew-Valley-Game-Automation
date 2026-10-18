# A8 真账本三种新形态读数（task-3）

**头部一行摘要：A8（0.7.43，`logs\longrun-runA8-0743.jsonl`，1322 行，winter 7→18 共 12 天）暴露 3 种旧 analyzer 只能人工读数才能发现的新形态——① `stage_churn` 2 天/3 段/89 次（冬 9 = 24+3 段、冬 14 = 62 段，同 stage 反复重分「1 格余量」、涉及格都是 `[37,35]`，最终 stuck）；② `work_spot_resume_exhausted` 3 天（冬 7/12/18，`ended_reason` 原文「stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标」）；③ `stuck_without_sleep` 2 天（冬 9/14，`ended_by=stuck` 但 `checks.slept_by_us=false`）—— 三者一律 **info /【无法判定】、不进 rc**，六本旧账本 rc/红数一字未变。**

- 分析者：teammate `log-analyst`（只读账本；只写 `tools/analyze-longrun.py`、`tests/test_analyze_longrun.py`、`docs/_analyze-*.md`、`scratch/`）。
- 分析对象：`logs\longrun-runA8-0743.jsonl`（mtime 2026-10-18 15:20:38，0.7.43 冻结提交 `5679562`；`-version.json` 记 0.7.43）。
- analyzer：`tools\analyze-longrun.py`（task-3 新增三聚合；判据常量 `STAGE_CHURN_MIN_RUN=3`、`STAGE_CHURN_SMALL_ASSIGNED=1`）。
- 复跑：`$env:PYTHONUTF8=1; python tools\analyze-longrun.py --journal logs\longrun-runA8-0743.jsonl --days 12`（rc=1；红 35 条是 A8 原有红，与三种新形态无关）。
- 取数脚本：`scratch\_t3_a8_table.py`（本文件所有表格/原文）；六账本对照：`scratch\_t3_cmp.py`。

---

## 1. 本工具在 A8 上的读数（一屏）

```
VERIFIED: 7/12 天（day_end 中 verified=true 7 次）
阶段 churn: 2 天 / 3 段 / 89 次（同 stage 连续 assigned<=1 且 stopped=incomplete、leftover 不降；
            最长 62 次；涉及格 [[37, 35]]）；纯 info：这不是失败、不进 rc
阶段 churn 日级: 1年 winter 9日=2 段/27 次（最长 24；格 [[37, 35]]）；
                1年 winter 14日=1 段/62 次（最长 62；格 [[37, 35]]）
回片区死循环（work_spot_resume）: 3 天收工（1年 winter 7日（连续 5 次；L139；no_progress_burst L134）；
                1年 winter 12日（连续 5 次；L581；no_progress_burst L576）；
                1年 winter 18日（连续 5 次；L1320；no_progress_burst L1315））
                ⇒ info：有界诚实收尾（task-134 A），不是失败、不进 rc；原文见下
stuck 未睡: 2 天（ended_by=stuck 且 checks.slept_by_us=false：1年 winter 9日、1年 winter 14日）
                ⇒【无法判定】当天没由我们睡过去、为什么 stuck / 是否真的收工说不清；不是失败、不进 rc
退出码: 1；有红 35 条（12 个 subjects；见上）——**全部是 A8 原有红**，三种新形态没有新增任何 subject
```

- 总读数：`rc=1`、红 **35** 条、`day_end` 12 条、可解析事件 1322/1322、`#无法判定` **103** 条。
- 蓝本账本同一读数（旧 analyzer `HEAD`）：`rc=1 / 红 35 / #无法判定 103`，新旧完全一致（本仓库 `scratch\_t3_cmp.py` 的 A8 段；HEAD 版导出 `scratch\_t3_head_analyze.py`）。
- 本报告**只**新增 info /【无法判定】聚合；A8 的 35 条红、六本旧账本的 rc/红数**都不动**（见 §5）。

---

## 2. A) `stage_churn`：同一天同一 stage 反复重分「1 格余量」

**判据**（`scan_stage_churn()`，`tools\analyze-longrun.py`）：`day_end.stages[]` 里**数组相邻**的记录满足

1. `stage` 同名且连续；
2. `assigned` 是整数且 `<= STAGE_CHURN_SMALL_ASSIGNED`（=1）——这一轮只分下去 1 格；
3. `stopped == "incomplete"`——这一轮还有分配未成事的格；
4. 段内 `leftover` 逐轮**不降**（next >= prev）——片区剩余没变少 = 空转；一旦降了就是有真实进展，段结束；
5. 连续长度 `>= STAGE_CHURN_MIN_RUN`（=3）——单次 incomplete 是正常重试，不算 churn。

**日级计数 + 涉及格坐标**：坐标只从结构化的 `cleared_tiles`/`unreachable_tiles`/`encircled_tiles`/`already_tiles`/`failed_tiles`/`ok_tiles`/`unexecuted_tiles` 数组里取（**绝不从 note/ended_reason 文本猜**）；`assigned`/`leftover` 缺失 ⇒【无法判定】（缺失 ≠ 0）。

### 2.1 逐日 churn 表（A8 全 12 天，`scratch\_t3_a8_table.py`）

| day | ended_by | verified | stages 数 | churn 段数 | churn 次数 | 最长段 | 涉及格坐标 | day_end 行 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| winter 7 | sleep | false | 20 | 0 | 0 | 0 | — | L139 |
| winter 8 | sleep | true | 21 | 0 | 0 | 0 | — | L240 |
| **winter 9** | **stuck** | false | 34 | **2** | **27** | 24 | `[[37, 35]]` | L518 |
| winter 10 | sleep | true | 1 | 0 | 0 | 0 | — | L533 |
| winter 11 | sleep | true | 2 | 0 | 0 | 0 | — | L553 |
| winter 12 | sleep | false | 2 | 0 | 0 | 0 | — | L581 |
| winter 13 | sleep | true | 3 | 0 | 0 | 0 | — | L606 |
| **winter 14** | **stuck** | false | 75 | **1** | **62** | **62** | `[[37, 35]]` | L1200 |
| winter 15 | sleep | true | 3 | 0 | 0 | 0 | — | L1225 |
| winter 16 | sleep | true | 3 | 0 | 0 | 0 | — | L1250 |
| winter 17 | sleep | true | 5 | 0 | 0 | 0 | — | L1285 |
| winter 18 | sleep | false | 3 | 0 | 0 | 0 | — | L1320 |

> 合计：**2 天 / 3 段 / 89 次**（27+62）；**冬 9 与冬 14 都是 `ended_by=stuck`、`verified=false`** —— 反复重分 1 格余量把一天耗到 stuck，而不是"在做实事"。

### 2.2 冬 9（L518，34 段里 28 段 `stopped=incomplete`）

- churn 段 1：`stages[6..29]`，**24 次**，每次 `stage=clear_area`、`assigned=1`、`assigned_undone=1`、
  `stopped=incomplete`、`leftover=1`（constant）、`reasons={"blocked_tile":1}`、`encircled_tiles=[[37,35]]`；
- 段 2：`stages[31..33]`，**3 次**，形态逐字相同（`leftover=1`、`[37,35]`）；
- 中间 `stages[30]` 是唯一一次成功（`ok=1`、`stopped=""`）—— 清掉一格后**下一轮又回到同形态**；
- 另有 `stages[5]`（`assigned=2`、`stopped=incomplete`）因 `assigned>1` 不计入 churn（口径边界）；
- 当天 `ended_reason` = `stuck:连续 3 轮世界没有任何变化（最后意图：['clear_area']；策略说有进展：False）；守卫仍说还有活：今天早些时候还有 209 格没做完（跨片地，最近的是 [43, 27]）；field_sw还有地要清/开/种`。

### 2.3 冬 14（L1200，75 段里 62 段同形态，最终 stuck）

- churn 段：`stages[13..74]`，**62 次连续**，每次 `stage=clear_area`、`assigned=1`、`assigned_undone=1`、
  `stopped=incomplete`、`leftover=3`（constant）、`unreachable_leftover=2`、`reasons={"blocked_tile":1}`、
  `encircled_tiles=[[37,35]]`；
- 段前 `stages[12]` 是 `stopped=unreachable`（`unreachable_tiles=[[39,32],[40,32]]`），随后转入 1 格余量循环；
- 当天 `ended_reason` = `stuck:连续 3 轮世界没有任何变化（最后意图：['clear_area']；策略说有进展：False）；守卫仍说还有活：今天早些时候还有 1 格没做完（跨片地，最近的是 [37, 35]）；field_nw还有地要清/开/种`。

### 2.4 两个"格坐标"别混

- churn 的坐标来自 stage 记录的 `encircled_tiles`，**冬 9 与冬 14 都是 `[37, 35]`**（同一格被反复重分）；
- 但冬 9 的 `ended_reason` 守卫说的是"最近的是 `[43, 27]`"（跨片 leftover 的最近格，另一个概念）；
- 冬 14 的守卫"最近的是 `[37, 35]`"才与 churn 坐标重合。⇒ 报告里**两处分别呈现**，不互相推导。

---

## 3. B) `work_spot_resume_exhausted`：连续 5 次拿不出目标而收工（冬 7/12/18 原文）

**判据**：`day_end.ended_reason` 原文含 `work_spot_resume` **且**含 `拿不出目标`（原文是一等证据）；
结构化旁证 = `no_progress_burst{source="回片区（work_spot_resume）", count=5, tiles=25}`（`brain/agentfarm/longrun.py:4600-4601`
`_no_progress_stop()`，`PLOT_EXHAUSTED_BURST=5`）。**这是 task-134 A 的防空转机制生效，不是失败**：
`ended_by` 可能是 `sleep`（`_do_sleep` 成功）或 `stuck`（被 `slept_without_work` 拦住），两种都如实保留原因。

| day | day_end 行 | ended_by | verified | 连续次数 | burst 行 / tiles | 原文 |
| --- | --- | --- | --- | ---: | --- | --- |
| winter 7 | L139 | sleep | false | 5 | L134 / 25 | 见下 |
| winter 12 | L581 | sleep | false | 5 | L576 / 25 | 见下 |
| winter 18 | L1320 | sleep | false | 5 | L1315 / 25 | 见下 |

**三天原文（逐字，`ended_reason`）**

1. **冬 7**（L139）：
   `stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标（守卫仍说还有活：今天早些时候还有 149 格没做完（跨片地，最近的是 [41, 18]））`
2. **冬 12**（L581）：
   `stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标（守卫仍说还有活：今天早些时候还有 216 格没做完（跨片地，最近的是 [51, 33]））`
3. **冬 18**（L1320）：
   `stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标（守卫仍说还有活：今天早些时候还有 177 格没做完（跨片地，最近的是 [64, 37]））`

**口径细节**：
- 三天都是**同一个 25 格跨片片区**（`burst.tiles=25`，`resume_walk` 连走到 5 次）—— 人回到那片地，但观测里仍拿不出目标 → 有界收工；
- `no_progress_burst` 的结构化证据在、`ended_reason` 原文也命中 ⇒ `state=found`、`reason_matched=true`；
- 若只有 burst 没有原文（或反之），报告会单列 `burst_mismatch_days`，**不许凭 burst 编原文**；
- 若整本连 `no_progress_burst`/`resume_reevaluate` 都没有（task-134 A 之前的老账本）⇒【无法判定】（缺失 ≠ 0，绝不当 0 次通过）。

---

## 4. C) `stuck_without_sleep`：`ended_by=stuck` 但 `checks.slept_by_us=false`（冬 9/14 原文）

**判据**：`day_end.ended_by == "stuck"` 且 `day_end.checks.slept_by_us is False`。

**口径（写清"为什么只能无法判定"）**：`slept_by_us=false` 说明当天**不是由我们睡过去**的（不是 `ended_by=sleep`）。
于是「这一天为什么 stuck / 到底有没有真的收工 / 世界有没有跨日」在账本里只有 `ended_reason` 一条自述，
没有"睡后重取的观测"（`day_after`）可对账 ⇒ 只能【无法判定】。**它既不是睡眠失败（`sleep:failed` 那条看 `sleep` 事件），
也不是通过**；`slept_by_us=true` 却 `ended_by=stuck` 的自相形态单独计 `coherent` 供人工核对；
`checks.slept_by_us` 整键缺失 ⇒ 同样【无法判定】（缺失 ≠ 0，绝不默认 false/true）。

| day | day_end 行 | ended_by | verified | slept_by_us | 原文 |
| --- | --- | --- | --- | --- | --- |
| winter 9 | L518 | stuck | false | false | 见下 |
| winter 14 | L1200 | stuck | false | false | 见下 |

1. **冬 9**（L518）：
   `stuck:连续 3 轮世界没有任何变化（最后意图：['clear_area']；策略说有进展：False）；守卫仍说还有活：今天早些时候还有 209 格没做完（跨片地，最近的是 [43, 27]）；field_sw还有地要清/开/种`
2. **冬 14**（L1200）：
   `stuck:连续 3 轮世界没有任何变化（最后意图：['clear_area']；策略说有进展：False）；守卫仍说还有活：今天早些时候还有 1 格没做完（跨片地，最近的是 [37, 35]）；field_nw还有地要清/开/种`

> 两天也正好是 §2 的两个 churn 日 —— 形态链：**反复重分 1 格余量（churn）→ 3 轮世界无变化 → stuck，且没睡过去**。
> 这是 task-3 想暴露的完整死循环现场；本工具只把它们如实摆出来（info /【无法判定】），不替 brain 下修复结论。

---

## 5. 变了吗？——六本旧账本回归（rc / 红数 / `#无法判定`）

对照方法：`git` HEAD 版 analyzer 导出到 `scratch\_t3_head_analyze.py`，与新版逐本各跑一次
`--json`（默认 `--days 3 --window 3`），比 `rc` / `red.total` / `len(undecidable)`（脚本 `scratch\_t3_cmp.py`）。

| 账本 | 旧 rc/红/`#无法判定` | 新 rc/红/`#无法判定` | 红数变化 | `#无法判定` 变化 |
| --- | --- | --- | --- | --- |
| `longrun-runA-0732.jsonl` | 1 / 117 / 111 | 1 / 117 / 111 | **0** | 0 |
| `longrun-runB-0732.jsonl` | 1 / 84 / 116 | 1 / 84 / 116 | **0** | 0 |
| `longrun-3day-llm-run9.jsonl` | 1 / 84 / 132 | 1 / 84 / 133 | **0** | **+1** |
| `longrun-3day-llm-run9b.jsonl` | 1 / 45 / 132 | 1 / 45 / 133 | **0** | **+1** |
| `longrun-3day-llm-run9c.jsonl` | 0 / 0 / 121 | 0 / 0 / 121 | **0** | 0 |
| `longrun-3day-llm-run9d.jsonl` | 1 / 29 / 108 | 1 / 29 / 108 | **0** | 0 |

> 唯一的 `#无法判定` 增量是 run9 / run9b 各 **+1** 条：新增探针 `day_end.stages[].assigned` ——
> 这两本的 `day_end.stages[]` 确实**没有** `assigned` 字段（0.7.36 时代的形态），所以按"缺失 ≠ 0"如实报
> 【无法判定】；其余 4 本的 5 条新探针都能在账本里找到键，故 0 增量。**这符合"#无法判定 只允许按新增探针增加"。**
> **六本 rc / 红数一字未变**（runA 1/117、runB 1/84、run9 1/84、run9b 1/45、run9c 0/0、run9d 1/29）。

> 结论：新聚合在旧账本上只会**多出 info 行**（例如 runA/runB 的 `harvest` 阶段也有 29/39/41/28 段的同形态 churn，
> run9d 的 summer 26 也有 1 天 work_spot_resume 收工），**不会有任何新红、不会改变 rc**；
> `#无法判定` 只按新增探针增加。

---

## 6. 单测与静态检查读数（2026-10-18，本提交）

```
python -W error::SyntaxWarning -m py_compile tools\analyze-longrun.py tests\test_analyze_longrun.py  # rc=0
python -m unittest tests.test_analyze_longrun        # Ran 282 tests ... OK（task-3 新增 18 条）
python -m unittest discover -s tests                 # Ran 1260 tests ... OK
```

- 新增用例：`TestStageChurn`（6）——正例（4 段/坐标/日级计数）、段长阈值、leftover 不降、同 stage/stopped 边界、
  `assigned` 缺失【无法判定】、`leftover` 缺失【无法判定】；`TestWorkSpotResumeExhausted`（5）——原文+burst 命中、
  只有原文、机制在场 0 天、机制缺失【无法判定】、burst/原文 mismatch；`TestStuckWithoutSleep`（3）——命中/coherent/缺字段；
  `TestRealRunA8Shapes`（4）——A8 真账本三条读数 + 不进 rc。
- 三种新形态的 **fail-closed**：缺字段一律走新增探针（`day_end.stages[].assigned` / `day_end.stages[].stopped` /
  `day_end.stages[].leftover` / `day_end.ended_reason` / `day_end.checks.slept_by_us`）→【无法判定】，
  绝不当 0、绝不当通过。

## 7. 已知限制 / 未做的事

1. **没有硬证据进 rc**：三种形态都只作 info /【无法判定】—— task-3 的要求是"新聚合默认 info 或【无法判定】，
   除非有硬证据才进 rc"。目前**没有**发现可以证伪成红的硬证据（churn 是行为证据不是失败；
   `work_spot_resume` 是有界诚实收尾；`stuck_without_sleep` 恰恰是"证据不足"本身），故一律不进 rc。
2. **churn 判据是"不降"不是"完全不动"**：段内 leftover 允许上升（更糟）也允许持平；只有**降了**才断段。
   如果将来要更严（例如要求 leftover 严格恒定），改 `scan_stage_churn()` 一个比较符即可，但旧账本读数会变。
3. **`work_spot_resume_exhausted` 依赖原文措辞**：brain 若改 `_no_progress_stop()` 的文案（例如"连续 N 次"变
   "第 N 次"），本工具的 `reason_matched` 会失真，但结构化 `no_progress_burst` 仍能兜住（此时进 `burst_mismatch_days`
   并提示"原文没命中 ⇒ 收工结论只能【无法判定】"）。
4. **A8 只到 winter 18**：`finish` 存在、`verified=7/12`；本报告不评价 A8 整跑是否达标（判决权威仍是
   `tools\verify-run3.py`），只报三种形态的读数。
5. **本报告只新增 info /【无法判定】聚合**：A8 的 35 条红与六本旧账本的 rc/红数都没有变（§5）；
   若 Lead 复核时看到任何红数变化，先按 `scratch\_t3_cmp.py` 复跑逐本对账，不要单方面改判定口径。
