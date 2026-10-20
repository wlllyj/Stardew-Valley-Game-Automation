# product-observer 缺口清单（目标1/目标2 证据链盘点 · a9-goal12 T-4）

日期：2026-10-19（夜）  
角色：product-observer（旁观者；只写 `docs/_observe-*.md` 与 `scratch/`，只读生产代码与账本；不改判据、不写生产代码、不碰游戏、不 deploy）

> 本文是**可执行缺口清单**，每条给出：缺口 / 现有证据（文件:行号 或 账本字段，全部本人实测复跑）/ 建议卡面（谁写什么）/ 可验证判据（独立观测差分）/ 依赖与风险。缺失一律写【缺失】/【无法判定】，不许猜。
> 基线：`git rev-parse HEAD` = `590f154`（含 0.7.49 冻结指针 `daceb48` 与前任会话两个修复 `c383a0e`/`590f154`）；工作树另有**未提交** task-240b（`brain/agentfarm/longrun.py` +7 行，无测试）与未跟踪 `docs/_release-0.7.50.md`、开发日志条目 097（未提交）。本文结论针对**已提交代码 + 今日账本实证**。
> 路径约定：`brain/agentfarm/*.py`、`mod/AgentFarm.Bridge/*.cs`、`tools/*.py`、账本 `logs/*.jsonl`。
> 本文取证脚本（本人所写，均在 `scratch/`）：`obs_t4_economy.py`（五账本经济事件统计）、`obs_t4_economy2.py`（逐行原文）、`obs_t4_zone.py`（D1 修复后 zone 口径 + verify-zone-retention 端到端）。

---

## 0. 前任缺口闭环状态（先看再判断）

| 前任缺口（_observe-goal-gap-2026-10-18 / _observe-review-p0-2026-10-19） | 状态 | 证据 |
|---|---|---|
| 1.1 / D1：`ZONE_BLOCKER_KINDS` 缺 `"clump"` ⇒ 大障碍永不计数（假清空） | **已闭环（0.7.49）** | `fields.py:83` `ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS \| {CLUMP_KIND})`；本人复跑：区内 weed+clump(stump) 报 `blockers=2`、`zone_blockers_total=2`；`verify-zone-retention.py` 对"clump 未清"输出 `FAIL / exit=1`（旧口径假 PASS 消失）；`tilesTruncated=True ⇒ None` fail-closed 保持 |
| B：`buy` 分支是"假装下单"？ | **已闭环（描述已更正）** | 条目 096 更正：购买路径原本真的执行（`_preconditions` 内部 `:7393` 调 `_preconditions_apply`），缺陷在记账恒真（D2，`longrun.py:9103` 已改 `bool(...)`）；链路 `worker.buy → bridge.py:1138 → BuySkill.cs:300-304 反射 ShopMenu.tryToPurchaseItem`，成败按钱/背包差分（`BuySkill.cs:245-265`） |
| C：`verify-zone-retention.py` 继承 D1 ⇒ 假 PASS | **已闭环（D1 修后）** | 本人端到端复跑见 §2.2；工具本身逻辑正确（fail-closed、无硬编码坐标、exit 语义 0=PASS/1=FAIL 或【无法判定】/2=用法错） |
| 1.2：zone-level 归零判据接入 longrun 日终 | **未闭环【缺失】** | `day_end` 无 `zone_clear[zone]` 字段；`_review-0.7.48.md:264-265` 明记"接线延后"；今日五跑账本无任何 zone 清空判读字段 |
| 1.3：连续 2 天复核（跨日对比工具被调用） | **未闭环【缺失】** | `verify-zone-retention.py` 无任何自动调用点（全仓 grep：只有 tests/docs 引用）；A9/B9 清单（`scratch/longrun-a9b9-rollout-checklist.md`）只写"每日 ≥2 份独立观测存 scratch/"，**没有**跑该工具的步骤、没有 before/after 命名约定、没有"恰好两天→链式 ≥2 天"的调用方 |
| 3.1/3.2：经济执行路径（买种/升级 caller） | **代码路径已存在、执行证据仍为零** | caller 齐全（§1.1），但今日所有跑 seed buy 成交 0 次、`upgrade_tool` 事件 0 次（§1.1 表） |
| 3.3：升级后清 toolOk=false 障碍的实测 | **未闭环【缺失】** | 今日五跑 `blocked_by_tool` 事件 = **0** ⇒ 没有任何观测级 `toolOk=false` 锚点格（§3.2） |
| 4.1：策略生成机制 | **已闭环**（机制就绪，简报信息仍缺，降级 P1） | 59 决策 / 177 意图全部落在具名田区或锚点（§5.1） |
| 4.2：结果校验含 CHECK 失败/收工原因 | **部分闭环**（post-run 齐备；review 输入缺 checks/ended_by，见 §5.2） | `day_end.checks` 10 项 + `ended_by/ended_reason` + `verify-run3.py` 逐日 problems 均在；但 5 条 review prompt 的 `ended_by/ended_reason` 恒"未观测到" |
| 4.3：lessons 注入 + A/B L0–L5 装置 | **装置齐备、对照未做** | 注入实证 22/23 等（§5.3）；`compare-runs.py` L0–L5 + 单测 + 历史 selftest 齐；**无真正 A/B 对**（B9 lessons 字节拷贝未执行） |
| 5.1/5.2：no_work 白拿口径、观测 ≥2 份 | **部分** | `verify-run3.py` 已有 `zero_action_evidenced`/实质动作证据（`:245-247`）；A9 清单 L2 有"每日 ≥2 份观测"但无强制校验 |

