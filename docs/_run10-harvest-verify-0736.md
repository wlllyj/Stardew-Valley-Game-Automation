# run10d · task-191 —— 0.7.36 同格收割复测（interact / use_tool / loot / fail-closed）

**一句话结论：四条判据全绿 = PASS；0.7.36 的 harvest 证据面基本收口**（R1 已闭合；R2 收敛为"白名单内逐 qid 精确一致"，附带非白名单掉落另记 R8）。全部读数为**真机 forensics**，判据只认观测差分与 Mod 原始回执原文。

- 日期：2026-10-17（Asia/Bangkok）｜执行：teammate `machine-runner`｜卡：task-191（`blocked_by task-190`）
- 被测版本：**0.7.36**，冻结提交 `7ad5f6b`（"freeze 0.7.36: use_tool acted/actedEvidence fail-closed + harvest evidence face (task-186/188/189/192)"）
- 起点存档：无跨日、无落盘 ⇒ 全部世界改动只存在内存里，退出即丢弃，样本原样保留

---

## §1 环境与版本（五文件指纹 5/5 MATCH）

| 文件 | SHA256(16) | size | mtime |
|---|---|---|---|
| `brain/agentfarm/longrun.py` | `C326DD1E1358EA15` | 423163 | 2026-10-17 08:08:08.884 |
| `brain/agentfarm/farmwork.py` | `FA6BD05CCAB9DF25` | 174268 | 2026-10-17 07:43:54.086 |
| `brain/agentfarm/bridge.py` | `968D1D227A293B1A` | 51696 | 2026-10-17 08:16:50.713 |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `D6699BD057C51CE7` | 202752 | 2026-10-17 08:17:05.275 |
| `mod/AgentFarm.Bridge/manifest.json` | `6578C42574237AA8` | 53261 | 2026-10-17 08:16:27.409 |

- Lead 给的五个 16 位指纹与现场 `Get-FileHash` **逐项 MATCH**（含 size/mtime）。
- 游戏进程 `StardewModdingAPI` PID **3204**（StartTime 2026-10-17 08:17:46）；`bridge.json` 206 B，`modVersion=0.7.36 / port=17890`。
- `git status --short` 只有 `?? scratch/_t192_delta.py`（**不是我的**，未提交）；`HEAD = 7ad5f6b`。
- 起跑前基线（Lead 侧）：`logs\run10d-baseline.json` 701 B / 08:18:37，`worldSeq 14`、秋 12 日 06:40 rain、Farm(64,15)、体力 247.2/270、钱 0g、`crops 102`、`unwateredCrops 2`、`dryCrops 0`、`waterLeft 27`、`farmingLevel 1`、`tillableCount 120`。
- 我的独立读盘（`scratch\_t191_probe.py env`）：`modVersion 0.7.36`；SMAPI 417 行、`newday 0`、`save_called` 原始 1 / **修正 0**（原始那 1 条 = L16 插件描述行假阳性）。
- 存档四条（全程未变，见 §10）：`Wahaha_450799035` 4310486 B / `2026-10-17 05:04:35.296`、`SaveGameInfo` 28707 / 05:04:35.298、`_old` 4281756 / 04:49:43.856、`SaveGameInfo_old` 28760 / 04:49:43.857。

## §2 起跑前现场（`fields`，`worldSeq 71`，秋 12 日 tod 1320 rain）

