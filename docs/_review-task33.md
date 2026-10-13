# task-33 独立验收（睡觉链路：踩触发格 → 同 tick 关框 → 跨日）

- 验收人：deputy-lead（只读复核 + 自写探针；**未改任何生产代码**，未碰游戏/桥）
- 日期：2026-10-13（晚）
- 对象：dev-coder 的 task-33 在制品（未提交），8 个文件 `+606 / −117`
- HEAD：`797d5b4`（task-37 真机定案 + 0.7.23 发布计划；本对象是它之上的未提交在制品）
- **判定：PASS-WITH-NITS**

| 文件 | SHA256（前 12） | 与 dev-coder 自报 |
|---|---|---|
| `brain/agentfarm/farmwork.py` | `cdc043f4641a` | 一致 |
| `tests/test_farmwork.py` | `6807a12edf0c` | 一致 |
| `mod/AgentFarm.Bridge/SleepSkill.cs` | `d995f057aa26` | 一致 |
| `mod/AgentFarm.Bridge/MoveToLocationSkill.cs` | `9ef66749a813` | 一致 |
| `mod/AgentFarm.Bridge/ModalDismiss.cs` | `2caf37ab2c9e` | 一致 |
| `mod/AgentFarm.Bridge/Contracts.cs` | `bc797ddd511b` | 一致 |
| `mod/AgentFarm.Bridge/WorldSnapshot.cs` | `bf6840f6ec47` | 一致 |
| `mod/AgentFarm.Bridge/Skills.cs` | `845039c660e7` | 一致 |

验收全程 8 个哈希未变（开工/收工各算一次）⇒ 结论对应的是同一份工作树。

## §1 惯例读数（条款 1）

| 项 | 读数 |
|---|---|
| `py_compile`（`brain/agentfarm`+`tests` 共 20 个 .py） | `exit 0` |
| `tests.test_farmwork` | `Ran 46 tests / OK` |
| 全量 `unittest discover -s tests` | **`Ran 306 tests / OK`**（≥301 ✅） |
| `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` | **0 个警告 / 0 个错误** |
| 版本 | `mod/AgentFarm.Bridge/manifest.json` = **0.7.22**；`brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.22"`（**未 bump** ✅） |
| 越界文件 | `brain/agentfarm/longrun.py`、`tests/test_longrun.py` **零 diff**（`git diff --numstat HEAD` 为空） |
| `git status --short` | 正好 8 个 ` M`（见上表）+ 我的 `?? scratch/_t33_{probe,mutate,falsify}.py` + Lead 的 `?? tools/_note-0723.txt` |

## §2 条款 2：`ModalDismiss.CloseDialogueBox` 抽取不改变 `dismiss_modal` 语义 —— **过（1 条可读性 NIT）**

- 抽取：`mod/AgentFarm.Bridge/ModalDismiss.cs:179 internal static string CloseDialogueBox(DialogueBox box)`；调用方 `:158 string closeNote = CloseDialogueBox(box);`。
- 逐行比对旧内联块（`git diff HEAD -- ModalDismiss.cs`）：调用顺序与条件**完全一致** ——
  `IsActiveDialogue(box)` → `box.closeDialogue()` → 仍在则 `box.exitThisMenu()` + `ClearDialogueFlag()` → `!IsActiveDialogue(box) && SafeBool(() => Game1.dialogueUp)` 时再 `ClearDialogueFlag()`。
- 唯一直接写游戏状态的那处**仍在**：`ClearDialogueFlag()` 定义 `:345`，在抽取体 `:192`、`:200` 被调用（与旧版两处相同）✅。
- 共用面：`SleepSkill.cs:322`（应答后同 tick）与 `:345`（等待期兜底）都走这一份实现 ⇒ "只有一份关框顺序"成立 ✅。
- **NIT-1（纯文案，不阻塞）**：旧 `closeNote` 自带前导「；」，新实现去掉了（`:198` 用条件式 `(closeNote.Length > 0 ? "；" : "")`），而调用方 `:158` 之后仍是 `$"已关闭对话框（选“{chosenText}”：{answerNote}{closeNote}）"` 直拼 ⇒ 会拼出 `…无需应答closeDialogue() 关闭（复位…）`、`…并复位残留的 dialogueUp` 紧跟 前一句。只影响 journal/reason 可读性，零功能影响。建议：调用点补「；」或在模板里插分隔符。
- **NIT-2（观察项，不可达）**：新增外层 `try/catch`（`:182-207`）把异常变成一句 note ⇒ 若将来内层某个调用真的抛，`dismiss_modal` 会返回 **ok** 而不是 error。当前内层每个危险调用各自 try/catch、`IsActiveDialogue`/`SafeBool` 也不抛 ⇒ 该分支不可达；记录以免后人在内层加会抛的代码时失去这个告警。

