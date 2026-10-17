# 0.7.37 批次独立对抗验收（task-200）

- 验收人：deputy-lead（独立对抗验收：只读生产码，只写 `docs/` 与 `scratch/`；不碰游戏/桥/板面）
- 验收对象：**`git archive 063351d`（0.7.37 冻结提交）** 冻结树 `scratch/_t200_frozen`（661 文件 + 夹具 105）
- 批次卡（按 Lead m08802 的范围）：task-192 / 198 / 199 / 202 / 204 / 208 / 213
  - **task-205 跳过**（我已单独判定 FAIL：F3 升级自死锁；修法与复核归 task-216）
  - task-195 / 196 / 197 / 193 已移出本批 → 0.7.39（见 `docs/_release-0.7.37.md` §1 卡表）
- 纪律：在制工作树只作线索，判定一律在冻结树上做；变异矩阵亲自实测并给「自报 vs 实测」两列；
  「没测到」不写成「通过」；每条给证据出处（提交 / 行号 / 测试名 / 读数文件）。
- 探针与工具：`scratch/_t200_probe.py`（198/199 假世界通道 + A′ 原型复现）、
  `scratch/_t200_mutate.py`（变异矩阵 + 锚点校验 + 自报/实测两列）、`scratch/_t200_trees.py`（归档建树）。

## §1 A 段：范围与读数（冻结树 `063351d`）

- 版本：`manifest.json "Version": "0.7.37"`、`bridge.py MOD_VERSION_EXPECTED = "0.7.37"`（冻结提交 bump 生效）。
- `py_compile -W error::SyntaxWarning`（farmwork/longrun/planner/bridge）：**exit 0**
  （注意 `-W` 必须在 `-m` 之前，否则 `py_compile.py: error: unrecognized arguments: -W`）。
- 定向 `tests.test_farmwork tests.test_longrun tests.test_planner`：**Ran 610 / OK**
  （读数 `scratch/_t200_fz_targeted.txt`）。
- 全量 `PYTHONUTF8=1 python -m unittest discover -s tests`：**Ran 1035 / OK（0 红）**
  （读数 `scratch/_t200_fz_full.txt`；注意我早前在 `62e9089` 交付点测得 986/2 红 = analyzer 桶漂移，
  已由 task-202 `f2e72e3` 归零 ⇒ 冻结树上无红）。
- `dotnet build --no-incremental`：**0 警告 / 0 错误**；C# 自检实跑 **`OK 60 断言全部通过`**。
- 逐卡定位用定向复跑：`tests.test_longrun.TestTask192ScopeReleaseAccounting` + `TestTask199ReadyFar` +
  `tests.test_farmwork.TestTask199FarmReadyTiles` + `TestTask199ModContract` ⇒ **Ran 19 / OK**。
- A 段不变量：`day_end` 无新键、`checks` 仍 10 键、`JUSTIFIED_END_REASONS = ("night","stamina","no_work")` 未变。

## §2 task-192：释放认输区时同步扣减当天记账 —— **PASS**

- 提交 `1246cdd`（3 文件 +282/−9：`brain/agentfarm/longrun.py` +63/−8、`planner.py` +33/−1、`tests/test_longrun.py` +186）；
  越界扫描（`mod/`/`tools/`/`manifest.json`/`bridge.py`/`logs/`/`00-开发日志`）**零命中**。
- 代码锚点：`longrun.py:1257-1293 _release_zone` —— `held = shed_zone_tiles.pop(...)`；
  `tiles = len(held) or item["tiles"]`；`self.scope_shed_tiles_today = max(0, int(...) - int(tiles))`；
  `rep.scope_shed_tiles` 同步、`rep.scope_shed` 同区扣减/清空并记 `released_tiles`；
  journal `scope_released{zone,reason,tiles,live_crops_now,shed_tiles_remaining}`；
  **`shed_ever_tiles` 不清**（`:808` 定义、`:1392` 累加）⇒ 累计 34% 上界不被释放绕过。
- 测试锚点：`tests/test_longrun.py:9446 TestTask192ScopeReleaseAccounting`（6 条，含
  `test_partial_release_keeps_the_remainder`、`test_released_zone_still_counts_against_the_cumulative_cap`、
  `test_shed_ever_survives_release_and_restart`）⇒ 定向全绿。
