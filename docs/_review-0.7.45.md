# 0.7.45 对抗验收（deputy-lead / task-21）

> 对象：task-15 修复提交 **`e347aaa`**（0.7.44 冒烟 FAIL 的 day_justified / 守卫口径修复）。
> **边界先声明**：0.7.45 **尚未冻结**——版本载体（`mod/AgentFarm.Bridge/manifest.json`、`brain/agentfarm/bridge.py` 的 `MOD_VERSION_EXPECTED`）仍是 **0.7.44**（A1），`docs/_release-0.7.45.md` §2 冻结九步未走、task-16 未落袋。本报告只判定 **task-15 代码内容能否进入 0.7.45**，**不构成 0.7.45 整体放行**。
> 冻结树：`git archive e347aaa --format=tar` → `%TEMP%\t0745_frozen`（737 文件）。作者自报数字一律不采信：下表所有「实测」均在本报告的冻结副本上复跑（证据见 §1.3）。

---

## §0 判定摘要

| 问题 | 回答 |
| --- | --- |
| task-15 代码面能否合并进 0.7.45 | **可以：PASS-WITH-NITS**（判据链成立、冒烟 263/217 独立复算闭合、防洗白通道 22 条判据全过、作者变异 4/4 + 我方变异 5/5 实测被杀） |
| 0.7.45 能否放行**重冒烟** | **不能**：task-16（背包）未落袋、冻结九步未走（版本仍是 0.7.44） |
| 能否放行 **A9/B9** | **不能**：① task-16 + 九步未走 ② `smoke-0745` 真机门禁未跑（要求 ≥1 天 `verified=true` 且 0.7.44 冒烟两个 FAIL 转 PASS） ③ A9 判定必须 already 双列（NIT-5） |
| 差什么 | ① task-16 合并 ② 九步冻结（含 check-release/deploy/preflight） ③ `smoke-0745` ≥1 天 VERIFIED ④ A9 账本 `stages[].already` 并列判读 |

**独立读数（冻结树 e347aaa，本节全部为实测）**

| 项 | 读数 |
| --- | --- |
| provenance | `e347aaa` 追踪 737、缺失 0、不符 0、eol 展开 6；3 个关键文件 blob 3/3 相等（`longrun.py=9af3defc6e22`、`test_longrun.py=a99b67ca3af4`、`_mutate_t15_justified.py=b784e446f35a`） |
| 探针合计 | **PASS=58 / FAIL=0 / SKIP=0 / INFO=8**（A 16P+3I；B 18P；C 22P+1I；D 2P+4I） |
| 单测（冻结树） | 定向 `TestTask15PendingCaliber` **Ran 6 tests / OK**；全量 discover **Ran 1311 tests / OK（skipped=11）**；`py_compile -W error::SyntaxWarning` rc=0 |
| 作者变异 | 4 条 **4/4 实测被杀**（基线 Ran 6 OK；副本跑） |
| 我方变异 | 5 条 **5/5 实测被杀**（probe+单测双判杀器；锚点 5/5 OK；副本跑） |
| Lead 自报全量 1317 | 与冻结树 1311 差 6 —— **【无法判定】**（工作树含未提交测试/夹具；本报告不采信工作树数字） |

---

## §1 对象、provenance、读数与夹具

### 1.1 provenance（独立复核，A 段）

`git ls-tree -r e347aaa` 全量 737 blob → 与解压后的冻结树逐文件自算 sha1（`.ps1/.bat/.cmd` 做 CRLF 归一）比对：**737/737 一致，缺失 0、不符 0**。关键文件 `git hash-object` 对冻结副本 3/3 相等：

| 文件 | 冻结副本 blob = 提交 blob |
| --- | --- |
| `brain/agentfarm/longrun.py` | `9af3defc6e22` |
| `tests/test_longrun.py` | `a99b67ca3af4` |
| `tests/_mutate_t15_justified.py` | `b784e446f35a` |

