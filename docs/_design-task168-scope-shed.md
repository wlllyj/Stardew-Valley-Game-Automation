# task-168 设计稿 rev2：规模取舍（scope shedding）—— 让"一天浇不完"变成**诚实、有界、可释放**的取舍

- 状态：**设计稿 rev2（未实现）**。实现要等 task-113（run B 证据）冻结后由 Lead 放行。
- rev2 变更：把 Lead 对五问的裁定全部折进来（见 §6「裁定记录」），并补 §5 的用例/变异骨架（伪代码）。
- 依据：`logs/longrun-runA-0732.jsonl`（run A 六天，只读）、现有代码（行号以 HEAD `3762936` 为准）。
- 纪律：本稿只写 `docs/`，未动 `brain/`、`mod/`、`tools/`、`tests/`、`logs/`。

---

## 0. 现象与算术（run A 账本实证）

`logs/longrun-runA-0732.jsonl` 的六条 `day_end`（`day` 字段 = `[1,'fall',N]`）：

| day | ended_by | ended_reason | ok_steps | failed | final_water(crops/dry) | budget live/reserve/capacity |
|---|---|---|---|---|---|---|
| fall 3 | sleep | `stamina:体力 0 < 12` | 65 | 1 | 142 / **73** | 142 / 296 / 0 |
| fall 4 | sleep | 同上 | 65 | 1 | 141 / **73** | 141 / 294 / 0 |
| fall 5 | sleep | 同上 | 65 | 1 | 140 / **72** | 140 / 292 / 0 |
| fall 6 | sleep | 同上 | 65 | 1 | 138 / **69** | 138 / 288 / 0 |
| fall 7 | night | `night:时间 2200 已经到夜里` | 1 | 31 | 125 / 0 | 137 / 286 / 0 |
| fall 8 | sleep_failed | 没有引出睡觉提问 | 15 | 44 | 118 / 0 | 122 / 256 / 4 |

- fall 3–6 四项 `checks` 全 false：`no_hard_failures` / `no_unmet_stages` / `crops_watered` / `watered_outdoor`。
- `deferred_by_budget` 在 **t=0.12（当天第一秒）** 就记了 `clear_area`：
  `体力 136 ≤ 浇水预备 296（142 格活苗 × 2 + 路程 12，basis=farm）⇒ 停手把体力留给浇水`，`tiles=183`；
  全天 `budget_deferred_tiles`/`deferred_by_budget` 族事件共 17 条，`deferred: [clear_area, till_area, plant_area]`。
- **算术**：`142 × STAMINA_COST_WATER(2.0) + PATH_STAMINA_ALLOWANCE(12) = 296 > maxStamina(270)`。
  即：**光是"把已有的活苗浇一遍"就超过一整管体力**；`capacity=0` 说明"再播种"这条路已经被 task-158 关掉，
  但**已有工作量没被缩小**，所以每天都停在 `dry≈70`、`stamina 0`、`verified=false`。
- 结论：这不是"预算不够"的问题（预算已经正确地不让人干新活），而是**当天任务规模 > 当天体力**的问题。
  唯一剩下的杠杆是**收缩当天的作业范围**，而且要诚实地记下来、并且**能释放**（§2.3）。

---

## 1. 事实入简报（让慢脑看得见"今天干不完"）

### 1.1 提案字段（`planner.Brief`，`brain/agentfarm/planner.py:1093-1144`）

| 字段 | 类型 | 含义 | 缺数据 |
|---|---|---|---|
| `live_crops` | `int \| None` | 全农场活苗数（`farm.crops`，与 `_farm_totals`/`_stamina_budget` 同口径） | `None` =【无法判定】 |
| `water_capacity` | `int \| None` | 一整管体力**最多能浇几格**：`floor((maxStamina − PATH_STAMINA_ALLOWANCE) / STAMINA_COST_WATER)` | `None` |
| `water_deficit` | `int \| None` | `max(0, live_crops − water_capacity)`，即"今天注定浇不完的格数" | `None` |

**硬规矩照旧**（与 `sellable`、`review_facts` 同一条诚实边界）：取不到就 `None` + 渲染「未观测到」，
**绝不写 0**；`None` 时下游一切"收缩"动作都不许发生（fail-closed，Lead 裁定 4）。

### 1.2 渲染位置：`base_lines()`，不是可选节

