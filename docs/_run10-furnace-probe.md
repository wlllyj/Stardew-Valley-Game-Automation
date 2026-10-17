# task-214 · Furnace 配方/触发器真机内省取证（0.7.37）

> 状态：**阻塞，未进入步骤 ①**。装机 0.7.37 的 Mod 在 `Skills.IsKnownSkill` 白名单里**没有** `debug_dump` / `add_missed_recipes`，
> 请求在进主线程之前就被 `unknown_skill` 拒掉 ⇒ 步骤 ②③④ 全部无法开始。**没有对世界做任何写操作**。
> 修复已存在于 HEAD `8f357bd`（未冻结、未部署）；需要 Lead 冻结新版（0.7.38）并重装后才能重跑本卡。

## §1 环境与指纹（我实测）

| 项 | 读数 |
| --- | --- |
| 游戏进程 | 存活（Lead 已 `goto Farm`，角色在 Farm (64,15)） |
| 桥 | `health = {ok:true, status:"ok", modVersion:"0.7.37", runtime:{ticks:76592, uptimeSeconds:1287.4, worldSeq:184, hasSaveLoaded:true, onTitleScreen:false}, server:{port:17890, requestsServed:13}}` |
| 装机 dll | `…\Steam\steamapps\common\Stardew Valley\Mods\AgentFarm.Bridge\AgentFarm.Bridge.dll` = **263168 B / 2026-10-17T23:20:40.742 / SHA256 `c1470b014037d38b0c92cf09af914d8274e94a75aa30cbcc7fb352c3cfa2ce58`**（与 Lead 给的 `C1470B014037D38B` 一致） |
| 装机 manifest | **56017 B / 23:18:45.036 / Version `0.7.37`** |
| 仓库 Release dll | `mod\AgentFarm.Bridge\bin\Release\AgentFarm.Bridge.dll` = **269312 B / 23:36:04.521 / SHA256 `1fde5f709eac1ec10de05c4a7670548210018757c7ac22e09e3491eeedff1f3e`**（**比装机新、大 6144 B**，含修复） |
| 仓库 manifest | 56017 B / 23:18:45.036 / Version `0.7.37`（与装机同一份） |
| `preflight --expect 0.7.37` | **exit 0**（`结论：✅ 可以起跑`；`farmingLevel 2`、`seeds [["483","Wheat Seeds",10]]`、`crops 34`、`unwatered 2`、`dryCrops 34`、`farmScanSeq 92`、`waterLeft 25`、`tillableCount 132`、`tileCount 400 truncated`、`worldAdvancing true`） |
| 存档四条（before） | 主档 `Wahaha_450799035` **4417243 B / 2026-10-17 12:09:48.738**；`_old` 4407033 / 11:35:56.736；`SaveGameInfo` 29567 / 12:09:48.842；`SaveGameInfo_old` 29527 / 11:35:56.738 |
| SMAPI | `SMAPI-latest.txt` 75997 B / mtime 23:33:38.191；`[23:23:19 INFO AgentFarm Bridge] AgentFarm Bridge v0.7.37 已就绪（schema agentfarm-bridge/1）` |

装机 Mod 目录里只有**一份** `AgentFarm.Bridge.dll`（263168 B），其余是 `.bak-2026*` 历史备份（最大 203776 B）⇒ SMAPI 加载的就是这份，不存在"加载到旧备份"。

## §2 步骤 ① 的失败原文

命令与落盘：`python scratch\_t213_probe.py --table crafting_recipes --key Furnace` → `logs/run10e-step1.txt`，**exit 1**：

```
❌ debug_dump(crafting_recipes) 失败：unknown_skill: [unknown_skill] (HTTP 200) 未知技能“debug_dump”（本 Mod 不认识这个技能名）
```

`unknown_skill` 是 Mod 侧**进主线程之前**的拒绝码（见 §3），因此：没有打开任何菜单、没有读写世界、没有落盘。步骤 ②③④（`trigger_actions` 全量、`--add-missed` 一次、复核条数）**均未执行**；`--add-missed` 一次都没发过。

## §3 证据链（为什么是"白名单漏了"而不是装错文件）

1. **拒绝点**：`mod/AgentFarm.Bridge/BridgeHost.cs:520-535`
   ```csharp
   string skill = exec.Skill.Trim();
   // 未知技能：连主线程都不必碰
   if (!Skills.IsKnownSkill(skill)) { … Status = "unknown_skill",
       Reason = $"未知技能“{skill}”（本 Mod 不认识这个技能名）" … }
   ```
   之后才会 `Skills.ClampTimeoutFor(...)` / `Skills.Create(...)` —— 即分发代码根本没被调用。
