# 播种/开垦"散乱"基线量化 + task-83 的可验收指标与账本字段清单（task-94）

- 只读取证；证据源：`logs\longrun-3day-llm-run7.jsonl`（1230 行，7 天：spring 26→28 + summer 3→9）、
  `logs\longrun-3day-llm-run5.jsonl`（531 行，6 天）、`logs\longrun-3day-llm-run6.jsonl`（143 行，同日两会话）。
- 复现脚本：`scratch/_t94_shapes.py`（事件形状普查）→ `scratch/_t94_shapes_u8.txt`；
  `scratch/_t94_baseline.py`（基线量化）→ `scratch/_t94_baseline.txt`。
- 动机：用户 `User said (m11003)` 第 2 条「田种的乱七八糟，东一个西一个」⇒ Lead 立 task-83（当家田块 + 连片播种）。

---

## §1 基线数字

### 1.1 先回答"账本里能不能拿到逐格落点"：**拿不到**

| 需要的坐标 | 账本现状 | 证据 |
| --- | --- | --- |
| 一次 `plant_area`/`till_area` 的**成功格列表** | **没有**。`day_end.stages[].tiles` 是**整数**（该阶段目标格数），`plot.tiles` 也是整数 | `scratch/_t94_shapes_u8.txt:110`（`"stage": "plant_area", "tiles": 2, "ok": 1`）、`:80`（`plot … "tiles": 25`） |
| 失败/被拒/不可达/被围住格的坐标 | **有**（逐格） | `stage_exhausted.tiles`（`:81`）、`unreachable.tile`（`:89`）、`tool_refused.tile`（`:87`）、`unreachable_stage.coords`（`:91`）、`day_end.stages[].unreachable_tiles/refused_tiles/encircled_tiles` |
| 播种"落点"的观测锚点 | 只有 `plot.anchor`（**观测锚点**，玩家站位/区域打分用，与落点无固定关系）+ `plot.zone` | `:79`（`plot … anchor:[69,35] zone:field_se tiles:25`） |
| 阶段→zone 归属 | **`day_end.stages[]` 没有 `zone` 字段**；只有 `stage_exhausted.zone` / `unreachable_stage.zone` / `plot.zone` 能间接看 | `:110`（stage 字典键里没有 zone） |
| 背包种子 | `final.seeds` 是**真实清单**（`seed_items()` 返回 `(itemId,name,count)`），`seeds=[]` = **背包确实没种子** | `brain/agentfarm/longrun.py:957`、`brain/agentfarm/farmwork.py:631` |

> ⇒ **结论：run5/6/7 的"播种落点散乱度"在账本层量化不了**（不是我不想算，是逐格成功坐标从来没有被写下来）。
> 本卡能给的只有：**阶段级格数/zone 序列/意图序列** 的近似基线（§1.2–§1.3），
> 以及对**唯一有坐标的那类格（失败/不可达）**演示连通性指标怎么算（§1.4）——它同时是 task-83 落地后的计算脚手架。
> **绝对不编逐格坐标。**

### 1.2 播种/开垦基线表（阶段级，来源：`outcome` + `day_end.stages[]`）

| 指标 | run7（7 天） | run5（6 天） | run6（同日 2 会话） |
| --- | --- | --- | --- |
| `plant_area` 阶段记录数 | 4（day1×3、day3×1） | 2（day1×1、day4×1） | 0 |
| 播种**成功**格数（Σ `plant_area.ok`） | **4** | **6** | **0** |
| 播种尝试格数（Σ `tiles`） | 12 | 8 | 0 |
| `plant_area` 因 `no_seed` 提前停 | 3 次（day1 L105、day1 L…、L105/L130 两处 `stopped:"no_seed"`） | 1 次（day1 L44 后 `stopped:"no_seed"`） | — |
| `till_area` 成功格数（Σ `ok`） | **38** | 30 | 0 |
| 播种落在几个 zone | **3**（field_se、field_nw、field_ne） | 2（field_nw、field_se） | 0 |
| 单日播种最多涉及 zone 数 | 2（day1：field_se + field_nw） | 1 | 0 |
| 连续两天在同一 zone 播种 | **否**（day1 SE/NW → day3 NE） | 否（day1 NW → day4 SE） | — |

