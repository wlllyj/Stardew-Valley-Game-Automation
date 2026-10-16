# task-133 / task-134 独立对抗验收报告（deputy-lead，task-135）

对象：`57ef928`（task-133 water_far 补水重试 + 逐格判据）、`903e6a4`（task-134 resume 有界 + leftover 口径拆分）；
外加 Lead 的工具侧 `c6cc654`（`tools/verify-run3.py` +63/−10、`tests/test_verify_run3.py` +64，放行链的一部分、按 Lead 要求纳入对账）。
验收方式：只读生产代码 + 只写 `scratch/`；三棵 `git archive` 快照（head / pre133 / pre134）上亲跑探针 `scratch/_t135_probe.py`，
真 `FarmWorker`/`LongRun`/真 journal 产物喂 `tools/verify-run3.py`。

---

## §0 判定：**FAIL**（1 必修 + 1 必答）

两提交的**脑侧**逻辑与卡面要求达标（B 段三处 FAIL→PASS 全部成立、C 段点名要堵的洗白方向都堵住），
但**放行链上的工具侧与脑侧 `checks.no_unmet_stages` 不同向**，且工具侧掉了一条既有交叉核对：

| # | 结论 | 事实 | 最小复现 |
|---|---|---|---|
| **F1（必修）** | 工具把"诚实上限"日判红 | 脑侧 task-134 口径：`stamina`/夜里收工留下的分配内未完成格记 `deferred_tiles`，**不算 unmet**；`tools/verify-run3.py:901` 读到了 `deferred_tiles` 却在 `:902` **只减** `unreach_exempt + refused_exempt` ⇒ 自算 `effective_unmet=1 > 0` ⇒ 报 `checks.no_unmet_stages=True 与自算不一致（分配内未完成 assigned_undone=1 格…期望 False）`，**同一份输出里还印着**"其中诚实上限延后 9 格 ⇒ 不计 unmet"（自相矛盾） | `scratch/_t135_probe.py::c_tool_reconcile` 的 `night+stamina` 组：`[FAIL] C-tool 同向：night+stamina（脑 no_unmet=True / 工具=needs_review / stage_undone=1 deferred=9）`，journal `scratch/_t135_j/_t135_head_nightstamina_600.jsonl` |
| **F2（必答/建议同批修）** | 工具丢了"journal 少做 vs 账本做净"的交叉核对 | 伪造账本：`stages[].assigned_undone=0` + `checks.no_unmet_stages=true` + journal 里有 `stage_shortfall{undone:5}` ⇒ **新工具 VERIFIED / 旧（pre134）工具 needs_review**（旧口径用 `leftover=5` 抓出来了）。`unreachable`/`refused` 两路都有"自算 + 交叉核对"，只有新增的 `assigned_undone` 是**纯自述** | `scratch/_t135_probe.py::c_tool_forged_journal_shortfall`：`head=VERIFIED problems=[] || pre134=needs_review` |

F1 的影响面 = run 验收：任何**体力收工**（`stopped="stamina"`）或**夜里收工**、且该阶段有分配格没做成的日子，
脑侧 `verified` 可能为真，工具一定判红 ⇒ run9b/run10 这种日子拿不到验收通过（正是 task-134 想消灭的假红）。
F1 修法一行：`effective_unmet = max(0, assigned_undone - unreach_exempt - refused_exempt - deferred_tiles)`
（或让脑侧把"诚实上限"阶段的 `stages[].assigned_undone` 直接写 0，两种取其一即可，但必须两侧同口径）。
F2 修法建议：像 unreachable/refused 一样从 journal 自算 `assigned_undone` 并与账本比对（至少"journal 说少做 > 账本说少做"时报问题）。

**其余打分：task-133 = PASS（四条全过）；task-134 脑侧 = PASS-WITH-NITS（口径实现/有界性达标，留 NIT-1）。**

---

## §1 范围与读数（A 段，全部亲跑）

- HEAD `c6cc654`；工作树另有他人 WIP（` M brain/agentfarm/longrun.py`、` M brain/agentfarm/planner.py`，+249/−16）
  ⇒ 一切读数用 `git archive` 干净快照，不采信脏工作树。
- `git show --stat`：`57ef928` = 2 文件（`brain/agentfarm/longrun.py`、`tests/test_longrun.py`，456 ins/23 del）；
  `903e6a4` = 2 文件 +383/−4（longrun 178 / test_longrun 209）；`c6cc654` = `tools/verify-run3.py` +63/−10、`tests/test_verify_run3.py` +64。
