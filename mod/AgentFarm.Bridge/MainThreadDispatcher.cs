using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 主线程调度器 —— 本 Mod 的线程纪律中枢。
    ///
    /// 【铁律】网络线程**绝不**直接碰任何游戏对象。
    /// 所有需要读/写游戏状态的工作都封装成 <see cref="WorkItem"/> 入队，
    /// 由 <c>helper.Events.GameLoop.UpdateTicked</c> 在游戏主线程排空执行，
    /// 再用 <see cref="WorkItem.Completion"/>（TaskCompletionSource）把结果交回网络线程。
    ///
    /// 【为什么不直接把整件事做完】
    /// `move_to` 天生要跨 tick 推进（走 40 格要十几秒）。如果主线程上一次跑完，
    /// 游戏就会整段卡死。所以工作项分两种：
    ///   * 短工作（observe / 参数校验）：Handler 一次调用即返回非 null 结果；
    ///   * 长任务（exec move_to）：Handler 返回 null 表示“本 tick 还没完”，
    ///     下个 tick 继续被调用，直到返回非 null。
    /// 同时在跑的**长任务最多 1 个**（架构 §2 原则 6“一次一件事”）。
    ///
    /// 【每 tick 预算】长任务步进 1 次 + 队列最多再消费 <see cref="MaxQueueDrainPerTick"/> 个短工作。
    /// 宁可让网络侧多等几毫秒，也不把帧率拖垮。
    /// </summary>
    internal sealed class MainThreadDispatcher
    {
        /// <summary>每次 UpdateTicked 最多从队列里取出并执行几个短工作项（长任务步进另算）。</summary>
        private const int MaxQueueDrainPerTick = 2;

        private readonly ConcurrentQueue<WorkItem> _queue = new ConcurrentQueue<WorkItem>();
        private readonly object _longLock = new object();
        private WorkItem _activeLong;      // 允许跨 tick 推进的长任务（同一时刻至多 1 个）
        private long _tick;

        /// <summary>长任务硬上限（毫秒）。任何长任务都不该无限占槽（卡死/寻路死循环的兜底）。
        /// 90s 远超正常走位自限（~60s），仅作最后保险；与脑侧 busy 重试总时长（~90s）对齐。</summary>
        private const long MaxLongTaskMs = 90_000;

        /// <summary>当前长任务已运行的真实时长（用于硬上限判定，帧率无关）。</summary>
        private readonly System.Diagnostics.Stopwatch _longTaskWatch = new System.Diagnostics.Stopwatch();

        /// <summary>当前 tick 序号（主线程自增，网络线程只读，用于日志与诊断）。</summary>
        public long Tick => Interlocked.Read(ref _tick);

        /// <summary>是否有长任务正在执行。</summary>
        public bool HasActiveLongTask { get { lock (_longLock) return _activeLong != null; } }

        /// <summary>
        /// 把工作项交给主线程并同步等待结果（由网络线程调用）。
        /// </summary>
        /// <returns>成功时返回工作项产出的对象；超时返回 null（调用方负责回 504）。</returns>
        public object SubmitAndWait(bool isLongTask, int timeoutMs, Func<object> handler)
        {
            var item = new WorkItem(isLongTask, handler);
            _queue.Enqueue(item);

            if (!item.Completion.Task.Wait(timeoutMs))
            {
                // 注意：**不做**“超时后强杀工作项”。
                // 长任务半路中断会把玩家丢在寻路控制器里，比多跑两秒糟糕得多；
                // 这里只是没人接收结果，下一次 exec 会直接拿到 busy。
                return null;
            }

            // GetAwaiter().GetResult()：原样抛出内部异常（不包成 AggregateException）。
            return item.Completion.Task.GetAwaiter().GetResult();
        }

        /// <summary>主线程：更新 tick 计数并排空队列（由 UpdateTicked 调用）。</summary>
        public void OnUpdateTicked()
        {
            Interlocked.Increment(ref _tick);

            // ---- 0) 长任务硬上限兜底（防占槽死锁）----
            // 任何长任务都不该无限占槽。MoveToLocation 等走位自限 ~60s，但寻路死循环/
            // 卡死会让槽位被永远占住（真机 9VXBtA 在 Town 的死锁根因）。这里给一个 90s
            // 硬上限：超时就强制释放槽位、清场（HaltPlayer），并把该工作项以超时失败告终
            // （ServeExec 的 try/catch 会转成 ok=false 回执，脑侧会当作硬错误而非 busy 重试）。
            lock (_longLock)
            {
                if (_activeLong != null && !_activeLong.IsDone
                    && _longTaskWatch.ElapsedMilliseconds > MaxLongTaskMs)
                {
                    WorkItem stuck = _activeLong;
                    _activeLong = null;
                    _longTaskWatch.Stop();
                    _longTaskWatch.Reset();
                    try { StepMover.HaltPlayer(); } catch { /* 清场失败也不能让主线程崩 */ }
                    stuck.Fail(new TimeoutException(
                        $"长任务超过 {MaxLongTaskMs}ms 硬上限被强制终止（疑似卡死/占槽，已调用 HaltPlayer 清场）"));
                }
            }

            // ---- 1) 长任务若已结束，先释放槽位 ----
            lock (_longLock)
            {
                if (_activeLong != null && _activeLong.IsDone)
                {
                    _activeLong = null;
                    _longTaskWatch.Stop();
                    _longTaskWatch.Reset();
                }
            }

            // ---- 2) 队列排空（有界）----
            for (int i = 0; i < MaxQueueDrainPerTick; i++)
            {
                if (!_queue.TryPeek(out WorkItem head)) break;

                if (head.IsLongTask && HasActiveLongTask)
                {
                    // 一次只允许一件事：已经在跑长任务时，排在后面的 exec 直接拒绝。
                    if (_queue.TryDequeue(out WorkItem rejected)) rejected.RejectBusy();
                    continue;
                }

                if (!_queue.TryDequeue(out WorkItem item)) break;

                if (item.IsLongTask)
                {
                    lock (_longLock)
                    {
                        _activeLong = item;
                        _longTaskWatch.Restart();
                    }
                }

                RunOne(item);
            }

            // ---- 3) 长任务步进（每 tick 恰好一次）----
            WorkItem active;
            lock (_longLock) active = _activeLong;
            if (active != null)
            {
                RunOne(active);
                if (active.IsDone)
                {
                    lock (_longLock)
                    {
                        if (ReferenceEquals(_activeLong, active)) _activeLong = null;
                        _longTaskWatch.Stop();
                        _longTaskWatch.Reset();
                    }
                }
            }
        }

        /// <summary>在游戏主线程执行/推进一个工作项。任何异常都被转成异常结果，绝不允许逃逸到游戏主线程。</summary>
        private static void RunOne(WorkItem item)
        {
            if (item.IsDone) return;

            try
            {
                object result = item.Handler();
                if (item.IsLongTask && result == null)
                    return;   // 长任务还没跑完：本 tick 到此为止，下 tick 继续

                item.Complete(result);
            }
            catch (Exception ex)
            {
                // 绝不允许异常逃逸到游戏主线程（会让整个游戏崩掉）。
                item.Fail(ex);
            }
        }

        /// <summary>
        /// 一个“待办项”。长任务的 Handler 返回 null 表示“本 tick 还没完”。
        /// </summary>
        internal sealed class WorkItem
        {
            public readonly bool IsLongTask;
            public readonly Func<object> Handler;
            public readonly TaskCompletionSource<object> Completion =
                new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);

            private int _done;

            public WorkItem(bool isLongTask, Func<object> handler)
            {
                this.IsLongTask = isLongTask;
                this.Handler = handler;
            }

            public bool IsDone => Volatile.Read(ref _done) != 0;

            public void Complete(object result)
            {
                Volatile.Write(ref _done, 1);
                Completion.TrySetResult(result);
            }

            public void Fail(Exception ex)
            {
                Volatile.Write(ref _done, 1);
                Completion.TrySetException(ex);
            }

            /// <summary>队列积压时的快速拒绝：不占用主线程，直接把 busy 交回网络线程。</summary>
            public void RejectBusy()
            {
                Volatile.Write(ref _done, 1);
                Completion.TrySetResult(new ExecResponse
                {
                    Ok = false,
                    Status = "busy",
                    Reason = "已有技能正在执行，同一时刻只允许一个 exec（一次一件事）",
                });
            }
        }
    }
}
