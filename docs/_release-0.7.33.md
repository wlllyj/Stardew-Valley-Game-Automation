# 0.7.33 发布计划 · **harvest 判据纠正（run A/B 的第一病灶）**

> 背景：run A（0.7.32，`logs\longrun-runA-0732.jsonl`）= **FAIL 0/5**，run B 同日同构建起跑后**首日就被 `harvest` 钉死**（全在 `[60,29]` 一格：一天 41 次 `failed`、两天 284 次尝试 0 成功、`ok_steps=0`）。task-169（log-analyst，`0bb94ba` + `docs\_il-harvest-path.md`）把根因压到唯一解：**Mod 用裸 `Crop.fullyGrown` 判"熟"，而游戏自己用 `HoeDirt.readyForHarvest()`**；且 `interact` 回执只报"没报错"。⇒ **0.7.33 = task-170（Mod+脑同批修）**；run B 已按 Lead 裁定**提前叫停**（无效臂：病灶钉死整天，跑完 5 天只是白烧），游戏已按 `User said (m02833)` 优雅退出（存档 `4310486 B / 2026-10-17 05:04:35.296`，重开起点 = **秋 12 日**）。

## §0 现状与定性（2026-10-17 05:0x）

- **run A 结果**：`finish {code:1, verified_streak:0, actions:415, minutes:37.23, unmet_days:[fall 3,4,5,6,8]}`，尾链 0/5；秋 3–6 逐日同型（`ok_steps=65`、`dry 73/73/72/69`、`ended_reason=stamina:体力 0 < 12`）。外部证据：存档链 5/6、SMAPI 六串 5/5/5/5/5/5（冻结件 `logs\runA-0732-smapi-window.txt` 385136 B / SHA256 `768E6B46…`）。
- **run B（被叫停）**：`04:50:42` 停手，账本 723 行、`last_t=1393.49`、**无 `finish`**；两个完整日（秋 9：`ok 0 / failed 41`，秋 10：`ok 89 / failed 30`）+ 秋 11 进行中；`(60,29)` 那格**跨两个跨日仍是 `ripe=true`**。SMAPI 窗口 584107 B / 8032 行 / SHA256 `DDD6619E…182B`，六串 2/2 配对；存档链 4248971→4260239→4281756。
- **现场独立观测**（`scratch\runB-0732-tile6029-live.json`）：`[60,29]` = `HoeDirt` + `crop 270` + `ripe=true` + `dead=false` + `watered=true` + `standable=true` + `actionable=true`；玩家在 `[60,28]` ⇒ **可达性排除**；`farm` 汇总 `crops 102 / ripeCrops 1 / dryCrops 1 / deadCrops 0`。
- **三层根因（task-169 定案）**：①判据错——`FarmScan.cs:285` / `WorldSnapshot.cs:636` 用裸 `Crop.fullyGrown`，与游戏 `HoeDirt.readyForHarvest()` 在**复收冷却 / 末阶段 / 枯死 / 采集形态**四处不等价；②回执谎报第三次——`Skills.cs:233` `Ok = err == null`、`:234 Status="ok"`（`acted` 只写在 reason 文本里）；③脑侧无"同格试满就当天放弃"的收口 ⇒ 一格钉死整天。
- **L1（教训注入）口径修正**：机器侧直查 47/47 条决策 prompt 含教训节（tool 曾报 0/6 ⇒ `lesson_text()` 键名不匹配 `hint`，已修：`2e3289e` + 6 条单测）。修正后 A 的读数 = **`lessons_total 6 / lessons_hits 4 / lesson_section_present true / injection_effective true`**；两处 miss 是 `stuck_with_leftover|plant_area` 与 `|till_area`（疑似按需过滤，非截断）⇒ 留作 task-162/113 的观察项。

## §1 卡片表（本版）

| 卡 | owner | 依赖 | 内容 | 状态 |
|---|---|---|---|---|
| **task-170** | dev-coder | task-169 ✅ | harvest 判据与回执诚实化：Mod `CropMeta.cs`（反射 `HoeDirt.readyForHarvest()` 为权威，缺项 ⇒ `null`）+ `TileView` 9 个形态字段 + `FarmView.readyCrops` + `ExecResponse.acted`；`tiles[].tool` 判据改 `(ready||dead)?"none":"can"`；`interact` 未动手 ⇒ `no_action`；镰刀类走工具路径；脑侧 `tile_ready`（fail-closed）+ `harvest_tool` + `harvest_gave_up`（同格上限、**不进 `_leftover`**、不进 `checks`）。≥8 单测 + ≥3 变异 | **已交付 `d88498d`**（12 文件 +688/−37；Lead 亲核：`py_compile` exit 0、定向 509 OK、全量 889/2 红=analyzer 缺新事件桶、`dotnet build --no-incremental` 0 警 0 错）。**真机同格验证待做** |
| **task-171** | deputy-lead | task-170 | **task-170 的独立对抗验收**（`:174`）：四条洗白通道 —— 判据 fail-open / 回执谎报复活 / `harvest_gave_up` 变豁免额度 / `readyCrops` 与 `ripeCrops` 口径混淆 | pending（已建，等 170 冻结后 delta 验收） |
| **task-172** | log-analyst | task-170 | analyzer 收录 `harvest_gave_up` + 新字段（`ready`/`readyCrops`/形态字段/`exec.acted`）+ `ripeCrops − readyCrops` 差值单列 ⇒ **全量回 0 红**（冻结硬前置） | in_progress（关键路径） |

