using System;
using System.Collections.Generic;
using System.Reflection;
using StardewValley;
using StardewValley.TerrainFeatures;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-170】作物"现在能不能收"的**唯一权威**（Mod 侧）。
    ///
    /// 背景（run A/B 共 284 次尝试、0 成功的事故；取证见 `docs\_il-harvest-path.md`）：
    /// 旧代码用**裸 `Crop.fullyGrown`** 当"熟了"（`WorldSnapshot.cs` 的 `t.Ripe`、
    /// `FarmScan.cs` 的 `RipeCrops`），而游戏真正给收的判据是 `HoeDirt.readyForHarvest()`
    /// （`scratch\il-hv-3.txt:2-48`）——两者差四类形态：
    ///
    /// | # | 形态 | 条件 |
    /// | - | ---- | ---- |
    /// | ① | 复收作物冷却期 | `fullyGrown && dayOfCurrentPhase > 0` |
    /// | ② | 阶段没走完 | `currentPhase &lt; phaseDays.Count - 1` |
    /// | ③ | 枯死 | `dead` |
    /// | ④ | 采集作物形态 2 | `forageCrop && whichForageCrop == "2"` |
    ///
    /// 落在这四类的格，旧 Mod **永远**报 `ripe=true`（实测 `(60,29)` 跨 8 个游戏日恒真），
    /// 游戏**永远**不给收 ⇒ 脑天天盯着一格摘不到的作物、把 sleep/recover 守卫钉死一整天。
    ///
    /// 【实现选择 · 为什么用反射】
    /// `Crop.HarvestMethod`、`currentPhase` 等成员在 1.6.15 上是**非 public** 的（编译期实证：
    /// 直接写 `crop.HarvestMethod` = `CS1061 未包含定义`），`HoeDirt.readyForHarvest()` 的可见性
    /// 也不保证。因此：
    ///   1. `Ready` **优先反射调用游戏自己的 `HoeDirt.readyForHarvest()`**（权威口径，找到就用）；
    ///   2. 拿不到时退回**等价的字段判据**（上面那条 IL 原文），字段同样用反射读；
    ///   3. 任一判据缺项 ⇒ **null（判不了）**：绝不当 `false`（漏掉真能收的），更**绝不**当"可收"。
    ///
    /// 反射结果按"类型.成员名"缓存（`_memberCache`），每帧不重复查表。
    /// </summary>
    internal static class CropMeta
    {
        private static readonly Dictionary<string, MemberInfo> _memberCache = new Dictionary<string, MemberInfo>();
        private static MethodInfo _readyMethod;
        private static bool _readyProbed;

        /// <summary>`Crop.HarvestMethod`（枚举 `HarvestMethod`）的字符串形式：`"Grab"` / `"Scythe"`；
        /// 没有作物 / 读不到 ⇒ null。</summary>
        internal static string HarvestMethodOf(Crop crop)
        {
            if (crop == null) return null;
            try { return ReadMember(crop, "HarvestMethod")?.ToString(); } catch { return null; }
        }

        /// <summary>`harvestMethod == Scythe` ⇒ 必须走**工具路径**（`HoeDirt.performToolAction`，
        /// `scratch\il-hv-4.txt:136-240`）；`interact` 的 `performUseAction` 分支永远摘不到它。</summary>
        internal static bool IsScythe(Crop crop)
        {
            try
            {
                return string.Equals(HarvestMethodOf(crop), "Scythe", StringComparison.OrdinalIgnoreCase);
            }
            catch { return false; }
        }

        /// <summary>作物是否**现在可收**（游戏口径）。`null` = 判不了（无作物 / 成员读不到）。</summary>
        internal static bool? Ready(HoeDirt dirt, Crop crop)
        {
            if (dirt == null || crop == null) return null;

            bool? direct = InvokeReadyForHarvest(dirt);
            if (direct != null) return direct;

            try
            {
                bool? fullyGrown = crop.fullyGrown != null ? (bool?)crop.fullyGrown.Value : null;
                int? dayOfPhase = NetIntOf(ReadMember(crop, "dayOfCurrentPhase"));
                int? phase = NetIntOf(ReadMember(crop, "currentPhase"));
                int? phases = CountOf(ReadMember(crop, "phaseDays"));
                bool? dead = crop.dead != null ? (bool?)crop.dead.Value : null;
                bool? forage = NetBoolOf(ReadMember(crop, "forageCrop"));
                string which = NetValue(ReadMember(crop, "whichForageCrop")) as string;

                if (fullyGrown == null || dayOfPhase == null || phase == null || phases == null || dead == null)
                    return null;                                  // 判据缺项 ⇒ 判不了（绝不猜）

                if (fullyGrown.Value && dayOfPhase.Value > 0) return false;   // ① 复收冷却
                if (phase.Value < phases.Value - 1) return false;             // ② 阶段没走完
                if (dead.Value) return false;                                 // ③ 枯死
                if (forage == true && which == "2") return false;             // ④ 采集作物形态 2
                return true;
            }
            catch { return null; }
        }

        /// <summary>把 TileView 上的作物形态字段一次填齐（读不到就留 null）。</summary>
        internal static void Fill(TileView t, Crop crop)
        {
            if (t == null || crop == null) return;
            t.FullyGrown = crop.fullyGrown != null ? (bool?)crop.fullyGrown.Value : (bool?)null;
            t.HarvestMethod = HarvestMethodOf(crop);
            t.CurrentPhase = NetIntOf(ReadMember(crop, "currentPhase"));
            t.PhaseDays = CountOf(ReadMember(crop, "phaseDays"));
            t.DayOfCurrentPhase = NetIntOf(ReadMember(crop, "dayOfCurrentPhase"));
            t.ForageCrop = NetBoolOf(ReadMember(crop, "forageCrop"));
            t.WhichForageCrop = NetValue(ReadMember(crop, "whichForageCrop")) as string;
            t.RegrowsAfterHarvest = InvokeBool(crop, "RegrowsAfterHarvest");
        }

        // ------------------------------------------------------------------ 反射工具

        private static bool? InvokeReadyForHarvest(HoeDirt dirt)
        {
            try
            {
                if (!_readyProbed)
                {
                    _readyProbed = true;
                    _readyMethod = typeof(HoeDirt).GetMethod(
                        "readyForHarvest",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
                        null, Type.EmptyTypes, null);
                }
                object v = _readyMethod?.Invoke(dirt, null);
                if (v is bool b) return b;
            }
            catch { }
            return null;
        }

        private static bool? InvokeBool(object obj, string method)
        {
            if (obj == null) return null;
            try
            {
                MethodInfo mi = obj.GetType().GetMethod(
                    method, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
                    null, Type.EmptyTypes, null);
                object v = mi?.Invoke(obj, null);
                if (v is bool b) return b;
            }
            catch { }
            return null;
        }

        private static object ReadMember(object obj, string name)
        {
            if (obj == null) return null;
            try
            {
                Type t = obj.GetType();
                string key = t.FullName + "." + name;
                MemberInfo mi;
                if (!_memberCache.TryGetValue(key, out mi))
                {
                    const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
                    mi = (MemberInfo)t.GetField(name, flags) ?? t.GetProperty(name, flags);
                    _memberCache[key] = mi;
                }
                FieldInfo fi = mi as FieldInfo;
                if (fi != null) return fi.GetValue(obj);
                PropertyInfo pi = mi as PropertyInfo;
                if (pi != null) return pi.GetValue(obj);
            }
            catch { }
            return null;
        }

        /// <summary>Net 字段（NetBool/NetInt/NetString…）取 `.Value`；拿不到 ⇒ null。</summary>
        private static object NetValue(object netField) => ReadMember(netField, "Value");

        private static bool? NetBoolOf(object netField)
        {
            object v = NetValue(netField);
            return v is bool b ? (bool?)b : null;
        }

        private static int? NetIntOf(object netField)
        {
            object v = NetValue(netField);
            return v is int i ? (int?)i : null;
        }

        private static int? CountOf(object listLike)
        {
            object v = ReadMember(listLike, "Count");
            return v is int i ? (int?)i : null;
        }
    }
}