- 越界扫描（`^mod/|^tools/|manifest.json|bridge.py|^logs/|00-开发日志`）对**两个被验提交** 0 命中；`c6cc654` 只碰 `tools/`+`tests/`（声明即如此）。
- 快照树：`scratch/_t135_head`（`c6cc654`，397 文件）、`scratch/_t135_pre133`（`57ef928^`=`73c6025`，395）、`scratch/_t135_pre134`（`903e6a4^`=`c5a64fa`，397）。
- 提交内 blob SHA256 前 16：`57ef928:longrun.py 8279d4d635524046`、`57ef928:test_longrun.py c4c021d8f1aa563c`、
  `903e6a4:longrun.py 9933c30e6e69ffc4`、`903e6a4:test_longrun.py dd6170d345532543`、`c6cc654:tools/verify-run3.py eb289fbfe1503382`
  （作者未自报 hash ⇒ 这些是我的读数）。
- `py_compile -W error::SyntaxWarning`（longrun/planner/farmwork/bridge）**exit 0**；
  `tests.test_farmwork tests.test_longrun tests.test_planner` = **Ran 433 / OK**（与 Lead 一致）；
  全量：干净快照（补上 gitignored 夹具后）= **Ran 762 / OK（0 红）**；缺夹具的快照 = 756 ran/9 skipped + 4 条 `test_analyze_longrun` 伪红；
  真实工作树 = 762 ran/2 failures（他人 WIP，不是本对象）。757 vs 762 的差额 = `tests/test_verify_run3.py` 在 `903e6a4` 53 个用例、在 `c6cc654` 58 个（+5）。

---

## §2 逐条对卡

**task-133（四条）**
1. 壶空 ⇒ **先补水再浇、且重试同一格**：PASS。head `B1`：`water_far_refill` 2 条（入口 1 + 走到跟前 `need_refill` 后 1）、`water_far` 1 条 `ok=True/try_=1/retried_after_refill=True`、世界 `watered=True`；
   pre133 同构造：`refill=0`、`water_far` `ok=False/code=need_refill`、世界没浇 ⇒ FAIL→PASS 成立（`FAR_DRY_REFILL_MAX=2`，`longrun.py:131`；`_refill_for_water_far` :1360；`_water_left_obs` :1343）。
2. 逐格证据不许被别格顶替：PASS。head `B2`（`FakeIsland` 只浇别的格、全局 `dryCrops` 2→1）：`water_far ok=False/cause=not_watered/evidence="该格仍在 farm.dryTiles 里（还干着）"`；pre133 同构造 `ok=True`（全局差分）⇒ FAIL→PASS 成立。
3. 补水失败有界 + 文案说"壶里没水"不是"够不着"：PASS。head `C2`（补水自称成功、水位不变）：`refill` 2 次（=上限）、`water_far` 2 条全失败、`far_dry_given_up={(61,10)}`；`_far_dry_give_up_cause_text`(:1054) 的 need_refill 分支文案见作者用例 ③；pre133 同构造 `refills=0/given_up=[]`。
4. `dryTiles` 缺失/被截断不许当成功：PASS。head `C1`：缺字段 ⇒ 无 `water_far` 且留 `water_far_unavailable`；`truncated` ⇒ `ok=False/cause=no_evidence`（原文"该格不在列表里**不算证据**⇒ 无法判定"）。

**task-134（A/B 段）**
- `assigned_undone` = 分配格 −（做成 ∪ 按规跳过）：PASS（`longrun.py:3454`，阶段字段 :3554，`stage_shortfall` :3556-3562）。
- `plot_pending` = 改判据前的 `raw_unmet`（逐 kind `_leftover` 求和）**逐字一致**：PASS。同一构造在 pre134 上工具自算输出 `自算有目标阶段 leftover=9 格`、head 账本 `plot_pending=9` ⇒ 数值一致（`longrun.py:4554-4558`）。
- 诚实上限只记 `deferred_tiles`(info)：PASS（`:4590-4626`，`honest = stamina | (budget & undone==0) | (night_end & stopped=="")`）。
- resume / work_spot / guard_leftover 空转有界：PASS。head `B3`：12 次调用只走到 `calls=5` + `no_progress_burst×1` + `ended_by=stuck` + `leftover_targets` 未被清空；pre134 同构造 `calls=12`、`burst=0`、`ended_by=''`（无界）⇒ FAIL→PASS 成立（`_resume_reevaluate` :2310、`_no_progress_stop` :2331、`PLOT_EXHAUSTED_BURST=5` :101）。
- `_resume_reevaluate` 只清任务级 `no_target`、**不动** `no_target_global`：PASS（`no_target_global` 只在 :794 加入，全仓无 `clear/discard` 命中）。
- 不把 leftover 洗掉（0 动作也不许白睡成达标）：PASS。C4 三组 + C-tool 三组里 `ended_by=stuck` 的日子 `checks.no_unmet_stages=False`、工具同向判红。
- run9b 真账本离线重放（C7）：PASS。head 工具重放 `logs/longrun-3day-llm-run9b.jsonl`：`verdict=needs_review`、`problems=13`、`summer 13/14/15 = False`、`16/17/18 = True`（旧账本无 `assigned_undone` ⇒ 走 leftover 旧口径，历史判决未翻案）。