- 变异（卡面未给数字 ⇒ **自报 GAP**，以下为我自建、base=冻结树）：`m192a_release_keeps_shed_accounting`
  （释放不扣当天记账）**杀 5**；`m192b_release_clears_cumulative`（释放时清 `shed_ever_tiles`）**杀 3**
  ⇒ 单测对这两条防线灵敏。
- 残余说明：工具侧「毛认输 − 释放 = 账本末态」的对账由 task-189/Lead 的 `3ccc29b` 提供，不在本卡；我未再写 192 专用假世界探针
  ⇒ 对抗强度中（证据链 = 代码锚点 + 6 单测 + 2 变异实测）。

## §3 task-198：背包满 = 全局阻塞（`no_slot`）+ 腾格收敛 + 诚实收尾 —— **PASS-WITH-NITS**

- 提交 `62e9089`（4 文件 +733/−18：`farmwork.py` +29/−5、`longrun.py` +291/−8、`test_farmwork.py` +61/−2、
  `test_longrun.py` +352/−3）；越界零命中。
- 冻结树 pre/post（假世界探针 `scratch/_t200_probe.py`，`T200_FORCE` 让 pre 照跑）：

| 树 | 来源 | marker | 读数 |
|---|---|---|---|
| `scratch/_t200_pre198` | `62e9089^` | `198=0/3` | **PASS=6 / FAIL=15 / SKIP=14** |
| `scratch/_t200_post198` | `62e9089` | `198=3/3` | **PASS=24 / FAIL=0 / SKIP=4** |

- pre 树原文（= 交付前缺陷）：`198a-1 code=failed status='' no_slot=None`；`198a-3 tile_attempts {}→{(61,11):1}`；
  `198a-4 harvest_gave_up=[(61,11)]`；`198b-1 failed_steps=4`、`stages=[('harvest',2,0),('harvest',2,0)]`、`no_hard_failures=False`；
  `198b-3/198f-2/198f-8` 收尾 = `stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：农场口径还有 1 格熟作物…）`；
  `198f-4` 假绿形态 `no_work:确实找不到可做的活（…）`。post 全部转绿。
- **A′ 原型复现通道**（Lead m08246 定的正式冻结判据）：照 `logs/longrun-runA3-0736.jsonl` day13 真实形态
  （满包 + 多格熟作物 + `(63,18)` 反复 no_slot）构造假世界 ⇒ post 树 8/8 绿：可腾 ⇒ `slot_relief.freed>=1`；
  腾不出 ⇒ `inventory_blocked` 收尾；低水位（1 空格 + 8 熟）⇒ 不再白撞；三形态**均不出现** `stuck:…守卫仍说还有活`，
  且 `failed_steps=0`、`verified=False`、不洗 VERIFIED。
- 变异（7 条作者变异，kind=全量套件，base=`_t200_post198`；**基线 2 红** analyzer 桶漂移）：

| 变异 | 自报 | 实测(毛/净) | 判定 |
|---|---|---|---|
| m198a 腾格回路失效 | 10 | 12 / **10** | 相符 |
| m198b `failed_any` 去 no_slot 过滤 | 4 | 6 / **4** | 相符 |
| m198c 守卫熟作物条件去 `and not bag_blocked` | 2 | 4 / **2** | 相符 |
| m198d `_count_attempts` no_slot 分支失效 | 1 | 3 / **1** | 相符 |
| m198e 低水位退回 `free_slots <= 0` | 2 | 4 / **2** | 相符 |
| m198f 守卫 `inventory_blocked` 分支失效 | 3 | 5 / **3** | 相符 |
| m198g `day_justified` 加 inventory_blocked | 1 | 3 / **1** | 相符 |

  我另加 2 条 probe 变异：`env_block` 摘除 ⇒ 1 杀；满包判定失效 ⇒ 2 杀 ⇒ A′ 通道非空转。
- NIT-1（不阻塞）：`inventory_blocked` 日 `stages[].env_block` 把同轮 `no_slot` 步数全累计（实测 21/24 步），
  语义易误读；`_leftover("harvest")` 仍非空、`no_unmet_stages=False`、`failed_steps=0` ⇒ **未洗白**（读数 `scratch/_t200_198_nit.txt`）。