---

## 1. 目标1 ① 经济闭环：事件链现状与"钱恒 3042"根因链

### 1.1 事件链实测（今日五跑 + smoke-0746，脚本 `scratch/obs_t4_economy.py` / `obs_t4_economy2.py`）

| 账本 | 天数 | money 时间线 | seed buy（种子） | ship/sell 出货 | upgrade_tool | tool_upgrade_skipped |
|---|---|---|---|---|---|---|
| `runA9-0749.jsonl`（12:54，无 finish 行） | 2（winter 26/27） | 2767→3042 | **0 成交**（buy 6 条全是 `code=disabled` 背包升级留痕） | sell ok=4 | **0 事件** | 4 |
| `runA9-0749-fix.jsonl`（12:59–13:10） | 4（winter26-28+spring1） | 2767→3042（+275=Wheat×5+Geode×3 NewDay 结算） | **1 次尝试失败**：`buy{item:"472"(Parsnip 春种), code:failed, 回执 item_not_sold, price_shelf=0, price_cfg=20}`（L9）→ `no_seed_for_sale`（L10） | sell ok=2（Wheat×5/125g + Geode×3/150g，L6/L7） | **0 事件** | 4（money 2767/3042/3042/3042） |
| `runA9-0749-spring.jsonl`（13:14–13:24） | 6（spring 1-6） | **恒 3042** | **0 次请求**（从未发出 buy；`slot_relief` 每天记"买种子前背包满且腾不出格子 ⇒ **不买**"L6/L126/L262/L397/L588/L700） | **0** | **0 事件** | 6（每天 money=3042） |
| `run-test-space.jsonl`（13:37–13:41） | 1（winter26） | 2767→3062 | 1 次尝试失败（同 472 item_not_sold） | sell ok=4（含 590f154 last-resort 出货 Acorn×1/Hay×6，L36/L37） | **0 事件** | 2 |
| `run0749-clean.jsonl` | 67 行 | 2767 | 1 次尝试失败 | sell ok=2 | **0 事件** | 1 |
| `longrun-smoke-0746.jsonl` | 1 | 3288 | 0（disabled 留痕 1 条） | 0 | **0 事件** | 1 |

**结论：事件链四环（buy 种子 / ship / sell / upgrade_tool）中，只有 ship 真发生过（且次日才到账）；种子采购在 winter 档"探一次就被冬季货架拒"、在 spring 档"一次请求都没发"；upgrade_tool 全程零事件。money 恒 3042 = 出货收入 +275 后再无任何支出/收入。**

### 1.2 "钱恒 3042"三重死锁（spring 档根因链，journal + console 实证）

1. **每天 `day_start free_slots=0`**（六天全 0，背包 12 格全满；`rows_before=12/rows_after=12`）且**没有可卖/可出货的盈余叠**：console 原文「背包里没有可卖的盈余叠（只认已知作物/材料/矿表，工具/武器/种子/升级材料/未知物品一律不卖）⇒ 腾不出格子」。
2. `_preconditions_apply`（`longrun.py:7486-7525`）据此走「买种子前背包满且腾不出格子 ⇒ **不买**」闸门，**连 ShopMenu 都不开** ⇒ seed buy 0 次请求。腾格路径自身也堵：`_sell_surplus_for_slot`/`_sell_surplus_for_space` 挑不出白名单叠（0.7.46 后建材/锭类永不卖，`SURPLUS_MATERIAL_IDS` 只剩 Sap/Slime）。
3. **catch-22**：`_slot_relief` 腾格成功后 `continue` 跳过本轮 `_preconditions`（`longrun.py:9879`）⇒ 即使哪天腾出格子，买种子也要等下一轮；**未提交的** task-240b（工作树 +7 行：腾格成功⇒重取快照+`_preconditions`+continue）正指向此环，**无测试、未落库**（T-1 在进行）。
4. 守卫每轮喊「没种子但钱够（3042g ≥ 20g），该去买」（`ended_reason` 原文，判据 `longrun.py:5089`）但执行层因背包满永久不买 ⇒ 守卫理由与执行能力脱节（`day_justified=false` 的直接来源）。

**冬季档附证**：买种探一次用 `472`（Parsnip，**春季**种子）打冬季货架 ⇒ `item_not_sold`（选品不认季节，T-2 task-241 针对此）；`price_shelf=0`（货架无种子条目）而守卫仍按配置价 `seed_price=20g`（`longrun.py:1063` 默认值）说"钱够" ⇒ **守卫"钱够"口径与货架实价口径不一致**（`_seed_price_now` 用货架价、`work_reasons` 用配置价）。

### 1.3 缺口清单（目标1 ①）

