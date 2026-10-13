# task-41 独立完整验收（deputy-lead）

**判定：PASS-WITH-NITS。**

- 功能面（eventUp 硬停 + 室内 farm 证据不可用 fail-closed + NIT-1 用例）**全部到位**，且经我**独立读数、独立变异、独立探针**验证；`Ran 328 tests / OK`；无夹带、未 bump。
- 5 条 NIT 全在**工具可观测性 / 文案 / 兜底用例**层，**没有一条会改变 run5 的判定正确性**（NIT-1/2 建议 run5 复盘前补，工具属 Lead 写权）。

对象 = Lead 指定冻结点 **`a302d61`**（`git log --oneline -1`）。`git show --stat a302d61` = **只有两个文件**：`brain/agentfarm/longrun.py`（96+/7−）、`tests/test_longrun.py`（259+/2−）；`git diff --numstat HEAD -- brain tests mod tools` **为空**（工作树 == 冻结点）。SHA256：`brain/agentfarm/longrun.py` = `E154312E2049F9981A573612DE7287B997C90716094402365564D3D252F89BDB`、`tests/test_longrun.py` = `29ABDEE42A658DE9BFF2DC4B3BDD1F9DFB4E67534013C88F26993FF9B98810AB`。

---

## §1 独立读数（我亲跑，不转述 dev-coder 的自报）

| 项 | 读数 |
|---|---|
| `python -W error::SyntaxWarning -m py_compile brain\agentfarm\longrun.py tests\test_longrun.py` | exit **0** |
| `python -m unittest discover -s tests` | **Ran 328 tests in 2.555s / OK**（exit 0） |
| `python -m unittest tests.test_longrun.TestTask11ModalGuard` | Ran **6** / OK |
| `python -m unittest tests.test_longrun.TestMorningIndoor` | Ran **2** / OK |
| `python -m unittest tests.test_longrun.TestTask15DayAccounting` | Ran **3** / OK |
| `python -m unittest tests.test_farmwork.TestSleepCrossDay` | Ran **14** / OK |
| 版本 | `mod/AgentFarm.Bridge/manifest.json` = **0.7.23**、`brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.23"`（**未 bump**、未 deploy） |

注：`TestSleepCrossDay` 现在是 **14** 条（task-33 时 11 条）；本冻结点**没有**碰 `tests/test_farmwork.py`，差额来自更早的任务，不是 task-41 夹带。

运行的命令原文（`$py` = 运行时 python）：

```text
$env:PYTHONUTF8="1"; $env:PYTHONPATH="$pwd\brain"
& $py -W error::SyntaxWarning -m py_compile brain\agentfarm\longrun.py tests\test_longrun.py      # exit 0
& $py -m unittest discover -s tests                                                              # Ran 328 / OK
& $py -m unittest tests.test_longrun.TestTask11ModalGuard -v                                     # Ran 6 / OK
& $py -m unittest tests.test_longrun.TestMorningIndoor tests.test_longrun.TestTask15DayAccounting -v
& $py -m unittest tests.test_farmwork.TestSleepCrossDay -v                                        # Ran 14 / OK
```

---

## §2 §9.1「护栏不许改既有断言」逐条（我按 §9.1 清单判）

`git diff -U0 a302d61^ a302d61 -- tests/test_longrun.py` **只有两个 hunk**：

- `@@ -34,8 +34,9 @@`：import 列表重排 + 新增 `ENDED_BY_EVENT`；**该 hunk 的 2 条删除行都是 import 行**（`DEFAULT_LLM_MAX_TOKENS, ENDED_BY_MODAL, …` 那两行被重新折行）。
- `@@ -2276,6 +2277,262 @@`：在 `class TestMorningIndoor` **之后追加** 7 个新用例。

⇒ **`class TestTask11ModalGuard`（`tests/test_longrun.py:1569`）–`class TestTask28BusySpin`（`:1719`）区间内删除行 = 0。**

| §9.1 机器判据 | 结果 |
|---|---|
| ① 该区间删除行 = 0 | ✅ 0 条（删除只发生在 import hunk） |
| ② 6 个既有测试 ID 仍能被 `-k` 命中 | ✅ `-k TestTask11ModalGuard` → Ran **6** / OK |
| ③ 新 event 用例确为**新增**、不重名 | ✅ 追加在文件尾（`:2280` 起），7 条新用例名与既有 6 条无重叠 |
| ④ 任一既有断言被放宽（`==1`→`<=1` 之类）⇒ FAIL | ✅ 无：2 条删除行都是 import，护栏 6 条断言一字未动 |

七行护栏表逐条结果（全 OK，行号用 rev4 时的文件核对过）：

