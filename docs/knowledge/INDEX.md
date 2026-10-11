# 知识库索引（agentfarm）

> 本目录收录**从旧项目 `stardew-auto-farm` 逆向整理出的知识资产**。
> 所有内容遵循同一条铁律：**没有实测输出背书的结论一律标 `[未验证]`，绝不当结论用。**
> 整理范围只含"已被实测验证的知识与数据"；旧项目的失败教训单独成篇，避免被误当成最佳实践。

---

## 1. 文档清单（每份一句话）

### 本目录（`docs/knowledge/`）

| 文档 | 一句话说明 |
|---|---|
| [legacy-api-1.6.15.md](legacy-api-1.6.15.md) | Stardew Valley 1.6.15 游戏 API 知识页：工具继承链 / `Crop.harvest` 反射 / 地形特性类型体系 / 背包与物品陷阱 / 地图传送判定 / 1.6.15 特有坑全清单，**每条都标了可信度与出处（文件:行号 或 探针名）**。 |
| [legacy-design-patterns.md](legacy-design-patterns.md) | 值得借鉴的 4 个设计模式（`PreCheck/Execute/PostCheck` 三段契约、`SelfTest()` 自检、`SurroundingsSnapshot` 逐字段容错、`WorldIsAdvancing` 活性检测）+ **10 条"以后绝对不要重做"的失败教训**及其真实故障证据。 |
| [INDEX.md](INDEX.md) | 本文件。知识库索引、可信度口径、未验证探针清单。 |

### 项目上层文档（`docs/`，本次整理**未修改**）

| 文档 | 一句话说明 |
|---|---|
| [_legacy-audit.md](../_legacy-audit.md) | **旧项目审计报告（本次整理的依据与可信度分层来源）**。§4.0 探针可信度分层、§4.1 API 知识、§4.2 数据资产、§4.4 运维资产、§5 架构级缺陷 D1~D5。 |
| [01-架构设计.md](../01-架构设计.md) | 新项目的架构设计。 |
| [02-环境实测快照.md](../02-环境实测快照.md) | 新项目的环境实测快照。 |
| [00-开发日志.md](../00-开发日志.md) | 新项目开发日志。 |
| [_external-research.md](../_external-research.md) | 外部资料研究（社区/Nexus/文档等外部来源）。 |
| [03-桥接协议.md](../03-桥接协议.md) | 桥接协议（本次整理未涉及）。 |

### 生成的数据与工具

| 路径 | 一句话说明 |
|---|---|
| [brain/data/crops.json](../../brain/data/crops.json) | **19 条作物经济数据**（外壳 `schema=agentfarm-crops/1`），由旧项目 `data/crop_economics.json` 转换，保留全部原始字段 + 全部作物条目 + 原始非作物段落（加工链/社区中心/年度路线/自动化目标）。 |
| [brain/data/crops-consistency-report.json](../../brain/data/crops-consistency-report.json) | 上述数据的**自洽性检查报告**：19 条中 8 条与文件自述公式不自洽（**只报告，未改数据**）。详见 §4。 |
| [tools/analyze_log.py](../../tools/analyze_log.py) | SMAPI 日志分析器（刷屏风暴检测 / 错误归类 / 已知故障签名匹配 / 任务健康统计）。从旧项目复制，**路径已参数化**。 |
| [tools/parse_save.py](../../tools/parse_save.py) | 存档 XML 解析器，输出农场关键状态与解锁进度。从旧项目复制，**路径已参数化**。 |
| [tools/il-probe/](../../tools/il-probe/) | `Probe26` 迷你 IL 反汇编器（已去 `bin`/`obj`），用于把"猜字段语义"换成"读 IL"。**旧项目从未产出落盘输出**，见 §3。 |

---

## 2. 可信度口径（全库统一）

| 标注 | 含义 | 判定标准 |
|---|---|---|
| `[实测 Probe8]` `[实测 Probe9]` `[实测 Probe10]` `[实测 Probe11]` `[实测 Probe13]` | 探针已落盘输出，**可信** | `tools/probes/ProbeN/probeN_out.txt` 实际存在且含该结论 |
| `[实测]` | 有运行期数据文件/日志佐证 | 可指到具体数据文件与字段 |
| `[旧代码]` | 旧项目源码里实际写成的调用或注释 —— **行为已编译验证，但游戏语义未必正确** | 可指到具体 `文件:行号` |
| `[旧代码/文档线索]` | 来自旧文档（`ARCHITECTURE.md` 等），**文档已知与实现有出入** | 只作线索，不得当结论 |
| `[未验证]` | 仅有探针源码/推测，无任何输出 | 必须在真机重新验证后才能升格 |
| `[审计]` | 引自 [_legacy-audit.md](../_legacy-audit.md) 的结论 | 该报告自身区分了"已读码"与"未确认" |

