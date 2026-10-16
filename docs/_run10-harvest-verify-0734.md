# task-177 · 0.7.34 同格 `(60,29)` 收获复测（含腾格 / 镰刀路径 / 对照格）

> 一句话结论：**三个混杂里 ①背包满 已排除且被证明是直接原因（腾出一格后同一次 harvest 立刻成功）、②`harvestMethod` 缺键 已排除（键在，值 `Grab`/`Scythe`，Scythe 走 `use_tool`）、③`readyCrops` 没收窄 仍成立但机制查清（是游戏口径、不是 fail-open 兜底）**；同时**发现两个新缺陷**（脑侧对再生作物的成功判据把成功判成失败；Mod 侧 `acted` 派生把成功报成 `no_action`）。判据 (1)(2)(3) 成立、(4) **反向违反**。

- 执行者：`machine-runner`（唯一真机操作者）；卡：**task-177**（rev1，blocked_by task-176）
- 版本：**0.7.34**，冻结提交 `f349f14`
- 时间：2026-10-17 06:13–06:16（游戏内 第 1 年 **秋 12 日** 10:10–11:30 rain）
- 只碰 `docs/`、`scratch/`、`logs/`；未改 `brain/`/`mod/`/`tools/`/`tests/`；未 deploy、未 `load_save`、未跨日

---

## §1 环境与版本指纹（逐字核对 Lead 给的一组）

| 文件 | SHA256 | size | mtime |
|---|---|---|---|
| `brain/agentfarm/longrun.py` | `2C5DEAAA0368B0C136BAE9F13E6EE3409DDEE75654F40498B90DD80E451A29A5` | 390876 | 2026-10-17T05:22:08.179 |
| `brain/agentfarm/farmwork.py` | `494E84C81FCD4C113D75794F91CFF300C8E8383D7E82C2FB67C505C49F0D0255` | 162757 | 2026-10-17T05:10:44.711 |
| `brain/agentfarm/bridge.py` | `FC830E2DA9D0ED1A7D183A631773BD0A0088700D480344D14AA946AB3685A7D0` | 49574 | 2026-10-17T06:09:34.062 |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `AA266F85F7407DA9F3CC32CC27945B7BD700AC06F6CCDF6D3A6FCDFA8AB16B6E` | 196608 | 2026-10-17T06:09:49.830 |
| `mod/AgentFarm.Bridge/manifest.json` | `8480207A46ECE5792857FA7D51F72DE91AB05C753301A37F0773BD1F5C6A1661` | 48579 | 2026-10-17T06:09:40.573 |

**五项全部 MATCH**（Lead 给的值逐字一致）。`HEAD = f349f14`（0.7.34 freeze）；`git status` 干净。
桥：`bridge.json` `pid=18724 / modVersion=0.7.34 / port=17890 / smapi 4.5.2`；游戏进程 PID **18724**（StartTime 2026-10-17 06:10:10）。
存档四条（起跑前）：`Wahaha_450799035` **4310486 B / 05:04:35.296**、`SaveGameInfo` 28707 B / 05:04:35.298、`_old` 4281756 B / 04:49:43.856、`SaveGameInfo_old` 28760 B / 04:49:43.857。

---

## §2 start 快照（`scratch\run10b-external-snapshots.jsonl` 第 1 行）

`{"tag":"start","at":"2026-10-17T06:13:34","save_main":{"size":4310486,"mtime":"2026-10-17T05:04:35.296"},"save_info":{"size":28707,...},"smapi_lines":416,"smapi_newday":0,"smapi_before_save":0,"smapi_save_called":3,"smapi_save_task":0,"smapi_save_completed":0,"bridge_info":{"pid":18724,"modVersion":"0.7.34"},"expected_mod_version":"0.7.34","mod_version_matches":true}`