| 护栏 | 用例 | 结果 |
|---|---|---|
| ① 提问框仍按既有口径关（不注入按键） | `TestTask11ModalGuard.test_question_modal_dismissed_with_no_key_injection`（`:1673`） | OK（`kind=="question"`） |
| ② `LevelUpMenu` 关一次 / 连出两次都关 | `…test_plain_levelup_dismissed_save_menu_only_waited`（`:1593`）、`…test_consecutive_levelups_are_both_dismissed`（`:1621`） | OK |
| ③ `SaveGameMenu`/`NewDaySavingMenu` 只等不关 | `…test_wait_only_modal_timeout_stops_the_day`（`:1689`） | OK（`dismiss_calls==0`） |
| ④ 职业非空停下；字段缺失按未知 | `…test_profession_choice_is_never_dismissed_and_day_is_not_verified`（`:1638`）、`…test_missing_professions_field_is_treated_as_unknown`（`:1657`） | OK（`blocked_modal`、`verified is False`） |
| ⑤ `eventUp=false` 睡觉提问仍走 task-33 配方 | `tests.test_farmwork.TestSleepCrossDay` 全 14 条 | OK |
| ⑥ 模态清理不许回归（task-15） | `TestTask15DayAccounting.test_env_retry_clears_the_blocking_modal`（`:1898`） | OK |
| ⑦ 室内日首回农场不许回归（task-40） | `TestMorningIndoor` 2 条（`:2222`） | OK |

---

## §3 eventUp 政策：逐条核对 + **新修复 / 既有事实**分开写

**新修复（task-41 加的）**
1. `longrun.py:106 ENDED_BY_EVENT = "blocked_event"`、`:110 BLOCKING_ENDS = (ENDED_BY_MODAL, ENDED_BY_EVENT)`（`:97-105` 注释带真机证据：关框会让事件推进一句、`Yes/No` 会被默认选否）。
2. **⓪ 闸门放在最前**：`longrun.py:1800-1803`（`_clear_modals` 里 `if not is_modal: return` 之后、提问/普通框之前）`if ui.get("eventUp") is True: return self._event_blocked(obs, rep)`。
3. `_event_blocked`（`longrun.py:1868`）：journal `event_blocked` 带 **`activeMenu`/`activeMenuText`/`dialogueIsQuestion`/`dialogueResponses`/`tile`/`timeOfDay`/`worldSeq`** + note；`rep.ended_by = ENDED_BY_EVENT`；`rep.notes` 写"不 dismiss / 不 sleep / 不 load_save"；`_say`；返回 `(obs, True)`。**不调任何桥写接口**：`tile`/`timeOfDay` 来自 `farmwork.py:547 player_tile(obs)` / `:557 time_of_day(obs)`（纯读 obs 的 staticmethod），`worldSeq` 直接取 `obs` ⇒ 卡面"不 dismiss、不 sleep、不 load_save"成立。
4. 收尾口径贯通：`longrun.py:2145 "no_blocking_modal": rep.ended_by not in BLOCKING_ENDS`、`:2282 run()` 早退 `("bridge_down", "stop", *BLOCKING_ENDS)`、`:1406 _execute` 里的模态停手真值改为 `rep.ended_by or ENDED_BY_MODAL`（否则事件会被改写成 `blocked_modal`）。`day_justified` 由 `is_justified_end`（`ended_by != "sleep"` ⇒ False）⇒ `verified=False`，与 `slept_by_us`/`no_blocking_modal` 三重一致。

**既有事实（必须与"新修复"分开记账，别当成新功）**
`mod/AgentFarm.Bridge/WorldSnapshot.cs:845-848` 的 `IsModal` **本来就 `|| v.EventUp`**（字段 `Contracts.cs:509 [JsonPropertyName("eventUp")] public bool EventUp`，写入点 `WorldSnapshot.cs:832`）⇒ **事件对话框在 task-41 之前就已经被判成模态**。本次新增的价值是**脑侧区分"事件（不可关）"与"可关的框"**，不是"首次把事件识别为模态"。

---

## §4 NIT-2 fail-closed（两处都到，且 rev4 §10 的破功点已堵）

- `work_reasons`：`longrun.py:1058-1060` 新增 `elif not self._is_farm(obs): reasons.append(self._farm_evidence_reason(obs))` ⇒ **`work_reasons()` 非空**，`_run_day` 的 `why = ("no_work" if not reasons else "stuck:…")` 不会再落 `no_work`。
- `sleep_guard`：`longrun.py:1139 return False, "keep_working", self._farm_evidence_reason(obs)`，位置在 `farm_work is not None` 分支之后、`reasons = self.work_reasons(obs)` 之前（diff 顺序）。
- `_farm_evidence_reason`（`longrun.py:1067-1085`）：每天最多一条 journal `farm_evidence_unavailable`（`complete`/`loaded`/`location` + note，由 `:449`/`:1910` 的 `farm_evidence_noted` 日重置控制），返回文案含"farm 证据不可用"。
- docstring 明写**有界性不靠 `idle_rounds`**、靠 `_run_day` 的 `spot is None` 单次分支（`:1070-1073`）⇒ 与我 task-40 上报的机制修正一致。
- 我自己核了破功链：`work_reasons()` 若为空才会落 `no_work`（`:1058` 保证非空）⇒ 堵住；对应用例 `tests/test_longrun.py:2442-2443` 也断言了 `work_reasons()` 含该理由。

