# task-40：`cc2988e` 独立验收 + `docs/_run3-evidence.md` 取证审计（deputy-lead）

**判定：**
- **A（`cc2988e` run3 室内 bug 修复）= PASS-WITH-NITS。** 两处修复各自被我的**独立变异**钉在预期用例上；无夹带；基线 321 OK。
- **B（run3 取证审计）= 5 条里 4 条对得上；断言 4 的 SMAPI 行号侧 + 断言 5 的 SMAPI/进程侧已不可复现** —— 不是文档写错，是 `SMAPI-latest.txt` 已被 run4 的会话**覆盖**（run4 于 19:15:49 启动，现文件 424 行、0 条 NewDay/Save 行）。存档 size/mtime 链部分可核，且与文档**逐字吻合**。

对象：`HEAD` 验收开始时 = `cc2988e`；本报告核对的两个文件在 `git diff --stat HEAD` 中**为空**（工作树 == 提交内容）。SHA256：`brain/agentfarm/longrun.py` = `ABFAD39178A839219C1E88FF9A0CFF66F342B498E1D67B73B90712451950F7CC`、`tests/test_longrun.py` = `836932FB28A240A45005C4AF8C83D71FC552F3B415EF852D0A170861A3F27361`。

---

## §1 读数（我亲跑）

| 项 | 读数 |
|---|---|
| `git show cc2988e --stat` | **只有 2 个文件**：`brain/agentfarm/longrun.py` +68、`tests/test_longrun.py` +103，**0 删除** ⇒ 无夹带 |
| `py_compile brain/agentfarm/longrun.py tests/test_longrun.py` | exit **0** |
| 全量 `python -m unittest discover -s tests` | **Ran 321 tests in 2.679s / OK**（= 卡片基线） |
| `tests.test_longrun.TestMorningIndoor -v` | **Ran 2 tests / OK** |
| 越界 | `manifest.json` = 0.7.23、`bridge.py:39` = 0.7.23（未 bump）；`longrun.py`/`test_longrun.py` 之外零改动 |

---

## §2 代码逐条核对（行号 = 提交后的现文件）

1. **`_ensure_on_farm(self, obs, rep)` 存在于 `longrun.py:527-551`**（卡片写 `:527-551` ✅）：`if self._is_farm(obs): return obs`（`:535-536`）→ `worker.ensure_location(self.farm)`（`:538`）→ **无论成败都写 journal** `goto_farm`（`:540-541`，`where="day_start"`）→ 失败 `rep.notes.append("回不去 …")` + `_say` + **返回原 obs**（`:542-545`，不假装成功）→ 成功后再 `self._snap()`，重取观测失败也进 notes（`:547-551`）。
2. **日首接线在 `longrun.py:1850`**（卡片写 `:1850` ✅）：`obs = self._ensure_on_farm(obs, rep)` 位于当天第一张观测之后、`last_obs`/`outdoor_obs` 初始化（`:1852-1859`）与主循环（`:1860`）**之前** ⇒ 后续窗口口径观测与 `outdoor_obs` 都基于"回到农场之后"的快照。顺序正确。
3. **`_farm_scope_work(self, obs) -> tuple[int,int] | None` 在 `longrun.py:553-566`**（卡片写 `:553-575`，函数实际 `:566` 结束，`_essence` 从 `:568` 起 —— 只是卡片行号偏大，非缺陷）：`_is_farm(obs)` ⇒ `None`（`:561-562`，人在农场时窗口就是真值）；`farm.complete is not True or farm.loaded is False` ⇒ `None`（`:564-565`）；否则 `(int(dryCrops or 0), int(ripeCrops or 0))`（`:566`）。**用 `dryCrops` 不是 `unwateredCrops`** ✅。
4. **字段不是幻觉**：`ripeCrops` 在 `mod/AgentFarm.Bridge/Contracts.cs:469` 有 `[JsonPropertyName("ripeCrops")] public int RipeCrops`，由 `FarmScan.cs:231 if (crop.fullyGrown.Value) _acc.RipeCrops++;` 累加 ⇒ `_farm_scope_work` 读的第二个分量真实可用。
5. **`work_reasons` 新增两条在 `longrun.py:1033-1039`**（卡片写 `:1037`/`:1039` = 两条 append 本身 ✅）：只在 `farm_work is not None` 时追加"farm 口径还有 N 格干/熟作物（先回去浇/收）"。
6. **`sleep_guard` 否决点在 `work_reasons` 之前**：否决块 `longrun.py:1085-1094`（卡片写 `:1088-1096`，含注释 `:1085-1087`），`reasons = self.work_reasons(obs)` 在 `:1095`、`no_work` 放行在 `:1096-1097` ⇒ "人没到地里"永远不可能被当成"地里没活"。且**顺序安全**：`night`（`:1073-1074`）与 `stamina`（`:1083-1084`）都在否决之前 ⇒ 深夜/体力见底仍允许睡，不会因"还有活"卡死。
7. **`self.farm`**：构造参数 `:381 self.farm = farm`，`_prepare()` 的旧调用点仍保留（`:2141`）。

