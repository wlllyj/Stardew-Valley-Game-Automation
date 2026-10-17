# 铁匠铺工具升级链：IL + 反射定案（task-204）

> **只读取证**（Lead m08838 的 task-204；用户目标是「赶紧做工具升级，农场快成森林了」）。
> 目的：给 **task-205（实现）** 一份可以照抄的链路底稿。所有结论标【已证】/【未定】/【推断】。
> 证据 = `tools/il-probe`（`Probe26.exe`）转储 + 只读反射探针 `scratch/_api_up/`（反射元数据，**不跑游戏**）。
> 原始产物（本次全部落 `scratch/`）：
> - `scratch/t204-il-up-1.txt`（`ResourceClump.*`，UTF-16LE）、`scratch/t204-il-up-1-u8.txt`（UTF-8）
> - `scratch/t204-il-up-2.txt`（`GameLocation.blacksmith` + `ShopMenu.tryToPurchaseItem` + `FIND|*`）
> - `scratch/t204-il-up-3.txt`（`GameLocation.answerDialogueAction` + `Utility.TryOpenShopMenu` + `ShopBuilder.GetToolUpgrade*` + `Tool.actionWhenPurchased` + `Farmer.showToolUpgradeAvailability`）
> - `scratch/t204-il-up-4.txt`（`Farmer.dayupdate` + `GetToolUpgradeConventionalTradeItem` + `ShopMenu..ctor`）
> - `scratch/t204-api-out.txt` / `scratch/t204-api-out_u8.txt`（可见性/签名反射 dump）
> - 工具：`scratch/_t204_grep.py`（按正则 grep 转储，`-n` 带上下文）、`scratch/_t204_conv.py`（UTF-16LE 无 BOM → UTF-8；**`tools/_tmp_conv.py` 对无 BOM 转储会报错**）
> **引法**：本文优先引 **IL 偏移**（跨转储稳定）；行号以当前 `_u8.txt` 为准，可用 §7 命令复现。

## 0. 结论速览

【已证】整条链是：

```
玩家进 Blacksmith 店 → GameLocation.blacksmith(tile) 挂出对话（应答键 "Blacksmith"）
  └ 选 Upgrade → answerDialogueAction("Blacksmith_Upgrade")
        ├ daysLeftForToolUpgrade > 0 → Clint 说 "Clint_StillWorking"，**不开店**
        └ 否则 → Utility.TryOpenShopMenu("ClintUpgrade", "Clint", true)   // 升级专用商店
              └ 在商店里买下工具条目 → ShopMenu.tryToPurchaseItem（private）
                    ├ 钱不够 / 材料不够 ⇒ cancel 分支（**什么都不扣**）
                    ├ chargePlayer（扣金币）→ ConsumeTradeItem（扣 5 条锭）
                    └ item.actionWhenPurchased("ClintUpgrade")
                          ├ player.toolBeingUpgraded.Value != null ⇒ 走基类返回 false（**钱已扣！**）
                          └ 否则：旧工具 removeItemFromInventory + UpgradeFrom(旧)
                                   toolBeingUpgraded.Value = this.getOne()
                                   daysLeftForToolUpgrade.Value = 2
每天 Farmer.dayupdate：daysLeft>0 ⇒ daysLeft--
取回：再进 Blacksmith 店 → blacksmith(tile) 开头（先于对话）的 pickup 分支
      ⇒ toolBeingUpgraded.Value = null + 工具进背包（等级已在买下时 +1）
```

**对 task-205 最有用的四条**：

1. **入口全部是 public API**：`GameLocation.blacksmith(Location)`、`GameLocation.performAction(String[], Farmer, Location)`、
   `GameLocation.answerDialogueAction(String, String[])`、`Utility.TryOpenShopMenu(String, String, Boolean)`、
   `ShopBuilder.GetShopStock(String)` 都是 **public**（`scratch/t204-api-out_u8.txt:258-265`、`:17-19`、`:277-279`）。
   唯一需要反射的是 **`ShopMenu.tryToPurchaseItem`（private）**（`:30`，先例 `mod/AgentFarm.Bridge/BuySkill.cs:280-305`）。
2. **`ShopBuilder.GetShopStock("ClintUpgrade")`（public static）可以“试算/预演”库存**：不开店就能拿到
   `Dictionary<ISalable, ItemStockInformation>`，读到 `Price` / `TradeItem` / `TradeItemCount`（`scratch/t204-api-out_u8.txt:277-279`、`:295-320`）。
   ⇒ 脑侧「升级要多少钱/够不够锭」可以**先问再买**，不用盲买。
3. **`answerDialogueAction("Blacksmith_Upgrade")` 自带 daysLeft 守卫**（仍工作时只说话不开店），
   而 `TryOpenShopMenu("ClintUpgrade")` **绕过**这个守卫 ⇒ 若已有工具在升级，用 `TryOpenShopMenu` 买 = **白扣钱不升级**。
   **推荐：先读状态决定，再开 `ClintUpgrade` 店买**（比走对话更可控）。
