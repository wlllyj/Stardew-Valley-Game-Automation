# 铁匠铺工具升级链：IL + 可见性取证（task-153）

> 只读取证（Lead m07115 的 task-153）。所有结论标【已证】/【未定】/【已证伪】，每条都带探针文件与行号。
> 探针：`tools/il-probe`（`scratch/_probe_il.py` 封装）+ 本次新建的只读可见性探针
> `scratch/_api_up/`（反射元数据，不跑游戏）。原始输出全部落 `scratch/`。
> **纪律**：本文件只描述游戏侧事实与我们代码错在哪；脑侧/桥侧改法归 task-141/142。

## 0. 一句话结论

【已证】升级链是：**与 Clint 对话选「Upgrade」（应答键 `Blacksmith_Upgrade`）→ 游戏开商店
`Utility.TryOpenShopMenu("ClintUpgrade", "Clint", true)` → 在商店里买下工具条目时
`ShopMenu.tryToPurchaseItem` 先 `chargePlayer`（扣金币）+ `ConsumeTradeItem`（扣 5 条金属锭），
再调 `Tool.actionWhenPurchased("ClintUpgrade")` ⇒ `Farmer.toolBeingUpgraded.Value = 工具副本`、
`Farmer.daysLeftForToolUpgrade.Value = 2`；此后每过一天 `Farmer.dayupdate` 把 `daysLeft` 减 1，
减到 `<= 0` 后再跟 Clint 说话才会**取回**（`toolBeingUpgraded.Value = null` + 工具进背包，等级 +1）。

**对我们最有用的三条**：
1. 入口是 **`Utility.TryOpenShopMenu(String, String, Boolean)`（public static）** ⇒ 不需要伪造对话
   （`scratch/_api_up_out_u8.txt:18-19`）。
2. 购买入口 `ShopMenu.tryToPurchaseItem` 是 **private** ⇒ 只能反射（先例：`mod/AgentFarm.Bridge/BuySkill.cs:300-306`）。
3. **钱与材料在 `actionWhenPurchased` 之前就扣掉了**（IL_0131/IL_0142 早于 IL_0161，
   `scratch/il-up-2.txt:432-450`）⇒ 我们的 Mod 必须在购买前自己判「当前没有工具在升级」，
   否则会白扣钱（见 §5 陷阱）。

## 1. 答案①：升级入口在哪

【已证】两个字符串分支都在 `GameLocation.answerDialogueAction(String, String[])`：

| 应答键 | 分支目标 | 行为 |
| --- | --- | --- |
| `Blacksmith_Shop` | `IL_2FF8`（`scratch/il-up-3.txt:3473-3477`） | `Utility.TryOpenShopMenu("Blacksmith", "Clint", true)`（普通商店） |
| `Blacksmith_Upgrade` | `IL_300E`（`scratch/il-up-3.txt:3479-3508`） | `if (player.daysLeftForToolUpgrade.Value > 0) → Clint 说 "Data\ExtraDialogue:Clint_StillWorking"（带工具名）；else → Utility.TryOpenShopMenu("ClintUpgrade", "Clint", true)` |
| `Blacksmith_Process` | `IL_3078`（`scratch/il-up-3.txt:3509-3511`） | `new <类型被探针屏蔽>()` + `set_activeClickableMenu(...)`（【未定】具体菜单类型，见 §8 U3） |

`Blacksmith_Upgrade` 的字符串常量位置：`scratch/il-up-3.txt:566`；`Blacksmith_Shop`：`:615`。

【已证】这些应答键由 `GameLocation.blacksmith(Location tileLocation)` 通过
`createQuestionDialogue("", responses, "Blacksmith")` 挂出（`scratch/il-up-2.txt:212-216`），
选项键与文案：`Shop`=`Strings\Locations:Blacksmith_Clint_Shop`、
`Upgrade`=`…:Blacksmith_Clint_Upgrade`、`Process`=`…:Blacksmith_Clint_Geodes`（有晶球时才有此选项，
`scratch/il-up-2.txt:147-183`）、`Leave`=`…:Blacksmith_Clint_Leave`。
⇒ 应答键 = `Blacksmith` + `_` + 选项键。

