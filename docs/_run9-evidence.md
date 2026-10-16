# run9 证据（task-105）

**状态：run9 已结束 · FAIL（0/5 VERIFIED，尾部窗口 0/3）** ｜ 起跑 `2026-10-16T20:40:40`，`finish` 于 `21:04:17`（t=1417.06，23.62 分钟，436 动作）
**被测版本：0.7.28**（Mod dll + manifest）/ `HEAD 8b1093623889ccaba800d53d2bc51639c38fb5cd`
**写这份文档时游戏仍在跑**（`StardewModdingAPI` 进程 1 个、PID 5512、桥 0.7.28），按 Lead 指令**未退游戏**（他要 live observe）；`--tag end` 快照已在 21:04:52 取完。

判据一律用**观测差分**（`observe?detail=full` 的 `tiles[]`/`clock`）与**外部证据**（存档 size/mtime、SMAPI 窗口）；Mod 回执只作声明，不作证据。

---

## §1 起跑现场与版本四要素

### 1.1 起跑前环境
- `team_task_get task-105` = rev4 / pending / ready（blockedBy `task-102/103/104/106/108/58/59/82/111/112`）⇒ claim `rev4→5`、`in_progress`、owner `machine-runner`。
- 桥：`bridge.json` `{pid 5512, modVersion 0.7.28, port 17890}`；游戏进程 PID 5512；`StardewModdingAPI` 1 个。
- 起跑前存档（= run8 收尾那一档）：`Wahaha_450799035` **3706657 B / 2026-10-15T22:22:57.011**、`SaveGameInfo` 27913 B / `22:22:57.145`、`_old` 3648782 B / `2026-10-14T23:33:11.539`、`SaveGameInfo_old` 27909 B / `23:33:11.542`。

### 1.2 start 快照（`scratch/run9-external-snapshots.jsonl`，`at 2026-10-16T20:40:29`）
原文要点：`save_main {3706657, 2026-10-15T22:22:57.011}`、`save_info {27913, 22:22:57.145}`、`smapi_lines 416 / smapi_newday 0 / smapi_save 1 / smapi_before_save 0 / smapi_save_called 0`、`expected_mod_version "0.7.28" / mod_version_matches true`、`bridge_info {pid 5512, 0.7.28}`。

> ⚠ 口径订正（如实记账）：`run8-snapshot.py` 的 **PID 候选与默认输出文件都硬编码 run8**。start 行因此带 `pid_file …longrun-3day-llm-run8.pid` / `pid 6480 / pid_alive false`（上一轮残留读数，与 run9 无关）；end 快照我是显式传 `--pid-file logs\longrun-3day-llm-run9.pid` 取的。真 PID 文件 = **`logs\longrun-3day-llm-run9.pid`（内容 10348）**。

### 1.3 `--dry-run` 四要素（EXIT=0，四判据全绿）
| 项 | 读数 |
|---|---|
| HEAD | `8b1093623889ccaba800d53d2bc51639c38fb5cd` |
| `brain/agentfarm/longrun.py` | `D597A32FCE5191446B19DE2C1BE67CEE569AC71E80C817366A202AB977E64DDF` @ `2026-10-16T20:27:05.557378` |
| `brain/agentfarm/farmwork.py` | `3D2A9E5AD4B84A7A129BEFD7BA8A8025B481B8DDBE90DB8D95661C0AD85D9F49` @ `2026-10-15T22:48:30.895020` |
| `brain/agentfarm/bridge.py` | `F5D1D90A5FDA7FFA18ACF774132B0151802149F3872B6ED4F888E91067EFE067` @ `2026-10-16T20:37:43.681667` |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `6F9F0A50AEB05760D65190325E0AE398F9AF79495FA93A9C6D3EA052BE14E155` @ `2026-10-16T20:38:02.390870` |
| `mod/AgentFarm.Bridge/manifest.json` | `F728FE53EF7BC6D33FFB8F766C548818787A376644088EAADD869ABD82F1B9A0` @ `2026-10-16T20:37:20.379614` |
| 工作树干净 | `true`（`git_status_short []`） |