`Brief.base_lines()`（`planner.py:1165-1181`）是"一个字段都不许被挤掉"的本体；`situation_text()`
（`planner.py:1220-1243`）按 `教训库 > 决策史 > 复盘笔记` 追加可选节，塞不下就整节丢。
"活苗数 / 能浇几格 / 缺口"属于**核心事实**，必须进 `base_lines()`（例如紧跟 `counts=` 之后一行）：

```
water_budget: live_crops=142 water_capacity=129 water_deficit=13 (basis=farm)
```
不可判定时：`water_budget: live_crops=未观测到 water_capacity=未观测到 water_deficit=未观测到`。

### 1.3 真值来源（唯一实现，别抄第二份公式）

- 控制器已经算了这套数：`longrun._stamina_budget()`（`longrun.py:1857-1916`）产出
  `{max, stamina, live_crops, dry, water_reserve, water_cost_est, path_allowance, capacity, basis, ...}`。
  新字段**必须复用**它（只加 `water_capacity`/`water_deficit` 两个派生量），不要在 planner 里重抄常量。
- 注入点：`longrun._plot_brief()`（`longrun.py:2264-2330`）——它已经用 `replace(...)` 往 `Brief` 上补
  `counts`/`sellable`；在这里把三个新字段一起 `replace` 进去即可（`_plot_brief` 是每条边界决策的必经之路）。
- 为什么不让 `Brief.from_observe()`（`planner.py:1246-1320`）自己算：那会让 `planner` 依赖
  `farmwork.STAMINA_COST_*`（`farmwork.py:266-272`），而 `planner` 目前是纯策略层（**无 farmwork 依赖**）。
  代价：直接调 `from_observe()` 的地方（如 `agentfarm plan`）恒为 `None` ⇒ 与 `sellable` 一样，
  文档里注明"该场合并未观测"。

---

## 2. 收缩意图：`reduce_scope`（Lead 裁定：名字由我定 → **`reduce_scope`**）

### 2.1 名字与形状

- `TASK_KINDS`（`planner.py:96-...`）新增 `"reduce_scope"`；`target` = **具名田区**（`field_ne` 这种，
  名字来源是 `fields.zones_from_observe()`，planner 不认识坐标）。
- 粒度 = **田区**（Lead 裁定 2）；`expect`（验收写什么）=「该田区当天不再浇水、不再产生'还有活'理由；
  日终 journal `scope_shed{zone,...}`」。
- 与 `review` 的区别：`review` 是"没事可做"；`reduce_scope` 是"有事，但今天**主动不做**"。

### 2.2 确定性触发（`deterministic_plan`，`planner.py:1553-...`）

在 `harvest` 之后、`water_area` 之前插入：

```
if brief.water_deficit is not None and brief.water_deficit > 0 and len(brief.areas) >= 2:
    → TaskIntent("reduce_scope", area_with_most_tiles, ...)
```

取"最不划算"的片区用**可解释的确定性代理**（不引入新观测）：优先 `area_lines` 里格数最多、
且熟作物最少的片区（同格数时取 `areas` 字典序，保证可复现）。`water_deficit is None` ⇒ **不提议**。

### 2.3 代码怎么把它落成具体动作（`longrun`）

新增 `_shed_scope(obs, rep, zone)`：

1. **先收成熟作物**（复用已有 `harvest`）：`_stage_tiles("harvest")` 限定在该区格子上跑，成熟的先收掉。
   这是**唯一真正减少 `live_crops` 的动作**（Lead 裁定 1：**不拔苗**；拔除未熟作物被否——不可逆、
   直接损失未来收成、且与正在做的经济闭环互相打脸）。
2. **显式认输（粘但可释放）**：把该区记进 `self.shed_zones`（田区级），并**持久化**到
   `<journal>-scope.json`（Lead 裁定 3，格式见 §4.1）；journal
   `scope_shed{zone, tiles, live_crops, water_capacity, deficit, basis, reason, sticky}`，
   `rep.scope_shed = {...}`。
3. **释放条件（Lead 裁定 1/3）**：每天日初（或认输集合变化时）评估——
   `farm.live_crops <= water_capacity`（即 `deficit == 0`）**或** 该区已无活苗 ⇒ 把该区从认输集合里清空、
   重新纳入浇水目标，journal `scope_released{zone, reason}`（`reason ∈ {"no_deficit", "no_live_crops"}`）。
   于是"农场规模逐日收敛到体力能覆盖"是**可达**的：每天把排在前面的干作物浇上 → 成熟 → 收走 →
   `live_crops` 减少（**前提是 `harvest` 真能摘**，见 §3.1 前置依赖）。
