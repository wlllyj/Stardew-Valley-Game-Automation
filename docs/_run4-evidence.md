# run4 取证：3 游戏日真机长跑（Mod 0.7.23，"睡醒在屋里"已由 `cc2988e` 修掉）

**当前状态：run4 已结束 · 失败**（`verified_streak 0/3`、**0 次跨日**、exit code 1）。起跑 2026-10-13 **19:33:37**（PID **18660**，脱离式 `Start-Process`，被测版本 **`a302d61` / task-41**），结束 **19:38:58**（账本 128 行，进程已退出）。

本文档把**这一次**记为 **RUN-4（有效）= FAIL**；在此之前那次只跑了 13 秒、死于 harness 托管作业 teardown 的起跑**不计成绩**（§0.6）；更早那次被剧情事件阻断的起跑**从未起跑**（第 0 部分）。

结论只有两条：① **田区作业全绿**（浇水 + 清障共 **89 个 ok / 0 failed / 0 skipped / 0 env_block / 0 inconclusive**）；② **`Farm → FarmHouse` 长距离接近门那一跳 8s 超时** ⇒ 两次 `sleep_failed`、**跨日从未发生**、`day_justified=false`。

---

## 第 0 部分：起跑前被剧情事件阻断（未起跑）

### 0.1 起跑前现场与前置（Lead 完成的前置，我不重复）

- `git log --oneline -1` = **`cc2988e`**「run3 真 bug 修复：睡醒在屋里也要先回农场（`_ensure_on_farm` 日首接线 + `_farm_scope_work` 让 `work_reasons`/`sleep_guard` 用 farm 口径判'还有活'）+ MorningIndoor 两条用例与变异验证（321 OK）」；我的写范围内工作树干净（只有 `?? docs/_run3-evidence.md` 与 `?? scratch/*.py`）。
- 桥：`modVersion=0.7.23`、`hasSaveLoaded=true`；raw `bridge.json` 的 `pid` 键 = **26344**，`load_bridge_info().pid` = **26344**（pid 双向取证再次一致；`BridgeFileAudit.recognized` 含 `pid`）。
- Lead 的 `python tools\preflight.py --expect 0.7.23 --save-baseline logs\run4-baseline.json` ⇒ **exit 0「✅ 可以起跑」**。基线要点：`day [1,spring,23] tod 650 **rain**`、`location Farm`、`playerTile [64,15]`、体力 270/270、钱 **14g**、`isInBed false`、种子 **[]**、`farmingLevel 0`、`crops 32 / unwateredCrops 14 / **dryCrops 0**`、`farmComplete true`、`waterLeft **2**`、`tillableCount 157`、`tileCount 400`、`tilesTruncated true`、无模态、`worldAdvancing true`。
- 存档未被本次事件改写：`Wahaha_450799035` = **3579973** / mtime **19:10:26.913**（`_old` 3543468 / 19:10:23.367）。

### 0.2 时间线（全部来自 SMAPI 行号 / bridge 回执 / 我的实时观测）

| 时刻 | 事实 | 来源 |
|---|---|---|
| 19:15:59 | `deploy-mod.py --no-quit` 起游戏（新 `bridge.json`：pid 26344、modVersion 0.7.23、`startedAt 2026-10-13T12:15:59+00:00`） | bridge.json / SMAPI L16 |
| 19:16:04 | `Context: loaded save 'Wahaha_450799035', starting spring 23 Y1, locale set to . Single-player.` | SMAPI L87 |
| 19:16:47–19:16:48 | `python -m agentfarm goto Farm`：`POST /v1/exec → 200 · 7662ms · worldSeq=15`，期间 **连续 ~370 行 `TRACE game] Warping to Farm`（≈每帧一次，2 秒内）** | SMAPI L361–L413 |
| 19:16:49 | 你的 preflight（`GET /v1/health` + `GET /v1/observe`）—— 当时 **exit 0、无模态** | SMAPI L415–L416 |
| 19:17:52 | 我起跑前取证（`scratch\run4-start.py`）：`ui={activeMenu:"DialogueBox", isModal:true, **eventUp:true**, activeMenuText:"Hello Jay!", dialogueIsQuestion:false, dialogueResponses:[]}`、`player.canMove=false`、`game.shouldTimePass=false`、`worldAdvancing=false`、clock `spring 23 tod650 rain`、`Farm [64,15]` 体力 270 钱 14 `waterLeft 2`、`farm crops 32 / unwatered 14 / dry 0`；full 快照落 `logs\run4-observe-start.json`（113008 bytes） | 我的脚本输出 |
| 19:17:52 | 我的独立 preflight ⇒ **exit 1「❌ 状态不满足，不要起跑」**：三项 ✅，`无阻断模态（ui.isModal==false）` **❌ —— activeMenu='DialogueBox'**；`⚠️ worldAdvancing=false` | 预检输出 |
| 19:18:55 | 复测：**一模一样**（`secondsSinceClockMoved=135.1`），即 75 秒零推进 | 我的脚本输出 |
| ≈19:19:0x | 按 Lead 授权 **(A)** 连续关框 5 次（护栏：出现提问/选项即停、最多 5 次）—— 详见 0.3 | `logs\run4-unblock.jsonl` |
| 19:20:5x | Lead 观测到台词已变为 `"I found it sitting outside the entrance to your farm! I think it's a stray... poor little thing."` ⇒ 事件性质定性为 **SDV 1.6 流浪宠物领养剧情**（后续会出现 Yes/No 收养选择） | **Lead 的观测（不是我）** |
| 19:21:0x | 那张带流浪宠物台词的快照是 **Lead 取的**（`GET /v1/observe` 两行属 Lead，不是我） | **Lead** |

