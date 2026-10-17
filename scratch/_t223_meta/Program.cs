using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Text;

// 只读：扫描一个托管 DLL 里所有方法体的 IL，找出引用了指定字符串字面量（ldstr）的方法。
// 为什么需要它：il-probe 的 FINDSTR| 对 ldstr 恒 0 命中（ldstr 是 token 不是内联文本），
// 而 System.Reflection.Metadata 能正确解析 #US 堆 + ldstr token。
internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.WriteLine("用法: T223Meta <路径.dll> <子串> [--exact]");
            return 2;
        }
        string dll = args[0];
        string needle = args[1];
        bool exact = args.Length > 2 && args[2] == "--exact";
        using var fs = File.OpenRead(dll);
        using var pe = new PEReader(fs);
        var md = pe.GetMetadataReader();
        int hits = 0;
        foreach (var handle in md.MethodDefinitions)
        {
            var mdef = md.GetMethodDefinition(handle);
            if (mdef.RelativeVirtualAddress == 0) continue;
            var body = pe.GetMethodBody(mdef.RelativeVirtualAddress);
            var il = body.GetILBytes();
            if (il == null) continue;
            for (int i = 0; i + 4 < il.Length; i++)
            {
                if (il[i] != 0x72) continue; // ldstr
                int token = BitConverter.ToInt32(il, i + 1);
                if ((token & 0xFF000000) != 0x70000000) continue;
                int offset = token & 0x00FFFFFF;
                string s;
                try { s = md.GetUserString(MetadataTokens.UserStringHandle(offset)); }
                catch (Exception) { continue; }
                if (s == null) continue;
                bool ok = exact ? s == needle : s.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0;
                if (!ok) continue;
                hits++;
                string typeName = "";
                try
                {
                    var td = md.GetTypeDefinition(mdef.GetDeclaringType());
                    typeName = md.GetString(td.Namespace) + "." + md.GetString(td.Name);
                }
                catch (Exception) { typeName = "?"; }
                Console.WriteLine(typeName + "::" + md.GetString(mdef.Name) + "  =>  \"" + s.Replace("\n", "\\n") + "\"");
            }
        }
        Console.WriteLine("[ok] hits=" + hits);
        return 0;
    }
}
