# 旧项目游戏 API 知识页（Stardew Valley 1.6.15 / SMAPI 4.5.2 / .NET 6）

> **来源**：`C:\Users\admin\WorkBuddy\2026-10-04-20-36-38\stardew-auto-farm`（只读引用，未修改）。
> **可信度口径**：本页严格分层，**没有任何实测输出背书的结论一律标 `[未验证]`**。
>
> | 标注 | 含义 | 判定标准 |
> |---|---|---|
> | `[实测 Probe8]` `[实测 Probe9]` `[实测 Probe10]` `[实测 Probe11]` `[实测 Probe13]` | 探针已落盘输出，**可信** | `tools/probes/ProbeN/probeN_out.txt` 实际存在且含该结论 |
> | `[旧代码]` | 旧项目源码中实际写成的调用/注释，**行为已编译验证，但游戏语义未必正确** | 可指到具体 `文件:行号` |
> | `[未验证]` | 仅有探针源码、无输出；或来自文档/推测 | 必须在真机重新验证后才能升格 |
>
> ⚠️ 引用约定：`文件:行号` 相对旧仓库根目录。**`docs/ARCHITECTURE.md` 等旧文档只作线索**，凡与源码/探针冲突处一律以源码/探针为准（审计 §4.0 已确认多处文档与实现不符）。

---

## 0. 可信度总览

- **有实测输出的探针只有 5 个**：Probe8（13.1 KB）、Probe9（26.2 KB）、Probe10（7.4 KB）、Probe11（6.9 KB）、Probe13（8.3 KB）。
- 其余 21 个探针**只有源码、没有输出**：`Probe`、`Probe2`~`Probe7`、`Probe12`、`Probe14`~`Probe26`。它们的 API 假设在本页**一律标 `[未验证]`**（清单见 `INDEX.md`）。
- `Probe26` 的方法名清单（`PathFindController.handleWarps` 等）是**代码里写死的字符串**，属"作者认为存在"，不是"已验证存在"（`Probe26.cs:25-30`）。

---

## 1. 工具与继承链

### 1.1 `StardewValley.Tool : Item`，各工具 : `Tool`

- **结论**：`StardewValley.Tool` 继承 `Item`；`Tools.Hoe` / `Tools.Axe` / `Tools.Pickaxe` / `Tools.WateringCan` 均继承 `Tool`。`FishingRod: Tool`。
- **证据出处**：`[实测 Probe8]` `Probe8/probe8_out.txt:5-9`（`StardewValley.Tool -> StardewValley.Tool : Item`、`Tools.Hoe : Tool`、`Tools.Axe : Tool`、`Tools.Pickaxe : Tool`、`Tools.WateringCan : Tool`）；`Probe8/probe8_out.txt:45`（`FishingRod: Tool`）。
- **对影响与建议**：所有工具可以统一以 `Tool` 静态类型处理（取工具、判等级、调 `DoFunction` 都只需一套代码）。新项目应建立 `ToolKind` 枚举 + 单一 `GetTool(kind)`，避免旧项目那种每个动作各写一次 `GetAxe()/GetPickaxe()/GetWateringCan()`。

### 1.2 `Tool.DoFunction(GameLocation, Int32 x, Int32 y, Int32 power, Farmer who)` 是所有工具的统一入口

- **结论**：`DoFunction` 签名为 `Void DoFunction(GameLocation location, Int32 x, Int32 y, Int32 power, Farmer who)`；`Hoe`、`Tool`、`FishingRod`、`Axe` 上签名完全一致。**坐标 x/y 是像素，不是格子**（须 `tile × 64`）。
- **证据出处**：`[实测 Probe8]` `probe8_out.txt:11,13,51,271`（Hoe / Tool / FishingRod / Axe 四处的 `DoFunction` 签名逐字相同）；像素坐标系 `[旧代码]` `src/AutoFarmWorker/ModEntry.ActionExec.cs:514`（注释"x/y 是**像素**（tile × 64）"）与 `:528` 的实现 `tool.DoFunction(loc, p.X * 64, p.Y * 64, 1, Game1.player)`。
- **对我们的影响与建议**：**强推**。新项目所有"用工具作用于世界"的操作都走这一条路径，一次踩坑（×64）就够。不要手写状态变更（见 1.3）。

### 1.3 为什么必须走 `DoFunction` 而不是 `performToolAction` 或手改状态

- **结论**：`performToolAction` 假定工具已处于"使用中"状态，会读 `lastFarmerToUse` 而抛空引用；手改 `tree.health`/`stump` 会绕过掉落、树倒动画与木材结算。`DoFunction` 走的是"玩家挥工具"那条完整路径，游戏自己处理全部后果。
- **证据出处**：`[旧代码]` `ActionExec.cs:519-521`（"后者假定工具已处于'使用中'状态，会读 `lastFarmerToUse` 而抛空引用"）；`:510-513`（手改状态会绕过掉落与动画）。`performToolAction` 确实存在且为多态：`[实测 Probe8]` `probe8_out.txt:38-40`（`TerrainFeature`/`Object`/`Grass` 三个重载）。
- **对我们的影响与建议**：`DoFunction` 与 `performToolAction` **都存在**（Probe8 证实后者），但旧项目实测选了前者。新项目保留同一选择，并把理由写进代码。

### 1.4 `Axe.UpgradeLevel` 是**属性**（getter `get_UpgradeLevel()`），不是字段

- **结论**：`UpgradeLevel` 通过 getter/setter 暴露，且可写；底层字段名是 `upgradeLevel`。
- **证据出处**：`[实测 Probe8]` `probe8_out.txt:14-17`（`Int32 get_UpgradeLevel()` 与 `Int32 UpgradeLevel`）；`[实测 Probe9]` `probe9_out.txt:425`（`Tool field NetInt upgradeLevel`）、`:575`（`Tool prop Int32 UpgradeLevel (canWrite=True)`）、`:602-603`（`get_UpgradeLevel`/`set_UpgradeLevel`）；`[实测 Probe10]` `probe10_out.txt:165-168`（`UpgradeLevel prop 可写: True`）。
- **对我们的影响与建议**：读等级用 `GetProperty("UpgradeLevel")`，**但**旧项目实测里同时准备了 Property→Field 双重尝试（`ActionExec.cs:165-168`），因为"这个字段的可访问性跨版本变过"。新项目：优先 Property，失败**显式报错**，不要静默返回 0/-1。

### 1.5 工具升级/附魔的直接入口

- **结论**：`Tool.UpgradeFrom(Tool)`、`ClearEnchantments()`、`CanAddEnchantment(BaseEnchantment)`、`CopyEnchantments(Tool,Tool)`、`AddEnchantment(BaseEnchantment)`、`hasEnchantmentOfType()`、`RemoveEnchantment(BaseEnchantment)`、`GetEnchantmentOfType<T>()`、`GetEnchantmentLevel()`；`Farmer` 侧有 `toolBeingUpgraded`(NetRef&lt;Tool&gt;) 与 `daysLeftForToolUpgrade`(NetInt)。
- **证据出处**：`[实测 Probe9]` `probe9_out.txt:602-612`（升级/附魔方法组）、`:596-597`（`Farmer field NetRef\`1 toolBeingUpgraded (泛型参数: Tool)`、`field NetInt daysLeftForToolUpgrade`）；`[实测 Probe8]` `probe8_out.txt:160-162` 同字段；`[实测 Probe10]` `probe10_out.txt:150`。
- **对我们的影响与建议**：实现"自动送修工具"不必模拟 UI，直接写 `Farmer.toolBeingUpgraded` + `daysLeftForToolUpgrade`。**但**这属于"绕过游戏流程"，新项目若目标是模拟玩家，应走 `Utility.TryOpenShopMenu("Blacksmith")`+`ShopMenu`（见 §6）。

