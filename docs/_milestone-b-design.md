# 里程碑 B 设计说明：`move_to_location`（跨地点移动）

> 本文是**实现侧**的设计说明，由子代理在实现 `move_to_location` 时写下。
> 契约层的权威描述在 `docs/03-桥接协议.md`、`docs/01-架构设计.md`（本文不改动它们）。
> 本文只写"代码里到底怎么做的、为什么这么做、哪些还没在真机上验证"。

改动文件：`mod/AgentFarm.Bridge/StepMover.cs`（新）、`mod/AgentFarm.Bridge/LocationGraph.cs`（新）、
`mod/AgentFarm.Bridge/MoveToLocationSkill.cs`（新）、`mod/AgentFarm.Bridge/Skills.cs`（改）、
`mod/AgentFarm.Bridge/Contracts.cs`（改）、`mod/AgentFarm.Bridge/BridgeHost.cs`（改）。

---

## 1. 地点图：一根硬编码地名/坐标都没有

**节点** = `Game1.locations` 里每个 `GameLocation.Name`；另外把"被某条 warp 指向的地名"也登记成节点
（目标地图此刻可能还没被游戏创建出来，但路由仍然算得出来）。

**边** = 每个地点的 `GameLocation.warps` 里的每一条 `Warp`：

| 字段 | 含义 | 来源 |
|---|---|---|
| `From` | 出发地点 | `GameLocation.Name` |
| `To` | 目标地点 | `Warp.TargetName` |
| `Source` | **源格**（在本地点里） | `Warp.X` / `Warp.Y` |
| `Landing` | **落点格**（在目标地点里） | `Warp.TargetX` / `Warp.TargetY` |

> `Warp.X/Y = 源格` 这一点是 **1.6.15 IL 反汇编直接读出来的**
> （`Warp..ctor(Int32 x, Int32 y, String targetName, Int32 targetX, Int32 targetY, Boolean flipFarmer, Boolean npcOnly)`
> 的 `ldarg` 顺序）。旧项目 `src/AutoFarmWorker/ModEntry.cs:518` 那句注释「Warp.X/Y 是目标地图坐标」**是错的**。

因此"FarmHouse 的门在哪"这个问题**不需要**任何常量：门就是 FarmHouse 这张地图 `Warps` 图层上的一条 warp，
源格由地图给、目标地名由地图给。换存档 / 装地图模组都不会失效。

**建图只读**：只读 `Game1.locations` / `loc.Name` / `loc.warps` / `Warp` 的四个坐标与目标名。
刻意**不**调用 `GameLocation.updateWarps()`（那是 `warps.Clear()` + 按地图重建，是状态写入）。
刻意**不**调用 `Game1.getLocationFromName()`（对某些名字它会**创建**一个新的 `GameLocation`，也是状态写入）。

过滤与去重：
* `warp.npcOnly == true` 的边跳过（玩家踩上去不会传送）—— 计入 `SkippedNpcOnly`，写进失败诊断串；
* `TargetName` 为空的跳过 —— 计入 `SkippedUnnamed`；
* 同一地点上 `(To, Source)` 完全相同的重复声明只留一条。

**路由**：从当前地点到目标地点做 **BFS**（边数最少 = 传送次数最少）。
排序是**确定性的**：每条邻接表按 `Priority`（源格能不能站）→ `To`（序数比较）→ `Source.Y` → `Source.X` 排序，
不依赖字典遍历顺序，同一次会话里重复调用得到同一条路。

`Priority` 的含义：`0` = 源格**本身可站**（直接走过去就触发）；`1` = 源格站不上去
（门格/台阶/水边/装饰格），得靠候选序列里的"穿过格 / 四邻 / 挤压格"去撞。
"能不能站"**问游戏**（复用 `StepMover.Standable`，`allow_bed=true`：这一跳只求触发传送，
判据是"地点真的变了"，与床边弹窗无关）。

**目标地名的规范化**只做大小写折叠（`ResolveName`），**不做**前缀匹配/别名表/相似度。
猜地名会直通旧方案病灶"基于错误事实的正确推理"。匹配不上就 `precondition_failed`，
reason 里列出**当前地点能直接去的所有地方**（`DirectNeighbors`）。

## 2. 一跳是怎么执行的（多跳、跨帧）

每一跳 = 「在当前地点内走到某个 warp 的**源格** → 等游戏真的把玩家传送过去」。

