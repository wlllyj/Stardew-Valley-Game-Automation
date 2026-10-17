# IL 取证 · 熔炉（Furnace 114）配方由谁授予（Stardew Valley 1.6.15）— **WIP / 暂停点**

> **状态：未定案。** 已定案的是**四条授予路径**（下面 §1 全部有 IL 行号）；未定案的是
> **本存档为什么没有 Furnace、该走哪条恢复**。按 Lead 暂停指令（m09218），本文件在末尾
> §7「暂停点」写清已查/已排除/下一步，不声明 completed。
>
> 只读取证：不碰 `brain/`、`mod/`、`tools/`、`tests/`；不启游戏、不动桥、不改存档。
> 探针：`tools\il-probe\bin\Release\Probe26.exe`（IL）、`scratch/_t211_api/`（反射）。
> 所有 IL dump 转 UTF-8 用 `scratch/_t204_conv.py`（`tools/_tmp_conv.py` 对无 BOM 的转储会报错）。

## §0 三句话结论（对应 Lead 三问）

1. **「Furnace 配方该由谁授予」的最佳假设（强度：中）**：它是**技能等级条件配方**，本应由
   `Farmer.AddMissedMailAndRecipes()` 在**每次 `LevelUpMenu` 构造时**补发（IL 已证）；
   本存档没有，最可能是**升级弹窗在自动化期间从未被构造**（`Game1.showEndOfNightStuff` 的
   `endOfNightMenus` 菜单链被 `dismiss_modal` 提前掐断 ⇒ 菜单 ctor 没跑）或**技能是脚本直接写进存档**。
   并列假设：由 **`Data/TriggerActions` 触发器动作**授予（`Triggers.TriggerActionManager` 存在，
   条件可能依赖矿井进度 —— 本存档 `deepestMineLevel=0` 从没下过矿）。
2. **`Farmer.LevelUp(Int32)` 不存在**（卡面假设过时）；`player.craftingRecipes` 的写入点已证两处：
   **`Farmer.AddMissedMailAndRecipes()`**（cooking/crafting 两个 `TryAdd`）与 **`LevelUpMenu.update`**
   的环（`TryAdd`）；`LevelUpMenu..ctor(skill, level)` 自己的环**只写 `newCraftingRecipes`（显示用），
   不写玩家字典**。
3. **下次恢复的第一件具体动作**：`Probe26.exe "<游戏目录>" "StardewValley.Triggers.TriggerActionManager|*"`
   （+ `"StardewValley.DataLoader|TriggerActions"`），在 IL 里找动作处理器并在运行时 dump
   `Data\TriggerActions` 中含 `Furnace` 的条目；同时做**一次运行时探针**：调
   `Game1.player.AddMissedMailAndRecipes()` 后查 `craftingRecipes.ContainsKey("Furnace")`
   —— 这一条能一锤定音「条件是不是技能等级」。

## §1 四条授予路径（已定案）

### 1.1 `Farmer.AddMissedMailAndRecipes()` —— 技能等级配方 + 4 封特例邮件

证据：`scratch/t212-il-4-u8.txt:462-620`（方法全文）。

* 烹饪：`foreach (CraftingRecipe.cookingRecipes)` →
  `CraftingRecipe.TryParseLevelRequirement(key, value, isCooking:true, out skill, out level, logErrors:true)`；
  成功且 `GetUnmodifiedSkillLevel(skill) >= level` ⇒ `cookingRecipes.TryAdd(key, 0)`，并置
  `cookedFired = true`（IL_0000-005B）。
* 合成：同上但 `isCooking:false` ⇒ `craftingRecipes.TryAdd(key, 0)`（IL_006C-00C6）。
* 邮件兜底（与 Furnace 无关）：`robinKitchenLetter`（仅当 cookedFired 且未收）、
  `marnieAutoGrabber`（`farmingLevel >= 10`）、`JunimoKart`（`completedJunimoKart > 0`）、
  `Beat_PK`（`completedPrairieKing > 0`）（IL_00D6-01CD）。
* **调用者**（`FIND|AddMissedMailAndRecipes`，`scratch/t212-il-3-u8.txt:1-4`）：
  `Game1.fixProblems()`、`AbigailGame.tick()`、`MineCart.EndCutscene()`、
  **`LevelUpMenu..ctor(Int32 skill, Int32 level)`**。

