using System;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-42】`sell`：把**白名单内**的一格背包物品放进**出货箱**（用户 m08335："怎么到现在一分钱也没挣到呀？"）。
    ///
    /// ==================================================================
    /// 【纪律：钱只能由游戏自己动】
    /// 与 `buy` 同一条硬规矩（v0.7.17"种子不扣"事故的教训）：**绝不自己写 `Money +=`**。
    /// 这里只调游戏自己的 <c>Farm.shipItem(Item, Farmer)</c>；钱由**下一次 `NewDay`** 结算
    /// （`Game1._newDayAfterFade`：`player.Money = player.Money + total`）。
    /// 所以本技能的判据**不是**钱变了（当天根本不会变），而是 **"那件东西真的离开背包了"**
    /// —— 唯一客观、当帧可见的差分。
    ///
    /// 【证据链（docs/_il-sell-path.md，1.6.15）】
    ///   `Farm.shipItem(Item i, Farmer who)`（public）：
    ///     `if (i == null) return;` → `who.removeItemFromInventory(i)` →
    ///     `this.getShippingBin(who).Add(i)` → `this.showShipment(i, false)` →
    ///     `this.lastItemShipped = i;` → `if (Game1.player.ActiveItem == null) { showNotCarrying(); Halt(); }`
    ///   结算在 `_newDayAfterFade`：`bin.RemoveEmptySlots()` → 每件进 `player.displayedShippedItems` →
    ///   只累加 `Object`（`obj.sellToStorePrice(-1) * obj.Stack`，**非 Object 计 0 钱**）→
    ///   `player.Money = player.Money + total` → 入账后才 `getShippingBin(player).Clear()`。
    ///
    /// 【三个必须记住的坑】
    ///   ① **必须传背包里那个实例**：`Farmer.removeItemFromInventory` 用 `Items.IndexOf(which)`
    ///      （**引用相等**）。传 `getOne()` 副本会变成"原物不动、副本进箱"，次日多拿一份钱。
    ///      这就是为什么脑侧必须下发**槽位**、Mod 侧必须取 `Game1.player.Items[slot]`。
    ///   ② **没有"卖一部分"的能力**：`shipItem` 拿走的是整件（整叠）。想留一半就别卖这一格。
    ///   ③ **有副作用**：`showShipment` 播动画 + `Halt()`（停下玩家）。无人值守时无害，
    ///      但脑侧必须知道"这一步会打断当前动作"。
    ///
    /// 【只做允许列表】`args.sellWhitelist` 为空 ⇒ 直接拒绝（一件都不卖）。脑侧只把
    /// `harvest()` 当天亲眼见过"进了背包"的 qualifiedId 放进来；**绝不**做"除了工具都能卖"的
    /// 黑名单 —— 那种判据一旦上游有 bug，种子/工具/任务物品都会被卖掉。
    ///
    /// 【U2 待真机探针】非 Farm 地点调 `shipItem` 是否安全：IL 里没有方位判据（箱子对象直接从
    /// `Game1.getFarm()` 拿），所以本技能**不**按地点拒绝，但把当时地点写进 reason 供审计。
    ///
    /// 【单 tick 同步技能】不加入 `BridgeHost.IsLongTaskSkill`：`shipItem` 一次调用即完成，
    /// 不需要跨 tick 等待（与 `buy` 不同，后者要等商店菜单挂上）。
    /// ==================================================================
    /// </summary>
    internal sealed class ShipSkill
    {
        private readonly ExecRequest _req;
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;

        private bool _started;
        private bool _done;
        private DateTime _startedAtUtc;
        private long _seqBefore;

        public ShipSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._req = req;
            this._world = world;
            this._monitor = monitor;
        }

        private long Elapsed() => this._started ? (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds : 0;

        private ExecResponse Fail(string status, string reason)
            => new ExecResponse
            {
                Ok = false, Status = status, Skill = "sell", Reason = reason,
                Schema = Skills.ExecSchema, ElapsedMs = this.Elapsed(),
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };

        private static string NameOf(Item it)
        {
            try { return it.DisplayName ?? it.Name ?? "?"; }
            catch { return "?"; }
        }

        private static string QidOf(Item it)
        {
            try { return it.QualifiedItemId ?? ""; }
            catch { return ""; }
        }

        /// <summary>主线程调用：单 tick 技能，返回的永远是终态（不会返回 null）。</summary>
        public object Step()
        {
            if (this._done)
                return this.Fail("error", "sell 是一次性单 tick 技能：同一请求不许重复执行");
            this._done = true;

            if (!Context.IsWorldReady || Game1.player == null)
                return this.Fail("no_save", "尚未加载存档，无法执行 sell");

            this._started = true;
            this._startedAtUtc = DateTime.UtcNow;
            this._seqBefore = this._world?.WorldSeq ?? 0;

            // ---- 参数 ----
            int? slotArg = this._req?.Args?.Slot;
            if (slotArg == null || slotArg.Value < 0)
                return this.Fail("bad_args",
                    "缺少参数 args.slot（要出货的背包槽位下标；0 起的整数）。"
                    + "为什么必须是槽位：`shipItem` 内部用引用相等找物品，只有槽位能无歧义指认那一件");

            int slot = slotArg.Value;
            var items = Game1.player.Items;
            if (items == null || slot >= items.Count)
                return this.Fail("bad_args",
                    $"槽位 {slot} 超出背包范围（当前共 {items?.Count ?? 0} 格）");

            Item item = items[slot];
            if (item == null)
                return this.Fail("empty_slot", $"背包槽位 {slot} 是空的，没有东西可出货");

            string qid = QidOf(item);

            // ---- 白名单（允许列表；空 = 一件都不卖）----
            string[] allow = this._req?.Args?.SellWhitelist;
            if (allow == null || allow.Length == 0)
                return this.Fail("not_whitelisted",
                    "脑侧没给白名单（`args.sellWhitelist` 为空）⇒ 一件都不卖。"
                    + "出货只做允许列表（脑侧把 `harvest()` 当天亲眼收获的 qualifiedId 放进来），"
                    + "绝不做“除工具以外都能卖”的黑名单");

            bool listed = false;
            foreach (string a in allow)
            {
                if (!string.IsNullOrEmpty(a)
                    && string.Equals(a.Trim(), qid, StringComparison.OrdinalIgnoreCase))
                {
                    listed = true;
                    break;
                }
            }
            if (!listed)
                return this.Fail("not_whitelisted",
                    $"槽位 {slot} 的 {qid}（{NameOf(item)}）不在脑侧白名单里"
                    + $"（白名单：{string.Join("、", allow)}）⇒ 不卖");

            // ---- 可卖性（按 docs/_il-sell-path.md §6 的 10 步伪代码）----
            StardewValley.Object obj = item as StardewValley.Object;
            if (obj == null)
                return this.Fail("not_sellable",
                    $"槽位 {slot} 的 {qid}（{NameOf(item)}）不是 Object（{item.GetType().Name}）"
                    + "⇒ 出货箱结算只累加 Object，非 Object 计 0 钱");

            try
            {
                if (obj.questItem.Value)
                    return this.Fail("quest_item", $"槽位 {slot} 的 {qid}（{NameOf(item)}）是任务物品 ⇒ 不卖");
            }
            catch { }

            try
            {
                if (obj.bigCraftable.Value)
                    return this.Fail("big_craftable", $"槽位 {slot} 的 {qid}（{NameOf(item)}）是大件制造物 ⇒ 不卖");
            }
            catch { }

            if (item.Stack <= 0)
                return this.Fail("empty_stack", $"槽位 {slot} 的 {qid}（{NameOf(item)}）堆叠为 {item.Stack} ⇒ 不卖");

            // ---- 观测差分：前 ----
            int stack = item.Stack;
            int binBefore = -1;
            long moneyBefore = -1;
            try
            {
                var bin0 = Game1.getFarm()?.getShippingBin(Game1.player);
                binBefore = bin0?.Count ?? -1;
            }
            catch { }
            try { moneyBefore = Game1.player.Money; } catch { }

            // ---- ★ 只调游戏自己的出货函数（Mod 绝不碰钱/不碰箱子）----
            try
            {
                Farm farm = Game1.getFarm();
                if (farm == null)
                    return this.Fail("error", "Game1.getFarm() 返回 null，拿不到出货箱（不过这会儿应该不可能）");
                farm.shipItem(item, Game1.player);
            }
            catch (Exception ex)
            {
                return this.Fail("error",
                    $"调用 Farm.shipItem 抛异常：{ex.GetType().Name}: {ex.Message}"
                    + $"（槽位 {slot} 的 {qid}×{stack}；Mod 没有做任何补救，物品状态由游戏决定）");
            }

            // ---- 判据 = 观测差分（槽位空没空 + 箱子件数 + lastItemShipped）----
            bool slotEmpty = false;
            try { slotEmpty = Game1.player.Items[slot] == null; } catch { }
            int binAfter = -1;
            long moneyAfter = -1;
            string last = "";
            try
            {
                var bin1 = Game1.getFarm()?.getShippingBin(Game1.player);
                binAfter = bin1?.Count ?? -1;
            }
            catch { }
            try { moneyAfter = Game1.player.Money; } catch { }
            try { last = Game1.getFarm()?.lastItemShipped?.QualifiedItemId ?? ""; } catch { }

            string where = StepMover.CurrentLocationName() ?? "（读不到）";
            string fact = $"箱子 {binBefore}→{binAfter} 件，lastItemShipped={last}，"
                        + $"钱 {moneyBefore}g→{moneyAfter}g（**当期不会变**：下一次 NewDay 才结算），当前地点 {where}";

            if (!slotEmpty)
            {
                try { this._monitor?.Log($"sell：调了 shipItem 但槽位 {slot} 仍有物品（{QidOf(Game1.player.Items[slot])}）"); }
                catch { }
                return this.Fail("sell_no_effect",
                    $"调了 Farm.shipItem，但背包槽位 {slot} 还是有东西（{NameOf(item)}×{stack}）⇒ 不算成功："
                    + fact);
            }

            return new ExecResponse
            {
                Ok = true,
                Status = "ok",
                Skill = "sell",
                Reason = $"已把槽位 {slot} 的 {qid}（{NameOf(item)}）×{stack} 放进出货箱：{fact}。"
                       + "⚠ 回执只是声明：钱与箱子内容请用 observe 复核（shippingBin.count / money）",
                Schema = Skills.ExecSchema,
                ElapsedMs = this.Elapsed(),
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = where,
            };
        }
    }
}