**为什么传送门会自己触发**：1.6.15 的 `Farmer.MovePositionImpl` 在**移动过程中**会调
`GameLocation.isCollidingWithWarp(玩家像素矩形, 玩家)`，命中就 `Game1.warpFarmer(warp, ...)`
（IL 实证）。`PathFindController.moveCharacter` 里也调 `character.MovePosition(...)`，
所以**游戏自带的寻路器会自己把人送过门**。

这正好满足硬纪律①（不伪造输入）：我们只下寻路目标，**不合成任何键鼠事件**，
也**绝不**自己调 `Game1.warpFarmer` —— 那等于绕过游戏规则瞬移，还会让"判据"变成自证。

`isCollidingWithWarp` 的判据（IL 实证，`position` 是**像素矩形**）：
`warp.X` 等于矩形左边缘或右边缘所在格，且 `warp.Y` 等于上边缘或下边缘所在格
（`(int)Math.Floor(position.Left / 64.0)` 等）。也就是说：**要"撞"到触发格上，而不是站上去不动**。

于是每跳的候选落脚点（按顺序尝试，`MaxCandidates = 16`）：
1. `source` —— 源格本身；
2. `cross` —— 沿"玩家来的方向"**穿过**源格的那一格（要撞门才会被传送）；
3. `neighbor` —— 源格四邻（按到玩家的曼哈顿距离排序，且只保留能站的），每个邻居后再补一次 `retry`（源格）；
4. `push` —— 从邻居那一侧往门里挤（"贴着门挤"）；
5. `alt_*` —— 同一地点通往**同一目标**的其它 warp（门可能不止一个）。

候选全部走完地点还是没变 → 这一跳失败（见 §4）。

**落地后的稳定期**：地点一旦变化，先等 `SettleTicks = 2` 个 tick 再走下一跳
（条目 013 的教训：刚落地那一帧读到的世界可能还在切换，拿它当下一步的依据会重演
"模态已关闭 ≠ 世界已恢复"）。

**按事实重新规划**：地点变化后**不假设**"门去了地图上写的地方"，
立刻用"现在真实所在的地点"重新建图 + 重新 BFS（`Replan`，上限 `MaxReplans = 10`，
防两个 warp 把人来回弹成 ping-pong）。回执里 `to`（地图上写的）与 `arrivedAt`（实际观测到的）
分开给，不一致时那一跳记 `result="mismatch"`。

**整体超时**沿用 `Skills.ClampTimeout`（[500, 30000]，缺省 8000）；每一跳另有 `HopTimeoutMs = 8000`
预算，并且再被"整体剩余时间"夹一次（`budget = min(8000, remaining)`），所以永远不会越过总预算。
跳数上限 `MaxHops = 24`。

## 3. 判据：只有"地点真的变了"才算成功

一跳成功的**唯一**判据是 `Game1.currentLocation.Name` 真的变成了别的地点。
`CurrentLocationName()` 读不出来返回 `null`，而 `null` **不当成功**（继续等到超时）——
绝不用"位置接近落点""走了 N 格""控制器结束"之类推断代替。

失败时 `hops[]` 里的 `result` 取值：

| result | 含义 |
|---|---|
| `ok` | 这一跳的地点**观测到**变了，且变到的正是 warp 上写的 `To` |
| `mismatch` | 地点变了，但变到的**不是** warp 上写的那个地方（诚实记账，随后按事实重规划） |
| `hop_failed` | 走到了触发区却**没**触发传送（或只走到门口附近、没能站上源格） |
| `unreachable` | 在**当前地点内** A* 就算不出到源格的路径 |
| `blocked` | 卡死（与 `move_to` 同一套像素位移判据：连续 > 90 帧位移 ≤ 2px） |
| `timeout` | 单跳预算或整体预算用尽 |
| `ui_modal` | 被菜单/对话/过场打断 |
| `error` | 内部异常 |

`reachedTiles` 的记账刻意分两档，避免"没有的证据"：
只有候选格**就是** `warp.Source` 时才写进 `_reachedTiles`（"人确实站上了触发格"），
走到四邻/穿过格只写进 `_reachedNearTiles`（"走到了门口附近"）。
`hop_failed` 的文案据此分两套，不会把"站上了触发格"说成事实之外的话。

## 4. 失败码与 reason（可操作）

