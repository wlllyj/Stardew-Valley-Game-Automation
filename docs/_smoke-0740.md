# 0.7.40 七步冒烟（A2 版）· 证据

> 目的：验 **0.7.40 的两个修复 + 回归**（① `slot_relief` 空格压力通道 ② §8 意图对账 `intent_no_target_evidence:ship`），不是成绩验收。
> 结论先行：**步 1、2、3、4 PASS；步 5 无法判定（本次没有 clear_area ok 步）；步 6 FAIL（第三次跨日没落盘）；步 7 FAIL（新出现 1 条 §8 红 `missed:intent_no_reason:water_area`，task-233 的 `ship` 那条已消失）**。
> 两个重点回归项：**① 空间压力通道"机制生效但不够"** —— 日报告仍 3/3 `inventory_blocked`；**② §8 的 ship 红已修，但冒出新的 water_area 红**。

## §1 环境与版本指纹

- Lead 装机：冻结提交 **`6f9b797`**；`deploy-mod --no-quit` = 0.7.39→0.7.40（dll **281088 B** / manifest **64311 B**），桥 `modVersion=0.7.40 port=17890`，自动读档；`goto Farm` ok（hop1 `[3,12]→[64,15]` 7645ms）。
- `preflight --expect 0.7.40 --save-baseline logs\run10h-baseline.json` ✅：第 1 年**秋 26 日 06:10 sunny**、Farm(64,15)、体力 270/270、钱 **1977g**、作物 34、`unwatered 2`、`dryCrops 34`、`waterLeft 6`、`tillable 141`、无模态、`worldAdvancing true`。
- **五文件指纹 5/5 逐字 MATCH（size 也一致）**：
  `longrun.py B432CC5439B6D2FCA6E99E938AF688A66D96520281D3EA066C988277C0C6231E (547868)` /
  `farmwork.py B7B4545414DC47E7D5392550E179B8113C645CAE1111950A3F4E678E3F6C76B3 (222811)` /
  `bridge.py 84281FEE6F125AF4FC901B1602D6402CD98F749C4B745DC071E3F84AA2D71B30 (64904)` /
  `dll FF05225C6846D80C6CCF4E8B16A15F399FACCBED572705DF886486A8E419BD08 (281088，与 0.7.39 字节相同)` /
  `manifest.json 57280F1D33AF2D5DEBCB7369A44E030B1B35CA26CC0A9D978434BE274AA35869 (64311)`。
- 骨架 `scratch/smoke-0740.py`（由 `smoke-0739.py` 参数化：`--expect-version 0.7.40`、journal `logs\longrun-smoke-0740.jsonl`、tag `run10h`）；`--dry-run` 体检 = `mod_version 0.7.40 / version_matches True / hasSaveLoaded True`。

## §2 七步结果

| 步 | 内容 | 结果 | 备注 |
|---|---|---|---|
| 1 | `debug_dump crafting_recipes/Furnace` | **PASS** | `matchedCount=1`、无 `unknown_skill` |
| 2 | `debug_dump trigger_actions` | **PASS** | 可读、无 `InvalidCastException` |
| 3 | 单技能砍树（A2：≤3 次有界 `use_tool`） | **PASS** | `(22,13)` 3 次调用后 `kind=None`（树已消失）；体力 258.6→230.1 |
| 4 | 1 日长跑 ⇒ `intent_coverage[]` + `<journal>-gaps.json` | **PASS（管道）；焦点回归 FAIL** | `finish` 出现、`intent_coverage` 在场、gaps 文件生成；但 **3/3 天仍 `inventory_blocked`** |
| 5 | `clear_area` 逐格判据活 | **无法判定** | 整跑 `clear_area` 的 ok 步 = 0（不是失败，是这跑没清障） |
| 6 | 跨日落盘六串 6/6 配对 | **FAIL** | `NewDay 3 ≠ Save called 2`（第三次跨日没落盘，根因见 §7） |
| 7 | analyzer §8 无红 + verify §8 只 info | **FAIL** | §8 专属红 1 条：`missed:intent_no_reason:water_area`；`missed:intent_no_target_evidence:ship` **已消失**（task-233 生效）；verify 侧仍 0 条 §8 problem（分工成立） |

