# Furnace 配方在 1.6.15 的合法授予路径（只读取证）— task-223

> 目的：回答「Furnace 配方到底由什么授予、我们为什么没有、怎么合法拿到」。
> 结论全部来自**离线只读**证据：`Content/*.xnb` 运行时反序列化（不启游戏）、`Stardew Valley.dll` 元数据/IL、存档 XML、wiki 数据文档。
> 旧稿 `docs/_il-furnace-recipe.md`（task-212 的 WIP）保留作历史，**本文件覆盖其结论**。

## §0 速览（五问五答）

| # | 问题 | 结论 |
|---|---|---|
| 1 | 配方串 `378 20 390 25/Home/13/true/l 2/` 各字段 | 材料 20 铜矿+25 石 / `Home` 是**无用占位** / 产出大件 13 / `true`=大件 / **解锁条件 `l 2`** / 显示名空（缺省用产物名）。`l 2` **不是技能条件、`2` 不是等级**——游戏只解析 `s <技能> <等级>` 与 `default`，其它一律当「由事件/其它方式解锁」 |
| 2 | 1.6.15 里 Furnace 由谁授予 | **农场事件 `Data/Events/Farm` 键 `992553/t 600 1130/n copperFound`**：Clint 过场，脚本里 **`/addCraftingRecipe Furnace/`** + `/addQuest 11/`。触发旗标 = 邮件 `copperFound`，由 `Farmer.OnItemReceived` 在玩家**真正收到铜矿**时写入（次日邮件） |
| 3 | 本存档差在哪 | 不是技能：`<copperFound xsi:nil="true"/>`（该统计从未 +1）、三个 mail 集合都无 `copperFound`、`deepestMineLevel=0`（从没下过矿）⇒ **从未真正获得过铜矿，旗标没被设过**。同存档 `s Mining 1` 的 Cherry Bomb 已学会 ⇒ 技能补发路径本身是好的 |
| 4 | Mod 能否合法触发 | **不能**直接写 `craftingRecipes`（造假），也不该直接执行事件脚本的 `addCraftingRecipe`。合法路径只有一条：**让游戏自己判定玩家真的收到铜矿** → 旗标 → 次晨 6:00–11:30 玩家进 Farm 时游戏自动演事件给配方。我们的 `goto_farm` 已满足「早上进 Farm」，唯一缺的是「合法得到铜矿」 |
| 5 | 5 个铜锭的替代来源 | Clint **不卖锭**；熔炼需要 Furnace ⇒ 合法闭环回到「先真采 1 个铜矿」。晶球/旅行商车/钓鱼宝箱/矿洞箱有几率给铜锭但不可控。**购买/钓鱼得到的铜矿是否也算** ⇒ **待 task-226 真机判定**（代码层看起来算，旧 wiki 说不算） |

## §1 配方串字段定案（运行时数据 + wiki 逐字段对照）

### 1.1 我们的实测数据（离线反序列化，未启游戏）

`scratch/_t223_xnb/`（C# 探针：`ContentManager` rooted at `<游戏目录>\Content` + 反射 `Load<object>`）
→ `scratch/t223-crafting.txt`（`Data/CraftingRecipes`，**150 条**）。关键原文：

```
[Wood Fence] = 388 2/Field/322/false/default/
[Stone Fence] = 390 2/Field/323/false/s Farming 2/
[Chest] = 388 50/Home/130/true/default/
[Scarecrow] = 388 50 382 1 771 20/Home/8/true/s Farming 1/
[Charcoal Kiln] = 388 20 334 2/Home/114/true/s Foraging 2/
[Furnace] = 378 20 390 25/Home/13/true/l 2/
[Heavy Furnace] = (BC)13 2 335 3 390 50/Home/HeavyFurnace/true/l 2/
[Anvil] = 335 50/Home/Anvil/true/l 2/
[Mini-Forge] = 852 5 335 10 336 10 337 5/Home/MiniForge/true/l 2/
[Wood Floor] = 388 1/Field/328/false/l 0/
```

