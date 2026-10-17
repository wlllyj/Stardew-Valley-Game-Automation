using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using Microsoft.Xna.Framework.Content;

internal static class Program
{
    private static string GameDir = @"D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley";

    // 静态构造里注册程序集解析（此时还没 JIT 到任何 MonoGame 类型）；
    // 若放在 Main 里就太晚：Main 的方法签名/IL 一加载就要 MonoGame.Framework。
    static Program()
    {
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string name = new AssemblyName(e.Name).Name + ".dll";
            string p = Path.Combine(GameDir, name);
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
    }

    private static int Main(string[] args) => Run(args);

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    private static int Run(string[] args)
    {
        // 用法：
        //   T223Xnb <asset> [--key NAME] [--contains TEXT] [--out FILE] [--max N]
        // asset 例：Data/CraftingRecipes、Data/mail、Data/TriggerActions、Data/Powers
        if (args.Length == 0)
        {
            Console.WriteLine("用法: T223Xnb <asset> [--key NAME] [--contains TEXT] [--out FILE] [--max N]");
            return 2;
        }
        string asset = args[0];
        var keys = new List<string>();
        var contains = new List<string>();
        string outFile = null;
        int maxLines = 200000;
        for (int i = 1; i < args.Length - 1; i++)
        {
            switch (args[i])
            {
                case "--key": keys.Add(args[++i]); break;
                case "--contains": contains.Add(args[++i]); break;
                case "--out": outFile = args[++i]; break;
                case "--max": int.TryParse(args[++i], out maxLines); break;
            }
        }

        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string name = new AssemblyName(e.Name).Name + ".dll";
            string p = Path.Combine(GameDir, name);
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        foreach (var dll in new[] { "MonoGame.Framework.dll", "StardewValley.GameData.dll", "Stardew Valley.dll", "xTile.dll" })
        {
            try { Assembly.LoadFrom(Path.Combine(GameDir, dll)); }
            catch (Exception ex) { Console.WriteLine("[warn] load " + dll + ": " + ex.Message); }
        }

        ContentManager cm;
        try { cm = new ContentManager(new DummyProvider(), Path.Combine(GameDir, "Content")); }
        catch (Exception ex) { Console.WriteLine("[fatal] ContentManager 构造失败: " + ex); return 3; }

        object root;
        try
        {
            // 用非泛型方式调 Load<object>，让 XNB 自己的 type reader 决定运行时类型
            var load = typeof(ContentManager).GetMethods(BindingFlags.Public | BindingFlags.Instance)
                .First(m => m.Name == "Load" && m.IsGenericMethodDefinition && m.GetParameters().Length == 1);
            root = load.MakeGenericMethod(typeof(object)).Invoke(cm, new object[] { asset });
        }
        catch (Exception ex)
        {
            var inner = ex is TargetInvocationException tie ? tie.InnerException : ex;
            Console.WriteLine("[fatal] 读 " + asset + " 失败: " + inner);
            return 4;
        }

        var lines = new List<string>();
        Walk(root, "", lines, 0, Math.Max(1, maxLines));
        int shown = 0;
        var sb = new StringBuilder();
        foreach (var line in lines)
        {
            bool ok = keys.Count == 0 || keys.Any(k => line.IndexOf("[" + k + "]", StringComparison.OrdinalIgnoreCase) >= 0
                                                     || line.StartsWith(k + "\t", StringComparison.OrdinalIgnoreCase)
                                                     || line.IndexOf("[" + k + "] =", StringComparison.OrdinalIgnoreCase) >= 0);
            if (ok && contains.Count > 0)
            {
                ok = contains.Any(c => line.IndexOf(c, StringComparison.OrdinalIgnoreCase) >= 0);
            }
            if (!ok) continue;
            if (shown++ >= maxLines) break;
            sb.AppendLine(line);
        }
        string text = sb.ToString();
        if (outFile != null)
        {
            File.WriteAllText(outFile, text, new UTF8Encoding(false));
            Console.WriteLine("[ok] " + asset + " 运行时类型=" + root?.GetType().FullName + " 行数=" + shown + " -> " + outFile);
        }
        else
        {
            Console.Write(text);
            Console.WriteLine("[ok] " + asset + " 运行时类型=" + root?.GetType().FullName + " 行数=" + shown);
        }
        return 0;
    }

    private sealed class DummyProvider : IServiceProvider
    {
        public object GetService(Type serviceType) => null;
    }

    private static void Walk(object node, string path, List<string> lines, int depth, int maxLines)
    {
        if (node == null) { lines.Add(path + " = <null>"); return; }
        if (lines.Count >= maxLines) return;
        if (node is string s) { lines.Add(path + " = " + s); return; }
        if (node is IConvertible && (node is int || node is long || node is bool || node is double || node is float || node is byte))
        {
            lines.Add(path + " = " + Convert.ToString(node, System.Globalization.CultureInfo.InvariantCulture));
            return;
        }
        if (depth > 6) { lines.Add(path + " = <深度截断 " + node.GetType().Name + ">"); return; }

        if (node is IDictionary dict)
        {
            foreach (DictionaryEntry kv in dict)
            {
                Walk(kv.Value, path + "[" + kv.Key + "]", lines, depth + 1, maxLines);
            }
            return;
        }
        if (node is IEnumerable en)
        {
            int i = 0;
            foreach (var item in en)
            {
                Walk(item, path + "[" + i++ + "]", lines, depth + 1, maxLines);
            }
            return;
        }
        // 自定义类型：反射字段与属性
        var t = node.GetType();
        bool any = false;
        foreach (var f in t.GetFields(BindingFlags.Public | BindingFlags.Instance))
        {
            any = true;
            Walk(f.GetValue(node), path + "." + f.Name, lines, depth + 1, maxLines);
        }
        foreach (var p in t.GetProperties(BindingFlags.Public | BindingFlags.Instance))
        {
            if (p.GetIndexParameters().Length > 0) continue;
            any = true;
            try { Walk(p.GetValue(node), path + "." + p.Name, lines, depth + 1, maxLines); }
            catch (Exception) { }
        }
        if (!any) lines.Add(path + " = " + node);
    }
}
