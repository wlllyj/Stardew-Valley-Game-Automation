# run9c 真机验收证据（0.7.30 上的 run A）

- 别：task-140（machine-runner）；产物：本文件 + `logs\run9c-*` + `scratch\run9c-*`
- **定位声明**：Lead m02015 已定 —— run9c **不作为 A/B 对照的 run A**（0.7.31 会改 `brain/`，两次 run 世界不可比）；run9c 只作**诊断跑**，A/B 改在 0.7.31 上重跑（run9d = run A、run10 = run B）。本文件的所有数字**照实记录，不因定位而删改**。
- 本跑结束时**未退游戏**（按卡面纪律，等 Lead 决定）。

## §0 一句话结论

**达标（VERIFIED）**：尾部连续 3 天（`summer 20/21/22`）`verified=true`；`finish = {"code":0,"verified_streak":3,"target_days":3,"actions":513,"minutes":28.03,"unmet_days":["1年 summer 18日"],"stuck_flushes":0}`。
- **落盘五串 5/5 配对**（NewDay → before save → SaveGame.Save() called. → Save task → completed，5 次跨日全配对）且**存档逐次前进**（`5766683 / 22:30:13` → `3860602 / 00:16:44.786`）。
- **经济闭环四腿真机跑通**：`sell` → 次日到账 → `buy` 成交 → `plant_area` 落格。
- 两侧工具同向：`tools\verify-run3.py` **rc=0 / VERIFIED**（尾部窗口 3/3，窗口内 problems 0）；`tools\analyze-longrun.py` **rc=0 / 有红 0 条**。
- `scratch\run9-lead-check.py` **rc=1**，但两条 ❌ 都是 **L16 插件描述行**把 `SaveGame.Save() called.` 计数从 5 抬成 6 的**工具假阳性**（§3.2 逐字点名），不是世界问题。
- 未达标/未尽事项：`summer 18` 因 `no_unmet_stages=false`、`summer 19` 因 `watered_outdoor=false` 各有一天未 VERIFIED（尾部窗口之外，`verify-run3.py` 记为 `history_problems` 4 条）；`summer 20` 是 23 秒真空短日、**没抓到独立观测**（§5.5 显式写【无法判定·窗口错过】）。

## §1 起跑与版本四要素

### 1.1 起跑前置（Lead 实测，我方引用）

| 项 | 值 |
|---|---|
| 冻结提交 | `aa3ceaf96e5dde34b7fedd84e1f695a868328aaf`（0.7.30 冻结：water_far 逐格判据/补水 task-133 + resume 有界与 leftover 口径拆分 task-134 + 演进素材质量 task-136） |
| `check-release --expect 0.7.30` | 六项全绿（`manifest==brain==0.7.30`、dll 不旧、`py_compile` 22 文件、**`Ran 776 tests` OK**、树干净） |
| 装机 | `deploy-mod --no-quit`：0.7.29 → **0.7.30**（`AgentFarm.Bridge.dll` 177664 B / `manifest.json` 30277 B；**Mod 本版无源码改动，只 bump**）；桥 `modVersion=0.7.30 port=17890`；自动读档 `Wahaha_450799035` → FarmHouse(9,9) |
| `goto Farm --no-focus` | FarmHouse(9,9) → Farm(64,15)，hop1 **7594ms** ok（`source=[3,12] landing=[64,15]`） |
| `preflight --expect 0.7.30 --save-baseline logs\run9c-baseline.json` | **✅ 可以起跑**；基线：**第1年 夏18日 06:10 / rain / Farm(64,15) / 体力 270 / 钱 205g / 种子 [] / farmingLevel 0 / 作物 55 / unwatered 34 / dryCrops 0 / waterLeft 8 / tillable 72 / 无模态 / worldAdvancing true** |
| 操作员预置 | **不做**（钱 205g + 无种子正是经济闭环验收面） |

### 1.2 起跑命令与版本四要素（`--dry-run` 与真起跑一致）

```
python tools\start-detached-longrun.py --days 3 --size 5 --max-minutes 150 --max-days 9 \
  --journal logs\longrun-3day-llm-run9c.jsonl --expect-version 0.7.30
```

