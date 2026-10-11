# 对象 → 正确工具 → 工具等级 对照表（task-10 A）

> 取证分析师 log-analyst 交付，2026-10-11。**只读取证**：本文所有结论都带定位（`文件:行号` 或 IL 偏移）。
> 目的：给 `brain/agentfarm/farmwork.py` 的门槛判断一张可直接查表用的真值表，并说明**哪些格子现在判不了、判不了该怎么办**。
> 证据分两层：**游戏侧**（`scratch/il-tools.txt`、`scratch/il-hoedirt.txt`，由 `tools/il-probe` 反汇编 1.6.15 的 `Stardew Valley.dll`）
> 与**桥侧**（`mod/AgentFarm.Bridge/*.cs`）。凡未查实的一律写「未定」。

---

## 0. 一句话结论

杂草/树枝/石头/草这四类**没有任何等级门槛**（真机 weed/twig/stone 各 1 次挥动即成，草是多刀），
**唯一有硬等级门槛的是 `ResourceClump`（大树桩/大木头/巨石）和灌木**；
但这四类里最要紧的 `ResourceClump` 恰恰是**观测判不了的**：观测里没有斧/镐/锄的 `upgradeLevel`
（只有水壶有），而 Mod 又把它一律写成 `tool="axe"`（`mod/AgentFarm.Bridge/WorldSnapshot.cs:438`）——
对巨石是错的。在补上等级字段之前，正确做法是**整类跳过并记账**，不要用 `auto` 去撞。

---

## 1. 观测产出侧：kind / tool 是谁写的（桥侧真值）

| 位置 | 判据 | 写出的 kind / tool |
|---|---|---|
| `mod/AgentFarm.Bridge/WorldSnapshot.cs:410` | `o.IsWeeds()` | `weed` / `hoe` |
| `WorldSnapshot.cs:411` | `o.IsTwig()` | `twig` / `axe` |
| `WorldSnapshot.cs:412` | `o.IsBreakableStone()` | `stone` / `pickaxe` |
| `WorldSnapshot.cs:435` | `tf is Grass` | `grass` / `scythe` |
| `WorldSnapshot.cs:436` | `tf is Tree` | `tree` / `axe` |
| `WorldSnapshot.cs:437` | `tf is FruitTree` | `fruitTree` / `axe` |
| `WorldSnapshot.cs:438` | `tf is ResourceClump` | `clump` / `axe` ← **见缺陷 D1** |
| `WorldSnapshot.cs:439` | `tf is HoeDirt` | `dirt` / `hoe` |
| `WorldSnapshot.cs:440` | `tf is Bush` | `bush` / `axe` |
| `WorldSnapshot.cs:449` | `hd.isWatered()` | `tiles[].watered` |
| `WorldSnapshot.cs:456` | `t.Ripe` | 有作物且熟 → `tool="none"`，否则 `tool="can"` |
| `WorldSnapshot.cs:461` | `t.Watered` | 浇过 → `tool="none"`，否则 `tool="can"` |
| `WorldSnapshot.cs:406` / `:432` | `kv.Value?.ItemId` / `tf.GetType().Name` | `tiles[].objId` / `tiles[].feature` |

**缺陷 D1（mod，建议交给 dev）**：`WorldSnapshot.cs:438` 把 `ResourceClump` 一律写成 `tool=axe`。
游戏侧同一类里既有斧头的活（600/602）也有镐的活（148/622/672/752…，见 §2），
`mod/AgentFarm.Bridge/UseToolSkill.cs:371-372` 的 `BuildPlan` 也照抄了 `clump → axe` ⇒ **对巨石首选斧头是错的**。
建议：`kind` 细化成 `stump` / `log` / `boulder`（按 `parentSheetIndex`），或直接把工具与等级判在 Mod 内（§4）。

**缺陷 D2（口径，非 bug）**：`mod/AgentFarm.Bridge/FarmScan.cs:243`（`Grass`）与 `:246`（`Bush`）**都计进 `farm.grass`**
⇒ `farm.grass` ≠ 「可割的草」，不能当 clear 的工作量指标；逐格真值只有 `tiles[].kind == "grass"`。

---

## 2. 对象 → 正确工具 → 等级门槛（游戏侧真值表）

