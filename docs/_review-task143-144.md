# task-145 独立对抗验收：task-143 + task-144（0.7.31）

**对象**：`task-143 = da5f81b`（plant_area 分配额按手上种子数收窄 + `_preconditions` 归还改动后观测）
+ `task-144 = 2438cae`（阶段内壶空先补水、把这一批原样重跑；`stopped` 不许留空）
**验收人**：deputy-lead（独立对抗，只读生产代码，写盘仅本文件 + `scratch/`）
**判定**：**task-143 PASS / task-144 PASS-WITH-NITS（NIT 为既有缺口，不属于这两张卡）**
**0.7.31 可否放行冻结**：**可以放行**（两条 run9c 形态均已 FAIL→PASS；口径不变量 5/6/7 有实现证据；NIT-1 建议另立卡、不阻塞本版）

---

## §1 A 段：范围与读数（我亲跑）

| 项 | 读数 |
|---|---|
| HEAD 开工时 | `2438cae`（= task-144 提交本身） |
| `git show --stat da5f81b` | 恰 2 文件 +193/−20：`brain/agentfarm/longrun.py` +85、`tests/test_longrun.py` +128 |
| `git show --stat 2438cae` | 恰 2 文件 +315/−4：`longrun.py` +78、`tests/test_longrun.py` +241 |
| 越界扫描（`^mod/\|^tools/\|manifest.json\|bridge.py\|^logs/\|00-开发日志`） | **0 命中**（两提交） |
| SHA256 前 16 | `brain/agentfarm/longrun.py 7FCFAEBA43A6EC68`（341392 B）、`tests/test_longrun.py 4C04CA18DFC5E7AA`（407007 B）；未改：`farmwork.py 4A39BC11ABCA3413`（153108 B） |
| `py_compile -W error::SyntaxWarning`（longrun/farmwork/planner/bridge） | **exit 0** |
| 定向 `tests.test_farmwork tests.test_longrun tests.test_planner` | **Ran 449 / OK** |
| 全量 `discover -s tests` | **Ran 805 / OK（0 红）** |

读数原文：`scratch/_t145_targeted.txt`、`scratch/_t145_full.txt`。

**仓库异常两条（已报 Lead，已闭环，不影响被验对象）**

1. Lead 派工信里的 `task-143 = 353e0a3` **不存在**（`git cat-file -t` ⇒ `fatal: Not a valid object name`）；真实提交 = `da5f81b`（本报告以 `da5f81b` 为准）。
2. 我的 task-146 提交 `eaf136f` 曾被 reflog 里的 reset 链丢弃（`16361a6 HEAD@{1}: reset: moving to HEAD~2`）；Lead 已按工作树内容恢复为 `b56360e`（`docs/_review-run9c.md` + 3 个 `scratch/_t146_*.py`），我未再动索引。
3. Lead 的工具侧同批改动 `36c13dd`（`tools/verify-run3.py` + `tests/test_verify_run3.py`，`tests.test_verify_run3` 64 OK）与判据不变量 `a46e5cf`（`docs/_run6-criteria.md` 的"在场证据"）**不属于本卡被验对象**，我按"工具侧同批、非本卡写盘范围"记录。

---

## §2 B 段：run9c 两条形态 FAIL→PASS（三棵树对照）

三棵树用 `git archive` 冻结（`scratch/_t145_pre143` = `da5f81b^`、`_t145_pre144` = `2438cae^`、`_t145_post` = `2438cae`），探针 `scratch/_t145_probe.py` 以 `T145_ROOT` 切树，同一脚本同一世界。

| 检查 | pre143（两卡之前） | pre144（只有 task-143） | post（143+144） |
|---|---|---|---|
| **B1** plant 分配额 ≤ 手上种子数（12 格空地 + 11 粒） | **FAIL** `pool=12 assigned=12 ok=11 undone=1 leftover=0 stopped='no_seed'` | PASS `pool=11 assigned=11 ok=11 undone=0` | PASS `pool=11 assigned=11 ok=11 undone=0 crops=11` |
| **B2** 壶空⇒补水续做（壶 25、30 格待浇、有补水点） | **FAIL** `refills=0 assigned=30 ok=25 undone=5 stopped='need_refill' unwatered=5` | **FAIL** 同左 | PASS `refills=1 retry_ev=1 assigned=30 ok=30 undone=0 unwatered=0` |
| **B2b** 窗口漂移下补水原样重跑 | **FAIL** `assigned=21 ok=19 undone=2 leftover=5 stopped='' \"\"+undone 阶段=1` | **FAIL** 同左 | PASS `assigned=18 ok=18 undone=0 leftover=5 stopped='' \"\"+undone=0` |