| status | 触发条件 | reason 里必须有的信息 |
|---|---|---|
| `unreachable_no_route` | warp 图上 BFS 无路 | **当前地点的直连邻居列表** + 目标地点的直连邻居 + 图规模 |
| `precondition_failed` | ①`args.location` 缺失/不存在；②坐标为负；③目标格有阻挡家具 | ①**当前地点能直接去的地方**（+ 若该地名被某条 warp 指着却不是任何地点名，明说"尚未解锁/未创建"）；③家具类别 + 改选建议（床另有 `allow_bed=true` 说明） |
| `hop_failed` | 走到触发区但地点没变 | 源格、地图上的落点、**试过的所有格子**（`usedTile(kind)=status[reason]` 列表） |
| `unreachable` | 源格在当前地点内 A* 无解 | 不可通行的判据 + 试过的格子 |
| `blocked` | 卡死 | "与 `move_to` 同一套判据（像素位置长时间不变）" + 试过的格子 |
| `timeout` | 单跳/整体超时 | 预算毫秒 + 剩余步数 + 起点/目标/已走跳数/当前停在哪 |
| `ui_modal` | 菜单/对话/过场 | 当前地点 + 目标地点 |
| `no_save` | 世界没就绪 | — |
| `error` | 图构建/重建失败、内部异常 | 异常类型 + 消息 |

失败回执**也**带 `path` 与 `hops`（脑能看到"走到哪一步断的"），并带 `reachedLocation`。

## 5. 回执

`ExecResponse` 新增三个**可选**字段（沿用既有风格：`null` 时序列化省略，所以其它技能的回执形状不变）：

```jsonc
"path": ["FarmHouse", "Farm"],          // 实际观测到的地点序列（含起点），不记计划
"hops": [ { …HopView… } ],              // 每一跳的明细
"reachedLocation": "Farm"               // 回执落账那一刻真实观测到的 Game1.currentLocation.Name
```

`HopView`（**全部**逐字段 `JsonPropertyName` 钉死，camelCase）：

```jsonc
{
  "from": "FarmHouse", "to": "Farm", "arrivedAt": "Farm",
  "sourceTile": [12, 3], "landingTile": [64, 15], "usedTile": [12, 3],
  "ms": 812, "result": "ok", "detail": null
}
```

### 完整请求 / 回执示例

成功（FarmHouse → Farm，然后再走到 (64,15)）：

```jsonc
// 请求
{"skill":"move_to_location","args":{"location":"Farm","tile":[64,15]},"timeout_ms":15000}
// 回执
{
  "ok": true, "status": "ok", "skill": "move_to_location",
  "reason": "已从 FarmHouse 到达 Farm（1 跳）",
  "schema": "agentfarm-exec/2",
  "elapsedMs": 1934, "worldSeqBefore": 12041, "worldSeqAfter": 12103,
  "path": ["FarmHouse", "Farm"],
  "hops": [
    {"from":"FarmHouse","to":"Farm","arrivedAt":"Farm",
     "sourceTile":[12,3],"landingTile":[64,15],"usedTile":[12,3],
     "ms":1105,"result":"ok"}
  ],
  "reachedLocation": "Farm"
}
```

无路（图上有起点、没路径）：

```jsonc
{"ok":false,"status":"unreachable_no_route","skill":"move_to_location",
 "reason":"从 FarmHouse 到 IslandSouth 在 warp 图上无路可走（FarmHouse 的直连邻居：Farm；目标 IslandSouth 的直连邻居：（无 —— 这个地点没有任何 warp 出口）；当前图规模 87 个地点 / 214 条 warp 边）",
 "elapsedMs":3,"worldSeqBefore":12041,"worldSeqAfter":12041,
 "path":["FarmHouse"],"reachedLocation":"FarmHouse"}
```

地名不存在：

```jsonc
{"ok":false,"status":"precondition_failed","skill":"move_to_location",
 "reason":"地点“farmhousee”不存在（当前地点 FarmHouse 能直接去的地方：Farm；当前图规模 87 个地点 / 214 条 warp 边）",
 "elapsedMs":3,"reachedLocation":"FarmHouse"}
```

走到了触发区但传送门没触发：

```jsonc
{"ok":false,"status":"hop_failed","skill":"move_to_location",
 "reason":"第 1 跳失败（hop_failed）：FarmHouse → Farm 的传送没有触发 —— 角色已经走到 (12,3)（warp 源格 (12,3)、落点 (64,15)），但 Game1.currentLocation.Name 仍然是 FarmHouse。该 warp 可能需要先开门/交互才会生效，或者这张地图的 warp 触发区与源格不一致；本跳试过的格子：(12,3)(source)=ok[走到了但地点没变]；…；本次共走 1 跳，当前停在 FarmHouse",
 "elapsedMs":11020,"worldSeqBefore":12041,"worldSeqAfter":12098,
 "path":["FarmHouse"],
 "hops":[{"from":"FarmHouse","to":"Farm","arrivedAt":"FarmHouse",
          "sourceTile":[12,3],"landingTile":[64,15],"usedTile":[12,3],
          "ms":9804,"result":"hop_failed","detail":"…"}],
 "reachedLocation":"FarmHouse"}
```

