# 失焦暂停门：`pauseWhenOutOfFocus` 的 IL 定位报告（SDV 1.6.15 / 只读分析）

分析对象：`D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley\Stardew Valley.dll`
（游戏运行中被锁 → 只读复制到 `%TEMP%\ooffprobe\sv\Stardew Valley.dll`，6268416 B）
程序集版本：`1.6.15.24356`，ImageRuntime `v4.0.30319`；dotnet 6.0.428。
工具：临时工程 `%TEMP%\ooffprobe\Probe26.csproj` + 自写 IL 扫描器 `%TEMP%\ooffprobe\Probe26.cs`（反射枚举全部类型/方法，自建 opcode 表按 `OpCode.OperandType` 推操作数长度）。
未修改仓库任何文件（本报告是本次唯一写入），未写游戏目录，未启动游戏/未抢焦点。

---

## 结论（Q4）：选 **A**

门就是 `StardewValley.Game1._update(GameTime)` 内 `IL_0466` 读取的 **`Game1.options.pauseWhenOutOfFocus`**，它在**每一帧**被重新读取，且该字段是普通 public 实例字段（无 `static`、无特性），**Mod 可以合法改**。

现有 Mod 修复无效的原因是**时机**：`mod\AgentFarm.Bridge\ModEntry.cs:52-76` 在 `GameLaunched` 时把它置 false（那一刻 `Game1.options` 刚由 `Game1.Initialize()` 新建，值为 true，所以那一次赋值确实生效），但**读档时 `Game1.options` 被整个换成存档文件里反序列化出来的 Options 实例**（`SaveGame+<getLoadEnumerator>d__101.MoveNext()` `IL_1526`→`IL_1530`），而该存档实例里 `pauseWhenOutOfFocus` 是 `true`（存档文件实测值）。GameLaunched 的修改因此被覆盖，且此后没有任何代码把它改回 false。

**部署约束不必是"窗口必须在前台"**：只要在 Options 实例被换掉之后（每帧兜底即可）重新置 false，失焦时 `_update` 就会走到 `IL_0481` 的主循环，时钟与 `PathFindController` 都会照常运行。

---

## Q1：`pauseWhenOutOfFocus` 被哪些方法读取

对全程序集做成员引用扫描（`scan-member pauseWhenOutOfFocus`），命中 **恰好 4 处**：

| # | 宿主方法 | 元数据 token | 关键 IL | 语义 |
|---|---|---|---|---|
| 1 | `StardewValley.Game1._update(Microsoft.Xna.Framework.GameTime)` | `0x06000B00` | `IL_0466: ldfld Boolean pauseWhenOutOfFocus` | **唯一的运行时读取点**（游戏逻辑门） |
| 2 | `StardewValley.Options.setToDefaults()` | `0x060013B1` | `IL_0080: ldc.i4.1` / `IL_0081: stfld Boolean pauseWhenOutOfFocus` | 写入默认值 **true** |
| 3 | `StardewValley.Options.changeCheckBoxOption(Int32 which, Boolean value)` | `0x060013B4` | `IL_013A: stfld Boolean pauseWhenOutOfFocus` | 选项菜单勾选框写入 |
| 4 | `StardewValley.Options.setCheckBoxToProperValue(StardewValley.Menus.OptionsCheckbox checkbox)` | `0x060013C3` | `IL_0178: ldfld Boolean pauseWhenOutOfFocus` | 纯 UI 回显 |

字段元数据（`field-info StardewValley.Options`）：

```
Boolean pauseWhenOutOfFocus   static=False   attrs=[]
```

即**既没有 `[DontLoadDefaultSetting]` 也没有 `[XmlIgnore]`**。对照：同一类型里 `ipConnectionsEnabled / enableServer / enableFarmhandCreation / gamepadMode / singlePlayerBaseZoomLevel / localCoopBaseZoomLevel / singlePlayerDesiredUIScale / localCoopDesiredUIScale / serverPrivacy` 共 9 个字段带 `[DontLoadDefaultSetting]`。**这一点是 Q3 的关键**：`Options.LoadDefaultOptions()` 用反射逐字段回填，会跳过带这两个特性的字段，但**不会**跳过 `pauseWhenOutOfFocus`。

读到 true / false 各自跳过了什么 → 见 Q2。

