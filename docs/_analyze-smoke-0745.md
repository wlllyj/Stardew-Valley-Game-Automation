# 0.7.45 首个真机冒烟账本分析（task-24）

**一句话**：`logs/longrun-smoke-0745.jsonl`（650 行 / 0 坏行 / 2 天 winter 26-27）在两处新机制上给出了正确读数——`pending` 七口径两天**不变式全成立**（0 违背）、背包压力**留痕完整**（226 步掉落被拒收）；但 `resume_exhausted` 收工那天仍留 **7 格 `pending_executable`**（与原文「当前观测里没有可执行目标」不一致），且冬 26 的 `day_justified=false` 是 `inventory_blocked` 不在白名单的设计行为 ⇒ **info 只点名、不进 rc；rc=1 / 红 63 / #无法判定 100 均由旧判据产生，本卡 0 新增红**。

- 判决（analyzer 口径）：rc=1、红 63 条、subjects 8 个、`#无法判定` 100 条、窗口未激活（尾部连续 VERIFIED 0 天 ⇒ 窗口外也照常 fatal）。
- `verify-run3.py` 仍是判决权威；本工具只做读数与归因。

## 1. 账本骨架

| 行 | 事件 | 读数 |
| --- | --- | --- |
| L1 / L231 | `day_start` / `day_end`（winter 26） | `verified=false`、`ended_by=inventory_blocked`、`ended_reason` 前缀 `inventory_blocked:` |
| L232 / L647 | `day_start` / `day_end`（winter 27） | `verified=false`、`ended_by=sleep`、`ended_reason` 前缀 `resume_exhausted:` |
| L226 / L643 | `sleep` | 均 `ok=true`（两天都真睡成：`slept_ok=true`、`checks.slept_by_us=true`） |
| L648 / L650 | `day_cap` / `finish` | `days=2/max_days=2`；`finish.code=1` |

- 行数 650（可解析 650、坏行 0）；`day_start` 2 次、`day_end` 2 次、`VERIFIED 0/2`。
- `checks` 两天均为：`slept_by_us/no_blocking_modal/no_hard_failures/refused_within_bound/no_unmet_stages/crops_watered/watered_outdoor/zero_action_evidenced=true`，**`day_justified=false`**；差别只有 `unreachable_within_bound`（冬 26=false、冬 27=true）。
- 冬 26 收工原文（L231）：`inventory_blocked:背包满（空格 1）且今天已经腾不出格子：不是没活、也不是 stuck —— 是背包堵住（先去出货/卖材料腾格，明天再收）`
- 冬 27 收工原文（L647）：`resume_exhausted:回片区 220 格都回去看过、换片 4 次，当前观测里没有可执行目标（守卫仍说：今天早些时候还有 7 格没做完（跨片地，最近的是 [31, 42]））`

## 2. ① `pending` 七口径：不变式闭合，但「残余 7 格」未闭合

| 列（day_end 键） | 冬 26（L231） | 冬 27（L647） |
| --- | --- | --- |
| `pending_ledger`（账本） | 3 | **230** |
| `pending_guard`（守卫） | 3 | **7** |
| `pending_stalled`（停滞） | 0 | **218** |
| `pending_executable`（可执行） | 0 | **7** |
| `pending_blocked`（已判死） | 0 | **223** |
| `pending_unobserved`（看不见） | 3 | 0 |
| `pending_malformed`（残缺） | 0 | 0 |
| 不变式 `ledger == guard + blocked` | 3 = 3 + 0 ✅ | 230 = 7 + 223 ✅ |
| 不变式 `guard == exec + unobs + malformed` | 3 = 0 + 3 + 0 ✅ | 7 = 7 + 0 + 0 ✅ |

- 两天不变式违背 **0 / 0**（`pending_caliber.violations_ledger=0`、`violations_guard=0`），`pending_caliber.state=found`。
- **与 task-15 归属表（0.7.44 同一玩法、同一天数）对照**：

