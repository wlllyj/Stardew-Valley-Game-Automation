# task-54 独立验收：task-50 / task-51 / task-52 / task-63 + 豁免洗白对抗

- 复核人：deputy-lead（只读生产代码；产物只写本文件与 `scratch/`）
- 时间：2026-10-13 21:30–22:05（Asia/Bangkok）
- 对象：当前 HEAD 工作树 = 四卡提交 `9d50f54`(task-50 brain+tests) / `1a57ea6`(task-51) / `294daea`(task-52) / `0d4d1c0`(task-63)，
  加 task-50/51 的 Mod 侧提交 `28f5974`(FarmScan dryTiles) / `1a57ea6`(deadCrops)，以及 Lead 的发布提交 `e381e58`（0.7.25 冻结）
- 真机：`0.7.25` 已装机、run6 已跑完；游戏在跑（**本次全程只读，未启动/未触碰游戏与桥**）

## 判定摘要

| 项 | 判定 | 一句话 |
|---|---|---|
| task-50（窗口外干格） | **PASS** | 全场 `dryTiles` 与窗口口径分离；缺字段判"不可用"而非"没有干格"；走不到 ⇒ `stuck:` 点名坐标；m50a 变红 |
| task-51（清死苗） | **PASS** | 目标池只收 `crop and dead`；活苗守卫在 `farmwork.clear_dead`；顺序 water→harvest→clear_dead→ship→…；m51a/m51b 各自变红 |
| task-52（unreachable 豁免） | **PASS-WITH-NITS** | 脑侧全过；**工具侧卡面 ⑥"扣了豁免但 journal 没写 ⇒ 判问题"未满足**（实测只记 info），见 NIT-1 |
| task-63（游戏拒绝豁免） | **PASS** | 只对 `TILE_INERT_STATUSES` 生效；"回执 ok 但世界没变"仍 failed；两套豁免各自有界；m63a 变红 7 条 |
| 对抗 4 项（(a)(b)(c)(d)） | **3 条打穿（工具侧）+ 1 条固有不可判** | (a) 仅"0 成功"时被反空洞挡住；(b) 不可判；(c)(d) 可打穿；另有卡面 ⑥ 方向也可打穿 |
| run6 快速失败 | **如实判红，不是判据 bug** | 42 格真不可达（全 `field_ne`、无落脚点），当天 0 步成功、54 格 leftover；根因在作业区选择，见 §5 |

## §1 基线读数（全部我亲跑）

```
git status --short                       → 仅 ?? docs/_run6-evidence.md（非我范围）
git log --oneline -6                     → HEAD fcf0116 …
mod/AgentFarm.Bridge/manifest.json:4     → "Version": "0.7.25"
brain/agentfarm/bridge.py:39             → MOD_VERSION_EXPECTED = "0.7.25"（Lead 的 e381e58，非作者越界）
dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental
                                          → 0 个警告 / 0 个错误（1.98s）
python -W error::SyntaxWarning -m py_compile <brain/agentfarm/*.py + tests/*.py>  → exit 0
python -m unittest discover -s tests      → Ran 455 tests in 3.490s / OK
```

四卡用例单独跑（9 个类，含 tests/test_farmwork.py 与 tests/test_longrun.py 两侧）：

```
python -m unittest -v tests.test_longrun.TestTask50FarDryTiles tests.test_longrun.TestTask52Unreachable \
  tests.test_longrun.TestTask51ClearDead tests.test_longrun.TestTask63Refused \
  tests.test_farmwork.TestTask63Refused tests.test_farmwork.TestFarmDryTiles \
  tests.test_farmwork.TestTask52Unreachable tests.test_farmwork.TestFarmDeadCrops \
  tests.test_farmwork.TestTask51ClearDead
→ Ran 39 tests / OK
```

