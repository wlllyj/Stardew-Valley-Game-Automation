# 0.7.36 发布计划 — loot 白名单收敛（task-186/189）+ Mod `use_tool` 回执诚实化（task-188）+ 认输释放的末态记账（task-192）

> 立卡时间：2026-10-17（Lead）。来源：task-184 真机复测残留 R1/R2/R3（`docs\_run10-harvest-verify-0735.md`，machine-runner `61031b6`）+ task-185 的 NIT-1（`docs\_review-task168.md`，deputy-lead `bd50814`）。

## 0. 为什么有这一版

0.7.35 把「收获成功」的真相钉死了（task-181/182/168），同格复测也过了三源一致。但同一次复测暴露三条**残余不彻底**：

- **R1（Mod）**：`use_tool` 路径（镰刀类作物）**没有** `acted`/`actedEvidence` ⇒ 回执仍可能是"世界变了却报没动手"的另一半；`skill:"use_tool"` 的 reason 还会渲染成空物品名（R4 文案）。
- **R2（brain）**：多格一次动作（一镰刀连收 4 格）与"并入既有叠"的 loot 记账靠**动作后第一张观测**，落下物有延迟 ⇒ 真机上 `(O)262 +4 / (O)178 +2` 被脑侧读成"背包没有新增物品"；判据本身没写错，是**时序 + 文案**把"还没看见"当成了"确实没有"。
- **R3（判据/文档）**：`interact` 的 `worldSeq` 可能不动（60→60）⇒ 不能拿它当成功信号；已写进 `docs\_run10-criteria.md` §5。

外加一条 task-185 的 NIT-1：`_release_zone` 释放认输区时**不扣当天认输记账** ⇒ `day_end.scope_shed_tiles` 记的是"曾经认输过多少格"而不是"日终仍在认输态多少格"，雨天「先认输 → 雨浇好 → 释放 → 其余活做完」的**诚实日**会被工具误判成 needs_review。判据修在工具侧（净额对账，`3ccc29b`），记账修在脑侧（task-192）。

## 1. 本批卡片（入版范围）

| 卡 | 所有者 | 内容 | 状态 |
|---|---|---|---|
| **task-186** | dev-coder | F1 缺格不许当"crop 消失"（`crop_gone = tile_seen and not crop`，且 `tile_seen` 同时把关 `ready`/`readySource` 两路）+ F3 白名单绑格子级证据（`whitelist_bound`/`tile_seen`，sell 事件加 `whitelist`/`whitelist_count`/`whitelist_source`）+ F5 措辞 | ✅ `c67b85f`（949 OK） |
| **task-189** | dev-coder | R2 loot 记账：有界确认（`LOOT_CONFIRM_TRIES=2` × 0.35s，只服务背包）+ 与 `affected_tiles` 对账 + 废止"背包没有新增物品"这句 + `loot_waits`/`loot_unconfirmed` | ✅ `7f9c719`（952 OK） |
| **task-188** | dev-coder | R1/R4（Mod）：`use_tool` 也走 task-182 的跨观测证据 + fail-closed；reason 文案不再渲染空物品名；C# 自检工程 ≥+3 断言 | 在制 |
| **task-192** | dev-coder | NIT-1（brain）：`_release_zone` 释放时扣当天认输记账并同步 `rep.scope_shed`/`shed_zones` 为**日终末态**；护栏一律不放宽 | 待做（排 188 后） |
| **task-190** | deputy-lead | task-186/188/189 独立对抗验收（自建变异实跑、C5 Mod 回执复核、C6c 作者自报变异映射实测、C2-a 记 NIT） | 骨架已就（`b632b42`，24 PASS/0 FAIL/2 SKIP） |
| **task-191** | machine-runner | 0.7.36 真机复测：镰刀格走 `use_tool` ⇒ 脑侧 `ok` + Mod `acted/actedEvidence` + 世界证据三者一致；多格 loot 记账与 `loot_waits` 如实 | blocked_by 190 |
| task-113（改） | machine-runner | **A′/B′ 复跑**（同构建、argv 只差 `--journal`；B 起点 = A 的 lessons 字节拷贝）⇒ L0–L5 | blocked_by 191 + 冻结装机 |

