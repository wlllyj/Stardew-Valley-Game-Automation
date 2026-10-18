# 产品面旁观审计：0.7.44 真机冒烟（winter 26/27）+ A8 十二天账本

> 角色：product-observer（旁观审计），**不做代码验收、不改代码、不碰游戏**。
> 权限：只读 `brain/ mod/ tools/ tests/ docs/`；只写本文件与 `scratch/product-observer/`。
> 本报告喂给 Lead 排卡，不替代 deputy-lead 的 `docs/_review-0.7.44.md`（验收权威）。
> 全部数字来自两本账本 + 只读代码 + 复跑脚本；无法核实的写【无法判定】，不猜。

## §0 审计范围与复现

| 输入 | 规模 | 用途 |
|---|---|---|
| `logs/longrun-runA8-0743.jsonl` | 1322 行，winter 7–18 共 12 天 | 策略/经济/判据主样本（A8 失败臂） |
| `logs/longrun-smoke-0744.jsonl` | 234 行，winter 26/27 共 2 天 | 0.7.44 冻结装机现状 |
| `logs/longrun-smoke-0744-llm.jsonl` | 4 行（2 decision + 2 review） | **LLM 实际看到的 prompt 原文** |
| `logs/longrun-smoke-0744.console.log` | 58 行 | 真机形态、校验取消原文、收工原文 |
| `brain/agentfarm/{longrun,farmwork,planner,llm}.py` | 只读 | 行为与状态注入事实 |
| `tools/analyze-longrun.py`、`tools/verify-run3.py`、`tools/compare-runs.py` | 只读 | 判据覆盖度 |

复跑脚本（我在 `scratch/product-observer/` 建的三支只读探针，均用 DSH python + `PYTHONUTF8=1`）：

```
probe_dump.py   # 按 event 名 dump 原始 JSON
probe_days.py   # 按 day 分组：LLM intents → intent_verdict → outcome → review_llm → day_end
probe_end.py    # day_start/day_end/review_llm/policy/tool_upgrade_skipped 全量读数 → end-reads.txt
```

口径说明：
- 代码行号钉在**审计时工作树快照**（HEAD `4cb6721` + task-15 在制改动）；task-15 提交后行号会漂，关键点一律同时给函数名（`sleep_guard`/`_pending_snapshot`/`is_justified_end`/`_review_facts` 等），以函数名 grep 为准。
- `A8 Lxxx` = `logs/longrun-runA8-0743.jsonl` 的第 xxx 行；`smoke-llm.jsonl:N` = 该文件第 N 行（1=冬26 decision，2=冬26 review，3=冬27 decision，4=冬27 review）。
- LLM 意图归属口径：`decision.source=llm` 的 12 条 × 3 条意图 = 36 条，意图 id 为 `<day>#01..#03`；其中 33 条进了 `_verify_intents`（`review` 类不进）。

关键事件计数（我自己重跑核对，非引用）：

| 事件 | A8（12 天） | 冒烟（2 天） |
|---|---|---|
| `sell` / `ship` / `ship_loot` / `harvest` / `pickup` | **0 / 0 / 0 / 0 / 0** | **0 / 0 / 0 / 0 / 0** |
| `inventory_blocked` / `slot_relief` | 0 / 0 | 0 / 0 |
| `buy`（均为失败） | 1 | 1 |
| `no_seed_for_sale` | 12 | 2 |
| `tool_upgrade_skipped` | 12 | 2 |
| `policy` | 4 | 2 |
| `no_progress_burst` | 3 | 1 |
| `decision` 中 LLM 来源 | 12（每天仅 1 次） | 2 |

---

## §1 结论速览（给 Lead 排卡用，按严重度排序）