用例分布：`tests/test_longrun.py:2889 TestTask50FarDryTiles`(5)、`:3131 TestTask52Unreachable`(5)、
`:3251 TestTask51ClearDead`(3)、`:3354 TestTask63Refused`(5)；`tests/test_farmwork.py:796 TestTask63Refused`(5)、
`:1319 TestFarmDryTiles`(4)、`:1362 TestTask52Unreachable`(5)、`:1433 TestFarmDeadCrops`(2)、`:1455 TestTask51ClearDead`(6)。

### §1.1 基线之后的上游变更（复核期间发生，必读）

我在 `fcf0116`（干净树）取的 455 OK / `dotnet build` 0 警 0 错基线；复核收尾时 HEAD 已前进到 **`6b9ebfb`**，其间新增的提交**只碰** `docs/`、`tools/analyze-longrun.py`、`tools/verify-run3.py`、`tests/test_verify_run3.py`、`tests/test_analyze_longrun.py`、`scratch/`
（`git diff --stat fcf0116..6b9ebfb` 逐文件核对；**四卡涉及的 `brain/`、`mod/`、`tests/test_longrun.py`、`tests/test_farmwork.py` 一个字节都没动**）。工作树 tracked 文件与 HEAD `6b9ebfb` 逐字节一致（`git diff --numstat` 空）。

**当前全量单测 = `Ran 473 tests / 1 failure`**（473 = 455 + 上游新增 18 条）：

```
FAIL: test_event_buckets_cover_every_brain_journal_name
      (tests.test_analyze_longrun.TestEventMappingDrift)
AssertionError: Lists differ: ['day_end','day_start','finish','no_seed_for_sale','seed_unavailable_today']
                 != ['day_end','day_start','finish']
⇒ EVENT_BUCKETS 落后于 brain/agentfarm/longrun.py
```

缺映射的两个名字 = `no_seed_for_sale`（`brain/agentfarm/longrun.py:1615`、`farmwork.py:738`）与 `seed_unavailable_today`（`longrun.py:1381`）—— 都是**买种子/货架**那条线（task-67）的 journal；**四卡的新事件**（`unreachable`/`unreachable_stage`/`unreachable_summary`/`tool_refused`/`refused_summary`/`clear_dead_scope` 等）**已经**在 `EVENT_BUCKETS` 里。见 NIT-7。

## §2 四卡逐条

### task-50（Mod 全场干格坐标 + 脑侧走过去浇）

| 卡面 | 证据 |
|---|---|
| Mod 传 KVP `Key`、`dryTiles`/`dryTilesTruncated`、上限 64、按 y 再 x 排序、同一次扫描 | `mod/AgentFarm.Bridge/FarmScan.cs:41 DryTilesMax = 64`、`:258 AccumulateTerrain(entry)`、`:303 _dryTiles.Add`、`:235-254 PublishDryTiles()`（`:240` 排序 y,x；`:242-245` 超限置 truncated；`:253-254` 异常 ⇒ 空 + truncated=true）；`Contracts.cs:553 dryTiles`、`:559 dryTilesTruncated` |
| 脑：`farm_dry_tiles` 返回坐标 + 状态；缺字段/证据不可信 ⇒ `unavailable`，**不许当"没有干格"** | `brain/agentfarm/farmwork.py:608-641`（`:626-627` loaded/complete 判据、`:628-630 raw is None ⇒ unavailable`、`:631-640` 逐条 int 容错 + 去重、`:641` truncated） |
| 窗口有可见干格 ⇒ `water_area`；无可见但有 `dryTiles` ⇒ 走过去浇，判据 = 观测差分 | `brain/agentfarm/longrun.py:2515 if self._water_far_dry(obs, rep): continue`；dry 状态位 `:551-556`；走过去浇/stuck 点名 `:2511-2533` |
| 走不到 ⇒ `stuck:` + 坐标，绝不 `no_work` | 同上；用例 `test_unreachable_far_dry_tile_ends_stuck_with_coordinates` |
| 有界（每格每天 ≤2 次 + 总上界） | `longrun.py:2438 far_dry_tries`（日清空）；用例 `test_far_dry_retries_are_bounded_per_day` |
| 老 Mod 缺字段行为同旧 | 用例 `test_old_mod_without_dry_tiles_is_not_no_dry_tiles`（test_longrun 侧） |