- 玩家 `[60,28]`（`move 60 28` ok 3861ms，`worldSeq 54→71`）、体力 247.20007、钱 0、`farmingLevel 1`。
- **样本格 `(60,29)`**（原始 JSON 关键字段）：`crop "270"`、`ready true`、`readySource "game"`、**`harvestMethod "Grab"`**、`ripe true`、`fullyGrown true`、`regrowsAfterHarvest true`、`dayOfCurrentPhase -9`、`feature "HoeDirt"`、`watered true`。`tile_ready=True`、`harvest_tool=None` ⇒ 脑侧会走 **`interact`**。
- **对照格 `(60,28) / (61,29) / (60,30)`**：`crop "262"`、`ready true`、`readySource "game"`、**`harvestMethod "Scythe"`**、`fullyGrown false`、`ripe false`、`currentPhase 4`、`phaseDays 5`。
- `farm`：`crops 102 / readyCrops 102 / ripeCrops 1 / deadCrops 0 / dryCrops 0 / unwateredCrops 2 / hoeDirt 153 / emptyDirt 51 / scanSeq 68`。
- 窗口聚合：`ready_true 86`、`with_crop 86`、`window_tiles 400`。
- 背包 **12 行占满**：`[Axe, Hoe, WateringCan, Pickaxe, (W)47 Scythe, (O)535 Geode×3, (O)262 Wheat×3, (O)178 Hay×17, (O)390 Stone×3, (O)483 Wheat Seeds×1, (O)Moss×35, (O)262 Wheat×37]`；`shippingBin {present true, count 0}`。
- 备注：`player.inventoryCount` 仍是**容量字段（=12）**，判"满没满"必须数 `player.inventory[]` 行数（本地读数为 12 行）。

## §3 0.7.36 脑侧 harvest 代码面（只读）

`brain/agentfarm/farmwork.py:2283 def harvest(self, tile) -> StepResult`：

1. `tile_ready(tv)` 为假 ⇒ `code="skipped"`，**不摘、不白试**（fail-closed）；
2. `player_free_slots()` 按 `inventory[]` **行数**算空槽，满 ⇒ 一次不交互直接 `failed`；
3. `harvestMethod == "Scythe"` ⇒ `self.c.use_tool(tile, tool=tool, timeout_ms=15000)`，否则 `self.c.interact(tile, timeout_ms=8000)`；
4. **四选一证据**（全部取自动作前后观测差分，且被 `tile_seen` 把关）：`crop_gone` / `ready_flipped`（或 `source_changed`）/ `gained`（逐 qid 背包差）/ `ready_dropped`；
5. 回执字段：`acted is False or ok is False` ⇒ `code="failed"`；`r.after` 带 `loot / harvested / affected_tiles / loot_whitelisted / whitelist_bound / tile_seen / loot_waits`（可选 `loot_unconfirmed` / `not_seen`）。
6. `LOOT_CONFIRM_TRIES = 2`、`LOOT_CONFIRM_WAIT_S = 0.35`：有格子级证据但还没看到逐 qid 新增时，**有界再观测**直到出现或用完次数。白名单只在有格子级证据时绑定。
- 桥侧：`brain/agentfarm/bridge.py:742 interact(self, tile=None, *, timeout_ms=5000)`、`brain/agentfarm/bridge.py:764 use_tool(self, tile=None, *, tool=None, timeout_ms=12000)`（tool ∈ axe/pickaxe/hoe/can/scythe/auto）。
- 工具：新建 `scratch\_t191_probe.py`（子命令 `env`/`fields`/`sell`/`harvest`/`use-tool`；`Rec` 薄代理记录 entry points + 截获原始回执；每条动作 dump `_t191_<tag>-{before,after,receipt,verdict}.json`，离线交 `_t184_triple_check.py` / `_t191_loot_check.py`）。

## §4 腾格（受制裁路径：出货箱，两次）

| # | 动作 | 结果 |
|---|---|---|
| 1 | `sell(slot=10, whitelist=["(O)Moss"])` | `ok=True code=ok`；背包行 **12→11**；`shippingBin.count 0→1`（`(O)Moss`×35）；钱 0（次日结算） |
| 2 | `sell(slot=8, qid "(O)390")` | `ok=True code=ok`；背包行 **12→11**；`shippingBin.count 1→2`（`(O)Moss`×35 + `(O)390`×3）；钱 0 |

两次都只出货箱、不手改、不卖工具/种子。

## §5 判据①② —— `interact` 路径（样本格 `(60,29)`）