2. **白名单**：`mod/AgentFarm.Bridge/Skills.cs` 的 `KnownSkills`（`IsKnownSkill` :802）。在**冻结提交 `063351d`（= 装机版本的来源）**里，这个表**只有 19 个名字**：
   `noop, move_to, dismiss_modal, move_to_location, load_save, quit_game, interact, use_tool, select_item, plant, sleep, buy, sell` + 规划中 `exit_building, harvest, pickup_debris, collect_machine, refill_watering_can, talk`
   ⇒ **`debug_dump` / `add_missed_recipes` 不在表里**（`upgrade_tool`/`pickup_tool`/`craft_item`/`place_object`/`machine` 也不在）。
3. **分发代码却在**：同提交里 `Skills.cs:99-102` 与 `:454-456` 都已有 `case "debug_dump": case "add_missed_recipes":`；`a0a0a4d`（task-213）把类型 `DebugDumpSkill` / `AddMissedRecipesSkill` 也编进了 dll（dll 内 UTF-16LE 字面量 `debug_dump`/`add_missed_recipes` 在**装机版与仓库版都存在** ⇒ "字面量缺失"不是原因）。
4. **修复提交 = `8f357bd`（HEAD，2026-10-17 23:36:53，"wip(task-210)"）** 把白名单补齐：
   `L795: "upgrade_tool", "pickup_tool", "debug_dump", "add_missed_recipes",`、`"craft_item", "place_object", "machine",`
   并给这个表加了自述注释：**「⚠️ 必须与 `Skills.Create` 的 case 逐字同步：`BridgeHost.ServeExec` 在进主线程之前就按这张表把不认识的技能一律 `unknown_skill` 拒掉。task-205/213/210 的真机事故教训：Create 里加了 case 但忘了这里 ⇒ 装机后才炸。」**
5. **时间线（关键）**：`063351d` freeze **23:21:03** → `f252202` **23:22:36** → 装机 dll 23:20:40（由 `063351d` 构建）→ **`8f357bd` 23:36:53（HEAD，含修复）** → 仓库 Release 重建 23:36:04（269312 B）。即：**修复是在装机之后才提交的，装机版天然没有它**。
6. 可复跑取证：`python scratch\_t214_vercheck.py`（只读；产出 `logs/run10e-dll-vercheck.json`，含两侧 dll/manifest 的 size/mtime/SHA256 与 UTF-16LE 字面量探针、`health`）。

结论：**这是 task-205/213/210 同一类"`Skills.Create` 加了 case、`KnownSkills` 忘了同步"的装机事故**，不是文件拷错、不是 manifest 描述撒谎（那段 changelog 文本来自 manifest，manifest 本来就是新版）、不是字节探针问题。

## §4 未执行与未写操作声明

- 未执行：步骤 ①②③④ 中除 ① 的失败调用之外全部；未 `--add-missed`（一次都没有）；未 `craft/place/buy/sell/load_save`；未 `dismiss_modal`；未开任何菜单。
- 未改动：世界（钱/背包/作物/时间）、存档四条（§1 的 before 读数）、代码、Mod 目录。
- 未做本卡步骤 ⑤ 的两件事：**未冻结 SMAPI 窗口**、**未退游戏**（游戏仍活、桥 `requestsServed 13`）—— 因为需要留作新版重装后的复核台；这两步等重跑本卡时一并做。

## §5 恢复执行的前置条件（需要 Lead 的写权）

1. 从 **HEAD `8f357bd`** 冻结 **0.7.38**：`_bump-mod-version.py` → `brain/agentfarm/bridge.py` `MOD_VERSION_EXPECTED` → build → `check-release --expect 0.7.38` → `deploy-mod.py --no-quit`；把新的 dll/manifest 指纹发我。
2. 我按本卡原步骤重跑 ①②③④（`--add-missed` 仍**只调一次**），再走 ⑤（SMAPI 冻结 + 退出 + 存档四条对照）。
3. 若 0.7.38 仍报 `unknown_skill`，则问题不止白名单（此时请把 `logs/run10e-dll-vercheck.json` 与 `health.modVersion` 一起对照），我会按同样方式继续二分。

## §6 结论（二选一，本卡未能定论）

- 【无法判定】Furnace 配方在本存档是否真的缺失、`AddMissedMailAndRecipes` 能否补出来 —— **因为唯一能回答这两个问题的 `debug_dump` / `add_missed_recipes` 在装机版上不可用**。
- 已确认的**外围事实**（来自 task-209 的只读取证，不是本卡新增）：存档 `craftingRecipes` 19 条里没有 `Furnace`；全农场/全地点无 `Furnace(114)` / `Charcoal Kiln(12)`；玩家 `mining` 1 级、`deepestMineLevel=0`。
- 本卡产出：`logs/run10e-step1.txt`（失败原文）、`logs/run10e-dll-vercheck.json`（指纹/字面量探针）、`scratch/_t214_vercheck.py`（可复跑）。
