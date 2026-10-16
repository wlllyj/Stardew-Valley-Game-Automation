# 0.7.31 发布计划（run9c 诊断 → 分配额口径修复 → run9d/run10 对照）

> Lead 独占落档。上一版：`docs/_release-0.7.30.md`（water_far 逐格判据 + resume 有界 + leftover 口径拆分 + 演进素材质量）。

## §0 run9c（0.7.30，run A 的第一次尝试）—— **真机首次 `finish code=0` / 尾部 3 连 VERIFIED**（诊断价值 + 待 task-146 独立复核定性）

**run9c 结果（Lead 亲核，2026-10-17 00:17）**：
- `finish {"code":0,"verified_streak":3,"actions":513,"minutes":28.03,"stages_seen":["clear_area","plant_area","till_area","water_area"],"no_unmet_stages":false,"unmet_days":["1年 summer 18日"],"stuck_flushes":0}`；
- 逐日：summer 18 `False`（仅 `no_unmet_stages`，= 143/144 两条分配额口径）｜summer 19 `False`（仅 `watered_outdoor`，dry 1/83）｜**summer 20/21/22 `True`（尾部三连，九项 checks 全 true）**；
- 落盘五串 5/5（`NewDay / before save / SaveGame.Save() called. / Saving without compression / completed`），存档 `5766683 / 22:30:13.053` → `3860602 / 2026-10-17T00:16:44.786` 逐次前进；SMAPI 冻结 `logs\run9c-smapi-window.txt`（379854 B / SHA256 `7B95E0F2…2CBF70`）；
- 经济闭环四腿真机走通：`sell` 2（含 `why=need_slot`）→ 次日到账（5→545）→ `buy` 6 中 5 成交（当季 `(O)483 Wheat Seeds`）→ 每天 `plant_area` 落格；
- 有界性：`plot_exhausted_burst`/`review_only_fallback`/`slept_without_work`/`no_day_progress`/`stuck_flushes` 全 0；`modal_dismissed` 2、`eventUp` 0；
- 两侧工具 + 我的复核器：`verify-run3 --days 3` ⇒ **rc=0 `VERIFIED`**（严格口径 `needs_review`，窗口外历史 4 条）；`scratch\run9-lead-check.py` ⇒ **rc=0**（SMAPI 5/5/5/5、自述 vs 自算 5/5 ✅）；`analyze-longrun --window 3` ⇒ rc=1（窗口外历史问题）。
- **诚实披露**：独立观测有 summer 18/19/19-2/21/22/22-2，**summer 20 是 23 秒真空短日、观测窗口错过 ⇒ 【无法判定·窗口错过】**。
- ⇒ **待 `task-146`（deputy-lead 独立对抗复核）给出 PASS / PASS-WITH-CAVEATS / FAIL**，再决定它能否作为 P3 ⑥"连续 3 个游戏日无人工介入"的验收证据；143/144 仍要做（把整跑也做干净 + 与 run10 构成本版同构建的 A/B）。

**已经修好的**（0.7.29/0.7.30 的成果在真机上兑现）：
- **落盘**：跨日保存链 100% 走完（run9b 起 5/5，SMAPI 五串 `NewDay → before save → SaveGame.Save() called. → Saving without compression → completed → after save, starting <次日>` 逐次配对）；
- **经济闭环**：`sell`（含 `why=need_slot` 腾格）→ 次日到账 → `buy`（含 `buy_partial`）→ `plant_area` 成格，四步都有真机留痕；
- **曾经出现过整天全绿**：run9b 的 summer 17（九项 `checks` 全 true、`dry 0/56`）；
- **有界收尾**：`plot_exhausted_burst`/`review_only_fallback`/`slept_without_work` 都有界且不洗白判定。

**run9c day1（summer 18）剩下的唯一缺口**：整天 `ok_steps=116 / failed_steps=0`、九项 checks 只挂 `no_unmet_stages=false`，收尾是诚实的 `no_work`。逐条查 stage 记录后定性为**两条"分配额超过资源"的口径错**：
1. `plant_area assigned 12 ok 11 undone 1 stopped 'no_seed'` + `assigned 4 ok 1 undone 3 stopped 'no_seed'` ⇒ 手上 11 粒种子却分 12 格、剩 1 粒却分 4 格 ⇒ **task-143**；
2. `water_area assigned 70 undone 27 stopped 'need_refill'`（水壶容量 40）+ `assigned 21 undone 3 stopped ''` ⇒ 壶空直接停、剩下格记成 `assigned_undone`，且存在"正常结束却仍有格没做"的不可解释形态 ⇒ **task-144**。

⇒ 这两条不修，run A/run B 都拿不到连续 3 天 VERIFIED；而修它们要改 `brain/`，**会破坏与 run9c 的可比性**。

## §1 卡片表

| 卡 | 内容 | 状态 |
|---|---|---|
| **task-143** | `plant_area` 分配额不得超过手上种子数（`limit = min(per_stage_tiles, seeds)`）；不许把 `no_seed` 塞进诚实上限白名单 | 本版必修 |
| **task-144** | `water_area` 阶段壶空 ⇒ 补水续做（有界 ≤2 次）；补水不可能才如实 `need_refill` + `assigned_undone>0`；消除 `stopped=="" ∧ assigned_undone>0` | 本版必修（blocked_by 143） |
| **task-145** | 对 143+144 的独立对抗验收（重点打"新洗白通道"） | 本版验收（blocked_by 143,144） |
| task-137 | 非 `sleep` 收尾分支 `day_end.final` 可能是旧快照 | 顺延 |
| task-101/107/109/110/117 | 类型校验 / dryTiles 同源 / 卖货如实性 / `ensure_location` 无 try / 教训内容模板 | 顺延 |
| task-141/142 | 用户 2026-10-17 诉求：工具升级（LLM 能建议 + 真能升级） | **run10 之后** |
| task-14/17/18/20/53/83/94 | warp 活锁 / world_stuck / 职业 / 工具等级 / 农场级计数 / 田块规整 | 长期 |

