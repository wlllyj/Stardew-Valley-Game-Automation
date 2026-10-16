# run A（0.7.32 · A/B 对照的 A 臂）真机证据

> 账本 `logs/longrun-runA-0732.jsonl`（**847 行**）｜判决：**FAIL（0/5 天 VERIFIED、尾部窗口 0/3、`finish.code=1`、`verified_streak=0`）**
> 判据纪律：**只认独立观测差分**（`observe?detail=full` 的 `tiles[]`/`clock`/`farm`），Mod 回执一律不作证据；缺失字段写【无法判定】，**缺失 ≠ 通过**。
> 用途：本跑是 A/B 对照的 **A 臂（诊断 + 教训库来源）**，不是"目标 2 达成"的证据。

---

## §1 起跑与版本四要素

命令（逐字，与 run B 只差 `--journal`）：

```
python tools\start-detached-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12 \
    --journal logs/longrun-runA-0732.jsonl --expect-version 0.7.32
```

| 项 | 值 |
|---|---|
| PID / 起跑时刻 | **21120** / `2026-10-17T03:45:38`（`logs\longrun-runA-0732.pid`） |
| 起跑器 argv（sidecar） | `['…python.exe','-u','tools/run-longrun.py','--days','5','--size','5','--max-minutes','240','--max-days','12','--journal','logs/longrun-runA-0732.jsonl']` |
| `head`（**只作参考，不比 head**） | `a0bd52820a4dcf9bbdb8665e2ea7f2de9e1f4403` |
| `worktree_clean` / `git_status_short` | `true` / `[]` |
| `boundary_llm` | `true` |

被测五文件（sidecar 原值，run B 起跑前逐字复核一致）：

| 文件 | SHA256 | mtime |
|---|---|---|
| `brain/agentfarm/longrun.py` | `6005F5E17BAEB050D8E7BAE9D36DAE2080CAD73867AC0C144033063373149507` | 2026-10-17 03:29:58.203408 |
| `brain/agentfarm/farmwork.py` | `7ED2DF1BA953C0B10AED389B2376819B6A24CB108A8927EC3D20C6C6C34913A8` | 2026-10-17 03:08:27.223513 |
| `brain/agentfarm/bridge.py` | `FF45381DBC732FDD6933983CA5EC6D58D891FF7315EFE27D86643A985425FA93` | 2026-10-17 03:43:01.214404 |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `5413C2BEEBA199BD9F5B065E3E88ED9A255253B6B90F3F0234BD6BD9769EFE65` | 2026-10-17 03:43:15.836710 |
| `mod/AgentFarm.Bridge/manifest.json` | `E6BA1B4C6ADABD3D467A6A4609ECDD70CA4DCA50782EF2F91085D36FD7F0DE73` | 2026-10-17 03:42:40.206287 |

- **Mod 0.7.32 装机**（Lead 执行，冻结提交 `300a01c`；`check-release --expect 0.7.32` 六项全绿含 `Ran 874 tests / OK`）：`AgentFarm.Bridge.dll` **188928 B**、`manifest.json` **41292 B**、桥 `modVersion=0.7.32 port=17890`。
- **权威基线** `logs\runA-0732-baseline.json`（Lead）：`第 1 年 秋 3 日 06:10 / debris / Farm(64,15) / 体力 136 / 钱 20g / 草 444 石 110 枝 71 树 632 / 耕地 165 / 作物 142 / waterLeft 0 / tillable 85 / tileCount 400 (truncated) / 无模态 / worldAdvancing true`。
- 我另做**独立 `preflight --expect 0.7.32`（不加 `--save-baseline`）⇒ EXIT=0**（四判据全绿），`--dry-run` 亦 EXIT=0。
- **90 秒体检**：脑进程存活、账本 19 行、`console.err.log` 0 B。

## §2 起止外部快照与存档链

`scratch\runA-0732-external-snapshots.jsonl` 两行原文要点：

