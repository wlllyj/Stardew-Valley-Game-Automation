using System;
using System.Reflection;
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

        /// <summary>
        /// 【task-208】实际选中项的文本（审计用；没有选中任何选项时为 null）。
        /// 旧行为（自动挑否）也会填；fail-closed 的失败路径不填。
        /// </summary>
        public string ChosenAnswer;
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
    ///   * 其余任何模态一律走游戏的 `exitThisMenu()`（等价于玩家按 Esc）——
    ///     **但 `ShippingMenu`／`SaveGameMenu`／`NewDaySavingMenu` 是硬例外**（task-129）：
    ///     这三类由 `ShippingMenuDismissSkill` 跨 tick 接管，本类**拒关**（见 `Dismiss()` 情况 2a）。
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

        /// <summary>主线程调用：关闭当前模态（**旧行为**：提问时自动挑否/最后一项）。绝不抛异常。</summary>
        public static ModalDismissResult Dismiss()
        {
            return Dismiss(null, null);
        }

        /// <summary>
        /// 主线程调用：关闭当前模态；给了 <paramref name="answerIndex"/> 或
        /// <paramref name="answerText"/> 时**按显式应答**（task-208）。
        ///
        /// 【语义】两个参数都不给 ⇒ 与 <see cref="Dismiss()"/> 逐字相同（自动挑否/最后一项）。
        /// 给了 ⇒ 只在「当前是提问对话框且有可选项」时生效；否则 fail-closed：
        /// `no_question` / `choice_not_found` / `choice_ambiguous` 都会如实失败，
        /// **绝不**退回自动挑 Yes（铁匠铺升级、职业选择这类不可逆决定不允许猜）。
        /// </summary>
        public static ModalDismissResult Dismiss(int? answerIndex, string answerText)
        {
            bool explicitChoice = answerIndex.HasValue || !string.IsNullOrWhiteSpace(answerText);
            try
            {
                IClickableMenu menu = null;
                try { menu = Game1.activeClickableMenu; } catch { }

                // ---- 显式应答（task-208）----
                // 前置判据先做完：没有模态 / 不是对话 ⇒ no_question（不去碰别的模态）。
                if (explicitChoice)
                {
                    string request = AnswerRules.DescribeRequest(answerIndex, answerText);
                    if (menu == null)
                    {
                        return Finish(false, AnswerRules.StatusNoQuestion,
                            $"指定了对话应答（{request}），但当前没有打开的模态 ⇒ 不猜、不退回自动挑 Yes");
                    }
                    if (!(menu is DialogueBox dlg))
                    {
                        return Finish(false, AnswerRules.StatusNoQuestion,
                            $"指定了对话应答（{request}），但当前模态是 {menu.GetType().Name}（不是提问对话框）"
                            + " ⇒ 不猜、不退回自动挑 Yes");
                    }
                    return DismissDialogueExplicit(dlg, answerIndex, answerText);
                }

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

                // ---- 情况 2a：出货菜单 / 存档菜单 → **绝不 exitThisMenu()**（task-129）----
                //
                // 【为什么必须拒】出货日的日切保存唯一入口在 `ShippingMenu.update()` 内部：
                // 只有私有字段 `outro == true`（= 玩家点 OK ⇒ 私有 `okClicked()`）之后才会
                // `new SaveGameMenu()` ⇒ `SaveGame.Save()`。这里一句 `exitThisMenu()` 会让
                // `outro` 永远为 false ⇒ **永不出存档菜单**；而 `Game1._update` 只要求
                // “夜菜单栈空 + 无活动菜单”就推进到早晨 ⇒ 日推进、盘不落、无人拦
                // （run9 实测 4 NewDay / 0 save，整跑作废）。
                // 所以这两类一律交给 `ShippingMenuDismissSkill`（跨 tick：反射 okClicked() 或
                // 点 okButton，然后只等游戏自己关）。
                if (menu is ShippingMenu || IsSaveMenu(menu))
                {
                    return Finish(false, "wait_only",
                        $"拒绝关闭 {menu.GetType().Name}：出货菜单的日切保存入口在它自己内部"
                        + "（只有点 OK 才会建 SaveGameMenu），存档菜单正把盘写出去 —— 这两类必须走"
                        + " dismiss_modal 的跨 tick wait-only 路径（task-129）");
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

            string closeNote = CloseDialogueBox(box);

            string head = isQuestion
                ? $"已关闭对话框（选“{chosenText}”：{answerNote}{closeNote}）"
                : $"已关闭对话（{answerNote}{closeNote}）";

            ModalDismissResult auto = Finish(true, "ok", $"{head}：“{question}”{convention}");
            // 【task-208】审计字段：旧行为也如实报出"实际选了哪一项"（非提问时为空）。
            auto.ChosenAnswer = string.IsNullOrEmpty(chosenText) ? null : chosenText;
            return auto;
        }

        /// <summary>
        /// 【task-208】按**显式应答**关掉一个提问对话框：命中后仍只走游戏自己的
        /// `answerDialogue(Response)`（`AnswerWith`），然后按状态正确的顺序关框。
        ///
        /// 【fail-closed】指定了却对不上（没有可选项 / 找不到 / 多命中）⇒ 如实失败，
        /// **绝不**退回 `DismissDialogue` 的"自动挑否"——那是替人做决定。
        /// </summary>
        private static ModalDismissResult DismissDialogueExplicit(
            DialogueBox box, int? answerIndex, string answerText)
        {
            string question = null;
            try { question = box.getCurrentString(); } catch { }

            Response[] responses = null;
            try { responses = box.responses; } catch { }

            bool isQuestion = false;
            try { isQuestion = box.isQuestion; } catch { }

            string request = AnswerRules.DescribeRequest(answerIndex, answerText);

            if (!isQuestion || responses == null || responses.Length == 0)
            {
                return Finish(false, AnswerRules.StatusNoQuestion,
                    $"指定了对话应答（{request}），但当前对话框不是提问/没有可选项"
                    + $"（isQuestion={isQuestion}，responses={(responses == null ? 0 : responses.Length)}）"
                    + " ⇒ 不猜、不退回自动挑 Yes");
            }

            var texts = new string[responses.Length];
            var keys = new string[responses.Length];
            for (int i = 0; i < responses.Length; i++)
            {
                Response item = responses[i];
                try { texts[i] = item?.responseText; } catch { texts[i] = null; }
                try { keys[i] = item?.responseKey; } catch { keys[i] = null; }
            }

            AnswerRules.AnswerPick pick = AnswerRules.Pick(answerIndex, answerText, texts, keys);

            if (pick.Status != AnswerRules.StatusFound)
            {
                string status = pick.Status == AnswerRules.StatusNoQuestion
                    ? AnswerRules.StatusNoQuestion
                    : pick.Status;
                return Finish(false, status,
                    $"显式应答失败（{request}）：{pick.Note}；对话框原文：“{question}”"
                    + " ⇒ 不猜、不退回自动挑 Yes");
            }

            Response chosen = responses[pick.Index];
            string chosenText = texts[pick.Index] ?? keys[pick.Index] ?? "";
            if (string.IsNullOrEmpty(chosenText)) chosenText = chosen?.responseKey ?? "";

            string answerNote = AnswerWith(chosen);
            string closeNote = CloseDialogueBox(box);

            ModalDismissResult result = Finish(true, "ok",
                $"已关闭对话框（显式选「{chosenText}」（{pick.Note}）：{answerNote}{closeNote}）：“{question}”");
            result.ChosenAnswer = string.IsNullOrEmpty(chosenText) ? null : chosenText;
            return result;
        }

        /// <summary>
        /// 按**状态正确的顺序**关掉一个 <see cref="DialogueBox"/>：先 `closeDialogue()`
        /// （复位 `Game1.dialogueUp` 与 `player.CanMove`），仍在才退回 `exitThisMenu()`，
        /// 最后兜住残留的 `dialogueUp`。返回一句用于 reason 的说明。
        ///
        /// 【为什么抽出来且必须 internal（2026-10-13 task-33 真机定案）】
        /// `SleepSkill` 在提问上答 Yes 之后**必须同一 tick 关框**：真机实测
        /// `answerDialogue()` **只应答、不关框** ⇒ `Game1.newDay=True` 已经是既成事实，
        /// 但提问框一直挂着、`newDaySync` 等不到保存 ⇒ 日期 180s 不动；关框后 ~3s 当天落地
        /// （`logs\probe-bed-close-run1.log`）。两处（dismiss_modal 与 sleep）必须共用这一份顺序，
        /// 绝不允许出现第二份“怎么关框”的实现 —— 关闭路径选错 API 就是 v2 那次永久卡死事故的根因。
        /// </summary>
        internal static string CloseDialogueBox(DialogueBox box)
        {
            string closeNote = "";
            try
            {
                if (IsActiveDialogue(box))
                {
                    try { box.closeDialogue(); } catch { }
                    closeNote = "closeDialogue() 关闭（复位 dialogueUp 与 player.CanMove）";
                }
                if (IsActiveDialogue(box))
                {
                    try { box.exitThisMenu(); } catch { }
                    ClearDialogueFlag();
                    closeNote = "closeDialogue() 未生效，已退回 exitThisMenu() 并复位 dialogueUp";
                }

                // 收尾：菜单已经没了，但 dialogueUp 还挂着残留标志 → 用唯一获准的那处状态写入兜住，
                // 否则后续所有 move_to 都会一直吃 ui_modal（假“有对话框”）。
                if (!IsActiveDialogue(box) && SafeBool(() => Game1.dialogueUp))
                {
                    ClearDialogueFlag();
                    closeNote += (closeNote.Length > 0 ? "；" : "") + "并复位残留的 dialogueUp";
                }
            }
            catch (Exception ex)
            {
                closeNote = "关框异常：" + ex.GetType().Name + ": " + ex.Message;
            }

            return string.IsNullOrEmpty(closeNote) ? "框已经不在了（无需关闭）" : closeNote;
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

        // ==================================================================
        // 【task-129】出货/存档菜单的公共判据与“点 OK”两条路（供 ShippingMenuDismissSkill 用）
        // ==================================================================

        /// <summary>
        /// 存档类菜单：正把盘写出去，**任何情况下都不许关**。
        ///
        /// `SaveGameMenu` 是 1.6.15 里保存的唯一载体（`docs\_il-shipmenu-save.md` §1 的两个创建点）。
        /// `NewDaySavingMenu` 在 1.6.15 **已经不是类型名**（同一篇 §5 的核对），但脑侧的
        /// `MODAL_WAIT_ONLY` 仍按名字列表在等它 —— 所以这里按**类型名**兜一遍，既可编译，
        /// 也不丢掉"将来版本又出现这个名字"的防线。
        /// </summary>
        internal static bool IsSaveMenu(IClickableMenu menu)
        {
            if (menu is SaveGameMenu) return true;
            try { return menu != null && menu.GetType().Name == "NewDaySavingMenu"; }
            catch { return false; }
        }

        /// <summary>出货菜单：日切保存的唯一入口在它自己内部（点 OK 才建 SaveGameMenu）。</summary>
        internal static bool IsShippingMenu(IClickableMenu menu) => menu is ShippingMenu;

        /// <summary>当前活动菜单的类型名（读不到返回空串，绝不抛）。</summary>
        internal static string SafeMenuName()
        {
            try { return Game1.activeClickableMenu?.GetType().Name ?? ""; } catch { return ""; }
        }

        /// <summary>
        /// 反射调用 `ShippingMenu` 的私有 `okClicked()` —— 这是“玩家点了 OK”在代码里的**唯一正路**
        /// （等价玩家点 OK，不是特权操作）。发出后调用方**什么都不该做**，等游戏自己把
        /// outro→SaveGameMenu→存档→换天走完。
        /// </summary>
        internal static bool TryInvokeOkClicked(ShippingMenu ship, out string note)
        {
            note = "";
            try
            {
                MethodInfo m = typeof(ShippingMenu).GetMethod(
                    "okClicked", BindingFlags.Instance | BindingFlags.NonPublic)
                    ?? typeof(ShippingMenu).GetMethod(
                        "okClicked", BindingFlags.Instance | BindingFlags.Public);
                if (m == null)
                {
                    note = "ShippingMenu 上找不到 okClicked（1.6.15 预期是私有实例方法）";
                    return false;
                }

                m.Invoke(ship, null);
                note = $"已反射调用 {m.DeclaringType?.Name}.okClicked()（等价玩家点 OK）";
                return true;
            }
            catch (Exception ex)
            {
                note = "反射 okClicked 异常：" + ex.GetType().Name + ": " + ex.Message;
                return false;
            }
        }

        /// <summary>
        /// 反射失败时的兜底：`currentPage == -1 && CanReceiveInput()` 时点 `okButton` 中心。
        ///
        /// `introTimer > 0` 期间 `receiveLeftClick` 会被**静默丢弃**（菜单还没做完进场动画），
        /// 所以调用方必须**按间隔重试到菜单消失**，而不是点一次就算数。
        /// </summary>
        internal static bool TryClickOkButton(ShippingMenu ship, out string note)
        {
            note = "";
            try
            {
                if (ship.currentPage != -1)
                {
                    note = $"currentPage={ship.currentPage}（还没走到最后一页）";
                    return false;
                }
                if (!ship.CanReceiveInput())
                {
                    note = "CanReceiveInput()=false（introTimer 还没走完，这一下点击会被静默丢弃）";
                    return false;
                }

                ClickableTextureComponent btn = ship.okButton;
                if (btn == null)
                {
                    note = "okButton 为空";
                    return false;
                }

                int x = btn.bounds.Center.X;
                int y = btn.bounds.Center.Y;
                ship.receiveLeftClick(x, y, true);
                note = $"已点 okButton 中心 ({x},{y})";
                return true;
            }
            catch (Exception ex)
            {
                note = "点 okButton 异常：" + ex.GetType().Name + ": " + ex.Message;
                return false;
            }
        }

        private static bool SafeBool(Func<bool> f) { try { return f(); } catch { return false; } }
    }
}