解锁条件分布（同一份 dump 统计）：`s <技能> <等级>` **71 条**、`null` **53 条**、`l <数字>` **14 条**
（其中 Furnace/Heavy Furnace/Anvil/Mini-Forge 都是 `l 2`，10 条地板/小径是 `l 0`）、`default` 若干。

### 1.2 wiki 字段表（1.6.15 原文数据）

来源：<https://wiki.stardewvalley.net/Modding:Recipe_data>

| 索引 | 字段 | 例子（crafting） |
|---|---|---|
| 0 | Ingredients（`id 数量` 成对） | `378 20 390 25` |
| 1 | **(Unused)**（crafting 里写 `Home`/`Field`，游戏不读） | `Home` |
| 2 | Yield（产出 id + 可选数量） | `13` |
| 3 | Big craftable? | `true` |
| 4 | **Unlock conditions** | `l 2` |
| 5 | Display name（tokenized string，缺省取产物名） | （空） |

wiki 对「Unlock conditions」的合法取值（原文要点）：
- `f <NPC> <hearts>`：仅烹饪；
- `s <skill> <level>`：`Farming/Mining/Fishing/Foraging/Luck/Combat`，在升级菜单解锁；
- `default`：自动学会（日初补缺）；
- **`none` 或任何其它值 ⇒ 「必须由其它方式解锁，例如事件」**。

⇒ **`l 2` 命中最后一档**：它不是技能条件；`2` **没有等级语义**（同样出现在 `l 0` 的地板上）。
这也解释了为什么 `Farmer.AddMissedMailAndRecipes()`（只按 `s` 条件补）与 `Farmer.LearnDefaultRecipes()`（只补 `default`）都补不出 Furnace —— 见 §2.3 的 IL 交叉验证。

## §2 1.6.15 的合法授予点（数据原文 + IL）

### 2.1 事件：`Data/Events/Farm` 键 `992553/t 600 1130/n copperFound`

实测 dump：`scratch/t223-ev-Data_Events_Farm.txt`（`Data/Events/Farm`，27 条）。原文（节选，完整一行见文件）：

```
[992553/t 600 1130/n copperFound] = continue/64 15/farmer 64 16 2 Clint 64 18 0/skippable
  /pause 1500/speak Clint "Uh... Hi there. Good morning.#$b#I noticed that you've been
   breaking some rocks open and finding ore. That's good!"/...
  /speak Clint "Just so happens I had an extra set of blueprints lying around. Here, I want you to have them."
  /pause 800/itemAboveHead/playSound getNewSpecialItem/addCraftingRecipe Furnace
  /pause 3300/message "Learned how to craft a 'Furnace'"/...
  /addQuest 11/end
```

要点：
- **地点 = Farm**（`Data/Events/<LocationName>` 规则），**时间 `t 600 1130` = 6:00–11:30**；
- **前置 `n copperFound` = 邮件旗标 `copperFound`**（旧式前置条件；`n` 的确切别名语义见 §6 U1）；
- 脚本命令 **`addCraftingRecipe Furnace`** + **`addQuest 11`**（任务「Furnace」）。
  事件命令文档：<https://wiki.stardewvalley.net/Modding:Event_data>（`addCraftingRecipe <recipe>`：把配方加给玩家；`addQuest <quest ID>`）。

### 2.2 旗标怎么被设上：`Farmer.OnItemReceived` IL（`scratch/t223-onitemreceived-u8.txt`）

开头的两个早退（这两条决定了「什么算真正收到」）：

```
IL_0014: ldarg.0
IL_0015: call    Boolean get_IsLocalPlayer()
IL_001A: brtrue.s -> IL_001D        // 不是本地玩家 ⇒ 直接 ret
IL_001E: isinst   StardewValley.Object
...
IL_002E: ldarg.1
IL_002F: callvirt Boolean get_HasBeenInInventory()
IL_0034: brfalse.s -> IL_0037
IL_0036: ret                        // 物品"曾经进过背包" ⇒ 不再算新获得
```

铜矿分支（按 item id 分派的 `switch` 里，该 case 同时累加统计与写旗标）：