【已证】取回工具的分支就在同一个 `blacksmith()` 方法开头：
`if (Game1.player.toolBeingUpgraded.Value != null && Game1.player.daysLeftForToolUpgrade.Value <= 0)`
⇒ `toolBeingUpgraded.Value = null`、`hasReceivedToolUpgradeMessageYet = false`、
`holdUpItemThenMessage(tool, true)`、`addItemToInventoryBool(tool, false)`，
并在 `useSeparateWallets && tool.UpgradeLevel == 4` 时发 `IridiumToolUpgrade` 全局消息
（`scratch/il-up-2.txt:2-121`）；背包满且不是 GenericTool 时改说
`Data\ExtraDialogue:Clint_NoInventorySpace`（`:120-122`）。

【已证】`FIND|Blacksmith` 命中 4 个调用方法，其中包含
`StardewValley.GameLocation.performAction(String[] action, Farmer who, Location tileLocation) → GameLocation.blacksmith`
⇒ 地图 `Action` 也能触发（具体 action 字符串【未定】，未单独转储 `performAction`）。

## 2. 答案②：菜单与选项类型

【已证】`Utility.TryOpenShopMenu(shopId, ownerName, playOpenSound)` 的完整头段
（`scratch/il-up-3.txt:4164-4225`）：从 `DataLoader.Shops(content)` 取 `Dictionary<String, ShopData>`，
按 `shopId` `TryGetValue` ⇒ **取不到就直接 `return false`**（IL_001F-0022）；
`ownerName` 先 `TryParseEnum<ShopOwnerType>`（解析失败就按 0），再 `GetCurrentOwners(shopData)` 选 owner。
⇒ 商店内容 100% 数据驱动，来自 `Data/Shops` 里的 `ClintUpgrade` 条目。

【已证】`ShopMenu` 的公开构造函数（`scratch/_api_up_out_u8.txt:27-29`）：
```csharp
public ShopMenu(string shopId, ShopData shopData, ShopOwnerData ownerData, NPC owner,
                OnPurchaseDelegate onPurchase, Func<ISalable,bool> onSell, bool playOpenSound)
public ShopMenu(string shopId, Dictionary<ISalable, ItemStockInformation> itemPriceAndStock,
                int currency, string who, OnPurchaseDelegate on_purchase, Func<…> on_sell, bool playOpenSound)
public ShopMenu(string shopId, List<ISalable> itemsForSale, int currency, string who, …)
```
关键公开字段（`scratch/_api_up_out_u8.txt:31-38`）：`public Dictionary<ISalable, ItemStockInformation> itemPriceAndStock`、
`public string ShopId`、`public ISalable heldItem`、`public bool readOnly`、`public int currency`、
`public static void chargePlayer(Farmer, int, int)`、`public static int getPlayerCurrencyAmount(Farmer, int)`；
而 **`private bool tryToPurchaseItem(ISalable, ISalable, int, int, int)`**（`:30`）。

【已证】工具升级条目的数据形状 = `StardewValley.GameData.Tools.ToolUpgradeData`
（`scratch/_api_up_out_u8.txt:118-123`）：`Condition`(GameStateQuery 串) / `Price`(int) /
`RequireToolId`(string) / `TradeItemAmount`(int) / `TradeItemId`(string)。
它由 `ShopBuilder.GetToolUpgradeData(ToolData tool, Farmer player)`（**public static**）现算
（`scratch/il-up-3.txt:4572-4671`）：以 `tool.ConventionalUpgradeFrom` 为 `RequireToolId`、
`GetToolUpgradeConventionalPrice(tool.UpgradeLevel)` 为 `Price`、
`GetToolUpgradeConventionalTradeItem(tool.UpgradeLevel)` 为 `TradeItemId`、`TradeItemAmount = 5`，
再与工具自己的 `ToolData.UpgradeFrom` 列表 `Concat`；
遍历时先看 `Condition`（`GameStateQuery.CheckConditions`，IL_008E-00AC）、
再看 `RequireToolId` 是否在 `player.Items` 里（`Inventory.ContainsId`，IL_00AE-00C9）⇒ 命中即返回。

## 3. 答案③：升级状态在 Farmer/Tool 上的确切成员（全部 public）

【已证】反射输出 `scratch/_api_up_out_u8.txt:1-15`：

