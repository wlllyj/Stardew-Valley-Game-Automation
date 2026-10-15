# run7 证据落盘（0.7.26 · 2026-10-14 22:53:17 → 23:18:29）

> **状态：run7 已完成，尾部连续 3 天 `verified=true`（summer 7/8/9），`finish.code = 0`。**
> **判决并列（两条都成立，见 §4.2）**：
> - **新口径（2026-10-15 起：达标窗口 = 尾部连续 N 天）⇒ `VERIFIED`**（`tools/verify-run3.py` **rc=0**）。
> - **旧口径（整本账本零问题）⇒ `needs_review`**；差异 = 9 条历史问题（summer 3/5/6），逐条列在 §4.2。
>
> 落盘人 `machine-runner`（task-85）。本文所有数字来自**账本 / SMAPI 日志 / 存档文件 / 两个检查器**，全程**未启动游戏、未改任何源码**。
> 原始取证文件：`logs/run7-journal-extract.txt`（685 行，全量账本摘要）、`logs/run7-verify.txt`、`logs/run7-analyze.txt`；脚本 `scratch/run7-extract.py`、`scratch/run7-tools.py`、`scratch/run7-smapi.py`。

---

## §1 起跑与版本四要素

### 1.1 版本四要素（照 `logs/longrun-3day-llm-run7.version.json` 原文）

| 项 | 值 |
|---|---|
| 被测提交 HEAD | `6718429310f685de8223f1347fe9adfc4f53333d` |
| PID / 起跑时刻 | **27308** / `started_at = 2026-10-14T22:53:16`（PID 文件 `logs/longrun-3day-llm-run7.pid` 内容 `27308`，mtime **22:53:17**） |
| 工作树 | `worktree_clean = false`；`git_status_short = ["?? scratch/_t72_tool_fix.py", "?? scratch/_t81_probe.py"]` ⇒ 只有两个**未跟踪**的 scratch 文件，**被测源码无 ` M`** |
| 起跑方式 | 起跑器 `tools/start-detached-longrun.py --journal logs/longrun-3day-llm-run7.jsonl --expect-version 0.7.26`（脱离式 `DETACHED_PROCESS`，非托管后台作业） |
| 起跑前基线 | `logs/run7-baseline.json`（原文见 §1.3） |
| 日志/工件 | 账本 1230 行；console `logs/longrun-3day-llm-run7.console.log` **20713 B / 185 行**；stderr **0 B**；LLM 留痕 `logs/longrun-3day-llm-run7-llm.jsonl` **27 行 / 81475 B** |

被测文件 SHA256 + mtime（sidecar 记录值 → **与现盘逐项一致**，§1.2）：

| 文件 | SHA256 | mtime |
|---|---|---|
| `brain/agentfarm/longrun.py` | `A10CA88E0628CE682F99A9ABBABD901DE806F20347F11ABF5D568FA17B49445B` | `2026-10-14T22:37:42.966147` |
| `brain/agentfarm/farmwork.py` | `404896339FADB1E06FC1C4E261AF45D3E3D2B09B5C1B6F1AB1A1B2F7C023ED01` | `2026-10-14T22:35:03.318170` |
| `brain/agentfarm/bridge.py` | `02B8E1A19997FB76F55C7392A0B7A348E01935E633F9DC1E0F4168364B4EDA94` | `2026-10-14T22:51:13.237531` |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `CC778BC7790C54DC739BD80E69B02026756E7676A41DD63D1FB38C8633B47D76` | `2026-10-14T22:51:21.765660` |
| `mod/AgentFarm.Bridge/manifest.json` | `B6E749C261D70751FFA924E26322C9B7D1EC9F02917550B1C8A81E819B8A007F` | `2026-10-14T22:50:58.690747` |

**起跑时刻晚于全部被测文件 mtime ⇒ 进程 import/装载的是冻结版 0.7.26。**

### 1.2 现盘 vs sidecar 核对（我重算）

五个文件**逐项一致**（SHA256 与 mtime 均相同）⇒ run7 之后没有人改过被测件。

