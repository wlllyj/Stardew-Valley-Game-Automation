# run1 行为合理性取证分析（task-3）

分析者：teammate `log-analyst`（只读取证，不写生产代码、不碰游戏）。
分析对象：`logs\longrun-3day-llm-run1.jsonl`（唯一行为输入，21 行 / 5895 B，mtime 2026-10-11 21:55:53）。
结论定位口径：journal 事件序号（=行号=事件序号，全程 `Ln` 与 `t` 秒并给）、源码片段 + 行号、IL 偏移。

---

## 0. 证据来源、方法与局限

| 证据 | 位置 | 用途 |
| --- | --- | --- |
| run1 LLM journal（21 事件） | `logs\longrun-3day-llm-run1.jsonl` | 唯一"这段运行发生了什么"的记录 |
| run1 对照 journal | `logs\longrun-3day-run1.jsonl` | 非 LLM 兄弟跑的同类"工具无效"现象 |
| run2 LLM journal | `logs\longrun-3day-llm-run2.jsonl` | 独立交叉验证（另一天/另一片地，machine-runner 正在跑） |
| 世界快照（day9 11:10，Farm） | `scratch\obs-full.json` | 地图交叉验证（哪些格是 grass、哪些不是） |
| 源码 | `brain\agentfarm\{longrun,farmwork,planner}.py`、`mod\AgentFarm.Bridge\{UseToolSkill,WorldSnapshot}.cs` | 机制解释 |
| 游戏程序集 IL | `scratch\il-grass-*.txt`、`scratch\il-didclick-u8.txt` | 钉死"镰刀为什么没挥出去" |
| 真机旧记录 | `docs\00-开发日志.md` | 同现象的先验证据 |

**局限（必须随结论一起读）**
1. `brain\agentfarm\longrun.py`、`farmwork.py` 在**我分析期间被他人改动**（mtime 22:13:45 / 22:11:57，均晚于 run1 的 21:55:53），且这两个文件在 git 里是 **untracked（`??`）**，没有历史版本可复原。⇒ 本报告的行号来自我读到的版本（`longrun.py` 1398 行 → 现 1439 行；`farmwork.py` 816 行 → 现更长），**行号可能漂移，以引用的代码片段为准**。当前版本里已经能看到针对 run1 的改动（如 `longrun.py` 注释原文"run1 的两格 grass 就是这么被连挥的"、`farmwork.py` 的 `proven_inert` 与"grass 记 skipped 而不是 failed"），§4 会区分"run1 当时"与"现在"。
2. run1 的 journal 缺 `sleep` / `day_end` / `finish`（§6-E1），所以"睡觉/收工"环节**没有观测证据**，只能给代码路径推断。
3. `scratch\obs-full.json` 是同日 **11:10** 的快照，run1 是 **16:20** 开局；两者 `crops=31 / unwatered=31` 完全一致（说明期间没有种植/清障改变口径），且我用 journal 的"待清理 N"逐片对账三处完全吻合，故作为地图参照风险低。
4. `obs-full.json` 的 `tillable` 是对象数组，我的探针按元组比较得到 0 交集（探针自身局限，不是数据问题）；`kind` 直方图与逐格字段不受影响。

---

## 1. 逐事件时间线与条数统计

### 1.1 条数统计（21 事件）

| event | 条数 | 事件序号 |
| --- | --- | --- |
| day_start | 1 | L1 |
| plot | 1 | L2 |
| decision | 4 | L3, L10, L15, L19 |
| refill | 1 | L4 |
| outcome | 6 | L5, L7, L9, L14, L17 |
| stage_no_target | 3 | L6, L8, L16 |
| policy | 2 | L11, L20 |
| blocked | 2 | L12, L13 |
| idle | 1 | L18 |
| no_intents | 1 | L21 |
| **sleep / day_end / finish** | **0** | —（见 §6-E1） |

### 1.2 时间线

| # | t(s) | event | 关键字段（原文摘要） |
| --- | --- | --- | --- |
| L1 | 0.09 | day_start | day=[1,spring,9] timeOfDay=1620（16:20）stamina=270 money=14 crops=31 **unwatered=31** Farm sunny |
| L2 | 0.13 | plot | zone=field_ne anchor=[56,17] tiles=25；note：`tilesTruncated=true`，400 格上限，**其中 3 格本次没返回**；可锄 17 / 待清理 3 / 待浇水 0 |
| L3 | 5.32 | decision | boundary=new_day source=llm：`water_area(field_ne)` + `till_area(**field_nw**)` + `plant_area(**field_nw**)`；zone=field_ne |
| L4 | 36.06 | refill | ok=true「补水成功（waterLeft 0 → 40）」 |
| L5 | 51.03 | outcome | water_area **VERIFIED**「目标 **32** 步：做成 31、跳过 0、失败 0」 |
| L6 | 51.14 | stage_no_target | till_area leftover=0 **zone=field_ne**（意图 area_hint 是 field_nw） |
| L7 | 51.14 | outcome | till_area needs_review「作业区 field_ne；目标 0 步：做成 0、跳过 0、失败 0；后置条件未成立（还剩 0 格）」 |
| L8 | 51.27 | stage_no_target | plant_area leftover=0 **zone=field_ne** |
| L9 | 51.27 | outcome | plant_area needs_review（同 L7 文案） |
| L10 | 58.11 | decision | boundary=task_kind_change source=llm：`till_area(anchor:field_ne)` + `plant_area(anchor:field_ne)` + `clear_area(anchor:field_ne)` |
| L11 | 58.11 | policy | 「今天不再要已证明没目标的任务 ['plant_area','till_area']」→ intents=["clear_area"] |
| L12 | 70.49 | **blocked** | tile=[58,21] action=clear reason=**「清不掉：这一格还是 grass」** |
| L13 | 70.49 | **blocked** | tile=[56,21] 同上 |
| L14 | 70.49 | outcome | clear_area **VERIFIED**「目标 4 步：做成 2、跳过 0、**失败 2**；后置条件成立」detail=两条 grass |
| L15 | 70.63 | decision | source=deterministic：clear_area(area_hint=near:player)「玩家周围还有 2 处障碍」 |
| L16 | 70.70 | stage_no_target | clear_area leftover=0 |
| L17 | 70.70 | outcome | clear_area needs_review「目标 0 步…还剩 0 格」 |
| L18 | 70.76 | idle | rounds=1 intents=["clear_area"] acted=false |
| L19 | 71.29 | decision | source=deterministic：clear_area(near:player)（**与 L15 逐字相同**） |
| L20 | 71.29 | policy | 「今天不再要已证明没目标的任务 ['clear_area']」→ intents=[] |
| L21 | 71.29 | no_intents | 「今天已经没有任何可做的目标（…['clear_area']）」 |

