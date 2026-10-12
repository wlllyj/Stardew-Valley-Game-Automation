# 0.7.22 冻结与发布计划（Lead 独占执行）

> 为什么要有这份清单：一次装机的内容必须与版本号**一一对应**。v0.7.17 的教训是"版本号相同、内容不同"
> ⇒ 桥的 `modVersion` 断言与验收口径全部失真。所以 bump、装机、部署**只由 Lead 在整链冻结后一次做完**，
> teammate 只改代码、不碰 `manifest.json` 与 `brain/agentfarm/bridge.py:MOD_VERSION_EXPECTED`。

## 1. 冻结判据（四条全绿才允许动 manifest）

| # | 判据 | 命令 / 证据 |
|---|------|-------------|
| 1 | 链条上已无人在改 Mod/brain 源码 | `git status --short` 只剩 Lead 自己的 docs（teammate 全部报完工） |
| 2 | Mod 全量重建 0 警 0 错 | `cd mod\AgentFarm.Bridge; dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` |
| 3 | 全量单测 OK | `python -m unittest discover -s tests`（当前基线 **249**） |
| 4 | deputy-lead 完整验收 PASS | `docs\_review-task7.md`（或新文件）逐条打勾 + 四处口径一致性 + 越界检查 |

## 2. 装机内容（0.7.22 = 以下三批，逐文件）