* **B1 就是 run9c day1 形态 ①**的逐字复现（`plant_area assigned 12 ok 11 undone 1 stopped 'no_seed'`，且 `_stage_tiles` 池 12 > 手上 11 粒）。
* **B2 判据设计**：`per_stage_tiles=12` 让前两轮撞 `budget`、第三轮才 `need_refill` ⇒ task-144 之前的 `attempts <= 2` 这时已经失效（attempts=3）⇒ 不补水、`stopped='need_refill'`、`undone=5`；修后改用独立的 `stage_refills` 计数 ⇒ 补水 1 次 + `forced` 原样重跑 5 格 ⇒ 全部浇完。
* **B2b 是 run9c day1 形态 ②**（`assigned 21 undone 3 stopped ''`）的机制复现：`RadiusWorld`（观测恒以玩家为中心，无 `MyopicWorld.revealed` 逃逸口）+ `WalkingWorker`（每格动作前走到格边 ⇒ 观测窗口漂移）。pre 树复算窗口就把 2 格漂丢了（`stopped=''` + `undone=2`），修后靠 `forced` 原样重跑 + `stage_stop_named` 收口 ⇒ `undone=0`。

**结论**：两条形态都拿到 FAIL→PASS 原文，且修复点与作者自述一致（`:2248-2257` 的 `limit=min(limit, seeds)`；`:3577-3610` 的 `stage_refills`/`refill_resume`/`forced`；`:3611+` 的 `stage_stop_named`）。

---

## §3 C 段：对抗矩阵（6 组，全部真代码 / 真 `LongRun`）

| 组 | 构造 | post 实测 | 判定 |
|---|---|---|---|
| **C1** seeds 谎报 0 | 种子叠改名"麦种"（不在 `SEED_NAME_HINTS`）+ `money=0` | 脑侧 `seeds=0 can_plant=False pool=0`；**而假世界的 `plant()` 其实可行** | **PASS（记 INFO-1：既有边界）** |
| **C2** 上限掩盖真没种完 | 20 粒种子 + 12 格空地，4 格 sow 恒 `failed` | `assigned=12 ok=8 failed=4 undone=4 stopped='incomplete'` | **PASS**（未洗成 0） |
| **C3** 壶空且**无**补水点 | `water_left=2`、6 格待浇、`refill_can` 恒失败 | `assigned=6 ok=2 undone=4 stopped='need_refill'` | **PASS**（如实 unmet，不算诚实上限） |
| **C4a** 补水回执说谎 | `refill_can` 回 `ok=True` 但世界没补上 | `calls=2 undone=4 stopped='need_refill'` | **PASS**（≤2 次、有界、不洗白） |
| **C4b** 补水抛 Python 异常 | 桩 `refill_can` 抛 `RuntimeError` | 异常穿出 `_step_stage`（三棵树同形） | **INFO-2**（桩形态；生产只捕 `BridgeError`，见 C4c） |
| **C4c** **真实** `FarmWorker.refill_can` 遇桥异常 | 真 `FarmWorker` + `observe` 抛 `BridgeError(bridge_down)` | `BridgeError` 穿出 `refill_can`（**pre143/pre144/post 三棵树完全同形**） | **FAIL-既有缺口（非本卡引入）⇒ NIT-1** |
| **C5a** `_stage_undone_cause` 四类归因 | `need_refill`/`unreachable`/`no_seed`/`failed` | 四类逐条正确 | **PASS**（pre 树 `AttributeError`） |
| **C5b** `stopped==""` ∧ `assigned_undone>0` 不许共存 | 三形态世界（sow 真失败 / 壶空无补水点 / 夜里失败） | 三形态 0 例；pre144 树 2 例 | **PASS**（本卡收口的核心不变量） |
| **C6** 两卡交叉：种子用尽 + 壶空同一天 | `seeds=3` + `water_left=2` 无补水点，整天 `run.run()` | `rc=1 no_unmet_stages=False assigned_undone=3 deferred=0` | **PASS**（两处都没洗成 0） |

**"新洗白通道"专项结论**：**未发现**。
* task-143 的收窄只把 `assigned` 降到资源以内 ⇒ 方向只会让 `assigned_undone` 更诚实；`C2` 证明"种子够但真种不完"照旧 `undone>0`。
* task-144 的 `forced` 原样重跑与 `stage_stop_named` 只补"如实命名"，`C3/C4a/C4c` 证明补水不成时 `stopped=need_refill` + `undone>0` 仍计入 unmet；夜里诚实上限只多认 `""`/`incomplete`（C5b 三形态里夜里失败也只在 `stopped` 被命名后才算 deferred）。
* 参考：改动把 `_stage_tiles` 的 `plant_area` 分支与 `_preconditions` 返回值改了，`C1/C6` 覆盖了这两处的外部输入面。

---

## §4 逐条对卡

**task-143（`da5f81b`）**

1. `plant_area` 分配额 ≤ 手上种子数（`longrun.py:2248-2257`）—— ✅ B1（pre143 FAIL→post PASS）。
2. `_preconditions` 改"归还改动后观测"（`:2934`/`:2958`）—— ✅ 代码逐行核对：`_preconditions_apply` 用 `changed` 汇总卖出/买入是否动过世界，`_run_day` 调用点改为 `obs = self._preconditions(obs, rep)`；作者用例 `test_same_round_buy_is_visible_to_the_intent_verifier` 覆盖"买到种子当轮可见"。
3. 不许把 `no_seed` 塞进诚实上限白名单 —— ✅ 注释明写反方向禁止，且 C 段 C2/C5b 实证 `stopped='no_seed'`/`''` 都会走 unmet（pre 树 `stopped=''` 反而被 C5b 抓到）。
4. 判定不变差：`py_compile` 0 / 定向 449 OK / 全量 805 OK 0 红 —— ✅。

