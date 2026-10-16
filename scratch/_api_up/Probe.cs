using System;
using System.IO;
using System.Linq;
using System.Reflection;

// task-153 只读探针：铁匠铺工具升级链相关类型的**真实可见性/签名**。
// 不加载存档、不连游戏进程，只反射元数据。
internal static class Probe
{
    public static string GameDir;

    public static Assembly Resolve(object sender, ResolveEventArgs e)
    {
        string simple = new AssemblyName(e.Name).Name + ".dll";
        string path = Path.Combine(GameDir, simple);
        if (File.Exists(path)) return Assembly.LoadFrom(path);
        path = Path.Combine(GameDir, "smapi-internal", simple);
        return File.Exists(path) ? Assembly.LoadFrom(path) : null;
    }

    public static void DumpMembers()
    {
        // Q3：升级状态在 Farmer 上的确切字段名/类型/可见性
        DumpNamed("StardewValley.Farmer",
            "toolBeingUpgraded", "daysLeftForToolUpgrade", "hasReceivedToolUpgradeMessageYet",
            "showToolUpgradeAvailability");

        // Q3：Tool 的等级属性与升级继承入口
        DumpNamed("StardewValley.Tool",
            "UpgradeLevel", "UpgradeFrom", "GetToolData", "indexOfMenuItemView", "getOne", "actionWhenPurchased");

        // Q1/Q2：打开升级商店的公开入口
        DumpNamed("StardewValley.Utility", "TryOpenShopMenu");

        // Q4：价格/材料表的代码入口
        DumpNamed("StardewValley.Internal.ShopBuilder",
            "GetToolUpgradeData", "GetToolUpgradeConventionalPrice", "GetToolUpgradeConventionalTradeItem");

        // Q2/Q5：ShopMenu 的构造与购买入口
        DumpNamed("StardewValley.Menus.ShopMenu",
            ".ctor", "tryToPurchaseItem", "itemPriceAndStock", "ShopId", "chargePlayer",
            "getPlayerCurrencyAmount", "heldItem", "readOnly", "currency", "onPurchase", "getItemAt");

        // Q4：Data/Shops 的 ToolUpgradeLevel / TradeItem* 字段名
        DumpAll("StardewValley.GameData.Shops.ShopItemData");
        DumpAll("StardewValley.GameData.Tools.ToolData");
        DumpAll("StardewValley.GameData.Tools.ToolUpgradeData");

        // Q7：ResourceClump 的类型区分与等级门槛
        DumpNamed("StardewValley.TerrainFeatures.ResourceClump",
            ".ctor", "parentSheetIndex", "health", "width", "height", "performToolAction",
            "ResourceClumpType", "GetData", "resourceClumpIndex");
    }

    private static void DumpAll(string fullName)
    {
        try
        {
            Assembly asm = Assembly.LoadFrom(Path.Combine(GameDir, "Stardew Valley.dll"));
            Type t = asm.GetType(fullName);
            if (t == null)
            {
                asm = Assembly.LoadFrom(Path.Combine(GameDir, "StardewValley.GameData.dll"));
                t = asm.GetType(fullName);
            }
            if (t == null) { Console.WriteLine("=== " + fullName + " ===\n  (类型不存在)\n"); return; }
            Console.WriteLine("=== " + t.FullName + " (全部声明成员) ===");
            foreach (MemberInfo m in t.GetMembers(BindingFlags.Public | BindingFlags.NonPublic
                        | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                     .OrderBy(m => m.MemberType.ToString()).ThenBy(m => m.Name))
            {
                Console.WriteLine("  " + Describe(m));
            }
            Console.WriteLine();
        }
        catch (Exception ex)
        {
            Console.WriteLine("=== " + fullName + " ===\n  EX " + ex.GetType().Name + ": " + ex.Message + "\n");
        }
    }

    private static void DumpNamed(string fullName, params string[] names)
    {
        try
        {
            Assembly asm = Assembly.LoadFrom(Path.Combine(GameDir, "Stardew Valley.dll"));
            Type t = asm.GetType(fullName);
            if (t == null) { Console.WriteLine("=== " + fullName + " ===\n  (类型不存在)\n"); return; }
            Console.WriteLine("=== " + t.FullName + " ===");
            foreach (string name in names)
            {
                MemberInfo[] members = t
                    .GetMembers(BindingFlags.Public | BindingFlags.NonPublic
                                | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                    .Where(m => m.Name == name || m.Name == "get_" + name || m.Name == "set_" + name)
                    .ToArray();
                if (members.Length == 0) { Console.WriteLine("  [缺失] " + name); continue; }
                foreach (MemberInfo m in members) Console.WriteLine("  " + Describe(m));
            }
            Console.WriteLine();
        }
        catch (Exception ex)
        {
            Console.WriteLine("=== " + fullName + " ===\n  EX " + ex.GetType().Name + ": " + ex.Message + "\n");
        }
    }

    private static string Describe(MemberInfo m)
    {
        if (m is MethodBase mb)
        {
            string vis = mb.IsPublic ? "public"
                : mb.IsAssembly ? "internal"
                : mb.IsFamily ? "protected"
                : mb.IsFamilyOrAssembly ? "protected internal"
                : "private";
            string stat = mb.IsStatic ? "static " : "";
            string ps = string.Join(", ", mb.GetParameters().Select(p => p.ParameterType.Name + " " + p.Name));
            return $"{vis} {stat}{mb.MemberType} {mb.Name}({ps})";
        }
        if (m is FieldInfo fi)
        {
            string vis = fi.IsPublic ? "public" : fi.IsAssembly ? "internal" : fi.IsFamily ? "protected" : "private";
            return $"{vis} {(fi.IsStatic ? "static " : "")}field {fi.FieldType.Name} {fi.Name}";
        }
        if (m is PropertyInfo pi)
        {
            MethodInfo g = pi.GetGetMethod(true);
            string vis = g == null ? "?" : g.IsPublic ? "public" : g.IsAssembly ? "internal" : g.IsFamily ? "protected" : "private";
            return $"{vis} property {pi.PropertyType.Name} {pi.Name}";
        }
        return m.MemberType + " " + m.Name;
    }
}
