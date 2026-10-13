using System;
using System.Collections.Generic;
using System.Threading;
using StardewValley;
using StardewValley.TerrainFeatures;
using SObject = StardewValley.Object;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 农场统计的**分帧累计缓存**。
    ///
    /// 【为什么不能每帧全量扫描】
    /// 本机实测农场有 1400+ 格，`terrainFeatures` + `objects` 里各有几百到上千个条目；
    /// 每帧全扫一边会在低配上吃掉好几毫秒。这里把一整轮扫描切成每 tick 最多
    /// <see cref="BudgetPerTick"/> 个子项，跑完一轮才发布新结果。
    ///
    /// 【为什么不只是“节流”】
    /// 单纯节流（比如每 10 秒扫一次）会在扫描那一帧造成明显尖峰。
    /// 分帧累计把尖峰摊平：最坏情况每 tick 处理 300 个格子，代价恒定且极小。
    ///
    /// 【一致性说明】发布出去的 <see cref="FarmView"/> 对象在发布后不再被写入
    /// （完整一轮结束才 new 一个新对象），所以网络线程读它不会读到撕裂的数字。
    /// </summary>
    internal sealed class FarmScanCache
    {
        /// <summary>每 tick 最多处理多少个子项（地形特征或放置物）。</summary>
        private const int BudgetPerTick = 300;

        /// <summary>统计结果的软生存期（秒）。超过就重扫一轮。</summary>
        private const double FreshSeconds = 2.0;

        /// <summary>
        /// `farm.dryTiles` 的坐标上限（task-50）。
        ///
        /// 【为什么是 64】干作物是"今天没浇完"的**待办清单**，正常农场一轮也就十几到几十格；
        /// 64 条 × 2 个 int 的 JSON 完全可以接受，而超过 64 说明整个农场都没浇（脑侧
        /// 本来也只能一小片一小片做，先做最近的即可）⇒ 截断并置 `dryTilesTruncated=true`，
        /// **计数仍以 `dryCrops` 为准**（脑侧不许拿截断列表当"全部"）。
        /// </summary>
        public const int DryTilesMax = 64;

        // ---- 游戏内 ID 常量（1.6.x 的 ItemId 风格字符串）----
        private static readonly HashSet<string> MachineIds = new HashSet<string>(StringComparer.Ordinal)
        {
            "Furnace", "PreservesJar", "Keg", "Cask", "MayonnaiseMachine", "CheesePress", "ButterChurn",
            "Loom", "OilMaker", "RecyclingMachine", "SeedMaker", "Crystalarium", "CharcoalKiln",
            "SlimeIncubator", "SlimeEggPress", "Tapper", "HeavyTapper", "WormBin", "Dehydrator",
            "FishSmoker", "MushroomBox", "WoodChipper", "BaitMaker", "Anvil", "MiniForge", "SolarPanel",
        };

        // ---- 石头 ID 兜底集合（已被 IsBreakableStone() 取代）----
        //
        // 【为什么保留】真机实测（2026-10-11）已经证明：1.6.x 的 ItemId 是**数字字符串**
        // （"343" / "450" / ...），旧代码按 `id == "Weeds"` / `id == "Twig"` 比较永远匹配不上，
        // 导致 weeds/twigs 恒为 0。现在杂草/树枝/石头**一律走游戏自己的判定方法**
        // （`Object.IsWeeds()` / `IsTwig()` / `IsBreakableStone()`），这是唯一与游戏口径一致的做法。
        //
        // 这一组数字只作为**兜底**：当某个 Mod/未来版本让 `IsBreakableStone()` 漏判时，
        // 仍按已知石类 ID 计入，避免 stones 数字突然掉下去。回归时可对照：
        // 若 IsBreakableStone() 已经覆盖全部，这组集合命中数为 0（不影响结果）。
        private static readonly HashSet<string> StoneIds = new HashSet<string>(StringComparer.Ordinal)
        {
            "343", "450", "668", "670", "845", "846", "847",
        };

        private readonly object _lock = new object();

        // 分帧累加的“半成品”
        private int _phase;                 // 0=遍历地形特征 1=遍历放置物 2=本轮完成
        private int _partialIndex;
        private List<KeyValuePair<Microsoft.Xna.Framework.Vector2, TerrainFeature>> _terrain = new List<KeyValuePair<Microsoft.Xna.Framework.Vector2, TerrainFeature>>();
        private List<KeyValuePair<Microsoft.Xna.Framework.Vector2, SObject>> _objects = new List<KeyValuePair<Microsoft.Xna.Framework.Vector2, SObject>>();

        /// <summary>本轮扫到的干作物格坐标（task-50；发布时排序 + 截断）。</summary>
        private readonly List<int[]> _dryTiles = new List<int[]>();

        private FarmView _acc = NewAccumulator();
        private FarmView _published;         // 最近一次完整结果（网络线程只读）
        private DateTime _publishedAtUtc = DateTime.MinValue;
        private GameLocation _scannedLocation;

        /// <summary>上一轮统计的 worldSeq（用于标注数字的“新鲜度”）。</summary>
        private long _scanSeq;

        /// <summary>最近一次完整结果（可能为 null）。</summary>
        public FarmView Current => Volatile.Read(ref _published);

        /// <summary>结果是否足够新。</summary>
        public bool IsFresh => Volatile.Read(ref _published) != null
            && (DateTime.UtcNow - _publishedAtUtc).TotalSeconds < FreshSeconds;

        /// <summary>换天 / 读档 / 回标题时调用：丢弃缓存，强制重扫。</summary>
        public void Invalidate()
        {
            lock (_lock)
            {
                _published = null;
                _publishedAtUtc = DateTime.MinValue;
                _scannedLocation = null;
                ResetCycle();
            }
        }

        private void ResetCycle()
        {
            _phase = 0;
            _partialIndex = 0;
            _terrain = new List<KeyValuePair<Microsoft.Xna.Framework.Vector2, TerrainFeature>>();
            _objects = new List<KeyValuePair<Microsoft.Xna.Framework.Vector2, SObject>>();
            _dryTiles.Clear();
            _acc = NewAccumulator();
        }

        private static FarmView NewAccumulator() => new FarmView { Loaded = true };

        /// <summary>
        /// 主线程调用（每 tick）：推进分帧扫描。
        /// </summary>
        /// <param name="worldSeq">当前 worldSeq，用于标注统计的新鲜度。</param>
        /// <param name="force">true = 忽略软生存期，尽快跑完一轮。</param>
        public void Step(long worldSeq, bool force)
        {
            Farm farm = null;
            try { farm = Game1.getFarm(); }
            catch { farm = null; }

            if (farm == null)
            {
                lock (_lock)
                {
                    if (_published == null || !_published.Loaded)
                        Volatile.Write(ref _published, new FarmView { Loaded = false, Complete = true, ScanSeq = worldSeq });
                }
                return;
            }

            lock (_lock)
            {
                if (!ReferenceEquals(_scannedLocation, farm))
                {
                    _scannedLocation = farm;
                    ResetCycle();
                }

                bool fresh = _published != null && (DateTime.UtcNow - _publishedAtUtc).TotalSeconds < FreshSeconds;
                if (fresh && !force) return;

                this.StepCore(farm, worldSeq);
            }
        }

        private void StepCore(Farm farm, long worldSeq)
        {
            int budget = BudgetPerTick;

            while (budget > 0 && _phase < 2)
            {
                if (_phase == 0)
                {
                    if (_terrain.Count == 0 && _partialIndex == 0)
                    {
                        try
                        {
                            foreach (var kv in farm.terrainFeatures.Pairs)
                                _terrain.Add(kv);
                        }
                        catch { }
                    }

                    while (budget > 0 && _partialIndex < _terrain.Count)
                    {
                        // task-50：把坐标一起传进去（KVP 的 Key 就是该格坐标）
                        AccumulateTerrain(_terrain[_partialIndex]);
                        _partialIndex++;
                        budget--;
                    }

                    if (_partialIndex >= _terrain.Count)
                    {
                        _phase = 1;
                        _partialIndex = 0;
                    }
                }
                else if (_phase == 1)
                {
                    if (_objects.Count == 0 && _partialIndex == 0)
                    {
                        try
                        {
                            foreach (var kv in farm.objects.Pairs)
                                _objects.Add(kv);
                        }
                        catch { }
                    }

                    while (budget > 0 && _partialIndex < _objects.Count)
                    {
                        AccumulateObject(_objects[_partialIndex].Value);
                        _partialIndex++;
                        budget--;
                    }

                    if (_partialIndex >= _objects.Count)
                    {
                        _phase = 2;
                        _partialIndex = 0;
                    }
                }
            }

            if (_phase >= 2)
            {
                // 1.6.x：FruitTree / Bush / ResourceClump 都在 terrainFeatures 里，
                // largeTerrainFeatures 只剩极少数类型；这里不再遍历它（TerrainFeature 分支已覆盖）。
                try { _acc.Animals = farm.animals.Length; } catch { _acc.Animals = 0; }

                _scanSeq = worldSeq;
                _acc.Complete = true;
                _acc.ScanSeq = worldSeq;
                PublishDryTiles();
                Volatile.Write(ref _published, _acc);
                _publishedAtUtc = DateTime.UtcNow;
                ResetCycle();
            }
        }

        /// <summary>
        /// 把本轮扫到的干作物格坐标排序 + 截断后写进待发布的 <see cref="_acc"/>（task-50）。
        ///
        /// * 排序：先 `y` 再 `x`（确定性）；坐标是**农场地图格坐标**，与 `dryCrops` 同一次扫描。
        /// * 截断：超过 <see cref="DryTilesMax"/> 只保留前 N 条并置 `DryTilesTruncated = true`。
        /// * 任何异常都不许影响统计发布：退回空数组 + `DryTilesTruncated = true`（不确定就说不确定）。
        /// </summary>
        private void PublishDryTiles()
        {
            try
            {
                var ordered = new List<int[]>(_dryTiles);
                ordered.Sort((a, b) => a[1] != b[1] ? a[1] - b[1] : a[0] - b[0]);
                bool truncated = false;
                if (ordered.Count > DryTilesMax)
                {
                    truncated = true;
                    ordered = ordered.GetRange(0, DryTilesMax);
                }

                _acc.DryTiles = ordered.ToArray();
                _acc.DryTilesTruncated = truncated;
            }
            catch
            {
                _acc.DryTiles = new int[0][];
                _acc.DryTilesTruncated = true;
            }
        }

        private void AccumulateTerrain(KeyValuePair<Microsoft.Xna.Framework.Vector2, TerrainFeature> entry)
        {
            TerrainFeature tf = entry.Value;
            if (tf == null) return;

            if (tf is HoeDirt dirt)
            {
                _acc.HoeDirt++;
                Crop crop = null;
                try { crop = dirt.crop; } catch { }

                if (crop == null)
                {
                    _acc.EmptyDirt++;
                }
                else
                {
                    _acc.Crops++;
                    try
                    {
                        if (crop.fullyGrown.Value) _acc.RipeCrops++;
                    }
                    catch { }
                    try
                    {
                        if (dirt.needsWatering()) _acc.UnwateredCrops++;
                    }
                    catch { }
                    // 真正的"今天还没浇"格数：判据与逐格 tiles[].watered 完全一致（HoeDirt.isWatered()）。
                    // 上面那个 UnwateredCrops 用的是 needsWatering()，它不看浇水状态（docs\_analyze-farmcounts.md）。
                    try
                    {
                        if (!dirt.isWatered())
                        {
                            _acc.DryCrops++;
                            // task-50：把坐标也带上（脑侧只有玩家周围 400 格窗口，看不到农场另一头）。
                            // 口径与 dryCrops 严格一致：只判 !isWatered()，**死苗也照报**
                            // （Lead 2026-10-13 更正：Mod 侧不许自作主张过滤，否则两个字段对不上账）。
                            _dryTiles.Add(new[] { (int)entry.Key.X, (int)entry.Key.Y });
                        }
                    }
                    catch { }
                }
                return;
            }

            if (tf is Grass) { _acc.Grass++; return; }

            // 灌木（Bush : LargeTerrainFeature : TerrainFeature）算在植被口径里
            if (tf is Bush) { _acc.Grass++; return; }

            if (tf is FruitTree) { _acc.Trees++; return; }

            if (tf is Tree tree)
            {
                try
                {
                    if (!tree.stump.Value) _acc.Trees++;
                }
                catch { _acc.Trees++; }
                return;
            }

            if (tf is ResourceClump clump)
            {
                // 无法稳定拿到 clumpType 的公开入口时，按“凡是 ResourceClump 都算巨石障碍”处理：
                // 巨石(148/150/152) 与 树桩/大木头(600/602/604) 对清障规划都是障碍，
                // 口径统一比细分更重要（细分留给 P2 的 affordance 层）。
                _ = clump;
                _acc.Stones++;
                return;
            }
        }

        private void AccumulateObject(SObject obj)
        {
            if (obj == null) return;

            // ---- 杂草 / 树枝 / 可击碎石头：用游戏自己的判定方法 ----
            //
            // 【为什么不用 ItemId 比较】1.6.x 的 ItemId 是数字字符串（例如杂草 (O)0 / 树枝 (O)294，
            // 实际拿到的是 "0"/"294" 这类数字），旧代码的 `id == "Weeds"` 永远为 false，
            // 于是 weeds/twigs 恒为 0（真机实测：weeds=0 而真值 443、twigs=0 而真值 114）。
            // `Object.IsWeeds()/IsTwig()/IsBreakableStone()` 是游戏内部同一套判定，
            // 已经过 tools/api-probe 编译期实证，是唯一不会与游戏口径漂移的写法。
            //
            // 顺序说明：三者互斥（同一个 Object 不会是杂草又是树枝），因此可安全提前 return。
            bool isWeeds = false, isTwig = false, isStone = false;
            try { isWeeds = obj.IsWeeds(); } catch { }
            try { isTwig = obj.IsTwig(); } catch { }
            try { isStone = obj.IsBreakableStone(); } catch { }

            if (isWeeds) { _acc.Weeds++; return; }
            if (isTwig) { _acc.Twigs++; return; }
            if (isStone) { _acc.Stones++; return; }

            // 兜底：IsBreakableStone() 未覆盖时，仍按已知石类 ID 计入（详见 StoneIds 注释）。
            string id = null;
            try { id = obj.ItemId; } catch { }
            if (!string.IsNullOrEmpty(id) && StoneIds.Contains(id)) { _acc.Stones++; return; }

            if (IsMachine(obj))
            {
                _acc.MachinesTotal++;
                try
                {
                    SObject held = obj.heldObject.Value;
                    if (obj.readyForHarvest.Value || (held != null)) _acc.MachinesReady++;
                }
                catch { }
            }

            bool sprinkler = false;
            try { sprinkler = obj.IsSprinkler(); } catch { }
            if (sprinkler) _acc.Sprinklers++;
        }

        private static bool IsMachine(SObject obj)
        {
            try
            {
                if (!obj.bigCraftable.Value) return false;
                string id = obj.ItemId;
                return id != null && MachineIds.Contains(id);
            }
            catch { return false; }
        }
    }
}
