# 0.7.25 发布计划（run6 前置）

> 目的：把 run5 暴露的三类"看得见/判得对"缺陷修掉，并给 LLM 决策加留痕，然后跑 **run6**（连续 3 个游戏日无人介入）。
> 本文件归 Lead 维护；各卡只改代码，**bump/装机/起跑口径以本文件为准**。

## 1 版本内容（冻结时以实际提交为准）

| 卡 | 内容 | 侧 |
|---|---|---|
| task-50 | Mod 暴露 `farm.dryTiles`（干作物格坐标，上限 64、按 y,x 排序、`dryTilesTruncated`）+ 脑侧"窗口外干格 ⇒ 走过去浇，浇不上就 `stuck:`，绝不许 `no_work`" | Mod + brain |
| task-51 | Mod 暴露 `farm.deadCrops` + 脑侧清死苗（`use_tool` 镰刀，判据=该格 crop 消失且 kind 仍 dirt；**活苗绝不碰**） | Mod + brain |
| task-52 | "四邻都站不过去/A* 无路" ⇒ 新分类 `unreachable`：不算 `failed_steps`、不算 `no_unmet_stages`（同 `max(5, floor(0.2×attempted))` 有界），但必须逐格进 journal；超界或 0 成功仍不 `verified` | brain |
| task-56 | 每次**真实** LLM 调用落一行 trace（`<journal>-llm.jsonl`：prompt/raw/usage/finish_reason/duration_ms/accepted/rejected），journal `decision` 行只新增 `llm_trace`/`llm_trace_hash`；写盘失败不影响决策 | brain |
| task-63 | `till` 的 `tool_ineffective`（游戏拒绝该工具动这格）**不再算硬失败** ⇒ `skipped`+`proven_inert`（逐格 journal `tool_refused`）；**Mod 回执 `ok` 但格子没变仍记 `failed`**；日级有界豁免 `refused_bound = max(5, floor(0.2×attempted))`，超界照实 `no_hard_failures=false` | brain |

不进本版：task-14（逐帧 warp 活锁）、task-17（world_stuck 自愈）、task-18（职业自动选）、task-20（工具等级主动探测）、task-53（农场级待清障/待开垦格数）、task-55（卖余料换种子钱）、task-58/59（B/C 件：把上次决策喂回模型 / 收工复盘）。

## 2 冻结与装机（Lead 独占，链条冻结后一次做完）

1. 确认 `task-50/51/52/56/63` 全部 completed、工作树干净、`git log -1` 记录 HEAD。
2. `tools\_note-0725.txt` **已预写**（四张卡一句话）；冻结前对照最终交付复核一遍，哪张卡没进本版就改这一句。⚠️ **文件必须以 `v0.7.25` 开头** —— 否则 `_bump-mod-version.py` 只打印一行"说明文件应以 v0.7.25 开头"的告警并**原样保留旧 Version**（本轮已在临时副本上实测，见 STEP 3 的预演）。
3. `python tools\_bump-mod-version.py 0.7.25 --note-file tools\_note-0725.txt`
4. 改 `brain\agentfarm\bridge.py` 的 `MOD_VERSION_EXPECTED = "0.7.25"`（注释列本版内容）。
5. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警 0 错**。
6. 提交（manifest + bridge.py + 装机前所有在制文件）。⚠️ **必须 `git add -A`**：`scratch/*.py` 被 `.gitignore` 特别保留（`!scratch/*.py`），新写的探针脚本算"未跟踪 ⇒ 工作树脏"，会让 STEP 7 判红（本轮实测：`check-release.py --expect 9.9.9` 同时报出版本不符与 7 项未提交，两条红线都真的会响）。
7. `python tools\check-release.py --expect 0.7.25` ⇒ **全绿**（manifest==brain、dll 不比源码旧、py_compile、全量单测、树干净）。
8. `python tools\deploy-mod.py --no-quit` ⇒ 记录 dll/manifest 字节数与桥 `modVersion=0.7.25`。
9. `python tools\preflight.py --expect 0.7.25 --save-baseline logs\run6-baseline.json` ⇒ 四项全绿（版本/已读档/户外农场/无模态）。

### 2.1 执行记录（2026-10-14，Lead 实做）

