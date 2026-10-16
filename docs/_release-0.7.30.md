# 0.7.30 发布计划（run9b 复盘：water_far 逐格判据 + resume 有界 + leftover 口径拆分）

- 起草：2026-10-16 深夜（Lead）
- 上一版：0.7.29（已装机，run9b = run A 正在跑）
- 本版目标：修掉 run9b 暴露的两条真缺陷 + 一次**口径变更（须过独立对抗验收）**，然后跑 run9c（= run A 重跑）与 run10（= run B 对照）。

## §0 run9b 现状（证据：`logs/longrun-3day-llm-run9b.jsonl`、`docs/_run9-evidence.md`）

- **P0「出货日日切不落盘」已修**：run9b **五次跨日、5/5 全配对**（SMAPI 六串齐全：`Synchronizing 'NewDay' task…` → `Context: before save.` → `SaveGame.Save() called.` → `Saving without compression…` → `completed without exceptions.` → `after save, starting <次日>`），存档逐次前进：3706657 → 3731582/22:05:16 → 3770274/22:13:28 → 3813991/22:18:07 → 3843606/22:22:45 → **5766683/22:30:13.053**。取证原文 `docs/_run9b-evidence.md` §3（含 `save_called` 原始计数 6 vs 修正 5 的假阳性机制：插件描述行 L16 被正则命中）。
- **6 个日报告里出现首个整天全 VERIFIED：summer 17**（`sleep`、`ok/skip/fail 70/0/0`、九项 checks 全 true、`dry 0/56`）。
- **但 0/3 VERIFIED**（三天 `no_unmet_stages=false`）：
  - summer 13：`stuck`（同秒连发换片 5 次 ⇒ `plot_exhausted_burst`），9 格跨片 leftover 反复"回去看"10 次却一格没做；
  - summer 14：`stamina`（体力 4 < 12）；
  - summer 15：`gave_up_dry`（窗口外 `[12,30]` 没浇上）。
- 已确认两条真缺陷：**task-133**（water_far：壶空被写成"够不着"，且 `ok` 判据被别格浇水的全局差值顶替）、**task-134**（resume 空转 + leftover 片区级口径让"阶段已完成"也记 leftover>0）。

## §1 卡片表

| 卡 | 内容 | 状态 | 0.7.30 必修 |
|---|---|---|---|
| task-133 | `_water_far_dry` 补水重试（≤2 次）+ **逐格判据**（`farm.dryTiles`/`watered`，禁止全局差值）+ 收尾分清因 | dev-coder **completed**（`57ef928`，Lead 已核） | ✅ |
| task-134 | A：resume/work_spot 空转有界（burst 计数覆盖）+ resume 重评 `no_target`；B：**leftover 口径拆分**（`assigned_undone` vs `plot_pending`） | dev-coder **completed**（`903e6a4`，2 文件 +383/−4；Lead 亲核定向 433 OK / 全量 **757 OK**） | ✅ |
| 工具侧对齐 | `tools/verify-run3.py` 3b 改按 `stages[].assigned_undone` 判 `no_unmet_stages`（`leftover`/`plot_pending` 只记录）+ 日级白名单补 `assigned_undone`/`plot_pending`/`plot_pending_by_kind`/`deferred_tiles` + 5 条新用例 | Lead **completed**（`c6cc654`；`tests.test_verify_run3` 58 OK、九账本 rc 并排不变） | ✅ |
| task-135 | 独立对抗验收 task-133 + task-134（重点：口径变更是否引入新洗白通道） | deputy-lead 首轮 **FAIL**（`1726d2e`：task-133 PASS / task-134 脑侧 PASS-WITH-NITS / 工具侧 F1 必修）⇒ 复验在制 | ✅ |
| task-135 修复 | 工具侧 **F1**（诚实上限阶段的分配内未完成格不许当 unmet ⇒ 消掉假红）+ **F2**（`assigned_undone` 不许纯自述：`stage_shortfall_day` 落痕 > 账本自算 ⇒ problem） | Lead **completed**（`5b070b4`；`tests.test_verify_run3` 60 OK、全量 **776 OK**、九账本 rc 逐字不变；deputy 的 F1 反例 `scratch/_t135_j/_t135_head_night+stamina_600.jsonl` 改前 needs_review ⇒ 改后 `--days 1` VERIFIED 无 mismatch） | ✅ |
| task-136 | 决策演进链质量：复盘调用留痕 + 复盘提示词接地 + 教训 hint 防污染（`[模型自述·未验证]`） | dev-coder **completed**（`7d4450f`，4 文件 +463/−23；Lead 亲核定向 438 OK / 全量 **767 OK**） | ✅（run9c 前） |
| task-139 | analyzer 收录 task-136 的 `lessons.hint_dropped` + 头部「教训素材质量」行 + 三条 ⚠（不进 rc） | log-analyst **completed**（`1e1d2cf`，3 文件 +247/−2；Lead 亲核 analyzer 171 OK / 全量 **774 OK**，十账本 rc 一字未变） | ✅（不阻塞冻结，run9c 判决前交） |
| task-101 | `_farm_totals` 类型校验（`dryCrops="abc"` 会让整天崩）等 NIT | pending | 顺延 |
| task-107 | Mod `dryTiles` 与 `dryCrops` 同源 + `scanSeq` | pending | 顺延 |
| task-109 | 卖货如实性（最大叠/最小损失）+ 卖后刷新 obs | pending | 顺延 |
| task-110 | `ensure_location` 无 try/except ⇒ `BridgeError` 穿出 `run()` | pending | 顺延 |
| task-117 | 教训内容模板校验 + 提示词标注"模型自述≠真值" | pending | 顺延 |
| task-131 | run9b（0.7.29 上的 run A） | machine-runner **completed**（`732aa51`，证据 414 行） | — |
| task-137 | 非 `sleep` 收尾分支的 `DayReport.final` 必须重取（证据字段滞后；run9b 尾部 `final.money=205` vs 现场 105 已查清=买前快照） | pending | 顺延（0.7.31） |

