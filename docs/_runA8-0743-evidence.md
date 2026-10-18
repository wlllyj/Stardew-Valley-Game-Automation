# A8 臂（0.7.43 · 2026-10-18）取证 —— **缺陷支配，不作 A″ 验收证据**

> **§0 结论先行**：A8 = 0.7.43 上 A″ 臂的一跑（起跑 `2026-10-18T14:54:23`，脑 PID **6852**，脱离式），共 **12 个游戏日（winter 7→18）**，`finish{code:1, verified_streak:0, actions:536, minutes:26.24}`，**7/12 天 VERIFIED**。
> **A8 不作 A″ 验收证据：5 个失败日全部落在两条系统性死循环上** —— winter 7/12/18 = `work_spot_resume` 连续 5 次拿不出目标即收工（§5-A），winter 9/14 = encircled/unreachable 的「1 格余量」当天被反复重分（§5-B）。这不是农务能力不足，而是收工回路与阶段分配的两条逻辑缺陷；同构建再跑 B8 会撞同样两条 ⇒ 拿不到可用对照（B8 未起跑）。
> 另：前任 Lead 会话 `2026-10-18 15:08:21` 上下文硬顶死亡、看护子代理 15:09 一起失败；A8 脑进程跑到 **15:20:38** 自己收尾后**无人执行 `stop-game`**，游戏继续到 **17:03:54**（SMAPI 末次保存 `starting winter 26 Y1`，期间再落盘 7 次）。**这 7 次无人值守跨日全部列废数据**，不进本文件任何结论（Lead 裁定，见 `docs/00-开发日志.md` 条目 084/085）。

- 执行：teammate `machine-runner`｜卡：task-1｜被测版本：**0.7.43**（冻结提交 `5679562`）
- 证据源：`logs\longrun-runA8-0743.jsonl`（1322 行）、`logs\longrun-runA8-0743.version.json`、`logs\ab-backup\A8-start\MANIFEST.json`、`%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt`（9506 行 / 689226 B / mtime `2026-10-18 17:03:54`）、当班快照 `scratch\runA8-observe*.json` ×4、`logs\runA8-0743-sixchain-progress.jsonl` ×3
- 取证时现场（2026-10-18 17:3x 实测）：无 `StardewModdingAPI`/`Stardew Valley` 进程、`netstat` 无 17890 LISTENING、`%APPDATA%\StardewValley\AgentFarm\bridge.json` 不存在（陈旧残留已由 Lead 归档清理）
- 本文件所有数字带「文件:行号」；账本行号 = `logs\longrun-runA8-0743.jsonl` 的 **1-based 行号**；SMAPI 行号 = 源文件行号 = 窗口副本 `logs\runA8-0743-smapi-window.txt` 行号（窗口从第 1 行开始，两者一致）

---

## §0 起跑 / 收尾与臂有效性判定

### 0.1 起跑

