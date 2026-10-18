# smoke-0746 真机门禁证据（0.7.47，tag `smoke-0746`）

- 日期：2026-10-18 21:44–21:50（Asia/Bangkok）；执行 machine-runner；任务 task-30
- 构建：AgentFarm Bridge **0.7.47**（冻结 `a03a564`；HEAD `f0d69a3` docs 冻结记录）；dll 293,888 B `C9B3BD6C…A662`（与 0.7.46 逐字节同）、manifest 76,849 B `9B7C30F6…ADBB067`
- 起跑档：**当前档 winter 28**（未 restore A9-start；A9 前才 restore）；背包升级对话购买默认关闭（task-35 opt-in 未开）
- 产物：`logs/longrun-smoke-0746.jsonl`（131 行）、`logs/smoke-0746-smapi-window.txt`、`scratch/smoke-0746.json`、console/gaps/lessons/guardian 见 §7

## §0 结论先行

**门禁六条：① PASS ②【无法判定】③ PASS ④ PASS（字面）⑤ PASS ⑥ PASS ⇒「六条全满足」不成立，按卡面不放行 A9，报 Lead 裁定。**

- 本跑是**正面证据**：`finish.code=0`、day winter28 **verified=true**（`checks` 10/10 true，含 `day_justified=true`）、0 条 `stuck:`、零卖单、guardian 自动优雅收尾 rc=0。
- 但 **②「0.7.45 两个 FAIL 形态转 PASS」未被触发**：本跑 `inventory_blocked=0`、`resume_exhausted=0`、`stuck:`=0、旧守卫文案 0 次；winter26 形态（满包+无活可做+腾不出格）与 winter27 形态（resume 耗竭）在本档（winter28）不出现，无法证明其已转 PASS ⇒ 缺失≠通过，记【无法判定】。
- 八步判定：步 3 PASS / 步 4 PASS / 步 5【无法判定】/ 步 6 PASS / **步 7 FAIL**（`slot_relief` 1 条缺 task-237 字段 `reached`；analyzer rc=1、verify rc=1）/ 步 8【无法判定】（8.1 PASS，8.2①③ 无读数，8.2② trees PASS 但含旧会话观测污染）。

## §1 起跑四要素

| 项 | 值 |
|---|---|
| HEAD | `f0d69a38e33eaca43a83f2645e90ac90391b2f99`；`worktree_clean=true`、`git_status_short[]` 空 |
| argv | `…\python.exe -u tools/run-longrun.py --days 1 --size 5 --max-minutes 60 --max-days 2 --journal logs/longrun-smoke-0746.jsonl`（`boundary_llm=true`）|
| 五文件 | longrun.py `DBF570A71C79A006…B4FA603C`（21:39:39）/ farmwork.py `ED2442B43A4A1F9E…F719F0`（20:03:29）/ bridge.py `A278974D837BDB28…D10D15BAA`（21:41:56）/ dll `C9B3BD6C…A662`（21:42:02）/ manifest `9B7C30F6…ADBB067`（21:41:51）|
| 装机 | dll/manifest 与上同哈希；`bin\Release` dll 亦为冻结 `C9B3BD6C…`（21:42:02，deploy 安全）；`deploy --no-quit` 后桥 `modVersion=0.7.47`、pid **16676**、token `05dae2699b6551df3b1f8d741f3f90dd`、startedAt 14:44:20Z |
| A9-start | **未动**：manifest 1,222 B 18:02:55 `5479354B…988A3D`；main 3,141,826 B 17:03:52 `053CAA71…8F4AF7`、SaveGameInfo 32,305 B `3D964F3F…9293`、_old 3,121,459 B 16:49:07 `E5B60E91…B19E`、info_old 32,472 B `9DD16B94…9525` |

起跑前存档四件（winter28，19:15:01 落盘）：main 2,948,770 B `6DE8419B…B594`；SaveGameInfo 32,264 B `B5B51971…10A1`；_old 3,137,234 B `1695C1ED…509D`；info_old 32,259 B `BCC85C1B…7DAA`。环境：进程 0 / bridge.json 无 / 17890 无 LISTENING。

## §2 逐日表（本跑只有 1 个 day_end：target_days=1 达成即停，max_days=2 未用到）

