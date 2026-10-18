# 0.7.44 冒烟门禁证据（tag `smoke-0744` · 2026-10-18 18:05–18:16）—— **步 8 FAIL：2 天 0 天 VERIFIED ⇒ 门禁未过，A9 未起**

> **§0 结论先行**：0.7.44 装机上真机短跑 **2 个游戏日（winter 26→28 晨）**，`finish{code:1, verified_streak:0, actions:156, minutes:8.54}`，两日均 `needs_review`、`verified=false`；八步门禁 **步 1/2/3/4/5/6 PASS、步 7【无法判定】、步 8 FAIL**。
> **FAIL 的唯一硬项是 8.1「冬季可验证性」**：`docs\_release-0.7.44.md:40` 要求在 winter 26 上至少 **1 天 `verified=true`**，本跑 **0/2**（`:43` 全绿才放行 A9/B9）。
> **两天的失败形态是同一类：诚实收工，但守卫仍说「今天早些时候还有 N 格没做完（跨片地）」⇒ `day_justified=false` ⇒ 当天不判 VERIFIED**。冬 26 以 `stuck:同一秒连发 5 次换片都没有目标…` 收工、冬 27 以 `resume_exhausted:回片区 217 格都回去看过、换片 4 次…` 收工；而两日 `day_end.plot_pending=0 / plot_pending_executable=0 / plot_pending_blocked=0`（§3/§8）。判据未改、未重跑、未 restore。
> **A9 未起跑、A9-start 备份原样未动**（`logs\ab-backup\A9-start\MANIFEST.json` 1222 B / SHA256 `5479354B…98A3D`，四件逐字节核过，§1.4）；冒烟把当前存档推进到 **winter 28 晨**（§2.5），后续是否用 A9-start 复原由 Lead 决定，我不动存档。

- 执行：teammate `machine-runner`｜卡：task-8（冒烟门禁阶段）｜被测版本：**0.7.44**（冻结提交 `37cac51`，起跑时 HEAD `ac1cea2`）
- 证据源：`logs\longrun-smoke-0744.jsonl`（308 行 / 209017 B）、`logs\longrun-smoke-0744.console.log`（58 行 / 8147 B）、`logs\longrun-smoke-0744.version.json`、`logs\longrun-smoke-0744-baseline.json`、`logs\longrun-smoke-0744-gaps.json`、`logs\longrun-smoke-0744-lessons.json`、`logs\longrun-smoke-0744-llm.jsonl`、`logs\smoke-0744-smapi-window.txt`（2297 行 / 232349 B）、`scratch\smoke-0744.json`、`scratch\smoke-0744-save-chain.json`、`scratch\smoke-0742-observe-*.json` ×19、`logs\longrun-smoke-0744-guardian.log` ×1 + `-state.json` + `.console.log`
- 现场（2026-10-18 18:2x 实测）：无 `Stardew Valley` / `StardewModdingAPI` 进程、`netstat -ano` 无 `:17890` LISTENING、`%APPDATA%\StardewValley\AgentFarm\bridge.json` **不存在**
- 本文数字一律带「文件:行号」；账本行号 = `logs\longrun-smoke-0744.jsonl` 的 1-based 行号；SMAPI 行号 = 冻结窗口 `logs\smoke-0744-smapi-window.txt` 行号（与源 `SMAPI-latest.txt` 逐字节一致）

---

## §1 起跑四要素与冻结一致性

### 1.1 构建 / HEAD / 工作树（`logs\longrun-smoke-0744.version.json`）

| 项 | 值 | 出处 |
|---|---|---|
| HEAD | **`ac1cea2`**（`docs(release): 更正 0.7.44 冒烟门禁与 A9/B9 起跑命令为实测 CLI`，提交时刻 18:04:59） | version.json `:2` |
| 冻结提交 | `37cac51`（18:00:50） | `git log` |
| 冻结→起跑差异 | `git diff --name-only 37cac51..ac1cea2` = `docs/00-开发日志.md`、`docs/_release-0.7.44.md` **仅文档** ⇒ 生产代码与冻结一致 | 08:0x 实测 |
| worktree_clean | `false`；`git_status_short` 原文 = `["M scratch/smoke-0742.py", "?? scratch/_t13_a8_census.py", … , "?? scratch/_t8_goto_farm.py"]`（我的探针修复 + log-analyst 的 scratch，无生产文件） | version.json `:27-38` |
| sidecar 五文件 | 与**当前树逐字节 5/5 MATCH**（见 1.2） | 18:2x 复核 |
| `boundary_llm` | `true` | version.json `:44` |

### 1.2 五文件 SHA256（sidecar 原文 ↔ 当前树复核）

| 文件 | SHA256 | 复核 |
|---|---|---|
| `brain/agentfarm/longrun.py` | `1789C862ADE18616A474140E22773EFD7DEC22254A72473AD018655709823D77` | MATCH |
| `brain/agentfarm/farmwork.py` | `88E14811260363F606EFA55C688E8DDB46E6BF3A7DE1162E2CDC5645F38370A0` | MATCH |
| `brain/agentfarm/bridge.py` | `75EFBB9AD9FD7AB2395C0B670761C930153DD21F68BCBFC3B028360FA4F0696D` | MATCH |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `806C1069D217EEEFAB6D3354BA09DA049847D97EE5B4A1D2D65845F1DCB0B17F` | MATCH（= 冻结 dll） |
| `mod/AgentFarm.Bridge/manifest.json` | `77003E0B9EBD0C0644787831AF814274A9283BFC857BB5DF271FB3D9BF49DB92` | MATCH |

### 1.3 起跑 argv 原文（`version.json:29-43`）

