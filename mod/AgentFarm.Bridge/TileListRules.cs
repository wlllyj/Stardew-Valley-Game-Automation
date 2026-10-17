using System;
using System.Collections.Generic;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-199】坐标列表发布规则（**纯函数、零游戏类型依赖**）：排序 + 上限截断。
    ///
    /// 为什么单独成文件（与 `ClumpRules` 同一套理由）
    ///   `FarmScan` 吃 `Game1`/`Farm`/`TerrainFeature`，仓库里没有能引用游戏程序集的测试工程
    ///   ⇒ "排序/截断/截断标志"这类**行为**只能在源码文本层面断言，变异体逃得掉。
    ///   把这段纯逻辑抽到这里，`mod/AgentFarm.Bridge.Tests`（零依赖控制台自检）可以直接
    ///   `Compile Include="..\AgentFarm.Bridge\TileListRules.cs"` 跑真行为断言。
    ///
    /// 口径（卡面 task-50 / task-199 一致）
    ///   * 排序：先 `y` 再 `x`（升序、确定性）；坐标是 `[x, y]` 两元数组（与协议 `dryTiles`/`readyTiles` 同形）。
    ///   * 截断：超过 `max` 条只保留前 `max` 条并置 `truncated = true`（**调用方的计数不受影响**：
    ///     计数是全场真值，坐标只是"够得着的一小部分"）。
    ///   * 不确定就说不确定：`source` 为 null 或任何异常 ⇒ 返回空数组 + `truncated = true`，
    ///     **绝不**把"没算出来"发布成"没有坐标"。
    /// </summary>
    internal static class TileListRules
    {
        /// <summary>
        /// 把 <paramref name="source"/> 排序 + 截断成可发布的坐标数组。
        /// </summary>
        /// <param name="source">本轮扫到的原始坐标（`[x, y]`；允许 null）。</param>
        /// <param name="max">坐标条数上限（&lt;= 0 视为"只要一个都不给"）。</param>
        /// <param name="tiles">排序 + 截断后的数组（异常/空 ⇒ 空数组）。</param>
        /// <param name="truncated">是否被截断（异常 ⇒ true）。</param>
        public static void OrderAndTruncate(List<int[]> source, int max,
                                            out int[][] tiles, out bool truncated)
        {
            try
            {
                truncated = false;
                if (source == null)
                {
                    // "没拿到扫描结果" ≠ "没有坐标"：置 truncated，调用方据此判"不确定"。
                    tiles = new int[0][];
                    truncated = true;
                    return;
                }

                var ordered = new List<int[]>();
                foreach (int[] item in source)
                {
                    if (item == null || item.Length < 2) continue;
                    ordered.Add(item);
                }

                int[] indices = OrderAndTruncateIndices(ordered, max, out truncated);
                var result = new int[indices.Length][];
                for (int i = 0; i < indices.Length; i++) result[i] = ordered[indices[i]];
                tiles = result;
            }
            catch
            {
                tiles = new int[0][];
                truncated = true;
            }
        }

        /// <summary>
        /// 【task-210】**按同样的 (y, x) 排序 + 上限截断**，但返回的是"原列表下标"。
        ///
        /// 为什么需要：`location.objects` 的逐条清单不是纯坐标，每行还带机器状态
        /// （`objId`/`heldObject`/`readyForHarvest`/`minutesUntilReady`）。
        /// 为了不让"排序 + 截断"这段判据出现第二份实现（两份必然漂移），
        /// 这里只算**下标顺序**，调用方照下标取自己的行对象。
        ///
        /// 口径与 <see cref="OrderAndTruncate"/> 完全一致：先 y 再 x；`max &lt;= 0` ⇒ 一条不给、
        /// `truncated = 条目数 &gt; 0`；`source == null` / 异常 ⇒ 空 + `truncated = true`
        /// （"没拿到" ≠ "没有"）；残缺条目（null / 长度 &lt; 2）跳过（其下标不会出现）。
        /// </summary>
        public static int[] OrderAndTruncateIndices(List<int[]> source, int max, out bool truncated)
        {
            try
            {
                truncated = false;
                if (source == null)
                {
                    truncated = true;
                    return new int[0];
                }

                var pairs = new List<KeyValuePair<int, int[]>>();
                for (int i = 0; i < source.Count; i++)
                {
                    int[] item = source[i];
                    if (item == null || item.Length < 2) continue;
                    pairs.Add(new KeyValuePair<int, int[]>(i, item));
                }

                pairs.Sort((a, b) => a.Value[1] != b.Value[1]
                    ? a.Value[1] - b.Value[1]
                    : a.Value[0] - b.Value[0]);

                if (max <= 0)
                {
                    truncated = pairs.Count > 0;
                    return new int[0];
                }

                if (pairs.Count > max)
                {
                    truncated = true;
                    pairs = pairs.GetRange(0, max);
                }

                var result = new int[pairs.Count];
                for (int i = 0; i < pairs.Count; i++) result[i] = pairs[i].Key;
                return result;
            }
            catch
            {
                truncated = true;
                return new int[0];
            }
        }
    }
}