- 脑侧：`StepResult{ok=True, code=ok}`，0.2s，reason = `收获成功（判据：该格 ready true→False；进背包：{'(O)270': 1}（逐 qid 差分））…受影响格：[[60, 29]]；再生作物：crop 对象保留、阶段重置（旧判据只看 crop 消失 ⇒ 假阴性）`。
- **Mod 原始回执**：`{"ok": true, "status": "ok", "skill": "interact", "acted": true, "actedEvidence": "ready"}`。
- 世界差分（两份 full observe）：`ready_flipped True`、`loot {'270': 1}`、`crop_gone False`（再生作物正常）、`readyCrops_down False`（当场 `102→102`）、`worldSeq advanced False`（`60→60`）⇒ **判定 `PASS · AGREE_SUCCESS`**。
- `entry points used = ['interact']`；脑侧 `after`：`loot {"(O)270":1}`、`affected [[60,29]]`、`loot_whitelisted ["(O)270"]`、`whitelist_bound True`、`tile_seen True`、`loot_waits 0`。
- 聚合滞后（如实记录）：动作后第一张观测里 `farm.readyCrops` 仍是 102；**下一次 fresh observe = 101**（`scanSeq 88`）、窗口 `ready_true 86→85` ⇒ 单看一张聚合快照会误判"没掉"，四选一证据（含逐 qid 背包差）才是可靠判据。

## §6 判据④ —— fail-closed（脑侧两层 + 原始技能对照）

| 子例 | 动作 | 结果 | 判定 |
|---|---|---|---|
| 6a | 同一格再 `harvest((60,29))`（此刻 `ready=false`） | 脑侧 `ok=False code=**skipped**`，reason `游戏口径不可收（ready != true…）⇒ 不摘`；**`entry points used=[]`（零触桥）**；世界无变化 | `PASS · AGREE_FAILURE` |
| 6b | 背包满时 `harvest((60,30))` | 脑侧 `ok=False code=**failed**`，reason `背包满（空槽 = inventoryCount 容量 − inventory[] 行数 = 0…）`；`entry points used=[]`；无回执 | `PASS · AGREE_FAILURE` |
| 6c | **原始** `use_tool(tool="scythe")` 打在不可收的 `(60,29)` | Mod 回执 `{ok:true,status:"ok",acted:true,actedEvidence:"readyCrops"}`，reason 声称该格"现在**上面已经没有东西了**"——**对该目标格是假话**（它仍 `crop "270" / ready=false`）；真实效果是**连带清掉 4 格**（`crops 102→98`、`readyCrops 101→97`、`emptyDirt 51→55`，其中含未成熟作物），当场 `loot {}` | `FAIL · BRAIN_SAYS_FAIL__WORLD_CHANGED`（原始技能无脑侧 `StepResult`，分类器如实标出） |

- **6c 的后续 fresh observe**：`(60,28)` 与 `(61,29)` 已变空（`crop` 键消失、`plantable true`）；`(60,30)` 当时仍在；qid 总量随后变为 `262: 40→44`、`178: 17→19` ⇒ **掉落是在更晚的一次观测里才入包的**（动作后第一张观测 `loot {}`）。
- 结论（判据④）：**脑侧 fail-closed 成立**（两条守卫都在触桥前拦下），且 6c 正是"为什么必须有这道闸门"的破坏性对照。**口径差异如实报**：Lead 卡面写的是"`ready=false` ⇒ 脑侧 `code=failed`"，0.7.36 实际实现返回 **`skipped`**（更早、更保守）。真机上**未能造出**「Mod 回执 `acted=false` 且脑侧 `code=failed`」的样本（脑侧会先以 `skipped` 拦截；唯一能触发原始路径的同一格又被聚合口径 `acted=true` 掩盖）⇒ 这一条按"脑侧零触桥 + 不可收格未被洗成成功"成立。

## §7 判据①②③ —— `use_tool` 脑侧路径（`(60,30)`，同一类镰刀作物）

> 说明：Lead 指定 `(60,28)` 做 `use_tool` 验收，但它在 §6c 的原始技能对照里被连带清掉（仅内存、重开即回滚），故改用**同类**镰刀作物 `(60,30)`。

