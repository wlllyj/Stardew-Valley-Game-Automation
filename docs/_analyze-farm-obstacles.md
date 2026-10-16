# 目标 1「把农场全部清理干净」清障基线量化（task-156）

> 取证分析师 log-analyst，2026-10-17。**只读**（本卡只写 `docs/` 与 `scratch/`）。
> 结论分【已证】（有文件行号/真机读数）、【推断】（有算术佐证）、【无法判定】（缺字段）。
> 原始取数脚本：`scratch/_t156_data.py`（`observe` / `shape` / `ledger` 三个模式），输出 `scratch/_t156_data.txt`。

---

## 0. 一句话结论

**【已证】run9c 这 5 天（夏 18 10:40 → 夏 23 06:10，6 份 `farm.complete=true` 快照）真正被清掉的只有三类：
`weeds 646→402`、`stones 110→104`、`twigs 70→60`（合计净 −260）；而 `trees 494→560`、`grass 700→784`（合计净 +150，**可再生**）。
用现在的观测**无法判定「农场已清干净」**，因为有三条硬缺口**：
1. `farm.stones` 把「可击碎石 + **所有** `ResourceClump`」混着数（`mod/AgentFarm.Bridge/FarmScan.cs:339-346`）；
2. `farm.trees` **不含树桩**：`FarmScan.cs:329-337` 只在 `!tree.stump` 时计数，**树桩不进任何计数器＝静默丢弃**；
3. 账本 `day_end.final.farm` 是**白名单**、完全没有障碍键（`brain/agentfarm/longrun.py:1506-1508`）⇒
   **run 期间若没有外部快照，就没有任何清障进度证据**（run9c 的障碍数字全靠 `scratch/run9c-observe-*.json` 才有）。

⇒ 对 task-151 的直接影响：判定必须**同时**给出「外部快照原始计数 + 快照时钟 + 当前地点」，
并且**显式列出拿不到的类**（树桩细分、`clumpIndex`、斧/镐等级），而不是沉默地当成 0。

---

## 1. 数据源盘点（逐条给路径/字段）

| # | 来源 | 路径 | 可用字段 | 口径 | 限制 |
|---|---|---|---|---|---|
| A | 外部观测（全农场） | `scratch/run9c-observe-*.json` → `.observe.farm` | `complete`/`loaded`/`scanSeq`/`weeds`/`stones`/`twigs`/`trees`/`grass`/`hoeDirt`/`emptyDirt`/`crops`/`ripeCrops`/`deadCrops`/`dryCrops`/`dryDeadCrops`/`dryTiles`/`dryTilesTruncated`/`machinesTotal`/`machinesReady`/`sprinklers`/`animals` | **全农场**（`Game1.getFarm()`，与玩家位置无关） | 只有 6 个时间点；无 `stumps`/`logs`/`boulders`/`bush`/`clumpIndex`；`farm.tiles` 恒为**空数组**（`len=0`，不能当逐格真值） |
| B | 外部观测（当前地点窗口） | 同上 `.observe.location` | `name`/`isFarm`/`isOutdoorFarm`/`tiles[]`（≤400 格，每格 `kind`/`tool`/`feature`/`objId`/`watered`/`crop`/`dead`/`ripe`/`plantable`/`standable`/`actionable`）/`tilesTruncated`/`objects`(计数)/`terrainFeatures`(计数)/`debris`/`tillable` | **当前地点**、按离玩家距离取最近 400 格 | 强依赖玩家站位；站在 `FarmHouse` 时 `tiles` 只有家具格（夏 23 那份 `terrainFeatures=0`、`objects=1`）⇒ **不能拿它当全场** |
| C | 账本 | `logs/longrun-3day-llm-run{7,8,9,9b,9c}.jsonl` → `day_end.final` | `counts_scope="window"`、`farm={loaded,complete,crops,dryCrops,dryDeadCrops,unwateredCrops,hoeDirt,deadCrops}`、窗口的 `crops`/`unwatered_crops`/`tillable`/`ripe`/`dead_crops`/`money`/`waterLeft`/`seeds` | `farm` 子集 = 全场；其余 = 窗口 | **没有任何障碍计数**（白名单在 `brain/agentfarm/longrun.py:1506-1508`） |
| D | 既有口径文档（**直接引用，不重做**） | `docs/_analyze-farmcounts.md`（两套仪器对照、`farm.unwateredCrops` 是数据表静态属性）、`docs/_tool-matrix.md`（对象→工具→等级真值表、缺陷 D1/D2） | — | — | 本文只补「清障进度/验收」这一层 |