## §3 步 1 / 步 2 原文要点

- 步 1：`table=crafting_recipes` 命中 `Furnace` **1 条**；无 `unknown_skill`（0.7.37 的 `KnownSkills` 白名单漏项坑已闭合）。
- 步 2：`trigger_actions` 可读、无 `InvalidCastException`；逐表 fail-closed 的 `type/error` 字段在场。

## §4 步 3（A2 版）+ 骨架 bug 修正

1. **A2 首跑记成 `use_tool_calls=0 / kind_trace=[]` 直接 FAIL —— 是骨架自己的 bug**：我把 `tool_ineffective` 抛出的 `BridgeError` 当成"中止条件"`break` 循环，等价于「一次都没打就判失败」。**已修**：异常只记留痕（`use_tool_errors[]`）→ observe → **继续下一次调用**（最多 3 次）。这条 bug 与被 Lead m03933 作废的旧口径同源，写在这里备查。
2. **修后读数**：窗口内 `kind=="tree"` **144** 格 / **90** 格有四邻可站格；选中 `(22,13)`；`move_to`（邻格）**ok 21566ms**（`worldSeq 67→152`）；**3 次调用**：
   `kind_trace = [tree@ws152/体力247.2, tree@ws153/体力235.8, null@ws153/体力230.1]` ⇒ 第 3 次后该格 `kind=None`（树已消失，`after=null`）；**体力 258.6→230.1（−28.5 ≈ 18 刀，真挥了）**、`worldSeq 152→153`。
3. **判据**：A2 要求"`kind` 变化（`stump`/消失）"⇒ **PASS**。两次 `tool_ineffective`（每次内部 6 下、`UsingTool=True`）只作过程留痕，**按 Lead m03933 不作失败证据**。
4. 如实声明：本次斩的是**新树** `(22,13)`（上一轮 `(39,14)` 那次单发 6 刀留在世界里的"轻伤"没有复用），所以 `calls=3` 是完整的"6+6+6 刀"读数。

## §5 步 4（1 日跑 ⇒ 3 个日报告）

```json
{"event":"finish","t":596.05,"code":1,"verified_streak":0,"actions":645,"minutes":9.93,
 "stages_seen":["harvest","till_area","water_area"],"no_unmet_stages":false,
 "unmet_days":["1年 fall 26日","1年 fall 27日","1年 fall 28日"],"stuck_flushes":0}
```

- 账本 **284 行**；`journal` / `.console.log`(10021 B) / `.console.err.log`(**0 B**) / `-gaps.json`(1410 B) / `-lessons.json`(2621 B) / `-llm.jsonl`(21918 B) 全部在场。
- **3 个日报告全部 `ended_by=inventory_blocked`、`verified=false`**：`fall 26` 37 ok/4 skip、`fall 27` 28/17、`fall 28` 31/36；三天 `checks = {slept_by_us:true, no_blocking_modal:true, no_hard_failures:true, unreachable_within_bound:true, refused_within_bound:true, no_unmet_stages:false, crops_watered:true, watered_outdoor:false, day_justified:false, zero_action_evidenced:true}`；`ended_reason` 原文 = `inventory_blocked:背包满（空格 0）且今天已经腾不出格子：不是没活、也不是 stuck —— 是背包堵住（先去出货/卖材料腾格，明天再收）`。
- **`day_end.intent_coverage[]` 在场**（14 / 11 / 19 条）：`harvest` 反复出现 `req=12 / ok=0 / failed=12 / steps=36 / reasons={"no_slot":12}`（三天都出现，合计 5 条这种记录）；`water_area` 有 `req=29 ok=24 failed=1 unexec=4 / reasons={"unknown_evidence":4,"gated":1}` 这类"真做成了一部分"的记录。
- **`slot_relief` 7 条 —— 机制确实动起来了**（这是 0.7.40 的正面证据）：