```
C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe -u tools/run-longrun.py
--days 1 --size 5 --max-minutes 60 --max-days 2 --journal logs/longrun-smoke-0744.jsonl
```

- `--days 1`（目标尾部连续 1 天 VERIFIED）、作业区 5×5、`--max-days 2` 封顶；**argv 里没有 `--no-crops`**（`--no-crops` 只作用于冒烟脚本 pre/post 的判据，不传给起跑器）。
- 脑 PID **10528**，`started_at=2026-10-18T18:07:31`（`version.json:25-26`）。

### 1.4 同起点备份与冒烟前存档（`logs\ab-backup\A9-start`，未动）

| 文件 | size | mtime | SHA256 |
|---|---|---|---|
| `Wahaha_450799035` | 3141826 | 2026-10-18 17:03:52 | `053CAA71007CEA6FB20D865154DACA236C4FC69F314774B9AC118FB5188F4AF7` |
| `SaveGameInfo` | 32305 | 2026-10-18 17:03:52 | `3D964F3F30AF39C3F33CCCD210C7CC76760B569349A16F12AFC91BB8144B9293` |
| `Wahaha_450799035_old` | 3121459 | 2026-10-18 16:49:07 | `E5B60E915BA393E87FD053A05DFE87FDFAF0F838F8C724F4E50D5B026964B19E` |
| `SaveGameInfo_old` | 32472 | 2026-10-18 16:49:07 | `9DD16B9462C3A213CE9A924D9CF4A34DC8F61406908D877F5919D49812E69525` |
| `MANIFEST.json` | 1222 | 2026-10-18 18:02:55 | `5479354B0628D5B547C7B1670A9B5C36296594FD8F77EF53DA48AD9105988A3D` |

- MANIFEST 原文：`arm=A9`、`created_at=2026-10-18T18:02:54`、`game_running_at_backup=false`（18:2x 复核：**备份目录未动**，四件与 GO 指令给出的三哈希一致）。
- 冒烟起跑前现场存档四件与上表**逐字节一致**（18:0x 实测）⇒ 冒烟起点 = A9 起点（winter 26，钱 2767 g，无作物，farmingLevel 3）。

### 1.5 游戏世界起点（`logs\longrun-smoke-0744-baseline.json`）

```
generatedAt=2026-10-18T18:07:31+07:00  worldSeq=63  modVersion=0.7.44
day=[1,"winter",26]  timeOfDay=750  location=Farm  playerTile=[31,17]
stamina=244.49992  money=2767  isInBed=false  seeds=[["483","Wheat Seeds",10]]
farmingLevel=3  crops=0  unwateredCrops=0  dryCrops=0  waterLeft=13
tillableCount=181  tileCount=400  tilesTruncated=true  activeMenu=null
isModal=false  worldAdvancing=true
```

- 游戏/桥环境：SMAPI 首行 `[18:05:50 INFO SMAPI] SMAPI 4.5.2 with Stardew Valley 1.6.15 build 24356`（SMAPI 窗口 `:1`）；桥首行 `18:05:57`、末行 `18:16:14`。
- 起跑时已 07:50（timeOfDay 750）：pre 阶段（含 goto Farm）先把 06:1x 推到 07:50 —— 见 §4 步 3 与 `logs\longrun-smoke-0744-baseline.json`。

---

## §2 两日读数（逐日）

### 2.1 时间线（真实时刻 ≈ 脑 t0 18:07:31 + 账本 t）

| 真实时刻 | 事件 | 账本行 |
|---|---|---|
| 18:05:50 | SMAPI 起（deploy-mod --no-quit 起游戏） | SMAPI `:1` |
| 18:06:40 | `goto Farm` 走位 `POST /v1/exec` 7650 ms（= 我脚本记录 7630 ms） | SMAPI 慢 exec 列表 |
| 18:07:11 | guardian 起（`--tag longrun-smoke-0744 --detach`，PID 3460） | guardian.log `:1` |
| 18:07:31 | 脑起跑（PID 10528），世界 winter 26 07:50 | journal `:1`（day_start）、baseline |
| 18:14:00 | 冬 26 入睡（`sleep` **t=389.74**，journal `:235`）→ `day_end t=389.89` | journal `:235-240`、`:302` 为冬 27 入睡 |
| 18:14:01 | 冬 27 06:00 开始（跨日保存完成，SMAPI NewDay `:1613`） | journal `:241` |
| 18:15:58–18:16:01 | 冬 28 保存链（SMAPI NewDay `:2276`；主档 mtime 18:16:01） | SMAPI `:2276-2285` |
| 18:16:03 | `finish code=1 verified_streak=0`（t=512.27） | journal `:308` |
| 18:16:14 | guardian 判据成立（脑死 + finish 已出现）⇒ 自动 `stop-game.py --wait 45` | guardian.log `:9-10` |

> 注：冬 26 的 `sleep` 事件在账本 `:238` 前后（`stage_midway_leftover t=389.74` → `lessons` → `day_end t=389.89` → `day_start t=389.91`），入睡真实时刻 ≈ **18:14:00.7**。

### 2.2 冬 26（`logs\longrun-smoke-0744.jsonl:240`，`day_end t=389.89`）

