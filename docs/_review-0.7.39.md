# 0.7.39 批次对抗验收（task-224）— 终稿

> 验收对象：**`git archive cea9c0f` 冻结树**（0.7.39 冻结提交；工作树含在制改动，只作线索、不作判定）。
> 探针：`scratch/_t224_probe.py`；变异矩阵：`scratch/_t224_mutate.py`；B 段建树：`scratch/_t224_trees.py`；
> 逐卡对照：`scratch/_t224_transitions.py`；伪造账本：`scratch/_t224_forge.py`。
> 原始读数：`scratch/_t224_frozen_{probe,targeted,full,build,cstest}.txt`、`scratch/_t224_{pre,post}{218,219,220,228}_probe.txt`、
> `scratch/_t224_author_t{218,219,228,230}_mutate.txt`、`scratch/_t224_mutd.txt`。

## §0 一句话结论

**PASS-WITH-NITS（无阻塞必修项）⇒ 0.7.39 可以据此放行 A″/B″。**
四条主通道（护栏 A 不静默缩水、护栏 B 逐格证据、§8 意图-执行对账/能力缺口、advance_dialogue 选项红线）在冻结树上全部有实测证据；
发现 1 个 GAP（task-228 作者变异脚本在冻结树不可复跑）与 5 条 NIT（详见 §9），均不阻塞。

> **D 段必写句（Lead m09338）**：advance_dialogue 的选项红线：**未替游戏做过任何选择** ——
> 证据：`D228-3`（规则/技能内 `answerDialogue`/`answerDialogueAction`/`selectOption`/`chooseProfession` 等
> 六类"替玩家应答"API 命中数 = **0**）、`D228-1`（Precheck 顺序 `is_question`(3879) → `professions`(3932) →
> `no_dialogue`(4001) → `not_running`(4056)，提问/职业选择最先拒）、`D228-16`（脑侧 `not has_dialogue or is_question`
> 入口 fail-closed）、`D228-4b`（Precheck 调用未被 `if(false)` 绕过）；变异 `m228a_no_is_question_guard`、
> `m228b_no_professions_guard`、`m228f_precheck_bypassed` **全部被杀**（1 红/条）。

## §1 验收对象、范围与台账

- 冻结提交：**`cea9c0f`**；验收时仓库 HEAD `520e64b`（docs-only：0.7.39 冻结装机记录 + 开发日志条目 079），
  `git diff cea9c0f HEAD -- brain mod tests` **为空** ⇒ 冻结树代码 = 当前代码。
- 工作树现状（验收时）：只有我的 `docs/_review-0.7.39.md` 与新增 `scratch/_t224_*.py`（外加 machine-runner 在制的
  `scratch/smoke-0739.py`，不属我）；生产码在 0.7.39 冻结后未再改。
- 版本：`mod/AgentFarm.Bridge/manifest.json` = **0.7.39**；`brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.39"`（冻结提交里唯一改这两处的提交，diff 只换版本号与注释）。
- 本批被验卡（提交 → 内容）：

| 卡 | 提交 | 文件数/行数（`--numstat` 合计） | 卡面范围 |
|---|---|---|---|
| task-218 | `b679f4e` | 9 文件 +887/−64（brain 3 + tests 3 + scratch 3） | 树清障 + 护栏 A/B |
| task-219 | `fc147a7` | 5 文件 +950/−22（brain 2 + tests 2 + scratch 1） | 意图-执行对账 + gaps |
| task-220 | `19b2827`（+`fac6a29`） | 3 文件 +767/−3（analyzer + tests + docs） | analyzer 收 §8 并判红 |
| task-222 | `7f030c2` | 7 文件 +399/−66（Mod 4 + Tests + brain + tests） | debug_dump 强类型表 + 已知配方三态 |
| task-228 | `3dc4b1e` | 13 文件 +1204/−9（Mod 3 + Tests 2 + brain 2 + docs 1 + SkillCatalog/Skills + test） | advance_dialogue |
| task-230 | `1e96509` | 8 文件 +538/−31 | P0 收口（FarmView 计数 / 原因码单一源 / gaps 可判红） |
| task-231 | `aec536c` | 3 文件 +311/−39 | analyzer gaps 读写失败红 + no_target 证据包 |