**独立变异**：m50a 把 `farm_dry_tiles` 的"缺字段 ⇒ unavailable"改成"⇒ ok 空表" ⇒ 红 2 条：
`tests.test_farmwork.TestFarmDryTiles.test_missing_or_untrusted_farm_is_unavailable_never_empty`、
`tests.test_longrun.TestTask50FarDryTiles.test_old_mod_without_dry_tiles_is_not_no_dry_tiles`。⇒ **用例真能证伪**。

### task-51（Mod 死苗计数 + 脑侧清死苗）

| 卡面 | 证据 |
|---|---|
| Mod `deadCrops` 走全场扫描 | `FarmScan.cs:280 DeadCrops++`；`Contracts.cs:520 deadCrops`；`WorldSnapshot.cs` 同步 |
| 脑新增 `clear_dead` 动作，判据 = `crop` 消失 | `farmwork.py:1256 clear_dead`、`:1329` 状态标签（无作物/枯死/活苗）、`STAGE_ACTION :177 "clear_dead"` |
| **活苗绝不碰** | `farmwork.py:1284 if not (tv or {}).get("dead"): return skipped`（动作层守卫）；目标池 `longrun.py:1285`、`:1335` 都是 `v.get("crop") and v.get("dead")` |
| planner 在 `deadCrops>0`/窗口内 dead>0 时给意图；顺序 water→harvest→clear_dead→ship→clear_area→till_area→plant | `planner.py:88 TASK_KINDS 含 clear_dead`、`:531 if tile.get("dead")`；用例 `test_planner_puts_clear_dead_between_harvest_and_ship` |
| 诚实性：清死苗失败仍 `skipped+proven_inert`；走不到归 `unreachable` | `farmwork.py:1353-1359`（unreachable 出口，reason 原样保留）、`:1378-1386`（skipped+proven_inert，判据未满足照实） |
| 窗口 vs 全场留痕 | `longrun.py:1848-1853` journal `clear_dead_scope{in_view, farm, status}` |
| ≥5 条假世界单测 | test_longrun 3 + test_farmwork 6 = 9 条 |

**独立变异**：m51a 把 `longrun.py:1335` 的目标池过滤去掉 `dead` ⇒ 红 `test_stage_tiles_leftover_and_plot_work_see_dead_crops_only`；
m51b 拆掉 `farmwork.py:1284` 的活苗守卫 ⇒ 红 `test_live_seedling_is_never_touched`。⇒ 两条安全属性**分别**被独立用例钉住。

### task-52（unreachable 独立分类 + 有界豁免 + 逐格留痕）

| 卡面 | 证据 |
|---|---|
| ① 独立 `code=unreachable`；`StepResult.failed` 对它 False；reason 原样 | `farmwork.py:121 UNREACHABLE_CODE`、`:125 UNREACHABLE_STATUSES`、`:129 UNREACHABLE_HINTS`（与 `tools\verify-run3.py:264` 同组）、`:388-394 failed`（只认 `code=="failed"`）、`:397-399 unreachable`、`:554-568 is_unreachable(status, text)` |
| ② 计数 + **逐格坐标进 journal**；当天记 blocked、次日清空 | `longrun.py:1707-1720`（`self.blocked[key]=…`、`unreachable_day.add(key)`、journal `unreachable{tile,action,stage,zone,reason,note}`）；日清空 `:2530`/`:2532`；stage 侧 `:1905-1913` + journal `unreachable_stage :1917`；日级 `:2711-2727` |
| ③ 有界 `unreachable ≤ max(5, floor(0.2×attempted))`；反空洞 | `longrun.py:2712 unreachable_bound = max(5, int(0.2 * attempted_steps))`、`:2804 unreachable_within_bound`、`:2811-2812 no_unmet_stages = unmet_leftover==0 and (made_any_progress or (unreachable_exempt==0 and refused_exempt==0))` |
| ④ `no_hard_failures` 只数真 failed；工具把 unreachable 当信息项；**字段缺失不得当通过** | `longrun.py:2801`；工具 `tools\verify-run3.py:264`（marks）、`:268-283`（journal 自算，会话键 `(day_key, _lineno)`）、`:450-460`（attempted/bound/exempt，缺失即自算）、`:474-478`（账本≠自算 ⇒ info） |
| ⑥ 同一豁免也作用到 `no_unmet_stages`；扣掉的格必须 journal 可见，**"扣了但没写"判问题** | `longrun.py:2751 unmet_leftover = max(0, raw_unmet - unreachable_exempt - refused_exempt)`；工具 `:648 effective_leftover`、`:652-658`（与 `checks.no_unmet_stages` 不一致 ⇒ problem）—— **但"扣了但没写坐标"只落成 info**，见 NIT-1 |
| ⑤ ≥6 条假世界单测 | 10 条（5+5），名与断言见 §1 与 §4 |

