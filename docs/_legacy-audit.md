# 既有《星露谷》自动化项目审计报告（供架构重写）

- **审计对象**：`C:\Users\admin\WorkBuddy\2026-10-04-20-36-38\stardew-auto-farm`
- **环境**：Stardew Valley 1.6.15 / SMAPI 4.5.2 / .NET 6 / Windows
- **故障现场（存档 Wahaha，第 1 年春 3 日）**：AI 写出 39 条动作，全部 SKIP，理由全为「跨地点退避中」。已从**磁盘实测数据**确认，非推测（见 §0）。

> 引用约定：`文件:行号` 中的文件路径相对仓库根目录。所有结论均来自实际读码或实际读取的运行期数据文件；无法确认处显式标注「未确认」。

---

## §0 现场实证（决定了后面所有结论的权重）

直接读游戏目录下运行期产物 `D:\...\Mods\AutoFarmWorker\data\`：

| 文件 | 大小 / 时间 | 关键内容 |
|---|---|---|
| `ai_result.json` | 2595 B / 16:10:55 | `schema=stardew-ai-result/1`，`done=0`，**`skipped=39`**，`failed=0`，**`elapsed_seconds=0.6`** |
| `farm_tiles.json` | 244637 B / 16:10:44 | `tiles_scanned=1404`、`crops=0`、`empty_dirt=0`、`weeds=443`、`stones=241`、`twigs=114`、`trees=148`、`grass=458` |
| `ai_directive.json` | 5458 B / 16:11:10 | 模型输出的 38~41 条计划，写入周期约 25~40 秒 |

`ai_result.json` 的 39 条 `details` 全部形如：

```
SKIP clear_weed@(62,20) [A141] — 跨地点退避中
SKIP scythe_or_till@(59,22) [A205] — 跨地点退避中
...（39 条，无一条 DONE / FAIL）
```

`farm_tiles.json` 的 `save` 与 `liveness` 段：

```json
"save": { "season":"spring","day":3,"year":1,"money":482,
          "player_xy":[2,11],"location":"FarmHouse","on_farm":false,
          "farm_entry_xy":[64,15] }
"liveness": { "world_advancing":true, "game_time":1200,
              "seconds_since_clock_moved":7.27 }