4. **工具被拿走期间，`player.Items` 里没有该工具**（`Tool.actionWhenPurchased` 里 `removeItemFromInventory(旧工具)`，
   `scratch/t204-il-up-3-u8.txt` 的 `actionWhenPurchased` IL_0094-009A）。脑侧 `toolOk` 不能只看背包；
   升级期间必须看 `Farmer.toolBeingUpgraded`。

## 1. ①入口链

### 1.1 对话选项从哪来：`GameLocation.blacksmith(Location tileLocation)`

【已证】`scratch/t204-il-up-2-u8.txt` 的 `GameLocation.blacksmith(Location tileLocation)` 全文 IL_0000-02DC：

1. `foreach (NPC npc in this.characters)`（IL_0000-000B）找 `npc.Name == "Clint"`（IL_001F-0024；不匹配继续循环 IL_0029）。
   ⇒ **`this` 这个地点的 `characters` 里必须有 Clint**，否则方法走完循环 `return false`（IL_02D8，静默）。
2. `npc.faceDirection(2)`（IL_0074）。⚠️ 参数 `tileLocation` **只被拿去比较 Clint 的朝向**（IL_002E-0073，比较结果还 `pop` 掉了），
   逻辑上**不影响任何分支** ⇒ 传 `default` 也行（【已证】IL 层面）。
3. **pickup 分支（先于对话）**：见 §1.3。
4. **否则挂对话**：扫背包 `IsGeode`（IL_018D-01D5）⇒ 有晶球 4 个选项、没有 3 个（IL_01D2-02A5）：

| 选项键（`Response.responseKey`） | 文案 key | 应答键（= `Blacksmith` + `_` + 选项键） |
| --- | --- | --- |
| `Shop` | `Strings\Locations:Blacksmith_Clint_Shop` | `Blacksmith_Shop` |
| `Upgrade` | `Strings\Locations:Blacksmith_Clint_Upgrade` | `Blacksmith_Upgrade` |
| `Process`（仅身上有晶球） | `Strings\Locations:Blacksmith_Clint_Geodes` | `Blacksmith_Process` |
| `Leave` | `Strings\Locations:Blacksmith_Clint_Leave` | `Blacksmith_Leave` |

5. `this.createQuestionDialogue("", responses, "Blacksmith")`（IL_02A6-02B2）——第三参 `dialogKey="Blacksmith"`
   就是「应答键前缀」的来源。方法返回 `true`（IL_02B7-02DC）。

【已证】地图侧的触发：`GameLocation.performAction(String[] action, Farmer who, Location tileLocation) → blacksmith(...)`
（`tools/il-probe` 的 `FIND|Blacksmith` 命中；这也是游戏里 Action 属性 `Blacksmith` 的执行路径）。
⇒ **Mod 不需要伪造对话**：直接调 `Game1.currentLocation.blacksmith(default)` 就能拿到同样的分支（pickup 或挂对话）。

### 1.2 `answerDialogueAction` 的两个分支

【已证】字符串常量与分派点（`scratch/t204-il-up-3-u8.txt`）：
- `ldstr "Blacksmith_Upgrade"` → `op_Equality` → `brtrue`（IL_07FC-0801 一带；分派方法 = `GameLocation.answerDialogueAction(String, String[])`）。
- `ldstr "Blacksmith_Shop"` → 同型分派（IL_08C9 一带）。
- 另有 `"telephone_Blacksmith_UpgradeCost"`（IL_0B10）——电话查价，见 §1.4。

**`Blacksmith_Shop` 分支**（IL_2FF8-3008）：`Utility.TryOpenShopMenu("Blacksmith", "Clint", true)`（普通商店）。

**`Blacksmith_Upgrade` 分支**（IL_300E-3073）：
```
if (Game1.player.daysLeftForToolUpgrade.Value > 0) {           // IL_300E-301E
    NPC clint = this.getCharacterFromName("Clint");            // IL_3020-302B
    if (clint != null)                                         // IL_302D-302F
        clint.DrawDialogue("Data\ExtraDialogue:Clint_StillWorking",
                           player.toolBeingUpgraded.Value.DisplayName);   // IL_3036-3058
    return;                                                    // IL_305D → IL_3976（**不开店**）
}
Utility.TryOpenShopMenu("ClintUpgrade", "Clint", true);        // IL_3062-3072
```

⚠️ **两个坑（task-205 必读）**：
1. 该分支**只看 `daysLeftForToolUpgrade > 0`**，**不看** `toolBeingUpgraded.Value != null`。
   ⇒ `daysLeft == 0` 但工具还没取回时，走对话会**开升级店**，而 `actionWhenPurchased` 因 `toolBeingUpgraded != null`
   直接返回 false ⇒ **钱与 5 条锭照扣、工具不升级**（§2.2）。
2. `TryOpenShopMenu("ClintUpgrade", ...)` 本身**没有任何 daysLeft/已有升级的守卫**。

### 1.3 取回工具（回程）：`blacksmith()` 开头的 pickup 分支

【已证】`scratch/t204-il-up-2-u8.txt` IL_007A-0178（在挂对话之前）：

