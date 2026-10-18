# run10（run B）验收判据：LLM 决策演进（会话内记忆 + 提示词反馈）

> 用户裁定：`User said (m12553)`「总之要让模型再玩这个游戏的时候具备决策演进的能力」、`User said (m12569)`「定好之后排上任务，不用开始，明天再做」。
> 诚实边界（**必须与结论一起写**）：本机制是「会话内记忆 + 提示词反馈」（每次调用留痕 + 夜间复盘 notes + 跨日教训库），**不是权重更新、不是在线训练**。没有下面的 A→B 对照证据，**不许**写"自我进化已实现"。

## 0. 设定（**2026-10-17 修订：A/B 都改到 0.7.32 同一构建**）

> ⚠️ **本节已过时**：现行 A/B = **0.7.35 上的 A′/B′**（`logs\longrun-runA2-0735.jsonl` / `…runB2-0735.jsonl`，task-113 rev11）。下面 0.7.32 的具体路径/文件名只作历史记录；**§1 的五条判定与 §2 反混淆、§5 测量规则仍然有效**。
- **run A = 累积轮 = `logs\longrun-runA.jsonl`**（**0.7.32**、5 天、`--days 5 --max-minutes 240 --max-days 12`）：跑完后把 `…-runA-lessons.json` **原样拷**成 `…-runB-lessons.json`（记拷贝时刻 + 两侧 SHA256）。
- **A 的初始教训库允许"继承历史"**（本轮裁定）：可以把 run9d（0.7.31）的 `logs\longrun-3day-llm-run9d-lessons.json`（3712 B / SHA256 `2C4BA15FB…`，以实际台账为准）**原样复制**为 A 的初始库，理由 = 教训库本来就是跨日/跨轮持久的知识；**代价与纪律**：①A 与 B 必须是**同一份 0.7.32 构建**（sidecar 四要素逐字对齐，只有 journal 路径不同）；②复制时刻 + 两侧 SHA256 双向记账并写进 `docs\_runB-evidence.md` §1；③报告里如实写"库里有几条来自 run9d、几条是 A 自己新产出的"；④若用户要求"从零积累"，则 A 必须自己在 0.7.32 上跑到库非空（L0 只认"库非空"，不区分来源，但来源必须公开）。
- **run B = 对照轮 = `logs\longrun-runB.jsonl`**（同 0.7.32、同 5 天、同存档线的下一段）：同一 Mod、同一 brain，**唯一差异 = 注入的教训/笔记/决策史**（路径由 `--journal` 自动推导，没有新增开关）；两份 sidecar 的 `argv` 必须逐字对齐（除 journal 路径）。
- **不参与 A→B 对照的历史轮**：run9（`lessons.total=0`）、run9b（落盘 5/5 但买死锁/空转未修）、run9c（含 summer 20 "0 动作自称 VERIFIED"假达标日）、**run9d（0.7.31；尾部 0/5，两条结构性病灶由 task-157/158 修）** —— 它们只作诊断/素材，**不得**当 run A 的对照臂。
- run B 起跑前必须先从 run A 的账本+教训库导出「待验证教训清单」（`tools/compare-runs.py` 的 lessons 段 + `criteria` 段），**先写下预测再跑**（避免事后挑证据）。

