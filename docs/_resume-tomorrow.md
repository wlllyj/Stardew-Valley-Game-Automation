# 接续清单 · 2026-10-11 收工时点（明天从这里开始）

> 本文是**收工快照**，只写"明天开工要用的东西"。`docs\_resume-prompt.md` 是 P2 时代的三步恢复法（仍然有效：单测 → `deploy-mod.py` → `run-plot.py`），但它的状态表已过期，以本文为准。
> 目标不变：**P3 ⑥ —— 端到端自主完成「清障 → 开垦 → 播种 → 浇水」，连续 3 个游戏日无人工介入**（判据一律用 `observe?detail=full` 的 `tiles[]`/`inventory[]`/`money` 差分，回执不算证据）。

## 0. 一句话状态

Mod **0.7.21** 装机中（游戏**未运行**、桥文件不存在、端口 17890 无监听、存档未被改写——machine-runner 独立复核过）；单测 **194 OK**（dev-coder 昨晚收工前跑出，188 → +6）；`git status` 有 dev-coder 的 5 个 WIP 文件未提交（见 §4）；任务：task-7（dev-coder，已停点、**代码在树里但未 bump/manifest 仍 0.7.21**）、task-10（log-analyst，**已交付并 complete**）；已交付的分析 = task-3（run1 行为）、task-6（睡觉根因）、task-9 复核（deputy-lead，6 账本独立复跑 PASS）、**task-10（`docs\_tool-matrix.md` + `docs\_analyze-farmcounts.md`）**；**新增 task-19**（浇水/计数验收口径，run3 前置）、**task-20**（工具等级可观测 + clump 判据，不阻塞 run3）。**两条最硬的结论** = 睡觉失败机制（`docs\_il-sleep-path.md`）+ **我自己的验收工具曾"白过"浇水一项**（见 §6 / §8）。goal 已 pause（rev3 / disarmed），你说"继续"就 resume。

## 1. 明天开工 30 分钟内要做的三件事

1. `git status --short` + `python -m unittest discover -s tests`（期望 188 OK，dev-coder 若已补用例会更多）——确认昨晚停点没被别人动过。
2. 看 `docs\_resume-tomorrow.md`（本文）§3 的任务顺序，把 task-7 的结果收进来：dev-coder 报完工 ⇒ 立刻让 deputy-lead 做集成验收（`py_compile` + 全量单测 + `dotnet build` 0 错 0 警）。
3. 收完 task-7 后按串行链推进；**Mod 版本只 bump 一次**（0.7.22），bump 完跑 `python tools\check-release.py --expect 0.7.22`。

## 2. 今天的决定性结论（task-8 直接照这个做）

`docs\_il-sleep-path.md`（含偏移级 IL 证据）：

- `GameLocation.answerDialogueAction` 是**字面量分派**：`IL_0ABC ldstr "Sleep_Yes"` → `brtrue IL_30D5` → `call startSleep()`；**没有** `isInBed`/`dialogueUp`/`lastQuestionKey` 前置判据；字符串对不上就 `IL_393D` **静默 no-op**（`Farm` 覆写同偏移同序列、`FarmHouse` 不覆写）。
- `startSleep()` 唯一分支 = `Game1.IsMultiplayer`：真 → 装 `ReadyCheckDialog("sleep", isCancelable: true, …)` 返回、**不睡**；假 → `doSleep()`。
- `doSleep()` **零前置判据**，三条分支都 `if (Game1.IsMasterGame) Game1.NewDay(0f)`。
- 22:07:55 的 PASS 探针在同一进程同一存档 **1.8s 跨日** ⇒ `IsMultiplayer=false`、`IsMasterGame=true` ⇒ run2 失败**只能**是"应答字符串没等于 `Sleep_Yes`"⇒ `lastQuestionKey` 前缀不是 `Sleep`（提问没开、`interact(bed)` 没能让游戏弹提问）。