| 项 | start（`at 2026-10-17T03:47:41`） | end（`at 2026-10-17T04:23:27`） |
|---|---|---|
| `save_main` | `4103808 / 2026-10-17T02:11:33.121` | `4221434 / 2026-10-17T04:10:25.974` |
| `save_info` | `28765 / 02:11:33.122` | `28898 / 04:10:25.975` |
| SMAPI 计数 | `lines 715 / newday 0 / before_save 0 / save_called 3 / save_task 0 / save_completed 0` | `lines 5146 / newday 5 / before_save 5 / save_called 8(原始) / save_task 5 / save_completed 5` |
| 账本 | `21 行 last=refill_retry` | `847 行 last=finish` |
| PID | `21120 / alive=true` | `21120 / alive=false` |
| 桥 | `{pid 20672, 0.7.32}`、`mod_version_matches=true` | 同左 |
| console / err | `1140 B / 10 行`、`0 B` | `22607 B / 172 行`、`0 B` |

> start 行里非 0 的 `newday 0 / save_called 3` 属**窗口外**痕迹（deploy 与 preflight 的 `load_save`），不参与窗口配对。

**每跳存档（轮询实测，size/mtime）**：

```
4103808 / 02:11:33.121  ← 起跑前
4130504 / 03:48:44      ← 跨日 1（fall 3→4）
4165300 / 03:51:55      ← 跨日 2（4→5）
4181797 / 03:55:04      ← 跨日 3（5→6）
4195472 / 03:58:12      ← 跨日 4（6→7）
4221434 / 04:10:25.974  ← 跨日 5（7→8）
（fall 8 以 sleep_failed 收尾 ⇒ 无第 6 次落盘）
```

## §3 SMAPI 窗口与六串配对

- 冻结文件：`logs\runA-0732-smapi-window.txt` = **385136 B / 5146 行 / mtime `2026-10-17 04:22:52.777` / SHA256 `768E6B46CA69EDB37EE355206FA6C117F41C4BB4F40D973AE1353A26C6B71262`**（源/副本 SHA 一致）。
- 窗口 `03:45:38–04:23:00`：带时间戳行 **4725** / 文件 5146。

| 串 | 次数 | 行号 |
|---|---|---|
| `Synchronizing 'NewDay' task` | 5 | 892, 1681, 2475, 3274, 4072 |
| `Context: before save.` | 5 | 895, 1684, 2478, 3277, 4084 |
| `SaveGame.Save() called.`（修正后） | 5 | 896, 1685, 2479, 3278, 4085 |
| `Synchronizing 'Save' task` | 5 | 897, 1686, 2480, 3279, 4086 |
| `completed without exceptions` | 5 | 900, 1689, 2483, 3282, 4089 |
| `after save, starting` | 5 | 901, 1690, 2484, 3284, 4090 |

⇒ **六串 5/5 逐条配对齐全**；`Save_called` **原始计数也是 5**（本次 L16 插件描述行差 0）。
噪声：`Warping to Farm` **1571**（task-14 逐帧活锁，信息项）、`GET /v1/observe` 2342；`ERROR`/`Disconnected`/`ClosedGame`/`Disposing`/`soft_oal`/`Exception` **全 0**。

## §4 逐日表与两侧工具判决

| 日 | ended_by | 跨日 | verified | ok/skip/fail | `final_water.dry` | 未通过判据 | `ended_reason`（摘要） |
|---|---|---|---|---|---|---|---|
| fall 3 | `sleep` | ✅→4 | False | 65/0/1 | **73**/142 | `no_hard_failures`,`no_unmet_stages`,`crops_watered`,`watered_outdoor` | `stamina:体力 0 < 12` |
| fall 4 | `sleep` | ✅→5 | False | 65/1/1 | **73**/142 | 同上四条 | `stamina:体力 0 < 12` |
| fall 5 | `sleep` | ✅→6 | False | 65/0/1 | **72** | 同上四条 | `stamina:体力 0 < 12` |
| fall 6 | `sleep` | ✅→7 | False | 65/4/1 | **69** | 同上四条 | `stamina:体力 0 < 12` |
| fall 7 | `sleep` | ✅→8 | False | **1/0/31** | 0 | **`no_hard_failures`** | `night:时间 2200 已经到夜里（≥2200）` |
| fall 8 | `sleep_failed` | ❌无 | False | **15/0/44** | 0 | `slept_by_us`,`no_hard_failures`,`no_unmet_stages`,`day_justified` | `没有引出睡觉提问…踩触发格 (10,9) 失败：timeout: move_to 超时（10000ms，剩余 9 步未走完）…timeOfDay 2240 stamina 245.3 isInBed False` |