## 1. 五条判定（全部要有原文读数）
| # | 判据 | 证据来源 | 通过条件 |
|---|---|---|---|
| **L0** | **run A 真有教训可注入**（前置，不满足则整条对照作废） | run A 的 `<journal>-lessons.json` 与 journal `lessons` 事件 | `lessons.total >= 1` 且至少 1 条 `count >= 1`。**只有 `count >= 1` 的条目算"可注入素材"**；0.7.37 前的旧库没有 `count` 字段 ⇒ 一律按 0 计并打 ⚠「旧库无 count，L0 只认总数」，不许把"没记录次数"说成"有进化素材"。`lessons.total == 0` ⇒ **直接写"run A 未产出教训，A→B 对照作废"**，不许拿"无教训"当"没有演进需求" |
| L1 | **教训确实被注入** | `<runB>-llm.jsonl` 的 prompt 原文 + journal `lessons`（`kept`/`loaded`） | **三信号同时上报**：`lessons_total`（A 库条数）/ `lessons_hits`（`hint` 整段子串命中数）/ `lesson_section_present`（教训节抬头出现）。**L1 分母只算决策行**：`-llm.jsonl` 里 `kind != "review"` 的行（review 行是夜间复盘，不是决策；先例 runB = 47 决策 + 1 review）；L1 成立 = 节在 且 命中 ≥1；命中 0 但节在 ⇒ 报「比对口径警告」，**不许**写"教训根本没送到" |
| L2 | **同形态不再出现** | 两侧 journal 的失败/取消事件按 `(kind, scope)` 聚合 | **严格三态**：`count_b < count_a` = 减少 ✅；`count_b == count_a` = 未变 ❌；`count_b > count_a` = 增加 ❌；**`count_a == 0 && count_b == 0` = 两边都没有（无可比）**，既不算"减少"也不算"没有演进"。只有"减少"项计入可比信号数。信号必须取自**现行账本形态**（`day_end.stages[].stopped/leftover`；0.7.37 起 `ended_by` 只有 sleep/sleep_failed，不再是 stuck 载体），并按教训 `scope` 优先匹配阶段名 |
| L3 | **决策可见地受影响** | `<runB>-llm.jsonl` 的 raw/`accepted` 意图 与 journal `decision`/`intent_verdict` | 至少 **1 条** run B 边界决策的 `intents` 或 `reason` 明确体现该教训（例：run A 反复 `cancel` 的意图在 run B 主动避开/换序），或守卫因教训改变了任务序 |
| L4 | **无回归** | `tools/verify-run3.py` + `tools/analyze-longrun.py` + `scratch/run9-lead-check.py` 原文 | 尾部窗口 = `--days`（默认 3，与验收窗口一致）内 run B 连续 VERIFIED 天数 **≥** run A；且无**新增硬失败类别**（只认 `HARD_FAILURE_CHECKS`：`no_hard_failures`/`no_unmet_stages`/`no_blocking_modal`/`watered_outdoor`/`unreachable_within_bound`/`refused_within_bound`/`day_justified`；`zero_action_evidenced` 这类非硬检查只作附注，不进 L4） |
| L5 | **诚实审计** | `tools/compare-runs.py` 输出 + `docs/_run10-evidence.md` | 门禁顺序 **L0 → L1 → L2 → L4 → L3 → 尾部达标**：任一不过即写"不足以判定自我进化（点名哪条不过）"；全部通过**且** `tail_b >= window` 才可写"有演进证据（正式结论仍需人工核对）"。逐条列出"注入了什么/出现几次/结局如何" |

### L1 的测量口径（**2026-10-17 事故后固化，必须双信号上报**）
- 量 L1 的工具是 `tools\compare-runs.py`。它的"取教训文本"口径**必须与 brain 落盘字段一致**：brain 写的是 `id/symptom/evidence/hint/count`，所以取文本按「`hint` → `lesson/text/summary/note/why/reason/symptom`」；**曾因只认 `lesson/text/...` 而退化成"把字段拼成长串" ⇒ 假报 `0/6`（"教训根本没送到"）**，而同一份留痕直查是 47/47 条决策提示词都含教训节 —— 教训：**工具自己数错的方向是"看起来没注入"，会直接把 A/B 对照判死**。
- 因此 L1 报告**必须同时给三个值**：`lessons_total` / `lessons_hits` / `lesson_section_present`（教训节抬头 `从过去几天的账本里总结的教训`）。命中 0 但节在 ⇒ 报**「比对口径警告」**（先查字段名/裁切），**不许**写"教训根本没送到"；节与逐条都没出现，才是真没送到。
- `lesson_hits` 是**子串命中**（注入后被预算裁掉的部分算未见）：run A/B 首选口径实测为 **4/6**（命中的 4 条 `hint` 整段逐字；未中的 2 条只 5 字符前缀偶然重合 ⇒ 疑"按形态按需筛选"，要单独核对渲染选择规则，不能算作"少注入"）。L3 的同指涉词表用 `lesson_full_text()`（症状+证据+自述），**不要**拿它做子串比对（会重演同一个事故）。

