# 0.7.39 实现前设计对抗评审（task-225）

- 评审人：deputy-lead（只读评审；只写 `docs/` + `scratch/`；未碰生产码/游戏/板面）
- 时机：task-218/222/219/220 **均未交付** ⇒ 本评审针对**计划与卡面**，比事后抓 bug 便宜，作为 task-224 对抗验收的输入之一
- 对象：`docs/_release-0.7.39.md`（§1 合入顺序 / §2 冻结九步 / §3 判据 / §4 风险）、
  `docs/_run10-criteria.md` **§8 意图-执行对账口径**（`8a32227`，含 §5/§6 对照）、task-218 卡（rev3）、task-219 卡（rev1）、
  task-222 卡（rev2）；代码取**当前 HEAD 工作树**（含 task-218 的部分在制雏形：`DEFERRED_KINDS` 已出现于 `planner.py:1238`）
- 说明：工作树有 task-218/222 在制改动 ⇒ 本报告的代码行号只用于**定位设计落点**，不当作已交付事实。

## §0 一句话结论

**设计可以开工，但有 4 项 P0 必须先补进卡面/判据** —— ①护栏 B 引用的 `farm.blockers` **在观测里不存在**（判据不可观测）；
②护栏 A 只测 `clear()` 单点、会漏掉其它丢 kind 的层（`_stage_tiles`/`_plot_has_work`/策略层），且缺**注册表漂移**测试；
③§8 原因码集与现有 `StepResult` 状态族没有完备映射、且 step/tile 单位未定义（对账可能永远"对不上"或永远"对得上"）；
④gaps 文件的 fail-closed 与"跨 run 长期缺口"没有分层（per-run 文件会丢长期缺口，而全局文件破坏 run 隔离）。
其余 6 项为开工前建议（可进 0.7.40），详见 §7。

## §1 护栏 A（意图-执行覆盖矩阵）能被怎么绕过

判定口径（计划 §3）：`OBSTACLE_KINDS ∪ CLUMP_KINDS` 每类要么能产出可执行目标，要么登记 `DEFERRED_KINDS` 且简报如实写"暂不支持"；两头都不在 ⇒ 红。

### §1.1 绕过路径（按危害排序）

| # | 绕过方式 | 具体反例（可写成测试） | 现设计是否拦得住 |
|---|---|---|---|
| A1 | **把整类登记进 `DEFERRED_KINDS` 就永久绿** —— 这正是当初 `SKIP_KINDS` 静默跳过树的重演，只是换了个"有理由"的壳 | `DEFERRED_KINDS["tree"] = "暂不支持"`（没有"缺什么能力/哪张卡/何时解锁"）⇒ 矩阵遍历仍绿，树一辈子不砍 | ❌ 拦不住（只查"在册 + 简报写了"） |
| A2 | **在别的层丢 kind**：矩阵只喂 `clear()`，但丢目标的层至少有 6 处：`farmwork.SKIP_KINDS`（`farmwork.py:113`）、`farmwork.clear()`（`:1868`）、`longrun._stage_tiles`、`longrun._plot_has_work`（`:2941`）、`longrun._plot_brief`（`:3104`）、`planner._apply_policy`／`sleep_guard` | `clear("tree")` 能产出目标，但 `_stage_tiles("clear_area")` 因 plot 过滤把该格排除 ⇒ 矩阵绿、实际永不执行 | ❌ 拦不住（单点测试） |
| A3 | **新增 kind 不自动变绿**：`OBSTACLE_KINDS`/`CLUMP_KINDS` 是手写常量，Mod 侧新 kind（如 1.6 新 debris 或 `greenRain` 变体）不会进入并集 ⇒ 矩阵对它"不存在"，天然通过 | 在测试夹具里加 `kind="driftwood"` ⇒ 两个常量都没它 ⇒ 遍历不到 ⇒ 绿 | ❌ 拦不住（需注册表漂移测试） |
| A4 | **简报只在"窗口 tiles 里看得见"时才宣告暂不支持**：`brief.deferred_kinds` 由 `present_kinds`（`:1554`）计算，而 `location.tiles` 缺失（summary 快照）或 `tilesTruncated` 时看不见树 ⇒ 简报不写"暂不支持" | 用 `observe?detail=summary` 跑一天：树在场但简报零字提及 ⇒ `deferred_capability` 的"简报如实写"条件被静默违反 | ❌ 拦不住（需 fail-closed announce） |
| A5 | **交集/漏项**：`clump` 同时在 `OBSTACLE_KINDS`（`:1229`）与 `CLUMP_KINDS`（`farmwork.py:138`）里；`stump/log/boulder/rockPile/greenRain` 只在后者；`grass/bush/fruitTree` 只在或特例 | 用集合差集断言"并集 13 类、各自归类唯一"否则矩阵会出现重复计数或漏测 | ⚠ 会漏（现设计没写去重/唯一归类规则） |
| A6 | **测试用合成 kind 而非真实快照**：夹具里手写 `{"kind":"tree"}`，但真实 Mod 的树走的可能是 `clump`（树桩）或 `tile.kind` 新值 ⇒ 测试"绿"与真机无关 | 用 `scratch/` 里带树 `observe?detail=full` 真快照做矩阵输入之一（卡面已要求离线复现，但没要求矩阵用它） | ⚠ 弱 |

