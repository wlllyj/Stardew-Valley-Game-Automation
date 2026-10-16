# task-155 设计草稿：清障元数据 + 工具等级/升级状态（0.7.32 第一张）

> 状态：**方案草稿**（run9d/run10 期间冻结窗口内写，不改任何生产文件、不进生产 import 路径）。
> 依据：`docs/_il-tool-upgrade.md` §3/§6/§7（task-153 已证）+ 板面 task-155 卡面 + 下游卡 task-20/141/142。
> 作者：dev-coder。**字段命名与顺序已由 Lead m13471 裁决定稿**（见 §8/§9），实现时照此写，不要再改名。

## 0. 一句话

现在的观测层**分不清**「这一堆大障碍要斧还是镐、要几级」和「我的工具是几级」，
于是脑侧只有两个坏结果：把巨石当斧头活白挥（`tool="axe"`），或整类 `clump` 直接认输。
本卡只做**观测如实**：补结构化 clump 元数据 + 四种工具的等级 + 升级在途状态；
判据、清障策略、升级链留给 141/142 与 task-20 的脑侧。

## 1. 现状与三处已证的错

| 位置 | 现状 | 错在哪 |
| --- | --- | --- |
| `mod/AgentFarm.Bridge/WorldSnapshot.cs:484` | `else if (tf is ResourceClump) { t.Kind = "clump"; t.Tool = "axe"; }` | 148/622/672/752+ 实际要**镐**（§7 表） |
| `mod/AgentFarm.Bridge/FarmScan.cs:339-346` | `if (tf is ResourceClump clump) { _ = clump; _acc.Stones++; }` | 树桩/大木头被算进 `stones`，「清空农场」分母混淆 |
| `mod/AgentFarm.Bridge/UseToolSkill.cs:432` | `case "clump": plan.Add("axe");` | 与上面同源，首选工具错；`:587` 的 `Done()`/分类同源 |

工具等级侧：`Contracts.cs:209-217` 的 `ToolsView` 只有 6 个 bool，唯一等级字段是
`Contracts.cs:324` 的洒水壶 `upgradeLevel`（`WorldSnapshot.cs:704` 填 `can.UpgradeLevel`）
⇒ 斧/镐/锄是几级**根本读不到**；`Farmer.toolBeingUpgraded` / `daysLeftForToolUpgrade`
也完全没进观测（`docs/_il-tool-upgrade.md` §6 的「升级链完全不可观测」）。

## 2. JSON 契约（本卡要落地的字段）

命名原则：**一个事实只有一个名字**；未知一律 `null`，**不许猜**（禁"默认 0/默认 axe"）。

### 2.1 逐格（`tiles[]`，`detail=full`）— `Contracts.TileView`

```
clumpIndex   : int|null      // ResourceClump.parentSheetIndex.Value（600/602/672/148/622/752…）
clumpWidth   : int|null      // ResourceClump.width.Value（1.6 为 public NetInt）
clumpHeight  : int|null      // ResourceClump.height.Value
clumpHealth  : float|null    // ResourceClump.health.Value（public NetFloat，诊断/进度用）
clumpKind    : string        // 固定取值 stump/log/boulder/rockPile/greenRain/unknown
                             // `unknown` 必须**显式出现**（未知索引），绝不许静默并进 stones
clumpTarget  : { tool:"axe"|"pickaxe", minLevel:int } | null   // 由 clumpIndex 按 §3 推导；未知 ⇒ null
tool         : string        // 仍保留，但 ResourceClump 分支必须按 clumpTarget.tool 写；未知 ⇒ "none"
toolOk       : bool|null     // 当前玩家这把工具的 UpgradeLevel 是否 ≥ clumpTarget.minLevel
```

- `toolOk` 放 Mod 侧算（Mod 手上就有 `Game1.player` 与工具），脑侧不必自己配表；
  `null` 表示**判不了**（无该工具 / 等级读不到 / clumpTarget 未知）——与 `false` 语义不同。
- `clumpTarget == null`（未知索引）时**且** `tool = "none"`、`toolOk = null`，Mod 记一次
  `warn`（**按索引去重**，不是每格一条，避免刷日志）。

### 2.2 全农场（`farm`）— `Contracts.FarmView`

新增按种类计数（均 `int`，与 `dryTiles` 同一次扫描产出）：

```
stumps       : int   // 600
logs         : int   // 602
boulders     : int   // 672
rockPiles    : int   // 148 / 622
greenRain    : int   // 752+（绿雨那支；索引集合未定，见 §7）
clumpsTotal  : int   // 以上之和 + 未知索引
```

`stones`（`Contracts.cs:580`）**语义收窄**为真正的石类：不再包含 `ResourceClump`。
⚠️ 这会让 `stones` 相对旧账本**变小**（树桩/大木头被移走）⇒ 交付说明里必须点名，
run A/B 对照若引用 `stones` 需按新口径重算（与 task-50 改 `DryCrops` 口径同一类风险）。