| 缺口 | 现有证据 | 为什么是缺口 | 建议卡面 | 可验证判据 | 依赖与风险 |
|---|---|---|---|---|---|
| E1 **seed buy 真机成交证据为零（spring 档零请求、winter 档被货架拒）** | §1.1 表；`slot_relief{trigger:"none",note:"买种子前背包满且腾不出格子"}`（spring L6 等 6 条）；`buy{code:failed,回执 item_not_sold}`（fix L9） | 目标1①要求"钱在种子与升级间有过实际分配"；今天 seed buy 0 成交 ⇒ 经济再投资从未发生 | **dev-coder（T-1/T-2 收口）**：task-240b catch-22 落库+测试；task-241 季节感知选品（只用当季可种/在售条目；冬季无在售⇒不发 buy、`seed_dead_today` 如实记账）。**machine-runner**：smoke-0750 门禁④"buy（种子）意图在真机出现且 executed_steps/reasons 如实" | 独立观测差分：buy 前后 `observe?detail=full` 的 `player.money`（−price×n）与背包种子叠加；账本 `buy{ok:true,source,price_shelf,price_cfg}`；次日 `day_start.money` 下降量吻合 | 冬季热身三天结构性无种可买（`_release-0.7.50.md` §5.1 已标）⇒ 种子证据只能押 spring1-5；若"全保护材料背包"死锁仍在（T-6 确认中），腾格仍失败 ⇒ 需 Lead 裁决 task-242 边界 |
| E2 **背包结构性死锁（满包=全保护材料，白名单无可卖叠）** | console 原文（§1.2.1）；`slot_relief` 18 条 spring 全 `freed=0`；`590f154` last-resort 出货只在 test-space 验证过 1 次（Acorn×1/Hay×6 后 buy 仍 failed item_not_sold） | 满包 ⇒ 买种/收货/熔炼全部堵死；这是 E1 的上游根因，且 0.7.46"建材永不卖"纪律与"腾格换钱"存在天然张力 | **dev-coder**：last-resort 出货的边界卡面（哪些保护叠可破例、每 qid 保留下限、建造预留）须 Lead 裁决后落码+单测；**log-analyst**：统计各跑 bag 构成（只读账本 `before/after` 的 qid 分布） | 腾格成功后 `freeSlots_after>0` 且被出货 qid 不在禁卖清单；后续 buy 请求真实发出（`buy{attempt>0}`） | 触及 AGENTS.md §5 纪律边界（工具/武器/种子/建材/锭类永不卖）⇒ 必须先裁决再落码，不许 dev-coder 私改 |
| E3 **upgrade_tool 全程零事件（计划恒 None）** | `tool_upgrade_skipped{reason:"没有可做的升级（钱/材料不够，或工具等级读不到，或已满级）",money:3042}`（spring L7/L127/L263/L398/L589/L701 六条）；`_tool_upgrade_plan`（`longrun.py:7222-7284`）要求 `money≥2000 且 (O)334≥5` | 钱 3042≥2000 够，但铜锭持有量【无法判定】（无 inventory 全文证据，T-6 进行中）；若为 0 ⇒ 计划恒 None、升级永不发生 | **machine-runner（T-6）**：只读探针出背包逐格（含 `(O)334/378/382/390` 计数）与五工具 `upgradeLevel`；据结果由 Lead 定"升级链"时间盒 | 账本出现 `upgrade_tool{ok:true,before/after}` 或探针证实无锭 ⇒ 标【无法判定】并上报 | 铜矿来源见 §3.1——农场 clump 不打铜矿 ⇒ 材料链可能结构性断裂 |
| E4 **经济事件缺 analyzer 聚合口径** | `analyze-longrun.py` 无 money 时间线/两头分配统计（T-3 的 `scratch/_a9_deep.py` 有 money 时间线但是 scratch 脚本，非交付判据） | "钱在两头有过实际分配"的判决需要机械可算的聚合，今天只能靠人读账本 | **log-analyst**：在 `tools/analyze-longrun.py` 增加经济聚合（money 逐日、buy/ship/upgrade 事件计数与金额、`seed_vs_upgrade` 双列），带单测 | analyzer 输出 `economy{money_by_day, seed_buy_total_g, upgrade_spend_g, ship_income_g}`，与账本逐条对得上 | 不改判据，只加只读聚合；需与 verify-run3 同向 |

---

## 2. 目标1 ② 指定作业区清空 + 连续 2 天复核

### 2.1 D1 修复已验证，但"清空判据"缺三块落地

**已验证（本人复跑 `scratch/obs_t4_zone.py`，当前工作树）**：
```
ZONE_BLOCKER_KINDS = ['bush','clump','stone','tree','twig','weed']   # fields.py:83
区内 weed+clump(stump) → blockers=2、zone_blockers_total=2           # 旧口径会漏 clump
verify-zone-retention：clump 未清 → field_nw 2 2 FAIL，exit=1        # 假 PASS 已消失
tilesTruncated=True → zone_blockers_total=None（fail-closed）
```

**缺口 Z1：`verify-zone-retention.py` 在 A9 管线里没有任何调用点与观测协议。**
- 证据：全仓 grep `verify-zone-retention` 只有 tests（`test_fields.py:538-544` CLI 用例）与文档引用；`longrun`/`verify-run3`/`analyze-longrun` 均不调它；A9/B9 清单（`79ae4cc`，161 行）L2 只写"每日 ≥2 份独立观测：`observe full`（存 scratch/）"——**没写存哪、按什么命名、谁来跑 retention**。
- 工具自身限制（`_note-0749.txt` 第 7 条已标、未修）：只用 `before` 推 zone 边界；只比恰好两天，"连续 ≥2 天"要调用方链式 `(N,N+1),(N+1,2)…`。
- **建议卡面**：**machine-runner** 在 A9 清单补"zone retention"步骤：每日收尾/起跑各存一份 `observe?detail=full` 到约定路径（如 `scratch/a9-zone/<date>-<day>.json`），跨日成对调 `tools/verify-zone-retention.py --before … --after … --all`，输出贴证据文档；**observer 二审**读数。
- **可验证判据**：判据必须读**独立观测差分**（两次 `observe?detail=full` 的 `zone_blockers_total` 都 ==0），绝不采信 journal 自述；`tilesTruncated=true` ⇒ 【无法判定】。
- **风险**：见 Z2——今天所有观测都截断，直接跑会全【无法判定】。

