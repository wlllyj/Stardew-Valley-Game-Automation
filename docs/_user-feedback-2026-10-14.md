# 用户反馈登记 · 2026-10-14（三条问题 → 立卡与修法）

> 来源：`User said (m11003)`：
> 1. 大模型的规划没有反馈，需要让大模型有反馈，之后能自我进化
> 2. 田种的乱七八糟，东一个西一个
> 3. 植物过了时间死了变成枯草，还是继续浇水，处理的有问题
>
> `User said (m11005)`：「你把问题记录下来，安排后续修复吧」⇒ 本文件 = 登记 + 机制定位 + 立卡 + 验收口径。

---

## 1) LLM 规划没有反馈 / 要能"自我进化" → **task-82**（承接 task-58/59）

**现状（有据可查）**
- **有留痕**：task-56 已实现每次真实 LLM 调用写 `<journal>-llm.jsonl`（`prompt/raw/usage/finish_reason/duration_ms/attempts/rejected/accepted/fallback`），journal `decision` 行带 `llm_trace`/`llm_trace_hash`；`tools/verify-run3.py` 已有"留痕完整性"闸门。
- **有当次校验**：`_verify_intents`（keep/unknown/cancel）在**同一次**决策内把不可见的意图判为 `unknown`、把无目标意图 `cancel`，并换任务（`policy_fallback`）。
- **没有反馈回灌**：模型看不到"我上次说的意图后来真成了没有"（`outcome`/`terminal`/`leftover`/失败格），也没有跨日记忆。task-58（决策史喂回提示词）与 task-59（夜间复盘 notes）已立卡但未实现。

**修法（task-82）**：决策 → 结果 join；`<journal>-lessons.json` 跨日教训库（代码写客观事实 + LLM 写一句 hint，上限 ~20 条、次日注入 ≤3 条）；超限裁切时决策史/教训最先被裁。
**诚实边界**：这叫"会话内记忆 + 提示词反馈"，**不是**权重更新/在线训练 —— 文档与验收话术都必须这么写。
**验收**：连续两次 run 的对照证据（run A 某意图被 cancel/失败 ⇒ run B 的 prompt 里出现对应教训且不再同形态重犯）。

## 2) 田种得东一个西一个 → **task-83**

**机制**
- 播种目标 = 当前**作业区（plot）**内的 `plantable` 格；作业区由 `plot_in_zone`/`_work_spot_plot`/`_resume_plot` 按打分与**距玩家最近**挑（`fields.py`）⇒ 今天 `field_ne`、明天 `field_se`。
- 种子少（run 里常只有 1–5 个）⇒ 每天只种 2–6 格，且跨区分散。
- `plant()` 顺序不是行优先，也不要求与已有同类作物相邻 ⇒ 同区内也会跳格。
- 用户更早的要求（m00601）就是"落点不因角色漂移"，本卡把它做实。

**修法**：固定**当家田块**（bed，锚点确定性、不看玩家位置，一个生长周期内不换）；`next_plant_tiles()` 行优先**连续填空**、优先补同类作物相邻格；同一天不跨 zone；journal 写 `plant_layout{zone,bed,tiles,contiguous,gap_count}`，`contiguous=false` 即缺陷。
**验收**：真机两次跨日后，同一 crop 的坐标必须同 zone 且 4-邻接连通（证据 = `observe` 的 `tiles[]` + `plant_layout`）。

## 3) 枯死作物还在浇水 → **task-84**

**机制（用户看到的现象完全对得上）**
- Mod：作物格 `Tool = watered ? "none" : "can"`，**不看 `crop.dead`** ⇒ 死苗格在观测里与"需要浇水"无异。
- 脑：`_stage_tiles("water_area")` 只看 `tool=="can"`，`water()` 照浇 ⇒ 给死苗浇水、白烧体力与水。
- 口径：`farm.dryCrops`/`dryTiles` 当初**刻意**把死苗也算"干"（task-50），于是 `tools/verify-run3.py` 的"`no_work` ⇒ `final_water.dry==0`"闸门在死苗清完前**永远不可能满足**，把"该清死苗"混进了"该浇水"。
- 顺序：政策顺序 `water_area → harvest → clear_dead` ⇒ 死苗**先被浇、后被杀**。

**修法**：Mod 把 dry 拆成"活苗 dry"vs 死苗（`dryCrops` 收窄为活苗 + `dryDeadCrops`；死苗格 `Tool` 不再返回 `"can"`）；脑侧 `water` 排除死苗（`skipped`，理由"枯死作物不浇水"）；`clear_dead` 提到 water 之前；`day_end` 增 `dead_crops`/`dry_dead`；工具侧（Lead 改 `verify-run3.py`）同向对齐。
**验收**：0.7.27 装机后喂"含死苗"场景 ⇒ 账本里**不得**出现对死苗格的浇水动作，`deadCrops` 下降。

---

## 排期建议（Lead）
| 卡 | 内容 | 依赖 | 归属 |
|---|---|---|---|
| task-58 / task-59 | 提示词带决策史 / 夜间复盘 notes（已存在，run6 后解阻） | task-57 ✅ | dev-coder |
| **task-82** | 决策→结果 join + 跨日教训库 + 注入（本批新增） | 58/59 | dev-coder |
| **task-83** | 当家田块 + 连片播种（本批新增） | — | planner-dev |
| **task-84** | 死苗不浇水 + dry 拆分 + clear_dead 提前（本批新增） | — | dev-coder |

> 三张卡都要动 `brain/agentfarm/longrun.py`（task-82/83/84）与 `farmwork.py`（83/84）⇒ **必须串行**，由 Lead 逐张放行，避免同文件并发写。

## 证据来源（供各卡取证）
- run7 账本：`logs/longrun-3day-llm-run7.jsonl`（+ `-llm.jsonl`）—— 用户第 2/3 条可在这里找现场（`plantable` 坐标分布、死苗格是否被 `water`）。
- 既有取证文档：`docs/_analyze-farmcounts.md`（farm 聚合口径）、`docs/_tool-matrix.md`、`docs/_run6-criteria.md`（判据）。
