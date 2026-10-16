# run9d 证据（task-147 · run A · 5 日自主运行）

> **状态行**：**已结束 · FAIL（尾部连续 VERIFIED 0/5、`finish.code=1`）**；2026-10-17 01:32:58 起跑 → 02:11:38 finish，共 **38.26 分钟 / 827 动作 / 9 个日报告**（summer 23 → fall 3）。被测版本 **0.7.31（`24a8ce7`）**，脱离式 PID **936**。
> **判据口径**：`docs/_run6-criteria.md` §2（尾部窗口）+ 本卡"尾部 5 天全 VERIFIED"；**不采用** `day_end.final.location=="Farm"`（已废弃）；世界差分只认 `observe?detail=full` 差分，**回执只作旁证**。
> **结论一句话**：机器侧机制全部按设计工作（六串落盘 8/8、checker 与自述 9/9 一致、task-133/149/102 三条新护栏真机生效），但**世界状态层面"作物规模 > 单日体力预算"**导致 25 日起干燥作物越积越多、末日 0 动作睡到 2400 被拦；**run A 未能建立 5 连基线**，run10 的 A/B 对照需要 0.7.32（task-155/157/158/20）修复后再做。

---

## §1 起跑与版本四要素

| 项 | 读数 |
|---|---|
| `git rev-parse HEAD` | `24a8ce79dc49ac0564994c5ed7e7b43a1f2abffd`（0.7.31 冻结提交） |
| `git status --short`（sidecar 记录） | `[]`（`worktree_clean=true`） |
| 起跑器版本 sidecar | `logs/longrun-3day-llm-run9d.version.json`（45 行，`boundary_llm=true`、`pid=936`、`started_at=2026-10-17T01:32:58`） |
| `brain/agentfarm/longrun.py` | SHA256 `86BC4D5CFEF5F58DF864928C1563A397C60371EC319FE85322107A5EFDD9F2DB` / mtime `2026-10-17T01:08:47.088887` |
| `brain/agentfarm/farmwork.py` | SHA256 `4A39BC11ABCA3413D1608CCD58CC1F070CEA9F85EAB4AA87E809ED5E686C2D80` / mtime `2026-10-16T21:45:23.956930` |
| `brain/agentfarm/bridge.py` | SHA256 `F2DE967CBBE21750AD1900E1A467877AE79ED640749488153EB983C885EABF85` / mtime `2026-10-17T01:29:47.210537` |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | SHA256 `02755488A532BA3D163010BAF985029B35B31C682D5AC025A9AD2E68D86297C7` / mtime `2026-10-17T01:30:04.824789` |
| `mod/AgentFarm.Bridge/manifest.json` | SHA256 `0E1F214D060E602510F6BE2224A8F8AD9BB90DFB727B058FA4B98D9CE97FA471` / mtime `2026-10-17T01:29:11.495458` |
| `StartTime` vs `longrun.py` mtime | 进程 `2026-10-17T01:32:58` **晚于** `01:08:47` ⇒ ✅ 加载的是冻结版 |
| 桥 | `bridge.json`：`pid 6456` / `modVersion 0.7.31` / `port 17890` / `gameVersion 1.6.15` / `smapiVersion 4.5.2` / `startedAt 2026-10-16T18:31:01+00:00`；快照内 `mod_version_matches=true` |
| 起跑命令（sidecar `argv` 原文） | `python -u tools/run-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12 --journal logs/longrun-3day-llm-run9d.jsonl` |

**两份基线（都保留）**：权威基线 = Lead 手写 `logs/run9d-baseline.json`（`夏23日 06:40 / sunny / Farm(64,15) / 体力 270 / 钱 265g / 背包 Wheat Seeds / 作物 103 / unwatered 24 / dryCrops 103 / waterLeft 18 / tillable 84 / 无模态 / worldAdvancing true`）；起跑器另写了一份 `logs/longrun-3day-llm-run9d-baseline.json`（`tod 810→820`），**来源不同、数值不同属预期**，本文件以 Lead 那份为准。**不做操作员预置**（卡面要求）。

## §2 起止快照与存档链

快照文件：`scratch/run9d-external-snapshots.jsonl`（2 行，`run9d-snapshot.py` 写出；end 行显式传了 `--pid-file logs\longrun-3day-llm-run9d.pid`）。