起跑器自带 preflight 基线（`logs/longrun-3day-llm-run9-baseline.json`）：`夏13日 tod 820 / Farm[64,15] / 体力 270 / 钱 188 / seeds [] / crops 6 / unwateredCrops 2 / dryCrops 0 / waterLeft 32 / tillableCount 142 / tileCount 400 / tilesTruncated true / worldSeq 24 / 无模态 / worldAdvancing true`；与 Lead 手写的 `logs/run9-baseline.json`（`tod 610`、其余同向）一致。

### 1.4 起跑（脱离式）
```
python tools\start-detached-longrun.py --days 3 --size 5 --max-minutes 150 --max-days 9 \
  --journal logs\longrun-3day-llm-run9.jsonl --expect-version 0.7.28
```
⇒ **PID 10348 / 起跑 2026-10-16T20:40:40**；四要素 sidecar `logs/longrun-3day-llm-run9.version.json`（1453 B、`pid 10348`、`worktree_clean true`）。
**操作员预置：无**（按 Lead 指令刻意不做 —— 让脑自己走"卖盈余 → 次日到账 → 买当季种子 → 播种"，这是 task-55/102 的唯一真机验收机会）。

---

## §2 外部证据：起止快照对照与存档链

| 项 | start（20:40:29） | end（21:04:52） | 差 |
|---|---|---|---|
| `save_main` | 3706657 / `2026-10-15T22:22:57.011` | **3706657 / `2026-10-15T22:22:57.011`** | **无变化** |
| `save_info` | 27913 / `22:22:57.145` | 27913 / `22:22:57.145` | 无变化 |
| `mod_version_matches` | true | true | — |
| `smapi_lines` | 416 | 4865 | +4449 |
| `smapi_newday` | 0 | **4** | +4 |
| `smapi_before_save` | 0 | **0** | 0 |
| `smapi_save_called` | 0 | **0** | 0 |
| `journal_lines` | null（当时未起跑） | 988（last=`finish`） | — |
| `pid_alive` | false（run8 残留读数，见 §1.2） | false（10348 已退出） | — |

- `logs/run9-external-snapshots.jsonl` 现为 **2 行**（start / end）。
- **存档链结论：run9 窗口内一次落盘都没有**。存档主文件与 `SaveGameInfo` 与起跑前逐字节同 size/mtime；`_old` 仍是 run8 时的 `3648782 / 2026-10-14T23:33:11.539`（说明连一次"旧档轮换"都没发生过）。⇒ 这 4 次跨日（13→14→15→16→17）**全部没有持久化**，run9 的进度如果直接退出就会丢。
- 与 run8 对照：run8 是 2 次 NewDay / 1 次落盘；run9 是 **4 次 NewDay / 0 次落盘**（同型病灶加重，详见 §3 与 `docs/_il-newday-save.md` 口径）。

---

## §3 SMAPI 窗口冻结与配对计数

> ⚠️ **作废标注（task-127 追加，结论数字未改）**：**本跑落盘 0/4（4 NewDay / 0 save），按 task-126 与 `docs/_run6-criteria.md` §2 新口径（commit `99eb8e0`：每次跨日必须落盘，`NewDay` 次数 > `Save` 次数即硬问题），run9 不能作为验收依据或 run A 基线；其逐日读数仅作诊断素材。**

- 冻结文件：`logs/run9-smapi-window.txt` = **360153 B / 4865 行 / mtime `2026-10-16 21:04:17.918` / SHA256 `FEE3DF3702BBBB641CC853D8D85AC1879417A47F63110BB153D2D6C474CCB2EC`**（`Copy-Item` 自 `%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt`）。
- 窗口 `20:40:40–21:04:17` 内 **4447 行**。