---

## 2. `Crop` 与耕地 API

### 2.1 ⚠️ `Crop.harvest` 在 1.6 带可选 `JunimoHarvester` 与 `Boolean` 参数 ⇒ 直接写 C# 调用编译失败 **CS1503**

- **结论**：真实签名为
  `Boolean harvest(Int32 xTile, Int32 yTile, HoeDirt soil, JunimoHarvester junimoHarvester, Boolean isForcedScytheHarvest)`。
  直接手写 `crop.harvest(x, y, dirt)` 会 CS1503。**正解**：反射取"参数最少且 `ps[0]==int && ps[1]==int`"的重载，只填前 3 个实参，其余用 `HasDefaultValue ? DefaultValue : 值类型默认值` 兜底。
- **证据出处**：`[实测 Probe10]` `probe10_out.txt:114`（完整签名逐字）；`[旧代码]` `ActionExec.cs:345-347`（"1.6 的签名带可选的 JunimoHarvester 参数，直接写 C# 调用会因类型不匹配编译失败（实测 CS1503）"）与 `:350-376` 的反射实现（`ps[0]==int && ps[1]==int` + `OrderBy(参数个数)` + `HasDefaultValue` 兜底）。
- **对我们的影响与建议**：**必须反射**，且必须保留 `OrderBy(...).FirstOrDefault()` 的"取最少参数重载"策略 —— 直接按签名写死参数个数会在下次游戏更新时静默失配。新项目应把这段封装成一个 `HarvestOnce(Crop, HoeDirt, Point, Farmer)` 能力，附 CS1503 注释。

### 2.2 `Crop` 的关键成员（可用于回检）

- **结论**：`GetHarvestMethod()`、`RegrowsAfterHarvest()`、`Kill()`、`IsInSeason(GameLocation)`、`getRandomWildCropForSeason(...)`；字段 `crop.dead`(NetBool)、`crop.forageCrop`(NetBool)、`crop.fullyGrown`。
- **证据出处**：`[实测 Probe10]` `probe10_out.txt:112-115`（`GetHarvestMethod`/`RegrowsAfterHarvest`/`harvest`/`Kill`）；`[实测 Probe13]` `probe13_out.txt:161-166`（`field Netcode.NetBool dead`、`field Netcode.NetBool forageCrop`、`IsInSeason`、`getRandomWildCropForSeason`、`Kill`）。
- **对我们的影响与建议**：`RegrowsAfterHarvest()` 是**判断作物是否多收的权威 API**，新项目做收益预测时应优先用它，而不是像旧数据那样靠人工 `regrow` 数值（见 `crops.json` 的自洽性问题）。
- **注意**：`fullyGrown` 未出现在任何探针输出中，旧代码大量使用（`ActionExec.cs:87,200,416`）。该字段的实际类型/可访问性 **`[未验证]`**。

### 2.3 ⚠️ `Crop` 继承 `Object`(System) ⇒ CS8121；作物挂在 `HoeDirt.crop`

- **结论**：`Crop` 的 C# 基类是 `System.Object`，不是游戏的 `StardewValley.Object`。因此 `x is Crop`/模式匹配写法会 CS8121；访问作物必须经由 `HoeDirt.crop`。
- **证据出处**：`[旧代码/文档线索]` 审计 §4.1 引自 `ARCHITECTURE.md:361`；探针侧无直接基类 dump。**升格条件**：跑一次 `typeof(Crop).BaseType` 探针。
- **对我们的影响与建议**：**当前标 `[未验证]`**（依据是文档而非探针）。新项目第一件事就是补一条 `BaseType` 探针；在拿到结果前，不要用模式匹配访问 `Crop`。

### 2.4 `HoeDirt.plant` 官方签名与浇水状态常量

- **结论**：`Boolean plant(String itemId, Farmer who, Boolean isFertilizer)`（`itemId` 是**字符串 ItemId**）。另有 `needsWatering()`、`isWatered()`、`canPlantThisSeedHere(String itemId, Boolean isFertilizer)`、`paddyWaterCheck(Boolean forceUpdate)`。状态字段 `state`(NetInt)，取值 `dry=0` / `watered=1` / `invisible=2`（可**直接写** `state.Value = HoeDirt.watered`）。
- **证据出处**：`[实测 Probe10]` `probe10_out.txt:62-69`（方法签名）、`:87-89`（`static Int32 dry = 0`、`watered = 1`、`invisible = 2`）、`:68`（`field NetInt state`）；`[旧代码]` `ActionExec.cs:396`（`d.plant(seed.ItemId, Game1.player, false)`）、`:328`（`d.state.Value = HoeDirt.watered`）。
- **对我们的影响与建议**：播种走官方 `plant`（**正解**，会正确处理肥料与地块状态）。浇水**直接写 `state`** 是旧项目的选择：不消耗水、不播放动画、不做水壶判定 —— 属于"改数据"。新项目若要求"模拟玩家"，应改用 `WateringCan.DoFunction`；若只求效率，直接写 `state` 并**显式记账**这是绕过。

### 2.5 `GameLocation.makeHoeDirt` 等耕地查询 API

- **结论**：`GameLocation.makeHoeDirt(Vector2 tileLocation, Boolean ignoreChecks)`、`GetHoeDirtAtTile(Vector2 tile)`、`isTileHoeDirt(Vector2 tile)`、`getTotalOpenHoeDirt()`。
- **证据出处**：`[实测 Probe8]` `probe8_out.txt:30-33`（四个签名逐字）。
- **对我们的影响与建议**：耕地创建/查询都走官方 API，**不要**自己 `terrainFeatures[xy] = new HoeDirt(...)`（会漏掉 `makeHoeDirt` 的内部检查与状态初始化）。注意 `GameLocation` 上**没有** `diggable`/`Diggable` 成员（`probe8_out.txt:34-35` 两次查询均为空）。

### 2.6 肥料/速生 ID 常量（可直接复用）

- **结论**：`fertilizerLowQualityID=368`、`fertilizerHighQualityID=369`、`waterRetentionSoilID=370`、`waterRetentionSoilQualityID=371`、`speedGroID=465`、`superSpeedGroID=466`、`hyperSpeedGroID=918`、`fertilizerDeluxeQualityID=919`、`waterRetentionSoilDeluxeID=920`；对应的限定 ID 形如 `(O)368`。`paddyGrowBonus=0.25`。
- **证据出处**：`[实测 Probe10]` `probe10_out.txt:90-107`。
- **对我们的影响与建议**：速生肥料对 `profit_per_day` 影响巨大（缩短 `grow_days`）。`crops.json` **不含肥料维度**，新项目若要精确排产，需把 `speedGro` 作为新字段补上。

---

## 3. 地形特性类型体系（`Bush` / `ResourceClump` 等）