| 快照 | 时刻 | save_main | save_info | SMAPI 行 / NewDay / before / called / task / completed | journal | PID |
|---|---|---|---|---|---|---|
| start | `2026-10-17T01:34:28` | 3860602 B / `2026-10-17T00:16:44.786` | 28884 B | 672 / 0 / 0 / **2** / 0 / 0 | 10 行（`refill_retry`） | 936 / alive |
| end | `2026-10-17T02:11:38` | **4103808 B / `2026-10-17T02:11:33.121`** | 28765 B / `02:11:33.122` | **8071** / 8 / 8 / 10 / 8 / 8 | 378 行（`finish`） | 936 / **not alive** |

> `start` 的 `save_called=2` 是**窗口外** deploy 的 `load_save` 留痕；`end` 的 `save_called=10` 比真实多 2（1 行 L16 插件描述假阳性 + 窗口内另一次非跨日保存，见 §3 的"原始 vs 修正"）。

**每跳存档（我轮询实测的 main 文件；未取到的跨日不编造）**

| # | 跨到 | save_main size / mtime |
|---|---|---|
| — | 起跑前 | 3860602 / `00:16:44.786` |
| 1 | summer 24 | 3919333 / `01:39:21` |
| 2 | summer 25 | 3948402 / `01:42:40` |
| 3 | summer 26 | 3988589 / `01:48:25` |
| 4 | summer 27 | 3997525 / `01:54:04` |
| 5 | summer 28 | 3969050 / `02:01:48` |
| 6 | fall 1 | （轮询间隔未取到） |
| 7 | fall 2 | 4083244 / `02:08:37`（现为 `_old`） |
| 8 | fall 3 | **4103808 / `02:11:33.121`**（现为 main） |

⇒ **8 次跨日 8 次落盘**（与 §3 的 8/8/8/8/8/8 一致；run9 的"4 NewDay / 0 save"形态**没有复现**）。

## §3 SMAPI 窗口与六串配对

- 冻结文件：`logs/run9d-smapi-window.txt` = **595212 B / 8071 行 / mtime `2026-10-17T02:11:35` / SHA256 `E1340346E09344527E6F5484B86589126E755CB98AEE0884C39252627139DC0E`**（与源 `SMAPI-latest.txt` 逐字节一致）。
- 计数窗口：`01:32:58 – 02:11:45`，带时间戳行 **7649**（文件总行 8071）。

| 串 | 次数 | 行号 |
|---|---|---|
| `Synchronizing 'NewDay' task` | **8** | 1355, 2035, 3224, 4335, 5654, 6456, 7277, 8049 |
| `Context: before save.` | **8** | 1358, 2046, 3235, 4338, 5665, 6467, 7280, 8065 |
| `SaveGame.Save() called.` | **8**（修正后） | 1359, 2047, 3236, 4339, 5666, 6468, 7281, 8066 |
| `Synchronizing 'Save' task` | **8** | 1360, 2048, 3237, 4340, 5667, 6469, 7282, 8067 |
| `completed without exceptions` | **8** | 1363, 2051, 3240, 4343, 5670, 6472, 7285, 8070 |
| `after save, starting` | **8** | 1364, 2052, 3241, 4344, 5671, 6474, 7286, 8071 |

**`save_called` 原始 vs 修正**：原始 **9** / 修正 **8**。差异行 **L16** 逐字为
`[01:31:01 INFO  SMAPI]    AgentFarm Bridge 0.7.31 by AgentFarm | v0.7.31（run9c 诊断后的口径修复：…）` —— 插件描述行被字符串匹配命中。判别式（task-127）：**有 `[HH:MM:SS LEVEL CHANNEL]` 前缀 且 不含 ` by AgentFarm ` / `| v0.`**。

**噪声（窗口内全 0）**：`ERROR` / `Disconnected` / `ClosedGame` / `Disposing` / `soft_oal` / `Exception` = **0/0/0/0/0/0**。
**`Warping to Farm` = 2200**（task-14 的逐帧活锁仍在，本卡只作信息项）。

## §4 逐日表与三个检查器

### 4.1 逐日表（9 个日报告，账本原文）

