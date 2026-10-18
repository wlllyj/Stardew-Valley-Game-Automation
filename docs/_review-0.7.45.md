# 0.7.45 对抗验收（deputy-lead / task-23）

> 对象：0.7.45 **冻结提交 `2feb1f8`**（`chore(release): 冻结 0.7.45（诚实收工判据/背包满留痕/残缺 tile fail-closed）`）。
> 合并回归三张卡：task-15 `e347aaa`（day_justified 诚实收工判据）、task-16 `3a5d24c`（背包空格口径/清障掉落留痕/满包先腾格）、task-22 `55add69`（残缺 tile fail-closed，堵 task-21 NIT-1）。
> 冻结树：`git archive 2feb1f8` → `%TEMP%\t0745b_frozen2`（**744 文件**，Python `tarfile` 解包，中文名正常）。作者自报数字一律不采信：所有「实测」均在本报告的冻结副本上复跑（证据见 §1.3）。
> 当前仓库 HEAD=`80488c8`（docs/analyzer 后续提交；`git diff 2feb1f8 HEAD -- brain tests mod tools` 只剩 `tests/test_analyze_longrun.py`+`tools/analyze-longrun.py` 的 task-24 分析器改动，**产品代码树与冻结树一致**）。

---

## §0 判定摘要

| 问题 | 回答 |
| --- | --- |
| task-15 + task-16 + task-22 合并代码面 | **PASS-WITH-NITS**：判据链、背包链路、malformed fail-closed 三块均成立；作者脚本可执行的 **10/12** 条变异实测被杀（t15 另 2 条锚点过期未执行，见 §5.1）；我方 11 条独立变异 **11/11 实测被杀** |
| 0.7.45 能否放行 **smoke-0745 重冒烟** | **可以放行**：冻结树 provenance 744/744、版本载体 0.7.45、定向 Ran 19 OK、全量 **Ran 1324 / OK**、py_compile rc=0、malformed 一票否决在所有白名单之前；0.7.44 冒烟两个 FAIL 形态在账本重放中已转 PASS（B2a2/B2b2） |
| 能否放行 **A9/B9** | **不能仅凭本报告放行**：代码面/离线判据已绿，但硬门禁未过——`smoke-0745` 真机 ≥1 天 `verified=true` 未跑；0.7.44 两种 `day_justified=false` 形态须在真机账本上实际转 true；A9 账本必须 already 双列（NIT-4） |
| 差什么 | ① `smoke-0745` 真机 ≥1 天 VERIFIED（0.7.44 两个 FAIL 转 PASS） ② A9 判定并列读 `stages[].already/attempted_ok` ③ NIT-1/NIT-2 两条测试补强（不阻塞重冒烟） |

**独立读数（冻结树 2feb1f8，本节全部为实测）**

| 项 | 读数 |
| --- | --- |
| provenance | `2feb1f8` 追踪 **744**、缺失 **0**、不符 **0**、eol 展开 6；8 个关键文件 `git hash-object` **8/8 相等** |
| 探针合计 | **PASS=91 / FAIL=0 / SKIP=0 / INFO=4**（A 17P+1I；A4 3P；B 30P+2I；C 39P；D 2P+1I） |
| 单测（冻结树） | 定向三卡 `Ran 19 tests / OK`；全量 discover **Ran 1324 tests / OK（skipped=11）**；`py_compile -W error::SyntaxWarning` rc=0 |
| 作者变异 | t16 **5/5**、t22 **3/3** 实测被杀；t15 **2/2 已跑被杀 + m3/m4 锚点随 task-22 过期未执行**（脚本原文 RC=2） |
| 我方变异 | **11/11 实测被杀，未杀/异常 0**（probe+单测双判杀器；锚点 11/11 OK；副本跑） |
| Lead 自报全量 1330 | 与冻结树 1324 差 6 —— **【无法判定】**（冻结树无 task-24 未入树测试；差额解释不充分，不采信 1330） |

