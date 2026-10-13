# 床交互与门格取证（task-31）

只读取证。本文回答两件事：**A. 睡觉提问到底怎么才会弹出来**（含"给哪个格/哪个入口"），**B. Farm → FarmHouse 的门格 (64,14) 为什么会被当成 A\* 目标**（含最小修法方向）。
写盘范围：本文 + `scratch/`；未改任何源码（`git status --porcelain -- mod/ brain/ tests/` 在本轮取证前就为空）。
程序集：`Stardew Valley, Version=1.6.15.24356`；游戏目录 `D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley`。

## 0. 一句话结论

* **A**：睡觉提问**只能**由"玩家**踩到床的 TouchAction 格**"引出 —— `BedFurniture.DoesTileHaveProperty` 只对**一格**返回 `TouchAction=Sleep`，即 `(床tileLocation.X + bedTileOffset, 床tileLocation.Y + 1)`。本存档床在 `(9,8)`、`bedTileOffset` 由玩家 Pixel X 与床 bbox 中心 `640` 决定 ⇒ 触发格是 **(10,9)**（从右侧靠近时才是 (9,9)）。脑侧现在踩的 `(9,8)` 是**床的碰撞格**（A\* 必然 `unreachable`），而 `interact(床)` 走的 `checkAction → Furniture.checkForAction` 在 1.6.15 **根本没有床/睡觉分支** —— 这两条路都注定弹不出提问。**真机已复现（2026-10-13，见 §2.7）**：先走离床格到 (8,9)、再踩 **(10,9)** 才会弹提问；且 `sleep` 应答 Yes 后 `answerDialogue()` **不关提问框**，必须再 `dismiss_modal()` 关框，日期才会在 ~3s 内落地 —— 这是真机上唯一卡住的一步。
* **B**：`MoveToLocationSkill.BuildCandidates` 把 **warp 的 source 触发格本身当作 A\* 走路目标**（`MoveToLocationSkill.cs:860`，`retry` 在 `:906`），而判"这格能不能站"用的 `StepMover.Standable` 看不懂地图墙/建筑（该文件 `:924-926` 自己写了这件事）。农舍门格 (64,14) 是墙上的门 ⇒ 前两个候选（`source`/`cross`）必然 `unreachable`，白烧单跳预算；真正可行的是排在后面的 `door_push`（`:927-936`，走到邻居再"朝门里推"）。

## 1. 交付口径与证据清单

| 文件（均在 `scratch/`，UTF-8） | 内容 |
| --- | --- |
| `obs-farmhouse-spring11.json` | lead 抓的权威现场：读档后人躺在床上时的 `observe("full")`（只读，脚本 `capture_farmhouse.py`） |
| `_probe_save_bed.py` / `_probe_save_raw.py` | 解析存档 XML：各地点 furniture/warps/doors/tiles；某地点某节原始 XML |
| `refl-bed.txt` | `BedFurniture` 反射清单（成员/可见性） |
| `refl-bedtype.txt` | `BedFurniture+BedType` 枚举（`Any/Child/Double/Single`） |
| `il-bed-1.txt` | `BedFurniture|*` 全方法 IL（16497 行；**`*` 模式不打印真实方法名**，靠参数表辨认） |
| `il-bed-2.txt` | 按名精确 dump：`GameLocation.checkAction` / `Farmer.checkAction` / `Furniture.checkForAction` / `BedFurniture.GetBedSpot` 等 |
| `il-bed-5.txt` | `GameLocation.performTouchAction` 全文（1633 行，含字符串分派表与 Sleep 分支） |
| `il-bed-6.txt` | `GameLocation.UpdateWhenCurrentLocation`（968 行，踩格驱动在这） |
| `il-bed-intersect.txt` | `BedFurniture/Furniture.IntersectsForCollision` + `GetBoundingBox` |
| `il-cqd.txt` | `FIND|createQuestionDialogue` = 74 个调用方法 |
| `ilscan-touch.txt` | `ILSCAN|…|TouchAction` 调用面 |
| `logs/longrun-rehearsal-0.7.22.jsonl` | 彩排现场（L50、L112 两条 sleep 失败，逐字见 §3.3） |
| `logs/probe-bed-{live,live2,sleep,close,recipe}-run1.log` | Lead 2026-10-13 真机五探针（UTF-16LE）；UTF-8 副本 `scratch\t37_probe-bed-*.txt`（转换脚本 `scratch\_t37_clean_logs.py`），逐字结论见 §2.7 |