---

## §3 独立变异证伪（我自己写 `scratch/_t40_falsify.py`，只改副本 `scratch/_t40_mut/agentfarm`）

跑法（cwd = 仓库根，`PYTHONPATH` 无所谓，脚本先占 `sys.modules` 再跑 `unittest`）：

```text
python scratch/_t40_falsify.py <none|A|B> tests.test_longrun.TestMorningIndoor.<test> [更多]
```

每次运行都打印 `USED_MODULE …\scratch\_t40_mut\agentfarm\longrun.py`（证明真的跑在副本上，不是 `brain/`）。

| 变异 | 注入 | 结果 | 红在哪个用例 |
|---|---|---|---|
| 对照 `none` | 无 | `RESULT successful=True failures=0 errors=0 run=2`、exit 0 | — |
| `A` | `_ensure_on_farm` 首行改成 `if True: return obs`（恒不回农场） | `RESULT successful=False failures=1 errors=0 run=2`、exit 1 | ✅ **`test_wakes_up_indoor_and_goes_back_to_the_farm`**：`AssertionError: 1 != 0 : [...]`；日志原文含 `1年 spring 7日 开始：FarmHouse … 作物 0（未浇 0）`、`stuck:守卫说还有活（人不在农场，但 farm 口径还有 1 格干作物（先回去浇））但没有任何作业区拿得出目标`、`→ needs_review`、`[run] needs_review：尾部连续 0/2 天（共 3 天，4 个动作，0.0 分钟）` |
| `B` | `_farm_scope_work` 首行改成 `if True: return None`（恒无 farm 口径证据） | `RESULT successful=False failures=1 errors=0 run=2`、exit 1 | ✅ **`test_no_work_is_never_asserted_from_an_indoor_window`**：`AssertionError: True is not false : (True, 'no_work', '确实找不到可做的活（地里的活干完了、也没法/没必要买种子）')` |

- 两个变异**各自只红一条、且正是卡片点名的那一条**（不是"红了就算"）。变异 B 下 `test_wakes_up_…` 仍绿：因为 `_ensure_on_farm` 没坏，白天会先把人带回农场，窗口观测就看得见干作物 ⇒ 该路径不依赖 `farm` 口径判活。这反过来证明**两处修复是互相独立的两条防线**。
- 两个坑都踩到了并已规避：`tests/test_longrun.py` 会 `sys.path.insert(0, brain)` 劫持 ⇒ 必须**先**预导入副本包（脚本里 `import agentfarm.longrun` 在 `loadTestsFromNames` 之前）；测试名必须写全 `tests.test_longrun.TestMorningIndoor.test_xxx`（裸方法名会变 `_FailedTest` 而退出码同样是 1，只看退出码会误判）。
- 变异只写副本；跑完 `git diff --stat HEAD` 仍空、两文件 SHA256 未变。

---

## §4 补充独立探针：`_ensure_on_farm` **失败分支**（提交里没有用例覆盖）有界且诚实

`scratch/_t40_probe.py`：假世界 = `MorningIndoorWorld`（睡醒在屋里）+ 一个 `ensure_location` **永远返回 `ok=False, code=timeout`** 的 worker，`target_days=2, max_days=2`：

```text
code=1 goto_calls=1 days=2 actions=4
  [1年 spring 6日] ended_by='sleep' reason='no_work:…' verified=True
  [1年 spring 7日] ended_by='sleep' reason='stuck:守卫说还有活（人不在农场，但 farm 口径还有 1 格干作物（先回去浇））但没有任何作业区拿得出目标' verified=False
    notes=['回不去 Farm：A* 未算出到 Farm 的路径', '找不到有活的作业区：人不在农场，但 farm 口径还有 1 格干作物（先回去浇）', '浇水证据不足/未浇完：…（scope=farm、tiles=1、crops=1、dry=1）']
goto_farm 事件 1 条：ok=[False] where=['day_start'] codes=['timeout']
```

