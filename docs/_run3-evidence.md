# run3 取证：3 游戏日真机长跑（Mod 0.7.23）

**一句话结论：`needs_review` / 未达标。** run3 在真机上产出 6 个日报告（游戏日 spring 18–22，共跨 5 次夜），
尾部连续 `verified=true` 天数 = **0/3**，exit code **1**。期间 **0 次崩溃、0 次桥掉线、0 次模态卡死**。
根因只有一个：**睡醒后玩家在室内 FarmHouse，而"今天还有没有活"用的是当前观测窗口口径**
（`final.counts_scope="window"`、`tillable=0`、`crops=0`）⇒ 判 `no_work` ⇒ 06:00 立刻再睡。
于是 spring 19–22 连续 4 天每天只活 3.5 秒空转，`watered_outdoor=false` 是同一根因的直接后果。
唯一一个 VERIFIED 的日报告是 spring 18 的第二次尝试（睡觉成功、浇水达标）。

> 取证纪律：本文件所有结论都来自**观测差分 / 游戏自己的日志与存档文件 / 账本原文**，不采信任何 Mod 自述回执。

---

## 第 0 部分：起跑前现场（Lead 完成的前置，我不重复）

- Mod **0.7.23** 已装机并在运行：raw `bridge.json` = `{"schema":"agentfarm-bridge/1","port":17890,"token":"986044b15f25a231df341b9b1c463c28","pid":14052,"modVersion":"0.7.23","gameVersion":"1.6.15","smapiVersion":"4.5.2","startedAt":"2026-10-13T11:44:36+00:00"}`（mtime 19:03:38）。
- Lead 的 preflight：`python tools\preflight.py --expect 0.7.23 --save-baseline logs\run3-baseline.json` ⇒ **exit 0**。基线原文（`logs\run3-baseline.json`，19:03:29）：

```json
{
  "generatedAt": "2026-10-13T19:03:29+07:00",
  "recordedAt": "2026-10-13 19:03:29",
  "worldSeq": 1066,
  "modVersion": "0.7.23",
  "day": [1, "spring", 18],
  "timeOfDay": 1310,
  "location": "Farm",
  "playerTile": [64, 15],
  "stamina": 270.0,
  "money": 14,
  "isInBed": false,
  "seeds": [],
  "farmingLevel": 0,
  "crops": 32,
  "unwateredCrops": 32,
  "dryCrops": 32,
  "farmComplete": true,
  "farmScanSeq": 1065,
  "waterLeft": 35,
  "tillableCount": 157,
  "tileCount": 400,
  "tilesTruncated": true,
  "activeMenu": null,
  "isModal": false,
  "worldAdvancing": true
}
```

- 我自己的独立复核（19:04:25，**不加** `--save-baseline`，避免覆盖 Lead 的文件）：四项判据全 ✅
  （`hasSaveLoaded`、`location.isOutdoorFarm=true`、`ui.isModal=false`、装机版本 `0.7.23` == `MOD_VERSION_EXPECTED`）⇒ **exit 0**；
  读数 worldSeq 1073、`[1,"spring",18]` tod 1420、Farm [64,15]、体力 270.0、钱 14、`isInBed=false`、种子 `[]`、farmingLevel 0、
  crops 32 / unwateredCrops 32 / dryCrops 32、waterLeft 35、`tillableCount 157`、`tileCount 400`、`tilesTruncated true`、`worldAdvancing true`。
  （与 Lead 19:03:29 的基线一致，只有 tod 1310→1420 / worldSeq 1066→1073 因过了 56 秒而前进。）
- 进程：游戏 **PID 14052**（创建 18:44:29）。存档主文件 `Wahaha_450799035` = **3552427** / mtime **18:58:05.645**（`SaveGameInfo` 25360 / 18:58:05.646）。
- **pid 双向取证（Lead 要的那条结论）**：原始文件的 `"pid"` 键 = **14052**；同一份文件走 `brain/agentfarm/bridge.py:151 load_bridge_info()` 得到的 `BridgeInfo.pid` = **14052** ⇒ **两边一致**。
  结论：`task-13` 想防的"大小写容错"在真实 `bridge.json` 上**没有复现**；我此前报告过的 `pid=None` 也无法用真实文件复现（当时那次取证读的应该不是这个文件/对象，不是桥文件的问题）。
