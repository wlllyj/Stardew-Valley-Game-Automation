# 0.7.42 真机冒烟（8 步）—— 证据与结论

> 执行：machine-runner（真机独占）。被测装机：**0.7.42**（冻结提交 `9a23fcf`）。
> 目的：验 0.7.42 两个修复（task-240 冬季可验证性 / task-241 清障吞吐）+ 既有 7 步回归。
> 纪律：只读观测 + 有界 `use_tool`，不 `load_save`、不 craft/place/buy/sell；跑完立刻冻结 SMAPI + 记存档四件 + 优雅退出。

## §1 环境与版本

| 项 | 值 |
|---|---|
| 冻结提交 | `9a23fcf`（release: 冻结 0.7.42） |
| 执行时 HEAD | `f1fae26`（我的两份自测均已入库，工作树干净） |
| 游戏进程 | PID **24628**（StartTime 2026-10-18 14:01:47 前后；`bridge.json` pid 24628 / **modVersion 0.7.42** / port 17890） |
| 基线文件 | `logs/run10j-baseline.json`（Lead 的 `preflight --expect 0.7.42 --save-baseline` exit 0） |
| 基线读数 | 第 1 年 **冬 5 日 06:10 sunny** / Farm(64,15) / 体力 270/270 / 钱 2767g / 农场[草 0 · 石 106 · 枝 74 · **树 840** · 耕地 61 · 作物 0] / `waterLeft 13` / tillable 139 / farmingLevel 3 / 无模态 / worldAdvancing true |

**五文件指纹复核（我独立算，5/5 逐字一致，size 也一致）**

| 文件 | SHA256 | size |
|---|---|---|
| `brain/agentfarm/longrun.py` | `FE53408E79B808484E5BD6EB9A032D8916E691D253EC59926066B86CCE223898` | 573374 |
| `brain/agentfarm/farmwork.py` | `88E14811260363F606EFA55C688E8DDB46E6BF3A7DE1162E2CDC5645F38370A0` | 231217 |
| `brain/agentfarm/bridge.py` | `83A2F977B5EFAF9E6D7DDB43C3447921DCF79A758CCCA47AD659469CD2C064F6` | 68134 |
| `mod/.../AgentFarm.Bridge.dll` | `3FF867BF9D1549D5D05EB6D2B26A72EC19DF1E42C60EB4A09823523B869EAA19` | 286208 |
| `mod/AgentFarm.Bridge/manifest.json` | `9D316BB560E8222DB0375D61E24E3EA85BB4C0438A10060FE4E812EEB339EEA2` | 68962 |

## §2 八步结论总表

| 步 | 结论 | 一句话 |
|---|---|---|
| 1 | **PASS** | `debug_dump table=crafting_recipes key=Furnace` ⇒ `matchedCount=1`，无 `unknown_skill` |
| 2 | **PASS** | `debug_dump table=trigger_actions` 可读，无 `InvalidCastException`（逐表 fail-closed 的 type/error 在） |
| 3 | **PASS** | A2：`(40,14)` 首格即 `tree → None`（`use_tool_calls=1`），kind 变化即 progress |
| 4 | **PASS** | 2 日长跑跑出 `finish`（journal 149 行），`intent_coverage[]` 与 `-gaps.json` 都在 |
| 5 | **FAIL** | **75 个 `clear_area` ok 动作只有 62 个逐格证据**（9 个阶段 ok ≠ len(cleared_tiles)，合计缺 13 处） |
| 6 | **PASS** | `save-chain-check` 判六串 **2/2/2/2/2/2** 全配对、末次跨日已落盘 |
| 7 | **无法判定** | 冬季 0 作物 ⇒ harvest 子项无读数；整跑 **0 次 `slot_relief`**（通道未被触发） |
| 8 | **无法判定** | 8.1 **PASS** / 8.2③ **PASS** / 8.2② **PASS** / **8.2① 无读数**（整跑 0 条 `blocked`、0 条 `tool_ineffective`） |

**净结果：5 PASS / 1 FAIL / 2 无法判定 / 0 桥掉线 / 0 崩溃。**

## §3 步 1–3 读数