```
IL_0889: ldarg.0
IL_088A: ldfld    StardewValley.Stats stats
...
IL_0890: callvirt UInt32 get_CopperFound()
IL_0895: ldloc.0
IL_0896: ldfld    Int32 countAdded
IL_089B: add
IL_089C: callvirt Void set_CopperFound(UInt32)     // 统计 CopperFound += countAdded
IL_08A1: ldarg.0
IL_08A2: ldstr    "copperFound"
IL_08A7: call     Boolean hasOrWillReceiveMail(System.String)
IL_08AC: brtrue.s -> IL_0905                        // 已有该信（含今天的信袋）⇒ 不重复
IL_08AE: ldstr    "copperFound"
IL_08B3: ldc.i4.1
IL_08B4: ldc.i4.0
IL_08B5: call     Void addMailForTomorrow(System.String, Boolean, Boolean)
IL_08BA: br.s     -> IL_0905                        // 明天把 copperFound 信放进邮箱
```

`hasOrWillReceiveMail`（`scratch/t223-one-u8.txt`）= `mailReceived.Contains(id) || mailForTomorrow.Contains(id) || mailbox.Contains(id) || mailForTomorrow.Contains(id + "%&NL&%")`。
⇒ 旗标只会设一次，且**“明天”才进邮箱** ⇒ 事件最早在**收到铜矿的次日早上**触发（与 wiki 描述一致）。

谁会触发它（`scratch/t223-find-onitem-u8.txt`，`FIND|OnItemReceived` 11 个调用方法）：
`Farmer.addItemToInventory(Item,List)` / `(Item,Int32)` / `addItemToInventoryBool` / `Utility.addItemToInventory` / `eatHeldObject` 等；
而 `Debris.collect`、`Crop.harvest`、`GameLocation.checkAction`、`GameLocation.blacksmith` 等都经由 `addItemToInventory*` 入包
⇒ **凡是"把 (O)378 真的放进背包"的路径都会走到这里**（唯一的两个例外见上面的早退）。

### 2.3 为什么「技能升级补发」补不出 Furnace（IL 交叉验证）

- `CraftingRecipe.TryParseLevelRequirement(id, rawData, isCooking, out skill, out level, logErrors)`：
  取 `crafting` 的第 5 段（索引 4）/ `cooking` 的第 4 段（索引 3），按空白拆成 `<技能> <等级>`，
  技能名只认 `farming/fishing/mining/combat/foraging/luck`（大小写不敏感），**其它形态一律 false**
  （证据：`scratch/t212-il-3-u8.txt:11-179`；`l 2` 在这里解析失败）。
- `Farmer.AddMissedMailAndRecipes()`：两轮 `TryParseLevelRequirement` + `GetUnmodifiedSkillLevel(skill) >= level`
  ⇒ `craftingRecipes.TryAdd(key, 0)`；另有 4 封特例信补发（`scratch/t212-il-4-u8.txt:462-620`）。
- `Farmer.LearnDefaultRecipes()`：只补「解锁字段 == `default`」的条目（`scratch/t212-il-4-u8.txt:163-242`）。

⇒ `l 2` 既不被技能解析、也不是 `default` ⇒ **任何"补发"API 都不会给 Furnace**。这与 task-214 真机
`add_missed_recipes` 调用后计数不变（19/1/5）完全一致，也把 task-212 旧稿的「技能升级补发」假设正式证伪。

## §3 本存档差在哪（只读存档取证）

`scratch/_t223_save.py`（只读 XML）→ 关键读数：

| 项 | 值 | 说明 |
|---|---|---|
| `experiencePoints` | `730, 0, 167, 279, 0, 0` | 顺序 farming/fishing/foraging/**mining**/combat/luck ⇒ mining **279 xp**（1 级） |
| `Stats.copperFound` | **`<copperFound xsi:nil="true"/>`** | 该统计**从未 +1** ⇒ 从未走到 §2.2 的铜矿分支 |
| `mailReceived`(5) | button_tut_1 / button_tut_2 / **geodeFound** / BackpackTip / sawQiPlane | 无 `copperFound` |
| `mailbox`(27) / `mailForTomorrow`(0) | 均无 `copperFound` | 三个集合都没有 ⇒ 旗标从未设过 |
| `craftingRecipes`(19) | 无 Furnace；**有 Cherry Bomb(`s Mining 1`)、Scarecrow(`s Farming 1`)、Stone Fence(`s Farming 2`)** | 技能条件类配方**都在** ⇒ 技能补发链路正常，Furnace 缺的不是它 |
| `cookingRecipes`(1) | Fried Egg（`default`） | `default` 类也正常 |
| `deepestMineLevel` | **0** | 从未下过矿 |
| 背包 (O)378 / (O)334 | 存档文本 0 / 0 | 没铜矿也没铜锭 |

