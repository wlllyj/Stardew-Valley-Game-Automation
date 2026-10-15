# 接续清单 · 2026-10-11 收工时点（明天从这里开始）

> 本文是**收工快照**，只写"明天开工要用的东西"。`docs\_resume-prompt.md` 是 P2 时代的三步恢复法（仍然有效：单测 → `deploy-mod.py` → `run-plot.py`），但它的状态表已过期，以本文为准。
> 目标不变：**P3 ⑥ —— 端到端自主完成「清障 → 开垦 → 播种 → 浇水」，连续 3 个游戏日无人工介入**（判据一律用 `observe?detail=full` 的 `tiles[]`/`inventory[]`/`money` 差分，回执不算证据）。

## 0h. 2026-10-15 深夜 · **run8 两病灶已修完，0.7.28 冻结只剩 task-108 一道门**（最新，与下文冲突以本节为准）

用户节奏：`User said (m12478)`：「准备停下来吧，明天再搞」。goal 已由 Lead `pause`。

- **run8（0.7.27）= 0/3**：summer 11 VERIFIED / summer 12 **0 动作早睡** / summer 13 `sleep_failed`。两病灶：**A 经济闭环空格死锁**（`buy` 26 次 0 成交，其中 25 次回执 `no_inventory_space`；当季筛选本身正确）+ **B 早晨连睡**（上一夜 `ShippingMenu` 把 `goto_farm` 挡成 `ui_modal`，人留 FarmHouse，`_water_far_dry` 仍逐格空转、6 格全进 `given_up` ⇒ 8 秒后 0 农场动作就睡）。证据 `docs/_run8-evidence.md`、开发日志条目 053。
- **0.7.28 内容已交三张 + 验收过一张**（全部已提交、单测全绿）：
  - **task-102** `9b09735`：`no_space` 独立结果码 + 当天 ≤3 + 卖一叠腾格（`surplus_sell{why:"need_slot"}`）+ 买前清模态 + 0 动作不许睡觉（`slept_without_work`）。
  - **task-104** `9b5b592`：`_water_far_dry` 只在人在户外农场时才逐格；场外回不去记 `water_far_skipped{reason:"not_on_farm"}`、**不扣额度、不认输**、收尾点名。
  - **task-106** `6293696`：analyze-longrun 收 4 个新事件（含 `water_far_skipped`/`modal_dismiss_failed`）⇒ 漂移红清零，全量 **618 OK**。
  - **task-103**（deputy 对 task-102 的对抗验收）= **PASS-WITH-NITS，无必修**（`7e2ad95`）；NIT-1（卖货计划如实性/最小损失）与 NIT-3（卖后刷新 obs）已立 **task-109**（0.7.29）。
  - **task-108（deputy 对 task-104 的对抗验收）在制** ⇒ **0.7.28 冻结的最后一道门**；明天先看它的判定。
- **明天第一件事（Lead，照 `docs/_release-0.7.28.md` §2）**：`tools/_note-0728.txt`（已在库、首串 `v0.7.28`）→ `python tools/_bump-mod-version.py 0.7.28 --note-file tools\_note-0728.txt`（⚠️ cp1252 下末句 print 抛 `UnicodeEncodeError` 且退出码 1，但版本已写盘 ⇒ 用 `json.load` 核对）→ `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED="0.7.28"` → `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental`（0/0）→ `git add -A` + 提交 → `python tools\check-release.py --expect 0.7.28`（须全绿）→ `python tools\deploy-mod.py --no-quit` → `python -m agentfarm goto Farm` → `python tools\preflight.py --expect 0.7.28 --save-baseline logs\run9-baseline.json`（四绿）→ 交 **task-105** 给 machine-runner 起 **run9**（`tools/start-detached-longrun.py --journal logs\longrun-3day-llm-run9.jsonl --expect-version 0.7.28`，起跑前 `scratch/run8-snapshot.py --tag start --expected-mod-version 0.7.28`）。
- **run9 现场（存档：夏 13 日 06:00、钱 188g、种子 `[]`、背包满、作物 6 格）**：**不做操作员预置** —— 这正是"卖一叠腾格 → 买当季种子 → 播种"的验收场景（task-105 卡面明写）。判据 = `docs/_run6-criteria.md` §3.4 的 N1–N5（N1 已按 task-103 的口径澄清改成不变量：`day_after` 推进 ∧ `ok_steps==0` ∧ `verified==true` 三者绝不同时）。
- **观察点（诚实边界）**：run8 那"6 格窗外干作物"在 summer 11 曾被浇成功过（当日 `dry=0`）⇒ 大概率可达，属 task-104 修的场外情形；若 run9 再现"真·够不着的活苗"，当天应如实 `gave_up_dry`/不 VERIFIED，**不许洗白**。
- **本轮提交**：`9b09735`(task-102)、`9b5b592`(task-104)、`6293696`(task-106)、`7e2ad95`(task-103 报告)、`beb1112`+`f220c3c`(0.7.28 计划/口径)、`2bf0d8f`/`a23427a`(条目 052)。
- **goal `goal-1ee4cda9-fdd4-4ba0-80cb-0c06902157eb` 已被 Lead pause**（用户要求今天停）⇒ 明天说一句「继续」或在会话 UI 里 resume 即可重新武装自动续跑。

## 0g. 2026-10-15 晚 · **run7 达成「尾部连续 3 个游戏日 VERIFIED」**

用户节奏：`User said (m11078)`：「继续」。