⇒ task-8 的判据用"**游戏自己弹出了睡觉提问**"（`lastQuestionKey` 前缀 `Sleep` / `ui.dialogueIsQuestion`），**不要**用 `isInBed`；拼不出 `Sleep` 前缀就立刻 `sleep_no_question` 失败（附 `isInBed`/`lastQuestionKey`/`activeClickableMenu`/`gameMode`），绝不等 180s；不要反射调 `startSleep()`/`doSleep()`。

## 3. 任务顺序（单写者串行，改自今天定稿的链）

```
task-7 (Mod 0.7.22: 镰刀真挥 + Done() Grass 判据 + clear() 多刀)   ← dev-coder 已停点（代码在树里）
  → task-8  (sleep 跨日: 先让游戏弹提问再回答; Mod 早失败)          blocked_by task-7
  → task-11 (模态守卫: LevelUpMenu 关 / SaveGameMenu 只等)          blocked_by task-8
  → task-15 (日级验收纳 no_unmet_stages + 买种子时机)               blocked_by task-11
  → task-19 (浇水/计数验收口径: checks.watered_outdoor, run3 前置)   blocked_by task-15
  → task-13 (bridge.json 字段容错)                                  blocked_by task-19
  → task-17 (world_stuck 检测与自愈)                                blocked_by task-11, task-15
  → task-14 (ensure_location 逐帧 warp 循环 + /v1/exec 带 skill 名)  blocked_by task-13, task-17
分析链：task-6 ✅ → task-10 ✅ → task-5 (卖出/出货 IL 取证)
run3 之后（不阻塞）：task-20 (工具等级可观测 + ResourceClump 工具/判据, blocked_by task-12)、
                     task-18 (职业选择自动化, 耕种优先: Tiller → Artisan)
真机：task-12 = run3 三日连跑（machine-runner，blocked_by task-7/8/9/11/15）——**必须等 Mod build 完 + Lead 部署完再 claim**
```
**Mod bump 规则**：0.7.22 由链上**最后一个 Mod 改动者**统一 bump（task-19 会加 `farm.dryCrops` 字段、task-14 改 `MoveToLocationSkill`/`BridgeHost`），bump 后同步 `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED` 并 `dotnet build` 0 错 0 警；在那之前**不要部署当前 dll**（行为已变、版本号没变，部署了会让 preflight 的版本断言失去意义）。

`task-9`（brain 账目/资源三处）已完成；`task-3`/`task-6` 已交付；`task-16` = deputy-lead 常设独立验收（每份 dev-coder 完工都要过它）。

## 4. 未提交的工作树（明天先看清再决定）

`git status --short`（收工时）：**dev-coder 的在制文件不要替它提交/回退**——`mod/AgentFarm.Bridge/UseToolSkill.cs`、`brain/agentfarm/farmwork.py`、`brain/agentfarm/bridge.py`（仅 docstring）、`tests/test_farmwork.py`、`tests/test_longrun.py`；另有 `scratch/_farm_dump.py` 未跟踪（不是 dev-coder 的）。
Lead 自己的改动（`tools/verify-run3.py`、`docs/_il-sleep-path.md`、`docs/_analyze-sleep-fail.md`、`docs/_review-task9.md`、`docs/00-开发日志.md` 条目 028、本条目、`scratch/_review_neg_gen.py`）已提交（`2ed2117`）。

### 4a. dev-coder 的 task-7 停点报告（昨晚收工，原文要点）