```
if (player.toolBeingUpgraded.Value != null && player.daysLeftForToolUpgrade.Value <= 0) {   // IL_007F-009E
    if (player.freeSpotsInInventory() <= 0 && !(toolBeingUpgraded.Value is GenericTool)) {  // IL_00A3-00C4
        clint.DrawDialogue("Data\ExtraDialogue:Clint_NoInventorySpace");                    // IL_017D-0183
        return true;                                                                        // IL_02B7
    }
    Tool t = player.toolBeingUpgraded.Value;                                                // IL_00C9-00D8
    player.toolBeingUpgraded.Value = null;                                                  // IL_00DE-00E4
    player.hasReceivedToolUpgradeMessageYet = false;                                        // IL_00E9-00EF
    player.holdUpItemThenMessage(t, true);                                                  // IL_00F4-00FB
    if (t is GenericTool) t.actionWhenClaimed(); else player.addItemToInventoryBool(t, false); // IL_0100-011C
    if (player.team.useSeparateWallets.Value && t.UpgradeLevel == 4)                        // IL_011D-013D
        Game1.multiplayer.globalChatInfoMessage("IridiumToolUpgrade", player.Name, ToolName(t.QualifiedItemId, t.UpgradeLevel)); // IL_0142-0173
    return true;
}
```

要点：
- **背包必须至少 1 空格**（`freeSpotsInInventory() > 0`），否则**拿不到工具**（只有一句 Clint_NoInventorySpace）——
  这条对 task-205/脑侧「背包腾格」是硬前置（升级完成日先腾格再去取）。
- 取回**不发钱、不发新工具**：工具在**买下时**就已经是升级后的等级（`actionWhenPurchased` 里 `getOne()` 的是“升级后的工具”）；
  取回只是把它从 `toolBeingUpgraded` 挪回背包。
- 等级**不是**在取回时 +1（task-153 版文档写“取回时等级 +1”不准确；真相是**买下时新工具已带新等级**，
  旧工具被 `UpgradeFrom` 的附魔/属性承接，见 §2.2）。

### 1.4 电话查价路径（只读店，别误用）

【已证】`answerDialogueAction` 内 `"telephone_Blacksmith_UpgradeCost"` 分支（`scratch/t204-il-up-3-u8.txt` IL_3728-3777）：
调一次 `this.answerDialogueAction("Blacksmith_Upgrade", Array.EmptyString())`，然后把得到的 `ShopMenu`
**`readOnly = true`** 并挂 `behaviorBeforeCleanup`。

⚠️ `tryToPurchaseItem` 里 `if (!readOnly) { item.actionWhenPurchased(...) }`（IL_0152）
⇒ **readOnly 店里买东西只有扣钱/扣材料，没有升级动作**（更严重的白扣坑）。
⇒ 自动化**绝不能**用电话路径开店，且买之前要断言 `shop.readOnly == false`。

## 2. ②扣钱与天数

### 2.1 `ShopMenu.tryToPurchaseItem`（private）的完整顺序

【已证】`scratch/t204-il-up-2-u8.txt`（`--- StardewValley.Menus.ShopMenu.tryToPurchaseItem(ISalable item, ISalable held_item, Int32 stockToBuy, Int32 x, Int32 y) ---`，共 845 行）：

| 顺序 | IL | 事实 |
| --- | --- | --- |
| 1 | IL_008E-0091 | `price = stockInfo.Price * stockToBuy` |
| 2 | IL_0092-00A3 | `if (getPlayerCurrencyAmount(player, currency) < price) goto IL_037B`（**钱不够**） |
| 3 | IL_00A8-00B3 | `if (stockInfo.TradeItem != null && !HasTradeItem(TradeItem, TradeItemCount)) goto IL_037B`（**材料不够**） |
| 4 | IL_00B8-00CC | `heldItem = item.GetSalableInstance(); heldItem.Stack = stockToBuy`（先放光标） |
| 5 | IL_00D1-0102 | `if (!heldItem.CanBuyItem(player) && !item.IsInfiniteStock() && !item.IsRecipe()) → smallSelect…`（`CanBuyItem` 这里才被调，钱/材料已过） |
| 6 | IL_0111 起 | `chargePlayer(player, currency, -price)`（**真正扣钱**） |
| 7 | IL_0142-014D | `if (!string.IsNullOrEmpty(TradeItem)) ConsumeTradeItem(TradeItem, TradeItemCount)`（**扣 5 条锭**） |
| 8 | IL_0152-0161 | `if (!readOnly) { if (item.actionWhenPurchased(ShopId)) …; }`（**升级动作**） |
| 9 | IL_037B-03A3 | **cancel 分支**：`if (price > 0) Game1.dayTimeMoneyBox.moneyShakeTimer = 1000`；`playSound("cancel")`；`goto IL_05C2`（**不扣钱、不扣材料、不升级**） |
| 10 | IL_05C2-05E2 | 尾部：`if (stockInfo.Stock > 0) return false; else { buyBackItems.Remove(item); hoveredItem = null; return true; }` |

