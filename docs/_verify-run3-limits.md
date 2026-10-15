# `tools\verify-run3.py` 的极限（负例 K 系列：它是**账本检查器**，不是**世界校验器**）

- 作者：deputy-lead（应 Lead m00877④）
- v1 2026-10-13 01:0x，工具 `tools\verify-run3.py` @ `bfb8649`（367 行）
- **v2 2026-10-13 01:1x 复测重写**：Lead 已按本文 §6 加固工具（536 行），口径/行号/期望表按加固后版本重写；复跑证据见 §8。
- **v3 2026-10-13 01:2x**：deputy-lead 按 **task-19 要求 5④**（"没有任何户外快照 ⇒ 如实 False/缺省，禁止默认 true"）新增 **B4b**（`:394-401`）与"没写 `final_water` ⇒ 信息项"（`:403-407`）；新增负例 **R**（window 口径覆盖 0 格却自称 `watered_outdoor=true`）与正对照 **S**（farm 口径覆盖 32 格 ⇒ 仍 exit 0）。**行号均按 603 行版**。后果：**K2 从 exit 0 翻成 exit 1**（它的 `final_water` 正是 window/0 格），矩阵 29 本 ⇒ exit 0 = 6 本 / exit 1 = 23 本（其余读数逐本不变，见 §2/§8）。
- **v4 2026-10-14 21:5x（task-72）**：新增 **§9**（task-52/task-63 豁免记账的**三条洗白通道**：修复前 exit 0 / 修复后 exit 1 的双侧实测）与 **§10**（run6 归因更正：`unreachable_within_bound=false` 与上界无关）；§4 盲区清单加 **B11–B14**；§5 加"**实测有效**的防线"。三条通道已由 **`9f554d7`（task-71）**修复并用负例锁死（`tests/test_verify_run3.py:518-578`）；**仍开放的是 B11**（真失败改写成 `unreachable`/`tool_refused`，账本层不可判）。
- **v5 2026-10-14 22:4x（本文档当前版本，task-79）**：记录 task-68 的 `encircled` 带来的**V5 洗白通道已关闭** —— 上界分母从 `attempted` 换成 **`bound_basis = attempted − encircled`**（"被围住的格既不是走不到、也不是干了没成，不该为豁免额度做贡献"）：脑侧 task-78 落地字段、工具侧 Lead 镜像提交 **`2ce830b`**（1051 行，sha256 `FDB4E8D9…`；自算 `max(5, floor(0.2×bound_basis))`，账本 `bound_basis` > 自算 或账本 `*_bound` > 自算 ⇒ problem）。§2.1 补双侧读数、§3 加第 13 条、§4 新增 **B15（已关闭）/ B16（开放）/ B17（开放）**、§9.5 记双侧实测原文。**明确保留开放、不许写成已修**：**V1 = B16**（0 阶段 + `no_work` 理由 + `verified` ⇒ 两侧都 exit 0）、**V2 = B17**（遮蔽，task-15 已知）、**B11**。
- **v6 2026-10-15 20:4x（task-86）**：Lead 把**验收口径**从"整本账本零问题"改成"**尾部连续 N 天达标 + 窗口内问题为空**"（提交 **`7c4ff68`**：`tools/verify-run3.py` +30 / `tests/test_verify_run3.py` +35 / `docs/_run6-criteria.md` +5 / `scratch/_run7_summary.py` +44；父 `1ffe2ca`）。窗口之外日子的**日级**问题降级为 `--json` 的 **`history_problems`**（人类输出里"历史问题（达标窗口之外…）"段），`streak < --days` **不降级**，不带 `[day]` 前缀的**全局**问题（journal 损坏 / `mod_version_mismatch` / `finish` 自相矛盾）**永不降级**。我独立两侧复跑 78 本账本（`scratch/_t86_side.py`）：**只有 run7 一本改变**（rc 1→0、9 条问题→9 条 history、VERIFIED），其余逐字不变；`--days 5` 零变化。**同时打穿/新增三条盲区 B19–B21**（详见 §11）：B19 = 打穿（窗口内问题可被"含 `]` 的 day 标签"降级）；B20 = 窗口外系统性缺陷被一路放过（设计取舍，需明示）；B21 = `analyze-longrun.py`（整本）与本工具（窗口）结论反向。判定见 `docs\_review-caliber-2026-10-15.md`（**FAIL**）。
- **v7 2026-10-15 20:5x（task-90，本文档当前版本）**：**B19（日标签注入 ⇒ 假 VERIFIED）已关闭** —— Lead 提交 **`c6d2a7a`**（`tools/verify-run3.py` +44/−5：新增 `_clean_label()` 净化 `[`/`]`/换行/制表、`problem_day()` 按**已知日标签最长前缀匹配**、降级条件改成 `head and head in known_names and head not in tail_names` ⇒ **头部标签不属于任何已知日 ⇒ 一律 fatal**；`tests/test_verify_run3.py` +55 两条新用例；`docs/_run6-criteria.md` +2）。我独立三副本复跑（`old`=`7c4ff68^` / `buggy`=`7c4ff68` / `fixed`=`c6d2a7a`，冻结脚本 `scratch/_t90_freeze.py`）：A4b 从 `buggy rc 0 / VERIFIED` 变 **`fixed rc 1 / needs_review`、问题留在 `problems`、history 为空**；85 本并排里 **`buggy`↔`fixed` 只有 A4b 一本不同**（run7 两者逐字相同 rc 0/0/9）；**同类洞普查**：全工具只有 1 处"按首个 `]` 截断"（`:127` 的 fallback），609 次 `problem_day` 调用里 **0 次走 fallback**（606 次最长前缀命中、3 条全局问题无前缀）⇒ 该分支对工具自产问题不可达；其余"从文本解析结构化字段"的站点（`ended_reason`/`reason` 的 `startswith` 白名单、`_UNREACH_MARKS` 子串）属**信任账本自述**类（B11/B16/B20 一线），不是分隔符截断。**B20 / B21 与 B11/B16/B17 一律保留开放**。§0 记录、§4 表、§12 为本次新增。
- **一句话结论（v3）**：K3（`finish` 自述反向）、K4（浇水两处自述矛盾）、**K2（window 口径 0 覆盖却自称浇过户外水）**已被抓（exit 1）；**完全自洽的伪造账本 `review-neg-K` 仍然 exit 0** —— `verify-run3.py` 验的是**这一本账本自己是否自洽**，**不是世界真的推进过 3 天**。防伪造仍必须靠**账本之外的证据**（§5）。

## §0 修订记录（初版 → v2 加固 → v3）

| # | §6 建议 | 落地情况 |
| --- | --- | --- |
| 1 | `finish` 自洽 + 与工具结论同向 | **已加固** `:478-500`（自洽 `:481-484`；同向 `:486-494`，其中 `code=0` 但已有别的问题 ⇒ 只记信息项 `:488`）。K3 现 exit 1 |
| 2 | `watered_outdoor` 与 `final_water.dry>0` 互斥 | **已加固** `:382-389`。K4 现 exit 1 |
| 3 | `t` 基本卫生 | **部分**：全局回退 `:240-242` 与当天倒挂 `:379-381` **只记信息项**（Lead 有意：`t` 是 longrun 自己的 `time.time()`，NTP 回拨会误杀真机） |
| 4 | 跨日 = 恰好 +1 天 | **已加固** `:365-377`（`_day_ordinal` 折绝对日序，季节边界正确；认不出日形状只记信息项 `:369-373`） |
| 5 | 0 步 VERIFIED 记 info | **改为条件放行** `:412-419`：有"无活可做"证据（`excuse` 或 `ended_reason` 以 `no_work`/`night`/`stamina` 开头）⇒ info 放行；否则 ⇒ problem |
| 6 | `worldSeq` 采样 | **未做**（Lead 有意：要改脑 + 口径，且 live join 成本高） |
| 7 | （v2 nit）"已由上面的问题解释"措辞 | **已修**（Lead `d43e75e`）：`:486-489` 降为信息项，不再一因两报 |
| 8 | （v3 新增）window 口径 0 覆盖不许自称 `watered_outdoor=true` | **已加** `:394-401`（依据 task-19 要求 5④）；`final_water` 整体缺失 ⇒ 只记 info `:403-407`。K2 现 exit 1 |

## §1 实验材料（全在 `scratch\`，生成器可复跑）

