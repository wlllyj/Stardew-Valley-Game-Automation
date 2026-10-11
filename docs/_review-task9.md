# 独立复核：task-9（brain 账目修复：blocked 不得算成功 / 没种子不垦地 / LLM max_tokens 16384）

- 复核人：deputy-lead（只读代码；未改 brain/mod/tests/tools，未碰游戏/桥，未改任务板）
- 复核时间：2026-10-11 22:5x（Asia/Bangkok）
- 判定：**PASS-WITH-NITS**（task-9 四条验收条款全部满足；两条跨任务口径残留路径见 §4，都不属于 task-9 声明范围，但必须在 task-15 里裁定，否则 run3 的"连续 3 日 VERIFIED"可能被误判）

## 0. 基线（先钉事实，避免"口头已完成"）

- HEAD = `8f1134a`；`git status --short` 与 `git diff HEAD` **均为空**。
- task-9 的改动**已经在版本库里**，不是"尚未提交的工作树改动"：
  - `git log --oneline -S "DEFAULT_LLM_MAX_TOKENS = 16384" -- brain/agentfarm/longrun.py` → `0784041`
  - `git cat-file -e 0784041^:brain/agentfarm/longrun.py` → `fatal: ... exists on disk, but not in '0784041^'`（该文件随 `0784041` 新入库）
  - `git log --oneline -- brain/agentfarm/longrun.py tests/test_longrun.py` → 都只有 `0784041`
  - ⇒ task-9 已随"大脑四层"提交 `0784041` 一起入库；Lead 若要"单独提交 task-9"，实际已无未提交内容（可核：`git diff HEAD` 空）。
- 独立命令与结果：
  - `python -m py_compile brain/agentfarm/{longrun,planner,llm}.py` → **exit=0**
  - `PYTHONUTF8=1 PYTHONPATH=<repo>\brain python -m unittest discover -s tests` → **`Ran 188 tests in 2.207s` / `OK`**（pwsh 把 unittest 的 stderr 记成 `[exit code: 1]` 是噪声；`$LASTEXITCODE` 实测 0）

## 1. 逐条对照 task-9 验收条款

| # | 条款 | 结论 | 我亲眼核的证据（文件:行） |
|---|---|---|---|
| 1 | `blocked` 只免重试、不得判定成功；只剩 blocked 格 ⇒ `postcondition_met=false`；reason 不许自相矛盾；`classify_outcome(postcondition_met=False)` ⇒ needs_review | **PASS** | `longrun.py:965` `met = bool(all_steps) and not leftover`；`longrun.py:667-693` `_leftover` 五个分支（water/harvest/clear/till/plant）**没有任何一处过滤 `self.blocked`**；`longrun.py:970-975` 阶段记录 `"leftover": len(leftover)`；`longrun.py:998-1005` reason `后置条件未成立（还剩 N 格，其中 M 格已判定干不动：<格> <理由>）`，`leftover==0` 时走 `longrun.py:1006-1008`"一格目标都没有"（不会出现"还剩 0 格"）；`planner.py:697-716` `classify_outcome` 仅在 `postcondition_met and not skipped and not error` 时给 VERIFIED；单测 `tests/test_longrun.py:1090-1119`（断言 `leftover` 集合看得见被封格 n==1、reason 含"还剩 1 格"/"1 格已判定干不动"、不含"还剩 0 格"，且 `stage_exhausted.leftover=1, doomed=1`） |
| 2 | 种子 0 且钱 < `seed_price` ⇒ `till_area`/`plant_area` 目标集合一律为空，且与守卫/简报同口径 | **PASS** | 执行层闸门 `longrun.py:649-657`（`_seed_outlook` 的 `can_plant` 为假 ⇒ `pool=[]`）；`_seed_outlook` `longrun.py:488-494`（`seeds>0 or (allow_buy and money>=seed_price)`，默认 `allow_buy=True`/`seed_price=20`，`longrun.py:214-216`）；守卫同口径 `longrun.py:499,508,518,520`；简报同口径 `longrun.py:567,580-583,594-595`；`work_reasons` 同口径 `longrun.py:706-708`；单测 `tests/test_longrun.py:1121-1150`（断言 `run_stage` 一次都没被调用 + 只播报一次 `seed_gate`，并断言 `_leftover("plant_area")` 仍非空 ⇒ 闸门是"目标集合"而不是"复核集合"） |
| 3 | 默认上限 16384（planner + longrun + tools）且保留截断/回退原因 | **PASS** | `llm.py:37`、`planner.py:935`、`longrun.py:128`、`tools/run-longrun.py:71`（import `DEFAULT_LLM_MAX_TOKENS`）、`tools/plan-llm-manual.py:51`；`PlannerDecision.truncated` `planner.py:661-664`，置位 `planner.py:1022`（`_describe_failure` 把 `status` 拼进字符串，`planner.py:1045-1050`），入 journal `longrun.py:1279`；`longrun.py:242-244` 播报/记账"生效值"；单测 `tests/test_longrun.py:1152-1184`（含 4096 反例与"网络失败不许标 truncated"反例） |
| 4 | 单测：blocked 不得 VERIFIED / 种子 0 钱<20 不垦地 / 默认 16384 | **PASS** | 三条用例即上表 `tests/test_longrun.py:1090`、`:1121`、`:1152`；全量 188 OK（见 §0）。用例断言非空转（读的是返回值与 journal 事件，不是重述实现） |