**验收读数**：`py_compile -W error::SyntaxWarning` exit 0；全量 455 OK；**run6 里 unreachable 日 `checks.no_hard_failures=True`**（§5）。
**独立变异**：m52a（`StepResult.unreachable` 恒 False）⇒ 7 红；m52b（`unreachable_bound` 恒 10^9）⇒ 1 红（`test_exceeding_the_bound_trips_the_check_and_kills_verification`）。

### task-63（游戏拒绝 = 世界前置事实，不算硬失败）

| 卡面 | 证据 |
|---|---|
| ① `till()` 世界没变且 `status ∈ TILE_INERT_STATUSES` ⇒ `skipped+proven_inert`；**回执 ok 但格子没变仍 `failed`** | `farmwork.py:84 TILE_INERT_STATUSES = ("tool_ineffective", "precondition_failed")`；till 收尾分支 `:1364-1378`（`refused=True`）、兜底 `:1379-1384`；用例 `test_game_refusal_is_skipped_and_proven_inert` / `test_ok_receipt_but_world_unchanged_is_still_failed` / `test_precondition_failed_is_also_a_refusal` |
| ② `refused_bound = max(5, floor(0.2×attempted))`，超界照实 `no_hard_failures=false`；`day_end` 增 `refused`/`refused_tiles`/`refused_bound` + journal `refused_summary` | `longrun.py:305-308`（字段）、`:2736`（bound）、`:2801`（`no_hard_failures = failed_steps==0 and refused <= refused_bound`）、`:2807`；journal `tool_refused :1730-1733`、`refused_summary :2753-2759` |
| ③ 两套豁免互不覆盖、各自有界各自留痕 | `:1726` 注释 + 两个独立集合（`unreachable_day :544`、`refused_day :549`）；扣减处见 NIT-3 |
| ④ 被拒格当天封格、次日清空重试，不整片放弃 | `_mark_blocked :1727`（`self.blocked[key]=…`）+ `_run_day` 日清空 `:2530/:2532`；用例 `test_next_day_retries_the_same_refused_tiles` |
| ⑤ ≥6 假世界 + ≥2 变异自检 | 10 条（5+5）；我另做 m63a |

**独立变异**：m63a（`TILE_INERT_STATUSES = ()`）⇒ 7 红（含两侧 `test_refused_tiles_do_not_hard_fail_an_otherwise_good_day`、`test_exceeding_the_bound_trips_the_check_and_kills_verification`）。

## §3 对抗实验：豁免洗白（(a)(b)(c)(d) + 卡面 ⑥）

工具：`scratch/_t54_forge.py` 从 `scratch/journal-green.jsonl` 第 1 天造 6 本伪造账本（自带自洽 `finish{code:0,days:1,verified_streak:1}`）；
复现：`& $py tools\verify-run3.py --journal scratch\review-t54-<变体>.jsonl --days 1`（pwsh 下 `>` 重定向会写 UTF-16，读回要 `-Encoding Unicode`）。