- 越界扫描（`logs/`、`mod/AgentFarm.Bridge/manifest.json`、`docs/00-开发日志.md`）：**七张卡本身 0 命中**；
  批次范围内这两处只有**冻结提交 `cea9c0f`** 自己改（`manifest.json` + `bridge.py` 版本行）⇒ 符合"版本号只由冻结提交改"。
  `brain/agentfarm/bridge.py` 仅 task-228 碰（`advance_dialogue` 薄包装 +33 行，**不改** `MOD_VERSION_EXPECTED`）。
- SHA256 前 16（冻结树）：`longrun.py B98BCBC6A0DCAFD1`(535469B)、`farmwork.py BEB8E1A63A437B10`(211847B)、
  `planner.py A6033FB8C3CCD2A5`、`bridge.py A298F135A9C339CE`、`Contracts.cs B77806AD2784B2ED`、`FarmScan.cs AE4260A0D9E5B12F`、
  `Skills.cs FF17423836CC634B`、`BridgeHost.cs 38A06B800DC11142`、`DialogueAdvanceRules.cs DE37F6A42DBAA67A`、
  `DialogueAdvanceSkill.cs 6CF71B71A0C1A500`、`DebugDumpSkill.cs FF74DEB0A4724B28`、`DumpRules.cs 6BA1DDC72DBA8694`、
  `SkillCatalog.cs 0BBD7668E83A32CD`、`analyze-longrun.py 1A3CCAA08B0914C2`(505008B)、`verify-run3.py 3F37B576AB42E1F9`、
  `test_longrun.py 50CDBEB5121CBD50`(608425B)、`test_farmwork.py 4173106B613609DC`、`test_planner.py 79D9DF56071B371A`、
  `test_analyze_longrun.py FDBA8BE14A2211F7`。与 Lead 给的五文件指纹（longrun/farmwork/bridge/dll/manifest）**前四个逐字一致**；
  `manifest` 归档 CRLF 版为 `C8EA3C51…1D47A6`（62651B），Lead 的 LF 版 `9CA523EF…`（62661B）—— **仅行尾差异**（装机目录文件＝Lead 版）。
- `py_compile -W error::SyntaxWarning`（`-W` 在 `-m` 前）：**rc=0**。
- 定向 `tests.test_farmwork tests.test_longrun tests.test_planner`：**Ran 689 / OK**。
- 全量 `python -m unittest discover -s tests`（`PYTHONUTF8=1`）：**Ran 1153 / OK**（与 Lead 一致）。
- `dotnet build --no-incremental`：**0 警 0 错**；C# 自检：**`OK 85 断言全部通过`**、`FAIL` 行 0。
- 探针（冻结树）：**PASS=67 / FAIL=0 / SKIP=0**（`scratch/_t224_frozen_probe.txt`）。

## §2 A 段：护栏与结构（逐项，冻结树实测）

| 项 | 检查 | 读数 |
|---|---|---|
| 护栏 B 逐格证据 | `P0-1a-1/2/3` | `StepResult.after` 为 dict 且带 `kind_before/kind_after`；`tree→stump` 记 progress（`ok=True code=ok`）不算硬失败 |
| 阶段账本 | `P0-1b-1/2` | 阶段记录带 `cleared_tiles`；`blocker_drop` 允许 **null**（观测无 farm 聚合时缺失 ⇒ null，不当 0） |
| FarmView 计数 | `P0-1c-1/2` | 五类障碍计数齐（weeds/stones/twigs/trees/clumps）；`Never` 三态可辨（缺失/null/0） |
| 护栏 A 注册表 | `P0-2-1..5` | 并集无重复归类冲突；`DEFERRED_KINDS = {fruitTree, bush}` 快照锁定；两条登记都带"缺什么能力/理由" |
| 护栏 A 六层矩阵 | `P0-2-6`（13 kind） | 逐 kind 走 `Brief.blockers → _plot_brief → _stage_tiles → clear() → _plot_has_work → _apply_policy`：tree/weed/twig/stone 六层可达；bush/fruitTree 六层**均被 defer 且带理由**；clump 族不入 clear_area（走 backlog 路线） |
| 漂移/公告 | `P0-2-7/8` | `DEFERRED_KINDS` 漂移测试存在（`tests/test_planner.py`）；tiles 缺失时 deferred kind 仍被公告（fail-closed 文案含"暂不支持"） |
| 树是真目标 | `P0-2-6 [tree]` | `stage_tiles=1`、`clear_ok=True/ok`、`plot_has_work=True`、`kept=['clear_area']`；日预算 `TREE_CLEAR_MAX_PER_DAY=2`、体力闸门 `TREE_STAMINA_ESTIMATE=100`（`longrun.py:3254-3266`）、多刀 `MAX_TREE_SWINGS=16`（`farmwork.py:129/2062`） |
| 护栏 B 判红落点 | 代码 | `longrun.py:6188-6230`：`clear_area` 有 ok 步却**一格 kind 都没变**且无"判不了"步、无预算/工具借口 ⇒ `stopped="incomplete"` + journal `stage_stop_named`（"挥过刀"不算清障有效；不依赖观测里不存在的 `farm.blockers`）⇒ 该阶段进 `assigned_undone` ⇒ 当天不可能 VERIFIED |

