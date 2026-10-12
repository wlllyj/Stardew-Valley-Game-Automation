# `tools\verify-run3.py` 的极限（负例 K 系列：它是**账本检查器**，不是**世界校验器**）

- 作者：deputy-lead（应 Lead m00877④）
- v1 2026-10-13 01:0x，工具 `tools\verify-run3.py` @ `bfb8649`（367 行）
- **v2 2026-10-13 01:1x 复测重写**：Lead 已按本文 §6 加固工具（536 行），口径/行号/期望表按加固后版本重写；复跑证据见 §8。
- **v3 2026-10-13 01:2x（本文档当前版本）**：deputy-lead 按 **task-19 要求 5④**（"没有任何户外快照 ⇒ 如实 False/缺省，禁止默认 true"）新增 **B4b**（`:394-401`）与"没写 `final_water` ⇒ 信息项"（`:403-407`）；新增负例 **R**（window 口径覆盖 0 格却自称 `watered_outdoor=true`）与正对照 **S**（farm 口径覆盖 32 格 ⇒ 仍 exit 0）。**行号均按 603 行版**。后果：**K2 从 exit 0 翻成 exit 1**（它的 `final_water` 正是 window/0 格），矩阵 29 本 ⇒ exit 0 = 6 本 / exit 1 = 23 本（其余读数逐本不变，见 §2/§8）。
- **一句话结论（v3）**：K3（`finish` 自述反向）、K4（浇水两处自述矛盾）、**K2（window 口径 0 覆盖却自称浇过户外水）**已被抓（exit 1）；**完全自洽的伪造账本 `review-neg-K` 仍然 exit 0** —— `verify-run3.py` 验的是**这一本账本自己是否自洽**，**不是世界真的推进过 3 天**。防伪造仍必须靠**账本之外的证据**（§5）。

## §0 修订记录（初版 → v2 加固 → v3）

| # | §6 建议 | 落地情况 |
| --- | --- | --- |
| 1 | `finish` 自洽 + 与工具结论同向 | **已加固** `:478-500`（自洽 `:481-484`；同向 `:486-494`，其中 `code=0` 但已有别的问题 ⇒ 只记信息项 `:488`）。K3 现 exit 1 |
| 2 | `watered_outdoor` 与 `final_water.dry>0` 互斥 | **已加固** `:382-389`。K4 现 exit 1 |
| 3 | `t` 基本卫生 | **部分**：全局回退 `:240-242` 与当天倒挂 `:379-381` **只记信息项**（Lead 有意：`t` 是 longrun 自己的 `time.time()`，NTP 回拨会误杀真机） |
| 4 | 跨日 = 恰好 +1 天 | **已加固** `:365-377`（`_day_ordinal` 折绝对日序，季节边界正确；认不出日形状只记信息项 `:369-373`） |
| 5 | 0 步 VERIFIED 记 info | **改为条件放行** `:412-419`：有"无活可做"证据（`excuse` 或 `ended_reason` 以 `no_work`/`night`/`stamina` 开头）⇒ info 放行；否则 ⇒ problem |
| 6 | `worldSeq` 采样 | **未做**（Lead 有意：要改脑 + 口径，且 live join 成本高） |
| 7 | （v2 nit）"已由上面的问题解释"措辞 | **已修**（Lead `d43e75e`）：`:486-489` 降为信息项，不再一因两报 |
| 8 | （v3 新增）window 口径 0 覆盖不许自称 `watered_outdoor=true` | **已加** `:394-401`（依据 task-19 要求 5④）；`final_water` 整体缺失 ⇒ 只记 info `:403-407`。K2 现 exit 1 |

## §1 实验材料（全在 `scratch\`，生成器可复跑）