⇒ 回不去时**不会**假成功、**不会**无界自旋（当天以 `stuck` 收尾、`verified=False`、退出码 1、只花 4 个动作），journal `goto_farm{ok:false}` + `rep.notes` 都留痕。这正是 run3 那种夜间寻路失败应当有的行为。

---

## §5 越界检查

- 提交 `cc2988e` 只含那 2 个文件、纯新增（0 删除），无 `docs/`、无 `mod/`、无 `tools/`、无版本号。
- 工作树（我这次验收期间）：`brain/`、`mod/`、`tests/` 对 HEAD 的 diff 为空；我只新增 `scratch/_t40_*.py` 与本报告。未碰游戏/桥（run4 正在跑）。

---

## §6 NIT 清单（都不阻塞，建议按序处理）

1. **NIT-1（建议顺手补）**：`_ensure_on_farm` 的**失败分支**（`:542-545` 的 notes 与 `goto_farm ok=false`）没有用例；卡片要求的变异也覆盖不到它。我有 §4 独立探针证明行为正确 ⇒ 建议把 §4 那个 `FailGotoWorker` 固化成第三条用例（断言：`goto_farm` 恰 1 条且 `ok=false`、`notes` 含"回不去"、当天 `stuck`、`verified=False`、动作数有界）。
2. **NIT-2（逻辑洞，低概率、需裁定）**：`_farm_scope_work` 在 `farm.complete is not True` 或 `loaded is False` 时返回 `None` ⇒ 若此时人又恰好**在室内**，守卫会退回 run3 的老路径（`work_reasons` 空 ⇒ 放行 `no_work`）。run3 现场 `farm.complete=true` 所以不会触发，且日首 `_ensure_on_farm` 正常时人已在农场 ⇒ 只在"**回不去农场 + farm 扫描不完整**"同时成立时才复发。建议二选一：(a) 把"人在室内且拿不到 farm 证据"也判 `keep_working`（有界：`idle_rounds>=3 ⇒ stuck`，§4 已证）；(b) 至少在守卫里 journal 一条"So 我在室内但 farm 证据不可用"，让复核看得见。**要不要改请你定，我不动生产代码。**
3. **NIT-3（取舍记录）**：`_ensure_on_farm` 一天只在日首调一次，失败后当天不再重试回家（下一游戏日重试）⇒ 白烧一天。可作为后续小改进（例如 `recovered` 计数里再试一次）。
4. **NIT-4（纯文档）**：任务卡引用的 `_farm_scope_work` 行号 `:553-575` 偏大（实际到 `:566`）、`sleep_guard` 否决点写 `:1088-1096`（实际 `:1085-1094`）；`_ensure_on_farm :527-551`、`work_reasons :1037/:1039`、日首接线 `:1850` 都准确。

---

## §7 B：`docs/_run3-evidence.md` 5 条断言逐条对账

数据源：`logs/longrun-3day-llm-run3.jsonl`（155 行 / 176 动作，**逐项与文档一致**）、`logs/run3-observe-start.json`、`logs/run3-observe-end.json`、`SMAPI-latest.txt`、存档目录。审计脚本 `scratch/_t40_audit.py`、`scratch/_t40_smapi.py`（只读）。

