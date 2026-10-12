# `tools\verify-run3.py` 的极限（负例 K 系列：它是**账本检查器**，不是**世界校验器**）

- 作者：deputy-lead（应 Lead m00877④）
- v1 2026-10-13 01:0x，工具 `tools\verify-run3.py` @ `bfb8649`（367 行）
- **v2 2026-10-13 01:1x 复测重写**：Lead 已按本文 §6 加固工具（**536 行**，未做 `worldSeq`/live join），本节所有口径、行号、期望表按加固后版本重写；复跑证据见 §8。
- **一句话结论（v2）**：加固后 **K3（`finish` 自述反向）与 K4（浇水两处自述矛盾）已被抓**（exit 1）；但**完全自洽的伪造账本 `review-neg-K` 与"伪造了无活可做理由"的 `review-neg-K2` 仍然 exit 0**。`verify-run3.py` 验的是**这一本账本自己是否自洽**，**不是世界真的推进过 3 天**。防伪造仍必须靠**账本之外的证据**（§5）。

## §0 修订记录（初版 → v2 加固后）

| # | §6 建议 | 落地情况（v2 实测） |
| --- | --- | --- |
| 1 | `finish` 自洽 + 与工具结论同向 | **已加固** `:409-436`（自洽 `:414-418`；同向 `:419-424`；两侧 `days` 不可比只记信息项 `:425-429`）。K3 现 exit 1 |
| 2 | `watered_outdoor` 与 `final_water.dry>0` 互斥 | **已加固** `:338-345`。K4 现 exit 1 |
| 3 | `t` 基本卫生 | **部分**：全局回退 `:240-242` 与当天倒挂 `:336-337` **只记信息项**（Lead 有意：`t` 是 longrun 自己的 `time.time()`，NTP 回拨会误杀真机）；理由注释在 `:226-228` |
| 4 | 跨日 = 恰好 +1 天 | **已加固** `:321-333`（`_day_ordinal` `:114-136` 折绝对日序，季节边界正确；认不出日形状只记信息项 `:326-329`） |
| 5 | 0 步 VERIFIED 记 info | **改为条件放行** `:346-358`：有"无活可做"证据（`excuse` 或 `ended_reason` 以 `no_work`/`night`/`stamina` 开头，注释还列了 `no_intents`/`plot_exhausted`/`policy_fallback`）⇒ info 放行；否则 ⇒ problem |
| 6 | `worldSeq` 采样 | **未做**（Lead 有意：要改脑 + 口径，且 live join 成本高） |

## §1 实验材料（全在 `scratch\`，生成器可复跑）

| 账本 | 构造 | 目的 |
| --- | --- | --- |
| `review-neg-K-forged-consistent.jsonl` | 3 天 `ended_by=sleep`+跨日+`verified=true`+`checks` 七项全 true（含 `watered_outdoor`/`no_unmet_stages`）+`leftover==0`+`failed_steps == Σ stages.failed` | 最大化自洽的伪造 |
| `review-neg-K2-forged-empty.jsonl` | 同上，但每天 `stages=[]`、`ok/skip/fail = 0/0/0`，`ended_reason="night:到点了"` | "没干活也算过？"（且伪造了无活可做理由） |
| `review-neg-K3-forged-finish-lie.jsonl` | K + `finish.code=1, verified_streak=0`（与 3 天全绿自相矛盾） | `finish` 是否被核对（v1 盲区 B1） |
| `review-neg-K4-forged-water-contradiction.jsonl` | K + `final_water.dry=5` 且 `checks.watered_outdoor=true` | 同源字段是否互检（v1 盲区 B4） |
| `review-task11-modal-day.jsonl` | 绿账本末日改 `blocked_modal` + `no_blocking_modal=false` | 反向对照：**真问题**必须被抓（它被抓了） |

生成器：`scratch\_review_neg_gen.py`（mode `forged_consistent`/`forged_empty`/`env_info_item`/…）、`scratch\_mk_k3_k4.py`、`scratch\_mk_task11_modal_day.py`。pwsh 下必须 `$env:PYTHONUTF8="1"`。