## §2 冻结与装机九步（Lead 独占，命令照抄）

1. 确认 143/144 completed、145 PASS、全量单测 **0 红**；
2. `tools/_note-0731.txt` 首串必须是 `v0.7.31`（列 143/144）；
3. `python tools\_bump-mod-version.py 0.7.31 --note-file tools\_note-0731.txt`（cp1252 末句会 `UnicodeEncodeError` 且退出码 1 —— **版本已写盘**，一律用 `json.load` 核对 manifest）；
4. `brain/agentfarm/bridge.py` 的 `MOD_VERSION_EXPECTED = "0.7.31"`（注释写清本版两项）；
5. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ 0 警 0 错；
6. 提交冻结（`git add -A` 后再看 `check-release`，未跟踪 `scratch/*.py` 也算脏）；
7. `python tools\check-release.py --expect 0.7.31` ⇒ 六项全绿；
8. `python tools\deploy-mod.py --no-quit`；
9. `python -m agentfarm goto Farm --no-focus` → `python tools\preflight.py --expect 0.7.31 --save-baseline logs\run9d-baseline.json`；**不做操作员预置**。

## §3 run9d（run A）+ run10（run B）跑法

- **同一构建**（0.7.31）上跑两次，**只有 `--journal` 路径不同**（sidecar 的 `argv`/`boundary_llm` 已记录可证）。
- run A：`tools\start-detached-longrun.py --days 3 --size 5 --max-minutes 150 --max-days 9 --journal logs\longrun-3day-llm-run9d.jsonl --expect-version 0.7.31`；
- run A 结束后把 `logs\longrun-3day-llm-run9d-lessons.json` **原样拷贝**为 `logs\longrun-3day-llm-run10-lessons.json`（记拷贝时刻 + 两侧 SHA256，写进 `docs/_run10-evidence.md` §1）；
- run B：同命令、`--journal logs\longrun-3day-llm-run10.jsonl`；
- 对照：`python tools\compare-runs.py --run-a logs\longrun-3day-llm-run9d.jsonl --run-b logs\longrun-3day-llm-run10.jsonl`（工具已含 L0–L5 机械判据；L3 只作旁证）；
- 每日独立观测：复用 `scratch\run9c-observe.py`（同格 kind 迁移 + `farm.*` + 体力/钱/种子叠 + `day_end.final` vs 现场）。

## §4 判据（继承 0.7.30 §4，另加三条）

1. 两侧工具同向：`tools\verify-run3.py`（尾部窗口 + `verdict`/`strict_verdict` 两行都抄）与 `tools\analyze-longrun.py --window 3`；
2. 外部证据：存档 size/mtime、SMAPI 窗口冻结（四联/五联计数）、起止快照；**缺失字段一律【无法判定】，缺失 ≠ 通过**；
3. 每次跨日必须落盘（`NewDay` 次数 == `SaveGame.Save() called.` 次数）；
4. **世界差分必须用独立 `observe?detail=full` 差分**（**每日 ≥2 份：晨间端点 A + 收尾端点 B**，同名不覆盖；逐日差分表），只有账本自述不算；**只有 1 份端点的日子，tile kind 迁移一律记【无法判定】**（run9c 的 summer 18/21 就是这个教训，summer 20 更是一份都没有 ⇒ 整日【无法判定·窗口错过】）；
5. **新增**：任何阶段的 `assigned` 不得超过当时的可用资源（种子数 / 壶容），否则 `assigned_undone` 记的是资源缺口而不是 agent 没干完；
6. **新增**：`stopped == ""` 与 `assigned_undone > 0` 不得同时出现；
7. **新增**：`checks.no_unmet_stages=false` 必须能在 `day_end.stages[].assigned_undone` 上逐格解释（解释不了就是口径洞）。

## §5 与 run9c 对比表

| 指标 | run9c（0.7.30，诊断） | run9d（0.7.31，run A） |
|---|---|---|
| 尾部连续 VERIFIED | **3/3 ✅**（summer 20/21/22；`finish code=0`） | 待填 |
| 跨日落盘配对 | **5/5 ✅** | 待填 |
| 经济闭环四腿 | sell→到账→buy→plant 均有留痕 ✅ | 待填 |
| `assigned_undone`（种子/壶空贡献） | >0（summer 18 plant 1+3、water 27） | 期望 0 |
| 独立观测覆盖 | 6 份（18/19/19-2/21/22/22-2）；**summer 20 窗口错过** | 期望每日 ≥1 |

## §6 决定与遗留

- **决定**：run9c **只作诊断证据**（落盘/经济闭环/有界收尾的真机证明），**不作为 A/B 对照的 run A** —— 0.7.31 会改 `brain/`，两次 run 的世界不可比。run A 必须在 0.7.31 上重跑（run9d），教训库显式拷给 run10。
- 遗留：task-137（`day_end.final` 滞后）、task-101/107/109/110/117；用户 2026-10-17 的工具升级诉求（task-141/142，run10 之后）。
- 诚实边界：`lesson` 注入 + `compare-runs` 的 L1–L4 只能证"机制生效 + 同形态减少"；**"自我进化"的正式结论**必须并列两侧工具判决与 L3 的人工核对，L1–L3 任一不成立就写"不足以判定自我进化"（`docs/_run10-criteria.md`）。