### 0.3 逐次关框读数（Lead 授权 (A)，最多 5 次；全程未出现提问/选项）

关框前快照：`activeMenu='DialogueBox' text='Hello Jay!' eventUp=True isModal=True q=False resp=[] canMove=False worldAdvancing=False secsSince=234.145 clock=spring 23 tod650 rain Farm[64,15] 体力270 钱14`

| 第几次 | `dismiss_modal` 回执（节选，原文） | 关完 `activeMenu` | `eventUp` | `isModal` | `canMove` | `worldAdvancing` | `secsSinceClockMoved` |
|---|---|---|---|---|---|---|---|
| 1 | `[world_stuck] (HTTP 200) 已关闭对话（非提问对话框，无需应答closeDialogue() 关闭（复位 dialogueUp 与 player.CanMove））："Hello Jay!"；警告：模态已关闭（或本就没有模态），但游戏仍处于不可控状态（canMove=False，isPlayerFree=False），世界没有恢复（CanMove=false 会让 shouldTimePass=false，时钟随之停止推进），需要外部恢复（建议重启游戏）` | **None**（框真的没了） | True | True | False | False | 234.244 |
| 2 | `当前没有打开的模态，无需关闭` + 同一条 `world_stuck` 警告 | None | True | True | False | False | 234.312 |
| 3 | 同上 | None | True | True | False | False | 234.381 |
| 4 | 同上 | None | True | True | False | False | 234.493 |
| 5 | 同上 | None | True | True | False | False | 234.585 |

- 5 次里 `activeMenuText` **始终是 `Hello Jay!`**（我从未观测到流浪宠物那段文本）；`dialogueIsQuestion=false`、`dialogueResponses=[]` **全程成立**（护栏没被踩到）；**框没有回来**（不是"关掉又来"）。
- 第 1 次之后 `activeMenu=None`，但 `eventUp=true` 且游戏每帧把 `player.CanMove` 压回 false ⇒ `shouldTimePass=false` ⇒ 时钟彻底不走；Mod 自己报"需要外部恢复（建议重启游戏）"。
- 终态：`modVersion 0.7.23` ✅ / `hasSaveLoaded` ✅ / `isOutdoorFarm` ✅ / **`isModal==false` ❌** / **`worldAdvancing` ❌** ⇒ 仍不可起跑（脚本 exit 3，`dismiss 次数=5`）。
- **时间边界（Lead 已复核）**：`logs\run4-unblock.jsonl` 5 行的 `secsSinceClockMoved` = 234.145 → 234.585，与我所述一致；**19:19:0x 之后我零调用**（没 dismiss / 没 load_save / 没 sleep / 没重启 / 没 observe / 没写文件）。

### 0.4 处置结论与责任归因（含一处自我更正）

