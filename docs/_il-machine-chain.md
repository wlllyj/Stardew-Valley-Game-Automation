# IL 取证 · 机器链：制作熔炉 → 放下去 → 投料 → 取锭（1.6.15 定案）

> 卡：task-211（关键路径）。目的：给 dev-coder（task-205/210 的机器回路）一份**可直接照抄**的三条最小安全调用序列。
> 方法：`tools\il-probe`（`Type|Method`、`FIND|`、`DISASM|`）+ `tools\api-probe` 反射 + 既有真机定案（`docs\_il-plant-consume.md`、`docs\_run10-material-scan.md`）。
> 纪律：**全程离线只读**，没启游戏、没动桥、没改存档。所有证据文件都在 `scratch/`，见 §7。
> 先说结论：**卡面的假设有两处过时** —— ① `CraftingRecipe` 在 1.6.15 **没有** `Craft(Farmer,int)` 方法；② `Object` 没有 `readyForHarvest()` 方法，`readyForHarvest` 是 **`NetBool` 字段**。另外发现一个**硬阻塞**：run10 存档里熔炉配方**还没学会**（§2.4）。

## 0. 速览（最关键的 5 条）

1. **三条链都有「方法级入口」，不需要模拟按键**：制作 = `CraftingRecipe.createItem()` + `consumeIngredients()`（都 public）；放置 = `Utility.tryToPlaceItem(...)`（public static）；投料/取货 = `GameLocation.checkAction(tile, Game1.viewport, Game1.player)`（public，就是 Mod 现在 `interact` 用的那个）。
2. **扣材料/扣物品都不在"造/放"的那一步里**，而在链尾：制作由 `consumeIngredients` 扣、放置由 `Game1.pressActionButton` 或 `Utility.tryToPlaceItem` 里的 `reduceActiveItemByOne()` 扣、投料由 `Object.PlaceInMachine → ConsumeInventoryItem` 扣。**绕过入口就必须用游戏自己的方法把这一步补回来**（0.7.19 播种踩过同一个坑）。
3. **投料和取货都走 `checkAction`，且投料读的是 `Farmer.CurrentItem`（当前选中的快捷栏物品），不是 `ActiveObject`**。所以投料前必须先把铜矿选到当前格（`Farmer.CurrentToolIndex`），否则 `checkAction` 走不到投料分支。
4. **`checkAction` 内部已经有"先 probe 干跑再真做"与 `ignoreItemConsumptionThisFrame` 防双扣**（`scratch/il-hv-1.txt:503-576`）。**自己直接调 `performObjectDropInAction` 再自己扣，会双扣**。
5. **取货在背包满时是安全的**：`CheckForActionOnMachine` 把产物放回 `heldObject` 并红字提示、返回 false（不吞产物）。而**制作的菜单路径（`CraftingPage.clickCraftingRecipe`，private）是"先扣材料、产物挂在光标的"**，不要用它。

## 1. 三条链的入口链（成员 + 可见性）

### 1.1 制作（熔炉 = 大件 `(BC)114`）

| 环节 | 成员（反射实证，`scratch/t211-api-out.txt`） | 可见性 |
|---|---|---|
| 取配方对象 | `CraftingRecipe(String name)` / `CraftingRecipe(String name, Boolean isCookingRecipe)` | **public** |
| 查材料够不够 | `CraftingRecipe.doesFarmerHaveIngredientsInInventory(IList<Item> extraToCheck)` | **public** |
| 扣材料 | `CraftingRecipe.consumeIngredients(List<Item> additionalMaterials)`（**void，无返回值**） | **public** |
| 造出物品 | `CraftingRecipe.createItem()` → `Item`（**只造，不进背包**） | **public** |
| 进背包 | `Farmer.addItemToInventoryBool(Item, Boolean)`（0.7.19 前就在用，Mod 侧编译通过即 public 实证） | public |
| 菜单路径（不推荐） | `Menus.CraftingPage.ctor(Int32,Int32,Int32,Int32,Boolean,Boolean,List<object>)`、`receiveLeftClick` | public，但内部 `clickCraftingRecipe(ClickableTextureComponent, Boolean)` 是 **private** |