| 要素 | 值 |
|---|---|
| `--dry-run` | 四判据全绿（装机版本 0.7.30 / 已读档 / 在户外农场 / 无阻断模态），基线 `夏18日 tod 750`、`worldSeq 21` |
| HEAD | `aa3ceaf96e5dde34b7fedd84e1f695a868328aaf` |
| `brain/agentfarm/longrun.py` | `12C6D0217013C39A5EF9534E7ECC78CBB83B67A7B5237B9AF21494EE1CD0D622` @ `2026-10-16T23:16:05.484063` |
| `brain/agentfarm/farmwork.py` | `4A39BC11ABCA3413D1608CCD58CC1F070CEA9F85EAB4AA87E809ED5E686C2D80` @ `2026-10-16T21:45:23.956930` |
| `brain/agentfarm/bridge.py` | `B520451FC254CA01F27024E41BA660D89808AF6D208089B685E589EA9697E7C3` @ `2026-10-16T23:45:57.892762` |
| `mod/…/AgentFarm.Bridge.dll` | `02755488A532BA3D163010BAF985029B35B31C682D5AC025A9AD2E68D86297C7` @ `2026-10-16T23:45:27.530570` |
| `mod/AgentFarm.Bridge/manifest.json` | `2257E76A3220052CA24196F1985CD4EC1A9F8315F6C5DC89E06507D45852B965` @ `2026-10-16T23:45:22.169716` |
| `git status --short` | 空（`worktree_clean=true`，sidecar 记 `git_status_short=[]`） |
| PID / 起跑时刻 | **18484** / `2026-10-16T23:48:27`（两侧各文件 mtime 均早于 StartTime ⇒ 进程加载的是冻结版） |
| PID 文件 / sidecar | `logs\longrun-3day-llm-run9c.pid` / `logs\longrun-3day-llm-run9c.version.json` |

## §2 起止快照与存档链

快照文件：`scratch\run9c-external-snapshots.jsonl`（2 行，`run9b-snapshot.py` 写入）。

| 端 | at | `save_main` | `save_info` | SMAPI NewDay/before/called(原始→修正)/task/completed | 账本 | PID |
|---|---|---|---|---|---|---|
| start | `2026-10-16T23:48:12` | 5766683 B / `2026-10-16T22:30:13.053` | 26933 B / `22:30:13.055` | 0 / 0 / 1→1 / 0 / 0 | 不存在 | PID 文件不存在（候选已显式打印） |
| end | `2026-10-17T00:16:53` | **3860602 B / `2026-10-17T00:16:44.786`** | 28884 B / `00:16:44.788` | **5 / 5 / 6→5 / 5 / 5** | 340 行 / last=`finish` | 18484 / `pid_alive=false` |

- start 行那个 `save_called 1` 是**窗口外**的 deploy 自动 `load_save` 痕迹（run9b 同源），不属本跑跨日。
- 窗口内中间三次落盘（存档 mtime 直接读到）：`3738764 / 23:53:59`（18→19）→ `3788187 / 00:01:31`（19→20）→ `3826574 / 00:08:27`（20→21）→ 收尾档 `3860602 / 00:16:44.786`（22→23）。
- 本跑**没有出现"有 NewDay 无 save"**（run9 的 0/4 病未复现）；`save_info` 与主文件成对更新。
- end 快照另含：`console = logs\longrun-3day-llm-run9c.console.log` **162 行 / 18040 B**（尾 3 行含 `{"code": 0, …}` 与 `终态：VERIFIED`）、`console_err = 0 B / 0 行`、`bridge_info {pid 8856, modVersion 0.7.30}`、`mod_version_matches=true`。

## §3 SMAPI 窗口与逐日落盘配对

### 3.1 冻结窗口

- `logs\run9c-smapi-window.txt` = **379854 B / 4878 行 / mtime `2026-10-17 00:16:46.819` / SHA256 `7B95E0F2EE2E452904EBCFE6A190BFDA2A52BBA125438FBCEAC686C7152CBF70`**（源 `SMAPI-latest.txt` 与副本 size/mtime 一致，00:16:46 字节复制）。
- 窗口内（起跑 23:48:27 – 收尾 00:16:46）带时间戳行 4872 条；噪声计数：`ERROR` 1（仅 `Steam isn't loaded` 类，无关）、`Disconnected` / `ClosedGame` / `Disposing` / `soft_oal` / `Exception` **全 0**、`Warping to Farm` **1257**（task-14 逐帧活锁仍在，仅信息项）、`POST /v1/exec` 911、`GET /v1/observe` 2532。

