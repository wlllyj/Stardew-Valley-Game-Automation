# task-166：task-163（体力预算延后口径）独立 delta 对抗验收

- **对象**：`3762936` = `0.7.31 task-163: 因体力预算被延后的活不再算「还有活」`
- **验收人**：deputy-lead（只读生产代码，只写本文件与 `scratch/`）
- **判定**：**PASS-WITH-NITS（无必修项）⇒ 0.7.32 可以据此冻结**
- **对照树**：`scratch/_t166_pre` = `3762936^` = `1aaac2b`（task-163 之前）
- **探针**：`scratch/_t166_probe.py`（43 项断言 + 16 条 note，`T166_ROOT` 切树）
- **原始读数**：`scratch/_t166_post_out3.txt`（post，43 PASS / 0 FAIL，exit 0）、`scratch/_t166_pre_out.txt`（pre，24 PASS / 13 FAIL，exit 1）、`scratch/_t166_diag_out.txt`、`scratch/_t166_<树名>.json`

---

## §1 A 段：范围与读数（我亲跑）

| 项 | 读数 |
|---|---|
| HEAD | `3762936` |
| `git show --numstat 3762936` | `brain/agentfarm/longrun.py` **+157/−13**、`tests/test_longrun.py` **+197/−0**（`--stat` 图显示 170/197） |
| 文件数 | 恰 **2** 个（与卡面一致） |
| 越界扫描 `^mod/\|^tools/\|manifest.json\|bridge.py\|^logs/\|00-开发日志` | **0 命中** |
| 工作树 vs 提交 | blob 相同（`longrun.py 84170c42d159`、`test_longrun.py e922475969ac`） |
| SHA256 前 16 | `longrun.py 6005F5E17BAEB050`、`tests/test_longrun.py 117AF2DED7C02F1D`（**与作者自报逐字一致**） |
| `py_compile -W error::SyntaxWarning`（longrun/farmwork/planner/bridge） | **rc=0** |
| 定向 `tests.test_farmwork tests.test_longrun tests.test_planner` | **Ran 499 / OK** |
| 全量 `discover -s tests` | **Ran 869 / FAILED (failures=2)** = `test_analyze_longrun.TestBagSpaceDeadlock::test_mechanical_enumeration_has_no_unmapped_event` + `::TestEventMappingDrift.test_event_buckets_cover_every_brain_journal_name`（**task-165 的 analyzer 收桶，与本批无关**） |

diff 原文留档 `scratch/_t166_diff_longrun.txt`（309 行）、`scratch/_t166_diff_tests.txt`（230 行）。

实现要点（我逐行核对，均与卡面一致）：
- 新状态 `self.budget_deferred_tiles: dict[str, list[tuple[int,int]]]`、`self.capacity_capped_noted: set[str]`（构造 ~`:727-730`，日复位 ~`:4897-4901`）。
- `_note_budget_deferred(task, why, tiles=())`：写 `budget_today["deferred_by_budget"]=True`、`deferred` 追加任务（一次）、把新格并入 `budget_deferred_tiles[task]` 与 `budget_today["deferred_tiles"][task]`；journal `deferred_by_budget{…}` +（有格时）`budget_deferred_tiles{…, note:"…也不参与任何判定扣减（延后≠洗白）"}`。
- `_budget_deferred_tasks()`（只在 `deferred_by_budget` 为真时给出任务集）、`_budget_deferred_tile_set()`（并集）、`_deferred_scan(task, obs)`（clear/till/plant 各自的真实候选格，且都要求 `can_plant`）、`_note_budget_deferrals(obs)`（日初、`stamina_budget` journal 之后调用）、`_note_capacity_capped(task, limit, capacity)`（一天每类一条 + journal `stage_capped_by_capacity`）。
- 守卫收口四处：`_plot_has_work`、`_stage_tiles`（预算闸门改记 `_leftover` 的格）、`_leftover`（首行 `if task in self._budget_deferred_tasks(): return []`）、`work_reasons`（`plant_area` 情形的两条理由加 `not in deferred`）；`_pending_work` 用 `_budget_deferred_tile_set()` 过滤。
- 红线核对：`checks` **一个键都没加**（仍是 task-149 起的 10 键）；`assigned_undone`/`plot_pending`/`deferred_tiles` 口径未改；`harvest`/`clear_dead`/浇水永不被延后。

---

## §2 B 段：三棵树复现（pre `1aaac2b` → post `3762936`）

