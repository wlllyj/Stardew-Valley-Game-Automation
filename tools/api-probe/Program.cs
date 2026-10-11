using System;
using System.IO;
using System.Reflection;
using System.Text;
using ApiProbe;

// api-probe 从第 18 轮起也能"跑"：不只是编译期探针，还可以用反射**列出真实成员清单**
// （因为"猜成员名"已经浪费了两轮编译，改成读清单更省）。
//
// ⚠️ 游戏程序集是 `<Private>false</Private>` 引用的（探针不复制游戏 DLL），
//    所以运行时必须自己把 `Stardew Valley.dll` 等从游戏目录解析出来，
//    否则会 `FileNotFoundException: Could not load file or assembly 'Stardew Valley'`。
internal static class Program
{
    private static string _gameDir;

    private static void Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;

        _gameDir = args.Length > 0
            ? args[0]
            : Environment.GetEnvironmentVariable("STARDEW_GAME_PATH")
              ?? Environment.GetEnvironmentVariable("STARDEW_GAME_DIR")
              ?? @"D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley";

        AppDomain.CurrentDomain.AssemblyResolve += (_, e) =>
        {
            string simple = new AssemblyName(e.Name).Name + ".dll";
            string path = Path.Combine(_gameDir, simple);
            if (File.Exists(path)) return Assembly.LoadFrom(path);

            path = Path.Combine(_gameDir, "smapi-internal", simple);
            return File.Exists(path) ? Assembly.LoadFrom(path) : null;
        };

        Console.WriteLine("api-probe 反射模式：列出 sleep/buy/跨日/水源 相关成员（游戏目录 " + _gameDir + "）");
        Probe.DumpMembers();
    }
}