### 1.2 读数表（A4）

| 项 | 命令（cwd=冻结树） | 读数 |
| --- | --- | --- |
| py_compile | `python -m py_compile brain/agentfarm/longrun.py` | rc=0 |
| 定向 | `python -m unittest tests.test_longrun.TestTask15PendingCaliber` | Ran 6 tests / OK |
| 全量 | `python -m unittest discover -s tests` | **Ran 1311 tests / OK（skipped=11）** |
| dotnet build / C# 自检 | 本卡只改 `brain/`+`tests/`（`e347aaa` 3 文件），`mod/` 零改动 ⇒ 不重复跑 | 【无法判定】→ 由 Lead 冻结九步第 4 步覆盖 |
| check-release / deploy / preflight | Lead 独占（九步未走） | 【无法判定】 |

### 1.3 夹具与证据文件

- 纯 `git archive` **不含** `.gitignore` 内的夹具：首跑全量单测 1 ERROR（`test_analyze_longrun.TestTask17Probes...`，`FileNotFoundError: logs/longrun-runA8-0743.jsonl`）。把工作树 20 个 `scratch/_ledger*` + `logs/longrun-runA8-0743.jsonl` 拷入冻结树 `logs/`、`scratch/` 后全量绿（1311/OK）。夹具只增未追踪文件；A0 provenance 在拷贝前已跑完，不受影响。
- 证据文件：`scratch/_t0745_probe_final.txt`（探针全量输出）、`scratch/_t0745_author_mut.txt`（作者脚本原文输出）、`scratch/_t0745_my_mut.txt`（我方变异矩阵输出）。
- 角色纪律：本报告只读生产代码，只写 `docs/_review-0.7.45.md` + `scratch/`；所有变异都在**冻结树临时副本**里做，冻结树零改动。

### 1.4 本提交的边界

`e347aaa` 自身：**3 files changed, 725 insertions(+), 49 deletions(-)**（`brain/agentfarm/longrun.py` +365/−49、`tests/test_longrun.py` +252、`tests/_mutate_t15_justified.py` +157 新文件）。树上同区间还有 log-analyst 的 task-17 分析器提交（`tools/analyze-longrun.py`、`tests/test_analyze_longrun.py`），**不在 task-15 卡面**；本报告只在 A6 做收录抽查，不对其判定负责。

---

## §2 A 段：范围、口径与 task-15 改法覆盖

### 2.1 版本面

- manifest / bridge 的版本载体 = **0.7.44**（A1，INFO）。task-15 只改 brain/tests，属「未冻结中间树」；任何「0.7.45 已发布/已冻结」的说法在本提交上**【无法判定】**。

### 2.2 checks 10 键与唯一语义改动（硬核对）

对 `37cac51`（0.7.44 冻结）与 `e347aaa` 做 checks 字典块 diff（去注释行）：**只有 `day_justified` 一行变化**：

```
-            "day_justified": is_justified_end(rep.ended_by, rep.ended_reason),
+            "day_justified": is_justified_end(
+                rep.ended_by, rep.ended_reason,
+                pending_executable=rep.pending_executable),
```

其余 9 键（`slept_by_us`/`no_blocking_modal`/`no_hard_failures`/`unreachable_within_bound`/`refused_within_bound`/`no_unmet_stages`/`crops_watered`/`watered_outdoor`/`zero_action_evidenced`）**公式逐字相同**；`no_unmet_stages` 切片、护栏 B「`cleared_tiles`」切片、旧白名单 `JUSTIFIED_END_REASONS = ("night","stamina","no_work")` 均与 0.7.44 相同（A5a/A5b/A5c）。新增字段**只作 info**，不参与 checks/豁免/no_unmet_stages。

### 2.3 新字段 / 事件名（单列）