| t | freed | 行数 | money | 卖出（slot/qid/stack） | 备注 |
|---|---|---|---|---|---|
| 0.34 | **0** | 12→12 | 1977→1977 | 9/`(O)262`/1 | `failed=true`，`blocked_reason="卖了 1 叠但背包行数没减少（12→12）⇒ 出货/卖出没有真的生效"`（见 §5.4） |
| 254.21 | 1 | 12→11 | 2014→2014 | 6/`(O)262`/10 | `crop_overflow:below_keep_whole_stack` |
| 254.37 | 1 | 11→10 | 2014→2014 | 6/`(O)262`/10 + 9/`(O)388`/6 | 同一轮 round2 |
| 369.29 | **3** | 12→9 | 2014→2014 | 6/`(O)262`/10 + 9/`(O)388`/6 | `shipped=true` |
| 462.69 | 1 | 12→11 | 2461→2461 | 10/`(O)262`/1 | |
| 462.88 | 1 | 11→10 | 2461→2461 | 10/`(O)262`/1 | `shipped=true` |
| 563.84 | 2 | 12→10 | 2461→2461 | 10/`(O)262`/1 | `shipped=true` |

  ⇒ **`freed>0` 出现 6/7 次、卖出的叠有 `sold[]` 明细、`rows 12→9/10`、钱随次日结算 1977→2014→2461**；`sell` 事件 10 条全 `ok=true`。**但**：每天只能腾出 1–3 格，而 `harvest` 每天要 12 格 ⇒ 腾出来的格子立刻被塞满 ⇒ 当天仍走到 `rounds=3 用满、背包仍然满` ⇒ `inventory_blocked`。**结论：通道修好了，但"腾格力度 vs 收获需求"的缺口还在**（这是 0.7.41 的口径问题，不是本卡能修的）。
- **`(O)378/390/382` 未被卖空**：`sell` 明细里没有这三种 qid（卖的是 `(O)262` Wheat、`(O)388` Wood、`(O)Moss`、`(O)178` Hay）。✔ 符合你的保留要求。
- **`logs\longrun-smoke-0740-gaps.json`**（`agentfarm-gaps/1`，4 条）：`dirt/no_slot ×148`（fall 26→28，样本格 `[[60,25],[61,25],[62,26],[62,27],[63,18]]`）、`dirt/gated ×12`、`dirt/unknown_evidence ×5`、`dirt/blocked_tile ×2`。

### §5.4 一个必须如实记的观察（新形态的"回执 ok 但世界没变"）
第一天开局 `t=0.31` 的 `sell`（slot 9、`(O)262`×1、`why=space_pressure`）回执 **`ok=true`**；0.03 秒后 `slot_relief` 自己量到 **行数 12→12、freed=0**，于是记 `failed=true / blocked_reason="卖了…没有真的生效"`，紧接着 `t=0.34` 直接 `inventory_blocked` 收工。**同一天后面的 `sell`（t=254/369/462/563）都真的生效了**。⇒ 现象 = **每天开局的第一次 sell 可能"回执 ok 但没生效"**（机制【无法判定】：可能是开局时槽位/背包快照过期，也可能是当晚出货箱结算路径的边界）。本报告只列证据，不猜测；建议 Lead 决定是否立案。

## §6 步 5：无法判定（数据不足，不是失败）

- `day_end.stages[]` 里没有 `clear_area` 的 ok 步：`clear_area_ok_steps=0 / clear_stage_ok_tiles=0 / clear_total_ok=0` ⇒ 本跑没有清障动作，**逐格判据"活不活"无法验证**。按你的纪律记【无法判定】，不判 FAIL。

## §7 步 6：FAIL —— 第三次跨日没有落盘（根因已定位到行）

