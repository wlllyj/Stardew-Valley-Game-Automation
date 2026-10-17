# run10 材料扫描：铜工具升级（2000g + 5 条铜锭）的材料可得性

> task-209 只读取证。**没做任何写入**：没真买成任何东西、没 `load_save`、没退游戏、没改存档。
> 环境：0.7.36 已装机读档；游戏 PID 10116；`health.hasSaveLoaded=true`；`worldSeq` 65→（扫描期间 65 起步）；第 1 年 **秋 19 日 15:10**（`weather=debris`）；玩家 `Farm(64,15)`；`money 2519g`；体力 270/270；背包 **12/12 行占满**（`inventoryCount` 是容量字段，判满要看 `player.inventory[]` 行数）；五件工具 `upgradeLevel 0`、`toolBeingUpgraded=null`、`daysLeft=0`。
> 只读产物（`scratch/` 下，按仓库约定 `scratch/*` 被 gitignore、仅 `*.py` 入库，JSON 留在磁盘）：`t210-blacksmith-stock.json`、`t210-upgrade-stock.json`、`t210-farm-objects.json`（149602 B）、`t210-machines-anywhere.json`、`t210-chest-contents.json`。

## §1 两个店的在售清单与价格（真机 dump）

**手法（安全）**：调 `BridgeClient.buy(item, shop=…)` 打一个**两店都不卖**的商品 `472`（Parsnip Seeds）⇒ `BuySkill.cs:195` 在 `item_not_sold` 时**提前 return**、永不进 `tryToPurchaseItem`；货架清单随失败回执返回，**键名是 `availableItems`**（`{Id=QualifiedItemId, Name, Price}`，按价格升序、最多 30 条）。每次 dump 前后各取一次 `observe` 断言 `money`/背包未变，dump 后 `dismiss_modal` 收店再打下一家。

| 店（ShopId） | 在售条目（原文 name / price） | 结论 |
|---|---|---|
| `Blacksmith`（Clint 普通店） | `Copper Ore 75g`、`Iron Ore 150g`、`Coal 150g`、`Gold Ore 400g` | **不卖铜锭(334)**（Clint 只卖矿与煤）；4 条，**远未触 30 条上限** |
| `ClintUpgrade`（升级店） | `Copper Axe 2000g`、`Copper Hoe 2000g`、`Copper Pickaxe 2000g`、`Copper Watering Can 2000g`、`Copper Trash Can 1000g` | 只出现**下一级=铜**的条目；价格与 `docs/_il-tool-upgrade.md` §2.3 的 0→1=2000g 一致（Trash Can 1000g）；5 条未截断 |

- **U2（`UpgradeLevel` 填目标还是当前）**：本机只能给**倾向**——条目名是 `Copper X`（=目标工具），且**没有**钢/金/铱条目出现（若"条目=当前等级"则会把 0 级的四个目标都列出来，与观测不符）⇒ 倾向"条目=目标等级=1"。但全部五件工具都是 0 级，两种读法都只预测出铜条目，**仍不能严格区分**。
- **材料要求读不到**：货架回执只有 `Id/Name/Price`，**没有 `TradeItem/TradeItemCount`** ⇒ "5 条铜锭"这一条**只能来自 IL 表**（`docs/_il-tool-upgrade.md` §2.3，vanilla `Tool.UpgradeLevel` 路径），**本机未验证**；下一张卡真机购买时用"钱差 2000g + 背包 `(O)334` 差 5"来落锤。
- **世界未变（三条独立证据）**：`money 2519→2519`；背包 12 行逐槽不变（无新增/减少）；`observe` 的 `worldSeq` 前后一致、`ui.activeMenu=null`（店已关）。两个 JSON 是这两次失败回执的原文。

## §2 农场/全地点的已放置机器（找熔炉 114 / 炭窑 12 / 箱子 130,232）

**① 真机 3×3 网格扫描**（`move_to` + 每锚点 `observe?detail=full`，9 个锚点 `(18,16)(40,16)(62,16)(18,36)(40,36)(62,36)(18,56)(40,56)(62,56)`，回程回 `(64,15)` ok）：**6 个锚点 `unreachable`**（"目标格不可通行（被建筑/水面/障碍占据）"或"A* 未算出路径"），只有 `(40,36)`、`(62,56)` 与起点 `(64,15)` 三处拿到了窗口；**三个窗口里 `kind=="object"` 的格数都是 0**，窗口 `kind` 只有 `dirt/tree/grass/weed/stone/twig`（⇒ 在 Mod 口径里，农场的石/枝/杂草是 `stone/twig/weed`，不是 `object`）。
**② 存档 XML 交叉验证**（`%APPDATA%\StardewValley\Saves\Wahaha_450799035\Wahaha_450799035`，4407033 B，`<SaveGame>` 下 87 个 location）：**Farm `<objects>` 共 689 条，全是杂物** —— `Weeds(678)×257`、`Weeds(679)×243`、`Stone(450)×63`、`Stone(343)×43`、`Twig(295)×42`、`Twig(294)×32`、`Weeds(786)×8`、`Artifact Spot(590)×1`；**机器/家具类 0 条** ⇒ **农场没有熔炉、没有炭窑、没有箱子**（与"`location.objects=689` 但窗口 `object=0`"完全一致）。
**③ 全地点机器扫描**：所有 location 的 objects/bigCraftables 里，机器只有 —— **FarmHouse 1 个 Chest @(3,7)**（内容：`Parsnip Seeds(472) ×15`，箱内无矿无锭无煤）、**Cellar ×8 各 33 个 Cask(163)**、Town 装饰 `Stone Junimo(55) @(57,16)`。**任何地点都没有 Furnace(114) / Charcoal Kiln(12)**。
**④ 其他真值**：玩家 `craftingRecipes` 19 条（Campfire / 各 Path / Text Sign / Stone Sign / Wood Sign / Torch / Chest / Gate / Wood Fence / Cherry Bomb / Wild Seeds (Sp) / Field Snack / Scarecrow / Basic Fertilizer / Stone Fence / Mayonnaise Machine / Sprinkler），**没有 `Furnace`**；`mining xp 279 = 1 级`、`foraging 1`、`farming 2`、`fishing 0`、`combat 0`；`deepestMineLevel=0`（从没下过矿）；`maxItems=12`；`totalMoneyEarned=4736`。
⇒ **结论：熔炉不存在（不是"没找到"，是存档里没有）**。所以"已有熔炉、买矿+煤直接烧"这条路不成立。

