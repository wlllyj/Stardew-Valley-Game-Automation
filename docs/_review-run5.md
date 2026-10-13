# task-45 复核：三源对账器（账本 ↔ SMAPI ↔ 存档）

- 复核人：deputy-lead（**只读**三源；只写 `scratch/` 与本文件；未碰游戏/桥）
- 授权：Lead m02588（"可以，**写**（这正是"独立复算"该有的样子，前面两次都是它抓出 Lead 的口径错）"）
- 口径（本版已按 Lead m02672 纠偏）：**P3 拆成 a/b/c**、P4 放宽为"差 ≤1 天记 info"，见 §2
- 时间：2026-10-13 20:0x–20:2x（run5 正在跑，**中局**）
- 产物：`scratch/_t45_three_source.py`（对账器）、`scratch/_t45_mk_fixtures.py`（夹具生成器）、
  `scratch/_t45_run_matrix.py`（矩阵跑器）、`scratch/_t45_fx/**`（绿夹具 + 6 负例 + 3 正例）、
  每次运行原文 `scratch/_t45_out_*.txt`、矩阵原文 `scratch/_t45_matrix_v6.txt`

## §1 一句话结论

对账器**能判绿也能判红**，且**不因"跑批中局"误判**：自洽三源 ⇒ exit 0；删一天 `day_end` /
SMAPI 少一条 NewDay / 存档 mtime 不动 / 存档天落后 2 天 / **跨日却没有对应 ok `sleep` 事件** /
**连续 2 日 NewDay 无 Save** ⇒ 各自 exit 1 且判红原文互不相同。

真实 run5 中局（20:19 前后）现在是 **GREEN（problem 0 / info 4 / ok 8）**：
3 次已完成的跨日在"账本 sleep 事件 + SMAPI NewDay + 存档落盘"三处都对得上，
第 4 天（summer 1）正在跑 ⇒ 收尾未写按 info 处理。**最终三源表要等 run5 跑完 + `end` 快照落盘后再出。**

> 本版修掉了我自己上一版的两个**假红**（都是我工具的缺陷，不是 run5 的问题）：
> ①窗口快照只有 1 行（`end` 还没写）时把同一行当 start/end ⇒ 误报"窗口内一次都没落盘"；
> ②跑批进行中最后一天当然没有 `day_end` ⇒ 误报"账本被截断"。
> 两条现在都记 info，并各有一本夹具（`pos-G`/`pos-I`）盯着不许再变红。

## §2 判据表（Lead m02672 裁定后的口径）

`scratch/_t45_three_source.py`（`PYTHONUTF8=1`；退出码 0=无 problem / 1=有 problem / 2=用法-IO / 3=账本缺失的预检模式）

| 判据 | 内容 | 判红条件 |
|---|---|---|
| P1 账本日链 | 每天 `day_start.day` → `day_end.day_after`（run5 真实字段；无 `day_after` 时退回 `final.day`）恰好 +1 天 | 缺 `day_end`（收工后）、或自称 `ended_by=sleep` 却不 +1 天 |
| P1b 账本内互证 | 每个"自称睡过去而且 +1 天"的日子，账本里必须有对应的 ok `sleep` 事件（`before.day`/`after.day` 正好是这两天） | 跨日了但找不到 sleep 事件（负例 H） |
| P2 跨日↔NewDay | 账本每次跨日必须能配到**单调**的 `Synchronizing 'NewDay' task...` | NewDay 条数 < 跨日次数 |
| P3a（硬） | 每次跨日都配一条 NewDay | 见 P2 |
| P3b（硬，反方向） | 不许出现 `SaveGame.Save() completed` 却前面 ≤180s 找不到 NewDay | 有 Save 无 NewDay |
| P3c（信息） | NewDay 有、Save 没有 ⇒ **info**（`save_skipped_by_game`，游戏自身跳过保存） | **连续 ≥2 次**跨日都无 Save 才升 problem |
| P4 存档天 | 存档 XML `<year>/<currentSeason>/<dayOfMonth>` 与账本收尾天相比 | 落后 ≥2 天 ⇒ problem（落后 1 天 ⇒ info）；存档比账本新 ≥2 天 ⇒ problem |
| P4' 中局放宽 | 没有 `finish` 时：最后一天缺 `day_end`、或存档比账本收尾新 **1** 天 | 记 info（收尾未写），不判红 |
| P5 出货到账 | 账本有 ok `sell` ⇒ 真值 `money` 必须变多（`logs/run5-baseline.json` vs 账本起跑 money） | 有卖出但 money 没动 |
| P6 窗口 delta | `--snapshots` start/end：主存档 size/mtime 必须前进；SMAPI 行/NewDay/Save 增量 ≥ 跨日次数 | 首尾存档完全没变；或增量不足 |