| 账本 | 构造 | 目的 |
| --- | --- | --- |
| `review-neg-K-forged-consistent.jsonl` | 3 天 `ended_by=sleep`+跨日+`verified=true`+`checks` 七项全 true（含 `watered_outdoor`/`no_unmet_stages`）+`leftover==0`+`failed_steps == Σ stages.failed` | 最大化自洽的伪造（**仍过**） |
| `review-neg-K2-forged-empty.jsonl` | K 但每天 `stages=[]`、`ok/skip/fail = 0/0/0`，`ended_reason="night:到点了"`，且 `final_water` 是 **window 口径 0 覆盖** | "没干活也算过？" + window 口径（**v3 起被 B4b 抓住**） |
| `review-neg-K3-forged-finish-lie.jsonl` | K + `finish.code=1, verified_streak=0` | `finish` 是否被核对（B1） |
| `review-neg-K4-forged-water-contradiction.jsonl` | K + `final_water.dry=5` 且 `checks.watered_outdoor=true` | 同源字段是否互检（B4） |
| `review-neg-R-t19-window-no-outdoor.jsonl` | 全绿日 + `watered_outdoor=true` + `final_water={location:"FarmHouse", tiles:0, crops:0, dry:0, scope:"window"}` | **task-19 上线前探针**：证据来源为空（当天无任何户外快照）时，"true"能不能白过 |
| `review-neg-S-t19-farm-scope-ok.jsonl` | 全绿日 + `watered_outdoor=true` + `final_water={scope:"farm", tiles:32, crops:32, dry:0}` | 正对照：加固不得误杀合法的一天 |
| `review-task11-modal-day.jsonl` | 绿账本末日改 `blocked_modal` + `no_blocking_modal=false` | 反向对照：**真问题**必须被抓（它被抓了） |
| `review-t72-bound-inflate.jsonl` | 42 格不可达 + 账本 `unreachable_bound=9999`（自算 10），其余自洽 | 通道 (c)：抬上界/抬分母（`9f554d7` **前** exit 0） |
| `review-t72-exempt-no-coords.jsonl` | 扣 3 格不可达豁免、`unreachable_tiles=[]`、无逐格 journal；上界取自算值 6 | 通道 (e)：扣豁免不写坐标（修复前 exit 0） |
| `review-t72-overlap-two-sets.jsonl` | 同一批 2 格 (50,14)/(51,14) 同时进 `unreachable_tiles` 与 `refused_tiles`；上界自洽 | 通道 (f)：两套豁免重复扣减（修复前 exit 0） |
| `review-t72-relabel-clean.jsonl` | 4 条真失败（`blocked`，reason「锄完不是 dirt」）改写成 `unreachable`，**账目字段全自洽**（bound=5、坐标齐、计数齐） | **B11 盲区**：账本层不可判（修复前后**都 exit 0**） |
| `review-t72-vacuum-clean.jsonl` | 8 格全不可达 + 0 成功动作 + 自称 VERIFIED，bound 自洽（=5） | 反空洞防线（修复前后**都 exit 1**） |

生成器：`scratch\_review_neg_gen.py`（mode `forged_consistent`/`forged_empty`/`env_info_item`/`env_info_cannot_mask`/`t19_window_no_outdoor`/`t19_farm_scope_ok`/`t15_last_round_done`/`t15_earlier_done_last_leftover`）、`scratch\_mk_k3_k4.py`、`scratch\_mk_task11_modal_day.py`、矩阵跑器 `scratch\_review_matrix.py`（`EXPECT0` = 期望 exit 0 集合）。pwsh 下必须 `$env:PYTHONUTF8="1"`。

**task-72 追加（豁免类账本）**：`scratch\_t72_forge.py`（复用 `scratch\_t54_forge.py` 的基座构造，但把 `unreachable_bound`/`refused_bound` 设成**工具自算值** `max(5, floor(0.2×attempted))` —— 即"攻击者把账本做到完全自洽"，从而把三条通道**各自隔离**，见 §9）；工具两侧冻结：`scratch\_t72_freeze_tool.py`（已提交 HEAD 版 → `_t72_tool_head.py`，Lead 在制版 → `_t72_tool_wip.py`）、`scratch\_t72_freeze2.py`（`9f554d7` 版 → `_t72_tool_fix.py` + 该提交的 `tests/test_verify_run3.py`）；闸门引入历史：`scratch\_t72_when.py`。

**v2 踩到的坑（留档）**：加固后我第一次跑矩阵，**除 green 外全部 exit 1** —— 不是工具误报，是**我的假账本自己 `t` 不单调**（`env_fail`/`finish` 的 `t` 小于前面事件）。已修。**真机 run2 账本零回退报告** ⇒ 该检查对真实数据不是误报（且现已是信息项）。

## §2 读数（v3 定稿）

| 账本 | verify-run3（v3） | 说明 |
| --- | --- | --- |
| K（自洽伪造） | **exit 0 / VERIFIED** | 3 天全绿、4 阶段、ok=40 ⇒ **仍是已知盲区**（它的 `final_water.scope="farm"` 有覆盖，B4b 不适用） |
| K2（0 阶段 0 步 + window 口径） | **exit 1 / needs_review**（v3 起被 B4b 抓住） | 每天一条 `checks.watered_outdoor=true 但 final_water.scope=window 且覆盖 0 格…⇒ 该 true 不可采信`；plus 原有 info `当天 0 个阶段且自称 VERIFIED，但有"无活可做"证据…⇒ 接受`。**"自洽伪造仍能过"这条盲区结论由 K 承担**（farm 口径、无矛盾、仍 exit 0） |
| K3（finish 自述失败） | **exit 1** | `finish 自述 code=1（自称未达标）而本工具判定达标（账本自相矛盾）` + info |
| K4（浇水自相矛盾） | **exit 1** | 每天 `watered_outdoor=true 但 final_water.dry=5（账本自相矛盾）` |
| **R（window 0 覆盖却自称 true）** | **exit 1 / needs_review** | 每天一条 B4b 问题（改前 exit 0 ⇒ 这正是 task-19 上线前必须堵的洞） |
| **S（farm 口径 32 格）** | **exit 0 / VERIFIED** | 正对照：加固不误杀 |
| 反向对照 `review-task11-modal-day` | **exit 1** | `ended_by=blocked_modal`、`verified=false`（真问题照抓） |

`tools\analyze-longrun.py` 交叉：K / K4 / R 上四类判定仍 **0 条**（它不查这些矛盾）⇒ **两个工具同读一本账本、同源，自洽伪造两边都过**（结论不变）。

**29 本全量矩阵（deputy-lead 独立复跑，`scratch\*.jsonl` + `logs\*.jsonl` 一个不漏，`scratch\_review_matrix.py`）**：
- **exit 0（6 本）**：`scratch\journal-green.jsonl`、`review-neg-G-env-info-item`、`review-neg-I-env-explained`、`review-neg-K-forged-consistent`、`review-neg-P-t15-last-round-done`、`review-neg-S-t19-farm-scope-ok`。
- **exit 1（23 本）**：`review-neg-A/B/C/D/E/F/H/J/K2/K3/K4/Q/R`、`scratch\review-task11-modal-day.jsonl`、真机 `logs\longrun-3day-llm-run2.jsonl`、`logs\longrun-3day-llm-run1.jsonl`、`logs\longrun-3day-run1.jsonl`、`logs\longrun-rehearsal-0.7.22.jsonl`，以及只有 1 天的 `scratch\_ledger_green.jsonl`/`_ledger_fallback.jsonl`/`_ledger_leftover_verified.jsonl` 与旧探针 `scratch\journal-green-bad.jsonl`、`scratch\journal-nochecks.jsonl`（后 7 本属预期）。
- **v3 相对 v2 的变化只有两处**：①`K2` exit 0 → exit 1（B4b）；②`R` 从不存在 → exit 1。**其余 27 本 problems/exit 逐本不变**（部分账本 `infos` +1/天，来自"`watered_outdoor=true` 但账本没写 `final_water`"的信息项 `:403-407`，不影响结论）。改前/改后逐行对照留档：`scratch\_matrix_before_t19gate.txt`、`scratch\_matrix_after_t19gate.txt`。

### §2.1 task-72：豁免三通道的双侧读数（修复前 vs 修复后）

两侧工具都按**冻结副本**跑（同一份字节 ⇒ 可复现）：
- 修复前 = 已提交 HEAD（`3c02940` 的 `tools/verify-run3.py`，937 行，sha256 `6c0ac399…`）→ `scratch\_t72_tool_head.py`
- 修复后 = `9f554d7`（task-71，988 行，sha256 `a62a6e94…`）→ `scratch\_t72_tool_fix.py`
- **v5 两侧（task-79）**：修复前 = `8ceea87`（995 行，sha256 `960837CB…`，即 `scratch\_t77_snap\tools\verify-run3.py`）；修复后 = `2ce830b`（1051 行，sha256 `FDB4E8D9…`，即仓库 `tools\verify-run3.py`，task-78 的镜像）

| 账本 | 修复前 | 修复后 | 说明 |
| --- | --- | --- | --- |
| `review-t72-bound-inflate` | **exit 0 / VERIFIED** | **exit 1 / needs_review** | 修复后的 problem：「不可达豁免上界账本=9999 > 自算=10（attempted=50）⇒ 上界被放宽」+ refused 侧同款 |
| `review-t72-exempt-no-coords` | **exit 0 / VERIFIED** | **exit 1 / needs_review** | 「不可达豁免扣了 3 格却没写任何坐标（journal 无 unreachable 逐格事件、`day_end.unreachable_tiles` 也空 ⇒ 缺失≠通过）」 |
| `review-t72-overlap-two-sets` | **exit 0 / VERIFIED** | **exit 1 / needs_review** | 「同一格同时进两套豁免：2 格（例 (50,14)、(51,14)）⇒ 可被重复扣减」 |
| `review-t72-relabel-clean` | exit 0 / VERIFIED | **exit 0 / VERIFIED** | **B11 仍开放**：真失败改写成 `unreachable`，账目自洽 ⇒ 两侧都看不出 |
| `review-t72-vacuum-clean` | exit 1 / needs_review | exit 1 / needs_review | 反空洞防线，两侧一致有效 |
| 对照 `scratch/journal-green.jsonl` | exit 0 | exit 0 | 修复**没有**引入假红 |
| 真机 run2/run3/run5/run6 | exit 1 ×4 | exit 1 ×4 | 判决逐本未变 |