## §2 冻结与装机九步（Lead 独占）

1. 确认 task-133/134/**136**/135 全 completed 且**全量单测 0 红**（`python -m unittest discover -s tests`）。本版**工具侧对齐已在冻结前完成**：`c6cc654`（3b 按 `assigned_undone` 判、日级白名单补四键）+ **`5b070b4`**（F1 诚实上限阶段假红、F2 `assigned_undone` 纯自述漏洞 —— deputy task-135 首轮 FAIL 的两条），冻结时只需再复跑一次确认（`tests.test_verify_run3` 60 OK / 全量 776 OK / 九账本 rc 并排不变）。**task-135 需 deputy 复验把 F1/F2 判 PASS-WITH-NITS 或 PASS**，否则不许冻结。**task-139**（analyzer 收录 task-136 新事件）已 completed（`1e1d2cf`）。
2. 写 `tools/_note-0730.txt`，**首串必须是 `v0.7.30`**，逐条列 task-133/134/136（已于本夜写好，首串 `v0.7.30（run9b 复盘：water_far 补水与逐格判据 + resume 空转兜底 + 阶段口径账实相符 + 演进素材质量）`）。
3. `python tools\_bump-mod-version.py 0.7.30 --note-file tools\_note-0730.txt`（末句在 cp1252 下会 `UnicodeEncodeError`、退出码 1，**版本已写盘** ⇒ 一律 `json.load` 核对 manifest）。
4. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.30"`（注释列本版两项）。
5. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ 必须 0 警告 0 错误（本版若 Mod 无源码改动，dll 内容不变但版本号随 manifest）。
6. `git add -A` 后提交冻结；`python tools\check-release.py --expect 0.7.30` 六项全绿（含树干净）。
7. `python tools\deploy-mod.py --no-quit`（装机 + 读档）。
8. `python -m agentfarm goto Farm --no-focus`（老存档从 FarmHouse 出发）。
9. `python tools\preflight.py --expect 0.7.30 --save-baseline logs\run9c-baseline.json` ⇒ 必须 `✅ 可以起跑`；**不做操作员预置**（经济闭环是 task-55/102 的验收面，必须让脑自己走"卖 → 次日到账 → 买 → 种"）。

## §3 run9c（run A）与 run10（run B）

- 起跑（脱离式，DSH 托管作业会在回合边界被收掉）：
  `python tools\start-detached-longrun.py --days 3 --size 5 --max-minutes 150 --max-days 9 --journal logs\longrun-3day-llm-run9c.jsonl --expect-version 0.7.30`
