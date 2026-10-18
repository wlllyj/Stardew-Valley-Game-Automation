# 0.7.41 七步真机冒烟（winter 1–4）· 证据

> 执行：machine-runner｜2026-10-18 13:14–13:26｜冻结 commit `7e6bf55`（Lead 装机）｜
> 脚本 `scratch/smoke-0741.py`（本轮改动：`--no-crops` 结构性限制开关 + `_harvest_ok_check` 无作物口径）｜
> 原始结果 `scratch/smoke-0741.json`｜账本 `logs/longrun-smoke-0741.jsonl`（253 行）｜摘要 `logs/smoke-0741-digest.txt`｜
> SMAPI 冻结副本 `logs/smoke-0741-smapi-window.txt`（本轮 `--refreeze` 覆盖了 12:33 的离线自测副本）。

## §1 环境与版本（五项指纹 5/5 逐字一致）

| 文件 | SHA256 | size |
|---|---|---|
| `brain/agentfarm/longrun.py` | `A728888FEF02ED170C3B81315C8A35E5F41D443DBCAB071D4CA9537A3896C59C` | 564473 |
| `brain/agentfarm/farmwork.py` | `7DA3D549E23798200307F49F87C17F5E45828DA3BC78B22713242CF8B8086B42` | 224375 |
| `brain/agentfarm/bridge.py` | `6AED9E257E0DD697D40CF80400E2FD4145C8F1D8FFD6F0285D97B05CE4D230D4` | 66642 |
| `mod/…/bin/Release/AgentFarm.Bridge.dll` | `FF05225C6846D80C6CCF4E8B16A15F399FACCBED572705DF886486A8E419BD08` | 281088 |
| `mod/AgentFarm.Bridge/manifest.json` | `B0257AFBC4898F45AB7EDC5583C726AC0981A420F98CD1C7EB7ECE3C91191B09` | 66623 |

- 桥：`pid 22632 / modVersion 0.7.41 / port 17890 / game 1.6.15 / SMAPI 4.5.2`。
- `logs/run10i-baseline.json`（Lead 的 preflight，`generatedAt 2026-10-18T13:13:48+07:00`）：`day [1,winter,1] / tod 610 / Farm(64,15) / 体力 270 / 钱 2767g / crops 0 / unwatered 0 / dryCrops 0 / waterLeft 13 / tillableCount 173`，无模态。
- `save-checks` 与 `save-chain-check --selftest`：8 夹具全 PASS；两窗口口径复验 —— 抢救前窗口 **FAIL rc=1**、全窗口 **PASS rc=0**。
- **结构性限制（Lead m04309，判据调整、不改结论）**：冬季第 1 天农场 **0 作物** ⇒ 步 7「至少一天 `harvest` ok>0」物理上不可能，按【无法判定·无作物】记，**不判 FAIL**；步 7 判红只认 ①`missed:intent_no_reason:*` 不得出现 ②`slot_relief` 必须带 `demand/demand_basis/target_free/reached`。

## §2 七步结论

| 步 | 内容 | 结论 | 关键读数 |
|---|---|---|---|
| 1 | `debug_dump crafting_recipes/Furnace` | **PASS** | `matchedCount=1`、无 `unknown_skill` |
| 2 | `debug_dump trigger_actions` | **PASS** | 可读、无 `InvalidCastException`（逐表 fail-closed 字段在场） |
| 3 | 单技能砍树（A2：≤3 次调用） | **PASS** | `(38,14)` `kind tree → None`、**calls=1** |
| 4 | 2 日长跑（`start-detached-longrun --days 2 --size 5 --max-minutes 60 --max-days 4`） | **PASS** | 跑出 `finish`（253 行 / 8.67 分钟 / 157 动作 / exit 1） |
| 5 | `clear_area` 逐格判据 | **PASS** | **8/8** 个 ok 动作带 `cleared_tiles`/kind 证据 |
| 6 | 日切保存守卫 | **PASS** | `save-chain-check` 判六串 **4/4/4/4/4/4** 全配对（末次跨日已落盘） |
| 7 | analyzer §8 + task-236/237 验收面 | **无法判定**（rc=12） | §8 干净（0 无原因码/0 无对账、`missed:intent_no_reason:*` 已消失）但 `slot_relief` 本批 0 次、`harvest` 无作物 ⇒ 两项【无法判定】 |

**总计：6 PASS / 1 无法判定 / 0 FAIL。**

## §3 步 1–2（内省面）

- 步 1：`table=crafting_recipes` 读到 `Furnace`，`matchedCount=1`，无 `unknown_skill`。
- 步 2：`table=trigger_actions` 可读、无 `InvalidCastException`（0.7.37 的强类型资产修好后首次冒烟通过）。
- 步 3（A2）：窗口内 `kind=="tree"` 且四邻有可站格的格中选 `(38,14)`；`move_to` 后**只发 1 次** `use_tool(axe)` ⇒ `kind tree → None`（首格即倒，未用满 3 次额度）。

