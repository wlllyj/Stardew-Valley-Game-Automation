# sleep_failed 根因取证（task-6）

> 取证者：log-analyst ｜ 日期：2026-10-11 ｜ 现场：`logs\longrun-3day-llm-run2.jsonl`（run2）、`C:\Users\admin\AppData\Roaming\StardewValley\ErrorLogs\SMAPI-latest.txt`、`logs\probe-sleep-run2.txt`（对照探针）
> 只读取证：本报告未修改 `brain\`、`mod\`、`tests\`，未对游戏/桥发起任何动作。

## 0. 一句话结论（已定）

run2 的两次 `sleep` 失败**不是** Mod 把"睡觉"这条指令拼错了 —— Mod 发的就是**游戏自己的睡觉入口**（`GameLocation.answerDialogueAction("Sleep_Yes", null)`，IL 与 `FIND` 双重确认）。失败的原因是：**调用时游戏根本没有进入跨日流程**。

SMAPI 日志证明：两次各 180 s 的窗口内 **完全没有 NewDay 的任何工作**——没有 `Synchronizing 'NewDay' task...`，没有 `SaveGame.Save()`，日期不变（L1213→L1214、L1221→L1222）。而对照探针（玩家真的在床上、`isInBed=true`）**1.73 s** 就完成了跨日 + 落盘（L103-L113）。

⇒ **睡觉能不能成，取决于"调用那一刻的游戏状态"（人是否真的在床上 / 睡觉提问是否开着），而不是取决于调用本身。** Mod 的兜底路径在状态不满足时**静默无效**（无异常、无报错），只能等满 180 s 超时再报 `code=failed`。
⇒ brain 的 `sleep()` 序列 `ensure_location(home)` → `bed_tile(obs)` → `stand_next_to(bed)` → `interact(bed)` → `client.sleep()` **四步里没有任何一步担保"进了床"或"提问开了"**，它只担保"站到床边 + 按了一次动作键"。

## 1. 两个现场对照

| | **PASS**（对照探针 22:07:55） | **FAIL #1**（run2 t=450.97） | **FAIL #2**（run2 t=631.16） |
|---|---|---|---|
| 脚本/调用方 | `scratch\probe_sleep.py`（直接 `BridgeClient().sleep()`） | `brain\agentfarm\farmwork.py` 的 `sleep()` | 同左 |
| 发请求前的状态 | spring 9、`timeOfDay=630`、FarmHouse、**tile [9,9]（床上那格）**、**`isInBed=true`**、stamina 270、worldSeq 4 | spring 10、`timeOfDay=1200`、FarmHouse、`isInBed=false`（machine-runner 观测：原本站 Farm(55,16)，`ensure_location` 才传进 FarmHouse） | spring 10、`timeOfDay=1610`、FarmHouse、**tile [8,8]**（床在 **[9,8]**）、**`isInBed=false`**、stamina 74、money 14 |
| Mod 走哪条路 | ② 兜底 `answerDialogueAction`（L103 只有这一条 sleep TRACE） | ② 兜底（L1213 同一文本） | ② 兜底（L1221 同一文本） |
| 耗时 / 回执 | **1.8 s**，`ok=true`，reason「已跨日：第 8 天 → 第 9 天…」，`elapsedMs=1733`，`uiOpened=false` | **180025 ms → `ok=false`** | **180020 ms → `ok=false`** |
| 游戏侧指纹 | L104 `Synchronizing 'NewDay' task...`、L107 `Context: before save.`、L109 `Synchronizing 'Save' task...`、L113 `after save, starting spring 10 Y1` | **180 s 内零 NewDay、零 Save**（L1213–L1214 之间只有时间戳，没有任何 TRACE game/SMAPI 行） | **同样零 NewDay、零 Save**（L1221–L1222） |
| 存档 | main mtime 21:46:56 → 22:07:58，size 3452166 → 3481024 | 不变 | 不变 |
| 结算 | PROBE VERDICT: PASS（日期前进 + 进程存活 + 存档 mtime 前进） | `day_end ended_by="sleep_failed"`、`verified=false`、`checks.slept_by_us=false` | `day_end`（第二次，同一天）、L93 `no_day_progress`、L94 `finish code=1` |

**唯一稳定的差别：调用那一刻"人在不在床上"。**

## 2. 证据链（每条都有定位）

### 2.1 SMAPI 日志（真机、`ErrorLogs\SMAPI-latest.txt`，1258 行）
- 对照成功：L103 sleep TRACE → L104 `Synchronizing 'NewDay' task...` → L107 `Context: before save.` → L109 `Synchronizing 'Save' task...` → L113 `Context: after save, starting spring 10 Y1.`（22:07:55–22:07:59）
- 第一次失败窗口：L1204 `[22:12:39 TRACE game] Warping to FarmHouse`（= `ensure_location`）→ L1205 exec 3663ms → L1209 exec 4ms → L1210 exec 1855ms → L1211 exec 19ms（= `bed_tile`/`stand_next_to`/`interact`）→ **L1213 `[22:12:41 TRACE AgentFarm Bridge] sleep：answerDialogueAction("Sleep_Yes")（已交给游戏自己的 answerDialogueAction…）`** → **L1214 `[22:15:41 INFO AgentFarm Bridge] POST /v1/exec → 200 · 180025ms · worldSeq=352`**
- 第二次失败窗口：L1219 exec 2ms → **L1221 `[22:15:42] sleep：answerDialogueAction("Sleep_Yes")`** → **L1222 `[22:18:42] POST /v1/exec → 200 · 180020ms · worldSeq=377`**
- 反证（跨日机制本身没坏）：L1230 `[22:22:52 TRACE game] Warping to FarmHouse` → **L1231 `[22:22:53 TRACE SMAPI] Synchronizing 'NewDay' task...`** → L1242 `before save.` → L1244 `SaveGame.Save() called.` → L1249 `after save, starting spring 11 Y1.`（这是游戏自己 02:00 昏倒触发的）。
- 全日志 `Synchronizing '...'` 只出现 8 次：L72/75/79/81（`Load_*`）、**L104（NewDay，PASS）**、L109（Save，PASS）、**L1231（NewDay，晕倒）**、L1245（Save，晕倒）；`Context: before save.` 只在 L107、L1242。⇒ **"有没有 NewDay"用 SMAPI 这两行判定是干净的**。
- 全日志 `TRACE AgentFarm Bridge` 只有 3 条（L103/L1213/L1221）⇒ 整个会话 mod 只发起过 3 次 sleep，且**三次都走兜底 ②**（`TryAnswerOpenQuestion` 分支一次都没走）。日志里**没有任何** multiplayer / farmhand / disconnect / ReadyCheck / netReady 相关行。

### 2.2 journal（`logs\longrun-3day-llm-run2.jsonl`）
- L88 `{"event":"sleep","t":450.97,"ok":false,"code":"failed","reason":"睡觉请求失败","before":{"day":[1,"spring",10],"timeOfDay":1200,"stamina":74.0},"after":null}`
- L89 `day_end`：`ended_by="sleep_failed"`、`verified=false`、`checks={"slept_by_us":false,"no_hard_failures":false,"crops_watered":true,"day_justified":false}`、8 个田区明细
- L90 `day_start t=450.99 day=spring 10 timeOfDay=1610 location=FarmHouse`
- L91 第二次 sleep：同样 `ok:false/code:failed/reason:睡觉请求失败/before timeOfDay=1610`
- L92 `day_end`：`no_hard_failures=true`、`notes:["睡觉失败：睡觉请求失败（no_work:确实找不到可做的活…）"]`、`final={"…","tile":[8,8],"isInBed":false,"waterLeft":27,…}`
- L93 `no_day_progress`；L94 `finish code=1 actions=117 minutes=10.52`
- **journal 的价值缺口（已定）**：`longrun.py` 的 sleep 事件只落 `code`/`reason`（`"睡觉请求失败"` 是 brain 自己的措辞），**Mod 回执里真正有用的 `reason` 正文（含 `Diagnose()`：`isInBed`/`Game1.newDay`/`activeClickableMenu` 类型名/`dialogueUp`/`pauseTime`/`gameMode`/`newDaySync` 状态）全部丢失**。run2 又**没有 stdout `.log`**（`logs\` 106 个文件里没有），所以那两次的现场只剩 SMAPI 的"没有 NewDay"。
- 二次修正的时钟：`timeOfDay` 1200（第一次 before）→1610（第一次 after/day_start）→1610（第二次 before/after）。第一个 180 s 窗口内时钟走了 410 分钟（≈全速的 16%），第二个窗口**一分钟都没走**。⇒ 第二个窗口里世界明显被"某个模态/暂停"卡住；`worldSeq` 却从 352 涨到 377（24→25 次）。**这一对（时钟停、seq 涨）是"有东西开着但不推进日子"的强提示，但具体是什么，见 §6 未定项 U2。**

### 2.3 Mod 侧源码（`mod\AgentFarm.Bridge\SleepSkill.cs`，运行时部署 0.7.21，日志文本与源码逐字一致）
- `Step()`（:111-153）：首 tick `FireSleepRequest()` 后 `return null`；之后只在 `dayNow > _dayBefore` 时 `Ok(Elapsed())`；`elapsed > _timeoutMs` 时 `Fail("timeout", "已发起睡觉（{_trigger}）但 {elapsed}ms 内日期没有前进（发起时第 {_dayBefore} 天，现在第 {dayNow} 天）；当前诊断：{Diagnose()}…")`。**180 s = 调用方传的 `timeout_ms=180000`**（探针与 journal 都一致；`ClampBudget` 只把它夹在 [5000,300000] 内）。
- `FireSleepRequest()`（:159-185）：① `TryAnswerOpenQuestion()`；② 失败则 `key = BuildSleepAnswerKey()` → `delivered = TryAnswerDialogueAction(key, out fallbackNote)` → **无条件** `_monitor.Log($"sleep：{_trigger}（{fallbackNote}）")`（这一行**不看 delivered**），`if (!delivered) Log(Warn, "sleep：应答没有送回游戏…")`。
- `TryAnswerDialogueAction()`（:247-263）：`loc = Game1.currentLocation; if (loc == null) { note="当前地点为空"; return false; } loc.answerDialogueAction(key, null); note="已交给游戏自己的 answerDialogueAction（它会走 startSleep → doSleep → Game1.NewDay）"; return true;`（catch ⇒ note="answerDialogueAction 异常：…"、false）
  ⇒ **L1213/L1221 打印的就是这句 note**，证明：`Game1.currentLocation` 非空、调用正常返回、无异常。但**"函数返回"≠"startSleep 执行了"** —— 这正是本次故障的盲区。
- `TryAnswerOpenQuestion()`（:195-222）：`Game1.activeClickableMenu as DialogueBox == null ⇒ false`；`!isQuestion || responses==null || Length==0 ⇒ false`；`FindAffirmativeIndex` 找不到肯定项（tokens `{"yes","yeah","sure","ok","是","好","确定"}`，先 responseKey 后 responseText，**刻意不兜底取第一项**）⇒ false
  ⇒ **两次 FAIL 时"睡觉提问"这个 DialogueBox 根本没开着**（否则会走 ① 分支，日志文本会不同）⇒ **`interact(bed)` 没有把提问打开**，这一条是已定的。
- `BuildSleepAnswerKey()`（:232-245）：`Game1.currentLocation?.lastQuestionKey` 非空则取首个空格前 head + `"_Yes"`；**读不到/为空则直接 `"Sleep_Yes"`** ⇒ 三次日志都是 `Sleep_Yes` 无法区分"提问开着"与"读不到"。
- `Diagnose()`（:304-321）：已经会打印 `isInBed` / `Game1.newDay` / `Game1.pauseTime` / `activeClickableMenu` 类型名 / `Game1.dialogueUp` / `player.CanMove` / `Game1.gameMode` / `timeOfDay` / `newDaySync.readyForSave()` / `hasSaved()` —— **这是现成的、能一次回答本问题的现场快照，但它只出现在 timeout reason 里，而 brain 把它丢了**（见 §4 R1）。

### 2.4 IL 定案（游戏 1.6.15，`Stardew Valley.dll`；转储见 `scratch\il-sleep-ada.txt`、`logs\il-newday-u8.txt`、`logs\il-sleep-entry-u8.txt`、`logs\il-sleep-callers-u8.txt`）
1. **`GameLocation.answerDialogueAction(String questionAndAnswer, String[] questionParams)`**（`scratch\il-sleep-ada.txt:2` 起，4373 行）：字符串 switch 里 **`IL_0ABC: ldstr "Sleep_Yes"` → `IL_0AC1: call String.op_Equality` → `IL_0AC6: brtrue -> IL_30D5`**，而 **`IL_30D5: ldarg.0` / `IL_30D6: call Void startSleep()` / `IL_30DB: br -> IL_3976`**。`questionParams`（arg.2）在 switch 之前完全没被解引用 ⇒ 传 `null` 安全。**该分支没有任何 `isInBed`/`dialogueUp` 之类的前置判据。**
2. **`GameLocation.startSleep()`**（`scratch\il-sleep-ada.txt:4164`；方法体亦见 `logs\il-sleepflow-u8.txt`）：`IL_0000-IL_000F: Game1.player.timeWentToBed.Value = Game1.timeOfDay;`（无条件）→ `IL_0014: if (Game1.IsMultiplayer)` ⇒ `netReady.SetLocalReady("sleep", true)`、`Game1.dialogueUp = false`、`Game1.activeClickableMenu = new ReadyCheckDialog("sleep", true, <startSleep>b__437_0, <startSleep>b__437_1)`；**否则 `IL_006E: this.doSleep()`**。之后只剩多人公告（`GoneToBed`/`globalChatInfoMessage`）。**无 isInBed 判据。**
3. `FIND|startSleep`（`logs\il-sleep-entry-u8.txt:1-3`）：`startSleep` 全程序集只有 **2 个调用方** —— `GameLocation.answerDialogueAction` 与编译器生成的 `<startSleep>b__437_0`（ReadyCheckDialog 的回调）⇒ **Mod 选 `answerDialogueAction` 作为唯一外部入口是正确且唯一的**（`startSleep`/`doSleep` 都是 private）。
4. **`GameLocation.doSleep()`**：三条分支只按 `lightLevel`/`timeOfDay`(2000)/`isOutdoors` 决定是否补光+放 `"openBox"`；**每条分支都以 `if (Game1.IsMasterGame) Game1.NewDay(0f)` 收尾**；随后写 `lastSleepLocation`/`lastSleepPoint`/`mostRecentBed`、`doEmote(24)`、`freezePause = 2000`。**无 isInBed 判据，也不设置 isInBed。**
5. **`Game1.NewDay(Single timeToPause)`**（`logs\il-newday-u8.txt`，66 行）：IL_0000-IL_0029 若 `activeClickableMenu is ReadyCheckDialog r && r.checkName=="sleep" && !r.isCancelable()` 则 `r.confirm()`；**`IL_0034-IL_0035: ldc.i4.1; stsfld Boolean newDay`（`Game1.newDay = true`，无条件）**；**`IL_003A-IL_003F: ldsfld NewDaySynchronizer newDaySync; callvirt Void create()`（无条件）**；**`IL_0044` 才是 `if (player.isInBed.Value || player.passedOut)`**（补光/黑屏/`Halt`/`CanMove=false`/`pauseTime`）；`IL_00CA` 若 `activeClickableMenu != null && !dialogueUp` 则 `emergencyShutDown(); exitActiveMenu()`。
   ⇒ **`NewDay` 不早退**：一旦被调用，`newDay=true` 与 `newDaySync.create()` 必然执行，SMAPI 的 `Synchronizing 'NewDay' task...` 必然出现。**两次 FAIL 里它没出现 ⇒ `NewDay` 根本没被执行 ⇒ `doSleep()` 没执行（或没到 NewDay 调用）。**
6. **状态语义（决定分支）**：`Game1.get_IsMultiplayer()` = `otherFarmers.Count() > 0`（"会话里还有别的农夫"）；`Game1.get_IsMasterGame()` = `multiplayerMode == 0 ? true : (multiplayerMode == 2)`（0=单人、1=客户端、2=主机）。
7. **`Farmer.isInBed` 只在"临时床"分支被置 true**：`answerDialogueAction` 里 `IL_04FD: brtrue -> IL_30E0` 那一支是 **`IL_30E0: call Farmer get_player()` / `IL_30E5: ldfld NetBool isInBed` / `IL_30EA: ldc.i4.1` / `IL_30EB: callvirt Void set_Value(Boolean)`**（紧跟 `sleptInTemporaryBed = true`）。**普通床的 "Sleep_Yes"（IL_30D5）只调 `startSleep()`，游戏从不在这条路上把 `isInBed` 置 true。** ⇒ `isInBed` 是"睡过临时床"之类的*状态位*，不是"上床"这个动作的结果；**不能把 `isInBed=true` 当成普通睡觉的前置条件去追求**（PASS 探针里它是 true，只是因为那份存档读进来时人还在床上）。

### 2.5 "interact(bed)" 到底是什么（`mod\AgentFarm.Bridge\Skills.cs:170-235`）
- `interact` 的实现 = **`Game1.currentLocation.checkAction(tile, viewport, player)`**（"用一下面前那一格"）。同一入口在 `MoveToLocationSkill.cs:493-571` 被用来进建筑（真机：`checkAction((64,14))` 返回 True 后 0.6 s 人已在 `FarmHouse(3,11)`）；`UseToolSkill.cs:20` 注释也把 `checkAction` 标成"同源先例"。
- ⇒ **游戏承认的"用床"动作 = 对床格调 `GameLocation.checkAction` → （家具路径）弹出键为 `Sleep` 的提问 → 玩家选"是" → `answerDialogueAction("Sleep_Yes")` → `startSleep()` → `doSleep()` → `Game1.NewDay(0f)`。** Mod 的兜底 ② 正好跳过了前面的"提问"环节，直接假装玩家点了"是"。
- **`checkAction` 是否真的能作用到床**：`scratch\il-bed2.txt`（本次新转储，1991 行）里 `GameLocation.checkAction`（:846 起）**没有任何 `"Sleep"` 字面量、也没有 `isInBed` 引用**；`StardewValley.Objects.BedFurniture.checkForAction`（:2-423）与 `Objects.Furniture.checkForAction`（:424-845）里同样没有 `"Sleep"`/`createQuestionDialogue`。⇒ 现有转储**无法证明**"床的睡觉提问由 checkAction 打开"（也未能否证；探针的方法体归属在这几个重载上有可疑处，见 U4）。**这一条列为未定，靠 §4 R5 的最小复现探针一次就能判死。**

## 3. 为什么"调用返回正常"却没有跨日（矛盾已定位，机制未定）

按 IL，`answerDialogueAction("Sleep_Yes")` 走到 `NewDay` 是一条**没有状态前置判据**的路；而实测两次都没有任何 NewDay 工作。逻辑上只剩三种可能，每种都能**精确复现**观察到的全部指纹（无 NewDay、无异常、控制台无报错、180 s 超时、世界像是被挂起）：

| # | 机制 | 为什么能解释全部现象 | 判别方法 |
|---|---|---|---|
| **M1** | **`Game1.IsMultiplayer == true`** ⇒ `startSleep()` 走 `ReadyCheckDialog` 分支：`netReady.SetLocalReady("sleep", true)` + 打开 `ReadyCheckDialog("sleep", …)`，**`doSleep()` 根本不被调用** ⇒ 永无 NewDay；对话框挂着 ⇒ 时间暂停（第二次窗口时钟 0 分钟）；`Config` 上 `isCancelable=true`，`NewDay` 里"自动确认"那条只认 `!isCancelable` ⇒ 永远等不到 | ✅ 全部 | 呼一次 `health`/`observe` 时读 `Game1.otherFarmers.Count`/`Game1.IsMultiplayer`；或让 Mod 在 timeout reason 里附 `Diagnose()`（现成） |
| **M2** | **`Game1.IsMasterGame == false`**（`multiplayerMode==1`，客户端）⇒ `startSleep` 正常、`doSleep()` 正常，但 `doSleep` 里 `if (Game1.IsMasterGame)` 为假 ⇒ 不调 `NewDay` | ✅ 无 NewDay；时间不该暂停（与第二次窗口时钟停不符） | 读 `Game1.multiplayerMode` / `IsMasterGame` |
| **M3** | **调用的不是基类那份 `answerDialogueAction`**（运行时 `currentLocation` 的 `Farm`/`FarmHouse` 覆盖）—— 已证 `FarmHouse` 不 override，但 **`Farm.answerDialogueAction` 确实存在且有自己的方法体**（头部与基类同形，正文未 diff）⇒ 若两次调用时 `currentLocation` 其实是 `Farm`，就可能走到不一样的实现 | ⚠️ 第一次 FAIL 之前才刚 `Warping to FarmHouse`（L1204），存在"调用时 `currentLocation` 仍是 Farm/FarmHouse 过渡态"的可能 | ① diff `Farm` 版与基类版正文（`scratch\il-sleep-override-u8.txt` 已有两份）；② 在 Mod 里把 `Game1.currentLocation.NameOrUniqueName` 一起记进日志 |

**结论：三种都指向同一个可操作的判断——"发请求前必须先看当场状态"，而且都能用一行现成日志（`Diagnose()`）判死。** 在拿到那份日志之前，本报告**不把 M1/M2/M3 中的任何一个写成"已定"**。

## 4. 修复建议（按收益排序，每条给验证方式）

| # | 改哪里 | 怎么改 | 为什么收益最高 | 验证 |
|---|---|---|---|---|
| **R1** | **brain（`longrun.py` 的 `_do_sleep`/sleep 事件）** | sleep 的 journal 事件**原样带上 Mod 回执的 `code` + `reason` 全文**（现在是 `"睡觉请求失败"` 这种 brain 自造文本）；同时把 `before`/`after` 里的 `isInBed`、`activeClickableMenu`（若观测里有）、`timeOfDay` 一起落盘 | 这次取证的**唯一卡点就是现场丢失**：Mod 已经算好 `Diagnose()`，brain 把它扔了；改一行，下次直接读出 M1/M2/M3 | 重跑一天；`grep '"event":"sleep"' logs\*.jsonl` 能看到 `诊断`/`activeClickableMenu` 字样 |
| **R2** | **brain（`farmwork.sleep()` 序列）** | 在 `interact(bed)` 之后、`client.sleep()` 之前**加状态断言**：再 observe 一次，要求 `isInBed==true` **或**（提问已开：观测里能拿到 `activeClickableMenu`/`dialogueUp` 为对话）；不满足就**不要发 sleep**，而是重试"用床"（`interact` 重发一次 / 站到床格上再按），仍不满足就**以独立失败码快速失败**（例如 `sleep_precondition`），而不是等 180 s | 把"静默无效 + 180 s 空等"变成"当场可见的失败"；同时给长跑一个真实的补救动作 | 单测/探针：从农场中央直接调 `farmwork.sleep()`，应在数十秒内返回 `sleep_precondition` 而不是 180 s；从床边（提问已开）调则跨日 |
| **R3** | **Mod（`SleepSkill.cs`）** | ① 首 tick 调用后**立刻记一次 `Diagnose()` + `Game1.newDay`/`newDaySync.readyForSave()`**（TRACE 级，不只看 timeout）；② 加 5–10 s 的"早期失败"：若 `delivered==true` 但 `dayNow==_dayBefore && Game1.newDay==false && activeClickableMenu is ReadyCheckDialog` ⇒ 直接 `Fail("precondition_failed", "startSleep 进了多人 ReadyCheck 分支（IsMultiplayer=true），本局不会跨日")`；③ 把 `delivered` 的语义从"函数返回了"改成"游戏状态真的动了" | 把 180 s 的哑超时变成**秒级、可归因**的失败码；`precondition_failed` 正是 `docs\00-开发日志.md:299-309` 已定下的失败码之一 | 编译后跑最小复现探针（R5），断言失败码是 `precondition_failed` 而不是 `timeout` |
| **R4** | **runner（收尾策略）** | 保持现有的"`sleep_failed` ⇒ `day_end.verified=false` ⇒ `no_day_progress` ⇒ `finish code=1`"**不重试整天**；但允许**一次**"重新用床 + 再 sleep"（≤60 s），成功则当天照常结算 | 现有行为是**正确**的（没跨日就不该算过），缺的只是"失败前的最后补救" | 看 run3 的 `day_end.checks.slept_by_us` 与 `finish`；跨日成功必须同时有 journal 日期 +1 与 SMAPI `Synchronizing 'NewDay'` |
| **R5** | **验收/探针（`scratch\`）** | 写一个"最小复现探针"：`goto FarmHouse` → observe(记 `isInBed`/`tile`/是否开提问) → `stand_next_to(bed)` → `interact(bed)` → observe(再记一次) → `sleep(timeout=60s)` → observe(日期)。判据：**日期 +1 ∧ 进程存活 ∧ 存档 mtime 前进**；再补一个**负对照**：在农场中央直接 `sleep()`，应当失败 | 一次就能判死 §3 的 M1/M2/M3，并把"上床"这一步的效果（提问有没有开）变成可观测事实 | 探针输出必须同时含 `interact` 前后的 `isInBed`/`dialogueUp`；PASS 那次必须能看到"提问在 interact 后出现" |
| **R6** | **文档（`docs\03-桥接协议.md` 的 `use_tool`/sleep 段）** | 把"回执 ok 不算成功"这条既有纪律扩展到 sleep：**睡觉的验收只看"日期 +1 + SMAPI NewDay/Save"**，回执 `ok` 与 `reason` 都只是声明 | 与 `docs\00-开发日志.md:296`「验收必须用 `tiles[]` 差分，回执只是声明」同源，避免下一次又拿 `ok=true` 当跨日 | 文档评审 |

**不建议**的修法：`SleepSkill` 里反射调 `GameLocation.startSleep`（`:338-359` 已有 `TryReflectStartSleep`，默认关）—— 它绕过 `answerDialogueAction`，虽然 IL 上等价，但**同样躲不开 IsMultiplayer/IsMasterGame 分支**，只会把"静默无效"换成"静默无效但看起来更底层的调用"。

## 5. "验收该怎么读"（给 runner / dev 的可判定规则）

1. **跨日成功**要**同时**满足：`journal` 里日期从 `[season, d]` 变成 `d+1` **且** SMAPI 日志出现 `Synchronizing 'NewDay' task...` + `SaveGame.Save()`（或至少存档 mtime 前进）。**回执 `ok=true` 不算证据**（对照：PASS 探针三条判据全绿；FAIL 两次回执都是 `ok=false`，但**如果哪天出现 `ok=true` 而日期没变，以日期为准**）。
2. `sleep` 事件必须带 **Mod 的原始 `code`+`reason`**（R1），否则"`code=failed`"无法区分 `timeout` / `precondition_failed` / `ui_modal` / `no_save`。
3. `day_end.checks` 的四项阈值是对的，**`slept_by_us=false` ⇒ 当天不 VERIFIED**（run2 L89 就是这样，正确）；`day_justified` 只看 `ended_reason` 前缀，**不要**用它替代 `slept_by_us`。
4. `no_day_progress` + `finish code=1` 是**正确收尾**（run2 L93/L94）：跨日失败 ⇒ 长跑必须停，而不是在同一个游戏日里空转（run2 第二次 sleep 就是对"同一天再睡一次"的白等，见 L91/L92 的 `timeOfDay=1610` 两次相同）。

## 6. 未定项（诚实清单）

- **U1（核心）**：§3 的 M1/M2/M3 到底是哪一个 —— 现有证据只能证明"没进 NewDay"，不能区分"进了多人分支" / "不是主控" / "调到了别的 override"。**判别成本很低（R1/R3 一行日志）**，但在拿到之前不写成已定。
- **U2**：两次 180 s 窗口里 `worldSeq` 涨了 24→25，而 `timeOfDay` 在第二个窗口一分钟没走（1200→1610 只在第一个窗口发生）。"时钟停但世界 seq 涨"与"有模态挂着"相符，但也可能是桥的 seq 口径包含非时间字段 —— **未定**。
- **U3**：`Farm.answerDialogueAction`（有自己的方法体）与基类版正文是否等价 —— **未 diff**（`scratch\il-sleep-override-u8.txt` 两份都在，属于廉价待办）。
- **U4**：**"用床"的入口链还缺一环**：`GameLocation.checkAction` / `BedFurniture.checkForAction` 现有转储里都找不到 `"Sleep"` 字面量与 `createQuestionDialogue`（`scratch\il-bed2.txt`），所以"`interact(bed)` 应当弹出提问"目前**只有真机先例（门/建筑）+ 设计推断**，没有 IL 直证。注意：`scratch\il-bed.txt`（16846 行、`BedFurniture.*` 全量转储）**方法体与类型名对不上**（头部写 `BedFurniture`，正文却是 PrairieKing/矿车/FarmComputer 等 `Object.checkForAction` 分支），**不可引用**；`scratch\il-bed2.txt` 里 `BedFurniture.checkForAction` 与 `Furniture.checkForAction` 两段也要先确认不是同一份重复体（探针在继承方法上的归属待复核）。→ 交给 R5 的探针直接观测。
- **U5**：run1 的 21:59:59 崩溃（`soft_oal.dll`、`0xc0000409`，崩溃前最后一条日志是 21:56:00 的 `sleep`）与 run1 的 journal 在 `t=71.29` 后停止是否同一件事 —— SMAPI 的 21:5x 段未读，**未定**。
- **U6**：`Game1.otherFarmers` 为何会非空（M1 的前提）—— 全 SMAPI 日志无 multiplayer/farmhand/disconnect 相关行，**未定**；若 M1 成立，需要查"这份存档是不是 co-op 存档 / 是否曾以 host 模式启动"。

## 7. 复核命令（只读，可重放）

```powershell
# 1) SMAPI 三段现场
$log = "$env:APPDATA\StardewValley\ErrorLogs\SMAPI-latest.txt"
Select-String -Path $log -Pattern "Synchronizing|before save|after save|sleep：|1800\d+ms" | Select-Object LineNumber,Line
# 2) journal 的两天结局
Select-String -Path logs\longrun-3day-llm-run2.jsonl -Pattern '"event":"sleep"|"event":"day_end"|no_day_progress|"event":"finish"' | Select-Object LineNumber,Line
# 3) 对照探针（PASS 现场）
Get-Content logs\probe-sleep-run2.txt
# 4) IL 关键三条（本报告引用的行号）
Select-String -Path scratch\il-sleep-ada.txt -Pattern "IL_0ABC|IL_30D5|IL_30E0|IL_30E5|IL_30EB"
Select-String -Path logs\il-newday-u8.txt   -Pattern "IL_0034|IL_003A|IL_0044|ReadyCheck|Sleep"
Select-String -Path logs\il-sleep-entry-u8.txt -Pattern "startSleep"
```

## 8. 一句话总评

**Mod 的睡觉代码没错，"叫醒游戏"的方式也没错；错在这条链上没有任何一步去确认"人到底在不在床上、提问到底开没开"，而游戏对"不在状态"的睡觉请求既不报错也不跨日 —— 于是系统只能白等 180 s，再把一整天判成失败。** 最高收益的修复不是改睡觉逻辑，而是**先让失败现场可见（R1/R3），再让 brain 在发请求前验证状态（R2）**。