## §3 B 段：逐卡 FAIL→PASS（pre 树 = 该卡父提交；post 树 = 该卡提交；**验收口径 = 冻结树**）

| 卡 | pre 树探针合计 P/F/S | 该卡组检查数（冻结树） | 该组「pre 非 PASS → 冻结树 PASS」 | 冻结树该组非 PASS |
|---|---|---|---|---|
| 218（`09425a2`） | 20/17/11 | 15 | **10 条**：P0-1a-1/2/3、P0-1c-1/2、P0-2-3/4/5/7/8 | 无 |
| 219（`7f030c2`） | 29/11/10 | 19 | **19 条**（P0-3 全部 13 + P0-4 全部 6） | 无 |
| 220（`fc147a7`） | 38/19/5 | 3 | **1 条**：P0-5-1（P0-5-2/3 在 219 落地时已成立） | 无 |
| 228（`fac6a29`） | 41/16/5 | 19 | **15 条**：D228-1/2/4/4b/5/6/7/8/9/10/11/12/16/17/18 | 无 |

- 关键 pre 原文（摘）：pre218 `P0-2-3 SKIP_KINDS=['bush','clump','fruitTree','object','tree'] ⊆? DEFERRED_KINDS`（tree 被静默跳过 ⇒ 落红）、
  `P0-2-4 实际=[]`（无白名单快照）、`P0-2-6 [tree] stage_tiles=0 clear_ok=False/skipped`；pre219 无 `intent_coverage` 相关实现
  （P0-3/P0-4 全部 SKIP/FAIL）；pre220 `P0-5-1 analyzer 不读 day_end.intent_coverage`；pre228 `D228-1 idx is_question=-1 …`（技能不存在）。
- 中间树（218/219/220 独立 post）仍有红，**全部是"依赖卡未落地"的断言**（例：P0-3-1 的十二码要 task-230 补 `failed`；
  P0-2-7 漂移测试要 230 的 `tests/test_planner.py`；P0-3-4 映射表 `STEP_CODE_TO_REASON` 要 230）——**冻结树 67/0/0 收口**。
  这正是"按卡建树、按冻结树判"的原因，不把中间树的红当回归。
- 代码锚点（护栏 A）：`brain/agentfarm/planner.py:1405 DEFERRED_KINDS`（带理由）、`:1528-1579` 简报"存在但暂不支持清理（原因）"公告、
  `:1790-1792` 按 obs 现算 deferred；`farmwork.py:110-118` 注释断言 `set(SKIP_KINDS) <= set(planner.DEFERRED_KINDS)`、
  **绝不静默跳过**、果树不进障碍计数；`tests/test_analyze_longrun.py:4563-4567` 两侧 `DEFERRED_KINDS` 一字不差漂移测试；
  `tests/test_longrun.py:10541 assertNotIn("fruitTree", CLEARABLE_KINDS)`。

## §4 C 段：六条作弊/回归通道（要么证伪，要么给"为什么不可能"）