**不入本版**：task-193（白名单只收本格作物产物 id）、task-175（`harvest_gave_up` 窗口依赖）、task-174（账本 farm 白名单补 `ripeCrops`/`readyCrops`）、目标 1 的经济/工具链（task-141/142/151/152/155）⇒ 0.7.37+。

## 2. 冻结九步（Lead 独占，链条冻结后一次做完）

1. `tools\_note-0736.txt` 首串必须是 `v0.7.36`（列本版 Mod 侧改动：task-188）。
2. `python tools\_bump-mod-version.py 0.7.36 --note-file tools\_note-0736.txt` ⇒ `manifest 0.7.35 → 0.7.36`（`json.load` 复核）。
3. `brain/agentfarm/bridge.py` 的 `MOD_VERSION_EXPECTED = "0.7.36"`（注释补 v0.7.36 条目，历史保留）。
4. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警 0 错**；记 dll / manifest 字节数。
5. `git add -A` + 冻结提交（工作树必须干净，否则 `check-release` 会红）。
6. `python tools\check-release.py --expect 0.7.36` ⇒ **六项全绿**（含全量单测、dll 不比源码旧、工作树干净）。
7. `python tools\deploy-mod.py --no-quit` ⇒ `0.7.35 → 0.7.36`，桥 `modVersion=0.7.36`，自动读档。
8. `python -m agentfarm goto Farm` ⇒ `preflight --expect 0.7.36 --save-baseline logs\run10d-baseline.json` 四项全绿。
9. 把五文件指纹 + argv + 现场读数发 machine-runner，GO **task-191**。

## 3. 判据

- **task-191（真机）**：镰刀格（`(60,28)` 类）走 `use_tool` ⇒ 脑侧 `ok` **且** Mod `acted=true`/`actedEvidence` 非空 **且** 世界证据至少一条；多格 loot 逐 qid 记账与 `loot_waits` 如实；出现"世界变了仍报 no_action"或"脑侧 ok 但世界没变" ⇒ FAIL + 最小复现。
- **A′/B′**：`tools\run-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12`；三检查器（`verify-run3` / `analyze-longrun` / `run9-lead-check`）同向 + L0–L5（`compare-runs`，L1 用 `hint`/`symptom` 口径 + `lesson_section_present` 双信号）。
- **目标 2 的验收**：连续 5 个游戏日 VERIFIED + 每日 ≥2 份独立观测 + 落盘五/六串配对 + L0–L5 对照；`history_problems` 只呈现，**尾部窗口**必须零问题。

## 4. 已知限制 / 风险

- **C2-a（deputy-lead task-190 骨架复现，记 NIT）**：有格子级证据时白名单取整份 `gained`，同动作顺手进包的无关注 qid 仍会进白名单（构造：收成 + `(O)128` ⇒ `harvested={'(O)128': 1}`）。这是**归因不彻底**（原洞"只凭背包差分也进白名单"已堵），不影响四腿与禁卖物清单 ⇒ 不阻塞本版，收紧见 **task-193**（0.7.37）。
- **GAP-1（deputy-lead task-190 实测，`m188e2` 变异 0 杀）**：task-188 的 R4「原物渲染成空」是**纯文本契约**，只覆盖模板站点、**不覆盖 `OriginalText()` 的兜底值**（把兜底改成 `（空）` 没有任何用例杀）。行为层不受影响、不影响四腿 ⇒ 不阻塞本版；后续若要覆盖，必须**行为化**（断言渲染结果而不是源码文本），记 **task-193**（0.7.37）批次。
- **NIT-2（deputy-lead task-190 实测）**：dev-coder 自报的「变异⇒用例」映射数字有两条不符（`m188a` 自报 7 实测杀 6、`m188b` 自报 8 实测杀 7）——**方向一致（两种变异都被杀）**，只是计数口径差；教训：自报映射必须以实测为准（同 task-180 的 GAP-2）。
- **`readyCrops == crops`**：游戏口径，不是 fail-open；本版不动目标池收窄，靠 `harvest_gave_up` 兜底。
- **`acted` 扩权到 `use_tool` 后**：必须防"世界变了但与本次动作无关"；`actedEvidence` 如实落来源，脑侧仍以观测差分判成功。
- **有界确认的代价**：`LOOT_CONFIRM_TRIES=2` × 0.35s 只在有格子级证据时发生 ⇒ 每天最多几次 × 0.7s，可忽略；但"真丢在地上"的情况会多花 0.7s 并如实写"对不上"。
- 时间预算：本批 4 张实现卡（186/189 已完成）+ 1 张对抗验收 + 1 张真机 + 2 次 5 天长跑。

