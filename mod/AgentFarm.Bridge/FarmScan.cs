using System;
using System.Collections.Generic;
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

        // ---- 游戏内 ID 常量（1.6.x 的 ItemId 风格字符串）----
        private static readonly HashSet<string> MachineIds = new HashSet<string>(StringComparer.Ordinal)
        {
            "Furnace", "PreservesJar", "Keg", "Cask", "MayonnaiseMachine", "CheesePress", "ButterChurn",
            "Loom", "OilMaker", "RecyclingMachine", "SeedMaker", "Crystalarium", "CharcoalKiln",
            "SlimeIncubator", "SlimeEggPress", "Tapper", "HeavyTapper", "WormBin", "Dehydrator",
            "FishSmoker", "MushroomBox", "WoodChipper", "BaitMaker", "Anvil", "MiniForge", "SolarPanel",
        };

        // 石头的 ItemId：1.6 里是 (O)343 / (O)450 / (O)668 / (O)670 ...
        // 保守用“含 Stone 的 TypeDefinitionId 或已知小 ID 集合”，避免漏计/误计。
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
                        AccumulateTerrain(_terrain[_partialIndex].Value);
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
                Volatile.Write(ref _published, _acc);
                _publishedAtUtc = DateTime.UtcNow;
                ResetCycle();
            }
        }

        private void AccumulateTerrain(TerrainFeature tf)
        {
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

            string id = null;
            try { id = obj.ItemId; } catch { }

            if (!string.IsNullOrEmpty(id))
            {
                if (id == "Weeds") { _acc.Weeds++; return; }
                if (id == "Twig" || id == "Twigs") { _acc.Twigs++; return; }
                if (StoneIds.Contains(id)) { _acc.Stones++; return; }
            }

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
