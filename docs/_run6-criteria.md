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

## 2. 连续性与外部证据

- **尾部连续 3 天**：`verified == true` 且 `ended_by == "sleep"` 且 `day_after` 比 `day_key` **恰好 +1 天**。
- 存档 `Wahaha_450799035` 的 **size 与 mtime 必须前进**（SMAPI `SaveGame.Save() called/completed` 对应）。
  注意：游戏自身的 `ShippingMenu` 路径会**跳过**当日存档（`docs/_il-newday-save.md`，task-47）——**跳过 ≠ sleep 失败**，以「跨日 +1 + 账本一致」为主，存档不前进取 info（连续 ≥2 天才算问题，见 `docs/_review-run5.md` 的 P3/P4 口径）。
- SMAPI `Synchronizing 'NewDay'` 计数与账本跨日次数**同向**。
- `finish.code == 0`、`verified_streak >= 3`、0 次 `bridge_down` / `watchdog_stop` / `modal_timeout` / `no_day_progress`。

## 3. 谁验（四路独立，任一路红即不算过）

1. `tools/verify-run3.py`（账本检查器；**只认账本 + 自己复算**，缺字段判问题）。
2. `tools/analyze-longrun.py`（分类/建议；与上者口径差异须在 `docs/_analyze-longrun-*.md` 里说明）。
3. deputy-lead 三源对账器 `scratch/_t45_three_source.py`（账本 / 存档 XML / SMAPI 三源）。
4. Lead 外部快照（`scratch/_run4_snapshot.py --tag start|end`：存档 size+mtime、SMAPI `NewDay`/`SaveGame` 累计、账本行数与 `finish`、PID 存活）。

## 4. run6 起跑与收口纪律

- 起跑前：`tools/preflight.py --expect 0.7.25 --save-baseline logs/run6-baseline.json` 四项全绿；记「版本四要素」（HEAD / 被测文件 SHA256+mtime / PID+StartTime / 工作树干净）。
- **脱离式启动**（`Start-Process`，不要用托管后台作业——run4 曾在回合边界被连根收掉，见条目 040/041），PID 落 `logs/run6.pid`，只按 PID + 文件轮询。
- 跑完**先别退游戏**，等 Lead live observe 对账。
- 出现 `eventUp=true` ⇒ 立刻停手上报，**不许** dismiss（task-41；SDV 1.6 流浪宠物事件会永久改档）。
