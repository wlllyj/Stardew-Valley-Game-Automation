using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Objects;
using StardewValley.Pathfinding;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// “在当前地点内走到某一格”的终态/中间态分类。
    /// 与桥接协议的 status 一一对应（<see cref="MoveOutcome.Status"/>），
    /// 唯一多出来的是 <see cref="Arrived"/>（成功）与 <see cref="Running"/>（还没走完）。
    /// </summary>
    internal enum MoveStopKind
    {
        Running,
        Arrived,
        Timeout,
        UiModal,
        Blocked,
        Unreachable,
        Error,

        /// <summary>途中**地点变了**（走到了门/warp 上被游戏传送走）—— 对跨地点技能是成功，对 move_to 是"目标不在这儿了"。</summary>
        LocationChanged,
    }

    /// <summary>
    /// 一次“走一格”的判定结果。文案由 <see cref="StepMover"/> 组装好，
    /// 调用方直接写进回执的 reason —— 这样 move_to 与 move_to_location 共用同一套词句，不会各写一份。
    /// </summary>
    internal sealed class MoveOutcome
    {
        public MoveStopKind Kind { get; }
        public string Reason { get; }

        public MoveOutcome(MoveStopKind kind, string reason)
        {
            this.Kind = kind;
            this.Reason = reason;
        }

        /// <summary>协议 status 文案（Running 时为 null）。</summary>
        public string Status
        {
            get
            {
                switch (this.Kind)
                {
                    case MoveStopKind.Arrived: return "ok";
                    case MoveStopKind.Timeout: return "timeout";
                    case MoveStopKind.UiModal: return "ui_modal";
                    case MoveStopKind.Blocked: return "blocked";
                    case MoveStopKind.Unreachable: return "unreachable";
                    case MoveStopKind.LocationChanged: return "location_changed";
                    case MoveStopKind.Error: return "error";
                    default: return null;
                }
            }
        }

        public static MoveOutcome Running() => new MoveOutcome(MoveStopKind.Running, null);
    }

    /// <summary>
    /// 【里程碑 B 抽取】把原先写在 <c>Skills.MoveToSkill</c> 里的“移动状态机”抽出来，
    /// 让 <c>move_to</c>（单跳：当前地点内走一格）与 <c>move_to_location</c>（多跳：每一跳也走一格）
    /// **共用同一套代码**，不再各写一份。
    ///
    /// 抽取的硬约束：**move_to 的对线行为逐字不变**。
    /// 因此这里的所有文案都带 <c>_label</c> 前缀，调用 <c>move_to</c> 时传 <c>"move_to"</c>，
    /// 拼出来的句子与抽取前**逐字节相同**（timeout / 执行异常两支）；另外三支（ui_modal / blocked /
    /// 无法寻路 / 发起寻路失败）本来就不带技能名，原样照搬。
    ///
    /// 【为什么状态机只在 tick 里推进】
    /// 每次被主线程调用只判定一次、返回一个结果，绝不自己等待、绝不 sleep，
    /// 保持“每 tick 最多推进 2 项”的长任务模型。
    /// </summary>
    internal sealed class StepMover
    {
        /// <summary>
        /// 寻路时“连着多少帧既没动像素、也没换格”判为卡死（60fps 下约 3 秒）。
        ///
        /// 【task-43 为什么从 90 提到 180】卡面 rev3 的口径是
        /// **“有进展就不许放弃，只有连续 ~3s 玩家格不变才判 `stuck` 早退”**。
        /// run4 实证：同一候选两次 8s 分别剩 52 / 16 步（人在稳定推进，≈4.5 格/s），
        /// 旧代码却在 8s 预算一到就 `timeout` 并换候选 ⇒ 两次后放弃。
        /// 判定用“像素动过 **或** 玩家格变过”（走路是逐像素推进，只盯像素在慢速移动下会误判）。
        /// </summary>
        public const int StuckFrames = 180;

        /// <summary>
        /// 【task-43】预算用尽但**人还在推进**时，一次续多少毫秒（真机实测 ≈4.5 格/s）。
        ///
        /// 【为什么必须续】run4 实证：`Farm [47,29]` → 农舍门口 A* 真实路径 ≈ **88 步**
        /// （直线 31 格，被草/石/枝/树逼得绕路 3 倍），而旧代码每跳固定 8000ms ——
        /// 同一候选连走两次分别剩 52 步、16 步，**人在稳定推进**，却两次都被判 `timeout`；
        /// 14:48 的两个日报告都因此 `sleep_failed`。所以判据必须是
        /// **“玩家格还在变 / 剩余步数还在减”就续跳，只有连续 ~3s 玩家格不变才判卡死**。
        /// </summary>
        public const int ExtensionMs = 8000;

        /// <summary>一次行走最多续预算几次（防"绕圈子一直走"；超出后仍如实报 `timeout`）。</summary>
        public const int MaxBudgetExtensions = 8;

        /// <summary>
        /// 【着陆契约修复】到达目标格之后，还要**连续**多少帧“像素位置没动”才算真的站定
        /// （60fps 下 0.2 秒）。
        ///
        /// 【为什么必须有它 —— v0.5.1 的真机 bug】
        /// v0.5.1 的到达判据是 <c>player.TilePoint == target</c>。`TilePoint` 是整数除法，
        /// **角色刚跨过格子边界那一帧**它就等于目标格了 —— 此时人还在朝格心走，最多还差 32 像素。
        /// 老代码在这一帧就 `controller = null` 收工，而控制器留下的 `movementDirections`
        /// **没有被清**，于是角色按原方向一直走到撞墙为止。
        ///
        /// 真机证据（`tools/soak.py` 2026-10-11 18:19–18:38，7 次 move_to **7 次落错格**）：
        ///   move_to(6,8) ok 1064ms → 观测在 [6,10]；move_to(7,9) ok 353ms → [9,9]；
        ///   move_to(8,9) ok 155ms → [1,9]；move_to(6,8) ok 1265ms → [6,6]；
        ///   move_to(7,9) ok 797ms → [7,10]；move_to(8,9) ok 378ms → [8,5]；
        ///   move_to(6,8) ok 1025ms → [6,10]。
        /// 全部是“沿原行走方向多走 1~7 格”。
        ///
        /// 现判据：**人真的停在目标格上**（像素连续若干帧不变），然后再 <see cref="HaltPlayer"/> 清干净。
        /// </summary>
        public const int SettleFrames = 12;

        private readonly GameLocation _loc;
        private readonly Point _target;
        private int _timeoutMs;
        private readonly string _label;

        /// <summary>上一 tick 的像素位置（用来判“这一帧到底动没动”）。</summary>
        private Vector2 _lastTickPosition;
        private int _stuckFrames;

        /// <summary>上一 tick 的**玩家格**（task-43：格变了也算进展，慢速走路时比像素更稳）。</summary>
        private Point _lastTilePoint;

        /// <summary>本条行走已经续过几次预算（task-43：上限 <see cref="MaxBudgetExtensions"/>，防绕圈）。</summary>
        private int _extensions;

        /// <summary>连续“在目标格上且像素没动”的帧数（见 <see cref="SettleFrames"/>）。</summary>
        private int _settleFrames;

        /// <summary>A* 给出的剩余步数（发起时捕获，仅用于失败时的诊断文案）。</summary>
        public int PathSteps { get; private set; }

        /// <summary>
        /// 把本次行走的时间预算**抬高**（只增不减）。
        ///
        /// 【task-43】真实剩余步数只有 <see cref="Begin"/> 跑完 A* 才知道，而 `Tick` 是拿
        /// `elapsed > 预算` 判超时的 ⇒ 发起后抬高完全来得及，不必为了拿步数跑两遍 A*。
        /// </summary>
        public void RaiseBudget(int ms)
        {
            if (ms > this._timeoutMs) this._timeoutMs = ms;
        }

        public Point Target => _target;
        public GameLocation Location => _loc;

        /// <param name="loc">在哪张地图上走（<c>move_to</c> 传 <c>Game1.currentLocation</c>）。</param>
        /// <param name="target">目标格。</param>
        /// <param name="timeoutMs">本次行走的时间预算。</param>
        /// <param name="label">失败文案里的技能名，例如 <c>"move_to"</c> 或 <c>"move_to_location 第 1 跳（FarmHouse → Farm）"</c>。</param>
        public StepMover(GameLocation loc, Point target, int timeoutMs, string label)
        {
            this._loc = loc;
            this._target = target;
            this._timeoutMs = timeoutMs;
            this._label = label;
        }

        /// <summary>发起寻路。返回 <see cref="MoveStopKind.Running"/> 表示已经上路，需要后续 tick 继续推进。</summary>
        public MoveOutcome Begin()
        {
            try
            {
                // 清掉可能残留的旧控制器 / 旧 movementDirections（上一次调用留下的）。
                // 【为什么连 movementDirections 一起清】见 <see cref="SettleFrames"/>：只清 controller
                // 会把“上一段行走的方向”留在角色身上，它会照着那个方向一直走下去。
                HaltPlayer();

                var ctrl = new PathFindController(Game1.player, this._loc, this._target, 0);
                Game1.player.controller = ctrl;

                int steps = 0;
                try { steps = ctrl.pathToEndPoint?.Count ?? 0; } catch { steps = 0; }
                this.PathSteps = steps;

                // A* 无解（目标被围死）：路径为空且人不在目标格上 → 立刻放弃，不空等。
                if (steps == 0 && Game1.player.TilePoint != this._target)
                {
                    HaltPlayer();
                    return new MoveOutcome(MoveStopKind.Unreachable,
                        $"寻路无法到达 {FormatTile(this._target)}（A* 未算出路径，目标可能被围住）");
                }

                this._lastTickPosition = Game1.player.Position;
                this._lastTilePoint = Game1.player.TilePoint;
                this._extensions = 0;
                this._stuckFrames = 0;
                this._settleFrames = 0;

                return MoveOutcome.Running();
            }
            catch (Exception ex)
            {
                HaltPlayer();
                return new MoveOutcome(MoveStopKind.Error,
                    "发起寻路失败：" + ex.GetType().Name + ": " + ex.Message);
            }
        }

        /// <summary>
        /// 每个 tick 推进一次。
        /// 判定顺序：**到达（站定）→ 寻路器提前收工 → 超时 → 模态 → 卡死**。
        /// </summary>
        /// <param name="elapsedMs">本次行走已经花掉的时间（由调用方按时钟算，保证跨跳不会各算各的）。</param>
        public MoveOutcome Tick(long elapsedMs)
        {
            try
            {
                Vector2 pos = Game1.player.Position;
                float deltaSq = Vector2.DistanceSquared(pos, this._lastTickPosition);
                this._lastTickPosition = pos;

                bool onTarget = Game1.player.TilePoint == this._target;

                // 0) 事实最优先之一：**正在传送**（`Game1.warpFarmer` 已发起、屏幕淡出中）。
                //    这段里地点还没换、角色一动不动；旧代码会命中下面的"卡死"判据（90 帧无位移）
                //    直接报 blocked 并收工，等地点真变了已经没人看。
                //    真机事故（2026-10-11 18:5x）：`goto Farm` 回执 status=blocked / arrivedAt=FarmHouse，
                //    而角色其实已经站在 Farm(64,15)。所以：**传送期间一律不下任何结论**。
                if (WarpInProgress())
                    return MoveOutcome.Running();

                // 0b) 事实最优先之二：地点已经变了（走到了门 / warp 上）。
                //     这比"卡住/超时"都权威，必须排在所有失败判据之前。
                string here = CurrentLocationName();
                if (here != null && this._loc != null &&
                    !string.Equals(here, this._loc.Name, StringComparison.Ordinal))
                {
                    HaltPlayer();
                    return new MoveOutcome(MoveStopKind.LocationChanged,
                        $"{this._label} 途中地点发生了变化（{this._loc.Name} → {here}）");
                }

                // 1) 到达判定：**人停在目标格上**才算到（不是“刚跨过格子边界”）
                if (onTarget && deltaSq <= 0.25f)
                {
                    this._settleFrames++;
                    if (this._settleFrames >= SettleFrames)
                    {
                        HaltPlayer();
                        return new MoveOutcome(MoveStopKind.Arrived, null);
                    }
                }
                else
                {
                    this._settleFrames = 0;
                }

                // 2) 游戏自己的寻路器把控制器摘了、人却不在目标格上 ⇒ 它提前收工了（被挡住/无路）。
                //    如实报失败：**绝不**把“控制器结束”当成“到了”（条目 013 的教训）。
                if (!onTarget && Game1.player.controller == null)
                {
                    HaltPlayer();
                    return new MoveOutcome(MoveStopKind.Blocked,
                        $"{this._label} 途中寻路器提前结束（当前格 {FormatTile(Game1.player.TilePoint)}，"
                        + $"目标 {FormatTile(this._target)}），已停止");
                }

                // 3) 【task-43】进展证据：像素动过 **或** 玩家格变过 ⇒ 刷新"卡死"计数。
                //    走路是逐像素推进（慢速移动时单帧位移可能不到 2px），所以"格变没变"比像素更可靠。
                Point nowTile = Game1.player.TilePoint;
                bool movedPixels = deltaSq > 4f;
                bool movedTile = nowTile != this._lastTilePoint;
                if (movedTile) this._lastTilePoint = nowTile;
                if (movedPixels || movedTile) this._stuckFrames = 0;
                else this._stuckFrames++;

                // 3b) 刷新诊断用的"剩余步数"（A* 路径在缩短 ⇒ 失败文案能看出人在推进）。
                try
                {
                    if (Game1.player.controller is PathFindController pc)
                    {
                        int left = pc.pathToEndPoint?.Count ?? this.PathSteps;
                        if (left > 0) this.PathSteps = left;
                    }
                }
                catch
                {
                    // 拿不到就保持旧值：这里只是诊断文案，不参与任何判据
                }

                // 4) 超时：预算用尽时**先看有没有进展** —— task-43 的核心口径。
                //    run4 实证：真实路径 ≈88 步（A* 被草/石/枝/树逼得绕路 3 倍），旧代码每跳固定 8000ms，
                //    而玩家 8s 能从"剩 52 步"走到"剩 16 步"（≈4.5 格/s）⇒ 人在稳定推进却被判 `timeout`。
                //    口径：**只要还在推进就续预算**（一次 <see cref="ExtensionMs"/>，最多
                //    <see cref="MaxBudgetExtensions"/> 次）；真正没进展由下面的卡死判据（~3s）收尾。
                if (elapsedMs >= this._timeoutMs)
                {
                    if (this._stuckFrames == 0 && this._extensions < MaxBudgetExtensions)
                    {
                        this._extensions++;
                        this._timeoutMs = (int)elapsedMs + ExtensionMs;
                        return MoveOutcome.Running();   // 续跳：绝不打断正在推进的行走
                    }
                    HaltPlayer();
                    return new MoveOutcome(MoveStopKind.Timeout,
                        $"{this._label} 超时（{this._timeoutMs}ms，剩余 {this.PathSteps} 步未走完），已停止寻路");
                }

                // 5) 模态/过场打断
                if (!PlayerFree() || Game1.activeClickableMenu != null || EventOrDialogue())
                {
                    HaltPlayer();
                    return new MoveOutcome(MoveStopKind.UiModal,
                        "移动过程中被菜单/对话/过场打断，已停止寻路");
                }

                // 6) 卡死检测：约 3 秒没有位移也没换格 ⇒ 真卡住，早退（不烧满预算）
                if (this._stuckFrames > StuckFrames)
                {
                    HaltPlayer();
                    return new MoveOutcome(MoveStopKind.Blocked,
                        $"角色在 {FormatTile(this._target)} 途中被挡住（约 {StuckFrames / 60.0:0.0} 秒没有位移），已停止寻路");
                }

                return MoveOutcome.Running();   // 继续走
            }
            catch (Exception ex)
            {
                HaltPlayer();
                return new MoveOutcome(MoveStopKind.Error,
                    $"{this._label} 执行异常：" + ex.GetType().Name + ": " + ex.Message);
            }
        }

        /// <summary>
        /// 把玩家**彻底**停下来：清掉寻路控制器 + 清掉残留的移动方向。
        ///
        /// 【IL 实证】`Farmer.Halt()`（1.6.15）无条件执行 `movementDirections.Clear()`，
        /// 且**没有**任何 `CanMove = false`；但转调基类 `Character.Halt()`（内含 `controller = null`）
        /// 会被“骑马 / 正在用工具 / 单帧动画”三个条件跳过 —— 所以这里再自己补一次
        /// `controller = null` 与 `movementDirections.Clear()`。
        /// </summary>
        public static void HaltPlayer()
        {
            try { if (Game1.player != null) Game1.player.Halt(); } catch { }
            try { if (Game1.player != null) Game1.player.controller = null; } catch { }
            try { if (Game1.player != null) Game1.player.movementDirections.Clear(); } catch { }
        }

        /// <summary>
        /// 是否**正在传送**（`Game1.warpFarmer` 已发起、地点切换前的淡出期）。
        /// 判据是游戏自己的 <c>Game1.locationRequest != null</c>（api-probe 编译期确认存在）。
        /// 读不出来时返回 false —— 宁可照常走别的判据，也不误报"在传送"。
        /// </summary>
        private static bool WarpInProgress()
        {
            try { return Game1.locationRequest != null; } catch { return false; }
        }

        /// <summary>
        /// 【兜底机制】把"**朝某一格走一步**"交给**游戏自己的寻路器**执行：
        /// <c>new PathFindController(Stack&lt;Point&gt; pathToEndPoint, GameLocation, Character, Point endPoint)</c>
        /// —— ctor 的 IL 实证（1.6.15）显示它**只是四个字段直接赋值**，不做任何 A*；
        /// 之后 `update` 每帧 `pathToEndPoint.Peek()` 取下一格、调 `moveCharacter` 把人往那一格走。
        ///
        /// 【为什么需要它】门的格子（例如农舍门 `(64,14)`）在墙上，**A\* 到不了**，所以
        /// 常规"给个目标让寻路器自己算"的办法必然 `unreachable`；而门的触发只要求
        /// **移动中**撞到门（`GameLocation.isCollidingWithWarpOrDoor`），站着不动永远不触发。
        /// 于是把这条"一步路径"直接喂给游戏自己的控制器 ——
        /// 既**没有**合成键鼠事件、**没有**直接改坐标、**也绝不**自己调 `Game1.warpFarmer`：
        /// 走不走得动、撞到门之后要不要传送，全部由游戏自己的移动/碰撞/warp 判定决定。
        /// </summary>
        public static bool PushInto(Point target, GameLocation loc)
        {
            try
            {
                if (Game1.player == null || loc == null) return false;

                var path = new Stack<Point>();
                path.Push(target);   // 单步路径：Peek() 就是这个门格
                Game1.player.controller = new PathFindController(path, loc, Game1.player, target);
                return true;
            }
            catch { return false; }
        }

        /// <summary>
        /// **这一格能不能锄出耕地**（＝照抄游戏自己的判据，别自己猜）。
        ///
        /// 【依据】`StardewValley.Tools.Hoe.DoFunction` 的 IL（1.6.15）：
        ///   `new Vector2(x / 64f, y / 64f)`（**参数是像素**）→ `terrainFeatures.TryGetValue` →
        ///   `location.objects` → `location.doesTileHaveProperty((int)tile.X, (int)tile.Y, "Diggable", "Back", false)`
        ///   （`IL_0165`–`IL_0183`，为 null 就 `brfalse -> IL_0404` 跳过造地）→ 最后
        ///   `location.makeHoeDirt(tile, false)`（`IL_01A7`）真正创建耕地。
        /// ⇒ 判据 = 该格**没有地形特征、没有放置物、不是水面、且 `Diggable` 属性存在**。
        ///
        /// 【为什么需要它（用户 m01668 提的）】之前 `use_tool(hoe)` 对不可锄的格子会**白挥 6 次**再报
        /// `tool_ineffective`，验证脚本也只能"挨个空格试"。有了这条前置判据，一次就能给出可操作的理由。
        /// 注意：**只对"空洞"用这条判据**（目的是造地）；格子上本来就有杂草/石头时，锄/斧/镐另有各自动作。
        /// </summary>
        public static bool Tillable(GameLocation loc, Point p, out string why)
        {
            why = null;
            try
            {
                if (loc == null) { why = "读不到当前地点"; return false; }

                var tile = new Vector2(p.X, p.Y);

                bool hasFeature = false;
                try { hasFeature = loc.terrainFeatures != null && loc.terrainFeatures.ContainsKey(tile); } catch { }
                if (hasFeature) { why = "这一格已经有地形特征（耕地/草/树…）"; return false; }

                bool hasObject = false;
                try { hasObject = loc.objects != null && loc.objects.ContainsKey(tile); } catch { }
                if (hasObject) { why = "这一格上有放置物（杂草/石头/树枝/机器…），要先清掉"; return false; }

                bool water = false;
                try { water = loc.isWaterTile(p.X, p.Y); } catch { }
                if (water) { why = "这一格是水面"; return false; }

                string diggable = null;
                try { diggable = loc.doesTileHaveProperty(p.X, p.Y, "Diggable", "Back", false); } catch { }
                if (string.IsNullOrEmpty(diggable))
                {
                    why = "游戏不认为这格可锄（Back 图层上没有 Diggable 属性）——多半是路径/建筑/装饰地面";
                    return false;
                }

                return true;
            }
            catch (Exception ex) { why = "判据读取异常：" + ex.GetType().Name; return false; }
        }

        /// <summary>停掉寻路（失败/成功都要做，绝不把玩家留在控制器里）。</summary>
        public void Halt() => HaltPlayer();

        // ==================================================================
        //  共用静态工具（原先散在 Skills.MoveToSkill 里的那几个）
        // ==================================================================

        /// <summary>
        /// 这一格角色站得上去吗（**问游戏，不自己猜几何**）。
        /// 家具只有**踩不上去的**（或床）才算阻挡，通过 <paramref name="blockingFurniture"/> 单独报出，
        /// 由调用方区分处理：“有家具”是**前置条件不满足**，而不是“A* 走不到”。
        /// 建筑与围墙这里判不准，由“A* 无解立即放弃 + 卡死检测”兜底。
        /// </summary>
        /// <param name="loc">在哪张地图上判（<c>move_to</c> 传 <see cref="Game1.currentLocation"/>）。</param>
        /// <param name="blockingFurniture">**阻挡**该格的家具（可踩的家具不算，没有则为 null）。</param>
        public static bool Standable(GameLocation loc, Point p, bool allowBed, out Furniture blockingFurniture)
        {
            blockingFurniture = null;
            try
            {
                if (loc == null) return false;

                var tile = new Vector2(p.X, p.Y);

                // ---- 家具检查（修复迭代 4：问游戏，而不是自己猜几何）----
                //
                // 【v3 为什么错】v3 认为“家具像素包围盒 ∩ 目标格像素矩形”就等于“这格不能站”。
                // 真机把它证伪了：FarmHouse 里 x=6..10 / y=8..10 共 13 格被判“有家具”，
                // 连**玩家出生点 (9,9)** 都在里面；而 (7,9) 在 v0.2.0 明明是 `OK 350ms`、
                // 角色确实站上去了。根因是**地毯等地面家具是可以踩上去的**，而它们的包围盒很大。
                // 只有床格 (10,9) 的拒绝是对的（踩上去会弹 “Go to sleep for the night?” 冻结世界时间）。
                //
                // 【v4 规则：什么情况才算阻挡】
                //   1. 床（`BedFurniture`）—— **无条件阻挡**，无论 `isPassable()` 返回什么。
                //      唯一例外：调用方显式传 `allow_bed=true`，这时放行。
                //   2. 其它家具 —— **只看 `f.isPassable()`**：可踩的（地毯/地垫/地板贴）一律放行。
                //   3. 包围盒（`GetBoundingBox()`）只用来**找到“哪些家具覆盖了目标格”**，
                //      **不再**用它直接下结论 —— 家具是多格的，床的触发区覆盖了 (10,9)，
                //      但床的 `TileLocation` 并不在这格。
                // ⚠️ 1.6.15 的 `Furniture` 上**没有** `getBoundingBox()`（CS1061 编译期证伪），
                //    可用的是继承自 `Object` 的 `GetBoundingBox()`（已用隔离探针编译确认）。
                try
                {
                    if (loc.furniture != null)
                    {
                        var tileRect = new Rectangle(p.X * Game1.tileSize, p.Y * Game1.tileSize,
                                                     Game1.tileSize, Game1.tileSize);

                        foreach (Furniture f in loc.furniture)
                        {
                            if (f == null) continue;

                            bool covers;
                            try { covers = f.GetBoundingBox().Intersects(tileRect); }
                            catch { covers = false; }

                            if (!covers)
                            {
                                // 兜底：包围盒读不出来时，至少比一次家具原点所在格。
                                try { covers = f.TileLocation == tile; } catch { covers = false; }
                            }

                            if (!covers) continue;

                            // 床优先判定：可踩也要拦（会触发睡觉确认框，冻结世界时间）。
                            if (f is StardewValley.Objects.BedFurniture)
                            {
                                if (allowBed) continue;
                                blockingFurniture = f;
                                return false;
                            }

                            // 其余家具：是否阻挡**必须由游戏自己的 isPassable() 决定**。
                            bool passable;
                            try { passable = f.isPassable(); }
                            catch { passable = false; }   // 读不出来时保守当阻挡

                            if (!passable)
                            {
                                blockingFurniture = f;
                                return false;
                            }

                            // 可踩的地毯之类：继续找，别被它遮住了后面真正的障碍家具。
                        }
                    }
                }
                catch { blockingFurniture = null; }

                // ---- 放置物 ----
                //
                // objects 里放的是与格子一一对应的放置物（机器、箱子、杂草、树枝、石头……），
                // 它们在游戏中确实都占格，保守拒绝不会把可走的格子判成不可走。
                // 另：农业视觉上可踩的“草”在 1.6.x 是 terrainFeatures 里的 Grass（见下），
                // 不是 objects，所以这里不会把草地误判成障碍。
                if (loc.objects != null && loc.objects.ContainsKey(tile)) return false;
                if (loc.isWaterTile(p.X, p.Y)) return false;

                // ---- 地形特征 ----
                //
                // 以下四类才挡路：资源堆（巨石/大木头）、树、果树、灌木。
                // **草地 `Grass` 与耕地 `HoeDirt`（含作物）刻意不列** —— 两者都能走上去。
                if (loc.terrainFeatures != null &&
                    loc.terrainFeatures.TryGetValue(tile, out StardewValley.TerrainFeatures.TerrainFeature tf) && tf != null)
                {
                    if (tf is StardewValley.TerrainFeatures.ResourceClump) return false;
                    if (tf is StardewValley.TerrainFeatures.Tree) return false;
                    if (tf is StardewValley.TerrainFeatures.Bush) return false;
                    if (tf is StardewValley.TerrainFeatures.FruitTree) return false;
                }

                return true;
            }
            catch { return false; }
        }

        /// <summary>
        /// 从 xTile 图层取地点尺寸（**单位就是格**，不要再除 <c>Game1.tileSize</c>）。
        ///
        /// 【为什么不用 Map.DisplayWidth / DisplayHeight（修复迭代 4）】
        /// 第一轮审计就发现它在个别地点**会抛异常**；一旦被 catch 吞掉、尺寸退化成 0，
        /// 就会出现“所有候选都在图外、出口永远找不到”的连锁故障（旧方案的实证症状）。
        /// </summary>
        /// <returns>true = 拿到了有效尺寸（&gt;0）；false = 地图/图层不可用，调用方应回退到 int.MaxValue。</returns>
        public static bool SizeFromLayers(GameLocation loc, out int width, out int height)
        {
            width = 0;
            height = 0;
            try
            {
                if (loc?.map?.Layers == null) return false;

                for (int i = 0; i < loc.map.Layers.Count; i++)
                {
                    xTile.Layers.Layer layer = loc.map.Layers[i];
                    if (layer == null) continue;
                    if (layer.LayerWidth > width) width = layer.LayerWidth;
                    if (layer.LayerHeight > height) height = layer.LayerHeight;
                }
            }
            catch
            {
                width = 0;
                height = 0;
            }

            return width > 0 && height > 0;
        }

        /// <summary>当前是否被菜单/对话/过场挡着（读不出来时**不**当成挡着）。</summary>
        public static bool UiBlocked()
        {
            try
            {
                if (Game1.activeClickableMenu != null) return true;
                if (Game1.eventUp) return true;
                if (Game1.dialogueUp) return true;
                if (!Context.IsPlayerFree) return true;
            }
            catch { }
            return false;
        }

        public static bool PlayerFree()
        {
            try { return Context.IsPlayerFree; } catch { return false; }
        }

        public static bool EventOrDialogue()
        {
            try { return Game1.eventUp || Game1.dialogueUp; } catch { return false; }
        }

        /// <summary>当前地点名（读不出来时返回 null，调用方必须当成“拿不到证据”而不是“没变”）。</summary>
        public static string CurrentLocationName()
        {
            try { return Game1.currentLocation?.Name; } catch { return null; }
        }

        public static string FormatTile(Point p) => $"({p.X},{p.Y})";
    }
}
