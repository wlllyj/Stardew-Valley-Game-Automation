# T-6 当前存档只读探针 + 全自动启停演示（2026-10-20）

- 日期：2026-10-20 00:24–00:26（Asia/Bangkok）；执行：machine-runner（team a9-goal12）
- 性质：**只读探针 + 全自动启停演示**。不买、不种、不卖、不使用工具、不写世界、不 restore、不起长跑；用户零介入（自动起游戏 → 等桥 → 读档 → goto Farm → observe → 优雅退 → 三核对）
- 游戏：Stardew Valley 1.6.15 / SMAPI 4.5.2 / Mod AgentFarm Bridge **0.7.49**（装机 dll `C9B3BD6C…A662`，与 0.7.47/0.7.48 逐字节相同的冻结产物）
- 探针脚本：`scratch/_t6_probe_save.py`（本版为"全自动演示版"；失败版备查 `scratch/_t6_probe_save.failed.json`）
- 观测原文：`logs/_probe-save-state-2026-10-20.observe.json`（187,858 B，SHA256 `455352D14C8C350BE777972A874ADC16D2FDFCF2780355793CCC24768445A9AB`）
- SMAPI 窗口：`logs/_probe-save-state-2026-10-20-smapi-window.txt`（103,003 B / 423 行，含优雅退迹线）
- 完整证据：`scratch/_t6_probe_save.json`（每一步 rc/输出/时间戳）

## §0 三问结论（先结论后证据）

**问 1：全自动启停演示成功了吗？—— 成功，全程 50.7 秒，用户零介入。**

六步全自动：现场三核对 → Popen 起游戏（20s 桥就绪）→ CLI 读档（rc=0）→ CLI goto Farm（rc=0，落点 [64,15]）→ CLI observe --full --json（rc=0）→ stop-game 优雅退（rc=0）→ 收尾三核对 **3/3 全过**。存档四件退前退后**逐字节一致**（只读未破坏）。

**问 2：背包有没有可卖/可出货的非保护叠？—— 有（Wheat×5 / Geode×3 / Hay×6），但背包 12/12 全满、0 空格。**

- 12 格逐格见 §3。非工具叠 7 叠：Geode×3、Wheat×5、Copper Ore×1、Stone×21、Hay×6、Clay×3、Wheat Seeds×10。
- 按脑侧售卖口径（`farmwork.py` 白名单 + `longrun.py:6519` `_PROTECTED` + 590f154 last-resort 口径）：
  - **可送**：`(O)262 Wheat×5`（作物白名单 `SLOT_RELIEF_CROP_IDS`）、`(O)535 Geode×3`（高价值白名单 `SLOT_RELIEF_HIGH_VALUE_IDS`；590f154 last-resort 按 `(stack, slot)` 排序会**首选它**）、`(O)178 Hay×6`（仅 last-resort 口径可送，不在三档白名单）。
  - **保护/永不送**：`(O)390 Stone×21`、`(O)378 Copper Ore×1`、`(O)330 Clay×3`（∈ `_PROTECTED` 建材/矿石）、`(O)483 Wheat Seeds×10`（种子：名字判据 + 白名单双排除）、5 件工具/武器。
- 关键事实：**capacity=12、非空 12、free_slots=0**（`inventoryCount` = `Farmer.Items.Count` = 容量，非件数）。⇒ 春季买种子即便钱够（2767g ≥ 种子价），没有空格也买不进；**腾格是买种子前置**，而可送叠确实存在 ⇒ 590f154 的 last-resort 在本档有 Material 可送。

**问 3：toolOk=false 锚点有哪些？—— 当前 winter-26 档 0 个 clump（farm-wide 亦 0），现场无锚点；锚点论据另有两层（历史账本 + 全 L0 工具 × ClumpMeta 门槛表）。**