**v2 踩到的坑（值得留档）**：加固后我第一次跑矩阵，**除 green 外全部 exit 1** —— 不是工具误报，是**我的假账本自己 `t` 不单调**：`env_fail` 原先 `rows.insert(3, …)` 插到 `sleep` 之后且 `t=600d+300 < sleep 的 600d+500`；`finish` 原先写死 `t=1900.0` 而末日 `day_end.t=7720`。已改为 `env_fail t=600d+100`（decision `600d+5` 之后、sleep 之前）、`finish t=7900`（> `12*600+520`）。**真机 run2 账本零回退报告** ⇒ 该检查对真实数据不是误报（且现已是信息项）。

## §2 读数（v2 定稿）

| 账本 | verify-run3（加固后） | 说明 |
| --- | --- | --- |
| K（自洽伪造） | **exit 0 / VERIFIED** | 3 天全绿、4 阶段、ok=40 ⇒ **仍是已知盲区** |
| K2（0 阶段 0 步） | **exit 0 / VERIFIED** | 信息项 `当天 0 个阶段且自称 VERIFIED，但有"无活可做"证据（night:到点了）⇒ 接受` |
| K3（finish 自述失败） | **exit 1 / needs_review** | problem `finish 自述 code=1（自称未达标）而本工具判定达标（账本自相矛盾）`；info `finish 自述 verified_streak=0 与本工具尾部连续天数 3 不同` |
| K4（浇水自相矛盾） | **exit 1 / needs_review** | 每天一条 `checks.watered_outdoor=true 但 final_water.dry=5（账本自相矛盾）`（×3）+ 因结论翻转而附带的 `finish 自述 code=0（自称达标）而本工具判定未达标（账本自相矛盾）` |
| 反向对照 `review-task11-modal-day` | **exit 1 / needs_review** | `ended_by=blocked_modal`、`verified=false`（真问题照抓） |

`tools\analyze-longrun.py` 交叉：在 K / K4 上四类判定仍 **0 条**（`dry=5` 与 `watered_outdoor=true` 的矛盾它不查）⇒ **两个工具同读一本账本、同源，自洽伪造两边都过**（v1 结论不变）。

**24 本全量矩阵（deputy-lead 独立复跑，`scratch\*.jsonl` + `logs\*.jsonl` 一个不漏）**：
- **exit 0（5 本）**：`scratch\journal-green.jsonl`、`review-neg-G-env-info-item`、`review-neg-I-env-explained`、`review-neg-K-forged-consistent`、`review-neg-K2-forged-empty`。
- **exit 1（12 本核心）**：`review-neg-A/B/C/D/E/F/H/J`、`review-neg-K3`、`review-neg-K4`、`scratch\review-task11-modal-day.jsonl`、真机 `logs\longrun-3day-llm-run2.jsonl`。
- **exit 1（另 7 本，均属预期）**：旧真机 `logs\longrun-3day-llm-run1.jsonl`、`logs\longrun-3day-run1.jsonl`；只有 1 天的 `scratch\_ledger_green.jsonl`/`_ledger_fallback.jsonl`/`_ledger_leftover_verified.jsonl`；旧探针 `scratch\journal-green-bad.jsonl`、`scratch\journal-nochecks.jsonl`。
- ⇒ 与 Lead 的读数**逐本一致**；`exit0=5 / exit1=19`，共 24 本。

## §3 工具**确实**查了的东西（加固后行号 = 536 行版，全部仍是"账本内部一致性"）

1. `ended_by != "sleep"` 即问题（`:257-260`）；`ended_by=="sleep"` 必须有 `event=sleep, ok=true` 证据（`:261-266`）—— **回执不算证据，要求观测里的日期变了**。
2. `checks.watered_outdoor` 缺失或 `false` 即问题（`:267-280`）；窗口 `unwatered_crops`/`crops_watered` 另算（`:281-285`）。
3. 日级 `failed_steps` 与 `Σ day_end.stages[].failed` 交叉核对 + **差额容错**（`:293-315`）：自述比求和还多 ⇒ 问题；自述少但差额**解释不完**（`Σ env_block_count + Σ inconclusive_count` 以外）⇒ 问题；解释得完 ⇒ 信息项（`:308-311`）。
4. `checks.no_hard_failures=false`（`:286-287`）、`day_end verified=false`（`:316-317`）、`sleep_fail>0`（`:318-319`）即问题。
5. **跨日恰好 +1 天**（`:321-333`，按 28 天/季折绝对日序；认不出日形状记信息项）。
6. `checks.watered_outdoor=true` 与 `final_water.dry>0` **不可并存**（`:338-345`）。
7. **0 阶段却自称 VERIFIED**：有"无活可做"证据放行（信息项 `:352-353`），否则问题（`:354-358`）。
8. 阶段后置条件：`checks.no_unmet_stages` 与自算 `leftover` 不一致 ⇒ 问题（`:360-366`）；**自述 `false` 一律问题**（`:370-374`，不信自述）；`leftover_zero_target>0` ⇒ 问题（`:377-381`，task-15 修 A 的守卫）。
9. 异常事件 `bridge_down`/`watchdog_stop`/`modal_timeout`/`no_day_progress` 出现即问题（`:383-392`）。
10. 尾部连续 VERIFIED 天数 ≥ `--days`（`:394-399`），`ok = streak >= target_days and not problems`（`:406-407`、`:438`）。
11. `finish` 自洽（`:413-418`）+ 与本工具结论同向（`:419-424`，两侧 `days` 不可比时降为信息项 `:425-429`；`verified_streak` 不同只记信息项 `:430-434`）；没有 `finish` 也记信息项（`:435-436`）。