| # | 现象（一句话） | 证据 | 影响 | 建议动作 | 置信度 |
|---|---|---|---|---|---|
| 1 | **判据奖励"不干活"**：12 天里 7 个 VERIFIED 日（winter 8/10/11/13/15/16/17）**全部**是 `no_work` 早收工，07:10–11:00 就睡、体力剩 70–161；且 0.7.44 冻结树 `sleep_guard` 只要 `work_reasons()` 为空就走 no_work（无"账本还剩挡死格"拦截） | `logs/longrun-runA8-0743.jsonl` day_end L240/533/553/606/1225/1250/1285；`brain/agentfarm/longrun.py:5535`（`if not reasons:` 之后才判 no_work）；挡死格拦截 `:5540-5544` 是 task-15 在制新增，0.7.44 冻结树无 | **目标 2 判据失效**：5 天 streak 可由"没活干"刷出；A9 门禁同样失真 | 补进 task-15：`no_work` 必须并列 `pending_*` 快照，"挡死格>0 或 unobserved>0 就不许 no_work"；`verified` 另加"当天有 ≥1 个作业阶段做成" | 高 |
| 2 | **263/217 归属分裂**：守卫说"还有 263/217 格没做完"，当天阶段账却是"做成 71 跳过 0 失败 0、片区待做 0、走不到 16（豁免界 21）" | `logs/longrun-smoke-0744.console.log:26`（263）与 `:37`（217）；`logs/longrun-smoke-0744.jsonl` day_end 两条 `day_justified=false` | **0.7.44 不可放行 A9/B9**（已知卡点） | 已由 task-15 在制（`_pending_snapshot` 三分 executable/blocked/unobserved）；验收必须用"独立观测差分"复算 263/217 | 高 |
| 3 | **背包满无感知三出口全开**：(a) 清障掉战利品在满包时丢失且**无任何事件**；(b) 买种子在满包时死锁（run8 已实证 25×`no_inventory_space`）；(c) 存档 12 格全满 = 春季买种/收获/升级材料三条腿都会被堵 | `brain/agentfarm/farmwork.py:2298-2570`（`clear()` 体内无 `free_slots/inventory/no_slot` 判定）对照 `:2997-3010`（harvest 有 `NO_SLOT_CODE`）；`docs/_run8-evidence.md:173`；容量语义 `farmwork.py:25-27/1353`（`inventoryCount` 是容量）；两本账本 `free_slots` 从未落值、事件表 0 条 sell/slot_relief/inventory_blocked；12 格全满来自存档摘要（用户给定，逐格构成见 §6-4），用户真机另见原生红 X「Inventory Full」（用户观察，本审计未复现） | **目标 1 立刻炸（春季）**；目标 2 的"清障日"持续静默丢资源 | task-16 扩围（见 §5-A2）：补 `loot_lost` info 事件 + 清障前置 free_slots 判定 + 买种前腾格 + **背包升级 2000g 优先级重估** | 高 |
| 4 | **经济面 12 天零变化**：钱恒定 2767g，`sell/ship/harvest` 全 0，`crops=0`，工具全 level 0；`TASK_KINDS` 12 种里**没有** buy/sell/upgrade/mining（`ship` 只运"亲手收获的东西"，无收获即永不触发） | `probe_end.py` 读数：12 天 day_start money=2767；事件计数表；`brain/agentfarm/planner.py:101-114` | **目标 1（经济与升级平衡）无数据面**；目标 2 即使 5 天全 VERIFIED 也不证明"经济闭环" | 新卡（经济腿）或并入 task-16；LLM 不给经济动作权限，由确定性腿驱动 | 高 |
| 5 | **目标 1 升级路径冬季结构性不可达**：5 铜锭需 25 铜矿 + 5 煤，手头 1 铜矿 0 煤；brain **无矿洞/采矿腿**、**无买矿 caller**、`Clint` 只出现在升级/取回路径；且 `tool_upgrade_skipped` 每天固定串，三种成因不可区分 | `grep` 全 `brain/` 无 Mines 能力（仅 `brain/data/crops.json:361` 数据串、`fields.py:270` 注释）；`farmwork.py:416-433`（2000g+5 铜锭）、`:1467-1473`（熔炉 20 铜矿+25 石）、`:3772/:3867`；`longrun.py:6305-6313` 固定串（`plan is None` ⇒ 三种成因一句「钱/材料不够，或工具等级读不到，或已满级」）；A8 12 条 `tool_upgrade_skipped{which=None,money=2767}` | **目标 1 阻断**（"至少一次真实工具升级"冬季做不到） | task-14 应**提前**（现 `blocked_by task-8` 不合理）；先评估"Clint 卖矿→熔炉→升级"最省路径 + 背包升级 | 高 |
| 6 | **LLM 输入缺关键状态 + 面积口径矛盾**：Brief 无空槽/容量、无工具等级与升级缺口、无种子名称与当季可种性 ⇒ 模型把 **483（Wheat Seeds）说成"10 份冬季种子"** 并据此下 `plant_area/water_area`；同一 prompt 里 `counts.tillable=18`（窗口）与田区行合计"可锄 181"（全片）并存 | prompt 实证 `logs/longrun-smoke-0744-llm.jsonl:1`（`inventory_items=12 seeds=['483'] seed_count=10`，无 name/无 capacity）；`brain/agentfarm/planner.py:1553-1580`（base_lines 字段表）、`:1803`（`inventory_size=len(inventory)`）、`:1749-1750`（`counts["tillable"]` 只数观测窗口）；`logs/longrun-runA8-0743.jsonl` L1257（w17 reason 原文，同一句内互斥） | 策略局限，但有产品修法；导致 8/12 天把体力花在冬季无效的 till/plant/water | 新卡"策略输入注入三件事"（§5-A3） | 高 |
| 7 | **意图被校验取消后无纠错回路**：取消只写 journal reason（例：w18 `reduce_scope@anchor:field_ne` →「观测里找不到田区「anchor:field_ne」」），次日 prompt 只有 `verdicts=keep1/cancel2` 计数，**没有 reason 文本** | `logs/longrun-runA8-0743.jsonl` L1292（w18 decision）与 L1293（verdict 原文）；`logs/longrun-smoke-0744-llm.jsonl:3`（次日 `recent_decisions` 只有计数）；校验点 `longrun.py:7690 _verify_intents` | 同一错误可无限重复（12 天里 till/plant 同构 8 次；w18 的收窄尝试一次就废） | 新卡或并入 task-15："cancel reasons 摘要进次日 prompt" | 中高 |
| 8 | **复盘看不到真卡点**：两次 review prompt 的"当天事实"`ended_by=未观测到、ended_reason=未观测到`；复盘在睡前跑（day_end 尚未生成） | `logs/longrun-smoke-0744-llm.jsonl:2` 与 `:4`；`longrun.py:4287 _review_before_sleep`、`:4230 _review_facts`（字段 `ended_by/ended_reason` 在 `:4237-4238` 有，但复盘时尚未定稿 ⇒ 值为空） | review 笔记只能泛泛（12 条多为"别砍果树/不用浇水"），学不到 263/217 | 新卡（P2）：day_end 后补"昨日终局事实"进次日 prompt | 中 |
| 9 | **冬季农务面结构性不可判**：12 天 `crops=0`，`water_area` 永远无目标、`harvest` 永不发生 ⇒ L2/L3 的"同形态下降"在冬季没有可测面 | day_start `crops=0` ×12；`docs/00-开发日志.md:90` 待决① | **L0–L5 对照**在冬季尾巴上不成立；A9 的 5 天若含 spring 1–5 才可能测 | Lead 决策：对照窗口必须覆盖春季播种日 | 中高 |
| 10 | **测量盲区**（不是产品缺陷，但会让判据"看起来通过"）：analyzer 无"背包满丢战利品""当日 LLM 有效意图=0""连续 N 天 0 收入""`pending_*`"聚合；`bag` 聚合在无 sell 证据时只能写【无法判定】 | `tools/analyze-longrun.py:4342-4343`、`:2246-2268`、`:4661-4663`、`:6970-6996` | 0.7.45 重冒烟会被同款盲区放过 | task-17 补 3 个聚合（info 级，不进 rc） | 中 |

