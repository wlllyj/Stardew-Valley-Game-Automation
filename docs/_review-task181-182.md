# task-183 独立对抗验收：task-181（脑侧收获四选一证据）+ task-182（Mod acted 跨观测证据 / ClumpRules / C# 自检）

- 验收人：deputy-lead（独立自写探针，**未读**作者探针；作者 docstring 引用的 `scratch/_t181_mutate.py`/`_t182_mutate.py` 不存在 ⇒ 变异装置由我自建）
- 对象：**task-181 = `c840b00`**（brain，2 文件 +266/−30）、**task-182 = `7236a9c`**（Mod，7 文件 +453/−42）
- 结论：**PASS-WITH-NITS（无必修项）⇒ 0.7.35 可以据此冻结**（NIT 见 §7，均不阻塞；残余风险见 §8）
- 覆盖状态：开工 `7236a9c`，收尾前 HEAD 前进到 `26a3ce1`（delta 为纯注释/文档 + docstring，逐行核过，见 §2.1；复跑读数逐条一致）

---

## §1 一句话判定

三条必修（①脑侧成功判据改成"动作前后观测差分四择一"、②`acted` 降级为线索、③Mod 侧 `acted` 改成跨观测证据并新增 `actedEvidence`）**实现与卡面/`docs/_t176-harvest-ready-findings.md` 的口径逐条一致**；task-177 真机两个样本格（再生作物 `(60,29)`、Scythe 对照 `(60,28)`）在假世界重放**都判对**（前者从"系统性假阴"变 `ok`，后者逐 qid loot 与 4 格 `affected_tiles` 都对）；**9 条作弊通道实测全部骗不过**（其中 5 条如实复现为"受限假阳面/措辞瑕疵"，见 §7）；**变异矩阵 7/7 符合期望**，特别是 task-178 点名的 GAP-1（"等价兜底被 `return (null, null);` 短路"）**已被新建的 C# 行为自检工程杀死**。

---

## §2 A 段：范围与读数（我亲跑）

| 项 | 读数 |
|---|---|
| HEAD | `7236a9c`（父 `c840b00` → `e6e1723` → `89db268` → `f851423` → `521a3ce`） |
| `git show --numstat 7236a9c`（task-182） | 恰 **7 文件 +453/−42**：`mod/AgentFarm.Bridge.Tests/AgentFarm.Bridge.Tests.csproj` 38/0、`mod/AgentFarm.Bridge.Tests/Program.cs` 83/0、`ClumpRules.cs` 60/0、`Contracts.cs` 17/0、`CropMeta.cs` 8/18、`Skills.cs` 120/14、`tests/test_longrun.py` 127/10 |
| `git show --numstat c840b00`（task-181） | 恰 **2 文件 +266/−30**：`brain/agentfarm/farmwork.py` 101/29、`tests/test_farmwork.py` 165/1 |
| 越界扫描（`manifest.json`/`brain/agentfarm/bridge.py`/`^logs/`/`00-开发日志`） | 两提交 **0 命中**（工作树另有 `?? scratch/_t180_mutate.py`、`?? tools/_note-0735.txt`，非本次对象） |
| SHA256 前 16 / 字节 | `farmwork.py E89DBB3C78DFFF12` 167713、`longrun.py 2C5DEAAA0368B0C1` 390876（未改）、`planner.py CB9A078A78FD3D45` 108882、`Skills.cs B3C62601FAB23318` 43249、`CropMeta.cs 0880D50436282250` 12073、`Contracts.cs 533BEE3BD06B5AA1` 69908、`test_longrun.py C7E669E0FEE2FE99` 495081 |
| `py_compile -W error::SyntaxWarning` | `longrun/farmwork/planner/bridge` **rc=0** |
| 定向 `tests.test_farmwork tests.test_longrun tests.test_planner` | **Ran 532 / OK** |
| 全量 `discover -s tests` | **Ran 924 / OK（0 红）** |
| `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --no-incremental` | **0 警告 0 错误**（1.38 s） |
| `dotnet run --project .\mod\AgentFarm.Bridge.Tests\... -c Release` | **rc=0 / `OK 18 断言全部通过`** |

