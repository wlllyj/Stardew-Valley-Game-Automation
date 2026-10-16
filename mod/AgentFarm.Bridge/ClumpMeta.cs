using System;
using System.Collections.Generic;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-155】`ResourceClump`（大障碍：树桩 / 大木头 / 巨石 / 石堆 / 绿雨那支）的**唯一权威**推导表。
    ///
    /// 依据 `docs/_il-tool-upgrade.md` §8/§9/§10/§11（真机 + IL 实证）与定稿设计
    /// `docs/_design-task155-clump-tool-metadata.md` §3：
    ///
    /// | `parentSheetIndex` | `clumpKind` | 工具      | 最低 `upgradeLevel` | 血量 |
    /// | ------------------ | ----------- | --------- | ------------------- | ---- |
    /// | 600                | `stump`     | axe       | 1                   | 10   |
    /// | 602                | `log`       | axe       | 2                   | 20   |
    /// | 672                | `boulder`   | pickaxe   | 2                   | 10   |
    /// | 148 / 622          | `rockPile`  | pickaxe   | 3                   | 20   |
    /// | &gt;= 752          | `greenRain` | pickaxe   | 0（**已证无门槛**） | 8    |
    /// | 其它 / 读不到       | `unknown`   | `null`    | `null`              | —    |
    ///
    /// 【铁律】未知索引 ⇒ 一律 `unknown` + `clumpTarget = null`：**绝不许**默认成斧头、也**绝不许**
    /// 默认成 0 级（那是凭空发明门槛）。`minLevel == 0`（已证无门槛）与 `null`（不知道）语义不同。
    ///
    /// 本类只回答"这一堆是什么、要什么工具、要几级"，**不做**任何行动决策：
    /// 等级够不够 ⇒ `WorldSnapshot` 算 `toolOk`；该不该挥 ⇒ task-20（脑侧）与 `UseToolSkill`。
    /// </summary>
    internal static class ClumpMeta
    {
        /// <summary>
        /// 可选的日志出口（由 `BridgeHost` 启动时设一次）。为 null 时只去重计数、不写日志
        /// （观测层是 static 方法，拿不到实例 monitor；这样既不污染契约也不丢诊断）。
        /// </summary>
        internal static Action<string> Warn { get; set; }

        /// <summary>已经 warn 过的 `clumpIndex`（`-1` 代表"读不到索引"）。按索引去重，避免每帧刷屏。</summary>
        private static readonly HashSet<int> WarnedIndexes = new HashSet<int>();

        /// <summary>`clumpKind`：`stump` / `log` / `boulder` / `rockPile` / `greenRain` / `unknown`。</summary>
        internal static string KindOf(int? index)
        {
            if (!index.HasValue)
            {
                return "unknown";
            }

            int i = index.Value;
            if (i == 600)
            {
                return "stump";
            }

            if (i == 602)
            {
                return "log";
            }

            if (i == 672)
            {
                return "boulder";
            }

            if (i == 148 || i == 622)
            {
                return "rockPile";
            }

            if (i >= 752)
            {
                return "greenRain";   // §7-U3：752 以上这一族的精确索引集合未定，先整族归类
            }

            return "unknown";
        }

        /// <summary>该用哪个工具（`axe` / `pickaxe`）；`null` = 判不了（**不许猜**）。</summary>
        internal static string ToolOf(int? index)
        {
            switch (KindOf(index))
            {
                case "stump":
                case "log":
                    return "axe";
                case "boulder":
                case "rockPile":
                case "greenRain":
                    return "pickaxe";
                default:
                    return null;
            }
        }

        /// <summary>最低 `upgradeLevel`；`0` = 已证无门槛，`null` = 不知道。</summary>
        internal static int? MinLevelOf(int? index)
        {
            switch (KindOf(index))
            {
                case "stump":
                    return 1;
                case "log":
                    return 2;
                case "boulder":
                    return 2;
                case "rockPile":
                    return 3;
                case "greenRain":
                    return 0;
                default:
                    return null;
            }
        }

        /// <summary>`clumpTarget` 视图；未知索引 ⇒ `null`（**不是** `minLevel=0`）。</summary>
        internal static ClumpTargetView TargetOf(int? index)
        {
            string tool = ToolOf(index);
            int? level = MinLevelOf(index);
            if (tool == null || !level.HasValue)
            {
                return null;
            }

            return new ClumpTargetView { Tool = tool, MinLevel = level };
        }

        /// <summary>
        /// 只用于 `<see cref="FarmView.ClumpsUnclassified"/>` 的分流判断：索引读不到或不在表里。
        /// </summary>
        internal static bool IsUnknown(int? index)
        {
            return KindOf(index) == "unknown";
        }

        /// <summary>遇到未知索引用一次 warn（按索引去重）。**绝不抛异常**（观测层不许因日志失败而挂）。</summary>
        internal static void NoteUnknown(int? index)
        {
            if (!IsUnknown(index))
            {
                return;
            }

            int key = index ?? -1;
            lock (WarnedIndexes)
            {
                if (!WarnedIndexes.Add(key))
                {
                    return;
                }
            }

            try
            {
                Warn?.Invoke(
                    "遇到未归类的 ResourceClump：parentSheetIndex="
                    + (index.HasValue ? index.Value.ToString() : "(读不到)")
                    + " ⇒ clumpKind=unknown、clumpTarget=null（不猜工具/等级；见 docs/_design-task155-clump-tool-metadata.md §3）。");
            }
            catch
            {
                // 日志失败绝不影响观测。
            }
        }
    }
}
