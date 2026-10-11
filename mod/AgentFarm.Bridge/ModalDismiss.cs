using System;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Menus;

namespace AgentFarm.Bridge
{
    /// <summary>dismiss_modal 的产出（与 ExecResponse 解耦，便于单测/阅读）。</summary>
    internal sealed class ModalDismissResult
    {
        public bool Ok;

        /// <summary>"ok" / "world_stuck" / "error"。</summary>
        public string Status = "ok";

        /// <summary>中文说明：关掉了什么、怎么关的、世界有没有恢复。</summary>
        public string Reason = "";

        /// <summary>
        /// 关掉模态之后**世界是否真的恢复可控**（`player.CanMove` 且 `Context.IsPlayerFree`）。
        ///
        /// 【为什么要有这个字段】事故教训：菜单关掉 ≠ 世界恢复。
        /// 真机上 dismiss_modal 报"已关闭对话框"，但随后时钟冻死、角色永久不能动。
        /// 只看"菜单没了"就会把这种永久停摆报成成功 —— 这是无人值守最怕的失败形态。
        /// </summary>
        public bool WorldResumed = true;
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
    /// ==================================================================
    /// 【事故记录（修复迭代 3）：禁止再用按键去“确认”选项】
    ///
    /// v2 的写法是 `selectedResponse = N` + `receiveKeyPress(Down/Enter/Space)` 去选 “No”。
    /// 真机复现：走到床边 → `Go to sleep for the night?` → dismiss_modal 返回
    /// “已关闭对话框（选“No”（按键确认未生效，已退回 exitThisMenu 关闭））”，
    /// 但此后**游戏永久卡死**：时钟停在 640、isModal=false、canMove=false、世界 45 秒以上不推进。
    ///
    /// 1.6.15 的 IL 实证（tools/il-probe 逐条核对）把这条链完整解释清楚了：
    ///   ① `Game1.drawObjectQuestionDialogue`（弹提问框的入口）里写着
    ///      `activeClickableMenu = new DialogueBox(...)`、`dialogueUp = true`、**`player.CanMove = false`**；
    ///   ② `DialogueBox.receiveKeyPress` 在提问时只识别「选项热键 / 'N'(78) / 'Y'(89) / Options.menuButton」，
    ///      **Enter(13) 与 Space(32) 在这里没有任何“应答”语义**：它们会先被 `Options.actionButton`
    ///      分支接走并转成 `receiveLeftClick(0, 0, true)` —— 那才是“确认当前选中项”的入口，
    ///      于是对话框进入 `transitioning` 中间态（菜单还在，所以按键路径自己都判断“没关掉”）；
    ///      （注：actionButton 默认是否含这两个键未逐字段核实，但**这条路径整体语义不可控**，
    ///        可能真的确认某个选项，所以整条删除。）
    ///   ③ 紧接着的兜底 `exitThisMenu()` 把菜单抽走，而 `DialogueBox.cleanupBeforeExit()` 是**空方法**：
    ///      `exitThisMenu()` **不复位 `Game1.dialogueUp`，也不复位 `Game1.player.CanMove`**
    ///      （干这两件事的是 `DialogueBox.closeDialogue()`）；
    ///   ④ `Game1.shouldTimePass()`：`if (!player.CanMove && !player.UsingTool) return player.forceTimePass;`
    ///      —— CanMove 停在 false ⇒ **时间永远不再推进**。
    ///    合起来就是真机看到的样子：没有模态、画面正常、角色不能动、时钟不走。
    ///    所以本次事故并不需要“真的按了 Yes”就能发生，**根因是关闭路径选错了 API**。
    ///
    /// 因此本轮定为硬规则（后人不要“优化”回去）：
    ///   * **永不注入确认键**（Down / Enter / Space 全部禁用，代码里已彻底删除该路径）；
    ///   * 应答提问走 `Game1.currentLocation.answerDialogueAction(...)`（见 BuildAnswerKey）；
    ///   * 关闭 DialogueBox 必须先走 `closeDialogue()`（复位 dialogueUp 与 CanMove），
    ///     仍在才退回 `exitThisMenu()`；
    ///   * 成功判据升级为“世界恢复”（CanMove && Context.IsPlayerFree），见 WorldResumed。
    /// ==================================================================
    ///
    /// 【合法性】以上全部等价于玩家按 Esc / 点“No”，不涉及任何特权操作。
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
                    return Finish(true, "ok", "当前没有打开的模态，无需关闭");
                }

                // ---- 情况 1：对话框（含提问）→ 应答 + 用 closeDialogue 关闭 ----
                if (menu is DialogueBox box)
                {
                    return DismissDialogue(box);
                }

                // ---- 情况 2：其它任何模态 → exitThisMenu()（等价按 Esc）----
                string text = UiRead.ActiveMenuText();
                try { menu.exitThisMenu(); } catch { }
                ClearDialogueFlag();