| 模式 | 次数 | 行号 / 时间 |
|---|---|---|
| `Synchronizing 'NewDay' task` | **4** | L997 `20:44:28`、L1887 `20:49:22`、L3003 `20:55:44`、L4532 `21:04:09` |
| `Context: before save.` | **0** | — |
| `SaveGame.Save() called.` | **0** | — |
| `Synchronizing 'Save' task` | **0** | — |
| `SaveGame.Save() completed without exceptions.` | **0** | — |
| `after save, starting …` | **0** | — |

噪声计数（窗口内）：`ERROR` 0、`Disconnected` 0、`ClosedGame` 0、`Disposing` 0、`soft_oal` 0、`Warping to Farm` **1256**（task-14 逐帧活锁仍在，信息项）。

口径：按 `docs/_il-newday-save.md`，"有 NewDay 无 save" 只记 **INFO**（日终菜单期保存可能被推迟，不判失败、也不当通过）。**但本节事实要写清**：整个 run9 窗口 `before save` / `Save called` 计数为 **0/0**，`Tool` 侧的 4 次 NewDay 一次都没走到保存链。

> 取证限制（如实）：冻结时游戏仍在运行、独占该文件，`Get-FileHash` 对**源文件**报 `being used by another process`（复制本身成功，size/mtime 与源一致）⇒ **源/副本的字节一致性没能校验**；且 21:04:17 之后游戏仍在追加本文件，本窗口只覆盖 run9。

---

## §4 逐日表与两侧判决

### 4.1 五个日报告（`logs/longrun-3day-llm-run9.jsonl`，988 行）

| 游戏日 | ended_by | 跨日 | ok/skip/fail | 阶段数 | 睡前未浇 | 作物 | 钱 | verified | 未通过项 |
|---|---|---|---|---|---|---|---|---|---|
| summer 13 | `stuck` | ✅→14 | 35/0/0 | 9 | 0 | 11 | 88 | **false** | `slept_by_us`、`no_unmet_stages`、`day_justified` |
| summer 14 | `sleep` | ✅→15 | 62/0/0 | 7 | 0 | 38 | 115 | **false** | `day_justified` |
| summer 15 | `sleep` | ✅→16 | 94/0/0 | 13 | 0 | 55 | 17 | **false** | `day_justified` |
| summer 16 | `stuck` | ✅→17 | 108/0/0 | 16 | 0 | 71 | 27 | **false** | `slept_by_us`、`no_unmet_stages`、`day_justified` |
| summer 17 | `slept_without_work` | ❌ `day_after=null` | **0/0/0** | 0 | 0 | 0 | 407 | **false** | `slept_by_us`、`watered_outdoor`、`day_justified` |

逐日 `ended_reason` 原文（节选）：
- summer 13：`stuck:连续 3 轮世界没有任何变化（最后意图：['review']；策略说有进展：False）；守卫仍说还有活：今天早些时候还有 14 格没做完（跨片地，最近的是 [55, 21]）`
- summer 14：`stuck:换过 11 片地都没有目标（守卫仍说还有活：field_se还有地要清/开/种）`（ended_by 仍是 `sleep`）
- summer 15：`stuck:换过 11 片地都没有目标（守卫仍说还有活：今天早些时候还有 8 格没做完（跨片地，最近的是 [71, 21]））`
- summer 16：`stuck:连续 3 轮世界没有任何变化（最后意图：['review']；策略说有进展：False）；守卫仍说还有活：今天早些时候还有 2 格没做完（跨片地，最近的是 [66, 22]）`
- summer 17：`stuck:守卫说还有活（没种子但钱够（407g ≥ 20g），该去买；人不在农场，但 farm 口径还有 73 格干作物（先回去浇））但没有任何作业区拿得出目标`

逐日 per-stage 成功数（`Σ stages[].ok`）：

| 日 | water_area | till_area | plant_area | clear_area | Σ ok |
|---|---|---|---|---|---|
| summer 13 | — | 12 | **10** | 13 | 35 |
| summer 14 | 15 | 24 | **23** | — | 62 |
| summer 15 | 34 | 35 | **16** | 9 | 94 |
| summer 16 | 48 | 22 | **19** | 19 | 108 |
| summer 17 | — | — | — | — | 0（守卫生效、没推进游戏日） |