**`tools\verify-run3.py --journal … --days 5 --json` ⇒ rc=1**：`verdict="needs_review"`、`strict_verdict="needs_review"`、`strict_problem_count=39`。信息段要点：fall 6 `plot_pending 47 格`（其中"诚实上限延后 46 格"⇒不计 unmet）、fall 7 `frontier_clear 6/6`、`assigned_undone=1 但无 stage_shortfall_day 落痕 ⇒ 无法交叉核对（缺失≠通过）`、`deferred_tiles=1 与自算 0 不一致`、不可达/锄不动 exempt 0、`llm.jsonl 决策 75 行 / 复盘 6 行`。

**`tools\analyze-longrun.py --window 5` ⇒ rc=1**（`logs\runA-0732-analyze.txt`）：窗口命中 `env_fail`/`env_spin_capped`/`inconclusive_fail` 各 **5**、`watered_outdoor` **1 缺失（红）+ 2 白做**、`no_work…+dry>0` **1（红）**、`no_unmet_stages` **1**、`day_after` **1（红）**、`unreachable`/`refused` 各 **5**、`verified=True 但 Σ stage.ok==0` **2（红）**；模态/`levelup_profession_*` 全 0。

**`scratch\run9-lead-check.py --snapshots scratch\runA-0732-external-snapshots.jsonl --smapi logs\runA-0732-smapi-window.txt` ⇒ rc=1**：跨日 **5/5 恰好 +1**；SMAPI 配对并排除 1 行插件描述行；**自述 vs 自算 6/6 ✅**（fall 7 `ok 1↔1 / failed 31↔31`、fall 8 `15↔15 / 44↔44`）；尾部窗口 fall 6/7/8 全 `verified=False`（fall 7 唯一坏项 `no_hard_failures`）⇒ **未达标**；`finish code=1 streak=0 actions=415 minutes=37.23`。

`finish` 原文：

```json
{"event":"finish","t":2233.62,"code":1,"verified_streak":0,"target_days":5,"actions":415,"minutes":37.23,
 "stages_seen":["clear_dead","harvest","plant_area","till_area","water_area"],
 "no_unmet_stages":false,
 "unmet_days":["1年 fall 3日","1年 fall 4日","1年 fall 5日","1年 fall 6日","1年 fall 8日"],
 "stuck_flushes":0}
```

⚠ **自述与逐日不一致（如实记录，未推断原因）**：`finish.unmet_days` 列了 5 天（fall 3/4/5/6/8）而**不含 fall 7**，但逐日表与 Lead 复核器都判 **fall 7 `verified=False`**（唯一坏项 `no_hard_failures`）。

## §5 判据对账（task-162 验收口径）

| # | 判据 | 结果 |
|---|---|---|
| 1 | 尾部连续 5 天 `ended_by=="sleep"` 且 `verified==true` | ❌ **0/5**（`verified_streak=0`） |
| 2 | 每次跨日落盘（六串配对）+ 存档 size/mtime 前进 | ✅ **5/5**（六串全 5，存档链 5 次前进） |
| 3 | 0 次桥掉线 / 崩溃 / 模态卡死 | ✅（`console.err` **0 B**、SMAPI `ERROR/Disconnected/ClosedGame/Disposing` 全 0、`ui.activeMenu` 全程无阻断模态） |
| 4 | exit code 0 | ❌ **1**（`needs_review`） |
| 5 | 每日 ≥2 份独立 Farm 端点观测 | ⚠ **部分**：fall 6/7/8 满足；**fall 3、fall 5 各 1 份；fall 4 为 0 份** ⇒ 那三天的 tile 迁移【无法判定·窗口错过】 |