| 口径 | 0.7.44 冒烟（task-15/17） | 0.7.45 冒烟（本账本） | 结论 |
| --- | --- | --- | --- |
| 守卫累计 pending | 263 / 217 | **3 / 7** | 修复生效：冬 27 从「累计 217」收窄到「当前可执行 7」 |
| 日级 `plot_pending*` | 0 / 0（最后一轮遮蔽） | **15（exec 3 / blocked 12）/ 1（exec 0 / blocked 1）** | 不再全 0；但 day 级仍取「每阶段最后一条」，与快照不同源 |
| `pending_ledger` | —（0.7.44 无此键） | 3 / 230 | 冬 27 = 220（旧 stage 余格）**+10**，多出的 10 格来源账本无标记 ⇒【无法判定】（喂 task-15 复核） |
| 停滞 / 已判死 | 停滞 261 / 217 | 停滞 218 / **判死 223** | 冬 27 判死比停滞多 **5 格**（`223−218`），这 5 格为何没进停滞集合，字段未单列 ⇒【无法判定】 |

- **仍未闭合的一处（最要紧，喂 task-15/16）**：冬 27 `pending_executable=7 > 0`，而 `ended_reason` 原文说「当前观测里没有可执行目标（守卫仍说 7 格没做完）」⇒ 0.7.45 的诚实收工判据（`pending_executable==0`）**没有通过**，`day_justified=false` 是 fail-closed 的正确结果；这 7 格坐标只能从 `no_progress_burst.samples`（L641，见下）读到 `[30,47]/[31,42]/[31,43]/[31,46]…`，账本没有逐格终态 ⇒ 需要 task-15/16 继续定位「为什么它们仍算可执行」。本工具**只报数、不猜**。
- `plot_pending_executable=3`（冬 26，来自 `till_area` 最后一条 stage 记录）与 `pending_executable=0`（快照）仍不同源：冬 26 的 `stage_midway_leftover` 8 条（最大轮 17、最大余格 7）说明「最后一轮口径」仍会遮蔽；快照把 3 格归入「看不见」⇒ 具体归属【无法判定】。

## 3. ② `day_justified` × `pending_executable` × `pending_malformed` 自洽性

`justified_evidence`（只 info、不改判、不进 rc）读数：

| 天 | `day_justified` | exec | malformed | 前缀 | 可疑点名 |
| --- | --- | --- | --- | --- | --- |
| 冬 26（L231） | false | 0 | 0 | `other`（inventory_blocked） | **是**（`suspicious_unjustified_no_work`） |
| 冬 27（L647） | false | **7** | 0 | `resume_exhausted` | 否（exec>0 ⇒ 不属于「没活却不判」形态） |

- 两天 `malformed` 都是 0、没有「`day_justified=true` 却 exec>0/None」的天。
- 冬 26 的可疑点名**不是 bug**：`inventory_blocked` 从设计上就不在 `JUSTIFIED_END_REASONS = ("night","stamina","no_work")`、也不在 `HONEST_EXHAUSTED_END_REASONS = ("resume_exhausted",)`（brain `:553`/`:567`/`:6335` 明确注释「不在白名单 ⇒ day_justified=False」）⇒ 该天是被「背包堵住」的诚实上限，`day_justified=false` 属设计行为。本探针按 `exec=0 & day_justified=false` 机械点名，人判时需用 `ended_by` 扣除；**不改判、不进 rc**。
- 冬 27 的 false 才是真信号：`exec=7` ⇒ 诚实收工判据没过（见 §2 未闭合项）。

## 4. ③ 背包压力：留痕完整（这是本账本第二个正确读数）