⇒ 这些**全是读账本自述**：`verified`/`checks`/`stages`/`failed_steps` 都是 longrun **自己写的**，账本自洽就无从分辨；加固只是把"自己跟自己打架"的花样抓得更全。

## §4 盲区清单（v2 状态）

| # | 盲区 | v2 状态 |
| --- | --- | --- |
| B1 | `finish` 不参与判定 | **已关闭**（`:409-436`；K3 exit 1） |
| B2 | `t` 从不检查 | **有意降级为信息项**（`:240-242`、`:336-337`）：判成问题会误杀真机 |
| B3 | 不与任何 live 观测 join（`final.day`/`money`/`stamina`/`worldSeq` 是否真来自世界） | **开放**（工具只读一份 JSONL） |
| B4 | `final_water` 与 `checks` 不互检 | **已关闭**（`:338-345`；K4 exit 1） |
| B5 | `cross_day` 只判"日期不同" | **已关闭**（`:321-333`） |
| B6 | 0 步整天也能 VERIFIED | **收窄**：必须有"无活可做"证据，否则问题 |
| B7 | 日级 `failed_steps` 的解释项与它同源（都 longrun 写的），可自洽洗账 | **开放**（`:302-311`；仍靠 `leftover`/`no_unmet_stages` 兜） |
| B8 | `analyze-longrun.py` 同源同盲 | **开放**（§2 实测 0 条） |
| B9 | B6 的"无活可做"证据也是**自述**（`ended_reason`/`excuse`/事件码都在同一本账本里）⇒ K2 照样过 | **开放**（K2 exit 0 即实证） |

## §5 那靠什么防（逐条标可执行性）

**A. 账本之外的外部证据（强，必须做）**