---

## Q2：跳过"推进时间 + 更新角色/控制器"的是哪一个分支

门在 `Game1.Update` 的子方法 `Game1._update` 里，是一段**提前 `ret`**（方法体最开始，早于 `Game1.ticks++`、早于一切世界更新）：

```
StardewValley.Game1._update(GameTime gameTime)   [token 0x06000B00]

IL_0444: ldsfld         Boolean paused                                   // Game1.paused
IL_0449: brtrue.s       -> IL_045A
IL_044B: ldarg.0
IL_044C: call           Boolean get_IsActiveNoOverlay()
IL_0451: brtrue.s       -> IL_0481                                       // 窗口激活 → 直奔主循环
IL_0453: ldsfld         Boolean releaseBuild                             // StardewValley.Program
IL_0458: brfalse.s      -> IL_0481
IL_045A: call           StardewValley.Options get_options()
IL_045F: brfalse.s      -> IL_0474                                       // options == null → 也暂停
IL_0461: call           StardewValley.Options get_options()
IL_0466: ldfld          Boolean pauseWhenOutOfFocus                      // ★ 唯一的门
IL_046B: brtrue.s       -> IL_0474                                       // true → 去暂停分支
IL_046D: ldsfld         Boolean paused
IL_0472: brfalse.s      -> IL_0481                                       // false → 直奔主循环
IL_0474: ldsfld         Byte multiplayerMode
IL_0479: brtrue.s       -> IL_0481
IL_047B: call           Void UpdateChatBox()
IL_0480: ret                                                             // ★ 整个世界逻辑被跳过
IL_0481: ...（主循环从这里开始）
```

等价 C#：

```csharp
if (Game1.paused || (!this.IsActiveNoOverlay && Program.releaseBuild))
{
    if (Game1.options == null || Game1.options.pauseWhenOutOfFocus || Game1.paused)
    {
        if (Game1.multiplayerMode == 0) { Game1.UpdateChatBox(); return; }   // IL_0480
    }
}
// IL_0481 起：完整世界更新
```

判定的字段**是 `Game1.options.pauseWhenOutOfFocus`**（不是 `Game1.game1.IsActive`）：`IsActiveNoOverlay`/`releaseBuild` 只决定"是否进入这个 if"，而"进入后是否真的 return"由 `pauseWhenOutOfFocus` 决定。

旁证：`StardewValley.Program..cctor()` `[0x0600140D] IL_0007: stsfld Boolean releaseBuild`；运行时读值 `StardewValley.Program.releaseBuild = True`（release 版恒为 true）。因此 `窗口失焦 && !paused` 时：`pauseWhenOutOfFocus=true → ret`，`=false → IL_0481`。

**被 `IL_0480` 跳掉的东西（全都在 `IL_0481` 之后）**：

- `IL_04AB: stsfld Int32 ticks`（`Game1.ticks++`）
- `IL_04B8: get_IsActiveNoOverlay()` — 只守 `checkForEscapeKeys()`
- `IL_1013: call Void UpdateOther(GameTime)`
- `IL_12C3: call Void UpdateGameClock(GameTime)` ← 世界时钟在这里
- `IL_12D1: call Void UpdateLocations(GameTime)` ← 角色/控制器在这里

**调用链证据（时钟）**

- `Game1.Update` `[0x06000AFC]`：`IL_0005 call BeforeGameUpdate()`、`IL_004E call Void _update(GameTime)`（SMAPI 的 `UpdateTicked` 挂在 `Game1.Update` 外层，所以失焦时事件照派发、门在更里面——与"ticks 仍在涨"的事实一致）。
- `Game1.UpdateGameClock(GameTime)` `[0x06000B3B]`：
  - `IL_0001: call Boolean shouldTimePass(Boolean)` → `brfalse IL_0028`（这解释了为什么 `shouldTimePass()` 返回 true 却仍不走表：它通过了，但根本没被调用）
  - `IL_0008: call Boolean get_IsClient()` → `brtrue IL_0028`
  - `IL_0023: stsfld Int32 gameTimeInterval` ← 用 `time.ElapsedGameTime.Milliseconds` 累加，超过阈值后 `IL_01EB: call Void performTenMinuteClockUpdate()`；`panMode` 时 `IL_01E5: stsfld gameTimeInterval`(0) 后 ret。
  - `UpdateGameClock` 的全部调用者只有 `Game1._update` 的 `IL_12C3` 和 FairyEvent / WitchEvent / WorldChangeEvent 的 `tickUpdate`。
