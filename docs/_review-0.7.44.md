# 0.7.44 对抗验收（deputy-lead / task-12）

> 验收对象：**冻结提交 `37cac51`**（`chore(release): 冻结 0.7.44`，3 文件 33+/4-：`brain/agentfarm/bridge.py`、`mod/AgentFarm.Bridge/manifest.json`、`tools/_note-0744.txt`）。冻结树 = `git archive 37cac51`（700 个追踪文件，提取到 `%TEMP%\t0744_frozen`）。
> 当前 HEAD 写作时 `ac1cea2`（冻结后仅 docs 提交：`docs/00-开发日志.md`、`docs/_release-0.7.44.md`）；`git diff --stat 37cac51 HEAD -- brain tests mod tools` **为空** ⇒ 审查对象与工作树产品代码零差异。
> 四卡：task-4 `b702708`、task-5 `f68de59`、task-6 `d8c723b`、task-11（卡 1b）`088f23a`。作者 dev-coder；本报告全部判据由 deputy-lead 独立实现，不抄作者脚本；变异一律在**副本树**跑（未原地改冻结树/工作树）。
> **一句话结论**：四卡代码面 **PASS-WITH-NITS**（NIT 无阻塞项，见 §6）；但 **0.7.44 现在不能据此放行 A9/B9** —— 真机冒烟门禁未过（2 个游戏日全 `needs_review`、`verified_streak=0`），§7 记录现场并判定为卡 1/1b 的 GAP 扩面（task-15），须 0.7.45 重冒烟后再放行。

---

## §0 判定摘要

| 项 | 读数 |
|---|---|
| 冻结提交 | `37cac51`（3 文件 33+/4-）；冻结树 700 文件 |
| A0 provenance | 700 追踪 / 0 缺失 / 0 blob 不符（6 个 eol 属性展开）；A0b 关键文件 `git hash-object` 4/4 |
| 版本载体 | manifest `0.7.44`；`bridge.py:39 MOD_VERSION_EXPECTED="0.7.44"` |
| 四卡判定 | task-4 **PASS**、task-5 **PASS**、task-6 **PASS**、task-11（1b）**PASS** |
| A 段（provenance/范围/口径） | **16 PASS / 4 INFO / 0 FAIL** |
| B 段（A8 夹具独立重放） | **27 PASS / 9 INFO / 0 FAIL** |
| C 段（对抗判据） | **44 PASS / 0 FAIL**（含 3 条【无法判定】用例） |
| D 段（变异两列） | 作者脚本 **16/16 实测被杀**；我方变异 **10/10 实测被杀**，未杀/异常 0 |
| 单测（冻结树） | 定向 Ran 779 OK；全量 **Ran 1267 OK**（纯 archive 4 红=本地夹具缺失，见 §1/NIT-1）；dotnet build 0 警 0 错；py_compile rc=0 |
| 装机读数（Lead） | check-release 六项全绿、全量 Ran 1277 OK（工作树含 log-analyst 未提交 +10 测试，见 §1） |
| 真机冒烟 | **2 日全 needs_review，verified_streak=0**（§7） |
| 放行结论 | **四卡代码面可放行（PASS-WITH-NITS）；A9/B9 不可放行**（§7 未收口） |

**A9/B9 放行还差什么**：①task-15（`day_justified` 只对当前可执行可达待做格敏感 + 263/217 归属表 + 反向洗白用例）落地；②0.7.45 冻结 + check-release 六项全绿；③真机冒烟 ≥1 天 `verified=true`（这次是 0/2）；④§3 两条死循环离线判据的两列复跑（本报告 B/C 段可直接复用作回归夹具）；⑤A9 判读必须并列 `already`（task-10 #1，见 §6/NIT-5）。

---

## §1 对象、provenance 与读数

### 1.1 provenance（独立复核）

- A0：用 `git ls-tree -r 37cac51` 的 700 条 blob sha1 逐文件对照冻结树 → 缺失 0、不符 0；其中 6 个文件带 eol 属性、按 `git archive` 语义展开（`.ps1/.bat/.cmd` 类），字节级差异只来自 eol。
- A0b：4 个关键文件 `git hash-object` 与提交内 blob 一致 4/4。
- 冻结树与工作树的关系：工作树是 CRLF 检出、冻结树是 LF 归档；**归一化 CRLF 后逐字节相同**（`brain/agentfarm/longrun.py`：worktree 628202B sha256 `1789C862…` vs frozen 618824B sha256 `1BD86757…`，`\r\n→\n` 后相等；`manifest.json` 同理 71491B `77003E0B…` vs 71481B `630D9D4C…`）。blob 级 `git hash-object` 两树同值（longrun `92b440c3…`、manifest `01aef24f…`）。
- 报告内所有「冻结树」读数均来自 `T744_ROOT=%TEMP%\t0744_frozen`；凡比较工作树的地方都注明。

### 1.2 读数表