- **git 现场（19:04:34 起跑前实测，属历史读数）**：`git log --oneline -1` = `ab4b3aa task-38: 修复"睡成功却判游戏日没前进"（睡后重取观测 + day_end.day_after 作跨日证据）+ verify-run3 读 day_after；32 本账本矩阵无回归`；`git status --short` 只有 2 行 = ` M tools/run-longrun.py` + `?? scratch/run3-start.py`，那个 M 是**纯 help 文案**（`--max-plots` 说明），sha256 `1FA263CA89A953D2149409923FC9E369095DC5D89799187E06E6EB35D30116E2`、mtime 19:03:58。
  **时序说明（不是漏读）**：Lead 的 `f046419`（19:04:31）、`1be8f1c`（19:07:48）、`6e3d66a`（19:09:32）、`c921b13`（19:12:45）都落在我这次快照**之后**；
  run3 实际执行的代码 = 19:04:34 的工作树 = `ab4b3aa` 内容 + 那句 help 文案。

---

## 第 1 部分：运行窗口

- 命令：`python -u tools\run-longrun.py --days 3 --size 5 --max-minutes 150 --journal logs\longrun-3day-llm-run3.jsonl`（后台作业 `pwsh-306`，`PYTHONUTF8=1`）。
- 起跑 **19:04:34** → 结束 **19:10:28** = **354.02 秒（5.90 分钟）**，远没用满 150 分钟预算；动作 **176** 个；账本 **155** 行。
- 停止原因 = **日报告上限**：`{"event":"day_cap","days":6,"max_days":6}`（默认 `max(3×2, 3+2)=6`）；`[run] needs_review：尾部连续 0/3 天（共 6 天，176 个动作，5.9 分钟）`、`{"code":1,"verified_streak":0,...}`、`终态：needs_review`。**不是**崩溃/超时/掉线。
- `[prep] Mod 0.7.23 就绪；Farm [64, 15]；体力 270 钱 14g 作物 30（未浇 30）种子 []`。
- 跑完立刻按 GO 电文执行 `python tools\stop-game.py`（19:11:31）：`✅ 游戏已退出（原 pids=[14052]）`；随后复核进程 0、17890 无 LISTENING、`bridge.json` 被 Mod 自己删除；SMAPI 尾为 `Disconnected: ClosedGame` → `Disposing...`（**游戏自己走的退出路径**）；**存档未被 quit 改写**（仍 3579973 / 19:10:26.913）——星露谷只在睡觉时存盘。
- 账本事件与 LLM 调用（`scratch\analyze_run3.py` → `logs\run3-journal-summary.txt`）：
  - 决策 **33** 条 = `source` {`llm`: **7**, `deterministic`: 26}；`llm=true` 7、`truncated` **0**、`fallback` 非空 **0**；`boundary` = {new_day 1, task_kind_change 5, recovery 1, None 26}。
  - intent 分布：clear_area 29、water_area 5、till_area 4、review 4、recover_stamina 1、sleep 2、plant_area 1。
  - 事件计数：decision 33、outcome 33、intent_verdict 31、plot 10、blocked 7、day_start 6、sleep 6、day_end 6、policy 4、review 4、intent_vetoed 3、stage_exhausted 2、stage_midway_leftover 2、plots_capped 1、idle 1、plot_exhausted 1、seed_gate 1、plot_walk 1、stage_no_target 1、day_cap 1、finish 1。
  - **点名事件全 0**：`policy_fallback` 0、`work_spot` 0、`env_fail` 0、`inconclusive_fail` 0、`modal_dismissed` 0、**`no_day_progress` 0**（⇒ task-38 的修在真机生效）、`levelup_profession_pending`/`levelup_profession_unknown` 0、`day_justified_fail` 0、`refill` 0、`goto_farm` 0。

