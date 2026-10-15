# run6 验收判据（Lead 定稿 · 2026-10-13）

> 本文件是 run6（0.7.25，task-50/51/52 落地后）的**唯一判据口径**。
> 宗旨：**只认真实证据**，不接受自述；**判据缺失 ≠ 通过**；历史错判据一律作废。

## 0. 为什么要有这份文件（踩过的坑，别再犯）

1. **作废判据**：曾要求「每天 `day_end.final.location == "Farm"`」——错。`final` 是**睡前**快照，而正常成功的一天是"走回 FarmHouse → 上床 → 睡"，`final.location` 本来就可能是 `FarmHouse`。run4 曾据此误报。
2. **run3 的真实病灶**：在**室内**用**窗口口径**认定 `no_work`，同时户外还有干作物 ⇒ 连睡 4 天。因此新增判据：`ended_reason` 以 `no_work` 开头的日子必须 `final_water.dry == 0`（`tools/verify-run3.py` 已实现该闸门）。
3. **run5 暴露的两条判据走火**：①「四邻都站不过去」被算成当天硬失败（task-52 修，且豁免同时作用到 `no_unmet_stages`）；②`farm.dryCrops` 把枯死作物也算"干"（task-50/51 修）。

## 1. 每天必须成立（`brain/agentfarm/longrun.py:2358-2373` 的 7 条与，缺一不可）

`rep.verified = all(rep.checks.values())`：

| 判据 | 含义 | 备注 |
|---|---|---|
| `slept_by_us` | `ended_by == "sleep"` | 必须是我们自己睡成功（跨日 +1 已由独立证据核对） |
| `no_blocking_modal` | `ended_by not in ("modal","blocked_event")` | 事件/职业弹窗 ⇒ 当天不算数（task-11/41） |
| `no_hard_failures` | `failed_steps == 0` | task-52 后"不可达"不计入（且有界） |
| `no_unmet_stages` | 每个 stage 当天最后一条记录 `leftover == 0` | task-52 后不可达格子同样豁免（有界） |
| `crops_watered` | 窗口口径 `final.unwatered_crops == 0` | **旁证**：室内恒 0，会白过 |
| `watered_outdoor` | farm 口径 `dryCrops == 0`（或当天最后一个户外窗口逐格全湿） | **唯一浇水证据**（task-19）；字段缺失即问题 |
| `day_justified` | `is_justified_end(ended_by, ended_reason)`；白名单 `night/stamina/no_work` | **不含** `no_plot`（task-32） |

**真空日闸门（`tools/verify-run3.py` 已实现，2026-10-13 Lead 补）**：`verified == true` 的一天必须**真的做成过事**。

- 有阶段记录但 `Σ stage.ok == 0` ⇒ **判红**（0 步不能自证做过事）。
- 完全没有任何阶段记录 ⇒ 必须有 `no_work` / `night` / `stamina` 收尾理由或 `excuse` 事件，否则**判红**。
- 成功动作 `< 5` 步、或只涉及一个阶段 ⇒ **只出 info**（合法但偏弱的一天，供复核时人读）。

**不可达信息项（`tools/verify-run3.py` 已实现，2026-10-14 Lead 补）**：`unreachable`（"四邻都站不过去 / A* 算不出路"）按 task-52 **不计当天硬失败**，但账本必须自洽。