| 类别 | 结果 |
| --- | --- |
| 新 `DayReport` 字段（7） | `pending_ledger`、`pending_guard`、`pending_stalled`、`pending_executable`、`pending_blocked`、`pending_unobserved`、`stage_midway_leftover`（A3；`removed=[]`） |
| new journal 事件名 | **0**（A3b：`added=[] removed=[]`；`stage_midway_leftover` 复用 task-122 已有事件，只有 day_end 字段是新的） |
| checks 键 | 恰 10 键、键序不变（A2） |

### 2.4 task-15 改法覆盖表（卡面 → 代码锚点 → 实测）

| 卡面要求 | 代码锚点（e347aaa 冻结树行号） | 实测 |
| --- | --- | --- |
| 守卫只对**当前可执行/可达**待做格敏感 | `_pending_work()` `longrun.py:4890` 剔 `resume_stall_tiles`/`encircled_day`；`_ledger_pending()` `:4936` 保留原始账本；`_plot_has_work()` `:3713`（`:3735` 剔停滞） | B2b 冬26 守卫 263→2；B2n 停滞格不算活；B2h 兜底仍用账本口径 |
| 六口径快照 + 不变式 | `_pending_snapshot()` `:4993`；盲区 fail-closed `:5034-5036` | B2a `ledger=280/guard=2/stalled=261/blocked=278/exec=0/unobs=2`；B2f 观测不可用 ⇒ `executable=guard`；C-j1 不变式 |
| `day_justified` 增加**证据门槛** | `HONEST_EXHAUSTED_END_REASONS` `:567`；`is_justified_end()` `:570`，证据分支 `:591 return pending_executable is not None and int(pending_executable) == 0`；`stuck:` 前缀永不认 | B2c 冬26 exec=0 ⇒ True（旧口径 False）；B2e 冬27 ⇒ True；B2g exec=1 ⇒ False；C-a1/a2/b1/b2 |
| burst / 换片上限改**诚实收工**、不写 `stuck:` | `_resume_exhausted()` `:4048`（证据字段 `:4077`）；burst `:8915`、switch_limit `:8923` 都走它 | B2i reason 前缀 `resume_exhausted` 且证据字段齐、exec=1 ⇒ 不 VERIFIED；B2j 代码段无 `stuck:`（注释除外） |
| `sleep_guard` 防「白拿 no_work」 | `:5540-5544`（只剩挡死格 ⇒ `keep_working`） | B2k `kind=keep_working` |
| day_end 并列留痕 + 中途轮 | `:9256-9267`（日终快照落 7 字段）；`:9205-9220`（`stage_midway_leftover` 只 info） | B2l as_dict 7 字段齐；B2m 结构判据；C-g1/g2/g3 |
| checks 10 键不变 | `:9306-9308` | A2g/A2h5；§2.2 diff |

### 2.5 越界扫描

只改 `brain/agentfarm/longrun.py` + `tests/`；未动 `mod/`、桥、`tools/`、游戏侧、任务板。无新增依赖。版本 bump 属 Lead 九步（未走）。

---

## §3 B 段：0.7.44 冒烟账本独立复算 + 0.7.45 重放

### 3.1 263 / 217 / 40 / 17 独立复算（夹具 `logs/longrun-smoke-0744.jsonl` 308 行）

| 项 | 独立读数 | 结论 |
| --- | --- | --- |
| 冬 26 pending | 263 = stalled 261 + 残余 2 | 闭合 |
| 冬 26 阶段窗口 | 某轮 `leftover_executable=211` + `leftover_blocked=12` = 223；**263−223 = 40 格**无坐标/无来源（10 片×25=250 < 263 截断） | 40 格【无法判定】（不猜） |
| 冬 27 pending | 217 = round0 片外累计 220 − 3 挡死格 `[39,31]/[39,32]/[40,32]`（`unreachable_summary`） | 闭合 |
| 挡死 17 格 | `logs/longrun-smoke-0744-gaps.json`：tree 12 / grass 3 / stone 1 / twig 1 = 17 | 闭合 |

### 3.2 0.7.45 重放（独立实现：真实类 + FakeWorld，按最后一张户外观测分类）