1. 我先前的读法"事件脚本自己卡死"**下早了，撤回**。正确读法：**那个框不是死锁，是"等下一句"**——`closeDialogue()` 让事件把它算作"这句说完了"，于是事件在随后（19:20:5x）推进到第二句。
2. 因此：**推进发生在 19:19:0x 我停手之后，但触发这次推进的原因是我第 1 次关框** ⇒ 这句跳过算在我头上（不追责，取证价值高）。
3. 两条对后续有用的结构性结论：
   - **(1) task-41 必做**：`eventUp=true` 时 `ui.isModal` 已是 `true` 而 `activeMenu` 可以是 `null` ⇒ 长跑"看到模态却无框可关"，`_clear_modals` 会空转或误判，必须改成**硬停上报**，绝不能 auto-dismiss（对剧情事件就是替游戏做决定）。
   - **(2) task-14 升级**：逐帧 warp 循环（**普通 `python -m agentfarm goto Farm` 即可复现**，370 行/2 秒）会反复触碰 `checkForEvents`，把存档里真实存在的剧情事件**勾出来**，从而直接阻断无人值守 —— 这不只是性能问题。
4. 事件性质：**SDV 1.6 流浪宠物领养剧情**，后续会出现 `Yes/No` 收养选择，**不可逆（收养 ⇒ 存档永久多一只宠物）** ⇒ 绝不代选；用户表态前游戏冻结。

### 0.5 记录与文件边界

- 本次我写的文件：`logs\run4-unblock.jsonl`（5 行逐次读数）、`logs\run4-observe-blocked.json`（被阻断那次的 full 快照，113008 bytes，19:17:52）、`scratch\run4-start.py`、`scratch\run4-unblock.py`，以及本文档 —— 前四者写于 Lead 的"冻结"指令**之前**；冻结期间只写了本文档。
- 明确未做：未起 run4（`logs\longrun-3day-llm-run4.jsonl` 不存在）、未 `load_save`、未 `sleep`、未重启、未改源码、未 deploy、未替游戏做任何选择。

### 0.6 第一次起跑被回合边界 teardown（只跑了 13 秒）

第一次起跑用的是**托管后台作业**（`run_in_background: true`，无 tee、无重定向），19:25:35 起。

| 项 | 读数 |
|---|---|
| 死账本（已改名保留） | `logs\longrun-3day-llm-run4-aborted-teardown.jsonl`，**14 行 / 4211 B / mtime 19:25:48.099** |
| 末条记录 | `intent_verdict`（t=12.85，`clear_area keep targets=1`）；**无 `day_end`、无 `finish`** |
| 作业记录 | `job_list` → `(no background jobs)`；`job_output pwsh-406` → `Error: unknown job pwsh-406` ⇒ **整条 job 记录消失**（对照：run2 的 `pwsh-236`、退出的 `pwsh-291`、run3 的 `pwsh-306` 跑完记录都在且能读 stdout 与 `EXIT=`）⇒ **无 Traceback 可贴** |
| 磁盘缓冲 | 无 `logs\run4-console*`；本次无新 `dsh-spill-*`（最新 17:58）；会话缓存 `285b3720-….json` 里 `pwsh-406` 只出现 1 次、`Traceback`/`run-longrun`/`EXIT=` 命中 0；`session.v4.jsonl.zstd` 1.9MB 压缩且本机无解码器（python 3.12.14 无 `zstandard`、PATH 无 `zstd`、app.asar 打包）⇒ **stdout 不可恢复** |
| 桥侧 | SMAPI 19:25 窗口全部 200、无 ERROR/超时/掉线；最后一条 `[19:25:51] POST /v1/exec → 200 · 3122ms · worldSeq=60`（请求 ≈19:25:47.9 发出，响应送达时请求方已消失） |
| OS 原生崩溃 | Windows Application **Id 1000/1001 在 19:20–19:35 无匹配**；python 进程 0 |

**对照实验（决定性）**：另起一个托管后台作业，每 5 秒往 `logs\_jobreap-probe.txt` 追加一拍，全程不碰游戏/桥：

```
probe start 2026-10-13T19:31:09.559+07:00 pid=25260
beat 1  19:31:09.576
beat 2  19:31:14.604
beat 3  19:31:19.619
```

我的回合在 ≈19:31:20 结束；19:31:52 复核该文件仍只有这 4 行、**无 beat 4、无 `probe end`** ⇒ **托管后台作业在回合边界被连带收掉**（与上表"job 记录整条消失"自洽）。

**结论**：第一次 run4 死于 **harness 托管作业的回合边界 teardown**，**不是 brain/Mod 的 bug**，也**不能**当作 run4 的成绩；跨回合的一切进程必须**脱离式**起跑。原账本**不删不覆盖**，改名保留为 `logs\longrun-3day-llm-run4-aborted-teardown.jsonl`。

