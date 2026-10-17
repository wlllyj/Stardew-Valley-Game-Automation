# 0.7.37 发布计划 — 背包阻塞/窗口外熟作物收口 + 显式对话应答 + 工具升级闭环

> 状态：**批内 4 卡已交付并亲核（192 / 198 / 199 / 208），task-205 在制，task-206 待 task-205**。冻结时机 = 205 落地 + deputy（task-200）对冻结树做完本批独立验收之后，一次冻结装机。
> 前置：`docs/_release-0.7.36.md`（0.7.36 冻结装机 + task-191 真机复测）；`docs/_runA3-0736-evidence.md`（A′ 叫停证据）；`docs/_il-tool-upgrade.md`（铁匠铺链 IL 定案）；`docs/_run10-material-scan.md`（真机材料盘点）；`docs/_upgrade-protocol.md`（真机升级验收协议）。
> 背景：A′（task-113）被 Lead **提前叫停**——该臂被「背包满 ⇒ `harvest` 全线被拒」支配（45 条同句失败 / `harvest_gave_up` 59 次 / `no_hard_failures=false` / 两天 `stuck`），**不作验收证据、L0–L5 不判、B′ 不跑**。本批据此收口，并叠加用户当场提的优先级（`User said (m18271)`「赶紧做工具升级吧」）。

## 0. 为什么有这一版

四件事合流：

1. **A′ 真机暴露的两张 P0**（task-198 / 199）：
   - `no_slot`（背包满）被当成硬失败 ⇒ 整天不可能 VERIFIED；真正缺的是「腾格优先于收割」的收敛回路与诚实收工（`inventory_blocked`）。
   - `farm.readyCrops` 是农场级计数，而脑侧目标池来自 400 格窗口 ⇒ 窗口外熟作物看不到也走不到，守卫却拿它当「还有活」⇒ 空转 `stuck`（A′ day13 原文）。
2. **task-192**：认输区「释放」后当日记账不归零 ⇒ 雨天「先认输→浇好→释放→其余活做完」的诚实日会被工具误判 needs_review。
3. **task-208**：`dismiss_modal` 只能按「Yes/第一项」应答，无法**显式指定选项** ⇒ 铁匠铺升级、职业选择这类必须选特定项的对话无法自动化。新增 `answerIndex`/`answerText`，互斥、fail-closed、绝不回退自动 Yes。
4. **task-205（工具升级闭环）**：IL 已定案（铁匠铺 `ClintUpgrade`，`tryToPurchaseItem` 私有需反射；钱+材料先扣、`actionWhenPurchased` 才换工具 ⇒ 必须自检 `toolBeingUpgraded==null`）。真机材料盘点：铜锭 0 / 铜矿 0 / 煤 0 / 熔炉 0 / 配方无 Furnace ⇒ 升级被**材料链**卡住（熔炉链 = task-210 + IL task-211），故 205 先交付**代码闭环**，真机成功验收按 `docs/_upgrade-protocol.md` 在材料到位后执行。

## 1. 本批卡片（入版范围）

| 卡 | 侧 | 内容 | 状态 |
|---|---|---|---|
| **task-192** | brain | 释放认输区同步扣当日记账；`day_end.scope_shed*` = 日终末态；累计量 `shed_ever` 跨释放保留（34% 上界成立） | ✅ `1246cdd`（Lead 亲核 965 OK；变异 5/3/3） |
| **task-198** | brain（P0） | `no_slot` 归**阻塞类**（六处排除面：`failed_any`/`_count_attempts`/`_note_harvest_gave_up`/`_stage_undone_cause`/`_mark_blocked`/守卫 `bag_blocked`）+ `SLOT_RESERVE` 低水位 + `SLOT_RELIEF_MAX=3` 腾格收敛 + 诚实 `inventory_blocked` 收尾（`failed_steps=0`/`verified=False`/不在 `JUSTIFIED_END_REASONS`） | ✅ `62e9089`（Lead 亲核 484 OK 定向；全量仅 2 条 analyzer 漂移→task-202 已修） |
| **task-199** | Mod+brain | `farm.readyTiles`（与 `readyCrops` 同源同扫描、上限 64、按 (y,x)、截断标志、三态可辨）+ 脑侧 `ready_far*` 走位族收窗口外熟格（`READY_FAR_MAX_TRIES=2`、走不到如实 `ready_far_blocked`、`gave_up_ready` 不进 `JUSTIFIED_END_REASONS`） | ✅ `edcd581`（Lead 亲核全量 1005 OK；变异 6/1/1/1） |
| **task-202** | analyzer | 收 task-198 的 `inventory_blocked`/`slot_relief`/`slot_relief_noted` + task-199 的 `ready_far*` 五名；旧账本判决/计数不变 | ✅ `f2e72e3`（全量 992 OK 归零） |
| **task-204** | docs（IL） | 铁匠铺升级链 IL 定案（入口/选工具/扣钱/回执/取回 + `GetShopStock` 公共接口） | ✅ `d6d55e2` |
| **task-208** | Mod | `dismiss_modal` 显式应答：`answerIndex`/`answerText` 互斥；未设 ⇒ 老行为不变；越界/不匹配 ⇒ `choice_not_found`（附选项清单）、多义 ⇒ `choice_ambiguous`、无提问 ⇒ `no_question`；绝不回退自动 Yes；`chosenAnswer` 可审计；不接管 ShippingMenu/存档菜单 | ✅ `dadd356`（C# 自检 38 断言；Lead 亲核） |
| **task-205** | Mod+brain | `upgrade_tool`：开店→读价（`GetShopStock`/`GetToolUpgradeData`）→硬自检（`toolBeingUpgraded==null` && 钱够 && 材料够 && 非 readOnly）→反射购买→钱差判据；脑侧策略（每天≤1 次、在浇水/收获之后、拾取工具优先、2 天在飞如实跳过）+ fail-closed 码 | 🛠 在制 |
| **task-206** | deputy-lead | task-205 独立对抗验收（≥8 作弊通道 + 变异自报 vs 实测两列） | ⏸ 待 205 |

