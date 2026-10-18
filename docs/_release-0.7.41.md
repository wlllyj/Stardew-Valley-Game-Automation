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

**前置（缺一不可，先跑再冒烟）**：
- `scratch/save-chain-check.py --selftest` ⇒ **6 夹具全 PASS**（A 红 / B 绿 / C 无法判定 / D 末次顺序 / E 链内逆序 / F 插件行 L16）；
- `tools/verify-run3.py --smapi <0.7.40 抢救前窗口> --before 12:22:00` ⇒ **必须判 problem**（NewDay 3 / Save 2）；同一份全窗口 ⇒ **不得判 problem**（3/3）；两夹具口径见 `scratch/_t239_win/`。

| 步 | 判据 |
| --- | --- |
| 1 | `debug_dump crafting_recipes key=Furnace`：`matchedCount>=1`（验活，不得 unknown_skill） |
| 2 | `debug_dump trigger_actions`：可读、无 `InvalidCastException` |
| 3 | 砍树 A2：有界 ≤3 次 `use_tool`，`kind` 一变即 PASS（`tool_ineffective` 只留痕） |
| 4 | 长跑起跑 = 脱离式、PID 记录、`finish` 出现 |
| 5 | 逐格证据：`clear_area` ok 步的 `cleared_tiles`/before-after（ok=0 时如实【无法判定】） |
| 6 | **`scratch/save-chain-check.py --freeze-smapi`：六串 `NewDay == before save == Save called == completed == after save` 且链内行号单调**（`--days 2` 必须跨 2 次日切；`NewDay > Save` 或逆序 ⇒ FAIL；L16 插件行只进原始计数）；`smoke-0741.py` 只认检查器 verdict，不自己重数 |
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

## §6 冻结与装机执行记录（2026-10-18）

| 步 | 读数 |
| --- | --- |
| 1 note | `tools/_note-0741.txt` 首行 `v0.7.41（2026-10-18）：全脑侧修复批次（0.7.40 七步冒烟抓出的三处真缺陷），Mod 无代码变更（dll 与 0.7.40 同源重建）`，9 行，Python 验 UTF-8 通过 |
| 2 bump | `_bump-mod-version.py 0.7.41 --note-file tools\_note-0741.txt` ⇒ manifest `0.7.40 → 0.7.41` |
| 3 brain | `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.41"`（注释写三条修复 + `--- 历史 ---` 保留 v0.7.40 原文） |
| 4 build | `dotnet build -c Release --no-incremental` **0 警 0 错**；dll **281088 B**（与 0.7.40 字节相同，Mod 确无变更）、manifest **66623 B**；C# 自检 85 断言 |
| 5 冻结提交 | **`7e6bf55`**（`chore(release): 冻结 0.7.41（落盘守卫 + 腾格力度 + §8 兜底）`；3 files +29/−3；未 amend） |
| 6 check-release | `--expect 0.7.41` **六项全绿**：manifest==brain、版本==期望、dll 不比源码旧、py_compile 22 文件、**`Ran 1199 tests / OK`**、树干净 |
| 7 装机 | `deploy-mod.py --no-quit` ⇒ `0.7.40 → 0.7.41`，桥 `modVersion=0.7.41 port=17890`，自动读档（FarmHouse 9,9） |
| 8 goto Farm | ok，`hop1 FarmHouse → Farm source=[3,12] landing=[64,15]` **7625ms** |
| 9 preflight | ✅ `logs\run10i-baseline.json` —— **第 1 年 冬 1 日 06:10 sunny** / Farm(64,15) / 体力 270/270 / 血 100 / **钱 2767g** / 农场[草 0 / 石 106 / 枝 74 / **树 804** / 耕地 18 / 作物 0] / `farmScanSeq 10` / `waterLeft 13` / `tillableCount 173` / `tileCount 400 truncated` / 无模态 / `worldAdvancing true` |

**0.7.41 五文件指纹**（`git archive` / 冒烟逐字比对用）：