- STEP 3 实测踩到一个**新坑**：`_bump-mod-version.py` 在 cp1252 控制台（未设 `PYTHONUTF8`）里**版本已写盘、最后一句 `print` 却抛 `UnicodeEncodeError`**（字符 `；`）⇒ 退出码 1 但 manifest 已改。已给 `tools\_bump-mod-version.py` 与 `tools\check-release.py` 补**自配 UTF-8 stdout**（与 `preflight.py`/`run-longrun.py` 同口径，提交见 §2 STEP 6 那笔）。核对 manifest 时**别只看退出码，要 `json.load` 读 Version**。
- STEP 3–8 结果：manifest `0.7.24 → 0.7.25`（note 列出 task-50/51/52/63/56）；`bridge.py:39 = "0.7.25"`；build **0 警 0 错**；提交 **`e381e58`**（冻结点）+ **`31cb3cd`**（预置脚本/工具 UTF-8）；`check-release --expect 0.7.25` **六项全绿**（`Ran 455 tests` OK、树干净）；`deploy-mod --no-quit` ⇒ dll **170496 B** / manifest **18426 B**、桥 `modVersion=0.7.25 port=17890`、`load_save ok` 进 `Wahaha_450799035`（FarmHouse (9,9)）。
- STEP 9 结果：`goto Farm`（Farm (64,15)）后 preflight **四项全绿**，基线写 `logs\run6-baseline.json`；关键值 `day [1,summer,4] tod 630`、money **956**、`seeds []`、`crops 35`、**`deadCrops 33`**（task-51 新字段真机可见）、`dryCrops 0`（天气 `lightning`）、`waterLeft 23`、`tillableCount 146`。

## 3 run6 起跑（machine-runner，task-57）

**首选：用 Lead 的脱离式起跑器**（把"版本四要素 + 独立进程 + PID 文件 + 90 秒体检"一次做完；`DETACHED_PROCESS` 起，父进程/agent 回合结束不会连带收掉它）：

```powershell
python tools\start-detached-longrun.py --journal logs\longrun-3day-llm-run6.jsonl --expect-version 0.7.25
```

- 它做的事：①PID 还活着就拒绝重复起跑（退 3）②`--expect-version` 时先跑 `preflight`，红灯就不起跑（退 4）③起 `tools\run-longrun.py`，stdout/stderr 落 `logs\longrun-3day-llm-run6.console{,.err}.log` ④写 `logs\longrun-3day-llm-run6.pid` 与 `…version.json`（HEAD / 被测文件 SHA256+mtime = `longrun.py`+`farmwork.py`+`bridge.py`+**Mod dll**+**manifest.json** / PID+起跑时刻 / `git status --short`）⑤体检 90 秒后打印 console 尾部与账本行数**然后返回**（进程继续跑）。
- 先跑一次 `--dry-run` 看四要素（不起进程），再真起跑；冒烟实测（`4aa2369` 后）：`--dry-run` 打出 HEAD `727a767…` + 五个文件 SHA256/mtime + `工作树干净 = False（11 项未提交）`；真起跑冒烟曾以独立进程 PID 26956 + sidecar + console 尾部 `[bridge_file_missing]` 快速失败验证链路。
- 子进程环境由起跑器写死 `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` / `PYTHONPATH=<repo>\brain` ⇒ 在哪个 shell 调用都不影响长跑的 import 与中文编码；起跑器自身也把 stdout/stderr 重配成 UTF-8（cp1252 的 Python 会 `UnicodeEncodeError`）。
- 它**不**判达标、不关框、不替游戏做选择、不杀进程；跑完仍在跑时**先别退游戏**（Lead 要 live observe 对账）。
- 需要手工起时（备用）：

```powershell
Start-Process -FilePath <python.exe> -ArgumentList '-u','tools\run-longrun.py','--days','3','--size','5','--max-minutes','150','--max-days','9','--journal','logs\longrun-3day-llm-run6.jsonl' `
  -PassThru -WindowStyle Hidden -RedirectStandardOutput 'logs\run6-console.log' -RedirectStandardError 'logs\run6-console.err.log'