**缺口 Z2：`tilesTruncated` 使"按区统计"今天恒不可判定（协议缺口）。**
- 证据：今日全部 baseline `tilesTruncated=true`（spring：`tileCount=400`/`tillableCount=172`；fix：`400/200`）；Mod 侧 `tiles[]` = 按离玩家距离排序取最近 400 格（`WorldSnapshot.cs:739-751`，本机农场 1400+ 格）；`zones_from_observe` 的包络本身只覆盖已返回格 ⇒ 截断时 zone 边界可能都是错的。
- **建议卡面**：**machine-runner** 立"zone 观测协议"：判某区清空前，先 `goto` 到该区附近再 `observe?detail=full`（让 400 格窗口盖上全区），记录 `tilesTruncated=false` 才采用；**dev-coder** 可选：在 `verify-zone-retention.py` 增加"两次观测同 location/同季节 + after 边界重算"断言（`_note-0749.txt` 已标"另开卡"）。
- **可验证判据**：用于判决的两份观测 `tilesTruncated=false` 且覆盖目标 zone bounds；否则结论写【无法判定】。

**缺口 Z3（新发现）：`kind="unknown"` 地形特征格不在任何桶里——zone 清空判据对它假 PASS，till 又被它拒。**
- 证据：spring 跑 `tool_refused` 12 条全部是 `till_area` + `tool_ineffective`（"Hoe 挥 6 次无效"），坐标 `[73,25][74,25][73,26][74,26][67,30][68,30][67,31][68,31]`（kind=未知，与 gaps `unknown gated×12` sample_tiles 一致）；fix 跑 spring1 `unknown blocked_tile×12`。本人核对常量：`'unknown' in OBSTACLE_KINDS=False`（`planner.py:1398`）、`in ZONE_BLOCKER_KINDS=False`（`fields.py:83`）、`in CLUMP_KINDS=False`（`farmwork.py:163`）、`in SKIP_KINDS=False`（`farmwork.py:124`）⇒ **计数、简报、清除三不沾**；Mod 对未归类 TerrainFeature 一律 `Kind="unknown"` 并写 `Feature=tf.GetType().Name`（`WorldSnapshot.cs:799-811`），脑侧从不读 `Feature`。
- 为什么是缺口：用户验收清单里"该清的全清"若只剩这类格，`zone_blockers_total=0` 报"已清空"，而 `till_area` 到这些格仍被游戏拒（smoke-0746 `[41,12][41,13]` 同形态）⇒ **新型假 PASS**；且它挡住开垦，是"farm 还有 157 格耕地空着却动不了"的疑凶之一。
- **建议卡面**：**machine-runner（T-6）**：只读探针读这些格的 `Feature` 字段与 `clumpIndex`（若其中确有 ResourceClump 未归类，则回到 clump 口径）；**dev-coder**：按探针结果给 `unknown` 一个明确桶——能清的进 `ZONE_BLOCKER_KINDS`+clearable，不能清的进 `DEFERRED_KINDS`（护栏 A 要求"不许静默跳过"）。
- **可验证判据**：探针输出这 12 格的 `Feature/clumpIndex/clumpKind/toolOk`；修复后同一观测的 `zone_blockers_total` 把这些格计入（或简报如实公告"暂不支持清理+原因"）。
- **风险**：未知索引按 ClumpMeta 铁律不许猜工具；若 `Feature` 显示是 GiantCrop 等设计上不该动的，则应进"不该动"桶并写入用户可见简报，而不是硬清。

### 2.2 缺口清单（目标1 ②）

| 缺口 | 现有证据 | 建议卡面 | 可验证判据 |
|---|---|---|---|
| Z1 retention 无调用点/无观测协议 | §2.1；清单 L2 只有"存 scratch/" | machine-runner 补清单步骤+路径命名；observer 复核 | 两次独立 `observe?detail=full`（非 journal）的 `zone_blockers_total` 均 0；跨日链式 ≥2 天 |
| Z2 tilesTruncated 恒真 ⇒ 按区统计不可判定 | 今日 baseline 全 `tilesTruncated=true` | machine-runner zone 观测协议（走近再观测）；dev-coder 补 after 边界/同地点断言 | 判决用观测 `tilesTruncated=false` |
| Z3 unknown 格三不沾（新发现） | §2.1；`_tile_reason` 对全 skipped 且 kind 不在 `DEFERRED_KINDS` 时记 `gated`（`longrun.py:8154-8159`） | T-6 探针读 Feature；dev-coder 定桶 | 探针 Feature 原文 + 修复后计数变化 |
| Z4 `day_end.zone_clear[zone]` 未接线（前任 1.2 遗留） | `_review-0.7.48.md:264-265` 明记延后 | dev-coder：日终写 `zone_clear[zone]=blockers_total==0`（只读统计，不进 checks） | 账本字段与独立观测同向 |