【已证】`ItemStockInformation` 的成员（反射 `scratch/t204-api-out_u8.txt`）：
- **类型全名是 `StardewValley.ItemStockInformation`（不是 `StardewValley.Menus.*`）**，公开字段含
  `Price`(Int32)、`Stock`(Int32)、**`TradeItem`(String)**、**`TradeItemCount`(Nullable<Int32>)**、
  `ItemToSyncStack`(ISalable)、`LimitedStockMode`、`StackDrawType`(Nullable)、`ActionsOnPurchase`(List)；
  构造签名 `(Int32 price, Int32 stock, String tradeItem, Nullable<Int32> tradeItemCount, LimitedStockMode stockMode,
  String syncedKey, ISalable itemToSyncStack, Nullable<?> stackDrawType, List<?> actionsOnPurchase)`。
- ⚠️ **字段名是 `TradeItem` / `TradeItemCount`，不是 `TradeItemId`**（task-153 版文档写错了，此处以 IL+反射为准）。

### 2.2 `Tool.actionWhenPurchased(String shopId)` 的完整逻辑

【已证】`scratch/t204-il-up-3-u8.txt` 的 `Tool.actionWhenPurchased(String shopId)`（IL_0000-017C + GenericTool 支路）：

```
if (shopId != "ClintUpgrade") goto exit_false;                 // IL_0000-000B；其它商店走基类
if (Game1.player.toolBeingUpgraded.Value != null) goto exit_false; // IL_0010-001F  ⇒ **只返回 false，不回滚钱**
if (!(this is Axe || Pickaxe || Hoe || WateringCan || Pan)) {   // IL_0026-0059
    if (this is GenericTool) goto generic_tool_path;            // IL_004E-0054
    goto exit_false;
}
ToolUpgradeData d = ShopBuilder.GetToolUpgradeData(this.GetToolData(), player); // IL_005E-0069
string req = d?.RequireToolId;                                  // IL_006E-007A
if (req != null) {                                              // IL_007B-007C
    Item old = player.Items.GetById(req).FirstOrDefault();       // IL_007E-0093
    player.removeItemFromInventory(old);                         // IL_0094-009A  ⇒ **旧工具离开背包**
    if (old is Tool t) this.UpgradeFrom(t);                      // IL_009F-00AB  ⇒ 承接附魔/属性
}
player.toolBeingUpgraded.Value = (Tool)this.getOne();            // IL_00B0-00C5
player.daysLeftForToolUpgrade.Value = 2;                         // IL_00CA-00D5
playSound("parry"); exitActiveMenu();                            // IL_00DA-00EF
Clint.DrawDialogue("Strings\StringsFromCSFiles:Tool.cs.14317");  // IL_00F4-0105
return true;                                                     // IL_010A-010B
generic_tool_path: indexOfMenuItemView.Value - 13 <= 3 ? (同上置位) : goto exit_false; // IL_010C-017C
exit_false: … 返回 false  // IL_017D
```

⚠️ **陷阱复述（§5 有兜底方案）**：第 2 步的门只看 `toolBeingUpgraded`，而扣钱/扣材料在**调用方**（`tryToPurchaseItem`）
第 6/7 步就已经执行 ⇒ **“已有工具在升级”时买 = 钱和 5 条锭白丢**。

### 2.3 价格与材料表

【已证】`ShopBuilder.GetToolUpgradeConventionalPrice(Int32 level)`（`scratch/t204-il-up-3-u8.txt`，IL_0018-0037）：
`switch (level)` = `2000 / 5000 / 10000 / 25000`（`ldc.i4 2000`、`5000`、`10000`、`25000`），default `2000`。

| `Tool.UpgradeLevel`（当前） | 目标 | 价格 | `TradeItem`（锭 id） | `TradeItemCount` |
| --- | --- | --- | --- | --- |
| 0（基础） | 1 铜 | **2000** | `(O)334` 铜锭 | 5 |
| 1（铜） | 2 钢 | **5000** | `(O)335` 铁锭 | 5 |
| 2（钢） | 3 金 | **10000** | `(O)336` 金锭 | 5 |
| 3（金） | 4 铱 | **25000** | `(O)337` 铱锭 | 5 |
| 其它 | — | 2000 | `(O)334` | 5 |

- 价格表在**代码常量**（`GetToolUpgradeConventionalPrice`），锭表在 **`GetToolUpgradeConventionalTradeItem`（private static）**；
  `TradeItemCount = 5` 硬编码（`ldc.i4.5`）。
- 商店条目是**数据驱动**的：`Utility.TryOpenShopMenu` 从 `DataLoader.Shops` 取 `Data/Shops` 的 `ClintUpgrade` 条目
  （`scratch/t204-il-up-3-u8.txt` 的 `TryOpenShopMenu` IL_0000-0060 一带：`TryGetValue` 失败即 `return false`），
  条目里的 `ToolUpgradeData{ Condition, Price, RequireToolId, TradeItemId, TradeItemAmount }`
  （`scratch/t204-api-out_u8.txt` 的 `ToolUpgradeData` 段）由 `ItemQueryResolver+DefaultResolvers.TOOL_UPGRADES` 现算。