## §3 条款 3：`farmwork.sleep()` 无界等待审计 —— **过（1 条必修建议 NIT-3）**

逐个循环上界（生产默认 `pause=time.sleep`，`farmwork.py:488`；`longrun.py:337` 不覆盖 ⇒ **生产是真睡**，只有测试注入 no-op）：

| 段 | 上界 | 行号 |
|---|---|---|
| `ensure_location(home)` | `timeout_ms=30000` | `farmwork.py:1345` |
| `_walk_off`（≤4 个邻居，每个 `move_to 8000ms`） | ≤32s | `:1212-1244` |
| `_step_onto`（每个触发格候选一次 `move_to 10000ms`） | ≤10s × 候选数（桥通常 ≤2） | `:1246-1263` |
| `_await_question`（`rounds=4, step_s=0.3`） | ≤1.2s | `:1265-1278` |
| `client.sleep()` | Mod `DefaultTimeoutMs=15000`（`SleepSkill.cs:72`） | `:1381` |
| `_dismiss_question()` | `dismiss_modal(timeout_ms=5000)`，异常全吞 | `:1280-1298` |
| `_await_day_change`（`rounds=12, step_s=0.5`） | ≤6s | `:1300-1312` |

最坏 ≈ **100s 且必须由 Mod 侧 15s 上限兜底**，没有任何 `while True`/无上界轮询 ✅。
三条情形（我的独立探针 `scratch\_t33_probe.py`，**14/14 ALL-PASS**，不复用作者断言）：

| 情形 | 实测 |
|---|---|
| 永远不弹提问（`step_opens_question=False`） | `code=sleep_no_question`、`sleep_calls=[]`、`interacts=0`、`proven_inert=False`、`pause` 轮数 8、`move_to` 3 次 |
| 关框也无效（`sleep_mode=timeout` + `dismiss_finishes_day=False`） | `code=timeout`、`dismiss_calls=1`、`sleep_calls=[15000]`（**绝不重发**）、reason 带 Mod `newDaySync` 现场、`pause` 轮数 12 |
| 桥中途沉默（`observe` 第 2 次抛 `BridgeError`） | **有界但异常穿出**：`sleep()` 直接抛 `BridgeError`（`observes=2`，未发 sleep 请求），不是 `StepResult` |
| 生产默认 `pause` | `FarmWorker(...).pause is time.sleep` ✅；测试形态注入 no-op ✅ |

- **NIT-3（建议冻结前修，约 3 行）**：`sleep()` 内多处 `self.snap()` 未包 try（`:1340`、`:1362`、`:1366`、`:1394`、`:1409`），而
  `longrun.py:993 st = self.worker.sleep(home=self.home)`（`_do_sleep`，`:990-1005`）与 `longrun.py:2016 rep = self._run_day()`（`run()` 内，`:2006-2028`）**都没有 try/except** ⇒ 睡觉途中桥掉线/`observe` 超时会以**未捕获 traceback 结束**（没有 `finish` journal、没有 `days[]`），而循环顶部那次 `_snap()` 掉线是会规规矩矩记 `ended_by="bridge_down"`（`:1724-1729`）的。物理后果仍有界（客户端自身超时），但 run3 会拿到"账本无 finish"而不是 bridge_down，且异常路径没有日报。
  建议二选一：①`sleep()` 把 `snap()` 包一层，失败即 `return StepResult(code="bridge_down"/"failed", ...)`；②`run()` 给 `_run_day()` 加 `except BridgeError as exc: rep.ended_by="bridge_down"`。**不阻塞**（task-33 之前同样存在，本卡把窗口略微放大）。

## §4 条款 4：不许再有 `interact(床)`、`SLEEP_NO_QUESTION` 不许盲发 —— **过**

- 全仓 `self.c.interact(` 在 `farmwork.py` 只剩 **1 处**：`:1086`（`harvest()` 内，`:1071` 动作），sleep 链路 0 次；`stand_next_to` 仍在 `:783/:902/:954/:1034/:1081/:1130`（till/plant/water/harvest/refill 等），**不再出现在 sleep**。
- `if not ready:` 分支 `:1370-1378`：`r.code = SLEEP_NO_QUESTION` 后**直接 return**，`client.sleep()` 在 `:1381` 位于其后 ✅。
- 独立复现（不引用作者用例）：探针情形 A `sleep_calls == []`、`interacts == 0` ✅；作者用例 `tests/test_farmwork.py:728` 亦有同断言（`:739`/`:740`）。