| 命令 | 读数 |
|---|---|
| `py_compile -W error::SyntaxWarning` | rc=0（A4a） |
| 定向单测（farmwork/longrun/planner） | **Ran 779 tests / OK**（A4b） |
| 冻结树全量 `unittest discover tests` | 纯 archive：Ran 1267 + 4 红（夹具缺失，见 NIT-1）；补入本地 `scratch/_ledger*` 20 个夹具后 **Ran 1267 tests / OK (skipped=12)**（A4c） |
| `dotnet build --no-incremental`（冻结树 mod） | **0 警告 0 错误**（A4d） |
| Lead 装机 `check-release --expect 0.7.44` | 六项全绿；全量 **Ran 1277 / OK** |

**Ran 1267 与 Ran 1277 的差额**：冻结提交树=1267；工作树=1277，差额 +10 来自 log-analyst **未提交**的 `tests/test_analyze_longrun.py`（工作树 +423 行）。两树同口径绿，数字不同属正常，不是产品红。

### 1.3 夹具与证据文件

- A8 真账本 `logs/longrun-runA8-0743.jsonl`：**1322 行**，sha256 `18f224c3f366d377f63fd6938b24ce2a05ffaed11b588829d94a8c89dbb13b60`（B0 实测与常量一致）。
- 证据文件：`scratch/_t0744_c2_final.txt`（A/B/C 终盘）、`scratch/_t0744_author_mut_{t4_resume,t5_encircled,t6_closeout,t11_resume_close}.txt`（作者脚本副本跑原文）、`scratch/_t0744_c2_my_mut.txt`（我方 10 条变异）、`scratch/_t0744_c2_smoke.txt`（§7 冒烟账本读数）。
- 探针：`scratch/_t0744_probe.py`（A~E 段）；变异：`scratch/_t0744_mutate.py`（CASES 10 条，`--base` 冻结树副本）；§7 取证：`scratch/_t0744_smoke_read.py`。

---

## §2 A 段：provenance + 范围 + 口径

### 2.1 版本与事件名

- A1/A1b：manifest `version=0.7.44`、`bridge.py MOD_VERSION_EXPECTED="0.7.44"`，与装机读数一致。
- A2：既有 journal 事件名 **removed=[]**（一个都没删）；**新增 journal 事件名 = 0**（卡 1/1b 复用 `plot_exhausted`/`resume_exhausted`/`no_progress_burst` 既有名，B 案，符合「先不新增」口径）。A2c/A2h2/h3/h4：卡 4/5/6/11 源码标记全部命中（`plot_exhausted`、`resume_exhausted`、`exhausted=True`、`switched=`、`_dead_tile_set`、`leftover_executable`、`leftover_blocked`、`MAX_ALLOC_NO_PROGRESS = 3`、`alloc_no_progress`、`slept_ok`、`_slept_by_us`、`deferred_by_budget_suppressed`、`budget_defer_events`、`_flush_budget_deferrals`、`_guard_leftover_resume`、`_dead_end_pending`、`where="guard_leftover"`）。

### 2.2 语义键与 checks 10 键（未动）

- A2d：阶段记录 36 键、`day_end` 47 键基线**语义键未删**（removed=[]）。
- A2e 新增阶段键（**单列，只作 info**）：`leftover_executable`、`leftover_blocked`、`leftover_blocked_tiles`、`alloc_capped_tiles`。冻结树注释明确：`leftover`/`assigned_undone`/`no_unmet_stages` 一个字不动，分拆只作 info。
- A2f 新增 `day_end` 键（**单列，只作 info**）：`slept_ok`、`plot_pending_executable`、`plot_pending_blocked`（后两者之和恒等于 `plot_pending`，checks/豁免/`no_unmet_stages` 一个字不看）。
- A2g/A2h5：`rep.checks` 字面键集（AST 取 `Assign(target=Attribute(attr="checks"))`）在 0.7.43 与 0.7.44 均恰为 **10 键且顺序一致**（`slept_by_us, no_blocking_modal, no_hard_failures, unreachable_within_bound, refused_within_bound, no_unmet_stages, crops_watered, watered_outdoor, day_justified, zero_action_evidenced`）。新字段没有污染 checks。
- `git diff 5679562 37cac51 -- brain/agentfarm/longrun.py` 复核：**checks 内唯一语义改动**是 `"slept_by_us": rep.ended_by in ("sleep","inventory_blocked")` → `"slept_by_us": self._slept_by_us(rep)`；`no_unmet_stages` 公式与护栏 B `cleared_tiles` 语义**未动**（新增注释反复声明“绝不拿分拆放宽判据，诚实优先”）。

### 2.3 四卡改法覆盖

