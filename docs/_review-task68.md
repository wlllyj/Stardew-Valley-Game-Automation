# task-77 独立验收：task-68（`encircled`/`frontier_clear`）＋ task-75（工具接住 encircled）

验收人：deputy-lead ｜ 日期：2026-10-14 晚 ｜ 判定：**PASS-WITH-NITS（无必修项；两条建议在 0.7.26 冻结前决定）**

> 卡面 B5 的字面标准（"伪造 `encircled` 很大 + `unreachable=0` + 当天 0 动作却 `verified=true`，看被哪条既有闸门拦下；一条都拦不住就是真缺陷"）**确实没拦住**（见 §3.5 V1）——但控制组证明原因是**既有**盲区（"0 阶段 + `no_work` 理由 ⇒ 接受"），`encircled` 字段对判决零影响；与 task-68 直接相关的新洞是 V5（`encircled` 步数抬高不可达豁免上界的分母），见 NIT-1。两条都写清楚了，请 Lead 定夺是否升级为必修。

---

## §1 基线

### 1.1 被验对象与范围

| 卡 | 提交 | `--stat` | 我核对的方式 |
|---|---|---|---|
| task-68 | `ea3541b`（10-14 22:09） | `brain/agentfarm/farmwork.py` +194、`brain/agentfarm/longrun.py` +189、`tests/test_farmwork.py` +85、`tests/test_longrun.py` +215（4 文件 +651/−32） | `git show --stat` + `git show --numstat` |
| task-75 | `8ceea87`（22:13） | `tools/verify-run3.py` +63、`tests/test_verify_run3.py` +49、`tools/_note-0726.txt` +1（3 文件 +113） | 同上 |

**夹带检查 ✅**：两个提交对 `mod/AgentFarm.Bridge/manifest.json`、`brain/agentfarm/bridge.py`、`docs/00-开发日志.md`、`logs/`、`scratch/`（产线部分）的 `--numstat` 计数均为 0。`tools/_note-0726.txt` 是 Lead 自己的便条（1 行），不属产线夹带。

**版本 ✅**：`manifest.json` = `0.7.25`、`brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.25"` ⇒ 两提交都**未 bump**（符合卡面）。

### 1.2 我跑的对象＝干净快照（避开 task-73 在制）

开工时 HEAD = `8ceea87`，工作树有 ` M brain/agentfarm/longrun.py`（dev-coder 的 task-73 在制）。为免在制污染，我用
`git archive --format=tar -o scratch\_t77_snap.tar 8ceea87` + `tar -xf … -C scratch\_t77_snap` 建了**干净快照**（`scratch/` 被 gitignore，不干扰仓库），所有读数与实验都在快照里跑。

快照 SHA256 前 16（= `8ceea87` 内容）：

| 文件 | SHA256(16) |
|---|---|
| `brain/agentfarm/farmwork.py` | `059A9CDE997592AC` |
| `brain/agentfarm/longrun.py` | `D475F5221BB0B07F` |
| `tests/test_farmwork.py` | `5EA376884401F77A` |
| `tests/test_longrun.py` | `D033D9B2177ABD30` |
| `tests/test_verify_run3.py` | `01F4E2DC3B645A81` |
| `tools/verify-run3.py` | `960837CBDD7C710F`（与主树同文件哈希相同） |

（快照的 `.py` 行尾被 `git archive` 规范化成 LF —— 主树同名文件 CRLF=2516/0，属导出伪影，内容一致。）

### 1.3 读数（我亲跑）

| 命令 | 结果 |
|---|---|
| 快照 `python -m unittest tests.test_farmwork tests.test_longrun` | **Ran 215 / OK** ✅（与作者自报一致） |
| 快照 `python -m unittest tests.test_verify_run3` | **Ran 37 / OK** ✅（与作者自报一致） |
| 快照 `python -m unittest discover -s tests` | **Ran 490 / FAILED (failures=2, errors=3, skipped=7)** |
| 主工作树 `… discover -s tests` | **Ran 496 / FAILED (failures=2)** |
| 快照 `py_compile`（brain/agentfarm + tests 全量） | exit 0 |