| 账本 | 构造 | 目的 |
| --- | --- | --- |
| `review-neg-K-forged-consistent.jsonl` | 3 天 `ended_by=sleep`+跨日+`verified=true`+`checks` 七项全 true（含 `watered_outdoor`/`no_unmet_stages`）+`leftover==0`+`failed_steps == Σ stages.failed` | 最大化自洽的伪造（**仍过**） |
| `review-neg-K2-forged-empty.jsonl` | K 但每天 `stages=[]`、`ok/skip/fail = 0/0/0`，`ended_reason="night:到点了"`，且 `final_water` 是 **window 口径 0 覆盖** | "没干活也算过？" + window 口径（**v3 起被 B4b 抓住**） |
| `review-neg-K3-forged-finish-lie.jsonl` | K + `finish.code=1, verified_streak=0` | `finish` 是否被核对（B1） |
| `review-neg-K4-forged-water-contradiction.jsonl` | K + `final_water.dry=5` 且 `checks.watered_outdoor=true` | 同源字段是否互检（B4） |
| `review-neg-R-t19-window-no-outdoor.jsonl` | 全绿日 + `watered_outdoor=true` + `final_water={location:"FarmHouse", tiles:0, crops:0, dry:0, scope:"window"}` | **task-19 上线前探针**：证据来源为空（当天无任何户外快照）时，"true"能不能白过 |
| `review-neg-S-t19-farm-scope-ok.jsonl` | 全绿日 + `watered_outdoor=true` + `final_water={scope:"farm", tiles:32, crops:32, dry:0}` | 正对照：加固不得误杀合法的一天 |
| `review-task11-modal-day.jsonl` | 绿账本末日改 `blocked_modal` + `no_blocking_modal=false` | 反向对照：**真问题**必须被抓（它被抓了） |

生成器：`scratch\_review_neg_gen.py`（mode `forged_consistent`/`forged_empty`/`env_info_item`/`env_info_cannot_mask`/`t19_window_no_outdoor`/`t19_farm_scope_ok`/`t15_last_round_done`/`t15_earlier_done_last_leftover`）、`scratch\_mk_k3_k4.py`、`scratch\_mk_task11_modal_day.py`、矩阵跑器 `scratch\_review_matrix.py`（`EXPECT0` = 期望 exit 0 集合）。pwsh 下必须 `$env:PYTHONUTF8="1"`。

**v2 踩到的坑（留档）**：加固后我第一次跑矩阵，**除 green 外全部 exit 1** —— 不是工具误报，是**我的假账本自己 `t` 不单调**（`env_fail`/`finish` 的 `t` 小于前面事件）。已修。**真机 run2 账本零回退报告** ⇒ 该检查对真实数据不是误报（且现已是信息项）。

## §2 读数（v3 定稿）

| 账本 | verify-run3（v3） | 说明 |
| --- | --- | --- |
| K（自洽伪造） | **exit 0 / VERIFIED** | 3 天全绿、4 阶段、ok=40 ⇒ **仍是已知盲区**（它的 `final_water.scope="farm"` 有覆盖，B4b 不适用） |
| K2（0 阶段 0 步 + window 口径） | **exit 1 / needs_review**（v3 起被 B4b 抓住） | 每天一条 `checks.watered_outdoor=true 但 final_water.scope=window 且覆盖 0 格…⇒ 该 true 不可采信`；plus 原有 info `当天 0 个阶段且自称 VERIFIED，但有"无活可做"证据…⇒ 接受`。**"自洽伪造仍能过"这条盲区结论由 K 承担**（farm 口径、无矛盾、仍 exit 0） |
| K3（finish 自述失败） | **exit 1** | `finish 自述 code=1（自称未达标）而本工具判定达标（账本自相矛盾）` + info |
| K4（浇水自相矛盾） | **exit 1** | 每天 `watered_outdoor=true 但 final_water.dry=5（账本自相矛盾）` |
| **R（window 0 覆盖却自称 true）** | **exit 1 / needs_review** | 每天一条 B4b 问题（改前 exit 0 ⇒ 这正是 task-19 上线前必须堵的洞） |
| **S（farm 口径 32 格）** | **exit 0 / VERIFIED** | 正对照：加固不误杀 |
| 反向对照 `review-task11-modal-day` | **exit 1** | `ended_by=blocked_modal`、`verified=false`（真问题照抓） |

`tools\analyze-longrun.py` 交叉：K / K4 / R 上四类判定仍 **0 条**（它不查这些矛盾）⇒ **两个工具同读一本账本、同源，自洽伪造两边都过**（结论不变）。

