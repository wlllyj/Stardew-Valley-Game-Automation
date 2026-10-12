# `ensure_location` 逐帧 warp 循环取证（task-27）

- 结论一句话：**这是"游戏自身的门格碰撞重发传送 × 淡出被每帧重置"的活锁**——Mod 在传送期间刻意不摘寻路控制器（`StepMover.cs:196-197`、`MoveToLocationSkill.cs:578-580`），游戏的 `PathFindController` 便每帧把玩家往 warp 格里推一次，每次都重新起一次传送并把淡出进度清零，于是挂起的传送**永远落不了地**；直到推动自己停下来，淡出才走完、传送才落地，所以它最终仍然返回 `ok`（run2：7683ms）。
- 性质：**自限风暴**（浪费 ~5 秒 + 313 行日志/次），不是必然死锁；但同一机制存在"一直推着就一直转，直到 30 秒总超时"的退化路径（§5）。
- 本次只读：**没有改任何 `mod\` / `brain\` 代码**，没有起游戏、没有 bump/deploy。

环境：游戏目录 `D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley`，程序集 `Stardew Valley, Version=1.6.15.24356`。

---

## §1 现象与时间线

| 时刻（真实） | 事件 | 证据 |
|---|---|---|
| 22:08:10 | run2 起跑，账本第一条就是 `goto_farm`（t=7.9） | `docs\_run2-evidence.md:357` |
| 22:08:10.6 | 脑侧发出这次 `/v1/exec`（`goto_farm` 的 `ensure_location("Farm")`） | 同上 |
| 22:08:12 → 22:08:18 | SMAPI **L119–L431 连续 313 行** `TRACE game] Warping to Farm`（≈60 次/秒 = 每帧一次） | 同上 |
| 22:08:18 | L432 `POST /v1/exec → 200 · 7683ms · worldSeq=15`（同一次请求） | 同上 |
| 22:22:52（对照） | 一次**正常**传送只打 1 行 `Warping to FarmHouse`（角色被送回床上） | `docs\_run2-evidence.md:335`（SMAPI `[1230]`） |

- `TRACE game] Warping to ...` 的**唯一出处**是 `Game1.performWarpFarmer`（见 §2.3c 的 IL）⇒ 313 行 = `performWarpFarmer` 在 5.2 秒里被重新进入 313 次。正常一次跨地点只需 1 次。
- 同时段 `worldSeq` 不推进、`POST /v1/exec` 一直挂着 ⇒ 不是"多次跳跃"，是**同一次跳**在风暴。
- 脑侧不肯重试、也没有第二个客户端：风暴窗口正好压在 run2 自己这次 `goto_farm` 的 exec 上（`docs\_run2-evidence.md:357` 的排除论证），调用方只能是 Mod 侧的移动技能。

调用链（脑 → Mod）：`brain\agentfarm\farmwork.py:682-701 ensure_location()` → `BridgeClient.move_to_location()` → `/v1/exec` → Mod `mod\AgentFarm.Bridge\MoveToLocationSkill.cs`。调用点示例 `brain\agentfarm\longrun.py:1699-1700`（`goto_farm`）。

---

## §2 状态机（含行号）

### 2.1 一次 `/v1/exec` 的生命周期

- **不是阻塞调用**：桥把请求变成一个技能实例，之后**每 tick 调一次 `Step()`**，直到返回 `Ok`/`Fail`（或脑侧超时）。
- `Step()` 在 `mod\AgentFarm.Bridge\MoveToLocationSkill.cs:239`；首次进来自 `Step()` 顶部 `if (!this._started) return this.Begin();`（243）→ `Begin()`（295-377）。

### 2.2 Mod 侧（`MoveToLocationSkill` + `StepMover`）

阶段枚举 None / Settle / Walk / Push / FinalWalk（约 96-104），`Step()` 分派在 275-284。关键点：

1. **整体超时最先判**（`MoveToLocationSkill.cs:247-255`）：`elapsed >= _timeoutMs` → `Fail("timeout")`。脑侧 `ensure_location` 用 `timeout_ms=30000`（`farmwork.py:682-690`）⇒ 30 秒是这轮风暴的最终兜底。
2. **唯一的一跳成功判据 = 地点真的变了**（`MoveToLocationSkill.cs:257-263`）：`string now = StepMover.CurrentLocationName(); if (now != null && !Same(now, this._observedLocation)) → NoteLocationChange + AfterLocationChange`。⇒ 传送期间（`currentLocation` 还没换）**不可能**判定成功。
3. 模态/过场 → `Fail("ui_modal")`（266-273）。
4. **"已在目标地点"只看 `Game1.currentLocation.Name`**：`Begin()` 317 取 `_startLocation = StepMover.CurrentLocationName()`；355-356 `if (Same(target, this._startLocation)) return this.StartFinalWalk(0);` → 0 跳收尾，`Ok()` 的 reason 是 `已经在 {target}（无需跨地点移动）`（208-210）。
5. **Push 阶段（门口推挤）`TickPush()`（573-620）**：
   - `578-580`：`bool warping = Game1.locationRequest != null; if (warping) return null;` —— **传送期间只是"等"**：既不 `HaltPlayer()`，也不推进下面的帧预算。注释 575-577 明说"任何放弃/换候选的判定都会让回执与事实相反"。
   - `582-601`：`if (this._pushFramesLeft-- <= 0)` → `StepMover.HaltPlayer()` + 记 `door_action` 失败 + 换下一个候选（`_candidateIndex++`）。
   - `604-616`：每 15 帧 `TryDoorAction()`；动作返回 false **且 `Game1.player.controller == null`** 时 `StepMover.PushInto(this._pushTarget, this._hopLocation)`。
   - `553-562 TryDoorAction()` = `Game1.currentLocation.checkAction(new xTile.Dimensions.Location(x,y), Game1.viewport, Game1.player)`。
   - `PushFrames = 180`（115，注释 106-114 写"门口动作最多约 3 秒"，并已知道 `Game1.warpFarmer` 的淡出"地点切换要 ~0.6~2 秒"）。
6. **`StepMover.Tick()`（`mod\AgentFarm.Bridge\StepMover.cs:181`）**：
   - `191-197`：`if (WarpInProgress()) return MoveOutcome.Running();` —— 注释明说"**传送期间一律不下任何结论**"（起因是 2026-10-11 18:5x 真机事故：回执 `blocked / arrivedAt=FarmHouse`，而角色其实已站在 Farm(64,15)）。
     ⚠️ 关键：这里**直接返回、不调 `HaltPlayer()`** ⇒ 游戏给玩家挂的 `PathFindController` **继续留在身上**。
   - `201-208`：地点变了 → `HaltPlayer()` + `MoveOutcome(LocationChanged)`。
   - `285-290 HaltPlayer()` = `Halt()` + `controller = null` + `movementDirections.Clear()`。
   - `297-300 WarpInProgress()` = `Game1.locationRequest != null`。
   - `315-327 PushInto()` = `Game1.player.controller = new PathFindController(path, loc, Game1.player, target)`（单步/短路径）。

### 2.3 游戏侧传送管线（1.6.15，本次取证新发现）

完整链条（每步都有 IL）：

**(a) 触发：门格碰撞，每帧一次**
`Farmer.MovePositionImpl(direction, speedX, speedY, time, viewport)`（`scratch\il-warp-game1.txt:605-649`）：
```
IL_0008: Game1.currentLocation
IL_000E/000F: isCollidingWithWarp(nextPosition(direction), this) → Warp w
IL_0014: stloc.1
IL_0016: brfalse.s -> IL_0071        // 没撞到 warp 就正常走
IL_0019: IsLocalPlayer; IL_001E: brfalse.s -> IL_0071
IL_0020: eventUp 为真 → 节日分支（IL_0027-0065，走 TryStartEndFestivalDialogue）
IL_0067/006A: call Farmer.warpFarmer(Warp, Int32)
IL_006F: ldc.i4.1; IL_0070: ret
```
**这条路径完全不查** `Game1.locationRequest` / 淡出状态 / `CanMove` ⇒ 只要"下一格位置"仍压着 warp 格，就每帧重发一次传送。

**(b) 起传**
`Farmer.warpFarmer(Warp w, Int32 dir)` IL_003B–IL_004E → `Game1.warpFarmer(w.TargetName, w.TargetX, w.TargetY, w.flipFarmer)` → 构造 `LocationRequest` → `Game1.warpFarmer(LocationRequest, …)`。

**(c) `Game1.performWarpFarmer`（`scratch\il-warp-perform.txt`）**
```
IL_003F-IL_0054: log.Verbose("Warping to " + locationRequest.Name)   ← SMAPI 那 313 行的唯一出处
IL_00B8: stsfld Game1.locationRequest      ← 挂起传送，字段是 static
IL_00D5: call Game1.fadeScreenToBlack()
```
**没有任何重入保护**：每调用一次都重新武装一次、并重打一行日志。

**(d) 淡出被清零**
`Game1.fadeScreenToBlack()`（`scratch\il-const.txt`）= `ldsfld screenFade; ldc.r4 0; ldc.i4.1; callvirt FadeScreenToBlack` ⇒ `ScreenFade.FadeScreenToBlack(startAlpha: 0f, stopMovement: true)`：
`globalFade=false; fadeToBlack=true; fadeIn=true;` **`fadeToBlackAlpha = 0`**；`Game1.player.CanMove = false`（`scratch\il-screenfade.txt`）。
⇒ **每重发一次传送，淡出进度就归零一次。**

**(e) 淡出推进**
`ScreenFade.UpdateFadeAlpha`（`scratch\il-fadealpha.txt`，只有 `fadeIn == true` 才走增量支——`FadeScreenToBlack` 正好把 `fadeIn` 置真）：`fadeToBlackAlpha += (Game1.eventUp || Game1.farmEvent ? 0.0008 : 0.0019) * gameTime.ElapsedGameTime.Milliseconds`（`IsDedicatedHost` 时直接置成 `1.2`）。
60fps ⇒ 单遍约 +0.032/帧；而 `fadeToBlack` 期间**每帧会被调用两遍**（`Game1._update` IL_0752 一次，随后同一帧里 `UpdateOther` → `ScreenFade.UpdateFade` IL_00AA 再一次）⇒ 合计 ~0.064/帧 ⇒ 从 0 涨到 1.1 约 **0.29 秒（~17 帧）**；只算单遍则约 0.58 秒（~35 帧）。

**(f) 落地：挂起传送**唯一**的应用点**
- 每帧调用 `ScreenFade.UpdateFade` 的是 `Game1.UpdateOther`：`ILSCAN|StardewValley.BellsAndWhistles.ScreenFade|UpdateFade`（token `0x060038D8`）命中 **唯一调用者 `StardewValley.Game1.UpdateOther` @IL+0x002D**（`Game1.UpdateOther` 又由 `Game1._update` IL_1013 调用）。
- `ScreenFade.UpdateFade`（`scratch\il-updatefade.txt`）：
```
IL_0006: fadeToBlack == false → IL_00AF: ret false       // 不在淡出就什么都不做
IL_001C: (pauseTime != 0 && !eventUp) → IL_00AF: ret false
IL_0022/0027: fadeToBlackAlpha <= 1.1f → IL_007E
IL_002E: Game1.messagePause 为真 → IL_007E
IL_0036: fadeToBlackAlpha = 1f
IL_0040/0046: onFadeToBlackComplete.Invoke()      ← 回调 = Game1.onFadeToBlackComplete
IL_004B: 返回真 → IL_004D/004E: ret true（本次淡出结束）
         返回假 → IL_004F: nonWarpFade=false; fadeIn=false; afterFade?.Invoke(); globalFade=false