复跑命令（Python 绝对路径，见 §6）。

## 2. A —— 睡觉提问怎么才能弹出来

### 2.1 唯一触发链（逐帧，四步）

```
Game1._update → GameLocation.updateWhenCurrentLocation(GameTime)      // 地点每帧
  └─ var tile = Game1.player.Tile                                     // IL_08DD-08E7
     if (lastTouchActionLocation == Vector2.Zero) {                   // IL_08EA-08F9
         string action = this.doesTileHaveProperty(tile.X, tile.Y,
                             "TouchAction", "Back", false);           // IL_090C
         lastTouchActionLocation = tile;                              // IL_0921
         if (action != null) this.performTouchAction(action, tile);   // IL_092A-092F
     } else if (lastTouchActionLocation != tile) {
         lastTouchActionLocation = Vector2.Zero;                      // IL_0936-094B（重新武装）
     }
        ↓  action == "Sleep"
GameLocation.performTouchAction(String[], Vector2)   // 字符串分派："Sleep" → IL_0FCB
  └─ if (Game1.newDay) skip                                          // IL_0FCB-0FD0
     if (!shouldTimePass(false)) skip                                 // IL_0FD2-0FD8
     if (!Game1.player.hasMoved) skip                                 // IL_0FDA-0FE4  ★人必须"刚动过"
     if (Game1.player.passedOut) skip                                 // IL_0FE6-0FF0
     createQuestionDialogue(
        LoadString("Strings\Locations:FarmHouse_Bed_GoToSleep"),      // IL_0FF8
        createYesNoResponses(), "Sleep", null);                       // IL_1008-100E
```

证据：`scratch\il-bed-6.txt:693-730`（驱动）、`scratch\il-bed-5.txt:156-159`（分派表 `"Sleep"` → IL_0FCB）、`scratch\il-bed-5.txt:1283-1303`（Sleep 分支四道门 + `createQuestionDialogue`）。

**这解释了 `docs\_analyze-sleep-fail.md` 的 U4**（"`checkAction`/`checkForAction` 里查不到 `Sleep` 字面量"）：`Sleep` 这个字面量在 **`GameLocation.performTouchAction`**（`il-bed-5.txt` 第 157 行）与 **`BedFurniture.DoesTileHaveProperty`**（`il-bed-1.txt` 第 1128 行）里，**都不在** `checkAction`/`checkForAction` 的调用路径上。提问不是"按出来的"，是"踩出来的"。

顺带一个**已被真机否掉**的判据：`createQuestionDialogue` 的第 3 个实参（dialog key）确实是 `"Sleep"`（IL_1008），但真机上提问开着时 Mod 报的 `lastQuestionKey` 是 **`None`**（§2.7 探针 #2/#3/#5）⇒ **验收判据改用 `ui.dialogueIsQuestion` + `ui.dialogueResponses`**，别等 `lastQuestionKey == "Sleep"`。

### 2.2 触发格的精确算法（`bedTileOffset`）

`BedFurniture.DoesTileHaveProperty(Int32 tile_x, Int32 tile_y, String property_name, String layer_name, String& property_value)`
证据：`scratch\il-bed-1.txt:1028-1133`。

