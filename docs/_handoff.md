# 交接说明（HANDOFF）· 星露谷自动化项目

> **新会话请先读这份**。它记录「现在到哪一步、怎么接着干、别踩哪些坑」。
> 详细过程在 `docs\00-开发日志.md`（条目 001–024，权威记录），架构/协议见 `docs\01-架构设计.md`、`docs\03-桥接协议.md`，P3 计划见 `docs\_p3-kickoff.md`。
> 本文件写在 2026-10-11 晚 —— 起因：**bili 上下文压缩在本会话里已经无法再折叠**（见文末「压缩问题」），需要换一个干净会话继续。

## 1. 目标（未变）
做**完全自主**的星露谷 AI：脑（外部 Python 进程）通过桥接 Mod 自主规划 + 操作，**不需要人介入**。
三阶段：①架构设计（P1，已完成并冻结）→ ②跑通基本操作（P2，已完成验收）→ ③**P3 = 农场清理 → 开垦 → 播种 → 浇水，端到端、连续 3 个游戏日无人介入**（进行中）。
用户长期授权：`User said (m01020): "没问题就继续吧，朝着目标，我没说停你就对准目标进行"`。
用户硬性要求：`User said (m01184): "大模型开始介入的时候告诉我一下"` —— 项目里的慢脑（`brain\agentfarm\llm.py`）**进入自动化循环前必须先告知用户**；P3 第⑤步的"边界决策"就是这个节点。
硬要求：**开发过程写进 `docs\00-开发日志.md`**（每条含 目标/做了什么/结论与证据/下一步/待决）。

## 2. 现在到哪了（本文件写作时的状态）
| 项 | 状态 |
|---|---|
| Mod | **0.7.18** 已装机并在跑（游戏在存档 `Wahao_450799035`… 实际为 `Wahaha_450799035`）|
| 快照 schema | `agentfarm-world/6`（脑侧 `MOD_VERSION_EXPECTED="0.7.18"`、`SCHEMA_WORLD="agentfarm-world/6"`、legacy `(5,4,3)`）|
| 单测 | `python -m unittest discover -s tests` → **45 OK** |
| P2 验收 | 落点契约 **18/18**（`tools\verify-landing.py`）、跨地点 **6/6**、`load_save` **4/4**、无人值守部署闭环 **6/6**、监督循环真机 ok |
| P3 ①–④ | **已完成并真机验收**（详见 §3）|
| P3 ⑤ 确定性部分 | **3x3 试点刚通过**：8/9 格"清障→锄→种→浇"全部差分通过，1 格跳过（草，锄头不产耕地），耗时 49s，终态 `VERIFIED` |
| P3 ⑤ 边界决策 / ⑥ | **未开始**（⑤的 LLM 部分按 m01184 需先告知用户）|

## 3. P3 已验收的事实（判据一律 `observe?detail=full` 的 `tiles[]` 差分）
- **逐格感知**（`agentfarm-world/6`，仅 `detail=full`）：
  `location.tiles[]`（`tile/kind/tool/objId/feature/standable/actionable/crop/ripe/dead/watered/plantable`，按离玩家距离排序、上限 400、`tilesTruncated`）；
  `location.tillable[]`（±12 格可锄空格、近处优先、上限 200，真机 196–200 格）；
  `location.doors[]`；`player.inventory[]`（槽位/id/名字/堆叠/是否工具）。
- **`move_to`**：到达判据 = "在目标格上 **且像素连续 12 帧不动**"，之后 `StepMover.HaltPlayer()`（`Halt()`+`controller=null`+`movementDirections.Clear()`）。旧判据在"刚跨过格子边界那一帧"就成立 ⇒ 修复前 soak **7/7 落错格**，修复后 **18/18 全对**。
- **`move_to_location`**：地点图 = `Game1.locations` 节点 + `loc.warps` 边 + **建筑门**（`Building.getPointForHumanDoor()`/`GetIndoors().NameOrUniqueName`/落点 `indoors.warps[0].Y-1`）；每跳判据只有 `Game1.currentLocation.Name` 真的变了。真机：`FarmHouse→Farm` 走室内 warp `source=[3,12] landing=[64,15]`（7616ms）；`Farm→FarmHouse` 到门前 `(64,15)` 调 `checkAction((64,14))`（1222ms）→ **往返 6/6**。
- **`use_tool`**：选工具槽 → 转向 → `Game1.pressUseToolButton()` → 等 `UsingTool` 落回 false；判据**按工具分别判**（`hoe`→该格出现 `HoeDirt`、`can`→`watered=true`、`axe/pickaxe/scythe`→该格东西没了）；`auto`＝候选工具序列＋失败换工具。真机各 1 次完成：树枝→Axe、石头→Pickaxe、**杂草→Hoe**。
- **"先判后动"**（用户 m01668 提的）：`StepMover.Tillable(loc, p, out why)` 照抄游戏 `Hoe.DoFunction` 的 IL 判据（无地形特征 + 无放置物 + 非水面 + Back 图层有 `Diggable`）；`use_tool` 对"空洞且首选 hoe"先跑它 —— 真机不可锄格 `(58,9)` **0.0s** 返回 `precondition_failed`（此前要白挥 6 次）。
- **`select_item` / `plant`**：`plant` 走 ①`pressUseToolButton()`×3 ②`GameLocation.leftClick(x,y,player)` ③`Object.placementAction(loc,x,y,player)`，判据"该格出现 crop"。⚠️ **②③的 x/y 是像素**（`placementAction` IL 开头 `new Vector2(x / 64f, y / 64f)`）。真机：`(64,18)` 锄→`kind=dirt` → `plant(472)`→`crop=24` → `can`→`watered=true`。
- **3x3 试点**（`tools\run-plot.py --size 3 --seed 472`）：8 格 ✅（cleared/tilled/planted/watered 全 True，体力 266→232），1 格 ⏭️（`草（该用镰刀割，锄头不产耕地）`），**0 格没做成**，终态 `VERIFIED`。

