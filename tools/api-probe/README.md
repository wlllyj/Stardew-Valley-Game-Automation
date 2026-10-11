# api-probe —— "这个 API 到底存不存在"的编译期探针

## 为什么需要它

实测教训（2026-10-11）：**`StardewModdingAPI.xml` 与 `StardewModdingAPI.dll` 不一致。**

- XML 第 128 行明确写着 `<member name="P:StardewModdingAPI.Constants.GameVersion">`
- 但引用了真实 DLL 的代码编译报 **CS0117：`Constants` 未包含 `GameVersion` 的定义**

→ **不要用 XML 文档、也不要凭记忆判断 API 是否存在。只有编译器算数。**

## 用法

1. 把要验证的代码写进 `Probe.cs`（哪怕只是 `_ = 某类型.某成员;`）
2. 构建：

```bat
cd /d "D:\Deepseek Harness Workspace\星露谷游戏自动化\tools\api-probe"
dotnet build -c Release
```

3. 读编译输出：

| 编译结果 | 含义 |
|---|---|
| **CS0117**「X 未包含 Y 的定义」 | **不存在**（成员名错、或被移除） |
| **CS0012**「类型在未引用的程序集中定义」 | **存在**，只是缺引用 → 按提示把程序集加进 `ApiProbe.csproj` |
| **CS1503 / CS1501**「参数不匹配 / 没有重载」 | 存在但**签名不同** → 这正是 `Crop.harvest` 那类坑 |
| 无错误 | 可用 |

游戏目录可用环境变量覆盖：`set STARDEW_GAME_PATH=E:\...\Stardew Valley`

## 已引用的程序集

`StardewModdingAPI` / `Stardew Valley` / `StardewValley.GameData` / `MonoGame.Framework` / `xTile`，
以及 `smapi-internal\` 下的 `SMAPI.Toolkit.CoreInterfaces`（`Constants.ApiVersion` 的返回类型在这）
与 `SMAPI.Toolkit`。

## 已固化的实测结论

| 结论 | 证据 |
|---|---|
| `Constants.GameVersion` **不存在** | CS0117；尽管 XML 里写着有 |
| `Constants.ApiVersion` **存在**（返回 `ISemanticVersion`） | 需要 `SMAPI.Toolkit.CoreInterfaces` 引用 |
| `Game1.weather` **不存在**（1.6.15 已移除） | CS0117；改用 `Game1.netWorldState.Value.LocationWeather` |
| `Game1.version` 可用，返回 `"1.6.15"` | 编译通过 |

> 与 `tools/il-probe/`（Probe26，IL 反汇编）的分工：
> **本工具回答"能不能编译"**（存在性与签名），**IL 探针回答"内部怎么实现"**（私有字段、字段名、运行时结构）。
