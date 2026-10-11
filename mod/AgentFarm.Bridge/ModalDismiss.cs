using System;
using StardewValley;
using StardewValley.Menus;

namespace AgentFarm.Bridge
{
    /// <summary>dismiss_modal 的产出（与 ExecResponse 解耦，便于单测/阅读）。</summary>
    internal sealed class ModalDismissResult
    {
        public bool Ok;

        /// <summary>"ok" 或 "error"。</summary>
        public string Status = "ok";

        /// <summary>中文说明：关掉了什么、怎么关的。</summary>
        public string Reason = "";
    }

    /// <summary>
    /// 把当前挡路的模态关掉 —— 无人值守场景的“救命技能”。
    ///
    /// 【真实场景】角色走到床边会弹 `go to sleep for the night?` + Yes/No，
    /// 此时**整个世界时间冻结**，后续任何计划都推不动。没有这个技能，无人值守会永久卡死。
    ///
    /// 【安全铁律：绝不选 Yes】
    /// 这个技能的存在目的是“解除阻塞”，不是“替人做决定”。因此：
    ///   * 只在 DialogueBox 且是提问时回答，且**只选否/取消/关闭**那一项；
    ///   * 找不到明确的“否”时，按星露谷惯例选**最后一项**，并在 reason 里如实说明；
    ///   * 其余任何模态一律走游戏的 `exitThisMenu()`（等价于玩家按 Esc）。
    ///
    /// 【为什么回答要走按键】1.6.15 的 `DialogueBox` 上**不存在** `receiveAction`
    /// （编译期探针证伪），`Response` 上也没有公开的 `responseCC`（拿不到每个选项的判定矩形），
    /// 所以“点坐标”这条路不可靠。可行的公开入口只有三个：
    ///   * `selectedResponse`（当前选中第几项，可写）
    ///   * `receiveKeyPress(Keys.X)`（键盘输入）
    ///   * `exitThisMenu()`（等价玩家按 Esc）
    /// 本类优先用“选中目标项 + 确认键”，并**验证对话框是否真的关掉了**，
    /// 没关掉才退回 `exitThisMenu()` —— 保证不会留下“以为关了其实没关”的假成功。
    ///
    /// 【合法性】以上全部等价于玩家按 Esc / 按 ↓ 选中 No 再按 Enter，不涉及任何特权操作。
    /// </summary>
    internal static class ModalDismiss
    {
        /// <summary>“否/取消/关闭”的文本特征（大小写不敏感；含中文）。</summary>
        private static readonly string[] NegativeTokens =
        {
            "no", "cancel", "close", "never", "否", "不", "取消",
        };

        /// <summary>主线程调用：关闭当前模态。绝不抛异常。</summary>
        public static ModalDismissResult Dismiss()
        {
            try
            {
                IClickableMenu menu = null;
                try { menu = Game1.activeClickableMenu; } catch { }

                // ---- 情况 3：没有模态 ----
                if (menu == null)
                {
                    return new ModalDismissResult
                    {
                        Ok = true,
                        Status = "ok",
                        Reason = "当前没有打开的模态，无需关闭",
                    };
                }

                // ---- 情况 1：对话框提问 → 永远选“否” ----
                if (menu is DialogueBox box)
                {
                    Response[] responses = null;
                    try { responses = box.responses; } catch { }

                    bool isQuestion = false;
                    try { isQuestion = box.isQuestion; } catch { }

                    if (isQuestion && responses != null && responses.Length > 0)
                        return AnswerNo(box, responses);
                }

                // ---- 情况 2：其它任何模态 → exitThisMenu()（等价按 Esc）----
                string text = UiRead.ActiveMenuText();
                menu.exitThisMenu();
                ClearDialogueFlag();

                return new ModalDismissResult
                {
                    Ok = true,
                    Status = "ok",
                    Reason = $"已关闭模态（{menu.GetType().Name}）"
                           + (string.IsNullOrEmpty(text) ? "" : $"：“{text}”"),
                };
            }
            catch (Exception ex)
            {
                return new ModalDismissResult
                {
                    Ok = false,
                    Status = "error",
                    Reason = "关闭模态时异常：" + ex.GetType().Name + ": " + ex.Message,
                };
            }
        }

