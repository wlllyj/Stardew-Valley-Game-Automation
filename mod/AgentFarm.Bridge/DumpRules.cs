using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-213】`debug_dump` 的**纯规则**（零游戏类型依赖、零外部依赖）。
    ///
    /// 【为什么外置】仓库里没有能引用游戏程序集的 C# 测试工程（`mod\AgentFarm.Bridge.Tests`
    /// 是零依赖控制台自检，只 `Compile Include` 纯逻辑文件）。凡是**判据**必须放在不
    /// `using StardewValley` 的文件里才能跑行为断言（同一纪律见 `ClumpRules` /
    /// `TileListRules` / `AnswerRules` / `ToolUpgradeRules`）。
    ///
    /// 【这个技能为什么存在】Furnace 配方缺失是升级链的硬阻塞：离线只能把授予路径收到
    /// 「`Farmer.AddMissedMailAndRecipes()` 是补发通道之一；条件串在打包 xnb 里读不到」，
    /// 必须**一次真机运行时内省**一锤定音（`docs\_il-furnace-recipe.md`）。这也是通用内省面：
    /// 以后查任何数据表都复用它。
    ///
    /// 本文件里的判据：
    ///   * 表名归一（大小写/连字符/别名 → 规范名；不认识的返回空串 ⇒ 调用方 fail-closed）；
    ///   * `limit` 钳制（默认 200、上限 2000，**不许**把整张表无界塞进回执）；
    ///   * `key` 匹配分级（精确 1 / 子串 2 / 不中 0，供回执标注 matchMode）；
    ///   * 集合差分（`add_missed_recipes` 的前后差分，排序后返回）；
    ///   * 复杂值的字符串化（反射逐成员，带截断，防超大回执）。
    /// </summary>
    internal static class DumpRules
    {
        /// <summary>`limit` 省略时的默认条数（够看一张表的开头，又不会撑爆回执）。</summary>
        public const int LimitDefault = 200;

        /// <summary>`limit` 的硬上限：任何调用方都不许要到更多（卡面要求）。</summary>
        public const int LimitMax = 2000;

        /// <summary>单条值字符串的截断长度（复杂对象反射出来可能很长）。</summary>
        public const int ValueMaxChars = 4000;

        /// <summary>规范表名（顺序 = 卡面顺序；回执里的 table 一律是这个写法）。</summary>
        public static readonly string[] Tables =
        {
            "crafting_recipes",
            "cooking_recipes",
            "trigger_actions",
            "mail",
            "machines",
            "objects",
            "big_craftables",
        };

        /// <summary>子串匹配模式下最多返回多少条命中（与 limit 取小）。</summary>
        public const int MatchMax = 200;

        /// <summary>
        /// 把用户给的表名归一成 <see cref="Tables"/> 里的规范名；不认识 ⇒ <c>""</c>（fail-closed）。
        ///
        /// 归一规则：去空白、转小写、连字符/空格/点 → 下划线；再收几个常见别名
        /// （`crafting`/`craftingrecipes` ⇒ `crafting_recipes` 等）。**不做**模糊匹配：
        /// 宁可 `table_unknown`，也不许猜一张表去读。
        /// </summary>
        public static string NormalizeTable(string raw)
        {
            if (string.IsNullOrWhiteSpace(raw)) return "";
            var sb = new StringBuilder();
            foreach (char ch in raw.Trim().ToLowerInvariant())
            {
                if (ch == '-' || ch == ' ' || ch == '.' || ch == '/')
                    sb.Append('_');
                else
                    sb.Append(ch);
            }
            string name = sb.ToString();
            while (name.Contains("__")) name = name.Replace("__", "_");
            name = name.Trim('_');
            // 也接受资产路径写法（`Data/CraftingRecipes` ⇒ `data_craftingrecipes`）：
            // 真机取证的人手里最容易拿到的是资产名，而不是我们脑侧的规范名。
            if (name.StartsWith("data_", StringComparison.Ordinal))
                name = name.Substring("data_".Length);

            switch (name)
            {
                case "crafting":
                case "craftingrecipes":
                case "crafting_recipe":
                    return "crafting_recipes";
                case "cooking":
                case "cookingrecipes":
                case "cooking_recipe":
                    return "cooking_recipes";
                case "triggeractions":
                case "trigger_action":
                case "triggers":
                    return "trigger_actions";
                case "mails":
                    return "mail";
                case "machine":
                case "machinedata":
                    return "machines";
                case "object":
                case "objectdata":
                    return "objects";
                case "bigcraftable":
                case "bigcraftables":
                case "big_craftable":
                    return "big_craftables";
                default:
                    return IsKnownTable(name) ? name : "";
            }
        }

        /// <summary>规范表名是否是支持的表。</summary>
        public static bool IsKnownTable(string name)
        {
            if (string.IsNullOrEmpty(name)) return false;
            for (int i = 0; i < Tables.Length; i++)
                if (Tables[i] == name) return true;
            return false;
        }

        /// <summary>
        /// 钳制 `limit`：省略 ⇒ <see cref="LimitDefault"/>；&lt;1 ⇒ 1；&gt;<see cref="LimitMax"/> ⇒
        /// <see cref="LimitMax"/>。**永远**返回一个可用的正数（调用方不必再判空）。
        /// </summary>
        public static int ClampLimit(int? limit)
        {
            int v = limit ?? LimitDefault;
            if (v < 1) v = 1;
            if (v > LimitMax) v = LimitMax;
            return v;
        }

        /// <summary>
        /// `key` 与表项 key 的匹配等级：1 = 精确（忽略大小写），2 = 子串（忽略大小写），0 = 不中。
        /// 精确优先——回执据此标注 `matchMode=exact|substring|none`，避免把"猜中的子串"当精确证据。
        /// </summary>
        public static int MatchKind(string key, string wanted)
        {
            if (string.IsNullOrEmpty(key) || string.IsNullOrEmpty(wanted)) return 0;
            if (string.Equals(key, wanted, StringComparison.OrdinalIgnoreCase)) return 1;
            return key.IndexOf(wanted, StringComparison.OrdinalIgnoreCase) >= 0 ? 2 : 0;
        }

        /// <summary>
        /// 集合差（`after` 有、`before` 没有），**按序数排序**后返回 —— 回执要可复现。
        /// 用序数比较而不是文化比较：这是程序化 key（`Furnace`/`(O)334`），与语言无关。
        /// </summary>
        public static List<string> DiffAdded(IEnumerable<string> before, IEnumerable<string> after)
        {
            var old = new HashSet<string>(before ?? Enumerable.Empty<string>(), StringComparer.Ordinal);
            var added = new List<string>();
            foreach (string key in after ?? Enumerable.Empty<string>())
                if (key != null && !old.Contains(key)) added.Add(key);
            added.Sort(StringComparer.Ordinal);
            return added;
        }

        /// <summary>
        /// 把一个游戏数据值渲染成**一行字符串**（回执用）。
        ///
        /// 口径：
        ///   * `null` ⇒ `"null"`；`string` 原样；基础类型用不变文化 `ToString`；
        ///   * `IDictionary` ⇒ `{k=v, ...}`；其它 `IEnumerable` ⇒ `[a, b, ...]`（都只展开一层）；
        ///   * 复杂对象 ⇒ 反射**全部公开实例属性 + 公开字段**（按名字排序），写成
        ///     `TypeName{Name=Value, ...}`；嵌套对象只再展开一层（防爆）；
        ///   * 任何反射/取值异常 ⇒ 该成员写 `"<读不到>"`，整体绝不抛；
        ///   * 最后按 `maxChars` 截断（截断处标注真实长度）。
        ///
        /// 不做 JSON 序列化：不打新依赖，且回执是 `key -> 值字符串` 的形状（卡面要求）。
        /// </summary>
        public static string Describe(object value, int maxChars = ValueMaxChars)
        {
            string text;
            try { text = DescribeCore(value, 2); }
            catch (Exception ex) { text = "<描述失败：" + ex.GetType().Name + ">"; }
            if (text == null) text = "null";
            if (maxChars > 0 && text.Length > maxChars)
                text = text.Substring(0, maxChars) + "…<truncated " + text.Length + " chars>";
            return text;
        }

        private static string DescribeCore(object value, int depth)
        {
            if (value == null) return "null";
            if (value is string s) return s;
            if (value is bool b) return b ? "true" : "false";
            if (value is char c) return c.ToString();
            if (value is Enum e) return e.ToString();
            if (value is IFormattable f)
            {
                try { return f.ToString(null, CultureInfo.InvariantCulture) ?? ""; }
                catch { return value.ToString() ?? ""; }
            }
            if (depth <= 0) return value.ToString() ?? value.GetType().Name;

            if (value is IDictionary dict)
            {
                var parts = new List<string>();
                int n = 0;
                foreach (DictionaryEntry entry in dict)
                {
                    parts.Add(SafeKey(entry.Key) + "=" + DescribeCore(entry.Value, depth - 1));
                    if (++n >= 12) { parts.Add("…"); break; }
                }
                return "{" + string.Join(", ", parts) + "}";
            }
            if (value is IEnumerable seq)
            {
                var parts = new List<string>();
                int n = 0;
                foreach (object item in seq)
                {
                    parts.Add(DescribeCore(item, depth - 1));
                    if (++n >= 12) { parts.Add("…"); break; }
                }
                return "[" + string.Join(", ", parts) + "]";
            }

            Type type = value.GetType();
            var members = new List<string>();
            var props = type.GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .Where(p => p.CanRead && p.GetIndexParameters().Length == 0)
                .OrderBy(p => p.Name, StringComparer.Ordinal);
            foreach (PropertyInfo prop in props)
            {
                string member;
                try { member = DescribeCore(prop.GetValue(value), depth - 1); }
                catch { member = "<读不到>"; }
                members.Add(prop.Name + "=" + member);
            }
            var fields = type.GetFields(BindingFlags.Public | BindingFlags.Instance)
                .OrderBy(fi => fi.Name, StringComparer.Ordinal);
            foreach (FieldInfo field in fields)
            {
                string member;
                try { member = DescribeCore(field.GetValue(value), depth - 1); }
                catch { member = "<读不到>"; }
                members.Add(field.Name + "=" + member);
            }
            if (members.Count == 0)
            {
                try { return value.ToString() ?? type.Name; }
                catch { return type.Name; }
            }
            return type.Name + "{" + string.Join(", ", members) + "}";
        }

        private static string SafeKey(object key)
        {
            if (key == null) return "null";
            try { return Convert.ToString(key, CultureInfo.InvariantCulture) ?? ""; }
            catch { return "?"; }
        }
    }
}