---

## §5 NIT-1（回不去农场）用例核对

`tests/test_longrun.py:2509 TestTask41CannotGoHome.test_cannot_go_home_ends_stuck_with_one_failed_goto`：夹具 `FlipIndoorWorld`（`:2466`，`_prepare` 后翻成室内）+ `_CannotGoHomeWorker`（`:2481`，`ensure_location` 恒 `timeout`、`run_stage` 全部失败 ⇒ 世界指纹不变 ⇒ `idle_rounds>=3` ⇒ 直接 `stuck`）。断言：恰 **1** 条 `goto_farm{where:"day_start", ok:false, code:"timeout"}`、`rep.notes` 含"回不去 Farm"、`ended_by=="stuck"`、`verified is False`、`actions<=40`、`len(run.days)==1` ⇒ **满足卡面第 7 条**。

与我 task-40 探针的差异（记录，不作缺陷）：我的探针（`FailGotoWorker` + 默认 `run_stage`）当天以 `ended_by="sleep"`、`reason` 前缀 `stuck:` 收尾、**4 个动作**；本用例用"`run_stage` 全失败"的更严夹具，直接拿到 `ended_by="stuck"`（注释记实测 26 个动作、上界断言 40）。两条路径都证明**有界且如实记账**，我按卡面判通过。

---

## §6 我自己的 m41a/b/c 变异矩阵（自己写脚本、自己跑）

脚本 `scratch/_t41_falsify.py`（只注入副本 `scratch/_t41_mut/agentfarm`；先预导入副本包以绕过 `tests/test_longrun.py:22` 的 `sys.path.insert(0, brain)` 劫持；每态打印 `USED_MODULE`）。

| mode | 注入点 | 期望 | 实测 |
|---|---|---|---|
| `none` | 不注入 | 7/7 绿 | `successful=True failures=0 errors=0 run=7` |
| `a` | `sleep_guard` 的 fail-closed → `return True, "no_work", …` | 两条 fail-closed 用例红 | `failures=2`，RED = `test_indoor_without_farm_evidence_never_says_no_work`、`test_day_never_ends_with_no_work_when_farm_evidence_is_missing` |
| `b` | `work_reasons` 的 `reasons.append(self._farm_evidence_reason(obs))` → `pass`（rev4 §10 的"改了等于没改"路径） | 同上两条红 | `failures=2`，同上两条 |
| `c` | 去掉 `if ui.get("eventUp") is True:` 闸门 | 两条 event 用例红 | `failures=2`，RED = `test_event_dialogue_is_never_dismissed_and_day_is_not_verified`、`test_event_question_is_never_answered` |

- 四态都打印了 `USED_MODULE …\scratch\_t41_mut\agentfarm\longrun.py`（避免"变异没生效导致假绿"）；四态跑完后生产 `brain/agentfarm/longrun.py` SHA256 仍为 `E154312E…F89BDB`。
- 我**没有**使用 dev-coder 在 `%TEMP%` 的脚本或它的任何读数；上述 red 集合是我自己跑出来的。

---

## §7 新闸门 + 我自造的 `blocked_event` 探针

**A. 「run3 连睡病复发」闸门**（`tools/verify-run3.py:436-448`，Lead 新增；我独立复跑）：`_end_reason.startswith("no_work")` 且 `final_water.dry>0` ⇒ 问题。读数：`scratch/journal-green.jsonl` ⇒ **exit 0 / VERIFIED**（0 命中）；`logs/longrun-3day-llm-run3.jsonl` ⇒ **exit 1 / needs_review**，命中 **spring 19/20/21/22，`dry=33/32/32/32`**。（`run2`、`rehearsal-0.7.22` 判决不变；`run4` 13 行无 `finish` 属预期，见 §9.2 A。）

**B. `blocked_event` 端到端探针**（我造 `scratch/review-t41-blocked-event-day.jsonl`：绿账本最后一天改为 `ended_by="blocked_event"` + 1 条 `event_blocked` journal；生成器 `scratch/_t41_event_day.py`）：