**结论**：差的不是技能等级（`l 2` 与技能无关；即便 mining 升到 10 级也不会因此解锁 Furnace），
而是**玩家从未真正获得过 1 个铜矿 ⇒ `copperFound` 旗标从未设过 ⇒ 事件 992553 从未满足前置**。
（另一条独立证据：同存档有 `geodeFound` 邮件且在矿洞外活动 77 天，说明游戏进度不低，纯粹是"没采过铜矿"。）

## §4 Mod 能否「合法」触发（推荐路径）

**不能**：
- 直接往 `Farmer.craftingRecipes` 写 `Furnace` = 改写玩家存档事实，属于造假（我们自己的验收判据就是观测差分，不能自己骗自己）；
- 直接调用事件脚本命令 `addCraftingRecipe` / 手工 `TryAdd` 同样等于伪造事件奖励；
- 调 `AddMissedMailAndRecipes()` 无效（§2.3）。

**可以（唯一合法路径）**：
1. 让玩家**真的收到** 1 个 (O)378 铜矿（走任何 `addItemToInventory*` 路径，见 §2.2）→ 游戏自动
   `stats.copperFound += 1`、`addMailForTomorrow("copperFound")`；
2. 次日 6:00–11:30，玩家**进入 Farm**（`Data/Events/Farm` 事件触发条件）→ 游戏自己演 Clint 过场 → 给配方 + 任务 11。
   我们的 `goto_farm` 每天早上的第一步就是进 Farm，**时间窗口通常满足** ⇒ Mod 侧不需要新增技能，
   只需要一条「合法拿到 1 个铜矿」的能力。

**「买到/钓到的铜矿算不算真的收到」——待 task-226 判定**：
- 代码层：`OnItemReceived` 只挡「非本地玩家」与 `HasBeenInInventory == true`。
  商店购买用 `GetSalableInstance()`，其 IL 就是 `getOne()`；`getOne()` = `GetOneNew()` + `GetOneCopyFrom(this)`，
  而 `GetOneCopyFrom` **把源物品的 `HasBeenInInventory` 复制过去**（`scratch/t223-one-u8.txt` IL_0035-003C、
  `scratch/t223-salable-u8.txt`）。
- ⇒ 若货架原型实例的 `HasBeenInInventory` 初值为 `false`，**购买铜矿在 1.6.15 里也会设旗标**（与旧 wiki「购买不触发」矛盾）；
  若为 `true` 则不设。**实测见 task-226**（买 1 铜矿 → 次日出门 → 查 `craftingRecipes`）。
  本报告不把这条写死。

## §5 5 个铜锭的替代来源（概率/成本级）

| 路径 | 可行性 | 说明 |
|---|---|---|
| 自己熔炼 | 需 Furnace | 闭环：Furnace 配方本身要 §2 的事件 |
| 找 Clint 买铜锭 | **无** | task-209 真机扫描：Clint 只卖铜矿 75g / 煤 150g，**不卖锭** |
| 旅行商车（Traveling Cart） | 概率 | 商品随机，铜锭只是可能项；不能作为 P0 |
| 钓鱼宝箱 / 矿洞木箱 | 概率 | 需要能钓鱼/下矿；同样不可控 |
| 晶球（Geode）破开 | 概率 | 我们已有 `geodeFound` 邮件、破过晶球；晶球可能出铜矿/铜锭 ⇒ **若目标是"设旗标"，晶球出的铜矿同样走 `addItemToInventory`，是合法路径**（需真机确认 RNG） |
| 回收机/其它机器 | 无 | 回收产物里没有铜锭 |