### 3.1 `Bush : LargeTerrainFeature`（**不是** `TerrainFeature`）——解释了一个字符串比较

- **结论**：`Grass` / `Tree` / `FruitTree` / `HoeDirt` : `TerrainFeature`；**`Bush` : `LargeTerrainFeature`**。因此遍历 `loc.terrainFeatures` 得到的 `Bush` 无法用 `tf is TerrainFeature` 之外的常规方式归类，旧项目只能用 `tf.GetType().Name != "Bush"` 做字符串比较。
- **证据出处**：`[实测 Probe8]` `probe8_out.txt:20-26`（`Bush -> LargeTerrainFeature`，其余四项 `-> TerrainFeature`）；`[旧代码]` `ActionExec.cs:140`（`if (tf.GetType().Name != "Bush") return "不是灌木";`）。
- **对我们的影响与建议**：新项目的类型体系必须**显式建模两条继承链**：`TerrainFeature` 与 `LargeTerrainFeature`。字符串比较是"类型体系没建好"的症状，应替换为 `is Bush` 或统一的 `TerrainKind` 分类器。

### 3.2 `ResourceClump` 全名 = `StardewValley.TerrainFeatures.ResourceClump`，基类 `TerrainFeature`

- **结论**：曾猜成 `StardewValley.ResourceClump`（错误）。正确全名与基类如上。
- **证据出处**：`[实测 Probe10]` `probe10_out.txt:5`（`StardewValley.TerrainFeatures.ResourceClump  (base=TerrainFeature)`）；`[实测 Probe8]` `probe8_out.txt:24` 该行输出为 `StardewValley.ResourceClump -> ???`，**即当时用错名字查不到** —— 与 Probe10 的更正互相印证。
- **对我们的影响与建议**：命名空间是**已验证的高频踩坑点**。新项目所有类型引用都应用全名 + 一次 `BaseType` 校验，并把 `ResourceClump` 的命名空间写进代码注释。

### 3.3 地形特征/物件容器的真实类型

- **结论**：`GameLocation.terrainFeatures` : `NetVector2Dictionary<TerrainFeature, NetRef<TerrainFeature>>`；`objects` : `OverlaidDictionary`；`resourceClumps` : `NetCollection<ResourceClump>`；`largeTerrainFeatures` : `NetCollection<LargeTerrainFeature>`。
- **证据出处**：`[实测 Probe8]` `probe8_out.txt:276-279`（四个字段的实际泛型）；`[实测 Probe13]` `probe13_out.txt:180-182`（带完整程序集限定名）。
- **对我们的影响与建议**：新项目不要把这些容器抽象成普通 `Dictionary`。`resourceClumps` 与 `largeTerrainFeatures` 是**独立集合**，不在 `terrainFeatures` 里 —— 旧项目在 `terrainFeatures` 里找 `ResourceClump`（`ActionExec.cs:483`）属于**可疑用法**，新项目应在真机确认 `ResourceClump` 到底落在哪个集合。

---

## 4. 物品与背包 API 陷阱

### 4.1 🔴 `Farmer.removeItemFromInventory(Item)` **没有 count 参数**，移除的是**整个物品（一整叠）**

- **结论**：该 API 唯一重载即 `Void removeItemFromInventory(Item which)`。想"扣 1 个"必须自己改 `Stack` 或用 `Inventory.Reduce(...)`。旧项目因此把"种 1 株"变成消耗 16 个种子，**全程无异常**，烧掉 430g 才发现。
- **证据出处**：`[实测 Probe8]` `probe8_out.txt:321-322`（`Farmer ??? 'removeItem'` 下**只有** `Void removeItemFromInventory(Item which)`）；`[旧代码]` `src/AutoFarmWorker/ModEntry.Diagnostics.cs:214-219`（事故记录："种 5 株、蒸发 5 叠、烧掉 430g，日志里一条异常都没有"）与 `:224-247` 的 `VerifySeedConsumption` 补偿校验。
- **对我们的影响与建议**：**最高优先级禁令**。新项目：① 任何扣减都走 `Inventory.Reduce`/直接改 `Stack`；② **保留**"每次改变世界的动作后核对自己的副作用"这条通用约定（见 `legacy-design-patterns.md`）。

### 4.2 背包可写性与加物品 API 组

- **结论**：`Farmer.Items` **只读**（`canWrite=False`），是可变的 `Inventory`；`ActiveItem`/`ActiveObject`/`CurrentTool` 可写；`Money`/`Position`/`currentLocation` 可写；`Tile`/`TilePoint` 只读。`Inventory` 提供 `CountItemStacks()`、`CountId(String itemId)`、`Remove(Item)`、`RemoveAt(Int32)`、`RemoveButKeepEmptySlot(Item)`、`Add(Item)`、`AddRange(ICollection)`、`RemoveRange(Int32,Int32)`、`RemoveEmptySlots()`。`Farmer` 侧有 `addItemToInventory(Item)` 等 4 个重载 + `addItemToInventoryBool(Item,Boolean)`。
- **证据出处**：`[实测 Probe9]` `probe9_out.txt:13-22`（`Inventory Items (canWrite=False)`、`ActiveItem (canWrite=True)`、`Money (canWrite=True)`、`Tile (canWrite=False)` 等）；`[实测 Probe8]` `probe8_out.txt:300-310`（`Inventory` 方法组）、`:313-320`（`addItemToInventory` 重载组）、`:325-328`（`Money`/`_money`/`totalMoneyEarned`）。
- **对我们的影响与建议**：`Items` 只读 ⇒ 不能整个替换背包，只能增删元素。`CountId(String)` 是"数种子"的现成 API，**不要**手写遍历（旧项目手写了 `CountSeedsInBag`）。

### 4.3 🔴 1.6 造物品必须用 `ItemRegistry.Create(qualifiedItemId)`

- **结论**：`ItemRegistry.Create(String)` 是 1.6 唯一正解，限定 ID 形如 `"(O)"+id`。旧项目用它造产物/种子。
- **证据出处**：`[旧代码]` `src/AutoFarmWorker/ModEntry.cs:515-517`（"1.6 用 `ItemRegistry.Create(qualifiedItemId)`"）、`:215`（`ItemRegistry.Create("(O)" + produceId) as StardewValley.Object`）、`ModEntry.TileMap.cs:696`；`src/AutoFarmTrader/ModEntry.cs:517`（审计 §6.4 引）。
- **对我们的影响与建议**：`new Object(id, 1)` 的旧写法在 1.6 已不可靠。新项目所有物品创建走 `ItemRegistry.Create`，并对返回 `null` 显式报错（旧项目只记 Trace 级日志，`ModEntry.cs:521`）。

### 4.4 ⚠️ `Object` 类别常量全表