| 游戏日 | ended_by | verified | ok/skip/fail | `final_water` dry / crops | 未过的判据 | `ended_reason` |
|---|---|---|---|---|---|---|
| summer 23 | sleep | **True** | 115/1/0 | 0 / 105 | — | `stamina:体力 10 < 12` |
| summer 24 | sleep | **True** | 46/0/0 | 0 / 127 | — | `no_work`（真空日，`dry=0` ⇒ 合法） |
| summer 25 | sleep | False | 115/2/0 | **1** / 126 | `watered_outdoor`,`day_justified` | `gave_up_dry:…还有 1 格干作物…坐标 [[12, 30]]…已放弃当天，不再空转` |
| summer 26 | sleep | False | 103/0/0 | 0 / 151 | **`day_justified`** | `stuck:回片区（work_spot_resume）连续 5 次都拿不出目标（守卫仍说还有活：今天早些时候还有 11 格没做完（跨片地，最近的是 [60, 32]））` |
| summer 27 | sleep | False | 104/0/0 | **17** / 148 | `crops_watered`,`watered_outdoor` | `stamina:体力 0 < 12` |
| summer 28 | sleep | False | 65/0/0 | **79** / 147 | 同上 | `stamina:体力 0 < 12` |
| fall 1 | sleep | False | 68/2/0 | **140** / 146 | 同上 | `stamina:体力 0 < 12` |
| fall 2 | sleep | False | 65/0/0 | **73** / 142 | 同上 | `stamina:体力 0 < 12` |
| fall 3 | **slept_without_work** | False | 0/0/0 | 73 / 142 | `slept_by_us`,`crops_watered`,`watered_outdoor`,`day_justified`,**`zero_action_evidenced`** | `night:时间 2400 已经到夜里（≥2200）` |

`day_after` 链：23→24→25→26→27→28→fall1→fall2→fall3（**8/8 恰好 +1**）；fall 3 `day_after=null`（未跨日）。
`finish` 原文：
```json
{"event": "finish", "t": 2295.61, "code": 1, "verified_streak": 0, "actions": 827, "minutes": 38.26,
 "stages_seen": ["clear_area", "clear_dead", "plant_area", "till_area", "water_area"],
 "no_unmet_stages": true, "unmet_days": [], "stuck_flushes": 0}
```
`fall 3` 拦停原文（task-102 生效）：
```json
{"event": "slept_without_work", "t": 2295.6, "why": "night:时间 2400 已经到夜里（≥2200）", "farm_actions": 0,
 "reasons": ["有 1 格作物没浇水", "farm 口径还有 23 格耕地空着（手上有 2 粒种子）⇒ 该去种",
             "农场口径还有 73 格干作物，其中 63 格在玩家窗口之外（Mod 报的坐标 [[54, 15], [56, 15], [57, 15]]） ⇒ 先走过去浇",
             "field_nw还有地要清/开/种"],
 "note": "0 农场动作就睡 = 用睡觉跳过整天的活（run8 day 12 形态）；本日不推进、按 needs_review 停在这里"}
```
随后 `{"event": "no_day_progress", "t": 2295.61, "day": [1, "fall", 3], "ended_by": "slept_without_work", "reason": "night:时间 2400 已经到夜里（≥2200）"}`。

### 4.2 `tools/verify-run3.py --journal logs/longrun-3day-llm-run9d.jsonl --days 5`（原文落 `logs/run9d-verify.txt`，410 行）

- **rc=1**；`"verdict": "needs_review"`、`"strict_verdict": "needs_review"`、`"strict_problem_count": 26`、`"history_problems": []`、`rows 378`、`finish_present true`、`bad_lines 0`。
- `problems` 数组 26 条**逐条原文**（节选全部 26 条，完整见文件 L333–360）：
  `[summer 25] checks.watered_outdoor=false`、`[summer 25] day_end verified=false`、`[summer 26] day_end verified=false`、`[summer 27] checks.watered_outdoor=false`、`[summer 27] 睡前 unwatered_crops=14（窗口口径，要求 0）`、`[summer 27] checks.crops_watered=false`、`[summer 27] day_end verified=false`、`[summer 28] checks.watered_outdoor=false`、`[summer 28] 睡前 unwatered_crops=50`、`[summer 28] checks.crops_watered=false`、`[summer 28] day_end verified=false`、`[summer 28] 0 目标阶段 leftover=3（task-15 修 A 后应为 0；请查 stage_no_target 分支）`、`[fall 1] checks.watered_outdoor=false`、`[fall 1] 睡前 unwatered_crops=64`、`[fall 1] checks.crops_watered=false`、`[fall 1] day_end verified=false`、`[fall 2] checks.watered_outdoor=false`、`[fall 2] 睡前 unwatered_crops=61`、`[fall 2] checks.crops_watered=false`、`[fall 2] day_end verified=false`、`[fall 3] ended_by=slept_without_work（不是我们主动睡过去的）`、`[fall 3] checks.watered_outdoor=false`、`[fall 3] 睡前 unwatered_crops=1`、`[fall 3] checks.crops_watered=false`、`[fall 3] day_end verified=false`、`journal 里出现 跨日没有推进 ×1`。