## 5. 执行记录（2026-10-17）

### 5.1 链条（冻结前）
| 卡 | 交付 | 内容 | Lead 亲核 |
| --- | --- | --- | --- |
| task-186 | `c67b85f` | 收获缺格不当成功（`crop_gone = tile_seen and not crop`）+ loot 与 `affected_tiles` 对账 + sell 白名单收窄 + F5 措辞 | 4 文件 +193/−12；全量 949 OK |
| task-189 | `7f9c719` | loot 记账根因 = 时序而非判据 ⇒ 有界确认轮 `LOOT_CONFIRM_TRIES=2 × 0.35s` + `loot_waits`/`loot_unconfirmed`；退役"背包没有新增物品"措辞 | 2 文件 +181/−4；全量 952 OK |
| task-188 | `e612464` | `use_tool` 回执补 `acted`/`actedEvidence`（与 `interact` 同源、fail-closed）+ R4 文案；C# 自检 26 断言 | 5 文件 +386/−9，只命中 `mod/AgentFarm.Bridge{,.Tests}/`；全量 959 OK |
| task-192 | `1246cdd` | 释放认输区同步扣减当天记账（`day_end.scope_shed*` = **日终末态**）+ 累计量 `shed_ever` 持久化（释放不清） | 3 文件 +282/−9；全量 **965 OK**；`planner.py` 越界为**纯加法**（可选 `ever` kwarg + 坏数据整份拒收），Lead 批准保留 |
| task-190（对抗验收） | `96d93a7` | deputy-lead：**PASS-WITH-NITS ⇒ 0.7.36 可以据此冻结** | 定向 554 OK / 全量 959 OK / build 0/0 / C# 自检 26 OK；pre186 18/17、pre188 30/5、pre189 27/8 ⇒ post **35/0**；C6c 实测 `m188a` 杀 **6**、`m188b` 杀 **7**（自报 7/8，方向一致，记 NIT-2）；`m188c/d/e` 各杀 1 符合；新增 `m188e2`（`OriginalText()` 兜底值）**0 杀** ⇒ **GAP-1** = R4 是纯文本契约、不覆盖兜底值（行为层不受影响） |
| task-185（task-168 验收） | `bd50814`+`4885ce8` | **PASS-WITH-NITS**；15 条认输洗白通道全不通；provenance blob 与 `30082e0` 全等 | NIT-1（释放不重置当天记账）⇒ Lead 裁定「修」⇒ task-192 |

### 5.2 冻结（`7ad5f6b`）
1. `tools\_note-0736.txt` 首串 `v0.7.36`（已核，8 行）。
2. `_bump-mod-version.py 0.7.36 --note-file tools\_note-0736.txt` ⇒ `manifest 0.7.35 → 0.7.36`（`json.load` 复核 = 0.7.36）。
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.36"`（注释补 v0.7.36 三条 + 历史保留）。
4. `dotnet build --no-incremental` ⇒ **0 警 0 错**；dll **202752 B** / manifest **53261 B**。
5. 冻结提交 **`7ad5f6b`**，树干净。
6. `check-release --expect 0.7.36` ⇒ **六项全绿**：manifest==brain 0.7.36 / ==期望 / dll 08:17:05 > `UseToolSkill.cs` 07:55:26 / py_compile 22 文件 / **`Ran 965 tests` OK** / 树干净。