- 当前存档：`farm.stumps/logs/boulders/rockPiles/greenRain/clumpsTotal` **全 0**（`complete=true, scanSeq=9`，全场口径可信）；玩家窗口 400 格（`tilesTruncated=true`）内同样 0 clump ⇒ **现场无 toolOk=false 格**。
- 历史锚点（spring 档账本 `logs/runA9-0749-spring.jsonl`，**不同存档态**，只作引用）：12 条 `tool_refused`（`tool_ineffective`，`kind=未知`）落点 **(73,25)、(74,25)、(73,26)、(74,26)、(67,30)、(68,30)**；`logs/runA9-0749-spring-gaps.json`：`kind=unknown, reason=gated, count=12`，`first_seen "2 spring 2"` / `last_seen "2 spring 5"`。
- 门槛表论据（`mod/AgentFarm.Bridge/ClumpMeta.cs`）：stump(600)=斧≥1 / log(602)=斧≥2 / boulder(672)=镐≥2 / rockPile(148/622)=镐≥3 / greenRain(≥752)=镐≥0。本存档**五件工具全部 upgradeLevel=0** ⇒ 除 greenRain 外**任何刷新出来的 clump 都必然 toolOk=false** ⇒ "升级后能清掉此前 toolOk=false 的障碍"（目标1③）的解锁前提 = 铜斧/铜镐升级链；当前存档无在途升级（`toolBeingUpgraded=null`、`toolUpgradeDaysLeft=0`）。

## §1 环境与版本（起跑前，00:24:43 现场三核对）

| 项 | 值 |
|---|---|
| HEAD | `590f154`（590f154 = last-resort ship 修复，13:41 提交） |
| 进程 | StardewModdingAPI 0 / Stardew Valley 0 / steam 0 |
| 17890 | 无 LISTENING |
| bridge.json | **残留死令牌**（上一次失败版被虐杀遗留，pid 10860，00:03:27 启动）⇒ 按规程删除并留记录（`step0.residual_bridge_cleanup`：删前 207 B `36DF556F…`） |
| 装机 dll | 293,888 B / `C9B3BD6CE42BEFE87E75DD64857A5C92F5B9F317940BDC3091D42D5E039A662A` / 2026-10-19 09:29:00 |
| 装机 manifest | 82,951 B / `FC2B02DE1F2146F079FAFF1A90FD9457D2DFD41337315BB41FA4283B27292BA9` / 2026-10-19 09:27:38 |
| 存档四件（基准） | 见 §7，与 A9-start 备份逐字节一致 |
| 代理坑（本机环境） | 工具会话带 `HTTP_PROXY`/`HTTPS_PROXY=http://127.0.0.1:40920`（沙箱连接器代理）⇒ urllib 把 127.0.0.1:17890 也代理 ⇒ 上一次失败版的 502/connection_broken 根因。本版脚本 import 即清所有 `*_proxy` 并设 `no_proxy=127.0.0.1,localhost`，子进程 env 同样清理（证据 `step0.env_proxy_evidence`） |

## §2 六步演示时间线（每步证据在 `scratch/_t6_probe_save.json`）