逐日 `final_water`（farm 口径，0.7.27 起 `dry` 只算活苗）：`dry 0 / tiles 93 · crops 16`、`0 / 113 · 40`、`0 / 142 · 56`、`0 / 162 · 73`、**`dry 63 / 163 · 73`**。`dead_crops` 5 天全 **0**、`dryDeadCrops` 全 **0**。

### 4.2 两侧工具原文（判决必须同向）

**`python tools/verify-run3.py --journal logs/longrun-3day-llm-run9.jsonl --days 3` ⇒ rc=1**（`logs/run9-verify.txt`，56 行）：
- `decision 194 条（LLM 调用 28 条 / 其中模型产出 28 条）`
- `尾部连续 VERIFIED 天数 0 / 要求 3`
- `stuck 日翻篇：2 天 / journal stuck_flush ×2、stuck_flush_skipped ×0（task-73 有界 MAX_STUCK_FLUSH=2；翻篇日必须 verified=false，尾部连续天数必须靠真干活的日子）`
- 问题清单（末 12 行原文）：summer 13 `checks.no_unmet_stages=false（自算有目标阶段 leftover=2 格）`、summer 14/15 `day_end verified=false`、summer 16 `ended_by=stuck（不是我们主动睡过去的）` + `verified=false` + `no_unmet_stages=false`、summer 17 `ended_by=slept_without_work` + `checks.watered_outdoor=false（睡前还有没浇的作物）` + `verified=false`、`journal 里出现 跨日没有推进 ×1`
- **结论：`needs_review`**

**`python tools/analyze-longrun.py --journal logs/longrun-3day-llm-run9.jsonl` ⇒ rc=1**（`logs/run9-analyze.txt`，204 行）关键行：
- `VERIFIED: 0/3 天（day_end 中 verified=true 0 次）`；`步数合计: ok 299 / skipped 0 / failed 0`
- `no_day_progress: 1 次（行 [987]）`（= summer 17 的 `slept_without_work`，是守卫生效的合法路径，不是 cc2988e 修的"睡成功却判没前进"）
- `sleep: 4 次（ok 4 / failed 0）`；`跨日证据 day_after: 2/2 天（ended_by=sleep）`
- 经济：`购买: 9 次（成功 8 / 没成交 1）`；`sell 5 次（成交 5）；surplus_sell 5 次（sold 289 件、below_keep 5 叠）；buy_no_space 0 次；腾格卖出 4 次（why 分布 {'need_slot': 4}）`；`种子经济: 买不到 3 次（没货 0 / 买不起 3）；seed_unavailable_today 3 次`；口径注明 **买不到不是失败**
- 教训库：`复盘 1 次、notes 3 条（108 字；被拒 0、截断 0）；复盘失败 3 次`（错误原文 `llm_error:truncated: 回答被 max_tokens 截断且内容为空（推理占用了约 512 个 token）。请调大 max_tokens（当前上限 512）。`）；`教训库 total 1 条（上限 20；本日新增 1 / 淘汰 0）`
- 死苗/放弃格：`枯死 0 格、其中没浇 0 格；当天认输格 0 格`
- 决策：`194 次（decisions_llm=28，其中模型产出 decisions_llm_used=28，无兜底）`
- `模态: 打断 4 次（信息项）；必须人工介入（红）0 条`
- `窗口: --window 3（尾部连续 VERIFIED 0 天，不足 ⇒ 不启用窗口降级）；窗口内红 84 条；窗口外历史问题 0 条`
- `退出码: 1；有红 84 条（missed:cancel:*、missed:check:{day_justified,no_unmet_stages,slept_by_us,watered_outdoor}、missed:plot_exhausted、missed:stage_exhausted、missed:stage_no_target）；判决权威仍是 tools\verify-run3.py`

**两侧同向：都是 FAIL（0/5 天、尾部窗口 0/3）。**

