# task-15 独立验收（deputy-lead，2026-10-13）

**判定：PASS-WITH-NITS** —— 功能与口径全部达标（含 Lead 的权威定义）；两条 NIT 见 §6，均不阻塞 run3。

验收时点 HEAD `dd7ea96`（release 0.7.22 + task-15 + task-30）。工作树里 `tools/verify-run3.py` 的 +56/-7 行是**我**（Lead 本轮授权）做的口径对齐；同时 Lead 在并行改 `docs/_release-0.7.22.md`、`tools/preflight.py`（与本卡无关）。

## §1 惯例四项（独立跑，不引用自述）
| 项 | 读数 |
|---|---|
| `git status --short` | 验收开始时干净（无 task-15 残留） |
| `python -m py_compile brain/agentfarm/longrun.py brain/agentfarm/farmwork.py` | exit 0 |
| `PYTHONPATH=<repo>\brain python -m unittest discover -s tests` | **Ran 280 tests in 2.517s / OK**（在冻结 HEAD `dd7ea96` 上复跑确认；pwsh 把 unittest 的 stderr 报成 `[exit code: 1]` 是已知噪声） |
| 版本 bump | **两侧一致 = 0.7.22**：`mod/AgentFarm.Bridge/manifest.json:4` = 0.7.22、`brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.22"` —— 更正：Lead 的 release 提交 `dd7ea96`（01:12:29）就落在本卡验收期间，我早期读到的是**提交前**的工作树（0.7.21 未 bump）。以冻结 HEAD 为准已 bump 且两侧一致，`MOD_VERSION_EXPECTED` 与装机版本不会失真。 |

## §2 任务书逐条
### ② 日级验收纳入阶段后置条件（PASS）
- `checks["no_unmet_stages"]` 只统计**有目标阶段**（`tiles > 0`）：`brain/agentfarm/longrun.py:1754-1758`（`last_by_stage`）。
- **Lead 权威定义核对**：`longrun.py:1746-1758` = "按阶段种类取当天**最后一条**记录再求和、只算 tiles>0、`unmet_leftover == 0`"，与 Lead 的定义**逐字一致**；`:1765` 写入 checks。
- 修法 A（zero-target 归零，且 `met` 仍 False）：`longrun.py:798-799`（till_area）、`:803-804`（plant_area）。
- **`stage_exhausted` 未被动**：`longrun.py:1205-1213` 仍保留 `leftover>0`；task-9 用例 `tests/test_longrun.py:1235 test_blocked_leftover_is_not_verified` 仍绿（280 OK 内含）。
- 汇总可见：`day_text` 播报 `longrun.py:1775`；`_finish` 的 `no_unmet_stages`/`unmet_days` `longrun.py:1892,1901,1918`。
- 用例：`tests/test_longrun.py:1266 test_no_seed_no_money_never_tills`（`_leftover` 归零 + `stage_calls==[]`）、`:1822 test_zero_target_day_still_verifies_with_no_unmet_stages`、`:1799 test_env_retry_exhausted_keeps_leftover_and_day_is_not_verified`。
### ③ 种子闸门的时间成本（PASS）
- 每个决策之前跑 + 先买再动 + 局限**写进 docstring 而非断言**：模块 docstring `longrun.py:21-28`（含"本仓库没有实测数字，不编"、"`distance_to_shop` 一律写未定"）。
- `seed_gate` journal 带 `in_plot`：`longrun.py:1059-1075`（`in_plot = pt in plot["tiles"]`）；用例 `tests/test_longrun.py:1302-1309` 断言两种人位（田外 False / 田内 True）。
### ④ 环境挡路不得判死整天（PASS）
- 重试上限 `max_env_retries`（默认 2）与"重跑同一批格子"：`longrun.py:1077-1082`，`:1117-1125`；判据唯一来源 `longrun.py:147 is_env_blocked` → `farmwork.ENV_BLOCK_STATUSES`（`:1116` 注释明说不另抄状态码）；journal `env_retry`（轮次/格数/模态/状态码）`:1124`。
- 日级硬失败 = 目标未完成：`longrun.py:1168-1174`（`failed = [s for s in failed_any if s.tile is None or tuple(s.tile) in left_set]`），另记 `failed_any` `:1183`、`env_block` 计数 `:1185`、journal `env_fail` `:1190-1194`、人话 reason `:1216-1218`。
- 用例：`tests/test_longrun.py:1403`（同一阶段调用内重试做成）、`:1462`（sow env 不封格不占配额）、`:1483`（water env 不占配额）、`:1686`/`:1706`（busy 属 env 不封格）、`:1799`（重试满仍 `run.blocked == {}`、`proven_inert=0`、当天不 VERIFIED）、`:1836`（确实调用模态守卫 `dismiss_calls==1`）。
- 语义达成核对："**可处置的环境挡路不再计入当日硬失败**"成立；"**不会让达标的一天被误判**"由 §3/§4 的口径对齐 + neg-P 反证证明。