---

## §2 大模型冬季每日策略审计（用户最关心）

### 2.1 事实：LLM 每天只被问 1 次

`planner.py:2420-2483` `decide()` 只在边界调 LLM；A8 12 天 `decision` 事件 164 条，其中 LLM 来源**恰好 12 条**（每天 `new_day` 一次），其余 152 条全是确定性/兜底。
即：**"LLM 策略闭环"实际上是"每天一句任务清单（3 条意图）+ 152 次确定性重决策"**。这决定了下面判"合理性"要看的是"清单质量 + 清单是否被采纳 + 采纳结果是否回流"，而不是逐动作智能。

### 2.2 逐日表（12 天，A8）

| 日 | decision 行 | LLM 三条意图 | verdict | 日终（ended_by / 时刻 / 体力 / 阶段 ok） | 判读 |
|---|---|---|---|---|---|
| 冬7 | L8 | `clear_area@field_ne` / `till_area@field_ne` / `plant_area@field_ne`（reason 引"7 格待清理""10 份种子"） | keep1 / cancel2 | sleep 1100 / 73 / 46 | till+plant 冬季无种子可买，被取消；当天仍 FAIL（回片区 149 格） |
| 冬8 | L148 | `till_area@field_ne`（"体力已回满…可锄格最多"）/ `plant_area@field_ne`（"先试播一小片验证冬季能否出苗"）/ clear | keep1 / cancel2 | sleep 1100 / 106 / 69 | **意图本身违反季节常识**（winter 试播）；靠确定性 `seed_gate` 兜住 |
| 冬9 | L247 | 同构三条，但 `zone=field_se`、意图全写 `field_ne` | keep1 / cancel2 | **stuck** 840 / 167 / 21 | 区域与作业区不一致；FAIL |
| 冬10 | L525 | `till` / `plant` / `clear@field_ne` | cancel2 / keep1 | sleep 800 / 70 / 12 | 无新信息，重复前日 |
| 冬11 | L540 | `clear@field_ne` / `clear@field_nw` / `review@farm`（reason 明说"冬季不能播种…先做能跨季保留的清理"） | unknown2 | sleep 720 / 148 / 12 | **首次正确适配季节**（丢掉 plant） |
| 冬12 | L560 | `clear@field_ne` / `clear@field_nw` / `review@farm` | unknown2 | sleep 710 / 175 / 13 | 沿用正确形态；但仍 FAIL（回片区 216 格） |
| 冬13 | L588 | `clear` / `till@field_ne` / `plant_area@tiles.plantable` | unknown3 | sleep 730 / 148 / 12 | **回退**（又下 till+plant）；`seed_gate: plantable=0, out_of_season=["Wheat Seeds"]`（L592/L597） |
| 冬14 | L615 | 同构 till/plant + `tiles.plantable` | unknown3 | **stuck** 1020 / 139 / 45 | 73 次 decision、65 次 clear 需复核；FAIL |
| 冬15 | L1207 | 同构三条 | unknown3 | sleep 720 / 144 / 12 | 收到 seed_gate 后仍下 plant |
| 冬16 | L1232 | `clear@anchor:field_ne` / `till` / `plant@tiles` | unknown3 | sleep 710 / 161 / 12 | 开始用 `anchor:` 写法（w18 因此被取消） |
| 冬17 | L1257 | `till` / `plant_area@field_ne` / `water_area@field_ne`，reason 称"**背包里有 10 份冬季种子（483）**；field_ne 可锄 183 格" | unknown3 | sleep 740 / 137 / 16 | **事实错误**：483=Wheat Seeds（out of season）；`water_area` 在 crops=0 下无意义；同一 reason 里又写"当前没有任何耕地（dirt=0、tillable=0）"——**自相矛盾的口径** |
| 冬18 | L1292 | `reduce_scope@anchor:field_ne` / `clear@field_ne` / `review@farm` | cancel1 / unknown2 | sleep 740 / 124 / 19 | 唯一一次尝试收窄范围，**因 area 非法被取消**；FAIL |