关键读数（run7）：
- day1：`L22 clear_dead field_se 12/12` → `L26 plant_area field_se 2/1` → `L34 till_area field_se 8/4（跳过 3、被拒 3、不可达 1）` → `L50 till 12/12` → `L61 till 10/10（reason 里没有"作业区"，zone 未知）` → `L100 plant_area **field_nw** 1/1` → `L101 till 12/12` → `L105 plant_area field_nw 2/1（stopped no_seed）` → `L108-110 till field_nw 0/0（no_target）`。
- day3：`L292 plant_area **field_ne** 2/1` → `L295-297 till field_ne 0/0（no_target）`。
- ⇒ **7 天里 4 格苗撒在 3 个不同田区**（平均每区 1.3 格），且**没有一天在同一片连续落 3 格以上**——这就是"东一个西一个"的可量化形态。
- `final.farm.crops`：run7 = 5,5,6,6,6,6,6（全农场作物数）；`final.tillable` 恒 200 ⇒ **不是没地，是没种子 + 没连片计划**（`final.seeds=[]` 全程）。

### 1.3 zone 切换与锚点距离（`outcome` 时间序 + `plot.anchor`）

| 天 | run7 的 zone 连续段（plant+till） | 切换次数 | 相邻 `plot` 锚点距离（格） | 锚点最近邻 mean/median/max |
| --- | --- | --- | --- | --- |
| summer 3 | `[field_se] → [field_nw]` | 1 | 31.62, 18.25, 6.4, 9.22, 7.28, 10.0 | 5.81 / 4.0 / 15.3 |
| summer 4 | `[field_nw]`（全是 0/0 no_target） | 0 | 3.61, 7.28, 7.62, 7.0, 7.28 | 2.27 / 3.0 / 3.61 |
| summer 5 | `[field_ne]` | 0 | 5.0, 9.43, 0.0, 14.21, 3.16, 3.16, 11.31, 10.05, 7.81 | 4.50 / 5.0 / 10.05 |
| summer 6 | `[field_nw]` | 0 | 5.0, 6.08, 8.06, 8.49, 10.3, 8.54, 4.12 | 6.18 / 6.08 / 8.54 |
| summer 7 | 无（无 plant/till） | 0 | 10.2, 9.9, 7.0, 19.24, 3.61, 9.22, 4.12, 3.16, 10.77 | 5.96 / 7.0 / 10.77 |
| summer 8 | `[field_ne]` | 0 | — | — |
| summer 9 | 无 | 0 | — | — |

> 锚点距离是**弱代理**（观测锚点跟着玩家走，不是落点）：它只能说明"这一天在场上到处转"，不能证明"苗撒开了"。
> run5 对照：day1 锚点 16.28/7.07/4.0/11.05/3.0/10.3/3.0/5.83/3.61（mean 4.96，median 3.61）。

### 1.4 连通性指标演示（用唯一有坐标的一类格：失败/不可达）

口径：格点四邻（曼哈顿 1）连通块；"最大连通块占比" = 最大块 / 去重格数。

| 账本 | 失败/不可达去重格数 | 连通块大小 | 最大占比 | 最近邻 mean/median/max |
| --- | --- | --- | --- | --- |
| run5 day2（spring 27… 实为 summer 2 会话） | 18 | `[4,4,2,2,1,1,1,1,1,1]` | **0.22** | 2.29 / 1.0 / 13.04 |
| run6 每个会话 | 42 | `[19,13,6,1,1,1,1]` | **0.45** | 1.18 / 1.0 / 5.83 |
| run7 summer 3 | 4 | `[4]` | 1.00 | 1.0 / 1.0 / 1.0 |
| run7 summer 5 | 8 | `[4,2,1,1]` | 0.50 | 1.49 / 1.0 / 4.47 |

> 这四行证明：**同一套算法对"成片"和"散开"的坐标都能算**（run7 day1 的 4 格正好互相邻接 ⇒ 1.00；
> run5 day2 的 18 格碎成 10 块 ⇒ 0.22）。task-83 只要把**成功格**坐标写下来，就能直接照抄这个算法出指标。

---

## §2 给 task-83 的可量化验收指标（5 条）

每条：**名字 / 公式 / 阈值（严格｜保守） / 从账本哪条事件算 / 反例形态**。
阈值依据 = run7 基线（§1.2：7 天 4 格撒 3 区，单日最多 2 区）+ §1.4 连通性校准；**没有真机 A/B，故一律给两档**。