IL_007E/0089: fadeToBlackAlpha >= -0.1 → IL_00A8（跳过重置块）
IL_008B-0098: fadeToBlackAlpha = 0; fadeToBlack = false; onFadedBackInComplete?.Invoke()
IL_00A8/00AA: call UpdateFadeAlpha(time)          // ← 每帧的第二遍 alpha 推进
IL_00AF: ret false
```
  ⇒ 风暴期间每帧走的就是 `alpha <= 1.1 → IL_007E → IL_00AA 再推一遍 → ret false` 这条路；只有 `alpha > 1.1` 才会进 IL_0036 那一支去调回调。
  回调的来源：`ScreenFade` 有字段 `private Func<Boolean> onFadeToBlackComplete`，由构造器 `.ctor(Func<Boolean> onFadeToBlack, Action onFadeIn)` 注入（`Game1.Initialize` 里传入 `Game1.onFadeToBlackComplete`，见 `FIND|onFadeToBlackComplete`）。
- `Game1.onFadeToBlackComplete`（`scratch\il-onfade.txt`）才是**真正换地点/落点**的地方：
```
IL_0077: Game1.nonWarpFade 为真 → 跳过整段
IL_0081: ldsfld Game1.locationRequest
IL_0086: brfalse → 没有挂起传送就跳过
IL_0092-00C3: Location 为空时 log.Error("Warp to … failed: location wasn't found or couldn't be loaded.") 并清空
IL_0163: locationRequest.IsRequestFor(currentLocation)   // 已经在目标地点 ⇒ 不再搬
IL_019D-01CF: player.Position = new Vector2(xLocationAfterWarp*64, yLocationAfterWarp*64 - sprite.Height - 32 + 16)
IL_01D4: Game1.viewportFreeze = 0
IL_01DA: currentLocation.resetForPlayerEntry()
IL_01E4: 本地标志 = 1（已落地）
```
  用 `ILSCAN|StardewValley.Game1|locationRequest`（字段 token `0x04000722`，`scratch\il-locreq-scan.txt`）全程序集扫描确认：共 **19 个方法**引用该字段；写方是 `Game1.performWarpFarmer @IL+0x00B9`，逐帧更新管线里真正**应用**（搬人 + 换地点）的只有 `Game1.onFadeToBlackComplete @IL+0x0082`（另外 `Game1.UpdateOther @IL+0x0115` 拿它当"要不要开始昏倒"的守卫，`Farmer.Update @IL+0x0123` / `Farmer.draw @IL+0x006D` 只是读，其余是事件/菜单/多人同步路径）。

⇒ **挂起的传送只有在淡出被允许连续涨到 `alpha > 1.1`（≈0.29 秒、约 17 帧不被打断）时才会落地。**

### 2.4 为什么 Mod 的"等"没防住这个循环

`Farmer.MovePosition`（`scratch\il-pfc.txt:806 行`）：
```
IL_02A7/02A8: get_CanMove
IL_02AD: brtrue -> IL_02C9            // 能走就正常走
IL_02AF: eventUp 为真 → IL_02C9
IL_02B6/02B7: ldfld PathFindController controller
IL_02BC: brtrue -> IL_02C9            // ★ 挂着寻路控制器 ⇒ 即使 CanMove=false 也照走
IL_0307/0328/0349/036B: callvirt MovePositionImpl
```
⇒ 传送把 `CanMove` 设成 false 并**不能**阻止控制器驱动的移动。而 Mod 在传送期间刻意不摘控制器（§2.2-6）⇒ 玩家每帧继续撞门格。

闭环（活锁）：
```
玩家被 PathFindController 推向门格
  → 每帧 Farmer.MovePositionImpl 撞到同一 warp 格
  → 每帧 Farmer.warpFarmer → Game1.performWarpFarmer（打 1 行日志）
  → 每帧 Game1.fadeScreenToBlack() → fadeToBlackAlpha = 0
  → ScreenFade.UpdateFade 的 alpha > 1.1 永不成立
  → Game1.onFadeToBlackComplete 永不被调用
  → 传送永不落地、currentLocation 永不改变
  → MoveToLocationSkill.Step() 257-263 永远判不出"这一跳成功"
  → Push 阶段 578-580 永远只说"还在传送，等着"（且因为提前 return，_pushFramesLeft 也不递减）
  → 回到第一行