**与卡面基线的差异（如实报告，NIT-6）**：

* 卡面说"全量应 **496** 测试 / **1** 红（`test_analyze_longrun.TestEventMappingDrift`，归 task-76）"。实测主树是 **496 / 2 红**：除漂移那条外，还有
  `tests/test_longrun.py::TestDiscipline::test_sleep_intent_is_vetoed_while_work_remains` —— 它在快照（= `8ceea87`）里**不红** ⇒ 是 dev-coder 的 **task-73 在制**（`stuck_flush`）引入的，与 task-68/75 无关，但卡面基线数字要更正。
* 快照的全量多出 5 条红，全是 `test_analyze_longrun`（ERROR ×3 = `TestSyntheticLedgers.test_fallback_ledger_is_flagged`/`test_green_day_reports_nothing`/`test_leftover_but_verified_is_flagged`；FAIL ×2 = `TestCliContract.test_json_mode_is_parseable` + `TestEventMappingDrift`）。逐条查过：`FileNotFoundError: …\_t77_snap\scratch\_ledger_green.jsonl` ⇒ **复制品伪影**（这些夹具在 `scratch/` 里被 gitignore，仓库快照没有）。**结论：全量读数要用主树跑**，快照只用于单测/实验。

### 1.4 收尾时的工作树（供 Lead 判断并发）

HEAD 已前进到 `24dc16e`（`task-73: stuck 日有界翻篇（stuck_flush 绕过 sleep_guard，但仍如实记 stuck/不 VERIFIED）`，其前 `ca4e440` = 0.7.26 发布计划）。工作树在制（**均非我范围**）：` M docs/_release-0.7.26.md`、` M tests/test_analyze_longrun.py`、` M tools/analyze-longrun.py`（log-analyst 的 task-76，+160/+327）。我自己只新增 `docs/_review-task68.md` + `scratch/_t77_{a,forge,regress}.py`（+快照目录，gitignored）。

---

## §2 A 段：范围 / 读数 / 账本回归

* **A1 范围与夹带 ✅**：见 §1.1。
* **A2 三条单测读数 ✅ 但基线数字要更正**：`test_farmwork`+`test_longrun` = 215 OK；`test_verify_run3` = 37 OK；全量见 §1.3（主树 496/2 红 + 快照 490/5 红的伪影解释）。
* **A3 账本回归：与 task-75 之前逐字一致 ✅ 7/7**。方法：用**两个工具**跑同一批账本——旧 = `scratch\_t72_tool_fix.py`（= `9f554d7:tools/verify-run3.py`，task-75 之前），新 = 快照 `tools/verify-run3.py`（`8ceea87`），比较**退出码 + 「问题：」块逐字**（信息项允许因 task-68 新 info 增加）。脚本 `scratch/_t77_regress.py`。

| 账本 | `--days` | 旧 exit / 新 exit | 问题数 | 结论 |
|---|---|---|---|---|
| `scratch/journal-green.jsonl` | 3 | 0 / 0 | 0 → 0 | 一致 ✅ |
| `scratch/_t5x_vacuum.jsonl`（Lead 的） | 1 | 1 / 1 | 3 → 3 | 一致 ✅ |
| `scratch/review-t54-vacuum-all-unreachable.jsonl` | 1 | 1 / 1 | 4 → 4 | 一致 ✅ |
| `logs/longrun-3day-llm-run2.jsonl` | 3 | 1 / 1 | 11 → 11 | 一致 ✅ |
| `logs/longrun-3day-llm-run3.jsonl` | 3 | 1 / 1 | 17 → 17 | 一致 ✅ |
| `logs/longrun-3day-llm-run5.jsonl` | 3 | 1 / 1 | 21 → 21 | 一致 ✅ |
| `logs/longrun-3day-llm-run6.jsonl` | 3 | 1 / 1 | 9 → 9 | 一致 ✅ |

