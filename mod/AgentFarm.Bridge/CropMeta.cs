using System;
using System.Collections.Generic;
using System.Reflection;
using StardewValley;
using StardewValley.GameData.Crops;
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
    /// 【task-176 更正】
    ///   * `harvestMethod` 的正确入口是**公开方法 `Crop.GetHarvestMethod()`**（不是字段 `HarvestMethod`）
    ///     —— 旧写法恒 null，镰刀类作物因此永远走 `interact`、永远摘不到；
    ///   * `Ready` 现在一并返回**来源**（`"game"` / `"fields"` / `null`），落进 `tiles[].readySource`：
    ///     没有来源标记，就无法定案"到底是游戏说的、还是我们兜底猜的"（task-173 的 FAIL 正是这样被掩盖的）；
    ///   * `"fields"` 只允许在**逐条等价**（上面 ①–④ + 全字段可读）时给出；否则 `(null, null)`。
    ///
    /// 反射结果按"类型.成员名"缓存（`_memberCache`），每帧不重复查表。
    /// </summary>
    internal static class CropMeta
    {
        private static readonly Dictionary<string, MemberInfo> _memberCache = new Dictionary<string, MemberInfo>();
        private static MethodInfo _readyMethod;
        private static bool _readyProbed;

        /// <summary>`Crop.GetHarvestMethod()`（枚举 `HarvestMethod`）的字符串形式：`"Grab"` / `"Scythe"`；
        /// 没有作物 / 读不到 ⇒ **null**（判不了，绝不默认 `Grab`）。</summary>
        ///
        /// <remarks>
        /// 【task-176 必修 ①】旧实现按**字段名** `HarvestMethod` 去读 ⇒ 1.6.15 上 `Crop` 根本没有这个
        /// 字段/属性 ⇒ 恒 `null` ⇒ `harvest_tool()` 恒 `null` ⇒ 镰刀类作物永远走 `interact`，
        /// 而 `HoeDirt.performUseAction` 的 grab 分支对 Scythe 类作物**永远摘不到**。
        ///
        /// 正确入口 = **公开方法 `Crop.GetHarvestMethod()`**（api-probe IL，`scratch\_t176_gethm.txt`）：
        /// <code>
        ///   CropData d = this.GetData();
        ///   if (d == null) return 0;            // 0 = HarvestMethod.Grab
        ///   return d.HarvestMethod;
        /// </code>
        /// `FIND|GetHarvestMethod` 的调用者正是 `HoeDirt.performUseAction` / `performToolAction`
        /// （`scratch\_t176_find_gethm.txt`），与 `scratch\il-hv-4.txt` 的镰刀路径对得上。
        /// 反射失败才退回 `GetData().HarvestMethod`；两条都不通 ⇒ null（键仍要输出，见 Contracts）。
        /// </remarks>
        internal static string HarvestMethodOf(Crop crop)
        {
            if (crop == null) return null;
            try
            {
                // 【task-176 必修 ①】`Crop.GetHarvestMethod()` 是 **public 无参方法** ⇒ 直接调，
                // 不反射（Lead 侧独立探针复核：`scratch\_lead_ghm.txt`，并确认
                // `StardewValley.Crop.HarvestMethod` 字段/属性在 1.6.15 **根本不存在** ——
                // 这才是旧实现恒 null 的原因，不是可见性问题）。
                switch (crop.GetHarvestMethod())
                {
                    case HarvestMethod.Grab: return "Grab";      // 0
                    case HarvestMethod.Scythe: return "Scythe";  // 1
                    default: return ((int)crop.GetHarvestMethod()).ToString();  // 未知值照实写
                }
            }
            catch { return null; }
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

        /// <summary>作物是否**现在可收**（游戏口径），以及结论的来源。
        /// `Value == null` = 判不了（无作物 / 成员读不到）；`Source` ∈ `"game"` / `"fields"` / `null`。</summary>
        ///
        /// <remarks>
        /// 【task-176 必修 ②】来源必须落账：`"game"` = 真的调用了 `HoeDirt.readyForHarvest()`；
        /// `"fields"` = 反射不可用、退回**与该方法 IL 逐条等价**的字段判据（见下方注释）；
        /// `null` = 判不了。**绝不许**用"宽松"字段判据冒充实测 `true` —— 只有逐条等价才允许
        /// 给 `"fields"` 结论，任一判据字段读不到就返回 `(null, null)`（fail-closed）。
        /// </remarks>
        internal static (bool? Value, string Source) Ready(HoeDirt dirt, Crop crop)
        {
            if (dirt == null || crop == null) return (null, null);

            // 【task-182 必修 4（GAP-1）】判据本体搬进 `ClumpRules.Ready`（纯函数、不引用游戏类型）
            // ⇒ 最小 C# 自检工程能直接跑**行为断言**（`mod/AgentFarm.Bridge.Tests`，Python 侧
            // `tests/test_longrun.py::TestTask182ClumpRulesBehaviour` 负责调它）。
            // 本方法从此只做**取数**一件事：反射问游戏 + 反射读字段。
            // 纪律：这里**只允许有一条 return**（那条委托）；任何"提前 return 兜底值"的变异
            // 都会被 Python 侧的结构契约当场抓住（见 `TestTask182*` 的结构断言）。
            bool? gameSaid = InvokeReadyForHarvest(dirt);
            try
            {
                bool? fullyGrown = crop.fullyGrown != null ? (bool?)crop.fullyGrown.Value : null;
                int? dayOfPhase = NetIntOf(ReadMember(crop, "dayOfCurrentPhase"));
                int? phase = NetIntOf(ReadMember(crop, "currentPhase"));
                int? phases = CountOf(ReadMember(crop, "phaseDays"));
                bool? dead = crop.dead != null ? (bool?)crop.dead.Value : null;
                bool? forage = NetBoolOf(ReadMember(crop, "forageCrop"));
                string which = NetValue(ReadMember(crop, "whichForageCrop")) as string;
                return ClumpRules.Ready(gameSaid, fullyGrown, dayOfPhase, phase, phases, dead, forage, which);
            }
            catch { return (null, null); }
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

        /// <summary>无参实例方法调用（public/non-public 都试）；拿不到返回值 ⇒ null。</summary>
        private static object InvokeMethod(object obj, string method)
        {
            if (obj == null) return null;
            try
            {
                MethodInfo mi = obj.GetType().GetMethod(
                    method, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
                    null, Type.EmptyTypes, null);
                return mi?.Invoke(obj, null);
            }
            catch { return null; }
        }

        private static bool? InvokeBool(object obj, string method)
        {
            object v = InvokeMethod(obj, method);
            return v is bool b ? (bool?)b : null;
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
