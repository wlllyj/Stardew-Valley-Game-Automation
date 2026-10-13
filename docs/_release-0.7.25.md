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

不进本版：task-14（逐帧 warp 活锁）、task-17（world_stuck 自愈）、task-18（职业自动选）、task-20（工具等级）、task-53（农场级待清障/待开垦格数）、task-55（卖余料换种子钱）、task-58/59（B/C 件：把上次决策喂回模型 / 收工复盘）。

## 2 冻结与装机（Lead 独占，链条冻结后一次做完）

1. 确认 `task-50/51/52/56` 全部 completed、工作树干净、`git log -1` 记录 HEAD。
2. `tools\_note-0725.txt` **已预写**（四张卡一句话）；冻结前对照最终交付复核一遍，哪张卡没进本版就改这一句。⚠️ **文件必须以 `v0.7.25` 开头** —— 否则 `_bump-mod-version.py` 只打印一行"说明文件应以 v0.7.25 开头"的告警并**原样保留旧 Version**（本轮已在临时副本上实测，见 STEP 3 的预演）。
3. `python tools\_bump-mod-version.py 0.7.25 --note-file tools\_note-0725.txt`
4. 改 `brain\agentfarm\bridge.py` 的 `MOD_VERSION_EXPECTED = "0.7.25"`（注释列本版内容）。
5. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警 0 错**。
6. 提交（manifest + bridge.py + 装机前所有在制文件）。⚠️ **必须 `git add -A`**：`scratch/*.py` 被 `.gitignore` 特别保留（`!scratch/*.py`），新写的探针脚本算"未跟踪 ⇒ 工作树脏"，会让 STEP 7 判红（本轮实测：`check-release.py --expect 9.9.9` 同时报出版本不符与 7 项未提交，两条红线都真的会响）。
7. `python tools\check-release.py --expect 0.7.25` ⇒ **全绿**（manifest==brain、dll 不比源码旧、py_compile、全量单测、树干净）。
8. `python tools\deploy-mod.py --no-quit` ⇒ 记录 dll/manifest 字节数与桥 `modVersion=0.7.25`。
9. `python tools\preflight.py --expect 0.7.25 --save-baseline logs\run6-baseline.json` ⇒ 四项全绿（版本/已读档/户外农场/无模态）。

## 3 run6 起跑（machine-runner，task-57）

```powershell
Start-Process -FilePath <python.exe> -ArgumentList '-u','tools\run-longrun.py','--days','3','--size','5','--max-minutes','150','--max-days','9','--journal','logs\longrun-3day-llm-run6.jsonl' `
  -PassThru -WindowStyle Hidden -RedirectStandardOutput 'logs\run6-console.log' -RedirectStandardError 'logs\run6-console.err.log'
```

- PID 落 `logs\run6.pid`；**不许**用托管后台作业（run4 曾在回合边界被连根收掉，只跑 13 秒，见条目 040）。
- 起跑前记"版本四要素"（HEAD / 被测文件 SHA256+mtime / PID+StartTime 必须晚于 mtime / `git status --short` 无被测源码 ` M`）。
- 只按 **PID 存活 + console 尾部 + 账本行数** 只读轮询；出现 `finish` 或 PID 消失立刻报 Lead；**跑完先别退游戏**（Lead 要 live observe 对账）。
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

- run6 仍缺"播种腿"的种子钱：钱 14g、种子 0 ⇒ task-55（卖余料换钱）排在本版之后。
- task-53（农场级待清障/待开垦格数）未做 ⇒ 观测窗口外仍有"看不见的活"（但不会再被写成 `no_work`）。
- task-14 逐帧 warp 活锁未修 ⇒ 每次 `goto Farm` 仍会刷 `Warping to Farm`，并可能勾出剧情事件（task-41 会硬停等人）。
- Mod 无 C# 测试工程 ⇒ Mod 侧新逻辑靠 build + 真机验收。
- LLM 留痕 `<journal>-llm.jsonl` **只追加、不轮转/不封顶**（task-56，Lead 2026-10-14 裁定）：run6 三天量级可接受，长跑（>10 天）再谈上限；`raw` 原样记录不截断（受 `max_tokens=16384` 天然约束）；`t` 是墙钟 unix 秒，**跨文件关联一律以 `llm_trace_hash` 为键**。