**⇒ task-75 没有新假红/假绿，`encircled`/`frontier_clear`/`clear_neighbor` 只进 info。**

---

## §3 B 段：对抗实验

实验脚本（都在 `scratch/`，只读生产代码）：
`_t77_a.py`（分类 + 日级 + 零动作 + 次日重试）、`_t77_forge.py`（伪造账本矩阵）、`_t77_regress.py`（A3）。运行：`$env:PYTHONUTF8="1"; python scratch\_t77_a.py`。

### 3.1 encircled 是怎么判出来的；"真能清却判 encircled"可行吗

`farmwork.py` 的分界（快照行号）：

* `_openable_neighbours(obs, tile, skip)` `:971-996`：候选 = 四邻里 `kind ∈ FRONTIER_KINDS`、无 crop、**且 `_standable_near(obs, n)` 为真**（`:961-969`：邻居 `tv is None`（未观测）**也算可站**）。
* `open_way(tile)` `:998-1036`：`for _i in range(MAX_OPEN_ACTIONS=4)`（`:197`）先试 `stand_next_to`，再取候选清一格；**候选空时**：`_standable_near(obs, tile)` 为假 ⇒ `"encircled"`（`:204 ENCIRCLED_CODE`），为真 ⇒ `"exhausted"`（⇒ `unreachable`）。循环 4 次仍站不到 ⇒ `"exhausted"`。

**攻击构造 P1a（我亲跑，快照）**：目标 `(62,10)`，围绕它铺满 5×5 的 `kind="weed", standable=false` 观测（**这些格子其实都是可清的杂草**），玩家在块外 ⇒

```
code='encircled' ok=False stood=False
reason: 四邻被不可清障物占住（树/桩/大石一类；2 层内没有「可站+可清」的突破口）⇒ 归 encircled：…
use_tool 调用次数: 0
```

⇒ **判据只依赖 `tiles[].standable` 的自述 + 1 层前瞻，不要求"至少挥过一次工具"，也不检查 `standable` 与 `kind` 是否自相矛盾**；reason 文案会把"四邻是可清杂草"写成"树/桩/大石"（**NIT-2**）。也就是说"真能清、只是今天没干成"的格子**可以被标成 `encircled`**（不掉进 `unreachable` 计数）。

对照（作者同款形态）：四邻有落脚点、只是清不动 ⇒ 走 `exhausted` ⇒ `unreachable`（`test_open_way_is_bounded_then_still_unreachable`：`len(w.calls)==1`、reason 含"上限 4 次"）。**所以两类的分界是"四邻有没有落脚点"，不是"干不干得动"。**

### 3.2 这种形态能不能拿到 `verified=true`？（真机代码路径）

用快照的 `EncircledWorld`（目标格被树围住）跑**完整一天**（P2a）：

```
ended_by/reason: 'stuck', "stuck:连续 3 轮世界没有任何变化（最后意图：['clear_dead']；策略说有进展：False）；守卫仍说还有活：…"
checks: no_hard_failures=True, no_unmet_stages=False, unreachable_within_bound=True,
        refused_within_bound=True, crops_watered=True, watered_outdoor=True, day_justified=False
verified=False   ok_steps=0   unreachable=0   encircled=1   unreachable_exempt=0
stages: [(attempted=1, engaged=0, leftover=1, encircled=1, unreachable=0) ×3]
encircled 格在 self.blocked 里吗: False
```

**结论：拿不到。** 被围住的格留在 `leftover` ⇒ 日级 `no_unmet_stages=False` ⇒ 当天诚实红。方向是对的：`encircled` 既不进豁免分子，也不能单独把一天洗成达标。