---

## 2. `farm.*` 的计数口径是谁写的（mod 侧真值，逐条行号）

`mod/AgentFarm.Bridge/FarmScan.cs` 的 `AccumulateTerrain`（`:258-348`）与 `AccumulateObject`（`:350-391`）：

| 游戏对象 | 计数器 | 行号 | 备注 |
|---|---|---|---|
| `HoeDirt` 无作物 | `EmptyDirt` | `:269-272` | |
| `HoeDirt` 有作物 | `Crops` / `DeadCrops` / `RipeCrops` / `UnwateredCrops` | `:275-292` | `UnwateredCrops` 用 `needsWatering()`，**不看当天浇水**（见 `docs/_analyze-farmcounts.md` §3） |
| `HoeDirt` 未浇 + 活苗 | `DryCrops`（并收 `dryTiles` 坐标） | `:299-317` | task-84 起死苗只进 `DryDeadCrops` |
| `Grass` | `Grass++` | `:322` | |
| `Bush` | **`Grass++`** | `:325` | **缺陷 D2【已证】**：`farm.grass` = 草 + 灌木，不是「可割的草」 |
| `FruitTree` | `Trees++` | `:327` | |
| `Tree` 且 `!stump` | `Trees++` | `:329-337` | **树桩既不进 `trees` 也不进任何别的计数器＝静默丢弃**【已证】 |
| `ResourceClump`（600/602/604/148/622/672/752+…） | **`Stones++`**（`_ = clump;` 明确不细分） | `:339-346` | **缺陷 D1【已证】**：注释里写「细分留给 P2」 |
| `Object` `IsWeeds()` | `Weeds++` | `:368` | 游戏自身判定，口径最稳 |
| `Object` `IsTwig()` | `Twigs++` | `:369` | 同上 |
| `Object` `IsBreakableStone()`（+`StoneIds` 兜底） | `Stones++` | `:370-375` | 与 ResourceClump 混在同一格计数器里 |
| 机器 / 洒水器 | `MachinesTotal`(`Ready`)/`Sprinklers` | `:377-390` | 与清障无关 |

**【推断，算术佐证】** 在 `location.name == "Farm"` 的 5 份快照里，
`location.terrainFeatures`（当前地点地形特征总数）减掉 `grass+trees+hoeDirt` 恒等于 **2**：

| 快照 | terrainFeatures | grass+trees+hoeDirt | 残差 |
|---|---|---|---|
| 夏 18 10:40 | 1402 | 700+494+206 = 1400 | **2** |
| 夏 19 08:10 | 1391 | 658+510+221 = 1389 | **2** |
| 夏 19 14:30 | 1422 | 654+510+256 = 1420 | **2** |
| 夏 21 10:20 | 1482 | 721+535+224 = 1480 | **2** |
| 夏 22 07:20 | 1523 | 750+547+224 = 1521 | **2** |

⇒ 农场里恒有 **2 个既不是草/树/耕地、又没被单独计数的地形特征**（= `ResourceClump` 与/或树桩）。
这**只能证明「至少 2 个未分类障碍」**，**分不出**是巨石还是树桩 —— 正是 task-155 要补 `clumpIndex`/`stumps` 的原因。
（同类佐证：`location.objects` 与 `weeds+stones+twigs` 也恒差 1，说明还有 1 个非杂草/树枝/石头的对象；具体是什么【未定】。）