## 4. 怎么接着干（开发循环）
1. 改 Mod 代码 → `cd mod\AgentFarm.Bridge; dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo`（要 0 错误 0 警告）。
2. **装机 + 重启 + 读档全自动**：`python tools\deploy-mod.py`（备份存档 → `quit_game` 优雅退出（失败才 `taskkill`）→ 装 dll+manifest（旧文件留 `.bak-<ts>`）→ 启动（`CREATE_NEW_CONSOLE|CREATE_NEW_PROCESS_GROUP`）→ 轮询 health → `load_save`）。跑测试：`python -m unittest discover -s tests`。
3. **验收一律用观测差分**：写一次性脚本到 `%TEMP%`（或 `tools\`），比对 `tiles[]` 前后状态；**回执只是声明**。已积累的验收脚本：`tools\verify-landing.py`、`tools\verify-no-pause.py`、`tools\run-plot.py`。
4. 每完成一个有意义的单元 → 往 `docs\00-开发日志.md` 顶部追加条目（含证据数字与踩坑）。
5. 探针优先：**先钉死游戏 API 再写代码** —— `tools\api-probe\`（编译期存在性；CS0117=不存在、CS1503=签名不同、CS0122=private）+ `tools\il-probe\`（自建 IL 反汇编；支持 `Type|Method`、嵌套类型 `Outer+Nested|Method`、方法名 `*` 包含匹配、以及 **`FIND|子串` 全程序集搜"谁调用了 X"**）。用 `dotnet run -c Release -- "<游戏目录>" "..."`。

## 5. 下一步（建议顺序）
1. **P3 ⑤ 确定性部分收尾**：`python tools\run-plot.py --size 5 --seed 472`（25 格），把失败/跳过明细记进日志；如需更大区域，走过去再 observe 一次（`tillable[]` 只覆盖玩家 ±12 格）。
2. **P3 ⑤ 边界决策层（先告知用户 m01184！）**：把 `brain\agentfarm\llm.py` 接进循环，只在**边界**用（换任务类型、异常恢复、跨日复盘）；LLM 输出**任务意图**（做什么/在哪片区域/为什么），坐标与动作序列仍由技能层按当下世界状态算（P1 核心决策：LLM 不碰坐标）。
3. **P3 ⑥**：扩到目标区域 + 处理体力/时间（进食/睡觉；睡觉确认框**不能盲按确认键**，要走 `answerDialog`/`dismiss_modal` 的既有纪律），跑满**连续 3 个游戏日无人介入**；长跑时用 `agentfarm run`（`brain\agentfarm\runner.py`）做看门狗。
4. 旧账：把 `watchdog`/`runner` 与规划层真正合到一个长跑循环里（目前 `runner` 只监督、不驱动任务）。

## 6. 踩过的坑（务必复用，别重蹈）
- **PowerShell 5.1 会毁 UTF-8**：`Get-Content -Raw` + `Set-Content -Encoding utf8` 把无 BOM UTF-8 当 cp1252 读 ⇒ 中文全乱码。**改文件只用编辑工具或 Python**；Python 脚本要**先写 .py 文件再执行**（在 PowerShell here-string 里嵌 `"` 会毁掉脚本，已踩两次）。
- **起游戏的方式**：`subprocess.Popen(..., creationflags=CREATE_NEW_CONSOLE(0x10)|CREATE_NEW_PROCESS_GROUP(0x200), stdout/stderr/stdin=DEVNULL)`。`DETACHED_PROCESS(0x8)` **起不来**（SMAPI 需要自己的控制台，150s 桥都不通）。`tools\start-game.cmd` **不要接管道**（游戏继承管道句柄 ⇒ 永久挂起）；后台作业被 `job_kill` 会**连带杀掉游戏**。
- **异步传送/淡出期间不下任何"失败"结论**（`Game1.locationRequest != null`）：曾出现 `goto Farm` 报 blocked 而人已站在 Farm。
- **`Game1.pressUseToolButton()` 在"鼠标这一帧可见"时作用在鼠标格**（IL：`wasMouseVisibleThisFrame ? 鼠标世界坐标 : GetToolLocation(false)`；真机鼠标格 `63,-2`）⇒ 工具走 GetToolLocation 不受影响，播种要绕开鼠标（直接调 `leftClick`/`placementAction`）。
- **坐标单位**：跨进游戏内部 API 前先确认单位。`placementAction`/`leftClick`/`Hoe.DoFunction` 的参数都是**像素**（内部 `x/64f`），传格坐标会静默失败（表现为"游戏不让做"）。
- **证伪清单**（省下重复探针）：`Farmer.UseTool` / `completeToolUse` 不存在；`Object.performUseAction` 无"对指定格"重载（只有 1 参 `(GameLocation)`）；`HoeDirt.performUseAction` 在 `crop==null` 时直接 `return false`（只管收获）；`GameLocation.ResolveSeedId` 不可访问（CS0117）；`Game1.ExitToTitleScreen` / `Program.quitting` / `SaveGame.GetSaveGames` / `Game1.loadingMultiplePlayers` / `Context.IsSaveLoaded` 不存在；`SaveGame.GetSavesFolder` / `Program.savesFolder` 不可访问。
- **存档布局与有效性判据**：`%APPDATA%\StardewValley\Saves\<名字>\`（`SaveGameInfo` / `SaveGameInfo_old` / `<名字>` / `<名字>_old`）；**有效 = `<名字>` 文件存在**。
- **环境**：游戏 1.6.15 / SMAPI 4.5.2 / .NET 6；游戏目录 `D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley`；DSH Python `C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`；长任务重定向到日志文件（`Select-Object -First N` 会掐死上游 python）。

## 7. 压缩问题（为什么需要换新会话）
**本会话的 bili 压缩已经无法再折叠**，不是它坏了：
- 它列出的唯一可压范围是 `m00001–m01767`（688.2K），但该范围**整体落在 31 个活跃块里**（回执固定：`already compressed in b1..b30 → refold blocked (not restored)`）；
- 官方解法是"先把相关块 inline 恢复再重压"，但实测单块 `b1` 恢复就是 **160,066 字符**（≈40K token），31 块合计 ≈688K 字符 —— **恢复的代价正是我们想省掉的东西**，不可行；
- 熔断器已 **18 次连续失败**（`consecutiveFailures 18/3`），按设计不再尝试；
- 根因之一是**可见消息编号是"重启世代"的局部编号，与真实会话 ref 不对应**，所以我圈出的窗口在工具眼里都是老内容（这也让"按提示压小范围"全部失败）。
**结论**：继续在这个会话里压不出东西；**换一个干净会话**（上下文重置为系统提示+工具 schema ≈ 50K 起）并把这份 HANDOFF 作为唯一入口，是最省事的解法。旧会话里的一切**已在磁盘上**：日志 001–024、协议、架构、探针结论（`docs\_il-*.md`）。

### 实测证据（2026-10-11 20:2x，供后来者省时间）
```
compress(m00001..m01767)  → FAILED  19 连败，熔断器 19/3
  "already compressed in active block(s) b1, b30 → Refold blocked: blocked by b1 (not restored); … b30 (not restored)"
  diagnostics: session highest ref = m01997, session history = 31 compressions, 31 blocks