        /// <summary>在提问对话框里选“否”。</summary>
        private static ModalDismissResult AnswerNo(DialogueBox box, Response[] responses)
        {
            string question = null;
            try { question = box.getCurrentString(); } catch { }

            int index = FindNegativeIndex(responses);
            string convention = "";
            if (index < 0)
            {
                // 星露谷惯例：肯定在前、否定/取消在后。
                index = responses.Length - 1;
                convention = "；未找到明确的“否”选项，按星露谷惯例选择了最后一项";
            }

            string chosen = responses[index]?.responseText ?? "";
            bool closed = ConfirmByKey(box, index);

            // 兜底：极少数情况下按键路径没关掉（例如该对话框不吃 Down/Enter），
            // 就直接走游戏的 exitThisMenu（等价玩家按 Esc）。
            // 无论走哪条路，目的都只是“关掉它”，绝不替玩家做肯定选择。
            string how = $"选“{chosen}”";
            if (!closed)
            {
                try { box.exitThisMenu(); } catch { }
                ClearDialogueFlag();
                how = $"选“{chosen}”（按键确认未生效，已退回 exitThisMenu 关闭）";
            }

            return new ModalDismissResult
            {
                Ok = true,
                Status = "ok",
                Reason = $"已关闭对话框（{how}）：“{question}”{convention}",
            };
        }

        /// <summary>
        /// 清掉"对话进行中"标志。
        ///
        /// 【为什么需要】`Game1.dialogueUp` 为 true 时 `Context.IsPlayerFree` 为 false，
        /// 后续所有 move_to 都会直接吃 `ui_modal`。如果走了 exitThisMenu 这条兜底路，
        /// 而游戏没来得及把标志复位，就会留下"菜单没了但谁也不能动"的僵局 —— 这正是
        /// 无人值守最怕的假成功。这里主动复位，保证关掉模态之后世界真的能继续。
        /// </summary>
        private static void ClearDialogueFlag()
        {
            try { Game1.dialogueUp = false; } catch { }
        }

        /// <summary>
        /// 用“键盘”确认选项（等价玩家按 ↓↓…Enter 选中某一项）。
        ///
        /// 【为什么不用鼠标点击】1.6.15 的 `Response` 上**没有**公开的 responseCC（已编译期证伪），
        /// 拿不到每个选项的判定矩形，算坐标点下去有“点空 / 点错项”的风险。
        /// 而 `receiveKeyPress` + `selectedResponse` 都是公开成员，且选项是按顺序排列的，
        /// 用 Down 逐项移动不可能越界（游戏内部会夹住序号）。
        ///
        /// 【安全方向】所有操作都只在“先选中目标项、再确认”这条路径上，
        /// 而目标项按铁律永远是“否/取消/关闭”，所以即使确认键语义与我预期不同，
        /// 也只会作用在否定项上，不会误触发 Yes。
        /// </summary>
        /// <returns>true = 确认后对话框确实关掉了。</returns>
        private static bool ConfirmByKey(DialogueBox box, int index)
        {
            try
            {
                // 1) 先清掉可能残留的旧选中项（-1 = 未选），再用 Down 逐项移动到目标项。
                //    起点未知，所以从“无选中”状态开始按 index+1 次，必然落在最后一项 index 上。
                try { box.selectedResponse = -1; } catch { }

                for (int i = 0; i <= index; i++)
                    box.receiveKeyPress(Microsoft.Xna.Framework.Input.Keys.Down);

                // 2) 兜底：直接把选中项设到目标（游戏中该字段就是“当前选中第几项”）。
                try { box.selectedResponse = index; } catch { }

                // 3) 确认。Enter 与 Space 都发一次：两个键都不会被用来“取消/返回”。
                box.receiveKeyPress(Microsoft.Xna.Framework.Input.Keys.Enter);
                box.receiveKeyPress(Microsoft.Xna.Framework.Input.Keys.Space);
            }
            catch { return false; }

            try
            {
                if (Game1.activeClickableMenu == null) return true;
                return !(Game1.activeClickableMenu is DialogueBox);
            }
            catch { return false; }
        }

        /// <summary>
        /// 找出“否/取消/关闭”那一项的序号；找不到返回 -1。
        /// 先看 responseKey（程序化 ID，最可靠），再看 responseText（给玩家看的文字）。
        /// 从后往前扫：星露谷惯例是否定项在后，倒序能优先命中真正的“否”。
        /// </summary>
        private static int FindNegativeIndex(Response[] responses)
        {
            for (int pass = 0; pass < 2; pass++)
            {
                for (int i = responses.Length - 1; i >= 0; i--)
                {
                    Response r = responses[i];
                    if (r == null) continue;

                    string key = pass == 0 ? r.responseKey : null;
                    string text = pass == 0 ? null : r.responseText;

                    if (MatchesNegative(key) || MatchesNegative(text)) return i;
                }
            }
            return -1;
        }

        private static bool MatchesNegative(string s)
        {
            if (string.IsNullOrEmpty(s)) return false;

            string lower = s.ToLowerInvariant();
            foreach (string token in NegativeTokens)
            {
                // 注意：这里用“包含”而不是“相等”，因为实际文本形如 "No" / "No, thanks" /
                // "Cancel" / "Never mind"。只把 "no" 当子串会出现误判风险（例如 "Nothing"），
                // 但那是**偏向否定**的误判，符合本技能“宁可少做、绝不多做”的安全取向。
                if (lower.Contains(token)) return true;
            }
            return false;
        }
    }
}