### 4.3 Lead 独立复核器原文（`python scratch\run9-lead-check.py … --snapshots scratch\run9-external-snapshots.jsonl --smapi logs\run9-smapi-window.txt` ⇒ rc=1，落 `logs/run9-lead-check.txt`）
- `[1] 跨日链`：13→14 ✅、14→15 ✅、15→16 ✅、16→17 ✅、summer 17 `day_after=None`（不计入）⇒ **合计跨日 4 次，恰好 +1 的 4/4**
- `[2] 存档链`：start 与 end 的 `save_main` 均为 `3706657 / 2026-10-15T22:22:57.011`，`mod_version_matches=True`
- `[3] SMAPI 配对`：`行 4865｜ NewDay 4 / before save 0 / Save called 0 / completed 0`；`INFO 有 NewDay(4) 无 save(0) 的缺口：日终菜单期保存可能被推迟（不判失败，也不当通过）`；NewDay 行号 `[997, 1887, 3003, 4532]`
- `[4] 自述 vs 自算`：5 天全部 ✅（`ok_steps` ↔ `Σ stages[].ok`；`failed_steps` ↔ `Σ failed`）
- `[5] 尾部窗口`：summer 15/16/17 全 `verified=False` ⇒ **未达标 ❌**
- `[6] finish: code=1 streak=0 actions=436 minutes=23.62 no_unmet_stages=False`

> 复核器第一次跑（未传 `--snapshots`/`--smapi`）时 [2][3] 报"无法判定"——因为这两个参数默认为空串；补传后如上。**缺失 ≠ 通过**，这里不是缺失，是参数未传。

---

## §5 本版关注项逐条读数（卡面 N1–N5 + Lead 六项）

**卡面 N1–N5 对照表**

| 卡面问 | 结论 | 读数 |
|---|---|---|
| N1 每天都有农场动作？ | ✅ | summer 13–16 `ok_steps` 35/62/94/108 且都推进游戏日；summer 17 `ok=0` 但 `slept_without_work` **没推进游戏日**（`day_after=null`），"`day_after` 推进 ∧ `ok_steps==0` ∧ `verified==true` 三者不同时"成立 |
| N2 经济闭环四步是否都留痕？ | ✅（四步各自成功，**跨日衔接**） | `sell` 5 成交 5 + `surplus_sell sold 289 件`；次日 `day_end.final.money` 88 → 115 → 17 → 27 → **407**；`buy` 9 成交 8（当季 `(O)483 Wheat Seeds` 10g）；`plant_area` ok **10/23/16/19 格** |
| N3 同日 `buy` ≤3？`no_inventory_space` 后是否重试？有 `surplus_sell{why:need_slot}`？ | ✅ | 单日 `buy` 最多 2 次（`attempt 2 / limit 3`）；`buy_no_space` **0 次**；`surplus_sell{why:"need_slot"}` **4 次**（腾格子卖出生效） |
| N4 `day_after` 恰 +1？落盘缺口能否用日终菜单链解释？ | 跨日 ✅ 4/4；落盘 **0/4** | 见 §4.3 `[1]`（4 次跨日全 +1，summer 17 未跨日不计）；落盘按 `docs/_il-newday-save.md` 记 **INFO**（日终菜单期保存可能被推迟，不判失败也不当通过），但存档 start==end ⇒ **本跑全部进度未持久化**，建议独立立项 |
| N5 死苗判据有真机证据？ | **真空未验** | 5 天 `final.dead_crops=0`、`farm.dryDeadCrops=0`、`day_end.gave_up_tiles=[]` ⇒ 全程没有死苗 ⇒ **真空未验：不算通过、也不算失败**（按 `docs/_run6-criteria.md` 死苗口径必须明写） |