- **验证原文**：`py_compile exit=0`；`python -m unittest discover -s tests` → `Ran 194 tests in 2.342s` / `OK`；`dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo` → `已成功生成。` / `0 个警告` / `0 个错误`（仅编译自检，**未 bump、未 deploy**）。
- **改了什么**：①`UseToolSkill.Swing()` 不再调 `Game1.pressUseToolButton()`，改调新增 `BeginUse()` —— 照抄游戏近战门闸**之后**那段（`GetToolLocation(clickPx,false)` → `FacingDirection` → `lastClick=clickPx` → `p.BeginUsingTool()`；拿不到 player/工具或异常时回退 `pressUseToolButton()`）；②`Done()` 补 `if (tf is Grass) return false;`；③失败回执加"现在还是「<kind>」+ 起手=是/否"；④`farmwork.clear()` 挥到 `kind` 变化为止、上限 `MAX_CLEAR_SWINGS=4`，只有挥满上限或 Mod 回 `tool_ineffective`/`precondition_failed` 才 `proven_inert` 封格，`no_save`/`ui_modal` 记 `failed` 且**不封格**；⑤`_receipt_of()` 把 Mod reason 带进 journal。
- **待裁定的偏差**：没有"伪造输入边沿"，改走 `BeginUsingTool()`。
- **Lead 裁定（2026-10-11 收工）**：**批准走 `BeginUsingTool()`**。理由：`Farmer.BeginUsingTool()` 只 fire `beginUsingToolEvent`，订阅者 `Farmer.performBeginUsingTool()` 就是真正的起手（`CanMove=false; UsingTool=true; CurrentTool.beginUsing(...)`），镰刀同步进 `MeleeWeapon.setFarmerAnimating` → 同一次调用内 `DoDamage` —— 这是**游戏自己的入口**（与"用 `addItemToInventoryBool` 收货、用 `chargePlayer` 扣钱"同一原则）；伪造 `InputState._currentMouseState`/`Game1.oldMouseState` 会污染同帧所有读输入的系统，且挥动方向取决于人手鼠标位置，不可接受。**条件**：真机差分必须看到 `grass → 非 grass` + 回执"起手=是"；若真机证明割不动，再回头讨论"合成左键边沿"这条备选。
- **明天给 dev-coder 的两条附加要求**：①非近战工具现在跳过 `fadeToBlack`/`nonWarpFade` 门卫（渐黑时可能白挥一次）⇒ 在 `BeginUse()` 里加一个便宜的门：`Game1.fadeToBlack`（或 `nonWarpFade`）为真时返回**可重试**状态而不是挥；②Mod 内部 `MaxSwings=6` 与脑侧 4 刀叠加，最坏 4 次请求 ⇒ 真机跑完要拿 journal 的"第 N 刀"轨迹确认没有空转。

## 5. 命令速查（全部在仓库根目录跑）

```powershell
# 0) 环境（每次新 shell）
$env:PYTHONUTF8=1
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONPATH = "D:\Deepseek Harness Workspace\星露谷游戏自动化\brain"

# 1) 单测（以 "Ran N tests / OK" 为准；pwsh 报 [exit code: 1] 是 unittest 写 stderr 的噪声）
& $py -m unittest discover -s tests

# 2) 发布闸门（manifest==MOD_VERSION_EXPECTED、dll 新鲜度、py_compile、单测、git 干净）
& $py tools\check-release.py --expect 0.7.22

# 3) 只读起跑自检（装机版本 / hasSaveLoaded / isOutdoorFarm / isModal / worldAdvancing + 基线快照）
& $py tools\preflight.py --save-baseline logs\run3-baseline.json

# 4) 装机（Lead 独占真机；装机脚本会优雅退出游戏 → 装 dll+manifest → 启动 → 轮询 health → load_save）
& $py tools\deploy-mod.py

# 5) run3（machine-runner；跑完立刻优雅退出，别把游戏留在跑）
& $py tools\run-longrun.py --days 3 --size 5 --max-minutes 150 --journal logs\longrun-3day-llm-run3.jsonl

# 6) 独立复核（Lead；只读 journal，不采信执行者口头结论）
& $py tools\verify-run3.py --journal logs\longrun-3day-llm-run3.jsonl --days 3
```

## 6. 明天的验收口径（不许软化）

