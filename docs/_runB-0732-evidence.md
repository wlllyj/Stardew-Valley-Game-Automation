# run B（task-113）证据 —— 0.7.32 · 与 run A 同构建

> **状态：已提前叫停；游戏已优雅退出**（脑进程 PID `10480` 于 `2026-10-17T04:50:42` 停止，**没有 `finish` 行**；叫停时游戏在 `fall 11 tod 700`，其后游戏自行走时钟到 `05:04:35` 自动跨夜，随后按 m02833 用 `tools\stop-game.py` 退出 ⇒ 见 §7 诚实声明）。
> 叫停理由与停止点留档见 **§0**（Lead m02439 裁定：`[60,29]` 熟了却摘不到 ⇒ 0.7.32 代码病 ⇒ B 臂是"因病退化的无效对照臂"）。
> 结构：§0 提前叫停 / §1 起跑与前置 / §2 `[60,29]` 现场 / §3 SMAPI 六串 / §4 逐日表与两侧工具 / §5 存档链与观测计数 / §6 世界差分 / §7 保留物·不确定项·诚实声明 / §8 A/B 对照（结论标"L2 及以下不可用"）。
> 判据纪律：**只认独立观测差分**（`observe?detail=full`），回执不作证据；缺失字段写【无法判定】，**缺失 ≠ 通过**。

---

## §0 提前叫停（Lead m02439 裁定，我执行；**如实留档，不补造 finish**）

### 0.1 停止方式与停止点

| 项 | 值 |
|---|---|
| 停止时刻 | **`2026-10-17T04:50:42+0700`** |
| 停止手段 | `Stop-Process -Id 10480`（PID 取自 `logs\longrun-runB-0732.pid`）⇒ 脑进程 `pid_alive = False` |
| 游戏 | **未动**：`StardewModdingAPI` 进程数 **1**（游戏 PID 20672）；**没有** `stop-game.py`、**没有** `load_save` |
| 账本 | `logs\longrun-runB-0732.jsonl` = **723 行**；`last_t = 1393.49`；`last_event = outcome`（`{kind: harvest, terminal: needs_review, postcondition_met: false, detail: ["(60, 29): 交互后作物还在（可能没摘到）"]}`） |
| `finish` 行 | **没有**（`journal_finish = null`）⇒ 所有工具判决都只能是"**临时**"，不得当验收依据 |
| console | `logs\longrun-runB-0732.console.log` = **9481 B / 85 行**；`.console.err.log` = **0 B**（全程） |
| end 外部快照 | `scratch\runB-0732-external-snapshots.jsonl` 的 `tag=end`（`at 2026-10-17T04:57:04`，显式 `--pid-file`）：`pid 10480 / pid_alive=false`、`journal 723 last=outcome`、`mod_version_matches=true`、`console_err 0 B` |

**已完成/进行中的游戏日（`day_end` 原文要点）**：