---

## §1 对象、provenance、读数与夹具

### 1.1 provenance（A 段，独立复核）

`git ls-tree -r 2feb1f8` 全量 744 blob → 与解压后的冻结树逐文件自算 sha1（`.ps1/.bat/.cmd` CRLF 归一）比对：**744/744 一致，缺失 0、不符 0，eol 展开 6**。关键文件 `git hash-object` 对冻结副本 **8/8 相等**：`brain/agentfarm/longrun.py`、`brain/agentfarm/farmwork.py`、`brain/agentfarm/bridge.py`、`tests/test_longrun.py`、`tests/_mutate_t15_justified.py`、`tests/_mutate_t16_inventory.py`、`tests/_mutate_t22_malformed.py`、`mod/AgentFarm.Bridge/manifest.json`。

### 1.2 读数表（A4）

| 项 | 命令（cwd=冻结树） | 读数 |
| --- | --- | --- |
| py_compile | `python -W error::SyntaxWarning -m py_compile brain/agentfarm/longrun.py brain/agentfarm/farmwork.py` | rc=0 |
| 定向 | `unittest TestTask15PendingCaliber + TestTask16InventoryFull + TestTask22MalformedTiles` | Ran 19 tests / OK |
| 全量 | `python -m unittest discover -s tests` | **Ran 1324 tests / OK（skipped=11）** |
| dotnet build / C# 自检 | 本批 `dll 806C1069…` 与 0.7.44 逐字节相同（Mod 无代码变更），冻结九步第 4 步已由 Lead 覆盖 | 【无法判定】（本树未重跑 build） |
| check-release / deploy / preflight | Lead 独占（冻结九步已走，Lead 读数六项全绿/Ran 1330 OK） | 不重复判 |

### 1.3 夹具与证据文件

- 纯 `git archive` **不含** `.gitignore` 内夹具；本次在跑 A0 provenance **之后**把工作树 20 个 `scratch/_ledger*` + `logs/longrun-runA8-0743.jsonl` + `logs/longrun-smoke-0744.jsonl` + `logs/longrun-smoke-0744-gaps.json` 拷入冻结树，全量单测才绿（否则 `test_analyze_longrun` 因缺 A8 账本红）。
- 证据文件：`scratch/_t0745b_probe_final.txt`（探针全量输出）、`scratch/_t0745b_author_mut.txt`（作者三脚本原文输出）、`scratch/_t0745b_my_mut.txt`（我方 11 条变异输出）。
- 角色纪律：只读生产代码，只写 `docs/_review-0.7.45.md` + `scratch/`；所有变异都在**冻结树临时副本**里做，冻结树零改动。

### 1.4 本提交的边界

`2feb1f8` 自身 **3 files / 31+/5-**（`bridge.py` +27、`manifest.json`、`tools/_note-0745.txt`）。被验三卡：task-15 `e347aaa` **3 files / 725+/49-**；task-16 `3a5d24c` **4 files / 826+/23-**（farmwork.py +60、longrun.py +328、`_mutate_t16_inventory.py` 新、test_longrun.py +288）；task-22 `55add69` **3 files / 291+/16-**（longrun.py +67、`_mutate_t22_malformed.py` 新、test_longrun.py +88）。树上另有 log-analyst 的 task-17/task-24 分析器改动（`tools/analyze-longrun.py`、`tests/test_analyze_longrun.py`），**不在三卡卡面**，本报告不对其判定负责。

---

## §2 A 段：范围、口径与三卡改法覆盖

### 2.1 版本与 checks 硬核对