## 2. 反混淆（先说清，再跑）
1. **世界可比性**：run A 与 run B 的世界状态不同（这正是"继续玩"的语义）。若 run A 的教训来自**一次性**条件（例：某格当天够不着、某种天气），run B 不复现**不构成学习证据** —— 必须能找到"run B 面对同类可复现形态时行为不同"的证据，否则 L2/L3 记为【无法判定】。
2. **守恒前提**：run B 期间 Mod/brain 不许改（四要素 sidecar 必须对齐），否则对照失效。
3. **LLM 非确定性**：同一 prompt 不同采样可能给出不同意图。L3 只认"提示词里有该教训 **且** 该次决策的理由/意图与它相关"，**不认**"碰巧做对了"。必要时跑两次同形态对照并如实报告抖动。
4. **长度/预算**：教训注入 ≤3 条、notes ≤3 条、decision 史 ≤5 条（`Brief` 口径），预算挤干时按 核心 > 教训 > 决策史 > 笔记 丢弃 —— run B 的证据里要写清"这次到底注入了哪几条"。

## 3. 交付物
- `docs/_run10-evidence.md`：§1 起跑四要素（必须与 run A 同 Mod/同 brain，只有 journal 不同）；§2 两侧工具原文（`verify-run3` 的 `verdict` + `strict_verdict` 两行、`analyze-longrun --window` 默认口径）；§3 外部证据（存档 size/mtime、SMAPI 窗口冻结、`NewJourney`/`Save` 配对）；§4 **L1–L5 逐条**（附 `tools/compare-runs.py` 原文）；§5 反混淆与盲区；§6 结论（**要么给出可复核的 A→B 对照，要么写"不足以判定自我进化"**）。
- `tools/compare-runs.py` 的原文输出（含 lessons/hints/decision 三段）。

## 4. 与主目标的关系
- 主目标（用户 2026-10-17 改定**目标 2**）以 **run A（0.7.32，5 天）的小尾巴连续 5 个游戏日 VERIFIED + 四腿 + 经济闭环** 为准；历史轮只作诊断：run9（0/3）、run9b（首个整天全绿但尾部 0/3）、run9c（诊断性 3/3，含假达标日）、run9d（0/5，落盘 8/8 但两条结构性病灶 ⇒ task-157/158 修）。演进（L0–L5）是**同一目标里的能力项**，仍**不得**用"学到教训"替代达标判定，也不得用达标替代演进证据。
- 若 run A 达标而 run B 因世界条件退化而未达标，按 L4 如实记录，不掩盖、不重跑刷分（重跑必须写明是第几次、为什么）。

## 5. 测量规则（**2026-10-17 task-184 真机复测后固化**）
> 现行 A/B 已改到 **0.7.35 上的 A′/B′**（`logs\longrun-runA2-0735.jsonl` / `…runB2-0735.jsonl`，见 task-113 rev11）；上文 §0 的 0.7.32 行只作历史。**L0–L5 的判定逻辑不变**，但下面两条测量规则**必须遵守**：

1. **`worldSeq` 不是成功信号（R3）**：真机实测 `interact` 路径收获成功时 `worldSeq 60→60`（**不推进**；Mod 回执也如实写 60→60），而 `use_tool` 一次挥动 `65→67`。⇒ **任何判据都不许拿 `worldSeq` 前进当"动作成功"的证据**。成功证据只认这四类：①目标格 `ready` 由 `true→false`（或 `readySource` 变化）；②背包**逐 qid 计数**增加（对得上 `affected_tiles` 的 gained）；③`farm.readyCrops` 下降；④对照观测的 `TileSig` 变化。**失败的判据也不许用 `worldSeq` 未动**（否则会把失败判成功或反之）。
2. **回执 `ok` 仍不等于世界变了**（族里第三次教训）：`interact`/`use_tool` 都必须以「跨观测证据」为准（task-182 的 `acted`/`actedEvidence`，Mod 侧 `use_tool` 见 task-188 补齐）。报告中若出现「回执 ok 但世界未变」必须单列，不许并进成功计数。
3. **落盘/跨日口径**：跨日 ≠ 落盘（有 `displayedShippedItems` 时 `ShippingMenu` 会推迟 `SaveGameMenu`）；六串配对**必须成组出现**，缺组即如实写【无法判定】，不许按"存档 mtime 没变"直接判失败或通过。**逐字锚点（SMAPI-latest.txt 原文，按顺序）**：①`Synchronizing 'NewDay' task`；②`Context: before save`；③`SaveGame.Save() called`；④`Synchronizing 'Save' task`（即"Save task"串）；⑤`completed without exceptions`（另 `Saving without compression` 是 0.7.37 真机实测多出来的一行，`completed` 结尾另有 `task complete.`，两者都不单独当判据）；⑥`Context: after save, starting <season> <day>`。**一条命令出配对表**：`python scratch\_ab_save_pairs.py logs\longrun-runB-0732.jsonl`（任务 1 用法见 §7；输出每对编号 + 六串到齐/缺哪串）。历史脚本 `scratch\_t215_pairs.py` 只做全量计数，缺逐对配对，仍保留作对照。