**29 本全量矩阵（deputy-lead 独立复跑，`scratch\*.jsonl` + `logs\*.jsonl` 一个不漏，`scratch\_review_matrix.py`）**：
- **exit 0（6 本）**：`scratch\journal-green.jsonl`、`review-neg-G-env-info-item`、`review-neg-I-env-explained`、`review-neg-K-forged-consistent`、`review-neg-P-t15-last-round-done`、`review-neg-S-t19-farm-scope-ok`。
- **exit 1（23 本）**：`review-neg-A/B/C/D/E/F/H/J/K2/K3/K4/Q/R`、`scratch\review-task11-modal-day.jsonl`、真机 `logs\longrun-3day-llm-run2.jsonl`、`logs\longrun-3day-llm-run1.jsonl`、`logs\longrun-3day-run1.jsonl`、`logs\longrun-rehearsal-0.7.22.jsonl`，以及只有 1 天的 `scratch\_ledger_green.jsonl`/`_ledger_fallback.jsonl`/`_ledger_leftover_verified.jsonl` 与旧探针 `scratch\journal-green-bad.jsonl`、`scratch\journal-nochecks.jsonl`（后 7 本属预期）。
- **v3 相对 v2 的变化只有两处**：①`K2` exit 0 → exit 1（B4b）；②`R` 从不存在 → exit 1。**其余 27 本 problems/exit 逐本不变**（部分账本 `infos` +1/天，来自"`watered_outdoor=true` 但账本没写 `final_water`"的信息项 `:403-407`，不影响结论）。改前/改后逐行对照留档：`scratch\_matrix_before_t19gate.txt`、`scratch\_matrix_after_t19gate.txt`。

## §3 工具**确实**查了的东西（v3 行号 = 603 行版，全部仍是"账本内部一致性"）

1. `ended_by != "sleep"` 即问题（`:301-302`）；`ended_by=="sleep"` 必须有 `event=sleep, ok=true` 证据（`:304-305`）—— **回执不算证据，要求观测里的日期变了**。
2. `checks.watered_outdoor` 缺失或 `false` 即问题（`:315-322`）；窗口 `unwatered_crops`/`crops_watered` 另算（`:323-327`）。
3. 日级 `failed_steps` 与 `Σ day_end.stages[].failed` 交叉核对 + **差额容错**（`:335-359`）：自述比求和还多 ⇒ 问题；自述少但差额**解释不完**（`Σ env_block_count + Σ inconclusive_count` 以外）⇒ 问题；解释得完 ⇒ 信息项；`failed_any > failed` 只记 info。
4. `checks.no_hard_failures=false`（`:328-329`）、`day_end verified=false`（`:360-361`）、`sleep_fail>0`（`:362-363`）即问题。
5. **跨日恰好 +1 天**（`:365-377`，按 28 天/季折绝对日序；认不出日形状记信息项）。
6. `checks.watered_outdoor=true` 与 `final_water.dry>0` **不可并存**（`:382-389`）。
6b. **（v3 新增）**`checks.watered_outdoor=true` 与 `final_water.scope=="window"` 且 `tiles==0` **不可并存**（`:394-401`，依据 task-19 要求 5④）；`watered_outdoor=true` 但整条 `final_water` 缺失 ⇒ 只记 info（`:403-407`）。
7. **0 阶段却自称 VERIFIED**（`:412-419`）：有"无活可做"证据（`excuse`/`ended_reason` 前缀）⇒ 信息项放行（`:413-417`），否则问题（`:418-419`）。
8. 阶段后置条件：`checks.no_unmet_stages` 与自算 `leftover` 不一致 ⇒ 问题（`:423-428`）；**自述 `false` 一律问题**（`:431-435`，不信自述）；`leftover_zero_target>0` ⇒ 问题（`:438-440`，task-15 修 A 的守卫）；同日同阶段种类的"中途遗留被最后一轮遮蔽"只记 info（`:280-296`）。
9. 异常事件 `bridge_down`/`watchdog_stop`/`modal_timeout`/`no_day_progress` 出现即问题（`:427-434` 起的异常事件段）。
10. 尾部连续 VERIFIED 天数 ≥ `--days`（`:451-456`），`ok = streak >= target_days and not problems`（`:467-470`）。
11. `finish` 自洽 + 与本工具结论同向（`:478-500`；两侧 `days` 不可比时降为信息项；`verified_streak` 不同只记信息项；没有 `finish` 也记信息项）。