```

**三点硬结论**：

1. **世界没有停摆**（`world_advancing=true`、时钟 7.27 秒前刚动过），所以「世界冻结」不是本次根因。这条排除了 manifest 里反复强调的失焦暂停坑（`src/AutoFarmWorker/manifest.json:5`）。
2. `elapsed_seconds=0.6` 且 `done=0`：整个 39 条计划在 **0.6 秒内被“处理”完**，说明每条都是在**入队后立刻被丢弃**，没有任何一条真正尝试过寻路或执行。
3. `farm_entry_xy=[64,15]` 与 `ModEntry.Watchdog.cs:371` 的**硬编码兜底值 `Point(64,15)` 逐字相同**。`WatchdogFindFarmLanding()` 的两个 `GetMainFarmHouseEntry()` 分支都返回了无效值，最终落到硬编码。这是 §5 缺陷 D3 的直接证据。

---

## §1 数据与通信协议（brain ↔ mod）

### 1.1 真正的数据流：不是 `live_snapshot.json`，而是 `farm_tiles.json`

文档 `docs/ARCHITECTURE.md:9-19` 与 `docs/WATCHDOG_AND_AI.md:113-121` 宣称的链路是
`AutoFarmPlanner/data/live_snapshot.json → 决策 → AutoFarmWorker/data/ai_directive.json`。
**实际编码后的 AI 规划器根本不读 `live_snapshot`**：

| 常量 | 位置 | 值 |
|---|---|---|
| `MODS` | `tools/scripts/ai_planner.py:52` | `D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley\Mods`（**硬编码**） |
| `WORKER` | `tools/scripts/ai_planner.py:53` | `MODS\AutoFarmWorker` |
| `TILES_FILE` | `tools/scripts/ai_planner.py:58` | `Worker\data\farm_tiles.json` ← **真正的感知输入** |
| `RESULT_FILE` | `tools/scripts/ai_planner.py:59` | `Worker\data\ai_result.json` |
| `DIRECTIVE_FILE` | `tools/scripts/ai_planner.py:60` | `Worker\data\ai_directive.json` |

`live_snapshot.json` 是**另一条并行的、AI 没有使用的**通道，只被 `state_report.py` / 人使用。文档与实现不一致，属于高价值的误导源。

**完整闭环（实际时序）**：

1. `AutoFarmWorker` 每 `TileMapIntervalSeconds`（默认 30）写 `data/farm_tiles.json`（覆盖式）—— `ModEntry.cs:334-343` 节流，`ModEntry.TileMap.cs:453-469` 写盘。
2. `ai_planner.py --watch` 每 `--poll`（默认 15 秒）读一次 `farm_tiles.json`（`start_planner.py:154`），用 `should_plan()` 判断是否值得调模型（`ai_planner.py:548-585`）。
3. 调 DeepSeek → 校验 → 覆盖写 `ai_directive.json`（`ai_planner.py:499-502`）。
4. `AutoFarmWorker` 每 `AiDirectivePollSeconds`（默认 20）轮询该文件（`ModEntry.Ai.cs:132-135`），比对 `mtime`，变了才装载（`ModEntry.Ai.cs:152-161`、`243-250`）。
5. 装载进 `_pending` 队列，逐条执行；计划收尾时写 `ai_result.json`（`ModEntry.Ai.cs:468-524`）。
6. 第 2 步读到新的 `ai_result.json` → `state_fingerprint()` 变化 → 「上一轮计划已跑完」→ 立刻再规划（`ai_planner.py:536-545`、`572-574`）。

> **这个闭环在第 6 步闭合成了正反馈空转**：计划被全量丢弃 → 世界毫无变化 → 但 `ai_result.json` 的 `finished_at` 变了 → 规划器认为“上一轮跑完了” → 立刻再花一次 API 钱生成一份同样会被丢弃的计划。`planner.log:1685 / 1720 / 1757` 连续三次触发都是「触发规划：上一轮计划已跑完」，间隔 25~40 秒，而农场状态指纹（`break_stone 241 / clear_weed 443 / …`）**逐轮完全一致**。

### 1.2 JSON schema 字段表

#### (a) `stardew-farm-tiles/1` —— 感知输出（`ModEntry.TileMap.cs:44`）

| 字段 | 类型 | 语义 |
|---|---|---|
| `schema` | string | `stardew-farm-tiles/1`（`TileMap.cs:44,435`） |
| `generated_at` | string | `yyyy-MM-dd HH:mm:ss`，**本地时间**（`TileMap.cs:436`） |
| `liveness.{world_advancing,game_time,day,seconds_since_clock_moved,warning}` | bool/int/double/string | `world_advancing` = 游戏内时钟 20 秒内是否动过（`TileMap.cs:85-89`）；`warning` 仅停摆时出现 |
| `save.{season,day,year,money,player_xy,stamina,max_stamina}` | — | 存档摘要（`TileMap.cs:471-479`） |
| `save.{location,on_farm}` | string/bool | **玩家所在地图名**（`TileMap.cs:496-497`） |
| `save.farm_entry_xy` | int[2] | 不在农场时给出“从屋里出来会落在哪”（`TileMap.cs:499-503`）。**实测恒为 `[64,15]` 硬编码兜底** |
| `summary.{tiles_scanned,crops,ripe,unwatered,empty_dirt,weeds,stones,twigs,trees,grass,action_pool_size}` | int | 汇总（`TileMap.cs:439-445`） |
| `action_pool[]` / `tiles[]` | array | 动作池见 §1.3；`tiles[]` 逐格：`xy`、`terrain`、`dirt`、`crop{id,name,phase,day_in_phase,dead,ripe}`、`tree{stage,stump,tapped}`、`object{id,name,big_craftable,ready}`、`blocked`、`can[]`、`tool`（`TileMap.cs:394-431`） |

#### (b) `stardew-live-snapshot/1` —— 并行的观测通道（`SurroundingsSnapshot.cs:35`）

路径 `Mods/AutoFarmPlanner/data/live_snapshot.json`（`SurroundingsSnapshot.cs:54`），**覆盖式** `File.WriteAllText`（`:69`）。节流 `SnapshotMinIntervalSeconds` 默认 30（`Models.cs:28`），触发于 `TimeChanged`（游戏内每 10 分钟）＋ `WriteSnapshot()`（`AutoFarmPlanner/ModEntry.cs:67-86`）。顶层段：`schema`、`generated_at`、`save`、`player`、`location`、`farm`、`mine`、`signals`（`:87-98`）。
`save` = `farm_name,player_name,year,season,day,time_of_day,is_multiplayer,weather`（`:108-126`，时间戳同样是**本地时间**）。
`player` = `location,tile,health,max_health,stamina,max_stamina,money,farming_level,mining_level,tools{hoe,axe,pickaxe,watering_can,fishing_rod,weapon},inventory_count`（`:141-188`）。
每个字段独立 `try/catch`，API 变化只丢一个字段（`:26-28`）—— **工程质量全项目最高**。**但 AI 规划器不读它**，消费方只有 `state_report.py` 等工具。

#### (c) `stardew-ai-directive/1` vs `/2` —— 未被强制校验的版本错位

C# 侧常量是 `stardew-ai-directive/1`（`AiDirective.cs:42`），Python 侧写的是 **`/2`**（`ai_planner.py:484`）。**关键事实：`ExpectedSchema` 从未被用于校验** —— 全仓库对它的引用只有两处，均为「生成示例文件时打印」（`ModEntry.Ai.cs:678`、`:759`）。版本号对不上也照样接受。

字段（`AiDirective.cs:44-127`，每个字段显式带 `[JsonProperty]`）：

| 字段 | 类型 | 语义 / 是否参与判断 |
|---|---|---|
| `schema` / `issued_at` / `reason` / `notes` / `goal` | string | 仅记录（`issued_at` 见 `AiDirective.cs:48`；`goal` 供回检） |
| `expires_at` | string | **“整套系统的安全阀”**，过期 → 回落规则队列（`:52-58`） |
| `mode` | string | 白名单 `auto/farm/mine/fish/ranch`；非 auto/farm 即“让路”（`:60-67`、`ModEntry.Ai.cs:221-222`） |
| `focus` / `avoid` | string[] | 活种类白名单/黑名单，交集合（`:69-75`） |
| `action` | string | 一次性动作：`none/sleep/unstick/reload`（`:77-82`） |
| `confidence` | double | **仅记录，不参与判断**（`:88-90`） |
| `plan_basis` | string | 计划所依据的 `farm_tiles.json.generated_at`，用于时效校验（`:111-119`） |
| `plan[]` | array | 决策主体（`:325-349`）：只有 `action`(string)、`xy`(int[2])、`id`(string)。刻意极小 —— “LLM 只说干什么，不说怎么走”（`:17-22`） |

**`expires_at` 安全阀实测失效**：Python 写入的是**空字符串**（`ai_planner.py:487`），而 `IsExpired()` 解析失败时 `return false`（`AiDirective.cs:143-145`，注释写明“格式不对 → 宽松处理，不算过期”）。二者相加 ⇒ **安全阀永不触发**，`ModEntry.Ai.cs:204` 的过期分支是死代码 —— 一个“看起来有、实际是空”的防护。

#### (d)(e)(f) 其余 schema

- `stardew-ai-result/1`（`ModEntry.Ai.cs:488-508`）：`schema,finished_at`（本地时间，`Ai.cs:491`）`,plan_basis,goal,elapsed_seconds,done,skipped,failed,details[]`；`details` 元素形如 `DONE <desc>` / `SKIP <desc> — <原因>` / `FAIL <desc> — <原因>`（`Ai.cs:541/557/562`）。**好设计**：成功与否取自世界状态（`PostCheckFor`，`ActionExec.cs:182-229`），不取自决策方自述 —— 新项目应保留。
- `stardew-incident-report/1`（`Watchdog.cs:501-524`）：`schema,time,reason,escalations,unblocks,last_action,pending_tasks,blocked_tiles,save{...},note`。
- 知识库导出（`ModEntry.Knowledge.cs:29-63`）：`crops.raw.json`、`objects.raw.json`、`meta.json`，均覆盖式 `File.WriteAllText`。

> **实测：知识链路从未跑通。** `Mods/AutoFarmWorker/knowledge/` 下**只有 `strategy.md`（24 KB）**，没有规划器要找的 `crops.md` / `tools.md`（`ai_planner.py:181`），于是注入占位文本（`:191-197`）：「知识库尚未生成……请只依据事实摘要中的 summary 做保守决策」。**`crop_economics.json` 那 11 KB 经济学数据在本次 39 条计划的生成中完全没进入 prompt。**

### 1.3 action pool（动作池）—— 语义、前置条件、代价

动作池由 `ActionOf(TileInfo)` 生成（`ModEntry.TileMap.cs:275-316`），每项 `{id:"A<n>", action, xy, tool}`（`:384-389`）。**`id` 只是序号、不含语义、每轮重新编号** —— 模型跨轮引用 `A141` 是无效引用（它却照抄，见 `planner.log:1732-1751`）。
执行器白名单 `LegalActions`（`ActionExec.cs:42-47`）与 Python 侧 `LEGAL`（`ai_planner.py:428-430`）**是两份硬编码，靠手工同步**（缺陷 D5）。

格式：`动作` — 池中生成条件（`TileMap.cs`）｜执行前置（`ActionExec.cs:PreCheckFor`）｜实现｜代价。

- **`water`** — 有作物且未浇（:284）｜耕地/有作物/非雨/`needsWatering()`/有水壶（:74-80）｜**直接改 `d.state.Value = HoeDirt.watered`**（`:328`，非模拟输入）｜水壶
- **`harvest`** — 作物成熟（:283）｜未枯死且 `fullyGrown`（:82-90）｜**反射调 `Crop.harvest`**，只传前 3 参（`:350-376`；1.6 签名带 `JunimoHarvester` 可选参）｜无工具
- **`plant`** — 空耕地（:311-313）｜无作物/有种子/`canPlantThisSeedHere`（:92-97）｜`d.plant(...)` + `SeedUtil.ConsumeOne`（`:396-401`）｜需种子
- **`clear_dead`** — 作物 `Dead`（:282）｜`dead==true`（:99-102）｜**直接 `d.crop = null`**（`:418`）｜锄头
- **`clear_weed`** — 名含 `Weeds` 或 `ItemId=="0"`（:293,296）｜`IsWeeds()`（:104-107）｜`Grass`→移除地形，物件→`objects.Remove`（`:434-453`）｜锄头
- **`clear_twig`** — 名含 `Twig` 或 `ItemId=="294"`（:294,297）｜`IsTwig()`（:109-112）｜`objects.Remove`（`:466-469`）｜斧头
- **`break_stone`** — 名含 `Stone` 或 `ItemId∈{2,343,450}`（:295,298-299）｜`IsBreakableStone()`/有镐（:114-118）｜`ResourceClump`→移除，否则 `objects.Remove`（`:483-499`）｜镐
- **`break_clump`** — 地形是 `ResourceClump`（:310）｜类型判断（:120-122）｜`terrainFeatures.Remove`（`:485`）｜镐
- **`chop_tree`** — `Tree` 且非树桩（:307）｜非树桩/有斧（:124-128）｜**走 `Tool.DoFunction`**（真实工具路径，保掉落/动画），坐标须 ×64（`:506-528`）｜斧头；**很耗时**
- **`remove_stump`** — `Tree` 且 `TreeStump`（:307）｜**`GetAxeLevel() >= 1`（铜斧）**（:130-136）｜同上｜铜斧以上
- **`chop_bush`** — 地形类型名 `Bush`（:309）｜类型名判断/有斧（:138-142）｜同上｜斧头
- **`scythe_or_till`** — 地形是 `Grass`（:305）｜`tf is Grass`（:144-146）｜移除 `terrainFeatures`（`:434-439`）｜锄头/镰刀

**一致性核查**：
- 两份白名单当前一致（12 个动作），但**无任何自动校验**。
- **真实语义错配**：`clear_dead` 在 `BuildTaskFor` 里被归到 `TaskKind.Till`（`ActionExec.cs:306`）—— “清枯苗”被当成“翻地”，会影响 `AiFilterCandidates` 的 focus/avoid 过滤（`ModEntry.Ai.cs:299-303`）。
- **`plant` 确实不在本存档池中**：`empty_dirt=0`，模型自己在 `planner.log:1657/1694` 观察到“池中也没有 plant 动作” —— 逻辑正确。
- **代价信息完全缺失**：池里只有 `tool`，没有耗时/体力/距离。模型只能靠 `ai_planner.py:134-145` 的文本 `ACTION_HINT` 猜排序。

### 1.4 事务与竞态保护 —— 结论：**只有“吞异常”，没有真正的竞态保护**

| 机制 | 存在？ | 证据 |
|---|---|---|
| 原子写（`.tmp` + `Move`/`Replace`） | **否** | 所有写盘都是裸 `File.WriteAllText`：`TileMap.cs:460`、`Ai.cs:508`、`Ai.cs:676`、`Watchdog.cs:528`、`SurroundingsSnapshot.cs:69`、`Knowledge.cs:58,121`。grep `.tmp`/`File.Replace`/`File.Move` **零命中** |
| 文件锁 | **仅 Python→Python** | `msvcrt.locking` 单实例锁（`ai_planner.py:992-1051`），只防两个规划器互踩 |
| 版本号 / 世代号 | **否** | 只有 `schema` 字符串，且不校验 |
| 时间戳新鲜度校验 | **部分** | Python 侧 `SNAPSHOT_STALE_SECONDS = 150`（`ai_planner.py:533`）拒绝过期快照 —— **全项目唯一真正生效的竞态防护**。C# 侧读指令时**无任何新鲜度校验** |
| 半截文件处理 | **弱** | C#：解析失败→Warn→保留上一版（`ModEntry.Ai.cs:170-176`）；Python：`load_json()` 一律 `except: return default`（`ai_planner.py:102-106`） |

**风险实例**：Python 用 `io.open(...).write(json.dumps(...))` 直接覆写 5458 B 的 `ai_directive.json`（`ai_planner.py:501-502`），Worker 每 20 秒轮询。撞上的概率不高但非零；一旦撞上 Worker 会 Warn 并沿用上一版 —— **表现是“计划没被执行，但日志里只有一行 Warn”**。这类“静默降级”是本项目的通病。

**更本质的时序缺陷**：写指令后**没有任何确认机制**知道 Worker 是否装载成功。两端唯一握手是 `ai_result.json.finished_at`，而它**只要计划“处理完”就更新，不管是被执行还是被丢弃**（`ModEntry.Ai.cs:543-544` 的 `AiNoteSkipped` 也计入 `_aiPlanFinished`，达阈值即 `AiFinishPlan()`）。**“被全量丢弃”与“圆满完成”在这个协议里无法区分** —— 即 §5 缺陷 D1。

---

## §2 执行层实现（AutoFarmWorker）

### 2.1 执行模型：**帧驱动 + FIFO 队列 + 游戏内 `PathFindController`**，不是协程

驱动入口 `OnUpdateTicked`（`ModEntry.cs:308-373`）：`WatchdogTick()` :315 → `CheckWorldStall()` :316 → `TickLiveness()` :321 → `if(!IsPlayerFree) return` :323 → `TickDirectMode()` :328 → `TickPendingTasks()` :331（每帧推进“走过去→干活”）→ TileMap 节流写盘 :334-343 → **每 `IntervalMs`(500ms)**：`AiPoll()/AiTick()` :353-354、`ShouldSleepNow()→TrySleep` :357-361、`PlanWork()` :363、`ReportStallIfAny()` :366 → `catch → this.Enabled=false` :368-372（出异常即自动停机）。
**顺序是刻意的**：看门狗与活性检测必须挂在 `IsPlayerFree` 之前（`:312-321` 注释），否则被菜单/对话挡住时它们永远没机会跑。

**“队列”本体**：`private readonly List<WorkTask> _pending`（`ModEntry.cs:66`），只当 FIFO 用（`_pending[0]` + `RemoveAt(0)`），**无优先级、无并发**。`WorkTask` 是**数据 + 委托**的组合（`ModEntry.cs:384-414`）：`Kind`(enum)、`LocationName`、`Tile`、`Action<GameLocation,Point> Act`、`Need`(工具)、`Label`(可读名，因为 `Till` 兼播种/翻地导致日志分不清 —— `:399-407`)、`AiItem`(回检用)。

**关键纠正**：`docs/ARCHITECTURE.md:75-87` 说“引擎每帧自动推进 controller，我们在 TickPendingTasks 里检查”，方向对；但文档 §二 描述的“按距离排序取前 N 个”是**旧的 C# 自动规划路径**，在当前配置下**根本不执行** —— `CodePlannerEnabled=false`（`configs/AutoFarmWorker.json`，默认 `ModEntry.cs:1656`），`PlanWork()` 在 `ModEntry.cs:1656-1661` 直接 `return`。**当前唯一的大脑是 LLM 的计划。**

### 2.2 动作原语实现方式分类

- **直接改数据**（绕过掉落/动画/结算）：`water`、`clear_dead`、`clear_weed`、`clear_twig`、`break_stone`、`break_clump`、`scythe_or_till`（`ActionExec.cs:321-504`）。⚠️ 对“清障”影响小，但 `break_stone` 直接 `objects.Remove` **不会掉石头/矿石/晶球**。
- **反射调游戏方法**：`harvest`（`:350-376`）✅ 正解 —— 1.6 的 `Crop.harvest` 签名带可选 `JunimoHarvester`，直接写 C# 会 CS1503（注释 `:345-347`）。
- **走真实工具 `Tool.DoFunction`**：`chop_tree`、`remove_stump`、`chop_bush`（`:506-528`）✅ 正解 —— 手动改 `tree.health`/`stump` 会绕过掉落与树倒动画，且 `stumpFall()` 不存在（实测 CS1061）。**注意坐标须 ×64**。
- **`HoeDirt.plant` 官方 API**：`plant`（`:396`）✅ 正解。

**没有使用任何模拟输入（不注入按键/鼠标）**，全部走游戏对象 API 或反射 —— 这是正确的技术路线。

### 2.3 寻路实现

同地点寻路（`ModEntry.cs:578-628`）的核心是五行：

```csharp
Point navTarget = this.ResolveNavTarget(loc, task.Tile);   // :585 终点必须是"人站得上去的格"
var ctrl = new StardewValley.Pathfinding.PathFindController(Game1.player, loc, navTarget, 0); // :589
Game1.player.controller = ctrl;                            // :592
bool noPath = ctrl.pathToEndPoint == null ||
              (ctrl.pathToEndPoint.Count == 0 && !this.NearEnough(loc, navTarget));  // :596-597