| 通道 | 结论 | 证据 |
|---|---|---|
| A1 登记进 `DEFERRED_KINDS` 就"永远绿"/静默缩水 | **不可能（结构性挡死）** | 白名单快照锁 `{fruitTree,bush}` + 漂移测试 + 六层矩阵（bush/fruitTree 每层都带理由、tree 每层可达）；新增 kind 必须显式改快照（`P0-2-4/7`） |
| A2 `clear_area` 有 ok 步但 blockers 未降能否洗过 | **不能（脑侧判红链路）** | `longrun.py:6188-6230`：逐格 `kind` 无变化 ⇒ `stopped=incomplete` + `stage_stop_named`（journal 原文"挥过刀不算清障有效"）⇒ `assigned_undone>0` ⇒ 当天 `no_unmet_stages=False`；`blocker_drop` 只 info（真机 smoke 里为 None，未当 0） |
| A3 窗口内树不进目标池/无限空挥 | **不会** | `P0-2-6 [tree]`：`stage_tiles=1`、`clear_ok=True`；日预算/体力闸门 `longrun.py:3266`；多刀上限 `farmwork.py:2062`；smoke 账本 `water_far_open=6`（开路砍树）与 `clear_area cleared_tiles=[[58,24]]` |
| B1 "意图缩小/不执行"逃过对账 | **挡死** | 计划过就必有一条对账：`_finish_intent_coverage`（`longrun.py:1503-1524`）对未执行的补 `superseded`/`gated`；12 码闭合集 `longrun.py:106`、映射唯一数据源 `:121`、集外判 False `:148-166`、`no_target` 必须带 `stage_tiles_empty` 证据否则降级 `unknown_evidence`（`tests/test_longrun.py:10853/11005`） |
| B1 伪造"执行了但没原因" | **判红（我亲跑伪造账本）** | `_t224_forged_b2.jsonl`（executed_steps=0、reasons={}）⇒ analyzer **rc=1**、含 `missed:intent_no_reason:harvest`；负例 `_t224_forged_b2_reasons.jsonl`（reasons={budget_deferred:1}）⇒ 不报 no_reason 但报 `missed:intent_bad_reason:harvest`（集外码一律红）—— 反例矩阵见 §8 |
| B2 生成器缺陷：`executed_steps==0` 无原因码 | **判红** | 同上（analyzer `tools/analyze-longrun.py:1369-1521 cat_intent`，共 8 类红：no_execution / no_reason / bad_reason / gap_missing / gap_kind_not_deferred / tiles_invariant / reason_count / no_target_evidence） |
| B3 gaps 写失败/读坏被吞 | **brain 侧可判红 + 工具读失败只告警（口径已写清）** | brain：`load_gaps_file` 坏文件归档 `<name>.bad.<ts>`、`_gaps_load` journal `gaps_load_failed` + `rep.gaps_problem`（`longrun.py:1392-1410`）、写失败 `gaps_write_failed`（`tests/test_longrun.py:11091/11096-11111`）；analyzer：`tests/test_analyze_longrun.py:4766 test_gaps_load_failed_event_is_red`；**工具自己读到坏 gaps 文件只告警**（我实测 `读坏 read_failed:JSONDecodeError`，不产红）⇒ P0-4.5 的判红责任落 brain 事件 + `day_end.gaps_problem`（报告口径见 §9 NIT-3） |
| C1 `debug_dump` 新表坏数据拖垮旧表 | **不会** | 每表 fail-closed（`table_unknown`/`load_failed`）；C# 断言 `t222_dictionary_entries_sorted` / `t222_list_entries_use_index_keys` / `t222_shape_label_reports_container` / `t222_null_asset_and_unknown_object_are_safe`（`Tests/Program.cs:354/360/365/371`，≥4 条符合卡面）；`knownCraftingRecipes` 三态 `Contracts.cs:223/228` + `tests/test_farmwork.py:3272-3274` |
| C2 新技能/表把旧枚举挤掉 | **结构性挡死** | `SkillCatalog.cs` 单一数据源；`Tests/Program.cs:484-507` 断言 Executable/Planned/LongTask 无重复、计数闭合、`IsKnown`/`IsLongTask` 白名单（覆盖 `debug_dump`/`add_missed_recipes`/`upgrade_tool`/`pickup_tool`/`craft_item`/`place_object`/`machine`） |

## §5 工具分工与零回归（§8 判红责任）