### M1 单日单区率（zone purity）
- 公式：`|{zone(落点) : 同一天成功播种格}| ≤ 1`；或数字版 `max_zone_share = max_zone_planted / planted_total`。
- 阈值：**严格 `≤1` 且 share ≥ 0.9｜保守 `≤2` 且 share ≥ 0.7**。
- 数据源：需要逐格或逐阶段带 zone 的**成功**留痕（现状：`plant_layout.zone`+`tiles`，见 §3 A/B）。
- 反例：run7 day1 —— 同一交易日播种落在 `field_se`（L26）与 `field_nw`（L100/L105）两个区 ⇒ 违反严格档；基线 `max_zone_share` 在该日 ≈ 0.33。

### M2 当家田块占比（home-plot share）
- 公式：`planted_in_home / planted_total`，`home = home_plot.bed`（或 `home_plot.zone` 的 bed 集合）。
- 阈值：**严格 ≥ 0.9｜保守 ≥ 0.8**；且要求 `home_plot_moved` 当天 ≤ 1 次（不然"当家"二字没意义）。
- 数据源：`plant_layout{zone,bed,tiles}` + `home_plot`/`home_plot_moved`。
- 反例：run7 day3 唯一 1 格播在 `field_ne`，而当家田区（若定为播种最多区）是 `field_se/field_nw` ⇒ 该日 share = 0。

### M3 最大连通块占比（largest connected component share）
- 公式：`max_cc(day 的播种格) / planted_total`，四邻连通（算法见 `scratch/_t94_baseline.py` 的 `comps()`）。
- 阈值：**严格 ≥ 0.8｜保守 ≥ 0.7**（保守档参考：run6 的 42 个"自然成片"失败格最大块 0.45，说明真实农场地形会把块打碎，≥0.8 是"有意排布"才做得到）。
- 数据源：**必须有逐格坐标**（`plant_layout.tiles` 为坐标列表）。
- 反例：run5 day2 的 18 个被拒/不可达格 = 10 块、最大占比 0.22（若播种也这样就是"撒"）。

### M4 行优先连片率与空洞数（contiguity / gap_count）
- 公式：对当家 bed 的包围盒 `bbox`：`planted_bbox = planted ∩ bbox`；`gap_count = |{t ∈ bbox : 可锄且未种}|`；
  `rowmajor_ok = (planted_bbox 按 y 再 x 排序后，前 k 个恰好是 k×w 的矩形)`。
- 阈值：**严格 `gap_count == 0`｜保守 `gap_count ≤ 1` 且 `rowmajor_ok`**。
- 数据源：`plant_layout.gap_count`（**被检查值**）+ 逐格坐标（**独立复核**，两者都要）。
- 反例：run7 day1 `till_area field_se 8 格只做成 4 格`（另有 3 被拒 `[72,35][72,36][73,36]`、1 不可达 `[73,35]`），这 4 个成功格周围必然留洞 ⇒ 若照原计划播种就会 `gap_count ≥ 3`。

### M5 同日多播的间距（intra-day spacing）
- 公式：同一天所有 `plant_layout` 的落点质心两两最大距离 `span`；或"同日两次 plant 的首个落点距离"。
- 阈值：**严格 `span ≤ 3`｜保守 `span ≤ 6`**（依据：相邻格距离 1；run7 day1 两次 plant 分区不同 ⇒ 距离 > 20，§1.3 锚点 31.62 是同一现象的外显）。
- 数据源：`plant_layout{t}` + `tiles` 质心。
- 反例：run7 day1 `L26 field_se` 与 `L100 field_nw` 两次播种（跨区）。

### （可选）M6 跨天续种率（same-bed reuse）
- 公式：`|bed(day_n) ∩ bed(day_{n+1})| ≥ 1` 的天数占比。
- 阈值：**严格 ≥ 0.8｜保守 ≥ 0.6**。数据源：`plant_layout.bed`。
- 反例：run7 day1（SE/NW）→ day3（NE）之间**零重叠**。

---

## §3 账本字段充分性 + 给 task-83 的字段清单

### 3.1 计划中的字段够不够？