4. **不再反复回去**：三处"目标池"必须剔除认输格，否则会重现 task-124/163 刚修完的病
   （"守卫说还有活、策略拿不出目标"⇒ 空转 ⇒ `stuck`）：
   - `_stage_tiles()`（`longrun.py:2655`）的 `water_area` 池；
   - `_pending_work()`（`longrun.py:2905`）——它是 `_resume_plot`/`work_spot` 的输入，不剔除就会**走回去**；
   - `_plot_has_work()`（`longrun.py:2128`）。
5. **守卫闭嘴**：`work_reasons()`（`longrun.py:2801`）的两条作物理由
   （`有 N 格作物没浇水` `:2822-2825`、`有 N 格作物熟了` `:2826-2828`）要**减去认输格**；
   `sleep_guard()`（`longrun.py:3185`）的 `unwatered` 分支（`:3198-3205`）与农场口径分支
   （`:3237-3253`）同样只数"未认输"的格子。
6. **收尾理由必须是它自己**：当"剩下的干作物全在认输区"时，守卫放行的 code 用 **`scope_shed`**
   （**不放进 `JUSTIFIED_END_REASONS`**，`longrun.py:317`）⇒ `day_justified=false` ⇒ 当天 `verified=false`。
   这正是"认输当天不达标"的如实表达（Lead 裁定 5），与 task-84 的 `gave_up_dry` 同构。

**会计口径（与 task-163 刻意不同，必须写死）**：认输格**留在会计里**（`_leftover` `longrun.py:2749`
照旧计入 `plot_pending`/`assigned_undone` ⇒ `no_unmet_stages=false`）；只有**目标池与守卫理由**剔除。
理由：task-163 的延后是"今天做不了"（体力），认输是"我们主动不做"——后者当天就不该算完成。

### 2.4 与既有闸门的相互作用

| 既有机制 | 位置 | 与 `reduce_scope` 的关系 |
|---|---|---|
| task-158 体力预算 | `_budget_defer_reason` `longrun.py:1949-1975` | 认输**先于**预算判定：认输区不再进浇水目标 ⇒ 浇水口径的 `live_crops` 下降 ⇒ `water_reserve` 下降 ⇒ 可能**解锁** clear/till/plant。这是本次取舍的**目的**，但两件事都要在账本里可见（`scope_shed` 与重算后的 `stamina_budget`）。 |
| task-163 延后口径 | `_budget_deferred_tasks` `longrun.py:2020`、`_leftover` `:2749`、`_pending_work` `:2905` | **刻意不同**（见上"会计口径"）：延后 ⇒ `_leftover` 返回空；认输 ⇒ `_leftover` 照旧。两者**不许合并计数**。 |
| `no_target` 记账 | `_mark_no_target` `longrun.py:899` | 认输**不得**记成 `no_target`/`stage_exhausted`（那是"拿不出目标"），必须有自己的事件名。 |
| `day_end` 判据 | `checks` `longrun.py:5556-5590` | **不新增任何 `checks` 键**（Lead 裁定 5）。认输的后果通过既有 `watered_outdoor`/`no_unmet_stages` 如实体现。 |
| 跨片地遗留 | `leftover_targets`/`_resume_plot` | 认输格不得进 `leftover_targets`（否则当晚/次日被走回去），也不得被 `resume` 清账逻辑"复活"。 |
| 教训库 | `_derive_lessons_path` `longrun.py:941-951`、`save_lessons_file` `planner.py:966-988` | **不混进 lessons**（Lead 裁定 3：那是"学到的东西"，这是"当前作业范围"）。落点见 §4.1。 |

### 2.5 有界（防"用认输把一天天做空"）

- 一天最多认输 **1 个田区**；
- 只在 `water_deficit > 0` 且 `basis == "farm"`（证据齐备）时允许（Lead 裁定 4：`conservative` ⇒ 不认输）；
- `live_crops <= water_capacity` ⇒ **拒绝**该意图，并把已是认输态的区域**释放**（§2.3 第 3 步）；
- 全 run 累计认输格 ≤ `SCOPE_SHED_MAX_FRACTION`（提案 **0.34**）× 农场可作业格数，超出 ⇒ journal
  `scope_shed_refused{reason:"cap"}` 且不再认输；