| 项 | 读数 |
|---|---|
| day_start | `:1` `1年 winter 26日 开始`，timeOfDay 750，体力 244.49992，钱 2767 g，作物 0（未浇 0），天气 sunny |
| ended_by / verified | `sleep` / **false** |
| ended_reason（原文） | `stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：今天早些时候还有 263 格没做完（跨片地，最近的是 [12, 17]））` |
| checks | 仅 `day_justified=false`；`slept_by_us / no_blocking_modal / no_hard_failures / unreachable_within_bound / refused_within_bound / no_unmet_stages / crops_watered / watered_outdoor / zero_action_evidenced` 全 `true` |
| 步数 | `ok_steps=71`、`skipped_steps=0`、`failed_steps=0`、`assigned_undone=0` |
| unreachable | 16 格（`bound=21`、`exempt=0`）：`[15,24] [16,23] [16,29] [16,30] [32,16] [32,19] [32,21] [33,19] [33,20] [34,13] [34,19] [36,15] [36,17] [36,18] [38,17] [40,30]` |
| refused | 0（bound 21） |
| encircled | 1 格 `[[32,20]]`（四邻无可清障突破口，不进 unreachable 豁免） |
| plot_pending | `plot_pending=0` / `plot_pending_executable=0` / `plot_pending_blocked=0` / `plot_pending_by_kind={}` |
| bound_basis | 109 |
| 终态 | `final{timeOfDay:1550, tile:[13,17], stamina:125.40015, money:2767, crops:0, tillable:198, waterLeft:13, seeds:[["483","Wheat Seeds",10]], farm:{loaded:true,hoeDirt:8,crops:0}}` |
| 体力 | `stamina_budget{max:270, stamina:244.5, capacity:126, deferred_by_budget:false, suppressed:1}`；`stamina_calibration clear_area{actions:71, spent:119.1, per_action:1.68}` |
| 阶段 | clear_area **40 轮**（首轮 `{ok:0,leftover:211,assigned:12,stopped:"unreachable"}`；末轮 `leftover:0`） |
| 种子 | 补种子 probe 失败 `item_not_sold`（SeedShop 没有 472）；`no_seed_for_sale`，当天不再试（console `:6-7`） |
| intent_coverage | `winter26#02 till_area` / `#03 plant_area` 均 `no_target`（没当季种子）；`dead_crops_status/dry_dead_status ok` |

### 2.3 冬 27（`logs\longrun-smoke-0744.jsonl:306`，`day_end t=512.22`）

| 项 | 读数 |
|---|---|
| day_start | `:241` winter 27 开始（06:00），体力 270（睡前 125.4 + 睡醒恢复），钱 2767 g |
| ended_by / verified | `sleep` / **false** |
| ended_reason（原文） | `resume_exhausted:回片区 217 格都回去看过、换片 4 次，当前观测里没有可执行目标（守卫仍说：今天早些时候还有 217 格没做完（跨片地，最近的是 [38, 36]））` |
| checks | 仅 `day_justified=false`，其余全 `true` |
| 步数 | `ok_steps=20`、`skipped=0`、`failed=0`、`assigned_undone=0` |
| unreachable | 3 格（bound 5）：`[[39,31],[39,32],[40,32]]`；refused 0（bound 5） |
| encircled | 0 |
| plot_pending | `0 / 0 / 0`，`plot_pending_by_kind={"clear_area":0}` |
| bound_basis | 20 |
| 终态 | `final{timeOfDay:800, tile:[39,36], stamina:152.50009, money:2767, tillable:200, hoeDirt:8, crops:0, seeds:[["483","Wheat Seeds",10]]}` |
| 体力 | `stamina_budget{max:270, stamina:270, capacity:126, deferred_by_budget:false, suppressed:1}` |
| 阶段 | 7 轮：clear_area `{ok:12,leftover:220,assigned:12}`、till_area `{ok:0}`、plant_area `{ok:0}`、clear_area `{ok:3,leftover:0}`、`{ok:1}`、`{ok:2}`、`{ok:2}` |
| intent_coverage | `winter27#01 clear_area` / `#02 till_area` 均 `unknown_evidence`（`obs_unavailable`，note「作业区离玩家 19 格，观测看不见，先走过去再看」） |
| 收工路径 | `:300 no_progress_burst t=491.84` 原文「回片区 / 换片 / 当前观测都没有可执行目标 ⇒ 今天按 resume_exhausted 诚实收工：睡下去让游戏日前进，但绝不写 stuck、也绝不判 VERIFIED」 |

### 2.4 收尾（journal `:307-308`）

- `:307 day_cap {"t":512.22,"days":2,"max_days":2}`（`--max-days 2` 封顶；实际两日均 needs_review，未凑出 VERIFIED）。
- `:308 finish` 原文：`{"event":"finish","t":512.27,"code":1,"verified_streak":0,"actions":156,"minutes":8.54,"stages_seen":["clear_area","plant_area","till_area"],"no_unmet_stages":true,"unmet_days":[],"stuck_flushes":0,"cleanup_modal_stuck":false,"cleanup_attempts":0,"cleanup_menu":""}`。
- console 收尾原文：`L39 × 试了 2 个游戏日仍未凑出连续 1 天，停下`、`L40 [run] needs_review：尾部连续 0/1 天 （共 2 天，156 个动作，8.54 分钟）；no_unmet_stages=True`、`L57 finish {…}`、`L58 终态：needs_review`。

### 2.5 冒烟后存档四件（当前盘上 = winter 28 晨；**不是** A9 起点）

| 文件 | size | mtime | SHA256 |
|---|---|---|---|
| `Wahaha_450799035` | 3049414 | 2026-10-18 18:16:01 | `32B526643FC3812B3417F97F41BAB8E1214F5D2C44179672FE80A519BA4A4B1B` |
| `SaveGameInfo` | 32181 | 2026-10-18 18:16:01 | `E625D020F3805A56B86A5741ED934AB7F7486BB9A8812063D99E8E718D3A28A8` |
| `Wahaha_450799035_old` | 3107720 | 2026-10-18 18:13:59 | `59FC5F50B6E14B7E39985778AF3287EE2B0A7FD7D15CCE3FFB72D3B391ECCBAA` |
| `SaveGameInfo_old` | 32181 | 2026-10-18 18:14:00 | `B1622909B0BF74F8480A08A840CC8BD1528A938CA92555CA89330EECCB43A871` |

