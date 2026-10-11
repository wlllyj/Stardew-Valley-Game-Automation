using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Objects;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【里程碑 B】跨地点移动 <c>move_to_location</c>：把玩家从"当前所在地点"带到"目标地点"，
    /// 可选到达后在目标地点内再走一格（<c>args.tile</c>）。
    ///
    /// 请求：<c>{"skill":"move_to_location","args":{"location":"Farm","tile":[64,15]}}</c>（tile 可省）
    ///
    /// ==================================================================
    ///  一、地点图从哪来（§5.2.1 铁律：禁止硬编码地名/坐标）
    /// ==================================================================
    /// 节点与边**全部从游戏真值读**：每个 <c>Game1.locations[i].Name</c> 是节点，
    /// 每条 <c>GameLocation.warps</c> 里的 <c>Warp</c> 是一条边
    /// （<c>Warp.X/Y</c> = 源格，<c>Warp.TargetName</c> = 目标地点，<c>Warp.TargetX/Y</c> = 落点）。
    /// 然后从当前地点到目标地点做 **BFS**（传送次数最少）。详见 <see cref="LocationGraph"/>。
    ///
    /// 因此"FarmHouse 的门在 (x,y)"这类常量在这里**一个都没有** ——
    /// 门就是地图 `Warps` 图层上的一条 warp，源格与目标地名都由地图给，换存档也不会失效。
    ///
    /// ==================================================================
    ///  二、一跳是怎么执行的（多跳、跨帧）
    /// ==================================================================
    /// 每一跳 = 「在当前地点内走到某个 warp 的**源格** → 等游戏真的把玩家传送过去」。
    ///
    /// 移动复用 <see cref="StepMover"/>（与 <c>move_to</c> 同一套状态机）：
    /// 发起 <c>new PathFindController(player, loc, 源格, 0)</c>，之后每 tick 推进一次。
    ///
    /// 【为什么传送门会自己触发，而不是我们自己调 warp】
    /// 1.6.15 的 `Farmer.MovePositionImpl` 在**移动过程中**会调
    /// `GameLocation.isCollidingWithWarp(玩家像素矩形, 玩家)`，命中就 `Game1.warpFarmer(warp, ...)`
    /// （IL 实证，见 docs/_milestone-b-design.md）。也就是说：
    /// **只要角色真的从触发格/门口走过，游戏自己就把人送过去了。**
    /// 这正好绕开本项目的硬纪律①「不允许伪造键鼠输入」—— 我们只下寻路目标，不合成任何输入事件；
    /// 也**绝不**自己调 `Game1.warpFarmer`（那等于绕过游戏规则瞬移，属于作弊，且会让"判据"变成自证）。
    ///
    /// 于是每一跳的候选落脚点（<see cref="BuildCandidates"/>）是：
    ///   ① warp 源格本身；
    ///   ② 沿"玩家来的方向"**穿过**源格的那一格（人要撞到门上才会被传送，斜着站也没关系）；
    ///   ③ 源格四邻（有些门只认"贴着"）；
    ///   ④ 同目标的多条 warp（同一地点可能有不止一个出口通往同一个地方）。
    /// 一个候选走完还没触发就换下一个；全部用完 → 这一跳失败。
    ///
    /// ==================================================================
    ///  三、判据（条目 013 的教训：绝不"大概到了就报 ok"）
    /// ==================================================================
    /// 一跳成功的**唯一**判据是 <c>Game1.currentLocation.Name</c> 真的变成了别的地点 ——
    /// 这是我们能拿到的、关于"世界真的换了"的最强事实。拿不到（读出来是 null）一律**不当成功**，
    /// 继续等到超时为止。**不允许**用"位置接近落点""走了 N 格""控制器结束"之类推断代替它。
    ///
    /// 并且：地点一旦变化，就**不假设**传送门去了地图上写的地方 ——
    /// 立即用"现在真实所在的地点"重新建图、重新 BFS（<see cref="Replan"/>）。
    /// 回执里每跳同时给出 `to`（warp 上写的目标）与 `arrivedAt`（**实际观测到的**地点），
    /// 两者不一致时 `result="mismatch"`，脑可以据此审计。
    ///
    /// 【另一条 013 教训用在传送上】传送落地后**先等 <see cref="SettleTicks"/> 个 tick** 确认地点不再变，
    /// 再走下一跳 —— 不然"刚落地那一帧"读到的世界可能还在切换（双传送/淡入淡出），
    /// 拿它当依据去下下一步就会重演"模态已关闭≠世界已恢复"。
    ///
    /// ==================================================================
    ///  四、失败要可操作
    /// ==================================================================
    ///   * <c>precondition_failed</c> —— 地点名不存在 / 坐标为负 / 目标格有阻挡家具；
    ///     reason 里给出**当前地点能直接去的地方**（直连邻居列表）。
    ///   * <c>unreachable_no_route</c> —— warp 图上无路；reason 里给直连邻居 + 图规模。
    ///   * <c>hop_failed</c> —— 走到了 warp 触发格但地点没变（传送门没触发）；reason 里给
    ///     源格/落点/试过的所有格子。
    ///   * <c>unreachable</c> —— warp 源格本身走不到（A* 无解）。
    ///   * <c>blocked</c> —— 卡死（与 move_to 同一套像素位移判据）。
    ///   * <c>timeout</c> —— 单跳超时或整体超时（沿用 <see cref="Skills.ClampTimeout"/>）。
    ///   * <c>ui_modal</c> —— 被菜单/对话/过场打断。
    /// 无论如何，失败回执也会带上已经走过的 `path` 与每一跳的 `hops`，便于脑看到"走到哪一步断的"。
    /// </summary>
    internal sealed class MoveToLocationSkill
    {
        /// <summary>单跳的默认时间预算（还会被"整体剩余时间"再夹一次，绝不会越过总预算）。</summary>
        private const int HopTimeoutMs = 8000;

        /// <summary>传送落地后先等几个 tick 再走下一跳（等世界稳定，见类注释第三节）。</summary>
        private const int SettleTicks = 2;

        /// <summary>单跳最多尝试多少个候选格（防坏图导致一拍子试几十个格子）。</summary>
        private const int MaxCandidates = 16;

        /// <summary>路由跳数上限（防坏图/环路导致的长链）。</summary>
        private const int MaxHops = 24;

        /// <summary>最多重新规划几次（防两个 warp 把人来回弹，变成 ping-pong）。</summary>
        private const int MaxReplans = 10;

        private enum Phase
        {
            None,
            Settle,      // 刚落地的稳定期
            Walk,        // 正在走向某个候选格
            Push,        // 已到门前，正在"朝门里推"（门的触发靠撞，不靠站）
            FinalWalk,   // 已经到达目标地点，正在走 args.tile
        }

        /// <summary>
        /// "门口动作"最多持续多少帧（60fps 下约 **3 秒**）。
        ///
        /// 【为什么从 1 秒放宽到 3 秒（真机教训 2026-10-11 20:0x）】`checkAction` 触发的门/建筑传送
        /// 是**异步**的：`Game1.warpFarmer` 先起淡出，地点切换要 ~0.6~2 秒。
        /// 原先 60 帧（1 秒）就放弃，于是 hop 先被判 `hop_failed`、随后玩家才真的进了屋
        /// （真机证据：`goto FarmHouse` 报 hop_failed，而下一次观测人已经在 FarmHouse(3,11)）。
        /// 这就是"回执与事实相反"的老毛病，必须靠**等够 + 传送期间不下结论**来治。
        /// </summary>
        private const int PushFrames = 180;

        private sealed class HopCandidate
        {
            public Point Tile;
            public LocationGraph.Edge Edge;
            public string Kind;   // source / cross / neighbor / retry / alt_source / door_push ...
            /// <summary>非 null = 走到 <see cref="Tile"/> 之后要朝这一格"推"（门格，走不上去但撞得到）。</summary>
            public Point? PushInto;
        }

        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly int _timeoutMs;
        private readonly string _targetLocation;
        private readonly Point _targetTile;
        private readonly bool _hasTile;
        private readonly bool _allowBed;

        private bool _started;
        private DateTime _startedAtUtc;
        private long _seqBefore;

        private string _startLocation;
        private string _observedLocation;     // 最近一次**观测到**的地点名（唯一权威事实）
        private string _targetLocationResolved;   // 大小写规范化后的目标地点名（图上的规范名）
        private LocationGraph _graph;

        private List<LocationGraph.Edge> _route = new List<LocationGraph.Edge>();
        private readonly List<string> _pathSoFar = new List<string>();
        private readonly List<HopView> _hops = new List<HopView>();
        private int _hopIndex;
        private int _replans;

        private Phase _phase = Phase.None;
        private int _settleTicks;
        private DateTime _hopStartedAtUtc;

        // 当前跳
        private List<HopCandidate> _candidates = new List<HopCandidate>();
        private int _candidateIndex;
        private StepMover _mover;
        private GameLocation _hopLocation;   // 这一跳所在的地图（发起时捕获，避免中途读串图）
        private StepMover _finalMover;
        private DateTime _finalStartedAtUtc;
        private Point _pushTarget;        // 门口动作/挤压的目标格（门格）
        private Vector2 _pushStartPos;    // 开始动作/挤压时玩家的像素位置（诊断"到底动没动"）
        private int _pushFramesLeft;
        private readonly List<Point> _reachedTiles = new List<Point>();       // 真的站上了 warp 源格、却没触发传送的格子
        private readonly List<Point> _reachedNearTiles = new List<Point>();   // 只走到源格附近（四邻/穿过格）的格子
        private readonly List<string> _attemptStatuses = new List<string>();
        private readonly List<string> _attemptText = new List<string>();

        public MoveToLocationSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._world = world;
            this._monitor = monitor;
            this._timeoutMs = Skills.ClampTimeout(req?.TimeoutMs);
            this._targetLocation = req?.Args?.Location;

            int[] tile = req?.Args?.Tile;
            this._hasTile = tile != null && tile.Length >= 2;
            this._targetTile = this._hasTile ? new Point(tile[0], tile[1]) : new Point(int.MinValue, int.MinValue);
            this._allowBed = req?.Args?.AllowBed ?? false;
        }

        // ==================================================================
        //  回执
        // ==================================================================

        private ExecResponse Fail(string status, string reason, long elapsedMs)
            => new ExecResponse
            {
                Ok = false,
                Status = status,
                Skill = "move_to_location",
                Reason = reason,
                ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
                // 失败也要交出"走到哪一步断的"，否则脑没法审计、没法换策略。
                Path = this._pathSoFar.Count > 0 ? this._pathSoFar.ToArray() : null,
                Hops = this._hops.Count > 0 ? this._hops.ToArray() : null,
            };

        private ExecResponse Ok(long elapsedMs)
        {
            var r = new ExecResponse
            {
                Ok = true,
                Status = "ok",
                Skill = "move_to_location",
                Reason = this._hops.Count == 0
                    ? $"已经在 {this._targetLocation}（无需跨地点移动）"
                    : $"已从 {this._startLocation} 到达 {this._targetLocation}（{this._hops.Count} 跳）",
                ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
                Path = this._pathSoFar.ToArray(),
                Hops = this._hops.ToArray(),
            };

            // 与 move_to 一致：到达后如果顺手弹出了模态，如实报回去（脑再决定 dismiss_modal）。
            try
            {
                r.UiOpened = Game1.activeClickableMenu != null;
                if (r.UiOpened) r.ActiveMenuText = UiRead.ActiveMenuText();
            }
            catch { }

            return r;
        }

        private long Elapsed() => (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds;

        private static bool Same(string a, string b) => string.Equals(a, b, StringComparison.Ordinal);

        // ==================================================================
        //  主循环
        // ==================================================================

        /// <summary>每次被主线程调用：返回 null = 还没走完，返回非 null = 终态。</summary>
        public object Step()
        {
            try
            {
                if (!this._started) return this.Begin();

                long elapsed = this.Elapsed();

                // 0) 整体超时（先判，保证任何阶段都不会越过总预算）
                if (elapsed >= this._timeoutMs)
                {
                    return this.Fail("timeout",
                        $"move_to_location 整体超时（{this._timeoutMs}ms 预算用尽）："
                        + $"起点 {this._startLocation}，目标 {this._targetLocation}，"
                        + $"已走 {this._hops.Count} 跳，当前停在 {this._observedLocation ?? "（读不到）"}",
                        elapsed);
                }

                // 1) 事实优先：地点是不是真的变了？（这是唯一的一跳成功判据）
                string now = StepMover.CurrentLocationName();
                if (now != null && !Same(now, this._observedLocation))
                {
                    this.NoteLocationChange(now, elapsed);
                    return this.AfterLocationChange(now, elapsed);
                }

                // 2) 模态/对话/过场：所有阶段都不可继续
                if (StepMover.UiBlocked() && this._phase != Phase.Settle)
                {
                    this.CancelMovers();
                    return this.Fail("ui_modal",
                        $"移动过程中被菜单/对话/过场打断，已停止移动（当前 {this._observedLocation ?? "（读不到）"}，"
                        + $"目标 {this._targetLocation}）",
                        elapsed);
                }

                switch (this._phase)
                {
                    case Phase.Settle: return this.TickSettle(elapsed);
                    case Phase.Walk: return this.TickWalk(elapsed);
                    case Phase.Push: return this.TickPush(elapsed);
                    case Phase.FinalWalk: return this.TickFinal(elapsed);
                    default:
                        this.CancelMovers();
                        return this.Fail("error", "move_to_location 内部状态机异常（阶段未初始化）", elapsed);
                }
            }
            catch (Exception ex)
            {
                this.CancelMovers();
                return this.Fail("error", "move_to_location 执行异常：" + ex.GetType().Name + ": " + ex.Message,
                    this._started ? this.Elapsed() : 0);
            }
        }

        /// <summary>前置校验 + 建图 + 求路由 + 起第一跳。返回 null 表示已上路，需要后续 tick 推进。</summary>
        private object Begin()
        {
            this._started = true;
            this._startedAtUtc = DateTime.UtcNow;
            this._seqBefore = this._world.WorldSeq;

            // ---- 前置校验 ----
            if (!Context.IsWorldReady || Game1.player == null || Game1.currentLocation == null)
                return this.Fail("no_save", "尚未加载存档，无法执行 move_to_location", 0);

            if (string.IsNullOrEmpty(this._targetLocation))
                return this.Fail("precondition_failed",
                    "缺少参数 args.location（期望地点名，例如 \"Farm\"）；也可用 observe 快照的 currentLocation 与 warp 列表来确认地名",
                    0);

            if (this._hasTile && (this._targetTile.X < 0 || this._targetTile.Y < 0))
                return this.Fail("precondition_failed",
                    $"目标格 {StepMover.FormatTile(this._targetTile)} 坐标为负数，非法", 0);

            if (StepMover.UiBlocked())
                return this.Fail("ui_modal", "当前有菜单/对话/过场打开，无法移动（请先关闭模态）", 0);

            this._startLocation = StepMover.CurrentLocationName();
            if (string.IsNullOrEmpty(this._startLocation))
                return this.Fail("precondition_failed", "读不到当前地点名（Game1.currentLocation.Name），无法规划路线", 0);

            this._observedLocation = this._startLocation;
            this._pathSoFar.Add(this._startLocation);

            // ---- 建图（只读游戏真值）----
            try
            {
                this._graph = LocationGraph.Build();
            }
            catch (Exception ex)
            {
                return this.Fail("error", "地点图构建失败：" + ex.GetType().Name + ": " + ex.Message, 0);
            }

            if (this._graph == null || this._graph.LocationCount == 0)
                return this.Fail("precondition_failed",
                    "地点图是空的（Game1.locations 读不到任何地点），疑似还没进过任何地图", 0);

            // ---- 目标地点名规范化 + 存在性 ----
            string target = this._graph.ResolveName(this._targetLocation);
            if (target == null)
            {
                List<string> neighbors = this._graph.DirectNeighbors(this._startLocation);
                string extra = this._graph.HasWarpTarget(this._targetLocation)
                    ? "；注意：图上有 warp **指向**这个地名，但 Game1.locations 里没有同名地点"
                      + "（多半是尚未解锁/尚未建造、此刻还没被游戏创建出来的地图，或者是带唯一后缀的地点名）"
                    : "";
                return this.Fail("precondition_failed",
                    $"地点“{this._targetLocation}”不存在（当前地点 {this._startLocation} 能直接去的地方："
                    + LocationGraph.DescribeNeighbors(neighbors) + $"；当前图规模 {this._graph.Describe()}{extra}）",
                    0);
            }

            this._targetLocationResolved = target;

            if (Same(target, this._startLocation))
                return this.StartFinalWalk(0);      // 已经在该地点：只剩可选的 args.tile

            // ---- BFS 求路由 ----
            List<LocationGraph.Edge> route = this._graph.FindRoute(this._startLocation, target);
            if (route == null)
            {
                List<string> neighbors = this._graph.DirectNeighbors(this._startLocation);
                return this.Fail("unreachable_no_route",
                    $"从 {this._startLocation} 到 {target} 在 warp 图上无路可走"
                    + $"（{this._startLocation} 的直连邻居：{LocationGraph.DescribeNeighbors(neighbors)}；"
                    + $"目标 {target} 的直连邻居：{LocationGraph.DescribeNeighbors(this._graph.DirectNeighbors(target))}；"
                    + $"当前图规模 {this._graph.Describe()}）",
                    0);
            }

            if (route.Count == 0)
                return this.StartFinalWalk(0);

            this._route = route;
            this._hopIndex = 0;
            return this.StartHop(0);
        }

        /// <summary>开一跳：准备候选格、建回执记录，然后开始走向第一个候选。</summary>
        private object StartHop(long elapsed)
        {
            if (this._hopIndex >= this._route.Count)
                return this.StartFinalWalk(elapsed);

            if (this._hops.Count >= MaxHops)
                return this.Fail("hop_failed",
                    $"跳数超过上限 {MaxHops}（疑似 warp 图把人绕圈子），已停止；当前停在 {this._observedLocation}", elapsed);

            LocationGraph.Edge primary = this._route[this._hopIndex];
            string from = this._observedLocation;

            // 事实与计划不一致（例如落点与地图上写的不同）：以事实为准重新规划，绝不用错的起点硬走。
            if (!Same(from, primary.From))
            {
                object replanned = this.Replan(from, elapsed);
                if (replanned != null) return replanned;
                if (this._route.Count == 0 || this._hopIndex >= this._route.Count)
                    return this.StartFinalWalk(elapsed);
                primary = this._route[this._hopIndex];
                from = this._observedLocation;
            }

            GameLocation loc = Game1.currentLocation;
            if (loc == null)
                return this.Fail("no_save", "Game1.currentLocation 读不到，无法移动", elapsed);

            this._hopLocation = loc;
            this._candidates = this.BuildCandidates(loc, primary, from);
            this._candidateIndex = 0;
            this._reachedTiles.Clear();
            this._reachedNearTiles.Clear();
            this._attemptStatuses.Clear();
            this._attemptText.Clear();
            this._mover = null;
            this._hopStartedAtUtc = DateTime.UtcNow;

            this._hops.Add(new HopView
            {
                From = from,
                To = primary.To,
                SourceTile = new[] { primary.Source.X, primary.Source.Y },
                LandingTile = new[] { primary.Landing.X, primary.Landing.Y },
                Result = "running",
            });

            this._phase = Phase.Walk;
            return this.StartCandidate(elapsed);
        }

        /// <summary>依次尝试候选格；能起路就返回 null，全部不行则把这一跳判失败。</summary>
        private object StartCandidate(long elapsed)
        {
            while (this._candidateIndex < this._candidates.Count)
            {
                HopCandidate c = this._candidates[this._candidateIndex];
                long remaining = this._timeoutMs - elapsed;
                int budget = (int)Math.Min(HopTimeoutMs, remaining);
                if (budget < Skills.TimeoutMinMs) budget = Skills.TimeoutMinMs;

                var mover = new StepMover(this._hopLocation ?? Game1.currentLocation, c.Tile, budget, this.HopLabel());
                MoveOutcome o = mover.Begin();

                if (o.Kind == MoveStopKind.Running)
                {
                    this._mover = mover;
                    this.Note("walking", c, "started");
                    return null;   // 交给后续 tick 推进
                }

                this.NoteAttempt(c, o);

                // 模态/异常不可自愈：直接终止整次调用（继续试只会浪费时间）。
                if (o.Kind == MoveStopKind.UiModal || o.Kind == MoveStopKind.Error)
                    return this.FailHop(o.Status, o.Reason, elapsed);

                // 这一格不行（A* 无解 / 已经在上面 / 其它）：换下一格
                this._candidateIndex++;
            }

            return this.FailHopExhausted(elapsed);
        }

        /// <summary>走向候选格的过程判定。地点变化已经在 <see cref="Step"/> 里优先处理掉了。</summary>
        private object TickWalk(long elapsed)
        {
            if (this._mover == null)
            {
                this._candidateIndex++;
                return this.StartCandidate(elapsed);
            }

            long hopElapsed = (long)(DateTime.UtcNow - this._hopStartedAtUtc).TotalMilliseconds;
            MoveOutcome o = this._mover.Tick(hopElapsed);

            switch (o.Kind)
            {
                case MoveStopKind.Running:
                    return null;

                case MoveStopKind.Arrived:
                    {
                        HopCandidate c = this._candidates[this._candidateIndex];

                        // ---- 走到门前那格了：进入"朝门里推"阶段 ----
                        // 门的触发在"移动进门的碰撞判定"里，站着不动不会触发（真机实测）。
                        if (c.PushInto.HasValue)
                        {
                            this._pushTarget = c.PushInto.Value;
                            this._pushFramesLeft = PushFrames;
                            try { this._pushStartPos = Game1.player.Position; } catch { }
                            StepMover.HaltPlayer();   // 先停掉寻路控制器，免得它跟"动作"抢角色

                            // ★ 首选机制：**游戏自己的动作入口** `checkAction`。
                            //   真机实证（0.7.1，2026-10-11 19:5x）：站在 Farm(64,15) 对着门格 (64,14)
                            //   调一次 checkAction 返回 True，**0.6 秒后玩家已经在 FarmHouse(3,11)**
                            //   —— 与 IL 推断完全一致：进建筑走的是 `checkAction → Building.doAction`
                            //   这条"动作"路径，不是碰撞传送（Farm 的 `loc.doors` 是空的）。
                            bool acted = this.TryDoorAction();
                            this.Note("door_action", c,
                                $"arrived → checkAction({StepMover.FormatTile(this._pushTarget)})={acted}");
                            this._attemptStatuses.Add("door_action");
                            this._phase = Phase.Push;
                            return null;
                        }

                        // 走到了却还是没换地图 —— 说明这一格不是有效的触发点（"站上去"不等于"撞上去"）。
                        // 诚实记账，换下一格（例如沿来向穿过源格）。
                        // 只有"真的站上了 warp 源格"才算硬证据；邻居/穿过格只算"到了门口附近"。
                        if (c.Tile == c.Edge.Source) this._reachedTiles.Add(c.Tile);
                        else this._reachedNearTiles.Add(c.Tile);
                        this.NoteAttempt(c, new MoveOutcome(MoveStopKind.Arrived, "走到了但地点没变"));
                        this._attemptStatuses.Add("no_warp");
                        this._mover = null;
                        this._candidateIndex++;
                        return this.StartCandidate(elapsed);
                    }

                case MoveStopKind.LocationChanged:
                    {
                        // 走到了门/warp 上，地点真的变了 —— 这正是这一跳要的结果，**不能**当失败。
                        // 这里只收掉 mover 并返回"还没走完"（null），交给 Step() 下一 tick 的统一路径
                        // （读地点 → NoteLocationChange → AfterLocationChange）去落账与重规划。
                        this._mover = null;
                        return null;
                    }

                default:
                    {
                        this.NoteAttempt(this._candidates[this._candidateIndex], o);
                        if (o.Kind == MoveStopKind.UiModal || o.Kind == MoveStopKind.Error)
                            return this.FailHop(o.Status, o.Reason, elapsed);

                        this._mover = null;
                        this._candidateIndex++;
                        // 时间预算已经烧光的候选会在下一轮 Begin 后立刻 Tick 出 timeout，
                        // 不会真的等满 —— 整体预算还有 Step() 开头的兜底。
                        return this.StartCandidate(elapsed);
                    }
            }
        }

        /// <summary>
        /// 调**游戏自己的动作入口** <c>GameLocation.checkAction(tile, viewport, player)</c>
        /// （api-probe 编译期实证 3 参重载存在）。
        ///
        /// 【为什么门的正道是它】真机 + IL 双重证据：
        ///   * `Farm` 的 `location.doors` 是**空的** ⇒ `isCollidingWithDoors` 无从触发；
        ///   * `GameLocation.checkAction` 的 IL 里遍历 `this.buildings`，调
        ///     `getPointForHumanDoor()` / `getWarpFromDoor(...)` / `Building.doAction(Vector2, Farmer)`；
        ///   * 真机：`checkAction((64,14))` 返回 True 后 0.6 秒进 `FarmHouse(3,11)`。
        /// 与 `dismiss_modal` 用 `answerDialogue` 而不按确认键同一条纪律：调游戏自己的处理函数，不合成键鼠。
        /// </summary>
        private bool TryDoorAction()
        {
            try
            {
                return Game1.currentLocation.checkAction(
                    new xTile.Dimensions.Location(this._pushTarget.X, this._pushTarget.Y),
                    Game1.viewport,
                    Game1.player);
            }
            catch { return false; }
        }

        /// <summary>
        /// "门口动作"阶段：每 15 帧再调一次 <see cref="TryDoorAction"/>（传送有淡出期，不是同一帧生效），
        /// 直到地点变化（由 <see cref="Step"/> 顶部的事实判据统一处理）或推够 <see cref="PushFrames"/> 帧。
        ///
        /// **绝不**在这里下"失败"结论：传送是异步的（`warpFarmer` 发起后有淡出期，
        /// 期间地点还没变、角色不动），任何"卡住/超时"的判据都会误报。
        /// 兜底：`checkAction` 返回 false（这一格没有动作）时，才退到"给定路径朝门走一步"物理挤门。
        /// </summary>
        private object TickPush(long elapsed)
        {
            // ★ **正在传送就别倒计时**：`Game1.locationRequest != null` 说明游戏已经受理了传送、
            //   正在淡出。这段时间里地点还没变、角色也不动，任何"放弃/换候选"的判定都会让回执与事实相反
            //   （真机：hop_failed 之后 0.6 秒人才进屋）。所以传送期间只是等。
            bool warping = false;
            try { warping = Game1.locationRequest != null; } catch { }
            if (warping) return null;

            if (this._pushFramesLeft-- <= 0)
            {
                // 【诊断】把"动作之前/之后"的像素位置一起写进 reason —— 回答"到底动没动"。
                string moved = "（读不到位置）";
                try
                {
                    Vector2 now = Game1.player.Position;
                    moved = $"像素 {this._pushStartPos.X:0},{this._pushStartPos.Y:0} → {now.X:0},{now.Y:0}"
                          + $"（位移 {now.X - this._pushStartPos.X:+0;-0;0},{now.Y - this._pushStartPos.Y:+0;-0;0}）";
                }
                catch { }

                StepMover.HaltPlayer();
                this.Note("door_action", null,
                    $"门口动作/挤压共 {PushFrames} 帧仍未触发传送；{moved}");
                this._mover = null;
                this._phase = Phase.Walk;
                this._candidateIndex++;
                return this.StartCandidate(elapsed);
            }

            // 每 15 帧重试一次动作（首次在进入本阶段时已经调过一次）。
            if (this._pushFramesLeft % 15 == 0)
            {
                bool acted = this.TryDoorAction();
                if (!acted)
                {
                    // 这一格没有动作 ⇒ 退回"把朝门走一步喂给游戏自己的寻路器"的物理挤门。
                    try
                    {
                        if (Game1.player != null && Game1.player.controller == null)
                            StepMover.PushInto(this._pushTarget, this._hopLocation);
                    }
                    catch { }
                }
            }

            return null;   // 地点变化由 Step() 顶部处理
        }

        /// <summary>稳定期：确认地点不再变，再走下一跳（见类注释第三节的 013 教训）。</summary>
        private object TickSettle(long elapsed)        {
            this._settleTicks--;
            if (this._settleTicks > 0) return null;

            if (this._hopIndex >= this._route.Count)
                return this.StartFinalWalk(elapsed);

            return this.StartHop(elapsed);
        }

        /// <summary>到达目标地点后的收尾：可选的 args.tile。</summary>
        private object StartFinalWalk(long elapsed)
        {
            // 跳数用尽（或本来就在目标地点）—— 先落账：地点真的对上才算数
            if (!Same(this._observedLocation, this._targetLocationResolved))
            {
                return this.Fail("hop_failed",
                    $"目标地点没走到：期望 {this._targetLocationResolved}，实际停在 {this._observedLocation ?? "（读不到）"}", elapsed);
            }

            if (!this._hasTile)
                return this.Ok(elapsed);

            // 复用 move_to 的同一条前置判据链（顺序也一样：已在该格 > 家具 > 不可通行）
            if (Game1.player.TilePoint == this._targetTile)
                return this.Ok(elapsed);

            if (this._targetTile.X < 0 || this._targetTile.Y < 0)
                return this.Fail("precondition_failed",
                    $"目标格 {StepMover.FormatTile(this._targetTile)} 坐标为负数，非法", elapsed);

            int maxX = int.MaxValue, maxY = int.MaxValue;
            try { StepMover.SizeFromLayers(Game1.currentLocation, out maxX, out maxY); }
            catch { maxX = int.MaxValue; maxY = int.MaxValue; }

            if (maxX > 0 && maxY > 0 && (this._targetTile.X >= maxX || this._targetTile.Y >= maxY))
            {
                return this.Fail("precondition_failed",
                    $"目标格 {StepMover.FormatTile(this._targetTile)} 不在 {this._observedLocation} 内"
                    + $"（该地点尺寸 {maxX}x{maxY}）", elapsed);
            }

            bool standable = StepMover.Standable(Game1.currentLocation, this._targetTile, this._allowBed, out Furniture blocking);
            if (blocking != null)
            {
                bool isBed = blocking is StardewValley.Objects.BedFurniture;
                string kind = isBed ? "床" : blocking.GetType().Name;
                string why = isBed
                    ? "；床可以踩，但踩上去会触发睡觉确认框（确认框开着时世界时间冻结），所以默认拒绝。"
                      + "若**故意**要引出这个弹窗（例如测试 dismiss_modal），请传 args.allow_bed=true"
                    : "";
                return this.Fail("precondition_failed",
                    $"目标格 {StepMover.FormatTile(this._targetTile)} 有家具（{kind}），不能作为落脚点；请改选旁边的空地板格{why}",
                    elapsed);
            }

            if (!standable)
            {
                return this.Fail("unreachable",
                    $"目标格 {StepMover.FormatTile(this._targetTile)} 不可通行（被建筑/水面/障碍占据），无法走上去", elapsed);
            }

            long remaining = this._timeoutMs - elapsed;
            int budget = (int)Math.Min(HopTimeoutMs, remaining);
            if (budget < Skills.TimeoutMinMs) budget = Skills.TimeoutMinMs;

            var mover = new StepMover(Game1.currentLocation, this._targetTile, budget, "move_to_location 收尾");
            MoveOutcome o = mover.Begin();
            if (o.Kind != MoveStopKind.Running)
                return this.Fail(o.Status, o.Reason, elapsed);

            this._finalMover = mover;
            this._finalStartedAtUtc = DateTime.UtcNow;
            this._phase = Phase.FinalWalk;
            return null;
        }

        private object TickFinal(long elapsed)
        {
            if (this._finalMover == null)
                return this.Ok(elapsed);

            long finalElapsed = (long)(DateTime.UtcNow - this._finalStartedAtUtc).TotalMilliseconds;
            MoveOutcome o = this._finalMover.Tick(finalElapsed);

            switch (o.Kind)
            {
                case MoveStopKind.Running: return null;
                case MoveStopKind.Arrived:
                    this._finalMover = null;
                    return this.Ok(elapsed);
                default:
                    this._finalMover = null;
                    return this.Fail(o.Status, o.Reason, elapsed);
            }
        }

        // ==================================================================
        //  地点变化（一跳成功 / 落点与地图不符 / 收尾途中又换图）
        // ==================================================================

        /// <summary>地点真的变了：落账到回执、更新权威事实、清掉旧控制器。</summary>
        private void NoteLocationChange(string now, long elapsed)
        {
            // 收尾途中又换图：这属于罕见但必须诚实报出的事（例如收尾的格子又是一道门）。
            if (this._phase == Phase.FinalWalk)
            {
                this.Note("final_walk_location_changed", null, $"{this._observedLocation} -> {now}");
            }

            // 把"正在跑"的那一跳落账
            for (int i = this._hops.Count - 1; i >= 0; i--)
            {
                if (this._hops[i].Result == "running")
                {
                    long ms = (long)(DateTime.UtcNow - this._hopStartedAtUtc).TotalMilliseconds;
                    this._hops[i].ArrivedAt = now;
                    this._hops[i].Ms = ms;
                    if (this._candidates != null && this._candidateIndex >= 0 && this._candidateIndex < this._candidates.Count)
                    {
                        Point used = this._candidates[this._candidateIndex].Tile;
                        this._hops[i].UsedSourceTile = new[] { used.X, used.Y };
                    }
                    if (Same(now, this._hops[i].To))
                    {
                        this._hops[i].Result = "ok";
                    }
                    else
                    {
                        this._hops[i].Result = "mismatch";
                        this._hops[i].Detail = $"warp 上写的目标是 {this._hops[i].To}，实际到达 {now}";
                    }
                    break;
                }
            }

            this.CancelMovers();
            this._observedLocation = now;
            if (this._pathSoFar.Count == 0 || !Same(this._pathSoFar[this._pathSoFar.Count - 1], now))
                this._pathSoFar.Add(now);
        }

        /// <summary>地点变化之后决定下一步：到目标了 → 收尾；否则**按事实重新规划**。</summary>
        private object AfterLocationChange(string now, long elapsed)
        {
            this._hopIndex++;

            if (Same(now, this._targetLocationResolved))
                return this.StartFinalWalk(elapsed);

            object failed = this.Replan(now, elapsed);
            if (failed != null) return failed;

            return null;   // 下一 tick 会从新的 Settle 阶段开始走新路由
        }

        /// <summary>
        /// 从"现在真实所在的地点"重新建图 + 重新 BFS。
        /// 【为什么每次都重建】`Game1.locations` 里的建筑内部是**进入之后才存在**的：
        /// 刚落地时那张地图的 warp 可能才第一次可读。重建让我们"每到一个新地方就重新认识世界"，
        /// 而不是拿着进屋前算出来的旧路由硬走。
        /// </summary>
        private object Replan(string from, long elapsed)
        {
            this._replans++;
            if (this._replans > MaxReplans)
            {
                return this.Fail("hop_failed",
                    $"重新规划次数超过上限 {MaxReplans}（疑似 warp 在两地点间来回弹），已停止；当前停在 {from}", elapsed);
            }

            try
            {
                this._graph = LocationGraph.Build();
            }
            catch (Exception ex)
            {
                return this.Fail("error", "地点图重建失败：" + ex.GetType().Name + ": " + ex.Message, elapsed);
            }

            if (this._graph == null || !this._graph.HasLocation(this._targetLocationResolved))
            {
                return this.Fail("precondition_failed",
                    $"到达 {from} 后目标地点“{this._targetLocationResolved}”不在可读的地点集里（地图可能没加载）", elapsed);
            }

            List<LocationGraph.Edge> route = this._graph.FindRoute(from, this._targetLocationResolved);
            if (route == null || route.Count == 0)
            {
                if (route != null && route.Count == 0)
                    return this.StartFinalWalk(elapsed);   // 已经在了（理论上不会到这）

                return this.Fail("unreachable_no_route",
                    $"从 {from} 到 {this._targetLocationResolved} 在 warp 图上无路可走"
                    + $"（{from} 的直连邻居：{LocationGraph.DescribeNeighbors(this._graph.DirectNeighbors(from))}；"
                    + $"当前图规模 {this._graph.Describe()}）",
                    elapsed);
            }

            this._route = route;
            this._hopIndex = 0;
            this._phase = Phase.Settle;
            this._settleTicks = SettleTicks;
            return null;
        }

        // ==================================================================
        //  候选格
        // ==================================================================

        /// <summary>
        /// 为这一跳生成候选落脚点（见类注释第二节）。
        /// 顺序刻意排成"最可能触发传送的排前面"，并且**允许同一个源格多次出现**：
        /// 从不同方向、经过不同邻居之后再踩一次源格，是"站上去没用、要走过去才有用"的兜底。
        /// </summary>
        private List<HopCandidate> BuildCandidates(GameLocation loc, LocationGraph.Edge primary, string from)
        {
            var list = new List<HopCandidate>();

            int maxX = int.MaxValue, maxY = int.MaxValue;
            try { StepMover.SizeFromLayers(loc, out maxX, out maxY); }
            catch { maxX = int.MaxValue; maxY = int.MaxValue; }

            // 同一地点通往同一目标的所有 warp（门可能不止一个）
            var edges = new List<LocationGraph.Edge> { primary };
            foreach (LocationGraph.Edge e in this._graph.EdgesFrom(from))
            {
                if (e == primary) continue;
                if (Same(e.To, primary.To)) edges.Add(e);
            }

            Point playerTile = Game1.player.TilePoint;

            foreach (LocationGraph.Edge e in edges)
            {
                string tag = (e == primary) ? "" : "alt_";

                this.AddCandidate(list, loc, maxX, maxY, e.Source, e, tag + "source");

                // ---- 门格走不上去时：走到能站的邻居，再"朝门里推"（2026-10-11 真机发现）----
                //
                // 症状：`goto FarmHouse` 报 hop_failed，角色走到门前那格 (64,15) 站定、地点没变；
                // 真值：门格 = 农舍这栋 Building 的 `getPointForHumanDoor()` = (64,14)，
                // A* 到 (64,14) 直接无解（那是墙上的门）。而**门的触发在"移动进门的碰撞判定"里**，
                // 站着不动永远不会触发 ⇒ 必须像玩家一样"往门里挤"。
                bool sourceStandable = false;
                try { sourceStandable = StepMover.Standable(loc, e.Source, true, out Furniture _); } catch { }

                // 沿"玩家来的方向"穿过源格：人要撞到门上才会被传送，站上去有时不算。
                int dx = e.Source.X - playerTile.X;
                int dy = e.Source.Y - playerTile.Y;
                if (dx != 0 || dy != 0)
                {
                    Point step = (Math.Abs(dx) >= Math.Abs(dy))
                        ? new Point(Math.Sign(dx), 0)
                        : new Point(0, Math.Sign(dy));
                    this.AddCandidate(list, loc, maxX, maxY,
                        new Point(e.Source.X + step.X, e.Source.Y + step.Y), e, tag + "cross");
                }

                // 源格四邻：有些门只认"贴着"，站上去反而不行
                var neighbors = new List<Point>
                {
                    new Point(e.Source.X, e.Source.Y - 1),
                    new Point(e.Source.X + 1, e.Source.Y),
                    new Point(e.Source.X, e.Source.Y + 1),
                    new Point(e.Source.X - 1, e.Source.Y),
                };
                neighbors.Sort((a, b) =>
                {
                    int ca = Math.Abs(a.X - playerTile.X) + Math.Abs(a.Y - playerTile.Y);
                    int cb = Math.Abs(b.X - playerTile.X) + Math.Abs(b.Y - playerTile.Y);
                    return ca.CompareTo(cb);
                });

                bool anyNeighbor = false;
                foreach (Point n in neighbors)
                {
                    bool standable = false;
                    try { standable = StepMover.Standable(loc, n, true, out Furniture _); } catch { standable = false; }
                    if (!standable) continue;

                    if (this.AddCandidate(list, loc, maxX, maxY, n, e, tag + "neighbor")) anyNeighbor = true;
                    this.AddCandidate(list, loc, maxX, maxY, e.Source, e, tag + "retry");
                }

                if (anyNeighbor)
                {
                    // 再从**邻居那一侧**穿过源格（贴着门往门里挤）
                    foreach (Point n in neighbors)
                    {
                        int sdx = e.Source.X - n.X;
                        int sdy = e.Source.Y - n.Y;
                        if (sdx == 0 && sdy == 0) continue;
                        this.AddCandidate(list, loc, maxX, maxY,
                            new Point(e.Source.X + sdx, e.Source.Y + sdy), e, tag + "push");
                    }
                }

                // 门格走不上去（或这条边本来就是"门"）⇒ 走到能站的邻居，然后**朝门里推**。
                //
                // 【为什么门边要无条件加】`StepMover.Standable` 只懂家具/放置物/水面/地形，
                // **看不懂地图的墙与建筑** —— 农舍的门格 (64,14) 会被它判成"可站"，
                // 于是只生成"走到门口站定"的候选，而站着永远不会触发门（真机实测两次 hop_failed）。
                if (e.IsDoor || !sourceStandable)
                {
                    foreach (Point n in neighbors)
                    {
                        bool here = false;
                        try { here = StepMover.Standable(loc, n, true, out Furniture _); } catch { }
                        if (!here) continue;
                        this.AddCandidate(list, loc, maxX, maxY, n, e, tag + "door_push", e.Source);
                    }
                }
            }

            return list;
        }

        /// <summary>
        /// 加一个候选格。**刻意允许"贴着地图边界外一点"的格子**（最多 2 格）。
        ///
        /// 【为什么：2026-10-11 真机发现】warp 源格可以落在**图层边界之外**：
        /// FarmHouse 的出门 warp 源格是 (3,12)，而该地图所有图层都是 12x12
        /// （合法格 x,y ∈ 0..11）。玩家在游戏里是**往下走出地图边缘**时被
        /// <c>isCollidingWithWarp</c> 抓住传送的 —— IL 实证：它比较的是玩家**像素矩形**的
        /// Left/Right/Top/Bottom 所在格与 <c>warp.X/Y</c>，所以人不需要"站在"那一格上。
        /// 旧代码的严格边界检查会把这种源格直接丢掉，只剩四邻可试，
        /// 真机症状就是 `hop_failed` 且 reason 里"只试过 1 个候选"。
        /// </summary>
        private bool AddCandidate(List<HopCandidate> list, GameLocation loc, int maxX, int maxY,
            Point tile, LocationGraph.Edge edge, string kind, Point? pushInto = null)
        {
            const int OutOfBoundsMargin = 2;

            if (list.Count >= MaxCandidates) return false;
            if (maxX > 0 && maxY > 0 &&
                (tile.X < -OutOfBoundsMargin || tile.Y < -OutOfBoundsMargin ||
                 tile.X >= maxX + OutOfBoundsMargin || tile.Y >= maxY + OutOfBoundsMargin))
                return false;
            if (tile.X < -OutOfBoundsMargin || tile.Y < -OutOfBoundsMargin) return false;

            if (list.Count > 0)
            {
                HopCandidate last = list[list.Count - 1];
                if (last.Tile == tile && last.Edge == edge) return false;
            }

            list.Add(new HopCandidate { Tile = tile, Edge = edge, Kind = kind, PushInto = pushInto });
            return true;
        }

        // ==================================================================
        //  记账 / 失败装配
        // ==================================================================

        private string HopLabel()
        {
            string to = (this._hopIndex < this._route.Count) ? this._route[this._hopIndex].To : "?";
            return $"move_to_location 第 {this._hopIndex + 1} 跳（{this._observedLocation} → {to}）";
        }

        private void Note(string kind, HopCandidate c, string detail)
        {
            this._attemptText.Add(c == null
                ? $"{kind}:{detail}"
                : $"{kind}:{StepMover.FormatTile(c.Tile)}({c.Kind})={detail}");
        }

        private void NoteAttempt(HopCandidate c, MoveOutcome o)
        {
            this._attemptStatuses.Add(o.Status ?? "running");
            this._attemptText.Add($"{StepMover.FormatTile(c.Tile)}({c.Kind})={o.Status ?? "running"}"
                + (string.IsNullOrEmpty(o.Reason) ? "" : $"[{o.Reason}]"));
        }

        /// <summary>这一跳里出现不可自愈的情况（模态/异常）：终止整次调用。</summary>
        private object FailHop(string status, string reason, long elapsed)
        {
            this.CloseRunningHop(status, reason);
            return this.Fail(status,
                $"{this.HopLabel()}失败（{status}）：{reason}"
                + $"；本次共走 {this._hops.Count} 跳，当前停在 {this._observedLocation}",
                elapsed);
        }

        /// <summary>候选全部用完还在一跳里：按"最有信息量"的口径给状态码。</summary>
        private object FailHopExhausted(long elapsed)
        {
            LocationGraph.Edge primary = (this._hopIndex < this._route.Count) ? this._route[this._hopIndex] : null;
            string from = this._observedLocation;
            string to = primary != null ? primary.To : this._targetLocationResolved;
            string srcTxt = primary != null ? StepMover.FormatTile(primary.Source) : "?";
            string landTxt = primary != null ? StepMover.FormatTile(primary.Landing) : "?";
            string tried = this._attemptText.Count > 0 ? string.Join("；", this._attemptText) : "（没有可用的候选格）";

            string status;
            string reason;

            if (this._reachedTiles.Count > 0)
            {
                // 最有信息量的一种：人**真的**走到了触发格/门口，游戏却没有传送。
                status = "hop_failed";
                reason = $"第 {this._hops.Count} 跳失败（hop_failed）：{from} → {to} 的传送没有触发 —— "
                    + $"角色已经走到 {this.JoinTiles(this._reachedTiles)}（warp 源格 {srcTxt}、落点 {landTxt}），"
                    + $"但 Game1.currentLocation.Name 仍然是 {from}。"
                    + $"该 warp 可能需要先开门/交互才会生效，或者这张地图的 warp 触发区与源格不一致；"
                    + $"本跳试过的格子：{tried}";
            }
            else if (this._attemptStatuses.Contains("blocked"))
            {
                status = "blocked";
                reason = $"第 {this._hops.Count} 跳失败（blocked）：走向 {from} → {to} 的 warp 源格 {srcTxt} 途中被挡住"
                    + $"（与 move_to 同一套判据：像素位置长时间不变）。本跳试过的格子：{tried}";
            }
            else if (this._attemptStatuses.Contains("timeout"))
            {
                status = "timeout";
                reason = $"第 {this._hops.Count} 跳失败（timeout）：走向 {from} → {to} 的 warp 源格 {srcTxt} 超时"
                    + $"（单跳预算 {HopTimeoutMs}ms 或整体剩余时间用尽）。本跳试过的格子：{tried}";
            }
            else if (this._reachedNearTiles.Count > 0)
            {
                // 走到过门口附近，但没能真正站上源格（源格本身多半不可通行：门/台阶）。
                // 这里**不**声称"人已经走到触发格"—— 那是没有的证据。
                status = "hop_failed";
                reason = $"第 {this._hops.Count} 跳失败（hop_failed）：{from} → {to} 的传送没有触发 —— "
                    + $"角色走到了源格附近 {this.JoinTiles(this._reachedNearTiles)}（warp 源格 {srcTxt}、落点 {landTxt}），"
                    + $"但没能真正站上源格，Game1.currentLocation.Name 仍然是 {from}。"
                    + $"本跳试过的格子：{tried}";
            }
            else
            {
                status = "unreachable";
                reason = $"第 {this._hops.Count} 跳失败（unreachable）：{from} 里通往 {to} 的 warp 源格 {srcTxt} 走不到"
                    + $"（A* 在 {from} 内算不出路径）。本跳试过的格子：{tried}";
            }

            this.CloseRunningHop(status, reason);
            return this.Fail(status,
                reason + $"；本次共走 {this._hops.Count} 跳，当前停在 {this._observedLocation}", elapsed);
        }

        private string JoinTiles(List<Point> tiles)
        {
            var parts = new List<string>();
            foreach (Point p in tiles) parts.Add(StepMover.FormatTile(p));
            return string.Join("、", parts);
        }

        /// <summary>把"正在跑"的那一跳落账成失败（回执里每跳的结果必须完整）。</summary>
        private void CloseRunningHop(string status, string detail)
        {
            for (int i = this._hops.Count - 1; i >= 0; i--)
            {
                if (this._hops[i].Result == "running")
                {
                    this._hops[i].Result = status;
                    this._hops[i].Detail = detail;
                    this._hops[i].ArrivedAt = this._observedLocation;
                    this._hops[i].Ms = (long)(DateTime.UtcNow - this._hopStartedAtUtc).TotalMilliseconds;
                    if (this._candidates != null && this._candidateIndex < this._candidates.Count)
                    {
                        Point used = this._candidates[this._candidateIndex].Tile;
                        this._hops[i].UsedSourceTile = new[] { used.X, used.Y };
                    }
                    break;
                }
            }
        }

        private void CancelMovers()
        {
            try { this._mover?.Halt(); } catch { }
            try { this._finalMover?.Halt(); } catch { }
            this._mover = null;
            this._finalMover = null;
        }
    }
}