## §3 `tools/verify-run3.py` 对齐（我的改动）
1. leftover 自算改 **per-kind last**（与 longrun 同口径）：`report()` 内 `last_by_stage`（约 `tools/verify-run3.py:260-275`）；0 目标阶段不计仍保留。
2. `failed_any` 汇总**只记信息项**；`Σ stage.failed` ↔ `day_end.failed_steps` 的差额容错原样保留（task-15 后两侧同口径，正常严格相等；容错只为旧账本）。
3. **遮蔽可见性**：直接从 `day_end.stages` 推导 —— 同一阶段种类 ≥2 条、更早 `leftover>0`、最后 `==0` ⇒ info；若将来 longrun 真发了 `stage_midway_leftover` 事件则在该 info 后附加说明（不依赖它）。
4. `checks.no_unmet_stages` 交叉核对、"`no_unmet_stages=false` 一律算问题"、差额容错、`finish` 级联降级等既有判据一条没删。

## §4 误报实验（Lead 点名要求）
- `scratch/review-neg-P-t15-last-round-done.jsonl`（生成器 `scratch/_review_neg_gen.py` 新 mode `t15_last_round_done`）：同一天同一阶段种类两条记录 —— 更早一轮 `leftover=5`（`stopped="no_seed"`）、最后一条做净 `leftover=0`；并带 `stage_midway_leftover` 事件、`failed_any=2/failed=0`、`env_block=2`。
  - **新工具 ⇒ exit 0 / VERIFIED**（每天 4 条 info：遮蔽、failed_any、环境挡路）。
  - **旧工具（`git show HEAD:tools/verify-run3.py`）⇒ exit 1**，原话 `[spring 10] checks.no_unmet_stages=True 与自算不一致（有目标阶段遗留 leftover=5 格）` ⇒ 正是"把达标的一天判死"的误报，已被对齐消除。
- `scratch/review-neg-Q-t15-masked-leftover.jsonl`（反方向：更早 `leftover=0`、最后 `leftover=5`）⇒ 新旧工具**都** exit 1（不许被更早的干净记录遮蔽）。
- 全矩阵 27 本（`scratch/_review_matrix.py`，`--json` 取 verdict）：**exit 0 共 6 本** = `journal-green`、`review-neg-G`、`review-neg-I`、`review-neg-K`、`review-neg-K2`、`review-neg-P`；**exit 1 共 21 本** = A/B/C/D/E/F/H/J/K3/K4/Q、`logs/longrun-3day-llm-run1`、`logs/longrun-3day-run1`、`logs/longrun-3day-llm-run2`、`logs/longrun-rehearsal-0.7.22`、`scratch/review-task11-modal-day`、7 本旧料（`_ledger_*`/`journal-green-bad`/`journal-nochecks`）。
- **读数变化**：26 本既有账本**无一本判决改变**（它们都是"一天一条 stage 记录"，per-kind last ≡ 全量相加）；真机 `logs/longrun-3day-llm-run2.jsonl` 新增 2 条**准确** info —— `[spring 10] 阶段 clear_area 当天共 10 条记录：更早一轮 leftover=2、最后一轮 0`、`阶段 till_area 共 4 条、更早 7` ⇒ 真实账本里遮蔽确实存在，现在看得见（判决仍 exit 1，问题数不变）。

## §5 口径一致性（同判据四处）
- 环境状态集合真值源唯一：`farmwork.ENV_BLOCK_STATUSES` → `longrun.is_env_blocked`(`:147`)/`_mark_blocked`/`_count_attempts`；工具只读账本字段、不复制状态码 ✓
- `failed` / `failed_any`：`longrun.py:1182-1183` ↔ 工具 `sum_failed`/`sum_failed_any` 同义 ✓
- `no_unmet_stages`：`longrun.py:1754-1758` ↔ 工具 `last_by_stage` ✓（**改前**工具是"全量相加"，属真实口径漂移，现已消除）