- 两次跨日各落盘一次（18:13:59 / 18:16:01），与 SMAPI 六串 2/2 一致（§5）；`finish`(18:16:03) 在末次落盘之后。
- **A9 若起跑需先 restore A9-start（winter 26）**；A9-start 备份本身未被本跑触碰。是否 restore 由 Lead 决定（GO 纪律：冒烟门禁未过，不进第二步）。

---

## §3 两段收工 reason 原文与 `day_end` 关键字段

### 3.1 reason 原文（`day_end.ended_reason` = console 同文）

- **冬 26**：`stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：今天早些时候还有 263 格没做完（跨片地，最近的是 [12, 17]））`
- **冬 27**：`resume_exhausted:回片区 217 格都回去看过、换片 4 次，当前观测里没有可执行目标（守卫仍说：今天早些时候还有 217 格没做完（跨片地，最近的是 [38, 36]））`

### 3.2 机读判据链（代码锚点）

- `brain/agentfarm/longrun.py:553`：`JUSTIFIED_END_REASONS = ("night","stamina","no_work")`
- `brain/agentfarm/longrun.py:563` `def is_justified_end(ended_by, ended_reason)`；`:570-572`：`if ended_by != "sleep": return False` / `return str(ended_reason or "").split(":",1)[0] in JUSTIFIED_END_REASONS`
- ⇒ `stuck` / `resume_exhausted` 两个前缀都不在白名单 ⇒ `day_justified=false` ⇒ `verified=false`。
- 守卫文案的生成：`longrun.py:4797`（`pending = self._pending_work()`）+ `:4801-4803`（`今天早些时候还有 {len(pending)} 格没做完（跨片地，最近的是 {…}）`）；`:4816` `_pending_work()` 注释口径「排除已封格/预算延后/认输收获格，但 `tile_attempts` 到顶仍算」。
- 0.7.44 新增路由：`:8644-8650` 守卫不放行 → `_guard_leftover_resume` → `_resume_switch_or_exhaust`；`:8662` `plot_exhausted` note；`:8666-8676` `burst >= PLOT_EXHAUSTED_BURST` ⇒ `_do_sleep(stuck:同一秒连发…)`；`:8677-8683` `recovered > max_plots_per_day` ⇒ `stuck:换过 {n} 片地都没有目标…`。

### 3.3 `day_end` 结构化摘录（大数组折叠，完整原文见行号）

- 完整原文：冬 26 = `journal:240`（**76114 字符**）、冬 27 = `journal:306`（**16877 字符**）。`logs/` 在 `.gitignore:13` 里不入库，本机文件保留；可用 `scratch\_t8_smoke_evidence.py` 重新导出（输出 `scratch\_t8_smoke_dayend.txt`）。
- 冬 26 关键字段（全量见 §2.2；此处补 checks 原样）：`checks = {"slept_by_us":true,"no_blocking_modal":true,"no_hard_failures":true,"unreachable_within_bound":true,"refused_within_bound":true,"no_unmet_stages":true,"day_justified":false,"crops_watered":true,"watered_outdoor":true,"zero_action_evidenced":true}`；`refused={bound:21, exempt:0, tiles:[]}`；`unreachable={bound:21, exempt:0, tiles:[16 格]}`；`encircled={count:1, tiles:[[32,20]]}`；`dead_crops=0, dry_dead=0, deferred_tiles=0, scope_shed=0, slept_ok=true, stuck_flushed=false`。
- 冬 26 `outcomes`：首条 `clear_area terminal=needs_review progress=false`，reason 原文「…目标 12 步：做成 0…其中 11 格走不到…提前停：unreachable；后置条件未成立（还剩 211 格，其中 11 格已判定干不动：(32,16)…(32,19)…(32,21)…）」；后续多条 `terminal=VERIFIED postcondition_met=true`。
- 冬 26 `notes`（19 条）含：补种子失败 / 无当季种子 / 工具升级 / 校验取消 till+plant / 记 11 格走不到 / `resume_walk 1..10/10` 与换片 `1..4/10` / 已开满 10 片地。
- 冬 27 `notes`（19 条）含：无当季种子 / `resume_walk 1..6/10` 与换片 `1..4/10` / 记 1 格走不到 ×3 / `回片区 217 格 / 换片 4 次都拿不出目标…按 resume_exhausted 诚实收工（不判 VERIFIED）` / 收工复盘 3 条 / 主动睡觉。
- 两日 `plots[]` 均带 `tilesTruncated=true`（冬 26 10 片、冬 27 4 片）：`observe` 的 `tiles[]` 有 400 格上限，plot 级坐标被截断，按「缺失≠通过」不当作 plot 完整性证据。
- 两日 `stages[0].leftover` 分别 211 / 220（首轮阶段分下去的格），但 `day_end.plot_pending=0` —— 即**阶段 leftover 与 plot 级 pending 两个口径不一致**（§8）。

---

## §4 八步门禁读数（`scratch\smoke-0744.json`，generated_at 18:16:23）

`phases_run = [pre, pre, launch, launch, wait, post]`（pre 两趟：首跑步 3 无法判定 → goto Farm 后 `--only 3` 重跑；launch 两趟：首跑 rc=4 探针 bug → 修复后 PASS）。