| 计划字段 | 够算 M1 | M2 | M3 | M4 | M5 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| `plant_layout.zone` | ✅ | ✅ | ✖ | ✖ | ✖ | zone 可算纯度 |
| `plant_layout.bed` | ✅ | ✅ | ✖ | ✖ | ✖ | **必须可稳定标识 + 带 bbox**，否则只能按 zone 退化成 M1 |
| `plant_layout.tiles` | ⚠ | ⚠ | ✅ | ✅ | ✅ | **必须是坐标列表 `[[x,y]…]`**；若是整数（像现在的 `stage.tiles`）⇒ M3/M4/M5 全部算不了 |
| `plant_layout.contiguous` / `gap_count` | ✖ | ✖ | ✖ | ⚠ | ✖ | 是**派生量**：只能当"被检查值"，无法独立复核 ⇒ 必须同时给 `tiles` |
| `home_plot` / `home_plot_moved` | ✖ | ✅ | ✖ | ✖ | ✖ | 需要 `from/to` 的 bed id 与 reason |

**结论：不够。** 至少缺三样：①`tiles` 是坐标列表（而不是计数）②逐格**成功**留痕事件 ③`home_plot` 的稳定 bed id/bbox。

### 3.2 给 task-83 的字段清单（字段名 + 语义 + 类型）

**A. 逐格成功留痕（最关键；当前只有失败逐格留痕）**
- `sow_step`（每次播种一格都写一条）：`{t: float, day: [year,season,dom], zone: str, bed: str, tile: [x,y], action: "sow", ok: bool, reason: str, source_intent: str}`
- `till_step`（同构）：`{t, day, zone, bed, tile:[x,y], action:"till", ok, reason, source_intent}`
- 若嫌事件多，可统一成 `tile_action{t, day, zone, bed, action:"sow"|"till", tile, ok, reason, source_intent}` —— **但日/zone/bed 必须逐条带**（`day_end.stages[]` 缺 zone，事后拼不回来）。

**B. `plant_layout`（日级/每次 plant 收工时一条）**
```
plant_layout = {
  t: float, day: [year, season, dom],
  zone: str,                        # field_nw/ne/sw/se
  bed: str,                         # 稳定 id，如 "bed:field_nw:8-12x18-21"
  bbox: [x0, y0, x1, y1],           # 闭区间
  tiles: [[x,y], ...],              # ★ 成功落点坐标列表（不许只给计数）
  planted: int,                     # = len(tiles)
  contiguous_largest: int,          # 最大四邻连通块大小（派生，供核对）
  gap_count: int,                   # bbox 内"可锄且未种"的格数
  nn_mean: float,                   # 落点平均最近邻距离（可选）
  source_intent: str,               # 哪个意图触发
  home: bool,                       # 是否落在当家田块
}
```

**C. 日级验收字段（让验收不用自己算）**
- `checks.plant_layout_ok: bool`（当天全部 plant 都满足 M1–M5 的**保守档**）
- `checks.plant_gap_count: int`、`checks.plant_zones: int`（当天播种涉及 zone 数）
- `day_end.planted_tiles: [[x,y]…]`（当天全部成功播种格，跨区合并；便于一次算 M3/M5）

**D. 当家田块**
- `home_plot{zone, bed, bbox:[x0,y0,x1,y1], since_day, reason}`
- `home_plot_moved{from:{zone,bed}, to:{zone,bed}, reason, t, day}`

**E. 结构性补丁（不改也能验收，但会让复核变"猜"）**
- `day_end.stages[].zone: str` —— 现在缺，导致阶段级 zone 归属只能靠 `stage_exhausted.zone`/`plot.zone` 间接看（run7 `L61 till 10/10` 的 `zone` 就是空的）。
- `plot.tillable_tiles: [[x,y]…]`（或至少 `bounds`）—— 现在 `tiles` 是整数、`anchor` 是观测锚点 ⇒ 无法把落点映射回 zone 做独立复核。

**F. 不许做的**：不要只写 `contiguous`/`gap_count` 这种派生布尔/计数而不写 `tiles` —— 那样验收只能信自述（违反"回执只是声明、验收看观测"的项目纪律）。

---

## §4 run7 播种现场表（每次 plant / till，来源：`outcome` 时间序）