| 卡 | 需求（release §1） | 实现（冻结树行号） | 独立证据 | 判定 |
|---|---|---|---|---|
| task-4 `b702708` | 冬 7/12/18 不再 `stuck:回片区（work_spot_resume）`；换片/前沿清一格/`resume_exhausted` 三档；不改语义键与 checks 10 键；≥4 单测 + ≥2 变异 | `_resume_switch_or_exhaust` 3918；换片 avoid_area；frontier 观测清一格；`resume_exhausted:` 4019；burst 路由 8648-8651 | B1 修前红 3/3；B6a/b/c 三档全绿；A2e/A2f 新键未入 checks；A2h5 10 键；作者变异 4/4；单测 Ran 7 | **PASS** |
| task-5 `f68de59` | 挡死格不进下一轮分配；leftover 拆「可执行余格 vs 物理挡死格」；同格当天重分有界留痕；不放宽 `no_unmet_stages`/护栏 B；≥5 单测 + ≥2 变异；A8 冬 9/14 离线复现 | `MAX_ALLOC_NO_PROGRESS=3` 244；`_dead_tile_set` 4835；`_dead_end_pending` 4849；`_stage_tiles` 剔除 encircled 4565-4566；`_work_spot_plot` 收尾作业区剔死格 3785-3788；阶段拆分 7053-7057 + 记录 7325-7327；重分有界 7058-7084；日终 `plot_pending_executable/blocked` 8826-8831 | B2 修前红 2/2；B7a~B7e 全绿；C5 14 条全绿；作者变异 5/5；A2e 4 新键；单测 Ran 5 | **PASS** |
| task-6 `d8c723b` | `checks.slept_by_us` 取真值；「只因预算延后」与「户外浇水达标」不同真；≥4 单测 + ≥2 变异 | `_do_sleep` 里 `if st.ok: rep.slept_ok=True` 6380-6386；`_slept_by_us` 6389-6398；`_flush_budget_deferrals` 3421-3450（浇水达标则整批压制、只累 `deferred_by_budget_suppressed`） | B3 修前红；B8a/b/b2/c 全绿（A8 12 天同真独立复算=12）；C6 10 条；作者变异 4/4；单测 Ran 6 | **PASS** |
| task-11 `088f23a` | GAP-1（`_review_only_fallback`）/GAP-2（`guard_leftover`）两入口统一走换片或诚实收工，不再落 `stuck:回片区` | `_review_only_fallback` 4918-5009（dead-only ⇒ `_resume_switch_or_exhaust(where="review_only_fallback")`）；`_guard_leftover_resume` 5029-5079（dead-only ⇒ `where="guard_leftover"`）；boss 8648-8651；复用 3918；无新事件名 | B6e 动态重放两入口均不落 `_no_progress_stop`；B10/B10b 全绿；C9 3 条；作者变异 3/3；单测 Ran 5 | **PASS** |

### 2.4 越界扫描

四卡改动面 = `brain/agentfarm/longrun.py` + `tests/test_longrun.py` + 作者变异/复现脚本（`tests/_mutate_*`、`tests/_repro_t5_encircled.py`）；冻结提交只碰 3 个版本文件。**无 mod/bridge 生产代码改动**（dll 与 0.7.43 同哈希），无 `tools/` 生产改动，无 `docs/` 之外的越界文件。

---

## §3 B 段：A8 真账本独立重放

夹具：`logs/longrun-runA8-0743.jsonl`（1322 行、sha256 见 §1.3）。B 段全部判据由本探针重新解析账本得出，不复用作者 `verify-run3`/`analyze-longrun` 的实现。

### 3.1 修前红（冻结树之前形态，A8 账本当夹具）

| 编号 | 现象（独立复算） | 期望 |
|---|---|---|
| B1 | 冬 7/12/18：同日 `plot_exhausted` burst 计数=5；`resume_walk`=6/4/4 次；`ok_steps`=46/13/19；理由文本含“跨片地待做” ⇒ 3/3 天是 `stuck:回片区（work_spot_resume）` 形态 | 修后不许再落该形态 |
| B2 | 冬 9：1 格 `incomplete` 归属的阶段记录 **28** 条；冬 14：**62** 条；`encircled_tiles=[(37,35)]`；`ended_by=stuck` ⇒ 2/2 天 | 修后挡死格不进下轮分配 |
| B3 | 冬 9/14：`sleep.ok=true` 但 `checks.slept_by_us=false`，`day_after` 已次日 ⇒ 旧口径假象 2/2 | 修后取真值 |
| B4 | analyzer 的「预算延后 vs 浇水达标」警告行 = `[33,150,254,527,542,563]`，与独立复算的 12 天同真完全一致（analyzer 只显示前 6 行是 `[:6]` 截断） | 退化检测 6/6 精确匹配 |

### 3.2 修后行为（冻结树独立重放）