**耗时分解**：起步到首个 LLM 决策 5.32 s；浇水 31 格 45.71 s（≈1.47 s/格，含 36.06 一次补水）；第二轮 LLM 决策 7.08 s；清障 2 格（4 次工具调用）12.38 s（≈3.1 s/次）；最后 0.66 s 内走完 deterministic→stage_no_target→idle→policy→no_intents。**全程 71.29 s：浇 31 格、开垦 0、播种 0、清障 2 成 2 败、未收工。**

---

## 2. 四类判定

条数：**该做没做 5 条；白做 4 条；无效挥动 1 类 / 4 次；睡觉时机 3 条（其中 1 条为代码路径推断，实况未定）。**

### 2.1 该做没做（5）

- **A1 开垦在 LLM 指定的田区从没被尝试**：L3 `till_area` 的 `area_hint=field_nw`，执行却落在 `field_ne`（L6/L7 `zone=field_ne`）⇒ 当天开垦 **0 格**。证据：L3 vs L6/L7。
- **A2 播种同 A1**：L3 `plant_area(area_hint=field_nw)` → L8/L9 `zone=field_ne`「目标 0 步」⇒ 当天播种 **0 格**（背包有 1 份防风草种子，L10 自己都说"plantable 为 0"）。
- **A3 两格 grass 没清掉**：L12/L13/L14，共 2 格。真机上**不可能成功**（§3），不是运气问题。
- **A4 浇水目标 32 步只做成 31**：L5「目标 32 步：做成 31、跳过 0、失败 0」⇒ 有 1 格目标既没做也没记录（跳过=0、失败=0）；journal 里**找不到第 32 格是谁**（`detail` 只记失败/跳过，成功格永不落盘，见 §5）。
- **A5 收工后世界里仍有大量可动格**：L21「今天已经没有任何可做的目标」与观测矛盾——`scratch\obs-full.json` 的 400 格里 `grass 161 / weed 103 / tree 56 / dirt 36 / stone 28 / twig 16`（同日 11:10；run1 开局作物口径一致），其中 `weed/stone/twig/grass` 全在 `longrun.py` 的 `ACTIONABLE_KINDS = ("weed","twig","stone","grass")`（当前 `longrun.py:53`）里。所谓"没目标"只是"刚被 blocked 的 2 格没目标"。

### 2.2 白做（4）

- **B1 两次 0 目标的阶段空转**：L6-L7（till_area）、L8-L9（plant_area）——每一次都走完"派活→观测→stage_no_target→outcome"，0 步落地（t=51.14、51.27）。
- **B2 一次 LLM 往返用来重提刚被证明为空的任务**：L10 又提 `till_area`/`plant_area`（4.6 s 前 L7/L9 刚证明 0 目标），逼出 L11 拉黑策略（≈7.08 s 的 LLM 往返 + 1 条 policy）。
- **B3 确定性兜底重复派一件已被封的事**：L15 与 L19 逐字相同的 `clear_area(near:player)`「玩家周围还有 2 处障碍」——那 2 处正是 L12/L13 刚 blocked 的 grass 格，于是 L16/L17 又是 0 目标，L18 idle 一轮，L20 再拉黑。
- **B4 idle 空转**：L18 `rounds=1 acted=false`。

（L4 补水不算白做：开局 `waterLeft` 0，31 格作物要用 31/40，补水是必要动作。）

### 2.3 无效挥动（1 类 / 4 次）

- **C1 4 次 scythe 工具调用全部无效**：`farmwork.clear()` 对 grass 走 `tool="scythe"`，且 run1 当时是 `for _ in range(2)`（每格挥 2 次）⇒ (58,21)×2 + (56,21)×2 = 4 次。**四次在真机上都没有产生任何游戏动作**（§3），mod 却每次都回 `ok`「该格原本是（空），现在已经空了」——4 条假回执，journal 侧只留下 L12/L13 两条 blocked（回执不在 journal 里）。
- **其余挥动有效**：L14「做成 2」的 2 格经地图交叉验证是 (59,21) stone 与 (60,18) weed（非 grass），走 hoe/pickaxe 正常成功。
- 对照：run1 journal **没有** `tool_ineffective`/`timeout` 类失败码，与"mod 立刻 Ok"完全一致（真机挥 6 次仍 `UsingTool=false` 的旧记录见 §3 证据 E-5）。

