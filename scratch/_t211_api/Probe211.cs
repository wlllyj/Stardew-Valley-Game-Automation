using System;
using System.IO;
using System.Linq;
using System.Reflection;

// task-211 只读探针：制作 / 放置 / 机器投料取货 三条链的成员可见性、签名、类型。
// 只反射元数据，不加载存档、不连游戏进程。
internal static class Probe211
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

    private static Assembly Game()
    {
        return Assembly.LoadFrom(Path.Combine(GameDir, "Stardew Valley.dll"));
    }

    private static Assembly Data()
    {
        return Assembly.LoadFrom(Path.Combine(GameDir, "StardewValley.GameData.dll"));
    }

    public static void DumpAll211()
    {
        // Q1：制作入口（CraftingRecipe 全部成员 → 找出 Craft / 材料检查 / 扣除）
        DumpAll("StardewValley.CraftingRecipe");

        // Q2/Q3/Q4：Object 上的放置 / 机器 / 状态成员
        DumpNamed("StardewValley.Object",
            "performObjectDropInAction", "checkForAction", "placementAction", "performDropDownAction",
            "performRemoveAction", "performUseAction", "heldObject", "readyForHarvest", "minutesUntilReady",
            "MinutesUntilReady", "bigCraftable", "GetMachineData", "PlaceInMachine", "OutputMachine",
            "onReadyForHarvest", "ShouldTimePassForMachine", "IsConsideredReadyMachineForComputer",
            "getOne", "ShowMenu", "Quality", "Stack", "ItemId", "QualifiedItemId", "TypeDefinitionId", "orderData",
            "performToolAction", "isForage", "IsHeldObjectReady");

        // Q1：大脑/Mod 侧要用到的 Farmer 成员（配方表、扣物品、当前物品）
        DumpNamed("StardewValley.Farmer",
            "craftingRecipes", "consumeObject", "craftItem", "hasCraftingRecipe", "GetCraftingRecipe",
            "ActiveObject", "ActiveItem", "CurrentItem", "CurrentTool", "Items", "currentLocation",
            "reduceActiveItemByOne", "GetEquippedTool");

        // Q2：放置入口的门闸（game 的 pressActionButton / tryToCheckAt）
        DumpNamed("StardewValley.Game1", "pressActionButton", "pressUseToolButton", "tryToCheckAt");

        // Q2/Q3：地点侧入口与对象访问
        DumpNamed("StardewValley.GameLocation",
            "checkAction", "getObjectAt", "objects", "characters", "performAction", "isPlaceableLocation");

        // Q2：游戏自己的放置结算入口
        DumpNamed("StardewValley.Utility", "tryToPlaceItem", "TryOpenShopMenu", "isThereAnObjectHere");

        // Q5：配方/机器数据（GameData 程序集）
        DumpTypesContaining("Crafting");
        DumpTypesContaining("Machine");
        DumpTypesContaining("Furnace");
    }

    private static void DumpTypesContaining(string fragment)
    {
        foreach (Assembly asm in new[] { Game(), Data() })
        {
            try
            {
                Type[] all = asm.GetTypes();
                foreach (Type t in all.Where(x => x.FullName != null && x.FullName.Contains(fragment))
                             .OrderBy(x => x.FullName))
                {
                    Console.WriteLine("=== [asm " + asm.GetName().Name + "][type] " + t.FullName + " : " + t.BaseType + " ===");
                    foreach (MemberInfo m in t.GetMembers(BindingFlags.Public | BindingFlags.NonPublic
                                | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                             .OrderBy(m => m.MemberType.ToString()).ThenBy(m => m.Name))
                    {
                        Console.WriteLine("  " + Describe(m));
                    }
                    Console.WriteLine();
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("=== [types containing " + fragment + " in " + asm.GetName().Name
                    + "] EX " + ex.GetType().Name + ": " + ex.Message);
            }
        }
    }

    private static Type FindType(string fullName)
    {
        Type t = Game().GetType(fullName);
        if (t != null) return t;
        t = Data().GetType(fullName);
        if (t != null) return t;
        // 兜底：按简单名/结尾搜（命名空间变了也能找到）
        string simple = fullName.Substring(fullName.LastIndexOf('.') + 1);
        foreach (Assembly asm in new[] { Game(), Data() })
        {
            try
            {
                foreach (Type cand in asm.GetTypes())
                {
                    if (cand.Name == simple || cand.FullName == fullName) return cand;
                }
            }
            catch { }
        }
        return null;
    }

    private static void DumpAll(string fullName)
    {
        try
        {
            Type t = FindType(fullName);
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
            Type t = FindType(fullName);
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
        if (m is EventInfo ei) return "event " + ei.EventHandlerType.Name + " " + ei.Name;
        return m.MemberType + " " + m.Name;
    }
}