- ⚠️ **实扣价可能被 `ShopItemData.PriceModifiers/ApplyProfitMargins` 改**（`scratch/t204-api-out_u8.txt` 的 `ShopItemData` 段）
  ⇒ **验收一律用“钱差”与“锭差”，不要硬编码 2000/5000/…**；预期值从 `ItemStockInformation.Price` 读。

### 2.4 天数推进与提示

【已证】`Farmer.dayupdate(Int32 timeWentToSleep)`（`scratch/t204-il-up-4-u8.txt` IL_0054-0069）：
`if (daysLeftForToolUpgrade.Value > 0) daysLeftForToolUpgrade.Value--;`
（`Farmer.dayupdate → FarmHouse.setMapForUpgradeLevel` 也在同方法里，那是**房子**升级，别混。）

【已证】`Farmer.showToolUpgradeAvailability()`（`scratch/t204-il-up-3-u8.txt` 全文）：
`toolBeingUpgraded != null && daysLeft <= 0 && toolBeingUpgraded.Value != null && !isFestivalDay && … &&
 !hasReceivedToolUpgradeMessageYet` ⇒ 压 `morningQueue` 或 `showGlobalMessage("Strings\StringsFromCSFiles:ToolReady", 工具名)`。
调用者：`Game1+<_newDayAfterFade>d__784.MoveNext` 与 `SaveGame+<getLoadEnumerator>d__101.MoveNext`（`scratch/t204-il-up-2-u8.txt` 的 `FIND|ToolUpgrade` 表）。

## 3. ③推荐的可自动化路径（可照抄）

### 3.0 前置条件（务必先满足）

1. **玩家在 Blacksmith 店内**（Town 的铁匠铺）。原因：`blacksmith()` 只认**当前地点 `characters` 里的 Clint**
   （IL_001F-0029）；`TryOpenShopMenu(...,"Clint",...)` 的 owner 解析也按名字找 NPC。
   ⇒ 脑侧要先 `move_to` 到 Blacksmith 店里的柜台前（可复用 `farmwork.ensure_location("Blacksmith")` 一类）。
2. 目标工具**在背包里**（`RequireToolId` 要在 `player.Items` 里，否则 `GetToolUpgradeData` 匹配不到 ⇒ 没有该条目）。
3. **至少 1 个背包空格**（取回时需要；买下时不需要空格，因为旧工具被移走后位置空出来）。
4. **没有任何工具在升级**（`Game1.player.toolBeingUpgraded.Value == null`）。
5. 钱 ≥ 你读到的 `ItemStockInformation.Price`（+ 5 条锭齐）。

### 3.1 技能伪码（Mod 侧，新增 `upgrade_tool` skill）

```csharp
// 入参：tool（"axe"|"pickaxe"|"hoe"|"can"），可选 expectedLevel
// 返回码见 §3.4；**所有判据都在观测上，不只看回执**
var p = Game1.player;
if (p.toolBeingUpgraded.Value != null) return Fail("already_upgrading", /* tool, daysLeft */);
if (p.daysLeftForToolUpgrade.Value > 0) return Fail("still_working", daysLeft);
if (p.freeSpotsInInventory() <= 0)      return Fail("inventory_full");

// 1) 预演库存（不开店；public static）
var stock = ShopBuilder.GetShopStock("ClintUpgrade");       // Dictionary<ISalable, ItemStockInformation>
// 2) 选目标条目：key is Tool t && t 的类型族匹配 && t.UpgradeLevel == (当前等级 + 1)
//    （首次真机要打印所有条目做钉死，见 §3.6）
// 3) 读预期值
int price = info.Price; string trade = info.TradeItem; int tradeN = info.TradeItemCount ?? 0;
if (p.Money < price)                    return Fail("cannot_afford", price, p.Money);
if (trade != null && !HasTradeItem(trade, tradeN)) return Fail("missing_trade_item", trade, tradeN);

// 4) 开店
if (!Utility.TryOpenShopMenu("ClintUpgrade", "Clint", true)) return Fail("shop_unavailable");
var shop = Game1.activeClickableMenu as ShopMenu;
if (shop == null) return Fail("shop_not_opened");
if (shop.readOnly) { Utility.exitActiveMenu? }              // readOnly 店绝不能买（电话路径）
// 5) 用反射调 private tryToPurchaseItem(item, null, 1, 0, 0)（先例 BuySkill.cs:280-305）
// 6) 关店（actionWhenPurchased 自己已调 exitActiveMenu；这里兜底再关，避免残留菜单）
// 7) 观测差分（§3.3）→ Ok / Fail("purchase_no_effect")
```

### 3.2 五步逐条（每步：调什么 / 读什么 / 期望）