- 步 1：`table=crafting_recipes` 读到 `Furnace`（`matchedCount=1`），无 `unknown_skill`。
- 步 2：`trigger_actions` 可读；逐表 `fail-closed` 的 `type`/`error` 字段在场，无 `InvalidCastException`。
- 步 3（A2）：窗口内挑 `kind=="tree"` 且四邻有可站格的格 → `move_to(邻格)`（行走单独计）→ 只发 `use_tool(axe)`：
  - 目标 `(40,14)`，**`use_tool_calls=1`**、`kind_trace = tree → None`、`worldSeq` 前进、`kind` 变化即 PASS；
  - 体力 `270.0 → 258.6`（−11.4）。

## §4 步 4：2 日长跑（`logs/longrun-smoke-0742.jsonl`，149 条记录）

`finish` 原文：

```json
{"event":"finish","t":295.19,"code":1,"verified_streak":0,"actions":101,"minutes":4.92,
 "stages_seen":["clear_area"],"no_unmet_stages":true,"unmet_days":[],"stuck_flushes":0,
 "cleanup_modal_stuck":false,"cleanup_attempts":0,"cleanup_menu":""}
```

逐日（**3 个 `day_end`**）：

| 日 | ended_by | verified | ok/skip/fail | day_after | 关键 checks | 结局原因 |
|---|---|---|---|---|---|---|
| 冬 5 | `sleep` | **false** | 63/0/0 | `[1,winter,6]` | `no_hard_failures=true`、`day_justified=false`、`zero_action_evidenced=true` | `stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标（守卫仍说还有活：今天早些时候还有 122 格没做完（跨片地，最近的是 [56, 18]））` |
| 冬 6 | `sleep` | **true** | 12/0/0 | `[1,winter,7]` | `day_justified=true`、全绿 | `no_work:当季（winter）没有可种的种子：手上有 Wheat Seeds 但都隔季，而 farm 口径还有 51 格耕地空着 ⇒ 今天没有可做的活（证据：Mod player.seeds[].plantableNow）` |
| 冬 7 | `blocked_event` | **false** | 0/0/0 | `null` | `no_blocking_modal=false`、`day_justified=false` | `游戏事件挂住（eventUp=true）：?` |

- **冬 6 是本批核心成果**：`verified=true` 且 `day_justified=true`，收工理由为 `no_work`（冬季无当季种子）——**task-240 的「冬季可验证」在真机上成立**；`ended_reason` 里**不再出现**旧文案「耕地空着（手上有 N 粒种子）⇒ 该去种」（全账本 0 次命中）。
- **冬 7 是新情况**：`day_start` 后 `goto_farm` ok，但 `event_blocked{activeMenu:null, eventUp:true, dialogueIsQuestion:false, tile:[64,15], timeOfDay:600, worldSeq:602, advance_steps:0, note:"游戏事件挂住（ui.eventUp=true）：关框会替游戏推进剧情/默认选否 ⇒ 不 dismiss / 不 sleep / 不 load_save，当天不判 VERIFIED，等人处理"}` ⇒ 长跑**正确地停手上报**（不替游戏做选择），但也因此提前结束（4.92 分钟）。**该事件是什么、要不要处理，需 Lead 裁定**（不在本卡范围）。
- 观测快照（wait/launch 期间）：`winter5-t0`（14:03:41，trees **839**，worldSeq 51）→ `winter5-07120`（14:05:20，trees **828**，worldSeq 200）→ `winter6-07241`（14:07:21，trees **832**，worldSeq 461）。

## §5 步 5 FAIL：`clear_area` 逐格证据缺口（**真 FAIL，不是骨架 bug**）

- 合计：`clear_area` **ok = 75**，`cleared_tiles` **合计 62** 个格；**9 个阶段** `ok != len(cleared_tiles)`，合计差 **13**：

| 日 | ok | cleared | failed | leftover |
|---|---|---|---|---|
| 冬 5 | 7 | 6 | 0 | 0 |
| 冬 5 | 5 | 4 | 0 | 0 |
| 冬 5 | 3 | 2 | 0 | 0 |
| 冬 5 | 2 | 1 | 0 | 0 |
| 冬 5 | 5 | 2 | 0 | 0 |
| 冬 5 | 4 | 2 | 0 | 0 |
| 冬 5 | 2 | 1 | 0 | 0 |
| 冬 5 | 4 | 2 | 0 | 0 |
| 冬 5 | 2 | 1 | 0 | 0 |