### 3.2 五串配对（逐次，行号 + 时刻）

| # | NewDay | before save | Save called | Save task | completed | after save | 存档 size / mtime |
|---|---|---|---|---|---|---|---|
| 1 | L1252 `23:53:54` | L1264 `23:53:58` | L1265 `23:53:58` | L1266 `23:53:58` | L1269 `23:53:59` | L1270 `23:54:01` → **summer 19** | 3738764 / `23:53:59`(读档 mtime) |
| 2 | L2468 `00:01:10` | L2480 `00:01:13` | L2481 `00:01:13` | L2482 `00:01:13` | L2485 `00:01:13` | L2486 `00:01:15` → **summer 20** | 3788187 / `00:01:31` |
| 3 | L2494 `00:01:30` | L2497 `00:01:31` | L2498 `00:01:31` | L2499 `00:01:31` | L2502 `00:01:31` | L2503 `00:01:33` → **summer 21** | （同上，20→21 跨日） |
| 4 | L3611 `00:08:27` | L3614 `00:08:27` | L3615 `00:08:27` | L3616 `00:08:27` | L3619 `00:08:27` | L3620 `00:08:29` → **summer 22** | 3826574 / `00:08:27` |
| 5 | L4866 `00:16:29` | L4872 `00:16:44` | L4873 `00:16:44` | L4874 `00:16:44` | L4877 `00:16:44` | L4878 `00:16:46` → **summer 23** | **3860602 / `00:16:44.786`** |

合计：`Synchronizing 'NewDay' task` **5** / `Context: before save.` **5** / `SaveGame.Save() called.` **5（修正后）** / `Synchronizing 'Save' task` **5** / `completed without exceptions` **5** / `after save, starting …` **5**。

### 3.3 `save_called` 原始 6 vs 修正 5 —— 工具假阳性的机制

- 原始计数 6 的行号 = `[16, 1265, 2481, 2498, 3615, 4873]`；剔除的是 **L16**：
  `[23:46:36 INFO  SMAPI]    AgentFarm Bridge 0.7.30 by AgentFarm | v0.7.30（run9b 复盘：water_far 补水与逐格判据 + resume 空转兜底 + 阶段口径账实相符 + 演进素材质量）  本版三张卡 + 一张对抗验收（Mod 无源码改动，只 bump 版本号）：  1. task-133（dev-coder）water_far 诚实浇水轨迹：…`
- 判别式（本跑修正、已写进 `docs\_run9b-evidence.md` §7 第 10 条）：**有 `[HH:MM:SS LEVEL CHANNEL]` 前缀 且 不含 ` by AgentFarm ` / `| v0.`**（插件描述行标记）。**注意**：假阳性行本身**带**时间戳前缀，所以"按前缀过滤"是不够的。
- ⇒ 本跑与 run9b、run9 的 `run9-lead-check.py` 都会因这一行报"before save(5) != Save called(6)"与"有 save 无 NewDay"；**这是工具侧的坑，不是世界问题**，已在 §4.3 逐条对照。

## §4 逐日表 + 两侧判决 + Lead 复核器

### 4.1 逐日 5 天（账本 `day_end`，权威字段）

| 游戏日 | ended_by | 跨日 | verified | ok / skip / fail | 睡前未浇 | 作物 | 钱 | 阶段数 | `final_water`（farm 口径） | 未过判据 |
|---|---|---|---|---|---|---|---|---|---|---|
| summer 18 | sleep | ✅→19 | **False** | 116 / 0 / 0 | 0 | 46 | 5 | 27 | `dry 0 / crops 76 / tiles 232` | 仅 `no_unmet_stages`（`assigned_undone=3`） |
| summer 19 | sleep | ✅→20 | **False** | 108 / 2 / 0 | 0 | 77 | 445 | 11 | `dry 1 / crops 83 / tiles 256` | 仅 `watered_outdoor` |
| summer 20 | sleep | ✅→21 | **True** | 0 / 0 / 0 | 0 | 0 | 465 | 0 | `dry 0 / crops 83 / tiles 256` | 无（真空日，`no_work` 证据被接受） |
| summer 21 | sleep | ✅→22 | **True** | 89 / 4 / 0 | 0 | 60 | 365 | 7 | `dry 0 / crops 84 / tiles 246` | 无（`stamina:体力 10 < 12`） |
| summer 22 | sleep | ✅→23 | **True** | 100 / 2 / 0 | 0 | 80 | 265 | 8 | `dry 0 / crops 101 / tiles 238` | 无（`stamina:体力 10 < 12`） |