### 2.4 睡觉时机（3）

- **D1（代码路径推断，实况未定）**：L21 `no_intents` 后进入"无意图分支"，会**重新跑一次 `sleep_guard`**；此刻 `unwatered=0`（31 格全浇，L5）⇒ 不满足"先把水浇完"；`stamina=270 ≥ min_stamina=12` ⇒ 不满足"体力不足"；`work_reasons` 因 clear_area 被拉黑+2 格 blocked 而为空 ⇒ 守卫返回 `("no_work")` 放行 ⇒ 调用 `_do_sleep(obs, rep, "no_work")`。**但 journal 没有 `sleep` 事件**，所以"确实调用了睡觉"只有代码路径，没有观测（§6-E1）。
- **D2 判定：不该睡**。即便调用成立，这是在 **day9 16:20、体力 270/270、31 格作物正在生长、地图上还有 161 grass+103 weed+28 stone+16 twig** 的状态下收工，且 `longrun.py` 顶部注释明确写着"没事就睡"是不允许的（我读到的版本 `longrun.py:13`）。
- **D3 run2 的对照是"睡也睡不成"**：`logs\longrun-3day-llm-run2.jsonl:89` `day_end`：`ended_by="sleep_failed"`、`ended_reason="睡觉请求失败"`、`verified=false`，`checks={"slept_by_us":false,"no_hard_failures":false,"crops_watered":true,"day_justified":false}`（t=450.97）。⇒ 睡觉链路自身有故障；run1 若也走到那一步，结果未知（run1 在 t=71.29 后被终止）。

---

## 3. 两个"清不掉"的 grass 格根因

**结论：已定，且是三层叠加。** 两个格不是特殊格，是**连片草地里最普通的 grass 格**；失败原因与"格子"无关，与"镰刀这一次调用根本挥不出去"有关。

### 3.0 目标格的事实（先钉死"不是叠层"）

`scratch\obs-full.json`（Farm，day9 11:10）：
- (58,21) 与 (56,21) 都恰好是 `{"kind":"grass","tool":"scythe","feature":"Grass","standable":true,"actionable":true,"ripe":false,"dead":false,"watered":false,"plantable":false}`：**无 crop、无 object、无第二层**；邻居 55,20=weed、59,21=stone、60,18=weed，30 行内 grass 连片（54..58,21-25 大量 grass）。
- `kind="grass"` 在 mod 里只有一个来源：`mod\AgentFarm.Bridge\WorldSnapshot.cs` 的 `if (tf is StardewValley.TerrainFeatures.Grass) { t.Kind="grass"; t.Tool="scythe"; }`（objects 侧的 weed/twig/stone 另有 `o.IsWeeds()/IsTwig()/IsBreakableStone()`）⇒ **grass = Grass 地形特征物体**，不是地形贴图。

**被代码逻辑否决的假设（H_叠层）**：`farmwork.clear()` 的判据是 `gone = (kind_now not in DEBRIS_KINDS) if not want_grass else (kind_now != GRASS_KIND)`，而 `DEBRIS_KINDS=("weed","twig","stone")` 不含 grass ⇒ 若一格原来是 weed、清完露出 grass，会被判 **成功**（"已清掉（kind weed → grass）"）。既然 journal 记的是**失败**「这一格还是 grass」，进 `clear()` 前该格 `kind` 就**已经是 grass**、工具走 scythe 分支。答案与 obs-full 一致 ⇒ **"同格叠 weed/twig 两层"不成立**。

### 3.1 第一层（决定性）：镰刀（MeleeWeapon）在 mod 的入口下**挥不出去**

证据链（IL，转储见 `scratch\il-grass-1-u8.txt`、`scratch\il-didclick-u8.txt`）：

1. `mod\AgentFarm.Bridge\UseToolSkill.cs` 的 `Swing()` —— **它只调这一个游戏 API**：`UseToolSkill.cs:270` `p.faceDirection(dir)`（dir 由 `(Math.Abs(dx)>=Math.Abs(dy)) ? (dx>0?1:(dx<0?3:2)) : (dy>0?2:0)` 算）→ `UseToolSkill.cs:273` `Game1.pressUseToolButton();`。（该文件 mtime 20:13:26，早于 run1 的 21:55:53 ⇒ 就是 run1 运行的桥。）
2. `Game1.pressUseToolButton()`（`scratch\il-grass-1-u8.txt:177-858`）里，当前工具是近战武器时有一道**输入门闸**：
   `IL_0826 CurrentTool` → `IL_082B isinst MeleeWeapon` → `IL_0830 brfalse IL_083D`（不是近战武器就直接去准备挥动）→ `IL_0832 ldc.i4.1`（参数 ignoreNonMouseHeldInput=true）→ `IL_0833 call Game1.didPlayerJustLeftClick` → `IL_0838 brfalse IL_0913`（**为假就跳到结尾 `ldc.i4.0; ret`，什么都不做**）。