### 4.3 `tools/analyze-longrun.py --journal … --window 5`（原文落 `logs/run9d-analyze.txt`，36670 字符）

**rc=1**。命中摘要（原文行）：`no_day_progress 1`（日级：这天没有任何进度，`slept_without_work`）、`watered_outdoor 缺失 1 / 白做（true 与 dry>0 互斥或 scope 不可采信）2`、`ended_reason=no_work… + final_water.dry>0` **1**（task-60 红线）、`day_end.checks.no_unmet_stages 1`、`day_end.day_after 1`、`verified=True 但 Σ stage.ok==0` **0**、`env_fail / env_spin_capped / inconclusive_fail` 各 **5**、`unreachable` **5** 与 `tool_refused/refused` **5**（两套独立豁免，均"不计当天硬失败"）、`review.work_reasons 4`、`intent_vetoed 4`、必须人工介入（红）**0**。

### 4.4 `scratch/run9-lead-check.py --journal … --snapshots scratch\run9d-external-snapshots.jsonl --smapi logs\run9d-smapi-window.txt`（原文落 `logs/run9d-lead-check.txt`）

**rc=1**，六段摘要：
1. `合计 跨日 8 次，其中恰好 +1 的 8/8`
2. 存档链：`tag=start … save_main[3860602 / 00:16:44.786] mod_version_matches=True`；`tag=end … save_main[4103808 / 02:11:33.121] mod_version_matches=True`
3. SMAPI 配对：`NewDay 8 / before save 8 / Save called 8 / completed 8`，`已排除 1 行插件描述行（含 ' by AgentFarm '/'| v0.' 标记，假阳性防护，task-127）`，行号同上
4. 自述 vs 自算：**9/9 ✅**（每天 `ok_steps == Σ stages[].ok`、`failed_steps == Σ failed`）
5. 尾部窗口（最后 3 天）：`fall 1`/`fall 2` 未过 `crops_watered, watered_outdoor`；`fall 3` 未过 5 项 ⇒ **结论：未达标 ❌**
6. `finish: code=1 streak=0 actions=827 minutes=38.26 no_unmet_stages=True`

## §5 判据逐条对账 + 世界差分

### 5.1 卡面判据

| 判据 | 结果 | 读数 |
|---|---|---|
| **尾部 5 天全 VERIFIED**（目标 2 / L4 基线） | ❌ | 连续 VERIFIED **0/5**（25 起断） |
| 每天 `ended_by=="sleep"` | ❌ | fall 3 是 `slept_without_work`（被 task-102 拦下，未跨日） |
| 六串落盘配对 | ✅ | 8/8/8/8/8/8（§3）；8 次跨日 8 次落盘 |
| 存档 size/mtime 前进 | ✅ | 3860602 → 4103808（§2） |
| `day_after` 恰 +1 链 | ✅ | 8/8（fall 3 无跨日） |
| 不可达/被拒**不判硬失败**（task-52/63） | ✅ | 账本与自算一致；`bound` 逐日 5–39，`exempt` 0–1 |
| 无 `bridge_down`/`watchdog_stop`/崩溃 | ✅ | SMAPI 窗口 `ERROR/Disconnected/ClosedGame/soft_oal` 全 0；`err.log` 全程 0 B |
| 每日 ≥2 份独立 Farm 观测（世界差分） | ⚠ 部分 | 17 份，但 23/24/25/28/fall2 **各只有 1 份**（缺口见 §6，不补造） |
| 经济闭环四腿（sell→到账→buy→plant） | ⚠ 部分 | `sell 4` + `surplus_sell 4`（`why=need_slot`）、`buy 9`（含 `buy_partial 4`、`cannot_afford 1`、`seed_unavailable_today 1`）、`plant_area` 多天有 ok；⚠ **`money` 在 265→6 之间震荡后归 0**（规模扩张吃掉了现金） |
| NIT-2（`emptyDirt>0` + 有种子却拿不出目标却仍 VERIFIED） | ✅ 未触发 | 无此类日子（summer 24 是真空日但 `dry=0`） |