**task-79（v5）附加读数**（复现脚本 `scratch\_t79_replay.py`，两侧工具见上；同一批账本逐本对比退出码 + 「问题：」块）：

| 账本 | `8ceea87`（修复前） | `2ce830b`（修复后） | 说明 |
| --- | --- | --- | --- |
| `review-t77-v5-encircled-inflates-unreachable-bound`（800 次 `encircled` 计进 `attempted` + 200 格真·不可达 + `bound=200`、`verified=true`） | **exit 0 / VERIFIED** | **exit 1 / needs_review** | **V5 通道关闭**。修复后 problem 逐字见 §9.5 |
| `review-t77-v1-encircled-no-work-verified`（0 阶段 / 0 动作 / `no_work` 理由 / `verified=true`） | exit 0 | **exit 0** | **B16 仍开放**（不是 task-68 引入；控制组 `v1c`（不写 encircled）判决完全相同，info 仍是"0 个阶段且自称 VERIFIED，但有『无活可做』证据 ⇒ 接受"） |
| `review-t77-v2-encircled-masked-by-later-clean-stage`（同 kind 更早一轮 `leftover=1`、最后一轮 0） | exit 0 | **exit 0** | **B17 仍开放**（task-15 已知遮蔽；只多一条 info「更早一轮 leftover=1、最后一轮 0」） |
| `review-t77-v3`（诚实红）/ `review-t77-v4`（谎报 `no_unmet_stages`） | exit 1 / exit 1 | exit 1 / exit 1 | 未被本次改动影响（问题数 2→2） |
| `review-t72-relabel-clean`（B11 分类造假） | exit 0 | **exit 0** | **B11 仍开放**，不许写成已修 |
| `scratch/journal-green.jsonl` | exit 0 | exit 0 | 无假红 |
| `_t5x_vacuum` / run2 / run3 / run5 / run6 | 1 / 1 / 1 / 1 / 1 | **1 / 1 / 1 / 1 / 1**（问题数 3 / 11 / 17 / 21 / 9 **逐本相同**） | 六本既有账本判决未变 |

**边界尝试（防止换个写法绕过新口径）**：用 `scratch\_t79_v5edge.py` 造三本 —— W1 账本显式 `bound_basis=1000`（> 自算 200）⇒ **exit 1**（`上界基数账本 bound_basis=1000 > 自算=200` + 上界同步判红）；W2 把 `bound_basis` 写对（200）但 `unreachable_bound` 压到自算值 40、仍报 `unreachable=200` / `unreachable_exempt=40` / `verified=false` ⇒ **exit 1**（`day_end verified=false` + `no_unmet_stages=false（自算 leftover=200 格）`）；W2' 同 W2 但谎报 `no_unmet_stages=true`/`verified=true` ⇒ **exit 1**（`no_unmet_stages=True 与自算不一致（…扣掉不可达豁免 40 后剩 160 格…）`）⇒ 三条写法都堵住了。

⇒ 一句话：**task-71 把三条"账本层可判"的通道都堵上了，且不误杀绿账本；唯一仍然过不去的是 B11（分类造假），它不是判据能解决的，见 §5-D/§10。** （v5 追加：`2ce830b` 把 task-68 `encircled` 的 **V5 通道**也堵上了 —— 上界分母剔除被围格；但 **V1/V2/B11 三条仍开放**，见上表，不许谎报已修。）

## §3 工具**确实**查了的东西（v3 行号 = 603 行版，全部仍是"账本内部一致性"）

1. `ended_by != "sleep"` 即问题（`:301-302`）；`ended_by=="sleep"` 必须有 `event=sleep, ok=true` 证据（`:304-305`）—— **回执不算证据，要求观测里的日期变了**。
2. `checks.watered_outdoor` 缺失或 `false` 即问题（`:315-322`）；窗口 `unwatered_crops`/`crops_watered` 另算（`:323-327`）。
3. 日级 `failed_steps` 与 `Σ day_end.stages[].failed` 交叉核对 + **差额容错**（`:335-359`）：自述比求和还多 ⇒ 问题；自述少但差额**解释不完**（`Σ env_block_count + Σ inconclusive_count` 以外）⇒ 问题；解释得完 ⇒ 信息项；`failed_any > failed` 只记 info。
4. `checks.no_hard_failures=false`（`:328-329`）、`day_end verified=false`（`:360-361`）、`sleep_fail>0`（`:362-363`）即问题。
5. **跨日恰好 +1 天**（`:365-377`，按 28 天/季折绝对日序；认不出日形状记信息项）。
6. `checks.watered_outdoor=true` 与 `final_water.dry>0` **不可并存**（`:382-389`）。
6b. **（v3 新增）**`checks.watered_outdoor=true` 与 `final_water.scope=="window"` 且 `tiles==0` **不可并存**（`:394-401`，依据 task-19 要求 5④）；`watered_outdoor=true` 但整条 `final_water` 缺失 ⇒ 只记 info（`:403-407`）。
7. **0 阶段却自称 VERIFIED**（`:412-419`）：有"无活可做"证据（`excuse`/`ended_reason` 前缀）⇒ 信息项放行（`:413-417`），否则问题（`:418-419`）。
8. 阶段后置条件：`checks.no_unmet_stages` 与自算 `leftover` 不一致 ⇒ 问题（`:423-428`）；**自述 `false` 一律问题**（`:431-435`，不信自述）；`leftover_zero_target>0` ⇒ 问题（`:438-440`，task-15 修 A 的守卫）；同日同阶段种类的"中途遗留被最后一轮遮蔽"只记 info（`:280-296`）。
9. 异常事件 `bridge_down`/`watchdog_stop`/`modal_timeout`/`no_day_progress` 出现即问题（`:427-434` 起的异常事件段）。
10. 尾部连续 VERIFIED 天数 ≥ `--days`（`:451-456`），`ok = streak >= target_days and not problems`（`:467-470`）。
11. `finish` 自洽 + 与本工具结论同向（`:478-500`；两侧 `days` 不可比时降为信息项；`verified_streak` 不同只记信息项；没有 `finish` 也记信息项）。
12. **（v4，行号按 `9f554d7` 的 988 行版）豁免记账**（task-52 不可达 / task-63 锄不动被拒）：自算分母 `day_end.attempted` > `Σ stages[].attempted` ⇒ problem「抬高分母就能放宽 20% 上界」（`:462-466`）；`bound_self = max(5, floor(0.2×attempted))`，账本 `unreachable_bound` > 自算 ⇒ problem（`:468-475`）、< 自算 ⇒ **info**「更严」（`:476-479`），refused 侧镜像（`:522-532`）；`*_exempt > 0` 而逐格坐标（journal 事件 + `day_end.*_tiles`）皆空 ⇒ problem「缺失≠通过」（`:486-490` / `:542-546`）；两套坐标**交集非空** ⇒ problem「同一格同时进两套豁免」（`:547-556`）；`checks.unreachable_within_bound is False` ⇒ problem（`:499-503`，refused 侧 `:518-522` 为 v3 既有）。⚠️ 这些**仍是"账本内部一致性"**：抓的是"账目互相打架"，不抓"分类本身是不是真的"（见 B11/§9）。
13. **（v5，行号按 `2ce830b` 的 1051 行版）上界基数（task-78）与 stuck 翻篇呈现（task-73）**：`day_end` 白名单加 `bound_basis`（`:233`）与 `stuck_flushed`（`:235`）；`encircled_total = day_end.encircled`（缺失则 `Σ stages[].encircled`）⇒ `basis_self = max(0, attempted_total − encircled_total)`（`:506-511`）；账本 `bound_basis` 缺失 ⇒ 用自算（`:529`）、> `attempted` ⇒ problem「抬高基数就能放宽 20% 上界」+ 退回 `attempted`（`:514-519`）、> 自算 ⇒ problem「基数被放宽，可能把真失败洗成不可达」（`:520-528`）、≤ 自算 ⇒ 取 `min(账本, 自算)`；`bound_self = max(5, floor(0.2 × basis))`，refused 侧镜像（`:586-595`）；info 行现在显示 `bound_basis={basis} = attempted {attempted_total} − encircled {encircled_total}`（`:558`）。**stuck 翻篇**：`stuck_flushed=true` 的日若 `verified` ⇒ problem（`:868-874`，「翻篇只许翻页、不许洗白」），`stuck_flush`/`stuck_flush_skipped` 次数与 `stuck_flush_resnap_failed` 只记 info（`:875-885`）。
    ⚠️ 一处**文案不一致**（不阻塞）：不可达侧的判红仍写 `（attempted=1000）`，而被拒侧已改成 `（bound_basis=200）` —— 同一新口径两种措辞，建议统一成 `bound_basis`。

⇒ 这些**全是读账本自述**：`verified`/`checks`/`stages`/`failed_steps` 都是 longrun **自己写的**，账本自洽就无从分辨；加固只是把"自己跟自己打架"的花样抓得更全（B4b 也属这一类：它抓的是"自称浇过水，却同时写着证据来自 0 格的窗口"）。

## §4 盲区清单（v7 状态；B1–B10 逐条沿用 v3 结论，B11–B22 见下）

