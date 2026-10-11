using System;
using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// AgentFarm Bridge —— 《星露谷》自动化项目的“桥接 Mod”。
    ///
    /// 职责边界（架构文档 §4“体”侧的最低两层）：
    ///   ⓪ 主线程队列排空：所有游戏对象访问都发生在 UpdateTicked 上；
    ///   ① 感知层：/v1/observe 导出世界快照；
    ///   ③ 通信层：127.0.0.1 上的极简 HTTP/JSON + 令牌。
    ///
    /// 里程碑 A 范围：看得见（observe）+ 走得动（move_to）、noop。
    /// 本文件只做“装配与生命周期”，不含业务逻辑。
    /// </summary>
    public sealed class ModEntry : Mod
    {
        private BridgeHost _host;

        public override void Entry(IModHelper helper)
        {
            this._host = new BridgeHost(this.Monitor, SafeModVersion());

            helper.Events.GameLoop.GameLaunched += this.OnGameLaunched;
            helper.Events.GameLoop.SaveLoaded += this.OnSaveLoaded;
            helper.Events.GameLoop.DayStarted += this.OnDayStarted;
            helper.Events.GameLoop.UpdateTicked += this.OnUpdateTicked;
            helper.Events.GameLoop.ReturnedToTitle += this.OnReturnedToTitle;

            // 真机排查用的小命令：afb verbose on|off|status
            // 存在意义：mod 启动后看不出“请求到底有没有打进来”，
            // 而 SMAPI 默认只显示 Info 及以上级别的日志。
            helper.ConsoleCommands.Add("afb",
                "AgentFarm Bridge 控制。用法: afb [verbose on|off|status]",
                (command, args) => this.Monitor.Log(this._host.HandleCommand(args), LogLevel.Info));

            // 启动顺序说明：Entry 里就把服务起起来。
            // 理由：无人值守时“脑”需要在游戏还在标题画面时就能发现端口与令牌，
            // 而不是等到读档完成；未读档时 /v1/observe 会诚实地回 no_save。
            this._host.Start();

            this.Monitor.Log($"AgentFarm Bridge v{this._host.ModVersion} 已加载（SMAPI {SafeSmapiVersion()}，游戏 {SafeGameVersion()}）。", LogLevel.Info);
        }

        // ==================================================================
        //  事件
        // ==================================================================

        private void OnGameLaunched(object sender, GameLaunchedEventArgs e)
        {
            // 「失焦不暂停」—— 无人值守的硬条件（v0.5.0 起由 BridgeHost.EnforceNoPauseOnFocusLoss 每帧兜底）。
            //
            // 为什么需要：`Game1._update` 的提前返回块（IL_0444–IL_0480）在窗口不活跃且
            // `Game1.options.pauseWhenOutOfFocus == true` 时**直接 ret**，于是
            // `UpdateGameClock`（IL_12C3）与 `UpdateLocations`（IL_12D1）整段被跳过 ——
            // 世界时钟停、角色不动，而 `shouldTimePass()` 仍返回 true（它压根没被调用）。
            //
            // ⚠️ 这里设一次**是不够的**（v0.4.0 的教训）：读档时
            // `SaveGame+<getLoadEnumerator>d__101.MoveNext()` IL_1526–IL_1530 会用存档里那份
            // Options 实例整体替换 `Game1.options`，把这里的修改冲掉（回标题/新建游戏同理）。
            // 所以真正的兜底在每帧（见 BridgeHost），这里只负责"读档之前"的那段时间。
            try
            {
                if (Game1.options != null && Game1.options.pauseWhenOutOfFocus)
                {
                    Game1.options.pauseWhenOutOfFocus = false;
                    this.Monitor.Log("已关闭“失焦自动暂停”（pauseWhenOutOfFocus=false）。注意：读档会换掉整个 Game1.options，"
                                     + "所以真正的兜底是每帧强制（health 里的 oofFixCount 是证据）。", LogLevel.Info);
                }
                else if (Game1.options != null)
                {
                    this.Monitor.Log("“失焦自动暂停”已是关闭状态（pauseWhenOutOfFocus=false）。", LogLevel.Info);
                }
            }
            catch (Exception ex)
            {
                this.Monitor.Log($"设置 pauseWhenOutOfFocus 失败（不影响其他功能）：{ex.Message}", LogLevel.Warn);
            }
        }

        private void OnSaveLoaded(object sender, SaveLoadedEventArgs e)
        {
            this._host.InvalidateWorldCache();
            this.Monitor.Log($"存档已加载：{SafePlayerName()} @ {SafeLocationName()}。桥接接口就绪。", LogLevel.Info);
        }

        private void OnDayStarted(object sender, DayStartedEventArgs e)
        {
            this._host.InvalidateWorldCache();
        }

        private void OnUpdateTicked(object sender, UpdateTickedEventArgs e)
        {
            // 注意：这里**不做** Context.IsWorldReady 的提前返回。
            // 队列必须始终被排空 —— 否则未读档时 /v1/observe 会一直挂着等超时，
            // “脑”看到的就只是“连接超时”而不是清晰的 no_save。
            try
            {
                this._host.OnUpdateTicked();
            }
            catch (Exception ex)
            {
                // 主线程异常绝不允许逃逸（会崩游戏）。
                this.Monitor.Log($"桥接主循环异常（已吞掉，不影响游戏）：{ex}", LogLevel.Error);
            }
        }

        private void OnReturnedToTitle(object sender, ReturnedToTitleEventArgs e)
        {
            this._host.InvalidateWorldCache();
        }

        /// <summary>
        /// mod 卸载（含游戏正常退出）时清理：关监听 + 删 bridge.json。
        /// 注意 SMAPI 的 IGameLoopEvents 里没有 GameExiting 事件（实测 4.5.2），
        /// 所以“退出清理”就靠这个重写点。
        /// </summary>
        protected override void Dispose(bool disposing)
        {
            try { this._host?.Stop(deleteBridgeFile: true); } catch { }
            base.Dispose(disposing);
        }

        // ==================================================================
        //  小工具
        // ==================================================================

        private static string SafeSmapiVersion()
        {
            try { return Constants.ApiVersion?.ToString() ?? "?"; } catch { return "?"; }
        }

        /// <summary>
        /// Mod 版本号，取自 manifest.json（<c>ModManifest.Version</c>）。
        /// 【为什么不再写死】写死的常量会让日志、bridge.json、health 三处与 manifest 脱节
        /// （真机上就出现过 manifest=0.2.0 而三处都报 0.1.0）。
        /// </summary>
        private string SafeModVersion()
        {
            try { return this.ModManifest?.Version?.ToString() ?? "unknown"; } catch { return "unknown"; }
        }

        private static string SafeGameVersion()
        {
            try { return Game1.version; } catch { return "?"; }
        }

        private static string SafePlayerName()
        {
            try { return Game1.player?.Name ?? "?"; } catch { return "?"; }
        }

        private static string SafeLocationName()
        {
            try { return Game1.currentLocation?.Name ?? "?"; } catch { return "?"; }
        }
    }
}