| 场景 | 快照/结果 | 判定 |
| --- | --- | --- |
| 冬 26 形态 | `ledger=280, guard=2, stalled=261, blocked=278, executable=0, unobserved=2` | `day_justified=True`（旧口径 False）——2 残余归 unobserved（NIT-1） |
| 冬 27 形态 | `ledger=220, guard=0, stalled=217, blocked=220, executable=0`；`_ledger_pending()=217` | `day_justified=True`（当天确实无当前可执行格） |
| 观测不可用 | `executable=guard=3`，`day_justified=False` | fail-closed 成立 |
| 还剩 1 格可执行 | `executable=1` ⇒ `day_justified=False` | 不洗白真活 |
| 卡 1/5 兜底 | `_pending_work()==[]` 时 `_dead_end_pending()==[(90,90),(91,90)]` | 兜底不是死代码 |
| burst 收尾 | `ended_reason` 前缀 `resume_exhausted`，`no_progress_burst` 带 `pending_ledger/guard/stalled/executable/unobserved`；exec=1 ⇒ 不 VERIFIED | 有界停 + 不洗白 |
| `sleep_guard` | 只剩挡死格 ⇒ `("keep_working", …)` | 不白拿 `no_work` |
| `_plot_has_work` | 水位格基线上班 True；同格加入 `resume_stall_tiles` ⇒ False | 两口径未再混用 |

---

## §4 C 段：对抗通道 a–k（重点防洗白；22 条判据 + 1 INFO 全过）

| 通道 | 注入的洗白/伪造形态 | 判据结果 |
| --- | --- | --- |
| a 证据门槛 | 无证据 / `pending_executable=None` / 有可执行格却认 `day_justified` | C-a1/a2 判红正确（fail-closed + 正数拒绝） |
| b 白名单洗白 | `stuck:` 冒充诚实收工；`no_plot:` 等旧前缀想蹭白名单 | C-b1/b2 判红正确 |
| c 观测盲区 | 观测不可用 ⇒ 声称「没有可执行的活」 | C-c1 判红正确（动态 B2f 复核） |
| d 字段缺失 | 观测里 `tile` 缺 `kind/crop` 单字段 ⇒ 归 unobserved ⇒ exec=0 ⇒ `day_justified` 放行 | **通道成立（C-d1/d2 实测）⇒ NIT-1** |
| e burst 标签 | burst 收尾仍写 `stuck:`；或有活仍 VERIFIED | C-e1/e2 判红正确 |
| f 兜底口径 | `_dead_end_pending` 改用剔除后的守卫口径（兜底变死代码） | C-f1 判红正确（B2h 动态） |
| g 中途轮遮蔽 | 伪造 `leftover=0` 记录进 `stage_midway_leftover`；缺字段 | C-g1/g2/g3 判绿/判红/【无法判定】三态正确 |
| h checks 污染 | 往 checks 塞 `slept_ok` 等新字段；缺键 | C-h1/h2/h3 三态正确 |
| i 放宽会计 | 有未做完阶段却 `no_unmet_stages=True` | C-i1 判红、C-i2 诚实停 stamina 判绿 |
| j 快照造假 | 不变式被破坏 / 伪造 `exec=0` / `day_justified=True` 但 exec>0 / 字段缺失 | C-j1 判绿，j2/j3 判红，j4【无法判定】 |
| k 工具口径 | task-10 #1：「ok=0 & already>0」阶段在 A8 账本为 **0**（stages=172、already 总步数 50；工具 `tools/verify-run3.py:1104/:1122` 只累加/单列 `ok`，不并列 `already`） | **INFO：A9 放行必须并列读 `stages[].already/attempted_ok`，且 A8/A9 不同起点不可跨对比较** |

---

## §5 D 段：变异两列（作者自报 vs 我方实测；全部在冻结树副本跑）

### 5.1 作者 `tests/_mutate_t15_justified.py`（目标类 `TestTask15PendingCaliber`，基线 Ran 6 / OK）