- `tools/verify-run3.py` ⇒ **exit 1**：`[spring 12] ended_by=blocked_event（不是我们主动睡过去的）`、`[spring 12] day_end verified=false`、结论 `needs_review` ✅
- `tools/analyze-longrun.py` ⇒ exit 0，但把这一天报进 **【0 必须人工介入（红）】1 条**（经 `checks.no_blocking_modal=false` / `checks.slept_by_us=false`）⇒ **没有漏判** ✅；不过那条 `event_blocked` 事件在 analyzer 输出里 **0 处提及**（NIT-1）。

---

## §8 NIT 清单（全部不阻塞；每条含行号 + 为什么 + 建议）

| # | 位置 | 现象 | 建议 |
|---|---|---|---|
| **NIT-1** | `tools/analyze-longrun.py:156-191` `EVENT_BUCKETS`、`:380` | 缺 `event_blocked` / `farm_evidence_unavailable`；未命中即静默跳过 ⇒ 实测探针里那条 `event_blocked` 在 analyzer 输出 0 处提及（`plots_capped` 当年同款问题） | 加两个桶（如 `"event_blocked": "event_blockeds"`、`"farm_evidence_unavailable": "farm_evidence"`），并在四类判定里加一条"事件挂住 ⇒ 需要人"的信息项 |
| **NIT-2** | `tools/analyze-longrun.py:154`、`:890`、`:915`（另文案 `:18`/`:149`/`:1501`） | `ENDED_BY_MODAL = "blocked_modal"` 单值 + `ended_by == ENDED_BY_MODAL` ⇒ `blocked_event` **靠 `checks` 兜住**（实测仍红），但"`ended_by` 规则"计数为 0、文案只写"职业选择/存档超时" | 改 `ended_by in (ENDED_BY_MODAL, "blocked_event")`，文案补"游戏事件挂住（eventUp）" |
| **NIT-3** | `brain/agentfarm/longrun.py:1802` | gate 用 `ui.get("eventUp") is True` 严格比较；**字段缺失**时退回旧行为（会关框）。现实不可达（`MOD_VERSION_EXPECTED="0.7.23"` + `tests/test_longrun.py:837 test_mod_version_mismatch_refuses_to_run`；`Contracts.cs:509` 是非空 `bool`、总是序列化），但缺一条兜底用例 | 补一条"`eventUp` 字段缺失 ⇒ 不 dismiss"的用例，把 fail-safe 钉死（同 task-11 职业字段"缺失按未知"的精神） |
| **NIT-4** | `brain/agentfarm/longrun.py:2145` vs `:1039` 注释 + analyzer 文案 | `no_blocking_modal` 语义已扩成"不是任一阻断型收尾"，但注释/文案仍写"职业选择/存档超时" | 文案补"游戏事件挂住" |
| **NIT-5** | `tests/test_longrun.py:2328` | 新用例断言 `assertIsNotNone(ev[0]["worldSeq"])` 依赖 FakeWorld 恒有 `worldSeq`；真机缺失时会记 `null` | 仅记录：属信息项，不阻塞 |

---

## §9 越界与纪律

- `git diff --numstat a302d61^ a302d61` = 只有 `brain/agentfarm/longrun.py`（96/7）与 `tests/test_longrun.py`（259/2）；`mod/`、`tools/`、`docs/`、`logs/` **零改动**（`docs/_run3-evidence.md` 的 M 是 Lead 的注记，不在本冻结点）。
- `manifest.json` 与 `bridge.py:39` 都仍 **0.7.23**（未 bump、未 deploy）。
- 我**未**启动/接触游戏与桥（run4 由 machine-runner 执行；我只跑离线单测、只读账本、副本变异）。
- 我的写盘只有 `docs/_review-task41.md` + `scratch/`（探针/变异/账本产物：`_t41_falsify.py`、`_t41_mut/`、`_t41_event_day.py`、`review-t41-blocked-event-day.jsonl`、`_t41_vr*_*.txt`、`_t41_an_event.txt`、`_t41_unittest.txt`、`_t41_mut_*.txt`）。

---

## §10 结论

**PASS-WITH-NITS** —— eventUp 硬停（含"一次都不动手"与 `run()` 早退）、fail-closed 双处落地（含 rev4 §10 破功点）、NIT-1 用例、护栏零改动，全部经我独立读数（328 OK）、独立变异（m41a/b/c 各红在预期用例、对照全绿）、独立探针（`blocked_event` 账本被 `verify-run3` 抓成 exit 1）验证；无夹带、未 bump、未碰游戏。5 条 NIT 都在工具可观测性/文案/兜底用例层，**无必修项**；其中 NIT-1/NIT-2 会让 run5 复盘时"事件挂住"在 analyzer 里不够显眼，建议在 run5 出结论前补（Lead 写权）。