- 脑侧：`StepResult{ok=True, code=ok}`，`entry points used = ['use_tool']`。
- **Mod 原始回执**：`{"ok": true, "status": "ok", "skill": "use_tool", "acted": true, "actedEvidence": "tile"}` ⇒ **R1 两键在**（枚举值 `tile`；样本格那条是 `ready`）。
- 世界差分：`crop_gone True`、`ready_flipped True`、`loot {'262': 2, 'Moss': 1}`、`readyCrops_down False`（当场 97→97，聚合滞后）、`worldSeq advanced True`（`123→…`）⇒ **判定 `PASS · AGREE_SUCCESS`**。
- 脑侧 `after`：`loot {"(O)262": 2}`、`affected [[59,30],[60,30]]`、`loot_whitelisted ["(O)262"]`、`whitelist_bound True`、`tile_seen True`、**`loot_waits 1`**、`loot_unconfirmed None`；reason 明写 `⚠ 动作后的第一张观测里背包还没反映这次收获，多等 1 次观测（0.35s/次）后才看到逐 qid 新增` ⇒ **`loot_waits` 翻篇机制真机生效**。
- **R2 核对（`scratch\_t191_loot_check.py`）**：脑侧自述 `{'262': 2}` vs 实测全量背包差 `{'262': 2, 'Moss': 1}` ⇒ 检查器判 `FAIL`。
  逐项定性：白名单内**逐个 qid 精确一致**（`262: +2 == +2`），多出来的 `Moss +1` 是镰刀顺带割草的非白名单掉落，脑侧没有把白名单外的掉落算进 `loot`/`affected_tiles`，**也没有多报**。⇒ 判据③按白名单口径 **PASS**；"非白名单附带掉落未记账"另立 **R8**（见 §8）。
- 收尾复核：`(59,30)`、`(60,30)` 均已变空；`farm crops 96 / readyCrops 95 / emptyDirt 57 / scanSeq 131`；窗口 `ready_true 74 / with_crop 75`；qid 总量 `262: 46`、`Moss: 1`、`178: 19`、`270: 1`。

## §8 四条判据对照表

| # | 判据（Lead m02902） | 读数 | 结论 |
|---|---|---|---|
| ① | `interact` 与 `use_tool` 两条路都出数（脑侧 `ok/code` + Mod `acted/actedEvidence` + 至少一项世界证据） | §5 `interact`：`ok=True`、`acted=true/ready`、`ready_flipped`+`loot`；§7 `use_tool`：`ok=True`、`acted=true/tile`、`crop_gone`+`ready_flipped`+`loot`+`worldSeq` | **PASS** |
| ② | `use_tool` 回执必须有 `acted` 与 `actedEvidence`（task-188 验收面） | §7：两键都在，`actedEvidence="tile"`；§5 `interact`：`actedEvidence="ready"` | **PASS**（R1 闭合） |
| ③ | 多格挥镰报 `loot`（逐 qid）+ `loot_waits`/`loot_unconfirmed`；loot 与实测逐 qid 一致（task-189 验收面） | §7：`loot {"(O)262":2}`、`loot_waits 1`（生效）、`loot_unconfirmed` 缺省；白名单内逐 qid 精确一致；另有非白名单 `Moss +1`（R8） | **PASS**（白名单口径） |
| ④ | 不可收格不被洗成成功（fail-closed） | §6a `skipped` + 零触桥；§6b `failed` + 零触桥；§6c 原始技能破坏性对照 | **PASS**（口径差异见 §6） |

**四条全绿 ⇒ 0.7.36 harvest 证据面判定 PASS。**

## §9 残留（R1–R8）

- **R1（已闭合）**：`use_tool` 回执补齐 `acted` + `actedEvidence`（`tile`）；`interact` 为 `ready`。
- **R2（收敛）**：白名单内逐 qid 精确一致，`loot_waits=1` 翻篇生效；不再出现"实收却说没有新增物品"的失真。
- **R3（口径，不改代码）**：`worldSeq` 不是成功/失败信号 —— 本次 `interact` 成功时 `60→60`（未前进），`use_tool` 成功时前进。已由 Lead 写进 `docs\_run10-criteria.md` §5。
- **R4（部分改善）**：`use_tool` reason 不再把原物渲染成"（空）"，但出现了新的过度断言"现在上面已经没有东西了"（对目标格不成立，见 §6c）。
- **R5（闭合）**：0 空槽守卫先拒绝且**零触桥**（§6b 复现）。
- **R6（口径）**：`readyCrops == crops`（102/102）是**游戏口径**（`readySource="game"`），不是 Mod fail-open 兜底；对照格一镰刀实收 `+4 Wheat / +2 Hay` 证明这些格**真的可收**。
- **R7（新，Mod 文案/口径）**：原始技能路径对**不可收**的格是**破坏性**的（连带清 4 格，含未成熟作物），而回执 `acted/actedEvidence` 是**聚合口径**（看 `readyCrops` 掉了就报 `acted=true`），对**目标格**的描述可以是错的。
- **R8（新，loot 记账）**：非白名单附带掉落（本次 `Moss +1`）不计入 `loot` / `affected_tiles`；若验收要求"全量背包逐 qid 一致"，需要额外口径说明或扩展字段。