## §4 步 4（2 日长跑 → 实跑 4 个日报告）

`finish` 原文：
```json
{"event":"finish","t":519.94,"code":1,"verified_streak":0,"actions":157,"minutes":8.67,
 "stages_seen":["clear_area","plant_area","till_area"],"no_unmet_stages":false,
 "unmet_days":["1年 winter 1日","1年 winter 2日","1年 winter 4日"],
 "stuck_flushes":0,"cleanup_modal_stuck":false,"cleanup_attempts":0,"cleanup_menu":""}
```
> 新字段 `cleanup_modal_stuck=false / cleanup_attempts=0 / cleanup_menu=""`（task-236 落盘守卫）真机在场且未触发。

4 个日报告全部 `ended_by=sleep`、`verified=false`、`ended_reason` 均以 `stuck:回片区（guard_leftover） 连续 5 次都拿不出目标` 开头：

| 日 | ok/skip/fail | 坏判据 | 守卫仍说的"活"（原文节选） |
|---|---|---|---|
| winter 1 | 13/1/0 | `no_unmet_stages, day_justified` | farm 口径还有 **29** 格耕地空着（手上有 10 粒种子）⇒ 该去种；今天早些时候还有 148 格没做完 |
| winter 2 | 47/4/**40** | `no_hard_failures, no_unmet_stages, day_justified` | 还有 **69** 格耕地空着…；203 格没做完 |
| winter 3 | 4/2/0 | `day_justified` | 还有 **61** 格耕地空着…；188 格没做完 |
| winter 4 | 12/2/1 | `no_hard_failures, no_unmet_stages, day_justified` | 还有 **65** 格耕地空着…；158 格没做完 |

- `day_after`：winter 2 → 3 → 4 → 5 逐日 +1（4 次跨日）；`day_cap{days 4, max_days 4}` 收尾。
- 每天 `final_water`：`crops=0 / dry=0`（冬季无作物，符合世界状态）。
- `intent_coverage[]` 在场（daily 10/37/12/9 条），`no_progress_burst{count 5}` ×4（有界机制生效、没有空转）。
- `plant_area` 失败：day 2/4 各有 `plant_area 0 ok / 10 failed`、`reasons={"failed":10}` ⇒ 冬季播种失败（见 §9 观察 2）。
- `blocked` 事件 9 条：**全部是砍树格 `tool_ineffective`**（axe 挥 6 次无效、目标格仍是 tree），涉及 `[36,10] [60,22] [57,24] [62,23] [61,26] [66,19] [72,20] [69,19]` 等。
- `deferred_by_budget{task:"clear_area_tree", why:"今天已砍 2 棵（上限 2）"}` ×3 ⇒ 砍树预算在生效。
- `encircled_summary{count 1, attempted 15, bound_basis 14, engaged 14, tried_open_steps 0, tiles [[38,11]]}`。
- `scope_shed_refused{zone:"field_ne", reason:"no_deficit"}` ×2。

## §5 步 5（逐格证据）

`clear_area` 的 8 个 ok 动作**全部**带 `cleared_tiles`（逐格 kind 前后），例：`('clear_area', 1, 0, cleared_tiles=1)`；日 1 的两段 `clear_area` 各 1 格、日 3 一段 3 格、日 4 一段 0 格（该段无 ok 步，不造假）。

## §6 步 6（日切保存守卫）

`scratch/save-chain-check.py --freeze-smapi` 判定 **PASS**：
- 六串 `NewDay 4 / before save 4 / SaveGame.Save() called 4 / Save task 4 / completed 4 / after save 4`（**4/4/4/4/4/4 全配对，链内顺序 ✅ 4 次链**）。
- SMAPI 时点冻结（**13:25:32，跑完立刻冻，之后源文件继续长到 209342 B 未复冻**）：
  `logs/smoke-0741-smapi-window.txt` = **208849 B / 2401 行 / SHA256 `EF13FD52C2964AFF6C9C9E5DC1B96057E9B3D5AA2C033FA1E03A3784FB2FABF6`**、`BYTE_IDENTICAL=True`。
- 存档链：跑完主档 `Wahaha_450799035` **3197212 B / 13:25:02**、`_old` 3192059 B / 13:24:06 ⇒ 末次跨日（winter 4→5）确实落盘（与 `after save` 时刻一致）。

## §7 步 7（analyzer §8 + task-236/237 验收面）

- analyzer `rc=1`、verify-run3 `rc=1`（日级未达标，冒烟不据此判 FAIL），但 **§8 管道全绿**：
  - `未执行意图: 意图 68 条 / 0 步 40 条 / 其中无原因码 **0** 条 / 计划无对账 **0** 条`；
  - `missed:intent_no_reason:*` **已消失**（task-236 验收面 ✓）；
  - `s8_red_tokens = 无`；`gaps` 文件已生成；`day_end.intent_coverage` 在场。
- 【无法判定】两项（缺失≠通过）：
  1. `slot_relief` **0 次**（本批背包没有满、空间压力通道没被触发 ⇒ 无法验收其 `demand/target_free/reached` 字段）；
  2. `harvest` 子项：**无法判定·无作物**（冬季第 1 天 `farm.crops==0`，`intent_coverage` 里根本没有 harvest 条目）。

## §8 收尾（优雅退出 + 四项核对）

- 退出前存档四件（size / mtime / SHA256 前 16）：主档 `3197212 / 13:25:02 / 9CE9AA729FAB347A`、`SaveGameInfo 31409 / 13:25:02 / 33D8C25308653088`、`_old 3192059 / 13:24:06 / 02AF90F74E8949CA`、`SaveGameInfo_old 31407 / 13:24:06 / 63698FCDB395EE83`。
- `python tools/stop-game.py` ⇒ **rc=0**、`✅ 游戏已退出（原 pids=[22632]）`。
- 四项核对：**进程 0 / `bridge.json` 已删 / 17890 仅 2×TIME_WAIT（无 LISTENING）/= 存档四件逐字未变（size+mtime+SHA256 全部一致）**。
- 未跨日、未落盘（退出前后存档哈希一致）⇒ 读档起点 = 服务端 fall/winter 5 之前那份存档（winter 5 清晨已在内存，随退出丢弃）。

## §9 结论与两条新观察（供 Lead 裁定，不影响七步结论）

**结论：0.7.41 七步冒烟 6 PASS / 1 无法判定（步 7 两项结构性无法判定）/ 0 FAIL。** 0.7.40 报的两个管道问题（末次跨日不落盘、`missed:intent_no_reason`）本批均未复现。

**观察 1（重要）：`clear_area` 砍树仍是"单次调用判失败"** —— 9 条 `blocked` 全是 axe 单次 `use_tool` 回 `tool_ineffective`（Mod 内部挥 6 次、树未倒）后即判该格 blocked；而同一台机器同一次冒烟的步 3（A2）证明**同一类树 1–3 次调用必倒**。⇒ A2 判据只落在冒烟骨架，**生产代码的 `clear_area` 路径没跟上**：每天 2 棵的砍树预算基本被"单次调用失败"吃掉，4 天实际只清掉 8 格，清障进度被这个口径卡住。**建议立案**（brain 侧：`clear_area`/`clear` 对 tree 类目标做有界多次 `use_tool`，或对 `tool_ineffective` 按"未完成但可继续"处理，而不是记 blocked）。

**观察 2：冬季守卫把"耕地空着 + 有种子"当成必须播种** —— 4 天 `stuck:回片区（guard_leftover）` 的 `reasons` 都是"farm 口径还有 29/69/61/65 格耕地空着（手上有 10 粒种子）⇒ 该去种"；但冬季露天无法播种（`plant_area 0 ok / 10 failed`，`reasons={"failed":10}`）⇒ **守卫每天必然判"还有活"，跑步无法收敛**。**建议立案**（brain 侧：冬季/不可播种季节把"该去种"降级或豁免，否则冬季无人值守永远拿不到 VERIFIED）。

## §10 保留物与诚实声明

- 保留：`logs/longrun-smoke-0741.jsonl`（253 行）、`logs/longrun-smoke-0741-gaps.json`、`logs/smoke-0741-smapi-window.txt`（冻结副本）、`logs/smoke-0741-digest.txt`、`scratch/smoke-0741.json`、`scratch/smoke-0741-save-chain.json`、`scratch/run10i-baseline.json` 不动。
- 判据调整留痕：①SMAPI 副本用 `--refreeze` 覆盖了 12:33 的离线自测副本（那是自测产物、不是真跑窗口）；②`--no-crops` 是为了遵守 Lead m04309 的结构限制，只把"harvest ok>0"子项记【无法判定·无作物】，**没有**把任何 FAIL 改判成 PASS；③步 5 用阶段级 `cleared_tiles` 作逐格证据（与 0.7.40 一致）。
- 不确定项：步 7 的两项（slot_relief 未触发、harvest 无作物）**没有**真机读数，只能等有作物/背包压力时再验；`blocked` 里 `tool_ineffective` 的树格为何单发不倒（等级/体力/树桩/位置？）尚未定位，观察 1 只证明"单发不够、多次够"。
- 未做：没 `load_save`、没 `craft/place/buy/sell`、没改存档、没第三次起跑；游戏已优雅退出。