| 类型 | 成员 | 可见性/类型 | 用途 |
| --- | --- | --- | --- |
| `Farmer` | `toolBeingUpgraded` | `public field NetRef<Tool>` | 正在升级的工具（`null` = 没有） |
| `Farmer` | `daysLeftForToolUpgrade` | `public field NetInt` | 还剩几天（买下时 = 2） |
| `Farmer` | `hasReceivedToolUpgradeMessageYet` | `public field bool` | 「工具好了」提示是否已弹过 |
| `Farmer` | `showToolUpgradeAvailability()` | `public Method` | 每天检查是否该提示 |
| `Tool` | `UpgradeLevel` | `public property int`（`get_`/`set_` 都是 public） | 等级 1..4（0 = 基础） |
| `Tool` | `indexOfMenuItemView` | `public field NetInt` | GenericTool 用它判等级（13..16 ⇒ 铜..铱） |
| `Tool` | `GetToolData()` | `public Method` | 取该工具的 `ToolData` |
| `Tool` | `UpgradeFrom(Tool other)` | `public Method` | 升级时承接旧工具（附魔/属性） |
| `Tool` | `actionWhenPurchased(string shopId)` | `public Method` | 真正的升级动作 |

【已证】每过一天扣一天：`Farmer.dayupdate(Int32 timeWentToSleep)`
（`scratch/il-up-4.txt:34-47`）：`if (daysLeftForToolUpgrade.Value > 0) daysLeftForToolUpgrade.Value--;`。
【已证】提示时机：`Farmer.showToolUpgradeAvailability()`（`scratch/il-up-3.txt:4817-4868`）：
`toolBeingUpgraded != null && daysLeft <= 0 && toolBeingUpgraded.Value != null && !isFestivalDay
&& (shortDayName != "Fri" || !hasCompletedCommunityCenter() || isRaining) && !hasReceivedToolUpgradeMessageYet`
⇒（`Game1.newDay` 时）把消息压进 `morningQueue`，否则 `showGlobalMessage("Strings\StringsFromCSFiles:ToolReady", 工具名)`。

## 4. 答案④：价格与条件

【已证】`ShopBuilder.GetToolUpgradeConventionalPrice(Int32 level)`（`scratch/il-up-3.txt:4674-4689`）
= `switch (level - 1)`：

| `tool.UpgradeLevel`（当前等级） | 目标等级 | `Price` | `TradeItemId`（`GetToolUpgradeConventionalTradeItem`，`scratch/il-up-4.txt:500-515`） | `TradeItemAmount` |
| --- | --- | --- | --- | --- |
| 0（基础） | 1 铜 | **2000** | `334` 铜锭 | 5 |
| 1（铜） | 2 钢 | **5000** | `335` 铁锭 | 5 |
| 2（钢） | 3 金 | **10000** | `336` 金锭 | 5 |
| 3（金） | 4 铱 | **25000** | `337` 铱锭 | 5 |
| 其它/默认 | — | 2000 | `334` | 5 |

`TradeItemAmount = 5` 是硬编码在 `GetToolUpgradeData` 里（`scratch/il-up-3.txt:4602-4604`，`ldc.i4.5`）。
【未定】`GetToolUpgradeConventionalTradeItem` 是 **private static**（`scratch/_api_up_out_u8.txt:24`）
⇒ 我们不能直接调它；要读表就自己按上表映射，或读 `ToolUpgradeData.TradeItemId`。

【已证】必要条件 = ①`ToolUpgradeData.Condition`（GameStateQuery）通过 +
②`RequireToolId` 在**玩家背包**里（`Inventory.ContainsId`，即手上/背包里有上一级工具）。
【已证】`Tool.actionWhenPurchased` 另有两个前置（`scratch/il-up-3.txt:4692-4721`）：
`shopId == "ClintUpgrade"` 且 `Game1.player.toolBeingUpgraded.Value == null`；
工具类型必须是 `Axe`/`Pickaxe`/`Hoe`/`WateringCan`/`Pan`，或 `GenericTool` 且
`indexOfMenuItemView.Value - 13 <= 3`（铜..铱通用工具）。

【未定】名义价 ≠ 一定等于实扣价：`ShopItemData`（`scratch/_api_up_out_u8.txt:41-96`）带
`PriceModifiers`/`PriceModifierMode`/`ApplyProfitMargins`/`IgnoreShopPriceModifiers`/`UseObjectDataPrice`
⇒ 真机验收应该用**观测到的钱差**，不要硬编码 2000/5000/10000/25000（2026-10-17 目标的「钱在作物与工具间平衡」按钱差算）。

