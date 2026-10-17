# run A′（0.7.36）· task-113 —— **提前叫停（不作验收证据）**

> **§0 结论先行**：run A′ 被「背包满 ⇒ `harvest` 全线被拒」这个**代码缺陷支配**，`checks.no_hard_failures=false` 每天都成立 ⇒ 这条臂**不可能产出 VERIFIED**，也无法作为 A/B 对照的一半。**Lead 于 2026-10-17 08:46 裁定提前叫停**（只杀脑进程、游戏保活），本文件按"提前叫停"格式记录已观测到的全部事实。**本跑不作验收证据；L0–L5 与目标 2 一律不作判定。** B′ 未起跑（对照作废，教训库字节拷贝作废）。

- 执行：teammate `machine-runner`｜卡：task-113（rev13）｜被测版本：**0.7.36**
- 起跑：`2026-10-17T08:37:40+07:00`，脑 PID **14296**（脱离式）
- 叫停：`2026-10-17T08:46:52.660+07:00`（账本 mtime），`Stop-Process -Id 14296`，**游戏保活** PID 16784
- 世界：**未跨日之外无任何写操作**；游戏由 Lead 指定的 patch 版决定后续，我只做只读

---

## §1 版本指纹与起跑（与 sidecar 逐字一致）

| 文件 | SHA256(16) | size | mtime |
|---|---|---|---|
| `brain/agentfarm/longrun.py` | `C326DD1E1358EA15` | 423163 | 2026-10-17T08:08:08.884476 |
| `brain/agentfarm/farmwork.py` | `FA6BD05CCAB9DF25` | 174268 | 2026-10-17T07:43:54.086395 |
| `brain/agentfarm/bridge.py` | `968D1D227A293B1A` | 51696 | 2026-10-17T08:16:50.713914 |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `D6699BD057C51CE7` | 202752 | 2026-10-17T08:17:05.275945 |
| `mod/AgentFarm.Bridge/manifest.json` | `6578C42574237AA8` | 53261 | 2026-10-17T08:16:27.409678 |

- Lead 给的 0.7.36 指纹 **5/5 MATCH**；`HEAD = fb926722b8cb2287d128592e9638f15e44e281cc`（task-194）、`worktree_clean=true`、`git_status_short=[]`。
- sidecar `logs\longrun-runA3-0736.version.json` 的 `argv`（原文）：
  `[python.exe, -u, tools/run-longrun.py, --days, 5, --size, 5, --max-minutes, 240, --max-days, 12, --journal, logs/longrun-runA3-0736.jsonl]`，`pid=14296`、`started_at=2026-10-17T08:37:40`、`boundary_llm=true`。
- 起跑前 `preflight --expect 0.7.36` ✅ ⇒ `logs\runA3-0736-baseline.json`（08:37:04）：`worldSeq 12`、`fall 12 tod 620`、`Farm(64,15)`、体力 247.2/270、钱 0、`seeds [["483","Wheat Seeds",1]]`、`farmingLevel 1`、`crops 102`、`unwateredCrops 2`、`dryCrops 0`、`waterLeft 27`、`tillableCount 120`、无模态、世界推进中。
- **起点世界 = task-191 之前的状态**（存档四条仍为 `4310486/05:04:35.296`、`28707/05:04:35.298`、`4281756/04:49:43.856`、`28760/04:49:43.857`）——task-191 的**腾格两次出货**（`(O)Moss`×35、`(O)390`×3）与**样本格 `(60,29)` 收获**、原始镰刀连带清格，全部**只发生在内存**，`stop-game.py` 优雅退出时**未落盘 ⇒ 已回滚**；因此样本格 `(60,29)` 与"12 行满背包"在存档里**原样保留**，A′ 是在它们之上起跑的。
- **口径标注（Lead m03022 要求）**：baseline 的 `crops 102` 取自 **`farm.*`（全场扫描）**；console `[prep]`/`[day]` 行写的「作物 94」取自**脑侧窗口 `location.tiles[]`**（400 格、玩家中心、`tileCount 400 / tilesTruncated=true`）；`unwateredCrops 2 → 0` 是 **rain 天气替玩家浇的**，不是我或脑侧的动作。本文件后续所有作物/浇水数字都按这两个口径分别标注。

## §2 逐日表（现有 `day_end` 原文；全部 `verified=false`）