### 1.3 起跑前基线原文（`logs/run7-baseline.json`，Lead 的 preflight 输出）

```json
{"generatedAt":"2026-10-14T22:53:07+07:00","recordedAt":"2026-10-14 22:53:07","worldSeq":12,
 "modVersion":"0.7.26","day":[1,"summer",3],"timeOfDay":620,"location":"Farm","playerTile":[64,15],
 "stamina":270.0,"money":14,"isInBed":false,"seeds":[],"farmingLevel":0,
 "crops":35,"unwateredCrops":35,"dryCrops":35,"farmComplete":true,"farmScanSeq":11,"waterLeft":23,
 "tillableCount":147,"tileCount":400,"tilesTruncated":true,"activeMenu":null,"isModal":false,"worldAdvancing":true}
```

要点：**钱 14g、种子 0 粒、35 株作物全干（dryCrops 35）、壶里 23 格水、`tilesTruncated=true`**（观测窗口被 400 格上限截断，这是 run7 全程的已知盲区）。

### 1.4 起跑/结束快照

**run7 没有起跑/结束快照**：`scratch/run7-external-snapshots.jsonl` 不存在；`scratch/run6-external-snapshots.jsonl` 里的 start/end 两行属 **run6**（`save_main 3696701 / 2026-10-13T20:37:37.898`、SMAPI 777→1447 行）。⇒ §3 的外部证据只能靠 SMAPI 与存档文件本身，**没有快照路的第二源**。照实记录，不补写。

---

## §2 逐日表（7 天：summer 3 → summer 9，跨日 7 次）

| # | 游戏日 | ended_by | verified | ok/skip/fail | `final_water`（farm 口径 tiles/crops/dry） | `day_after` | 未过的 checks |
|---|---|---|---|---|---|---|---|
| 173 | summer 3 | `sleep` | **False** | 109/3/0 | 136 / 5 / **1** | summer 4 ✅ | `watered_outdoor`, `day_justified` |
| 207 | summer 4 | `sleep` | **True** | 15/0/0 | 128 / 5 / **0** | summer 5 ✅ | —（全过） |
| 433 | summer 5 | `sleep` | **False** | 187/0/0 | 132 / 6 / **1** | summer 6 ✅ | `watered_outdoor`, `day_justified` |
| 1012 | summer 6 | **`stuck`** | False | 46/0/0 | 133 / 6 / **1** | summer 7 ✅ | `slept_by_us`, `crops_watered`, `watered_outdoor`, `day_justified` |
| 1195 | summer 7 | `sleep` | **True** | 134/0/0 | 152 / 6 / **0** | summer 8 ✅ | —（全过） |
| 1216 | summer 8 | `sleep` | **True** | 5/0/0 | 135 / 6 / **0** | summer 9 ✅ | —（全过） |
| 1228 | summer 9 | `sleep` | **True** | 6/0/0 | 129 / 6 / **0** | summer 10 ✅ | —（全过） |

`day_after` 链 **7/7 恰 +1**（3→4→5→6→7→8→9→10）。

**逐日 `ended_reason` 原文（关键三条）**

- **summer 3**（`ok 109`）：`stuck:换过 11 片地都没有目标（守卫仍说还有活：农场口径还有 1 格干作物，其中 1 格在玩家窗口之外（Mod 报的坐标 [[12, 30]]；已试 2 次都够不着，当天不再重试）（壶里还有 26 格水），先把水浇完再谈收工）`
  - 阶段：`clear_dead` **6 段 / ok 30**、`till_area` 5 段、`plant_area` 3 段（`stopped='no_seed'`）、`water_area` 1 段；`unreachable 1 格 [[73,35]] bound 23`、`refused 3 格 [[72,35],[72,36],[73,36]] bound 23`。
  - 这一天把 **`farm.dryCrops` 从 35 一路浇到 1**（notes 逐条留痕：35→35→34→33→31→30→…），剩下那 1 格 `[[12,30]]` 在玩家窗口外、走不到。