- 意图必须过 `_verify_intents`：田区名必须在**当轮观测**里真实存在，否则 `cancel`
  （与 task-143 同一条纪律）。

---

## 3. 诚实判据与**作弊通道**

### 3.1 诚实判据（含一条**前置依赖**，必须写进任何实现卡）

- journal `scope_shed{zone, tiles, live_crops, water_capacity, deficit, basis, reason, sticky}`；
  journal `scope_released{zone, reason}`；
- `day_end.scope_shed{zone, tiles, dry_in_zone, reason}` + `day_end.scope_shed_tiles: int`（**info**）；
- 认输格**不得**被算成"已浇"：`_water_evidence`（`longrun.py:1687`）算出的
  `final_water`/`watered_outdoor`/`farm.dryCrops` **一律照原值统计**，认输区在范围内就必须让 `dry > 0`；
- 外部可核：`observe?detail=full` 的 `tiles[]` 差分必须能看到"该区 `watered` 仍为 false（或作物仍在）"。
- **⚠️ 前置依赖（Lead 裁定 1 明确要求写进稿子）**：
  **不修 `harvest`（task-169 取证 → 修复卡）的话，本机制只能换来"当天不空转"，换不来"连续 5 天"。**
  因为释放与收敛都依赖"成熟作物被真摘走 ⇒ `live_crops` 真下降"；若 `harvest` 摘不掉，
  认输区会一直有活苗 ⇒ `farm.dryCrops > 0` 永远存在 ⇒ `watered_outdoor` 永远 false。
  本卡与 harvest 修复卡的关系：**本卡 = 诚实有界 + 停止扩种；harvest 修复卡 = 收敛的发动机**。
- **红线（Lead 裁定 1 末句）**：**不许**为了达标去放宽 `watered_outdoor`（`farm.dryCrops == 0`）——
  改判据就是自己骗自己。

### 3.2 作弊通道 ↔ 堵法

| # | 作弊方式 | 堵法 |
|---|---|---|
| C1 | 把认输区当"已浇"，`dry` 归零换 `watered_outdoor=true` | 认输**不参与任何浇水证据**；`final_water.dry`/`farm.dryCrops` 照原口径；单测钉死"有认输区 ⇒ 当天 `verified=false`" |
| C2 | `scope_shed` 变成新的免罚额度（像 `unreachable_exempt`/`refused_exempt`） | **不许**进入 `unmet_leftover`/`no_unmet_stages` 的豁免算式（`longrun.py:5572`）；豁免结构与 `bound_basis` 分母一字不动 |
| C3 | 用认输把 `no_unmet_stages` 洗成 true | 认输格**留在** `_leftover` ⇒ `plot_pending`/`assigned_undone` 照旧；剔除只发生在"去哪儿干活"的目标池与守卫理由 |
| C4 | LLM 滥用 `reduce_scope` 逃避所有活 | 触发条件由**代码**判定（`water_deficit > 0` 且 `basis=="farm"`），`_verify_intents` 复核田区真实存在；一天 1 区 + 全 run 34% 上限；`deficit is None`/≤0 ⇒ `cancel` |
| C5 | 认输悄悄扩大、跨日累积不释放 | 每天日初按 §2.3 第 3 步评估释放（`no_deficit`/`no_live_crops`）；累计上限 + `scope_shed_refused{cap}`；`<journal>-scope.json` 是唯一持久层且 run 边界不继承（§4.1） |
| C6 | 认输后仍以 `no_work` 收尾（假绿灯） | 收尾 code 用 `scope_shed`，**不在** `JUSTIFIED_END_REASONS`(`:317`) ⇒ `day_justified=false`；`no_work` 只在"确实没活"时出现 |
| C7 | 用认输掩盖"本来能浇完" | 只有 `live_crops > water_capacity`（算术上确实浇不完）才允许；算式与 `basis` 一起入账；`basis="conservative"` ⇒ **不认输**（裁定 4） |

---

## 4. 持久层与判据影响评估（给 analyzer/tool 卡用）

### 4.1 `<journal>-scope.json`（Lead 裁定 3）

- 路径推导与 llm/lessons 同款：`_derive_llm_trace_path` `longrun.py:929-938`、
  `_derive_lessons_path` `longrun.py:941-951`（`logs/run9.jsonl` ⇒ `logs/run9-scope.json`）；
  **不新增命令行开关**。