- 5 天 `checks` 里恒为 true 的：`slept_by_us` / `no_blocking_modal` / `no_hard_failures` / `unreachable_within_bound` / `refused_within_bound` / `crops_watered` / `day_justified`。
- `day_after` 链：`18→19→20→21→22→23`，**5/5 恰好 +1**。
- 睡前未浇（`final.unwatered_crops`）逐日 **0**；`farm.dryCrops` 逐日 0/1/0/0/0。

### 4.2 两侧工具（原文摘录，全文见 `logs\run9c-verify.txt` / `logs\run9c-analyze.txt`）

`tools\verify-run3.py --journal logs\longrun-3day-llm-run9c.jsonl --days 3` ⇒ **rc=0**
- 日表（含 `睡前未浇 / 作物 / 钱 / 阶段 / ok / skip / fail / verified`）：`summer 18 … False`、`summer 19 … False`、`summer 20 … True`、`summer 21 … True`、`summer 22 … True`
- `decision 52 条（LLM 调用 21 条 / 其中模型产出 21 条）`；`尾部连续 VERIFIED 天数 3 / 要求 3`
- 结论行：`结论：VERIFIED`
- 严格口径行：`严格口径（整本零问题，仅呈现、不参与退出码）：needs_review（问题共 4 条 = 窗口内 0 + 窗口外历史 4）`
- `历史问题（达标窗口之外的日子，不影响结论，共 4 条）`：
  1. `[summer 18] day_end verified=false`
  2. `[summer 18] checks.no_unmet_stages=false（有阶段后置条件未成立；分配内未完成 assigned_undone=3 格）`
  3. `[summer 19] checks.watered_outdoor=false（睡前还有没浇的作物）`
  4. `[summer 19] day_end verified=false`
- `--json` 关键键：`verdict = VERIFIED`、`strict_verdict = needs_review`、`problems = 0`、`strict_problem_count = 4`、`history_problems = 4`（落 `logs\run9c-verify.json`）。

`tools\analyze-longrun.py --journal logs\longrun-3day-llm-run9c.jsonl --days 3` ⇒ **rc=0**（摘录）
- `行数: 340`；`VERIFIED: 3/3 天`；`步数合计: ok 413 / skipped 8 / failed 0`；`no_day_progress: 0 次`；`blocked: 0 条`；`sleep: 5 次（ok 5 / failed 0）`
- 经济：`购买: 6 次（成功 5 / 没成交 1）`；`sell 2 次（成交 2）`；`surplus_sell 2 次（sold 28 件）`；`buy_no_space 0 次`；`腾格卖出 2 次（why=need_slot）`；`slept_without_work 0 次`
- 浇水：`water_far 47 次（浇成 47 / 没成 0）`；`water_far_refill 3 次（成功 3；水位 0→40）`；⚠ `47 条 water_far 没有 cause 字段（旧账本形态）`
- 阶段：`阶段没做完 11 次（分下去 321 格 / 没做完 121 格；stopped no_seed×3、need_refill×3、?×2、stamina×3）`；`日级 shortfall 1 次`；`诚实上限留下 3 次 / 14 格（只作 info、不进 no_unmet_stages）`
- LLM：`复盘 5 次、notes 15 条（403 字；被拒 0 条、截断 0 次）`；`教训库 total 4 条（上限 20；本日新增 6 / 淘汰 6）`；`决策: 52 次（decisions_llm=21，其中模型产出 decisions_llm_used=21，无兜底）`；边界 `(none)=31 / new_day=4 / task_kind_change=17`
- 模态：`打断 2 次（信息项）`；`必须人工介入（红）0 条`；`退出码: 0；有红 0 条`

### 4.3 `scratch\run9-lead-check.py`（两侧参数显式传入）⇒ 修正前 **rc=1** / 修正后 **rc=0**