- **B5（作者离线复现，形状验证）**：`tests/_repro_t5_encircled.py` rc=0；修前 `b702708`：Ran 5，failures=3 errors=2，红的用例 = `test_leftover_is_split_into_executable_and_blocked`/`test_same_tile_reallocation_is_bounded_and_journalled`/`test_day_with_only_encircled_leftover_ends_honestly`/`test_plot_has_work_ignores_encircled_tiles`/`test_stage_tiles_excludes_encircled_tiles`；HEAD 绿（Ran 5 红 0）⇒「修前红 / 修后绿 —— 离线复现成立」。*注：这是作者脚本的自报形状，独立修前红由 B1/B2 补强，不是只信脚本。*
- **B6a 换片**：无产出回片区 ⇒ 换到别的片区（`avoid_area` 生效）。
- **B6b 前沿清一格**：观测里真正清掉一格（`cleared_tiles` 非空）才允许收工。
- **B6c `resume_exhausted`**：`ended_reason` 前缀为 `resume_exhausted:`，`day_justified=false` / `verified=false` 不被当达标。
- **B6d encircled**：`encircled_day` 的格不作为可执行回片区目标。
- **B6e GAP-1/GAP-2 收口**：动态 monkeypatch 两个入口后均不走 `_no_progress_stop`（`review_only_fallback` 仍写 `stuck` 的路径=False；`guard_leftover` 段内不再出现 `_no_progress_stop`、含 `_resume_switch_or_exhaust=True`）；A8 账本 review 事件=0。
- **B6f A8 路由**：A8 三日 `no_progress_burst.source` 全 = `回片区（work_spot_resume）`。
- **B7a~B7e（卡 5 独立重放）**：`_dead_tile_set()={(37,35),(40,30)}` 且 (37,35) 不在 `blocked`；`_dead_end_pending()==[(37,35)]`；`water_area` 目标池排除被围格、保留可执行格；真浇水阶段记录 `leftover=1 / leftover_executable=0 / leftover_blocked=1 / leftover_blocked_tiles=[[37,35]]`，清单⊆dead 集；连续 3 次「分配了但零产出」后：`blocked` 事件 `{action:"stage_realloc", tile:[60,13], alloc_no_progress:3, limit:3, no_effect:false}` 落账、格进 `blocked`、第 4 次阶段分配=0；收尾作业区对只剩死格的片返回 None。**限量=3、不是新豁免额度**。
- **B8a~B8c（卡 6 独立重放）**：`_slept_by_us` 三态 `[True,False,True]`（`slept_ok=True+stuck`⇒真、`slept_ok=False+stuck`⇒假、`ended_by=sleep`⇒真）；`_flush_budget_deferrals(watered_outdoor=True)` 返回 0、一条 `deferred_by_budget` 事件不落、`deferred_by_budget_suppressed=2`、`deferred_by_budget=False`；反向未达标 ⇒ 返回 1、事件落账；A8 12 天「预算延后+浇水达标+dry=0」同真独立复算=**12/12**。
- **B9（task-10 #1）**：A8 全部 `day_end.stages[]`=**172** 条，`ok==0 且 already>0` 的阶段数=**0**（A8 无“只靠 already 撑账”的阶段）；`already` 步总数=**50**。B9b：`tools/verify-run3.py:1104 _ok_self += int(_s.get("ok") or 0)`、:1122 只单列 `ok`，**未并列 already** ⇒ A9 判定必须额外读 `stages[].already`/`attempted_ok`（见 NIT-5）。
- **B10/B10b（卡 1b 两入口动态路由）**：review 入口 ret=`(None,False)` 且 `_resume_switch_or_exhaust` 收到 `where=["review_only_fallback"]`；guard 入口 ret=`('ended',False)` 且 `where=["guard_leftover"]`；两者均不落 `stuck`、不调用 `_no_progress_stop`。

**B 段合计：27 PASS / 9 INFO / 0 FAIL**（INFO 是修前形态确认与工具口径提示，不是产品失败）。

---

## §4 C 段：对抗判据（重点防洗白）

44 条全部 PASS（判红/判绿/【无法判定】三态都按设计动作；其中 3 条断言“字段缺失 ⇒ 【无法判定】”）。

| 组 | 条数 | 覆盖的洗白形态 | 代表用例（全部 PASS） |
|---|---|---|---|
| C4（卡 4 换片/exhausted） | 12 | 换片不看 avoid_area、`resume_exhausted` 被当达标、burst 无限换片、清一格假证据、`stuck` 洗成 `no_work`、`verified` 与 `day_justified` 脱钩 | J1a 换片到别的区；J3a/3b `resume_exhausted` 不 VERIFIED；J6a-c 前沿清一格证据；J7a `day_justified` 白名单 |
| C5（卡 5 挡死格/拆分/有界） | 14 | 挡死清单混入可执行格；拆分分母造假（exec+blocked≠leftover）；字段缺失当 0；`limit` 抬高成新豁免；未到 3 次就封；封后又被分配；重分无界 | C5-8 清单⊆dead 且与 `cleared_tiles` 不冲突；C5-9 exec+blocked==leftover；C5-10 字段缺失 ⇒【无法判定】；C5-11 limit≠3 判红；C5-12 n<3 判红；C5-13 第 4 次重新分配判红 |
| C6（卡 6 睡/浇水） | 10 | 伪造入睡证据（无 sleep.ok 却 slept_by_us=true）；真睡成却报 false；伪造浇水达标（`watered_outdoor=true` 且 `final_water.dry>0`）；预算延后与浇水达标同真；`dry` 缺失 | C6-5/C6-7 伪造入睡判红；C6-6 真睡报 false 判红；C6-9 dry 缺失 ⇒【无法判定】；C6-10 可解释（sleep.ok+跨日）判绿 |
| C7（checks 10 键） | 3 | 新字段塞进 checks 污染语义；缺基线键 | C7-1 塞 `slept_ok` 判红；C7-2 恰 10 键判绿；C7-3 缺键 ⇒【无法判定】 |
| C8（`no_unmet_stages`/护栏 B） | 2 | 用分拆字段放宽 unmet；把诚实停当不达标 | C8-1 `assigned_undone>0` 却 `no_unmet_stages=true` 判红；C8-2 诚实停（stamina）判绿 |
| C9（卡 1b 统一路由） | 3 | `resume_exhausted` 且 `verified=true`；两入口 burst 无 source；仍写 `stuck:回片区` | C9-1 判红；C9-2 两入口 source 可解释判绿；C9-3 仍写 stuck 判红 |