---

## 第 1 部分：正式起跑（被测版本 = `a302d61` / task-41）

### 1.1 版本口径四要素（回答"进程 import 的是哪份代码"）

| # | 项 | 读数 |
|---|---|---|
| 1 | `git rev-parse HEAD` | `a302d619a970d679c9cb28c4aa3b3a90ba82bcc6`（`a302d61`） |
| 1 | `git status --short` | ` M docs/_run3-evidence.md`、`?? docs/_review-cc2988e.md`、`?? docs/_run4-evidence.md`、`?? scratch/*.py`（**被测源码上没有 ` M`**） |
| 2 | `brain\agentfarm\longrun.py` SHA256 | `E154312E2049F9981A573612DE7287B997C90716094402365564D3D252F89BDB`（与 task-41 冻结版一致） |
| 2 | 同上 mtime | `2026-10-13T19:28:55.773` |
| 3 | `Get-Process -Id (Get-Content logs\run4.pid) \| Select StartTime` | **2026-10-13T19:33:37.520**（PID **18660**） |
| 4 | **结论** | `StartTime`(19:33:37) **晚于** `longrun.py` mtime(19:28:55) ⇒ **进程 import 的就是 task-41 冻结版 ✅ 有资格** |

### 1.2 起跑前状态（睡到干净早晨 → 落户外 → preflight exit 0）

- `python scratch\verify-sleep-brain.py --from-farm` ⇒ **VERIFIED**：睡前 `day [1,spring,23] tod 1750 Farm[67,32] 体力 268/270 isInBed False`、存档（主文件 + SaveGameInfo 合计）**3605134 B / 19:10:26** → 睡后 `day [1,spring,24] tod 600 FarmHouse[9,9] 体力 270/270 isInBed True`、存档 **3649072 B / 19:32:46**；耗时 **11.9s**；回执原文 `已跨日：spring 23日 → spring 24日（体力 268 → 270）；已踩触发格 (10, 9)`。⇒ 三项外部证据齐（`day` +1、存档 size+mtime 前进、`tod` 回 600 且体力恢复）。
- 随后 `preflight`（人在床上）⇒ **exit 1**，唯一不过项 = `❌ 在户外农场（location.isOutdoorFarm）`（基线 `spring 24 tod 620 FarmHouse`、`crops 32 / unwatered 3 / dryCrops 32`、`waterLeft 2`、`tillableCount 0`、`tileCount 1`、无模态、`worldAdvancing true`）。
- **我补了一步，两次读数都留档**：`python -m agentfarm goto Farm` ⇒ `FarmHouse(9,9) → Farm(64,15)`、`hop1 result=ok source=[3,12] landing=[64,15] 7632ms`、`worldSeq 150→160`；**流浪宠物事件没有再次触发**、无模态。
- 再跑 `python tools\preflight.py --expect 0.7.23 --save-baseline logs\run4-baseline.json` ⇒ **exit 0「✅ 可以起跑」**：`spring 24 tod 640 Farm [64,15]`、`crops 32 / unwatered 3 / dryCrops 32`、`waterLeft 2`、`tillableCount 152`、`tileCount 400`、`tilesTruncated true`、无模态、`worldAdvancing true`。（本次 preflight 覆盖了 0.1 里那份"被剧情事件阻断时"的 `logs\run4-baseline.json`；阻断期读数以 0.1/0.2 为准。）

### 1.3 起跑方式与监控（脱离式，避免再次 teardown）

```powershell
$p = Start-Process -FilePath <python> -ArgumentList '-u','tools\run-longrun.py','--days','3','--size','5','--max-minutes','150','--max-days','9','--journal','logs\longrun-3day-llm-run4.jsonl' -WorkingDirectory <repo> -RedirectStandardOutput logs\run4-console.log -RedirectStandardError logs\run4-console.err.log -WindowStyle Hidden -PassThru
$p.Id | Set-Content logs\run4.pid      # -> 18660
```