**① 经济闭环四步（task-55/102 的唯一真机验收）——四步各自都成功过 ✅，但没有任何一天走完"同日全链"**
- `sell` **5 次成交 5**（`strategy=surplus_materials`、`below_keep 5 叠`、`surplus_sell sold 289 件`）；其中 **4 次 `why=need_slot`**（腾格子）。例：`t=0.25` 出货 slot 8 `(O)771 Fiber`（`freeSlots 0 / slotsNeeded 1`）；`t=84.69` 出货 slot 6 `(O)390 Stone stack 163`。
- **钱次日到账 ✅**：`day_end summer 13 money=88` → `day_start summer 14` 结算后 `415`（+327 = 两叠合计）；`t=228.73` 买 `188→…`（当日链）…… 逐日 `day_end.final.money` = 88 → 115 → 17 → 27 → **407**（summer 17 早晨，前一日 sell 到账）。
- `buy` **9 次、成交 8**：唯一未成交 = 探路 `472`（春季种子）`item_not_sold`（回执带 30 条在售清单）；**成交 8 次全是当季最便宜的 `(O)483 Wheat Seeds` 10g**（t=0.56 `188→88`、t=228.73 `415→315`、t=405.78 `315→215`、t≈+? `117→17`、`127→27` …），`attempt ≤ limit 3`。
- `plant_area` **ok 逐日 10 / 23 / 16 / 19 格**（summer 13–16）⇒ 播种腿成功。
- ⇒ **结论：买到了、种下了、钱也真的到账了**，与 run8 的"卖成功但买不到"相比是决定性进步；但**"同日全链"未达成**（卖出与播种跨日衔接；summer 17 甚至 0 动作）。

**② 每天必须有农场动作（N1：`day_after` 推进 ∧ `ok_steps==0` ∧ `verified==true` 三者绝不同时）——✅ 通过**
- summer 13/14/15/16 的 ok = 35/62/94/108（都 > 0）且都推进了游戏日；summer 17 `ok_steps==0` 但 `slept_without_work` ⇒ **没有推进游戏日**（`day_after=null`），三者未同时成立。
- `stuck_flush` 2 次（task-73 `MAX_STUCK_FLUSH=2` 有界例外）⇒ 有界，未失控。

**③ `no_space` 不再死锁（同日 buy ≤3、`buy_no_space` 有界）——✅ 通过**
- `buy_no_space` **0 次**（run8 是 25 次 `no_inventory_space`）；腾格子卖出 4 次生效（run8 的根因是背包 0 空格）；`cannot_afford` 3 次 + `seed_unavailable_today` 3 次（`note: 今天不再发起 buy（次日重试一次）`）⇒ **当天失效留痕存在**；`buy` 单日最多 2 次（attempt 2 / limit 3）。

**④ LLM 演进留痕——留痕齐全，但 512 token 预算把 3/4 次复盘打废（task-121 `9a4da64` 已修）**
- `decisions_llm=28`、`decisions_llm_used=28`（**无兜底**）、`truncated 0`、`fallback 0`；boundary `new_day 4 / task_kind_change 24 / none 166`。
- `review_llm` **1 次成功**（notes 3 条 / 108 字 / 被拒 0 / 截断 0）；`review_llm_failed` **3 次**，错误原文 = `max_tokens 截断且内容为空（推理占用了约 512 个 token）`。
- 教训库 `logs/longrun-3day-llm-run9-lessons.json` **原文**（与 Lead 预期完全一致，**只有 1 条**）：
```json
{"id": "slept_without_work|day", "kind": "slept_without_work", "scope": "day",
 "symptom": "一天里一次农场动作都没做就想收工（被拦住、没推进游戏日）",
 "evidence": "ended_by=slept_without_work 动作=0", "hint": "", "count": 1,
 "first_day": [1, "summer", 17], "last_day": [1, "summer", 17], "last_seq": 6,
 "severity": 2, "src": "agentfarm"}
```
- 说明：run9 是**旧代码**（512 上限）；本跑只作"run A 只积累"的基线，对照留给 run10。

**⑤ 跨日落盘（NewDay ↔ `SaveGame.Save()` 配对）——0/4，按 INFO 口径不判失败，但事实严重**
- 见 §2/§3：`NewDay 4`、`before save 0`、`Save called 0`、`completed 0`；存档 start==end（`3706657 / 2026-10-15T22:22:57.011`）⇒ **run9 全程未持久化**。
- 按 `docs/_il-newday-save.md` 口径记 INFO（日终菜单期保存可能被推迟，不算失败）；但它比 run8 的 1/2 更差，建议单独立项（task-47/task-104 线）。

