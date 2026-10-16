# run9c 独立对抗验收（task-146）

- **对象**：run9c（0.7.30，PID 18484）账本 `logs\longrun-3day-llm-run9c.jsonl`（219949 B / **340 行 / 坏行 0**）、SMAPI 窗口 `logs\run9c-smapi-window.txt`（379854 B / 4878 行）、外部快照 `logs\run9c-external-snapshots.jsonl`、独立观测 `scratch\run9c-observe-*.json`。
- **判定：PASS-WITH-CAVEATS**。工具与账本自洽、三工具 rc=0（我亲跑复现）；但对"连续 3 个游戏日无人工介入地干活"这一目标，**证据链有一处硬缺口**：尾部第 3 天（summer 20）是 22.81 秒 / 0 动作 / **从未到过农场** / **当天无任何独立观测**的"自证真空日"，其 `no_work` 未获独立证实，且与农场当日的未做工容量相左（§2②、§4）。
- **P3 ⑥ 一句话回答**：**不能**仅凭 run9c 判定"连续 3 个游戏日都在农场干活"达成 —— 三天里只有 summer 21/22 有真工作（89/100 步），summer 20 只能算"无人工介入的空转日"；建议再跑一次（run10）收官，或在口径里追加"每个尾部达标日须 ≥1 次农场动作或一张在场观测"再复评。

---

## §1 A 段：范围与读数（原文/亲跑）

### 1.1 提交与工作树
- HEAD `13fa690`（scratch：lead-check 排除插件描述行假阳性 + run9/run7/run9c 三本回归，`scratch/run9-lead-check.py` +20）。
- 相关提交：`aa3ceaf`（0.7.30 冻结：`brain/agentfarm/bridge.py` 18 + `mod/AgentFarm.Bridge/manifest.json` 4 + `scratch/_t139_pre.py` 5035）、`ec436e7`（`tools/verify-run3.py` +30/−3、`tests/test_verify_run3.py` +32）、`13fa690`。
- 工作树（machine-runner 在写）：`A docs/_run9c-evidence.md`、`A scratch/run9c-days.py`、`A scratch/run9c-tools.py`。

### 1.2 三工具（亲跑，rc 均用"不带管道"的方式取）
| 工具 | 命令要点 | rc | 结论 |
|---|---|---|---|
| `tools\verify-run3.py` | `--journal logs\longrun-3day-llm-run9c.jsonl --days 3` | **0** | `VERIFIED`（尾部 3/3）；严格口径 `needs_review`（窗口内 0 + 窗口外历史 4） |
| `scratch\run9-lead-check.py` | `--journal … --snapshots scratch\run9c-external-snapshots.jsonl --smapi logs\run9c-smapi-window.txt --days 3` | **0** | 跨日 5/5 全 +1；SMAPI 5/5/5/5；自述 vs 自算 5/5 ✅ |
| `tools\analyze-longrun.py` | `--journal … --days 3 --window 3` | **0** | 窗口内红 0 条；窗口外历史 11 条；模态打断 2（信息项）；必须人工介入 0；退出码 0 |

原文留档：`scratch\_t146_verify.txt`、`scratch\_t146_leadcheck.txt`、`scratch\_t146_analyze.txt`。

**verify-run3 结论段原文**：
```
结论：VERIFIED
严格口径（整本零问题，仅呈现、不参与退出码）：needs_review（问题共 4 条 = 窗口内 0 + 窗口外历史 4）
  [summer 18] day_end verified=false
  [summer 18] checks.no_unmet_stages=false（…分配内未完成 assigned_undone=3 格）
  [summer 19] checks.watered_outdoor=false（睡前还有没浇的作物）
  [summer 19] day_end verified=false
info: [summer 20] 当天 0 个阶段且自称 VERIFIED，但有"无活可做"证据（no_work:…）⇒ 接受
```

### 1.3 `finish`（L340）
`{"t":1681.55,"code":0,"verified_streak":3,"actions":513,"minutes":28.03,"stages_seen":["clear_area","plant_area","till_area","water_area"],"no_unmet_stages":false,"unmet_days":["1年 summer 18日"],"stuck_flushes":0}`