```
if (tile_x < tileLocation.X || tile_x >= tileLocation.X + getTilesWide()) return false;  // IL_0058-007F
if (tile_y != tileLocation.Y + 1) return false;                                          // IL_0084-0097
if (layer_name != "Back") return false;                                                  // IL_0099-00A5
if (property_name == "Bed") { value = "T"; return true; }                                // IL_00A7-00BD
if (bedType == BedType.Double /*2*/) return false;                                       // IL_00BE-00C5
int x2 = (int)tileLocation.X + bedTileOffset;                                            // IL_00C7-00DA
if (ignoreContextualBedSpotOffset) x2 = (int)tileLocation.X + 1;                         // IL_00DB-00F0
if (tile_x != x2) return false;                                                          // IL_00F1-00F3
if (property_name == "TouchAction") { value = "Sleep"; return true; }                    // IL_00F5-010B
return false;
```

`bedTileOffset` 由 `BedFurniture.UpdateBedTile(Boolean check_bounds)` 维护（`scratch\il-bed-1.txt:747-781`）：

```
Rectangle bb = GetBoundingBox();
if (bedType == BedType.Child /*1*/) { bedTileOffset = 1; return; }            // IL_0007-0017
if (check_bounds && bb.Intersects(Game1.player.GetBoundingBox())) return;     // IL_0018-002C（保持现值）
bedTileOffset = (Game1.player.Position.X > bb.Center.X) ? 0 : 1;              // IL_002E-0056
```

⇒ 触发格 = `(床X + offset, 床Y + 1)`，其中 `offset` 是**上下文的**（取决于玩家从床的哪一侧靠近），不是常量。`BedType` 的数值由 IL 反推：`Child=1`、`Double=2`（本存档 `bedType=Single`，走常规分支）。

### 2.3 本存档的真值（lead 抓的 `obs-farmhouse-spring11.json`）

* 唯一的床：`{"tile":[9,8],"bbox":[576,512,128,192],"passable":false,"ground":true,"isBed":true,"blocking":true,"type":"BedFurniture","name":"Bed"}`。
* 存档侧独立核对（`_probe_save_bed.py`）：`<Furniture xsi:type="BedFurniture">` `tileLocation=(9,8)`、`furniture_type=15`、`bedType=Single`、`boundingBox=(576,512,128,192)`；FarmHouse 共 9 件家具，其余 8 件非床；**家具 tile 存在嵌套节点 `<tileLocation><X>/<Y>`**（不是 `tileX/tileY` 叶子，首版脚本按叶子取名会得到 `None`）。
* bbox 中心 X = `576 + 64 = 640`；玩家 tile `[9,9]` ⇒ `Position.X ≈ 576+n < 640` ⇒ `bedTileOffset = 1` ⇒ **触发格 = (10,9)**；从右侧（Pixel X > 640）靠近时才是 (9,9)。
* `location.doors = []`（空），存档里 FarmHouse/Farm **也没有 `<warps>` 节点** —— 门/出口 warp 来自地图资源与运行时，**不能从存档拿**（B 侧必须读 Mod/IL）。

### 2.4 碰撞箱证据：为什么 (9,8) 走不到，而 (9,9)/(10,9) 能站

`BedFurniture.IntersectsForCollision(Rectangle rect)`（`scratch\il-bed-intersect.txt:2-40`）：

```
Rectangle bb = GetBoundingBox();          // (576,512,128,192)
Rectangle r = bb; r.Height = 64;          // 只留 y=8 这一行
if (r.Intersects(rect)) return true;
r = bb; r.Y += 128; r.Height -= 128;      // 只留 y=10 这一行
return r.Intersects(rect);
```

⇒ 床的**碰撞只覆盖 y=8 与 y=10 两行，中间那一行 y=9 不挡人**。这正好解释了彩排的两条现象：

* `move_to(9,8)` → `unreachable`（(9,8) 是碰撞格，游戏 A\* 不会给人算进去）；
* 触发格 `(9,9)`/`(10,9)` 在 y=9 行，**是可站格** ⇒ 正常 `PathFindController` 走得到，不需要推挤。

（`Furniture.IntersectsForCollision` 是朴素 `GetBoundingBox().Intersects`，`intersect` 的重写是 `BedFurniture` 独有的；`GameLocation.isCollidingPosition` 走 `IntersectsForCollision`，见 `GameLocation.isCollidingPosition(…, Boolean pathfinding, …)` 的 IL_0733。）

### 2.5 为什么 `interact(床)` 永远弹不出提问

