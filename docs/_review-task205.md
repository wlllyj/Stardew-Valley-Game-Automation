# task-205 独立对抗验收（铁匠铺升级闭环）

> 验收对象：`8ee33cb`（task-205）· 验收人：deputy-lead · 2026-10-17
> 只读生产代码；探针与变异全部自建，写盘仅 `docs/` 与 `scratch/`。

## 1. 判定

**FAIL** —— 一条**必修**（P0，阻塞 0.7.38 冻结）：

- **F3：升级完成后「取回」被"紧急农活优先"永久挡死 ⇒ 自死锁。**
  `_tool_upgrade_plan()` 已经给出 `pickup`，但 `_tool_upgrade_due()` 的"紧急农活"闸门先看到
  **窗口里有没浇的活苗** 就 `return False`；而那批苗之所以浇不了，正是因为**壶/锄正在 Clint 那里升级**
  （`water_area`/`till_area` 被暂停）。于是：工具不在 ⇒ 农活永远做不了 ⇒ 取回永远到不了 ⇒ 天天
  `stuck`/`slept_without_work`。2 天实测 `pickup_calls=0`（F3a），同刻 `plan={'action':'pickup',...}`
  而 `due=False`（F3c），根因唯一。

结论：**0.7.38 不可据此冻结**。修法建议（最小）：`_tool_upgrade_due()` 的紧急农活闸门只拦
`upgrade`，`pickup` 一律放行（或在算"紧急农活"时排除被该在途工具暂停的阶段）。

## 2. A 段：范围与读数（我亲跑）

- 仓库：HEAD `2adcca6`；`git diff 8ee33cb HEAD -- brain mod tests` **为空**（仅 docs/scratch/tools note 变化）
  ⇒ 验收对象 = 工作树代码，与 `8ee33cb` 逐字一致。
- `git show --numstat 8ee33cb`：12 文件 **+2102/−4**，全落声明范围（brain/mod/tests）：
  `bridge.py` +45、`farmwork.py` +248、`longrun.py` +196/−2、`Tests.csproj` +4、`Tests/Program.cs` +81、
  `BridgeHost.cs` +6/−1、`Contracts.cs` +84、`Skills.cs` +38/−1、`ToolUpgradeRules.cs` +212、
  `ToolUpgradeSkill.cs` +809、`tests/test_farmwork.py` +158、`tests/test_longrun.py` +221。
- 越界扫描（`mod/AgentFarm.Bridge/manifest.json`、`brain/agentfarm/bridge.py` 版本行、`logs/`、`00-开发日志`）：
  本批 **未 bump** —— `manifest Version=0.7.36`、`MOD_VERSION_EXPECTED="0.7.36"`（info A1/A2，符合"冻结前不 bump"）。
- 冻结树：`scratch/_t206_pre`（`8ee33cb^`=`b053340`，631 文件 + 104 夹具）、`scratch/_t206_post`（`8ee33cb`，633 文件 + 104 夹具）。
- 读数（post 树）：`py_compile -W error::SyntaxWarning` exit 0；定向 `tests.test_farmwork tests.test_longrun`
  **Ran 518 / OK**；全量 `discover -s tests` **Ran 1026 / FAILED (failures=2)**，唯二红 =
  `tests/test_analyze_longrun.py` 的 `TestBagSpaceDeadlock.test_mechanical_enumeration_has_no_unmapped_event`
  与 `TestEventMappingDrift.test_event_buckets_cover_every_brain_journal_name`（4 个新事件未入桶 = task-207，**已知**）；
  `dotnet build --no-incremental` **0 错误 0 警告**；C# 自检 `dotnet run` exit 0、**50 ok / 0 FAIL**、`OK 50 断言全部通过`。
- SHA256 前 16：`ToolUpgradeRules.cs 45FCDA3113494B03`、`ToolUpgradeSkill.cs 158406F354084859`、
  `Contracts.cs D0375AB8E016A62F`、`Skills.cs FBDE62A538A59E83`、`BridgeHost.cs A0E01C70F0DEB4B5`、
  `Tests/Program.cs 841C1FB55C09FD2B`、`farmwork.py EB41BF868A69B346`、`longrun.py 5D13B16DD8E824EE`、
  `bridge.py 0E4BB231868E2A19`、`test_farmwork.py 0849FCAFD01036B6`、`test_longrun.py 796337D85D5B1B95`。

## 3. B 段：八条通道逐条

探针：`scratch/_t206_probe.py`（`T206_ROOT` 切树）· post 树 **PASS=46 / FAIL=4 / SKIP=0**（原始输出 `scratch/_t206_post.txt`）。