```

三处设计是**真本事**，值得复用：(1) `ResolveNavTarget`（`:904`）—— 障碍物自身那格在通行判定里不可通行，以它为终点会让 A* 立刻失败，故终点须另选可站立格；(2) **发起后立刻验证 `pathToEndPoint` 是否非空**（`:596-607`），无解立刻放弃不空等（`:594-607` 注释明说要根治“控制器挂着但人不动”）；(3) 超时**按路径步数动态算** `Math.Min(10.0 + steps*0.5, 120.0)`（`:618-621`），修复“97 步的路 15 秒必然走不完”（注释 `:616`）。跨地点寻路见 §2.4。

### 2.4 「跨地点退避中」与「找不到通往 Farm 的出口」——精确代码位置与逻辑

两条 SKIP 出自**同一段跨地点子系统**（`ModEntry.cs`）。

#### 触发点 A：「跨地点退避中」（本次故障的直接产出者）

**`ModEntry.cs:637-648`**（`TickPendingTasks` 的“情况 B：人在别的地点”）：

```csharp
638:  if (Game1.player.controller != null) return;
640:  // 退避期内不再硬闯（出不去还一直重试只会空转刷屏）
641:  if (DateTime.UtcNow < this._crossLocBackoffUntil)
643:      this.DiscardTask("跨地点退避中");
644:      return;
647:  this.BeginCrossLocation(task, cur, loc);
```

**`ModEntry.cs:1105-1112`** 有**第二处完全相同的闸门**（`BeginCrossLocation` 入口）：`if (DateTime.UtcNow < this._crossLocBackoffUntil) { this.DiscardTask("跨地点退避中"); return; }`。

`DiscardTask`（`:664-675`）从队首移除并调 `AiNoteSkipped(task, reason)`（`:673-674`），后者把中文原因写进 `_aiPlanResults`（`ModEntry.Ai.cs:541`）—— **这就是 `ai_result.json` 里那 39 条 `— 跨地点退避中` 的来源。**

**退避怎么被点亮**（`:442-468`，`_awaitingLocationChange` 的 12 秒等待超时分支）：`_crossLocAttempts++`（`:451`）→ `_crossLocFailStreak++`（`:454`，全局累计、不随换任务清零）→ 当 `>= 3` 时清零连击并 `_crossLocBackoffUntil = UtcNow.AddSeconds(30)`（`:456-459`）。
**退避的清除点**只有两处：被超时分支重置（`:458`，但立刻在 `:459` 重新点亮，**等效于永不解除**）、看门狗软复位（`Watchdog.cs:260`）与 `afw` 命令（`ModEntry.cs:2983`、`ModEntry.Ai.cs:642`）。

> **为什么 39 条会在 0.6 秒内全灭**：退避生效期间，**每一条**进入 `TickPendingTasks` 的农场任务都**无条件**命中 `:641` → `DiscardTask` → 取下一条；390 条也只需 0.6 秒，计划条数再多都“跑得完”。与实测 `elapsed_seconds=0.6, done=0, skipped=39` **完全吻合**。

#### 触发点 B：「在 FarmHouse 找不到通往 Farm 的出口」

**`ModEntry.cs:1131-1147`**：

```csharp
1134:  if (this.TryWalkToLocation(cur, target.Name))       // 返回 true → 挂起等地图切换
1135:  { this._awaitingLocationChange = true; ... return; }
1142:  // 找不到出口 → 干脆放弃这条跨地点任务，绝不靠瞬移硬来。
1144:  this.Monitor.Log($"在 {cur.Name} 没找到通往 {target.Name} 的出口，...", LogLevel.Trace);
1145:  this.DiscardTask($"在 {cur.Name} 找不到通往 {target.Name} 的出口");
```

**只有 `TryWalkToLocation` 返回 `false` 才会走到 `:1145`。** 该函数（`:1191-1284`）的流程：
1. `FindWarpTiles(cur, target)`（`:1194`）—— 用**游戏自己的碰撞判定** `isCollidingWithWarpOrDoor` 全图扫描（`:1302-1345`，反射取方法，`Public|NonPublic`）。理由写在 `:1296-1298`：不猜字段语义，直接问游戏“这一格算不算传送点”。
2. `CollectExitCandidates`（`:1197`）—— 5 个来源：`interiorDoors` / `doors` / `getWarpPointTo` / `warps.XY+TargetXY` / 瓦片 `Action|TouchAction`（`:1356-1488`）。
3. 逐个候选：`IsTileInsideMap`（`:1214`）→ 构造 `PathFindController` 看 `pathToEndPoint.Count > 0`（`:1220-1229`），通过即 `return true`。
4. 允许**一次** `TryUnstick` 重试（`:1234-1248`）—— 覆盖“角色自己站在不可通行格（床上/家具缝里）”导致 A* 从坏起点出发算不出路径。
5. 全部候选失败 → **Info 级日志列出所有被否候选**（`:1256-1260`）→ 瞬移兜底（`:1265-1281`）→ 仍失败才 `return false`（`:1283`）。

**为什么瞬移兜底（`AllowTeleportFallback` 默认 true，`ModConfig.cs:237`）也没救回来？** 看 `:1265-1281`：`Point? safe = this.FindSafeLanding(target, cur.Name); if (safe != null) { Game1.warpFarmer(...); return true; }`。而 `FindSafeLanding`（`:1550-1572`）遍历 `target.warps` 找 `w.TargetName == fromLocName` 的那条 warp，取 `new Point(w.X, w.Y)` 再交 `ShiftOffWarpTile` 挪开门口。**它返回 `null` 的两个条件**：`target.warps` 里没有 `TargetName == "FarmHouse"` 的条目，或遍历中抛异常（`:1570` 是空 `catch`）。**只要返回 `null`，瞬移兜底被完全跳过，直接 `return false` → `:1145` 的「找不到通往 Farm 的出口」。**

> **无法从静态代码断定 `Farm` 的 `warps` 里有没有那条回程条目 —— 标记「未确认」。** 但有**强旁证**：`farm_tiles.json.farm_entry_xy` 实测为 `[64,15]`，即 `WatchdogFindFarmLanding()` 的 `GetMainFarmHouseEntry()` 分支返回无效值并落到硬编码兜底（`Watchdog.cs:337-372`）⇒ **运行时确实取不到“农舍↔农场”的权威坐标**，与 `FindSafeLanding` 依赖 `warps` 反查同源。瞬移兜底失效高度可疑，但确切原因需在游戏内跑 `afw exit Farm` 定论 —— 项目**自己就提供了这个诊断命令**（`ExitDebug.cs:27-129`）。

#### 这是不是一个结构性缺陷？—— **是，而且是本次停摆的决定性原因**

1. **退避的粒度错了**：`_crossLocBackoffUntil` 是**单个全局标量**（`ModEntry.cs:89`），它把“从 FarmHouse 到 Farm 这条路走不通”泛化成“**所有**跨地点工作停摆 30 秒”。而玩家 `location` 与所有任务目标地点在这 30 秒内都没变 ⇒ 退避解除后必然再次失败、再次点亮。**这是一个不会自愈的循环。**
2. **丢弃策略把“路径不可达”降级成了“逐条跳过”**：`DiscardTask`（`:664-675`）的注释（`:650-663`）自己承认这一点，甚至写了历史事故“角色被带进矿洞后，AI 计划 39 条被逐条丢弃却永不收尾”（`:660`）。修复方式是让 `AiNoteSkipped` 计入 `_aiPlanFinished` 以便**收尾**（`ModEntry.Ai.cs:539-544`）—— 但**这只修好了“计划能收尾”，没修“为什么做不了”**，于是收尾变成正反馈（详见 §5 D1）。
3. **缺少“把角色送到工作地点”这一独立的、有结论的能力**：整套架构里**移动是每个动作任务的附带步骤**，而不是可被规划、可被重试、可被诊断、成功后会被记住的前置条件。所以 39 个动作各自独立回答“我怎么到 Farm”39 次、全部失败，且没有任何一层能说“**当前无法离开 FarmHouse**，别再下发农场任务了”。

**结论**：不是 bug 级，是**架构级** —— 缺失“位置/可达性”这一层抽象（缺陷 D2，见 §5）。

---

## §3 可靠性机制清单

### 3.1 全量清单与实效判定

| # | 机制 | 位置 | 处理什么故障 / 触发条件 | 实效判定 |
|---|---|---|---|---|
| 1 | 整机看门狗 `WatchdogTick` | `Watchdog.cs:132-183` | “有活却一件干不成”；队列有活 且 180 秒无 `PopTask(failed:false)` | ❌ **被自身判据短路，见 3.2** |
| 2 | 三级自救 L1/L2/L3 | `Watchdog.cs:199-242` | L1 软复位 `:248-267`（内部状态乱/误拉黑）；L2 逃离 `:273-317`（人在错地图/被围死）；L3 强制推进一天 `:218-235`（世界僵局） | ⚠️ 逻辑正确但**因 #1 从不被触发**；L2 落点走**硬编码兜底 `(64,15)`**（`:337-372`），与故障现场吻合 |
| 3 | 停机保护 `WatchdogTrip` | `Watchdog.cs:472-488` | 反复卡死污染存档；累计自救 ≥ `WatchdogMaxEscalations`(5) → 停机 + 写 `incident_report.json` | ✅ 设计合理，**触发条件依赖 #1 因而同样失效** |
| 4 | 菜单/对话解锁 | `Watchdog.cs:387-462` | NPC 搭话 / 弹窗；`IsPlayerFree==false` 超 25 秒 | ✅ **有效**，正确挂在 `IsPlayerFree` 检查之前（`ModEntry.cs:315`） |
| 5 | 矿洞让路 | `Watchdog.cs:151-156,319-331` | 避免把玩家从矿里拽出；`loc is MineShaft` | ✅ 有效，用“结果状态”而非“谁发起的”判断 |
| 6 | 世界停摆告警 + 失焦暂停自动关闭 | `FocusPause.cs:131-151,73-119` | 游戏被暂停；时钟 60 秒未动 / 启动时 | ✅ **有效且高价值**。`WorldIsAdvancing()` 把该事实写进快照（`TileMap.cs:85-89`），使上游可拒绝基于冻结数据规划 |
| 7 | 跨地点退避 | `ModEntry.cs:456-459` | 防“出不去还一直硬闯”；跨地点失败连击 ≥3 | ❌ **有害**：全局标量 + 30 秒窗口 + `DiscardTask` 循环内不断重新点亮 → 本次停摆直接成因 |
| 8 | 目标格黑名单 | `ModEntry.cs:781-796,806` | 反复走不到的格子不再霸占队列；同格失败 ≥3 | ❌ **当前配置下是死代码**：唯一消费点 `:1745` 在 `PlanWork()` 内，而它在 `CodePlannerEnabled=false` 时于 `:1656-1661` 提前 `return`；AI 路径走 `AiLoadPlan()`（`Ai.cs:367-459`）**完全不查黑名单** |
| 9 | 降级直执 + 强制自救 | `ModEntry.cs:743-757,719-723` | 地形进不去时跳过走位；连续走不到 ≥4（开关）/ ≥8（强制） | ⚠️ 逻辑有效但**跨地点故障永远不触发**：AI 路径下靠 `PopTask(failed:true)` 计数，而跨地点走 `DiscardTask`，`_giveUpStreak` 既不清零也不累加（`:670-671` 注释明说） |
| 10 | 控制器卡死检测 + 脱困 | `ModEntry.cs:867-889,817-861` | controller 挂着但人不动（3 秒位置不变）/ 卡在碰撞缝里 | ✅ 有效。含两处正确的历史修复：不在重新发起寻路时清零计数（`:609-613`）；脱困**朝目标侧挪**（`:824-825`） |
| 11 | 寻路无解快速失败 + 动态超时 | `ModEntry.cs:596-607,618-621` | A* 算不出路径却干等 / 长路径被固定超时误杀 | ✅ **高价值**。根治“控制器挂着人不动”；超时按步数算 `min(10+steps*0.5,120)`，修复“97 步路 15 秒走不完” |
| 12 | 跨地点等待超时 | `ModEntry.cs:442-468` | 地图切换卡住；12 秒未切换 | ⚠️ 从 6 秒放宽到 12 秒（`:445-446`）—— **在反复调参掩盖“出口找不到”的真问题** |
| 13 | 瞬移兜底 `AllowTeleportFallback` | `ModEntry.cs:1265-1281` | 出口不可达；`FindSafeLanding() != null` | ❌ **依赖 `warps` 反查，本次未生效**（§2.4；确切原因需游戏内 `afw exit Farm` 定论，「未确认」） |
| 14 | 种子副作用校验 | `Diagnostics.cs:211-260` | `removeItemFromInventory` 无 count 参数会清空整叠；每次播种 | ✅ **必要**。代价：“种 5 株、蒸发 5 叠、烧掉 430g，日志里一条异常都没有”（`:216-219`） |
| 15 | 出口诊断 `afw exit` | `ExitDebug.cs:27-129` | “找不到出口”无法定位；人工触发 | ✅ **全项目最有价值的运维工具**，只读、不动角色 |
| 16 | 停滞报告 `ReportStallIfAny` | `Diagnostics.cs:374-397` | 有活无任务；队列空 且 世界有可做的活 | ⚠️ AI 路径下队列通常非空（39 条挂着），`:379` 直接 `return` ⇒ 同样不报 |
| 17 | 落点安全化 `ShiftOffWarpTile` | `ModEntry.cs:1578-1600` | 落在门口被立刻弹回 | ✅ 有效（修过“Warping to Farm 刷 971 次”的历史事故，`:1559-1563`） |
| 18 | 单实例锁（规划器） | `ai_planner.py:992-1051` | 两个规划器互相覆写计划 | ✅ **有效**。`msvcrt` 字节区间锁（进程死自动释放），且正确把 `PermissionError` 判为“已被占用” |
| 19 | 快照过期拒绝 | `ai_planner.py:533-557` | 游戏关着时基于旧文件规划；年龄 > 150 秒 | ✅ **有效**，全项目唯一真正生效的时效防护 |

### 3.2 看门狗为何在这次故障中完全没响 —— 精确代码

**`ModEntry.Diagnostics.cs:188-199`**：

```csharp
188: internal bool IdleIsLegitimate()
189: {
190:     try
191:     {
192:         if (this._pending.Count > 0) return true;   // 有任务在手，不算空闲
193:         var f = this.ScanWorldFacts();
194:         if (!f.FarmLoaded) return true;
195:         if (this.IsExhausted()) return true;
196:         return !f.HasActionable;
197:     }
198:     catch { return true; }
199: }
```

`WatchdogTick` 在 `Watchdog.cs:167-172` 调用它，返回 `true` 就刷新 `_wdLastProgressAt` 并 `return` —— **永不升级**。

**这就是致命的组合**：

- `TickPendingTasks` 在退避期间**并没有清空队列**（`DiscardTask` 一次只丢队首，`ModEntry.cs:666-667`），而 `PlanWork()` 又因 `AiPlanRunning==true` 保持 `_planHadWork=true`（`ModEntry.cs:1641-1645`）；
- 于是 `_pending.Count > 0` 恒成立 ⇒ `IdleIsLegitimate()` 恒为 `true` ⇒ 看门狗认为“有任务在手，一切正常”。

> **讽刺的是**，该函数的 XML 注释（`Diagnostics.cs:180-187`）写着它就是为了“不再被死锁骗过”而替换掉旧的 `_planHadWork`。它把“队列非空”当成了“有进展”的同义词，于是**换了一个同样会被骗过的判据**。这是一个典型的“缺抽象导致的补丁”——它试图用更聪明的启发式修补一个本应由**显式进度/健康状态**回答的问题。

### 3.3 哪些属于“缺抽象导致的补丁”

按“补丁浓度”从高到低：

| 补丁 | 它想弥补的缺失抽象 | 证据 |
|---|---|---|
| **跨地点退避 + 等待超时 12 秒 + `afw exit` 诊断** | 缺“可达性”层：系统无法表达“从 A 到 B 现在是否可通行” | `ModEntry.cs:442-468`、`:456-459`、`ExitDebug.cs`。三处都在处理同一个症状，且注释里明确写了历史事故（“一份 24 条的 AI 计划被整份丢弃”，`:1184`） |
| **`IdleIsLegitimate()` + `ScanWorldFacts()`** | 缺“进度/健康”状态机：无法回答“我现在是否在正常推进” | `Diagnostics.cs:64-199`。用独立世界扫描替代任务生成器输出来打破循环依赖，方向对，但仍用“队列非空”这个坏代理 |
| **`WatchdogFindFarmLanding()` 三层兜底 + 硬编码 `(64,15)`** | 缺“地点拓扑/出入口”抽象：无法统一查询“农舍→农场落点” | `Watchdog.cs:337-372`。**分支 1 与分支 2 是逐字重复的同一段代码**（`:345-352` 与 `:359-366`），只有变量名不同 `farm0/v0` vs `farm/v` —— 这是复制粘贴的痕迹 |
| **`ShiftOffWarpTile` 12 个偏移量逐个试** | 缺“warp 触发范围”抽象 | `ModEntry.cs:1578-1600`。用暴力枚举替代规则 |
| **`FindWarpTiles` 反射 + 全图逐格扫描** | 缺“地图出入口”抽象 | `ModEntry.cs:1302-1345`。农舍 12×12、农场 80×60 全扫，注释自辩“代价可忽略” |
| **`CollectExitCandidates` 5 个来源并集** | 同上，且**来源越多说明越不确定** | `ModEntry.cs:1356-1488`。注释（`:1348-1354`）按“可靠度排序”，但这 5 个来源本身就说明作者不知道正确 API 是哪一个 |
| **工具等级硬判 `GetAxeLevel() >= 1`** | 缺“工具能力”模型 | `ActionExec.cs:130-136`，注释：“这是实测过的硬规则，白跑一趟很浪费” |
| **`TaskKind.Till` 兼播种与翻地，另加 `Label` 打补丁** | 缺任务语义分类 | `ModEntry.cs:399-407`，注释承认“日志里两者都打成 Till，实测排查时完全分不清” |
| **`SeedUtil` 三级判据** | 缺统一的物品分类 | `src/Shared/SeedUtil.cs`；`AiDirective.cs:372-380` 承认 `TaskKind` 需要加成员才能区分 till/plant |

---

## §4 可复用资产（分层）

### 4.0 一个必须先说的方法论问题：探针的可信度分层

`tools/probes/` 下有 **26 个探针**（`Probe`、`Probe2`…`Probe26`），但**只有 5 个留下了实际输出文件**：

| 有实测输出（**可信**） | 仅有源码、无输出（**未验证**） |
|---|---|
| `Probe8`(13.1KB)、`Probe9`(26.2KB)、`Probe10`(7.4KB)、`Probe11`(6.9KB)、`Probe13`(8.3KB) | `Probe`、`Probe2`~`Probe7`、`Probe12`、`Probe14`~`Probe26` |

`docs/ARCHITECTURE.md:319` 说“`tools/probes/` 下 **13 个**工具”，与实际 **26 个**不符（文档未同步）。
**下面的 API 结论严格区分两类**：✅ 有输出佐证 / ⚠️ 仅源码假设。

### 4.1 游戏 API 知识（最有价值的可复用资产）

#### ✅ 有实测输出佐证（`probe8/9/10/11/13_out.txt`）

| 主题 | 结论 |
|---|---|
| **工具与继承链**（probe8） | `StardewValley.Tool : Item`；`Tools.Hoe/Axe/Pickaxe/WateringCan : Tool`。**`Tool.DoFunction(GameLocation, Int32 x, Int32 y, Int32 power, Farmer who)` 是所有工具的统一入口**。`Axe.UpgradeLevel` 是**属性**（`Int32 get_UpgradeLevel()`）⇒ 须用 `GetProperty` 而非字段（对应 `ActionExec.cs:159-172` 的 Property→Field 双重尝试） |
| **地形特征继承**（probe8/10） | `Grass`/`Tree`/`FruitTree`/`HoeDirt` : `TerrainFeature`；**`Bush` : `LargeTerrainFeature`**（不是 `TerrainFeature`）⇒ 解释了 `ActionExec.cs:140` 为何用 `GetType().Name != "Bush"` 字符串比较。**`ResourceClump` 全名 = `StardewValley.TerrainFeatures.ResourceClump`，基类 `TerrainFeature`**（曾猜成 `StardewValley.ResourceClump`） |
| **耕地 API**（probe8） | `GameLocation.makeHoeDirt(Vector2, Boolean ignoreChecks)`、`GetHoeDirtAtTile(Vector2)`、`isTileHoeDirt(Vector2)`、`getTotalOpenHoeDirt()`。`makeHoeDirt` 用于 `ModEntry.cs:2644` |
| **物品类别常量全表**（probe10） | `SeedsCategory=-74`、`VegetableCategory=-75`、`FruitsCategory=-79`、`flowersCategory=-80`、`GreensCategory=-81`、`artisanGoodsCategory=-26` 等，全部落在 `-2`~`-29` 与 `-74`~`-95` 两段 |
| **`BobberBar` 完整字段**（probe11） | `bobberPosition`、`bobberBarPos`、`bobberBarHeight`、`bobberInBar`、`distanceFromCatching`、`difficulty`、`motionType`、`perfect`、`treasure`、`fishSize`、`fishQuality`、`challengeBaitFishes`、`scale`… ⇒ 钓鱼改动的全部抓手 |
| **商店 API**（probe9） | `ShopMenu`：`itemPriceAndStock`(Dict)、`forSale`(List)、`heldItem`/`hoveredItem`(ISalable)、`currency`、`onPurchase`/`onSell`、`BuyBuybackItem(ISalable,Int32,Int32)`、`HandleSynchedItemPurchase(...)`、**`ShopId` + `ShopData`**。另有 **`Utility.TryOpenShopMenu(String shopId, String ownerName, Boolean playOpenSound)`** 及重载 |
| **睡觉 / 时间**（probe9） | `Game1.NewDay(Single timeToPause)`、**`Game1.newDayAfterFade(Action after)`**（`ARCHITECTURE.md:223` 用的就是它）、`Game1.PassOutNewDay()`、`Game1.PollForEndOfNewDaySync()` |
| **`Farmer` 可写性**（probe9） | `{set}`：`Money`、`Position`、`currentLocation`、`ActiveItem`、`ActiveObject`、`CurrentTool`；`{ro}`：`Items`、`Tile`、`TilePoint` |
| **菜单/输入全局态**（probe9） | `Game1.activeClickableMenu`、`InputState input`、`Game1.dialogueUp`、`Game1.eventUp` ⇒ `Watchdog.cs:439-453` 正是用后三个做阻塞解锁。另见 `Furniture`/床：`GetBedSpot()`、`BedType get_bedType()`、`IsBeingSleptIn()`、`DayUpdate()`、`CanModifyBed(Farmer)` |
| **`FarmAnimal`**（probe13） | 字段 `currentProduce`(NetString)、`friendshipTowardFarmer`、`age`、`health`、`happiness`、`fullness`、`wasPet`(NetBool)、`type`、`position`(NetPosition)；方法 `pet(Farmer,Boolean is_auto_pet)`、`GetProduceID(Random,Boolean deluxe)`、`dayUpdate(GameLocation)`、`CanGetProduceWithTool(Tool)`、`Eat(GameLocation)`、`DigUpProduce(GameLocation,Object)`（`Rancher` 用法见 `AutoFarmRancher/ModEntry.cs:186/208/223`） |
| **`AnimalHouse`**（probe13） | `animalLimit`(NetInt)、**`animals`(NetLongDictionary<FarmAnimal,NetRef<FarmAnimal>>)**、`animalsThatLiveHere`(NetLongList)、`piecesOfHay`(NetInt)、`parentLocationName`(NetString)、`ParentBuilding`；**`feedAllAnimals()`**。`ARCHITECTURE.md:301` 提醒“值是 `NetRef`，要再取一次 `.Value`” |

#### ✅ 1.6.15 特有的坑（有输出/实测佐证）

- **SMAPI `ReadJsonFile` 不做 snake_case→PascalCase 转换，但大小写不敏感**：`expires_at`/`plan_basis`/`issued_at` 这类带下划线字段**静默丢失**、不报错、不告警；单词字段（`goal`/`reason`/`mode`/`plan`）不受影响。修复 = 每字段显式 `[JsonProperty("snake_case")]`（`AiDirective.cs:45-127`）+ `SelfTest()` 往返自检（`:204-260`）；`ARCHITECTURE.md:365` 记同一坑。
- **`Crop.harvest` 在 1.6 带可选 `JunimoHarvester` 参数** ⇒ 直接写 C# 调用编译失败 **CS1503**；解法是反射取参数最少且 `ps[0]==int && ps[1]==int` 的重载（`ActionExec.cs:345-376`）。
- **`Crop` 继承 `Object`(System)** ⇒ CS8121；作物在 `HoeDirt.crop`（`ARCHITECTURE.md:361`）。
- **没有 `Tree.stumpFall()`** ⇒ CS1061（`ActionExec.cs:512`）。
- **`performToolAction` 假定工具已处于“使用中”，会读 `lastFarmerToUse` 抛空引用** ⇒ 统一改走 `DoFunction`（`ActionExec.cs:519-521`）。
- **`Farmer.removeItemFromInventory(Item)` 无 count 参数，移除的是整个物品（一整叠）** ⇒ “种 1 株”消耗 16 个种子、**无任何异常**，烧掉 430g 才被发现（`Diagnostics.cs:214-219`）。
- **`Game1.getFarm()` 会抛 `KeyNotFoundException`** ⇒ 改为遍历 `Game1.locations`（`ARCHITECTURE.md:366`）。
- **`Options.pauseWhenOutOfFocus`：界面里已无对应文本（扫遍 Content 下 3560 个文件），但 `Game1._update` 仍读它** ⇒ 一旦为开，失焦时**世界冻结**，快照看着正常却全是旧值（`manifest.json:5`；`FocusPause.cs:16,44-61`；`Probe22.cs` 专探此事）。
- **`isCollidingWithWarpOrDoor` 是判断“这一格是否传送点”的权威方法**，且**跨版本 warp 坐标字段命名不一致**（`X/Y` 与 `TargetX/TargetY` 语义易搞反）⇒ 照猜会拿到**目的地**坐标（农舍只有 12×12 却拿到 (64,15)），寻路目标在图外，实测刷了 937~971 次 warp（`ModEntry.cs:1294-1300,1559-1563`；`Probe26` 专门 IL dump 了 `handleWarps`/`getWarpFromDoor`/`openDoor`/`isCollidingWithWarpOrDoor`/`isCollidingWithWarp`/`isCollidingWithDoors`）。
- **`NetIntList` 只有 `Count`，没有 `phaseDays.Length`** ⇒ CS1061（`ARCHITECTURE.md:362`）。
- **1.6 造物品必须用 `ItemRegistry.Create("(O)"+id)`**（`ARCHITECTURE.md:248`；`AutoFarmTrader/ModEntry.cs:515-517`）。
- **`Map.DisplayWidth` 在个别地点抛异常**，被 catch 吞掉后尺寸变 0 ⇒“所有候选都在图外”⇒ 出口永远找不到；解法改为读图层 `LayerWidth/LayerHeight`（`ModEntry.cs:1490-1494`）。
- **机器判断**：`obj.bigCraftable?.Value == true`；产出看 `readyForHarvest?.Value` + `heldObject?.Value`；投料用 `performObjectDropInAction(Item, Boolean probe, Farmer, Boolean returnFalseIfItemConsumed)`（`ARCHITECTURE.md:305-313`）。

#### ⚠️ 仅源码假设、无输出佐证（**新项目必须先自行验证**）

`Probe12`（`WateringCan` 字段 / `NetInt` 全名）、`Probe14`（矿洞 / 矿石 / 怪物 / 体力血量 / 镐）、`Probe15`~`Probe21`、`Probe22`（失焦暂停）、`Probe23`~`Probe25`、**`Probe26`（IL dumper，方法名已见，但无 dump 输出落盘）**。其中 `Probe26` 的方法清单本身（`PathFindController.handleWarps` 等）是**代码里写死的字符串**，属于“作者认为存在”，不是“已验证存在”。

> **建议**：`Probe26` 的 **IL 反汇编器本体**是全项目最值得带走的技术资产（`Probe26.cs:23-100`，自建 opcode 表、用 `OpCode.OperandType` 推操作数长度）。它把“猜字段语义”换成了“读 IL”。新项目应把这类探针**常态化**（每次游戏更新跑一遍）。

#### 文档中的命令/坑（`docs/COMMANDS.md`）

速查表（完整版见 `COMMANDS.md:11-341`）：`afw on|off|status|scan|layout|reload|sleep|dbg|direct|unblock|wd|ai|why|seeds|kb|tiles|exit|focus`（`ModEntry.cs:162-164`）、`aft on|off|status|dryrun|sell|buy|reload|dump`、`aff on|off|status|cast|reload`、`afr on|off|status|scan|feed|pet|load|collect|reload`、`afp plan|scan|crops|why|reload|snap`、`afm on|off|status|enter|exit|depth|reload`。
`COMMANDS.md:396-403` 的挖矿安全线（血量 <40% / 体力 <20% / 21:00 / 被 4 只以上围 / 下矿门槛血<60%体力<50% / 只打 2 格内）是一份**可直接复用的调参基线**。

### 4.2 数据资产

#### `data/crop_economics.json`（11.1 KB）—— **结构完整、可直接复用**

实测顶层键与结构：

| 顶层键 | 结构 | 内容 |
|---|---|---|
| `_comment` / `_meta` | string / object | `_meta = {version:"1.6", currency:"g", season_days:28}` |
| `spring` / `summer` / `fall` / `winter` | object | 各含 `crops[]`、`best_crop`、`strategy`。实测：春 7 条、夏 6 条、秋 6 条、**冬 0 条** |
| `processing_chain` | object | `keg_wine[]`、`preserves_jar`、`general_rule`、`_comment` |
| `community_center_priority` | object | `tier_S`、`tier_A`、`tier_B`、`key_items`、`_comment` |
| `year_roadmap` | — | 年度路线 |
| `automation_target` | object | `required_mods[]`（Automate Nexus:1063 / Tractor Mod Nexus:1401 / Chests Anywhere Nexus:518 / Auto-Grabber / Sprinklers / 本项目）、`layout_principle` |

**作物记录 schema**（`spring.crops[0]`，逐字段实测）：

```json
{ "id":"Parsnip", "name":"防风草", "seed_cost":20, "sell":35,
  "grow_days":4, "regrow":0, "yield_avg":1.0,
  "profit_per_day":3.75, "tier":"early" }
