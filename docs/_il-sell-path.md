# 卖出 / 出货路径：IL 取证与选型（task-5）

> 只读取证。本文件所有结论都带定位：IL 转储文件 + 偏移，或反射 dump + 行号。
> 转储工具：`scratch\_probe_il.py`（内部调 `tools\il-probe\bin\Release\Probe26.exe`，UTF-16LE→UTF-8）。
> 反射工具：`scratch\_api_sell\`（自建只读副本，不改 `tools\api-probe`，不碰游戏进程）。

## 0. 一句话结论

**选路 B：出货箱 —— `Game1.getFarm().shipItem(item, Game1.player)`。** 它是 **public**、一次调用完成
"从背包拿走 → 进货箱 → 开箱动画"，IL 里**没有任何**菜单 / 坐标 / 朝向 / 距离 / 输入边沿判据；钱由
**下一次 `NewDay`** 里游戏自己的 `player.Money = player.Money + total` 付（`scratch\il-sell-newday.txt:774-779`）。
任务书里"路 A = `ShopMenu.tryToPurchaseItem` 的 `held_item != null` 支"**被证伪**：那一支是**买**（也扣钱），
真正的卖方逻辑在 `ShopMenu.receiveLeftClick/receiveRightClick`，它**先让 `InventoryMenu.leftClick` 把物品从背包拿走、再加钱**，
中途任何异常都会让物品**凭空消失**（见 §2）。实现上**绝不自己写 `Money +=`**：两条路的钱都出自游戏自己的
`chargePlayer` / `set_Money`。

---

## 1. 任务书 ① 的答案：`tryToPurchaseItem` 的 `held_item != null` 支到底做什么

方法：`StardewValley.Menus.ShopMenu.tryToPurchaseItem(ISalable item, ISalable held_item, Int32 stockToBuy, Int32 x, Int32 y)`
（转储 `scratch\il-sell-shopmenu.txt`，535 行）。可见性：**private**（`scratch\il-sell-visibility.txt`）——想调只能像 `BuySkill` 那样反射。

- `IL_0000-0009`：`readOnly` → `ret false`。
- `IL_0017-0018`：`ldarg.2 brtrue → IL_03A8`，即 `held_item == null` 走 **IL_001D 支**，`!= null` 走 **IL_03A8 支**。
- **`held_item == null` 支 = 买**：
  - `IL_001D`：`Stock == 0` → `hoveredItem = null; ret true`（**返回值只表示"该商品售罄 / 需要刷新显示"，不代表购买成功**）。
  - `IL_002E-004D` clamp `stockToBuy`；`IL_0050-0057` `price = stockInfo.Price * stockToBuy`。
  - `IL_0092-00A3` 钱不够 → `IL_037B`（cancel 音效 + `DayTimeMoneyBox.moneyShakeTimer = 1000`）。
  - `IL_00B8-00DC`：`this.heldItem = item.GetSalableInstance(); heldItem.Stack = stockToBuy * item.Stack`
    ⇒ **东西进"手上" = `ShopMenu.heldItem` 字段，不进背包**（`BuySkill` 因此要 `SettleHeldItem`）。
  - **`IL_0131-013D` `chargePlayer(player, currency, price)` = 扣钱**；`IL_014D ConsumeTradeItem`；
    `IL_0257 HandleSynchedItemPurchase`；`IL_0365 onPurchase.Invoke(...) → exitThisMenu`；
    `IL_05C2-05E2 if (Stock <= 0) { buyBackItems.Remove(item); hoveredItem = null; return true; } return false;`。
- **`held_item != null` 支（`IL_03A8`-`IL_05C2`）= 同样是买**（买进"手上"那一叠）：
  - 门闸 `if (!held_item.canStackWith(item)) goto 尾`；`IL_03B4-03CE`
    `stockToBuy = Min(stockToBuy, (held_item.maximumStackSize() - held_item.Stack) / item.Stack)`；
    `IL_03E1 price = Price * stockToBuy`；
  - `IL_047C-048B` `this.heldItem.Stack += stockToBuy * item.Stack`；
  - **`IL_04B1-04BE chargePlayer(...)` 仍然是扣钱**；`IL_050D ConsumeTradeItem`；
    `IL_051B-0533 actionWhenPurchased → heldItem = null`；`IL_0538 HandleSynchedItemPurchase`。
- ⇒ **两支都没有给玩家钱**。`buyBackItems`（`AddBuybackItem`）只在**真正的卖方逻辑**里被调用。

## 2. 真正的卖方逻辑（路 A 的实质）与它的致命处

`StardewValley.Menus.ShopMenu.receiveLeftClick(Int32 x, Int32 y, Boolean playSound)`（`scratch\il-sell-shopclick.txt`，752 行）：

- `IL_017C-018C`：`if (this.heldItem != null || this.readOnly) goto IL_0511` ⇒ **只有"手上空着 + 商店可写"才卖**。
- `IL_0191-01A0`：`Item item = this.inventory.leftClick(x, y, null, false)`（`IL_019B`）——**这一步就把物品从背包拿走了**（见下）。
- `IL_01A1`：`if (item == null) → IL_0530`（点空不做事）。
- `IL_01A7-01BC`：`if (this.onSell != null) { onSell.Invoke(item); goto IL_0509; }`
  ⇒ 商店若挂了 `onSell`（`public field Func<ISalable, Boolean> onSell`），**钱不由游戏给**（走自定义逻辑）。
- `IL_01C1-01D2`：`int price = (int)(item.sellToStorePrice(-1) * this.sellPercentage)`。
- **`IL_01D4-01E9`：`chargePlayer(player, this.currency, -price * item.Stack)`** —— 负数金额 = **加钱**（走游戏货币 API）。
- `IL_01EE-03C5`：掉屑动画（`Stack/8 + 2` 个 sprite）。
- `IL_03D4-03E5`：`if (CanBuyback()) AddBuybackItem(item, price, item.Stack)`。
- `IL_03FD-0480`：若 `item is Object && edibility != -300` → `getOne()` 补满 Stack（`IL_0410`）→ 记进
  `itemsToStartSellingTomorrow`（`IL_0476`，"明天货架上会出现"）。
- `IL_0490/IL_04A4`：`playSound("sell")` / `playSound("purchase")`。

`ShopMenu.receiveRightClick(Int32, Int32, Boolean)`（`scratch\il-sell-shoprclick.txt`，523 行）同型：
`IL_0048 onSell`；`IL_0064-0071 price = (int)(sellToStorePrice(-1) * sellPercentage)`；`IL_0074 stack = item.Stack`；
`IL_007D-008C chargePlayer(player, currency, -price * stack)`；`IL_00A0 AddBuybackItem`；`IL_0378 playSound("sell")`；
`IL_05B3 addItemToInventoryBool(...)`。

**致命处** —— `StardewValley.Menus.InventoryMenu.leftClick(Int32 x, Int32 y, Item toPlace, Boolean playSound)`
（`scratch\il-sell-invleftclick.txt`，115 行）：扫 `inventory` 组件 `containsPoint` 得 index，`toPlace == null` 支
（`ldarg.3 brfalse → IL_00C1`）里：

    IL_00DA  Item taken = Item.removeItemFromInventory(index, actualInventory); return taken;

⇒ **"从背包去掉"是 `InventoryMenu.leftClick` 自己做的**。调用方（`receiveLeftClick`）若在它之后任何地方提前返回 / 抛异常
（或 `onSell` 支路），物品**已经没了而钱没到**。这是路 A 不可回避的风险，不是理论风险：它由 IL 顺序保证。

价格：`Item.sellToStorePrice(Int64)` = `salePrice(false) / 2`（`scratch\il-sell-itemprice.txt:2-9`，整数除）；
`Utility.getSellToStorePriceOfItem(Item i, Boolean countStack)` = `i == null ? 0 : sellToStorePrice(-1) * (countStack ? i.Stack : 1)`
（`scratch\il-sell-sellprice-util.txt:2-19`）。`ShopMenu.chargePlayer` / `getPlayerCurrencyAmount` 都是 **public static**，
`switch (currencyType)`：0 = `who.Money`（`IL_001B-0029`）、1 = festivalScore、2 = clubCoins、3 = QiGems
（`scratch\il-sell-charge.txt` 34 行、`scratch\il-sell-currency.txt:1-19`）。
`ShopMenu.sellPercentage` 是 **private float**（`scratch\il-sell-visibility.txt`）⇒ 脑/Mod 读不到，路 A 的实际收益不可预测。

## 3. 路 B（出货箱）：入口 + 结算时机 + 价格（推荐）

### 3.1 入口：一次调用

`StardewValley.Farm.shipItem(Item i, Farmer who)`（**public**）— `scratch\il-sell-farmship.txt:2-27`：

    i == null → return
    who.removeItemFromInventory(i)        // 从背包拿去
    this.getShippingBin(who).Add(i)       // 进货箱
    this.showShipment(i, false)           // 开箱动画
    this.lastItemShipped = i
    if (Game1.player.ActiveItem == null) { showNotCarrying(); Halt(); }

`Farm.getShippingBin(Farmer who)`（**public**）— `scratch\il-sell-getbin.txt:2-15`：

    if (Game1.player.team.useSeparateWallets) return who.personalShippingBin.Value;
    else                                       return this.sharedShippingBin.Value;

箱子**一定非 null**：`Farm..ctor` 里 `new Inventory()` → `new NetRef<Inventory>(...)` → `stfld sharedShippingBin`
（`scratch\il-sell-binctor.txt:33-36`，两个 ctor 都有）。`Farm.AddDefaultBuildings` 只加 "Shipping Bin" **建筑外观**
（同文件 `:105-133`），不影响容器。
`Buildings.ShippingBin.doAction(Vector2, Farmer)`（`scratch\il-sell-bindoaction.txt:IL_0058-0061`）要求
`Game1.didPlayerJustRightClick(true)` ⇒ **不可自动化**；`FIND|shipItem`（`scratch\il-sell-shipitem-callers.txt`）的调用者只有
`Locations.IslandWest.checkAction` 与 `Buildings.ShippingBin.doAction`。我们从 Mod 直接调 `Farm.shipItem` 是"另开一个入口"，
但该入口本身 public（§4），且内部逻辑与游戏自己走的完全相同。

### 3.2 结算时机：下一次 NewDay 的 `_newDayAfterFade`

`Game1+<_newDayAfterFade>d__784.MoveNext`（`scratch\il-sell-newday.txt`，2340 行）：

- `:676-681`（`IL_09A2-09B1`）：`bin = Farm.getShippingBin(player); bin.RemoveEmptySlots();`
- `:686-695`（`IL_09B8-09E3`）：每件 `Game1.player.displayedShippedItems.Add(item)`。
- `:702-707`（`IL_09F3-0A09`）：`if (!useSeparateWallets && !IsMainPlayer) goto IL_0AE0`。
- `:714-735`（`IL_0A0E-0A4F`）求总额：`var obj = item as Object; if (obj != null) value = obj.sellToStorePrice(-1) * obj.Stack; total += value;`
  ⇒ **非 `Object` 的物品计 0 钱**。
- `:736-767`（`IL_0A51-0AB3`）：`team.specialOrders` 里每个 `onItemShipped?.Invoke(player, item, value)`。
- **`:774-779`（`IL_0ACD-0ADB`）：`player.Money = player.Money + total`** —— 主玩家唯一的加钱点。
- `:900-978`（`IL_0CA7-0D96`）离线帮工：逐个 `getFarm().getShippingBin(f)`、`sellToStorePrice(f.UniqueMultiplayerID)`
  （`:922-925`）、`team.AddIndividualMoney(f, total)`（`:976`）、`bin.Clear()`（`:978`）。
- `:1173-1182`（`IL_1008-1031`）屏障 `clearShipping`：`Farm.lastItemShipped = null; Farm.getShippingBin(player).Clear();`
  ⇒ **主玩家货箱在钱入账之后才清空**。
- `Menus.ShippingMenu.parseItems(IList<Item>)`（`scratch\il-sell-shippingmenu.txt`，198 行）只用 `sellToStorePrice` + `MoneyDial`
  做**展示**，不加钱。
- 链：`FIND|newDayAfterFade`（`scratch\il-sell-newday-find.txt`，7 条）= `Game1.newDayAfterFade(Action)` →
  `<>c__DisplayClass782_0.<newDayAfterFade>b__0` → `Game1._newDayAfterFade`。

### 3.3 价格：出货箱给**全额**（"卖店半价"不适用于 Object）

`Object.sellToStorePrice(Int64)`（`scratch\il-sell-objprice.txt:2-82`）：

- `Fence` → `price`；
- `Category == -22`（渔具）→ uses 相关的专门公式；
- 其它：`num = price * (1 + quality * 0.25)` → `getPriceAfterMultipliers(num, specificPlayerID)` →
  若 `QualifiedItemId == "(O)493"` 再除一个常数 → `num = Max(1, num * MasterPlayer.difficultyModifier)`。

对照：`Item.sellToStorePrice = salePrice(false) / 2`，而 `Item.salePrice(bool)` 基类就是 `return -1`
（`scratch\il-sell-objprice.txt:85-87`）⇒ 那条"半价"只作用于**非 `Object`**，而新日结算只累加 `Object`
⇒ **工具/武器出货 = 0 钱且物品消失**（白名单必须挡住）。`Object.salePrice(bool)` 里还有
`(O)388/390/382/378/380/384`（木材/石头/煤/铜/铁/金矿）按年份的硬编码价（同文件 `:110-177`）。

## 4. 可见性实证与三个必须写进实现纪律的陷阱

反射 dump 原始输出：`scratch\il-sell-visibility.txt`（`scratch\_api_sell\`，`dotnet build -c Release` 后运行）。

- **public（可直接调）**：`Farm.shipItem/getShippingBin/lastItemShipped/showShipment`；
  `ShopMenu.chargePlayer`(static)、`getPlayerCurrencyAmount`(static)、`receiveLeftClick`、`receiveRightClick`、
  `performHoverAction`、`heldItem`、`readOnly`、`buyBackItems`、`buyBackItemsToResellTomorrow`、`currency`、
  `inventory`、`onSell`、`AddBuybackItem`、`CanBuyback`、`ShopId`；`InventoryMenu.leftClick/getItemAt/inventory/actualInventory`；
  `Item.sellToStorePrice/salePrice/Stack/Category/QualifiedItemId`；`Object.sellToStorePrice/salePrice/questItem/bigCraftable/Type/IsSpawnedObject`；
  `StardewValley.Tool.isScythe/UpgradeLevel/isHeavyHitter`；`Utility.TryOpenShopMenu`(两个重载)/`getSellToStorePriceOfItem`(static)；
  `Farmer.displayedShippedItems/Money/removeItemFromInventory/Items/personalShippingBin/team`；
  `StardewValley.FarmerTeam.useSeparateWallets/AddIndividualMoney`；`Game1.getFarm/player/activeClickableMenu`。
- **private（不许直接调）**：`ShopMenu.tryToPurchaseItem`、`ShopMenu.sellPercentage`、`Buildings.ShippingBin.shipItem`
  （要出货就调 `Farm.shipItem`，不要反射调这个）。

**陷阱 1（会复制物品）**：`Farmer.removeItemFromInventory(Item which)` 的 IL 是
`int index = Items.IndexOf(which); if (index < 0 || index >= Items.Count) return; Items[index].actionWhenStopBeingHeld(this); Items[index] = null;`
（`scratch\il-sell-removeinv.txt:2-30`），而 `Item.Equals(object)` / `Object.Equals(object)` 都只是转调
`object.Equals(object, object)`（`scratch\il-sell-equals.txt:2-13`）⇒ **引用相等**。所以传 `getOne()` 副本时 `IndexOf` 返回 -1：
**原物不被动、副本进箱** ⇒ 次日多拿一份钱。**必须传背包里那个实例**（`Game1.player.Items[slot]`）。

**陷阱 2（整叠出货）**：同一条 IL 的 `Items[index] = null` ⇒ 一格 400 个就出 400 个，`shipItem` **没有"出一部分"的能力**。

**陷阱 3（副作用）**：`shipItem` 会调 `showShipment`（动画）与 `Halt()`（镜头停住，只在 `ActiveItem == null` 时）。
自动化里不要在依赖输入/动画的同一帧做判断。

## 5. A / B 选型（成本 / 风险 / 观测差分）与明确推荐

| 维度 | 路 A：商店卖 | 路 B：出货箱 |
|---|---|---|
| 入口 | private UI 回调；要么反射调 `receiveLeftClick(坐标)`，要么反射调 private `tryToPurchaseItem`（而它不卖） | **public** `Farm.shipItem(item, who)` 一行 |
| 前置 | 需开店（`Utility.TryOpenShopMenu` public，`BuySkill` 已实证）+ `heldItem == null` + `readOnly == false` + 命中商品格的**像素坐标** | 无（不需菜单/坐标/距离/朝向） |
| 收益时点 | 同帧到账 | **次日 NewDay**（`IL_0ACD-0ADB`） |
| 单价 | `sellToStorePrice(-1) * sellPercentage`（`sellPercentage` private，可能 ≠ 1） | 全额 `Object.sellToStorePrice(-1) * Stack` |
| 失败模式 | 物品已被 `InventoryMenu.leftClick` 拿走而钱没到 ⇒ **凭空消失**；几何点偏 ⇒ 卖错东西；挂 `onSell` 的店不给钱 | 参数错则早退无副作用；**唯一风险是陷阱 1 的复制**（传给非背包实例） |
| 可观测差分 | `inventory[]` 与 `money` **当场**变化 | `inventory[]` 当场少、`money` **次日**涨；货箱内容**当前观测不到**（U1） |

**推荐 = 路 B。** 理由：入口是 public、无 UI/几何依赖、价格更高且可算（`Object.sellToStorePrice(-1)`，脑里也能用
`Utility.getSellToStorePriceOfItem` 预测）、失败模式是"早退"而不是"物品消失"。
路 A 只作为**将来**的 fallback（例如"不清货箱格 / 要当场拿钱"），且必须先解决坐标脆弱性与 `onSell` 支路。

## 6. 黑白名单（伪代码，待在 mod 侧 `SellSkill` 实现）

    允许出货(slot):
      1  必要性：Game1.getFarm() != null && who != null
      2  item = who.Items[slot]                // **必须是背包里的实例**（陷阱 1）
      3  item == null                          → refuse "empty_slot"
      4  item is not Object                    → refuse "not_sellable"   // 工具/武器/家具之外的杂项：0 钱还白丢
      5  ((Object)item).questItem.Value        → refuse "quest_item"
      6  ((Object)item).bigCraftable.Value     → refuse "big_craftable"  // 机器/箱子类
      7  item.Stack <= 0                       → refuse "empty_stack"
      8  item.Stack > 1 且 !policy.allowWholeStack → refuse "whole_stack_only"   // v1：只出 1 件
      9  item.QualifiedItemId ∉ brain 下发的白名单(本日实际收获的 id) → refuse "not_whitelisted"
     10  调 Game1.getFarm().shipItem(item, Game1.player)      // 游戏自己的入口
     11  回执 = { slot, QualifiedItemId, Stack, lastItemShipped == item }
         // 回执**不算证据**（use_tool / buy 的教训），验证只看差分

brain 侧：`harvest` 成功时把"本日产出 id"记进白名单；`sell` 只吃这份白名单；**永不出货**工具/武器/任务物/机器。

## 7. 真机验收怎么做（先假世界，后真机）

0. **诚实前置（必须写进报告）**：① `brain\agentfarm\farmwork.py:831-863` 的 `harvest()` docstring 自己写着
   "真机证据还薄"；② 当前 sleep/跨日坏着（task-8）⇒ **路 B 的"钱到账"这一半今天无法验收**。
1. **假世界单测（brain/py，`tests\test_farmwork.py` 范式）**：fake bridge client 记录调用序列，断言
   "取 slot → exec sell → 不改本地 money/inventory 计数"（钱由游戏给，脑不许自己算）。
2. **真机单件试验**：确认背包里**恰好 1 个** parsnip（`(O)24`）→ 调 sell →
   **立即差分**：`inventory[]` 该格消失、`inventoryCount -1`、**`money` 不变**（这是预期，不是失败）。
3. **跨日验收（等 task-8）**：sleep → 次日 `money` 增量 == `Object.sellToStorePrice(-1) * 1`（parsnip 35 × 质量系数）；
   `displayedShippedItems` 有它；货箱清空（`clearShipping`，`:1173-1182`）。
4. **负对照**：`shipItem(null, who)` 无任何变化；非 `Object`（斧头）**只在单测里**断言被白名单挡住，真机不试。
5. **≥3 次重复**：每次只出 1 件，观察 `inventoryCount` 单调 -1、无重复计数（防陷阱 1）。

## 8. 未定（U）

- **U1（最重要）**：观测里**没有货箱内容**。`mod\AgentFarm.Bridge\Contracts.cs:145 "money"`、`:147 "inventoryCount"`、
  `:183 "inventory" ItemView[]` 是全部相关字段 ⇒ 出货后**当天没有可判定的证据**。需要加
  `farm.shippingBin[]`（或 `player.displayedShippedItems`，或 public 的 `Farm.lastItemShipped`）才能当场差分。
- **U2**：在**非 Farm 地点**调 `shipItem` 是否安全 —— IL 里无方位/距离判据（静态证据支持"安全"），但**未真机验证**。
- **U3**：`sellPercentage` 的赋值来源（private，未反查到）⇒ 路 A 收益不可预测。
- **U4**：`Object.sellToStorePrice` 里 `(O)493` 的除数与 `getPriceAfterMultipliers` 细节（dump 省略了 `ldc.r4` 常量）。
- **U5**：`onSell` 在哪些商店会被挂上（未做 `FIND|onSell`）。
- **U6**：若业务上需要"出 N 件留 M 件"，`shipItem` 做不到（整叠 + `Items[index] = null`），需要另找游戏内分叠入口。

## 9. 复核命令

    # IL 转储（UTF-16LE → UTF-8 由脚本自动处理）
    python scratch\_probe_il.py scratch\il-sell-<名>.txt "StardewValley.Farm|shipItem" "FIND|getShippingBin" ...
    # 可见性（反射，不碰游戏）
    dotnet build "scratch\_api_sell\ApiSell.csproj" -c Release
    dotnet "scratch\_api_sell\bin\Release\net6.0\ApiSell.dll"

证据文件：`scratch\il-sell-shopmenu.txt`、`il-sell-shopclick.txt`、`il-sell-shoprclick.txt`、`il-sell-itemprice.txt`、
`il-sell-objprice.txt`、`il-sell-sellprice-util.txt`、`il-sell-charge.txt`、`il-sell-currency.txt`、`il-sell-invleftclick.txt`、
`il-sell-farmship.txt`、`il-sell-getbin.txt`、`il-sell-binship.txt`、`il-sell-bindoaction.txt`、`il-sell-newday.txt`、
`il-sell-newday-find.txt`、`il-sell-binctor.txt`、`il-sell-removeinv.txt`、`il-sell-equals.txt`、`il-sell-shippingmenu.txt`、
`il-sell-shipitem-callers.txt`、`il-sell-storeprice.txt`、`il-sell-saleprice.txt`、`il-sell-visibility.txt`。

## 10. 一句话总评

出路 B：**一个 public API + 次日由游戏自己结算**，失败是"没出货"而不是"东西没了"；
路 A 是"先扣物、后给钱、还要点像素坐标"的私有 UI 回调，风险不对等。
**但真正的卡点是 U1：加上货箱观测字段之前，出货这件事当天不可判定，"回执 ok"依旧不能当证据。**