| # | 变体（`scratch/`） | 构造 | exit | 结论 |
|---|---|---|---|---|
| ① | `review-t54-vacuum-all-unreachable.jsonl` | 8 格全不可达 + 0 步成功 + 自称 VERIFIED（(a) 的极端形态） | **1** | **反空洞有效**。problem 原文：`自称 VERIFIED 但当天成功动作 0 步（有阶段记录、ok 全 0）` + `checks.no_unmet_stages=True 与自算不一致（…扣掉不可达豁免 8 + 锄不动豁免 0 后剩 0 格、当天成功动作 0；期望 False）` |
| ② | `review-t54-inflate-bound-attempted.jsonl` | 42 格不可达、账本 `unreachable_bound=9999`、`attempted=50`、另有 20 步成功浇水 | **0** | **打穿 (c)**。info 原文 `豁免上界 bound=9999（attempted=50）`：上界与实扣**全信账本**，不与 `attempted` 交叉核对 |
| ③ | `review-t54-exempt-without-coords.jsonl` | `unreachable_exempt=3`、`unreachable_tiles=[]`、**零 journal 事件** | **0** | **打穿卡面 ⑥**。info 原文 `账本=3、journal 自算=0 次/0 格` ⇒ 卡面要求"扣了但没写坐标 ⇒ 判问题（缺失≠通过）"，实测只记 info |
| ④ | `review-t54-failed-relabeled-unreachable.jsonl` | 4 条真失败 `blocked`（reason=`锄完不是 dirt（kind=未知）`）+ 4 条假 `unreachable` 事件、`failed_steps=0`、另有 20 步成功 | **0** | **打穿 (b)**：真失败改写成"不可达"，账本层看不出（无坐标/无世界证据可对） |
| ⑤ | `review-t54-overlap-two-sets.jsonl` | 同一组 2 个坐标**同时**进 `unreachable_tiles` 与 `refused_tiles`；`raw_unmet=2`、两边各 exempt 2 ⇒ 相减后 0 | **0** | **打穿 (d)**：两套豁免重复扣减未被察觉（工具 `:653` 与 `longrun.py:2751` 都直接相减） |
| ⑥ | `review-t54-overlap-two-sets-inconsistent.jsonl` | 照抄 ⑤ 但 `checks.no_unmet_stages=false` | **1** | 对照组：problem `checks.no_unmet_stages=False 与自算不一致（…扣掉不可达豁免 2 + 锄不动豁免 2 后剩 0 格、当天成功动作 6；期望 True）` ⇒ 工具**确实在算** effective leftover，⑤ 的洞是"两集合未去重" |

**可达性判定（哪些是"脑会犯的"，哪些只是"账本可伪造"）**

- (b) **不可判**：账本是唯一输入，"真失败 vs 不可达"的世界证据不在账本里 ⇒ 属账本检查器的**边界**（对应 `docs\_verify-run3-limits.md` 的"账本检查器 ≠ 世界校验器"）。可加的只是启发式：当天存在未命中豁免关键词的 `blocked` 事件而 `failed_steps==0` ⇒ info。
- (c) 脑侧 `unreachable_bound` 由 `longrun.py:2712` 现算，**正常不会虚报** ⇒ 属**工具加固**方向（防"代码改坏/账本被改"）。
- (d) 脑侧当前**不可达**：`_mark_blocked` 对两套豁免都当天封格（`:1705-1734`），且 `_stage_tiles` 过滤 `self.blocked`（`:1311`、`:1430`、`:1941`）⇒ 同一天同一格不会既 unreachable 又 refused。但工具信账本 ⇒ 仍值得按坐标去重加固。
- 卡面 ⑥ 的方向（③）：**脑侧可达**（只要豁免靠账本字段而 journal 掉一条就是这形态），且卡面明确要求判问题 ⇒ 见 NIT-1。