- `bridge.py` `MOD_VERSION_EXPECTED="0.7.45"`、`manifest.json` `Version=0.7.45`（A1/A1b）。
- checks **恰 10 键、键序不变**（A2/C-c）：`slept_by_us,no_blocking_modal,no_hard_failures,unreachable_within_bound,refused_within_bound,no_unmet_stages,crops_watered,watered_outdoor,day_justified,zero_action_evidenced`；`rep.verified = all(rep.checks.values())` 未动。
- `no_unmet_stages` 公式、护栏 B「`cleared_tiles`」切片、旧白名单 `JUSTIFIED_END_REASONS=("night","stamina","no_work")` 与 0.7.44 **逐字相同**（A5a/b/c）；新字段只作 info。
- **无新 journal 事件名**（A4 `added=[]`）：`slot_relief`、`no_progress_burst`、`stage_midway_leftover` 均复用旧名。

### 2.2 malformed 一票否决顺序（本批最硬的一条）

`is_justified_end()` 体内顺序（A6 实测位置递增）：`malformed=1154` → `ended_by=1208` → `justified 白名单=1311` → `honest 白名单=1371` ⇒ **malformed 否决在一切白名单之前**；C-a 去 docstring/注释后复核 `if int(malformed_tiles) > 0`（@183）先于 `if prefix in JUSTIFIED_END_REASONS`（@340）。`_pending_snapshot()` 对「tiles[] 里出现但既无 crop、无 kind、也不在 tillable」的记录单独 `malformed += 1` 且不归 unobserved（B2e/B2e4）；整张观测缺失时 `executable=len(guard_tiles)`、`malformed=0`（fail-closed，B2d）。

### 2.3 新字段 / 事件名（单列）

| 类别 | 结果 |
| --- | --- |
| 新 `DayReport` 字段（15） | task-15 七：`pending_ledger/guard/stalled/executable/blocked/unobserved` + `stage_midway_leftover`；task-16 七：`free_slots_start/last/min/status` + `loot_lost_steps/tiles/items`；task-22 一：`pending_malformed`（A3 差集恰 15、`removed=[]`；to_dict 导出 `pending_malformed/loot_lost_steps` 等） |
| new journal 事件名 | **0**（A4） |
| checks 键 | 恰 10 键（A2/C-c），新字段不进入 checks（C-g2 判红） |

### 2.4 三卡改法覆盖表（卡面 → 代码锚点 → 实测）

| 卡 | 卡面要求 | 代码锚点（冻结树行号） | 实测 |
| --- | --- | --- | --- |
| 15 | 守卫只对当前可执行/可达待做格敏感 | `_pending_work` 4944 剔 `resume_stall_tiles`/`encircled_day`；`_ledger_pending` 4990 保留 263/217 母集；`_plot_has_work` 3765 剔停滞/被围 | B2g 217 停滞格守卫 0、账本 217；B2i 停滞格不算活 |
| 15 | 六口径快照 + 不变式 + 盲区 fail-closed | `_pending_snapshot` 5047 | B2a-d 快照数值/不变式全过；观测不可用 ⇒ exec=guard |
| 15 | day_justified 加证据门槛 | `HONEST_EXHAUSTED_END_REASONS` 567、`is_justified_end` 570、证据分支 `pending_executable == 0` | B2a2/b2 冬26/27 ⇒ True；B2c2 exec=1 ⇒ False；B2d2 None ⇒ False；B2e2 malformed=1 ⇒ False |
| 15 | burst/换片上限诚实收工、不写 `stuck:` | `_resume_exhausted` 4100、burst 调用点 8906-8918 | B2j 去注释后无 `stuck:`、前缀 `resume_exhausted`；C-h1/h2/C-l2 判红；m23k 实测被杀 |
| 16 | free_slots = cap − 已用；缺失不猜 0 | `farmwork.player_free_slots` 1372 | B3a 5/5（含 unavailable 不猜 0）；B3b 观测不写数值；C-j2/j3 |
| 16 | 满包清障留 `loot_lost`、ok 不变/不算失败 | `farmwork.clear` 漏险判定 2473、成功分支 2531-2540；`_note_loot_lost` 6040 | B3c 满包 ok=True loot_lost=True；B3c2 空包不误报；B3d 聚合 steps=1 items=['Weeds']；C-i1/i2 |
| 16 | 腾格走白名单+保留下限；买种前先腾；压力不判失败 | `_slot_relief` 6109、`_sell_surplus_for_space` 5824、买种前 6607-6649、`_note_slot_pressure_stuck` 6000 | B3e relief@2282 < buy@5956；B3f free>0/unavailable ⇒ 不卖；C-n1 工具/种子进卖单判红；C-k1~k4 双差分 |
| 22 | 残缺 tile ⇒ malformed，一票否决 day_justified | snapshot 5047 分类分支、`pending_malformed` 796、checks 调用点 9622-9625 | B2e/e2/e3/e4；B2d 观测缺失 fail-closed；m23a/b/d/j 实测被杀 |