- NIT-2（不阻塞）：`slot_relief` 与 `inventory_blocked` 语义区别只在 journal 层，analyzer 侧归因见 task-202/193。

## §4 task-199：`readyTiles` 与 `readyCrops` 同源 + 走不到不空转 —— **PASS-WITH-NITS**

- 提交 `edcd581`（9 文件 +794/−33：brain 2、mod 3、Tests 2、tests 2）；均在卡面 writeScopes 内。
- 假世界探针（`case_199`，26 条断言 + 源码/契约检查）：

| 树 | marker | 读数 |
|---|---|---|
| `scratch/_t200_pre199`（`2bcad88`，`T200_FORCE=1`） | `199=0/3` | **PASS=24 / FAIL=1 / SKIP=9**（唯一 FAIL = 接口齐备：缺 `farmwork.farm_ready_tiles` + longrun 五个 ready_far 方法） |
| `scratch/_t200_post199`（`edcd581`） | `199=3/3` | **PASS=45 / FAIL=0 / SKIP=3** |

- 通道实测（post）：读 `readyTiles` 并扣窗口内已见格；走过去收 ⇒ `ready_far` 带 `ready_before/ready_after` 且 `farm_actions_today` 增；
  走不到 ⇒ 2 次认输 + `ready_far_blocked` **恰 1 条** + 第 3 次不再开路 + 守卫改 `gave_up_ready`（不再被钉死）；
  截断 ⇒ 逐次 `ready_far{status:"truncated"}`，坐标空+截断 ⇒ `ready_far_truncated` 恰 1 条；缺字段 ⇒ `unavailable` + 老文案 fail-closed + sleep_guard keep_working。
- 变异（作者自报 m199a 6 / m199b 1 / m199c 1 / m199d 1；**`scratch/_t199_mutate.py` 不在库、提交说明无定义 ⇒ GAP-1**，
  以下为我按描述重建、base=`_t200_post199`）：

| 变异（我的重建） | 自报 | 实测 | 判定 |
|---|---|---|---|
| m199a 去掉 readyTiles 并集 | 6 | **5** | 不符 |
| m199b 去掉 fail-closed（`_ready_far_reason` unavailable 返 ""） | 1 | **0** | 不符 |
| m199b2 缺字段当成全认输 | 1 | **0** | 不符 |
| m199b3 旧 Mod 缺字段不 fail-closed（`farm_ready_tiles` 返 "ok"） | 1 | **2** | 不符 |
| m199c 认输格进守卫理由 | 1 | **1** | 相符 |
| m199d 每次尝试都记 blocked | 1 | **1** | 相符 |
| （我自建）无截断留痕 / 认输次数无界 | — | 1 / 2 | 通道灵敏 |

  由于作者未交脚本，**无法证明我的重建与作者原变异同址** ⇒ 4 条"不符"记为 GAP 而非缺陷。
- NIT-1（不阻塞）：卡面「同源一致（伪造不一致必须被拦）」目前只有**源码文本契约**（`TestTask199ModContract`：
  FarmScan 同一 `CropMeta.Ready` 分支 600 字符内双标记）+ 运行期各自读三态；我构造"`readyCrops>0` 但 `readyTiles=[]`"
  的伪造世界不被拦（后果是**有序收尾，不是假绿**）⇒ 契约层达标、运行期交叉校验缺失。
- NIT-2（不阻塞）：`tools/verify-run3.py`（冻结树）**0 处** `readyTiles`/`ready_far` ⇒ 工具侧无对账闸门，
  只有 analyzer 收 5 桶；建议后续（0.7.39+）工具侧加"账本自称全收 vs readyTiles 覆盖"的 info 级核对。

## §5 task-202：analyzer 收录背包阻塞三事件 —— **PASS-WITH-NITS**

- 提交 `f2e72e3`（4 文件 +359/−2：`tools/analyze-longrun.py` +140、`tests/test_analyze_longrun.py` +103、
  `docs/_analyze-longrun-caliber.md` +55/−2、`scratch/_t202_matrix.py` +61）；`tools/` 属本卡声明写盘范围。
