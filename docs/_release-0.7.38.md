# 0.7.38 发布计划 · 工具升级闭环（铁匠铺）

> 状态：**开工**（2026-10-17 11:45 起草）。触发：`User said (m18271)`「赶紧做工具升级吧，农场都快成森林了」⇒ 工具升级从 backlog 提到队首。
>
> 一个先期发现（已记入 task-203 的关闭说明）：**工具等级/升级状态的数据面早就有了**（task-155 那批，0.7.31/0.7.32 已装机）——`player.tools.tools[].upgradeLevel`、`player.toolUpgradeDaysLeft`、`player.toolUpgradeNotice`、`PlayerView.toolBeingUpgraded`。真机实测本存档 `Axe/Hoe/WateringCan/Pickaxe/Scythe` 的 `upgradeLevel` **全 0**。所以本批**不需要补观测**，只需要：①铁匠铺链路定案；②升级动作本身（含"指定选哪一项"的应答能力，现在 `dismiss_modal` 只会自己挑 Yes/第一项）；③脑侧升级策略与"在途两天"的诚实跳过。

## 1. 本批卡片

| 卡 | 侧 | 内容 | 状态 |
|---|---|---|---|
| **task-204** | 只读取证（log-analyst） | 铁匠铺升级链 IL 定案：入口（`Utility.TryOpenShopMenu("Blacksmith")` 还是 `answerDialogueAction` 字面量）、选工具 UI、真正扣钱+拿走工具的方法、`toolBeingUpgraded`/`daysLeftForToolUpgrade` 成员类型、价格与天数、可自动化路径 | 在制 |
| **task-205** | Mod + brain（dev-coder） | ①`dismiss_modal` 支持**显式应答**（`answer` = 下标或文本子串；仍只走游戏自己的 `answerDialogue`，禁注入确认键）②`upgrade_tool` 技能（开铺→选工具→付钱→回执带钱/等级/天数证据）③脑侧 `farmwork.upgrade_tool` + 每天最多一次的策略 + 「在途两天」如实跳过 + 事件 `tool_upgrade`/`tool_upgrade_skipped` | 待开工（等 204） |
| **task-206** | 独立对抗验收（deputy-lead） | 8 条作弊通道（回执洗白 / 钱不够仍扣款 / 已升级仍重复购买 / 选错工具 / 在途两天假跳过 / checks 口径污染 / 变异实测 vs 自报 / 真机序列可复算） | 待 205 |
| **task-199** | Mod + brain（dev-coder） | 上一批的 WIP（`farm.readyTiles` + 脑侧走过去收窗口外熟作物），约 90%（剩 1 处小修验证 + farmwork 三态用例 + 变异） | 在制（先收尾，单独冻结 0.7.37） |

**批次切分（Lead 裁定）**：为了让升级尽快上线，**0.7.37 收缩为 {task-199}**，它一交付就冻结装机；原本排在 0.7.37 的 **195 / 196 / 193 / 197 移到 0.7.39**（不丢，见 §5）。

## 2. 冻结九步（每批照走，Lead 独占）

1. `tools/_note-*.txt`（首串必须是 `vX.Y.Z`，列出本版内容）
2. `python tools/_bump-mod-version.py X.Y.Z --note-file tools/_note-XXXX.txt`（改 manifest）
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "X.Y.Z"`（注释补本版条目、历史保留）
4. `dotnet build mod/AgentFarm.Bridge/AgentFarm.Bridge.csproj -c Release --nologo --no-incremental`（必须 0 警 0 错）
5. **冻结提交**（`git add -A` 后提交；工作树必须干净）
6. `python tools/check-release.py --expect X.Y.Z`（六项全绿：manifest==brain、版本==期望、dll 比源码新、`py_compile`、全量单测、树干净）
7. `python tools/deploy-mod.py --no-quit`（装机 + 自动读档）
8. `python -m agentfarm goto Farm`
9. `python tools/preflight.py --expect X.Y.Z --save-baseline logs/runXXX-baseline.json` ⇒ ✅ 才起跑

## 3. 本批判据（真机，外部观测差分）

- **升级序列（存档已知：钱 2519g、五把工具全 0 级、秋 19 日）**：铜级 2000g ⇒ 期望 `money 2519 → 519`、`player.toolBeingUpgraded` 出现 `axe`、`toolUpgradeDaysLeft == 2`、`player.tools.tools[]` 中 Axe 不再以 0 级出现 ⇒ **两天后** `upgradeLevel.axe == 1`。
- **升级效果**：升级前农场里某格大桩/圆木（`ResourceClump`）`toolOk == false` ⇒ 升级后同格 `toolOk == true` 且 `use_tool` 能真正清掉（`farm.clumpsTotal` 下降 / 该格 `tile` 变化）。
- **三条红线**（任一违反 ⇒ 不许冻结）：①钱不够时**一分不扣**、false-positive 一律 fail-closed；②Mod 回执说 ok 但世界没变 ⇒ 脑侧必须判 failed；③升级在途两天里，需要该工具的动作必须**如实 `skipped`**，不算 hard failure、不吃 `gave_up` 配额、不许用 `tool_upgrade` 洗白 `no_unmet_stages`。

## 4. 已知限制 / 风险

- 升级要**走到铁匠铺**（跨地点），跨地点路径与 `move_to_location` 的 hop 预算要单独看（最近一版把跳预算改成 `Clamp(4000+500×剩余步数, 8000, ≤30000)`）。
- 工具被拿走 **2 天**：这两天里"需要那把工具"的清障会停，属预期；但**浇水**只在水壶升级时受影响。
- 每档价格 2000 / 5000 / 10000 / 25000（待 204 文档确证），当前钱只够**一次铜级**。
- 若 205 新增了 journal 事件名，需同步 analyzer 卡（否则全量漂移红会挡住冻结）。

## 5. 欠账（0.7.39 起）

- **task-195**（Mod）：`actedEvidence` 必须绑**目标格**或标注聚合来源；原始 `use_tool` 在目标格不可收时不得静默连带（R7）。
- **task-196**（brain）：目标格 loot 与**连带掉落**分栏记账（`loot` / `collateral_loot`）+ `affected_tiles` 如实（R8）。
- **task-193**（brain）：`sell` 白名单收窄（"与目标格变化相关的收获"），杜绝无关 qid 进白名单（C2-a / task-200 NIT-1）。
- **task-197**（tests）：消除子进程 stdout 的编码依赖（显式 `encoding="utf-8"`）+ 「不带 `PYTHONUTF8` 也绿」回归护栏。
- **task-151 / task-141 / task-142**（目标 1 的另一半）：全场清理收敛 + "该升哪把工具"的 LLM 建议 + 工具升级链（本批 204/205 即 142 的主体）。注意 task-142 已被本批拆分取代，收口时在板上注明。
