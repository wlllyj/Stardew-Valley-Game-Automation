# run8 证据（Mod 0.7.27 · task-89 · 起跑者 machine-runner）

**状态**：run8 **已结束**（起跑 `2026-10-15T22:21:02` / 账本末条 `t=143.33` = 22:23:25 / PID **6480 已退出**）。**两侧判决 = FAIL（尾部连续 VERIFIED 0/3）**：`tools/verify-run3.py` 尾部窗口口径 **exit 1 / needs_review**；`tools/analyze-longrun.py` 严格整本 **exit 1 / 有红 29 条**（`--window 3` **不启用降级**，因为尾部 0 天）。游戏进程（PID 22272 / 0.7.27）在写本文档时**仍在运行**，按 Lead 指示：先交本文档，随后优雅退出。

判据依据：`docs/_run6-criteria.md`（尾部窗口口径）+ `docs/_release-0.7.27.md` §4（本版四条关注项）。**本证据不使用 `day_end.final.location=="Farm"` 这条已废弃判据。**

---

## §1 起跑与版本四要素

| 项 | 值 |
|---|---|
| `git rev-parse HEAD` | `2bf0d8f8e2a9c1ffae7b54707dca3f066ed90efa`（`2bf0d8f`） |
| `git status --short`（起跑时，sidecar 记录） | `[]`（`worktree_clean: true`） |
| 起跑器 | `python tools/start-detached-longrun.py --journal logs/longrun-3day-llm-run8.jsonl --expect-version 0.7.27`（先跑过 `--dry-run`，EXIT=0、四判据全绿） |
| PID / 起跑时刻 | **6480** / `2026-10-15T22:21:02`（`logs/longrun-3day-llm-run8.pid`） |
| sidecar | `logs/longrun-3day-llm-run8.version.json`（`head` / 五文件 sha256+mtime / `pid` / `started_at` / `worktree_clean`） |

**被测五文件（sidecar 原文，SHA256 / mtime）**

| 文件 | SHA256 | mtime |
|---|---|---|
| `brain/agentfarm/longrun.py` | `D1D02D9AE9AB189685A07676681FA61351F44965F892EB1C76D6EFC310D15CE2` | `2026-10-15T22:09:20.758323` |
| `brain/agentfarm/farmwork.py` | `8B62190A7E4010B835A122360E794ADD82B28…`（sidecar 原文；与 dry-run 打印一致） | `2026-10-15T21:07:05.570` |
| `brain/agentfarm/bridge.py` | `102736ECA189EA4E…` | `2026-10-15T21:26:17.335` |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `6F9F0A50AEB05760…` | `2026-10-15T21:26:06.228` |
| `mod/AgentFarm.Bridge/manifest.json` | `FD8277044B8C115D…` | `2026-10-15T21:26:04.040` |

> 注：上表后四行的 sha256 为 sidecar 原文截断（完整值见 `logs/longrun-3day-llm-run8.version.json`）；`longrun.py` 给出完整 64 位。

**Lead 侧前置（非我执行，如实转录）**：0.7.27 已装机（`AgentFarm.Bridge.dll` **172032 B** / `manifest.json` **21468 B**、桥 `modVersion=0.7.27 port=17890`、已读档）；`tools/check-release.py --expect 0.7.27` 四项全绿（`Ran 594 tests / OK`）；`python -m agentfarm goto Farm` OK（FarmHouse(9,9)→Farm(64,15)、hop1 7611ms）；`tools/preflight.py --expect 0.7.27 --save-baseline logs/run8-baseline.json` 四项全绿（基线 `第1年夏11日 06:20 / Farm(64,15) / 体力 270 / 钱 14g / 种子 [] / 作物 6 / dryCrops 6 / waterLeft 38 / tillable 155 / worldAdvancing true`）。

