# 0.7.28 发布 / 验收计划（run9 = run A，run10 = run B）

> 起草：2026-10-15 22:35（Lead）。状态：**未冻结**（等 task-104/task-106 交付 + task-103/task-108 对抗验收 PASS）。
> 上游：`docs/_release-0.7.27.md`（0.7.27 已装机并跑出 run8，证据见 `docs/_run8-evidence.md`、开发日志条目 053）。

## 1. 本版内容（卡片即权威）

### 1a. 第一批：run8 两病灶（已交，验收已过）

| 卡 | owner | 内容 | 状态 |
|---|---|---|---|
| **task-102** | dev-coder | **A 经济闭环空格死锁**（`no_space` 独立结果 + 当天 ≤3 次；`seeds_total==0 && money>=seed_price && free_slots==0` ⇒ 整叠卖一叠盈余材料腾格，白名单、不碰种子/工具/武器/建材；buy 前清残留模态；优先当季在售买得起的种子）+ **B 早睡防线**（钱够买不到/农场有干作物时 `sleep_guard` 不许放行；不许 0 动作收工；`goto_farm` 遇模态先清一次再重试） | **已交 `9b09735`**（Lead 已核范围与读数） |
| **task-103** | deputy-lead | 对 task-102 的独立对抗验收（空格死锁复现 FAIL→PASS、腾格卖出不得碰种子/工具/K、跨天重试有界性、`no_space` 谎报成功、睡前后模态 fail-closed） | in_progress |
| **task-104** | dev-coder | **`_water_far_dry` 人在农场之外不许扣当日额度**（run8 day12：晨间 `ShippingMenu` 挡掉 `goto_farm` ⇒ 人在室内逐格试 6 格全 `unreachable`、当天全体认输、0 动作早睡）⇒ 入口先回农场（清模态 + 重试一次）、`water_far_skipped{reason:"not_on_farm"}` 不 `try_++`/不进 `given_up`、收尾 `not_on_farm` 点名 | **已交 `9b5b592`**（Lead 已核：2 文件 +246/−2、越界零命中、`tests.test_farmwork tests.test_longrun` 281 OK） |
| **task-108** | deputy-lead | 对 task-104 的独立对抗验收（`not_on_farm` 不扣额度、收尾点名、回不去时的有界性、回农场后仍能浇的正例） | in_progress |
| **task-106** | log-analyst | **analyze-longrun 收 task-102 新事件/字段**（`slept_without_work`/`buy_no_space`/`surplus_sell.why=need_slot`，另补 `modal_dismiss_failed`/`water_far_skipped`）——`TestEventMappingDrift` 那条红**必须清零** | **已交 `6293696`**（Lead 已核：3 文件 +372/−2、越界零命中、`tests.test_analyze_longrun` 122 OK、全量 618 OK 零红） |

### 1b. 第二批：LLM 决策复盘/演进（**明天做**，brain-only，串行同一 owner）

> 来源：用户 `m12553`：「总之要让模型再玩这个游戏的时候具备决策演进的能力，你自己定吧」⇒ Lead 决定并入 0.7.28。