**deputy task-166 的三条观察点**（真机结果）：

1. 「绿日尾部出现'三腿覆盖 0 步' info」→ **出现且是常驻信息项**：`verify-run3` 明确报"三腿覆盖：清障/开垦 全程 0 步成功"、"播种 全程 0 步成功"（本跑种子/钱不足，属合法但目标 P3 ⑥ 要求真机证据）。
2. `stage_capped_by_capacity` 真机是否出现 → **未命中**（事件计数里 0 次）。
3. `plot_exhausted_burst` 收 `stuck` 形态（INFO-1）是否复现 → **未复现**（`no_progress_burst` 0、`slept_without_work` 0）。

## §6 世界差分表

`logs\runA-0732-diff.txt`（**12106 字符**，`scratch\run9c-diff.py`）：共 **41 份** `scratch\runA-0732-observe-*.json` 观测（`--naming alpha` 同名不覆盖，全部带 `worldSeq`）。

| 日 | 观测份数 | 端点对（当日首份→收尾） | 同格 `kind` 迁移 | `farm.*` 与种子 | 判定 |
|---|---|---|---|---|---|
| fall 3 | 1（tod 1110） | 缺第 2 份 | — | — | 【无法判定·窗口错过】 |
| fall 4 | **0** | 无 | — | — | 【无法判定·窗口错过】 |
| fall 5 | 1（tod 730） | 缺第 2 份 | — | — | 【无法判定·窗口错过】 |
| fall 6 | 6（tod 600→910） | B 在 `FarmHouse`（`tiles=1`，整场计数归 0） | 不可比 | 不可比 | 【无法判定】 |
| fall 7 | 14（tod 640→2140） | **双 Farm** ✅ | **0 处**（窗口 `+60/−60`，无同格迁移） | **新增 19 格**：`(53,16)(53,17)(54,15)(54,16)(54,17)` … | 唯一可复核的世界差分 |
| fall 8 | 19（tod 600→2230） | `FarmHouse`→`Farm` | `+400/−1`（整天换场，不可比） | `crops 0→…`、`hoeDirt 0→…` 等整场重算 | 【无法判定】 |

⇒ run A 的**世界差分证据几乎为空**：唯一"双 Farm 端点"的 fall 7 恰好是 harvest 病灶日（`[60,29]` 打转、`ok 1 / fail 31`），因此**不能用它证明"做了多少活"**。这直接对应 Lead 在 0.7.32 起跑时加的硬要求（每日 ≥2 份 Farm 端点）——它在 run A 前半段没有被满足。

## §7 保留物 · 不确定项 · 诚实声明

**保留物**：`logs\longrun-runA-0732.jsonl`（847 行）、`.pid`、`.version.json`、`.console.log`、`.console.err.log`（0 B）、`logs\runA-0732-{smapi-window.txt, verify.txt, analyze.txt, lead-check.txt, diff.txt}`、`scratch\runA-0732-{external-snapshots.jsonl, observe-*.json}`、`scratch\runA-tools.py`、`logs\runA-0732-baseline.json`。

**不确定项（全部如实列出）**：

1. fall 3/4/5 的独立观测缺口 ⇒ 那三天的世界差分【无法判定】（**缺失 ≠ 通过**）。
2. `finish.unmet_days` 与逐日表不一致（不含 fall 7）——只记事实，未推断归因。
3. `deferred_tiles=1` 与按阶段自算 `0` 不一致（工具已提示"供复核"）。
4. `assigned_undone=1` 无 `stage_shortfall_day` 落痕 ⇒ 无法交叉核对。
5. run A 的起点世界**不可复现**（B 起跑前游戏已自行从 `fall 8` 推进到 `fall 9`、`farmingLevel 0→1`）。

