# IL 实证 · 读档（`SaveGame.Load`）与"门"（`getWarpFromDoor`）

> 工具：`tools\il-probe\`（Probe26，**已修掉静默漏打 bug**）。游戏版本 **1.6.15**。
> 运行示例：
> ```
> cd tools\il-probe
> $g = "D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley"
> dotnet run -c Release -- $g "StardewValley.SaveGame|Load"
> dotnet run -c Release -- $g "StardewValley.SaveGame|TryReadSaveFile"
> dotnet run -c Release -- $g "StardewValley.SaveGame+getLoadEnumerator|MoveNext"   # 嵌套迭代器
> dotnet run -c Release -- $g "StardewValley.GameLocation|getWarpFromDoor"
> ```

---

## 1. `SaveGame.Load(String filename)` —— `load_save` 技能的全部依据

```
--- StardewValley.SaveGame.Load(String filename) ---
  IL_0001: call           Void set_gameMode(Byte)                    // Game1.gameMode = 6（加载态）
  IL_0006: ldsfld         StardewValley.LocalizedContentManager content
  IL_000B: ldstr          "Strings\StringsFromCSFiles:SaveGame.cs.4690"
  IL_0010: callvirt       System.String LoadString(System.String)
  IL_0015: stsfld         System.String loadingMessage
  IL_001B: call           System.Collections.Generic.IEnumerator`1[System.Int32] getLoadEnumerator(System.String)
  IL_0020: stsfld         System.Collections.Generic.IEnumerator`1[System.Int32] currentLoader
```

**结论**：`SaveGame.Load(存档名)` = 把游戏切到加载态 + 把 `Game1.currentLoader` 设成加载迭代器。
之后**进度推进完全由游戏主循环负责**（玩家点 Continue 走的是同一条路）。
⇒ 我们**没有**写任何世界状态、没有改角色坐标/金钱/时间、没有伪造键鼠事件；这正是 `load_save` 被判定为"合法操作"的依据。

---

## 2. `SaveGame.TryReadSaveFile(String file, String fileNameSuffix, String& error)` —— 存档路径怎么拼

```
--- StardewValley.SaveGame.TryReadSaveFile(String file, String fileNameSuffix, String& error) ---
  IL_0000: call           System.String GetSavesFolder()
  IL_0005: ldarg.0                                                   // file
  IL_0006: ldarg.0
  IL_0007: ldarg.1                                                   // fileNameSuffix
  IL_0008: call           System.String Concat(System.String, System.String)      // file + suffix
  IL_000D: call           System.String Combine(System.String, System.String, System.String)
                                                                     // Path.Combine(savesFolder, file, file+suffix)
  IL_0012: stloc.1
  IL_0013: ldloc.1
  IL_0014: call           Boolean Exists(System.String)              // File.Exists
  IL_0019: brtrue.s       -> IL_0036
  IL_001B: ldloc.1
  IL_001C: ldstr          ".xml"
  IL_0021: call           System.String Concat(System.String, System.String)
  IL_0026: stloc.1
  IL_0027: ldloc.1
  IL_0028: call           Boolean Exists(System.String)
  IL_002D: brtrue.s       -> IL_0036
  IL_002F: ldarg.2
  IL_0030: call           StardewValley.SaveGame <TryReadSaveFile>g__FileDoesNotExist|99_0(System.String ByRef)
  IL_0035: ret                                                        // ★ 文件不存在 ⇒ 只设置 error，不抛异常
  …
  IL_0039: call           Byte[] ReadAllBytes(System.String)
```

`TryReadSaveFileWithFallback(file, out error, out autoRecovered)` 依次试 `file`、`file + "_old"`、`file + "_STARDEWVALLEYSAVETMP"`。

**结论**：
1. `file` 参数是**存档文件夹名**，路径由游戏拼成 `Saves\<名字>\<名字>`；
2. 一个存档文件夹**有效的判据** = `<名字>` 这个文件存在（`SaveGameInfo` 只是给读档菜单看的）；
3. **文件不存在/损坏时不会抛异常**，只会把错误交给加载界面 ⇒ Mod 侧的 `load_save` 若超时，
   基本等于"存档读不出来 / 加载卡住"，reason 里已写明这一点。

### 真机核对（`%APPDATA%\StardewValley\Saves\Wahaha_450799035\`）
```
SaveGameInfo        23931 bytes
SaveGameInfo_old    24134 bytes
Wahaha_450799035  3310322 bytes   ← 有效性判据看这个
Wahaha_450799035_old
```
> 我自己第一版把判据写成 `<名字>_SaveGameInfo`（**错**），真机列目录即被证伪。教训：**先看现场，再写判据。**

### 附带证伪
- `SaveGame.GetSavesFolder()`、`Program.savesFolder` 在 Mod 侧**不可访问**（api-probe CS0117）⇒
  Mod 采用 SMAPI 的公共入口 `Constants.SavesPath`，再用**游戏自己的判据**复核目录内容。
- `SaveGame.GetSaveGames()`、`Game1.loadingMultiplePlayers`、`Context.IsSaveLoaded`、`Game1.ExitToTitleScreen` 都不存在（CS0117）。

---

## 3. `GameLocation.getWarpFromDoor(Point door, Character character)` —— "门"的解析（农舍回屋）

```
--- StardewValley.GameLocation.getWarpFromDoor(Point door, Character character) ---
  IL_0000: ldarg.0
  IL_0001: ldfld          Netcode.NetCollection`1[StardewValley.Buildings.Building] buildings
  IL_0006: callvirt       Enumerator GetEnumerator()
  …（遍历 buildings）
  IL_0016: ldarg.1
  IL_0017: ldloc.1
  IL_0018: callvirt       Microsoft.Xna.Framework.Point getPointForHumanDoor()
  IL_001D: call           Boolean op_Equality(Point, Point)          // door == b.getPointForHumanDoor()
  IL_0022: brfalse.s      -> IL_0071
  IL_0024: ldloc.1
  IL_0025: callvirt       StardewValley.GameLocation GetIndoors()
  IL_002A: stloc.2
  IL_002B: ldloc.2
  IL_002C: brfalse.s      -> IL_0071                               // 没有室内 ⇒ 继续找
  IL_002E: … ldarg.1.X, ldarg.1.Y
  IL_003B: callvirt       System.String get_NameOrUniqueName()      // 目标地点 = indoors.NameOrUniqueName
  IL_0046: … indoors.warps[0].X
  IL_005D: … indoors.warps[0].Y
  IL_0062: ldc.i4.1
  IL_0063: sub                                                      // 落点 Y = indoors.warps[0].Y - 1
  IL_0066: newobj         Void .ctor(Int32, Int32, String, Int32, Int32, Boolean, Boolean)
  …
  IL_008A: …（之后才是地图 Action/Buildings/Doors 属性层的分支）
```