被模态打断：`status="ui_modal"`，reason `"移动过程中被菜单/对话/过场打断，已停止移动（当前 FarmHouse，目标 Farm）"`。
卡死：`status="blocked"`。超时：`status="timeout"`，reason 里带预算与已走跳数。

## 6. `StepMover`：抽取移动状态机，`move_to` 行为逐字不变

原先写在 `Skills.MoveToSkill` 里的移动状态机（到达/超时/模态/卡死四支 + 家具与可站判据 + 尺寸来源）
已经抽成 `StepMover`，`move_to`（单跳）与 `move_to_location`（每跳）共用**同一套**代码。

`StepMover` 公开面：

```csharp
internal enum MoveStopKind { Running, Arrived, Timeout, UiModal, Blocked, Unreachable, Error }
internal sealed class MoveOutcome { MoveStopKind Kind; string Reason; string Status; static MoveOutcome Running(); }

internal sealed class StepMover
{
    public const int StuckFrames = 90;
    public int PathSteps { get; }
    public Point Target { get; }
    public GameLocation Location { get; }
    public StepMover(GameLocation loc, Point target, int timeoutMs, string label);
    public MoveOutcome Begin();
    public MoveOutcome Tick(long elapsedMs);
    public void CancelController();
    public static bool Standable(GameLocation loc, Point p, bool allowBed, out Furniture blockingFurniture);
    public static bool SizeFromLayers(GameLocation loc, out int width, out int height);
    public static bool UiBlocked();
    public static bool PlayerFree();
    public static bool EventOrDialogue();
    public static string CurrentLocationName();
    public static string FormatTile(Point p);
}
```

不回归的做法：**所有失败文案都带 `label` 前缀**，`move_to` 传 `"move_to"`，
拼出来的句子与抽取前**逐字节相同**（timeout / 执行异常两支靠这个前缀；
`ui_modal` / `blocked` / `unreachable` / `发起寻路失败` 本来就不带技能名，原样照搬）。
判定顺序也与抽取前完全一致：**到达 → 超时 → 模态 → 卡死**。

`git diff` 逐条核对过的 `move_to` 既有文案（全部原样保留，包括那句刻意留着的陈旧尾缀）：

* `"尚未加载存档，无法执行 move_to"`
* `"缺少参数 args.tile（期望 [x, y] 两个整数）"`
* `$"已在该格 {…}（无需移动）"`
* `"当前有菜单/对话/过场打开，无法移动（请先关闭模态）"`
* `$"目标格 {…} 坐标为负数，非法"`
* `$"目标格 {…} 不在当前地点 {Name} 内（该地点尺寸 {W}x{H}）；跨地点移动尚未实现"`（尾缀**故意**不动）
* `$"目标格 {…} 有家具（{kind}），不能作为落脚点；请改选旁边的空地板格{why}"`
* `$"目标格 {…} 不可通行（被建筑/水面/障碍占据），无法走上去"`
* `$"寻路无法到达 {…}（A* 未算出路径，目标可能被围住）"`
* `$"move_to 超时（{ms}ms，剩余 {n} 步未走完），已停止寻路"`
* `"移动过程中被菜单/对话/过场打断，已停止寻路"`
* `$"角色在 {…} 途中被挡住（约 {1.5:0.0} 秒没有位移），已停止寻路"`
* `"发起寻路失败：{Type}: {msg}"` / `"move_to 执行异常：{Type}: {msg}"`

前置校验顺序不变：no_save → 缺 tile → **已在该格**（必须在家具判据之前，出生点 (9,9) 被床的包围盒覆盖）
→ ui_modal → 负坐标 → 越界 → **家具**（必须在"不可通行"之前，否则家具分支变死代码）→ 不可通行 → 发起寻路。

`BridgeHost` 的长任务判据从 `skill == "move_to"` 改成
`IsLongTaskSkill(skill) => skill == "move_to" || skill == "move_to_location"`
（漏了它的症状就是"第一跳刚发起就把 `null` 交给网络线程"，即条目 013 那类"接口报 ok、实际半途而废"）。

