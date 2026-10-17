using System;
using System.Collections.Generic;
using System.Reflection;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Internal;   // ShopBuilder
using StardewValley.Menus;      // ShopMenu
using StardewValley.Tools;      // Tool / Axe / Pickaxe / Hoe / WateringCan / Pan

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-205】铁匠铺升级链的 I/O 小工具：读玩家工具状态、读 `ClintUpgrade` 在售表、
    /// 调游戏自己的购买/取回入口。**判据本体**在 `ToolUpgradeRules`（纯函数、自检工程可跑）。
    ///
    /// 链路依据：`docs/_il-tool-upgrade.md`（task-204，`d6d55e2`）。四条硬事实：
    ///   1. 入口不用对话：`Utility.TryOpenShopMenu("ClintUpgrade", "Clint", true)`（public static）；
    ///   2. 不开店就能读价/材料：`ShopBuilder.GetShopStock("ClintUpgrade")`（public static）；
    ///   3. **白扣钱陷阱**：`tryToPurchaseItem` 先扣钱+扣锭，再 `actionWhenPurchased`；
    ///      后者见"已在升级"直接 false **且不回滚** ⇒ 买前必须堵 `toolBeingUpgraded != null`；
    ///   4. **电话查价店 `readOnly == true`**：那里买东西只扣钱不升级 ⇒ 买前必须断言 `readOnly == false`。
    /// </summary>
    internal static class ToolUpgradeIo
    {
        internal const string ShopId = "ClintUpgrade";
        internal const string ShopOwner = "Clint";
        internal const string BlacksmithLocation = "Blacksmith";

        /// <summary>钩 `Tool.UpgradeLevel`（0 = 初始）。读不到 ⇒ -1。</summary>
        internal static int TierOf(Tool tool)
        {
            if (tool == null) return -1;
            try { return tool.UpgradeLevel; } catch { return -1; }
        }

        /// <summary>`actionWhenPurchased` 只认这五类（IL §2.2）：斧/镐/锄/壶/淘金盘。镰刀不在其中。</summary>
        internal static bool IsUpgradableKind(string kind)
        {
            string k = ToolUpgradeRules.NormalizeKind(kind);
            return k == "axe" || k == "pickaxe" || k == "hoe" || k == "can" || k == "pan";
        }

        /// <summary>工具种类（与 `WorldSnapshot` 的 `tools[].kind` 同口径）。</summary>
        internal static string KindOf(Item item)
        {
            if (item is Axe) return "axe";
            if (item is Pickaxe) return "pickaxe";
            if (item is Hoe) return "hoe";
            if (item is WateringCan) return "can";
            if (item is Pan) return "pan";
            if (item is FishingRod) return "fishingRod";
            if (item is MeleeWeapon) return "other";
            return item is Tool ? "tool" : null;
        }

        /// <summary>在背包里按种类找工具（升级店要求目标工具**在背包里**才有条目：IL §3.0-2）。</summary>
        internal static Tool FindTool(Farmer p, string kind)
        {
            if (p?.Items == null) return null;
            foreach (Item item in p.Items)
            {
                if (item is Tool t && ToolUpgradeRules.SameKind(KindOf(item), kind)) return t;
            }
            return null;
        }

        /// <summary>背包里某个 QualifiedItemId 的总数量（锭：`(O)334` 等）。</summary>
        internal static int CountItem(Farmer p, string qualifiedId)
        {
            if (p?.Items == null || string.IsNullOrEmpty(qualifiedId)) return 0;
            int n = 0;
            foreach (Item item in p.Items)
            {
                if (item == null) continue;
                try
                {
                    if (string.Equals(item.QualifiedItemId, qualifiedId, StringComparison.OrdinalIgnoreCase))
                        n += Math.Max(0, item.Stack);
                }
                catch { }
            }
            return n;
        }

        /// <summary>背包空格数：优先游戏自己的 `freeSpotsInInventory()`，读不到就数空位。</summary>
        internal static int FreeSlots(Farmer p)
        {
            if (p == null) return 0;
            try { return p.freeSpotsInInventory(); } catch { }
            try
            {
                int free = 0;
                if (p.Items != null)
                {
                    foreach (Item item in p.Items) if (item == null) free++;
                }
                return free;
            }
            catch { return 0; }
        }

        /// <summary>`ShopMenu.readOnly`（电话查价路径 = true）。反射读，免得依赖可见性。</summary>
        internal static bool? ReadOnly(ShopMenu menu)
        {
            if (menu == null) return null;
            try
            {
                FieldInfo f = typeof(ShopMenu).GetField(
                    "readOnly", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (f == null) return null;
                object v = f.GetValue(menu);
                return v is bool b ? b : (bool?)null;
            }
            catch { return null; }
        }

        internal static string SafeId(ISalable s)
        {
            try
            {
                if (s is Item it)
                {
                    if (!string.IsNullOrEmpty(it.QualifiedItemId)) return it.QualifiedItemId;
                    if (!string.IsNullOrEmpty(it.ItemId)) return it.ItemId;
                }
                return s?.Name;
            }
            catch { return null; }
        }

        internal static string SafeName(ISalable s)
        {
            try { return s?.DisplayName ?? s?.Name; } catch { return null; }
        }

        /// <summary>
        /// 不开店读 `ClintUpgrade` 的在售表（`ShopBuilder.GetShopStock`，public static）。
        /// `null` = 读不到（Fail-closed 由调用方处理）。
        /// </summary>
        internal static Dictionary<ISalable, ItemStockInformation> ReadStock(out string note)
        {
            note = "(未读)";
            try
            {
                Dictionary<ISalable, ItemStockInformation> stock = ShopBuilder.GetShopStock(ShopId);
                note = stock == null ? "ShopBuilder.GetShopStock 返回 null" : $"在售 {stock.Count} 条";
                return stock;
            }
            catch (Exception ex)
            {
                note = "ShopBuilder.GetShopStock 异常：" + ex.GetType().Name + ": " + ex.Message;
                return null;
            }
        }

        /// <summary>把 `Dictionary<ISalable, ItemStockInformation>` 映射成纯值条目（给判据用）。</summary>
        internal static List<UpgradeOfferInput> ToOffers(
            IDictionary<ISalable, ItemStockInformation> stock, out List<ISalable> keys)
        {
            var rows = new List<UpgradeOfferInput>();
            keys = new List<ISalable>();
            if (stock == null) return rows;
            foreach (KeyValuePair<ISalable, ItemStockInformation> kv in stock)
            {
                ISalable key = kv.Key;
                Tool tool = key as Tool;
                if (tool == null) continue;      // 升级店里只认工具条目；其它（理论上没有）跳过
                ItemStockInformation info = kv.Value;
                rows.Add(new UpgradeOfferInput(
                    SafeId(key), SafeName(key), KindOf(tool), TierOf(tool),
                    info?.Price ?? 0, info?.TradeItem, info?.TradeItemCount ?? 0, info?.Stock ?? 0));
                keys.Add(key);
            }
            return rows;
        }

        /// <summary>
        /// U2 兜底：主匹配（kind + tier+1）找不到时，用 `ShopBuilder.GetToolUpgradeData` 反查
        /// 期望的 `Price` / `TradeItemId`，再按"价格+材料"匹配条目。
        ///
        /// 全程反射：`GetToolUpgradeData` 的参数类型（`ToolData`）与返回类型的属性名在
        /// 1.6.15 里没有编译期实证，不能硬写（编译失败会挡住整个 Mod）。
        /// </summary>
        internal static int MatchByExpectedData(
            List<UpgradeOfferInput> offers, Farmer p, Tool tool, out string note)
        {
            note = "(未尝试)";
            if (offers == null || tool == null) return -1;
            try
            {
                MethodInfo getData = typeof(Tool).GetMethod("GetToolData",
                    BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (getData == null) { note = "找不到 Tool.GetToolData()"; return -1; }
                object data = getData.Invoke(tool, null);

                MethodInfo getUpgrade = null;
                foreach (MethodInfo mi in typeof(ShopBuilder).GetMethods(BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic))
                {
                    if (mi.Name != "GetToolUpgradeData") continue;
                    ParameterInfo[] ps = mi.GetParameters();
                    if (ps.Length == 2) { getUpgrade = mi; break; }
                }
                if (getUpgrade == null) { note = "找不到 ShopBuilder.GetToolUpgradeData(ToolData, Farmer)"; return -1; }
                object expected = getUpgrade.Invoke(null, new object[] { data, p });
                if (expected == null) { note = "GetToolUpgradeData 返回 null"; return -1; }

                int price = ReadIntProperty(expected, "Price", -1);
                string trade = ReadStringProperty(expected, "TradeItemId") ?? ReadStringProperty(expected, "TradeItem");
                var hits = new List<int>();
                for (int i = 0; i < offers.Count; i++)
                {
                    if (price >= 0 && offers[i].Price != price) continue;
                    if (!string.IsNullOrEmpty(trade)
                        && !string.Equals(offers[i].TradeItem, trade, StringComparison.OrdinalIgnoreCase)) continue;
                    hits.Add(i);
                }
                note = $"GetToolUpgradeData ⇒ price={price}, trade={trade ?? "(无)"}；命中 {hits.Count} 条";
                return hits.Count == 1 ? hits[0] : -1;
            }
            catch (Exception ex)
            {
                note = "反查异常：" + (ex is TargetInvocationException tie && tie.InnerException != null
                    ? tie.InnerException.GetType().Name + ": " + tie.InnerException.Message
                    : ex.GetType().Name + ": " + ex.Message);
                return -1;
            }
        }

        private static int ReadIntProperty(object obj, string name, int fallback)
        {
            try
            {
                PropertyInfo pi = obj.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                object v = pi?.GetValue(obj);
                return v == null ? fallback : Convert.ToInt32(v);
            }
            catch { return fallback; }
        }

        private static string ReadStringProperty(object obj, string name)
        {
            try
            {
                PropertyInfo pi = obj.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                return pi?.GetValue(obj)?.ToString();
            }
            catch { return null; }
        }

        /// <summary>
        /// 反射调 `ShopMenu.tryToPurchaseItem(item, null, 1, 0, 0)`（private；先例 `BuySkill.TryPurchase`）。
        /// `held_item = null` 是关键：只有 null 才走"直接购买"那条路（IL_0017）。
        /// </summary>
        internal static bool TryPurchase(ShopMenu menu, ISalable item, out string note)
        {
            try
            {
                MethodInfo mi = typeof(ShopMenu).GetMethod(
                    "tryToPurchaseItem", BindingFlags.Instance | BindingFlags.NonPublic);
                if (mi == null) { note = "找不到 ShopMenu.tryToPurchaseItem（私有）"; return false; }
                object ret = mi.Invoke(menu, new object[] { item, null, 1, 0, 0 });
                note = $"tryToPurchaseItem({SafeName(item)}, null, 1, 0, 0) → {ret}";
                return true;
            }
            catch (TargetInvocationException ex)
            {
                note = "tryToPurchaseItem 抛异常：" + (ex.InnerException ?? ex).GetType().Name
                     + ": " + (ex.InnerException ?? ex).Message;
                return false;
            }
            catch (Exception ex)
            {
                note = "反射调用 tryToPurchaseItem 异常：" + ex.GetType().Name + ": " + ex.Message;
                return false;
            }
        }

        /// <summary>
        /// 取回入口：`GameLocation.blacksmith(default)`（public；参数在 IL 层只被拿去比较朝向、不影响分支）。
        /// 必须在 Blacksmith 店内（该方法只认**当前地点 `characters` 里的 Clint**，找不到就静默 false）。
        /// </summary>
        internal static bool CallBlacksmith(out string note)
        {
            note = "(未调用)";
            try
            {
                MethodInfo mi = typeof(GameLocation).GetMethod(
                    "blacksmith", BindingFlags.Instance | BindingFlags.Public);
                if (mi == null) { note = "找不到 GameLocation.blacksmith"; return false; }
                ParameterInfo[] ps = mi.GetParameters();
                object arg = ps.Length == 0 ? null : Activator.CreateInstance(ps[0].ParameterType);
                object ret = ps.Length == 0 ? mi.Invoke(Game1.currentLocation, null)
                                           : mi.Invoke(Game1.currentLocation, new object[] { arg });
                note = $"GameLocation.blacksmith(...) → {ret}";
                return ret is bool b && b;
            }
            catch (TargetInvocationException ex)
            {
                note = "blacksmith 抛异常：" + (ex.InnerException ?? ex).GetType().Name
                     + ": " + (ex.InnerException ?? ex).Message;
                return false;
            }
            catch (Exception ex)
            {
                note = "反射调用 blacksmith 异常：" + ex.GetType().Name + ": " + ex.Message;
                return false;
            }
        }

        internal static string LocationName()
        {
            try { return Game1.currentLocation?.Name; } catch { return null; }
        }
    }

    /// <summary>
    /// 【task-205】`upgrade_tool`：在铁匠铺升级店买下某件工具的下一级。
    ///
    /// 流程（`docs/_il-tool-upgrade.md` §3.2）：
    ///   1. 预检：已在升级 / 还在做（daysLeft&gt;0）/ 目标工具在背包里 / 可升级种类；
    ///   2. 开店 `Utility.TryOpenShopMenu("ClintUpgrade", "Clint", true)`，等 `ShopMenu` 挂上（跨 tick）；
    ///   3. 在 `ShopMenu.itemPriceAndStock` 里选**唯一**条目（kind 相同 &amp; tier == 当前+1），
    ///      读它自己的 `Price` / `TradeItem` / `TradeItemCount`；
    ///   4. 自检（钱/锭/readOnly）—— 任何一项不过 ⇒ 关店 + fail-closed，**一个子都不扣**；
    ///   5. 反射 `tryToPurchaseItem(item, null, 1, 0, 0)`；
    ///   6. 判据 = 观测差分（钱差 / 锭差 / `toolBeingUpgraded` 出现），回执只是声明。
    ///
    /// ⚠️ 等级在**买下时**就换了（`toolBeingUpgraded` = 升级后的副本、`daysLeft = 2`、旧工具离包）；
    /// 取回是**另一件事**（`pickup_tool`）。
    /// </summary>
    internal sealed class ToolUpgradeSkill
    {
        private readonly ExecRequest _req;
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly int _timeoutMs;

        private bool _started;
        private DateTime _startedAtUtc;
        private long _seqBefore;

        private Tool _tool;
        private string _kind;
        private int _tierBefore;
        private int _moneyBefore;
        private int _tradeHaveBefore;
        private List<UpgradeOfferInput> _preOffers;
        private int _prePick = -1;
        private string _preNote = "";
        private UpgradeOfferView[] _rows;

        public ToolUpgradeSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._req = req;
            this._world = world;
            this._monitor = monitor;
            this._timeoutMs = Skills.ClampTimeoutFor("upgrade_tool", req?.TimeoutMs);
        }

        private long Elapsed() => (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds;

        private ExecResponse Respond(bool ok, string status, string reason)
        {
            UpgradeOfferView[] rows = this._rows;
            int? daysLeft = null;
            string beingUpgraded = null;
            try
            {
                daysLeft = Game1.player?.daysLeftForToolUpgrade?.Value;
                beingUpgraded = Game1.player?.toolBeingUpgraded?.Value?.DisplayName;
            }
            catch { }
            return new ExecResponse
            {
                Ok = ok,
                Status = status,
                Skill = "upgrade_tool",
                Reason = reason,
                Schema = Skills.ExecSchema,
                ElapsedMs = this.Elapsed(),
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
                Tool = this._kind,
                TierBefore = this._tierBefore >= 0 ? this._tierBefore : (int?)null,
                ToolBeingUpgraded = beingUpgraded,
                DaysLeft = daysLeft,
                Offers = rows,
            };
        }

        private ExecResponse Fail(string status, string reason) => this.Respond(false, status, reason);

        public object Step()
        {
            long seq = 0;
            try { seq = this._world?.WorldSeq ?? 0; } catch { }

            if (!Context.IsWorldReady || Game1.player == null)
                return this.Fail("no_save", "尚未加载存档，无法 upgrade_tool");

            Farmer p = Game1.player;

            if (!this._started)
            {
                this._started = true;
                this._startedAtUtc = DateTime.UtcNow;
                this._seqBefore = seq;

                string kind = (this._req?.Args?.Tool ?? "").Trim();
                if (string.IsNullOrEmpty(kind))
                    return this.Fail("bad_args", "upgrade_tool 需要 args.tool（axe|pickaxe|hoe|can|pan）");
                this._kind = ToolUpgradeRules.NormalizeKind(kind);
                if (!ToolUpgradeIo.IsUpgradableKind(this._kind))
                    return this.Fail(ToolUpgradeRules.StatusToolNotOffered,
                        $"「{kind}」不能升级：`Tool.actionWhenPurchased` 只认 斧/镐/锄/壶/淘金盘 五类（IL §2.2）");

                this._tool = ToolUpgradeIo.FindTool(p, this._kind);
                if (this._tool == null)
                    return this.Fail(ToolUpgradeRules.StatusToolMissing,
                        $"背包里没有「{this._kind}」这件工具 —— 升级店只给「背包里现有的工具」出条目（IL §3.0-2）");
                this._tierBefore = ToolUpgradeIo.TierOf(this._tool);

                // ---- 玩家状态预检（白扣钱陷阱：已在升级时买 = 钱和锭白丢，IL §2.2） ----
                bool already;
                int daysLeft;
                try
                {
                    already = p.toolBeingUpgraded?.Value != null;
                    daysLeft = p.daysLeftForToolUpgrade?.Value ?? 0;
                }
                catch { already = false; daysLeft = 0; }
                string pre = ToolUpgradeRules.Precheck(
                    new UpgradePrecheck(already, daysLeft, ToolUpgradeIo.FreeSlots(p), false,
                                        p.Money, 0, 0, 0), requireFreeSlot: false);
                if (pre == ToolUpgradeRules.StatusAlreadyUpgrading)
                    return this.Fail(pre, "已经有工具在 Clint 那里升级（toolBeingUpgraded != null）。"
                        + "此时买 = 钱和 5 条锭当场扣掉、工具不升级（tryToPurchaseItem 先扣钱再 actionWhenPurchased）"
                        + $"；等在途那把取回再来。在途：{SafeBeingUpgraded(p)}");
                if (pre == ToolUpgradeRules.StatusStillWorking)
                    return this.Fail(pre, $"还在升级中（daysLeftForToolUpgrade={daysLeft}）；先等它做完再来");

                // ---- 不开店先试读在售表（只用于"条目存不存在"的早期判断与失败回执） ----
                string stockNote;
                Dictionary<ISalable, ItemStockInformation> stock = ToolUpgradeIo.ReadStock(out stockNote);
                List<ISalable> keys;
                this._preOffers = ToolUpgradeIo.ToOffers(stock, out keys);
                this._rows = OfferRows(this._preOffers);
                UpgradePickResult prePick = ToolUpgradeRules.Select(this._preOffers, this._kind, this._tierBefore);
                this._prePick = prePick.Index;
                this._preNote = prePick.Note;
                if (prePick.Index < 0)
                {
                    // U2 兜底：条目上的 UpgradeLevel 语义未定 ⇒ 用 GetToolUpgradeData 反查价格+材料
                    int alt = ToolUpgradeIo.MatchByExpectedData(this._preOffers, p, this._tool, out string altNote);
                    if (alt < 0)
                        return this.Fail(prePick.Status, prePick.Note + $"（预读：{stockNote}；反查：{altNote}）");
                    this._prePick = alt;
                    this._preNote = $"主匹配失败，按 GetToolUpgradeData 反查命中：{altNote}";
                }
            }

            // ---- 开店（跨 tick 等菜单） ----
            ShopMenu menu = Game1.activeClickableMenu as ShopMenu;
            if (menu == null)
            {
                bool opened = false;
                string why = null;
                try { opened = Utility.TryOpenShopMenu(ToolUpgradeIo.ShopId, ToolUpgradeIo.ShopOwner, true); }
                catch (Exception ex) { why = ex.GetType().Name + ": " + ex.Message; }
                if (!opened)
                    return this.Fail(ToolUpgradeRules.StatusShopUnavailable,
                        $"Utility.TryOpenShopMenu(\"{ToolUpgradeIo.ShopId}\", \"{ToolUpgradeIo.ShopOwner}\", true) 返回 false"
                        + (why == null ? "" : $"（异常：{why}）")
                        + $"；当前地点 {ToolUpgradeIo.LocationName()}，timeOfDay={Game1.timeOfDay}"
                        + "。可能原因：Data/Shops 没有该 id / 世界没准备好");
                menu = Game1.activeClickableMenu as ShopMenu;
                if (menu == null)
                {
                    if (this.Elapsed() > this._timeoutMs)
                        return this.Fail(ToolUpgradeRules.StatusShopUnavailable,
                            $"请求开店「{ToolUpgradeIo.ShopId}」后 {this.Elapsed()}ms 内没等到 ShopMenu"
                            + $"（activeMenu={Game1.activeClickableMenu?.GetType().Name ?? "(无)"}）");
                    return null;    // 等下一 tick
                }
            }

            // ---- readOnly 店：只扣钱不升级（电话查价路径），绝不能买 ----
            bool? readOnly = ToolUpgradeIo.ReadOnly(menu);
            if (readOnly == true)
            {
                CloseShop(menu);
                return this.Fail(ToolUpgradeRules.StatusReadOnly,
                    "当前 ShopMenu.readOnly == true（电话查价路径）：在这类店里买东西**只扣钱/扣材料、不升级**"
                    + "（tryToPurchaseItem 的 actionWhenPurchased 被 `if (!readOnly)` 跳过）⇒ 本次不买，已关店");
            }

            // ---- 在**这个**菜单实例的 itemPriceAndStock 里重新选条目（引用相等：必须用菜单自己的 key） ----
            var menuOffers = new List<UpgradeOfferInput>();
            var menuKeys = new List<ISalable>();
            try
            {
                foreach (KeyValuePair<ISalable, ItemStockInformation> kv in menu.itemPriceAndStock)
                {
                    if (!(kv.Key is Tool t)) continue;
                    menuOffers.Add(new UpgradeOfferInput(
                        ToolUpgradeIo.SafeId(kv.Key), ToolUpgradeIo.SafeName(kv.Key),
                        ToolUpgradeIo.KindOf(t), ToolUpgradeIo.TierOf(t),
                        kv.Value?.Price ?? 0, kv.Value?.TradeItem, kv.Value?.TradeItemCount ?? 0,
                        kv.Value?.Stock ?? 0));
                    menuKeys.Add(kv.Key);
                }
            }
            catch (Exception ex)
            {
                CloseShop(menu);
                return this.Fail(ToolUpgradeRules.StatusShopUnavailable,
                    "读 ShopMenu.itemPriceAndStock 异常：" + ex.GetType().Name + ": " + ex.Message);
            }

            UpgradePickResult pick = ToolUpgradeRules.Select(menuOffers, this._kind, this._tierBefore);
            if (pick.Index < 0)
            {
                int alt = ToolUpgradeIo.MatchByExpectedData(menuOffers, p, this._tool, out string altNote);
                if (alt < 0)
                {
                    CloseShop(menu);
                    return this.Fail(pick.Status, pick.Note + $"（菜单内反查：{altNote}）");
                }
                pick = new UpgradePickResult { Index = alt, Status = ToolUpgradeRules.StatusOk,
                                               Note = $"按 GetToolUpgradeData 反查命中：{altNote}" };
            }

            UpgradeOfferInput offer = menuOffers[pick.Index];
            ISalable key = menuKeys[pick.Index];
            this._rows = OfferRows(menuOffers);
            this._moneyBefore = p.Money;
            this._tradeHaveBefore = ToolUpgradeIo.CountItem(p, offer.TradeItem);

            // ---- 自检（钱 / 锭 / 空位）----
            string block = ToolUpgradeRules.Precheck(
                new UpgradePrecheck(false, 0, ToolUpgradeIo.FreeSlots(p), false,
                                    this._moneyBefore, offer.Price, this._tradeHaveBefore, offer.TradeCount),
                requireFreeSlot: false);
            string snap =
                $"目标「{offer.Name}」tier {this._tierBefore}→{offer.Tier}，价 {offer.Price}g"
                + (string.IsNullOrEmpty(offer.TradeItem) ? "（不要材料）"
                   : $"，材料 {offer.TradeItem} ×{offer.TradeCount}（现有 {this._tradeHaveBefore}）")
                + $"；钱 {this._moneyBefore}g；空格 {ToolUpgradeIo.FreeSlots(p)}";
            if (block == ToolUpgradeRules.StatusNoMoney)
            {
                CloseShop(menu);
                return this.Fail(block, $"钱不够：{snap}；差额 {offer.Price - this._moneyBefore}g ⇒ 本次不买（游戏会走 cancel 分支，什么都不扣但白跑）");
            }
            if (block == ToolUpgradeRules.StatusNoTradeItem)
            {
                CloseShop(menu);
                return this.Fail(block, $"材料不够：{snap}；还缺 {offer.TradeCount - this._tradeHaveBefore} 件 ⇒ 本次不买");
            }
            if (block != "")
            {
                CloseShop(menu);
                return this.Fail(block, $"预检不通过（{block}）：{snap}");
            }

            // ---- 买（游戏自己的购买函数） ----
            bool invoked = ToolUpgradeIo.TryPurchase(menu, key, out string callNote);
            string closeNote = "actionWhenPurchased 自己可能已 exitActiveMenu";
            try { if (Game1.activeClickableMenu != null) { menu.exitThisMenu(false); closeNote = "exitThisMenu(false)"; } }
            catch (Exception ex) { closeNote = "exitThisMenu 异常：" + ex.GetType().Name; }

            // ---- 判据：观测差分（不看回执/游戏返回值） ----
            int moneyAfter = p.Money;
            int tradeAfter = ToolUpgradeIo.CountItem(p, offer.TradeItem);
            bool upgradeAppeared = false;
            string beingName = null;
            int? daysAfter = null;
            try
            {
                Tool being = p.toolBeingUpgraded?.Value;
                upgradeAppeared = being != null;
                beingName = being?.DisplayName;
                daysAfter = p.daysLeftForToolUpgrade?.Value;
            }
            catch { }
            bool moneyReduced = moneyAfter < this._moneyBefore;
            bool tradeReduced = tradeAfter < this._tradeHaveBefore;
            string evidence = ToolUpgradeRules.Evidence(upgradeAppeared, tradeReduced, moneyReduced, false);

            string core =
                $"{snap}；钱 {this._moneyBefore}→{moneyAfter}"
                + (string.IsNullOrEmpty(offer.TradeItem) ? "" : $"，材料 {this._tradeHaveBefore}→{tradeAfter}")
                + $"；toolBeingUpgraded={beingName ?? "(无)"}，daysLeft={daysAfter?.ToString() ?? "(读不到)"}"
                + $"；调用：{callNote}；invoked={invoked}；关店：{closeNote}";

            if (!ToolUpgradeRules.Acted(evidence))
            {
                return this.Fail(ToolUpgradeRules.StatusPurchaseNoEffect,
                    "买了但观测上什么都没变（钱没少 / 锭没少 / toolBeingUpgraded 仍是 null）⇒ 如实判失败（回执只是声明）："
                    + core);
            }

            ExecResponse ok = this.Respond(true, ToolUpgradeRules.StatusOk,
                "已在铁匠铺买下升级：" + core + $"。判据来源={evidence}。"
                + "注意：等级在买下时就换了；再过 2 天（daysLeft=0）去铁匠铺取回（pickup_tool）");
            ok.Price = offer.Price;
            ok.TradeItem = offer.TradeItem;
            ok.TradeCount = offer.TradeCount;
            ok.MoneyBefore = this._moneyBefore;
            ok.MoneyAfter = moneyAfter;
            ok.TierAfter = offer.Tier;
            ok.Acted = true;
            ok.ActedEvidence = evidence;
            return ok;
        }

        private static string SafeBeingUpgraded(Farmer p)
        {
            try { return p?.toolBeingUpgraded?.Value?.DisplayName ?? "(无)"; } catch { return "(读不到)"; }
        }

        private static void CloseShop(ShopMenu menu)
        {
            try { if (Game1.activeClickableMenu != null) menu.exitThisMenu(false); } catch { }
        }

        private static UpgradeOfferView[] OfferRows(List<UpgradeOfferInput> offers)
        {
            if (offers == null) return null;
            var rows = new UpgradeOfferView[offers.Count];
            for (int i = 0; i < offers.Count; i++)
            {
                UpgradeOfferInput o = offers[i];
                rows[i] = new UpgradeOfferView
                {
                    Id = o.Id, Name = o.Name, Kind = o.Kind, Tier = o.Tier,
                    Price = o.Price, TradeItem = o.TradeItem,
                    TradeCount = o.TradeCount > 0 ? o.TradeCount : (int?)null,
                    Stock = o.Stock,
                };
            }
            return rows;
        }
    }

    /// <summary>
    /// 【task-205】`pickup_tool`：升级完成（`daysLeft &lt;= 0`）后去铁匠铺**取回**工具。
    ///
    /// 取回不是 `answerDialogueAction`，而是 `GameLocation.blacksmith(...)` **开头的 pickup 分支**
    /// （IL §1.3）：清空 `toolBeingUpgraded` + 工具进背包 + `hasReceivedToolUpgradeMessageYet = false`
    /// + `holdUpItemThenMessage`。
    ///
    /// 硬前置：
    ///   * `toolBeingUpgraded != null`（没有在途 ⇒ `nothing_to_pickup`）；
    ///   * `daysLeft &lt;= 0`（还在做 ⇒ `still_working`）；
    ///   * **背包 ≥1 空格**（`freeSpotsInInventory() &lt;= 0` ⇒ Clint 只说 `Clint_NoInventorySpace`，工具拿不回来 ⇒ `no_slot`）；
    ///   * 人在 Blacksmith 店里（`blacksmith()` 只认当前地点 `characters` 里的 Clint）。
    /// </summary>
    internal sealed class ToolPickupSkill
    {
        private readonly ExecRequest _req;
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly int _timeoutMs;

        private bool _started;
        private DateTime _startedAtUtc;
        private long _seqBefore;
        private string _kind;
        private int _tierBefore;
        private string _beingBefore;
        private int _invBefore;
        private int? _daysLeft;

        public ToolPickupSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._req = req;
            this._world = world;
            this._monitor = monitor;
            this._timeoutMs = Skills.ClampTimeoutFor("pickup_tool", req?.TimeoutMs);
        }

        private long Elapsed() => (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds;

        private ExecResponse Respond(bool ok, string status, string reason)
            => new ExecResponse
            {
                Ok = ok,
                Status = status,
                Skill = "pickup_tool",
                Reason = reason,
                Schema = Skills.ExecSchema,
                ElapsedMs = this.Elapsed(),
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
                Tool = this._kind,
                TierBefore = this._tierBefore >= 0 ? this._tierBefore : (int?)null,
                ToolBeingUpgraded = this._beingBefore,
                DaysLeft = this._daysLeft,
            };

        private ExecResponse Fail(string status, string reason) => this.Respond(false, status, reason);

        public object Step()
        {
            long seq = 0;
            try { seq = this._world?.WorldSeq ?? 0; } catch { }

            if (!Context.IsWorldReady || Game1.player == null)
                return this.Fail("no_save", "尚未加载存档，无法 pickup_tool");

            Farmer p = Game1.player;
            if (!this._started)
            {
                this._started = true;
                this._startedAtUtc = DateTime.UtcNow;
                this._seqBefore = seq;

                Tool being;
                int daysLeft;
                try
                {
                    being = p.toolBeingUpgraded?.Value;
                    daysLeft = p.daysLeftForToolUpgrade?.Value ?? 0;
                }
                catch { being = null; daysLeft = 0; }
                this._daysLeft = daysLeft;
                this._beingBefore = being?.DisplayName;
                this._kind = ToolUpgradeIo.KindOf(being);
                this._tierBefore = ToolUpgradeIo.TierOf(being);
                this._invBefore = being == null ? 0 : CountSameKind(p, this._kind);

                if (being == null)
                    return this.Fail(ToolUpgradeRules.StatusNothingToPickup,
                        "没有工具在 Clint 那里升级（toolBeingUpgraded == null）—— 没什么可取回的");
                if (daysLeft > 0)
                    return this.Fail(ToolUpgradeRules.StatusStillWorking,
                        $"「{this._beingBefore}」还在升级（daysLeftForToolUpgrade={daysLeft}）；做完再来取回");

                int free = ToolUpgradeIo.FreeSlots(p);
                if (free <= 0)
                    return this.Fail(ToolUpgradeRules.StatusNoSlot,
                        $"背包没有空格（freeSpotsInInventory={free}）：`blacksmith()` 的 pickup 分支见"
                        + " `freeSpotsInInventory() <= 0` 只会让 Clint 说 Clint_NoInventorySpace，工具拿不回来"
                        + "（且不会失败扣钱、只是白跑）⇒ 先腾格再来取回");

                string loc = ToolUpgradeIo.LocationName();
                if (!string.Equals(loc, ToolUpgradeIo.BlacksmithLocation, StringComparison.OrdinalIgnoreCase))
                    return this.Fail(ToolUpgradeRules.StatusWrongLocation,
                        $"当前地点是「{loc ?? "(读不到)"}」：`blacksmith()` 只认**当前地点 characters 里的 Clint**，"
                        + $"必须人在「{ToolUpgradeIo.BlacksmithLocation}」店里（脑侧先 ensure_location）");
            }

            // ---- 调游戏自己的取回入口 ----
            bool called = ToolUpgradeIo.CallBlacksmith(out string callNote);

            // ---- 判据：观测差分 ----
            Tool stillBeing = null;
            int daysAfter = -1;
            try
            {
                stillBeing = p.toolBeingUpgraded?.Value;
                daysAfter = p.daysLeftForToolUpgrade?.Value ?? -1;
            }
            catch { }
            int invAfter = CountSameKind(p, this._kind);
            bool cleared = stillBeing == null;
            bool gained = invAfter > this._invBefore;
            string evidence = ToolUpgradeRules.Evidence(cleared, false, false, gained);

            int tierAfter = -1;
            Tool back = ToolUpgradeIo.FindTool(p, this._kind);
            if (back != null) tierAfter = ToolUpgradeIo.TierOf(back);

            string core = $"工具「{this._beingBefore ?? "(读不到)"}」kind={this._kind ?? "?"}，tier {this._tierBefore}"
                + $"；toolBeingUpgraded {(cleared ? "已清空" : "仍在")}，daysLeft={daysAfter}"
                + $"；背包同种工具 {this._invBefore}→{invAfter}（取回后 tier={tierAfter}）"
                + $"；调用：{callNote}；called={called}";

            if (!ToolUpgradeRules.Acted(evidence))
                return this.Fail("pickup_no_effect",
                    "取了但观测上什么都没变（toolBeingUpgraded 仍非 null 且背包没增加）⇒ 如实判失败：" + core);

            ExecResponse ok = this.Respond(true, ToolUpgradeRules.StatusOk,
                "已取回升级后的工具：" + core + $"。判据来源={evidence}");
            ok.Price = null;
            ok.MoneyBefore = p.Money;
            ok.MoneyAfter = p.Money;
            ok.TierAfter = tierAfter >= 0 ? tierAfter : (int?)null;
            ok.InventoryAdded = invAfter - this._invBefore;
            ok.DaysLeft = daysAfter;
            ok.Acted = true;
            ok.ActedEvidence = evidence;
            return ok;
        }

        private static int CountSameKind(Farmer p, string kind)
        {
            if (p?.Items == null || string.IsNullOrEmpty(kind)) return 0;
            int n = 0;
            foreach (Item item in p.Items)
            {
                if (item is Tool t && ToolUpgradeRules.SameKind(ToolUpgradeIo.KindOf(item), kind)) n++;
            }
            return n;
        }
    }
}