逐日 VERIFIED = F/V/F/V/V/F/V/F/V/V/V/F（7/12，最长 3 连，尾部 0/5，与 `docs/_analyze-A8.md` 一致）。
**7 个 VERIFIED 日全部是 `no_work` 早收工**，无一日来自"把活干完"。

### 2.3 合理性判据（六条，逐条给判）

**判据 A：季节/能力一致性**
判：**不合格，但被确定性层兜住**。含 `till/plant` 意图的有 8/12 天，`water_area` 出现在 crops=0 的冬17。冬季 SeedShop 在售清单无 472（`no_seed_for_sale` 12/12；`console.log:6` 原文"商店「SeedShop」里没有「472」"），所以 plant 必然落空。winter 8 的 reason 直接写"先试播一小片**验证冬季能否出苗**"——这是**拿体力做假设实验**，产品上应由状态注入（`plantableNow`）阻止，而不是靠 `seed_gate` 事后取消。

**判据 B：是否重复下达被校验取消的意图**
判：**是，且无学习**。36 条 LLM 意图中 33 条进了校验：`keep 4 / cancel 9 / unknown 20`（另 3 条是 `review` 类不进校验）。cancel 全是 till/plant（w7/8/9/10 各 2 条）+ w18 `reduce_scope`。同一形态 4 天重复；`unknown` 的原文是"作业区离玩家 N 格，观测看不见，先走过去再看"（如 w17 三条全是「离玩家 29 格」）——即 **61%（20/33）的意图连可行性校验都没过，直接盲走**，走到地方后再由确定性层重决策。`policy` 事件的自动收窄只覆盖 `clear_area`（4 条 note 均为"今天不再要已证明没目标的任务 ['clear_area']"），**不覆盖 till/plant**——因为 till/plant 是被 `_verify_intents` 取消而非"做不下去"，两条路径没汇合。

**判据 C：是否考虑体力/背包/工具等级/材料**
判：**体力部分考虑（review 笔记反复提），背包/工具/材料完全不可见，且面积口径自相矛盾**。`Brief.base_lines` 字段表 `planner.py:1553-1580` 实测 prompt（`smoke-llm.jsonl:1`）只有 `inventory_items=12`（=使用行数，`planner.py:1803` 的 `len(inventory)`）、`seeds=['483']`（**无名称、无是否当季**），**没有容量、没有空槽、没有工具等级、没有升级材料缺口**。12 天里 LLM 从未提及"背包满"（因为看不到）。工具升级同理：`TASK_KINDS` 没有 upgrade 类，模型连表达都没有词。
另实测一处**口径矛盾**：同一 prompt 里 `counts.tillable=18`（观测窗口内可锄，`planner.py:1749-1750`）而四个田区行合计"可锄" 42+86+5+48=**181**（全片区）；A8 冬17 的 reason 于是同时写出"当前没有任何耕地（dirt=0、tillable=0）"和"field_ne 可锄 183 格"两句互斥的话。这会直接误导面积/体力预算。

**判据 D：是否依据前一日结果调整（闭环是否真闭合）**
判：**半闭合，且会回退**。正面：文本反馈链路**确实接通**——冬27 的 prompt 比冬26 多出 `lessons`、`recent_decisions`（含 verdict 计数）、`recent_notes`（3 条复盘笔记）、`recent_gaps` 四节（`smoke-llm.jsonl:3`，1445 字符 vs 860），说明 `longrun.py:4319/4321` 的 `recent_notes→lessons_hints` 生效。反面：(1) 冬11/12 适配正确后，冬13 又退回 till+plant；(2) reviewer 在冬15/16 说"冬天不用浇水/浇水不是主线"，冬17 仍下 `water_area`；(3) `recent_decisions` 只有 `keep1/cancel2` **计数**，没有取消原因，模型无法知道"为什么被否"；(4) 复盘的 `ended_by/ended_reason` 两日均为"未观测到"（`smoke-llm.jsonl:2/:4`），模型学不到 263/217 这个真卡点。

