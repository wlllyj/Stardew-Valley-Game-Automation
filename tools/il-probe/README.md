# il-probe —— 迷你 IL 反汇编器（Stardew Valley 方法语义探查）

## 这是什么

一个**把游戏方法的 IL 打出来看**的小工具，用来回答"这个方法到底做了什么"，
替代"猜字段语义、猜调用时机"。

**来源**：复制自旧项目（只读引用，未修改原文件）
`C:\Users\admin\WorkBuddy\2026-10-04-20-36-38\stardew-auto-farm\tools\probes\Probe26\`
（原件仅 `Probe26.cs` + `Probe26.csproj`；本副本**已去掉 `bin/` 与 `obj/` 构建产物**）。

审计 `docs/_legacy-audit.md` §4.1 的评价：
> `Probe26` 的 **IL 反汇编器本体**是全项目最值得带走的技术资产（`Probe26.cs:23-100`，自建 opcode 表、用 `OpCode.OperandType` 推操作数长度）。它把"猜字段语义"换成了"读 IL"。新项目应把这类探针**常态化**（每次游戏更新跑一遍）。

---

## ⚠️ 首要警告：本工具在旧项目里**从未产出过落盘输出**

- 旧项目的 26 个探针中，**只有 Probe8/9/10/11/13 留下了输出**；`Probe26` **没有**。
- `Probe26.cs:25-30` 里那 6 个方法名是**代码里写死的字符串**，代表"作者认为存在"，
  **不代表"已验证存在"**。
- 因此 `docs/knowledge/legacy-api-1.6.15.md` 中一切依赖本工具验证的结论
  （尤其是 `isCollidingWithWarpOrDoor` 及其签名）**一律标为 `[未验证]`**。
- **你跑一次本工具并把输出入库，就能把这些结论升格。** 这正是它被复制过来的理由。

---

## 它当前会 dump 哪些方法

`Probe26.cs:25-30` 写死了 6 个目标，全部围绕"玩家踩到某格时会怎样被传送"：

| # | 类型 | 方法 | 想回答的问题 |
|---|---|---|---|
| 1 | `StardewValley.Pathfinding.PathFindController` | `handleWarps` | 寻路走到 warp 格时怎么处理 |
| 2 | `StardewValley.GameLocation` | `getWarpFromDoor` | 门 → warp 的真实映射 |
| 3 | `StardewValley.GameLocation` | `openDoor` | 开门做了什么 |
| 4 | `StardewValley.GameLocation` | `isCollidingWithWarpOrDoor` | **权威传送判定**的真身 |
| 5 | `StardewValley.GameLocation` | `isCollidingWithWarp` | 只判 warp 的版本 |
| 6 | `StardewValley.GameLocation` | `isCollidingWithDoors` | 只判 door 的版本 |

**要 dump 别的方法**：改 `Probe26.cs` 的 `Main`（第 25~30 行）里的 `Dump(...)` 调用即可。
`Dump` 会打印**同名方法的所有重载**（`Probe26.cs:78-83`），并用 `DescribeParams`
把每个重载的签名打出来（`:182-183`）。

---

## 为什么要它：三次"看起来合理"的错误结论

`Probe26.cs:7-13` 原文：

> 为什么需要它：猜字段语义、猜调用时机已经错了三次（每次都很像合理的结论）。
> 唯一可靠的办法是把相关方法的 IL 打出来看。
>
> operand 长度不手写，直接问 BCL：`OpCode.OperandType` → 字节数。
> 手写 opcode 表正是上一轮把静态/实例 `ldfld` 搞混的根源。

这条经验与 `docs/knowledge/legacy-design-patterns.md` §5.5（缺"地点拓扑"抽象，
用硬编码坐标兜底）是同一个病的两种表现。

---

## 用法

### 1. 准备

- .NET 6 SDK（`Probe26.csproj:4` 为 `net6.0`）
- 一个**能读到 `Stardew Valley.dll`** 的路径（游戏安装目录）

### 2. 构建并运行

```powershell
# 在 tools\il-probe 目录下
dotnet build -c Release

# 方式 A：传入游戏安装目录（推荐，不依赖当前工作目录）
dotnet run -c Release -- "C:\Program Files (x86)\Steam\steamapps\common\Stardew Valley"

