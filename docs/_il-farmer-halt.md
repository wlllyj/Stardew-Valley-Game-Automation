# IL 实证 · `Farmer.Halt()` / `isCollidingWithWarp` / `PathFindController.update`

> 工具：`tools\il-probe\`（Probe26）。运行示例：
> ```
> cd tools\il-probe
> dotnet run -c Release -- "D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley" "StardewValley.Farmer|Halt"
> ```
> 游戏版本 **1.6.15**（`Stardew Valley.dll`）。
>
> ⚠️ **本文件里的结论是用"修掉静默漏打 bug 之后"的探针重打的**（见 `docs\00-开发日志.md` 条目 017）。
> 旧版探针会丢掉所有无操作数指令（`ldarg`/`ldloc`/`stloc`/`ret`…），据此得出的"某处没有 `ret`"
> 这类**否定性结论不可信**。

---

## 1. `StardewValley.Farmer.Halt()` —— "停下来"到底做了什么

```
--- StardewValley.Farmer.Halt() ---
  IL_0000: ldarg.0
  IL_0001: call           StardewValley.FarmerSprite get_FarmerSprite()
  IL_0006: callvirt       Boolean get_PauseForSingleAnimation()
  IL_000B: brtrue.s       -> IL_0023                       // 单帧动画中 ⇒ 跳过 base.Halt()
  IL_000D: ldarg.0
  IL_000E: call           Boolean isRidingHorse()
  IL_0013: brtrue.s       -> IL_0023                       // 骑马 ⇒ 跳过
  IL_0015: ldarg.0
  IL_0016: call           Boolean get_UsingTool()
  IL_001B: brtrue.s       -> IL_0023                       // 正在用工具 ⇒ 跳过
  IL_001D: ldarg.0
  IL_001E: call           Void Halt()                      // = base.Halt()（Character.Halt：内含 controller = null / 停动画）
  IL_0023: ldarg.0
  IL_0024: ldfld          System.Collections.Generic.List`1[System.Int32] movementDirections
  IL_0029: callvirt       Void Clear()                     // ★ 无条件清空移动方向（不受上面三个条件影响）
  IL_002E: ldarg.0
  IL_002F: ldfld          Boolean isEmoteAnimating
  IL_0034: brtrue.s       -> IL_0044
  IL_0036: ldarg.0
  IL_0037: call           Boolean get_UsingTool()
  IL_003C: brtrue.s       -> IL_0044
  IL_003E: ldarg.0
  IL_003F: call           Void stopJittering()
  IL_0044: ldarg.0
  IL_0045: call           Microsoft.Xna.Framework.Vector2 get_Zero()
  IL_004A: stfld          Microsoft.Xna.Framework.Vector2 armOffset
  IL_004F: ldarg.0
  IL_0050: call           Boolean isRidingHorse()
  IL_0055: brfalse.s      -> IL_0073
  IL_0057: ldarg.0
  IL_0058: call           StardewValley.Characters.Horse get_mount()
  IL_005D: callvirt       Void Halt()
  IL_0062: ldarg.0
  IL_0063: call           StardewValley.Characters.Horse get_mount()
  IL_0068: callvirt       StardewValley.AnimatedSprite get_Sprite()
  IL_006D: ldnull
  IL_006E: callvirt       Void set_CurrentAnimation(System.Collections.Generic.List`1[StardewValley.FarmerSprite+AnimationFrame])
  IL_0073: ldarg.0
  IL_0074: callvirt       Boolean IsSitting()
  IL_0079: brfalse.s      -> IL_0081
  IL_007B: ldarg.0
  IL_007C: call           Void ShowSitting()
  IL_0081: ret