---

## 3. 目标1 ③ 铜斧升级链（2000g + 5×(O)334）

### 3.1 铜矿来源：农场 clump 不打铜矿（IL 实证），矿洞/Clint 买矿均无路径

**IL 实证**（`scratch/t204-il-up-1-u8.txt`，`ResourceClump.performToolAction(Tool, GameLocation, Vector2)` 方法体，2026-10-19 本人复读）：
- `600/602`（stump/log）支：`(O)709` Hardwood ×2/×8，小概率 `(O)292` Sap；`StumpsChopped` 统计 +  foraging XP 25；
- `672`（boulder）支：`(O)390` **Stone** ×15 + `playSound("boulderBreak")` + 粒子；
- `148` 支：`(O)390` Stone ×10；
- `622` 支：`(O)386` Clay ×10、`(O)390` ×8、`(O)749` OmniGeode ×2、小概率 `(O)74`；
- ⇒ **四个分支没有一个掉 `(O)334` 铜矿/铜锭。**（ClumpMeta.cs:14-18 的门槛表：stump axe≥1 / log axe≥2 / boulder pickaxe≥2 / rockPile pickaxe≥3 / greenRain pickaxe≥0。）

**结论**：`UPGRADE_TRADE_ITEMS={0:"(O)334"}`（`farmwork.py:423`）的 5 块铜锭**不可能从农场大障碍获得**。剩余来源：
1. **矿洞开采**：脑内无 `mine` 意图/能力（`planner.py:101-114 TASK_KINDS` 无 mine）⇒【缺失】；
2. **Clint 商店购买**：`docs/_upgrade-protocol.md` §2 假设"买 `(O)378`×45、`(O)382`×6"（预算 6275g），但**没有任何真机货架证据**证明 Clint 卖矿（vanilla `ClintUpgrade` 店按 task-204 IL 只挂升级条目）⇒【无法判定】，且当前钱 3042 < 6275；
3. **熔炼链**（协议 §3-§5：造熔炉→放置→5 次冶炼）需要先有铜矿+煤 ⇒ 同归 1/2；
4. **开晶石**（Clint 25g/个）：当前档有过 Geode（fix 跑出货过 3 个），但 Mod 无 geode-cracking 技能 ⇒【缺失】。

### 3.2 "升级后清掉此前 toolOk=false 障碍"的锚点格：今日零实证

- **`blocked_by_tool` 事件今日五跑全为 0**（本人逐账本统计）⇒ 没有任何一格留下"观测级 toolOk=false（等级不够）"的账。该事件正是 task-218⑤设计的"可升级跟进账"（带 `tile/tool/minLevel/currentLevel`，`longrun.py:7956-7961`）。
- smoke-0746 的 `[41,12][41,13] tool_ineffective` 是 **Hoe 锄不动**（kind=未知），不是 clump 等级门槛 ⇒ 不是铜斧锚点；
- gaps 文件里 `unknown×12` 是 `kind="unknown"` 地形特征（toolOk 未评估，见 Z3）、`tree blocked_tile×13` 是站位阻挡（`blocked_tile` 非等级）；
- ⇒ **当前档不存在已证的"铜斧升级后可清"锚点格**；农场是否有 stump(600)/boulder(672) 且 `toolOk=false`，需 T-6 只读探针（clump 分布 + `parentSheetIndex` + `toolOk` 三态）证实 ⇒ 目前标【无法判定】。

### 3.3 缺口清单（目标1 ③）

| 缺口 | 现有证据 | 建议卡面 | 可验证判据 | 依赖与风险 |
|---|---|---|---|---|
| U1 **铜锭来源无路径（IL 已证农场 clump 不打矿）** | §3.1；`farmwork.py:423`；协议 §2 买矿假设无货架证据 | **machine-runner（T-6）**：探针背包 `(O)334/378/382` 计数 + Clint 店货架只读清单（`observe`/shop probe）判"Clint 到底卖不卖矿"；**Lead**：据结果定升级链时间盒或判冬季【无法判定】 | 探针货架原文；若 Clint 不卖矿且无矿洞腿 ⇒ "铜斧升级"冬季结构性不可达，结论如实上报 | `docs/_upgrade-protocol.md` §2 的 6275g 预算建立在未证假设上；协议需按探针结果改写 |
| U2 **toolOk=false 锚点格零实证** | §3.2（blocked_by_tool=0） | **machine-runner（T-6）**：clump 分布探针（每格 `clumpIndex/clumpKind/clumpTarget/toolOk`）；若有 600/672 且 toolOk=false ⇒ 锚点现成，登记坐标进 A9 判决证据 | T1（升级前）该格 `toolOk=false` → T2（升级后 axe.level≥1）`use_tool` 成功且 tiles[].kind 变化、无 `tool_ineffective`（两次独立 `observe?detail=full`） | 升级要 2 天在途（`daysLeft=2`）跨日；若农场压根没有 axe≥1 门槛的 clump ⇒ 目标1③冬季【无法判定】，需 Lead 定口径 |
| U3 升级链代码两侧齐备但零执行 | `farmwork.py:3889-3983`（观测差分判据：tier+1 或 toolBeingUpgraded 出现才 ok）、`ToolUpgradeSkill.cs`、协议 §0-§8 | 无需新卡；U1/U2 解决后由 A9/B9 自然产生首批执行证据 | `upgrade_tool{ok:true,before/after}` + money_delta==-2000 + (O)334 −5 + tools[].upgradeLevel 0→1 + toolBeingUpgraded/daysLeft=2 | 防重复购买（协议 §6 硬自检已在 farmwork:3926-3930 fail-closed） |

