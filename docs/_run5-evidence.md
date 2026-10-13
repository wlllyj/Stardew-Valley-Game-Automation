# run5 真机验收证据（task-45）

> **状态（本文件会随取证推进更新）**：**run5 已结束（未达标；按 Lead m00987 定性为"取证跑"）** —— 账本 `logs\longrun-3day-llm-run5.jsonl` **531 行** / 241692 B / mtime **20:32:41.447**；`finish` = `{"event":"finish","t":1543.42,"code":1,"verified_streak":0,"actions":522,"minutes":25.72,"stages_seen":["clear_area","plant_area","till_area","water_area"],"no_unmet_stages":false,"unmet_days":["1年 spring 26日"]}`；PID **22608** 已消失，`logs\run5-console.err.log` 全程 **0 B**（`logs\run5.pid` 内容仍是 22608）。
> 起跑时刻 **2026-10-13 20:06:57.748**，Mod **0.7.24**（装机 dll 169472 B / manifest 17316 B），被测脑侧 HEAD **242315a5da4002ecba1fe39240b2cf0ac9e2a3e8**；起跑前 task-43（长路径寻路 13.4s ok）与 task-42（出货 + 次日结算 +100g）**均通过**，见第 1 部分。
> run5 共 6 个日报告（实际跨日 5 次），逐日见第 2 部分，外部证据/判据对照/结论见第 3/4 部分。
> 收工处置：20:37:37 按 Lead m01045 **关掉那个空 `LevelUpMenu`**（`professionsToChoose:[]`；一次 `dismiss_modal` → `SaveGameMenu` 只等不关 → 3s 后菜单消失 → 10.1s 时 `worldAdvancing=true`），并在**同一秒补齐了被推迟的落盘**（`3696701 B / 20:37:37.898`）；随后按用户 m02833 政策 `tools\stop-game.py` **优雅退出**（20:37:54 `Disconnected: ClosedGame`、`bridge.json` 已删、进程 0、无崩溃）。详见 §1.4 末条与 §4.3。
> 本文件由 `machine-runner` 独占写入；所有读数均为**观测/文件/进程**取证，Mod 回执只作声明不作证据。

---

## 第 0 部分 环境纪律与版本口径

### 0.1 纪律（本次执行遵守）

- 长动作一律**脱离式**起跑：`Start-Process -PassThru -RedirectStandardOutput/Error -WindowStyle Hidden`，PID 落 `logs\run5.pid`，之后只用「PID 存活 + 文件内容」轮询，**不用托管后台作业**（run4 第一次起跑就是被回合边界 teardown 静默杀掉的，探针实验见 `logs\_jobreap-probe.txt`）。
- 单写者：run5 期间只有本进程驱动游戏桥；期间**不改源码、不 deploy、不 `load_save`、不替游戏做选择**。
- **不写** `day_end.final.location == "Farm"`（Lead 已更正：`final` 是睡前快照，正常一天要"走回 FarmHouse → 上床"，成功的一天 `location` 本就是 `FarmHouse`）。改用：`ended_reason` 以 `no_work` 开头的日子**必须** `final_water.dry == 0`。
- 跑完**先不退游戏**（Lead 要做 live observe 对账后才决定）；退游戏只在没有作业且按用户 m02833 政策执行时进行。

### 0.2 版本四要素

| 项 | 读数 | 记录时刻 |
|---|---|---|
| `git rev-parse HEAD` | `242315a5da4002ecba1fe39240b2cf0ac9e2a3e8` | 20:06:5x |
| `git status --short` | ` M scratch/_t44_falsify.py`、` M scratch/_t44_probe.py`、`?? docs/_review-e818195.md`、`?? scratch/{run5-dismiss-modal,run5-smapi-counts,run5-state,tail}.py`（**被测源码无 ` M`**） | 20:06:5x |
| 装机 `AgentFarm.Bridge.dll` | size **169472** B，mtime **2026-10-13 20:00:37.037**（`manifest.json` 17316 B / 20:00:35.316） | 20:06:5x |
| 桥 `health()` | `modVersion = 0.7.24`、`port = 17890`、游戏 PID **26016** | 20:02:18 |
| `brain\agentfarm\longrun.py` | SHA256 **8024851052D0B9C31651BE2A2A455AE4878404D5448ABF6C0B84D9BB0ACDC64B**、mtime **19:53:58.212** | 20:06:5x |
| run5 进程 `StartTime` | **2026-10-13 20:06:57.748** | 起跑时 |

**结论：`StartTime`（20:06:57.748）晚于 `longrun.py` mtime（19:53:58.212）⇒ 本进程加载的就是冻结版（0.7.24 对应的脑侧提交），不需要重启。**

---

## 第 1 部分 起跑前：睡到干净早晨 + task-43 + task-42

### 1.1 起点状态与 preflight

- 起点存档（20:02:18）：`C:\Users\admin\AppData\Roaming\StardewValley\Saves\Wahaha_450799035\Wahaha_450799035` = **3623151** B / mtime 2026-10-13 **19:32:46.399**（= run4 结束时的档，游戏日 `spring 24`）。
- 桥已由 Lead 用 `tools\deploy-mod.py --no-quit` 拉起并 `load_save` 进 `Wahaha_450799035`，落点 FarmHouse (9,9)。
- `python tools\preflight.py --expect 0.7.24`（**不加** `--save-baseline`，避免覆盖 Lead 的基线）⇒ **exit 1**：`✅ 装机 0.7.24`、`✅ 已读档`、`❌ 在户外农场`（当时人刚读完档在床上；`tillableCount 0`、`tileCount 1`）⇒ 属**预期**不满足，需要先走到户外农场（run-longrun 的 `[prep]` 本来也会做 `goto_farm`）。
- 残留 `logs\run4.pid`（18660）已删除，避免与本次混淆。