`interact` → `GameLocation.checkAction` → `Furniture.checkForAction`，这条链在 1.6.15 只有这些字面量：

* `GameLocation.checkAction(Location, Rectangle, Farmer)`（`scratch\il-bed-2.txt:3` 起）：`Strings\Locations:ChallengeShrine_NotYetHard`（IL_029D）→ `createQuestionDialogue(String, Response[], String)`（IL_02B2）、`ChallengeShrine_Activated`（IL_02D6）、`Strings\UI:PendingProposal_Canceling`（IL_03AA）——**没有床/睡觉**。
* `Farmer.checkAction(Farmer, GameLocation)`（`scratch\il-bed-2.txt:2303` 起）：`AskToDance_`/`AskToMarry_`/`GiftPlayerItem_` —— 面向 NPC。
* `Furniture.checkForAction(Farmer, Boolean)`（`scratch\il-bed-2.txt:2933` 起）：只有 `Strings\1_6_Strings:WizardCatalogueLetter`（IL_0349）、`JojaCatalogueDescriptionTerms`（IL_03BB）—— **没有床/睡觉**。
* `BedFurniture` 自己**没有声明** `checkForAction`（`scratch\refl-bed.txt`），它只重写了 `DoesTileHaveProperty`（上面 2.2）。

⇒ 与 `docs\_analyze-sleep-fail.md` 的结论一致：`interact(床)` 是**静默 no-op**，不是"差一点成功"。要弹提问只能靠 §2.1 的踩格链。

补一条 Mod 侧现状（**task-33 要改的地方**）：`mod\AgentFarm.Bridge\Contracts.cs:426-438` 把 `isBed` 单独列出并把床判为阻挡（`standable = !isBed && passable`），`move_to` 因此默认拒绝床格，必须显式 `allow_bed=true`（`Skills.cs:348/371`、`MoveToLocationSkill.cs:178/668-672`）。而脑侧 `brain\agentfarm\farmwork.py:1136-1142` 的 `bed_tile()` 取的是**床的 `isBed` 原点格 (9,8)**，`:1176-1196` 用它 `move_to(..., allow_bed=True)`、失败后兜底 `stand_next_to(bed)` + `interact(bed)` —— 两条路都落在错误的目标/入口上。

### 2.6 给 task-33 的可施工伪代码（不写代码，只定方案）

**目标格（权威、零猜测）**：不要自己算 offset，直接问游戏 —— 遍历床的 bbox 内每格调
`loc.doesTileHaveProperty(x, y, "TouchAction", "Back", ref v)`，返回 `"Sleep"` 的那格就是目标（这就是游戏自己的判据，`bedTileOffset`/`ignoreContextualBedSpotOffset` 全自动正确）：

```
Point? sleepTile = null;
foreach tile in bedTiles(fromBbox):        // x: bbox.X/64 .. +width, y: bbox.Y/64 .. +height
    string v = null;
    if (loc.doesTileHaveProperty(tile.X, tile.Y, "TouchAction", "Back", ref v) && v == "Sleep")
        { sleepTile = tile; break; }
if (sleepTile == null) return Fail("bed_no_sleep_tile", "这张床不暴露 Sleep 触发格（double/child 床或自定义床）");
```

**动作序列（脑侧，仍走现有桥 API；真机定案见 §2.7）**：先 `move_to(床外一格)` 满足 `hasMoved` → `move_to(sleepTile.X, sleepTile.Y, allow_bed=True)`（回执 `ui_modal` 算成功）→ 等观测 `ui.dialogueIsQuestion=true` → `sleep` 应答 → **再 `dismiss_modal()` 关框**（不关框日期永远不动）。若 `move_to` 报 `unreachable`，退一步：先站到触发格紧邻的可站格，再 `move_to` 触发格（游戏 A\* 应能到，见 §2.4）；**别再退回 `interact`**。

