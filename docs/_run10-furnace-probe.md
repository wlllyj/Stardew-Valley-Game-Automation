# task-214 · Furnace 配方/触发器真机内省取证（0.7.37）

> **状态：BLOCKED（环境/构建缺陷），不是 FAIL。** 装机 0.7.37 的 Mod 在 `Skills.IsKnownSkill` 白名单里没有
> `debug_dump` / `add_missed_recipes`（`upgrade_tool`/`pickup_tool`/`craft_item`/`place_object`/`machine` 也没有），
> 请求在**进主线程之前**就被 `unknown_skill` 拒掉 ⇒ 本卡**未取得任何配方/触发器证据**，步骤 ②③④ 无法开始。
> 修复在 `8f357bd`（WIP，未冻结未装机），将随 **0.7.38 重冻结**装机后原样重跑四步。
> 我对世界的写操作：**零**（未 `add_missed_recipes`、未开菜单、未 `load_save`、未 `craft/place/buy/sell`）。

## §1 五文件指纹与命令原文

**本卡实际只执行了一条 Mod 命令**（其余步骤因阻塞未发）：

```
python scratch\_t213_probe.py --table crafting_recipes --key Furnace
```

**五文件指纹**（16 位大写 SHA256 前缀；`[我复算]` = 我在本机重新算过，`[Lead 提供]` = 冻结时给的），冻结提交 **`063351d`**（`freeze: 0.7.37`，2026-10-17 23:21:03）：