### 1.2 task-43 真机验收 = **PASS**（run4 唯一硬卡点）

背景：run4 里从 `Farm(64,15)` 走回 `FarmHouse` **稳定 8000ms 超时**（`warp 源格 (64,14) 超时…剩余 5x 步未走完`）。Lead 复现结论 = `mod\AgentFarm.Bridge\MoveToLocationSkill.cs:83 HopTimeoutMs=8000` 是**与路径长度无关的跳预算**（真实路径 ≈88 步，被草/石/枝/树绕 3 倍），0.7.24 改成按真实步数放大。

| 步骤 | 结果 |
|---|---|
| `python -m agentfarm goto Farm` | **7647ms ok**：FarmHouse(9,9) → Farm(64,15)，hop1 `source=[3,12]` 7611ms |
| 站 (64,15) 直接 `goto FarmHouse` | **822ms ok**：hop1 `Farm → FarmHouse result=ok source=[64,14] landing=[3,11] used=[64,15]` |
| `goto Farm` | 5933ms ok |
| `move 47 29 --timeout-ms 30000 --no-focus` | **13311ms ok**（seq 20→81）⇒ 站到远角 (47,29) |
| **从 (47,29) `goto FarmHouse`** | **13367ms ok**：hop1 `Farm → FarmHouse result=ok source=[64,14] landing=[3,11] used=[64,15]`，exit 0 |

⇒ **13.4s，落在验收带 20–30s 内**（且远早于 30s 上限）；短距 822ms 的对照说明改的是**跳预算**，不是门口几何。

### 1.3 task-42 出货链验收 = **PASS**（含次日结算）

探针：`python scratch\verify-sell-brain.py --expect-version 0.7.24`（**显式白名单** `['(O)535']`，脚本自己打印"脚本白名单=✅"；脑侧 `sell` 默认只卖 `self.harvested`，手工跑不传白名单会"一件不卖"）。

| 项 | 出货前 | 出货后（游戏内） | 次日跨日后 |
|---|---|---|---|
| 背包目标 slot | slot 5 `Geode (O)535` stack **2** | stack **0**（qid 总数 2→0） | — |
| 出货箱 | 0 件 | **2 件** | 已结算清空 |
| `money` | **14g** | 14g（结算要等 `NewDay`） | **114g = +100g** |

- 回执原文：`已出货槽位 5 的 (O)535（背包 2→0，出货箱 1 件）；钱要等下一次 NewDay 才由游戏结算（当前 14g）`。
- **负例**（非 Object 不可卖）：slot 0 `Axe / (T)Axe` ⇒ `ok=False code=failed`、`reason=出货没有生效…Mod status=not_sellable`、回执 `not_sellable: …（Axe）不是 Object（Axe）⇒ 出货箱结算只累加 Object，非 Object 计 0 钱`。
- **结算口径核对**：`money` 增量 **+100g == `sellToStorePrice(-1) × stack` = 50 × 2** ⇒ 与游戏结算一致（钱由游戏加，脑没加）。探针总耗时 **2.5s**，脚本判 `✅ VERIFIED：出货差分成立、钱的结算口径正确、负例被拒`。
- **跨日链（`day_after` 与外部证据）**：
  - `spring 24 → spring 25`：`scratch\verify-sleep-brain.py --from-farm` 判 **VERIFIED**（`day` +1、`timeOfDay` 回 600、体力回 270、存档前进：主文件 3623151 → **3658556** B / mtime **20:03:44.986**；SMAPI `Context: before save.` → `SaveGame.Save() called.` → `completed without exceptions.` → `after save, starting spring 25 Y1`）。
  - `spring 25 → spring 26`：**`sleep` 跨日成功（`day` +1、`money` 结算 +100g）** ＋ **保存被当日早晨的出货日终菜单推迟（`NewDay` task 完成，当时没有 `SaveGame.Save()` 调用）** —— 两条并列，后者**不是 sleep 的问题**（task-47 口径见 `docs\_il-newday-save.md`，详见 1.4）。`scratch\verify-sleep-brain.py` 判 `needs_review` 只是它的工具判据（要求存档 size/mtime 前进）在这种日子上**过严**。
- **钱的完整链（本文件重点证据）**：`14g`（起点）→ 卖 2 件 Geode → **114g**（游戏次日结算 +100）→ run5 首日脑自己买种子 `买到 5 个 472（钱 114→14）` ⇒ 卖货收入**真的进了经济闭环**，不再是"有钱花不掉"。

### 1.4 跨日 2 的存档缺口：**保存被出货日终菜单推迟**（task-47 口径；`ShippingMenu` 只是同场出现的框）