**Mod（`mod\AgentFarm.Bridge\`）**
- `UseToolSkill.cs` — task-7 收窄版：`Swing()` 只对 `CurrentTool is MeleeWeapon` 走 `BeginUse()`（逐行照抄 `pressUseToolButton` 门闸之后的 IL_083D-08BD：`GetToolLocation`→`FacingDirection`→`lastClick`→`p.BeginUsingTool()`），Hoe/Can/Axe/Pickaxe **原样走 `Game1.pressUseToolButton()`**；`WorldFading()` 渐黑门（`world_fading`，可重试不消耗刀数）；`Done()` 加 `if (tf is Grass) return false;`（+task-22 的 D1 注释归位）。
- `SleepSkill.cs` — task-8：判据=**游戏自己弹出了睡觉提问**（`lastQuestionKey` 前缀 `Sleep`），拼不出前缀立刻 `sleep_no_question` 并附 `isInBed/lastQuestionKey/activeClickableMenu/gameMode`，绝不等满 180s。
- `WorldSnapshot.cs` + `Contracts.cs` — task-23：`farm.dryCrops`（真值来自 `HoeDirt.needsWatering()`，只在 `complete==true` 时可用）；task-11：`ui.professionsToChoose`（`LevelUpMenu` 私有字段反射读）。
- `UiRead.cs` + `ModalDismiss.cs` — task-11：职业弹窗**绝不 dismiss**；`SaveGameMenu` 只等不关。
- `manifest.json` — Version → `0.7.22`（其余文件不改）。

**brain（`brain\agentfarm\`）**
- `bridge.py` — `MOD_VERSION_EXPECTED = "0.7.22"`（唯一一处版本断言）。
- `farmwork.py` / `longrun.py` — task-22 状态三分类与 `env_block`/`inconclusive` 记账、**task-28 的 `busy`→ENV / `stale`→INCONCLUSIVE 与防自旋上限**、task-15 的 `no_unmet_stages` + 条款④、task-19 的 `checks.watered_outdoor` + `day_end.final_water`。
- `__main__.py` — task-26 的 `await_game_exit` 三态。

**明确不并入 0.7.22（留给 0.7.23+）**：task-14（warp 循环根因修复）、task-17（`world_stuck` 自愈）、task-18（职业选择自动化）、task-20（工具等级可观测）、task-24（UI 可见性）。它们都不在 run3 的关键路径上。

## 3. 发布步骤（按顺序，任一步失败就停下回报，不许"跳步装机"）

```powershell
cd "D:\Deepseek Harness Workspace\星露谷游戏自动化"
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
```

1. **写说明文件**（UTF-8）`tools\_note-0722.txt`，首行必须是 `v0.7.22`，列出三批内容一句话摘要。
2. **bump**：`& $py tools\_bump-mod-version.py 0.7.22 --note-file tools\_note-0722.txt`
3. **同步 brain**：编辑 `brain\agentfarm\bridge.py` 的 `MOD_VERSION_EXPECTED` → `"0.7.22"`（用编辑工具，不用 PowerShell 读写）。
4. **全量重建**：`cd mod\AgentFarm.Bridge; dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental`（0 警 0 错）。
5. **发布前自检**：`& $py tools\check-release.py --expect 0.7.22`（四项：版本一致 / dll 不比源码旧 / py_compile / 全量单测 / 工作树干净）。
6. **提交**：`git commit -m "release: Mod 0.7.22（task-7/8/11/23 + 15/19）"`（含 manifest + bridge.py + 说明文件）——**先提交再装机**，装机失败也能从版本号回溯到确切内容。
7. **装机**：`& $py tools\deploy-mod.py`（备份存档 → 优雅 `quit_game` → 装 dll+manifest，旧文件留 `.bak-<ts>` → 启动 → 轮询 health → `load_save`）。日志 `logs\deploy-0.7.22.log`。
8. **起跑前四查**：`& $py tools\preflight.py --expect 0.7.22`（`hasSaveLoaded=true` / `location.isOutdoorFarm=true` / `ui.isModal=false` / `MOD_VERSION_EXPECTED==装机版本`）。
9. **run3**（交给 machine-runner，见 task-12）：
   `& $py tools\run-longrun.py --days 3 --size 5 --max-minutes 150 --journal logs\longrun-3day-llm-run3.jsonl`
10. **双重复核**（Lead + deputy-lead 各跑一次，判据只认观测/账本，不认回执）：
    `& $py tools\verify-run3.py --journal logs\longrun-3day-llm-run3.jsonl --days 3`
    `& $py tools\analyze-longrun.py --journal logs\longrun-3day-llm-run3.jsonl`
11. **跑完立刻退出**（用户 m02833）：`& $py tools\stop-game.py`（或 `python -m agentfarm shutdown --force-after 30`）。

### 3b. 验收不许只看账本（`tools\verify-run3.py` 的已知极限）

`verify-run3.py` / `analyze-longrun.py` 都是**账本检查器，不是世界校验器**：账本自己自洽时（每天 `ended_by=sleep`、跨日、`verified=true`、`checks` 全真、`leftover==0`、`watered_outdoor=true`、`failed_steps == Σ stages.failed`）它们会判 VERIFIED，哪怕世界没变（deputy-lead 的负例 K 会把这条极限写成结论）。所以 run3 的验收**必须**同时附外部证据：

- 存档 `%APPDATA%\StardewValley\Saves\Wahaha_450799035\Wahaha_450799035` 的 **mtime/size 前进**（每个跨日都应该动一次）；
- `Game1.Date.TotalDays`（`observe` 的 clock.day/season/year）真变化，且与 journal 的 `day_end` 对齐；
- SMAPI 日志里对应的 `Synchronizing 'NewDay' task...` / `SaveGame.Save` 行与时间窗；
- 起跑基线 `tools\preflight.py --save-baseline` 的 JSON 与跑完的观测做差分。

以上缺一条 ⇒ 结论只能写 `needs_review`，不许写"通过"。

**`verify-run3.py` 已加固（Lead，2026-10-13，提交 `fd0ec6d`）**，加固后它除了语义检查还会查账本**内部自洽**：①`finish` 自身自洽（`code==0 ⇔ verified_streak>=days`）+ 与工具结论同向（仅当 `finish.days == --days` 可比时算问题）②`final_water.dry>0` 与 `checks.watered_outdoor=true` 互斥 ③跨日必须**恰好 +1 天**（按 28 天/季折绝对日序）④**0 步 VERIFIED 必须有"无活可做"证据**（`no_intents`/`plot_exhausted`/`policy_fallback` 事件，或 `sleep.reason`/`ended_reason` 以 `no_work`/`night`/`stamina` 开头）⑤`t` 回退与当天时间轴倒挂只记信息项（`t` 是 longrun 自己的 `time.time()`，时钟回拨会误杀真跑）。
**加固后的已知盲区仍在**：完全自洽的伪造账本（K）、0 步但伪造了"无活可做"理由（K2）都会判 VERIFIED ⇒ 上面四条外部证据依然是硬要求。加固后的矩阵期望：exit 0 = green/G/I/K/K2；exit 1 = A–F/H/J/K3/K4/task11-modal-day/真机 run2（详见 `docs\_verify-run3-limits.md`）。

## 4. 回退

- 装机时旧 dll/manifest 自动留 `.bak-<ts>`；回退 = 复制回两个文件 + `deploy-mod.py --skip-backup` 重装。
- **存档不动**：`deploy-mod.py` 装机前先备份存档；run3 期间不允许任何"重启续跑"（要重启就另起 run4 并写新 journal）。
- 若 run3 中途桥掉线/崩溃：保留 journal 原文，用 `verify-run3.py` 如实判 `needs_review`，不修饰结论。

## 5. 记录要求

- 部署与 run3 各写一条 `docs\00-开发日志.md` 条目（倒序置顶，含 日期/阶段/目标/做了什么/结论与证据/下一步/待决）；踩坑必写。
- run3 证据落 `docs\_run3-evidence.md`（machine-runner 交付，含跨日证据：`Game1.Date.TotalDays` 变化 + 存档 mtime/size 前进）。

## 6. 实际执行记录（2026-10-13 夜，Lead 亲跑）

| 时刻 | 动作 | 结果 |
|---|---|---|
| 01:11 | `python tools\_bump-mod-version.py 0.7.22 --note-file tools\_note-0722.txt` | manifest `0.7.21 → 0.7.22`，Description 头部插入 v0.7.22 说明 |
| 01:11 | 改 `brain\agentfarm\bridge.py`：`MOD_VERSION_EXPECTED = "0.7.22"` | 与装机版本对齐（注释列出本版六项内容） |
| 01:11 | `dotnet build .\AgentFarm.Bridge.csproj -c Release --no-incremental` | **0 个警告 / 0 个错误**；`AgentFarm.Bridge.dll` 158208 B / 01:11:35 |
| 01:12 | `python -m unittest discover -s tests`（PYTHONUTF8=1 + PYTHONPATH=brain） | **Ran 280 tests / OK**（基线 262 → 280，含 task-11/15/28/30） |
| 01:12 | `git commit dd7ea96` | 冻结提交：manifest + bridge.py + task-15（`longrun.py`/`test_longrun.py`）+ task-30（`tools\analyze-longrun.py`/其测试） |
| 01:10–01:13 | `python tools\deploy-mod.py`（日志 `logs\deploy-0.7.22.log`） | 备份存档 → 装 0.7.21→0.7.22（dll 158208 / manifest 15083）→ 启动 `flags=0x210` → `桥已就绪：modVersion=0.7.22 port=17890` → `load_save` 进 `Wahaha_450799035`（FarmHouse (9,9)）→ `[OK] 部署闭环完成` |
| 01:13 | `python tools\preflight.py --expect 0.7.22` | 版本 ✅（0.7.22 == 0.7.22）/ 已读档 ✅ / 无模态 ✅；`isOutdoorFarm` ❌（起跑瞬间人在 FarmHouse —— runner 的 `_prepare()` 会自己走到 Farm，01:15 复查已 ✅） |
| 01:13 | 彩排起跑：`python tools\run-longrun.py --days 1 --size 5 --max-minutes 30 --journal logs\longrun-rehearsal-0.7.22.jsonl` | **LLM 边界决策开启**（默认；m01184 的告知义务见开发日志条目 034） |

彩排前的世界读数（`scratch\rehearsal_state.py`，独立证据，非账本自述）：
`spring 11 06:30 / FarmHouse (9,9) / isInBed=true / 体力 270 / 钱 14 / 无种子 / waterLeft 27 /
farm={complete:true, crops:32, dryCrops:32, unwateredCrops:32, weeds:462, stones:245, twigs:121, grass:620, trees:218, emptyDirt:53}`；
存档 `Wahaha_450799035` 3502298 B / `SaveGameInfo` 25234 B / mtime `2026-10-11 22:24:19`（**跑完必须前进**）。

彩排中途实测（01:15，只读）：`farm.dryCrops` **32 → 18**（14 格浇下去了）、`waterLeft` **27 → 13**，而
`farm.unwateredCrops` **仍是 32** —— 现场再次证明旧字段不是"今天没浇的格数"（task-10 的结论），
`dryCrops` 才是（task-23 交付的新字段，本版首次真机使用）。

**踩坑（本夜，已修）**：`tools\preflight.py:100` 调了不存在的 `worker.seed_items(obs)` ⇒ 每次跑都在
"种子清点"一行打 `AttributeError: 'FarmWorker' object has no attribute 'seed_items'`（不致命，但基线 `seeds` 恒空）。
修法：改成模块级函数 `farmwork.seed_items(worker.player_of(obs))`（`tools\preflight.py:27` 同步 import）；修后复跑该行不再报错。

**另一个观察（未修，明天处理）**：后台跑长任务时 stdout/文件写都是**块缓冲**（`logs\longrun-rehearsal-0.7.22.jsonl`
在 2048 B 才落盘一次、Tee 的 `.log` 整段不出现）⇒ 想边跑边看，起跑命令要带 `-u`。