**C 段合计：44 PASS / 0 FAIL。** 这些判据可直接复用于 0.7.45/task-15 的回归与反向洗白验证。

---

## §5 D 段：变异两列（自报 vs 实测）

所有变异在**副本树**执行：作者脚本以 `--from-worktree` 在临时副本上改（`git archive` 语义，工作树产品代码 = 冻结树归一化内容）；我方 `scratch/_t0744_mutate.py --base %TEMP%\t0744_frozen` 也是复制后改副本。冻结树与工作树生产文件均未被改动。

### 5.1 作者变异脚本（目标类 = `tests/test_longrun.py`）

| 脚本 / 目标类 | 变异数（自报） | 基线 | 自报杀数 | **实测杀数**（副本跑） | 实测红项（代表性） |
|---|---|---|---|---|---|
| `tests/_mutate_t4_resume.py` / `TestTask4ResumeNoOutput` | 4（docstring 声明“全部杀死”） | Ran 7 OK | 4/4 | **4/4，存活 0** | m1 换区；m2 exhausted 写成 stuck（红 3 条）；m3 把 encircled 当可执行；m4 不清前沿一格 |
| `tests/_mutate_t5_encircled.py` / `TestTask5EncircledRealloc` | 5 | Ran 5 OK | 5/5 | **5/5，存活 0** | m1 被围格进池；m2 收尾作业区忽略死格；m3 `leftover_blocked` 恒 0（红 2）；m4 重分无界；m5 dead-only 路由短路 |
| `tests/_mutate_t6_closeout.py` / `TestTask6CloseoutCaliber` | 4 | Ran 6 OK | 4/4 | **4/4，存活 0** | m1/m2 slept_by_us 退回只看 ended_by；m3 压制逻辑不看浇水证据；m4 反方向一律压制 |
| `tests/_mutate_t11_resume_close.py` / `TestTask11UnifiedResumeClose` | 3 | Ran 5 OK | 3/3 | **3/3，存活 0** | m1 review 触顶不换片；m2 guard 触顶不换片；m3 guard dead-only 不诚实收工 |

「自报」出处诚实说明：四个脚本的 docstring 只声明**变异条数与“全部杀死”的目标**，仓库里没有作者写下的独立“N/N”数字；上表“自报杀数”抄自脚本**运行输出**的结论行，与我的实测一致。证据：`scratch/_t0744_author_mut_*.txt`。

### 5.2 我方独立变异（10 条，冻结树副本跑）

| # | 变异 | 期望被谁杀 | 实测 |
|---|---|---|---|
| a | 换片忽略 `avoid_area` | C4-J1a | **杀 1** |
| b | `resume_exhausted` 写成 `stuck:` | C4-J3a/3b | **杀 1** |
| c | 把 encircled 当可执行 | C4/C5 | **杀 1** |
| d | 停滞格不记 `resume_stall_tiles` | B6/C4 | **杀 2** |
| e | `_work_spot_plot` 不再剔死格（`if dead:`→`if False:`） | B7e / C5 | **杀 1** |
| f | 阶段记录 `leftover_blocked` 恒 0 | B7c2 / C5-9 | **杀 1** |
| g | `_slept_by_us` 退回只看 `ended_by` | B8a / C6-6 | **杀 1** |
| h | `_flush_budget_deferrals` 的 `if watered_outdoor:` 关掉 | B8b / C6 | **杀 1** |
| i | review 兜底 dead-only 分支退回 `stuck` | B10 / C9-3 | **杀 1** |
| j | guard_leftover dead-only 分支退回 `stuck` | B10b / C9-3 | **杀 1** |

**合计：10/10 被杀（累计 11 条次 FAIL），未杀/异常 0。** 锚点核对 `--check-anchors` 10/10 OK。
教训（判据自身 bug，非产品 bug）：i 初版锚点改的是 review **触顶**分支（B10 的 patch 场景走不到），存活 0 杀；改锚到 **dead-only** 分支（冻结树 4966-4973）后被杀。判据 bug 与产品 bug 分开记录。

---

## §6 结论与 NIT 清单

**判定：四卡代码面 PASS-WITH-NITS；0.7.44 作为 A9/B9 门禁 = 不放行（§7）。**

### NIT（单列，均非阻塞四卡代码面判定）

