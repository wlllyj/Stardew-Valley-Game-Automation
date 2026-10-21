using System;
using System.Reflection;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Menus;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-228】`advance_dialogue`：把**非提问**的事件对话/过场**受控推进**到结束。
    ///
    /// 【要解决的问题（真机事故）】
    /// Clint 送熔炉配方的事件触发后，过场是**非提问对话**、停在第一句等点击 ⇒
    /// `ui.eventUp=true` + `liveness.worldAdvancing=false`，无人值守时**永久挂住**、
    /// 整条跑批作废（目标 2 要求连续 5 天无人值守）。
    ///
    /// 【原语选择（IL 实证，见 `docs/_il-dialogue-advance.md`）】
    /// 唯一正确入口 = `DialogueBox.receiveLeftClick(0, 0, true)`（public override）：
    ///   * 玩家真实鼠标点击（`Game1.updateActiveMenu`）走的就是它；
    ///   * 右键 `receiveRightClick` 只是转发到它；
    ///   * 动作键 `receiveKeyPress` 在 1.6.15 里也映射成 `receiveLeftClick(0,0,true)`；
    ///   * **不用** `closeDialogue()`（那是 `exitActiveMenu()` 跳句：跳过该句显示时机、
    ///     后续 `addCraftingRecipe` 等效果仍执行 ⇒ 看起来"事办了"但对话语义丢了；
    ///     只能作 `dismiss_modal` 的应急路径，不作为推进）；
    ///   * **不用** `Game1.pressActionButton(...)`（提问分支会替玩家应答、且伪造输入边沿）。
    ///
    /// 【为什么必须跨 tick】
    /// ① `if (transitioning) return;` ⇒ 过场动画期调用是空操作；
    /// ② `if (characterIndexInDialogue < getCurrentString().Length - 1) { …; return; }`
    ///    ⇒ **第一次点击只补完打字**，不换句（一次调用 ≠ 前进一句）；
    /// ③ 收尾 `safetyTimer = 750`（短句 550）⇒ 连点会被吞掉。
    ///
    /// 【事件 `pause` 不是卡死（真机补钉 task-226 / d1e085a）】
    /// 事件脚本里有 `pause` 命令，期间文本不变是正常的。因此单步"无变化"**不立刻判 stalled**：
    /// 隔 ≥3.0s 再点，最多重试 2 次（同一处共 ≤3 次点击）；成功判据包含
    /// `activeMenuText` 变化与 `eventUp` 变化；三次都没变化才 `advance_stalled`。
    ///
    /// 【绝不越权】每次点击前：提问（`isQuestion`）⇒ `is_question`；职业选择在途 ⇒
    /// `professions_pending`；不是事件 ⇒ `event_not_running`。**一次都不点**。
    /// </summary>
    internal sealed class DialogueAdvanceSkill
    {
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly int _maxSteps;
        private readonly long _timeoutMs;
        private readonly DateTime _startedUtc = DateTime.UtcNow;
        private readonly DialogueStateView _before = new DialogueStateView();

        private bool _beforeCaptured;
        private int _stepped;
        private int _attempts;
        private int _noChangeCount;
        private bool _lastStepStalled;
        private long? _seqBefore;
        private DateTime _nextAllowedUtc = DateTime.MinValue;
        private string _lastProgress = "";

        // 【P1】第一次观测到"已推进过 + 对话框没了"的时刻；宽限窗口从这一刻开始算。
        private DateTime? _closedSinceUtc;

        // ---- DialogueBox 的私有字段（IL 实证存在；读不到就按"判不了"处理，不猜） ----
        private static readonly FieldInfo CharacterIndexField =
            typeof(DialogueBox).GetField("characterIndexInDialogue", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        private static readonly FieldInfo SafetyTimerField =
            typeof(DialogueBox).GetField("safetyTimer", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        private static readonly FieldInfo TransitioningField =
            typeof(DialogueBox).GetField("transitioning", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        private static readonly FieldInfo ProfessionsField =
            typeof(LevelUpMenu).GetField("professionsToChoose", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);

        public DialogueAdvanceSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._world = world;
            this._monitor = monitor;
            this._maxSteps = DialogueAdvanceRules.ClampMaxSteps(req?.Args?.MaxSteps);
            this._timeoutMs = Skills.ClampTimeoutFor("advance_dialogue", req?.TimeoutMs);
        }

        private long Elapsed()
        {
            double ms = (DateTime.UtcNow - this._startedUtc).TotalMilliseconds;
            return ms < 0 ? 0 : (long)ms;
        }

        /// <summary>主线程每 tick 调一次；返回非 null = 终态。</summary>
        public object Step()
        {
            DialogueBox box = Game1.activeClickableMenu as DialogueBox;
            bool eventUp = Game1.eventUp;
            bool isQuestion = box != null && box.isQuestion;
            bool professions = this.ProfessionsPending();

            // 框又出现了（同一请求内）⇒ 下一次"关框"要重新起算宽限窗口。
            if (box != null) this._closedSinceUtc = null;

            if (!this._beforeCaptured)
            {
                this._beforeCaptured = true;
                this._before.EventUp = eventUp;
                this._before.MenuText = SafeMenuText();
                this._before.IsQuestion = box != null ? (bool?)isQuestion : null;
                this._before.EventCommand = UiRead.EventCommand();
                this._before.DialogueLines = UiRead.DialogueLineCount(box);
                this._seqBefore = this._world != null ? this._world.WorldSeq : (long?)null;
                this._monitor?.Log($"advance_dialogue：开动（maxSteps={this._maxSteps}，eventUp={eventUp}，isQuestion={isQuestion}）");
            }

            // 已经推进过、而且对话框没了 ⇒ 推进任务完成（事件本体是否继续跑由脑侧 event 守卫管）。
            //
            // 【dialogue-okfix / P0】这条是**成功**分支，必须回 ok=true。旧实现走的是
            // `this.Finish(...)` ⇒ `Build(false,…)` ⇒ 回执 ok=false，而 reason 又写着
            // "已推进 N 步…对话框已关闭"（自相矛盾）。下游 `bridge.py` 见到 ok!=true 立刻抛
            // BridgeError，payload 里的 `stepped` 被整包丢弃 ⇒ 脑侧只记 stall、两次后
            // `event_blocked`。**点击其实每次都是有效的**，是回执照谎报。
            //
            // 【dialogue-okfix / P1】关框后不立刻收尾：事件脚本常在关框后极短时间内把下一句
            // （甚至同一句的重放）又弹出来。宽限 ReopenGraceMs（默认 2000ms）内若冒出新的
            // `DialogueBox`，就在**同一请求**里接着按原逻辑推（仍受 maxSteps 与 timeout 约束）；
            // 宽限到点仍无框才按成功收尾。这样才不会"每步等脑侧 15s、一个请求只推 1 步"。
            if (this._stepped > 0 && box == null)
            {
                if (!this._closedSinceUtc.HasValue) this._closedSinceUtc = DateTime.UtcNow;
                long waitedMs = (long)(DateTime.UtcNow - this._closedSinceUtc.Value).TotalMilliseconds;

                bool canWait = DialogueAdvanceRules.AfterBoxClosed(eventUp, waitedMs)
                               == DialogueAdvanceRules.ClosedAfterProgress.KeepWaiting
                               && this.Elapsed() <= this._timeoutMs;
                if (canWait) return null; // 宽限中：下一 tick 再看有没有新对话框

                this._lastStepStalled = false;
                return this.FinishOk(DialogueAdvanceRules.StatusOk,
                    $"已推进 {this._stepped} 步（{this._attempts} 次点击），对话框已关闭"
                    + $"（宽限 {DialogueAdvanceRules.ReopenGraceMs}ms 内没有新的对话，等待 {waitedMs}ms；eventUp={eventUp}）");
            }

            string pre = DialogueAdvanceRules.Precheck(box != null, isQuestion, professions, eventUp);
            if (pre.Length > 0)
            {
                return this.Finish(pre, this.ReasonFor(pre));
            }

            if (this.Elapsed() > this._timeoutMs)
            {
                return this.Finish(DialogueAdvanceRules.StatusTimeout,
                    $"推进超时（{this.Elapsed()}ms > {this._timeoutMs}ms），已推进 {this._stepped} 步、{this._attempts} 次点击");
            }

            if (this._stepped >= this._maxSteps)
            {
                return this.FinishOk(DialogueAdvanceRules.StatusMaxStepsReached,
                    $"已达本次上限 {this._maxSteps} 步（对话仍在；下一轮请求可继续）");
            }

            // ---- 等 safetyTimer / transitioning / 自己的安全间隔（含 pause 重试间隔） ----
            if (DateTime.UtcNow < this._nextAllowedUtc) return null;
            if (ReadBool(box, TransitioningField, false)) return null;
            if (ReadInt(box, SafetyTimerField, 0) > 0) return null;

            // ---- 点击前观测 ----
            string textBefore = SafeText(box);
            string menuTextBefore = SafeMenuText();
            bool eventUpBefore = Game1.eventUp;
            int indexBefore = ReadInt(box, CharacterIndexField, -1);
            bool indexWasIncomplete = textBefore != null && indexBefore >= 0 && indexBefore < textBefore.Length - 1;

            try
            {
                // 与玩家点一下完全相同的那条路（坐标在非提问分支不使用）。
                box.receiveLeftClick(0, 0, true);
            }
            catch (Exception ex)
            {
                return this.Finish(DialogueAdvanceRules.StatusError,
                    $"receiveLeftClick 抛异常：{ex.GetType().Name}: {ex.Message}");
            }

            this._attempts++;

            // ---- 点击后观测（同 tick 内 receiveLeftClick 是同步改状态的） ----
            DialogueBox after = Game1.activeClickableMenu as DialogueBox;
            string textAfter = after != null ? SafeText(after) : null;
            string menuTextAfter = SafeMenuText();
            bool eventUpAfter = Game1.eventUp;
            int indexAfter = after != null ? ReadInt(after, CharacterIndexField, -1) : -1;
            bool menuReplaced = after != null && !ReferenceEquals(after, box);
            bool textChanged = after != null && textBefore != null && textAfter != null && !string.Equals(textAfter, textBefore, StringComparison.Ordinal);
            bool indexCompleted = after != null && indexWasIncomplete && indexAfter == textBefore.Length - 1;
            bool menuTextChanged = !string.Equals(menuTextBefore, menuTextAfter, StringComparison.Ordinal);
            bool eventUpChanged = eventUpBefore != eventUpAfter;
            bool closed = after == null;

            string progress = closed
                ? DialogueAdvanceRules.ProgressAdvanced
                : DialogueAdvanceRules.Classify(menuReplaced, textChanged, indexCompleted, menuTextChanged, eventUpChanged);

            this._lastProgress = progress;
            if (DialogueAdvanceRules.IsProgress(progress))
            {
                this._stepped++;
                this._noChangeCount = 0;
                this._lastStepStalled = false;
                this._nextAllowedUtc = DateTime.UtcNow.AddMilliseconds(
                    DialogueAdvanceRules.SafetyGapMs(textAfter != null ? textAfter.Length : 0));
                return null; // 继续下一 tick
            }

            // ---- 事件 `pause`：无变化先按"可能还在 pause"重试，而不是立刻 fail ----
            this._lastStepStalled = true;
            this._noChangeCount++;
            if (DialogueAdvanceRules.ShouldRetryAfterNoChange(this._noChangeCount))
            {
                this._nextAllowedUtc = DateTime.UtcNow.AddMilliseconds(DialogueAdvanceRules.StallRetryGapMs);
                this._monitor?.Log($"advance_dialogue：第 {this._noChangeCount} 次无变化（可能事件 pause）⇒ {DialogueAdvanceRules.StallRetryGapMs}ms 后重试");
                return null;
            }

            return this.Finish(DialogueAdvanceRules.StatusAdvanceStalled,
                $"同一处连点 {DialogueAdvanceRules.StallMaxClicks} 次、每次间隔 ≥{DialogueAdvanceRules.StallRetryGapMs}ms，"
                + $"文本/菜单文本/事件状态/索引都没有任何变化（progress={progress}）⇒ 判定推进卡死（已推进 {this._stepped} 步）");
        }

        // ------------------------------------------------------------------ 内部
        private bool ProfessionsPending()
        {
            LevelUpMenu menu = Game1.activeClickableMenu as LevelUpMenu;
            if (menu == null) return false;
            try
            {
                object value = ProfessionsField != null ? ProfessionsField.GetValue(menu) : null;
                if (value is System.Collections.ICollection col) return col.Count > 0;
                return value != null;
            }
            catch (Exception)
            {
                // 读不到职业列表 ⇒ 无法判定 ⇒ fail-closed：当成"有职业选择在途"，绝不动手。
                return true;
            }
        }

        private string ReasonFor(string status)
        {
            switch (status)
            {
                case DialogueAdvanceRules.StatusIsQuestion:
                    return "当前是**提问**（isQuestion=true）⇒ 本技能只推进非提问对话，绝不替玩家选选项，一次都没点";
                case DialogueAdvanceRules.StatusProfessionsPending:
                    return "LevelUpMenu 还有职业选择在途（professionsToChoose 非空）⇒ 不可逆操作，一次都没点";
                case DialogueAdvanceRules.StatusNoDialogue:
                    return "当前没有 DialogueBox ⇒ 无可推进（eventUp=" + Game1.eventUp + "）";
                case DialogueAdvanceRules.StatusEventNotRunning:
                    return "当前不是事件（eventUp=false）⇒ 本技能只服务事件对话，一次都没点";
                default:
                    return status;
            }
        }

        private ExecResponse Finish(string status, string reason)
        {
            return this.Build(false, status, reason);
        }

        private ExecResponse FinishOk(string status, string reason)
        {
            return this.Build(true, status, reason);
        }

        private ExecResponse Build(bool ok, string status, string reason)
        {
            DialogueBox box = Game1.activeClickableMenu as DialogueBox;
            DialogueStateView after = new DialogueStateView
            {
                EventUp = Game1.eventUp,
                MenuText = SafeMenuText(),
                IsQuestion = box != null ? (bool?)box.isQuestion : null,
                // 【P2 取证】和 `before` 用同一套读法 ⇒ 可直接做 command/条数的差分。
                EventCommand = UiRead.EventCommand(),
                DialogueLines = UiRead.DialogueLineCount(box),
            };
            this._monitor?.Log($"advance_dialogue：{status}（stepped={this._stepped}/{this._maxSteps}，attempts={this._attempts}，lastProgress={this._lastProgress}）");
            return new ExecResponse
            {
                Ok = ok,
                Status = status,
                Skill = "advance_dialogue",
                Reason = reason,
                Schema = Skills.ExecSchema,
                ElapsedMs = this.Elapsed(),
                Stepped = this._stepped,
                Stalled = this._lastStepStalled,
                Before = this._before,
                After = after,
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world != null ? this._world.WorldSeq : (long?)null,
            };
        }

        private static string SafeMenuText()
        {
            try { return UiRead.ActiveMenuText(); }
            catch (Exception) { return null; }
        }

        private static string SafeText(DialogueBox box)
        {
            try { return box.getCurrentString(); }
            catch (Exception) { return null; }
        }

        private static bool ReadBool(DialogueBox box, FieldInfo field, bool fallback)
        {
            try
            {
                if (box == null || field == null) return fallback;
                object v = field.GetValue(box);
                return v is bool b ? b : fallback;
            }
            catch (Exception) { return fallback; }
        }

        private static int ReadInt(DialogueBox box, FieldInfo field, int fallback)
        {
            try
            {
                if (box == null || field == null) return fallback;
                object v = field.GetValue(box);
                return v is int i ? i : fallback;
            }
            catch (Exception) { return fallback; }
        }
    }
}
