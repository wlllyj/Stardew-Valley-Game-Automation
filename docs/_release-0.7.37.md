# 0.7.37 发布计划 — 收获证据面的三条残留收口（R7/R8/C2-a）+ 测试编码护栏

> 状态：**草稿 → 已开工（brain/mod 已解冻）**。A′（task-113）被 Lead **提前叫停**：该臂被「背包满 ⇒ `harvest` 全线被拒」支配（45 条同句失败 / `harvest_gave_up` 59 次 / `no_hard_failures=false` / 两天 `stuck`），**不作验收证据、L0–L5 不判**（`docs/_runA3-0736-evidence.md`）。no B′ run. 本批据此**扩容**：新增两张 P0（**task-198** 背包满/腾格收敛、**task-199** 窗口外熟作物坐标）+ 独立对抗验收 **task-200**。
> 前置：`docs/_release-0.7.36.md`（0.7.36 冻结装机 + task-191 真机复测 PASS + `§5.5`）；`docs/_run10-harvest-verify-0736.md`（task-191 真机取证，R7/R8 出处）；`logs\longrun-runA3-0736.jsonl`（A′ 账本）。

## 0. 为什么有这一版

0.7.36 把收获证据面收到「判据落在世界证据上、回执只作线索」，task-191 真机四条判据全绿。真机同时暴露三条**口径外**的残留（不阻塞 A′/B′，但会影响「回执可信度」与「附带效果记账」的长期可信）：

- **R7（Mod）**：原始 `use_tool(tool="scythe")` 打在不 `ready` 的目标格上 ⇒ Mod 回执 `acted=true` / `actedEvidence="readyCrops"`，reason 却谎称该格「上面已经没有东西了」（实际仍在），真实效果是**连带清掉 4 格**（`crops 102→98`、`readyCrops 101→97`、`emptyDirt 51→55`，含未成熟作物）。⇒ `actedEvidence` 是**聚合口径**，与「目标格」写在同一份回执里会误导；原始技能无脑侧守卫时是破坏性的。
- **R8（brain）**：镰刀收割时顺带割草 ⇒ 背包 `Moss +1` 未进 `loot` / `affected_tiles`（脑侧**没多报**，是**没记账**）；机检脚本按「全量背包差」口径会误判 FAIL。
- **C2-a（brain，task-190 骨架复现）**：有格子级证据时白名单取整份 `gained`，同一次动作顺手进包的无关注 qid 仍会进白名单。
- **工程侧（tests）**：全量单测**依赖 `PYTHONUTF8`** —— 不带时 `test_longrun.TestTask182ClumpRulesBehaviour::test_csharp_rules_self_test_passes` 假红（C# 自检的 UTF-8 输出被按 cp1252 解码）。

### 追加：A′ 真机暴露出两张 P0（本批因此扩为 6 卡）

- **task-198（brain P0）**：`outcome[harvest]` **45 条**失败全是 `背包满（空槽 = inventoryCount 容量 − inventory[] 行数 = 0）⇒ 先出货/整理背包再来收`；`harvest_gave_up` 59 次（每格试满 `limit=2`）；`stage_stop_named{stage:"harvest", assigned:12, assigned_undone:12, codes:["failed"]}` ⇒ `checks.no_hard_failures=false` ⇒ **整天不可能 VERIFIED**。而 `sell`/`ship` 其实在跑（16 条 sell、次日钱结算到 2997g、t=188 买到 10 个 `(O)483`）⇒ **不是不会卖，是没有「腾格优先于收割」的收敛回路**；同时 `clear`/`till`/`water` 的掉落持续把背包重新填满。
- **task-199（Mod+brain）**：day13 `ended_reason = stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：农场口径还有 8 格熟作物（当前窗口没盖到，别处还有活），先去收）` ⇒ `farm.readyCrops` 是**农场级**计数，脑侧目标池来自**窗口** `tiles[]`（400 格、玩家中心、截断）⇒ 窗口外熟作物**看不到也走不到**，守卫却拿它当"还有活"⇒ 空转 `stuck`。同类先例：task-50 已给干作物补了 `farm.dryTiles` 坐标，熟作物缺同款。