- `--journal logs\longrun-3day-llm-run9c.jsonl --snapshots scratch\run9c-external-snapshots.jsonl --smapi logs\run9c-smapi-window.txt --days 3`
- [1] 跨日链：`合计 跨日 5 次，其中恰好 +1 的 5/5`（含 `(1,summer,22) → (1,summer,23) +1 ✅ ended_by=sleep`）
- [2] 存档链：start `save_main 5766683 / 22:30:13.053`、end `3860602 / 00:16:44.786`，两端 `mod_version_matches=True`
- [3] SMAPI 配对：`NewDay 5 / before save 5 / Save called 6 / completed 5`（行号 `[1252,2468,2494,3611,4866]` / `[1264,2480,2497,3614,4872]`）
- [4] 自述 vs 自算：5/5 天 `ok_steps == Σ stages[].ok` 且 `failed_steps == Σ failed` ✅
- [5] 尾部窗口：`summer 20/21/22` 三天 `verified=True 未通过项=[]` ⇒ `结论：达标 ✅`
- [6] `finish: code=0 streak=3 actions=513 minutes=28.03 no_unmet_stages=False`
- `发现问题：❌ SMAPI 里 before save(5) != Save called(6)` / `❌ 有 save(6) 无 NewDay(5) —— 保存没有对应的跨日`
  ⇒ 两条都因 §3.3 的 **L16 假阳性**；修正后计数为 `5 / 5 / 5 / 5`，**无真实缺口**。
- **修正后复跑（Lead 提交 `13fa690` 的版本，00:25 后）**：⇒ **rc=0**，`合计 跨日 5 次，其中恰好 +1 的 5/5`、`结论：达标 ✅`、**无任何 ❌**（落 `logs\run9c-lead-check.txt`，本文件上文保留的是修正前的原始输出，两条 ❌ 不删改）。

## §5 判据逐条对账

### 5.1 task-140 / `docs\_release-0.7.30.md` §4 的硬判据

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| ① | 尾部连续 3 天 `ended_by=="sleep"` 且 `verified==true` 且跨日 +1 | **✅ 达标** | §4.1 表尾 3 行 + `verify-run3` 「尾部连续 VERIFIED 天数 3 / 要求 3」 |
| ② | 每天有农场动作（`day_after` 推进 ∧ `ok_steps==0` ∧ `verified==true` 三者不可同时） | **✅ 例外被接受** | summer 20 是真空日（`ok_steps=0` 且 `verified=true`），但 `verify-run3` 明写 `有"无活可做"证据（no_work:…）⇒ 接受`；其余 4 天 ok 89–116 |
| ③ | `no_space` 不死锁（同日 buy ≤3、`buy_no_space` 有界） | **✅** | `buy_no_space 0`、`cannot_afford 0`、`seed_unavailable_today 0`；`buy` 6 次中 5 成交、1 次 `item_not_sold` 探路（`attempt` ≤3） |
| ④ | LLM 演进留痕（`-llm.jsonl` 行数、`review_llm`/`lessons`/次日教训注入） | **✅** | `logs\longrun-3day-llm-run9c-llm.jsonl` 21 行 ↔ `decisions_llm=21`；`review_llm` 5 次 / notes 15 条 403 字 / 截断 0；教训库 4 条（§5.4） |
| ⑤ | **世界差分**（每游戏日 ≥1 份独立 `observe?detail=full`，逐日差分表） | **⚠ 部分** | 6 份独立观测覆盖 4 天（18/19/21/22）；**summer 20 缺观测**；tile kind 迁移在 18/21 只有 1 份端点 ⇒【无法判定】。明细见 §5.5 |
| ⑥ | 新闸门有无假红/假绿 | **✅ 无假绿；有 1 处工具假红** | `run9-lead-check.py` 的两条 ❌ = L16 假阳性（§3.3）；`verify-run3` 窗口内 problems 0 |
| ⑦ | 落盘五串配对 + 存档前进 | **✅ 5/5** | §3.2 + §2 |

### 5.2 经济闭环四腿（run9c 的核心留证）