- 现象（`spring 26` 开局，20:04:30）：`ui = {activeMenu:"ShippingMenu", isModal:true, eventUp:false, onScreenMenus:4, dialogueResponses:[], dialogueIsQuestion:false, activeMenuText:"ShippingMenu"}`、`game = {paused:false, shouldTimePass:false}`、`liveness = {worldAdvancing:false, secondsSinceClockMoved:74.152}`、`player.canMove=true`。⇒ **不是 `eventUp` 事件、不是提问**，是普通晨间结算框。
- 处置（按 Lead m00873 授权"按老规矩 dismiss"）：`python scratch\run5-dismiss-modal.py` ⇒ 回执 `{'ok':True,'status':'ok','skill':'dismiss_modal','reason':'已关闭模态（ShippingMenu）："ShippingMenu"','worldSeqBefore':179,'worldSeqAfter':179,'uiOpened':False,'worldResumed':True}`；关后 `activeMenu=None`、`isModal=false`、`worldAdvancing=true`（`secondsSinceClockMoved=0.855`）。
- **存档缺口的证据链（Lead 逐行读 SMAPI）**：
  - 第一次跨日（20:03:43）**齐全**：`Synchronizing 'NewDay' task...` → `Context: before save.` → `SaveGame.Save() called.` → `SaveGame.Save() completed without exceptions.` → `Context: after save, starting spring 25 Y1.`（**L1077 / L1080 / L1081 / L1085 / L1086**）。
  - 第二次跨日（20:04:29，**L1435**）：`Synchronizing 'NewDay' task...` → `task complete.` 之后**既没有 `Context: before save.`，也没有 `SaveGame.Save() called.`**（Lead 查到 20:05:45 都没有）⇒ 按 task-47 口径：**保存被出货日终菜单（`ShippingMenu`）推迟、关框后仍未落盘（原因未定）**——不是 sleep 失败、不是落盘滞后；落盘唯一通道是"日终菜单栈为空时被创建出来的 `SaveGameMenu`"，日终菜单在栈上时保存**按设计推迟**（`docs\_il-newday-save.md` §0 / §1 / §3）。此前我写的"是游戏自己跳过了保存"一句已按该口径更正；我的 `dismiss_modal` 发生在更晚的 ~20:05:5x。
  - 我 20:06:43 的复核与之一致：SMAPI `Synchronizing 'NewDay' task` = **2** 次而 `SaveGame.Save() called` 只有 **1** 次、`after save, starting` = 1；磁盘仍是 `3658556 B / 20:03:44.986`（`spring 25` 那一档），游戏内已是 `spring 26 tod 710 money 114`。
- 归因与跟进：**`sleep` 跨日成功（`day` +1 / `money` 结算）与"游戏当日跳过落盘"是两条并列事实**；后者的调用条件由 **task-47**（log-analyst 只读取证"日切保存的调用条件"）负责。脑侧 modal 守卫 `brain\agentfarm\longrun.py:1867` 的 `MODAL_WAIT_ONLY` 只把 `SaveGameMenu`/`NewDaySavingMenu` 当作"只能等"，其余（含 `ShippingMenu`）走 `_dismiss_modal_once`（`longrun.py:1808`）—— 但这次缺口在关框**之前**就存在了，不能归给关框。
- 对判据的影响：外部证据里的"存档 size/mtime 应前进"在**有出货的次日早晨**可能不成立；解释时必须先看"那一天是否有出货"，不能一律当失败，也不能一律当成功。run5 里只有脑自己出货才会触发（本次它已买种子，若有收成出货，次日早晨大概率复现）——如实记录。
- 附注：SMAPI 里 `ERROR` 1 条 = `[20:01:28 ERROR game] Oops! Steam achievements won't work because Steam isn't loaded…`，与本次无关。
- **后续真机确认（同一机制，`LevelUpMenu` 版；20:37:37）**：run5 第 5 次跨日（`summer 2 → summer 3`，20:32:34 **L6637** 只有 `Synchronizing 'NewDay' task...`）同样缺 save；收工时 `ui.activeMenu="LevelUpMenu"`（`professionsToChoose:[]`）把时钟卡住（§4.3）。按 Lead m01045 关掉这一次日终菜单后，SMAPI **同一秒**出现完整落盘链：`L6946` observe → `L6947` `POST /v1/exec`（`dismiss_modal`）→ **`L6948` `Context: before save.` → `L6950` `SaveGame.Save() called.` → `L6951` `Synchronizing 'Save' task...` → `L6952` `Saving without compression...` → `L6954` `completed without exceptions.` → `L6955` `Context: after save, starting summer 3 Y1.`**；存档随即前进：`Wahaha_450799035` **3696701 B / 20:37:37.898**、`_old` = `3747788 / 20:22:58.840`（`summer 2` 那一档）⇒ **与 task-47 的 IL 链条同向**："关掉日终菜单 → 早晨例程再来一遍 → 栈空 → 新建 `SaveGameMenu` → 落盘"。因此 §1.4 的缺口**不是"游戏永久跳过保存"，而是菜单链没走完**；有日终菜单而存档未动 ⇒ 按 `docs\_run6-criteria.md` §2 **既不判失败也不判通过**。

### 1.5 起跑现场与基线

- `goto Farm` 7619ms ok（到 Farm [64,15]）⇒ `python tools\preflight.py --expect 0.7.24 --save-baseline logs\run5-baseline.json` ⇒ **exit 0「✅ 可以起跑」**。
- 基线 `logs\run5-baseline.json`（Lead 侧 20:04:30 版本与我 20:06:00 版本一致）：`day=[1,"spring",26]`、`timeOfDay≈610`、`location=Farm[64,15]`、`worldSeq=179`、`stamina 270/270`、**`money=114`**、`isInBed=false`、`seeds=[]`、`crops=32`、`unwateredCrops=3`、`dryCrops=32`、`waterLeft=2`、`tillableCount=145`、`tileCount=400`、`tilesTruncated=true`、`activeMenu=null`、`isModal=false`、`worldAdvancing=true`。
- 起跑命令（脱离式，`logs\run5.pid` = 22608）：
  ```
  Start-Process -FilePath <python> -ArgumentList '-u','tools\run-longrun.py','--days','3','--size','5',
    '--max-minutes','150','--max-days','9','--journal','logs\longrun-3day-llm-run5.jsonl'
    -PassThru -RedirectStandardOutput 'logs\run5-console.log' -RedirectStandardError 'logs\run5-console.err.log' -WindowStyle Hidden
  ```
- 90 秒读数：存活 True、`logs\run5-console.err.log` **0 B**、`logs\run5-console.log` 9 行、账本 **23 行 / 20:08:26**。
  ```
  [prep] Mod 0.7.24 就绪；Farm [64, 15]；体力 270 钱 114g 作物 29（未浇 29）种子 []
  [day] 1年 spring 26日 开始：Farm 体力 270 钱 114g 作物 29（未浇 29）天气 debris
    · 补种子：买到 5 个 472（钱 114→14）
    · 作业区 field_ne 锚点 [57, 18]（25 格）
    · 校验取消 clear_area：本片看得见却没有可动目标
    · 作业区 field_nw 锚点 [41, 21]（25 格）
  ```

