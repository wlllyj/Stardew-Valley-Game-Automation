# 0.7.42 发布计划（冬季可验证性 + 清障吞吐；A″/B″ 的最后一道门禁）

> 由来：0.7.41 七步冒烟（6 PASS / 1 无法判定 / 0 FAIL，`docs/_smoke-0741.md`）暴露出两条**会直接决定 5 天能否 VERIFIED / 目标 1 是否可达**的真缺陷。
> 结论：**A″/B″ 再顺延到 0.7.42**；这两条不修，冬季跑批每天必然 `stuck`、目标 1 要 400 天。

## §1 卡片

| 卡 | 优先级 | 内容 | 归属 | 验收面 |
| --- | --- | --- | --- | --- |
| task-240 | P0 | **季节闸门**：Mod 暴露 `player.seeds[]`（`{id,name,stack,seasons,plantableNow}`，三态可辨）；脑侧 `plantable_seeds(player, season)` 贯穿 `_farm_plant_work`/`_plot_has_work`/`_stage_tiles("plant_area")`/`seed_gate`/`_preconditions`；**守卫「该去种」只在窗口真有 plantable 目标时才准出现**；当季无种 + 无别的活 ⇒ 诚实 `no_work` + `day_justified=true`（不许 `stuck`）；过季证据 `evidence.why="seed_out_of_season"`（不新增原因码/checks 键） | dev-coder | ≥6 单测（含 smoke-0741 day1 离线夹具）+ ≥3 变异；C# 断言覆盖三态 |
| task-241 | P0 | **清障吞吐**：树/石/枝类目标允许**有界多次** `use_tool`（`TREE_SWING_CALLS=3`，kind 变/目标消失即停；3 次仍 `tool_ineffective` ⇒ blocked + `tool_ineffective_bound` 证据，单发不再 blocked）；**清障预算改体力驱动**（去掉硬编码 2 棵/天，封顶 `MAX_TREES_PER_DAY=20`，`deferred_by_budget` 写「预算 N / 已砍 M」）；`cleared_tiles`/护栏 B/`assigned_undone` 语义不变 | dev-coder | ≥5 单测 + ≥3 变异；冻结后短跑 `farm.trees` 日降幅 > 2 棵、blocked 显著下降 |

顺序：**240 → 241**（都改 `brain/agentfarm/longrun.py`，串行单写者）。两张交付后树干净。

## §2 冻结九步（Lead 独占）

1. `tools/_note-0742.txt`（首行 `v0.7.42`；列 240/241 两条）
2. `python tools/_bump-mod-version.py 0.7.42 --note-file tools\_note-0742.txt`（manifest 0.7.41→0.7.42）
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.42"`（注释 + `--- 历史 ---` 保留 v0.7.41）
4. `dotnet build -c Release --no-incremental`（0 警 0 错；记录 dll/manifest 字节数 —— 本批 Mod 有 `PlayerView.seeds[]` 变更，dll 应变化）
5. 冻结提交（`git diff --cached --name-only` 核对；**禁 amend**）
6. `python tools/check-release.py --expect 0.7.42`（六项全绿）
7. `python tools/deploy-mod.py --no-quit`（0.7.41→0.7.42）
8. `python -m agentfarm goto Farm`（`PYTHONPATH=<repo>\brain`）
9. `python tools/preflight.py --expect 0.7.42 --save-baseline logs\run10j-baseline.json` ⇒ 记五文件 SHA256

## §3 真机门禁（A″/B″ 前）

1. **复跑七步冒烟**（`scratch/smoke-0741.py` 参数化到 0.7.42，`--days 2`）：步 1/2/3/5/6 必须 PASS；步 7 的 `slot_relief` 若有背包压力则须带 `demand/target_free/reached`；`harvest` 子项在冬季仍记【无法判定·无作物】。
2. **冬季可验证性硬判据（本批新增）**：冒烟的日报告里，**至少 1 天 `verified=true`**（冬 0 作物时 `ended_by` 应为 `night` 或 `no_work`，`day_justified=true`），且**不得再出现** `stuck:…守卫仍说还有活：…耕地空着（手上有 N 粒种子）⇒ 该去种`。
3. **清障吞吐判据（本批新增）**：`clear_area` 的 `blocked` 里 `tool_ineffective` 单发封格的条数为 **0**；`farm.trees` 日降幅 > 2 棵；`deferred_by_budget` 理由含「预算 N / 已砍 M」。
4. 全绿 ⇒ A″/B″ 放行（task-113 rev20，0.7.42，同起点协议）。

## §4 A″/B″（task-113 rev20）

- 同起点协议：`logs\ab-backup\A7-start\` 四件备份 → A″（5 天）→ 恢复备份并逐件 SHA256 核对 → B″（5 天，lessons 字节拷贝）；
- 账本 `logs\longrun-runA7-0742.jsonl` / `runB7-0742.jsonl`；
- 判据：`verify-run3 --days 5 --smapi` + `analyze-longrun --window 5` + `run9-lead-check` + `compare-runs` L0–L5；**冬季结构限制**如实写（农务面不可判），清障/经济面必须真机验证。

## §5 已知限制

- 冬季露天 0 作物：`harvest`/浇水/播种在真机上无法被完整验证（240 只保证"不可种时诚实 no_work"，不等于"能种"）。
- 240 的 `plantableNow` 依赖 `CropData.Seasons`；若 Mod 反射拿不到季列表 ⇒ 必须如实 null（fail-closed），届时守卫按"未知"处理，禁止猜。
- 241 的体力驱动预算需要真实体力成本数据；若 `STAMINA_COST_*` 与游戏实际不符，表现为"砍到一半没体力"，需在证据里如实记。