- **summer 5**（`ok 187`）：同型 `stuck`，仍是 `[[12,30]]` 那一格（`unreachable 8 格 bound 39 exempt 1`），壶里剩 21 格水。
- **summer 6**（`ended_by=stuck`，`ok 46`）：`stuck:连续 3 轮世界没有任何变化（最后意图：['water_area']；策略说有进展：False）；守卫仍说还有活：有 1 格作物没浇水；field_nw还有地要清/开/种`
  - **task-73 `stuck_flush` 自主翻篇**（账本 #1009）：`{"ok":true,"count":1,"limit":2,"day_after":[1,"summer",7], "note":"…刻意绕过 sleep_guard 睡过去，让整轮继续跑下一天；本日仍如实计 stuck、day_justified=False、绝不 VERIFIED。"}` ⇒ 当天 `verified=false`、`day_justified=false`，**没有洗白**。
  - 同一天 **`frontier_clear` 20 次全部 `acted:true`**（坐标 `[17,26] [17,27] [16,25] [15,26] [16,27] [14,26] [14,27] [13,25] [12,24] [12,23] [12,22] [11,23] [11,22] [10,23] [10,22] [9,23] [9,22] [8,23] [9,21] [8,22]`，`limit=20`）⇒ `ok 46 ≠ 0`，**"零动作收工"没有复现**（见 §4.3 第 5 条）。
- **summer 7/8/9**：`no_work:确实找不到可做的活（地里的活干完了、也没法/没必要买种子）`，`dry=0`、`ok 134/5/6`、`verified=true` ⇒ 与 `docs/_run6-criteria.md` 的「`no_work` ⇒ `final_water.dry == 0`」口径一致。

**逐日 `final` 原始字段（window 口径，供对照）**

| 日 | `final.location` | `final.tile` | `tod` | `crops` | `unwatered_crops` | `waterLeft` | `stamina` | `money` |
|---|---|---|---|---|---|---|---|---|
| summer 3 | `Farm` | [58,25] | 1530 | 2 | 0 | 26 | 76.1 | 14 |
| summer 4 | `Farm` | [46,17] | 700 | 1 | 0 | 26 | 258.3 | 14 |
| summer 5 | `Farm` | [68,40] | 1320 | 5 | 0 | 21 | 168.3 | 14 |
| summer 6 | `Farm` | [9,22] | 1040 | 1 | 1 | 16 | 189.9 | 14 |
| summer 7 | `Farm` | — | 1150 | — | — | — | — | 14 |
| summer 8 | `Farm` | — | 720 | — | — | — | — | 14 |
| summer 9 | `Farm` | — | 730 | — | — | — | — | 14 |

（`final.location == "Farm"` **不是判据**——该条已作废；上表只作为原始证据。summer 7/8/9 的空格未取，完整值在 `logs/run7-journal-extract.txt`。）

**其他总量读数（账本）**

- 事件计数（1230 条账本）：`day_start 7, day_end 7, sleep 7, decision 217, intent_verdict 186, outcome 186, policy 108, idle 66, plot 43, plot_exhausted 23, stage_exhausted 74, stage_no_target 6, stage_midway_leftover 6, work_spot 27, water_far 25, refill 2, goto_farm 6, plots_capped 2, seed_gate 5, clear_neighbor 67, frontier_clear 20, clear_dead_scope 1, unreachable 14, unreachable_stage 69, unreachable_summary 4, tool_refused 3, refused_stage 1, refused_summary 1, resume_walk 30, review 9, stuck_flush 1, finish 1`。
- **全程没有**：`buy`、`no_seed_for_sale`、`cannot_afford`、`sell`、`no_day_progress`、`bridge_down`、`modal_*`、`event_blocked`、`watchdog_stop`、`sell`（`intent 分布`里有 1 次 `ship` 意图，但没有落地成 `sell` 事件）。
- 阶段步数合计：`ok 502 / skipped 3 / failed 0`（analyze 口径）。
- LLM：`decision 217` 条中 `llm=true` **27**、`source="llm"` **27**（= `decisions_llm` 与 `decisions_llm_used` 两口径同值）、`truncated 0`、`fallback 0`；留痕文件 27 行与之**一一对应**。