留档：`scratch/_t183_targeted.txt`、`_t183_full.txt`、`_t183_build.txt`、`_t183_cstests.txt`、`_t183_diff_brain.txt`(234 行)、`_t183_diff_mod.txt`(637 行)。

### §2.1 验收期间 HEAD 前进（并发变更核对，必须记）

我开工时 HEAD = `7236a9c`（上表读数取自该状态）。收尾前发现 HEAD 已前进两提交（**不是我的**）：

| 提交 | 内容 | 是否影响被验逻辑 |
|---|---|---|
| `145c65c` | `tools/_note-0735.txt` +7（0.7.35 备注） | 否 |
| `26a3ce1` | `docs/_t176-harvest-ready-findings.md` +26、`mod/AgentFarm.Bridge/Skills.cs` **+8（纯注释）**、`tests/test_longrun.py` +16/−5（**docstring-only**） | **否** |

- `git diff 7236a9c..26a3ce1 -- mod/AgentFarm.Bridge/Skills.cs` 逐行读过：只新增【NIT-2 局限】注释块（门/入口传送格可能落 `acted=false`/`no_action`，今天无害），**无任何逻辑改动**；测试侧的改动只更正 `TestTask176HarvestMethodSourceAndActed` 的 docstring（GAP-2 变异读数），**断言与用例个数未变**。
- 复跑读数（当前工作树 = `26a3ce1`）：定向 `tests.test_farmwork tests.test_longrun tests.test_planner` = **Ran 532 / OK**、全量 `discover -s tests` = **Ran 924 / OK**、`dotnet build --no-incremental` rc=0 / **0 错误**、`dotnet run`（C# 自检）rc=0 / **`OK 18 断言全部通过`** ⇒ 与本节原读数逐条一致（留档 `scratch/_t183_targeted2.txt`、`_t183_full2.txt`、`_t183_build2.txt`、`_t183_cstests2.txt`）。
- `mod/AgentFarm.Bridge/Skills.cs` 指纹按当前状态更新为 `4FB3C7D77D8FA99E` / 44089 B（开工时 `B3C62601FAB23318` / 43249 B；`farmwork.py`、`CropMeta.cs` 指纹未变）。
- 我的探针与变异矩阵**本身就是在前进后的工作树上跑的**（0.7.35 全量状态）⇒ §3–§6 的结论覆盖 `26a3ce1`，不是只覆盖 `7236a9c`。
- 附注：`26a3ce1` 自己更正了 GAP-2 的变异读数（`m176a`–`m176d` 各杀 1 条、杀点全是**文本契约**、行为层当时无用例）——与我 task-178 的实测（`m178a` 杀 1）互相印证，也再次说明 task-182 新建 C# 自检工程的必要性。


---

## §3 B 段：task-177 真机重放（假世界差分）

探针 `scratch/_t183_probe.py`（`T183_ROOT` 切树）+ 输出 `scratch/_t183_probe_out.txt`。

| 例 | 输入（真机读数） | 期望 | 实测 |
|---|---|---|---|
| **B1** 再生作物 `(60,29)` | 动作后 `crop` 仍 `"270"`、`ready true→false`、`readyCrops 102→101`、背包 `(O)270 +1`、Mod 回执 `acted=false` | `ok=true` | **PASS**：`ok/code=ok`，reason = `收获成功（判据：该格 ready true→False；进背包：{'(O)270': 1}；farm.readyCrops 102→101）`；`harvested == {"(O)270": 1}`；`affected_tiles == [[60,29]]`；Mod 的 `acted=False` 只出现在失败文案模板里、本轮不进成功文案 |
| **B2** 对照 `(60,28)`（Scythe） | 一镰刀 `crops 102→98`、`readyCrops 101→97`、背包 `(O)262 +4`、`(O)178 +2`、该格键消失 | 走 `use_tool`、逐 qid loot、4 格 affected | **PASS**：工具路径 `['scythe']`；`loot == {"(O)262":4,"(O)178":2}`；`harvested` 两件；`affected_tiles` 覆盖 4 格 |
| **B3** 四条全不成立 | 回执谎报 `ok=true, acted=true`、世界没变 | `failed` | **PASS**：`code=failed`、文案点名"四条判据全不成立"、白名单空、世界 crop 仍在 |