| 步 | 判 | 读数（evidence 原文/摘要） |
|---|---|---|
| 1 env_check | **PASS** | `crafting_recipes` 读到 `Furnace matchedCount=1`，无 `unknown_skill` |
| 2 trigger_actions | **PASS** | `trigger_actions` 可读，无 `InvalidCastException` |
| 3 砍树（tree） | **PASS** | `location=Farm`、`isOutdoorFarm=true`；window 内 tree 216 格、可站立邻格 32；`walk=(31,17) 成功 move_to 10178ms ws14→58`；前两次 `use_tool` 收 `tool_ineffective`，第 3 次 receipt ok「Axe 对 (32,17) 动手 3 次…现在上面已经没有东西了」；`tile.kind: tree→none`，`calls=3` |
| 4 起跑四要素 | **PASS** | `pid=10528`、`journal_lines=308`、`last_event=finish`、finish 字段与账本一致；起跑器先 `--dry-run` 过四要素再真起跑 |
| 5 逐格证据（task-242） | **PASS** | 91 个 `clear_area ok` 格全部逐格对上：**等值阶段 41 / 可解释 0** |
| 6 六串配对 | **PASS** | 六串 **2/2/2/2/2/2**（`save_called` 原始 3、L16 假阳性 1 行排除）；`checker_rc=0`，`VERDICT: PASS`；行号见 §5 |
| 7 幂等/事件 | **无法判定** | 「账本里没有 `slot_relief` 事件 ⇒ 空间压力通道本批没被触发（缺失≠通过）」；`无法判定·无作物`（`--no-crops`：冬季第 1 天农场 `crops==0`，`day_end.intent_coverage` 里根本没有 harvest 条目） |
| 8 冬季可验证性 | **FAIL** | 8.1 原文「2 个日报告里没有一天 `verified=true`（冬季必须能验证）」；8.2 子项见下 |

### 4.1 步 8 其余子项

- `trees` **PASS**：winter26 `913→897`（delta -16，n=11）、winter27 `910→896`（delta -14，n=4）。
- 但 `trees` 里混入 **2 份 14:0x 生成的旧观测**（winter5 `839→828`，n=2；旧 0.7.42 门禁跑残留），属污染，不参与本次判决。
- `clear_throughput` / `budget_reason` **无法判定**：账本无 `tool_ineffective` 事件、无 `deferred_by_budget`（体力不是早退原因）。
- 8.2① 单发 `tool_ineffective` 在步 3 出现过两次（探针自己触发的回执），已在上表说明。

### 4.2 探针 bug（与本跑产品缺陷分开判）

- `scratch\smoke-0742.py:377` 原写死 `"--expect-version", EXPECT_VERSION`（模块常量 `EXPECT_VERSION="0.7.42"`，`:77`）；preflight 实测 0.7.44 ≠ 0.7.42 ⇒ 起跑器拒绝（launch 首跑 rc=4）。
- 修复：`:377` 改用 `args.expect_version`（并加注释「探针 bug 与产品 bug 分开判」）。修复后 launch PASS；`git diff` 仅此一处（CRLF 警告：工作区 CRLF 下次触碰转 LF，不影响运行）。
- 这是**探针缺陷**，不是 0.7.44 产品缺陷；本文件 8.1 FAIL 与它无关。

---

## §5 六串配对（跨日落盘）

### 5.1 SMAPI 冻结窗口（`logs\smoke-0744-smapi-window.txt`）

| 项 | 值 |
|---|---|
| copy size / mtime | 232349 B / 2026-10-18 18:16:23 |
| SHA256（源=副本） | `5AD308CCC3118FF013772A329EC23CABE17F207B9CBDD82C279AC4A9013CF7E1` |
| 源文件 | `%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt`（source_mtime 18:16:14，`byte_identical=true`） |
| 行数 | 2297（窗口内带时间戳行 2291） |
| 首行 | `[18:05:50 INFO  SMAPI] SMAPI 4.5.2 with Stardew Valley 1.6.15 build 24356` |
| 末 4 行 | `[18:16:14 TRACE game] Disconnected: ClosedGame` / `[18:16:14 TRACE SMAPI] Disposing...` / `[18:16:14 INFO AgentFarm Bridge] 已删除发现文件 …bridge.json。` / `Disposing the content coordinator` |
| 桥行 | 1541 条（首 18:05:57、末 18:16:14）：health 67 / exec 516 / observe 958；exec 耗时 max **23339 ms**（18:13:33），>5 s 共 12 条（23339/15022/14497/12345/11742/10805/10799/10192/8826/8429/7659/7650） |

### 5.2 六串行号与计数（`scratch\smoke-0744-save-chain.json`，checker = `scratch\save-chain-check.py`）

| 串 | 计数 | 行号 |
|---|---|---|
| [1] `NewDay` | 2 | `[1613, 2276]` |
| [2] `Context: before save` | 2 | `[1615, 2279]` |
| [3] `SaveGame.Save() called` | 2（原始 3，L16 假阳性 1） | `[1617, 2280]` |
| [4] `Synchronizing 'Save' task` | 2 | `[1618, 2281]` |
| [5] `completed without exceptions` | 2 | `[1621, 2284]` |
| [6] `Context: after save` | 2 | `[1622, 2285]` |

- 末次 NewDay 行 2276 / 末次 Save called 行 2280 / 末次 after save 行 2285；链内顺序 ✅（2 次保存链均满足 before < called < [task] < completed < after）。
- checker 尾行原文：`VERDICT: PASS（退出码 0）`；`=== 账本 === 308 行 / day_end 2 / verified [False, False] / finish True`。
- 与存档 mtime 对照：18:13:59 / 18:16:01 两次落盘 ⇒ **两次跨日都已落盘**（跨日≠落盘 的坑本次未踩）；`finish`(18:16:03) 在末次 `after save`(18:16:01) 之后。
- 出货模态：`--no-crops` 且两日 `shippingBin.count=0`、`crops=0`，未触发 `ShippingMenu` 推迟保存路径（本跑无出货）。

---