**判据 E：review_llm 笔记是文案还是约束**
判：**是文案 + 提示词，不是约束**。代码自述 `longrun.py:4331` `note="只写 journal 与次日 recent_notes；不参与任何判定"`；`planner.py:1500-1503` 同样写"只影响**提示词文本**，绝不参与任何判定"。唯一"变成约束"的机制是确定性 `policy`（`longrun.py:7772`），它由阶段账本触发，与 review 笔记无关。12 条笔记的内容也确实停在"别砍果树/不用浇水/先留体力"，没有一条转成次日 gating（grep 12 天无任何 `policy` 涉及 plant/till）。

**判据 F：意图区域与当日作业区是否一致**
判：**不一致**。w9/w14/w16 的 `zone=field_se` 但意图全指 `field_ne`；w18 用 `anchor:field_ne` 这种不在合法前缀表里的写法（`planner.py:160-162/174-180` 只接受已观测前缀/具名田区/合法锚点）⇒ 唯一一次范围收窄被取消。A8 里 `idle 93`、`goto_farm 13` 事件佐证跨区走路消耗。

### 2.4 这个循环离「L0–L5 演进对照」成立还差什么

| 层 | 现状 | 缺口 |
|---|---|---|
| L0 教训库非空 | 12 天 `lessons` 事件齐全，`added` 有 `unreachable\|clear_area`、`encircled\|clear_area` | **已达成** |
| L1 教训进 prompt | `smoke-llm.jsonl:3` 有 `lessons`/`recent_notes`/`recent_gaps` 节 | **已达成**（文本层） |
| L2 同形态下降 | 12 天形态未下降（FAIL 5 天 = `stuck` 2 天 + 回片区 3 天，`no_progress_burst` 3 次），且**冬季无农务面可测**（crops=0） | 缺可测面 + 缺 A/B 两臂同窗对照 |
| L3 决策体现教训 | 仅 1–2 处可指认（冬11/12 去 plant），随后回退 | 缺"取消原因/终局原因"输入，模型只能靠文案悟 |
| L4 无回归 | 12 天 VERIFIED 7/12、尾部 0/5 | 判据被 `no_work` 灌水（§1-1），"无回归"不可信 |
| L5 尾部达标 | 最长 3 连（冬15–17），且这 3 天全是 `no_work` 早收工 | 5 天窗口在冬季几乎不可能靠"真作业"达成（804 棵树 ×6 刀/270 体力 ≈ 27 棵/天，`docs/00-开发日志.md:90`） |

**结论（一句话）**：LLM 冬季策略不是"笨"，是"瞎"——**输入缺关键状态（背包/工具/种子当季性）、输出无纠错（取消原因不回灌）、结果判据奖励不干活（no_work 即 VERIFIED）**。三者按可修复成本排序：判据（P0，task-15 已有）> 反馈信号（P1，新卡）> 状态注入（P1，新卡）> 策略质量（它的下游产物，不需要单独"训模型"）。

---

## §3 经济与资源面审计

### 3.1 实测（12 天 + 2 天，全部可复跑）

| 维度 | 读数 | 证据 |
|---|---|---|
| 钱 | 12 天 day_start/day_end 恒为 **2767g**；`sell/ship/ship_loot` **0 / 0 / 0** | `probe_end.py`；事件计数 |
| 收入 | 0（唯一 `buy` 是失败：SeedShop 无 472） | `console.log:6`；`buy 1×item_not_sold` |
| 作物 | crops=0 / unwatered=0 全程；`harvest` **0** | day_start ×12 |
| 工具 | axe/hoe/can/pickaxe 全 `upgradeLevel 0`；`tool_upgrade_skipped` 12+2 条，`which=None, money=2767, free_slots=None` | 账本；`longrun.py:6213-6220` |
| 背包 | 容量 12、**12 格全满**（5 工具 + Geode×3 + Wheat×5 + CopperOre×1 + Stone×30 + Hay×6 + Clay×3 + WheatSeeds×10）；`free_slots` 在**任何事件里都没有落值** | 两本账本 0 条 free_slots 证据；`farmwork.py:25-27/1353` |
| 矿 | 铜矿 1、煤 0；`craft()` 熔炉需要 20 铜矿+25 石、5 铜锭需要 25 铜矿+5 煤；**brain 无采矿腿、无买矿 caller** | `farmwork.py:1467-1473`、`:3962/:4005/:4067`；grep `Clint` 仅升级/取回路径 |
| 树/石/枝 | trees ~897、stones ~79、twigs ~58、hoedirt 8 | 存档摘要（prompt 给定，本轮未再核） |
| 升级账 | 铜斧 = 2000g + 5×(O)334；钱够，**材料 0** | `farmwork.py:416-433` |