### 1.4 SMAPI 落盘链（我独立复核 `logs\run9c-smapi-window.txt`）
| 标记 | 计数 | 行号 | 墙钟 |
|---|---|---|---|
| `Synchronizing 'NewDay' task` | **5** | 1252, 2468, 2494, 3611, 4866 | 23:53:54 / 00:01:10 / 00:01:30 / 00:08:27 / 00:16:29 |
| `Context: before save.` | **5** | 1264, 2480, 2497, 3614, 4872 | 23:53:58 / 00:01:13 / 00:01:31 / 00:08:27 / 00:16:44 |
| `SaveGame.Save() called` | **原始 6 → 修正 5** | 16, 1265, 2481, 2498, 3615, 4873 | — |
| `SaveGame.Save() completed without exceptions` | **5** | 1269, 2485, 2502, 3619, 4877 | 23:53:59 / 00:01:13 / 00:01:31 / 00:08:27 / 00:16:44 |
| `Synchronizing 'Save' task` | 5 | 1266, 2482, 2499, 3616, 4874 | — |
| `after save, starting` | 5 | 1270, 2486, 2503, 3620, 4878 | — |

- **L16 是假阳性**：`[23:46:36 INFO SMAPI] AgentFarm Bridge 0.7.30 by AgentFarm | v0.7.30（run9b 复盘：…）` —— 插件描述正文里含字面串 `SaveGame.Save() called.`。排除规则（含 ` by AgentFarm ` / `| v0.` 的行不计）**方向 fail-closed**：真实标记行不含这些子串，误剔只会让计数偏少 ⇒ 该规则够严。
- **5 次 NewDay ⇔ 5 次 before save ⇔ 5 次 Save called ⇔ 5 次 completed**，与账本 5 次跨日（§2①）一一对应。

### 1.5 存档链与外部快照
- `start`（`at=2026-10-16T23:48:12`）：`save_main{size 5766683, mtime 2026-10-16T22:30:13.053}`、`save_info 26933`、`smapi_lines 416`（`newday 0 / before_save 0 / save_called 1 / completed 0`）。
- `end`（`at=2026-10-17T00:16:53`）：`save_main{size 3860602, mtime 2026-10-17T00:16:44.786}`、`save_info 28884`、`smapi_lines 4878`（`newday 5 / before_save 5 / save_called 6 / save_task 5 / completed 5`）。
- **文件只有 start/end 两行** ⇒ 中间三次跨日在快照文件里**没有逐次落痕**（只能靠 SMAPI 行号 + 墙钟，见 1.4）。存档 size 5766683→3860602、mtime 22:30:13→00:16:44 逐次前进（末次 mtime 与 SMAPI `completed` 00:16:44 吻合）。

### 1.6 独立观测清单（`scratch\run9c-observe-*.json`）
| 文件 | captured_at | 说明 |
|---|---|---|
| summer18 | 23:50:15 | 117458 B |
| summer19 | 23:55:45 | — |
| summer19-2 | 00:00:26 | — |
| **summer20** | **（无）** | 窗口 00:00:54–00:01:17 落在 00:00:26 与 00:04:55 两次观测之间 ⇒ **当天无任何独立观测** |
| summer21 | 00:04:55 | `clock.day 21 / timeOfDay 1020 / Farm / money 465 / waterLeft 28`；`farm{loaded,complete,hoeDirt 224,emptyDirt 142,crops 82,ripeCrops 0,deadCrops 0,unwateredCrops 31,dryCrops 25,dryTiles[25]}` |
| summer22 | 00:09:42 | — |
| summer22-2 | 00:16:54 | 9727 B |

---

## §2 B 段：七条逐条判定

### ① tail-3 九项 checks 逐条（抄录 + 自洽复算）— ✅ PASS
| 日 | `verified` | 九项 | ok/skip/fail | stage 数 | assigned_undone | plot_pending | deferred | bounds(basis) |
|---|---|---|---|---|---|---|---|---|
| summer 18（L1→L108） | **False** | 仅 `no_unmet_stages=false` | 116/0/0 | 27 | 3 | 0 | 0 | 23/23 (118) |
| summer 19（L109→L184） | **False** | 仅 `watered_outdoor=false` | 108/2/0 | 11 | 0 | 13 | 3 | 22/22 (112) |
| summer 20（L185→L191） | **True** | **九项全 true** | **0/0/0** | **0** | 0 | 0 | 0 | 5/5 (0) |
| summer 21（L192→L275） | **True** | 九项全 true | 89/4/0 | 7 | 0 | 10 | 10 | 19/19 (95) |
| summer 22（L276→L339） | **True** | 九项全 true | 100/2/0 | 8 | 0 | 3 | 1 | 21/21 (106) |