## §6 HUD 异常观察（Lead m00446 要求；结论：**无法判定 / 未复现**）

- **用户目击**：红色 X「Inventory Full」原生 HUD，冬 26 14:10，钱 2767 g；当时背包 **12/36**（16 份 `--capture-observe` 观测里 `player.inventoryCount` 全程恒 12）。
- **时点映射**：game clock 1410 ≈ 真实 **18:12:35**（脑 t0=18:07:31；timeOfDay 750→1600 用 389.6 s 线性内插）；对应账本 t≈296–305 段与 SMAPI 18:12:23–18:12:53 段。
- **账本行**：`:183 intent_verdict t=281.6`；`:184 outcome t=285.72`「field_ne 目标 1 步 做成 1 后置成立」；`:185 work_spot t=285.83`；`:186 resume_walk t=296.73`；`:187 decision t=296.81`；`:188 intent_verdict t=296.81`；`:189 outcome t=305.35`「field_sw 目标 3 步：做成 3、跳过 0、失败 0、后置条件成立」。**14:10 前后无 slot / no_slot / inventory 事件**。
- **SMAPI 前后窗口原文**（同一时刻段）：
  - `18:12:23 health 0 ms worldSeq=913`
  - `18:12:28 POST /v1/exec 10805 ms worldSeq 913→935`（近似对应 resume_walk 走位）
  - `18:12:33 health ws=955`；`18:12:33 exec 5393 ms ws=959`；`18:12:34 exec 539 ms ws=959`
  - `18:12:35 exec 400 ms / 527 ms ws=960`；`18:12:36 exec 422 ms / 526 ms ws=961`
  - `18:12:43 health ws=988`；`18:12:52 POST /v1/exec 15022 ms ws=1026`
  - 同段 observe 多条 7–41 ms（观察通道未阻塞）
- **第二证据源均无**：①冻结 SMAPI 全窗口 `Inventory` 唯一命中 = `:16`（len 43661，Mod 0.7.44 发布说明行），`HUD` 0 命中；②账本无 slot 类事件；③19 份观测无 HUD/Inventory 字段（grep `InventoryFull|inventoryFull|freeSlots` 0 命中）；④`mod/` 全树 0 处 `showRedMessage|HUDMessage|addHUDMessage`（grep 实测）。
- ⇒ HUD 归因 **【无法判定】**：Mod 侧无调用痕迹、日志无留痕；本跑**未复现**。按 Lead 口径继续挂观察（真实时刻 + game clock + journal 末 3–5 行 + SMAPI 前后各 5 行），不改跑法、不打断长跑。

---

## §7 机械事实（优雅退出 / 无残留）

- guardian（`logs\longrun-smoke-0744-guardian.log`，22 行）：
  - `:1` 18:07:11 start（`interval=10s stall=180s bridge_stale=120s dry_run=False`）
  - `:3-4` 18:07:11 安全闸「PID 文件缺失 ⇒ 无法证明脑死，不触发」（起在脑之前，未误杀）
  - `:5-6` 18:07:31 brain pid=10528 alive=True 桥 ok；`:7-8` 18:12:33 brain alive lines=188 last=intent_verdict@296.81
  - `:9-10` 18:16:14 **trigger=True**（brain alive=False、lines=308 last=finish@512.27、finish=True）「判据成立：脑死 且 finish 已出现」
  - `:12` stop 命令 `…python.exe -u …tools\stop-game.py --wait 45.0`；`:13` 游戏在跑 pids=[14044]；`:14` 桥就绪 modVersion=0.7.44
  - `:15-18` quit_game 回执 ok → ✅ 游戏已退出（原 pids=[14044]）→ rc=0
  - `:19-22` 进程数=0、`bridge.json exists=False`、`17890 LISTENING=False`、`[exit] code=0`
- 18:2x 复核：`tasklist` 无 Stardew 进程；`netstat -ano` 无 `:17890`（仅历史 TIME_WAIT）；`bridge.json` 不存在。
- 残留物：`logs\longrun-smoke-0744.pid`（5 B，内容 `10528`）与 `-guardian.pid`（4 B，内容 `3460`）在脑/守护退出后仍留在盘上（pid 文件不自动删，与 A8 同）；guardian 用「进程不存在」判脑死，不依赖 pid 文件存在性 ⇒ 不影响判据，记为观察项。
- `console.err.log` 0 B（无 stderr 异常）。

---

## §8 缺陷线索清单（给 dev-coder / log-analyst；≤20 行，判决归 Lead）

> 线索只列账本行号 + 事件 + 代码锚点；不改判据、不重跑。