### 5.3 装机与基线（`logs\run10d-baseline.json`）
- `deploy-mod --no-quit` ⇒ `0.7.35 → 0.7.36`（dll 202752 / manifest 53261），桥 `modVersion=0.7.36 port=17890`，自动读档 `Wahaha_450799035`（FarmHouse (9,9)）。
- `goto Farm` ok：`hop1 FarmHouse→Farm source=[3,12] landing=[64,15]` **7608ms**（秋12 06:10 → 06:20）。
- `preflight --expect 0.7.36 --save-baseline logs\run10d-baseline.json` = **✅ 可以起跑**：秋12日 **06:40 rain** / Farm(64,15) / 体力 **247.2**/270 / 钱 **0g** / `Wheat Seeds ×1`（483）/ 作物 **102** / `unwateredCrops 2` / `dryCrops 0` / `waterLeft 27` / farmingLevel 1 / `farmScanSeq 13` / `tillableCount 120` / `tileCount 400 truncated` / 无模态 / `worldAdvancing true`。

### 5.4 指纹与移交（GO task-191）
- 五文件指纹：`longrun.py C326DD1E1358EA15` / `farmwork.py FA6BD05CCAB9DF25` / `bridge.py 968D1D227A293B1A` / `dll D6699BD057C51CE7` / `manifest 6578C42574237AA8`（只比这五个 + argv，不比 HEAD）。
- 已发 machine-runner：四件复测（`interact` 与 `use_tool` 两条路出数 / `use_tool` 回执两键 / loot 逐 qid 对账 / 不可收格不被洗成成功）+ 纪律（先腾一格背包、不 `load_save`、`worldSeq` 不是成功信号、收尾优雅退游戏）。
- **后续**：task-191 四条全绿 ⇒ 起 **task-113（A′/B′，各 5 天）**；`docs\_run10-criteria.md` §5 的测量规则（`worldSeq` 不是成功信号）已生效。

### 5.5 task-191 真机复测结果（2026-10-17，machine-runner）
- 交付 **`eb93c13`**（2 文件 +495：`docs\_run10-harvest-verify-0736.md` 131 行 + `scratch\_t191_probe.py`）。**卡面写的是 `docs\_run10d-verify-0736.md`，实际交付名以我 GO 消息里允许的 `_run10-harvest-verify-0736.md` 为准**（已在消息中确认接受，不再改名重提）。
- **四条判据全绿 = PASS**：①两条路都出数（`interact` 样本格 `(60,29)`：脑 `ok=True`、Mod `acted=true/actedEvidence="ready"`、`ready_flipped`+`loot {'270':1}`；`use_tool` 同类镰刀格 `(60,30)`：脑 `ok=True`、Mod `acted=true/actedEvidence="tile"`、`crop_gone`+`ready_flipped`+`loot`+`worldSeq` 前进）；②**R1 闭合**（`use_tool` 成功路径两键都在）；③loot 逐 qid 与白名单内实测精确一致，`loot_waits 1` 真机生效；④fail-closed：不可收格 ⇒ `skipped`、背包满 ⇒ `failed`，**两者零触桥**。
- **口径差异（已接受，不当作已覆盖）**：判据④卡面写「`ready=false` ⇒ 脑侧 `code=failed`」，实际 0.7.36 返回更早更保守的 `skipped`；「Mod 回执 `acted=false` 且脑侧 `failed`」这一形态**真机没造出来**（脑侧先拦），已在 `docs\_run10-harvest-verify-0736.md` §9 如实留痕。
- **两条新残留立案（0.7.37，跑批期不动 brain/mod）**：**task-195** = 原始 `use_tool` 路径的 `actedEvidence` 是**聚合口径**（对目标格描述可错）且无脑侧守卫时**破坏性**（实测连带清 4 格含未成熟作物）；**task-196** = 非白名单附带掉落（镰刀顺带割草 `Moss +1`）未计入 `loot`/`affected_tiles`。
- **收尾按 m02833**：`stop-game.py` rc=0 ⇒ 进程 0 / `bridge.json` 已删 / 17890 仅 TIME_WAIT / 存档四条逐字未变；SMAPI 窗口退出后复制 `logs\run10d-smapi-window.txt`（77360 B / SHA256 `38282A5CEDFAAD0CA91614B9103029247D181B3C90DAF795FD0423CE815A7031` / `BYTE_IDENTICAL=True`）。世界改动只存内存、退出即回滚 ⇒ 样本 `(60,29)` 与 12 行满背包在存档里原样保留。
- **下一关**：等 task-194（analyzer 读 task-192 新字段）落地 ⇒ Lead 放行 **task-113（A′/B′，各 5 天）**。