**为什么 P3 必须拆 a/b/c（Lead 的原始证据，我逐行复核一致）**：20:04:29 那次跨日**游戏根本没调
`SaveGame.Save()`**——`L1435 Synchronizing 'NewDay' task...` → `task complete.` 之后既没有
`Context: before save.` 也没有 `SaveGame.Save() called.`；而 20:03:43 那次是齐全的。
⇒ 旧口径"NewDay 后 180s 内必须有 Save completed"会把这种**游戏自身行为**判成账本问题。

### §2.1 我复核到的 SMAPI 原始行（Lead 指定要抄进来）

第一次跨日（完整落盘，写的是 **spring 25 / money 14**）：

```
L1077 [20:03:43 TRACE SMAPI] Synchronizing 'NewDay' task...
L1078 [20:03:43 TRACE SMAPI] ... task complete.
L1080 [20:03:43 TRACE SMAPI] Context: before save.
L1081 [20:03:43 TRACE game]  SaveGame.Save() called.
L1085 [20:03:45 TRACE game]  SaveGame.Save() completed without exceptions.
L1086 [20:03:45 TRACE SMAPI] Context: after save, starting spring 25 Y1.
```

第二次跨日（**没有** Save）：

```
L1435 [20:04:29 TRACE SMAPI] Synchronizing 'NewDay' task...
L1436 [20:04:29 TRACE SMAPI] ... task complete.
L1437 [20:04:29 TRACE SMAPI] ...(bridge POST worldSeq=179)
（我读到 L1448 全是 observe/health：没有任何 Context: before save. / SaveGame.Save() called.）
```

时间线自洽：20:03:43 那次是 **24→25**（存档落地 spring 25 / money 14），20:04:29 那次是 **25→26**
（**没落盘**，+100g 分红只在内存里）。⇒ 我上一版写的"**存档滞后**"措辞不准确，
正确表述是"**游戏自身跳过了保存**"（task-47 由 log-analyst 挖触发条件）。

## §3 合成夹具矩阵（10 例，全部符合期望；原文 `scratch/_t45_matrix_v6.txt`）

夹具按 run5 **真实账本形状**造：`day_end` 带 `day_after`（无 `cross_day`）、每天配一条 ok `sleep` 事件、
3 天 spring 26→27→28→29、1 笔 ok `sell`、SMAPI 3 组 NewDay/Save、存档 XML(day 29/money 114)、start/end 快照。

| 夹具 | 注入 | exit | 关键读数 |
|---|---|---|---|
| `ok` | 无 | **0** | problem 0 / info 3 / ok 12（跨日三处都对上：sleep 事件行 3/6/9、SMAPI 行 4/10/16、存档一致） |
| `pos-E-save-one-day-behind` | 存档只落后 1 天 | **0** | info：`需人工确认是『save-day=睡前那天』的语义差，还是落盘滞后` |
| `pos-G-one-day-no-save` | 1 次跨日没落盘 | **0** | info：`save_skipped_by_game：1年 spring 28日（行 10 @ 20:40:00） 有 NewDay 但没有 SaveGame.Save() completed（180s 内）…不判 problem` |
| `pos-I-midrun-last-day-open` | 跑批中局（最后一天无 `day_end`、无 `finish`） | **0** | info：`账本还在跑（没有 finish）：最后一天还没有 day_end ⇒ 本次不判红` + `跑批进行中…存档领先 1 天属收尾未写` |
| `neg-A-ledger-cut` | 删第 2 天 `day_end` | **1** | `[1年 spring 27日] 这一天没有 day_end/day_after（账本被截断？行 5）` |
| `neg-B-smapi-short` | SMAPI 少一条 NewDay | **1** | `SMAPI NewDay 只有 2 条，而账本声称跨日 3 次`＋`[1年 spring 29日] 没有可配对的 SMAPI NewDay` |
| `neg-C-no-save` | 全程无 Save + 存档 mtime 不动 | **1** | `save_skipped_by_game：连续 3 次跨日都没有落盘…⇒ 游戏连续多日不落盘`＋`窗口首尾的主存档 size/mtime 完全没变` |
| `neg-D-save-behind` | 存档落后 2 天 | **1** | `存档还停在 1年 spring 27日，账本已到 1年 spring 29日（落后 2 天）⇒ 超出『save-day 语义差 + 游戏跳过保存』能解释的 1 天` |
| `neg-F-two-days-no-save` | 连续 2 次跨日无 Save | **1** | `save_skipped_by_game：连续 2 次跨日都没有落盘（…28日、…29日）` |
| `neg-H-cross-day-without-sleep-event` | day_end 自称 sleep 且 +1 天，但删掉 sleep 事件 | **1** | `[1年 spring 27日] 跨日 +1 但账本里没有对应的 ok sleep 事件（before/after 天对不上，行 6）` |