| day | ended_by | ended_reason | verified | checks=false 键 | ok/skip/fail | 峰时/终时 | 备注 |
|---|---|---|---|---|---|---|---|
| winter 28 | sleep | `stamina:体力 11.6002 < 12` | **true** | 无（10/10 true）| 139/2/0 | 06:30→13:10 | `stages_seen=[till_area]`；`deferred_tiles=9`（till_area，诚实上限）；`refused=2`（[41,12][41,13] tool_ineffective，bound 28、exempt 0、bound_basis 141）；`unreachable=0`；`assigned_undone=0`；`stage_midway_leftover=[]`；`dead_crops=0` |

day_end 关键字段（`logs/longrun-smoke-0746.jsonl:130`）：
- `checks` 全 true：`slept_by_us/no_blocking_modal/no_hard_failures/unreachable_within_bound/refused_within_bound/no_unmet_stages/crops_watered/watered_outdoor/day_justified/zero_action_evidenced`
- pending 七口径：`pending_ledger=9, pending_guard=9, pending_stalled=0, pending_executable=0, pending_blocked=0, pending_unobserved=9, pending_malformed=0`（`9=9+0`、`9=0+9+0` 不变式成立）
- `plot_pending=9`（`plot_pending_executable=9`、`plot_pending_blocked=0`；`plot_pending_by_kind={"till_area":9}`）
- `free_slots_start/last/min = 0/0/0`（status ok）；`relief_exhausted=true`；`bag_evidence={free_slots:0, sellable_above_keep:0, relief_rounds:0, sold_stacks:0, plan_pressure:true, exhausted:true, loot_lost_steps:0, loot_lost_limit:5}`
- `loot_lost_steps=0`、`loot_lost_tiles=[]`；`slept_ok=true`、`stuck_flushed=false`、`gave_up_tiles=[]`
- 背包升级：`backpack_upgrade_ok=false`、`attempts=0`、`skip="disabled"`、`backpack_capacity_before/after=null`
- `final`：winter28 13:10，Farm tile [61,26]，体力 11.600226，钱 3288，tillable 200，hoeDirt 145，作物 0；`day_after=[2,"spring",1]`
- `sleep`（L129 t=309.49）：`ok/code=ok`，winter28 13:10 → spring1 06:00（第 111→112 天，1873 ms，`answerDialogue(Yes："Yes")`），体力 11.6002→270
- `finish`（L131 t=309.62）：`code=0, verified_streak=1, actions=148, minutes=5.16, no_unmet_stages=true, unmet_days=[], stuck_flushes=0`；console 终态「VERIFIED」

## §3 0.7.45 两个 FAIL 形态在本跑的对照

- **未出现**：`inventory_blocked` 0 条、`resume_exhausted` 0 条、`stuck:` 0 条、旧守卫文案「守卫仍说」0 次。
- 本日**背包确实满**（free_slots 0/0/0）且腾不出格（`relief_exhausted=true`，`slot_relief` 3 条：两条 t=0.11 的 `trigger=none`、一条 t=3.31 的 `trigger=clear_gate`），但**仍有活可做**（winter28 还有 tillable 200 格 / 139 格出手）⇒ 走的是「满包留痕 + 继续干活 + 体力诚实收工」路径，不是 winter26 的「无活可做 ⇒ inventory_blocked 收尾」路径 ⇒ **两形态未触发，无法判定是否转 PASS**。
- `intent_vetoed` 2 条（t=283.65/289.94）记录了「没种子但钱够该去买、还有地要清」，但买种子被满包闸挡住（`slot_relief t=0.11` `demand_basis=buy_full`，note「买种子前背包满且腾不出格子 ⇒ 不买」）。

## §4 八步判定（`scratch/smoke-0746.json`）

