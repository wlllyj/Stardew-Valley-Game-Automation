# 0.7.41 发布计划（落盘守卫 + 腾格力度 + §8 兜底）

> 由来：0.7.40 七步冒烟 4 PASS / 1 无法判定 / **2 FAIL**（末次跨日未落盘、`missed:intent_no_reason`），
> 另一项"通道通但力度不足"（`slot_relief` 每天 1–3 格 vs `harvest` 需 12 格）。
> 结论：**A″/B″ 暂缓**，先修这三处再冻结 0.7.41，否则对照会被"每天 blocked / 最后一天丢失"污染。

## §1 卡片

| 卡 | 优先级 | 内容 | 归属 | 验收面 |
| --- | --- | --- | --- | --- |
| task-236 | P0 | 末次跨日落盘守卫：收尾见 `ui.isModal` ⇒ ≤3 次 `dismiss_modal`+observe（journal `cleanup_dismiss{menu,ok,tries}`）；3 次仍卡 ⇒ `cleanup_blocked` + `finish.cleanup_modal_stuck=true`（不洗白）；`tools/verify-run3.py` 加 `--smapi`：`NewDay > Save called` ⇒ problem，无 SMAPI ⇒【无法判定】 | dev-coder | 单测 ≥4 + 变异 ≥2；`save-chain-check.py` 一红一绿两夹具 |
| task-237 | P0 | 需求驱动腾格：`harvest_demand=min(可收格数,12)`（三态缺失 ⇒ conservative=3 + `demand_basis`）、`target_free=min(SLOT_RESERVE+demand,12)`、**harvest 之前**调用、`SLOT_RELIEF_MAX` 3→6、叠数 5→10、优先卖收获产物、`slot_relief` 加 `demand/target_free/reached`；**并吸收 task-235**：`sell` 前先 `dismiss_modal` 并确认 `ui.isModal==false`，否则不卖、如实 blocked（同一机制，别写两套） | dev-coder | 单测 ≥6 + 变异 ≥3；冒烟里至少一天 `harvest` ok>0 |
| task-238 | P1 | §8 兜底：`executed_steps==0 && reasons=={}` ⇒ 汇总前回填**闭合原因码**（`why="finalize_fallback"` + 当天 `ended_by` 原文）；只补原因码，不改 `executed_steps`/`checks`；`docs/_run10-criteria.md` §8.2c 补语义 | dev-coder | 单测 ≥4 + 变异 ≥2；`missed:intent_no_reason:*` 消失 |

顺序：**236 → 237 → 238**（都改 `longrun.py`，串行单写者）。全部交付后树干净。

## §2 冻结九步（Lead 独占）

1. `tools/_note-0741.txt`（首行必须以 `v0.7.41` 开头；列 3 条 Mod/脑侧变更）
2. `python tools/_bump-mod-version.py 0.7.41 --note-file tools\_note-0741.txt`（manifest 0.7.40→0.7.41）
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.41"`（注释 + `--- 历史 ---` 保留 v0.7.40）
4. `dotnet build -c Release --no-incremental`（0 警 0 错；记录 dll/manifest 字节数）
5. 冻结提交（提交前 `git diff --cached --name-only` 逐条核对；**禁止 amend**）
6. `python tools/check-release.py --expect 0.7.41`（六项全绿：manifest==brain、dll 新于源码、py_compile、全量单测、树干净）
7. `python tools/deploy-mod.py --no-quit`（0.7.40→0.7.41、桥 `modVersion=0.7.41`）
8. `python -m agentfarm goto Farm`（需 `PYTHONPATH=<repo>\brain`）
9. `python tools/preflight.py --expect 0.7.41 --save-baseline logs\run10i-baseline.json` ⇒ 记五文件 SHA256 指纹

## §3 真机冒烟（A″/B″ 门禁）

`python tools/start-detached-longrun.py --days 2 --size 5 --max-minutes 60 --max-days 4 --journal logs\longrun-smoke-0741.jsonl --expect-version 0.7.41`，随后 `scratch/smoke-0741.py`：

| 步 | 判据 |
| --- | --- |
| 1 | `debug_dump crafting_recipes key=Furnace`：`matchedCount>=1`（验活，不得 unknown_skill） |
| 2 | `debug_dump trigger_actions`：可读、无 `InvalidCastException` |
| 3 | 砍树 A2：有界 ≤3 次 `use_tool`，`kind` 一变即 PASS（`tool_ineffective` 只留痕） |
| 4 | 长跑起跑 = 脱离式、PID 记录、`finish` 出现 |
| 5 | 逐格证据：`clear_area` ok 步的 `cleared_tiles`/before-after（ok=0 时如实【无法判定】） |
| 6 | **`scratch/save-chain-check.py`：`NewDay == Save called == after save`**（`--days 2` 必须跨 2 次日切；有 `NewDay > Save` ⇒ FAIL） |
| 7 | `analyze-longrun --days 2`：**不得出现 `missed:intent_no_reason:*`**；`slot_relief` 带 `demand/target_free/reached`；**至少一天 `harvest` ok>0** |

全绿 ⇒ A″/B″ 放行；任一 FAIL ⇒ 修卡再冻结，不许"带病起跑"。

## §4 A″/B″ 门槛（task-113）

- 同起点协议：起跑前把主档四件备份到 `logs\arm-baseline-0741\`，A″ 收工后 B″ 前用备份还原（Lead/machine-runner 独占，不 `load_save` 到别的档）；
- 账本：`logs\longrun-runA6-0741.jsonl` / `logs\longrun-runB6-0741.jsonl`；教训库字节拷贝 + 两侧 SHA256；
- 判据：`tools/verify-run3.py --days 5 --smapi`（含 §8 与落盘）+ `tools/analyze-longrun.py --window 5` + `scratch/run9-lead-check.py` + `tools/compare-runs.py` L0–L5；
- 判决口径：连续 5 日 VERIFIED + 每日 ≥2 份独立观测 + 落盘六串 + L0–L5 对照（目标 2）；目标 1 的「指定作业区清空」由 task-151 rev5 判定。

## §5 已知限制

- 冒烟只有 2 天，`harvest` 是否真收成受种子/体力/背包共同影响；若 2 天都不出现 harvest ok，需在证据里如实写"能力未验证"而不是判 PASS。
- `save-chain-check.py` 只判"次数配对"，不判"存档内容"；内容正确性仍靠存档四件 size/mtime 与 `after save, starting <season> <day>` 原文。
- `slot_relief` 卖掉的是"收获产物"，若当天无收获产物则只能卖盈余材料（仍受白名单与建造预留约束）。