- 起跑后 75 秒读数（19:34:52）：PID 18660 **存活**、`logs\run4-console.err.log` **空**、console 正常增长（`[prep] Mod 0.7.23 就绪；Farm [64,15]；体力 270 钱 14g 作物 29（未浇 29）种子 []` → `[day] 1年 spring 24日 开始：Farm 体力 270 钱 14g 作物 29（未浇 29）天气 sunny` → `作业区 field_se 锚点 [70,25]（25 格）` …）、账本 **12 行**（mtime 19:34:36）。
- 监控口径：只读轮询 `Get-Process -Id (Get-Content logs\run4.pid)` / console 尾 20 行 / 账本行数与尾行；**不再使用 `job_output`**（托管作业管不到脱离式进程）；出现 `finish` 或 PID 消失 ⇒ 立刻报 Lead；**跑完先不退游戏**（Lead 要先做一次 live observe 对账）。

### 1.4 运行结果（账本原文，128 行）

起跑 19:33:37 → 结束 **19:38:58**（进程 18660 已退出；`logs\run4-console.err.log` 全程 **0 B**）。事件计数：
`day_start 2 / day_end 2 / sleep 2 / decision 28 / intent_verdict 28 / outcome 29 / plot 20 / policy 6 / review 2 / refill 1 / plot_walk 1 / plot_exhausted 1 / plots_capped 1 / stage_no_target 1 / stage_exhausted 1 / stage_midway_leftover 1 / **no_day_progress 1** / finish 1`。
（精炼取证落 `logs\run4-journal-extract.txt`，脚本 `scratch\run4-dayend.py`、`scratch\run4-extract.py`。）

**`finish` 原文**
```json
{"event":"finish","t":320.65,"code":1,"verified_streak":0,"actions":95,"minutes":5.34,
 "stages_seen":["clear_area","plant_area","water_area"],"no_unmet_stages":false,
 "unmet_days":["1年 spring 24日"]}
```

**两个 `day_start` 原文（同一天 `spring 24`）**
```json
{"event":"day_start","t":0.08,   "day":[1,"spring",24],"timeOfDay":650, "stamina":270,       "money":14,"crops":29,"unwatered":29,"location":"Farm","weather":"sunny"}
{"event":"day_start","t":204.48, "day":[1,"spring",24],"timeOfDay":1130,"stamina":180.50003, "money":14,"crops":4, "unwatered":0, "location":"Farm","weather":"sunny"}
```
⇒ 两次都从 `Farm` 开始、**日期完全没变** ⇒ **跨日 0 次**。

**两个 `day_end` 关键字段**

| # | t | day | ended_by | verified | `day_after` | `checks` |
|---|---|---|---|---|---|---|
| 55 | 204.46 | `[1,spring,24]` | `sleep_failed` | **false** | **null** | `{"slept_by_us":false,"no_blocking_modal":true,"no_hard_failures":true,"no_unmet_stages":false,"crops_watered":true,"watered_outdoor":false,"day_justified":false}` |
| 125 | 320.65 | `[1,spring,24]` | `sleep_failed` | **false** | **null** | `{"slept_by_us":false,"no_blocking_modal":true,"no_hard_failures":true,"no_unmet_stages":true,"crops_watered":true,"watered_outdoor":false,"day_justified":false}` |

**`ended_reason` 原文（两次同因）**
```
回不了 FarmHouse：去 FarmHouse 失败：[timeout] (HTTP 200) 第 1 跳失败（timeout）：走向 Farm → FarmHouse 的 warp 源格 (64,14) 超时（单跳预算 8000ms 或整体剩余时间用尽）。本跳试过的格子：walking:(64,15)(door_push)=started；(64,15)(door_push)=timeout[move_to_location 第 1 跳（Farm → FarmHouse） 超时（8000ms，剩余 58 步未走完），已停止寻路]；(63,14)(door_push)=unreachable[寻路无法到达 (63,14)（A* 未算出路径，目标可…
```
（第 2 次同文，仅"剩余 **51** 步未走完"不同。）