```

### 结论（`StepMover.HaltPlayer()` 的依据）
1. **`movementDirections` 的类型是 `List<int>`**（不是老版本的 `Stack<int>`），且 `Halt()` 会**无条件** `Clear()`；
2. 转调基类 `Character.Halt()`（`controller = null`、停动画）**会被三个条件跳过**：单帧动画 / 骑马 / 正在用工具；
3. **全程没有 `CanMove = false`**，也**没有提前返回**（唯一出口是 `IL_0081: ret`）。
   ⇒ 因此 Mod 侧 `HaltPlayer()` 写成三件事都做：`player.Halt()` + `player.controller = null` + `player.movementDirections.Clear()`。

---

## 2. `GameLocation.isCollidingWithWarp(Rectangle position, Character character)` —— 传送触发几何

```
--- StardewValley.GameLocation.isCollidingWithWarp(Rectangle position, Character character) ---
  IL_0000: ldarg.0
  IL_0001: ldfld          Boolean ignoreWarps
  IL_0006: brfalse.s      -> IL_000A
  IL_0008: ldnull
  IL_0009: ret                                             // ignoreWarps ⇒ 直接不判
  IL_000A: ldarg.0
  IL_000B: ldfld          Netcode.NetObjectList`1[StardewValley.Warp] warps
  IL_0010: callvirt       Enumerator GetEnumerator()
  …（遍历）
  IL_0023: ldarg.2                                         // character
  IL_0024: isinst         StardewValley.NPC
  IL_0029: brtrue.s       -> IL_003B                       // NPC 不看 npcOnly
  IL_002B: ldloc.1
  IL_002C: ldfld          Netcode.NetBool npcOnly
  IL_0031: callvirt       Boolean get_Value()
  IL_0036: brtrue         -> IL_0134                       // npcOnly ⇒ 跳过这条 warp
  IL_003B: ldloc.1
  IL_003C: callvirt       Int32 get_X()
  IL_0041: ldarga.s       1
  IL_0043: call           Int32 get_Left()
  IL_0048: conv.r8
  IL_0049: ldc.r8          (64.0)                          // 注：InlineR 操作数本工具尚未解码
  IL_0052: div
  IL_0053: call           Double Floor(Double)
  IL_0058: conv.i4
  IL_0059: beq.s          -> IL_007E                       // warp.X == 矩形左边缘所在格 ⇒ X 通过
  IL_005B: ldloc.1
  IL_005C: callvirt       Int32 get_X()
  IL_0061: ldarga.s       1
  IL_0063: call           Int32 get_Right()
  …            （== Floor(Right/64) 也通过）
  IL_007E: ldloc.1
  IL_007F: callvirt       Int32 get_Y()
  IL_0084: ldarga.s       1
  IL_0086: call           Int32 get_Top()
  …            （== Floor(Top/64) 通过）
  IL_009E: ldloc.1
  IL_009F: callvirt       Int32 get_Y()
  IL_00A4: ldarga.s       1
  IL_00A6: call           Int32 get_Bottom()
  …            （== Floor(Bottom/64) 也通过）
  IL_00BE: ldloc.1
  IL_00BF: callvirt       System.String get_TargetName()
  …（之后按 TargetName 特判 BoatTunnel / VolcanoEntrance 等再返回 warp）
```

### 结论
判定式为：
```
warp.X == Floor(rect.Left/64) || warp.X == Floor(rect.Right/64)
  &&  warp.Y == Floor(rect.Top/64)  || warp.Y == Floor(rect.Bottom/64)
```
1. **`warp.X/Y` 是"玩家像素矩形边缘要碰到的格"（源格）**，不是"玩家要站上去的格"；
2. 所以**源格可以落在图层之外**：真机 FarmHouse→Farm 的源格是 `(3,12)`，而 FarmHouse 所有图层都是 12x12（合法格 x,y∈0..11）——
   玩家是**走出地图边缘**时被抓住传送的（真机回执：`source=[3,12] landing=[64,15] used=[3,12] 7616ms`）；
3. 触发发生在**移动过程**中（`Farmer.MovePositionImpl` 调它），**站着不动永远不触发** —— 这是"门要靠撞"的机制根源。

---

## 3. `PathFindController.update(GameTime)` —— 起点（节选）

修复后的 dump 开头（注意 `ldarg.0` 之类的指令现在都在了）：
```
--- StardewValley.Pathfinding.PathFindController.update(GameTime time) ---
  IL_0001: ldfld          System.Collections.Generic.Stack`1[Microsoft.Xna.Framework.Point] pathToEndPoint
  IL_0006: brfalse.s      -> IL_0015
  IL_0009: ldfld          … pathToEndPoint
  IL_000E: callvirt       Int32 get_Count()
  IL_0013: brtrue.s       -> IL_0017
  IL_0018: ldfld          Boolean NPCSchedule
  IL_001D: brtrue.s       -> IL_0076
  IL_0020: call           Boolean isPlayerPresent()
  IL_0025: brtrue.s       -> IL_0076
  IL_0028: … endPoint.X <= 0 ⇒ 跳过
  IL_0044: ldfld          StardewValley.Character character
  …           character.Position = new Vector2(endPoint.X * 64 + 32, endPoint.Y * 64 + 32)
```
要点：`pathToEndPoint` 是 `Stack<Point>`（Mod 里读 `Count` 判"A* 有没有给出路径"）；路径走完时对 NPC 会把角色**吸附到格心**，对"玩家在场"的情况不走这一支。

---

## 相关
- `docs\00-开发日志.md` 条目 016（落点契约修复）、条目 017（探针 bug）、条目 018（跨地点对线）
- `docs\_il-savegame-load.md`（读档与门的 IL）
- `tools\il-probe\README.md`