**建议顺序**（给 Lead 决策）：
1. **先做 task-226（买 1 铜矿 → 次日出门 → 查配方）**：若 PASS，则 Mod 只需「买矿」这条已有能力（`buy` 技能）即可解 P0；
2. 若 FAIL，则必须让 Mod 具备「真正采集铜矿」的能力（下矿/破晶球），这是新的能力缺口（mining 技能，任务量大）；
3. 不建议任何"直接写配方"的捷径。

## §6 未定 / 需要补的探针

- **U1**：事件前置 `n copperFound` 的确切语义。1.6 wiki 现行前置表里 `LocalMail`="已收到该信"，弃用别名表可见部分
  只有 `l`=NotLocalMail（未收到）；`n` 不在其中 ⇒ `n` 可能是「**信已排队/未读**」的旧别名。
  需要：`Stardew Valley.dll` 里事件前置解析器（`Event` 类）的 IL 或真机实验。**若 `n` 是"未收到"，则事件在信到达当天早上触发（时序刚好）；
  若 `n` 是"已收到"，则需等信读完。两者都不改变"先采铜矿"的结论。**
- **U2**：商店货架原型 `HasBeenInInventory` 初值（决定 U2/task-226 的购买路径是否触发）。
- **U3**：1.6.15 是否仍适用 wiki「购买/钓鱼得到的铜矿不触发」——待 task-226。
- **U4**：矿洞铜矿节点最低层数（wiki 常识 1–39 层；未在本卡取证）。
- **U5**：地板类 `l 0` 的真实授予点（Robin 商店/事件）——不影响本卡结论，仅记录同一字段的另一种"其它方式"。

## §7 证据文件与复核命令

**新产物（全部在 `scratch/`，只读离线）**
- `scratch/_t223_xnb/`（`T223Xnb.csproj`+`Program.cs`）：用 `ContentManager` 离线反序列化任意 `Content/Data/*.xnb`；
  用法：`dotnet scratch\_t223_xnb\bin\Release\net6.0\T223Xnb.dll "Data/CraftingRecipes" --out scratch\t223-crafting.txt`
- `scratch/_t223_meta/`（`T223Meta.csproj`+`Program.cs`）：用 `System.Reflection.Metadata` 扫 `ldstr` 字面量 → 定位
  「哪个方法引用了某字符串」（`FINDSTR|` 对 `ldstr` 恒 0 命中的正解）；
  用法：`dotnet scratch\_t223_meta\bin\Release\net6.0\T223Meta.dll "<游戏目录>\Stardew Valley.dll" copperFound`
- `scratch/t223-crafting.txt`（CraftingRecipes 150 条）/ `t223-mail.txt`（mail 179 条，**无 furnace 信**）/
  `t223-trigger.txt`（TriggerActions **31 条**，**无任何 AddCraftingRecipe**）/ `t223-ev-Data_Events_Farm.txt`（事件 992553）
- `scratch/t223-onitemreceived-u8.txt`、`t223-one-u8.txt`、`t223-salable-u8.txt`、`t223-find-onitem-u8.txt`（IL 与调用者）
- `scratch/_t223_save.py`（存档只读解析）

**复核命令**
```
python scratch\_t223_save.py
dotnet scratch\_t223_xnb\bin\Release\net6.0\T223Xnb.dll "Data/CraftingRecipes" --out scratch\t223-crafting.txt
dotnet scratch\_t223_meta\bin\Release\net6.0\T223Meta.dll "<游戏目录>\Stardew Valley.dll" copperFound
```

**外部来源**
- <https://wiki.stardewvalley.net/Modding:Recipe_data>（字段表 / 1.6.15 原始数据 / 解锁条件四档）
- <https://wiki.stardewvalley.net/Modding:Event_data>（事件资产路径 / 前置条件 / `addCraftingRecipe` 命令）
- <https://wiki.stardewvalley.net/Furnace>（"采集到首个铜矿后次日、6:00–11:30 走出农舍由 Clint 给蓝图"——按 Lead 转述引用；"购买/钓鱼不计"待 task-226）