**⑥ 本版新闸门有没有假红/假绿——没发现假红/假绿**
- 两侧同向 FAIL；`history_problems` 0（窗口外无历史问题）；`unreachable_within_bound`/`refused_within_bound` 5/5 天全 `true`，账本 `unreachable` 事件仅 2 次、`unreachable_summary` 1 次、`refused_*` 0 次 ⇒ 没有"豁免越界"式假绿；无可达性假红。
- 真空日闸门正常：summer 17 `ok=0` 的日子被 `slept_without_work` 拦住、**没有**被记成 VERIFIED。
- Lead 复核器 `[4] 自述 vs 自算 5/5 ✅` ⇒ 账本 self-report 未洗账。

---

## §6 与 run8 对比

| 维度 | run8（0.7.27，2.39 分钟） | run9（0.7.28，23.62 分钟） |
|---|---|---|
| 日报告 / VERIFIED | 3 / 1 天（尾部 0/3） | 5 / 0 天（尾部 0/3） |
| `sell` | 1 次（Fiber 174） | **5 次**（成交 5、腾格 4） |
| `buy` | **26 次、成交 0**（`no_inventory_space` 25） | **9 次、成交 8**（`no_space` 0） |
| 播种 | 0（`plant_area` 无成功格） | **ok 10/23/16/19 格** |
| 钱 | 14 → 188（一次到账） | 188 → 88 → 115 → 17 → 27 → **407**（多次到账） |
| 早晨被模态挡掉 | 直接连睡到次日（0 农场动作） | **`slept_without_work` 拦住、当天不推进**（task-102 B 生效） |
| 落盘 | 2 次 NewDay / 1 次 save | **4 次 NewDay / 0 次 save** |
| 主拦路判据 | `watered_outdoor`、`no_hard_failures` | **`day_justified` 5/5 天**（＋2 天 `stuck` 的 `slept_by_us`/`no_unmet_stages`） |

---

## §7 保留物 · 不确定项 · 诚实声明

> ⚠️ **作废标注（task-127 追加，结论数字未改）**：**本跑落盘 0/4（4 NewDay / 0 save），按 task-126 与 `docs/_run6-criteria.md` §2 新口径（commit `99eb8e0`：每次跨日必须落盘，`NewDay` 次数 > `Save` 次数即硬问题），run9 不能作为验收依据或 run A 基线；其逐日读数仅作诊断素材。**

### 7.1 保留物（未删改）
`logs/run9-journal-extract.txt`、`logs/run9-smapi-window.txt`、`logs/run9-smapi-counts.txt`、`logs/run9-verify.txt`、`logs/run9-analyze.txt`、`logs/run9-lead-check.txt`、`logs/longrun-3day-llm-run9.jsonl`（988 行）、`.console.log`（310 行 / 41754 B）、`.console.err.log`（**0 B**）、`.version.json`、`-llm.jsonl`、`-lessons.json`、`logs/run9-baseline.json`、`logs/longrun-3day-llm-run9-baseline.json`、`scratch/run9-external-snapshots.jsonl`（2 行）、`scratch/run9-extract.py`、`logs/run9.pid` 不存在（真 PID 文件是 `logs/longrun-3day-llm-run9.pid`）。

### 7.2 不确定项 / 缺失（缺失 ≠ 通过）
1. SMAPI 源文件冻结时被运行中的游戏占用 ⇒ **源/副本字节一致性未校验**（复制成功、size/mtime 一致）。
2. 存档只保留两代 ⇒ 窗口内中间各次 size 不可恢复（本次更极端：**一档都没变**）。
3. 冻结发生在 21:04:17、游戏仍在运行 ⇒ 之后 SMAPI 仍会追加，本窗口只覆盖 run9。
4. `water_far` 14 次（"浇窗口外干作物"）与 task-58/59 相关，本次未逐格判定归属。
5. §5① 的"同日全链"没有实现——run9 的四步是**跨日衔接**，不构成"同一天里卖→买→种→浇"。
6. `day_justified` 是 5/5 天的主拦路项；它的判定细则（哪些理由算"当天正当收工"）以 `docs/_run6-criteria.md` 为准，本跑只如实列出未过。