**桥侧最小补强（可选但推荐）**：在 `observe` 的家具条目里补一个 `sleepTile`（就是上面那格的坐标），或直接在 `location.tiles[]` 里把返回 `TouchAction` 的格子标出来 —— 让脑侧不必知道 `bedTileOffset` 这套上下文规则。另外 `ui` 里把提问的 dialog key 原样报出来（**注意**：真机上 `lastQuestionKey` 读不到，见 §2.7 ⇒ 验收判据用 `ui.dialogueIsQuestion`）。

### 2.7 真机验证（Lead，2026-10-13）★

Lead 在 0.7.22 + 本存档（`spring 11` 起）上把 §2.1/§2.2 的判据逐格跑通，并连跑两次跨日。原始日志是 UTF-16LE（`read` 工具会判成 binary），我用 `scratch\_t37_clean_logs.py` 去 ANSI + 转 UTF-8 成副本 `scratch\t37_probe-bed-*.txt` 后逐条读过：

| 日志 | 结论（逐字读过） |
| --- | --- |
| `logs\probe-bed-live-run1.log` | 探针 #1：对床的 6 个占位格 `[[9,8],[9,9],[9,10],[10,8],[10,9],[10,10]]` 逐个 `interact`（= 游戏 `checkAction`）**全部返回 False**、`dialogueIsQuestion=false`、`lastQuestionKey=None` ⇒ §2.5 的 U4 结论被真机判死：入口不是 `interact`。 |
| `logs\probe-bed-live2-run1.log` | 探针 #2：`(9,8)`/`(9,10)`/`(10,8)` A\* `unreachable`；`(9,9)` 站得上但**不弹提问**；踩 **`(10,9)`** 时 `move_to` 回 `ui_modal`（`"移动过程中被菜单/对话/过场打断，已停止寻路"`），随后 `dialogueIsQuestion=true`、`dialogueResponses=['Yes','No']`、`activeMenuText="Go to sleep for the night?"`、`lastQuestionKey=None`。 |
| `logs\probe-bed-sleep-run1.log` | 探针 #3：只发 `sleep`（答 Yes）⇒ 回执 `timeout`，诊断 `isInBed=True, Game1.newDay=True, pauseTime=600, activeMenu=DialogueBox, dialogueUp=True, canMove=False, newDaySync.readyForSave?=True, hasSaved?=False` ⇒ **`Game1.newDay` 已置位（`doSleep → Game1.NewDay(0f)` 确实执行）但 180s 日期不动**。 |
| `logs\probe-bed-close-run1.log` | 探针 #4：`dismiss_modal()`（游戏自己的关框路径：`answerDialogue("No")` + `closeDialogue()`，回执 `worldResumed=true`）⇒ **spring 11 → 12**、`SaveGameMenu`、存档 3502298 → **3515386** B、mtime 2026-10-11 22:24:19 → **2026-10-13 18:15:25**。 |
| `logs\probe-bed-recipe-run1.log` | 探针 #5：整条配方连跑第二次 ⇒ **spring 12 → 13**（`t+0.0s` 还是 12、`t+3.4s` 变 13）、存档 3515386 → **3547073** B、mtime → **18:16:10**，`VERIFIED`。 |

**真机定案的五步配方**（task-33 照此施工）：

```
1. move_to(床外一格)               // 本机 (9,9) → (8,9)：满足 Farmer.hasMoved，并离开床格
2. move_to(触发格, allow_bed=True) // 本机 (10,9)：回执 ui_modal 是【成功】信号，不是失败
3. 观测 ui.dialogueIsQuestion      // 本机 true；dialogueResponses=['Yes','No']
4. sleep（answerDialogue Yes）     // 观测 Game1.newDay == true
5. dismiss_modal()                 // ★ 必须关框：answerDialogue() 不会关
   → 等 Game1.Date.TotalDays 前进 + 存档 size/mtime 前进（本机 0.2s ~ 3.4s）
```