### 1.2 `Farmer.LearnDefaultRecipes()` —— 无条件配方，每日补

证据：`scratch/t212-il-2-u8.txt:163-242`。遍历静态表，若玩家未学且
`value.Split('/')[4] == "default"`（烹饪取 `[3]`）⇒ `Add(key, 0)`。
调用者（`scratch/t212-il-3-u8.txt:6-8`）：**`Farmer.dayupdate`**、`Farmer.farmerInit`、`Game1.fixProblems`。
⇒ **Furnace 不是 `default` 配方**（否则每天睡觉醒来就学到了）。

### 1.3 `LevelUpMenu..ctor(Int32 skill, Int32 level)` 的显示环 —— 只写菜单列表

证据：`scratch/t212-il-4-u8.txt:281-372`。对同一份静态表做
`TryParseLevelRequirement`，仅当 `skill == currentSkill && level == currentLevel` 时
`new CraftingRecipe(key, false)` 加入 `this.newCraftingRecipes` 并累加窗口高度。
**不写 `player.craftingRecipes`** —— 这一环只负责「本次升级解锁了哪些配方」的弹窗显示。

### 1.4 `LevelUpMenu.update(GameTime)` 的第二个授予环 —— 真的写玩家字典

证据：`scratch/t212-il-1-u8.txt:1281-2216`（方法范围），授予环在 `:2002-2059`。

* 方法开头：`if (!this.isActive) { this.exitThisMenu(true); return; }`（`:1287-1293`）
  ⇒ 菜单不活跃时**直接退出，不跑任何授予**。
* 环：`foreach (CraftingRecipe.craftingRecipes)` → `Split('/')` →
  `StringHelpers.Get(parts, 4, "", true)` 取条件串 → `conditions.Contains(getSkillNameFromIndex(currentSkill))`
  且 `conditions.Contains(currentLevel.ToString())` ⇒ `new CraftingRecipe(key,false)` 加入
  `newCraftingRecipes` **且 `player.craftingRecipes.TryAdd(key, 0)`**（`:2051-2059`）。
* 该环受 `isActive` 与 `hasUpdatedProfessions` 控制，**对 Mining 1/2 级（非职业选择级）是否执行未定**
  （`isProfessionChooser = (level == 5 || level == 10)`，见 1.5）。

### 1.5 `isProfessionChooser` 语义（补上卡面没提的前提）

证据：`scratch/t212-il-4-u8.txt:196-201`：`isProfessionChooser = (level == 5 || level == 10)`。
⇒ 只有 5/10 级才是「职业二选一」界面；1-4 级只是普通升级提示。

### 1.6 触发器动作系统（1.6 的新蓝图分发通道）

证据：`scratch/t212-il-5-u8.txt:73`：`FIND|TriggerActions` = 1 命中
`StardewValley.Triggers.TriggerActionManager.GetActionsByTrigger()` → `StardewValley.DataLoader.TriggerActions`。
`FIND|AddCraftingRecipe` = **0 命中** —— 但 1.6 的触发器动作名是 **`ldstr` 字面量分派**
（`String.op_Equality` 比较后 switch），**`FIND` 原理上只能按方法名匹配，看不到字符串**
⇒ **0 命中不是"不存在"的证据**（这是本项目踩过的老坑）。触发器动作里极可能有
`AddCraftingRecipe`/`SendMail` 这类条目。

## §2 已排除 / 已证伪（4 条）

1. **「我们关掉升级弹窗 ⇒ 配方丢失」【就 LevelUpMenu 路径而言证伪】**：授予发生在
   `LevelUpMenu..ctor` 里对 `AddMissedMailAndRecipes()` 的调用（IL_01A4，`scratch/t212-il-4-u8.txt:230`），
   **构造即执行**，与菜单是否被显示/关闭/被 `dismiss_modal` 关闭无关。真正重要的前提是
   「LevelUpMenu 到底有没有被构造过」。
2. **「`AddMissedMailAndRecipes` 一定能补 Furnace」【未定，取决于条件串】**：它只认
   `<技能名> <等级>`（`TryParseLevelRequirement` 支持 farming/fishing/mining/combat/foraging/luck 六种，
   大小写不敏感；格式=空格分隔，证据 `scratch/t212-il-3-u8.txt:11-179`）。`default` 归 1.2 管；
   其它形式（邮件蓝图/触发器动作）两条都不管。