- **结论**：`GreensCategory=-81`、`GemCategory=-2`、`VegetableCategory=-75`、`FishCategory=-4`、`EggCategory=-5`、`MilkCategory=-6`、`CookingCategory=-7`、`CraftingCategory=-8`、`BigCraftableCategory=-9`、`FruitsCategory=-79`、`SeedsCategory=-74`、`mineralsCategory=-12`、`flowersCategory=-80`、`meatCategory=-14`、`fertilizerCategory=-19`、`junkCategory=-20`、`baitCategory=-21`、`tackleCategory=-22`、`sellAtFishShopCategory=-23`、`furnitureCategory=-24`、`ingredientsCategory=-25`、`artisanGoodsCategory=-26`、`syrupCategory=-27`、`monsterLootCategory=-28`、`equipmentCategory=-29`、`clothingCategorySortValue=-94`、`hatCategory=-95`、`ringCategory=-96`、`weaponCategory=-98`、`bootsCategory=-97`、`toolCategory=-99`、`clothingCategory=-100`、`trinketCategory=-101`、`booksCategory=-102`、`skillBooksCategory=-103`、`litterCategory=-999`。
- **证据出处**：`[实测 Probe10]` `probe10_out.txt:10-45`（全表逐字）。
- **对我们的影响与建议**：**直接搬进新项目常量类**，不要硬编码数字。注意审计 §4.1 说"全部落在 `-2`~`-29` 与 `-74`~`-95` 两段"，但实测表里还有 `-96`~`-103` 与 `-999`，**审计那句话不完整，以探针全表为准**。

### 4.5 `Object` 判定方法组（清障动作的白名单判据）

- **结论**：`IsScarecrow()`、`IsFenceItem()`、`IsSprinkler()`、`IsBreakableStone()`、`IsTwig()`、`IsWeeds()`、`IsTapper()`、`isForage()`；另有 `IsConsideredReadyMachineForComputer()`、`IsBreakableStone()` 等大量同类判定。
- **证据出处**：`[实测 Probe10]` `probe10_out.txt:50-57`；`[实测 Probe9]` `probe9_out.txt:215-221`（`IsSprinkler`/`IsBreakableStone`/`IsTextSign`/`IsTwig`/`IsWeeds`/`IsTapper`/`IsBar` 等）。
- **对我们的影响与建议**：清障动作的**前置条件**应直接用这些官方判定，替代旧项目那种"名字含 `Weeds` 或 `ItemId=="0"`"的字符串启发式（`ActionExec.cs:106,111,116,446,466,494`）。旧项目是"官方 API + 字符串兜底"双判据 —— 新项目应只用官方 API，并在它返回 false 时**报错**而不是继续猜。

---

## 5. 地图、传送与可达性判定

### 5.1 ✅ `isCollidingWithWarpOrDoor` 是判断"这一格是否传送点"的**权威方法**

- **结论**：`GameLocation.isCollidingWithWarpOrDoor(...)` 内部**同时考虑 `warps` 与 `doors`**，用的就是玩家真正踩上去时那套判断，因此答案一定与实际行为一致。它非 public，须反射（`Public|NonPublic|Instance`）。返回 `Warp`，可用 `Warp.TargetName` 过滤目标地点。
- **证据出处**：`[旧代码]` `src/AutoFarmWorker/ModEntry.cs:1293-1300`（设计理由原文）、`:1302-1337`（实现：反射取方法 → 全图逐格构造 `Rectangle(x*tileSize, y*tileSize, tileSize, tileSize)` → `m.Invoke(cur, new object[]{ rect, Game1.player }) as Warp` → 比对 `w.TargetName`）。
- **对我们的影响与建议**：**保留这个思路**（"不猜字段语义，直接问游戏"），它是旧项目最有洞察力的 API 决策。**但**方法名本身在探针侧 **`[未验证]`**：`Probe26.cs:28-30` 只是把 `isCollidingWithWarpOrDoor`/`isCollidingWithWarp`/`isCollidingWithDoors` 写成待 dump 的字符串，**没有 dump 输出落盘**（审计 §4.1 已指出）。新项目须先跑 `tools/il-probe` 确认存在与签名。

### 5.2 🔴 跨版本 `Warp` 坐标字段命名不一致，照猜会拿到**目的地**坐标

- **结论**：`Warp` 里两对坐标（`X/Y` 与 `TargetX/TargetY`）语义在版本间不稳定，极易搞反 —— 农舍本身只有 12×12，却拿到了 `(64,15)`（那是**农场**上的坐标），于是寻路目标落在图外，实测刷了 937~971 次 warp。
- **证据出处**：`[旧代码]` `ModEntry.cs:1296-1298`（"Warp 里那两对坐标的命名跨版本都不一致"）、`:1559-1563`（"Warping to Farm 刷 971 次"的历史事故注释）；`[实测运行期数据]` 审计 §0：`farm_tiles.json.save.farm_entry_xy = [64,15]` 与 `Watchdog.cs:371` 硬编码 `Point(64,15)` 逐字相同。
- **对我们的影响与建议**：**禁止按字段名猜 warp 坐标**。只用 `isCollidingWithWarpOrDoor`/`Warp.TargetName` 这类"语义明确"的接口。若必须读坐标，先 IL dump 该方法确认哪个字段是"源格"。

### 5.3 🔴 `Map.DisplayWidth` 在个别地点会抛异常 → 尺寸变 0 → "所有候选都在图外"

- **结论**：`Map.DisplayWidth` 不可靠；被 catch 吞掉后尺寸为 0，导致**出口永远找不到**。正解：遍历 `map.Layers` 取 `LayerWidth`/`LayerHeight` 的最大值，最后才退回 `DisplayWidth / Game1.tileSize`。
- **证据出处**：`[旧代码]` `ModEntry.cs:1490-1494`（注释原文）、`:1495-1519`（`MapExtent` 实现）。**注意** `Map.DisplayWidth` 仍在另一处被直接用：`ModEntry.cs:952`（`if (p.X >= loc.Map.DisplayWidth / Game1.tileSize) return false;`）—— 同一文件里两种写法并存。
- **对我们的影响与建议**：新项目统一用 `MapExtent` 式实现，**并且尺寸取不到时必须显式报错**（旧项目 `IsTileInsideMap` 在 `w<=0` 时 `return true` 放行，`ModEntry.cs:1525`，属静默降级）。

### 5.4 `GameLocation` 可通行性/属性查询 API

- **结论**：`doesTileHaveProperty(Int32 xTile, Int32 yTile, String propertyName, String layerName, Boolean ignoreTileSheetProperties)`、`isWaterTile(Int32,Int32)`、`isTilePassable(Vector2)`、`isTilePassable(Location, Rectangle)`、`isTilePassable(Rectangle, Rectangle)`。
- **证据出处**：`[实测 Probe8]` `probe8_out.txt:282-286`。
- **对我们的影响与建议**：可达性判定的原子操作应基于 `isTilePassable` + `doesTileHaveProperty`，而不是旧项目那种"试着构造 `PathFindController` 看有没有路径"的暴力探测（`ModEntry.cs:1220-1229`）。

### 5.5 `PathFindController` 构造与"发起后立刻验证"

- **结论**：构造函数共 7 个重载，最常用为 `ctor(Character c, GameLocation location, Point endPoint, Int32 finalFacingDirection)`；另有带 `endBehavior`/`limit`/`clearMarriageDialogues` 以及接受现成 `Stack<...> pathToEndPoint` 的版本。`PathFindController` 与 `PathNode` 都在 `StardewValley.Pathfinding` 命名空间。
- **证据出处**：`[实测 Probe8]` `probe8_out.txt:203-212`（7 个 ctor）、`:205`（`StardewValley.Pathfinding.PathFindController`）；`[旧代码]` `ModEntry.cs:1530-1541`（`NewPathController`）与 `:1534` 的 `new ...PathFindController(Game1.player, loc, target, 0)`。
- **对我们的影响与建议**：旧项目三条**值得复用**的规则（审计 §2.3 评为"真本事"）：① 终点必须是**人站得上去的格**（障碍物自身那格不可通行，以它为终点 A* 立刻失败）；② **发起后立刻检查 `ctrl.pathToEndPoint == null || (Count==0 && !NearEnough)`**，无解立刻放弃不空等；③ 超时**按路径步数动态算** `Math.Min(10.0 + steps*0.5, 120.0)`。证据：`[旧代码]` `ModEntry.cs:585-621`、`:596-607`、`:618-621`、`:904`。