- SMAPI 六串（窗口 = 本跑 12:08:39–12:20:43，共 3309 行）：
  `NewDay = 3`（L1209 `12:14:43`、L2308 `12:18:20`、**L3304 `12:20:40`**）；
  `before save = 2`（L1219、L2325）/ `Save called = 2`（L1220、L2326）/ `Save task = 2`（L1221、L2327）/ `completed = 2`（L1224、L2330）/ `after save = 2`（L1225 `12:14:49 starting fall 27`、L2331 `12:18:25 starting fall 28`）。
  ⇒ **第 1、2 次跨日 6/6 配对；第 3 次只有 `NewDay`，后面全缺。**
- 第 1、2 次为什么能落盘（关键原文）：
  - `L1218 12:14:44 dismiss_modal: ShippingMenu → okClicked()（已反射调用 ShippingMenu.okClicked()，只等游戏自己关）` ⇒ `L1219 before save` ⇒ `L1220 SaveGame.Save() called.` ⇒ `L1225 after save, starting fall 27 Y1.`
  - `L2324 12:18:20` 同型 ⇒ `L2325/L2326` ⇒ `L2331 after save, starting fall 28 Y1.`
  - 即：**新的一天先由 `dismiss_modal` 把晨间 `ShippingMenu` 关掉（触发 `okClicked()`），保存链才走完**（task-47 的机制在 0.7.40 上依旧；brain 的 `modal_dismissed` 事件 ×3 与之对应）。
- 第 3 次跨日原文（`L3295–L3309`）：
  ```
  3300 [12:20:39 TRACE AgentFarm Bridge] sleep：已用游戏自己的 answerDialogue 应答睡觉提问（选 "Yes"…）
  3301-3303 sleep：关框第 1/2/3 次（当前没有对话框（不用关））
  3304 [12:20:40 TRACE SMAPI] Synchronizing 'NewDay' task...
  3305 [12:20:40 TRACE game] Applied trigger action 'Mail_Mom_5K' with actions [AddMail Current mom1].
  3306 [12:20:41 TRACE SMAPI]    task complete.
  3307 [12:20:41 INFO  AgentFarm Bridge] POST /v1/exec → 200 · 1610ms · worldSeq=1657
  3309 [12:20:50 INFO  AgentFarm Bridge] GET /v1/health → 200 · 0ms · worldSeq=1657
  ```
  ⇒ `NewDay` **task complete 了，但没有 `before save` / `Save called`**，之后到 12:24 也没有。**根因 = 这一跑在第 3 次跨日之后立刻 `finish` 并退出（PID 11948 于 12:20:43 消失），没有人再关那个晨间 `ShippingMenu`，于是这次日切保存永远没开始。** 这不是"游戏跳过保存"（前两次证明只要关框就会保存），而是**跑尾声的时序缺口：最后一次跨日的保存没人兜底**。
- **存档证据（现在）**：`Wahaha_450799035` **4464675 B / 2026-10-18 12:18:23**、`SaveGameInfo` 30992 / 12:18:23、`_old` 4515874 / 12:14:47、`SaveGameInfo_old` 31034 / 12:14:47 ⇒ **落盘停在"第 2 次跨日"（fall 28 清晨）**，之后的世界（fall 28 全天 + 跨到 winter 1）都在内存里、未落盘。

## §8 步 7：FAIL —— §8 意图对账仍有 1 条红（ship 那条已修）