| 步 | 动作 | 读/调 | 期望（成功） |
| --- | --- | --- | --- |
| 1 | 预检 | `Game1.player.toolBeingUpgraded.Value`、`daysLeftForToolUpgrade.Value`、`freeSpotsInInventory()` | `== null`、`== 0`（或 `<=0`）、`> 0` |
| 2 | 预演库存 | `ShopBuilder.GetShopStock("ClintUpgrade")`（public static） | 找到 `key is Tool` 且 `UpgradeLevel == 当前+1` 的条目；读 `ItemStockInformation.Price/TradeItem/TradeItemCount` |
| 3 | 开店 | `Utility.TryOpenShopMenu("ClintUpgrade", "Clint", true)` | 返回 `true`；`Game1.activeClickableMenu is ShopMenu` 且 `readOnly == false` |
| 4 | 购买 | 反射 `ShopMenu.tryToPurchaseItem(item, null, 1, 0, 0)` | 扣钱/扣锭/升级动作都发生了（见步 5） |
| 5 | 观测差分 | `player.Money`、对应锭数量、`toolBeingUpgraded.Value`、`daysLeftForToolUpgrade.Value`、`player.Items` 里旧工具 | 钱差 == `Price`；锭 −`TradeItemCount`；`toolBeingUpgraded != null` 且类型 == 目标；`daysLeft == 2`；**旧工具不在背包** |

### 3.3 判据（“升级真的发生了”＝观测差分，不许看回执）

- **当次**：`moneyBefore - moneyAfter == info.Price`（容忍 `PriceModifiers` 偏差：读的是同一 `ItemStockInformation.Price`，偏差应≈0）；
  对应锭 `−TradeItemCount`；`toolBeingUpgraded.Value != null` 且 `GetType()` 与目标工具族一致；
  `daysLeftForToolUpgrade.Value == 2`；`player.Items` 里**找不到**旧等级的该工具（`GetById(旧id)` 为空）。
- **次日**：`daysLeftForToolUpgrade.Value` 比昨天 −1（`Farmer.dayupdate`）。
- **取回日**：`daysLeft <= 0` 时再调 `Game1.currentLocation.blacksmith(default)`（或走进店触发柜台）⇒
  `toolBeingUpgraded.Value == null` 且背包出现该工具、`UpgradeLevel == 旧+1`（新工具在买下时已是新等级）。
- **反向证据**（任一成立 ⇒ 没升级，无论回执）：钱没动 / 锭没少 / `toolBeingUpgraded` 仍 null / 旧工具还在背包。

### 3.4 失败兜底（如实返回，全部不进“成功”）

| 返回码 | 触发条件（观测/IL 事实） | 处置 |
| --- | --- | --- |
| `already_upgrading` | `toolBeingUpgraded.Value != null`（§2.2 的坑，钱会白扣） | 不做；等取回 |
| `still_working` | `daysLeftForToolUpgrade.Value > 0`（§1.2 StillWorking 对话） | 不做；报剩余天数 |
| `inventory_full` | `freeSpotsInInventory() <= 0`（取回时会被 Clint_NoInventorySpace 挡，§1.3） | 先腾格（复用 task-198 腾格回路） |
| `cannot_afford` | `price > player.Money`（`tryToPurchaseItem` 会走 cancel 分支，不扣钱但白跑） | 报差额，攒钱 |
| `missing_trade_item` | `info.TradeItem != null && !HasTradeItem(...)`（同上 cancel 分支） | 报缺几块锭 |
| `no_offer` | `GetShopStock("ClintUpgrade")` 里没有 `UpgradeLevel == 当前+1` 的条目（已铱级/工具不对） | 不做 |
| `shop_unavailable` | `TryOpenShopMenu` 返回 false（`Data/Shops` 没有该 id，§2.3） | 不做，报环境问题 |
| `shop_readonly` | `shop.readOnly == true`（电话路径开店，§1.4） | 关店，不做 |
| `purchase_no_effect` | 观测差分不成立（钱/锭/`toolBeingUpgraded` 都没按预期变） | 如实失败 + 现场快照 |

### 3.5 取回工具

- 路径：`Game1.currentLocation.blacksmith(new xTile.Dimensions.Location(0, 0))`（public；参数不影响逻辑，§1.1）
  —— **必须在 Blacksmith 店内**（`currentLocation.characters` 要有 Clint），否则静默 `return false`。
- 期望：`toolBeingUpgraded.Value == null`、背包出现该工具、`UpgradeLevel` 已是新等级、`hasReceivedToolUpgradeMessageYet == false`。
- ⚠️ 前提：`daysLeftForToolUpgrade.Value <= 0` **且** 背包有空格（§1.3）。

### 3.6 首次真机调试（把“选条目”钉死，10 分钟）

task-205 第一次跑时**不要直接买**，先只读打印：

```csharp
var stock = ShopBuilder.GetShopStock("ClintUpgrade");
foreach (var kv in stock) {
    var s = kv.Key; var info = kv.Value;
    // 打印：s.GetType().FullName / s.Name / s.QualifiedItemId / (s is Tool t ? t.UpgradeLevel : -1)
    //       info.Price / info.TradeItem / info.TradeItemCount / info.Stock / info.LimitedStockMode
}
```

