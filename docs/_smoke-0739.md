# 0.7.39 真机冒烟报告（七步）

**状态**：已跑完并优雅退出（游戏进程 0）· **结论：管道 5/6 项 PASS，步 3 待下一轮 bring-up 用 `--only 3` 补跑；步 7 有一条 §8 相邻红待裁**
**日期**：2026-10-18（本机 +07:00）· 执行：machine-runner（single-writer）· 数据源：`logs/longrun-smoke-0739.jsonl`（220 行）、`logs/smoke-0739-smapi-window.txt`、`scratch/smoke-0739.json`

> 口径提醒：**冒烟验管道不验成绩**。本次 1 日跑没有 VERIFIED（3 天都因 `ended_by=inventory_blocked` 收工），按 Lead m03837 的裁定，只要 `day_end.intent_coverage[]` 出现且 `<journal>-gaps.json` 生成，即算步 4–7 的 PASS 候选，**不因当天没 VERIFIED 判冒烟 FAIL**。

---

## §1 环境与版本

| 项 | 读数 |
|---|---|
| 冻结提交 / 版本 | `cea9c0f` / `0.7.39` |
| 装机 | `deploy-mod.py --no-quit`：0.7.38→0.7.39，dll **281088 B** / manifest **62661 B**，桥 `modVersion=0.7.39 port=17890`，自动读档 FarmHouse (9,9) |
| `goto Farm` | ok 7617ms（hop1 `FarmHouse→Farm source=[3,12] landing=[64,15]`） |
| preflight | `--expect 0.7.39 --save-baseline logs\run10g-baseline.json` ✅（fall 23 06:10 debris / Farm(64,15) / 体力 270 / 钱 1977g / Wheat Seeds×10 / farmingLevel 2 / crops 34 / unwatered 2 / dryCrops 34 / waterLeft 25 / tillable 138 / tileCount 400 truncated / 无模态 / worldAdvancing true） |
| 五文件指纹（我复算） | **5/5 逐字一致（size 也一致）**：`longrun.py B98BCBC6…77B0`(535469) / `farmwork.py BEB8E1A6…5255`(211847) / `bridge.py A298F135…8388`(63651) / `dll FF05225C…BD08`(281088) / `manifest 9CA523EF…59D1`(62661) |
| 游戏进程 | PID **24636**（退出时 `原 pids=[24636]`） |
| 存档四条（退出前后**逐字未变**） | `Wahaha_450799035` **4504729 B / 2026-10-18 11:38:26**；`SaveGameInfo` **31022 B / 11:38:26**；`_old` **4487494 B / 11:35:42**；`SaveGameInfo_old` **30999 B / 11:35:42**（秒级取自冻结前打印，此处按分钟记录） |

## §2 七步结果汇总

| 步 | 内容 | 结果 | 备注 |
|---|---|---|---|
| 1 | `debug_dump crafting_recipes/Furnace` | **PASS** | `matchedCount=1`、无 `unknown_skill` |
| 2 | `debug_dump trigger_actions` | **PASS** | 可读、无 `InvalidCastException` |
| 3 | 单技能砍树 `use_tool(axe)` | **FAIL（前置不成立）** | 首跑玩家在 (64,15)、目标 (39,14) 相距 ~25 格 ⇒ 空挥 6 次；已按 Lead 裁 (A) 改成先 `move_to(邻格)` 再「只发一次」，**待下一轮 bring-up `--only 3` 补跑** |
| 4 | 1 日长跑 ⇒ intent_coverage + gaps | **PASS** | `finish` 出现、`intent_coverage[]` 8 条/天、`scripts`→`logs\longrun-smoke-0739-gaps.json` 已生成 |
| 5 | `clear_area` 逐格判据活 | **PASS（修取证路径后）** | `day_end.stages[]` 里 `clear_area tiles=2 ok=1` 且 `cleared_tiles` 1 条；首版只看 `outcome` 事件 ⇒ 误判"无法判定" |
| 6 | 跨日落盘六串 6/6 | **PASS** | `NewDay/before save/Save called/Save task/completed/after save = 3/3/3/3/3/3`（排除插件描述行 1 条） |
| 7 | analyzer §8 无红 + verify §8 只 info | **FAIL（部分）** | 头部对账计数**干净**（0 步且无原因码 **0** 条、计划无对账 **0** 条）；但 analyzer 红清单含 **`missed:intent_no_target_evidence:ship`**（一条 ship 意图没有目标证据）⇒ 待 Lead 裁是否算 §8 阻断 |

## §3 步 1 / 步 2 原文要点

- 步 1：`debug_dump table=crafting_recipes key=Furnace` ⇒ 不再是 `unknown_skill`（0.7.37 那次 `BridgeHost` 白名单漏 `debug_dump` 的坑已闭合），命中 `Furnace` 1 条。
- 步 2：`debug_dump table=trigger_actions` 可读，**无 `InvalidCastException`** ⇒ 1.6 强类型资产读取修复生效（task-222 的验收面）。
- 读者注意：这两步在本轮之前（0.7.37）都曾是 `unknown_skill`，本轮是**先修白名单、后修强类型**两个修复叠起来才同时通过。

