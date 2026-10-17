using System;
using System.Collections;
using System.Collections.Generic;
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
    /// 【纪律】
    ///   * **只读**：本技能绝不写玩家/世界状态（写操作在 `add_missed_recipes` 里，且单独回执）；
    ///   * 表名与 `limit` 的判据全在 `DumpRules`（纯函数，自检工程可跑行为断言）；
    ///   * **不许**把整张表无界塞进回执：`limit` 默认 200 / 上限 2000，`truncated` 如实报；
    ///   * fail-closed：不认识的表 ⇒ `table_unknown`（reason 列出支持的表）；
    ///     读表抛异常 ⇒ `load_failed`（异常原文进 reason，不许猜）；
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

        /// <summary>规范表名 → 资产名（`Game1.content.Load` 的 asset）。</summary>
        private static readonly Dictionary<string, string> Assets = new Dictionary<string, string>
        {
            ["crafting_recipes"] = "Data/CraftingRecipes",
            ["cooking_recipes"] = "Data/CookingRecipes",
            ["trigger_actions"] = "Data/TriggerActions",
            ["mail"] = "Data/Mail",
            ["machines"] = "Data/Machines",
            ["objects"] = "Data/Objects",
            ["big_craftables"] = "Data/BigCraftables",
        };

        /// <summary>复杂表的游戏数据值类型简单名（在 StardewValley 程序集里按名字解析）。</summary>
        private static readonly Dictionary<string, string[]> ComplexValueTypes = new Dictionary<string, string[]>
        {
            ["machines"] = new[] { "MachineData" },
            ["objects"] = new[] { "ObjectData" },
            ["big_craftables"] = new[] { "BigCraftableData" },
            ["trigger_actions"] = new[] { "TriggerActionData" },
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

        private ExecResponse Fail(string status, string reason)
            => new ExecResponse
            {
                Ok = false,
                Status = status,
                Skill = "debug_dump",
                Reason = reason,
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
            if (!DumpRules.IsKnownTable(table))
            {
                return this.Fail("table_unknown",
                    "不支持的数据表 " + Describe(raw) + "；支持的表：" + string.Join(", ", DumpRules.Tables));
            }

            string asset = Assets[table];
            int limit = DumpRules.ClampLimit(this._req != null && this._req.Args != null
                ? this._req.Args.Limit : (int?)null);
            string wanted = this._req != null && this._req.Args != null ? this._req.Args.Key : null;

            IDictionary data;
            string loadNote = "";
            try
            {
                data = LoadTableDetail(table, asset, out loadNote);
            }
            catch (Exception ex)
            {
                Exception inner = Unwrap(ex);
                return this.Fail("load_failed",
                    "读 " + asset + " 失败：" + inner.GetType().Name + ": " + inner.Message
                    + (string.IsNullOrEmpty(loadNote) ? "" : "；" + loadNote));
            }
            if (data == null)
                return this.Fail("load_failed", "读 " + asset + " 返回 null（游戏没有加载这张表？）"
                    + (string.IsNullOrEmpty(loadNote) ? "" : "；" + loadNote));

            var all = new List<KeyValuePair<string, string>>();
            foreach (DictionaryEntry entry in data)
            {
                string key;
                try { key = Convert.ToString(entry.Key, System.Globalization.CultureInfo.InvariantCulture) ?? ""; }
                catch { key = ""; }
                all.Add(new KeyValuePair<string, string>(key, DumpRules.Describe(entry.Value)));
            }
            all.Sort((a, b) => string.CompareOrdinal(a.Key, b.Key));

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
                var matched = exact.Count > 0 ? exact : fuzzy;
                int cap = Math.Min(matched.Count, Math.Min(limit, DumpRules.MatchMax));
                resp.MatchMode = mode;
                resp.Matched = matched.GetRange(0, cap).ToArray();
                resp.MatchedCount = matched.Count;
                resp.MatchedTruncated = matched.Count > cap;
                resp.Entries = new string[0][];
                resp.Truncated = false;
                resp.Reason = matched.Count == 0
                    ? "表 " + table + " 里没有匹配 " + Describe(wanted) + " 的 key（精确与子串都没有）"
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
            resp.Reason = "表 " + table + " 共 " + all.Count + " 条"
                          + (resp.Truncated == true ? "（按 limit=" + limit + " 只回前 " + take + " 条）" : "（全部返回）");
            return resp;
        }

        /// <summary>按表名读数据；复杂表先在游戏程序集里按简单名解析值类型，解析不到再退回字符串表。</summary>
        private static IDictionary LoadTableDetail(string table, string asset, out string note)
        {
            note = "";
            if (!ComplexValueTypes.TryGetValue(table, out string[] valueTypeNames))
                return LoadDictionary(asset, typeof(string));

            foreach (string simpleName in valueTypeNames)
            {
                Type valueType = ResolveGameType(simpleName);
                if (valueType == null)
                {
                    note = "程序集里找不到 " + simpleName + " 类型";
                    continue;
                }
                try
                {
                    return LoadDictionary(asset, valueType);
                }
                catch (Exception ex)
                {
                    note = "按 " + valueType.FullName + " 读失败：" + Unwrap(ex).GetType().Name
                           + ": " + Unwrap(ex).Message;
                }
            }
            // 兜底：有些版本把这些表暴露成 Dictionary<string,string>（读到就可用，读不到就抛）。
            return LoadDictionary(asset, typeof(string));
        }

        private static IDictionary LoadDictionary(string asset, Type valueType)
        {
            MethodInfo method = FindLoadMethod();
            if (method == null)
                throw new MissingMethodException("Game1.content 上找不到单参泛型 Load<T>(string)（游戏版本不支持内省读表）");
            Type dictType = typeof(Dictionary<,>).MakeGenericType(typeof(string), valueType);
            object result = method.MakeGenericMethod(dictType).Invoke(Game1.content, new object[] { asset });
            if (result is IDictionary dict) return dict;
            throw new InvalidCastException("Load 返回的不是字典：" + (result == null ? "null" : result.GetType().FullName));
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

        /// <summary>在游戏程序集里按**类型简单名**解析（命名空间在各版本间不稳定，不写死全名）。</summary>
        private static Type ResolveGameType(string simpleName)
        {
            try
            {
                Assembly asm = typeof(Game1).Assembly;
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
                // 解析失败 ⇒ 调用方按"读不了"处理（fail-closed）
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