## 7. 遵守的硬纪律

* **不伪造输入**：全程只用 `PathFindController` 下寻路目标，没有 `receiveKeyPress` / 合成键鼠；
  传送由游戏自己在移动过程中触发。
* **不自己传送**：没有调用 `Game1.warpFarmer`（那是瞬移作弊，也会让判据自证）。
* **只读**：建图与判据只读游戏状态；唯一的写操作仍然是豁免清单里的
  `Game1.player.controller`（与 `move_to` 同性质的"停止寻路"），以及 `MoveToSkill` 原有的行为。
* **无硬编码地名/坐标**：`MoveToLocationSkill.cs` / `LocationGraph.cs` 里没有
  `"FarmHouse"`、`(64,15)` 这类常量，地名只在注释与文档示例里出现。
* **不改版本号**：`manifest.json` 的 Version、`ModEntry.cs` 版本文案、`brain/agentfarm/bridge.py`
  的 `MOD_VERSION_EXPECTED` 都没动；`ExecSchema` 仍是 `agentfarm-exec/2`
  （新增字段是**可选**的、`null` 即省略，老客户端读到的形状不变）。

## 8. 编译

```
cd mod/AgentFarm.Bridge
dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo
```

结果：`已成功生成。 0 个警告 0 个错误`。

## 9. ⚠️ 本次**没能**验证的东西（留给真机）

本次任务硬约束是"只写代码 + 编译"，**没有装机、没有启动/关闭游戏、没有向 127.0.0.1:17890
发任何请求**（浸泡测试 `tools/soak.py` 在独占游戏通道）。因此以下全部只是**静态/编译期**证明：

1. **warp 触发那一帧 `Game1.currentLocation` 何时更新**：我的状态机在 `Step()` 里
   "先读地点、再判模态"。若游戏在传送的那一帧先把 `currentLocation` 换掉、
   但 `Context.IsPlayerFree` 仍为 `false`（过场），我的第 1 步会先捕获地点变化，**不会**误报 `ui_modal`；
   反过来若它是先置 `IsPlayerFree=false` 再换地点，则同一 tick 会先命中模态分支。
   这两种顺序**只能在真机确认**（如果真机上出现"跨地点到一半报 ui_modal"，
   把模态判据移到地点判据之后即可，改动只有一个块的位置）。
2. **`isCollidingWithWarp` 的实际触发几何**：IL 读出的是"warp 格 == 玩家像素矩形左/右边缘所在格
   **且** == 上/下边缘所在格"。真机上是否只要**靠近**源格就会触发（而不是必须"穿过"），
   决定候选序列里 `source` / `cross` / `push` 哪一档真正生效。静态实现把四档都排上了，
   真机跑通后**可以**据此把候选裁到最小。
3. **FarmHouse → Farm 的实际成功率**（验收要求 ≥ 9/10）：本次无法测。
4. **`Game1.locations` 里 `Name` 与实际 warp `TargetName` 的一致性**：多格小屋/多人存档里
   客户端小屋的 `Name` 是 `FarmHouse` 而 `TargetName` 可能带唯一后缀。本实现对"目标名不是任何
   地点名"的情况给 `precondition_failed` 并提示该地名被某条 warp 指着；
   若真机上遇到这类地点，需要在 `LocationGraph` 里加别名映射（**不能用 `getLocationFromName`**，
   它会创建地点，属于状态写入）。
5. **落地后是否会立刻被反向 warp 弹回**：如果游戏把玩家落在**反向门的触发格上**，
   下一跳可能立刻被送回，表现为 `hops` 里出现 `mismatch` 往返，10 次重规划后 `hop_failed`。
   本实现对此是诚实的（回执里看得见），但没有真机验证过原版农场门口会不会发生。
6. **`SizeFromLayers` 对 Farm 这种大室外地图的层尺寸**是否与可走范围一致（越界判据只是前置拒绝，
   不影响正常路径）。
7. **家具/可站判据在 Farm 上的表现**：`move_to` 的判据已在 FarmHouse 真机对线过，
   但 Farm 上有大量 terrainFeatures，`Standable` 把它们列为阻挡（树/灌木/资源堆）——
   没在真机上验证过"目标格恰好是耕地/草地时能走"。
8. **`hops[].usedTile` 的语义**：它记的是"最后走向的那个候选格"，不是"触发传送的那一格"；
   只有在 `result="ok"` 且候选就是源格时才等价。