3. `Game1.didPlayerJustLeftClick(Boolean)`（`scratch\il-didclick-u8.txt`，51 行）只在**真实输入边沿**上返回 true：鼠标左键本帧刚按下（`IL_000B-IL_0023`）／手柄 X 刚按下（`IL_0024-IL_0056`）／键盘 `options.useToolButton` 刚按下（`IL_0057-IL_008C`）；否则 `IL_008D ldc.i4.0; ret`。**自动化运行时没有任何人类输入 ⇒ 恒 false。**
4. ⇒ 镰刀（`(W)47`，`WorldSnapshot` 里 `isTool=true` 的 MeleeWeapon；`MeleeWeapon.IsScythe(String id)` 对 `"(W)47"/"(W)53"/"(W)66"/"47"/"53"/"66"` 返回 true）走 `IL_0913` 直接返回：**不调 `player.BeginUsingTool()`、`UsingTool` 保持 false、没有挥动动画**。
5. 而割草的唯一伤害路径在动画里：`MeleeWeapon.DoDamage(...)` 的 `IL_020C terrainFeatures.TryGetValue` → `IL_021F **ldc.i4.0**` → `IL_0222 tf.performToolAction(this, 0, tile)` → `IL_0227 brfalse IL_023C`（返回 false 就跳过）→ `IL_0236 location.terrainFeatures.Remove(tile)`（`scratch\il-grass-3-u8.txt`）；`FIND|DoDamage` 的调用方是 `Farmer.showSwordSwipe` / `MeleeWeapon.doDaggerFunction` / `MeleeWeapon.setFarmerAnimating`——**伤害由挥动动画驱动**。
6. 并且 `Grass.performToolAction(Tool,Int32,Vector2)` 自己**从不移除地形特征**（`scratch\il-grass-1-u8.txt:2-116`）：它只 `numberOfWeeds.Value = numberOfWeeds.Value - loc2`（`IL_00F5-IL_0108`）然后 `return TryDropItemsOnCut(t, true)`（`IL_0115-IL_011D`）；移除只发生在第 5 步的 `Remove`，即只有 `performToolAction` 返回 true 才移除，而 `Grass.TryDropItemsOnCut` 的 `IL_0000-IL_001A / IL_0386-IL_0389` 是：**`numberOfWeeds > 0 ⇒ return false`；只有 `numberOfWeeds == 0` 才 `return true`**（`scratch\il-grass-2-u8.txt:2-279`）。
7. ⇒ 因果链闭合：**没有输入边沿 ⇒ 没有挥动 ⇒ `DoDamage` 不执行 ⇒ `Grass.performToolAction` 从未被调用 ⇒ `numberOfWeeds` 永不减 ⇒ 地形特征永不被移除 ⇒ `kind` 永远是 grass。**

**真机先验证据（同现象早已出现过）**：`docs\00-开发日志.md:323-333` 原文记录首版 `auto` 把 weed 映射成 scythe 的真机结果——"`tool_ineffective`：挥了 6 次、`UsingTool` **始终 false**、格子纹丝不动（体力也不掉）"，逐工具诊断证明 `tool="hoe"` 一次就清掉（524 ms，体力 266→264）。当时把它归因为"杂草该用锄头"（对杂草成立，0.7.8 据此改成 hoe）；真正的机制是**镰刀这一次 tool 入口根本挥不动**——对杂草、对 grass 一视同仁。

**交叉验证（地图 × journal，n=12 次 clear 步骤，三片田区）**——用 `scratch\_probe_map.py` 读 `scratch\obs-full.json`，把 journal 的 `plot` 锚点当 5×5 左上角取 ACTIONABLE 格：

| journal 事件 | 田区/锚点 | 地图上的清障目标 | journal 结果 | 吻合 |
| --- | --- | --- | --- | --- |
| run1 L2/L14 | field_ne [56,17]（5×5 内只返回 5 格，与 note"3 格没返回"一致） | (56,21)grass、(58,21)grass、(59,21)stone、(60,18)weed = **2 grass + 2 非 grass** | 4 步做成 2 失败 2，失败=两格 grass | ✅ |
| run2 事件（t=61.88） | field_ne [71,17] | (71,21)weed、(73,21)weed、(74,19)stone、(74,21)weed = **4 非 grass** | 4 步做成 4 失败 0 | ✅ |
| run2 事件（t=134.22） | field_ne [61,26] | (61,27)weed、(62,26)stone、(64,26)stone、(65,26)grass、(65,27)grass = **3 非 grass + 2 grass** | 5 步做成 3 失败 2，失败=(65,26)/(65,27) grass | ✅ |

⇒ **非 grass 7/7 成功；grass 5/5 失败（0 成功）**；(51,12) 那格不在 400 格窗口内（journal 记为 grass 且失败）不影响结论。这排除了"随机性/位置/站不过去"的解释（4 个 grass 格 `standable=true`，且 till 的 blocked 另有"四邻都站不过去"的独立 reason）。同时它也排除了 H_多刀计数：`farmwork.clear()` 对每格挥 2 次，若 grass 真能被割，`numberOfWeeds≤2` 的格子至少该偶尔成功——**5 格 0 成功**，只有"一次都没挥出去"能解释。

### 3.2 第二层：mod 的回执**谎报成功**（回执说 ok、观测没变）

`mod\AgentFarm.Bridge\UseToolSkill.cs` 的 `Done()`（`UseToolSkill.cs:427`）：`hoe` 判 `hd != null`、`can` 判 `hd != null && watered`，**其余工具**只判 `UseToolSkill.cs:448` `if (hasObject) return false;` 加 `tf is Tree / FruitTree / ResourceClump` 四道 ⇒ `return true`——**完全没判 `tf is Grass`（对全文件 grep `is Grass` 命中 0 次）**。grass 格恰好"无 object、无 Tree/FruitTree/ResourceClump"⇒ `Done()` 立刻 true ⇒ 返回 `Ok(status="ok", reason=…"该格原本是（空），现在**已经空了**")`。⇒ 上面 C1 的 4 条假回执就是这么来的。

