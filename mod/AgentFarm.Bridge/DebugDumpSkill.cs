using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-213】`debug_dump`：**只读**地把一张游戏数据表倒成 `key -> 值字符串`。
    ///
    /// 【为什么需要它（本卡的真实动机）】Furnace 配方缺失是铁匠铺升级链的硬阻塞：
    /// 离线把授予路径收到「`Farmer.AddMissedMailAndRecipes()` 是补发通道之一；配方表在
    /// 打包 xnb 里，条件串读不到」⇒ 必须**一次真机运行时内省**一锤定音
    /// （`docs\_il-furnace-recipe.md`，task-212 定案）。
    ///
    /// 这也是通用「Mod 内省面」：以后查任何数据表/补发逻辑都复用它（`add_missed_recipes`
    /// 是它的伴生写操作，见 `AddMissedRecipesSkill`）。
    ///
    /// 【task-222：1.6 强类型资产】真机（task-214）暴露：1.6 的数据表**不再清一色**
    /// `Dictionary&lt;string,string&gt;` —— `Data/TriggerActions` 是 `List&lt;TriggerActionData&gt;`、
    /// `Data/Objects`/`BigCraftables`/`Machines` 是 `Dictionary&lt;string,XxxData&gt;` ⇒ 旧实现
    /// 强转字典全挂（`InvalidCastException`），能读的只剩配方/信件三张。
    /// 现在改成**按表登记期望形态**（字典 or 列表 + 值类型简单名）走泛型 `Load&lt;T&gt;`，
    /// 再交给 `DumpRules.EnumerateEntries` 泛型摊平（纯函数、自检工程可跑行为断言）。
    /// **每张表 fail-closed 独立**：一张读不出来只影响它自己（回执带 `error` 原文），
    /// 绝不因为一张表挂了就整类内省不可用。
    ///
    /// 【纪律】
    ///   * **只读**：本技能绝不写玩家/世界状态（写操作在 `add_missed_recipes` 里，且单独回执）；
    ///   * 表名与 `limit` 的判据全在 `DumpRules`（纯函数）；
    ///   * **不许**把整张表无界塞进回执：`limit` 默认 200 / 上限 2000，`truncated` 如实报；
    ///   * fail-closed：不认识的表 ⇒ `table_unknown`（reason 列出支持的表）；
    ///     读表抛异常 ⇒ `load_failed`（异常原文进 `reason`/`error`，不许猜）；
    ///   * 复杂值用 `DumpRules.Describe`（反射逐成员 + 截断），**不打新依赖**。
    ///
    /// 【单 tick 同步技能】不加入 `BridgeHost.IsLongTaskSkill`：一次读表即完成；
    /// 时间预算见 `Skills.ClampDumpTimeout`（默认 30s，大表允许更久）。
    /// </summary>
    internal sealed class DebugDumpSkill
    {
        private readonly ExecRequest _req;
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;

        private long _seqBefore;

        /// <summary>一张表的加载规格：资产名 + 期望形态（列表/字典）+ 值类型简单名（null=string）。</summary>
        private sealed class TableSpec
        {
            public string Asset;
            public bool IsList;
            public string ValueTypeName;
        }

        private static readonly Dictionary<string, TableSpec> Specs = new Dictionary<string, TableSpec>
        {
            ["crafting_recipes"] = new TableSpec { Asset = "Data/CraftingRecipes" },
            ["cooking_recipes"] = new TableSpec { Asset = "Data/CookingRecipes" },
            ["mail"] = new TableSpec { Asset = "Data/Mail" },
            ["trigger_actions"] = new TableSpec { Asset = "Data/TriggerActions", IsList = true, ValueTypeName = "TriggerActionData" },
            ["machines"] = new TableSpec { Asset = "Data/Machines", ValueTypeName = "MachineData" },
            ["objects"] = new TableSpec { Asset = "Data/Objects", ValueTypeName = "ObjectData" },
            ["big_craftables"] = new TableSpec { Asset = "Data/BigCraftables", ValueTypeName = "BigCraftableData" },
        };

        /// <summary>单参泛型 `Load&lt;T&gt;(string)` 的缓存（`Game1.content` 是 ContentManager）。</summary>
        private static MethodInfo _loadMethod;
        private static bool _loadMethodSearched;

        public DebugDumpSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._req = req;
            this._world = world;
            this._monitor = monitor;
        }

        private ExecResponse Fail(string status, string reason, string type = null, string table = null)
            => new ExecResponse
            {
                Ok = false,
                Status = status,
                Skill = "debug_dump",
                Reason = reason,
                Error = reason,
                Table = table,
                Type = type,
                Schema = Skills.ExecSchema,
                ElapsedMs = 0,
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world != null ? this._world.WorldSeq : this._seqBefore,
            };

        /// <summary>主线程调用：单 tick 技能，永远返回终态。</summary>
        public object Step()
        {
            this._seqBefore = this._world != null ? this._world.WorldSeq : 0;

            string raw = this._req != null && this._req.Args != null ? this._req.Args.Table : null;
            string table = DumpRules.NormalizeTable(raw);
            if (!DumpRules.IsKnownTable(table) || !Specs.TryGetValue(table, out TableSpec spec))
            {
                return this.Fail("table_unknown",
                    "不支持的数据表 " + Describe(raw) + "；支持的表：" + string.Join(", ", DumpRules.Tables));
            }

            int limit = DumpRules.ClampLimit(this._req != null && this._req.Args != null
                ? this._req.Args.Limit : (int?)null);
            string wanted = this._req != null && this._req.Args != null ? this._req.Args.Key : null;

            object root;
            string typeLabel;
            string loadNote = "";
            try
            {
                root = LoadAsset(spec, out typeLabel, out loadNote);
            }
            catch (Exception ex)
            {
                Exception inner = Unwrap(ex);
                string reason = "读 " + spec.Asset + " 失败：" + inner.GetType().Name + ": " + inner.Message
                                + (string.IsNullOrEmpty(loadNote) ? "" : "；" + loadNote);
                return this.Fail("load_failed", reason, null, table);
            }
            if (root == null)
            {
                return this.Fail("load_failed",
                    "读 " + spec.Asset + " 返回 null（游戏没有加载这张表？）"
                    + (string.IsNullOrEmpty(loadNote) ? "" : "；" + loadNote), null, table);
            }
            typeLabel = DumpRules.ShapeLabel(root);

            List<KeyValuePair<string, string>> all = DumpRules.EnumerateEntries(root);

            var resp = new ExecResponse
            {
                Ok = true,
                Status = "ok",
                Skill = "debug_dump",
                Schema = Skills.ExecSchema,
                ElapsedMs = 0,
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world != null ? this._world.WorldSeq : this._seqBefore,
                Table = table,
                Type = typeLabel,
                Count = all.Count,
            };

            if (!string.IsNullOrWhiteSpace(wanted))
            {
                // 精确优先、子串兜底，两者都试并标注（卡面要求）：绝对匹配一条都没有时才降级子串。
                var exact = new List<string[]>();
                var fuzzy = new List<string[]>();
                foreach (KeyValuePair<string, string> pair in all)
                {
                    int kind = DumpRules.MatchKind(pair.Key, wanted);
                    if (kind == 1) exact.Add(new[] { pair.Key, pair.Value });
                    else if (kind == 2) fuzzy.Add(new[] { pair.Key, pair.Value });
                }
                string mode = exact.Count > 0 ? "exact" : (fuzzy.Count > 0 ? "substring" : "none");
                List<string[]> matched = exact.Count > 0 ? exact : fuzzy;
                if (matched.Count == 0 && spec.IsList)
                {
                    // 【task-222】列表型表（如 TriggerActions）的 key 是下标，按 key 找 `Furnace`
                    // 永远找不到 ⇒ 再按**值内容**子串试一次（只加一条证据，不改 key 语义）。
                    foreach (KeyValuePair<string, string> pair in all)
                    {
                        if (pair.Value.IndexOf(wanted, StringComparison.OrdinalIgnoreCase) >= 0)
                            matched.Add(new[] { pair.Key, pair.Value });
                    }
                    if (matched.Count > 0) mode = "value_substring";
                }
                int cap = Math.Min(matched.Count, Math.Min(limit, DumpRules.MatchMax));
                resp.MatchMode = mode;
                resp.Matched = matched.GetRange(0, cap).ToArray();
                resp.MatchedCount = matched.Count;
                resp.MatchedTruncated = matched.Count > cap;
                resp.Entries = new string[0][];
                resp.Truncated = false;
                resp.Reason = matched.Count == 0
                    ? "表 " + table + "（" + typeLabel + "）里没有匹配 " + Describe(wanted)
                      + " 的 key（精确、子串" + (spec.IsList ? "、值子串" : "") + "都没有）"
                    : "按 key 过滤：" + mode + " 命中 " + matched.Count + " 条"
                      + (resp.MatchedTruncated == true ? "（只回前 " + cap + " 条）" : "");
                return resp;
            }

            int take = Math.Min(all.Count, limit);
            var entries = new string[take][];
            for (int i = 0; i < take; i++)
                entries[i] = new[] { all[i].Key, all[i].Value };
            resp.Entries = entries;
            resp.Truncated = all.Count > take;
            resp.Reason = "表 " + table + "（" + typeLabel + "）共 " + all.Count + " 条"
                          + (resp.Truncated == true ? "（按 limit=" + limit + " 只回前 " + take + " 条）" : "（全部返回）");
            return resp;
        }

        /// <summary>
        /// 按表登记形态加载资产：先按期望类型（字典/列表 + 值类型）读；复杂表读失败再退回
        /// `Dictionary&lt;string,string&gt;`（老版本资产形状）。两条都失败 ⇒ 抛出合并后的异常原文。
        /// </summary>
        private static object LoadAsset(TableSpec spec, out string typeLabel, out string note)
        {
            typeLabel = "";
            note = "";
            var errors = new List<string>();

            if (!string.IsNullOrEmpty(spec.ValueTypeName))
            {
                Type valueType = ResolveGameType(spec.ValueTypeName);
                if (valueType == null)
                {
                    errors.Add("程序集里找不到 " + spec.ValueTypeName + " 类型");
                    note = string.Join("；", errors);
                }
                else
                {
                    try
                    {
                        object typed = LoadContainer(spec.Asset, spec.IsList, valueType);
                        typeLabel = DumpRules.ShapeLabel(typed);
                        return typed;
                    }
                    catch (Exception ex)
                    {
                        Exception inner = Unwrap(ex);
                        errors.Add("按 " + valueType.FullName + " 读失败：" + inner.GetType().Name + ": " + inner.Message);
                        note = string.Join("；", errors);
                    }
                }
            }

            // 兜底：老版本（或某些表）把资产暴露成 Dictionary<string,string>。
            try
            {
                object legacy = LoadContainer(spec.Asset, false, typeof(string));
                typeLabel = DumpRules.ShapeLabel(legacy);
                return legacy;
            }
            catch (Exception ex)
            {
                Exception inner = Unwrap(ex);
                errors.Add("按 Dictionary<string,string> 兜底读也失败：" + inner.GetType().Name + ": " + inner.Message);
            }

            throw new InvalidOperationException(string.Join("；", errors));
        }

        private static object LoadContainer(string asset, bool isList, Type valueType)
        {
            MethodInfo method = FindLoadMethod();
            if (method == null)
                throw new MissingMethodException("Game1.content 上找不到单参泛型 Load<T>(string)（游戏版本不支持内省读表）");
            Type container = isList
                ? typeof(List<>).MakeGenericType(valueType)
                : typeof(Dictionary<,>).MakeGenericType(typeof(string), valueType);
            object result = method.MakeGenericMethod(container).Invoke(Game1.content, new object[] { asset });
            if (result == null)
                throw new InvalidCastException("Load 返回 null（资产没加载）");
            return result;
        }

        private static MethodInfo FindLoadMethod()
        {
            if (_loadMethodSearched) return _loadMethod;
            _loadMethodSearched = true;
            try
            {
                MethodInfo[] methods = Game1.content.GetType().GetMethods(BindingFlags.Public | BindingFlags.Instance);
                foreach (MethodInfo m in methods)
                {
                    if (m.Name != "Load" || !m.IsGenericMethodDefinition) continue;
                    if (m.GetParameters().Length != 1) continue;
                    _loadMethod = m;
                    break;
                }
            }
            catch
            {
                _loadMethod = null;
            }
            return _loadMethod;
        }

        /// <summary>
        /// 在**所有已加载程序集**里按类型简单名解析（1.6 把这些数据类放在
        /// `StardewValley.GameData` 命名空间下，有的版本在游戏程序集里、有的在附属程序集里；
        /// 命名空间与程序集位置都不写死）。
        /// </summary>
        private static Type ResolveGameType(string simpleName)
        {
            Type found = ResolveGameType(typeof(Game1).Assembly, simpleName);
            if (found != null) return found;
            try
            {
                foreach (Assembly asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    if (asm == typeof(Game1).Assembly) continue;
                    Type t = ResolveGameType(asm, simpleName);
                    if (t != null) return t;
                }
            }
            catch
            {
                // 遍历失败 ⇒ 调用方按"读不了"处理（fail-closed）
            }
            return null;
        }

        private static Type ResolveGameType(Assembly asm, string simpleName)
        {
            try
            {
                Type[] types;
                try { types = asm.GetTypes(); }
                catch (ReflectionTypeLoadException ex)
                {
                    var list = new List<Type>();
                    foreach (Type t in ex.Types) if (t != null) list.Add(t);
                    types = list.ToArray();
                }
                foreach (Type t in types)
                    if (t.Name == simpleName && !t.IsAbstract) return t;
            }
            catch
            {
                // 解析失败 ⇒ null
            }
            return null;
        }

        private static Exception Unwrap(Exception ex)
        {
            if (ex is TargetInvocationException tie && tie.InnerException != null) return tie.InnerException;
            return ex;
        }

        private static string Describe(string raw)
            => raw == null ? "(空)" : "\"" + raw + "\"";
    }
}