## 1. 本批卡片（入版范围）

| 卡 | 侧 | 内容 | 验收 |
|---|---|---|---|
| **task-198** | brain（P0） | 背包满 ⇒ `harvest` 全线被拒：无空格归**阻塞类**（`no_slot`，不封格/不吃 `gave_up` 上限/不计 failed）+ 守卫口径 + **腾格优先的收敛回路**（`slot_relief`，有界、每轮至少腾 1 格，腾不出 ⇒ 如实 `inventory_blocked`）+ 掉落预算 | ≥6 单测 + ≥3 变异（报实测杀数）+ 全量 0 红（带 `PYTHONUTF8=1`）+ 用 A′ 真实序列的离线推演 |
| **task-199** | Mod+brain | `farm.readyTiles` 坐标（与 `readyCrops` **同源同扫描**、上限 64、按 (y,x) 排序、截断标志）⇒ 窗口外熟作物复用 `water_far` walker 一族去收；走不到如实 `ready_far_blocked`、不许空转 `stuck`；缺字段 fail-closed | Mod：`dotnet build` 0/0 + C# 自检 ≥2 断言；brain：≥5 单测 + ≥3 变异 |
| **task-195** | Mod | `actedEvidence` 必须对得上**目标格**（或明确标注聚合来源）；原始 `use_tool` 在目标格 `ready!=true` 时不得静默连带（fail-closed 或如实报连带影响） | `dotnet build` 0 警 0 错 + C# 自检 ≥3 条新断言（目标格不可收时不得声称已空 / 连带影响必须入回执 / 证据能区分目标格与聚合）+ ≥3 变异 |
| **task-196** | brain | 附带掉落与目标格掉落**分栏记账**（`loot` / `collateral_loot`）+ `affected_tiles` 如实 + 口径说明（全量背包差 ≠ 白名单逐 qid 差） | ≥4 单测 + ≥2 变异 + 口径写进 `docs/_run10-criteria.md` 或 `docs/_analyze-longrun-caliber.md` |
| **task-193** | analyzer | 白名单归因收紧（C2-a）+（若 task-196 需要）新字段入桶；旧账本判决与计数不得变化 | 单文件 OK + 全量 OK + 六账本 rc/红数/#无法判定**并排**给旧版读数 |
| **task-197** | tests | 消除子进程抓 stdout 的编码依赖（显式 `encoding="utf-8"` 或 ASCII 标记断言）+ 「不带 PYTHONUTF8 也绿」回归护栏 | 两种环境（带/不带 `PYTHONUTF8`）都 `Ran N / OK`，读数原文贴进交付 |
| **task-200** | deputy-lead | 本批**独立对抗验收**（6 卡逐卡 + 变异自报 vs 实测两列 + 是否可冻结；只写 `docs/_review-0.7.37.md` + `scratch/`） | PASS / PASS-WITH-NITS / FAIL + 可冻结结论 |

**实施顺序（单写者 dev-coder 串行）**：`198 → 199 → 195 → 196 → 197`；`193`（log-analyst）可并行；`200`（deputy-lead）在三卡以上交付后可滚动开始，最终冻结前必须完成。

## 2. 冻结九步（Lead 独占，链条冻结后一次做完）

1. `tools\_note-0737.txt`（**首串必须 `v0.7.37`**，列本批 Mod 侧改动）。
2. `python tools\_bump-mod-version.py 0.7.37 --note-file tools\_note-0737.txt` ⇒ manifest `0.7.36 → 0.7.37`（用 `json.load` 复核，别信最后那行 print：cp1252 下它会 UnicodeEncodeError 但文件已写）。
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.37"`（注释补本批条目、上一版转历史）。
4. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警 0 错**；记 dll/manifest 的 size 与 mtime。
5. `git add -A && git commit`（冻结提交；**先提交再 check-release**）。
6. `python tools\check-release.py --expect 0.7.37` ⇒ 六项全绿（含 `Ran N tests`、树干净）。
7. `python tools\deploy-mod.py --no-quit` ⇒ 桥 `modVersion=0.7.37`、自动读档。
8. `python -m agentfarm goto Farm` ⇒ ok。
9. `python tools\preflight.py --expect 0.7.37 --save-baseline logs\run10e-baseline.json` ⇒ 四项全绿；把五文件 SHA 前 16 位发给下一张真机卡。