### 5.2 世界差分表（`scratch/run9c-diff.py … --out logs/run9d-diff.txt`，14747 字符；判据 = 独立观测差分，账本只作旁证）

| 游戏日 | 观测数 | 端点（文件名·时刻） | kind 迁移 | `farm.*` 变化 | `player` | 种子叠 | 新增 crop 格 |
|---|---|---|---|---|---|---|---|
| summer23 | 1 | 单份 | 【无法判定】 | 无 | 体力 98（不变）钱 165 | `(O)483: 10→10` | 0 |
| summer24 | 1 | 单份 | 【无法判定】 | 无 | 体力 246 钱 5 | `6→6` | 0 |
| summer25 | 1 | 单份 | 【无法判定】 | 无 | 体力 128 钱 6 | `2→2` | 0 |
| summer26 | 2 | `summer26@01:49:45`(Farm) → `summer26-b@01:54:06`(FarmHouse) | 窗口 +1/−400（位移，不可区分） | crops 127→0、hoeDirt 229→0、weeds 437→0…（**室内窗口**，不可用） | 体力 246→270 钱 146→6 | `10→0` | 0 |
| summer27 | 4 | `summer27@01:56:08` → `summer27-d@02:00:32`（**都在 Farm**） | 同格 0；窗口 +169/−169 | **crops 151→148**、**dryCrops 94→38**、emptyDirt 102→105、grass 847→841 | **体力 154→44**、钱 6（不变） | 无 | **新增 26 格**（示例 (43,24)(64,30)(64,31)(64,32)(65,30)） |
| summer28 | 1 | 单份 | 【无法判定】 | 无 | 体力 128 钱 0 | `2→2` | 0 |
| fall1 | 2 | `fall1@02:04:53`(FarmHouse) → `fall1-b@02:06:55`(Farm) | 窗口 +400/−1 | crops 0→143、dryCrops 0→116、deadCrops 0→**1**、dryDeadCrops 0→1、hoeDirt 0→166、weeds 0→441、stones 0→110、twigs 0→70、trees 0→617、grass 0→892 | 体力 136→82、钱 20 | `2→2` | 【无法判定】schema 无 crop 字段 |
| fall2 | 1 | 单份 | 【无法判定】 | 无 | 体力 134 钱 20 | `2→2` | 0 |
| fall3 | 4 | `fall3-b@02:11:20` → `fall3-d@02:11:22`（都在 Farm，间隔 2 秒） | 同格 0；窗口 +0/−0 | 无（2 秒内的空转终点） | 体力 136 钱 20 | `2→2` | 0 |

**能不看账本复核的行**：summer 27 一行（两个文件、两个字段、差值）——`scratch/run9d-observe-summer27.json` 的 `farm.dryCrops=94` → `scratch/run9d-observe-summer27-d.json` 的 `farm.dryCrops=38`，**当日真的浇掉了 56 格干作物**，同时体力 154→44；`farm.crops` 151→148（旱死 3 株）。**【无法判定】6 条**：summer 23/24/25/28/fall2 各缺第 2 份 Farm 观测；fall1 的"新增 crop 格"因 schema 无 `crop` 字段。

### 5.3 结构性诊断（本卡的两条结论，已由 Lead 立卡）

1. **`[12,30]` —— "够不着的活苗干作物"（task-157）**：run9c 时它被记成 `need_refill`，0.7.31 起判成 `unreachable`（task-133 生效）；本跑 summer 25 因此 `gave_up_dry`、`dry=1` ⇒ **阴雨天它被雨浇到（summer 23/24 全绿）、不下雨就必破尾链**。
2. **作物规模 > 单日体力预算（task-158）**：`farm.crops` 105→151，日体力固定 270；阶段补水（task-133/144）只补**壶**不补**人** ⇒ `dry` 17→79→140（`clear_dead` 清枯苗后回落 73）**单调恶化**，`money` 265→6→0。末日体力耗尽后 0 动作睡到 2400，`slept_without_work` + `no_day_progress` 拦下（**task-102 生效**）。
3. **task-149 生效证据**：`t=923.98 goto_farm{where:"day_start"} failed [ui_modal]` → `t=938.47 goto_farm{where:"day_start_retry"} ok=true`（日初被模态挡住后真的重试一次）。
4. **新判据名 `zero_action_evidenced`** 在 fall 3 首次真机出现，与 `slept_without_work` 一起把"0 动作睡过去"挡在 VERIFIED 之外。