| 变异 | 改法 | 自报 | 实测 |
| --- | --- | --- | --- |
| m1_honest_reasons_emptied | `HONEST_EXHAUSTED_END_REASONS = ("resume_exhausted",)` → `()` | 4/4（脚本 docstring 只声明条数与目标，运行输出自报 4/4） | **KILLED**，红 2：`test_full_day_resume_exhausted_with_zero_executable_is_justified_but_not_verified`、`test_is_justified_end_resume_exhausted_requires_zero_executable` |
| m2_pending_work_counts_stalled | `_pending_work` 不再剔 `resume_stall_tiles` | 同上 | **KILLED**，红 1：`test_ledger_pending_keeps_stalled_guard_does_not` |
| m3_day_justified_no_evidence | `day_justified` 回到单参调用（无 `pending_executable`） | 同上 | **KILLED**，红 1：`test_full_day_resume_exhausted_with_zero_executable_is_justified_but_not_verified` |
| m4_burst_stuck_text | burst 收尾写回 `stuck:` | 同上 | **KILLED**，红 1：`test_burst_close_is_resume_exhausted_not_stuck` |

**实测 4/4 被杀，存活 0**（`scratch/_t0745_author_mut.txt`）。

### 5.2 我方独立变异 `scratch/_t0745_mutate.py`（5 条；锚点 5/5 OK；基线 probe FAIL=0、定向单测 FAIL/ERROR=0）

| 变异 | 改法 | probe 杀 | 单测杀 | 实测 |
| --- | --- | --- | --- | --- |
| m0745a_justified_without_evidence | 证据门槛 `… == 0` → `return True` | 6 | 3 | **KILLED** |
| m0745b_dead_end_back_to_guard_caliber | `_dead_end_pending` 的 `_ledger_pending()` → `_pending_work()` | 2 | 1 | **KILLED** |
| m0745c_blind_fail_open | 观测不可用分支 `exec=guard/unobs=0` → `exec=0/unobs=guard` | 1 | 1 | **KILLED** |
| m0745d_guard_counts_stalled | `_plot_has_work` 不剔 `resume_stall_tiles` | 1 | 0 | **KILLED** |
| m0745e_justified_off_by_one | 证据门槛 `== 0` → `<= 1`（还剩 1 格真活也放行） | 2 | 2 | **KILLED** |

**实测 5/5 被杀，存活/异常 0**（`scratch/_t0745_my_mut.txt`）。机制：复制冻结树 → 文本变异 → 我方 probe B,C 段 + 作者定向单测双判杀器，任一红即 KILLED。

---

## §6 结论、NIT 与放行建议

### 6.1 判定

**task-15 代码面：PASS-WITH-NITS。** 依据：① `day_justified` 的唯一语义改动是**加证据门槛**（其余 9 键逐字相同）；② 0.7.44 冒烟 263/217 两个病灶在真实账本上**独立复算闭合**（263=261+2；217=220−3；40 格如实【无法判定】），重放后冬 26/27 在当前观测面确实 exec=0；③ 有活（exec≥1）或观测不可用（None）时不放行——防洗白方向正确；④ 22 条对抗判据三态全过；⑤ 作者 4/4 + 我方 5/5 变异实测被杀。

### 6.2 放行建议

- **可以**：把 task-15 作为 0.7.45 的一部分继续（等 task-16 落袋、dev-coder 合并后走 Lead 冻结九步）。
- **不可以**：现在放行 `smoke-0745` 重冒烟或 A9/B9——九步未走（版本仍 0.7.44）、task-16 未落袋、真机门禁未跑。
- 重冒烟放行判据（引 `docs/_release-0.7.45.md` §3）：≥1 天 `verified=true`；0.7.44 冒烟步 8.1 由 FAIL 转 PASS；`day_end.pending_executable=0` 时 `day_justified` 必须 true；**再出现 `stuck:` 掩盖 ⇒ 不放行**。
- A9 判定附加：`stages[].already`/`attempted_ok` 与 `ok` 并列读（NIT-5），A8/A9 不同起点不可跨对比较。