                return Finish(true, "ok",
                    $"已关闭模态（{menu.GetType().Name}）"
                    + (string.IsNullOrEmpty(text) ? "" : $"：“{text}”"));
            }
            catch (Exception ex)
            {
                return Finish(false, "error",
                    "关闭模态时异常：" + ex.GetType().Name + ": " + ex.Message);
            }
        }

        /// <summary>关闭一个 <see cref="DialogueBox"/>：提问先应答（永不选 Yes），再按状态正确的顺序关闭。</summary>
        private static ModalDismissResult DismissDialogue(DialogueBox box)
        {
            string question = null;
            try { question = box.getCurrentString(); } catch { }

            Response[] responses = null;
            try { responses = box.responses; } catch { }

            bool isQuestion = false;
            try { isQuestion = box.isQuestion; } catch { }

            string convention = "";
            string chosenText = "";
            string answerNote = "非提问对话框，无需应答";

            if (isQuestion && responses != null && responses.Length > 0)
            {
                int index = FindNegativeIndex(responses);
                if (index < 0)
                {
                    // 星露谷惯例：肯定在前、否定/取消在后。
                    index = responses.Length - 1;
                    convention = "；未找到明确的“否”选项，按星露谷惯例选择了最后一项";
                }

                Response chosen = responses[index];
                string key = chosen?.responseKey;
                if (string.IsNullOrEmpty(key)) key = chosen?.responseText;   // responseKey 为空时退回 responseText
                chosenText = chosen?.responseText ?? key ?? "";

                answerNote = AnswerWith(chosen);
            }
            else if (isQuestion)
            {
                answerNote = "提问对话框没有可读选项，直接关闭";
            }

            // ---- 关闭：先 closeDialogue()，仍在才退回 exitThisMenu() ----
            string closeNote = "";
            if (IsActiveDialogue(box))
            {
                try { box.closeDialogue(); } catch { }
                closeNote = "；closeDialogue() 关闭（复位 dialogueUp 与 player.CanMove）";
            }
            if (IsActiveDialogue(box))
            {
                try { box.exitThisMenu(); } catch { }
                ClearDialogueFlag();
                closeNote = "；closeDialogue() 未生效，已退回 exitThisMenu() 并复位 dialogueUp";
            }

            // 收尾：菜单已经没了，但 dialogueUp 还挂着残留标志 → 用唯一获准的那处状态写入兜住，
            // 否则后续所有 move_to 都会一直吃 ui_modal（假“有对话框”）。
            if (!IsActiveDialogue(box) && SafeBool(() => Game1.dialogueUp))
            {
                ClearDialogueFlag();
                closeNote += "；并复位残留的 dialogueUp";
            }

            string head = isQuestion
                ? $"已关闭对话框（选“{chosenText}”：{answerNote}{closeNote}）"
                : $"已关闭对话（{answerNote}{closeNote}）";

            return Finish(true, "ok", $"{head}：“{question}”{convention}");
        }

        /// <summary>
        /// 把“选中的那一项”交给游戏自己的应答入口。返回一句用于 reason 的说明。
        ///
        /// 【为什么绝不注入按键】键路径在 1.6.15 上语义不可控（见类注释的事故记录）：
        /// `receiveKeyPress` 对 Enter/Space 没有应答语义，而若该键命中 `Options.actionButton`，
        /// 会被转成 `receiveLeftClick(0,0,true)`＝“确认当前选中项”，后果不可预期。
        ///
        /// 【为什么优先 `answerDialogue(Response)` 而不是 `answerDialogueAction`】
        /// 前者才是**游戏自己**用的入口：它内部拼好组合键再转调 `answerDialogueAction`，
        /// 并且**会消费 `location.afterQuestion`** —— 即让游戏执行“回答之后本应发生的事”
        /// （例如把角色从床上移下来）。直接调 `answerDialogueAction` 会**跳过这段副作用**，
        /// 留下“答是答了，但状态没走完”的半成品。
        /// 因此顺序是：`answerDialogue(Response)` → 异常才退回 `answerDialogueAction(组合键)`。
        /// </summary>
        /// 【为什么是 internal】`SleepSkill`（睡觉 = 在 "go to sleep for the night?" 上答 Yes）
        /// 必须走**同一份**应答口径，绝不允许出现第二份实现 —— 这是本项目唯一一处"把选项交给游戏"的代码。
        internal static string AnswerWith(Response chosen)
        {
            GameLocation loc = null;
            try { loc = Game1.currentLocation; } catch { }
            if (loc == null) return "未能应答（当前地点为空）";
            if (chosen == null) return "未能应答（选项为空）";

            string label = chosen.responseKey ?? chosen.responseText ?? "";

            // 1) 游戏自身的应答入口（会消费 afterQuestion）
            try
            {
                loc.answerDialogue(chosen);
                return $"answerDialogue(\"{label}\")";
            }
            catch (Exception ex)
            {
                // 2) 回退：组合键路径（不消费 afterQuestion，但至少把“否”真正答上去）
                try
                {
                    string responseKey = chosen.responseKey;
                    if (string.IsNullOrEmpty(responseKey)) responseKey = chosen.responseText;
                    string answerKey = BuildAnswerKey(responseKey);
                    if (string.IsNullOrEmpty(answerKey))
                        return "应答异常且无法回退：" + ex.GetType().Name + ": " + ex.Message;

                    loc.answerDialogueAction(answerKey, null);
                    return $"answerDialogue 异常（{ex.GetType().Name}），已回退 answerDialogueAction(\"{answerKey}\")";
                }
                catch (Exception ex2)
                {
                    return "应答异常：" + ex2.GetType().Name + ": " + ex2.Message;
                }
            }
        }

        /// <summary>
        /// 拼出游戏自己的应答键。
        ///
        /// 【为什么不直接用裸 responseKey】IL 实证（1.6.15）：玩家点击选项或按选项热键时，
        /// 游戏走的是 `GameLocation.answerDialogue(Response)`，它把答案拼成
        /// **`lastQuestionKey 的第一段 + "_" + responseKey`**（例："Sleep_No"）才交给
        /// `answerDialogueAction`。也就是说 `answerDialogueAction` 收的是“组合键”，
        /// 裸传 "No" 在所有 `questionKey_xxx` 型对话框上都是空操作（本 Mod 要的是真正把“否”答上去）。
        /// 这里按同样的拼法组装（`SplitBySpace()[0]` 等价于取第一个空格前的一段）；
        /// `lastQuestionKey` 为空时退回裸 key，保持对非组合键对话框的兼容。
        /// </summary>
        private static string BuildAnswerKey(string responseKey)
        {
            if (string.IsNullOrEmpty(responseKey)) return null;

            string questionKey = null;
            try { questionKey = Game1.currentLocation?.lastQuestionKey; } catch { }

            if (string.IsNullOrEmpty(questionKey)) return responseKey;

            int space = questionKey.IndexOf(' ');
            string head = space >= 0 ? questionKey.Substring(0, space) : questionKey;
            if (string.IsNullOrEmpty(head)) return responseKey;

            return head + "_" + responseKey;
        }

        private static bool IsActiveDialogue(DialogueBox box)
        {
            try { return box != null && ReferenceEquals(Game1.activeClickableMenu, box); }
            catch { return false; }
        }

        /// <summary>
        /// 收尾判定：**成功判据是“世界恢复了”，不是“菜单关了”**。
        ///
        /// 在同一 tick 内读 `player.CanMove` 与 `Context.IsPlayerFree`：
        ///   * 两者都为 true → worldResumed=true，按普通成功返回；
        ///   * 否则 → 状态改判 `world_stuck`、`ok=false`，reason 里明确警告，
        ///     让“脑”能据此升级处理（重启游戏），绝不允许报成普通成功。
        /// </summary>
        private static ModalDismissResult Finish(bool ok, string status, string reason)
        {
            bool canMove = SafeBool(() => Game1.player != null && Game1.player.CanMove);
            bool playerFree = SafeBool(() => Context.IsPlayerFree);
            bool resumed = canMove && playerFree;

            if (!resumed && status == "ok")
            {
                return new ModalDismissResult
                {
                    Ok = false,
                    Status = "world_stuck",
                    WorldResumed = false,
                    Reason = reason
                        + "；警告：模态已关闭（或本就没有模态），但游戏仍处于不可控状态"
                        + $"（canMove={canMove}，isPlayerFree={playerFree}），世界没有恢复"
                        + "（CanMove=false 会让 shouldTimePass=false，时钟随之停止推进），需要外部恢复（建议重启游戏）",
                };
            }

            return new ModalDismissResult
            {
                Ok = ok,
                Status = status,
                WorldResumed = resumed,
                Reason = reason,
            };
        }

        /// <summary>
        /// 清掉"对话进行中"标志。
        ///
        /// 【为什么需要】`Game1.dialogueUp` 为 true 时 `Context.IsPlayerFree` 为 false，
        /// 后续所有 move_to 都会直接吃 `ui_modal`。正常路径由 `closeDialogue()` 自己复位；
        /// 只有走到 `exitThisMenu()` 这条兜底路（它不复位任何标志）时才由这里补一刀，
        /// 保证"菜单没了但谁也不能动"的僵局不会出现。
        ///
        /// 【豁免】这是**全项目唯一一处直接写游戏状态**，已获用户批准并在架构文档 §2 原则 7
        /// 的豁免清单里记录。不要删，也不要在这里新增别的写入。
        /// </summary>
        private static void ClearDialogueFlag()
        {
            try { Game1.dialogueUp = false; } catch { }
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

        private static bool SafeBool(Func<bool> f) { try { return f(); } catch { return false; } }
    }
}