- **run7 已自行结束**（2026-10-14 23:18:29）：`logs/longrun-3day-llm-run7.jsonl` **1230 行**，`finish {code:0, verified_streak:3, target_days:3, actions:683, minutes:25.2, unmet_days:[], stuck_flushes:1}`；尾部 **`summer 7/8/9` 三天全部 `verified=true`**。游戏进程已退出，`bridge.json` 是 run7 残留（**起 run8 前必须重新拉起游戏**）。
- **四腿全部真机跑通**（Python 逐条解析账本）：`clear_area` 94 次/**384 格**、`clear_dead` 6 次/**32 株死苗**、`till_area` 9 次/**38 格**、`plant_area` 4 次/**4 格**、`water_area` 73 次/**44 格**；`t=647.52` 有一次 LLM 决策同时给 `plant_area`+`water_area`（理由："先把种子落地才能进入后续农务循环"、"刚种下的作物默认为未浇水状态…浇透"）。
- **经济闭环仍空**：`sell`/`buy`/`ship` 事件 **0 条**，5 次 `seed_gate` 全 `{seeds:0, money:14}`；4 格播种吃的是背包原有的 `MixedFlowerSeeds`。⇒ 自主"挣钱→买种"没跑过（task-55）。
- **达标口径本次改了（Lead 自己改的，必须知道）**：`tools/verify-run3.py` 提交 `7c4ff68` —— `ok = (尾部连续 N 天 verified) and (窗口内 problems 为空)`；窗口外日子的日级问题降级为 `summary["history_problems"]`（逐条列出、不影响 rc）；`streak < --days` 不降级；全局问题永远 fatal。文档 `docs/_run6-criteria.md` §2。**旧口径 run7 = `needs_review`，新口径 = VERIFIED，差异 9 条**（summer 3/5/6）。
- **窗口外那 9 条**：`summer 3`/`summer 5` 因农场口径还有 1 格干作物（`[12,30]`）**始终 `unreachable`/够不着**而 `stuck:` 收尾；`summer 6` 连续 3 轮世界不变后靠 task-73 `stuck_flush` **自主翻篇**（真机首次生效）。
- **三路独立验收已派**：**task-85**（machine-runner，`docs/_run7-evidence.md`，两侧结论都要写）、**task-86**（deputy-lead，**对抗打穿口径变更** + 问"账本越长是否把系统性缺陷放过去"）、**task-87**（log-analyst，run7 逐日分类 + 与 analyze-longrun 同向性）。
- **task-55 已派 dev-coder**（经济闭环二：卖盈余材料换种子钱，K=10、三条件门闸、`Money +=` 零写入）。其后依次 **task-84**（死苗不浇水，含 Mod 改动）→ **task-83**（田块规整）；三张都动 `longrun.py` ⇒ Lead 逐张放行。
- **0.7.27 发布计划已落盘**：`docs/_release-0.7.27.md`（九步冻结流程 + run8 判据四条关注项 + 与 run7 对比表 + 已知遗留）。若 task-84 掉卡（只剩 brain-only 卡）⇒ **不 bump**，直接以 0.7.26 起 run8。
- **goal 仍 `paused`**：`update_goal resume` 被拒（"模型不能 resume 一个 paused goal"）⇒ **需要用户在会话 UI 里 resume，或说一句「继续」**，自动续跑才会重新武装。
- 今天的提交：`7c4ff68`（口径）、`1b801c1`（NIT-1 先比较再钳）、`1ffe2ca`（§0f）、`aa8c6e1`（条目 050）、`a4b185b`（run7 探针）、`fd1d2c3`（条目 050 更正 + 0.7.27 计划）。

## 0f. 2026-10-14 深夜二段收尾（**最新，与下文冲突以本节为准**）

用户节奏：`User said (m11056)`：「找合适的时机可以先停了，明天再继续」；同夜还有 `User said (m11003)`（三条问题）与 `User said (m11005)`（「记录下来，安排后续修复」）。

- **run7 仍在跑（脱离式，与 DSH 无关，重启 DSH 不会中断）**：`logs/longrun-3day-llm-run7.jsonl`，PID **27308**（存活），游戏 `StardewModdingAPI` PID **19500** 存活、`bridge.json` 在。收尾时已出现 **两个 `day_end`**：
  - `[1,summer,3]` → `ended_by=sleep`、`verified=false`、reason `stuck:换过 11 片地都没有目标（守卫仍说还有活：农场口径还有 1 格干作物，其中 1 格在玩家窗口之外…）` —— **task-73 的"stuck 日翻篇"真机首次生效**（run6 是 19 秒当场收工）。
  - `[1,summer,4]` → `ended_by=sleep`、**`verified=true`**、reason `no_work:确实找不到可做的活（地里的活干完了、也没法/没必要买种子）` —— **P3 ⑥ 的"单个游戏日达标"首次成立**（还差"连续 3 天"，run7 最长 9 天，可能今晚自己跑完）。
- **明天第一件事**：看 run7 是否已 `finish`（`logs/longrun-3day-llm-run7.jsonl` 尾行 + `logs/longrun-3day-llm-run7.pid` 是否还活）⇒ 已结束就 `python tools/stop-game.py` 收掉游戏、`scratch\run6-snapshot.py --tag end` 取外部证据、跑三路复核（`tools/verify-run3.py` / `tools/analyze-longrun.py` / deputy 三源对账器）并写 `docs/_run7-evidence.md`（machine-runner）。
- **用户三条新反馈已立卡（本夜完成）**：`docs/_user-feedback-2026-10-14.md` + 开发日志**条目 049**（提交 `e8f5bde`）：
  - **task-82**：LLM 反馈闭环（决策→结果 join + `<journal>-lessons.json` 跨日教训库 + 次日注入；承接 task-58/59）。诚实边界：是"会话内记忆 + 提示词反馈"，**不是**改权重。
  - **task-83**：固定当家田块 + `next_plant_tiles()` 行优先连续填空 + 同日不跨 zone（治"东一个西一个"）。
  - **task-84**：死苗不再浇水（Mod 拆"活苗 dry/死苗" + `water()` 排除死苗 + `clear_dead` 提到 water 之前）。
  - ⚠ 三张卡都要动 `brain/agentfarm/longrun.py`（83/84 还要 `farmwork.py`）⇒ **必须 Lead 逐张串行放行**，收进 **0.7.27**。
- **Lead 工具侧本夜最后一笔（已提交 `1b801c1`）**：task-81 的 NIT-1 —— `tools/verify-run3.py` 上界基数改为**先比较再钳**（旧写法 `min()` 先钳住，"账本谎报 `bound_basis`"永不触发、说谎不留痕）；新增回归用例 ⇒ `tests.test_verify_run3` **42 OK**、全量 OK。
- **task-81（deputy-lead）= PASS-WITH-NITS**（`docs/_review-task78.md`，提交 `f2b4cdd`）：task-78 四文件哈希/范围/回归/对抗全过，B 段实测 `attempted=564, encircled=539, bound_basis=25 ⇒ bound=5`（旧口径会是 112）⇒ 被围住的格不再抬上界。
- goal `goal-1ee4cda9-fdd4-4ba0-80cb-0c06902157eb` 仍 **paused/disarmed** ⇒ 明天在界面 resume 或对我说「继续」。

## 0e. 2026-10-14 深夜收尾（**与下文冲突以本节为准**）

用户节奏：`User said (m10939)`：「准备收尾我需要重启dsh」⇒ 本回合只做"把状态收干净 + 让真实运行自己跑完"。

- **0.7.26 已冻结并装机**：提交 **`6718429`**（`mod/AgentFarm.Bridge/manifest.json` 0.7.25→**0.7.26** + `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED="0.7.26"`）；`dotnet build -c Release --no-incremental` **0 警 0 错**（dll **172032 B** @22:51、manifest **19887 B**）；`tools/deploy-mod.py --no-quit` ⇒ 0.7.26 装机 + 自动读档 `Wahaha_450799035`（FarmHouse (9,9)）。
- **run7 已脱离式起跑（与 DSH 无关，重启 DSH 不会中断它）**：`python tools/start-detached-longrun.py --journal logs\longrun-3day-llm-run7.jsonl --expect-version 0.7.26` ⇒ 体检通过（存活 True / 账本 12 行 / stderr 0 B）。产物：`logs/longrun-3day-llm-run7.jsonl`（+ `-llm.jsonl` 决策留痕）+ `logs/longrun-3day-llm-run7.{pid,console.log,console.err.log,version.json}`。console 首批已见 `[day] 1年 summer 3日 开始：Farm 体力 270 钱 14g 作物 31（未浇 31）` 与一串 `· 浇窗口外干作物 [x,y]：ok`（**task-50 的 Mod `farm.dryTiles` + 脑侧走过去浇在真机首次生效**）。
- 起跑基线：`tools\preflight.py --expect 0.7.26 --save-baseline logs\run7-baseline.json` ⇒ **✅ 可以起跑**（`day [1,summer,3] 06:20`、`Farm (64,15)`、体力 270、**钱 14g**、`seeds []`、`crops 31`、`tillableCount 147`、无模态、`worldAdvancing true`）。
- ⚠ **run7 是无种起跑（预期）**：昨晚预置的 956g 没能落盘（`ShippingMenu` 日终菜单把保存推迟、重开游戏回到钱 14g）⇒ 播种腿今晚大概率仍空转，`buy` 会走 task-67 的新路径（货架清单 → 挑当季种子 → 14g 买不起则记 `cannot_afford`，且**当天不再重试、不再判 stuck**）。这本身是 run7 要验的诚实性。
- **收尾时未做（明天补）**：`tools/check-release.py --expect 0.7.26` 没跑（冻结时工作树还有 deputy 的未跟踪 `scratch/_t72_tool_fix.py`/`_t81_probe.py`）⇒ 明天先 `git add -A` + `check-release --expect 0.7.26`。
- **明天开工顺序**：①读 `docs/_review-task78.md`（task-81，deputy-lead 在本回合收尾时仍在跑，完成与否看板面）；②`tools/verify-run3.py --journal logs\longrun-3day-llm-run7.jsonl` + `tools/analyze-longrun.py` + deputy 三源对账器三路复核 run7，并用 `scratch\run6-snapshot.py` 取外部证据；③按 run7 结果立卡（预期仍是"播种腿/经济闭环"与"窗口盲区"家族）；④goal 是 **paused/disarmed**，要在界面里 resume 才能自动续跑。

## 0d. 2026-10-14 收工（**最新，与下文冲突以本节为准**）

用户节奏：`User said (m10163)`：「完成现有的任务后，跑一次真实的游戏运行，然后结束今天的事情，总结整理今天的进展，明天再继续」⇒ **今天到此为止，明天继续**。

- **状态（收工实测）**：Mod **0.7.25 已冻结并装机**（`manifest.json` 0.7.25 + `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED="0.7.25"`，dll 170496 B / manifest 18426 B）；**游戏已优雅退出**（`tools/stop-game.py`，原 pids=[27276]）、`bridge.json` 已删、17890 无监听；存档 `Wahaha_450799035` 最后一次落盘 = summer 2（20:22:58）——summer 3 的落盘被日终菜单推迟，`dismiss_modal` 关掉 `ShippingMenu` 后仍未落盘（task-47 的 U2 未定项，`docs/_il-newday-save.md`）。
- **今天的真实运行 = run6**（`logs/longrun-3day-llm-run6.jsonl`，21:41:21 起跑、**37.2 秒**、exit 1、**0/3 天**）：summer 4 两轮都 `ended_by=stuck`（连续 3 轮世界无变化）、`verified=false`。证据 = `docs/_run6-evidence.md`（含 42 格坐标）。三个真缺陷 ⇒ 明天的活：
  1. **采购硬编码春季种子 472** ⇒ 夏季 SeedShop 无货，`buy` 6 次全 `item_not_sold`（货架是 Melon/Tomato/Blueberry/Pepper/Wheat/Radish/Poppy/Spangle）⇒ **task-67**（dev-coder，今天在制并收尾）：按季/按在售清单选种；缺种子诚实记 `no_seed_for_sale` / `seed_unavailable_today`。
  2. **枯死作物全被杂物包围**：`clear_dead` 0 成功、42 格「四邻都站不过去」> bound 8 ⇒ `checks.unreachable_within_bound=false` ⇒ **task-68**（`blocked_by task-67`）：planner 死锁守卫 + 前沿优先/先清四邻，不许一回合 0 动作。
  3. **守卫死锁指纹**：`idle{rounds:3}` + `stage_exhausted{clear_dead,leftover:30,doomed:30}` + 唯一阶段 ok 全 0 ⇒ 口径已落 `docs/_analyze-longrun-caliber.md` §3.8（**task-69 已 completed**，`13f5a16`，全量 459 OK）。
- **今晚落盘**：`docs/_run6-criteria.md`（判据）、`docs/_release-0.7.26.md`（下一版清单：task-67/68 + 收尾项）、`docs/00-开发日志.md` 条目 047；提交 `d290509`（**verify-run3 同日重试按会话计数**，修掉 run6 上假"不可达不一致" + 2 条回归用例）、`735f4e4`（条目 047）、`9cc4f3c`（0.7.26 发布文档）、`ffda30a`/`fcf0116`（run6 证据）、`13f5a16`（task-69）。
- **队友与板面（22:05 定稿）**：**task-67 已完成并提交 `2f4d03f`**（6 文件 +580/−20；`dotnet build --no-incremental` 0 警 0 错；全量 **Ran 473 tests / 唯一红 = `TestEventMappingDrift`（归 task-70）**；工作树只剩 `?? scratch/_t54_*.py`、`?? scratch/_t67_*.py`、`?? docs/_review-task50-52.md` 等未跟踪件）；**task-54 已完成**：task-50 **PASS** / task-51 **PASS** / task-52 **PASS-WITH-NITS** / task-63 **PASS**（`docs/_review-task50-52.md`，四卡 39 用例 OK + 自写变异全部红在预期用例）；dev-coder 已停手；deputy-lead 已收工；log-analyst / machine-runner 待命（明天开派）。
- **明天新增两张卡（Lead 侧，均 ready、无依赖）**：
  - **task-71**（Lead 自己改 `tools/verify-run3.py` + `tests/test_verify_run3.py`）：task-54 打穿的**三条洗白通道** —— ①豁免上界必须**自算**（`max(5, floor(0.2×attempted))`），账本写 `9999` 这类不一致 ⇒ problem；②`exempt > 0` 但没写逐格坐标 ⇒ **problem**（现在只落 info，卡面 ⑥ 要求判问题）；③同一坐标同时进 `unreachable_tiles` 与 `refused_tiles` ⇒ problem。附 ≥3 条负例 + 六本账本判决不变的回归。
  - **task-72**（deputy-lead，docs-only）：把三条打穿 + 「真失败改分类在账本层不可判」这个开放盲区 + **run6 归因更正**（`unreachable_within_bound=false` **不是**"合法豁免被上界卡住"：42 格全 `field_ne`、每 kind 最后一条 leftover 合计 54 格 vs bound 8 ⇒ 如实判红，根因是作业区选择把一天花在无落脚点簇上）写进 `docs/_verify-run3-limits.md`。
- **task-70**（log-analyst）= analyze-longrun 收 `no_seed_for_sale`/`seed_unavailable_today`（可能还有 `cannot_afford`）三个新桶，依赖已满足 ⇒ **它就是当前全量唯一红**，冻 0.7.26 前必须绿。
- **明天开工 30 分钟版**：
  1. `git status --short` + `python -m unittest discover -s tests`（今天收工读数：**Ran 473 / 1 红** = `test_analyze_longrun.TestEventMappingDrift.test_event_buckets_cover_every_brain_journal_name`，归属 task-70；把三个新桶补上后应回到全绿）。
  2. 收 task-67（**已完成 `2f4d03f`**）→ 派 task-70（log-analyst，依赖已满足）→ task-68（`blocked_by task-67`，已满足）→ 收 task-54（**已完成**，PASS×3 + PASS-WITH-NITS；三条打穿见 task-71/72）。
  3. 全绿后冻结 **0.7.26**：`tools/_note-0726.txt`（首串必须是 `v0.7.26`）→ `python tools/_bump-mod-version.py 0.7.26 --note-file tools/_note-0726.txt` → 改 `brain/agentfarm/bridge.py:39` → `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental`（0 警 0 错）→ 提交 → `git add -A`（未跟踪 `scratch/*.py` 会被当成脏树）→ `python tools/check-release.py --expect 0.7.26` → `python tools/deploy-mod.py --no-quit` → `python tools/preflight.py --expect 0.7.26 --save-baseline logs/run7-baseline.json`。
  4. **脱离式起跑**（DSH 托管后台作业会在回合边界被连根收掉，run4 只跑 13 秒）：`python tools/start-detached-longrun.py --journal logs/longrun-3day-llm-run7.jsonl --expect-version 0.7.26`（先 `--dry-run` 看四要素）→ `tools/verify-run3.py` + `tools/analyze-longrun.py` 双复核 + `scratch/run6-snapshot.py` 外部快照。
  5. ⚠ goal `goal-1ee4cda9-fdd4-4ba0-80cb-0c06902157eb` = **phase paused / disarmed**（模型侧不能 resume）⇒ 明天在界面里 resume，或直接对我说「继续」。

## 0c. 2026-10-13 02:40 整理停当（**与下文冲突以本节为准**）

用户节奏：`User said (m04479)` goal 轮续跑 → `User said (m04528): "停下来了把？明天再搞"` → `User said (m07147): "重新整理一下，明天在继续任务"` ⇒ **今天到此为止，明天开工**。

- **goal**：`goal-1ee4cda9-fdd4-4ba0-80cb-0c06902157eb` = **phase paused / disarmed（rev5）**，模型侧不能 resume ⇒ **明天要在界面里 resume**（或直接跟我说"继续"）。
- **队友**：全部 **inactive**（dev-coder、planner-dev 已在被叫停时 `interrupt_agent`；无人在跑、无半截写入进行中）。
- **环境（02:40 实测）**：游戏进程 0、`bridge.json` 不存在、17890 无监听；存档 `Wahaha_450799035` 3502298 B / mtime `2026-10-11 22:24:19` **未动**；装机 Mod **0.7.22**，`brain\agentfarm\bridge.py:39 MOD_VERSION_EXPECTED="0.7.22"` 与之相同。
- **未提交的在制品（task-19，尚未验收）**：`brain/agentfarm/longrun.py`(+143) + `tests/test_longrun.py`(+151)：**`checks.watered_outdoor` + `day_end.final_water` 已写进代码**（字段 `longrun.py:243`、落 journal `:281-283`、口径 docstring `:542-547`、日级证据 `:1883`）。
- **停点读数（Lead 亲跑）**：`py_compile brain\agentfarm\{longrun,farmwork}.py` exit 0；全量 **`Ran 290 tests / OK`**（基线 284 ⇒ 净增 6）。
- **task-31 取证未交付**：`docs\_il-bed-interaction.md` **不存在**（planner-dev 被叫停前只留下两个只读探针 `scratch\_probe_save_bed.py`、`scratch\_probe_save_raw.py`）⇒ 明天要**重派或续做**。
- **明天开工 30 秒版**
  1. `git status --short` + `python -m unittest discover -s tests`（期望 **290 OK**；上面两个 WIP 文件还在就说明停点没被别人动过）。
  2. `python tools\deploy-mod.py --no-quit`（起游戏 + 自动读档）→ `python tools\preflight.py --expect 0.7.22`（**exit 0 才准跑真机**）。
  3. **让 deputy-lead 独立验收 task-19**（它已待命，`grep watered_outdoor` 命中即做）：①四字段真名与语义（`watered_outdoor`/`final_water.scope`/`tiles`/`crops`/`dry`）②"没有任何户外快照 ⇒ False/缺省、**禁止默认 true**"③`farm.complete==false` 或旧 Mod 缺 `dryCrops` ⇒ 退回窗口口径 ④任务书 5 条假世界用例 ⑤与 `tools\verify-run3.py` 新闸门一致（通过形态 = `scope=="farm"` + `tiles>0` + `crops>0` + `dry==0` + `watered_outdoor==true`；窗口口径必须 `tiles>0`）。**验收过才提交**。
- **继续顺序**：task-19 验收提交 → **task-31 取证**（重派 planner-dev）→ **task-33**（睡觉链路修复，按 31 结论；`blocked_by [task-31, task-19]`）→ **task-32**（上限触顶不许早睡）+ **task-34**（逐格 `tile_step` 证据，U1）→ 冻结 **0.7.23** → machine-runner 真 3 日 run3 → `verify-run3.py` + `analyze-longrun.py` 双复核 + 外部证据（存档 mtime/size、SMAPI `NewDay`/`SaveGame.Save`）。
- **已提交（本段工作的完整链条）**：`dd7ea96`（0.7.22 冻结）→ `cd41905`（彩排收尾 + 条目 034 + §0b）→ `4f411ef`（deputy B4b 闸门 + `docs\_verify-run3-limits.md` v3 + log-analyst 复算口径 + **U3 修复** + 条目 034 三处数字修正）→ `4ff87a2`（§0b 更正 + 深夜派工 task-19/31/33/34）→ `02105d9`（§0c 停点）。

## 0b. 2026-10-13 凌晨收工更新（**与下文冲突时以本节为准**）

- **状态**：Mod **0.7.22 已冻结并装机过**（`dd7ea96`：`manifest.json` 0.7.22 + `brain\agentfarm\bridge.py:39 MOD_VERSION_EXPECTED="0.7.22"` + `dotnet build --no-incremental` 0 警 0 错 + 全量单测 **280 OK**）；彩排后已按 m02833 **优雅退出游戏**（`pids=[29744]` 已消失、`bridge.json` 不存在、17890 无监听），存档 `Wahaha_450799035` **3502298 B / mtime `2026-10-11 22:24:19` 未被改写**。开工请按老规矩来：`python tools\deploy-mod.py --no-quit` 起游戏 + 读档，再 `python tools\preflight.py --expect 0.7.22`（exit 0 才准跑）。
- **彩排（1 游戏日，`logs\longrun-rehearsal-0.7.22.jsonl`，4.31 分钟 / 114 动作 / 退出码 1，两份 day 报告都是 spring 11）结论**：**农场作业面全绿，跨日仍失败**。
  - 绿：浇水 **32/32**（`farm.dryCrops 32→0`，含一次 `refill waterLeft 0→40`）；`clear_area` **19 个 stage 条目（天1 10 + 天2 9）/ ok 73 / failed 1 @`(72,51)`（"四邻都站不过去"）/ skipped 0**、`proven_inert=0`/`env_block=0`/`inconclusive=0`；**LLM 边界决策真在用**（`decision` **23 条里 6 条** `source=llm`：`new_day=2`/`task_kind_change=3`/`recovery=1`，给出 `water_area@anchor:field_ne / field_se`、`clear_area@anchor:field_nw` 等**具名田区方向**，坐标由代码落）；政策接管（`water_area` 提到最前）与校验关口（`till_area` cancel / `clear_area` unknown）都有账本证据。**（数字以 log-analyst 只读复算为准，`scratch\_reh_analyze3.txt`）**
  - **硬发现 1（跨日卡点 A）**：`move_to_location("FarmHouse")` 把**门格 (64,14) 当 A* 目标** ⇒ `A* 未算出路径` ⇒ `sleep_failed`。旧 recipe 是"站 (64,15) 再 `checkAction((64,14))`"。
  - **硬发现 2（早睡换形态）**：`plots_today >= max_plots_per_day(10)` ⇒ `no_plot` ⇒ 09:40、体力 144.7 就准备睡，而 `work_reasons` 仍非空（= m02532 的老毛病）；`day_justified` 现在居然**接受 `no_plot`**。
  - **硬发现 3（跨日卡点 B）**：进屋后 `sleep_no_question` —— 玩家已站床旁 (8,8)、`interact((9,8))` 弹不出睡觉提问（`lastQuestionKey=(空)`），且脑侧想"踩上床格"时 A* 也失败（室内 `tiles[]` 只有 1 格，应看 `location.furniture[].isBed`）。
  - **外部证据**：彩排前后 `day` 都是 `spring 11`、存档 size/mtime **没动** ⇒ 跨日确实没发生（`scratch\rehearsal_state.py` 只读快照）。
- **明天第一件事（顺序）**：**task-19**（`checks.watered_outdoor` + `day_end.final_water`，消费 `farm.dryCrops`；缺它 run3 必被自己的工具判 exit 1）→ **task-31**（只读取证：门格寻路 + 上床/提问）→ **task-33**（按 task-31 结论做修复；`blocked_by [task-31, task-19]`）→ **task-32**（上限触顶不许早睡）+ **task-34**（逐格 `tile_step` 证据落账，U1）→ 冻结 **0.7.23** → machine-runner 跑真 3 日 run3 → 双复核 + 四条外部证据。
- **队友状态**：dev-coder 已**开工 task-19**（brain-only，是 run3 直接前置）；planner-dev 已**开工 task-31 的取证半边**（只写 `docs\_il-bed-interaction.md` + `scratch\`，不许碰源码）；deputy-lead 待命（`grep watered_outdoor` 在 `brain/` 命中即对 task-19 做独立验收）；log-analyst 只读待命（task-5 未开）；machine-runner 待命等 "deploy done"。
- ⚠ **goal `goal-1ee4cda9` 已被用户 resume**（revision 4 / phase active / armed，round 8/60）⇒ 会自动续跑；本轮深夜续跑就是在 goal 轮里推进。**（已过时：用户随后叫停，见 §0c —— 现为 paused/disarmed rev5。）**
- **已提交**：`cd41905`（彩排收尾 + 条目 034 + §0b + preflight 坑修）、**`4f411ef`**（deputy B4b 窗口口径闸门 + `docs\_verify-run3-limits.md` v3 + log-analyst 复算口径 + **`tools\verify-run3.py` 浇水检查提到 `sleep` 分支外（U3）** + 条目 034 三处数字修正）。
- **U3 已修（我亲跑回归）**：`_water_problems()` 在 `ended_by=="sleep"` 与否则两条分支都调用 ⇒ 睡觉失败的日子不再静默跳过浇水验收；绿本/neg-G/I/S 仍 exit 0，A/B/E/R/K + 彩排 + run2 各 exit 1。
- **一条观察**：后台长任务的 stdout/文件写是**块缓冲**（jsonl 攒到 2048 B 才落盘）⇒ 想边跑边看要加 `-u`。

## 0a. 2026-10-13 开工更新（**与下文冲突时以本节为准**）

- **开工状态**（2026-10-13 上午实测）：游戏进程不存在、`bridge.json` 不存在、17890 无监听、存档 `Wahaha_450799035` size 3502298 / mtime `2026-10-11 22:24:19` 未改写；全量单测 **Ran 194 tests / OK**；工作树只有 dev-coder 的 5 个在制文件（`brain/agentfarm/bridge.py`、`brain/agentfarm/farmwork.py`、`mod/AgentFarm.Bridge/UseToolSkill.cs`、`tests/test_farmwork.py`、`tests/test_longrun.py`，+302/−35）。
- **deputy-lead 对 task-7 的预检 = 绿**：`py_compile` exit 0、**194 OK**、`dotnet build` **0 警 0 错**；提醒最终验收要 `--no-incremental` 全量重建。
- **任务板已改**（Lead 独占）：`task-12 blocked_by += task-19`（rev3，理由：task-19 才写 `checks.watered_outdoor`，缺它 run3 必被自己的工具判 exit 1）；`task-19 blocked_by=[task-15, task-17]`、`task-13 blocked_by=[task-17, task-19]`、`task-18 blocked_by=[task-11, task-21]`（串行化同文件写者）。**新的串行顺序见 §3**。
- **新任务**：**task-21**（planner-dev：`LevelUpMenu` 职业选择能否程序安全驱动的探针，交付 `docs/_il-profession.md`，是 task-18 的前置）；**task-5** 由 log-analyst 继续（`docs/_il-sell-path.md`）。
- **0.7.22 发布规则改为 Lead 独占**（详见 §3 末段）：一次装机 = task-7 + task-8 + task-19；bump 与部署都由 Lead 在 deputy 完整验收通过后执行。
- **门槛更新已落 `tools/verify-run3.py`**：要求 `day_end.checks.watered_outdoor`（缺字段即算问题）。负例回归 7/7：绿账本 exit 0，neg-A/B/C/D/E/F 各 exit 1（E = 完美一天只缺该字段）。
- ⚠ **goal `goal-1ee4cda9` 仍是 paused（disarmed）**：模型侧 resume 被拒（"the user must resume it"）⇒ **需要用户在界面里 resume**，否则本轮结束后不会自动续跑。今日进展见 `docs/00-开发日志.md` 条目 029。

## 0. 一句话状态

Mod **0.7.21** 装机中（游戏**未运行**、桥文件不存在、端口 17890 无监听、存档未被改写——machine-runner 独立复核过）；单测 **194 OK**（dev-coder 昨晚收工前跑出，188 → +6）；`git status` 有 dev-coder 的 5 个 WIP 文件未提交（见 §4）；任务：task-7（dev-coder，已停点、**代码在树里但未 bump/manifest 仍 0.7.21**）、task-10（log-analyst，**已交付并 complete**）；已交付的分析 = task-3（run1 行为）、task-6（睡觉根因）、task-9 复核（deputy-lead，6 账本独立复跑 PASS）、**task-10（`docs\_tool-matrix.md` + `docs\_analyze-farmcounts.md`）**；**新增 task-19**（浇水/计数验收口径，run3 前置）、**task-20**（工具等级可观测 + clump 判据，不阻塞 run3）。**两条最硬的结论** = 睡觉失败机制（`docs\_il-sleep-path.md`）+ **我自己的验收工具曾"白过"浇水一项**（见 §6 / §8）。goal 已 pause（rev3 / disarmed），你说"继续"就 resume。

## 1. 明天开工 30 分钟内要做的三件事

1. `git status --short` + `python -m unittest discover -s tests`（期望 188 OK，dev-coder 若已补用例会更多）——确认昨晚停点没被别人动过。
2. 看 `docs\_resume-tomorrow.md`（本文）§3 的任务顺序，把 task-7 的结果收进来：dev-coder 报完工 ⇒ 立刻让 deputy-lead 做集成验收（`py_compile` + 全量单测 + `dotnet build` 0 错 0 警）。
3. 收完 task-7 后按串行链推进；**Mod 版本只 bump 一次**（0.7.22），bump 完跑 `python tools\check-release.py --expect 0.7.22`。

## 2. 今天的决定性结论（task-8 直接照这个做）

`docs\_il-sleep-path.md`（含偏移级 IL 证据）：

- `GameLocation.answerDialogueAction` 是**字面量分派**：`IL_0ABC ldstr "Sleep_Yes"` → `brtrue IL_30D5` → `call startSleep()`；**没有** `isInBed`/`dialogueUp`/`lastQuestionKey` 前置判据；字符串对不上就 `IL_393D` **静默 no-op**（`Farm` 覆写同偏移同序列、`FarmHouse` 不覆写）。
- `startSleep()` 唯一分支 = `Game1.IsMultiplayer`：真 → 装 `ReadyCheckDialog("sleep", isCancelable: true, …)` 返回、**不睡**；假 → `doSleep()`。
- `doSleep()` **零前置判据**，三条分支都 `if (Game1.IsMasterGame) Game1.NewDay(0f)`。
- 22:07:55 的 PASS 探针在同一进程同一存档 **1.8s 跨日** ⇒ `IsMultiplayer=false`、`IsMasterGame=true` ⇒ run2 失败**只能**是"应答字符串没等于 `Sleep_Yes`"⇒ `lastQuestionKey` 前缀不是 `Sleep`（提问没开、`interact(bed)` 没能让游戏弹提问）。

⇒ task-8 的判据用"**游戏自己弹出了睡觉提问**"（`lastQuestionKey` 前缀 `Sleep` / `ui.dialogueIsQuestion`），**不要**用 `isInBed`；拼不出 `Sleep` 前缀就立刻 `sleep_no_question` 失败（附 `isInBed`/`lastQuestionKey`/`activeClickableMenu`/`gameMode`），绝不等 180s；不要反射调 `startSleep()`/`doSleep()`。

## 3. 任务顺序（单写者串行，改自今天定稿的链）

```
task-7 (Mod 0.7.22: 镰刀真挥 + Done() Grass 判据 + clear() 多刀)   ← dev-coder 已停点（代码在树里）
  → task-8  (sleep 跨日: 先让游戏弹提问再回答; Mod 早失败)          blocked_by task-7
  → task-11 (模态守卫: LevelUpMenu 关 / SaveGameMenu 只等)          blocked_by task-8
  → task-15 (日级验收纳 no_unmet_stages + 买种子时机)               blocked_by task-7, task-11
  → task-17 (world_stuck 检测与自愈)                                blocked_by task-11, task-15
  → task-19 (浇水/计数验收口径: checks.watered_outdoor, run3 前置)   blocked_by task-15, task-17
  → task-13 (bridge.json 字段容错)                                  blocked_by task-17, task-19
  → task-14 (ensure_location 逐帧 warp 循环 + /v1/exec 带 skill 名)  blocked_by task-13, task-17
分析链：task-6 ✅ → task-10 ✅ → task-5 (卖出/出货 IL 取证, log-analyst 进行中)
职业链：task-21 (LevelUpMenu 职业选择探针, planner-dev) → task-18 (职业选择自动化, blocked_by task-11, task-21)
run3 之后（不阻塞）：task-20 (工具等级可观测 + ResourceClump 工具/判据, blocked_by task-12)
真机：task-12 = run3 三日连跑（machine-runner，blocked_by task-7/8/9/11/15/**19**）——**必须等 Mod build 完 + Lead 部署完再 claim**；缺 task-19 会让 run3 被自己的 `verify-run3.py` 判 exit 1（白烧唯一一次真机）
```
**Mod bump 规则（2026-10-13 更新，Lead 裁定）**：0.7.22 = **一次装机**的合并版本，内容 = task-7（镰刀真挥 + `Done()` Grass 判据 + 多刀）+ task-8（sleep 跨日/快速诚实失败）+ task-19（`farm.dryCrops`/Contracts 字段）；**bump `manifest.json`、同步 `MOD_VERSION_EXPECTED`、`tools/deploy-mod.py` 装机全部由 Lead 独占**，在链条全部落地且 deputy-lead 完整验收通过后一次执行；task-7/8/19 都**只改代码不 bump**（避免"版本号相同、内容不同"的假 0.7.22 —— v0.7.17 教训）。task-14 赶得上并入同版，赶不上 0.7.23 二次部署，不影响 run3 起跑。

`task-9`（brain 账目/资源三处）已完成；`task-3`/`task-6` 已交付；`task-16` = deputy-lead 常设独立验收（每份 dev-coder 完工都要过它）。

## 4. 未提交的工作树（明天先看清再决定）

`git status --short`（收工时）：**dev-coder 的在制文件不要替它提交/回退**——`mod/AgentFarm.Bridge/UseToolSkill.cs`、`brain/agentfarm/farmwork.py`、`brain/agentfarm/bridge.py`（仅 docstring）、`tests/test_farmwork.py`、`tests/test_longrun.py`；另有 `scratch/_farm_dump.py` 未跟踪（不是 dev-coder 的）。
Lead 自己的改动（`tools/verify-run3.py`、`docs/_il-sleep-path.md`、`docs/_analyze-sleep-fail.md`、`docs/_review-task9.md`、`docs/00-开发日志.md` 条目 028、本条目、`scratch/_review_neg_gen.py`）已提交（`2ed2117`）。

### 4a. dev-coder 的 task-7 停点报告（昨晚收工，原文要点）

- **验证原文**：`py_compile exit=0`；`python -m unittest discover -s tests` → `Ran 194 tests in 2.342s` / `OK`；`dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo` → `已成功生成。` / `0 个警告` / `0 个错误`（仅编译自检，**未 bump、未 deploy**）。
- **改了什么**：①`UseToolSkill.Swing()` 不再调 `Game1.pressUseToolButton()`，改调新增 `BeginUse()` —— 照抄游戏近战门闸**之后**那段（`GetToolLocation(clickPx,false)` → `FacingDirection` → `lastClick=clickPx` → `p.BeginUsingTool()`；拿不到 player/工具或异常时回退 `pressUseToolButton()`）；②`Done()` 补 `if (tf is Grass) return false;`；③失败回执加"现在还是「<kind>」+ 起手=是/否"；④`farmwork.clear()` 挥到 `kind` 变化为止、上限 `MAX_CLEAR_SWINGS=4`，只有挥满上限或 Mod 回 `tool_ineffective`/`precondition_failed` 才 `proven_inert` 封格，`no_save`/`ui_modal` 记 `failed` 且**不封格**；⑤`_receipt_of()` 把 Mod reason 带进 journal。
- **待裁定的偏差**：没有"伪造输入边沿"，改走 `BeginUsingTool()`。
- **Lead 裁定（2026-10-11 收工）**：**批准走 `BeginUsingTool()`**。理由：`Farmer.BeginUsingTool()` 只 fire `beginUsingToolEvent`，订阅者 `Farmer.performBeginUsingTool()` 就是真正的起手（`CanMove=false; UsingTool=true; CurrentTool.beginUsing(...)`），镰刀同步进 `MeleeWeapon.setFarmerAnimating` → 同一次调用内 `DoDamage` —— 这是**游戏自己的入口**（与"用 `addItemToInventoryBool` 收货、用 `chargePlayer` 扣钱"同一原则）；伪造 `InputState._currentMouseState`/`Game1.oldMouseState` 会污染同帧所有读输入的系统，且挥动方向取决于人手鼠标位置，不可接受。**条件**：真机差分必须看到 `grass → 非 grass` + 回执"起手=是"；若真机证明割不动，再回头讨论"合成左键边沿"这条备选。
- **明天给 dev-coder 的两条附加要求**：①非近战工具现在跳过 `fadeToBlack`/`nonWarpFade` 门卫（渐黑时可能白挥一次）⇒ 在 `BeginUse()` 里加一个便宜的门：`Game1.fadeToBlack`（或 `nonWarpFade`）为真时返回**可重试**状态而不是挥；②Mod 内部 `MaxSwings=6` 与脑侧 4 刀叠加，最坏 4 次请求 ⇒ 真机跑完要拿 journal 的"第 N 刀"轨迹确认没有空转。

## 5. 命令速查（全部在仓库根目录跑）

```powershell
# 0) 环境（每次新 shell）
$env:PYTHONUTF8=1
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONPATH = "D:\Deepseek Harness Workspace\星露谷游戏自动化\brain"

# 1) 单测（以 "Ran N tests / OK" 为准；pwsh 报 [exit code: 1] 是 unittest 写 stderr 的噪声）
& $py -m unittest discover -s tests

# 2) 发布闸门（manifest==MOD_VERSION_EXPECTED、dll 新鲜度、py_compile、单测、git 干净）
& $py tools\check-release.py --expect 0.7.22

# 3) 只读起跑自检（装机版本 / hasSaveLoaded / isOutdoorFarm / isModal / worldAdvancing + 基线快照）
& $py tools\preflight.py --save-baseline logs\run3-baseline.json

# 4) 装机（Lead 独占真机；装机脚本会优雅退出游戏 → 装 dll+manifest → 启动 → 轮询 health → load_save）
& $py tools\deploy-mod.py

# 5) run3（machine-runner；跑完立刻优雅退出，别把游戏留在跑）
& $py tools\run-longrun.py --days 3 --size 5 --max-minutes 150 --journal logs\longrun-3day-llm-run3.jsonl

# 6) 独立复核（Lead；只读 journal，不采信执行者口头结论）
& $py tools\verify-run3.py --journal logs\longrun-3day-llm-run3.jsonl --days 3
```

## 6. 明天的验收口径（不许软化）

- **浇水证据（今天新堵的洞）**：窗口 `tiles[]` 的 `crops`/`unwatered_crops` **在室内恒 0** —— run2 里 `day_end.final` 是 `FarmHouse crops=0` 而 `checks.crops_watered=true` 白过；Mod 的 `farm.unwateredCrops` 又是 `HoeDirt.needsWatering()`（只读 `CropData.NeedsWatering`、**不看浇水状态**）⇒ 两者都**不能**当浇水证据。`tools\verify-run3.py` 现在要求 **`day_end.checks.watered_outdoor`**（缺字段即算问题），该字段由 task-19 落地：用当天**最后一个户外全量快照**逐格算"有 crop 且 `watered==false`"，或（更好）用 Mod 新增的 `farm.dryCrops`（farm-wide 真值，需 `farm.complete==true`）；`day_end.final_water` 记 `{t, location, tiles, crops, dry, scope}` 供手工复核。
- 尾部**连续 3 天**满足：`ended_by == "sleep"`（我们自己睡的）+ `day_end.verified == true` + `checks.watered_outdoor == true` + 当天 `day_end.stages` 求和硬失败 0 + 有目标阶段 `leftover == 0` + journal 无 `bridge_down`/`watchdog_stop`/`modal_timeout`/`no_day_progress`。
- 跨日证据：`day_end.final.day` 与 `day_start.day` 不同 **且** journal 里有成功的 `sleep` 事件；存档 mtime/size 前进。
- **`farm.*` 只在 `farm.complete == true` 时可用**（`complete=false` 全 0 ≠"0 个作物"）；两套计数（farm 扫全场 / 窗口 400 格）**不许混列**（run2 的 31→8→21→32 就是混列）。
- 回执 `ok=true` **不构成**任何判定依据（v0.7.17"种了种子不扣"与今天 `answerDialogueAction` 静默 no-op 两次教训）。

## 8. task-10 的两份交付（今天新增的关键事实，动手前先读）

- `docs\_tool-matrix.md`（对象→正确工具→等级门槛）：硬等级门槛**只在 `ResourceClump` 与 `Bush`**（600=铜斧≥1、602=钢斧≥2、148/622=金镐≥3、672=钢镐≥2、752 系列=镐任意；Bush 需斧且(铜斧或 `size==3`)）；weed/twig/stone/tree/fruitTree/grass **无门槛**（stone 只按等级算伤害）；grass 多刀（`(W)47`=1/刀、`53`=2、`66`=4，蓝草 50% 空挥）。**观测判不了工具等级**（`player.tools{}` 只有布尔）⇒ 现行规则 R2：`clump` 整类 `skipped`+`proven_inert`，不用 `auto` 去撞；Mod 缺陷 `WorldSnapshot.cs:438` 把 `ResourceClump` 一律写 `tool="axe"`（对巨石错）——都进 **task-20**。
- `docs\_analyze-farmcounts.md`（farm 聚合口径）：见 §6 的浇水证据条目。


## 7. 硬纪律（复用，别重新踩）

- 改 Mod ⇒ `dotnet build` **0 错 0 警** ⇒ 只有 Lead 能 `deploy-mod.py`（真机独占串行）。
- 改文件用编辑工具或"先写 .py 再执行"；**PowerShell 5.1 直接读写 UTF-8 会毁中文**。
- `tools\il-probe` 重定向到文件是 **UTF-16LE**，先 `tools\_tmp_conv.py` 转 UTF-8 再 `read`/`grep`。
- 异步传送/淡出期间不下失败结论（`Game1.locationRequest != null`）；`pid_alive` 绝不用 `os.kill(pid,0)`。
- 队友之间：写范围不重叠，跨任务顺序由 `blocked_by` 表达；被 `blocked` 的任务**不能** reassign owner。
- 用户硬要求：**大模型开始介入自动化循环前先告知用户**（已履行，2026-10-11 手动演练 + 用户已批准默认开启）；LLM 只给**方向**（具名田区 + 规模），**坐标一律由代码落**。