### 6.3 NIT（单列；均非阻塞 task-15 代码面判定）

1. **NIT-1（防洗白通道，建议下一批补）**：观测里单格字段缺失（如 `{"tile":[60,10]}` 无 `kind/crop`）会被归为 `unobserved` ⇒ `executable=0` ⇒ `day_justified` 放行（C-d1/d2 实测复现）。建议：缺失字段按 executable/fail-closed 计，或对 `unobserved>0` 加阻断性判据（当前 `pending_unobserved` 只作 info，NIT-4 同根）。
2. **NIT-2（状态，非缺陷）**：0.7.45 版本未 bump、九步未走；本判定只覆盖 `e347aaa` 的代码内容，冻结树 ≠ 已发布 0.7.45。
3. **NIT-3**：`stage_midway_leftover` 字段**无单测直测**（作者 6 条测试都不触该字段）；本报告只有结构判据（B2m）+ 判据侧三态（C-g1~g3）。建议 task-16 批补一条「早轮剩格 > 末轮 0 ⇒ day_end 并列留痕」的单测。
4. **NIT-4**：`pending_unobserved` 只作 info、不做阻断；观测截断（`tilesTruncated`）时它与 NIT-1 同根，日终可能「看起来没活」。
5. **NIT-5（task-10 #1，Lead 要引用的原话）**：`tools/verify-run3.py` 只累加/单列 `ok`（`:1104`/`:1122`），**不并列 `already`**。A9 放行时必须读 `day_end.stages[].already`、`attempted_ok`、以及「`ok=0/cleared=0` 但 `already>0`」的阶段数，并与 B9 同起点对比；A8/A9 不同起点不可跨对比较（A8 起点冬 26，A9 备份 `logs/ab-backup/A9-start/`）。
6. **NIT-6**：Lead 自报工作树全量 1317 vs 冻结树 1311，差 6 —— **【无法判定】**（工作树有未提交测试/夹具；冻结树读数 1311 是本报告唯一采信值）。
7. **NIT-7（跨卡观察，不判 task-15）**：`tools/analyze-longrun.py` 已收录 `stage_midway_leftover`、`pending_executable`，但**未收录 `pending_ledger`**（A6 INFO）；A9 对账表若要用原始账本口径，建议 log-analyst 在 task-17 面补收录。

### 6.4 已知限制 / 【无法判定】

- 0.7.45 未冻结、未装机 ⇒ 无 dll/manifest/check-release/deploy/preflight 读数（Lead 九步覆盖）。
- 真机重冒烟未做；`smoke-0745` 的 VERIFIED、`day_end.pending_executable` 真机分布均在本次判定之外。
- 冬 26 的 **40 格**账本无坐标（10 片×25=250 < 263 截断）⇒ 逐格归属【无法判定】；冬 27 的 217 精确闭合。
- task-16（背包）与 task-20（LLM 输入）不在本报告范围。
- 全量单测依赖未入仓夹具（`.gitignore` 内 `scratch/_ledger*` + A8 账本）；纯 `git archive` 树跑全量会因夹具缺失红 4 条——这是夹具缺失，不是产品红。

---

## §7 边界声明

- 只读生产代码；只写 `docs/_review-0.7.45.md` 与 `scratch/`；未改任务板、未 deploy、未碰游戏/桥。
- 所有变异均在冻结树的**临时副本**里做，冻结树零改动；作者自报数字一律另列，不替代实测。
- 判据用本报告自己的独立实现（`scratch/_t0745_probe.py`），不抄作者脚本；缺失项写【无法判定】，不当 PASS。
- 本判定只对 task-15 代码内容负责；0.7.45 整体放行与 A9/B9 由 Lead 依据九步 + `docs/_smoke-0745.md` 真机证据决定。