## 5. 答案⑤：可执行路径 + 「升级真的发生了」的观测判据

【已证】购买主链的 IL（`scratch/il-up-2.txt:312-845`，`ShopMenu.tryToPurchaseItem`）：

1. `IL_00D1-0110`：`!item.CanBuyItem(player) && !item.IsInfiniteStock() && !item.IsRecipe()`
   ⇒ 放一声 `smallSelect`、返回 false（买不了）。
2. `IL_0131-013D`：`chargePlayer(player, currency, 金额)` ⇒ **扣钱**。
3. `IL_0142-014D`：`if (!string.IsNullOrEmpty(tradeItemId)) ConsumeTradeItem(tradeItemId, tradeItemAmount)` ⇒ **扣 5 条金属锭**。
4. `IL_0152-0161`：`if (!readOnly) { if (item.actionWhenPurchased(ShopId)) { … } }` ⇒ 升级动作。
5. `Tool.actionWhenPurchased("ClintUpgrade")`（`scratch/il-up-3.txt:4696-4776`）：
   - 若 `RequireToolId != null`：`player.Items.GetById(id).FirstOrDefault()` 取到旧工具 ⇒
     `player.removeItemFromInventory(旧工具)` + `this.UpgradeFrom(旧工具)`；
   - `player.toolBeingUpgraded.Value = this.getOne() as Tool`；
   - `player.daysLeftForToolUpgrade.Value = 2`；
   - `playSound("parry")` + `exitActiveMenu()` + Clint 说 `Strings\StringsFromCSFiles:Tool.cs.14317`；返回 true。

**【重要陷阱·已证（顺序）】** 第 2/3 步在 `actionWhenPurchased` **之前**；
而 `actionWhenPurchased` 在「已有工具在升级」时直接落到基类（`IL_017D` 起）并返回 false
（`scratch/il-up-3.txt:4697-4700`、`4811-4814`），方法尾部只按 `Stock` 决定返回值
（`IL_05C2`：`Stock > 0 ⇒ return false`，`Stock <= 0 ⇒ return true`，`scratch/il-up-2.txt:829-844`）。
⇒ **钱和材料照扣、工具不会升级**。所以我们的 Mod 必须在调用前自己判
`Game1.player.toolBeingUpgraded.Value == null`（并把 `daysLeftForToolUpgrade` 也纳入状态机）。

**【推荐路径（可执行）】**
1. `if (Game1.player.toolBeingUpgraded.Value != null) → 不买`；
2. `Utility.TryOpenShopMenu("ClintUpgrade", "Clint", true)`（public static；false = `Data/Shops` 没这个 id）；
3. `var shop = Game1.activeClickableMenu as ShopMenu;` 在 **public** `shop.itemPriceAndStock` 里挑出
   目标工具那一项（`ISalable`），读它的 `ItemStockInformation.Price`/`TradeItemId`/`TradeItemAmount` 作**预期值**；
4. 反射调 `tryToPurchaseItem(item, null, 1, 0, 0)`（先例 `mod/AgentFarm.Bridge/BuySkill.cs:292-317`）；
5. 先 `exitActiveMenu()`/关店（`actionWhenPurchased` 自己已调了 `exitActiveMenu()`）并归还光标物品。

**【观测判据（不许看回执；与项目「观测差分」纪律一致）】**
- **当次**：`Game1.player.Money` 下降量 == 商店里那一项的 `Price`（把 PriceModifiers 的偏差当容忍带）；
  `GetPlayerInventory` 里对应金属锭数量 -5；`toolBeingUpgraded.Value != null` 且
  其 `GetType()`/名称 == 目标工具；`daysLeftForToolUpgrade.Value == 2`。
- **次日**：`daysLeftForToolUpgrade.Value` 比昨天少 1（`Farmer.dayupdate`）。
- **取回**：`daysLeft <= 0` 时走 `Blacksmith_Upgrade` 分支（或直接跟 Clint 对话）
  ⇒ `toolBeingUpgraded.Value == null` 且背包里出现同一工具、`UpgradeLevel` == 旧值 + 1。
- 反向证据（也算观测）：钱没动 / 金属锭没少 / `daysLeft` 没变 ⇒ **没升级**，无论回执说什么。

## 6. 答案⑥：观测缺口（建议的 ToolsView 字段，本卡不改代码）