## 2. 我另外独立复核的"账目是否还能被洗白"

- `_leftover` 内**没有**任何别的地方排除 blocked：逐分支读过 `longrun.py:679-693`；`self.blocked` 在 longrun.py 的全部出现点（`:305,:501,:557,:559,:662,:670,:845,:847,:956,:957,:959,:1001,:1223`）**只有 `_stage_tiles`（:662）、`retryable`（:956）、`doomed`/`capped` 分类（:957,:959）和文案（:1001）在用它**，判定成功的 `_leftover`/`met`（:965,:667-693）都不用。⇒ 条款 1 的"洗白"主路径已封。
- `stage_exhausted` 时：`met=False`（:965）、`leftover=len(_leftover(...))`（:974，含 doomed/capped；单测实测 1）、journal 里同时给 `leftover` 与 `doomed`（:987-989）⇒ 不会把"只剩干不动"说成"没有目标"。
- grass 属 `ACTIONABLE_KINDS`（`longrun.py:53`），且 `farmwork.clear()` 空挥后记 `skipped`+`proven_inert`（`farmwork.py:593-597`）而不是 `failed` —— 这是下面 R1 的触发条件。

## 3. 附带：`tools/verify-run3.py` ↔ journal 字段对账（常设职责②，本次顺带做）

- 用真实 run2 journal 逐字段核对：`verify-run3.py` 读的 `day_end.day/ended_by/ended_reason/final/checks/verified/ok_steps/skipped_steps/failed_steps/stages` **全部存在**；实测 `logs\longrun-3day-llm-run2.jsonl` 的 day_end 键 = `[checks, day, day_text, ended_by, ended_reason, event, failed_steps, final, notes, ok_steps, outcomes, plots, skipped_steps, stages, started_at, t, verified]`；`final.unwatered_crops`（`longrun.py:398`）、`stages[].leftover`（`longrun.py:974`，run2 的 16 条 stage 记录条条都有）、`sleep.ok`（`longrun.py:787`）、`decision.llm`（`longrun.py:1274`）、`finish.code`（`longrun.py:1494`）均对得上。**无字段名漂移。**
- 工具行为实测：`scratch\journal-green.jsonl` → `结论：VERIFIED` exit 0；`scratch\journal-green-bad.jsonl` → `checks.no_unmet_stages=false` 三条、exit 1；`scratch\journal-nochecks.jsonl` → 走 leftover 回退（`verify-run3.py:163-171`）exit 1；真实 run2 → exit 1（0 跨日 / no_day_progress ×1）。
- Nit（不影响判定）：`verify-run3.py:108` 收集 `event=="stage"`，而 longrun **从不**写 `stage` 事件（green 合成账本里有 3 条）⇒ 这是死回退；`:214` 的 `or len(d["stages"])` 在真实账本里恒为 0，但 `day_end.stages` 一定存在，所以不影响任何结论。

