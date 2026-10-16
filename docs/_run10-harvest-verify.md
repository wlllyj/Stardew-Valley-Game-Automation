# run10 同格 harvest 定点验证 —— 0.7.33 装机后对 `(60,29)` 做**一次** harvest

> task-173（machine-runner）。**结论：FAIL**（判据 (a)/(b) **都不成立**），且**存在两个未排除的混杂因素**，故本文件不把 FAIL 归因于"判据纠正无效"这一句话 —— 见 §7。
> 纪律：验收只看 `observe?detail=full` 差分（回执只作诊断）；本卡只做**一次** harvest，未起长跑、未改任何源码、未 deploy。

---

## §1 环境与版本（动手前）

| 项 | 读数 |
|---|---|
| 游戏进程 | `StardewModdingAPI` PID **13248**（StartTime `2026-10-17 05:37:16`） |
| `bridge.json` | `pid 13248` / `modVersion **0.7.33**` / `port 17890` / `gameVersion 1.6.15` / `smapiVersion 4.5.2`（mtime `2026-10-17T05:40:24.046`） |
| `tools\preflight.py --expect 0.7.33` | **exit 0 ✅ 可以起跑**：秋12日 `06:50→09:40`、`Farm`、`isOutdoorFarm true`、`hasSaveLoaded true`、`activeMenu null`/`isModal false`、`worldAdvancing true`、`crops 102`、`dryCrops 0`、`waterLeft 27`、`farmingLevel 1`、`money 0`、`stamina 247.2` |
| 前置走位 | `python -m agentfarm move 60 28 --no-focus --timeout-ms 40000` ⇒ `move_to status=ok 3861ms worldSeq 33→51`、**到达 (60,28)**（样本格必须进观测窗口：窗口是玩家中心 400 格） |
| 脚本 | `scratch\run10-tile6029-verify.py`（`py_compile -W error::SyntaxWarning` exit 0；只读 + 一次 `FarmWorker.harvest((60,29))`；用薄代理截获 Mod 原始回执） |

---

## §2 动手前基线（`scratch\run10-tile6029-before.json`，full 观测原文）

`clock = {year 1, season fall, day 12, timeOfDay 1000, weather rain}`；`ui = {activeMenu null, isModal false, eventUp false, professionsToChoose null}`；`player.tile [60,28]`、`stamina 247.20007`、`money 0`、`farmingLevel 1`。

**farm 计数（原文）**：`{"crops": 102, "readyCrops": 102, "ripeCrops": 1, "unwateredCrops": 2, "dryCrops": 0, "deadCrops": 0, "hoeDirt": 153, "emptyDirt": 51, "complete": true, "scanSeq": 51}`
⇒ ⚠ **`readyCrops == crops == 102`**（下面 §4 的 (60,28) 解释了为什么）。

**样本格 `(60,29)` 原文（`location.tiles[]` 里那一项，逐字）**：

```json
{"tile": [60, 29], "kind": "dirt", "tool": "none", "feature": "HoeDirt", "standable": true,
 "actionable": true, "crop": "270", "ripe": true, "dead": false, "ready": true,
 "fullyGrown": true, "currentPhase": 5, "phaseDays": 6, "dayOfCurrentPhase": -9,
 "forageCrop": false, "regrowsAfterHarvest": true, "watered": true, "plantable": false}
```

**`harvestMethod` 键完全不存在**（不是 `null`，是**没有这个键**）⇒ 与 `Contracts.cs` 声明（`[JsonPropertyName("harvestMethod")] public string HarvestMethod`）和 `CropMeta.Fill`（`t.HarvestMethod = HarvestMethodOf(crop)`）不符 ⇒ `CropMeta.HarvestMethodOf` 在本机返回了 `null`（`ReadMember(crop,"HarvestMethod")` 取不到——它在 1.6.15 是**非 public**，见 `docs\_il-harvest-path.md`）。
⇒ 脑侧 `harvest_tool(tv)` 实测 = `None` ⇒ **永远走 `interact`，走不到工具路径**。