---

## 3. run9c 清障基线与进度表（外部观测，全农场口径）

| 快照（`scratch/`） | 游戏日/时刻 | `complete` | weeds | stones | twigs | trees | grass | hoeDirt | emptyDirt | crops |
|---|---|---|---|---|---|---|---|---|---|---|
| `run9c-observe-summer18.json` | 夏 18 10:40（雨） | true | **646** | **110** | **70** | 494 | 700 | 206 | 144 | 62 |
| `run9c-observe-summer19.json` | 夏 19 08:10 | true | 371 | 109 | 67 | 510 | 658 | 221 | 146 | 75 |
| `run9c-observe-summer19-2.json` | 夏 19 14:30 | true | 371 | 109 | 67 | 510 | 654 | 256 | 178 | 78 |
| `run9c-observe-summer21.json` | 夏 21 10:20 | true | 393 | 106 | 60 | 535 | 721 | 224 | 142 | 82 |
| `run9c-observe-summer22.json` | 夏 22 07:20 | true | 398 | 103 | 61 | 547 | 750 | 224 | 141 | 83 |
| `run9c-observe-summer22-2.json` | **夏 23 06:10**（站在 FarmHouse） | true | **402** | **104** | **60** | **560** | **784** | 221 | 118 | 103 |

**净变化（夏 18 → 夏 23）**：`weeds −244（−37.8%）`、`stones −6（−5.5%）`、`twigs −10（−14.3%）`、
`trees +66（+13.4%）`、`grass +84（+12.0%）`、`hoeDirt +15`、`emptyDirt −26`、`crops +41`。

**三条读数要点**：
1. **可再生类会涨**：weeds 在夏 19 掉到 371，随后 21/22/23 分别回到 393/398/402（每日重生）；
   trees/grass 五天内净增 —— 所以**「障碍总数单调不增」这种指标是错的**（见 §6 M2 的修正写法）。
2. **同一游戏日内的两份快照才可比**：夏 19 两份（08:10 / 14:30）weeds/stones/twigs 完全相等
   （371/109/67），说明当天这三类**没被清掉任何一格**；hoeDirt 221→256 说明当天主要在做耕地/浇水。
3. **末份快照站在 FarmHouse**，`location.terrainFeatures=0` ⇒ 若判定脚本只看 `location.*`，会误判成「农场空了」；
   必须用 `farm.*`（全场）+ 校验 `location.name == "Farm"` 才允许用 `location.terrainFeatures` 做残差。

**账本侧对照（`day_end.final.farm`，只有作物/耕地，没有障碍）**：
夏 18 `crops 76 / hoeDirt 232 / dryCrops 0` → 夏 22 `crops 103 / hoeDirt 239 / dryCrops 0`；
run9c 的 `final.counts_scope` 恒为 `window`，窗口 `crops` 随站位在 0…80 之间跳（`docs/_analyze-farmcounts.md` §1/§2 已定案）。

---

## 4. 口径红线（task-151 判定必须遵守）

1. **两套仪器不许混**：`farm.*`（全农场，仅 `complete=true` 可用）与 `location.tiles[]`（≤400 格窗口）分开报；
   任何把窗口数当全场数、或把全场数塞进窗口列的行，一律标【无法判定】。
2. **`farm.complete=false`/缺失 ⇒ 该次读数整体【无法判定】**，不许退回 `tiles[]` 也不许当 0。
3. **禁止「只写派生量」**：任何 `cleared=true`/`progress=100%` 形式的结论，必须**同一条判定里**带上
   `weeds/stones/twigs/trees/grass/hoeDirt/emptyDirt/crops` 的**原始计数** + 快照 `clock` + `worldSeq` + `complete`。
4. **快照密度**：沿用 0.7.31 起的世界差分口径（每日 ≥2 份端点快照，以 Lead 的 `docs/_run6-criteria.md` §4 原文为准）；
   只有 1 份的当天不得断言"清障了/没清障"。