- 形态：**每段 ok 都 ≥ cleared 的个数**，差值 1–3，`failed` 全 0 ⇒ 说明部分 `ok` 步的逐格清单**没被记账**（或同一格被多步算多次）。这正是步 5 要抓的"逐格证据不在场"，**判 FAIL**（未达成 task-241 的 `cleared_tiles`/kind 变化验收面）。
- 另有 2 段 `clear_area` `stopped="unreachable"`（`ok=0`、`leftover=145` / `leftover=2`），`stage_stop_named{cause:"unreachable"}` 原文如实带了 `assigned/assigned_undone/tiles/codes`。

## §6 步 6 PASS：跨日落盘守卫

- `scratch/save-chain-check.py --smapi logs/smoke-0742-smapi-window.txt --journal logs/longrun-smoke-0742.jsonl` ⇒ **PASS rc=0**：六串 **`NewDay 2 / before save 2 / SaveGame.Save() called 2 / Save task 2 / completed 2 / after save 2`**（L16 插件描述行按判别式排除），链内顺序 ✅、末次跨日已落盘。
- SMAPI 时点冻结：`logs/smoke-0742-smapi-window.txt` = **197032 B / 2071 行 / mtime 2026-10-18 14:08:48 / SHA256 `D0EEDBEA6C6BE1E0A4F9BEAA6BFD0244EFA53D1E16DBB888C123B90C8345ED72` / `BYTE_IDENTICAL=True`**（冻结后源文件继续长，**未**复冻）。

## §7 步 7 无法判定（两项，均"缺失≠通过"）

1. **`slot_relief` 0 次**：整跑没有触发空间压力通道 ⇒ "腾格"判据无读数（本批不判 PASS/FAIL）。
2. **冬季 0 作物**：`day_end.intent_coverage` 里没有 harvest 条目 ⇒ harvest 子项记**【无法判定·无作物】**（`--no-crops`，Lead m04309 授权，不改判）。
3. 其余可判部分：`deferred_by_budget` 2 条理由都合规（见 §8.3）；`policy_fallback` 2 条只放行 `clear_area`（`plant_area/till_area/water_area` 被挡 —— 冬季正常）。

## §8 步 8：0.7.42 三条硬判据

### 8.1 冬季可验证性 —— **PASS**
- 日报告 3 天中 **1 天 `verified=true`**（冬 6），`day_justified=true`。
- 旧守卫文案「耕地空着（手上有 N 粒种子）⇒ 该去种」**全账本 0 次命中**（正则扫全部 149 条记录）。
- ⇒ task-240 验收面通过。

### 8.2① 清障单发封格 —— **无法判定（无读数）**
- 整跑 `blocked` 记录 **0 条**、`tool_ineffective` **0 条** ⇒ 「单发 `tool_ineffective` 就封格」计数 = 0（**没有违规**），但也没有"合法放弃（`tool_ineffective_bound` 且 calls≥2）"的正样本 ⇒ 按"缺失≠通过"记**无法判定**，不判 PASS。
- 侧面证据：本批树是**真倒的**（`farm.trees` 839→828，−11 棵），说明 0.7.42 的"有界多次 `use_tool`"路径至少没有退化成单发即弃。

### 8.2② `farm.trees` 日降幅 —— **PASS**
- 冬 5 同日首末：**839 → 828（−11 棵，>2）** ⇒ PASS。
- 附带异常（**待解释，不影响本判据**）：冬 6 早晨快照 `trees=832`，比冬 5 末（828）**多 4 棵**。可能原因：`farm.trees` 语义含树桩/生长阶段变化，或两次全场扫描口径差异 —— 本卡未深挖，如实记录。

