# 0.7.26 发布计划（run7 前置）

> 上一版 0.7.25 的 run6 = **干净快速失败（0/3、0 跨日、37.2s，首个日报告 t=18.5s）**，死因三条：夏季买不到硬编码的 `472`（且守卫死咬"该去买"）、枯死作物 42 格全被围住不可达、**stuck 日不能翻篇**（`no_day_progress` 直接终止整轮）。本版修这三条，然后发 run7。

---

## 1 版本内容（冻结时以实际提交为准）

| 卡 | 内容 | 侧 |
|---|---|---|
| **task-67** | `BuySkill` 回执带**结构化在售清单** `available:[{id,name,price}]`（≤30 条，成功/失败都带）；脑侧按「name 含 Seeds/种子 且 price ≤ money/K(K=10) 的最便宜者」下单，不再硬编码 `472`；买不到 ⇒ journal `no_seed_for_sale` + **当天不再发起 buy**；**守卫里「没种子但钱够 ⇒ 该去买」当天失效**（改记 `seed_unavailable_today`），收工理由诚实（`no_work`/`stuck:`） | Mod + brain |
| **task-68** | 判"走不到"之前先看 4 邻，邻格是可清障类（weed/stone/twig/grass）就先清它、清完重试目标格（每格 ≤4 次开路动作，`open_way`/`_ensure_reachable`）；口径取**单选题③**：`encircled`（四邻连落脚点都没有）**单独成类** —— 不封格、**不进 `unreachable_exempt` 分子**、只单独留痕；`attempted` 分母**不动**（与工具侧对账口径一致）；新增 `frontier_clear`（所有指定目标都不可达时，至少真清一格可达的可清障格，≤20/天，杜绝 run6 那种"19 秒零动作收工"）；**不放宽** `checks.unreachable_within_bound` 的存在性与 `no_unmet_stages` 的防空洞条 | brain |
| **task-73** | **stuck 日有界翻篇**：idle 守卫判 stuck 后不立刻让外层 `no_day_progress` 终止整轮，而是先 `_do_sleep(..., "stuck_flush:…")` 翻到下一天（`MAX_STUCK_FLUSH=2`，**整轮**计数，刻意绕过 `sleep_guard` 并在 journal 写明理由）；三重拒绝（`eventUp` / `SaveMenu` 类模态 / 到顶）都记 `stuck_flush_skipped`；睡不成才照旧终止。**该日 `verified` 仍为 False**（`ended_by=stuck`、`day_justified=False`），绝不许洗成 `no_work`/`night`/`stamina`。附带修掉真 bug：`_last_day_key` 原取睡前快照 ⇒ 翻篇那天 key 停在旧日、外层照样 `no_day_progress` break（翻篇白做） | brain |
| **task-70** | `analyze-longrun` 种子经济三事件（`no_seed_for_sale`/`seed_unavailable_today`/`seed_gate` 同类分开计数）+ `NEW_EVENT_BUCKETS` 桶名→事件名反查修复（此前会**静默丢事件**）+ 口径卡 §3.9 | 工具 |
| **task-71** | `verify-run3` 对抗加固：两套豁免的 `bound` 一律**自算**（账本写 `9999` 不再被采信）、豁免>0 而无坐标 ⇒ problem、同一格同时进两套豁免 ⇒ problem、`attempted` 被抬高 ⇒ 可疑 | 工具 |
| **task-75** | `verify-run3` 接住 task-68 的五个新名字（`encircled`/`encircled_stage`/`encircled_summary`/`frontier_clear`/`clear_neighbor`）：白名单补 `day_end.encircled*`、会话级自算、info 里点名"`stuck` 且 `ok_steps==0` ⇒ 零动作收工" | 工具 |
| **task-76** | `analyze-longrun` 收同样五个新事件（可达性/开路新类，与 `environment:unreachable` 分开计数）+ 漂移测试全绿 | 工具 |

**不在本版**：task-53（农场级待清障/待开垦计数）、task-55（卖余料换种子钱，脑侧自己出货 + 分叠/记账）、task-58/59（LLM 带决策史 / 收工复盘）⇒ 排 0.7.27。

---

## 2 冻结与装机（Lead 独占，链条冻结后一次做完）

1. 写 `tools\_note-0726.txt` —— **首串必须是 `v0.7.26`**（否则 `_bump-mod-version.py` 只告警、保留旧 Version，见条目 045 坑 ①）。
2. `python tools\_bump-mod-version.py 0.7.26 --note-file tools\_note-0726.txt`（`mod\AgentFarm.Bridge\manifest.json`）。
3. 同步 `brain\agentfarm\bridge.py:39 MOD_VERSION_EXPECTED = "0.7.26"`（注释列本版内容）。
4. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ 期望 **0 警告 / 0 错误**，记 dll 字节数。
5. **`git add -A`**（`check-release.py` 把未跟踪 `scratch/*.py` 也算脏）→ 提交（bump 与代码分开提交也行，但树必须干净）。
6. `python tools\check-release.py --expect 0.7.26` ⇒ 六行全绿（版本一致 / dll 不比源码旧 / `py_compile` / 全量单测 / 树干净）。
7. `python tools\deploy-mod.py --no-quit` ⇒ 记 dll/manifest 字节数、`modVersion=0.7.26`、port、读档地点。
8. `python -m agentfarm goto Farm --no-focus`（需 `PYTHONPATH=<repo>\brain`）；确保玩家在户外农场。
9. `python tools\preflight.py --expect 0.7.26 --save-baseline logs\run7-baseline.json` ⇒ 期望 exit 0（"✅ 可以起跑"）；四项：版本 / 已读档 / 户外农场 / 无模态。

