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
- 防洗白不靠本条：**全格不可达 + 当天 0 成功动作**仍被上面的真空日闸门判红。

**风险事件分级（`tools/verify-run3.py` 已实现，2026-10-14 Lead 补）**：`mod_version_mismatch`（版本与脑侧期望不一致）**升格为问题项** —— 版本不符的账本不能当验收证据。其余十类只记 info：`water_far_unavailable`（farm 说还有干作物却拿不到 `dryTiles` 坐标）、`farm_evidence_unavailable`、`sell_failed`、`zones_failed`、`day_key_resnap_failed`、`bridge_unavailable`、`env_spin_capped`、`budget_exhausted`、`day_cap`、`event_blocked`。

## 2. 连续性与外部证据

- **尾部连续 3 天**：`verified == true` 且 `ended_by == "sleep"` 且 `day_after` 比 `day_key` **恰好 +1 天**。
- 存档 `Wahaha_450799035` 的 **size 与 mtime 应前进**（对应 SMAPI `SaveGame.Save() called/completed`）。
  **口径按 task-47 定案（`docs/_il-newday-save.md`）更正**：落盘唯一通道是 `SaveGameMenu.update` 的 master 分支；`SaveGameMenu` 只在
  `Game1.showEndOfNightStuff()` 且 **`endOfNightMenus.Count == 0`** 时被创建 ⇒ **当天早晨有日终菜单（`ShippingMenu`＝有货要结算 / `LevelUpMenu` / `Billboard`）时，存档是被设计延后的**。
  因此：**跨日 ≠ 落盘**；有日终菜单而"存档未动"**既不能判失败、也不能判通过**（记账本与存档一致 + 三源对账器的 P3c 容差）；**没有任何日终菜单却缺 `SaveGame.Save() called.` 且存档未动 = 异常**。
  以「跨日 +1 + 账本一致」为主判据（P3a 每次跨日必有 `Synchronizing 'NewDay' task`；P3b 有 Save 必有 NewDay；P3c NewDay 无 Save 记 info，连续 ≥2 天才升 problem）。
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

## 4. run6 起跑与收口纪律

- 起跑前：`tools/preflight.py --expect 0.7.25 --save-baseline logs/run6-baseline.json` 四项全绿；记「版本四要素」（HEAD / 被测文件 SHA256+mtime / PID+StartTime / 工作树干净）。
- **脱离式启动**（`Start-Process`，不要用托管后台作业——run4 曾在回合边界被连根收掉，见条目 040/041），PID 落 `logs/run6.pid`，只按 PID + 文件轮询。
- 跑完**先别退游戏**，等 Lead live observe 对账。
- 出现 `eventUp=true` ⇒ 立刻停手上报，**不许** dismiss（task-41；SDV 1.6 流浪宠物事件会永久改档）。