### 3.3 零动作收工（run6 的 19 秒 / 0 动作）

* `_frontier_clear` **真的产生动作 ✅**（P2c）：目标格被 `ui_modal` 挡路 + 农场里有可达杂草 ⇒
  `frontier_clear{tile:[70,10], acted:true, attempt:1}`，杂草**真的从世界消失**；`FRONTIER_CLEAR_MAX=20`。
* 仍可 0 动作收尾的路径（都诚实，无洗白）：
  1. **没有任何候选**（全农场没有"可清 + 够得着 + 不在 `encircled_day`"的格）⇒ `cands` 空 ⇒ 不硬造动作。P2d 实测：`frontier_clear` 0 条、`ok_steps=0`、`ended_reason='no_work:确实找不到可做的活…'`、`no_unmet_stages=False`、`verified=False` ✅。
  2. **≤3 个候选全都清不掉**（每次 `s.ok` 为假）⇒ 同样 0 动作，但 journal 留 `frontier_clear{acted:false}` 证据。
  3. `frontier_clears` 达 20 上限后停手（那天已经有 20 次真动作）。
* 行号：`longrun.py:1459-1512 _frontier_clear`（候选空 ⇒ `return False`）；调用点 `:2766`（plot-None 分支，**且要求 `work_reasons` 非空**）与 `:2910`（`idle_rounds>=3` 分支）。

### 3.4 次日重试 / 证据链

* **次日重试 ✅**：`_mark_blocked` 的 encircled 分支（`longrun.py:1818-1831`）**只**做 `self.encircled_day.add(key)` + journal `encircled`，**不写 `self.blocked`**、**不进 `unreachable_day`**；`encircled_day` 每天在 `_run_day` 开头重置。P2b 实测：连跑两天，两天各 `encircled=1`（各自重新尝试），末态 `self.blocked == {}` ⇒ 不永久封格、次日重试成立。
* **NIT-3**：`encircled_day` 只被 `_frontier_clear`（`:1477`）查询；**stage/plot 路径不看它** ⇒ 同一天同一格会被反复选中（P2a 实测 3 条 stage 记录 / 3 次 `encircled` 事件）。卡面"当天不再试"只在 frontier 层成立；当天真正的止损靠 `idle_rounds>=3` 与每格 attempt 配额。
* **证据链 ✅**：`StepResult.opened` 是独立字段（`farmwork.py:402-403`；`clear()` 里 `r.opened = list(cleared)`，注释明说"`after` 在动作循环里会被逐格观测覆盖，开路证据要留住"）⇒ 不被覆盖，`as_dict()` 另出 `clear_neighbor`。日级 `encircled` = `self.encircled_day ∪ Σ stages[].encircled_tiles`（`longrun.py:3028-3036`，集合去重后 `rep.encircled = len(enc_day)`）⇒ **不是 stage 简单求和** ✅。但**伪造成本低**：账本字段 + journal 事件照抄即可，工具对二者只记 info（见下）。

### 3.5 B5：伪造账本矩阵（工具 = 快照 `8ceea87`）

命令：`python scratch\_t77_snap\tools\verify-run3.py --journal <本> --days 1`（生成器 `scratch/_t77_forge.py`）