### §1.2 若"模型仍反复要求暂不支持的能力"算不算红？

**不算红，但必须有牙**：`deferred_capability` 如实记录 = 我们想要的诚实；§8.3.6 的「同 (kind,reason) 连续 ≥3 天 ⇒ ⚠」就是牙。
但两个补充条件必须写死，否则会变成"永远 ⚠、永远没人修"：
1. `⚠` 一旦出现，**必须在 `docs/_run10-evidence.md`/验收报告里点名并给出修复卡号**（流程约束，写进 §8.4）；
2. 若该 kind **其实可执行**（`_stage_tiles` 能出格）却被登记为 deferred ⇒ **直接判红**（A1 的兜底）。

### §1.3 建议（P0，写进 task-218 卡面）

- **A-P0-1**：`DEFERRED_KINDS` 改为结构化登记：`{kind: {reason, missing_capability, blocked_by(卡号/里程碑), since_version}}`；
  `missing_capability` 为空 ⇒ 测试红；简报渲染必须带 `missing_capability`。
- **A-P0-2**：加**白名单快照测试**：`set(DEFERRED_KINDS) == {"fruitTree", "bush"}`（或显式核准的集合），
  任何人想再"合法化"一类必须改测试 + 改卡 + Lead 复核 —— 否则 A1 必然复发。
- **A-P0-3**：护栏 A 测试改成**端到端矩阵**，每类跑完整链路：
  合成观测（含该类）→ `_plot_has_work` 为真 → `_stage_tiles("clear_area")` 非空 → `clear()` 产出目标；
  并在**同一断言**里要求：不在 `DEFERRED_KINDS` 的类，`work_reasons`/`sleep_guard` 不得对"只有该类障碍"的日子说 `no_work`。
- **A-P0-4**：加**注册表漂移测试**（照 `TestEventMappingDrift` 的模式）：以 `docs/_tool-matrix.md` 或 `FarmScan` 的 kind 词表为源，
  断言 `OBSTACLE_KINDS ∪ CLUMP_KINDS` 覆盖全部已知 kind；并断言 `SKIP_KINDS ⊆ DEFERRED_KINDS`。
- **A-P0-5**：`deferred_kinds` 的可见性 fail-closed：`tiles` 缺失/截断时，若 farm 侧障碍计数非零 ⇒ 简报**也必须**写"树/障碍存在但暂不支持"；
  不允许因"看不见"而静默。

## §2 护栏 B（`clear_area` ok 步但 blockers 未降判红）会不会误伤

### §2.1 硬事实：**`farm.blockers` 字段不存在**