- **NIT-1（夹具未入仓）**：纯 `git archive 37cac51` 跑全量单测是 Ran 1267 + 4 红，全部是本地 `.gitignore` 内的 `scratch/_ledger*` 夹具缺失（3 个 `FileNotFoundError` + `test_json_mode_is_parseable` 的 `AssertionError: 2 != 0`），不是产品红；补入工作树 20 个夹具后 **Ran 1267 OK (skipped=12)**。装机 Ran 1277 = 工作树含 log-analyst 未提交 +10 测试；报告须并列写两个数，禁止混用。
- **NIT-2（作者“自报”无独立出处）**：变异脚本 docstring 只声明条数；本报告“自报”列抄自运行输出。另：脚本默认基线 `git archive HEAD`，队列有新提交时必须显式指定 `--rev`，否则“基线”漂移。
- **NIT-3（B5 只作形状验证）**：作者 repro 的“修前红/修后绿”是脚本自报，独立修前红由 B1/B2 补齐；未做逐 step 重放（时间成本，已在 B 段以账本级重放替代）。
- **NIT-4（坐标清单截断）**：`leftover_blocked_tiles`、`alloc_capped_tiles` 只存**前 12 个**坐标，>12 时账本不完整；审计必须看 `leftover_blocked`/count 与 `blocked` journal 原文。
- **NIT-5（A9 的 already 口径，task-10 #1）**：A8 中 `ok=0 且 already>0` 的阶段=**0**；但 `tools/verify-run3.py` 只累加/单列 `ok`（:1104/:1122），不并列 `already`。**A9 放行时必须读**：`day_end.stages[].already`、`attempted_ok`、以及“`ok=0/cleared=0` 但 already>0”的阶段数，并与 B9 同起点对比；A8/A9 不同起点**不可跨对比较**（A8 起点冬 26，A9 备份 `logs/ab-backup/A9-start/`）。
- **NIT-6（冒烟账本的两个事实层次）**：真机 `day_end.plots[].tiles` 是**计数**（如 25），不是坐标数组；“被截断”在 `location.tilesTruncated=true`（`tiles[]` 400 上限）层，`plots[].note` 转述该标记——不要把 note 当字段。账本里的**累积 pending**（263/217）与**当前可执行面**（`plot_pending=0`）是两个口径，§7 的归属表（task-15）必须分开。
- **NIT-7（阻塞项，task-15）**：§7 的 `day_justified` 口径缺口。它不是四卡代码面缺陷（卡 1/1b 的“拿不出目标”路由本身正确），但它使用户目标「连续 5 日 VERIFIED」在真机不可达 ⇒ 必须在 0.7.45 收口后才能放行 A9/B9。

### 已知限制 / 【无法判定】

- **0 动作日 edge**：需 A9/B9 真机样本，当前【无法判定】（沿用 0.7.43 结论；A8 无 0 动作日）。
- 作者变异“自报杀数”的**独立出处**：仓库无作者书面数字，只能以脚本运行输出为准（已注明）。
- B5 逐 step 重放：未做（账本级重放已覆盖），属方法上限，不判红。
- 本报告未对 `tools/analyze-longrun.py`、`tests/test_analyze_longrun.py` 的未提交在制改动做判定（log-analyst 在制，不属本批）。

---

## §7 真机暴露的未收口形态（2026-10-18 冒烟；事实 + 判断）

> 本节是 0.7.44 冻结后的**真机门禁读数**（Lead 提供背景，我独立读账本/console 复核）。它**不改变** §2~§5 对冻结树四卡代码面的判定；它改变的是「能否据 0.7.44 放行 A9/B9」的结论。
> 冒烟运行：`tools/run-longrun.py --days 1 --size 5 --max-minutes 60 --max-days 2 --journal logs/longrun-smoke-0744.jsonl`；账本 308 行；`logs/longrun-smoke-0744.version.json` 记录 head=`ac1cea2`、dll `806C1069…`、manifest `77003E0B…`，且 `brain/agentfarm/longrun.py` sha256 `1789C862…`（工作树 CRLF 版）；与冻结树 **LF 归一化后逐字节相同**（sha256 `1BD86757…`，blob `92b440c3…` = `37cac51`），即冒烟代码 = 冻结代码（版本载体与 §6 冻结记录一致）。`worktree_clean=false` 只来自他人 `scratch/` 在制，不影响产品文件。

### 7.1 事实（原文行号）

**冬 26（`logs/longrun-smoke-0744.jsonl:240`；console `logs/longrun-smoke-0744.console.log:25/26`）**
- `ended_by=sleep`、`verified=false`；`ended_reason=`**`stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：今天早些时候还有 263 格没做完（跨片地，最近的是 [12, 17]））`**。
- `checks` 唯一 false = `day_justified`；其余 9 项全 true（含 `slept_by_us=true`、`no_unmet_stages=true`）。
- `plot_pending=0`、`plot_pending_by_kind={}`、`assigned_undone=0`、`unreachable=16`。
- `plot_exhausted_burst`（jsonl:233）`count=5, t=362.63`；前 5 条 `plot_exhausted` 在 `t=362.31/362.40/362.47/362.56/362.63`（**约 0.32 秒内 5 次**），每条 `pending=263`、`stalled_total` 120→162→205→230→261。
- `sleep`（jsonl:235）`ok=true`，跨日 winter 26→27、体力 125.4→270。
- `plots` 10 片、每片 `tiles=25`（计数），**每片 note 均含 `location.tilesTruncated=true（tiles[] 只有 400 格上限）`**。