⇒ 6 个负例的判红原文**互不相同**，说明不是"一条万能规则在响"；3 个正例覆盖两类"合法的落后/未收尾"。

## §4 真实 run5 阅读（中局；只读）

命令：`& $py scratch/_t45_three_source.py`（默认读 live 三源），原文 `scratch/_t45_out_real-live4.txt`。

| 时点 | 账本 | SMAPI | 存档 XML |
|---|---|---|---|
| 20:15:37 | 134 行 / 3 天 / 无 finish | 3759 行 / NewDay 4 / Save-done 3 | spring 28 / money 14（3665473 B @20:14:12） |
| 20:19:0x | **174 行 / 4 天 / 无 finish** | **4410 行 / NewDay 5 / Save-called 4 / Save-done 4** | **summer 1 / money 14（3793288 B @20:16:14.028）** |

- 对账结果：**problem 0 / info 4 / ok 8 ⇒ GREEN**。三条已完成的跨日日链互证：
  `spring 26→27`（sleep 行 86）、`spring 27→28`（sleep 行 115）、`spring 28→summer 1`（sleep 行 144）
  分别对上 SMAPI `L1077 @20:03:43`、`L1435 @20:04:29`、`L2571 @20:12:00`；存档天与账本收尾一致（summer 1）。
  **季节边界也对**（spring 28 → summer 1，按 28 天/季折绝对日序）。
- `save_skipped_by_game`（info，1 条）：`1年 spring 28日（行 1435 @ 20:04:29）` ⇒ 就是上面那次"游戏自身跳过保存"。
- `窗口快照只有 1 行（end 还没写）⇒ 跳过 P6`（info）；`账本里没有成功的 sell 事件 ⇒ 本次没有出货分红要对`（info）。
- **money 链的观察（不是缺陷，是事实陈述）**：20:03:44 那次 Save 写的是 `spring 25 / money 14`；
  20:04:30 的实时快照已是 `spring 26 / money 114` ⇒ **+100g 分红发生在"没落盘"的那次跨日里**。
  run5 账本第 1 天（spring 26）起跑 money 就是 114，随后 1 笔 `buy` 把 114 花到 14（买种子），
  之后的跨日（27/28）都落了盘，所以现在的存档是 `summer 1 / money 14` —— 分红与买种子在**同一个未落盘窗口**里，
  真在这中间崩/被杀，两者会一起回退（不会凭空多钱）。
- 上表"存档落后/领先"的容差与 §2 的 P4/P4' 一致：**中局一律 info**，收工后才是硬判据。

### §4.1 `Warping to Farm` 活锁（run 级证据，task-14）

- Lead 读数：本窗口 **1565 次**，集中在 20:03:58–20:04:02（299 行）与 20:05:54–20:05:59（≈300 行）。
- 我的独立读数（随时间增长）：20:12:33 **1883 次 / 2943 行**；20:15:37 **2197 次 / 3756 行**；
  首命中 `L102 @20:02:29`，末命中 20:12:09；峰值约 **59 次/秒**；≥30 次/秒的突发秒共 32 个
  （20:02:30–34、20:02:46–49、…、20:12:06–09）。
- ⇒ 结论与 Lead 一致：**每跑一次 `goto Farm` 就复现**（run4 的剧情事件就是它勾出来的），
  这条不属于三源对账器的判据，但对 run5 结果的解释力很强（真机时间大部分被它烧掉）。

### §4.2 run 级原始证据（**判据归 `tools/verify-run3.py`，本节只记证据，不下 run 级结论**）

`tools\verify-run3.py --journal logs\longrun-3day-llm-run5.jsonl`（我独立只读复跑；账本 210–235 行、3 个 `day_end`）
与 `scratch\_t45_days.py`（我写的原始 dump）读数：

| 天 | `checks` 里为 false 的项 | `failed_steps` | `final_water` | `ended_reason` |
|---|---|---|---|---|
| spring 26（L88） | `no_hard_failures`、`no_unmet_stages`、`watered_outdoor` | 4（全是 `till_area` 的 `tool_ineffective`：锄完不是 dirt） | `{scope:"farm", tiles:115, crops:37, dry:1}` | `no_work:确实找不到可做的活…` |
| spring 27（L117） | **只有** `watered_outdoor` | 0（44 ok） | `{scope:"farm", tiles:108, crops:36, dry:1}` | 同上 |
| spring 28（L146） | **只有** `watered_outdoor` | 0（39 ok） | `{scope:"farm", tiles:102, crops:36, dry:1}` | 同上 |