- **浇水证据（今天新堵的洞）**：窗口 `tiles[]` 的 `crops`/`unwatered_crops` **在室内恒 0** —— run2 里 `day_end.final` 是 `FarmHouse crops=0` 而 `checks.crops_watered=true` 白过；Mod 的 `farm.unwateredCrops` 又是 `HoeDirt.needsWatering()`（只读 `CropData.NeedsWatering`、**不看浇水状态**）⇒ 两者都**不能**当浇水证据。`tools\verify-run3.py` 现在要求 **`day_end.checks.watered_outdoor`**（缺字段即算问题），该字段由 task-19 落地：用当天**最后一个户外全量快照**逐格算"有 crop 且 `watered==false`"，或（更好）用 Mod 新增的 `farm.dryCrops`（farm-wide 真值，需 `farm.complete==true`）；`day_end.final_water` 记 `{t, location, tiles, crops, dry, scope}` 供手工复核。
- 尾部**连续 3 天**满足：`ended_by == "sleep"`（我们自己睡的）+ `day_end.verified == true` + `checks.watered_outdoor == true` + 当天 `day_end.stages` 求和硬失败 0 + 有目标阶段 `leftover == 0` + journal 无 `bridge_down`/`watchdog_stop`/`modal_timeout`/`no_day_progress`。
- 跨日证据：`day_end.final.day` 与 `day_start.day` 不同 **且** journal 里有成功的 `sleep` 事件；存档 mtime/size 前进。
- **`farm.*` 只在 `farm.complete == true` 时可用**（`complete=false` 全 0 ≠"0 个作物"）；两套计数（farm 扫全场 / 窗口 400 格）**不许混列**（run2 的 31→8→21→32 就是混列）。
- 回执 `ok=true` **不构成**任何判定依据（v0.7.17"种了种子不扣"与今天 `answerDialogueAction` 静默 no-op 两次教训）。

## 8. task-10 的两份交付（今天新增的关键事实，动手前先读）

- `docs\_tool-matrix.md`（对象→正确工具→等级门槛）：硬等级门槛**只在 `ResourceClump` 与 `Bush`**（600=铜斧≥1、602=钢斧≥2、148/622=金镐≥3、672=钢镐≥2、752 系列=镐任意；Bush 需斧且(铜斧或 `size==3`)）；weed/twig/stone/tree/fruitTree/grass **无门槛**（stone 只按等级算伤害）；grass 多刀（`(W)47`=1/刀、`53`=2、`66`=4，蓝草 50% 空挥）。**观测判不了工具等级**（`player.tools{}` 只有布尔）⇒ 现行规则 R2：`clump` 整类 `skipped`+`proven_inert`，不用 `auto` 去撞；Mod 缺陷 `WorldSnapshot.cs:438` 把 `ResourceClump` 一律写 `tool="axe"`（对巨石错）——都进 **task-20**。
- `docs\_analyze-farmcounts.md`（farm 聚合口径）：见 §6 的浇水证据条目。


## 7. 硬纪律（复用，别重新踩）

- 改 Mod ⇒ `dotnet build` **0 错 0 警** ⇒ 只有 Lead 能 `deploy-mod.py`（真机独占串行）。
- 改文件用编辑工具或"先写 .py 再执行"；**PowerShell 5.1 直接读写 UTF-8 会毁中文**。
- `tools\il-probe` 重定向到文件是 **UTF-16LE**，先 `tools\_tmp_conv.py` 转 UTF-8 再 `read`/`grep`。
- 异步传送/淡出期间不下失败结论（`Game1.locationRequest != null`）；`pid_alive` 绝不用 `os.kill(pid,0)`。
- 队友之间：写范围不重叠，跨任务顺序由 `blocked_by` 表达；被 `blocked` 的任务**不能** reassign owner。
- 用户硬要求：**大模型开始介入自动化循环前先告知用户**（已履行，2026-10-11 手动演练 + 用户已批准默认开启）；LLM 只给**方向**（具名田区 + 规模），**坐标一律由代码落**。