## 4. 残留路径（不属于 task-9 声明范围，但会影响 run3 判定，必须由 Lead 在 task-15 里裁定）

- **R1（日级 checks 仍不看阶段后置条件）**：`longrun.py:1358-1365` 的 `rep.checks` 只有 `slept_by_us / no_hard_failures / crops_watered / day_justified`，**没有**阶段后置条件 ⇒ 阶段 `needs_review`（leftover>0）时当天**仍可能** `verified=True`。可达性有真机实证：run2 的 `day_end.stages` 里有 `{"stage":"plant_area","tiles":2,"ok":1,"failed":0,"stopped":"no_seed","leftover":1}`、`{"stage":"till_area","tiles":12,"ok":12,"failed":0,"leftover":5}` —— `failed=0` 却有 leftover。task-15 的 `no_unmet_stages` 正是补这条，`tools/verify-run3.py` 也会优先读它；task-12 的 `blocked_by` 已含 task-15 ⇒ 只要 task-15 落地就能关门。**task-15 落地前不得跑 run3 验收。**
- **R2（`_stage_tiles` 有种子闸门、`_leftover` 没有 ⇒ 判定依赖"远近距离"）**：`longrun.py:649-657` 把 `till_area`/`plant_area` 目标掐空，但 `longrun.py:686-692` 的 `_leftover` **不掐**（task-9 的用例 `tests/test_longrun.py:1133` 有意断言它非空）。后果：当作业区离玩家 >`OBSERVE_REACH=14`（`longrun.py:133,1041`）时，`_verify_intents` 判 `unknown` 并把意图留下（`longrun.py:1049-1056`），`_step_stage` 会走进作业区、拿到 0 目标、`all_steps` 为空而 `leftover>0` ⇒ 阶段照样记进 `rep.stages`（`longrun.py:970-975`）。此时 task-15 的 `no_unmet_stages=all(not s["leftover"])`（以及 `verify-run3.py:163-171` 的 leftover 回退）会把这天判成"有阶段没做完" ⇒ **3 日连续 VERIFIED 被一个本无活的阶段打断**（run3 起始钱 14g、种完即 0 种子，正是这个场景）。同一场景近处走 `cancel`（`:1057-1059`）则不记阶段、当天可 VERIFIED ⇒ 验收结论取决于距离，属于不可接受的随机性。
  - 建议口径（供 task-15 作者二选一，不要两头都改）：① `_leftover` 对 `till_area`/`plant_area` 也套 `can_plant`（"没种子 ⇒ 今天本来就不该动这块地"），此时 leftover=0、met 仍 False，`no_unmet_stages` 才为 True；或 ② `no_unmet_stages` 只统计"当天真的发起过动作"的阶段（`tiles>0`），把 zero-target 阶段排除。另建议把"为什么这一阶段没有目标"（seed_gate / stage_exhausted / far-walk）写成阶段记录里的显式字段，避免 reason 文案（`longrun.py:901-902` 说"没有目标"）与 leftover（>0）在同一份账本里互相矛盾。
- **R3（Nit，越界检查）**：`brain/agentfarm/__main__.py:761` 的 `--max-tokens` 默认值也改成了 16384，但这个文件**不在 task-9 的 writeScopes**（task-9 只列了 planner/longrun/tests/tools 两份 CLI；`__main__.py` 属于 task-1 范围）。改动本身正确且无害，仅记录口径。**未发现**对 `docs/00-开发日志.md`、`logs/`、`mod/` 的改动；无 deploy、无真机触碰。

## 5. 判定与给 Lead 的下一道门

- **task-9：PASS-WITH-NITS** —— 四条验收条款逐条有代码行 + 独立命令证据；188 OK；`_leftover` 洗白主路径已封。
- NITS 两条（R1/R2）都不是 task-9 声明范围内的事，但**都是 task-15 的必答项**，且都直接决定 run3 的 `verified_streak` 能不能凑够 3。建议 Lead 在派 task-15 时把 R2 的两个备选口径写明（否则 task-15 按现文案"保证 leftover==0"会与 task-9 的 `_leftover` 语义相撞）。
- 对 task-7 的后续复核我已就位；`verify-run3.py` 字段对账无漂移，run3 可继续用它做主判据。