**task-144（`2438cae`）**

1. `STAGE_REFILL_MAX = 2` + 日级 `max_refills_per_day` 兜底（`:140`/`:3577-3578`）—— ✅ B2（refills=1）+ C4a（说谎回执也只试 2 次）。
2. 补水成功后 `forced` 原样重跑这一批（journal `refill_retry`，新字段 `stage_refills`/`stage_limit`）—— ✅ B2/B2b；`refill_retry` 事件带 `stage_refills=1`、`stage_limit=2`。
3. 补水不成/到上限 ⇒ 如实 `stopped='need_refill'` + `assigned_undone` 计 unmet —— ✅ C3/C4a/C6（`no_unmet_stages=False`）。
4. `stage_stop_named` 收口 `stopped=='' ∧ assigned_undone>0`（`_stage_undone_cause` 四类）—— ✅ C2（post `stopped='incomplete'`、pre144 `''`）+ C5a/C5b。
5. 日终诚实上限只多认"夜里 + `stopped ∈ ("","incomplete")`"（`:4792+`）—— ✅ C5b 三形态（夜里失败在命名后仍 `assigned_undone=0`/`deferred>0`，属刻意设计边界，与作者用例 `test_night_end_keeps_deferred_not_unmet` 一致）。
6. 判定不变差 —— ✅ 同上。

---

## §5 NIT / INFO 表

| 编号 | 现象（行号） | 是否阻塞 0.7.31 | 建议 |
|---|---|---|---|
| **NIT-1** | `FarmWorker.refill_can`（`farmwork.py:2360`/`:2387`）里的 `self.snap()` 无 try；`_step_stage` 的 refill 分支裸调 `self.worker.refill_can()`（post `longrun.py:3580`、pre `:3504`/`:3544`）；`_run_stage_intent`→`_run_day`→`run()`（`longrun.py:5211`）三处都没有 `BridgeError` 兜底 ⇒ 桥抖动会把整轮长跑**带栈打掉**，而不是 graceful `ended_by="bridge_down"` + exit 2 | **否**（三棵树同形，pre-exist，不是这两张卡引入；与 task-108 记的 `_water_far_dry` 逃逸同类） | 单独立卡：把阶段执行与 refill 包一层 `BridgeError` ⇒ 记 `stage_bridge_down` + `ended_by="bridge_down"`；顺带把 `_step_stage` 的首个 `_snap()` 一并纳入 |
| **INFO-1** | `_seed_outlook`/`seed_items` 按**名字**认种子（`SEED_NAME_HINTS=("seed","seeds","种子")`）⇒ 名字认不出时 `plant_area` 静默 0 目标、当天仍可能 VERIFIED（C1：世界其实能种） | 否（既有边界，非本卡引入） | 归 localization 类后续卡（与 farm 字段同一类"自述口径"边界） |
| **INFO-2** | 桩里塞 Python 异常会穿出（生产的 `refill_can` 只捕 `BridgeError`） | 否 | 并入 NIT-1 |
| **INFO-3** | pre 树 `stopped=''` + `undone>0` 是既有洞（C2/C5b 的 pre 侧原文），本卡已收口 | 否 | 已修，留档 |

---

## §6 复跑命令

```powershell
$py = 'C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$repo = 'D:\Deepseek Harness Workspace\星露谷游戏自动化'
# 三棵树已冻结在 scratch/；重建：
#   git archive --format=tar -o scratch\t.tar da5f81b^  ; tar -xf scratch\t.tar -C scratch\_t145_pre143
$env:PYTHONUTF8 = '1'                     # 必须：否则中文输出会撞 cp1252
foreach ($t in @('post','pre144','pre143')) {
  $env:T145_ROOT = Join-Path $repo "scratch\_t145_$t"
  & $py -W error::SyntaxWarning (Join-Path $repo 'scratch\_t145_probe.py')
}
```

原文读数：`scratch/_t145_post_out.txt`（10/11）、`scratch/_t145_pre144_out.txt`（6/11）、`scratch/_t145_pre143_out.txt`（5/11）。

---

## §7 结论

* **task-143：PASS** —— B1（run9c 形态 ①）FAIL→PASS，`assigned ≤ 种子数` 成立，反方向（把资源缺口洗成 deferred）没有出现。
* **task-144：PASS-WITH-NITS** —— B2/B2b（run9c 形态 ②）FAIL→PASS；`stage_refills` 有界（≤2，说谎回执也只试 2 次）；`stage_stop_named` 把 `stopped==""` 与 `assigned_undone>0` 的不变量钉死；日终诚实上限边界与作者用例一致。唯一 NIT 是**既有**的桥异常逃逸（三树同形），不影响本版判定。
* **0.7.31 能否放行冻结：可以**。建议把 NIT-1 单独立卡（0.7.31 之后），INFO-1 归 localization 类后续卡。