**结论**：task-177 判据 (4) 的"反向违反（`acted=false` 而世界确实变了）"已被修掉；再生作物不再系统性假阴。

---

## §4 C 段：作弊通道（9 条，实测）

探针逐条构造，`check()` 计正确行为、`finding()` 单列"复现出来的发现"。

| # | 通道 | 实测 | 结论 |
|---|---|---|---|
| C1 | **动作后观测缺了这一格**（世界真相不变） | `ok=true`，reason 写"该格 crop 已消失；该格 ready true→None"，`affected_tiles=[[60,29]]`，而 `records` 里 crop 仍在；白名单为空（无 loot） | **发现 F1**（缺失被当成功）。**不能洗白天级判定**：作物仍在 ⇒ `_leftover` 仍算未做完、当天不 VERIFIED |
| C2 | `crop=null` 但 `ready=true`（自相矛盾观测） | `ok=true`（`crop_gone`） | **发现 F2**（Mod 不会产出这种形状 ⇒ 实际不可达） |
| C3 | 背包 +N 来自**无关来源** | `ok=true`，`harvested == {"(O)128":1}`；进一步 `sellable_slots()` 非空、`sell_loot()` **真的把该无关 qid 出了货** | **发现 F3**（白名单污染，下游会真出货）；但 `_loot_delta` 的"逐 qid 背包差分"是 **task-42 既有**机制，本卡只是把它从"一格一物"改成逐 qid ⇒ 既有信任边界 |
| C4 | 背包满**按 `inventory[]` 行数**判 | 12 行/容量 12 ⇒ `failed` + "背包满" + **零请求**；对照 11 行 ⇒ 真请求并成功；容量字段缺失 ⇒ 不判满（"不知道 ≠ 满"） | **PASS**（对齐真机 `inventoryCount` 腾格后仍读 12 的现象） |
| C5 | 一镰刀多格但只掉 1 个 qid | `loot` 1 条、`affected_tiles` 仍 4 格 | **PASS**（两边都没缩水） |
| C6 | 只有 `farm.readyCrops` 下降（格子级什么都没变） | `ok=true`、白名单**空**、`affected_tiles="unknown"` | **PASS**（按卡面是设计内判据；至少不污染白名单） |
| C7 | 旧路径回归（非再生 crop 消失） | `ok=true`、文案走"crop 已消失"、不误标"再生作物"、白名单正确 | **PASS** |
| C8 | **仅 `readySource` 标签变化**（`ready` 仍 true、无 loot） | `ok=true`，文案"判据：该格 readySource game→fields" | **发现 F4**（按卡面②这是设计内判据，但单独"来源标签抖动"即判成功，属残留假阳面） |
| C9 | `farm.readyCrops` 缺失/类型不对 | 该通道不构成证据、整体 `failed` | **PASS**（fail-closed）；但失败文案仍断言"farm.readyCrops 没下降" ⇒ **发现 F5**（措辞） |

探针汇总：**PASS=38 / FAIL=0**，复现发现 5 条。

**卡面点名、但脑侧结构上不可能的两条（我单独核过）**：
1. **伪造 `actedEvidence`** —— `grep -n "actedEvidence" brain/` **零命中**：脑侧只读回执的 `status` 与 `acted`，凭证字段根本不参与判定；`B3` 已实测同类（回执 `acted=true` 而世界没变 ⇒ `failed`）。也就是说 `actedEvidence` 是**诊断字段**、不是信任来源。
2. **"`ready` 翻转但背包没变仍报成功"** —— 这是**卡面/`docs/_t176-harvest-ready-findings.md` 的设计内判据**（四择一任一成立即可；真机 `(60,29)` 正是这种形态），探针 `B1` 覆盖；更极端的"只有 `farm.readyCrops` 下降、格子级什么都没变"由 `C6` 覆盖（判成功但白名单必须为空）。