**⚠️ 旧文档不可信的具体证据**（审计 §4.0 已确认）：
- `docs/ARCHITECTURE.md:319` 说探针有 **13 个**，实际 **26 个**（文档未同步）。
- 审计 §4.1 指出：审计报告那句"类别常量全部落在 `-2`~`-29` 与 `-74`~`-95` 两段"**不完整** ——
  实测 `probe10_out.txt:35-45` 还有 `-96`~`-103` 与 `-999`。**以探针全表为准。**
- 审计 §1.1：`ARCHITECTURE.md:9-19` 与 `WATCHDOG_AND_AI.md:113-121` 宣称的数据链路与实现不符
  （真正的感知输入是 `farm_tiles.json`，不是 `live_snapshot.json`）。

---

## 3. 探针可信度总览

旧项目 `tools/probes/` 下共 **26 个**探针，但**只有 5 个留下了实际输出文件**。

### ✅ 有实测输出（可信，可直接引用）

| 探针 | 输出大小 | 主要覆盖 |
|---|---|---|
| `Probe8` | 13.1 KB | 工具继承链、`Tool.DoFunction` 签名、地形特性继承、`GameLocation` 耕地 API、`Inventory`/`addItemToInventory`、`PathFindController` 构造、`Debris`、`Map` 容器字段 |
| `Probe9` | 26.2 KB | 菜单/输入全局态、`Farmer` 可写性、`ShopMenu` 全成员、`Utility.TryOpenShopMenu`、睡觉/新一天、床与睡眠、`FishingRod` 详解、`PathFindController` 委托、`Game1.warpFarmer` |
| `Probe10` | 7.4 KB | `ResourceClump` 真实全名与基类、`Object` 类别常量全表、`HoeDirt.plant` 与状态常量、**`Crop.harvest` 完整签名**、洒水器、工具升级 |
| `Probe11` | 6.9 KB | **`BobberBar` 完整字段表**、`BobberBar` 构造、`InputState`、`pullFishFromWater` |
| `Probe13` | 8.3 KB | `FarmAnimal`/`AnimalHouse`、加工机器 `heldObject`/`minutesUntilReady`、`Crop` 死亡/换季、季节常量、`NetLongDictionary` 值类型 |

**输出文件路径（旧仓库，只读）**：
`tools/probes/Probe{8,9,10,11,13}/probe{8,9,10,11,13}_out.txt`

### ❌ 只有源码、无输出（**未验证**，共 21 个）

> 以下清单**逐字抄自** [_legacy-audit.md](../_legacy-audit.md) §4.0。
> 这些探针的 API 假设**一律标 `[未验证]`**，新项目必须先自行验证。

| # | 探针 | 备注（来自审计 §4.1 / §4.4） |
|---|---|---|
| 1 | `Probe` | 一次性脚本，无输出无文档 |
| 2 | `Probe2` | 同上 |
| 3 | `Probe3` | 同上 |
| 4 | `Probe4` | 同上 |
| 5 | `Probe5` | 同上 |
| 6 | `Probe6` | 同上 |
| 7 | `Probe7` | 同上 |
| 8 | `Probe12` | `WateringCan` 字段 / `NetInt` 全名 |
| 9 | `Probe14` | 矿洞 / 矿石 / 怪物 / 体力血量 / 镐 |
| 10 | `Probe15` | — |
| 11 | `Probe16` | — |
| 12 | `Probe17` | — |
| 13 | `Probe18` | — |
| 14 | `Probe19` | — |
| 15 | `Probe20` | — |
| 16 | `Probe21` | — |
| 17 | `Probe22` | **失焦暂停专探**（`Options.pauseWhenOutOfFocus`，即 API 页 §7.9 的坑） |
| 18 | `Probe23` | — |
| 19 | `Probe24` | — |
| 20 | `Probe25` | — |
| 21 | `Probe26` | **IL dumper**；方法名已见，但**无 dump 输出落盘**。见下 |

**计 21 个**：`Probe`、`Probe2`~`Probe7`（6 个）、`Probe12`、`Probe14`~`Probe26`（13 个）。
合计 1 + 6 + 1 + 13 = 21。✔

