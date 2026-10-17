using System;
using System.Collections.Generic;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-210】`place_object`：把背包里的**可放置物**（熔炉 `(BC)114` 是第一个用例）放到指定格。
    ///
    /// ==================================================================
    /// 【入口与扣物品（task-211 IL 定案）】只走 <c>Utility.tryToPlaceItem(loc, obj, px, py)</c>（public static）：
    ///   `playerCanPlaceItemHere` 判定 → `item.placementAction(...)` → 成功则 `player.reduceActiveItemByOne()`。
    ///   **扣物品是游戏自己做的**；我们**绝不**手写 `reduceActiveItemByOne` / 手写扣背包
    ///   （0.7.19 播种"放了没扣"事故的同类教训；重复扣 = 多扣一件）。
    ///
    /// 【返回值不可信】IL 实证：`tryToPlaceItem` 对**非家具**的放置失败也 `return true`
    /// （`scratch/il-mc-4.txt:1374-1545`）⇒ 判据必须是**观测**：
    ///   ①目标格上真的出现了这个物体（`loc.objects` 同格 + qid 一致）；
    ///   ②背包里那件恰好 −1（游戏扣的）。
    /// 两个都成立才算成功；一个成立一个不成立 ⇒ 各自如实报（绝不自补扣/自补放）。
    ///
    /// 【前置】要把物品选成 `CurrentItem`（`CurrentToolIndex`）：`tryToPlaceItem` 末尾的
    /// `reduceActiveItemByOne` 作用在当前选中物上；不选就扣错东西。
    ///
    /// 【fail-closed】`no_object`（背包里找不到那件可放置物）/ `tile_occupied`（格子上已有东西）/
    /// `placement_failed`（没放上去也没扣）/ `placement_failed_consumed`（扣了但没放上去 —— 需要人工看）/
    /// `not_consumed`（放上去了但背包没减 —— 不许自己补扣）。
    ///
    /// 【单 tick 同步技能】不加入 `BridgeHost.IsLongTaskSkill`。
    /// ==================================================================
    /// </summary>
    internal sealed class PlaceObjectSkill
    {
        private readonly ExecRequest _req;
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;

        private bool _started;
        private bool _done;
        private DateTime _startedAtUtc;
        private long _seqBefore;

        public PlaceObjectSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._req = req;
            this._world = world;
            this._monitor = monitor;
        }

        private long Elapsed() => this._started ? (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds : 0;

        private ExecResponse Fail(string status, string reason)
            => new ExecResponse
            {
                Ok = false, Status = status, Skill = "place_object", Reason = reason,
                Schema = Skills.ExecSchema, ElapsedMs = this.Elapsed(),
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };

        private static List<ObjectSlotInput> SnapshotSlots()
        {
            var slots = new List<ObjectSlotInput>();
            try
            {
                var items = Game1.player?.Items;
                if (items == null) return slots;
                for (int i = 0; i < items.Count; i++)
                {
                    Item it = items[i];
                    if (it == null) { slots.Add(null); continue; }
                    var row = new ObjectSlotInput { Index = i, IsObject = it is StardewValley.Object };
                    try { row.QualifiedId = it.QualifiedItemId; } catch { }
                    try { row.ItemId = it.ItemId; } catch { }
                    try { row.Name = it.DisplayName; } catch { }
                    try { row.Stack = it.Stack; } catch { }
                    try { row.MaxStack = it.maximumStackSize(); } catch { }
                    slots.Add(row);
                }
            }
            catch { }
            return slots;
        }

        private static StardewValley.Object ObjectAt(GameLocation loc, int x, int y)
        {
            try
            {
                if (loc?.objects == null) return null;
                StardewValley.Object o;
                return loc.objects.TryGetValue(new Microsoft.Xna.Framework.Vector2(x, y), out o) ? o : null;
            }
            catch { return null; }
        }

        public object Step()
        {
            if (this._done)
                return this.Fail("error", "place_object 是一次性单 tick 技能：同一请求不许重复执行");
            this._done = true;

            if (!Context.IsWorldReady || Game1.player == null)
                return this.Fail("no_save", "尚未加载存档，无法放置");

            this._started = true;
            this._startedAtUtc = DateTime.UtcNow;
            this._seqBefore = this._world?.WorldSeq ?? 0;

            // ---- 参数 ----
            int[] tileArg = this._req?.Args?.Tile;
            if (tileArg == null || tileArg.Length < 2)
                return this.Fail("bad_args", "缺少参数 args.tile（目标格 [x, y]）");
            int x = tileArg[0], y = tileArg[1];
            string wanted = this._req?.Args?.Item;
            if (string.IsNullOrWhiteSpace(wanted))
                return this.Fail(MachineRules.StatusNoObject,
                    "缺少参数 args.item（要放的物品：qualifiedId / ItemId / 名字子串，例 \"(BC)114\"）");

            GameLocation loc = Game1.currentLocation;
            if (loc == null)
                return this.Fail("no_save", "读不到当前地点，无法放置");

            // ---- 目标格必须是空的（放置不可逆，宁可少放不许乱放）----
            if (ObjectAt(loc, x, y) != null)
                return this.Fail(MachineRules.StatusTileOccupied,
                    $"目标格 ({x},{y}) 上已经有放置物（qid={SafeQid(ObjectAt(loc, x, y))}）⇒ 换个空格");

            // ---- 在背包里找那件可放置物 ----
            var slots = SnapshotSlots();
            int slot = MachineRules.FindObjectSlot(slots, wanted);
            if (slot < 0)
                return this.Fail(MachineRules.StatusNoObject,
                    $"背包里找不到可放置物「{wanted}」（按 qualifiedId → ItemId → 名字子串匹配；找不到 fail-closed，不猜）");

            Item item = Game1.player.Items[slot];
            var obj = item as StardewValley.Object;
            if (obj == null)
                return this.Fail(MachineRules.StatusNoObject, $"槽位 {slot} 的物品「{wanted}」不是 Object，无法放置");

            int stackBefore = 0;
            try { stackBefore = obj.Stack; } catch { }
            string qid = SafeQid(obj);

            // ---- 选成当前物品（扣物品作用在 CurrentItem 上）----
            try { Game1.player.CurrentToolIndex = slot; }
            catch (Exception ex)
            {
                return this.Fail("error", $"设 CurrentToolIndex={slot} 失败（无法保证扣对物品，不做）：{ex.Message}");
            }

            bool reported;
            try
            {
                reported = Utility.tryToPlaceItem(loc, obj, x * 64 + 32, y * 64 + 32);
            }
            catch (Exception ex)
            {
                return this.Fail("error",
                    $"Utility.tryToPlaceItem 抛异常（可能已放/已扣，请用 observe 复核）：{ex.GetType().Name}: {ex.Message}");
            }

            // ---- 判据 = 观测（返回值不可信，见类注释）----
            StardewValley.Object placedObj = ObjectAt(loc, x, y);
            string placedQid = SafeQid(placedObj);
            bool placed = placedObj != null
                          && (string.Equals(placedQid, qid, StringComparison.OrdinalIgnoreCase)
                              || (placedQid.Length > 0 && qid.Length > 0
                                  && placedQid.EndsWith(qid, StringComparison.OrdinalIgnoreCase)));

            int stackAfter = 0;
            bool slotEmpty = false;
            try
            {
                var again = Game1.player.Items[slot];
                slotEmpty = again == null;
                if (again != null) stackAfter = again.Stack;
            }
            catch { }
            bool consumed = slotEmpty || stackAfter == stackBefore - 1;

            this._monitor?.Log($"[place_object] {qid} → ({x},{y}) reported={reported} placed={placed} consumed={consumed}");

            if (placed && consumed)
            {
                return new ExecResponse
                {
                    Ok = true, Status = MachineRules.StatusOk, Skill = "place_object",
                    Reason = $"已把 {qid} 放到 ({x},{y})：观测到格子上出现该物体、背包 −1"
                             + $"（游戏入口 reported={reported}，不采信）",
                    Schema = Skills.ExecSchema, ElapsedMs = this.Elapsed(),
                    WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                    ReachedLocation = StepMover.CurrentLocationName(),
                    ObjectQid = qid, Placed = true, Consumed = true,
                    Acted = true, ActedEvidence = "tile",
                };
            }

            if (!placed && consumed)
                return this.Fail(MachineRules.StatusPlaceFailedConsumed,
                    $"背包 −1 但 ({x},{y}) 上没出现物体（reported={reported}）⇒ 请人工复核："
                    + "不自己补扣、不自己补放");

            if (placed && !consumed)
                return this.Fail(MachineRules.StatusNotConsumed,
                    $"格子上出现物体但背包没减（reported={reported}）⇒ 游戏入口没扣，**不自己补扣**"
                    + "（可能已扣别的槽/别的物品，补扣会多扣）");

            return this.Fail(MachineRules.StatusPlaceFailed,
                $"放置没生效：({x},{y}) 上没出现物体、背包也没减（reported={reported} 不可信）"
                + "；常见原因：目标格不可放 / 玩家够不着 / 该物品不是可放置物");
        }

        private static string SafeQid(Item it)
        {
            if (it == null) return "";
            try { return it.QualifiedItemId ?? ""; } catch { return ""; }
        }
    }
}