---

## §3 外部证据（三源）

### 3.1 存档 size/mtime

| 文件 | size | mtime |
|---|---|---|
| `Wahaha_450799035` | **3648782 B** | **2026-10-14 23:33:11.539548800** |
| `SaveGameInfo` | 27909 B | 2026-10-14 23:33:11.542060200 |
| `Wahaha_450799035_old` | **3614652 B** | **2026-10-14 23:18:27.238134500** |
| `SaveGameInfo_old` | 27907 B | 2026-10-14 23:18:27.239637200 |

- **run7 窗口（22:53:17–23:18:29）内的最后一次落盘 = `_old` 那份：3614652 B / 23:18:27**，即 summer 9 → summer 10 那次跨日。
- **main 那份（3648782 B / 23:33:11）属于 run7 结束之后游戏的自动过夜**（SMAPI 同刻 `Context: after save, starting summer 11 Y1`，见 §3.2）⇒ **必须与 run7 分开写**，不计入 run7。
- **存档目录只保留两代**（main + `_old`）⇒ run7 窗口内中间 5 次落盘各自的 size **不可恢复**，本文件不猜。

### 3.2 SMAPI 窗口行号（`%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt`）

日志 8533 行 / mtime `2026-10-14 23:33:13`；时间跨度 22:52:15–23:33:13；**窗口内（22:53:17–23:18:29）8106 行**。

| 跨日 | `Synchronizing 'NewDay' task` | `Context: before save.` | `SaveGame.Save() called.` | `Synchronizing 'Save' task` | `completed without exceptions` | `after save, starting …` |
|---|---|---|---|---|---|---|
| → summer 4 | L1299 23:00:00 | L1302 23:00:01 | L1303 | L1304 | L1307 23:00:03 | L1308 23:00:04 |
| → summer 5 | L1761 23:01:11 | L1764 23:01:11 | L1765 | L1766 | L1769 23:01:11 | L1770 23:01:13 |
| → summer 6 | L3494 23:06:57 | L3497 23:06:57 | L3498 | L3499 | — | L3503 23:06:59 |
| → summer 7 | L6256 23:10:57 | L6259 23:10:57 | L6260 | L6261 | — | L6265 23:10:59 |
| → summer 8 | L7680 23:15:42 | L7683 23:15:42 | L7684 | L7685 | — | L7689 23:15:44 |
| → summer 9 | L8086 23:17:00 | L8088 23:17:00 | L8090 | L8091 | — | L8095 23:17:02 |
| → summer 10 | L8513 23:18:27 | L8516 23:18:27 | L8517 | L8518 | — | L8522 23:18:29 |
| **→ summer 11（窗口外）** | L8533 23:33:13 | — | — | — | — | L8533 23:33:13 |

- 窗口内 **`Synchronizing 'NewDay' task` 7 次、`Context: before save.` 7 次、`SaveGame.Save() called.` 7 次、`Synchronizing 'Save' task` 7 次**，与账本 **7 次跨日一一对应**；`after save, starting summer N Y1` 共 8 条，**第 8 条（summer 11 / 23:33:13）在窗口外**，属游戏自动过夜。
- **run7 没有 run6/run5 那种"有 NewDay 却没有 Save"的缺口**（task-47 的菜单链问题在本轮 7/7 全部走完）。最后落盘与 `_old` 的 23:18:27 完全吻合。

### 3.3 快照文件

- `scratch/run7-external-snapshots.jsonl`：**不存在**（起跑/结束均未写；原因见 §1.4）。
- `scratch/run6-external-snapshots.jsonl`：只有 run6 的 start（`2026-10-13T21:41:56`，`save_main 3696701 / 20:37:37.898` 为覆盖值，`smapi_lines 777 / newday 1 / save 1`）与 end（`21:43:27`，`1447 / 1 / 1`）两行，**与 run7 无关**。

### 3.4 窗口内噪声与已知活锁