| 游戏日 | t(s) | ended_by | verified | ok/skip/fail | `final_water`(farm) | 坏判据 | ended_reason 原文（摘） |
|---|---|---|---|---|---|---|---|
| fall 12 | 180.57 | sleep | **false** | 26/29/60 | dry 0/24 | `no_hard_failures` | `stuck:回片区（guard_leftover） 连续 5 次都拿不出目标（守卫仍说还有活：今天早些时候还有 52 格没做完（跨片地，最近的是 [44, 22]）；field_ne还有地要清/开/种）` |
| fall 13 | 279.95 | sleep | **false** | 21/0/32 | dry 1/24 | `no_hard_failures`、`no_unmet_stages`、`watered_outdoor` | `stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：农场口径还有 8 格熟作物（当前窗口没盖到，别处还有活），先去收）` |
| fall 14 | 397.69 | sleep | **false** | 22/0/42 | dry 0/34 | `no_hard_failures`、`no_unmet_stages` | `stuck:回片区（guard_leftover） 连续 5 次都拿不出目标（守卫仍说还有活：farm 口径还有 109 格耕地空着（手上有 10 粒种子）⇒ 该去种；农场口径还有 1 格熟作物（当前窗口只看到 0 格）；今天早些时候还有 13 格没做完（跨片地，最近的是 [59, 26]））` |
| fall 15 | 544.11 | sleep | **false** | 43/1/42 | dry 1/34 | `no_hard_failures`、`no_unmet_stages`、`watered_outdoor` | `stuck:回片区（guard_leftover） 连续 5 次都拿不出目标（守卫仍说还有活：农场口径还有 1 格熟作物（当前窗口只看到 0 格）；今天早些时候还有 5 格没做完（跨片地，最近的是 [63, 28]）；field_ne还有地要清/开/种）` |
| fall 16 | 544.12 开始 | —（**无 day_end**） | — | — | — | — | 停止点：`[day] 1年 fall 16日 开始：FarmHouse 体力 270 钱 2798g 作物 0（未浇 0）天气 sunny` 之后仅 `· 回到 Farm：` |

- 四个 `day_end` 的 `checks` 共同项：`slept_by_us=true`、`no_blocking_modal=true`、`unreachable_within_bound=true`、`refused_within_bound=true`、`crops_watered=true`、`day_justified=false`、`zero_action_evidenced=true`；**`no_hard_failures=false` 四天全中**。
- `day_start` 5 条：fall 12/13/14/15/16（t=0.12/180.58/279.97/397.71/544.12）。`day_start` 记录的 `final` 为空，钱要看 `buy/sell` 记录：fall 14 开局钱 **2898g**、fall 16 开局钱 **2798g**。
- 事件计数（账本 454 条）：`harvest_gave_up` **80**、`decision` 48、`intent_verdict` 48、`policy` 39、`outcome` 36、`stage_stop_named` 22（**harvest 20** / water_area 2）、`stage_shortfall` 22、`plot` 16、`sell` 16、`water_far` 8、`goto_farm` 7、`sleep` 4、`day_end` 4、`buy` 3、`modal_dismissed` 3、`surplus_sell` 1、`cannot_afford` 1、`refill` 1。

## §3 外部证据（**SMAPI 窗口待冻结**，现在只给只读计数）

**存档四条**

| 时点 | `Wahaha_450799035` | `SaveGameInfo` | `Wahaha_450799035_old` | `SaveGameInfo_old` |
|---|---|---|---|---|
| A′ 起跑前 | 4310486 / 05:04:35.296 | 28707 / 05:04:35.298 | 4281756 / 04:49:43.856 | 28760 / 04:49:43.857 |
| **叫停后（现盘）** | **4333057 / 08:46:42.979** | **29261 / 08:46:42.980** | 4312426 / 08:44:16.580 | 29258 / 08:44:16.582 |

- 轮询期间另见到 `4285980 / 08:40:45`、`4277814 / 08:42:23` 两代（存档只保留两代，中间各次 size 不可恢复）。**大小有涨有落属正常**（内容变化，不是损坏）。
- **SMAPI 窗口（只读计数、未冻结）**：`%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt` **仍在被游戏继续写**（读时 262118 B / 3371 行；其 SHA256 随写入变化，**不作为冻结证据**）。按时间戳切窗 `08:37:40–08:46:52`（命中 2952 行）→

| 计数项 | 窗口内 |
|---|---|
| `Synchronizing 'NewDay' task` | **4** |
| `Context: before save.` | **4** |
| `SaveGame.Save() called.` | **4** |
| `Synchronizing 'Save' task` | **4** |
| `completed without exceptions` | **4** |
| `after save, starting …` | **4** |
| `Warping to Farm` | 1256 |
| `POST /v1/exec` / `GET /v1/observe` | 304 / 1327 |
| `ERROR` / `Disconnected` / `Exception` | 0 / 0 / 0 |

- 四对 `NewDay↔Save` 的时刻（原文）：`08:40:40/08:40:44`、`08:42:20/08:42:23`、`08:44:16/08:44:16`、`08:46:42/08:46:42` ⇒ 与 4 个 `day_end` 的跨日一一对应，**六串 4/4 全配对**（本次未出现"NewDay 无 save"）。
- **冻结待办**：等 Lead 说"可以冻了"，我再把 SMAPI 复制成 `logs\runA3-0736-smapi-window.txt` 并给出 size/mtime/SHA256/`BYTE_IDENTICAL` 判定。

## §4 归因（Lead 已逐条核对账本；以下三行按原文引用）

