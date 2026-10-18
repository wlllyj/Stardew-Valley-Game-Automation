# 0.7.39 批次对抗验收（task-224）— 报告骨架

> 状态：**骨架（并行准备）**。task-218/222/219/220 与 task-228（advance_dialogue）尚未全部交付，本文只含验收框架、探针用法与占位；
> 正式判定必须在 **`git archive` 冻结树**上跑完 A/B/C/D 四段后落笔（工作树含 dev-coder 在制改动，只作线索）。
> 探针：`scratch/_t224_probe.py`；变异矩阵：`scratch/_t224_mutate.py`。

## §0 一句话结论（待填）

待填：`PASS / PASS-WITH-NITS（无必修）/ FAIL` + 「0.7.39 是否可以据此冻结」+ 必修项最小反例。

> **D 段必写句（Lead m09338）**：advance_dialogue 的选项红线：**未替游戏做过任何选择**（附测试/变异证据：
> `D228-1/3/4b` 探针读数 + `m228a/m228b/m228f` 变异实测杀数）。

## §1 验收对象与滚动进度

| 卡 | 内容 | 提交 | 状态 | 验收要点 |
|---|---|---|---|---|
| task-218 | 树纳入清障 + 护栏 A/B + 片地优先/体力预算/桩与圆木 backlog | 待交付 | ⏳ | P0-1 逐格证据、P0-2 六层矩阵/注册表/announce、§9.1–9.3 |
| task-222 | `debug_dump` 1.6 强类型表 + `knownCraftingRecipes` 三态 | 待交付 | ⏳ | FarmView 障碍计数（P0-1 备选）、泛型反射 fail-closed、C# ≥4 断言 |
| task-223 | Furnace 配方定案（若需 Mod 入口再立卡） | 待结果 | ⏳ | 冒烟第 1 步 `debug_dump table=crafting_recipes key=Furnace` 不得 `unknown_skill` |
| task-219 | 意图-执行对账闭环（`intent_plan`/`intent_execution`/`day_end.intent_coverage`/gaps） | 待交付 | ⏳ | P0-3 原因码/单位/证据 schema/ACTIONLESS、P0-4 gaps 分层 |
| task-220 | analyzer 收 `intent_coverage`/gaps 并判红 | 待交付 | ⏳ | P0-5 工具分工（§8 只由 analyzer 判红、verify-run3 只 info） |
| task-228 | `advance_dialogue` 事件对话推进 + pause 重试语义 | 待交付 | ⏳ | **D 段**：选项红线（is_question/professions 拒绝）、有界性（单事件 ≤40 / 每天 ≤60）、pause 语义、政策不冲突 |

零回归口径：全量单测 0 红 + 账本矩阵 rc 不变 + **0.7.39 不动 L0–L5**；旧账本缺字段 ⇒【无法判定】；缺失 ≠ 通过。

## §2 P0 对账表（冻结树实测，待填）

| P0 | 要求（摘要） | 探针用例 | 冻结树读数 | 判定 |
|---|---|---|---|---|
| P0-1 | 护栏 B 逐格判据：`StepResult.after` 带 before/after kind 或 `cleared_tiles`；`tree→stump`=progress 不算红；farm 聚合只 info | `p01_after_kind_schema` / `p01_guard_b_fields` / `p01_farmview_counts` | 待填 | 待填 |
| P0-2 | 护栏 A 端到端 6 层 + `SKIP_KINDS ⊆ DEFERRED_KINDS` + 白名单快照 `{fruitTree,bush}` + 漂移测试 + tiles 缺失 announce | `p02_registry_invariants` / `p02_six_layers` / `p02_drift_and_announce` | 待填 | 待填 |
| P0-3 | 12 码闭合集 + `no_target` 证据 schema + 瓦片不变式 + `intent_id` 跨日唯一 + ACTIONLESS 白名单 | `p03_*`（5 个） | 待填 | 待填 |
| P0-4 | gaps：per-run + schema + 原子写 + 坏文件归档 + 写失败判问题 + 禁止转 lessons + 跨 run 聚合在工具侧 | `p04_gaps_layering` | 待填 | 待填 |
| P0-5 | §8 由 analyzer 判红、verify-run3 只 info、能力缺口不进 checks/_leftover | `p05_tool_division` | 待填 | 待填 |
| D-228 | advance_dialogue：选项红线（is_question/professions 最先拒）/ 有界性（maxSteps **1..10、默认 1**（Lead m21195 批准口径，探针期望已按此更新）、脑侧单次 ≤10、每天 ≤60）/ pause 语义（同一处 ≤3 次点击、间隔 ≥3s、连续 2 次 stalled 才放弃）/ 政策不冲突（event_blocked 保留、JUSTIFIED/checks 不加 advance） | `p228_option_redline` / `p228_bounds` / `p228_pause_semantics` / `p228_policy_no_conflict` | 待填 | 待填 |

