using System;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-33】`talk` 原语的**纯规则**（零游戏类型依赖，自检工程直接编译这份源码跑行为断言）。
    ///
    /// 为什么拆出来：判据如果留在吃 `NPC`/`Game1` 类型的 `TalkSkill` 里，自检工程就只能做
    /// 源码文本断言（task-182 的 GAP-1 教训：文本断言逃逸了行为变异）。这里的三件事都是纯逻辑：
    ///
    ///   ① 名字匹配（大小写不敏感、trim；显示名与内部名都算命中）；
    ///   ② 相邻判定（切比雪夫距离 ≤1 —— 与游戏 `NPC.withinPlayerThreshold(1)` 同口径）；
    ///   ③ 回执分类（`code` 的 fail-closed 顺序 + 「applied 必须带 UI 证据」的形状校验）。
    ///
    /// 【红线条（契约 §8.4）】`talk` 只调游戏自己的 `NPC.checkAction(Farmer, GameLocation)`：
    /// 不改 Money/Items/MaxItems、不调 `increaseBackpackSize`、不合成键鼠。
    /// 所以这里也**没有**任何写钱包/背包的入口，只有"读事实 + 判定"。
    /// </summary>
    internal static class TalkRules
    {
        internal const string CodeOk = "ok";
        internal const string CodeNpcNotFound = "npc_not_found";
        internal const string CodeNotAdjacent = "not_adjacent";
        internal const string CodeNoAction = "no_action";
        internal const string CodeNotSupported = "not_supported";

        /// <summary>名字归一：null ⇒ 空串，去首尾空白（匹配前两边都走这里）。</summary>
        internal static string Normalize(string name)
        {
            return name == null ? "" : name.Trim();
        }

        /// <summary>
        /// 名字是否命中 NPC（大小写不敏感；内部名与显示名任一相等即算）。
        /// 空查询 ⇒ false（fail-closed：不拿"空名字"去猜最近的人）。
        /// </summary>
        internal static bool NameMatches(string want, string name, string displayName)
        {
            string q = Normalize(want);
            if (q.Length == 0) return false;
            return string.Equals(q, Normalize(name), StringComparison.OrdinalIgnoreCase)
                || string.Equals(q, Normalize(displayName), StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>切比雪夫距离（八方向相邻都算 1）。</summary>
        internal static int ChebyshevDistance(int dx, int dy)
        {
            return Math.Max(Math.Abs(dx), Math.Abs(dy));
        }

        /// <summary>相邻判定：切比雪夫距离 ≤1 ⇒ 玩家能直接对 NPC 调 checkAction。</summary>
        internal static bool IsAdjacent(int dx, int dy)
        {
            return ChebyshevDistance(dx, dy) <= 1;
        }

        /// <summary>
        /// 回执形状：`applied==true` 时**必须**至少有一项 UI 证据（activeMenu 或提问），
        /// 否则就是实现缺陷（契约 §8.4 判红）。这里返回 false 表示"不可信"。
        /// </summary>
        internal static bool HasDialogueEvidence(bool applied, string activeMenu, bool dialogueIsQuestion)
        {
            if (!applied) return false;
            return !string.IsNullOrEmpty(activeMenu) || dialogueIsQuestion;
        }

        /// <summary>
        /// 回执 `code` 的 fail-closed 分类（顺序即优先级）：
        ///   找不到 NPC ⇒ `npc_not_found`；不相邻 ⇒ `not_adjacent`；游戏没认领 ⇒ `no_action`；
        ///   认领了但没有任何 UI 证据 ⇒ `not_supported`（实现缺陷，不当成功）；其余 ⇒ `ok`。
        /// </summary>
        internal static string DecideCode(bool found, bool adjacent, bool applied,
                                         string activeMenu, bool dialogueIsQuestion)
        {
            if (!found) return CodeNpcNotFound;
            if (!adjacent) return CodeNotAdjacent;
            if (!applied) return CodeNoAction;
            return HasDialogueEvidence(applied, activeMenu, dialogueIsQuestion)
                ? CodeOk
                : CodeNotSupported;
        }

        /// <summary>`code=="ok"` 是否成立（= 分类结果与形状校验同时通过）。</summary>
        internal static bool IsOkCode(string code)
        {
            return string.Equals(code, CodeOk, StringComparison.Ordinal);
        }
    }
}