## §4 步 3 前置修正（第一次为何 FAIL、第二次怎么测、一个骨架小 bug）

1. **第一次 FAIL 是测试前置不成立，不是"砍树技能坏了"**：玩家 `(64,15)`、目标树 `(39,14)`，相距 ~25 格；`use_tool` 不负责行走 ⇒ Mod 的 6 次重试全在"够不着"里空挥。原文（节选）：
   `[tool_ineffective] (HTTP 200) use_tool 试过的工具都无效：「Axe」挥 6 次无效（UsingTool=True）；目标格 (39,14) 上仍有东西（现在还是「tree」，起手=是）… acted 证据：tileChanged=false；readyCrops[34 → 34]（dropped=false）；inventoryGrew=false`
   世界确实未变 ⇒ 这条 FAIL 只作**"前置不成立"的证据**留档，**不能**当"单技能砍树坏"的结论。
2. **按 Lead 裁 (A) 改成**：挑「四邻有可站格」的 `kind=="tree"` ⇒ `move_to(邻格, timeout_ms=30000)`（行走单独计入 `evidence.walk`，**不并入单技能结论**）⇒ 到位后重新 observe 取 before（记 `worldSeq_after_walk` / `player_after_walk`）⇒ **只发一次** `use_tool(axe)` ⇒ 比 `kind`（`tree→stump`/消失 = PASS）+ `worldSeq`；走不到邻格判【无法判定】不判 FAIL。代码已改好（`scratch/smoke-0739.py`），**未在长跑期间补跑**（single-writer：长跑在驱世界，不允许插一手）。
3. **骨架自己的 int/float bug（被 dry-run 拦下）**：起跑器 `--max-minutes` 是 `int`，骨架首版传了 `40.0` ⇒ 起跑器 `--dry-run` 直接 `invalid int value: '40.0'`、rc=2。已改 `str(int(...))` 后重跑通过。**这条正好证明 dry-run 四要素校验有效**（把参数错误挡在起跑之前，而不是浪费一次真跑）。

## §5 步 4 读数（1 日长跑）

```json
{"event":"finish","t":508.31,"code":1,"verified_streak":0,"actions":618,"minutes":8.47,
 "stages_seen":["clear_area","harvest","water_area"],"no_unmet_stages":false,
 "unmet_days":["1年 fall 23日","1年 fall 24日","1年 fall 25日"],"stuck_flushes":0}
```

- **3 个日报告，全部 `ended_by=inventory_blocked`、`verified=false`**：`fall23 32 ok/1 skip`、`fall24 31/0`、`fall25 31/0`；`checks.no_hard_failures=true`、`unreachable_within_bound=true`、`refused_within_bound=true`，但 `watered_outdoor=false` / `day_justified=false` / `no_unmet_stages=false` ⇒ 不达标。
- **`inventory_blocked` 是新的收工理由**（事件计数 `inventory_blocked` ×3、`slot_relief` ×3 但 `freed=0`）：背包 12/12 满、当天没有可出货/可卖的叠 ⇒ 腾格回路尝试 3 轮腾出 0 格 ⇒ 如实收工。analyzer 明确记「这是**如实上限**，不是失败、也不是豁免」。
- **`day_end.intent_coverage[]` 在场**（8 条/天，字段 `requested_tiles/ok_tiles/failed_tiles/unexecuted_tiles/executed_steps/reasons/actionless/reasons_are_intent_level`）。例：`harvest` 12 格请求、0 ok、12 failed、`executed_steps=36`、`reasons={"no_slot":12}`；`water_area` 31 格请求、31 ok。
- **gaps 文件已生成**：`logs/longrun-smoke-0739-gaps.json`（1126 B，`schema=agentfarm-gaps/1`，4 条）：`dirt/no_slot ×166`（fall 23→25，样本格 `[[60,25],[61,25]…]`）、`tree/gated ×1 [[60,22]]`、`dirt/gated ×1`、`dirt/blocked_tile ×1`。

## §6 步 5 证据（逐格判据活）

- `fall 23` 的 `day_end.stages[]` 里有 `clear_area tiles=2 ok=1 stopped="" cleared_tiles=[…1 条]` ⇒ 每个 ok 动作都带逐格证据。**修取证路径后重跑 ⇒ PASS**（`clear_total_ok=1`、`clear_total_with=1`）。
- 首版误判原因（如实记）：`step5` 只扫 `outcome/stage_step/blocked` 事件里的 `kind=clear_area`，而本账本没有逐格 clear 事件（只有阶段汇总）⇒ 误报"该日没有 clear_area 的 ok 步"。已改成「退到 `day_end.stages[].cleared_tiles`」取证。