1. `L58 work_spot t=77.46`「今天还有 25 格没做完（field_sw，玩家窗口看不见）」→ `L60 resume_walk` → `L62 plot_exhausted`（回片区连续拿不出目标 ⇒ 换片）—— 0.7.44 新路由在**当天早期**就进入「回片区/换片」循环。
2. `L185 work_spot t=285.83`「还有 2 格」→ `L186 resume_walk t=296.73`（走了 **11.3 s**）→ `L204 work_spot t=338.73`「还有 2 格」→ `L206 resume_walk t=362.06`。
3. `L210 stage_no_target t=362.19` → `L213 work_spot t=362.3`「还有 2 格」→ `L216/220/224/228/232 plot_exhausted t=362.31~362.63` **五连发**，reason 原文「这一片没目标了，但守卫仍要求干活（**今天早些时候还有 263 格没做完**（跨片地，最近的是 [12, 17]））⇒ 换一片地」。
4. `L233 plot_exhausted_burst t=362.63`（同一秒连发 5 次）→ `L240 day_end verified=false`（`ok_steps=71`、`plot_pending=0`）。
5. 冬 27：`L268 work_spot t=459.97`「25 格」→ `L270 resume_walk`；`L272 plot_exhausted t=460.43`；`L274 work_spot t=463.49`「23 格」→ `L275 plot_exhausted`；`L285 work_spot t=477.64`「20 格」→ `L288 plot_exhausted t=477.78`；`L290 work_spot t=484.42`「25 格」→ `L291 plot_exhausted` → `L292 resume_walk`。
6. `L293 work_spot t=487.92`「5 格」→ `L300 no_progress_burst t=491.84` 原文「回片区 / 换片 / 当前观测都没有可执行目标 ⇒ 今天按 resume_exhausted 诚实收工…绝不写 stuck、也绝不判 VERIFIED」→ `L306 day_end verified=false` → `L307 day_cap` → `L308 finish code=1 streak=0`。
7. **矛盾数字 A**：两日 `day_end.plot_pending=0 / plot_pending_executable=0 / plot_pending_blocked=0`（冬 26 by_kind `{}`、冬 27 by_kind `{"clear_area":0}`），但 `day_end.stages[0].leftover` 分别 **211 / 220**。
8. **矛盾数字 B**：收工 reason 引「今天早些时候还有 **263 / 217** 格没做完」，与 plot 级 pending 0 并存（`bound_basis=109 / 20`）。
9. 守卫文案来源确认：`brain/agentfarm/longrun.py:4797-4803`（`pending = self._pending_work()` 的结果直接拼进 reasons）；`:4816` `_pending_work()` 口径「排除已封格/预算延后/认输收获格，但 `tile_attempts` 到顶仍算」。
10. 换片/收尾路由：`:8644-8650 _guard_leftover_resume → _resume_switch_or_exhaust`；`:8662 plot_exhausted note`；`:8666-8676 burst≥PLOT_EXHAUSTED_BURST ⇒ stuck`；`:8677-8683 recovered>max_plots_per_day ⇒ stuck`。
11. 冬 27 走 `resume_exhausted` 不写 stuck（`L300` 明确「绝不写 stuck」），但 `is_justified_end`（`:563-572`）白名单只有 `night/stamina/no_work` ⇒ 两日都 `day_justified=false`。
12. `day_end.plots[*].tilesTruncated=true`（冬 26 10 片 / 冬 27 4 片）：`observe` `tiles[]` 400 格上限导致 plot 级坐标截断（note 有 `tilesTruncated` 但无结构化字段）。
13. `intent_coverage`：冬 26 `winter26#02 till_area`/`#03 plant_area` 均 `no_target`（`no_seed_for_sale`：SeedShop 无 472、Wheat 隔季）；冬 27 `#01 clear_area` `unknown_evidence`/`obs_unavailable`「作业区离玩家 19 格」。
14. `unreachable`：冬 26 16 格（含 `[32,20]` 被 `encircled` 单独计数，`L13 encircled t=8.88`）；`logs\longrun-smoke-0744-gaps.json` 记 tree `blocked_tile` 12 格；冬 27 3 格 `[[39,31],[39,32],[40,32]]`。
15. `stamina_budget`：两日均 `deferred_by_budget=false`（冬 26 stamina 244.5/max 270、冬 27 270/270）⇒ 不是体力早退。
16. `stage_shortfall` 多条（`L23 t=9.04`、`L86 t=105.62`、`L116 t=159.39`、`L198 t=338.09`）`stopped=unreachable`；冬 26 `no_unmet_stages=true`（豁免被扣完）。
17. 工具链定位：`tests/test_longrun.py:7388` 注释确认「`work_reasons`/`sleep_guard` 用的是**跨片地当日 leftover**」；`tools/analyze-longrun.py:5185/5254/7632/7798` 有旧口径「弃权后 ended_reason 仍说守卫仍说还有活 ⇒ ⚠ 警告」。
18. 账本/console 路径：`logs\longrun-smoke-0744.jsonl`（308 行）、`logs\longrun-smoke-0744.console.log`（58 行）；`llm` 对话 `logs\longrun-smoke-0744-llm.jsonl`（14192 B，备份收工复盘可查）。
19. 建议先查 `_pending_work()` 的 day-level leftover 集合为何在 plot 级 pending 已 0 时仍非空（是否包含已换片/不可执行格，或与 stage leftover 记账口径不一致），再定「守卫仍说活没干完」的计数修正口径。
20. 判决由 Lead 出；本清单只是线索，未改判据、未重跑、未起 A9。

---

## §9 已知限制（照实写）

1. **步 7 无法判定**：账本无 `slot_relief`（空间压力通道未触发）且 `--no-crops` 冬季无 harvest 子项 ⇒ 【无法判定】，不是 PASS。
2. **步 8.2 树差分 PASS 但含污染**：混入 2 份 14:0x 旧观测（winter5 839→828，旧 0.7.42 跑残留）；本跑两日数据（-16 n=11 / -14 n=4）可用，旧两份不参与判决。
3. **冒烟期间 HEAD 变动**：起跑时 HEAD=`ac1cea2`（仅 docs 变更，生产与冻结一致）；`a1d23b8`（analyze/tests/scratch，+752/+423 行）**18:18:59** 才提交（冒烟已结束），步 7 使用的 `analyze-longrun.py` 版本未锁定在旁证里；该步结论是「缺失事件 ⇒ 无法判定」，不依赖新分析逻辑。生产五文件与 sidecar 已 5/5 复核为冻结版本。
4. **六串只覆盖 2 次保存**（2 个游戏日）；更长日程的保存链由 A9/B9 长跑另证。
5. **HUD**：无法判定（§6），仅 1 次用户目击、日志与代码均无痕迹。
6. **本文件不判 A9/B9**：只交冒烟门禁读数与证据；A9 是否起跑、是否 restore A9-start 由 Lead 判决。
7. **存档现状**：当前档已推进 winter 28 晨（§2.5），与 A9-start（winter 26）不同；未做任何 restore。
8. **探针 bug 已修**（§4.2），属探针缺陷，与产品缺陷分开记。