**四邻（同一份观测）**：

| 格 | kind/feature | crop | ripe | **ready** | fullyGrown | currentPhase/phaseDays | dayOfCurrentPhase | dead | watered | standable |
|---|---|---|---|---|---|---|---|---|---|---|
| `(60,29)` 样本 | dirt/HoeDirt | **270** | **true** | **true** | true | 5 / 6 | -9 | false | true | true |
| `(60,28)` 玩家所在 | dirt/HoeDirt | 262 | false | **true** ⚠ | **false** | 4 / 5 | 7 | false | true | true |
| `(61,29)` | dirt/HoeDirt | 262 | false | **true** ⚠ | false | 4 / 5 | 9 | false | true | true |
| `(60,30)` | dirt/HoeDirt | 262 | false | **true** ⚠ | false | 4 / 5 | 9 | false | true | true |
| `(59,29)` | tree/Tree | — | false | （缺键） | — | — | — | false | false | **false** |

⚠ **三格 `ready=true` 但 `fullyGrown=false`/`ripe=false`** ⇒ `ready` 判据与"熟"不一致（这正是 `readyCrops==crops==102` 的来源）。

**脑侧判据（同一份观测）**：`tile_ready((60,29)) = True`、`_ready_note = ''`、`harvest_tool = None`。

**背包（12 格全满，`player.inventoryCount = 12`）**：
`(T)Axe×1 / (T)Hoe×1 / (T)WateringCan×1 / (T)Pickaxe×1 / (W)47 Scythe×1 / (O)535 Geode×3 / (O)262 Wheat×3 / (O)178 Hay×17 / (O)390 Stone×3 / (O)483 Wheat Seeds×1 / (O)Moss×35 / (O)262 Wheat×37`
⇒ ⚠ **0 个空格**（run8 的 `no_inventory_space` 病灶形态，task-102 的领域）。

**存档（动手前）**：`Wahaha_450799035` **4310486 B / `2026-10-17 05:04:35.296`**；`SaveGameInfo` **28707 B / `05:04:35.298`**。
**SMAPI（动手前）**：`lines 424` / `newday 0` / `save_called(原始) 1 / (修正后) 0`。

---

## §3 只做一次 `harvest((60,29))`

`StepResult`：`action=harvest` `tile=(60,29)` **`ok=False`** `code=failed` `status=''` `proven_inert=False` `env_block=False` `inconclusive=False`，用时 **0.2s**。

`reason`（原文）：
> 游戏口径可收但作物还在（交互/挥镰后没摘到）；Mod status=ok；ok: 已在 (60,29) 调游戏自己的 checkAction（返回 true：这一格有可执行的动作/门）。若这一格是门/建筑入口，传送由游戏自己发起（有淡出期，**以 observe 到的地点为准**）

**Mod 原始回执（代理截获，逐字）**：

```json
{"interact": {"acted": true, "elapsedMs": 0, "ok": true, "reachedLocation": "Farm",
 "reason": "已在 (60,29) 调游戏自己的 checkAction（返回 true：这一格有可执行的动作/门）。…",
 "schema": "agentfarm-exec/2", "skill": "interact", "status": "ok", "uiOpened": false,
 "worldResumed": true, "worldSeqAfter": 51, "worldSeqBefore": 51}}
```

⇒ 回执自述 `acted=true`/`ok=true`/`status=ok`，但 **`worldSeqBefore == worldSeqAfter == 51`**（世界序列一动没动）。

---

## §4 动手后观测（`scratch\run10-tile6029-after.json`）与逐字段差分

**farm**：`{"crops": 102, "readyCrops": 102, "ripeCrops": 1, "unwateredCrops": 2, "dryCrops": 0, "deadCrops": 0, "hoeDirt": 153, "emptyDirt": 51, "complete": true, "scanSeq": **52**}`