---

## 第 2 部分：逐日时间线（6 个日报告）

| # | 账本 | t(s) | 游戏日 | ended_by / ended_reason | day_after | 做成/跳过/失败 | 关键 checks | final_water（farm 口径） | `day_end.final.location` |
|---|---|---|---|---|---|---|---|---|---|
| 1 | #137 | 0.09→330.80 | spring 18 | **sleep_failed**：回不了 FarmHouse（`Farm → FarmHouse` 的 warp 源格 (64,14) 单跳 8000ms 超时；`walking:(64,15)(door_push)` started→timeout；`(63,14)(door_push)` unreachable） | — | 161 / 0 / **7** | `slept_by_us=false`、`no_hard_failures=false`、`day_justified=false`；`crops_watered=true`、`watered_outdoor=true`、`no_unmet_stages=true` | `Farm` tiles=132 crops=33 **dry=0** | `Farm` [35,30] tod2200 |
| 2 | #140 | 330.84→339.65 | spring 18（同日重试） | **sleep**：`night:时间 2210 已经到夜里（≥2200）` | `[1,"spring",19]` | 0 / 0 / 0 | **7 条判据全 true（`verified=true`）** | `Farm` tiles=133 crops=33 **dry=0** | `Farm` [53,16] tod2210 |
| 3 | #143 | 339.66→343.31 | spring 19 | **sleep**：`no_work:确实找不到可做的活（地里的活干完了、也没法/没必要买种子）` | `[1,"spring",20]` | 0 / 0 / 0 | 只有 **`watered_outdoor=false`** | `Farm` tiles=123 crops=33 **dry=33** | **`FarmHouse`** [9,9] tod600 isInBed=true |
| 4 | #146 | 343.32→346.87 | spring 20 | 同上 `no_work` | `[1,"spring",21]` | 0 / 0 / 0 | 只有 `watered_outdoor=false` | `Farm` tiles=113 crops=32 **dry=32** | **`FarmHouse`** |
| 5 | #149 | 346.89→350.46 | spring 21 | 同上 `no_work` | `[1,"spring",22]` | 0 / 0 / 0 | 只有 `watered_outdoor=false` | `Farm` tiles=107 crops=32 **dry=32** | **`FarmHouse`** |
| 6 | #152 | 350.46→354.02 | spring 22 | 同上 `no_work` | `[1,"spring",23]` | 0 / 0 / 0 | 只有 `watered_outdoor=false` | `Farm` tiles=96 crops=32 **dry=32** | **`FarmHouse`** |

- 睡觉记录 6 条：1 条 failed（#134）+ 5 条 ok。5 条成功**都是** `answerDialogueAction("Sleep_Yes")`、约 1.4–1.5 秒；spring 18 那次回执明写
  `已踩触发格 (10, 9)：回执 ui_modal = **命中信号**（睡觉提问被自己弹出来了，世界冻结是预期行为）`。
- **`day_start` 记录（#141/#144/#147/#150）逐条如下，这是根因的直接证据**：
  `{"day":[1,"spring",19],"timeOfDay":600,"stamina":270,"money":14,"crops":0,"unwatered":0,"location":"FarmHouse","weather":"sunny"}`（20/21/22 同形）。
- spring 19–22 四个日报告各只活约 3.5 秒 ⇒ 5 次跨日全挤在 **19:10:12–19:10:28 的 16 秒里**。
- 天气：spring 22 的 `day_start.weather="debris"`；跑完观测到 spring 23 `weather="rain"`（见第 6 部分的提醒）。

---

## 第 3 部分：spring 18 的真实成绩（唯一一个 VERIFIED 日）