### B1 超载日（reserve > max、有浇水债、该浇的都浇完）——卡面核心，**FAIL→PASS**

| 读数 | pre | post |
|---|---|---|
| `run()` 退出码 | **1** | **0** |
| `ended_reason` | `stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：farm 口径还有 13 格耕地空着（手上有 20 粒种子）⇒ 该去种；field_se还有地要清/开/种）` | `no_work:确实找不到可做的活（地里的活干完了、也没法/没必要买种子）` |
| `verified` / `day_justified` | `False` / `False` | **`True` / `True`** |
| `plot_exhausted_burst` | **1** | **0** |
| `deferred_by_budget` 条数 | 5（每个候选任务各写一条、**无格子**） | 3（`clear_area`/`till_area`/`plant_area` 各一次） |
| `budget_deferred_tiles` | 0 条（不存在该事件） | 1 条（`plant_area`，`count=2`） |
| `day_end.stamina_budget.deferred_tiles` | `{}` | `{"plant_area": 2}` |
| `watered_outdoor` / `crops_watered` / `no_unmet_stages` | True / True / True | True / True / True |
| `assigned_undone` / `plot_pending` / `deferred_tiles`（顶层） | 0 / 0 / 0 | 0 / 0 / 0 |
| 真实动作 | 12 步浇水 | 12 步浇水 |

⇒ 卡面验收目标达成：**同一世界、同一天，pre 是 `stuck/verified=false`，post 是 `no_work/verified=true`**，且 `ok_steps=12`（不是"什么都没干就绿"）。
证据文件：`scratch/_t166_j/_t166_pre_b1.jsonl`（14 行）、`scratch/_t166_j/星露谷游戏自动化_b1.jsonl`（14 行）。

### B2 有真活没做（1 格活苗浇不上，世界层失败、仍在阶段 tiles 里）——不许变绿

| 读数 | pre | post |
|---|---|---|
| `verified` / `crops_watered` / `watered_outdoor` | False / False / False | **False / False / False** |
| `no_unmet_stages` | False | **False** |
| `assigned_undone` / `plot_pending` | 1 / 1 | 1 / 1 |
| `ended_reason` | `…守卫仍说还有活：有 1 格作物没浇水…` | 同形 |

⇒ 延后口径**没有**把"还有真活"的日子洗绿（这是新口径最该被打的方向，结果是 fail-closed）。

### B3 无浇水债（dry=0）时延后不许生效

| 读数 | pre | post |
|---|---|---|
| `_budget_defer_reason`（clear/till/plant） | 全 `""` | 全 `""` |
| `deferred_by_budget` 事件 | 0 | **0** |
| 真实动作 | 9 步（清障/开垦） | 9 步 |

⇒ 无债不延后，两侧一致；**没有出现"无债也延后少干活"的假延后**（见 §3 C1 的直接断言）。

---

## §3 C 段：七组对抗

