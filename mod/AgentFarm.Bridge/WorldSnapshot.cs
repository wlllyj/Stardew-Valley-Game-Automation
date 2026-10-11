using System;
using System.Collections.Generic;
using StardewModdingAPI;
using StardewValley;
using StardewValley.TerrainFeatures;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 感知层（架构文档 §5.1）：把游戏真值打包成 `agentfarm-world/5` 快照。
    ///
    /// 【铁律】本类所有方法**只能在游戏主线程调用**（由 MainThreadDispatcher 保证）。
    ///
    /// 【worldSeq 口径】用“廉价指纹”（地点名 + 玩家格 + 游戏内分钟 + 金钱 + 背包数）比较得出：
    /// 指纹变了就 +1。刻意不哈希全农场 —— 那会在每次 observe 时付出全量扫描的代价，
    /// 而世界是否变化对“脑”来说只要单调递增且与动作相关即可。
    /// </summary>
    internal sealed class WorldObserver
    {
        /// <summary>
        /// 快照协议版本。
        /// v1 → v2 的变更（详见 docs/03-桥接协议.md §5/§8）：新增 weatherOnFarm / isOutdoorFarm /
        /// onScreenMenus / activeMenuText / dialogueResponses / dialogueIsQuestion / windowActive /
        /// canMove / hasController / exec.uiOpened，删除误导性的 ui.dialogsOnScreen。
        ///
        /// v2 → v3 的变更（修复迭代 3，真机“冻结”事故）：
        ///   * 新增 `player.isInBed`、`game.paused`、`game.shouldTimePass`（新段 `game`）——
        ///     事故现场是“模态没了、画面正常，但 canMove=false、时钟停走”，
        ///     旧字段无法区分“游戏认为自己暂停/在睡觉”与“程序卡住”。
        ///
        /// v3 → v4 的变更（修复迭代 4，真机“家具误判”）：
        ///   * 新增 `location.furniture[]`，**仅 `detail=full` 时出现**（summary 不含，避免大清单污染常规观测）：
        ///     每件家具的 `tile` / `bbox` / `passable` / `ground` / `isBed` / `blocking` / `type` / `name`。
        ///     这是本轮的关键可观测性 —— v3 的家具误判（FarmHouse 里 13 格被判“有家具”，含出生点 (9,9)）
        ///     就是只能靠“逐格网格扫描”猜出来的；有清单后可以直接看出是哪件家具盖住了哪一格。
        /// </summary>
        public const string WorldSchema = "agentfarm-world/6";

        /// <summary>世界指纹单调递增计数器。</summary>
        private long _worldSeq;
        private string _fingerprint = "";

        // ---- 活性检测（参考旧项目 ModEntry.TileMap.cs:58-110 的 WorldIsAdvancing 思路）----
        private int _lastTimeOfDay = int.MinValue;
        private int _lastDay = int.MinValue;
        private DateTime _lastClockChangeUtc = DateTime.UtcNow;

        private readonly FarmScanCache _farm = new FarmScanCache();

        public long WorldSeq => _worldSeq;

        /// <summary>距离游戏内时钟最后一次推进过了多少秒。</summary>
        public double SecondsSinceClockMoved => (DateTime.UtcNow - _lastClockChangeUtc).TotalSeconds;

        /// <summary>
        /// 世界是否在推进。阈值 20 秒：游戏内每 10 分钟（现实约 7 秒）会 tick 一次时钟，
        /// 20 秒没动就一定不正常（典型原因：`pauseWhenOutOfFocus=true` 被改回、读档卡住、过场）。
        /// v0.5.0 起 Mod 每帧关掉该选项，所以"失焦"不再是合理原因（health.game.oofFixCount 是证据）。
        /// 这一条对无人值守是关键判据。
        /// </summary>
        public bool WorldIsAdvancing
        {
            get
            {
                if (!Context.IsWorldReady) return false;
                return this.SecondsSinceClockMoved < 20.0;
            }
        }

        /// <summary>每 tick 调用（主线程）。推进活性检测与农场分帧统计。</summary>
        public void OnTick(bool farmScanWanted)
        {
            try
            {
                int t = Game1.timeOfDay;
                int d = Game1.dayOfMonth;
                if (t != _lastTimeOfDay || d != _lastDay)
                {
                    _lastTimeOfDay = t;
                    _lastDay = d;
                    _lastClockChangeUtc = DateTime.UtcNow;
                }
            }
            catch
            {
                // 游戏对象还没初始化（标题画面）——忽略，下一 tick 再来。
            }

            try { this.UpdateWorldSeq(); } catch { }

            try { _farm.Step(_worldSeq, force: farmScanWanted); } catch { }
        }

        /// <summary>读档 / 换天 / 回标题时丢弃统计缓存。</summary>
        public void InvalidateFarmCache() => _farm.Invalidate();

        // ==================================================================
        //  worldSeq
        // ==================================================================

        /// <summary>用廉价指纹推进 worldSeq。</summary>
        private void UpdateWorldSeq()
        {
            if (!Context.IsWorldReady || Game1.player == null || Game1.currentLocation == null)
            {
                // 未进入世界时也推进（读档/回标题本身是显著状态变化），但指纹置空。
                if (_fingerprint.Length != 0)
                {
                    _fingerprint = "";
                    _worldSeq++;
                }
                return;
            }

            string fp;
            try
            {
                var tile = Game1.player.TilePoint;
                fp = string.Concat(
                    Game1.currentLocation.Name ?? "?",
                    "|", tile.X, ",", tile.Y,
                    "|", Game1.timeOfDay,
                    "|", Game1.dayOfMonth,
                    "|", Game1.player.Money,
                    "|", Game1.player.Items.Count);
            }
            catch
            {
                return;
            }

            if (fp != _fingerprint)
            {
                _fingerprint = fp;
                _worldSeq++;
            }
        }

        // ==================================================================
        //  快照
        // ==================================================================

        /// <summary>
        /// 生成世界快照（主线程）。<paramref name="detail"/> 取 summary / full / tiles。
        /// </summary>
        public WorldSnapshotViewResult Observe(string detail)
        {
            bool hasSave = false;
            try { hasSave = Context.IsWorldReady && Game1.player != null && Game1.currentLocation != null; }
            catch { hasSave = false; }

            if (!hasSave)
            {
                // 契约：未加载存档时其余段为 null，只保留 ok/status/schema/hasSaveLoaded。
                return new WorldSnapshotViewResult
                {
                    Body = new WorldSnapshot
                    {
                        Ok = true,
                        Status = "no_save",
                        Schema = WorldSchema,
                        HasSaveLoaded = false,
                    },
                };
            }

            var snap = new WorldSnapshot
            {
                Ok = true,
                Status = "ok",
                Schema = WorldSchema,
                WorldSeq = _worldSeq,
                GeneratedAt = DateTimeOffset.Now.ToString("yyyy-MM-dd'T'HH:mm:sszzz"),
                HasSaveLoaded = true,
            };

            snap.Clock = ReadClock();
            snap.Player = ReadPlayer();
            snap.Location = ReadLocation(detail);
            snap.Farm = ReadFarm(detail);
            snap.Ui = ReadUi();
            snap.Liveness = ReadLiveness();
            snap.Game = ReadGame();

            return new WorldSnapshotViewResult { Body = snap, WorldSeq = _worldSeq };
        }

        private static ClockView ReadClock()
        {
            return new ClockView
            {
                Year = Game1.year,
                Season = Game1.currentSeason,
                Day = Game1.dayOfMonth,
                TimeOfDay = Game1.timeOfDay,
                Weather = DescribeWeather(Game1.currentLocation),
                WeatherOnFarm = DescribeWeather(SafeFarm()),
            };
        }

        private static GameLocation SafeFarm()
        {
            try { return Game1.getFarm(); } catch { return null; }
        }

        /// <summary>
        /// 天气字符串（v2 起恒为明确取值，不再返回空串）。
        ///
        /// 【为什么不用 netWorldState.LocationWeather】
        /// v1 走的是 <c>Game1.netWorldState.Value.LocationWeather[name].weather</c>，
        /// 真机上恒为 ""（那套字段本机版本里是空的）。1.6.15 的权威判定是 Game1 上的
        /// 四个 <c>IsXxxHere(GameLocation)</c> 方法（已由 tools/api-probe 编译期实证）。
        ///
        /// 【判定顺序与含义】顺序即优先级，先命中先返回：
        ///   1. lightning —— 雷雨。它同时会让 IsRainingHere 为 true，所以必须排在 rain 前面，
        ///                   否则雷暴会被误报成普通下雨；
        ///   2. rain      —— 下雨（含雷雨，但已被上面截走）；
        ///   3. snow      —— 下雪；
        ///   4. debris    —— 大风（DebrisWeather，天上飘树叶/花瓣）；
        ///   5. sunny     —— 以上都不成立（晴/多云归入此档）。
        /// </summary>
        private static string DescribeWeather(GameLocation loc)
        {
            if (loc == null) return "sunny";

            try { if (Game1.IsLightningHere(loc)) return "lightning"; } catch { }
            try { if (Game1.IsRainingHere(loc)) return "rain"; } catch { }
            try { if (Game1.IsSnowingHere(loc)) return "snow"; } catch { }
            try { if (Game1.IsDebrisWeatherHere(loc)) return "debris"; } catch { }

            return "sunny";
        }

        private PlayerView ReadPlayer()
        {
            Farmer p = Game1.player;
            var tile = new int[2];

            try
            {
                var tp = p.TilePoint;
                tile[0] = tp.X;
                tile[1] = tp.Y;
            }
            catch { }

            var view = new PlayerView
            {
                Name = SafeString(() => p.Name),
                Location = SafeString(() => p.currentLocation?.Name),
                Tile = tile,
                Facing = SafeInt(() => p.FacingDirection),
                Stamina = SafeFloat(() => p.stamina),
                MaxStamina = SafeFloat(() => p.MaxStamina),
                Health = SafeInt(() => p.health),
                MaxHealth = SafeInt(() => p.maxHealth),
                Money = SafeInt(() => p.Money),
                FarmingLevel = SafeInt(() => p.FarmingLevel),
                InventoryCount = SafeInt(() => p.Items?.Count ?? 0),
                CanMove = SafeBool(() => p.CanMove),
                HasController = SafeBool(() => p.controller != null),
                IsInBed = SafeBool(() => p.isInBed.Value),
                Tools = ReadTools(p),
                WateringCan = ReadWateringCan(p),
                Inventory = ReadInventory(p),
            };
            return view;
        }

        /// <summary>
        /// 背包清单（v0.7.9 新增，仅 detail=full）。
        ///
        /// 【为什么必须有】快照此前只有 `inventoryCount`，脑**不知道手里有没有种子/工具**——
        /// P3 步骤④（播种）第一步就是"我有没有防风草种子"。
        /// 槽位下标一并报出：`select_item` 就是拿它设 `CurrentToolIndex`（与玩家滚快捷栏等价）。
        /// </summary>
        private static ItemView[] ReadInventory(Farmer p)
        {
            var list = new List<ItemView>();
            try
            {
                var items = p?.Items;
                if (items == null) return System.Array.Empty<ItemView>();
                for (int i = 0; i < items.Count; i++)
                {
                    Item it = items[i];
                    if (it == null) continue;
                    var iv = new ItemView { Slot = i };
                    try { iv.Id = it.ItemId; } catch { }
                    try { iv.QualifiedId = it.QualifiedItemId; } catch { }
                    try { iv.Name = it.DisplayName ?? it.Name; } catch { }
                    try { iv.Stack = it.Stack; } catch { }
                    try { iv.IsTool = it is Tool; } catch { }
                    list.Add(iv);
                }
            }
            catch { }
            return list.ToArray();
        }

        private static ToolsView ReadTools(Farmer p)
        {
            var t = new ToolsView();
            try
            {
                if (p.Items == null) return t;

                foreach (Item item in p.Items)
                {
                    if (item is StardewValley.Tools.Axe) t.Axe = true;
                    else if (item is StardewValley.Tools.Pickaxe) t.Pickaxe = true;
                    else if (item is StardewValley.Tools.Hoe) t.Hoe = true;
                    else if (item is StardewValley.Tools.WateringCan) t.WateringCan = true;
                    else if (item is StardewValley.Tools.FishingRod) t.FishingRod = true;
                    else if (item is StardewValley.Tools.MeleeWeapon) t.Weapon = true;
                }
            }
            catch { }
            return t;
        }

        private static LocationView ReadLocation(string detail)
        {
            GameLocation loc = Game1.currentLocation;
            var v = new LocationView
            {
                Name = SafeString(() => loc.Name),

                // isFarm 保留原语义（SMAPI 的 GameLocation.IsFarm：Farm 与 FarmHouse 都为 true），
                // 但注释已写清陷阱；脑要“是否站在露天农场”请用 isOutdoorFarm。
                IsFarm = SafeBool(() => loc.IsFarm),
                IsOutdoorFarm = SafeBool(() => loc.Name == "Farm"),

                IsFarmhouse = SafeBool(() => loc.Name == "FarmHouse"),
                IsOutdoors = SafeBool(() => loc.IsOutdoors),
                Characters = SafeInt(() => loc.characters?.Count ?? 0),
            };

            try { v.Objects = loc.objects?.Length ?? 0; } catch { }
            try { v.Debris = loc.debris?.Count ?? 0; } catch { }
            try { v.TerrainFeatures = loc.terrainFeatures?.Length ?? 0; } catch { }

            // v4：家具清单**只在 detail=full 时**输出，summary 保持精简（脑的常规轮询不该被大清单拖累）。
            if (IsFullDetail(detail))
            {
                try { v.Furniture = ReadFurniture(loc); } catch { v.Furniture = System.Array.Empty<FurnitureView>(); }
                try { v.Doors = ReadDoors(loc); } catch { v.Doors = System.Array.Empty<DoorView>(); }
                try
                {
                    bool truncated;
                    v.Tiles = ReadTiles(loc, out truncated);
                    v.TilesTruncated = truncated ? true : (bool?)null;
                }
                catch { v.Tiles = System.Array.Empty<TileView>(); }

                // v0.7.18：能锄出耕地的空格（P3 步骤⑤"开垦哪几格"要靠它，别再瞎试空格）
                try { v.Tillable = ReadTillable(loc); } catch { v.Tillable = System.Array.Empty<int[]>(); }
                try
                {
                    bool refillTruncated;
                    v.RefillTiles = ReadRefillTiles(loc, out refillTruncated);
                    v.RefillTilesTruncated = refillTruncated;
                }
                catch { v.RefillTiles = System.Array.Empty<int[]>(); }
            }

            return v;
        }

        /// <summary>`detail=full|tiles` 判定（与 <see cref="ReadFarm"/> 用同一口径）。</summary>
        private static bool IsFullDetail(string detail)
            => string.Equals(detail, "full", StringComparison.OrdinalIgnoreCase)
            || string.Equals(detail, "tiles", StringComparison.OrdinalIgnoreCase);

        /// <summary>
        /// 逐格清单（v0.7.4 / `agentfarm-world/6` 新增，仅 detail=full）。
        ///
        /// 【目的】让脑第一次"看得见"农场哪一格上是什么（此前只有计数）。
        /// 【判据全部问游戏】`Object.IsWeeds()/IsTwig()/IsBreakableStone()` 是游戏自己的分类；
        /// terrainFeature 的类型名直接用 `GetType().Name`；能不能站人用 `StepMover.Standable`
        /// （与 `move_to` 同一套，家具/水面/放置物/地形一并算）。
        /// 【上限】`MaxTiles = 400`：本机农场有 1400+ 格、objects+terrainFeatures 上千条，
        /// payload 必须有界；截断时 `tilesTruncated=true`（脑可以据此换区域再问一次）。
        /// 工具映射是**给规划层的建议**，不是硬规则：杂草/树枝/草→镰刀，石头→镐，树/资源堆→斧，空耕地→锄。
        /// </summary>
        private static TileView[] ReadTiles(GameLocation loc, out bool truncated)
        {
            const int MaxTiles = 400;
            truncated = false;
            var list = new List<TileView>();
            // 【为什么先收集再截断（真机教训 2026-10-11）】旧实现是"objects 先塞满 400 格，
            // terrainFeatures 就一个都进不去"——于是脑的 tiles[] 里**看不到刚锄出来的耕地**，
            // 表现为"Mod 报 ok、tiles[] 里那一格是 null"，看着像回执撒谎，其实是**观测被截断**。
            // 现在：先全部收集，**按离玩家的距离排序**，再取最近 400 格 ⇒ 玩家身边永远看得见。
            var all = new List<KeyValuePair<int, TileView>>();
            if (loc == null) return System.Array.Empty<TileView>();

            try
            {
                if (loc.objects != null)
                {
                    foreach (KeyValuePair<Microsoft.Xna.Framework.Vector2, StardewValley.Object> kv in loc.objects.Pairs)
                    {
                        var p = new Microsoft.Xna.Framework.Point((int)kv.Key.X, (int)kv.Key.Y);
                        var t = new TileView { Tile = new[] { p.X, p.Y }, Kind = "object", Tool = "none" };
                        try { t.ObjId = kv.Value?.ItemId; } catch { }
                        try
                        {
                            StardewValley.Object o = kv.Value;
                            if (o != null && o.IsWeeds()) { t.Kind = "weed"; t.Tool = "hoe"; }   // ← 真机实证：杂草是锄头清掉的（0.7.7 验收，1 次 516ms）
                            else if (o != null && o.IsTwig()) { t.Kind = "twig"; t.Tool = "axe"; }
                            else if (o != null && o.IsBreakableStone()) { t.Kind = "stone"; t.Tool = "pickaxe"; }
                        }
                        catch { }
                        try { SetReach(loc, p, t); } catch { }
                        all.Add(new KeyValuePair<int, TileView>(DistToPlayer(p), t));
                    }
                }
            }
            catch { }

            try
            {
                if (loc.terrainFeatures != null)
                {
                    foreach (KeyValuePair<Microsoft.Xna.Framework.Vector2, StardewValley.TerrainFeatures.TerrainFeature> kv
                             in loc.terrainFeatures.Pairs)
                    {
                        var p = new Microsoft.Xna.Framework.Point((int)kv.Key.X, (int)kv.Key.Y);
                        var t = new TileView { Tile = new[] { p.X, p.Y }, Kind = "unknown", Tool = "none" };
                        var tf = kv.Value;
                        try { t.Feature = tf?.GetType().Name; } catch { }
                        try
                        {
                            if (tf is StardewValley.TerrainFeatures.Grass) { t.Kind = "grass"; t.Tool = "scythe"; }
                            else if (tf is StardewValley.TerrainFeatures.Tree) { t.Kind = "tree"; t.Tool = "axe"; }
                            else if (tf is StardewValley.TerrainFeatures.FruitTree) { t.Kind = "fruitTree"; t.Tool = "axe"; }
                            else if (tf is StardewValley.TerrainFeatures.ResourceClump) { t.Kind = "clump"; t.Tool = "axe"; }
                            else if (tf is StardewValley.TerrainFeatures.HoeDirt) { t.Kind = "dirt"; t.Tool = "hoe"; }
                            else if (tf is StardewValley.TerrainFeatures.Bush) { t.Kind = "bush"; t.Tool = "axe"; }
                        }
                        catch { }

                        // v0.7.9：耕地/作物状态（P3 步骤④"能不能种、该不该浇"全靠这几项）
                        try
                        {
                            if (tf is StardewValley.TerrainFeatures.HoeDirt hd)
                            {
                                t.Watered = hd.isWatered();
                                var cr = hd.crop;
                                if (cr != null)
                                {
                                    t.Crop = cr.indexOfHarvest?.Value;
                                    t.Ripe = cr.fullyGrown != null && cr.fullyGrown.Value;
                                    t.Dead = cr.dead != null && cr.dead.Value;
                                    t.Tool = t.Ripe ? "none" : "can";
                                }
                                else
                                {
                                    t.Plantable = true;
                                    t.Tool = t.Watered ? "none" : "can";
                                }
                            }
                        }
                        catch { }
                        try { SetReach(loc, p, t); } catch { }
                        all.Add(new KeyValuePair<int, TileView>(DistToPlayer(p), t));
                    }
                }
            }
            catch { }

            // 按"离玩家多远"排序后取最近 MaxTiles 格（近处永远看得见；远处的靠 tilesTruncated 提示）
            try { all.Sort((a, b) => a.Key.CompareTo(b.Key)); } catch { }
            truncated = all.Count > MaxTiles;
            for (int i = 0; i < all.Count && list.Count < MaxTiles; i++) list.Add(all[i].Value);

            return list.ToArray();
        }

        /// <summary>离玩家当前格多远的曼哈顿距离（读不到玩家时给一个很大的值，让它们排在最后）。</summary>
        private static int DistToPlayer(Microsoft.Xna.Framework.Point p)
        {
            try
            {
                var pt = Game1.player?.TilePoint;
                if (pt == null) return int.MaxValue / 2;
                var q = pt.Value;
                return Math.Abs(p.X - q.X) + Math.Abs(p.Y - q.Y);
            }
            catch { return int.MaxValue / 2; }
        }

        /// <summary>
        /// 填一格的两个可达性判据：
        ///   * `standable` —— 这一格**自己**能不能站人（与 `move_to` 同一套 `StepMover.Standable`）；
        ///   * `actionable` —— **够不够得着**（自身可站，或四邻任一格可站）。
        ///
        /// 【为什么必须分开（真机教训）】首版只报 `reachable = Standable(tile)`，真机上 400 格
        /// **全是 false** —— 因为杂草/石头/树枝的格子上都有东西，`Standable` 的定义就是"这格不能站"。
        /// 而规划层问的其实是"我能不能站到旁边把它清掉"，那是 `actionable`。
        /// 工具（锄/种/砍）作用的是**面朝的那一格**，所以"四邻有一格能站"就够得着。
        /// </summary>
        private static void SetReach(GameLocation loc, Microsoft.Xna.Framework.Point p, TileView t)
        {
            bool self = false;
            try { self = StepMover.Standable(loc, p, true, out StardewValley.Objects.Furniture _); } catch { }
            t.Standable = self;
            if (self) { t.Actionable = true; return; }

            var n = new[]
            {
                new Microsoft.Xna.Framework.Point(p.X, p.Y - 1),
                new Microsoft.Xna.Framework.Point(p.X + 1, p.Y),
                new Microsoft.Xna.Framework.Point(p.X, p.Y + 1),
                new Microsoft.Xna.Framework.Point(p.X - 1, p.Y),
            };
            foreach (var q in n)
            {
                bool ok = false;
                try { ok = StepMover.Standable(loc, q, true, out StardewValley.Objects.Furniture _); } catch { }
                if (ok) { t.Actionable = true; return; }
            }
        }

        /// <summary>
        /// 能锄出耕地的空格（v0.7.18 新增，仅 detail=full）。
        ///
        /// 以玩家为中心扫 `±Radius` 格，过 <see cref="StepMover.Tillable"/> 的留下，近处优先，最多 200 个。
        /// 【为什么是"附近"】P3 的开垦是**局部动作**（5x5 一小块地），远处没必要现在算；
        /// 需要别的区域时人走过去再 observe 一次即可（与 `tiles[]` 同一口径）。
        /// </summary>
        private static int[][] ReadTillable(GameLocation loc)
        {
            const int Radius = 12;
            const int MaxTiles = 200;
            var all = new List<KeyValuePair<int, int[]>>();
            try
            {
                if (loc == null) return System.Array.Empty<int[]>();
                var pt = Game1.player?.TilePoint;
                if (pt == null) return System.Array.Empty<int[]>();
                int cx = pt.Value.X, cy = pt.Value.Y;

                for (int dx = -Radius; dx <= Radius; dx++)
                {
                    for (int dy = -Radius; dy <= Radius; dy++)
                    {
                        int x = cx + dx, y = cy + dy;
                        if (x < 0 || y < 0) continue;

                        string why;
                        if (!StepMover.Tillable(loc, new Microsoft.Xna.Framework.Point(x, y), out why)) continue;
                        all.Add(new KeyValuePair<int, int[]>(Math.Abs(dx) + Math.Abs(dy), new[] { x, y }));
                    }
                }
            }
            catch { }

            try { all.Sort((a, b) => a.Key.CompareTo(b.Key)); } catch { }

            var outp = new List<int[]>();
            for (int i = 0; i < all.Count && i < MaxTiles; i++) outp.Add(all[i].Value);
            return outp.ToArray();
        }

        /// <summary>
        /// 能给**浇水壶补水**的格子（v0.7.21 新增，仅 detail=full）。
        ///
        /// 【判据是游戏自己的】逐格调 `GameLocation.CanRefillWateringCanOnTile(x, y)`
        /// （api-probe 实证 public，见 `logs\api-water-members.txt`）——水面、水槽，以及农场小屋里
        /// 那种"看着不像水"的水槽都算，**不硬编码坐标、不猜地形属性**。
        ///
        /// 【为什么扫全图而不是像 tillable 那样只扫 ±12】tillable 的口径是"局部动作"（5x5 一小块地），
        /// 而水源可能离耕地几十格（农场水塘就是），"走到水边"本来就该由脑自己规划。
        /// 全图 80×65 ≈ 5200 次判定，一次 observe 的开销可以接受；结果按曼哈顿距离排序、最多 24 个。
        /// 地图尺寸读不到时退回玩家 ±40 的窗口，**绝不让 observe 因这个字段抛异常**。
        /// </summary>
        private static int[][] ReadRefillTiles(GameLocation loc, out bool truncated)
        {
            const int MaxTiles = 24;
            const int FallbackRadius = 40;
            truncated = false;
            var all = new List<KeyValuePair<int, int[]>>();
            try
            {
                if (loc == null) return System.Array.Empty<int[]>();
                var pt = Game1.player?.TilePoint;
                if (pt == null) return System.Array.Empty<int[]>();
                int cx = pt.Value.X, cy = pt.Value.Y;

                int x0 = 0, y0 = 0, xEnd, yEnd;
                try
                {
                    var layers = loc.map?.Layers;
                    xEnd = (layers != null && layers.Count > 0) ? layers[0].LayerWidth : 0;
                    yEnd = (layers != null && layers.Count > 0) ? layers[0].LayerHeight : 0;
                }
                catch { xEnd = 0; yEnd = 0; }
                if (xEnd <= 0 || yEnd <= 0)
                {
                    x0 = Math.Max(0, cx - FallbackRadius);
                    y0 = Math.Max(0, cy - FallbackRadius);
                    xEnd = cx + FallbackRadius + 1;
                    yEnd = cy + FallbackRadius + 1;
                }

                for (int y = y0; y < yEnd; y++)
                {
                    for (int x = x0; x < xEnd; x++)
                    {
                        bool can;
                        try { can = loc.CanRefillWateringCanOnTile(x, y); } catch { can = false; }
                        if (!can) continue;
                        all.Add(new KeyValuePair<int, int[]>(Math.Abs(x - cx) + Math.Abs(y - cy), new[] { x, y }));
                    }
                }
            }
            catch { }

            truncated = all.Count > MaxTiles;
            try { all.Sort((a, b) => a.Key.CompareTo(b.Key)); } catch { }

            var outp = new List<int[]>();
            for (int i = 0; i < all.Count && i < MaxTiles; i++) outp.Add(all[i].Value);
            return outp.ToArray();
        }

        /// <summary>
        /// 浇水壶水量（v0.7.21 新增）。
        ///
        /// 【为什么单独读，不塞进 `inventory[]`】`ItemView` 只有 slot/id/name/stack/isTool，
        /// 而"水"在 `WateringCan` 自己身上（`WaterLeft` / `waterCanMax`，1.6.15 的 public 成员）。
        /// 脑要靠"还剩几格水"决定先去补水 —— 壶空了以后 `use_tool(can)` 只会一直 `tool_ineffective`，
        /// 那时再补就要先诊断"为什么浇不动"，白烧一轮。
        /// 找不到壶时 `present=false`（**不报 0**：0 会被脑当成"壶空了"而去白补水）。
        /// </summary>
        private static WateringCanView ReadWateringCan(Farmer p)
        {
            var v = new WateringCanView();
            try
            {
                var can = p?.CurrentTool as StardewValley.Tools.WateringCan;
                if (can == null && p?.Items != null)
                {
                    foreach (var it in p.Items)
                    {
                        if (it is StardewValley.Tools.WateringCan c) { can = c; break; }
                    }
                }
                if (can == null) return v;
                v.Present = true;
                v.WaterLeft = SafeInt(() => can.WaterLeft);
                v.Max = SafeInt(() => can.waterCanMax);
                v.UpgradeLevel = SafeInt(() => can.UpgradeLevel);
                v.Bottomless = SafeBool(() => p.hasWateringCanEnchantment);
            }
            catch { }
            return v;
        }

        /// <summary>
        /// 门清单（v0.6.2 新增，仅 detail=full）。
        ///
        /// 【权威来源】`GameLocation.isCollidingWithDoors` 的 IL 实证：它遍历
        /// **`this.doors`**（`NetPointDictionary&lt;string,NetString&gt;`：门格 → 门类型），
        /// 用玩家像素矩形的**四个角**所在格去比对，命中后 `getWarpFromDoor` 才得到 Warp。
        /// 所以"回屋的门到底在哪一格"必须问这份字典，而不是从 Building 推。
        /// </summary>
        private static DoorView[] ReadDoors(GameLocation loc)
        {
            var list = new List<DoorView>();
            try
            {
                if (loc?.doors == null) return System.Array.Empty<DoorView>();
                foreach (KeyValuePair<Microsoft.Xna.Framework.Point, string> kv in loc.doors.Pairs)
                {
                    var d = new DoorView();
                    try { d.Tile = new[] { kv.Key.X, kv.Key.Y }; } catch { }
                    d.Type = kv.Value;   // 编译期实证：Pairs 枚举出的值就是 string（不是 NetString）
                    list.Add(d);
                }
            }
            catch { }
            return list.ToArray();
        }

        /// <summary>
        /// 家具清单（v4 新增，仅 detail=full）。
        ///
        /// 【为什么必须把"可踩/不可踩"一起报出来】迭代 4 的家具误判之所以难查，是因为
        /// v3 的判定藏在几何里（包围盒相交），从外部只看得到"这格被拒"，看不到"是谁盖住了它、
        /// 它到底能不能踩"。把 `passable` / `ground` / `isBed` / `blocking` 与 `bbox` 并排给出，
        /// 下次真机上只要一条 observe 就能定位，**不用再整屋扫网格猜**。
        ///
        /// 【这里的 `blocking` 必须与 move_to 的前置检查同口径】
        /// `Skills.SafeStandable` 的规则是 `isBed || !isPassable()`。清单里逐字复刻同一规则，
        /// 否则又会出现"诊断说能走、技能却拒绝"的自相矛盾（v2 的教训）。
        /// 每一件家具的读取都单独 try/catch：某件读不出来不影响整份清单。
        /// </summary>
        private static FurnitureView[] ReadFurniture(GameLocation loc)
        {
            var list = new List<FurnitureView>();
            if (loc?.furniture == null) return System.Array.Empty<FurnitureView>();

            foreach (StardewValley.Objects.Furniture f in loc.furniture)
            {
                if (f == null) continue;

                var item = new FurnitureView();

                try
                {
                    var tile = f.TileLocation;
                    item.Tile = new[] { (int)tile.X, (int)tile.Y };
                }
                catch { item.Tile = new[] { 0, 0 }; }

                try
                {
                    var box = f.GetBoundingBox();
                    item.Bbox = new[] { box.X, box.Y, box.Width, box.Height };
                }
                catch { item.Bbox = new[] { 0, 0, 0, 0 }; }

                // 老版本/异常时默认 false（false 是"可踩"的反面：不确定时按"不可踩"处理），
                // 与 SafeStandable 里的兜底口径一致。
                item.Passable = SafeBool(() => f.isPassable());
                item.Ground = SafeBool(() => f.isGroundFurniture());
                item.IsBed = SafeBool(() => f is StardewValley.Objects.BedFurniture);

                // 与技能层同口径：床无条件阻挡；其余只由 isPassable() 决定。
                item.Blocking = item.IsBed || !item.Passable;

                try { item.Type = f.GetType().Name; } catch { item.Type = null; }
                item.Name = SafeFurnitureName(f);

                list.Add(item);
            }

            return list.ToArray();
        }

        /// <summary>
        /// 家具可读名：优先 <c>DisplayName</c>，失败退回 <c>Name</c>，都失败给 null。
        /// 用反射调用是为了"某个成员在别的游戏版本上不存在时只少一个字符串，而不是整体编译/运行失败"
        /// （架构 §12 的逐字段安全原则）。反射失败只捕获异常，不影响其它字段。
        /// </summary>
        private static string SafeFurnitureName(StardewValley.Objects.Furniture f)
        {
            try
            {
                var prop = f.GetType().GetProperty("DisplayName");
                if (prop != null)
                {
                    object v = prop.GetValue(f);
                    string s = v as string;
                    if (!string.IsNullOrEmpty(s)) return s;
                }
            }
            catch { }

            try { return f.Name; } catch { return null; }
        }

        private FarmView ReadFarm(string detail)
        {
            FarmView farm = _farm.Current;
            if (farm == null)
            {
                // 还没跑完第一轮：返回 loaded=true 但 complete=false 的零值，
                // 明确告诉“脑”这些数字还不能用。
                farm = new FarmView { Loaded = true, Complete = false, ScanSeq = _worldSeq };
            }

            // detail=full|tiles 时附上地块数组。
            // TODO(P2)：实现分区域地块导出（GET /v1/observe/tiles?area=x1,y1,x2,y2 已在架构 §6 规划）。
            // 当前里程碑 A 只做农场汇总统计，tiles 先返回空数组，避免在 observe 里搬 244KB。
            if (IsFullDetail(detail))
            {
                farm.Tiles = System.Array.Empty<object>();
            }

            return farm;
        }

        private UiView ReadUi()
        {
            var v = new UiView();
            try { v.ActiveMenu = Game1.activeClickableMenu?.GetType().Name; } catch { }
            try { v.EventUp = Game1.eventUp; } catch { }
            try { v.OnScreenMenus = Game1.onScreenMenus?.Count ?? 0; } catch { }

            // 模态里的文字 + 对话框选项：无人值守时脑必须读到这些内容才能决定
            // “该关掉它 / 该回答它 / 该换计划”。实测床边睡觉确认框会让**整个世界时间冻结**，
            // 而 v1 只给得出一个类名 "DialogueBox"，脑无从判断。
            v.ActiveMenuText = UiRead.ActiveMenuText();
            v.DialogueResponses = UiRead.DialogueResponseTexts();
            v.DialogueIsQuestion = UiRead.DialogueIsQuestion();

            v.IsModal = v.ActiveMenu != null
                || v.EventUp
                || SafeBool(() => Game1.dialogueUp)
                || !SafeBool(() => Context.IsPlayerFree);

            return v;
        }

        private LivenessView ReadLiveness()
        {
            return new LivenessView
            {
                WorldAdvancing = this.WorldIsAdvancing,
                SecondsSinceClockMoved = Math.Round(Math.Min(this.SecondsSinceClockMoved, 86400.0), 3),
            };
        }

        /// <summary>
        /// 游戏级暂停/时间状态（v3 新增，诊断“冻结”专用）。
        ///
        /// 【为什么加】事故现场：`canMove=false`、`isModal=false`、时钟 45 秒不走。
        /// 旧快照里没有任何字段能说明“游戏自己是否认为时间应该推进”，排查只能靠猜。
        /// 现在把 `Game1.paused` 与 `Game1.shouldTimePass()` 直接报出来：
        ///   * `paused=true` → 游戏被显式暂停（例如打开菜单/过场；**不再是**失焦，v0.5.0 每帧关掉它）；
        ///   * `shouldTimePass=false` 且 `paused=false` → 世界因为别的原因停摆
        ///     （IL 实证：`CanMove=false` 且未使用工具时它就返回 false）；
        ///   * `player.isInBed=true` → 正在睡觉流程里。
        /// 三者一起就能把“冻结”的成因定位到具体分支。
        /// </summary>
        private static GameStateView ReadGame()
        {
            return new GameStateView
            {
                Paused = SafeBool(() => Game1.paused),
                ShouldTimePass = SafeBool(() => Game1.shouldTimePass()),
            };
        }

        // ==================================================================
        //  逐字段安全读取（架构 §12：游戏更新时“只丢一个数字，而不是整体崩溃”）
        // ==================================================================

        private static string SafeString(Func<string> f) { try { return f(); } catch { return null; } }
        private static int SafeInt(Func<int> f) { try { return f(); } catch { return 0; } }
        private static float SafeFloat(Func<float> f) { try { return f(); } catch { return 0f; } }
        private static bool SafeBool(Func<bool> f) { try { return f(); } catch { return false; } }
    }

    /// <summary>observe 的产出：DTO + 生成时刻的 worldSeq（两个必须是同一个值）。</summary>
    internal sealed class WorldSnapshotViewResult
    {
        public WorldSnapshot Body;
        public long WorldSeq;
    }
}