### 2.5 越界扫描

只改 `brain/agentfarm/longrun.py`+`farmwork.py`、`bridge.py`、`mod/.../manifest.json`、`tests/`、`tools/_note-0745.txt`；未动桥协议、游戏侧、任务板；无新增依赖。版本 bump/冻结属 Lead 九步（已完成）。

---

## §3 B 段：0.7.44 冒烟账本独立复算 + 0.7.45 重放

### 3.1 263 / 217 / 40 / 17 独立复算（夹具 `logs/longrun-smoke-0744.jsonl` 308 行）

| 项 | 独立读数 | 结论 |
| --- | --- | --- |
| 冬 26 burst 形态 | `plot_exhausted_burst` t=362.63 count=5；前 1.5s 内 5 条 `plot_exhausted`（t 362.31/362.40/362.47/362.56/362.63，跨度 0.32s），note 均含「还有 263 格没做完」 | 闭合（B1b） |
| 冬 26 day_end | `ended_by=sleep`、旧理由 `stuck:同一秒连发 5 次换片…263…`、`checked.day_justified=false`（0.7.44 形态） | 历史事实（B1c INFO） |
| 冬 26 阶段窗口 | 223 = `leftover_executable 211 + leftover_blocked 12`；**263−223 = 40 格**无坐标/无来源（10 片×25=250 < 263 截断） | 40 格【无法判定】（B1e，不猜） |
| 冬 27 | burst `pending=217`、`stalled_tiles=217`、source=回片区（work_spot_resume）；217 = 220（round0 片外累计）− 3 挡死格 `[39,31]/[39,32]/[40,32]` | 闭合（B1d） |
| 挡死 17 格 | `logs/longrun-smoke-0744-gaps.json`：tree 12 / grass 3 / stone 1 / twig 1 = 17 | 闭合（B1f） |

### 3.2 0.7.45 重放（独立实现：真实类 + FakeWorld，按最后一张户外观测分类）

| 场景 | 快照/结果 | 判定 |
| --- | --- | --- |
| 冬 26 形态（2 格残余） | `{ledger:2, guard:2, stalled:0, blocked:0, executable:0, unobserved:2, malformed:0}` | `day_justified=True`（0.7.44 为 False，**该 FAIL 形态已转 PASS**） |
| 冬 27 形态（217 全停滞） | `{ledger:217, guard:0, stalled:217, blocked:217, executable:0, unobserved:0}` | `day_justified=True`（**转 PASS**） |
| 还剩 1 格真活 | `executable=1` | `day_justified=False`（不洗白） |
| 整张观测缺失 | `executable=guard=2`、`day_justified=False` | fail-closed 成立 |
| 残缺 1 格 | `malformed=1, executable=0` | `day_justified=False`（一票否决，C-d 原形被堵） |
| 残缺 2 + 真活 1 | `malformed=2, executable=1` | 不放行；不变式全过 |
| 两套待做口径 | `_pending_work()=[]`（217 全停滞） vs `_ledger_pending()=217` | 口径分离成立 |
| burst 收尾 | 前缀 `resume_exhausted`、函数体（去注释）无 `stuck:` | 有界停 + 不写 stuck |
| 停滞格是否算活 | 加入 `resume_stall_tiles` 后 `_plot_has_work` 由 True→False | 两口径未混用 |