（**不属于本版**：task-168（`reduce_scope` 收缩策略，设计稿 rev2 `docs\_design-task168-scope-shed.md`，Lead 已裁定"不拔苗/田区粒度/粘但可释放/conservative 不认输/只进 info"）；task-141/142/151/152/154/155 后续 NIT 卡 —— 见 §5。）

## §2 冻结与装机九步（Lead 独占）

1. `tools\_note-0733.txt` 就绪（首串必须 `v0.7.33`）✅
2. task-172 落地 ⇒ **全量 0 红** 
3. `git add -A`（check-release 把未跟踪文件算脏）
4. `python tools\_bump-mod-version.py 0.7.33 --note-file tools\_note-0733.txt`（manifest 0.7.32→0.7.33）
5. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED` 改 `"0.7.33"`
6. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` = 0 警 0 错
7. 冻结提交 + `python tools\check-release.py --expect 0.7.33`（六项绿，含全量单测）
8. `python tools\deploy-mod.py --no-quit` ⇒ 装机 0.7.33
9. `python -m agentfarm goto Farm` + `python tools\preflight.py --expect 0.7.33 --save-baseline logs\run10-baseline.json`

## §3 真机验证方案（**同格 `[60,29]` 定点**，machine-runner 独占）

存档 = 秋 12 日清晨（重开起点），`[60,29]` 那格熟作物仍在盘上。判据（二选一即通过，**唯一不许**的是"284 次 0 成功还钉住整天"）：
- **(a) 真摘到**：`farm.readyCrops 1→0` 且该格 `crop == null`（或 `kind` 变非作物）；`interact` 回执 `acted=true`/`status=ok`；背包多出对应作物。
- **(b) 判据纠正后不再算可收**：`farm.readyCrops == 0`（`ripeCrops` 允许仍为 1）+ 该格 `ready` 为 `false`/`null` + 脑**不再把它当目标**（当天 `harvest` 目标池空、正常收尾，且**不是**靠 `harvest_gave_up` 洗白：`harvest_gave_up` 若出现必须同时有 `_leftover("harvest") > 0` 的如实 unmet）。
- 外部证据：`observe?detail=full` 差分（前后两份 `tiles[]`）+ 存档 size/mtime 前进 + SMAPI 窗口增量。
- 通过后**才**解冻 brain 侧写入，接着做 task-168。

## §4 放行判据（0.7.33 之后立即跑）

- 冻结前：全量 0 红 + `check-release` 六绿 + task-171 结论明确"可冻结/不可冻结"。
- 冻结后：§3 同格验证通过 ⇒ 重跑 **run A′**（同 0.7.33 构建、`--days 5 --size 5 --max-minutes 240 --max-days 12`、起点秋 12），再把 `logs\longrun-runA′-lessons.json` 拷成 `…runB′…` 跑 **run B′**，用 `tools\compare-runs.py` 出 L0–L5 对照（目标 2 的演进证据）。
- 目标 2 的验收口径不变：**尾部连续 5 天 `verified=true`** + 每日 ≥2 份独立观测 + 落盘六串 + 两侧工具同向（`verdict` + `strict_verdict` 都抄）。

## §5 风险与不做

- **不做**：本版不含 task-168（`reduce_scope`）、不含目标 1 的升级链（task-141/142/151/152/155）。run A′/B′ 仍会受"规模 > 单日体力"（task-158 已缓解但不解决）与"够不着"（task-157 已缓解）影响 ⇒ 尾链可能仍 <5 天，属预期。
- **风险**：`tile_ready` 的 fail-closed 会让旧 Mod（缺字段）下"熟作物永远收不了" —— 但本版 Mod 与脑同批装机，不存在旧 Mod 组合。
- **风险**：`harvest_gave_up` 可能被当成"洗白通道"（试满就放弃 ⇒ 当天仍可能 `no_unmet_stages`？**不会**：`_leftover("harvest")` 不扣 ⇒ 仍如实 unmet）。task-171 必须专门打这条。

## §6 前置与后续

- 前置：task-169 ✅（IL 定案）、task-172（analyzer 0 红）。
- 后续：task-168 实现 → task-171 对抗验收 → 重跑 A′/B′ → 0.7.34（目标 1：155/141/142/151/152 + 154/110）。

## §7 执行记录（Lead 逐条追加）

- （待第 4 步起逐条填）