**`final` / `final_water` 原文**
```json
#55  final={"day":[1,"spring",24],"timeOfDay":1120,"location":"Farm","tile":[47,29],"stamina":180.50003,"money":14,"isInBed":false,
            "crops":2,"unwatered_crops":0,"ripe":0,"tillable":200,"waterLeft":12,"seeds":[],"counts_scope":"window",
            "farm":{"loaded":true,"complete":true,"crops":32,"dryCrops":2,"unwateredCrops":3,"hoeDirt":98}}
     final_water={"t":204.463,"location":"Farm","tiles":98,"crops":32,"dry":2,"scope":"farm","note":"farm 口径：dry 来自 farm.dryCrops…farm.unwateredCrops=3 不是干格数、不参与判定"}
#125 final={"day":[1,"spring",24],"timeOfDay":1400,"location":"Farm","tile":[26,23],"stamina":158.70004,"money":14,"isInBed":false,
            "crops":2,"unwatered_crops":0,"ripe":0,"tillable":200,"waterLeft":10,"seeds":[],"counts_scope":"window",
            "farm":{"loaded":true,"complete":true,"crops":33,"dryCrops":1,"unwateredCrops":4,"hoeDirt":103}}
     final_water={"t":320.645,"location":"Farm","tiles":103,"crops":33,"dry":1,"scope":"farm","note":"…farm.unwateredCrops=4 不是干格数、不参与判定"}
```

**田区作业成绩（`stages` 按 stage 汇总，`ok_steps`/`failed_steps` 来自 `day_end`）**

| day_end | `ok_steps` | `skipped_steps` | `failed_steps` | `water_area` | `clear_area` | `plant_area` |
|---|---|---|---|---|---|---|
| #55 | **58** | 0 | **0** | tiles 30 / **ok 30** / failed 0 / leftover 2 | tiles 28 / **ok 28** / failed 0 / leftover 2 | — |
| #125 | **31** | 0 | **0** | tiles 1 / **ok 1** / failed 0 | tiles 29 / **ok 29** / failed 0 | tiles 2 / ok 1 / **`stopped:"no_seed"`** |

- 合计 **89 ok / 0 failed / 0 skipped / 0 failed_any / 0 env_block / 0 inconclusive / 0 proven_inert** ⇒ 田区作业干净（`no_hard_failures=true` 两天都成立）。
- `refill` 1 次：note 原文 `补水：补水成功（waterLeft 0 → 40）`；`waterLeft` 40 → 12 → 10。
- `farm.dryCrops` 32（起跑）→ **2**（#55）→ **1**（#125）；`water_area` 30+1 个 ok 与之吻合。
- 环境事实（**不是失败理由**，如实记）：种子 `[]`、钱 14g，note 反复出现 `没种子且钱不够（14g < 20g），只能干等/清障开垦`；`stage_no_target`/`stage_exhausted`/`stage_midway_leftover`/`plots_capped` 各 1；`plot_exhausted` 1。day1 的 `plant_area` 因 `no_seed` 停 ⇒ 该日 `no_unmet_stages=false`（finish 里 `unmet_days=["1年 spring 24日"]`）。
- 有 `review` 2 次、`复盘：还有活可做 —— field_nw/field_ne 还有地要清/开/种`。

**两次 `sleep` 原文（都是失败）**
```json
#53  {"event":"sleep","t":204.46,"ok":false,"code":"failed",
      "before":{"day":[1,"spring",24],"timeOfDay":1120,"stamina":180.50003,"isInBed":false,"question":"none","activeMenu":null},
      "after":null,
      "receipt":"timeout: [timeout] (HTTP 200) 第 1 跳失败（timeout）：走向 Farm → FarmHouse 的 warp 源格 (64,14) 超时…"}
#124 {"event":"sleep","t":320.65,"ok":false,"code":"failed",
      "before":{"day":[1,"spring",24],"timeOfDay":1400,"stamina":158.70004,"isInBed":false,"question":"none","activeMenu":null},
      "after":null,
      "receipt":"timeout: …（同上，剩余 51 步未走完）"}
```
⇒ 两次 `before.activeMenu=null`、`question="none"`、`isInBed=false` ⇒ **不是模态挡的、也不是"没有床/没有提问"**，卡点纯粹在**从田里走回门口那一跳**（`MoveToLocationSkill.cs:83 HopTimeoutMs=8000` 与路径长度无关 ⇒ 已开 **task-43**）。

**`no_day_progress` 1 次（原文）**
```json
{"event":"no_day_progress","t":320.65,"day":[1,"spring",24],"ended_by":"sleep_failed","reason":"回不了 FarmHouse：…"}
```
- 说明：这条**是合理停止路径**（连续两个日报告都没跨日 ⇒ 停），**不是** `cc2988e` 修掉的那个"睡成功却误判没前进"的 bug（那次 bug 的触发前提是 `sleep` 成功；本次两次 `sleep` 都是 `ok:false`）。按硬判据 ④ 仍如实计入"出现 1 次 `no_day_progress`"。