### 5.6 `Game1.warpFarmer` 与传送相关 API

- **结论**：`warpFarmer` 有 4 个重载（`(String,Int32,Int32,Boolean)`、`(String,Int32,Int32,Int32)`、`(String,Int32,Int32,Int32,Boolean)`、`(LocationRequest,Int32,Int32,Int32)`）；另有 `warpCharacter`(3 重载)、`warpHome()`、`get_isWarping()`、`get_nonWarpFade()`/`set_nonWarpFade(Boolean)`。
- **证据出处**：`[实测 Probe9]` `probe9_out.txt:628-638`。
- **对我们的影响与建议**：能用 `warpFarmer` 瞬移，但审计 §2.4 证明"瞬移兜底"在旧项目里**实测未生效**（依赖 `warps` 反查落点失败）。新项目应把"移动"建模为独立能力（见 `legacy-design-patterns.md` §5），瞬移只作为**显式、可记账、失败即报错**的降级手段。

### 5.7 ⚠️ `Game1.getFarm()` 会抛 `KeyNotFoundException`

- **结论**：不要用 `Game1.getFarm()`，改为遍历 `Game1.locations` 或用自己的 `TryGetLocation(name)`。
- **证据出处**：`[文档线索]` 审计 §4.1 引自 `ARCHITECTURE.md:366`；**探针侧反证**：`[实测 Probe13]` `probe13_out.txt:198` 显示 `static Farm getFarm()` **确实存在**。存在 ≠ 安全调用（抛异常是运行期行为，反射可见性查不出来）。
- **对我们的影响与建议**：**标 `[未验证]` 的存在性风险**。"存在"已实测，"会抛异常"仅有文档线索。新项目：包一层 `TryGetFarm()` 并捕获，且**首次失败就报 Error**，不要静默返回 null。

---

## 6. 商店 / 买卖 / 时间（`[实测 Probe9]` `[实测 Probe10]`）

### 6.1 `ShopMenu` 关键成员

- **结论**：字段 `ShopId`、`ShopData`、`itemPriceAndStock`(Dictionary)、`forSale`(List)、`heldItem`/`hoveredItem`(ISalable)、`currency`(Int32)、`onPurchase`(OnPurchaseDelegate)、`onSell`(Func)、`readOnly`(Boolean)、`buyBackItems`(HashSet)；方法 `highlightItemToSell(Item)`、`CanBuyback()`、`BuyBuybackItem(ISalable,Int32,Int32)`、`AddBuybackItem(ISalable,Int32,Int32)`、`HandleSynchedItemPurchase(ISalable,Farmer,Int32)`。构造 3 个重载。
- **证据出处**：`[实测 Probe9]` `probe9_out.txt:27-76`（成员全表）、`:71-76`（方法）；`[实测 Probe8]` `probe8_out.txt:71-73`（3 个 ctor）；`[实测 Probe10]` `probe10_out.txt:138-141`。
- **对我们的影响与建议**：要做**真交易**，用 `Utility.TryOpenShopMenu(shopId, ...)` 开店后走 `HandleSynchedItemPurchase` 或直接操作 `itemPriceAndStock`。**不要**学旧项目 `AutoFarmTrader` 那种"直接 `Money += gain` + `removeItemFromInventory`"的凭空买卖（审计 §6.4 定性为经济作弊）。

### 6.2 `Utility.TryOpenShopMenu` 重载

- **结论**：`Boolean TryOpenShopMenu(String shopId, String ownerName, Boolean playOpenSound)`；`Boolean TryOpenShopMenu(String shopId, GameLocation location, Nullable ownerArea, Nullable maxOwnerY, Boolean forceOpen, Boolean playOpenSound, Action<...> showClosedMessage)`；另有 `List<...> getDaysOfBooksellerThisSeason()`。
- **证据出处**：`[实测 Probe9]` `probe9_out.txt:81-83`；`[实测 Probe10]` `probe10_out.txt:132-133`。
- **对我们的影响与建议**：第二个重载带 `forceOpen`，可绕过"店主不在/营业时间"—— 是否使用是**产品决策**，新项目应显式配置并记账。

### 6.3 `Game1.shop_*` 常量全表（34 个）

- **结论**：`shop_adventurersGuild`、`shop_adventurersGuildItemRecovery`、`shop_animalSupplies`、`shop_blacksmith`、`shop_blacksmithUpgrades`、`shop_boxOffice`、`shop_catalogue`、`shop_carpenter`、`shop_casino`、`shop_desertTrader`、`shop_dwarf`、`shop_fish`、`shop_furnitureCatalogue`、`shop_generalStore`、`shop_hatMouse`、`shop_hospital`、`shop_iceCreamStand`、`shop_islandTrader`、`shop_jojaMart`、`shop_krobus`、`shop_qiGemShop`、`shop_resortBar`、`shop_sandy`、`shop_saloon`、`shop_travelingCart`、`shop_volcanoShop`、`shop_bookseller`、`shop_bookseller_trade`、`shop_jojaCatalogue`、`shop_wizardCatalogue`、`shop_junimoCatalogue`、`shop_retroCatalogue`、`shop_trashCatalogue`、`shop_petAdoption`。
- **证据出处**：`[实测 Probe9]` `probe9_out.txt:89-122`（逐条为 `static field String ...`）。
- **对我们的影响与建议**：**共 34 条**。买种子用 `shop_generalStore`/`shop_sandy`（沙漠）；工具升级用 `shop_blacksmith` 或 `shop_blacksmithUpgrades`。直接搬进常量类。

### 6.4 睡觉 / 新一天

- **结论**：`Game1.NewDay(Single timeToPause)`、`Game1.newDayAfterFade(Action after)`、`Game1.PassOutNewDay()`、`Game1.PollForEndOfNewDaySync()`、`Game1.UpdateWeatherForNewDay()`、`Game1.ApplyWeatherForNewDay()`；另有私有 `_newDayAfterFade()`(IEnumerator) 与 `<onFadeToBlackComplete>g__AfterNewDay|746_0()`。`Farmer.dayupdate(Int32 timeWentToSleep)`、`GameLocation.DayUpdate(Int32 dayOfMonth)`。
- **证据出处**：`[实测 Probe9]` `probe9_out.txt:88-93`、`:137-141`；`[实测 Probe8]` `probe8_out.txt:129-141`；`[实测 Probe10]` `probe10_out.txt:120-127`。
- **对我们的影响与建议**：`newDayAfterFade(Action after)` 是**带回调的安全入口**（回调在淡入淡出结束后执行），优先于裸 `NewDay`。

### 6.5 床与睡眠成员

