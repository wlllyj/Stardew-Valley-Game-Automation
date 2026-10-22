using System;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-228】`advance_dialogue` 的**纯规则**（零游戏类型依赖）。
    ///
    /// 为什么外置：仓库没有能引用游戏程序集的 C# 测试工程（见 `ClumpRules`/`TileListRules`/
    /// `AnswerRules` 的同样理由），吃 `DialogueBox`/`Game1` 的类型只能当源码看；把
    /// "该不该点/点完算不算前进/两次点击隔多久"这些**决策逻辑**放在这里，零依赖自检工程
    /// `mod/AgentFarm.Bridge.Tests` 才能跑**行为断言**（而不是文本存在性断言）。
    ///
    /// 规则来源：`docs/_il-dialogue-advance.md`（`DialogueBox.receiveLeftClick` 的 IL 证据链）。
    /// </summary>
    internal static class DialogueAdvanceRules
    {
        // ---------------------------------------------------------------- 常量
        // maxSteps 的默认/上界：一次请求最多推进多少"步"。取值依据（task-228 卡面：1..10，默认 1）：
        //   * 单步之间的间隔由 safetyGap（550~750ms）保证，一次调用推太多步会把一个请求的
        //     主线程槽位占很久（单线程调度一次只做一件事）；
        //   * 脑侧按"每轮一次调用"循环推进（每轮还会重新观测 eventUp/isQuestion 与余额），
        //     所以小步长足够快，又能让"提问/职业选择一出现就立刻停手"的粒度最细；
        //   * 上限 10 与卡面一致；真正的总量上界在脑侧（每次 ≤10 步、每天 ≤60 步）。
        internal const int MaxStepsDefault = 1;
        internal const int MaxStepsCap = 10;
        internal const int MaxStepsFloor = 1;

        // safetyTimer 的实测值（`DialogueBox.receiveLeftClick` IL_0352-0396）：
        //   safetyTimer = IsDedicatedHost ? 0 : 750; 短句（<=20 字）再 -200 ⇒ 550。
        // 我们不是 DedicatedHost（无人值守单机），所以按 750/550 等；再 +50ms 容错帧。
        internal const int SafetyGapLongMs = 750;
        internal const int SafetyGapShortMs = 550;
        internal const int SafetyTextThreshold = 20;
        internal const int SafetyBufferMs = 50;

        // 【真机补钉（task-226 / machine-runner d1e085a）】事件脚本里有 `pause` 命令（如 pause 8000），
        // 期间"对话文本没变"是**正常**的 —— 0.8s 间隔连点 3 次会把它误判成 advance_stalled。
        // 因此同一处最多点 3 次（首次 + 重试 2 次），每次间隔 ≥3.0s；三次都没有任何观测变化
        // 才判 stalled。脑侧另有"连续 2 次 stalled ⇒ 停止推进 + event_blocked"的守卫。
        internal const int StallRetries = 2;
        internal const int StallMaxClicks = StallRetries + 1;
        internal const int StallRetryGapMs = 3000;
        internal const int ConsecutiveStallLimit = 2;

        // 【dialogue-okfix / P1】关框后的宽限窗口。
        // 真机现象：推完最后一句、`DialogueBox` 关掉之后，事件脚本常在极短时间内把下一句
        // （甚至同一句的重放）又弹出来。旧实现"一看见 `box==null` 就立刻按成功返回"
        // ⇒ 每个请求只推 1 步、剩下的步数要等脑侧下一次轮询（实测一轮 ~15s）。
        // 现在关框后先宽限 REOPEN_GRACE_MS 看有没有**新的非提问** `DialogueBox`：
        // 有 ⇒ 在同一请求内接着按原逻辑推（仍受 maxSteps / timeout 约束）；没有 ⇒ 按成功收尾。
        internal const int ReopenGraceMs = 2000;

        /// <summary>`box==null`（已推进过）时该收尾还是继续等宽限。</summary>
        internal enum ClosedAfterProgress
        {
            /// <summary>按**成功**收尾（`FinishOk` ⇒ 回执 `ok=true`）。</summary>
            FinishOk = 0,

            /// <summary>还在宽限窗口里：本 tick 返回 null，下一 tick 再看有没有新对话框。</summary>
            KeepWaiting = 1,
        }

        // ---------------------------------------------------------------- 状态码
        // 与 Python 侧 `brain/agentfarm/longrun.py` 的守卫口径逐字对齐（见交付说明）。
        internal const string StatusOk = "ok";
        internal const string StatusNoDialogue = "no_dialogue";
        internal const string StatusIsQuestion = "is_question";
        internal const string StatusProfessionsPending = "professions_pending";
        internal const string StatusEventNotRunning = "event_not_running";
        internal const string StatusAdvanceStalled = "advance_stalled";
        internal const string StatusTimeout = "timeout";
        internal const string StatusMaxStepsReached = "max_steps_reached";
        internal const string StatusError = "error";

        // ---------------------------------------------------------------- 进度分类
        internal const string ProgressAdvanced = "advanced";
        internal const string ProgressTyping = "typing";
        internal const string ProgressStalled = "stalled";
        internal const string ProgressMenuReplaced = "menu_replaced";

        /// <summary>钳制 `maxSteps`：null ⇒ 默认（1）；越界夹到 [1, 10]（卡面范围）。</summary>
        internal static int ClampMaxSteps(int? maxSteps)
        {
            int v = maxSteps.HasValue ? maxSteps.Value : MaxStepsDefault;
            if (v < MaxStepsFloor) v = MaxStepsFloor;
            if (v > MaxStepsCap) v = MaxStepsCap;
            return v;
        }

        /// <summary>
        /// 调用前 fail-closed 判定（顺序固定，返回 `""` 表示可以点）。
        ///
        /// 顺序为什么这样：**越权的风险优先**。`is_question` 必须最先拦（点了就可能替玩家应答，
        /// 不可逆）；`professions_pending` 次之（职业选择同样不可逆）；`no_dialogue` 再往下
        /// （没东西可推）；最后才是 `event_not_running`（作用面限制）。
        /// </summary>
        internal static string Precheck(bool hasDialogue, bool isQuestion, bool professionsPending, bool eventUp)
        {
            if (isQuestion) return StatusIsQuestion;
            if (professionsPending) return StatusProfessionsPending;
            if (!hasDialogue) return StatusNoDialogue;
            if (!eventUp) return StatusEventNotRunning;
            return "";
        }

        /// <summary>两次**有效**点击之间的最小间隔（ms）：短句 550、长句 750，再 +50 容错。</summary>
        internal static int SafetyGapMs(int textLength)
        {
            int gap = textLength <= SafetyTextThreshold ? SafetyGapShortMs : SafetyGapLongMs;
            return gap + SafetyBufferMs;
        }

        /// <summary>
        /// 一次点击之后的进度分类（判据 = 观测差分，见文档 §3）。
        ///
        /// 输入全部是**点击前后拍到的观测**：
        /// * `menuReplaced`：`activeClickableMenu` 的 `DialogueBox` 实例换了（新对话框/新一页）；
        /// * `textChanged`：`getCurrentString()` 文本变了；
        /// * `indexCompleted`：`characterIndexInDialogue` 从"未补完"走到"补完"（第一次点击的正常结果）；
        /// * `menuTextChanged`：`UiRead.ActiveMenuText()` 变了（真机补钉：事件脚本 `pause`
        ///   期间文本可能不变，但菜单文本/事件状态变化仍算前进）；
        /// * `eventUpChanged`：`Game1.eventUp` 变了（事件结束 = 推进成功）。
        ///
        /// 任一为真都算 progress（避免把"补完打字"或 `pause` 误判成 stalled 而 fail-closed）；
        /// 全假才是 `stalled`。
        /// </summary>
        internal static string Classify(bool menuReplaced, bool textChanged, bool indexCompleted,
                                        bool menuTextChanged = false, bool eventUpChanged = false)
        {
            if (menuReplaced) return ProgressMenuReplaced;
            if (eventUpChanged) return ProgressAdvanced;
            if (menuTextChanged) return ProgressAdvanced;
            if (textChanged) return ProgressAdvanced;
            if (indexCompleted) return ProgressTyping;
            return ProgressStalled;
        }

        /// <summary>这一处"无变化"之后还该不该再点一次（首次+重试共 ≤3 次）。</summary>
        internal static bool ShouldRetryAfterNoChange(int noChangeCount)
        {
            return noChangeCount <= StallRetries;
        }

        /// <summary>脑侧守卫：连续多少次 `stalled` 就停止推进该事件（诚实收尾）。</summary>
        internal static bool ShouldGiveUpAfterStalls(int consecutiveStalls)
        {
            return consecutiveStalls >= ConsecutiveStallLimit;
        }

        /// <summary>progress 分类里哪些算"真的动了一下"（stalled 之外都算）。</summary>
        internal static bool IsProgress(string progress)
        {
            return progress == ProgressAdvanced || progress == ProgressTyping || progress == ProgressMenuReplaced;
        }

        /// <summary>
        /// 【P1】已经推进过 ≥1 步、且此刻 `DialogueBox` 为 null 时，接下来的动作。
        ///
        /// 判据顺序（同样是"越权/空转风险优先"）：
        ///   1. `eventUp==false` ⇒ 事件本身结束了，没有"下一句"可言 ⇒ 立刻按成功收尾；
        ///   2. 宽限未到 ⇒ 继续等（事件脚本常在关框后立刻弹出下一句）；
        ///   3. 宽限到点仍无框 ⇒ 按成功收尾。
        ///
        /// 注意：宽限只影响"等多久"，**不影响**能不能点 —— 点击仍然每次都过
        /// <see cref="Precheck"/>，提问/职业选择一次都不会点。
        /// </summary>
        internal static ClosedAfterProgress AfterBoxClosed(bool eventUp, long waitedMs)
        {
            if (!eventUp) return ClosedAfterProgress.FinishOk;
            if (waitedMs >= ReopenGraceMs) return ClosedAfterProgress.FinishOk;
            return ClosedAfterProgress.KeepWaiting;
        }
    }
}