- 本卡**没有长跑账本**（不是 run-longrun），`journal_*` 与 `pid_*` 全为 null、候选 PID 文件不存在（脚本如实打印"候选不存在"）⇒ 工具按"无长跑"处理，读数以存档与 SMAPI 为准。
- `smapi_save_called=3` 是**含 L16 插件描述行**的原始计数（修正后 = 0）。
- 走位：`python -m agentfarm move 60 28 --no-focus --timeout-ms 40000` ⇒ `move_to ok 3860ms`，`worldSeq 35→52`，玩家 `(64,15)→(60,28)`（样本格必须进玩家中心 400 格窗口）。

---

## §3 第一次 observe：**两个键都出来了**（混杂 ② 排除）

`scratch\run10b-tile6029-fields.json`（full 观测原文）。观测：`worldSeq 54`、秋12日 `timeOfDay 1030` rain、`player (60,28)` 体力 247.2 钱 0 `farmingLevel 1`、`ui` 无模态。

**(60,29) 键存在性（不是只看值）**

| 键 | 键存在 | 值 |
|---|---|---|
| `harvestMethod` | **✅ present** | `"Grab"` |
| `readySource` | **✅ present** | `"game"` |

`_all_keys` = `actionable, crop, currentPhase, dayOfCurrentPhase, dead, feature, forageCrop, fullyGrown, harvestMethod, kind, phaseDays, plantable, ready, readySource, regrowsAfterHarvest, ripe, standable, tile, tool, watered`

**样本格 `(60,29)` 原文**：`crop "270"`、`ripe true`、`ready true`、`readySource "game"`、`harvestMethod "Grab"`、`fullyGrown true`、`currentPhase 5`、`phaseDays 6`、`dayOfCurrentPhase -9`、`dead false`、`watered true`、`standable/actionable true`、`plantable false`、`regrowsAfterHarvest true` ⇒ `tile_ready=True`、`harvest_tool=None`（⇒ 走 `interact`）。

**四邻**：`(60,28)/(61,29)/(60,30)` = `crop "262"`、`ripe false`、**`ready true`**、`readySource "game"`、**`harvestMethod "Scythe"`**、`fullyGrown false`、`currentPhase 4 / phaseDays 5`、`dayOfCurrentPhase 7/9/9`；`(59,29)` = `tree/Tree`。

**farm 池（在 `obs.farm`，顶层；不是 `location.farm`）**：`hoeDirt 153`、`emptyDirt 51`、`crops 102`、`ripeCrops 1`、**`readyCrops 102`**、`deadCrops 0`、`unwateredCrops 2`、`dryCrops 0`、`weeds 483`、`stones 113`、`twigs 74` ⇒ **`readyCrops == crops == 102`（混杂 ③ 仍成立）**。窗口内 `400` 格、`ready==true` **86**、`with_crop` **86**。

**背包**：12 行、槽 0–11 全占（`(T)Axe/Hoe/WateringCan/Pickaxe`、`(W)47 Scythe`、`(O)535 Geode×3`、`(O)262 Wheat×3`、`(O)178 Hay×17`、`(O)390 Stone×3`、`(O)483 Wheat Seeds×1`、`(O) Moss×35`、`(O)262 Wheat×37`）。

---

## §4 腾格：受制裁出货路径（混杂 ① 的排除动作）

`scratch\_t177_sell.py` → `FarmWorker.sell(slot=10, whitelist=["(O)Moss"])`（`Farm.shipItem`，钱次日结算）。

| 项 | 前 | 后 |
|---|---|---|
| 出货槽位 | 槽 10 `(O)Moss ×35` | 槽 10 **空** |
| 该 qid 背包总数 | 35 | **0** |
| `shippingBin.items` | 0 | **1** |
| `money` | 0g | 0g（次日 NewDay 结算，**未**写钱） |
| 占据槽位行数 | **12** | **11** |

`StepResult: ok=True code=ok`，reason `已出货槽位 10 的 (O)Moss（背包 35→0，出货箱 1 件）…`。存档动手前后**逐字节未变**。