- `Game1.performTenMinuteClockUpdate()` `[0x06000B39]` 只是 `Game1.hooks.OnGame1_PerformTenMinuteClockUpdate(action)`；`ModHooks.OnGame1_PerformTenMinuteClockUpdate(Action)` `[0x060024D3]` 体为 `IL_0000 ldarg.1; IL_0001 callvirt Void Invoke(); IL_0006 ret`（SMAPI 覆盖它来发事件）。真正逻辑在 `Game1+<>c.<performTenMinuteClockUpdate>b__738_0()` `[0x06003D11]`：`IL_000E ldc.i4.0` / `IL_000F stsfld Int32 gameTimeInterval`（**同步清零**）、`IL_0014 call get_IsMasterGame()` 为真才 `IL_001B-IL_0023 timeOfDay += 10`，再 `IL_004F` 用 `Min(2600)` 夹取。

**调用链证据（角色 / PathFindController）**

`_update`（IL_0481 之后）→ `UpdateOther` / `UpdateLocations` `[0x06000B37]`（`IL_0035 GameLocation.UpdateWhenCurrentLocation`、`IL_0059 GameLocation.updateEvenIfFarmerIsntHere`）→ `GameLocation.updateEvenIfFarmerIsntHere` `IL_0038 GameLocation.updateCharacters` → `StardewValley.Farmer.Update(GameTime, GameLocation)` `[0x06000953]`：`IL_0917: callvirt Boolean update(GameTime)`（即 `PathFindController.update`）/ `StardewValley.Character.update(...)` `[0x0600056E] IL_013D`。

**`_update` 内其它 `IsActive` 点（都不是世界门，已逐一核对）**

- `IL_07AC: call Boolean get_IsActive()` → `brfalse IL_0EA7`：只守键鼠输入处理。
- `IL_11F6: call Boolean get_IsActiveNoOverlay()`：守卫 `UpdateControlInput`，但它有旁路——

```
IL_11E0: call  Boolean get_globalFade();        brtrue  -> IL_120B
IL_11E7: ldsfld Boolean freezeControls;         brtrue  -> IL_120B
IL_11EE: call  IClickableMenu get_activeClickableMenu(); brtrue -> IL_120B
IL_11F5: ldarg.0
IL_11F6: call  Boolean get_IsActiveNoOverlay(); brtrue  -> IL_1204
IL_11FD: ldsfld StardewValley.Util.IInputSimulator inputSimulator; brfalse -> IL_120B
IL_1204: ldarg.0 / IL_1205: ldarg.1
IL_1206: call  Void UpdateControlInput(GameTime)
```

即 **`Game1.inputSimulator != null` 时，失焦也会走 `UpdateControlInput`**。这条与 `pauseWhenOutOfFocus` 无关，但对"模拟按键"类自动化是一个独立的旁路点（备注，不影响本次结论）。

---

## Q3：`Game1.options` / `pauseWhenOutOfFocus` 会不会被重新赋值

`Game1.options` 是**属性**而非字段：

- `StardewValley.Game1.get_options()` `[0x06000AB6]` = `ldsfld StardewValley.Game1.game1; ldfld StardewValley.Options instanceOptions; ret`
- `StardewValley.Game1.set_options(StardewValley.Options)` `[0x06000AB7]` = `game1.instanceOptions = value; ret`

⇒ **换掉整个 Options 实例 == 换掉这个开关**。`set_options` 的全部调用点（扫描结果）：