⇒ 这些**全是读账本自述**：`verified`/`checks`/`stages`/`failed_steps` 都是 longrun **自己写的**，账本自洽就无从分辨；加固只是把"自己跟自己打架"的花样抓得更全（B4b 也属这一类：它抓的是"自称浇过水，却同时写着证据来自 0 格的窗口"）。

## §4 盲区清单（v3 状态）

| # | 盲区 | v3 状态 |
| --- | --- | --- |
| B1 | `finish` 不参与判定 | **已关闭**（K3 exit 1） |
| B2 | `t` 从不检查 | **有意降级为信息项**：判成问题会误杀真机 |
| B3 | 不与任何 live 观测 join（`final.day`/`money`/`stamina`/`worldSeq` 是否真来自世界） | **开放** |
| B4 | `final_water` 与 `checks` 不互检 | **已关闭**（K4 exit 1） |
| B4b | 自称浇过户外水、但证据来源为空（window 口径 0 格） | **已关闭**（R / K2 exit 1）。工具文案已写成可执行建议：`watered_outdoor=true 但 final_water.scope=="window" 且 tiles==0（当天没有任何户外快照）⇒ 该 true 不可采信`。**task-19 落地后这条检查的期望形态（正常的一天）**：`final_water.scope=="farm"` + `tiles>0` + `crops>0` + `dry==0` + `checks.watered_outdoor==true`（farm 口径注明来自 `farm.dryCrops`）；退回窗口口径时 `scope=="window"` **必须** `tiles>0`（否则 `watered_outdoor` 只能为 `false`/缺省）。 |
| B5 | `cross_day` 只判"日期不同" | **已关闭** |
| B6 | 0 步整天也能 VERIFIED | **收窄**：必须有"无活可做"证据，否则问题 |
| B7 | 日级 `failed_steps` 的解释项与它同源，可自洽洗账 | **开放**（仍靠 `leftover`/`no_unmet_stages` 兜） |
| B8 | `analyze-longrun.py` 同源同盲 | **开放**（§2 实测 0 条） |
| B9 | B6 的"无活可做"证据也是**自述** | **开放，但已不能单独骗过**：K2 现在必须先解决 B4b（伪造者把 `scope` 改成 `farm`+覆盖格数即可再骗过 ⇒ 本质仍开放） |
| B10 | （v3 新增）`watered_outdoor` 的**真值来源**本身不可验：`scope="farm"` + `tiles=32` + `dry=0` 也全是自述 | **开放**（B3 的实例；只有 task-19 的单测 + 真机外部证据能兜） |

## §5 那靠什么防（逐条标可执行性）

**A. 账本之外的外部证据（强，必须做）**

