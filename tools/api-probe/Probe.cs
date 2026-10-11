using System;
using StardewModdingAPI;
using StardewValley;

namespace ApiProbe
{
    /// <summary>
    /// API 存在性探针。**把你要问的问题写成代码，然后编译。**
    ///
    /// 编译器报 CS0117（未包含该定义）= 不存在；
    /// 报 CS0012（类型在未引用的程序集中）= 存在，只是缺引用（往 csproj 里加）；
    /// 什么都不报 = 可用。
    ///
    /// 下面保留的是 2026-10-11 实测过的样例，可留作对照，也可整段替换。
    /// </summary>
    public static class Probe
    {
        // ---- 实测结论：不存在（CS0117）------------------------------------
        // StardewModdingAPI.xml 第 128 行声称有它，但 DLL 里没有。
        // 教训：XML 文档与 DLL 可能不一致，只有编译器算数。
        // public static object 已证伪_Constants_GameVersion() => Constants.GameVersion;

        // 1.6.15 已移除：天气改从 netWorldState.Value.LocationWeather 取。
        // public static object 已证伪_Game1_weather() => Game1.weather;

        // ---- 实测结论：存在 -------------------------------------------------
        /// <summary>SMAPI 版本（返回 ISemanticVersion，需要 SMAPI.Toolkit.CoreInterfaces 引用）。</summary>
        public static string SmapiApiVersion() => Constants.ApiVersion.ToString();

        /// <summary>游戏版本字符串，例如 "1.6.15"。</summary>
        public static string GameVersion() => Game1.version;

        /// <summary>SMAPI 最低支持的游戏版本。</summary>
        public static string MinimumGameVersion() => Constants.MinimumGameVersion?.ToString() ?? "";

        /// <summary>世界状态（1.6 的天气/日期等权威来源）。</summary>
        public static object NetWorldState() => Game1.netWorldState;

        /// <summary>存档路径，用于定位 bridge.json 之类的同伴文件。</summary>
        public static string DataPath() => Constants.DataPath;
    }
}