> **顺带查清一个字段语义（重要）**：`player.inventoryCount` 在 0.7.34 上**是容量（12），不是"占用格数"** —— 腾空槽 10 之后它**仍然读 12**。判断"背包满没满"必须数 `player.inventory[]` 的行数（本次 12 → 11）。task-173 说的"12/12 全满"由此得到精确化：当时是 **12 行占满 12 槽**（真的满），不是字段假象。

---

## §5 一次 `harvest((60,29))`：**世界成功、脑与 Mod 都报失败**

调用：`FarmWorker.harvest((60,29))`（`harvestMethod="Grab"` ⇒ 走 `interact`）。

**脑侧 StepResult**：`ok=False, code=failed, status='', elapsed 0.2s`
reason：`游戏口径可收但作物还在（交互/挥镰后没摘到）；Mod status=no_action；no_action: [no_action] (HTTP 200) (60,29) 这一格**没有任何可独立观测的变化**（checkAction 返回 True；前[|tf:HoeDirt:watered=True:crop=270:phase=5:grown=True:dead=False] → 后[…同…]）`
（`entry points used = []`：`no_action` 让客户端抛 `BridgeError`，我**动手时**的代理只在正常返回后记账 ⇒ 事后已把代理改成"调用前记账 + 捕获异常"（`scratch\_t177_harvest.py`）。Mod 回执文本里的 **`checkAction 返回 True`** 证明走的是 `interact` 路径。）

**世界差分（观测，`scratch\run10b-tile6029-{before,after}.json`）**

| 项 | 前 | 后 | 判定 |
|---|---|---|---|
| `worldSeq` | 60 | **61** | **前进** |
| `farm.readyCrops` | 102 | **101** | **下降** |
| 窗口 `ready==true` 格数 | 86 | **85** | **下降** |
| 背包该作物 | 无 `(O)270` | **`(O)270` ×1** | **+1** |
| `(60,29).ready` | true | **false** | 翻转 |
| `(60,29).dayOfCurrentPhase` | -9 | **4** | 再生计时重置 |
| `(60,29).crop` | `"270"` | `"270"` | **未消失**（`regrowsAfterHarvest=true`，再生作物收后留株） |
| `(60,29).tool` | `none` | `can` | 手持工具切换 |
| `farm.ripeCrops` | 1 | 1 | 未变（再生作物不进 ripe 计数） |
| 存档 | 4310486 / 05:04:35.296 | 同 | **未落盘** |
| SMAPI | 428 行 | 433 行 | 全是我自己的 GET/POST；`NewDay 0→0`、`save_called(修正) 0→0` |

---

## §6 对照格 `(60,28)`（卡面第 5 步）：Scythe 走工具路径，且**一镰刀收了 4 格**

`scratch\_t177_control.py`。该格 `crop "262"`、`ready true`、`readySource "game"`、`harvestMethod "Scythe"`、`fullyGrown false`、`ripe false`、`regrowsAfterHarvest false` ⇒ `harvest_tool='scythe'`。

- **入口**：`entry points used = ['use_tool']`，原始回执 `{ok:true,status:"ok",skill:"use_tool",elapsedMs:355,worldSeqBefore:66,worldSeqAfter:66}`，reason `已用「Scythe」对 (60,28) 动手 1 次（起手=是）…` ⇒ **判据 (2) 成立**。
- **世界差分**：`worldSeq 65→67`；`farm.crops 102→98`、`farm.readyCrops 101→97`、`farm.emptyDirt 51→55`（**清掉 4 格作物**）；背包 **`(O)262 Wheat 40→44`（+4）**、**`(O)178 Hay 17→19`（+2）**；`(60,28)` 收后 `crop` 键消失、`ready` 键消失、`harvestMethod null`、`readySource null`、`plantable true`。
- **脑侧 StepResult**：`ok=True code=ok`，但 reason 里写 `⚠ 背包没有新增物品（收货可能丢了，不能出货）` ⇒ **与实测 +4 Wheat / +2 Hay 矛盾**（第三个小病灶，见 §8-C）。
- **含义**：这三格 `fullyGrown=false`/`ripe=false` 却 `ready=true` 的作物**真的可收**（一镰刀得 4 个 Wheat）⇒ 游戏口径说"可收"是对的，**误导的是 Mod 的 `fullyGrown`/`ripe` 字段**。