```

- **不许**用托管后台作业（`run_in_background`）：run4 曾在回合边界被连根收掉，只跑 13 秒（条目 040）。
- 只按 **PID 存活 + console 尾部 + 账本行数** 只读轮询；出现 `finish` 或 PID 消失立刻报 Lead。
- 交付 `docs\_run6-evidence.md`（machine-runner 独占）：逐日表 + 外部证据 + 判据对照 + 与 run5 的对比段。

## 4 判据（以 `docs\_run6-criteria.md` 为准）

- **达标**：尾部连续 **3 个游戏日** `ended_by == "sleep"` 且 `verified == true`，且 `finish.code == 0`。
- 每日七项 checks（`tools\verify-run3.py` 复核）：`no_hard_failures` / `no_unmet_stages` / `watered_outdoor` / `no_blocking_modal` / `crops_watered`（不作证据）/ `day_justified` / 真空日闸门（`verified=true` 但当天成功动作 0 步 ⇒ 判红）。
- **`ended_reason` 以 `no_work` 开头的日子必须 `final_water.dry == 0`**（run3 连睡病复发闸门）。
- **已作废判据：`final.location == "Farm"`**（睡前快照，正常成功的一天就是走回 FarmHouse→上床→睡）。
- 落盘口径按 task-47（`docs\_il-newday-save.md`）：**跨日 ≠ 落盘**；有日终菜单（`displayedShippedItems` 非空 / `endOfNightMenus` 栈非空）时"存档未动"既不判失败也不判通过；**没有**日终菜单却缺 `SaveGame.Save()` = 异常。
- 外部证据三项必须同向：存档 size/mtime、SMAPI `Synchronizing 'NewDay' task` / `SaveGame.Save() called|completed`、`day_after` 逐日 +1。

## 5 与 run5 对比要看什么

`farm.dryCrops` 是否归零（run5 三天恒剩 1）；枯死作物有没有被清（run5 36 株里 24 株死、`deadCrops:null`）；"四邻都站不过去"的日子还判不判 hard failure（run5 summer 1 因 8 格不可达被判 `no_hard_failures=false`）；有没有 `sell` 事件（run5 一次都没有，出货只在验收探针里验证过）；LLM 决策条数 / 截断次数 / trace 是否齐全。

## 6 已知遗留（不阻塞 run6）

- ~~run6 仍缺"播种腿"的种子钱：钱 14g、种子 0~~ ⇒ **本轮已由操作员预置解决**（§7.1：出货 6 叠 + 睡一夜 ⇒ money **956g**，起跑后脑自己 `buy` 种子）；**结构性修复仍是 task-55**（脑侧自己卖余料 + 分叠/记账，避免把家底整叠卖空）。
- task-53（农场级待清障/待开垦格数）未做 ⇒ 观测窗口外仍有"看不见的活"（但不会再被写成 `no_work`）。
- task-14 逐帧 warp 活锁未修 ⇒ 每次 `goto Farm` 仍会刷 `Warping to Farm`，并可能勾出剧情事件（task-41 会硬停等人）。
- Mod 无 C# 测试工程 ⇒ Mod 侧新逻辑靠 build + 真机验收。
- LLM 留痕 `<journal>-llm.jsonl` **只追加、不轮转/不封顶**（task-56，Lead 2026-10-14 裁定）：run6 三天量级可接受，长跑（>10 天）再谈上限；`raw` 原样记录不截断（受 `max_tokens=16384` 天然约束）；`t` 是墙钟 unix 秒，**跨文件关联一律以 `llm_trace_hash` 为键**。

## 7 run6 起跑前的操作员预置（Lead 执行，起跑前完成）

**目的**：让 run6 真的能演示"播种腿"，而不是像 run5 那样因为"钱 14g、种子 0"整跑只剩清障+浇水（任务书 ⑥ 的四个动作 = 清障→开垦→播种→浇水）。

**做法（全部走已真机验收过的路径；不改代码、不动 `mod/`、不手改存档）**：
1. `python tools\preflight.py --expect 0.7.25 --save-baseline logs\run6-baseline.json` —— 同时记录 `money` / `seeds` / `inventory` / `farm` 计数基线。
2. 若 `seeds_total == 0`：用 `scratch\verify-sell-brain.py` 把 run5 清障/开垦攒下的余料（石/木/纤维/黏土/煤等，**每个 id 保留 K=10**；工具/武器/种子/建材一律不卖）送进出货箱 —— 这是那批被清掉的资源变成的钱。判据一律观测差分（槽位空 + 箱件数增加），钱要等跨日才到账。
3. `python scratch\verify-sleep-brain.py`（已 VERIFIED 的"踩触发格"配方）睡一天收款；外部证据三项：`clock.day` +1、存档 size/mtime 前进、`timeOfDay` 回 ≈06:00。
4. 复核 `money ≥ 20g` 且 `seeds_total == 0` ⇒ 起跑后**脑自己**会 `buy` 种子并播种（该路径 run5 实测过：`114→14` 买 5 包 `472`）。
5. 之后 3 个游戏日**全程无人介入**；预置发生在起跑前，不计入"无人介入"。

**红线**：预置只允许用 `sell` / `sleep` / `buy` 三条已验收路径；**绝不** `Money +=`、绝不手改存档、绝不直接塞背包。每一步留 `logs/` 证据，并在 `docs\_run6-evidence.md` 第 0 段如实写明"操作员预置：卖了什么、卖了几个、到账多少"。

### 7.1 执行记录（2026-10-14，Lead 实做）

- 预置脚本 `scratch\run6-preseed.py`（新，可复现；`--dry-run` 先看计划）。走游戏自己的 `Farm.shipItem`，**整叠**出货 6 叠，6/6 观测差分确认（槽位空 + 箱件数 0→6）：
  `(O)535 Geode×1`、`(O)390 Stone×104`、`(O)388 Wood×72`、`(O)771 Fiber×115`、`(O)382 Coal×11`、`(O)330 Clay×13`。
- 收款：`scratch\verify-sleep-brain.py --from-farm` 睡一夜 **summer 3 → summer 4**（tod 840→600），**money 14 → 956g**（次日游戏自己结算；预置出货当天 money 不变，符合设计）。
- ⚠️ **缺口（比 §7 原计划更严）**：Mod `ShipSkill` 出货的是 `Items[slot]` **整叠**，没有"只卖超额部分"的能力 ⇒ **"每 id 保留 K=10"在操作员层也做不到**（这次是整叠卖掉）。这正是 task-55 要在脑侧解决的形态（要么先分叠、要么按 id 记账免得把家底卖空）。
- ⚠️ **task-47 U2 数据点**：本次 summer 3→4 的日终保存**即使关掉 `ShippingMenu` 也没落盘**（存档仍 `3696701 B / 2026-10-13T20:37:37.898`；关框后 `worldAdvancing=true` 但无 `SaveGame.Save()` 行）⇒ 起点存档 mtime 是旧的；按 `docs\_run6-criteria.md` §2 口径（有日终菜单时"存档未动"不判失败也不判通过）处理，但 evidence 里要如实点名。
- 起跑前状态即 §2.1 STEP 9 的基线：`money 956` / `seeds []` ⇒ 起跑后**脑自己**会 `buy` 种子（该路径 run5 实测过：`114→14` 买 5 包 `472`）。

### 7.2 run6 结果（2026-10-14，Lead + machine-runner 取证）——**FAIL（0/3）**

- `finish {"code":1,"verified_streak":0,"target_days":3,"actions":95,"minutes":0.62,"stages_seen":["clear_dead","till_area"],"unmet_days":["1年 summer 4日","1年 summer 4日"]}`；两次日报告同为 `summer 4`（t 18.47 / 37.20），`ended_by=stuck`、`day_after=null`，**0 跨日**；存档 `3696701 B / 20:37:37.898` 未动；SMAPI 起跑后 672 行里 NewDay 0 / `SaveGame.Save()` 0 / ERROR 0；`console.err` 0 B ⇒ **干净快速失败**（不是崩溃/掉线/模态）。
- 死因两条（详见 [docs/_run6-evidence.md](docs/_run6-evidence.md)、条目 047）：
  1. `buy` 品种硬编码 **472（防风草＝春季作物）**，夏季 SeedShop 不卖 ⇒ 一天 6 次 `item_not_sold`；`sleep_guard` 的「没种子但钱够(956g)⇒该去买」使该条件**永不可满足**；
  2. 唯一实体活（清 `field_ne` 枯死作物）**42 格全部「四邻都站不过去」**⇒ `unreachable 42 > bound 8` ⇒ `checks.unreachable_within_bound=false`（新闸门首次真机报警）。
- 去向：**task-67**（按在售清单买当季种子 + `no_seed_for_sale` 当天封 + 守卫理由当天失效）、**task-68**（先清邻格开路 + `unreachable_bound` 口径修正）⇒ 冻结 **0.7.26** 后跑 **run7**（见 [docs/_release-0.7.26.md](docs/_release-0.7.26.md)）。