### 3.2 春季连锁影响（逐条判"会不会立刻炸"）

| 出口 | 机制 | 判 |
|---|---|---|
| ① 买种子（spring 1 商店有 472，20g/包） | `_buy_seed`（longrun.py:6466）→ 背包满 ⇒ `no_inventory_space` | **会立刻炸**，且已有前科：run8 夏季 `buy` 26 次 **0 成交**，其中 **25 次 `no_inventory_space`**、2 秒内 13 轮"开商店→失败→关商店"（`docs/_run8-evidence.md:173`）。0.7.44 的 `slot_relief` 三档白名单（`farmwork.py:1478-1637`）理论上能腾格，但：Stone 30 = `SLOT_RELIEF_RESERVES` 预留 30 正好卡死、CopperOre 1 < 预留 25、Hay 不可卖且不在白名单、5 工具不可卖 ⇒ **可腾上限约 3 格（Clay/Geode/Wheat）**，且账本 0 条 `slot_relief` 证据说明从未触发过（`free_slots` 从未被计算）。 |
| ② 播种 | 483 Wheat Seeds 在 spring 可种（season 转 spring 后 `plantableNow=true`）；`plant_area` 会真的下地 | **不炸但有隐性坑**：先买不到 472 就只能种 10 粒 Wheat（4 天成熟），收成 1 叠 Wheat 仍只占 1 格、腾不出新格；且 `UPGRADE_SUSPENDS` 不含 plant，无冲突。 |
| ③ 收获 | harvest 满包 ⇒ `code=failed + NO_SLOT_CODE + env_block`（`farmwork.py:2997-3010`），全局阻塞 | **会炸**：春季第一次收获就会把"全局阻塞"打开，而 `inventory_blocked` 不在 `JUSTIFIED_END_REASONS` ⇒ 当天必 `day_justified=false`，5 天 streak 断。 |
| ④ 卖货/腾格 | `_sell_surplus_for_seeds/_sell_surplus_for_slot/_sell_surplus_for_space`（longrun.py:5582/5695/5760）都在**买/收两条路径内**触发，冬季清障日没有任何 caller | **不会自己发生**：必须由 task-16 把"每次观测算 free_slots"接上，否则 12 天 0 卖货不是偶然而是必然。 |
| ⑤ 工具升级 | 需 5 铜锭；无矿、无买矿、无背包升级（grep `backpack` 0 命中） | **目标 1 直接阻断**（§1-5）。最省路径见 3.3。 |
| ⑥ 背包升级 | Pierre 2000g（12→24 格）；钱够（2767g） | **最便宜的解锁点**，但 brain 无实现，且 task-16 卡面明确"**背包升级不在本卡**" ⇒ 建议扩围或开新卡（§5-A2）。 |

### 3.3 目标 1「至少一次真实工具升级」：客观可达路径

| 路径 | 需要什么 | 工期/风险 | 判 |
|---|---|---|---|
| ① Clint 买矿 → 熔炉冶炼 → 铁匠升级 | 新 caller（打开 Clint 普通商店买 Copper Ore/Coal）+ `craft()` 已验证；钱 2767 足够 25 矿×~75g + 5 煤×~150g | 小–中；**前提：Clint 是否卖矿/年份限制本仓库无数据【无法判定】**；且背包 12 满，买 25 矿需要 1 格（矿可堆叠），仍需先腾格 | **最省**：0.7.46 可做 |
| ② Mod 技能直接发矿 | 新 Mod 技能 + 数值安全评审（禁止自写物品） | 中；违反"所有经济动作走游戏入口"的风险高 | 不建议 |
| ③ 春季矿洞腿 | brain 无 Mines 能力（grep 证），需新腿 + 新观测 + 新判据 | **大**（越过 0.7.45 窗口） | 顺延到 0.7.47+，task-14 评估 |
| ④ 砍树掉铜矿（Stardew 树掉种子/木材，不掉矿） | — | 不可行 | 排除 |
| ⑤ 背包升级 2000g | 钱够 | 小，但**不满足"工具升级"**，只能解锁出口 | 与 ① 配对 |

**结论**：目标 1 在冬季**结构性不可达**（不是策略问题）。0.7.45 窗口内唯一现实路径是 ①＋⑤，且依赖两个"未验证前提"（Clint 卖矿、背包升级入口可用）。task-14 应立刻把这两个前提核掉；核不掉就把"至少一次真实升级"顺延到 0.7.46，而不是硬凑 A9/B9。

---

## §4 验收判据盲区（只提建议，不改工具）

现有判据链：`checks` 10 键（`analyze-longrun.py:289-291` 语义表）+ `verify-run3.py` + `compare-runs.py` + analyzer 聚合。以下六类问题它们**看不见**：