| 字段 | 前 | 后 | 变化 |
|---|---|---|---|
| `farm.readyCrops` | 102 | **102** | 无 |
| `farm.ripeCrops` | 1 | **1** | 无 |
| `farm.crops` | 102 | 102 | 无 |
| `farm.dryCrops` / `unwateredCrops` / `deadCrops` | 0 / 2 / 0 | 0 / 2 / 0 | 无 |
| `farm.hoeDirt` / `emptyDirt` | 153 / 51 | 153 / 51 | 无 |
| `farm.scanSeq` | 51 | 52 | 只证明**又扫了一次** |

| `(60,29)` 字段 | 前 | 后 | 变化 |
|---|---|---|---|
| `crop` | `"270"` | **`"270"`** | **无（作物还在）** |
| `ripe` / `ready` / `fullyGrown` | true / true / true | true / true / true | 无 |
| `currentPhase` / `phaseDays` / `dayOfCurrentPhase` | 5 / 6 / -9 | 5 / 6 / -9 | 无 |
| `dead` / `watered` / `standable` / `actionable` | false / true / true / true | 同 | 无 |
| `harvestMethod` | **缺键** | **缺键** | 无 |

**背包差分**：`{}`（`(O)270` 或任何新物品都没有增加；`w._loot_delta` 同为 `{}`）。
**存档差分**：主档 **4310486 B / `2026-10-17 05:04:35.296`** 与 `SaveGameInfo` **28707 B / `05:04:35.298`** —— **动手前后逐字节未变**。
**SMAPI 差分**：`lines 424→429`（+5，全是本脚本的 `GET /v1/observe` / `POST /v1/exec` 记录）；`newday 0→0`；`save_called(修正后) 0→0` ⇒ 本次动作**没有引发任何落盘**。

---

## §5 判据对照（卡面原文口径）

| 判据 | 要求 | 实测 | 命中 |
|---|---|---|---|
| **(a) 真摘到** | `readyCrops 1→0` 且该格 `crop==null`（或不再 `ripe`）；回执 `acted=true`/`status=ok`；背包对应作物 +1 | `readyCrops` **102→102**；`crop` 仍 `"270"`、`ripe` 仍 true；回执 `acted=true`/`status=ok` ✅；背包 **+0** | **✗ 不成立** |
| **(b) 判据纠正后不再算可收** | `readyCrops == 0`（`ripeCrops` 允许仍 1）+ 该格 `ready` 为 `false`/`null` + 当天目标池空且**不是**靠 `harvest_gave_up` 洗白 | `readyCrops = 102`（≠0）；该格 `ready = true`（既非 false 也非 null）；`tile_ready=True` ⇒ 仍被当可收 | **✗ 不成立** |
| FAIL 条款 1 | `ready` 缺失/`null` 却被当"可收" | `ready` **存在且为 true**（不是缺失） | 未直接命中，但见 §7 缺陷 B |
| FAIL 条款 2 | `acted` 缺失却算 ok | `acted=true`、`status=ok`；**脑侧如实判 `code=failed`**（没有把它当成功） | 未命中 |
| FAIL 条款 3 | 同格试满 `MAX_TILE_ATTEMPTS` 后整天无进展 | 本卡只做 **1 次**（未试满、无整天） | 未命中 |

⇒ **唯一诚实结论：PASS 的 (a)/(b) 都不成立 ⇒ FAIL**；FAIL 的三条字面条款也都不构成，说明"这次失败"不是判据把 `ready` 缺失当可收、也不是回执谎报被脑采信。

---

## §6 本次动作的"回执 vs 世界"对照（诚实化到底了没有）