### 8.2③ 预算理由格式 —— **PASS**
- 2/2 条 `deferred_by_budget` 理由同时含「预算 N / 已砍 M」，原文：
  - `t=63.31`：`"why": "预算 10 棵 / 已砍 11 棵（体力驱动：可支配体力 128.8 ÷ 单棵 12，封顶 20）"`
  - `t=275.34`：`"why": "预算 8 棵 / 已砍 12 棵（体力驱动：可支配体力 102.2 ÷ 单棵 12，封顶 20）"`

## §9 骨架自身的两个 bug（如实记录，已修）

1. **8.2② 找不到观测文件**：`_capture_observe()` 把快照写到 `scratch/`，而 `_step8_trees()` 只 glob `logs/` ⇒ 第一次 `post` 报"没有可用观测"。修法：glob 同时收 `logs/` 与 `scratch/`。
2. **8.2② 排序把首末弄反**：按**文件名**排序时 `-t0`（起跑基线 839）排在 `-07120`（10:10 828）**之后** ⇒ 算出 +11 假 FAIL。修法：按快照里的 `captured_at` 排序（退化到 mtime）。
   ⇒ 两个都是**骨架 bug 不是判据 bug**；判据在修正后给出 `-11 棵 ⇒ PASS`。

## §10 收尾（优雅退出四项 + 存档四件）

- 存档四件（**退前 == 退后，size+mtime+SHA256(前16) 全一致**）：

| 文件 | size | mtime | sha256(前16) |
|---|---|---|---|
| `Wahaha_450799035` | 3134243 | 2026-10-18 14:08:28 | `E38D0771EFAB1D0D` |
| `SaveGameInfo` | 31566 | 2026-10-18 14:08:28 | `0735FF7DB77A5575` |
| `Wahaha_450799035_old` | 3172619 | 2026-10-18 14:06:38 | `DB0880884FD9BE47` |
| `SaveGameInfo_old` | 31317 | 2026-10-18 14:06:39 | `B6E4B75B3BBD789B` |

- `python tools/stop-game.py` ⇒ **rc=0**，`✅ 游戏已退出（原 pids=[24628]）`。
- 四项核对：`StardewModdingAPI` **进程 0** / `bridge.json` **已删** / `netstat :17890` **只有 3 条 TIME_WAIT、无 LISTENING** / 存档四件未变。
- SMAPI 冻结见 §6（退出前时点冻结，`BYTE_IDENTICAL=True`）。

## §11 结论与待裁事项

1. **0.7.42 的两个目标修复都有正面证据**：冬季可验证（冬 6 `verified=true` + `no_work` 正当理由）、清障吞吐（`farm.trees` 日降 11 棵、`deferred_by_budget` 理由带体力驱动预算）。
2. **步 5 是唯一真 FAIL**：`clear_area` ok 与逐格清单不一致（75 vs 62，13 处）⇒ 建议立案（dev-coder）核查 `cleared_tiles` 记账。
3. **步 7 / 8.2① 无读数**：`slot_relief` 未被触发、`blocked/tool_ineffective` 为 0 —— 不是失败，但也不该记 PASS。
4. **冬 7 `event_blocked`**：开局 `eventUp=true` 挂住的事件需要在下一轮 bring-up 前查清（是谁、要不要处理）；长跑行为正确（停手上报）。
5. `farm.trees` 冬 6 晨 +4 的异常待解释（不影响 8.2② 的 PASS 判定口径）。
6. **冒烟验管道不验成绩**：本批 `finish.code=1` / 尾部 0/2 是冬季无种子 + 中途事件所致，不据此判 0.7.42 冒烟失败。

## §12 保留物

`logs/longrun-smoke-0742.jsonl`（149 条）、`logs/longrun-smoke-0742-gaps.json`、`logs/smoke-0742-smapi-window.txt`（冻结）、`logs/smoke-0742-digest.txt`、`scratch/smoke-0742.json`（逐步结果）、`scratch/smoke-0742-observe-*.json`（3 份 full observe）、`scratch/smoke-0742-save-chain.json`；脚本 `scratch/smoke-0742.py`、`scratch/_smoke0742_digest.py`。

> 诚实声明：本卡没有做任何世界写入类技能（除步 3 一次有界 `use_tool`），未 `load_save`、未买/卖/种/放；所有结论都来自账本原文 + 独立观测 + SMAPI 原文 + 存档四件，缺数据处一律写【无法判定】。