### 3.3 task-16 专项

`free_slots` 口径 5/5 例（cap−已用，unavailable 不猜 0）；满包清障 `ok=True` 但 `loot_lost=True/loot_free_slots=0/items=['Weeds']`，**不算 failed**（B3c/B3c2）；loot 聚合 `steps=1, tiles=[[60,10]]`（B3d）；买种前腾格顺序在 `_preconditions_apply` 中 relief@2282 先于 buy@5956（B3e）；`_slot_relief` 在 free>0 或 unavailable 时直接 False 且 `sell` 零调用（B3f）；压力腾不出只 `pressure=True/failed=False` 留痕，不判失败。

---

## §4 C 段：对抗通道 a–n（39 条判据全过）

| 通道 | 注入形态 | 判据结果 |
| --- | --- | --- |
| a malformed 顺序 | 把一票否决挪到白名单之后 | C-a 判红（顺序检查） |
| b 判据证据 | `day_justified` 调用漏 `pending_executable`/`malformed_tiles` | C-b 判红（源码证据参数） |
| c checks 污染 | 新字段塞进 checks / 缺键 | C-c 恰 10 键；C-g1 绿、C-g2/g3 红、C-g4【无法判定】 |
| d 钉死用例 | 删掉作者 5 条钉死测试 | C-d 5/5 在 |
| e 快照造假 | `executable=0` 与 ledger 不符 / 负数 / 缺键 | C-e1 绿、e2/e3 红、e4【无法判定】 |
| f 判据三态 | malformed=1、exec=2、`day_justified=false` 却 exec=0、缺字段 | C-f1 绿、f2/f3/f4 红、f5【无法判定】 |
| g checks 三态 | 恰 10 键/塞 `pending_malformed`/缺键/缺失 | C-g1 绿、g2/g3 红、g4【无法判定】 |
| h 0.7.44 两 FAIL 形态 | `stuck:` burst、`day_justified=false`、有活仍 VERIFIED | C-h1/h2/h3 全红；C-h4 合法规避绿 |
| i loot_lost | 被算失败 / 被吞（无字段） | C-i1 绿、i2 红、i3【无法判定】 |
| j 空格状态 | 自洽 / unavailable 不猜 0 / unavailable 却写 0 / 缺状态 | C-j1/j2 绿、j3 红、j4【无法判定】 |
| k 腾格双差分 | 行数没减却自称卖掉 / 钱变了 / 无卖货事件 | C-k1 绿、k2/k3 红、k4【无法判定】 |
| l burst 标签 | 诚实 burst / 写 `stuck:` / 无 burst | C-l1 绿、l2 红、l3【无法判定】 |
| m 会计放宽 | 有活却 `no_unmet_stages=True` | C-m1 红、m2 诚实停绿 |
| n 卖单白名单 | 工具/种子进 slot_relief 卖单 | C-n1 红、n2 普通盈余绿 |

---

## §5 D 段：变异两列（作者自报 vs 冻结副本实测）

### 5.1 作者三脚本（副本跑，`--from-worktree`；证据 `scratch/_t0745b_author_mut.txt`）

| 卡 | 脚本 | 自报 | 实测 |
| --- | --- | --- | --- |
| 16 | `tests/_mutate_t16_inventory.py`（基线 Ran 9 OK） | 5/5 | **5/5 实测被杀**：m1 红 7、m2 红 1、m3 红 2、m4 红 2、m5 红 2 |
| 22 | `tests/_mutate_t22_malformed.py`（基线 Ran 4 OK） | 3/3 | **3/3 实测被杀**：m1/m2/m3 各红 2 |
| 15 | `tests/_mutate_t15_justified.py`（基线 Ran 6 OK） | 4/4 | **2/2 已跑被杀 + 2 条锚点过期**：m1 红 2、m2 红 1；**m3 锚点出现 0 次（task-22 改写了 `is_justified_end` 调用点，脚本未更新）→ RC=2 中止，m4 未执行** |