## 6. 测量规则（**2026-10-17 A′ 叫停后固化，0.7.37 起生效**）

> 起因：A′（0.7.36）被「背包满 ⇒ `harvest` 全线被拒」支配，`no_hard_failures=false` 整天、守卫拿 farm 级计数空转 `stuck`（`docs\_runA3-0736-evidence.md`）。这三条是**判据层**的修正，不替代硬验收。

1. **「背包满」不是硬失败（task-198）**：无空格 ⇒ 阻塞类（`no_slot` 同族），**不进 `failed_steps`/`no_hard_failures`、不吃 `harvest_gave_up` 上限、不封格**；报告里单列「背包满阻塞次数」，与「真失败」分开。若某天因此无法 VERIFIED，`ended_reason` 必须写**可执行**的原因（"背包满、需先腾格/出货"），**不许**写成"没干活"。
2. **守卫的「还有活」必须能落到可执行目标（task-199）**：`work_reasons()` 给出的每一条理由，都必须能对应到**具体可执行目标**（坐标/指派阶段）；farm 级计数（`readyCrops` 等）只能当**线索**，不能单独作为"还有活"的证据 —— 否则会像 A′ day13 那样空转 `stuck`。窗口外目标要么有坐标可走过去（`readyTiles` 一族），要么如实记 `*_far_blocked` 并**不进入**"还有活"。
3. **sell 白名单归因分两通道（task-193/196）**：作物白名单（`whitelist_source="crop_product"`，只收本格作物产物 id；取不到 crop id ⇒ 空白名单 + `unavailable`，**宁可少挣、不许乱卖**）与材料白名单（盈余材料换种子钱，`task-55`）**必须分列统计**；连带掉落（`collateral_loot`）不许进作物白名单。任何"白名单里出现与目标格无关 qid"都要单列为 ⚠。

## 7. task-217 修订记录（2026-10-18，源自 task-215 审计）

> 起因：task-215 只读审计（`docs\_audit-ab-criteria.md`）发现 7 处「文档 ↔ `tools/compare-runs.py`」实施偏差。本节记录**代码与文档同步修订**后的口径；代码 = `tools/compare-runs.py`（704 行），测试 = `tests/test_compare_runs.py`（34 条）。

### 7.1 七项修订（对应 §1 表的行）

1. **L0**：代码改成 `lessons_total >= 1` **且**「至少 1 条 `count >= 1`」。旧库无 `count` 字段 ⇒ 按 0 计并打 ⚠（不伪装成有素材）。
2. **L1 分母**：`-llm.jsonl` 的行按 `kind` 分为**决策行 / review 行**；L1 的调用集与命中**只算决策行**，review 数单列（`b_review_calls`/`a_review_calls`）；旧行无 `kind` ⇒ 按决策行（兼容旧格式）。L1 成立 = `lesson_section_present` 且 `lessons_hits >= 1`；节在而 0 命中 ⇒ 只报「比对口径警告」。
3. **L2 严格三态**：`减少 / 未变 / 增加 / 无可比（0→0）`；只有"减少"计入可比信号。信号表改按**现行账本形态**多候选（`day_end.stages[].leftover` / `stopped=incomplete`；`ended_by:stuck` 只兜底），并按教训 `scope` 优先匹配阶段名；另补 `dead_crops_blocking → day_dead_crops`（run A 真实教训 kind，旧表漏映射）。
4. **L4 窗口与硬检查**：尾部窗口 = `--days`（默认 3，与验收窗口一致）；"新增失败类别"只认 `HARD_FAILURE_CHECKS`（7 键），`zero_action_evidenced` 这类非硬检查降为**附注**（`other_new_false_checks_in_b`）。
5. **L5 门禁**：顺序 **L0→L1→L2→L4→L3→尾部达标**；L3 不过时同时点名「run B 尾部连续 VERIFIED n < window」；只有全过且 `tail_b >= window` 才可写"有演进证据"。
6. **恒退码**：统一「读不到/读坏账本或 sidecar ⇒ **rc=2**；其余恒 **rc=0**」——删掉旧的 `raise SystemExit("[exit 2] …")`（它实际 rc=1 且文案误导），改 `LedgerReadError` → 打印 + `return 2`。
7. **`--json`**：结构化结果新增窗口/门禁/三态等字段（`l2_signal_states`、`l5_gates` 等），便于证据文档直接引用。