| 卡 | owner | 内容 | 状态 |
|---|---|---|---|
| **task-58** | dev-coder | `Brief.recent_decisions` 骨架（最近 3–5 条边界决策 + 结局摘要喂回提示词，≤300 字符；超限时决策史最先被裁；≥4 单测） | pending（明天第一个开工） |
| **task-82** | dev-coder | 决策→结果 join（`terminal`/`leftover`/`unreachable`/`refused`/`ended_by`/失败格坐标 ≤3）+ **跨日教训库** `<journal>-lessons.json`（客观事实代码写、一句 `hint` LLM 写；≤~20 条按 `last_seen` 淘汰；次日注入 ≤3 条 ≤200 字符；**只认客观证据**） | pending |
| **task-59** | dev-coder | night 边界一次独立复盘调用（只写 `review_llm` + 次日 `recent_notes`；**失败无害**；`max_tokens ≤512`；notes 含坐标 ⇒ 拒收） | pending |
| **task-111** | log-analyst | analyzer 收录本批新事件/字段（防漂移红）+ 八本账本两侧 rc 同向 | **已交 `d10dc6b`**（5 个新事件入桶 + 三条完整性红 + 全量 665 OK / 0 红） |
| **task-116** | log-analyst | analyzer 收 task-114 的新事件 `lessons_rejected` ⇒ **全量归零**（0.7.28 放行条件） | pending（0 红前不许冻结） |
| **task-112** | deputy-lead | 独立对抗验收：**最高优先级 = 零判定影响**（开/关机制 `verified`/`checks`/`final_water` 逐字相同）+ 只认客观证据 + 失败无害 + 有界性 + ≥4 对抗 | pending（`blocked_by 58/59/82`） |

> **诚实边界**（写进 evidence 与给用户的结论）：这是「会话内记忆 + 提示词反馈」，**不是**权重更新/在线训练。
> **演进验收**：run9 = run A（积累）→ run10 = run B（注入）。必须有"run A 某意图被 cancel/失败 → run B 的 prompt 里出现对应教训、且同形态不再出现"的对照证据，**否则不许写"自我进化已实现"**。

## 2. 冻结与装机九步（Lead 独占，链式，不许并行）

1. `team_task_get` 确认 **task-102 / task-104 / task-106 / task-58 / task-59 / task-82 / task-111 / task-114 / task-116 已 completed**，且 **task-103 / task-108 PASS、task-112 FAIL→task-114 已修、task-115 PASS 或 PASS-WITH-NITS（无必修）**。
   - 其中 **task-112 = FAIL**（`docs/_review-llmfeedback.md`：F1 教训库来源可信性、F2 裁剪优先级）⇒ **task-114 修 → task-115 delta 复验**；两条都不阻塞 run9 判定正确性，但削弱演进机制，故列为本版必修。
   - task-111 已交 **`d10dc6b`**（5 个新事件入桶 + `review_llm_without_notes`/`lessons_over_limit`/`lessons_load_failed` 三条红；全量 **665 OK / 0 红**；八账本 rc 与 `verify-run3` 一字未变）。
   - **task-114 已交 `c135edc`**（教训库 schema 信任边界 + 裁剪优先级 核心>教训>决策史>笔记 + `no_inventory_space.evidence` 用当次真值；丢条目记新事件 `lessons_rejected`）；**task-116 收该事件前全量有 2 条漂移红**（`Ran 672, failures=2`，均在 `tests/test_analyze_longrun.py`）⇒ **task-116 归零是本版放行硬条件**。
2. 确认 `tools/_note-0728.txt` 存在且**首串是 `v0.7.28`**（列本版两批卡片：run8 两病灶 + LLM 复盘/教训库；LLM 两条等 task-82/task-59 落地后按实际内容补写）。
3. `python tools/_bump-mod-version.py 0.7.28 --note-file tools\_note-0728.txt`（⚠️ cp1252 下末句 print 会 `UnicodeEncodeError` 且退出码 1，但**版本已写盘** ⇒ 一律用 `json.load` 核对 `manifest.json` 的 `Version`）。
4. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.28"`。
5. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ 0 警告 0 错误；记下 `AgentFarm.Bridge.dll` / `manifest.json` 的 B 与 mtime。
6. `git add -A` → 提交（**先提交再 check-release**：它要求工作树干净，未跟踪 `scratch/*.py` 也算脏）。
7. `python tools\check-release.py --expect 0.7.28` ⇒ 须全绿（含全量单测 `Ran N tests / OK`）。
8. `python tools\deploy-mod.py --no-quit` ⇒ 装机 + 读档；记下桥 `modVersion=0.7.28 port=17890`。
9. `python tools\preflight.py --expect 0.7.28 --save-baseline logs\run9-baseline.json` ⇒ 四绿（版本/已读档/在户外农场/无阻断模态）。