> ❗ 1.6.15 **不存在** `CraftingRecipe.Craft(...)`（反射 dump 里没有；`scratch/t211-api-out.txt` 的 CraftingRecipe 段）。老代码/wiki 写法不可照抄。
> 配方数据：`CraftingRecipe.InitShared()` 里 `craftingRecipes = DataLoader.CraftingRecipes(Game1.content)`（`scratch/il-mc-1.txt:1409` 附近），即 `Game1.content.Load<Dictionary<string,string>>("Data\CraftingRecipes")`（`scratch/il-mc-3.txt:712`）。

### 1.2 放置（把熔炉放到地图上）

| 环节 | 成员 | 可见性 |
|---|---|---|
| 只放不扣 | `Object.placementAction(GameLocation, Int32 x, Int32 y, Farmer)` | **public** |
| 放 + 扣（推荐） | `Utility.tryToPlaceItem(GameLocation, Object item, Int32 x, Int32 y)` | **public static** |
| 扣 1 个（游戏口径） | `Farmer.reduceActiveItemByOne()` | **public** |
| 人类入口 | `Game1.pressActionButton(KeyboardState, MouseState, GamePadState)` | public，但**由输入状态驱动**，自动化不可靠（`docs\_il-plant-consume.md` §2.2/§3） |

`Utility.tryToPlaceItem` 的 IL（`scratch/il-mc-4.txt:1374-1545`）逐条：

```
if (item == null) return false;                             // IL_0000-0004
tile = (x/64f, y/64f)                                       // IL_0005-0011
if (!playerCanPlaceItemHere(loc, item, x, y, Game1.player, false)) goto 失败分支
if (item is Furniture) Game1.player.ActiveObject = null;    // IL_002F-0035
if (item.placementAction(loc, x, y, Game1.player)) {
    Game1.player.reduceActiveItemByOne();                   // IL_004A-004F ← 扣物品在这里
    return true;                                            // IL_0077-0078
} else {
    if (item is Furniture) 还原 ActiveObject;
    if (item is Wallpaper) return false;
    return true;                                            // ⚠ 非家具放置失败也返回 true
}
失败分支：施肥规则/红字提示后 return false;                  // IL_00DD-01DA
```

⇒ **返回值不可信**（非家具、非壁纸时，`placementAction` 失败也返回 `true`）⇒ 必须用**观测**验证"熔炉真的在地图上"。

### 1.3 投料 / 取货（对已放下的机器）

| 环节 | 成员 | 可见性 |
|---|---|---|
| **统一入口** | `GameLocation.checkAction(Location tileLocation, Rectangle viewport, Farmer who)` | **public** |
| 干跑（判断"能不能收下"） | `Object.performObjectDropInAction(Item, Boolean probe, Farmer, Boolean returnFalseIfItemConsumed)` | **public** |
| 真正装料 | `Object.PlaceInMachine(MachineData, Item, Boolean probe, Farmer, Boolean showMessages, Boolean playSounds)` | **public** |
| 产出/装产物 | `Object.OutputMachine(MachineData, MachineOutputRule, Item, Farmer, GameLocation, Boolean probe, Boolean heldObjectOnly)` | **public** |
| 取货实现 | `Object.CheckForActionOnMachine(Farmer, Boolean justCheckingForActivity)` | **private**（只经 `checkForAction` 进） |
| 机器数据 | `Object.GetMachineData()` | **public** |

人类入口还是 `Game1.pressActionButton`（`scratch/il-hv-1.txt` 里 `performUseAction`→`reduceActiveItemByOne` 那段，`docs\_il-plant-consume.md` §2.2 有偏移表）。自动化直接调 `checkAction`。

## 2. 扣料与计时（游戏口径）

### 2.1 投放：`checkAction` 的完整顺序（`scratch/il-hv-1.txt:503-576`，IL_05EB-0698）

```csharp
// 仅当该格的 Action 类型是 "Crafting" / "interactive"（IL_05CA-05E6）
if (who.CurrentItem == null) { obj.checkForAction(who, false); return; }   // IL_0612/0699
object loc22 = obj.heldObject.Value;                 // 先存旧 held
obj.heldObject.Value = null;                         // IL_0627-062E 临时清空
bool p = obj.performObjectDropInAction(who.CurrentItem, probe:true,  who, false);  // 干跑
obj.heldObject.Value = loc22;                        // 还原
bool r = obj.performObjectDropInAction(who.CurrentItem, probe:false, who, true);   // 真做
if (p || r) { if (who.isMoving()) haltAfterCheck = false; }
if (who.ignoreItemConsumptionThisFrame) return true;                // 机器自己已扣
if (r) { who.reduceActiveItemByOne(); return true; }                // 否则由这里扣 1
return obj.checkForAction(who, false) || p;                          // 不成立时退化成"用一下"
```