---

## §5 D 段：Mod 侧（静态契约 + 行为化）

| # | 检查 | 实测 |
|---|---|---|
| D1 | 证据优先级 `tile > ready > readyCrops > inventory` | PASS（`Skills.cs` 四条 `if/else if` 顺序与卡面一致；格子级优先、全局面垫底） |
| D2 | `acted` 只由证据决定 | PASS（`bool acted = err == null && evidence != null;`，且旧的 `Ok = err == null && handled` 不在） |
| D3 | `actedEvidence` 落盘 + 契约声明 | PASS（`ActedEvidence = evidence`；`Contracts.cs` 有 `[JsonPropertyName("actedEvidence")]`） |
| D4 | `readyCrops` 读不到返 **-1** 且判据要求 `>= 0` | PASS（`return -1;` + `readyCropsBefore >= 0 && readyCropsAfter >= 0`） |
| D5 | `ClumpRules` 零游戏类型 + `CropMeta` 取数后只有一条委托 return | PASS（代码行无 `HoeDirt`/`Netcode`/`StardewValley`；`return ClumpRules.Ready(gameSaid, …)`） |
| D6 | NIT-1：`forageCrop && whichForageCrop == null ⇒ (null, null)` | PASS |
| D7 | C# 行为自检工程 | PASS（`dotnet run … -c Release` rc=0 / `OK 18 断言全部通过`） |

**INFO-2（我顺手核的 Lead 提示②）**：`readyCrops`/`inventory` 两路**天然是全局量** ⇒ 别的格/别的事件造成的变化也会让 Mod 报 `acted=true`（`actedEvidence="readyCrops"/"inventory"`）。脑侧已不采信 `acted`（只作线索）⇒ 今天无害；但字段名承诺的是"本次动作的证据"，建议文档/字段注释把"全局弱证据"写死（`Contracts.cs` 已写 inventory 是弱证据，`readyCrops` 同理）。

---

## §6 变异矩阵（自建 `scratch/_t183_mutate.py`，输出 `scratch/_t183_mut_out.txt`）

每个变异把 `brain/`+`tests/`+`mod/` 拷进 `scratch/_t183_mut/<case>/`，在副本上改一处，跑 4 个类（共 23 条）：

| 变异 | 改动 | 红数 | 被杀用例 |
|---|---|---|---|
| **control** | 无 | **0**（Ran 23 / OK） | — |
| m183a `crop_gone_only` | `if evidence:` → `if crop_gone:`（判据退回只看作物消失） | **2** | `test_regrowing_crop_ready_flip_with_loot_is_a_success`、`test_ready_crops_drop_alone_is_enough` |
| m183b `capacity_as_free` | 空槽改读容量字段 | **2** | `test_full_backpack_is_judged_by_row_count_not_capacity`、`test_full_backpack_blocks_the_request_entirely` |
| m183c `loot_single_qid` | `_loot_delta` 只取 1 个 qid | **1** | `test_one_swing_can_harvest_several_tiles_and_reports_each_qid` |
| m183d `receipt_first` | 回执 `acted is False` 即判失败（老行为） | **2** | `test_regrowing_crop_ready_flip_with_loot_is_a_success`、`test_acted_false_receipt_is_a_failure_even_when_ok` |
| **m183e `clumprules_early_null`** | 游戏分支后插 `return (null, null);`（**= task-178 的 GAP-1 replay**） | **1** | `test_csharp_rules_self_test_passes` ⇐ **GAP-1 已闭合** |
| m183f `nit1_gate_removed` | 删 NIT-1 闸 | **2** | `test_nit1_which_forage_crop_is_part_of_the_gate`、`test_csharp_rules_self_test_passes` |

**期望不符数 = 0**（`m183d` 我原本保守估 1，实测 2 ⇒ 已按实测更正期望）。