| # | 断言 | 结论 | 原文/读数 |
|---|---|---|---|
| 1 | spring 18 `farm.dryCrops` 32→0 | ✅ **对得上** | 独立观测：起跑前 `farm.dryCrops=32`（19:04:25，`run3-observe-start.json`）→ 跑完 `0`（19:11:06，`run3-observe-end.json`）；账本 spring 18 VERIFIED 那天 `day_end.final_water = {scope:"farm", tiles:132, crops:33, dry:0}` |
| 2 | `waterLeft 35→2` = 净耗 33 格 ⇔ 33 株 | ✅ **净耗对得上**（措辞小保留） | 独立观测 `wateringCan.waterLeft` 35 → 2 = **33**；账本 spring 18 `final_water.crops=33`。保留：跑完独立观测 `farm.crops=32`（文档 §5.4 已自陈"窗口截断时 farm 聚合也会变小"）⇒ "精确吻合 33 株"在独立观测口径上是 32 株，净耗 33 格无争议 |
| 3 | spring 19–22 四天 `day_start.location == FarmHouse` 且 `counts_scope == window` | ✅ **对得上** | 账本 4 条 `day_start`：`{day:[1,"spring",19..22], timeOfDay:600, crops:0, unwatered:0, location:"FarmHouse"}`；4 天 `day_end.final.counts_scope="window"`、`tillable=0/crops=0`，`ended_reason="no_work:…"`、`checks.watered_outdoor=false` |
| 4 | 5 次 `Synchronizing 'NewDay'`+`SaveGame.Save() completed`，SMAPI 行号 L4141…L4217 + 存档 mtime/size | ⚠️ **SMAPI 侧已不可复现；存档侧部分可核且吻合** | 现在 `SMAPI-latest.txt` = **19:15:49 起的 run4 会话**（424 行，NewDay/Save/after-save 命中 **0**；`logs\` 里也没有 run3 副本，只有 22:07 的 `smapi-sleep-window.txt`）⇒ L4141…L4217 **无法复核**（run4 起跑把文件覆盖了，非文档之误）。存档侧：`Wahaha_450799035` = **3579973 / 19:10:26.913**、`SaveGameInfo` = **25161 / 19:10:26.916**、`_old` = **3543468 / 19:10:23.367**（文档称"= 跨到 spring 22 那一档"）**逐字吻合**；文档里的起点 `3552427 / 18:58:05.645` 已被后续存盘覆盖、不再可核 |
| 5 | 0 崩溃 / 0 桥掉线 / 0 模态卡死 | ✅ 账本侧对得上；⚠️ SMAPI/进程侧同 #4 不可复现 | 账本事件：`bridge_down=0`、`modal_timeout=0`、`watchdog_stop=0`、`no_day_progress=0`、`modal_dismissed=0`；`finish={code:1, verified_streak:0, actions:176, minutes:5.9}`；6 个 `day_end` 里 `no_hard_failures` 仅第一个（`sleep_failed` 回不了家）为 false。SMAPI 关键词与"进程存活"当时可查、现已随日志覆盖，`logs\` 无进程快照 ⇒ 只能采信文档自述（其自述与账本一致） |

**额外核对（顺手，均 ✅）**：文档 §1 的事件计数与我复算**逐项一致**（day_start 6 / day_end 6 / decision 33 / outcome 33 / intent_verdict 31 / sleep 6 / blocked 7 / policy 4 / review 4 / intent_vetoed 3 / stage_exhausted 2 / stage_midway_leftover 2 / plots_capped 1 / idle 1 / plot_exhausted 1 / seed_gate 1 / plot_walk 1 / stage_no_target 1 / day_cap 1 / finish 1），"点名事件全 0"也一致（含 `goto_farm=0`，因为 run3 跑的是修复前的 `ab4b3aa`+help 文案；`git merge-base --is-ancestor ab4b3aa HEAD` = True，时序成立）；spring 19–22 四个日报告各活 **3.46/3.65/3.58/3.57 秒**，5 次跨日落在 t=339.66→354.02（≈19:10:13.7→19:10:28.0）—— 与文档"3.5 秒、16 秒里完成 5 次"一致。

**给 Lead 的两条取证建议（B 部分的可执行结论）**：
1. **run4 现在还在跑 ⇒ 建议立刻（停游戏前）把 SMAPI 当前窗口拷进 `logs\run4-smapi-window.txt`**，否则 run5 一起跑，run4 的行号级证据同样会消失。run3 这次的教训就是"行号级证据只活在 RAM 覆盖型的 `SMAPI-latest.txt` 里"。
2. 在 `docs/_run3-evidence.md` §4 加一句时间戳注记："行号读数时刻 19:11:31；该文件已于 19:15:49 被 run4 覆盖，行号不可再复核；可复核的是存档 size/mtime 与账本 `day_after` 对齐"。**可选**：把 run3 的 SMAPI 片段从机器上任何缓存/`SMAPI-crash.txt` 类残留里找回（本机 `ErrorLogs\` 只有 `SMAPI-latest.txt` 一个文件，已确认无残留）。

---

## §8 结论

- **A：PASS-WITH-NITS** —— `cc2988e` 的两处修复（日首回农场 + 用 `dryCrops/ripeCrops` 判"还有活" + 守卫室内否决）**方向正确、接线位置正确、字段真实**；我的独立变异把 A/B 分别钉在 `test_wakes_up_indoor_and_goes_back_to_the_farm` / `test_no_work_is_never_asserted_from_an_indoor_window` 上（各只红一条）；回不去的失败分支经独立探针证明**有界且如实记账**；无夹带、321 OK。唯一"建议做"的是 NIT-1（补失败分支用例）；NIT-2 是低概率逻辑洞、需你裁定；NIT-3/4 记录性。
- **B：4/5 对得上**；第 4 条的 SMAPI 行号侧（及第 5 条的 SMAPI/进程侧）**因 run4 起跑覆盖日志而不可复现**，已在 §7 写明；存档 size/mtime 链与账本 `day_after`/观测对齐**全部吻合**。文档核心结论（spring 18 浇水 32/32 真达标、spring 19–22 因"睡醒在屋里"连睡 4 天、`dry=33` 与 `day_start crops=0` 自相矛盾）**成立**。

---

## §9 task-41 验收预案（待 Lead 说"run4 已起跑"后才开工）

Lead m02286 把我这份报告的两条 NIT 并入 **task-41**（同一写者、同一文件 `brain/agentfarm/longrun.py`，硬约束"run4 起跑后才许动"）：**NIT-2 走 fail-closed**、NIT-1 补"回不去农场"用例。task-41 卡面主体：**`ui.eventUp==true` + `isModal==true` 一律视为阻断模态**（记 `event_blocked`、不 dismiss/不 sleep/不 load_save、`ended_by="blocked_event"`、`checks.no_blocking_modal=False`、`run()` 早退含 `blocked_event`），且 `eventUp` 为假时既有四类行为一字不变。

**卡面已升到 rev4**（`team_task_get task-41` = revision 4、owner=dev-coder、in_progress）：追加 1 收 NIT-1/NIT-2，追加 2 收我的机制修正（第 9 条有界性来源 = `longrun.py:1900-1909` 单次分支；第 10 条 fail-closed 破功点；第 11 条我的 m41a/b/c 矩阵）。⇒ **验收以 rev4 卡面为准**（"卡面 + 电文"只在卡面未写到处兜底；rev1 只写了 eventUp 政策）。**run4 已于 19:25:4x 起跑、随即死亡**（Lead 亲查：`logs\longrun-3day-llm-run4.jsonl` 只 14 行、最后一条 `intent_verdict` 在 t=12.85s、mtime 19:25:48.099 后不再写、**无 `finish` 事件**、系统无 python 进程；怀疑是调度"前台命令被回收"而非 brain bug）⇒ **run4 无有效结论、不引用它的结果**。`logs\run4-smapi-window.txt`（444 行 / 38581 B / 19:21:21）仍是 run4 会话窗口（run3 那 5 组 NewDay 行不在其中，别误当 run3 证据）。**在 Lead 明确说"游戏/桥可用"之前，不碰游戏与桥。**

**我打算怎么验（rev4 对齐版）**：

1. **夹带与对象**：`git show <commit> --stat` 只许那两个文件；两文件 SHA256 记录并与写者自报逐字比；`git diff --stat HEAD` 对这两个文件为空（工作树==提交内容）；`manifest.json`/`bridge.py:39` 仍 0.7.23（未 bump）；`mod/`、`tools/verify-run3.py` 零改动。
2. **读数**：`py_compile` exit 0；全量 `discover -s tests` **≥321 且只许升**；新用例 `-k event` 全绿。
3. **eventUp 政策（静态）**：模态守卫在**任何** dismiss/sleep/load_save 之前读 `ui.eventUp`（`mod/AgentFarm.Bridge/Contracts.cs:509 [JsonPropertyName("eventUp")] public bool EventUp`，由 `WorldSnapshot.cs:832 v.EventUp = Game1.eventUp` 写入；**并且 `WorldSnapshot.cs:845-848` 的 `IsModal` 已经 `|| v.EventUp`** ⇒ 事件对话框在当前代码里本来就会被判成模态，缺的只是"脑侧区分这是事件而不是可关的框"）；`eventUp=true && isModal=true` ⇒ 只写 journal `event_blocked`（`activeMenu`/`activeMenuText`/`dialogueIsQuestion`/`dialogueResponses`/`tile`/`timeOfDay`/`worldSeq`）并把当天收成 `blocked_event`。
4. **回归护栏（可判定清单见 §9.1）**：`eventUp=false` 时 ①普通 DialogueBox（无提问）仍关一次 ②`LevelUpMenu` 仍关 ③`SaveGameMenu`/`NewDaySavingMenu` **只等不关** ④职业非空仍 `levelup_profession_pending` 停下 ⑤睡觉提问仍走 task-33 配方。判定 = 跑既有用例 + **diff 里该测试类不得有一行断言被删改**。
5. **NIT-2 fail-closed（必查）**：`farm.complete is not True`/`loaded is False` 且人不在农场 ⇒ `sleep_guard` **不得**出 `no_work`，须返回 keep_working 且理由点明 farm 证据不可用；**有界性来源 = `longrun.py:1900-1909` 单次分支**（`_work_spot_plot(obs) or _near_player_plot(obs)` 为 `None` ⇒ `_do_sleep(why)` + `break`，一天只走一次），**不是** `idle_rounds`（后者只在 `:1982-1990` 走完 `_execute` 且世界指纹没变时递增）；另 journal 一条 `farm_evidence_unavailable`（带 `complete`/`loaded`/`location`）。**破功点（rev4 第 10 条）**：若 `work_reasons()` 不同时给出该理由，`:1905` 的 `("no_work" if not reasons else …)` 会让 `why="no_work"` ⇒ run3 连睡路径原地复活。
6. **NIT-1**：用例覆盖"回不去农场"分支。我的独立探针（`scratch/_t40_probe.py`：`FailGotoWorker` 恒 `ok=False,code=timeout`）给出的期望形态（rev4 第 7 条已采纳）：`goto_farm` 恰 1 条且 `ok=[False]`、`rep.notes` 含"回不去 Farm"（`:542-545`）、当天收成 `stuck` 语义（探针里进 `_do_sleep` 后 `rep.ended_by` 落成 `"sleep"`、`ended_reason` 以 `stuck:` 开头 ⇒ 我按**卡面 `ended_by=="stuck"`** 判、reason 前缀作交叉核对，两者不一致就报出来让 Lead 定）、`verified=False`、动作数有界（2 天 4 个动作）。
7. **我的独立变异矩阵（rev4 第 11 条，命名已对齐）**：**m41a** = `keep_working` 退回 `no_work` ⇒ 必须红在"室内 + farm 证据不可用"用例；**m41b** = 只让 `_farm_scope_work` 恒 `None`（`work_reasons()` 不加理由）⇒ 应被"`ended_reason` 前缀不是 `no_work:`"的断言抓住；**m41c** = 去掉 `eventUp` 判断 ⇒ eventUp 用例必红。三态都只注入副本（照 `scratch/_t40_falsify.py` 的"预导入副本包"写法），生产文件哈希事后必须不变。
8. **假世界探针**：`ui.eventUp=true` + `activeMenu="DialogueBox"` + `activeMenuText="Hello Jay!"` + `dialogueResponses=[]`（复现 run4 现场 19:16–19:18 形态）；fail-closed 用"室内 + `farm={loaded:false}`"与"室内 + `complete:false`"两态各跑一次。

### §9.1 "eventUp 四类回归护栏不许改既有断言" 的可判定清单（rev4 第 3/4 条）

运行目录 = 仓库根；判定口径 = `Ran N tests / OK`（pwsh 把 unittest 的 stderr 报成 `[exit code: 1]` 是噪声）。行号取自 rev4 时的 `tests/test_longrun.py`。

| 护栏（rev4 第 3 条） | 既有用例（ID 逐字） | 期望 |
|---|---|---|
| ① 普通/提问 DialogueBox 仍按既有口径关（不注入按键） | `TestTask11ModalGuard.test_question_modal_dismissed_with_no_key_injection`（`:1673`） | OK；`kind=="question"`、无按键注入 |
| ② `LevelUpMenu` 关一次 / 连出两次都关 | `…test_plain_levelup_dismissed_save_menu_only_waited`（`:1593`）、`…test_consecutive_levelups_are_both_dismissed`（`:1621`） | OK；`dismissed==["LevelUpMenu"]`、`dismiss_calls==1` / `==2` |
| ③ `SaveGameMenu`/`NewDaySavingMenu` 只等不关 | `…test_wait_only_modal_timeout_stops_the_day`（`:1689`） | OK；`dismiss_calls==0`、`modal_timeout[0]["menu"]=="SaveGameMenu"` |
| ④ 职业非空停下；字段缺失按未知 | `…test_profession_choice_is_never_dismissed_and_day_is_not_verified`（`:1638`）、`…test_missing_professions_field_is_treated_as_unknown`（`:1657`） | OK；`dismiss_calls==0`、`ended_by=="blocked_modal"`、`verified is False` |
| ⑤ `eventUp=false` 睡觉提问仍走 task-33 配方 | `tests.test_farmwork.TestSleepCrossDay` 全部 11 条 | OK |
| ⑥ 模态清理不许回归（task-15） | `TestTask15DayAccounting.test_env_retry_clears_the_blocking_modal`（`:1898`） | OK |
| ⑦ 室内日首回农场不许回归（task-40） | `tests.test_longrun.TestMorningIndoor` 2 条（`:2222`） | OK |

命令（`$py` = 运行时 python）：

```text
$env:PYTHONUTF8="1"; $env:PYTHONPATH="$pwd\brain"
& $py -m unittest discover -s tests -p "test_longrun.py" -k TestTask11ModalGuard -k TestMorningIndoor -k TestTask15DayAccounting -v
& $py -m unittest tests.test_farmwork.TestSleepCrossDay -v
```

**"不许改既有断言"的机器判定**（不信自查报告）：
1. `git diff -U0 HEAD -- tests/test_longrun.py` 中，落在 `class TestTask11ModalGuard`（`:1569`）到 `class TestTask28BusySpin`（`:1719`）之间的**删除行**（`-` 开头、非 `---`）必须为 **0** —— 该类 6 条用例只能原样保留；新增 event 用例应另起 `class`（推荐）或在类尾追加。
2. 上述 6 个测试 ID 在提交后仍能被 `-k` 精确命中（改名 = 变相删断言 ⇒ 至少记 NIT；若改名同时放宽断言则判 FAIL）。
3. 新 event 用例必须是**新增**：新增行数 ≥ 新用例数 × 其断言数，且名字不与既有 6 条重名。
4. 任一既有断言被**放宽**（例如 `dismiss_calls==1` 改成 `<=1`、`verified is False` 改成布尔断言）⇒ 判 **FAIL** 并报行号。

### §9.2 追加机器判据 + 结论必须写清的两件事（Lead m02347）

**A. 新闸门"run3 连睡病复发"（Lead 加在 `tools/verify-run3.py:436-448`，我独立复跑核对）**：`_end_reason.startswith("no_work")` 且 `final_water.dry > 0` ⇒ 记问题「ended_reason 以 no_work 开头，但 final_water.dry=N（户外还有干作物却判"今天没活" ⇒ run3 连睡病复发）」。我亲跑五本（`& $py tools\verify-run3.py --journal <f>`，输出存 `scratch\_t41_vr_*.txt`）：

| 账本 | exit | 新闸门命中 |
|---|---|---|
| `scratch/journal-green.jsonl` | **0**（VERIFIED） | 0 |
| `logs/longrun-3day-llm-run3.jsonl` | 1（needs_review） | **4**：spring 19/20/21/22，`dry=33/32/32/32` |
| `logs/longrun-3day-llm-run2.jsonl` | 1（needs_review，判决未变） | 0 |
| `logs/longrun-rehearsal-0.7.22.jsonl` | 1（needs_review，判决未变） | 0 |
| `logs/longrun-3day-llm-run4.jsonl` | 1（13 行、无 `finish`，属预期） | 0 |

⇒ 与 Lead 的读数**逐项一致**。**task-41 验收时这条作为硬判据之一**：新代码上线后，凡"`no_work` 收尾 + `dry>0`"必须为 0（绿账本形态仍 exit 0）。

**B. 结论里必须写清"本来就成立"的事实**（避免把已有判定当成新修复）：`mod/AgentFarm.Bridge/WorldSnapshot.cs:845-848` 的 `IsModal` **本来就 `|| v.EventUp`**（字段 `Contracts.cs:509`，写入点 `:832`）⇒ 事件对话框在 task-41 之前**已经是模态**；task-41 的新增价值只是**脑侧区分"事件（不可关）"与"可关的框"**，不是"首次把事件识别为模态"。这条要写进 §结论的"新修复 vs 既有事实"一段。

写范围仍只有 `docs/_review-*.md` + `scratch/`；对象是**未提交在制**时就只读复核，未冻结前不跑全量当证据（避免撞上写者并行改动的假红）。