5. **拿不到的类必须点名**，不许静默计入别的类：树桩（现在完全不计数）、`clumpIndex` 细分、灌木（混进 grass）、
   斧/镐等级（观测里只有洒水壶有 `upgradeLevel`，见 `docs/_tool-matrix.md` §0 与 `docs/_il-tool-upgrade.md` §6）。

---

## 5. 工具瓶颈表：要清完还缺什么（判断方法 + 数据缺口）

**【已证】门槛表**（来源 `docs/_tool-matrix.md` §2 与 `docs/_il-tool-upgrade.md` §7，IL 定案）：

| `clumpIndex` | 正确工具 | 等级门槛 | 现在能不能判 |
|---|---|---|---|
| 600（树桩） | `axe` | ≥1（铜斧） | **不能**：①观测没有 `clumpIndex`；②观测没有斧的 `upgradeLevel` |
| 602（大木头） | `axe` | ≥2（钢斧） | 同上 |
| 672（巨石） | `pickaxe` | ≥2（钢镐） | 同上 |
| 148 / 622 | `pickaxe` | ≥3（金镐） | 同上 |
| 752+ | `pickaxe` | 无等级判据 | 同上 |
| 树桩（`Tree.stump`） | `axe` | 无门槛 | **不能，且更糟**：它**不在任何计数器里**（`FarmScan.cs:329-337`） |
| 灌木（`Bush`，可摧毁） | `axe` | ≥1 或 `size==3` | **不能**：混进 `farm.grass`（`FarmScan.cs:325`） |
| 杂草 / 树枝 / 石头 | `hoe` / `axe` / `pickaxe` | 无 | 能（`weeds`/`twigs`/`stones`，但 stones 与 clump 混装） |

**判断方法（现阶段可写的部分，禁止编数字）**：
```
可清障碍_原始 = {weeds, twigs, stones}
clump_下界      = location.terrainFeatures − (farm.grass + farm.trees + farm.hoeDirt)   # 仅当 location.name=="Farm"
                  # 【推断】≥1 说明还有未分类障碍；无法判断是巨石还是树桩
工具是否够      = 需要 (clumpIndex, 斧/镐 upgradeLevel) 两个字段 ⇒ 现在一律【无法判定】
树桩            = 【无法判定】（不在 trees/stones/任何计数器里）
```

**给 task-155 的最小字段清单**（补齐后才能算"还缺哪种工具"）：
`farm.stumps` / `farm.logs` / `farm.boulders`（或 `clumps` 按 `clumpIndex` 分桶）、`farm.bushes`（从 grass 拆出）、
`tools[].kind`（axe/pickaxe/hoe/can）+ `tools[].upgradeLevel`（四类工具都写）、以及 `final.farm` 白名单
（`brain/agentfarm/longrun.py:1506-1508`）加入 `weeds/stones/twigs/trees/grass/stumps/boulders` —— **后者是让 run 账本自带清障证据的唯一办法**。

---

## 6. 给 task-151 的验收指标草案（3–5 条，均可从外部观测算）

> 每条都强制「原始计数 + 派生量」同时出现（§4 第 3 条）。`K = {weeds, stones, twigs}`，`V = {trees, grass}`。

**M1（格式门·原始计数）**
判定文本必须逐项列出 `weeds/stones/twigs/trees/grass/hoeDirt/emptyDirt/crops` + `complete` + `clock` + `worldSeq`，
且必须点名「树桩/clump 细分/灌木/斧镐等级 = 无法判定」。
反例（禁止形态）：只写 `"farm_cleared": true` 或 `"obstacles_remaining": 0`。

**M2（同日净减·修正版）**
同一游戏日（`clock.season/day` 相同）内若有 ≥2 份 `complete=true` 快照：
`(ΣK)_after − (ΣK)_before ≤ 0`（严格不增），且必须同时报 `Δweeds/Δstones/Δtwigs` 三个原始差。
反例：run9c 夏 18→19 的 `ΣK 826→547` 看起来漂亮，但那是跨日（含夜间重生）⇒ **跨日不许断言单调**；
run9c 夏 19 两份快照 `ΣK 547→547`（Δ=0）是合规的"当天没清障"。