---

## 4. 补充A「余力多清」与补充B「经济两头平衡」

### 4.1 补充A：surplus 清障无实现（前任 2.1/2.2 仍未闭环）

- **`surplus_mode`/`extra_cleared` 在 longrun 零命中**（grep 实证）。task-221 rev2 的规划（`reserve=次日浇水体力+安全余量`、只排核心任务之后、有界 3 格/天、farm 计数不可用 fail-closed——开发日志条目 033 行 199/333 有记录）**未落码**。
- **代码侧唯一的"核心优先"次序在 fallback**：`deterministic_plan`（`planner.py:2015-2096`）顺序 = `recover_stamina → harvest → reduce_scope → clear_dead → water_area → ship → clear_area → till_area → plant_area` ⇒ clear_area 确实排在水/收/出货之后；但主驱动是 LLM 边界意图——spring 跑 177 个意图的 area_hint 分布以 `field_ne`(69)/`anchor:field_ne`(60) 为主且 clear_area 常居决策首位（LLM 不知道"余力"概念，简报也没给它"核心已完成"的信号）。
- **"不透支次日浇水体力"**：现有守护只有 `_stamina_budget` 的 `water_reserve`（按**今日** live_crops，`longrun.py:3429-3488`）+ `capacity` 限今日播种量（`:4847-4860`）+ 树预算 discretionary（`:3715-3771`）；**没有**"次日最坏需水"显式验证，也没有 surplus 专属硬闸。
- **账本口径**：无 `extra_cleared` 字段；"核心完成后额外清了多少格"今天**不可分离**（clear_area 的 ok/already/leftover 混在 `day_end.stages` 里）。
- **建议卡面**：**dev-coder**：新增 `surplus_mode`（`no_unmet_stages` 语义成立且浇水/收获/清死苗/播种无 leftover 时进入），只清指定作业区内 `ACTIONABLE_KINDS ∪ CLUMP_KINDS`，执行前强制 `discretionary_after >= cost_est` 并 journal `surplus_check`；日终写 `day_end.extra_cleared`（格数）；**log-analyst**：A/B9 日终核对 surplus 未挤占浇水（`crops_watered` 真值不变）。
- **可验证判据**：核心任务结束时刻 vs 日终的两次观测差分 = `extra_cleared`；日终 `stamina >= water_reserve − ε` 且 `farm.dryCrops` 无新增；surplus 期间浇水队列无中断证据。

### 4.2 补充B：经济两头无资金仲裁，"钱在两头有过分配"缺最小证据集

- **主循环次序**（`longrun.py:9858-9900`）：背包升级(默认关) → `sleep_guard` → `_slot_relief`（腾格；未提交的 task-240b 在其后插 `_preconditions`）→ **`_preconditions`（买种子）** → **`_maybe_tool_upgrade`（升级/取回，日 1 次；`upgrade` 要等紧急农活做完、`pickup` 一律放行）** ⇒ **种子采购优先于升级，且两者之间没有任何预算仲裁/预留**：都够钱时种子先花（`n=min(buy_count=10, money//price)`，`:7629`），升级只有"钱≥2000 且 (O)334≥5"的粗判（`_tool_upgrade_plan:7222-7284`）。钱 3042 时若铜锭够，理论上可"同日既买种又升级"——但没有任何机制保证"平衡推进"（例如留 2000g 升级专款）。
- **`SEED_KEEP_FACTOR=10` 已不参与判定**（`longrun.py:7694` 注释：task-123 之后只为老账本对账保留）；`UPGRADE_PRICES={0:2000,…}` 与 `seed_price`（默认 20）之间无联动。
- **守卫口径不一致**：`work_reasons` 的"钱够"用配置价 20g（`:5089`），`_seed_price_now` 用货架价（`:3882-3884`）⇒ 冬季货架无种子时守卫仍喊"该去买"（证据真值问题，条目 097 留 Lead 单独裁决，dev-coder 不许私改判据）。
- **"钱在两头有过实际分配"的最小证据集（observer 建议，供 Lead 采信）**：
  1. 同一次 A9/B9 跑内，`buy{ok:true}`（种子，Mod 侧钱/背包差分）≥1 笔 **且** `upgrade_tool{ok:true}` ≥1 笔；
  2. money 时间线出现两次下降：种子支出（=price×n）与升级支出（=−2000），中间被 NewDay 出货收入部分抵消（ship→次日结算）；
  3. 升级前后各一份 `observe?detail=full`：`player.money` −2000、背包 `(O)334` −5、`tools[].upgradeLevel` 0→1、`toolBeingUpgraded` 出现且 `daysLeft=2`；
  4. 两侧工具同向：`analyze-longrun` 经济聚合（E4）与账本逐条对得上。
