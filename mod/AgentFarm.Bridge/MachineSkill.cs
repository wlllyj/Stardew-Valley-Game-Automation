using System;
using System.Collections.Generic;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-210】`machine`：机器投料 / 取货（熔炉是第一个用例）。
    ///
    /// ==================================================================
    /// 【唯一入口 = 游戏自己的 `checkAction`（task-211 IL 定案 + 真机实证）】
    ///   投料与取货都走 `GameLocation.checkAction(new xTile.Dimensions.Location(x, y), Game1.viewport, player)`：
    ///     * 投料：`checkAction → ... → obj.performObjectDropInAction(who.CurrentItem, false, who)`
    ///       ⇒ **读的是 `who.CurrentItem`**（不是 `ActiveObject`）⇒ 必须先把要投的矿选到快捷栏
    ///       （`player.CurrentToolIndex = slot`），否则投的是别的东西。
    ///     * 取货：`checkAction → ... → MachineData/`Object.checkForAction`` 的 pickup 分支：
    ///       `heldObject` 放回背包（背包满时安全：放回 heldObject + 红字，不吞产物）。
    ///   `checkAction` 内部自带"探测干跑 + 真做"两步 + `ignoreItemConsumptionThisFrame` 防双扣
    ///   ⇒ **绝不要自己调 `performObjectDropInAction` 再自己扣材料**（会双扣）。
    ///
    /// 【判据 = 跨观测差分】（对齐 task-182/188 的 acted 证据纪律）
    ///   投料成功：`heldObject` 变了（空 ⇒ 有 / 变了 qid 或 stack）**或**背包逐 qid 计数减少。
    ///   取货成功：`heldObject` 清空 / `readyForHarvest` 翻转 **或**背包逐 qid 计数增加。
    ///   回执里把证据来源如实写清（`heldObject`/`ready`/`inventory`）；全不命中 ⇒ 如实失败，
    ///   绝不因为 `checkAction` 返回 true 就自称成功（`checkAction` 的返回值只说明"这一格被认领了"）。
    ///
    /// 【fail-closed】`no_machine`（这一格不是机器）/ `not_ready`（还没产出 ⇒ 取货前拦）/
    /// `already_full`（机器里已有东西 ⇒ 投料前拦，熔炉在炼时 heldObject 非空）/
    /// `no_object`（要投的物品不在背包）/ `no_slot`（背包满，取货放不下）/
    /// `not_consumed`（投了但材料没减、机器也没变 —— 不做任何补扣）。
    ///
    /// 【单 tick 同步技能】`checkAction` 是同步的；不加入 `BridgeHost.IsLongTaskSkill`。
    /// ==================================================================
    /// </summary>
    internal sealed class MachineSkill
    {
        private const string ActionFeed = "feed";
        private const string ActionCollect = "collect";

        private readonly ExecRequest _req;
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;

        private bool _started;
        private bool _done;
        private DateTime _startedAtUtc;
        private long _seqBefore;

        public MachineSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._req = req;
            this._world = world;
            this._monitor = monitor;
        }

        private long Elapsed() => this._started ? (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds : 0;

        private ExecResponse Fail(string status, string reason)
            => new ExecResponse
            {
                Ok = false, Status = status, Skill = "machine", Reason = reason,
                Schema = Skills.ExecSchema, ElapsedMs = this.Elapsed(),
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };

        // ---------------------------------------------------------------- 背包

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

        /// <summary>逐 qualifiedId 的背包总件数（用于"投料有没有扣 / 取货有没有进包"的判断）。</summary>
        private static Dictionary<string, int> Counts()
        {
            var map = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            try
            {
                var items = Game1.player?.Items;
                if (items == null) return map;
                for (int i = 0; i < items.Count; i++)
                {
                    Item it = items[i];
                    if (it == null) continue;
                    string qid = "";
                    int stack = 0;
                    try { qid = it.QualifiedItemId ?? ""; } catch { }
                    try { stack = it.Stack; } catch { }
                    if (qid.Length == 0) continue;
                    int cur;
                    map.TryGetValue(qid, out cur);
                    map[qid] = cur + stack;
                }
            }
            catch { }
            return map;
        }

        // ---------------------------------------------------------------- 机器

        private sealed class MachineState
        {
            public bool Present;
            public string HeldQid = "";
            public int HeldStack;
            public bool Ready;
            public int MinutesUntilReady = -1;

            public bool HeldFull => this.Present && (this.HeldQid.Length > 0 || this.HeldStack > 0);
        }

        private static MachineState ReadMachine(GameLocation loc, int x, int y)
        {
            var st = new MachineState();
            try
            {
                if (loc?.objects == null) return st;
                StardewValley.Object o;
                if (!loc.objects.TryGetValue(new Microsoft.Xna.Framework.Vector2(x, y), out o) || o == null) return st;
                if (o.GetMachineData() == null) return st;   // 不是机器（普通物体/家具）
                st.Present = true;
                try
                {
                    StardewValley.Object held = o.heldObject?.Value;
                    if (held != null)
                    {
                        st.HeldQid = held.QualifiedItemId ?? "";
                        st.HeldStack = held.Stack;
                    }
                }
                catch { }
                try { st.Ready = o.readyForHarvest != null && o.readyForHarvest.Value; } catch { }
                try { st.MinutesUntilReady = o.MinutesUntilReady; } catch { st.MinutesUntilReady = -1; }
            }
            catch { }
            return st;
        }

        // ---------------------------------------------------------------- 主流程

        public object Step()
        {
            if (this._done)
                return this.Fail("error", "machine 是一次性单 tick 技能：同一请求不许重复执行");
            this._done = true;

            if (!Context.IsWorldReady || Game1.player == null)
                return this.Fail("no_save", "尚未加载存档，无法操作机器");

            this._started = true;
            this._startedAtUtc = DateTime.UtcNow;
            this._seqBefore = this._world?.WorldSeq ?? 0;

            // ---- 参数 ----
            string action = (this._req?.Args?.Action ?? "").Trim().ToLowerInvariant();
            if (action != ActionFeed && action != ActionCollect)
                return this.Fail("bad_args", $"参数 args.action 必须是 \"{ActionFeed}\" 或 \"{ActionCollect}\"（收到「{action}」）");
            int[] tileArg = this._req?.Args?.Tile;
            if (tileArg == null || tileArg.Length < 2)
                return this.Fail("bad_args", "缺少参数 args.tile（机器所在格 [x, y]）");
            int x = tileArg[0], y = tileArg[1];

            GameLocation loc = Game1.currentLocation;
            if (loc == null)
                return this.Fail("no_save", "读不到当前地点，无法操作机器");

            var before = ReadMachine(loc, x, y);
            if (!before.Present)
                return this.Fail(MachineRules.StatusNoMachine,
                    $"({x},{y}) 上没有机器（`objects` 里没有物体或 `GetMachineData()` 为空）⇒ 不猜");

            var invBefore = Counts();

            // ---- 前置分类（fail-closed，不白白调 checkAction）----
            if (action == ActionFeed)
            {
                string pre = MachineRules.ClassifyFeed(true, before.HeldFull);
                if (pre != MachineRules.StatusOk)
                    return this.Fail(pre, $"机器里已有东西（heldObject = {DescribeHeld(before)}）⇒ 等它产出并取货后再投料");

                string wanted = this._req?.Args?.Item;
                if (string.IsNullOrWhiteSpace(wanted))
                    return this.Fail(MachineRules.StatusNoObject,
                        "投料必须给 args.item（要投进去的物品：qualifiedId / ItemId / 名字子串，例 \"(O)378\" 铜矿）");
                var slots = SnapshotSlots();
                int slot = MachineRules.FindObjectSlot(slots, wanted);
                if (slot < 0)
                    return this.Fail(MachineRules.StatusNoObject, $"背包里找不到投料「{wanted}」");
                Item item = Game1.player.Items[slot];
                if (!(item is StardewValley.Object))
                    return this.Fail(MachineRules.StatusNoObject, $"槽位 {slot} 的物品「{wanted}」不是 Object");

                try { Game1.player.CurrentToolIndex = slot; }
                catch (Exception ex)
                {
                    return this.Fail("error",
                        $"设 CurrentToolIndex={slot} 失败（checkAction 读的是 CurrentItem，选不对就会投错物品 ⇒ 不做）：{ex.Message}");
                }
            }

            // ---- 游戏入口（唯一入口；绝不自调 performObjectDropInAction）----
            bool handled;
            try
            {
                handled = loc.checkAction(new xTile.Dimensions.Location(x, y), Game1.viewport, Game1.player);
            }
            catch (Exception ex)
            {
                return this.Fail("error",
                    $"checkAction 抛异常（可能已部分生效，请用 observe 复核）：{ex.GetType().Name}: {ex.Message}");
            }

            // ---- 判据 = 跨观测差分 ----
            var after = ReadMachine(loc, x, y);
            var invAfter = Counts();

            bool heldChanged = before.HeldQid != after.HeldQid || before.HeldStack != after.HeldStack;
            bool readyFlipped = before.Ready != after.Ready;
            bool inventoryChanged = !SameCounts(invBefore, invAfter);
            string evidence = MachineRules.Evidence(heldChanged, readyFlipped, inventoryChanged);

            this._monitor?.Log(
                $"[machine] {action} ({x},{y}) handled={handled} held {DescribeHeld(before)} → {DescribeHeld(after)}"
                + $" ready={before.Ready}→{after.Ready} invChanged={inventoryChanged} evidence={evidence ?? "none"}");

            if (evidence != null)
            {
                return new ExecResponse
                {
                    Ok = true, Status = MachineRules.StatusOk, Skill = "machine",
                    Reason = $"{ActionWord(action)}成功：观测到世界变化（证据来源 `{evidence}`；"
                             + $"heldObject {DescribeHeld(before)} → {DescribeHeld(after)}，ready {before.Ready} → {after.Ready}，"
                             + $"背包逐 qid 计数{(inventoryChanged ? "有变化" : "无变化")}；checkAction 返回 {handled} 不采信）",
                    Schema = Skills.ExecSchema, ElapsedMs = this.Elapsed(),
                    WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                    ReachedLocation = StepMover.CurrentLocationName(),
                    MachineAction = action,
                    HeldObject = string.IsNullOrEmpty(after.HeldQid) ? null : new HeldObjectView { Id = after.HeldQid, Stack = after.HeldStack },
                    MachineReady = after.Ready,
                    MinutesUntilReady = after.MinutesUntilReady >= 0 ? after.MinutesUntilReady : (int?)null,
                    Acted = true, ActedEvidence = evidence,
                };
            }

            // 没有任何观测变化 ⇒ 如实失败（checkAction 的返回值不算证据）
            if (action == ActionFeed)
                return this.Fail(MachineRules.StatusNotConsumed,
                    $"投料没有生效：`heldObject` 没变（{DescribeHeld(before)}）、背包逐 qid 计数也没减少"
                    + $"（checkAction 返回 {handled}，不采信）⇒ 常见原因：机器不接受这种材料 / 机器已满 / 玩家够不着");
            return this.Fail(MachineRules.StatusNothingHeld,
                $"取货没有生效：`heldObject` 没变（{DescribeHeld(before)}）、`readyForHarvest` 没翻转、背包也没增加"
                + $"（checkAction 返回 {handled}，不采信）⇒ 常见原因：还没产出 / 玩家够不着 / 背包已满且产物放不下");
        }

        private static string ActionWord(string action) => action == ActionFeed ? "投料" : "取货";

        private static string DescribeHeld(MachineState st)
        {
            if (!st.Present) return "（不是机器）";
            if (string.IsNullOrEmpty(st.HeldQid) && st.HeldStack == 0) return "空";
            return $"{st.HeldQid} × {st.HeldStack}";
        }

        private static bool SameCounts(Dictionary<string, int> a, Dictionary<string, int> b)
        {
            if (a.Count != b.Count) return false;
            foreach (var kv in a)
            {
                int other;
                if (!b.TryGetValue(kv.Key, out other) || other != kv.Value) return false;
            }
            return true;
        }
    }
}