**结论**（`LocationGraph` 补门边的依据）：
- **建筑的门不是 `loc.warps` 里的 warp**，所以地点图只读 `warps` 会漏边；
- 门格 = `Building.getPointForHumanDoor()`，目标 = `GetIndoors().NameOrUniqueName`，落点 = 室内第一条 warp 的 `(X, Y-1)`；
- 真机核对：农舍门格 `(64,14)`、落点 `(3,11)`（正是室内出口 warp `(3,12)` 的上一格）；
- 门格在墙上，**A\* 到不了**（真机 `unreachable`），而门只在"**移动进门的碰撞判定**"里触发
  （`isCollidingWithWarpOrDoor`）⇒ 站着不动永远不会触发。这就是条目 018 里 `door_push` 存在的理由。

---

## 4. `GameLocation.checkAction(...)` —— "进建筑"走的是**动作**路径（不是碰撞传送）

真机现象（2026-10-11 晚，0.7.0）：站在 `Farm(64,15)` 对着农舍门格 `(64,14)`，
`move_to_location FarmHouse` 报 `hop_failed`；把"朝门走一步"这条给定路径喂给寻路器
（`new PathFindController(Stack<Point>, GameLocation, Character, Point)`，ctor IL 只做字段赋值）
也只在像素上把玩家从 `(4096,976)` 推到 `(4096,963)`（**位移 0,-13**，被墙挡住）——
矩形四角永远进不了门格，**碰撞式触发没有机会发生**。

再看两条事实：
* `Farm` 与 `FarmHouse` 的 `location.doors` **都是空的**（真机 `observe?detail=full` 实测 `doors=[]`）
  ⇒ `GameLocation.isCollidingWithDoors` 遍历的那张字典里根本没有这个门；
* `GameLocation.checkAction` 的 IL（dump 共 2064 行）里遍历 `this.buildings`，调
  `getPointForHumanDoor()` / `getWarpFromDoor(...)` / **`Building.doAction(Vector2, Farmer)`**。

```
  IL_0051: ldfld          Netcode.NetCollection`1[StardewValley.Buildings.Building] buildings
  IL_0061: callvirt       StardewValley.Buildings.Building get_Current()
  IL_007A: callvirt       Boolean doAction(Microsoft.Xna.Framework.Vector2, StardewValley.Farmer)
  …
  IL_0062: callvirt       StardewValley.Warp getWarpFromDoor(Microsoft.Xna.Framework.Point, StardewValley.Character)
```

### 结论（真机验证）
`GameLocation.checkAction(tile, viewport, player)`（**api-probe 实证：3 参重载存在，4 参不存在 CS1501**）
就是"进建筑"的正道：

```
interact((64,14))  →  回执 ok，checkAction 返回 True  →  0.6 秒后玩家在 FarmHouse(3,11)
```
落点 `(3,11)` 与第 3 节推出的 `indoors.warps[0].Y - 1 = 11` **完全一致**。

因此 Mod 里"门"的正确做法是：走到门前那一格 → 调 `checkAction(门格)` → **等地点真的变**
（传送是异步的：`warpFarmer` 先淡出 0.6~2 秒，这期间**不能**下任何"失败"结论，也不要倒计时）。
与 `dismiss_modal` 用 `answerDialogue` 而不按确认键是同一条纪律：**调游戏自己的处理函数，不合成键鼠**。

---

## 相关
- `docs\00-开发日志.md` 条目 016 / 017 / 018
- `docs\_il-farmer-halt.md`
- `tools\api-probe\README.md`、`tools\il-probe\README.md`
