# run7 独立分类复核（task-87，log-analyst）

- 账本：`logs/longrun-3day-llm-run7.jsonl`（1230 行 / 582,929 B / 2026-10-14 23:18:29；`bad_lines=0`）
- 命令（两侧同一条账本，均可复跑）：
  ```
  python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run7.jsonl
  python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run7.jsonl --json --top 0   # 全量条目
  python tools\verify-run3.py      --journal logs\longrun-3day-llm-run7.jsonl
  ```
- 留档：`scratch\_r7_analyze.txt`（文本）、`scratch\_r7_analyze_all.json`（`--top 0` 全量）、`scratch\_r7_verify.txt`、`scratch\_r7_map.txt`（逐日逐事件拉平，由 `scratch\_r7_map.py` 生成）、`scratch\_r7_chain.txt`（`water_far`/`day_end`/`idle` 链路明细）、`scratch\_r7_redsplit.txt`（红条目窗口内外拆分）

## 0. 一句话结论

**run7 的质量事实两侧一致**（尾部 summer 7/8/9 连续三天真 VERIFIED；早期 summer 3/5/6 确实有问题），**但 rc 与判红陈述不同向**：`verify-run3`（新尾部窗口口径）判 **VERIFIED / rc=0**，我的工具判 **138 条红 / rc=1**。差异全部落在三处口径：①我的工具**没有窗口概念**（125/132 个红行号来自窗口外）；②`missed:cancel|stage_no_target|stage_exhausted|plot_exhausted` 是**事件级**判红，缺"当天是否已结清"这一层（窗口内 7 条红全是这类，而对应三天 `verified=true`、`no_unmet_stages=true`）；③`wasted:finish_incoherent` 对 `--days` 参数敏感（`--days 7` 才出现，默认 3 天时无）。run7 里最贵的真实缺陷只有一条：**"窗口外 + A* 够不着"的那格干作物一直留在守卫的"还有活"理由里**，先后烧掉 summer 3、summer 5 两个整天，并在 summer 6 触发 63 次空转后才靠 task-73 翻篇救回。

## 1. 两侧并排

| 项 | `analyze-longrun.py` | `verify-run3.py`（`7c4ff68` 尾部窗口口径） |
| --- | --- | --- |
| rc | **1** | **0** |
| 结论 | 138 条红（132 个行号；**窗口内 7 / 窗口外 125**） | **VERIFIED**（尾部连续 3 天；窗口外 9 条降级 `history_problems`） |
| 六类全量计数 | manual 0 / missed **138** / wasted 14 / ineffective 1 / sleep 14 / environment 80 | — |
| `day_start` / `day_end` | 7 / 7 | 7 / 7 |
| VERIFIED 天数 | 4 / 7（summer 4/7/8/9） | 尾部 3 连续（summer 7/8/9） |
| `decision` | 217（decisions_llm=27、used=27、无 truncated） | 217 条（LLM 调用 27 / 模型产出 27） |
| `sleep` | 7（ok 7 / failed 0） | 7 次 |
| `no_day_progress` | 0 | —（无该问题行） |
| `blocked` | 0 | — |
| `unreachable` | 14 事件 / 12 格；日级最后一天 count=4、bound=27、bound_basis 自算=138 | 逐日账本/自算一致：3→1、4→0、5→8、6→1、7→4、8→0、9→0（summer 5 exempt=1、6 exempt=1） |
| `encircled` | 0 次 / 0 格 | 每天 0 格 |
| `frontier_clear` | 20 次（**真清掉 20 / 没清掉 0**） | summer 6：20 次（真清掉 20） |
| `clear_neighbor` | 67 条阶段级 / opens=76 | summer 5：1、6：64、7：2 |
| `stuck_flush` | 1 次（L1010，ok=1、skipped=0） | 1 天 / ×1、`stuck_flush_skipped` ×0 |
| `seed_gate` | **5** | （逐日信息里未单列） |
| `buy` / `sell` | **0 / 0 条事件** | — |
| `unmapped_events` | **{}**（0 条） | — |
| `tool_refused` / `unreachable_summary` | 3 / 4 | summer 3：3 次 3 格 / 逐日汇总齐全 |