**骨架自测读数（2026-10-18，非正式）**：
- 工作树（线索）：`PASS=2 FAIL=0 SKIP=13`（未交付项全部 SKIP，符合"没测到不算通过"）。
- `scratch/_t238`（0.7.38 冻结树）：`PASS=2 FAIL=0 SKIP=13`。
- `T224_ASSUME=218,219,220` 强制放开门槛（验证断言"是活的"）：`PASS=22 FAIL=2 SKIP=8`，无 traceback；
  两条红（`P0-2-7` 漂移测试缺失、`P0-5-1` analyzer 未收 `intent_coverage`）正是交付前的预期缺口。
- **D 段（task-228，2026-10-18 追加）**：worktree 线索模式 `T224_ONLY=D-228` ⇒ **PASS=19 FAIL=0 SKIP=0**；
  变异锚点 `--card 228 --check-anchors` ⇒ **7 处、坏 0**。注：228 的 Mod+脑侧已在工作树落地，
  正式读数仍以 `git archive` 冻结树为准；D 段 7 条变异自报杀数待 dev-coder 给（暂记 `?`）。
- **口径修正（Lead m21195）**：`advance_dialogue.maxSteps` 卡面定为 **1..10、默认 1**（脑侧每轮传 10、每天 60 额度由脑侧管）；
  探针 `D228-6/7/8` 期望已按批准口径更新（「按 Lead m21195 批准口径更新期望」）。
- **P0 组工作树线索红（非 D 段引入）**：219/220 陆续落地后出现 9 条红（P0-3 原因码集合/映射表/`stage_tiles_empty`、
  P0-4 坏文件归档/失败 journal/不转 lessons），属"交付在制 vs patches 预期"的差异，**正式验收在冻结树上逐条判**（不得当通过）。

## §3 A 段读数模板（冻结树，待填）

- HEAD / 冻结提交：待填
- `git show --stat` 四卡逐卡 numstat 与卡面 writeScopes 对照：待填
- 越界扫描（`^mod/|^tools/|manifest.json|bridge.py|^logs/|00-开发日志`；本批允许 tools+tests 的 analyzer 卡）：待填
- SHA256 前 16（brain/agentfarm/{planner,farmwork,longrun}.py、mod/AgentFarm.Bridge/{Contracts,FarmScan,Skills,BridgeHost}.cs、tools/{analyze-longrun,verify-run3}.py、tests/{test_longrun,test_farmwork,test_planner}.py）：待填
- `py_compile -W error::SyntaxWarning`（`-W` 在 `-m` 之前）：待填
- 定向 `tests.test_farmwork tests.test_longrun tests.test_planner`：待填
- 全量 `discover -s tests`：待填
- `dotnet build --no-incremental`：待填（0 警 0 错）
- C# 自检断言数：待填
- 版本：manifest 与 `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED` 是否同为 0.7.39：待填

## §4 B 段 FAIL→PASS（pre/post 冻结树，待填）

用 `git archive <卡提交>^` 与 `<卡提交>` 各建冻结树（`scratch/_t224_pre_<card>` / `_t224_post_<card>`，照 `_t200_trees.py` 先例，含夹具日志拷贝），
跑探针取 pre FAIL / post PASS 原文。逐卡三列：卡面要求 → pre 原文 → post 原文。

