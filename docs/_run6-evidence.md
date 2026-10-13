# run6 验收取证（task-57）—— attempt #1：失败跑

**状态行**：run6 **attempt #1** = 2026-10-13 **21:41:21 → 21:41:58**（**37.2 秒 / 0.62 分钟**），被测版本 **0.7.25（`31cb3cd`）**，脱离式起跑，PID **28240**。
**结论：FAIL（尾部连续 VERIFIED 0/3、0 次跨日、`exit 1`）**，定性为「**干净快速失败**」：`stderr 0 B`、0 崩溃、0 掉线、0 模态阻断。
**死因**：`sleep_guard` 的「没种子但钱够 ⇒ 该去买」× 枯死作物不可达 ⇒ 死锁（证据见 §3）。已由 Lead 派 **task-67 / task-68** 修复；**run6 不重跑**，修完冻结 0.7.26 后跑 run7。
**游戏未退出**：仍运行中（PID **27276**，bridge `modVersion=0.7.25`）。
判据口径一律以 `docs\_run6-criteria.md` 为准；**全程未使用** `day_end.final.location=="Farm"`（已废弃）。

---

## §1 版本与前置（四要素 + version sidecar 原文）

### 1.1 四要素

| 项 | 值 |
|---|---|
| `HEAD` | `31cb3cd7fc0500716ba0ad6946efd0aa59b3a5ef`（0.7.25 冻结提交；含冻结提交 `e381e58`） |
| `git status --short` | `M docs/_release-0.7.25.md`（唯一一条；**被测源码无 ` M`**） |
| 长跑 PID / 起跑时刻 | **28240** / `2026-10-13T21:41:21`（**晚于**下列全部被测文件 mtime ⇒ 加载的是冻结版 ✅） |

被测文件（SHA256 + mtime），来自起跑器 sidecar：

| 文件 | SHA256 | mtime |
|---|---|---|
| `brain/agentfarm/longrun.py` | `4AEDF22C87F9470C1038A9F5A6DFD8C51252891E1BDCD2AE87BDBD5E9A39CD29` | `2026-10-13T21:27:51.277556` |
| `brain/agentfarm/farmwork.py` | `990580EE4EFA739D8F06C5EF0AAF17A0AFB7EE76B3E6A42C1A057364D4AD0068` | `2026-10-13T21:27:51.275956` |
| `brain/agentfarm/bridge.py` | `109E71CD2CE62BB3CEFC7B2229D6FFF961988FEB4CBD9D6BEF93DC3E62E76D31` | `2026-10-13T21:36:57.796395` |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `28E650A8F7C4A39B7C0C0E7E81D3D85B33E3D3FE32C33E0D275411F3350EC637` | `2026-10-13T21:37:04.474775`（170496 B） |
| `mod/AgentFarm.Bridge/manifest.json` | `3B8C4F26916CB418F669E5A97C0F43FA10725174B7A56D67F31F8A998DDDFCFB` | `2026-10-13T21:36:04.148125`（18426 B，Version 0.7.25） |

### 1.2 version sidecar 原文（`logs\longrun-3day-llm-run6.version.json`）

```json
{
  "head": "31cb3cd7fc0500716ba0ad6946efd0aa59b3a5ef",
  "files": {
    "brain/agentfarm/longrun.py": {
      "sha256": "4AEDF22C87F9470C1038A9F5A6DFD8C51252891E1BDCD2AE87BDBD5E9A39CD29",
      "mtime": "2026-10-13T21:27:51.277556"
    },
    "brain/agentfarm/farmwork.py": {
      "sha256": "990580EE4EFA739D8F06C5EF0AAF17A0AFB7EE76B3E6A42C1A057364D4AD0068",
      "mtime": "2026-10-13T21:27:51.275956"
    },
    "brain/agentfarm/bridge.py": {
      "sha256": "109E71CD2CE62BB3CEFC7B2229D6FFF961988FEB4CBD9D6BEF93DC3E62E76D31",
      "mtime": "2026-10-13T21:36:57.796395"
    },
    "mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll": {
      "sha256": "28E650A8F7C4A39B7C0C0E7E81D3D85B33E3D3FE32C33E0D275411F3350EC637",
      "mtime": "2026-10-13T21:37:04.474775"
    },
    "mod/AgentFarm.Bridge/manifest.json": {
      "sha256": "3B8C4F26916CB418F669E5A97C0F43FA10725174B7A56D67F31F8A998DDDFCFB",
      "mtime": "2026-10-13T21:36:04.148125"
    }
  },
  "pid": 28240,
  "started_at": "2026-10-13T21:41:21",
  "git_status_short": ["M docs/_release-0.7.25.md"],
  "worktree_clean": false
}
```