- 两天 `free_slots_start=0`、`free_slots_min=0`、`free_slots_status=ok`；冬 26 日终 `free_slots_last=1`（卖 1 叠成功腾出 1 格，L239），冬 27 日终仍 0。
- `loot_lost_steps/tiles`：冬 26 **21 步 / 21 格**、冬 27 **205 步 / 205 格** ⇒ 两天共 **226 步 / 226 格**掉落被游戏拒收；`loot_lost_items` 近似 `[木材, 树液, 石头, 纤维,（可能）干草,（可能）矿石,（可能）硬木]`（带「（可能）」= 逐格掉落是概率表，账本不做确定断言）。
- `slot_relief` 压力通道 5 次：L6、L9、L239、L257、L258；`need=0`、`freed=0/0/1/0/0`、`trigger=space_pressure×3 / none×2`、`demand_basis={space_pressure:3, buy_full:2}`。
  - L6/L239：`space_pressure`（清障/浇水前先腾格，掉落会被拒收）；L9/L258：`buy_full`（买种子前背包满且腾不出 ⇒ **不买**，避免白开 ShopMenu）；L257：满包且腾不出 ⇒ **不判失败**、日循环继续（清障/浇水照做），逐格 `loot_lost` 留痕。
- 冬 26 因背包满收工：L7 `inventory_blocked`（`卖了 1 叠但背包行数没减少（12→12）⇒ 出货/卖出没有真的生效`），`ended_by=inventory_blocked`；`failed_steps=0`。
- 结论：两天都是**真背包满**，0.7.45 的 `free_slots_*`/`loot_lost_*`/`slot_relief` 三处读数互相一致，`bag_pressure.state=found`、无 `unavailable_days`。

## 5. ④ already-aware 双列（ok 必须与 already 并读）

- 总计：94 段 stage 里 **22 段 `ok=0`**，其中 **3 段 `ok=0 且 already>0`（1 天，冬 26）**；`ok` 合计 **243**、`already` 合计 **96**；`already_stages=33`。
- 冬 26 明细（3 段，`clear_area`）：格 `[[6,36], [25,44], [33,33], [34,33], [35,32]]`（5 格）；该天 ok 合计 33 / already 合计 14。
- 冬 27：`ok0_already=0`（74 段、ok 210 / already 82）。
- 口径不变（task-13）：`ok` = 真世界变化数、`already` = 本来就不用做的格 ⇒ **`ok=0` 不代表白干**，A9 判决必须两列并读；`window` 两天与总量相同（账本只有 2 天）。

## 5b. 售材白名单纪律冲突证据（Lead m01932 问 ③ 追加；账本侧只报数字）

`strategy=slot_relief_space` / `why=space_pressure` 的 `sell` 事件共 **10 条**（成功 **9**、失败 1）：

| 行 | 天 | qid / 物品 | 叠数 | 结果 | `after.shipping_bin` |
| --- | --- | --- | --- | --- | --- |
| L5 | 冬 26 | (O)262 Wheat | 5 | ok | 1 |
| L8 | 冬 26 | (O)310 Maple Seed（槽位显示 (O)262，Mod `status=not_whitelisted`） | 5 | **failed** | 1 |
| L35 | 冬 26 | **(O)330 Clay 黏土** | 3 | ok | 2 |
| L41 | 冬 26 | (O)92 Sap | 1 | ok | 3 |
| L61 | 冬 26 | **(O)388 Wood 木材** | 1 | ok | 4 |
| L72 | 冬 26 | **(O)388 Wood 木材** | 31 | ok | 5 |
| L81 | 冬 26 | **(O)388 Wood 木材** | 2 | ok | 6 |
| L86 | 冬 26 | **(O)388 Wood 木材** | 46 | ok | 7 |
| L95 | 冬 26 | (O)535 Geode | 3 | ok | 8 |
| L238 | 冬 27 | **(O)388 Wood 木材** | 12 | ok | 1（跨日重新计数） |

