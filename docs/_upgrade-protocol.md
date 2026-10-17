# 铜斧升级 · 真机验收协议（0.7.38+）

> 目的：把「工具升级」这条**依赖材料链**的业务从「口头计划」变成可逐条判红的真机协议。
> 触发前提：Mod ≥0.7.38（含 task-205 `upgrade_tool`、task-210 机器链、task-208 显式应答）。
> 判据纪律：**一切以外部世界差分为准**（`observe?detail=full` 的 `player.money`/`inventory[]`/`tiles[]`/`farm.*` + 存档 size/mtime + SMAPI），账本自述只作线索；缺失 ≠ 通过。

## 0. 前置自检（不过就停）

| 项 | 期望 | 判据来源 |
| --- | --- | --- |
| `toolBeingUpgraded` | `null` | `player.toolBeingUpgraded` |
| `toolUpgradeDaysLeft` | `0` | 同上 |
| 五件工具 `upgradeLevel` | 全 `0` | `player.tools.tools[]` |
| 钱 | ≥ **6275g**（见 §2 预算） | `player.money` |
| 背包空格 | ≥ 2 | `inventoryCount − len(inventory[])` |
| 存档 | 已读档、无模态、`worldAdvancing==true` | `preflight` |

**预算（0→1 铜斧，按 task-204/209 数据）**
- 45 铜矿 × 75g = **3375g**（熔炉 20 + 冶炼 25）
- 6 煤 × 150g = **900g**（冶炼 5 + 余 1）
- 25 石（农场自采；背包当前 3）
- 铁匠铺升级费 = **2000g**
- ⇒ 现金合计 **6275g**；材料缺口需先靠「卖作物/杂物」补齐（经济闭环 task-55/102/123 已真机通过）

## 1. 资金（经济闭环，可能跨多日）

1. `ship`（出货箱）或 `sell`（商店）把成熟作物与杂物变现；出货箱**次日到账**。
2. 判据：`money` 单调上升 + `farm` 障碍计数下降；每笔卖出记 `sell`/`surplus_sell` 事件与背包逐 qid 差分。
3. 边跑边判「臂有效性」：若连续两天 money 不涨且背包不满 ⇒ 停下报告（不是继续空转）。

## 2. 采购（Clint `Blacksmith`）

- 买 `(O)378` ×45、`(O)382` ×6。
- 判据：`money` 减少 **4275g**；背包两 qid 各 +45/+6。
- **fail-closed**：钱不够 ⇒ 停下报告；**不许**买一半再试（避免半吊子状态）。

## 3. 造熔炉（`craft_item`）

- 配方（以实现时的 `Data/CraftingRecipes` 为准，task-211 定案）：20 铜矿 + 25 石 → `(BC)114` ×1。
- 判据：背包 `(O)378` −20、`(O)390` −25、`(BC)114` +1；`money` 不变。

## 4. 放置熔炉（`place_object`）

- 目标：农场可站空格（不压作物/不挡门口/不在箱子旁），先由脑侧选格并记录坐标。
- 判据：背包 `(BC)114` −1；该格 `tiles[].kind=="object"` 且 `objId=="(BC)114"`；存档 `<objects>` 条数 +1。

## 5. 冶炼 ×5（`machine` feed → 等待 → collect）

- 每次：投 5 铜矿 + 1 煤 ⇒ 30 游戏分钟后产出 1 铜锭 `(O)334`。
- 每次判据：铜矿 −5、煤 −1；机器 `heldObject.id=="334"`；collect 后背包 `(O)334` +1 且机器 `heldObject==null`。
- 5 次后：背包 `(O)334` = 5。
- **不许**为了验收造材料（`addItem` 直造禁止）。

## 6. 升级（`upgrade_tool`）

- 入口：`Utility.TryOpenShopMenu("ClintUpgrade","Clint",true)` → 反射 `ShopMenu.tryToPurchaseItem(<Copper Axe 条目>, null, 1, 0, 0)`。
- **硬自检（防损）**：`toolBeingUpgraded==null` && `toolUpgradeDaysLeft==0` && `money>=2000` && 背包 `(O)334>=5`。**四项任一不满足 ⇒ 不发购买**（`tryToPurchaseItem` 是「先扣钱+材料、再 `actionWhenPurchased`」，失败不回滚）。
- 判据（购买瞬间）：`money` −2000；`(O)334` −5；`toolBeingUpgraded=="(T)Axe"`；`toolUpgradeDaysLeft==2`；斧头从 `tools[]` 消失或不可用。
- **绝不重复购买**（第二次会再扣 2000 + 5 锭且不退款）。

## 7. 取回（2 个游戏日后）

- 睡 2 夜后找 Clint 取回（进店 `blacksmith()` 取回分支）；需 ≥1 空槽。
- 判据：`toolBeingUpgraded==null`；`player.tools.tools[]` 里斧头回来且 `upgradeLevel==1`；`toolUpgradeDaysLeft==0`。

## 8. 升级的价值验证（清障能力）

- 挑一个升级前 `toolOk==false` 的小树/巨石：升级后同类格 `toolOk==true`，且一次 `use_tool` 后该格 `feature/kind` 变化。
- 判据：`tiles[].toolOk` false→true；挥砍后该格变化 + 背包掉落/qid 增量；`farm` 障碍计数下降。

## 失败分支（都必须如实记录，不许洗白）

| 分支 | 处置 |
| --- | --- |
| 钱不足 | 停机报告；不买半份 |
| 无空位放熔炉 | 有界 3 次清格后重试，仍失败 ⇒ 报告 |
| 冶炼 30 分钟超时 | 如实记录，不 `load_save` 重试 |
| 升级后 2 天内工具不在手 | 日循环必须跳过依赖该工具的活，如实记录（不许假装干了） |
| 外部证据与账本冲突 | 以外部证据为准，停下报告 |

## 9. 记录要求

- 每步前后各一份 `observe?detail=full`（存 `scratch/upgrade-verify-*.json`）；存档 size/mtime 前后各记；账本事件对应行号。
- 汇总写 `docs/_run10-upgrade-verify.md`：§0 结论、§1 基线、§2 逐步骤差分表、§3 外部证据（存档/SMAPI）、§4 失败分支与原因、§5 【无法判定】清单。