### 关于 `Probe26` 的特别说明

- `Probe26.cs:25-30` 的 6 个方法名（`PathFindController.handleWarps`、
  `getWarpFromDoor`、`openDoor`、`isCollidingWithWarpOrDoor`、`isCollidingWithWarp`、
  `isCollidingWithDoors`）是**代码里写死的字符串**，属"作者认为存在"，**不是"已验证存在"**。
- 因此**依赖它验证的传送判定结论全部标 `[未验证]`**（API 页 §5.1、§5.2、§8 第 4/5 项）。
- 该工具已复制到 [tools/il-probe/](../../tools/il-probe/)（**已去 `bin`/`obj`**）。
  **跑一次并落盘输出，即可把上述结论升格。**

> **元教训（写进 METHODOLOGY）**：探针的价值**完全在输出**。没有落盘输出的探针
> = 一次性脚本 + 一个无法验证的假设，还会被后来者（包括 AI）误当成已验证事实。
> 新项目规则：**探针产物必须入库**（输出文件 + 用途 README + 运行命令）。

---

## 4. 数据资产：`crops.json` 与自洽性检查

### 4.1 交付内容

- 源：旧项目 `data/crop_economics.json`（11.1 KB，只读，未修改）
- 目标：[brain/data/crops.json](../../brain/data/crops.json)
- 转换规则：**保留全部原始字段与全部作物条目**，加外壳
  `{"schema":"agentfarm-crops/1","source":"legacy crop_economics.json (WorkBuddy stardew-auto-farm)","crops":[...]}`。
  额外保留原始非作物段落（原样，未改动数值）：`meta`、`comment`、`season_strategy`、
  `processing_chain`、`community_center_priority`、`year_roadmap`、`automation_target`。

| 统计 | 值 |
|---|---|
| 作物条目总数 | **19**（春 7 / 夏 6 / 秋 6 / **冬 0**） |
| 原始字段 | `id` `name` `seed_cost` `sell` `grow_days` `regrow` `yield_avg` `profit_per_day` `tier`，部分条目另有 `note`；**全部保留** |
| 新增字段 | 仅 `season`（用于把 4 个季节数组合并成一个列表；原始数据按季节嵌套，无此字段） |

### 4.2 自洽性检查发现（**只报告，未改任何数值**）

判据 = 文件 `_comment` **自述**的公式：`profit_per_day = (sell × yield_avg − seed_cost) / grow_days`。
容差 1%。完整结果见 [brain/data/crops-consistency-report.json](../../brain/data/crops-consistency-report.json)。

**结论：19 条中 11 条自洽、8 条不自洽。**

**✔ 自洽的 11 条**（偏差 ≤ 0.05%）：Parsnip、Cauliflower、Potato、Kale、Rhubarb、
Melon、Starfruit、Pumpkin、SweetGemBerry、BokChoy、Amaranth —— **全部是 `regrow == 0`（单次收获）作物。**

**❌ 不自洽的 8 条（偏差 > 1%）**：

| 作物 | 季节 | `regrow` | 报告值 | 自述公式值 | 偏差 | 说明 |
|---|---|---|---|---|---|---|
| Cranberry | fall | 5 | 18.21 | **−12.86** | **170.6%** | 公式算出**负数**（220g 成本 vs 200g 单次产出） |
| GreenBean | spring | 3 | 7.86 | **−2.00** | **125.5%** | 同上（60g vs 40g） |
| Hops | summer | 1 | 13.93 | **−3.18** | **122.8%** | 同上（60g vs 25g） |
| HotPepper | summer | 3 | 10.00 | **0.00** | **100.0%** | 公式算出**恰好 0**（40g = 40g） |
| Tomato | summer | 4 | 8.93 | 0.91 | **89.8%** | 严重低估 |
| Grape | fall | 3 | 17.86 | 2.00 | **88.8%** | 严重低估 |
| Strawberry | spring | 4 | 22.14 | 2.50 | **88.7%** | 严重低估 |
| Blueberry | summer | 4 | 18.57 | 5.38 | **71.0%** | 严重低估 |

**根因（可直接证实的规律）：所有 8 条不自洽的作物 `regrow > 0`（多次收获），
11 条自洽的作物 `regrow == 0`。** 即：`profit_per_day` 对多次收获作物**换用了别的口径**
（明显把"整季多轮收获"摊进了单日利润），但**文件头部的 `_comment` 只声明了单次收获口径**。