1. **存档真的落盘了**：`C:\Users\admin\AppData\Roaming\StardewValley\Saves\Wahaha_450799035\` 下 `Wahaha_450799035` 与 `SaveGameInfo` 的 **mtime/size 前进**（实测 2026/10/11 22:24:19、`3502298`/`25234` B，`_old` 备份 22:07:58）。
   可执行：run3 前后各 `Get-Item` 一次（或用 python `os.stat`），要求 **每个游戏日至少一次 mtime 前进**。❌ 机器生成的账本不会让存档前进。注意：`tools\verify-landing.py` **不查**这项（只查 `hasSaveLoaded`/`onTitleScreen` 等运行时字段）。
2. **SMAPI 日志里的世界级事件**：`C:\Users\admin\AppData\Roaming\StardewValley\ErrorLogs\SMAPI-latest.txt`，每行带 `[HH:mm:ss LEVEL]` 时间戳。实测可用锚点：
   - `[.. TRACE SMAPI] Synchronizing 'NewDay' task...`（本次 22:07:56、22:22:53）—— **每个跨日必须有 1 条**；
   - `[.. TRACE game] SaveGame.Save() called.` / `completed without exceptions.`（22:07:57 / 22:07:58、22:24:19）；
   - `[.. TRACE AgentFarm Bridge] sleep：answerDialogueAction("Sleep_Yes")`（22:07:55 / 22:12:41 / 22:15:42）—— 桥自己打的、时间戳独立。
   可执行：run3 的时间窗（journal 首末事件墙钟 ± 5 min）内**数 `NewDay` 与 `SaveGame.Save()` 条数 ≥ 天数**。⚠️ 强于账本，但仍是"同一台机器上的另一个文件"（能改，只是不再是"顺手伪造"）。
3. **live 再观测对账（建议加进 run3 流程）**：run3 结束后**不要立刻 quit**，用桥 `/observe` 再取一次，把 `day/money/crops/stamina/location` 与最后一条 `day_end.final` 比 —— 世界必须还在那个状态（或已经继续前进）。❌ 需要游戏仍在跑；写进 task-12 步骤即可。

**B. 跨工具交叉（中）**

4. `tools\analyze-longrun.py` 用**独立代码路径**复算事件→类别映射（它能抓 `blocked_modal`、`no_blocking_modal=false`、睡前 100% 体力这类"行为不像人"的线索）。⚠️ 同读一本账本，**对自洽伪造无效**（K/K4 实测 0 条）。
5. **同源警告（必须写进验收单）**：`checks.watered_outdoor`、`final_water`、`verified`、`checks.*`、`ended_reason`/`excuse` 全部由 longrun **自己**写；它们是"过程记录"，**不是独立见证**。任何"用 A 证明 B"的论证只要两端都在同一本 journal 里就不成立。

**C. 机器不可伪造的锚（建议加）**

6. journal 的 `day_start`/`day_end` 里记录 `liveness.worldSeq`（桥观测的单调世界序号）与 `player.money` 等；再要求**跨日时 `worldSeq` 必须显著前进**。⚠️ 需改 brain + 口径；这是"让伪造成本变高"，不是"不可能伪造"。

## §6 对 `verify-run3.py` 的低成本加固建议（只报不改）—— v2 状态

1. ~~`finish` 一致（挡 K3）~~ → **已加固**（§0-1）。
2. ~~浇水互检（挡 K4）~~ → **已加固**（§0-2）。
3. ~~`t` 基本卫生~~ → **部分加固，且有意只作信息项**（§0-3）。
4. ~~跨日 = 恰好 +1 天~~ → **已加固**（§0-4）。
5. ~~0 步 VERIFIED 记 info~~ → **已改为"有证据才放行"**（§0-5）。
6. `worldSeq` 采样 → **未做**（Lead 有意；见 §5-C）。
7. （v2 新增，纯措辞 nit）任何 problem 都会让 `_ok_now()` 为假，从而在 `finish.days == --days` 时**追加**一条 `finish 自述 code=0（自称达标）而本工具判定未达标（账本自相矛盾）`（`:423-424`）—— 一个根因变成两条，且"账本自相矛盾"的措辞指向 finish 而非真因。建议改成"（可能由上面的问题所致）"或降为信息项。**低优先，不影响判定**。

## §7 建议写进 task-12 / 发布清单的验收单（外部证据）

1. run3 开始前记录存档 `Wahaha_450799035` 与 `SaveGameInfo` 的 `mtime/size`；结束后要求 **每个游戏日至少前进一次**。
2. 记录 run3 的墙钟窗口（journal 首末 `t` + 起止时间），在该窗口内 **SMAPI 日志**必须有 `Synchronizing 'NewDay'` × 天数、`SaveGame.Save() completed` × 天数、`AgentFarm Bridge sleep：answerDialogueAction("Sleep_Yes")` × 天数（缺一即当"没真跨日"处理）。
3. run3 结束、quit 前做一次 **live `/observe` 对账**：`day_key/money/crops/stamina/location` 与最后一条 `day_end.final` 相符。
4. 在这三条之外，`verify-run3.py` 的 exit 0 才是"账本自洽"的**必要条件**，不是"跑通了"的充分条件。

## §8 怎么复跑（v2 证据）

```powershell
$env:PYTHONUTF8="1"
$py="C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py scratch\_review_neg_gen.py          # 生成 A–K2 + G/H/I/J
& $py scratch\_mk_k3_k4.py                # K3/K4 从 K 派生
& $py scratch\_mk_task11_modal_day.py     # 反向对照从 green 派生
Get-ChildItem scratch\*.jsonl, logs\*.jsonl | ForEach-Object {
  & $py tools\verify-run3.py --journal $_.FullName; "$($_.Name) exit=$LASTEXITCODE" }
```

期望：§2 的 5 本 exit 0 / 19 本 exit 1，逐本与本文件一致。