- 九项键集合每天一致：`slept_by_us / no_blocking_modal / no_hard_failures / unreachable_within_bound / refused_within_bound / no_unmet_stages / crops_watered / watered_outdoor / day_justified`；**`day_end.verified == all(checks.values())` 五天全部自洽**（无缺失键、无多余键）。
- 我的独立复算：`Σ stages[].ok / skip / fail` 与 `day_end.ok_steps / skipped_steps / failed_steps` **5/5 完全一致**（116/0/0、108/2/0、0/0/0、89/4/0、100/2/0）。
- 18/19 两天不达标是**如实**的（18：`plant_area` 因没种子留下 3 格未做、`stage_shortfall_day.unmet=3` L105；19：睡前仍有 1 格干作物 `final_water.dry=1`，体力 10 < 12 收工）。

### ② summer 20「真空日」判定 — ⚠ **CAVEAT-1（决定性）**
事实链（行号全部可查）：
- L185 `day_start`：`location=FarmHouse`、`weather=lightning（雨天）`、`money=465`、`stamina=270`、窗口无农场格。
- L186 `goto_farm{where:day_start} ok=False code=failed [ui_modal]`，`day_end.notes[0]` 原文："**回不去 Farm：去 Farm 失败：[ui_modal] … 当前有菜单/对话/过场打开，无法移动**"。
- L187 `modal_dismissed`：ShippingMenu、`receipt.ok=true`、`dismissPath=ok_clicked`、等 6788ms、`menuGone=true`、`reachedLocation=FarmHouse`。
- L189 `sleep` @t=784.61（`before.timeOfDay=610` 06:10、体力 270/270）⇒ 跨日 20→21。
- L191 `day_end`：`ended_by=sleep`、`ended_reason=no_work:确实找不到可做的活（地里的活干完了、也没法/没必要买种子）`、`verified=True`、`ok_steps=0`、`stages=[]`、**24 个事件里 `decision=0 / outcome=0`**（当天脑侧一次决策周期都没跑）。
- 当日 `final.farm = {loaded:true, complete:true, crops:83, dryCrops:0, dryDeadCrops:0, unwateredCrops:55, hoeDirt:238, deadCrops:0}`；`final.tillable=0`（`counts_scope=window`，人在室内）；`final.seeds=[["483","Wheat Seeds",2]]`。

**判定**：这条尾巴**不能**作为"当日在农场干活 / 当日确有活可做"的验收证据。理由三条：
1. **零动作、零决策、从未到过农场**（L186 失败后没有再试，后续 4 秒就走回床睡掉）；整日 22.81 秒。
2. **"没活可做"是单侧自述**：它的判据来自"室内窗口（tillable=0）+ farm 计数（dry 0 / ripe 0 / dead 0）"，而 **`final.farm` 里没有 `emptyDirt`/`hoeDirt`/`tillable` 这类"未做工容量"来源**（`work_reasons()` 的耕地/清理/播种理由依赖窗口观测）。当天 0 个 stage、0 条决策 ⇒ 没有任何一处独立证据支持"没活"。
3. **唯一可用的旁证方向相反**：紧随其后的独立观测（summer21 @00:04:55 = 10:20，**该日**）显示农场 `hoeDirt=224 / emptyDirt=142 / crops=82 / deadCrops=0 / dryCrops=25`；18/19 两天的窗口 `可锄=200`。⇒ 农场当天带着**未做工容量**（空地/可锄地 + 手上 2 颗 Wheat Seeds + 465g），"地里的活干完了"不成立。
4. 新增解释：day 19 末 `farm.dryCrops=1`、day 20 末 `dryCrops=0` 而当天 0 动作 ⇒ 因为这天下雨（`weather=lightning`）自动浇了作物；"作物都浇好、无熟、无死苗"这部分是**真的**，真空日不是伪造的，但"完全没活"不是。

### ③ 落盘链 — ✅ PASS
- 账本 5 次跨日（L108/L184/L191/L275/L339）⇔ SMAPI **5×NewDay / 5×before save / 5×Save called / 5×Save completed**（§1.4），墙钟 23:53:54→00:16:44 单调前进；末次存档 mtime `2026-10-17T00:16:44.786` 与 SMAPI completed `00:16:44` 吻合。
- L16 假阳性已按 fail-closed 方向排除（§1.4）。
- `modal_dismissed` 2 次（**L111** t=334.64 day 19、**L187** t=768.85 day 20，均 `ShippingMenu` + `ok_clicked` + `menuGone=true`，等 7502ms / 6788ms）都发生在跨日**之后**，且两处 save 链都完整完成（L1264-1269、L2480-2485）⇒ **关模态没有掐断落盘**。