### 1.6 逐帧 warp 活锁的计数（外部证据，指向 task-14）

- 本窗口 SMAPI 里 `Warping to Farm` 共 **1565** 次，集中在两段：`20:03:58–20:04:02`（**299 行**）与 `20:05:54–20:05:59`（**≈300 行**）⇒ **每次 `goto Farm` 都复现**（≈每帧一次）。这就是 task-14 的"逐帧 warp 活锁"；run4 被阻断的流浪宠物剧情事件，就是它反复把 `checkForEvents` 勾出来触发的。
- 现场纪律（task-41）：run5 期间若 `eventUp` 再被勾出来（`ui.eventUp==true`，或出现 `DialogueBox` 且 `dialogueIsQuestion`），**立刻收手上报 Lead，绝不 `dismiss`、绝不替游戏做选择**。

### 1.7 对账用的外部快照（deputy 三源对账器的输入）

- `scratch\run5-external-snapshots.jsonl`：`tag:"start"` 行已写（**补写于 20:12:48**：SMAPI 累计计数按时间戳 `<=20:06:57` **精确回溯** = `smapi_lines 1769 / smapi_newday 2 / smapi_save 3`；存档字段用当时实测值覆盖 = `save_main 3658556 / 20:03:44.986`、`save_info 25825`；`pid 22608 / pid_alive true`；`journal_lines 0`；`written_at` 与 `note` 说明它是补写）。收工后写 `tag:"end"` 行：`python scratch\run5-snapshot.py --tag end`（字段与 `scratch\run4-external-snapshots.jsonl` 一致）。
- 收工后立刻冻结 SMAPI：`Copy-Item $env:APPDATA\StardewValley\ErrorLogs\SMAPI-latest.txt logs\run5-smapi-window.txt`（`SMAPI-latest.txt` 会在下次启动被覆盖，事后不可补）。

---

## 第 2 部分 run5 逐日结果（6 个日报告：5 天 `sleep` 跨日 + 1 天 `blocked_modal`）

### 2.1 第 1 天（`spring 26` → `spring 27`）：`ended_by=sleep`、**`verified=False`**

| 项 | 读数 |
|---|---|
| 日报告 | 账本 `#87`，`t=304.88`（约 5.1 分钟） |
| `ended_by` / `ended_reason` | `sleep` / `no_work:确实找不到可做的活（地里的活干完了、也没法/没必要买种子）` |
| `verified` | **False** |
| `day_after` | `[1, "spring", 27]` ⇒ **恰 +1 ✅** |
| `checks` | `slept_by_us=true`、`no_blocking_modal=true`、`day_justified=true`、`crops_watered=true`；**`no_hard_failures=false`**、**`no_unmet_stages=false`**、**`watered_outdoor=false`** |
| 步数 | `ok_steps=109`、`skipped_steps=0`、`failed_steps=4` |
| `final_water` | `scope="farm"`、`crops=37`、**`dry=1`**（`final` 快照：`location="Farm"`、`tod=1400`、窗口口径 `crops=7`、`unwatered_crops=0`） |

- **判据③ 直接命中**：这一天 `ended_reason` 以 `no_work` 开头，而 `final_water.dry = 1 ≠ 0` ⇒ **地里还剩 1 株干作物却宣布"没活可干"**（run3 那个病的最小残留形态）⇒ 按验收口径这天**必须判失败**，不能因为 `day_justified=true` 就算过。
- **4 个失败步（`blocked` 记录原文要点）**：全在 `field_nw` 的 `[38,20] / [38,19] / [37,20] / [37,19]`，动作 `till`，`no_effect=true`、Mod `status=tool_ineffective`、原因"锄完不是 dirt（kind=未知）"，体力被白烧 `140→126→114→102`（4 × ≈12）⇒ **对这几格锄地完全无效**（`no_hard_failures=false` 就是它）。
- 阶段级 `needs_review`（4 条 `outcome`）：`water_area` 两段"还剩 1 格"（做成 29+1）、`till_area` 一段"还剩 21 格"、`water_area` 一段"目标 0 步"。
- 决策与事件：决策 **24** 条（`llm` 7 / `deterministic` 17，`truncated=0`，`fallback` 空）；意图分布 `water_area 14 / clear_area 13 / till_area 5 / plant_area 5 / review 1`；点名事件 `buy 1`（5 个 472，钱 114→14）、`refill 2`、`goto_farm 1`、`plots_capped 1`、`stage_exhausted 1`、`stage_no_target 1`、`plot_exhausted 1`、`stage_midway_leftover 1`；**0 次** `no_day_progress` / `bridge_down` / `modal_timeout` / `modal_dismissed` / `event_blocked` / `watchdog_stop` / `levelup_*`。
- 该日存档外部证据见第 3 部分（与 `tag:"end"` 快照做差）。

### 2.2 第 2 天（`spring 27` → `spring 28`）：`ended_by=sleep`、**`verified=False`**

| 项 | 读数 |
|---|---|
| 日报告 | 账本 `#116`，`t=436.31`（距第 1 天 131 秒） |
| `ended_by` / `ended_reason` | `sleep` / `no_work:确实找不到可做的活（地里的活干完了、也没法/没必要买种子）`（**游戏内才 `tod 820`（13:40）就收工**） |
| `verified` | **False** |
| `day_after` | `[1, "spring", 28]` ⇒ **恰 +1 ✅** |
| `checks` | `slept_by_us=true`、`no_blocking_modal=true`、`day_justified=true`、`no_hard_failures=true`、`no_unmet_stages=true`、`crops_watered=true`；**唯一不过 = `watered_outdoor=false`** |
| 步数 | `ok_steps=44`、`skipped_steps=0`、`failed_steps=0` |
| `final_water` | `scope="farm"`、`crops=36`、**`dry=1`**（`final`：`Farm`、`tod=820`、窗口口径 `crops=6`） |

