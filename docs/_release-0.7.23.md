# 0.7.23 冻结与发布计划（Lead 独占执行）

> 为什么要有这份清单：一次装机的内容必须与版本号**一一对应**（v0.7.17 的教训：版本号相同、内容不同 ⇒
> 桥的 `modVersion` 断言与全部验收口径失真）。所以 bump、装机、部署**只由 Lead 在整链冻结后一次做完**，
> teammate 只改代码、不碰 `manifest.json` 与 `brain/agentfarm/bridge.py:MOD_VERSION_EXPECTED`。

## 1. 冻结判据（四条全绿才允许动 manifest）

| # | 判据 | 命令 / 证据 |
|---|------|-------------|
| 1 | 链条上已无人在改 Mod/brain 源码 | `git status --short` 只剩 Lead 自己的 docs/scratch（teammate 全部报完工） |
| 2 | Mod 全量重建 0 警 0 错 | `cd mod\AgentFarm.Bridge; dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` |
| 3 | 全量单测 OK | `python -m unittest discover -s tests`（起跑基线 **301**，0.7.23 落地后只增不减） |
| 4 | deputy-lead 完整验收 PASS | `docs\_review-task33.md`（+ task-32/task-34 若有）逐条打勾 + 越界检查 |

## 2. 装机内容（0.7.23 = task-33 为主；以 dev-coder 报完工的文件清单为准）