3. **「Furnace 曾被我们弄丢」【无证据】**：本存档 `mailReceived` 5 条、`mailbox` 26 条
   **都没有 furnace 相关邮件**，整份存档 XML 里 `Furnace`/`furnace` 关键字 **0 命中**
   （只读扫描 `scratch/_lead_save_mail.py`）⇒ 蓝图邮件**从未寄出**，谈不上丢失。
4. **卡面两条假设过时**：`Farmer.LevelUp(Int32)` **不存在**（`FIND` 探针报「未找到」）；
   `FIND|ApplyTriggerActions` **0 命中**（实际类型是 `StardewValley.Triggers.TriggerActionManager`）。

## §3 本存档真值（只读，存档 4,417,241 B）

来源：`scratch/_lead_save_mail.py`（只读正则解析存档 XML）＋ `docs/_run10-material-scan.md`。

* `mailReceived`（5）：`button_tut_1`、`button_tut_2`、`geodeFound`、`BackpackTip`、`sawQiPlane`
* `mailbox`（26）：`spring_2_1`、`landslideDone`、`passedOut2 48`、`spring_11_1`、`spring_12`、
  `spring_15_1`、`fertilizers`、`spring_19_1`、`spring_23`、`robinWell`、`summer_3_1`、
  `pierreBackpack`、`summer_10`、`summer_14_1`、`GreenRainGus`、`summer_20_1`、`summer_25_1`、
  `summer_28`、`fall_3_1`、`fall_8_1`、`fall_9`、`passedOut3_NotBilled 0`、`fall_15`、
  `passedOut3_Billed 279`、`fall_19_1`、`passedOut3_Billed 251`
  —— **没有 Clint 的熔炉信**
* `craftingRecipes`（19）：Campfire、Cobblestone Path、Gravel Path、Wood Path、Text Sign、
  Stone Sign、Wood Sign、Torch、Chest、Gate、Wood Fence、Cherry Bomb、Wild Seeds (Sp)、
  Field Snack、Scarecrow、Basic Fertilizer、Stone Fence、Mayonnaise Machine、Sprinkler
  —— **无 Furnace**
* `cookingRecipes`（1）：Fried Egg
* 关键字命中：`Furnace` **0**、`furnace` **0**、`Clint` 8、`114` 46
* 其它真值（task-209/run10）：mining xp 279 = **1 级**、farming 2、foraging 1、
  `deepestMineLevel = 0`（**从没下过矿**）、钱 2519g、背包 12/12 满。

## §4 最佳假设与证据强度

* **假设 A（主；强度：中）**——Furnace 是**技能等级条件**配方，本应被
  `AddMissedMailAndRecipes()` 补发；本存档没有，是因为**升级弹窗从未构造**（自动化把
  `Game1.showEndOfNightStuff` 的日终菜单链提前关掉 ⇒ 没有 `LevelUpMenu..ctor` ⇒ 没补），
  或**技能是脚本直接写进存档的**（没有升级过程）。
  *判据*：运行时调一次 `AddMissedMailAndRecipes()` 后 `craftingRecipes` 是否出现 Furnace。
* **假设 B（并列；强度：中）**——Furnace 由 **`Data/TriggerActions`** 的触发器动作授予
  （1.6 蓝图分发大量走这条路），条件可能依赖矿井进度（`deepestMineLevel=0` ⇒ 从未触发）。
  *判据*：`TriggerActionManager` 的动作处理器里是否有 `AddCraftingRecipe`/`SendMail`；运行时 dump
  `Data\TriggerActions` 里带 `Furnace` 的条目。
* **假设 C（弱）**——Furnace 蓝图在 Clint 商店/事件授予：存档 mail 两表都无痕迹，未见证据。

## §5 恢复方案（按优先级）

* **R1（先做，零风险）**：调用 `Game1.player.AddMissedMailAndRecipes()`
  （public 或反射；Probe211 反射表里尚未列它，下一步补一次反射确认可见性），随后观测
  `player.craftingRecipes` 是否出现 Furnace ⇒ 直接判定假设 A。
* **R2**：若 R1 失败 ⇒ 走触发器通道：找 `TriggerActionManager` 的「手动执行一个动作」入口
  （先确认 `GetActionsByTrigger` 之外是否有 `ApplyAction(s)`/`TryRunAction`），动作名与条件在
  运行时 dump `Data\TriggerActions` 钉死后再执行。
