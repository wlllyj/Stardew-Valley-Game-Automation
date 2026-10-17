# task-184：0.7.35 同格复测 —— `(60,29)` 再生作物收获被判**正确成功** + Scythe 对照格回归

> **状态：交付 · 核心判据 PASS（三源一致）**
> 一句话结论：**再生作物收获的"世界变了但脑/Mod 都报失败"已被修复** —— 样本格 `(60,29)` 上脑侧 `ok=True`（reason 明确写出新判据）、Mod 回执 `acted=true` + `actedEvidence="ready"`、世界差分（`ready true→false`、`readyCrops 102→101`、背包 `(O)270 +1`）**三者一致**；Scythe 走 `use_tool` 亦正确。**残留三项**：① `use_tool` 回执仍**缺 `acted`/`actedEvidence` 键**；② 脑侧 loot 记账**仍报"背包没有新增物品"**（缺陷 C 未修，实收 `(O)262 +4`/`(O)178 +2`）；③ `worldSeq` 不随 `interact` 收获前进（不能当成功信号）。本次**未跨日、未落盘**，退出后存档四条逐字未变。

- 日期：2026-10-17（Asia/Bangkok）｜执行者：`machine-runner`｜版本：**Mod 0.7.35 / HEAD `630e594`**
- 产物：本文件 + `scratch\_t184_probe.py`（探针）+ `scratch\_t184_triple_check.py`（三源判定，离线）
- 原始证据：`scratch\_t184_observe-fields.json`、`scratch\_t184_harvest-6029-{before,after,receipt,verdict}.json`、`scratch\_t184_control-6028-{before,after,receipt,verdict}.json`、`scratch\_t184_sell-{before,after}.json`、`scratch\run10c-external-snapshots.jsonl`、`logs\run10c-smapi-window.txt`

---

## §1 环境、版本与指纹

**五文件指纹（与 Lead 下发的 0.7.35 构建锚逐字比对，五项全部 MATCH）**

| 文件 | SHA256(前16) | size | mtime |
|---|---|---|---|
| `brain/agentfarm/longrun.py` | `D5F8F98D16AC8451` | 417566 | 2026-10-17 07:11:30.596 |
| `brain/agentfarm/farmwork.py` | `E89DBB3C78DFFF12` | 167713 | 2026-10-17 06:24:00.388 |
| `brain/agentfarm/bridge.py` | `3FAEBC363BF92D4E` | 50526 | 2026-10-17 07:18:40.536 |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `5925F3660AB5613E` | **199168** | 2026-10-17 07:18:59.237 |
| `mod/AgentFarm.Bridge/manifest.json` | `24877328542B956C` | **51090** | 2026-10-17 07:18:11.424 |

- `git rev-parse --short HEAD` = `630e594`；`git status --short` 干净。
- `bridge.json` = `{"schema":"agentfarm-bridge/1","port":17890,"pid":21496,"modVersion":"0.7.35","gameVersion":"1.6.15","smapiVersion":"4.5.2","startedAt":"2026-10-17T00:19:26+00:00"}`（207 B，mtime 07:20:57）。
- 游戏进程 PID **21496**（StartTime 2026-10-17 07:19:19）；`python -m agentfarm goto Farm` 由 Lead 执行（`hop1 [3,12]→[64,15]` 7623ms）。
- Lead 的 `preflight --expect 0.7.35 --save-baseline logs\run10c-baseline.json` = **exit 0**；基线要点：`generatedAt 2026-10-17T07:19:42+07:00`、`worldSeq 10`、`day [1,"fall",12]`、`tod 600`、`modVersion 0.7.35`、`tillableCount 120`、`tileCount 400`、`tilesTruncated true`；现场读数（Lead 下发）：秋 12 日 06:00 rain、Farm(64,15)、体力 247.2/270、钱 0g、种子 Wheat Seeds×1、`crops 102`、`unwateredCrops 2`、`dryCrops 0`、`scanSeq 9`、`waterLeft 27`、无模态、世界推进中。**未做任何操作员预置**。
- **start 快照**（`scratch\run10c-external-snapshots.jsonl`，`tag:"start"`）：`save_main 4310486 B / 2026-10-17T05:04:35.296`、`save_info 28707 B`、`journal_lines_at_start 0`、`expected_mod_version 0.7.35`。
  - **两处口径说明（诚实标注）**：① 该行是**事后补写**（`written_at 07:25:27`，`note` 已写明）—— 因为本轮不跨日、start 与 end 的读数完全一致，补写不影响任何判据；② `save_info.mtime` 被 `--save-mtime` 单一覆盖写成 `05:04:35.296`，**真实读数是 `05:04:35.298`**（见 §3 与 §9 的现场四条）；③ `smapi_lines 0` 是因为 `--smapi-before 07:19:00` 之前没有任何带时间戳的行（游戏 07:19:19 才启动），语义正确。