- task-218：待填（预期 pre：tree 被静默跳过 / `_stage_tiles` 空 / announce 缺失；post：tree 进目标池、after kind 可达、announce 生效）
- task-222：待填（预期 pre：`trigger_actions` 无泛型反射 / 观测无 `knownCraftingRecipes` 三态）
- task-219：待填（pre：无 intent_coverage；post：plan/execution/coverage+gaps 齐）
- task-220：待填（pre：analyzer 不判 §8；post：判红且 verify-run3 仍 info）
- task-228（D 段）：待填（pre：无 `advance_dialogue` 技能/脑侧；post：`is_question` 拒绝、`max_steps_reached` 有界、pause 重试不误报 stalled、`event_blocked` 仍诚实收尾）

## §5 变异矩阵（自报 vs 实测，待填）

用法：
```
$env:PYTHONUTF8="1"
python scratch/_t224_mutate.py --base scratch/_t224_frozen --check-anchors
python scratch/_t224_mutate.py --base scratch/_t224_frozen --all
python scratch/_t224_mutate.py --self-test      # 机械件自测（已通过）
```

待填表：`case | 卡 | kind | 自报杀数 | 实测杀数 | 判定`；不符必须点名（task-180 教训）。
骨架已列 19 条待登记变异（`TEMPLATES`：218/219/220 十条 + 228 九条）；**D 段七条已 `reg()` 登记**
（`m228a_no_is_question_guard` / `m228b_no_professions_guard` / `m228c_no_maxsteps_clamp` /
`m228d_no_retry_after_no_change` / `m228e_no_retry_gap` / `m228f_precheck_bypassed` / `m228g_stalled_immediately`），
自报杀数暂记 `?`（dev-coder 交付时补），验收时按冻结树 `--check-anchors` 重校后跑 `--all`。

## §6 工具分工与零回归（待填）

- `tools/analyze-longrun.py`：§8 判红主体（`intent_coverage` 七条判红）；待填实测。
- `tools/verify-run3.py`：对 §8 **只 info**、不新增 day_end 白名单字段、能力缺口不进 checks/_leftover；待填实测。
- 账本矩阵 rc 不变；L0–L5 不动；旧账本【无法判定】；缺失 ≠ 通过；待填。

## §7 最小冒烟 7 步核对表（真机，Lead 执行；我核证据）

| # | 步骤 | 证据 | 结论 |
|---|---|---|---|
| 1 | `debug_dump table=crafting_recipes key=Furnace` 不得 `unknown_skill` 且 matchedCount≥1 | 待填 | 待填 |
| 2 | `debug_dump table=trigger_actions` 能读（否则本批 smoke 判红回炉） | 待填 | 待填 |
| 3 | 单技能砍树 tree→stump（或消失）且 `StepResult.after` 带 before/after kind | 待填 | 待填 |
| 4 | 跑 1 个游戏日 ⇒ `day_end.intent_coverage` 出现、`<journal>-gaps.json` 生成 | 待填 | 待填 |
| 5 | 该日 `clear_area` 每个 ok 步都有 `cleared_tiles`/kind 变化 | 待填 | 待填 |
| 6 | 跨日落盘六串 6/6 配对 | 待填 | 待填 |
| 7 | `analyze-longrun --days 1` §8 无「executed_steps==0 且无原因码」；`verify-run3` 对 §8 只 info | 待填 | 待填 |

## §8 复跑命令与边界

```
# 探针（只读；T224_ROOT 切树；T224_ASSUME 仅用于验证断言活性）
$env:PYTHONUTF8="1"
$env:T224_ROOT="$PWD\scratch\_t224_frozen"; python scratch\_t224_probe.py
$env:T224_ONLY="P0-3"; python scratch\_t224_probe.py
```

边界：我只写 `docs/` + `scratch/`；不碰生产码/游戏/桥/板面；不 bump/不装机/不跑真机；正式验收只用 `git archive` 冻结树。