第 5 步是 task-31 没写出来、真机上唯一卡住的地方：`sleep` 的 `answerDialogue(Yes)` 只把 `Game1.newDay` 置位、提问框仍挂着（`activeMenu=DialogueBox, dialogueUp=True, canMove=False`）⇒ `newDaySync` 等不到"框关了才存"，所以日期 180s 不动；**关框后 0.2s（`close` 探针首采样）/ `t+3.4s`（`recipe` 探针）日期就前进**。⇒ 别把"日期没动"当跨日失败去重发 `sleep`；`sleep` 失败后应当先 `dismiss_modal` 再看。

**观测口径修正（真机反例）**：提问开着时 `location.lastQuestionKey` 是 **`None`**，不是 `"Sleep"`（§2.1 末尾那条判据作废）⇒ 判据用 **`ui.dialogueIsQuestion` + `ui.dialogueResponses`**；Mod 兜底 path ②（`BuildSleepAnswerKey`）在真机不可用。

**本机环境事实**（task-33 写默认值时可参考）：床 bbox `[576,512,128,192]`、`passable=false`、占位格 6 格；触发格命中 **(10,9)** —— 从 (8,9) 靠近时 `Position.X < bbox.Center.X(=640)` ⇒ `bedTileOffset=1`，与 §2.2/§2.3 的推算完全一致；`(9,9)`（offset=0 的那格）同样站得上但**不是**这一刻的触发格。跨日落地后玩家被送到 `tile=[9,9]`、`tod=600`。

## 3. B —— Farm → FarmHouse 的门格为什么被当成 A\* 目标

### 3.1 图里门的语义（先分清三个格）

`mod\AgentFarm.Bridge\LocationGraph.cs`：

* `Edge.Source`（`:38-39`）= **触发区锚点**，来自地图 `Warp.X/Y`；`:48` 的注释已经写明"`Warp.X/Y` 只是**触发区**的锚点，**不等于"可以站人的格子"**"。
* `Edge.Landing`（`:42`）= 目标地点里的落点，`:41` 注释写明"只用于回执审计，本次不依赖它"。
* 门的两个来源：`loc.warps` 分支（`:114-208`）与**建筑**分支（`:214-253`，`door = b.getPointForHumanDoor()`、`AddEdge(..., isDoor: true)`；`Edge.IsDoor` 声明在 `:64`）；`:293` 的去重会把同一 `(from,to,source)` 的 `IsDoor` 或起来。
* 入图的触发方式**不是"站上 Source"**：`GameLocation.isCollidingWithWarp(玩家像素矩形, 玩家)` 比的是玩家**像素矩形四个角**所在格（`MoveToLocationSkill.cs:946-952` 的注释 + 那里对 `FarmHouse` 出门 warp 源格 `(3,12)` 落在 12x12 图层之外的说明）⇒ "走过去撞上"才算，站着不算。

### 3.2 混同点：`source` 被当成走路目标（行号）

`MoveToLocationSkill.BuildCandidates(GameLocation loc, LocationGraph.Edge primary, string from)`（`:838`）按"最可能触发的排前面"生成候选：

| 行 | 候选 | 说明 |
| --- | --- | --- |
| `:860` | `tag + "source"` | **把 `e.Source` 直接当 A\* 走路目标** ← 混同点 1 |
| `:874-880` | `tag + "cross"` | 沿玩家来向"穿过"源格（`e.Source + step`） |
| `:891-896` | 四邻按到玩家的曼哈顿距离排序 | 决定后面邻居类候选的先后 |
| `:902-903` | `StepMover.Standable(loc, n, …)` | 判"这格能不能站" |
| `:905-906` | `tag + "neighbor"` / `tag + "retry"` | 邻居 + **`e.Source` 再来一次** ← 混同点 2 |
| `:912-919` | `tag + "push"` | 从邻居那一侧穿过源格 |
| `:927-934` | `tag + "door_push"` | 站到可站邻居，然后 `PushInto = e.Source`（走到之后"朝门里推"） |

罪魁是 `:868-869` 的判据本身：

```csharp
bool sourceStandable = false;
try { sourceStandable = StepMover.Standable(loc, e.Source, true, out Furniture _); } catch { }
```