把一张表贴进 task-205 的日志，按 `(Type 族, UpgradeLevel == 当前+1)` 选中；若条目上拿不到等级信息
（【未定】见 U3），改用 `RequireToolId` 反查：对目标工具调 `ShopBuilder.GetToolUpgradeData(tool.GetToolData(), player)`
（public static）拿 `RequireToolId/Price/TradeItemId`，再在 stock 里按价格+材料匹配。

## 4. ④风险与不可逆点

| 风险 | 事实/证据 | 缓解 |
| --- | --- | --- |
| **2 天不能用该工具** | `daysLeft = 2`（§2.2 IL_00CA-00D5），每天 −1（§2.4） | 脑侧：升级期间把依赖该工具的活（砍树/清障/耕地/浇水）降级；别在急着清农场时升斧/镐到一半 |
| **钱 + 5 锭先扣、升级可能不发生** | §2.1 步 6/7 早于 §2.2 的 `toolBeingUpgraded` 门 | 预检 `toolBeingUpgraded == null`（§3.1/§3.4） |
| **readOnly 店买东西 = 只扣钱不升级** | §1.4 + IL_0152 的 `if (!readOnly)` | 断言 `shop.readOnly == false` |
| **旧工具离开背包** | `removeItemFromInventory`（§2.2 IL_0094-009A） | 脑侧 `toolOk` 改用 `toolBeingUpgraded` 判「工具在哪」；背包里没有≠丢了 |
| **取回需要背包空格** | §1.3 `freeSpotsInInventory() <= 0` 分支 | 取回前先腾格 |
| 存档回滚 | 状态在 `NetRef<Tool>`/`NetInt`（`Farmer` 字段），随存档持久化；**不落盘则回滚**（`docs/_il-newday-save.md` 的 SMAPI 五连行判据） | 【推断】回滚安全 = 退出不保存；若已落盘，只能读旧存档 —— 真机验证前不要赌 |
| 节日/天气 | `showToolUpgradeAvailability` 的 `isFestivalDay` 等条件只影响**提示**（§2.4），不影响升级本身 | 无 |
| `useSeparateWallets` | 只在取回且铱级时多发一条全局聊天消息（§1.3） | 无 |

## 5. ⑤给 task-205 的实现清单

**5.1 Mod 观测（`Contracts.cs`/`WorldSnapshot.cs`，归 task-203/205 的写者）**

```csharp
tools[]            : [{ id, name, kind("axe"|"pickaxe"|"hoe"|"can"|"pan"|other), upgradeLevel, isEquipped }]
                     // 现状只有 watering can 写 upgradeLevel（Contracts.cs:323-324），要扩到四种工具
toolBeingUpgraded  : { id, name, kind, upgradeLevel } | null   // Farmer.toolBeingUpgraded.Value
toolUpgradeDaysLeft: int                                       // Farmer.daysLeftForToolUpgrade.Value
toolUpgradeNotice  : bool                                      // hasReceivedToolUpgradeMessageYet
freeSlots          : int                                       // Farmer.freeSpotsInInventory()
shop               : { shopId, isOpen, readOnly, currency } | null   // ShopMenu.ShopId/readOnly/currency
shopOffers[]       : [{ itemId, name, kind, upgradeLevel, price, tradeItem, tradeItemCount, stock }]
                     // 由 ShopBuilder.GetShopStock(shopId) 读（**注意：tools 条目是 Tool 实例**）
```

**5.2 技能**：`upgrade_tool`（§3.1）、`claim_tool_upgrade`（§3.5，可并入 `interact`/`blacksmith` 专用 skill）、
`shop_peek`（只读 `GetShopStock`，给脑侧做预算，可选）。

**5.3 脑侧判据/政策**

- 触发：目标 1（清农场）里工具等级不足时（例：`clumpIndex ∈ {672,148,622}` 需要镐 ≥2/≥3，
  见 `docs/_tool-matrix.md` 与旧版本文档 §7），且 `money ≥ price + 安全垫`、锭够、未来 2 天没有必须用该工具的活。
- 预算：优先升级**镐**（清石/矿）与**斧**（清树/桩），锄/壶视 crop 面积。
- 失败即停：`already_upgrading`/`still_working`/`purchase_no_effect` 一律不重试当次；
  `cannot_afford`/`missing_trade_item` 记“差多少”后当天下次再说。
- 验收：只用 §3.3 的观测差分；`toolBeingUpgraded` 出现 + 钱/锭变化 + 次日 `daysLeft` −1 + 取回后 `UpgradeLevel` +1。

## 6. 未定项

- **U1**：`Data/Shops["ClintUpgrade"]` 的**条目原文**（哪条 `TOOL_UPGRADES` 查询、有无 `Condition`）。
  游戏目录只有打包 `Content/Data/Shops.xnb`，工作区无 XNB 读取器 ⇒ 未定（但 `TryOpenShopMenu` 的 `TryGetValue` 失败会返回 false，
  ⇒ task-205 用 `TryOpenShopMenu` 的返回值即可判“店存不存在”）。