**刻意不做操作员预置**（Lead 定；`docs/_release-0.7.27.md` §7.2 第 5 步）：钱 14g、种子 0、背包有清障盈余 —— 这正是 task-55「脑自己卖盈余 → 次日到账 → 买当季种子 → 播种」的验收场景，不许先用 `scratch/run6-preseed.py` 卖一遍。

---

## §2 外部证据

### 2.1 起止快照原文（`scratch/run8-external-snapshots.jsonl`，2 行）

**start**（`at 2026-10-15T22:20:45`，**deploy 之后**取 ⇒ `mod_version_matches=true`）：

```json
{"tag": "start", "at": "2026-10-15T22:20:45", "save_main": {"exists": true, "size": 3648782, "mtime": "2026-10-14T23:33:11.539"}, "save_info": {"exists": true, "size": 27909, "mtime": "2026-10-14T23:33:11.542"}, "smapi_lines": 416, "smapi_newday": 0, "smapi_save": 1, "smapi_before_save": 0, "smapi_save_called": 0, "smapi_total_lines": 416, "journal_lines": null, "pid": null, "pid_alive": null, "bridge_info": {"pid": 22272, "modVersion": "0.7.27", "port": 17890}, "expected_mod_version": "0.7.27", "mod_version_matches": true, "written_at": "2026-10-15T22:20:45"}
```

**end**（`at 2026-10-15T22:23:42`）：

```json
{"tag": "end", "at": "2026-10-15T22:23:42", "save_main": {"exists": true, "size": 3706657, "mtime": "2026-10-15T22:22:57.011"}, "save_info": {"exists": true, "size": 27913, "mtime": "2026-10-15T22:22:57.145"}, "smapi_lines": 1705, "smapi_newday": 2, "smapi_save": 3, "smapi_before_save": 1, "smapi_save_called": 1, "journal_lines": 213, "journal_last_event": "finish", "journal_finish": {"event": "finish", "t": 143.33, "code": 1, "verified_streak": 0, "actions": 106, "minutes": 2.39, "stages_seen": ["clear_area", "till_area", "water_area"], "no_unmet_stages": false, "unmet_days": ["1年 summer 13日"], "stuck_flushes": 0}, "pid": 6480, "pid_alive": false, "bridge_info": {"pid": 22272, "modVersion": "0.7.27", "port": 17890}, "mod_version_matches": true, "written_at": "2026-10-15T22:23:42"}
```

### 2.2 存档前进（外部证据）

| 时点 | `Wahaha_450799035` | `SaveGameInfo` |
|---|---|---|
| start | 3648782 B / `2026-10-14T23:33:11.539` | 27909 B / `2026-10-14T23:33:11.542` |
| end | **3706657 B** / **`2026-10-15T22:22:57.011`** | 27913 B / `2026-10-15T22:22:57.145` |

⇒ run8 窗口内**确实落了一次盘**（+57875 B），与 SMAPI 的 `after save, starting summer 13 Y1`（`2026-10-15T22:22:58`）同向。

### 2.3 SMAPI 窗口（冻结副本）

`logs/run8-smapi-window.txt` = **133851 B / 1705 行 / SHA256 `A3FABA90C06A10F725682159614797D2493DC0DD291E4FD8958F8245CAADA62A`**（冻结时点 `22:23:26`）。

| 关键行 | 次数 | 行号/时刻 |
|---|---|---|
| `Synchronizing 'NewDay' task` | **2** | L684 `22:22:49`、L865 `22:22:55` |
| `Context: before save.` | **1** | L868 |
| `SaveGame.Save() called.` | **1** | L869 |
| `Synchronizing 'Save' task` | **1** | L870 |
| `SaveGame.Save() completed without exceptions.` | **1** | L873 `22:22:57` |
| `after save, starting …` | **1** | L874 `22:22:58` → **summer 13** |
| `ERROR` | 1 | L66（Steam 未加载，与 run 无关） |
| `Disconnected` / `ClosedGame` / `Disposing` / `Exception` / `soft_oal` | **0** | — |
| `Warping to Farm` | 627 | task-14 逐帧活锁，**信息项**（不判成败） |