---

## §7 NIT 清单（按卡面要求注明是否阻塞）

| 编号 | 现象 | 位置 | 是否阻塞冻结 | 建议 |
|---|---|---|---|---|
| **NIT-1 ＝ F1** | `crop_gone = not (tv or {}).get("crop")` ⇒ **目标格从观测里消失**（窗口截断/丢失）被当成功；`ready_flipped` 也会把"`ready→None`"算成翻转 | `brain/agentfarm/farmwork.py:2350-2352` | **不阻塞**（作物仍在 ⇒ `_leftover` 仍算未做完，不会把一天洗绿；白名单为空 ⇒ 不会误出货） | 下一次动这块代码时：要求"目标格仍在观测里"才认 `crop_gone`/`ready_flipped`（`tv is None` ⇒ 判不了 ⇒ 不成功） |
| **NIT-2 ＝ F4** | 仅 `readySource` 标签变化（`ready` 仍 true、无 loot）即判成功 | `farmwork.py:2353` | 不阻塞（卡面②即此设计） | 若想更严：把 `source_changed` 从独立判据降为"仅在 `ready_flipped or gained or ready_dropped` 时的加分说明" |
| **NIT-3 ＝ F2** | `crop == null` 且 `ready == true` 的矛盾观测被采信 | `farmwork.py:2350` | 不阻塞（Mod 侧 `Ready(dirt=null)` 走 != null 分支返回 `(null,null)` ⇒ 实际不可达） | 可加一句"`crop` 为 null 时 `ready` 视为判不了"的防御 |
| **NIT-4 ＝ F3** | 无关物品进背包 ⇒ 记进收获白名单 + `sell_loot` 真会出货 | `farmwork.py:2363-2366`、`sellable_slots:2461` | 不阻塞（`_loot_delta` 逐 qid 差分是 task-42 既有机制；本卡修的是"一格一物"漏记） | 建议后续卡：白名单只在"目标格 crop 消失 / ready 翻转"同时成立时才叠加 `gained`（纯背包差分的白名单可被无关掉落污染） |
| **NIT-5 ＝ F5** | `readyCrops` 判不了（缺失）时，失败文案仍断言"farm.readyCrops 没下降" | `farmwork.py:2398-2399` | 不阻塞（判据 fail-closed 正确，纯文案） | 文案按实际可评估的通道动态拼接 |
| **INFO-1** | Mod 的 `readyCrops`/`inventory` 两路是**全局量** ⇒ 无关变化也能填 `actedEvidence` | `Skills.cs` 四路 | 不阻塞（脑侧不采信 `acted`） | 字段注释写清"全局弱证据" |
| **INFO-2** | 证据只覆盖"世界变了"，不覆盖"**是我的动作导致的**" | 同上 | 不阻塞 | 若要更强，只能靠"目标格签名"单路 + 明确 `no_action` |

---

## §8 残余风险

1. **NIT-1 的可达性**：需要"动作后目标格不在观测里"。本机窗口是半径 3 + `location.tiles` 全量（`FarmWorker.snap()` 走 `observe("full")`），`harvest()` 期间玩家不动 ⇒ 正常路径不可达；只有窗口截断（Mod `MaxTiles` 上限）或观测异常才会出现。无假绿后果（见 NIT-1 列）。
2. **NIT-4 的下游放大**：若某天真的发生"无关掉落 + 收获判成功"，`sell_loot` 会把这件无关物品出掉。建议 run A/B 后抽查 `sell` 事件的 `qid` 是否都来自 `harvest`。
3. `readyCrops`/`inventory` 作为 `actedEvidence` 的"全局弱证据"性质不变 ⇒ task-177 的真机结论仍以"脑侧四选一"为准。

---

## §9 结论