1. **存档真的落盘了**：`C:\Users\admin\AppData\Roaming\StardewValley\Saves\Wahaha_450799035\` 下 `Wahaha_450799035` 与 `SaveGameInfo` 的 **mtime/size 前进**（实测 2026/10/11 22:24:19、`3502298`/`25234` B，`_old` 备份 22:07:58）。run3 前后各 `Get-Item` 一次，要求 **每个游戏日至少一次 mtime 前进**。❌ 机器生成的账本不会让存档前进。注意：`tools\verify-landing.py` **不查**这项。
2. **SMAPI 日志里的世界级事件**：`C:\Users\admin\AppData\Roaming\StardewValley\ErrorLogs\SMAPI-latest.txt`，每行带 `[HH:mm:ss LEVEL]`。可用锚点（实测）：`[.. TRACE SMAPI] Synchronizing 'NewDay' task...`（每个跨日 ≥1 条）、`[.. TRACE game] SaveGame.Save() called.` / `completed without exceptions.`、`[.. TRACE AgentFarm Bridge] sleep：answerDialogueAction("Sleep_Yes")`。可执行：run3 时间窗内数 `NewDay` 与 `SaveGame.Save()` 条数 ≥ 天数。⚠️ 仍是同一台机器上的另一个文件。
3. **live 再观测对账**：run3 结束后**不要立刻 quit**，用桥 `/observe` 再取一次，把 `day/money/crops/stamina/location` 与最后一条 `day_end.final` 比。❌ 需要游戏仍在跑；写进 task-12 步骤。

**B. 跨工具交叉（中）**

4. `tools\analyze-longrun.py` 用**独立代码路径**复算事件→类别映射（能抓 `blocked_modal`、`no_blocking_modal=false` 这类"行为不像人"的线索）。⚠️ 同读一本账本，**对自洽伪造无效**。
5. **同源警告（必须写进验收单）**：`checks.watered_outdoor`、`final_water`（含 `scope`/`tiles`/`dry`）、`verified`、`checks.*`、`ended_reason`/`excuse` 全部由 longrun **自己**写；它们是"过程记录"，**不是独立见证**。任何"用 A 证明 B"的论证只要两端都在同一本 journal 里就不成立 —— B4b 只抓"自述与自己写的 `scope` 打架"，**不证明水真的浇过**。task-19 的正确性最终靠它的假世界单测（5 条）+ 真机窗外证据。

**C. 机器不可伪造的锚（建议加）**

6. journal 的 `day_start`/`day_end` 里记录 `liveness.worldSeq`（桥观测的单调世界序号）+ 要求跨日时显著前进。⚠️ 需改 brain + 口径；是"提高伪造成本"，不是"不可能伪造"。

## §6 对 `verify-run3.py` 的低成本加固建议（只报不改）—— v3 状态

1. ~~`finish` 一致（挡 K3）~~ → **已加固**。
2. ~~浇水互检（挡 K4）~~ → **已加固**。
3. ~~`t` 基本卫生~~ → **部分加固，且有意只作信息项**。
4. ~~跨日 = 恰好 +1 天~~ → **已加固**。
5. ~~0 步 VERIFIED 记 info~~ → **已改为"有证据才放行"**。
6. `worldSeq` 采样 → **未做**（Lead 有意；见 §5-C）。
7. ~~措辞 nit（一因两报）~~ → **已修**（`d43e75e`）。
8. **（v3）window 口径 0 覆盖不许 `watered_outdoor=true`** → **已加**（`:394-401`）。**待 Lead 拍板**的一点：这会改 `review-neg-K2` 的基线读数（exit 0 → exit 1）；若要把 K2 保留为"完全过关的伪造样本"，可用 `review-neg-K`（farm 口径）替代它的角色 —— 但我建议**保留这次加固**，因为 K2 原来的过关依赖的正是 task-19 明令禁止的字段组合。

## §7 建议写进 task-12 / 发布清单的验收单（外部证据）

1. run3 开始前记录存档 `Wahaha_450799035` 与 `SaveGameInfo` 的 `mtime/size`；结束后要求 **每个游戏日至少前进一次**。
2. 记录 run3 的墙钟窗口，在该窗口内 **SMAPI 日志**必须有 `Synchronizing 'NewDay'` × 天数、`SaveGame.Save() completed` × 天数、`AgentFarm Bridge sleep：answerDialogueAction("Sleep_Yes")` × 天数（缺一即当"没真跨日"）。
3. run3 结束、quit 前做一次 **live `/observe` 对账**：`day_key/money/crops/stamina/location` 与最后一条 `day_end.final` 相符。
4. 这三条之外，`verify-run3.py` 的 exit 0 只是"账本自洽"的**必要条件**，不是"跑通了"的充分条件。
5. **（v3）** task-19 落地后，除 `checks.watered_outdoor` 外**必须同时看 `final_water.scope`**：`scope="window"` 且覆盖 0 格时该字段不得为 `true`（工具已按此抓，见 B4b）。

## §8 怎么复跑（v3 证据）

```powershell
$env:PYTHONUTF8="1"
$py="C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py scratch\_review_neg_gen.py          # 生成 A–K2 + G/H/I/J/P/Q/R/S
& $py scratch\_mk_k3_k4.py                # K3/K4 从 K 派生
& $py scratch\_mk_task11_modal_day.py     # 反向对照从 green 派生
& $py scratch\_review_matrix.py           # 29 本一把跑完；"--verbose" 追加逐条 problems/infos
```

期望（v3）：**exit 0 = 6 本**（green / G / I / K / P / S），**exit 1 = 23 本**（A/B/C/D/E/F/H/J/K2/K3/K4/Q/R + modal-day + 真机 run2/run1 + 彩排 + 7 本旧料/单日料），逐本与 §2 一致；`scratch\_review_matrix.py` 的 `EXPECT0` 集合需随之更新为上面 6 本（`K2` 移出）。