| 变体（`scratch/review-t77-*.jsonl`） | 构造 | exit | 判红/信息原文（节选） |
|---|---|---|---|
| **V1** `v1-encircled-no-work-verified` | `encircled=5`、`unreachable=0`、`stages=[]`、`ok_steps=0`、`verified=true`、`ended_reason="no_work:…"`（+5 条 encircled journal） | **0（VERIFIED）** | 只有 info：`被围住…账本=5、journal 自算=5 格` |
| **V1'** `v1c-control-no-encircled` | 同 V1，但不写 encircled 字段/事件 | **0** | 唯一 info：`当天 0 个阶段且自称 VERIFIED，但有"无活可做"证据（no_work:…）⇒ 接受` |
| **V2** `v2-encircled-masked-by-later-clean-stage` | encircled 格在**更早**的 `clear_area`（leftover=1）里，最后一轮 `clear_area` 干净；`verified=true` | **0** | info：`阶段 clear_area 当天共 2 条记录：更早一轮 leftover=1、最后一轮 0 ⇒ 按日级口径以最后一轮为准（遮蔽已显式列出）` |
| **V3** `v3-encircled-leftover-honest-red` | 同一格留在 leftover + `no_unmet_stages=false`/`verified=false` | **1** ✅ | `checks.no_unmet_stages=false（有阶段后置条件未成立；自算 leftover=1 格）` |
| **V4** `v4-encircled-lie-no-unmet` | 同 V3 但谎报 `no_unmet_stages=true`/`verified=true` | **1** ✅ | `自称 VERIFIED 但当天成功动作 0 步` + `checks.no_unmet_stages=True 与自算不一致（…剩 1 格）` |
| **V5** `v5-encircled-inflates-unreachable-bound` | 800 次 encircled 尝试（计入 `attempted`）+ 200 格真·不可达（`unreachable_leftover=200`、`bound=200`、`ok_steps=1`、`verified=true`） | **0（VERIFIED）** | info：`被围住…账本=800、journal 自算=800 格` |

**结论（回答卡面 B5）**：

1. **卡面点名的 V1 确实一条闸门都拦不住** —— 但 **V1'（控制组，无 encircled）判决完全相同**⇒ 根因是**既有**盲区"0 阶段 + `no_work` 理由 ⇒ 接受"（`_verify-run3-limits.md` 的 B6/B9 一类），**`encircled` 字段对判决零影响**，不是 task-68 引入。
2. **V2 = 既有遮蔽盲区**（task-15 已知局限：日级后置条件按"每阶段种类最后一条记录"算，`stage_midway_leftover` 只留痕）——task-68 让它更容易命中：`encircled` 不入 `blocked`，当天可继续换片/换阶段，把被围住的格"留在更早那条记录里"。
3. **V5 = 与 task-68 直接相关的新洞（NIT-1）**：`encircled` 步数**计入 `attempted`**，而 `attempted` 正是不可达豁免上界 `unreachable_bound = max(5, floor(0.2 × attempted))` 的**分母**；`encircled` 自身**没有上界、没有任何闸门** ⇒ 只要 encircled 尝试足够多，真·不可达格就能"名义上在 20% 以内"被豁免到 `no_unmet_stages=true`（V5 里 **200 格真不可达被豁免、当天 VERIFIED**）。真机单日量级受 `idle_rounds>=3` + `FRONTIER_CLEAR_MAX=20` 限制（P2a 单日 3 次），但**口径上不设限**。
4. task-71 的新闸门在伪造时确实生效（V2 第一版我把 `unreachable_bound` 写成 6、而 `Σ attempted=11` 自算 5 ⇒ 判红 `不可达豁免上界账本=6 > 自算=5（attempted=11）⇒ 上界被放宽`）✅。
5. **NIT-5（工具文案）**：`encircled 坐标对不上：账本 5 格 vs journal 5 格` 的触发条件是"格数相同、坐标集合不同"，措辞读起来像数量不符 ⇒ 建议改成"坐标集合不同（账本 N 格 / journal M 格）"。

---

## §4 NIT 清单