# 方式 B：省略参数 —— 会退回 Probe26.cs:20 写死的默认路径
dotnet run -c Release
```

把输出**落盘入库**（这是本工具的产出物，必须一起提交）：

```powershell
dotnet run -c Release -- "<游戏目录>" | Out-File -Encoding utf8 probe26_out.txt
# 或直接跑编译好的 exe
.\bin\Release\Probe26.exe "<游戏目录>" | Out-File -Encoding utf8 probe26_out.txt
```

> ⚠️ `Probe26.cs:20` 的默认路径是**旧机器的硬编码路径**：
> `D:/Program Files (x86)/Steam/steamapps/common/Stardew Valley`。
> **强烈建议总是显式传参**，或按下面 §"建议的改造"把它改成从环境变量读。
> 这与 `tools/analyze_log.py`、`tools/parse_save.py` 的路径参数化口径一致 ——
> 旧项目硬编码 `MODS` 路径是审计点名的缺陷，新项目不再重复。

### 3. 阅读输出

- `IL_0000: ldarg.1 ...` —— 形如 `IL_<偏移>: <opcode 名> <操作数>`。
- 操作数会**尽量解析成可读文本**：方法/字段用 `Module.ResolveMethod/ResolveField`，
  类型用 `ResolveType(...).FullName`，字符串用 `ResolveString`，跳转用 `-> IL_xxxx`。
- 解析不了的会打 `tok 0x........` —— 这是**正常的**（不是工具坏了）。

---

## 实现要点（值得保留的工程细节）

1. **opcode 表从 BCL 生成，不手抄**（`Probe26.cs:33-43`）：遍历 `OpCodes` 的静态字段，
   用 `op.Size == 2 ? (0xFE00 | op.Value) : op.Value` 作键。
   **手写表正是旧项目把静态/实例 `ldfld` 搞混的根源。**
2. **操作数长度问 BCL，不手算**（`:45-72`）：`OperandSize` 按 `OpCode.OperandType` 返回
   字节数，含 `InlineSwitch` 的 `4 + 4*n`。
3. **无条件前进 n 字节**（`:166-173`，附原文注释）：
   > 一律前进 n 字节。绝不能"只对我列举的类型前进"—— 漏掉 `InlineType`
   >（`castclass` / `isinst` / `box`）会让整段反汇编错位，
   > 错位后打出来的"未知 opcode"完全是假象，反而更难查。
   
   这是一条**有代价学到的教训**，新项目若重写这个工具务必保留这个行为。
4. **找不到方法/取不到 IL 都软失败**（`:81`、`:88-89`）：打印 `(未找到 ...)` 或
   `(无方法体)` 后继续，不崩溃；便于一次性 dump 一组方法。

---

## ⚠️ 本工具自身的一个 bug（2026-10-11 已修，**旧结论必须重打**）

原版 `Dump` 的最后一行是：

```csharp
if (!string.IsNullOrEmpty(operand))
    Console.WriteLine($"  IL_{start:X4}: {op.Name,-14} {operand}");
```

`operand` 只在 switch 里列举的 `OperandType` 分支里被赋值，于是**所有没有操作数的指令**
（`ldarg.0/1`、`ldloc`、`stloc`、`ret`、`add`、`pop`、`br`… 即 `OperandType.InlineNone`）
**被静默丢掉了**。症状是 dump 里 IL 偏移**不连续**（例：`IL_0000` 直接跳到 `IL_0008`）。

**为什么危险**：`ret` 是**控制流**。看不见它，就会把"这里提前返回了"读成"顺序往下执行"，
于是"某方法里没有 `CanMove = false`""没有提前返回"这类**否定性结论全部不可信**。
本仓库早先关于 `Farmer.Halt()` / `PathFindController.update` 的阅读都是在带 bug 的版本上做的，
已在 2026-10-11 用修好的版本**重打并复核**（见 `docs\_il-farmer-halt.md`）。

现在无论 `operand` 是否为空都会打印（等价于"每个操作码都占一行"）。

## 已完成的改造（2026-10-11）

| 改造 | 状态 |
|---|---|
| 目标列表改为**从命令行读入** | ✅ `dotnet run -c Release -- "<游戏目录>" "Type\|Method" …`（不传则 dump 下面那 6 个默认目标） |
| dump **编译器生成的嵌套类型**（迭代器/lambda） | ✅ 写成 `Outer+NestedSubstring\|Method`，例如 `"StardewValley.SaveGame+getLoadEnumerator\|MoveNext"` |
| 方法名**按包含**匹配（dump lambda） | ✅ 方法名以 `*` 结尾即"包含匹配"，例如 `"StardewValley.SaveGame+DisplayClass101\|*"` |
| 默认路径改为读环境变量 | ✅ 顺序：命令行参数 > `STARDEW_GAME_DIR` > 旧机器硬编码路径 |
| 输出落盘 | ⚠️ 仍未内置；**约定**：结论写进 `docs\_il-*.md`（如 `_il-farmer-halt.md`、`_il-savegame-load.md`） |

**仍待改进**：`InlineR` / `InlineI8` 的操作数没有解码（浮点/长整型常量会打印成裸 opcode，
例如 `ldc.r8` 后面看不到 `64.0`）。不影响语义判断，但碰浮点常量时要知道这件事。

---

## 相关文档

- `docs/knowledge/legacy-api-1.6.15.md` §5.1 / §5.2 —— 依赖本工具验证的传送判定结论（当前 `[未验证]`）
- `docs/knowledge/legacy-design-patterns.md` §5.5 —— 为什么"猜语义"在这个项目里代价极高
- `docs/_legacy-audit.md` §4.1 —— 探针可信度分层与对本工具的评价