- ✅ **脑侧诚实化生效**：`FarmWorker.harvest()` 的判据是**该格作物没了**，回执只当诊断 ⇒ 明明 `status=ok`，脑仍如实判 `code=failed` + reason「游戏口径可收但作物还在」。**没有出现 run A/B 那种"回执 ok 就算摘到"**。
- ⚠ **Mod 的 `acted` 语义仍会误导人**：`acted=true` 只表示"我调了游戏自己的 `checkAction`"，**不表示作物被摘掉**（`worldSeq 51→51`、作物原封不动）。`docs\_il-harvest-path.md` 的验收口径要求"若某天它真的可收，`interact` 后的观测里 `crop` 必须消失；回执只在 `acted==true` 时才允许 `ok`"——本次 `acted=true` 且 `crop` **没**消失，说明**这条通道（`interact`）对样本格无效**。

---

## §7 结论、机制假设与混杂因素（**不许跳过本节**）

**结论：FAIL**（PASS 二选一都不成立）。但**我不把成因单独归给"判据纠正没用"**，因为存在两个**未排除的混杂因素**：

**混杂 1 —— 背包 12/12 全满（0 空格）**。
- 事实：`inventoryCount = 12`，12 格全被占（§2）。
- 影响：收获物的落袋路径会失败；若游戏因此拒绝/不完成收获，那么"摘不到"**与 harvest 判据无关**。我**未**用任何方式排除它（本卡只允许一次 harvest，我没有去腾格）。
- 旁证：run8 的同一病灶就是"背包 0 空格、无法并堆"（`no_inventory_space` ×25，task-102）。

**缺陷 A —— `harvestMethod` 字段缺失 ⇒ 工具路径永远走不到（本机实证）**。
- 事实：样本格与四邻的 JSON 里**都没有 `harvestMethod` 键**（§2），而 `Contracts.cs` 声明了它、`CropMeta.Fill` 也填了它 ⇒ `CropMeta.HarvestMethodOf()` 返回 `null`（`ReadMember` 取不到非 public 的 `Crop.HarvestMethod`）⇒ `harvest_tool()` 恒为 `None` ⇒ 脑**只能**走 `interact`。
- 后果：按 `docs\_il-harvest-path.md` 第 14 行的 IL 结案，**镰刀类作物 `interact` 永远摘不到**（`HoeDirt.performUseAction` 的 `harvestMethod==Scythe` 分支要求 `player.CurrentTool.isScythe()`，否则只弹红字）⇒ 若样本格恰是镰刀类作物，就会精确复现本次症状（`acted=true`、`crop` 不动）。**而唯一能判定它是不是镰刀类作物的字段，正是缺失的那个。**
- 附带观测：该格 `regrowsAfterHarvest=true`、`dayOfCurrentPhase=-9`、`fullyGrown=true` —— 判别量不全，本文**不**据此断言子形态（记【无法判定】）。

**缺陷 B —— `ready` 与"熟"不一致 ⇒ 目标池没有被收窄**。
- 事实：`(60,28)/(61,29)/(60,30)` 三格 `fullyGrown=false`、`ripe=false`，但 `ready=true` ⇒ `farm.readyCrops == farm.crops == 102`。
- 两种可能：(i) `CropMeta.Ready` 的反射调用 `HoeDirt.readyForHarvest()` **失败**、退回字段判据，而字段判据在"末阶段还没熟"这一形态上过宽；(ii) 游戏自己就说这三格可收——但那样 `interact` 应当能把它们摘掉（本次**未测**）。
- 无论哪种，**run A/B 的"整天盯着一格"形态没有被 `readyCrops` 收窄**：目标池仍等于全部作物。

**为什么这次不能直接改判为"0.7.33 判据纠正无效"**：样本格的 `ready=true` 与 `ripe=true` 一致（该格**确实**是熟作物），失败点落在"摘不动"而不是"把不熟的当熟"；而"摘不动"的三条候选路径（背包满 / 镰刀类走错入口 / 游戏另有前置条件）**本次都没被排除**。