### 2.4 「跨日 ≠ 落盘」（task-47 口径）

账本 3 个游戏日里有 **2 次跨日**（summer 11→12、12→13），但 SMAPI 只有 **1 组** `Context: before save.` → `SaveGame.Save() called.`。对应关系：`NewDay task` 两次（22:22:49 = summer 11→12 那次；22:22:55 = 12→13 那次），**落盘那次是 12→13**。

⇒ **summer 11→12 那次跨日没有落盘**，形态与 task-47 定的"日终菜单链没走完"同型（该日睡前 `after.activeMenu="ShippingMenu"`）。按 `docs/_run6-criteria.md` §2 口径：**有日终菜单时不判失败也不判通过**（只是外部证据缺口，如实记录）。

### 2.5 `day_after` 链

`summer 11` → `[1,"summer",12]` → 账本 `day_after=[1,"summer",13]`；summer 13 无 `day_after`（`sleep_failed`）。⇒ 有效跨日 2 次，链路逐日 +1，无跳日/倒退。

---

## §3 逐日表

| 游戏日 | `day_start`（钱/作物） | `ended_by` | `day_after` | `verified` | 阶段 ok/skip/fail | 睡前 `final_water`（farm 口径） | 未过的 checks |
|---|---|---|---|---|---|---|---|
| **summer 11** | 14g / 5 | `sleep` | `[1,"summer",12]` | **True** | 9 段：**19 ok** / 0 skip / 0 fail（`tiles 22`、`leftover 3`） | `tiles 99 / crops 6 / dry 0` | 全过（9 项 true，含 `unreachable_within_bound`/`refused_within_bound`） |
| **summer 12** | 188g / 0（醒在 FarmHouse） | `sleep` | `[1,"summer",13]` | False | **0 段 / 0/0/0** | `tiles 91 / crops 6 / **dry 6**` | `watered_outdoor=false`、`day_justified=false` |
| **summer 13** | 188g / 0 | **`sleep_failed`** | **无** | False | 2 段：0 ok / 0 skip / 0 fail（`tiles 13`、`leftover 23`） | `tiles 81 / crops 6 / dry 0` | `unreachable_within_bound=false`（13 格 > bound 5）、`no_unmet_stages=false`（leftover 23）、`day_justified=false` |

三个 `ended_reason` 原文（关键两天的完整文本）：

- **summer 11**：`no_work:…`（当天完成浇水+清障+认输 3 格后主动睡觉）；`final_water` farm 口径 `dry 0/6` ⇒ `watered_outdoor=true`。
- **summer 12**：
  `stuck:守卫说还有活（没种子但钱够（188g ≥ 20g），该去买；人不在农场，但 farm 口径还有 6 格干作物（先回去浇））但没有任何作业区拿得出目标`
- **summer 13**：
  `回不了 FarmHouse：[ui_modal] …人在 (64,15)（Farm）`

补充读数：`final` 是**睡前快照**（所以 `counts_scope="window"` 在室内恒 0），`final_water` 才是 farm 口径浇水证据；summer 12 的 `dry 6/6` 与 `watered_outdoor=false` 自洽 ⇒ **不是假 VERIFIED**（task-96/99 的 fail-closed 在本轮方向正确）。

---

## §4 判据对照（**两侧结论都写**）

### 4.1 尾部窗口口径（**权威**，`tools/verify-run3.py --days 3`）

**exit code = 1 / 结论 `needs_review`**，`尾部连续 VERIFIED 天数 0 / 要求 3`。

日表（工具输出原文）：

```
日           ended_by      跨日    睡前未浇     作物    钱     阶段   ok   skip  fail  verified
summer 11   sleep         True  0        0     14    9    19   0     0     True
summer 12   sleep         True  0        0     188   0    0    0     0     False
summer 13   sleep_failed  False 0        4     188   2    0    0     0     False

decision 22 条（LLM 调用 3 条 / 其中模型产出 3 条）
```