**冬 27（jsonl:306；console:37/38）**
- `ended_by=sleep`、`verified=false`；`ended_reason=`**`resume_exhausted:回片区 217 格都回去看过、换片 4 次，当前观测里没有可执行目标（守卫仍说：今天早些时候还有 217 格没做完（跨片地，最近的是 [38, 36]））`**。
- `checks` 唯一 false = `day_justified`；其余 9 项全 true。
- `plot_pending=0`、`plot_pending_by_kind={clear_area:0}`、`assigned_undone=0`、`unreachable=3`。
- `no_progress_burst`（jsonl:300）`count=1, source="回片区（work_spot_resume）", exhausted=true, pending=217, stalled_tiles=217, newly_stalled=5, encircled_pending=0, switches=4, farm_actions_today=23`，note 原文含「今天按 resume_exhausted 诚实收工：睡下去让游戏日前进，但绝不写 stuck、也绝不判 VERIFIED」。
- `sleep`（jsonl:302）`ok=true`，跨日 27→28、体力 152.5→270。
- `plots` 4 片（25/25/25/20），note 均含同一 `location.tilesTruncated=true` 标记。

**263/217 的来源链**：`plot_exhausted{source="resume_ledger", pending}` 在 jsonl:62/79/94/97/103（263）与 :272/275/288/291（217）；守卫文本模板来自冻结树 `_work_reasons` 4798-4802「今天早些时候还有 {len(pending)} 格没做完（跨片地，最近的是 …）」。即：**守卫的 pending 是当日累积 `leftover_targets` 口径（263/217，含当前观测/可达面之外的格），而当天的 `plot_pending=0`、当前观测没有可执行格**。

### 7.2 判据链（冻结树行号）

- burst 有界停：`_plot_exhausted_burst() >= PLOT_EXHAUSTED_BURST(=5, :307)` 时 `_do_sleep(obs, rep, f"stuck:同一秒连发 {burst} 次换片都没有目标（守卫仍说还有活：{text}）")`（:8665-8676）。它睡成、日推进，但理由前缀是 `stuck:`。
- `day_justified`：`is_justified_end(ended_by, ended_reason)`（:563-572）要求 `ended_by=="sleep"` **且** `ended_reason.split(":",1)[0] ∈ JUSTIFIED_END_REASONS`（:553 = `("night","stamina","no_work")`）。`stuck:` 与 `resume_exhausted:` **都不在白名单** ⇒ 两天 `day_justified=false` ⇒ `verified=false`。
- 卡 1 的 `resume_exhausted` 路径本身按设计工作（冬 27 的 `no_progress_burst.exhausted=true, source=回片区（work_spot_resume）`，没有 `stuck:回片区`），只是它同样过不了 `day_justified`。

### 7.3 独立判断：**是卡 1/1b 的 GAP 扩面**（不是 GAP-1/2 回退）

1. **不是回退**：GAP-1（`_review_only_fallback`）/GAP-2（`guard_leftover`）两入口都走了卡 1/1b 的换片/诚实收工路由，没有 `_no_progress_stop`、没有 `stuck:回片区`；burst 路径 0.32 秒内 5 次即停，不空转；两天都真睡成、日推进、`slept_by_us=true`。卡 1b 的“统一路由”在真机上得到了正例。
2. **是 GAP 扩面（第三个形态）**：卡 1/1b 把“拿不出目标”从 `stuck` 升级为“换片 → `resume_exhausted:` 诚实收工”，但 `day_justified` 的**理由白名单**没有跟上——它只认 `night/stamina/no_work`。于是“**当前观测/可达面没活、但当日累积 pending 还有 263/217 格**”这一形态的收工，只能落到 `stuck:` 或 `resume_exhausted:`，两种都被判不 VERIFIED。卡面写的是「确实没活 ⇒ 诚实收工不 VERIFIED」，而真机形态是「当前没活、账本还有 263/217 格」——判定“确实没活”的口径与账本累积口径不同步，这正是 task-15 要修的 `day_justified` 只对**当前可执行可达**待做格敏感 + 263/217 归属表。
3. **对我此前 GAP-3 裁决的自我修正**：0.7.44 验收时我把 burst 路径判为“有界诚实停、非洗白、可不改”。真机正例证实**有界性成立**（0.32s/5 次即停、随后立即睡成），但**有界 ≠ 可放行**：它停在 `stuck:` 标签上，导致 `day_justified=false`、`verified=false`，A9 目标「连续 5 日 VERIFIED」不可达。因此 GAP-3（burst 写 `stuck:` 标签）必须与 task-15 一并收口：至少要改理由口径（白名单是否接纳新收工形态，或改 `ended_reason` 语义并配反向洗白用例）；burst 的**有界逻辑本身**可保留。
4. **对 task-15 验收的输入（我给 Lead 的建议）**：①`day_justified` 改成只看**当前可执行可达**待做格（不是累积 pending）；②263/217 归属表（逐格/逐区归因：当前可见可执行 / 不可达 / 被围 / 已封 / 观测截断未返回）；③反向洗白用例（伪造“当前没活”必须判红；有真实可执行格时 `day_justified` 必须 false）；④对 burst 写 `stuck:` 给出判定（扩白名单或改 reason 语义），不得放宽 `no_unmet_stages`/护栏 B（§4 的 44 条判据可直接复用）；⑤A9 开跑前后都要看 `verified_streak` 与 `day_justified` 的逐日原文。
5. **0.7.45 回归单列判据（burst 收尾标签，Lead m00889 要求单列）**：允许 burst 路径有界停（本机 0.32 秒内 5 次即停是正例）；但 **①不许再写 `stuck:` 掩盖**（要么改成可审计的诚实收工理由码，要么扩 `day_justified` 白名单并配反向洗白用例）；**②不许因“有界停”而不 VERIFIED**，除非有证据证明当天真有活没干完（真实可执行可达格遗留 / `assigned_undone>0` / 护栏 B 红）。该条是 0.7.45 回归（task-18）必过项。