- **判据③ 再次命中**：`no_work` 收工而 `final_water.dry = 1 ≠ 0`。
- **这一天的落盘是齐全的（外部证据）**：SMAPI `20:14:12 Synchronizing 'NewDay' task...` → `Context: before save.` → `SaveGame.Save() called.` → `Saving without compression...` → `SaveGame.Save() completed without exceptions.` → `20:14:14 Context: after save, starting spring 28 Y1.`；存档主文件 **3665473 B / 20:14:12.533**、`SaveGameInfo` 25167 / 20:14:12.535，上一档（`spring 27`）在 `Wahaha_450799035_old` = **3687165 B / 20:12:01.002**。
- 第 1 天的落盘同样齐全：`20:12:00 Synchronizing 'NewDay' task...` → `Context: before save.` → `SaveGame.Save() called.` → `20:12:02 Context: after save, starting spring 27 Y1.`，文件 3687165 / 20:12:01.002 ⇒ **两次跨日都真的落盘了**（对比 §1.4 那次"游戏跳过保存"是特例，不是常态）。
- 阶段级：本次 `ok=44 / failed=0`（第 1 天是 `109/4`）；`blocked` 仍只有第 1 天那 4 条 `till` 无效格（`[38,20]/[38,19]/[37,20]/[37,19]`，`tool_ineffective`）。

### 2.3 第 3 天（`spring 28` → `summer 1`，跨季）：`ended_by=sleep`、**`verified=False`**

| 项 | 读数 |
|---|---|
| 日报告 | 账本 `#145`，`t=557.74` |
| `ended_by` / `ended_reason` | `sleep` / `no_work:确实找不到可做的活（地里的活干完了、也没法/没必要买种子）`（游戏内 `tod 810`） |
| `verified` | **False** |
| `day_after` | `[1, "summer", 1]` ⇒ **恰 +1 ✅（跨季也 +1）** |
| `checks` | `slept_by_us=true`、`no_blocking_modal=true`、`day_justified=true`、`no_hard_failures=true`、`no_unmet_stages=true`、`crops_watered=true`；**唯一不过 = `watered_outdoor=false`** |
| 步数 | `ok_steps=39`、`skipped_steps=0`、`failed_steps=0` |
| `final_water` | `scope="farm"`、`crops=36`、**`dry=1`**（`final`：`Farm`、`tod=810`、窗口口径 `crops=6`、`waterLeft=16`） |

- **判据③ 第三次命中**：`no_work` 收工而 `final_water.dry = 1 ≠ 0`；与第 2 天完全同型（`water_area 28/28 + 1/1 + 5/5 + 1/1`，`clear_area` 各 2 格）。
- 落盘齐全：`20:16:13 Synchronizing 'NewDay' task...` → `Context: before save.` → `SaveGame.Save() called.` → `20:16:15 Context: after save, starting summer 1 Y1.`（L3814/3817/3818/3823）；存档 **3793288 B / 20:16:14.028**。

### 2.4 第 4 天（`summer 1` → `summer 2`）：`watered_outdoor` 首次转 **true**，但 8 格清障失败

| 项 | 读数 |
|---|---|
| 日报告 | 账本 `#298`，`t=962.68` |
| `ended_by` / `ended_reason` | `sleep` / `no_work:…`（游戏内 `tod 1440`） |
| `verified` | **False** |
| `day_after` | `[1, "summer", 2]` ⇒ **恰 +1 ✅** |
| `checks` | `slept_by_us=true`、`no_blocking_modal=true`、`day_justified=true`、`no_unmet_stages=true`、`crops_watered=true`、**`watered_outdoor=true`（首次）**；**唯一不过 = `no_hard_failures=false`** |
| 步数 | `ok_steps=124`、`skipped_steps=0`、`failed_steps=8` |
| `final_water` | `scope="farm"`、`crops=36`、**`dry=0`（33/36 格全部浇上，农场口径归零）**（`final`：`Farm`、`tod=1440`、`waterLeft=20`） |

- **8 个失败步全是 `clear` + `no_effect=true` + `reason="四邻都站不过去"`**，时间戳 `t=809.5`：`[71,34] [71,35] [71,36] [74,34] [72,37] [75,35] [75,37]`（7 格）+ `t=917.59` `[47,22]`（1 格）；阶段级表现为 `clear_area 10/3ok/7fail`、`clear_area 7/6ok/1fail` ⇒ 客观不可达，不是循环坏了（task-52 已立：`unreachable` 单独分类）。
- 落盘齐全：`20:22:58 Synchronizing 'NewDay' task...` → `Context: before save.` → `SaveGame.Save() called.` → `20:23:00 Context: after save, starting summer 2 Y1.`（L5121/5124/5125/5130）；存档 **3747788 B / 20:22:58.840**。

### 2.5 第 5 天（`summer 2` → `summer 3`）：18 格清障失败；**当日落盘被游戏跳过**

| 项 | 读数 |
|---|---|
| 日报告 | 账本 `#525`，`t=1536.71` |
| `ended_by` / `ended_reason` | `sleep` / `no_work:…`（游戏内 `tod 1830`） |
| `verified` | **False** |
| `day_after` | `[1, "summer", 3]` ⇒ **恰 +1 ✅** |
| `checks` | `no_hard_failures=false`（18 格清障失败）；`watered_outdoor=true`、`final_water.dry=0` |
| 步数 | `ok_steps=147`、`skipped_steps=0`、`failed_steps=18` |
| `final_water` | `scope="farm"`、`crops=35`、`dry=0`（`final`：`Farm`、`tod=1830`、`waterLeft=23`） |