| 调用点 | 触发时机 | 新实例的 `pauseWhenOutOfFocus` |
|---|---|---|
| `Game1.Initialize()` `IL_0037`（`newobj` 于 `IL_0032`） | 启动 | `Options..ctor()` → `setToDefaults()` → **true** |
| `Game1.loadForNewGame(Boolean loadedGame)` `IL_0158` | 新游戏 | 有守卫：`IL_0150 ldarg.1; IL_0151 brtrue.s -> IL_016C`，**仅 `loadedGame==false`** 才 `newobj IL_0153` + `LoadDefaultOptions IL_0162` → true/文件值 |
| `Game1.ResetGameStateOnTitleScreen()` `IL_046C`（`newobj IL_0467`） | 回标题界面 | 新 `Options`（跨替换只保留 `gamepadControls`+`snappyMenus`，**不**调 `LoadDefaultOptions`）→ **true** |
| `SaveGame+<getLoadEnumerator>d__101.MoveNext()` `IL_1526`→`IL_1530` | **读存档** | `IL_1526 ldsfld SaveGame loaded; IL_152B ldfld StardewValley.Options options; IL_1530 call set_options` → **直接装入存档里的 Options 实例**（值 = 存档文件里的值）|
| 同上 `IL_15E7`（`newobj IL_15E2` + `LoadDefaultOptions IL_15F1`） | 读存档且 `Game1.options == null`（`IL_15DB get_options; IL_15E0 brtrue`） | true / default_options 文件值 |
| `GameRunner.LoadInstance` `IL_0061` | 分屏实例 | — |
| `Menus.FarmhandMenu.<loadClientOptions>g__LoadOptions|16_0()` `IL_0020` | 分屏联机 | — |

- `StardewValley.Options..ctor()` `[0x060013A9]`：`IL_0376: call Void setToDefaults()` ⇒ **任何 `new Options()` 之后该字段必为 true**。
- `StardewValley.Options.LoadDefaultOptions()` `[0x060013AB]`：`IL_0005 call get_IsMainInstance` 为假直接 ret；用 `GetFilePathForDefaultOptions()`（`GetAppDataFolder(null,true) + "default_options"`，`IL_0007-IL_000C` 见 `ldstr "default_options"`）反序列化到临时实例（`IL_002F stloc.0`），再 `GetFields(BindingFlags=20)` 反射逐字段 `SetValue`，跳过带 `[DontLoadDefaultSetting]` / `[XmlIgnore]` 的字段 ⇒ `pauseWhenOutOfFocus` **会被 `default_options` 文件里的值覆盖**。
- `Options.LoadDefaultOptions` 的全部调用点只有两处：`Game1.loadForNewGame` `IL_0162`（仅新游戏）与 `SaveGame+<getLoadEnumerator>` `IL_15F1`（仅 `options==null`）。**标题菜单不调它。**
- `Options.SaveDefaultOptions()` `[0x060013AC]`（写 `default_options`）调用者：`Menus.ExitPage.receiveLeftClick` `IL_0035`、`Menus.GameMenu.cleanupBeforeExit` `IL_0017`、`SaveGame+<getLoadEnumerator>d__101.MoveNext()` `IL_162F`（**读完档就把当前 Options 写回 `default_options`**）。
- 存档写入侧：`SaveGame+<getSaveEnumerator>d__94.MoveNext()` `[0x06003F97]`：

```
IL_04FC: dup
IL_04FD: call  StardewValley.Options get_options()
IL_0502: stfld StardewValley.Options options        // SaveGame.options = Game1.options（同一实例）
```

⇒ 存档里那份 Options 就是**存档那一刻的 `Game1.options`**。

### 文件实测（只读）

| 文件 | mtime | `<pauseWhenOutOfFocus>` |
|---|---|---|
| `%APPDATA%\StardewValley\default_options` | **2026/10/11 18:03:20**（本次运行中，由读档 `IL_162F` 写入） | **true** |
| `%APPDATA%\StardewValley\startup_preferences` | 2026/10/11 18:02:56 | false |
| `%APPDATA%\StardewValley\startup_preferences.bak-20261005-030642` | 2026/10/5 3:06:42 | true |
| `%APPDATA%\StardewValley\Saves\Wahaha_450799035\Wahaha_450799035` | 2026/10/5 0:14:11 | **true** |
| `...\Wahaha_450799035_old` | 2026/10/5 0:01:53 | true |
| `SaveGameInfo` / `SaveGameInfo_old` | — | 无该元素 |

（`"startup_preferences"` 字符串在程序集里只出现在 `StardewValley.StartupPreferences..cctor()` `[0x060014AB] IL_0000`；全程序集**没有** `"options.json"` 字符串。）

### 完整因果链（这就是"Mod 改了却没用"的原因）