| # | 盲区 | v4 状态 |
| --- | --- | --- |
| B1 | `finish` 不参与判定 | **已关闭**（K3 exit 1） |
| B2 | `t` 从不检查 | **有意降级为信息项**：判成问题会误杀真机 |
| B3 | 不与任何 live 观测 join（`final.day`/`money`/`stamina`/`worldSeq` 是否真来自世界） | **开放** |
| B4 | `final_water` 与 `checks` 不互检 | **已关闭**（K4 exit 1） |
| B4b | 自称浇过户外水、但证据来源为空（window 口径 0 格） | **已关闭**（R / K2 exit 1）。工具文案已写成可执行建议：`watered_outdoor=true 但 final_water.scope=="window" 且 tiles==0（当天没有任何户外快照）⇒ 该 true 不可采信`。**task-19 落地后这条检查的期望形态（正常的一天）**：`final_water.scope=="farm"` + `tiles>0` + `crops>0` + `dry==0` + `checks.watered_outdoor==true`（farm 口径注明来自 `farm.dryCrops`）；退回窗口口径时 `scope=="window"` **必须** `tiles>0`（否则 `watered_outdoor` 只能为 `false`/缺省）。 |
| B5 | `cross_day` 只判"日期不同" | **已关闭** |
| B6 | 0 步整天也能 VERIFIED | **收窄**：必须有"无活可做"证据，否则问题 |
| B7 | 日级 `failed_steps` 的解释项与它同源，可自洽洗账 | **开放**（仍靠 `leftover`/`no_unmet_stages` 兜） |
| B8 | `analyze-longrun.py` 同源同盲 | **开放**（§2 实测 0 条） |
| B9 | B6 的"无活可做"证据也是**自述** | **开放，但已不能单独骗过**：K2 现在必须先解决 B4b（伪造者把 `scope` 改成 `farm`+覆盖格数即可再骗过 ⇒ 本质仍开放） |
| B10 | （v3 新增）`watered_outdoor` 的**真值来源**本身不可验：`scope="farm"` + `tiles=32` + `dry=0` 也全是自述 | **开放**（B3 的实例；只有 task-19 的单测 + 真机外部证据能兜） |
| B11 | **（v4）真失败改分类**：格子没变/回执 ok 但世界没变，却被写成 `unreachable`（或 `tool_refused`） | **开放（本质不可判）**：把账目做自洽后两侧工具都 exit 0（`review-t72-relabel-clean`）。复核只能盯这几个位置：`day_end.stages[].unreachable`/`unreachable_tiles`；`blocked` 事件的 `reason`（真失败文案如「锄完不是 dirt」）；`brain/agentfarm/farmwork.py:554-568 is_unreachable()`（**自由文本**命中 `UNREACHABLE_HINTS` 也算不可达 ⇒ 回执文案可触发）；`farmwork.py:379-399` 的 `StepResult.failed/unreachable` 两属性；`longrun.py:2712` 的上界公式与 `:2751` 的 `unmet_leftover` 扣减。**真防线是 §5-A 的外部证据 + 分类代码本身可复核**，不是账本判据 |
| B12 | （v4，**已关闭** `9f554d7`）账本自抬 `*_bound` / 抬高 `attempted` 分母 | **已关闭**：自算 `max(5, floor(0.2×attempted))` + 分母与 `Σ stages.attempted` 交叉核对 ⇒ problem；负例 `tests/test_verify_run3.py:518-539` |
| B13 | （v4，**已关闭** `9f554d7`）扣了豁免却不写逐格坐标 | **已关闭**：`*_exempt > 0` 且 journal/账本坐标皆空 ⇒ problem「缺失≠通过」；负例 `tests/test_verify_run3.py:540-550` |
| B14 | （v4，**已关闭** `9f554d7`）两套豁免坐标重叠（重复扣减） | **已关闭**：坐标交集非空 ⇒ problem；负例 `tests/test_verify_run3.py:551-570`，且"不相交 + 带坐标仍绿"有正对照 `:571-578` |
| B15 | （v5，**已关闭** `2ce830b` + task-78）**`encircled` 抬高豁免上界的分母**：800 次被围住的格把 `attempted` 撑到 1000 ⇒ `bound = max(5, 0.2×1000) = 200` ⇒ 200 格真·不可达被"名义上 20% 以内"豁免，当天 `verified=true`（task-77 的 V5 账本，修复前 exit 0） | **已关闭，关闭方式 = 上界分母剔除被围格（`bound_basis = attempted − encircled`），不是新增闸门**：工具自算 `max(5, floor(0.2×bound_basis))`，账本 `bound_basis`/`*_bound` 更大 ⇒ problem；负例 `tests/test_verify_run3.py` 的 `test_encircled_steps_do_not_inflate_the_exemption_bound`（`:640`）/`test_bound_basis_field_is_honoured_when_consistent`（`:664`）；双侧读数见 §2.1、原文见 §9.5。**注意脑侧字段要等 task-78 落地**，落地前真机账本没有 `bound_basis` 时工具按 `attempted − encircled` 自算（更严，不会放过） |
| B16 | （v5，**开放**，pre-existing，**与 task-68 无关**）**0 阶段 / 0 动作 + `no_work` 理由 + `verified=true`**：账本写 `encircled` 一大把、`unreachable=0`、`stages=[]`、`ok_steps=0`，靠"无活可做"证据放行（task-77 的 V1 账本，两侧工具都 exit 0） | **开放**：控制组 V1'（完全不写 encircled/无该事件）判决**完全相同** ⇒ 根因是既有 B6/B9 一类盲区（"0 步不能自证做过事"只对**没有**无活可做证据的日子生效），**不是 task-68 引入**。要动它属于"改 `no_work` 放行口径"，与 `encircled` 无关 |
| B17 | （v5，**开放**，task-15 已知）**遮蔽**：同一阶段种类当天更早一轮 `leftover>0`（被围住的格留在那轮）、最后一轮 `leftover=0` ⇒ 日级按"最后一条"算 ⇒ 当天 `verified=true`（task-77 的 V2 账本，两侧工具都 exit 0） | **开放**：`stage_midway_leftover` 只留痕、不改结论（`9f554d7` 起也只在工具里给 info）。task-68 让命中概率上升（`encircled` 格不入 `blocked`、当天可换片继续），但**判据本身是 task-15 定的**，要收紧需单独裁定 |
| B18 | （v5，**已关闭** `2ce830b`）**stuck 翻篇洗白**：`day_end.stuck_flushed=true` 的一天却记 `verified=true`（用"睡过去翻篇"凑尾部连续天数） | **已关闭**：`stuck_flushed=true` 且 `verified` ⇒ problem；负例 `tests/test_verify_run3.py` 的 `test_stuck_flushed_day_must_not_be_verified`（`:679`）（`test_stuck_flush_day_is_reported_as_info`（`:691`）守 info 侧） |

| B19 | （v6，**打穿 = 开放**，`7c4ff68` 引入）**窗口内的 fatal 问题可以被"改 key"降级成 `history_problems`**：把该日 `day_start.day[1]`（季节）写成含 `]` 的字符串（例 `spring]x`）⇒ 问题前缀变 `[spring]x 11] …` ⇒ 窗口过滤用 `p[1:].split("]",1)[0]` 解析出 `spring`，与 `tail_names` 不匹配 ⇒ 被判"窗口之外"、`rc` 从 1 变 0、`VERIFIED` | **已关闭（v7，`c6d2a7a`，2026-10-15）**。修法：`_clean_label()` 生成标签时净化 `[`/`]`/换行/制表；`problem_day()` 按**已知日标签最长前缀匹配**；降级条件 `head and head in known_names and head not in tail_names` ⇒ **头部标签不属于任何已知日 ⇒ 一律 fatal**。三副本实测（`scratch/_t90_freeze.py` + `scratch/_t90_replay.py`）：old `rc 1` / **buggy `rc 0 VERIFIED`（洞）** / fixed `rc 1 needs_review`；用例 `tests/test_verify_run3.py::test_bracket_in_day_label_cannot_hide_an_in_window_problem` 在 buggy 上**确实红**（`AssertionError: True is not false`）⇒ 用例非空转。见 §12 |
| B20 | （v6，**开放 = 设计取舍，需 Lead 明示**）**窗口之外的系统性缺陷被一路放过**：27 天全程"浇水没做完" + 尾部 3 天全绿 ⇒ 新口径 `VERIFIED`（135 条 `history_problems`），旧口径 `needs_review` | **开放**：`scratch/review-t86-a6-systematic-27-bad-3-clean.jsonl`。要保留该口径，必须在 `docs/_run6-criteria.md` §2 与发布清单写死"验收只覆盖尾部 N 天，更早缺陷靠三源对账/人工"；否则给历史问题加门槛（数量/同因 ⇒ 至少不判 VERIFIED） |
| B21 | （v6，**开放**）`tools/analyze-longrun.py` **仍按整本账本**判红（run7：`VERIFIED: 4/3 天`、`退出码 1；有红 138 条`），而 `verify-run3.py` 按窗口判 `VERIFIED` ⇒ 两个工具对同一本账本**结论反向** | **开放（口径差异，不是 bug）**：发布物里必须注明口径，或给 `--json` 加 `caliber:"tail_window"`；否则外部读者会以为两者自相矛盾 |
| B22 | （v7 观测，**不是洗白通道**）**日标签重名**（两个会话停在同一游戏日 ⇒ 同一个 `key`）：窗口外那天的日级问题会因标签同时属于窗口内某天而被判 fatal | **方向是保守多报，不会漏报**（`scratch/_t90_survey.py` S5：谓词级 `[spring 15]` 与窗口内标签同名 ⇒ 降级=False；把坏日改成同名 ⇒ `rc 1` 且多出 6 条 problem）。修掉需要"按天序号而不是标签"归因，属结构性改造，本卡不改 |