- **结论**：`BedFurniture`（全名 `StardewValley.Objects.BedFurniture`）：`GetBedSpot()`、`get_bedType()`/`set_bedType(BedType)`、`IsBeingSleptIn()`、`DayUpdate()`、`CanModifyBed(Farmer)`、`GetSittingPosition(...)` 等。`Farmer` 侧字段：`timeWentToBed`(NetInt)、`sleptInTemporaryBed`(NetBool)、`mostRecentBed`(Vector2)、`isInBed`(NetBool)、`passedOut`(Boolean)、`lastSleepLocation`(NetString)、`lastSleepPoint`(NetPoint)。
- **证据出处**：`[实测 Probe9]` `probe9_out.txt:100-163`（方法组）、`:365-371`（字段组）。
- **对我们的影响与建议**：判断"今天睡过没"读 `Farmer.isInBed`/`timeWentToBed`，不要靠时间戳猜。

### 6.6 `FarmAnimal` / `AnimalHouse`（牧场）

- **结论**：`FarmAnimal` 字段 `currentProduce`(NetString)、`friendshipTowardFarmer`、`age`、`health`、`happiness`、`fullness`、`wasPet`(NetBool)、`type`(NetString)、`position`(NetPosition)；方法 `pet(Farmer,Boolean is_auto_pet)`、`GetProduceID(Random,Boolean deluxe)`、`dayUpdate(GameLocation)`、`CanGetProduceWithTool(Tool)`、`Eat(GameLocation)`、`DigUpProduce(GameLocation,Object)`。
  `AnimalHouse` 字段 `animalLimit`(NetInt)、`animals`(NetLongDictionary&lt;FarmAnimal,NetRef&lt;FarmAnimal&gt;&gt;)、`animalsThatLiveHere`(NetLongList)、`piecesOfHay`(NetInt)、`parentLocationName`(NetString)、`ParentBuilding`；方法 `feedAllAnimals()`、`getAllFarmAnimals()`、`addNewHatchedAnimal(String)`、`adoptAnimal(FarmAnimal)`、`resetPositionsOfAllAnimals()`。
- **证据出处**：`[实测 Probe13]` `probe13_out.txt:5-21`（FarmAnimal）、`:26-130`（AnimalHouse 字段/方法与继承来的 `GameLocation` 成员）、`:119-130`（方法组）。
- **对我们的影响与建议**：喂食直接用 `house.feedAllAnimals()`（官方接口，旧项目 `AutoFarmRancher/ModEntry.cs:238-288` 就是这么做的，审计评为"最扎实"）。**注意** `animals` 的值是 `NetRef<FarmAnimal>`，必须再取一次 `.Value`。`Game1.getFarm()` 与 `GameLocation.animals` 均存在（`probe13_out.txt:135-137,180`）。

### 6.7 加工机器

- **结论**：`Object` 字段 `bigCraftable`(NetBool)、`readyForHarvest`(NetBool)、`heldObject`(NetRef&lt;StardewValley.Object&gt;)、`minutesUntilReady`(NetIntDelta)；属性 `MinutesUntilReady`(可写)、`Name`(可写)、`QualifiedItemId`(只读)；方法 `performObjectDropInAction(Item dropInItem, Boolean probe, Farmer who, Boolean returnFalseIfItemConsumed)`、`PlaceInMachine(...)`、`OutputMachine(...)`、`onReadyForHarvest()`、`ShouldTimePassForMachine()`、`IsConsideredReadyMachineForComputer()`、`GetMachineData()`。
- **证据出处**：`[实测 Probe13]` `probe13_out.txt:142-156`（字段与方法）、`:144` 含程序集版本 `Version=1.6.15.24356`；`[实测 Probe9]` `probe9_out.txt:155`（`performObjectDropInAction` 签名）、`:193-207`（`onReadyForHarvest`/`ShouldTimePassForMachine`/`GetMachineData` 等）。
- **对我们的影响与建议**：`bigCraftable`/`readyForHarvest`/`heldObject` 都是 **`NetXxx` 包装**，判空必须 `.Value`（`readyForHarvest?.Value == true`）。投料用 `performObjectDropInAction(item, false, Game1.player, false)`（第 4 参 `returnFalseIfItemConsumed`）。

### 6.8 钓鱼（`BobberBar`）

- **结论**：`BobberBar : IClickableMenu`。关键字段：`difficulty`(Single)、`motionType`(Int32)、`bobberPosition`、`bobberSpeed`、`bobberAcceleration`、`bobberTargetPosition`、`bobberBarPos`、`bobberBarSpeed`、`bobberBarHeight`(Int32)、`bobberInBar`(Boolean)、`distanceFromCatching`(Single)、`perfect`、`treasure`、`treasureCaught`、`fishSize`(Int32)、`fishQuality`(Int32)、`challengeBaitFishes`、`scale`、`bobbers`(List)、`fishShake`/`treasureShake`(Vector2)、私有 `fishObject`(Item)。
  构造：`ctor(String whichFish, Single fishSize, Boolean treasure, List bobbers, String setFlagOnCatch, Boolean isBossFish, String baitID, Boolean goldenTreasure)`。
- **证据出处**：`[实测 Probe11]` `probe11_out.txt:5`（类型+基类）、`:10-40`（字段全表）、`:45`（`Position` 属性）、`:149`（ctor）。
- **对我们的影响与建议**：这 30 个字段是"改判定通关"的全部抓手。旧项目 `instant` 模式直接写 `bar.distanceFromCatching = 1f; bar.bobberInBar = true;`（`AutoFarmFishing/ModEntry.cs:262-263`）—— **能赢但没玩**。新项目若要求"模拟玩家"，必须每帧推 `bobberBarPos`，并注意 `:287` 的 `568f` 是**魔法数字**（"BobberBar 内部高度近似"），需先用探针确认真实内部高度。
- **收杆**：`FishingRod.pullFishFromWater(String fishId, Int32 fishSize, Int32 fishQuality, Int32 fishDifficulty, Boolean treasureCaught, Boolean wasPerfect, Boolean fromFishPond, String setFlagOnCatch, Boolean isBossFish, Int32 numCaught)`、`doneFishing(Farmer who, Boolean consumeBaitAndTackle)`、`tickUpdate(GameTime, Farmer)`、`getBobberStyle(Farmer)`。证据：`[实测 Probe11]` `probe11_out.txt:158-159`、`:474-478`。

### 6.9 采集物 / 掉落物

- **结论**：`Debris : Object`；`Debris.collect(Farmer, Chunk)`、`Debris.item`(Item)、`itemQuality`、`chunksMoveTowardPlayer`、`Chunks`(NetObjectShrinkList)。`GameLocation` 侧：`sinkDebris(Debris,Vector2,Vector2)`、`doesTileSinkDebris(...)`、`removeDamageDebris(Monster)`、`IsDebrisWeatherHere()`、`OnHarvestedForage(Farmer,Object)`、`getTotalForageItems()`。
- **证据出处**：`[实测 Probe8]` `probe8_out.txt:225-246`（`Debris: Object` 及成员）；`[实测 Probe9]` `probe9_out.txt:508-509`（`Debris.collect(Farmer, Chunk)`）、`:526-533`（Debris 属性）。
- **对我们的影响与建议**：拾取掉落物走 `Debris.collect`，不要手改 `Chunks`。

