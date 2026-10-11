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
        // 游戏目录：命令行第一参数 > 环境变量 STARDEW_GAME_DIR > 旧机器硬编码路径（仅最后兜底）。
        string g = args.Length > 0
            ? args[0]
            : Environment.GetEnvironmentVariable("STARDEW_GAME_DIR")
              ?? @"D:/Program Files (x86)/Steam/steamapps/common/Stardew Valley";
        var asm = Assembly.LoadFrom(System.IO.Path.Combine(g, "Stardew Valley.dll"));

        BuildOpTable();

        // 额外目标：命令行里每个 `Type|Method` 都 dump 一次（README 建议的改造，避免改代码重编译）。
        var targets = new List<(string Type, string Method)>();
        if (args.Length <= 1)
            targets.AddRange(new (string, string)[]
            {
                ("StardewValley.Pathfinding.PathFindController", "handleWarps"),
                ("StardewValley.GameLocation", "getWarpFromDoor"),
                ("StardewValley.GameLocation", "openDoor"),
                ("StardewValley.GameLocation", "isCollidingWithWarpOrDoor"),
                ("StardewValley.GameLocation", "isCollidingWithWarp"),
                ("StardewValley.GameLocation", "isCollidingWithDoors"),
            });

        foreach (var a in args.Skip(1))
        {
            int bar = a.IndexOf('|');
            if (bar <= 0 || bar == a.Length - 1)
            {
                Console.WriteLine($"(忽略无法解析的目标参数：{a}；格式应为 Type|Method)");
                continue;
            }
            targets.Add((a.Substring(0, bar), a.Substring(bar + 1)));
        }

        foreach (var (type, method) in targets)
        {
            // `FIND|子串` ⇒ **在整个程序集里找出"谁调用了名字含该子串的方法"**。
            // 【为什么要它】"谁调用了 `HoeDirt.plant`"这类问题靠逐个 dump 猜太慢
            //（真机上就卡在这儿：`Object.performUseAction`、`GameLocation.leftClick`
            //  的 IL 里都不含 plant 调用，可播种明明要调它）。
            if (string.Equals(type, "FIND", StringComparison.Ordinal))
            {
                FindCallers(asm, method);   // 命令行写 `FIND|子串`（参数解析会把两边拆成 type/method）
                continue;
            }

            // `FINDSTR|子串` ⇒ **在整个程序集里找出"IL 里出现了该字符串"的方法**。
            // 【为什么要它】有些关键流程**没有任何可检索的方法名**，只能靠游戏自己的提示文本反查：
            // 例如"睡觉"—— 床是怎么把玩家送进睡眠确认框的？全程序集里 `Furniture.performAction`
            // 根本不存在，但 `Game1` 的某处一定处理了 `sleep` / `Sleep` 字样的对话键。
            // 逐个类型 dump 不可能（Stardew Valley.dll 有上千个类型），所以让工具反过来找。
            if (string.Equals(type, "FINDSTR", StringComparison.Ordinal))
            {
                FindStringUsers(asm, method);   // 命令行写 `FINDSTR|子串`
                continue;
            }

            // `DISASM|子串` ⇒ 把"IL 里出现该字符串"的方法**逐个反汇编出来**（配合 FINDSTR 用：
            // FINDSTR 只给名字，确认名字后再用 DISASM 看它到底做了什么）。
            if (string.Equals(type, "DISASM", StringComparison.Ordinal))
            {
                DumpStringUsers(asm, method);   // 命令行写 `DISASM|子串`
                continue;
            }

            // `外层类型+嵌套名子串|方法` ⇒ dump 匹配到的**嵌套类型**（迭代器状态机就靠这个）。
            int plus = type.IndexOf('+');
            if (plus > 0)
            {
                string outerName = type.Substring(0, plus);
                string nestedSub = type.Substring(plus + 1);
                var outer = asm.GetType(outerName);
                bool any = false;
                foreach (var nt in outer?.GetNestedTypes(BindingFlags.Public | BindingFlags.NonPublic) ?? Type.EmptyTypes)
                {
                    if (!nt.Name.Contains(nestedSub)) continue;
                    DumpType(nt, nt.FullName, method);
                    any = true;
                }
                if (!any) Console.WriteLine($"(未找到 {outerName} 里名字含 \"{nestedSub}\" 的嵌套类型)");
                continue;
            }

            Dump(asm, type, method);
        }
    }

    /// <summary>
    /// 在**整个程序集**里找出"IL 里含有某个字符串字面量"的方法（不反汇编，只报名字）。
    ///
    /// 用途：反向定位"没有任何好搜的方法名、但游戏一定会用到某段提示文本"的流程。
    /// 例：`FINDSTR|Sleep` 能直接指出"谁在处理睡觉确认"。
    ///
    /// 实现注意：IL 里的 `ldstr` 是 UTF-16LE 字节，所以直接把 IL 字节当 UTF-16 解一遍找子串，
    /// 比逐条反汇编再 ResolveString 快得多（上千类型 × 每个方法都反汇编太慢）。
    /// </summary>
    static void FindStringUsers(Assembly asm, string needle)
    {
        int hits = 0;
        foreach (var t in SafeTypes(asm))
        {
            foreach (var m in SafeMethods(t))
            {
                byte[] il;
                try { il = m.GetMethodBody()?.GetILAsByteArray(); }
                catch { continue; }
                if (il == null || il.Length < 2) continue;
                if (IlContainsString(il, needle))
                {
                    Console.WriteLine($"[FINDSTR] {t.FullName}.{m.Name}{DescribeParams(m)}");
                    hits++;
                }
            }
        }
        Console.WriteLine($"[FINDSTR] \"{needle}\" 命中 {hits} 个方法");
    }

    /// <summary>
    /// 同 <see cref="FindStringUsers"/>，但把命中的方法**逐个反汇编**出来
    /// （`FINDSTR` 给名单，`DISASM` 给正文；两步分开是因为正文可能很长）。
    /// </summary>
    static void DumpStringUsers(Assembly asm, string needle)
    {
        int hits = 0;
        foreach (var t in SafeTypes(asm))
        {
            foreach (var m in SafeMethods(t))
            {
                byte[] il;
                try { il = m.GetMethodBody()?.GetILAsByteArray(); }
                catch { continue; }
                if (il == null || il.Length < 2) continue;
                if (!IlContainsString(il, needle)) continue;
                Console.WriteLine("================================================================");
                Disassemble(m, il, $"{t.FullName}.{m.Name}");
                hits++;
            }
        }
        Console.WriteLine($"[DISASM] \"{needle}\" 反汇编了 {hits} 个方法");
    }

    static IEnumerable<Type> SafeTypes(Assembly asm)
    {
        Type[] ts;
        try { ts = asm.GetTypes(); }
        catch (ReflectionTypeLoadException e) { ts = e.Types.Where(x => x != null).ToArray(); }
        return ts.Where(t => t != null);
    }

    static IEnumerable<MethodBase> SafeMethods(Type t)
    {
        MethodBase[] ms = null;
        try
        {
            ms = t.GetMethods(BindingFlags.Public | BindingFlags.NonPublic |
                              BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                  .Cast<MethodBase>().ToArray();
        }
        catch { }
        return ms ?? Array.Empty<MethodBase>();
    }

    static bool IlContainsString(byte[] il, string needle)
    {
        // IL 是 UTF-16LE；用 Encoding.Unicode 解出来的文本里找 needle 即可。
        // （若 needle 含中文，命令行传参时请确保控制台是 UTF-8 —— 否则 needle 本身就已经烂了。）
        var text = System.Text.Encoding.Unicode.GetString(il);
        return text.IndexOf(needle, StringComparison.Ordinal) >= 0;
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

    /// <summary>
    /// 扫描整个程序集，找出**调用了名字含 <paramref name="needle"/> 的方法**的那些方法，打印调用点。
    ///
    /// 实现口径：把每个方法的 IL 按位置逐个 4 字节当元数据 token 试着 `ResolveMethod`，
    /// 命中且方法名包含子串就报一行。**会有假阳性**（字节碰巧构成合法 token），
    /// 但用来回答"谁调用了 X"这种定位问题足够，且每条都能再用 `Type|Method` dump 复核。
    /// </summary>
    static void FindCallers(Assembly asm, string needle)
    {
        Type[] types;
        try { types = asm.GetTypes(); }
        catch (System.Reflection.ReflectionTypeLoadException e)
        {
            types = e.Types.Where(x => x != null).ToArray();
        }
        catch (Exception) { types = new Type[0]; }

        int hits = 0;
        foreach (var t in types)
        {
            if (t == null) continue;
            IEnumerable<MethodBase> ms;
            try
            {
                ms = t.GetMethods(BindingFlags.Public | BindingFlags.NonPublic |
                                  BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                      .Cast<MethodBase>()
                      .Concat(t.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic |
                                                BindingFlags.Instance | BindingFlags.DeclaredOnly));
            }
            catch { continue; }

            foreach (var m in ms)
            {
                byte[] il = null;
                try { il = m.GetMethodBody()?.GetILAsByteArray(); } catch { }
                if (il == null) continue;

                for (int i = 0; i + 4 <= il.Length; i++)
                {
                    int tok = BitConverter.ToInt32(il, i);
                    MethodBase mb;
                    try { mb = m.Module.ResolveMethod(tok); } catch { continue; }
                    if (mb == null) continue;
                    if (mb.Name.IndexOf(needle, StringComparison.OrdinalIgnoreCase) < 0) continue;

                    Console.WriteLine($"  {t.FullName}.{m.Name}({DescribeParams(m)})  →  {mb.DeclaringType?.FullName}.{mb.Name}");
                    hits++;
                    break;   // 一个方法只报一次
                }
            }
        }
        Console.WriteLine($"（FIND|{needle}：命中 {hits} 个调用方法；4 字节滑动扫描可能有假阳性，命中项可用 Type|Method 复核）");
    }

    static void Dump(Assembly asm, string typeName, string methodName, int context = 999)
    {
        var t = asm.GetType(typeName);
        DumpType(t, typeName, methodName);
    }

    /// <summary>
    /// 真正的 dump 实现（按 <see cref="Type"/>）。
    ///
    /// 【为什么要单独拆出来】编译器生成的**嵌套类型**（迭代器状态机
    /// <c>&lt;getLoadEnumerator&gt;d__12</c> 之类）只能在拿到外层类型后遍历
    /// <c>GetNestedTypes()</c> 才能找到 —— 而"这个方法到底怎么拼存档路径"这类问题，
    /// 答案恰恰在迭代器的 <c>MoveNext</c> 里，不在外层方法里。
    /// </summary>
    static void DumpType(Type t, string typeName, string methodName)
    {
        Console.WriteLine("================================================================");
        // 方法名以 `*` 结尾 ⇒ 按"包含"匹配（用来 dump 编译器生成的 lambda，例如 `<getLoadEnumerator>b__0`）。
        bool contains = methodName.EndsWith("*");
        string needle = contains ? methodName.TrimEnd('*') : methodName;

        // 【2026-10-11 加】构造函数：方法名写 `.ctor` / `.cctor`。
        // 需要它是因为"某个类到底有哪些构造重载"只能问 GetConstructors（GetMethods 拿不到 .ctor），
        // 而"PathFindController 能不能接受一条**给定路径**"正是这条线索。
        List<MethodBase> ms;
        if (methodName == ".ctor" || methodName == ".cctor")
        {
            bool wantStatic = methodName == ".cctor";
            ms = t == null
                ? new List<MethodBase>()
                : t.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic |
                                    BindingFlags.Instance | BindingFlags.Static)
                   .Where(c => c.IsStatic == wantStatic)
                   .Cast<MethodBase>().ToList();
        }
        else
        {
            ms = t?.GetMethods(BindingFlags.Public | BindingFlags.NonPublic |
                               BindingFlags.Instance | BindingFlags.Static)
                  .Where(m => contains ? m.Name.Contains(needle) : m.Name == needle)
                  .Cast<MethodBase>().ToList();
        }

        if (ms == null || ms.Count == 0) { Console.WriteLine($"(未找到 {typeName}.{methodName})"); return; }

        foreach (var m in ms)
        {
            Console.WriteLine($"--- {typeName}.{methodName}{DescribeParams(m)} ---");
            byte[] il;
            try { il = m.GetMethodBody()?.GetILAsByteArray(); }
            catch (Exception e) { Console.WriteLine("  取不到 IL: " + e.Message); continue; }
            if (il == null) { Console.WriteLine("  (无方法体)"); continue; }

            Disassemble(m, il, null);
        }
    }

    /// <summary>
    /// 把一个方法体反汇编出来。<paramref name="label"/> 非空时先打一行标题
    /// （`DISASM|`/`FINDSTR|` 模式用；`Dump` 自己已经打过标题，所以传 null）。
    /// </summary>
    static void Disassemble(MethodBase m, byte[] il, string label)
    {
        if (label != null)
            Console.WriteLine($"--- {label}{DescribeParams(m)} ---");

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

                // 【2026-10-11 修掉的一个静默漏打 bug】原版是
                //     `if (!string.IsNullOrEmpty(operand)) Console.WriteLine(...)`
                // —— 于是所有**没有操作数**的指令（`ldarg.0/1`、`ldloc`、`stloc`、`ret`、
                // `add`、`pop`、`br`… 即 OperandType.InlineNone）全被悄悄丢掉了！
                // 表现是 dump 里 IL 偏移不连续（例如 IL_0000 → IL_0008 中间少了 3 个字节），
                // 而 `ret` 是**控制流**：看不见它就会把"这里提前返回了"读成"顺序往下执行"。
                // 证据：本工具早先关于 `Farmer.Halt()` / `PathFindController.update` 的阅读
                // 都是在带这个 bug 的版本上做的 —— 必须重打一遍才算数。
                Console.WriteLine(string.IsNullOrEmpty(operand)
                    ? $"  IL_{start:X4}: {op.Name}"
                    : $"  IL_{start:X4}: {op.Name,-14} {operand}");
        }
        Console.WriteLine();
    }

    static string DescribeParams(MethodBase m) =>
        "(" + string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name + " " + p.Name)) + ")";
}