- 跑完先**别退游戏**；让 machine-runner 取 `--tag end` 快照（用现成脚本 `scratch\run9b-snapshot.py --tag end --journal logs\longrun-3day-llm-run9c.jsonl --pid-file logs\longrun-3day-llm-run9c.pid`，它的 PID 候选按 `--journal` 推导、含四联计数 `smapi_newday/before_save/save_called/save_task/save_completed`）+ 冻结 SMAPI 窗口，再按 `User said (m02833)` 优雅退游戏。
- 两侧工具 + Lead 复核器都要跑：`python tools\verify-run3.py --journal <账本> --days 3`、`python tools\analyze-longrun.py --journal <账本> --days 3`、`python scratch\run9-lead-check.py --journal <账本> --snapshots <快照> --smapi <SMAPI 窗口>`（后者的 `--snapshots`/`--smapi` **必须显式传**，且「有 NewDay 无 save」自 0.7.29 起是**硬问题**）。
- 教训库交接（**必须显式拷贝**，不许加命令行开关）：`logs\longrun-3day-llm-run9c-lessons.json` → 原样拷成 `logs\longrun-3day-llm-run10-lessons.json`，记拷贝时刻与两侧 SHA256（写进 `docs/_run10-evidence.md` §1 与版本 sidecar）。
- run10（run B）用同一条起跑命令、只换 journal 路径（`--journal logs\longrun-3day-llm-run10.jsonl`）。
- 对照取证：`python tools/compare-runs.py --run-a logs\longrun-3day-llm-run9c.jsonl --run-b logs\longrun-3day-llm-run10.jsonl`（工具恒退 0；缺文件退 2；正式判决仍归 `verify-run3` + `analyze-longrun`）。

## §4 判据（继承 + 本版新增）

继承 `docs/_run6-criteria.md`：尾部窗口 `verdict` + 严格口径 `strict_verdict` 两行都抄；外部证据单列（存档 size/mtime、SMAPI 窗口冻结、start/end 快照）；**缺失字段一律【无法判定】，缺失 ≠ 通过**；两侧工具必须同向。

本版新增/变更：

1. **每次跨日必须落盘**：SMAPI `NewDay` 次数 == `before save` == `SaveGame.Save() called.` == `completed without exceptions` == `after save, starting`，任一缺口即硬问题（task-126/129 之后 run9b 已 3/3 齐全）。
2. **窗外浇水逐格判据**（task-133）：`ok` 只认该格证据（不在 `farm.dryTiles` 或 `watered=true`）；不许用全局 `dryCrops` 差值顶替；`gave_up_dry` 的理由必须区分壶空/不可达/缺证据。
3. **resume 有界**（task-134 A）：`work_spot`/`resume_walk` 连续无产出必须被 burst 计数拦住（≤5），当天以 `stuck:` 诚实收尾且 leftover 不许归零。
4. **leftover 口径拆分**（task-134 B，口径变更）：`assigned_undone`（阶段分到的格少做了）非诚实上限 ⇒ unmet；诚实上限（`stamina`/夜里/`budget` 且作业量做完）留下的片区待做 ⇒ `deferred_tiles`(info) 且不进 unmet；`plot_pending` 字段保留且数值不得变（守卫行为不许变）；`unreachable`/`refused` 越界仍判 false。
5. **世界差分（原始目标口径：判据 = `observe?detail=full` 差分，不信回执）**：run9c 每个游戏日至少要有一份**独立**的 `observe?detail=full` 原文（`scratch/run9c-observe-<day>.json`），证据文档里给出"当日 `day_start` 观测 → 当日收尾观测"的**逐格/计数差分表**（至少：`location.tiles[]` 的 `kind` 迁移数、`farm.crops/unwatered(needsWatering)/dryCrops/deadCrops`、`player.stamina/money`、`inventory` 种子叠），并写明"哪一格从什么变成什么"。**只有账本自述没有独立观测差分的天，不算世界差分证据**（自述只能作旁证）。
6. **`assigned_undone` 不得纯自述**（task-135 F2，`5b070b4`）：该字段是脑侧自报；`tools/verify-run3.py` 新增交叉核对 —— `stage_shortfall_day`（非夜里收工的欠账落痕）`unmet > 账本自算 assigned_undone` ⇒ problem。伪造 `assigned_undone=0` + 落痕 `unmet=5` 的账本必须被判红。
7. **诚实上限阶段不得制造假红**（task-135 F1，`5b070b4`）：体力/夜里/预算收尾且作业量做完的阶段，其分配内未完成格只进 `deferred_tiles`（info），自算 `no_unmet_stages` 时从基数里减掉；账本谎报 `true` 时仍报 mismatch。