### 6.10 菜单 / 输入 / 阻塞判定

- **结论**：`Game1.input`(static InputState)、`Game1.dialogueUp`(static Boolean)、`Game1.eventUp`(static Boolean)、`Game1.activeClickableMenu`(IClickableMenu)。`NPC.CurrentDialogue` 是 `Stack<...>`（1.6 对话队列挂在说话人身上）。`Game1.getCharacterFromName(String, Boolean mustBeVillager, Boolean includeEventActors)` 有两个重载（泛型 T 与非泛型 NPC）。
- **证据出处**：`[实测 Probe9]` `probe9_out.txt:5-8`（前四项）、`:643-647`（`getCharacterFromName` 与 `NPC.CurrentDialogue`/`Name`）。
- **对我们的影响与建议**：阻塞解锁判据 = `!Context.IsPlayerFree`（SMAPI）+ `Game1.dialogueUp`/`eventUp`/`activeClickableMenu`（游戏）。旧项目 `WatchdogUnblockMenu`（`Watchdog.cs:387-462`）就是这套，实测**有效**（审计 §3.1 第 4 项）。且必须挂在这些检查**之前**才能生效。

---

## 7. 1.6.15 特有坑（完整清单）

### 7.1 🔴 SMAPI `ReadJsonFile` **不做 snake_case→PascalCase 转换**，但大小写不敏感 ⇒ 带下划线字段**静默丢失**

- **结论**：`expires_at` / `plan_basis` / `issued_at` 这类**带下划线**的 JSON 字段反序列化时**静默丢失**，不报错、不告警；单词字段（`goal`/`reason`/`mode`/`plan`）不受影响。修复 = 每个字段显式 `[JsonProperty("snake_case")]` + 往返自检。
- **证据出处**：`[旧代码]` `src/AutoFarmWorker/AiDirective.cs:45-127`（逐字段 `[JsonProperty]`）、`:195-203`（注释明写这是实测踩过的坑）、`:204-260`（`SelfTest()`）；审计 §4.1 与 `ARCHITECTURE.md:365` 记同一坑。
- **对我们的影响与建议**：**新项目所有跨语言 JSON 契约都必须**：① 每个字段显式 `[JsonProperty]`；② 启动时跑一次往返 `SelfTest`，失败即 Error 级失败。这一条要用在**所有**契约面（指令、快照、结果），不要只用在指令上。

### 7.2 🔴 `expires_at` "安全阀"因**两端各错一半**而永久失效（完整因果链）

- **结论**：Python 侧写的是**空字符串**，C# 侧 `IsExpired()` 解析失败时 `return false`（宽松处理）。二者相加 ⇒ 安全阀**永不触发**，过期分支是**死代码**。
- **证据出处**：`[旧代码]` `src/AutoFarmWorker/AiDirective.cs:143-145`（"格式不对 → 宽松处理，不算过期"）与 `:115`（审计引 `ai_planner.py:487` 写空串、`ModEntry.Ai.cs:204` 为死代码）。
- **对我们的影响与建议**：**"宽松解析" + "宽松写入" 是两个独立的静默失败，叠加后防护归零**。新项目规则：任何安全阀字段**写入端必须校验非空**、**读取端解析失败必须视为过期（fail-closed）**。

### 7.3 `Crop.harvest` 可选 `JunimoHarvester` 参数 ⇒ CS1503

- 见 §2.1。`[实测 Probe10]` `probe10_out.txt:114`。

### 7.4 `Crop` 继承 `Object`(System) ⇒ CS8121

- 见 §2.3。`[未验证]`（文档线索）。

### 7.5 没有 `Tree.stumpFall()` ⇒ CS1061

- **结论**：`Tree` 无 `stumpFall()` 方法；不要试图调用它让树倒下，改走 `Tool.DoFunction`。
- **证据出处**：`[旧代码]` `ActionExec.cs:512`（"没有 `stumpFall()` 这种 API 可用（实测 CS1061）"）。探针侧：`[实测 Probe8]` `probe8_out.txt:256-268` 列出 `Tree`/`FruitTree` 仅有 `shake` 与 `performToolAction`，**未见 `stumpFall`** —— 与旧代码结论一致。
- **对我们的影响与建议**：树倒动画与木材结算由 `DoFunction` 负责。

### 7.6 `performToolAction` 假定工具处于"使用中"，会读 `lastFarmerToUse` 抛空引用

- 见 §1.3。`[旧代码]` `ActionExec.cs:519-521`。

### 7.7 🔴 `removeItemFromInventory` 无 count 参数会清空整叠

- 见 §4.1。`[实测 Probe8]` `probe8_out.txt:321-322`。

### 7.8 `Game1.getFarm()` 会抛 `KeyNotFoundException`

- 见 §5.7。**存在性已实测**（`probe13_out.txt:198`），**抛异常仅有文档线索 ⇒ 整体标 `[未验证]`**。

### 7.9 🔴 `Options.pauseWhenOutOfFocus`：界面里已无对应文本，但 `Game1._update` 仍读它

- **结论**：该选项**在游戏界面里根本不存在**（实测扫描 Content 下全部 **3560** 个文件，没有任何一处包含它的界面文本），但 IL 扫描确认 `Options.pauseWhenOutOfFocus` **仍被 `Game1._update` 读取**（即仍生效）。一旦为 `true`，只要游戏窗口不是前台，**整个世界冻结**：时钟不走、Mod 不干活、AI 计划一条也执行不了。而快照看起来完全正常（体力满、作物待浇、时间 8:10），实际是几十秒前的冻结画面。
- **证据出处**：`[旧代码]` `src/AutoFarmWorker/ModEntry.FocusPause.cs:11-22`（注释原文，含 3560 与 IL 扫描结论）、`:40-62`（`ReadFocusPause`/`WriteFocusPause` 用反射读写该字段）；`ModConfig.cs:244,254`（`DisablePauseWhenOutOfFocus = true` 默认关闭该选项）；`ModEntry.TileMap.cs:30` 记同一坑。
- **对我们的影响与建议**：**必须主动关掉它**（反射写 `false`），并在**多个时点各调一次**（启动 / 读档 / 换天），因为游戏可能从配置文件重新读回。同时**必须**把"世界是否在推进"写进快照（见 §8），让上游拒绝基于冻结数据规划。
- **可信度说明**："界面无文本"与"IL 扫描确认仍被读取"来自旧代码注释（作者自述已完成该扫描），**原始扫描产物未落盘** ⇒ 这两条按本页口径应为 **`[旧代码]`（作者自述实测）**，若新项目需要硬证据，应重跑一次 IL dump + Content 全文搜索。

### 7.10 🔴 `isCollidingWithWarpOrDoor` 是权威传送判定（且 warp 坐标字段命名跨版本不一致）

- 见 §5.1、§5.2。方法名本身 `[未验证]`（Probe26 无 dump 输出）。

### 7.11 `NetIntList` 只有 `Count`，没有 `phaseDays.Length` ⇒ CS1061

- **结论**：`NetIntList` 不支持数组式 `.Length` 访问，只能用 `Count`。
- **证据出处**：`[文档线索]` 审计 §4.1 引自 `ARCHITECTURE.md:362`；探针侧**无直接证据**。
- **对我们的影响与建议**：**标 `[未验证]`**。常见替代：读 `Crop.phaseDays` 前先确认类型；或改用 `Crop` 的 `dayInPhase`/`currentPhase` 等标量字段。