要点：
* 输入物 = **`who.CurrentItem`**（不是 `ActiveObject`）。所以投料前必须把铜矿选到快捷栏当前格。
* `returnFalseIfItemConsumed:true` ⇒ 机器**成功装料时该方法返回 false**（因为 `PlaceInMachine` 已经通过 `ConsumeInventoryItem` 扣过）；caller 靠干跑结果 `p` 判断"成没成"。**返回值语义是反的，别当真值用**。
* 自己绕过 `checkAction` 直接调 `performObjectDropInAction` 时必须自己扣且只能扣一次（否则双扣），**强烈建议直接复用 `checkAction`**（Mod 的 `interact` 已经是它）。

### 2.2 机器内部：`performObjectDropInAction`（`scratch/il-mc-2.txt:2-313`）

```
若 isTemporarilyInvisible / dropInItem 不是 Object ⇒ false
洒水器分支：装肥料、heldObject、MinutesUntilReady=-1、true（probe 早返回 1）
仙尘 (O)872 分支
MachineData md = GetMachineData();
if (md != null) {
    if (heldObject != null && !md.AllowLoadWhenFull) return false;
    if (probe && MinutesUntilReady > 0) return false;          // 满了就别收
    if (PlaceInMachine(md, dropInItem, probe, who, showMessages:true, playSounds:true)) {
        if (returnFalseIfItemConsumed && !probe) return false;  // ← 上面的"反向返回值"
        return true;
    }
    return false;
}
// 干草料斗 (BC)99 分支…
```

`PlaceInMachine`（`scratch/il-mc-4.txt:2-254`）：
```
自动装载仓 inv = autoLoadFrom ?? who.Items;
HasAdditionalRequirements(inv, md.AdditionalConsumedItems, out fail) 失败 ⇒ 红字 + ignoreItemConsumptionThisFrame=true + false
TryGetMachineOutputRule(..., ItemPlacedInMachine, ...) 失败 ⇒ 红字 + ignoreItemConsumptionThisFrame=true + false
if (probe) return true;                                   // IL_0176-017A：干跑到此结束，不动任何状态
OutputMachine(md, rule, inputItem, who, location, probe:false, heldObjectOnly:false)
foreach (var req in md.AdditionalConsumedItems) inv.ReduceId(req.ItemId, req.RequiredCount);  // 煤在这里扣
if (triggerRule.RequiredCount > 0) ConsumeInventoryItem(who, inputItem, triggerRule.RequiredCount); // 铜矿在这里扣
装料动画/音效/统计…
```

`ConsumeInventoryItem`（`scratch/il-mc-6.txt:17` 起）：
```
if (drop_in.ConsumeStack(amount) == null) {           // ConsumeStack 就地改 Stack；扣光才返回 null
    (autoLoadFrom ?? who.Items).RemoveButKeepEmptySlot(drop_in);
    ...
}
```
⇒ **按物品实例扣**。必须传背包里的**那个实例**；传 `getOne()` 副本会扣不到/复制（同 task-5 售卖教训）。

### 2.3 取货：`CheckForActionOnMachine`（`scratch/il-mc-5.txt:2-284`）

```
md = GetMachineData();
if (!readyForHarvest.Value) { if (md.InteractMethod 命中) 走交互；return false; }
if (justCheckingForActivity) return true;                  // 纯查询，不改状态
held = heldObject.Value;                                   // RecaculateOnCollect 时先用 OutputMachine(heldObjectOnly) 重算
if (who.IsLocalPlayer) {
    heldObject.Value = null;
    if (!who.addItemToInventoryBool(held, false)) {         // 背包满
        heldObject.Value = held;                            // ← 放回去，不吞产物
        showRedMessage("Strings\StringsFromCSFiles:Crop.cs.588");
        return false;
    }
    playSound("coin"); ...
}
heldObject.Value = null; readyForHarvest.Value = false; showNextIndex = false;
if (md != null && OutputCollected 规则命中) OutputMachine(...)  // 自动重新装料（例如持续型机器）
```

### 2.4 计时与配方数据（**这两项离线定不了，禁止硬编码**）