### 7.3 诚实声明
- 我只做**只读**取证与起止快照；**没有**改源码/Mod/tools/tests、**没有** deploy、**没有**替游戏做选择（`eventUp` 全程 0 命中、无 Dialog/LevelUp/ShopMenu 的选择动作）。
- 一处**订正已如实记账**：end 快照初次被 `run8-snapshot.py` 的默认输出写进了 `scratch/run8-external-snapshots.jsonl`；已由 `scratch/run9-extract.py` 的 `fix_snapshots()` 把 run9 行搬回 `scratch/run9-external-snapshots.jsonl`，并把 run8 那份**原样恢复为 2 行**（内容未改，只去掉误入行）。
- 结论口径：**FAIL（0/5 VERIFIED、尾部窗口 0/3、exit 1）**；两侧工具同向；所有"好消息"（经济闭环四步各自成功、守卫生效、不死锁）与"坏消息"（0 落盘、`day_justified` 5/5 未过、两天 `stuck`）都如实列出，未做取舍性叙述。

---

## §8 下次证据必须包含（run9b / run10 模板，task-127 追加）

下一跑（run9b/run10）的 `docs/_runNN-evidence.md` **必须**含下列八项，缺哪项就在对应位置写【无法判定】——**缺失 ≠ 通过**。

1. **四个 SMAPI 计数逐条配对**：`NewDay`（`Synchronizing 'NewDay' task`）↔ `before save`（`Context: before save.`）↔ `Save called`（`SaveGame.Save() called.`）↔ `completed`（`SaveGame.Save() completed without exceptions.`）。每个计数给**次数 + 行号/时间**，并**逐次**把同一晚跨日的四个计数配成一组；`NewDay` 次数 > `Save` 次数即硬问题（task-126 / `docs/_run6-criteria.md` §2，commit `99eb8e0`）。
2. **两侧工具的 `verdict` 与 `strict_verdict` 两行都抄**：`python tools\verify-run3.py --journal <journal> --days 3`（尾部窗口 verdict）与 `python tools\analyze-longrun.py --journal <journal>`（严格整本 / exit code）；两者必须同向，不同向就列为未决并写清差异条目。
3. **`python scratch\run9-lead-check.py` 原文**，且**必须显式传** `--snapshots <快照文件> --smapi <SMAPI 窗口文件>`（默认是空串，不传只会报"无法判定"）。
4. **教训库原文 + SHA256**：`logs/<journal 词干>-lessons.json` 全文与 `Get-FileHash -Algorithm SHA256` 结果。
5. **`<journal>.version.json` 的四要素**：`head`、`files{五文件 sha256 + mtime}`、`pid` + 起跑时刻、`git_status_short`/`worktree_clean`；另附外部判定"进程 `StartTime` 晚于被测文件 mtime"。
6. **起止快照两行原文**：`python scratch\run9b-snapshot.py --tag start` 与 `--tag end`（PID 候选按 `--journal` 自动推导 `X.jsonl ⇒ X.pid`；`--tag end` 建议显式 `--pid-file <journal>.pid`）；`save_main` 起止 size+mtime 一致 ⇒ 落盘 0，必须点名。
7. **存档四条读数**（`Wahaha_450799035` / `SaveGameInfo` / `_old` / `SaveGameInfo_old` 的 size+mtime）与逐日 `day_after` 链（必须恰 +1）。
8. **每日读数表**：`ended_by`、`verified`、`checks` 全项、`ok/skip/fail`、`final_water`（farm 口径 dry/crops）+ 逐日 `day_start.money`。
