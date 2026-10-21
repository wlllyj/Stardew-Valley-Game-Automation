using System;
using System.Collections.Generic;
using System.Reflection;
using StardewValley;
using StardewValley.Menus;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 读取“当前模态”的可读内容（世界快照与技能共用）。
    ///
    /// 【为什么单独成文件】observe 要把模态内容报给脑（ui.activeMenuText / dialogueResponses），
    /// dismiss_modal 要按同样的口径判断“这是不是提问、哪一项是否”。两处必须是**同一套读法**，
    /// 否则会出现“observe 说是问题、dismiss 却当成普通菜单”的自相矛盾。
    ///
    /// 【实测依据】`DialogueBox` 上没有 `dialogue` 字段、也没有 `receiveAction`，
    /// 只有 `getCurrentString()` / `responses`（类型是 `Response[]`，用 `.Length`）/
    /// `selectedResponse` / `isQuestion` —— 全部经 tools/api-probe 编译期实证。
    /// </summary>
    internal static class UiRead
    {
        /// <summary>当前活动菜单，若非 DialogueBox 则为 null。</summary>
        public static DialogueBox ActiveDialogueBox()
        {
            try { return Game1.activeClickableMenu as DialogueBox; }
            catch { return null; }
        }

        /// <summary>
        /// 模态里的文字：
        ///   * DialogueBox → `getCurrentString()`（例："go to sleep for the night?"）；
        ///   * 其它菜单   → 菜单类型名（例："GameMenu"）；
        ///   * 没有菜单   → null（序列化时该字段会被省略）。
        /// </summary>
        public static string ActiveMenuText()
        {
            try
            {
                IClickableMenu menu = Game1.activeClickableMenu;
                if (menu == null) return null;

                if (menu is DialogueBox box) return box.getCurrentString();
                return menu.GetType().Name;
            }
            catch { return null; }
        }

        /// <summary>对话框的选项文本；没有对话框时返回空数组（不是 null）。</summary>
        public static string[] DialogueResponseTexts()
        {
            var box = ActiveDialogueBox();
            if (box == null) return Array.Empty<string>();

            try
            {
                Response[] responses = box.responses;
                if (responses == null || responses.Length == 0) return Array.Empty<string>();

                var list = new string[responses.Length];
                for (int i = 0; i < responses.Length; i++)
                    list[i] = responses[i]?.responseText ?? "";
                return list;
            }
            catch { return Array.Empty<string>(); }
        }

        /// <summary>当前对话框是不是“提问”。</summary>
        public static bool DialogueIsQuestion()
        {
            var box = ActiveDialogueBox();
            if (box == null) return false;
            try { return box.isQuestion; } catch { return false; }
        }

        /// <summary>
        /// `LevelUpMenu` 的职业候选（私有字段 `professionsToChoose`，类型 `List&lt;int&gt;`，**需反射读**）。
        ///
        /// 【为什么要报这个字段】职业选择弹窗（技能 5/10 级）是**不可逆**的：
        /// `exitThisMenu()` → `cleanupBeforeExit()` → `okButtonClicked()` → `RemoveLevelFromLevelList()`
        /// 会永久删掉这次等级点 ⇒ 那次 Tiller/Artisan 选择就丢了。脑在 dismiss 之前必须先知道
        /// “这是普通升级弹窗，还是有人在等我选职业”。判据来源见 `docs\_il-profession.md` §3。
        ///
        /// 【三种返回】当前菜单不是 `LevelUpMenu` → null（序列化时该字段被省略）；
        /// 是 `LevelUpMenu` 且读到了 → `int[]`（**空数组 = 普通升级、没有职业可选**）；
        /// 是 `LevelUpMenu` 但读不到（字段改名/反射异常）→ null —— 脑侧对 null 按“未知”处理，
        /// **同样不许 dismiss**（fail-safe：不拿不确定性去赌不可逆操作）。
        /// </summary>
        public static int[] ProfessionsToChoose()
        {
            try
            {
                IClickableMenu menu = Game1.activeClickableMenu;
                if (!(menu is LevelUpMenu)) return null;

                FieldInfo field = ProfessionChooserField();
                if (field == null) return null;

                var raw = field.GetValue(menu) as System.Collections.IEnumerable;
                if (raw == null) return null;

                var ids = new List<int>();
                foreach (object item in raw)
                    if (item is int id) ids.Add(id);
                return ids.ToArray();
            }
            catch { return null; }
        }

        /// <summary>
        /// 【dialogue-okfix / P2 取证】当前对话框**还剩几条**对话（`DialogueBox.dialogues` 的元素数）。
        ///
        /// 【为什么需要】真机现象："关框之后同一句又回来"。两种成因必须分开：
        ///   * 事件脚本重放同一条 command（`Event.CurrentCommand` 不自增）⇒ `dialogues` 条数会被
        ///     重新填回、`command` 不变；
        ///   * 事件重触发（新 Event 实例）⇒ 两者都会变。
        /// 没有这两个字段，只能靠 reason 文本猜。
        ///
        /// 【读法】`dialogues` 是 `DialogueBox` 上的字段（tools/api-probe 编译期实证存在），
        /// 但不同版本可能是 `List&lt;string&gt;`/`Queue&lt;string&gt;`，所以按 `ICollection.Count`
        /// 反射读（与 `characterIndexInDialogue` 同一套"读不到就 null"的口径）。
        /// 没有对话框 / 字段不存在 / 反射异常 ⇒ null（**不拿 0 冒充观测**）。
        /// </summary>
        public static int? DialogueLineCount(DialogueBox box)
        {
            if (box == null) return null;
            try
            {
                FieldInfo field = DialogueLinesField();
                if (field == null) return null;

                object raw = field.GetValue(box);
                if (raw is System.Collections.ICollection col) return col.Count;
                return null;
            }
            catch { return null; }
        }

        /// <summary>
        /// 【dialogue-okfix / P2 取证】当前事件脚本执行到**第几条 command**
        /// （`Game1.CurrentEvent.CurrentCommand`；编译期实证类型是 `int`，即命令下标）。
        ///
        /// 用途：判定"关框后同句复现"是**重放**（下标没自增）还是**重触发/正常推进**（下标变了）。
        /// 没有事件 ⇒ null（字段被省略）；事件在跑但读不到 ⇒ 同样 null。
        /// </summary>
        public static int? EventCommand()
        {
            try
            {
                Event ev = Game1.CurrentEvent;
                return ev == null ? (int?)null : ev.CurrentCommand;
            }
            catch { return null; }
        }

        private static FieldInfo _dialogueLinesField;
        private static bool _dialogueLinesFieldSearched;

        private static FieldInfo DialogueLinesField()
        {
            if (!_dialogueLinesFieldSearched)
            {
                _dialogueLinesFieldSearched = true;
                try
                {
                    _dialogueLinesField = typeof(DialogueBox).GetField(
                        "dialogues",
                        BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                }
                catch { _dialogueLinesField = null; }
            }
            return _dialogueLinesField;
        }

        // 反射结果缓存一次：观察是热路径，但 `GetField` 只在第一次付代价。
        private static FieldInfo _professionField;
        private static bool _professionFieldSearched;

        private static FieldInfo ProfessionChooserField()
        {
            if (!_professionFieldSearched)
            {
                _professionFieldSearched = true;
                try
                {
                    _professionField = typeof(LevelUpMenu).GetField(
                        "professionsToChoose",
                        BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                }
                catch { _professionField = null; }
            }
            return _professionField;
        }
    }
}