（客户端没被这个假回执骗过：`farmwork.clear()` 只看回执之外的 `tiles[]` 重快照⇒ 记失败。这正是 `docs\00-开发日志.md:296` 立的规矩——"验收**必须用 `tiles[]` 差分**，回执只是声明"。）

### 3.3 第三层：失败被"封格"机制洗成 `VERIFIED`

- `longrun.py`：`_mark_blocked(before,after,steps,rep)` 只对 `s.failed and s.tile and s.action in ("till","clear","sow")` 且"整格关键状态 `before.get(key)==after.get(key)`"的步，写 `self.blocked[key]=f"{action} 无效：{reason[:80]}"` 并 `journal("blocked",...)`（我读到的版本 `:798-819`；当前版 `longrun.py:801-829`，判据片段 `if key in self.blocked or before.get(key) != after.get(key): continue`）。
- 关键**次序**：run1 当时的阶段收尾是 `fresh=_snap()` → `_mark_blocked(obs, fresh, all_steps, rep)` → `leftover=_leftover(task, fresh, plot)` → `met = bool(all_steps) and not leftover`（我读到的版本 `:882-888`；当前版 `longrun.py:914-918`，注释"⚠️ 后置条件必须**先有目标**才算成立"）。
- 而 `_leftover` 的 clear_area 分支写着 `kind ∈ ACTIONABLE_KINDS **and t not in self.blocked**`（当前 `longrun.py:661`）。
- ⇒ **刚刚被 blocked 的格，立刻被 `_leftover` 排除** ⇒ `leftover=∅` ⇒ `met=True` ⇒ `planner.classify_outcome`（`planner.py:692-711`：`if postcondition_met and not skipped and not error: return TERMINAL_VERIFIED`；该函数注释明确"刻意不提供第三个'部分完成'状态"）给 **VERIFIED**。
- 于是 L14「目标 4 步：做成 2、**失败 2**；后置条件**成立**」+ `postcondition_met=true`；并且 `error` 只因 `failed and not met` 才置位（我读到的版本 `:899-901`）⇒ 这里 `error=None`、`fail_streak` 归零（`:783-784`），**2 个硬失败在任务层等于没发生**。run2 三处同类事件（t=134.22 的 5 步 3 成 2 败、t=209.69 的 1 步 0 成 1 败、t=61.88）**同样 VERIFIED**。

### 3.4 未定项（不影响上面的结论）

- **`(W)47` 的 `WeaponData.Type` 到底是不是 2**：`MeleeWeapon.ReloadData()` 是 `type.Value = WeaponData.Type`（数据驱动，`scratch\il-grass-4-u8.txt`），而武器数据打包在 `Content\Data\Weapons.xnb`（约 2738 B，非 JSON）⇒ 读不到。若 `type==2`，`Grass.performToolAction` 会因 `DoDamage` 恒传 `explosion=0` 而无条件 `return false`（另一条独立死路）；但**这条被第一层完全掩盖**（一刀都没挥出去），所以不影响根因与修复方向。已核实 `WeaponDataDefinition.GetData(String)` 只写 `Category = IsScythe ? -99 : -98`，**不设置** `Type`。
- **修好入口后才会暴露的次级风险（重要，别漏）**：`numberOfWeeds` 每刀只减 `loc2`（普通镰刀 1、金镰刀 2，见 `Grass.performToolAction` 的 `IL_00A9-IL_00D8`），且特征只在 `numberOfWeeds==0` 时才移除 ⇒ 割一格 grass 需要**多刀**（1..4 刀），而 run1 当时 `farmwork.clear()` 只挥 `for _ in range(2)` 两次 ⇒ 即使入口修好，`numberOfWeeds≥3` 的格子仍会"挥两刀还是 grass"。修复必须同时把"挥到 `kind` 变化或达上限 N 次"作为循环条件（当前工作区 `farmwork.py` 顶部注释已写"挥了世界没变也只挥**一次**"，是朝这个方向动，但**次数上限未与 numberOfWeeds 关联**）。
- **run1 为何在 t=71.29 后终止**：未定（见 §6-E1）。

---

## 4. 修复建议（按收益排序）

> "现象 → 机制 → 改哪里 → 怎么验（含**不需要真机**的验法）"。前 3 条是收益最高的。

### R1（最高）让镰刀/近战武器能真正挥出去——否则所有割草路径都是死代码
- **现象**：grass 5/5 全失败、非 grass 7/7 全成功；真机旧记录"挥 6 次 `UsingTool` 始终 false、格子纹丝不动、体力不掉"（`docs\00-开发日志.md:324-325`）。
- **机制**：`UseToolSkill.Swing()` → `Game1.pressUseToolButton()`；该方法对 `CurrentTool is MeleeWeapon` 要求 `didPlayerJustLeftClick(true)`（本帧真实输入边沿），自动化恒 false ⇒ `IL_0913` 返回，不 `BeginUsingTool()`、无动画、`MeleeWeapon.DoDamage` 不执行（§3.1）。
- **改哪里**：`mod\AgentFarm.Bridge\UseToolSkill.cs` 的 `Swing()`（`UseToolSkill.cs:273` 的 `Game1.pressUseToolButton()` 调用点）与 `Step()`（`:141` `if (this._swings >= MaxSwings)` 及等待/判完成逻辑）。可行方向（须逐一验证，不要凭猜）：
  1. 调用前**构造一帧输入边沿**（把 `Game1.oldMouseState.LeftButton` 或 `oldKBState`/`oldPadState` 置成"本帧刚按下"的状态），再调 `pressUseToolButton()` 并让游戏自己走完 `BeginUsingTool`/动画——最贴近原版路径；
  2. 或跳过门闸直接驱动使用路径（设 `player.lastClick` + `player.FacingDirection` + `player.BeginUsingTool()`，并确认 `usingTool` 变成 true）；
  3. 明确**不能**用 `CurrentTool.DoFunction(...)` 代替：`MeleeWeapon.DoFunction` 不调 `DoDamage`，割草无效（`scratch\il-grass-3-u8.txt:266-386`）。
