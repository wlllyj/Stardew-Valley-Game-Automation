# 0.7.32 发布计划 · **目标 2 的解药（够得着 + 体力预算）与目标 1 的观测前置**

> 用户 2026-10-17 `User said (m15155)` 把目标改成两个：**目标 1** 全场清理（钱要平衡"作物再投资"与"工具升级"，**只要求完成一次全部清理即标完成**）；**目标 2** 连续 5 个游戏日完全自主 + 策略生成/结果校验/据结果优化。
> **拆版（2026-10-17 Lead 裁定，run9d 结论后）**：run9d（0.7.31）尾链 0/5，病灶是 ①`[12,30]` 这类**够不着**的活苗干作物（task-157）②**农场规模 > 单日体力预算**（task-158）。⇒ **0.7.32 = task-157 + task-158 + task-155 + task-20**（目标 2 的解药 + 目标 1 的 Mod 观测前置）；**0.7.33 = task-141 + 142 + 151 + 152**（升级链 + 全场清理收敛 + 钱的三分配 ⇒ 目标 1 的"完成一次完整清理"）。两张目标 1 的核心卡因此从本版移出，见 §7。
> **排期纪律（已解除并改写）**：原规则"0.7.32 的代码改动必须等 run9d/run10 跑完"是因为长跑器直接读工作树；**run9d 已结束、0.7.31 上不再排验收跑** ⇒ 纪律解除。新的纪律：**A→B 演进对照必须在 0.7.32 同一份构建上跑两次**，A/B 之间不许动 brain/mod（只许拷教训库）。

## §0 现状（2026-10-17 01:2x）

- **已证**（task-153，`24ffe71`，`docs/_il-tool-upgrade.md`）：
  - 升级入口 = 对话应答键 `Blacksmith_Upgrade` ⇒ `Utility.TryOpenShopMenu("ClintUpgrade","Clint",true)`；菜单是数据驱动 `ShopMenu`（`Data/Shops["ClintUpgrade"]`，条目 = `ToolUpgradeData{Condition,Price,RequireToolId,TradeItemId,TradeItemAmount}`）。
  - 状态字段全 public：`Farmer.toolBeingUpgraded`、`Farmer.daysLeftForToolUpgrade`、`Tool.UpgradeLevel`。
  - 价格：**2000+5 铜锭 / 5000+5 铁锭 / 10000+5 金锭 / 25000+5 铱锭**（按当前等级 0..3）；升级耗时 2 天。
  - **陷阱**：`chargePlayer`/`ConsumeTradeItem` 排在 `actionWhenPurchased` **之前** ⇒ 已有工具在升级时**钱照扣、工具不升级** ⇒ 发起前必须先自己判 `toolBeingUpgraded == null`。
  - 清障门槛：**600 树桩=斧≥1、602 大木头=斧≥2、672 巨石=镐≥2、148/622=镐≥3、752+（绿雨）无等级检查**；血量 10/20/10/20/8。
  - 我们的三处错：`WorldSnapshot.cs:484` 全部 clump 写 `tool="axe"`；`FarmScan.cs:339-346` 把树桩/大木头算进 `stones`；`UseToolSkill.cs:432` clump 一律用斧。
- 观测层现状：`ToolsView` 只有布尔 + `wateringCan.upgradeLevel`（`Contracts.cs:323-324`）⇒ 看不清"哪把工具能清哪种障碍"。
- 经济现状：run9c 已真机跑通"卖盈余 → 次日到账 → 买当季种子 → 播种"（`sell` → money 5→545→465→365 → `buy` 6 成交 5 → 每日 `plant_area` 落格），但**没有任何"为升级存钱"的概念**。

- **run9d（0.7.31，2026-10-17，run A 之前的诊断跑）实测**：`--days 5 --max-days 12` ⇒ 9 个日报告、`finish {code:1, verified_streak:0, actions:827, minutes:38.26, no_unmet_stages:true, unmet_days:[], stuck_flushes:0}`，**尾链 0/5**。逐日：夏 23 ✅（`stamina:体力 10 < 12`，dry 0）/ 24 ✅（真空日 `no_work`，dry 0）/ 25 ❌（`gave_up_dry`：`[12,30]` **够不着**）/ 26 ❌（`work_spot_resume` ×5）/ 27 ❌（`stamina:体力 0 < 12`，dry **17**）/ 28 ❌（dry **79**）/ 秋 1 ❌（dry **140**）/ 秋 2 ❌（dry 73）/ 秋 3 ❌（`slept_without_work`，0 动作）。外部证据：存档 **8/8** 跨日六串全配对（SMAPI 窗口 595212 B / 8071 行 / SHA256 `E1340346…DC0E`）、跨日链 8/8 恰 +1、自述 vs 自算 9/9、三工具全 rc=1、`Warping to Farm` 2200 次（task-14，信息项）、优雅退出已核。
- **两条根因（⇒ 本版两张主卡）**：①`[12,30]` 这类"够不着"的活苗干作物 —— 逐格判据没错（task-133 生效），错在**没有"先开路再浇"的动作**（task-157）；②**农场规模 > 单日体力**：作物 105→151、`stamina` 用尽在浇水前（`dry` 17→79→140 逐日堆积）⇒ **体力预算与规模控制**（task-158）。
## §1 卡片表（本版）