红条目按天（`scratch\_r7_map.txt`）：summer 3 **27**、summer 4 **2**、summer 5 **29**、summer 6 **67**（= 125 行窗口外）、summer 7 **4**、summer 8 **2**、summer 9 **1**（+`--days 7` 时 finish 行 1 条 = 8）。

## 2. 逐日逐事件分类（设计内 / 缺陷）

### 2.1 summer 3 / 5：`water_far` → `far_dry_given_up`（够不着那格干作物）

链路（`scratch\_r7_chain.txt`）：

- `water_far` 共 25 条，其中 23 条 `ok=true`（窗口外干作物逐格走过去浇掉了，例 L2 `[39,19]`「已浇（水 23→22）」）。
- 同一个格 `[12,30]` 失败 4 对、8 条（L14/15、L212/213、L437/438、L1016/1017），每条 `ok=false, code="unreachable", walked=false`，`try_=1/2, limit=2`，第 2 次后 **`given_up=true`**。
- `plot_exhausted` summer 3 出现 11 次，note 明写「这一片没目标了，但守卫仍要求干活（农场口径还有 1 格干作物，其中 1 格在玩家窗口之外（Mod 报的坐标 `[[12,30]]`；**已试 2 次都够不着，当天不再重试**）…）⇒ 换一片地」。
- `day_end` summer 3（L174）与 summer 5（L434）：`ended_by="sleep"` 但 `ended_reason` 前缀是 `stuck:`「换过 11 片地都没有目标（守卫仍说还有活：农场口径还有 1 格干作物，其中 1 格在玩家窗口之外…）」；两天 `verified=false`、`checks.watered_outdoor=false`。

**判定**
- `water_far` 有界重试（limit=2）+ 当天不再重试：**设计内**（task-50，避免在一格上无限烧时间）。
- `plot_exhausted` 换片地兜底：**设计内**。
- **`far_dry_given_up` 之后该格仍留在守卫的"还有活"理由里 ⇒ 缺陷**：守卫 (`sleep_guard` / `_farm_scope_work` 一线) 用 `farm.dryCrops>0` 当"还有活"，而这一格已被证明 A* 够不着且当天放弃 ⇒ 整天的意图生成都在追一个物理不可达的目标，最终只能靠"换完 11 片地"或翻篇收场。这是 run7 里**唯一一条能解释整天损失**的链。
- 同一条链在 summer 8/9 也出现（`water_far` `[12,30]` 仍在），但那两天收尾 `farm dry=0`、`verified=true` ⇒ 是否致命取决于当天时序（见 §5 U1，**未定**）。

### 2.2 summer 6：`idle` ×63 → `frontier_clear` ×20 → `stuck_flush`

链路（`scratch\_r7_chain.txt` / `scratch\_r7_map.txt`）：

- summer 6 事件：`idle` **63**（其中 **21 条 `rounds=3`**，全部是 `intents=["water_area"], zone="field_nw", acted=false`，时间从 t≈939 到 t≈1040）、`unreachable_stage` 64、`clear_neighbor` 64、`frontier_clear` 20、`stage_exhausted` 65、`policy` 65。
- `day_end` L1013：`ended_by="stuck"`、`ended_reason`「连续 3 轮世界没有任何变化（最后意图：['water_area']；策略说有进展：False）；守卫仍说还有活：有 1 格作物没浇水；field_nw还有地要清/开/种」。
- `stuck_flush` L1010：`ok=true, count=1, limit=2, day_after=[1,"summer",7]`，note 明写"刻意绕过 `sleep_guard` 睡过去，让整轮继续跑下一天；本日仍如实计 stuck"。

**判定**
- `idle` 的 3 轮无变化 ⇒ stuck 判定、`frontier_clear` 开路尝试、`stuck_flush` 有界翻篇：**都是设计内**（task-68/task-73），且翻篇日仍 `verified=false`、不洗白 —— 设计意图完全达到。
- **缺陷（成本侧）**：63 次 idle（21×3）与 20 次开路全部花在同一个够不着的目标上（`water_area @ field_nw`，根因同上 §2.1），t≈790→1062 约 **4.5 分钟**空转；`frontier_clear` 20 次全部"真清掉"（说明开路本身有效，只是开的是一条通往不可达目标的走廊）。

