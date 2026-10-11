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
    ///   ② 没有提问（脑已经站到床上但对话框没弹，或直接从别处调用）→
    ///      `GameLocation.answerDialogueAction("<lastQuestionKey 首段>_Yes")`，退到裸 `"Sleep_Yes"`。
    ///   **绝不注入键鼠事件**（与 ModalDismiss 同一条铁律：1.6.15 的 `DialogueBox.receiveKeyPress`
    ///   对 Enter/Space 没有应答语义，会经 `Options.actionButton` 变成 `receiveLeftClick(0,0,true)`＝确认当前项，
    ///   真机事故记录见 ModalDismiss 类注释）。
    ///
    /// 【成功判据：日期真的前进了】`Game1.Date.TotalDays` 变大。
    /// 回执里的说法只是声明；脑必须用 observe 复核（`clock.day` 变了、体力回满）。
    /// 跨日要淡黑 + 存档 + 换天，**合法地慢**（几秒到几十秒），所以本技能是跨 tick 长任务，
    /// 时间预算走自己的口径 <see cref="ClampBudget"/>（上限 5 分钟，比"走一格"的 30 秒宽）。
    /// ==================================================================
    /// </summary>
    internal sealed class SleepSkill
    {
        private const int DefaultTimeoutMs = 120000;
        private const int MaxTimeoutMs = 300000;

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

                this.FireSleepRequest();

                // 跨 tick：这一 tick 只负责"把睡觉发起出去"，跨日要等淡黑 + 存档 + 换天。
                return null;
            }

            // ---------------- 等跨日 ----------------
            int dayNow = SafeTotalDays();

            if (this._dayBefore >= 0 && dayNow > this._dayBefore)
                return this.Ok(this.Elapsed());

            long elapsed = this.Elapsed();
            if (elapsed > this._timeoutMs)
            {
                return this.Fail("timeout",
                    $"已发起睡觉（{this._trigger}）但 {elapsed}ms 内日期没有前进"
                    + $"（发起时第 {this._dayBefore} 天，现在第 {dayNow} 天）"
                    + $"；当前诊断：{this.Diagnose()}"
                    + "。可能原因：睡觉提问没被应答 / 跨日流程被打断 / 世界被模态挡住；"
                    + "需要外部恢复（脑可先 dismiss_modal 再看，或重启游戏）",
                    elapsed);
            }

            return null;
        }

        // ==================================================================
        //  发起睡觉
        // ==================================================================

        private void FireSleepRequest()
        {
            // ① 床上已经弹出 "go to sleep for the night?" → 用游戏自己的 answerDialogue 答 Yes
            string note;
            string chosenText;
            if (TryAnswerOpenQuestion(out chosenText, out note))
            {
                this._trigger = $"answerDialogue(Yes：\"{chosenText}\")";
                this._triggerNote = note;
                this._monitor?.Log(
                    $"sleep：已用游戏自己的 answerDialogue 应答睡觉提问（选 \"{chosenText}\"：{note}）");
                return;
            }

            // ② 没有开着提问 → 直接走游戏的应答分发器
            //    （IL 实证：answerDialogueAction 是唯一调用 GameLocation.startSleep 的地方）
            string key = BuildSleepAnswerKey();
            string fallbackNote;
            bool delivered = TryAnswerDialogueAction(key, out fallbackNote);

            this._trigger = $"answerDialogueAction(\"{key}\")";
            this._triggerNote = fallbackNote
                + (string.IsNullOrEmpty(chosenText) ? "" : $"；当时开着的是非提问对话「{chosenText}」");
            this._monitor?.Log($"sleep：{this._trigger}（{fallbackNote}）");
            if (!delivered)
                this._monitor?.Log("sleep：应答没有送回游戏（见回执 reason），将在超时后如实报失败", LogLevel.Warn);
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
                return true;
            }
            catch (Exception ex)
            {
                note = "读对话选项异常：" + ex.GetType().Name + ": " + ex.Message;
                return false;
            }
        }

        /// <summary>
        /// 拼 `answerDialogueAction` 要收的**组合键**（`lastQuestionKey 首段 + "_Yes"`）。
        ///
        /// 【为什么不是裸 "Yes"】`ModalDismiss` 的注释已实证：游戏把答案拼成
        /// `lastQuestionKey.Split(' ')[0] + "_" + responseKey`（睡觉是 `"Sleep_Yes"`），
        /// 裸传 "Yes" 在所有 `questionKey_xxx` 型对话上都是空操作。
        /// `lastQuestionKey` 读不到时退回裸 "Sleep_Yes"（睡觉的键名是固定的）。
        /// </summary>
        private static string BuildSleepAnswerKey()
        {
            string questionKey = null;
            try { questionKey = Game1.currentLocation?.lastQuestionKey; } catch { }

            if (!string.IsNullOrEmpty(questionKey))
            {
                int space = questionKey.IndexOf(' ');
                string head = space >= 0 ? questionKey.Substring(0, space) : questionKey;
                if (!string.IsNullOrEmpty(head))
                    return head + "_Yes";
            }
            return "Sleep_Yes";
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
