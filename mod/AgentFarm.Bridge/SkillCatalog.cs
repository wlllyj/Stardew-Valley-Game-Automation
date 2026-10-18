using System;
using System.Collections.Generic;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-216 / 0.7.38 结构性护栏】技能名的**唯一权威表**（纯数据、零游戏类型依赖）。
    ///
    /// 为什么必须有这个文件：0.7.37 冻结点 `063351d` 的真机事故 —— `Skills.Create` 里已经加了
    /// `debug_dump` / `add_missed_recipes` / `upgrade_tool` / `pickup_tool` / `craft_item` /
    /// `place_object` / `machine` 的 case，但 `Skills.KnownSkills` 白名单没跟上；
    /// `BridgeHost.ServeExec` 在进主线程**之前**就按白名单把请求拒成 `unknown_skill`
    /// ⇒ `Create` 的 case 根本没机会跑，整条链路装机后全不可用（机器链/升级链/内省面全废）。
    ///
    /// 人工纪律"两边都要记得同步"已经失败过一次，所以这里改成**单一数据源**：
    ///
    ///   * `Skills.KnownSkills` 由 <see cref="Known"/> 派生（只加一次名）；
    ///   * `BridgeHost.IsLongTaskSkill` 由 <see cref="IsLongTask"/> 派生；
    ///   * `mod/AgentFarm.Bridge.Tests/Program.cs` 每次 build 都**读源码文本**校验：
    ///     `Skills.Create` 的每个 `case "..."` 字面量 ⇔ <see cref="Executable"/> 双向一致、
    ///     `BridgeHost.IsLongTaskSkill` 的每个 `skill == "..."` ⇔ <see cref="LongTask"/> 双向一致。
    ///     文本断言的理由同 `ClumpRules`/`TileListRules`/`AnswerRules`：这个自检工程不能引用
    ///     游戏程序集，吃 Stardew 类型的 `Skills.cs`/`BridgeHost.cs` 只能当源码看。
    ///
    /// 这个文件故意不引用任何 Stardew 类型，`Compile Include` 进自检工程后可直接跑行为断言。
    /// </summary>
    internal static class SkillCatalog
    {
        /// <summary>已实现、可直接执行的技能（`Skills.Create` 每个 case 必须在这里，反之亦然）。</summary>
        internal static readonly string[] Executable =
        {
            "noop", "move_to", "move_to_location", "load_save", "quit_game", "interact", "use_tool",
            "select_item", "plant", "sleep", "buy", "sell", "dismiss_modal",
            "upgrade_tool", "pickup_tool", "debug_dump", "add_missed_recipes",
            "craft_item", "place_object", "machine", "advance_dialogue",
            "talk",
        };

        /// <summary>
        /// 架构 §5.3 规划中：登记在案、`Create` 走 `not_implemented`（如实，不算未知技能）。
        /// 这条链只影响"未实现"文案，不影响可用性；新技能落地时把它从这里搬到 <see cref="Executable"/>。
        /// </summary>
        internal static readonly string[] Planned =
        {
            "exit_building", "harvest", "pickup_debris", "collect_machine", "refill_watering_can",
        };

        /// <summary>
        /// 可能跨多个 dispatcher tick 的技能（`MainThreadDispatcher.RunOne`：handler 返回 null
        /// = 本 tick 未完、下 tick 继续）。**判据是"要不要等外部状态"**，不是"重不重"：
        ///
        ///   * 要等：`upgrade_tool`（等 `ShopMenu` 挂上）、`dismiss_modal`（等存档菜单十几秒）、
        ///     `move_to*`/`load_save`/`use_tool`/`plant`/`sleep`/`buy`（游戏侧动画/过场/保存）、
        ///     `advance_dialogue`（等 safetyTimer 750/550ms 与事件 pause 的 3s 重试）。
        ///   * 不等（单 tick 必出终态）：`craft_item` / `place_object` / `machine` / `pickup_tool` /
        ///     `debug_dump` / `add_missed_recipes`。标成长任务没有收益，反而会白占"一次只允许
        ///     一件事"的槽位、把其它请求拒成 `busy`（`MainThreadDispatcher.cs` §1）。
        /// </summary>
        internal static readonly string[] LongTask =
        {
            "move_to", "move_to_location", "load_save", "use_tool", "plant", "sleep", "buy",
            "dismiss_modal", "upgrade_tool", "advance_dialogue",
        };

        private static readonly HashSet<string> KnownSet = BuildKnown();
        private static readonly HashSet<string> LongTaskSet =
            new HashSet<string>(LongTask, StringComparer.Ordinal);

        /// <summary>全部"认识"的技能名（已实现 + 规划中）。</summary>
        internal static IReadOnlyCollection<string> Known => KnownSet;

        internal static bool IsKnown(string skill) => skill != null && KnownSet.Contains(skill);

        internal static bool IsLongTask(string skill) => skill != null && LongTaskSet.Contains(skill);

        private static HashSet<string> BuildKnown()
        {
            var set = new HashSet<string>(StringComparer.Ordinal);
            foreach (string name in Executable) set.Add(name);
            foreach (string name in Planned) set.Add(name);
            return set;
        }
    }
}
