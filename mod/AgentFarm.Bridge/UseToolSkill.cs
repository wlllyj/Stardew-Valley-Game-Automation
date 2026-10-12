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
    /// * **"按下使用键"按工具类型分派**（见 <see cref="Swing"/>）：
    ///   ① 非近战（Hoe / WateringCan / Axe / Pickaxe）⇒ 走游戏自己的入口
    ///      <c>Game1.pressUseToolButton()</c>（api-probe 第 12 轮编译期实证存在）。它与玩家真的按键
    ///      走的是同一条代码；v0.7.19 / v0.7.21 真机反复验收过（锄地 `kind=dirt`、浇水 `watered=true`、
    ///      水量 0→40），**不许顺手改**；
    ///   ② 近战武器（镰刀/武器）⇒ `pressUseToolButton()` 内部有一道输入门闸，桥驱动时恒为 false
    ///      （task-3 的 IL 证据：`IL_0826 isinst MeleeWeapon` / `IL_0833 call didPlayerJustLeftClick` /
    ///      `IL_0838 brfalse`），改走 <see cref="BeginUse"/> 照抄门闸**之后**那段。
    ///   两条路**都没有**合成任何键鼠事件。同源先例：`interact` 用 `GameLocation.checkAction`、
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
        private bool _deferredByFade;    // 渐黑/过场挡住起手 ⇒ Step() 报可重试状态（不是挥不动）

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
        {
            // 回执要说清**凭什么**算成功：`Done()` 是按 `_wantedKind` 分支判的，文案也必须分支 ——
            // 否则"已经空了"会被读成"这一格空了"（锄地是把空格**变成耕地**，不是变空；
            // 而 scythe 加 `Grass` 判据之前，草格会拿到"已经空了"的假 ok）。
            string what;
            if (this._wantedKind == "hoe") what = "现在**已经是耕地**（HoeDirt）";
            else if (this._wantedKind == "can") what = "现在**已经浇过水**（HoeDirt.watered=true）";
            else what = $"现在**上面已经没有东西了**（kind=「{this.KindNow()}」）";
            return new ExecResponse
            {
                Ok = true, Status = "ok", Skill = "use_tool",
                Reason = $"已用「{this._toolUsed}」对 {StepMover.FormatTile(this._target)} 动手 {this._swings} 次"
                       + $"（起手={this.StartedText()}），该格原本是 {(this._objIdBefore ?? "（空）")}，{what}"
                       + "（请用 observe 的 tiles[] 复核）",
                Schema = Skills.ExecSchema, ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };
        }

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
                        $"use_tool 超时（{this._timeoutMs}ms）：已挥 {this._swings} 次（用「{this._toolUsed}」，"
                        + $"起手={this.StartedText()}），目标格 {StepMover.FormatTile(this._target)} 上仍有东西，"
                        + $"现在还是「{this.KindNow()}」。"
                        + "常见原因：工具不对/等级不够/体力不足/目标不在可作用范围内/屏幕一直在渐黑或过场",
                        elapsed);
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

                // 渐黑/过场挡住起手（Swing() 里那道门）⇒ 报**可重试**状态：
                // 这不是"这一格干不动"，脑只许记 failed、不许封格（下一轮世界恢复就能做）。
                if (this._deferredByFade)
                {
                    StepMover.HaltPlayer();
                    return this.Fail("world_fading",
                        $"屏幕正在渐黑/过场（fadeToBlack/nonWarpFade）⇒ 现在起手也是白挥，use_tool 未执行"
                        + $"（已挥 {this._swings} 次）。这是**可重试**状态：等世界恢复后重发即可。", elapsed);
                }

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
                        + $"{StepMover.FormatTile(this._target)} 上仍有东西（现在还是「{this.KindNow()}」，"
                        + $"起手={this.StartedText()}）⇒ 目标不在作用范围/等级不够/体力不足。", elapsed);
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
            // 0) 渐黑/过场期间**游戏自己也会拒绝起手** —— 这是 `pressUseToolButton` 的第一道门卫：
            //    `IL_001C: call Boolean get_fadeToBlack(); IL_0021: brfalse.s IL_0025; IL_0023: ldc.i4.0; ret`
            //    近战那条路我们绕开了 game 入口（见 BeginUse），所以这道门要自己补上；非近战那条路
            //    游戏内部本来也有这道门。无论哪条路，渐黑时挥了都是白挥（世界不推进、动画不结算、
            //    格子不会变）⇒ 不挥，记下"被环境挡住"交给 Step() 报**可重试**状态（world_fading）。
            if (WorldFading())
            {
                this._deferredByFade = true;
                return;
            }
            this._swings++;
            try
            {
                // 1) 先转向目标格（工具作用的是面朝的那一格）
                var p = Game1.player;
                int dx = this.Target.X - p.TilePoint.X;
                int dy = this.Target.Y - p.TilePoint.Y;
                int dir = (Math.Abs(dx) >= Math.Abs(dy)) ? (dx > 0 ? 1 : (dx < 0 ? 3 : 2)) : (dy > 0 ? 2 : 0);
                p.faceDirection(dir);

                // 2) 按工具分派 —— **只对近战武器**绕开游戏入口，其余工具一个字都别改：
                //
                //    * MeleeWeapon（镰刀/武器）⇒ 走 BeginUse()。task-3 证明过的 IL 门闸只对这类成立：
                //        IL_0826 CurrentTool → IL_082B isinst MeleeWeapon → IL_0830 brfalse IL_083D
                //        IL_0832 ldc.i4.1 → IL_0833 call didPlayerJustLeftClick(true) → IL_0838 brfalse IL_0913
                //      而 didPlayerJustLeftClick() 只认真实输入边沿（鼠标左键本帧刚按下 / 手柄 X /
                //      键盘 useToolButton），桥驱动时恒为 false ⇒ 镰刀一刀都挥不出去
                //      （真机取证：非 grass 7/7 成功、grass 5/5 失败，镰刀就在背包里）。
                //
                //    * Hoe / WateringCan / Axe / Pickaxe ⇒ **原样走 Game1.pressUseToolButton()**。
                //      这是 v0.7.19 / v0.7.21 真机反复验收过的路（锄地 kind=dirt、浇水 watered=true、
                //      水壶水量 0→40 都过了），task-3 的门闸与它们无关；它自带 fadeToBlack 门卫、
                //      LowPriorityLeftClick、tryToPlaceItem、体力耗尽的抖动提示。run3 只剩一次真机机会，
                //      **不许顺手把已验证路径换成未验证路径**。
                bool melee = false;
                try { melee = p != null && p.CurrentTool is MeleeWeapon; } catch { }

                if (!melee)
                {
                    Game1.pressUseToolButton();
                }
                else if (!this.BeginUse(p))
                {
                    // 兜底：拿不到 player/工具时退回游戏入口（它对镰刀仍会被门闸挡住，但至少不崩）
                    Game1.pressUseToolButton();
                }
            }
            catch (Exception ex)
            {
                this._monitor?.Log($"use_tool Swing 异常：{ex.GetType().Name}: {ex.Message}", LogLevel.Warn);
            }
        }

        /// <summary>
        /// 真·起手一次工具 —— **只用于近战武器（镰刀/武器）**，由 <see cref="Swing"/> 按工具类型分派调用；
        /// 其余工具（Hoe / WateringCan / Axe / Pickaxe）**原样**走 <c>Game1.pressUseToolButton()</c>，不经过这里。
        /// 返回 false = 没起手（调用方退回 Game1.pressUseToolButton()）。
        ///
        /// 【为什么要绕开 pressUseToolButton()】它内部对**近战武器**有一道输入门闸：
        ///   IL_0826 player.CurrentTool → IL_082B isinst MeleeWeapon → IL_0830 brfalse IL_083D
        ///   IL_0832 ldc.i4.1 → IL_0833 call Game1.didPlayerJustLeftClick(true) → IL_0838 brfalse IL_0913
        /// 而 didPlayerJustLeftClick() 只认真实输入边沿（鼠标左键**本帧刚按下** / 手柄 X / 键盘 useToolButton），
        /// 桥驱动时恒为 false ⇒ 直接 return，**不 BeginUsingTool、镰刀一刀都挥不出去**。
        /// 真机取证：run1 里非 grass 7/7 全成功、grass 5/5 全失败（0 成功），而镰刀就在背包里。
        ///
        /// 这里改为照抄它在门闸**之后**的那段（IL_083D-IL_08BD）：
        ///   savedFacing = player.FacingDirection
        ///   toolLoc = player.GetToolLocation(clickPx, false)
        ///   player.FacingDirection = player.getGeneralDirectionTowards(toolLoc, 0, false, true)
        ///   player.lastClick = clickPx
        ///   player.BeginUsingTool()
        /// 唯一的改动是把真机里"人手鼠标的像素位置"换成**目标格中心**（自动化里没有鼠标，用目标格更准）。
        ///
        /// 【为什么 BeginUsingTool() 就够】它只做一件事：fire `beginUsingToolEvent`；而该事件在
        /// `Farmer.initNetFields()` 里挂的是 `Farmer.performBeginUsingTool()`：
        ///   CurrentTool == null ? return; CanMove=false; UsingTool=true; canReleaseTool=true;
        ///   CurrentTool.beginUsing(currentLocation, (int)lastClick.X, (int)lastClick.Y, this);
        /// 对镰刀（MeleeWeapon）这条路会走 `MeleeWeapon.setFarmerAnimating(who)`，它在**同一次调用内**就执行了
        ///   who.lastClick = Vector2.Zero; Vector2 tl = who.GetToolLocation(true);
        ///   MeleeWeapon.DoDamage(loc, (int)tl.X, (int)tl.Y, who.FacingDirection, 1, who);
        /// 而 `GetToolLocation(true)`（ignoreClick=true）是**纯 FacingDirection 派生**的 ⇒
        /// 割不割得到草只取决于朝向 + 站位，与鼠标无关。
        /// </summary>
        private bool BeginUse(Farmer p)
        {
            if (p == null || p.CurrentTool == null) return false;
            try
            {
                // 目标格中心的像素坐标（真机这里的来源是鼠标位置）
                var clickPx = new Vector2(this.Target.X * 64 + 32, this.Target.Y * 64 + 32);
                var toolLoc = p.GetToolLocation(clickPx, false);
                p.FacingDirection = p.getGeneralDirectionTowards(
                    new Vector2((int)toolLoc.X, (int)toolLoc.Y), 0, false, true);
                p.lastClick = clickPx;
                p.BeginUsingTool();
                // 回执要报真话：这次到底起手了没有（镰刀的 DoDamage 是同一调用内结算的）
                try { this._sawUsingTool = this._sawUsingTool || p.UsingTool; } catch { }
                return true;
            }
            catch (Exception ex)
            {
                this._monitor?.Log($"use_tool BeginUse 异常，退回 pressUseToolButton：{ex.GetType().Name}: {ex.Message}",
                    LogLevel.Warn);
                return false;
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
        /// <summary>回执里报"这格现在到底是什么"（别拿"应该是"糊弄）。</summary>
        private string KindNow()
        {
            try { return ClassifyTile(this.Target); } catch { return "unknown"; }
        }

        /// <summary>回执里报"这次到底起手了没有"（镰刀被输入门闸挡住时会是"否"）。</summary>
        private string StartedText() => this._sawUsingTool ? "是" : "否";

        /// <summary>屏幕正在渐黑/过场？`pressUseToolButton` 的第一道门卫就是 `get_fadeToBlack`：
        /// `IL_001C: call Boolean get_fadeToBlack(); IL_0021: brfalse.s IL_0025; IL_0023: ldc.i4.0; ret`
        /// （证据 `scratch/il-grass-1-u8.txt:177-246`）。`nonWarpFade` 是"非传送引起的渐黑"
        /// （睡觉/过场）。两者任一为真都不该起手 —— 挥了世界也不推进、动画不结算。</summary>
        private static bool WorldFading()
        {
            try { return Game1.fadeToBlack || Game1.nonWarpFade; } catch { return false; }
        }

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
                // 草是**多刀**地形特征：`Grass.performToolAction` 只把 numberOfWeeds 减 1（金镰刀减 2），
                // 只有减到 0 才移除特征。所以"还是草"必须算没做完 —— 原实现漏了这条，
                // 会对着草回 "已经空了" 的假回执（真机 run1 的 5/5 grass 假 ok 就有这一半责任）。
                if (tf is StardewValley.TerrainFeatures.Grass) return false;
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