- 账本字段：`day_end.unreachable`（当天次数）与 `day_end.unreachable_tiles`（逐格 `[[x,y],…]`）；`day_end.stages[i].unreachable` 同理。
- 工具侧独立自算：扫 journal 里 `blocked`/`stage_exhausted`/`unreachable` 事件中含"四邻都站不过去 / 寻路无法到达 / 无法到达 / A* 未算出路径"字样的行（逐格去重）。
- 两者都存在且**不相等** ⇒ 只记 **info**（同一格可能多次重试）；**账本未写字段**但自算 > 0 ⇒ 也记 info（缺失 ≠ 通过，必须有自算值说话）。
- **豁免口径（task-52，2026-10-14 Lead 补）**：账本新增 `day_end.unreachable_bound`（上界 `max(5, floor(0.2×attempted))`）、`day_end.unreachable_exempt`（当天实际从 `unmet` 扣掉的格数）、`day_end.attempted`；`stages[i]` 增 `unreachable_tiles`/`unreachable_leftover`/`attempted`。工具的自算比对**先扣同一笔豁免再比** `checks.no_unmet_stages`（否则合法豁免会被误判成"自述与自算不一致"）。
- **新硬闸门**：`checks.unreachable_within_bound is False`（豁免越界）⇒ **problem** —— 这是"把真失败/不可动格混进不可达来洗白"的直接信号，必须人工核对 `unreachable_tiles`。
- 防洗白不靠本条：**全格不可达 + 当天 0 成功动作**仍被上面的真空日闸门判红（task-52 再加一条：`ok_steps==0 且全部靠豁免` ⇒ `no_unmet_stages` 仍为 false）。

**锄不动信息项（`tool_ineffective`，task-63，2026-10-14 Lead 补）**：`till` 被游戏拒绝（`UseToolSkill` 挥满 `MaxSwings` 恒 false 才报该 status）⇒ 按 task-63 **不算当天硬失败**（`skipped` + `proven_inert`），但账本必须自洽，且与不可达是**两笔各自扣减、互不掩护**。

- 语义分界：**世界没变且 Mod 报 `tool_ineffective`** ⇒ 前置事实（豁免）；**Mod 回执 ok 但格子没变** ⇒ 仍记 `failed`（说谎的回执不许洗白）。
- 账本字段：`day_end.refused`/`refused_tiles`/`refused_bound`/`refused_exempt`；`day_end.checks.refused_within_bound`（**总写** bool）；逐格 journal `tool_refused`、阶段级 `refused_stage`、日级 `refused_summary`。
- 上界 `refused_bound = max(5, floor(0.2×bound_basis))`（**task-78 起分母换成 `bound_basis`，见下条**）；`refused_exempt = min(bound, 仍在 leftover 的被拒格数)`。
- 工具侧：`checks.refused_within_bound is False` ⇒ **problem**；journal 自算 `tool_refused` 逐格数 **多于**账本计数 ⇒ **problem**（账目不可信）；一致 ⇒ 只记 info。两笔豁免（`unreachable_exempt` + `refused_exempt`）在 `no_unmet_stages` 自算里**各自扣完**，且「两笔豁免把 leftover 扣到 0 但当天 0 成功动作」按防真空口径仍算 `no_unmet_stages=false`（镜像 `longrun` 的 `unmet_leftover == 0 and (有进展 or 两笔豁免都为 0)`）。

**风险事件分级（`tools/verify-run3.py` 已实现，2026-10-14 Lead 补）**：`mod_version_mismatch`（版本与脑侧期望不一致）**升格为问题项** —— 版本不符的账本不能当验收证据。其余十类只记 info：`water_far_unavailable`（farm 说还有干作物却拿不到 `dryTiles` 坐标）、`farm_evidence_unavailable`、`sell_failed`、`zones_failed`、`day_key_resnap_failed`、`bridge_unavailable`、`env_spin_capped`、`budget_exhausted`、`day_cap`、`event_blocked`。

**dry 口径与死苗 / 买不起（Lead 2026-10-15 补，run7 实证；task-84/88 修复前适用）**：