## §7 步 6 证据（跨日落盘六串）

- 冻结窗口：`logs/smoke-0739-smapi-window.txt` = **279110 B / mtime 2026-10-18 11:38:56 / SHA256 `C5B3A5EDD629E6F069071366B97FF3B08D6EF45785C87D2DE52A629E80F4DE78` / `BYTE_IDENTICAL=True`**（等游戏退出后复制 ⇒ 源/副本字节一致可校验）。
- 六串 **3/3/3/3/3/3**（`NewDay` / `before save` / `SaveGame.Save() called` / `Synchronizing 'Save' task` / `completed without exceptions` / `after save`），排除 1 条插件描述行（L16 判别式：有 `[HH:MM:SS LEVEL CHANNEL]` 前缀且不含 ` by AgentFarm ` / `| v0.`）。

## §8 步 7 读数（两个检查器）

- `analyze-longrun --journal logs\longrun-smoke-0739.jsonl --days 1` ⇒ **rc=1，有红 33 条**，红清单里 **§8 专属红只有一条：`missed:intent_no_target_evidence:ship`**（其余 `missed:cancel:plant_area / missed:check:day_justified / missed:check:no_unmet_stages / missed:check:watered_outdoor / missed:env_fail / missed:harvest / missed:seeds / missed:stage_exhausted` 都是**日级"当天没达标"**，不是 §8 管道问题）。
- §8 头部对账计数（`未执行意图:` 行）：**意图 34 条；0 步 14 条 / 其中无原因码 0 条；计划无对账 0 条**；原因码 `blocked_tile×1、gated×2、no_slot×14、no_target×3、superseded×3、unknown_evidence×8` ⇒ **Lead 点名的「executed_steps==0 且无原因码」子判据干净**。
- `verify-run3 --journal … --days 1` ⇒ **rc=1 / `needs_review`**，问题清单全是日级 `ended_by=inventory_blocked` / `watered_outdoor=false` / `verified=false` / `no_unmet_stages=false`，**没有任何把 `intent_coverage` 当 problem 的行** ⇒ **§8 分工（analyzer 判红、verify 只 info）成立**。
- **骨架自身的一个正则误命中（已修）**：首版 step7 用 `executed_steps\s*[=:]\s*0` + "原因码" + "红" 去 grep，命中的是 analyzer 的**判据说明行**（"…executed_steps=0 无原因码…⇒ 红"）而不是真红行 ⇒ 误报 FAIL。已改成**解析头部对账计数** + 只认红清单里的 `missed:intent*`/`missed:gaps*`。

## §9 收尾（m02833 优雅退出 + 时点冻结）

- `python tools\stop-game.py` ⇒ **rc=0**、`✅ 游戏已退出（原 pids=[24636]）`。
- 退出后四项核对：**进程 0** / `bridge.json` **已删** / 17890 只剩 **2 条 TIME_WAIT**（无 LISTENING）/ **存档四条逐字未变**（见 §1）。
- SMAPI 窗口**等退出后**复制并校验 `BYTE_IDENTICAL=True`（0.7.35 那次留下的"源被占用不能做字节一致"缺口，这次按 Lead 建议补齐）。
- 没有 `load_save`、没有 craft/place/buy/sell、没有对事件做 dismiss；步 3 在长跑期间**未**补跑（single-writer）。

## §10 结论与待办

1. **管道结论：步 1、2、4、5、6 PASS；步 3 因测试前置不成立而 FAIL（已按 (A) 改好，待下一轮 bring-up `--only 3` 补跑）；步 7 部分 FAIL（§8 有一条 `missed:intent_no_target_evidence:ship`）**。
2. **步 3 补跑计划（Lead 已批准）**：Lead 做 `deploy-mod --no-quit` + preflight（重开 = 秋 23 日清晨存档，树还在）⇒ 我只跑 `--only 3` ⇒ 立刻再退游戏。
3. **步 7 待裁**：`missed:intent_no_target_evidence:ship` 是"ship 意图没有目标证据"—— 本次 `slot_relief` 腾格 3 轮 `freed=0`（没有可出货叠），是否该把这条当 §8 阻断，请 Lead 定。**它不改变"头部对账计数干净"这个事实**。
4. 本报告**不作为验收/成绩证据**（1 日跑 0 VERIFIED），只作 0.7.39 管道冒烟。

## §11 保留物

`logs/longrun-smoke-0739.jsonl`（220 行）/ `.console.log` / `.console.err.log`（0 B）/ `.pid` / `.version.json`（sidecar）/ `-llm.jsonl` / `-lessons.json` / `-gaps.json` / `-baseline.json`；`logs/smoke-0739-smapi-window.txt`；`logs/smoke-0739-analyze.txt`、`logs/smoke-0739-verify.txt`；`scratch/smoke-0739.json`（七步累计记录）；`scratch/smoke-0739.py`。