| 文件 | size / mtime | sha16 | 与 Lead 指纹 |
| --- | --- | --- | --- |
| `brain/agentfarm/longrun.py` | 479420 / 2026-10-17 23:43:23.922 | `A71D304234A9832E` [我复算] | ❌ 不一致（Lead：`5D13B16DD8E824EE`）— **冻结后 dev-coder 又改过**（mtime 23:43 > freeze 23:21，`git status` 显示 ` M`），属在制改动，非我触碰 |
| `brain/agentfarm/farmwork.py` | 204190 / 2026-10-17 23:41:22.847 | `B0C719E23D4D0482` [我复算] | ❌ 不一致（Lead：`EB41BF868A69B346`）— 同上，` M` 在制 |
| `brain/agentfarm/bridge.py` | 58932 / 2026-10-17 23:19:40.983 | `40D1A2B300306F07` [我复算] | ✅ **逐字一致** |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll`（仓库构建） | 269312 / 23:36:04.521 | `1FDE5F709EAC1EC1` | — 这是**含修复的重建版**，比装机新（见 §3） |
| `mod/AgentFarm.Bridge/manifest.json` | 56017 / 23:18:45.036 | `87094344E412C2FB` [我复算] | ✅ **逐字一致**（Version `0.7.37`） |
| **装机** `…\Mods\AgentFarm.Bridge\AgentFarm.Bridge.dll` | **263168** / 23:20:40.742 | **`C1470B014037D38B`** [我复算] | ✅ **逐字一致**（= Lead 给的 dll 指纹；= 冻结件构建） |
| **装机** `…\Mods\AgentFarm.Bridge\manifest.json` | 56017 / 23:18:45.036 | `87094344E412C2FB` | ✅ 与仓库同一份 |

装机目录里只有**一份** `AgentFarm.Bridge.dll`（263168 B），其余是 `.bak-2026*` 历史备份（最大 203776 B）⇒ SMAPI 加载的就是这份，不存在"加载到旧备份"。

## §2 回执原文（一字不改）

`logs/run10e-step1.txt`，**exit 1**：

```
❌ debug_dump(crafting_recipes) 失败：unknown_skill: [unknown_skill] (HTTP 200) 未知技能“debug_dump”（本 Mod 不认识这个技能名）
```

**注意码名**：是 **`unknown_skill`**（进主线程之前的白名单拒绝），**不是 `not_implemented`**（那才是"技能已登记但没实现"）。Mod 侧 reason 模板原文（`BridgeHost.cs:531-533`）：

```csharp
Status = "unknown_skill",
Reason = $"未知技能“{skill}”（本 Mod 不认识这个技能名）"
```

## §3 证明方式：为什么是"白名单漏登记"，而不是装错文件/没编进去

1. **拒绝点**在 `mod/AgentFarm.Bridge/BridgeHost.cs:520-535`：`if (!Skills.IsKnownSkill(skill)) { …unknown_skill… }` —— 之后才会 `Skills.ClampTimeoutFor(...)` / `Skills.Create(...)`，**分发代码根本没被调用**。
2. **白名单**只有一处：`mod/AgentFarm.Bridge/Skills.cs` 的 `private static readonly HashSet<string> KnownSkills`（`IsKnownSkill` :802）。**冻结提交 `063351d` 里这个表只有 19 个名字**：
   `noop, move_to, dismiss_modal, move_to_location, load_save, quit_game, interact, use_tool, select_item, plant, sleep, buy, sell` + 规划中 `exit_building, harvest, pickup_debris, collect_machine, refill_watering_can, talk`
   ⇒ **`debug_dump` / `add_missed_recipes` 未登记**；`upgrade_tool` / `pickup_tool` / `craft_item` / `place_object` / `machine` 也都没登记。
3. **不是"没编进 dll"**：同提交里 `Skills.Create` 已有 `case "debug_dump": case "add_missed_recipes":`（`Skills.cs:99-102` / `:454-456`）；类型 `DebugDumpSkill`/`AddMissedRecipesSkill` 在装机 dll 与仓库 dll 里都在；按 **UTF-16LE** 规则扫 dll 字面量，`debug_dump`/`add_missed_recipes`/`craft_item`/`crafting_recipes`/`trigger_actions`/`pickup_tool` **装机版与仓库版都命中**（先前用 ASCII 扫全 False 是方法错误：.NET 字符串常量在 #US 堆是 UTF-16LE）。
4. **修复已在 `8f357bd`**（HEAD，2026-10-17 23:36:53，"wip(task-210) 机器技能 feed/collect 在制"）：`Skills.cs:795` 补了 `"upgrade_tool", "pickup_tool", "debug_dump", "add_missed_recipes",` + `"craft_item", "place_object", "machine",`，并给该表加了自述注释——「⚠️ 必须与 `Skills.Create` 的 case 逐字同步：`BridgeHost.ServeExec` 在进主线程之前就按这张表把不认识的技能一律 `unknown_skill` 拒掉。task-205/213/210 的真机事故教训：Create 里加了 case 但忘了这里 ⇒ 装机后才炸。」
5. **时间线（根因）**：`063351d` freeze **23:21:03** → 装机 dll **23:20:40**（由 `063351d` 构建）→ **`8f357bd` 23:36:53 才提交修复** ⇒ 装机版天生没有它；仓库 Release 重建 dll **23:36:04 / 269312 B / `1FDE5F70…`** 才含修复，但**未 deploy**。
6. 可复跑：`python scratch\_t214_vercheck.py`（只读）⇒ `logs/run10e-dll-vercheck.json`（两侧 dll/manifest 的 size/mtime/SHA256、UTF-16LE 字面量探针、`health`）。

## §4 后续（等 0.7.38 重冻结装机后原样重跑）

1. 0.7.38 将包含：`8f357bd` 的白名单修复 + task-216（F3 取回死锁）+ task-210（机器链，若交付）+ **结构性护栏**（自检断言：`Create` 每个 case 名必须 ∈ `KnownSkills`）。
2. 装好后 Lead 发我五文件指纹；我先发**一发只读验活**：`debug_dump --table crafting_recipes --key Furnace` —— 只要不再 `unknown_skill`（哪怕 Furnace 不在表里）即证明分发通了。
3. 然后按本卡原序重跑：① `crafting_recipes`（含 `--limit 2000` 全表复核）② `trigger_actions` 全量 ③ **`add_missed_recipes` 只调一次** ④ 复核条数 ⑤ SMAPI 冻结 + 存档四条 + 优雅退出。
4. 判据与交付同原卡（`docs/_run10-furnace-probe.md` §2/§3/§4 的真机数据 + 结论二选一）。

## §5 存档与 SMAPI 前后（本次收尾）

**存档四条 —— 退前 / 退出后（退出本身零写入）**：

| 文件 | 退前 | 退出后 |
| --- | --- | --- |
| `Wahaha_450799035` | **4383128 B / 2026-10-17 23:38:17.154** | 同左（逐字未变） |
| `SaveGameInfo` | 29605 B / 23:38:17.251 | 同左 |
| `Wahaha_450799035_old` | 4417243 B / 12:09:48.738 | 同左 |
| `SaveGameInfo_old` | 29567 B / 12:09:48.842 | 同左 |

**SMAPI 窗口（退出后复制，字节一致）**：`logs/run10e-smapi-window.txt` = **77248 B / 439 行 / SHA256 `010AFBC786D64D411D2D283120A266F7134B97A6E0D3583EC3EFA7630FFD5587` / dst mtime 23:50:26.221 / `BYTE_IDENTICAL=True`**。尾部原文：

```
[23:50:26 INFO  AgentFarm Bridge] POST /v1/exec → 200 · 5ms · worldSeq=231
[23:50:26 TRACE game] Disconnected: ClosedGame
[23:50:26 TRACE SMAPI] Disposing...
[23:50:26 INFO  AgentFarm Bridge] 已删除发现文件 …\StardewValley\AgentFarm\bridge.json。
[23:50:26 TRACE SMAPI] Disposing the content coordinator.
```

**优雅退出核对**（`python tools\stop-game.py`，exit 0，回执 `✅ 游戏已退出（原 pids=[11104]）`）：`StardewModdingAPI` 进程 **0** / `bridge.json` **已删**（`Test-Path=False`）/ 17890 **无 LISTENING**（仅 2 条 `TIME_WAIT`）/ 存档四条退出前后**逐字未变**。

## §6 本次未调用任何游戏方法 —— 但纠正一条："存档逐字节未变"不成立

- **本卡对游戏方法的调用 = 0**（`debug_dump` 被白名单拒在主线程之前，`add_missed_recipes` 一次没发）⇒ 卡面本身没有改动世界。
- **但存档确实变了**：主档 `4417243 B / 12:09:48.738` → **`4383128 B / 23:38:17.154`**，两份主档里的 `money`：**2268 → 2042（−226g）**。变化发生在 **23:38:17**，即游戏在**无人值守**状态下被自己的 **2:00 强制昏睡**（10% 医疗费）结算并落盘 —— 正是你警告的那条事故（2268 × 10% ≈ 226.8 → 扣 226g）；`_old` 保留的 12:09:48 那份就是被覆盖前的旧主档。**这一次不是我的动作造成的，但我必须如实记录**：它是"游戏开着不动"的代价，也是本卡收尾必须立刻退出的原因。
- 退出动作本身：退出前后四条存档读数**完全相同**（§5）⇒ `stop-game.py` 的 `Game1.quit` 路径没有触发额外落盘。