> **对抗结论**：作者 t15 脚本的「4/4」在 0.7.45 冻结树上**不可复现**（2 条锚点已随 task-22 失效）。m3/m4 的意图由我方 m23j/m23k 按新锚点补测（均被杀，见 §5.2），不把作者自报当证据。

### 5.2 我方独立变异 `scratch/_t0745b_mutate.py`（11 条；锚点 11/11 OK；基线 probe FAIL=0、三卡单测 FAIL/ERROR=0）

| 变异 | 改法 | probe 杀 | 单测杀 | 实测 |
| --- | --- | --- | --- | --- |
| m23a malformed 一票否决删除 | `if int(malformed_tiles) > 0: return False` → `if False:` | 2 | 2 | **KILLED** |
| m23b 残缺记录改回 unobserved | malformed 分支 → `if False:` | 2 | 2 | **KILLED** |
| m23c 证据门槛打开 | `pending_executable == 0` → `return True` | 2 | 4 | **KILLED** |
| m23d 观测缺失 fail-open | `executable=guard` → `executable=0` | 2 | 2 | **KILLED** |
| m23e 清障掉落检测关掉 | `loot_risk = …` → `False` | 1 | 1 | **KILLED** |
| m23f 空格按容量算 | `cap - len(inv)` → `cap` | 2 | 7 | **KILLED** |
| m23g 压力腾格通道关掉 | `if need <= 0 and not space_pressure:` → `if need <= 0:` | 0 | 2 | **KILLED** |
| m23h 买种前不腾格 | `if fs_status == "ok" and free_slots < 1:` → `if False:` | 0 | 2 | **KILLED** |
| m23i checks 载荷污染 | checks 里插 `pending_malformed` | 1 | 1 | **KILLED** |
| m23j day_justified 丢 malformed 证据 | 调用点 `malformed_tiles=rep.pending_malformed` → `0` | 1 | **0** | **KILLED（仅 probe 杀；见 NIT-1）** |
| m23k burst 写回 `stuck:` | burst 调用 `_resume_exhausted` → `_do_sleep("stuck:…")` | 0 | 1 | **KILLED** |

**实测 11/11 被杀，未杀/异常 0**（`scratch/_t0745b_my_mut.txt`）。判杀器 = 我方 probe B/C 段 + 作者三卡定向单测，任一红即 KILLED；复制冻结树→文本变异→跑杀器，冻结树零改动。

---

## §6 结论、NIT 与放行建议

### 6.1 判定

**task-15 + task-16 + task-22 合并代码面：PASS-WITH-NITS。** 依据：① provenance/版本/checks 10 键/公式未动均硬核对通过；② malformed 一票否决在所有白名单之前，残缺 1 格与整张观测缺失都 fail-closed；③ 0.7.44 冒烟 263/217 在真实账本上独立复算闭合（40 格如实【无法判定】），重放后冬 26/27 `day_justified` 均为 True，exec≥1/malformed>0/观测缺失均 False；④ task-16 背包链路（口径、掉落留痕、白名单腾格、买种前腾格、压力不判失败）逐条实测成立；⑤ 39 条对抗判据三态全过；⑥ 我方 11/11、作者 t16 5/5 + t22 3/3 变异实测被杀。

### 6.2 放行建议