---

## §3 B 段 pre→post 对照（三树同构探针）

| 用例 | pre133（`73c6025`） | pre134（`c5a64fa`） | head（`c6cc654`） | 结论 |
|---|---|---|---|---|
| B1 壶空补水+重试同格 | FAIL（refill=0、ok=False、没浇） | PASS（refill=2、ok=True） | PASS | task-133 修复生效 |
| B2 别格被浇不算本格证据 | FAIL（ok=True，全局差分） | PASS（ok=False/not_watered） | PASS | 同上 |
| B3 resume 空转有界 | FAIL（12 次仍转） | FAIL（12 次仍转、burst=0） | PASS（5 次 + burst + stuck） | task-134 修复生效 |
| C1 缺/截断 `dryTiles` | PASS（字段不存在） | PASS | PASS | 一致 |
| C2 补水自旋有界 | FAIL（refills=0） | PASS（2 次 + given_up） | PASS | task-133 |
| C3 ok/given_up 互斥 | PASS | PASS | PASS | 一致 |
| C4 `no_target`/`world`/`sow_failed` + 少做 | 字段不存在（N/A） | 红（leftover 口径） | **红（`no_unmet_stages=False`，口径正确）** | 未洗白 |
| C5 `stamina` + 少做 | N/A | 红（leftover 口径） | **绿（`deferred_tiles=9`、`no_unmet_stages=True`）** | 卡面要求的口径变化，但**工具不认（F1）** |
| C7 run9b 三天重放 | false/false/false | 同 | 同 | 历史判决未变 |

探针纯文本读数：`scratch/_t135_head_out.txt`、`scratch/_t135__t135_pre133_out.txt`、`scratch/_t135__t135_pre134_out.txt`（head **13/17**、pre133 9/17、pre134 12/17；head 的 4 条 FAIL = F1 的 3 组 + F2 的 1 条；pre 侧的"FAIL"多是该特性尚不存在的 N/A 项，逐条解释见上表）。
run9b 单独重放：`& $py tools\verify-run3.py --journal logs\longrun-3day-llm-run9b.jsonl --days 3` ⇒ `结论：needs_review`（exit 1），`summer 13/14/15` 三天 `no_unmet_stages=false`。

---

## §4 C 段对抗矩阵（每组：目的 → 结果）

| 组 | 目的 | 结果 |
|---|---|---|
| C1a | 缺 `farm.dryTiles` ⇒ 不许判 ok | PASS：无 `water_far`、有 `water_far_unavailable` |
| C1b | `dryTiles` 被截断（>64）⇒ 不许判 ok | PASS：`ok=False/cause=no_evidence` |
| C1c（=B2） | 坐标/证据来自别格 ⇒ 不许判 ok | PASS：`not_watered` |
| C2 | 补水无界自旋 | PASS：2 次封顶 + 认输 |
| C3 | 同格 `ok` 与 `given_up` 互斥 | PASS：0 条违规 |
| C4 ×3 | `no_target`/`world`/`sow_failed` + `assigned_undone>0` 伪装诚实上限 | PASS：`no_unmet_stages=False`（`assigned_unmet=1`） |
| C4b | 夜里 + `stopped=""` + 少做 | **VERIFIED**（`deferred=9`）⇒ 记 NIT-1；生产不可用（见 §5） |
| C5 | `stamina` + 少做 ⇒ `deferred_tiles>0` 且不计 unmet | PASS（脑侧）／工具 F1 判红 |
| C-tool 同向 ×4 | 同一账本"工具自算"与"脑侧 checks"必须同向 | `no_target` PASS；`night+stopped=''`、`night+stamina`、`stamina` **FAIL（F1）** |
| C-tool 伪造 | journal `stage_shortfall{undone:5}` vs 账本 `assigned_undone=0` | **FAIL（F2）**：head VERIFIED、pre134 needs_review |
| C7 | run9b 三天口径 | PASS：三天仍 `False`，历史判决未变 |