- `mod/AgentFarm.Bridge/Contracts.cs:751-796` 的 FarmView 只有：`loaded / hoeDirt / emptyDirt / crops / ripeCrops / readyCrops / deadCrops / unwateredCrops / dryCrops`
  ⇒ **没有 `blockers`，也没有 `weeds/stones/twigs/trees`**。
- `planner.py:1512` 的 `counts["blockers"] = weeds+stones+twigs+trees` 是**简报侧合成值**，且只在 `tiles_present == False`（summary 回退分支，`:1506-1513`）才用 farm 值；
  `farm.get("trees")` 在当前 FarmView 里恒取不到 ⇒ **summary 快照下 `blockers` 恒 0**（这本身是既有的简报失真，不只是护栏 B 的问题）。
- ⇒ 计划 §3 写的「当天 `farm.blockers` 未下降」**按字面不可实现**。必须先定义可观测口径，否则护栏 B 要么永不触发（假绿），要么开发时临时抓一个字段乱判。

### §2.2 判别口径建议（按"该判红 / 不该判红"列）

| 场景 | 该判红？ | 建议判据 |
|---|---|---|
| `clear_area` 有 ok 步，但这些 ok 步的**目标格**在当日末观测里仍是**同类障碍**，且无预算/工具/配额原因 | ✅ 红 | 逐格判：`affected_tiles ∩ 日末同类障碍格` 非空 ⇒ `stopped="world"` + 阶段 `incomplete` |
| 障碍消失但被**另一种障碍**接替（树被砍倒 → 留下树桩：`tree → stump`） | ❌ 不红 | 定义"已清除 = 目标格不再含**任何** `OBSTACLE_KINDS ∪ CLUMP_KINDS` 或 kind 变成非障碍"；`tree→stump` 记 **progress**，由 `clump_blocked_backlog`/下一阶段接手 |
| 清掉的是**窗口外**格（far dry/ready 一族那样走过去清），窗口内计数不变 | ❌ 不红 | 逐格证据只看被清格自身；farm 级聚合仅作 info |
| farm 证据不可用（`complete != true`）或 `tiles` 截断 | ❌ 不红 | 【无法判定】+ info（缺失 ≠ 通过：只说明"判不了"，但也不许当通过写 VERIFIED 的理由；该日已有其它 checks 兜底） |
| farm 级聚合净值为 0（清 3 格 + 新长/别处增加 3 格） | ❌ 不红（聚合口径下） | 这正是聚合口径的假红来源；**不采用聚合判红** |
| 作物收获/浇水导致的计数抖动（`crops/ripeCrops` 变） | ❌ 不红 | 护栏 B 只看障碍类，不碰 crop 计数 |
| 预算/工具挡下（`budget`/`tool_level`/`clump_blocked_backlog`） | ❌ 不红 | 已在卡面 4/5 条里，但要在判据里**显式列为豁免原因**，且记 journal |

**推荐实现**：`clear_area` 阶段记录 `cleared_tiles` / `unchanged_ok_tiles`（或复用 `affected_tiles` + `TileSig`），
护栏 B = `ok_steps > 0 and cleared_tiles == 0 and no (budget|tool_level|quota)` ⇒ `stopped="world"` + `incomplete`；
farm 级 `blockers` 只作 info —— 这样就**不需要** Mod 新增字段，也不必等 task-222。
若仍想用 farm 级计数，需在 task-222 给 FarmView 加 `weeds/stones/twigs/trees/clumps`（纯加法），并写清截断/缺失三态；这是 **P0 的备选路线**。

## §3 §8 原因码集的洞

### §3.1 已识别的洞（按严重度）

1. **`cancelled_by_verify` 语义过载**：`_verify_intents`（`longrun.py:5880-5938`）产出 `keep/unknown/cancel` 三态；
   `cancel` 的 docstring（`:5892`）自己写的是 `no_target`；而 `unknown`（作业区太远、先走过去）可能随后变 cancel；
   另外 `_apply_policy`（`:5940`）在 verify **之后**还会改写意图（顺序/替换）。
   ⇒ 三种完全不同的情况（真没目标 / 先走再看 / 策略改写）会被塞进同一码。**建议**：`cancel ⇒ no_target（带证据）`；
   `unknown` 最终未执行 ⇒ `blocked_tile` 或新码 `unknown_evidence`；策略改写 ⇒ 新码 `superseded`（见 5）。
