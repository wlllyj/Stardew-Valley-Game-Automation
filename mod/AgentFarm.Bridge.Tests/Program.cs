using System;
using System.Collections.Generic;
using AgentFarm.Bridge;

namespace AgentFarm.Bridge.Tests
{
    /// <summary>
    /// task-182 必修 4（GAP-1）：`ClumpRules.Ready` 的**行为**断言（不是源码文本断言）。
    ///
    /// 覆盖的口径 = `HoeDirt.readyForHarvest()` 的 IL 逐条等价（`scratch\_t176_ready.txt`）：
    ///   * 游戏说了算（`gameSaid != null` ⇒ 来源 `"game"`，且**优先于**字段判据）；
    ///   * 兜底字段判据的四类假阳性（复收冷却 / 阶段没走完 / 枯死 / 采集形态 2）；
    ///   * 任一判据字段缺项 ⇒ `(null, null)`（fail-closed）；
    ///   * **NIT-1**：`forageCrop == true` 而 `whichForageCrop` 读不到 ⇒ `(null, null)`。
    ///
    /// 关键：**最后一条**（`FieldsPathStillWorksAfterGameBranch`）就是 task-178 的 `m178b`
    /// （在游戏分支之后插 `return (null, null);`）的杀手 —— 它走 `gameSaid = null` 的兜底路径，
    /// 期望 `(true, "fields")`；任何让兜底路径提前返回 null 的变异都会让它红。
    /// </summary>
    internal static class Program
    {
        private static int _failed;

        private static void Check(string name, bool ok, string detail)
        {
            if (ok)
            {
                Console.WriteLine("  ok  " + name);
                return;
            }
            _failed++;
            Console.WriteLine("FAIL  " + name + "  -> " + detail);
        }

        private static void Expect(string name, (bool? Value, string Source) actual, bool? value, string source)
        {
            bool ok = actual.Value == value && string.Equals(actual.Source ?? "<null>", source ?? "<null>", StringComparison.Ordinal);
            Check(name, ok, $"期望 ({value?.ToString() ?? "null"}, {source ?? "null"})，实得 ({actual.Value?.ToString() ?? "null"}, {actual.Source ?? "null"})");
        }

        private static int Main()
        {
            Console.WriteLine("ClumpRules.Ready 行为断言（task-182 GAP-1）");

            // ---- 游戏口径优先 -------------------------------------------------
            Expect("game_said_true_wins", ClumpRules.Ready(true, false, 0, 0, 1, false, false, null), true, "game");
            Expect("game_said_false_wins_even_if_fields_say_ready",
                   ClumpRules.Ready(false, true, 0, 5, 6, false, false, null), false, "game");

            // ---- 兜底字段判据（gameSaid = null）--------------------------------
            var ready = (bool?)true;
            var no = (bool?)false;
            Expect("fields_path_ready", ClumpRules.Ready(null, ready, 0, 5, 6, no, no, null), true, "fields");
            Expect("fields_path_regrow_cooldown", ClumpRules.Ready(null, ready, 1, 5, 6, no, no, null), false, "fields");
            Expect("fields_path_phase_incomplete", ClumpRules.Ready(null, no, 0, 4, 6, no, no, null), false, "fields");
            Expect("fields_path_dead", ClumpRules.Ready(null, ready, 0, 5, 6, true, no, null), false, "fields");
            Expect("fields_path_forage_form_2", ClumpRules.Ready(null, ready, 0, 5, 6, no, true, "2"), false, "fields");
            Expect("fields_path_forage_form_1", ClumpRules.Ready(null, ready, 0, 5, 6, no, true, "1"), true, "fields");
            Expect("fields_path_not_forage_ignores_which", ClumpRules.Ready(null, ready, 0, 5, 6, no, no, "2"), true, "fields");

            // ---- 缺项 ⇒ 判不了（fail-closed）----------------------------------
            Expect("missing_fully_grown", ClumpRules.Ready(null, null, 0, 5, 6, no, no, null), null, null);
            Expect("missing_day_of_phase", ClumpRules.Ready(null, ready, null, 5, 6, no, no, null), null, null);
            Expect("missing_current_phase", ClumpRules.Ready(null, ready, 0, null, 6, no, no, null), null, null);
            Expect("missing_phase_days", ClumpRules.Ready(null, ready, 0, 5, null, no, no, null), null, null);
            Expect("missing_dead", ClumpRules.Ready(null, ready, 0, 5, 6, null, no, null), null, null);
            Expect("missing_forage_flag", ClumpRules.Ready(null, ready, 0, 5, 6, no, null, null), null, null);
            // NIT-1：forageCrop 为真但 whichForageCrop 读不到 ⇒ 判不了（旧代码会错给 (true,"fields")）
            Expect("nit1_forage_without_which_is_unknown", ClumpRules.Ready(null, ready, 0, 5, 6, no, true, null), null, null);

            // ---- 变异杀手：游戏分支之后不许提前兜底（m178b 形态）----------------
            // gameSaid = null 时必须**继续走**字段判据；插 `return (null,null);` 的变异会在这里红。
            bool okFallback = ClumpRules.Ready(null, ready, 0, 5, 6, no, no, null) == (true, "fields");
            Check("fields_path_still_works_after_the_game_branch", okFallback,
                  "兜底路径被提前 return 短路了（m178b 形态：fail-closed 过头）");

            Console.WriteLine(_failed == 0
                ? "OK 18 断言全部通过"
                : $"FAILED {_failed} 条断言不通过");
            return _failed == 0 ? 0 : 1;
        }
    }
}