- 18 个失败步同样是 `clear` + `四邻都站不过去`：`[70,35] [71,35]`、`[73,41]`、`[71,53] [72,53] [68,56]`、`[30,52] [28,53] [28,54] [30,56] [28,55] [28,56]`、`[16,34] [15,35] [14,35] [14,34] [13,35]`、`[17,21]`。
- **落盘缺口（第二次出现，与 §1.4 同型）**：SMAPI 里 `20:32:34 Synchronizing 'NewDay' task...`（**L6637**）之后**没有** `Context: before save.`，也**没有** `SaveGame.Save() called.` ⇒ 游戏自己跳过了当日保存；磁盘上最新一档仍是 `summer 2`（3747788 / 20:22:58.840）。**这不是 sleep 失败**（`sleep` 回执 ok、`day_after` 已 +1）。

### 2.6 第 6 天（`summer 3`）：晨间剧情对话 ⇒ **`blocked_modal` 停下等人（未跨日）**

- `#529 t=1543.42 ended_by=blocked_modal`、`verified=False`、**`day_after=None`**、`ok_steps=0`。
- `ended_reason`：`关不掉模态 DialogueBox：[world_stuck] (HTTP 200) 已关闭对话（非提问对话框，无需应答closeDialogue() 关闭（复位 dialogueUp 与 player.CanMove））："There was an earthquake during the night."；警告：模态已关闭（或本就没有模态），但游戏仍处于不可控状态（canMove=False，isPlayerFree=True），世界没有恢复…需要外部恢复`
- 账本 `modal_blocked` 记录 `#528`：`{"menu":"DialogueBox","note":"不可逆/不敢关的模态 ⇒ 当天不判 VERIFIED，等人工处理"}`。
- `day_end.notes` 三条：① `回不去 Farm：去 Farm 失败：[ui_modal] 移动过程中被菜单/对话打断，已停止移动（当前 FarmHouse，目标 Farm）`；② `被模态挡住，停下等人：关不掉模态 DialogueBox…`；③ `浇水证据不足/未浇完`。
- ⇒ **行为符合 task-41**：`eventUp`/剧情类模态**不替游戏做选择**、不自动关，停下并把当天判为非 VERIFIED。`final`：`FarmHouse [3,11]`、`tod 600`、`farm crops=35 / dryCrops=35`。

## 第 3 部分 外部证据与三源对账

run5 运行窗口：**20:06:57.748（起跑）→ 20:32:41.447（账本 mtime，finish t=1543.42）**，约 **25.7 分钟**。

### 3.1 SMAPI 冻结窗口

- `Copy-Item $env:APPDATA\StardewValley\ErrorLogs\SMAPI-latest.txt logs\run5-smapi-window.txt` ⇒ **456658 B / 6938 行 / mtime 20:32:41.455**（源文件同尺寸；冻结发生在 finish 之后，未再被覆盖）。
- 窗口内 `Synchronizing 'NewDay' task...` 共 **7** 次、`SaveGame.Save() called.` 共 **5** 次（含起跑前 20:03:43 / 20:04:29 两次跨日，见 §1.4）。
- **run5 的 5 次跨日逐条**（行号取自冻结窗口）：

| 跨日 | SMAPI 行号 | 落盘 | 存档 |
|---|---|---|---|
| `20:12:00` → spring 27 | L2571 / L2574 / L2575 / L2580 | ✅ | 3687165 B / 20:12:01.002 |
| `20:14:12` → spring 28 | L3204 / L3207 / L3208 / L3213 | ✅ | 3665473 B / 20:14:12.533 |
| `20:16:13` → summer 1 | L3814 / L3817 / L3818 / L3823 | ✅ | 3793288 B / 20:16:14.028 |
| `20:22:58` → summer 2 | L5121 / L5124 / L5125 / L5130 | ✅ | 3747788 B / 20:22:58.840 |
| `20:32:34` → summer 3 | **L6637**（只有 `Synchronizing 'NewDay' task...`） | **❌ 跳过** | 无新档 |

⇒ **5 次跨日 = 5 次 `sleep` 成功**，与账本 5 条 `sleep ok` 一一对应；其中第 5 次**游戏自己跳过了 `SaveGame.Save()`**（与 §1.4 同型，第 2 次出现）。

### 3.2 存档读数（收工时）

| 文件 | size | mtime |
|---|---|---|
| `Wahaha_450799035` | **3747788** | **2026-10-13 20:22:58.840** |
| `SaveGameInfo` | 25330 | 20:22:58.842 |
| `Wahaha_450799035_old` | 3793288 | 20:16:14.028 |
| `SaveGameInfo_old` | 25081 | 20:16:14.031 |

⇒ 磁盘上最后成功落盘的是 **`summer 2` 开局**（20:22:58）；`summer 3` 那天的进度**没有落盘**（游戏跳过，非 sleep 失败）。

### 3.3 start/end 外部快照与增量（`scratch\run5-external-snapshots.jsonl`，2 行）

| 字段 | start 行（**补写于 20:12:48**，SMAPI 计数按 `<=20:06:57` 精确回溯） | end 行（20:34:03，按 `<=20:32:45` 过滤） | 窗口增量 |
|---|---|---|---|
| `smapi_lines` | 1769 | 6936 | **+5167** |
| `smapi_newday` | 2 | 7 | **+5（= 5 次跨日，正好）** |
| `smapi_save` | 3 | 11 | **+8**（5 次跨日 + 3 次其他保存） |
| `save_main` | 3658556 / 20:03:44.986（`overridden`） | **3747788 / 20:22:58.840** | — |
| `save_info` | 25825 | 25330 | — |
| `journal_lines` | 95（写入时刻的实时值；`journal_lines_at_start=0`） | **531** | **+436** |
| `journal_finish` | `null` | `t=1543.42 code=1` | — |
| `pid` / `pid_alive` | 22608 / true | 22608 / **false** | — |