---

## §5「task-134 的口径变更是否引入新的洗白通道」——单列结论

**脑侧：没有发现"把没做完洗成达标"的通道。**
- 不诚实停名（`no_target`/`world`/`sow_failed`）+ 分配内少做 ⇒ 一律 `no_unmet_stages=False`（C4 三组，探针直测）。
- 唯一"看起来像"的是 C4b：夜里收工 + `stopped=""` + 有格少做 ⇒ `honest` 成立 ⇒ `deferred_tiles` ⇒ 当天 `verified=True`。
  但该形态**在生产不可达**：`stopped` 只在 `budget`/`stamina`/`no_seed`/`need_refill`/某步 `code` 时被 `FarmWorker.run_stage` 写下（`farmwork.py:2830-2861`），
  循环正常跑完时每个分配格都会留下一条 step；`assigned_undone>0` 而 `stopped==""` 只能来自**某格硬失败**（`ok=False` 且非 `skipped`），
  而硬失败一定让 `checks.no_hard_failures=False` ⇒ 当天不可能 `verified`。我的探针用"整格不派活"制造出这种形态，属防御性构造。
  ⇒ 记 **NIT-1**（见 §6），不是通过的洗白通道。
**工具侧：有两条方向相反的偏差（F1 过严、F2 过松）**，F2 不是"脑侧洗白"，而是"工具不再独立复核 `assigned_undone`"——
`task-52/63` 那两路豁免都有"自算 + 与账本交叉核对"，新增的 `assigned_undone` 目前**只信账本自述**，与其"不信自述"的既有设计不一致。

---

## §6 NIT 清单

| # | 现象 | 行号/证据 | 阻塞放行？ |
|---|---|---|---|
| F1 | 工具自算不减 `deferred_tiles` ⇒ 诚实上限日被工具判红（同时印着"延后 9 格 ⇒ 不计 unmet"） | `tools/verify-run3.py:901-902`；`scratch/_t135_probe.py::c_tool_reconcile` `night+stamina` | **是（必修）** |
| F2 | 工具对 `assigned_undone` 无 journal 交叉核对 ⇒ 账本说做净、journal 说少做 5 格仍 VERIFIED | `tools/verify-run3.py:897-906`；`::c_tool_forged_journal_shortfall` | 建议同批（单项可留 0.7.31，但需 Lead 拍板） |
| NIT-1 | 夜里 + `stopped=""` + `assigned_undone>0` 走 `honest` ⇒ 记 `deferred_tiles`；生产不可达（§5），但将来任何"忘了写 `stopped`"的新路径都会静默变成诚实延后 | `longrun.py:4600-4602` | 否（建议 0.7.31 顺手收紧：要求 `stopped in ("", "night")` 且 `assigned_undone==0` 才按 night 算 honest，或新路径一律显式写 `stopped`） |
| NIT-2 | 我的探针在 `night` 组里出现"缺跨日证据"（夹具 `sleep` 后 `day_end.final` 仍是睡前快照）——纯夹具现象，不是产品问题 | `scratch/_t135_j/*.jsonl` | 否 |

---

## §7 复跑命令（三树 + run9b）

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"; $env:PYTHONDONTWRITEBYTECODE="1"
foreach ($t in @("_t135_head","_t135_pre133","_t135_pre134")) {
  $env:T135_ROOT = "D:\Deepseek Harness Workspace\星露谷游戏自动化\scratch\" + $t
  & $py -W error::SyntaxWarning "scratch\_t135_probe.py" 2>&1 | Out-File -Encoding utf8 ("scratch\_t135_" + $t + "_out.txt")
}
# 工具单跑（伪造账本/run9b 重放）已含在探针内；单独重放 run9b：
& $py "tools\verify-run3.py" --journal "logs\longrun-3day-llm-run9b.jsonl" --days 3
```

## §8 结论

- **task-133 = PASS**（四条全过，B 段 FAIL→PASS 有 pre 树原文）。
- **task-134（脑侧）= PASS-WITH-NITS**（口径实现、有界性、历史不翻案都达标）。
- **整体 FAIL / 0.7.30 暂不可放行**：F1 是"脑侧 verified 被工具否掉"的整链不同向，必须在放行前修（一行）；F2 同批修最省事。
  放行判据（建议）：改完后用本报告 §7 的 head 探针复跑，`C-tool 同向` 四组全 PASS + `C-tool 伪造` 转为 needs_review，且 `no_target` 组仍红。