## §2 现场与走位

- 走位：`python -m agentfarm move 60 28 --no-focus --timeout-ms 40000` ⇒ `move_to status=ok 3861ms worldSeq 28→45`，到达 **(60,28)**（既在样本格正邻，也让 `(60,29)` 进 400 格观测窗口）。
- 观测窗口必须包含样本格，否则 `tile_view()` 返回 `None`（task-173 已踩过）。本次 `window_tiles=400`、`with_crop=86`。

## §3 字段核对（步骤 1）与"背包是否满"的正确口径

`observe?detail=full`（`worldSeq 52`、`clock fall 12 tod 1010 rain`、`player [60,28]`、`stamina 247.20007`、`money 0`、`ui.isModal false`、`liveness.worldAdvancing true`）。

**样本格 `(60,29)` 原文（关键字段）**
```json
{"tile":[60,29],"kind":"dirt","tool":"none","feature":"HoeDirt","standable":true,"actionable":true,
 "crop":"270","ripe":true,"ready":true,"readySource":"game","harvestMethod":"Grab",
 "fullyGrown":true,"currentPhase":5,"phaseDays":6,"dayOfCurrentPhase":-9,
 "dead":false,"watered":true,"plantable":false,"regrowsAfterHarvest":true}
```
- **两个新键都在**：`harvestMethod`（值 `"Grab"`）与 `readySource`（值 `"game"`）——task-176 的"键必出"在 0.7.35 上成立 ✅
- 脑侧判定：`tile_ready=True`、`ready_note=''`、`harvest_tool=None`（⇒ 走 `interact` 路径）

**四邻**

| 格 | crop | ripe | ready | readySource | harvestMethod | fullyGrown | 说明 |
|---|---|---|---|---|---|---|---|
| `(60,28)` | `262` | false | **true** | `game` | `Scythe` | false | 对照格 |
| `(61,29)` | `262` | false | true | `game` | `Scythe` | false | 同形 |
| `(60,30)` | `262` | false | true | `game` | `Scythe` | false | 同形 |
| `(59,29)` | — | false | — | — | — | — | 树（不可站） |

**farm 池与窗口**（`obs.farm`，顶层）
`crops 102`、`readyCrops 102`、`ripeCrops 1`、`unwateredCrops 2`、`dryCrops 0`、`deadCrops 0`、`hoeDirt 153`、`emptyDirt 51`、`complete true`、`scanSeq 52`；窗口 `ready==true` **86**、`with_crop` **86**、`tiles 400`。
⇒ **`readyCrops == crops == 102` 依旧成立**（task-177 的混杂③"游戏口径"在 0.7.35 上未变，且非 fail-open：对照格证明这些格真能收）。

**背包**：`player.inventoryCount = 12`（**容量字段**，task-177 缺陷 D）而 `inventory[]` **行数 = 12** ⇒ **0 空槽**。
| slot | itemId | 名称 | stack |
|---|---|---|---|
| 0–3 | Axe / Hoe / WateringCan / Pickaxe | 工具 | 1 |
| 4 | `47` | Scythe | 1 |
| 5 | `535` | Geode | 3 |
| 6 | `262` | Wheat | 3 |
| 7 | `178` | Hay | 17 |
| 8 | `390` | Stone | 3 |
| 9 | `483` | Wheat Seeds | 1 |
| 10 | `Moss` | Moss | 35 |
| 11 | `262` | Wheat | 37 |

`shippingBin` = `{"present":true,"count":0,"items":[],"lastItemShipped":""}`（路径 `obs.shippingBin`）。

## §4 腾格（步骤 3，**只走出货箱**）

| # | 动作 | rows 前→后 | 被卖栈 | `shippingBin.count` | money | 存档 |
|---|---|---|---|---|---|---|
| 1 | `sell(slot=10, whitelist=["(O)Moss"])` | **12 → 11** | `(O)Moss` ×35 | 0 → 1 | 0 → 0 | 未变 |
| 2 | `sell(slot=8, whitelist=["(O)390"])` | **12 → 11** | `(O)390` ×3 | 1 → 2 | 0 → 0 | 未变 |

