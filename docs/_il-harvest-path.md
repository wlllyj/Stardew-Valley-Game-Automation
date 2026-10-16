# 只读取证：`harvest`「熟了却摘不到」的完整链路（task-169）

> 证据面：`logs\longrun-runA-0732.jsonl`（847 行，0.7.32，fall 3–8）+ `logs\longrun-runB-0732.jsonl`（**662 行**，fall 9–10，同一格仍在重试）；**live 观测**：machine-runner 2026-10-17 04:42:34 / 04:42:54 两次 `observe?detail=full`（见 §0.5）
> 代码面：`brain\agentfarm\farmwork.py`、`brain\agentfarm\longrun.py`、`mod\AgentFarm.Bridge\{Skills,WorldSnapshot,FarmScan,Contracts}.cs` + 游戏 1.6.15 IL（`scratch\il-hv-1/2/3/4.txt`）
> 纪律：本文件只读取证，**没有**改动 `brain\`/`mod\`/`tools\`/`tests\`，取证期间**没有**碰游戏/桥（run B 由 machine-runner 独占）。

---

## 0. 判定摘要

| 可能 | 判定 | 关键证据 |
| --- | --- | --- |
| **判据错**（Mod 认为"熟了"，游戏认为"不可收"） | **【已证】唯一主因** | Mod 的"熟"=`Crop.fullyGrown`（`mod\AgentFarm.Bridge\WorldSnapshot.cs:636`；全场口径同样 `FarmScan.cs:285`），游戏的"可收"=`HoeDirt.readyForHarvest()`（`scratch\il-hv-3.txt:2-48`）+ `Crop.harvest` 自己的谓词（`scratch\il-hv-1.txt:1154-2193`）。两者差四类形态：①`fullyGrown && dayOfCurrentPhase > 0`（复收冷却期）②`currentPhase < phaseDays.Count-1` ③`dead` ④`forageCrop && whichForageCrop=="2"`。落在这四类的格，Mod **永远**报 `ripe=true`，游戏**永远**不给收。 |
| **入口错**（`checkAction` 不触发收获） | **【已证伪·对 Grab 类作物】** | `GameLocation.checkAction` 无距离/朝向判据，落到 `terrainFeatures[vec].performUseAction(vec)`（`scratch\il-hv-1.txt:814`，`IL_094E`）→ `HoeDirt.performUseAction`（`scratch\il-hv-2.txt:2-162`）：grab 分支在 `scratch\il-hv-2.txt:71`（`IL_00C7`）`callvirt Boolean harvest(Int32, Int32, HoeDirt, JunimoHarvester, Boolean)`（`this/(int)X/(int)Y/null/false`），失败则 `IL_00CC brfalse -> IL_01F1`。**这正是游戏自己的动作按钮通路**：`FIND|checkAction`（`scratch\il-hv-4.txt:1-50`）的调用者是 `Game1.tryToCheckAt` 的闭包与 `Game1.pressUseToolButton` 的两个闭包（`:45-47`），`Farm.checkAction` 只是 override 转基类（`:7`）。`Farmer.tryToHarvestHere` 在 1.6.15 **不存在**（`:54`），`tryToHarvestHere` 只存在于 `JunimoHarvester`（`:51-52`）。**但**：`HoeDirt.performUseAction` 的 `harvestMethod==Scythe` 分支（`IL_0129`-`IL_014B`）要求 `player.CurrentTool.isScythe()`，否则只弹红字（`IL_01D4` `didPlayerJustClickAtAll(true)`）⇒ 镰刀类作物的正确入口是**工具动作**（`HoeDirt.performToolAction`：`IL_00FE isScythe()` → `IL_0140` `HarvestMethod==Scythe \|\| ItemId=="66"` → `IL_01C7 crop.harvest(..., true)` → `destroyCrop(true)`，`scratch\il-hv-4.txt:136-240`），`interact` 永远摘不到它。 |
| **可达性错**（够不着却一直被当活） | **【已排除】**（Lead 2026-10-17 04:42 升级证据后排除） | live 观测两次（04:42:34 / 04:42:54）：**玩家就站在 `[60,28]`**（`[60,29]` 的正邻居），`[60,29] standable=true`，`[60,28]/[60,30]/[61,29]` 也都 `standable=true`；账本侧 `(60,29)` 的失败码**始终是 `failed`**，从未出现 `unreachable`/`tool_refused`。注：`frontier_clear`（A+B 合计 31 次、全部 `acted=true`、attempt 到 10，`scratch\_harvest_audit_u8.txt:197`）是**另一个**真瓶颈（别处够不着），与这一格无关。 |
| **回执谎报**（回执 ok 但世界没变） | **【已证】（第三次同类事故）** | 游戏拒绝时 `HoeDirt.performUseAction` 返回 `loc0`（`scratch\il-hv-2.txt:160-162`）/ `GameLocation.checkAction` 返回 `false`，但 `mod\AgentFarm.Bridge\Skills.cs:190-246` 的 `interact` 只写 `Ok = err == null`（`:233`）⇒ **没抛异常就报 ok**；`acted` 只落在 reason 文本里（`:238`）。账本**没有**回执原文字段（脑侧只在抛异常时记回执，`farmwork.py:2256`）。所幸脑侧用观测差分判失败（`:2260` / `:2274 code="failed"`）⇒ 这次失败**没被洗成成功**，但"回执 ok"仍是谎报，任何按回执记账的下游都会被骗。 |

**一句话**：`(60,29)` 是"**Mod 口径说熟了（`fullyGrown=true`）、游戏口径说不可收**"的格 —— 入口与可达性都已排除，根因在**判据**；细分到复收冷却 / 未熟 / 死苗 / 采集作物 / 镰刀类需要新字段（§4），修复方案见 §5。

---

## 0.5 这一格到底是什么（live 观测 + 字段语义）

machine-runner 2026-10-17 04:42:34 / 04:42:54 两次 `observe?detail=full`（两次一致）：

| 格 | 关键字段 |
| --- | --- |
| `[60,29]`（问题格） | `kind=dirt`、`feature=HoeDirt`、`tool=none`、`standable=true`、`actionable=true`、**`crop="270"`、`ripe=true`、`dead=false`、`watered=true`、`plantable=false`** |
| `[60,28]`（玩家所在） | `HoeDirt`、`standable=true`、`crop="262"`、`ripe=false`、`watered=true` |
| `[61,29]` / `[60,30]` | `HoeDirt`、`standable=true`、`crop="262"`、`ripe=false`、`watered=true` |
| `[59,29]` | `kind=tree`、`tool=axe`、`feature=Tree`、`standable=false` |

- `observe.farm`：`crops 102 / ripeCrops 1 / dryCrops 1 / deadCrops 0 / hoeDirt 149` ⇒ 守卫那句 `intent_vetoed{sleep: "农场口径还有 1 格熟作物（当前窗口没盖到，别处还有活），先去收"}` 指的就是这一格（口径出自 `FarmScan.cs:285`）。
- **字段语义已核实（本轮新证据）**：`Contracts.cs:516` 的注释写明 `Crop` = `Crop.indexOfHarvest`（**成熟后收获物的 object id**），`WorldSnapshot.cs:635` 取的就是 `cr.indexOfHarvest?.Value`；`Contracts.cs:519-520` / `WorldSnapshot.cs:636` 的 `Ripe` = `Crop.fullyGrown`。⇒ `crop="270"` / `"262"` 是**收获物 id**，不是作物种类键，也不代表"可收"。
- 【推断·外部知识，**未在本仓库验证**】香草 SDV 里 `(O)270` = 玉米（**可复收**）、`(O)262` = 小麦（**镰刀收**）。若成立，本格就落在"复收冷却"或"镰刀类被用 `checkAction` 摘"这两种子形态之一，两者根因相同（判据错）。本仓库 `logs/`、`docs/knowledge/` 里**没有** 270/262 的 id→名称记录（已 grep）⇒ 只作线索，不作结论。
- 决定性字段**一个都没被观测**：`harvestMethod`、`currentPhase`、`phaseDays.Count`、`dayOfCurrentPhase`、`fullyGrown` 原始值、`forageCrop`/`whichForageCrop`（§4）。

---

## 1. 判据链：'可收' 这个判断来自哪个字段

1. **目标从哪来（脑侧）**：`longrun.py:2688`、`:2773`、`:2826`、`:4543` 全是
   `[t for t, v in tmap.items() if v.get("crop") and v.get("ripe")]`，`tmap` = 观测窗口 `location.tiles[]`；`tile_view()` 取的就是窗口字段（`farmwork.py:1326-1333` 的键表含 `crop`/`ripe`）。
   ⇒ **决定"这格可收"的是窗口 `tiles[].ripe`，不是 `farm.ripeCrops`**（后者只喂守卫/理由，见 §3）。
2. **窗口 `ripe` 的生产者（Mod）**：`WorldSnapshot.cs:636` `t.Ripe = cr.fullyGrown != null && cr.fullyGrown.Value;`（`Contracts.cs:519-520` 注释亦写「`Crop.fullyGrown`」）。
3. **全场口径同错**：`FarmScan.cs:285` `if (crop.fullyGrown.Value) _acc.RipeCrops++;` ⇒ `farm.ripeCrops` 与窗口 `ripe` 是**同一个错口径**，两边不能互相印证。
4. **脑侧收获动作**：`farmwork.py:2229-2283 harvest()`：`:2243 if not (tv or {}).get("ripe"): skip「还没成熟」` → `_ensure_reachable`（`:2249`，封装 `:1434`）→ `interact(tile, timeout_ms=8000)`（`:2253`）→ 重新快照，`crop` 变空 ⇒ ok（`:2260`）；`crop` 还在 ⇒ `code="failed"` + reason「交互后作物还在（可能没摘到）」（`:2274`/`:2282`）。
5. **游戏口径（正解）**：`HoeDirt.readyForHarvest()`（`scratch\il-hv-3.txt:2-48`）=
   `crop != null && !(fullyGrown && dayOfCurrentPhase > 0) && currentPhase >= phaseDays.Count-1 && !dead && (forageCrop ? whichForageCrop != "2" : true)`。
   `HoeDirt.performUseAction` 里 grab 前的 `loc0` 用同一形状（`scratch\il-hv-2.txt:8-34`），`Crop.harvest` 自身再判一次（`scratch\il-hv-1.txt:1154-2193`）。
6. **入口的完整形状（本轮补齐）**：`Game1.tryToCheckAt` / `Game1.pressActionButton` → `GameLocation.checkAction(tile, viewport, who)` → `Farm.checkAction`（override → 基类）→ `terrainFeatures[tile].performUseAction(tile)` → `HoeDirt.performUseAction`；`FIND|checkAction` 共 49 个调用者，`Game1.pressUseToolButton` 的闭包也在其中（`scratch\il-hv-4.txt:3-5,45-47`）。⇒ 我们 `interact` 用的就是游戏自己的通路。

---

## 2. 账本事实（run A / run B 逐日）

`(60,29)` 是**唯一**被反复重试的 harvest 格（A+B 合计 **284 次**尝试、t=11.87→2215.4、跨 fall 3–10；详见 §7）。

| 日 | `day_end.stages[harvest]` | 首次→末次 t | `day_end.verified` / 关键 checks | `final.ripe` / `final.dead_crops` |
| --- | --- | --- | --- | --- |
| A fall 3 | 1 条：tiles=1 **ok=0 failed=1** | 39.99→39.99 | false；`no_hard_failures=false` | 1 / 1 |
| A fall 4 | 1 条：1/0/1 | 225.34→225.34 | false | 1 / 0 |
| A fall 5 | 1 条：1/0/1 | 420.04→420.04 | false | 1 / 0 |
| A fall 6 | 1 条：1/0/1 | 603.16→603.16 | false | 0 / 1 |
| A fall 7 | **31 条**：31/0/31 | 780.04→1468.88 | false；`no_unmet_stages=true`（但 failed>0） | 1 / 0 |
| A fall 8 | **44 条**：44/0/44 | 1508.18→2215.40 | false；`ended_by=sleep_failed`（`move_to (10,9)` timeout） | 1 / 0 |
| B fall 9 | **41 条**：41/0/41 | 11.87→596.91 | false（L409 t=613.21，`ended_by=sleep`，"night: 2200"） | 1 / 0 |

- 每条重试的形状都是：
  `stage_stop_named {stage:"harvest", cause:"incomplete", assigned:1, assigned_undone:1, tiles:[[60,29]], codes:["failed"]}`
  + `stage_exhausted {stage:"harvest", leftover:1, doomed:0, capped:1, tiles:[[60,29]]}`
  （例 run A `L83/L85`、`L461/L464`、`L845`；run B `L12/L20`、`L420`、`L448/L450`）。
- **run A 全账本 harvest：成功 0 步 / 失败 79 步**；run B 到取证时：成功 0 / 失败 41（`scratch\_harvest_audit_u8.txt:200-202`）。**没有一条 `ok`**，也没有任何一格的 harvest 成功记录。
- run B 除 `(60,29)` 外**没有第二个** harvest 目标格。

---

## 3. 它把守卫钉死了 ⇒ 直接污染「目标 2」

- `intent_vetoed {task:"sleep", reason:"农场口径还有 1 格熟作物（当前窗口没盖到，别处还有活），先去收"}`
  ：run A **11 条**（`L366/L407/L417…`）、run B **35 条**，另有 `recover_stamina` 被同一理由挡 **13 次**（`scratch\_harvest_audit_u8.txt:195-196`）⇒ 只要 `farm.ripeCrops>0`，守卫就不许睡/不许恢复，一直拖到 2200 硬上限。
- `review.work_reasons` 每天都带 `有 1 格作物熟了` + `今天早些时候还有 1 格没做完（跨片地，最近的是 [60, 29]）`（A+B 的 `review` 里「有 N 格作物熟了」共出现 **59** 次，`scratch\_harvest_audit_u8.txt:198`）。
- 后果：`checks.no_hard_failures`（要求 `failed_steps==0`）与 `stage_stop_named{cause:"incomplete"}` 造成的"分配未成事"在**有这格的每一天都恒假** ⇒ 「连续 VERIFIED」永远起不来；run A 6 天里 5 天 `ended_by=sleep` 但 `verified` 全是 false，fall 8 直接 `sleep_failed`。
- 所以：**不修它，目标 2 不可能达标**（不是"可能难"，是结构上恒假）。

---

## 4. 【无法判定】与证据缺口（缺失 ≠ 否定）

`(60,29)` 在账本里**只**出现在这两类事件里：`stage_stop_named`（146 条）+ `stage_exhausted`（138 条），合计 284 条（`scratch\_harvest_audit_u8.txt:188`）。这些事件提供的关于该格的**全部**字段只有 `tiles:[[60,29]]` + `codes:["failed"]`。

**live 观测（§0.5）已补上** `kind/feature/crop/ripe/watered/dead/standable`，但下列仍然缺：

- **决定性字段**：`harvestMethod` / `currentPhase` / `phaseDays` / `dayOfCurrentPhase` / `fullyGrown` 原始值 / `forageCrop`+`whichForageCrop` —— 没有它们就无法在"复收冷却 / 未熟 / 死苗 / 采集作物 / 镰刀类"之间定案；
- Mod `interact` 回执原文与 `checkAction` 返回的 `acted` —— 脑侧**只在抛异常时**才记回执（`farmwork.py:2256` `r.receipt = _receipt(exc)`），成功回执里的 `acted`（`Skills.cs:238` 的「返回 {acted}」）**没有任何落点**；
- 逐格窗口快照（run 只落 `*-baseline.json` 汇总，不落 `tiles[]`）。

⇒ 子形态**仍无法从账本区分**；但 live 观测 + IL 已把范围压到"判据错"这**一个根因**上（入口与可达性都排除）。

可用的间接旁证（只减弱"未熟/死苗"两支，不能定案）：
- A fall 7/8 `final.dead_crops=0` 而 `final.ripe=1`；live 观测 `dead=false`；
- `dead_crops_summary` 的 `tiles` 是**空列表**（只给计数、不给坐标，`L32/L64/L96/L126`）；
- 这一格跨 **8 个游戏日**恒 `ripe=true`（fall 3→10，284 次尝试）⇒ **不是"还没熟"**（真未熟会随时间变熟）；复收冷却也不会连跨 8 天（复收周期 4 天）⇒ 若子形态是"复收冷却"，则说明 `dayOfCurrentPhase` 在从未成功收获的情况下**不再归零**（可检验的预测：`dayOfCurrentPhase` 会大于 Regrowth 值）。

---

## 5. 建议（只提案，未改任何生产代码）

1. **Mod（治本）**：
   - 把"可收"口径换成游戏口径：`WorldSnapshot.cs:636` 与 `FarmScan.cs:285` 改用 `HoeDirt.readyForHarvest()`（或等价：`fullyGrown && dayOfCurrentPhase == 0 && currentPhase >= phaseDays.Count-1 && !dead && !(forageCrop && whichForageCrop=="2")`）；`fullyGrown` 若要保留就**另开字段**，不要复用 `ripe`。
   - `CropView` 增：`harvestMethod`（Grab/Scythe）、`currentPhase`、`phaseDays`、`dayOfCurrentPhase`、`forageCrop`/`whichForageCrop` —— 这五个是子形态的唯一判别量（也解开 §4 的【无法判定】）。
   - `interact`（`Skills.cs:226-238`）：`checkAction` 返回 `false`（`acted==false`）时**不许报 ok** —— 至少 `Status="failed"`/`code="nothing_happened"`，并把 `acted` 写成机器可读字段，否则"回执谎报"还会再犯第四次。
2. **脑（止血）**：harvest 目标改用 Mod 的 `readyForHarvest` 口径；对"同一格连续 N 次 failed"设上限（`proven_inert` 式记账），且**不许**让它把 sleep/recover 守卫钉一整天（把"这一格今天摘不到"降级为"今天不试"）。
3. **若子形态是镰刀类作物**：入口要换成**工具动作** —— `use_tool` 带镰刀走 `HoeDirt.performToolAction` 的 `isScythe()` 分支；但按 task-3 的结论，`Game1.pressUseToolButton` 对 `MeleeWeapon` 要求 `didPlayerJustLeftClick(true)` 真实输入边沿 ⇒ 这条**依赖那次的输入边沿方案**，不能在脑侧单独解决。
4. **验收口径**：新增判据「`farm.ripeCrops>0` 但连续 2 天无法收获 ⇒ 必须有一条可定位的 cap 记录，且当天 sleep guard 不被它 veto」。
5. **同格真机验证（Lead 指定 `[60,29]` 保留为样本）**：修好后应同时满足 ①该格 `ripe`/`readyForHarvest` 为 **false**（或显示 `harvestMethod=Scythe` 并走工具路径）②harvest 阶段不再分配它 ③`intent_vetoed{sleep}` 不再出现 ④若某天它真的可收，`interact` 后的观测里 `crop` 必须消失；回执只在 `acted==true` 时才允许 `ok`。

---

## 6. 复现命令（全部只读）

```
python scratch\_harvest_audit.py                 # run A+run B：逐格 / 逐日 / 判据链 / 缺口 / 守卫与开路
python scratch\_t169_tile_mentions.py 60 29      # 该格出现在哪些事件里
python tools\_tmp_conv.py <utf16文件> <utf8文件>  # pwsh 重定向产物是 UTF-16LE，读之前先转码
```

IL 转储（`tools\il-probe`，游戏目录 `D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley`）：

- `scratch\il-hv-1.txt`：`GameLocation.checkAction(Location,Rectangle,Farmer)` + `Crop.harvest(Int32,Int32,HoeDirt,JunimoHarvester,Boolean)`
- `scratch\il-hv-2.txt`：`HoeDirt.performUseAction(Vector2)` + `TerrainFeature.performUseAction` 基类
- `scratch\il-hv-3.txt`：`HoeDirt.readyForHarvest()`
- `scratch\il-hv-4.txt`：`FIND|checkAction`（49 调用者）+ `FIND|tryToHarvestHere` + `HoeDirt.performToolAction(Tool,Int32,Vector2)`

---

## 7. 按格聚合表（run A + run B，`scratch\_harvest_audit.py` → `scratch\_harvest_audit_u8.txt`）

**① 逐格**

| 格 | 账本 | 尝试次数 | 首次→末次 t | 出现的日 | code 分布 | 出现在哪些事件 |
| --- | --- | --- | --- | --- | --- | --- |
| `(60,29)` | A + B | **284** | 11.87 → 2215.4 | A fall 3/4/5/6/7/8 + B fall 9/10 | `incomplete:146`、`harvest:138` | 仅 `stage_stop_named`(146) + `stage_exhausted`(138) |

**② 账本汇总**

| 账本 | harvest 成功 | harvest 失败 | `day_end` 天数 | `intent_vetoed{sleep}` | `frontier_clear`（全 acted=true） |
| --- | --- | --- | --- | --- | --- |
| A（847 行） | **0** | **79** | 6 | 11 | 15（attempt→9） |
| B（662 行，取证时仍在跑） | **0** | **41** | 1 | 35（另 `recover_stamina` 13） | 16（attempt→10） |

**③ 判据链抽样**（`_harvest_audit_u8.txt` §3a/§3c）
- harvest 的 `intent_verdict`：先 `unknown`（作业区离玩家 16–23 格 ⇒ 观测看不见），一旦看见就恒 `keep targets=1`，全程再无 `cancel`；A 里 fall 7 连续 31 轮、fall 8 连续 44 轮都是 `keep`。
- `review.work_reasons` 抽样（`AL179`/`AL189`/`AL200`…）：`['有 1 格作物熟了', '今天早些时候还有 1 格没做完（跨片地，最近的是 [60, 29]）']`。

**④ 其他**
- 除 `(60,29)` 外，harvest 目标格为 **0**；`(60,29)` 之外没有任何 harvest 成功记录。
- `frontier_clear` 31 次的 `tiles` 全表见 `_harvest_audit_u8.txt:197`（attempt_max=10），属"别处够不着"，与本格无关。