## 3. 判据

- **task-195 真机**：在 `(60,29)/(60,30)` 类格上，`use_tool` 回执的证据必须能追溯到**目标格**；对未成熟/不可收格发原始 `use_tool` ⇒ 要么被拒，要么回执如实写连带影响（受影响格清单），**不得**出现「目标格没变却说它已空」。
- **task-196**：镰刀顺带割草 ⇒ `collateral_loot` 记录 `Moss +1`；`loot` 仍只含目标格白名单项；口径不一致**不判失败**。
- **task-193**：六账本判决/计数与旧版并排一致（`#无法判定` 允许因修 bug 下降，需给出两列）；作物白名单 / 材料白名单**两通道分列**，`(O)Moss` 类连带掉落不得进作物白名单。
- **task-197**：带与不带 `PYTHONUTF8` 均全绿。
- **task-198（A′ 原型复现，冻结硬判据）**：用 `logs\longrun-runA3-0736.jsonl` 的真实形态构造假世界（满包 + `(63,18)` 反复 no_slot；day13 的 `stuck:…守卫仍说还有活：农场口径还有 8 格熟作物`）⇒ post 树必须出现「`slot_relief` 或 `inventory_blocked`」，且**不得出现** `stuck:…守卫仍说还有活`；`checks.no_hard_failures` 不得因 `no_slot` 为 false。
- **task-199（窗口外熟作物）**：`readyTiles` 与 `readyCrops` 同源一致（伪造不一致必须被拦）；走不到 ⇒ `ready_far_blocked` 且**不空转**；缺字段 ⇒ fail-closed 老行为。

## 4. 已知限制 / 风险

- 本批**不碰** `checks` 键集、不碰 `_leftover` / `JUSTIFIED_END_REASONS` 语义（0.7.36 的边界继续有效）。
- `acted` 仍是「跨观测证据」的推断，不是游戏的真值；任何新字段都要 **fail-closed**（缺 ⇒ 不采信）。
- **本批现在是 A″/B″ 的前置**（不再"跑批后加固"）：0.7.37 冻结装机后，才在 0.7.37 上跑 A″/B″（`logs\longrun-runA4-0737.jsonl` / `runB4-0737.jsonl`，各 5 天）。B′（0.7.36）**不跑**。
- `task-198` 与 `task-199` 都改 `brain/agentfarm` ⇒ 必须串行（198 先合）；`task-195`（Mod）与 199 的 Mod 半同批，注意别让 `Contracts.cs`/`FarmScan.cs` 两卡互相覆盖。
- 真机侧：A′ 被叫停后**游戏保活**（存档留在秋 12 清晨、样本 `(60,29)` 与 12 行满背包原样）；修复后的真机验证（slot 收敛、`readyTiles`）放到 A″/B″ 一起看。

## 5. 执行记录（待填）

- 5.0 A′ 起跑与叫停（本批触发因）：0.7.36 上 A′ 于 `2026-10-17T08:37:40` 起跑（PID 14296，五文件指纹 5/5 与 0.7.36 冻结一致：`longrun C326DD1E1358EA15` / `farmwork FA6BD05CCAB9DF25` / `bridge 968D1D227A293B1A` / `dll D6699BD057C51CE7` / `manifest 6578C42574237AA8`）；跑至 fall 14 被 Lead 叫停（只 `Stop-Process` 脑、游戏保活、SMAPI 未冻、无 B′）；证据 `docs\_runA3-0736-evidence.md`。
- 5.1 链条（冻结前）：待填
- 5.2 冻结（提交 hash）：待填
- 5.3 装机与基线：待填
- 5.4 指纹与移交：待填