工具取值沿用 `use_tool` 的枚举：`axe` / `pickaxe` / `hoe` / `scythe` / `can` / `auto`
（`mod/AgentFarm.Bridge/UseToolSkill.cs:385-417` 的 `FindToolSlot`）。

| 观测 `kind` | 游戏里的对象/特征 | 正确工具 | **等级门槛** | 一次挥动能成吗 | 证据（IL 行号 = `scratch/il-tools.txt`） |
|---|---|---|---|---|---|
| `weed` | `Object.IsWeeds()` | `hoe`（真机实证；游戏只要求 `t.isHeavyHitter()`） | **无** | 1 刀（`MinutesUntilReady -= 1`） | `:2988-3008`（杂草支）、`:2886-2955` |
| `twig` | `Object.IsTwig()` | **必须 `Axe`** | **无** | **1 刀必成**：置 `fragility=2`、掉 `(O)388` 木头、`gainExperience(2,1)`、`ret true` | `:3088-3180` |
| `stone` | `Object.IsBreakableStone()` | `pickaxe` | **无**（`damage = upgradeLevel+1`，只影响耐久扣减） | 小石头 1 刀（真机 511ms） | `:2886-2955` |
| `grass` | `tf is Grass` | `scythe`（Mod 建议值）；游戏侧实际接受**任意 `MeleeWeapon` 且 `type != 2`**（棍棒不行，剑/匕首可以） | **无** | **多刀**：`numberOfWeeds -= amount`；`(W)47`→1、`(W)53`→2、`(W)66`→4；`grassType==6` 有 50% 概率 `amount=0`（空挥） | `:4248-4348`（门闸 `:4248-4260`、数额 `:4286-4325`、蓝草 `:4326-4335`、扣减 `:4336-4343`） |
| `tree` | `tf is Tree` | `axe` | **无门槛**（等级只进伤害/木屑公式：`switch(level)`、`random.Next(level*2, level*4)`） | 多刀（扣 `health`） | `:913-945`、`:1140-1156` |
| `fruitTree` | `tf is FruitTree` | `axe` | **无门槛**（同上只进木屑公式） | 多刀 | `:1409-1420` |
| `bush` | `tf is Bush`（且 `isDestroyable()`） | `axe` | **`upgradeLevel >= 1`（铜斧）或 `size == 3`（大灌木）** | 多刀：`health -= health / upgradeLevel`（`size==3` 时 `-= 1`） | `:2431-2479`（门槛 `:2452-2461`） |
| `clump`（600） | `ResourceClump` id **600** | `axe` | **`upgradeLevel >= 1`（铜斧）**；不够则播 `axe` 音、弹 `ResourceClump.cs.13945` 对话、`ret false` | 多刀（扣 `health`） | 分派 `:32-59`；600 支 `:60-100` |
| `clump`（602） | id **602** | `axe` | **`upgradeLevel >= 2`（钢斧）**；否则对话 `ResourceClump.cs.13948` | 多刀 | `:101-141` |
| `clump`（148 / 622） | id **148**、**622** | `pickaxe` | **`upgradeLevel >= 3`（金镐）**；否则 `clubhit`+`clank`、对话 `ResourceClump.cs.13952` | 多刀 | `:142-181` |
| `clump`（672） | id **672** | `pickaxe` | **`upgradeLevel >= 2`（钢镐）**；否则对话 `ResourceClump.cs.13956` | 多刀 | `:194-233` |
| `clump`（752…） | id **752** 起的 switch 分支 | `pickaxe` | **无等级判据**（只 `isinst Pickaxe`） | `damage = 14`、`shakeTimer` | `:246-268` |
| `clump`（其它 id） | `IsGreenRainBush()` 为真 | 任意（草类口径） | 无 | 扣 `health`，播 `weed_cut`/`cut`、`damage = 36` | `:269-294` |
| `dirt`（有空地） | `HoeDirt`（无作物） | `hoe` | 无 | 1 次变耕地 | `WorldSnapshot.cs:439` |
| `dirt`（有作物，未熟/需水） | `HoeDirt.crop != null` | `can`（或 `harvest`） | 无 | — | `WorldSnapshot.cs:456/461` |
| `dirt`（有作物，`ripe`） | 同上 | `none`（`harvest`） | 无 | — | `WorldSnapshot.cs:456` |
| `object` | 机器/放置物等 | **不该动** | — | — | `brain/agentfarm/farmwork.py:53-59`（`SKIP_KINDS`） |