| 关键词 | 窗口内计数 |
|---|---|
| `Disconnected` / `ClosedGame` / `Disposing` | **0** / 0 / 0 |
| `ERROR` / `Exception` | **0** / **0** |
| `soft_oal` | **0** |
| `Warping to Farm` | **1885**（task-14 逐帧 warp 活锁**仍在**；本轮没有勾出剧情事件，`modal_*` 0 次，**只作信息项**） |

### 3.5 `day_after` 链

7 天 7 次跨日，`day_after` 逐日恰 +1（§2 表）；`tools/analyze-longrun.py` 独立核对 `跨日证据 day_after 6/6（ended_by=sleep）`（它只统计 `ended_by=sleep` 的日子，故为 6）。

---

## §4 判据对照

### 4.1 每日七项 checks（逐日原文）

| 日 | `slept_by_us` | `no_blocking_modal` | `no_hard_failures` | `unreachable_within_bound` | `refused_within_bound` | `no_unmet_stages` | `crops_watered` | `watered_outdoor` | `day_justified` |
|---|---|---|---|---|---|---|---|---|---|
| summer 3 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| summer 4 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| summer 5 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| summer 6 | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| summer 7 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| summer 8 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| summer 9 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

- `unreachable_within_bound` / `refused_within_bound` **7/7 全绿**，且账本每天都给出了坐标与上界（summer 3：1 格 / bound 23；summer 5：8 格 / bound 39 / exempt 1；summer 6：1 格 / bound 22 / exempt 1；summer 7：4 格 / bound 27）⇒ **"不可达假红"没有复现**。
- `day_end` 记录里已带 task-78 的 `bound_basis` / `encircled` / `encircled_tiles` 字段（口径收窄落地）。
- `no_hard_failures` 7/7 全绿 ⇒ run7 没有"四邻都站不过去"被判硬失败（run5/run6 的老病灶）。

### 4.2 达标口径：旧 vs 新（两条结论都写）

- **新口径（`docs/_run6-criteria.md` §2，2026-10-15 起；提交 `7c4ff68`）**：达标窗口 = **尾部连续 N 天**；窗口**之外**日子的问题降级为 `history_problems`、不影响 exit code。
  ⇒ `python tools/verify-run3.py --journal logs/longrun-3day-llm-run7.jsonl` **rc=0、`VERIFIED`**：`尾部连续 VERIFIED 天数 3 / 要求 3`；`finish {code:0, verified_streak:3, actions:683, minutes:25.2, stages_seen:[clear_area, clear_dead, plant_area, till_area, water_area], no_unmet_stages:true, unmet_days:[], stuck_flushes:1}`；`stuck 日翻篇：1 天 / stuck_flush ×1 / stuck_flush_skipped ×0`。全文见 `logs/run7-verify.txt`。
- **旧口径（整本账本零问题）⇒ `needs_review`**；差异 **9 条** `history_problems`（原文逐条）：
  1. `[summer 3] watered_outdoor=false`
  2. `[summer 3] verified=false`
  3. `[summer 5] watered_outdoor=false`
  4. `[summer 5] verified=false`
  5. `[summer 6] ended_by=stuck`
  6. `[summer 6] watered_outdoor=false`
  7. `[summer 6] 睡前 unwatered_crops=1`
  8. `[summer 6] crops_watered=false`
  9. `[summer 6] verified=false`
- 共同根因：**窗口外那 1 格干作物 `[[12,30]]`**（summer 3/5/6 各因此收不了功）。summer 6 的 `stuck_flush` 把这一页翻过去，summer 7 起 `dry=0`，尾部 3 天全绿。

### 4.3 `docs/_release-0.7.26.md` §4 的 7 条新增关注项