### 7.4 结论

**0.7.44 不可据此放行 A9/B9**。冻结树四卡代码面仍判 PASS-WITH-NITS（§0-§6），但真机门禁（release §3.4 要求 smoke ≥1 天 `verified=true`）**未过（0/2）**，且暴露的是卡 1/1b “诚实收工”判定的未收口形态（task-15）。放行条件见 §0 末「还差什么」。

### 7.5 补充：真机差异（提交后补记，Lead m00889 第 1 项）

> 除 §7.1 已记的「装机成功、冒烟 2 日失败」外，账本里还有以下差异/事实未被 §7.1 收录，全部有原文行号；不改变结论。

- **实际跑满 2 日，收在 `day_cap`**：argv 是 `--days 1 --max-days 2`；账本 `day_cap`（jsonl:307）`{days:2, max_days:2}`；`finish`（jsonl:308）`code=1, verified_streak=0, actions=156, minutes=8.54, stages_seen=[clear_area, plant_area, till_area], no_unmet_stages=true, unmet_days=[], stuck_flushes=0, cleanup_modal_stuck=false, cleanup_attempts=0`。即 0.7.44 冒烟不是“跑 1 天就崩”，而是**跑满 2 天、每天都有真实动作、每天都不 VERIFIED**。
- **`plots_capped`（jsonl:81）**：`plots_today=10, limit=10`，「已开满 10 片地（上限 10），不再累计新作业区」——这是 263/217「跨片地累积且不再新增作业区」的直接来源之一。
- **日级判定被“最后一轮”遮蔽的风险（与 task-15/17 的归属表直接相关）**：`stage_midway_leftover`（jsonl:238，t=389.74，`clear_area`，`tiles=2, leftover=2, round=39`）与（jsonl:304，t=512.04，`clear_area`，`tiles=12, leftover=220, round=1`）。该事件 note 原文警告：「同一阶段种类当天更早一轮还剩格子、最后一轮 leftover==0 ⇒ 日级判定取最后一轮；若那批格子属于另一片地则存在遮蔽，请人工复核 stage_exhausted」。冬 27 的 `no_unmet_stages=true` 取的正是最后一轮 leftover=0，而第一轮 leftover=220 ⇒ **day 级 unmet 判定存在被“最后一轮”遮蔽的可能**；263/217 归属表必须把 `stage_midway_leftover` 的早轮 leftover 一起算，不能只看 `day_end.plot_pending`。
- **`gaps.json` 挡死格真实存在**：`tree:12 / grass:3 / stone:1 / twig:1`（`reason=blocked_tile`，first/last seen 均 winter 26）——与卡 5 B7「blocked 集真实、不是探针臆造」一致；这些格对应 B7/`_dead_tile_set` 口径。
- **收尾纪律（guardian）**：`logs/longrun-smoke-0744-guardian-state.json`：`brain_dead=true`、`finish` 已出现、`trigger` 理由「脑死 且 finish 已出现」、`stop.executed=true` rc=0、`verify` 游戏进程 0；`bridge.json` 在停止前快照存在（modVersion=0.7.44），停止后已删。真机已按 AGENTS 纪律收尾，无残留进程/桥。
- **version.json 的 `worktree_clean=false`**：只来自他人 `scratch/` 在制；产品文件（longrun.py/manifest/dll）与冻结树 LF 归一化一致（§7 开头已给 sha/blob），不是版本问题。

---

## §8 边界声明

- 角色：deputy-lead，只做独立对抗验收。**只读**生产代码；**只写** `docs/_review-*.md` 与 `scratch/`；未跑游戏/桥、未 deploy、未改任务板、未写 `docs/00-开发日志.md`。
- 所有变异在**副本树**（临时目录）执行，未原地修改冻结树或工作树生产文件；作者脚本 `--from-worktree` 的自检副作用只发生在临时副本。
- 判据全部独立实现（探针 A~E 段 + 本报告的 44 条 C 段判据），不调用作者 `verify-run3`/`analyze-longrun` 作判定依据；`git archive` 冻结树 + `git hash-object` blob 对照保证 provenance。
- 缺失/不可测项一律写【无法判定】，不当 PASS。
- 本次提交文件（按路径 add）：`docs/_review-0.7.44.md`、`scratch/_t0744_probe.py`、`scratch/_t0744_mutate.py`、`scratch/_t0744_smoke_read.py`；未提交工作树中他人的在制改动（`scratch/smoke-0742.py`、`tests/test_analyze_longrun.py`、`tools/analyze-longrun.py` 及未追踪 scratch 文件）。
