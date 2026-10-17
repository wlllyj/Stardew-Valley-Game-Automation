using System;
using System.Collections.Generic;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-208】`dismiss_modal` 的**显式应答**选择规则（纯函数、零游戏类型依赖）。
    ///
    /// 【为什么外置成纯函数】仓库里没有能引用游戏程序集的 C# 测试工程：
    /// `mod\AgentFarm.Bridge.Tests` 是零依赖控制台自检（`Compile Include` 只收纯逻辑文件）。
    /// 所以凡是**判据**，必须放在不 `using StardewValley` 的文件里才能跑行为断言
    /// （同一纪律见 <c>ClumpRules</c> / <c>TileListRules</c>）。
    ///
    /// 【为什么需要它】铁匠铺升级要走「选 Upgrade → 选工具 → 确认」的对话选择，
    /// 而旧的 `dismiss_modal` 只会自己挑「否/最后一项」。脑侧必须能指定"选第几个/选哪一句"，
    /// 且**指错了必须失败**——绝不允许悄悄退回自动挑 Yes（那等于替人做了不可逆决定）。
    ///
    /// 语义（与卡面逐字对齐）：
    ///   * 两个参数都不给 ⇒ <see cref="StatusAuto"/>：调用方**保持旧行为**（自动挑否/最后一项）；
    ///   * `answerIndex`：0 基下标，对应 `ui.dialogueResponses[]` 的顺序；
    ///   * `answerText`：大小写不敏感子串匹配，**唯一命中**才算成功；
    ///   * 找不到 ⇒ <see cref="StatusNotFound"/>；多命中/两个参数同时给 ⇒ <see cref="StatusAmbiguous"/>；
    ///   * 没有可选项 ⇒ <see cref="StatusNoQuestion"/>。
    /// </summary>
    internal static class AnswerRules
    {
        /// <summary>没给显式应答 ⇒ 调用方沿用旧行为（自动挑否/最后一项）。</summary>
        public const string StatusAuto = "auto";

        /// <summary>唯一命中：<see cref="AnswerPick.Index"/> 可用。</summary>
        public const string StatusFound = "found";

        /// <summary>指定了应答但当前没有提问框 / 没有可选项。</summary>
        public const string StatusNoQuestion = "no_question";

        /// <summary>指定了应答但没有任何一项命中（**不许**退回自动挑）。</summary>
        public const string StatusNotFound = "choice_not_found";

        /// <summary>多命中，或同时给了 index 与 text（互斥）——拒绝替人猜。</summary>
        public const string StatusAmbiguous = "choice_ambiguous";

        /// <summary><see cref="Pick"/> 的产出：下标（-1 = 没得选）、状态、给 reason 的说明。</summary>
        internal struct AnswerPick
        {
            public int Index;
            public string Status;
            public string Note;
        }

        /// <summary>把可选项渲染成「0=是 / 1=否」形式（失败 reason 里必须列出，便于取证）。</summary>
        public static string DescribeOptions(string[] texts, string[] keys)
        {
            if (texts == null || texts.Length == 0) return "（当前提问没有可选项）";
            var parts = new List<string>();
            for (int i = 0; i < texts.Length; i++)
            {
                string text = i < texts.Length ? texts[i] : null;
                string key = keys != null && i < keys.Length ? keys[i] : null;
                string label = !string.IsNullOrEmpty(text) ? text : (key ?? "");
                parts.Add(i + "=" + Quote(label));
            }
            return string.Join(" / ", parts);
        }

        /// <summary>把请求渲染成一句人读的说明（失败 reason 用）。</summary>
        public static string DescribeRequest(int? answerIndex, string answerText)
        {
            if (answerIndex.HasValue && !string.IsNullOrWhiteSpace(answerText))
                return "answerIndex=" + answerIndex.Value + " 且 answerText=" + Quote(answerText) + "（互斥）";
            if (answerIndex.HasValue) return "answerIndex=" + answerIndex.Value;
            if (!string.IsNullOrWhiteSpace(answerText)) return "answerText=" + Quote(answerText);
            return "（未指定，自动挑否）";
        }

        /// <summary>
        /// 选出要应答的选项。
        ///
        /// 返回 <see cref="AnswerPick.Status"/>：
        ///   * <see cref="StatusAuto"/> —— 两个参数都没给，调用方走旧逻辑（自动挑否/最后一项）；
        ///   * <see cref="StatusFound"/> —— <see cref="AnswerPick.Index"/> 是唯一命中的下标；
        ///   * <see cref="StatusNoQuestion"/> —— 目标对话没有可选项；
        ///   * <see cref="StatusNotFound"/> —— 没命中（Note 里带可选项原文）；
        ///   * <see cref="StatusAmbiguous"/> —— 多命中或参数互斥（Note 里列出命中项）。
        /// </summary>
        public static AnswerPick Pick(int? answerIndex, string answerText,
                                      string[] responseTexts, string[] responseKeys)
        {
            bool hasIndex = answerIndex.HasValue;
            bool hasText = !string.IsNullOrWhiteSpace(answerText);

            if (!hasIndex && !hasText)
                return new AnswerPick { Index = -1, Status = StatusAuto, Note = "" };

            int count = responseTexts?.Length ?? 0;
            if (count <= 0)
            {
                return new AnswerPick
                {
                    Index = -1,
                    Status = StatusNoQuestion,
                    Note = "当前对话没有可选项（responses 为空）",
                };
            }

            if (hasIndex && hasText)
            {
                return new AnswerPick
                {
                    Index = -1,
                    Status = StatusAmbiguous,
                    Note = "answerIndex 与 answerText 只能给一个（互斥），拒绝替人猜；可选项："
                           + DescribeOptions(responseTexts, responseKeys),
                };
            }

            if (hasIndex)
            {
                int idx = answerIndex.Value;
                if (idx >= 0 && idx < count)
                    return new AnswerPick { Index = idx, Status = StatusFound, Note = "下标命中" };
                return new AnswerPick
                {
                    Index = -1,
                    Status = StatusNotFound,
                    Note = "answerIndex=" + idx + " 越界（可选项共 " + count + " 项）；可选项："
                           + DescribeOptions(responseTexts, responseKeys),
                };
            }

            string needle = answerText.Trim();
            var hits = new List<int>();
            for (int i = 0; i < count; i++)
            {
                string text = responseTexts[i];
                string key = responseKeys != null && i < responseKeys.Length ? responseKeys[i] : null;
                if (ContainsIgnoreCase(text, needle) || ContainsIgnoreCase(key, needle))
                    hits.Add(i);
            }

            if (hits.Count == 0)
            {
                return new AnswerPick
                {
                    Index = -1,
                    Status = StatusNotFound,
                    Note = "answerText=" + Quote(needle) + " 没有任何命中；可选项："
                           + DescribeOptions(responseTexts, responseKeys),
                };
            }

            if (hits.Count > 1)
            {
                var names = new List<string>();
                foreach (int i in hits)
                {
                    string text = i < responseTexts.Length ? responseTexts[i] : null;
                    string key = responseKeys != null && i < responseKeys.Length ? responseKeys[i] : null;
                    names.Add(i + "=" + Quote(!string.IsNullOrEmpty(text) ? text : (key ?? "")));
                }
                return new AnswerPick
                {
                    Index = -1,
                    Status = StatusAmbiguous,
                    Note = "answerText=" + Quote(needle) + " 命中 " + hits.Count + " 项（" +
                           string.Join(" / ", names) + "）⇒ 歧义，拒绝替人猜",
                };
            }

            return new AnswerPick { Index = hits[0], Status = StatusFound, Note = "文本唯一命中" };
        }

        private static bool ContainsIgnoreCase(string haystack, string needle)
        {
            if (string.IsNullOrEmpty(haystack) || string.IsNullOrEmpty(needle)) return false;
            return haystack.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static string Quote(string text) => "「" + (text ?? "") + "」";
    }
}