### 7.12 🔴 1.6 造物品必须用 `ItemRegistry.Create("(O)"+id)`

- 见 §4.3。`[旧代码]` `ModEntry.cs:515-517`。

### 7.13 🔴 `Map.DisplayWidth` 在个别地点抛异常 ⇒ 尺寸变 0 ⇒ 出口永远找不到

- 见 §5.3。`[旧代码]` `ModEntry.cs:1490-1494`。

### 7.14 机器判断需 `.Value` 二次取值

- 见 §6.7。`[实测 Probe13]` `probe13_out.txt:142-144`。

### 7.15 `NetLongDictionary` 的值是 `NetRef<T>`，要再取一次 `.Value`

- **结论**：`GameLocation.animals` 的类型是 `NetLongDictionary<FarmAnimal, NetRef<FarmAnimal>>`，遍历得到的值是 `NetRef<FarmAnimal>`。
- **证据出处**：`[实测 Probe13]` `probe13_out.txt:180`（带完整程序集限定名）、`:102`（`prop NetLongDictionary\`2 Animals`）；审计 §4.1 亦提醒。
- **对我们的影响与建议**：所有 `Net*` 字典/引用容器都要 `.Value`。建议在新项目里写一个统一访问器，**禁止**直接在业务代码里点 `.Value`（漏一次就是空引用或错误状态）。

### 7.16 《星露谷》季节判定：不能用"地点是否存在"判断温室是否解锁

- **结论**：**温室地点始终存在**，只是内容被禁用。必须用 `farm.greenhouseUnlocked?.Value == true` 判断。
- **证据出处**：`[旧代码]` `src/AutoFarmPlanner/ModEntry.cs:203-205`（判定）与 `:204` 的注释（"不能用『地点是否存在』判断 —— 温室地点始终存在，只是内容被禁用"）、`:207-211`（只在解锁后才纳入扫描）。
- **对我们的影响与建议**：这是一条**通用的 1.6 建模原则**：地点/建筑/功能的"存在"≠"可用"。新项目所有功能开关都要有显式的解锁判定，不要用"对象是否非 null"代替。

### 7.17 季节常量 API

- **结论**：`Game1.season`(static Season)、`Game1.getSeasonNameFromNumber(Int32)`、`getSeasonKey(Season)`、`getSeasonNumber(String whichSeason)`、`debrisWeatherSeason`(static Nullable)。
- **证据出处**：`[实测 Probe13]` `probe13_out.txt:169-175`。
- **对我们的影响与建议**：季节→字符串/编号的转换用官方方法，不要自己写映射表。

---

## 8. 未验证清单（本页所有 `[未验证]` 项汇总）

> 以下内容**没有实测输出背书**，新项目使用前必须在真机验证。

| # | 内容 | 为什么未验证 | 建议验证方式 |
|---|---|---|---|
| 1 | `Crop` 的基类是 `System.Object` ⇒ CS8121 | 仅 `ARCHITECTURE.md:361` 文档线索 | 探针 dump `typeof(Crop).BaseType` |
| 2 | `Game1.getFarm()` 会抛 `KeyNotFoundException` | 只有文档线索；`getFarm()` 存在性已由 `probe13_out.txt:198` 证实 | 真机调一次并捕获 |
| 3 | `NetIntList` 只有 `Count`，无 `phaseDays.Length` ⇒ CS1061 | 仅 `ARCHITECTURE.md:362` | 探针 dump `NetIntList` 成员 |
| 4 | `GameLocation.isCollidingWithWarpOrDoor` 的存在与签名 | `Probe26.cs:28` 只是待 dump 的字符串，**无输出** | 跑 `tools/il-probe`（Probe26） |
| 5 | `PathFindController.handleWarps` / `getWarpFromDoor` / `openDoor` / `isCollidingWithWarp` / `isCollidingWithDoors` 的存在 | 同上（`Probe26.cs:25-30`） | 同上 |
| 6 | `Options.pauseWhenOutOfFocus` 的"界面无文本 + 仍被 `Game1._update` 读取" | 旧代码注释自述，原始扫描产物未落盘 | 重跑 IL dump + Content 全文搜索（3560 文件） |
| 7 | `Crop.fullyGrown` 的类型与可访问性 | 旧代码大量使用，但**无任何探针输出** | 探针 dump `Crop` 字段表 |
| 8 | `ResourceClump` 究竟落在 `terrainFeatures` 还是 `resourceClumps` | 两个集合都存在（`probe8_out.txt:278`），旧代码在 `terrainFeatures` 里找它（`ActionExec.cs:483`），与 `resourceClumps` 的存在矛盾 | 真机打印两个集合的键 |
| 9 | `Probe12`/`Probe14`~`Probe25` 的全部 API 假设（含 `WateringCan` 字段、矿洞/怪物/体力、失焦暂停专探） | 只有源码无输出 | 逐个重跑（清单见 `INDEX.md`） |
| 10 | `BobberBar` 内部高度常量（旧代码 `AutoFarmFishing/ModEntry.cs:287` 的 `568f`） | 魔法数字，无探针 | 探针 dump `BobberBar` 的 `bobberBarHeight` 取值域 |

---

## 9. 高频踩坑速查（TOP 10）

| # | 坑 | 正确做法 | 可信度 |
|---|---|---|---|
| 1 | `removeItemFromInventory(Item)` 清空整叠 | `Inventory.Reduce`/直接改 `Stack`；动作后核对副作用 | `[实测 Probe8]` + `[旧代码]` |
| 2 | snake_case 字段静默丢失 | 每字段 `[JsonProperty]` + 启动 `SelfTest` | `[旧代码]`（实测踩过） |
| 3 | 安全阀 `expires_at` 两端都宽松 ⇒ 永久失效 | 写入端校验非空，读取端 fail-closed | `[旧代码]` |
| 4 | `Crop.harvest` 带可选参数 ⇒ CS1503 | 反射取最少参数重载 | `[实测 Probe10]` |
| 5 | `DoFunction` 坐标是像素不是格子 | `tile × 64` | `[实测 Probe8]` + `[旧代码]` |
| 6 | `Bush : LargeTerrainFeature`（非 `TerrainFeature`） | 显式建模两条继承链，别用字符串比较 | `[实测 Probe8]` |
| 7 | `ResourceClump` 命名空间是 `TerrainFeatures` | 用全名 | `[实测 Probe10]` |
| 8 | `Map.DisplayWidth` 抛异常 ⇒ 尺寸 0 ⇒ 出口找不到 | 遍历 `map.Layers` 取 `LayerWidth/Height` | `[旧代码]` |
| 9 | `pauseWhenOutOfFocus` 界面不可见但世界会冻结 | 反射强制关掉 + 快照里验活性 | `[旧代码]`（作者自述实测） |
| 10 | 1.6 造物品必须 `ItemRegistry.Create("(O)"+id)` | 不用 `new Object(...)` | `[旧代码]` |

---

*本页仅整理，未修改旧项目任何文件。所有 `文件:行号` 均相对旧仓库根 `C:\Users\admin\WorkBuddy\2026-10-04-20-36-38\stardew-auto-farm`。*