- 阶段汇总（#137 的 33 个 stage 段）：`water_area` 3 段 tiles 32 / ok **32** / failed 0；`clear_area` 28 段 tiles 135 / ok **128** / failed **7** / leftover 12；`plant_area` 1 段 tiles 2 / ok 1 / `stopped="no_seed"`；`till_area` 1 段 tiles **0**（没目标）。
- **浇水 = 达标**：`final_water`（farm 口径）= `Farm tiles=132 crops=33 dry=0`；`checks.crops_watered=true`、`watered_outdoor=true`。
- **外部交叉校验（不依赖 brain 自述）**：`player.wateringCan.waterLeft` 起跑 **35** → 跑完 **2** = 净耗 **33** 格，与 farm 口径的 33 株作物精确吻合。
- 7 个失败格全部在 `field_ne`，原因同一类"**四邻都站不过去**"：`(21,42)`、`(20,43)`、`(21,43)`、`(21,44)`、`(21,45)`、`(21,46)` + 另 1 格（原文 `error: 7 格没做成（例：(21, 46) 四邻都站不过去）`；`evidence` 列出 `(21,46)/(21,45)/(21,44)`）。
  `env_block=0`、`inconclusive=0`、`proven_inert=0`、`no_unmet_stages=true` ⇒ 属**环境不可达**，不是"动了没用"，也不是脚本 bug。
- **播种/开垦本次没有目标**（按 task-9 口径）：种子 0 粒、钱 14g < 种子单价 20g ⇒ 日志明写"今天不再开垦/播种：till_area 没有目标（锄了也种不下去 = 纯烧体力）"；`plant_area` 提前停 `no_seed`（2 格目标做成 1 格后停）。
  如实记录：**本次自主链 = 浇水 → 清障 → 跨日睡觉，没有播种环节**；播种要等 task-24 卖收成换钱之后补 run4。
- 该日报告唯一失败原因（`ended_by=sleep_failed`）= **回不了 FarmHouse**（夜间寻路）：`walking:(64,15)(door_push)` started→timeout、`(63,14)(door_push)` unreachable（A* 未算出路径）；`no_hard_failures=false`、`day_justified=false`。
  第二次（#140）成功睡下 ⇒ 与 Lead 的彩排结论一致：**第一次夜里回家寻路失败是允许的，长跑会重试同一天**。

---

## 第 4 部分：跨日外部证据（游戏自己的日志/文件，不依赖 Mod 回执）

5 次跨日，每次都是 `Synchronizing 'NewDay' task...` → `Context: before save.` → `SaveGame.Save() called.` → `Synchronizing 'Save' task...` → `SaveGame.Save() completed without exceptions.` → `Context: after save, starting spring N Y1`：

| 跨到 | SMAPI 行号（NewDay / before save / Save called / Sync Save / completed / after save） | 时间 |
|---|---|---|
| spring 19 | L4141 / 4144 / 4145 / 4146 / 4149 / 4150 | 19:10:12 → 19:10:14 |
| spring 20 | L4160 / 4163 / 4164 / 4165 / 4168 / 4169 | 19:10:15 → 19:10:18 |
| spring 21 | L4179 / 4182 / 4183 / 4184 / 4187 / 4188 | 19:10:19 → 19:10:21 |
| spring 22 | L4198 / 4201 / 4202 / 4203 / 4206 / 4207 | 19:10:23 → 19:10:25 |
| spring 23 | L4217 / 4220 / 4221 / 4222 / 4225 / 4226 | 19:10:26 → 19:10:28 |

> ⚠️ **行号保质期（Lead 注，2026-10-13 19:22，deputy-lead 审计 §7 提出）**：上表的行号读数时刻是 **19:11:31**。`SMAPI-latest.txt` 已于 **19:15:49** 被 run4 会话覆盖（行数 4236 → 424 起，NewDay/Save 命中 0），因此 **L4141–L4226 已无法在原文件复核**（这是 run4 覆盖所致，不是本文档之误）。覆盖**之后**冻结的窗口副本是 `logs\run4-smapi-window.txt`（**444 行 / 38581 B / mtime 2026-10-13 19:21:21**）—— 它保存的是 **run4 会话**，含 task-14 的 ~370 行 `Warping to Farm`（L361–L413）证据，**不含**上表那 5 组 run3 的 NewDay 行。存档侧读数不受影响（逐字吻合，见下）。