### 1.3 起跑路径与文件

- 起跑器（task-57 新工具，优先路径）：`python tools\start-detached-longrun.py --journal logs/longrun-3day-llm-run6.jsonl --expect-version 0.7.25 --health-seconds 25`；先 `--dry-run` 核对四要素，结论「可以起跑」。
- 起跑器前置体检四项全绿：`装机 0.7.25 ✅ / 已读档 ✅ / 在户外农场 ✅ / 无阻断模态（activeMenu=None）✅`。
- PID 文件 `logs\longrun-3day-llm-run6.pid`（= 28240）；console `logs\longrun-3day-llm-run6.console.log`（终态 8190 B / 43 行）；stderr `logs\longrun-3day-llm-run6.console.err.log`（**0 字节**）；账本 `logs\longrun-3day-llm-run6.jsonl`（143 条）；外部快照 `scratch\run6-external-snapshots.jsonl`（`tag:"start"` / `tag:"end"`）。

### 1.4 两份基线（`logs\run6-baseline.json` 为权威）

| 项 | 权威 `logs\run6-baseline.json`（Lead 手写） | 起跑器副本 `logs\longrun-3day-llm-run6-baseline.json`（21:41:21 真起跑时写入） |
|---|---|---|
| 游戏日 | `[1, "summer", 4]` | `[1, "summer", 4]` |
| `timeOfDay` | **630** | **740** |
| 地点 / 玩家格 | `Farm` / `(64,15)` | `Farm` / `[64,15]` |
| 体力 / 钱 | 270 / **956** | 270.0 / **956** |
| `crops` / `unwateredCrops` / `dryCrops` | 35 / — / **0** | 35 / 35 / **0** |
| `deadCrops` | **33**（task-51 新字段真机可见） | 未输出该字段 |
| 天气 | **lightning** | 未列（console `[day]` 行：`天气 lightning`） |
| `waterLeft` / `tillableCount` / `tileCount` | 23 / 146 / 400（`tilesTruncated=true`） | 23 / 146 / 400（`tilesTruncated=true`） |
| `worldSeq` / `farmScanSeq` | — | 56 / 56 |
| 模态 / `worldAdvancing` | 无模态 / true | `activeMenu=null` / `isModal=false` / true |

差异原因：两份相隔约一小时（权威基线取在预置前后，副本取在真起跑瞬间），期间 `timeOfDay` 630→740、`worldSeq` 因 observe/出货/睡觉而变。两份原文都在各自文件里。

### 1.5 操作员预置（Lead 完成，非本跑动作）与已知干扰项

- `scratch\run6-preseed.py`：走 `Farm.shipItem` **整叠**出货 6 叠（`(O)535 Geode×1`、`(O)390 Stone×104`、`(O)388 Wood×72`、`(O)771 Fiber×115`、`(O)382 Coal×11`、`(O)330 Clay×13`），6/6 观测差分确认、当天 money 不变（14g）。
- `scratch\verify-sleep-brain.py --from-farm`：睡一夜 **summer 3 → summer 4**，**money 14 → 956g**（出货箱日终结算）。
- **task-47 U2 数据点**：这次日终保存**即使关掉 ShippingMenu 也没落盘** ⇒ 起跑前磁盘存档仍是 `3696701 B / 2026-10-13T20:37:37.898`（20:37 写的 `summer 3` 档），而游戏内已是 `summer 4`、money 956。按 `docs\_run6-criteria.md` §2：**不判失败也不判通过**，此处点名。
- 观察截断：全程 `location.tilesTruncated=true`（`tiles[]` 有 400 格上限；`plot` 记录两次都带该告警，田区统计与锚点打分只覆盖已返回的格）。
- 已知缺口（非本轮）：Mod `ShipSkill` 只能整叠出货，无「每 id 保留 K=10」能力（task-55）。

