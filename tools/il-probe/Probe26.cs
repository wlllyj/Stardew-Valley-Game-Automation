using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;

// 迷你 IL 反汇编器：用来读懂"游戏到底怎么触发传送"。
//
// 为什么需要它：猜字段语义、猜调用时机已经错了三次（每次都很像合理的结论）。
// 唯一可靠的办法是把相关方法的 IL 打出来看。
//
// operand 长度不手写，直接问 BCL：OpCode.OperandType → 字节数。
// 手写 opcode 表正是上一轮把静态/实例 ldfld 搞混的根源。
class Probe26
{
    static Dictionary<int, OpCode> _ops;

    static void Main(string[] args)
    {
        string g = args.Length > 0 ? args[0] : @"D:/Program Files (x86)/Steam/steamapps/common/Stardew Valley";
        var asm = Assembly.LoadFrom(System.IO.Path.Combine(g, "Stardew Valley.dll"));

        BuildOpTable();

        Dump(asm, "StardewValley.Pathfinding.PathFindController", "handleWarps");
        Dump(asm, "StardewValley.GameLocation", "getWarpFromDoor");
        Dump(asm, "StardewValley.GameLocation", "openDoor");
        Dump(asm, "StardewValley.GameLocation", "isCollidingWithWarpOrDoor");
        Dump(asm, "StardewValley.GameLocation", "isCollidingWithWarp");
        Dump(asm, "StardewValley.GameLocation", "isCollidingWithDoors");
    }

    static void BuildOpTable()
    {
        _ops = new Dictionary<int, OpCode>();
        foreach (var f in typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static))
        {
            if (f.FieldType != typeof(OpCode)) continue;
            var op = (OpCode)f.GetValue(null);
            int key = op.Size == 2 ? (0xFE00 | (byte)op.Value) : (byte)op.Value;
            _ops[key] = op;
        }
    }

    static int OperandSize(OperandType t, byte[] il, int pos)
    {
        switch (t)
        {
            case OperandType.InlineSwitch:
                {
                    int n = BitConverter.ToInt32(il, pos);
                    return 4 + 4 * n;
                }
            case OperandType.InlineNone: return 0;
            case OperandType.ShortInlineI:
            case OperandType.ShortInlineVar:
            case OperandType.ShortInlineBrTarget: return 1;
            case OperandType.InlineVar: return 2;
            case OperandType.ShortInlineR: return 4;
            case OperandType.InlineI:
            case OperandType.InlineBrTarget:
            case OperandType.InlineField:
            case OperandType.InlineMethod:
            case OperandType.InlineSig:
            case OperandType.InlineString:
            case OperandType.InlineTok:
            case OperandType.InlineType: return 4;
            case OperandType.InlineI8:
            case OperandType.InlineR: return 8;
            default: return 4;
        }
    }

    static void Dump(Assembly asm, string typeName, string methodName, int context = 999)
    {
        var t = asm.GetType(typeName);
        Console.WriteLine("================================================================");
        var ms = t?.GetMethods(BindingFlags.Public | BindingFlags.NonPublic |
                               BindingFlags.Instance | BindingFlags.Static)
                  .Where(m => m.Name == methodName).ToList();
        if (ms == null || ms.Count == 0) { Console.WriteLine($"(未找到 {typeName}.{methodName})"); return; }

        foreach (var m in ms)
        {
            Console.WriteLine($"--- {typeName}.{methodName}{DescribeParams(m)} ---");
            byte[] il;
            try { il = m.GetMethodBody()?.GetILAsByteArray(); }
            catch (Exception e) { Console.WriteLine("  取不到 IL: " + e.Message); continue; }
            if (il == null) { Console.WriteLine("  (无方法体)"); continue; }

            var mod = m.Module;
            int i = 0;
            while (i < il.Length)
            {
                int start = i;
                int key = il[i++];
                if (key == 0xFE && i < il.Length) key = 0xFE00 | il[i++];
                if (!_ops.TryGetValue(key, out var op)) { Console.WriteLine($"  IL_{start:X4}: <未知 opcode 0x{key:X2}>"); break; }

                int n = OperandSize(op.OperandType, il, i);
                string operand = "";
                try
                {
                    switch (op.OperandType)
                    {
                        case OperandType.InlineMethod:
                        case OperandType.InlineTok:
                            {
                                int tok = BitConverter.ToInt32(il, i);
                                object r = null;
                                try { r = mod.ResolveMethod(tok); } catch { try { r = mod.ResolveField(tok); } catch { } }
                                operand = r?.ToString() ?? $"tok 0x{tok:X8}";
                                break;
                            }
                        case OperandType.InlineField:
                            {
                                int tok = BitConverter.ToInt32(il, i);
                                object r = null;
                                try { r = mod.ResolveField(tok); } catch { }
                                operand = r?.ToString() ?? $"tok 0x{tok:X8}";
                                break;
                            }
                        case OperandType.InlineType:
                            {
                                int tok = BitConverter.ToInt32(il, i);
                                try { operand = mod.ResolveType(tok).FullName; } catch { operand = $"type 0x{tok:X8}"; }
                                break;
                            }
                        case OperandType.InlineSig:
                            operand = "sig";
                            break;
                        case OperandType.InlineString:
                            {
                                int tok = BitConverter.ToInt32(il, i);
                                try { operand = "\"" + mod.ResolveString(tok) + "\""; } catch { operand = $"str 0x{tok:X8}"; }
                                break;
                            }
                        case OperandType.InlineBrTarget:
                            {
                                int rel = BitConverter.ToInt32(il, i);
                                operand = $"-> IL_{i + 4 + rel:X4}";
                                break;
                            }
                        case OperandType.ShortInlineBrTarget:
                            {
                                sbyte rel = (sbyte)il[i];
                                operand = $"-> IL_{i + 1 + rel:X4}";
                                break;
                            }
                        case OperandType.InlineI:
                            operand = BitConverter.ToInt32(il, i).ToString();
                            break;
                        case OperandType.ShortInlineI:
                            operand = ((sbyte)il[i]).ToString();
                            break;
                        case OperandType.InlineVar:
                            operand = BitConverter.ToUInt16(il, i).ToString();
                            break;
                        case OperandType.ShortInlineVar:
                            operand = il[i].ToString();
                            break;
                    }
                }
                catch { }

                // 一律前进 n 字节。绝不能"只对我列举的类型前进"——
                // 漏掉 InlineType（castclass / isinst / box）会让整段反汇编错位，
                // 错位后打出来的"未知 opcode"完全是假象，反而更难查。
                if (n > 0)
                {
                    if (i + n > il.Length) break;
                    i += n;
                }

                if (!string.IsNullOrEmpty(operand))
                    Console.WriteLine($"  IL_{start:X4}: {op.Name,-14} {operand}");
            }
            Console.WriteLine();
        }
    }

    static string DescribeParams(MethodBase m) =>
        "(" + string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name + " " + p.Name)) + ")";
}