## 6. 追加发现（读到 Lead 的 task-15 任务书正文后；必须赶在 task-15 开工前裁定）

- **task-15 正文把两条不同的代码路径混成了一个名字，照字面实现会撤销 task-9 的条款①。** 实测当前 `longrun.py` 里：
  - `longrun.py:976-977`：`if not all_steps and not met:` → journal **`stage_no_target`**，`leftover=len(leftover)`。这才是"一格目标都没有（这一阶段没有该动的格子）"的路径；task-9 之后 `plant_area`/`till_area` 的 `_stage_tiles` 被种子闸门掐空正是走这里。
  - `longrun.py:981-989`：`if not met and not retryable:` → journal **`stage_exhausted`**，显式同步 `leftover=len(leftover), doomed=len(doomed), capped=len(capped)`。这是"剩下的格子一个都不值得再试（全被封格/到本日上限）"的路径，**leftover>0 是它的设计语义**，也是 task-9 条款①的落点。
  - Lead 的 task-15 任务书写"「一格目标都没有」的阶段（task-9 的 `stage_exhausted` 路径）要保证 `leftover == 0`"。若 dev-coder 把这个"归零"施加到 `longrun.py:981-989` 的 `stage_exhausted` 上，后果是：①`no_unmet_stages` 恒真 ⇒ 硬失败重新被洗成当天 VERIFIED，task-9 条款①当场作废；②与 task-9 自己的用例 `tests/test_longrun.py:1090-1119`（断言 `stage_exhausted.leftover=1`、reason 含"还剩 1 格"）直接冲突；③`tools/verify-run3.py:163-171` 的 leftover 回退彻底失明（该工具将永远判通过）。
  - **正确落点只有一个**：要归零的是 `longrun.py:976` 的 `stage_no_target`（即"没种子 ⇒ 今天这块地本来就不该动"），实现方式二选一 —— ①把 `_leftover` 的 till/plant 分支也套 `can_plant`（此时 `leftover=0`、`met` 仍 False，`tests/test_longrun.py:1133` 的断言需同步改）；②在 zero-target 分支单独记 `leftover=0`（`_leftover` 语义不动）。**`stage_exhausted` 的 leftover 必须保留 >0**，且 `no_unmet_stages` 必须看得见它（否则 R1 白修）。
  - 附带好处：无论选①还是②，R2 的"距离随机性"（远距离记阶段/近距离 cancel）都被消除，因为两种距离下 zero-target 阶段都是 `leftover=0`。
- **行号漂移（nit）**：task-15 正文引用 `rep.checks` 为 `longrun.py:1293-1300`，实测现在是 `longrun.py:1358-1365`（`no_hard_failures` 在 `longrun.py:1360`）。task-9 之后文件已增长到 1506 行，建议 task-15 任务书改用"函数名 + 现测行号"，避免 dev-coder 照错行号找。
- **任务板写范围冲突（只报不改，按硬规则未动任务板）**：`task-17`（world_stuck 自愈）的 `blockedBy=["task-11"]`、写范围含 `brain/agentfarm/longrun.py` + `tests/test_longrun.py`；`task-15` 的 `blockedBy=["task-7","task-11"]`、写范围同样含 `brain/agentfarm/longrun.py` + `tests/test_longrun.py`。⇒ 当 task-7 与 task-11 都完成后，**task-15 与 task-17 会同时 ready 且同时写 longrun.py**，违反本项目单写者链（现链条是 task-7→task-8→task-11→task-15→task-13→task-14，task-17 不在链上）。建议 Lead 把 task-17 的 `blocked_by` 加到 `[task-11, task-15]`（或把 task-17 排到 task-14 之后）。
- **ready 但无人认领**：`task-5`（卖出/出货路径 IL 取证 → 收成换钱 → 买种子，`docs/_il-sell-path.md`）状态 `pending`/`ready=true`/无 owner。它不在 run3 的硬阻塞链上，但"收成→换钱→买种子→再种"是 3 日连跑后仍要闭环的一环，且 log-analyst 手上还有 task-10，建议 Lead 决定是派人还是显式降级到 run3 之后。

