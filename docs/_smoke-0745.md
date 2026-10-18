# 0.7.45 冒烟门禁证据（task-18 / smoke-0745）

- 执行者：machine-runner（真机独占；只写 `docs/_run*-evidence.md`、`docs/_smoke-*.md`、`logs/`、`scratch/`）
- 执行时间：2026-10-18 18:57:34 – 19:16（本地时间，UTC+8）；游戏会话 SMAPI 日志 18:57:34 → 19:15:17
- 环境：Windows 11（10.0.26200.0）、Stardew Valley 1.6.15 build 24356、SMAPI 4.5.2、Mod **0.7.45**（冻结提交 `2feb1f8`，装机后桥自报 modVersion=0.7.45 port=17890）
- 存档：`Wahaha_450799035`；起跑前用 `arm-start-helper.py restore --arm A9` 还原到 A9 起点（第 1 年冬 26）
- 本文只交读数与证据；**门禁判决由 Lead 出**：Lead 已确认「FAIL（0/2 天 verified），A9 继续 hold」。

## §0 结论先行

1. **门禁 FAIL**：两个游戏日的 `day_end.verified` 都是 `false`（冬 26、冬 27 各 1 次 `day_end`，`verified_days=[]`）⇒ 步 8.1「冬季 ≥1 天 VERIFIED」**0/2，未转 PASS** ⇒ 按 GO「不达标就停」，**A9 不放行**。
2. 八步结果：步 3/4/5/6 **PASS**；步 1/2 本批未执行（GO 只要求 `pre --only 3`）⇒【无法判定·未执行】；步 7【无法判定·无作物】；步 8 **FAIL**（8.1 FAIL；8.2② 砍树 PASS；8.2①/③ 无法判定）。`scratch\smoke-0745.json` 汇总 rc=10。
3. 两日收尾形态（都如实留痕、都不是旧的 `stuck:` 掩盖，账本 `stuck:` 前缀 0 条）：
   - 冬 26：`ended_by=inventory_blocked`，ok 33、failed 0，「背包满（空格 1）且腾不出格子」；
   - 冬 27：`ended_by=sleep`，ok 210、failed 0，`resume_exhausted`：回片区 220 格都回去看过、换片 4 次，但守卫口径仍报「还有 7 格没做完」。
   - 两日 `checks.day_justified` 均为 `false` ⇒ `verified=false`。
4. 与 0.7.44 冒烟对照：**旧「stuck: 守卫仍说还有 263/217 格 vs plot_pending=0」的自相矛盾形态消失**（本跑 `stuck:` 0 条；`pending_ledger=230 = pending_executable 7 + pending_blocked 223`、`plot_pending=1 = 0+1` 不变式成立），**但两个失败日均未转 VERIFIED，步 8.1 仍未 PASS**（详见 §7）。
5. 看护：guardian 19:15:16 判据成立（脑死且 finish 已出现）→ `stop-game.py --wait 45` rc=0 → 进程 0 / `bridge.json` 已删 / 17890 无 LISTENING，guardian exit code=0（真机第二战闭环，证据 `logs\longrun-smoke-0745-guardian.log`）。
6. 两个必须单列的事实：① pre 步 3 首跑一次 FAIL 属**探针上限太紧**（该树需 21 刀，探针 3 次调用×≤6 刀不够），非产品回归，重跑 PASS（§9.1）；② 本跑卖出含 `(O)388 Wood`（×1/×31/×2/×46/×12），与 AGENTS.md「建材永不卖」冲突——按 Lead 裁决如实记录，另开 0.7.46 收紧，本文不为该行为辩护（§9.4）。

## §1 起跑四要素与装备

### 1.1 起跑 HEAD / argv（取自 `logs\longrun-smoke-0745.version.json` 原文）

| 项 | 值 |
|---|---|
| head | `3608593fa6fe6f51993e8dab300f44eaf6cf17f4`（0.7.45 冻结后 docs 提交） |
| worktree_clean | `false`（起跑工作树有别人的在制改动：`M tools/analyze-longrun.py`） |
| started_at | `2026-10-18T19:00:31` |
| boundary_llm / boundary_llm_model | `true` / 见 sidecar |
| journal | `D:\...\logs\longrun-smoke-0745.jsonl` |
| argv | `python -u tools/run-longrun.py --days 1 --size 5 --max-minutes 60 --max-days 2 --journal logs\longrun-smoke-0745.jsonl` |

### 1.2 五文件 SHA256（取自 sidecar 原文，未手抄）

| 文件 | size | mtime | SHA256 |
|---|---|---|---|
| `brain/agentfarm/longrun.py` | — | 18:51:47 | `FEC2FBD47E63CB1969487B06131435EC78604D7CC0A8B72176797A8A570EE12E` |
| `brain/agentfarm/farmwork.py` | — | 18:41:17 | `9FC2CAB5C06330029C80D528262D4B15F61DE142B1ABA029AB2416E381ACC77D` |
| `brain/agentfarm/bridge.py` | — | 18:54:03 | `66C2A5A5C8A8103078F4AB0BC8E495466253A6BD6FDE9D83B586699093D59A4B` |
| `mod/AgentFarm.Bridge/bin/Debug/AgentFarm.Bridge.dll` | 286208 | 18:54:09 | `806C1069D217EEEFAB6D3354BA09DA049847D97EE5B4A1D2D65845F1DCB0B17F` |
| `mod/AgentFarm.Bridge/manifest.json` | 73663 | 18:53:51 | `DECBA6775569D7C42DF910E7E6A72BC2CF59B1E2729C29484E700F6E786A2E5C` |