**石头支的两个例外（同一段 IL，`:2898-2930`、`:2963-2987`）**：
* `(O)12` / `(O)14` 这两个 id 在特定镐等级下 `damage = 0`（白敲）：`(id==12 && level==1)` 或 `((id==12||id==14) && level==0)` ⇒ 敲下去只播 `"crafting"` 音、耐久不减。**未定**：`(O)12` / `(O)14` 的语义名（未查 `Content/Data`）。
* `name == "Boulder"` 的对象：**需 `upgradeLevel >= 4`（铱镐）**且 `t is Pickaxe`，否则播 `hammer`、`ret false`（`:2963-2987`）。

**`ResourceClump` 通用尾段**（所有分支汇合）：`health -= damage`（`:295-301`），
`damage` 由 `:16-26` 按 `(upgradeLevel+1) * 系数` 算出，之后再看 `hasEnchantmentOfType[ShavingEnchantment]()` 追加掉落。
⇒ 大树桩/大木头/巨石都是「等级够就多刀砍掉、等级不够就一次都不掉血」。

---

## 3. 玩家等级从观测哪个字段读？——**答：现在读不到（Part A ③）**

| 想要的信息 | 观测里有吗 | 定位 |
|---|---|---|
| 农耕**技能**等级 | 有 | `Contracts.cs:146 player.farmingLevel` ← `WorldSnapshot.cs:258 FarmingLevel = SafeInt(() => p.FarmingLevel)` |
| 有没有斧/镐/锄/壶/武器 | 有（**只有布尔位**） | `Contracts.cs:203-211 ToolsView{hoe,axe,pickaxe,wateringCan,fishingRod,weapon}` ← `WorldSnapshot.cs:301-320`（只 `is` 判类型，**不读等级**） |
| 水壶等级 | 有 | `Contracts.cs:318 player.wateringCan.upgradeLevel` ← `WorldSnapshot.cs:655 v.UpgradeLevel = SafeInt(() => can.UpgradeLevel)` |
| **斧 / 镐 / 锄的 `upgradeLevel`** | **没有** | `grep -n "UpgradeLevel\|upgradeLevel" mod/AgentFarm.Bridge/` 只有上述 6 处命中 |

⇒ **斧头够不够铜、镐够不够金，脑在现有契约下判不了。** 两条出路（建议都做，优先级从高到低）：

1. **把判定留在 Mod（零脑改动、最准）**：`WorldSnapshot` 对 `ResourceClump`（以及将来的 `Bush`）直接输出
   `toolRequired`（`"axe"`/`"pickaxe"`）、`toolLevelRequired`（0/1/2/3/4）、`toolOk`（bool）。
   游戏侧的分派表就在 IL `:32-59`/`:141-233`/`:246-268`，照抄 10 行即可。
2. **补观测字段**：`player.tools` 增加 `axeLevel` / `pickaxeLevel` / `hoeLevel`
   （`SafeInt(() => axe.UpgradeLevel)`，与 `wateringCan` 同法），脑侧照 §2 的表自己判。

**临时口径（今天就能用）**：`clump` 一律 `skipped`（`farmwork.py:53-59` 已是如此），
原因写「资源堆需要工具等级，观测里没有等级字段」；**不要**退回 `use_tool(auto)` 用撞的方式探——
`BuildPlan` 对 clump 首选 `axe`（`UseToolSkill.cs:371-372`），对巨石必然白挥。

---

## 4. 判不出来时怎么办（Part A ④ 的规则）

沿用 `brain/agentfarm/farmwork.py` 已有的「先判后动」骨架（`:586-593`），把三条规则补进去：

* **R1 工具类型不对 / 没这件工具** → `skipped`，理由写清（现有：`tool_missing_reason`，`farmwork.py:588-593`）。
* **R2 等级门槛判不了** → `skipped` + `proven_inert`（今天不再碰），**绝不用 `auto` 去撞**。适用于全部 `clump`，以及 `bush`（`size != 3` 时需铜斧）。
* **R3 挥动有效性存疑时，先证明「这一刀真的挥出去了」，再判「挥不动」**：
  run1 的两格 grass 就是反例——6 次挥动、`UsingTool` 始终 false、世界纹丝不动，被判成「挥不动」，
  真实原因是 Mod 的入口对近战武器有输入门闸（见 `docs/_analyze-longrun-run1.md` 的 grass 三层根因；
  dev 侧已在 `UseToolSkill.cs:287-337 BeginUse()` 绕开）。若回执不能区分「没挥出去」与「挥了没变」，
  脑就会把「入口坏了」记成「这格干不动」，并进一步被 `_mark_blocked` 洗成后置条件成立。