2. **"执行到一半失败"没有码**：`executed_steps>0, ok_steps==0` 且 `failed/refused` 真实存在（`tool_ineffective`（锄不动）、`sow_failed`、`no_seed`、`stamina` 中途）
   在 10 码里没有对应：`tool_level` 只覆盖 clump；`world_stuck` 语义太宽。**建议**：先做**完备映射表**（每个 `StepResult.code/status` → 恰好一码），
   缺的码补进闭合集（候选：`tile_refused`、`no_seed`、`stamina` 或合并进 `budget`），并用漂移测试钉死"新状态码必须有映射"。
3. **`no_target` 证据未定义**：§8.2 只写"`_stage_tiles==[]` 且窗口/农场计数支持"。**建议** evidence 子结构：
   `{stage_tiles:0, window_tiles:n, tiles_present:bool, farm_complete:bool, deferred:[...]}`；
   `tiles_present==false`（summary）或 farm 证据不可用 ⇒ **禁止裸用 `no_target`**（改 `unknown_evidence`/`gated`），否则 no_target 不可证伪。
4. **跨日归属未定义**：`intent_plan`/`intent_execution` 若沿用"decision 行 + day_end 汇总"，跨日续跑会重复计数。
   **建议**：`intent_id = "{day_key}:{seq}"` 全局唯一、**禁止跨日复用**；`day_end.intent_coverage` 只汇总当日 intent；
   若确实需要"carried"，加 `carried_from_day` 字段并只在**原始日**计一次（analyzer 规则 1/2 只认原始日）。
5. **`reasons` 与 `unexecuted_tiles` 对账口径未定义**：现在没写"count 的单位是 step 还是 tile"，也没写总和约束。
   **建议**：瓦片制（砍一棵树 8 刀仍是 1 tile，attempts 另计）：`requested_tiles = ok_tiles + failed_tiles + unexecuted_tiles`、
   `Σ reasons.count == failed_tiles + unexecuted_tiles`（每格只归一个主原因；多原因放 `reasons_multi` 仅作诊断）—— 写成测试。
6. **无动作意图**：`_verify_intents` 对 `task not in STAGE_ACTION`（`sleep`/`review`，`:5924-5926`）**不产生 verdict**；
   若 §8.3.2「`executed_steps==0` 必须有原因码」不做豁免，会**每天误报** sleep/review。**建议**：定义 `ACTIONLESS_TASKS = {sleep, recover_stamina, review}`，
   这些意图允许 `reasons={}`（仍要 plan/execution 记录），并加测试。
7. **0 意图决策**（LLM 返回空、fallback）没有规定：应记 `decision.problems`/fallback，不产生 intent_coverage ⇒ analyzer 不得因此红。
8. **`reduce_scope` 意图**（`longrun.py:5905-5922`）有 keep/cancel 但没有"执行了认输"的码：建议 `gated`（或新码 `scope_reduce`），并在 gaps 里按 zone 聚合。

### §3.2 与 task-219 卡面的偏差

- 卡面把 `intent_plan` 说成"可复用 `decision` 行，加 `intent_id`"，但没定义 `intent_id` 生成规则与唯一性 ⇒ 见洞 4。
- 卡面 `intent_execution.reasons` 没写单位/对账约束 ⇒ 见洞 5。
- 卡面 `gaps` 聚合键 `(capability|kind, tool, reason)` 里 `tool` 对非工具类缺口恒空 ⇒ 明确"空串合法"。

## §4 `<journal>-gaps.json` 的 fail-closed 与跨 run 隔离

### §4.1 失败形态与处置