## §10 收尾：按 `User said (m02833)` 优雅退出（四项核对）

- `python tools\stop-game.py` ⇒ **rc=0**、`✅ 游戏已退出（原 pids=[3204]）`（回执 `ok — 已置 Game1.quit=true`）。
- 退出后四项核对：`StardewModdingAPI` **进程 0**；`bridge.json` **Test-Path=False（已删）**；`netstat 17890` 只剩 **2 条 TIME_WAIT**（无 LISTENING）；**存档四条逐字未变**（4310486/05:04:35.296、28707/05:04:35.298、4281756/04:49:43.856、28760/04:49:43.857）。
- **SMAPI 窗口在退出后复制**（避开独占）：`logs\run10d-smapi-window.txt` = **77360 B**、mtime `2026-10-17 08:31:19.860`、SHA256 `38282A5CEDFAAD0CA91614B9103029247D181B3C90DAF795FD0423CE815A7031`，**源与副本 `BYTE_IDENTICAL=True`**。
- SMAPI 尾部（原文，控制台显示为乱码但文件是 UTF-8）：`08:31:19 POST /v1/exec → 200` → `TRACE game] Disconnected: ClosedGame` → `TRACE SMAPI] Disposing...` → `INFO AgentFarm Bridge] 已删除发现文件 …\bridge.json` → `Disposing the content coordinator.`（无 Event 1000/1001）。
- end 快照已追加到 `scratch\run10d-external-snapshots.jsonl`（`tag=end`，`at 08:30:47`）：`save_main 4310486/05:04:35.296`、`save_info 28707`、`smapi_lines 464`、`newday 0`、`before_save 0`、`save_task 0`、`save_completed 0`、`bridge pid 3204 / 0.7.36`、`mod_version_matches true`、PID 文件候选**不存在**（本卡不是长跑）。

## §11 保留物 / 不确定项 / 诚实声明

**保留物**：`scratch\_t191_probe.py`；`scratch\_t191_{fields,harvest-60-29,harvest-60-30,usetool-60-29,sell-*}-{before,after,receipt,verdict}.json`；`scratch\run10d-external-snapshots.jsonl`（end 行）；`logs\run10d-smapi-window.txt`；`logs\run10d-baseline.json`（Lead 侧）。

**不确定项（明确写清）**：
1. 判据④里「Mod 回执 `acted=false` ⇒ 脑侧 `code=failed`」这一具体形态**未在真机造出**（脑侧先以 `skipped` 拦截；原始路径又因聚合口径报 `acted=true`）⇒ 按"脑侧零触桥 + 不可收格未被洗白"判定成立，**不宣称已覆盖该形态**。
2. 6c 的破坏性副作用只存在于内存（未落盘、未跨日），因此**无法用退出后重开的观测再次复核**；结论仅由内存中的前后观测差分支撑。
3. `farm.*` 聚合计数在动作后第一张观测里会**滞后一拍**（本卡出现两次：`readyCrops 102→102` 后下一张为 101；`97→97`），单张聚合快照不足以判定成败。
4. 本次测试期间游戏内时钟从 tod 1320 走到 2310（动作与等待消耗），**未跨日、未落盘**。

**诚实声明**：本卡的世界改动全部发生在内存；退出即回滚，样本格 `(60,29)` 与 12 行满背包在存档里原样保留。所有 PASS/FAIL 判定均基于**独立观测差分**与**Mod 原始回执原文**，未使用任何自述替代观测；两条新残留（R7/R8）如实保留、未并入"通过"。