1. 启动：`Game1.Initialize()` → `new Options()` → `setToDefaults()` → **true**；随后 SMAPI 发 `GameLaunched`，Mod 置 **false**（此刻生效）。
2. 玩家读档：`SaveGame+<getLoadEnumerator>d__101.MoveNext()` `IL_1526-IL_1530` 把**存档里的 Options 实例**装进 `Game1.options`，其 `pauseWhenOutOfFocus = true`（存档实测 true）→ **Mod 的修改被静默覆盖**。
3. 同一段代码 `IL_162F` 立刻 `SaveDefaultOptions()`，把 true 写回 `default_options`（mtime 18:03:20 与本次读档时刻吻合）。
4. 此后每帧 `Game1._update`：失焦 → `IL_0444`/`IL_044C` 进入分支 → `IL_0466` 读到 true → `IL_0480 ret`，时钟与角色更新全部不发生。
5. 视窗恢复激活 → `IL_0451 brtrue IL_0481`，跳过整个暂停块（**与 `pauseWhenOutOfFocus` 无关**），主循环立即恢复。这与"一恢复焦点就正常"的观察完全一致。
6. 回到标题：`Game1.ResetGameStateOnTitleScreen()` `IL_046C` 再换一个 new Options → 又变 true。
7. 选项菜单里手动取消勾选会经 `changeCheckBoxOption` `IL_013A` 写 false，但下一次读档/回标题又会被覆盖。

---

## Q4：结论与修复方案

**选 A。** 门 = `Game1._update` 内 `IL_0466` 读取的 `Game1.options.pauseWhenOutOfFocus`；它是 public 实例字段，且**每帧**通过 `get_options()`（`IL_0461`/`IL_0466`）重新读取，Mod 完全可改。失效是**时机**问题（读档/回标题整体替换 Options 实例），不是"无法改变的状态"。

推荐修复（按稳健度排序）：

1. **【推荐，零 Harmony，可证明足够】** 每帧兜底归一化。放在已有的 tick 回调里（`mod\AgentFarm.Bridge\ModEntry.cs` 已在 `helper.Events.GameLoop.GameLaunched` 挂过回调，可再加 `helper.Events.GameLoop.UpdateTicked`）：

   ```csharp
   if (Game1.options != null && Game1.options.pauseWhenOutOfFocus)
       Game1.options.pauseWhenOutOfFocus = false;
   ```

   理由（IL 层面）：门在 `IL_0461-IL_0466` 每帧重新 `get_options()` + `ldfld`，所以**只要上一帧末把它置 false，本帧的 `_update` 就一定越过 `IL_0480` 走到 `IL_0481`**；SMAPI 的 `UpdateTicked` 由 `Game1.Update` `IL_0005 BeforeGameUpdate` 触发（在 `_update` 之前），因此最坏只有 1 帧延迟，与 SMAPI 事件顺序、与 `Options` 何时被替换都无关。代价：用户手动在选项菜单重新勾选会被覆盖（对自动化场景可接受）。
2. **【更精确，需 Harmony】** `[HarmonyPatch(typeof(Game1), "set_options")]` 的 postfix（以及在 `Options.LoadDefaultOptions`/`Game1.ResetGameStateOnTitleScreen` 之后）里置 false，做到"实例一换就归一化"；配合 (1) 作为兜底最稳。
3. **【不要只靠事件】** 只挂 `SaveLoaded` / `ReturnedToTitle` / `DayStarted` 有顺序风险（`set_options` 发生在读档协程内部、与 SMAPI 事件的相对次序不是本报告证明的内容）；方案 1 不依赖这些假设。

### 部署注意事项（即便修好 `pauseWhenOutOfFocus`）

- `Game1.paused`（打开任何菜单/暂停菜单）仍会走 `IL_0444→IL_0480 ret` ⇒ **自动化期间不要打开菜单**。
- `get_activeClickableMenu() != null` / `freezeControls` / `globalFade` 会挡住 `UpdateControlInput`（`IL_11EE`/`IL_11E7`/`IL_11E0`）；`PathFindController` 类移动不受这些影响，但**模拟键鼠输入**受影响。若需失焦下模拟输入，可关注 `Game1.inputSimulator`（`IL_11F6-IL_1202` 的旁路），本次未展开。
- 改这个字段等于关掉"失焦暂停"，游戏在后台会持续推进世界（作物、NPC、体力/时间），这是预期行为，但会与"挂机不动"的旧假设冲突。