| 项 | 值 | 出处 |
|---|---|---|
| 构建 | 0.7.43，冻结提交 **`5679562`** | `logs\longrun-runA8-0743.version.json:2`（`head=56795627113d38d80a93fa13fe1472e85eba4113`） |
| worktree | `worktree_clean=true`、`git_status_short=[]` | 同文件 `:27-28` |
| 脑进程 | PID **6852**，`started_at=2026-10-18T14:54:23`，`boundary_llm=true` | 同文件 `:25-26`、`:44` |
| argc/argv | 8 个 token，原文见 §1.3 | 同文件 `:29-43` |
| 游戏启动 | `14:50:12`（SMAPI 首行；14:50:21 发起 `load_save`，14:50:27 读档完成 winter 7 Y1） | SMAPI `:1`、`:68`、`:87` |
| 世界起点 | 第 1 年 winter 7 日 06:40 · Farm(64,15) · 体力 270 · 钱 2767g · farmingLevel 3 · crops 0 · waterLeft 13 · tillable 177 · `tilesTruncated=true` | `logs\longrun-runA8-0743-baseline.json:2-30` |
| 同起点备份 | `logs\ab-backup\A8-start\`（四件 + MANIFEST，14:54:22 落） | §1.4 |

### 0.2 收尾

- `day_cap`：账本 `:1321` `{"event":"day_cap","t":1574.51,"days":12,"max_days":12}` ⇒ **以 max-days 上限自然收尾**。
- `finish`：账本 `:1322` 原文 `{"event":"finish","t":1574.53,"code":1,"verified_streak":0,"actions":536,"minutes":26.24,"stages_seen":["clear_area","plant_area","till_area","water_area"],"no_unmet_stages":false,"unmet_days":["1年 winter 9日"],"stuck_flushes":2,"cleanup_modal_stuck":false,"cleanup_attempts":0,"cleanup_menu":""}`。
- 收尾时刻：14:54:23 + 1574.53 s ≈ **15:20:37.5**；账本 mtime = `2026-10-18 15:20:38`（与 §3 窗口末行 15:20:38 一致）。
- 12 天逐日：winter 7 ✗ / 8 ✓ / 9 ✗ / 10 ✓ / 11 ✓ / 12 ✗ / 13 ✓ / 14 ✗ / 15 ✓ / 16 ✓ / 17 ✓ / 18 ✗（逐日读数见 §2）。
- `unmet_days` 只写 `1年 winter 9日`：winter 14 的 `no_unmet_stages=true`（两条豁免被扣完），但 `day_justified=false` ⇒ 仍不 VERIFIED（口径见 §5-B 末）。

### 0.3 臂有效性判定（Lead 已拍板 + 本文件复核）

| 判据 | 读数 | 结论 |
|---|---|---|
| 失败日是否可归因于**能力/农务**？ | 5 个失败日 = winter 7/9/12/14/18；winter 7/12/18 的失败发生在**已做成 46/13/19 步之后**的回片区环节；winter 9/14 的失败发生在**唯一一格被围/走不到**的重复分配上 | **否 ⇒ 两条系统性死循环**（§5） |
| 是否可用作 A″ 验收证据？ | 被缺陷支配 ⇒ 无法产出「尾部连续 5 天全 VERIFIED」（§6） | **否：不作 A″ 验收证据** |
| 能否用同构建补 B8 对照？ | B8 会撞同样两条 | **不补（B8 未起跑）** |
| 事故链是否污染证据？ | 脑停后无人值守 7 次落盘（15:35:20→17:03:54） | **是：全部列废数据**（§3 末、§4） |

> 依据：A′ 先例「A/B 试验必须边跑边判臂有效性」（`docs/00-开发日志.md` 条目 076）；用户 2026-10-18 拍板「A8 判缺陷支配、不作验收证据，修 0.7.44 后重跑 A9/B9」（条目 085）。

---

## §1 起跑四要素

### 1.1 HEAD 与五文件指纹（SHA256 全部取自 sidecar 原文；现树复算 5/5 一致）

- `HEAD`（起跑时）= **`56795627113d38d80a93fa13fe1472e85eba4113`**（`logs\longrun-runA8-0743.version.json:2`）= `5679562`「chore(release): 冻结 0.7.43」。
- 取证时仓库 HEAD = `8f0605c`（其后 Lead 的 docs 收尾提交）；**五文件内容与 mtime 均未动**（下表末列 = 取证时复算，逐字 MATCH）。

| 文件 | SHA256（sidecar 原文） | size（现树） | mtime（sidecar 原文） | 现树复算 |
|---|---|---|---|---|
| `brain/agentfarm/longrun.py` | `FF031D7791A85DAB54B13E3FC5EAD59C34A24F196C7577CC992E5BD2B878369D` | 591736 | `2026-10-18T14:40:02.195480` | SHA256 MATCH / mtime MATCH |
| `brain/agentfarm/farmwork.py` | `88E14811260363F606EFA55C688E8DDB46E6BF3A7DE1162E2CDC5645F38370A0` | 231217 | `2026-10-18T13:49:08.914712` | MATCH / MATCH |
| `brain/agentfarm/bridge.py` | `992FB6A4785A4A25993BDE819F7BC0FA20BA5D48008BF4008CB3DFC95844AFC4` | 69493 | `2026-10-18T14:49:24.869617` | MATCH / MATCH |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `806C1069D217EEEFAB6D3354BA09DA049847D97EE5B4A1D2D65845F1DCB0B17F` | 286208 | `2026-10-18T14:49:33.013124` | MATCH / MATCH |
| `mod/AgentFarm.Bridge/manifest.json` | `3CED533859272EBC7246012020270F4667654B9435773D079E48FEADB881244C` | 70055 | `2026-10-18T14:49:06.614997` | MATCH / MATCH |

> 复算命令：`python scratch\_t250_a8_evidence.py --check-files`（只读；读数见 §8.1）。

### 1.2 五文件 sidecar 原文位置

`logs\longrun-runA8-0743.version.json:3-23`（`files` 对象，逐文件 `sha256`+`mtime`）；本文件 §1.1 表格从该处逐字抄出，未补造。

### 1.3 argv（sidecar 原文，`logs\longrun-runA8-0743.version.json:29-43`）

```json
"C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe",
"-u",
"tools/run-longrun.py",
"--days", "5",
"--size", "5",
"--max-minutes", "240",
"--max-days", "12",
"--journal", "logs/longrun-runA8-0743.jsonl"
```

- 起跑为**脱离式**（脑进程独立于会话；会话 15:08 死亡后仍跑到 15:20:38 —— 正是脱离式的证据，也是「无人收尾」事故的前提）。

### 1.4 A8-start 四件（`logs\ab-backup\A8-start\MANIFEST.json` 原文 + 现盘复算）

| 文件 | size | mtime（manifest 原文 epoch → 本地时间） | SHA256（manifest 原文） | 现盘复算 |
|---|---|---|---|---|
| `Wahaha_450799035` | 3134243 | `1792307308.4710822` → 2026-10-18 14:08:28 | `E38D0771EFAB1D0D387E5B8BEA49656FC0D35E49A5341D6A04A17CAAC55B0E22` | MATCH |
| `SaveGameInfo` | 31566 | `1792307308.4743526` → 2026-10-18 14:08:28 | `0735FF7DB77A5575153A15B6477A613DE250D858395A3676E008D0EC063D9777` | MATCH |
| `Wahaha_450799035_old` | 3172619 | `1792307198.941477` → 2026-10-18 14:06:38 | `DB0880884FD9BE47E855C340C7CE057B92809626D8DE8BDFC3099BDB4A3417BB` | MATCH |
| `SaveGameInfo_old` | 31317 | `1792307199.0395067` → 2026-10-18 14:06:39 | `B6E4B75B3BBD789B565038253B6A36C8B94FC3C546B9882FE3922F05FF26BE1C` | MATCH |

- `MANIFEST.json` 文件本身 size 674 / mtime `2026-10-18 14:54:22`（早于起跑 14:54:23）。
- ⇒ **起点存档可逐字节复核**（4/4 size+SHA256 与现盘备份一致；mtime 被备份保留）。

### 1.5 「新的一对起点」声明（Lead 要求写死）

A8 起点 = **winter 7**；A9/B9 已改为新起点 **winter 26**（`docs/00-开发日志.md` 条目 085、task-8 卡面）。**A8 与 A9/B9 不是同一对起点，不可跨对做 A/B 比较**；A8 只作历史臂与缺陷取证，A9/B9 是**新的一对**（同起点、同构建、唯一差异 = 教训库）。

---

## §2 逐日表（12 个 `day_end`；全部取自 `logs\longrun-runA8-0743.jsonl` 原文）

| # | 游戏日 | `day_start`–`day_end` 行号 | ended_by | verified | ok/skip/fail | `checks` 里 false 的键 | clear_area 阶段 / 其中「1 格余量 incomplete」 | ended_reason（原文截取） |
|---|---|---|---|---|---|---|---|---|
| 1 | winter 7 | 1–139 | sleep | **false** | 46/0/0 | `unreachable_within_bound`、`day_justified` | 20 / 0 | `stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标（守卫仍说还有活：今天早些时候还有 149 格没做完（跨片地，最近的是 [41, 18]））` |
| 2 | winter 8 | 140–240 | sleep | true | 69/0/0 | — | 21 / 0 | `no_work:当季（winter）没有可种的种子：手上有 Wheat Seeds 但都隔季，而 farm 口径还有 37 格耕地空着 ⇒ 今天没有可做的活（证据：Mod player.seeds[].plantableNow）` |
| 3 | winter 9 | 241–518 | stuck | **false** | 21/0/0 | `slept_by_us`、`no_unmet_stages`、`day_justified` | 34 / **28**（27 个 assigned=1，1 个 assigned=2） | `stuck:连续 3 轮世界没有任何变化（最后意图：['clear_area']；策略说有进展：False）；守卫仍说还有活：今天早些时候还有 209 格没做完（跨片地，最近的是 [43, 27]）；field_sw还有地要清/开/种` |
| 4 | winter 10 | 519–533 | sleep | true | 12/0/0 | — | 1 / 0 | `no_work:…farm 口径还有 30 格耕地空着…` |
| 5 | winter 11 | 534–553 | sleep | true | 12/0/0 | — | 2 / 0 | `no_work:…farm 口径还有 28 格耕地空着…` |
| 6 | winter 12 | 554–581 | sleep | **false** | 13/0/0 | `day_justified` | 2 / 0 | `stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标（守卫仍说还有活：今天早些时候还有 216 格没做完（跨片地，最近的是 [51, 33]））` |
| 7 | winter 13 | 582–606 | sleep | true | 12/0/0 | — | 3 / 0 | `no_work:…farm 口径还有 20 格耕地空着…` |
| 8 | winter 14 | 607–1200 | stuck | **false** | 45/0/0 | `slept_by_us`、`day_justified` | 75（clear_area 73 + till/plant 各 1）/ **62**（全部 assigned=1） | `stuck:连续 3 轮世界没有任何变化（最后意图：['clear_area']；策略说有进展：False）；守卫仍说还有活：今天早些时候还有 1 格没做完（跨片地，最近的是 [37, 35]）；field_nw还有地要清/开/种` |
| 9 | winter 15 | 1201–1225 | sleep | true | 12/0/0 | — | 3 / 0 | `no_work:…farm 口径还有 17 格耕地空着…` |
| 10 | winter 16 | 1226–1250 | sleep | true | 12/0/0 | — | 3 / 0 | `no_work:…farm 口径还有 17 格耕地空着…` |
| 11 | winter 17 | 1251–1285 | sleep | true | 16/0/0 | — | 5 / 0 | `no_work:…farm 口径还有 15 格耕地空着…` |
| 12 | winter 18 | 1286–1320 | sleep | **false** | 19/0/0 | `day_justified` | 3 / 0 | `stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标（守卫仍说还有活：今天早些时候还有 177 格没做完（跨片地，最近的是 [64, 37]））` |

**逐日复核要点**

- 12 天 `ok_steps` 合计 **289**、`skipped_steps=0`、`failed_steps=0`；`finish.actions=536`（含移动/观测动作，与 ok 不同口径）。
- 7 天 VERIFIED = winter 8/10/11/13/15/16/17；这 7 天的收尾理由全部是 `no_work:当季（winter）没有可种的种子…`，`verify-run3` 同时给「VERIFIED 但只涉及一个阶段（['clear_area']）⇒ 供复核」的 info（冬季无作物，农务腿结构性缺席，见 §7）。
- **winter 9 / winter 14 的 `ended_by=stuck` 却 `checks.slept_by_us=false`，但账本随后确实有 `sleep` 且 `day_after` +1**（`logs\longrun-runA8-0743.jsonl:512`、`:1194`，`sleep.ok=true` 原文「已跨日：winter 9日 → winter 10日」「winter 14日 → winter 15日」）⇒ 这是**收工路径 checks 快照滞后**（已另立 task-6 缺陷 B）。本文件如实记录，不据此改判、也不拿它洗白。
- day 3（winter 9）`unmet` 来自 `stage_shortfall_day`（账本 `:514` `{"unmet":1,"assigned":1,"undone":1,"leftover":1}`）；day 8（winter 14）的 `no_unmet_stages=true` 是两笔豁免扣完的结果（`:1197` `unreachable_summary{count:2,bound:11,exempted:2}` + `:1198` `encircled_summary{count:1}`），但 `day_justified=false` 仍使整天不 VERIFIED。

---

## §3 SMAPI 窗口冻结与六串配对（12/12 PASS）

### 3.1 窗口与副本（时点冻结）

| 项 | 值 |
|---|---|
| 源 | `%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt` |
| 源取证时读数 | **9506 行 / 689226 B / mtime `2026-10-18 17:03:54`**（取证时 17:31 复读一致；此后无游戏进程，源不再增长） |
| 窗口 | `14:50:12`（SMAPI 首行，游戏启动）→ `15:20:39`（Lead 指定上界）；源文件中最后一条 `≤15:20:39` 的行 = **第 9443 行（15:20:38）** |
| 窗口副本 | `logs\runA8-0743-smapi-window.txt` = **676458 B / 9443 行 / SHA256 `614B3E710A59B07D53444D16B731BF6588E2F20C103B5F2BF79B7F9768A3F246`** |
| 副本一致性 | 写后复读：副本 9443 行 **逐行 == 源文件前 9443 行 = True**；窗口内唯一 `ERROR` = 第 64 行「Steam achievements won't work because Steam isn't loaded」（非游戏错误）；`Disconnected/ClosedGame` = 0 行 |
| 窗口后（废数据） | 源第 9444–9506 行共 **63 行**：`15:35:20` 起 7 次跨日落盘（after save `starting winter 20…26`），最后一次 `17:03:52–17:03:54` |

### 3.2 六串逐对（行号 = `NewDay / before save / SaveGame.Save() called / Synchronizing 'Save' task / completed / after save`）

L16 真伪判别：插件描述行也含关键词，必须 `[HH:MM:SS` 前缀且不含 ` by AgentFarm `/`| v0.`；本窗口**排除 1 行**（源第 16 行），排除后六串各 **12** 条。

| # | 六串行号（NewDay / before / Save called / Save task / completed / after） | 时刻 | `after save` 目标日 | 配对 |
|---|---|---|---|---|
| 1 | 1290 / 1301 / 1302 / 1303 / 1306 / 1307 | 14:57:56 → 14:57:59 | winter 8 Y1 | **PASS** |
| 2 | 2366 / 2369 / 2370 / 2371 / 2374 / 2375 | 15:02:11 → 15:02:13 | winter 9 Y1 | **PASS** |
| 3 | 3611 / 3614 / 3615 / 3616 / 3619 / 3620 | 15:04:37 → 15:04:39 | winter 10 Y1 | **PASS** |
| 4 | 4059 / 4062 / 4063 / 4064 / 4067 / 4068 | 15:06:32 → 15:06:34 | winter 11 Y1 | **PASS** |
| 5 | 4495 / 4498 / 4499 / 4500 / 4503 / 4504 | 15:07:55 → 15:07:57 | winter 12 Y1 | **PASS** |
| 6 | 4939 / 4942 / 4943 / 4944 / 4947 / 4948 | 15:09:17 → 15:09:19 | winter 13 Y1 | **PASS** |
| 7 | 5378 / 5389 / 5390 / 5391 / 5394 / 5395 | 15:10:52 → 15:10:54 | winter 14 Y1 | **PASS** |
| 8 | 7573 / 7576 / 7577 / 7578 / 7581 / 7582 | 15:14:34 → 15:14:36 | winter 15 Y1 | **PASS** |
| 9 | 8016 / 8019 / 8020 / 8021 / 8024 / 8025 | 15:15:53 → 15:15:56 | winter 16 Y1 | **PASS** |
| 10 | 8454 / 8457 / 8458 / 8459 / 8462 / 8463 | 15:17:10 → 15:17:12 | winter 17 Y1 | **PASS** |
| 11 | 8934 / 8937 / 8938 / 8939 / 8942 / 8943 | 15:18:53 → 15:18:55 | winter 18 Y1 | **PASS** |
| 12 | 9431 / 9434 / 9435 / 9436 / 9439 / 9440 | 15:20:35 → 15:20:38 | winter 19 Y1 | **PASS** |

**配对结论**：

- 窗口内六串计数 = `newday 12 / before_save 12 / save_called 12 / save_task 12 / completed 12 / after_save 12` ⇒ **12/12 全配对（PASS）**，**不存在「NewDay 无 save」**；每对内部 6 行严格有序、时刻单调。
- 12 对与 12 个 `day_end` 的跨日一一对应（winter 7→8 … winter 18→19），且与 §1.4 起点备份的时间线衔接（起点 winter 7 = SMAPI `:87` 读档）。
- 当班实时记录的跨 #1–#3 见 `logs\runA8-0743-sixchain-progress.jsonl:1-3`（14:58:40 / 15:03:09 / 15:05:34，3/3 PASS，行号 1290/2366/3611 与本表一致）；**其余 9 对由本文件按 SMAPI 原文逐对补**（SMAPI 是脑停后仍在写的源文件，但 15:20:38 之前的窗口内容不再变化；本文件以冻结副本计数、SHA256 为锚）。

### 3.3 **必须排除：15:20:39 之后的无人值守跨日**

- 窗口后 63 行（源 `9444–9506`）是 **脑进程 15:20:38 收尾之后**、无人操作的游戏自行跨日：`15:35:20 / 15:50:05 / 16:04:51 / 16:19:36 / 16:34:21 / 16:49:07 / 17:03:52`，7 次落盘、`after save` 依次为 `starting winter 20 / 21 / 22 / 23 / 24 / 25 / 26 Y1`。
- 这 7 对六串**自身配对齐全**，但**没有 journal、没有脑、没有独立观测** ⇒ **全部列废数据**，不计入本跑六串、不进 §2/§4/§6 任何结论；**「17:03 之后（含 17:03:52–17:03:54 末次落盘）的无人值守跨日不属于本窗口、必须排除」**。

---

## §4 存档四件：起点可核，终点【无法判定】

### 4.1 起点 = `logs\ab-backup\A8-start\MANIFEST.json` 原文（逐字）

```json
{
  "Wahaha_450799035": {
    "size": 3134243,
    "sha256": "E38D0771EFAB1D0D387E5B8BEA49656FC0D35E49A5341D6A04A17CAAC55B0E22",
    "mtime": 1792307308.4710822
  },
  "SaveGameInfo": {
    "size": 31566,
    "sha256": "0735FF7DB77A5575153A15B6477A613DE250D858395A3676E008D0EC063D9777",
    "mtime": 1792307308.4743526
  },
  "Wahaha_450799035_old": {
    "size": 3172619,
    "sha256": "DB0880884FD9BE47E855C340C7CE057B92809626D8DE8BDFC3099BDB4A3417BB",
    "mtime": 1792307198.941477
  },
  "SaveGameInfo_old": {
    "size": 31317,
    "sha256": "B6E4B75B3BBD789B565038253B6A36C8B94FC3C546B9882FE3922F05FF26BE1C",
    "mtime": 1792307199.0395067
  }
}
```

现盘复算 4/4 MATCH（size + SHA256，见 §1.4）；本地 mtime 依次 14:08:28 / 14:08:28 / 14:06:38 / 14:06:39。

### 4.2 终点 = **【无法判定：脑停后无人值守又落盘 7 次，A8 收尾时主档已被覆盖】**

- 推理链（SMAPI 原文）：
  1. A8 第 12 次落盘发生在 `15:20:35–15:20:38`，`after save` 写 `starting winter 19 Y1`（源 `:9431`、`:9440`）。
  2. 之后无人看护的游戏又落盘 **7 次**：`15:35:20`、`15:50:05`、`16:04:51`、`16:19:36`、`16:34:21`、`16:49:07`、`17:03:52`（源 `:9444–9506`），逐次把主档写成 winter 20→26。
  3. 存档目录只保留两代（主档 + `_old`）：现盘主档 mtime = `17:03:52`、`_old` = `16:49:07`，**A8 收尾那一代（15:20:38，winter 19 起点）早已被挤出两代窗口**。
- ⇒ **A8 收尾时的主档四件不可恢复、不可复核**；本文件**不拿当前档冒充 A8 终点**。

### 4.3 现盘四件（只作「现在盘上是什么」的如实记录，**不是 A8 终点**）

| 文件 | size | mtime | SHA256 | 状态 |
|---|---|---|---|---|
| `Wahaha_450799035` | 3141826 | 2026-10-18 17:03:52 | `053CAA71007CEA6FB20D865154DACA236C4FC69F314774B9AC118FB5188F4AF7` | 无人值守 winter 26 起点的落盘 |
| `SaveGameInfo` | 32305 | 2026-10-18 17:03:52 | `3D964F3F30AF39C3F33CCCD210C7CC76760B569349A16F12AFC91BB8144B9293` | 同上 |
| `Wahaha_450799035_old` | 3121459 | 2026-10-18 16:49:07 | `E5B60E915BA393E87FD053A05DFE87FDFAF0F838F8C724F4E50D5B026964B19E` | 无人值守 winter 25→26 的上一代 |
| `SaveGameInfo_old` | 32472 | 2026-10-18 16:49:07 | `9DD16B9462C3A213CE9A924D9CF4A34DC8F61406908D877F5919D49812E69525` | 同上 |

**结论**：A8 的外部存档证据链**只能给起点（可逐字节复核），给不出终点** ⇒ 连同 §0 的缺陷支配，A8 不能作 A″ 验收证据；同时**起点备份仍可作 A9/B9 之前的历史对照锚点**。

---

## §5 缺陷归因（5 个失败日 = 两条系统性死循环，全部给账本行号）

### 5-A `work_spot_resume`「连续 5 次拿不出目标」即把整天判 stuck（winter 7 / 12 / 18）

| 日 | 当天已做成 | 触发链（账本行号） | 收工原文（账本行号） |
|---|---|---|---|
| winter 7 | 46 步（`day_end` `:139`） | `:115` `resume_walk{attempt:2,zone:field_sw,tiles:25}` → `:126` attempt3 → `:128` attempt4 → `:130` attempt5 → `:132` attempt6（同一秒内连发，每次 `walked:true` 但拿不出目标）→ `:134` `no_progress_burst{count:5, source:"回片区（work_spot_resume）", tiles:25, reasons:["今天早些时候还有 149 格没做完（跨片地，最近的是 [41, 18]）"]}` | `:139` `ended_reason="stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标（守卫仍说还有活：今天早些时候还有 149 格没做完（跨片地，最近的是 [41, 18]））"`，`verified=false`、`day_justified=false`，且 `unreachable_within_bound=false`（17 个不可达 > bound 15，`:137` 原文） |
| winter 12 | 13 步（`:581`） | `:567` `work_spot` → `:568/570/572/574` `resume_walk{attempt:1..4,tiles:25}`（t=876.66→877.00，全部 1 秒内）→ `:576` `no_progress_burst{count:5, source:"回片区（work_spot_resume）", reasons:["今天早些时候还有 216 格没做完（跨片地，最近的是 [51, 33]）"]}` | `:581` `ended_reason="stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标…[51, 33]）"`，`verified=false`、`day_justified=false` |
| winter 18 | 19 步（`:1320`） | `:1305` `work_spot` → `:1306` `resume_reevaluate{where:"work_spot_resume"}` → `:1307/1309/1311/1313` `resume_walk{attempt:1..4}`（t=1558.15→1558.44，同秒）→ `:1315` `no_progress_burst{count:5, source:"回片区（work_spot_resume）", reasons:["今天早些时候还有 177 格没做完（跨片地，最近的是 [64, 37]）"]}` | `:1320` `ended_reason="stuck:回片区（work_spot_resume） 连续 5 次都拿不出目标…[64, 37]）"`，`verified=false`、`day_justified=false`；`:1321` 随即 `day_cap` 收尾 |

**共性（证据只到这里，根因判定归 task-4）**：三天都在「当天仍做成 46/13/19 步、守卫仍点名还有 149/216/177 格跨片待做」的情况下，回片区 5 次拿不出目标就写 `stuck:` 收工；`no_progress_burst` 的 `source` 原文就是 `回片区（work_spot_resume）`。⇒ 收尾回路把「回原片区拿不出目标」误判成「全天没活」。代码线索见 task-4 卡面（`brain/agentfarm/longrun.py:3705 _resume_plot`、`:4564 _resume_reevaluate`、`:4650-4671` 收尾回片区循环、`:7767`、`:7927`），**本文件不判定代码根因**。

### 5-B encircled / unreachable 的「1 格余量」当天被反复重分（winter 9 / 14）

| 日 | 余格（坐标） | 重复分配证据（账本行号） | 判定证据 |
|---|---|---|---|
| winter 9 | **encircled `[37,35]`**（四邻 `kind=['tree','tree','tree','tree']`，`tried_open=0`，`:271` 原文）；unreachable `[40,30]` `:505`、`[41,31]` `:507`、`[40,31]` `:509`（zone `field_sw`） | `stage_stop_named{cause:"incomplete", assigned:1, assigned_undone:1, tiles:[[37,35]]}` **28 条**，行号 **272–500**（第一条 `:272` 是 `assigned:2/assigned_undone:1`，其余 27 条 `assigned:1`）；每轮后接 `stage_shortfall{stopped:"incomplete"}`（如 `:273`、`:493`、`:501`）；共 34 个 `clear_area` 阶段 | `:513` `stuck_flush{count:1}` → `:514` `stage_shortfall_day{unmet:1,stages:[{assigned:1,undone:1,leftover:1}]}` → `:515` `unreachable_summary{count:3,bound:5,attempted:51,bound_basis:23}` → `:516` `encircled_summary{count:1,tiles:[[37,35]]}` → `:518` `day_end{ended_by:"stuck", verified:false}` |
| winter 14 | **encircled `[37,35]`**（`:668`，同四邻 tree×4）；unreachable `[40,32]` `:667`、`[39,32]` `:669`（zone `field_nw`） | 同形态 `stage_stop_named{cause:"incomplete", assigned:1, assigned_undone:1, tiles:[[37,35]]}` **62 条**，行号 **680–1188**（最后一条 `:1188`；`:1190` 是最后一次 `encircled_stage`）；当天 `day_end.stages` 共 75（clear_area 73 + till_area/plant_area 各 1），其中 62 个 clear_area 阶段为 `assigned=1/undone=1/stopped=incomplete` | `:1194` `sleep{ok:true}` → `:1195` `stuck_flush{count:2, detail:"stuck:连续 3 轮世界没有任何变化…[37, 35]）"}` → `:1196` `stage_shortfall_day` → `:1197` `unreachable_summary{count:2,bound:11,exempted:2}` → `:1198` `encircled_summary{count:1}` → `:1200` `day_end{ended_by:"stuck", verified:false, day_justified:false}` |

**共性（证据只到这里，根因判定归 task-5）**：同一格（`[37,35]` encircled；`[40,30]/[40,31]/[41,31]` 与 `[39,32]/[40,32]` unreachable）在当天被**反复重分**为新的 `clear_area` 阶段，每轮都 `assigned=1 / assigned_undone=1 / stopped=incomplete`，`stage_shortfall` 连发，直到 `stuck:连续 3 轮世界没有任何变化`。日级后果：winter 9 `no_unmet_stages=false`；winter 14 因两笔豁免扣完 `no_unmet_stages=true`，但 `day_justified=false` 仍使整天不 VERIFIED。代码线索见 task-5 卡面（`longrun.py:4714-4731` 的 `encircled_day`、`:6104-6188` 阶段收尾分类、`:6714` `plot_pending`），**本文件不判定代码根因**。

### 5-C 量化汇总（本跑账本事件计数，`verify-run3` 原文）

`stage_stop_named 95 / stage_shortfall 95 / encircled 91 / encircled_stage 91 / resume_walk 14 / work_spot 14 / no_progress_burst 3 / stuck_flush 2 / frontier_clear 31 / unreachable 25`；教训库 `logs\longrun-runA8-0743-lessons.json`：`stuck_with_leftover` **97** 次、`encircled` **91** 次、`unreachable` **5** 次（`count` 字段原文）。

### 5-D 归因结论

**5 个失败日 100% 落在 A/B 两条**（winter 7/12/18 = A；winter 9/14 = B）⇒ 按 A′ 先例判 **A8 = 臂被缺陷支配、不作 A″ 验收证据**。这两条已分别在 0.7.44 卡 1（task-4）/ 卡 2（task-5）修复中立案；`stuck` 路径 `checks.slept_by_us` 快照滞后另立卡 3（task-6）。

---

## §6 与目标 2 的关系：最佳连续 3，未达 5

**判据（已有口径，不新立）**：A″/B″ 的目标 2 = **任一跑尾部连续 5 天 `verified=true`**，且每日 ≥2 份独立观测、落盘六串 ≥5/5、L0–L2 成立、三检查器同向（`docs\00-开发日志.md` 条目 076 的下一步；`docs\_run6-criteria.md` §2 尾部窗口口径；0.7.43 `docs\_release-0.7.43.md` 的 A″/B″ 放行条件）。

| 读数 | 值 | 证据 |
|---|---|---|
| 逐日 VERIFIED | 7/12（winter 8/10/11/13/15/16/17） | §2 表 |
| **最佳连续 VERIFIED** | **3 天**（winter 15–17） | `logs\longrun-runA8-0743.jsonl:1201-1285` 三个 `day_end.verified=true` |
| **尾部 5 天窗口**（末 5 个 `day_end` = winter 14–18） | 逐日 = **F / V / V / V / F** | `:1200`（F）、`:1225`（V）、`:1250`（V）、`:1285`（V）、`:1320`（F） |
| 尾部窗口内 VERIFIED 计数 | **3/5** | 同上 |
| 尾部连续（`verify-run3 --days 5` 口径，末日往前） | **0/5**；原文「尾部连续 VERIFIED 天数 0 / 要求 5」，工具 rc=1 | `PYTHONUTF8=1 python tools\verify-run3.py --journal logs\longrun-runA8-0743.jsonl --days 5`（§8.2） |
| finish 的 `verified_streak` | **0**；`finish.code=1`、`no_unmet_stages=false` | 账本 `:1322` |
| 目标 2 判定 | **未达**（最佳 3 连、尾部末天失败） | 上述 |

**对旧会话简写「尾部 5 天=1」的核对（如实并列，不硬凑）**：本文件按账本逐日复算**得不到「1」这个数**。可复核的两个读数是：**尾部窗口内 VERIFIED = 3/5**；**尾部连续 = 0/5**（末天 winter 18 失败把连续清零）。「最佳 3 连（winter 15–17）之后只剩 **1 天**（winter 18）就失败」可以解释该简写，但**不能改变「未达 5 天」的结论**。⇒ §6 结论按逐日账本 + 工具原文写，不按简写写。

**L0–L5 不判**：L0/L1 = 同构建、同起点的一对臂（A″/B″）的对照前提；B8 未起跑、A8 又被缺陷支配 ⇒ **对照前提不成立，L0–L5 一律不判**。A8 与 A9/B9 **不同起点**（winter 7 vs winter 26）⇒ 也不可跨对比较（§1.5）。

**其它目标 2 前置项的本跑读数（不足即写不足）**：

| 前置项 | 本跑读数 | 判定 |
|---|---|---|
| 尾部连续 5 天 VERIFIED | 最佳 3；尾部窗口 3/5；尾部连续 0/5 | ❌ |
| 每日 ≥2 份独立观测 | 只有 4 份快照：winter 7（`scratch\runA8-observewinter7.json` 14:57:34）、winter 8（14:58:41）、winter 9（15:03:10）、winter 10（15:05:34）；winter 11–18 **0 份** ⇒ 全跑无一天 ≥2 份 | ❌（且尾段无观测） |
| 落盘六串 ≥5/5 | 窗口内 **12/12** PASS（§3） | ✅（仅此一项成立） |
| 三检查器同向 | `verify-run3 --days 5` = 尾部 0/5；当班 analyzer 读数 rc=1/红 35 | ❌（同向判不达标） |

---

## §7 已知限制 / 缺失清单（缺失 ≠ 通过）

1. **尾段（winter 11–18）无独立观测快照**：当班只留下 winter 7/8/9/10 各 1 份 `scratch\runA8-observe*.json`；15:08 会话死亡后至 15:20:38 收尾期间**没有任何 `observe?detail=full` 快照** ⇒ §2 尾段只有账本 + SMAPI，两源独立但**不是世界差分**；「每日 ≥2 份独立观测」全跑不满足。
2. **A8 终态存档四件【无法判定】**（§4）：脑停后无人值守又落盘 7 次，主档两代窗口已覆盖 A8 收尾那一代；不拿当前档冒充。
3. **`event_wait` / `event_blocked` 各 0 条**：`logs\longrun-runA8-0743.jsonl` 内 grep 无匹配 ⇒ 0.7.43「事件无对话盒有界等待」在 A8 **未被真机触发**，A8 对该路径**不能给任何证据**（`bridge_down` / `watchdog_stop` / `modal_timeout` / `no_day_progress` 同样 0 条，`verify-run3` 事件表原文）。
4. **15:20:39 之后的 7 次跨日全部列废数据**（15:35:20→17:03:54，`starting winter 20…26`）：无脑、无 journal、无独立观测；不进 §2/§3/§4/§6 任何结论（Lead 裁定，`docs\00-开发日志.md` 条目 084/085）。
5. **零硬失败 ≠ 通过**：12 天 `skipped_steps=0`、`failed_steps=0`，失败全部来自收工回路（§5）；本文件不拿「零硬失败」反推任何通过项。
6. **六串时间线说明**：当班实时只记录了前 3 对（`logs\runA8-0743-sixchain-progress.jsonl`），后 9 对由本文件用 SMAPI 原文补；SMAPI 是脑停后仍被无人游戏写入的源文件，本文件以**冻结副本**（9443 行 / SHA256 `614B3E71…A3F246`）计数，源文件 15:20:39 后的增长不参与任何计数。
7. **冬季/无作物 ⇒ 农务三腿结构性缺席**：12 天全 winter、`crops=0`、种子全隔季（`no_seed_for_sale` 12 次、`seed_unavailable_today` 12 次）；`verify-run3` 原文「三腿覆盖：播种 全程 0 步成功」「浇水 全程 0 步成功」⇒ 本跑**无法评农务能力**，只能看清障/收工/落盘；这本身也是 0.7.43 冬季证据面的已知限制（0.7.43 §4），A9/B9 改新起点 winter 26 正是为此。
8. **`checks` 快照滞后（task-6 现场）**：winter 9/14 `ended_by=stuck` + `checks.slept_by_us=false`，但账本随后确有 `sleep{ok:true}` 且 `day_after` +1（§2 要点）⇒ 本文件只如实记录，不据此改判、也不拿它洗白。
9. **`finish.code=1`**：`code=1` 表示「未以 VERIFIED 收尾」，与 §6 不达标一致；不是崩溃（`finish` 正常写入、`cleanup_modal_stuck=false`、`cleanup_attempts=0`）。
10. **A8 与 A9/B9 不可跨对比较**（§1.5）。

---

## §8 复跑与自检读数

### 8.1 证据生成器（只读源 + 只写 `logs/` 三份派生物）

```
$env:PYTHONUTF8=1
python scratch\_t250_a8_evidence.py --check-files
```

复跑会重写：`logs\runA8-0743-smapi-window.txt`、`logs\runA8-0743-sixchain-final.json`、`logs\runA8-0743-daytable.json`（三份在 `.gitignore` 的 `logs/` 下，**不入库**；窗口副本以 SHA256 为锚）。2026-10-18 17:31 实测读数：

- 窗口副本：676458 B / 9443 行 / SHA256 `614B3E710A59B07D53444D16B731BF6588E2F20C103B5F2BF79B7F9768A3F246`；`副本逐行 == 源前 9443 行 = True`。
- 六串：窗口内 12/12 PASS、`L16 排除 1`；窗口后 7/7 PASS（废数据，§3.3）。
- 五文件现树：5/5 SHA256 + mtime MATCH（§1.1）。
- A8-start 四件：4/4 MATCH（§1.4）。

### 8.2 独立工具读数（原文）

```
$env:PYTHONUTF8=1
python tools\verify-run3.py --journal logs\longrun-runA8-0743.jsonl --days 5
```

- 12 个日行：winter 7 F / 8 V / 9 F / 10 V / 11 V / 12 F / 13 V / 14 F / 15 V / 16 V / 17 V / 18 F；`finish` 同 §0.2。
- 末行原文：**`尾部连续 VERIFIED 天数 0 / 要求 5`**，rc=1（本跑需 `--days 5`；工具自身退出码非 0 表示未达标）。
- 附：`decision 164 条（LLM 调用 12 条 / 其中模型产出 12 条）`；`风险事件：触发 max-days 上限收尾 ×1`。

### 8.3 本卡提交物（按路径 add，禁 amend / 禁 add -A）

- `docs\_runA8-0743-evidence.md`（本文件）
- `scratch\_runA8_baseline.py`、`scratch\_runA8_day.py`、`scratch\_runA8_six.py`、`scratch\_runA8_wait.py`、`scratch\_t247_readA8.py`（当班在制取证脚本，收口提交）
- `scratch\_t250_a8_evidence.py`（本文件 §1/§3/§4 数字的生成器，收口提交）

提交后自检：`git show --stat HEAD`（见提交回执；`git diff --cached --name-only` 只含上述 7 条路径）。

---

## 附：数字溯源速查

| 本文件数字 | 出处 |
|---|---|
| HEAD / pid / started_at / argv / worktree | `logs\longrun-runA8-0743.version.json:2,25-28,29-43` |
| 五文件指纹 | 同文件 `:3-23`（+ §8.1 现树复算） |
| A8-start 四件 | `logs\ab-backup\A8-start\MANIFEST.json:1-22`（+ §8.1 现盘复算） |
| 12 天逐日 / finish / day_cap | `logs\longrun-runA8-0743.jsonl:139,240,518,533,553,581,606,1200,1225,1250,1285,1320,1321,1322` |
| 死循环 A（3 天） | 账本 `:115,126,128,130,132,134,139`（winter 7）、`:567-575,576,581`（winter 12）、`:1305-1315,1320`（winter 18） |
| 死循环 B（2 天） | 账本 `:271-272,505,507,509,512-516,518`（winter 9）、`:667-669,680,1188,1194-1198,1200`（winter 14） |
| 六串 12 对 | SMAPI 源 `:1290,2366,3611,4059,4495,4939,5378,7573,8016,8454,8934,9431` 起；明细 `logs\runA8-0743-sixchain-final.json` |
| 废数据 7 对 | SMAPI 源 `:9444-9506` |
| 现盘存档四件 | `%APPDATA%\StardewValley\Saves\Wahaha_450799035\*`（17:03:52 / 16:49:07） |
| 独立观测快照 | `scratch\runA8-observewinter7.json`、`runA8-observe-winter8.json`、`-winter9.json`、`-winter10.json`（captured_at 14:57:34 / 14:58:41 / 15:03:10 / 15:05:34） |
| 当班实时六串 3 对 | `logs\runA8-0743-sixchain-progress.jsonl:1-3` |
