# 冬 7 开局 eventUp 溯源 + farm.trees 计数口径（task-243 只读审计）

**速览**
- 冬 7 的 `eventUp=true` **不是观测 bug**：Mod 直读 `Game1.eventUp`，而游戏只会在 `currentEvent != null` 时置这个全局位 ⇒ **确实有一个事件对象在跑**。
- 但**离线无法定案是哪一个**：事件状态不落存档、SMAPI 窗口无事件日志、`Data/Events/Farm` 27 条逐条审计后唯一"未被 seen 且可评估前置全过"的只剩 `900553`（其 `A cc_Greenhouse` 语义未定）⇒ 判 **【无法判定·需真机再取证】**（可执行建议见 §1.5）。
- `farm.trees` **口径正常，不是 bug**：Trees = 果树 + **非树桩**树（树桩单列），存档 Farm 段逐格 = 836 棵、其中 4 个树桩 ⇒ 口径值 **832**，与冬 6 晨实测 832 **完全吻合**；冬 5 的 −11 有 `TreesChopped=11` 佐证，冬 6 的 +4 需真机双采样（§2）。

## 1. 冬 7 开局 eventUp（P0）

### 1.1 现场（`logs/longrun-smoke-0742.jsonl`）
- `L143 t=287.35` `day_start`：`day=[1,winter,7] timeOfDay=600 stamina=270 money=2767 crops=0 unwatered=0 location=FarmHouse weather=sunny`
- `L144 t=295.08` `goto_farm ok=true code=ok where=day_start`
- `L146 t=295.15` `event_blocked`：`activeMenu=null activeMenuText=null dialogueIsQuestion=false tile=[64,15] timeOfDay=600 worldSeq=602 advance_steps=0`，note「游戏事件挂住（ui.eventUp=true）：关框会替游戏推进剧情/默认选否 ⇒ 不 dismiss / 不 sleep / 不 load_save」
- `L148` `day_end ended_by=blocked_event verified=false checks.no_blocking_modal=false` ⇒ `L149 finish{code:1, minutes:4.92, actions:101}`（整跑 4.92 分钟就结束）
- ⇒ 触发点是**进 Farm 后 70ms**（295.08→295.15），位置 `[64,15]` 正是 `Data/Events/Farm` 里 20 多条事件的入口锚点 `continue/64 15/...`。

### 1.2 为什么不是 Mod 观测 bug（已证）
- `mod/AgentFarm.Bridge/WorldSnapshot.cs:1316` `try { v.EventUp = Game1.eventUp; } catch { }` —— 直读、无缓存；JSON 字段见 `mod/AgentFarm.Bridge/Contracts.cs:1008`（`eventUp`）、`:1029`（`dialogueIsQuestion`）。
- `StardewValley.GameLocation.checkForEvents()` IL（`scratch/t243-il4.txt`，`IL_0233-023C`）：`if (this.currentEvent != null) { eventUp = true; }` ⇒ **eventUp=true ⇒ currentEvent 非空**。

### 1.3 存档现场（**不持久化事件状态** ⇒ 存档没法定位）
文件 `C:\Users\admin\AppData\Roaming\StardewValley\Saves\Wahaha_450799035\Wahaha_450799035`（3134241 B，mtime 2026-10-18 14:08:28，即 blocked 后 6s 的落盘）：
- `<currentSeason>winter</currentSeason>`、`<dayOfMonth>7</dayOfMonth><year>1</year>`、`<weather><string>Sun</string></weather>`（当日晴）
- `<eventsSeen><int>60367</int><int>1590166</int><int>992553</int></eventsSeen>`（= 开局事件 / Marnie 猫 / Clint 熔炉）
- `<money>2767</money>`、`<totalMoneyEarned>5536</totalMoneyEarned>`、`friendshipData` 4 条全 0、`petType=Cat`、`<mailReceived>` 6 条（含 `copperFound`）
- `currentEvent` / `eventUp` / `<events>` **0 命中**（不落盘）
- 星期换算：`WorldDate.get_DayOfWeek()` → `GetDayOfWeekFor(dayOfMonth) = dayOfMonth % 7`（`scratch/t243-il3.txt`）⇒ 冬 7 ⇒ 7%7=0 ⇒ **周日**

### 1.4 `Data/Events/Farm` 27 条逐条审计（原文 `scratch/t223-ev-Data_Events_Farm.txt`）
| 事件 id | 前置条件 | 冬 7 判定 |
|---|---|---|
| 5 | `e 3` | ✗ eventsSeen 无 3 |
| 47 / 55 / 91 / 93 / 980558 | `f <NPC> 750~2000` | ✗ 友谊全 0 |
| 2146991 / 63 / 3917587 | `y 2`/`y 3` | ✗ 年 1 |
| 102 | `z spring/summer/fall` + `d Mon..Sat` | ✗ 冬 + 周日 |
| 992553 | `t 600 1130` + `n copperFound` | 前置 ✓ 但**已 seen** ⇒ 应跳过 |
| **1590166** | `m 1000 / t 600 930 / d Mon Tue Thu Sat Sun / w sunny / h cat / H` | **全部 ✓ 但已 seen** ⇒ 应跳过 |
| **900553** | `t 600 1130 / Hn ccPantry / A cc_Greenhouse / w sunny` | **唯一未 seen 候选**；`Hn ccPantry`（host 且未收该信）✓（CC 未完成）；`A` 语义未定 |
| 65 / 3917587 | `m 25000` / `M 5000` | ✗ 总赚 5536 / 现有 2767 |
| 3912125 | `U 8`（次日冬 8 = Festival of Ice ✓，见 `Preconditions.UpcomingFestival`）+ `p Elliott`/`O Elliott` | ✗ 未婚 |
| 66 / 2118991 / 2128292 / 980559 | `e <id>` | ✗ 未 seen |
| giveAlexMoney | 无条件 | 但脚本 `money -5000` 未发生（存档 money 仍 2767）且非数字 id（fork 专用）⇒ 未触发 |