## 7. `tools/verify-run3.py` 负例加固：发现 **两处"缺字段/自述即可永远判通过"** 的洞（run3 最终判据）

我扩了 Lead 的负例素材（生成器 `scratch/_review_neg_gen.py`，产物 `scratch/review-neg-*.jsonl`；只写 scratch/，未改 tools/），三个新账本 + 正例回归实测：

| 账本 | 构造 | 工具实测 | 判断 |
|---|---|---|---|
| `scratch/journal-green.jsonl`（Lead 原正例） | 全字段齐全且真绿 | `problems: []` / `verdict: VERIFIED` / **exit 0** | 正例回归未破 |
| `scratch/review-neg-A-no-verified.jsonl` | 3 天 `ended_by=sleep`+跨日+未浇 0+阶段 leftover 0，但 day_end **完全省略 `verified` 与 `checks` 字段** | `verified: null` ×3 / `problems: []` / **VERIFIED exit 0** | ❌ **字段缺失被当成通过** |
| `scratch/review-neg-B-self-report-green.jsonl` | `checks.no_unmet_stages=true`、`no_hard_failures=true`、`failed_steps=0`，但 `day_end.stages=[{failed:3, leftover:5}]` | `problems: []` / **VERIFIED exit 0** | ❌ **只信自述、不做交叉核对** |
| `scratch/review-neg-C-fallback-ok.jsonl`（对照） | 自述字段 `failed_steps`/`no_unmet_stages` 缺省，阶段记录如实写 leftover=5/failed=3 | 3 条 leftover problem / **needs_review exit 1** | 回退路径对 leftover 有效，但见下 |

逐行定位（`tools/verify-run3.py` 现 289 行）：
- **洞 1（neg-A）**：`verify-run3.py:188` 的连续日判定用 `d["verified"] is not False`，而 `verify-run3.py:158` 只在 `verified is False` 时报错 ⇒ `verified` 键**缺失（None）**时既不算未达标也不报问题，三天直接凑成 `verified_streak_tail: 3`，配合 `verify-run3.py:197` 的 `not problems` 给出 VERIFIED。今日真实 journal 有该字段（§3 已对账），但一旦字段改名/漏写，工具会静默放行 —— 属于我职责里"工具永远判通过"那一类。
- **洞 2（neg-B）**：`verify-run3.py:164-173` 只要读到 `checks.no_unmet_stages` 就**不再**自己算 leftover（`elif unmet is False` 之外完全不看 `stages`），而 `verify-run3.py:153-157` 优先信任 `day_end.failed_steps`。⇒ **task-15 落地后，只要 `no_unmet_stages` 算错或被误写为 true，run3 的最终判据会零 problem 放行**。这正是我在 §6 警告的"task-15 若把 `stage_exhausted` 的 leftover 归零"在验收侧的放大器：执行侧改了账本，验收侧看不见。
- **洞 2b（neg-C 暴露）**：`verify-run3.py:155` 的失败回退 `sum(int(s.get("failed") or 0) for s in d["stages"])` 里的 `d["stages"]` 来自 `verify-run3.py:108` 的 `ev == "stage"` 事件，而 **longrun 从不写 `stage` 事件** ⇒ 该回退**恒等于 0**；`d["stages"]` 为空时 `failed=0`，`failed_steps` 一缺，阶段级硬失败就看不见（neg-C 里 failed=3 未被报出，只是恰好被 leftover 回退兜住）。注意对比 `verify-run3.py:166` 用的是 `(d.get("end") or {}).get("stages")` —— **同一个脚本里两个回退读的是两个不同的容器**，一个对（day_end.stages）一个空（逐行 stage 事件）。
- 建议修法（Lead 的工具，我不改）：①`verified is None` 视为异常并报 problem；②失败数一律从 `day_end.stages` 求和，且与 `failed_steps` 不一致时报 problem；③无论 `no_unmet_stages` 在不在，都自算 leftover 并与它交叉核对（不一致 ⇒ problem）；④`verify-run3.py:108` 的死路径删掉或加注释说明 longrun 不写该事件。