* 计时：`OutputMachine`（`scratch/il-mc-4.txt:257-465`）从 `MachineOutputRule` 取 `MinutesUntilReady`（或 `DaysUntilReady` 经 `CalculateMinutesUntilMorning`），再叠 `ReadyTimeModifiers`，`MinutesUntilReady==0` 时 `readyForHarvest = true`。**具体分钟数在内容数据里**。
* 数据位置（IL 实证）：`DataLoader.CraftingRecipes(LocalizedContentManager)` → `Game1.content.Load<Dictionary<string,string>>("Data\CraftingRecipes")`；`DataLoader.Machines(...)` → `Game1.content.Load<Dictionary<string,MachineData>>("Data\Machines")`（`scratch/il-mc-3.txt:712`、`:719`）。**`Content\` 是打包 xnb，本仓库没有 xnb 解包器** ⇒ 熔炉配方串与 `MachineData` 数值 = **【无法判定·离线】**，不许抄 wiki。
* 运行时 dump（给 task-210 用；`DataLoader` 这两个方法是 public static，或直接 `Game1.content.Load<...>`）：
  ```csharp
  var rawRecipes = Game1.content.Load<Dictionary<string, string>>("Data\\CraftingRecipes"); // 打印与 Furnace 相关的 key/value
  var machines   = Game1.content.Load<Dictionary<string, MachineData>>("Data\\Machines");  // 打印 keys，钉死熔炉键形式
  bool learned   = Game1.player.craftingRecipes.ContainsKey("Furnace");                    // 学会没有（键形式待钉死）
  ```
* ⚠ **硬阻塞**：`docs\_run10-material-scan.md` 实测 run10 存档 `craftingRecipes` 只有 19 条、**没有 Furnace**；mining level 1（279 xp）、`deepestMineLevel=0`、背包 12/12 满。⇒ **机器回路的第一道门不是 IL，是"熔炉配方还没学会"**（先解决蓝图获取；触发条件属存档/运行时，未定）。

## 3. 三条可直接照抄的最小安全调用序列

> 三条都遵守同一个模式：**先观测/干跑 → 用游戏自己的方法做 → 用观测差分验收**。绝不信回执或返回值。

### 3.1 制作熔炉（`craft_item`）

```csharp
// 前置：Game1.player.craftingRecipes.ContainsKey("Furnace") 为 true（否则如实失败 code=recipe_unknown）
var recipe = new CraftingRecipe("Furnace");                       // public ctor，从 Data\CraftingRecipes 解析
if (!recipe.doesFarmerHaveIngredientsInInventory(null)) return Fail("materials_missing");
Item crafted = recipe.createItem();                               // 只造，不进背包、不扣材料
if (crafted == null) return Fail("recipe_invalid");
if (!HasRoomFor(Game1.player, crafted)) return Fail("no_inventory_space");  // 自己扫 who.Items（public），不要先扣
recipe.consumeIngredients(null);                                  // 扣材料（void；此时才扣）
bool added = Game1.player.addItemToInventoryBool(crafted, false);
if (!added) return Fail("add_failed_after_consume");             // 理论上已被上一步挡住；如实报错
Ok();
```
* 判据（观测差分）：背包多 1 件 `(BC)114`；铜矿 −20、石头 −25（数值以运行时数据为准，不是本条硬编码）。
* 兜底：材料不够 → `materials_missing`；背包满 → `no_inventory_space`（**先扣后失败的坑就在这里被堵住**）；配方未学会 → `recipe_unknown`。

### 3.2 放置熔炉（`place_object`）

```csharp
// 前置：目标格可站、格子上没东西；熔炉在背包第 i 格
Game1.player.CurrentToolIndex = i;                 // public NetInt：把熔炉选成 CurrentItem（扣料作用于它）
bool ok = Utility.tryToPlaceItem(location, (Object)item, tileX * 64 + 32, tileY * 64 + 32);  // 像素坐标约定见 U4
// 不信 ok：观测 tile 上出现 qid == "(BC)114" 才算成功
// 校验扣减：该物品 Stack 恰好 -1（若没减 ⇒ 游戏入口没走到，如实报 item_not_consumed，别自己补扣两次）
```
* 判据：格子上出现熔炉对象 **且** 背包该物品 −1。
* 兜底：`tryToPlaceItem` 返回 true 但观测没变化 ⇒ `placement_failed_unconsumed`（返回值不可信，见 §1.2）；若返回 true 且背包没减 ⇒ 游戏链没扣，**不要**盲目 `reduceActiveItemByOne()`（可能已扣别的物品/别的槽）。

### 3.3 投料 + 取货（`feed_machine` / `collect_machine`，复用 `interact`）

```csharp
// 投料前置：站在机器 4 邻；把铜矿选到 CurrentItem（选 slot 的 NetInt）
Game1.player.CurrentToolIndex = oreSlot;
Game1.currentLocation.checkAction(new Location(tileX, tileY), Game1.viewport, Game1.player);
// 判据：heldObject 非空、MinutesUntilReady > 0、背包铜矿 −5 且煤 −1（数值以运行时数据为准）
// 取货：同一句 checkAction；判据：heldObject 变空、readyForHarvest==false、背包 +1 铜锭
```
* 取货兜底：背包满时游戏已安全（产物放回、红字、返回 false）⇒ 如实报 `no_inventory_space`。
* **不要**自己调 `performObjectDropInAction` 再自己扣（双扣，见 §0-4）。

## 4. 风险与不可逆点

| # | 风险 | 证据 | 对策 |
|---|---|---|---|
| R1 | 制作菜单路径"先扣材料、产物挂光标" | `CraftingPage.clickCraftingRecipe`（`scratch/il-mc-3.txt:241` 起：`createItem` 先、`heldItem==null` 时 `consumeIngredients` 后、`heldItem=crafted`） | **不走菜单**，用 §3.1 原语 |
| R2 | `placementAction` 不扣物品 | `FIND|reduceActiveItemByOne` 的 25 个调用者里没有 `placementAction`（`docs\_il-plant-consume.md` §2.1） | 用 `tryToPlaceItem`（它扣）或自己补一次（只一次） |
| R3 | 投料双扣 | `checkAction` 的 `ignoreItemConsumptionThisFrame` + `returnFalseIfItemConsumed` 逻辑 | 只走 `checkAction` |
| R4 | 扣错物品/扣不到 | `ConsumeInventoryItem` 按实例 `ConsumeStack` + `RemoveButKeepEmptySlot` | 传背包实例，不传副本 |
| R5 | 背包满丢产物（制作） | 菜单路径的光标物品 | §3.1 前置自检 + 原语路径 |
| R6 | 机器数值硬编码错 | 数据在 `Data\Machines`/`Data\CraftingRecipes`（xnb） | 运行时 dump（§2.4），生产逻辑不写死数字 |
| R7 | 时间不推进就不出锭 | `MinutesUntilReady` 只随时间/`DayUpdate` 推进 | 只能"等"（跨日/睡觉），不许改 `minutesUntilReady` 作弊 |
| R8 | 熔炉配方未学会 | run10 实测 19 条无 Furnace（`docs\_run10-material-scan.md`） | 先解决蓝图；否则整条链不可达 |

不可逆点：熔炉放下后只能 `performToolAction` 敲掉（会掉物品，未验）；材料扣了不会退；存档回滚只有 `load_save`。

## 5. 给 task-205 / task-210 的实现清单

**Mod 侧观测（`WorldSnapshot` 的对象条目加字段，反射路径）**
* `heldObject`：`Object.heldObject`（public `NetRef<Object>`）→ `.Value` 的 `QualifiedItemId` + `Stack`（空 = null）
* `readyForHarvest`：`Object.readyForHarvest`（public `NetBool`）→ `.Value`
* `minutesUntilReady`：`Object.MinutesUntilReady`（public int 属性；底层 public 字段 `minutesUntilReady`: `NetIntDelta`）
* `bigCraftable`（public `NetBool`）、`qid`（`Item.QualifiedItemId`）
* `lastInputItem` / `lastOutputRuleId`（**可见性未定**，U3；先试反射，拿不到就不给）

**Mod 侧技能**：`craft_item`（recipeName）、`place_object`（qid, tile）、`feed_machine`/`collect_machine`（可先复用 `interact` + `select_item`，但必须在回执里写清"选了哪个槽、扣了多少"）。

**脑侧判据**：一律观测差分（背包物品数、机器 `heldObject`/`readyForHarvest`、`farm.machinesTotal/Ready`）；预算/配方未学会要作为**前置检查**如实失败，不许当成"做了但没效果"。

**验收**：同格真机 —— 造 1 个熔炉、放到指定格、投 5 矿+1 煤、等到出锭、取 1 锭；每步都用 `observe?detail=full` 差分，不采信回执。

## 6. 未定项（UNRESOLVED）

* **U1** 熔炉配方串 + `MachineData` 数值（`MinutesUntilReady`、`AdditionalConsumedItems`、`OutputRules`）—— 内容资产 xnb，离线不可读（§2.4）。
* **U2** `Data\Machines` 的键形式（`"Furnace"`？`"(BC)114"`？）—— 运行时打印 keys 钉死。
* **U3** `Object.lastInputItem` / `lastOutputRuleId` 的可见性 —— 反射 dump 未覆盖。
* **U4** `tryToPlaceItem` 的像素坐标约定（我按 `tile*64+32` 写；游戏自身调用点传的是 `lastClick` 像素，未逐条验）。
* **U5** `Farmer.couldInventoryAcceptThisItem` 可见性 —— 未定，§3.1 改用手写槽位自检规避。
* **U6** `pressActionButton` 输入门的精确判据（`wasMouseVisibleThisFrame`/`didPlayerJustLeftClick`）—— 只有 0.7.19 侧证，未逐条 dump。
* **U7** 熔炉一炉的分钟数（wiki 说 30 分钟；**未从游戏数据证实**，等 U1）。
* **U8** 熔炉物品 id `(BC)114` 的权威来源 —— 来自 `docs\_run10-material-scan.md` 的存档扫描，未经 IL 交叉。

## 7. 证据文件与复核命令

| 文件 | 内容 |
|---|---|
| `scratch/t211-api-out.txt` | 反射 dump（CraftingRecipe / Object / Farmer / Game1 / GameLocation / Utility / CraftingPage / MachineData 全家族） |
| `scratch/il-mc-1.txt` | `CraftingRecipe|*` + `FIND|Craft`（InitShared 在 :1409 附近） |
| `scratch/il-mc-2.txt` | `performObjectDropInAction`(:2) / `checkForAction`(:316) / `placementAction`(:831) |
| `scratch/il-mc-3.txt` | `consumeIngredients`(:2) / `createItem`(:154) / `doesFarmerHaveIngredientsInInventory`(:189) / `clickCraftingRecipe`(:241) / `DataLoader`(:712,:719) |
| `scratch/il-mc-4.txt` | `PlaceInMachine`(:2) / `OutputMachine`(:257) / `GetMachineData`(:468) / `tryToPlaceItem`(:1374) / `reduceActiveItemByOne`(:1548) |
| `scratch/il-mc-5.txt` | `CheckForActionOnMachine`(:2) / `CheckForActionOnFeedHopper`(:287) |
| `scratch/il-mc-6.txt` | `ConsumeInventoryItem`(:17) + FIND 批次 |
| `scratch/il-hv-1.txt:503-576` | `GameLocation.checkAction` 的投放顺序 |
| `docs\_il-plant-consume.md` | 放置/扣物品的既有定案（`pressActionButton` 偏移表） |

```
tools\il-probe\bin\Release\Probe26.exe "<游戏目录>" "StardewValley.Object|PlaceInMachine" "StardewValley.Object|performObjectDropInAction" "StardewValley.Utility|tryToPlaceItem"
```
（产物是 UTF-16LE：用 `scratch\_t204_conv.py <src> <dst>` 转 UTF-8 再读，`tools\_tmp_conv.py` 对无 BOM 转储会报错）

## 8. 相对旧稿/卡面的修正

1. 卡面写 `CraftingRecipe.Craft(Carmer, int)` —— **1.6.15 不存在**；等效能力 = `createItem()` + `consumeIngredients()`。
2. 卡面问 `readyForHarvest()` 是方法还是属性 —— **都不是**：是 `NetBool` 字段（`.Value`）；`MinutesUntilReady` 才是 int 属性。
3. 投料输入是 `CurrentItem`（快捷栏选中项），不是 `ActiveObject`。
4. `performObjectDropInAction` 的 `returnFalseIfItemConsumed` 让**成功时返回 false** —— 返回值语义反向。
5. `Utility.tryToPlaceItem` 对非家具放置失败也返回 `true` —— 返回值不可信。
6. 机器数值全部在内容资产里，**离线拿不到**；且 run10 熔炉配方尚未学会（硬阻塞）。