| 形态 | 处置建议 |
|---|---|
| 文件不存在（首次/本 run 无缺口） | 合法；只有"本 run 出现过 `deferred_capability`/`tool_level` 却写不出文件"才判问题 |
| 坏 JSON / 半写 | **原子写**（tmp + `os.replace`）+ schema 头；坏文件**不覆盖、改名归档**（`*.corrupt-<ts>`）+ journal `gaps_load_failed`；本轮从空开始并在 `day_end` notes 留痕 |
| 旧格式/未知 schema | 同上归档 + 按空加载（fail-closed），禁止"猜字段"；analyzer 对"缺 schema 且当日有缺口语义"判问题 |
| 写失败（磁盘/权限） | journal `gaps_write_failed` + analyzer：当日有缺口语义而文件缺失/未更新 ⇒ **problem**（缺失 ≠ 通过） |
| 并发双 run | 单 run 假设写进文档；文件按 journal 命名本身已隔离，不共享写句柄 |

### §4.2 跨 run 隔离 vs 长期缺口（设计缺口）

task-219 卡面：「跨日累积（run 边界不继承，随 journal 命名）」。这会**丢掉"跨 run 的长期缺口"**（A″/B″ 两跑各一份，修复卡需要的是"同一缺口跨 run 反复出现"）。
**建议分两层，且明确所有权**：
1. **brain 层（run 内）**：只读写 `<journal>-gaps.json`（run 隔离；A″ 与 B″ 互不污染，符合对照要求）。
2. **工具/分析层（跨 run 聚合）**：由 analyzer（task-220）或 Lead 的 `tools/compare-runs.py` 产出 `logs/gaps-registry.json`（append-only 聚合，**只读不参与 checks**）；
   brain **不写**全局层（避免并发/污染，也避免"gap 变成豁免"）。
- 这样 §8.3.4「deferred 而 gaps 无条目 ⇒ 红」只查 run 内文件；§8.3.6「连续 ≥3 天」在 run 内即可判定，跨 run 的 ⚠ 由聚合层在证据文档里出。

### §4.3 与 `lessons.json` 的边界

| | lessons 库 | gaps 清单 |
|---|---|---|
| 语义 | 行为知识（"别这样做/这样做"），教模型 | 能力事实（"现在做不到"），只提示 |
| 生产者 | 夜间复盘 LLM + 规则提炼（带 `src` 可信标记，task-118） | 执行对账（确定性，无 LLM） |
| 注入 | ≤3 条，裁剪优先级高于笔记/决策史 | ≤3 条 ≤200 字符，**最先被裁** |
| 是否能互相转换 | gap 修复后**可以**由复盘 LLM 总结成 lesson（带 `src`） | **禁止**自动把 gaps 转成 lessons（会污染 L0–L5 演进证据链） |
| 是否进 checks | 否 | 否（明确"不做豁免、不改 `_leftover`"，沿用 scope_shed 口径） |

## §5 与既有判据的冲突

1. **`no_unmet_stages` vs `intent_coverage`**：deferred 的 kind 不进 `_stage_tiles` ⇒ 不进 leftover ⇒ `no_unmet_stages` 可能为 True 而 LLM 意图"未执行"。
   这是**有意设计**（能力缺口不是 agent 偷懒），但必须写进口径并避免双判红：**能力缺口只由 §8 的 analyzer ⚠/gap 追踪，不进 hard checks**；
   同时护栏 A 必须保证"可执行却登记 deferred"会红（否则这条豁免就变成洗白通道）。
2. **`checks` 不加键**：analyzer 读 `day_end.intent_coverage` 可行 —— `analyze-longrun.py` 的 day_ends 解析保留**整个 dict**（`as_dict(...)`，`:5478` 一带），不靠白名单；
   但 **`tools/verify-run3.py` 对 day_end 有自己的字段白名单**（`:290-324` 一带，逐字段抽取）⇒ 新字段不会被 verify-run3 看到。
   **建议**：明确"§8 由 analyzer 判、verify-run3 不判"，并在 verify-run3 顺手把 `intent_coverage` 加入白名单只为 show/info（不改 rc），避免"两个工具口径打架"。
   另需在 analyzer 的 FIELD_PROBES 增加 `day_end.intent_coverage[(task,reason)]` 等条目（不加 EVENT_BUCKETS，因为不新增事件名）。