| # | 级别 | 现象 + 行号 | 为什么 | 建议 |
|---|---|---|---|---|
| NIT-1 | **中** | `encircled` 无上界，且其步数进 `attempted` 分母（`longrun.py:2967-2969`；工具 `_bound` 优先取账本 `:453-460`） | 稀释 `unreachable` 的 20% 上界；V5 实测 200 格真不可达被豁免 + VERIFIED | 二选一：给 `encircled` 加 `max(5, 0.2×attempted)` 上界（同 `refused`）；或把 encircled 步从 `attempted` 里剔出（但会与 `verify-run3.py`/`analyze-longrun.py` 的对账口径冲突，需两侧同改、由 Lead 拍板） |
| NIT-2 | **中** | `open_way`/`_ensure_reachable`（`farmwork.py:998-1068`）判 `encircled` 不要求"至少挥过一次工具"，reason 文案与事实不符（P1a：四邻是 weed 却写"树/桩/大石"） | 观测一失真/一陈旧就能整片标 `encircled`（掉出 unreachable 计数）；journal 读起来会误导复核人 | 文案改成"四邻观测皆无落脚点"；可考虑"`_openable_neighbours` 空且未试过任何清障"与"试过但都失败"分两类留痕 |
| NIT-3 | 低 | `encircled_day` 只在 `_frontier_clear`（`longrun.py:1477`）生效；stage 路径不看它 | "当天不再试"不成立（P2a 同日 3 次），白花墙钟 | 若确实想"当天不再试"，把 `encircled_day` 也纳入目标池过滤；否则把卡面/注释措辞改成"当天止损靠 idle/配额" |
| NIT-4 | 低 | 日级 `encircled` 伪造成本低（V1/V5 均 exit 0；工具对"账本 vs journal 自算"只记 info） | 复核人无法区分真 `encircled` 与伪造 | 保持 info 不变（Lead 已刻意不判红），可在 `_verify-run3-limits.md` 里把这条列为已知盲区 |
| NIT-5 | 低 | 工具文案"坐标对不上：账本 N 格 vs journal N 格"（格数相同、集合不同时最易误读） | 复核人可能以为数量不符 | 改成"坐标集合不同（账本 N 格 / journal M 格）" |
| NIT-6 | 信息 | 卡面基线"496 / 1 红"应为"496 / 2 红"；快照跑全量会多 5 条假红 | 报告数字要对得上；避免下一个人按错基线判红 | 卡面改成"主树 496 / 2 红（task-76 漂移 + task-73 在制 `test_sleep_intent_is_vetoed_while_work_remains`）"；全量读数一律用主树 |

---

## §5 判定

**PASS-WITH-NITS（无必修项）**：task-68 的核心口径正确（`encircled` 与 `unreachable`/`refused` 三套独立、不封格、次日重试、证据链独立字段、被围住拿不到 VERIFIED），task-75 只加 info、7/7 账本判决与之前逐字一致。

但两件事请在 0.7.26 冻结前给个决定：

1. **NIT-1（V5，`encircled` 抬高不可达豁免上界的分母）** —— 这是唯一与本次改动直接相关的容量洞，建议至少加一条"encircled 也有上界"或"encircled 步不计入分母"；
2. **NIT-2（`encircled` 判据不要求尝试过、文案会误导）** —— 建议改文案 + 考虑分两类留痕。

另：卡面 B5 点名的伪造账本（V1）确实没被拦住，但控制组证明这是**既有**盲区、不是 task-68 引入（详见 §3.5 第 1 条），我按"不是新缺陷"处理，请 Lead 确认这个定性。

---

## 附：复跑命令

```powershell
$env:PYTHONUTF8="1"; $py="C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
# 干净快照（若要重做）
git archive --format=tar -o scratch\_t77_snap.tar 8ceea87; New-Item -ItemType Directory -Force scratch\_t77_snap | Out-Null
tar -xf scratch\_t77_snap.tar -C scratch\_t77_snap
# B 段
& $py scratch\_t77_a.py            # 分类 / 日级 / 零动作 / 次日重试
& $py scratch\_t77_forge.py        # 伪造账本矩阵（V1…V5）
& $py scratch\_t77_regress.py      # A3：与 9f554d7 版工具逐字对比（7 本）
# A 段读数
cd scratch\_t77_snap; & $py -m unittest tests.test_farmwork tests.test_longrun; & $py -m unittest tests.test_verify_run3
```
