using System;
using System.Reflection;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Menus;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【P3 步骤⑤/⑥】`sleep`：**睡到第二天早上** —— 无人值守连续多日的唯一正路。
    ///
    /// ==================================================================
    /// 【为什么必须"睡"，而不能用别的手段跨日】
    /// 游戏**只在睡觉时落盘**（`SaveGame` 的调用方清单里没有别的入口）。
    /// 所以"quit_game + load_save" 读回来还是同一天的早上，**那是假跨日**：
    /// 日期不前进、体力不恢复、作物不长、天不换。必须让游戏自己走完跨日流程。
    ///
    /// 【机制（tools/il-probe 逐条核对，1.6.15）】
    ///   * `FIND|startSleep` → `StardewValley.GameLocation.answerDialogueAction(String, String[])`
    ///     是**唯一**调用 `GameLocation.startSleep()` 的地方（另一条是 startSleep 自己的 lambda）；
    ///   * `startSleep()`：先 `player.timeWentToBed = timeOfDay`；单人（`!Game1.IsMultiplayer`）
    ///     直接 `this.doSleep()`；多人则弹 `ReadyCheckDialog("sleep", ...)` 等所有人就绪；
    ///   * `doSleep()`：`Game1.IsMasterGame` 时调 **`Game1.NewDay(0f)`**，随后写
    ///     `lastSleepLocation/lastSleepPoint/mostRecentBed`、`doEmote(24)`、`freezePause = 2000`；
    ///   * `Game1.NewDay(timeToPause)` 的 IL：`player.isInBed || player.passedOut` 时
    ///     `nonWarpFade=true` / `FadeScreenToBlack` / `player.Halt()` / `CanMove=false` / `pauseTime=timeToPause`，
    ///     然后置 `Game1.newDay = true`、`Game1.newDaySync.create()` —— 跨日与存档由它引发。
    /// ⇒ 因此本技能**调游戏自己的应答入口**，等价于玩家在 "go to sleep for the night?" 上点了 Yes：
    ///   ① 床上已经弹出提问时 → `GameLocation.answerDialogue(Response=Yes)`（ModalDismiss.AnswerWith，
    ///      它会消费 `location.afterQuestion`，与真人点 Yes 同一条路）；
    ///   ② 没有提问、但 `lastQuestionKey` 首段**就是 `Sleep`** → `answerDialogueAction("Sleep_Yes")`；
    ///   ③ 两者都不成立（**包括** `lastQuestionKey` 为空、或首段是别的前缀）→ **不发**，
    ///      立刻 `sleep_no_question` 失败。
    ///
    /// 【③ 为什么必须这么严（2026-10-13 IL 定案，docs/_il-sleep-path.md）】
    /// `answerDialogueAction` 是**字面量分派**：`IL_0ABC ldstr "Sleep_Yes"` → `op_Equality` →
    /// `brtrue` 才走到 `startSleep()`，任何别的字符串都从默认出口**静默返回**（它**没有**
    /// isInBed/dialogueUp/lastQuestionKey 前置判据 ⇒ 发出去不会报错）。所以"键发出去了"完全
    /// 不等于"游戏收到了"：run2 两次 180s 超时就是发了一个按 `lastQuestionKey` 首段拼的错键。
    /// 
    ///   **绝不注入键鼠事件**（与 ModalDismiss 同一条铁律：1.6.15 的 `DialogueBox.receiveKeyPress`
    ///   对 Enter/Space 没有应答语义，会经 `Options.actionButton` 变成 `receiveLeftClick(0,0,true)`＝确认当前项，
    ///   真机事故记录见 ModalDismiss 类注释）。
    ///
    /// 【成功判据：日期真的前进了 + `Game1.newDay` 已归位】`Game1.Date.TotalDays` 变大。
    /// 回执里的说法只是声明；脑必须用 observe 复核（`clock.day` 变了、体力回满）。
    ///
    /// 【为什么"答了 Yes"还要**同一 tick 关框**（task-33 真机定案）】
    /// 真机配方（`logs\probe-bed-close-run1.log`）：踩到床的 `TouchAction="Sleep"` 格 ⇒ 弹出
    /// `Go to sleep for the night?`；用游戏自己的 `answerDialogue()` 答 Yes 之后，
    /// `Game1.newDay` **立刻**变 true（跨日已经启动），但日期 180s 都不动 —— 因为
    /// `answerDialogue()` **只应答、不关框**，而 `newDaySync` 要等提问框收掉才会推进到保存/换天。
    /// 同一 tick 按游戏自己的顺序关框（`ModalDismiss.CloseDialogueBox`）后 ~3s 当天落地。
    /// 所以：①应答后立刻关框；②等跨日期间每 tick 检查一次（newDay 置位而框还在 ⇒ 再关，最多
    /// `CloseBoxMaxTries` 次）；③**关框前绝不重发 `sleep`**（会把已置位的 newDay 流程搅乱）。
    /// 跨日要淡黑 + 存档 + 换天：实测 ~1.8s（task-6 PASS 探针），默认预算 **15 秒**
    /// （旧值 120s：run2 两次失败各白等 180s 才回报）。仍可用 `timeout_ms` 放宽，
    /// 但"没有提问"这条路现在是秒级失败，不会再走到超时。
    /// ==================================================================
    /// </summary>
    internal sealed class SleepSkill
    {
        /// <summary>
        /// 默认预算 **15 秒**（旧值 120000）。
        ///
        /// 【为什么改】跨日实测只要 ~1.8s（task-6 的 PASS 探针：人已在床上时
        /// `answerDialogueAction("Sleep_Yes")` → 日期 +1）；而"提问根本没弹出来"这种失败现在由
        /// <see cref="FireSleepRequest"/> **秒级**报 `sleep_no_question` ⇒ 再用 120s/180s 只是为了
        /// 把根因埋掉：run2 两次失败各等满 180s，journal 里只剩一句"睡觉请求失败"
        /// （`docs/_analyze-sleep-fail.md` §4 R3）。
        /// </summary>
        private const int DefaultTimeoutMs = 15000;
        private const int MaxTimeoutMs = 300000;

        /// <summary>
        /// 等待跨日期间"发现 newDay 已置位但框还挂着"时，最多主动关框几次（幂等，纯兜底；
        /// 正常路径由 <see cref="FireSleepRequest"/> 在同一 tick 就关掉了）。
        /// 取 3：关框本身不消耗预算，但真出了别的问题时不该让它无限刷日志。
        /// </summary>
        private const int CloseBoxMaxTries = 3;

        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly int _timeoutMs;

        private bool _started;
        private DateTime _startedAtUtc;
        private long _seqBefore;
        private int _dayBefore = -1;
        private int _timeBefore = -1;
        private string _trigger = "(未发起)";
        private string _triggerNote = "";
        private int _closeTries;

        public SleepSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._world = world;
            this._monitor = monitor;
            this._timeoutMs = ClampBudget(req?.TimeoutMs);
        }

        /// <summary>
        /// 睡觉的时间预算（刻意不用 <see cref="Skills.ClampTimeout"/>：那个上限 30 秒是给"走一格"定的，
        /// 跨日 + 存档合法地会超过它）。与 <see cref="LoadSaveSkill.ClampBudget"/> 同一套写法：
        /// **技能自己与 BridgeHost 的主线程等待都调它**，免得两边各算一个数把 2 分钟的跨日掐死。
        /// </summary>
        public static int ClampBudget(int? timeoutMs)
        {
            int t = timeoutMs ?? DefaultTimeoutMs;
            if (t < 5000) t = 5000;
            if (t > MaxTimeoutMs) t = MaxTimeoutMs;
            return t;
        }

        private long Elapsed() => (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds;

        private ExecResponse Fail(string status, string reason, long elapsedMs)
            => new ExecResponse
            {
                Ok = false, Status = status, Skill = "sleep", Reason = reason,
                Schema = Skills.ExecSchema, ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };

        private ExecResponse Ok(long elapsedMs)
        {
            int dayNow = SafeTotalDays();
            int timeNow = SafeTimeOfDay();
            string stamina = "?";
            try { stamina = Game1.player?.stamina.ToString("0"); } catch { }

            return new ExecResponse
            {
                Ok = true, Status = "ok", Skill = "sleep", Schema = Skills.ExecSchema,
                Reason = $"已跨日：第 {this._dayBefore} 天 → 第 {dayNow} 天（timeOfDay {this._timeBefore} → {timeNow}，"
                       + $"体力 {stamina}，{elapsedMs}ms）。怎么睡的：{this._trigger}（{this._triggerNote}）"
                       + "。回执只是声明，跨日是否真的成功请用 observe 复核（clock.day / 体力 / 地点）",
                ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };
        }

        /// <summary>主线程调用：返回非 null = 终态；返回 null = 还在跨日，下个 tick 继续。</summary>
        public object Step()
        {
            long seq = 0;
            try { seq = this._world?.WorldSeq ?? 0; } catch { }

            if (!Context.IsWorldReady || Game1.player == null)
                return this.Fail("no_save", "尚未加载存档，无法 sleep", 0);

            // ---------------- 发起 ----------------
            if (!this._started)
            {
                this._started = true;
                this._startedAtUtc = DateTime.UtcNow;
                this._seqBefore = seq;
                this._dayBefore = SafeTotalDays();
                this._timeBefore = SafeTimeOfDay();

                bool delivered = this.FireSleepRequest();

                // 没东西可应答 ⇒ **秒级**如实失败，绝不把"没有提问"拖成 3 分钟超时：
                // 既是白等，也让 journal 里看不出根因（task-6 §4 R2/R3；Lead m01071）。
                if (!delivered)
                    return this.Fail("sleep_no_question",
                        "睡觉提问没弹出来，拒绝盲发应答（盲发在 IL 上是静默 no-op）："
                        + $"当前地点 {StepMover.CurrentLocationName()} 的 lastQuestionKey="
                        + $"{(string.IsNullOrEmpty(LastQuestionKey()) ? "(空)" : LastQuestionKey())}；"
                        + $"诊断：{this.Diagnose()}。"
                        + "睡觉提问只能由**玩家踩到床的 `TouchAction=\"Sleep\"` 触发格**引出"
                        + "（`GameLocation.UpdateWhenCurrentLocation → performTouchAction`），"
                        + "而且要求这一帧真的移动过（`Farmer.hasMoved`）；"
                        + "`interact(床格)` 在 1.6.15 是静默 no-op。"
                        + "脑侧做法：现算触发格（`furniture[].bedCells`）→ 先走离床格一步 → "
                        + "`move_to(触发格, allow_bed=true)`（命中时回执就是 `ui_modal`，那是**命中信号**）→ "
                        + "等提问弹出来再 sleep",
                        this.Elapsed());

                // 跨 tick：这一 tick 只负责"把睡觉发起出去"，跨日要等淡黑 + 存档 + 换天。
                return null;
            }

            // ---------------- 等跨日 ----------------
            int dayNow = SafeTotalDays();

            // 【task-33 真机定案】答 Yes 之后 `Game1.newDay=True` 就已经是既成事实，日期之所以不动
            // 只是因为**提问框还挂着**（`newDaySync` 等不到保存）。所以每 tick 都检查一次：
            // 只要 newDay 已置位、而框还在，就按游戏自己的顺序把它关掉（幂等，最多 CloseBoxMaxTries 次）。
            if (SafeNewDay() && this._closeTries < CloseBoxMaxTries)
            {
                this._closeTries++;
                string closeNote = CloseActiveQuestionBox(
                    "等待跨日时 newDay 已置位但日期不动");
                this._monitor?.Log($"sleep：关框第 {this._closeTries} 次（{closeNote}）");
            }

            if (this._dayBefore >= 0 && dayNow > this._dayBefore)
            {
                // 日期前进 ⇒ 跨日已发生。但**还要等 newDay 归位**（存档/换天收尾），
                // 否则脑侧立刻接着干活会撞上还在切场景的世界。
                if (!SafeNewDay())
                    return this.Ok(this.Elapsed());
            }

            long elapsed = this.Elapsed();
            if (elapsed > this._timeoutMs)
            {
                bool newDayStill = SafeNewDay();
                return this.Fail("timeout",
                    $"已发起睡觉（{this._trigger}）但 {elapsed}ms 内日期没有前进"
                    + $"（发起时第 {this._dayBefore} 天，现在第 {dayNow} 天）"
                    + $"；当前诊断：{this.Diagnose()}"
                    + $"（默认预算 {DefaultTimeoutMs}ms；确认真跨日需要更久时可放宽 timeout_ms）"
                    + (newDayStill
                        ? "。⚠ `Game1.newDay` 仍是 true ⇒ **跨日流程已经启动、只是没收尾**："
                          + "真机上这一般是睡觉提问框没被关掉（`answerDialogue()` 只应答不关框），"
                          + "脑侧可用 `dismiss_modal` 兜底关框后再 observe 看日期；"
                        : "。可能原因：睡觉提问没被应答 / 跨日流程被打断 / 世界被模态挡住；")
                    + "需要外部恢复（脑可先 dismiss_modal 再看，或重启游戏）",
                    elapsed);
            }

            return null;
        }

        // ==================================================================
        //  发起睡觉
        // ==================================================================

        /// <summary>
        /// 发起睡觉。返回**是否真的把应答送出去了**。
        ///
        /// * `true`：①真开着提问且我们答了 Yes，或 ②`lastQuestionKey` 首段就是 `Sleep`
        ///   且 `answerDialogueAction` 调用没抛异常；
        /// * `false`：**没有**可证明是睡觉提问的东西 ⇒ 调用方立刻 `sleep_no_question` 失败，
        ///   **不发送**、更不等超时。
        ///
        /// 【为什么必须这么严（2026-10-13 IL 定案，docs/_il-sleep-path.md）】
        /// `GameLocation.answerDialogueAction(String, String[])` 是**字面量分派**：
        /// `IL_0ABC ldstr "Sleep_Yes"` → `IL_0AC1 op_Equality` → `IL_0AC6 brtrue` 才走到
        /// `startSleep()`；任何别的字符串都从默认出口**静默返回**，且它**没有**前置判据
        /// ⇒ 发出去永远不会报错。所以"把键发出去了"完全不等于"游戏收到了"：
        /// run2 两次 180s 超时就是发了一个按 `lastQuestionKey` 首段拼出来的错键。
        /// </summary>
        private bool FireSleepRequest()
        {
            // ① 床上已经弹出 "go to sleep for the night?" → 用游戏自己的 answerDialogue 答 Yes
            string note;
            string chosenText;
            if (TryAnswerOpenQuestion(out chosenText, out note))
            {
                this._trigger = $"answerDialogue(Yes：\"{chosenText}\")";
                this._triggerNote = note;
                // 诊断：开着提问的键不是 Sleep 时留个痕（真机若出现"答了别的提问"能一眼看出来）。
                string qHead = LastQuestionKeyHead();
                if (!string.IsNullOrEmpty(qHead) && !qHead.Equals("Sleep", StringComparison.OrdinalIgnoreCase))
                    this._triggerNote += $"；⚠ 当时 lastQuestionKey 首段是「{qHead}」而不是 Sleep";
                this._monitor?.Log(
                    $"sleep：已用游戏自己的 answerDialogue 应答睡觉提问（选 \"{chosenText}\"：{note}）");
                return true;
            }

            // ② 没开着提问 ⇒ 必须能从 lastQuestionKey 证明"上一个提问就是睡觉提问"，才允许发键
            string key = BuildSleepAnswerKey();
            if (string.IsNullOrEmpty(key))
            {
                this._trigger = "(未发送：拼不出 Sleep 前缀的应答键)";
                this._triggerNote = "拒绝盲发（answerDialogueAction 发错键会静默 no-op）";
                this._monitor?.Log(
                    $"sleep：{this._trigger}；当前诊断：{this.Diagnose()}", LogLevel.Warn);
                return false;
            }

            string fallbackNote;
            bool delivered = TryAnswerDialogueAction(key, out fallbackNote);

            this._trigger = $"answerDialogueAction(\"{key}\")";
            this._triggerNote = fallbackNote
                + (string.IsNullOrEmpty(chosenText) ? "" : $"；当时开着的是非提问对话「{chosenText}」");
            this._monitor?.Log($"sleep：{this._trigger}（{fallbackNote}）");
            if (!delivered)
                this._monitor?.Log("sleep：应答没有送回游戏（见回执 reason），将在超时后如实报失败", LogLevel.Warn);
            return delivered;
        }

        /// <summary>
        /// 如果当前开着的是提问对话框，就用**游戏自己的** `answerDialogue(Response)` 选"是"那一项。
        ///
        /// 【为什么复用 ModalDismiss.AnswerWith】那是本项目**唯一**一处"把选项交给游戏"的实现，
        /// 里面写着两条硬教训：必须走 `answerDialogue(Response)`（它会消费 `location.afterQuestion`，
        /// 也就是让游戏执行"回答之后本应发生的事"，例如 startSleep）；
        /// 异常才回退组合键 `answerDialogueAction`。这里直接复用，避免出现第二份口径。
        /// </summary>
        private static bool TryAnswerOpenQuestion(out string chosenText, out string note)
        {
            chosenText = null; note = "";
            try
            {
                DialogueBox box = Game1.activeClickableMenu as DialogueBox;
                if (box == null) return false;

                Response[] responses = null;
                try { responses = box.responses; } catch { }
                bool isQuestion = false;
                try { isQuestion = box.isQuestion; } catch { }
                if (!isQuestion || responses == null || responses.Length == 0) return false;

                int index = FindAffirmativeIndex(responses);
                if (index < 0) return false;   // 没有"是"这一项：不是睡觉提问，交回调用方走 ②

                Response chosen = responses[index];
                chosenText = chosen?.responseText ?? chosen?.responseKey ?? "";
                note = ModalDismiss.AnswerWith(chosen);

                // 【task-33 真机定案：答了 Yes 必须**同一 tick**关框】
                // `answerDialogue()` 只应答、不关框 ⇒ `Game1.newDay` 已经是 true，但提问框一直挂着，
                // `newDaySync` 等不到保存/换天 ⇒ 日期 180s 不动（真机 `probe-bed-close-run1.log`）。
                // 按游戏自己的顺序关掉（`closeDialogue()` → 仍在才 `exitThisMenu()`），~3s 当天落地。
                note += "；关框：" + ModalDismiss.CloseDialogueBox(box);
                return true;
            }
            catch (Exception ex)
            {
                note = "读对话选项异常：" + ex.GetType().Name + ": " + ex.Message;
                return false;
            }
        }

        /// <summary>
        /// 把当前开着的对话框按游戏自己的顺序关掉（没有框 ⇒ 返回一句说明，不报错）。
        ///
        /// 【用途】等待跨日期间的兜底：`Game1.newDay` 已经置位、日期却不动 ⇒ 通常是提问框没关掉。
        /// 只走 <see cref="ModalDismiss.CloseDialogueBox"/> 那一份顺序，绝不自己拼关闭逻辑。
        /// 异常一律吞掉并写进返回值：关框失败不能让技能崩，脑侧还有 `dismiss_modal` 兜底。
        /// </summary>
        private static string CloseActiveQuestionBox(string why)
        {
            try
            {
                DialogueBox box = Game1.activeClickableMenu as DialogueBox;
                if (box == null) return "当前没有对话框（不用关）";
                return $"（{why}）" + ModalDismiss.CloseDialogueBox(box);
            }
            catch (Exception ex)
            {
                return "关框异常：" + ex.GetType().Name + ": " + ex.Message;
            }
        }

        /// <summary>
        /// 拼 `answerDialogueAction` 要收的**组合键**（`lastQuestionKey 首段 + "_Yes"`）。
        ///
        /// 【为什么不是裸 "Yes"】`ModalDismiss` 的注释已实证：游戏把答案拼成
        /// `lastQuestionKey.Split(' ')[0] + "_" + responseKey`（睡觉是 `"Sleep_Yes"`），
        /// 裸传 "Yes" 在所有 `questionKey_xxx` 型对话上都是空操作。
        /// `lastQuestionKey` 读不到、或首段**不是** `Sleep` 时返回 `null`。
        ///
        /// 【2026-10-13 改】旧实现在读不到时退回裸 `"Sleep_Yes"`。IL 定案（见
        /// <see cref="FireSleepRequest"/>）证明"发错键 = 静默 no-op"，所以盲发毫无意义，
        /// 只会把根因埋进超时里；现在返回 null 让调用方秒级失败。
        /// </summary>
        private static string BuildSleepAnswerKey()
        {
            string head = LastQuestionKeyHead();
            if (string.IsNullOrEmpty(head)) return null;
            if (!head.Equals("Sleep", StringComparison.OrdinalIgnoreCase)) return null;
            return head + "_Yes";
        }

        /// <summary>当前地点的 `lastQuestionKey` 原文（读不到 = null）。</summary>
        private static string LastQuestionKey()
        {
            try { return Game1.currentLocation?.lastQuestionKey; } catch { return null; }
        }

        /// <summary>`lastQuestionKey` 的首段（游戏把键拼成 `<首段>_<responseKey>`；睡觉是 `Sleep_Yes`）。</summary>
        private static string LastQuestionKeyHead()
        {
            string q = LastQuestionKey();
            if (string.IsNullOrEmpty(q)) return null;
            int space = q.IndexOf(' ');
            return space >= 0 ? q.Substring(0, space) : q;
        }

        private static bool TryAnswerDialogueAction(string key, out string note)
        {
            note = "";
            try
            {
                GameLocation loc = Game1.currentLocation;
                if (loc == null) { note = "当前地点为空"; return false; }
                loc.answerDialogueAction(key, null);
                note = "已交给游戏自己的 answerDialogueAction（它会走 startSleep → doSleep → Game1.NewDay）";
                return true;
            }
            catch (Exception ex)
            {
                note = "answerDialogueAction 异常：" + ex.GetType().Name + ": " + ex.Message;
                return false;
            }
        }

        /// <summary>
        /// 找"是/确定"那一项。先看 `responseKey`（程序化 ID，最可靠），再看 `responseText`。
        /// 与 ModalDismiss.FindNegativeIndex 同构，只是取肯定项、且**从前往后**扫（肯定项在前）。
        /// ⚠️ 刻意**不**做"找不到就取第一项"的兜底：睡觉是破坏性动作，选错项比不睡更糟。
        /// </summary>
        private static int FindAffirmativeIndex(Response[] responses)
        {
            string[] tokens = { "yes", "yeah", "sure", "ok", "是", "好", "确定" };

            for (int pass = 0; pass < 2; pass++)
            {
                for (int i = 0; i < responses.Length; i++)
                {
                    Response r = responses[i];
                    if (r == null) continue;
                    string s = pass == 0 ? r.responseKey : r.responseText;
                    if (string.IsNullOrEmpty(s)) continue;
                    string lower = s.ToLowerInvariant();
                    foreach (string t in tokens)
                        if (lower.Contains(t)) return i;
                }
            }
            return -1;
        }

        // ==================================================================
        //  诊断读数
        // ==================================================================

        private static int SafeTotalDays()
        {
            try { return Game1.Date.TotalDays; } catch { return -1; }
        }

        private static int SafeTimeOfDay()
        {
            try { return Game1.timeOfDay; } catch { return -1; }
        }

        /// <summary>
        /// `Game1.newDay`（跨日流程是否还在跑）。读不到按 **false** 处理：宁可早报成功让脑侧
        /// observe 复核，也不要因为反射失败把已经跨完日的技能拖到超时。
        /// </summary>
        private static bool SafeNewDay()
        {
            try { return Game1.newDay; } catch { return false; }
        }

        private string Diagnose()
        {
            string isInBed = "?", newDay = "?", pauseTime = "?", menu = "?", dialogueUp = "?";
            string canMove = "?", gameMode = "?", timeOfDay = "?";
            try { isInBed = (Game1.player?.isInBed?.Value ?? false).ToString(); } catch { }
            try { newDay = Game1.newDay.ToString(); } catch { }
            try { pauseTime = Game1.pauseTime.ToString("0.##"); } catch { }
            try { menu = Game1.activeClickableMenu?.GetType().Name ?? "(无)"; } catch { }
            try { dialogueUp = Game1.dialogueUp.ToString(); } catch { }
            try { canMove = (Game1.player?.CanMove ?? false).ToString(); } catch { }
            try { gameMode = Game1.gameMode.ToString(); } catch { }
            try { timeOfDay = Game1.timeOfDay.ToString(); } catch { }

            return $"isInBed={isInBed}, Game1.newDay={newDay}, pauseTime={pauseTime}, "
                 + $"activeMenu={menu}, dialogueUp={dialogueUp}, canMove={canMove}, "
                 + $"gameMode={gameMode}, timeOfDay={timeOfDay}, "
                 + $"newDaySync.readyForSave?={(SafeReadyForSave())}, newDaySync.hasSaved?={(SafeHasSaved())}";
        }

        // api-probe 实证：NewDaySynchronizer.readyForSave() / hasSaved() 是**方法**（返回 Boolean），不是字段。
        private static string SafeReadyForSave()
        {
            try { return Game1.newDaySync?.readyForSave().ToString() ?? "?"; } catch { return "?"; }
        }

        private static string SafeHasSaved()
        {
            try { return Game1.newDaySync?.hasSaved().ToString() ?? "?"; } catch { return "?"; }
        }

        /// <summary>
        /// 反射调私有的 `GameLocation.startSleep()`（保留入口：万一 `answerDialogueAction`
        /// 这条路在某个版本上被改掉，可以直接调它）。当前 **默认不用**，只在日志里留证据用。
        /// </summary>
        internal static bool TryReflectStartSleep(out string note)
        {
            note = "";
            try
            {
                GameLocation loc = Game1.currentLocation;
                if (loc == null) { note = "当前地点为空"; return false; }

                MethodInfo mi = typeof(GameLocation).GetMethod(
                    "startSleep", BindingFlags.Instance | BindingFlags.NonPublic);
                if (mi == null) { note = "找不到 GameLocation.startSleep（私有）"; return false; }

                mi.Invoke(loc, null);
                note = "已反射调用 GameLocation.startSleep()";
                return true;
            }
            catch (Exception ex)
            {
                note = "反射调用 startSleep 异常：" + ex.GetType().Name + ": " + ex.Message;
                return false;
            }
        }
    }
}