3. **§5/§6 既有口径**：§6.2「守卫的‘还有活’必须落到可执行目标」与护栏 A 同源，不矛盾；但落地时要避免重复判红——
   建议：护栏 B 判"阶段 incomplete"、§6.2 仍由 `work_reasons`/`intent_coverage` 暴露，**verify-run3 保持原判据**。
4. **L0–L5 冻结前不动**：§8 的 gaps 可作未来 L2 信号源，但 0.7.39 **不得**改 L0–L5 判定逻辑（A″/B″ 要在同一判据下跑）；建议 0.7.40 再加。
5. **旧账本**：无 `intent_coverage` ⇒ analyzer 逐条【无法判定】（§8.3.7），不得让历史账本矩阵 rc 变红 → 零回归断言里要把
   `green/run2/run7/runA-0732/run9b/run9c/run9d` 的 rc 前后对比写进验收。
6. **`stopped` 闭集**：护栏 B 判 incomplete 若引入新 `stopped` 值，会撞 analyzer 的 `stage_incomplete`/`stopped` 映射表（task-202 口径）——
   **建议复用 `stopped="world"` + journal 证据**，或先报 Lead 走 analyzer 卡，别悄悄加枚举值。

## §6 验收顺序：必须真机 vs 单测 + 最小冒烟清单

### §6.1 必须真机（单测无法替代）

| # | 项 | 证据 |
|---|---|---|
| R1 | `debug_dump table=trigger_actions` 不得 `unknown_skill`，且 `objects/big_craftables/machines` 能出强类型条目（task-222） | 回执 `table/type/count/entries/truncated` 原文 |
| R2 | 0 级斧砍普通树：多刀到消失、体力消耗、`use_tool` 的 `acted/actedEvidence`、`farm` 相关计数变化（task-218） | `observe?detail=full` 前后 + journal `clear_area` 步 |
| R3 | 桩/圆木/巨石 `toolOk=false` ⇒ `clump_blocked_backlog`；`toolOk=null` ⇒ 如实 skip（不挥）；升级选型选到斧/镐 | backlog journal + `_tool_upgrade_plan` 原文 |
| R4 | 一天真实 LLM 决策产生 `intent_plan`/`intent_execution`/`day_end.intent_coverage`，且 gaps 文件写出 | 账本逐行 + `-gaps.json` 文件 |
| R5 | gaps 次日可见（prompt 原文含 `recent_gaps` 段） | `-llm.jsonl` prompt 原文 |
| R6 | 新增活动后落盘链仍 6/6 配对（SMAPI 六串） | `scratch\_ab_save_pairs.py` 输出 |
| R7 | 跑 A″/B″ 时 gaps 文件按 run 隔离、互不继承 | 两文件 SHA/路径 |
| R8 | 既有账本矩阵 rc 不变（零回归） | 两侧工具原文 |

### §6.2 单测足够

护栏 A 端到端矩阵 + 注册表漂移；护栏 B 决策表（逐格 cleared/kind-change/budget/tool_level/证据不可用）；
§8 原因码完备映射 + 单位对账不变式；`intent_id` 唯一/跨日禁复用；ACTIONLESS 豁免；gaps schema/原子写/坏文件/归档/prune/大小上限；
brief 截断优先级（gaps 最先裁）；analyzer 七条判红（合成账本）；verify-run3 对新字段 info 不改 rc。

### §6.3 最小但充分的真机冒烟清单（按顺序，失败即停手）

1. 冻结装机九步 → `check-release --expect 0.7.39` 六绿。
2. **`debug_dump table=trigger_actions`** 一次（不得 `unknown_skill`；回执 type/list 可读）。
3. `debug_dump table=objects limit=3` + `machines limit=3`（强类型表各一次）。
4. 单技能砍树探针：对片地内一棵树连挥到消失（记录刀数/体力/`acted` + 前后 `observe?detail=full` 的树数差）。
5. `goto Farm` + `preflight --expect 0.7.39` 全绿。
6. 短跑 1 游戏日（LLM 开）：验 `intent_coverage` 有记录、gaps 文件存在、落盘 6/6、analyzer/verify rc 与旧口径一致。
7. 以上全过才允许起 A″/B″（0.7.39 批，5 天 ×2 + compare-runs L0–L5）。