### 2.3 工具与升级状态 — `Contracts.ToolsView` / `PlayerView`

```
tools[]               : [{ id, name, kind:"axe"|"pickaxe"|"hoe"|"can"|"pan"|"other",
                          upgradeLevel:int, indexOfMenuItemView:int|null,
                          isEquipped:bool, stack:int }]
toolBeingUpgraded     : { id, name, kind, upgradeLevel } | null   // Farmer.toolBeingUpgraded.Value
toolUpgradeDaysLeft   : int|null                                   // Farmer.daysLeftForToolUpgrade.Value
toolUpgradeNotice     : bool|null                                  // hasReceivedToolUpgradeMessageYet
```

- 四种工具（`Axe`/`Pickaxe`/`Hoe`/`WateringCan`）的 `upgradeLevel` **都写**（现状只写洒水壶）；
  `ToolsView` 的 6 个 bool **原样保留**（加字段不改语义，老读法不破）。
- `kind` 按真实类型写（`is Tool` 的 `GetType().Name` 判定），不写 `upgradeLevel` 到 `other` 上。
- `pan`（淘金盘）1.6 也是 `Tool`；没有就 `tools[]` 里不出现（`present` 语义由"在不在数组里"承担）。

## 3. clump 推导表（照抄 §7，别重新探）

| `clumpIndex` | 工具 | 最低 `upgradeLevel` | 血量 | `clumpKind`（**推断名，可改**） |
| --- | --- | --- | --- | --- |
| 600 | axe | 1 | 10 | `stump` |
| 602 | axe | 2 | 20 | `log` |
| 672 | pickaxe | 2 | 10 | `boulder` |
| 148 / 622 | pickaxe | 3 | 20 | `rockPile` |
| 752+ | pickaxe | **无等级检查** ⇒ `minLevel: 0` | 8 | `greenRain`（索引集合未定，见 §7-U3） |
| 其它 | **null（不许猜）** | null | 读到的血量照写 | `unknown` |

`minLevel: 0` 与 `null` 的区别：`0` = 「已证无门槛」，`null` = 「不知道」⇒ brain 侧
只有 `minLevel == 0` 才允许直接动手，`null` 一律当"判不了"。

## 4. 逐文件改动清单（实现时照此做）

1. `mod/AgentFarm.Bridge/Contracts.cs`
   - `TileView` 加 §2.1 七项；`FarmView` 加 §2.2 六项；`ToolsView` 加 `tools[]`；
     `PlayerView` 加 §2.3 三项。
   - 所有新字段都带 XML doc（写清「null = 判不了」的语义），供离线自检脚本静态核对。
2. `mod/AgentFarm.Bridge/WorldSnapshot.cs`
   - `:484` 的 `ResourceClump` 分支改成调用一个新的私有 helper
     `FillClumpMeta(TileView t, ResourceClump clump, Farmer who)`：填 index/width/height/health、
     推导 `clumpTarget`/`clumpKind`、按 `clumpTarget.tool` 写 `t.Tool`、算 `toolOk`；
     未知索引 ⇒ `t.Tool = "none"` + 去重 warn。
   - `PlayerView` 填充处补 `tools[]`/`toolBeingUpgraded`/`toolUpgradeDaysLeft`/`toolUpgradeNotice`
     （等级取 `Tool.UpgradeLevel`；在途工具取 `Game1.player.toolBeingUpgraded.Value`）。
3. `mod/AgentFarm.Bridge/FarmScan.cs`
   - `:339-346`：`ResourceClump` 按 `clumpIndex` 分流到 `Stumps/Logs/Boulders/RockPiles/GreenRain`
     与 `ClumpsTotal`，**不再** `Stones++`；`clumpIndex` 读不到 ⇒ 只进 `ClumpsTotal`（+去重 warn）。
   - 保证与 `dryTiles` 同一次扫描、同一个 `scanSeq`（task-107 的教训：计数与列表必须同源）。
4. `mod/AgentFarm.Bridge/UseToolSkill.cs`
   - `:432` 的 `case "clump"` 改成：先看观测给的 `clumpTarget.tool`；
     读不到 ⇒ `precondition_failed` + 理由「clump 目标工具未知（clumpIndex=…）」；
     `toolOk == false` ⇒ **不发请求**、`skipped` + 理由「需要 axe≥2（当前 0）」；
     `toolOk == null` ⇒ 也当"判不了"处理（不挥）。
   - `:587` 的 `Done()`/分类不动（它只判"这格清干净没有"）。

## 5. 下游怎么吃（design only，不在本卡实现）