---

## §2 逐日表与 `ended_reason` 原文

### 2.1 逐日表（2 个日报告，都在同一天，0 次跨日）

| # | `t` | 日 | `ended_by` | 跨日 | `day_after` | ok/skip/fail | `final_water` | `checks`（全字段） |
|---|---|---|---|---|---|---|---|---|
| `#69` | **18.47** | `1年 summer 4日` | **stuck** | ❌ | `null` | **0/0/0** | `scope=farm`、`location=Farm`、`tiles=92`、`crops=35`、**`dry=0`** | `slept_by_us:false`、`no_blocking_modal:true`、`no_hard_failures:true`、**`unreachable_within_bound:false`**、`refused_within_bound:true`、**`no_unmet_stages:false`**、`crops_watered:true`、`watered_outdoor:true`、`day_justified:false` |
| `#140` | **37.20** | `1年 summer 4日` | **stuck** | ❌ | `null` | **0/0/0** | 同上（`tiles=92`、`crops=35`、`dry=0`） | 完全同上 |

`day_start`（两条，证明第二次是**同一天重试**）：
- `#0 t=0.1`：`{"day":[1,"summer",4],"timeOfDay":740,"stamina":270,"money":956,"crops":30,"unwatered":0,"location":"Farm","weather":"lightning"}`
- `#70 t=18.52`：与上条**逐字段相同**。

`finish` 原文：`{"event":"finish","t":37.2,"code":1,"verified_streak":0,"actions":95,"minutes":0.62,"stages_seen":["clear_dead","till_area"],"no_unmet_stages":false,"unmet_days":["1年 summer 4日","1年 summer 4日"]}`

### 2.2 `ended_reason` 原文（两次逐字相同）

> `stuck:连续 3 轮世界没有任何变化（最后意图：['clear_dead']；策略说有进展：False）；守卫仍说还有活：没种子但钱够（956g ≥ 20g），该去买；今天早些时候还有 12 格没做完（跨片地，最近的是 [61, 20]）；field_se还有地要清/开/种`

### 2.3 账本事件计数（143 条）

`{"day_start": 2, "buy": 6, "plot": 2, "decision": 6, "intent_verdict": 6, "clear_dead_scope": 2, "unreachable": 84, "unreachable_stage": 8, "outcome": 8, "idle": 6, "modal_dismissed": 5, "stage_exhausted": 2, "unreachable_summary": 2, "day_end": 2, "no_day_progress": 1, "finish": 1}`

`sleep` **0** 条、`goto_farm` 0、`refill` 0（`dryCrops=0`、`waterLeft=23` ⇒ 本轮既不需要浇水也不需要补水）。

---

## §3 根因链（三段，全部有账本原文）

### 3.1 守卫认为「还有活、不许收工」

`ended_reason` 里守卫原话（见 §2.2）：

> 守卫仍说还有活：**没种子但钱够（956g ≥ 20g），该去买**

对照 run5：那时钱只有 14g（买不起），守卫允许以 `no_work` 收工；本轮操作员预置把 money 打到 **956g**，于是守卫要求「必须去买种子」，**拒绝收工**。

### 3.2 这个活不可能完成：SeedShop 在 summer 不卖 472

`buy` 失败 **6 次**（`t=0.28 / 13.99 / 17.13 / 18.69 / 32.60 / 35.78`），每次 `before/after` 都是 `{"money":956,"item":0}`（一件未成交、钱未变）。回执原文（截断处在原账本里更长）：

> `item_not_sold: [item_not_sold] (HTTP 200) 商店「SeedShop」里没有「472」。在售清单：Melon Seeds(80g)、Tomato Seeds(50g)、Blueberry Seeds(80g)、Pepper Seeds(40g)、Wheat Seeds(10g)、Radish Seeds(40g)、Poppy Seeds(100g)、Spangle Seeds(50g)、H…`