## §6 独立观测清单（每天 ≥2 份的硬要求；缺口如实列出）

`scratch/run9d-observe-*` 共 **17 份**（`run9c-observe.py --naming alpha` 逐日命名、**同名绝不覆盖**）：

| 日 | 份数 | 文件（时刻 / 地点 / `worldSeq`） |
|---|---|---|
| summer 23 | **1 ⚠** | `summer23.json`（01:36:25 / Farm / 484） |
| summer 24 | **1 ⚠** | `summer24.json`（01:40:48 / Farm / 898） |
| summer 25 | **1 ⚠** | `summer25.json`（01:45:58 / Farm / 1467） |
| summer 26 | 2 | `summer26.json`（01:49:45 / Farm / 1872）、`summer26-b.json`（01:54:06 / **FarmHouse** / 2203） |
| summer 27 | 4 | `summer27.json`（01:56:08 / 2408）、`-b`（01:58:09 / 2773）、`-c`（01:58:30 / 2855）、`-d`（02:00:32 / 3301） |
| summer 28 | **1 ⚠** | `summer28.json`（02:02:33 / Farm / 3567） |
| fall 1 | 2 | `fall1.json`（02:04:53 / **FarmHouse** / 3820）、`fall1-b.json`（02:06:55 / Farm / 4154） |
| fall 2 | **1 ⚠** | `fall2.json`（02:08:56 / Farm / 4407） |
| fall 3 | 4 | `fall3-b/-c/-d/.json`（02:11:20–02:11:22 / Farm / 4635） |

**缺口原因（如实）**：23/24/25 三天在上半程，跨日间隔只有 3–6 分钟，我 4–5 分钟一轮的轮询追不上第 2 份；发现后改成"2 分钟一轮 + 每轮前后各抓一份"，26 日起补齐。fall 3 的 4 份是 finish 前 2 秒内的连拍（同一 `worldSeq`，实际信息量 1 份）。**不补造、不重跑**。

## §7 保留物、不确定项与诚实声明

### 7.1 保留物（不删、不改名）

| 文件 | 大小/摘要 |
|---|---|
| `logs/longrun-3day-llm-run9d.jsonl` | 378 行账本（`finish` 在末条） |
| `logs/longrun-3day-llm-run9d.version.json` | 版本四要素 + `argv` + `boundary_llm` |
| `logs/longrun-3day-llm-run9d.pid` / `.console.log` / `.console.err.log` | PID 936 / 控制台 / **err 0 B** |
| `logs/longrun-3day-llm-run9d-lessons.json` | **3712 B / mtime `2026-10-17T02:11:14` / SHA256 `2C4BA15F361005A7C19100FD36A7B48FB56037CD14BF8FFA49838035E4E67885`**（**原样保留、未拷贝、未改名**） |
| `logs/run9d-smapi-window.txt` | 595212 B / SHA256 `E1340346E09344527E6F5484B86589126E755CB98AEE0884C39252627139DC0E` |
| `logs/run9d-verify.txt` / `run9d-analyze.txt` / `run9d-lead-check.txt` | 三个检查器原文 |
| `logs/run9d-diff.txt` | 世界差分表（14747 字符） |
| `scratch/run9d-external-snapshots.jsonl` | start/end 快照两行 |
| `scratch/run9d-observe-*.json` | 17 份独立观测 |
| `scratch/run9d-days.py` / `run9d-tools.py` / `run9d-snapshot.py` | 逐日摘要 / 冻结+三检查器 / 快照包装 |

**教训库 7 条（原文摘要）**：`dead_crops_blocking|farm`（count 3，fall 1→3，severity 3，`dead_crops=1 dry_dead=1`）、`slept_without_work|day`（1，fall 3）、`far_dry_given_up|water_far`（2，summer 25→27，`gave_up=1`）、`stuck_with_leftover|plant_area`（6，summer 23→26）、`stuck_with_leftover|till_area`（5）、`stuck_with_leftover|water_area`（2，`stopped=budget`）、`stuck_with_leftover|clear_area`（1）。⇒ **LLM 复盘已能针对不同 scope 写出不同 `hint`**（如"钱只剩5g，背包里一颗种子也没有，明天先想办法弄钱或留种"），但 4 条 `stuck_with_leftover` 的 hint 仍是同一句"体力要省着用"（**同质化仍未解**，见 §7.3）。