**红线**：bump + build + 装机只由 Lead 做；各处只改代码不 bump（v0.7.17"版本号相同内容不同"的教训）。

---

## 3 run7 起跑（machine-runner：task-74）

- 先用起跑器，**不要**用托管后台作业（DSH 会在 agent 回合边界把作业连根收掉 ⇒ run4 13 秒猝死，见条目 040/041）：
  ```
  python tools\start-detached-longrun.py --dry-run --journal logs\longrun-3day-llm-run7.jsonl --expect-version 0.7.26
  python tools\start-detached-longrun.py --journal logs\longrun-3day-llm-run7.jsonl --expect-version 0.7.26
  ```
- 起跑器会：拒绝重复起跑（PID 活着 ⇒ exit 3）、可选 `preflight` 前置（红灯不起跑 ⇒ exit 4）、`DETACHED_PROCESS` 起进程、写 `<journal>.pid` / `.console.log` / `.console.err.log` / `.version.json`（HEAD + 三份 brain 文件 + **Mod dll + manifest** 的 SHA256/mtime + PID + 起跑时刻 + `git status --short`），并在 90 秒内回体检结果。
- 监控：只读轮询三样（PID 存活 / console 尾部 / 账本行数与尾条），出现 `finish` 或 PID 消失立刻报 Lead；**跑完先别退游戏**（Lead 要 live observe 对账）。
- 交付 `docs\_run7-evidence.md`（同 run6 的 5 节结构）。

---

## 4 判据（以 `docs\_run6-criteria.md` 为准，本版新增 4 条关注项）

沿用：禁止 `final.location == "Farm"`；`ended_reason` 以 `no_work` 开头 ⇒ `final_water.dry == 0`；真空日闸门；豁免上界；`day_after` 恰 +1；`checks` 七项；外部证据三项同向（存档 size/mtime、SMAPI `NewDay`/`SaveGame.Save`、`day_after` 链）；`finish.code == 0`；#四路复核。

本版新增关注：
1. `buy` **成功**：钱减少 + 背包多出**当季**种子（在售清单里的 id），且后续 `plant_area`/`sow` 有 ok>0。
2. `no_seed_for_sale` 每天最多 1 次，且**不再**导致 `stuck`（守卫理由当天失效生效）。
3. `clear_dead` 至少有一天 `ok > 0`，`farm.deadCrops` 下降。
4. `unreachable_within_bound` 不再假红；若仍超界，账本必须给出 `encircled`/坐标证据证明是真超界。
5. **零动作收工不再出现**：`stuck` 日的 `frontier_clear` 至少要真清掉一格（`frontier_clear{acted:true}` 或 stage `ok>0`）；工具侧会点名 `stuck` + `ok_steps==0`。
6. **stuck 日翻篇**：出现 `stuck_flush` 时看它是否真的把 `day_after` 推进 +1，且当天 `verified=false`、`day_justified=false`（不许洗白）。
7. 工具侧新闸门必须**不误杀**：`verify-run3` 对 run2/run3/run5/run6 旧账本的判决与 task-71/75 之前**逐字相同**；`analyze-longrun` 六本账本 rc 不变。

---

## 5 与 run6 对比要看什么

- 天数推进：run6 = 0 跨日、同一天重试两次；run7 至少要看到 `day_after` 链推进（最好连续 3 天）。
- 种子腿：run6 = 6 次 `item_not_sold` 全败；run7 = 应看到一次成功 `buy`（夏季种子）。
- 枯死作物腿：run6 = 42 格全不可达、`clear_dead` 0 ok；run7 = 应有开路后清掉的真机证据。
- 守卫诚实性：run6 = `stuck`（守卫说有活但干不了）；run7 = 若仍无活可干，必须走 `no_work` 且 `final_water.dry == 0`。

---

## 6 已知遗留（不阻塞 run7）

- task-42 出货是**整叠**（无"每 id 保留 K"能力）⇒ task-55。
- task-53：农场级"待清障/待开垦格数"缺失 ⇒ 观测窗口盲区（`location.tilesTruncated=true` 常伴随）。
- task-14：逐帧 warp 活锁（`Warping to Farm` 风暴）仍会勾出剧情事件；task-41 已能硬停，但根因未修。
- task-58/59：LLM 带决策史（`recent_decisions`）与收工复盘（night 边界 notes）排 run7 之后。
- 仓库**没有 C# 测试工程** ⇒ Mod 内部数值（跳预算/续跳/在售清单）只能 build + 真机验收。