## 3. 起跑（machine-runner，task-89 家族）

```
python tools\start-detached-longrun.py ^
  --journal logs\longrun-3day-llm-run9.jsonl ^
  --expect-version 0.7.28
```
- 起跑前 `python scratch\run8-snapshot.py --tag start --expected-mod-version 0.7.28`（脚本沿用，输出 `scratch/run9-external-snapshots.jsonl`；PID 候选 `logs/run9.pid`）。
- **起跑命令行必须原文记录**（`docs/_run9-evidence.md` §1 + console 头）：run9 = run A（积累）、run10 = run B（注入），两次**只许 journal 路径不同**，其余参数（`--days/--size/--max-minutes/--max-days/--boundary-llm`）逐字一致，否则"演进对照"不成立。
- 结束后立刻 `--tag end`，**先别退游戏**（Lead 要 live observe 对账），再写 `docs/_run9-evidence.md`。
- 现场政策不变：`ui.eventUp=true` ⇒ **立即停手等人**（task-41）；不替游戏做选择。
- **run10 交接（Lead 独占，且必须留痕）**：run9 结束后，把 `logs\longrun-3day-llm-run9-lessons.json` **原样拷贝**成 `logs\longrun-3day-llm-run10-lessons.json`（记录拷贝时刻 + 源/目标 SHA256，命令原文写进 `docs/_run10-evidence.md` §1 与版本 sidecar）。理由：教训库路径由 `--journal` 自动推导（`X.jsonl` ⇒ `X-lessons.json`），**没有任何命令行开关** ⇒ "把上一轮教训交给下一轮"必须由这一步显式交接完成；两次 run 的 journal 也必须各自独立（不许复用同一路径，否则证据互相覆盖）。

## 4. run9 验收判据（继承 0.7.27 + 本轮新增四条）

继承：尾部窗口 N=3 全 VERIFIED（`tools/verify-run3.py`，并**并列严格整本第二判决**）；四腿覆盖（clear/till/plant/water 至少各有成功步）；`watered_outdoor` 只在 farm 证据可用时算数；`no_work` ⇒ `final_water.dry==0`；`dry_dead` 不得污染浇水判据；跨日 `day_after` 恰 +1；SMAPI 外部证据（`NewDay` / `before save` / `SaveGame.Save() called.`）。

**本轮新增（run8 病灶的对偶判据）**：
- **N1 每天必须有农场动作**：任何 `ended_by=="sleep"` 的日子，`ok_steps >= 1`（0 动作收工 ⇒ 必须记 `slept_without_work` 且 `verified=false`）。
- **N2 经济闭环四步留痕**：`sell`/`surplus_sell`（卖出）→ 次日 `day_start.money` 增加（到账）→ `buy` 成功（当季种子）→ `sow`/`plant_area` 至少 1 格成功；四步缺一即在该日 evidence 里点名。
- **N3 无空格死锁**：同一天 `buy` 尝试 ≤3、`no_inventory_space` 后不再重试；若因背包满，必须出现 `surplus_sell{why:"need_slot"}`。
- **N4 跨日与落盘**：每个 `day_after` 恰 +1；落盘缺口必须能用"日终菜单链（`ShippingMenu`/`SaveGameMenu`）"解释，否则记红。
- **N5 死苗证据不许"真空通过"**：run8 全程 `farm.deadCrops=0`/`dryDeadCrops=0`/`day_end.dead_crops=0` ⇒ task-84 的死苗路径在真机上**仍是真空未验**（见 `docs/_run8-evidence.md` §4.3 ③）。run9 若同样没有死苗，evidence **必须明写"本轮无死苗 ⇒ 该判据真空，不算通过也不算失败"**；想真正验到它需要跨换季（下一次换季 = 秋1日，距今约 15 游戏日）或另设针对性场景 —— 记为后续 run 的必验项。