| 组 | 期望 | 实测（post） | 判定 |
|---|---|---|---|
| **C1 无债时假延后** | 0 条延后记录 | `deferred=[]`、`budget_deferred_tiles` 前后均为 `{}`（basis=farm、stam=5、reserve=12、live_crops=0、dry=0 ⇒ `debt=False`） | **PASS** |
| **C2 延后清单 vs 守卫/`_pending_work`** | 延后的任务必须让守卫闭嘴、延后格不得出现在 `_pending_work` | `deferred=['clear_area','plant_area','till_area']`；`work_reasons` 里三者在场理由全消失（只剩"12 格没浇水 / 152 格窗口外干作物"）；`_pending_work()==[]`；**反向伪造**（只塞 `budget_deferred_tiles`、不给 `budget_today`）⇒ `_budget_deferred_tile_set()={(62,13)}` 而 `_budget_deferred_tasks()==set()`、守卫照旧抱怨 ⇒ 两套账可被单侧伪造，但**不产生假绿**（守卫仍拦） | **PASS** |
| **C3 延后格是否进了任何扣减** | `assigned_undone`/`plot_pending`/`deferred_tiles` 不被"扣"，只进 info 留痕 | `assigned_undone=0`、`plot_pending=0`、顶层 `deferred_tiles=0`（延后任务**根本没进 stage** ⇒ 属"未分派"而非"被豁免"）；`checks` 键集与 task-149 起的 10 键**完全相等**；journal `{plant_area:2}` 与 `day_end.stamina_budget.deferred_tiles` 逐字一致；**反向验证**：把当天 `budget_today` 清空后守卫立刻重新抱怨 `farm 口径还有 13 格耕地空着…` ⇒ 守卫沉默确实来自延后留痕（非空转） | **PASS** |
| **C4 浇水/收获/清死苗永不被延后** | 四类 `_budget_defer_reason` 全空；端到端里 harvest/clear_dead 照跑 | 直接调用：`water_area/water_far/harvest/clear_dead` 全 `""`；`deferred` 不含它们；端到端 `stages=['harvest','clear_dead','water_area']` 且 `ok_steps=8` | **PASS** |
| **C5 容量命中留痕 vs 实际上限** | journal 与 `_stage_tiles` 实际限一致 | `capacity=11 < 12` ⇒ `stage_capped_by_capacity{task:plant_area, limit:12, capacity:11}` **恰 1 条**；`day_end.stamina_budget.capped_by_capacity["plant_area"]=={"limit":12,"capacity":11}`；真跑 `plant_area` 各轮 `assigned=[3,1,6]` 全部 ≤ 11 | **PASS** |
| **C6 有界性（不许新型同秒空转）** | 修复日无 burst、`stuck_flush` 0 | post：`plot_exhausted_burst=0`、`no_progress_burst=0`、`stuck_flush*=0`、`days=1`；**对照组**（post 树上把 `_budget_deferred_tasks` 打成空集 ⇒ 复刻 pre 语义）⇒ `burst=1`、`code=1`、`verified=False` ⇒ 修复本身（而不是"循环没跑"）把这一天变绿，且旧形态**仍有界**（pre 同样 burst=1、单日收尾） | **PASS** |
| **C7 没有 farm 证据时不许绿** | 必须 fail-closed | `farm=None`（`farm_evidence_unavailable` 入账）⇒ `verified=False`、`code=1`、理由 `…farm 证据不可用…`；即便当天记了 `deferred_by_budget`/`budget_deferred_tiles` 也不绿 | **PASS** |
| **C8 工具侧审计（我自选第七组）** | 真实延后日工具应接受；工具能否识破"抹掉延后留痕" | `tools/verify-run3.py --journal …/…_b1.jsonl --days 1` ⇒ **rc=0 / VERIFIED**；把 `deferred_by_budget`/`budget_deferred_tiles` 事件与快照里的 `deferred_by_budget`/`deferred_tiles` 全部抹掉后再跑 ⇒ **仍 rc=0 / VERIFIED** ⇒ 工具**不核**延后留痕（见 NIT-1） | **PASS（并据此记 NIT-1）** |

---

## §4 NIT 表（均不阻塞冻结）

| 编号 | 现象 | 证据/行号 | 是否阻塞 | 建议 |
|---|---|---|---|---|
| **NIT-1** | 工具侧对延后口径**完全盲**：`deferred_by_budget`/`budget_deferred_tiles`/`day_end.stamina_budget.deferred_tiles` 没有任何核对；把一个真实绿日的延后留痕全部抹掉，`tools/verify-run3.py` 仍给 `rc=0 / VERIFIED`（C8）。属既有"账本自述信任"类（与 B1/B4/B10 同族），**不是新洗白通道**（脑侧要延后必须有预算依据，`_budget_defer_reason` 有债务+体力双条件） | `scratch/_t166_j/星露谷游戏自动化_b1.jsonl` vs `…_b1_stripped.jsonl`；`tools/verify-run3.py` 3b 段 | 否 | 0.7.33 可考虑：`no_unmet_stages=true` 且 `plot_pending==0` 的绿日，若 `stamina_budget.deferred_by_budget=true` 则要求 journal 有对应 `deferred_by_budget`（缺 ⇒ info 或 problem，由 Lead 定口径）；或直接把延后计数纳入工具 info |
| **NIT-2** | **同名不同义**：`day_end.deferred_tiles`（task-134，诚实上限延后的**格数**）与 `day_end.stamina_budget.deferred_tiles`（task-163，按任务的**格数映射**）同名；本日 B1 里前者 0、后者 `{plant_area:2}`，工具读的是前者 | `longrun.py` `as_dict()` 的 `deferred_tiles` vs `stamina_budget` 内层 | 否 | 0.7.33 改名（如 `deferred_tiles_by_task`）或至少在 3b 段注释写清两个字段的来源差异 |
| **INFO-1** | **farm 级理由 vs plot 级目标**：B3 世界（25 格农场、10 杂草、20 空耕地、体力 200、无预算债）里，清障/开垦做完 9 步后守卫仍说 `farm 口径还有 11 格耕地空着（手上有 11 粒种子）⇒ 该去种`，而当天作业区拿不出播种目标 ⇒ `plot_exhausted_burst` ⇒ `stuck`、`verified=false`。**fail-closed、有界**，不是洗白通道；夹具里"换片"是瞬移（同一秒 5 次）才触发 burst，真机走路要数秒 | `scratch/_t166_diag_out.txt`（`farm_plot_work=(25,20,20)`、`deferred_scan(plant_area)` 9 格、守卫原文）；`scratch/_t166_out3` B3 段 | 否 | run A 观察项③：若真机出现同类 `plot_exhausted_burst` 日，考虑让"farm 级耕地理由"在作业区无目标时先走 `work_spot_resume`（找有空地的片区）而不是直接 burst 收 stuck |
| **INFO-2** | pre 树每个候选任务每次调用都会写一条 `deferred_by_budget`（B1 里 5 条、无格子），post 合并为"每任务一次 + 有格子时另写 `budget_deferred_tiles`" ⇒ 日志更干净、可核对 | pre/post B1 段读数 | 否 | 无需动作（记录口径演进） |

