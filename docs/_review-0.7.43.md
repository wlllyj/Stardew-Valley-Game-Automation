# 0.7.43 delta（task-242：clear_area 逐格证据记账完整性）独立对抗验收

> 状态：**骨架 + 修前基线（待 0.7.43 冻结 hash 后做正式判定）**。
> 判定人：deputy-lead（只读生产代码；只写 `docs/_review-*.md` + `scratch/`）。
> 正式判定必须用 `git archive <0.7.43 冻结提交>` 冻结树，并记 provenance（`git hash-object` 对照）。

## §0 判定摘要（待填）

（冻结 hash：____；逐卡：task-242 = ____；**0.7.43 可以/不可以放行 A″/B″**：____；还差什么：____）

## §1 对象与读数

| 项 | 值 |
|---|---|
| 0.7.43 冻结提交 | ____（待 Lead 发） |
| task-242 提交 | ____ |
| 修前基线树 | `git archive 533e017`（0.7.42 HEAD）→ `scratch/_t244_base042`（661 文件） |
| 版本 | 修前 `manifest.json`=0.7.42 / `bridge.py:39`=0.7.42 |
| 冻结树读数（待填） | `py_compile -W error::SyntaxWarning` rc=____；定向 Ran____/OK；全量 Ran____/OK；`dotnet build` ____；C# 自检 ____ |

## §2 A 段：范围与越界

- A1 关键文件在树内 ✅（`brain/agentfarm/longrun.py`、`farmwork.py`、`tests/test_longrun.py`）。
- 越界扫描（`mod/`、`manifest.json`、`bridge.py`、`logs/`、`docs/00-开发日志.md`）0 命中：____（待冻结树核）。
- 新字段单列（卡面要求「只许新增字段、须单列」）：____（待交付后 `A3` 读数）。
- 语义未动：`assigned_undone`/`plot_pending`/护栏 B 判据/`checks` 键集（10 键）/事件名 ____。

## §3 B 段：根因与修法覆盖

### §3.1 修前红（0742 账本基线，已复现）

- 夹具：`logs/longrun-smoke-0742.jsonl`（149 行；3 个 `day_end`；无独立 `stage` 事件，阶段记录在 `day_end.stages[]`）。
- **9 个 `clear_area` 阶段 ok ≠ len(cleared_tiles)**，全部在 `day=[1,"winter",5]` 的 `day_end`（行 126）`stage_index=4,5,9,11,12,14,15,16,17`：

| # | ok | cleared | 差 | failed |
|---|---|---|---|---|
| 1 | 7 | 6 | 1 | 0 |
| 2 | 5 | 4 | 1 | 0 |
| 3 | 3 | 2 | 1 | 0 |
| 4 | 2 | 1 | 1 | 0 |
| 5 | 5 | 2 | 3 | 0 |
| 6 | 4 | 2 | 2 | 0 |
| 7 | 2 | 1 | 1 | 0 |
| 8 | 4 | 2 | 2 | 0 |
| 9 | 2 | 1 | 1 | 0 |
| 合计 | **34** | **21** | **13** | 0 |

- 与 `docs/_smoke-0742.md` §5「`clear_area` ok=75 / cleared=62、9 阶段差 13」一致（全账本口径 75/62；本表为这 9 个阶段内部口径 34/21）。
- **代码级根因候选（修前 `brain/agentfarm/longrun.py:6644-6676`）**：`cleared_tiles` 仅收录「`s.ok and s.tile` 且 `before.kind` 与 `after.kind_after|after.kind` **都非空且不等**」的步；否则 `unclear_steps += 1` —— **该计数只进内部变量，账本无对应字段**；而阶段记录 `"ok": len(oks)`（`:6765`）是**按步计数** ⇒ 差额在账本上无痕。这正是「每段 ok ≥ cleared、差 1–3、failed 全 0」的形态。
- 修前假世界复现（真 `FarmWorker` + `FakeClient`，4 格 `weed`）：普通阶段 `ok=4 == cleared=4`；**B3 伪造「ok 但 after 无 kind 证据」⇒ `ok=4 / cleared=3 / explained=0`（静默丢，修前红）= 修后必须转绿**。

### §3.2 修法与覆盖（待交付后填）

- 修法要点/新增字段：____
- 是否覆盖全部漏记路径（多次 `use_tool` 补请求、`clear_neighbor`/`open_way` 连带格、`tree→stump`、stage tiles 与 step tile 不同源、blocked/deferred 路径）：____
- 连带格「目标格 + 连带格」显式区分：____

## §4 C 段：四把伪造（独立判据，修前已可判红/判绿）

判据（我方独立实现，卡面语义）：`ok > len(cleared) + explainable` ⇒ 红；`len(cleared) > ok + collateral` ⇒ 红；清单格不在阶段 tiles 且非 collateral ⇒ 红。

| # | 伪造 | 期望 | 修前读数 |
|---|---|---|---|
| C1 | 漏记一个 ok 格（ok=4 / cleared=3） | 红 | ✅ 红 |
| C2 | 连带清多格只记目标格（ok=1 / cleared=2，无 collateral 解释） | 红 | ✅ 红 |
| C2b | 同 C2 但显式记 `collateral_tiles` | 绿（可解释） | ✅ 绿 |
| C3 | 清单多出未 ok 的格（ok=3 / cleared=4） | 红 | ✅ 红 |
| C4 | `len==ok` 但格子不在阶段 tiles 内（`[70,20]` 越界） | 红 | ✅ 红 |

## §5 D 段：变异实测（自报 vs 实测，待填）

- 作者脚本：____（若未交付 ⇒ 记 **GAP**，自建 ≥2 条补足）。
- 我方自建：`scratch/_t244_mutate.py`（锚点待交付后填；kind = probe / unittest / csharp）。
- 两列表：____

## §6 E 段：结论（待填）

- task-242 判定：____（PASS / PASS-WITH-NITS / FAIL + 证据锚点）。
- **0.7.43 可/不可放行 A″/B″**：____；还差什么：____。

## §7 边界声明

- 只读生产代码；只写 `docs/_review-0.7.43.md` + `scratch/`；不碰游戏/桥、不 deploy、不 bump、不改任务板、不写 `docs/00-开发日志.md`。
- worktree 在制读数只作线索（dev-coder 在制时曾撞到 `longrun.py` 半截 `UnboundLocalError: oks`）；正式判定一律以冻结树为准。
- 探针骨架提交：`73d3c9a`（`scratch/_t244_{baseline,probe,mutate}.py`）。