| 步 | 动作 | 结果 | 耗时 |
|---|---|---|---|
| 0 | 现场三核对 + 删残留死令牌 + 存档四件基准 | 进程 0/0/0、端口空；死令牌已删 | — |
| 1 | Popen 起游戏（`CREATE_NEW_CONSOLE(0x10)\|CREATE_NEW_PROCESS_GROUP(0x200)`、三个 std 全 DEVNULL、close_fds、**env=scrubbed**；exe=`StardewModdingAPI.exe`，cwd=游戏目录）→ 轮询等桥（每 2s 新建 BridgeClient 重读 token/port） | 00:25:03 桥就绪：health `modVersion=0.7.49 game=1.6.15 smapi=4.5.2 port=17890 windowActive=true onTitleScreen=true` | 起→桥 20s |
| 1b | **代理清理证据（环境坑自动绕开，无需人工介入）**：import 时发现并清掉 `HTTP_PROXY`/`HTTPS_PROXY`/`http_proxy`/`https_proxy`（原值均 `http://127.0.0.1:40920`，证据 `step0.env_proxy_evidence`），设 `no_proxy=NO_PROXY=127.0.0.1,localhost`；起游戏的 Popen 继承的是**已清理的 os.environ**（scrubbed env；脚本后续已加固为显式 `env=clean_env()`，行为一致）；所有 CLI 子进程 env 同样清理 | **health 直连 127.0.0.1:17890 成功**：HTTP 200、`modVersion=0.7.49`、`server.requestsServed` 递增；随后 load/goto/observe 全部 rc=0 ⇒ 请求不经 40920 代理 | — |
| 2 | `python -m agentfarm load --save Wahaha_450799035` | **rc=0**（11.8s）：`已进入存档 Wahaha_450799035：地点 FarmHouse 格 [9,9]（9299ms）`；读档后 `第1年 冬26日 06:00 sunny FarmHouse(9,9) 体力270/270 钱2767g seq=1 世界推进中` | 11.8s |
| 3 | `python -m agentfarm goto Farm` | **rc=0**（9.0s）：`move_to_location status=ok reachedLocation=Farm`，path `FarmHouse → Farm`，hop1 `landing=[64,15] used=[3,12] 7623ms`；移动后 `Farm(64,15) 农场[草0/石88/枝63/树914 耕地8 作物0] seq=10` | 9.0s |
| 4 | `python -m agentfarm observe --full --json` | **rc=0**：原文 187,858 B 落 `logs/_probe-save-state-2026-10-20.observe.json`（worldSeq=10，`worldAdvancing=true`，`secondsSinceClockMoved=10.5s`） | <1s |
| 5 | `tools/stop-game.py --wait 45` 优雅退 | **rc=0**（2.9s）：回执 `ok — 已置 Game1.quit=true`；原 pids=[5456]；SMAPI 迹线 `00:25:26 Disconnected: ClosedGame → Disposing... → 已删除发现文件 bridge.json` | 2.9s |
| — | 全程 | **50.7s**，`notes` 为空（无异常、无兜底） | |

## §3 背包 12 格逐格清单（observe?detail=full，00:25:25，capacity=12）

| slot | qualifiedId | name | stack | isTool | 售卖资格（判据出处） |
|---|---|---|---|---|---|
| 0 | `(T)Axe` | Axe | 1 | true | 工具，永不送 |
| 1 | `(T)Hoe` | Hoe | 1 | true | 工具 |
| 2 | `(T)WateringCan` | Watering Can | 1 | true | 工具 |
| 3 | `(T)Pickaxe` | Pickaxe | 1 | true | 工具 |
| 4 | `(W)47` | Scythe | 1 | true | 武器（kind=other） |
| 5 | `(O)535` | Geode | 3 | false | **可送**：高价值白名单；590f154 last-resort 首选（stack 最小） |
| 6 | `(O)262` | Wheat | 5 | false | **可送/可出货**：作物白名单（`farmwork.py:1448` 262 Wheat） |
| 7 | `(O)378` | Copper Ore | 1 | false | 保护：`_PROTECTED`（铜矿=熔锭原料） |
| 8 | `(O)390` | Stone | 21 | false | 保护：`_PROTECTED`（建材） |
| 9 | `(O)178` | Hay | 6 | false | **仅 last-resort 口径可送**（不在三档白名单） |
| 10 | `(O)330` | Clay | 3 | false | 保护：`_PROTECTED`（粘土=建材） |
| 11 | `(O)483` | Wheat Seeds | 10 | false | 保护：种子（名字含 seed；白名单双排除） |