## §5 与 run9b 对比（跑完填）

| 项 | run9b | run9c |
|---|---|---|
| 尾部连续 VERIFIED | 0/3 | 待填 |
| 跨日落盘 | 3/3 齐全 | 待填 |
| 经济闭环 | 卖/买/种各自成交 | 待填 |
| `gave_up_dry` 天数 | 2 | 待填 |

## §6 遗留与未定

- task-134 B 段是口径变更：**未过 task-135 不得冻结**。
- **task-136 必须在 run9c 起跑前落地**：run9b 的 `logs/longrun-3day-llm-run9b-lessons.json` 里 `far_dry_given_up|water_far` 的 `hint`（"作物全已浇水…"）与它自己的 `evidence="gave_up=3 dry_dead=0"` 矛盾，且复盘调用本身没进 trace ⇒ 这是**反馈污染**：run9c 写进库的教训会被 run10 原样注入。run9c 前要么修好（首选，task-136），要么在 run9c 起跑前把旧 `-lessons.json` 清空重来。
- run10 的演进判定按 `docs/_run10-criteria.md`（L0 要求 run A 的 `lessons.total>=1`，run9/run9b 实测 0 ⇒ run A 必须在 0.7.30 上重跑）。
- 顺延卡见 §1 表（task-101/107/109/110/117/**137**），以及长期项 task-14（warp 活锁）、task-17（world_stuck）、task-18（职业选择）、task-20（工具等级）、task-53（农场级待清/待垦）、task-83/94（田块规整）。
- **run9c 证据必查项（Lead 定的两条新注意点）**：①若 run9c 出现 `slept_without_work`/`gave_up_dry`/`blocked_modal` 收尾，**必须单独取一次收尾现场 `observe`**（这些分支的 `day_end.final` 可能是旧快照，见 task-137）；②`save_called` 的原始计数含 L16 插件描述行的假阳性 ⇒ 一律报"修正后 5/5"并附机制说明。

## §7 冻结与装机执行记录（Lead 独占，2026-10-16 23:45–23:55）

1. **放行闸门**：task-133（`57ef928`）/134（`903e6a4`）/136（`7d4450f`）/139（`1e1d2cf`）completed；**task-135 首轮 FAIL**（`1726d2e`）⇒ Lead 修 F1/F2（`5b070b4`）⇒ deputy 复验 **PASS-WITH-NITS**（`fdb83ea`，修后探针 18/18、`C-tool 同向` 四组全 PASS、伪造转 needs_review、`no_target` 组仍红）。全量 **776 OK / 0 红**。
2. **冻结**：`tools/_note-0730.txt` 首串 `v0.7.30`（Mod 本版无源码改动）⇒ `_bump-mod-version.py 0.7.30` ⇒ manifest `0.7.29 → 0.7.30`（Description 头部已插）⇒ `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.30"` ⇒ `dotnet build --no-incremental` **0 警 0 错**（`AgentFarm.Bridge.dll` **177664 B**、`manifest.json` **30277 B**）⇒ 冻结提交 **`aa3ceaf`** ⇒ `check-release --expect 0.7.30` **六项全绿**（`manifest==brain==0.7.30` / dll 22:45:27 不旧 / `py_compile` 22 文件 / `Ran 776 tests` OK / 树干净）。
3. **装机**：`deploy-mod --no-quit` ⇒ 0.7.29 → **0.7.30**（桥 `modVersion=0.7.30 port=17890`；自动读档 `Wahaha_450799035` → FarmHouse(9,9)）；日志 `logs\deploy-0.7.30.log`。
4. **起跑前现场**：`goto Farm --no-focus` FarmHouse(9,9) → Farm(64,15) hop1 **7594ms**；`preflight --expect 0.7.30 --save-baseline logs\run9c-baseline.json` ⇒ **✅ 可以起跑**，基线 = **夏 18 日 06:10 / rain / Farm(64,15) / 体力 270 / 钱 205g / 种子 [] / farmingLevel 0 / 作物 55 / unwatered 34 / dryCrops 0 / waterLeft 8 / tillable 72 / 无模态 / worldAdvancing true**。**不做操作员预置**。
5. **派卡**：**task-140**（run9c = run A）已派 machine-runner；起跑命令 `tools\start-detached-longrun.py --days 3 --size 5 --max-minutes 150 --max-days 9 --journal logs\longrun-3day-llm-run9c.jsonl --expect-version 0.7.30`。