- **怎么验**：免真机——对 `Swing()` 写断言/回放：请求后 `UsingTool` 必须为 true，且回执 reason **不得**是"已经空了"；真机——同一 grass 格连挥 1-2 刀后 `tiles[]` 差分必须出现 `kind != grass`（这是"验收只看观测"的口径）。**别用回执当验收。**

### R2 让验收门闸不再被"封格"洗白：有 failed 步 ⇒ 不许 VERIFIED
- **现象**：run1 L14（2 成 2 败却 `VERIFIED/postcondition_met=true`）、run2 三处同类（含 1 步 0 成 1 败仍 VERIFIED）。
- **机制**：`_mark_blocked` 先把失败格写进 `self.blocked`，紧接着 `_leftover` 用 `t not in self.blocked` 把它排除 ⇒ `met=True` ⇒ `classify_outcome` 给 VERIFIED（§3.3）。
- **改哪里**：`brain\agentfarm\longrun.py` —— `_leftover`（`longrun.py:655-668`，clear_area 分支 `:661`）不要用 `self.blocked` 当"已解决"；或 `met`（`longrun.py:918`）额外要求 `not failed and not skipped`；或 `brain\agentfarm\planner.py:692-711` 的 `classify_outcome` 增加"存在 failed 步 ⇒ 不得 VERIFIED"。三者取其一即可，但**必须同时保留 `blocked` 的"今天别再白试"用途**（两件事解耦：封格 ≠ 已完成）。
- **怎么验**：免真机——`tests\test_longrun.py` 加用例：构造 clear_area 2 格失败 + 世界不变 ⇒ 断言 `terminal != VERIFIED`、`postcondition_met is False`；再补一条"目标 0 步 ⇒ 不得 VERIFIED"（现在靠 `bool(all_steps)` 兜着，值得锁死）。

### R3 修 `UseToolSkill.Done()` 的判据：地形特征没消失就不算完成
- **现象**：4 次空挥全部回 `ok`「已经空了」，journal 侧只有 2 条 blocked（§3.2 / §5）。
- **机制**：`Done()` 只判 `hasObject`/`Tree`/`FruitTree`/`ResourceClump`，漏掉 `tf is Grass`（以及其他 terrainFeature）。
- **改哪里**：`mod\AgentFarm.Bridge\UseToolSkill.cs` 的 `Done()`（`UseToolSkill.cs:427`，`hasObject` 判据在 `:448`）：加 `if (tf is Grass) return false;`（更稳妥是"凡 `terrainFeatures` 命中目标格且该工具不动它 ⇒ false"），并在 `Fail` 时回带 `kind_now` 让上层能记"回执与观测不符"。
- **怎么验**：免真机——用 `tools\fake_bridge.py` 造一格 grass，断言 `use_tool(scythe)` 不得返回 ok；真机——回执 ok 的格必须 `tiles[]` 差分真的变了（对账脚本：把回执与差分逐格比对）。

### R4 早睡防线：`no_work` 不能因为"格子被封"就成立
- **现象**：L21 后按代码路径会 `_do_sleep(..., "no_work")`，此时 16:20、体力 270/270、地里还有 161 grass+103 weed+28 stone+16 twig。
- **机制**：`work_reasons` 只看"还有没有目标格"，而 blocked 把仅有的目标清空 ⇒ `sleep_guard` 判 `no_work` 放行（我读到的版本 `:698-723`、无意图分支 `:1195-1219`；当前版 `_do_sleep` 调用点与 `no_intents` journal 在 `longrun.py:1258` 附近）。
- **改哪里**：`brain\agentfarm\longrun.py` 的 `work_reasons`/`sleep_guard`：把"被封的格"和"真的没有可动格"分开——若观测里仍有 `ACTIONABLE_KINDS` 或作物需要照顾，且 `timeOfDay < sleep_at`，`no_work` 不应成立（或至少不直接睡）。
- **怎么验**：免真机——`tests\test_longrun.py` 造"作物全浇 + 2 格 blocked + 观测里仍有 weed"⇒ 断言 `sleep_guard(...)[0] is False`；真机——run3 观察是否还会在 16:20 前后出现 `sleep` 事件。