复现命令（pwsh，`$py` = 项目 python）：
`& $py tools\verify-run3.py --journal scratch\review-neg-A-no-verified.jsonl --json` → exit 0 / VERIFIED（应为非 0）
`& $py tools\verify-run3.py --journal scratch\review-neg-B-self-report-green.jsonl --json` → exit 0 / VERIFIED（应为非 0）
`& $py tools\verify-run3.py --journal scratch\review-neg-C-fallback-ok.jsonl --json` → exit 1 / needs_review（对照，符合预期）
`& $py tools\verify-run3.py --journal scratch\journal-green.jsonl --json` → exit 0 / VERIFIED（正例，符合预期）

### 7.1 复核 Lead 修好后的 `verify-run3.py`（现 320 行）：4 个账本按 Lead 口径全部符合 + 我发现 1 条新的残留洞（neg-D）

Lead 的修复（我逐行读过 `verify-run3.py:150-204`）与实测结果一致，我把 5 个账本又独立跑了一遍（命令同上，逐条贴输出）：

| 账本 | 工具实测 | 是否符合 Lead 口径 |
|---|---|---|
| `scratch/journal-green.jsonl` | 无问题 → **VERIFIED exit 0** | ✅ 正例回归未破 |
| `scratch/review-neg-A-no-verified.jsonl` | 3 天各报「day_end 缺 verified 字段（缺失 ≠ 通过）」→ **exit 1** | ✅ 洞 1 已堵（`verify-run3.py:158`） |
| `scratch/review-neg-B-self-report-green.jsonl` | 每天 2 条：「自述 failed_steps=0 与 day_end.stages 求和 3 不一致」「no_unmet_stages=True 与自算不一致（有目标阶段遗留 leftover=5 格）」→ **exit 1** | ✅ 洞 2 已堵（`:180-183`、`:193-197`） |
| `scratch/review-neg-C-fallback-ok.jsonl` | 每天 2 条：「当天 stages 硬失败 3 格」「有阶段遗留目标 leftover=5」→ **exit 1** | ✅ 洞 2b 已堵（`:151/:155/:179` 改为以 `day_end.stages` 求和） |
| `logs/longrun-3day-llm-run2.jsonl`（真机） | sleep_failed / no_hard_failures=false / 硬失败 14 格 / verified=false / sleep 失败 1 次 / leftover=15 / 跨日没有推进 ×1 → **exit 1** | ✅ 与 Lead 报告一致 |

- **残留洞（新，neg-D）**：`scratch/review-neg-D-unmet-but-verified.jsonl`（3 天，`checks.no_unmet_stages=false` 且 `day_end.stages=[{tiles:15,ok:10,failed:0,leftover:5}]`——**自述与阶段记录一致地"没做完"**，但 `day_end.verified=true`、`failed_steps=0`）→ 工具 **零问题 / VERIFIED / exit 0**。原因：`verify-run3.py:193` 只做**一致性**比较（`bool(unmet) != (leftover_targeted == 0)`），而旧版那条无条件的 `elif unmet is False: 问题` 被这次修改删掉了 ⇒ 当 `no_unmet_stages=False` 与自算 leftover **一致**时，脚本不再把它当失败；唯一还能拦住它的是 `verify-run3.py:186` 的 `verified is False`，而这份账本自称 `verified=true`。真实 longrun 里 `rep.verified = all(rep.checks.values())`（`longrun.py:1365`）会连带写成 false、所以今天多半拦得住；但工具存在的意义就是**不信执行者的自述**，且"verified 只取部分 checks"正是 R1 那类 bug 的形态。建议加回一行：`if unmet is False: problems.append(f"[{name}] checks.no_unmet_stages=false（有阶段后置条件未成立）")`，与一致性检查并存。
- Nit：`_tile_count()`（`verify-run3.py:79-87`）对**没有 `tiles` 字段**的历史账本返回 0，于是该阶段落入 `leftover_zero_target` 并报「0 目标阶段 leftover=…」——方向是 fail-safe（宁可误报不放过），但错误信息会误导；run3 的账本每阶段都写 `tiles`（`longrun.py:971`），不受影响。
- `verify-run3.py:119-121` 的 `event=="stage"` 已按约定保留 + 加 legacy 注释；权威口径统一为 `day_end.stages`。