### §7.4 体力预算 / 延后（run A 的结构性读数）

- 新护栏真机出数：`stamina_budget` **6** 次、`budget_deferred_tiles` **16**、`deferred_by_budget` **17**、`deferred_tiles` **5**、`stage_shortfall` **83**、`stage_shortfall_day` **5**、`stage_exhausted` **74**、`work_spot` **31**、`idle` **48**、`intent_vetoed` **23**。
- fall 8 的 `stamina_budget` 原文要点：`{max 270, stamina 270, live_crops 122, dry 0, water_reserve 256, water_cost_est 0, path_allowance 12, capacity 4, basis farm, deferred_by_budget true, deferred [clear_area, till_area], deferred_tiles {till_area 4}}`。
- `stamina_calibration = {plant_area {actions 3, per_action 0.0}, till_area {actions 12, stamina_spent 22.8, per_action 1.9}}`。
- **结构性结论（观测支撑）**：作物规模 **125 格** × 浇水成本 vs **单日体力 270** ⇒ 结构上不可能一天全浇；fall 3–6 每天 `final_water.dry` 稳定在 **69–73**、`ended_reason` 恒为 `stamina:体力 0 < 12`、每天恰好 1 个失败步 ⇒ **"作物规模 > 单日体力预算"是本跑 0/5 的第一层原因**；第二层是 fall 7/8 的 harvest 病灶（见 §7.6）。

### §7.6 harvest 病灶（run A 已经存在）

- 账本里含 `交互后作物还在` 的行 **92 条**，全部指向同一格 `[60,29]`；样例 `outcome{kind: harvest, terminal: needs_review, postcondition_met: false, detail: ["(60, 29): 交互后作物还在（可能没摘到）"]}`。
- fall 7 = `ok 1 / fail 31`、fall 8 = `ok 15 / fail 44`，失败步绝大多数是该格反复 harvest ⇒ 守卫被这 1 格熟作物钉死（`intent_vetoed{sleep: "农场口径还有 1 格熟作物…先去收"}`）。
- 该格在 run B 起跑后、以及**两次跨日之后仍 `ripe=true`**（见 `docs\_runB-0732-evidence.md` §0 现场），⇒ 作为 harvest 修复后的**同格前后对照基线**。

### §7.8 经济闭环四腿（run A）

| 腿 | 真机读数 |
|---|---|
| 卖 | `sell` **0 条**；`surplus_sell_skip` **1 条**（`#465 t=1519.13`：`钱 20g < 100g 且种子 0 且空耕地 28 格 ⇒ 该卖材料换钱，但没有任何材料 id 超过保留线 K=10`，`Stone total 3 / keep 10 / sell 0`）⇒ **合法跳过**（不是失败） |
| 次日到账 | 无卖出 ⇒ 无到账 |
| 买 | `buy` **2 条**：`#466 t=1519.29 ok=false item_not_sold`（探春季 `472`，回执带在售清单 `Pumpkin 100g / Corn 150g / Eggplant 20g / Bok Choy 50g / Yam 60g / Cranberry 240g / **Wheat 10g** / Sunflower …`）、`#467 t=1519.33 ok=true 买到 2 个 (O)483（钱 20→0）`；`buy_partial` **1 条**（"钱只够买 2 个（想买 10 个，单价 10g）⇒ 量力而行"） |
| 播种 | `plant_area` 有 `ok`（fall 3–6 每天 65 个成功步里含播种；总计 `plant_area ok 3` 计在 stage 汇总） |

### §7.9 诚实声明

- run A **未达标**（0/5），**不宣称目标 2 有任何进展**；本跑的世界差分证据**大部分无法判定**（观测覆盖不足），能站住的只有 §3 的落盘六串、§4 的逐日判决、§7.4/§7.6 的结构性读数与病灶。
- 本跑期间我**只读**游戏与账本，未改源码、未 deploy、未替游戏做选择；证据文件均在本文件"保留物"清单内。