即在售的都是**夏季**种子，而脑侧要买的是 **472（Parsnip Seeds）** ⇒ 采购**永不可能成功**。
（期间 `modal_dismissed:5`，全部是普通 `ShopMenu`，**非** `eventUp` 事件、**非** `professionsToChoose` ⇒ task-41 事件硬停未被触发。）

### 3.3 唯一剩下的实体活也干不了：42 格不可达

`clear_dead`（清枯死作物，task-51 新阶段）与 `till_area` 的候选格**全部「四邻都站不过去（没有落脚点）」**。

`unreachable_stage` 明细（**task-68 的输入**，逐格坐标）：

| # | `stage` | `zone` | `tiles` | `in_leftover` | 坐标 |
|---|---|---|---|---|---|
| 1 | `clear_dead` | `field_ne` | 12 | 12 | `[60,26] [64,18] [66,20] [67,21] [68,20] [68,21] [69,20] [69,21] [70,20] [71,22] [71,23] [72,22]` |
| 2 | `till_area` | `field_ne` | 12 | 12 | `[59,18] [60,18] [60,19] [61,18] [61,19] [62,18] [62,19] [62,20] [63,18] [63,19] [63,20] [63,21]` |
| 3 | `clear_dead` | `field_ne` | 12 | 24 | `[71,24] [71,25] [71,26] [72,23] [72,24] [72,25] [73,22] [73,23] [73,24] [74,22] [74,24] [75,22]` |
| 4 | `clear_dead` | `field_ne` | 6 | 30 | `[39,16] [40,18] [72,26] [75,24] [75,25] [75,26]` |

每个 `unreachable` 事件的 `reason` 统一为 `四邻都站不过去（没有落脚点）`，`note` 为 `四邻都站不过去/寻路到不了 ⇒ 当天不再白试（次日会重试）；不算硬失败，日级另有有界豁免`。

`unreachable_summary` 原文（两次相同）：

```json
{"event":"unreachable_summary","t":18.47,"count":42,"bound":8,"attempted":42,"exempted":8,"raw_unmet":54,"unmet":46,
 "tiles":[[39,16],[40,18],[59,18],[60,18],[60,19],[60,26],[61,18],[61,19],[62,18],[62,19],[62,20],[63,18]],
 "note":"不可达豁免：界内不影响 verified；扣掉的格子在 leftover 里逐格可见"}
```

配套：`stage_exhausted{"stage":"clear_dead","leftover":30,"doomed":30,"capped":0}`。
⇒ 有界豁免只豁免 **8** 格（`bound:8`），其余 **46** 格如实计为未完成 ⇒ `checks.unreachable_within_bound=false`、`checks.no_unmet_stages=false`。

### 3.4 合成：`idle` → `stuck` → 同日重试 → `no_day_progress` → 停跑

- 守卫说有活（3.1）+ 买不到种子（3.2）+ 剩下的活不可达（3.3） ⇒ 世界**连续 3 轮零变化**：
  `idle{"event":"idle","t":37.19,"rounds":3,"zone":"field_ne","intents":["clear_dead"],"acted":false}`
- 于是 `day_end #69`（t=18.47）判 `stuck`（0 做成 0 跳过 0 失败）⇒ 系统**重开同一天**（`#70 day_start` 又是 `summer 4 tod 740`）⇒ 第二轮完全复现 ⇒ `day_end #140`（t=37.20）再次 `stuck` ⇒ `no_day_progress{"t":37.2,"day":[1,"summer",4],"ended_by":"stuck",…}` ⇒ console 打印 `× 游戏日没有前进（stuck…），停下` ⇒ `finish code=1` ⇒ 进程 28240 于 21:41:58 退出。
- 全程：**没有**任何跨日、**没有**模态阻断、**没有**崩溃、**没有**掉线。

---

## §4 外部证据（与账本同向）