- `tools/analyze-longrun.py`：**§8 判红主体**（`cat_intent` 八类红）；冻结树上 `test_analyze_longrun` 全绿（`Ran 1153` 内含）。
- `tools/verify-run3.py`：源码里**没有** `intent_coverage`/`gaps_problem` 字样（`grep` 0 命中）⇒ 对 §8 完全不动（比"只 info"更严：不新增 day_end 白名单字段，自然不可能误判）。
- 能力缺口（`deferred_capability`）不进 `checks`/`_leftover`；`DEFERRED_KINDS` 只影响目标池与公告（`P0-5-3`）。
- 账本矩阵 rc：本批不改 verify-run3，历史账本判决不变；L0–L5 未动。

## §6 变异矩阵（自报 vs 实测；作者脚本在冻结树上复跑）

| 卡 | 作者自报 | 我的实测（冻结树） | 判定 |
|---|---|---|---|
| 218 | 2/1/1/1/4/2/1（合计 12） | **2/1/1/1/4/2/1（合计 12）**，基线 0 红 | ✅ 逐字一致 |
| 219 | 1/2/1/1/1/1（合计 7） | **1/2/1/1/1/1（合计 7）**，基线 0 红 | ✅ 一致 |
| 230 | 实测杀 9 | **2/1/1/3/1/1（合计 9）**，基线 0 红 | ✅ 一致 |
| 228 | m228a/b/c/d 杀 2/3/1/1 | **脚本不可复跑**：`AssertionError: 变异锚点找不到：m228a_questions_are_advanced` ⇒ **GAP-1（自报无法核实）** | ⚠️ GAP |
| 228（我的自建 7 条） | 无自报 | `m228a_no_is_question_guard` 1 / `m228b_no_professions_guard` 1 / `m228c_no_maxsteps_clamp` 1 / `m228d_no_retry_after_no_change` 1 / `m228e_no_retry_gap` 1 / `m228f_precheck_bypassed` 1 / `m228g_stalled_immediately` 2 ⇒ **7/7 全杀** | ✅ 覆盖选项红线与 pause 语义 |
| 220/222/231 | 未给变异矩阵（卡面未要求） | 行为证据走 §4 C1/B1/B2 与 C# 85 断言 | 记录为 GAP-2（自报缺失） |

留档：`scratch/_t224_author_t{218,219,228,230}_mutate.txt`、`scratch/_t224_mutd.txt`；锚点校验 `--card 228 --check-anchors --base <冻结树>` = **7 处 0 坏**。

## §7 最小冒烟 7 步：我核到的证据（真机执行者是 machine-runner）

`logs/longrun-smoke-0739.jsonl`（185 行、3 个 `day_start`、2 个 `day_end`、无 `finish`）＋ `logs/longrun-smoke-0739-gaps.json`（1126B）：

| # | 步骤 | 证据 | 结论 |
|---|---|---|---|
| 1 | `debug_dump table=crafting_recipes key=Furnace` 不得 `unknown_skill` | 本账本不含该步（属 tools/console 侧）；C# 85 断言含 dump 表契约 | 【本账本无法判定】 |
| 2 | `debug_dump table=trigger_actions` 能读 | 同上 | 【本账本无法判定】 |
| 3 | 砍树 tree→stump/消失且 `after` 带 before/after kind | 账本含 `clear_area` 阶段 `cleared_tiles=[[58,24]]`、`water_far_open=6`（开路真砍） | ✅（逐格证据齐；`blocker_drop=None` 属未观测） |
| 4 | 跑 1 个游戏日 ⇒ `intent_coverage` 出现 + `-gaps.json` 生成 | `day_end.intent_coverage` 8/17 条；`logs/longrun-smoke-0739-gaps.json` 存在 | ✅ |
| 5 | `clear_area` 每个 ok 步都有 `cleared_tiles`/kind 变化 | 见第 3 行；`P0-1b-1/2` 探针同口径 | ✅ |
| 6 | 跨日落盘六串 6/6 配对 | 本次 smoke 只有 2 天且**均以 `inventory_blocked` 收尾**（背包满：`harvest` 每天 12 次 `no_slot`），跨日 SMAPI 六串证据不在本账本 | 【无法判定·本跑未覆盖】 |
| 7 | analyzer 无「executed_steps==0 且无原因码」；verify-run3 对 §8 只 info | 本账本 coverage 记录均带原因码或真执行（`no_slot:12`/`no_target:1`/`gated:1`）；verify-run3 源码无 §8 字样 | ✅ |