| 卡 | owner | 依赖 | 内容 | 状态 |
|---|---|---|---|---|
| **task-155** | dev-coder | task-153 ✅ | Mod 观测补：`clumpIndex`/`width`/`height`/`health` + 推导 `clumpTarget{tool,minLevel}`；`FarmScan` 按 clumpIndex 分流（树桩/大木头不再进 `stones`）；`ToolsView.tools[]` 带 `upgradeLevel`；`player.toolBeingUpgraded`/`toolUpgradeDaysLeft`；`UseToolSkill` 按 `clumpTarget` 选镐/斧、等级不够直接 `skipped` | pending |
| **task-141** | dev-coder | 155 | Brief 暴露 `tool_levels` + `obstacles_by_tool`；`TASK_KINDS` 增 `tool_upgrade` 意图（**只建议不改世界**，journal `tool_advice`/`day_end.tool_advice`，不影响 `verified`/rc）；≥6 单测 | pending |
| **task-142** | dev-coder | 141 | 铁匠铺升级链：`upgrade_tool` 技能（`TryOpenShopMenu("ClintUpgrade")` + 反射 `tryToPurchaseItem(item,null,1,0,0)`，**先判 `toolBeingUpgraded == null`**）+ 主动升级闭环（钱够 + 有对应金属锭 + 该工具是当前瓶颈）；判据=观测差分（钱差==Price、锭 -5、`toolBeingUpgraded!=null`、`daysLeft==2`、次日 -1、取回 `UpgradeLevel+1`） | pending |
| **task-151** | dev-coder | 142 | **全场清理收敛**：以 `farm` 清障计数为进度、按田区推进直到可清障碍为 0；journal `farm_progress`/`farm_cleared` + `day_end.farm_cleared`；缺字段/`complete=false` fail-closed；≥6 单测；验收=**一次完整清理**且外部 `observe?detail=full` 差分可核 | pending |
| **task-152** | dev-coder | 142 | **钱的三分配**：种子再投资 / 工具升级储备 / 缓冲；LLM 给分配意图（journal `money_plan{reserve_for_upgrade,spend_on_seeds,reason}`），代码算数字与兜底硬约束（**先留住下一件关键升级的钱 > 至少留 1 份种子钱 > 其余才买种子/囤货**）；缺字段保守；禁 `Money +=` | pending |
| **task-157** | dev-coder | — | **`water_far` 够不着时先有界开路再试**（run9d 实证：`[12,30]` 活苗干作物 `code=unreachable`，雨天掩盖、非雨天必破尾链）；仍走不到 ⇒ `water_far_blocked{tile,cause,attempts,cleared_tiles}` + 当天如实 `gave_up_dry`（**不许把开路当浇水**）；原因 `unreachable/no_route/need_refill/no_evidence/truncated` 显式分离；≥6 单测 + ≥2 变异 | **已交付 `ef59f30`**（Lead 亲核：2 文件 +351/−14、定向 463 OK、全量 822 其中 2 红＝analyzer 缺桶 ⇒ task-160） |
| **task-158** | dev-coder | 157 | **体力预算与规模控制**：`water_reserve = 活苗×2.0 + 12`、`capacity=(max−reserve−5)//2`、预算不足时 clear/till/plant 停手（journal `deferred_by_budget`）、`farm` 计数不可用 ⇒ `basis="conservative"`（全留给浇水）；常量集中在 `farmwork.py`（**未标定估算** ⇒ task-161） | **已交付 `cf7432a`**（Lead 亲核：3 文件 +293/−4、定向 470 OK、全量 829 其中 2 红同上）；两点裁定已发：超载时"只浇水"保持、不许加清障底（补 harvest/clear_dead 不被延后的测试）、预算必须取 `farm` 块 |
| **task-159** | deputy-lead | 157,158 | 对 157+158 的**独立对抗验收**（少干活/开路当浇水的洗白通道；`docs/_review-task157-158.md`） | **PASS**（`ad34bf6`）：task-157 PASS / task-158 PASS-WITH-NITS 无必修；B 段 22/31→35/35；正对照 SHA256 逐字相同；C 段 8 组全过 |
| **task-160** | log-analyst | 158 | analyzer 收录 157/158 新事件与字段（`water_far_open`/`water_far_blocked`/`stamina_budget`/`deferred_by_budget`）⇒ **全量回 0 红** | **已交付 `694c7b0`**（3 文件 +461/−7；全量 **838 OK / 0 红**；12 账本 rc 与 `verify-run3` 并排一字未变） |
| **task-161** | dev-coder | 20 | **阶段体力实测留痕与标定**：stage 记录补 `stamina_before/after/spent` + `day_end.stamina_calibration`（按 stage 的 `actions/per_action`）；只留痕不改判据；用于把 `farmwork.py` 的估算常量换成实测值（改常量单独一步、须过对抗验收） | in_progress |
| **task-164** | log-analyst | 20 | analyzer 收录 task-20 新事件 `blocked_by_tool` / `blocked_by_tool_summary` ⇒ **全量回 0 红**（0.7.32 放行条件） | in_progress |
| **task-163** | dev-coder | 161 | **预算延后不得变成"还有活"**（task-159 NIT-1/NIT-2）：延后任务的格子不再进守卫理由（改走显式延后 + 日级按任务留痕）、容量命中加可见 journal；验收目标 = 被预算卡住但该做的都做了的一天**必须能 `verified=true`**，且不许洗白 | pending（0.7.32 冻结前最后一张脑侧卡，`blocked_by task-161`） |
| **task-20**（Mod 侧并入 155） | dev-coder | 155 | 脑侧消费 `clumpKind/clumpTarget/toolOk`：**工具等级不够的地 0 次 `use_tool` + 当天封格 + 不算活**；缺 `clumpTarget`/`minLevel=null` ⇒ fail-closed 不挥；weed/twig/stone/tree/grass 不动 | **已交付 `1a86192`**（Lead 亲核：恰 4 文件 +339/−10、越界零命中、定向 484 OK、全量 849 其中 2 红＝analyzer 缺桶 ⇒ task-164） |
| **task-154** | dev-coder | — | 种子识别不许只靠名字：结构性识别（`Crop` 数据/`Data/Shops` 交叉）+ `seed_source` + `seed_unknown` fail-closed（来源 task-145 INFO-1） | pending |
| **task-110** | dev-coder | — | **桥异常绝不许穿出 `run()`**：`ensure_location`/`snap`/`sleep` 三处 + 顶层兜底，任何 `BridgeError` 都要落 `finish` 并如实记因（来源 task-108 NIT-2 / task-145 NIT-1） | pending |
| task-109 / task-101 / task-107 / task-117 | dev-coder | — | 顺延 NIT：卖货如实性（卖最大叠 vs 文档说最小、卖后刷新 obs）、`_farm_totals` 类型校验、Mod `dryTiles`/`dryCrops` 同源、教训内容模板校验 | pending |

