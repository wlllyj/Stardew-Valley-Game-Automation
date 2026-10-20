# 卡片草稿 A4 — 跨天 `refused_tiles` 记忆（unknown 格每天白撞的浪费）

> 状态：草案（未落库）。仅分析 + 提案，不改代码、不改开发日志。
> 作者：analyst-b3（log-analyst）。关联缺口：Z3（unknown 格三不沾）。

## 0. 现象：同一批 unknown 格每天被重撞

春季存档 `logs/runA9-0749-spring.jsonl` 里，**8 个 `kind=unknown` 的 `tool_ineffective` 格**
每天都被重试、白白烧掉当日预算：

```
(73,25)(74,25)(73,26)(74,26)(67,30)(68,30)(67,31)(68,31)
```

聚合侧佐证（`docs/_probe-save-state-2026-10-20.md` §0 问3，`line 28`）：
- `logs/runA9-0749-spring-gaps.json`：`kind=unknown, reason=gated, count=12`，
  `first_seen "2 spring 2"` / `last_seen "2 spring 5"` —— 跨度 4 天，同一批格反复出现。
- 该 gaps 文件中 12 条 `tool_refused`（`tool_ineffective`，`kind=未知`）落点即上述坐标簇
  （(73,25)(74,25)(73,26)(74,26)(67,30)(68,30) 为主，含相邻 (67,31)(68,31)）。

行为后果：**每天对这几格各挥 6 次锄（Hoe 无效）→ `till_area` 被拒 → 不进农场动作，却吃了
走路预算 + 工具动作预算**。这正与 A9-0749 复盘里"走路预算燃烧（resume_walk）"的"走了不干活"
同源——守卫说 zone 已清空，执行层到格却被游戏拒。

## 1. 根因：与 Z3 是同一个 bug

`docs/_observe-goal12-2026-10-19.md` Z3（`line 90-95`）已定位：

- `kind="unknown"` 地形特征格**不在任何桶里**：`'unknown' in OBSTACLE_KINDS=False`
  （`planner.py:1398`）、`in ZONE_BLOCKER_KINDS=False`（`fields.py:83`）、
  `in CLUMP_KINDS=False`（`farmwork.py:163`）、`in SKIP_KINDS=False`（`farmwork.py:124`）
  ⇒ **计数、简报、清除三不沾**。
- 于是 zone 清空判据对它**假 PASS**（`zone_blockers_total=0` 报"已清空"），
  但 `till_area` 到这些格时游戏仍拒（Hoe 报 `tool_ineffective`）。
- 脑侧 `_tile_reason` 对"全 skipped 且 kind 不在 `DEFERRED_KINDS`"的格记 `gated`
  （`longrun.py:8154-8159`）—— 既没进 `ZONE_BLOCKER_KINDS` 也没进 `DEFERRED_KINDS`，
  于是既不"清得了"也不"明确递延"，每天原地重撞。

简言之：**zone 判据看不见 unknown 格（假 PASS），而 Hoe 能看见（真拒）**——判据与执行层错位，
且**没有跨天记忆**，所以每天都从零开始重撞。这正是 Z3 的运行时表现。

## 2. 提案：跨天 `refused_tiles` 记忆

核心：把"试过且被拒"的格**跨天记住**，次日及以后**抑制重撞**，改走诊断，而不是每天烧预算。

### 2.1 数据结构（建议）
- 在 DayReport / 运行态里加 `refused_tiles: dict[tuple, dict]`，键为 `(x,y)`（或含 `zone` 维度），
  值记录 `{kind, reason, first_seen_day, last_seen_day, attempts, last_code}`。
- 落点来源：已有 `_tile_reason` 返回的 `gated` / `tool_level` / `unknown_evidence` 等
  （`longrun.py:8140-8159`），凡 `code in ("tool_ineffective","gated","blocked_tile",...)` 且
  确认是"地形不可清"的，写入 `refused_tiles`。
- **跨天持久化**：写入 save-state（与 `shop_offers` 同口径，跨天保留，见 `_preconditions_apply`
  的 `self.shop_offers` 注释 `7460`），而非仅当天内存。

### 2.2 抑制 + 路由
- 决策/路径规划时查询 `refused_tiles`：若目标格已在其中且 `attempts >= 阈值`（如 ≥2 天仍拒），
  **不再派 `till_area`/`clear` 到该格**，从当日可工作计划中剔除 → 省下走路预算 + 工具动作预算。
- 被抑制的格**路由到诊断**而非静默丢弃：
  - 触发 `machine-runner` 风格的探针（复用 Z3 建议卡：`T-6` 读 `Feature`/`clumpIndex`/`toolOk`，
    见 `docs/_observe-goal12-2026-10-19.md:93`）；
  - 简报如实公告"X 格 unknown 地形，连续 N 天被拒，待定桶/人工判定"，而不是每天假 PASS。

### 2.3 与 Z3 修复的分工
- Z3（dev-coder 定桶）：从**根上**给 `unknown` 一个明确桶（可清→`ZONE_BLOCKER_KINDS`+clearable；
  不可清→`DEFERRED_KINDS`），让 zone 判据不再假 PASS。
- A4（本卡 `refused_tiles`）：在根因修复**落地前/落地后**都生效的**兜底护栏**——
  即使某类地形一时定不了桶，也绝不每天重撞，而是抑制 + 诊断。两者互补，不互斥。

### 2.4 验收判据（草案）
- 单测：构造连续 2 天的 ledger，day1 对 (73,25) 记 `tool_ineffective`，断言 day2 决策中
  (73,25) **不再出现在 `till_area` 计划**，且 `refused_tiles[(73,25)].attempts>=2`、
  简报含"unknown 连续 N 天被拒"诊断条目。
- 行为账本对照：A9-0749 春季跑修复后，`gaps` 文件 `unknown gated×12` 的"每天重撞"应消失，
  改为首日记一次 + 后续抑制 + 一条诊断；走路预算（resume_walk）中"走了不干活"的天数应下降。
- 护栏要求（沿用 Z3 的"不许静默跳过"）：被抑制的格必须出现在简报/账本，不得凭空消失。

## 3. 引用锚点
- `docs/_probe-save-state-2026-10-20.md` §0 问3（`line 25-29`）—— 8 格坐标、`kind=unknown`、
  `reason=gated count=12`、`first_seen/last_seen` 跨 4 天。
- `docs/_observe-goal12-2026-10-19.md` Z3（`line 90-95, 103`）—— unknown 格三不沾、假 PASS、
  `_tile_reason` 记 `gated` 的 `longrun.py:8154-8159`、T-6 探针建议。
- `brain/agentfarm/longrun.py:8154-8159` — `_tile_reason` 全 skipped 且 kind∉DEFERRED_KINDS ⇒ `gated`。
- `brain/agentfarm/longrun.py:7460` — `shop_offers` 跨天保留口径（可作 `refused_tiles` 持久化参考）。