- `tools\analyze-longrun.py --journal … --window 3` ⇒ **rc=1，有红 38 条**；执行 `--days 3` 的 `verify-run3` ⇒ rc=1、`needs_review`、尾部连续 VERIFIED **0/3**、`--window 3` **不启用窗口降级**（窗口外历史问题 0 条）。
- **§8 头部对账**（原文）：`未执行意图: 意图 44 条（覆盖 3 天；0 步 20 条 / 其中无原因码 1 条；计划无对账 0 条；原因码 blocked_tile×1、gated×4、no_slot×16、no_target×3、superseded×6、unknown_evidence×12）`。
- **§8 专属红 = 1 条**：`missed:intent_no_reason:water_area` —— 即那 **1 条「`executed_steps=0` 且 `reasons={}`」** 的 `water_area` 意图记录（违反 `docs/_run10-criteria.md` §8.3「0 步必须给原因码」；应有 `unknown_evidence`/`superseded` 之类）。
- **好消息（task-233 验收面）**：`missed:intent_no_target_evidence:ship` **已经不在红清单里**（上一跑的那条已消失）；`verify-run3` 侧对 `intent_coverage` 仍然 **0 条 problem**（只有事件统计行里出现 `intent_verdict`）⇒ **§8 分工仍然成立**，只有 analyzer 一方报红。
- 其余 37 条红都是**日级未达标**（`missed:check:day_justified / no_unmet_stages / watered_outdoor`、`missed:harvest`、`missed:seeds`、`missed:stage_*`、`missed:env_fail` 等），不是 §8 管道问题。

## §9 收尾状态（游戏仍在运行，按你 "不退游戏" 的指令）

- 跑完后**没有退出游戏**（`stop-game.py` 未执行）。当前现场（我 12:26 只读 observe 一次）：`clock = winter 1 06:00 sunny`、`player = FarmHouse (9,9) / 体力 270 / **money 2767** / isInBed true`、`ui = {activeMenu:"ShippingMenu", isModal:true, eventUp:false, ...}`、`liveness = {worldAdvancing:false, secondsSinceClockMoved:60.7}`、`worldSeq=1657`、游戏进程仍 1 个。
- 这意味着：**那个没落盘的 `ShippingMenu` 现在还开着**（它挡着世界时间）。若之后要退出，**先关框等保存链走完再退**，否则 fall 28 整天的进度会丢；存档主档目前 = fall 28 清晨（12:18:23）。
- 本卡未做：`load_save`、`buy`、`craft`、`place`、手改存档；`sell` 只发生在 `slot_relief` 内部（受制裁路径）；`use_tool` 仅步 3 的 3 次有界调用。

### §9.1 现场抢救与优雅退出（Lead m04068 步骤 1–3，事后补记；这一步同时是步 6 根因的反证）

- **关框前（只读）**：`ui={activeMenu:"ShippingMenu", isModal:true}`、`clock=winter 1 06:00 sunny`、`player={FarmHouse(9,9), 体力270, money 2767, isInBed:true}`、`liveness={worldAdvancing:false, secondsSinceClockMoved:190.1}`；存档四件 = 主档 **4464675 B / 12:18:23 / sha256 `2D9B92D6CB401B36…`**、`SaveGameInfo` 30992 / 12:18:23、`_old` 4515874 / 12:14:47、`SaveGameInfo_old` 31034 / 12:14:47。
- **发一次 `dismiss_modal`**：回执 `ok=true`、`dismissPath="ok_clicked"`、`waitedMs=6768`、`menuGone=true`、`worldSeqBefore/After=1657`、reason `出货/存档菜单处理完毕（路径=ok_clicked：已反射调用 ShippingMenu.okClicked()…等了 6768ms；菜单已消失）`。
- **同一秒保存链补齐（SMAPI 原文 5 行，12:23:53–12:23:56）**：
  `Context: before save.` → `SaveGame.Save() called.` → `Synchronizing 'Save' task...` → `SaveGame.Save() completed without exceptions.` → **`Context: after save, starting winter 1 Y1.`**
  ⇒ 存档主档 **4464675/12:18:23 → 3104089 B / 12:23:54**、`SaveGameInfo` 30992 → 31188；`_old` 轮换为上一对（4464675/12:18:23）。`ui.isModal → false`（`activeMenu=null`）。
