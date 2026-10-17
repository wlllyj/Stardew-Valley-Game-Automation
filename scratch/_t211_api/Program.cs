using System;

// 关键：Main 的方法体**不许出现任何 Stardew 类型**（否则 JIT Main 时 AssemblyResolve 未装 ⇒ FileNotFound）。
internal static class Program
{
    private static void Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        Probe211.GameDir = args.Length > 0
            ? args[0]
            : @"D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley";

        AppDomain.CurrentDomain.AssemblyResolve += Probe211.Resolve;

        try
        {
            Probe211.DumpAll211();
        }
        catch (Exception ex)
        {
            Console.WriteLine("EX: " + ex);
        }
    }
}
