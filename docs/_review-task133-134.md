# task-133 / task-134 独立对抗验收报告（deputy-lead，task-135）

对象：`57ef928`（task-133 water_far 补水重试 + 逐格判据）、`903e6a4`（task-134 resume 有界 + leftover 口径拆分）；
外加 Lead 的工具侧 `c6cc654`（`tools/verify-run3.py` +63/−10、`tests/test_verify_run3.py` +64，放行链的一部分、按 Lead 要求纳入对账）。
验收方式：只读生产代码 + 只写 `scratch/`；三棵 `git archive` 快照（head / pre133 / pre134）上亲跑探针 `scratch/_t135_probe.py`，
真 `FarmWorker`/`LongRun`/真 journal 产物喂 `tools/verify-run3.py`。

---

## §0 判定：**PASS-WITH-NITS**（F1/F2 已由 Lead `5b070b4` 修好、我复验通过 ⇒ **0.7.30 可放行**）

初判 FAIL 的两条（F1 工具把"诚实上限"日判红、F2 `assigned_undone` 纯自述）在 Lead 提交
**`5b070b4`**（`tools/verify-run3.py` +60/−?、`tests/test_verify_run3.py` +42/−?，2 文件 +96/−6）后**全部关闭**：

| # | 初判 | 修复 | 我的复验（快照 `scratch/_t135_fix` = `5b070b4`） |
|---|---|---|---|
| **F1** | 工具把诚实上限日判红 | 工具自算逐字镜像脑侧口径：honest（`stamina`／`budget 且 `undone==0`／夜里收尾且 `stopped==""`）阶段的 `assigned_undone` 不进基数，只累 `deferred_tiles` | 探针 `_t135_fix`：`C-tool 同向` 四组 **全 PASS**（旧树 `_t135_head` 同四组 3 红）。CLI 直跑原反例 `scratch/_t135_j/_t135_head_night+stamina_600.jsonl --days 1` ⇒ **rc=0 / VERIFIED / `finish.no_unmet_stages=True` / `unmet_days=[]`**、无 `与自算不一致`（只剩 info"VERIFIED 但只涉及一个阶段 ⇒ 供复核"）；对照 `_t135_head_no_target_600.jsonl --days 1` ⇒ **rc=1 / `no_unmet_stages=False` / `unmet_days=['1年 spring 6日']`**（真硬失败没被放过） |
| **F2** | `assigned_undone` 纯自述 | 新增交叉闸门：`journal stage_shortfall_day.unmet > 账本自算 assigned_undone` ⇒ problem | 探针变体 B（账本 `assigned_undone=0` + 日级落痕 `stage_shortfall_day{unmet:5}` + `checks=True`）⇒ **needs_review**，原文 `[spring 11] 账本 assigned_undone=0 < journal stage_shortfall_day.unmet=5（阶段日记自报少做了这些格，账本却少记 ⇒ 可能被洗白）`；旧工具（`c6cc654`）同输入 **VERIFIED / problems=[]** ⇒ FAIL→PASS 成立 |

**保留 NIT-2（不阻塞放行）**：伪造账本的**变体 A**（只留 **stage 级** `stage_shortfall{undone:5}`、不带日级 `stage_shortfall_day`）在修后**仍 VERIFIED**
（`pre134` 旧口径反而 needs_review）——F2 闸门只认日级落痕。要一并堵住需再读 stage 级落痕，但"取最大值"会引入假红
（同一阶段种类跨轮次：早轮 `stage_shortfall{undone:1}` 在末轮做净后仍留在 journal）⇒ 建议按 `(stage, zone)` 取**最后一条**再比，属 0.7.31 口径加固；
真实脑侧两种落痕都会写，纯自述伪造才需要同时抹掉日级痕迹，故不影响本批放行。

**其余打分（不变）**：task-133 = **PASS**（四条全过）；task-134 脑侧 = **PASS-WITH-NITS**（口径实现/有界性/历史不翻案达标，留 NIT-1）。

**初判时的原文（留档）**：

| # | 结论 | 事实 | 最小复现 |
|---|---|---|---|
| **F1（必修）** | 工具把"诚实上限"日判红 | 脑侧 task-134 口径：`stamina`/夜里收工留下的分配内未完成格记 `deferred_tiles`，**不算 unmet**；`tools/verify-run3.py:901` 读到了 `deferred_tiles` 却在 `:902` **只减** `unreach_exempt + refused_exempt` ⇒ 自算 `effective_unmet=1 > 0` ⇒ 报 `checks.no_unmet_stages=True 与自算不一致（分配内未完成 assigned_undone=1 格…期望 False）`，**同一份输出里还印着**"其中诚实上限延后 9 格 ⇒ 不计 unmet"（自相矛盾） | `scratch/_t135_probe.py::c_tool_reconcile` 的 `night+stamina` 组：`[FAIL] C-tool 同向：night+stamina（脑 no_unmet=True / 工具=needs_review / stage_undone=1 deferred=9）`，journal `scratch/_t135_j/_t135_head_night+stamina_600.jsonl` |
| **F2（必答/建议同批修）** | 工具丢了"journal 少做 vs 账本做净"的交叉核对 | 伪造账本：`stages[].assigned_undone=0` + `checks.no_unmet_stages=true` + journal 里有落痕 ⇒ **新工具 VERIFIED / 旧（pre134）工具 needs_review**（旧口径用 `leftover=5` 抓出来了）。`unreachable`/`refused` 两路都有"自算 + 交叉核对"，只有新增的 `assigned_undone` 是**纯自述** | `scratch/_t135_probe.py::c_tool_forged_journal_shortfall`：`head=VERIFIED problems=[] || pre134=needs_review` |

F1 的影响面 = run 验收：任何**体力收工**（`stopped="stamina"`）或**夜里收工**、且该阶段有分配格没做成的日子，
脑侧 `verified` 可能为真，工具一定判红 ⇒ run9b/run10 这种日子拿不到验收通过（正是 task-134 想消灭的假红）。
F1 修法（Lead 采用）：工具侧逐字镜像 honest 判定；F2 修法（Lead 采用）：`stage_shortfall_day.unmet` 交叉核对。

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
- **修后追加读数（`5b070b4`，Lead 的 F1/F2 修复）**：`git show --stat` = **2 文件 +96/−6**（`tools/verify-run3.py` +60、`tests/test_verify_run3.py` +42）；越界扫描只命中 `tools/verify-run3.py`（声明即如此，`mod/`、`logs/`、`manifest.json`、`bridge.py`、`00-开发日志` 均 0）；快照 `scratch/_t135_fix`（`git archive 5b070b4`），`tools/verify-run3.py` SHA256 前 16 = `A781DE2FD068C3B8`、`tests/test_verify_run3.py` = `262E7518E8992805`；`py_compile -W error::SyntaxWarning` **exit 0**；`tests.test_verify_run3` = **Ran 60 / OK**（Lead 报 60，逐字一致）；全量 = **Ran 776 / OK**（Lead 报 776，一致）；九账本 rc 与 Lead 报的一致（green 0 / run2 1 / run3 1 / run5 1 / run6 1 / run7 0 / run8 1 / run9 1 / run9b 1）。

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

探针纯文本读数（定稿，含后补的 C6）：`scratch/_t135_head_out2.txt`、`scratch/_t135__t135_pre133_out2.txt`、`scratch/_t135__t135_pre134_out2.txt`（head **14/18**、pre133 **10/18**、pre134 **13/18**；head 的 4 条 FAIL = F1 的 3 组 + F2 的 1 条；pre 侧的"FAIL"多是该特性尚不存在的 N/A 项，逐条解释见上表）。
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
| C5 | `stamina` + 少做 ⇒ `deferred_tiles>0` 且不计 unmet | PASS（脑侧）／`_t135_fix` 起工具同向 PASS |
| C6 | 诚实上限（`stamina`）+ `unreachable` 越界（6 格 > bound 5） | PASS：head `unreachable=6/5`、`within_bound=False`、`verified=False`、`ended_by=stuck`（`deferred_tiles=9` 仍只作 info）；pre134/pre133 同构造同样 `within_bound=False/verified=False`（该闸门早于本批次） |
| C-tool 同向 ×4 | 同一账本"工具自算"与"脑侧 checks"必须同向 | `no_target` 全树 PASS；`night+stopped=''`、`night+stamina`、`stamina` 在 `_t135_head`(c6cc654) **FAIL（F1）** ⇒ 在 `_t135_fix`(5b070b4) **全 PASS** |
| C-tool 伪造 A | 账本 `assigned_undone=0` + 只留 **stage 级** `stage_shortfall{undone:5}` | `_t135_fix` 仍 **VERIFIED**（pre134 needs_review）⇒ 记 **NIT-2**（残余、不阻塞） |
| C-tool 伪造 B | 同上 + 日级 `stage_shortfall_day{unmet:5}` | `_t135_head` **FAIL（F2，VERIFIED）** ⇒ `_t135_fix` **PASS（needs_review）**，原文见 §0 |
| C7 | run9b 三天口径 | PASS：三天仍 `False`，历史判决未变 |
| C6-fix（CLI） | 我的 F1 反例直接喂修后工具 | `night+stamina_600.jsonl --days 1` ⇒ **rc=0 / VERIFIED / `no_unmet_stages=True` / `unmet_days=[]`**；`no_target_600.jsonl --days 1` ⇒ **rc=1 / `no_unmet_stages=False` / `unmet_days=['1年 spring 6日']`** |

---

## §5「task-134 的口径变更是否引入新的洗白通道」——单列结论

**脑侧：没有发现"把没做完洗成达标"的通道。**
- 不诚实停名（`no_target`/`world`/`sow_failed`）+ 分配内少做 ⇒ 一律 `no_unmet_stages=False`（C4 三组，探针直测）。
- 唯一"看起来像"的是 C4b：夜里收工 + `stopped=""` + 有格少做 ⇒ `honest` 成立 ⇒ `deferred_tiles` ⇒ 当天 `verified=True`。
  但该形态**在生产不可达**：`stopped` 只在 `budget`/`stamina`/`no_seed`/`need_refill`/某步 `code` 时被 `FarmWorker.run_stage` 写下（`farmwork.py:2830-2861`），
  循环正常跑完时每个分配格都会留下一条 step；`assigned_undone>0` 而 `stopped==""` 只能来自**某格硬失败**（`ok=False` 且非 `skipped`），
  而硬失败一定让 `checks.no_hard_failures=False` ⇒ 当天不可能 `verified`。我的探针用"整格不派活"制造出这种形态，属防御性构造。
  ⇒ 记 **NIT-1**（见 §6），不是通过的洗白通道。
**工具侧**：初判时两条方向相反的偏差（F1 过严、F2 过松）**都已由 `5b070b4` 修掉**：
- F1（过严）⇒ 工具自算逐字镜像脑侧 honest 判定，诚实上限日不再假红（§0 复验表）。
- F2（过松）⇒ 接入 journal `stage_shortfall_day.unmet` 交叉核对，账本少报即 problem。
- **残余 NIT-2**：闸门只认日级落痕，伪造账本若**只留 stage 级** `stage_shortfall`（不带日级事件）仍能 VERIFIED（§0、§6）；
  建议 0.7.31 按 `(stage, zone)` 取最后一条 stage 级落痕再比（避免跨轮次假红）。真实脑侧两种落痕都会写。

---

## §6 NIT 清单

| # | 现象 | 行号/证据 | 阻塞放行？ |
|---|---|---|---|
| F1 | 工具自算不减 `deferred_tiles` ⇒ 诚实上限日被工具判红（同时印着"延后 9 格 ⇒ 不计 unmet"） | `tools/verify-run3.py:901-902`（修前）；`scratch/_t135_probe.py::c_tool_reconcile` `night+stamina` | **已修（`5b070b4`）**，复验 PASS |
| F2 | 工具对 `assigned_undone` 无 journal 交叉核对 ⇒ 账本说做净、journal 说少做 5 格仍 VERIFIED | `tools/verify-run3.py:897-906`（修前）；`::c_tool_forged_journal_shortfall` 变体 B | **已修（`5b070b4`）**，复验 needs_review |
| NIT-1 | 夜里 + `stopped=""` + `assigned_undone>0` 走 `honest` ⇒ 记 `deferred_tiles`；生产不可达（§5），但将来任何"忘了写 `stopped`"的新路径都会静默变成诚实延后 | `longrun.py:4600-4602` | 否（建议 0.7.31 顺手收紧：要求 `stopped in ("", "night")` 且 `assigned_undone==0` 才按 night 算 honest，或新路径一律显式写 `stopped`） |
| NIT-2 | F2 闸门只认日级落痕：伪造账本只留 **stage 级** `stage_shortfall{undone:5}`（不带 `stage_shortfall_day`）仍 VERIFIED | `tools/verify-run3.py`（修后闸门）；`::c_tool_forged_journal_shortfall` 变体 A | 否（0.7.31 加固；真实脑侧两种落痕都写） |
| NIT-3 | 我的探针在 `night` 组里出现"缺跨日证据"（夹具 `sleep` 后 `day_end.final` 仍是睡前快照）——纯夹具现象，不是产品问题 | `scratch/_t135_j/*.jsonl` | 否 |

---

## §7 复跑命令（四树 + run9b + F1/F2 单跑）

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"; $env:PYTHONDONTWRITEBYTECODE="1"
# 三棵开工时的树 + 修后树（`scratch\_t135_fix` = `git archive 5b070b4`；期望 18/18 PASS）
foreach ($t in @("_t135_head","_t135_pre133","_t135_pre134","_t135_fix")) {
  $env:T135_ROOT = "D:\Deepseek Harness Workspace\星露谷游戏自动化\scratch\" + $t
  & $py -W error::SyntaxWarning "scratch\_t135_probe.py" 2>&1 | Out-File -Encoding utf8 ("scratch\_t135_" + $t + "_out.txt")
}
# F1 反例：修后工具必须放行我原来的"夜里/体力收工"账本，且仍判红真硬失败日
& $py "scratch\_t135_fix\tools\verify-run3.py" --journal "scratch\_t135_j\_t135_head_night+stamina_600.jsonl" --days 1   # rc=0
& $py "scratch\_t135_fix\tools\verify-run3.py" --journal "scratch\_t135_j\_t135_head_no_target_600.jsonl"    --days 1   # rc=1
# run9b 三天重放
& $py "tools\verify-run3.py" --journal "logs\longrun-3day-llm-run9b.jsonl" --days 3
```

## §8 结论

- **task-133 = PASS**（四条全过，B 段 FAIL→PASS 有 pre 树原文）。
- **task-134（脑侧）= PASS-WITH-NITS**（口径实现、有界性、历史不翻案都达标）。
- **放行链（工具侧）= 复验 PASS**：`5b070b4` 后 `_t135_fix` 探针 **18/18**，`C-tool 同向` 四组全 PASS、伪造变体 B 转 needs_review、
  `no_target` 组仍红；`tests.test_verify_run3` **Ran 60 / OK**、全量 **Ran 776 / OK**、九账本 rc 与 Lead 报的一致。
- **总结论：PASS-WITH-NITS ⇒ `0.7.30 可放行`**（残余 NIT-1/NIT-2 均不阻塞，建议 0.7.31 顺手收）。