**问题 8 条（原文）**：

1. `[summer 12] checks.watered_outdoor=false（睡前还有没浇的作物）`
2. `[summer 12] day_end verified=false`
3. `[summer 13] ended_by=sleep_failed（不是我们主动睡过去的）`
4. `[summer 13] checks.unreachable_within_bound=false（不可达豁免超出上界 bound=5）⇒ 可能把真失败/不可动格混进不可达来洗白，必须人工核对 unreachable_tiles`
5. `[summer 13] day_end verified=false`
6. `[summer 13] 当天有 1 次 sleep 失败（回执 ok=false）`
7. `[summer 13] checks.no_unmet_stages=false（有阶段后置条件未成立；自算有目标阶段 leftover=23 格）`
8. `journal 里出现 跨日没有推进 ×1`

**`history_problems`（窗口外历史问题）= 0 条**（本跑整本都在尾部窗口内，因此窗口口径与整本口径这次没有差异 —— 与 run7 那种"窗口外 9 条"的形态不同）。

不可达坐标（summer 13 的 13 格，工具给出 8 个代表格）：`[[29,51],[30,52],[31,51],[56,20],[57,20],[57,21],[58,20],[58,21]]`；日级 `count=13 / bound=5 / attempted=13 / exempt=5`。

### 4.2 严格整本口径（`tools/analyze-longrun.py`，第二判决）

**exit code = 1**：`VERIFIED: 1/3 天`；`退出码 1；有红 29 条`（`manual:check:unreachable_within_bound`、`missed:cancel:clear_area`、`missed:check:day_justified`、`missed:check:no_unmet_stages`、`missed:check:slept_by_us`、`missed:check:unreachable_within_bound`、`missed:check:watered_outdoor`、`missed:plot_exhausted`、`missed:stage_exhausted`）。
窗口行原文：`窗口: --window 3（尾部连续 VERIFIED 0 天，不足 ⇒ **不启用窗口降级**（窗口外也照常 fatal，历史问题不能替本跑开脱））；窗口内红 29 条；窗口外历史问题 0 条`。
其余关键行：`种子经济: 买不到 1 次（没货 0 / 买不起 1）；当天失效留痕 seed_unavailable_today 0 次 ⚠ 有买不到结论但没有当天失效留痕 ⇒ 守卫可能还在要「去买」（run6 死锁形态）`；`模态: 打断 24 次（信息项）；必须人工介入（红）1 条`；`不可达: 16 次 / 16 格`；`三腿覆盖：播种 全程 0 步成功`。

⇒ **两侧同判 FAIL**；差异只在红条计数（8 vs 29），因为 `verify-run3` 只把"日级闸门"当问题，`analyze-longrun` 还把阶段级/事件级漂移一并计入。

### 4.3 本版四条关注项（`docs/_release-0.7.27.md` §4）

| 关注项 | 判定 | 读数 |
|---|---|---|
| ① 同日全链：`sell` → `buy` 成交 → `sow ok>0` → `water_area` 覆盖新播格 | ❌ **未达成** | 卖出腿过（见 §5②）；`buy` 26 次 **0 成交**；`plant_area`/`sow` **0 步成功**；无新播格 ⇒ 最后一条无从检验 |
| ② `seed_gate {seeds:0}` 显著减少 | ⚠ 部分 | `seed_gate` 1 次（run7 为 5 次）⇒ 次数下降；但 `buy` 仍 0 成交，且**没有** `cannot_afford` 之外的"钱没到账"留痕（`seed_unavailable_today` 0 次） |
| ③ 死苗不再被浇水（`water_area` 不含 `dead=true`；`clear_dead` 在 `water_area` 之前） | ⚠ **真空未验** | 本轮 `farm.deadCrops=0`、`farm.dryDeadCrops=0`、`day_end.dead_crops=0` **全程为 0** ⇒ 无死苗，该判据本轮**没有真机证据**（不算通过，也不算失败） |
| ④ 田块规整（task-83 入版时才判） | — | 本版未启用 |