| 证据 | 读数 | 与账本是否同向 |
|---|---|---|
| 存档主文件 `Wahaha_450799035` | **3696701 B / 2026-10-13T20:37:37.898**（起跑前、跑后**逐字节相同**） | ✅ 同向（0 次跨日） |
| `SaveGameInfo` | **26578 B / 2026-10-13T20:37:37.899**（未变） | ✅ |
| `_old` / `SaveGameInfo_old` | 3747788 / 20:22:58.840、25161 / 20:22:58.842（= `summer 2` 档，未被本轮触碰） | ✅ |
| SMAPI（`SMAPI-latest.txt`） | 全文 **1453** 行；**起跑前**（≤21:41:21）777 行（`Synchronizing 'NewDay'` **1** / `SaveGame.Save()` **1** = 操作员那次 sleep）；**起跑后**（>21:41:21）**672 行**：`Synchronizing 'NewDay'` **0** / `SaveGame.Save()` **0** / `after save, starting` **0** / `ERROR` **0** / `Disconnected` **0** | ✅ 同向（无 `NewDay`、无保存） |
| `logs\longrun-3day-llm-run6.console.err.log` | **0 字节** | ✅ 无未捕获异常 |
| console | 8190 B / 43 行，末三行 `[run] 账本：…` / `{"code": 1, …}` / `终态：needs_review（判据：observe?detail=full 的 tiles[]/clock 差分；回执一律不作证据）` | ✅ |
| Windows 事件 1000/1001 | 本轮窗口无新增 | ✅ 无原生崩溃 |
| 桥 | `bridge.json` mtime 21:43:05.731，`pid=27276`、`modVersion=0.7.25`；游戏进程 27276 存活；run6 PID 28240 **已退出** | ✅ |

### 4.1 `scratch\run6-external-snapshots.jsonl`

**`tag:"start"`（写于 21:41:56，起跑时刻口径）**：`smapi_lines 777`（`smapi_counts_filter: timestamp <= 21:41:21`）、`smapi_newday 1`、`smapi_save 1`、`smapi_total_lines 1393`；`save_main 3696701 / 20:37:37.898`、`save_info 26578 / 20:37:37.898`（两项 `overridden:true`，即用起跑前逐字节读数覆盖）、`journal_lines_at_start 0`；`pid 28240 / pid_alive true`；`bridge_info{pid:27276, modVersion:0.7.25, startedAt:2026-10-13T14:37:34+00:00}`；`expected_mod_version 0.7.25 / mod_version_matches true`；`version_sidecar`（= §1.2 原文）；`console{bytes:3877, lines:20}`；`console_err{bytes:0}`。

**`tag:"end"`（写于 21:43:27）**：`smapi_lines 1447`（`timestamp <= 21:42:20`）、`smapi_newday 1`、`smapi_save 1`、`smapi_total_lines 1453`、`smapi_mtime 21:41:59.207`；`save_main 3696701 / 20:37:37.898`、`save_info 26578 / 20:37:37.899`（**未 overridden，实测值**）；`journal_lines 143`、`journal_last_event "finish"`、`journal_finish`（= §2.1 的 finish 原文）、`journal_lines_at_start 143`；`pid 28240 / **pid_alive false**`；`bridge_info{pid:27276, modVersion:0.7.25, mtime:2026-10-13T21:43:05.731}`；`console{bytes:8190, lines:43}`；`console_err{bytes:0}`。

---

## §5 判据对照、结论与保留物

### 5.1 判据对照（`docs\_run6-criteria.md`）