* **R4 允许「一刀没变」不算完**：草是多刀特征（`numberOfWeeds`），蓝草（`grassType==6`）还有 50% 概率空挥
  （IL `:4326-4335`）⇒ 判据必须是「挥到上限」而不是「一刀没变就封格」。
  现有实现已符合（`MAX_CLEAR_SWINGS = 4`，`farmwork.py:64-67`、`:602-646`），且 `TILE_INERT_STATUSES`
  （`:71`）只在 Mod 明确说「这一格挥不动」时早停。
* **R5 封格记账不得改善后置条件**：`_mark_blocked` 与 `_leftover` 必须分开记账，
  否则「把失败格封掉」会让 `leftover` 变空 → `met=True` → 任务级 VERIFIED（run1 事件 14 的根因，task-9 已修）。

`KIND_TOOL`（`farmwork.py:94`）与 Mod 的 `BuildPlan`（`UseToolSkill.cs:359-374`）必须同源；
目前两处都把 `clump` 当 `axe`，改的时候一起改。

---

## 5. 未定项（U）

* **U1**：`ResourceClump` id **600/602/148/622/672/752…** 的语义名（大树桩/大木头/巨石？）——未查 `Content/Data`，本文只保证「工具类型与等级门槛」这半张表是 IL 真值。
* **U2**：`Bush.size` 的取值分布与来源（只有 `size == 3` 这条免等级通道是确定的）。
* **U3**：`(O)12` / `(O)14` 的语义名（见 §2 例外）。
* **U4**：`(W)47`（普通镰刀）的 `MeleeWeapon.type` 值 —— 打包在 `Content/Data/Weapons.xnb`，读不到；
  但 `Grass.performToolAction` 的门闸是 `type != 2`，而真机证明 `(W)47` 能割草 ⇒ 该值 ≠ 2 是**由游戏行为反推的**，非直接读出。
* **U5**：`FruitTree.performToolAction`（`:1373-2387`）与 `Grass` 段我只钉了等级/工具相关片段，未逐行读完（不影响本表结论）。
* **U6**：`scythe` 的 `FindToolSlot` 把**任意** `MeleeWeapon` 当镰刀（`UseToolSkill.cs:404`）⇒ 自动序列可能拿剑/匕首去割草（游戏侧确实允许，但会造成「用的不是镰刀」的账目歧义）。

---

## 6. 复核命令（只读）

```powershell
$env:PYTHONUTF8=1
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
# 1) 重放本文引用的 IL（如已有 scratch\il-tools.txt 可直接 grep，不必重跑）
& $py scratch\_probe_il.py scratch\il-tools.txt `
  "StardewValley.TerrainFeatures.ResourceClump|performToolAction" `
  "StardewValley.TerrainFeatures.Tree|performToolAction" `
  "StardewValley.TerrainFeatures.FruitTree|performToolAction" `
  "StardewValley.TerrainFeatures.Bush|performToolAction" `
  "StardewValley.Object|performToolAction" `
  "StardewValley.TerrainFeatures.Grass|performToolAction"
& $py scratch\_probe_il.py scratch\il-hoedirt.txt "StardewValley.TerrainFeatures.HoeDirt|isWatered"
# 2) 桥侧写 kind/tool 的位置
Select-String -Path mod\AgentFarm.Bridge\WorldSnapshot.cs -Pattern 't\.Kind = |t\.Tool = '
# 3) 观测里有没有工具等级
Select-String -Path mod\AgentFarm.Bridge\*.cs -Pattern 'UpgradeLevel|upgradeLevel'
```

关联文档：`docs/_analyze-longrun-run1.md`（grass 三层根因）、`docs/_analyze-sleep-fail.md`（回执不可信的先例）、
`docs/_analyze-farmcounts.md`（farm 聚合口径，本任务的 B 部分）。