**Mod（`mod\AgentFarm.Bridge\`）**
- `SleepSkill.cs` — **睡眠跨日真机定案（条目 036）**：提问开着时选肯定项应答 → **同一 tick 走游戏自己的关框路径**（`closeDialogue()`，仍在才 `exitThisMenu()`）→ 等 `Game1.Date.TotalDays` 前进且 `newDay` 归 false 才回 ok；**无提问立即 `sleep_no_question`**（附 `isInBed`/`lastQuestionKey`/`activeClickableMenu`/`gameMode`），**绝不再等 180s**。
- `Contracts.cs` + `WorldSnapshot.cs` — `FurnitureView` 为 `isBed` 家具暴露**触发格 `bedCells`**（`[[x, y+1], [x+1, y+1]]`，或等价 `bedTileOffset`）；脑侧不再靠押格。
- `MoveToLocationSkill.cs`（+ `StepMover.cs`/`LocationGraph.cs` 若需要）— **门格不许当 A* 目标**：warp 的 `Edge.Source` 是触发区锚点（`LocationGraph.cs:48` 注释自己写明"不等于可站人的格子"），先试 `(source.X, source.Y±1)/(source.X±1, source.Y)` 的可站立格再 `checkAction(门格)`（已验证旧 recipe：站 `(64,15)` → `checkAction((64,14))`）；报错文案写清"试过哪些格、为什么不行"。
- `manifest.json` — Version → `0.7.23`（其余不改）。

**brain（`brain\agentfarm\`）**
- `bridge.py` — `MOD_VERSION_EXPECTED = "0.7.23"`（唯一版本断言）；`sleep()` docstring 同步新口径。
- `farmwork.py` — `sleep()` 新配方：`stand_next_to(床)` → **先走离床格一步**（满足 `Farmer.hasMoved`）→ 踩触发格（接受 `ui_modal` 回执）→ 仅当 `ui.dialogueIsQuestion` 为真才 `client.sleep()`；判据 = `clock.day` 变了；床边无提问 ⇒ 立刻 `sleep_no_question`。
- `longrun.py` — task-32：`no_plot` **不得**判 `day_justified`；`max_plots_per_day` 触顶后**在区内继续干活**（journal `plots_capped`）；task-34：逐格 `tile_step` 证据（若落地）。

**明确不并入 0.7.23**：task-14（逐帧 warp 循环修复，`docs\_il-warp-loop.md` 已给方向）、task-17（`world_stuck` 自愈）、task-18（职业选择自动化）、task-20（工具等级可观测）、task-24（卖东西换钱）、task-30 之后的分析类。

## 3. 发布步骤（按顺序，任一步失败就停下回报，不许"跳步装机"）

```powershell
cd "D:\Deepseek Harness Workspace\星露谷游戏自动化"
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
```

1. **写说明文件**（UTF-8）`tools\_note-0723.txt`，首行必须是 `v0.7.23`。
2. **bump**：`& $py tools\_bump-mod-version.py 0.7.23 --note-file tools\_note-0723.txt`
3. **同步 brain**：编辑 `brain\agentfarm\bridge.py` 的 `MOD_VERSION_EXPECTED` → `"0.7.23"`（用编辑工具，不用 PowerShell 读写）。
4. **全量重建**：`cd mod\AgentFarm.Bridge; dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental`（0 警 0 错）。
5. **发布前自检**：`& $py tools\check-release.py --expect 0.7.23`。
6. **提交**：`git commit -m "release: Mod 0.7.23（task-33 睡眠跨日 + 门格）"`——**先提交再装机**。
7. **装机**：`& $py tools\deploy-mod.py`（优雅 `quit_game` → 装 dll+manifest，旧文件留 `.bak-<ts>` → 启动 → 轮询 health → `load_save`）。日志 `logs\deploy-0.7.23.log`。
8. **起跑前四查**：`& $py tools\preflight.py --expect 0.7.23`（`hasSaveLoaded` / `location.isOutdoorFarm` / `ui.isModal` / `MOD_VERSION_EXPECTED==装机版本`）。
9. **脑侧睡眠真机复验（新增，0.7.23 特有）**：`& $py scratch\verify-sleep-brain.py`（走 `FarmWorker.sleep()` 的真实路径，判据 = `day` +1 **且** 存档 size/mtime 前进；连续 2 次）。
10. **1 游戏日彩排**：`& $py tools\run-longrun.py --days 1 --size 5 --max-minutes 30 --journal logs\longrun-rehearsal-0.7.23.jsonl`（**不判达标**，只验：睡过去（`ended_by=sleep`）、跨日外部证据、`decision.llm=true` 有真 LLM 决策）。
11. **真 3 日 run3**（machine-runner，task-12）：`& $py tools\run-longrun.py --days 3 --size 5 --max-minutes 150 --journal logs\longrun-3day-llm-run3.jsonl`
12. **双重复核**（Lead + log-analyst 各一次）：`& $py tools\verify-run3.py --journal logs\longrun-3day-llm-run3.jsonl --days 3` + `& $py tools\analyze-longrun.py --journal logs\longrun-3day-llm-run3.jsonl`
13. **跑完立刻退出**（用户 m02833）：`& $py tools\stop-game.py`。

## 3b. 验收不许只看账本（外部证据硬要求，沿用 0.7.22 §3b）

`verify-run3.py` / `analyze-longrun.py` 都是**账本检查器，不是世界校验器**（deputy-lead 的负例 K/K2 已证）。run3 结论必须同时附：

- 存档 `%APPDATA%\StardewValley\Saves\Wahaha_450799035\{Wahaha_450799035,SaveGameInfo}` 的 **size/mtime 每个跨日前进一次**；
- `Game1.Date.TotalDays`（`clock.year/season/day`）真变化且与 journal `day_end` 对齐（**恰好 +1 天**）；
- SMAPI 日志窗口内 `Synchronizing 'NewDay' task...` 与 `SaveGame.Save` 行数 = 跨日次数；
- `day_end.final` 与 quit 前 live `/observe` 对账（`unwatered_crops==0`、`farm.dryCrops==0`）。

## 4. 回退

- Mod：`mod\AgentFarm.Bridge\*.bak-<ts>` 与版本号可回溯；失误就 `git revert` 后重新 bump 一个**新版本号**（不覆盖旧版本号）。
- 存档：`tools\deploy-mod.py` 每次装机前都备份（`%APPDATA%\StardewValley\Saves\_agentfarm-backup-*`）；run3 期间**不许重启续跑**，失败另起 run4。