## §5 条款 5：门候选顺序改动不回归既有寻路 —— **过（逐行 diff）**

`git diff HEAD -- mod/AgentFarm.Bridge/MoveToLocationSkill.cs` 结论：

- 先算一次 `standableNeighbors`（复用原 `neighbors` 列表与同一 `StepMover.Standable(loc, n, true, out Furniture _)` + 同 `catch ⇒ false`）——语义与旧的"边遍历边判可站"**逐项相同**。
- **仅 `IsDoor` 的边**新增前置块：`foreach (Point n in standableNeighbors) AddCandidate(..., n, e, tag + "door_push", e.Source)`（`e.IsDoor` 分支）。
- 其后顺序与旧版一致：`source` → `cross` → `neighbor`/`retry` → `push` 块；末尾门分支由 `if (e.IsDoor || !sourceStandable)` 改为 **`if (!e.IsDoor && !sourceStandable)`** ⇒ 对**非门边**，进入条件与候选集合/顺序**完全相同**（`!sourceStandable` 一切照旧）；对门边，同一批 `door_push` 只是从末尾提到最前、末尾不再重复。
- `FailHopExhausted`：新增 `doorNote`（`primary.IsDoor` 时解释"warp 源格是触发区锚点、不是可站格"）并拼进 fail reason —— 纯文案。
- `Begin()` 的 `ui_modal` 文案与 `Skills.cs:447-455`（同句）只加"睡觉触发格 ⇒ 命中信号"说明 —— 纯文案。
- 局限（记录）：C# 侧候选顺序**没有单元测试**（`tests/test_farmwork.py:816-817` 明说钉不住），本轮只能靠逐行 diff；真机回归证据沿用 task-33 施工单引用的 `logs/probe-bed-*`。

## §6 条款 6：sleep 用例真能证伪（变异实验）—— **过**

工具：`scratch/_t33_mutate.py`（把整个 `brain/agentfarm` 复制到 `scratch/_t33_mut/agentfarm`，只在**副本**注入一处错误判断）+ `scratch/_t33_falsify.py`（跑目标用例）。

- ⚠ **第一次跑全是绿（假象）**：`tests/test_farmwork.py:22 sys.path.insert(0, …/brain)` 会把生产包插到最前，`PYTHONPATH` 指副本**不起作用**（变异与对照读数一模一样）。改成"先 `import agentfarm.farmwork`（来自副本）占住 `sys.modules`，再加载测试模块"后才行；探针会打印 `USED_MODULE …\_t33_mut\agentfarm\farmwork.py` 自证。
- 结果：对照（未注入）`Ran 3 / OK`；**m1**（把"没提问就早退"改成盲发 sleep）⇒ `test_no_question_fails_fast_without_asking_mod` 红：`AssertionError: 'failed' != 'sleep_no_question'`；**m2**（把"日期真变了"改成"回执 ok 就算"）⇒ `test_ok_receipt_without_day_change_is_failed` 红：`AssertionError: True is not false`；**m3**（把踩触发格 `ui_modal` 当失败）⇒ `test_steps_onto_bed_then_crosses_day` 红：`AssertionError: '命中信号' not found`；恢复副本后 3 条全绿。生产文件哈希全程不变。
- 用例清点：`tests/test_farmwork.py:691-828 TestSleepCrossDay` 实测 **11 条**（任务书写 10 条；本轮 diff 新增/改名 7 条、删除改名 2 条）。断言实质（抽查）：`:739 sleep_calls == []`、`:754 dismiss_calls == 1`、`:777 code == "failed"`、`:788 moves == []`、`:811 bed_cells == [(62,14),(63,14)]`。

## §7 条款 7：越界检查 —— **过**

- `git diff --numstat HEAD` 对以下路径**全为空**：`mod/AgentFarm.Bridge/manifest.json`、`docs/00-开发日志.md`、`logs/`、`tools/`、`brain/agentfarm/longrun.py`、`tests/test_longrun.py`。
- 改动 = 8 个文件 `+606 / −117`（`farmwork.py +224/−32`、`test_farmwork.py`、`ModalDismiss.cs`、`MoveToLocationSkill.cs`、`SleepSkill.cs`、`Contracts.cs`、`WorldSnapshot.cs`、`Skills.cs`），全部在 task-33 写范围内。
- `brain/agentfarm/farmwork.py` 的 hunk 全部落在睡眠链 + 两处小改：`:29 import time`、`:118 BED_CELL_FALLBACK = ((0, 1), (1, 1))`、`:488/:493 pause 注入`、`:702 ensure_location` 失败 reason 带 Mod 原文（Lead 已批准 `why = str(exc)[:300]`）、`:1159-1424` 睡眠链。
- 我自己的新增文件：`scratch/_t33_probe.py`、`scratch/_t33_mutate.py`、`scratch/_t33_falsify.py`、`scratch/_t33_mut/`、若干 `scratch/_t33_*.txt`。