| # | 判据 | 本轮读数 | 判定 |
|---|---|---|---|
| ① | 尾部连续 3 天 `ended_by=="sleep"` 且 `verified==true` 且跨日 +1 | 2 个日报告**全是 `stuck`**、`verified=false`、跨日 0 次 | ❌ **0/3** |
| ② | 禁用 `day_end.final.location=="Farm"` | 本文件与账本核对**都没用**该条 | ✅ 遵守 |
| ③ | `no_work` 收工的日子必须 `final_water.dry==0` | 本轮**无** `no_work` 日（两天都是 `stuck`）；`dry` 两天都是 `0/35` | n/a（如实记：`dry=0` 但收工理由是 `stuck`） |
| ④ | 0 次 `bridge_down`/`modal_timeout`/`watchdog_stop`/`no_day_progress`/`event_blocked`，0 崩溃 | `bridge_down`/`modal_timeout`/`watchdog_stop`/`event_blocked` 各 **0**；stderr 0 B；SMAPI 起跑后 `ERROR 0`/`Disconnected 0`；Windows 1000/1001 无新增；**但 `no_day_progress` = 1 次**（t=37.2，`ended_by=stuck`） | ❌（仅此项被踩） |
| ⑤ | 外部证据与账本同向 | 存档 size/mtime 未变、SMAPI 起跑后 `NewDay 0`/`Save 0`、`day_after` 两条 `null` —— 三者与「0 次跨日」完全同向 | ✅ 同向 |

### 5.2 结论

**FAIL（尾部连续 VERIFIED 0/3、0 次跨日、`exit 1`）**，属**干净快速失败**：`code=1`、37.2 秒、`stderr 0 B`、0 崩溃、0 掉线、0 模态阻断。踩到的硬项只有 ①（未达标）与 ④ 中的 `no_day_progress`（它是「游戏日没前进」的**正当停止路径**，但按卡面字面属被点名事件，如实记 ❌）。
**新机器件表现正常**：task-41 事件硬停未被触发（无 `eventUp`、无 `professionsToChoose`）；task-52/63 的不可达豁免**按设计**有界豁免（`bound:8`）并如实扣分，没有把不可达当硬失败；task-56 的留痕（`unreachable` / `unreachable_stage` / `unreachable_summary` / `stage_exhausted` / `no_day_progress`）齐备。

### 5.3 已知干扰项与处置去向

- **干扰项**：起跑前磁盘存档 mtime 是旧的（`20:37:37.898`，task-47 U2：日终保存被推迟/未落盘）—— 按 `docs\_run6-criteria.md` §2 不判失败也不判通过；`location.tilesTruncated=true`（400 格上限）影响田区统计覆盖度，已如实标注。
- **死因已派卡**：`task-67`（买种子按当前季节/在售清单：Mod 回执带结构化 `available[]`、脑侧挑最便宜且 `price ≤ money/10`、买不到记 `no_seed_for_sale` 且当天不再重试、并让守卫那条「没种子但钱够 ⇒ 该去买」当天失效）；`task-68`（不可达前先看 4 邻、邻格可清障就先清再重试目标格；修 `unreachable_bound` 口径——本轮 42 格 > `bound 8` 被误判超界）。§3.3 的四张坐标清单即 task-68 的输入。
- **不重跑**：run6 保留为 attempt #1；修完冻结 0.7.26 后由 Lead 发 run7。

### 5.4 保留物（不删）

`logs\longrun-3day-llm-run6.jsonl`（143 条）、`logs\longrun-3day-llm-run6.pid`、`logs\longrun-3day-llm-run6.version.json`、`logs\longrun-3day-llm-run6.console.log` / `.console.err.log`、`logs\longrun-3day-llm-run6-baseline.json`（起跑器副本）、`logs\run6-baseline.json`（权威）、`scratch\run6-external-snapshots.jsonl`（start/end）、`scratch\run6-quick.py`、`scratch\run6-watch.py`、`scratch\run6-snapshot.py`。

### 5.5 诚实声明

1. 本文件结论**只用观测差分**（`observe?detail=full` 的 `clock`/`tiles[]`/`inventory[]`）与外部证据（存档 size/mtime、SMAPI 行号、Windows 事件）；Mod 回执只作「它声称做了什么」，**不当成绩证据**。
2. 我**没有**退出游戏、**没有**重启续跑、**没有**改任何源码、**没有** deploy、**没有**替游戏做选择（`ShopMenu` 由长跑自己 dismiss；期间无 `eventUp`）。
3. 本文件由 machine-runner 独占撰写；若后续重跑，本文件保留为 **attempt #1**，重跑追加为新章节。