### R5 `area_hint` 落到执行（否则 LLM 的"去哪片地"形同虚设）
- **现象**：L3 `till_area/plant_area(area_hint=field_nw)` → L6-L9 `zone=field_ne`（当天开垦/播种 0 格）。
- **机制**：执行用 `self.pending_zone_hint` + 统一选片（`longrun.py:1073-1080` 注释"方向由大模型给、坐标由代码落"），但 run1 里最终 zone 仍是 `field_ne`，`area_hint` 没生效。
- **改哪里**：`longrun.py` 的 `_execute` 里 `pending_zone_hint` 与选片打分/`_pick_plot` 的优先级，或在 stage 层按 `area_hint` 覆盖 `plot`。
- **怎么验**：免真机——单测：意图 `area_hint=field_nw` ⇒ 断言 `_stage_tiles` 的池来自 field_nw 的锚点；真机——journal 的 `zone` 与意图 `area_hint` 必须一致（现在 `plot`/`stage`/`outcome` 三条都带 zone，可直接对账）。

### R6 观测完整性：400 格上限正在污染判断依据
- **现象**：L2 note 明确"`tilesTruncated=true`…其中 3 格本次没返回"；run2 每个 `plot` 都带同类 note（"其中 4 格没返回"）。
- **机制**：`tiles[]` 以玩家为中心截断到 400 格 ⇒ `plot` 统计、`_stage_tiles` 池、`_leftover`、`_mark_blocked` 都建在残缺快照上；"看得见却没有可动目标"的判定（`_verify_intents` 的 keep/unknown/cancel）也会被影响。
- **改哪里**：`mod\AgentFarm.Bridge\WorldSnapshot.cs`（分片/按田区拉取或提高上限）+ `brain\agentfarm\longrun.py` 的 `plot_observe`（`:549-551` 用 `skip=self.blocked` 的局部观测）。
- **怎么验**：免真机——用 `logs\observe-farm-sample.json` 这类大快照做回归，断言 `tilesTruncated=false` 时统计与逐格一致；真机——同一天两次观测同一田区的"待清理"数应稳定。

### R7 记账与文案（低成本、立即可做）
- L5"目标 32 步：做成 31、跳过 0、失败 0"少了 1 步 ⇒ 在 `rep.stages` 里补"未执行"计数，或让 `run_stage` 回带"目标被丢弃的原因"。
- L7/L9/L17"目标 0 步…**后置条件未成立（还剩 0 格）**"是自相矛盾的文案（0 目标时 leftover 也是 0，`met` 只因 `bool(all_steps)` 为 False）⇒ 文案应改成"这一阶段没有可动目标"。
- `detail` 只记失败/跳过的前 3 格（我读到的版本 `:911-918`）⇒ 成功格永不落盘，事后无法核对"哪 31 格浇了水"；建议 stage 级记成功格的 hash/计数下界。

---

## 5. 与"验收只看观测"冲突的地方（单列一节）

"验收只看观测（`tiles[]` 差分），回执只是声明"（`docs\00-开发日志.md:296`）这条规矩，在 run1 里有 **4 处被违反或绕过**：

1. **回执说成功、观测没变（4 次）**：`use_tool(scythe)` 对 (58,21)/(56,21) 各 2 次都回 `ok`「该格原本是（空），现在**已经空了**」，而观测 `kind` 仍是 `grass`（§3.2）。回执侧没有任何"我没做成"的信号，journal 里也**没有**记录这次矛盾（只留下失败的 blocked）。
2. **任务级 VERIFIED 与逐格失败并存（1 处，run2 3 处）**：L14 `terminal=VERIFIED, postcondition_met=true` 与 `失败 2` 写在同一行。日级 checks 确实能抓到硬失败（run2 `day_end`：`no_hard_failures=false`），但 **run1 根本没走到 `day_end`**，所以 run1 的失败没有任何上层兜住。
3. **"世界没变"被当成"已经解决"**：`_mark_blocked`→`_leftover` 的次序把"动不了"洗成"没剩余"（§3.3）。观测（`before==after`）本来正好证明"任务没完成"，却被用于**反向**结论。
4. **mod 的 `actionable=true` 与真机不可动矛盾**：`obs-full.json` 里 4 个失败 grass 格都带 `standable=true / actionable=true`（观测层声称可动），真机一次都动不了（§3.1）。⇒ `actionable` 字段当前**不能**作为"能不能做"的依据。

---

## 6. 我发现但没人交代过的异常