| 日 | t | ended_by | verified | 跨日 | ok/skip/fail | `final_water.dry` | 未通过判据 |
|---|---|---|---|---|---|---|---|
| fall 9 | 613.21 | `sleep` | False | ✅→fall 10 | **0**/0/**41** | 0 / 102 | `no_hard_failures`（`zero_action_evidenced` = **false**） |
| fall 10 | 1348.06 | `sleep` | False | ✅→fall 11 | 89/1/30 | **1** / 102 | `no_hard_failures`、`watered_outdoor`（`zero_action_evidenced` = true） |

两天 `ended_reason` 均为 `night:时间 2200 已经到夜里（≥2200）`。`day_start` 三条：`fall 9 @Farm money 0 crops 106` → `fall 10 @FarmHouse` → `fall 11 @FarmHouse`。

⚠ **一处事实更正（我此前报告"停在 fall 10"，实际不是）**：叫停前游戏日**已自己翻过两次页**（run B 的 fall 10 正常 `sleep` 收尾、fall 11 已开始，`day_start` `t=1348.1`），因此**停止点是 `fall 11`；`fall 11` 的 harvest 尝试（`last_t=1393.49`）没有 `day_end`**。

### 0.2 停止时的现场（`[60,29]` 仍 `ripe`，跨两次跨日未变）

- `clock = {fall 11, timeOfDay 700, weather rain}`；玩家 `Jay Farm[60,28] stamina 247.20007 money 0 farmingLevel 1`；
- `farm = {crops 102, ripeCrops 1, unwateredCrops 5, dryCrops 0, deadCrops 0, hoeDirt 158, emptyDirt 56, scanSeq 3943}`；
- `[60,29] = {kind: dirt, feature: HoeDirt, standable: true, actionable: true, crop: "270", ripe: true, dead: false, watered: true}`（与 fall 10 两次观测**逐字相同**）；`[59,29] = tree`；`[61,29]/[60,28]/[60,30] = crop "262" 未熟`。
- 完整原文另存 **`scratch\runB-0732-tile6029-live.json`**（含完整 `observe`、clock/liveness/ui/player/farm 与 5 格 tile 记录）⇒ **harvest 修复后的同格前后对照基线**。

### 0.3 叫停理由（Lead 裁定原话要点）

`[60,29]` 在窗口内、`standable/actionable/watered/ripe` 全真，而观测时玩家就站在正邻居 `[60,28]` ⇒ **不是够不着，是"这一格熟了却摘不到"**；配上 `farm.ripeCrops=1` 与 `intent_vetoed{sleep: "农场口径还有 1 格熟作物…先去收"}` ⇒ 守卫整天被这 1 格钉死。**这是 0.7.32 的代码病，不是策略问题** ⇒ B 臂判为**因病退化的无效对照臂**，继续跑只会重复"0 成功 / 40+ 失败"并占住游戏与桥。修复（`harvest` 路径）优先于跑满。

---

## §1 起跑与版本四要素（A/B 同构建核对）

- **冻结提交** `300a01c`（0.7.32：`mod/AgentFarm.Bridge/manifest.json` 0.7.32 + `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED="0.7.32"`；`tools\check-release.py --expect 0.7.32` **六项全绿**含 **`Ran 874 tests` / OK**、树干净；`deploy-mod.py --no-quit` 0.7.31 → 0.7.32、桥 `modVersion=0.7.32 port=17890`）。
- **起跑命令**（脱离式；argv 与 run A **只差 `--journal`**）：
  `…\python.exe -u tools/run-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12 --journal logs/longrun-runB-0732.jsonl`
  ⇒ **PID 10480 / 起跑 `2026-10-17T04:27:17`**；账本 `logs\longrun-runB-0732.jsonl`；console `logs\longrun-runB-0732.console.log`（`.console.err.log` 全程 **0 B**）；sidecar `logs\longrun-runB-0732.version.json`。
- **五文件 SHA256 与 run A 的 sidecar 逐字一致**（起 B 前用 `scratch\runB-pre.py` 逐项核对，退出码 0）：

| 文件 | SHA256（A = B） | mtime |
|---|---|---|
| `brain/agentfarm/longrun.py` | `6005F5E17BAEB050D8E7BAE9D36DAE2080CAD73867AC0C144033063373149507` | 2026-10-17T03:29:58.203408 |
| `brain/agentfarm/farmwork.py` | `7ED2DF1BA953C0B10AED389B2376819B6A24CB108A8927EC3D20C6C6C34913A8` | 2026-10-17T03:08:27.223513 |
| `brain/agentfarm/bridge.py` | `FF45381DBC732FDD6933983CA5EC6D58D891FF7315EFE27D86643A985425FA93` | 2026-10-17T03:43:01.214404 |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `5413C2BEEBA199BD9F5B065E3E88ED9A255253B6B90F3F0234BD6BD9769EFE65` | 2026-10-17T03:43:15.836710 |
| `mod/AgentFarm.Bridge/manifest.json` | `E6BA1B4C6ADABD3D467A6A4609ECDD70CA4DCA50782EF2F91085D36FD7F0DE73` | 2026-10-17T03:42:40.206287 |

- **sidecar 指纹**：`head = b18917a79e8737577154e35ad5c8919667b469ff`（按 Lead 口径**只作参考、不拿 head 比**）、`pid = 10480`、`started_at = 2026-10-17T04:27:17`、`worktree_clean = false`、`git_status_short = ["?? scratch/runA-tools.py", "?? scratch/runB-pre.py"]`（我本轮新增的取证脚本，**非被测源码**）。
- **教训库拷贝（run A → run B 唯一"记忆"通道，原样字节拷贝 `shutil.copyfile`）**：
  - run A：`logs\longrun-runA-0732-lessons.json` = **3220 B / mtime 2026-10-17T04:22:52 / SHA256 `C42AF6BE52D0DC30973E4E62512AFC79D554881F0382BE3ADC892D98ED98D642`**
  - run B：`logs\longrun-runB-0732-lessons.json` = **3220 B / mtime 2026-10-17T04:25:53 / SHA256 同上（两侧一致 = True）**
  - **拷贝时刻 = `2026-10-17T04:25:53+0700`**
  - ⚠ **该文件在跑动中被 run B 自己持续重写**（脑侧持久化）：04:25:53 拷贝时 3220 B → 04:3x 一度 3085 B / 6 条（Lead 直查）→ 04:37:31 已 3365 B / SHA256 `25DBD1EF1F759283…`。⇒ §1 的"预置"证据以 **04:25:53 那一行**为准；后续大小变化属预期，不代表拷贝失败。

### 1.2 起跑前工况（两次 preflight 读数，均留档）

- **第一次（04:26:17）**：四项里 **唯一不过项 = `在户外农场 ❌`**（`location=FarmHouse`、`playerTile=[9,9]`、`isInBed=true`）；读数 `day=[1,'fall',9] tod 710 / 体力 245.30008 / 钱 0g / 种子 483×1 / crops 117 / unwatered 5 / dryCrops 0 / farmingLevel 1 / 无模态 / worldAdvancing true`。基线写入 `logs\runB-0732-baseline.json`（随后被第二次覆盖）。
- **标准 bring-up**（`python -m agentfarm goto Farm --no-focus`）：`FarmHouse(9,9) → Farm(64,15)`、hop1 `result=ok source=[3,12] landing=[64,15]`、**7619ms**（这也正是 `run-longrun` 自己的 `[prep]` 会做的事）。
- **第二次（04:27:17，覆盖后的现基线）**：**四项全绿**，`day=[1,'fall',9] tod 820 / Farm(64,15) / 体力 245.30008 / 钱 0g / 种子 483×1 / crops 117 / unwateredCrops 5 / dryCrops 0 / farmComplete true / farmScanSeq 2400 / waterLeft 8 / tillableCount 117 / tileCount 400(truncated) / farmingLevel 1 / activeMenu null / isModal false / worldAdvancing true`。
- **A→B 之间的世界差异（真实发生、不是我做的操作，只记现象不推断机制）**：run A 在 `fall 8` 以 `sleep_failed` 收工（`tod 2240`、人还在农场醒着）⇒ 到我起 B 时游戏自己已推进到 **`fall 9` 早晨**，且 `farmingLevel` 由 **0 → 1**（升级发生过；B 起跑时无模态、无 `professionsToChoose`）；存档 `4221434/04:10:25.974` → **`4248971/04:25:17.592`**。

---

## §2 进行中快照（task-169：`harvest` 反复失败 —— 只读，未改任何参数）

采集时刻 **2026-10-17T04:42:34 / 04:42:54**（两次 `observe?detail=full`，脚本 `scratch\runB-status.py`；原始两份观测落 `scratch\runB-0732-status-044254.json`）。

### 2.1 观测 A @ 04:42:34

```
clock                = {"year": 1, "season": "fall", "day": 10, "timeOfDay": 1240, "weather": "sunny", "weatherOnFarm": "sunny"}
liveness             = {"worldAdvancing": true, "secondsSinceClockMoved": 3.991}
game                 = {"paused": false, "shouldTimePass": true}
ui                   = activeMenu=None / isModal=False / dialogueIsQuestion=False / professionsToChoose=None
player               = Jay loc=Farm tile=[60, 28] stamina=78.10041 money=0 isInBed=False farmingLevel=1 waterLeft=27
farm                 = {"crops": 102, "ripeCrops": 1, "unwateredCrops": 5, "dryCrops": 1, "deadCrops": 0, "dryDeadCrops": 0,
                        "hoeDirt": 149, "emptyDirt": 47, "weeds": 475, "stones": 109, "twigs": 77, "trees": 687,
                        "grass": 1028, "complete": true, "scanSeq": 3572}
location             = Farm isOutdoorFarm=True tiles=400（截断）
```

`[60,29]` 及其四邻的**原始 tile 记录**（全部**在窗口内**）：

```
tile [60,29]: {"tile":[60,29],"kind":"dirt","tool":"none","feature":"HoeDirt","standable":true,"actionable":true,"crop":"270","ripe":true,"dead":false,"watered":true,"plantable":false}
tile [59,29]: {"tile":[59,29],"kind":"tree","tool":"axe","feature":"Tree","standable":false,"actionable":true,"ripe":false,"dead":false,"watered":false,"plantable":false}
tile [61,29]: {"tile":[61,29],"kind":"dirt","tool":"can","feature":"HoeDirt","standable":true,"actionable":true,"crop":"262","ripe":false,"dead":false,"watered":true,"plantable":false}
tile [60,28]: {"tile":[60,28],"kind":"dirt","tool":"can","feature":"HoeDirt","standable":true,"actionable":true,"crop":"262","ripe":false,"dead":false,"watered":true,"plantable":false}
tile [60,30]: {"tile":[60,30],"kind":"dirt","tool":"can","feature":"HoeDirt","standable":true,"actionable":true,"crop":"262","ripe":false,"dead":false,"watered":true,"plantable":false}
```

### 2.2 观测 B @ 04:42:54

```
clock                = {"year": 1, "season": "fall", "day": 10, "timeOfDay": 1310, "weather": "sunny", "weatherOnFarm": "sunny"}
liveness             = {"worldAdvancing": true, "secondsSinceClockMoved": 2.14}
game                 = {"paused": false, "shouldTimePass": true}
ui                   = activeMenu=None / isModal=False / dialogueIsQuestion=False / professionsToChoose=None
player               = Jay loc=Farm tile=[70, 24] stamina=78.10041 money=0 isInBed=False farmingLevel=1 waterLeft=27
farm                 = {"crops": 102, "ripeCrops": 1, "unwateredCrops": 5, "dryCrops": 1, "deadCrops": 0, "dryDeadCrops": 0,
                        "hoeDirt": 149, "emptyDirt": 47, "weeds": 475, "stones": 109, "twigs": 77, "trees": 687,
                        "grass": 1025, "complete": true, "scanSeq": 3589}
```

`[60,29]` 的记录与观测 A **逐字相同**（`crop "270"` / `ripe true` / `watered true` / `standable true` / `actionable true`）。

### 2.3 两次读数增量（判"在推进"还是"原地打转"）

| 指标 | A → B（20 秒墙钟） | 判读 |
|---|---|---|
| `worldSeq` | `3572 → 3589`（Δ **+17**） | 世界在动 |
| `clock.timeOfDay` | `1240 → 1310`（Δ **+70**） | **时间在走**（约 7 秒墙钟 = 10 游戏分钟） |
| `liveness.worldAdvancing` | `true → true` | 未被冻住 |
| `liveness.secondsSinceClockMoved` | `3.991 → 2.14` | 时钟刚动过 |
| `player.tile` | `[60,28] → [70,24]` | 角色在移动 |
| `farm.crops` / `dryCrops` | `102 → 102` / `1 → 1` | 全局计数未变 |
| 账本行数 | `468 → 485`（Δ **+17**） | 在持续记账 |

**结论（我的读数依据）**：**这一天在推进，不是死锁** —— `timeOfDay` 20 秒墙钟走了 70 分钟、`worldSeq` +17、账本 +17，且当日已由 `fall 9` 自然翻到 `fall 10`（04:37:35 观测到 `[day] 1年 fall 10日 开始`）。
**但 `harvest` 这个子目标在原地打转**：`[60,29]` 在 20 秒间隔的两次独立观测里 **`ripe` 恒为 true、`crop "270"` 不变**，而账本里同一格反复出现 `stage_exhausted{stage:"harvest", tiles:[[60,29]], capped:1, leftover:1}` 与 `outcome{kind:"harvest", postcondition_met:false, "目标 1 步：做成 0、跳过 0、失败 1"}`。
**关键事实（对 task-169 有用）**：这**不是够不着的问题** —— 观测 A 里玩家就站在 **`[60,28]`**（`[60,29]` 的正邻居），而 `[60,29]` 本身 `standable=true`、`actionable=true`、`watered=true`、`ripe=true`、`kind=dirt`、`tool=none`；唯一不顺的邻居是 `[59,29]`（`kind=tree`、`standable=false`、`tool=axe`）。⇒ 反复失败更像**交互没落到目标格 / 采摘动作没生效**（账本自述 `交互后作物还在（可能没摘到）`），而不是寻路问题；机制不推断，只记现象。

### 2.4 L1（教训注入）当场证据补充

- `logs\longrun-runB-0732-llm.jsonl`：**48 行 = 47 条 `decision` + 1 条 `review`**；**47/47 条 `decision` 的 prompt 里都出现「教训」节**，唯一不含的是那 1 条非决策的 `review` 行（#42）。
- 现场教训库（会被 B 持续重写）此刻 = `{"lessons":[6 条]}`：`stuck_with_leftover|harvest` count **48**、`stage_incomplete|harvest` count **120**、`dead_crops_blocking|farm` count 4、`stuck_with_leftover|water_area` count 4、`stuck_with_leftover|plant_area` count 1、`stuck_with_leftover|till_area` count 1（Lead 04:3x 直查时 `stage_incomplete|harvest` 还是 79 ⇒ 它在跑动中增长）。
- `tools\compare-runs.py` 存在（`--run-a/--run-b/--label-a/--label-b/--json`）；其 `lessons_total / lessons_hits / injection_effective` 三键见 **§8.1**：**修正后（`2e3289e`）= `lessons_total 6` / `lessons_hits 4` / `injection_effective true` / `lesson_section_present true`**，与本节直查的 **47/47** 同向（旧版 `false`/0 命中是工具字段口径错误导致的误报，已裁定）。

---

## §3 SMAPI 冻结窗口与六串配对

- 冻结文件：`logs\runB-0732-smapi-window.txt` = **584107 B / 8032 行 / mtime `2026-10-17 04:50:42.879` / SHA256 `DDD6619EEB0E5E681C506C5D9D49AB7620E873A8F56DA8A18C967D11F216182B`**（源/副本 SHA 一致）。
- 窗口 `04:27:17–04:50:42`：带时间戳行 **2557** / 文件 8032。

| 串 | 窗口内次数 | 行号 |
|---|---|---|
| `Synchronizing 'NewDay' task` | 2 | 6088, 7604 |
| `Context: before save.` | 2 | 6091, 7607 |
| `SaveGame.Save() called.` | 2 | 6092, 7608 |
| `Synchronizing 'Save' task` | 2 | 6093, 7609 |
| `completed without exceptions` | 2 | 6096, 7612 |
| `after save, starting` | 2 | 6097, 7613 |

⇒ **B 窗口内六串 2/2 逐条配对齐全**（`Save_called` 原始计数在窗口内也是 2，窗口内没有插件描述行）。
**整份冻结文件的累计**：`NewDay 8 / before save 8 / Save called 11(原始) / Save task 8 / completed 8`；按"有日志前缀且非插件描述行"修正后 `Save called = 8`（差 1 行 = `L16` 插件描述行 `[03:43:40 INFO  SMAPI]    AgentFarm Bridge 0.7.32 by AgentFarm | v0.7.32（…）`，含 ` by AgentFarm `）。8 次 `NewDay` = run A 的 5 次 + 中间 1 次游戏自动跨日（`fall 8→9`）+ **run B 的 2 次** ⇒ 只有后 2 次属于本跑。
噪声（窗口内）：`Warping to Farm` **628**（task-14 逐帧活锁，信息项）、`GET /v1/observe` **1502**；`ERROR`/`Disconnected`/`ClosedGame`/`Disposing`/`soft_oal`/`Exception` **全 0**。

## §4 逐日表与两侧工具判决

| 日 | ended_by | 跨日 | verified | ok/skip/fail | `final_water.dry` | 未通过判据 | 备注 |
|---|---|---|---|---|---|---|---|
| fall 9 | `sleep` | ✅→10 | False | **0**/0/**41** | 0 / 102 | `no_hard_failures` | `zero_action_evidenced = **false**`（0 步成功却没被标"零动作"） |
| fall 10 | `sleep` | ✅→11 | False | 89/1/30 | **1** / 102 | `no_hard_failures`、`watered_outdoor` | `zero_action_evidenced = true`；30 个失败步绝大多数是 `[60,29]` 的 harvest |
| fall 11 | （无 `day_end`） | — | — | — | — | — | 被提前叫停 |

- **`tools\verify-run3.py --journal logs\longrun-runB-0732.jsonl --days 3 --json` ⇒ rc=1**：`verdict="needs_review"`、`strict_verdict="needs_review"`、`strict_problem_count=12`。问题清单要点（原文 `logs\runB-0732-verify.txt`）：`[fall 10] 当天有 1 格干作物认输（不再当"有活"）`、`[fall 10] 账本 assigned_undone=1 但 journal 没有 stage_shortfall_day 落痕 ⇒ 无法交叉核对（缺失 ≠ 通过）`、`[fall 10] 片区还剩 1 格可做（plot_pending），但当日分配内已做净（其中诚实上限延后 0 格）⇒ 不计 unmet`、`[fall 10] 账本 deferred_tiles=1 与按阶段自算 0 不一致（供复核）`、`[fall 11] 账本没写 dry_dead ⇒ 死苗口径无法判定`、`三腿覆盖：清障/开垦 全程 0 步成功`、`三腿覆盖：播种 全程 0 步成功`，以及 **`journal 里没有 finish 事件 ⇒ 判决为临时`**。
- **`tools\analyze-longrun.py --window 3` ⇒ rc=1**（`logs\runB-0732-analyze.txt`）：命中 `day_end.checks.watered_outdoor / final_water` **2 白做**、`no_work…+dry>0` 1、`no_unmet_stages` 1、`day_after` 1、`unreachable`/`refused` 各 5、`verified=True 但 Σok==0` 2 等规则条目（**同样因无 `finish` 只作旁证**）。
- **`scratch\run9-lead-check.py --journal … --snapshots scratch\runB-0732-external-snapshots.jsonl --smapi logs\runB-0732-smapi-window.txt` ⇒ rc=1**：`[3]` SMAPI 配对 `NewDay 8 / before save 8 / Save called 8 / completed 8`（**已排除 1 行插件描述行**，行号 `[892,1681,2475,3274,4072,5148,6088,7604]`）；`[4]` **自述 vs 自算 2/2 ✅**（fall 9 `0↔0 / 41↔41`、fall 10 `89↔89 / 30↔30`）；`[5]` 尾部窗口**只有 2 天，不足 3 天 ⇒ 未达标 ❌**；`[6]` **`finish: 没有（跑批未收尾或被中断）⇒ 无法判定（不是通过）`**。

## §5 存档链与观测计数

| 事件 | 存档主文件 | `SaveGameInfo` |
|---|---|---|
| B 起点（游戏自行推进产生） | `4248971 / 04:25:17.592` | `28867` |
| 跨日 1（fall 9→10） | `4260239 / 04:37:29.117` | `28759 / 04:37:29.118` |
| 跨日 2（fall 10→11） | `4281756 / 04:49:43.856` | `28760 / 04:49:43.857` |
| 现盘 `_old` | `4260239 / 04:37:29.117` | `28759 / 04:37:29.118` |

⇒ 两次跨日**各落盘一次**，与 §3 的六串 2/2 一致；被叫停的 `fall 11` 没有新落盘（`day_end` 不存在）。
外部快照：`scratch\runB-0732-external-snapshots.jsonl` 两行（`start @04:30:18`：`save_main 4248971/04:25:17.592`、`smapi_lines 5619 / newday 6 / before 6 / save_called 9 / task 6 / completed 6`；`end @04:57:04`：见 §0.1）。
**独立观测 `scratch\runB-0732-observe-*.json` 共 25 份**：`fall9` **9 份**（04:31:07–04:36:55）、`fall10` **16 份**（04:37:35–04:49:32）⇒ **两天的"每日 ≥2 份"硬要求都满足**（这正是 run A 前半段没做到的）。

## §6 世界差分表

`logs\runB-0732-diff.txt`（**6384 字符**，`scratch\run9c-diff.py --prefix runB-0732-observe-`）：

| 游戏日 | 观测数 | 端点（首→末） | location | 同格 `kind` 迁移 | `farm.*` 变化 | player | 种子叠 | 新增 crop 格 |
|---|---|---|---|---|---|---|---|---|
| fall9 | 9 | `04:31:07` → `04:36:55` | Farm→Farm ✅ | `weed→dirt×1`（例 `(63,38)`）；窗口 `+53/−53` | `crops 111→102`、`hoeDirt 156→157`、`emptyDirt 45→55`、`weeds 469→468`、`trees 676→674`、`grass 1022→1011` | 体力 `245.30→243.40`、钱 `0→0` | `(O)483: 1→1` | **0 格** |
| fall10 | 16 | `04:37:35` → `04:49:32` | `FarmHouse→Farm`（端点 A 是室内 `tiles=1`） | 无同格迁移（窗口 `+400/−1`） | `dryCrops 102→1`、`grass 1028→1017` | 体力 `270→78.10`、钱 `0→0` | `(O)483: 1→1` | 【无法判定】（schema 无 crop 字段） |

**结论**：fall 9 是唯一**双 Farm 端点**且能复核的差分日（`weed→dirt×1`，即当天清障只实清 1 格）；fall 10 因端点 A 落在室内而**不可比**；`[60,29]` 的"熟了摘不到"在两天里**完全不体现在 `farm.*` 计数上**（`crops 111→102→102`、`dryCrops 102→1→0`），只体现在账本自述的 71 次 harvest 失败里 ⇒ **世界差分再次证明"账本自述不能代替观测"**。

## §7 保留物 · 不确定项 · 诚实声明

**保留物**：`logs\longrun-runB-0732.{jsonl,pid,version.json,console.log,console.err.log}`、`logs\runB-0732-{smapi-window.txt,verify.txt,analyze.txt,lead-check.txt,diff.txt,compare.txt}`、`scratch\runB-0732-{external-snapshots.jsonl,tile6029-live.json,status-044254.json,observe-*.json}`、`scratch\runB-{pre,status,stop-point,tools,compare}.py`、`logs\longrun-runB-0732-lessons.json`（**不得删改**）。

**不确定项**：

1. **run B 没有 `finish`** ⇒ 两侧工具的判决都是"临时"，本文件不把它当验收依据（`lead-check` 已明示"无法判定，不是通过"）。
2. run B 的 fall 10 端点 A 是 `FarmHouse` 观测 ⇒ 该日 tile 差分不可比（已在 §6 标注）。
3. `fall 9` 当天 `ok_steps=0` 却 `zero_action_evidenced=false` ⇒ **守卫没有为"0 步成功的一天"落下零动作标记**（与 fall 10 的 `zero_action_evidenced=true` 形成对照），这条留给 harvest/守卫相关任务（task-169 现场）。
4. `deferred_tiles=1` 与按阶段自算 `0` 不一致；`assigned_undone=1` 无 `stage_shortfall_day` 落痕 ⇒ 无法交叉核对。
5. **L1 口径冲突（已裁定：工具误报，已修 `2e3289e`）**：旧版 `compare-runs.py` 报"0/6 条教训文本命中"、`injection_effective=false`；根因是 `lesson_text()` 只认 `lesson/text/summary/note/why/reason`，而 brain 写进 `<journal>-lessons.json` 的字段是 `id/symptom/evidence/hint/count` ⇒ 取不到值后退化成"把所有字段拼成长串"，永远不可能命中。修正后 = **4/6 命中 + 教训节抬头 ✅ + L1 ✅**，与我的直查同向：`llm.jsonl` **47/47 条 `decision` 的 prompt 都含「教训」节**（唯一不含的是 1 条非决策 `review`）。**L1 成立；L2 及以下仍不可用（见 §8.4）。**

**诚实声明**：run B 是**提前叫停的无效对照臂**（0/2 天 VERIFIED、无 `finish`）；本文件**不据此宣称"有进化"也不宣称"没有进化"**；`[60,29]` 现场已按 Lead 要求另存（`scratch\runB-0732-tile6029-live.json`）。

**收尾后续（Lead m02500 之后补记）**：脑进程停在 `fall 11 tod 700`（人站在 `Farm[60,28]`）之后**游戏继续自行走时钟**，到 `05:04:35` 已自动跨过一次夜 ⇒ 退出前存档 = **`Wahaha_450799035` 4310486 B / `2026-10-17 05:04:35.296`**（`SaveGameInfo` 28707 / `05:04:35.298`；`_old` = 4281756 / `04:49:43.856`、`SaveGameInfo_old` 28760 / `04:49:43.857`）。随后按 m02833 用 `tools\stop-game.py` **优雅退出**（rc=0、`✅ 游戏已退出（原 pids=[20672]）`）：进程 **0** / `bridge.json` **已删** / 17890 **无 LISTENING（2 条 TIME_WAIT）** / 存档四条**退出前后逐字未变**。⇒ **将来重开读档时的起点是夜里自动推进后的那一天**（`fall 12` 06:00 一带，不是 `fall 11`），`[60,29]` 的熟作物样本仍在存档里、可直接做 harvest 修复后的同格对照。

## §8 A/B 对照（结论：**L0/L1 成立；L2 及以下不可用**）

### 8.0 世界可比性背景（比较前必读）

| 项 | run A 起点 | run B 起点 |
|---|---|---|
| 游戏日 | `fall 3`（06:10） | `fall 9`（06:10 起跑、tod 820） |
| 体力 / 钱 | `136 / 270`、`20g` | `245.3 / 270`、`0g` |
| 作物 / 未浇 / 干 | `125` / `125` / `dry 125` | `117` / `5` / `dry 0` |
| `farmingLevel` | 0 | **1** |
| 观测覆盖 | fall 3/5 各 1 份、fall 4 为 0 ⇒ 世界差分大半无法判定 | fall 9 = 9 份、fall 10 = 16 份 ⇒ 达标 |

⇒ **B 的起点比 A 干净得多（dry 0 vs 125）**，且 A→B 之间游戏自行推进了 6 个游戏日（含一次升级）。**这行背景必须与 L2 以下同读；不得把它当作"B 更差/更好"的因果。**

### 8.1 `[5] run A 教训库 → run B 提示词命中`（**修正后原文**）

> **旧版"0/6 + 教训根本没送到"是工具误报，已由 Lead 裁定并修复（commit `2e3289e`）**：根因 `tools\compare-runs.py` 的 `lesson_text()` 只认 `lesson/text/summary/note/why/reason`，而 brain 写进 `<journal>-lessons.json` 的字段是 `id/symptom/evidence/hint/count` ⇒ 取不到值后退化成"把所有字段拼成长串"，自然不可能是提示词子串。修法：按渲染顺序取键（`hint` 优先）做子串命中、新增 `lesson_full_text()`（症状+证据+自述）供 L3 同指涉词表用、新增教训节抬头结构性核对 `LESSON_SECTION_MARK = "从过去几天的账本里总结的教训"`、命中 0 但节在只报「比对口径警告」、`tests\test_compare_runs.py` 加 6 条回归用例（`Ran 23 tests … OK`）。**我的直查（`llm.jsonl` 47/47 条 `decision` 的 prompt 含「教训」节）是对的，工具错了。**

```
[5] run A 教训库 → run B 提示词命中
  教训库 D:\Deepseek Harness Workspace\星露谷游戏自动化\logs\longrun-runA-0732-lessons.json：6 条
   1. [✅ 进提示词] 体力已归零，明天别一早就硬撑，留出回程和补给的余量。
   2. [❌ 未见] 西北那片地进场先收成熟作物，今天有一次采收没摘到；摘完再看其他田区，别被同一格卡住。
   3. [❌ 未见] 西北那片地进场先收成熟作物，今天有一次采收没摘到；摘完再看其他田区，别被同一格卡住。
   4. [✅ 进提示词] 体力已归零，明天别一早就硬撑，留出回程和补给的余量。
   5. [✅ 进提示词] 体力已归零，明天别一早就硬撑，留出回程和补给的余量。
   6. [✅ 进提示词] 体力已归零，明天别一早就硬撑，留出回程和补给的余量。
  ⇒ 4/6 条教训文本出现在 run B 的 72 次 LLM 调用提示词里（子串比对；注入后被裁掉的部分算未见）
  教训节抬头「从过去几天的账本里总结的教训」在 run B 提示词里：✅ 出现
```

**三键口径（`--json logs\runB-0732-compare.json` 实测）**：`lessons_total = 6`、`lessons_hits = 4`、`injection_effective = true`、`lesson_section_present = true`（另有 `b_prompt_calls`）。
**逐条判读**：命中的 4 条是同一句 `hint`（"体力已归零…"），未中的 2 条是 `stuck_with_leftover|plant_area` 与 `|till_area` 的 `hint`（"西北那片地进场先收成熟作物…"）⇒ 更像**按需筛选**（该形态当天不是当前决策的教训）而非长度裁切；已请 dev-coder 核对渲染选择规则（`lesson_section_present=true` 已排除"节没进去"）。

### 8.2 `[6] 演进判据（L0–L5）`（**修正后原文**，工具修于 `2e3289e`；L3 六行不变，仍是 0 次同指涉）

```
[6] 演进判据（L0–L5，机械可算部分 + 旁证）
  L0 run A 有教训库（≥1 条）            : ✅  (6 条)
  L1 教训确实进了 run B 提示词          : ✅  (4/6 命中，run B 72 次调用)
  L2 同形态在 run B 减少                : ✅
       · stuck_with_leftover  ended_by:stuck               runA-0732=0 → runB-0732=0  ✅ 减少
       · stuck_with_leftover  ended_by:stuck               runA-0732=0 → runB-0732=0  ✅ 减少
       · stuck_with_leftover  ended_by:stuck               runA-0732=0 → runB-0732=0  ✅ 减少
       · stage_incomplete     （无可数信号，需人工看账本）
       · dead_crops_blocking  （无可数信号，需人工看账本）
       · stuck_with_leftover  ended_by:stuck               runA-0732=0 → runB-0732=0  ✅ 减少
  L4 无回归（尾部 VERIFIED 不降 + 无新失败类）: ❌  尾部 runA-0732=0 → runB-0732=0；新增失败项 ['zero_action_evidenced']
  L3 决策受影响的旁证（需人工确认）    :
       · 决策理由里同指涉出现 0 次 ｜ stuck_with_leftover|harvest / stuck_with_leftover / harvest / harvest 收尾时还剩 1 格没做成、当天以 stuck 结束
       · 决策理由里同指涉出现 0 次 ｜ stuck_with_leftover|plant_area / stuck_with_leftover / plant_area / plant_area 收尾时还剩 1 格没做成、当天以 stu
       · 决策理由里同指涉出现 0 次 ｜ stuck_with_leftover|till_area / stuck_with_leftover / till_area / till_area 收尾时还剩 4 格没做成、当天以 stu
       · 决策理由里同指涉出现 0 次 ｜ stage_incomplete|harvest / stage_incomplete / harvest / harvest 有 1 格没做成，还剩 1 格 / failed=1 leftover=1
       · 决策理由里同指涉出现 0 次 ｜ dead_crops_blocking|farm / dead_crops_blocking / farm / 枯死作物占着地，浇水和当天验收过不去 / dead_crops=1 dry_dead=0
       · 决策理由里同指涉出现 0 次 ｜ stuck_with_leftover|water_area / stuck_with_leftover / water_area / water_area 收尾时还剩 46 格没做成、当天以 stuck 结束
  L5 结论：有演进痕迹，但 run B 未达标（尾部连续 VERIFIED 天数不足）

  ⚠ 本工具的 L 判据只做机械对照；「自我进化」的正式结论必须并列 `verify-run3`/`analyze-longrun` 的判决与 L3 的人工核对。
```

（本节 L1 已按 `2e3289e` 修正为 ✅ 4/6；L4 的 `zero_action_evidenced` 是 run B 新增失败项，与本跑被 harvest 缺陷支配有关，**不单独归因于教训注入**。）

### 8.3 `[1]`–`[4]` 对照摘要（L2 相关的机械计数）

| 维度 | run A | run B | 说明 |
|---|---|---|---|
| 账本行数 / 已完成日 | 847 / 6 | 723 / 2（无 `finish`） | B 少 3 天且未收尾 |
| `decision`（LLM 行数） | 79（LLM 75） | 73（LLM 70） | llm-trace 行 81 / 72 |
| 阶段成功格数 | `water_area 260`、`till_area 12`、`plant_area 3`、`clear_dead 1` | `water_area 89`、其余 **0** | B 的 clean/plant 腿两天全 0 |
| 阶段失败/异常收尾 | `harvest 79`、`water_area 4` | `harvest 71`、`water_area 1` | 两跑都被 harvest 支配 |
| 被校验取消的意图 | `plant_area 2 / till_area 2 / clear_area 2 / water_area 1` | `plant_area 3 / till_area 2 / clear_area 1` | 量级相当 |

（完整 [1]–[4] 表格见 `logs\runB-0732-compare.txt`，本表只抄要点，避免与原文重复。）

### 8.4 结论（按 Lead m02439 口径）

- **L0 成立**：run A 有教训库（6 条 `logs\longrun-runA-0732-lessons.json`）。
- **L1 成立（Lead 已裁定：直查对、工具错）**：run B 的 **47/47 条 `decision` 提示词含教训节**；工具修正后为 **4/6 条教训文本命中 + 教训节抬头 ✅**（`lessons_total 6 / lessons_hits 4 / injection_effective true / lesson_section_present true`）；`lessons` 文件为**原样字节拷贝**（`3220 B`，两侧 SHA256 `C42AF6BE…D642` 一致，拷贝时刻 `2026-10-17T04:25:53+0700`）。旧版 `injection_effective=false` 是 `lesson_text()` 字段口径错误导致的误报，已修 `2e3289e`。
- **L2 及以下不可用**：B 臂被 `harvest` 缺陷支配（fall 9 一天 `ok 0 / fail 41`；fall 10 持续同一格打转，`[60,29]` 跨两次跨日仍 `ripe` 未摘），叠加 A→B 的世界差异（起点 `dry 125 → dry 0`、多推进 6 个游戏日、`farmingLevel 0→1`）构成**世界差异 + 代码缺陷的双重混淆** ⇒ **不据此宣称"没有进化"，也不宣称"有进化"**，只记事实：`finish` 缺失、尾部 0/2、L4 反而多出 `zero_action_evidenced` 一项。
- **本跑最有价值的产出不是 A/B 对照，而是 `[60,29]` 这一格的现场**（§0.2）：窗口内、`standable/actionable/watered/ripe` 全真、玩家就在正邻居、反复 `postcondition_met=false` ⇒ harvest 修复后可直接做"同格前后对照"（期望 `farm.ripeCrops 1→0`）。