## §5 那靠什么防（逐条标可执行性）

**A. 账本之外的外部证据（强，必须做）**

1. **存档真的落盘了**：`C:\Users\admin\AppData\Roaming\StardewValley\Saves\Wahaha_450799035\` 下 `Wahaha_450799035` 与 `SaveGameInfo` 的 **mtime/size 前进**（实测 2026/10/11 22:24:19、`3502298`/`25234` B，`_old` 备份 22:07:58）。run3 前后各 `Get-Item` 一次，要求 **每个游戏日至少一次 mtime 前进**。❌ 机器生成的账本不会让存档前进。注意：`tools\verify-landing.py` **不查**这项。
2. **SMAPI 日志里的世界级事件**：`C:\Users\admin\AppData\Roaming\StardewValley\ErrorLogs\SMAPI-latest.txt`，每行带 `[HH:mm:ss LEVEL]`。可用锚点（实测）：`[.. TRACE SMAPI] Synchronizing 'NewDay' task...`（每个跨日 ≥1 条）、`[.. TRACE game] SaveGame.Save() called.` / `completed without exceptions.`、`[.. TRACE AgentFarm Bridge] sleep：answerDialogueAction("Sleep_Yes")`。可执行：run3 时间窗内数 `NewDay` 与 `SaveGame.Save()` 条数 ≥ 天数。⚠️ 仍是同一台机器上的另一个文件。
3. **live 再观测对账**：run3 结束后**不要立刻 quit**，用桥 `/observe` 再取一次，把 `day/money/crops/stamina/location` 与最后一条 `day_end.final` 比。❌ 需要游戏仍在跑；写进 task-12 步骤。

**B. 跨工具交叉（中）**

4. `tools\analyze-longrun.py` 用**独立代码路径**复算事件→类别映射（能抓 `blocked_modal`、`no_blocking_modal=false` 这类"行为不像人"的线索）。⚠️ 同读一本账本，**对自洽伪造无效**。
5. **同源警告（必须写进验收单）**：`checks.watered_outdoor`、`final_water`（含 `scope`/`tiles`/`dry`）、`verified`、`checks.*`、`ended_reason`/`excuse` 全部由 longrun **自己**写；它们是"过程记录"，**不是独立见证**。任何"用 A 证明 B"的论证只要两端都在同一本 journal 里就不成立 —— B4b 只抓"自述与自己写的 `scope` 打架"，**不证明水真的浇过**。task-19 的正确性最终靠它的假世界单测（5 条）+ 真机窗外证据。

**C. 机器不可伪造的锚（建议加）**

6. journal 的 `day_start`/`day_end` 里记录 `liveness.worldSeq`（桥观测的单调世界序号）+ 要求跨日时显著前进。⚠️ 需改 brain + 口径；是"提高伪造成本"，不是"不可能伪造"。

**D. 实测有效的防线（v4，不是建议）**

7. **反空洞**（task-52 ⑥）：一天全是豁免格 + 0 步成功 + 自称 VERIFIED ⇒ 判红（`review-t72-vacuum-clean` 修复前后**都 exit 1**；problem 文案「自称 VERIFIED 但当天成功动作 0 步」＋「`checks.no_unmet_stages` 与自算不一致」）。⇒ 伪造者不能靠"把 0 成功的一天写成全豁免"过关。
8. **B11 的复核动作（账本层不可判，但必须留痕可查）**：拿 `day_end.stages[].unreachable_tiles` + `unreachable` journal 事件逐格对照 ——(a) 该格四邻在观测窗口里是否真的都不可站；(b) 同一天同阶段有没有 `blocked` 事件（"真失败被改写"的痕迹）；(c) `stage.attempted` 与 `ok/skipped/failed` 是否自洽。⚠️ (b) 只能抓"改了一半"的账本，**全删干净就查不出来** ⇒ 最终仍靠 §5-A 的三条外部证据。

## §6 对 `verify-run3.py` 的低成本加固建议 —— v4 状态（9/10/11 已由 Lead 在 `9f554d7` 落地）

1. ~~`finish` 一致（挡 K3）~~ → **已加固**。
2. ~~浇水互检（挡 K4）~~ → **已加固**。
3. ~~`t` 基本卫生~~ → **部分加固，且有意只作信息项**。
4. ~~跨日 = 恰好 +1 天~~ → **已加固**。
5. ~~0 步 VERIFIED 记 info~~ → **已改为"有证据才放行"**。
6. `worldSeq` 采样 → **未做**（Lead 有意；见 §5-C）。
7. ~~措辞 nit（一因两报）~~ → **已修**（`d43e75e`）。
8. **（v3）window 口径 0 覆盖不许 `watered_outdoor=true`** → **已加**（`:394-401`）。**待 Lead 拍板**的一点：这会改 `review-neg-K2` 的基线读数（exit 0 → exit 1）；若要把 K2 保留为"完全过关的伪造样本"，可用 `review-neg-K`（farm 口径）替代它的角色 —— 但我建议**保留这次加固**，因为 K2 原来的过关依赖的正是 task-19 明令禁止的字段组合。
9. **（v4）账本大幅放宽 `unreachable_bound`/`refused_bound`、或抬高 `attempted` 分母** → **已加固（`9f554d7`，task-71）**：工具自算 `attempted`（`day_end.attempted > Σ stages.attempted` ⇒ problem `:462-466`）与自算上界 `max(5, floor(0.2×attempted))`（账本 **大于** 自算 ⇒ problem `:468-475`/`:522-532`；**小于** 自算只记 info「更严」`→ 不误杀保守账本`）；负例 `tests/test_verify_run3.py:518-539`。
10. **（v4）扣了豁免却不写逐格坐标** → **已加固（`9f554d7`）**：`*_exempt > 0` 且 journal 逐格事件与 `day_end.*_tiles` 皆空 ⇒ problem「缺失≠通过」（`:486-490`/`:542-546`）；负例 `tests/test_verify_run3.py:540-550`。
11. **（v4）两套豁免互相掩护** → **已加固（`9f554d7`）**：解析两套逐格坐标取交集，非空 ⇒ problem（`:547-556`）；负例 `:551-570` + 正对照"不相交且带坐标仍绿"`:571-578`。
12. **（v4，判据关不掉）B11 分类造假**：建议最多做**启发式 info**（同阶段存在 `blocked` 事件而 `failed_steps==0` ⇒ info 提示人工核对），并把"本质不可判"写进 §5-D（已写）。**不要**把启发式升成 problem —— 会误杀"不可达格与真失败格恰好同阶段"的合法日。

## §7 建议写进 task-12 / 发布清单的验收单（外部证据）

1. run3 开始前记录存档 `Wahaha_450799035` 与 `SaveGameInfo` 的 `mtime/size`；结束后要求 **每个游戏日至少前进一次**。
2. 记录 run3 的墙钟窗口，在该窗口内 **SMAPI 日志**必须有 `Synchronizing 'NewDay'` × 天数、`SaveGame.Save() completed` × 天数、`AgentFarm Bridge sleep：answerDialogueAction("Sleep_Yes")` × 天数（缺一即当"没真跨日"）。
3. run3 结束、quit 前做一次 **live `/observe` 对账**：`day_key/money/crops/stamina/location` 与最后一条 `day_end.final` 相符。
4. 这三条之外，`verify-run3.py` 的 exit 0 只是"账本自洽"的**必要条件**，不是"跑通了"的充分条件。
5. **（v3）** task-19 落地后，除 `checks.watered_outdoor` 外**必须同时看 `final_water.scope`**：`scope="window"` 且覆盖 0 格时该字段不得为 `true`（工具已按此抓，见 B4b）。
6. **（v4）豁免日的附加核对**：某天出现 `day_end.unreachable`/`refused` > 0 时，验收人要额外核三件事（`9f554d7` 起工具会自动判红，但验收单上要写明口径）：①`unreachable_bound`/`refused_bound` 必须等于 `max(5, floor(0.2×attempted))`；②被豁免的**每一格**都能在 journal 里找到逐格坐标；③不可达与被拒两套坐标**交集为空**。任一条不满足 ⇒ 该天不算"合法豁免"，**不得**据此把 `no_unmet_stages` 当通过。

## §8 怎么复跑（v3 证据）

```powershell
$env:PYTHONUTF8="1"
$py="C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py scratch\_review_neg_gen.py          # 生成 A–K2 + G/H/I/J/P/Q/R/S
& $py scratch\_mk_k3_k4.py                # K3/K4 从 K 派生
& $py scratch\_mk_task11_modal_day.py     # 反向对照从 green 派生
& $py scratch\_review_matrix.py           # 29 本一把跑完；"--verbose" 追加逐条 problems/infos
```

期望（v3）：**exit 0 = 6 本**（green / G / I / K / P / S），**exit 1 = 23 本**（A/B/C/D/E/F/H/J/K2/K3/K4/Q/R + modal-day + 真机 run2/run1 + 彩排 + 7 本旧料/单日料），逐本与 §2 一致；`scratch\_review_matrix.py` 的 `EXPECT0` 集合需随之更新为上面 6 本（`K2` 移出）。

### §8.1 task-72 复跑（豁免三通道，双侧冻结副本）

```powershell
$env:PYTHONUTF8="1"
$py="C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py scratch\_t72_freeze_tool.py   # 冻结：已提交 HEAD 版 → _t72_tool_head.py；Lead 在制/修复版 → _t72_tool_wip.py（打印两侧 sha256）
& $py scratch\_t72_freeze2.py      # 冻结：9f554d7 版 → _t72_tool_fix.py（+ 该提交的 tests/test_verify_run3.py，592 行）
& $py scratch\_t72_when.py         # 闸门引入历史（哪些提交开始带这些判据）
& $py scratch\_t72_forge.py        # 生成 5 本"上界自洽"的隔离账本 review-t72-*.jsonl
# 逐本跑两侧冻结副本（原文输出留档 scratch\_t72b_{head,fix}_*.txt）
foreach ($t in @("head","fix")) { foreach ($f in @("bound-inflate","exempt-no-coords","overlap-two-sets","relabel-clean","vacuum-clean")) {
  & $py "scratch\_t72_tool_$t.py" --journal "scratch\review-t72-$f.jsonl" --days 1
  Write-Output "$t/$f exit=$LASTEXITCODE"
} }
& $py -m unittest tests.test_verify_run3   # task-71 的负例所在：Ran 34 / OK
```

期望（v4，读数见 §2.1）：`head`（修复前）= `bound-inflate`/`exempt-no-coords`/`overlap-two-sets`/`relabel-clean` **exit 0**、`vacuum-clean` exit 1；`fix`（`9f554d7`）= 前三本 **exit 1**、`relabel-clean` 仍 **exit 0**（B11 盲区）、`vacuum-clean` exit 1。冻结副本单个 ≈52 KB，**不入库**；账本（`*.jsonl`）与文本输出也被 `.gitignore` 的 `scratch/*`（例外 `!scratch/*.py`）排除 ⇒ **入库的只有这 4 个脚本**（`_t72_forge.py`/`_t72_freeze_tool.py`/`_t72_freeze2.py`/`_t72_when.py`），账本与 `scratch\_t72b_*.txt` 随时可用脚本重生成。

## §9 task-72 实测：豁免记账的三条洗白通道（已由 `9f554d7` 关闭）+ 一条开放盲区

**背景**：task-52（不可达豁免）与 task-63（游戏拒绝豁免）让"环境挡路"不再计入当天硬失败，代价是**多了一条洗白通道** —— 把失败写成"豁免"，`no_hard_failures`/`no_unmet_stages` 就都变成账本自述。task-54 时我用 6 本伪造账本打穿其中**三条账本层可判**的通道；Lead 的 **task-71（提交 `9f554d7`，只改 `tools/verify-run3.py` + `tests/test_verify_run3.py`）**把这三条堵上并用负例锁死。

### §9.1 双侧矩阵（复现命令见 §8.1；原文输出 `scratch\_t72b_{head,fix}_*.txt`）

| 通道 | 账本（`scratch/`） | 关键构造 | 修复前 HEAD（937 行 `6c0ac399…`） | 修复后 `9f554d7`（988 行 `a62a6e94…`） |
| --- | --- | --- | --- | --- |
| (c) 抬上界/抬分母 | `review-t72-bound-inflate.jsonl` | 42 格不可达、账本 `unreachable_bound=9999`（自算 10） | **exit 0 / VERIFIED** | **exit 1 / needs_review** |
| (e) 扣豁免不写坐标 | `review-t72-exempt-no-coords.jsonl` | `unreachable_exempt=3`、`unreachable_tiles=[]`、无逐格 journal | **exit 0 / VERIFIED** | **exit 1 / needs_review** |
| (f) 两套豁免重叠 | `review-t72-overlap-two-sets.jsonl` | 同 2 格同时进 `unreachable_tiles` 与 `refused_tiles` | **exit 0 / VERIFIED** | **exit 1 / needs_review** |
| (b) 分类造假 | `review-t72-relabel-clean.jsonl` | 4 条真失败（「锄完不是 dirt」）写成不可达、**账目全自洽** | exit 0 / VERIFIED | **exit 0 / VERIFIED（仍开放 = B11）** |
| 反空洞（防线） | `review-t72-vacuum-clean.jsonl` | 8 格全不可达 + 0 成功动作 + 自称 VERIFIED | exit 1 | exit 1 |
| 对照 | `scratch/journal-green.jsonl` | 正常绿账本 | exit 0 | exit 0 |

真机 `logs\longrun-3day-llm-run{2,3,5,6}.jsonl` 修复前后**都是 exit 1**（判决未变，输出 `scratch\_t72c_*.txt`）⇒ 这次加固不引入新假红。用 `_t54_forge.py` 那 6 本（上界写成 8、与自算不符）复跑同样得到"修复前 4 本 exit 0 / 修复后全 exit 1"，见 `scratch\_t72_head_review-t54-*.txt` 与 `scratch\_t72_wip_review-t54-*.txt`。

### §9.2 修复后的判红原文（逐字抄自工具输出）

- **(c)** 两套上界各报一条：
  - `[spring 10] 不可达豁免上界账本=9999 > 自算=10（attempted=50）⇒ 上界被放宽，可能把真失败洗成不可达`
  - `[spring 10] 被拒豁免上界账本=9999 > 自算=10（attempted=50）⇒ 上界被放宽，可能把真失败洗成「游戏拒绝」`
- **(e)** `[spring 10] 不可达豁免扣了 3 格却没写任何坐标（journal 无 unreachable 逐格事件、day_end.unreachable_tiles 也空 ⇒ 缺失≠通过）`
- **(f)** `[spring 10] 同一格同时进两套豁免：2 格（例 (50,14)、(51,14)）⇒ 可被重复扣减（unreachable + refused），必须人工核对坐标来源`
- **修复前**这三本都只有"信息项"、`结论：VERIFIED`，例：`[spring 10] 不可达（四邻都站不过去/A* 算不出路）账本=42、journal 自算=42 次/42 格、豁免上界 bound=9999（attempted=50）、实际扣除 exempt=42（task-52 政策：不计当天硬失败；本行只供复核）` ⇒ 说明工具当时**只是"展示"豁免，没有核对**。
- **反空洞防线**（修复前后都判红）：`[spring 10] 自称 VERIFIED 但当天成功动作 0 步（有阶段记录、ok 全 0）（0 步不能自证做过事；查 stage_no_target / no_work 分支）` + `[spring 10] checks.no_unmet_stages=True 与自算不一致（有目标阶段遗留 leftover=0 格，扣掉不可达豁免 8 + 锄不动豁免 0 后剩 0 格、当天成功动作 0；期望 False）`。

### §9.3 修补位置（`9f554d7`，行号按 988 行版；只动工具与工具单测两个文件）

1. **自算分母 + 自算上界**：`day_end.attempted` 与 `Σ stages[].attempted` 交叉核对（账本更大 ⇒ problem「抬高分母就能放宽 20% 上界 ⇒ 账目不可信」`:462-466`）；`bound_self = max(5, floor(0.2×attempted))`，账本 `unreachable_bound` **大于** 自算 ⇒ problem（`:468-475`）、**小于** ⇒ 只记 info「更严」（`:476-479`）；refused 侧镜像（`:522-532`）。⇒ 通道 (c) 关闭。
2. **豁免必须有逐格坐标**：`unreachable_exempt > 0` 且 journal 逐格事件 `self_tiles == 0` 且 `day_end.unreachable_tiles` 为空 ⇒ problem（`:486-490`）；refused 侧 `:542-546`。⇒ 通道 (e) 关闭。
3. **两套豁免不得互相掩护**：`overlap = (journal 坐标 ∪ 账本坐标)_unreachable ∩ (…)_refused`，非空 ⇒ problem 并打印样例坐标（`:547-556`）。⇒ 通道 (f) 关闭。
4. **负例锁死**（`tests/test_verify_run3.py`，592 行，sha256 `eb11c9b8…`）：`test_forged_large_unreachable_bound_is_problem` `:518`、`test_forged_large_refused_bound_is_problem` `:529`、`test_exemption_without_coordinates_is_problem` `:540`、`test_overlapping_exemption_tiles_is_problem` `:551`、正对照 `test_disjoint_exemptions_with_coordinates_stay_green` `:571`（不相交 + 带坐标仍绿）。**我亲跑** `python -m unittest tests.test_verify_run3` ⇒ **Ran 34 tests / OK**。

### §9.4 为什么 (b) 关不掉（= B11）

分类造假发生在**写入阶段**：`farmwork.is_unreachable()`（`brain/agentfarm/farmwork.py:554-568`）判定"不可达"的依据之一是**自由文本**命中 `UNREACHABLE_HINTS`（"四邻都站不过去"/"寻路无法到达"/"无法到达"/"A* 未算出路径"/"unreachable"），而 `StepResult.unreachable`（`:388-390`）与 `failed`（`:379`）是同一份 `code` 的两个投影。**只要伪造者把 `code` 写成 `unreachable`、坐标写齐、上界取自算值、不留下 `blocked` 事件**，账本里就没有任何自相矛盾之处 ⇒ 工具两侧都只能给 `VERIFIED`（`review-t72-relabel-clean` 实证）。这不是工具的缺陷，而是**判据的信息论上限**：判据只能读账本，无法读世界。复核动作见 §5-D；最终仍靠 §5-A 的三条外部证据 + 直接读分类代码。

### §9.5 task-79（v5）：V5 通道关闭的双侧实测

对象 = task-77 的 V5 账本 `scratch/review-t77-v5-encircled-inflates-unreachable-bound.jsonl`（构造：800 条 `encircled` journal 事件 + stage `clear_dead{attempted=800, encircled=800}` + `till_area{unreachable=200, unreachable_leftover=200}` + `unreachable_bound=refused_bound=200` + `verified=true`）。

| 工具 | 行数 / sha256 | 该账本 exit | 原文 |
| --- | --- | --- | --- |
| `8ceea87`（task-75 版；= 快照 `scratch\_t77_snap\tools\verify-run3.py`） | 995 / `960837CB…` | **0 / VERIFIED** | 只有 info：`被围住（encircled，四邻无落脚点）账本=800、journal 自算=800 格` |
| `2ce830b`（task-78 镜像） | 1051 / `FDB4E8D9…` | **1 / needs_review** | 两条 problem（逐字）：`[spring 10] 不可达豁免上界账本=200 > 自算=40（attempted=1000）⇒ 上界被放宽，可能把真失败洗成不可达`、`[spring 10] 被拒豁免上界账本=200 > 自算=40（bound_basis=200）⇒ 上界被放宽，可能把真失败洗成「游戏拒绝」` |

**关闭机制（逐字口径）**：分母 = `bound_basis = attempted − encircled = 1000 − 800 = 200` ⇒ 自算上界 `max(5, floor(0.2×200)) = 40`；账本写 200 > 40 ⇒ problem。**不是新增闸门**，而是把"被围住的格"从豁免额度里剔除（`encircled` 既不是"走不到"、也不是"干了没成"）。边界写法 W1（账本 `bound_basis` 抬高）/ W2 / W2'（把 bound 压到自算值再谎报）三条**也都 exit 1**（见 §2.1 末段）。

**同一批账本复查（不许谎报已修）**：V1（0 阶段 + `no_work` 理由 + `verified`）**两侧都 exit 0**（= B16 开放）、V2（遮蔽）**两侧都 exit 0**（= B17 开放）、`review-t72-relabel-clean`（B11）**两侧都 exit 0**（仍开放）；V3（诚实红）/V4（谎报）两侧都 exit 1；`journal-green` 0、`_t5x_vacuum`/run2/run3/run5/run6 各 1 且**问题条数逐本相同**（3/11/17/21/9）。

**复现**：`$env:PYTHONUTF8="1"; python scratch\_t77_forge.py`（重生成 V1–V5）→ `python scratch\_t79_replay.py`（两侧逐本对比）→ `python scratch\_t79_v5edge.py`（三条边界写法）。本次验收**未改任何工具/测试**：`tools\verify-run3.py` 与 `tests\test_verify_run3.py` 全程与 `2ce830b` 一致（`tests.test_verify_run3` = **Ran 41 / OK**）。

## §10 run6 归因更正：`unreachable_within_bound=false` 不是"上界卡住合法豁免"

Lead 原倾向是"密农场下上界公式偏小 + 42 格确实无落脚点"。逐字段核对后**只有后半句成立**：

- run6 账本（`logs\longrun-3day-llm-run6.jsonl`，143 行）：`unreachable` 84 条、`unreachable_stage` 8 条、`unreachable_summary` 2 条；`day_start/day_end` 各 2（summer 4 跑了两轮），`finish={code:1, verified_streak:0, actions:95, minutes:0.62, stages_seen:["clear_dead","till_area"], no_unmet_stages:false, unmet_days:["1年 summer 4日","1年 summer 4日"]}`。
- 工具 info 行口径（两轮相同）：`账本=42、journal 自算=42 次/42 格、豁免上界 bound=8（attempted=42）、实际扣除 exempt=8` ⇒ **42 格全被判"四邻都站不过去"（`field_ne`）**，而 `max(5, floor(0.2×42)) = 8` ⇒ 42 ≫ 8（超界 5.25 倍）。**就算把上界公式放大到 42 也仍然要问"这 42 格为什么都没有落脚点"** ⇒ 失败与上界无关。
- 每类阶段最后一条 leftover 合计 **54 格**，`checks.no_unmet_stages=false`、`ended_by=stuck`、`verified=false`、37.2 s 就退出 ⇒ **工具如实判红，不是误判**；`finish` 自述 `code=1/verified_streak=0` 与之一致。
- 根因链（写给 run7 复盘）：作业区选择把一整天花在"无落脚点簇"上（task-67 已修采种死锁、task-68 在修可达性与上界口径）。⇒ 验收单上写"**run6 失败 = 不可达格数远超上界 + 作业区选择**"，**不要**写"上界公式偏小导致合法豁免被卡住"。

## §11 task-86 实测：尾部达标窗口口径（`7c4ff68`）—— 新旧差别 / 打穿清单 / 剩余盲区

**新口径（`tools/verify-run3.py` @`7c4ff68`，1139 行）**

- `ok = (尾部连续 N 天 verified) and (窗口内问题为空)`；`streak = days[-target_days:]` 若全满足 `ended_by=="sleep" and cross_day and verified is True`（`:894-899`，在降级**之前**算，不受影响）。
- `if streak >= target_days:` ⇒ `tail_names = {d["key"] for d in days[-streak:]}`（`:911`）；逐条问题 `head = p[1:].split("]",1)[0] if p.startswith("[") else ""`，`head` 命中 `tail_names` ⇒ 保留，否则进 `history_problems`（`:914-916`）；`problems = kept`（`:919`）。`history_problems` 不参与 rc。
- `streak < target_days` ⇒ **整段跳过**（不降级）。不带 `[day]` 前缀的全局问题（journal 坏行、`mod_version_mismatch`、`finish` 自洽/同向）在降级**之后**追加（`:996-1027`）⇒ 结构上永不被降级。
- `--json` 新增 `history_problems`（`:1072`）；人类输出多一段"历史问题（达标窗口**之外**的日子，不影响结论，共 N 条）"（`:1123-1127`）。

**两侧并排（78 本既有账本，`scratch/_t86_side.py --days 3`）**

| 类别 | 旧（`7c4ff68^`，1109 行 LF sha256 `7532E783…`） | 新（`7c4ff68`，1139 行 sha256 `3573A397…`） |
| --- | --- | --- |
| `logs/longrun-3day-llm-run7.jsonl` | rc 1 / 9 问题 / needs_review | **rc 0 / 0 问题 / 9 history / streak 3 / VERIFIED** |
| 其余 77 本（含 green、neg-A..Q、K/K2/K3/K4、t54/t72/t77/t79/t81 全系列） | — | **判决、问题数逐字不变** |
| `--days 5` | — | **零本改变**（run7 `streak(3) < 5` ⇒ 不降级） |

run7 的 9 条 history 原文（summer 3×2、summer 5×2、summer 6×5）见 `docs\_review-caliber-2026-10-15.md` §2；run7 本体读数：1230 行 / 7 天 / `finish{code:0,streak:3,actions:683,minutes:25.2}`，尾部 summer 7/8/9。

**打穿 / 未打穿（`scratch/_t86_adv.py` → `scratch/review-t86-*.jsonl`）**

| 变体 | 旧 rc | 新 rc | 结论 |
| --- | --- | --- | --- |
| A1 尾部 3 绿 + 前 5 坏 | 1 | 0（25 history） | 设计允许；坏日逐条列出 |
| A6 **27 坏 + 3 绿（同因系统性）** | 1 | **0（135 history）** | **B20：会一路放过**（需 Lead 明示取舍） |
| A2 窗口内中间日账目自相矛盾 | 1 | 1 | 窗口内问题仍 fatal ✅ |
| A3 run 停在坏的一天 | 1 | 1（streak 0 / history 0） | 窗口没打满不降级 ✅ |
| A4a 窗口内矛盾（正常标签，对照） | 1 | 1 | ✅ |
| A4b 同 A4a，仅 day 标签改 `spring]x` | 1 | **0（该问题进 history）** | **B19：打穿** |
| A5 全局问题（早期 `bridge_down`）+ 3 绿窗口 | 1 | 1（25 条降级、全局那条保留） | 全局问题永不降级 ✅ |

**三源对账 run7（只读，`scratch/_t45_three_source.py`）**：6 次跨日全部恰好 +1（summer 3→4 / 4→5 / 5→6 / 7→8 / 8→9 / 9→10），其中 5 次与 SMAPI `Synchronizing 'NewDay' task` + `SaveGame.Save() completed` 逐条配对（`23:00:00` / `23:01:11` / `23:06:57` / `23:10:57` / `23:15:42` / `23:17:00`），summer 6 是 `stuck` 翻篇（info）；存档主文件 3648782 B @ `23:33:11.539`（`_old` 3614652 B @ `23:18:27`）⇒ 前进。**唯一 problem**：存档比账本收尾新 1 天（存档 summer 11 / 账本 summer 10）—— 原因是 SMAPI 在 `23:18:27`（L8513/L8521）与 `23:33:11`（L8525/L8532）还各有一次 NewDay+Save，而 journal 在 `23:18:29` 已 `finish` 停写 ⇒ **不是账本造假**，是"跑批窗口 < 游戏会话"；建议收工前退出游戏，或有 `finish` 时把该检查降 info（NIT-5）。SMAPI 源（`SMAPI-latest.txt` 630353 B / 8533 行 / mtime `2026-10-14 23:33:13`）仍是 run7 会话，只读副本 `scratch/_t86_smapi_run7_live.txt` sha256 `0782B2A1…`；**请求冻结为 `logs/run7-smapi-window.txt`**；无 run7 的 start/end 快照 ⇒ 窗口 delta 未判（info）。

**复跑命令**

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"
& $py scratch\_t86_freeze.py               # 先重生成两侧冻结副本（不入库）
& $py scratch\_t86_side.py --days 3        # 两侧并排 → scratch\_t86_side_d3.txt
& $py scratch\_t86_adv.py                 # A1/A2/A3/A4a/A4b/A5/A6 → scratch\_t86_adv_out.txt
& $py scratch\_t86_tool_old.py --journal scratch\review-t86-a4b-inwindow-contradiction-injected-key.jsonl --days 3   # rc 1
& $py scratch\_t86_tool_new.py --journal scratch\review-t86-a4b-inwindow-contradiction-injected-key.jsonl --days 3   # rc 0 / VERIFIED
& $py scratch\_t45_three_source.py --ledger logs\longrun-3day-llm-run7.jsonl --smapi scratch\_t86_smapi_run7_live.txt --date 2026-10-14 --snapshots scratch\_t86_no_such_snapshots.jsonl --baseline logs\run7-baseline.json
python -m unittest tests.test_verify_run3   # Ran 44 / OK
```

## §12 task-90 实测：B19 关闭的独立复验 + 同类洞普查（2026-10-15）

**三副本**（`scratch/_t90_freeze.py` 用 `git show <rev>:tools/verify-run3.py` 重生成；大文件不入库）

| 副本 | 来源 | 行数 | sha256（前 16） |
| --- | --- | --- | --- |
| `scratch/_t90_tool_old.py` | `7c4ff68^`（口径变更之前） | 1109 | `7532E7836F75417E` |
| `scratch/_t90_tool_buggy.py` | `7c4ff68`（尾部窗口口径，带 B19 洞） | 1139 | `3573A39700B9BDD3` |
| `scratch/_t90_tool_fixed.py` | `c6d2a7a`（修复；= 仓库现行 `tools/verify-run3.py`，逐字节相同 `636FD5018C08F297`） | 1173 | `636FD5018C08F297` |

**同输入三判决（`scratch/_t90_replay.py`，A4b = 窗口内矛盾 + day 标签 `spring]x`）**

| 账本 | old | buggy | fixed |
| --- | --- | --- | --- |
| `review-t86-a4b-inwindow-contradiction-injected-key.jsonl` | rc 1 / 1 problem / 0 history | **rc 0 / VERIFIED / 0 problem / 1 history（洞）** | **rc 1 / needs_review / 1 problem / 0 history（关上）** |
| `review-t86-a4a-…-normal-key.jsonl`（对照） | rc 1 / 1 / 0 | rc 1 / 1 / 0 | rc 1 / 1 / 0 |
| A1 / A5 / A6（窗口外降级的设计行为） | 见 §11 | buggy == fixed 逐字相同 | 同左 |

固定版把注入标签**净化**成 `springx 11`（`_clean_label`），它属于已知日、且是窗口内那天 ⇒ 问题留 fatal。

**用例非空转（`scratch/_t90_nonvacuous.py`：把 `tests/test_verify_run3.py` 的 `vr` 换成冻结副本再跑那两条新用例）**

| 副本 | `test_bracket_in_day_label_cannot_hide_an_in_window_problem` | `test_unknown_problem_day_label_is_never_demoted` |
| --- | --- | --- |
| old | FAIL（`KeyError: 'history_problems'`，旧版没有该键） | FAIL（旧版没有 `problem_day`） |
| buggy | **FAIL：`AssertionError: True is not false : 窗口内的问题带 \`]\` 标签也必须 fatal`** | FAIL |
| fixed | PASS | PASS |

⇒ 新用例**确实钉住了这条回归**（不是空转），且只在修复版上通过。

**同类洞普查（`scratch/_t90_survey.py`）**

- 全工具 `split(` / `[1:]` / `rsplit(` 只有 **1 处**：`problem_day()` 的 fallback `text[1:].split("]", 1)[0]`（修前是窗口过滤的唯一解析点）。工具里**没有任何正则**（`re.` 零命中）。
- **兜底分支间谍**：把 `problem_day` 包一层统计，跑 `scratch/*.jsonl` + `logs/*.jsonl` 共 **85 本 / 170 次 `report()`** ⇒ `problem_day` 调用 **609 次**：**最长前缀命中 606 次、走 fallback 0 次**、其余 3 次是不带 `[` 前缀的全局问题（`head=""` ⇒ fatal）。⇒ 那个会截断的分支对**工具自产问题**不可达（问题前缀永远是 `name = d["key"]`，而 `key` 已被 `_clean_label` 净化、必属已知日集合）。
- **脏标签矩阵**（窗口内那天：前 3 天真失败 + 后 3 天干净 ⇒ `streak=3`、窗口=后 3 天；把中间那天改成"自称达标但 `stage leftover=2` 与 `checks.no_unmet_stages=true` 矛盾"）：
  | 标签 | 净化后 key | 判决 |
  | --- | --- | --- |
  | `spring` | `spring 14` | rc 1 / 1 problem / 15 history |
  | `spring]x` | `springx 14` | rc 1 / 1 / 15 |
  | `spring\n14` | `spring14 14` | rc 1 / 1 / 15 |
  | `sp[ring\t14` | `spring14 14` | rc 1 / 1 / 15 |
  | `""` | `? 14` | rc 1 / 1 / 15 |
  ⇒ 窗口外那 15 条照旧降级、窗口内这条**任何脏标签都降不下去**。
- **重名方向性（B22）**：谓词级 `[spring 15]`（标签与窗口内某天同名）⇒ 降级=False（保守保留 fatal）；把窗口外坏日的日号也改成窗口内那天的日号（真同名）⇒ `rc 1`、`#problem=6`、`#history=10` ⇒ **只会多报，不会漏报**。
- 其余"从文本解析结构化字段"的站点（逐条看过，**都不是分隔符截断**）：`tools/verify-run3.py:221` / `:765` / `:787` 对 `ended_reason`/`reason` 做 `startswith("no_work"/"night"/"stamina"/"no_water")` 白名单；`:321` 把 `reason/note/tile/tiles` 拼成 blob 后按 `_UNREACH_MARKS` 子串计数；`:1016` 数非空行。这些属**信任账本自述**类（B11/B16/B20 一线），要改是口径问题、不是解析 bug。

**回归读数（task-90 当时的主树）**

- `py_compile -W error::SyntaxWarning tools\verify-run3.py tests\test_verify_run3.py` ⇒ exit 0。
- `python -m unittest tests.test_verify_run3` ⇒ **Ran 46 / OK**。
- `python -m unittest discover -s tests` ⇒ **Ran 550 / FAILED (failures=1)**；唯一红为 `tests/test_analyze_longrun.py::TestEventMappingDrift::test_event_buckets_cover_every_brain_journal_name`，断言 `['day_end','day_start','finish','surplus_sell','surplus_sell_skip'] != ['day_end','day_start','finish']` —— `brain/agentfarm/farmwork.py:67`（`surplus_sell_plan`）与 `:810`（`surplus_sell_skip`）已在（dev-coder task-55 在制），而 `tools/analyze-longrun.py` 的 `EVENT_BUCKETS` 还没跟上（log-analyst task-88 在制）⇒ **归属 task-55/task-88 的跨卡集成缺口，不计入 task-90**。
- 85 本三副本并排（`scratch/_t90_side.py 3` → `scratch/_t90_side_d3.txt`）：**`buggy`↔`fixed` 只有 B19 那 1 本不同**；`old`↔`buggy` 不同 5 本 = run7（口径变更的设计行为）+ 我自造的 A1/A4b/A5/A6（同样由口径变更解释）。run7 在 buggy/fixed 上逐字相同（rc 0 / 0 problem / 9 history / streak 3 / VERIFIED）。

**NIT-5 处置建议（不动工具，报 Lead）**：把"存档比账本收尾新 1 天"在**账本带 `finish`** 时降为 **info**（附"跑批窗口 < 游戏会话"的解释），仅在**无 `finish`**（跑批被中断/崩溃，账本没跑完）或**相差 ≥2 天**时判 problem。理由：run7 的存档链证明游戏在我们 `finish` 之后又正常落了两次盘，`journal` 已停写 ⇒ 这是"跑批窗口短于游戏会话"的**常见产物**，不是账本缺陷；而"无 `finish`"才是真正需要人工确认的情形。落地位置：`tools/verify-run3.py` 存档比对段（`d.get("finish")` 判空 + gap 判断）；本次不改。

**复跑命令**

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"
& $py scratch\_t90_freeze.py                 # 三副本（old/buggy/fixed）→ scratch/
& $py scratch\_t90_replay.py                 # 7 本伪造账本 × 三副本并排 → scratch\_t90_replay.txt
& $py scratch\_t90_nonvacuous.py             # 把测试的 vr 换成三副本跑两条新用例 → scratch\_t90_nonvacuous.txt
& $py scratch\_t90_survey.py                 # 脏标签 / 重名 / 兜底分支普查 → scratch\_t90_survey.txt
& $py scratch\_t90_side.py 3                 # 85 本三副本并排 → scratch\_t90_side_d3.txt
& $py -m unittest tests.test_verify_run3     # Ran 46 / OK
```