- **task-20（脑侧）**：`kind in ("clump","stump","log","boulder","rockPile","greenRain")` 且
  `toolOk == false` ⇒ `skipped` + `proven_inert`，理由写「工具等级不够（需要 axe≥2）」，
  **一个请求都不发**；`toolOk == true` 仍按现行 R2（整类跳过、不白挥）——直到有专项清障策略。
- **task-141（建议通道）**：`Brief` 的 `obstacles_by_tool` 直接由 `tiles[]` 聚合
  `{f"{tool}>={minLevel}": count}`（`minLevel==0` 归 `f"{tool}>=0"`）+ `farm` 的分类计数做交叉核对；
  工具瓶颈摘要用 `tools[].upgradeLevel` 与 `obstacles_by_tool` 相减得出"升到几级能清掉多少格"。
- **task-142（升级链）**：前置断言用 `toolBeingUpgraded == null` 且 `toolUpgradeDaysLeft == null`；
  买后判据用 `toolBeingUpgraded != null` + `daysLeft == 2` + 次日 `daysLeft` 减 1；
  §6 的 `shop`/`shopUpgradeOffer` 不属本卡（属 142 的 Mod 部分）。

## 6. 验收与自检

- `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ 0 警 0 错。
- `git show --stat` 越界零命中（只许 `mod/AgentFarm.Bridge/*.cs`）。
- 仓库**没有 C# 测试工程** ⇒ 用 `scratch/` 里的**离线静态自检脚本**核对：
  ①`Contracts.cs` 里 §2 的 JSON 名逐一存在；②`WorldSnapshot.cs`/`FarmScan.cs` 里
  `ResourceClump` 分支不再出现字面量 `"axe"`（除推导表集中处）；③去重 warn 只出现一处实现。
- 只能真机验的部分（写进交付说明）：`clumpIndex`/`clumpHealth` 的实际取值、
  `tools[].upgradeLevel` 与 `toolBeingUpgraded` 在真存档里的形态、`toolOk` 是否符合预期。

## 7. 未定项（照抄 §8，不许自己填）

- **U3**：`752+` 的 switch 跳转表索引集合未定 ⇒ `greenRain` 一支的**精确索引**未定；
  `clumpKind` 的名字是按形状的**推断**（索引与门槛才是已证）。
- **U2**：每次挥动的具体伤害未定（不影响本卡，只影响 141 的"要挥几下"估算）。
- `ResourceClump.width/height/health` 的**确切成员类型**（`NetInt`/`NetFloat`）以 api-probe 复核为准；
  取不到就写 `null` + warn，**不许写 0**。

## 8. Lead 裁决（m13471，已定稿；原三问已关闭）

1. **重叠 = 按草稿建议办**：**task-155 吸收 task-20 的 Mod 部分**，一个事实一个名字，字段名以本文件为准；
   task-20 已改成「收窄：工具等级不足时的**脑侧行为** + 单测」且 `blocked_by task-155`。
   注意 task-20 的 writeScopes 里仍写着 mod 路径（advisory，Lead 未重写）——
   **`WorldSnapshot.cs`/`Contracts.cs`/`UseToolSkill.cs` 三个文件算 task-155 的写盘范围，task-20 里不许再动**。
   task-20 的脑侧终稿要求（实现时照做）：`toolOk == false` ⇒ `skipped`（**0 次 `use_tool`，不是 `failed`**）
   + 当天记账不再试；`clumpTarget` 缺失 ⇒ **不挥 + 无法判定**（不许默认斧头/默认 0）；
   无门槛类（weed/twig/stone/tree/grass）不受影响。
2. **`stones` 语义收窄，不留旧别名**；收窄后所有"石头还剩 N"的消费方都在 0.7.32 内一次性改掉
   （`docs/_analyze-farmcounts.md`/`_tool-matrix.md` 讲的是旧口径成因，不冲突）。
3. **字段形态定为终稿**：`tiles[]` 用扁平键，`farm` 用分 kind 计数；下游已核：
   **task-151**（全场清理）吃 `farm.<kind>` + "未分类障碍显式化"（run9c 残差 2 靠 `clumpIndex` 解）、不需要字典形态；
   **task-152**（钱的三分配）**不需要新 Mod 字段**（读 `player.money`/货架价/升级价）；
   **task-156**（只读基线）只要 `clumpIndex` 能解掉那 2 个未分类障碍。
   `clumpKind` 取值固定 `stump/log/boulder/rockPile/greenRain/unknown`，`unknown` 必须显式出现、不许静默并进 `stones`。

## 9. 0.7.32 顺序（等 run10 跑完的 GO）

`155 → 20（脑侧）→ 141 → 142 → 151 → 152`，中间按需插入 `154 → 110 → 109/101/107/117`。
141/142 依赖 155 的 `tools[].upgradeLevel` 与 `toolBeingUpgraded`；151 的 M5 三元组也吃 155。