## §2 冻结与装机九步（Lead 独占，同 0.7.25–0.7.31 流程）

1. 确认本版所有卡 completed + 它们的对抗验收 PASS + **全量 `unittest discover -s tests` 0 红**；
2. `tools\_note-0732.txt`（首串必须是 `v0.7.32`）写完；
3. `python tools\_bump-mod-version.py 0.7.32 --note-file tools\_note-0732.txt` ⇒ 核对 `mod\AgentFarm.Bridge\manifest.json` 的 `Version`（cp1252 末句可能 `UnicodeEncodeError`、退出码 1，**版本已写盘**，一律用 `json.load` 核对）；
4. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.32"`；
5. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警告 0 错误**；
6. `git add -A` ⇒ 提交冻结（提交信息写清版本内容）；
7. `python tools\check-release.py --expect 0.7.32` ⇒ 六项全绿；
8. `python tools\deploy-mod.py --no-quit` ⇒ 桥 `modVersion=0.7.32`；
9. `python -m agentfarm goto Farm --no-focus` → `tools\preflight.py --expect 0.7.32 --save-baseline logs\run10b-baseline.json`。

## §3 起跑（目标 1 的真机验收跑）

- 目标 1 不要求"连续 N 天"，只要求**完成一次全部清理**：起跑用 `tools\start-detached-longrun.py --days 5 --size 5 --max-minutes 300 --max-days 15 --journal logs\longrun-clear-run1.jsonl --expect-version 0.7.32`（天数取宽，允许跨多天清理）。
- 每天 ≥2 份 `observe?detail=full` 端点（晨间 A + 收尾 B）⇒ 逐日世界差分表；清障进度以 `farm` 计数的 `complete=true` 快照为准（`FarmScanCache` 全农场口径，不受 400 格窗口影响）。
- 完成判据（外部可核）：`farm_cleared=true` 且**外部观测**里可清障碍计数（`weeds/stones/twigs/trees/stumps/logs/boulders/bushes`）为 0；`day_end.farm_cleared` 与之一致；存档落盘六串齐全。