| # | 通道 | 判定 | 证据 |
|---|------|------|------|
| ① | 回执洗白 | **PASS** | B1a 回执 ok 但世界没动 ⇒ `ok=False code=failed`（"观测上什么都没变：钱 5000→5000，在途=(空)，等级 0→0"）；B1b 理由点明观测；B1c 钱/等级/在途全未变；**B1d 反向**（回执 ok=false 但世界真升级）⇒ `ok=True` 认；B2a 取回同向 ⇒ failed |
| ② | 钱不够 fail-closed | **PASS** | C1a 钱 1999<2000 ⇒ 计划 `None`、不跑腿；C1b `upgrade_calls=[]`、钱一分不动；C1c `tool_upgrade_skipped` 留痕；C2 Mod 回 `no_money` ⇒ failed 且钱不动；C3 钱够材料 0 ⇒ 计划 None；C4 钱+5 锭 ⇒ `{'action':'upgrade','kind':'axe','price':2000,...}` |
| ③ | 在途重复购买 | **PASS** | D1 daysLeft=1 ⇒ `wait`；D2 0 请求、钱不变；D3 `tool_upgrade_skipped{action:wait}`；D4 worker 层在途 ⇒ failed+0 请求；D5 **daysLeft 缺失 ⇒ fail-closed wait**（不许当 0）；D6 daysLeft=0+有空格 ⇒ `pickup`；D7 背包满 ⇒ `need_slot` |
| ④ | 选错工具 | **PASS** | E1 只售别的工具 ⇒ `tool_not_offered`、钱不动；E2 `Select` 同 kind+`Tier==tierBefore+1`+唯一命中；E3 `Precheck` 顺序；E4 `NormalizeKind`（wateringcan/fishingrod）；E5 记 NIT（见 §5） |
| ⑤ | 在途两天诚实留痕 | **FAIL** | F1b 不算 hard failure（`failed_steps=0`、`no_hard_failures=True`）、F1d `harvest_gave_up` 未消耗；**F1e 在途 wait 日 `tool_upgrade_blocked_work`/`tool_upgrade_skipped` 都是 0 条**（`due=False` ⇒ `_maybe_tool_upgrade` 根本没被调，docstring"wait/need_slot 也会留痕"不成立）；**F3a/F3c 取回死锁**（见 §1） |
| ⑥ | checks/口径污染 | **PASS（1 NIT）** | A3 `JUSTIFIED_END_REASONS` 仍 `('night','stamina','no_work')`；A9 `checks` 仍 10 键（无新增可洗白键）；G1 暂停阶段 `_leftover` 仍报 4 格（不被扣减）；G2 `_stage_tiles` 空池；G3 壶暂停期守卫不再拿"没浇水"钉死；G4 有未浇活苗+壶在途 ⇒ 当天 `verified=False`。**F1c2 口径不一致**（见 §5 NIT-1） |
| ⑦ | 变异实测 | **GAP + 自建实测** | 作者自报 m205a 2 / m205b 3 / m205c 5 / m205d 1，但**库里没有 `scratch/_t205_mutate.py`、提交说明也无定义** ⇒ 无法复跑（GAP-1）。我自建 10 条：见 §4 |
| ⑧ | 真机可复核性 | **无法判定** | H1 `docs/_il-tool-upgrade.md` 存在（25375 字符，含前置条件/首次真机调试步骤）；H3 回执带 `MoneyBefore/After/Price/TradeItem/TierAfter/ActedEvidence`；H2 `logs/` 无 tool/upgrade 相关证据 ⇒ **真机未跑，判【无法判定】**（不写成通过） |

## 4. 变异矩阵（自建，实测）

脚本 `scratch/_t206_mutate.py`（拷冻结树 + 纯文本变异 + 跑探针/跑 C# 自检；跑完删树）。
基线 control：probe `FAIL={F1c2,F1e,F3a,F3c}`、C# `0 FAIL`。

| 变异 | 目标 | 实测杀 |
|---|---|---|
| m206a 暂停失效（`_stage_tiles` 不再返回空池） | brain | **4**（F1c1/F2b/G2/G4） |
| m206b due 去掉"紧急农活优先" | brain | **2**（F4a/G4） |
| m206c 升级判据恒 ok（回执洗白） | brain | **4**（B1a/B1b/C2/E1） |
| m206d 取回判据恒 ok | brain | **1**（B2a） |
| m206e 取回去掉背包满 fail-closed | brain | **1**（F 段） |
| m206f due 把 wait 也算"该去" | brain | 0（**无行为差**：wait 计划仍只留痕、不发请求 ⇒ 可杀的只有留痕，而留痕本缺失） |
| m206g `read_only` 自检失效 | Mod 规则 | **1**（`t205_read_only_blocks`） |
| m206h `Select` 放宽到 `Tier >= tierBefore` | Mod 规则 | **0 ⇒ GAP-2**（C# 自检 50 断言未覆盖"等级不匹配要拒"） |
| m206i 证据优先级颠倒 | Mod 规则 | 锚点未命中（源码形状与我假设不同；未改代码，作废） |
| m206j `kind` 归一化失效 | Mod 规则 | **1**（`t205_kind_normalization`） |