**移出本批（→ 0.7.39）**：task-195（`actedEvidence` 目标格绑定）、task-196（连带掉落分栏）、task-193（白名单两通道）、task-197（测试编码护栏）。
**下一批（→ 0.7.38）**：task-210（机器链 craft/place/feed/collect）、task-211（IL 定案，进行中）、task-200 的冻结树正式验收。

## 2. 冻结九步（Lead 独占，链条冻结后一次做完）

1. `tools\_note-0737.txt`（**首串必须 `v0.7.37`**，列本批 Mod 侧：199 `readyTiles`、208 显式应答、205 `upgrade_tool`）。
2. `python tools\_bump-mod-version.py 0.7.37 --note-file tools\_note-0737.txt` ⇒ manifest `0.7.36 → 0.7.37`（用 `json.load` 复核；cp1252 下最后一行 print 会 UnicodeEncodeError 但文件已写）。
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.37"`（注释补本批条目、上一版转历史）。
4. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警 0 错**；记 dll/manifest size 与 mtime。
5. `git add -A && git commit`（冻结提交；**先提交再 check-release**）。
6. `python tools\check-release.py --expect 0.7.37` ⇒ 六项全绿（含 `Ran N tests`、树干净）。
7. `python tools\deploy-mod.py --no-quit` ⇒ 桥 `modVersion=0.7.37`、自动读档。
8. `python -m agentfarm goto Farm` ⇒ ok。
9. `python tools\preflight.py --expect 0.7.37 --save-baseline logs\run10e-baseline.json` ⇒ 四项全绿；把五文件 SHA 前 16 位发给下一张真机卡。

## 3. 判据

- **task-198（A′ 原型复现，冻结硬判据）**：用 `logs\longrun-runA3-0736.jsonl` 真实形态构造假世界（满包 + 反复 `no_slot`；day13 的 `stuck:…守卫仍说还有活：农场口径还有 8 格熟作物`）⇒ post 树必须出现 `slot_relief` 或 `inventory_blocked`，**不得**出现 `stuck:…守卫仍说还有活`；`no_hard_failures` 不得因 `no_slot` 为 false。
- **task-199**：`readyTiles` 与 `readyCrops` 同源一致（伪造不一致必须被拦）；走不到 ⇒ `ready_far_blocked` 且不空转；缺字段 ⇒ fail-closed 老行为。
- **task-208**：显式应答必须真的选中指定项（`chosenAnswer` 与选项一致）；不匹配/越界不得乱选；不设参数时行为与 0.7.36 完全一致。
- **task-205**：`already_upgrading`/`no_money`/`no_trade_item`/`tool_not_offered`/`shop_unavailable`/`read_only`/`no_slot` 全部 fail-closed，且**绝不重复购买**；真机成功验收按 `docs/_upgrade-protocol.md`（§2 预算 6275g、§6 防损四自查）。
- **task-192**：释放后日终记账 = 仍在认输的格数；「释放 + verified=true」不再判 problem；`_leftover` 语义一字不改。

## 4. 已知限制 / 风险

- 本批**不碰** `checks` 键集、不碰 `_leftover` / `JUSTIFIED_END_REASONS` 语义。
- `acted` 是跨观测推断，不是游戏真值；任何新字段都要 fail-closed。
- task-198 与 task-199/205 都改 `brain/agentfarm` ⇒ 单写者串行；`Contracts.cs` 被 199/208/205 三卡先后改过，冻结前必须整体 build 复核。
- 工具升级的真机成功路径**被材料链卡住**：0 铜锭、无熔炉、无 Furnace 配方 ⇒ 本批只交付能力，真机验收等 task-210 机器链（熔炉→铜锭）到位。
- 升级后 2 天内该工具不可用 ⇒ 日循环必须如实跳过依赖它的活（205 的脑侧策略已含）。

## 5. 执行记录

- 5.0 A′ 起跑与叫停（本批触发因）：0.7.36 上 `2026-10-17T08:37:40` 起跑（PID 14296，五文件指纹 5/5 与 0.7.36 冻结一致：`longrun C326DD1E1358EA15` / `farmwork FA6BD05CCAB9DF25` / `bridge 968D1D227A293B1A` / `dll D6699BD057C51CE7` / `manifest 6578C42574237AA8`），跑至 fall 14 被叫停（只 `Stop-Process` 脑、游戏保活、SMAPI 未冻、无 B′）；证据 `docs\_runA3-0736-evidence.md`。
- 5.1 链条（冻结前）：待填（task-205 / 206）
- 5.2 冻结（提交 hash）：待填
- 5.3 装机与基线：待填
- 5.4 指纹与移交：待填
