using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using StardewValley;
using StardewValley.Buildings;
using StardewValley.Objects;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【里程碑 B】地点拓扑图 —— **每一根边都是从游戏真值读出来的 warp，没有任何硬编码地名/坐标**。
    ///
    /// 建图方式（§5.2.1「禁止硬编码坐标」）：
    ///   节点 = 每个 <c>Game1.locations[i].Name</c>（外加 warp 指向的落点地名，防止目标地点此刻不在 locations 里）；
    ///   边   = `<c>GameLocation.warps</c>` 里的每一条 <c>Warp</c>：
    ///          `Warp.X / Warp.Y` = **源格（在本地点里）**，
    ///          `Warp.TargetName` = 目标地点名，
    ///          `Warp.TargetX / Warp.TargetY` = **落点格（在目标地点里）**。
    ///          【这一点是 1.6.15 的 `Warp..ctor(Int32 x, Int32 y, String targetName, Int32 targetX, Int32 targetY, Boolean flipFarmer, Boolean npcOnly)`
    ///           IL 反汇编直接读出来的，旧项目 `ModEntry.cs:518` 那句「Warp.X/Y 是目标地图坐标」的注释是**错的**。】
    ///
    /// 之所以能"自己发现 FarmHouse 的门在哪"：门就是 FarmHouse 这张地图 `Warps` 图层上的一条 warp，
    /// 源格由地图给、目标地名由地图给。所以换存档/换模组改地图都不会失效。
    ///
    /// 路由 = 在图上做 BFS（边数最少 = 最少次传送），**确定性**（同层按优先级/坐标排序，不依赖字典遍历顺序）。
    /// </summary>
    internal sealed class LocationGraph
    {
        /// <summary>一条传送边。</summary>
        internal sealed class Edge
        {
            /// <summary>出发地点名（本地点，<c>Warp.X/Y</c> 所在的这张地图）。</summary>
            public string From;

            /// <summary>目标地点名（<c>Warp.TargetName</c>）。</summary>
            public string To;

            /// <summary>传送门**源格**（本地点内，<c>Warp.X/Y</c>）—— 玩家得走到这一格（或紧挨着它）才会被传送。</summary>
            public Point Source;

            /// <summary>落点格（目标地点内，<c>Warp.TargetX/TargetY</c>）—— 只用于回执审计，本次不依赖它。</summary>
            public Point Landing;

            /// <summary>
            /// 0 = 源格本身**可站**（最省事：直接走过去就触发）；
            /// 1 = 源格站不上去（门口、水边、装饰格……）：这时要先走到它旁边再"挤"一下。
            ///
            /// 【为什么要这个字段】1.6.15 的 <c>Warp.X/Y</c> 只是**触发区**的锚点，不等于"可以站人的格子"：
            /// 门格常常是 <c>map</c> 上的不可通行物。IL 实证：<c>Game1</c> 只在
            /// <c>Farmer.MovePositionImpl</c>（**移动过程**中）把玩家像素包围盒送到触发格上时才调 <c>Game1.warpFarmer</c>。
            /// 所以这里分两档：能站的源格直接踩；站不上的源格要靠候选序列里的"穿过格/四邻/挤压格"去撞。
            /// </summary>
            public int Priority;

            /// <summary>
            /// 这条边是**建筑的门**（<c>Building.getPointForHumanDoor()</c>），不是 <c>loc.warps</c> 里的 warp。
            ///
            /// 【为什么必须分出来（2026-10-11 真机）】门格通常**站不上去**（在墙上），
            /// 而我们的 <c>Standable</c> 只懂家具/放置物/水面/地形，**看不懂地图的墙与建筑** ——
            /// 于是它会错误地把门格判成"可站"，hop 就只会去"走到门口站定"，而**站着永远不会触发门**
            /// （门的触发在"移动进门的碰撞判定"里）。所以门边必须显式带上这个标记，
            /// 让 hop 生成"走到邻居再朝门里推"的候选。
            /// </summary>
            public bool IsDoor;

            public string Key => $"{this.From}|{this.To}|{this.Source.X},{this.Source.Y}";
        }

        private readonly Dictionary<string, List<Edge>> _out = new Dictionary<string, List<Edge>>(StringComparer.Ordinal);
        private readonly HashSet<string> _nodes = new HashSet<string>(StringComparer.Ordinal);

        /// <summary>真实存在于 <c>Game1.locations</c> 里的地点数。</summary>
        public int LocationCount { get; private set; }

        /// <summary>warp 边总数。</summary>
        public int EdgeCount { get; private set; }

        /// <summary>被跳过的 NPC 专用 warp 数（<c>warp.npcOnly == true</c>，玩家用不了）。</summary>
        public int SkippedNpcOnly { get; private set; }

        /// <summary>被跳过的无名 warp 数（<c>TargetName</c> 为空）。</summary>
        public int SkippedUnnamed { get; private set; }

        /// <summary>诊断串，写进失败回执的 reason，便于脑审计。</summary>
        public string Describe() => $"{this.LocationCount} 个地点 / {this.EdgeCount} 条 warp 边"
            + (this.SkippedNpcOnly > 0 ? $"，跳过 {this.SkippedNpcOnly} 条 NPC 专用" : "")
            + (this.SkippedUnnamed > 0 ? $"，跳过 {this.SkippedUnnamed} 条无名" : "");

        /// <summary>这个地名在图上存在吗（真实地点，或至少被某条 warp 指向）。</summary>
        public bool HasLocation(string name) => name != null && this._nodes.Contains(name);

        /// <summary>
        /// 把调用方给的地名**规范化**成图上的名字（大小写不敏感），找不到返回 null。
        ///
        /// 【为什么只做名字匹配、不做任何猜测】脑可能写 <c>"farm"</c> 而游戏里是 <c>"Farm"</c>。
        /// 只做大小写折叠已经是"承认名字"的极限；**不允许**再做前缀匹配、别名表、相似度之类的猜测 ——
        /// 猜错的地点名会变成"基于错误事实的正确推理"，这正是 §5.2.1 要根除的旧方案病灶。
        /// 匹配不上就老老实实 <c>precondition_failed</c>，并列出当前地点能直接去的地方。
        /// </summary>
        public string ResolveName(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            if (this._nodes.Contains(name)) return name;

            foreach (string node in this._nodes)
            {
                if (string.Equals(node, name, StringComparison.OrdinalIgnoreCase)) return node;
            }

            return null;
        }

        /// <summary>
        /// 从游戏真值建图。**只读**：读 `Game1.locations` / `loc.Name` / `loc.warps` / warp 的四个坐标与目标名，
        /// 不写任何游戏状态，也不调用 `GameLocation.updateWarps()`（那是 `warps.Clear()` + 按地图重建，属于状态写入）。
        /// </summary>
        public static LocationGraph Build()
        {
            var g = new LocationGraph();

            IList<GameLocation> locations = null;
            try { locations = Game1.locations; } catch { }

            if (locations != null)
            {
                for (int i = 0; i < locations.Count; i++)
                {
                    GameLocation loc = locations[i];
                    if (loc == null) continue;

                    string name = null;
                    try { name = loc.Name; } catch { }
                    if (string.IsNullOrEmpty(name)) continue;

                    g.NoteNode(name);
                    g.LocationCount++;
                    if (!g._out.ContainsKey(name)) g._out[name] = new List<Edge>();

                    List<Warp> warps = null;
                    try
                    {
                        if (loc.warps != null)
                        {
                            warps = new List<Warp>();
                            for (int k = 0; k < loc.warps.Count; k++)
                            {
                                Warp w = null;
                                try { w = loc.warps[k]; } catch { }
                                if (w != null) warps.Add(w);
                            }
                        }
                    }
                    catch { warps = null; }

                    if (warps != null && warps.Count > 0)
                    {
                        foreach (Warp w in warps)
                        {
                            string to = null;
                            int sx = 0, sy = 0, lx = 0, ly = 0;
                            bool npcOnly = false;

                            try
                            {
                                to = w.TargetName;
                                sx = w.X;
                                sy = w.Y;
                                lx = w.TargetX;
                                ly = w.TargetY;
                                npcOnly = w.npcOnly != null && w.npcOnly.Value;
                            }
                            catch { continue; }

                            if (npcOnly) { g.SkippedNpcOnly++; continue; }        // NPC 专用，玩家踩上去不会传送
                            if (string.IsNullOrEmpty(to)) { g.SkippedUnnamed++; continue; }   // 无名 warp，无法用于规划

                            AddEdge(g, loc, name, to, new Point(sx, sy), new Point(lx, ly));
                        }
                    }

                    // ---- 门（Door）：`loc.doors` 才是**权威触发格**（v0.6.2 补上）----
                    //
                    // 【IL 实证】`GameLocation.isCollidingWithDoors(Rectangle, Character)` 遍历的是
                    // **`this.doors`**（`NetPointDictionary<string,NetString>`：门格 → 门类型），
                    // 拿玩家像素矩形**四个角**所在格逐个比对；命中后才 `getWarpFromDoor(point, character)`
                    // 解析出真正的 `Warp`。所以：
                    //   * 门格必须从这份字典读（`Building.getPointForHumanDoor()` 只是其中一条解析路径）；
                    //   * 触发要求"**移动中**有角落进门格"，站着不动不会触发。
                    try
                    {
                        if (loc.doors != null && Game1.player != null)
                        {
                            foreach (KeyValuePair<Microsoft.Xna.Framework.Point, string> kv in loc.doors.Pairs)
                            {
                                Warp dw = null;
                                try { dw = loc.getWarpFromDoor(kv.Key, Game1.player); } catch { continue; }
                                if (dw == null) continue;

                                string to = null;
                                int lx = 0, ly = 0;
                                try { to = dw.TargetName; lx = dw.TargetX; ly = dw.TargetY; } catch { continue; }
                                if (string.IsNullOrEmpty(to)) continue;

                                AddEdge(g, loc, name, to, kv.Key, new Point(lx, ly), isDoor: true);
                            }
                        }
                    }
                    catch { }

                    // ---- 建筑的门：作为**补充**（有些建筑的门不在 doors 字典里，或字典还没建好）----
                    //
                    // 【症状】`move_to_location FarmHouse` 报「从 Farm 到 FarmHouse 在 warp 图上无路可走
                    //   （Farm 的直连邻居：Backwoods、BusStop、FarmCave、Forest）」，而反向
                    //   FarmHouse → Farm 是有边的 —— 因为**回屋走的是"门"，不是 `loc.warps` 里的 warp**：
                    //   农舍本身是 Farm 地图上的一栋 `Building`。
                    //
                    // 【解析方式照抄游戏自己】`GameLocation.getWarpFromDoor(Point, Character)` 的 IL
                    //   （1.6.15）对 buildings 分支就是这么写的：
                    //     门格  = b.getPointForHumanDoor()
                    //     目标  = b.GetIndoors().NameOrUniqueName
                    //     落点  = 室内第一条 warp 的 (X, Y - 1)   ← 游戏原文就是 `warps[0].Y - 1`
                    //   一个常量坐标都没有，全部来自游戏真值。与上面的 doors 分支由 AddEdge 去重。
                    try
                    {
                        if (loc.buildings != null)
                        {
                            foreach (Building b in loc.buildings)
                            {
                                if (b == null) continue;

                                Point door;
                                string to;
                                Point landing;
                                try
                                {
                                    door = b.getPointForHumanDoor();

                                    GameLocation indoors = b.GetIndoors();
                                    if (indoors == null) continue;

                                    to = indoors.NameOrUniqueName;
                                    if (string.IsNullOrEmpty(to)) continue;

                                    // 落点照游戏自己的算法；室内没有 warp 时给 (0,0) 并在 reason/回执里
                                    // 由"实际观测到的地点"兜底（我们**从不**假设落点）。
                                    var lp = new Point(0, 0);
                                    if (indoors.warps != null && indoors.warps.Count > 0 && indoors.warps[0] != null)
                                        lp = new Point(indoors.warps[0].X, indoors.warps[0].Y - 1);
                                    landing = lp;
                                }
                                catch { continue; }

                                AddEdge(g, loc, name, to, door, landing, isDoor: true);
                            }
                        }
                    }
                    catch { }
                }
            }

            // 确定性排序：先"源格能站"的，再按目标名/坐标。BFS 的同层顺序因此完全可复现。
            foreach (KeyValuePair<string, List<Edge>> kv in g._out)
            {
                kv.Value.Sort((a, b) =>
                {
                    int c = a.Priority.CompareTo(b.Priority);
                    if (c != 0) return c;
                    c = string.CompareOrdinal(a.To, b.To);
                    if (c != 0) return c;
                    c = a.Source.Y.CompareTo(b.Source.Y);
                    if (c != 0) return c;
                    return a.Source.X.CompareTo(b.Source.X);
                });
            }

            return g;
        }

        /// <summary>
        /// 加一条边（warp 与门共用）：去重 + 标记"源格能不能站"的优先级。
        /// 【为什么要标记】能站的源格走上去就可能触发；不能站的（例如室内出口 warp 落在图层外、
        /// 或门格被家具压住）要排在后面，由 hop 逻辑靠"多候选"兜底。
        /// </summary>
        private static void AddEdge(LocationGraph g, GameLocation loc, string from, string to,
            Point source, Point landing, bool isDoor = false)
        {
            if (string.IsNullOrEmpty(from) || string.IsNullOrEmpty(to)) return;
            if (!g._out.ContainsKey(from)) g._out[from] = new List<Edge>();

            // 去重：同一地点上完全相同的 (目标, 源格) 只留一条（个别地图会重复声明，门与 warp 也可能重叠）。
            foreach (Edge old in g._out[from])
            {
                if (old.To == to && old.Source == source) { old.IsDoor |= isDoor; return; }
            }

            bool standable = false;
            try { standable = StepMover.Standable(loc, source, true, out Furniture _); } catch { standable = false; }

            g._out[from].Add(new Edge
            {
                From = from,
                To = to,
                Source = source,
                Landing = landing,
                Priority = standable ? 0 : 1,
                IsDoor = isDoor,
            });
            g.EdgeCount++;
            g.NoteNode(to);   // 落点地名也登记成节点（万一它此刻不在 locations 里，路由仍然算得出来）
        }

        private void NoteNode(string name)
        {
            if (!string.IsNullOrEmpty(name)) this._nodes.Add(name);
        }

        /// <summary>从某地点出发的所有边（已排序；可能为空列表，绝不为 null）。</summary>
        public List<Edge> EdgesFrom(string from)
        {
            if (from != null && this._out.TryGetValue(from, out List<Edge> list)) return list;
            return new List<Edge>();
        }

        /// <summary>和某地点**直接相邻**（一条 warp 直达）的地点名，去重 + 排序。失败回执里要用它。</summary>
        public List<string> DirectNeighbors(string from)
        {
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (Edge e in this.EdgesFrom(from)) seen.Add(e.To);
            var list = new List<string>(seen);
            list.Sort(StringComparer.Ordinal);
            return list;
        }

        /// <summary>
        /// 图上有没有哪条 warp 把某个地点名当作目标（大小写不敏感）。
        ///
        /// 【用途】调用方要的地点名在 <c>Game1.locations</c> 里查不到、但确实被某条 warp 指着时，
        /// 说明它多半是"还没被游戏创建出来"的地图（未解锁/未建造）。这时 <c>precondition_failed</c> 的
        /// reason 里必须把这个事实说出来，否则脑只会看到"地名不存在"，白白重试。
        /// </summary>
        public bool HasWarpTarget(string name)
        {
            if (string.IsNullOrEmpty(name)) return false;

            foreach (KeyValuePair<string, List<Edge>> kv in this._out)
            {
                foreach (Edge e in kv.Value)
                {
                    if (e.To != null && string.Equals(e.To, name, StringComparison.OrdinalIgnoreCase)) return true;
                }
            }

            return false;
        }

        /// <summary>把一个邻居列表渲染成 reason 里能直接读的一句话。</summary>
        public static string DescribeNeighbors(List<string> neighbors)
        {
            if (neighbors == null || neighbors.Count == 0) return "（无 —— 这个地点没有任何 warp 出口）";
            return string.Join("、", neighbors);
        }

        /// <summary>
        /// BFS 求路由：边数最少（传送次数最少）。
        /// 返回 null = 图上无路；返回空列表 = 起点就是终点。
        /// </summary>
        public List<Edge> FindRoute(string from, string to)
        {
            if (string.IsNullOrEmpty(from) || string.IsNullOrEmpty(to)) return null;
            if (!this._nodes.Contains(from) || !this._nodes.Contains(to)) return null;

            var route = new List<Edge>();
            if (string.Equals(from, to, StringComparison.Ordinal)) return route;

            var previous = new Dictionary<string, Edge>(StringComparer.Ordinal);
            var seen = new HashSet<string>(StringComparer.Ordinal) { from };
            var queue = new Queue<string>();
            queue.Enqueue(from);

            while (queue.Count > 0)
            {
                string cur = queue.Dequeue();
                foreach (Edge e in this.EdgesFrom(cur))
                {
                    if (e.To == null || seen.Contains(e.To)) continue;
                    seen.Add(e.To);
                    previous[e.To] = e;

                    if (string.Equals(e.To, to, StringComparison.Ordinal))
                    {
                        // 回溯
                        string node = to;
                        while (previous.TryGetValue(node, out Edge back))
                        {
                            route.Add(back);
                            node = back.From;
                            if (string.Equals(node, from, StringComparison.Ordinal)) break;
                        }
                        route.Reverse();
                        return route;
                    }

                    queue.Enqueue(e.To);
                }
            }

            return null;
        }

        /// <summary>路由上的地点名列表（含起点）。回执的 <c>path</c> 字段。</summary>
        public static List<string> RouteNames(string start, List<Edge> route)
        {
            var names = new List<string> { start };
            if (route != null)
            {
                foreach (Edge e in route) names.Add(e.To);
            }
            return names;
        }
    }
}