---

## §7 卡面四条判据对照

| 判据 | 要求 | 实测 | 判定 |
|---|---|---|---|
| **(1) 两键必须存在** | `harvestMethod` + `readySource` | 都在：`(60,29)` = `"Grab"`/`"game"`；`(60,28)` = `"Scythe"`/`"game"` | **✅ PASS** |
| **(2) Scythe 必须走 `use_tool`** | 工具路径 | 对照格 `used=['use_tool']`；样本格是 `Grab` ⇒ `interact`（Mod 文本 `checkAction 返回 True`） | **✅ PASS** |
| **(3) 成功 = `readyCrops`/`ripeCrops` 下降 + 背包 +1 + `worldSeq` 前进 + 作物从该格消失** | 四条 | `readyCrops 102→101` ✅、背包 `(O)270` +1 ✅、`worldSeq 60→61` ✅、**`crop` 未消失**（`regrowsAfterHarvest=true` 的正常形态） | **✅ PASS（3/4；第 4 条对再生作物不适用）——但脑侧报 `failed`** |
| **(4) 仍收不到 ⇒ 必须 `acted=false`/`status="no_action"`** | 不许再"`acted=true` 而世界不变" | **反向违反**：出现 `acted=false`/`no_action` **而世界确实变了**（`readyCrops` 下降、背包 +1、`worldSeq` 前进） | **❌ 违反（新病灶，见 §8-B）** |

**三个混杂逐条结论**

| # | 混杂 | 结论 | 依据 |
|---|---|---|---|
| ① | 背包 12/12 满 | **已排除，且证明是直接原因** | 腾空 1 格后，同一次 `harvest((60,29))` 立刻产生世界变化（背包 +1、`ready` 翻转、`readyCrops` −1、`worldSeq` +1） |
| ② | `harvestMethod` 缺键 | **已排除** | 键存在且值正确（`Grab`/`Scythe`），Scythe 正确路由到 `use_tool` |
| ③ | `readyCrops` 目标池没收窄 | **仍成立**，但机制查清 | `readyCrops == crops == 102`；对照格证明这些格**真的可收**（一镰刀 +4 Wheat）⇒ 是**游戏口径**（`readySource="game"`），不是 Mod fail-open 兜底；误导源是 Mod 的 `fullyGrown`/`ripe` |

---

## §8 新发现（附带产出，建议各自立案）

**A. 脑侧 `harvest()` 的成功判据对"再生作物"系统性地假阴性（重要，直接解释 run A/B 的"284 次 0 成功"）**
`farmwork.py` 的判据是"**该格 `crop` 消失**"。样本格 `regrowsAfterHarvest=true` ⇒ 收完作物留株，`crop` 永远是 `"270"` ⇒ 即使 `ready` 已翻 `false`、背包已 +1、`readyCrops` 已下降、`worldSeq` 已前进，仍报 `code=failed`。
建议判据改为**任一**成立即成功：`crop` 消失 **或** `ready` true→false **或** 该 qid 背包 +N **或** `readyCrops` 下降。

**B. Mod 侧 `acted` 派生把"成功的收获"报成 `no_action`（task-176 (iii) 的判据太窄）**
回执显示 `acted` 的比较对象是 `watered/crop/phase/grown/dead` 这几项 TileSeg 字段；再生作物收获后**这些字段一项都不变**（`crop` 留株、`watered` 不变、`phase/grown` 不变）⇒ 判"没有任何可独立观测的变化" ⇒ `status="no_action"` 且被当作错误状态返回 ⇒ 脑侧记 `failed`。
建议 `acted` 纳入"该格作物的 qid 在背包 +N / `ready` 翻转 / `readyCrops` 下降"这类**跨观测**证据，或至少让 `no_action` 与"世界确实变了"可区分（不要用同一状态码覆盖）。