- 效果实测：`62e9089` 的 2 红（`TestBagSpaceDeadlock` / `TestEventMappingDrift`）在冻结树归零 ⇒ 全量 **1035/OK**。
- 代码锚点：`tools/analyze-longrun.py:666-680` FIELD_PROBES 收 `slot_relief`/`slot_relief.freed`/`slot_relief_noted`/
  `inventory_blocked`/`inventory_blocked.free_slots`；`:952 "inventory_blocked": "inventory_blockeds"`（EVENT_BUCKETS）；
  `:948-949`、`:5068-5108` 两处注释与计数节写死语义红线"如实上限、非失败非豁免"。
- 变异（卡面未给数字 ⇒ 自报 GAP，自建，base=冻结树，kind=`tests.test_analyze_longrun`）：
  `m202a` 改 EVENT_BUCKETS **键** ⇒ **杀 3**；`m202b` 只改桶值名 ⇒ **杀 0**
  ⇒ 漂移测试只认键、不认桶值（覆盖边界，非缺陷；若要钉桶值需另加断言）。
- NIT（不阻塞）：`inventory_blocked` 当天自称 VERIFIED 的告警在 analyzer 侧已写（`:3087-3093`），
  但 `verify-run3` 无对应硬闸门；属 0.7.39 工具侧收口项。

## §6 task-204：铁匠铺升级链 IL 定案（docs-only）—— **PASS**

- 提交 `d6d55e2`（`docs/_il-tool-upgrade.md` +400/−241、`scratch/_api_up/Probe.cs` +35、`_t204_conv.py`、`_t204_grep.py`）；
  越界零命中。
- 冻结树实读：`docs/_il-tool-upgrade.md` 存在 **32772 B**，锚点逐条核对 ——
  `# 铁匠铺工具升级链：IL + 反射定案（task-204）`、`§0 结论速览`、`TryOpenShopMenu("ClintUpgrade","Clint",true) // IL_3062-3072`、
  `item.actionWhenPurchased("ClintUpgrade")`、`TryOpenShopMenu 本身没有任何 daysLeft/已有升级守卫 ⇒ 先读状态再开店`、
  价格/锭/`Clint_NoInventorySpace` 等；与 `docs/_release-0.7.37.md` §4 一致。
- 本卡为定案文档，残余实现工作在 task-205（已判 FAIL → task-216），本报告不再重复其缺陷。

## §7 task-208：`dismiss_modal` 显式应答（fail-closed）—— **PASS-WITH-NITS**

- 提交 `dadd356`（6 文件 +385/−17：`AnswerRules.cs` +180、`ModalDismiss.cs` +108/−2、`Skills.cs` +28/−17、
  `Contracts.cs` +27、Tests 2）；`mod/` 属声明范围。
- 代码锚点：`ModalDismiss.cs:108 Dismiss(int? answerIndex, string answerText)`、
  `:110 bool explicitChoice = answerIndex.HasValue || !string.IsNullOrWhiteSpace(answerText);`、
  `:239 DismissDialogueExplicit`、`AnswerRules.Pick`（`:269` 附近，返回 `StatusFound/NotFound/Ambiguous/NoQuestion/Auto`）。
- C# 自检锚点（`mod/AgentFarm.Bridge.Tests/Program.cs:145-176`）：`t208_index_hit`、`t208_text_hit_is_case_insensitive_substring`、
  `t208_missing_text_fails_closed`、`t208_ambiguous_text_fails_closed`、`t208_no_explicit_args_keeps_old_behavior`、
  `t208_index_and_text_are_mutually_exclusive`、`t208_no_options_is_no_question`（7 条纯规则断言）。
- 变异（卡面未给数字 ⇒ 自报 GAP，自建，base=冻结树）：
  - 规则层 `m208b_rule_index_hit_returns_999` ⇒ **杀 1**（`t208_index_hit`）⇒ 自检对规则层回归灵敏；
  - 入口层 `m208a_explicit_choice_disabled`（`explicitChoice=false`，退回自动挑）⇒ **杀 0**
    ⇒ **C# 自检只覆盖 `AnswerRules` 纯规则，不覆盖 `ModalDismiss.Dismiss` 入口分叉**（覆盖边界，NIT）。