---

## §5 结论：0.7.32 能不能据此冻结

**能。** task-163 达成卡面验收目标：

1. **被预算卡住但该做的都做了的一天能绿**：B1 从 pre 的 `stuck/verified=false/code=1`（守卫明知预算不够还抱怨"13 格耕地空着"，5 次同秒换片后收 stuck）变成 post 的 `no_work/verified=true/code=0`，同时真实浇水 12 步、`watered_outdoor=true`、`no_unmet_stages=true`。
2. **"还有真活没做"的一天不许变绿**：B2（1 格浇不上）post 仍 `verified=false`、`crops_watered=false`、`assigned_undone=1`。
3. **无债不延后**：B3/C1 两侧一致 0 条延后记录；无"假延后少干活"。
4. **不是新洗白通道**：`checks` 未加键（仍 10 键）；延后格不进任何扣减（属"未分派"）；延后同时进 journal 与 `day_end` 快照两处；抹掉延后留痕后工具仍盲（NIT-1，既有 ledger-trust 类，非本卡引入）；无 farm 证据时仍 fail-closed（C7）。
5. **有界**：修复日无 burst/无 `stuck_flush`；对照组（复刻 pre 语义）仍是有界单日收 stuck。

NIT-1/NIT-2 与两条 INFO 均**不阻塞**冻结；建议 run A 顺带观察 INFO-1 形态与 `stage_capped_by_capacity` 是否在真机出现。

---

## §6 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$repo = "D:\Deepseek Harness Workspace\星露谷游戏自动化"
Set-Location $repo; $env:PYTHONUTF8 = "1"; $env:PYTHONPATH = "$repo\brain"

# post（工作树 = 3762936）
Remove-Item Env:\T166_ROOT -ErrorAction SilentlyContinue
& $py -W error::SyntaxWarning scratch\_t166_probe.py

# pre（task-163 之前）
if (!(Test-Path scratch\_t166_pre)) {
  git archive --format=tar -o scratch\_t166_pre.tar 1aaac2b
  New-Item -ItemType Directory -Force scratch\_t166_pre | Out-Null
  Set-Location scratch\_t166_pre; tar -xf ..\_t166_pre.tar; Set-Location $repo
  Remove-Item scratch\_t166_pre.tar -Force
}
$env:T166_ROOT = "$repo\scratch\_t166_pre"
& $py -W error::SyntaxWarning scratch\_t166_probe.py

# 工具侧对照（真实延后日 vs 抹掉留痕）
& $py tools\verify-run3.py --journal scratch\_t166_j\星露谷游戏自动化_b1.jsonl --days 1
& $py tools\verify-run3.py --journal scratch\_t166_j\星露谷游戏自动化_b1_stripped.jsonl --days 1
```

## §7 越界与纪律

- 只写 `docs/_review-task163.md` 与 `scratch/`（探针 + 输出 + `_t166_j/` 账本 + `_t166_pre/` 快照树）。
- 未改任何生产代码（`brain/`、`mod/`、`tools/`、`tests/` 全未动）；未跑游戏、未用桥、未 bump、未装机。
- 已知环境噪声：pwsh 把 unittest 的 stderr 记成 `[exit code: 1]`（非失败）。