## §13 步 5 判据按 task-242 收紧（2026-10-18，离线，提交 `926dddd`）

**新判据（写进 `scratch/smoke-0742.py` 的 `step5`）**：对每个 `day_end.stages[]` 里的 clear 类阶段（`CLEAR_STAGES = clear_area / clear_dead / clear_neighbor / frontier_clear`）：
- `len(cleared_tiles) == ok` ⇒ **conforming**；
- 否则若账本给了可解释的「目标格 / 连带格」区分（结构化字段 `target_tiles`/`collateral_tiles`/`cleared_targets`/`cleared_collateral`/`targets`/`extra_tiles` 之和等于 `len(cleared_tiles)+delta`，或任一计数等于 delta；或 `note`/`reason` 文案含「连带 / 一次多格 / 目标格 / 附带 / 顺手清 / 多格」）⇒ **explained**；
- 都不可解释 ⇒ **unexplained ⇒ FAIL**，并逐条列出 `ok / cleared / delta / attempted / engaged / ok_tiles / tiles / extra_keys`。

**反向夹具（真实账本，必须 FAIL）**：`python scratch\smoke-0742.py --phase post --only 5 --journal logs\longrun-smoke-0742.jsonl --tag selftest-0743 --no-crops` ⇒ **rc=10 / 步 5 FAIL**，9 个 clear_area 阶段全部 unexplained（`ok=7 cleared=6 差1`、`5/4 差1`、`3/2 差1`、`2/1 差1`、`5/2 差3`、`4/2 差2`、`2/1`、`4/2`、`2/1`；`extra_keys=[]` ⇒ 账本里没有新字段可解释）。原文落 `logs/selftest-step5-reverse.txt`。

**正向对照自测（新脚本 `scratch/_selftest_step5_0742.py`，离线、无游戏）**：`py_compile -W error::SyntaxWarning`=0；`--selftest` **STEP5 SELFTEST PASS 5/5** —— A 等值(ok=3/1, cleared 3/1)⇒PASS、B 结构化可解释(`target_tiles` 2 + `collateral_tiles` 3 = cleared 3 + delta 2)⇒PASS、B2 文案可解释(note「一次多格」)⇒PASS、C 不可解释(ok=5/cleared=3)⇒FAIL(列差异)、D 整跑无 clear_area ok 格⇒无法判定。

**机制发现（task-242 的定位依据）**：0.7.42 账本里那 9 个不等值阶段的字段显示 `ok == attempted == ok_tiles == tiles == bound_basis`，而 **`engaged` 恰等于 `len(cleared_tiles)`**（6/6、4/4、2/2、1/1、2/2、2/2、1/1、2/2、1/1）⇒ **`ok` 计的是"尝试成功"的格，只有 `engaged` 个格真的产生了世界变化，`cleared_tiles` 只收后者**。账本已有 `attempted`/`engaged` 两个字段但未在语义上声明「目标格 vs 实际变化格」，`cleared_tiles` 也不含未变化的目标格 ⇒ 这正是 task-242 要补的口径。

**部分复跑入口（0.7.43 用，无需改代码）**：`main()` 的 `--only` 分派是 `want & {1,2,3}`→pre、`4 in want`→launch+wait、`want & {5,6,7,8}`→post ⇒
- `python scratch\smoke-0742.py --phase all --only 3 --no-crops` ⇒ 只跑步 1–3（**不会起跑**）；
- `python scratch\smoke-0742.py --phase all --only 5,8 --journal logs\longrun-smoke-0743.jsonl --tag smoke-0743 --smapi logs\smoke-0743-smapi-window.txt --no-crops` ⇒ 只跑离线步 5/8。
保留纪律：冬季 0 作物 ⇒ 步 7 `harvest` 子项【无法判定·无作物】；`eventUp=true` ⇒ 当天停手上报、不判 VERIFIED。

**A8 同起点备份路径（无需改代码）**：`python scratch\arm-start-helper.py backup --arm A8` ⇒ `logs\ab-backup\A8-start\`（`BACKUP_ROOT = logs\ab-backup`、`--arm` 默认 `A7`，实测 `--selftest` 6 用例 PASS）。