## §4 独立变异证伪（我自己写、自己跑）

脚本 `scratch/_t54_falsify.py`（副本 `scratch/_t54_mut/agentfarm`；先预导入副本模块，避开 `tests/test_farmwork.py:22` 把 `brain/` 插进 `sys.path[0]` 的劫持；打印并断言 `USED_LONGRUN/USED_FARMWORK` 指向副本）：

```
& $py scratch\_t54_falsify.py <mode> <tests...>
```

| mode | 改什么（生产文件:行） | 期望红 | 实测 |
|---|---|---|---|
| none（对照） | — | 全绿 | run=18 successful=True |
| m52a | `farmwork.py:397-399` `unreachable` 属性 ⇒ `return False` | task-52 用例 | **7 红**（farmwork 2 + longrun 5，含 `test_stage_counts_match_the_per_tile_journal`、`test_next_day_retries_the_same_unreachable_tiles`） |
| m52b | `longrun.py:2712` bound ⇒ `10 ** 9` | 超界用例 | **1 红** `test_exceeding_the_bound_trips_the_check_and_kills_verification` |
| m63a | `farmwork.py:84 TILE_INERT_STATUSES ⇒ ()` | task-63 用例 | **7 红**（farmwork 2 + longrun 5） |
| m50a | `farmwork.py:628-630` `raw is None ⇒ unavailable` 改成 `⇒ ok` | task-50 缺字段用例 | **2 红**（`test_missing_or_untrusted_farm_is_unavailable_never_empty`、`test_old_mod_without_dry_tiles_is_not_no_dry_tiles`） |
| m51a | `longrun.py:1335` 目标池去掉 `dead` 过滤 | 池用例 | **1 红** `test_stage_tiles_leftover_and_plot_work_see_dead_crops_only` |
| m51b | `farmwork.py:1284` 活苗守卫 ⇒ `if False:` | 活苗用例 | **1 红** `test_live_seedling_is_never_touched` |

⇒ 四卡的关键判据都有**能红的**用例；m51a/m51b 说明"池过滤"与"动作层守卫"是两条独立防线。

## §5 run6 真机判定：合法豁免被上界卡住，还是真超界？

事实（`logs\longrun-3day-llm-run6.jsonl`，143 行，我亲读）：

- `finish = {t:37.2, code:1, verified_streak:0, actions:95, minutes:0.62, stages_seen:["clear_dead","till_area"], no_unmet_stages:false}`
- `day_end`（summer 4，两轮）`failed_steps=0`、`unreachable=42`、`unreachable_bound=8`、`unreachable_exempt=8`、`refused=0`；
  `checks = {no_hard_failures:True, unreachable_within_bound:False, refused_within_bound:True, no_unmet_stages:False, watered_outdoor:True}`
- stages：`clear_dead(ok 0, leftover 30, attempted 12, unreachable 12)`、`till_area(0,24,12,12)`、`clear_dead(0,30,12,12)`、`clear_dead(0,30,6,6)` ⇒ **全阶段 0 步成功**
- `ended_reason = stuck:连续 3 轮世界没有任何变化（最后意图：['clear_dead']；策略说有进展：False）；守卫仍说还…`
- 42 条 `unreachable` 事件**全部** `zone=field_ne`、reason `四邻都站不过去（没有落脚点）`，坐标密集在 (59–75, 18–26)
- `tools\verify-run3.py` ⇒ exit 1，problem：`checks.unreachable_within_bound=false（不可达豁免超出上界 bound=8）` + `ended_by=stuck` + `verified=false`；
  info：`账本=42、journal 自算=42 次/42 格、豁免上界 bound=8（attempted=42）、实际扣除 exempt=8`

**我的判定 = 偏"真超界/如实判红"，且"上界公式偏小"这一半不成立**：