### 2.3 summer 8 / 9：`stage_no_target` / `stage_exhausted` / `cancel:till_area`

- L1212 `stage_no_target(stage=till_area, zone=field_ne, leftover=0)`、L1213 `stage_exhausted(till_area, leftover=0)`、L1224 `cancel:till_area @ field_ne`「看得见却没有一格可动目标」。
- `seed_gate` 5 次（seeds=0、money=14、seed_price=20），day_end note：「没种子也没钱（种子 0 粒、钱 14g < 单价 20g）⇒ 今天不再开垦/播种：till_area 没有目标（锄了也种不下去 = 纯烧体力）」。

**判定**：**设计内**（种子/经济闸门 + 阶段无目标）。但我的工具把这 3 条判成"该做没做"红 —— 见 §4 第 2 条（口径问题，不是行为问题）。

## 3. 新事件桶核对

- `unmapped_events = {}`（**0 条**）✓：task-76 之后无漂移；run7 头部"新事件计数"逐项可见：`goto_farm=6、plot_walks=6、resume_walks=30、water_fars=25、seed_gates=5、stage_midway_leftover=6、unreachable=14、unreachable_stages=69、unreachable_summaries=4、tool_refused=3、refused_stages=1、refused_summaries=1、frontier_clears=20、clear_neighbors=67、stuck_flushes=1`。
- `buy`：run7 里是 **0 条事件**（不是"0 次成交"）——`seed_gate`（5 次，seeds=0 / money=14 / seed_price=20）在 till/plant 之前就把阶段挡掉了，大脑从未发起购买。
  - 我的工具呈现：不出现 `购买:` 行（0 事件）、`seed_economy.total=0`、**不判红、不进"任务失败"** ✓（卡面要求满足）。
  - 但"钱不够"只在 `seed_gate` 的 `money`/`seed_price` 字段与 day_end note（"没种子且钱不够（14g < 20g）"）里，工具侧**没有一句人话点名**；且 task-67 的 `cannot_afford` 事件本跑 **0 条**（`seed_gate` 早退把经济事件短路了）⇒ 见 §5 建议 3。
- `sell`：0 条（无收获、无出货；task-42 通道未被触发）——与设计一致。

## 4. 对 2026-10-15 新口径（尾部窗口 VERIFIED）的表态

**不同向**，且我能把差异定位到具体字典/闸门（三处，按解释力排序）：

1. **窗口口径缺失（scope，解释 125/132 个红行号）**：`verify-run3.py` `7c4ff68` 只对**尾部窗口**（run7 = summer 7/8/9）判达标，窗口外的问题降级为 `history_problems`（run7 9 条，不影响 rc）；我的工具**没有窗口概念**，7 天一律计入红。⇒ run7 旧口径 needs_review / 新口径 VERIFIED 的变化，我的工具完全没跟上。
2. **事件级 class-1 缺"已结清"层（dictionary，解释窗口内全部 7 条红）**：窗口内我判 7 条红 —— L1026 `cancel:till_area`、L1078 `stage_exhausted(water_area, leftover=1)`、L1145 `stage_exhausted(clear_area, leftover=3)`、L1179 `plot_exhausted`、L1212 `stage_no_target(till_area, 0)`、L1213 `stage_exhausted(till_area, 0)`、L1224 `cancel:till_area`。这三天 `day_end.verified=true`、`no_unmet_stages=true`，且 verify-run3 的逐日 info 明确写了"阶段当天共 N 条记录：更早一轮 leftover=…、最后一轮 0 ⇒ 按日级口径以最后一轮为准（**遮蔽已显式列出**）" ⇒ 这些事件是**瞬间态**，当天随后结清了。我的 `missed:cancel|stage_no_target|stage_exhausted|plot_exhausted` 只看事件、不看当天是否结清，所以把"设计内的阶段无目标/意图取消"读成了"该做没做"。
3. **`wasted:finish_incoherent` 对 `--days` 参数敏感（规则）**：`finish{code=0, verified_streak=3}` 与 `--days 7` 相比 ⇒ 判"自述与正文不同向"；默认 `--days 3` 时无此红。规则应比"**目标窗口天数**"（默认 3）而不是"账本里的天数"，否则参数一变就多出一条假红。