### 7.2 实测读数（2026-10-18，runA-0732 → runB-0732，`--days 3`）

- L0 ✅（6 条；`count>=1` True）；L1 ✅（**4/6** 命中，run B **70 次决策调用**，另 2 次 review 不计入）；L2 ✅（**6 条可比信号**：harvest leftover 79→71、plant_area 1→0、till_area 1→0、stage_incomplete@harvest 79→71、`dead_crops_blocking` 4→0、water_area 4→1；**旧版曾打三行 `0→0 ✅ 减少` 的假阳性**）；L4 ✅（尾部 runA=0 → runB=0；新增非硬 check `zero_action_evidenced` 只作附注）；L3 全部 0 次旁证；L5 =「**不足以判定自我进化**（L3：没有任何决策受影响的旁证）；且 run B 尾部连续 VERIFIED 0 < 3 天」。
- 单测：`tests.test_compare_runs` **34 OK**（原 23 + 新增 11）；全量 `discover -s tests` **Ran 1055 / OK（0 红）**。
- **A″/B″ 提醒**：现行 A″/B″（`runA2/runB2-0735`）的 `-llm.jsonl` sidecar 在本机**缺失** ⇒ 对其跑 L1 会得到"读不到留痕"（预期路径缺失 ≠ 没注入）；Lead 重跑前需补齐 sidecar，否则 L1 只能标【无法判定】。

## 8. 意图-执行对账口径（2026-10-18 固化，`User said (m18972)`，0.7.39 起生效）

> 起因：LLM 明确要求 `clear_area`（简报里树就是障碍），而实现层 `SKIP_KINDS` 静默跳过树 —— **没有任何一条判据发现"意图被无声缩水"**，这个缺口活了十几轮。本节把"每个 LLM 意图都必须有执行对账"固化成判据；实现卡 = task-219（brain）、task-220（analyzer）。

### 8.1 数据形状（三个**挂载点**，不是新事件名；2026-10-18 按 task-219/220 实现与 task-232 对账修订）

1. **`decision.plans[]`**（挂在既有 `decision` 行上的字段）—— 每个意图 `{intent_id, task, area_hint, source(deterministic|llm), boundary}`；`intent_id = "<day_key>#<seq>"`。
2. **`day_end.intent_coverage[]`** —— 当天每个意图的执行对账 `{intent_id, task, requested_tiles, ok_tiles, failed_tiles, unexecuted_tiles, executed_steps, reasons:{code:count}, area_hint, source, boundary, reasons_are_intent_level}`；**不新增 checks 键**。
3. **`<journal>-gaps.json`**（旁车文件，schema `agentfarm-gaps/1`）—— 缺口清单按 `(kind|capability, tool, reason)` 聚合 `count/first_seen/last_seen/sample_tiles`；**per-run 隔离**，跨 run 聚合由工具侧只读生成 `logs/gaps-registry.json`。

**关键字段（analyzer 判红依赖，改名会静默失效 ⇒ 必须有源码漂移测试）**：`reasons_are_intent_level`（区分 intent 级 vs 瓦片级口径）、`bad_reasons`（集外码不丢、专供判红）、`actionless`（无动作意图标记）。

### 8.2 固定原因码枚举（闭合集，出现集外值 ⇒ 判红）