- 回执原文（#1）：`已出货槽位 10 的 (O)Moss（背包 35→0，出货箱 1 件）；钱要等下一次 NewDay 才由游戏结算（当前 0g）`
- `shippingBin.items` 逐条确认：`[{"qualifiedId":"(O)Moss","stack":35},{"qualifiedId":"(O)390","stack":3}]`
- 第 2 次腾格是**为步骤 7 的对照格回归**腾出空槽（第一次腾出的空槽被样本格收获的新物品 `(O)270 ×1` 占用，见 §5）。

## §5 样本格 `(60,29)`：**一次** `FarmWorker.harvest((60,29))`（步骤 4）

- 路径：`entry points used = ['interact']`（`harvest_tool=None`，与 `harvestMethod="Grab"` 一致）✅
- 脑侧 `StepResult`：`ok=True`、`code=ok`、`status=''`、耗时 **0.2s**
- **reason 原文**（含新判据自述）：
  > 收获成功（判据：该格 ready true→False；进背包：{'(O)270': 1}（逐 qid 差分；一次动作可能收多格））；受影响格：[[60, 29]]；再生作物：crop 对象保留、阶段重置（旧判据只看 crop 消失 ⇒ 假阴性）
- **Mod 原始回执原文**：
```json
{"acted":true,"actedEvidence":"ready","elapsedMs":0,"ok":true,"reachedLocation":"Farm",
 "reason":"已在 (60,29) 调游戏自己的 checkAction，且**观测到世界变了**（证据来源 `ready`；checkAction 返回 True）。tile[|tf:HoeDirt:watered=True:crop=270:phase=5:grown=True:dead=False → |tf:HoeDirt:watered=True:crop=270:phase=5:grown=True:dead=False]；ready[True → False，readySource[game → game]；readyCrops[102 → 101]；inventoryGrew=True。…",
 "schema":"agentfarm-exec/2","skill":"interact","status":"ok","uiOpened":false,"worldResumed":true,
 "worldSeqBefore":60,"worldSeqAfter":60}
```
- **世界差分**（`_t184_harvest-6029-{before,after}.json`，判定取自现场观测，**不取自 final 快照**）

| 观测量 | before | after | 变化 |
|---|---|---|---|
| `farm.readyCrops` | 102 | **101** | ↓ |
| 窗口 `ready==true` | 86 | **85** | ↓ |
| 背包 `270` 栈 | 0 | **1** | **+1** |
| `(60,29).ready` | true | **false** | 翻转 |
| `(60,29).dayOfCurrentPhase` | -9 | **4** | 阶段重置 |
| `(60,29).tool` | none | can | 动作后状态 |
| `(60,29).crop` | `"270"` | `"270"`（**保留**） | 再生作物正常 |
| `worldSeq` | 60 | **60** | **未前进** |
| 存档四条 | 05:04:35 | 05:04:35 | 未落盘 |

- **三源判定**（`scratch\_t184_triple_check.py`）：`PASS · AGREE_SUCCESS`，`three_way_consistent = True`

## §6 对照格 `(60,28)`：Scythe 路径 + 多格 loot 记账（步骤 7）

**第 1 次尝试（背包满，被脑侧拒绝，未触桥）** —— 这一步本身是**缺陷 D 修复的正面证据**：
- 脑侧 `ok=False code=failed`、耗时 **0.0s**、`entry points used = []`、**Mod 回执 `null`**（**没有向桥发任何请求**）
- reason 原文：`背包满（空槽 = \`inventoryCount\` 容量 − \`inventory[]\` 行数 = 0；\`inventoryCount\` 是容量字段，不能拿它判满）⇒ 先出货/整理背包再来收`
- 三源判定：`PASS · AGREE_FAILURE`（拒绝一致、世界未变）

**第 2 次尝试（腾格后）**
- 路径：`entry points used = ['use_tool']` ✅（`harvestMethod="Scythe"` 正确路由）
- 脑侧：`ok=True code=ok`、0.9s；**受影响格 8 格**：`[[44,24],[53,16],[54,15],[59,28],[60,28],[61,28],[61,29],[72,21]]`（一次动作多格，符合镰刀语义）
- reason 原文（**注意末句是错的**，见 §8-R2）：
  > 收获成功（判据：该格 crop 已消失；该格 ready true→None）；受影响格：[…8 格…]；⚠ 背包没有新增物品（收货可能丢了，不能出货）