- NIT（不阻塞）：入口层建议加 1 条单测/C# 断言（"显式参数 ⇒ 不退回 Yes"）；本卡卡面要求的
  "`no_question`/`choice_not_found`/`choice_ambiguous` fail-closed" 在规则层已被钉死。

## §8 task-213：Mod 内省面（`debug_dump` / `add_missed_recipes`）—— **PASS-WITH-NITS**

- 提交 `a0a0a4d`（9 文件 +1092/−1：`DebugDumpSkill.cs` +276、`DumpRules.cs` +257、`AddMissedRecipesSkill.cs` +185、
  `Contracts.cs` +96、`Skills.cs` +33/−1、Tests 2、`brain/agentfarm/bridge.py` +48、`tests/test_bridge_client.py` +33、
  `scratch/_t213_probe.py` +107）；`mod/`+brain+tests 属声明范围。
- 代码锚点：`DebugDumpSkill.cs:94 Fail("table_unknown")`、`:99 DumpRules.ClampLimit`、
  `:156 cap = Math.Min(matched.Count, Math.Min(limit, DumpRules.MatchMax))`、`:170 take = Math.Min(all.Count, limit)`；
  `DumpRules.cs:127-133 ClampLimit`（默认 200 / 上限 2000）；C# 自检 `Program.cs:265-291` `t213_table_normalization`/`t213_limit_clamped` 等。
- 变异（卡面未给数字 ⇒ 自报 GAP，自建，base=冻结树）：
  - 规则层 `m213c_rule_limit_ignored` ⇒ **杀 1**（`t213_limit_clamped`）；
  - 入口层 `m213a_dump_no_match_cap`、`m213b_dump_no_limit` ⇒ **各杀 0**
    ⇒ 与 208 同构的覆盖边界：自检只覆盖 `DumpRules` 纯规则，不覆盖 `DebugDumpSkill.Step` 的装载/回执层（NIT，不阻塞）。
- NIT（不阻塞）：`add_missed_recipes` 的反射接线（`AddMissedMailAndRecipes`、前后差分）只有 scratch 探针
  `scratch/_t213_probe.py` + 真机取证可证，C# 自检覆盖不到；建议 0.7.38 真机内省跑批时顺带验证一次。

## §9 变异矩阵汇总（自报 vs 实测，两列）

| 卡 | 作者自报 | 实测（我的重建 / 自建） | 结论 |
|---|---|---|---|
| 192 | 卡面未给（GAP） | 5 / 3（自建 2 条） | 单测灵敏 |
| 198 | 10/4/2/1/2/3/1 | **10/4/2/1/2/3/1（扣基线 2 红）** | **100% 相符** |
| 199 | 6/1/1/1（无脚本 ⇒ **GAP-1**） | 5 / 0 / 2 / 1 / 1（另有 2 条自建） | 2 条不符（同址性不可证） |
| 202 | 卡面未给（GAP） | 3（键）/ 0（值）（自建 2 条） | 键层灵敏、值层不可测 |
| 204 | docs-only | 不适用 | — |
| 208 | 卡面未给（GAP） | 1（规则）/ 0（入口）（自建 2 条） | 规则层灵敏、入口层未覆盖 |
| 213 | 卡面未给（GAP） | 1（规则）/ 0 / 0（入口）（自建 3 条） | 规则层灵敏、入口层未覆盖 |

方法说明：198 的基线 2 红 = `62e9089` 交付时 analyzer 桶漂移（`scratch/_t200_post198_base_suite.txt` 亲测 = 2），
task-202 后归零；"毛/净"已在 §3 表内分列。其余卡的变异在 `scratch/_t200_frozen` 副本上打文本变异后，
按 `probe`（数 `  FAIL ` 行）/`csharp`（数 `^FAIL\s` 行）/`unittest:<dotted>`（数 `FAIL:`/`ERROR:` 行）计入。

## §10 结论与"0.7.38 重冻结还需要补什么"

**批次判定：PASS-WITH-NITS（无阻塞项）。**