- 注：start 行的 `journal_lines` 是该行**写入时刻**（20:12:48）的实时行数，不是起跑时刻的值；起跑时刻以 `journal_lines_at_start=0` 为准，表内"窗口增量"用 end − 起跑（0）口径也对得上（531 = 全程）。
- `logs\run5.pid` 内容仍是 **22608**；`logs\run5-console.err.log` **0 B**（20:06:57.746 创建后从未写入）；`logs\run5-console.log` 17989 B / 20:32:41.464。
- 说明：Lead 指定的 `python scratch\_run4_snapshot.py --tag end` 是 **run4 的**快照脚本（按 run4 账本取值、写 `scratch\run4-external-snapshots.jsonl`，报的是 run4 的 128 行 / `t=320.65`），因此 run5 的 end 行**另由** `python scratch\run5-snapshot.py --tag end` 写入；run4 那一行也已落盘。

### 3.4 `tools\verify-run3.py` 闸门（独立复核）

`python tools\verify-run3.py --journal logs\longrun-3day-llm-run5.jsonl --days 3` ⇒ **exit 1**，结论 **`needs_review`**：

- 逐日表与第 2 部分一致（6 行）；`decision 114 条（其中 LLM 33 条）`；**"尾部连续 VERIFIED 天数 0 / 要求 3"**。
- 问题清单（原文要点）：`spring 26` 四条（`watered_outdoor=false`、`no_hard_failures=false`、当天 stages 硬失败 4 格、`no_unmet_stages=false`）+ 三天（`spring 26/27/28`）各一条 `ended_reason 以 no_work 开头，但 final_water.dry=1 ⇒ run3 连睡病复发`；`summer 1/2` 各两条（`no_hard_failures=false` + 硬失败格数）；`summer 3` 两条（`ended_by=blocked_modal`、`watered_outdoor=false`）。
- 信息级提示：多天 `water_area`/`clear_area` 当天有多轮记录（更早一轮 leftover>0、最后一轮 0），闸门按日级口径取最后一轮并显式列出遮蔽。

### 3.5 `clock` 对齐（观测而非回执）

- 6 条 `day_start`：`spring 26`（`Farm`、`tod 730`、crops 29）、`spring 27/28`、`summer 1/2/3`（`FarmHouse`、`tod 600`、crops 0、`stamina 270`、`money 14`）。
- 5 条 `sleep` 回执与 5 次 `day_after` 逐一对齐：`spring 26→27`、`27→28`、`28→summer 1`、`summer 1→2`、`summer 2→3`；`summer 3`（第 6 个日报告）**没有跨日**（`day_after=null`），与之对应的正是 `blocked_modal`。

## 第 4 部分 判据对照、结论与诚实声明

### 4.1 判据对照（task-45 §4 五条）

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| 1 | 尾部连续 **3** 天 `ended_by=="sleep"` 且 `verified==true` 且 `day_after` 恰 +1 | **未达标（0/3）** | 6 个日报告全 `verified=false`；5 次 `sleep` 都跨日成功（+1），但没有一天 `verified=true` |
| 2 | **不**使用 `final.location=="Farm"` | **遵守** | 全文未采用该判据（改用 `no_work` ⇒ `final_water.dry==0`） |
| 3 | `ended_reason` 以 `no_work` 开头的日子必须 `final_water.dry == 0` | **失败（3 天命中）** | `spring 26/27/28` 各 `dry=1`（`crops=37/36/36`）⇒ 按 run3 口径判失败；`summer 1/2` `dry=0` 通过 |
| 4 | 0 次 `bridge_down`/`modal_timeout`/`watchdog_stop`/`no_day_progress`/`event_blocked`，无崩溃 | **通过** | 上述事件计数全 **0**；`modal_blocked` 1 次属 task-41 的"正确停下"；`err.log` 0 B；无原生崩溃 |
| 5 | 外部证据同向（存档前进 + SMAPI `NewDay`/`SaveGame.Save` 行号 + `clock` 对齐） | **按 run6 新口径重述** | 5 次跨日、7 次 `Synchronizing 'NewDay'`（含起跑前 2 次）；**4 次当场落盘**；第 5 次（`summer 2→3`，20:32:34）**当天早晨有日终菜单**（随后观测到 `LevelUpMenu`、`professionsToChoose:[]`）⇒ 按 `docs\_run6-criteria.md` §2 与 `docs\_il-newday-save.md`：**有日终菜单而存档未动＝设计性推迟，既不判失败也不判通过**；收工清掉该菜单后 save 立即补齐（§1.4 末条：L6948–L6955、3696701 B / 20:37:37.898）；`clock`/`day_after` 链完全对齐 |

⇒ **验收结论：`needs_review`（`verify-run3.py` exit 1，`finish.code=1`，`verified_streak=0`）—— 未达标。** 按 Lead m00987 的定性，本次作为**取证跑**收口，不再追加新判据。

### 4.2 这次跑"证明了什么 / 暴露了什么"

**在长跑里被证明可用的**：
- task-43：长路径寻路（`goto FarmHouse` 13.4s，run4 曾稳定 8000ms 超时）；run5 中 5 次 `goto_farm` 全部成功。
- task-42：经济闭环在长跑里真的转了 —— 脑自己 `buy 1`（5 个 472，钱 114→14），`refill 5` 全部成功（`waterLeft 0 → 40`）。
- 户外浇水链路：`summer 1` / `summer 2` 两天 `final_water.dry = 0`（33/36、35 格全浇上）⇒ **"户外还有干作物"这件事本身是能被做干净的**，spring 三天残留的 `dry=1` 因此更像**计量口径**问题而不是"浇不上"。
- 睡觉链路：5/5 `sleep ok`、5/5 `day_after` 恰 +1，含一次跨季（`spring 28 → summer 1`）。