## §3 「5 条铜锭最省路径」候选 + 成本（含需要的新能力）

先把硬数字摆出来：**升级一次 = 2000g 手续费 + 5 条 `(O)334`**；**1 条锭 = 5 铜矿 + 1 煤**；**熔炉配方 = 20 铜矿 + 25 石**（配方本身本存档没有）。当前 `铜锭 0 / 铜矿 0 / 煤 0 / 石 3`，钱 **2519g**。

| 候选 | 需要什么 | 成本估算 | 判定 |
|---|---|---|---|
| **A 已有熔炉 ⇒ 买矿+煤烧** | 假设有熔炉 | 45 铜矿×75g = **3375g** + 5 煤×150g = **750g** | **不成立**：全存档/全地点无熔炉（§2③） |
| **B 先造熔炉，再烧** | ①**熔炉配方**（本存档缺失，见 §2④）②**造物能力**（Mod 无 `craft`）③**放置大件**（无）④**投料/收货**（无机器交互 skill） | 20 铜矿+25 石（造炉）+45 铜矿+5 煤（5 锭，其中 20 已算在造炉里则共 45 矿）⇒ 若全买 45×75+5×150+2000 = **6125g** | 需要**4 类新能力** + 配方缺口；且钱不够（缺口见下） |
| **C 去矿山挖矿，再烧** | ①**进矿/破矿/捡矿**能力（Mod 无 `MineShaft` 相关 skill；`deepestMineLevel=0`）②仍要 B 的熔炼链（矿洞出**矿/煤/晶洞**，不出锭） | 体力 + 镐磨损；能同时解决"矿/煤/石头"三样，长期最省 | 是**矿的唯一自采解**，但属新能力项目，不是"买一下" |
| **D 其他** | D1 **旅行商车**（随机卖铜锭，1–2 条/次，5 条要多次且看运气；`buy(shop="Traveler")` 能否远开【无法判定】）D2 钓鱼宝藏（fishing 0，无能力）D3 怪物掉落（无战斗能力） | 机会性、不可规划 | 仅备选，不能作为验收路径 |

**钱可行性（关键）**：升级手续费 2000g + 满买材料 4125g = **6125g**，现有 **2519g ⇒ 缺 3606g**。背包里可立即变现的只有 `Wheat×11`（≈25g/个 ⇒ ≈275g 量级）+ `Stone×3`(≈2g) + `Moss×2`(≈5g)，**远不够**；而农场清理产物（纤维/石/木/杂草）本来就是当前 run 的收入来源（本存档 `basicShipped`：纤维 211、石 163、木 100、黏土 29、煤 16…），**要靠几天收成慢慢补 3.6k g**。

**最小新增能力路径（建议，供 Lead 决策）**
1. **立"机器链"卡（Mod+brain）**：`craft_item`（`CraftingRecipe` + `player.craftingRecipes`）→ `place_object`（大件制造物落农场）→ `collect_machine`（Furnace/Cask 通用投料与收货）。这一步同时解锁熔炉、木桶、罐头瓶，是**目标 1（清干净农场）+ 目标 2** 的公共基础设施。
2. **铜矿来源二选一**：(a) **买**（先攒钱到 6125g，靠农场清理变现数天）；(b) **采矿能力**（矿山 warp + 破矿 + 捡矿）——既省钱又顺带产出矿/煤/晶洞，长期更符合"全自主"。
3. **短期不卡升级目标的做法**：先把 2000g 手续费之外的现金留给"锄头/十字镐升级"（工具升级收益最大），但**材料链不解决就一步都动不了** ⇒ 建议先立 1 的能力卡，再决定用买还是用挖。

**不确定项（诚实）**：① 5 条铜锭要求在真机购买时未验证（货架无 `TradeItem`，只有 IL 表）；② 熔炉配方缺失的**原因**（采矿等级已是 1 级，按公开资料该级应已解锁；本存档配方表里没有 `Furnace`）⇒ 【无法判定】（存档可能被脚本生成/改过，`deepestMineLevel=0` 也可疑）；③ `Traveler` shop 是否能被 `buy` 远程打开未测；④ 农场 6/9 锚点 `unreachable`，其余区域是否有机器**无法排除**（但存档 XML 是全场 689 条对象的真值，已覆盖全农场）。