- **E1 run1 没有收尾事件，且文件是完整的**：`sleep`/`day_end`/`finish` 一个都没有，而 `_do_sleep` 成功/失败都会 `journal("sleep",...)`、`run()` 正常结束必写 `finish`、`_journal` 每行 `write+flush`；文件 21 行、末行 CRLF 完整、mtime 21:55:53 ⇒ **不是写到一半被截断**，而是进程在 t=71.29 落盘之后、`_do_sleep` 的桥调用返回之前被外部终止（`tools\run-longrun.py` 对 `KeyboardInterrupt` 直接 return、不写 finish）。**后果：run1 的"睡觉/收工"环节没有任何行为证据，§2.4-D1 只能是代码路径推断。**
- **E2 人类可读日志没生成**：任务描述里提到的 `logs\longrun-3day-llm-run1.log` **不存在**（同目录只有 jsonl 与一个非 LLM 兄弟 `logs\longrun-3day-run1.jsonl`）。排查 run1 只能读 jsonl。
- **E3 run2 是"睡也睡不成"**：`logs\longrun-3day-llm-run2.jsonl:89` `ended_by="sleep_failed"`、`ended_reason="睡觉请求失败"`、`verified=false`。睡觉链路本身有故障，而 run1 恰好没走到这一步 ⇒ **"能不能睡"这件事两跑都没有成功样本**。
- **E4 分析目标源码在我分析期间被改动、且不受版本控制**：`brain\agentfarm\longrun.py`（mtime 22:13:45）与 `farmwork.py`（22:11:57）都晚于 run1（21:55:53），且 `git status` 显示二者均为 **untracked（`??`）**⇒ run1 时代的行号无法复原。当前版本已经包含针对 run1 的改动（`longrun.py:890-895` 注释原文"…若等到阶段结束才 `_mark_blocked`，同一格注定干不动的格子会在后续每一轮被重新选中再白试一次（**run1 的两格 grass 就是这么被连挥的**）"；`farmwork.py` 新增 `proven_inert`，并把"挥了镰刀还是 grass"改记 `skipped`）。⇒ **本报告行号仅供定位，结论请以代码片段与 journal 字段为准**；同时提醒：§3.3 的"blocked 洗白 VERIFIED"在当前版本**依然成立**（`longrun.py:661` + `:914-918`：`_leftover` 仍排除 `self.blocked`，`met` 仍只看 `all_steps` 非空 + leftover 空），即 **R2 还没修**。
- **E5 自相矛盾的 outcome 文案**：L7/L9/L17「目标 0 步：做成 0、跳过 0、失败 0；后置条件未成立（还剩 **0** 格）」——"还剩 0 格"会误导读者以为还有工作未做。
- **E6 记账缺口**：L5「目标 32 步：做成 31、跳过 0、失败 0」少了 1 步且无任何说明；journal 不记成功格（`detail` 只记失败/跳过的前 3 格）⇒ 事后无法独立复核"浇了哪 31 格"。
- **E7 `area_hint` 与执行 zone 不一致**：L3（field_nw）vs L6-L9（field_ne）；L10 起 LLM 改口 `anchor:field_ne` ⇒ **field_nw 的开垦/播种一整天没被尝试过**，而它恰恰是 LLM 两次都想去的地方。
- **E8 journal 里看不出"回执 ok 但差分不变"**：4 次假回执在 journal 中不留痕（没有"回执与观测不符"事件类型），只能靠"blocked reason"反推 ⇒ 观测层缺一条最重要的对账信号。

---

## 7. 一句话总评（含"几分像人"）

**像人程度 3/10**：run1 的 71 秒里，唯一真实的产出是**把 31/32 格作物浇了水**（量上像人、策略上无错）；开垦与播种因"LLM 说的田区（field_nw）被执行的田区（field_ne）顶掉"而从未尝试，清障则被**一个 IL 级输入门闸**（程序化调用 `Game1.pressUseToolButton()` 对 MeleeWeapon 恒被 `didPlayerJustLeftClick` 拦下、镰刀一次也没挥出去）全部浪费，随后**回执谎报成功、封格机制把 2 个硬失败洗成 `VERIFIED`、并把仅有的目标清空到足以在 16:20 触发"没事干 ⇒ 睡觉"**。**最大浪费**是"两次把已证明 0 目标的活再派一遍 + 4 次注定无效的挥动"，但真正的病根不是浪费而是**撒谎**：程序化输入 ≠ 真实输入边沿，而观测/回执/验收三层里只有 `tiles[]` 差分说了真话。

---

## 附录：证据文件与复核命令

| 文件 | 内容 |
| --- | --- |
| `logs\longrun-3day-llm-run1.jsonl` | 分析对象（21 事件；§1 全表逐行来自它） |
| `logs\longrun-3day-llm-run2.jsonl` | 交叉验证（grass 失败复现、`day_end`/`sleep_failed`） |
| `scratch\obs-full.json` | day9 11:10 Farm 世界快照（kind/feature 直方图、逐格字段） |
| `scratch\il-grass-1-u8.txt` | `Grass.performToolAction`、`Tool.isScythe`、`Farmer.useTool`、`Farmer.BeginUsingTool`、`Game1.pressUseToolButton`（L177-858） |
| `scratch\il-grass-2-u8.txt` | `Grass.TryDropItemsOnCut`、`Grass..ctor`、`MeleeWeapon.IsScythe`、`GameLocation.performToolAction` |
| `scratch\il-grass-3-u8.txt` | `MeleeWeapon.DoDamage`（IL_020C-IL_0236 关键段）、`MeleeWeapon.DoFunction` |
| `scratch\il-grass-4-u8.txt` | `MeleeWeapon.ReloadData`（type 数据驱动） |
| `scratch\il-didclick-u8.txt` | `Game1.didPlayerJustLeftClick`（只认真实输入边沿） |
| `scratch\il-find-*.txt` | `FIND\|DoDamage`（4 个调用方）、`FIND\|isScythe`、`FIND\|performToolAction` |
| `scratch\_probe_map.py` | 只读地图交叉验证探针（§3.1 表格的来源） |
| `docs\00-开发日志.md:296,323-333` | "验收必须用 `tiles[]` 差分" + 镰刀空挥的真机旧记录 |

复核命令（只读，从工作区根执行）：

```powershell
# 事件/阶段/步数统计
& $py tools\longrun-report.py logs\longrun-3day-llm-run1.jsonl --top 5
# 地图交叉验证（读 scratch\obs-full.json）
& $py scratch\_probe_map.py
# IL 探针（需游戏目录）
tools\il-probe\bin\Release\Probe26.exe "D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley" "StardewValley.Game1|didPlayerJustLeftClick"
```
（`$py` = `C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`；IL 转储为 UTF-16LE，用 `tools\_tmp_conv.py <src> <dst>` 转 UTF-8 再读。）