## §8 NIT 清单

| 编号 | 位置 | 现象 | 建议 | 是否阻塞 |
|---|---|---|---|---|
| NIT-3 | `brain/agentfarm/farmwork.py:1340/1362/1366/1394/1409` + `longrun.py:993`/`:2016` | 睡觉途中桥沉默 ⇒ `BridgeError` 穿出（无 `finish`/`day_end`，无 `bridge_down` 归类） | `sleep()` 包 `snap()`；或 `run()` 给 `_run_day()` 加 `except BridgeError` | **建议冻结前修**（不阻塞 run3 判定） |
| NIT-1 | `mod/AgentFarm.Bridge/ModalDismiss.cs:158` + 抽取体 `:198` | reason 文案缺「；」分隔符 | 调用点补分隔符 | 否（纯可读性） |
| NIT-2 | `mod/AgentFarm.Bridge/ModalDismiss.cs:182-207` | 外层 catch 会把（当前不可达的）异常变成 ok 回执 | 留注释说明或去掉外层 catch | 否 |
| INFO-1 | `WorldSnapshot.cs:760 ReadBedCells` | 非法入参 `null` 与非床 `null` 不可区分；兜底两槽位可能落在图外/非触发格 | 脑侧已逐个试并如实报 `sleep_no_question`，无需改 | 否 |
| INFO-2 | `SleepSkill.cs:449 SafeNewDay()` | 读不到 `Game1.newDay` 按 `false`（=宁可早报成功） | 已有 docstring 说明，脑侧用观测差分复核 | 否 |
| INFO-3 | `WorldSnapshot.cs:760` | `bedCells` 是**候选集合**而非唯一真值（`bedTileOffset` 逐帧翻转） | 设计如此；脑侧 `_cell_order` 逐个试 | 否 |

### §8.1 NIT-3 delta 复核（2026-10-13 晚，dev-coder 修 `snap()` 穿出之后）

对象：`brain/agentfarm/farmwork.py` = `6957707d03c391ad992a56b61d62d68f51901d40e511ac24db96e5111340b93e`、
`tests/test_farmwork.py` = `f5088bc6e7fc04b1633391c179d00214e21543bf35fbde036533da0ab9c9b9cc`（与 dev-coder 自报逐字一致）。

**① 读数**：`py_compile` exit 0；全量 **`Ran 309 tests / OK`**（306 + 3 条新用例）；6 个 Mod 文件哈希与上一轮**逐字一致**（⇒ 未重跑 `dotnet build`，二进制输入未变）；仍只有那 8 个文件在制（`git diff --stat HEAD` = 755/120）。

**② wrapper 拆分与词表对照（逐行核）**

| 位置 | 词表 | 含 `timeout`? |
|---|---|---|
| `brain/agentfarm/farmwork.py:119-122 BRIDGE_DOWN_STATUSES` | `unreachable_bridge`/`connection_broken`/`bad_response`/`bridge_file_missing`/`bridge_file_invalid`/`schema_mismatch` | **否** |
| `brain/agentfarm/longrun.py:1724-1729` | **catch-all**：`_snap()` 抛**任何** `BridgeError` ⇒ `ended_by="bridge_down"` | 是（连 `no_save` 也算） |
| `brain/agentfarm/bridge.py:816`（`quit_game` 折叠"回执收不到"） | `connection_broken`/`bad_response`/`unreachable_bridge`/`timeout` | 是 |

⇒ 三处**不同构**。对 sleep 这条路径，新代码行为正确：`_sleep_impl:1419` 只在 `not raw`（空 status）/`raw=="bridge_down"`/`raw in BRIDGE_DOWN_STATUSES` 时 `raise`，**`timeout`/`stale` 不在其中且非空 ⇒ 不 re-raise**，继续走原"打标 + `dismiss_modal` 兜底关框 + 等日期"。
探针 `scratch/_d33_stale_probe.py`（把 `MiniWorld.do_sleep` 换成抛指定 status 的 `BridgeError`，共 12 态）：

