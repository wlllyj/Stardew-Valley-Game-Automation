using System;
using System.Collections.Generic;
using System.Text;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 铁匠铺升级店（`ClintUpgrade`）的一条在售条目 —— 纯值，不带任何游戏类型。
    /// 由 `ToolUpgradeSkill` 从 <c>ShopBuilder.GetShopStock("ClintUpgrade")</c> 映射进来。
    /// </summary>
    internal readonly struct UpgradeOfferInput
    {
        public readonly string Id;          // QualifiedItemId（如 (T)Ax）——取证/日志用
        public readonly string Name;        // 展示名
        public readonly string Kind;        // axe / pickaxe / hoe / can / scythe / pan / fishingRod / other
        public readonly int Tier;           // Tool.UpgradeLevel（0 = 初始）
        public readonly int Price;          // ItemStockInformation.Price
        public readonly string TradeItem;    // ItemStockInformation.TradeItem（如 (O)334）；null = 不要材料
        public readonly int TradeCount;      // ItemStockInformation.TradeItemCount ?? 0
        public readonly int Stock;           // ItemStockInformation.Stock（0 = 无限）

        public UpgradeOfferInput(string id, string name, string kind, int tier,
                                int price, string tradeItem, int tradeCount, int stock)
        {
            this.Id = id;
            this.Name = name;
            this.Kind = kind;
            this.Tier = tier;
            this.Price = price;
            this.TradeItem = tradeItem;
            this.TradeCount = tradeCount;
            this.Stock = stock;
        }
    }

    /// <summary>
    /// 买前自检的输入（全部是观测值）。顺序与失败码见 <see cref="ToolUpgradeRules.Precheck"/>。
    /// </summary>
    internal readonly struct UpgradePrecheck
    {
        public readonly bool AlreadyUpgrading;   // player.toolBeingUpgraded != null
        public readonly int DaysLeft;            // player.daysLeftForToolUpgrade
        public readonly int FreeSlots;           // player.freeSpotsInInventory()
        public readonly bool ShopReadOnly;       // ShopMenu.readOnly（电话查价路径 = true）
        public readonly int Money;
        public readonly int Price;
        public readonly int TradeHave;           // 背包里 TradeItem 的现有数量
        public readonly int TradeNeed;           // ItemStockInformation.TradeItemCount ?? 0

        public UpgradePrecheck(bool alreadyUpgrading, int daysLeft, int freeSlots, bool shopReadOnly,
                               int money, int price, int tradeHave, int tradeNeed)
        {
            this.AlreadyUpgrading = alreadyUpgrading;
            this.DaysLeft = daysLeft;
            this.FreeSlots = freeSlots;
            this.ShopReadOnly = shopReadOnly;
            this.Money = money;
            this.Price = price;
            this.TradeHave = tradeHave;
            this.TradeNeed = tradeNeed;
        }
    }

    /// <summary>条目选择结果：<see cref="Index"/> &gt;= 0 且 <see cref="Status"/> == "ok" 才算选中。</summary>
    internal sealed class UpgradePickResult
    {
        public int Index = -1;
        public string Status = "";
        public string Note = "";
    }

    /// <summary>
    /// 【task-205】铁匠铺升级链的**判据本体**（纯函数、零游戏类型依赖）。
    ///
    /// 为什么外置（与 `ClumpRules`/`TileListRules` 同一条理由）：仓库没有能引用游戏程序集的
    /// C# 测试工程，判据若留在吃 `ShopMenu`/`Farmer` 的技能里就只能做源码文本断言。
    /// 抽成纯函数后 `mod/AgentFarm.Bridge.Tests` 直接编译本文件跑**行为**断言。
    ///
    /// 【链路依据】`docs/_il-tool-upgrade.md`（task-204，`d6d55e2`）：
    ///   * 白扣钱陷阱：`tryToPurchaseItem` 先 `chargePlayer` + `ConsumeTradeItem`，再
    ///     `actionWhenPurchased`；后者见"已在升级"直接 return false **且不回滚**
    ///     ⇒ 买前必须堵 `toolBeingUpgraded != null`（`AlreadyUpgrading`）。
    ///   * `readOnly` 店（电话查价路径）买东西**只扣钱不升级**（`if (!readOnly) { … }`）
    ///     ⇒ 买前必须堵 `ShopMenu.readOnly == true`。
    ///   * 材料/钱不够时 `tryToPurchaseItem` 走 cancel 分支（什么都不扣），但仍然白跑一趟
    ///     ⇒ 先算清楚再动手。
    /// </summary>
    internal static class ToolUpgradeRules
    {
        // ---- 失败码（与卡面/IL 文档逐字一致） ----
        public const string StatusOk = "ok";
        public const string StatusAlreadyUpgrading = "already_upgrading";
        public const string StatusStillWorking = "still_working";
        public const string StatusNoSlot = "no_slot";
        public const string StatusReadOnly = "read_only";
        public const string StatusNoMoney = "no_money";
        public const string StatusNoTradeItem = "no_trade_item";
        public const string StatusToolNotOffered = "tool_not_offered";
        public const string StatusShopUnavailable = "shop_unavailable";
        public const string StatusPurchaseNoEffect = "purchase_no_effect";
        public const string StatusToolMissing = "tool_missing";
        public const string StatusNothingToPickup = "nothing_to_pickup";
        public const string StatusWrongLocation = "wrong_location";

        // ---- `actedEvidence` 的枚举（新技能专用；不冒充 task-182 的四类） ----
        public const string EvidenceMoney = "money";
        public const string EvidenceTradeItem = "trade_item";
        public const string EvidenceToolBeingUpgraded = "tool_being_upgraded";
        public const string EvidenceInventory = "inventory";

        /// <summary>
        /// 买前自检：返回 <c>""</c> = 可以买；否则返回失败码（顺序即优先级）。
        /// </summary>
        /// <param name="requireFreeSlot">
        /// 买下时**不**需要空格（旧工具被移走后位置空出来，见 IL §2.2）；
        /// 取回时需要（`blacksmith()` 的 pickup 分支：`freeSpotsInInventory() &lt;= 0` ⇒ 拿不到）。
        /// </param>
        internal static string Precheck(UpgradePrecheck s, bool requireFreeSlot)
        {
            if (s.AlreadyUpgrading) return StatusAlreadyUpgrading;
            if (s.DaysLeft > 0) return StatusStillWorking;
            if (requireFreeSlot && s.FreeSlots <= 0) return StatusNoSlot;
            if (s.ShopReadOnly) return StatusReadOnly;
            if (s.Price > 0 && s.Money < s.Price) return StatusNoMoney;
            if (s.TradeNeed > 0 && s.TradeHave < s.TradeNeed) return StatusNoTradeItem;
            return "";
        }

        /// <summary>
        /// 从货架里选目标条目：**kind 相同且 Tier == tierBefore + 1** 且**唯一**。
        /// 0 条 / 多条都 fail-closed（`tool_not_offered`，note 里列在售表）——
        /// 买错条目不可逆（钱和 5 条锭当场扣掉）。
        /// </summary>
        internal static UpgradePickResult Select(IReadOnlyList<UpgradeOfferInput> offers, string kind, int tierBefore)
        {
            var pick = new UpgradePickResult();
            if (offers == null)
            {
                pick.Status = StatusShopUnavailable;
                pick.Note = "拿不到 ClintUpgrade 的在售表（ShopBuilder.GetShopStock 返回 null）";
                return pick;
            }
            var hits = new List<int>();
            for (int i = 0; i < offers.Count; i++)
            {
                if (!SameKind(offers[i].Kind, kind)) continue;
                if (offers[i].Tier != tierBefore + 1) continue;
                hits.Add(i);
            }
            if (hits.Count == 1)
            {
                pick.Index = hits[0];
                pick.Status = StatusOk;
                return pick;
            }
            pick.Status = StatusToolNotOffered;
            pick.Note = (hits.Count == 0
                ? $"货架里没有「{kind}」的 {tierBefore + 1} 级条目（当前 {tierBefore} 级）"
                : $"货架里有 {hits.Count} 条「{kind}」{tierBefore + 1} 级条目（不唯一 ⇒ fail-closed）")
                + $"；在售：{Describe(offers)}";
            return pick;
        }

        /// <summary>工具种类归一化：`wateringcan`/`watering_can` ⇒ `can`；大小写不敏感。</summary>
        internal static string NormalizeKind(string kind)
        {
            string k = (kind ?? "").Trim().ToLowerInvariant().Replace("_", "");
            if (k == "wateringcan") return "can";
            if (k == "fishingrod") return "fishingRod";
            return k;
        }

        internal static bool SameKind(string a, string b)
            => string.Equals(NormalizeKind(a), NormalizeKind(b), StringComparison.OrdinalIgnoreCase);

        /// <summary>
        /// 一次动作"真的发生了"的证据来源（优先级：升级在途 &gt; 材料减少 &gt; 钱减少 &gt; 背包增加）。
        /// 全不命中 ⇒ <c>null</c>（调用方必须据此判 <c>acted=false</c>，不许拿回执当证据）。
        /// </summary>
        internal static string Evidence(bool upgradeAppeared, bool tradeReduced, bool moneyReduced, bool inventoryGained)
        {
            if (upgradeAppeared) return EvidenceToolBeingUpgraded;
            if (tradeReduced) return EvidenceTradeItem;
            if (moneyReduced) return EvidenceMoney;
            if (inventoryGained) return EvidenceInventory;
            return null;
        }

        internal static bool Acted(string evidence) => !string.IsNullOrEmpty(evidence);

        /// <summary>把在售表渲染成一行人话（失败回执/日志用）。</summary>
        internal static string Describe(IReadOnlyList<UpgradeOfferInput> offers)
        {
            if (offers == null) return "(拿不到)";
            if (offers.Count == 0) return "(空)";
            var sb = new StringBuilder();
            for (int i = 0; i < offers.Count; i++)
            {
                if (i > 0) sb.Append(" / ");
                UpgradeOfferInput o = offers[i];
                sb.Append(o.Name ?? o.Id ?? "?");
                sb.Append("(kind=").Append(o.Kind ?? "?");
                sb.Append(", tier=").Append(o.Tier);
                sb.Append(", price=").Append(o.Price);
                if (!string.IsNullOrEmpty(o.TradeItem))
                    sb.Append(", trade=").Append(o.TradeItem).Append(" x").Append(o.TradeCount);
                sb.Append(')');
            }
            return sb.ToString();
        }
    }
}