> - **主因**：`harvest` 被「背包满（空槽 = `inventoryCount` − `inventory[]` 行数 = 0）」全线拒绝 —— 账本里 **45 条** harvest 失败 detail 全是这句（t=57.62/79.47/84.92/123.82/130.29/215.71/255.8/258.62/268.3/299.38/313.06/317.5/339.38/343.38/426.63…），每天 12 格 × 多轮，`harvest_gave_up` 59 次（每格试满 2 次）。
> - **为什么钱/出货没救回来**：`sell`/`ship` 确实在跑（16 条 sell，t=85–188 出货 15+ 件，钱次日结算到 2997g，t=188 还买了 10 个 Wheat Seeds），但**清障/开垦/浇水的掉落持续把背包重新填满**，策略里**没有"腾格优先于收割"的收敛回路** ⇒ 一整天在「收 → 满 → 拒 → give_up」里打转。
> - **次因（独立缺陷，另立案）**：fall 13 的 `stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：农场口径还有 8 格熟作物（当前窗口没盖到，别处还有活），先去收）` ⇒ **窗口外熟作物没有坐标、脑侧走不到**，守卫因此不肯收工（同 run9d 的 `[12,30]` 族；task-50 当年给"干作物"补了 `dryTiles` 坐标，熟作物还缺同款 `readyTiles`）。

**我自己的计数（口径与上面不同，如实并列，不覆盖裁定）**

| 指标 | 记录级 | 逐格级 | 说明 |
|---|---|---|---|
| 提及「背包满」的记录 | **34** | — | outcome 20 / decision 6 / review_llm 4 / day_end 4（按整条记录 JSON 搜字符串） |
| `outcome[kind=harvest]` | **26** | — | 其中 20 条 detail 是"背包满"**逐格列表** |
| 「背包满」拒收 | — | **60 格** | 每条 outcome 的 `detail` 是一格一条，20 条记录合计 60 格 |
| `harvest_gave_up` | **80** | 31 个不同格 | 每条 `attempts=2 / limit=2`；t 从 79.46 到 551 前后 |
| `stage_stop_named[harvest]` | **20** | assigned 176 / undone 176 | zone：`field_se` 18 次、`field_nw` 2 次 |
| 其它 harvest detail | — | 15 格 | 6 条记录，绝大多数是「这一格没有作物」 |

- 经济侧我的读数：`sell` **16** 条（首条 t=85.62 `(O)262`×3）、`surplus_sell` 1 条（t=188.12 `need_slot`，白名单 `(O)771`）、`sell_failed` 1 条（t=108.92「出货没有生效（槽位 9 的 (O)262：背包 1→1，槽位已空）」）、`buy` 3 条（首条 t=188.25 失败：`item_not_sold`「商店 SeedShop 里没有 472」，**钱 2997→2997**）、`cannot_afford` 1（t=64.86，钱 0）、`refill` 1（t=437.15 `waterLeft 0→40`）⇒ 与 Lead 的"卖货在跑、钱次日结算到 2997g"一致。
- 停止点末三条记录：`stamina_budget`（t=551.85，`live_crops 34 / dry 34 / capacity 92`）、`deferred_by_budget{plant_area, why:"今天还有 34 格活苗没浇（farm.dryCrops）⇒ 先浇水，预算不许再播种", tiles:92}`、`budget_deferred_tiles{count:92}` ⇒ 即便在缺陷之下，体力预算与"延后≠洗白"的机制仍按设计工作。

## §5 判定与保留物

- **本跑不作验收证据。L0–L5、目标 2 一律不判**（臂被代码缺陷支配，缺"有效对照"这一前提）。B′ 未起跑；教训库字节拷贝、`compare-runs` 对照本轮**作废**；旧 run A/B、run9c/run9d 证据一律保留作历史。
- **修复线索（供 task-195/196/197/198/199/193 批次参考）**：① 背包空间与"收割→掉落填满"的收敛回路缺失（需要"腾格优先于收割"或"掉落前先腾格"）；② 窗口外熟作物缺坐标（`readyTiles` 同 `dryTiles`）；③ `harvest` 统计口径（记录级 vs 逐格级）需要在 analyzer 里显式说明，否则同一账本会读出 20/26/34/60/80 五个不同数字。
- **保留物（原样、未删、未补造 `finish`）**：`logs\longrun-runA3-0736.jsonl`（454 行、无 `finish`）、`logs\longrun-runA3-0736.version.json`、`logs\runA3-0736-baseline.json`、`logs\longrun-runA3-0736.console.log`（85 行）/`.console.err.log`（0 B）、`scratch\runA3-observe-*.json`（8 份独立观测：fall12 / fall14 / fall15 / fall15-b/c/d / fall16；fall 13 无观测 ⇒【无法判定·窗口错过】）、`scratch\_runA3_stop_digest.py` / `_runA3_counts.py` / `_runA3_tiles.py` / `_runA3_smapi_wincount.py`。
- 游戏状态：**仍在运行（PID 16784，0.7.36，读档 fall 16 日清晨）**，按 Lead 指令保活当修复验证台；未做 `load_save`、未做任何写操作。