---

## §10 复现命令与产物哈希表

### 10.1 命令原文（按实际执行顺序）

```powershell
# 0) 起游戏（部署 + 自动读档 Wahaha_450799035，桥 0.7.44）
PYTHONUTF8=1 & $py tools\deploy-mod.py --no-quit
# 1) pre（首跑：步1/2 PASS、步3 无法判定，location=FarmHouse）
PYTHONUTF8=1 & $py scratch\smoke-0742.py --phase pre --tag smoke-0744 --expect-version 0.7.44 --no-crops
# 2) 走到 Farm（我新增 scratch\_t8_goto_farm.py：BridgeClient.observe + move_to_location("Farm")，只走不清）
PYTHONUTF8=1 & $py scratch\_t8_goto_farm.py
# 3) pre 步3 重跑（仅步3）
PYTHONUTF8=1 & $py scratch\smoke-0742.py --phase pre --only 3 --tag smoke-0744 --expect-version 0.7.44 --no-crops
# 4) launch（首跑 rc=4 探针 bug → 修 :377 后重跑 PASS；后台 job 跑）
PYTHONUTF8=1 & $py scratch\smoke-0742.py --phase launch --tag smoke-0744 --expect-version 0.7.44 --days 1 --size 5 --max-minutes 60 --max-days 2 --capture-observe --observe-every 120 --no-crops
# 5) 起跑成功后立即起 guardian（脱离式）
PYTHONUTF8=1 & $py tools\run-guardian.py --tag longrun-smoke-0744 --detach
# 6) wait
PYTHONUTF8=1 & $py scratch\smoke-0742.py --phase wait --tag smoke-0744 --expect-version 0.7.44 --wait-minutes 60 --capture-observe --observe-every 120 --no-crops
# 7) post（冻结 SMAPI + 步5/6/7/8）
PYTHONUTF8=1 & $py scratch\smoke-0742.py --phase post --tag smoke-0744 --expect-version 0.7.44 --freeze-smapi --no-crops
```

### 10.2 产物哈希表

| 文件 | size | mtime | SHA256 |
|---|---|---|---|
| `logs\longrun-smoke-0744.jsonl` | 209017 | 18:16:03 | `1175748483326CD4605F5E95A0340166D010F75C8BD0C7C9A7B3913E8251E13C` |
| `logs\longrun-smoke-0744.version.json` | 1703 | 18:07:31 | `65BE07091483E47DB9541B35822E78DD3F4FDFB7B909C50A1002CF5F29B952FA` |
| `logs\longrun-smoke-0744-baseline.json` | 705 | 18:07:31 | `3699C7066CCC6DDC2BE5888067627BF9608F43C44B75F0C22EDBC65CE3B87B38` |
| `logs\longrun-smoke-0744.pid` | 5 | 18:07:31 | `FB0924424CA6FE968898C408C84C932BA3AEC5698674E2523026AC41E4F09442` |
| `logs\longrun-smoke-0744.console.log` | 8147 | 18:16:03 | `F10559EAF0A1EB29D565580387D48BF908FDD52ECC878E7A5DE2E54DB011FD5D` |
| `logs\longrun-smoke-0744.console.err.log` | 0 | 18:07:31 | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `logs\longrun-smoke-0744-lessons.json` | 1997 | 18:16:03 | `024B6CD23A0F6673E147DA958518E7D2E23BF2C8BE6CD210CA9FFB340CE50A38` |
| `logs\longrun-smoke-0744-llm.jsonl` | 14192 | 18:15:47 | `764D89B76BE6D33AD1BF570836A51C6EC41204061BC5AA89CC87660E9CAF6B23` |
| `logs\longrun-smoke-0744-gaps.json` | 1230 | 18:14:01 | `483F7EA14E81F607DE5E83E7CB8E3E5BEDFE0B1BE25CFFE8F7F3110765BE3372` |
| `logs\smoke-0744-smapi-window.txt` | 232349 | 18:16:23 | `5AD308CCC3118FF013772A329EC23CABE17F207B9CBDD82C279AC4A9013CF7E1` |
| `logs\longrun-smoke-0744-guardian.log` | 2734 | 18:16:17 | `7A34E570FFA871E93D682EAEF7DAD71B8B6F7E9F25DEFA8CCC4011B8CA3880C0` |
| `logs\longrun-smoke-0744-guardian-state.json` | 2210 | 18:16:17 | `CEB311BBA4EF67362C992DC089F57055F5FA1D18D1B7727AD62AFF31D20B0415` |
| `logs\longrun-smoke-0744-guardian.console.log` | 2294 | 18:16:17 | `A087082BA36FECBB54B198E04B57186E68A4DC4C8976C4B402FFA28A2C7DDBE9` |
| `logs\longrun-smoke-0744-guardian.pid` | 4 | 18:07:11 | `C89B4E41F654EEA7EB98D53066D86785177654A42694ADA4FA7A99C9C2597071` |
| `scratch\smoke-0744.json` | 67984 | 18:16:23 | `1BE221DFB9FCA05C85AD4BECD58AC2E17770671B560EE55B1348564E18938381` |
| `scratch\smoke-0744-save-chain.json` | 2919 | 18:16:23 | `52FB837A4BBB72DF1985F8A35542D6F74AA1920893A9F643D526E578BE79C470` |

（`logs/` 与 `scratch/*.json` 均不入库；上表哈希为 2026-10-18 18:2x 实测。）
