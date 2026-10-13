using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Menus;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【P3 步骤⑤/⑥】`buy`：**用游戏自己的购买链买种子**（脑有钱就补货，而不是一有空就睡）。
    ///
    /// ==================================================================
    /// 【规则：钱与物品只能由游戏自己动，Mod 绝不自己加减】
    /// 这是 v0.7.17 那次真机事故（作物种下去了、种子却没扣，见 docs/_il-plant-consume.md）留下的硬纪律：
    /// 凡涉及"钱/物品数量"的副作用，**一律调游戏自己的函数**，Mod 不写 `Money -= price` 这种算术。
    ///
    /// 【证据链（tools/il-probe，1.6.15，落 logs/il-shop-buy-u8.txt 与 logs/il-shop-callers-u8.txt）】
    /// `ShopMenu.receiveLeftClick(x,y,playSound)` 是玩家点"买"时走的路，它的核心一步是
    ///   `IL_06B5 call Boolean tryToPurchaseItem(ISalable item, ISalable held_item, Int32 stockToBuy, Int32 x, Int32 y)`
    /// 而 `tryToPurchaseItem` 内部（private，只能反射）已经包含**完整**的一次购买：
    ///   * `IL_0000-0009  if (this.readOnly) return false;`                        ← 只读商店不卖
    ///   * `IL_000A-0016  stockInfo = itemPriceAndStock[item];`
    ///   * `IL_0017-0018  if (held_item != null) goto IL_03A8;`                    ← 传 null 才走"直接购买"
    ///   * `IL_001D-002D  if (stockInfo.Stock == 0) { hoveredItem = null; return true; }`  ← **没货也返回 true**
    ///   * `IL_002E-004D  stockToBuy = clamp(…, 1, item.maximumStackSize())`
    ///   * `IL_0050-0057  price = stockInfo.Price * stockToBuy;`
    ///   * `IL_0092-00A3  if (getPlayerCurrencyAmount(player, currency) < price) goto IL_037B`  ← 钱不够整体拒绝
    ///   * `IL_00B8-00DC  this.heldItem = item.GetSalableInstance(); heldItem.Stack = …; heldItem.CanBuyItem(player)`
    ///   * `IL_013D        chargePlayer(player, currency, amount)`                  ← **扣钱（游戏自己扣）**
    ///   * `IL_014D        ConsumeTradeItem(...)`（以物易物才走）
    ///   * `IL_0257        HandleSynchedItemPurchase(item, player, stockToBuy)`     ← 团队成员共享库存记账
    ///   * `IL_0365        onPurchase.Invoke(item, player, n, stockInfo)`           ← 商店自己的购买回调
    ///   * `IL_05C2-05E2  if (Stock <= 0) return true; return false;`               ← ⚠️ 返回值含义是"这行该撤了"
    /// 两个**必须记住的坑**（不记住就会写出"以为成功了其实没买"或"钱扣了东西没到手"）：
    ///   ① **返回值不是成功判据**：`Stock` 没归零时它返回 `false`，而"库存为 0 什么都没买"却返回 `true`。
    ///      ⇒ 本技能一律**用观测差分判成交**（钱少了多少 + 背包里这件东西多了几个），回执里两个数都报出来。
    ///   ② **它不把东西放进背包**：物品被放进 `this.heldItem`（= 鼠标上那件）。玩家是自己再点背包放下的；
    ///      游戏自己在两处替玩家收尾，都是同一句
    ///      `Game1.player.addItemToInventoryBool(heldItem as Item, false)`
    ///      —— `receiveLeftClick` 的收尾分支（`logs/il-shop-callers-u8.txt` IL_0799）与
    ///      `ShopMenu.emergencyShutDown`（关店时的兜底）。本技能就调**这一句**，见 <see cref="SettleHeldItem"/>。
    ///      （绝对不自己往背包里塞：那样就成了第二次"伪造物品数量"。）
    ///
    /// 【为什么不用 `receiveLeftClick(按钮中心)` 这条更"玩家"的路】
    /// 那条路要先算出可点击行的屏幕坐标（`forSaleButtons[i].containsPoint`，还要处理 `currentItemIndex` 滚动），
    /// 坐标一错就是"点了别的商品"——静默买错比买不到更糟。这里改为直接调它内部那句
    /// `tryToPurchaseItem(item, null, count, 0, 0)`，**跳过的是几何寻址，不是购买逻辑**；
    /// 钱、库存、回调、团队成员同步全部仍由游戏自己完成。
    ///
    /// 【开店】`Utility.TryOpenShopMenu(shopId, ownerName, playOpenSound)`（public，api-probe 实证）。
    /// shopId 只交给游戏去查 `Data/Shops`（默认 `"SeedShop"` = 皮埃尔杂货店）。
    /// ==================================================================
    /// </summary>
    internal sealed class BuySkill
    {
        private const string DefaultShopId = "SeedShop";
        private const int OpenShopWaitMs = 3000;

        private readonly ExecRequest _req;
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly int _timeoutMs;

        private bool _started;
        private DateTime _startedAtUtc;
        private long _seqBefore;
        private int _openTries;

        /// <summary>
        /// 【0.7.26 / task-67】菜单挂上那一刻的货架清单（`itemPriceAndStock`），成功与失败回执都带。
        /// run6 真机事故：脑硬编码 `472`（**春季**防风草种子）⇒ 夏季每天白试 6 次 `item_not_sold`。
        /// 脑看不到 `Data/Crops`，只能靠这份清单自己挑当季能买的种子。
        /// </summary>
        private ShopItemView[] _available;

        public BuySkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._req = req;
            this._world = world;
            this._monitor = monitor;
            // 开店 + 买东西都很快，用默认口径（8 秒，上限 30 秒）足够
            this._timeoutMs = Skills.ClampTimeout(req?.TimeoutMs);
        }

        private long Elapsed() => (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds;

        private string ShopId
        {
            get
            {
                string s = this._req?.Args?.Shop;
                return string.IsNullOrWhiteSpace(s) ? DefaultShopId : s.Trim();
            }
        }

        private ExecResponse Fail(string status, string reason, long elapsedMs)
            => new ExecResponse
            {
                Ok = false, Status = status, Skill = "buy", Reason = reason,
                Schema = Skills.ExecSchema, ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
                // 【task-67】失败也必须带货架清单：`item_not_sold` 正是脑唯一能"改买当季种子"的时机。
                AvailableItems = this._available,
            };

        /// <summary>主线程调用：返回非 null = 终态；返回 null = 还在等商店菜单挂上。</summary>
        public object Step()
        {
            long seq = 0;
            try { seq = this._world?.WorldSeq ?? 0; } catch { }

            if (!Context.IsWorldReady || Game1.player == null)
                return this.Fail("no_save", "尚未加载存档，无法 buy", 0);

            if (!this._started)
            {
                this._started = true;
                this._startedAtUtc = DateTime.UtcNow;
                this._seqBefore = seq;
            }

            ShopMenu menu = Game1.activeClickableMenu as ShopMenu;

            if (menu == null)
            {
                // 第一次：开店（游戏自己的入口）
                if (this._openTries == 0)
                {
                    this._openTries++;
                    bool opened = false;
                    string why = null;
                    try { opened = Utility.TryOpenShopMenu(this.ShopId, null, false); }
                    catch (Exception ex) { why = ex.GetType().Name + ": " + ex.Message; }

                    if (!opened)
                        return this.Fail("shop_unavailable",
                            $"Utility.TryOpenShopMenu(\"{this.ShopId}\", null, false) 返回 false"
                            + (why == null ? "" : $"（异常：{why}）")
                            + $"。当前地点 {StepMover.CurrentLocationName()}，timeOfDay={Game1.timeOfDay}"
                            + $"，activeMenu={Game1.activeClickableMenu?.GetType().Name ?? "(无)"}"
                            + "。可能原因：商店 id 不存在 / 该商店此刻不开门 / 世界没准备好",
                            this.Elapsed());

                    this._monitor?.Log($"buy：已请求开店「{this.ShopId}」，等菜单挂上");
                    menu = Game1.activeClickableMenu as ShopMenu;
                    if (menu == null) return null;   // 跨 tick 等
                }
                else
                {
                    if (this.Elapsed() > OpenShopWaitMs)
                        return this.Fail("shop_timeout",
                            $"请求开店「{this.ShopId}」后 {this.Elapsed()}ms 内没等到 ShopMenu"
                            + $"（activeMenu={Game1.activeClickableMenu?.GetType().Name ?? "(无)"}）",
                            this.Elapsed());
                    return null;
                }
            }

            return this.DoPurchase(menu);
        }

        // ==================================================================
        //  一次购买（单 tick 内完成）
        // ==================================================================

        private ExecResponse DoPurchase(ShopMenu menu)
        {
            long elapsed = this.Elapsed();
            // 【task-67】先抓一份货架真值：成功、失败（`item_not_sold` 尤其重要）都要带回去。
            this._available = Shelf(menu);
            string want = this._req?.Args?.Item;
            if (string.IsNullOrWhiteSpace(want))
                return this.Fail("bad_args", "buy 需要 args.item（ItemId / QualifiedItemId / 名字）", elapsed);
            want = want.Trim();

            // ---- 1) 在货架上找这一条（游戏的真值：itemPriceAndStock） ----
            ISalable key = null;
            ItemStockInformation info = null;
            try
            {
                foreach (KeyValuePair<ISalable, ItemStockInformation> kv in menu.itemPriceAndStock)
                {
                    if (MatchesItem(kv.Key, want)) { key = kv.Key; info = kv.Value; break; }
                }
            }
            catch (Exception ex)
            {
                return this.Fail("shop_error", "读 itemPriceAndStock 异常：" + ex.GetType().Name + ": " + ex.Message, elapsed);
            }

            if (key == null)
                return this.Fail("item_not_sold",
                    $"商店「{this.ShopId}」里没有「{want}」。在售清单：{Listing(menu)}", elapsed);

            string itemName = SafeName(key);
            int price = info?.Price ?? 0;
            int stock = info?.Stock ?? 0;
            int moneyBefore = Game1.player.Money;
            int invBefore = CountInInventory(Game1.player, want);

            // ---- 2) 请求量夹小（游戏还会再判一次：钱不够它会整体拒绝） ----
            int count = this._req?.Args?.Count ?? 1;
            if (count < 1) count = 1;

            if (price > 0)
            {
                int affordable = moneyBefore / price;
                if (affordable < 1)
                    return this.Fail("cannot_afford",
                        $"钱不够：现有 {moneyBefore}g，「{itemName}」单价 {price}g，一个都买不起"
                        + $"（库存 {StockText(stock)}）", elapsed);
                if (count > affordable) count = affordable;
            }
            if (stock > 0 && count > stock) count = stock;

            // ---- 3) 背包空间预检（防止"钱扣了、东西没地方放"这种真实损失） ----
            int freeSlots;
            int roomInSameStack;
            CountSpace(Game1.player, want, out freeSlots, out roomInSameStack);
            if (freeSlots < 1 && roomInSameStack < 1)
                return this.Fail("no_inventory_space",
                    $"背包既没有空格、也没有「{itemName}」的同类堆叠可以并入（空格 0），"
                    + "为避免扣了钱却拿不到东西，本次不购买。请先腾出背包空间", elapsed);

            // ---- 4) 调游戏自己的购买函数 ----
            string callNote;
            bool gameReturn;
            bool invoked = TryPurchase(menu, key, count, out gameReturn, out callNote);

            // ---- 5) 收货：游戏自己在关店/收尾时用的那一句 ----
            string settleNote;
            bool settled = SettleHeldItem(menu, out settleNote);

            // ---- 6) 关店，把世界交还（游戏自己的 exitThisMenu，会走 emergencyShutDown 兜底） ----
            string closeNote = "(没关店)";
            if (settled)
            {
                try { menu.exitThisMenu(false); closeNote = "exitThisMenu(false)"; }
                catch (Exception ex) { closeNote = "exitThisMenu 异常：" + ex.GetType().Name + ": " + ex.Message; }
            }

            // ---- 7) 判据：观测差分（不看游戏返回值） ----
            int moneyAfter = Game1.player.Money;
            int invAfter = CountInInventory(Game1.player, want);
            int spent = moneyBefore - moneyAfter;
            int gained = invAfter - invBefore;

            string core =
                $"「{itemName}」单价 {price}g，请求 {count} 个（库存 {StockText(stock)}）"
                + $"；钱 {moneyBefore}→{moneyAfter}（支出 {spent}g），背包里这件 {invBefore}→{invAfter}（净得 {gained}）"
                + $"；调用：{callNote}；游戏返回值={gameReturn}（⚠️ 它的含义是「这行该撤了」，不是成败）"
                + $"；收货：{settleNote}；关店：{closeNote}";

            if (gained <= 0)
            {
                return this.Fail("purchase_no_effect",
                    core + "。结论：**观测上看没有买到东西**（背包数量没变）"
                    + $"。诊断：readOnly={SafeReadOnly(menu)}，"
                    + $"activeMenu={Game1.activeClickableMenu?.GetType().Name ?? "(无)"}"
                    + "。这是一次「宣称成功但事实没有」的典型，脑必须以背包/钱的实际数字为准",
                    this.Elapsed());
            }

            if (!invoked || !settled)
            {
                return this.Fail("purchase_partial",
                    core + "。结论：东西**到手了一部分但收尾不干净**（反射调用或收货失败），"
                    + "需要人工/脑复核（钱已按实际支出扣减）",
                    this.Elapsed());
            }

            return new ExecResponse
            {
                Ok = true, Status = "ok", Skill = "buy", Schema = Skills.ExecSchema,
                Reason = core + $"。结论：买到了 {gained} 个「{itemName}」，共花 {spent}g。"
                              + "回执只是声明，钱与种子数请用 observe 复核（player.money / inventory[]）",
                ElapsedMs = this.Elapsed(),
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
                AvailableItems = this._available,   // 【task-67】货架真值：脑据此挑品种
            };
        }

        // ==================================================================
        //  调游戏自己的购买 / 收货
        // ==================================================================

        /// <summary>
        /// 反射调 `ShopMenu.tryToPurchaseItem(item, null, count, 0, 0)`。
        /// `held_item` 传 null 是**关键**：IL_0017 的分支表明只有 null 才走"直接购买"那条路。
        /// </summary>
        private static bool TryPurchase(ShopMenu menu, ISalable item, int count, out bool gameReturn, out string note)
        {
            gameReturn = false;
            try
            {
                MethodInfo mi = typeof(ShopMenu).GetMethod(
                    "tryToPurchaseItem", BindingFlags.Instance | BindingFlags.NonPublic);
                if (mi == null) { note = "找不到 ShopMenu.tryToPurchaseItem（私有）"; return false; }

                object ret = mi.Invoke(menu, new object[] { item, null, count, 0, 0 });
                gameReturn = ret is bool b && b;
                note = $"tryToPurchaseItem({SafeName(item)}, null, {count}, 0, 0) → {ret}";
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
        /// 把 `menu.heldItem`（买到的、挂在"鼠标"上的那件）放进玩家背包 —— 用**游戏自己的那一句**
        /// `Game1.player.addItemToInventoryBool(item, false)`（`ShopMenu.receiveLeftClick` 收尾分支
        /// IL_0799 与 `ShopMenu.emergencyShutDown` 都是它）。成功后才清掉 `heldItem`。
        /// </summary>
        private static bool SettleHeldItem(ShopMenu menu, out string note)
        {
            Item held = null;
            try { held = menu.heldItem as Item; } catch { }
            if (held == null) { note = "手上没有待收货的物品"; return true; }

            try
            {
                bool added = Game1.player.addItemToInventoryBool(held, false);
                if (added)
                {
                    int n = held.Stack;
                    menu.heldItem = null;
                    note = $"addItemToInventoryBool({SafeName(held)} ×{n}, false) → true，已从商店手上清掉";
                    return true;
                }
                note = $"addItemToInventoryBool({SafeName(held)}, false) → false（背包可能已满）：物品仍留在商店手上，"
                     + "本次**不关店**，以免物品丢失";
                return false;
            }
            catch (Exception ex)
            {
                note = "收货异常：" + ex.GetType().Name + ": " + ex.Message;
                return false;
            }
        }

        // ==================================================================
        //  物品匹配与计数（一律走游戏的真值）
        // ==================================================================

        private static bool MatchesItem(ISalable s, string want)
        {
            if (s == null || string.IsNullOrEmpty(want)) return false;
            string w = want.Trim();

            if (s is Item it)
            {
                if (Eq(it.QualifiedItemId, w)) return true;            // "(O)472"
                if (Eq(it.ItemId, w)) return true;                     // "472"
                if (Eq("(O)" + it.ItemId, w)) return true;             // 允许只写前缀形式
                if (Eq(it.Name, w)) return true;                       // "Parsnip Seeds"
                if (Eq(it.DisplayName, w)) return true;                // 本地化名
            }
            return Eq(s.Name, w);
        }

        private static bool Eq(string a, string b)
            => !string.IsNullOrEmpty(a) && string.Equals(a, b, StringComparison.OrdinalIgnoreCase);

        /// <summary>背包里这件东西一共有几个（同 id 的多个堆叠会相加）。</summary>
        private static int CountInInventory(Farmer who, string want)
        {
            int n = 0;
            try
            {
                foreach (Item it in who.Items)
                    if (it != null && MatchesItem(it, want)) n += Math.Max(1, it.Stack);
            }
            catch { }
            return n;
        }

        /// <summary>空格子数与"同类堆叠还能装下几个"。</summary>
        private static void CountSpace(Farmer who, string want, out int freeSlots, out int roomInSameStack)
        {
            freeSlots = 0; roomInSameStack = 0;
            try
            {
                foreach (Item it in who.Items)
                {
                    if (it == null) { freeSlots++; continue; }
                    if (MatchesItem(it, want)) roomInSameStack += Math.Max(0, it.maximumStackSize() - it.Stack);
                }
            }
            catch { }
        }

        private static string SafeName(ISalable s)
        {
            if (s == null) return "(null)";
            try { return s.DisplayName ?? s.Name ?? "(无名)"; } catch { return "(取名异常)"; }
        }

        private static string StockText(int stock)
            => stock == int.MaxValue ? "无限" : (stock < 0 ? "?" : stock.ToString());

        /// <summary>
        /// 【task-67】货架的**结构化**清单：按价格升序、最多 30 条。
        ///
        /// 为什么按价格升序再截断：脑要的是"我买得起的最便宜当季种子"，贵的排后面被截掉正合适。
        /// 读不出来就返回 null（字段被省略 ⇒ 脑按"没有清单"处理）——**绝不伪造**货架。
        /// </summary>
        private static ShopItemView[] Shelf(ShopMenu menu)
        {
            try
            {
                List<ShopItemView> rows = new List<ShopItemView>();
                foreach (KeyValuePair<ISalable, ItemStockInformation> kv in menu.itemPriceAndStock)
                    rows.Add(new ShopItemView
                    {
                        Id = SafeId(kv.Key),
                        Name = SafeName(kv.Key),
                        Price = kv.Value?.Price ?? -1,
                    });
                rows.Sort((a, b) => a.Price.CompareTo(b.Price));
                if (rows.Count > 30) rows = rows.GetRange(0, 30);
                return rows.ToArray();
            }
            catch { return null; }
        }

        /// <summary>下单用的 id：优先 `QualifiedItemId`（`(O)472`），退 `ItemId`，再退名字。</summary>
        private static string SafeId(ISalable s)
        {
            if (s == null) return null;
            try
            {
                if (s is Item it)
                {
                    if (!string.IsNullOrEmpty(it.QualifiedItemId)) return it.QualifiedItemId;
                    if (!string.IsNullOrEmpty(it.ItemId)) return it.ItemId;
                }
                return s.Name;
            }
            catch { return null; }
        }

        /// <summary>货架清单（截断），用于"没有这件商品"时让脑自己看清有什么。</summary>
        private static string Listing(ShopMenu menu)
        {
            try
            {
                List<string> names = new List<string>();
                foreach (KeyValuePair<ISalable, ItemStockInformation> kv in menu.itemPriceAndStock)
                {
                    if (names.Count >= 12) { names.Add("…"); break; }
                    int p = kv.Value?.Price ?? -1;
                    names.Add($"{SafeName(kv.Key)}({p}g)");
                }
                return names.Count == 0 ? "(货架是空的)" : string.Join("、", names);
            }
            catch (Exception ex) { return "(读货架异常：" + ex.GetType().Name + ")"; }
        }

        /// <summary>
        /// 诊断用：`ShopMenu.readOnly`（IL_0000：只读商店会直接 return false，什么也不卖）。
        /// 用反射读，免得依赖它的可见性。
        /// </summary>
        private static string SafeReadOnly(ShopMenu menu)
        {
            try
            {
                FieldInfo f = typeof(ShopMenu).GetField(
                    "readOnly", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (f == null) return "?(字段不存在)";
                return f.GetValue(menu)?.ToString() ?? "?";
            }
            catch { return "?(读不到)"; }
        }
    }
}