| 日 | 行 | 事件 | zone | `tiles/ok/跳过/失败` | 备注（`stopped`） |
| --- | --- | --- | --- | --- | --- |
| summer 3 | L22 | outcome clear_dead | field_se | 12/12/0/0 | 播种前清死苗 |
| summer 3 | **L26** | **outcome plant_area** | field_se | **2/1/0/0** | 第 1 处落点（区 A） |
| summer 3 | L34 | outcome till_area | field_se | 8/4/3/0 | 被拒 3（`[72,35][72,36][73,36]`）、不可达 1（`[73,35]`） |
| summer 3 | L50 | outcome till_area | field_se | 12/12/0/0 | |
| summer 3 | L61 | outcome till_area | **?（无作业区）** | 10/10/0/0 | reason 缺 zone ⇒ 复核断点 |
| summer 3 | **L100** | **outcome plant_area** | field_nw | **1/1/0/0** | 第 2 处落点（区 B，跨区） |
| summer 3 | L101 | outcome till_area | field_nw | 12/12/0/0 | |
| summer 3 | **L105** | **outcome plant_area** | field_nw | **2/1/0/0** | `stopped: no_seed` |
| summer 3 | L110 | outcome till_area | field_nw | 0/0/0/0 | `no_target` |
| summer 4 | L185 | outcome till_area | field_nw | 0/0/0/0 | `no_target` |
| summer 5 | **L292** | **outcome plant_area** | field_ne | **2/1/0/0** | 第 3 处落点（区 C） |
| summer 5 | L297 | outcome till_area | field_ne | 0/0/0/0 | `no_target` |
| summer 6 | L448 | outcome till_area | field_nw | 0/0/0/0 | `no_target` |
| summer 8 | L1214 | outcome till_area | field_ne | 0/0/0/0 | `no_target` |

> run7 全程：`plant_area` 4 次（成功 4 格 / 尝试 12 格）、`till_area` 8 次（成功 38 格）；
> `final.seeds=[]`（背包无种子）⇒ 4 次里 3 次以 `no_seed` 收尾。
> run5 对照：`L18/L19` day1 field_nw 1/1 + 1/1，`L27/L31/L43` till 12/12、9/9、12/8/4，`L44` plant 5/4（`no_seed`），day4 `L236` plant field_se 2/1。

---

## §5 未定项

- **U1（最重要）**：run5/6/7 **没有任何一次播种的逐格成功坐标** ⇒ §1.2 的"撒了 3 个区"是**阶段/意图级**结论，不是逐格结论；真实"散乱度"（M3/M4/M5）在这三本账本上**无法计算**。task-83 落地后必须补一本 run8 才能给真基线。
- **U2**：`plot.anchor` 与落点的关系未定（疑似"观测锚点/打分中心"），因此 §1.3 的距离只能当"场上移动"的代理，不能当落点散度。
- **U3**：`final.farm.crops`（5→6）与当日 `plant_area.ok`（3）对不上账（day1 播 3 格但农场作物只 +0/+1）——`counts_scope` 的窗口口径未定；不影响本卡结论（我们只用 zone/格数），但 task-83 的验收若要用作物数差分，必须先澄清这个口径。
- **U4**：`day_end.stages[].zone` 缺失导致 run7 `L61` 那次 10 格开垦无法归属田区（§4 表里标 `?`）。
- **U5**：阈值全部基于"run7 基线 + 失败格连通性校准 + 常识"，**没有真机 A/B**（run7 从没执行过连片策略）；两档阈值是先验，等 run8 有数据后应收紧。

---

## §6 复核命令

```powershell
# 形状普查（哪些事件带坐标、`tiles` 是整数还是列表）
python scratch\_t94_shapes.py            # 输出 UTF-16LE，需 tools\_tmp_conv.py 转 UTF-8
# 基线量化（zone 序列 / 锚点距离 / 失败格连通性）
python scratch\_t94_baseline.py scratch\_t94_baseline.txt
# 原始证据点
python -c "import json;[print(i,json.loads(l)['event']) for i,l in enumerate(open(r'logs\longrun-3day-llm-run7.jsonl',encoding='utf-8'),1)]"
```

一句话总评：**"散"在账本上只能证明到"7 天 4 格撒进 3 个田区、单日最多跨 2 区、跨天零续种"这个层级（§1.2）；
真正的连片度（M3–M5）在 run5/6/7 上无法计算，因为成功落点坐标从来没被写下来——这是 task-83 的第一优先级字段（§3.2 A/B），
不补它，验收就只能靠自述。**
