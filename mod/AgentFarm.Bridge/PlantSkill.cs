using System;
using Microsoft.Xna.Framework;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【P3 步骤④】`select_item` / `plant`。
    ///
    /// * <c>select_item</c>（**短任务**）：`{"item":"472"}` → 找到背包里那件（先比 `ItemId`，再比
    ///   `QualifiedItemId`，最后比名字）→ 设 `CurrentToolIndex` → **复核** `CurrentItem` 真的是它，
    ///   回执报出槽位与物品名。拿不到就 `precondition_failed` 并把背包清单列出来（脑据此换策略）。
    /// * <c>plant</c>（**跨 tick 长任务**）：`{"seed":"472","tile":[x,y]}` → 先选种子 →
    ///   校验目标格是**空耕地**（`HoeDirt` 且 `crop == null`）→ 面向目标格 →
    ///   ① `Game1.pressUseToolButton()`（玩家"选中种子对着地按使用键"的路径）；
    ///   ② 若没生效，退到**游戏自己的** `ActiveObject.performUseAction(tile, location)`
    ///      （同一件事的另一个官方入口，api-probe 实证存在）；
    ///   ③ 都没有 ⇒ 如实报 `plant_failed`，并把两条路径的结果写进 reason。
    ///
    /// **判据只有一个**：目标格上**真的出现了作物**（`HoeDirt.crop != null`）。
    /// 回执里的说法只是声明；脑必须用自己的 `tiles[]` 差分复核（条目 013/016/022 的一贯纪律）。
    /// **不自己调** `HoeDirt.plant(...)`（那是直接写状态，属于作弊路径；本文件刻意不用它）。
    /// </summary>
    internal sealed class SelectItemSkill
    {
        private readonly WorldObserver _world;
        private readonly string _want;

        public SelectItemSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._world = world;
            this._want = req?.Args?.Item?.Trim();
        }

        public object Step()
        {
            long seq = 0;
            try { seq = this._world?.WorldSeq ?? 0; } catch { }

            if (!Context.IsWorldReady || Game1.player == null)
                return Fail("no_save", "尚未加载存档，无法 select_item", seq);

            if (string.IsNullOrEmpty(this._want))
                return Fail("precondition_failed", "缺少 args.item（物品 ItemId / QualifiedItemId / 名字）", seq);

            string why;
            int slot = FindItemSlot(this._want, out why);
            if (slot < 0)
                return Fail("precondition_failed",
                    $"{why}。当前背包：{DescribeInventory()}", seq);

            try { Game1.player.CurrentToolIndex = slot; } catch { }

            string gotId = null, gotName = null;
            try { gotId = Game1.player.CurrentItem?.ItemId; gotName = Game1.player.CurrentItem?.DisplayName; } catch { }

            if (!ItemMatches(gotId, gotName, this._want))
            {
                return Fail("select_failed",
                    $"已把 CurrentToolIndex 设为 {slot}，但复核到的当前物品是「{gotName}」({gotId})，与请求「{this._want}」不符"
                    + "（游戏的快捷栏选择没有生效）", seq);
            }

            return new ExecResponse
            {
                Ok = true, Status = "ok", Skill = "select_item", Schema = Skills.ExecSchema,
                Reason = $"已选中槽位 {slot}：「{gotName}」({gotId})",
                ElapsedMs = 0, WorldSeqBefore = seq, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };
        }

        private static ExecResponse Fail(string status, string reason, long seq)
            => new ExecResponse
            {
                Ok = false, Status = status, Skill = "select_item", Reason = reason,
                Schema = Skills.ExecSchema, WorldSeqBefore = seq,
            };

        // ---- 共用工具（PlantSkill 也调） ----

        /// <summary>按 id / qualifiedId / 名字找背包槽位（大小写不敏感）。</summary>
        internal static int FindItemSlot(string want, out string reason)
        {
            reason = null;
            try
            {
                var items = Game1.player?.Items;
                if (items == null) { reason = "读不到背包（Items 为空）"; return -1; }

                for (int i = 0; i < items.Count; i++)
                {
                    Item it = items[i];
                    if (it == null) continue;
                    string id = null, qid = null, name = null;
                    try { id = it.ItemId; } catch { }
                    try { qid = it.QualifiedItemId; } catch { }
                    try { name = it.DisplayName ?? it.Name; } catch { }
                    if (ItemMatches(id, name, want) || ItemMatches(qid, name, want)) return i;
                }
                reason = $"背包里找不到「{want}」";
            }
            catch (Exception ex) { reason = "枚举背包失败：" + ex.GetType().Name + ": " + ex.Message; }
            return -1;
        }

        internal static bool ItemMatches(string id, string name, string want)
        {
            if (string.IsNullOrEmpty(want)) return false;
            if (!string.IsNullOrEmpty(id) && string.Equals(id, want, StringComparison.OrdinalIgnoreCase)) return true;
            if (!string.IsNullOrEmpty(name) && string.Equals(name, want, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        internal static string DescribeInventory()
        {
            var parts = new System.Collections.Generic.List<string>();
            try
            {
                var items = Game1.player?.Items;
                if (items != null)
                {
                    for (int i = 0; i < items.Count; i++)
                    {
                        Item it = items[i];
                        if (it == null) continue;
                        parts.Add($"[{i}]{it.DisplayName ?? it.Name}({it.ItemId})x{it.Stack}");
                    }
                }
            }
            catch { }
            return parts.Count > 0 ? string.Join("、", parts) : "（空）";
        }
    }

    /// <summary><c>plant</c>：把种子种进已经锄好的格子里（见 <see cref="SelectItemSkill"/> 的类注释）。</summary>
    internal sealed class PlantSkill
    {
        /// <summary>每条路径最多等多少帧再判（60fps 下约 1 秒）；最多按几次使用键。</summary>
        private const int WaitFrames = 60;
        private const int MaxAttempts = 3;

        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly int _timeoutMs;
        private readonly string _seed;
        private readonly Point _target;

        private bool _started;
        private DateTime _startedAtUtc;
        private long _seqBefore;
        private int _frames;
        private int _attempts;
        private int _path;                   // 0=还没试 leftClick，1=还没试 placementAction
        private int _slot = -1;              // 种子在背包里的槽位（诊断 + 不依赖 ActiveObject）
        private string _plantRule;           // 游戏自己的判据：CanPlantSeedsHere(...) 的答案
        private readonly System.Collections.Generic.List<string> _pathsTried =
            new System.Collections.Generic.List<string>();
        private bool _sawUsingTool;          // 路径①「按使用键」期间 UsingTool 是否真的变成过 true
        private string _pathLog = "";        // 路径逐步日志（成功回执也带上，便于日后复盘）
        private string _seedUsed;
        private string _consumptionNote = "";   // 物品消耗诊断（v0.7.19：placementAction 不扣物品这个 bug）
        private int _seedStackBefore = -1;      // 播种前该种子在背包里的堆叠（写进回执，便于差分核对）
        private int _seedStackAfter = -1;       // 播种后（含补扣）的堆叠

        public PlantSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._world = world;
            this._monitor = monitor;
            this._timeoutMs = Skills.ClampTimeout(req?.TimeoutMs);
            this._seed = req?.Args?.Seed?.Trim();
            int[] tile = req?.Args?.Tile;
            this._target = (tile != null && tile.Length >= 2) ? new Point(tile[0], tile[1]) : new Point(int.MinValue, int.MinValue);
        }

        private long Elapsed() => (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds;

        public object Step()
        {
            try
            {
                if (!this._started) return this.Begin();

                long elapsed = this.Elapsed();
                if (elapsed >= this._timeoutMs)
                    return this.Fail("timeout", $"plant 超时（{this._timeoutMs}ms）：已按 {this._attempts} 次使用键，"
                        + $"目标格 {StepMover.FormatTile(this._target)} 仍没有作物", elapsed);

                if (this.HasCrop()) return this.Ok(elapsed);

                this._frames++;
                if (this._frames < WaitFrames) return null;
                this._frames = 0;

                // ---- 路径①：按使用键（玩家那条路），最多 MaxAttempts 次 ----
                if (this._attempts < MaxAttempts)
                {
                    this._attempts++;
                    this.FaceTarget();
                    try { Game1.pressUseToolButton(); } catch { }
                    // 记录"使用键到底有没有启动一次动作"：种子这条路真机一直是 false —— 这条事实
                    // 是后来改走 placementAction 的直接依据（见下方长注释），必须留在回执里。
                    try { if (Game1.player.UsingTool) this._sawUsingTool = true; } catch { }
                    return null;
                }

                // ---- 路径②：游戏自己的"在某一格按下"入口 `GameLocation.leftClick(x,y,player)` ----
                // 【为什么直接指定格子】`Game1.pressUseToolButton()` 在"鼠标这一帧可见"时，
                // 目标是**鼠标所在格**（IL：`wasMouseVisibleThisFrame ? 鼠标世界坐标 : GetToolLocation(false)`），
                // 而无人值守时鼠标停在哪完全不可控 ⇒ 工具那几条路（走 GetToolLocation）没事，种子这条路会被带偏。
                // 所以我们绕开鼠标，直接对目标格调它最终要调的那个入口。
                if (this._path == 0)
                {
                    this._path = 1;
                    bool ok2 = this.TryLeftClick();
                    this._pathsTried.Add($"②leftClick({this._target.X},{this._target.Y}) 返回 {ok2}");
                    return null;
                }

                // ---- 路径③：`Object.placementAction`（IL 探针 FIND 到它内部的 lambda 才调 HoeDirt.plant）----
                if (this._path == 1)
                {
                    this._path = 2;
                    string detail;
                    bool consumed;
                    bool ok3 = this.TryPlacementAction(out detail, out consumed);
                    this._pathsTried.Add($"③placementAction 返回 {ok3}{detail}");
                    // 【真机 bug 修复：种子不消耗】详见 TryPlacementAction 上方长注释与
                    // EnforceItemConsumed 的 IL 依据（`Game1.pressActionButton` IL_0752–IL_0776）。
                    // 只在"作物已种下、但物品没被扣"时补扣，且只走游戏自己的入口。
                    if (this.HasCrop()) this.EnforceItemConsumed(consumed);
                    return null;
                }

                return this.Fail("plant_failed",
                    $"种子没能种下：用「{this._seedUsed}」对 {StepMover.FormatTile(this._target)} —— "
                    + $"①按了 {this._attempts} 次使用键无效（UsingTool={this._sawUsingTool}）；"
                    + string.Join("；", this._pathsTried)
                    + $"；游戏自己的判据：{this._plantRule ?? "（没取到）"}"
                    + $"；鼠标这一帧可见={this.MouseVisible()}（鼠标格 {this.MouseTile()}，面朝格 {this.FacedTile()}）",
                    elapsed);
            }
            catch (Exception ex)
            {
                StepMover.HaltPlayer();
                return this.Fail("error", "plant 执行异常：" + ex.GetType().Name + ": " + ex.Message,
                    this._started ? this.Elapsed() : 0);
            }
        }

        private object Begin()
        {
            this._started = true;
            this._startedAtUtc = DateTime.UtcNow;
            try { this._seqBefore = this._world?.WorldSeq ?? 0; } catch { }

            if (!Context.IsWorldReady || Game1.player == null || Game1.currentLocation == null)
                return this.Fail("no_save", "尚未加载存档，无法 plant", 0);

            if (StepMover.UiBlocked())
                return this.Fail("ui_modal", "当前有菜单/对话/过场打开，无法播种（请先关闭模态）", 0);

            if (string.IsNullOrEmpty(this._seed))
                return this.Fail("precondition_failed",
                    $"缺少 args.seed（种子 ItemId，例 472=防风草种子）。当前背包：{SelectItemSkill.DescribeInventory()}", 0);

            if (this._target.X == int.MinValue)
                return this.Fail("precondition_failed", "缺少 args.tile（要播种的耕地格）", 0);

            // 目标格必须是**空耕地**
            string why;
            if (!IsPlantableDirt(out why))
                return this.Fail("precondition_failed",
                    $"目标格 {StepMover.FormatTile(this._target)} 不能播种：{why}（应先用 use_tool 锄地）", 0);

            // 选种子
            string why2;
            int slot = SelectItemSkill.FindItemSlot(this._seed, out why2);
            if (slot < 0)
                return this.Fail("precondition_failed", $"{why2}。当前背包：{SelectItemSkill.DescribeInventory()}", 0);
            // 【显式报错，不静默】格子是空的却没法种，最常见的原因就是种子用完了
            //（v0.7.19 之前"placementAction 不扣物品"掩盖了这一点：种子永远不会用完）。
            var seedStack = (Game1.player.Items?[slot] as StardewValley.Object)?.Stack ?? 0;
            if (seedStack <= 0)
                return this.Fail("precondition_failed",
                    $"背包里「{this._seed}」这一格堆叠为 {seedStack}，没有种子可种。"
                    + $"当前背包：{SelectItemSkill.DescribeInventory()}", 0);
            try { Game1.player.CurrentToolIndex = slot; } catch { }
            this._slot = slot;
            try { this._seedUsed = Game1.player.CurrentItem?.DisplayName ?? this._seed; } catch { this._seedUsed = this._seed; }
            // 记下播种前的堆叠：回执里给出"种一格 → 少一个"的可核对数字（v0.7.19）
            try { this._seedStackBefore = (Game1.player.Items?[slot] as StardewValley.Object)?.Stack ?? -1; } catch { }

            // 顺手问游戏自己的判据："这一格能不能种这个种子"（IL 探针 FIND 出来的官方入口）。
            // 把答案写进回执 —— 播种失败时它就是**最有信息量**的那一句。
            try
            {
                string denied = null;
                bool can = Game1.currentLocation.CanPlantSeedsHere(
                    this._seed, this._target.X, this._target.Y, false, out denied);
                this._plantRule = $"CanPlantSeedsHere={can}"
                                + (string.IsNullOrEmpty(denied) ? "" : $"（denied：{denied}）");
            }
            catch (Exception ex) { this._plantRule = "CanPlantSeedsHere 调用失败：" + ex.GetType().Name; }

            // 再往下追一层：`Object.placementAction` 的 IL 显示它依次调
            //   `GameLocation.ResolveSeedId(ActiveObject.ItemId, loc)` → `HoeDirt.canPlantThisSeedHere(seedId, false)`
            //   → `HoeDirt.plant(seedId, who, false)`，任一为 false 就返回 false。
            // 这三步都在**耕地**这一层，与地点层的 `CanPlantSeedsHere` 不是一回事 —— 所以逐个问出来。
            try
            {
                StardewValley.TerrainFeatures.TerrainFeature tf = null;
                Game1.currentLocation.terrainFeatures?.TryGetValue(
                    new Vector2(this._target.X, this._target.Y), out tf);
                var hd = tf as StardewValley.TerrainFeatures.HoeDirt;
                if (hd != null)
                {
                    // ⚠️ `GameLocation.ResolveSeedId(String, GameLocation)` 在 Mod 侧**不可访问**（CS0117，
                    //    它是 internal/private）⇒ 直接用调用方给的种子 id（例 472）；只有"混合种子"那类
                    //    需要按季节解析的情况才会与游戏内部值不同，届时以回执里的 canPlant 结果为准。
                    string sid = this._seed;
                    bool canPlant = false;
                    try { canPlant = hd.canPlantThisSeedHere(sid, false); } catch { }
                    this._plantRule += $"；ResolveSeedId={sid ?? "?"}；HoeDirt.canPlantThisSeedHere={canPlant}"
                                     + $"；该格 crop={(hd.crop == null ? "null" : "有")}";
                }
                else
                {
                    this._plantRule += "；（该格取不到 HoeDirt）";
                }
            }
            catch (Exception ex) { this._plantRule += "；耕地层判据读取失败：" + ex.GetType().Name; }

            // 面向目标格，然后走第 ① 条路径：游戏自己的"使用键"
            this.FaceTarget();
            try { Game1.pressUseToolButton(); } catch { }
            this._attempts = 1;
            return null;
        }

        // 【第二条路径的由来（真机 + IL 双重证据）】
        // ① `Game1.pressUseToolButton()` 对手里的**种子**不会播种（真机连按 3 次 UsingTool 始终 false）。
        // ② `HoeDirt.performUseAction(Vector2)` **只处理收获**：IL 开头 `if (this.crop == null) { ldc.i4.0; ret }`
        //    ⇒ 空格子上它必然返回 false（真机实测返回 False，与 IL 完全一致）。
        // ③ 于是用新加的 `FIND|<子串>` 模式在**整个程序集里找"谁调用了 HoeDirt.plant"**，命中 17 处，其中一处是
        //    **`Object.placementAction(GameLocation, int, int, Farmer)` 内部的 lambda**
        //    （`Object+<>c__DisplayClass401_2.<placementAction>b__1` → `HoeDirt.plant`）。
        //    ⇒ **"把物品用在这一格"的正规入口就是 `placementAction`**（玩家在游戏里用种子走的就是它）。
        // 我们调的是这个处理器，**不是**自己写状态：种子消耗与作物创建都由游戏完成。
        /// <summary>路径③：`Object.placementAction(GameLocation, int x, int y, Farmer)`。
        ///
        /// ⚠️ **参数是"像素"不是"格"**！IL（`placementAction` 开头）：
        /// `new Vector2(x / 64f, y / 64f)` —— 它自己会除 64 得到格坐标。
        /// 我第一版直接传了格坐标 (64,18) ⇒ 它去查 `(1.0, 0.28)` 那一格的地形特征、当然没有 HoeDirt、
        /// 于是整条播种链一步都没走到就返回 false（真机现象：`canPlantThisSeedHere=True` 却 `placementAction=False`）。
        ///
        /// ⚠️⚠️ **它不扣背包里的物品**（真机 bug，2026-10-11 用户发现）：连续种 20 格，作物都出现了，
        /// 但背包里那包种子**一直是 10 个**。IL 定案：
        ///   * `Object.placementAction` 的 IL 里**没有** `consumeObject`、也没有 `reduceActiveItemByOne`
        ///     （`FIND|consumeObject` 命中 0 个调用方法；`FIND|reduceActiveItemByOne` 的 25 处里没有它）；
        ///   * 真正扣物品的是 **`Game1.pressActionButton`**：它在放置前把 `ActiveObject.Stack` 存进局部变量 10
        ///     （IL_0658），放置后比较 `ActiveObject.Stack < 存下来的值`，**只有变小**才认为消耗成功
        ///     （IL_0752–IL_0776）；而"把种子用进耕地"这条路是 `placementAction` 自己扣的 —— 它是由
        ///     `Utility.tryToPlaceItem` 内部调用的，那条链我们没走。
        /// 所以我们绕开鼠标直接调 `placementAction` 时，缺少"扣物品"这一步 ⇒ 无限种子。
        /// 修法（见 `TryPlacementAction` 的第二个 out 参数 + `EnforceItemConsumed`）：照抄游戏口径 ——
        /// 放置后若 Stack 没变小，就调游戏自己的 `Farmer.reduceActiveItemByOne()` 补上这一次消耗。
        /// </summary>
        private bool TryPlacementAction(out string detail, out bool consumed)
        {
            detail = "";
            consumed = false;
            try
            {
                // 用**背包里那件种子本身**调（不依赖 ActiveObject 是否已经刷新）
                string activeId = null;
                try { activeId = Game1.player?.ActiveObject?.ItemId; } catch { }

                StardewValley.Object obj = null;
                try { if (this._slot >= 0) obj = Game1.player?.Items?[this._slot] as StardewValley.Object; } catch { }
                if (obj == null) obj = Game1.player?.ActiveObject;

                int px = this._target.X * 64, py = this._target.Y * 64;   // 像素坐标（见上面的 ⚠️）
                detail = $"（用物品 {(obj == null ? "null" : obj.ItemId)}，ActiveObject={(activeId ?? "null")}，"
                       + $"像素 {px},{py}）";
                if (obj == null) return false;

                // 游戏自己的口径：放置前记下堆叠，放置后比大小（`Game1.pressActionButton` IL_0658/IL_0752）
                int stackBefore = -1;
                try { stackBefore = obj.Stack; } catch { }

                bool placed = obj.placementAction(Game1.currentLocation, px, py, Game1.player);

                try
                {
                    int stackAfter = obj.Stack;
                    consumed = stackBefore > 0 && stackAfter < stackBefore;
                    detail += $"（Stack {stackBefore}→{stackAfter}，{(consumed ? "已在链内扣掉" : "链内没扣")}）";
                }
                catch { }

                return placed;
            }
            catch (Exception ex) { detail = "（异常：" + ex.GetType().Name + "）"; return false; }
        }

        /// <summary>照抄 `Game1.pressActionButton` 的消耗口径：放置成功后若物品没被扣，就补扣一次。
        ///
        /// 【为什么这不是"乱写游戏状态"】`Farmer.reduceActiveItemByOne()` 是游戏自己扣手持物品的方法
        /// （`Game1.pressActionButton` IL_062C 与 IL_0752–IL_0776 用的就是它/它的判据），
        /// 我们只是把"绕过鼠标直接调 placementAction"时丢掉的那一步补回来，参数与前置条件都与游戏一致。
        /// 只在**作物确实已经种下**（调用方先查 HasCrop()）且**链内没扣**时才补，避免重复扣。
        /// </summary>
        private void EnforceItemConsumed(bool consumed)
        {
            if (consumed) return;
            try
            {
                var p = Game1.player;
                if (p?.ActiveObject == null) { this._consumptionNote = "ActiveObject 为 null，未能补扣"; return; }
                string id = p.ActiveObject.ItemId;
                int before = p.ActiveObject.Stack;
                p.reduceActiveItemByOne();
                int after = -1;
                try { after = (p.Items?[p.CurrentToolIndex] as StardewValley.Object)?.Stack ?? -1; } catch { }
                this._consumptionNote = $"补扣 {id}：Stack {before}→{after}（游戏入口 reduceActiveItemByOne）";
            }
            catch (Exception ex)
            {
                this._consumptionNote = "补扣失败：" + ex.GetType().Name + ": " + ex.Message;
            }
        }

        /// <summary>路径②：游戏自己的"在某一格按下"入口（鼠标路径最终调的就是它）。
        /// 同样**传像素坐标**（与 <see cref="TryPlacementAction"/> 同一口径：它会自己除 64）。</summary>
        private bool TryLeftClick()
        {
            try
            {
                return Game1.currentLocation.leftClick(this._target.X * 64, this._target.Y * 64, Game1.player);
            }
            catch { return false; }
        }

        // ---- 诊断（说明"使用键"被鼠标格带偏这件事）----
        private bool MouseVisible()
        {
            try { return Game1.wasMouseVisibleThisFrame; } catch { return false; }
        }

        private string MouseTile()
        {
            try
            {
                var v = new Vector2(Game1.getOldMouseX() + Game1.viewport.X, Game1.getOldMouseY() + Game1.viewport.Y);
                return $"{(int)(v.X / 64f)},{(int)(v.Y / 64f)}";
            }
            catch { return "?"; }
        }

        private string FacedTile()
        {
            try
            {
                var v = Game1.player.GetToolLocation(false);
                return $"{(int)(v.X / 64f)},{(int)(v.Y / 64f)}";
            }
            catch { return "?"; }
        }

        private void FaceTarget()
        {
            try
            {
                var p = Game1.player;
                int dx = this._target.X - p.TilePoint.X;
                int dy = this._target.Y - p.TilePoint.Y;
                int dir = (Math.Abs(dx) >= Math.Abs(dy)) ? (dx > 0 ? 1 : (dx < 0 ? 3 : 2)) : (dy > 0 ? 2 : 0);
                p.faceDirection(dir);
            }
            catch { }
        }

        private bool IsPlantableDirt(out string why)
        {
            why = null;
            try
            {
                var loc = Game1.currentLocation;
                StardewValley.TerrainFeatures.TerrainFeature tf = null;
                if (loc?.terrainFeatures != null) loc.terrainFeatures.TryGetValue(new Vector2(this._target.X, this._target.Y), out tf);

                if (tf is StardewValley.TerrainFeatures.HoeDirt hd)
                {
                    if (hd.crop != null) { why = "这一格已经有作物了"; return false; }
                    return true;
                }
                if (tf == null)
                {
                    why = "这一格不是耕地（没有 HoeDirt）";
                    return false;
                }
                why = "这一格被别的地形占着（" + tf.GetType().Name + "）";
                return false;
            }
            catch (Exception ex) { why = "读地形失败：" + ex.GetType().Name; return false; }
        }

        private bool HasCrop()
        {
            try
            {
                var loc = Game1.currentLocation;
                StardewValley.TerrainFeatures.TerrainFeature tf = null;
                if (loc?.terrainFeatures != null) loc.terrainFeatures.TryGetValue(new Vector2(this._target.X, this._target.Y), out tf);
                return tf is StardewValley.TerrainFeatures.HoeDirt hd && hd.crop != null;
            }
            catch { return false; }
        }

        private ExecResponse Ok(long elapsed)
        {
            // 播种后的堆叠（差分用）：种一格就该少一个 —— v0.7.19 起这是可核对的事实，而不是假设。
            try { this._seedStackAfter = (Game1.player.Items?[this._slot] as StardewValley.Object)?.Stack ?? 0; } catch { }
            // 成功也把"走过的路径"写进回执：这条日志正是 v0.7.13→v0.7.19 三轮 bug 的取证材料。
            this._pathLog = this._pathsTried.Count == 0
                ? "①pressUseToolButton（没走到②③就成功了）"
                : string.Join("；", this._pathsTried);
            return new ExecResponse
            {
                Ok = true, Status = "ok", Skill = "plant", Schema = Skills.ExecSchema,
                Reason = $"已把「{this._seedUsed}」种进 {StepMover.FormatTile(this._target)}"
                       + $"（按了 {this._attempts} 次使用键，UsingTool={this._sawUsingTool}）；"
                       + $"种子堆叠 {this._seedStackBefore}→{this._seedStackAfter}"
                       + (string.IsNullOrEmpty(this._consumptionNote) ? "" : $"（{this._consumptionNote}）")
                       + $"；路径：{this._pathLog}"
                       + "。请用 observe 的 tiles[] 复核：该格应出现 crop",
                ElapsedMs = elapsed, WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };
        }

        private ExecResponse Fail(string status, string reason, long elapsed)
            => new ExecResponse
            {
                Ok = false, Status = status, Skill = "plant", Reason = reason, Schema = Skills.ExecSchema,
                ElapsedMs = elapsed, WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };
    }
}