- `farm.dryCrops`/`dryTiles` 目前**把枯死作物格也算"干"**（`FarmScan.AccumulateTerrain` 的判据是 `crop != null && !HoeDirt.isWatered()`，**不看 `dead`**）⇒ `checks.watered_outdoor` / `final_water.dry` 在死苗清完之前**不可能为 0**。
- run7 实证（`logs/longrun-3day-llm-run7.jsonl`）：`clear_dead_scope`(t=143) 记 `farm=33` 株死苗，本跑 `clear_dead` 只做成 **32** 株；剩下那一株（高置信 = `[12,30]`，`water_far` 10 次：8 次 `unreachable`、2 次 `ok=true` 但 `dry 6→6`）导致 **`summer 3`/`summer 5` 各烧掉一个整天**（`dry=1`、`verified=false`、`stuck:`）、**`summer 6` 63 次 `idle` + 20 次 `frontier_clear`（约 4.5 分钟）后靠 `stuck_flush` 翻篇**。
- 复核口径：`final_water.dry > 0` 且 `farm.deadCrops > 0` ⇒ **必须点名"疑似死苗"**（task-84 落地前工具侧给 info；落地后 `dry` 只算活苗、`dead_crops` 单列，见 task-84 卡面）。
- **买不起 ≠ 失败**：`seed_gate {seeds:0, money < seed_price}` ⇒ **未发起购买，属设计内**（不是任务失败、不判红、不算 `no_work` 洗白的理由）。run7 的 `buy` 事件 **0 条**正是此形态（`seed_gate` 5 次全是 `{seeds:0, money:14, seed_price:20}`）。brain 侧自 task-55 起补写 `cannot_afford` 事件；工具侧自 task-88 起输出人话行。

## 2. 连续性与外部证据

- **尾部连续 3 天**：`verified == true` 且 `ended_by == "sleep"` 且 `day_after` 比 `day_key` **恰好 +1 天**。
- **【口径澄清 · Lead 2026-10-15（run7 后定，适用于 run7 起）】达标窗口 = "尾部连续 N 天"，不是"整本账本零问题"。**
  - 长跑允许早期日子不达标后**自主恢复**（task-73 的 `stuck` 翻篇就是为此而生）⇒ 落在**窗口之内**的那几天的问题、以及不带 `[day]` 前缀的全局问题（journal 损坏、`mod_version_mismatch`、`finish` 自相矛盾等）才是 fatal；
  - 窗口**之外**日子的问题降级为 `tools/verify-run3.py` 输出里的 **`history_problems`**（逐条列出、可复盘、不影响结论）；
  - **窗口没打满时（`streak < --days`）不降级**，维持原判；**run 必须停在窗口上**（尾部那天坏 ⇒ streak 归零 ⇒ 不过）。
  - 记录在案：run7 在**旧口径（整本零问题）下是 `needs_review`**，在新口径下 **VERIFIED**；差异的 9 条问题（summer 3/5/6）已在输出里逐条列出，不是被抹掉。
  - **【取舍写死 · Lead 2026-10-15（回应 deputy-lead task-86 的第②问）】** 验收范围**就是**尾部 N 天，这是刻意的：用户要的是"**连续 N 个游戏日无人介入**"，不是"整本账本零瑕疵"。代价必须显式承认并留痕：①`docs/_runN-evidence.md` §4 必须**逐条抄出 `history_problems`**，并写清"过的是哪 N 天、窗口外还有 N 条问题"；②若窗口外存在**系统性**问题（同一毛病连续多天、例如 A6 形态：27 天每天都有"浇水没做完" + 尾部 3 天全绿 ⇒ 判 VERIFIED），evidence 必须**单独点出这是系统性缺陷、只是不落在验收窗口内**，不许用"窗口外不计"一句带过；③要严格口径时**直接用工具内置的第二判决**：`tools/verify-run3.py` 现在在人类输出里多打一行 `严格口径（整本零问题，**仅呈现、不参与退出码**）：…`，JSON 里对应 `strict_verdict` / `strict_problem_count`（**只呈现，rc 与 `verdict` 不变**）。`docs/_runN-evidence.md` §4 必须并列这一行（若与 `verdict` 不同），**不许只报宽的那一个**。
  - **健壮性（task-86 FAIL 的修复，2026-10-15）**：`[day]` 前缀解析**绝不能**用"第一个 `]` 截断"。旧实现 `p[1:].split("]", 1)[0]` 被打穿过：只要账本 `day_start.day[1]` 里塞一个 `]`（如 `spring]x`），窗口内的问题就会被算成"窗口外"降级 ⇒ **假 VERIFIED**。现实现 = `_clean_label()` 生成标签时净化 `[`/`]`/换行 + `problem_day()` 按**已知日标签最长前缀匹配** + **头部标签不属于任何已知日时一律 fatal**（不许降级）。回归用例 `tests/test_verify_run3.py::test_bracket_in_day_label_cannot_hide_an_in_window_problem` 与 `::test_unknown_problem_day_label_is_never_demoted`；冻结三副本实测：旧口径 fatal / `7c4ff68` 版本 VERIFIED（洞）/ 修复后 fatal。