- 逐卡：192 PASS ｜ 198 PASS-WITH-NITS ｜ 199 PASS-WITH-NITS ｜ 202 PASS-WITH-NITS ｜ 204 PASS ｜
  208 PASS-WITH-NITS ｜ 213 PASS-WITH-NITS ｜ 205 = 跳过（已判 FAIL，归 task-216）。
- 冻结树实测：**Ran 1035 / OK（0 红）**、`dotnet build --no-incremental` 0/0、C# 自检 `OK 60 断言`、未发现新洗白通道
  （`checks`/`day_end` 键集与 `JUSTIFIED_END_REASONS` 均未变；198 的 A′ 通道 8/8、199 的认输/截断通道均有序有界）。
- **0.7.37 是否可据此冻结**：本批（192/198/199/202/204/208/213）可以；但 0.7.37 已装机且 F3（task-205）在冻结件内
  ⇒ 真正要放行 A″/B″ 的是 **0.7.38 重冻结**，其入口是 task-216。

**task-216 修完后，0.7.38 重冻结还需要补什么：**

1. **F3 修复验收**：dev-coder 交 `fd1b88d` 后我做 F3 delta 复核（plan=`pickup` 时 `_tool_upgrade_due` 不得被
   "紧急农活优先"挡死；主循环级单测：壶在途 days=0 + 窗口有没浇活苗 ⇒ 当天必须 `pickup_tool` 被调用一次）；
2. **GAP-2**：C# 自检补 3–4 条断言（`ToolUpgradeRules.Select` 的 `Tier == tierBefore+1` / kind 一致 / 不连续 tier / 多命中）
   —— 我的 `m206h`（`>=` 变异）0 杀证明现在自检覆盖不到；
3. **GAP-1**：补 `scratch/_t205_mutate.py`（m205a–d 定义），否则「自报 2/3/5/1」无法复跑；
4. **通道⑤**：`wait` / `need_slot` 日必须留 `tool_upgrade_skipped`（我 task-206 的 F1）；B1e（只扣钱算成功）/B2b（取回无背包增量算成功）判据收紧；
5. **重取批次级读数**：task-216 落地后重冻结再跑一次全量（当前 1035 是 task-216 前基线）+ 我的 `_t200_probe.py`
   与 `_t200_mutate.py` 两套矩阵（应仍 45/0 + 全杀）；
6. **不阻塞的可选项**（记 NIT，不挡住冻结）：208/213 入口层加单测；202 桶值断言；199 运行期 `readyCrops×readyTiles`
   交叉校验 + 工具侧 `ready_far` info；198 `env_block` 计数与 `no_slot` 分栏。

## §11 复跑命令

```powershell
$py="C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"
# 建冻结树（相对路径，避免 tar 打不开中文绝对路径）
cd scratch; git archive --format=tar -o _t200_frozen.tar 063351d; tar -xf _t200_frozen.tar -C _t200_frozen
# 批次级读数
cd _t200_frozen; $env:PYTHONPATH="$PWD\brain"
& $py -W error::SyntaxWarning -m py_compile brain\agentfarm\farmwork.py brain\agentfarm\longrun.py brain\agentfarm\planner.py brain\agentfarm\bridge.py
& $py -m unittest discover -s tests
& $py -m unittest tests.test_longrun.TestTask192ScopeReleaseAccounting tests.test_longrun.TestTask199ReadyFar
cd ..\..; dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental
dotnet run --project .\mod\AgentFarm.Bridge.Tests\AgentFarm.Bridge.Tests.csproj -c Release --nologo
# 探针 / 变异矩阵
& $py scratch\_t200_probe.py        # 需 T200_ROOT 指向冻结树
& $py scratch\_t200_mutate.py --base scratch/_t200_frozen --all
```

## §12 边界

- 只读生产码：未修改 `brain/`、`mod/`、`tools/`、`tests/`、`logs/`、`docs/00-开发日志.md`；未碰游戏/桥/任务板。
- 未装机、未 bump、未起跑批；一切判定基于 `063351d` 归档树 + 我自己的探针/变异。
- task-205 不在本报告重复判定（见 `docs/_review-task205.md`）；F3 复核在我收到 Lead 通知后单独出 delta 结论。