- **task-181 = PASS-WITH-NITS**（三条必修逐条落地；真机两格重放都对；四类伪造只有"受限假阳面"）。
- **task-182 = PASS-WITH-NITS**（`acted`/`actedEvidence` 契约与优先级正确；`-1` 哨兵与 NIT-1 闸到位；**新建 C# 自检工程把 task-178 的 GAP-1 杀掉了**）。
- **无必修项 ⇒ 0.7.35 可以据此冻结。** NIT-1/NIT-4 建议排到后续卡（不是本版闸门）。

---

## §10 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"
# 探针（post 树）
& $py -W error::SyntaxWarning scratch\_t183_probe.py *> scratch\_t183_probe_out.txt
# 变异矩阵（control + 6 变异；含 m183e = GAP-1 replay）
& $py -W error::SyntaxWarning scratch\_t183_mutate.py *> scratch\_t183_mut_out.txt
# 卡面读数
& $py -W error::SyntaxWarning -m compileall -q brain\agentfarm tests
& $py -m unittest tests.test_farmwork tests.test_longrun tests.test_planner
& $py -m unittest discover -s tests
dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental
dotnet run --project .\mod\AgentFarm.Bridge.Tests\AgentFarm.Bridge.Tests.csproj -c Release
```

## §11 越界

只写 `docs/_review-task181-182.md`、`scratch/_t183_probe.py`、`scratch/_t183_mutate.py`（+ `scratch/_t183_*` 输出 txt）与临时副本目录 `scratch/_t183_mut/`（跑完自删）。未碰游戏/桥、未 deploy、未改任务板与开发日志；生产代码只读（变异全部在副本里做，已核对工作树 `brain/`/`mod/` 无需恢复）。

---

## §12 task-186 收口记录（dev-coder，2026-10-17）

task-186 按本文件的 F1/F3/F5 三条必修与 NIT-4 收尾，落地如下（详细读数见 task-186 交付消息）：

| 条目 | 处理 | 落点 |
| --- | --- | --- |
| **F1** 动作后观测缺格被当"crop 消失 ⇒ 成功" | 只在**该格确实出现在动作后观测里**时才允许走"crop 消失"这一路；**同一原则扩到 `ready`/`readySource` 两路**（缺格时 `(tv or {})` 给 `None`，旧写法会把"没看见"读成"翻转了/来源变了"，与 crop 路是同一条假绿通道）；`affected` 只认动作后**仍看得见**的格 | `brain/agentfarm/farmwork.py` `harvest()` 判据段 |
| **F3 / NIT-4** 白名单污染 | 白名单改为绑定"与目标格变化相关"的收获：**只有背包差分、没有格子级证据**（crop 消失 / ready 翻转 / readySource 变化 / 受影响格）的那批 qid **不进** `worker.harvested`（步骤仍算收获成功）；`sell` 事件新增 `whitelist` / `whitelist_count` / `whitelist_source` 三个**字段**（刻意不新增事件名，避免 analyzer 机械枚举漂移） | `farmwork.py` 白名单累加 + `longrun.py` `_ship_loot` |
| **F5** 措辞诚实 | `readyCrops` 缺失 ⇒ "farm.readyCrops 无法判定（字段缺失/该 Mod 版本不提供）"；读数 `< 0` ⇒ 同样写"无法判定（读数 x→y）"；只有两边都是非负 `int` 才写"x→y 没下降" | `farmwork.py` 失败文案 |
| **NIT-2 ＝ F4**（仅 `readySource` 标签变化即判成功） | **有意口径，不修**：卡面必修 2 的判据 b) 明文包含"或 `readySource` 变化"（task-177 真机里 `readySource` 由 `game` 变 `fields` 正是收获发生的信号之一）。本文件 §7 的 NIT-2 行保留为记录，**不视为待修**；若将来要更严，按该行的备选方案（降为加分说明）另开卡 | 本文档 |

变异实测（`scratch/_t186_mutate.py`，brain+tests 一起拷临时目录，跑完已删）：基线 4/4 绿；`m186a`（`crop_gone` 去掉 `tile_seen`）杀 2、`m186b`（`ready`/`readySource` 两路去掉 `tile_seen`）杀 2、`m186c`（白名单改回"有 gained 就加"）杀 1。