| # | 盲区 | 为什么看不见 | 最小补法（谁做） |
|---|---|---|---|
| 1 | **背包满丢战利品** | 源事件根本不存在：`clear()`（`farmwork.py:2298-2570`）不查 `free_slots`、不记 `no_slot`；`farm` 观测里也不带掉落计数 | dev-coder：在 `clear/pickup/ship` 路径补 `info` 事件 `loot_lost{free_slots,qid,count,tile}`（不改判定）；log-analyst：analyzer 加 `bag_loot_lost` 聚合 |
| 2 | **策略无效空转**（下了意图但全被取消） | 现有红判据只覆盖"`cancel` 且该任务当天再没做成"（`analyze-longrun.py:2246-2268`）；"当日 LLM 3 条意图 0 条生效"无聚合；cancel **原因文本**只在 journal | log-analyst（task-17）：加 `llm_intent_effect{keep,cancel,unknown, cancelled_tasks, reasons_top3, executed_any}`；info 级 |
| 3 | **连续 N 天零收入** | 无 `economy` 聚合；`checks` 10 键无经济键 | log-analyst：加 `economy{money_open,money_close,sells,buys,income}`；Lead 决定是否升为第 11 键（建议**不进 rc**，只进报告） |
| 4 | **`pending_*` 新字段**（task-15 在制） | analyzer 未收 `pending_executable/blocked/unobserved`，冒烟后无法验证"no_work 是否诚实" | log-analyst：收四字段 + 校验不变式 `executable+blocked+unobserved==guard`（工作树 `longrun.py:776` 注释：`pending_guard == pending_executable + pending_unobserved`） |
| 5 | **"每日 ≥2 份独立观测"** | 账本里只有事件流，没有 `observe?detail=full` 的 `tiles[]`/`farm` 快照；`_pending_snapshot` 的分类也依赖 `tiles[]` 是否完整（截断按 unobserved，工作树 `:4993` 起） | machine-runner：冒烟脚本落盘每日 ≥2 份观测原文；log-analyst 聚合"观测份数" |
| 6 | **L3 只能人工判** | `compare-runs` 是词表旁证，"决策明确体现教训"无机器判据 | 保持人工，但在 `compare-runs` 输出"命中关键词的决策原文表"（现有词表旁证已有，补明细即可）；**不**升级为自动判定 |

一句话：**现有判据能证明"程序没崩、收工理由在白名单内"，证明不了"今天有产出、策略有效、经济在动"**。

---

## §5 建议动作清单（给 Lead 排卡）

### A. 建议动作

| 编号 | 动作 | 归属 | 优先级 | 为什么 | 验收判据（独立观测差分方向） |
|---|---|---|---|---|---|
| A1 | **守住 task-15 的 no_work 闸门**，并把"`no_work` 并列 pending 快照"写进验收 | 补进 task-15 | **P0** | §1-1：7/12 的 VERIFIED 全是 no_work 早收工，不堵这个口，A9 的 5 天没有意义 | 0.7.45 重冒烟：`day_end` 里 `checks.day_justified=true` 的每一天都必须同时落 `pending_executable/pending_blocked/pending_unobserved` 三个读数、`pending_executable=0`、且不变式成立；且"当天 ≥1 个作业阶段 ok>0" |
| A2 | **task-16 扩围为"背包满三出口"**：①每次观测算 `free_slots`（不再等 sell 证据）②清障/砍树前 `free_slots<=0` 就如实停并记 `loot_lost`（禁止静默丢）③买种前先腾格 ④**背包升级 2000g 单列评估**（Pierre，12→24） | 扩 task-16 | **P0** | §3.2：run8 已实证买种死锁 25 次；春季三条出口全在 12 格上撞墙 | 0.7.45 冒烟出现 ≥1 条 `slot_relief` 成功腾格（`trigger.freeSlots` 有值）；且出现 ≥1 条 `inventory_blocked`（如实留痕）或买种成交；`bag` 聚合不再写【无法判定】 |
| A3 | **新卡：策略输入注入三件事**（0.7.45 卡 C）：`bag={free}/{capacity}`、`seeds=[{qid,name,plantableNow}]`、`tools=[{kind,tier,upgrade_missing:{money,copper_bars}}]` | 新卡（dev-coder） | **P1** | §1-6：模型把 483 当"冬季种子"；8/12 天把体力花在无效 till/plant | 0.7.45 冒烟 prompt 里出现 `bag=0/12` 与 `plantableNow=false`；LLM `plant_area` 意图数 0.7.44=2/2 天 → 0.7.45 ≤1；decision 的 reason 不再出现"冬季种子(483)"式误称 |
| A4 | **新卡：意图取消原因回灌**：次日 prompt 增加 `cancel_reasons`（top-3 原文，如「field_se 看得见却没有一格可动目标」「观测里找不到田区 anchor:field_ne」） | 新卡或并入 task-15 | **P1** | §1-7：同一形态 8/12 天重复，模型没有纠错输入 | 0.7.45 冒烟次日 decision prompt 含 `cancel_reasons` 节；`unknown ∕ cancel` 意图占比从 29/33 降到 <50%；`reduce_scope` 类 area 非法不再重复 |
| A5 | **task-14 提前**（去掉 `blocked_by task-8`）：先核"Clint 卖矿？背包升级入口可用？"两个前提，给出目标 1 最省路径与是否顺延 | 改 task-14 依赖 | **P1** | §3.3：目标 1 冬季结构性不可达，拖着不核会让 A9 白跑 | `docs/_eval-target1-upgrade.md` 里两个前提各有"真机/代码"证据；给出 0.7.46 是否可达的结论 |
| A6 | **新卡（P2）：复盘输入补昨日终局**：把 `ended_by/ended_reason/pending_*` 作为"昨日事实"进次日 review/decision prompt | 新卡或并入 A4 | P2 | §1-8：两日 `ended_by=未观测到`，复盘学不到真卡点 | 0.7.45 冒烟第 2 天 prompt 里 `ended_by`/`ended_reason` 非"未观测到" |
| A7 | **task-17 补聚合**：`bag_loot_lost` / `llm_intent_effect` / `economy` / `pending_*` + 观测份数（§4-1..5） | 扩 task-17 | P2 | §4：现有判据证明不了"有产出/策略有效/经济在动" | 0.7.45 冒烟清单里四项都有非【无法判定】读数；`compare-runs` 输出命中教训的决策原文表 |
| A8 | **Lead 侧口径决策**：L0–L5 对照窗口必须覆盖"有农务面"的日子（spring 1–5），冬季尾巴上 L2/L3 结构性不可判 | Lead | P1 | §1-9 | `docs/_run10-criteria.md` 或 A9/B9 卡面写明窗口 = spring 1–5，且 B 臂教训库开关有参数记录 |