## §7 必修（开工前就要改）与建议（0.7.40）

### §7.1 必修 P0（进 task-218/219/220 卡面或判据文档）

| # | 必修项 | 归属 | 不做的后果 |
|---|---|---|---|
| P0-1 | 护栏 B 观测口径：改为**逐格 cleared/kind-change**（推荐），或给 FarmView 加障碍计数字段（备选）；`farm.blockers` 字面判据作废 | task-218 | 判据不可实现/假红假绿 |
| P0-2 | 护栏 A：端到端矩阵（6 层）+ `SKIP_KINDS ⊆ DEFERRED_KINDS` + 白名单快照（只许 fruitTree/bush）+ 注册表漂移测试 | task-218 | 换壳静默跳过复发 |
| P0-3 | `DEFERRED_KINDS` 结构化（missing_capability/blocked_by）且简报 **fail-closed announce**（tiles 缺失也要写） | task-218 | 简报"如实写"条件被静默违反 |
| P0-4 | §8 原因码**完备映射表** + 单位对账不变式 + `no_target` 证据 schema + ACTIONLESS 白名单 + `intent_id` 唯一/跨日规则 | task-219 | 对账永远对不上或永远对得上 |
| P0-5 | gaps：schema 头 + 原子写 + 坏文件归档 fail-closed + 写失败判问题 + run 隔离（brain）与跨 run 聚合（工具）分层 | task-219/220 | 丢长期缺口或污染 run 对照 |
| P0-6 | analyzer 接入细节：FIELD_PROBES 登记、verify-run3 白名单是否加（建议 info-only）、旧账本【无法判定】、零回归断言 | task-220 | §8 判红空转或误伤历史账本 |
| P0-7 | 口径文档写死"能力缺口 ≠ hard failure、不进 `_leftover`/checks；可执行却登记 deferred ⇒ 红" | `_run10-criteria.md` §8 | 护栏与豁免互相掩护 |
| P0-8 | 冻结九步的烟雾扩成 §6.3 清单（含 `trigger_actions`、单技能砍树、1 日 intent_coverage） | `_release-0.7.39.md` §2 | 装机后才发现技能不可用 |
| P0-9 | 护栏 B 若引入新 `stopped` 值 ⇒ 先报 Lead 走 analyzer 卡；否则复用 `stopped="world"` | task-218/220 | analyzer 映射漂移 |

### §7.2 建议（0.7.40 或按需）

- S1：`L2` 信号源扩展：把 gaps 的 `(kind,reason)` 计数纳入 compare-runs 的 L2 三态（需先在 0.7.39 把数据形状稳定）。
- S2：`gaps-registry.json` 由 analyzer 产出并在证据文档里出"跨 run 反复缺口"表。
- S3：FarmView 增加 `weeds/stones/twigs/trees/clumps`（纯加法）——护栏 B 与简报计数都受益。
- S4：树→树桩的转移写成正式映射表（cleared/progress/blocked 三态），供所有"清障有效性"判据复用。
- S5：`reduce_scope` 的认输/释放也进 intent 对账（gaps 按 zone 聚合），避免"规模取舍"成为 §8 盲区。
- S6：把 `docs/_tool-matrix.md` 升级为机器可读清单（drift 测试的单一事实源）。

## §8 边界

- 只读评审：未修改 `brain/`、`mod/`、`tools/`、`tests/`、`logs/`；未跑游戏/桥；未改板面。
- 代码行号基于当前工作树（含 task-218/222 在制雏形）；实现后需以冻结树复核。
- 本报告供 task-224 对抗验收引用；P0 项若不改，task-224 应把对应章列为"卡面缺口"而不是实现 bug。