### 1.5 判定与建议
**判定【无法判定·需真机再取证】**：①eventUp 必有 currentEvent【已证】；②触发点=进 Farm 的 70ms、位置=Farm 事件锚点 ⇒ 几乎必然是 `Data/Events/Farm` 的一条【强推断】；③但按存档状态逐条审计，唯一"未 seen 且可评估前置全过"的候选只剩 `900553`（`A cc_Greenhouse` 语义未定，`scratch/t243-il5.txt` 的 `Preconditions.*` 全集尚未逐字母映射）；④事件 id 不落盘、SMAPI 窗口无事件行（全 2071 行里只有 4 条命中 sleep/Steam 关键字）⇒ 离线已无法再证。
建议（给下一轮 bring-up / A″）：
1. **识别**：Mod `ui` 观察面加 `eventId`（`Game1.currentEvent?.id`）——1 行、零风险，从此"事件挂住"可归因（本卡只报，不改代码）。
2. **规避**：起跑后进 Farm 前先 `observe`；若 `ui.eventUp==true` 且 `activeMenu==null` ⇒ 先等 60~120s（每 30s 重观测），仍 true 才按"事件卡死"处理；**不要**直接停整天（本次 4.92 分钟白烧）。
3. **A″ 判据**：`ended_by=blocked_event` 当天记【无法判定】、不作 FAIL，但它会把 `verified_streak` 清零 ⇒ A″ 起跑前先做一次"农场门口 eventUp 探测"，true 就重起进程/换存档，否则整跑可能只剩 3 天。
4. 现有口径（`docs/_run10-criteria.md` §6 + `checks.no_blocking_modal=false`）已覆盖"诚实停手"，但缺"如何识别/恢复"这条；脑侧行为本身正确（不 dismiss/sleep/load_save），**无需改脑**。

## 2. `farm.trees` 计数口径（P1）

- **口径（源码）**：`mod/AgentFarm.Bridge/FarmScan.cs:371` `FruitTree` ⇒ `Trees++`；`:373-379` `Tree` 且 **`!stump.Value`** 才 `Trees++`；`:398-399` 树桩单列（Stumps）⇒ **Trees = 果树 + 非树桩树，树桩不计入**。
- **存档逐格核对**（Farm 段 `<GameLocation xsi:type="Farm">`，脚本 `scratch/_t243_farmtrees.py`）：Tree 特征 **836**、其中 `stump=true` **4**、FruitTree **0**、Grass 1152、HoeDirt 44 ⇒ 口径值 **832**；冬 6 晨实测 `farm.trees=832` ⇒ **完全一致，无 bug**。
- **冬 5 −11（839→828）**：存档 stats `<key>TreesChopped</key><value>11</value>` ⇒ 当日砍倒 11 棵；砍倒即变树桩、不再计入 Trees ⇒ −11 与口径自洽。
- **冬 6 晨 +4（828→832）**：离线只有 14:06 之后的终态（836 棵/4 桩），**冬 5 末的逐格快照没落盘** ⇒ 无法归因（"树桩被清掉"不改变 Trees 计数，解释不通）⇒ **判定【无法判定·需真机】**：同日双采样（`observe?detail=full` 的 `farm.trees` + `debug_dump` Farm 逐格 Tree/stump）即可闭合。
- 结论：**Trees 口径正常；−11 有 `TreesChopped=11` 佐证；+4 待真机双采样，当前不判为计数 bug。**

## 3. 证据文件 / 复现
`scratch/t243-il3.txt`（WorldDate 星期）、`scratch/t243-il4.txt`（GameLocation.checkForEvents）、`scratch/t243-il5.txt`（FIND|Precondition：`StardewValley.Preconditions.*` 30+ 处理器全集）、`scratch/t243-mail-winter7.txt`（`Data/mail[winter_7]` = Festival of Ice 通知）、`scratch/t223-ev-Data_Events_Farm.txt`（27 条事件原文）、`scratch/_t243_farmtrees.py`（Farm 逐格树统计）、`scratch/_t243_probe6.py`（账本 L143-149 上下文）。
存档：`C:\Users\admin\AppData\Roaming\StardewValley\Saves\Wahaha_450799035\Wahaha_450799035`（3134241 B，2026-10-18 14:08:28）。