### B. 本轮**不该**做的事（明确划界）

1. **不许为凑 5 天放宽 `day_justified`**：尤其不要把 `resume_exhausted`/`stuck` 无条件塞进 `JUSTIFIED_END_REASONS`。task-15 在制的"仅 `pending_executable==0` 才放行、`None` 一律 False"是正确方向，保留。
2. **不在 0.7.45 塞矿洞腿**：brain 无 Mines 能力（grep 证），新腿会挤爆窗口，拖垮 A9 门禁；目标 1 顺延比假通过好。
3. **不把背包升级混进 task-16 顺手写**：它是独立入口（Pierre 特殊商品），需要自己的观测/回执/失败留痕；**也不要在同卡顺手改采购硬编码 472 的旧病灶**（`docs/_resume-tomorrow.md:217`），两条改动一起做无法归因。
4. **不让 LLM 直接下 buy/sell/upgrade 新任务**：`TASK_KINDS` 12 种里没有经济动作（`planner.py:101-114`，`ship` 只运亲手收获物），LLM 负"策略"不负"钱"；经济动作继续由确定性腿驱动，否则一改双重来源无法判责。
5. **不通过调 `work_reasons` 阈值"多干活"来掩盖 263/217**：那是判据稀释，不是修复；§1-2 的归属表必须用独立观测差分重算。
6. **不在没有观测快照的前提下宣布 A9/B9 通过**：`pending_*` 分类依赖 `tiles[]` 完整性（截断按 unobserved），账本里目前没有 `observe?detail=full` 落盘证据。

---

## §6 无法判定（诚实清单）

1. **A9/B9 实际结果**：尚未跑（task-8 在制），5 天 spring 1–5 的逐日 outcome【无法判定】。
2. **Clint 冬季是否卖铜矿/煤、年份限制**：仓库无调用方、无数据；需真机核【无法判定】。同理 Pierre 背包升级是否走 `ShopMenu.tryToPurchaseItem` 现有入口【无法判定】。
3. **"每日 ≥2 份独立观测"**：两本账本内未见 `observe?detail=full` 快照事件；是否有独立观测文件（guardian 侧）未核【无法判定】。
4. **背包 12 格的逐格构成**：只能从 prep 行与用户描述推断"12 行全满"，具体哪叠占哪格、`slot_relief` 实际可腾几格需存档/观测复算【部分无法判定】。
5. **L3 "决策明确体现教训"**：机器无判据，本轮只人工指认 1–2 处【无法判定（需人工）】。
6. **0.7.45 在制代码最终形态**：工作树 `M brain/agentfarm/longrun.py`（task-15 在制，审计期间仍在变动，行号会漂）未提交、未评审，本报告只引用其行为片段（`_pending_snapshot`、`_dead_end_pending`、`is_justified_end` 新签名），不作为验收依据。

---

*本报告只读完成，未启动游戏、未调 `/v1/exec`、未改生产代码。所有读数可用 `scratch/product-observer/` 三支探针复跑。*