**M3（清障完成判定）**
`farm_cleared=true` **当且仅当**同一份 `complete=true` 快照满足：
`weeds==0 ∧ twigs==0 ∧ stones==0 ∧ trees==0 ∧ grass==0 ∧ clump_残差==0`，
其中 `clump_残差 = location.terrainFeatures − (grass+trees+hoeDirt)` 且必须**当前地点是 Farm**；
`location.name != "Farm"` 或 `terrainFeatures` 缺失 ⇒ 【无法判定】（禁止用 FarmHouse 的 `terrainFeatures=0` 判完成）。
反例：`run9c-observe-summer22-2.json`（夏 23 06:10 在 FarmHouse）若被误用，会得出"残差 0−0=0 ⇒ 清干净了"。

**M4（树桩/未分类障碍显式化）**
只要 `clump_残差 > 0`，判定必须写出「至少 N 个未分类障碍（树桩或 ResourceClump；`clumpIndex` 落地前无法细分）」，
且**不许**把它计入 `stones` 后当成"石头还剩 N 个"了事。
阈值：`clump_残差 == 0` 才允许声称"没有树桩/资源堆"。

**M5（工具可达性）**
对每个待清障碍类，判定必须给出 `(工具, 现有等级, 门槛)` 三元组；缺 `clumpIndex` 或斧/镐 `upgradeLevel` ⇒ 【无法判定】。
反例（禁止形态）：用"连续 N 天没清掉"反推"工具等级不够"（那可能是够不着/被围住，见 task-52/133/134 的 `unreachable` 家族）。

**M6（可选·进度口径）**
报告里同时给两个数：`ΔK`（可清对象净减，原始差）与 `ΔV`（植被净变，原始差），
并注明 `V` 是**可再生**、不计入"清障进度"；避免用「障碍总数」把再生量当成失败。

---

## 7. 未定项

- **U1**：`location.objects − (weeds+stones+twigs)` 恒为 1 —— 那个对象是什么（宝箱/饲料/野生作物/掉落物）【未定】。
- **U2**：`clump_残差 = 2` 的组成（2 个 ResourceClump？1 clump + 1 树桩？2 个树桩？）【无法判定】，等 `clumpIndex`/`stumps`。
- **U3**：`farm.trees` 的 +66 是"树长大了被计到"还是"同一批树的另一种统计口径变化"【未定】；
  可查点：`Tree.growthStage` 只在成熟后进 `Trees`？——不，`FarmScan.cs:329-337` 不看 `growthStage`，只排除 `stump`
  ⇒ 更可能是**新树苗/种子长成**（Trees 计数上升），需逐格 `tiles[].kind=="tree"` 在窗口内的对照（窗口外看不到，未定）。
- **U4**：run9c 期间是否还有未落盘的观察快照（机器侧可能有但工作区没有）【未定】。

## 8. 复核命令（只读）

```powershell
# 取数（写 scratch/_t156_data.txt，UTF-8）
python scratch\_t156_data.py observe    # 6 份外部快照的 farm.* 与 location.tiles[] 直方图
python scratch\_t156_data.py shape      # location/farm 各列表字段的真实形状（farm.tiles 恒空已在输出里）
python scratch\_t156_data.py ledger     # run7/8/9/9b/9c 的 day_end.final.farm 白名单内容（证明没有障碍键）

# 口径真值（mod 侧，只读）
#   weeds/twigs/stone/clump 的计数规则：mod/AgentFarm.Bridge/FarmScan.cs:258-391
#   clump 一律 axe 的缺陷：   mod/AgentFarm.Bridge/WorldSnapshot.cs:484（见 docs/_tool-matrix.md D1）
#   账本 farm 白名单：        brain/agentfarm/longrun.py:1506-1508
```
