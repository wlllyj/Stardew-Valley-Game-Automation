using System;
using System.Collections.Generic;
using System.Reflection;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-213】`add_missed_recipes`：调**游戏自己的补发入口**
    /// `Farmer.AddMissedMailAndRecipes()`，并把**前后差分**如实写进回执。
    ///
    /// 【为什么需要它（本卡的真实动机）】Furnace 配方缺失是铁匠铺升级链的硬阻塞。
    /// log-analyst 的 task-212 定案（`docs\_il-furnace-recipe.md`）：唯一合法的授予通道是
    /// 「玩家技能升级时构造 `LevelUpMenu` → `AddMissedMailAndRecipes()`」；
    /// `LearnDefaultRecipes` 每日只给默认配方（Furnace 不在其中）；
    /// 而我们的自动化**从未构造过 LevelUpMenu** ⇒ 配方没被补发。
    /// 条件串在打包 xnb 里读不到 ⇒ 必须真机跑一次内省 + 补发来一锤定音。
    ///
    /// 【纪律（与卡面逐字对齐）】
    ///   * **会真的写玩家字典**（游戏自己的补发逻辑，允许）：所以回执必须如实列出
    ///     `crafting_recipes_added` / `cooking_recipes_added` / `mail_added` 与前后计数；
    ///   * **只准调用一次/次**：绝不循环调用（循环调游戏补发逻辑是最容易出事的那种写法）；
    ///   * 方法不存在（游戏版本没有这个通道）⇒ `not_available`，**不许猜替代**（不自己写表）；
    ///   * 调用抛异常 ⇒ `error`，异常原文进 reason（回执里同时报"已经调过、可能写了一半"）。
    ///
    /// 【单 tick 同步技能】不加入 `BridgeHost.IsLongTaskSkill`。
    /// </summary>
    internal sealed class AddMissedRecipesSkill
    {
        private readonly ExecRequest _req;
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;

        private long _seqBefore;

        public AddMissedRecipesSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
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
                Skill = "add_missed_recipes",
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

            Farmer player = Game1.player;
            if (player == null)
                return this.Fail("no_save", "当前没有存档（Game1.player == null）：补发配方必须先读档");

            MethodInfo method = typeof(Farmer).GetMethod(
                "AddMissedMailAndRecipes",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (method == null)
            {
                return this.Fail("not_available",
                    "StardewValley.Farmer 上不存在 AddMissedMailAndRecipes()（当前游戏版本没有这个补发通道）；"
                    + "**没有**调用任何补发逻辑、没有改玩家数据");
            }

            Snapshot<HashSet<string>> craftingBefore = SafeKeys(() => player.craftingRecipes.Keys);
            Snapshot<HashSet<string>> cookingBefore = SafeKeys(() => player.cookingRecipes.Keys);
            Snapshot<HashSet<string>> mailBefore = SafeKeys(() => player.mailReceived);
            var beforeCounts = new Dictionary<string, int>
            {
                ["crafting_recipes"] = craftingBefore.Values.Count,
                ["cooking_recipes"] = cookingBefore.Values.Count,
                ["mail"] = mailBefore.Values.Count,
            };
            if (!string.IsNullOrEmpty(craftingBefore.Error) || !string.IsNullOrEmpty(cookingBefore.Error)
                || !string.IsNullOrEmpty(mailBefore.Error))
            {
                return this.Fail("load_failed",
                    "读玩家字典失败（防止「补发前后差分为空」误判成「没补发」）："
                    + FirstError(craftingBefore.Error, cookingBefore.Error, mailBefore.Error)
                    + "；**没有**调用补发逻辑");
            }

            string invokeError = "";
            try
            {
                // 【只调一次】卡面硬要求：绝不循环调用游戏自己的补发逻辑。
                method.Invoke(player, null);
            }
            catch (Exception ex)
            {
                Exception inner = ex is TargetInvocationException tie && tie.InnerException != null
                    ? tie.InnerException : ex;
                invokeError = inner.GetType().Name + ": " + inner.Message;
            }

            Snapshot<HashSet<string>> craftingAfter = SafeKeys(() => player.craftingRecipes.Keys);
            Snapshot<HashSet<string>> cookingAfter = SafeKeys(() => player.cookingRecipes.Keys);
            Snapshot<HashSet<string>> mailAfter = SafeKeys(() => player.mailReceived);
            var afterCounts = new Dictionary<string, int>
            {
                ["crafting_recipes"] = craftingAfter.Values.Count,
                ["cooking_recipes"] = cookingAfter.Values.Count,
                ["mail"] = mailAfter.Values.Count,
            };

            List<string> craftingAdded = DumpRules.DiffAdded(craftingBefore.Values, craftingAfter.Values);
            List<string> cookingAdded = DumpRules.DiffAdded(cookingBefore.Values, cookingAfter.Values);
            List<string> mailAdded = DumpRules.DiffAdded(mailBefore.Values, mailAfter.Values);

            var resp = new ExecResponse
            {
                Ok = invokeError.Length == 0,
                Status = invokeError.Length == 0 ? "ok" : "error",
                Skill = "add_missed_recipes",
                Schema = Skills.ExecSchema,
                ElapsedMs = 0,
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world != null ? this._world.WorldSeq : this._seqBefore,
                CraftingRecipesAdded = craftingAdded.ToArray(),
                CookingRecipesAdded = cookingAdded.ToArray(),
                MailAdded = mailAdded.ToArray(),
                BeforeCounts = beforeCounts,
                AfterCounts = afterCounts,
            };
            int totalAdded = craftingAdded.Count + cookingAdded.Count + mailAdded.Count;
            resp.Reason = invokeError.Length == 0
                ? "已调用一次 Farmer.AddMissedMailAndRecipes()：crafting +" + craftingAdded.Count
                  + "、cooking +" + cookingAdded.Count + "、mail +" + mailAdded.Count
                  + "（共 " + totalAdded + " 条；前后计数见 beforeCounts/afterCounts）"
                : "调用 AddMissedMailAndRecipes() 抛异常：" + invokeError
                  + "（**可能已写了一半**：crafting +" + craftingAdded.Count
                  + "、cooking +" + cookingAdded.Count + "、mail +" + mailAdded.Count + "）";
            return resp;
        }

        private static string FirstError(params string[] errors)
        {
            foreach (string e in errors)
                if (!string.IsNullOrEmpty(e)) return e;
            return "";
        }

        /// <summary>快照 + 错误信息（读不到时**不许**当空集合，否则"没补发"会被误判）。</summary>
        private sealed class Snapshot<T>
        {
            public T Values;
            public string Error = "";
        }

        /// <summary>
        /// 只快照**键集合**：`player.craftingRecipes` / `cookingRecipes` 是
        /// `NetStringDictionary&lt;int, NetInt&gt;`、`mailReceived` 是 `NetStringHashSet`，
        /// 它们都不是普通 `Dictionary&lt;string,string&gt;`；补发判据只需要"有哪些键"。
        /// </summary>
        private static Snapshot<HashSet<string>> SafeKeys(Func<IEnumerable<string>> get)
        {
            var values = new HashSet<string>(StringComparer.Ordinal);
            var snap = new Snapshot<HashSet<string>> { Values = values };
            try
            {
                IEnumerable<string> src = get();
                if (src != null)
                    foreach (string k in src)
                        if (k != null) values.Add(k);
                return snap;
            }
            catch (Exception ex)
            {
                snap.Error = ex.GetType().Name + ": " + ex.Message;
                return snap;
            }
        }
    }
}