- **Mod 原始回执原文**（**注意：没有 `acted`/`actedEvidence` 键**，见 §8-R1）：
```json
{"elapsedMs":355,"ok":true,"reachedLocation":"Farm",
 "reason":"已用「Scythe」对 (60,28) 动手 1 次（起手=是），该格原本是 （空），现在**上面已经没有东西了**（kind=「dirt」）（请用 observe 的 tiles[] 复核）",
 "schema":"agentfarm-exec/2","skill":"use_tool","status":"ok","uiOpened":false,"worldResumed":true,
 "worldSeqBefore":66,"worldSeqAfter":66}
```
- **世界差分**

| 观测量 | before | after | 变化 |
|---|---|---|---|
| `farm.crops` | 102 | **98** | −4 |
| `farm.readyCrops` | 101 | **97** | −4 |
| `farm.emptyDirt` | 51 | **55** | +4 |
| 窗口 `ready==true` / `with_crop` | 85 / 86 | **76 / 77** | −9 / −9 |
| 背包 `262` | 40 | **44** | **+4** |
| 背包 `178` | 17 | **19** | **+2** |
| `(60,28)` | `crop "262"`, `ready true`, Scythe | `crop` 键消失、`ready` 键消失、`harvestMethod null`、`readySource null`、`plantable true` | 清空 |
| `worldSeq` | 65 | **67** | +2 |
- **三源判定**：`PASS · AGREE_SUCCESS`，`three_way_consistent = True`
- **多格 loot 记账（逐 qid）**：`{"178": +2, "262": +4}` ⇒ 两个 qid 全部入账，**一次动作多格**的观测口径正确

## §7 四条判据逐条读数

| # | 判据 | 读数 | 结论 |
|---|---|---|---|
| (1) | 脑侧报 `ok` | 样本格 `ok=True code=ok`（reason 自述新判据）；对照格 `ok=True code=ok` | **✅ PASS** |
| (2) | Mod `acted=true` 且 `actedEvidence` 非空 | 样本格（`interact`）：`acted=true`、`actedEvidence="ready"` ✅；对照格（`use_tool`）：**两键均缺失** ❌ | **⚠ 部分 PASS**（见 R1） |
| (3) | 世界证据至少一条命中 | 样本格：`ready` 翻转 ✅ + `readyCrops` 下降 ✅ + 背包 `(O)270 +1` ✅（`crop` 不消失属再生作物正常）；对照格：`crop` 消失 ✅ + `readyCrops 101→97` ✅ + loot `+4/+2` ✅ | **✅ PASS** |
| (4) | 三者一致（不许"世界变了但脑侧报 failed"） | 两次都是 `AGREE_SUCCESS`；被背包守卫拒绝那次是 `AGREE_FAILURE`（且未触桥） | **✅ PASS** |

**总判定：核心目标达成 —— task-181（脑侧四择一 + 逐 qid 记账）与 task-182（Mod `acted` 跨观测证据）在 `interact` 收获路径上真机生效，"反向不一致"消失。**

## §8 残留与新增发现

- **R1（新，Mod 侧）**：`use_tool` 技能的回执**没有 `acted`/`actedEvidence` 键**（`interact` 有）。task-182 的跨观测证据只覆盖了 `interact`。⇒ 判据 (2) 在 Scythe 路径上无法满足；建议 task-182 的修法覆盖 `use_tool`（或统一由 exec 层派生）。
- **R2（旧缺陷 C 未修，brain 侧）**：对照格 reason 仍写 `⚠ 背包没有新增物品（收货可能丢了，不能出货）`，而世界实测 `(O)262 +4`、`(O)178 +2`。⇒ 脑侧 loot 记账（或"新物品"判定）在多格/合并入既有栈的情形下仍失真；这会误导后续"卖收获物"的决策（agent 会以为自己没收上来东西）。
- **R3（口径）**：`interact` 收获**不会推进 `worldSeq`**（60→60，Mod 回执也如实写 `worldSeqBefore/After=60`）。⇒ `worldSeq` 不能当"收获成功"的判据；四条世界证据里应以 `ready` 翻转 / 背包 qid +N / `readyCrops` 下降为准。
- **R4（NIT，Mod 文案）**：`use_tool` 的 reason 把该格原物渲染成空 —— `该格原本是 （空）`（作物名取不到），容易误读。不影响判定。
- **R5（正面，已修复确认）**：`player.inventoryCount` 是**容量**字段，0.7.35 的脑侧"背包满"守卫已改用 `inventory[]` **行数**，且在 0 空槽时**不向桥发任何请求**（`entry points used = []`、Mod 回执 `null`），reason 明确解释了口径。缺陷 D 闭合。
- **R6（观察）**：`readyCrops == crops == 102` 在 0.7.35 上仍成立；但对照格一镰刀真收 4 格 ⇒ 确认这是**游戏口径**（`readySource="game"`），非 Mod fail-open。若未来要收窄目标池，应在脑侧按"可操作性/可达性"过滤，而不是改 `readyCrops`。