1. 每阶段种类最后一条 leftover = 30(clear_dead) + 24(till_area) = **54 格没做完**；豁免最多扣 8 ⇒ 还剩 46 ⇒ `no_unmet_stages=False` 与上界无关。
2. 反空洞条款（`:2811-2812`）本来就要求"0 成功日不许靠豁免换 VERIFIED"——本日 0 成功。
3. 42 格确有世界依据：同一个 zone、同一个 reason（四邻都无落脚点），且是 `clear_dead`/`till_area` 两种不同动作各撞一半 ⇒ 不是"一种动作的系统性误分类"。
4. 真正的洞在**作业区选择/可达性**：这一天把全部动作花在 `field_ne` 一个 zone 的无落脚点密集簇上，既没切 zone 也没拿到任何 ok ⇒ 对应 Lead 已立的 task-67/task-68。
5. 因此**不建议**用"放宽 `unreachable_bound`"去救 run6 —— 那会同时放松防洗白；正确方向是 task-68 的可达性 + 切区（`plot_exhausted`/`stuck` 之外要有"这个 zone 干不了、换一个"的路径）。

## §6 NIT 清单

| # | 现象（行号） | 建议 | 阻塞 |
|---|---|---|---|
| NIT-1 | 卡面 task-52 ⑥ 要求"扣了豁免但 journal 没写 ⇒ 判问题（缺失≠通过）"，但 `tools\verify-run3.py:466-472`（自算=0/0 格仍只开 info）与 `:479-483`（账本≠自算只 info）都不判问题；变体 ③ 实测 exit 0 | 加硬判据：`unreachable_exempt > 0` 且 `len(self_tiles) == 0`（或 `unreachable_exempt > len(self_tiles)`）⇒ problem；refused 侧同理（`:512-517` 已有"账本 < 自算 ⇒ problem"，缺反向的"账本 > 0 而自算 0"） | **建议必改**（卡面条款未满足） |
| NIT-2 | `tools\verify-run3.py:458-461` 无条件采信账本 `unreachable_bound`；变体 ② 用 `bound=9999` 过 | 与自算 `max(5, int(0.2*attempted_total))` 比对：账本 > 公式 ⇒ problem（至少 info 升级） | 建议改 |
| NIT-3 | `tools\verify-run3.py:653` 与 `brain/agentfarm/longrun.py:2751` 都把两套豁免直接相减，未按坐标去重；变体 ⑤ 过（脑侧当前不可达） | 扣减前按坐标 union 去重；工具对"同一坐标同时出现在 `unreachable_tiles`/`refused_tiles`" ⇒ problem | 建议改 |
| NIT-4 | 变体 ④：真失败被改写成 unreachable，账本层不可判 | 只做启发式（有未命中关键词的 `blocked` 事件而 `failed_steps==0` ⇒ info），并把"不可判"写进 `docs\_verify-run3-limits.md` | 不阻塞 |
| NIT-5 | 39 条四卡用例里**没有**覆盖 NIT-1（扣了豁免没写坐标）与 NIT-3（两套豁免重叠）两个方向 | 各补 1 条假账本/假世界用例 | 不阻塞（与 NIT-1/3 同批） |
| NIT-6 | run6 `day_end` 没有 `attempted` 字段（工具回退 Σ stages.attempted） | 卡面未要求；建议补上便于对账 | 不阻塞 |
| NIT-7 | **当前全量单测红 1 条**：`tests/test_analyze_longrun.py:884 TestEventMappingDrift.test_event_buckets_cover_every_brain_journal_name` —— `EVENT_BUCKETS`(`tools/analyze-longrun.py`) 缺 `no_seed_for_sale`(`brain/agentfarm/longrun.py:1615`、`farmwork.py:738`) 与 `seed_unavailable_today`(`longrun.py:1381`)（task-67 那条线，**不是四卡**） | 把这两个名字加进 `EVENT_BUCKETS`（`tools/analyze-longrun.py` 的桶表），或按作者意图只加进"已知但无桶"白名单；改完复跑 `tests/test_analyze_longrun.py` | **必改**（树是红的，冻 0.7.26 前要绿） |