【已证】现状：`mod/AgentFarm.Bridge/Contracts.cs:209` 的 `ToolsView` 只有
「手上工具 id/名称/是工具」这类字段；唯一等级字段 `upgradeLevel` 只对**洒水壶**写
（`mod/AgentFarm.Bridge/Contracts.cs:323-324`，`WorldSnapshot.cs:704` 的 `can.UpgradeLevel`）。
⇒ 升级链**完全不可观测**。建议（命名供 task-141/142 参考）：

```
tools[]            : [{ id, name, kind("axe"/"pickaxe"/"hoe"/"can"/"pan"/other), upgradeLevel,
                        indexOfMenuItemView, isEquipped, stack }]
toolBeingUpgraded  : { id, name, kind, upgradeLevel } | null      // Farmer.toolBeingUpgraded.Value
toolUpgradeDaysLeft: int                                          // Farmer.daysLeftForToolUpgrade.Value
toolUpgradeNotice  : bool                                         // hasReceivedToolUpgradeMessageYet
shop               : { shopId, isOpen, currency, stockCount } | null   // ShopMenu.ShopId/readOnly/currency
shopUpgradeOffer   : { itemId, price, tradeItemId, tradeItemAmount } | null  // 从 itemPriceAndStock 取的那一项
money              : int                                          // 已有
```
其中 `kind` 必须**按工具真实类型**写（`Axe`/`Pickaxe`/`Hoe`/`WateringCan`/`Pan`），
不要像现在这样只写 `isTool`；`upgradeLevel` 对**四种工具**都写。

## 7. 答案⑦：障碍瓶颈（ResourceClump 分不清工具与等级）

【已证】`ResourceClump.performToolAction(Tool t, Int32 damage, Vector2 tileLocation)`
（`scratch/il-up-1.txt:138-568`）先按 `parentSheetIndex` 分派（switch 在 `IL_0054-00BD`），
每个分支的工具与**最低等级**（`t.upgradeLevel` 是 `Tool` 上的 `NetInt` 字段，IL_0025 起）：

| `parentSheetIndex` | 要求的工具 | 最低 `upgradeLevel` | 不够时的文案 | 血量（同族 helper，`scratch/il-up-1.txt:85-118`） |
| --- | --- | --- | --- | --- |
| `600`（树桩形状，2×2） | `Axe` | **≥ 1**（铜斧） | `ResourceClump.cs.13945` | 10 |
| `602`（大木头/空心木形状） | `Axe` | **≥ 2**（钢斧） | `ResourceClump.cs.13948` | 20 |
| `672`（巨石形状） | `Pickaxe` | **≥ 2**（钢镐） | `ResourceClump.cs.13956` | 10 |
| `148`、`622`（另一种石堆形状） | `Pickaxe` | **≥ 3**（金镐） | `ResourceClump.cs.13952` | 20 |
| `752+`（switch 跳转表；有一支走 `IsGreenRainBush()`，`scratch/il-up-1.txt:405-430`） | `Pickaxe`（绿雨那支 `minDamage = 36`） | 该支**无等级检查**（IL_0308 起） | — | 8（跳转表某个索引） |

伤害与血量：【已证】`damage = Max(<常量A>, <常量B> × (upgradeLevel + 1))`（`scratch/il-up-1.txt:152-161`），
`health.Value -= damage`（`IL_0392-03A0`）；斧头带 `ShavingEnchantment` 时还有额外掉落分支（`IL_03A5+`）。
【未定】两个 `ldc.r4` 常量的数值（探针不打印浮点立即数）⇒ **每次挥动的具体伤害未定**。

【已证】我们 Mod 现状写错了两处：
1. `mod/AgentFarm.Bridge/WorldSnapshot.cs:484`：
   `else if (tf is ResourceClump) { t.Kind = "clump"; t.Tool = "axe"; }`
   ⇒ **所有资源堆都写成斧头**，而 148/622/672/752+ 需要**镐**（上表）。
2. `mod/AgentFarm.Bridge/FarmScan.cs:339-346`：`if (tf is ResourceClump clump) { _ = clump; _acc.Stones++; }`
   ⇒ 树桩/大木头被算进 `stones`，且注释已自认「细分留给 P2」（`FarmScan.cs:341-343`）。
   另外 `mod/AgentFarm.Bridge/UseToolSkill.cs:432` 的 `case "clump": plan.Add("axe")` 与 `:587` 同源。