```
longrun.py  A728888FEF02ED170C3B81315C8A35E5F41D443DBCAB071D4CA9537A3896C59C   564473
farmwork.py 7DA3D549E23798200307F49F87C17F5E45828DA3BC78B22713242CF8B8086B42   224375
bridge.py   6AED9E257E0DD697D40CF80400E2FD4145C8F1D8FFD6F0285D97B05CE4D230D4    66642
dll         FF05225C6846D80C6CCF4E8B16A15F399FACCBED572705DF886486A8E419BD08   281088
manifest    B0257AFBC4898F45AB7EDC5583C726AC0981A420F98CD1C7EB7ECE3C91191B09    66623
```

**结构限制（冒烟判据按它调整，不改结论）**：装机时是**冬季第 1 天、农场 0 作物** ⇒ §3 步 7 的「至少一天 `harvest` ok>0」物理上不可能出现，记 **【无法判定·无作物】**；步 7 的判红只认 ①零 `missed:intent_no_reason:*` ②`slot_relief` 带 `demand/demand_basis/target_free/reached`。步 5 若 `clear_area` ok=0 同样如实【无法判定】（冬 0 草，但石/枝/树可清，ok 应为正 —— 若为 0 需查清障能力是否又静默缩水）。

## §7 七步冒烟结果（2026-10-18，machine-runner，`629af9f` / 证据 `docs/_smoke-0741.md`）

**6 PASS / 1 无法判定 / 0 FAIL**（`logs/longrun-smoke-0741.jsonl`，253 行 / 8.67 分钟 / 157 动作 / `finish.code=1`）：

| 步 | 结论 | 关键读数 |
| --- | --- | --- |
| 1 | PASS | `crafting_recipes/Furnace` `matchedCount=1`，无 `unknown_skill` |
| 2 | PASS | `trigger_actions` 可读，无 `InvalidCastException`（0.7.37 那个强类型资产面彻底过） |
| 3 | PASS（A2） | 树 `(38,14)` 只 1 次 `use_tool(axe)` ⇒ `kind tree → None`，`calls=1` |
| 4 | PASS | `finish` 出现；`cleanup_modal_stuck=false / cleanup_attempts=0`（task-236 字段真机在场且未触发） |
| 5 | PASS | `clear_area` **8/8** 个 ok 动作带逐格 `cleared_tiles` |
| 6 | PASS | `save-chain-check`：六串 **4/4/4/4/4/4** 全配对 + 链内顺序 4 链 + 末次跨日（winter 4→5）落盘；SMAPI 时点冻结 `208849 B / 2401 行 / SHA256 EF13FD52…FABF6 / BYTE_IDENTICAL=True` |
| 7 | 无法判定（rc=12） | §8 管道全绿：`意图 68 / 0 步 40 / 其中无原因码 0 / 计划无对账 0`、`missed:intent_no_reason:*` 消失、gaps 在场；两项缺真机读数：`slot_relief` 0 次（背包没满未触发）、`harvest` 无作物 |

**步 4 的 4 个日报告**：`ended_by=sleep`、`verified=false`、`ended_reason` **全部以 `stuck:回片区（guard_leftover）连续 5 次都拿不出目标` 开头**；`day_after` 逐日 +1（winter 2→5）、`no_progress_burst{count 5}` ×4（有界机制在跑）、`intent_coverage` 在场（10/37/12/9 条）。

**收尾**：存档四件退前=退后（size+mtime+SHA256）；`stop-game.py` rc=0 ⇒ 进程 0 / `bridge.json` 已删 / 17890 无 LISTENING。

**冒烟抓出的两条真缺陷（0.7.42 门禁）**：
- **task-240**：`plant_area` 季节闸门 + 守卫「该去种」必须有可执行目标 —— 冬季 0 作物 + `Wheat Seeds×10` ⇒ 守卫宣称「29 格耕地空着该去种」而目标池 0 ⇒ 每天 `stuck`、`day_justified=false` ⇒ **冬季永远拿不到 VERIFIED**。
- **task-241**：树类清障要有界多次 `use_tool` + 预算改体力驱动 —— 9 条 `blocked` 全是单发 `tool_ineffective` 封格（A2 证明同类树 1–3 次必倒），且树有硬编码 2 棵/天（874 棵树要 400 天 ⇒ 目标 1 不可达）。