| # | 关注项 | run7 读数 | 判定 |
|---|---|---|---|
| 1 | `buy` 成功（钱减少 + 当季种子 + 后续 `plant_area` ok>0） | **`buy` 事件 0 次**；5 次 `seed_gate` 全是 `{seeds:0, money:14, seed_price:20}`（钱 14g < 售价 20g）；`plant_area` 3 段均 `stopped='no_seed'` | **未发生 / 未覆盖**（不是失败：钱不够，脑侧按 task-67 口径不再盲买） |
| 2 | `no_seed_for_sale` 每天 ≤1 次且不再致 `stuck` | 该事件 **0 次** | **未触发**（不能算通过：种子腿整轮缺席） |
| 3 | `clear_dead` 至少一天 `ok>0`，`farm.deadCrops` 下降 | summer 3 `clear_dead` **6 段 / ok 30**；`clear_dead_scope`（t=143.06）记 `farm=33 / in_view=28`；**`farm.deadCrops` 没有第二个读数**；旁证：`farm.crops` 由基线 **35 → 5**（30 格枯死作物被清掉） | **前半 ✅（ok 30）；"deadCrops 下降"无第二个外部读数 ⇒ 不判定** |
| 4 | `unreachable_within_bound` 不再假红 | 7/7 天 ✅，且每天给出坐标 + bound + exempt | ✅ |
| 5 | 零动作收工不再出现（`stuck` 日必须真清掉一格） | summer 6 `stuck` 日 `frontier_clear` **20 次全 `acted:true`**、`ok 46`；工具侧未点名 `stuck + ok_steps==0` | ✅ |
| 6 | `stuck` 日翻篇（`day_after` +1、当天不洗白） | `stuck_flush #1009 ok:true count 1/2`、`day_after=[1,'summer',7]`；当天 `verified=false`、`day_justified=false` | ✅ |
| 7 | 工具侧新闸门不误杀旧账本 | 本卡只跑 run7 账本；**跨账本回归（run2/3/5/6 逐字相同、analyze 六本 rc 不变）由工具侧/Lead 做，我没有独立复跑** | **未验证（照实写）** |

### 4.4 别的硬口径

- **禁止 `final.location == "Farm"`**：本文件不把它当判据（§2 只作原始证据列示）。✅
- **`ended_reason` 以 `no_work` 开头 ⇒ `final_water.dry == 0`**：summer 4/7/8/9 四天满足；summer 3/5 的 `ended_reason` 是 `stuck:`，不属此条但 dry=1（已计入 §4.2 历史问题）。✅
- **真空日闸门**：7 天都有真实动作（最小 `ok 5`），无真空日。✅
- **`finish.code == 0`**：✅（`verified_streak=3`、`stuck_flushes=1`）。

---

## §5 独立结论 + 不确定项

### 5.1 我亲跑的检查器

- **`tools/verify-run3.py --journal logs/longrun-3day-llm-run7.jsonl` ⇒ rc=0 / `VERIFIED`**（`logs/run7-verify.txt`）。日表 7 行；`decision 217 条（LLM 调用 27 / 其中模型产出 27）`；info 段确认逐日不可达/拒绝"账本 vs 自算"一致、`clear_neighbor`（summer 6 **64 次**、summer 7 2 次、summer 5 1 次）、`frontier_clear` summer 6 **20 次（真清掉 20）**、summer 4 只涉及一个阶段（弱日 info）。
- **`tools/analyze-longrun.py --journal …` ⇒ rc=1**（`logs/run7-analyze.txt`，204 行）：`VERIFIED: 4/3 天`（口径不同：它按 daily-verified 计数）、`步数合计 ok 502 / skipped 3 / failed 0`、`no_day_progress 0`、`blocked 0`、`sleep 7（ok 7 / failed 0）`、`不可达 14 次/12 格`、`游戏拒绝 3 次/3 格`、`开路尝试 20 次（真清掉 20 / 没清掉 0）`、`stuck 翻篇 1 次（行 [1010]）`、**`必须人工介入（红）0 条`**；rc=1 的原因是**事件映射红 138 条**（`missed:cancel:*`、`missed:check:*`、`missed:plot_exhausted`、`missed:stage_exhausted`、`missed:stage_no_target`）= 账本里有这些事件名而工具的期望表未收录（task-66 类）。