【建议新增的结构字段（task-141/142 用；本卡不改代码）】
```
clumpIndex      : int        // ResourceClump.parentSheetIndex.Value（600/602/622/672/148/752…）
clumpWidth/Height : int      // ResourceClump.width/height（public NetInt，1.6 有）
clumpHealth     : float      // ResourceClump.health（public NetFloat，诊断/进度用）
clumpTarget     : { tool:"axe"|"pickaxe", minLevel:int }   // 由 clumpIndex 按上表推导
clumpKind       : string     // "stump"/"hollowLog"/"boulder"/"meteorite"/"greenRain"（名称映射见 U3）
```
`FarmScan` 的 `Stones++` 应至少按 `clumpIndex` 分流（树桩/大木头不是石头），
否则「清空农场」的进度分母会把两类障碍混在一起。

## 8. 未定项

- **U1**：`Data/Shops["ClintUpgrade"]` 的**原文条目**（用哪条 `TOOL_UPGRADES` 查询、有无 `Condition`）。
  游戏目录只有打包的 `Content/Data/Shops.xnb`，工作区没有 XNB 读取器，未解包 ⇒ 未定。
  （但 `ShopBuilder`/`ItemQueryResolver+DefaultResolvers.TOOL_UPGRADES → GetToolUpgradeData` 的调用关系已证：
  `scratch/il-up-2.txt:234-240`。）
- **U2**：§7 的两个 `ldc.r4` 常量（探针不打印浮点立即数）⇒ 单次伤害数值未定。
- **U3**：`switch` 跳转表不打（探针限制）⇒ `752+` 的**具体索引集合**、以及
  `Blacksmith_Process`/`IL_3078` 那个 `newobj Void .ctor()` 的**声明类型**未定。
  §7 表里的「树桩/大木头/巨石/陨石」名字是按形状与音效的**推断**，索引与门槛（600/602/672/148/622）才是【已证】。
- **U4**：`ItemStockInformation.Price` 是否被 `PriceModifiers`/`ApplyProfitMargins` 改过 ⇒ 实扣价未定
  （验收用钱差，不硬编码）。
- **U5**：`GetToolUpgradeConventionalTradeItem` 是 private static ⇒ 只能自己按表映射。

## 9. 复核命令（全部只读）

```powershell
# 1) 每批 IL 转储（UTF-16LE → 用 tools/_tmp_conv.py 转 UTF-8 再读）
python scratch\_probe_il.py scratch\il-up-1.txt "StardewValley.TerrainFeatures.ResourceClump|*"
python scratch\_probe_il.py scratch\il-up-2.txt "StardewValley.GameLocation|blacksmith" "FIND|ToolUpgrade" "FIND|upgradeLevel" "StardewValley.Tools.Tool|*" "StardewValley.Menus.ShopMenu|tryToPurchaseItem"
python scratch\_probe_il.py scratch\il-up-3.txt "StardewValley.GameLocation|answerDialogueAction" "StardewValley.Utility|TryOpenShopMenu" "StardewValley.Internal.ShopBuilder|GetToolUpgradeData" "StardewValley.Internal.ShopBuilder|GetToolUpgradeConventionalPrice" "StardewValley.Tool|actionWhenPurchased" "StardewValley.Farmer|showToolUpgradeAvailability"
python scratch\_probe_il.py scratch\il-up-4.txt "StardewValley.Farmer|dayupdate" "StardewValley.Internal.ShopBuilder|GetToolUpgradeConventionalTradeItem" "StardewValley.Menus.ShopMenu|.ctor"
python tools\_tmp_conv.py scratch\il-up-3.txt scratch\il-up-3-u8.txt   # 其余同理

# 2) 可见性/类型（只反射元数据，不跑游戏）
dotnet build scratch\_api_up\ApiUp.csproj -c Release
scratch\_api_up\bin\Release\net6.0\ApiUp.exe > scratch\_api_up_out.txt
python tools\_tmp_conv.py scratch\_api_up_out.txt scratch\_api_up_out_u8.txt
```

> 姊妹篇：`docs/_il-newday-save.md`（日切保存链）、`docs/_il-shipmenu-save.md`（出货日 SaveGameMenu）。
> 三篇合起来是「跨日 + 落盘 + 升级」三条链的 IL 底稿。