其他口径：真空日闸门（"自称 VERIFIED 但当天成功动作 0 步"）**未被触发**（day 11 有 19 ok）；豁免不得洗白 ⇒ summer 13 **正是被 `unreachable_within_bound=false` 判掉的**（豁免没有洗白成功）；落盘口径"跨日 ≠ 落盘"见 §2.4。

---

## §5 归因与遗留（卡面五问逐条）

### ① 播下的苗当天有没有被浇到？

**本轮没有播种**：`plant_area`/`sow` 全程 **0 步成功**，`finish.stages_seen = ["clear_area","till_area","water_area"]`（无 `plant_area`），`verify-run3` 直白写着「三腿覆盖：播种 全程 0 步成功」。⇒ 这条判据**本轮无法回答**（没有新播格可检验），不构成通过/失败证据。**归因**：种子 0 粒 + 钱不够（day 11 只有 14g）→ day 12 钱到了 188g 但**背包 0 空格**买不进来（见 §6-A）。

### ② 脑有没有自己完成"卖 → 买 → 种"？

- **卖：成功了。** `sell` 1 条（`t=0.2`，**游戏日 summer 11**，`strategy=surplus_materials`，slot 8 `(O)771 Fiber` **stack 174 整叠**进箱，`keep 10` 但 `below_keep=true`）+ `surplus_sell` 1 条（`sold 174`）。同批 Clay 17 / Coal 16 / Wood 97 / Stone 163 **全部 `sell 0`**（Mod 侧只能整叠出货，`keep K=10` 能力缺失 —— task-55 已知缺口）。
- **钱的结算口径正确**：当天 `money` 不变（14g，设计如此）；**次日 `NewDay` 结算后 `day_start #62` 的 money = 188g = 14 + 174**，与卖出叠 `sellToStorePrice(-1) × stack` 合计**恰好相等** ✓。
- **买：失败（但卡点不是"买不起"，而是背包满）。** `buy` 共 **26 次 / 成交 0**：① 1 次 `item_not_sold`（先探 `472` Parsnip Seeds = **春季**作物；回执带在售清单 `Melon Seeds(80g) / Tomato Seeds(50g) / Blueberry Seeds(80g) / Pepper Seeds(40g) / **Wheat Seeds(10g)** / Radish Seeds(40g) / Poppy Seeds(100g) / Spangle Seeds(50g)…`）② **25 次 `no_inventory_space`**（回执原文：`背包既没有空格、也没有「Wheat Seeds」的同类堆叠可以并入（空格 0），为避免扣了钱却拿不到东西，本次不购买。请先腾出背包空间`）。**当季筛选逻辑本身正确**（跳过春季的 472，选中当季最便宜的 `(O)483 Wheat Seeds 10g`）。
- **种：0 步。** 没买到种子 ⇒ `plant_area`/`till_area` 无目标。
⇒ 四腿里 **卖腿过、结算过、买腿与种腿没过**；卡点=**背包 0 空格**（不是钱、不是货架、不是季节判定）。**注意**：不能简写成"没成交"，卖是成功的，只有买在最后一步失败。

### ③ 死苗是否还被浇水？

**本轮没有死苗**：`farm.deadCrops=0` / `farm.dryDeadCrops=0` / `day_end.dead_crops=0` / `day_end.dry_dead=0` 三个游戏日全程为 0。⇒ task-84 的"死苗不浇水 + `clear_dead` 提前"这条判据**真机未被检验**（真空）。`water_area`/`water_far` 的 tiles 里没有 `dead=true` 格这一点，本轮**无法与非死苗形态区分**，如实记为**未取得证据**。

### ④ `[12,30]` 类"够不着的格"是否还在烧整天？