- 存档目录 `C:\Users\admin\AppData\Roaming\StardewValley\Saves\Wahaha_450799035\`：
  主文件 起点 **3552427** / 18:58:05.645 → 终点 **3579973** / **19:10:26.913**；`Wahaha_450799035_old` = 3543468 / 19:10:23.367（= 跨到 spring 22 那一档）；`SaveGameInfo` 25161 / 19:10:26.916、`_old` 25135 / 19:10:23.369。
  ⇒ **每次跨日都真的落盘**，最后一次跨日（spring 23）在 19:10:26 落盘；exit 后未被改写。
- 跑完观测（19:11:06，`logs\run3-observe-end.json`，worldSeq 1828）：clock `year1 spring 23 tod 650 weather rain`、`FarmHouse`、玩家 `Jay [9,9] isInBed=true`、体力 270/270、钱 14、farmingLevel 0、`waterLeft 2/40`、
  `farm {crops 32, unwatered 14, dry 0, ripe 0, hoeDirt 92, emptyDirt 60, complete true, scanSeq 1827}`、无模态、`worldAdvancing=true`
  ⇒ 与账本末条 `day_after=[1,"spring",23]` **对齐**（外部世界校验跨日链）。
- 窗口内关键词计数（SMAPI 日志 2965 行之后）：`Disconnected` **0**、`Disposing` **0**、`ERROR` **0**、`soft_oal` **0**、`ClosedGame` **0**（退出后才各 1 条）、`no_day_progress` **0**；
  `Exception` 命中 5 处，**全部**是 `SaveGame.Save() completed without exceptions.` 这 5 行本身（文本里带 "exceptions" 一词），**不是真异常**。
  ⇒ **0 次进程崩溃、0 次桥掉线**。SMAPI 日志行数 2965（19:03:29）→ 4236（19:11:31）。

---

## 第 5 部分：根因（与 Lead 的读法一致）

1. 机制：睡觉成功 → 游戏 `Game1.NewDay` 把玩家放回床（**室内 FarmHouse**）→ 长跑评估"今天还有没有活"时用的是**当前观测窗口**
   （`final.counts_scope="window"`、`tillable=0`、`crops=0`，室内看不到任何作物/可耕格）⇒ `sleep_guard` 判 `no_work` ⇒ 06:00 立刻再睡。
2. 同一条账本里三处互证：`day_start.location="FarmHouse"` + `crops 0 / unwatered 0`（#141/144/147/150）；
   与此同时 `final_water(scope=farm)` 报 `dry=33/33`（作物其实全是干的）；`checks.watered_outdoor=false`、note 明写"浇水证据不足/未浇完"。
3. 后果：spring 19–22 连续 4 天 **0 动作**空转，`verified_streak` 停在 0，`day_cap=6` 用尽后停下。
4. 附带事实（不影响判定，供 task-10 / 新修复参考）：
   - `farm.unwateredCrops` 恒为 **14** 而实际干格是 33/32（`FarmWorker` 自己声明"不是干格数、不参与判定"）；
   - `farm.hoeDirt` 随清障从 132 → 123 → 113 → 107 → 96，说明**窗口观测被截断时 farm 聚合也会变小** ⇒ farm 口径数字只能作**同刻**判据，不能跨日比较。

---

## 第 6 部分：观测差分（19:04:25 起跑前 vs 19:11:06 跑完后，`scratch\run3-diff.py` 生成）

| 字段 | 起跑前 | 跑完后 |
|---|---|---|
| worldSeq | 1073 | 1828 |
| clock | `spring 18 tod1420 sunny` | `spring 23 tod650 **rain**` |
| location / isOutdoorFarm | `Farm` / **true** | `FarmHouse` / **false** |
| player.tile / isInBed | [64,15] / false | [9,9] / true |
| stamina / money / farmingLevel | 270 / 14 / 0 | 270 / **14** / 0 |
| wateringCan.waterLeft | **35** | **2** |
| inventoryCount | 12 | 12 |
| farm.crops | 32 | 32 |
| farm.unwateredCrops | 32 | **14** |
| farm.dryCrops | 32 | **0** |
| farm.hoeDirt / emptyDirt | 86 / 54 | 92 / 60 |
| farm.weeds / stones / twigs | 443 / 221 / 107 | **414 / 202 / 97** |
| farm.trees / grass | 247 / 672 | 289 / 727 |
| ui.isModal / worldAdvancing | false / true | false / true |

- 背包（起跑前 → 跑完后）：`Axe×1 Hoe×1 Watering Can×1 Pickaxe×1 Scythe×1 Geode×1→2 Stone×56→77 Wood×36→51 Fiber×36→67 Coal×3→9 Clay×5→6`
  —— 全是**清障掉落**；**没有种子、没有买/卖**，钱 14g→14g 未变。
- **雨天提醒（如实记录，不是任何人改的）**：跑完时是 spring 23 `weather=rain`；雨天游戏会自己把作物浇上，
  这会**降低** run4 第一天的浇水压力（run4 若在雨天开始，`dry` 可能一开始就是 0）。

---

## 第 7 部分：判据对照（task-12 硬验收，缺一不可）

| 判据 | 结果 |
|---|---|
| 尾部连续 3 天 `ended_by=="sleep"` **且** `verified==true` | ❌ **0/3**（唯一 VERIFIED 是 spring 18 的第 2 个日报告；其后 4 天 `verified=false`） |
| `checks.day_justified==true`（只认 night/stamina/no_work） | ⚠️ spring 18 第 1 个日报告 `day_justified=false`；其余 5 个因 `no_work`⇒true，但按根因那是**空转式收工** |
| 期间 0 次桥掉线 / 进程崩溃 | ✅ 0 |
| exit code 0 | ❌ **1** |
| 外部证据齐备（存档 mtime/size + SMAPI NewDay/SaveGame 行号 + `day_after` 与 observe 对齐） | ✅ 5 次跨日全部三对齐 |
| 每天 `day_end.final.location` 必须是 `Farm`（Lead 新增） | ❌ **4/6 天是 `FarmHouse`**（本 bug 的特征）；spring 18 两个日报告都是 `Farm` |

**结论：`needs_review`，未达标。** 按"失败也要交"的要求，首个异常事件（#137 `sleep_failed` 回不了 FarmHouse）与账本全文（155 行）都在 `logs\longrun-3day-llm-run3.jsonl`。

---

## 第 8 部分：诚实声明

- 本次我**没有**任何源码/Mod 改动，**没有** deploy；写入只落在 `logs\`、`docs\_run3-evidence.md`、`scratch\`（`run3-start.py`、`run3-end.py`、`run3-diff.py`、`run3-dayend.py`、`analyze_run3.py`）。
- 没有为了好看改任何读数：`farm.unwateredCrops=14` 与干格 33/32 的矛盾、`day_justified` 的模糊处、雨天、播种无目标、7 个失败格全部原样写出。
- 跑完 19:11:31 已 `stop-game.py` 优雅退出（进程 0、端口 0、`bridge.json` 已删）；**不重启、不续跑**。
- run4 由 Lead 起：Lead 跑 `deploy-mod.py --no-quit` + `preflight --expect 0.7.23 --save-baseline logs\run4-baseline.json` → 给我 go；我的命令用新开关 `--max-days 9`
  （run3 的 `day_cap=6` 太紧：睡失败会重试同一天、每次都占一个日报告）：
  `python -u tools\run-longrun.py --days 3 --size 5 --max-minutes 150 --max-days 9 --journal logs\longrun-3day-llm-run4.jsonl`。
- 保留物：`scratch\run3-start.py`、`logs\run3-observe-start.json`（Lead 要引用）、`logs\run3-observe-end.json`、`logs\run3-journal-summary.txt` 都不删。