- **建材被卖合计：Wood 92 件（冬 26 80 / 冬 27 12）+ Clay 3 件（冬 26）= 95 件**；9 叠成功出货里 **5 叠是建材**。
- `before.whitelist` 原文显示当时 Mod **把 `(O)388`/`(O)330` 列入可卖白名单**（L35 `["(O)330"]`、L61/72/81/86/238 `["(O)388"]`）⇒ 与 AGENTS §5「建材/建造预留永不卖」的纪律冲突（Lead 已裁决为纪律问题，不在本卡改判）。
- 预留逻辑只在**后段**拦住：L257（冬 27）`reason=剩下的可卖叠都是建造预留材料（铜矿/石头/煤），卖空会破坏熔炉/升级计划 ⇒ 宁可不腾格`；冬 26 与冬 27 早段的 Wood/Clay 已卖出（L35/L61/L72/L81/L86/L238）。
- 出货箱差分：`after.shipping_bin` 冬 26 依次 1→8（与成功 8 次一致）、冬 27 为 1（1 次）；钱 2767（L1）→3264（L232）= **+497g 于 NewDay 结算**，但账本 `sell` 事件无单价 ⇒「497g 里多少来自建材」**无法判定**。
- 供 0.7.46 复验：售材白名单收紧后，上述 5 行（L35/L61/L72/L81/L86/L238）的 qid 不应再出现。

## 6. 其余聚合读数（全 info、不进 rc）

| 聚合 | 读数 |
| --- | --- |
| `resume_exhausted`（新前缀） | `found` 1 天（冬 27 L647；`switches=4`、`burst_lines=[641]`、`burst_count=0`、`burst_switches=[4]`、`burst_stalled=[220]`）；旧 `stuck:` 前缀 0 天 |
| `workspot_resume_exhausted`（task-3 旧块） | `zero`（机制事件在场但没有「连续 5 次拿不出目标」形态 ⇒ 0 是真实读数） |
| `no_progress_burst` | 1 条（L641）：`source=回片区（switch_limit）`、`count=0`、`exhausted=true`、`tiles=7`、`pending=225`、`pending_ledger=230`、`stalled_tiles=220`、`newly_stalled=0`、`switches=4`、`farm_actions_today=311`、`samples` 含 `[30,47]/[31,42]/[31,43]/[31,46]…`（7 格可回看） |
| `stage_realloc`（封格） | `zero` / 0 事件；`stage_capped=0`（94 段 `alloc_capped_tiles` 全空 ⇒ 0 次封格） |
| `leftover_split`（余格拆分） | `ok`：94/94 段带拆分、`mismatch=0`；可执行 300 / 挡死 47 / leftover 347 格 |
| `slept_ok` | true 2 天 / false 0 / 缺字段 0 |
| `budget_suppressed` | `found` 2 天（各 `suppressed=1`、`deferred_by_budget=false`、`events=0`、`conflict_days=[]`） |
| `midway_masking` | `found`：8 条 / 1 天（冬 26，`max_round=17`、`max_leftover=7`，事件 L229）；冬 27 空数组 |
| `plots_capped` | 2 次（L132 冬 26、L345 冬 27，均 `plots_today=10/limit=10`） |
| `guard_count`（task-17） | `zero` 0 天（本账本 `plot_pending*` 不再是 0 ⇒ 旧「守卫计数口径」形态不成立，0 是真实读数） |
| `stage_churn` / `stuck_without_sleep` | 0 / 0（无对应形态） |

## 7. 回归对照（基线 = `80488c8~1` 的 analyzer，未收 0.7.45 字段）

| 账本 | 基线 rc/红/#无法判定 | 新版 rc/红/#无法判定 | Δ红 | Δ无法判定 |
| --- | --- | --- | --- | --- |
| runA | 1/117/128 | 1/117/146 | +0 | +18 |
| runB | 1/84/133 | 1/84/151 | +0 | +18 |
| run9 | 1/84/151 | 1/84/169 | +0 | +18 |
| run9b | 1/45/151 | 1/45/169 | +0 | +18 |
| run9c | 0/0/138 | 0/0/156 | +0 | +18 |
| run9d | 1/29/125 | 1/29/143 | +0 | +18 |
| A8（0.7.43） | 1/35/118 | 1/35/136 | +0 | +18 |
| smoke-0744（0.7.44） | 1/33/105 | 1/33/123 | +0 | +18 |
| **smoke-0745（0.7.45）** | 1/63/100 | 1/63/100 | **+0** | **+0** |