| status | 异常穿出? | 走哪条路 | `dismiss_calls` | `code` |
|---|---|---|---|---|
| `timeout`/`stale`/`no_save`/`ui_modal`/`world_fading`/`busy`/`error` | 否 | 原逻辑兜底 | 1 | `""`（当天被兜底关框救回 ⇒ `ok=True`；探针预置了开着的提问，属假世界行为，不是产品结论） |
| `connection_broken`/`unreachable_bridge`/`bad_response`/`schema_mismatch` | 否 | bridge-fail | 0（不做需要桥的补救） | `bridge_down` |
| 空 status（生产不可达：`bridge.py` 每个 `raise` 都带 status） | 否 | bridge-fail | 0 | `error` + `inconclusive=True`（`_exc_status:454-460` 明确把"没 status"归 inconclusive） |

**③ 三条新用例能证伪（变异实验，`scratch/_t33_mutate.py` 新增 m4–m7，只在副本注入）**

| 变异 | 注入点 | 结果 |
|---|---|---|
| `m4_bridgedown_not_success`（跨日也不算成功） | `_sleep_bridge_fail:1487` 条件置假 | ✅ 红：`test_bridge_down_after_day_change_still_counts_as_crossed` |
| `m5_no_normalize`（桥码不折成 `bridge_down`） | `:1478-1479` | ✅ 红：`test_sleep_call_bridge_down_is_bounded_and_normalized`（`connection_broken` 原样漏出） |
| `m6_no_wrapper`（去掉外层收口 = NIT-3 的病本身） | `sleep():1361-1364` 改成 `raise` | ✅ 三条全红（ERROR：异常穿出） |
| `m7_fake_success`（连观测都拿不到时假装成功） | `:1498-1500` 改成 `ok=True; return` | ✅ 红：`test_bridge_down_mid_bed_step_returns_bounded_result` |
| 对照（未注入） | — | `Ran 3 / OK`；变异后生产哈希不变 |

⚠ 诚实记录：`m5` 只让**第三条**用例变红 —— 第一条的假桥抛的 status 字面就是 `"bridge_down"`（`tests/test_farmwork.py:857`），归一与否都得到同一码 ⇒ 它钉的是"不许穿出"，归一由第三条钉。任务书"另两条必须红"与实际不完全一致，非缺陷。

**④ 边界检查**：`_sleep_bridge_fail` 全方法**只有 1 次** `self.snap()`（`:1485`，无 `while`/`for`）⇒ 不是重试风暴；`day_before is None` 或 `day_after == day_before` ⇒ 一律 `ok=False` 如实失败（`m7` 证明被用例钉住）；`day_after` 取不到时 `after = {"day_before": …, "stage": …}` 仍带现场；`receipt = _receipt_long(exc)`（非 BridgeError 为空并在 reason 补 `异常类型=`）；reason 三段齐全（`status` + `跨日未完成，请按桥掉线处理` + `最后一步=<stage>` + `脑侧现场=<diag>`）。

**⑤ delta 判定：`DELTA-PASS-WITH-NITS`（无必修项）** —— NIT-3 已按验收要求收口：桥中途沉默 ⇒ 有界 `StepResult`、不穿出、桥自身码归一成 `bridge_down`、跨日已发生仍算成功、连观测都拿不到时如实失败。
- **NIT-4（新增，既有粗粒度，非本 delta 引入，不阻塞冻结）**：`longrun.py:1724-1729` 的 `bridge_down` 是 catch-all，会把一次 `_snap()` **HTTP 超时**（`bridge.py:466 status="timeout"`）也记成 `ended_by="bridge_down"`，而 `tools/verify-run3.py` 把 `bridge_down` 当**异常事件**算问题 ⇒ 环境抖动会被升级成账本异常。建议后续把该处也按 `BRIDGE_DOWN_STATUSES` 过滤（并统一三处词表），排 0.7.23 之后。

## §9 结论

条款 1–7 全部通过；跨日链路的关键语义（`ui_modal`=命中信号、先走离床一步、同 tick 关框、判据=观测差分）在代码、用例与我的独立探针三处一致；`dotnet build --no-incremental` 0 警 0 错、全量 306 OK。唯一建议在冻结 0.7.23 前修的是 **NIT-3**（桥中途沉默时让 `sleep()` 有界返回而不是抛穿），其余为文案/留档项。C# 侧的"同 tick 关框"与"门候选提前"没有自动化测试，本轮以逐行 diff + 真机日志引用为准，属已知局限。

**补（2026-10-13 晚）**：NIT-3 已由 dev-coder 修完（`sleep()` 加 wrapper + `_sleep_bridge_fail` 收口），delta 复核见 **§8.1 = DELTA-PASS-WITH-NITS（无必修项）**，全量 **309 OK**，Mod 6 文件哈希未变 ⇒ 0.7.23 可冻结；唯一遗留是既有的 NIT-4（`longrun` 的 `bridge_down` catch-all 粒度），排 0.7.23 之后。
