using System;
using System.Collections.Generic;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-240】种子季节判定的**纯函数**（零游戏类型依赖）。
    ///
    /// 背景（0.7.41 冒烟 day 1 的真实缺陷）：冬季 1 日、农场 0 作物、背包 Wheat Seeds×10。
    /// 脑侧（`brain/agentfarm/longrun.py`）**全仓零季节语义** —— 只要 `farm.emptyDirt > 0`
    /// 且背包里有种子，守卫就宣称「该去种」；而小麦在冬季不可种 ⇒ 目标池 0 格 ⇒ 守卫
    /// 永远抱怨 ⇒ 当天以 `stuck:` 报废（`plant_area requested_tiles=0`、`no_unmet_stages=false`）。
    /// 根因就是这里缺的那条事实：**"有种子" ≠ "当季能种"**。
    ///
    /// 为什么单独一个文件：仓库没有能引用游戏程序集的 C# 测试工程（见 `ClumpRules` /
    /// `TileListRules` 的同款说明），判据必须外置成纯逻辑，才能被
    /// `mod/AgentFarm.Bridge.Tests` 跑**行为**断言（而不是只盯源码文本）。
    ///
    /// 三态纪律（与 `CropMeta.Ready` 一致）：
    ///   * 判定不了 ⇒ **null**（`seasons` 缺失 / 空数组 / 当前季节读不到）——
    ///     绝不当 `false`（会把能种的判成不能种 = 该干活的时候不干），
    ///     也绝不当 `true`（会把不能种的判成能种 = 原 bug 复发）。
    /// </summary>
    internal static class SeedRules
    {
        /// <summary>游戏 `Season` 枚举的规范小写名字（下标即枚举值：春 0 / 夏 1 / 秋 2 / 冬 3）。</summary>
        public static readonly string[] SeasonNames = { "spring", "summer", "fall", "winter" };

        /// <summary>把任意大小写/空白的季节名归一；认不出 ⇒ `""`（空串 = 未知，不是"没有季节"）。</summary>
        public static string NormalizeSeason(string raw)
        {
            if (string.IsNullOrWhiteSpace(raw)) return "";
            string s = raw.Trim().ToLowerInvariant();
            for (int i = 0; i < SeasonNames.Length; i++)
            {
                if (SeasonNames[i] == s) return s;
            }
            return "";
        }

        /// <summary>
        /// 规范化的季节列表；`null` **原样返回 null**（= 读不到，判不了）——
        /// 空列表则返回空数组（= 读到但一个季节都没有，也判不了，调用方据此给 null）。
        /// 未知名字直接丢弃（不猜），避免把乱码当成季节。
        /// </summary>
        public static string[] NormalizeSeasons(IEnumerable<string> raw)
        {
            if (raw == null) return null;
            var list = new List<string>();
            foreach (string s in raw)
            {
                string n = NormalizeSeason(s);
                if (n.Length > 0 && !list.Contains(n)) list.Add(n);
            }
            return list.ToArray();
        }

        /// <summary>
        /// 这包种子**现在**能不能种：`true` 能 / `false` 不能 / `null` 判不了。
        ///
        /// `seasons == null`（读不到）或长度 0（没有季节信息）⇒ null；
        /// 当前季节认不出 ⇒ null；否则就看季节列表里有没有它。
        /// </summary>
        public static bool? PlantableNow(string[] seasons, string currentSeason)
        {
            if (seasons == null || seasons.Length == 0) return null;
            string cur = NormalizeSeason(currentSeason);
            if (cur.Length == 0) return null;
            for (int i = 0; i < seasons.Length; i++)
            {
                if (string.Equals(NormalizeSeason(seasons[i]), cur, StringComparison.Ordinal))
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>给回执/日志用的季节串：`"spring,summer,fall"`；判不了 ⇒ `""`。</summary>
        public static string DescribeSeasons(string[] seasons)
        {
            if (seasons == null || seasons.Length == 0) return "";
            return string.Join(",", seasons);
        }
    }
}