**我认同 verify-run3 的新口径判决（rc=0 / 尾部 3 天 VERIFIED）**：三条尾部日子 `ended_by=sleep`、`dry=0`、`ok>0`、`day_after` +1、外部三源（存档 23:18:27、SMAPI 7 次完整 Save 链、`day_after` 链）同向。
**我不认同把 `analyze-longrun` 的 rc=1 当成功能失败**：它 138 条红全是事件映射漂移，`必须人工介入（红）0 条`、`failed 0`、`no_day_progress 0`；判决权威是 `verify-run3`。

### 5.2 不确定项 / 盲区（照实写）

1. **无 run7 起跑/结束快照**（`scratch/run7-external-snapshots.jsonl` 不存在）⇒ 存档侧只有"最后一次落盘"这一个窗口内数据点，**中间 5 次落盘 size 不可恢复**（存档只留两代）。
2. **`tilesTruncated=true` 全程为真**（观测窗口被 400 格上限截断）⇒ 田区统计只覆盖已返回的格；`final.crops`（window 口径）与 `final_water.crops`（farm 口径）数值不同即源于此。
3. **种子腿整轮缺席**：`buy` 0 次、`seed_gate` 5 次（钱 14g < 单价 20g）⇒ §4.3 第 1/2 条只能记"未发生"。
4. **`farm.deadCrops` 只有 1 个读数**（33，t=143.06）⇒ "下降"缺第二个外部读数；只能给 `farm.crops 35→5` 与 `clear_dead ok=30` 作旁证。
5. **`Warping to Farm` 1885 次**（task-14 逐帧活锁）仍在；本轮没有勾出剧情事件（`modal_*`/`event_blocked` 0），故不影响 run7 判决，但**它是"下一次 run 可能被事件阻断"的现存风险**。
6. **本卡没有复跑跨账本回归**（§4.3 第 7 条），也没有复核 `docs/_run6-criteria.md` §2 的窗口定义本身（那是 Lead/工具侧的活）。
7. `final.location/tile` 之外的 `final` 字段（summer 7/8/9 的 tile/stamina/waterLeft）本文件留空，完整值在 `logs/run7-journal-extract.txt`。

### 5.3 保留物

`logs/longrun-3day-llm-run7.jsonl`（1230 行）、`logs/longrun-3day-llm-run7.version.json`、`logs/longrun-3day-llm-run7.pid`、`logs/longrun-3day-llm-run7.console.log`、`logs/longrun-3day-llm-run7.console.err.log`（0 B）、`logs/longrun-3day-llm-run7-llm.jsonl`（27 行）、`logs/run7-baseline.json`、`logs/longrun-3day-llm-run7-baseline.json`、`logs/run7-journal-extract.txt`、`logs/run7-verify.txt`、`logs/run7-analyze.txt`、`scratch/run7-extract.py`、`scratch/run7-tools.py`、`scratch/run7-smapi.py`。均不删。

---

## 附：与 run6 的对比（一句话）

| 指标 | run6（0/3） | run7（3/3 尾部） |
|---|---|---|
| 跨日 | 0 次 | **7 次**（`day_after` 7/7 +1） |
| 终止 | 快速失败 `finish{code:1, 37.2s}` | `finish{code:0, 25.2 分钟, verified_streak:3}` |
| 种子腿 | 6 次 `item_not_sold` 全败 | 0 次 `buy`（钱 14g < 20g，`seed_gate` 5 次，不再盲买） |
| 枯死作物 | 42 格全不可达、`clear_dead` 0 ok | `clear_dead` **ok 30**、`farm.crops 35→5` |
| "四邻都站不过去" | 判 `no_hard_failures=false`、42 格 | `no_hard_failures` **7/7 全绿**、不可达每日在 bound 内 |
| `stuck` 日 | 直接终止整轮（`no_day_progress`） | **翻篇**（`stuck_flush` 1 次，`day_after` 前进、当天不洗白） |
| 浇水 | 未跨日、无 `dry` 归零证据 | summer 4/7/8/9 `dry=0`；summer 3 把 `dryCrops` 35→1 |