- 写法照抄 lessons 的**原子写**：`tmp = p.with_name(p.name + ".tmp")` → `write_text` → `tmp.replace(p)`
  （`planner.py:984-987`）；写失败只记 `scope_save_failed`，**绝不影响当天判定**。
- 内容（提案 schema，实现卡定稿前请 Lead 确认）：
  ```json
  {"schema": "agentfarm-scope/1", "run": "<journal stem>",
   "zones": {"field_ne": {"since_day": [1,"fall",3], "tiles": 183,
                          "live_crops_at_shed": 142, "reason": "water_deficit=13 > 0"}}}
  ```
- **run 边界不继承**（与新 run 的 journal 不同名 ⇒ 天然隔离）；跨 run 的"学到的东西"仍归 `*-lessons.json`。
- 读到损坏/被外部改写 ⇒ 丢弃整个文件并记 `scope_rejected`（与 `load_lessons_file` 的信任边界同思路，
  `planner.py:904-...`），**绝不让外部文件决定判定**。

### 4.2 事件/字段清单

- **新增 journal 事件名（Lead 要转 log-analyst 立桶卡）**：
  `scope_shed`、`scope_shed_refused`、`scope_released`（外加持久层失败时的 `scope_save_failed`/`scope_rejected`，
  这两个也请一并入桶）。
- **`day_end` 新增子字段**（info，**不进任何 checks**）：`scope_shed`、`scope_shed_tiles`。
- **`Brief` 新增字段**（进提示词）：`live_crops`/`water_capacity`/`water_deficit`（可空）。
- **需要对账的既有闸门**：
  1. `tools/verify-run3.py` 的 3b 自算 `no_unmet_stages`（按 `stages[].assigned_undone`）——认输**不改变**它（§2.3），
     但工具侧要能把"认输格"从 `plot_pending` 里**认出来**（否则复核者会把"主动放弃"误读成"没目标"）；
  2. `deferred_tiles` 口径：认输**不是** `deferred_tiles` ⇒ 两者不许合并计数；
  3. `analyze-longrun` 的机械枚举：新事件名会让
     `TestBagSpaceDeadlock.test_mechanical_enumeration_has_no_unmapped_event` 与
     `TestEventMappingDrift.test_event_buckets_cover_every_brain_journal_name` 变红，**这是预期的**，
     要提前立桶卡（同 task-160/164 的处理方式），**绝不允许改名躲检测**。
- **不新增 `checks` 键**（红线）。

---

## 5. 用例与变异骨架（伪代码，实现卡照此展开）

> 约定：`w = FakeWorld(...)`；`run = make_run(w, ...)`；`run.worker = FakeWorker(w)`；
> `run.client = FakeClient(w)`（`make_run` 不自动装 worker，这是 task-161 的教训）。
> 造"活苗远超体力"的世界：`w.dirt` 放 N 格、`w.crops[t] = {"watered": False, "ripe": False}`、
> `w.farm = {"loaded": True, "complete": True, "crops": N, "dryCrops": N, "hoeDirt": N, "emptyDirt": 0}`。

### 5.1 单测（8 条）