目标集合 **12 码**：`no_target` / `unknown_evidence` / `superseded` / `deferred_capability` / `tool_level` / `budget` / `blocked_tile` / `blocked_modal` / `no_slot` / `world_stuck` / `gated` / `failed`。

- **现状（2026-10-18）**：brain `INTENT_REASON_CODES` 是 **11 码**，缺 `failed`（由 task-230 补齐）⇒ 本文件只把 `failed` 标为「新增」，`unknown_evidence`/`superseded` 在 task-219 已落地；
- **`no_target`** 必须附证据 `{stage_tiles_empty: true, obs_seq | counts 快照}`；`tiles` 缺失/截断/证据不可用 ⇒ **禁止裸用**，改用 `unknown_evidence`；
- **`unknown_evidence`**：观测不可用/被截断/字段缺失导致判不了 —— "没证据"≠"没目标"；
- **`superseded`**：策略层改写/合并意图（`_apply_policy`）导致该意图未执行 —— 与 verify 的 `cancel`（归 `no_target`）分开；
- **`failed`**（新增）：执行了但真实失败（`tool_ineffective`/`sow_failed`/`no_seed`/中途体力耗尽等）—— 必须有**完备映射表**（单一数据源 + 漂移测试），映射不到的 step 状态码 ⇒ 判红（漏码即缺陷）；
- `deferred_capability` 必须同时在 `DEFERRED_KINDS`；「简报如实写暂不支持」这条**由 brain 单测守**（analyzer 读不到提示词，日志层不可判）；
- `budget` / `gated` 属策略性延后：**不进 hard failure**（gaps/次日简报可见性由 brain 单测守）；
- 一个意图可以有多条原因码（按环节累计），但**不许 0 条**。

### 8.2b 计数单位与不变式（瓦片制）

- `requested_tiles = ok_tiles + failed_tiles + unexecuted_tiles`；
- `Σ reasons.count = failed_tiles + unexecuted_tiles`（`reasons.count` 按**瓦片数**计，不按 step 数；intent 级原因码记 `reasons_are_intent_level: true` 时按 0 瓦片计）；
- 对不上 ⇒ 判红（账目不可信）。

### 8.2c ACTIONLESS 白名单

`sleep` / `review` / `wait_for_save` / `recover_stamina` 这类**无动作意图**在 `_verify_intents`（`brain/agentfarm/longrun.py:6314` 附近）不产生 verdict ⇒ 必须显式列入 `ACTIONLESS_TASKS`，否则 §8.3.2 会**每天误报**。不在白名单的任务一律按有动作意图对账。

【task-238 兜底回填语义】日终 `_finish_intent_coverage()` 会对 `executed_steps==0 && reasons=={}` 的意图按当天收尾原因补一个**闭合集**原因码（`inventory_blocked→no_slot`、`blocked_modal→blocked_modal`、`blocked_event→gated`、`stuck*→world_stuck`、夜里/体力收工→`gated`、其余→`unknown_evidence`），`evidence.why="finalize_fallback"` 且带当天 `ended_by` 原文。**回填只补原因码**：不改 `executed_steps`、不改 `checks`、不改 `verified`、不做任何豁免 —— 它不是洗白通道（否则等于把"实现漏记"变成"理由充分"）。

### 8.3 analyzer 判红（task-220 实现 + task-232 对齐后，硬性 9 条）

1. 有意图计划而**无** `intent_coverage` 条目 ⇒ 红（对账缺失）；
2. `executed_steps==0` 且 `reasons` 为空（且非 ACTIONLESS）⇒ 红（无声缩水）；
3. `reasons` 含集外码（`bad_reasons` 非空）⇒ 红；
4. `deferred_capability`/`tool_level`（能力缺口）而 `<journal>-gaps.json` 无对应条目 ⇒ 红（缺口没落盘）；
5. gaps 条目里的 `kind` **不在** `DEFERRED_KINDS` ⇒ 红（登记表与缺口不一致；**注：原稿「DEFERRED_KINDS 里的 kind 出现可执行目标却一次没执行 ⇒ 红」语义不同，属另一件事，暂记待实现，见 §8.6**）；
6. 瓦片不变式不符（§8.2b 两条）⇒ 红；
7. `no_target` 无 `evidence.stage_tiles_empty` ⇒ 红；
8. 同 `(kind, reason)` 连续 **≥3 天**出现在 gaps 且无修复卡 ⇒ **⚠**（Lead 复核，不自动判红）；
9. 旧账本没有这些字段 ⇒ 【无法判定】（缺失 ≠ 通过，也不许当失败）。