**需要改的是我的工具，不是 `verify-run3`**：两工具对"质量事实"（尾部三天真 VERIFIED、早期三天真有问题）没有分歧，分歧只在"如何把事实折算成 rc/红"。run8 前建议按 §5 的 1、2 条改我这边（`--window N` 默认 3 + out-of-window → `history_problems`；class-1 事件"同日已结清"降级为 info），改完 run7 上我的窗口内红应从 7 → 0、rc 与 verify-run3 同向（0），窗口外仍逐条列出（不丢失信息）。

## 5. 建议 run8 优先修什么（≤3，按收益）

1. **守卫理由集合剔除"已证明够不着"的干格（brain 侧，收益最高）**：`water_far` → `far_dry_given_up`（`try_` 达 limit 且 `code=unreachable`）之后，该格不应再作为 `sleep_guard`/"还有活"的理由（或直接计入 `unreachable` 当日豁免）。run7 实证成本：summer 3、summer 5 各烧一整天（`ended_reason` 前缀 `stuck:`、`verified=false`），summer 6 因此空转 63 次才翻篇。验收：run8 里出现 `given_up=true` 的当天不再以 `stuck:` 收尾、`idle` 总数与 `plot_exhausted` 次数显著下降。
2. **我的工具窗口化 + "已结清"降级（分析侧，收益高）**：新增 `--window N`（默认 3，与 `verify-run3` 尾部窗口同义），窗口外红降级为 `history_problems`；`missed:cancel|stage_no_target|stage_exhausted|plot_exhausted` 仅在"当天未 VERIFIED 或该阶段/任务当天再未成功"时判红，否则记 info（标 `(已结清)`）；同时修 `wasted:finish_incoherent` 的 `--days` 参数敏感（比目标窗口天数，或降 info）。验收：run7 上窗口内红 7 → 0、rc=0 与 verify-run3 同向；summer 6 的 67 条如实保留（那天确实 stuck 未 VERIFIED）。
3. **种子经济"钱不够"呈现 + brain 事件补齐（中收益）**：`seed_gate` 且 `seeds==0 && money < seed_price` ⇒ 一行 info「买不起（money 14 < seed_price 20）⇒ till/plant 被跳过，不是任务失败」；并建议 brain 在 `seed_gate` 早退路径上也写一次 `cannot_afford`（task-67 通道，本跑 0 条）。验收：run8 报告里"钱不够"一眼可见、不计失败、`seed_economy` 不再恒 0。

## 6. 未定项 / 限制

- **U1**：summer 8/9 同样有 `water_far [12,30]`（`farm.dryCrops 6→6` 未下降），但当天 `farm dry=0` 收尾且 `verified=true`；summer 3/5 却以 `watered_outdoor=false` 收尾。是那格后来被浇上、还是 mod 的 `dryTiles` 口径/时序变化？账本没有逐格 `before/after` 差分，**未定**（需要 run8 抓 `day_end.final_water` 与 `tiles[]` 差分）。
- **U2**：`water_far` 事件里 `ok=false` 的同时 `status:"ok"`（L14/15 等）——字段语义是否刻意（`status` 指通道可用、`ok` 指这一格结果）未定；若是笔误，会削弱"够不着"这一证据链的可读性。
- **U3**：run7 里 `blocked` 事件 0 条，但有 `tool_refused` 3 条；被拒是否也应同时进 `blocked`（供第 3 类"无效挥动"归因）**未定**。
- **限制**：本复核全部基于账本与两个只读工具的输出，未接触游戏/桥，也未改任何 `tools/`、`brain/` 文件；工具行为未在 run7 上做任何修改（task-87 纪律）。
