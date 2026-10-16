using System;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Menus;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-129 / 0.7.29 P0】`dismiss_modal` 遇到**出货菜单 / 存档菜单**时的跨 tick 路径：
    /// 推游戏自己点 OK，然后**只等**游戏把「出货 → 日切保存 → 换天」这条链走完。
    ///
    /// ==================================================================
    /// 【事故：run9 四天 0 次落盘，整跑作废】
    /// 出货日的日切保存**唯一入口在 `ShippingMenu.update()` 内部**（`docs/_il-shipmenu-save.md`，
    /// commit 8fdd3bb）：只有私有字段 `outro == true`（= 玩家点了 OK ⇒ 私有 `okClicked()`）
    /// 之后才会 `new SaveGameMenu()` ⇒ `SaveGame.Save()`。
    /// 旧代码在 `ModalDismiss` 里对一切非对话模态一律 `menu.exitThisMenu()`（:106）⇒ `outro` 永假
    /// ⇒ **永不出存档菜单**；而 `Game1._update`（IL_120B-127C）只要求「夜菜单栈空 + 无活动菜单」
    /// 就推进到早晨 ⇒ **日推进、盘不落、没有任何闸门会拦**（SMAPI 日志里
    /// `Context: before save.` / `SaveGame.Save() called.` 一次都没有，存档 start==end）。
    ///
    /// 【三条铁律（后人不要"优化"回去）】
    ///   ① `ShippingMenu` / `SaveGameMenu` / `NewDaySavingMenu` **禁止** `exitThisMenu()` /
    ///      `emergencyShutDown()`：前者会让日切保存永久丢失，后者正把盘写出去；
    ///   ② `ShippingMenu` 只走游戏自己的 OK 路径：反射私有 `okClicked()`（等价玩家点 OK），
    ///      发出后**什么都不做**，等游戏自己关（800ms outro + 铭牌 + 700ms + 保存 + 2000ms）；
    ///   ③ 反射不可用时兜底"点 okButton 中心"：必须 `currentPage == -1 && CanReceiveInput()`
    ///      （`introTimer > 0` 期间 `receiveLeftClick` 会被静默丢弃），且**按间隔重试到菜单消失**。
    ///
    /// 【合法性】反射调 `okClicked()` 与点 `okButton` 都等价于玩家点 OK，不涉及特权操作。
    /// ==================================================================
    /// </summary>
    internal sealed class ShippingMenuDismissSkill
    {
        /// <summary>兜底路径下两次点 OK 之间的间隔（`introTimer` 走完之前点了没用，所以要重试）。</summary>
        private const int ClickRetryMs = 700;

        /// <summary>推出去之后、菜单真空期的宽限：至少等这么久再相信"真的没菜单了"。</summary>
        private const int EmptyGraceMs = 1500;

        public const int WaitMinMs = 5000;
        public const int WaitMaxMs = 120000;
        public const int WaitDefaultMs = 20000;

        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly int _timeoutMs;

        private bool _started;
        private DateTime _startedAtUtc;
        private long _seqBefore;
        private string _menu0 = "";
        private bool _pushed;
        private bool _sawSaveMenu;
        private string _path = "(未动手)";
        private string _pathNote = "";
        private long _lastClickAt = long.MinValue;

        public ShippingMenuDismissSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._world = world;
            this._monitor = monitor;
            this._timeoutMs = ClampBudget(req?.TimeoutMs);
        }

        /// <summary>
        /// 出货 → 保存 → 换天这条链在真机上一秒到十几秒都可能，默认 8s 的上限不够，
        /// 所以这一类单独给一个预算区间（脑侧也要相应地把 budget 提上来）。
        /// </summary>
        public static int ClampBudget(int? timeoutMs)
        {
            int v = timeoutMs ?? WaitDefaultMs;
            if (v < WaitMinMs) v = WaitMinMs;
            if (v > WaitMaxMs) v = WaitMaxMs;
            return v;
        }

        /// <summary>本技能只接管这三类菜单；其它模态仍走单 tick 的 `ModalDismiss.Dismiss()`。</summary>
        public static bool Applies()
        {
            try
            {
                IClickableMenu menu = Game1.activeClickableMenu;
                return menu is ShippingMenu || ModalDismiss.IsSaveMenu(menu);
            }
            catch { return false; }
        }

        private long Elapsed() => (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds;

        /// <summary>主线程调用：返回非 null = 终态；返回 null = 还在等游戏自己走完。</summary>
        public object Step()
        {
            long seq = 0;
            try { seq = this._world?.WorldSeq ?? 0; } catch { }

            if (!Context.IsWorldReady || Game1.player == null)
                return this.Fail("no_save", "尚未加载存档，无法处理出货/保存菜单", 0);

            if (!this._started)
            {
                this._started = true;
                this._startedAtUtc = DateTime.UtcNow;
                this._seqBefore = seq;
                this._menu0 = ModalDismiss.SafeMenuName();
            }

            long elapsed = this.Elapsed();
            IClickableMenu menu = null;
            try { menu = Game1.activeClickableMenu; } catch { }

            // ---- ① 存档菜单：只等（保存中关掉会毁档）----
            if (ModalDismiss.IsSaveMenu(menu))
            {
                this._sawSaveMenu = true;
                this._path = "wait_only";
                if (elapsed > this._timeoutMs)
                {
                    return this.Fail("timeout",
                        $"存档菜单（{menu.GetType().Name}）等了 {elapsed}ms 还没消失；"
                        + "本技能只等不关（保存中关掉会毁档）—— 请查 SMAPI 的 SaveGame 日志确认保存是否完成，"
                        + "必要时人工处理", elapsed);
                }
                return null;
            }

            // ---- ② 出货菜单：推一次（反射 okClicked，失败退回点 okButton），之后只等 ----
            if (menu is ShippingMenu ship)
            {
                if (!this._pushed)
                {
                    this._pushed = true;

                    string note;
                    if (ModalDismiss.TryInvokeOkClicked(ship, out note))
                    {
                        this._path = "ok_clicked";
                        this._pathNote = note;
                        this.Log($"ShippingMenu → okClicked()（{note}），只等游戏自己关");
                        return null;   // 什么都不做：保存链在游戏自己手里
                    }

                    if (ModalDismiss.TryClickOkButton(ship, out note))
                    {
                        this._path = "click_ok_button";
                        this._pathNote = note;
                        this._lastClickAt = elapsed;
                        this.Log($"ShippingMenu → 反射失败，兜底点 OK 按钮（{note}）");
                    }
                    else
                    {
                        this._path = "reflection_failed";
                        this._pathNote = note;
                        this.Log($"ShippingMenu → 两条路都没走通：{note}");
                    }
                    return null;
                }

                // 兜底路径：**重试到菜单消失**（introTimer > 0 时点击会被静默丢弃）
                if (this._path == "click_ok_button" && elapsed - this._lastClickAt >= ClickRetryMs)
                {
                    string retryNote;
                    if (ModalDismiss.TryClickOkButton(ship, out retryNote))
                    {
                        this._pathNote = retryNote;
                        this._lastClickAt = elapsed;
                    }
                }

                if (elapsed > this._timeoutMs)
                {
                    return this.Fail("timeout",
                        $"ShippingMenu 等了 {elapsed}ms 还没被游戏自己关掉（路径={this._path}：{this._pathNote}）；"
                        + "本技能绝不 exitThisMenu —— 那一句会让日切保存永久丢失（run9 就是这么丢的 4 天盘）",
                        elapsed);
                }
                return null;
            }

            // ---- ③ 菜单没了 ----
            if (menu == null)
            {
                // 刚推出去的那一刻菜单可能短暂为空、下一秒才建 SaveGameMenu ⇒ 给一点宽限
                if (this._sawSaveMenu || elapsed >= EmptyGraceMs)
                    return this.Ok(elapsed, true, null);
                return null;
            }

            // ---- ④ 换成了别的模态：本技能只处理出货/存档菜单，交回外层重新分派 ----
            return this.Ok(elapsed, false,
                $"原菜单 {this._menu0} 已换成 {menu.GetType().Name}，本技能不动手，交回外层");
        }

        private ExecResponse Ok(long elapsedMs, bool menuGone, string extra)
        {
            bool resumed = false;
            try { resumed = Context.IsPlayerFree && Game1.player != null && Game1.player.CanMove; } catch { }

            string reason =
                (string.IsNullOrEmpty(extra) ? "" : extra + "；")
                + $"出货/存档菜单处理完毕（路径={this._path}：{this._pathNote}；等了 {elapsedMs}ms；"
                + $"菜单{(menuGone ? "已消失" : "仍在或已换人")}）";

            return new ExecResponse
            {
                Ok = true,
                Status = "ok",
                Skill = "dismiss_modal",
                Reason = reason,
                Schema = Skills.ExecSchema,
                ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world?.WorldSeq,
                WorldResumed = resumed,
                ReachedLocation = StepMover.CurrentLocationName(),
                ActiveMenuText = menuGone ? null : ModalDismiss.SafeMenuName(),
                DismissPath = this._path,
                WaitedMs = elapsedMs,
                MenuGone = menuGone,
            };
        }

        private ExecResponse Fail(string status, string reason, long elapsedMs)
            => new ExecResponse
            {
                Ok = false, Status = status, Skill = "dismiss_modal", Reason = reason,
                Schema = Skills.ExecSchema, ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
                ActiveMenuText = ModalDismiss.SafeMenuName(),
                DismissPath = this._path,
                WaitedMs = elapsedMs,
                MenuGone = false,
            };

        private void Log(string message)
        {
            try { this._monitor?.Log($"[AgentFarm] dismiss_modal: {message}", LogLevel.Trace); }
            catch { }
        }
    }
}