decompress(blockId=b1, toFile=…\_b1-restore.txt) → Content (160066 chars)
  ⇒ 单块恢复就 16 万字符；31 块 ≈688K 字符 ≈ 整个会话——"恢复再重压"等于白折腾
compress(各种小窗口) → 同一条回执（可见编号是"重启世代"局部编号，与真实 ref 不对应）
```
### 新会话恢复步骤（照做即可）
1. 目录：`D:\Deepseek Harness Workspace\星露谷游戏自动化`（先 `pwd` 确认）。
2. 读 `docs\_handoff.md`（本文件）→ 需要细节再读 `docs\00-开发日志.md` 最新条目、`docs\03-桥接协议.md` §6/§8。
3. 检查现场：`python -m unittest discover -s tests`（应 45 OK）；`python -m agentfarm health`（`modVersion` 应为 0.7.18；游戏不在跑就用 `python tools\deploy-mod.py --no-quit` 把它拉起来并自动读档）。
4. 接着干 P3 ⑤：`python tools\run-plot.py --size 5 --seed 472`（先 3x3 已过）；**接 LLM 之前先告知用户**（m01184）。
5. 纪律不变：改完 Mod → `tools\deploy-mod.py` 装机+重启+读档；每步用 `observe` 差分验收；写日志。