- **建议卡面**：**Lead** 定"两头平衡"验收口径（同日双头 vs 跨日双头；无铜锭时是否接受"种子一头+升级【无法判定】"）；**dev-coder**（若 Lead 要求仲裁）：在 `_preconditions_apply` 与 `_maybe_tool_upgrade` 之间加"升级专款预留"开关（默认关，opt-in），journal `economy_reserve`；**log-analyst**：E4 聚合落地。
- **风险**：3042g 距协议 6275g 预算差一半；若 T-6 证实零铜锭，则春季档"两头分配"只剩一头 ⇒ 现在不改判据，只把最小证据集定下来，跑完用数据说话。

---

## 5. 目标2 三能力证据链

### 5.1 ① 策略生成（意图+具名田区→代码落坐标）——**机制齐备，落点证据充分**

- 落点链：prompt 在 `planner.py:2109-2152`（system 明写"`area_hint` …**不要坐标**"）+ `:2141-2152`（`__AREAS__`←`brief.areas`、`__ANCHORS__`←`allowed_area_hints`）；`llm.py` 仅 HTTP 客户端（无 zone 字样）；解析端 `validate_intent`（`:266-285` 拒 `coordinate_in_intent`）→ `resolve_zone`（`fields.py:422`）→ `plot_in_zone`（`fields.py:476`，代码落锚点）。
- **今日实证**（三跑 llm.jsonl，本人统计）：决策行 59、意图 177；**59/59 条 prompt 含具名田区清单**（`areas=['field_nw','field_ne','field_sw','field_se']` + 每区可锄/待清理/作物/浇水/距离）；area_hint 分布：`field_ne` 69、`anchor:field_ne` 60、`tiles.plantable` 24、`tiles.crops` 6，其余为 `tiles/inventory/near:/farm/current_location` 等非片区任务；`intent_verdict` 132 条 keep/cancel 均带理由（如「「field_ne」看得见却没有一格可动目标」）。
- **残留缺口（P1）**：`zone_brief_lines`（`fields.py:358-369`）仍不含"当季可种/axe 等级"事实（条目 087"不是笨是瞎"根因）；简报 `counts.clumps=0` 与 gaps 12 个 unknown 格矛盾（观测窗口截断，简报只反映玩家身边 400 格）。**建议卡面**：dev-coder 在简报补当季可种性与工具等级事实（只加事实不加指令）；log-analyst 抽样 5 条决策核对 0 次 `coordinate_in_intent`。

### 5.2 ② 结果校验（当天结果与判据对照、CHECK 失败/收工原因）——**post-run 齐备，run 内 LLM 复盘缺输入**

- 齐备部分：`day_end.checks` 10 项（slept_by_us/no_blocking_modal/no_hard_failures/unreachable_within_bound/refused_within_bound/no_unmet_stages/crops_watered/watered_outdoor/day_justified/zero_action_evidenced）+ `ended_by`/`ended_reason`（spring 跑 ended_reason 含守卫三条原文）；`tools/verify-run3.py` 逐日 problems（CHECK 失败/收工原因全列，`:684-697` 等）；`analyze-longrun.py` 七口径不变式。
- **缺口 R1：review_llm 的输入看不到"怎么收的尾、为什么"**。实证：spring 跑 5 条 review prompt 的 `ended_by`/`ended_reason` **全部"未观测到"**（`_review_before_sleep` 在 `_do_sleep` 内、`rep.ended_by` 由调用方在 `_do_sleep` 返回**之后**才写：`longrun.py:7741` vs `:9864-9866`；docstring `:4514` 声称"`rep.final`/`rep.checks` 都已定稿"与代码顺序不符）；且 prompt **不含 `checks` 全量**（只有 ok_steps/failed_steps/unreachable/refused/dry 等平铺事实）。
- **建议卡面**：**dev-coder**：review prompt 追加"判据对照"小节（逐项 `checks` 键值 + 失败项全列）与"收尾原因"（`ended_by`+`ended_reason`）；修 docstring 与顺序不符之处；**log-analyst**：抽样 review 输出 notes 至少引用一个关键失败项。
- **可验证判据**：`*-llm.jsonl` 的 `kind="review"` prompt 含 checks 全量与 ended_by/ended_reason 实值（跨夜跑次日 review 时能看到前一天的）；review notes 引用具体判据名（不许只写"体力不足"）。
- **缺口 R2（P1）**：`analyze-longrun.py` 无经济聚合（见 E4）、无 zone 清空聚合（Z4 的账本侧）。

### 5.3 ③ lessons.json 注入 + run A vs run B L0–L5——**注入实证充分，对照装置齐备但未做过**