> 备注：本账本两天都 `ended_by=inventory_blocked`、`verified=False`、`harvest` 每天 12 次 `no_slot` ——
> 正是 task-198 卡面要消灭的"满包洗白"形态，本跑**如实不 VERIFIED**，且 `intent_coverage` 把 `no_slot` 记成原因码而非静默缩水 ⇒
> A′ 的"满包阻塞日不许假绿"在 0.7.39 上仍然成立。

## §8 复跑命令

```powershell
$env:PYTHONUTF8="1"
# 冻结树（若 scratch 里没有；用 ASCII 临时目录建 tar，避免中文路径）
python scratch/_t224_trees.py 218 219 220 228      # 建 pre/post 树（含夹具）
python scratch/_t224_transitions.py               # 逐卡 pre→冻结树 对照表
# 探针（只读；T224_ROOT 切树）
$env:T224_ROOT="$env:TEMP\t224_frozen"; python scratch\_t224_probe.py
# 变异（两列）
python scratch/_t224_mutate.py --base "$env:TEMP\t224_frozen" --check-anchors
python scratch/_t224_mutate.py --base "$env:TEMP\t224_frozen" --all
# 伪造账本（B2/B3）
python scratch/_t224_forge.py
python "$env:TEMP\t224_frozen\tools\analyze-longrun.py" --journal scratch/_t224_forged_b2.jsonl --days 1 --window 1
```

## §9 NIT / GAP 清单（每条注明是否阻塞放行）

| # | 类别 | 内容 | 阻塞？ |
|---|---|---|---|
| GAP-1 | 自报不可复跑 | task-228 作者 `scratch/_t228_mutate.py` 在冻结树锚点失配（`m228a_questions_are_advanced` 找不到）；自报 2/3/1/1 无法核实。我用 7 条自建变异覆盖（全杀） | 否（建议 0.7.40 要求作者脚本锚点用稳定注释/行内标记） |
| GAP-2 | 自报缺失 | task-220/222/231 卡面未要求变异矩阵，作者也未给；其行为证据由 §4 伪造账本实验 + C# 85 断言承担 | 否 |
| NIT-1 | 断言脆弱 | `D228-16` 是**文本形状**断言（要求 `if not has_dialogue or is_question` 单行存在）：228 独立树不满足、冻结树满足——**task-230 把两行拆开刻意迎合探针**（`longrun.py:6845` 注释自证）。功能等价守卫在 228 已存在，无产品缺陷；建议后续改为行为断言 | 否 |
| NIT-2 | 观测面 | `blocker_drop` 在真机 smoke 恒 `None`（观测无 `farm.blockers` 聚合）⇒ 护栏 B 实际只走逐格判据；与卡面 P0-1"farm 聚合只 info"一致，但"farm 级下降"这类信息短期拿不到 | 否 |
| NIT-3 | 口径 | analyzer 自己读到坏 `-gaps.json` **只告警不判红**（我实测 `read_failed:JSONDecodeError` 只进统计）；P0-4.5 的可判红责任在 brain 的 `gaps_load_failed`/`gaps_write_failed` 事件与 `day_end.gaps_problem`。报告已写清，但工具输出可加一句"本账本无 brain 侧 gaps 事件 ⇒ 读写失败无法判定"（现在清单式列出，够用） | 否 |
| NIT-4 | 冒烟覆盖 | smoke 两天均满包 `inventory_blocked` 收尾、无 `finish`、无跨日六串证据 ⇒ §7 第 6 步【无法判定】；A″/B″ 正式跑必须补 | 否（正式跑批会覆盖） |
| NIT-5 | 探针门槛 | `T224_ASSUME` 只用于"断言活性"自测；中间树的 FAIL 数不代表回归（依赖卡未落地），报告已按"冻结树为准"呈现 | 否 |

## §10 边界

只写 `docs/` + `scratch/`；未改生产码/游戏/桥/板面；未 bump、未装机、未跑真机；所有正式读数来自 `git archive cea9c0f` 冻结树（§8 命令可复跑）。