## §4 判据

1. 两侧工具同向（`tools\verify-run3.py` 的 `verdict` + `strict_verdict` 两行都要抄；`tools\analyze-longrun.py --window N` rc 同向）+ `scratch\run9-lead-check.py --snapshots/--smapi` 无硬问题。
2. **缺失字段一律【无法判定】，缺失 ≠ 通过**；每个数字都要有外部证据（存档 size/mtime、SMAPI 行号、`observe` 端点）。
3. 钱：全程 `git grep -n "Money *+=" -- brain mod` 只许命中注释；买入/升级的花费一律走游戏自己的 `chargePlayer` 路径，判据用观测差分。
4. 工具等级不足**不许发请求空挥**（task-20 口径）；`clumpTarget` 缺失 ⇒ `precondition_failed` + 理由，不许默认斧头。
5. 升级发起前必须 `toolBeingUpgraded == null`（否则白扣钱 —— task-153 §7 已证陷阱）。
6. 口径变更（含 `checks` 新键、`TASK_KINDS` 新档）必须过一轮**独立对抗验收**才能拿去判真机账本。
7. **够不着的活苗干作物不许洗白**：`watered_outdoor` 只认逐格证据（该格 `watered=true` 或该格不在新鲜 `farm.dryTiles`）；走不到的格如实 `gave_up_dry` + 当天不 VERIFIED。run9d 的 `[12,30]` 就是这一类（雨天掩盖），修法是 task-157 的"先开路再试"，**不是**放宽判据。

## §5 待写（跑完后填）

- run 表（逐日 `ended_by`/`verified`/清障增量/钱/工具等级）、清障前后外部差分、升级链真机留痕、两侧工具原文、结论。

## §6 遗留 / 顺延

- task-14（逐帧 warp 活锁，run9d 仍 2200 次）、task-83/task-94（田块规整）、task-17（world_stuck 自愈）、task-18（职业耕种优先）、task-53（农场级待清/待垦计数）、task-137（非 sleep 收尾分支 `final` 快照滞后）、task-154（种子结构性识别 + `seed_unknown`）、task-110（桥异常绝不许穿出 `run()`）、task-109/101/107/117（顺延 NIT）。

## §7 拆版记录（2026-10-17，run9d 结论后）

- **0.7.32（本版）** = `task-157`（`water_far` 够不着先有界开路）+ `task-158`（体力预算与规模控制）+ `task-155`（Mod 障碍物/工具等级元数据）+ `task-20`（脑侧消费，`blocked_by task-155`）+ `task-159`（对 157/158 的独立对抗验收）。
- **移到 0.7.33**（目标 1 主体）：`task-141`（Brief 暴露 `tool_levels`/`obstacles_by_tool` + `tool_upgrade` 建议意图）、`task-142`（铁匠铺升级链 `upgrade_tool` + 主动升级闭环）、`task-151`（全场清理收敛 + `farm_cleared` 完成判定）、`task-152`（钱的三分配：种子/升级储备/缓冲）。
- **顺序**：`157 → 158`（目标 2 关键路径，已交付）+ `155 ✅ → 20 → 161 → 163`（Mod 元数据 → 脑侧消费 → 体力标定 → 预算延后口径）⇒ `task-159` 对抗验收 ✅ + `task-160`（analyzer 回 0 红）✅ ⇒ Lead 冻结装机 ⇒ **run A / run B（同一 0.7.32 构建）** ⇒ 结论。
- **A→B 对照口径（`docs/_run10-criteria.md`，提交 `54f8d07`）**：run A 与 run B 必须是**同一份 0.7.32 构建**、同参数（`--days 5 --size 5 --max-minutes 240 --max-days 12`），**唯一差异 = 注入的教训/笔记/决策史**；run9/run9b/run9c/run9d 都**不参与** A→B（它们分别是旧构建/诊断跑）。A 的初始教训库允许继承 run9d 的（双账本记录：继承 vs 本轮新增），B 用 A 的库显式拷贝。
- **附加说明**：`task-161`（阶段体力标定）是 0.7.32 的**最后一张脑侧卡**；若它能在冻结前落地，A/B 两次跑的口径必须一致（`stamina_calibration` 只留痕、不改判据 ⇒ 允许同版共存）。
