using System;
using System.Reflection;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【Option A / task-253】`skip_event`：程序化结束当前游戏事件（等价于玩家敲 `endevent` 调试命令）。
    ///
    /// 【要解决的问题（真机事故，A9 spring1）】
    /// spring1 存在双事件：Kent 归来 `eventId=63`（纯自动过场，计时/动画播完自行结束，Fix A 成立）
    /// 与进 Town 触发的 `eventId=15389722`（command 48 = playerControl 形态，等玩家动作/移动）。
    /// 后者在 `eventUp` 下**没有任何脑侧合法游戏动作**：`StepMover` 在 `Game1.eventUp` 时拒移动、
    /// 桥只暴露 `dismiss_modal`/`advance_dialogue`（都只对 `DialogueBox`）⇒ 事件无限冻结、从 spring1
    /// 起跑必死于 day1，全部 save-backups 都没有"已过 spring1"基线。
    ///
    /// 【原语选择（IL/调试命令实证）】
    /// 游戏原生 `endevent`/`leaveevent` 调试命令就是调 `Game1.CurrentEvent.skipEvent()`（fallback
    /// `exitEvent`）。这里用反射调同一入口，**不伪造输入、不替游戏选选项**：只是告诉事件"按你的
    /// 跳过逻辑立刻结束"，与玩家在控制台敲 `endevent` 语义完全一致——是"主动合理结束事件"，
    /// 不是"替游戏做决定"。
    ///
    /// 【绝不越权（fail-closed）】
    ///   * 没有事件在跑（`Game1.eventUp=false` 或 `Game1.CurrentEvent==null`）⇒ 回 `no_event`，
    ///     一次都不调；
    ///   * 绝不用于"有对话盒"的事件（那应交给 `advance_dialogue` 推非提问对话）；脑侧只在
    ///     "无对话框冻结态"触发本技能；
    ///   * `skipEvent()` 抛异常 ⇒ 回 `skip_threw`，不静默当成功。
    ///
    /// 【单 tick（不进 LongTask）】本技能是**同步**的：调一次跳过逻辑即终态，不需要跨 tick 等外部
    /// 状态。事件真正结束（`eventUp` 转 false）发生在**下一 tick**，由脑侧重观测确认——所以回执
    /// 状态是 `skip_issued`（"已发出跳过指令"），不是"已结束"。`SkillCatalog` 据此**不**把
    /// `skip_event` 登记为长任务。
    /// </summary>
    internal sealed class SkipEventSkill
    {
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly DateTime _startedUtc = DateTime.UtcNow;

        // Game1.CurrentEvent 是 public static Property（1.6.x 实证存在）；拿不到就走反射兜底。
        private static readonly PropertyInfo CurrentEventProp =
            typeof(Game1).GetProperty("CurrentEvent", BindingFlags.Public | BindingFlags.Static);

        // Event.skipEvent() 是 public 实例方法，无参、返回 void（调试命令 endevent 同入口）。
        private static readonly MethodInfo SkipMethod =
            typeof(Event).GetMethod("skipEvent",
                BindingFlags.Public | BindingFlags.Instance, null, Type.EmptyTypes, null);

        // 兜底：exitEvent(object cause, bool fromSave)（部分版本 skipEvent 内部就调它）。
        private static readonly MethodInfo ExitMethod =
            typeof(Event).GetMethod("exitEvent",
                BindingFlags.Public | BindingFlags.Instance, null,
                new[] { typeof(object), typeof(bool) }, null);

        public SkipEventSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._world = world;
            this._monitor = monitor;
        }

        private long Elapsed()
        {
            double ms = (DateTime.UtcNow - this._startedUtc).TotalMilliseconds;
            return ms < 0 ? 0 : (long)ms;
        }

        /// <summary>主线程每 tick 调一次；返回非 null = 终态（本技能单次即终态）。</summary>
        public object Step()
        {
            try
            {
                bool eventUp = Game1.eventUp;
                object currentEvent = GetCurrentEvent();
                if (!eventUp || currentEvent == null)
                {
                    return Build(false, "no_event",
                        $"当前没有正在运行的事件（eventUp={eventUp}，CurrentEvent="
                        + (currentEvent == null ? "null" : "有") + "）⇒ 不调用跳过逻辑");
                }

                // 反射调 skipEvent()；反射失败（签名差异/版本）再试 exitEvent(null, false)。
                try
                {
                    if (SkipMethod != null)
                    {
                        SkipMethod.Invoke(currentEvent, null);
                    }
                    else if (ExitMethod != null)
                    {
                        ExitMethod.Invoke(currentEvent, new object[] { null, false });
                    }
                    else
                    {
                        return Build(false, "unsupported",
                            "Game1.CurrentEvent 上既找不到 skipEvent() 也找不到 exitEvent()"
                            + "（游戏版本/反射受限）⇒ 无法程序化跳过");
                    }
                }
                catch (TargetInvocationException tie)
                {
                    Exception inner = tie.InnerException ?? tie;
                    return Build(false, "skip_threw",
                        $"跳过逻辑抛出异常：{inner.GetType().Name}: {inner.Message}");
                }

                this._monitor?.Log($"skip_event：已对当前事件调用跳过逻辑（eventUp={eventUp}）");
                // 事件真正结束（eventUp 转 false）要在下一 tick / 脑侧重观测才能确认；
                // 这里只回"已发出跳过指令"，由脑侧核对终态（见 longrun._try_skip_event）。
                return Build(true, "skip_issued",
                    "已对当前事件调用 skipEvent()/exitEvent()（等价于玩家 endevent）。"
                    + "事件真正结束（eventUp 转 false）要在下一 tick，由脑侧重观测确认");
            }
            catch (Exception ex)
            {
                return Build(false, "error", $"执行异常：{ex.GetType().Name}: {ex.Message}");
            }
        }

        /// <summary>
        /// 取当前事件：先走 public static <see cref="Game1.CurrentEvent"/> 属性，拿不到再退到
        /// <c>Game1.currentLocation.currentEvent</c>（字段/属性双兜底，跨版本更稳）。
        /// </summary>
        private static object GetCurrentEvent()
        {
            try
            {
                if (CurrentEventProp != null)
                {
                    object ev = CurrentEventProp.GetValue(null);
                    if (ev != null) return ev;
                }

                FieldInfo locField = typeof(Game1).GetField("currentLocation",
                    BindingFlags.Public | BindingFlags.Static);
                object loc = locField?.GetValue(null);
                if (loc != null)
                {
                    PropertyInfo evProp = loc.GetType().GetProperty("currentEvent",
                        BindingFlags.Public | BindingFlags.Instance);
                    object ev = evProp?.GetValue(loc);
                    if (ev != null) return ev;

                    FieldInfo evField = loc.GetType().GetField("currentEvent",
                        BindingFlags.Public | BindingFlags.Instance);
                    ev = evField?.GetValue(loc);
                    if (ev != null) return ev;
                }
            }
            catch
            {
                // 读不到事件对象 ⇒ 当"无事件"处理（fail-closed，不猜）。
            }

            return null;
        }

        private ExecResponse Build(bool ok, string status, string reason)
        {
            return new ExecResponse
            {
                Ok = ok,
                Status = status,
                Skill = "skip_event",
                Reason = reason,
                Schema = Skills.ExecSchema,
                ElapsedMs = this.Elapsed(),
                WorldSeqBefore = this._world != null ? this._world.WorldSeq : (long?)null,
                WorldSeqAfter = this._world != null ? this._world.WorldSeq : (long?)null,
            };
        }
    }
}