- **注入实证**（今日三跑）：spring 22/23、fix 27/28、test-space 7/8 条决策 prompt 含 `lessons（从过去几天的账本里总结的教训，只作参考）:` 节；每跑 `*-lessons.json` 自带 `id/kind/scope/symptom/evidence/hint/count/src=agentfarm`（spring 6 条含 `plot_exhausted` count=6、`tool_refused@till_area` count=4；L0 的"≥1 条 count>=1"成立）。边界纪律保持：lessons 只进提示词、不进判定（`planner.py:456` 注释）。
- **对照装置齐备**：`tools/compare-runs.py` L0–L5 完整（L0 库存在、L1 注入命中、L2 同形态减少三态、L4 尾部无回归、L3 影响旁证、L5 总判），`tests/test_compare_runs.py` 在，历史 selftest（`scratch/_cmp_selftest.txt`，run7 vs run8）在；`scratch/run9-lead-check.py` 第三检查器在；A9/B9 清单 §5 判决链完整（verify-run3 双侧 + analyze 双侧 + compare-runs + 三检查器 + already/attempted_ok 双列）。
- **本人试跑**（fix 为 A、spring 为 B，`--days 3`）：L0 ✅（5 条、count≥1）；L1 ❌ 0/5——但工具自带警告正确归类为"比对口径/未注入"问题：**spring 跑用的是自己积累的 lessons，不是 fix 的库**（B9 的 B-LS 字节拷贝未执行）⇒ 这正好说明 **L1 命中以"A9 lessons 字节拷贝到 B9"为前提**，该步骤只在清单里、从未演练。
- **缺口 C1**：真正 A/B 对照未做（A9/B9 未起跑）；**C2**：L1 子串口径（`lesson_text` 取 hint-first 单字段；注入被 200 字符裁掉算未见）需在真对上验证——建议 B9 起跑后先用 `compare-runs` 空跑一次核对 `lessons_hits/section_present` 两值同向；**C3（P1）**：`LESSONS_INJECT_MAX=3`/`LESSONS_INJECT_CHARS=200` 渠道极小，"据结果优化"的影响面受限，需在 L3 旁证里实证而非灌字。
- **建议卡面**：**log-analyst**：A9/B9 跑完后按清单 §5 执行 compare-runs + 人工核对 L3（决策理由溯源到 lesson id/scope）；**machine-runner**：B-LS 字节拷贝记 size+SHA256；**dev-coder**：若 L1 出现"节在、0 命中"且确认字节拷贝无损，则修 `lesson_text` 取键口径（属判据工具修复，须 Lead 批准）。

---

## 6. 建议优先级（执行顺序）

1. **P0-E1/E2**：经济三重死锁收口——task-240b 落库+测试（T-1，工作树已有无测试改动）、task-241 季节选品（T-2）；"全保护材料背包"腾格边界须 Lead 裁决（task-242）后再落码。**这是目标1①"钱有过实际分配"的前置**，冬季三天无种可买 ⇒ 证据押 spring1-5。
2. **P0-Z1/Z2/Z3**：zone 清空判据落地——retention 调用点+观测协议（machine-runner 清单补步骤）、`tilesTruncated` 协议（走近再观测）、`unknown` 格定桶（T-6 探针先行）。**这是目标1②"连续 2 天复核保持清空"的前置**；Z3 不修则验收可能新型假 PASS。
3. **P0-U1/U2**：铜斧链取证——T-6 探针（背包逐格含 (O)334 + clump 分布 + Clint 货架）是全部后续决策的输入；据结果定"升级链"时间盒或如实判冬季【无法判定】。
4. **P1-R1**：review prompt 补 checks/ended_by（目标2②的 LLM 侧闭环）。
5. **P1-补充A**：surplus 清障落地（observer 早前 2.1/2.2，仍未闭环）。
6. **P1-补充B/E4**：经济聚合口径 + "两头平衡"最小证据集由 Lead 定稿。
7. **P1-C1/C2**：A9/B9 真对照（跑完后自然产出，重点是 B-LS 字节拷贝与 L1 口径预核对）。
8. **P2-5.1 简报补事实**（当季可种/工具等级）、Z4 `day_end.zone_clear` 接线。

---

## 7. 已知限制（如实）

- 本文所有动态证据 = **静态代码 + 今日账本/journal 实证 + 最小观测复跑**；未跑真机、未起长跑（observer 纪律）。
- 背包**全文**（`(O)334` 是否持有、12 格都是什么）在今日账本里不存在（baseline 只有 seeds 段）⇒ 铜矿持有量【无法判定】，等 T-6。
- `kind="unknown"` 12 格的 `Feature`（C# 类型名）未在任何落盘证据里出现过 ⇒ 它是什么【无法判定】，等 T-6；在定桶前不猜。
- Clint 是否卖铜矿/煤【无法判定】（协议 §2 的 6275g 预算建立在未证假设上）。
- 冬季守卫"钱够"口径与货架实价不一致一事涉及判据真值，按条目 097 留 **Lead 单独裁决**，本文只记事实。
- 工作树未提交改动（task-240b +7 行、条目 097、`_release-0.7.50.md`）不在本文判决范围；本文结论对已提交 HEAD `590f154` 成立。
- `runA9-0749.jsonl`（12:54 首跑）无 `finish` 行、无裁决文档（前任会话中断），条目 097 为补记。

## 附录：本文复核命令（均已执行）

```
1) PYTHONUTF8=1 python scratch/obs_t4_economy.py            # 五账本经济事件统计
2) PYTHONUTF8=1 python scratch/obs_t4_economy2.py           # buy/sell/upgrade 逐行原文
3) PYTHONUTF8=1 python scratch/obs_t4_zone.py               # D1 修复后 zone 口径 + retention 端到端
4) PYTHONUTF8=1 PYTHONPATH=brain python tools/compare-runs.py --run-a logs/runA9-0749-fix.jsonl \
       --run-b logs/runA9-0749-spring.jsonl --days 3        # L0–L5 试跑
5) grep blocked_by_tool / seed_gate / tool_upgrade_skipped（五账本逐事件统计）
6) git log --oneline -25 ; git diff brain/agentfarm/longrun.py   # 基线与未提交改动核对
7) sed -n '760,1130p' scratch/t204-il-up-1-u8.txt           # ResourceClump.performToolAction 掉落 IL
```