- `inventoryCount=12`、`len(inventory[])=12`、**`free_slots=0`**（无空槽）。
- `player.seeds`（task-240 只读观测面）：`(O)483 Wheat Seeds ×10，seasons=["summer","fall"]，plantableNow=false` ⇒ **夏季/秋季货，冬季（当前）不可种**；春季档同理不可种（春不在 seasons 里）。
- 判据出处：`brain/agentfarm/farmwork.py:1342 SURPLUS_MATERIAL_IDS={92,766}`、`:1436 SLOT_RELIEF_CROP_IDS`（含 262）、`:1488 SLOT_RELIEF_HIGH_VALUE_IDS`（含 535）、`:1495 SLOT_RELIEF_NEVER_SELL_IDS={334,335,336,337,338,787}`、`:1210 SEED_NAME_HINTS=("seed","seeds","种子")`；`brain/agentfarm/longrun.py:6519 _PROTECTED={330,378,380,382,384,386,388,390}`、`:6515-6556 _ship_one_stack_for_space`（590f154）。

## §4 player.tools 各件 kind/upgradeLevel（00:25:25）

| id | name | kind | upgradeLevel | isEquipped |
|---|---|---|---|---|
| Axe | Axe | axe | **0** | true |
| Hoe | Hoe | hoe | **0** | false |
| WateringCan | Watering Can | can | **0** | false |
| Pickaxe | Pickaxe | pickaxe | **0** | false |
| 47 | Scythe | other | **0** | false |

- bools：hoe/axe/pickaxe/wateringCan=true，fishingRod=false，weapon=true。
- 浇水壶：`present=true, waterLeft=13/40, bottomless=false, upgradeLevel=0`。
- 升级在途：`toolBeingUpgraded=null`、`toolUpgradeDaysLeft=0` ⇒ 无 Clint 升级订单。

## §5 farm tiles 分布 + toolOk=false / tool_ineffective 锚点

**玩家窗口（`location.tiles[]`，按距离排序、上限 400、`tilesTruncated=true` ⇒ 只是"看得见的那部分"）**：`tree 216、grass 169、dirt 8、stone 5、twig 1、object 1`；**clump 0**。
- twig 格：[43,17]；stone 格：[75,26],[75,27],[76,28],[76,33],[40,8]；object 格 [58,33] = `(O)590 Artifact Spot`。
- `location.tillable[]` 200 条（触顶 200，截断）；`refillTiles[]` 24 条。

**全场口径（`farm` 视图，`complete=true, scanSeq=9`）**：`weeds 0、stones 88、twigs 63、trees 914、grass 755；stumps 0、logs 0、boulders 0、rockPiles 0、greenRain 0、clumpsTotal 0、clumpsUnclassified 0；hoeDirt 8、emptyDirt 8、crops 0、ripeCrops 0、readyCrops 0、deadCrops 0、dryCrops 0；sprinklers 0、machinesTotal 0、animals 0`。

**toolOk=false 锚点**：
- 当前档：**无**（全场 0 clump ⇒ 无 toolOk 判定对象；窗口内亦无）。
- 历史（spring 档账本，引用非本档事实）：12 条 `tool_refused` `tool_ineffective`，落点 (73,25),(74,25),(73,26),(74,26),(67,30),(68,30)，`kind=未知`；gaps `reason=gated count=12`（`2 spring 2`–`2 spring 5`）。
- 结构性论据：全工具 L0 × ClumpMeta 门槛表（stump 斧≥1 / log 斧≥2 / boulder 镐≥2 / rockPile 镐≥3）⇒ 目标1③"升级后能清掉此前 toolOk=false 的障碍"在本档的表现形式 = 任何新刷新 clump 当场 toolOk=false，升级铜斧（stump）后转 true。

## §6 money / 季节 / 日期 / 时间