### 1.5 判据对照（按 Lead 更正后的口径）

| # | 判据 | 结果 |
|---|---|---|
| ① | 尾部连续 3 天 `ended_by=="sleep"` 且 `verified==true` | **0/3 ❌**（两个日报告都是 `sleep_failed` / `verified=false`） |
| ② | 每个日报告 `checks.day_justified==true` | **false / false ❌** |
| ③ | `no_work` 开头的日子必须 `final_water.dry == 0` | **不适用**（本轮没有任何 `no_work` 日报告；`no_work` 是 run3 的病灶） |
| ④ | 每个 `verified==true` 的日子要有真实动作 | **无 `verified` 日 ⇒ 不适用**；但动作本身全绿（89 ok / 0 failed） |
| ⑤ | 0 次 `bridge_down`/`modal_timeout`/`watchdog_stop`/`no_day_progress` | **`no_day_progress` 1 次**（合理停止路径，见上）；其余 3 项 **0 次** |
| ⑥ | exit code 0 | **exit code 1 ❌** |
| — | "每天 `day_end.final.location` 必须是 `Farm`" | **本判据已由 Lead 更正、不采用**（`final` 是睡前快照；且本轮两天都是 `Farm`，本来也不会误报） |

**外部证据**：`day_start`/`day_end` 的 `timeOfDay` 全程在 **spring 24**（650 → 1120 → 1130 → 1400）；`day_after` 两次都是 `null`；存档在本次窗口内**没有出现跨日写入** —— 收尾时（19:4x，只读）实际读数：

```
Wahaha_450799035      3623151 B   mtime 2026-10-13 19:32:46.399   <- 仍是 §1.2 那次 verify-sleep-brain 的跨日落盘
SaveGameInfo           25921 B   mtime 2026-10-13 19:32:46.531
Wahaha_450799035_old  3579973 B   mtime 2026-10-13 19:10:26.913   <- run3 结束时的存档
SaveGameInfo_old       25161 B   mtime 2026-10-13 19:10:26.916
```
⇒ run4 的窗口（19:33:37–19:38:58）内**一个字节都没落盘**，与"0 次跨日"完全一致；`_old`/`SaveGameInfo_old` 就是 run3 那一次，也说明 run4 连"开始新的一天"都没走到。

---

## 第 2 部分：结论与归因（RUN-4 有效 = FAIL）

1. **田区作业全绿**：浇水 30+1 个 ok、清障 28+29 个 ok，`failed_steps=0`、`env_block=0`、`inconclusive=0`、`proven_inert=0`；`farm.dryCrops` 32 → 2 → 1；补水一次成功（0 → 40）；`farm` 口径与 `water_area` 逐格吻合。⇒ 0.7.23 + `a302d61` 的**干活链路没有退化**。
2. **唯一的硬卡点 = "从田里走回 FarmHouse 门口那一跳"**：两次 `sleep_failed` 都停在 `Farm → FarmHouse` 的 warp 源格 `(64,14)`，`MoveToLocationSkill` 的单跳预算 **8000ms** 与"剩余 58 / 51 步"无关 ⇒ **跨日从未发生、体力从未恢复、`day_justified=false`**。这与 §1.2 里"**在屋里**床上用的 `--from-farm` 睡觉配方 VERIFIED"**不矛盾**：屋里到床的路径短、能过；从田里长距离接近门的那一跳过不去。（Lead 已据此开 **task-43**。）
3. **run4 的失败不含"睡醒在屋里"那个 bug**：两天 `day_start.location` 都是 `Farm`（`cc2988e`/`a302d61` 的修复在真机上生效），失败发生在**跨日之前**。
4. **不计成绩的两次**：§0.6 那次 13 秒死于 harness 托管作业 teardown（外部原因）；第 0 部分那次被 SDV 1.6 流浪宠物领养剧情阻断、**从未起跑**（且当次 `closeDialogue()` 导致事件跳过第一句，归我，取证已留档）。
5. **环境事实**（不作为成败理由）：种子 0、钱 14g ⇒ `plant_area` 永远 `no_seed` 停下、`till_area` 常见"没有可动目标"；这要等 task-24（卖收成换钱）之后才有意义。
6. **本轮未做**：未改源码、未 deploy、未 `load_save`、未替游戏做任何选择；**游戏保持运行**（按 Lead 要求，留给 0.7.24 装机验收用），未对桥发任何写请求；轮询监控已停止。