### 8.6 待实现（记入 backlog，不在 0.7.39）

- 「`DEFERRED_KINDS` 里的 kind 出现可执行目标却一次都没执行 ⇒ 红」—— 需 brain 侧导出"每类 kind 是否产出过可执行目标"的证据，0.7.40 再评估（与 task-151/221 的田区工作一起）。

### 8.4 次日可见（只提示，不豁免）

`Brief.recent_gaps` 最多 3 条、总长 ≤200 字符，渲染在核心行之后；**裁剪优先级：核心 > 教训 > 决策史 > 复盘 > gaps（最先裁）**。gaps 只影响提示词，**不进 `checks`、不做豁免额度、不改 `_leftover`**（沿用 `scope_shed` 的"裁撤 ≠ 免罚"口径）。

### 8.5 与"目标 1/2"的关系

- 目标 1（指定作业区清空）：护栏 A/B（task-218）保证"说得出、做得到"；本节保证"做不到必须说清楚"。
- 目标 2（策略闭环）：`intent_coverage` + gaps 是"结果校验 → 据结果优化"的**事实基座**；没有它，L0–L5 里的 L3（决策受教训影响）无法取证。

## 9. `clear_area` 有效性口径（task-218 固化，0.7.39 起）

> 起因：`User said (m18938)`「树已经多到影响种植了，先升级斧子砍树」+ `User said (m18962)`「脑侧从来没砍过树」。旧实现 `farmwork.SKIP_KINDS` 把 `tree` 静默跳过，而简报把树算进 `blockers` ⇒ LLM 一直要求清障、实现层一直不砍。task-218 起普通树可砍（0 级斧），但"砍"必须可验收。

### 9.1 能力覆盖（护栏 A）

`planner.OBSTACLE_KINDS ∪ farmwork.CLUMPS_KINDS` 里每一类必须满足二者之一：

1. **可执行**：只含该类障碍的合成观测喂 `farmwork.clear()` 能产出 ≥1 个动作（或明确 skip 原因）；
2. **显式登记**：在 `planner.DEFERRED_KINDS` 里登记"理由 + 缺什么能力"，且 `Brief.situation_text()` 如实写「<kind> 存在但暂不支持清理（原因）」。

**静默跳过不允许**：登记了却不告知 = 判红；漏登记某 kind ⇒ 覆盖矩阵测试必须红。当前登记：`fruitTree`（砍掉会毁果树产出，需玩家确认）、`bush`（留浆果，归余力多清）。

### 9.2 有效性（护栏 B）

`clear_area` 阶段记录里：

- `blocker_drop = farm.blockers(阶段开始) − farm.blockers(阶段结束)`（farm 证据不可用 ⇒ `null`，**不许当 0**）；
- 有 `ok` 步、却**既没有目标格障碍消失、`blocker_drop` 也不为正**、且不是预算/工具挡下 ⇒ `stopped="incomplete"`、`met=False`，并记一条 `stage_stop_named`（带 `blocker_drop`）。

**"挥过刀"不算清障有效，判据是"目标格障碍消失"或"farm.blockers 真降"。** 这项只收紧"有效性"的如实记账，**不新增 `checks` 键、不改 `_leftover`/`JUSTIFIED_END_REASONS` 语义**。

### 9.3 体力预算（树是唯一受日预算约束的清障对象）

- `TREE_CLEAR_MAX_PER_DAY=2`，且 `体力 − 浇水预备 > TREE_STAMINA_ESTIMATE(100)` 才准砍；
- 预算挡下的树：不进目标池、不算"还有活"、不算 leftover（延后 ≠ 未完成），**不记 hard failure**；
- 每天至多一条 `deferred_by_budget{task:"clear_area_tree"}`（**复用既有事件名**，不新增桶）。

### 9.4 与目标 1 的关系

"大模型指定的作业区清空"（task-151 rev5）要求区内障碍证据链；本节给出 `clear_area` 侧的"有效 = 障碍消失"判据，二者必须同口径，否则又会出现"账上说清完了、地里还有树"。