**尚未定论的部分**：这些"别的口径"**也不是**统一的整季 28 天摊薄 ——
报告里的 `deviation_season_28d_pct` 显示 8 条**没有一条**能被
`(sell×yield−seed_cost)/28` 复现。因此**无法从数据本身反推出多收作物的实际算法**
（例：GreenBean 的 `note` 说"全季 28 天收 7 轮"，但用 7 轮重算也对不上 7.86）。
⇒ **`[未验证]`**，需向原作者确认，或改用游戏权威 API `Crop.RegrowsAfterHarvest()`
（见 API 页 §2.2）在真机重算。

### 4.3 对新项目的影响与建议

1. **不要直接把 `profit_per_day` 当排序依据**。用它排产会把
   Cranberry(18.21) 排在 Pumpkin(16.92) 之前 —— 但按文件自述公式两者关系相反。
   **多收作物的排序结论目前不可信。**
2. **统一口径后重算**：把 `profit_per_day` 拆成两个显式字段
   （如 `profit_per_day_first` = 首次收获口径、`profit_per_season` = 整季口径），
   并注明计算式，消除"同一字段两种含义"。
3. **`tier` 取值域未文档化**（出现 `early`/`mid`/`best`，无定义、无边界）。
   新项目应给出 `tier` 的判定规则或改为派生值。
4. **`winter` 为空**（0 条作物）—— 这不是缺陷（冬季无法户外种植），但下游代码
   必须能处理空季节，不要假设"每季都有 best_crop"（`winter.best_crop` 为 `null`）。
5. **数据缺口**：无肥料（速生）维度。`HoeDirt.speedGroID=465` 等常量已实测
   （API 页 §2.6），肥料会直接改变 `grow_days` ⇒ 影响 `profit_per_day`。
   若要精确排产需补此维度。

### 4.4 数据里的其他资产（原样保留，供新项目直接使用）

- `processing_chain.keg_wine[]`：8 条，`multiplier` 实测 Starfruit/Pumpkin/Melon/Rhubarb/
  Grape/Cranberry/Blueberry = **3.0**，**Hops = 12.0**（"啤酒花→淡啤酒，倍数最高"）。
- `processing_chain.preserves_jar[]`：5 条，`multiplier` 1.4~4.0（**注意：该组数值内部不一致**：
  Starfruit 750→1050 是 1.4×，Cranberry 75→250 是 3.33×，Blueberry 50→200 是 4.0×，
  HotPepper 40→160 是 4.0×，Pumpkin 320→690 是 2.16×，均**与 `multiplier` 字段自洽**，
  故仅"实际增值倍数差异大"而非计算错误）。
- `community_center_priority`：`tier_S`/`tier_A`/`tier_B` + `key_items`。
- `year_roadmap`：三年路线图；`automation_target`：`required_mods[]`（含 Nexus ID）+ `layout_principle`。

---

## 5. 快速导航：我该看哪一份？

| 你的问题 | 看这里 |
|---|---|
| 这个 API 在 1.6.15 里到底怎么调？可信吗？ | [legacy-api-1.6.15.md](legacy-api-1.6.15.md) |
| 有没有一条"1.6.15 特有坑"的清单？ | 同上 §7（含每条坑的证据与影响） |
| 哪些结论其实是没验证的？ | 同上 §8 + 本文件 §3 |
| 旧项目哪些设计值得抄？ | [legacy-design-patterns.md](legacy-design-patterns.md) §1~§4 |
| 旧项目哪些机制**绝对不要重做**？ | 同上 §5（10 条，每条附真实故障证据） |
| 为什么旧项目会静默空转 40 分钟？ | 同上 §5.2 / §5.3 / §5.9；原始分析见 [_legacy-audit.md](../_legacy-audit.md) §5 |
| 作物经济数据怎么来的、能用吗？ | 本文件 §4；数据在 [brain/data/crops.json](../../brain/data/crops.json) |
| 怎么分析 SMAPI 日志 / 读存档？ | [tools/analyze_log.py](../../tools/analyze_log.py)、[tools/parse_save.py](../../tools/parse_save.py) |
| 怎么确认一个方法到底做了什么？ | [tools/il-probe/README.md](../../tools/il-probe/README.md) |

---

*本索引只做导航与可信度声明；所有结论的出处见各文档正文。整理过程未修改旧项目任何文件，
也未修改 `docs/` 下既有的 5 个文档。*
