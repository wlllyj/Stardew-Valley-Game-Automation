using System;
using System.IO;
using System.Linq;
using System.Reflection;

// task-126 只读探针：打印 ShippingMenu / SaveGameMenu / Game1 日切保存链相关成员的**真实可见性**。
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
        // 1) ShippingMenu 的**全部**声明成员（可见性 + 签名）——okClicked/saveGameMenu/savedYet 是关键
        DumpAll("StardewValley.Menus.ShippingMenu");

        // 2) 基类 IClickableMenu 的退出相关成员（对比用）
        DumpNamed("StardewValley.Menus.IClickableMenu",
            "exitThisMenu", "emergencyShutDown", "cleanupBeforeExit", "behaviorBeforeCleanup",
            "exitFunction", "onExit", "gameWindowSizeChanged", "SetChildMenu", "_parentMenu");

        // 3) SaveGameMenu 的关键成员
        DumpNamed("StardewValley.Menus.SaveGameMenu",
            "complete", "update", "quit", "loader", "hasDrawn", "completePause", "saveText");

        // 4) Game1 的日切链状态
        DumpNamed("StardewValley.Game1",
            "endOfNightMenus", "showingEndOfNightStuff", "_afterNewDayAction", "showEndOfNightStuff",
            "PollForEndOfNewDaySync", "saveOnNewDay", "newDaySync", "IsSaving", "exitActiveMenu");

        // 5) NewDaySynchronizer 与 endOfNightStatus（脑侧 MODAL_WAIT_ONLY 里出现过 NewDaySavingMenu）
        DumpNamed("StardewValley.NewDaySynchronizer", "hasSaved", "flagSaved", "readyForSave", "destroy", "hasInstance");
        DumpNamed("StardewValley.BellsAndWhistles.PlayerStatusList", "UpdateState", "WithdrawState");
        DumpAll("StardewValley.Menus.NewDaySavingMenu");
    }

    private static void DumpAll(string fullName)
    {
        try
        {
            Assembly asm = Assembly.LoadFrom(Path.Combine(GameDir, "Stardew Valley.dll"));
            Type t = asm.GetType(fullName);
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
