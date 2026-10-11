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
    /// 技能层（架构 §5.3）。里程碑 A 只实现两个：
    ///   * <c>noop</c>     —— 立刻返回 ok，用于验证通信链路，完全不碰游戏；
    ///   * <c>move_to</c>  —— 用游戏自带 <see cref="PathFindController"/> 把玩家走到 args.tile。
    ///
    /// 【跨 tick 推进】move_to 的 Handler 在“还没走完”时返回 null，
    /// 由 MainThreadDispatcher 下个 tick 继续调用；返回非 null 即为终态。
    /// 这样既不卡帧，又不会把玩家丢在控制器里。
    /// </summary>
    internal static class Skills
    {
        public const int TimeoutMinMs = 500;
        public const int TimeoutMaxMs = 30000;
        public const int TimeoutDefaultMs = 8000;

        /// <summary>
        /// based_on_seq 的“陈旧”阈值（架构 §5.3 时效拒绝）。
        ///
        /// 口径说明：worldSeq 会因为**玩家每跨一格**而 +1（指纹含玩家坐标），
        /// 所以“正常走一段路”本身就会让 seq 涨几十。阈值取得太小会误杀正常请求。
        /// 取 300：约等于 300 格位移或 50 分钟游戏内时间的变化量，
        /// 超出这个量级说明“脑”依据的快照已经明显过期，拒绝执行并要求重新观测。
        /// </summary>
        public const int StaleSeqThreshold = 300;

        /// <summary>寻路时“角色连着多少帧像素位置没变”判为卡死（60fps 下约 1.5 秒）。</summary>
        private const int StuckFrames = 90;

        public static int ClampTimeout(int? timeoutMs)
        {
            int v = timeoutMs ?? TimeoutDefaultMs;
            if (v < TimeoutMinMs) v = TimeoutMinMs;
            if (v > TimeoutMaxMs) v = TimeoutMaxMs;
            return v;
        }

        /// <summary>
        /// 构造一个技能执行器。返回的委托每次被主线程调用：
        /// 返回非 null = 终态（交付网络线程）；返回 null = 还没走完。
        /// </summary>
        public static Func<object> Create(string skill, ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            switch (skill)
            {
                case "noop":
                    return () => new ExecResponse
                    {
                        Ok = true,
                        Status = "ok",
                        Skill = "noop",
                        Reason = "",
                        Schema = "agentfarm-exec/1",
                        WorldSeqBefore = world.WorldSeq,
                        WorldSeqAfter = world.WorldSeq,
                        ElapsedMs = 0,
                    };

                case "move_to":
                    return new MoveToSkill(req, world, monitor).Step;

                case "dismiss_modal":
                    // 单 tick 完成的短任务：不返回 null，所以不会被当成跨 tick 长任务。
                    return () =>
                    {
                        ModalDismissResult r = ModalDismiss.Dismiss();
                        return new ExecResponse
                        {
                            Ok = r.Ok,
                            Status = r.Status,
                            Skill = "dismiss_modal",
                            Reason = r.Reason,
                            Schema = "agentfarm-exec/1",
                            ElapsedMs = 0,
                        };
                    };

                default:
                    // 未实现的技能：合法请求但还没有实现（区别于 unknown_skill）。
                    return () => new ExecResponse
                    {
                        Ok = false,
                        Status = "not_implemented",
                        Skill = skill,
                        Reason = $"技能“{skill}”尚未实现（里程碑 A 只提供 noop、move_to 与 dismiss_modal）",
                    };
            }
        }

        /// <summary>已知技能名（用于区分 unknown_skill 与 not_implemented）。</summary>
        private static readonly HashSet<string> KnownSkills = new HashSet<string>(StringComparer.Ordinal)
        {
            // 已实现
            "noop", "move_to", "dismiss_modal",
            // 架构 §5.3 规划中（返回 not_implemented，便于“脑”一次性看清缺口）
            "move_to_location", "exit_building", "use_tool", "plant", "harvest",
            "pickup_debris", "collect_machine", "refill_watering_can", "talk",
            "buy", "sell", "sleep",
        };

        public static bool IsKnownSkill(string skill) => skill != null && KnownSkills.Contains(skill);

        // ==================================================================
        //  move_to
        // ==================================================================

        private sealed class MoveToSkill
        {
            private readonly WorldObserver _world;
            private readonly IMonitor _monitor;
            private readonly int _timeoutMs;
            private readonly Point _target;

            private bool _started;
            private DateTime _startedAtUtc;
            private Vector2 _lastPosition;
            private int _stuckFrames;
            private long _seqBefore;
            private int _pathSteps;

            public MoveToSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
            {
                this._world = world;
                this._monitor = monitor;
                this._timeoutMs = ClampTimeout(req?.TimeoutMs);

                int[] tile = req?.Args?.Tile;
                this._target = (tile != null && tile.Length >= 2)
                    ? new Point(tile[0], tile[1])
                    : new Point(int.MinValue, int.MinValue);
            }

            private ExecResponse Fail(string status, string reason, long elapsedMs)
                => new ExecResponse
                {
                    Ok = false,
                    Status = status,
                    Skill = "move_to",
                    Reason = reason,
                    ElapsedMs = elapsedMs,
                    WorldSeqBefore = this._seqBefore,
                    WorldSeqAfter = this._world.WorldSeq,
                };

            private ExecResponse Ok(long elapsedMs)
            {
                var r = new ExecResponse
                {
                    Ok = true,
                    Status = "ok",
                    Skill = "move_to",
                    Reason = "",
                    ElapsedMs = elapsedMs,
                    WorldSeqBefore = this._seqBefore,
                    WorldSeqAfter = this._world.WorldSeq,
                };

                // ---- 到达后的副作用：是否顺手弹出了模态 ----
                //
                // 真机实测：走到床边会“成功到达”，但同时触发 "go to sleep for the night?" 对话框，
                // 整个世界时间随之冻结。v1 在这种情况下只回一个 ok，脑会以为一切正常，
                // 于是继续下发下一步 —— 而所有动作都会因为模态挡路而失败。
                // 这里把“到达 + 弹窗”如实报回去，脑再决定是否调 dismiss_modal。
                try
                {
                    r.UiOpened = Game1.activeClickableMenu != null;
                    if (r.UiOpened) r.ActiveMenuText = UiRead.ActiveMenuText();
                }
                catch { }

                return r;
            }

            /// <summary>每次被主线程调用：返回 null = 还在走，返回非 null = 终态。</summary>
            public object Step()
            {
                try
                {
                    if (!_started) return this.Begin();

                    // ---- 每次 tick 的推进与判定 ----
                    long elapsed = (long)(DateTime.UtcNow - _startedAtUtc).TotalMilliseconds;

                    // 1) 到达判定：以玩家**当前格**为准
                    if (Game1.player.TilePoint == _target)
                    {
                        try { Game1.player.controller = null; } catch { }
                        return this.Ok(elapsed);
                    }

                    // 2) 超时：必须停止寻路，绝不能把玩家卡在控制器里
                    if (elapsed >= _timeoutMs)
                    {
                        try { Game1.player.controller = null; } catch { }
                        return this.Fail("timeout",
                            $"move_to 超时（{_timeoutMs}ms，剩余 {this._pathSteps} 步未走完），已停止寻路", elapsed);
                    }

                    // 3) 模态/过场打断
                    if (!SafePlayerFree() || Game1.activeClickableMenu != null || SafeEventOrDialogue())
                    {
                        try { Game1.player.controller = null; } catch { }
                        return this.Fail("ui_modal", "移动过程中被菜单/对话/过场打断，已停止寻路", elapsed);
                    }

                    // 4) 卡死检测：像素位置长时间不变
                    Vector2 pos = Game1.player.Position;
                    if (Vector2.DistanceSquared(pos, _lastPosition) > 4f)
                    {
                        _lastPosition = pos;
                        _stuckFrames = 0;
                    }
                    else
                    {
                        _stuckFrames++;
                        if (_stuckFrames > StuckFrames)
                        {
                            try { Game1.player.controller = null; } catch { }
                            return this.Fail("blocked",
                                $"角色在 {FormatTile(_target)} 途中被挡住（约 {StuckFrames / 60.0:0.0} 秒没有位移），已停止寻路", elapsed);
                        }
                    }

                    return null;   // 继续走
                }
                catch (Exception ex)
                {
                    // 技能内部异常：保证清理控制器，再把异常摘要交回网络线程。
                    try { if (Game1.player != null) Game1.player.controller = null; } catch { }
                    return this.Fail("error", "move_to 执行异常：" + ex.GetType().Name + ": " + ex.Message,
                        this._started ? (long)(DateTime.UtcNow - _startedAtUtc).TotalMilliseconds : 0);
                }
            }

            /// <summary>前置校验 + 发起寻路。返回 null 表示已经发起、需要后续 tick 推进。</summary>
            private object Begin()
            {
                _started = true;
                _startedAtUtc = DateTime.UtcNow;
                _seqBefore = _world.WorldSeq;

                // ---- 前置校验 ----
                if (!Context.IsWorldReady || Game1.player == null || Game1.currentLocation == null)
                    return this.Fail("no_save", "尚未加载存档，无法执行 move_to", 0);

                if (_target.X == int.MinValue || _target.Y == int.MinValue)
                    return this.Fail("precondition_failed", "缺少参数 args.tile（期望 [x, y] 两个整数）", 0);

                if (this.IsUiBlocked())
                    return this.Fail("ui_modal", "当前有菜单/对话/过场打开，无法移动（请先关闭模态）", 0);

                if (_target.X < 0 || _target.Y < 0)
                    return this.Fail("precondition_failed", $"目标格 {FormatTile(_target)} 坐标为负数，非法", 0);

                // 目标必须在当前地点内 —— 跨地点移动属于里程碑 B
                int maxX = int.MaxValue, maxY = int.MaxValue;
                try
                {
                    maxX = Game1.currentLocation.Map.DisplayWidth / Game1.tileSize;
                    maxY = Game1.currentLocation.Map.DisplayHeight / Game1.tileSize;
                }
                catch { }

                if (_target.X >= maxX || _target.Y >= maxY)
                {
                    return this.Fail("precondition_failed",
                        $"目标格 {FormatTile(_target)} 不在当前地点 {Game1.currentLocation.Name} 内（该地点尺寸 {maxX}x{maxY}）；跨地点移动尚未实现",
                        0);
                }

                if (!SafeStandable(_target, out Furniture blocking))
                {
                    return this.Fail("unreachable",
                        $"目标格 {FormatTile(_target)} 不可通行（被建筑/水面/障碍占据），无法走上去", 0);
                }

                if (blocking != null)
                {
                    // 家具（床/桌椅/箱子摆放位）单独报 precondition_failed：
                    // 这不是“走不到”，而是“这个格子本来就不该被当成落脚点”。
                    // 真机教训：派到床格会先成功到达，再弹出睡觉确认框冻结整个世界时间；
                    // 提前挡住比事后补救便宜得多。
                    string kind = blocking is StardewValley.Objects.BedFurniture ? "床/家具" : blocking.GetType().Name;
                    return this.Fail("precondition_failed",
                        $"目标格 {FormatTile(_target)} 有家具（{kind}），不能作为落脚点；请改选旁边的空地板格", 0);
                }

                // ---- 发起寻路 ----
                try
                {
                    Game1.player.controller = null;   // 清掉可能残留的旧控制器

                    var ctrl = new PathFindController(Game1.player, Game1.currentLocation, _target, 0);
                    Game1.player.controller = ctrl;

                    int steps = 0;
                    try { steps = ctrl.pathToEndPoint?.Count ?? 0; } catch { steps = 0; }
                    _pathSteps = steps;

                    // A* 无解（目标被围死）：路径为空且人不在目标格上 → 立刻放弃，不空等
                    if (steps == 0 && Game1.player.TilePoint != _target)
                    {
                        Game1.player.controller = null;
                        return this.Fail("unreachable",
                            $"寻路无法到达 {FormatTile(_target)}（A* 未算出路径，目标可能被围住）", 0);
                    }

                    _lastPosition = Game1.player.Position;
                    _stuckFrames = 0;

                    return null;   // 交给后续 tick 推进
                }
                catch (Exception ex)
                {
                    try { Game1.player.controller = null; } catch { }
                    return this.Fail("error", "发起寻路失败：" + ex.GetType().Name + ": " + ex.Message, 0);
                }
            }

            private bool IsUiBlocked()
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

            /// <summary>
            /// 这一格角色站得上去吗。
            /// 放置物一律挡路；地形特征里树/灌木/资源堆挡路，草地与耕地能走；
            /// 家具（床/桌椅等）通过 <paramref name="blockingFurniture"/> 单独报出，由调用方区分处理：
            /// “有家具”是**前置条件不满足**，而不是“A* 走不到”。
            /// 建筑与围墙这里判不准，由“A* 无解立即放弃 + 卡死检测”兜底。
            /// </summary>
            /// <param name="blockingFurniture">该格上的家具（没有则为 null）。</param>
            private static bool SafeStandable(Point p, out Furniture blockingFurniture)
            {
                blockingFurniture = null;
                try
                {
                    GameLocation loc = Game1.currentLocation;
                    if (loc == null) return false;

                    var tile = new Vector2(p.X, p.Y);

                    // ---- 家具检查（v2 新增）----
                    //
                    // 1.6.x 的 loc.furniture 是 NetCollection<Furniture>，**直接 foreach 遍历**
                    // （没有 .Pairs，那是 objects/terrainFeatures 的写法）。
                    // 床尤其重要：它自带碰撞，A* 永远绕不进去，只会浪费一次 8 秒超时或报“A* 无解”。
                    try
                    {
                        if (loc.furniture != null)
                        {
                            foreach (Furniture f in loc.furniture)
                            {
                                if (f == null) continue;
                                if (f.TileLocation == tile) { blockingFurniture = f; return false; }
                            }
                        }
                    }
                    catch { }

                    if (loc.objects != null && loc.objects.ContainsKey(tile)) return false;
                    if (loc.isWaterTile(p.X, p.Y)) return false;

                    if (loc.terrainFeatures != null && loc.terrainFeatures.TryGetValue(tile, out StardewValley.TerrainFeatures.TerrainFeature tf) && tf != null)
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

            private static bool SafePlayerFree()
            {
                try { return Context.IsPlayerFree; } catch { return false; }
            }

            private static bool SafeEventOrDialogue()
            {
                try { return Game1.eventUp || Game1.dialogueUp; } catch { return false; }
            }

            private static string FormatTile(Point p) => $"({p.X},{p.Y})";
        }
    }
}