**还在，但已收敛为有界重试 —— 不再烧整天。** 读数：

- **day 11（summer 11）成功浇到窗口外远距格**：notes 原文 `浇了窗口外那格干作物 [12, 30]（第 1 次尝试；farm.dryCrops 6→6）`、`浇了窗口外那格干作物 [60, 29]（第 1 次尝试；farm.dryCrops 6→5）`。⚠ **`[12,30]` 那格回执 ok 但 `farm.dryCrops` 6→6 没掉** ⇒ 该格"浇水后证据不动"（原因未定，见 §7 不确定项）。
- **day 12**：notes `窗口外干作物 [12, 30] 没浇成（第 1/2 次）：unreachable` →（第 2/2 次）`不再试这一格`；当天 `unreachable` 日级 0 格、另有 **6 格干作物认输**（`analyze-longrun`：`当天有 6 格干作物认输（不再当"有活"）`）。
- **day 13**：`unreachable` **13 格**（> bound 5）⇒ 这条正是把当天判掉的原因之一。
- 整轮 `water_far` 事件 **14** 次；`unreachable` 事件 **16 次 / 8 个代表格**。

⇒ 与 run7 相比：**"试 2 次就不再试 + 日级认输记账"已生效**（不再整天烧在一格上），但"够不着"本身**没有解决**（task-52/task-68/task-78 的既有遗留）。

### ⑤ 有没有出现 `farm_evidence_unavailable`，它有没有伴随假 VERIFIED？

**0 次**（事件计数里没有该事件）⇒ **没有"它伴随假 VERIFIED"的实例**。反方向的证据在：day 12 收尾时 `final_water.farm dry=6` + `watered_outdoor=false` + `verified=false`，`ended_reason` 明确抱怨"人不在农场，但 farm 口径还有 6 格干作物" ⇒ **fail-closed 方向正确**（task-96/task-99 的修法本轮没被绕过）。

---

## §6 两条新病灶（Lead 要求单列；影响 task-102 的修法）

### 6-A 背包 0 空格 ⇒ 买种子死锁，一整天 0 农场动作

**证据链（账本 + 回执原文）**

- 时间压缩：`t=108.19 → 110.26` **两秒内 13 轮**「开商店 → `no_inventory_space` → 关商店 → 再开」；day 12 模态打断 **13 次**、day 13 **11 次**；全轮 `modal_dismissed` **24 次 = ShopMenu×23 + ShippingMenu×1**。
- `buy` 26 次全败：1×`item_not_sold` + **25×`no_inventory_space`**（回执见 §5②）。
- 后果：day 12 `day_end #104` 的 **`stages: []`、`ok/skip/fail = 0/0/0`**、`final_water dry 6/6`、`watered_outdoor=false`、`verified=false`、`ended_by=sleep`（`t=115.83`，游戏内才 06:20 出头就收工）。
- 工具警告（`analyze-longrun.py` 原文）：`种子经济: 买不到 1 次（没货 0 / 买不起 1）；当天失效留痕 seed_unavailable_today 0 次 ⚠ 有买不到结论但没有当天失效留痕 ⇒ 守卫可能还在要「去买」（run6 死锁形态）`。
- 账本 note 原文（同日）：`补种子（shelf 10g）：没成交：物品 0→0，钱 188→188；回执=no_inventory_space: …（空格 0），为避免扣了钱却拿不到东西，本次不购买。请先腾出背包空间`。

⇒ **机制**：守卫说"没种子但钱够 ⇒ 该去买"（合法），买入被背包满挡住，**"当天不再买"的失效留痕缺失** ⇒ 同一天反复重试，把整天的动作预算烧光，农场一圈没动。这正是 Lead 立 **task-102-A**（空格死锁腾格）要修的形状。

### 6-B 早晨第一件事没做成 ⇒ 直接滑到收尾（早睡防线缺失）

