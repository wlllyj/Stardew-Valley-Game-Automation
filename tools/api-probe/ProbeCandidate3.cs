using System;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Menus;

namespace ApiProbe
{
    /// <summary>
    /// 第三轮候选：**怎么"正确地"回答一个提问对话框**（2026-10-11）。
    ///
    /// 背景（真机事故）：`dismiss_modal` 用
    /// `selectedResponse = N` + `receiveKeyPress(Down×N)` + `Enter` + `Space`
    /// 去选"No"，结果对话框是关了，**但游戏进入了冻结状态**：
    ///   时钟停在 640、canMove=False、isModal=False、世界不再推进（45 秒+）。
    /// 强烈怀疑 Enter/Space 真的确认了某个选项（可能导致半途的睡觉流程）。
    ///
    /// 结论方向：**提问类对话框不能按确认键**。要找的是"只取消、不确认"的官方路径，
    /// 或者"按选项索引精确答某一个"的官方入口。
    /// </summary>
    public static class ProbeCandidate3
    {
        // ---- 候选 A：只取消（等价玩家按 Esc）----
        public static void A_ExitNoArg() => (Game1.activeClickableMenu as DialogueBox)?.exitThisMenu();
        public static void A_ExitWithBool() => (Game1.activeClickableMenu as DialogueBox)?.exitThisMenu(true);
        public static void A_Close() => (Game1.activeClickableMenu as DialogueBox)?.closeDialogue();

        // ---- 候选 B：把"回答"交给地点处理（游戏自己的应答机制）----
        public static void B_AnswerAction()
        {
            var box = Game1.activeClickableMenu as DialogueBox;
            if (box?.responses == null || box.responses.Length == 0) return;
            string key = box.responses[box.responses.Length - 1].responseKey;
            Game1.currentLocation?.answerDialogueAction(key, null);
        }

        // ---- 候选 C：直接给 DialogueBox 注入"取消"按键 ----
        public static void C_EscapeKey() =>
            (Game1.activeClickableMenu as DialogueBox)?.receiveKeyPress(Microsoft.Xna.Framework.Input.Keys.Escape);

        // ---- 候选 D：读出"这个问题是谁问的" ----
        public static string D_LastQuestionKey() => Game1.currentLocation?.lastQuestionKey ?? "";
        public static string D_LastQuestionKeyPlayer() => Game1.player?.currentLocation?.lastQuestionKey ?? "";

        // ---- 候选 E：床上状态与暂停标志（诊断"冻结"用）----
        public static bool E_PlayerIsInBed() => Game1.player != null && Game1.player.isInBed.Value;
        public static bool E_GamePaused() => Game1.paused;
        public static bool E_CanMove() => Game1.player != null && Game1.player.CanMove;
        public static bool E_IsPlayerFree() => Context.IsPlayerFree;
        public static bool E_DialogueUp() => Game1.dialogueUp;
        public static bool E_IsActive() => Game1.game1.IsActive;
        // ❌ 已证伪：NetWorldState 上没有 TimeOfDay（CS1061）。游戏时间请读 Game1.timeOfDay。
        // public static string E_NetWorldStateTime() => Game1.netWorldState.Value.TimeOfDay.ToString();
        public static int E_GameTimeOfDay() => Game1.timeOfDay;
        public static bool E_ShouldTimePass() => Game1.shouldTimePass();
        public static int E_ActiveMenuCount() => Game1.activeClickableMenu == null ? 0 : 1;
    }
}