### ④ 经济四腿（sell → 次日到账 → buy → plant）— ✅ PASS（以账本 + 存档链为准）
- **`sell`**：L18（t=171.02，`(O)330 Clay` stack 27、`below_keep=true`、trigger `money=5/seeds=0/emptyDirt=131/seedPrice=20/threshold=100`）、L112（t=334.74，`why=need_slot`、stack 1、trigger `money=545/freeSlots=0`）；`surplus_sell` L19/L113 成对（analyzer：`腾格卖出 2 次（why=need_slot）`）。
- **次日到账**：day 18 末 `final.money=5`（L108）→ 翌日 `buy` 的 `before.money=545`（**L114**，t=334.81）⇒ 540g 由出货在跨日结算到账，且该跨日有 SMAPI 落盘证据（L1264-1269）⇒ 不是内存幻觉。
- **`buy`**：L2（t=0.46，`472` `failed/item_not_sold`，`price_shelf=0/price_cfg=20` ⇒ 只买在售货）、L3（`(O)483` 10 个×10g，钱 205→105，attempt 2/3）、L14（105→5，attempt 3/3）、L114（545→445）、L259（465→365）、L291（365→265）；`(O)483` = Wheat Seeds（当季在售）。
- **`plant`**：农场作物数逐日 `final_water.crops` = 76 → 83 → 83 → 84 → **101**（L108/184/191/275/339），`finish.stages_seen` 含 `plant_area` ⇒ 买到种子后确实种下去了（钱→种子→种植闭环成立）。`buy_no_space` 0 次、`no_space` 0 次（analyzer 同读）。

### ⑤ 有界性 / 无自旋 — ✅ PASS
- 直方图（340 行）**零**：`plot_exhausted_burst`、`review_only_fallback`/`review_only_no_target`、`slept_without_work`、`no_day_progress`、`stuck_flush*`；`finish.stuck_flushes=0`。
- 有剂量上限的事件：`plots_capped` 1、`idle` 2、`stage_no_target` 2（L149 630.71、L317 1635.61）、`stage_exhausted` 3（L150、L318、L326）；`refused_stage`/`refused_summary` 各 3（19 日 2 格、21/22 各 2 格锄不动，均在 `refused_bound` 内）。
- `modal_dismissed` 2 次为 ShippingMenu 必经动作（`ok_clicked` 等价玩家点 OK），**不是缺陷**、也没掐断保存（§2③）。

### ⑥ 反例（我构造，全部只写 `scratch/`）— ✅ 全部 fail-closed
| 反例 | 构造 | 结果 |
|---|---|---|
| 窗口幅度 | 同一本账本 `--days 1/2/3` | `VERIFIED` / 0 problem（24 info） |
| 窗口幅度（对照） | `--days 5` | `needs_review` + 上述 4 条历史问题 ⇒ 达标只成立于"尾部窗口=20/21/22" |
| 截断入窗 | 截到 L275（`_t146_cut21.jsonl`）/ 截到 L191（`_t146_cut20.jsonl`） | 均 `needs_review` + 4 条问题（尾部连续 VERIFIED 数 < N 时不降级） |
| 伪造窗口日 | 把 summer 21 的 `watered_outdoor` 改成 false | `needs_review` 6 条（含该日两条） |
| 脏标签/重名 | 同例把标签改 `summer]21` 或改名 `summer 18` | **仍 `needs_review` 6 条**（无降级、无假 VERIFIED） |
| 自述与九项不自洽 | 把某 `verified=false` 说成 true | 仍 `needs_review`（`checks.watered_outdoor=false` 被抓） |
| 自述改 checks | 把 summer 20 `no_unmet_stages` 伪造成 false 而 `verified=true` | 2 条问题（`与自算不一致` + `no_unmet_stages=false`） |

原始输出：`scratch\_t146_probe_out.txt`、`scratch\_t146_probe2_out.txt`；探针 `scratch\_t146_probe.py`、`scratch\_t146_probe2.py`。

### ⑦ 独立观测覆盖逐日 — ⚠ 一天缺失
18 ✅（23:50:15）、19 ✅（23:55:45、00:00:26 两张）、**20 ❌【无法判定·窗口错过】**、21 ✅（00:04:55）、22 ✅（00:09:42、00:16:54 两张）。**只有 summer 20 无法用外部观测对照**，而它恰好是唯一需要对照的那一天（§2②）。

---

## §3 结论