| 项 | 值 |
|---|---|
| clock | 第 **1** 年 **winter（冬）26** 日 **06:00**（`timeOfDay=600`），`weather=sunny`、`weatherOnFarm=sunny` |
| money | **2,767 g** |
| farmingLevel | 3 |
| stamina | 270 / 270 |
| player | Farm [64,15]，canMove=true |
| shippingBin | `present=true, count=0`（空箱），`lastItemShipped=""` |
| ui/liveness | 无模态、无事件；worldSeq=10、worldAdvancing=true |

⚠ 与 Lead 卡面措辞的一处事实更正：**盘上当前存档是 winter 26（A9-start 态，四件与 `logs/ab-backup/A9-start/` 逐字节一致），不是 spring 态**；spring 态（year2 spring1，money 3042）只存在于 `logs/runA9-0749-spring-baseline.json` 与账本里（该跑 13:24 结束后存档被回退）。本探针按"当前存档"口径如实记录 winter 26 读数。

## §7 收尾：三核对 + 存档四件 + SMAPI 窗口

- **三核对（00:25:28–00:25:32，全过）**：进程 `StardewModdingAPI 0 / Stardew Valley 0 / steam 0`；`bridge.json exists=False`（Mod 退出时自删，SMAPI 迹线在案）；`17890 LISTENING=False`。
- **存档四件退前退后逐字节一致**（`save_four_item_compare` 四行 `byte_identical=true`，mtime 未变 ⇒ load/goto/observe 不写档、退出前未睡觉）：

| 文件 | size | mtime | SHA256 |
|---|---|---|---|
| `Wahaha_450799035` | 3,141,826 | 2026-10-18 17:03:52 | `053CAA71007CEA6FB20D865154DACA236C4FC69F314774B9AC118FB5188F4AF7` |
| `SaveGameInfo` | 32,305 | 2026-10-18 17:03:52 | `3D964F3F30AF39C3F33CCCD210C7CC76760B569349A16F12AFC91BB8144B9293` |
| `Wahaha_450799035_old` | 3,121,459 | 2026-10-18 16:49:07 | `E5B60E915BA393E87FD053A05DFE87FDFAF0F838F8C724F4E50D5B026964B19E` |
| `SaveGameInfo_old` | 32,472 | 2026-10-18 16:49:07 | `9DD16B9462C3A213CE9A924D9CF4A34DC8F61406908D877F5919D49812E69525` |

- **SMAPI 窗口**：`logs/_probe-save-state-2026-10-20-smapi-window.txt` 103,003 B / 423 行 / `F2F59ACDBFFD9E68…`（源=副本逐字节一致）；窗口内 ERROR 仅 1 条且为已知 benign（`Oops! Steam achievements won't work because Steam isn't loaded`）。
- 装机复核（收尾后）：dll/manifest 与起跑前一致（§1）。

## §8 春季买种子死锁判断题（供 Lead 裁定 task-240b + 590f154）

1. **钱不是死锁**：winter-26 档 2767g、spring 档 3042g，均 ≥ 种子价（守卫原话 `钱够（3042g ≥ 20g），该去买`）。
2. **空格是硬前置**：winter-26 档 `free_slots=0`（12/12 满）；spring 档六天 `free_slots_start/min/last = 0/0/0`、`relief_exhausted=true`（`logs/runA9-0749-spring.jsonl` day_end×6）。
3. **spring 档旧白名单无可送叠**：18 条 `slot_relief freed=0`，理由原文"背包里没有可卖的盈余叠（只认已知作物/材料/矿表，工具/武器/种子/升级材料/未知物品一律不卖）⇒ 腾不出格子" ⇒ 旧通道（三档白名单）在 spring 态确实腾不出。
4. **590f154 能否解开取决于 spring 档逐格内容**：last-resort 口径 = 非 isTool + ∉`_PROTECTED` + 名字无 seed + ∉`SLOT_RELIEF_NEVER_SELL_IDS` + stack>0，按 `(stack,slot)` 升序送一叠。**winter-26 档实测有 3 叠候选**（Geode×3 / Wheat×5 / Hay×6，首选 Geode×3）⇒ 本档能腾出 1 格。**spring 档逐格清单【无法判定】**（spring 态已不在盘上；账本只留 `seeds=[Wheat Seeds×10, Maple Seed×1]`、capacity 12、free 0）。按 spring 账本可见信息推断：Wheat Seeds（种子排除）+ Maple Seed×1（310：名字含 "Seed" ⇒ last-resort 亦排除；且不在任何白名单）⇒ **spring 档可能 still 无候选叠** ⇒ 590f154 单独未必够；task-240b（腾格后立刻买种子的 catch-22）与"春季货架选品"（T-2）才是主解。**此判断需 T-7 重跑春天 day1 的 full 观测实证**（建议 A9 重跑 day1 落一份 `observe?detail=full` 原文）。
5. ** Wheat Seeds×10 是夏季/秋季货**（`seasons=["summer","fall"]`，`plantableNow=false`）：冬季与春季都不可种；它不是"种子储备"而是占用一格的需要处置的叠（送不掉——种子保护）。