| 步 | 判定 | 读数 |
|---|---|---|
| 3 单技能砍树 | PASS | goto Farm 后 (35,14) `tree → None`（calls=1）；py 前置：读档在 FarmHouse，先 `python -m agentfarm goto Farm`（rc=0，7616 ms，landing [64,15]）|
| 4 2 日长跑 | PASS | 起跑器拉起 brain PID **12196**；journal 131 行出 finish |
| 5 task-242 逐格判据 | **无法判定** | `clear_stage_total_ok=0`（整跑只做 till_area，没有 clear_area 的 ok 格 ⇒ 判据本批无读数，缺失≠通过）|
| 6 跨日落盘守卫 | PASS | save-chain-check：六串 **1/1/1/1/1/1** 全配对；SMAPI 行号 NewDay 1403 / before 1406 / called 1407 / task 1408 / completed 1412 / after 1413；时间 21:50:02→21:50:05；`save_called_raw=2`（L16 发布说明 1 条假阳性被排除）；末次跨日已落盘 |
| 7 analyzer §8 + slot_relief 字段 | **FAIL** | `slot_relief` 共 3 条，index 2（t=3.31，`trigger=clear_gate`）**缺字段 `reached`**（task-237 要求 demand/target_free/reached）；`analyze_rc=1`、`verify_rc=1`；其余：`missed:intent_no_reason:*` 0 ✓、`intent_reconciliation={intents:75, zero_step:56, zero_step_no_reason:0, plans_no_reconciliation:0}` ✓、gaps.json 2 类（unknown_evidence 8 格、gated 2 格 = [41,12][41,13]）|
| 8 0.7.42 三条硬判据 | **无法判定** | 8.1 **PASS**（1/1 天 verified，旧守卫文案 0 次）；8.2① tool_ineffective 单发封格【无法判定】（本跑 `tool_refused` 2 条但无 `blocked_tool_ineffective` 计数）；8.2② trees **PASS（含污染，见§8）**：best_delta −19 来自 **旧会话** winter27 观测（910→891，n=9），本跑 winter28 仅 +2（905→907，n=4）；8.2③ 预算理由【无法判定】（`deferred_by_budget` 0 条）；harvest 冬季【无法判定·无作物】 |

## §5 门禁六条逐条

1. **`finish.code==0` 且 ≥1 天 verified=true ⇒ PASS**：code=0、winter28 verified=true（L131/L130）。
2. **0.7.45 两 FAIL 形态转 PASS ⇒【无法判定】**：形态未触发（§3）；不能以「本日 verified」代替（缺失≠通过）。
3. **0 条 `stuck:` 掩盖 ⇒ PASS**：journal 全文 `stuck:`=0、`守卫仍说`=0；`stuck_flushes=0`；本日以 `stamina:` 诚实收工。
4. **建材/锭类零卖单 ⇒ PASS（字面）**：全跑 `sell` 事件 0 条、`slot_relief[].sold=[]` 三条、钱 3288 未变 ⇒ 388/390/330/771/382/378/380/384/386/909 **零卖单**成立；**证据限制**：卖材通道本跑根本未触发（无可卖盈余叠），白名单修复未被实际路径验证。
5. **背包留痕在场且有界 ⇒ PASS**：`buy{status:skipped, code:disabled}` 1 条（day_start 后 t=0.1，reason 原文含 task-34 说明）；`day_end.backpack_upgrade_skip="disabled"`；`free_slots_*/bag_evidence` 在场；`loot_lost_steps=0 ≤ limit 5`；`backpack_capacity_before/after=null`（如实缺读数）。
6. **六串配对 + 优雅退 ⇒ PASS**：六串 1/1/1/1/1/1；guardian 21:50:14 判据成立（脑死 + finish）→ `stop-game --wait 45` rc=0（原 pids=[16676]）→ 21:50:17 进程 0、bridge.json=False、17890 LISTENING=False、guardian exit code=0。

## §6 收尾四项 + SMAPI 窗口 + 存档四件（跑后）

- SMAPI 窗口 `logs/smoke-0746-smapi-window.txt`：**179,772 B / 1,429 行 / mtime 21:50:34 / SHA256 `E84EB6C944E1058E8D824F23BAA008BBEFB167B900E0EBB534C5789F4FDB9C5E`**（源=副本逐字节一致）
- guardian：`logs/longrun-smoke-0746-guardian-state.json` trigger=true、「判据成立：脑死 且 finish 已出现」，stop rc=0，verify `{进程数:0, bridge.json exists:False, 17890 LISTENING:False}`
- 跑后存档四件（21:50:04 落盘 winter28→spring1 跨日）：
  - main 3,571,471 B / `2B1BCC1B8084858DBA262077A950DB0C77D56ECA636C72C8B26CEF395312F669`
  - SaveGameInfo 32,618 B / `2B8140D91C41E7D6E93CB437161B57913C2956C7F4E3CD0A2D0732F8991F8334`
  - _old 2,948,770 B / `6DE8419B098EA16972C7DB761F4080127599523A2C1AD8EC5A6176F86861B594`（=起跑前 main）
  - SaveGameInfo_old 32,264 B / `B5B51971BFF129EDE468D2671731A50B0D0A7964755AE7AB5643AEF07A7310A1`（=起跑前 info）