### 1.3 A9 起点还原（逐字节核对）

- `arm-start-helper.py verify --arm A9`（还原前）：备份 4/4 OK、当前档 4/4 MISMATCH、`VERDICT: DIFFER` rc=3（符合预期，当前档是 0.7.44 冒烟推进后的 winter28）。
- `arm-start-helper.py restore --arm A9` rc=0 `RESTORED`；再 `verify --arm A9`：**备份 4/4 OK、当前档 4/4 OK、`VERDICT: SAME` rc=0**。
- A9-start 存档四件（还原后未再写；跑完又核一次仍一致，见 §8.3）：

| 文件（`logs\ab-backup\A9-start\`） | size | mtime | SHA256 |
|---|---|---|---|
| `Wahaha_450799035` | 3141826 | 2026-10-18 17:03:52 | `053CAA71007CEA6FB20D865154DACA236C4FC69F314774B9AC118FB5188F4AF7` |
| `SaveGameInfo` | 32305 | 2026-10-18 17:03:52 | `3D964F3F30AF39C3F33CCCD210C7CC76760B569349A16F12AFC91BB8144B9293` |
| `Wahaha_450799035_old` | 3121459 | 2026-10-18 16:49:07 | `E5B60E915BA393E87FD053A05DFE87FDFAF0F838F8C724F4E50D5B026964B19E` |
| `SaveGameInfo_old` | 32472 | 2026-10-18 16:49:07 | `9DD16B9462C3A213CE9A924D9CF4A34DC8F61406908D877F5919D49812E69525` |
| `MANIFEST.json` | 1222 | 2026-10-18 18:02:55 | `5479354B0628D5B547C7B1670A9B5C36296594FD8F77EF53DA48AD9105988A3D` |

### 1.4 游戏与桥

- `tools\deploy-mod.py --no-quit` rc=0：Mod 0.7.45 已装机（版本不变），启动游戏并自动读档 `Wahaha_450799035`，地点 FarmHouse(9,9)。
- `bridge.json`：pid=1500、token=`1a5fb6a0596d4743b7915eeb6b94a1f4`、gameVersion=1.6.15、smapiVersion=4.5.2、startedAt=`2026-10-18T11:57:49+00:00`、文件 SHA256 `44CA59486A4A626895F84C45DAECC8BD001BABB576DB42277736CEC25984F08D`。
- 进程 1500 `StardewModdingAPI`（18:57:49 起）。

## §2 时间线与两日读数

### 2.1 时间线（本地时间）

| 时刻 | 事件 | 证据 |
|---|---|---|
| 18:57:34 | SMAPI 4.5.2 / SDV 1.6.15 build 24356 启动 | 窗口首行 |
| 18:57:48 | AgentFarm Bridge 加载 | SMAPI 窗口 |
| 19:00:22 | guardian 起（PID 20516，tag=longrun-smoke-0745，interval 10s / stall 180s / bridge_stale 120s） | `logs\longrun-smoke-0745-guardian.log:1` |
| 19:00:31 | 起跑器 launch 成功，脑 PID=2168 | `scratch\smoke-0745.json` 步 4 |
| 19:00:32 | guardian 首拍：脑活、桥在 ⇒ 正常 | guardian.log:5-6 |
| 19:02:10 / 19:04:10 | 观测 winter26（`trees` 900/900） | `scratch\smoke-0742-observe-winter26-24930/-25050.json` |
| 19:04:10 前后 | 冬 26 收尾（`inventory_blocked`，`sleep` L226 t=238.25 → 冬 27） | jsonl:226 / :231 / :232 |
| 19:06:11–19:14:11 | 观测 winter27（trees 898→893→892→891→891） | 5 份 observe 文件 |
| 19:15:05 | 账本最后一次写入（650 行） | guardian state JSON |
| 19:15:16 | 脑死且 finish 已出现 ⇒ trigger，执行 `stop-game.py --wait 45` | guardian.log:11-14 |
| 19:15:17 | SMAPI 收尾（`Disposing...`、删除 bridge.json） | 窗口末 3 行 |
| 19:15:18 | `stop-game` rc=0「游戏已退出（原 pids=[1500]）」 | guardian.log:19-20 |
| 19:15:46 | 冻结 SMAPI 窗口（源=副本，428250B） | `smoke-0745-smapi-window.txt` |

### 2.2 两日主表（`logs\longrun-smoke-0745.jsonl`）

| 日 | day_end 行 | ended_by | verified | ok / skip / fail | checks 为 false 的键 | unreachable | pending（七口径，见 2.3） | free_slots start/last/min | loot_lost_steps | stage_midway_leftover | 末刻 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 冬 26 | `:231` | `inventory_blocked` | **false** | 33 / 0 / 0 | `unreachable_within_bound`、`day_justified` | 32（bound 15 / exempt 12 / bound_basis 79） | ledger 3 / guard 3 / stalled 0 / exec 0 / blocked 0 / unobserved 3 / malformed 0 | 0 / 1 / 0 | **21** | 8 条 | 14:10，stamina 31.00023，钱 2767 |
| 冬 27 | `:647` | `sleep` | **false** | 210 / 0 / 0 | 仅 `day_justified` | 16（bound 61 / exempt 1 / bound_basis 308） | ledger 230 / guard 7 / stalled 218 / exec 7 / blocked 223 / unobserved 0 / malformed 0 | 0 / 0 / 0 | **205** | [] | 19:30，stamina 62.700172，钱 3264 |

- 两日 `plot_pending`：冬 26 = 15（till_area 15；executable 3 / blocked 12），冬 27 = 1（clear_area 1；executable 0 / blocked 1）。
- 两日 `assigned_undone`：冬 26 = 12，冬 27 = 1；`refused=0`；`encircled=0`。
- 两日 `stages` 记录数：冬 26 = 20 条；冬 27 = 74 条；两日 `stages[].failed` 全 0、`skipped` 全 0。
- 两日 `stamina_budget`：max 270 / capacity 126 / `deferred_by_budget=false` / `deferred_by_budget_suppressed=1`。
- 两日 `plots` 各 10 片：冬 26 锚点 `[4,4][21,16][20,23][20,23][16,16][6,23][2,34][5,45][5,46][5,51]`；冬 27 锚点 `[65,33][67,40][49,43][39,26][47,18][39,12][31,22][21,23][26,25][35,36]`。
- 冬 26 `stage_midway_leftover` 8 条（round 4/5/11/12/13/14/15/17，leftover 5/7/2/3/1/1/3/1——**记录在案、但日级口径以最后轮为准**；判据不因此放宽）。

> 口径说明：上表 pending 七口径来自 `day_end.pending_ledger/guard/stalled/executable/blocked/unobserved/malformed`；`plot_pending*` 是每阶段种类**最后一轮**的余格。冬 27 不变式成立：`7 + 223 = 230`（ledger）、`0 + 1 = 1`（plot_pending）。

### 2.3 两日 `ended_reason` 原文（不加工）

- 冬 26（`jsonl:231`）：
  `inventory_blocked:背包满（空格 1）且今天已经腾不出格子：不是没活、也不是 stuck —— 是背包堵住（先去出货/卖材料腾格，明天再收）`
- 冬 27（`jsonl:647`）：
  `resume_exhausted:回片区 220 格都回去看过、换片 4 次，当前观测里没有可执行目标（守卫仍说：今天早些时候还有 7 格没做完（跨片地，最近的是 [31, 42]））`

### 2.4 背包真值与交易读数

- 容量 12（未买背包升级），**12 格全占**（最新观测 `scratch\smoke-0742-observe-winter27-25651.json`）：5 工具（Axe/Hoe/Watering Can/Pickaxe/Scythe）+ `(O)309` Acorn×1、`(O)310` Maple Seed×10、`(O)378` Copper Ore×1、`(O)390` Stone×51、`(O)178` Hay×6、`(O)382` Coal×2、`(O)483` Wheat Seeds×10。`player.inventoryCount=12`。
- 交易：`sell` 事件 10 条（成功 9、失败 1）；失败 1 条为 `(O)310` Maple Seed `status=not_whitelisted`（`jsonl:8`）。
  - 冬 26 成功出货：`(O)262`×5（`:5`）、`(O)330`×3（`:35`）、`(O)92`×1（`:41`）、`(O)388`×1（`:61`）、`(O)388`×31（`:72`）、`(O)388`×2（`:81`）、`(O)388`×46（`:86`）、`(O)535`×3（`:95`）——出货箱 1→8 件。
  - 冬 27 成功出货：`(O)388`×12（`:238`）——出货箱 1 件。
  - 钱：2767g（冬 26 全天）→ 3264g（冬 27 06:00 NewDay 结算，+497）。
  - **`(O)388` = Wood（建材）共出货 5 次（×1/×31/×2/×46/×12）**：与 AGENTS.md「建材永不卖」冲突，按 Lead 裁决另开 0.7.46 收紧；本文只记读数（§9.4）。
- 空间压力通道（0.7.45 新留痕）：`slot_relief_noted`×2（`jsonl:4`、`:237`）、`slot_relief`×5（`:6`、`:9`、`:239`、`:257`、`:258`）、`inventory_blocked`×1（`:7`）。
  - `jsonl:7` 原文：`free_slots=0, reserve=1, rounds=1, limit=6, reason=「卖了 1 叠但背包行数没减少（12→12）⇒ 出货/卖出没有真的生效」`，note：`…不算 hard failure（no_slot 不是 failed），但 verified=false；守卫不再把「还有熟作物」当还能干活的理由`。
  - `jsonl:257` 原文：`剩下的可卖叠都是建造预留材料（铜矿/石头/煤），卖空会破坏熔炉/升级计划 ⇒ 宁可不腾格`。

### 2.5 掉落被拒收留痕（`loot_lost`）

- 冬 26：`loot_lost_steps=21`；坐标样例 `[10,13][10,12][9,13][6,16][7,14][7,13][5,17][10,9][6,13][3,16][8,10][6,12][20,25][23,23][20,26][24,23][22,25][24,24][10,27][9,27][8,27]`；`loot_lost_items=[木材, 树液, （可能）硬木, 纤维, （可能）干草, 石头, （可能）矿石]`。
- 冬 27：`loot_lost_steps=205`（坐标全集见 day_end 原文）。
- 语义：`free_slots=0` ⇒ 掉落被原版游戏拒收（Inventory Full），只留痕、不判失败。

### 2.6 finish（`jsonl:650` 原文）

```json
{"event": "finish", "t": 874.13, "code": 1, "verified_streak": 0, "actions": 420, "minutes": 14.57,
 "stages_seen": ["clear_area", "plant_area", "till_area"], "no_unmet_stages": true, "unmet_days": [],
 "stuck_flushes": 0, "cleanup_modal_stuck": false, "cleanup_attempts": 1, "cleanup_menu": "ShippingMenu"}