**run10（run B）专属 —— N6 演进对照**（判据全文 = task-113 卡面 + `tools/compare-runs.py`）：
- `--run-a logs\longrun-3day-llm-run9.jsonl --run-b logs\longrun-3day-llm-run10.jsonl` 必须跑通并把 JSON 附进 `docs/_run10-evidence.md`；
- run A 的教训库（`<journal>-lessons.json`）逐条原文 + 每条在 run B 提示词里的命中/未命中；
- run A 被 `cancel`/做不成的形态在 run B 的次数对照（**变了不等于因果，"没变"是硬事实**）；
- 两侧 `verify-run3` + `analyze-longrun` 判决并列；**没有可辨认的"学到"就如实写"未观察到演进"**，禁止挑字符串硬凑。

## 5. 与 run8 的对比基线

| 项 | run8（0.7.27） | run9 期望 |
|---|---|---|
| 尾部连续 VERIFIED | **0/3** | **3/3** |
| 自主卖出 | ✅ 1 次（Fiber 174 ⇒ 钱 14→188） | ✅ 至少 1 次 |
| 自主购买 | ❌ 26 次尝试 0 成交（`no_inventory_space`×25） | ✅ 至少 1 次成交（当季种子） |
| 自主播种 | ❌ 0 格 | ✅ ≥1 格 |
| 0 动作收工 | ❌ day 12（8 秒就睡） | ✅ 0 次 |
| 假 VERIFIED | ✅ 0 次（fail-closed 生效） | ✅ 0 次 |

## 6. 遗留（不进本版 → 0.7.29 候选）

- **task-101**（0.7.29）：`_farm_totals` 类型校验（`dryCrops="abc"` 会抛 `ValueError` 穿出整天；`"0"` 与合法 0 不可区分；`-1` 状态自相矛盾）、窗口全死苗时 `watered_outdoor` 的字段级收口、夹具 `farm_scan()` 的死苗口径。
- **task-107**（0.7.29，Mod）：`farm.dryTiles` 与 `farm.dryCrops` **同一次扫描 + 共用 `scanSeq`**（解释 run8 `[12,30]` 记 `ok` 但计数 `6→6`；dev-coder 已判定既非死苗也非一拍滞后 ⇒ 最可能同一次发布里不同源）。**脑侧 `_water_far_dry` 的 `ok` 判据不收紧**（计数若真滞后，收紧会造假失败）。
- task-83 rev2（田块规整：坐标级留痕 `sow_step`/`till_step` + `plant_layout.tiles` 坐标 + 五指标）—— 需要 run9 的数据才有意义。
- **task-109**（0.7.29）：`farmwork.py:1006-1015` money 循环无条件先跑 ⇒ 腾格分支在"存在真盈余叠"时不可达（实卖最大叠而 docstring 说最小；只缺 1 格却每 id 各卖一叠）；`longrun.py:2040-2047` 卖后用过期 obs ⇒ 多一次 `empty_slot` 卖出。
- **task-110**（0.7.29，老洞）：`longrun.py:974` `worker.ensure_location` 无 try/except，其内部 `snap()` 抛 `BridgeError` 会从 `run()` 穿出（无 `finish`/无 `day_end` 的静默死法）。
- **task-117**（0.7.29）：教训**内容模板校验**（按 kind 固定句式、只允许数字可变）+ 提示词里显式区分「观测真值」与「模型自述（不是真值）」。task-114 只锁了结构，**合法 kind 的自由文本仍会进提示词**（dev-coder 主动报备、deputy task-115 §NIT 再判）。
- task-14（逐帧 warp 活锁）、task-18（职业选择耕种优先）、task-53（农场级待清/待垦计数）、task-98（`Brief.from_observe` 无 tiles 时回退 farm 计数的耦合）。
- Mod `ShipSkill` 只能整叠出货 ⇒ 每 id 保留 K=10 做不到（详见条目 053 待决②）。