## §9 收尾：优雅退出（`User said (m02833)`）

`python tools\stop-game.py` ⇒ **rc=0**、`✅ 游戏已退出（原 pids=[21496]）`（回执 `ok — 已置 Game1.quit=true`）。

| 检查项 | 退出前 | 退出后 |
|---|---|---|
| `StardewModdingAPI` 进程 | 1（PID 21496） | **0** |
| `bridge.json` | 存在（207 B / 07:20:57） | **已删除**（`Test-Path=False`） |
| 端口 17890 | LISTENING | **仅 2 条 TIME_WAIT**（无 LISTENING） |
| `Wahaha_450799035` | 4310486 B / `2026-10-17 05:04:35.296` | **逐字未变** |
| `SaveGameInfo` | 28707 B / `05:04:35.298` | **逐字未变** |
| `_old` / `SaveGameInfo_old` | 4281756 B / 04:49:43.856；28760 B / 04:49:43.857 | **逐字未变** |

- **SMAPI 冻结**（这次按 Lead 的建议**等游戏退出后**再复制，源不再被独占）：`logs\run10c-smapi-window.txt` = **74319 B / SHA256 `88C22A9D5CA36C863AE16A09F845069BC39AC4C44194D05886341CD56D761CE0` / mtime 07:24:56.329`；与源 `%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt` **size 与 SHA256 完全一致（`BYTE_IDENTICAL=True`）** —— task-177 那条"未能校验源/副本一致"的口径缺口本次补齐 ✅
- 结束链：SMAPI 尾 `07:24:56 GET /v1/health → POST /v1/exec → TRACE game] Disconnected: ClosedGame → Disposing... → INFO AgentFarm Bridge] 已删除发现文件 …\bridge.json → Disposing the content coordinator.`（游戏自己关的，非被强杀；无 Event 1000/1001）
- 本次会话：`NewDay 0` / `before save 0` / `Save called`（修正后）**0** / `Save task 0` / `completed 0`（`raw 3` 全部来自 L16 插件描述行那条假阳性）
- **未跨日、未落盘** ⇒ **重开读档仍是第 1 年秋 12 日清晨**；但注意：本会话在**内存里**已改变的世界（样本格已收、`(60,28)` 等 8 格被清、出货箱里有 Moss×35 + Stone×3、背包里多了 `(O)270 ×1`/`(O)262 +4`/`(O)178 +2`、少了 Moss/Stone）**退出即丢弃**，重开后样本格仍是 `ready=true`（`harvestMethod="Grab"`），可再次复测。

## §10 保留物、不确定项与诚实声明

**保留物**（不删、不改名）：`scratch\_t184_observe-fields.json`、`scratch\_t184_sell-{before,after}.json`、`scratch\_t184_harvest-6029-{before,after,receipt,verdict}.json`、`scratch\_t184_control-6028-{before,after,receipt,verdict}.json`、`scratch\run10c-external-snapshots.jsonl`、`logs\run10c-smapi-window.txt`、`logs\run10c-baseline.json`（Lead 的）。

**本次明确做到**：走位让样本格进窗口；腾格只走出货箱且只用白名单盈余材料（Moss/Stone）；样本格**只动手一次**；判定一律取自**两份独立观测的差分**，不取自 `day_end.final` 或 Mod 自述；源/副本 SMAPI 字节一致性已校验；退出前后存档四条对比。

**不确定项（不宣称）**：
1. **"7 个游戏日的自主运行能否达标"未验证** —— 本次只做了两个单点动作，不代表 run 级表现。
2. **`readyCrops == crops`** 只证明"游戏口径下这些格可收"，**不证明**脑侧目标池选择是否合理（可达性/可操作性过滤仍待 run 级检验）。
3. **R2 的 loot 记账失真只在"多格/合并入既有栈"的形态上被观测到**；单格新物品（样本格 `(O)270 +1`）时脑侧 reason 记的是 `{'(O)270': 1}`，**是对的** ⇒ 需要按形态分别复现才能定案根因。
4. **`use_tool` 回执缺键** 只在本形态（Scythe、多格）上观测到；未穷举其它 `use_tool` 场景（锄地/浇水同样走 `use_tool`）。
5. 本文件所有读数均为**单次真机观测**；未做重复测量，故不给误差估计。