```
test_water_budget_facts_reach_the_prompt
    # 142 格活苗、maxStamina 270 ⇒ water_capacity==129、water_deficit==13
    assert "water_budget:" 出现在 base_lines() 里
    assert brief.water_deficit == 13 and "13" in brief.situation_text()

test_missing_farm_counts_render_unobserved_and_block_shedding      # 钉死 fail-closed
    w.farm = {}                       # 或 {"complete": False}
    b = run._plot_brief(w.obs(), plot)
    assert b.live_crops is None and b.water_capacity is None and b.water_deficit is None
    assert "未观测到" in b.situation_text()
    assert deterministic_plan(b) 里没有 reduce_scope
    assert 没有 scope_shed 事件

test_deficit_zero_means_no_shedding
    w.farm["crops"] = 50; w.farm["dryCrops"] = 50     # 50 <= water_capacity
    assert brief.water_deficit == 0
    assert deterministic_plan(brief) 里没有 reduce_scope
    assert run.shed_zones == set()

test_shed_zone_leaves_water_targets_and_guard_reasons
    run._shed_scope(obs, rep, "field_ne")
    assert 该区所有格 not in run._stage_tiles("water_area", obs, plot)
    assert 该区所有格 not in run._pending_work()
    assert "有 N 格作物没浇水" 的 N 不含认输格
    assert run._plot_has_work(obs, 该区格) is False

test_shed_day_is_never_verified                                  # 钉死"认输不许变绿"
    run.run()  # 一天
    d = run.days[-1]
    assert d.ended_reason.startswith("scope_shed")
    assert d.checks["watered_outdoor"] is False and d.checks["no_unmet_stages"] is False
    assert d.verified is False and d.checks["day_justified"] is False
    assert d.scope_shed["tiles"] > 0

test_shed_is_not_an_exemption_budget                             # 防 C2/C3
    两个世界：一个认输、一个不认输（其余相同）
    assert 两者 unreachable_exempt / refused_exempt / unmet_leftover 逐字相同
    assert 认输世界的 plot_pending / assigned_undone 仍 > 0

test_harvest_runs_before_shedding
    认输区放 2 格 ripe=True 的作物
    run._shed_scope(...) 之后 assert 这两格已被收走（harvest 先跑）
    assert journal 顺序：harvest 相关事件出现在 scope_shed 之前

test_release_when_deficit_disappears                             # 裁定 1/3 的释放
    run.shed_zones = {"field_ne"}（模拟从 <journal>-scope.json 读入）
    w.farm["crops"] = 10; w.farm["dryCrops"] = 0     # deficit == 0
    run._release_scope_if_converged(obs, rep)
    assert run.shed_zones == set() 且 journal scope_released{reason:"no_deficit"}
    assert 该区重新出现在 _stage_tiles("water_area") 里
```

### 5.2 变异设计（4 个，`scratch/_t168_mutate.py`；brain+tests 一起拷临时目录——task-124 的教训）

```
m168a  # 把认输格当"已浇"：_water_evidence/final_water 里把认输格的 dry 扣掉
       # 预期杀：test_shed_day_is_never_verified
m168b  # 让 _leftover/unmet_leftover 排除认输格（= 洗白通道 C3）
       # 预期杀：test_shed_is_not_an_exemption_budget
m168c  # water_deficit is None 时也允许认输（去 fail-closed）
       # 预期杀：test_missing_farm_counts_render_unobserved_and_block_shedding
m168d  # _pending_work 不剔除认输格（= 走回去复发）
       # 预期杀：test_shed_zone_leaves_water_targets_and_guard_reasons
```

变异脚本要求（沿用既有纪律）：基线全绿；每个变异必须**落在最终赋值之后**（task-157 的教训：
补丁位置不对会"0 红"）；杀掉条数按**去重后的测试名**统计；"补丁已落却 0 红"⇒ 先怀疑补丁位置。

---

## 6. 裁定记录（Lead m14861，五问全部关闭）

| # | 我的提案 | Lead 裁定 | 稿中落点 |
|---|---|---|---|
| 1 | 三条路线 A/B/C（B = 允许拔除未熟作物） | **否掉 B，走 C**：只收成熟 + 认输 + 停止扩种；认输**粘但可释放**，释放条件 = `live_crops <= water_capacity` 或该区无活苗；**必须写明"不修 harvest 只能换来当天不空转"**，并把依赖标成"前置：task-169（harvest 取证）→ 修复卡"；**不许**放宽 `watered_outdoor` | §2.3、§3.1 |
| 2 | 粒度 = 田区 | **同意** | §2.1 |
| 3 | 同一 run 内跨日粘；持久层待定 | **同意粘 + 可释放**；落点 = **新文件 `<journal>-scope.json`**（从 `--journal` 派生、tmp+replace 原子写、run 边界不继承），**不混进 lessons**；释放记 `scope_released{zone,reason}`；三个新事件名报 Lead | §2.3、§4.1 |
| 4 | `basis="conservative"` ⇒ 不认输 | **同意** | §2.5、§3.2 C7 |
| 5 | 只作 info、不进 `checks` | **同意**；但**认输格留在会计里**、收尾 code `scope_shed` 不在 `JUSTIFIED_END_REASONS` | §2.3、§3.2 C1/C2/C3/C6 |

**仍然开放（不属于本卡，属实现/验收链）**：
- `harvest` 真能摘的取证与修复（Lead 已点名 task-169 为前置）——它决定"连续 5 天"是否可达；
- `<journal>-scope.json` 的 schema 终稿（§4.1 提案）与是否需要 Lead 侧工具读取它（本轮只作 info）。