- day 12 醒来在 `FarmHouse`，`goto_farm` 在 `t=107.91` 被**晨间 `ShippingMenu`** 挡成 `[ui_modal]` 失败（note 原文：`回不去 Farm：去 Farm 失败：[ui_modal] …当前有菜单/对话/过场打开，无法移动（请先关闭模态）`；随后 `t=107.95` `modal_dismissed ShippingMenu` 关掉了它）。
- **关框之后没有重试 `goto_farm`**：当天唯一的动作是 §6-A 的 buy 循环，然后在 `t=115.83`（游戏内 ~06:2x）以 `ended_by=sleep` + `ended_reason=stuck:守卫说还有活…但没有任何作业区拿得出目标` 收尾 ⇒ **0 阶段、0 动作**、`dry 6/6`。
- 结果：day 12 全天没有在户外做任何一件事，`watered_outdoor=false` ⇒ 整天不 VERIFIED。

⇒ **机制**：晨间模态（`ShippingMenu`）让"离家"这一步失败一次，重试链没接上，守卫又因"人不在农场 + 窗口口径"找不到目标 ⇒ 早睡。这正是 **task-102-B**（早睡防线）要修的形状。

### 6-C 附带：`ShopMenu` 残留把第 3 天的 `sleep` 卡成 `sleep_failed`

day 13 结尾 `ended_reason = 回不了 FarmHouse：[ui_modal] …人在 (64,15)（Farm）`。即 §6-A 反复开关的 `ShopMenu` 残留（或再次打开）让"回家睡觉"这一步失败 ⇒ `day_after=null`、`跨日没有推进`、`sleep_failed`。**没有替游戏做选择、没有手动 dismiss**（全部 dismiss 都是 `longrun._clear_modals` 自己发的，24 次全部记录在账本里）。

---

## §7 保留物、不确定项与诚实声明

**保留物（不删）**：`logs/longrun-3day-llm-run8.jsonl`（213 行）、`.pid`、`.llm.jsonl`、`.console.log`（128 行）、`.console.err.log`（**0 B**）、`logs/longrun-3day-llm-run8.version.json`、`logs/run8-baseline.json`（Lead 权威基线）、`logs/longrun-3day-llm-run8-baseline.json`（起跑器副本）、`logs/run8-smapi-window.txt`、`logs/run8-smapi-counts.txt`、`logs/run8-journal-extract.txt`、`logs/run8-verify.txt`、`logs/run8-analyze.txt`、`scratch/run8-snapshot.py`、`scratch/run8-extract.py`、`scratch/run8-external-snapshots.jsonl`。

**不确定项（不编）**：

1. 游戏存档只保留两代（main + `_old`），**窗口内中间各次落盘的 size 不可回溯**；本文档只给起止两点 + SMAPI 行号。
2. `[12,30]` 那格"回执 ok 但 `farm.dryCrops` 6→6 没掉"的**原因未定**（Mod 未真浇 / 该格是死苗 / 窗口口径差异，三种都可能）；与 run7 那颗 `[12,30]` 同坐标，值得单独立卡。
3. SMAPI 里 `eventUp`/`DialogueBox`/`LevelUp` 各命中 1 次，**全部是 L16 的插件描述文本**，不是运行事件；账本里这四个关键词 **0 次**（⇒ task-41 未触发，本轮无剧情事件、无升级弹窗）。
4. day 12 的 `ended_by=sleep` 是"守卫说要活但没目标"的 `stuck:` 收尾被记成 `sleep`；`day_justified=false` 如实标出，**没有被洗成 VERIFIED**。

**诚实声明**：本文档所有数字来自账本 / SMAPI 冻结副本 / 存档 stat / 两个检查器的实际输出；我没有改任何源码、Mod、工具或测试；没有替游戏做任何选择；run8 期间 `ui.eventUp` 从未为 true。截至写本文档时游戏仍在运行（PID 22272），按 Lead 指示**先交文档、随后优雅退出**。