| 腿 | 证据（账本原文摘录） |
|---|---|
| ① 卖 | `sell t=171.02 slot=11 qid=(O)330 stack=27 keep=10 below_keep=true`、`t=334.74 why=need_slot`；`surplus_sell` 2 次（`sold 28 件`） |
| ② 次日到账 | `day_start #108 summer 19 money=545`（前一日收尾 5g）；`day_start #191 money=465`；`#275 money=365` |
| ③ 买 | `buy` 6 次：`t=0.46` 探 `472` `item_not_sold`（在售清单 Melon 80/Tomato 50/Blueberry 80/Pepper 40/**Wheat 10**/Radish 40/Poppy 100/Spangle 50）→ 成交 5 次全是当季 `(O)483 Wheat Seeds` 10g：`205→105`、`105→5`、`545→445`、`465→365`、`365→265` |
| ④ 种 | `plant_area` 每天都有 ok 落格（summer 18 阶段数 27 / ok 116；summer 21 阶段 7 / ok 89；summer 22 阶段 8 / ok 100）；收尾快照 `day_end.final.seeds` 逐日可见买到手的当季种子：`summer 19 = [['483','Wheat Seeds',2]]`、`summer 21 = [['483','Wheat Seeds',10]]`、`summer 22 = [['483','Wheat Seeds',1]]` |

### 5.3 有界性 / 守卫（task-124/task-134/task-136 相关）

- `plot_exhausted_burst` **0**、`review_only_fallback` **0**、`slept_without_work` **0**、`no_day_progress` **0**、`stuck_flush` **0**、`blocked` **0**、`eventUp` **0**、`modal_dismissed` **2**（信息项）。
- `tool_refused` 8 次（`verify-run3` 按 task-63 政策计入豁免，`refused_within_bound=true` 五天全 true）；`unreachable` 0 次（`unreachable_within_bound=true`）。
- 阶段"没做完"11 次 / 121 格：`stopped no_seed×3 / need_refill×3 / ?×2 / stamina×3`；**日级 shortfall 1 次**（unmet 最多 3 格）。
- **两条新病灶（Lead m02015，已立 task-143/144）**在账本里可见：
  - `plant_area` 一次分 12 格但手上只有 11 粒种子 ⇒ `assigned_undone`（summer 18 `no_unmet_stages=false` 的成因之一）。
  - `water_area` 一次分 70 格但壶容 40 ⇒ `undone 27`，其中有一段 `stopped==""` 却仍有 3 格没做（另一成因）。

### 5.4 教训库（L0）

`logs\longrun-3day-llm-run9c-lessons.json` = **2134 B / mtime `2026-10-17 00:16:30.037` / SHA256 `F650B245BFFEC87DBA267957BB0499498340E1E8ADC9E57C05BCCEEBA1BE5118`**，4 条：

| id | count | severity | symptom（摘要） | evidence | hint |
|---|---|---|---|---|---|
| `tool_refused\|till_area` | 3 | 3 | till_area 有 2 格被游戏拒绝 | `refused=2 leftover=2` | 体力几乎见底，明天先补体力再下地，别硬撑。 |
| `stuck_with_leftover\|till_area` | 7 | 2 | 收尾还剩 2 格、当天 stuck | `leftover=2 failed=0 stopped=` | 体力几乎见底，明天先补体力再下地，别硬撑。 |
| `stuck_with_leftover\|water_area` | 4 | 2 | 收尾还剩 37 格、当天 stuck | `leftover=37 failed=0 stopped=need_refill` | 体力几乎见底，明天先补体力再下地，别硬撑。 |
| `stuck_with_leftover\|plant_area` | 4 | 2 | 收尾还剩 1 格、当天 stuck | `leftover=1 failed=0 stopped=stamina` | 钱只剩5g、背包没有种子，明天别急着种，先清田里和田边的杂草换点资源。 |

- **本库不用于 run10**（Lead m02015：run10 必须以 0.7.31 上 run9d 的 `-lessons.json` 重新拷贝，记拷贝时刻 + 两侧 SHA256）；本文件原地保留、不改。
- ⚠ 观察（进 §7）：4 条里 **3 条的 `hint` 是同一句"体力几乎见底…"**，而 `symptom/evidence` 各不相同（含 `stopped=need_refill`）⇒ hint 质量仍有同质化，值得 task-136 继续看。

### 5.5 世界差分表（判据 = `observe?detail=full` 差分，不信回执）

观测文件（6 份，`scratch\run9c-observe-*.json`，同名不覆盖）：`summer18@23:50:15`、`summer19@23:55:45` + `summer19-2@00:00:26`、`summer21@00:04:55`、`summer22@00:09:42` + `summer22-2@00:16:54`。