## §6 发现（NIT，不阻塞）
- **N1：Lead 说的 `stage_midway_leftover` 事件不存在。** 全仓 grep `midway` 零命中（`brain/`、`tests/`、`tools/`）⇒ longrun 既没发这条 journal，也没进 `rep.notes`；只有 `longrun.py:1752-1753` 的注释记了局限。影响有限：更早那条 `leftover>0` 记录本就在 `day_end.stages[]` 里可查，且我已让工具**自行推导**并打 info（真机 run2 实证可见）。建议二选一：dev-coder 补这几行 journal，或把口径改成"由工具从 stages 推导"（我已按后者落地）。
- **N2：新口径没有单测。** "同阶段种类当天多轮、以最后一轮为准"只有 `scratch/probe_task15.py`（1040 B，01:08:48）一次性探针 + 我的 neg-P/Q 账本，`tests/test_longrun.py` 无对应用例。建议把 neg-P/Q 的形状固化成假世界用例（同一天两次 `plant_area`：先 `no_seed` 后做净）。
- **N3（非缺陷）：** `logs/longrun-rehearsal-0.7.22.jsonl` 只有 7 行、停在 `outcome`（t≈48s，未到 day_end）⇒ 工具报 `day_end 缺 verified`、`ended_by=?` 属**预期**（1 天且未跑完），不是账目问题；彩排跑完后再看。

## §7 越界与卫生
- 我：只写 `tools/verify-run3.py`（授权）+ `scratch/`（`_review_neg_gen.py` 增 P/Q、新增 `_review_matrix.py`、`_old_verify_run3.py` 对照副本）。未碰 `brain/`、`mod/`、`tests/`、`docs/00-开发日志.md`、`logs/`。
- dev-coder（task-15）：改动全在 writeScopes 内（`brain/agentfarm/longrun.py` + `tests/test_longrun.py`），本轮未碰 `farmwork.py`，无夹带。

## §8 任务板卫生（task-16 常设职责；只报不改）
1. **task-17 已 ready 但在制冲突**：`pending` / owner 空 / `ready=True` / `blockedBy=[task-11, task-15]`（两者都已 completed）。它的 writeScopes = `brain/agentfarm/longrun.py` + `brain/agentfarm/farmwork.py` + `tests/test_longrun.py`，与**在制的 task-19**（dev-coder，同样这三处）完全重叠 ⇒ 现在任何人认领 task-17 都会与 task-19 抢同一批文件。建议：task-17 的 `blocked_by` 补 `task-19`（或用正文写死顺序），否则"ready"这个信号是误导性的。
2. **task-18 也 ready，且踩 0.7.22 冻结线**：`pending` / owner 空 / `ready=True` / `blockedBy=[task-11]`（已完成）。风险两条：①它写 `mod/AgentFarm.Bridge` 全域 + `brain/agentfarm/longrun.py` + `tests` ⇒ 与 task-19 抢 brain 文件；②0.7.22 刚由 Lead 冻结/正在部署，此时再改 Mod 就是"版本号相同、内容不同"（Lead 给 task-24 定过的同一条理由）⇒ 建议排到 0.7.23 并明确"run3/0.7.22 装机前不许认领"。
3. **task-19 在 progress 但写者已 inactive**：`task-19` = `in_progress` / owner dev-coder，而 dev-coder 当前 inactive（inactive ≠ 完成）。它是 run3 的关键前置（`day_end.checks.watered_outdoor` / `final_water`），task-12 正 blocked 在它上面 ⇒ 请确认是"写完待提交"还是"中途停了"。
4. **task-29 ready 但无人可领**：`pending` / owner 空 / `ready=True`，owner 侧 planner-dev 已 inactive；它只碰 `brain/agentfarm/__main__.py` + `tests/test_main_pid_gate.py`，与 task-19 不冲突，纯属挂单（低优先，不阻塞 run3）。
5. **版本一致性**：`manifest.json` = 0.7.22 与 `bridge.py:39 MOD_VERSION_EXPECTED` = 0.7.22 两侧一致（见 §1 更正），不会出现 task-7 复核时我担心的"行为已变但版本未 bump"。