* **R3（不推荐，需标注）**：直接 `player.craftingRecipes["Furnace"] = 0` —— 这是**改存档式作弊**，
  违背「观测差分、不造假」路线；只有在确认是游戏 bug 导致蓝图丢失时作为最后手段。
* ⚠ **不知道 Furnace 的条件串就分不清 A/B**；条件串在打包的
  `Content\Data\CraftingRecipes.xnb`（`DataLoader.CraftingRecipes` →
  `Game1.content.Load<Dictionary<string,string>>("Data\CraftingRecipes")`，见
  `docs/_il-machine-chain.md` §2.4）—— 离线不可读（本仓库没有 xnb 解包器）。

## §6 对 task-205 / task-210 的影响

* **「熔炉配方已学会」是机器链的硬前置**：task-210 的 `craft_item` 必须先回答
  `player.craftingRecipes.ContainsKey("Furnace")`，否则如实返回 `recipe_unknown`（不许硬造）。
* 观测契约建议：Mod 把 `craftingRecipes` 的 key 列表（或至少 `furnaceRecipeKnown` 布尔）
  暴露进观测，让脑侧不靠猜；升级链（task-205）在材料到位前不依赖此项。

## §7 暂停点（Lead 要求）

**已 dump 并转码的证据文件**

| 文件 | 行数/大小 | 内容 |
|---|---|---|
| `scratch/t212-il-1-u8.txt` | 5432 行 | `LevelUpMenu` 全部方法（含 `update(GameTime)` 授予环 `:2002-2059`）+ `Farmer.gainExperience` |
| `scratch/t212-il-2-u8.txt` | 5594 行 | `AddMissedMailAndRecipes`、`LearnDefaultRecipes`、`gainExperience`、`LetterViewerMenu` 全方法 |
| `scratch/t212-il-3-u8.txt` | 180 行 | `FIND|AddMissedMailAndRecipes`(4) / `FIND|LearnDefaultRecipes`(3) + `TryParseLevelRequirement` IL |
| `scratch/t212-il-4-u8.txt` | 629 行 | `LevelUpMenu..ctor()` / `..ctor(Int32,Int32)`（含 IL_01A4 `AddMissedMailAndRecipes`、显示环、`isProfessionChooser`）+ `AddMissedMailAndRecipes` 全文 |
| `scratch/t212-il-5-u8.txt` | 74 行 | `FIND|addMailForTomorrow`（70 个调用方，逐个看过：没有「Mining 1 → 寄熔炉信」这种调用方）、`FIND|AddCraftingRecipe`(0)、`FIND|TriggerActions`(1→`TriggerActionManager.GetActionsByTrigger`) |
| `scratch/t212-api-out*.txt` | — | 反射：`Farmer` 成员/`CraftingRecipe`/`LevelUpMenu` 等可见性 |

**已排除的假设**：见 §2 四条（关框丢配方 / AddMissed 必补 / 曾丢后无 / 卡面两处方法名）。

**下次恢复的第一件动作**：
1. `Probe26.exe "<游戏目录>" "StardewValley.Triggers.TriggerActionManager|*" "StardewValley.DataLoader|TriggerActions"`；
   在 IL 里找动作名分派（`ldstr "AddCraftingRecipe"` 等）与 `craftingRecipes` 的写入点。
2. 反射补 `Farmer.AddMissedMailAndRecipes` / `GetUnmodifiedSkillLevel` / `craftingRecipes` 的可见性。
3. 真机/存档副本做 R1 探针（调 `AddMissedMailAndRecipes` → 观测 Furnace 是否出现），一次定 A/B。

## §8 复核命令

```pwsh
$py="C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$gd="D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley"
$exe="tools\il-probe\bin\Release\Probe26.exe"
& $exe $gd "StardewValley.Menus.LevelUpMenu|.ctor" "StardewValley.Farmer|AddMissedMailAndRecipes" "FIND|GetUnmodifiedSkillLevel" > scratch\t212-il-4.txt
& $py scratch\_t204_conv.py scratch\t212-il-4.txt scratch\t212-il-4-u8.txt
& $py scratch\_lead_save_mail.py   # 只读：mailReceived / mailbox / craftingRecipes / cookingRecipes
```