**暴露的四类问题（已由 Lead 立卡）**：
1. **枯死作物被 `farm.dryCrops` 计成"干"** ⇒ `spring 26/27/28` 恒剩 `dry=1`（Lead 的 `scratch/_lead_crop_audit.py` 审计：窗口内 24 格作物里 23 格 `dead=True`；`farm.deadCrops` 字段 Mod 还没暴露）—— task-50/51。
2. **不可达格清障被当硬失败** ⇒ `summer 1` 8 格、`summer 2` 18 格 `clear` + `四邻都站不过去`，把 `no_hard_failures` 打 false（客观不可达，不是循环坏了）—— task-52（`unreachable` 单独分类、有界、防洗白）。
3. **`till` 在非 dirt 格 `tool_ineffective` 白烧体力** ⇒ `spring 26` 的 `[38,20]/[38,19]/[37,20]/[37,19]` 4 格，体力 140→102（4×≈12）。
4. **日切保存会被游戏跳过**（§1.4 + §3.1 第 5 次跨日）⇒ 外部证据"存档必须前进"不能无条件当判据 —— task-47。

### 4.3 收工时的 live 状态（只读 observe 一次，20:34）

- 游戏 **PID 26016 存活**（StartTime 20:01:14），`bridge.json` 存在（207 B / 20:33:30）⇒ **游戏未退**（按 Lead 要求）。
- `ui = {"activeMenu":"LevelUpMenu","isModal":true,"eventUp":false,"professionsToChoose":[],"activeMenuText":"LevelUpMenu"}`、`liveness = {"worldAdvancing":false,"secondsSinceClockMoved":91.262}` ⇒ **被一个"空的 LevelUpMenu"卡住（时钟不走）**。
- `player`：`FarmHouse [9,9]`、`isInBed=false`、`clock 1/summer/3 tod 600`、体力 270/270、`money 14`、`waterLeft 23/40`；`farm`：`crops 35 / dryCrops 35 / unwateredCrops 35 / hoeDirt 95 / complete true / scanSeq 2770`（新的一天，尚未浇水）。
- **处置结果（Lead m01045 授权后执行，20:37:37）**：before = `activeMenu="LevelUpMenu"` / `isModal=true` / `professionsToChoose:[]` / `onScreenMenus:4` / `worldSeq=2770` / `secondsSinceClockMoved=303.002`；判据满足（`LevelUpMenu` 且职业列表为空）⇒ `dismiss_modal` **一次**（`elapsedMs:0`、`worldResumed:true`）⇒ 关后 `activeMenu` 立刻变 **`SaveGameMenu`** ⇒ 按规则**只等不关**（间隔 2.5s 轮询）⇒ **3 秒后菜单消失**、**10.1 秒时 `worldAdvancing=true`（`clock 600→610`、`worldSeq 2770→2771`）** ⇒ **清干净、世界恢复**（脚本 `scratch\run5-levelup-clear.py` exit 0，日志 `logs\run5-levelup-clear.log`）。全过程**没有连关、没有 `load_save`、没有重启、没有替游戏选**。
- **清场即触发落盘**：`dismiss` 同一秒 SMAPI 出现完整 save 链（L6948–L6955），存档写成 **`3696701 B / 20:37:37.898`**（`summer 3` 那一档）⇒ task-47 机制的又一次真机确认（§1.4 末条）。
- **按用户 m02833 政策优雅退出**：`python tools\stop-game.py` ⇒ 回执 `ok — 已置 Game1.quit=true…`、`✅ 游戏已退出（原 pids=[26016]）`（exit 0）；退出后复核：`StardewModdingAPI` 进程 **0**、`bridge.json` **已删除**、17890 无 LISTENING、存档四条读数不变（`Wahaha_450799035` 3696701 / 20:37:37.898、`SaveGameInfo` 26578 / 20:37:37.899、`_old` 3747788 / 20:22:58.840、`SaveGameInfo_old` 25330 / 20:22:58.842）；SMAPI 尾 `L6962 20:37:54 Disconnected: ClosedGame` → `Disposing...` → `L6964 已删除发现文件 …\bridge.json`；**无崩溃**（无 Event 1000/1001）。至此待命：不改源码、不 deploy、不 `load_save`、不起跑。

### 4.4 保留物（不删）

`logs\longrun-3day-llm-run5.jsonl`（531 行）、`logs\run5-console.log`、`logs\run5-console.err.log`（0 B）、`logs\run5-smapi-window.txt`（冻结窗口，截止 20:32:45）、`logs\run5-levelup-clear.log`（20:37:37 清场日志）、`logs\run5.pid`、`logs\run5-baseline.json`、`logs\run5-journal-summary.txt`、`logs\run5-observe-*.json`、`scratch\run5-external-snapshots.jsonl`、`scratch\run5-*.py`。
- 注意：`logs\run5-smapi-window.txt` 冻结在 **finish（20:32:45）**，因此**清场/落盘/优雅退出**的证据（`L6946`–`L6965`）只在源日志 `C:\Users\admin\AppData\Roaming\StardewValley\ErrorLogs\SMAPI-latest.txt`（**6960 行**）里；引用这些行号时须写明来源是源日志。

### 4.5 诚实声明

- 本次 run5 由 `machine-runner` 单写者驱动：**没改任何源码、没 deploy、没 `load_save`、没替游戏做任何选择**；对游戏的调用只有 `observe`（只读）、`dismiss_modal`（§1.4 的 `ShippingMenu`，Lead 授权）与长跑自身。
- 所有结论以**观测/文件/进程**读数为准，Mod 回执只作声明；`ui`/`clock`/存档 mtime/size/SMAPI 行号均为原始读数。
- 未做推测性结论的地方都标了"待 task-XX"；`summer 3` 的 `blocked_modal` 与 live 的 `LevelUpMenu` 都**留给人工裁定**。