另：`farmwork.py:1332-1337` 里 `till_blocked_by` 命中（含缺锄头）走 `skipped + proven_inert=True` 但 **`refused=False`** ⇒ 不计入任何豁免；它仍算 `attempted`（`:393-395`）并留在 leftover 里 ⇒ 属于"照实不做完"，符合口径（记录以免误判为漏标）。

## §7 越界与卫生

- 四卡提交 `9d50f54`/`1a57ea6`/`294daea`/`0d4d1c0` 的 `--numstat` 里 **没有** `mod/AgentFarm.Bridge/manifest.json`、`logs/`、`docs/00-开发日志.md`；Mod 侧改动在 0.7.25 冻结前单独提交（`28f5974`/`1a57ea6`）。卡面写"未 bump"指的是**作者没有自己 bump**，实际 bump 来自 Lead 的发布提交 `e381e58` ⇒ 不属越界。
- 我本次：只读 `brain/`、`mod/`、`logs/`、`tests/`；产出只写 `docs/_review-task50-52.md` 与 `scratch/`（`_t54_forge.py`、`_t54_dbg.py`、`_t54_ledger_shape.py`、`_t54_falsify.py`、`_t54_run5_days.py`、6 本 `review-t54-*.jsonl`）；未改生产代码与既有断言；未启动/未触碰游戏与桥。

## §8 task-68 落地后需要复验的差分点

1. **口径放宽不许把 run6 救活**：新 `unreachable_bound` 口径下，`1年 summer 4日` 仍须 `no_unmet_stages=False`（54 格 leftover、0 成功）与 `unreachable_within_bound` 的判定如实；若新口径让这天变成 `verified=true`，就是放水。
2. **切区路径**：若 task-68 让"选定 zone 全不可达 ⇒ 换区/落 `plot_exhausted`"，要在 run7 账本里看到换区事件且当天 `ok>0`；只有 `stuck` 仍算失败。
3. **工具侧 NIT-1/2/3 若采纳**：重跑 6 本 `review-t54-*.jsonl`（期望 ②③⑤ 全部翻成 exit 1 且判红原文互不相同）+ `scratch/journal-green.jsonl`（必须仍 exit 0，0 误报）+ run5/run6（判决不变）。
4. **真机复验**：run7 里 unreachable 日要同时满足 `no_hard_failures=true`（已达成）**且**至少一个 stage `ok>0`，否则不该 VERIFIED。

## §9 结论

- task-50 / task-51 / task-63 = **PASS**（逐条打勾、用例可证伪、变异各自变红）。
- task-52 = **PASS-WITH-NITS**：脑侧全过（分类、逐格 journal、当天封格次日重试、有界、反空洞、run6 `no_hard_failures=true`）；**工具侧卡面 ⑥ 未满足**（NIT-1）。
- 对抗结论：**反空洞闸门有效**（0 成功日打不进去）；但 **(c) 虚报上界、(d) 两套豁免重复扣减、卡面 ⑥ 方向（扣了豁免没写坐标）三条能在账本层打穿**，(b) 真失败改写不可判（账本检查器边界）。三条工具侧洞都给了硬判据建议（NIT-1/2/3）。
- run6 的 37 秒快速失败是**如实判红**，根因是作业区选择把一天花在无落脚点的 `field_ne` 簇上（task-67/68），**不是**判据或上界造成的。
- 另有**独立于四卡**的树级红灯：`tests/test_analyze_longrun.py:884`（`tools/analyze-longrun.py` 的 `EVENT_BUCKETS` 缺 task-67 的 `no_seed_for_sale` / `seed_unavailable_today`）⇒ 当前全量 `Ran 473 / 1 failure`，冻 0.7.26 前必须变绿，见 NIT-7。
- 四卡自身在**当前 HEAD（6b9ebfb）**下复跑单测仍全绿（39 条四卡用例 `Ran 39 / OK`）。