- 存档 `Wahaha_450799035` 的 **size 与 mtime 应前进**（对应 SMAPI `SaveGame.Save() called/completed`）。
  **口径按 task-47 定案（`docs/_il-newday-save.md`）更正**：落盘唯一通道是 `SaveGameMenu.update` 的 master 分支；`SaveGameMenu` 只在
  `Game1.showEndOfNightStuff()` 且 **`endOfNightMenus.Count == 0`** 时被创建 ⇒ **当天早晨有日终菜单（`ShippingMenu`＝有货要结算 / `LevelUpMenu` / `Billboard`）时，存档是被设计延后的**。
  因此：**跨日 ≠ 落盘**。豁免**有期限**（2026-10-14 采纳 log-analyst 建议，task-61）：①有日终菜单且**未观测到菜单被关掉** ⇒ 存档未动只记 **info**（设计性延后）；②**已观测到菜单被关掉**（`activeMenu` 变 null，或转 `SaveGameMenu` 后消失）**而其后 1–2 秒内仍无 `SaveGame.Save() called.`** ⇒ 转**待查/异常**（run5 的 25→26 出货那次正属此形态，见 `docs/_il-newday-save.md` §2.5/§4）；③**没有任何日终菜单却缺 `SaveGame.Save() called.` 且存档未动 = 异常**（原样）。
  以「跨日 +1 + 账本一致」为主判据（P3a 每次跨日必有 `Synchronizing 'NewDay' task`；P3b 有 Save 必有 NewDay；P3c NewDay 无 Save：**未观测到菜单被关**记 info，**已关仍无 Save** 记 problem/待查，连续 ≥2 次同样升 problem）。
- SMAPI `Synchronizing 'NewDay'` 计数与账本跨日次数**同向**。
- `finish.code == 0`、`verified_streak >= 3`、0 次 `bridge_down` / `watchdog_stop` / `modal_timeout` / `no_day_progress`。

## 3. 谁验（四路独立，任一路红即不算过）

1. `tools/verify-run3.py`（账本检查器；**只认账本 + 自己复算**，缺字段判问题）。
2. `tools/analyze-longrun.py`（分类/建议；与上者口径差异须在 `docs/_analyze-longrun-*.md` 里说明）。
3. deputy-lead 三源对账器 `scratch/_t45_three_source.py`（账本 / 存档 XML / SMAPI 三源）。
4. Lead 外部快照（`scratch/_run4_snapshot.py --tag start|end`：存档 size+mtime、SMAPI `NewDay`/`SaveGame` 累计、账本行数与 `finish`、PID 存活）。

### 3.1 「LLM 覆盖」口径（Lead 2026-10-14 裁定，源自 log-analyst 在 run2 L17 发现的分歧）

`decision` 行有两个**不同**的计数，四个工具都必须按同一口径报，不许混用：

| 口径 | 判据 | 含义 | run2 实测 | run5 实测 |
| --- | --- | --- | --- | --- |
| `decisions_llm` | `llm == true` | **发起过**模型调用（含被拒/截断） | 7 | 33 |
| `decisions_llm_used` | `llm == true and source == "llm"` | 模型结果**真被采纳** | 6 | 33 |
| 二者之差 | `deterministic_fallback` | 模型答了但没用（截断/拒收后兜底） | 1（L17） | 0 |