**C. 两次脑侧"战利品"记账与观测不符**
对照格 reason 写"背包没有新增物品"，实测 `(O)262 +4`、`(O)178 +2`（一次镰刀连带收 4 格）⇒ 脑侧 loot 差分口径需复核（可能是"只认单格产物/单次 snap 窗口"）。同时提示：**一次动作可能收多格**（本例一镰刀清 4 格），记账粒度要跟上。

**D. 字段语义（已在 §4 记录）**：`player.inventoryCount` 是**容量**（12），不是占格数；"背包满"必须数 `inventory[]` 行数。

---

## §9 收尾：优雅退出（`User said (m02833)`）

`python tools\stop-game.py` ⇒ **rc=0**、`✅ 游戏已退出（原 pids=[18724]）`（回执 `ok — 已置 Game1.quit=true`）。

**退出后四条核对**：`StardewModdingAPI` 进程 **0**；`bridge.json` **已删**；`netstat 17890` 只剩 **2 条 TIME_WAIT**（无 LISTENING）；存档四条与退出前**逐字一致**（4310486 / 05:04:35.296、28707 / 05:04:35.298、4281756 / 04:49:43.856、28760 / 04:49:43.857）。SMAPI 尾：`06:15:43 Disconnected: ClosedGame → Disposing... → 已删除发现文件 …\bridge.json`；06:00 之后 Windows 事件 1000 计数 **0**。

**先冻结后退出**：`logs\run10b-smapi-window.txt` = **70252 B / mtime 2026-10-17T06:15:17.807 / SHA256 `E128DA82E01BA36A43B93708AF9C9EFABE7EEE172CA3CE63FBE57A8246033BBC`**。（源文件被运行中的游戏独占，`Get-FileHash` 对源失败 ⇒ **源/副本字节一致性未校验**，与 run9 同样情形。）

**重开读档的起点**：本次**没有跨日、没有任何落盘**（`NewDay 0→0`、`save_called 0→0`，存档四条未变）⇒ 磁盘上仍是**第 1 年秋 12 日清晨**，且**背包 12 槽全占、Moss×35 还在、`(60,29)` 仍是 `ready=true` 的熟作物** —— 即本次所有腾格/收获**只存在于内存**，退出即消失，样本原样保留，可再复测。

---

## §10 保留物 · 不确定项 · 诚实声明

**保留物**：`scratch\run10b-external-snapshots.jsonl`（start/end）、`scratch\run10b-tile6029-fields.json`、`scratch\run10b-tile6029-{before,after}.json`、`scratch\run10b-control-{before,after}.json`、`logs\run10b-smapi-window.txt`、`scratch\_t177_{fields,sell,harvest,control}.py`。

**不确定项**
1. 对照格那一镰刀到底覆盖哪几格 —— 【无法判定】（只观测到净效果：`crops −4`、`emptyDirt +4`、`Wheat +4`、`Hay +2`；未逐格取证）。
2. 源 SMAPI 与冻结副本是否逐字节一致 —— 【无法判定】（源被游戏独占）。
3. ①"背包满"是**唯一**阻塞因素还是**之一** —— 【部分可判定】腾 1 格后同格收获成功，说明满格至少是充分阻塞项；但未做"再多腾几格"的对照。
4. §8-C 的 loot 记账口径 —— 【无法判定】（需要读脑侧代码或再复现一次）。

**诚实声明**：本卡按 Lead 流程执行；`(60,29)` 与对照格 `(60,28)` 各只做 **1 次**收获尝试（共 2 次动作 + 1 次受制裁出货）；未跨日、未落盘、未改源码、未 deploy。判据 (3) 的"成功"是**按世界观测差分**判的；脑侧与 Mod 侧当时的结论都是失败，正是本卡最重要的产出（§8-A/B）。