- **U2**：`ClintUpgrade` 条目的 `ISalable` 是**哪种 `Tool` 实例、`UpgradeLevel` 字段填的是目标等级还是当前等级**
  （`ItemQueryResolver.ApplyItemFields` 会写 `ISpawnItemData.ToolUpgradeLevel`，但具体值语义未逐条核）⇒ §3.6 的真机打印钉死。
- **U3**：`ResourceClump` 的 `parentSheetIndex → 形状名`（树桩/大木头/巨石/陨石）与 `ldc.r4` 两个伤害常量未定
  （switch 跳转表与浮点立即数探针都打不出；阈值 600/602/672/148,622/752+ 是【已证】）。
- **U4**：`GetToolUpgradeConventionalTradeItem` 是 private static ⇒ 只能按 §2.3 表自映射，或读商店条目的 `TradeItem`。
- **U5**：`PriceModifiers/ApplyProfitMargins` 对 `ClintUpgrade` 的实际影响 ⇒ 用钱差验收，别硬编码。
- **U6**：`blacksmith()` 在“玩家不在此地点”时直接调 `Game1.getLocationFromName("Blacksmith").blacksmith(default)`
  能否安全完成取回（会 `holdUpItemThenMessage` 但玩家不在场）——【推断】可行但**未真机验证**，task-205 先走“人在店里”的正路。

## 7. 复核命令（全部只读，不启动游戏）

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"

# 1) 反射可见性/签名（离线；输出 UTF-16LE 再转 UTF-8）
dotnet build scratch\_api_up\ApiUp.csproj -c Release
scratch\_api_up\bin\Release\net6.0\ApiUp.exe > scratch\t204-api-out.txt
& $py scratch\_t204_conv.py scratch\t204-api-out.txt scratch\t204-api-out_u8.txt

# 2) IL 转储重做（Probe26 输出 UTF-16LE；用 scratch\_t204_conv.py 转 UTF-8）
& $py scratch\_probe_il.py scratch\il-up-2.txt "StardewValley.GameLocation|blacksmith" "StardewValley.Menus.ShopMenu|tryToPurchaseItem"
& $py scratch\_probe_il.py scratch\il-up-3.txt "StardewValley.GameLocation|answerDialogueAction" "StardewValley.Utility|TryOpenShopMenu" "StardewValley.Internal.ShopBuilder|GetToolUpgradeData" "StardewValley.Internal.ShopBuilder|GetToolUpgradeConventionalPrice" "StardewValley.Tool|actionWhenPurchased" "StardewValley.Farmer|showToolUpgradeAvailability"
& $py scratch\_probe_il.py scratch\il-up-4.txt "StardewValley.Farmer|dayupdate" "StardewValley.Internal.ShopBuilder|GetToolUpgradeConventionalTradeItem"
& $py scratch\_t204_conv.py scratch\il-up-3.txt scratch\t204-il-up-3-u8.txt

# 3) 关键事实的 grep 复现
& $py scratch\_t204_grep.py scratch\t204-il-up-3-u8.txt "Clint_StillWorking|Blacksmith_Upgrade|Blacksmith_Shop" -n 2
& $py scratch\_t204_grep.py scratch\t204-il-up-2-u8.txt "getPlayerCurrencyAmount|moneyShakeTimer|TradeItem|ConsumeTradeItem" -n 1
& $py scratch\_t204_grep.py scratch\t204-il-up-3-u8.txt "ldc.i4\s+(2000|5000|10000|25000)" -n 0
& $py scratch\_t204_grep.py scratch\t204-api-out_u8.txt "TradeItem|ItemStockInformation" -n 0
```

## 8. 与 task-153 版（旧稿）的差异（修正清单）

1. **字段名**：`ItemStockInformation.TradeItem` / `TradeItemCount`（旧稿写 `TradeItemId`，错）。
2. **类型命名空间**：`StardewValley.ItemStockInformation`（不是 `StardewValley.Menus.*`）。
3. **等级 +1 的时机**：**买下时**新工具就带新等级（`getOne()` 的副本），**不是**取回时 +1。
4. **取回路径**：是 `blacksmith()` 开头的 pickup 分支（**不是** `answerDialogueAction`）。
5. **`Blacksmith_Upgrade` 分支只判 `daysLeft`**，不判 `toolBeingUpgraded != null` ⇒ 用 `TryOpenShopMenu` 绕过守卫有白扣风险。
6. **电话查价路径**会把 `ShopMenu.readOnly = true` ⇒ 该店里买东西只扣钱不升级。
7. **入口全 public**：`blacksmith`/`performAction`/`answerDialogueAction`/`TryOpenShopMenu`/`GetShopStock` 都不用反射；
   只有 `tryToPurchaseItem` 要反射。

> 姊妹篇：`docs/_il-newday-save.md`（日切保存链）、`docs/_il-shipmenu-save.md`（出货日 SaveGameMenu）、
> `docs/_il-harvest-path.md`（收成链路）。四篇合起来是「跨日 + 落盘 + 升级 + 收成」四条链的 IL 底稿。