| 游戏日 | 观测数 | 端点（A→B） | ① tiles kind 迁移 | ② farm 计数变化 | ③ 体力/钱 | ④ 种子叠 | ⑤ 新增 crop 格 | 旁证 `day_end` |
|---|---|---|---|---|---|---|---|---|
| summer 18 | 1 | `summer18` →（同一份） | **【无法判定】**（当日 Farm 端点不足 2 份） | 无变化 | 226→226 / 105→105 | `(O)483` 3→3 | 0 | sleep / False / dry 0 |
| summer 19 | 2 | `summer19`@23:55:45 → `summer19-2`@00:00:26（均在 Farm） | `grass→dirt×2`：**(68,28)**、**(69,28)**；窗口新增/消失 +91/−91（不可区分） | `crops 75→78`、`unwatered 47→50`、**`dryCrops 56→1`**、`hoeDirt 221→256`、`emptyDirt 146→178`、`grass 658→654` | **232→20** / 445→445 | `(O)483` 10→7 | **新增 3 格**：(66,31)、(69,28)、(69,29) | sleep / False / dry 1 |
| summer 21 | 1 | `summer21` →（同一份） | **【无法判定】**（同上） | 无变化 | 156→156 / 465→465 | `(O)483` 2→2 | 0 | sleep / True / dry 0 |
| summer 22 | 2 | `summer22`@00:09:42（Farm）→ `summer22-2`@00:16:54（**FarmHouse**） | 无同格迁移；窗口 +1/−400（端点跨地点，不可比） | `crops 83→103`、`dryCrops 73→103`、`hoeDirt 224→221`、`emptyDirt 141→118`、`weeds 398→402`、`stones 103→104`、`twigs 61→60`、`trees 547→560`、`grass 750→784` | 248→270 / 365→265 | `(O)483` 10→1 | 0 | sleep / True / dry 0 |
| summer 20 | **0** | — | **缺观测**（23 秒真空短日，窗口错过） | — | — | — | — | sleep / True / dry 0 |

- 端点口径：每个游戏日 = 当日最早一份 → 当日最晚一份；tile 差分只在**两次都在 Farm 上**的端点对之间做（`location.tiles[]` 是玩家中心 400 格窗口 + 截断）。
- **【无法判定】清单（缺失 ≠ 通过）**：`summer18` 的 tiles kind 迁移、`summer21` 的 tiles kind 迁移、**`summer20` 全天无观测**。
- 本表可由第三方**不看账本**复核：每行都写了"哪个文件、哪两个字段、差多少"（脚本 `scratch\run9c-diff.py`，输出 `logs\run9c-diff.txt` 7645 字符）。
- ⚠ `day_end.final` 与现场不一致的两处（`summer18` final.money=5 / 现场 105；`summer21` final.money=365 / 现场 465）：**核对了时间先后**——两次观测都发生在**当天最后一次 `buy` 之前**（`t=126.11` 的 `105→5`、`t=1141.5` 的 `465→365`），所以这两处是**观测时刻早于收尾**，**不能据此断言 `final` 滞后**。run9b 的 task-137 证据（`slept_without_work` 分支上 `final.money` 滞后）不受影响。

## §6 与 run9b 对比（同为 0.7.x 上的短跑，仅诊断）

| 维度 | run9b（0.7.29，task-131） | **run9c（0.7.30，task-140）** |
|---|---|---|
| 判决 | `needs_review`（尾部 **1/3**，`finish code=1`） | **`VERIFIED`（尾部 3/3，`finish code=0`）** |
| 跨日 / 落盘 | 5 次跨日、五串 **5/5** | 5 次跨日、五串 **5/5** |
| 时长 / 动作 / 账本行 | 30.35 分钟 / 432 / 357 | 28.03 分钟 / 513 / **340** |
| 未达标日 | 3 天（`unmet_days` 3 条） | **1 天**（仅 `summer 18`） |
| 经济四腿 | sell 3 / buy 8（含 `buy_partial` 2） | sell 2 / buy 6（成交 5；当季 `(O)483`） |
| 有界性 | `plot_exhausted_burst 1`、`review_only_fallback 2`、`slept_without_work 1` | **三项全 0**、`no_day_progress 0`、`stuck_flush 0` |
| 教训库 | `far_dry_given_up` hint 与 evidence 自相矛盾（task-136） | 4 条，无自相矛盾；但 **3 条 hint 同质化**（§7） |
| 世界差分 | 无逐日独立观测（run9b 未要求） | 6 份观测 + 差分表（4/5 天有端点；20 缺） |