- 判据里说"LLM 覆盖"一律指 **`decisions_llm_used`**；`decisions_llm` 只作旁证。
- run2 L17 = `llm=true` + `source=deterministic_fallback` + `fallback=llm_error:truncated` ⇒ **不算模型产出**。
- 两数不等的账本，`tools/verify-run3.py` 会把差额记成 info（不改结论），`tools/analyze-longrun.py` 必须在头部点名该行号。
- **留痕完整性**（task-56）：账本 `decision[].llm_trace` 引用的 `<journal>-llm.jsonl` 必须**真的在盘上**，且文件行数与引用条数一一对应；缺失/行数不符都记 info（复盘材料不全，不影响当天是否达标），`llm_trace_failed` 事件也列进风险信息项。

### 3.2 「三腿覆盖」（P3 ⑥ 的四步里，哪几步在 run6 里真跑过）

`tools/verify-run3.py` 汇总 `leg_ok`（按阶段名归并：**清障/开垦** = `clear_area` + `till_area`、**播种** = `plant_area` + `sow`、**浇水** = `water_area`），某腿全程 0 步成功时记 info。

- **达标日不强制包含播种腿** —— 种子/钱不足时它会合法缺席（钱 14g、种子 20g/包），但 **P3 ⑥ 的整体结必须能指出播种腿的真机证据**，不许"三层过了就说四层过"：
  1. 首选 run6 内出现 `plant_area`/`sow` 的 `ok > 0` 阶段；
  2. 若 run6 全程无种子，则引用既有真机证据（run5 `播种 ok=7`、run2 `播种 ok=1`）+ **一次装机后的单独播种探针**，并在开发日志里写明"run6 只覆盖三腿"。
- 参照数字：run5 = 清障/开垦 **284** / 播种 **7** / 浇水 **172**；run2 = **66 / 1 / 31**。

### 3.3 「窗口全死苗」时 `watered_outdoor` 的证明力（Lead 2026-10-15，源自 deputy-lead task-100 的 NIT-3 结论）

- 形态：窗口口径 `crops > 0` 但**全部是死苗**（`dry_dead > 0`、`dry == 0`）、且 farm 级证据不可用 ⇒ `day_end.checks.watered_outdoor` **仍可能写成 `true`**（字段偏乐观）。
- **该字段此时不具证明力**：这种形态在 task-96 + task-99 之后**必 fail-closed** —— 人（无论室内或农场）在 farm 证据不可用时会拿到「farm 证据不可用」的 `work_reasons`，`sleep_guard` 不放行 `no_work` ⇒ `ended_by=stuck`、`verified=False`、`day_justified=False`；`tools/verify-run3.py` 的窗口闸门只在 `scope=="window" && crops==0` 判红，`crops>0` 不触发，但当天已经因为别的闸门红了 ⇒ **不产生假绿**。
- 因此**不另立卡**；字段级收口（让全死苗时直接写 `false`）列为 0.7.28 可选 NIT（见 `docs/_review-task99.md` NIT-2、`longrun.py:1071/:1085-1093`）。
- 实测出处：`scratch/_t100_b.py` / `scratch/_t100_b_out.txt`（task-100，`4b68e94`）。

## 4. run6 起跑与收口纪律

- 起跑前：`tools/preflight.py --expect 0.7.25 --save-baseline logs/run6-baseline.json` 四项全绿；记「版本四要素」（HEAD / 被测文件 SHA256+mtime / PID+StartTime / 工作树干净）。
- **脱离式启动**（`Start-Process`，不要用托管后台作业——run4 曾在回合边界被连根收掉，见条目 040/041），PID 落 `logs/run6.pid`，只按 PID + 文件轮询。
- 跑完**先别退游戏**，等 Lead live observe 对账。
- 出现 `eventUp=true` ⇒ 立刻停手上报，**不许** dismiss（task-41；SDV 1.6 流浪宠物事件会永久改档）。