- **可以放行 `smoke-0745` 重冒烟**：冻结树已绿（§0）、版本载体 0.7.45、0.7.44 两个 FAIL 形态在离线重放中已转 PASS；冒烟必须按 `docs/_release-0.7.45.md` §3 跑 ≥1 天，判据：`verified=true` 至少 1 天、`day_end.pending_executable=0` 时 `day_justified=true`、**再出现 `stuck:` 掩盖或 malformed 日仍 VERIFIED ⇒ 不放行**。
- **不能仅凭本报告放行 A9/B9**：真机证据缺失（smoke-0745 未跑）；A9 账本必须 already 双列（NIT-4），A8/A9 不同起点不可跨对比较。
- A9 判定附加硬要求：`stages[].already`/`attempted_ok` 与 `ok` 并列读；「`ok=0/cleared=0` 但 `already>0`」阶段数必须与 B9 同起点对比（A8 该阶段数=0，stages=172、already 总 50）。

### 6.3 NIT（单列；均非阻塞 smoke-0745 放行）

1. **NIT-1（测试缺口，建议 0.7.46 补）**：`day_justified` 调用点把 `malformed_tiles=rep.pending_malformed` 改成 `0` 的变异（m23j）**只有我的 source 判据能杀，作者单测 0 红**——malformed 只在函数级被测，缺一条「整日跑完 + 残缺 tile + 断言 verified=false」的集成测试。
2. **NIT-2（测试脚本过期）**：`tests/_mutate_t15_justified.py` 的 m3/m4 锚点随 task-22 失效（0 次命中）；提交前应同步更新，否则「4/4」只是历史数字。
3. **NIT-3（沿用）**：`stage_midway_leftover` 仍无单测直测（仅字段/结构判据与 B 段重放）。
4. **NIT-4（task-10 #1 原话）**：`tools/verify-run3.py` 只累加/单列 `ok`（`:1104`/`:1122`），不并列 `already`。A9 放行时必须读 `day_end.stages[].already`、`attempted_ok`、以及「`ok=0/cleared=0` 但 `already>0`」的阶段数，并与 B9 同起点对比；A8/A9 不同起点不可跨对比较（A8 起点冬 26，A9 备份 `logs/ab-backup/A9-start/`）。
5. **NIT-5（沿用）**：`pending_unobserved` 仍只作 info、不做阻断；截断观测下与 NIT-1 同源。
6. **NIT-6（读数差额）**：Lead 自报工作树全量 1330 vs 冻结树 **1324**，差 6 —— **【无法判定】**（冻结树无 task-24 未入树测试；差额无法完整解释，不采信 1330；本报告以 1324 为唯一值）。
7. **NIT-7（跨卡）**：`tools/analyze-longrun.py` 在冻结树里仍是 0.7.44 期版本（task-24 未入冻结树）；A9 对账若依赖新字段收录，须在 A9 前确认工具版本。

### 6.4 已知限制 / 【无法判定】

- `smoke-0745` 真机未跑 ⇒ VERIFIED、日终字段真机分布均不在本判定内。
- 冬 26 的 **40 格**账本无坐标（10 片×25=250 < 263 截断）⇒ 逐格归属【无法判定】；冬 27 的 217 精确闭合。
- 冻结树 dotnet build 未重跑（Mod 无代码变更，dll 与 0.7.44 同哈希）⇒ 以 Lead 九步读数为准。
- 全量单测依赖未入仓夹具（`.gitignore` 内 `scratch/_ledger*` + A8/smoke 账本）；纯 `git archive` 树跑全量会红，属夹具缺失，不是产品红。

---

## §7 边界声明

- 只读生产代码；只写 `docs/_review-0.7.45.md` 与 `scratch/`；未改任务板、未 deploy、未碰游戏/桥、未写开发日志。
- 所有变异均在冻结树**临时副本**里做，冻结树零改动；作者自报数字另列，不替代实测。
- 判据用本报告自己的独立实现（`scratch/_t0745b_probe.py`），不抄作者脚本；缺失项写【无法判定】，不当 PASS。
- 本判定只对 `2feb1f8` 冻结树的三卡代码内容负责；smoke-0745 与 A9/B9 由 Lead 依据真机证据 + 九步决定。