## §9 已知限制与【无法判定】项（照实）

1. **spring 档背包逐格清单【无法判定】**：盘上存档为 winter 26（A9-start），spring 态（year2 spring1+）不在盘上；本探针所有"春季"相关判断只能引用 spring 账本/baseline（§8.4）。
2. **spring 档 tool_ineffective 格 (73,25) 等的 clump 种类【无法判定】**：spring 账本记的是 `kind=未知`（Hoe 挥不动反推），当年未取到 clump 元数据；且那是不同存档态。
3. **窗口截断**：`location.tiles[]` 400 格 `tilesTruncated=true`、`tillable[]` 200 触顶 ⇒ 玩家窗口只是局部；全场口径以 `farm`（complete=true）为准，两者不可混用。
4. **SMAPI 冻结时点**：脚本首冻在退游戏前（00:25:25，417 行），随后把同一会话的完整日志（423 行，含 ClosedGame/Disposing/删 bridge.json 迹线）覆盖为正式冻结副本；证据 JSON 的 `smapi_window` 条目已更新并注明。退出过程的独立证据另有 stop-game 回执 + 三核对。
5. **pauseWhenOutOfFocus=true**：health 在标题界面读到 true（Mod 每帧扳回只在世界就绪后生效）；世界就绪后推进正常（worldSeq 1→10）⇒ 不影响本探针结论。
6. 上一次失败版（管道继承 → 游戏被级联杀 → 502/connection_broken）完整现场保留在 `scratch/_t6_probe_save.failed.json` + `logs/_probe-save-state-2026-10-19-smapi-window.txt`，本版启动配方（Popen + DEVNULL + 新控制台）即其修正。

## §10 命令与产物

- 起游戏（脚本内）：`subprocess.Popen([StardewModdingAPI.exe], cwd=<game>, stdout/stderr/stdin=DEVNULL, creationflags=0x10|0x200, close_fds=True)`（配方出处 `tools/deploy-mod.py:182-194`）
- 读档：`PYTHONUTF8=1 PYTHONPATH=brain python -m agentfarm load --save Wahaha_450799035`
- 移动：`python -m agentfarm goto Farm`
- 观测：`python -m agentfarm observe --full --json`
- 收尾：`python tools/stop-game.py --wait 45`
- 探针：`PYTHONUTF8=1 PYTHONPATH=brain python scratch/_t6_probe_save.py --wait-bridge 120`
- 产物：`scratch/_t6_probe_save.py`、`scratch/_t6_probe_save.json`（证据）、`scratch/_t6_probe_save.failed.json`（失败版备查）、`logs/_probe-save-state-2026-10-20.observe.json`（观测原文）、`logs/_probe-save-state-2026-10-20-smapi-window.txt`（SMAPI 窗口）、本文件
- 本阶段探针文件**未 git commit**（按 Lead 收口规程）。