- **六旧账本 rc/红数一字未变**；`#无法判定` 各 +18 = 本卡新增 18 条探针在这些旧账本里 0 命中（缺失 ≠ 0）。
- 0.7.45 真账本 `#无法判定` 增量 0：18 条新探针在本账本**全部命中**，这正是「新字段真落盘」的直接证据。

## 8. 四问结论（task-24 交付口径）

1. **`pending` 七口径闭合**：两天不变式 0 违背、字段全在场；但与 task-15 的 263/217 数字**不再对应**（修复后 3/7），且冬 27 仍有 `executable=7` 未消——需要 task-15/16 继续定位「7 格为何仍算可执行」与「加 10 格 `ledger` 来源」。
2. **`day_justified` 自洽性**：冬 26 false+exec0 是 `inventory_blocked` 白名单设计（info 点名、非 bug）；冬 27 false+exec7 是 fail-closed 正确结果（诚实收工判据没过）；`malformed` 两天 0、无「true 却 exec>0」。
3. **背包压力留痕**：完整（`free_slots`/`loot_lost`/`slot_relief` 三处一致），两天都是真背包满；冬 26 因此早停，不是失败。**售材纪律冲突见 §5b**：9 叠成功出货中 5 叠为建材（Wood 92 + Clay 3 件，L35/L61/L72/L81/L86/L238），账本侧如实报、由 0.7.46 白名单收紧后复验。
4. **already 双列**：3 段 / 1 天 / 5 格，`ok=0` 不可单独读；`ok 243 / already 96` 必须并读。

## 9. 已知限制 /【无法判定】

- 冬 27 `blocked(223) − stalled(218) = 5` 格：已判死但未在停滞集合，账本未单列坐标 ⇒【无法判定】。
- 冬 27 `pending_ledger=230` 比 0.7.44 同玩法 stage 余格 220 多 10 格：来源无标记 ⇒【无法判定】。
- 冬 26 `plot_pending_executable=3` 与快照 `executable=0` 不同源（阶段末条 vs 日终快照），3 格终态 ⇒【无法判定】。
- **层级不可对账（Lead m01955 口径增量）**：day 级 `pending_*` 七口径（冬 27：账本 230 / 守卫 7 / 判死 223 / 可执行 7）与 stage 级 `leftover_split`（冬 27：可执行余格 290 / 挡死 19）是**两个层级**，**不可互相加减或对账**；0.7.46 卡 B 对「7 格」逐格归因必须走 day 级 `pending_*`，拿 290/19 对账会误判。
- 渲染文案缺陷（`afford_blocked` 把「背包 0 种子 / 无当季种子」并进「缺种子钱」旧文案，`tools/analyze-longrun.py:8564-8568`）：Lead 已裁决属 analyser 文案缺陷、登 backlog task-10，**不影响红/rc，本卡不改**。
- `loot_lost_items` 含「（可能）」= 概率掉落，账本只做近似归因，不能当确定物品清单。

## 10. 复核命令

```
python -m py_compile tools\analyze-longrun.py
python -m unittest tests.test_analyze_longrun            # Ran 334 / OK
python -m unittest discover -s tests                     # Ran 1348 / OK
python tools\analyze-longrun.py --journal logs\longrun-smoke-0745.jsonl --days 2
python scratch\_t24_smoke0745.py                          # 六聚合 + 老聚合读数 → scratch\_t24_smoke0745_readings.json
python scratch\_t24_smoke0745_detail.py                   # day_end 字段/关键事件原文/stage 汇总
python scratch\_t24_check.py                              # 九账本基线(80488c8~1) vs 新版 rc/红/#无法判定
python scratch\_t24_compare_one.py logs\longrun-smoke-0745.jsonl   # 单账本旧/新 red subjects 逐项对照
python scratch\_t24_sell_audit.py                         # 出货逐件表 + 建材被卖（Wood/Clay）行号与 shipping_bin 差分
```