- A9-start 未动（§1）；装机 dll/manifest 收尾后仍为冻结哈希 `C9B3BD6C…` / `9B7C30F6…`

## §7 产物哈希

| 文件 | size | mtime | SHA256 |
|---|---|---|---|
| `logs/longrun-smoke-0746.jsonl` | 146,399 | 21:50:06 | `B08F351BA0C998C1B8543CB9058A0C43012FE288D1638FCFE779E2F76E4F6728` |
| `logs/longrun-smoke-0746.version.json` | 1,449 | 21:44:56 | `710CAD9A167BDB8CA4A99B66EA448A3D694BEC5C63505A96E4A50E19A43B7099` |
| `logs/longrun-smoke-0746.console.log` | 5,929 | 21:50:06 | `A7261194BC7D539F651540BCA9591FBCFF9099EAD323F654E68E1D234E07C8C5` |
| `logs/longrun-smoke-0746-gaps.json` | 710 | 21:50:06 | `5E0FB5A243A0A5A2B9BC74787A255DB9ABBA8A94C617D433EBE2C3072E33F8B4` |
| `logs/longrun-smoke-0746-lessons.json` | 960 | 21:50:06 | `F790924D1566B33282E2E6FD612EC553C84457D98850BC5166BACEF99425154E` |
| `logs/longrun-smoke-0746-guardian.log` | 2,740 | 21:50:17 | `9440352D1FACC63DB80F38038429027FA65939D78042FDF15D4762AD449C08EA` |
| `logs/longrun-smoke-0746-guardian-state.json` | 2,209 | 21:50:17 | `C1FFA32C7C245A696C2F844AEA8A2FE8C905C954ACB49E8ACFEDB006F243E526` |
| `scratch/smoke-0746.json` | 38,946 | — | `EB6247EA57DFA5B55DAD2F6B90DF88ED6F00E1EA251854E5AE2F1AB5B6839C14` |
| `scratch/smoke-0746-save-chain.json` | 2,642 | — | `9570BDC3F05BAC52A790247E0D02DA3C7BEF450A73567C14585EC2C0D8BBC48E` |

## §8 已知限制

1. **gate ② 未触发**：本档从 winter28 起跑、`--days 1` 当日即 VERIFIED 停止，winter26/winter27 旧形态无法在本配置下重放（不 restore A9-start、不挑重跑）⇒ 无法判定是否转 PASS。
2. **步 8.2② trees 判定含旧会话污染**：`scratch/smoke-0742-observe-*.json` 里残留 0.7.44/0.7.45 冒烟的 winter26/27/winter5 观测（本跑只新增 winter28 的 t0/34790/34911 三份：trees 907→907→905…）；PASS 依据的 −19 不是本跑读数，**不可引用为本跑证据**。
3. **步 7 FAIL 为字段级缺口**：`slot_relief` 的 `clear_gate` 分支（t=3.31）未写 `reached`；是否属产品缺陷/是否 task-237 有意豁免，需 dev/log-analyst 裁定；本文件只记读数。
4. **步 5 无读数**：本跑只做 till_area，没有 clear_area ok 格，task-242 判据无法验证（不是失败）。
5. **卖材白名单未被实际验证**：零卖单（无可卖盈余叠），门禁 ④ 仅字面满足。
6. 只有 1 个 day_end：`--days 1` 首日即达标，第 2 天（spring 1）未跑（max_days=2 未用到）——卡面「两天 day_end 全字段」只能记 1 天。
7. 背包升级「是否真发生」=【无法判定】（入口未取证，0.7.47 默认关闭；`capacity_before/after=null`）。

## §9 命令原文

```
python tools\deploy-mod.py --no-quit
PYTHONPATH=brain python -m agentfarm goto Farm
python scratch\smoke-0742.py --expect-version 0.7.47 --phase pre --only 3 --tag smoke-0746
python tools\run-guardian.py --tag longrun-smoke-0746 --detach
python scratch\smoke-0742.py --expect-version 0.7.47 --phase launch --tag smoke-0746 --days 1 --size 5 --max-minutes 60 --max-days 2 --capture-observe --observe-every 120 --no-crops
python scratch\smoke-0742.py --expect-version 0.7.47 --phase wait --tag smoke-0746 --wait-minutes 60 --capture-observe --observe-every 120 --no-crops
python scratch\smoke-0742.py --expect-version 0.7.47 --phase post --tag smoke-0746 --freeze-smapi --no-crops
```