```

`keg_wine[]` 元素：`{crop, raw, processed, multiplier, note?}`，实测倍数：Starfruit/Pumpkin/Melon/Rhubarb/Grape/Cranberry/Blueberry = **3.0**，**Hops = 12.0**（`note`:"啤酒花→淡啤酒，倍数最高"）。
**评价**：结构清晰、单位诚实（`profit_per_day` 直接给出，模型不必自己算）。缺点：只有 19 条作物、`winter` 为空数组、`tier` 取值域未文档化。**建议整表迁移并扩展。**

#### 农场知识库 —— **实际是断链的**

`ModEntry.Knowledge.cs:29-63` 定义了 `crops.raw.json` / `objects.raw.json` / `meta.json` 的导出（`afw kb`），`build_knowledge.py`（251 行）负责加工成 `crops.md` / `tools.md`。
**但实测 `Mods/AutoFarmWorker/knowledge/` 下只有 `strategy.md`（24363 B），没有 `crops.md` / `tools.md`** ⇒ 规划器注入的是占位文本（`ai_planner.py:191-197`）。
**可作为资产的部分**：`build_knowledge.py` 的加工逻辑 + `ModEntry.Knowledge.cs` 的反射导出逻辑（用 `DataLoader`/`ExportDict` 批量导游戏字典，`Knowledge.cs:46-63`）—— 思路（把游戏数据 dump 成 JSON 再加工成 Markdown 喂给模型）是**正确且值得复用**的，只是从未跑通。

#### 存档解析

`tools/scripts/parse_save.py`（104 行）—— 直接解析存档 XML。范围较小，**未确认**其覆盖度。`export_farm_tiles.py`（359 行）在 Python 侧重算地块，与 C# 的 `farm_tiles.json` 功能重叠（**两份实现，需合并**）。

### 4.3 代码资产分级

#### ✅ 值得复用 / 参考（设计正确、注释说明了为什么）

| 资产 | 位置 | 复用理由 |
|---|---|---|
| **`PreCheck / Execute / PostCheck` 三段契约** | `ActionExec.cs:60-229` | **最佳设计**。动作自带前后置条件，回检判据取自世界状态而非自述。新项目的动作原语就该长这样 |
| **`AiDirective.SelfTest()` + `[JsonProperty]` 显式标注 + 宽松类型** | `AiDirective.cs:44-127,204-260` | 反序列化往返自检，专治“字段静默丢失”（踩过真实坑）；接口面极小的指令模型（只有 `action`+`xy`+`id`）+ 白名单硬校验。**这两个思路应整体保留** |
| **`Tool.DoFunction` + ×64 坐标系 / `Crop.harvest` 反射** | `ActionExec.cs:350-376,506-536` | 砍树与收获的成品解法（保掉落/动画/结算），注释写明了反面教材，可直接搬 |
| **寻路“发起后立刻验证 `pathToEndPoint`” + 动态超时 + `ResolveNavTarget`** | `ModEntry.cs:585-621,904` | 根治“controller 挂着人不动”；超时按步数算；终点必须是可站立格 |
| **`DetectStuckController` + `TryUnstick`（朝目标侧挪）** | `ModEntry.cs:817-889` | 有效的卡死自救，含“不要在哪清零计数”的关键注释（`:609-613`） |
| **`SurroundingsSnapshot`** | `SurroundingsSnapshot.cs:33-629` | **工程质量最高的一段**。逐字段 `try/catch`，游戏更新只丢一个数字而非整份快照；另有 `Summarize()` 给人看 |
| **`TickLiveness`/`WorldIsAdvancing`/`CheckWorldStall`/`FocusPauseEnsure`** | `TileMap.cs:58-110`、`FocusPause.cs:27-151` | **必修概念**：把“世界是否在推进”当一等公民写进快照，让上游拒绝基于冻结数据规划 —— 本项目最有洞察力的发现。附 1.6.15 隐藏开关的成品绕过方案 |
| **其余** | — | `SeedUtil`（`src/Shared/SeedUtil.cs`，246 行）：跨 Mod 统一种子判定 + **精确扣减 1 个**，唯一成功的共享抽象。`WatchdogUnblockMenu`（`Watchdog.cs:433-462`）：对话/菜单解锁（注意 1.6 对话队列挂在说话人身上）。`WriteIncidentReport`（`:491-529`）：结构化事故快照。`FarmLayout`（`FarmLayout.cs`，310 行）：网格切床 + 缓存 + 按离门口远近排序，逻辑自洽（当前未启用）。`Probe26` IL 反汇编器本体（`Probe26.cs:23-100`）。`ModEntry.ExitDebug.cs` 整体（`ExitDebug.cs:27-129`）：只读诊断命令模板 —— 新项目每个易错子系统都该配一个 |

#### ❌ 必须丢弃

| 资产 | 位置 | 丢弃理由 |
|---|---|---|
| 跨地点子系统（退避 + 等待超时 + `FindWarpTiles` + `CollectExitCandidates` + `FindSafeLanding` + `ShiftOffWarpTile`） | `ModEntry.cs:430-473,637-648,1105-1600` | 缺抽象导致的补丁集群（§3.3）。应替换为**显式的可达性查询 + 地点图** |
| `_pending` FIFO 队列 + `TickPendingTasks` + `DiscardTask`/`PopTask` + `IdleIsLegitimate()` | `ModEntry.cs:66,416-724`、`Diagnostics.cs:188-199` | 任务=数据+委托、无优先级、无进度模型；`DiscardTask`/`PopTask` 的区分本身就是在给缺失的“进度状态机”打补丁；`IdleIsLegitimate` 用“队列非空”当“有进展”（§3.2） |
| `PlanWork()` + `FindClear/FindHarvest/FindWater/FindTill/FindPlant` 全套 | `ModEntry.cs:1637-2900` | 与 AI 计划**双头决策**。已被 `CodePlannerEnabled=false` 关掉，却留下大量只被它调用的代码（黑名单、部分诊断）⇒ **一半系统是死的**。应彻底移除，不要保留两套大脑 |
| `WatchdogFindFarmLanding()` | `Watchdog.cs:337-372` | 分支 1/2 逐字重复 + 硬编码 `(64,15)`，且实测取不到真实落点 |
| 26 个探针中的 `Probe`~`Probe21`（除 8/9/10/11/13）、`dist/`、硬编码 `MODS` 路径 | `tools/probes/`、`dist/`、`ai_planner.py:52` | 探针为一次性脚本、无输出无文档，价值已被结论吸收（**保留有输出的 5 个 + `Probe26`**）；`dist/` 是产物不应入库；`MODS` 路径必须参数化 |

### 4.4 运维资产

| 资产 | 位置 | 可用性 |
|---|---|---|
| **`build.ps1`** | `build.ps1`（119 行） | ✅ **质量高，值得整体复用**。三处关键设计：(1) **构建前检查游戏进程**，因 DLL 被锁会导致“部署静默失败”（`:31-39`）；(2) 每个 Mod 部署后 **MD5 校验**（`:96-104`）；(3) 失败汇总 `exit 1`（`:115-119`）。**唯一缺陷：`$Mods` 只有 5 项，漏了 `AutoFarmMiner`**（`:16-22`），而它是实际存在的第 6 个 Mod 且已在 Mods 目录 |
| **`analyze_log.py`**（410 行） | `tools/scripts/` | ✅ **高价值**。刷屏风暴检测、错误归类、**已知故障签名匹配**、任务健康统计（`COMMANDS.md:449-455`）。“同一模式短时间高频重复”正是抓“每帧 warp”那类故障的工具。**建议复用** |
| **规划器启停链路** | 根目录 + `tools/scripts/` | ✅ `启动AI规划器(后台).vbs`（隐藏窗口）、`运行/停止/查看规划器状态.bat`、`planner_daemon.bat`、`planner_ctl.py`（286 行）、`start_planner.py`（143 行，`subprocess.Popen` + 日志重定向，`:116-124`）、`.planner.lock`/`.planner.pid`（单实例，`ai_planner.py:992-1051`） |
| **校验类 Python 工具** | `tools/scripts/`、`data/` | ✅ `state_report.py`（183 行，读 `live_snapshot.json` 出人读报告）、`check_data_json.py`（212 行）、`check_vocab.py`（146 行，能在 CI 里防住“C# 与 Python 两份白名单漂移”= 缺陷 D5）、`verify_economics.py`（2.5 KB） |
| **`configs/*.json`** | `configs/` | ✅ 6 个 Mod 的配置模板齐备 |
| ⚠️ 短板 | — | `check_greenhouse.py` 仅 54 行；`parse_save.py`（104 行）覆盖度**未确认**；`export_farm_tiles.py`（359 行）与 C# 的 `farm_tiles.json` **功能重叠**，应择一；`secrets/deepseek.key` 实测为**空文件（0 字节）**，API key 走环境变量（`ai_planner.py:91-97`），`.gitignore` 已忽略 secrets |

---

## §5 失败根因结论

### 5.1 一段话说清为什么停摆

这套架构把**“把角色送到工作地点”当成了每个动作任务的附带步骤，而不是一个独立、可查询、可失败的能力**。存档 Wahaha 里玩家在 `FarmHouse`（`farm_tiles.json.save.location=FarmHouse, player_xy=[2,11]`），而 AI 下发的 39 条动作全部指向 `Farm`。于是每一条动作都要**各自独立地**回答“我怎么从农舍走到农场”——而这个子系统既查不出出口（`ModEntry.cs:1144-1145` 「在 FarmHouse 找不到通往 Farm 的出口」），瞬移兜底也因 `FindSafeLanding()` 从 `warps` 反查不到落点而失效（`ModEntry.cs:1265-1281`、`1550-1572`）。失败被 `DiscardTask` 记成**“跳过”而非“失败”**（`ModEntry.cs:664-675`），既不累加 `_giveUpStreak`（因此 8 次阈值的安全自救永不触发）、又不停留在任何可观察的失败状态，只往 `ai_result.json` 写一条 `— 跨地点退避中`。紧接着，跨地点连续失败把 30 秒全局退避点亮（`ModEntry.cs:456-459`），而重新规划**并不会重置这个全局标量**——于是后续每一条任务都在 `ModEntry.cs:641-645` 被无条件丢弃，39 条在 **0.6 秒内**全部“处理完毕”（实测 `elapsed_seconds=0.6, skipped=39, done=0`）。最后这个“处理完毕”被当成正常收尾写进 `ai_result.json`（`ModEntry.Ai.cs:539-544`、`568-569`），规划器据此认定「上一轮计划已跑完」（`ai_planner.py:572-574`）并立刻再规划 —— 每 25~40 秒烧一次 API，农场一动不动，而**唯一该救场的看门狗被自己的判据短路**：`IdleIsLegitimate()` 看到队列里还挂着 39 个任务就返回 `true`（`Diagnostics.cs:192`），于是永远不判定“卡死”。**系统在每一个环节都“觉得自己正常”，这正是它能静默空转 40 分钟的根本原因。**

### 5.2 架构级缺陷（5 个，非 bug 级）

#### D1 缺“结果语义”——“被丢弃”与“已完成”在协议里无法区分，形成正反馈空转
- **证据/后果**：`AiNoteSkipped` 与 `AiNoteResult` **都**递增 `_aiPlanFinished`（`ModEntry.Ai.cs:540` vs `:565`），达 `_aiPlanQueued` 即 `AiFinishPlan()`（`:543-544`、`:568-569`），而它**无条件刷新 `finished_at`**（`:491`）；规划器的 `state_fingerprint` 把这个时间戳当“上一轮跑完”的信号（`ai_planner.py:544`、`:572-574`）。于是：全量丢弃 → 触发立即重规划 → 再全量丢弃。实测 `planner.log:1685/1720/1757` 连续三次「触发规划：上一轮计划已跑完」，而农场状态指纹逐轮完全一致（`break_stone 241 / clear_weed 443`）。
- **本质与修法**：协议缺少**结果分类**（`no-op`/`blocked`/`failed`/`done`）与**进展语义**，`skipped` 被压成一个不区分“世界变了”与“我根本到不了”的桶。`ai_result.json` 必须显式区分 `blocked_by:<capability>`，且**只有 `done>0` 或世界状态指纹变化才算“跑完”**；否则应退避/上报而非重规划。

#### D2 缺“可达性 / 位置”层——移动没有抽象，只有补丁
- **证据/后果**：移动逻辑散落在 `BeginCrossLocation`（`ModEntry.cs:1105-1172`）、`TryWalkToLocation`（`:1191-1284`）、`FindWarpTiles`（`:1302-1345`）、`CollectExitCandidates`（`:1356-1488`）、`FindSafeLanding`（`:1550-1572`）、`ShiftOffWarpTile`（`:1578-1600`）、`ResolveNavTarget`（`:904`）、`IsStandable`（`:947`）八处，**没有任何一处能回答“当前位置 P 能否到达地点 L”这个单一问题**，也没有状态缓存。后果：39 个动作各自重试 39 次同样的失败；`_crossLocBackoffUntil` 是全局标量（`:89`），把“某一条路线不通”泛化成“所有跨地点停摆”；12 秒等待超时是**调参**（注释 `:445-446` 承认从 6 秒放宽）而非**判定**。
- **本质与修法**：缺地点图 + 可达性查询 + 移动作为**一等任务**（可重试、可诊断、成功后会被记住）。把“移动”建模为独立 capability，带自己的状态机与失败分类；地点间用显式入口/出口图，查询结果可缓存并带失效条件。

#### D3 缺“地点拓扑”抽象——出入口靠猜、靠反射、靠硬编码
- **证据/后果**：`WatchdogFindFarmLanding()` 的三层兜底里，**分支 1 与分支 2 是逐字重复的同一段代码**（`Watchdog.cs:345-352` vs `:359-366`，只有 `farm0/v0` 与 `farm/v` 变量名不同），最终硬编码 `return new Point(64, 15)`（`:371`）。实测 `farm_tiles.json.save.farm_entry_xy` **正好是 `[64,15]`** ⇒ 前两层全部返回无效值。后果：模型 prompt 里的“出口坐标 `[64,15]`”是**硬编码常量**而非真实拓扑（`planner.log:1657` 模型据此推理“出屋即落在 [64,15]”）；`FindSafeLanding` 依赖 `target.warps` 反查、实测同样取不到 ⇒ 瞬移兜底失效。
- **本质与修法**：没有“地点 ↔ 地点”的权威拓扑模型，只能用 `isCollidingWithWarpOrDoor` 全图逐格扫描（`:1323-1337`，农舍 12×12 / 农场 80×60）+ 5 个来源并集来逼近。应建立**地点拓扑表**（地点、入口格、出口格、触发方式），用游戏权威 API 一次性解析并缓存，**禁止硬编码坐标，取不到时必须显式报错**而非静默兜底。

#### D4 双头决策——两套大脑并存，一半代码在默认配置下是死的
- **证据**：`PlanWork()`（`ModEntry.cs:1637`）是规则大脑；`AiLoadPlan()`（`ModEntry.Ai.cs:367`）是模型大脑。`CodePlannerEnabled=false`（`configs/AutoFarmWorker.json`；默认 `ModEntry.cs:1656`）让规则大脑在 `:1656-1661` 直接 `return`。
- **后果**：只被规则大脑调用的代码全部失效，但**没有任何机制指出它们已死**：
  - 目标格黑名单 `_blockedTiles` 的唯一消费点在 `ModEntry.cs:1745`（`PlanWork` 内）⇒ AI 路径下**黑名单完全无效**（`IsBlocked` 在 `:806` 定义后无人调用）。
  - `AiFilterCandidates`（`ModEntry.Ai.cs:279-328`，focus/avoid 过滤）同样只在 `PlanWork` 里被调用（`:1749`）⇒ **`focus`/`avoid` 两个指令字段在 AI 计划模式下也是死的**。
  - `_planHadWork` 在两条路径下语义相反：`PlanWork` 里 `= this._pending.Count > 0`（`:1761`），AI 计划运行中写 `true`（`:1643`），无计划时写 `false`（`:1658`）。
- **本质**：没有删除旧路径，也没有把“能力开关”与“代码存在性”对齐。**“配置关闭”不等于“代码移除”**，于是读者（和后续维护者）无法分辨哪些逻辑仍然活着 —— 这在架构重写时是最危险的陷阱。
- **修法方向**：新项目**只保留一个决策源**；任何被禁用的能力必须物理删除，而不是留在配置后面。

#### D5 缺“唯一契约来源”——schema 声明但未校验、白名单两份、知识库断链
- **证据**（四处独立漂移）：
  1. `AiDirective.ExpectedSchema = "stardew-ai-directive/1"`（`AiDirective.cs:42`），而 Python 写的是 **`/2`**（`ai_planner.py:484`）；且 `ExpectedSchema` **只被用于生成示例文本**（`ModEntry.Ai.cs:678`、`:759`），**从未参与校验**。
  2. 动作白名单两份硬编码：`LegalActions`（`ActionExec.cs:42-47`）与 `LEGAL`（`ai_planner.py:428-430`），靠手工同步；`ToolFor()`（`TileMap.cs:319-341`）又是第三份动作↔工具映射。
  3. `expires_at` “安全阀”：Python 写空串（`ai_planner.py:487`）+ C# 解析失败即视为不过期（`AiDirective.cs:143-145`）⇒ **安全阀永久失效**，`ModEntry.Ai.cs:204` 是死代码。
  4. 知识库断链：规划器读 `knowledge/crops.md` / `tools.md`（`ai_planner.py:181`），实测目录下**只有 `strategy.md`** ⇒ 注入占位文本（`:191-197`）⇒ `crop_economics.json` 的经济学数据从未进入 prompt。
- **本质**：没有 machine-readable 的单一契约（schema 文件 + 代码生成/校验），因而字段名、版本号、白名单、知识路径四处各自漂移，且**全部静默失败**。
- **修法方向**：schema 用文件定义并在两端做**强制**校验（版本 + 必填 + 枚举）；白名单从一个源生成；契约漂移必须在启动时以 Error 级别失败（`SelfTest` 的思路是对的，要扩展到**所有**契约面）。

---

## §6 能力边界（农业之外）

### 6.1 总表

| Mod | 行数 | 执行模型 | 完成度 | 关键证据 |
|---|---|---|---|---|
| **AutoFarmMiner** 挖矿 | 979 | `UpdateTicked` 帧驱动 + `WorkTask` 列表 | ⚠️ **代码最完整，但部署链路断裂** | 见 6.2 |
| **AutoFarmFishing** 钓鱼 | 320 | `UpdateTicked` + 接管 `Game1.activeClickableMenu` | ⚠️ **半成品，靠"改判定"通关** | 见 6.3 |
| **AutoFarmTrader** 交易 | 545 | 定时（`_tradesToday` 计数） | ❌ **不是交易，是"删物品加钱"** | 见 6.4 |
| **AutoFarmRancher** 牧场/加工 | 515 | `UpdateTicked` + `FindLocation("Farm")` 遍历建筑 | ✅ **能跑，是 4 个里最扎实的** | 见 6.5 |
| **AutoFarmPlanner** 温室支持 | 466+538 | `TimeChanged` 写快照；`afp` 命令 | ⚠️ **只读不干** | 见 6.6 |

### 6.2 AutoFarmMiner（挖矿）—— 代码完整度最高，但**从未被 build.ps1 构建部署**

**能跑的部分（代码证据充分）**：
- 真实进入矿洞：`Game1.warpFarmer("Mine", 18, 12, false)`（`AutoFarmMiner/ModEntry.cs:453`）；撤离 `warpFarmer(Config.RetreatLocation, ...)`（`:498`）。
- 矿洞状态读取：`MineShaft.mineLevel`、`ladderHasSpawned`（反射字段，`:864-873`）、`stonesLeftOnThisLevel`、`EnemyCount`（`:33-34`、`:875-880`）。
- 任务生成齐全：`FindOres`（`:757`）、`FindStones`（`:784`）、`FindDebris`（`:812`）、`FindLadder`（`:901`，含反射调 `MineShaft.findLadder`，`:618`）、`FindMonsters`（`:688`）、`DescendDirectly`（`:912`）。
- 战斗：`EnumerateMonsters`（`:661-673`）→ `AttackMonster` → `Monster.takeDamage(int,int,int,bool,double,Farmer)`（`:36`、`:704-717`），并正确计数 `MonstersKilled`。
- 安全撤退：`RetreatReason(MineShaft)`（`:271-288`）+ `SafeEnemyCount`（`:1140`），阈值与 `COMMANDS.md:396-403` 的表格一致（血量 <40%、体力 <20%、21:00、被 4 只以上围、只打 `FightRadius` 内）。

**问题**：
1. **`build.ps1` 的 `$Mods` 数组不含 `AutoFarmMiner`**（`build.ps1:16-22`，共 5 项），但游戏 `Mods\` 下**确实有 `AutoFarmMiner` 目录**。⇒ 这个 Mod **无法通过标准流程重新构建/部署**，当前 DLL 很可能是手工拷贝的历史版本。**这是运维链路的真实断点。**
2. `afm` 的“农场优先”判据（`COMMANDS.md:421-427`：农场有活就不下矿）与 Worker 的 `ScanWorldFacts` 逻辑重复但**不共享代码** —— 又是一个双份实现。
3. **未确认**：它是否有自己的寻路/卡死自救（979 行中未逐段核实），以及是否真的端到端跑过。

### 6.3 AutoFarmFishing（钓鱼）—— 半成品，“完成小游戏”是靠**直接改判定**

- 流程齐全：装备鱼竿 → `rod.DoFunction(...)` 抛竿（`AutoFarmFishing/ModEntry.cs:161`）→ 咬钩后再 `DoFunction` 收杆（`:179`）→ 检测 `Game1.activeClickableMenu is BobberBar`（`:88`）。
- **小游戏是作弊而非操作**：`instant` 模式直接 `bar.distanceFromCatching = 1f; bar.bobberInBar = true;`（`:262-263`）—— 直接置为必成功，**不依赖任何操作**。`assist` 模式（`:267-287`）才真的每帧推 `bobberBarPos`，但注释自承“更真实但可能失手”，且 `:287` 的 `568f` 是**魔法数字**（“BobberBar 内部高度近似”）。
- **评价**：manifest 声称“自动完成钓鱼小游戏”（`manifest.json`），实际默认路径是**绕过小游戏**。作为“能持续钓鱼赚钱”它是有效的；作为“模拟玩家钓鱼”它是未完成的。API 知识（`BobberBar` 字段表）来自 `probe11_out.txt`，**可信**。

### 6.4 AutoFarmTrader（交易）—— **不存在真正的交易**

- 声称“自动卖货 + 智能补货买种子”（`manifest.json`）。
- **卖**：遍历背包 → `item.sellToStorePrice()` 取价（`AutoFarmTrader/ModEntry.cs:253`）→ **直接 `cur.Stack -= take` + `removeItemFromInventory`（`:171-173`）→ `Game1.player.Money += gain`（`:175`）**。
- **买**：`ItemRegistry.Create("(O)"+id)`（`:517`）→ `addItemToInventory`（`:377`）→ `Money -= cost`（`:387`）。
- **结论**：**不经过任何 NPC、商店 UI、运输箱（shipping bin）或营业时间**。物品凭空消失、金钱凭空增加。这是**经济作弊**，不是自动化交易。`ARCHITECTURE.md:228-252` 把这称为“无 UI 交易的**核心决策**”，并列为优点 —— 这是**设计意图**，不是 bug；但如果新项目的目标是“模拟玩家农场经营”，这部分**必须整体重写**为走 shipping bin / ShopMenu。
- 可复用部分：`SeedUtil` 的种子判定与精确扣减（`:17` 引用跨 Mod 统一口径）、`aft dump` 诊断、`ItemRegistry.Create` 的 1.6 用法。

### 6.5 AutoFarmRancher（牧场 + 加工）—— **4 个里最扎实，基本能跑**

- 喂食：遍历 `farm.buildings` → `b.GetIndoors()` → `AnimalHouse` → 检查 `piecesOfHay.Value > 0` 与 `animalCount > 0` 后调 **`house.feedAllAnimals()`**（`AutoFarmRancher/ModEntry.cs:238-288`）。用官方接口，正确。
- 抚摸：`animal.pet(Game1.player, false)`（`:186`），先查 `wasPet`。
- 收产物：读 `animal.currentProduce?.Value`（`:208`）→ 建物品入包 → **`animal.currentProduce.Value = null`**（`:223`）。
- 机器：`readyForHarvest?.Value == true` 判定可收（`:363`），收后 `readyForHarvest.Value = false`（`:376`）；投料用 `performObjectDropInAction(one, false, Game1.player, false)`（`:421`，第四个参数 `returnFalseIfItemConsumed`）。
- **明确短板**：
  1. **不跨地点**：`FeedAllHouses` 走 `farm.buildings`（能覆盖农场上的畜棚/鸡舍），但抚摸/收产物/机器处理都是**“当前地点”**（`:293-295` 的 `GetAnimalHouse(loc)` 就是 `loc as AnimalHouse`）。⇒ 玩家不在畜棚里时只能靠 `afr pet` / `afr collect` 人工触发，**没有自动导航到畜棚的能力**。
  2. **温室未覆盖**：全项目 `Greenhouse` 相关代码只出现在 `AutoFarmPlanner`（只读判断）与一个文档注释里（`AutoFarmWorker/ModEntry.cs:2675` 提到“温室门口”）。`Rancher` **没有任何温室专门逻辑**。
  3. **未确认**：`DigUpProduce` 是否被实际调用（注释 `:19` 提到，grep 未见调用点）。

### 6.6 温室（Greenhouse）—— **只有"知道"，没有"去干"**

- `AutoFarmPlanner` 做得对：用 `farm.greenhouseUnlocked?.Value == true` 判断解锁（`AutoFarmPlanner/ModEntry.cs:203-205`），并**只在解锁后才把 `Greenhouse` 纳入扫描地点**（`:207-211`）。注释明确记录了 1.6 的坑：**“不能用『地点是否存在』判断 —— 温室地点始终存在，只是内容被禁用”**（`:204`）。
- 温室被当作**最高优先级策略目标**：`"【温室未解锁 —— 全游戏最高优先级】"`（`:407`）、`"解锁后全年种植杨桃，单日利润 26.92g/株"`（`:533`）。
- 快照里也暴露 `greenhouse_unlocked`（`SurroundingsSnapshot.cs:363`）并在未解锁时写进 `signals.notes`（`:479-480`）。
- **但**：`AutoFarmWorker` 的注释说“只扫主农场(户外)，不含温室 —— 温室由 Worker 单独处理”（`AutoFarmPlanner/ModEntry.cs:481`），而 **Worker 侧没有任何温室操作代码**；`ModEntry.cs:29` 仍写着“温室需要显式开启”却找不到对应开关。
- **结论**：温室是**规划上的一等公民、执行上的空白**。`check_greenhouse.py`（54 行）只做存档 XML 校验，证明作者知道这里有不确定性。

### 6.7 跨 Mod 的横向结论

| 观察 | 证据 |
|---|---|
| **6 个 Mod 之间几乎没有共享抽象**，唯一的成功共享是 `SeedUtil` | `src/Shared/SeedUtil.cs`；`AutoFarmWorker/ModEntry.cs:153-154`、`AutoFarmTrader/ModEntry.cs:17`。`FarmAuto.Shared` 命名空间只被 2 处引用 |
| **6 个 Mod 各自实现了“找地点/找建筑/枚举对象”**：`TryGetLocation`(Worker) / `FindLocation`(Rancher) / `GetAnimalHouse` / `WatchdogInMine` / `EnumerateMonsters` | `AutoFarmWorker/ModEntry.cs`、`AutoFarmRancher/ModEntry.cs:244,293-295`、`AutoFarmMiner/ModEntry.cs:661-673`。**同一件事 4 份实现** |
| **“农场优先/让路”逻辑在多处重复** | `WatchdogInMine`（`Watchdog.cs:320-331`）、`COMMANDS.md:421-427` 的 Miner 判据、`_aiPassive` 让路（`Ai.cs:221-222`）、`AutoFarmPlanner` 的 `HasActionable` 概念 |
| **只有 3 个 Mod 有自动化运行时**，另 3 个是“只读建议/工具” | 可写世界的：Worker / Trader / Rancher / Miner / Fishing；只读的：Planner（+ `state_report.py` 等 Python） |
| **配置模板与实际部署不同步**：`configs/AutoFarmWorker.json` 里 `FallbackDirectMode=false`，而 `ModConfig.cs:237` 的代码默认是 `AllowTeleportFallback=true` —— 二者一致；但 `ModConfig.cs` 的代码默认值与 `configs/*.json` 是否逐项一致**未逐项核对** | 抽查一致，全面核对**未确认** |

---

## §7 给架构重写的优先级建议（一句话版）

1. **先造“能力（capability）”抽象**：`Move` / `Till` / `Plant` / `Water` / `Harvest` … 每个能力自带 `precondition` / `effect` / `cost` / **失败分类**。D2、D4 一并解决。
2. **再定唯一契约**：一份 machine-readable schema 同时生成 C# 模型与 Python 校验；启动时强制校验版本 + 枚举 + 必填，失败即 Error。D5 解决。
3. **进度与结果必须有区分度**：`done > 0` 或世界指纹变化才算“跑完”；`blocked` 必须指名缺哪个能力。D1 解决。
4. **地点拓扑显式化**：地点图 + 入口/出口表 + 可达性查询，禁止硬编码坐标，取不到就报错。D3 解决。
5. **可复用资产优先搬运**：`SurroundingsSnapshot`（逐字段容错）、`PreCheck/Execute/PostCheck` 契约、`SelfTest`、`Tool.DoFunction`+×64、`Crop.harvest` 反射、`build.ps1`（补上 Miner）、`analyze_log.py`、`Probe26` IL 工具、`Probe8/9/10/11/13` 的 API 结论、`crop_economics.json` 结构。

---

*报告结束。全文所有 `文件:行号` 引用均来自本次实际读码；所有运行期数字均来自实际读取的 `Mods\AutoFarmWorker\data\*.json` 与 `planner.log`。标注「未确认」的四项为：① `Farm.warps` 中回程条目的确切内容；② 各 ModConfig 代码默认值与 `configs/*.json` 的逐项一致性；③ Miner 的端到端可运行性；④ `parse_save.py` 的覆盖范围。*