**建议的下一步（供 Lead 决策，我不擅自执行）**
1. **dev-coder**：查 `CropMeta.HarvestMethodOf` 在 1.6.15 上的反射失败原因（成员名/可见性/是否 `NetString`），并让 `ready` 的来源可判别（输出"是反射到的 `readyForHarvest()` 还是退回字段判据"）。**没有这个字段，镰刀类作物永远摘不到，也无法判定样本格子形态。**
2. **一次腾格复测**（可选，同会话即可做）：用**受制裁的**`sell`/`surplus_sell` 路径把一叠盈余材料（如 `(O)262 Wheat×37` 或 `(O)Moss×35`）出货腾出空格，然后对 `(60,29)`**再摘一次**并观测 —— 这样能把"混杂 1（背包满）"单独排除。**代价**：若作物真是可摘的，样本会被摘掉（`(60,29)` 的"熟了摘不到"现场就没了，但它已写进 `scratch\run10-tile6029-{before,after}.json`）。
3. **镰刀路径复测**（会消耗样本）：`use_tool((60,29), tool="scythe")` 一次，看是否正是被 `interact` 挡掉的那条路 —— 需要 Lead 明确授权，因为它是"改变样本"的动作。
4. 若确认是背包满导致：本卡的 FAIL 应当**撤销**，改判为"**因满格无法验证**"（needs_retest），并把 task-102/104 的空格前置条件写进卡面。

---

## §8 保留物 · 不确定项 · 诚实声明

**保留物**：`scratch\run10-tile6029-before.json`（full 观测原文）、`scratch\run10-tile6029-after.json`、`scratch\run10-tile6029-verify.py`；`logs\run10-baseline.json`（Lead 起跑前写的基线）；SMAPI `logs` 未冻结（本轮不动长跑，增量已在 §4 记数）。

**不确定项（逐条）**
1. **背包满是否为直接原因** —— 【无法判定】（未腾格复测）。
2. **样本格是否镰刀类作物** —— 【无法判定】（`harvestMethod` 缺失）。
3. **`ready=true` 的来源**（反射 `readyForHarvest()` vs 字段判据） —— 【无法判定】（Mod 未输出该来源标记）。
4. `(60,28)` 等三格 `ready=true` 是否与游戏口径一致 —— 【无法判定】（未对它们动手）。
5. 存档/世界：本次动作**没有**任何落盘（`NewDay 0→0`、`save_called 0→0`），**没有**新增/减少物品，**没有**作物状态变化 ⇒ 世界状态与动手前一致。

**诚实声明**：本卡按卡面只做了**一次** harvest，未起长跑、未腾格、未改源码、未 deploy；FAIL 是"PASS 二选一都不成立"的事实判定，**不是**对 0.7.33 修复效果的最终裁定；在混杂因素被排除前，本文**不**宣称"0.7.33 的 harvest 判据纠正无效"，也**不**宣称"有效"。

---

## §9 收尾：优雅退出（用户政策 m02833）

**退出前**（与 §4 一致，本次动作没有引发任何落盘）：`Wahaha_450799035` **4310486 B / `2026-10-17 05:04:35.296`**、`SaveGameInfo` **28707 B / `05:04:35.298`**、`_old` 4281756 / `04:49:43.856`、`SaveGameInfo_old` 28760 / `04:49:43.857`。

`python tools\stop-game.py` ⇒ **rc=0**、`✅ 游戏已退出（原 pids=[13248]）`（回执：`ok — 已置 Game1.quit=true`）。**退出后核对**：`StardewModdingAPI` 进程数 **0**；`bridge.json` **已删**（`Test-Path = False`）；`netstat 17890` 只剩 **2 条 TIME_WAIT**（无 LISTENING）；**存档四条与退出前逐字一致**（4310486 / 05:04:35.296 等）。SMAPI 尾部 `05:44:08 Disconnected: ClosedGame → Disposing... → 已删除发现文件 …\bridge.json`（无 Windows 事件 1000/1001）。

⇒ **重开读档起点仍是秋 12 日清晨**（本次没有跨日、没有落盘），样本格 `(60,29)` 与"背包 12/12 全满"的状态都原样留在存档里，可随时复测。