- 三天都命中 `tools\verify-run3.py:436-448` 的闸门：`ended_reason` 以 `no_work` 开头，而 `final_water.dry=1`。
- 三天 `checks.crops_watered=true`（窗口口径恒 0）而 `checks.watered_outdoor=false`，`day_justified=true` ⇒ 两个口径分名的价值在此体现。
- 每天**最后一次** `water_area` 阶段都是 `leftover=0`（作业区内确实浇完了），但 farm 口径仍剩 1 格干作物；
  三天每片 `plots[].note` 都写着 `location.tilesTruncated=true`（`location.tiles[]` 只返回离玩家最近的 400 格，
  本机 1400+ 格）⇒ **那 1 格可能在观测窗口之外**（假设，未证实）。
- `goto_farm` 3 条全 `ok=True where=day_start code=ok` ⇒ 人确实被带回农场，问题不在"回没回农场"。

## §5 局限（这个工具**不能**证明什么）

- 它证明的是"**账本自述的跨日**在 SMAPI 与存档上找得到对应、账本内部的 sleep 证据自洽、且确实落了盘"；
  **不能**证明"游戏真的浇过水/真的卖出了作物"（`checks.watered_outdoor` 仍同源自述；经济闭环对
  `tools/verify-run3.py` 也不可见）。
- **P3c 的边界**：连续 ≥2 次无 Save 判红，但"为什么游戏跳过保存"本身还没结论（**task-47** 在挖）。
  如果 task-47 证明"多日不落盘也是游戏正常行为"，这条判据要再放宽（信息项保留）。
- `Synchronizing 'NewDay' task` 在读档时也会出现 ⇒ 条数够 ≠ 玩家真睡了那么多天；要配合 P6（窗口内存档前进）
  与账本 `sleep` 事件的 before/after 一起看。
- SMAPI 解析依赖行格式 `[HH:MM:SS LEVEL SOURCE] msg`（live 文件已实测；跨午夜自动滚动 +1 天）；
  `SMAPI-latest.txt` 会被下一次会话**覆盖**（run3 的证据就是这么丢的）⇒ 必须冻结副本。
- 中局放宽（P4'）会让"跑批中途"的对账宽松；**最终判定必须等 `finish` 落账后重跑**（那时最后一天缺 `day_end`
  或存档领先都会变回 problem）。

## §6 请 Lead 转给 machine-runner（跑完前两件小事）

1. ✅ `scratch/run5-external-snapshots.jsonl` 的 `{"tag":"start",…}` **已写**（20:12:48，1 行）；
   跑完请再补 `{"tag":"end",…}`（同字段：`save_main{exists,size,mtime}`、`smapi_lines`、`smapi_newday`、
   `smapi_save`、`journal_lines`、`pid`）。
2. ⏳ run5 结束时把 SMAPI 日志**冻结**成 `logs/run5-smapi-window.txt`（否则会被下一次会话覆盖）。

这两件齐了，我立刻出**最终三源表**（P1–P6 全绿/全红的逐日行 + 窗口 delta）。

## §7 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"
& $py scratch\_t45_mk_fixtures.py        # 重造夹具（绿 + 6 负例 + 3 正例）
& $py scratch\_t45_run_matrix.py         # 10 例矩阵：打印 exit code / 期望 / 判红原文
$d = "scratch\_t45_fx\ok"                # 换 neg-*/pos-* 即复现红/绿
& $py scratch\_t45_three_source.py --ledger "$d\ledger.jsonl" --smapi "$d\smapi.txt" `
      --save-dir "$d\Saves\Wahaha_450799035" --snapshots "$d\snapshots.jsonl" `
      --baseline "$d\baseline.json" --date 2026-10-13
& $py scratch\_t45_three_source.py       # 真实 run5（live 三源；中局绿=自洽，收工后重跑才是终判）
```

## §8 本版相对上一版的变更（便于 Lead 对账）

1. P3 → **P3a/P3b/P3c**（Lead 纠偏），新增 `save_skipped_by_game` 信息项；`--no-save-lag` 参数删除。
2. P4 → 差 ≤1 天一律 info；新增 P4'（中局放宽：无 `finish` 时最后一天未收尾、存档领先 ≤1 天记 info）。
3. 账本解析改用真实字段 **`day_after`**（`cross_day` 在 run5 账本里根本不存在）+ **sleep 事件账本内互证**（P1b）。
4. 窗口快照只有 1 行 ⇒ info 跳过 P6（不再假红）。
5. 夹具从 6 例扩到 **10 例**（新增 `pos-G`/`pos-I`/`neg-F`/`neg-H`），矩阵跑器 `scratch/_t45_run_matrix.py` 自动比对期望退出码。