```

---

## §3 三候选判定

| 候选 | 判定 | 证据 |
|---|---|---|
| **M1**「"已在目标地点"只看 `currentLocation.Name`，warp 未完成 ⇒ 每帧重发」 | **部分成立，但重发者不是 Mod** | Mod 侧确实只看名字（`MoveToLocationSkill.cs:317 / 355-356 / 258-263`），但 **Mod 从不调用 `Game1.warpFarmer`**（`grep` 整个 `mod\AgentFarm.Bridge` 只命中注释与 `Game1.locationRequest` 读）⇒ 重发来自游戏自身的碰撞路径（§2.3a）。正确表述：Mod 的错误不是"重发传送"，而是**"传送期间不摘控制器、把重发外包给了游戏"** |
| **M2**「`locationRequest != null` 期间无 await/退避，`Step()` 每 tick 照常驱动」 | **成立（变体）** | `MoveToLocationSkill.cs:578-580`（warping → 直接 `return null`，不 Halt、不推进预算）+ `StepMover.cs:196-197`（`WarpInProgress()` → `MoveOutcome.Running()`，**故意不 `HaltPlayer()`**；注释 191-195 把"不下结论"当成了"什么都不做"）。后果即 §2.4 的闭环 |
| **M3**「失败重试无上限、无退避」 | **不成立** | 上限/退避都在：`PushFrames = 180`（115）、到期 `HaltPlayer()` 换候选（582-601）、路线的 `MaxHops`/`MaxReplans`、`Step()` 顶部整体超时（247-255，脑侧 30 秒）。**本次风暴不是重试失控，是"等"本身没有终止条件** |

---

## §4 为什么最终仍然成功

- 推动是**有限**的：单步 `PathFindController` 的路径会走完；`_pushFramesLeft` 在非传送帧递减（`MoveToLocationSkill.cs:582`）；不再有帧往门格推之后，`fadeToBlackAlpha` 就能连续 ~17 帧不被打断地涨到 `>1.1`（≈0.29s）。
- 淡出走完 ⇒ `Game1.onFadeToBlackComplete` 应用挂起传送（§2.3f）⇒ `currentLocation` 真的变成 Farm ⇒ `Step()` 257-263 判"这一跳成功" ⇒ Settle → 后续跳/收尾 ⇒ run2 在 **7683ms** 返回 `ok`（SMAPI L432）。
- ⚠️ 注意 313 帧 > `PushFrames = 180`：风暴期间几乎每帧都处于"传送中"，`_pushFramesLeft` 基本不递减 ⇒ **终止不是靠 PushFrames 到期，而是靠推动自己停下来**。这是静态分析的推论，缺"每帧 `locationRequest` 是否为 null / 玩家是否真在移动"的真机读数（见 §7 未定项）。
- 结论：**自限风暴**——每次约 5 秒、313 行日志、每帧一次淡出重置；不是"必然卡死"。

---

## §5 对 run3 的风险评估

**会复现吗**：大概率。run2 起跑第一次 `goto_farm`（FarmHouse → Farm，正是"门口推挤"路径）就中了；run3 的 preflight 若也走同一条路，会再中一次。

**影响面**：
1. 每次跨门跳多花 ~3–6 秒（run2：7683ms，其中风暴 ~5.2s）。
2. SMAPI 日志被刷几百行 ⇒ run3 的日志行号定位/人工排查会很难受（本次分析就靠行号对齐）。
3. 该窗口内 `worldSeq`/时钟不推进，`POST /v1/exec` 长挂。
4. 退化路径：只要"玩家持续被推在 warp 格上"，风暴不会自己停，**只剩 `Step()` 的 30 秒总超时兜底**（`MoveToLocationSkill.cs:247-255`）⇒ 该 hop 回 `timeout` ⇒ 脑侧 `ensure_location` 记 `failed`（`farmwork.py:691-699`：既可能因 `BridgeError` 失败，也可能因观测未变而判"回执说到了，但观测显示还在 X"）⇒ `goto_farm` 失败但**不会硬卡死**（不是 modality 那种永久卡住）。

**run3 起跑时该盯哪一行判断它是不是元凶**：
> SMAPI 日志里**同一地名**的 `TRACE game] Warping to <地名>` 连续出现 **≥2 次**（正常只出现 1 次），尤其是"2 秒内十几次以上" ⇒ 就是本循环；伴随现象：该 `POST /v1/exec` 耗时数秒（run2=7683ms）、期间 `worldSeq` 不推进。
> 反证：地名每次不同（正常的连续跳跃）、或每个地名只出现 1 次。

---

## §6 修复方向（只写方向，不改代码）

1. **传送期间"停机"而不是"只等"**：`StepMover.Tick` 的 `WarpInProgress()` 分支（`StepMover.cs:196-197`）或 `TickPush` 的 warping 分支（`MoveToLocationSkill.cs:578-580`）里先 `StepMover.HaltPlayer()`，再返回 `Running()`。
   - 要点：**停机 ≠ 下结论**——那句旧注释（191-195）担心的是"误判 blocked"，而摘掉控制器不影响"继续观察"，反而让淡出能走完。
2. **传送期间不重挂控制器**：`MoveToLocationSkill.cs:612-613` 现在只判 `Game1.player.controller == null`，再加一条 `Game1.locationRequest == null` 前置。
3. **可选诊断**：在 Push 阶段记录 `Game1.fadeToBlackAlpha` 连续若干帧是否不增长；不增长即"淡出被反复重置"，把该读数写进 `Note()`，下次真机可直接取证（不改结论逻辑）。
4. 旧代码有相邻教训可参考：`ShiftOffWarpTile`（旧 `ModEntry.cs:1578-1600`，"落点安全化"，见 `docs\knowledge\legacy-api-1.6.15.md:168`、`docs\_legacy-audit.md:282`）治的是"**落在** warp 格被立刻弹回"；本例是"**推在** warp 格上反复起传"，互补但修法不同。

---

## §7 证据、复跑方式与未定项

### 工具与复跑

- 方法级 IL（含分支目标）：`tools\il-probe\bin\Release\Probe26.exe <gameDir> "Type|Method" ... "FIND|<子串>"`。注意 `FIND|` **只解析方法 token**，查字段名永远 0 命中。
- 常量/字段名解析：`scratch\profession-probe`（net6.0）新增两种模式
  - `ILDEC|<TypeFullName>|<MethodName>`：手写 IL 走读，解码 `ldc.r4/ldc.r8/ldc.i4*` 常量并打出字段/方法/字符串名（Probe26 缺 `InlineR` case，见 `tools\il-probe\Probe26.cs:392-422`）。
  - `ILSCAN|<TypeFullName>|<MemberName>`：全程序集扫描"哪些方法的 IL 含该成员 token"（4 字节滑窗，可能有假阳性，可用 `ILDEC` 复核）。
  - 构建：`C:\Program Files\dotnet\dotnet.exe build -c Release --nologo scratch\profession-probe\ProfessionProbe.csproj`（0 warning / 0 error）。
- 直接调静态只读方法：`INVOKE|<Type>|<Method>|<args>`。
- IL 转储若是 UTF-16LE，先 `tools\_tmp_conv.py` 转 UTF-8。

### 本次产生的证据文件（均在 `scratch\`）

| 文件 | 内容 |
|---|---|
| `il-warp-game1.txt` | `FIND|warpFarmer` 的 66 个调用方法；`Farmer.MovePositionImpl` 全文（605-649 行是碰撞→起传） |
| `il-warp-perform.txt` | `Game1.performWarpFarmer`（日志 + `stsfld locationRequest` + `fadeScreenToBlack`）、`Farmer.warpFarmer` 两个重载 |
| `il-screenfade.txt` | `ScreenFade.FadeScreenToBlack(startAlpha, stopMovement)` |
| `il-const.txt` | `Game1.fadeScreenToBlack()` = `FadeScreenToBlack(0f, true)` |
| `il-warp-update.txt` / `il-update-dec.txt` | `Game1._update`（含 `fadeToBlack` 门：IL_0757-0761 `blt.un -> IL_0F26`） |
| `il-pfc.txt` | `Farmer.MovePosition`（`CanMove=false` 被 controller 绕过，IL_02A7-02BC） |
| `il-locreq-scan.txt` | `ILSCAN|Game1|locationRequest` ⇒ 19 个引用方法（含 `onFadeToBlackComplete`） |
| `il-onfade.txt` | `Game1.onFadeToBlackComplete`（真正落地传送）+ `notifyServerOfWarp` |
| `il-updatefade.txt` / `il-updatefade-probe26.txt` | `ScreenFade.UpdateFade`（alpha > 1.1 才回调；probe26 版带分支目标） |
| `il-updatefade-callers.txt` | `ILSCAN` ⇒ `UpdateFade` 的唯一调用者 `Game1.UpdateOther @IL+0x002D` |
| `il-fadealpha.txt` / `il-screenfade.txt` | `ScreenFade.UpdateFadeAlpha`（0.0019 / 0.0008 每毫秒；`IsDedicatedHost` → 1.2）、`FadeScreenToBlack`（alpha=startAlpha、CanMove=false） |
| `il-setters.txt` | `Game1.set_fadeToBlack / set_nonWarpFade / set_fadeToBlackAlpha` 都只是纯字段写（无回调、无副作用） |
| `il-updatepause.txt` / `il-updateother.txt` | `Game1.updatePause`（3 处 `warpFarmer`，不读 `locationRequest`）/ `Game1.UpdateOther` |
| `il-locreq.txt` | 反例记录：`FIND|locationRequest` 只命中名字含该串的**方法** ⇒ 证明 `FIND` 查不到字段 |

### 未定项（如实记录）

1. **风暴终止的逐帧机制**是推论（§4）：缺少"每帧 `Game1.locationRequest` 是否非空、玩家像素位置是否在变"的真机读数。要定案需要 Mod 侧诊断（§6-3）或一次带逐帧观测的真机跑。
2. **run2 起跑时玩家所在地点**没有直接日志证据；由"账本第一条就是 `goto_farm`"+"当天地点日志 22:22:52 角色在床上（FarmHouse）"推断起点是 FarmHouse、那 313 次是 FarmHouse→Farm 的门格 warp，未直接观测。
3. `Game1._update` 在 `fadeToBlack && alpha<1` 时跳到 `IL_0F26` 而跳过的具体步骤（IL_0771–IL_0F25：输入/指令处理段）只做了粗粒度确认，未逐条清点——本次结论不依赖它。