## §7 不确定项与诚实声明

1. **summer 20 全天没有独立观测**（23 秒真空短日：`t=761.88→784.69`），该日的"世界差分"判据只能写【无法判定】；同理 `summer 18` / `summer 21` 各只有 1 份 Farm 观测，tile kind 迁移【无法判定】。
2. `summer 22` 的端点 B 落在 **FarmHouse**（收尾后在屋内观测），该日的 tile 差分与 `dryCrops` 变化混合了"地点切换 + 窗口位移"，**不可当农场世界变化读**。
3. `location.tiles[]` 是**玩家中心 400 格窗口且被截断（`tilesTruncated=true`）**，所以"只在一端出现的格"只能写 +n/−n，**不能**区分世界变化与窗口位移。
4. 教训库 4 条里 3 条 `hint` 相同（"体力几乎见底…"），与各自 `symptom/evidence` 不匹配（例如 `stopped=need_refill`）⇒ **hint 质量仍有同质化**；本文件如实记录，供 task-136 后续评估。
5. `day_end.final` 与现场不一致的 2 处已查明是**观测时刻早于当天最后一次 buy**，不是 `final` 滞后（§5.5 末条）；`final` 字段的滞后风险仍以 run9b 的分支证据为准（task-137）。
6. `analyze-longrun.py` 报 `47 条 water_far 没有 cause 字段（旧账本形态）` ⇒ 该字段缺失，**当次无法判定逐格因由**（缺失 ≠ 通过）。
7. `verify-run3.py` 的**严格口径**（整本零问题）仍是 `needs_review`（4 条历史问题，全部在尾部窗口之外）；本跑判决以**尾部窗口口径**为准，两种读法**并列保留**，不做单边取舍。
8. `run9c` **不是** A/B 对照的 run A（Lead m02015）；A/B 将在 0.7.31 上重跑（run9d = run A、run10 = run B）。**未起 run10、未改 run9c 教训库**。
9. 本跑未覆盖：成熟作物收获、死苗（`farm.deadCrops=0` 全程）、夜间剧情事件（`eventUp=0`）、`ShipSkill` 整叠限制（task-55 缺口）。
10. 游戏**未退出**（收尾后游戏进程仍活着，PID 8856 / 桥 0.7.30），按纪律等 Lead 指令再 `tools\stop-game.py`。
11. 本文件与 `logs\run9c-*`、`scratch\run9c-*` 的所有读数均为**观测/日志原文**；Mod 回执只作旁证（`final` 字段明确区分），未用回执当证据。
12. **`save_called` 判别式与 Lead 侧口径已对齐**：Lead 在 `scratch\run9-lead-check.py` 里修掉了同一个假阳性（提交 **`13fa690`**），修正规则 = **有 `[HH:MM:SS LEVEL CHANNEL]` 前缀 且 不含 ` by AgentFarm ` / `| v0.`**（插件描述行标记）——与本文件 §3.3 的规则逐字一致；修后本跑复核器 **rc=0 / 无 ❌**，与 `verify-run3.py` 同向。§4.3 同时保留修正前 `rc=1` 的原始输出，**不删改**。
13. **优雅退出（2026-10-17 00:27:52）**：`python tools\stop-game.py` ⇒ **exit 0**、`✅ 游戏已退出（原 pids=[8856]）`；四项核对：进程数 **0**、`bridge.json` **已删除**、17890 **无 LISTENING**（仅 2 条 TIME_WAIT）、存档四条**逐字未变**（`Wahaha_450799035` 3860602 B / `2026-10-17 00:16:44.786`、`SaveGameInfo` 28884 B / `00:16:44.788`、`_old` 3826574 B / `00:08:27.843`、`SaveGameInfo_old` 28709 B / `00:08:27.844`）；SMAPI 尾 `00:27:52 Disconnected: ClosedGame → Disposing... → 已删除发现文件 …\AgentFarm\bridge.json → Disposing the content coordinator`，无 Event 1000/1001。
