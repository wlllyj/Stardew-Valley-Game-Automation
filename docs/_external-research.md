# Stardew Valley 自主 AI Agent —— 外部开源项目与学术工作调研

> 用途：自研架构决策参考。调研时间 **2026-10-11**（Bangkok，UTC+7）。
> **可信度标记**：`[自述]` = 项目 README／官方页面自述；`[证据]` = 代码或文档中可直接核对的内容；`[推断]` = 本次调研的分析推断。
> **数据纪律**：star 数、提交时间均取自 GitHub REST API（`api.github.com/repos/...`）实时查询；查不到的写「未确认」，不估算。

---

## 0. 结论速览（TL;DR）

1. **社区已收敛到「SMAPI mod 暴露结构化状态 + 动作」路线**，本次检索到的十余个可实际操控游戏的项目**没有一个**用纯视觉+模拟输入来闭环控制农务。视觉只作为「附加观察/问答」（StarDojo 的 `image_obs`、Stardew-Sage 的截图问答）。[推断]
2. **LLM 定位的共识是「低频决策 + 代码高频执行」**，没有人让 LLM 每 tick 决策。关键量化证据：StarDojo 基线 `Latency/Step 48.7s`、ReAct-like `24.5s`（SPIKE 论文），而游戏 1 游戏日 ≈ 14 分钟真实时间。[证据]
3. **「LLM 输出动作序列被执行器大量 SKIP」这类开放环失败，在社区里是被明确讨论并已被工程化规避的**，但通常不叫这个名字，而是以「前置条件校验 / 候选（affordance）生成 / 执行契约 / 动作回执」等形式出现。已收集到 6 类具体做法，见 §4。
4. 目前唯一有**端到端长程无人值守成功记录**的开源项目是 [`Zsh123456-BOOP/stardew-together`](https://github.com/Zsh123456-BOOP/stardew-together)：**153 小时无人值守跑完全成就**，1.7451 亿 token，约 ¥213.3。[自述] 这是本次调研最有价值的对标对象。
5. **学术 benchmark 的天花板极低**：StarDojo-Lite 上最强模型 GPT-4.1 总成功率 **12.7%**，中/高难度接近 0。[证据]

---

## 1. 项目清单与元数据（GitHub API 实测）

| 项目 | Star | 语言 | 最后推送 | 创建 | 许可 | 游戏接入 | 人机接口 | LLM 位置 |
|---|---|---|---|---|---|---|---|---|
| [Zsh123456-BOOP/stardew-together](https://github.com/Zsh123456-BOOP/stardew-together) | 147 | C# | 2026-09-23 | 2026-07-31 | **无 LICENSE 文件** | SMAPI mod（原生状态） | 游戏内面板 F8/F10 + 工具调用 | LLM 低频选目标，算法做细节 |
| [Hunter-Thompson/stardew-mcp](https://github.com/Hunter-Thompson/stardew-mcp) | 164 | C# | 2026-02-05 | 2026-01-20 | 未确认 | SMAPI mod + WebSocket | MCP(Go) + WS `ws://localhost:8765` | LLM 每步决策 + 30 个 cheat |
| [anqinou-art/NagiBridge](https://github.com/anqinou-art/NagiBridge) | 105 | C# | 2026-09-19 | 2026-04-24 | MIT | SMAPI mod HTTP API | HTTP :7842/:7843 + MCP :9000 | 脚本(代码)控制 + LLM 写脚本 |
| [StarDojo2025/stardojo](https://github.com/StarDojo2025/stardojo) | 73 | Python+C# | 2025-11-03 | 2025-05-16 | MIT | SMAPI mod（StarDojoMod） | Python socket wrapper | LLM 每步决策（有 planner pipeline） |
| [amarisaster/StardewValley-MCP](https://github.com/amarisaster/StardewValley-MCP) | 29 | C# | 2026-06-04 | 2026-02-22 | 仓库 `license: Apache-2.0`（README 写 MIT，冲突） | SMAPI mod + JSON 文件 | MCP(Node) 25 tools | LLM 每步（player 模式）/ 自主模式 |
| [Zhang-986/Stardew-Sage](https://github.com/Zhang-986/Stardew-Sage) | 26 | Vue/Java | 2026-09-26 | 2025-07-24 | MIT | **不接入游戏** | MCP :8099 + SSE | LLM 问答/RAG，**非游戏控制** |
| [wencanjiang/SPIKE](https://github.com/wencanjiang/SPIKE) | 20 | Python | 2026-05-20 | 2026-05-13 | MIT | 复用 StarDojoMod | StarDojo wrapper | **双控制器**：战略低频 + 反应高频 |
| [sei-studio/sei](https://github.com/sei-studio/sei) | 19 | TypeScript | 2026-10-11 | 2026-04-24 | AGPL-3.0 | 未确认（跨游戏同伴） | 未确认 | 未确认 |
| [kogazz/stardew-llm-agent](https://github.com/kogazz/stardew-llm-agent) | 15 | Python+C# | 2025-10-12 | 2025-10-11 | 未确认 | SMAPI mod + FastAPI | 游戏内聊天 `!` 前缀 | **只对话，不控制游戏** |
| [rottenpen/agent-stardew](https://github.com/rottenpen/agent-stardew) | 10 | TypeScript+C# | 2026-09-20 | 2026-09-19 | MIT | SMAPI mod | WebSocket `ws://127.0.0.1:17655/` + dsh 插件 | LLM 每步（多问题决策） |
| [JoeStrout/Farmtronics](https://github.com/JoeStrout/Farmtronics) | 55 | C# | 2025-09-05 | 2021-11-17 | MIT | SMAPI mod（游戏内机器人） | 游戏内编程终端 | **无 LLM**（玩家写程序） |
| [Cabbagito/Junimo-Kart-AI](https://github.com/Cabbagito/Junimo-Kart-AI) | 13 | Python | 2023-01-28 | 2023-01-28 | 未确认 | 视觉/RL | 无 | RL，非 LLM |

> 补充：`onp-china/RL_in_StardewValley`(2★)、`CrazyBong/Autonomous-Stardew-Valley-Agent-ASVA-`(1★)、`luy-0/StardewValley-MCP`(5★)、`shylux/StardewMCP`(1★)、`irenegu-xiaoyu/my_junimo_assistant`(5★) 均在检索结果中出现但未深入核实，标为未确认。

---

## 2. 逐项目梳理

### 2.1 ⭐ `stardew-together`「同行」— 唯一有长程无人值守完整战绩的项目

- **技术栈** `[证据]`：C# SMAPI mod（`mod/Together/`、`mod/AgentBridge/`、`mod/SquadAdapter/`）+ Python 构建/启动脚本；模型 **DeepSeek Flash**；`vendor/Farmtronics/` 为固定版本子模块。
- **游戏接入** `[自述]`：「Together **直接通过 SMAPI 读取游戏状态，无需逐帧截图识别**；正式运行也不依赖常驻 Python 决策服务。」→ 路线 **B（结构化状态）**。
- **控制循环位置** `[自述]`：「**大模型负责有意义的选择，算法负责可计算的细节**。寻路、挥锄、拾取等连续子动作由执行器推进，不需要每一步都重新请求模型。」→ **LLM 低频、代码高频**。
- **关键战绩** `[自述]`（README 表格，来源：[README](https://github.com/Zsh123456-BOOP/stardew-together)）：
  - 参考人类时长：基础 40 项成就约 **150–200 小时**
  - **Together 全成就运行用时：153 小时，Windows**
  - DeepSeek Flash 总用量（日志折算）：**1.7451 亿 token**
  - 完成全部成就的 API 总费用：**人民币 213.3 元**
- **验证环境** `[自述]`：macOS、Stardew Valley **1.6.15**、SMAPI **4.5.2**、.NET SDK 6、Python 3.11+。
- **已知局限** `[自述]`：「自主控制玩家是当前主要运行形态。**全成就闭环、自定义伙伴协作与中后期完整生产链仍在持续完善**。」
- **许可证风险** `[证据]`：GitHub API 返回 `license: none`——仓库**未声明许可证**，不能直接复用其代码。这是本项目相对其他候选最实际的短板。

**值得直接抄的 5 个设计（均有源码文件路径）** `[证据]`：
1. **执行契约 + 前置条件校验**：`ExecutionContract.cs`——「检查决策是否过期、参数与执行条件」，再交给执行器。
2. **异步任务回执与账本分离**：「购买请求入队时**不会增加已购数量**，只有原生到货证据才更新账本与记忆。」（**这正是开放环失败的正面解法**）
3. **三类记忆分离**：事实事件 / 计划承诺 / 经验总结；「**历史流水不累加成当前库存，计划不算已完成，摘要也不能覆盖实时状态**」，模型日总结必须引用给定事件中的有效证据 ID。
4. **上下文投影而非追加历史**：`DecisionContext.cs`、`OnDemandContext.cs`、`ContextBudget.cs`；「关键状态超过硬预算时**明确报错，不静默删除关键约束**」。
5. **工具按需加载 + 冻结契约**：`ToolSpec.cs`、`AgentToolDiscovery.cs`；「API 中的工具定义和调用参数校验**使用同一份冻结契约**」。

### 2.2 `Hunter-Thompson/stardew-mcp` — 星数最高，但已停更

- **技术栈** `[证据]`：C# SMAPI mod（.NET 6）+ **Go** MCP server + GitHub Copilot SDK（Claude Sonnet）。
- **接入/接口** `[证据]`：WebSocket `ws://localhost:8765/game`，JSON 请求/响应；12 个 AI 工具 + **30 个 cheat 工具**；61×61 ASCII 地图视野（`get_surroundings`）。
- **控制循环** `[证据]`：`StardewAgent` 自带 autonomous loop，`-goal "Clear the farm and plant parsnips"`，`-auto=false` 可关。→ **LLM 在环内逐步决策**。
- **活跃度** `[证据]`：164★ 但最后推送 **2026-02-05**，此后无提交（约 8 个月）。
- **已知局限** `[证据]`：README 自陈 pathfinding 最多重算 5 次、「Some areas may be unreachable due to obstacles」；工具冷却 30 game ticks；依靠 cheat 能力（`cheat_grow_crops` 等）来「绕过」执行困难——**对评测有意义，对真实长期游玩等于绕过游戏**。
- **许可** `[证据]`：API 返回无 license → **不可复用**。

### 2.3 `anqinou-art/NagiBridge` — 「代码控制器 + LLM 写代码」路线的代表

- **技术栈** `[证据]`：C# SMAPI mod（HTTP server）+ 10+ 个 Python 活动脚本 + Bun/MCP channel server + tkinter 聊天气泡。
- **接入** `[证据]`：HTTP `:7842`(host) / `:7843`(farmhand)，**40+ 端点**（移动/工具/交互/warp/菜单/制作/机器/动物）；MCP channel `:9000`。
- **控制循环** `[证据]`：`scripts/farm_row.py`、`water_crops.py`、`chop_trees.py`、`mine_run.py` 等**每个脚本就是一种农场活动的完整代码控制器**；LLM（Claude Code）负责**写和调度脚本**，不在每步决策。小游戏 bot（草原国王、21点）是「LLM 写算法 → 算法每 tick 执行」。→ **LLM 离线规划，代码在线执行**。
- **踩坑记录 = 极佳的失败模式素材** `[自述]`（[PROJECT.md](https://github.com/anqinou-art/NagiBridge/blob/main/PROJECT.md)）：
  - 「**万亿参数不会开门 → warp 绕过**」——即 LLM 做不好精确低层操作，直接用 teleport 替代。
  - 「**move_to 落点偏 1 格 → 精确操作用 warp**」——低层动作不可靠时改用确定性通道。
  - 「**背包满 give/craft 静默掉落 → 操作前检查空间**」——**典型的前置条件校验解决开放环失败**。
  - 「pyautogui 夺舍输入法 → 改用 channel server」；「游戏运行时 DLL 被锁 → 必须先关游戏再复制」——注入/热更新的工程约束。
  - 1.6 反射专项：字段名 `player2MovementDirections` 变更、`FirstField` 多候选名 fallback、Harmony 时序问题（`SMAPI UpdateTicked 在 Game.Update 之后`）。→ **直接印证 §6 的版本脆弱性**。
- **活跃度** `[证据]`：105★，最后推送 2026-09-19，MIT → 相对健康、可参考。

### 2.4 `StarDojo2025/stardojo` — 环境与 benchmark 的「标准答案」

见 §5 专项。

### 2.5 `amarisaster/StardewValley-MCP` — MCP 形态 + 「影子农夫」模式

- **技术栈** `[证据]`：C# SMAPI mod + Node/TS MCP server（stdio），README 写「25 tools = 13 global + 12 player 模式」。
- **核心巧思** `[证据]`：**Shadow Farmer 模式**——一个可见的 NPC（自定义 sprite + 寻路）配一个不可见的 `BotFarmer : Farmer` 影子实例，由影子实例通过真实游戏 API 执行工具/战斗/钓鱼。`draw()` 置空。灵感来自 Farmtronics。
- **关键工程注记** `[证据]`：影子农夫**故意不加入 `Game1.otherFarmers`**，因为该表网络同步且 `Multiplayer.updateRoots()` 会因非网络支撑的 farmer 而 NPE。
- **对「LLM 太慢」的正面处理** `[证据]`：README 明说 `stardew_set_auto_combat`「Real-time combat automation for when **LLM round-trips are too slow**」；钓鱼同理 auto-hook。→ **社区已明确承认 LLM 往返延迟是硬约束，用手写反应式控制器兜底**。
- **稳定性修复清单** `[证据]`（v0.2.1）：AI tick rate 从 2/sec 修到 60/sec、双向**原子文件写**、动作文件竞争修复、**farm mode stuck detection**、mine mode ladder descent、fishing timeout、**per-companion crash isolation**、**day transition safety**、sleep sync 防死锁。→ 这就是无人值守故障模式的实战清单。
- **许可** `[证据]`：**冲突**——GitHub API 报 Apache-2.0，README 末尾写「License: MIT」。使用前需澄清。

### 2.6 `rottenpen/agent-stardew` — 与本项目最同构的对标（中文、dsh 插件）

- **技术栈** `[证据]`：`packages/protocol`（协议）+ `packages/cli`（命令/连接）+ `packages/dsh-plugin`（工具 + skill + 控制器）+ `mods/AgentStardew`（C# SMAPI，主线程执行）；Node 22+/pnpm。
- **接入** `[证据]`：WebSocket `ws://127.0.0.1:17655/`；README 明确「Mod 支持**失焦后台运行**，后台游戏时间会继续推进」。基线：**Stardew Valley 1.6.15、SMAPI 4.5.2**，`.NET 6`。
- **控制循环位置** `[证据]`（[jev-runtime.md](https://github.com/rottenpen/agent-stardew/blob/main/docs/jev-runtime.md)）：控制器在 dsh 插件内（`packages/dsh-plugin/src/agent/`：`candidates.ts`、`jev-client.ts`、`memory.ts`、`planner.ts`、`runner.ts`）。**「正常游玩循环无需聊天模型参与」**；聊天模型仅做可选阶段规划（`StagePlanner`）。
- **决策粒度** `[证据]`：每轮一个 OpenRouter 请求（`~typesafe/jev-latest`，`/api/alpha/decisions`），同时回答多问题（`intent` + 每类别一个 `action_<类别>`），**「最多执行一个原子命令」**；「移动期间交由 Mod 寻路……**不会每走一格重新请求模型**」。
- **实测延迟** `[证据]`：mock 农场 + 真实 Jev 5 次请求完成「种 1 颗防风草并浇水」，各次耗时 **4384 / 825 / 607 / 488 / 566 ms**。→ **这是本项目可用的延迟基线，比 StarDojo 的 48.7s/step 快约 2 个数量级**，因为动作粒度粗、无视觉输入。
- **对开放环失败的防线** `[证据]`：① 候选带前置规则（`diggable`、工具类型、种子类别、`needsWater`、`refillable`）；② 返回值必须属于当前候选集；③ 「过期任务修订或取消后的响应都不能执行」；④ 相同前提下失败的动作暂时排除，条件变化后允许重试；⑤ 停滞计数 + 具体阻塞上报；⑥ **`needs_review` 与 `completed/VERIFIED` 严格区分**（「不能直接宣称完成」）。
- **已暴露的真实游戏 bug** `[证据]`（[verification.md](https://github.com/rottenpen/agent-stardew/blob/main/docs/verification.md)）：礼盒交互误报 `UNSUPPORTED`（旧实现只查地图/菜单引用，未查菜单签名+背包变化）；农舍出口坐标在地图边界外一格导致寻路拒绝；`IInputHelper.Suppress` 语义是**屏蔽按键而非释放按键**，导致残留输入干扰后续移动。
- **已知局限** `[自述]`：「**完整真实游戏农务与自主补能力验收仍待完成**」「商店购买、容器取放等仍需补齐基础接口」；验收标准为「同一基线跑 5 次 Jev 自主任务，**至少 4 次**由游戏状态证明成功」——**尚未达成**。

### 2.7 `kogazz/stardew-llm-agent` / `Stardew-Sage` — 反例（不是游戏 agent）

- `stardew-llm-agent` `[证据]`：SMAPI mod（HarmonyLib hook 聊天）+ FastAPI + GPT-4o-mini/Ollama，**只回复建议**（`!qual semente...`），不控制角色。路线 **C 的退化形态**（读结构化状态做问答）。
- `Stardew-Sage` `[证据]`：Spring Boot 3 + Spring AI + MySQL + RedisStack 向量库 + Vue；**完全不接入游戏进程**，只做数据问答/RAG/截图分析。与自主游玩无关，可借鉴的是**游戏数据库建模**（20+ 张表）与 RAG 检索。
- 结论 `[推断]`：**「能聊天」与「能干活」在这个领域是两件事**，检索结果里后者数量远少于前者。

---

## 3. 技术路线对比

三条路线：(A) 纯视觉 + 模拟输入（pixel/OCR/YOLO）；(B) SMAPI mod 暴露结构化状态 + 动作；(C) 混合。

| 维度 | A 纯视觉 + 模拟输入 | B SMAPI mod 结构化 | C 混合 |
|---|---|---|---|
| **可靠性** | 低。StarDojo 作者称游戏「只能通过截图观察 + 键鼠控制」，他们**专门做了 StarDojoMod 来摆脱它**；GUI 失败模式研究把 grounding error / 隐藏操作盲区列为独立失败类 `[证据]` | 高。状态是引擎真值，动作直接走游戏 API，无需坐标映射 `[证据]` | 中高 |
| **开发成本** | 高（需自建感知 + 坐标标定 + 输入注入），且**每个新场景都要重做** | 中（C# mod 开发，但字段一次对齐后复用） | 高（两套都要维护） |
| **泛化性** | 跨版本/分辨率/UI 主题脆；但**不需要游戏源码** | 依赖游戏内部字段，版本内泛化好 | 中 |
| **版本升级脆弱性** | 视觉相对稳（UI 变了才坏），但坐标/像素匹配会坏 | **最脆**：1.6 是 mod 灾难，见 §6.3 | 中 |
| **延迟** | 高（截屏+推理） | 最低（StarDojo 称共享内存把观察取回降到 **30 ms**）`[证据]` | 中 |
| **无人值守可行性** | 未见成功案例 | **有**（stardew-together 153h 全成就）`[自述]` | 有（StarDojo 用它跑 benchmark） |
| **反作弊/ToS** | 更接近「外挂」，风险感知最高 | SMAPI 是官方社区框架，风险最低 | 中 |

**本次检索到的实际分布** `[推断]`：可闭环操控农务的项目 **100% 走 B（或 B+少量视觉附加）**；纯视觉仅出现在 RL 小游戏（[Junimo-Kart-AI](https://github.com/Cabbagito/Junimo-Kart-AI)）和文档问答。

**证据引文**：
- StarDojo 官方页：「Stardew Valley only supports human-like interaction, e.g., observing gameplay through screenshots and using keyboard and mouse... The game must remain active and focused in the foreground, which **severely limits** the ability to automate gameplay」——他们因此引入 StarDojoMod 提供「rendered gameplay images... **internal game states**... **diverse callable functions as action skills beyond traditional keyboard and mouse inputs**」。[来源](https://stardojo2025.github.io/stardojo/)
- StarDojo 性能归因：失败「primarily due to challenges in **visual understanding, multimodal reasoning and low-level manipulation**」。[来源](https://stardojo2025.github.io/stardojo/)
- NagiBridge 踩坑：「万亿参数不会开门 → warp 绕过」「move_to 落点偏 1 格 → 精确操作用 warp」。[来源](https://github.com/anqinou-art/NagiBridge/blob/main/PROJECT.md)

> **给本项目的结论** `[推断]`：**不要走纯视觉**。这与已知起点（agent-stardew 用 SMAPI + WebSocket）一致。视觉可作为**可选第二观察源**用于「未预期状态」诊断，但不进主控制环。

---

## 4. LLM 在环的位置 & 「开放环失败」

### 4.1 行业做法：LLM 每一步都决策 vs 低频规划

| 做法 | 代表项目 | 延迟/成本证据 | 失败率证据 |
|---|---|---|---|
| **每步 LLM 决策**（原始 ReAct 式） | StarDojo 基线、Hunter-Thompson MCP、agent-stardew 每轮 | StarDojo 基线 **48.7 s/step**、295.9k tokens/task；ReAct-like **24.5 s/step**、102.6k tokens/task `[证据]`（SPIKE 论文表） | Lite-100 SR：StarDojo 12.3%、ReAct-like **6.7%** `[证据]` |
| **低频战略 + 高频代码执行**（双控制器） | **SPIKE**、stardew-together、NagiBridge | SPIKE **43.5 s/step**、168.1k tokens/task，比 CRADLE 省 **54.9% token、40.8% 延迟** `[证据]` | SPIKE Lite-100 SR **18.0%**，比最强基线 CRADLE(13.0%) **+5.0 pt**，Budgeted SR **+9.3 pt** `[证据]` |
| **LLM 离线写代码，代码在线跑** | NagiBridge 小游戏 bot、Farmtronics | 在线零 LLM 调用 `[证据]` | 未确认（无统一评测） |

**关键推论** `[推断]`：SPIKE 用**同一批任务、同一模型族**证明——把战略推理「摊薄」到有意义的边界、剩下的交给受约束的反应式控制器，能**同时**提升成功率、降低 token 和延迟。这不是取舍，是纯改进。**这就是我们架构应该采用的形状。**

SPIKE 的具体机制（[项目页](https://wencanjiang.github.io/projects/SPIKE/)）`[自述]`：
1. **Event-triggered amortized deliberation**：战略推理在稳定局部区间被**复用**，仅在 visual / progress / repetition / **failure** 边界重新调用。
2. **Adaptive dual-controller**：Strategic Controller 负责规划与恢复；bounded Reactive Controller 做快速局部执行与 **local override**。
3. **Controller-specific hierarchical memory**：常规执行查 State-Action Memory Bank，重规划查 State-Action Knowledge Graph。
4. 指标含 **Recovery/Stuck Ratio**（SPIKE 2.75 vs ReAct-like 1.61）——**长程 agent 应该报「卡住/恢复比」，而不只是成功率**。
5. SPIKE 默认模型为 Qwen3.5-397B，Lite-100 划分 **56 easy / 23 medium / 21 hard**，3 次重复运行。arXiv: [2605.18636](https://arxiv.org/abs/2605.18636)

**延迟的物理约束（重要）** `[证据]`：Stardew Valley 一个游戏日约 **14 分钟真实时间**（06:00→02:00，每 10 游戏分钟 = 7 真实秒）。若每步 48.7 s，一个 150 步 cap 的高难度任务 **光推理就约 2 小时**，而游戏内时间还在流逝。→ **LLM 不可能在环内高频决策**，必须异步/摊薄。这也直接回答了「LLM 输出动作序列」这种做法的动机。

### 4.2 「LLM 输出结构化动作序列后被执行器大量 SKIP」——别人讨论过吗？

**结论：讨论过，但以「前置条件校验 / affordance / 执行契约」的名字出现，而不是「SKIP 率」。** `[推断]`

已收集到的 **6 类解法**（全部有项目出处）：

| # | 解法 | 出处与原文 |
|---|---|---|
| 1 | **前置条件校验（在执行前判定动作是否可能有意义）** | ① agent-stardew：候选生成器「负责判断操作是否有现场依据」，候选只在「当前工具与相邻目标匹配」时生成 `[证据]` ② NagiBridge：「背包满 give/craft 静默掉落 → **操作前检查空间**」`[自述]` |
| 2 | **把动作池做成 affordance（只给模型合法的选项）** | agent-stardew：候选按操作类别分组，**返回值必须满足当前问题和候选集合**，未知选择不能执行 `[证据]`；Hunter-Thompson 的 `find_best_target` / `clear_target` 也是同类思路 `[证据]` |
| 3 | **执行契约 + 时效校验（拒绝过期决策）** | agent-stardew：「过期任务修订或取消后的响应都不能执行」`[证据]`；stardew-together `ExecutionContract.cs`：「**检查决策是否过期、参数与执行条件**，再交给执行器」`[证据]` |
| 4 | **动作回执与账本分离（结果由证据而非意图确认）** | stardew-together：「购买请求入队时**不会增加已购数量**，只有原生到货证据才更新账本与记忆」；「对于异步任务，最初回执可能只是『已接收／已排队』」`[证据]` |
| 5 | **失败反馈回灌 + 相同前提失败暂时屏蔽 + 停滞计数** | agent-stardew：「对相同前提下失败的动作暂时排除，条件变化后允许重试」；「位置往返且没有新增观察、资源或目标进展时**累积停滞计数**……达到限额后给出具体阻塞，避免持续消耗调用」`[证据]`；amarisaster 有 farm mode stuck detection `[证据]` |
| 6 | **不可靠低层动作直接换确定性通道** | NagiBridge：「**万亿参数不会开门 → warp 绕过**」「move_to 落点偏 1 格 → 精确操作用 warp」`[自述]`；StarDojo 甚至默认**禁用** `navigate` 技能 `[证据]`；amarisaster 用 auto-combat / auto-hook 兜底「LLM round-trips are too slow」`[证据]` |

**反面证据（说明「纯靠反馈还不够」）** `[证据]`：GUI agent 失败模式研究 [*Naive Visual Memory is Not Enough*](https://arxiv.org/abs/2606.14106)（2026-06）把失败分为 **cognitive failure / visual state misunderstanding / hidden operation blindness / grounding error**，并发现**全图记忆能减少状态级失败，却会加重动作级失败**（隐藏操作盲区与 grounding 错误）。→ `[推断]` 对我们是警示：单调增加观察/记忆并不能自动减少「动作被跳过」，必须**在动作层做约束**。

**我们该做的（映射到已知的 SKIP 问题）** `[推断]`：
- SKIP 不是 bug，是**缺乏「执行器知道为什么跳过」的通道**。要求执行器对每个被跳过/失败的动作产出**结构化 veto 原因**（缺前置、目标不可达、资源不足、状态已过期），并把 veto 原因回灌进下一轮候选生成——这正是 agent-stardew 的「候选 + 现场依据」和 stardew-together 的「执行条件检查」合起来做的事。
- 让 LLM 输出的**不是一个序列，而是一个意图**，序列由代码在满足前置条件时展开（stardew-together 的 `work.run` 就是「按工作类型组合参数与说明」）`[证据]`。

---

## 5. 评测与验证：StarDojo 拆解 + 可借用资产

### 5.1 StarDojo 基本信息

- 论文：[arXiv 2507.07445v3](https://arxiv.org/abs/2507.07445) ／ [OpenReview](https://openreview.net/pdf?id=jRi824qGpS) ／ [NTU PDF](https://www3.ntu.edu.sg/home/boan/papers/ECCV26_StarDojo.pdf)（ECCV 2026 / NeurIPS 2025 展示）
- 代码：<https://github.com/StarDojo2025/stardojo>（MIT，73★，最后推送 2025-11-03）
- 文档：<https://stardojo2025.github.io/stardojo/>（`/docs`；注意 `action_space/` 等子页在**根路径下 404**，真实路径为 `/stardojo/docs/action_space/`）
- Mod：Nexus Mods [mods/34175](https://www.nexusmods.com/stardewvalley/mods/34175)

### 5.2 环境接口设计（怎么观测、怎么操作）

- **观测** `[证据]`（[observation_space](https://stardojo2025.github.io/stardojo/docs/observation_space/)）：**结构化字典**，字段含 `energy / money / location / position / facing_direction / inventory / chosen_item`、`time / day / season`、`farm_animals / farm_pets / farm_buildings`、`surroundings`（相对坐标 + 对象标签，如 `"Type: Dirt"`, `"Diggable: True"`）、`crops / exits / buildings / furniture / npcs / shop_counters / current_menu`，以及可选的 `image_paths`（截图，由 `image_obs` 开关控制）。
  - 另有「轻量观测集」：health/energy/money/time/day/season/手持物品/36 格工具栏/当前菜单/周围方块。
  - 扩展点：改 `agent/stardojo/environment/stardew/stardew_env.py` 的 `_get_obs()`，**同时要改 prompt 模板**。
- **动作** `[证据]`（[action_space](https://stardojo2025.github.io/stardojo/docs/action_space/) + 源码 `agent/stardojo/environment/stardew/atomic_skills/basic_skills.py`）：**只有 9 个原子技能**——`move(x,y)`、`craft(item)`、`use(direction)`、`interact(direction)`、`choose_item(slot_index)`、`choose_option(option_index, quantity, direction)`、`attach_item(slot_index)`、`unattach_item()`、`menu(option, menu_name)`。全部经 `@register_skill(...)` 装饰器注册，通过 socket 发给 mod 的 `ActionProxy`。
  - **`navigate` 默认禁用**（源码中被注释掉，文档明说要手动在 `basic_skills.py` 开启）。→ **低层动作刻意保持最小、可控**。
  - 注释掉的还有 `move_step`、`turn`、`open_map`、`sell_current_item`、`take_from_chest`、`put_to_chest`——说明作者**主动裁剪**了动作空间。
- **并行与暂停** `[自述]`：每个实例独立端口，共享内存让观察取回低至 **30 ms**；支持 Xvfb 无头运行；**可配置的 pause-and-resume 通过直接修改游戏内部状态实现**，让游戏在 agent 规划时暂停、执行前恢复。→ **这是解决「LLM 慢 vs 游戏时间流逝」的另一种思路，值得评估**。
- **复合技能** `[证据]`：`agent/stardojo/environment/stardew/composite_skills/` 下有 `farm.py`、`go_home.py`、`go_through_door.py`、`shopping.py`、`buy_item.py`。→ 与我们的 `skill` 概念对应。
- **Agent 侧** `[证据]`：`provider/module/` 下有 `task_inference.py`、`information_gathering.py`、`action_planning.py`、`self_reflection.py`、`skill_curation.py`；感知栈含 `provider/object_detect/gd_provider.py`（GroundingDINO）、`sam_provider.py`（SAM）、`video/video_ocr_extractor.py`、`circle_detector.py`、`icon_replacer.py`、`template_matching.py`。→ **学术路线 = 结构化状态为主 + 视觉模型辅助定位**，路线 C。

### 5.3 任务定义与判定（**最可直接借用的部分**）

- **任务格式** `[证据]`（`env/tasks/task_suite/*.yaml`，如 `farming.yaml`）：

```yaml
clear_5_weeds_with_scythe:
  id: 0
  object: Weeds
  quantity: 5
  tool: Scythe
  save: save_new            # 指定起始存档
  init_commands: null       # 或 ['add_item_by_name("Golden Scythe")']
  evaluator: clear          # 判定器类型
  difficulty: easy
```

- **规模** `[证据]`：`farming.yaml` 首行注释 `# easy: 140, medium: 30, hard: 40, total: 210`；全库 **1000 任务**，5 大类（farming / crafting / exploration / combat / social），难度对应**启发式最大步数 30 / 50 / 150**；另有 **StarDojo-Lite 100 任务**（`StarDojo_Lite.xlsx`）。SPIKE 用的 Lite 划分是 **56 easy / 23 medium / 21 hard**（Farming 21 / Crafting 14 / Exploration 28 / Combat 12 / Social 25）`[证据]`。
- **判定实现** `[证据]`（`env/tasks/farming.py` + `env/tasks/utils/obs_check.py`）：按 `evaluator` 分派到 `clear / till / sow / water / fertilize / harvest / skill / open / close / pet / fill / incubate / friendship / mood / profession`，核心是 **`count_check(...)` / `surrounding_check(...)` 比较前后两次观测的差值**，累加到 `current_quantity`，`>= quantity` 即 `completed`。
  - 例如 `water`：`count_check(check_list, obs["crops"], self.last_obs["crops"], False, "watered_crop")`——**用游戏内真值计数，不用 LLM 自评**。
  - `skill`：`obs["player"]["skills"]["farming"] - last_obs...`——技能等级差值。
- **命名任务与确定性** `[证据]`：任务名自带参数（`clear_5_weeds_with_scythe`），`save` 字段固定起始状态，`init_commands` 准备前置物品。→ **可复现**。

### 5.4 指标与结果

- **主指标：Success Rate (SR)**；随后续工作补充 **Budgeted SR**（匹配 LLM 调用预算）、**Tokens/Task**、**Latency/Step**、**Recovery/Stuck Ratio** `[证据]`。
- **SOTA 结果** `[证据]`（[官方项目页](https://stardojo2025.github.io/stardojo/)）：
  - GPT-4.1 最高总成功率 **12.7%**，其他模型均 **< 11%**；开源最强为 Llama 4 Maverick。
  - 「Most successful completions are limited to **easy** tasks, whereas all models struggle significantly with medium and hard tasks, achieving **near-zero** success rates」。
  - 相对擅长的：farming、crafting；困难的：exploration、combat、social。
- **SPIKE 在 Lite-100 上的对比** `[证据]`：SPIKE 18.0% > CRADLE 13.0% > StarDojo baseline 12.3% > Reflexion-like 8.7% > Voyager-like 7.3% > ReAct-like 6.7%。
- **跨游戏迁移** `[证据]`：SPIKE 在 Red Dead Redemption 2 上 13 个长程任务 SR **56.4%**（vs StarDojo baseline 33.3%）——说明**双控制器结构是环境无关的**，不是 Stardew 特调。

### 5.5 我们能直接借用的资产

| 借用项 | 具体做法 | 来源 |
|---|---|---|
| **任务 YAML schema** | `object / quantity / tool / save / init_commands / evaluator / difficulty`，用 YAML 声明而非写代码定义任务 | [farming.yaml](https://github.com/StarDojo2025/stardojo/blob/main/env/tasks/task_suite/farming.yaml) |
| **前后观测差分判定** | 不信任 LLM 自评，比较 `last_obs` 与 `obs` 的游戏内计数差值 | [farming.py](https://github.com/StarDojo2025/stardojo/blob/main/env/tasks/farming.py) |
| **确定性起始状态** | 每个任务绑定固定存档 + `init_commands` 准备前置 | 同上 |
| **难度 = 步数预算** | easy/medium/hard ↔ 30/50/150 步 | [项目页](https://stardojo2025.github.io/stardojo/) |
| **固定测试存档** | 仓库内置 `save_new` / `save_farming` / `save_quests` | `env/tasks/saves/` |
| **指标集** | SR + Budgeted SR + tokens + latency + Recovery/Stuck Ratio | [SPIKE](https://wencanjiang.github.io/projects/SPIKE/) |
| **暂停-恢复机制** | 规划时暂停游戏时钟，执行前恢复（避免「想太久天就黑了」） | [项目页](https://stardojo2025.github.io/stardojo/) |

> agent-stardew 已经在做类似的事：`cropId/cropCount/watered` 完成条件 + `completed/VERIFIED` vs `needs_review` 的区分 + 固定基线存档 + 哈希记录 `[证据]`。**建议正式引入 StarDojo 风格的 YAML 任务套件**，让内外评测口径统一。

---

## 6. 风险提示

### 6.1 反作弊 / ToS

- `[证据]` Stardew Valley 是**单机离线游戏**（含可选联机 co-op）；SMAPI 是**官方社区认可**的 modding 框架（[smapi.io](https://smapi.io/)），StarDojo、agent-stardew、NagiBridge 等均以它为基础公开发布；StarDojo 还把 mod 发到了 Nexus Mods。
- `[推断]` **不存在 VAC 式反作弊封禁风险**（没有可信证据表明 Stardew Valley 使用 VAC；本次未找到官方 EULA 中禁止自动化的明确条款，标为**未确认**）。真实风险不在封号，而在：
  1. **多人 co-op 场景**——用自动化冒充 human farmhand 会被其他玩家排斥；NagiBridge 特意做了 `:7843` farmhand 端口，说明这一点需要注意。
  2. **Steam 成就公信力**——stardew-together 的 153 小时全成就明确是自动化产物；如对外宣传需注明。
  3. **发行合规**——若发布 mod，Nexus Mods 政策适用（未核实）。
- **待办** `[推断]`：若要严谨，应查阅 ConcernedApe 官方 modding 声明与游戏 EULA 原文；本次检索未取得可引用的一手条款，**不要写进对外文档**。

### 6.2 存档损坏风险

- `[证据]` 官方 1.6 迁移文档专门处理了「**Error Item**」问题：移除了添加物品的 mod 后，存档中会出现无底层数据的物品，以前会导致「invisible items, errors, and crashes」，1.6 才加入「comprehensive handling」，用 🛇 图标 + `Error Item` 名称 + 缺失 ID 描述来容错。[来源](https://stardewvalleywiki.com/Modding:Migrate_to_Stardew_Valley_1.6)
  → `[推断]` **启示：跨 mod 依赖的存档很脆**。我们的 mod 若给存档写入自定义物品/标记，卸载后必须能被原版安全忽略；优先用 `ModData` 之类的附加字段，而不是新物品 ID。
- `[证据]` agent-stardew 对存档的处理值得复制：使用**专用测试存档**（`AgentTest / AgentFarm`），基线存档记 SHA-256，安装 mod 前**先备份到 `work/backups/`**，「不使用已有用户存档进行破坏性测试」，并明确「游戏运行记录不等于游戏持久存档」。
- `[证据]` `[推断]` 高风险操作清单（来自各项目实践）：
  - **直接修改游戏内部状态**（StarDojo 的 pause-and-resume 就是「directly modifying the inner states」；NagiBridge 曾尝试「直接修改 playerPosition 绕过输入系统」并标注「待验证」）——最易引起状态不一致/物理异常。
  - **warp / teleport**——NagiBridge 大量使用，未见损坏报告，但会跳过碰撞与地图转换逻辑 `[推断]`。
  - **睡觉/换日流程**——amarisaster 专门做了 sleep sync（「Bot farmers auto-signal sleep readiness on day end and at 2 AM to **prevent deadlocks**」），说明换日是无人值守最容易死锁的地方 `[证据]`。
  - **游戏中写文件/复制 DLL**——NagiBridge：「游戏运行时 DLL 被锁 → 必须先关游戏再复制」`[自述]`。
- **缓解措施建议** `[推断]`：① 每次运行前对存档目录做快照（带时间戳）；② 写入侧一律原子写（amarisaster 的「Atomic file writes both directions」是现成范式）；③ 高风险动作（warp、直接改状态）做成可开关的调试能力，默认关闭；④ 在测试存档上跑，永久隔离真实存档。

### 6.3 游戏更新（1.6.x）导致 mod 失效

**这是本项目最确定的长期风险。** `[证据]`

- 官方迁移文档原话：「**Is this the modapocalypse? Maybe.** The update includes major changes to fundamental parts of the game, and SMAPI and Content Patcher **can't feasibly rewrite every older mod** for compatibility with some of the changes. **This will break many existing mods** until they're updated.」[来源](https://stardewvalleywiki.com/Modding:Migrate_to_Stardew_Valley_1.6)
- 该页面配有图表：「SMAPI compatibility over time. The Stardew Valley 1.6 release appears as a **sudden drop in March 2024**.」`[证据]`
- **具体破坏形式（对我们最相关的一类：内部字段/类型变更）** `[证据]`：
  - **运行时框架换代**：`.NET 5 → .NET 6`，所有 C# mod 必须把 `<TargetFramework>net5.0</TargetFramework>` 改为 `net6.0` 并重编译。
  - **集合类型变更**：`Farmer.achievements`、`professions`、`mailReceived`、`eventsSeen`、`songsHeard` 等一批字段从 `List<T>` 改为 **`HashSet<T>`** → **不可索引**（`list[0]` 编译/运行失败）、**无序**，需改用 `RemoveWhere` / `Add`。受影响类型：`Farmer`、`FarmerTeam`、`Game1`、`NetWorldState`。
  - **类型语义变更**：`Game1.weather` / `weatherForTomorrow` 从 int 改为 **string**；天气常量语义变化（新增 `Game1.legacy_weather_sunny`）。
  - **数据资产重命名**：`Data/BigCraftablesInformation` → `Data/BigCraftables`；`Data/Crops`、`Data/Weapons` 改为模型（model）而非斜杠分隔字符串。
  - **物品标识重构**：新增 `ItemId` / `QualifiedItemId`（如 `(O)128` vs `(BC)128`）；物品引用从 `ParentSheetIndex` 改为 `ItemId`。
  - **通用陷阱**：`DataLoader`（强类型数据加载，替代易错的 `Game1.content.Load<...>("Data\\...")`，官方直言旧写法「fragile」「spell asset name」易错且「wouldn't notice until runtime」）。
  - **地图/瓦片属性**：`Arch/asdf/Debris/Fish` 等属性被移除，`Music`/`UniquePortrait` 弃用。
- **补丁版本也会破坏 mod** `[证据]`：维基存在 **`Modding:Migrate to Stardew Valley 1.6.16`** 独立迁移页（[链接](https://wiki.stardewvalley.net/mediawiki/index.php?title=Modding:Migrate_to_Stardew_Valley_1.6.16)）→ **1.6.x 小版本同样需要迁移工作，不是只有 1.6.0 这一次性冲击**。
- **一线项目的实证** `[证据]`：NagiBridge 专门记录「**1.6 版字段名是 `player2MovementDirections` 不是 `playerMovementDirections`** → `FirstField` 多候选名 fallback」，以及 Harmony 注入时序问题（「SMAPI `UpdateTicked` 在 `Game.Update` 之后，设的方向下一帧被 `_UpdateInput` 清除」）。StarDojo 的 reflect 读字段（`1.6版字段名`）与 amarisaster 的 shadow farmer 绕过 `Game1.otherFarmers` NPE，都是同一类脆弱性的表现。

**缓解建议** `[推断]`：
1. **锁定并记录版本三元组**（游戏 build + SMAPI 版本 + .NET SDK），像 agent-stardew 那样写进 SPEC 并在 `doctor` 里校验。已知基线：Stardew 1.6.15 build 24356 / SMAPI 4.5.2 / .NET 6。
2. **把「游戏内幕访问」集中到一个薄适配层**（类似 `mods/AgentStardew/Observations.cs` + `GameActions.cs`），让协议/CLI/控制器**不直接依赖游戏字段名**——这样 1.6.16 之类升级只改一个文件。
3. **反射访问一律写多候选字段名 fallback**（NagiBridge 的 `FirstField` 做法），并在字段缺失时**降级而非崩溃**。
4. **优先用官方稳定 API**：SMAPI 的 `Helper.Reflection`、`Helper.GameContent`、`ModData`、`DataLoader`，而不是直接 Harmony patch 私有字段。对 `manifest.json` 声明 `MinimumApiVersion`。
5. **在 CI 里做「字段存在性体检」**：启动时把用到的反射字段列表打日志，升级后一眼看出哪几个消失了。

### 6.4 无人值守长时间运行的常见故障模式

综合各项目实证（每条有出处）：

| 故障模式 | 实证出处 |
|---|---|
| **换日/睡觉死锁**（agent 不睡，游戏不推进） | amarisaster 专门做 sleep sync，在日终和凌晨 2 点自动 sign sleep，「prevent deadlocks」`[证据]` |
| **卡住无法自恢复**（stuck detection） | amarisaster v0.2.1「Farm mode stuck detection」「Mine mode ladder descent」「Fishing timeout」；agent-stardew 停滞计数 + 具体阻塞上报 `[证据]` |
| **决策/动作频次不匹配导致状态错乱** | amarisaster「AI tick rate fix (60/sec, was 2/sec)」`[证据]` |
| **文件接口竞争与半写** | amarisaster「Atomic file writes both directions」「Action file race fix」`[证据]` |
| **单个组件崩溃拖垮全局** | amarisaster「Per-companion crash isolation」`[证据]` |
| **模型超时/限流/迟到响应** | agent-stardew「超时和限流使用有限退避，达到预算即停止并保留原因」「取消推理后的迟到响应」必须在验证矩阵中 `[证据]` |
| **上下文膨胀 / 成本失控** | stardew-together 专门做上下文投影与硬预算（超预算**明确报错**而非静默裁剪）；并提供 `ModelTokenBudgetPerDay` 开关 `[证据]`；agent-stardew 有共享请求预算与总时限 `[证据]` |
| **世界模型与现实漂移** | stardew-together：「**历史流水不累加成当前库存，计划不算已完成，摘要也不能覆盖实时状态**」`[证据]`；agent-stardew：「远处事实注明最后观察时间；历史引用不直接复用，行动前从当前快照重新取得引用」`[证据]` |
| **静默动作失败** | NagiBridge「背包满 give/craft **静默掉落**」`[自述]`；agent-stardew 的 `UNSUPPORTED` 误判（礼盒交互实际成功却报失败）`[证据]` |
| **窗口失焦 / 渲染停滞 / 进程存活** | agent-stardew README 要求「游戏窗口需要正常刷新，**渲染停滞时主线程动作也会超时**」，并保存了 `game-smoke/sample.txt` 进程采样；同时它明确「Mod 支持**失焦后台运行**」`[证据]`（注意：这是本项目的强项，因为不依赖截屏） |
| **地图边界/寻路特例** | agent-stardew：农舍出口坐标在地图边界外一格被寻路拒绝 `[证据]`；Hunter-Thompson：A* 最多重算 5 次，部分区域不可达 `[证据]` |

**建议的安全网** `[推断]`：心跳 + 看门狗超时、进度不变量（N 分钟内必须发生资源/位置/任务进展之一）、硬步数与 token 预算、结构化 veto 原因日志、崩溃后 supervisor 重启 + 幂等恢复（核对存档身份/位置/背包后才续跑，agent-stardew 已明确「重启保留证据，**不自动恢复执行**」）、以及每次运行前存档快照。

---

## 7. 可借鉴的设计模式 TOP 5

### TOP 1 — 双控制器 + 事件触发的摊薄式推理（战略低频 / 反应高频）

**做法**：LLM 只在**视觉变化、进度停滞、重复检测、失败**这四类边界被唤醒；稳定区间由一个有界的反应式控制器连续执行局部动作，并允许 local override。
**为什么**：SPIKE 在同一 benchmark 上同时拿到 **+5.0 pt SR、−54.9% token、−40.8% 延迟**（对比 CRADLE）——不是取舍。
**来源**：[SPIKE 项目页](https://wencanjiang.github.io/projects/SPIKE/) ／ [GitHub](https://github.com/wencanjiang/SPIKE) ／ [arXiv 2605.18636](https://arxiv.org/abs/2605.18636)
**落地要点**：把「多久问一次模型」做成显式预算与触发器，而不是每步一问。

### TOP 2 — 候选（affordance）生成 + 执行契约 + 结构化 veto 原因

**做法**：不让 LLM 自由输出动作序列。① 执行器从当前快照生成**带前置条件的合法候选**；② LLM 只在候选集内选；③ 执行前校验时效与执行条件；④ 被拒绝的候选必须产出**原因码**并回灌下一轮。
**为什么**：这是社区对「大量 SKIP」的事实标准解法；NagiBridge 用「操作前检查空间」消除了背包满静默掉落，agent-stardew 用候选集 + 过期拒绝消除了非法/过期动作。
**来源**：[agent-stardew jev-runtime.md](https://github.com/rottenpen/agent-stardew/blob/main/docs/jev-runtime.md) ／ [stardew-together README](https://github.com/Zsh123456-BOOP/stardew-together)（`ToolSpec.cs` / `ExecutionContract.cs`）／ [NagiBridge PROJECT.md](https://github.com/anqinou-art/NagiBridge/blob/main/PROJECT.md)
**落地要点**：**把 SKIP 从「静默丢弃」变成「一等公民的可观测事件」**——这是我们已知问题的直接解药。

### TOP 3 — 结果回执与账本分离：只信游戏证据，不信模型意图

**做法**：模型说「买了 15 份种子」不记账；只有**原生到货证据**才更新账本与记忆。异步任务的首个回执只是「已排队」。完成判定用**前后观测差分计数**（StarDojo 的 `count_check`）而非 LLM 自评。区分 `completed/VERIFIED` 与 `needs_review`。
**为什么**：这是长程 agent 不「漂移」的根基；stardew-together 用「历史流水不累加成当前库存、计划不算已完成、摘要不能覆盖实时状态」三句话把规则说清了。
**来源**：[stardew-together README](https://github.com/Zsh123456-BOOP/stardew-together) ／ [StarDojo farming.py](https://github.com/StarDojo2025/stardojo/blob/main/env/tasks/farming.py) ／ [agent-stardew verification.md](https://github.com/rottenpen/agent-stardew/blob/main/docs/verification.md)
**落地要点**：每个资源字段都要能回答「这条数字的证据来自哪次原生回执」。

### TOP 4 — 用 YAML 任务套件 + 固定存档 + 步数预算做可复现评测

**做法**：任务用 YAML 声明（`object/quantity/tool/save/init_commands/evaluator/difficulty`），绑定固定起始存档，难度映射到步数上限（30/50/150），判定用观测差分。指标至少报 **SR + 预算受限 SR + token/任务 + 每步延迟 + Recovery/Stuck Ratio**。
**为什么**：StarDojo 用这套把 MLLM 的天花板钉在 12.7%，SPIKE 用同一套证明双控制器有效；没有这套，我们无法判断任何改动是否真的更好。
**来源**：[StarDojo farming.yaml](https://github.com/StarDojo2025/stardojo/blob/main/env/tasks/task_suite/farming.yaml) ／ [StarDojo 项目页](https://stardojo2025.github.io/stardojo/) ／ [SPIKE 实验](https://wencanjiang.github.io/projects/SPIKE/)
**落地要点**：直接采用 StarDojo 的 YAML 字段命名，便于**与公开结果做同口径对比**（这是低成本高收益的动作）。

### TOP 5 — 记忆三分 + 上下文投影（而不是追加对话历史）

**做法**：把记忆拆成**事实事件**（原生回执、资源变化）/ **计划承诺**（目标、依赖、未完成项）/ **经验规则**（带适用条件的失败规则、日/季摘要）。每轮**重新投影**当前决策所需的上下文并做硬预算；关键约束超预算时**报错**而不是静默裁剪；模型生成的摘要必须引用证据 ID 且标记为「派生内容」。
**为什么**：直接对抗「上下文膨胀 → 成本失控 → 关键约束被挤掉 → 行为漂移」这条长程失败链；GUI agent 研究也警告盲目堆记忆会恶化动作级失败。
**来源**：[stardew-together README](https://github.com/Zsh123456-BOOP/stardew-together)（`MemoryArchive.cs` / `DecisionContext.cs` / `ContextBudget.cs`）／ [arXiv 2606.14106](https://arxiv.org/abs/2606.14106)
**落地要点**：注意 stardew-together **未声明许可证**，只能借鉴设计、不能复制代码。

---

## 8. 参考来源索引

**开源项目**
- [Zsh123456-BOOP/stardew-together](https://github.com/Zsh123456-BOOP/stardew-together) — 153h 全成就无人值守战绩、执行契约、记忆三分
- [Hunter-Thompson/stardew-mcp](https://github.com/Hunter-Thompson/stardew-mcp) — SMAPI+Go+MCP，WebSocket 8765，30 cheats
- [anqinou-art/NagiBridge](https://github.com/anqinou-art/NagiBridge) — HTTP :7842，脚本控制器，踩坑记录
- [amarisaster/StardewValley-MCP](https://github.com/amarisaster/StardewValley-MCP) — shadow farmer、25 tools、stuck detection
- [rottenpen/agent-stardew](https://github.com/rottenpen/agent-stardew) — dsh 插件 + Jev 决策，`docs/jev-runtime.md`、`docs/verification.md`
- [StarDojo2025/stardojo](https://github.com/StarDojo2025/stardojo) — 环境 + benchmark + StarDojoMod
- [wencanjiang/SPIKE](https://github.com/wencanjiang/SPIKE) — 双控制器，Lite-100 实验
- [JoeStrout/Farmtronics](https://github.com/JoeStrout/Farmtronics) — 游戏内可编程机器人（shadow farmer 灵感来源）
- [Zhang-986/Stardew-Sage](https://github.com/Zhang-986/Stardew-Sage) — 游戏数据问答/RAG（非控制）
- [kogazz/stardew-llm-agent](https://github.com/kogazz/stardew-llm-agent) — 对话助手（非控制）
- [Cabbagito/Junimo-Kart-AI](https://github.com/Cabbagito/Junimo-Kart-AI) — 小游戏 RL

**学术**
- StarDojo: [arXiv 2507.07445](https://arxiv.org/abs/2507.07445) ／ [OpenReview](https://openreview.net/pdf?id=jRi824qGpS) ／ [项目页](https://stardojo2025.github.io/stardojo/) ／ [NTU PDF](https://www3.ntu.edu.sg/home/boan/papers/ECCV26_StarDojo.pdf) ／ [NeurIPS 2025](https://neurips.cc/virtual/2025/loc/san-diego/128024)
- SPIKE: [arXiv 2605.18636](https://arxiv.org/abs/2605.18636) ／ [项目页](https://wencanjiang.github.io/projects/SPIKE/)
- CRADLE: [arXiv 2403.03186](https://arxiv.org/abs/2403.03186)（SPIKE 的基线来源之一）
- Naive Visual Memory is Not Enough: [arXiv 2606.14106](https://arxiv.org/abs/2606.14106) ／ [GUI Agents Paper List](https://osu-nlp-group.github.io/GUI-Agents-Paper-List/papers/arxiv-2606-14106/)
- Voyager: [arXiv 2305.16291](https://ar5iv.labs.arxiv.org/html/2305.16291)

**官方文档 / 风险**
- [Modding: Migrate to Stardew Valley 1.6](https://stardewvalleywiki.com/Modding:Migrate_to_Stardew_Valley_1.6) — 「modapocalypse」、HashSet 字段、.NET 6、物品 ID 重构
- [Modding: Migrate to Stardew Valley 1.6.16](https://wiki.stardewvalley.net/mediawiki/index.php?title=Modding:Migrate_to_Stardew_Valley_1.6.16) — 补丁版本也需迁移
- [SMAPI](https://smapi.io/) ／ [SMAPI release notes](https://github.com/Pathoschild/SMAPI/blob/develop/docs/release-notes.md)

---

## 9. 未确认事项（不要当结论用）

1. Stardew Valley 官方 EULA / ConcernedApe 对**自动化游玩**的明确态度——本次未取得可引用的一手条款。
2. 是否存在 VAC 类反作弊（**推断为无，但未证实**）。
3. StarDojo 的 pause-and-resume「直接修改内部状态」是否会在长期运行中引入状态不一致——无公开报告。
4. `stardew-together` 的 153h / 1.7451 亿 token / ¥213.3 均为**项目自述**，无第三方复现。
5. Stardew-Sage、sei、luy-0/StardewValley-MCP、shylux/StardewMCP 等的接入方式与自主能力未逐一核实。
6. StarDojo 论文中的详细消融数据（我们只能读到项目页摘要与 SPIKE 的对比表；PDF 抽取在本环境不可用）。
