using System;
using System.Collections.Generic;
using StardewModdingAPI;
using StardewValley;
using StardewValley.TerrainFeatures;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 感知层（架构文档 §5.1）：把游戏真值打包成 `agentfarm-world/2` 快照。
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
        /// </summary>
        public const string WorldSchema = "agentfarm-world/2";

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
        /// 20 秒没动就一定不正常（典型原因：失焦暂停、读档卡住、过场）。
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
            snap.Location = ReadLocation();
            snap.Farm = ReadFarm(detail);
            snap.Ui = ReadUi();
            snap.Liveness = ReadLiveness();

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
                Tools = ReadTools(p),
            };
            return view;
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

        private static LocationView ReadLocation()
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

            return v;
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
            if (string.Equals(detail, "full", StringComparison.OrdinalIgnoreCase)
                || string.Equals(detail, "tiles", StringComparison.OrdinalIgnoreCase))
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