该文件 `:924-926` 的注释自己承认："`StepMover.Standable` 只懂家具/放置物/水面/地形，**看不懂地图的墙与建筑** —— 农舍的门格 (64,14) 会被它判成"可站""。于是 `sourceStandable = true`，`:927 if (e.IsDoor || !sourceStandable)` 这条兜底**仍然靠 `e.IsDoor` 进入**、`door_push` 候选确实生成了，但它的顺序排在 `source`/`cross`/`neighbor`/`retry`/`push` 之后（`:860`→`:906`→`:917`→`:934`），而单跳预算 `HopTimeoutMs = 8000`（`:83`）是硬的。

候选去重只跟**上一个**条目比（`AddCandidate` `:965-969`：`last.Tile == tile && last.Edge == edge`），所以相邻的 `neighbor`/`retry` 组合仍会重复出现 —— 预算最先烧在和墙"讲道理"的候选上。

### 3.3 彩排现场逐字（`logs/longrun-rehearsal-0.7.22.jsonl`）

第 1 天（L50，`t=145.05`，`code=failed`）：

```
timeout: [timeout] (HTTP 200) 第 1 跳失败（timeout）：走向 Farm → FarmHouse 的 warp 源格 (64,14) 超时
（单跳预算 8000ms 或整体剩余时间用尽）。本跳试过的格子：(64,14)(source)=unreachable[寻路无法到达 (64,14)
（A* 未算出路径，目标可能被围住）]；(65,14)(cross)=unreachable[寻
```

第 2 天（L112，`t=258.71`，`code=sleep_no_question`）：

```
睡觉提问没弹出来，拒绝盲发应答（盲发在 IL 上是静默 no-op）：当前地点 FarmHouse 的 lastQuestionKey=(空)；
诊断：isInBed=False, Game1.newDay=False, pauseTime=0, activeMenu=(无), dialogueUp=False, canMove=True,
gameMode=3, timeOfDay=1230, newDaySync.readyForSave?=True, newDaySync.hasSaved?=False。先让玩家**踩到床格**
…；脑侧现场：踩床格 (9, 8) 失败：unreachable: [unreachable] (HTTP 200) 寻路无法到达 (9,8)
（A* 未算出路径，目标可能被围住）；兜底 interact(床) 已发出
```

现场快照（跑后）：玩家 `playerTile=[8,8]`（已站在床旁）、`isInBed=false`、`activeMenu=(无)`。

两条日志各印证一半：

* 第 1 天 = 门格被当目标 ⇒ 前两个候选 `(64,14)(source)`、`(65,14)(cross)` 都是 A\* 无解。`(65,14)` 也 unreachable 是因为它在建筑 footprint/墙里（建筑占位格），而 `StepMover.Standable` 看不出来。
* 第 2 天 = 踩 `(9,8)`（床的**碰撞格**，见 §2.4）+ `interact`（§2.5 的静默 no-op）⇒ 提问恒不出现，`lastQuestionKey` 空。

状态码说明（`FailHopExhausted`，`:1010-1064`）：优先级 `hop_failed(真站到过)` > `blocked` > **`timeout`** > `hop_failed(走近过)` > `unreachable`。第 1 天报 `timeout` ⇒ 后面还有别的候选被判了 timeout（walk 到某个候选把 8000ms 用完了），前两条 `unreachable` 只是被这条优先级盖住。

## 4. 未定项 / 还缺什么证据（2026-10-13 更新，含真机结案）