## 5. NIT 清单（均不阻塞，但建议 0.7.38 顺手修）

- **NIT-1（口径不一致，潜在洗白面）**：暂停阶段**不产生 stage 记录**，而 `no_unmet_stages` 只按 stage 记录算 ⇒ 暂停阶段的 `_leftover`（实测 `clear_area` 剩 4 格）**看不见**：F1c2 `leftover=4` 而 `no_unmet_stages=True`。当前有 `day_justified`/`slept_without_work` 兜底（S8 实测没能洗成 `verified=True`），但这是"两套口径不一致"的隐患。建议：暂停阶段也写一条 `leftover` 记录（或日级 `no_unmet` 用 `_leftover` 汇总）。
- **NIT-2（留痕缺失）**：在途 `wait`/`need_slot` 日**没有任何 `tool_upgrade_*` 事件**（F1e），与 docstring/卡面"每天一条留痕"不符；作者用例 `test_blocked_work_is_logged_once_while_suspended` 是**直调 `_maybe_tool_upgrade`**，绕过了主循环所以没暴露。建议主循环另给一条"在途日"留痕（或在 `_tool_upgrade_due` 为 False 但 plan 非 None 时记 `tool_upgrade_skipped`）。
- **NIT-3（回执/观测边界，B1e INFO）**：`upgrade_tool` 判据含 `money_down` ⇒ "只扣钱、没升级、没在途"也会判 `ok=True`（实测：等级 0→0、在途=(空)、钱 5000→3000 仍 ok）。真机 `tryToPurchaseItem` 原子，可达性未证，但方向上是"钱花了没拿到东西仍算成功"。建议判据改成"在途出现 或 等级+1"（钱差只作记账）。
- **NIT-4（取回判据，B2b INFO）**：`pickup_tool` 判据 `being_after is None or tier_up` ⇒ "在途清空但背包没多出工具"也判 ok（实测 inventory 4→4）。与"升级副本不许丢"的关注点相关，建议加"背包内该工具 +1 或 inventoryGained"。
- **NIT-5（Mod 源码，E5）**：`ToolUpgradeSkill.MatchByExpectedData` 兜底只按 `price`+`TradeItem` 匹配、**不带 kind/索引过滤**；理论上同价同材料的另一件工具条目也会被选中。真机可达性未证（只在 U2 语义时走）。
- **GAP-1（通道⑦）**：作者变异 m205a–d **无定义、无脚本**（`scratch/_t205_mutate.py` 不在库）⇒ 自报杀数无法复跑，请 dev-coder 补变异定义。
- **GAP-2（通道⑦）**：C# 自检未覆盖 `Select` 的"等级必须 `tierBefore+1`"与"同 kind"判据（m206h 杀 0）；建议补 3–4 条行为断言（错等级/错 kind/多命中 ⇒ `tool_not_offered`）。

## 6. 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"
# 探针（冻结 post 树）
$env:T206_ROOT = "$PWD\scratch\_t206_post"
& $py -W error::SyntaxWarning scratch\_t206_probe.py        # 期望 PASS=46 FAIL=4（4 条即本报告发现）
# pre 树（has_205=False ⇒ B–H 全 SKIP；A4/A 段因接口不存在而红，符合预期）
$env:T206_ROOT = "$PWD\scratch\_t206_pre"
& $py -W error::SyntaxWarning scratch\_t206_probe.py
# 变异矩阵（自建，跑完自删树）
& $py scratch\_t206_mutate.py --all
# C# 自检
dotnet run --project mod\AgentFarm.Bridge.Tests -c Release --nologo
```

## 7. 边界与残余风险

- 本报告只覆盖 brain/mod 源码 + 假世界 + C# 自检；**真机未跑**（通道⑧ = 【无法判定】）。
- 探针改动均在 `scratch/`；未改 `brain/`、`mod/`、`tests/`、`tools/`、`docs/00-开发日志.md`、未 bump。
- 3 处已知不阻塞：analyzer 2 红（task-207）、pre 树无此特性（FAIL→PASS 对照不适用，改用变异矩阵证伪）。