### 7.2 不确定项 / 盲区（缺失 ≠ 通过）

1. **cross 6（summer 28→fall 1）的存档 size/mtime 没测到**（轮询窗口错过）；但 SMAPI 第 6 组六串齐全 ⇒ 落盘成立，只是**具体 size 未知**。
2. **summer 26-b / fall 1 的端点落在 FarmHouse**（`tiles=1`），当天 tile 差分不可用；summer 26 的 farm 计数差是**室内窗口**造成的假差分，已在 §5.2 标注不可用。
3. **`observe?detail=full` 的 `tiles[]` 没有 `crop` 字段** ⇒ "新增作物格"只能靠 `farm.crops` 计数与 stage 记录，**逐格 crop 差分【无法判定】**（summer 27 的 26 格来自 `tiles[]` 的 `kind` 变化，不是 crop）。
4. **`farm.unwateredCrops` 与 `dryCrops` 口径不同**：`unwateredCrops` 恒大于 `dryCrops`（前者含非作业区/枯死），判定只用 `dryCrops`（0.7.27 起只算活苗）。
5. **夜间/睡前的 `isInBed` 与模态状态未逐日留证**（观测按轮询抓取，不是睡前那一瞬）。
6. **`money` 现金流去向只能给区间**：265→165→5→26→246→146→46→6→0/20，中间买卖交替，我没有把每一笔与货架逐笔对齐（`buy` 9 条、`sell` 4 条在账本里，未做逐笔对账）。

### 7.3 诚实声明

- 本次结论 = **run A FAIL（尾链 0/5）**；**没有**为了让尾链好看而改判据、改账本或补造观测。观察到的 17 份观测**原样保留**，缺口写在 §6。
- 机器侧（六串落盘、checker 一致、三条新护栏）**全部按设计工作**；失败来自**世界状态**（够不着的干作物 + 作物规模超过体力预算），已由 task-157 / task-158 覆盖。
- 本文件只写 `docs/_run9d-evidence.md` 与 `scratch/`；**未碰** `brain/`、`mod/`、`tools/`、`tests/`，**未 deploy、未重启游戏、未做操作员预置**。
- run10（run B）未起跑：需等 0.7.32 冻结，且 run B 要先预置 `logs/longrun-3day-llm-run10-lessons.json`（**拷自 run9d 的库**，按 Lead 记账）。

### 7.4 收工后核对（`tools\stop-game.py`，2026-10-17 02:17:19）

| 核对项 | 退出前 | 退出后 |
|---|---|---|
| `StardewModdingAPI` 进程 | 1 个（PID 6456） | **0 个** |
| `bridge.json` | 存在（`pid 6456 / 0.7.31`） | **已删除** |
| 端口 17890 | LISTENING | **0 条 LISTENING**（2 条 TIME_WAIT） |
| `Wahaha_450799035` | 4103808 B / `02:11:33.121` | **不变** |
| `SaveGameInfo` | 28765 B / `02:11:33.122` | **不变** |
| `Wahaha_450799035_old` | 4083244 B / `02:08:37` | **不变** |
| `SaveGameInfo_old` | 28916 B / `02:08:37` | **不变** |

`stop-game.py` 回执：`[1] 游戏在跑：pids=[6456]` → `[2] 请游戏自己退出（quit_game → Game1.quit=true）…` → `✅ 游戏已退出（原 pids=[6456]）`，`exit 0`。
SMAPI 尾部证明是**游戏自己走的退出路径**（不是被杀、不是崩溃）：
`[02:17:19 TRACE game] Disconnected: ClosedGame` → `[02:17:19 TRACE SMAPI] Disposing...` → `[02:17:19 INFO AgentFarm Bridge] 已删除发现文件 …\AgentFarm\bridge.json。` → `Disposing the content coordinator`。窗口内 `ERROR` / `soft_oal` / Windows 事件 1000·1001 均无。

---
*本文件由 machine-runner 生成；判据口径以 `docs/_run6-criteria.md` §2 与本卡卡面为准；所有"原文"均为文件逐字引用。*
