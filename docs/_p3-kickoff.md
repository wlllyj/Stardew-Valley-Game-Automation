# P3 启动计划 · 农场清理 + 规划种田（端到端、无人介入）

> 写在 P2 收尾之后（2026-10-11 晚）。P2 的可判定验收现状见 `00-开发日志.md` 条目 016/019
> 与 `01-架构设计.md` §8。本文只讲 **P3 要做什么、缺什么、按什么顺序做**，便于新会话直接接手。

## 1. 目标（架构 §8 · P3）
给定任务：「清理 A 区域障碍 → 开垦 N 格 → 种下防风草 → 浇水」，**全自主完成**，且由游戏状态判定
（地块数、作物数、已浇水数、背包变化）；自主处理体力不足（进食/回家睡觉）与时间耗尽（睡觉），
**连续 3 个游戏日无人工介入**；失败经验进记忆、跨日失败率下降。

## 2. 手上已有的能力（真机验收过的）
| 能力 | 技能 | 真机结果 |
|---|---|---|
| 走一格（不越界、不停错格） | `move_to` | 落点契约 18/18（`tools\verify-landing.py`） |
| 跨地点（含进屋/出门两种机制） | `move_to_location` | FarmHouse ⇄ Farm 往返 6/6；正向走室内 warp `(3,12)`，反向在门前调 `checkAction((64,14))` |
| 用一下面前那格（门/机器/交互的总入口） | `interact` | `checkAction` 返回 True，0.6s 进 `FarmHouse(3,11)` |
| 读档 / 关游戏 | `load_save` / `quit_game` | 4/4；配合 `tools\deploy-mod.py` 构成无人值守部署闭环（4/4） |
| 关模态（救命） | `dismiss_modal` | 条目 013 事故后重写，成功判据是"世界恢复" |
| 感知 | `observe?detail=summary/full` | 时钟/玩家/农场摘要/家具/门清单 |

## 3. 缺什么（按依赖顺序）

### ① 感知：**脑目前看不见"哪一格上有什么"**（最硬的缺口）
现状：`location.objects` / `location.terrainFeatures` **只有计数**（如 `weeds=456, stones=247`）。
计划：给 `observe?detail=full` 增加**逐格清单**（新段 `tiles[]`，快照升 `agentfarm-world/6`）：
```
tiles: [ {"tile":[x,y], "kind":"weed|twig|stone|tree|grass|hoeDirt|water|building",
           "tool":"scythe|axe|pickaxe|hoe|can|none", "crop":"Parsnip", "ripe":false,
           "watered":false, "reachable":true} , … ]
```
只输出**玩家附近 + 农场可耕作区域**的格子（限制体积；`summary` 不含）。
判据来源全部问游戏：`loc.objects[key]`（`Object.IsWeeds()/IsTwig()/IsBreakableStone()`、`Object.ItemId`）、
`loc.terrainFeatures[key]`（`Grass/HoeDirt/Tree/ResourceClump`）、`HoeDirt.crop`、`HoeDirt.state`。
> 这一步不做，规划层就只能"猜格子"，必然重演旧项目"照着 LLM 给的坐标乱走"的老毛病。

### ② 动作：`use_tool(tool, tile)` —— 用当前工具对某格动手
要点：**别自己写锄地/砍树逻辑**，找游戏自己的入口。候选（需 api-probe + IL 定论，顺序即优先级）：
1. `Game1.pressUseToolButton()`（玩家按 C/鼠标左键走的那条）；
2. `Farmer.UseTool(GameLocation, int x, int y)` / `Farmer.BeginUsingTool()` / `Farmer.completeToolUse()`
3. 后备：`GameLocation.checkAction(...)`（只对"动作格"有效，砍草/敲石不是动作格）。
验收：`(a)` 每格操作前后用 `tiles[]` 差分证实"该格真的变了"（**不允许**用回执当证据）；
`(b)` 位置必须**面朝**目标格（`FacingDirection`），必要时应先转身 —— 转身也要走游戏自己的入口。

### ③ 物品与背包：`select_item(item_id)` / `plant(seed, tile)` / `pickup_debris(tile)`
* `select_item`：读 `player.Items` 找 id → 设 `player.CurrentToolIndex`（+ 确认 `CurrentItem` 真的变了）；
* `plant`：选中种子 → 对目标格用（游戏自己的 `Object.performUseAction` / `pressUseToolButton` 二选一，先探针）；
* `pickup_debris`：走到格上（`move_to`）后游戏通常自己会捡；捡不到再走 `checkAction`。
* 背包满/体力不足必须**显式报错**（`precondition_failed` + 可操作 reason），不许静默丢东西。

### ④ 体力与时间：`eat(item)` / `sleep()`（＝走到床边 + `allow_bed` + `dismiss_modal` 的"是"分支）
注意条目 013 的教训：睡觉确认框**不能盲按确认键**；要用 `answerDialogue(Response)` 选"是"，
并验证"世界真的进了下一天"（`clock.day` 变化 + `hasSaveLoaded`）。

### ⑤ 规划层（脑侧）：任务队列 + LLM 边界
* 结构：`observe(tiles) → 选任务（代码）→ 技能序列（代码）→ 每步用 observe 复核 → 记账`；
* **LLM 只在边界出现**（换任务类型、异常恢复、跨日复盘），不参与逐格执行 —— 这是 P1 的核心决策，别忘；
* 未完成时**不许报成功**：任务终态只有 `VERIFIED` / `needs_review`（架构 §5.4）。

### ⑥ 安全网接入运行循环（旧账，条目 00888）
`brain\agentfarm\watchdog.py`（20 个测试）目前只有 `agentfarm triage` 手动跑；P3 必须把它**接进运行循环**：
每 N 秒 `assess()`，`verdict=stop` 时落 `logs\stops\stop-*.json` 并调用 `quit_game` 收工（不要半死不活地重试）。

## 4. 建议的推进顺序（每步都要真机验收）
1. **⑥ 先接安全网**（1 小时级）：P3 是长跑，没有看门狗会重演旧项目"40 分钟空转没人发现"。
2. **① 逐格感知**（world/6 + 脑侧解析 + 单元测试）：让脑第一次"看得见农场"。
3. **② `use_tool`**（探针定入口 → 实现 → 真机对 10 格做差分验收）。
4. **③ `select_item` / `plant`**（先手动种一格并差分验收，再做 10 格）。
5. **⑤ 规划层最小闭环**：一块地（如 5x5）→ 清障 → 锄地 → 种 → 浇水，全程 observe 复核。
6. 扩到目标区域 + 体力/时间处理 → 跑满 **3 个游戏日无人介入**。

## 5. 纪律提醒（都是踩过的坑）
* **只信游戏证据**：回执是声明，`observe` 才是证据；每步都要差分复核。
* **不伪造键鼠**：优先调游戏自己的入口（`checkAction` / `pressUseToolButton` / `answerDialogue` 的先例）。
* **不硬编码坐标**：区域用相对玩家/建筑的锚点或 `tiles[]` 真值表达（§5.2.1）。
* **改 Mod 必须重启游戏**：用 `tools\deploy-mod.py`（自己关 → 换 → 开 → 读档），一次攒够再部署。
* **改文件别用 PowerShell 字符串读写**（会把 UTF-8 中文读成 cp1252 乱码）：用编辑工具或 Python。
* **异步动作要等够**：传送/淡出期间不下任何"失败"结论（条目 019 教训 2）。