1. **仍开放（证据缺口）**：彩排第 1 天的 receipt 在 `logs/` 里被截断到约 160 字符（`scratch\_peek_sleep_fail.py` 直读 JSONL 同样被截）⇒ 看不到第 3 个候选之后的尝试列表。run3 前建议让"本跳试过的格子"不要截断，或 Mod 侧改成结构化 `attempts[]`，否则分不清"没走到 door_push"和"door_push 也没触发"。
2. **仍开放**：`door_push` 在 Farm→FarmHouse 这条边上**是否被真正执行过**（有没有进入 Push 阶段），彩排里没有直接证据（见第 1 条）。
3. **真机结案（值）/ 仍需暴露（接口）**：`bedTileOffset` 现场值已定 —— 先走到 (8,9) ⇒ `offset=1` ⇒ 触发格 **(10,9)**，`probe-bed-live2` 命中。但**桥不让脑侧读 offset**，脑侧仍只能押两格 ⇒ **task-33 要在 `observe` 的床条目里暴露 `bedCells`**（`doesTileHaveProperty(..., "TouchAction", "Back") == "Sleep"` 的所有格），或按 §2.6 现算。
4. **结案**：`hasMoved` 门槛由"先走离床格一步"满足 —— 真机 (8,9) → (10,9) 两次都弹出提问，无需伪造输入（`probe-bed-live2` / `probe-bed-recipe`）。
5. **结案（反例）**：`lastQuestionKey` 判据作废 —— 真机提问开着时它是 `None`；判据改用 `ui.dialogueIsQuestion`(+`ui.dialogueResponses`)，Mod 兜底 path ②（`BuildSleepAnswerKey`）真机不可用。文案问题一并结案：本机弹的是英文 `"Go to sleep for the night?"`（游戏语言 = 英文），与逻辑无关。

## 5. 给 task-33 的一句话口径

**睡觉**（真机定案，照 §2.7 的五步走）：目标格永远是 `doesTileHaveProperty(x, y, "TouchAction", "Back") == "Sleep"` 的那一格（本存档 = 床 (9,8) 的 `y+1` 行、x 由 `bedTileOffset` 决定 ⇒ 从左侧靠近是 **(10,9)**、从右侧是 (9,9)，**绝不是 (9,8)**）；顺序必须是「先走离床格一步（满足 `hasMoved`）→ `move_to(触发格, allow_bed=True)`（回执 `ui_modal` 算成功）→ 等 `ui.dialogueIsQuestion` → `sleep` 答 Yes → **`dismiss_modal()` 关框** → 等日期 + 存档前进」；不要再退回 `interact`，也不要在关框前因为"日期没动"重发 `sleep`。
**门**：`Edge.Source` 是**触发锚点**不是走路目标（`MoveToLocationSkill.cs:860/:906` 的混同），墙上的门格 A\* 必然无解；要么把 `door_push` 提到同边候选最前面，要么在第一个候选 `unreachable` 后直接跳到 `door_push`，别把 8000ms 单跳预算花在"站到墙上"。

## 6. 复跑命令

```powershell
$env:PYTHONUTF8="1"
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py scratch\run_il_probe.py scratch\il-bed-5.txt "StardewValley.GameLocation|performTouchAction"
& $py scratch\run_il_probe.py scratch\il-bed-6.txt "StardewValley.GameLocation|UpdateWhenCurrentLocation"
& $py scratch\run_il_probe.py scratch\il-bed-1.txt "StardewValley.Objects.BedFurniture|*"
& $py scratch\run_il_probe.py scratch\il-bed-intersect.txt "StardewValley.Objects.BedFurniture|IntersectsForCollision" "StardewValley.Objects.Furniture|GetBoundingBox"
& $py scratch\_probe_save_bed.py          # 存档侧家具/warps/doors
& $py scratch\_peek_sleep_fail.py         # 彩排两条 sleep 失败
& $py scratch\_t37_clean_logs.py          # logs\probe-bed-*-run1.log（UTF-16LE）转 UTF-8 副本到 scratch\
```

反射/枚举/ILSCAN 用 `scratch\profession-probe\bin\Release\net6.0\ProfessionProbe.exe "<游戏目录>" <out> "<TypeSpec>"`（TypeSpec：`Type|kw`、`?substr`、`INVOKE|Type|Method|args`、`ILDEC|Type|Method`、`ILSCAN|Type|Member`）。
坑：`tools\il-probe` 的 `FIND|` 只解析**方法** token（查字段名必 0 命中）；`FINDSTR` 搜的是 IL 内联串而 `ldstr` 走 #US 堆（搜英文字面量必 0 命中）；`*` 模式不打印真实方法名；`ILSCAN|Type|Member` 对**重载方法名**会 `AmbiguousMatchException`。