```

- 控制台（`logs\longrun-smoke-0745.console.log`）：`:54`「× 试了 2 个游戏日仍未凑出连续 1 天，停下」；`:56`「[run] needs_review：尾部连续 0/1 天（共 2 天，420 个动作，14.57 分钟）」；`:74` 终态 `needs_review`。
- 账本 `stuck:` 前缀事件 **0 条**；`守卫仍说` 文本仅 1 处（冬 27 的 reason，见 §2.3）。

## §3 `day_justified` 机制与代码锚点（0.7.45 当前工作树）

- `brain/agentfarm/longrun.py:553` `JUSTIFIED_END_REASONS = ("night", "stamina", "no_work")`
- `brain/agentfarm/longrun.py:567` `HONEST_EXHAUSTED_END_REASONS = ("resume_exhausted",)`
- `brain/agentfarm/longrun.py:570-600` `def is_justified_end(ended_by, ended_reason, *, pending_executable=None, malformed_tiles=None)`：
  - `:597` 前缀在 `JUSTIFIED_END_REASONS` ⇒ 正当（与旧实现逐字一致）；
  - `:600` 前缀 `resume_exhausted` 且 `pending_executable == 0`（且 `malformed_tiles==0`）⇒ 正当；`pending_executable is None` 视为证据不可用、不放行；
  - 其余前缀（`stuck` / **`inventory_blocked`** / `gave_up_*` / `no_water` / `no_plot` …）**照旧不放行**。
- 写 `resume_exhausted` 的证据面：`:4100-4147` `_resume_exhausted()`（`:4115` 并列记录 `pending_guard`；`:4135` `pending_executable/pending_blocked`；`:4140` note；`:4147` reason 前缀原文）——**只有当前观测里可执行格为 0 时 `day_justified` 才认**。
- `inventory_blocked` 收尾：`:6328-6346` `_end_inventory_blocked()`（`ended_by/ended_reason` 写 `inventory_blocked:`）；`:6087-6111` `_note_inventory_blocked()`；`:6900` `checks.slept_by_us = slept_ok or ended_by in ("sleep","inventory_blocked")`；`:5611-5615` `sleep_guard` 的 `inventory_blocked` 分支。
- `_pending_work()`：`:4944`；日终可执行面快照：`:5048-5103`；`checks.day_justified` 计算：`:9618-9624`。
- 结论（机制层，不是判决）：本跑的两天 `day_justified=false` **符合 0.7.45 的设计语义**——冬 26 的 `inventory_blocked` 不在白名单（且 `pending_unobserved=3` 也 fail-closed），冬 27 的 `pending_executable=7>0` 使 `resume_exhausted` 不获认。0.7.45 宁可不 VERIFIED，也不洗白。

## §4 八步判定（`scratch\smoke-0745.json`，rc=10）

| 步 | 内容 | 判定 | 读数 |
|---|---|---|---|
| 1 | crafting_recipes 自检 | 【无法判定·未执行】 | 本批 pre 以 `--only 3` 执行（GO 指定门禁子集）；`results_all_steps` 现存 6 步（3–8）。0.7.44 冒烟已单独验过步 1/2，但不能跨版本当 0.7.45 读数 |
| 2 | trigger_actions 自检 | 【无法判定·未执行】 | 同上 |
| 3 | 单技能砍树 | **PASS** | `(13,16)` kind tree→None，`calls=1`；走位 move_to 5622ms ws70→95；`tree_tiles_in_window=211`、有可站邻格 72；`stamina 234.29994→232.59995`；receipt `acted=true / actedEvidence=tile / elapsedMs=509` |
| 4 | 2 日起跑 | **PASS** | pid=2168、journal 650 行、last_event=finish（`obs_files=0` 因观测在 wait 阶段写入，自评不碍） |
| 5 | task-242 逐格判据 | **PASS** | `clear_stage_total_ok=243`，等值阶段 72 个、可解释阶段 0 个、未解释 0；两日 `day_end_count=2` |
| 6 | 跨日落盘守卫（六串） | **PASS** | `save-chain-check.py` rc=0；counts `2/2/2/2/2/2`（`save_called` 原始 3，L16 插件描述行假阳性排除 1）；行号见 §5 |
| 7 | analyzer §8 无红 + slot_relief 证据 + harvest | 【无法判定·无作物】 | `slot_relief` 子项 **PASS**（5 条，`demand/target_free/reached` 齐全）；`harvest_ok` 无法判定（`--no-crops`：冬季农场 `crops==0`，`intent_coverage` 无 harvest 条目）；`intent_reconciliation`：intents 133 / zero_step 45 / `zero_step_no_reason=0` / `plans_no_reconciliation=0`；analyzer 输出无 `missed:intent_no_reason:*`；`gaps.json` 存在；`analyze_rc=1`、`verify_rc=1`（尾部连续 VERIFIED 0/2） |
| 8.1 | 冬季可验证性 | **FAIL** | `winter: {day_end: 2, verified_days: [], guard_text_hits: [], guard_text_hits_total: 0, status: FAIL, reason: 「2 个日报告里没有一天 verified=true（冬季必须能验证）」}` |
| 8.2① | 单发 tool_ineffective 封格=0 | 【无法判定】 | `blocked_tool_ineffective=0`、`illegal_total=0`、`legal_total=0` ⇒ 整跑无该类读数（缺失≠通过） |
| 8.2② | farm.trees 日降幅 >2 | **PASS** | `best_delta=-19`：winter26 first 902/last 900（-2，n=13）、winter27 910→891（**-19**，n=9）；另有 winter5 839→828（-11，n=2）来自 **0.7.44 冒烟遗留的旧观测文件**（污染，见 §9.3） |
| 8.2③ | 预算理由文案 | 【无法判定】 | 整跑无 `deferred_by_budget` 事件 ⇒ 无读数 |

## §5 六串配对与 SMAPI 冻结窗口

### 5.1 冻结窗口

- 文件：`logs\smoke-0745-smapi-window.txt`
- 源：`C:\Users\admin\AppData\Roaming\StardewValley\ErrorLogs\SMAPI-latest.txt`（size 428250，mtime 19:15:17）
- 副本：size 428250，mtime 19:15:46；**源与副本 `BYTE_IDENTICAL=True`**
- **SHA256：`A24EB3D59C97F9F422A24C5BB58911418CA6B6B6FCAF1A7A37A50F7F43441780`**
- 行数 4631（窗口内带时间戳行 4625）；首行 18:57:34 SMAPI 4.5.2 / SDV 1.6.15 build 24356；末 3 行 19:15:17 `Disposing...`、删除 bridge.json、`Disposing the content coordinator`
- 桥行共 3900 条：health 102 / exec 1420 / observe 2353；`exec` ≥5s 共 30 条，最大 `29788ms @19:03:34 worldSeq=458`（其余：22462ms@19:10:55 ws1679、22344ms@19:10:32 ws1578、21162ms@19:03:57 ws548、14058ms@19:04:26 ws623、13353ms@19:14:55 ws2368、12311ms@19:11:38 ws1817、12182ms@19:11:25 ws1763、11846ms@19:11:50 ws1869、11103ms@19:14:10 ws2254、10205ms@18:58:27 ws56）

### 5.2 六串（`scratch\smoke-0745-save-chain.json` + checker 原文）

| 串 | 次数 | 行号 |
|---|---|---|
| NewDay | 2 | `[1871, 4608]` |
| Context: before save | 2 | `[1881, 4615]` |
| SaveGame.Save() called | 2（原始 3，L16 假阳性 1） | `[1882, 4616]` |
| Synchronizing 'Save' task | 2 | `[1883, 4617]` |
| completed without exceptions | 2 | `[1886, 4620]` |
| Context: after save | 2 | `[1888, 4621]` |

- 链内顺序 ✅：2 次保存链均满足 before < called < [task] < completed < after；**末次跨日已落盘**（末次 NewDay 行 4608 / Save called 4616 / after save 4621）。
- checker 同时复核账本：650 行 / day_end 2 / verified `[False, False]` / finish True。
- `VERDICT: PASS（退出码 0）`。

## §6 HUD 异常观察（按 Lead 口径单列）

- 本轮**未复现**红字「Inventory Full」HUD：SMAPI 冻结窗口里 `HUD` / `No space` / `inventory full` 命中 **0**；`Inventory` 仅 1 处命中（第 16 行，Mod 0.7.45 发布说明文本，非 HUD 日志）⇒ 无第二证据源。
- 账本无 HUD 事件；`loot_lost` 只是 0.7.45 新留痕字段（`free_slots=0` ⇒ 原版拒收掉落），**不能当成 HUD 红字的证据**。
- 结论：**【无法判定】**（缺独立观测；不写成「已消失」）。
- 若后续复现，按 Lead 口径记录：真实时刻 + 游戏 clock + journal 末 5 行 + SMAPI 前后 5 行（尤其 `POST /v1/exec` 耗时与 worldSeq）。

## §7 0.7.44 冒烟的两个失败日：是否转 PASS（明确结论）

> 结论先行：**都没有转 PASS。** 0.7.44 冒烟的两个失败日（冬 26 `stuck:263`、冬 27 `resume_exhausted:217`）在 0.7.45 里换了形态、口径矛盾消除，但两日 `verified` 仍为 `false`，步 8.1 仍 FAIL。

| 对照项 | 0.7.44 冒烟 | 0.7.45 冒烟（本跑） | 判决 |
|---|---|---|---|
| 冬 26 收尾形态 | `stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有 263 格…）` | `inventory_blocked:背包满（空格 1）且今天已经腾不出格子…`（新留痕、非 stuck） | 形态改变，**未转 PASS**（verified=false） |
| 冬 27 收尾形态 | `resume_exhausted:…守卫仍说还有 217 格`；`pending` 与 `plot_pending=0` 自相矛盾 | `resume_exhausted:…守卫仍说还有 7 格`；`pending_ledger 230 = exec 7 + blocked 223`、`plot_pending 1 = 0+1` 不变式成立 | 口径矛盾消除（PASS），**当日未转 PASS**（`pending_executable=7>0`） |
| `stuck:` 事件数 | 2 条（旧形态） | **0 条** | 旧形态消失（改善） |
| 步 8.1 冬季可验证性 | FAIL（0/2） | **FAIL（0/2）** | **未转 PASS** |
| 步 8.2② 砍树 | PASS（best -19） | PASS（best -19） | 保持 PASS |
| 步 7 | 【无法判定】（无 slot_relief 留痕 + 无作物） | 【无法判定·无作物】（`slot_relief` 子项已 PASS） | 仍无法判定 |

- 残留缺口（读数，不含判决）：冬 27 守卫口径 `pending_executable=7`（`no_progress_burst` `jsonl:641`：`tiles=7`、`samples=[[30,47],[31,42],[31,43],[31,46],[31,47],[31,48],[31,49],[37,36]]`、`pending 225`、`stalled_tiles 220`、`switches 4`、`farm_actions_today 311`）而回片区/换片后当前观测无执行格 ⇒ 可执行面证据与守卫口径仍有语义差。
- 另：冬 26 的 `inventory_blocked` 是 0.7.45 的**设计性非达标**（不在 `JUSTIFIED_END_REASONS`，且 `pending_unobserved=3`），不算产品 bug，但意味着「背包 12/12 满 + 无可腾格」会稳定吃满整日且当日不 VERIFIED——A9 若继续用该存档起点，这个条件大概率还会出现（§11）。

## §8 收尾四项

### 8.1 优雅退出与复核

- guardian 判据（`logs\longrun-smoke-0745-guardian.log:11-12`）：`brain pid=2168 alive=False · journal lines=650 last=finish@874.13 finish=True` ⇒ `trigger=True`，原文「判据成立：脑死 且 finish 已出现」。
- 执行：`python -u tools\stop-game.py --wait 45.0`（`:14`）；桥就绪 modVersion=0.7.45 ⇒ `quit_game` 回执 ok（`:16-18`）；`✅ 游戏已退出（原 pids=[1500]）`（`:19`）；`rc=0`（`:20`）。
- 复核（`:21-23`）：`进程数=0`、`bridge.json exists=False`、`17890 LISTENING=False`；guardian `[exit] code=0`（`:24`）。事后 `netstat` 仅剩 `:17890` 的 TIME_WAIT（无 LISTENING）。

### 8.2 跑后存档四件（游戏在 19:15:01 落盘 winter 28；**不是 A9 起点**）

| 文件（`%APPDATA%\StardewValley\Saves\Wahaha_450799035\`） | size | mtime | SHA256 |
|---|---|---|---|
| `Wahaha_450799035` | 2948770 | 19:15:01 | `6DE8419B098EA16972C7DB761F4080127599523A2C1AD8EC5A6176F86861B594` |
| `SaveGameInfo` | 32264 | 19:15:01 | `B5B51971BFF129EDE468D2671731A50B0D0A7964755AE7AB5643AEF07A7310A1` |
| `Wahaha_450799035_old` | 3137234 | 19:04:33 | `1695C1ED3286601FD951837AD0D4363EA45542024E01CD0B4F45B26FD453509D` |
| `SaveGameInfo_old` | 32259 | 19:04:33 | `BCC85C1B47EE63CE043EDE9668EA44E76D67867DD1C5E1CBCB4392D3AAE57DAA` |

### 8.3 A9-start 备份跑后再核（未动）

`MANIFEST.json` 1222B `5479354B…988A3D`；四件 size/SHA256 与 §1.3 完全一致（mtime 仍 17:03:52 / 17:03:52 / 16:49:07 / 16:49:07）。A9 起跑前仍需 `restore --arm A9`（当前档已被冒烟推进到 winter28）。

## §9 机械事实与缺陷清单

### 9.1 探针缺陷：pre 步 3 首跑 FAIL（**非产品回归**）

- 首次 `--phase pre --only 3 --tag smoke-0745` **FAIL rc=10**：目标树 `(32,17)`，走到 `(31,17)`（move_to 10191ms ws11→56），连续 3 次 `use_tool`（每次收到 ≤6 刀）后 `kind` 仍是 `tree`；3 条 `BridgeError: [tool_ineffective] …「Axe」挥 6 次无效…`；候选树 216 格、其中 32 格有可站邻格。
- 诊断（`scratch\_t18_step3_probe.py`，只读+正常砍树）：发现 `tiles[]` 的坐标键是 `tile:[x,y]`；**手动第 4 次 `use_tool axe (32,17)` 直接成功**（`elapsedMs=1528`、`worldSeq 67→67`、`acted=true`，reason 原文「已用「Axe」对 (32,17) 动手 3 次（起手=是）…现在**上面已经没有东西了**（kind=「none」）」）。
- 结论：该树共需 21 刀（3 次探针调用 18 刀无效 + 第 4 次 3 刀倒），**探针的「3 次调用上限」太紧**；Mod dll 与 0.7.44 逐字节同、0.7.45 Mod 无代码变更 ⇒ 不是产品回归。按纪律「骨架/探针自己的 bug 与产品 bug 分开判」，记录探针缺陷，不改判产品。
- 重跑 `--phase pre --only 3 --tag smoke-0745` ⇒ **PASS**：`(13,16)` tree→None，`calls=1`。两次 pre 结果都在 `scratch\smoke-0745.json`（`phases_run=[pre,pre]`）。

### 9.2 读取与编码

- guardian 日志本身是 UTF-8 且内容正常（`read` 工具直接读无乱码）；在 PowerShell 里用 `Get-Content` 直接读会按 cp1252 解码出现 `PID æ–‡ä»¶ç¼ºå¤±` 之类 mojibake——那是**读法**问题，不是文件损坏。证据引用以 `read` 工具/state JSON 为准。

### 9.3 观测文件污染（步 8.2② 的 winter5 行）

`scratch\smoke-0742-observe-winter5-t0.json` / `winter5-07120` / `winter6-07241`（mtime 14:03–14:07）是 **0.7.44 冒烟时期**的遗留观测，被步 8.2② 计入 `observations=26`、`days_with_two_obs=3`。本轮真实观测 9 份（winter26 t0/24930/25050；winter27 25170/25291/25411/25531/25651）。步 8.2② 的 PASS 由 winter27 `-19` 决定，**不受旧文件影响**；但「26 份观测」不能当作本跑样本数。

### 9.4 交易纪律读数（只记录、不辩护）

- `sell` 事件 10 条（成功 9）中，`(O)388`（Wood，建材）出货 5 次：`jsonl:61`（×1）、`:72`（×31）、`:81`（×2）、`:86`（×46）、`:238`（×12）。
- 这与 AGENTS.md §5「工具/武器/种子/建材/锭类永不卖」冲突；Lead 已裁决按纪律收紧、另开 0.7.46 卡。本文只如实记录读数。
- 其余成功出货：`(O)262`×5、`(O)330`×3、`(O)92`×1、`(O)535`×3；失败出货：`(O)310` Maple Seed `not_whitelisted`。出售全部走 shipping bin（出货箱），无直接改钱。

### 9.5 工作树与提交

- 起跑 sidecar `head=3608593`（`worktree_clean=false`）；运行期间/之后仓库 HEAD 前进到 `9732aed`（log-analyst 的 analyze 提交，与本跑无关，生产五文件未变）。
- 本任务新增只读取证脚本（scratch/，`.gitignore` 白名单 `!scratch/*.py`）：`_t18_smoke_evidence.py`、`_t18_dayend_brief.py`、`_t18_steps_brief.py`、`_t18_anchor_probe.py`、`_t18_step3_probe.py`。

## §10 命令原文与产物哈希

### 10.1 命令（PowerShell，`$env:PYTHONUTF8=1`；Python 用 DSH 运行时）

```powershell
& $py -u tools\arm-start-helper.py verify --arm A9
& $py -u tools\arm-start-helper.py restore --arm A9
& $py -u tools\deploy-mod.py --no-quit
& $py -u scratch\smoke-0742.py --expect-version 0.7.45 --phase pre --only 3 --tag smoke-0745
& $py -u tools\run-guardian.py --tag longrun-smoke-0745 --detach
& $py -u scratch\smoke-0742.py --expect-version 0.7.45 --phase launch --tag smoke-0745 --days 1 --size 5 --max-minutes 60 --max-days 2 --capture-observe --observe-every 120 --no-crops
& $py -u scratch\smoke-0742.py --expect-version 0.7.45 --phase wait --tag smoke-0745 --wait-minutes 60 --capture-observe --observe-every 120 --no-crops
& $py -u scratch\smoke-0742.py --expect-version 0.7.45 --phase post --tag smoke-0745 --freeze-smapi --no-crops
```

- 另：`scratch\_t8_goto_farm.py`（步 3 前置，FarmHouse→Farm）、`scratch\save-chain-check.py`（步 6 checker）、`tools\stop-game.py --wait 45`（guardian 自动调用）。

### 10.2 产物哈希（size / SHA256）

| 文件 | size | SHA256 |
|---|---|---|
| `logs\longrun-smoke-0745.jsonl` | 450865 | `911F2CE5A355C56426302718927829CBC924AF97FB472CB45384608A0EB44B27` |
| `logs\longrun-smoke-0745.version.json` | 1594 | `FADF2FE7A3C4BE18C24F75EAB8DD4796C6BCC6058EB2713564523CACA18FB637` |
| `logs\longrun-smoke-0745.console.log` | 9202 | `75B98834AD92E75FC831A91A7FCB08CDBD30217038ACC756DD38EF33A02E9561` |
| `logs\longrun-smoke-0745.console.err.log` | 0 | （空） |
| `logs\longrun-smoke-0745-gaps.json` | 1558 | `BDC5241D6EDA9C43BF869016ABA68AAC7A8FE98D11CABE940DBA56AA3D653019` |
| `logs\longrun-smoke-0745-lessons.json` | 2505 | `284166A128952B9E8F9560273C565008966E53EE28839C85F542F870DA908751` |
| `logs\longrun-smoke-0745-llm.jsonl` | 13833 | `2AB8E01212B3F7CC5809E835630221D20746C1F93035C92E49D181D0A4D0EFBE` |
| `logs\longrun-smoke-0745-baseline.json` | 705 | `4612671C0534F2258D59FF44979B8E0F75B7FD67A26F125C14B3AB61FD0432C1` |
| `logs\longrun-smoke-0745-guardian.log` | 2999 | `DDCEA76D869AF41DEFF84603CADD4E813CF5325B39F4C6AF6097817F2354AD53` |
| `logs\longrun-smoke-0745-guardian-state.json` | 2205 | `C39DA4628AC3D4D2E8AE5AE80DB0B5BC38C83923F69CF38AB57C2658610F09A1` |
| `logs\longrun-smoke-0745-guardian.console.log` | 2519 | `BDF59130F7CC50E94BF2C29D9BCEC990D0559185511517230278EE94DE66D335` |
| `logs\longrun-smoke-0745-guardian.pid` | 5 | `D2D55578A18B43224206AF02B14D8ACFB63786F29E4D0D30D5DE2DB317170C67` |
| `logs\smoke-0745-smapi-window.txt` | 428250 | `A24EB3D59C97F9F422A24C5BB58911418CA6B6B6FCAF1A7A37A50F7F43441780` |
| `scratch\smoke-0745.json` | 71874 | `C79048B2E45CCC91E87B6396B77FF912D047D9917117A70A29EBED1B954BA3F4` |
| `scratch\smoke-0745-save-chain.json` | 2932 | `196F6BB2DE54CDD6C0B44DDD9F59DC8FF08A0B504CD44F52A85C62620BB5FD77` |
| `scratch\_t18_smoke_dayend.txt`（两日 day_end 全文） | 318935 | `74B48B62EAE86CB2617E529D58F8F430FA21CD18B70635A639B1507CDA8F2434` |
| `scratch\_t18_smoke_lines.txt` | 92345 | `4236F93E8767F42DEC74D0DA1E940A3D0F3E1F214BB135A0445D1A20ACBB1FAD` |

## §11 已知限制（如实）

1. **门禁判据未满足**：8.1 要求「冬季 ≥1 天 verified=true」，本跑 0/2；按 GO 已停，A9 未起跑、未 restore。
2. **冬 26 是设计性非达标**：`inventory_blocked` 不在 `JUSTIFIED_END_REASONS`；且当天 `pending_unobserved=3`。该形态不是缺陷，但它与「12/12 满背包 + 无可腾格」绑定，若 A9 沿用同一存档起点，出现概率高（A9 的 5 天判据要求 5/5，1 天这种收尾即不达标）——建议 Lead 在放行 A9 前决定：先解决背包容量/起点背包（0.7.46 卡）或把 A9 的起点调整到「有空格」的可比状态；本文不擅自改起点。
3. **冬 27 残留语义缺口**：`pending_executable=7`（守卫口径）与「回片区 220 格/换片 4 次后当前观测无执行格」并存 ⇒ `day_justified=false`。账本口径已自洽（`7+223=230`），但守卫仍把 7 格当「还能干」。
4. **HUD【无法判定】**：见 §6；无第二证据源。
5. **步 1/2 未执行**（本批 `--only 3`）⇒ 无法判定；步 7 的 harvest 子项、8.2①/③ 均无读数（缺失≠通过）。
6. **观测样本污染**：3 份 0.7.44 遗留观测混入步 8.2②（已注明，但 `observations=26` 不是本跑样本数）。
7. **存档终态是 winter 28**，不是 A9 起点；A9 起跑前必须 `restore --arm A9`（A9-start 已核未动）。
8. **本跑工作树非冻结态**：起跑 sidecar `worktree_clean=false`（别人在制 `tools/analyze-longrun.py`）；生产五文件哈希与冻结一致，但严格意义上不是 `git archive` 冻结树。
9. 本文不给出 A9 是否放行的判决；门禁结论由 Lead 出（已由 Lead 确认 FAIL / hold）。