### 与既有实测事实的一处矛盾（需重测，不影响本结论）

代码里**找不到任何"补时间 / catch-up"机制**：`gameTimeInterval` 只在 `UpdateGameClock`（`IL_0023`）里累加，而失焦时 `UpdateGameClock` 根本没被调用；`performTenMinuteClockUpdate` 还会在 `IL_000F` 把它同步清零。因此"停滞 12 s 后 12 s 内补了 +60 min（6 拍）"无法用现有代码解释。补充：`runtime.ticks` 是 **Mod 侧计数器**（`mod\AgentFarm.Bridge\BridgeHost.cs:358` `Ticks = this._dispatcher.Tick`，SMAPI `UpdateTicked` 计数），不是 `Game1.ticks`，所以"ticks 在涨"不能证明 `_update` 越过了 `IL_0480`。
最小验证实验：失焦 30 s 期间每 tick 记录 `Game1.gameTimeInterval` 与 `Game1.timeOfDay`（预期：两者都恒定不变），恢复焦点后按 100 ms 采样（预期：每约 7000 ms 才 +10 分钟，无跳变）。若观察到补时间，再单独定位（可能是 MonoGame 单帧 `ElapsedGameTime` 尖峰）。

---

## 复现方式（全部只读）

```powershell
# 1) 只读复制被锁的 dll
$t="$env:TEMP\ooffprobe"; New-Item -ItemType Directory -Force $t\sv | Out-Null
Copy-Item "D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley\Stardew Valley.dll" "$t\sv\" -Force
# 2) 临时工程（本次未放入仓库）
Copy-Item "<repo>\tools\il-probe\*" $t -Recurse -Force      # Probe26.cs / Probe26.csproj
$env:SVDLL = "$t\sv\Stardew Valley.dll"                     # 必须用临时副本；Probe26 另有 SVDIR 回退
dotnet build -c Release $t\Probe26.csproj
# 3) 扫描
dotnet $t\bin\Release\Probe26.dll scan-member  pauseWhenOutOfFocus    # Q1：4 处命中
dotnet $t\bin\Release\Probe26.dll field-info   StardewValley.Options  # Q1：无 [DontLoadDefaultSetting]/[XmlIgnore]
dotnet $t\bin\Release\Probe26.dll dump         "StardewValley.Game1" "_update" 2500   # Q2：IL_0444-IL_0481
dotnet $t\bin\Release\Probe26.dll callers      StardewValley.Game1  set_options       # Q3：6 个替换点
dotnet $t\bin\Release\Probe26.dll callers      StardewValley.Options LoadDefaultOptions
dotnet $t\bin\Release\Probe26.dll dump "SaveGame\+<getLoadEnumerator>d__101" "MoveNext" 2500   # IL_1526-1530 / 162F
dotnet $t\bin\Release\Probe26.dll dump "SaveGame\+<getSaveEnumerator>d__94"  "MoveNext" 2500   # IL_04FD-0502
# 4) 文件实测
$app="$env:APPDATA\StardewValley"
[regex]::Match((Get-Content "$app\default_options" -Raw),'<pauseWhenOutOfFocus>[^<]*</pauseWhenOutOfFocus>').Value
[regex]::Match((Get-Content "$app\Saves\Wahaha_450799035\Wahaha_450799035" -Raw),'<pauseWhenOutOfFocus>[^<]*</pauseWhenOutOfFocus>').Value
```

## 下一步建议

1. 按 Q4 方案 1 在 `mod\AgentFarm.Bridge` 增加 `UpdateTicked` 兜底（每帧把 `Game1.options.pauseWhenOutOfFocus` 置 false），并把"读到 true 就改"的日志降为只在状态变化时打一条，避免刷日志。
2. 加一条自检：`bridge.health.windowActive == false` 期间断言 `Game1.timeOfDay` 仍在推进（可用现有 `BridgeHost.cs:262` 的 `Game1.game1?.IsActive`）。
3. 顺带重测"失焦是否真的补时间"（见上文最小实验），据此修正既有实测快照；同时把 `runtime.ticks` 的语义（Mod 侧计数，非 `Game1.ticks`）写进文档，避免再次误判。
