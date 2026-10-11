using System;
using Microsoft.Xna.Framework;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Tools;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【P3 步骤③】<c>use_tool</c>：**用当前选中的工具对某一格动手**（砍树枝 / 敲石头 / 割草 / 锄地 / 浇水）。
    ///
    /// 请求：<c>{"skill":"use_tool","args":{"tile":[x,y],"tool":"axe|pickaxe|hoe|can|scythe|auto"}}</c>
    /// （<c>tile</c> 省略时用"玩家面朝的那一格"；<c>tool</c> 省略＝<c>auto</c>）
    ///
    /// ==================================================================
    ///  一、为什么这样实现（纪律：调游戏自己的入口，不伪造键鼠）
    /// ==================================================================
    /// * **"按下使用键"用游戏自己的入口** <c>Game1.pressUseToolButton()</c>
    ///   （api-probe 第 12 轮编译期实证存在）。它与玩家真的按键走的是同一条代码；
    ///   我们**没有**合成任何键鼠事件。同源先例：`interact` 用 `GameLocation.checkAction`、
    ///   `dismiss_modal` 用 `answerDialogue`。
    /// * **选工具**用 <c>Game1.player.CurrentToolIndex</c>（api-probe 实证可写）——
    ///   等价于玩家滚动快捷栏。选完**必须复核** <c>CurrentTool</c> 的类型，回执里报出真实用的那件物品。
    /// * **朝向**：工具作用的是"面朝的那一格"，所以先按目标格算出方向再 `faceDirection`，
    ///   否则 `pressUseToolButton` 会朝错地方（真机上表现为"挥了但没效果"）。
    /// * ⚠️ `Farmer.UseTool(...)` / `completeToolUse()` 在 1.6.15 上**不存在**（CS1061，api-probe 证伪）
    ///   ⇒ 不要试图"直接对坐标用工具"。
    ///
    /// ==================================================================
    ///  二、判据（条目 013/016 的教训：绝不拿"我发了动作"当"事情做成了"）
    /// ==================================================================
    /// 技能**只看游戏状态**：
    ///   * 每次挥动后等 <c>player.UsingTool</c> 从 true 回到 false（动画结束）才判定；
    ///   * 终态判据是**目标格上的东西没了**（<c>location.objects</c> 里那一格不存在了）；
    ///   * 挥够 <see cref="MaxSwings"/> 次还在 ⇒ 如实报 <c>tool_ineffective</c>（可能是工具不对/等级不够/体力不足）。
    /// 回执里给"用的哪件物品 / 挥了几次 / 该格前后的 objId"，方便脑审计；
    /// 但**权威证据永远是脑自己 observe 的 `location.tiles[]` 差分**（回执只是声明）。
    ///
    /// ==================================================================
    ///  三、`auto` 怎么选工具（对着 tiles[] 的同一套分类）
    /// ==================================================================
    /// 树枝→斧、可敲石头→镐、杂草/草→镰刀（没有镰刀就用任意 MeleeWeapon）、空耕地→锄、耕地→水壶。
    /// 找不到合适工具 ⇒ <c>precondition_failed</c>，reason 里列出玩家实际拥有的工具（脑可以据此改策略）。
    /// </summary>
    internal sealed class UseToolSkill
    {
        /// <summary>最多挥几次（石头可能要敲两下；再多说明工具不对）。</summary>
        private const int MaxSwings = 6;

        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly int _timeoutMs;
        private readonly string _wantTool;
        private readonly Point _target;

        private bool _started;
        private DateTime _startedAtUtc;
        private long _seqBefore;
        private int _swings;
        private string _toolUsed;        // 实际用的那件物品名（回执要报出来）
        private string _wantedKind;      // 当前在试哪一类工具（hoe/can/axe/…）；Done() 按它选判据
        private string _objIdBefore;     // 动手前该格的 objId（没有则 null）
        private bool _sawUsingTool;      // 是否至少观察到一次"正在用工具"

        // ---- auto：按顺序试可用工具（真机教训见下）----
        // 真机实测（2026-10-11）：**杂草是用锄头清掉的**（`use_tool(tool="hoe")` 一次 524ms，
        // 该格从 tiles[] 消失、体力 266→264）；我原先把 weed 映射成 scythe，
        // 结果是"挥了 6 次 UsingTool 始终 false、格子纹丝不动"（`tool_ineffective`）。
        // 这说明"哪个工具能清哪种东西"**必须以游戏为准、并且要能换工具重试** ——
        // 于是 auto 变成一条**候选工具序列**：先按种类猜，失败就换下一个，直到格子真的变了。
        private System.Collections.Generic.List<string> _plan;
        private int _planIndex;
        private readonly System.Collections.Generic.List<string> _attemptText = new System.Collections.Generic.List<string>();

        public UseToolSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._world = world;
            this._monitor = monitor;
            this._timeoutMs = Skills.ClampTimeout(req?.TimeoutMs);
            this._wantTool = string.IsNullOrWhiteSpace(req?.Args?.Tool) ? "auto" : req.Args.Tool.Trim().ToLowerInvariant();

            int[] tile = req?.Args?.Tile;
            this._target = (tile != null && tile.Length >= 2)
                ? new Point(tile[0], tile[1])
                : new Point(int.MinValue, int.MinValue);
        }

        private long Elapsed() => (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds;

        private ExecResponse Fail(string status, string reason, long elapsedMs)
            => new ExecResponse
            {
                Ok = false, Status = status, Skill = "use_tool", Reason = reason,
                Schema = Skills.ExecSchema, ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };

        private ExecResponse Ok(long elapsedMs)
            => new ExecResponse
            {
                Ok = true, Status = "ok", Skill = "use_tool",
                Reason = $"已用「{this._toolUsed}」对 {StepMover.FormatTile(this._target)} 动手 {this._swings} 次，"
                       + $"该格原本是 {(this._objIdBefore ?? "（空）")}，现在**已经空了**（请用 observe 的 tiles[] 复核）",
                Schema = Skills.ExecSchema, ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };

        /// <summary>每次被主线程调用：返回 null = 还在挥；非 null = 终态。</summary>
        public object Step()
        {
            try
            {
                if (!this._started) return this.Begin();

                long elapsed = this.Elapsed();
                if (elapsed >= this._timeoutMs)
                {
                    StepMover.HaltPlayer();
                    return this.Fail("timeout",
                        $"use_tool 超时（{this._timeoutMs}ms）：已挥 {this._swings} 次（用「{this._toolUsed}」），"
                        + $"目标格 {StepMover.FormatTile(this._target)} 上仍有东西。"
                        + "常见原因：工具不对/等级不够/体力不足/目标不在可作用范围内", elapsed);
                }

                // 工具动画期间什么都不做（也别催它）
                bool usingTool = false;
                try { usingTool = Game1.player != null && Game1.player.UsingTool; } catch { }
                if (usingTool)
                {
                    this._sawUsingTool = true;
                    return null;
                }

                // 动画结束：看**这一格是不是变成了它该有的样子**（见 Done()：
                // 锄头要"变成耕地"、水壶要"变成已浇水"、斧镐镰刀要"东西没了"——
                // 不能统一用"没有物体"，否则对着空洞挥锄也会报 ok）
                if (this.Done()) return this.Ok(elapsed);

                if (this._swings >= MaxSwings)
                {
                    // 这件工具不行 ⇒ 换下一件（auto 计划里还有的话），并把这次失败记进回执
                    this._attemptText.Add($"「{this._toolUsed}」挥 {this._swings} 次无效（UsingTool={this._sawUsingTool}）");
                    if (this._plan != null && this._planIndex + 1 < this._plan.Count)
                    {
                        this._planIndex++;
                        this._wantedKind = this._plan[this._planIndex];
                        this._swings = 0;
                        this._sawUsingTool = false;
                        string why2;
                        int slot2 = this.FindToolSlot(this._plan[this._planIndex], out why2);
                        if (slot2 >= 0)
                        {
                            try { Game1.player.CurrentToolIndex = slot2; } catch { }
                            try { this._toolUsed = Game1.player.CurrentItem?.DisplayName ?? "?"; } catch { this._toolUsed = "?"; }
                            this._monitor?.Log($"use_tool：换工具 → {this._toolUsed}", LogLevel.Info);
                            this.Swing();
                            return null;
                        }
                        this._attemptText.Add($"（{this._plan[this._planIndex]} 没有：{why2}）");
                    }

                    StepMover.HaltPlayer();
                    return this.Fail("tool_ineffective",
                        $"use_tool 试过的工具都无效：{string.Join("；", this._attemptText)}；目标格 "
                        + $"{StepMover.FormatTile(this._target)} 上仍有东西 ⇒ 目标不在作用范围/等级不够/体力不足。", elapsed);
                }

                this.Swing();
                return null;
            }
            catch (Exception ex)
            {
                StepMover.HaltPlayer();
                return this.Fail("error", "use_tool 执行异常：" + ex.GetType().Name + ": " + ex.Message,
                    this._started ? this.Elapsed() : 0);
            }
        }

        private object Begin()
        {
            this._started = true;
            this._startedAtUtc = DateTime.UtcNow;
            try { this._seqBefore = this._world?.WorldSeq ?? 0; } catch { }

            if (!Context.IsWorldReady || Game1.player == null || Game1.currentLocation == null)
                return this.Fail("no_save", "尚未加载存档，无法执行 use_tool", 0);

            if (StepMover.UiBlocked())
                return this.Fail("ui_modal", "当前有菜单/对话/过场打开，无法使用工具（请先关闭模态）", 0);

            Point target = this._target;
            if (target.X == int.MinValue)
            {
                // 省略 tile ⇒ 用玩家面朝的那一格
                var p = Game1.player;
                int x = p.TilePoint.X, y = p.TilePoint.Y;
                switch (p.FacingDirection)
                {
                    case 0: y--; break;
                    case 1: x++; break;
                    case 2: y++; break;
                    default: x--; break;
                }
                target = new Point(x, y);
            }
            this._targetOverride = target;

            // ---- 选工具（auto 时先按种类猜，后面留好"换工具重试"的余地）----
            this._plan = this.BuildPlan(target);
            this._planIndex = 0;
            this._wantedKind = this._plan[0];

            // 【先判后动（用户 m01668 提的）】动工具之前先问游戏"这一格该不该/能不能这么处理"。
            // 只对**空洞**（既没有放置物也没有地形特征）套锄地判据 —— 那正是"打算锄出新耕地"的情形；
            // 格子上本来有杂草/石头时，锄/斧/镐各有各的动作，不该用这条拦（真机：锄杂草不产耕地，但确实能除草）。
            try
            {
                var v = new Vector2(target.X, target.Y);
                bool hasObj = false, hasTf = false;
                try { hasObj = Game1.currentLocation?.objects != null && Game1.currentLocation.objects.ContainsKey(v); } catch { }
                try { hasTf = Game1.currentLocation?.terrainFeatures != null && Game1.currentLocation.terrainFeatures.ContainsKey(v); } catch { }

                if (!hasObj && !hasTf && string.Equals(this._plan[0], "hoe", StringComparison.OrdinalIgnoreCase))
                {
                    string whyNot;
                    if (!StepMover.Tillable(Game1.currentLocation, target, out whyNot))
                    {
                        return this.Fail("precondition_failed",
                            $"目标格 {StepMover.FormatTile(target)} 不能锄：{whyNot}。"
                            + "请换一格可锄的 —— observe?detail=full 的 `location.tillable[]` 就是**全部可锄空格**。"
                            + "这条是先判后动：不再对不可锄的格子白挥 6 次", 0);
                    }
                }
            }
            catch { }

            string why;
            int slot = this.FindToolSlot(this._plan[0], out why);
            if (slot < 0)
                return this.Fail("precondition_failed", why, 0);

            try { Game1.player.CurrentToolIndex = slot; } catch { }

            // ---- 复核选中的到底是什么（回执必须报真话）----
            try { this._toolUsed = Game1.player.CurrentItem?.DisplayName ?? Game1.player.CurrentItem?.Name ?? "?"; }
            catch { this._toolUsed = "?"; }

            try { this._objIdBefore = ObjectIdAt(target); } catch { }

            this.Swing();
            return null;
        }

        /// <summary>因为 Begin 里可能把"面朝格"解析成具体坐标，终态判定要用解析后的目标。</summary>
        private Point _targetOverride;
        private Point Target => this._targetOverride == default(Point) ? this._target : this._targetOverride;

        private void Swing()
        {
            this._swings++;
            try
            {
                // 1) 先转向目标格（工具作用的是面朝的那一格）
                var p = Game1.player;
                int dx = this.Target.X - p.TilePoint.X;
                int dy = this.Target.Y - p.TilePoint.Y;
                int dir = (Math.Abs(dx) >= Math.Abs(dy)) ? (dx > 0 ? 1 : (dx < 0 ? 3 : 2)) : (dy > 0 ? 2 : 0);
                p.faceDirection(dir);

                // 2) 调游戏自己的"使用键"入口（不合成键鼠）
                Game1.pressUseToolButton();
            }
            catch (Exception ex)
            {
                this._monitor?.Log($"use_tool Swing 异常：{ex.GetType().Name}: {ex.Message}", LogLevel.Warn);
            }
        }

        // ==================================================================
        //  工具选择
        // ==================================================================

        /// <summary>
        /// 生成"先试哪把工具"的候选序列。
        ///
        /// 【真机教训】杂草是**锄头**清掉的（hoe 一次成功），不是镰刀 —— 原映射 weed→scythe 让
        /// 6 次挥动全部无效。所以：先按种类猜，再把其余工具依次垫在后面，
        /// 由 `Step()` 里"挥满 MaxSwings 就换下一件"来兜底。
        /// </summary>
        private System.Collections.Generic.List<string> BuildPlan(Point target)
        {
            var plan = new System.Collections.Generic.List<string>();
            if (this._wantTool != "auto")
            {
                plan.Add(this._wantTool);
                return plan;
            }

            string kind = ClassifyTile(target);
            bool hasCrop = false;
            try { hasCrop = CropAt(target) != null; } catch { }

            // 按种类首选（含真机已证实的三条：twig→axe、stone→pickaxe、weed→hoe）
            switch (kind)
            {
                case "twig": plan.Add("axe"); break;
                case "stone": plan.Add("pickaxe"); break;
                case "weed": plan.Add("hoe"); break;                 // ← 真机实证：锄头除草
                case "dirt": plan.Add(hasCrop ? "can" : "hoe"); break;
                case "grass": plan.Add("scythe"); break;
                case "tree":
                case "clump": plan.Add("axe"); break;
                default: break;
            }

            // 兜底顺序：把还没试过的都垫上（找不到的工具会被 FindToolSlot 跳过并记录）
            foreach (string t in new[] { "hoe", "axe", "pickaxe", "can", "scythe" })
            {
                if (!plan.Contains(t)) plan.Add(t);
            }
            return plan;
        }

        /// <summary>按请求/自动判断找背包里合适的工具槽位；找不到时给出可操作的 reason。</summary>
        private int FindToolSlot(string want, out string reason)
        {
            reason = null;
            if (string.IsNullOrEmpty(want)) want = "any";

            var items = Game1.player.Items;
            int fallback = -1;
            for (int i = 0; i < items.Count; i++)
            {
                Item it = items[i];
                if (it == null) continue;

                bool hit = false;
                switch (want)
                {
                    case "axe": hit = it is Axe; break;
                    case "pickaxe": hit = it is Pickaxe; break;
                    case "hoe": hit = it is Hoe; break;
                    case "can": hit = it is WateringCan; break;
                    case "scythe": hit = it is MeleeWeapon || (it is Tool && (it.ItemId == "47" || it.ItemId == "53")); break;   // 真机实证：镰刀在 1.6.15 是 Tool(id=47)；金镰刀 53
                    default: hit = it is Tool; break;                 // any：任意工具
                }
                if (hit) return i;
                if (fallback < 0 && it is Tool) fallback = i;
            }

            if (fallback >= 0 && want == "any") return fallback;

            reason = $"背包里找不到「{want}」这类工具（目标格 {StepMover.FormatTile(this.Target)} 需要它）。"
                   + $"当前拥有的工具：{DescribeTools()}。"
                   + "可改用 args.tool 显式指定，或先回屋/去商店取工具";
            return -1;
        }

        private static string DescribeTools()
        {
            var parts = new System.Collections.Generic.List<string>();
            try
            {
                var items = Game1.player.Items;
                for (int i = 0; i < items.Count; i++)
                {
                    Item it = items[i];
                    if (it is Tool) parts.Add($"[{i}]{it.Name}");
                }
            }
            catch { }
            return parts.Count > 0 ? string.Join("、", parts) : "（一件都没有）";
        }

        /// <summary>目标格上的东西是什么（与 `location.tiles[]` 同一套判据）。</summary>
        private static string ClassifyTile(Point p)
        {
            try
            {
                var loc = Game1.currentLocation;
                var v = new Vector2(p.X, p.Y);
                StardewValley.Object o = null;
                try { if (loc.objects != null) loc.objects.TryGetValue(v, out o); } catch { }
                if (o != null)
                {
                    try { if (o.IsWeeds()) return "weed"; } catch { }
                    try { if (o.IsTwig()) return "twig"; } catch { }
                    try { if (o.IsBreakableStone()) return "stone"; } catch { }
                    return "object";
                }

                StardewValley.TerrainFeatures.TerrainFeature tf = null;
                try { if (loc.terrainFeatures != null) loc.terrainFeatures.TryGetValue(v, out tf); } catch { }
                if (tf is StardewValley.TerrainFeatures.Grass) return "grass";
                if (tf is StardewValley.TerrainFeatures.HoeDirt) return "dirt";
                if (tf is StardewValley.TerrainFeatures.Tree) return "tree";
            }
            catch { }
            return "none";
        }

        private static object CropAt(Point p)
        {
            try
            {
                var loc = Game1.currentLocation;
                var v = new Vector2(p.X, p.Y);
                StardewValley.TerrainFeatures.TerrainFeature tf = null;
                if (loc.terrainFeatures != null) loc.terrainFeatures.TryGetValue(v, out tf);
                if (tf is StardewValley.TerrainFeatures.HoeDirt hd && hd.crop != null) return hd.crop;
            }
            catch { }
            return null;
        }

        /// <summary>
        /// 按"这一格现在应该长成什么样"判断做完了没。**这是条目 022 之后最重要的修正**：
        /// 旧判据统一是"该格没有物体"，而空洞本来就没有物体 ⇒ **对着房子墙边的空地挥锄也会报 ok**，
        /// 真机就踩到了（报告"已经空了"，可那格根本没有 HoeDirt）。
        /// 现在按工具分别判定：
        ///   * `hoe` → 该格**变成耕地**（HoeDirt）；
        ///   * `can` → 该格是耕地**且已浇水**；
        ///   * 其余（axe/pickaxe/scythe）→ 该格上的**物体没了**（树/资源堆/果树这类地形也算"东西"）。
        /// </summary>
        private bool Done()
        {
            try
            {
                var loc = Game1.currentLocation;
                var v = new Vector2(this.Target.X, this.Target.Y);

                bool hasObject = false;
                try { hasObject = loc?.objects != null && loc.objects.ContainsKey(v); } catch { }

                StardewValley.TerrainFeatures.TerrainFeature tf = null;
                try { if (loc?.terrainFeatures != null) loc.terrainFeatures.TryGetValue(v, out tf); } catch { }

                var hd = tf as StardewValley.TerrainFeatures.HoeDirt;
                bool watered = false;
                if (hd != null) { try { watered = hd.isWatered(); } catch { } }

                string kind = this._wantedKind ?? "";
                if (kind == "hoe") return hd != null;
                if (kind == "can") return hd != null && watered;

                if (hasObject) return false;
                if (tf is StardewValley.TerrainFeatures.Tree) return false;
                if (tf is StardewValley.TerrainFeatures.FruitTree) return false;
                if (tf is StardewValley.TerrainFeatures.ResourceClump) return false;
                return true;
            }
            catch { return false; }
        }

        private static bool HasObjectAt(Point p)
        {
            try
            {
                var loc = Game1.currentLocation;
                if (loc?.objects == null) return false;
                return loc.objects.ContainsKey(new Vector2(p.X, p.Y));
            }
            catch { return false; }
        }

        private static string ObjectIdAt(Point p)
        {
            try
            {
                var loc = Game1.currentLocation;
                StardewValley.Object o = null;
                if (loc?.objects != null) loc.objects.TryGetValue(new Vector2(p.X, p.Y), out o);
                return o?.ItemId;
            }
            catch { return null; }
        }
    }
}