- **`worldAdvancing` 仍为 false（如实记）**：关框后 `worldAdvancing=false, secondsSinceClockMoved≈197` —— 玩家 `isInBed=true`（睡觉技能把角色留在床上，`FarmHouse(9,9)`），所以时钟不走。**这不影响"保存已补齐"的结论**（保存链 5 行齐全 + 主档前进），但"世界时间恢复"要等角色下床才成立。
- **反证步 6 的根因**：同一个 `ShippingMenu`，没人关时（跑已退出）`NewDay` 之后**永无**保存链；**关一次**就立刻补齐 5 行 + 主档前进 ⇒ 步 6 的红是"跑尾声没人关框 + 没人等落盘"，**不是游戏跳过保存**。
- **优雅退出（m02833）**：`tools\stop-game.py` rc=0（原 pids `[24756]`）⇒ 进程 **0** / `bridge.json` **已删** / 17890 仅 **2 条 TIME_WAIT**（无 LISTENING）/ **存档四件退出前后逐字节未变**；SMAPI 尾 `12:24:13 Disconnected: ClosedGame → Disposing... → 已删除发现文件 …\bridge.json`（无 Event 1000/1001）。
- **「fall 28 全天是否保住」**：**保住了** —— 12:23:54 的这次保存写入的是内存里的**winter 1 06:00 状态**（money 2767 已含 fall 28 的出货结算），`_old` 保留的是 fall 28 清晨那份（4464675/12:18:23）；两次落盘之间没有丢失的游戏日。
- 取证脚本：`scratch\_t_save_winter1.py`；读数 JSON：`scratch\t-save-winter1.json`。
- 观察留痕（不解释）：主档体积 4464675 → 3104089（−1.36 MB），`after save, starting winter 1 Y1` 为权威；本报告不据此推断内容差异。

## §10 结论与建议（先结果，后建议）

1. **管道结论**：步 1/2/3/4 PASS、步 5 无法判定、步 6 FAIL、步 7 FAIL ⇒ **冒烟未全绿**，其中步 6 是**新版硬问题口径下的真红**（每次跨日必须落盘）。
2. **0.7.40 两个修复各自的验收**：
   - **空格压力通道（task-232）**：**机制生效**（7 次 `slot_relief` 里 6 次 `freed>0`、`sold[]` 明细、行数真的降、钱随次日结算上升），**但强度不够**（日腾 1–3 格 vs 收获需 12 格）⇒ 3/3 天仍 `inventory_blocked`。⇒ 建议：**不判 task-232 失败**（通道确实通了），但它不是"日报告不再 inventory_blocked"的完整解 —— 需要下一步"腾格力度/收获批次"口径（或降低单日 harvest 分配）。
   - **§8（task-233）**：`ship` 那条**已修**；**新出现 1 条** `missed:intent_no_reason:water_area`（0 步无原因码）⇒ 建议立案（可能是"`water_area` 意图被 superseded 时 `reasons` 丢了"这一类）。
3. **步 6 建议**：这是**跑尾声时序缺口**，建议在 `longrun.py` 收尾路径上加一条"最后一次跨日后等落盘确认（关 `ShippingMenu`→等六串→超时如实记 `save_missing` 并进 checks）"的守护；别把"NewDay 完成"当"日切完成"。
4. **存档状态提醒**：当前游戏在 `ShippingMenu` 上、fall 28 全天未落盘；退出前必须先关框等保存（否则丢一天）。
5. 本报告**不作为成绩/验收证据**（1 日跑 0 VERIFIED），只作 0.7.40 管道冒烟。

## §11 保留物

`logs\longrun-smoke-0740.jsonl`(284 行) / `.console.log` / `.console.err.log`(0 B) / `.pid` / `.version.json` / `-llm.jsonl` / `-lessons.json` / `-gaps.json` / `-baseline.json`；`logs\smoke-0740-verify.txt`、`logs\smoke-0740-analyze.txt`；`scratch\smoke-0740.json`（七步累计）；`scratch\smoke-0740.py`；`scratch\_smoke0740_digest.py`、`scratch\_smoke0740_smapi.py`（只读取证脚本）。