- **工具侧**：`verify-run3` / `run9-lead-check` / `analyze-longrun` 三具 rc=0 我亲跑复现；账本自洽（`verified == all(checks)`、`Σ stages` == `day_end` 计数）、落盘链 5/5/5/5、反例矩阵全部 fail-closed ⇒ **账本没有被洗白的迹象**。
- **目标侧**：尾部三天 = 2 天真工作（21：89 步；22：100 步）+ 1 天真空日（20：0 步、未到农场、无独立观测）。
- **判定：PASS-WITH-CAVEATS**：
  - **CAVEAT-1（决定性，见 §2②）**：summer 20 不能算"在农场干活的一天"；若 P3 ⑥ 要求"连续 3 个游戏日都在农场干活"，则**证据不足**。
  - **CAVEAT-2**：达标只成立于"尾部窗口 = 20/21/22"；整本严格口径是 `needs_review`（18/19 各一条硬问题）。
  - **CAVEAT-3**：外部快照只有 start/end 两行，中间三次跨日无逐次落痕（SMAPI + 存档 mtime 可替代，但弱于设计意图）。
- **P3 ⑥ 裁决建议**：先按"**不能**"记账；建议 run10 收官（成本 30 分钟），或在 `docs\_run6-criteria.md` 追加"尾部达标日须 ≥1 次农场动作或一张在场观测"，再据此复评 run9c。

---

## §4 发现（NIT / 建议立卡）

| # | 级别 | 发现 | 证据 | 建议 |
|---|---|---|---|---|
| F1 | **material（建议立卡）** | **"回不去农场 + farm 计数为空 ⇒ 0 动作 VERIFIED"** 的 fail-open：`work_reasons()` 对"耕地/清理/播种"没有 farm 级来源（`final.farm` 只有 dry/ripe/dead/hoeDirt/unwateredCrops），窗口在室内时该来源整体消失；`_farm_scope_work` 只给 (dry, ripe)。雨日（作物已被雨浇好）撞上"日初回农场被模态挡住"就会整天 0 动作并 `verified=true` | L185-L191（`decision=0`、`goto_farm ok=false`、`no_work`）、`final.farm` 无 emptyDirt、summer21 观测 `emptyDirt=142/hoeDirt=224` | 二选一：①把 `emptyDirt`/`hoeDirt`（或"farm 未做工容量"）纳入 farm 级工作理由；②加 fail-closed：**人在室内（窗口不可用）且当日 0 次农场快照 ⇒ 不许 `no_work` 收工**。verify-run3 的反真空只认 `reason` 前缀 `no_work`，抓不到这类日，需同步加闸门 |
| F2 | INFO | 外部快照文件只有 start/end 两行，中间三次跨日无逐次落痕 | `logs\run9c-external-snapshots.jsonl`（仅 2 行） | 若要把"逐次落盘"当硬证据，快照写手应在每次跨日后追加一行 |
| F3 | INFO | analyzer 报 `⚠ 47 条 water_far 没有 cause 字段（旧账本形态）` 与实际不符：47/47 条**都有** `cause`，只是成功路径写空串 | `water_far` 事件样本（`cause:""`、`evidence:"该格观测 watered=true"`） | 文案改成"cause 为空（成功路径）"，避免误判为旧账本 |
| F4 | INFO | `modal_dismissed` 顶层没有 `ok`，成败在 `receipt.ok`（消费方需注意形状） | L111/L187 | 归一化或文档化 |
| F5 | INFO（正面） | task-133 的"逐格判据"在真机生效：L349.88 `water_far tile=[44,23] dry_before=75 dry_after=75 ok=true evidence="该格观测 watered=true"` —— 全局 `dryCrops` 没变而该格确实浇上了，旧口径（run9b）会误判 | L~120 区间 water_far 事件 | 无需动作，留作 task-133 修复的实证 |

---

## §5 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"
& $py tools\verify-run3.py --journal logs\longrun-3day-llm-run9c.jsonl --days 3            # rc 0 / VERIFIED
& $py scratch\run9-lead-check.py --journal logs\longrun-3day-llm-run9c.jsonl `
      --snapshots scratch\run9c-external-snapshots.jsonl --smapi logs\run9c-smapi-window.txt --days 3   # rc 0
& $py tools\analyze-longrun.py --journal logs\longrun-3day-llm-run9c.jsonl --days 3 --window 3         # rc 0
# 反例矩阵（只写 scratch/）
& $py scratch\_t146_probe.py ; & $py scratch\_t146_probe2.py
# 逐日事实
& $py scratch\_t146_days.py   # 输出 scratch\_t146_days_out.txt
```

---

## §6 越界与纪律

- 本次只写 `docs\_review-run9c.md`、`scratch\_t146_*.py`/`scratch\_t146_*_out.txt`；未改 `brain/`、`mod/`、`tools/`、`tests/`、`logs/`、`docs\00-开发日志.md`；未跑真机、未装机、未 bump。
- 与 machine-runner 的在制文件（`docs\_run9c-evidence.md`、`scratch\run9c-*.py`）无写冲突。
