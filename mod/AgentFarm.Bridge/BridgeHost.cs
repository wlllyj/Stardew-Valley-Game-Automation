using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 桥接服务宿主：端口发现 / 令牌 / 路由 / 主线程工作编排 / bridge.json 生命周期。
    ///
    /// 【线程模型】
    ///   * 网络线程（HttpBridgeServer 的 worker）：只做 HTTP 解析与路由决策，
    ///     **绝不**直接访问 Game1.*；需要游戏数据的一律丢给 MainThreadDispatcher。
    ///   * 游戏主线程（UpdateTicked）：排空队列、推进技能、收集快照。
    /// 两侧唯一共享的是不可变 DTO 与 <see cref="WorldSnapshot"/> 的计数器。
    /// </summary>
    internal sealed class BridgeHost
    {
        public const string BridgeSchema = "agentfarm-bridge/1";

        private const int PortFirst = 17890;
        private const int PortLast = 17900;
        private const int RequestThreads = 4;
        private const int HeartbeatSeconds = 30;

        /// <summary>写 bridge.json 后，游戏若在此秒数内正常退出也不删文件（避免误删正在用的发现信息）。</summary>
        private static readonly TimeSpan HttpWaitPadding = TimeSpan.FromSeconds(15);

        private readonly IMonitor _monitor;
        private readonly MainThreadDispatcher _dispatcher = new MainThreadDispatcher();
        private readonly WorldObserver _world = new WorldObserver();

        private HttpBridgeServer _server;
        private string _token;
        private string _bridgeFilePath;

        private DateTime _startedAt = DateTime.UtcNow;
        private DateTime _lastHeartbeatUtc = DateTime.MinValue;
        private long _requestsServed;
        private volatile bool _farmScanWanted;

        /// <summary>
        /// 每帧兜底「失焦不暂停」时，本局把 <c>pauseWhenOutOfFocus</c> 从 true 扳回 false 的次数。
        /// 它是"这个选项真的被别处改回了 true"的**直接证据**（不是推理）。
        /// </summary>
        private long _oofFixCount;

        /// <summary>强制关闭「失焦暂停」抛异常的次数（只为把日志节流到一次）。</summary>
        private long _oofErrorCount;

        public BridgeHost(IMonitor monitor, string modVersion)
        {
            this._monitor = monitor;

            // 版本号必须来自 manifest.json（ModEntry 传 this.ModManifest.Version），
            // 不再写死：写死会让日志 / bridge.json / health 三处与 manifest 悄悄脱节。
            this.ModVersion = string.IsNullOrWhiteSpace(modVersion) ? "unknown" : modVersion.Trim();
        }

        /// <summary>Mod 版本号（形如 "0.2.0"），唯一来源是 manifest.json。</summary>
        public string ModVersion { get; }

        /// <summary>
        /// 是否逐条打印请求日志（方法/路径/状态码/耗时/worldSeq）。
        ///
        /// 用 <see cref="LogLevel.Trace"/> 打印：“脑”侧每秒可能问好几次 observe，
        /// 用 Info 会把 SMAPI 控制台刷满，反而看不见关键信息。
        /// 同时提供控制台命令 `afb verbose on|off` 把它临时抬到 Info，
        /// 这样真机排查时不需要重启游戏加 -verbose 参数。
        /// </summary>
        private volatile bool _verbose = true;

        public int Port => this._server?.Port ?? 0;
        public string BridgeFilePath => this._bridgeFilePath;

        // ==================================================================
        //  生命周期
        // ==================================================================

        /// <summary>启动：选端口 → 起监听 → 写发现文件。由 ModEntry 在 Entry 里调用。</summary>
        public void Start()
        {
            this._token = GenerateToken();
            this._startedAt = DateTime.UtcNow;

            // ---- 选端口：17890 起依次试，都失败则让系统分配 ----
            int chosen = -1;
            for (int port = PortFirst; port <= PortLast; port++)
            {
                if (this.TryStartServer(port)) { chosen = port; break; }
            }

            if (chosen < 0)
            {
                if (this.TryStartServer(0))
                {
                    chosen = this._server.Port;
                    this._monitor.Log($"17890-17900 全部被占用，改用系统分配的空闲端口 {chosen}。", LogLevel.Warn);
                }
            }

            if (chosen < 0)
            {
                this._monitor.Log("桥接服务启动失败：没有任何可用端口，HTTP 接口不可用。", LogLevel.Error);
                return;
            }

            this.WriteBridgeFile();

            this._monitor.Log("──────────────────────────────────────────────", LogLevel.Info);
            this._monitor.Log($"AgentFarm Bridge v{this.ModVersion} 已就绪（schema {BridgeSchema}）。", LogLevel.Info);
            this._monitor.Log($"  监听：http://127.0.0.1:{this._server.Port}", LogLevel.Info);
            this._monitor.Log($"  令牌文件：{this._bridgeFilePath}", LogLevel.Info);
            this._monitor.Log("  接口：GET /v1/health（免鉴权）· GET /v1/observe?detail=summary|full · POST /v1/exec", LogLevel.Info);
            this._monitor.Log("  控制台：afb verbose on|off|status", LogLevel.Info);
            this._monitor.Log("──────────────────────────────────────────────", LogLevel.Info);
        }

        private bool TryStartServer(int port)
        {
            var server = new HttpBridgeServer(port, RequestThreads, this.HandleRequest, this.Log);
            if (!server.Start()) return false;

            this._server = server;
            return true;
        }

        /// <summary>关闭：停监听 + 删发现文件。由 ModEntry 在 Exit 与 ReturnedToTitle 调用。</summary>
        public void Stop(bool deleteBridgeFile)
        {
            try { this._server?.Stop(); } catch { }
            this._server = null;

            if (deleteBridgeFile) this.DeleteBridgeFile();
        }

        /// <summary>每 tick 调用（主线程）。</summary>
        public void OnUpdateTicked()
        {
            // 必须**在**本帧游戏逻辑之前把「失焦暂停」关掉：UpdateTicked 由 Game1.Update 在
            // Game1._update 之前派发，而 _update 的第 IL_0466 行读取的就是这个字段。
            this.EnforceNoPauseOnFocusLoss();

            this._dispatcher.OnUpdateTicked();

            bool wantScan = this._farmScanWanted;
            this._farmScanWanted = false;      // 只加速“当前有 observe 在等”的那一轮
            this._world.OnTick(wantScan);

            // 心跳：定期重写 bridge.json（进程还在的信息比文件里那一行更可信）
            if ((DateTime.UtcNow - this._lastHeartbeatUtc).TotalSeconds >= HeartbeatSeconds)
            {
                this._lastHeartbeatUtc = DateTime.UtcNow;
                this.WriteBridgeFile();
            }
        }

        /// <summary>
        /// 每帧强制关闭「失焦自动暂停」（<c>Game1.options.pauseWhenOutOfFocus = false</c>）。
        ///
        /// 为什么必须每帧做，而不是在 GameLaunched 里设一次（v0.4.0 就是这么做的，**无效**）：
        /// `Game1._update` 的提前返回块（IL_0444–IL_0480）在窗口不活跃且该选项为 true 时
        /// **直接 ret**，于是 `UpdateGameClock`（IL_12C3）与 `UpdateLocations`（IL_12D1 →
        /// `Farmer.Update` → `PathFindController.update`）整段被跳过 —— 世界时钟停、角色不动，
        /// 而 `shouldTimePass()` 依旧返回 true（它根本没被调用）。
        /// 而读档时 `SaveGame+&lt;getLoadEnumerator&gt;d__101.MoveNext()` IL_1526–IL_1530
        /// 会用**存档文件里那份 Options 实例**整体替换 `Game1.options`（紧接 IL_162F 写回
        /// default_options），把我们在 GameLaunched 里改的值冲掉；回标题、新建游戏同理。
        /// 既然门是每帧重新读这个字段的，我们就在**每帧**（同一帧、游戏逻辑之前）把它关掉。
        ///
        /// 这样"游戏窗口必须保持前台"就不再是运行时的必要约束（无人值守的关键）。
        /// </summary>
        public void EnforceNoPauseOnFocusLoss()
        {
            try
            {
                var options = Game1.options;
                if (options == null) return;
                if (!options.pauseWhenOutOfFocus) return;

                options.pauseWhenOutOfFocus = false;
                long n = Interlocked.Increment(ref this._oofFixCount);

                // 只在第 1 次和之后每 ~20 秒记一次：这个函数每帧都跑，不节流会把控制台刷满。
                if (n == 1 || n % 1200 == 0)
                {
                    this._monitor.Log(
                        $"把「失焦自动暂停」扳回关闭（第 {n} 次）—— 它被改回 true 了（读档/回标题会整体换掉 Game1.options）。" +
                        "没有这一帧兜底，失焦时世界时钟与角色更新都会被跳过。", LogLevel.Info);
                }
            }
            catch (Exception ex)
            {
                // 每帧都跑：异常也只在第一次记，避免刷屏掩盖真正的问题。
                if (Interlocked.Increment(ref this._oofErrorCount) == 1)
                {
                    this._monitor.Log($"强制关闭「失焦自动暂停」失败（忽略，不影响其他功能）：{ex.Message}", LogLevel.Warn);
                }
            }
        }

        /// <summary>读档 / 换天：丢弃统计缓存。</summary>
        public void InvalidateWorldCache() => this._world.InvalidateFarmCache();

        // ==================================================================
        //  发现文件（%APPDATA%\StardewValley\AgentFarm\bridge.json）
        // ==================================================================

        private void WriteBridgeFile()
        {
            try
            {
                string path = this.BuildBridgeFilePath();
                if (path == null) return;

                string dir = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);

                var payload = new BridgeDiscovery
                {
                    Schema = BridgeSchema,
                    Port = this.Port,
                    Token = this._token,
                    Pid = Environment.ProcessId,
                    ModVersion = this.ModVersion,
                    GameVersion = GameVersionString(),
                    SmapiVersion = SmapiVersionString(),
                    StartedAt = this._startedAt.ToString("yyyy-MM-dd'T'HH:mm:sszzz", CultureInfo.InvariantCulture),
                };

                string json = JsonSerializer.Serialize(payload, JsonDefaults.Options);

                // 原子写：先写同目录下的临时文件，再 File.Move 覆盖。
                // 这样“脑”任何时刻读到的都是完整 JSON，不会读到写了一半的内容。
                string tmp = path + ".tmp";
                File.WriteAllText(tmp, json, new UTF8Encoding(false));
                File.Move(tmp, path, overwrite: true);

                this._bridgeFilePath = path;
            }
            catch (Exception ex)
            {
                this.Log($"写 bridge.json 失败：{ex.GetType().Name}: {ex.Message}", LogLevel.Error);
            }
        }

        private void DeleteBridgeFile()
        {
            try
            {
                if (this._bridgeFilePath != null && File.Exists(this._bridgeFilePath))
                {
                    File.Delete(this._bridgeFilePath);
                    this.Log($"已删除发现文件 {this._bridgeFilePath}。", LogLevel.Info);
                }

                if (this._bridgeFilePath != null)
                {
                    string tmp = this._bridgeFilePath + ".tmp";
                    if (File.Exists(tmp)) File.Delete(tmp);
                }
            }
            catch (Exception ex)
            {
                this.Log($"删除 bridge.json 失败（下次启动会被覆盖，不影响使用）：{ex.Message}", LogLevel.Warn);
            }
            finally
            {
                this._bridgeFilePath = null;
            }
        }

        private string BuildBridgeFilePath()
        {
            // Constants.DataPath = %APPDATA%\StardewValley（SMAPI 官方给出的游戏数据目录）
            string dataPath = null;
            try { dataPath = Constants.DataPath; } catch { }

            if (string.IsNullOrEmpty(dataPath)) return null;
            return Path.Combine(dataPath, "AgentFarm", "bridge.json");
        }

        private static string GenerateToken()
        {
            var bytes = new byte[16];   // 16 字节 = 32 个十六进制字符
            using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(bytes);

            var sb = new StringBuilder(32);
            foreach (byte b in bytes) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        /// <summary>
        /// 游戏版本字符串，形如 "1.6.15"。
        /// 走 <c>Game1.version</c>：实测 SMAPI 4.5.2 的 <c>Constants</c> 上**没有** GameVersion 属性（编译期 CS0117），
        /// 别改回去。
        /// </summary>
        private static string GameVersionString()
        {
            try { return Game1.version; } catch { return "unknown"; }
        }

        private static string SmapiVersionString()
        {
            try { return Constants.ApiVersion?.ToString() ?? "unknown"; }
            catch { return "unknown"; }
        }

        /// <summary>游戏窗口是否在前台。注意：焦点本身不决定世界走不走，真正的门是 pauseWhenOutOfFocus。</summary>
        private static bool GameWindowActive()
        {
            try { return Game1.game1?.IsActive ?? false; }
            catch { return false; }
        }

        /// <summary><c>Options.pauseWhenOutOfFocus</c> 的当前实际值（health 用）。</summary>
        private static bool SafePauseWhenOutOfFocus()
        {
            try { return Game1.options != null && Game1.options.pauseWhenOutOfFocus; }
            catch { return false; }
        }

        private sealed class BridgeDiscovery
        {
            [System.Text.Json.Serialization.JsonPropertyName("schema")] public string Schema { get; set; }
            [System.Text.Json.Serialization.JsonPropertyName("port")] public int Port { get; set; }
            [System.Text.Json.Serialization.JsonPropertyName("token")] public string Token { get; set; }
            [System.Text.Json.Serialization.JsonPropertyName("pid")] public int Pid { get; set; }
            [System.Text.Json.Serialization.JsonPropertyName("modVersion")] public string ModVersion { get; set; }
            [System.Text.Json.Serialization.JsonPropertyName("gameVersion")] public string GameVersion { get; set; }
            [System.Text.Json.Serialization.JsonPropertyName("smapiVersion")] public string SmapiVersion { get; set; }
            [System.Text.Json.Serialization.JsonPropertyName("startedAt")] public string StartedAt { get; set; }
        }

        // ==================================================================
        //  路由（网络线程）
        // ==================================================================

        private HttpResponse HandleRequest(HttpRequest req)
        {
            var sw = Stopwatch.StartNew();
            HttpResponse res;

            try
            {
                res = this.Route(req);
            }
            catch (Exception ex)
            {
                // 绝不允许异常逃逸到网络线程。
                res = HttpResponse.JsonError(500, "Internal Server Error", "服务端异常：" + ex.GetType().Name + ": " + ex.Message);
            }

            sw.Stop();
            Interlocked.Increment(ref this._requestsServed);

            this.LogRequest($"{(req.Method ?? "?")} {req.Path} → {res.StatusCode} · {sw.ElapsedMilliseconds}ms · worldSeq={this._world.WorldSeq}");

            return res;
        }

        private HttpResponse Route(HttpRequest req)
        {
            if (req.Method == "GET" && req.Path == "/v1/health")
                return HttpResponse.Json200(this.ServeHealth());

            // ---- 除 health 外一律鉴权 ----
            if (!this.IsAuthorized(req))
            {
                return HttpResponse.JsonError(401, "Unauthorized", "令牌不匹配");
            }

            if (req.Method == "GET" && req.Path == "/v1/observe")
                return this.ServeObserve(req, "summary");

            // 便于快速自检：/v1/observe/full 等价于 ?detail=full
            if (req.Method == "GET" && req.Path == "/v1/observe/full")
                return this.ServeObserve(req, "full");

            if (req.Method == "POST" && req.Path == "/v1/exec")
                return this.ServeExec(req);

            if (req.Path == "/v1/observe" || req.Path == "/v1/exec")
                return HttpResponse.JsonError(405, "Method Not Allowed", $"路径 {req.Path} 不支持 {req.Method} 方法");

            return HttpResponse.JsonError(404, "Not Found", $"未知路径：{req.Path}");
        }

        private bool IsAuthorized(HttpRequest req)
        {
            if (!req.Headers.TryGetValue("X-Auth-Token", out string provided)) return false;
            return string.Equals(provided, this._token, StringComparison.Ordinal);
        }

        // ==================================================================
        //  路由（主线程工作）
        // ==================================================================

        private string ServeHealth()
        {
            var health = new HealthResponse
            {
                Ok = true,
                Status = "ok",
                Schema = BridgeSchema,
                ModVersion = this.ModVersion,
                Game = new HealthGame
                {
                    Version = GameVersionString(),
                    Smapi = SmapiVersionString(),
                    WindowActive = GameWindowActive(),
                    PauseWhenOutOfFocus = SafePauseWhenOutOfFocus(),
                    OofFixCount = Interlocked.Read(ref this._oofFixCount),
                },
                Runtime = new HealthRuntime
                {
                    Ticks = this._dispatcher.Tick,
                    UptimeSeconds = Math.Round((DateTime.UtcNow - this._startedAt).TotalSeconds, 1),
                    WorldSeq = this._world.WorldSeq,
                    HasSaveLoaded = SafeWorldReady(),
                    OnTitleScreen = !SafeWorldReady(),
                },
                Server = new HealthServer
                {
                    Port = this.Port,
                    RequestsServed = Interlocked.Read(ref this._requestsServed),
                },
            };

            return JsonSerializer.Serialize(health, JsonDefaults.Options);
        }

        private static bool SafeWorldReady()
        {
            try { return Context.IsWorldReady; } catch { return false; }
        }

        private HttpResponse ServeObserve(HttpRequest req, string defaultDetail)
        {
            string detail = req.Query1("detail") ?? defaultDetail;
            this._farmScanWanted = true;

            object result;
            try
            {
                result = this._dispatcher.SubmitAndWait(isLongTask: false, timeoutMs: 10000, handler: () =>
                {
                    WorldSnapshotViewResult r = this._world.Observe(detail);
                    return r.Body;
                });
            }
            catch (Exception ex)
            {
                return HttpResponse.JsonError(500, "Internal Server Error", "生成快照失败：" + ex.GetType().Name + ": " + ex.Message);
            }

            if (result == null)
                return HttpResponse.JsonError(504, "Gateway Timeout", "主线程在 10 秒内没有响应（游戏可能正在读档/加载）");

            return HttpResponse.Json200(JsonSerializer.Serialize(result, JsonDefaults.Options));
        }

        /// <summary>
        /// 哪些技能是**跨 tick 长任务**（Handler 会在"还没走完"时返回 null，由调度器下个 tick 继续调用）。
        ///
        /// 【里程碑 B】move_to_location 与 move_to 共用 <see cref="StepMover"/> 状态机，同样跨 tick：
        /// 忘了把它加进来，症状会立刻变成"第一跳刚发起就把 null 交给网络线程"，
        /// 也就是条目 013 那类"接口报 ok、实际半途而废"的翻版。
        ///
        /// 【里程碑 C】load_save 同理：发起读档后要每 tick 等世界变可读，必须在这里。
        ///
        /// 【P3 步骤③】use_tool 也是：挥动 → 等 `player.UsingTool` 落回 false → 再看目标格 —— 天然跨 tick。
        ///
        /// 【P3 步骤⑤/⑥】sleep 也是：这一 tick 只把"睡觉"发起出去，之后每 tick 等
        /// `Game1.Date.TotalDays` 变大（跨日要淡黑 + 存档 + 换天，可能好几十秒）。
        ///
        /// buy 也是：`Utility.TryOpenShopMenu` 之后要等 `Game1.activeClickableMenu` 变成 `ShopMenu`
        /// 才能买（菜单不是同 tick 就挂上的）。买完是同 tick 返回终态。
        /// </summary>
        private static bool IsLongTaskSkill(string skill)
            => skill == "move_to" || skill == "move_to_location" || skill == "load_save"
            || skill == "use_tool" || skill == "plant" || skill == "sleep" || skill == "buy";

        private HttpResponse ServeExec(HttpRequest req)
        {
            ExecRequest exec;
            try
            {
                exec = string.IsNullOrWhiteSpace(req.Body)
                    ? new ExecRequest()
                    : JsonSerializer.Deserialize<ExecRequest>(req.Body, JsonDefaults.Options);
            }
            catch (JsonException ex)
            {
                return HttpResponse.JsonError(400, "Bad Request", "请求正文不是合法 JSON：" + ex.Message);
            }

            if (exec == null || string.IsNullOrWhiteSpace(exec.Skill))
                return HttpResponse.JsonError(400, "Bad Request", "缺少字段 skill");

            string skill = exec.Skill.Trim();

            // 未知技能：连主线程都不必碰
            if (!Skills.IsKnownSkill(skill))
            {
                return HttpResponse.Json200(JsonSerializer.Serialize(new ExecResponse
                {
                    Ok = false,
                    Status = "unknown_skill",
                    Skill = skill,
                    Reason = $"未知技能“{skill}”（本 Mod 不认识这个技能名）",
                }, JsonDefaults.Options));
            }

            int timeoutMs = Skills.ClampTimeoutFor(skill, exec.TimeoutMs);

            // stale 判定放在主线程里做，保证读到的 worldSeq 是执行当下的真值。
            Func<object> runner = Skills.Create(skill, exec, this._world, this._monitor);

            object result;
            try
            {
                result = this._dispatcher.SubmitAndWait(
                    isLongTask: IsLongTaskSkill(skill),
                    timeoutMs: timeoutMs + (int)HttpWaitPadding.TotalMilliseconds,
                    handler: () =>
                    {
                        long before = this._world.WorldSeq;

                        // 时效拒绝（阈值说明见 Skills.StaleSeqThreshold）
                        if (exec.BasedOnSeq.HasValue && skill != "noop")
                        {
                            long delta = before - exec.BasedOnSeq.Value;
                            if (delta > Skills.StaleSeqThreshold)
                            {
                                return new ExecResponse
                                {
                                    Ok = false,
                                    Status = "stale",
                                    Skill = skill,
                                    Reason = $"决策依据的世界快照已过期（based_on_seq={exec.BasedOnSeq.Value}，当前 worldSeq={before}，差 {delta} > {Skills.StaleSeqThreshold}），请重新 observe 后再下发",
                                    WorldSeqBefore = before,
                                    WorldSeqAfter = before,
                                    ElapsedMs = 0,
                                };
                            }
                        }

                        object inner = runner();
                        if (inner is ExecResponse er)
                        {
                            if (!er.WorldSeqBefore.HasValue) er.WorldSeqBefore = before;
                            if (!er.WorldSeqAfter.HasValue) er.WorldSeqAfter = this._world.WorldSeq;
                        }
                        return inner;
                    });
            }
            catch (Exception ex)
            {
                return HttpResponse.Json200(JsonSerializer.Serialize(new ExecResponse
                {
                    Ok = false,
                    Status = "error",
                    Skill = skill,
                    Reason = "执行异常：" + ex.GetType().Name + ": " + ex.Message,
                }, JsonDefaults.Options));
            }

            if (result == null)
            {
                return HttpResponse.Json200(JsonSerializer.Serialize(new ExecResponse
                {
                    Ok = false,
                    Status = "timeout",
                    Skill = skill,
                    Reason = $"等待执行结果超时（{timeoutMs}ms 预算 + {HttpWaitPadding.TotalSeconds:0} 秒余量已用尽）",
                }, JsonDefaults.Options));
            }

            return HttpResponse.Json200(JsonSerializer.Serialize(result, JsonDefaults.Options));
        }

        private void Log(string message, LogLevel level)
        {
            try { this._monitor.Log(message, level); } catch { }
        }

        /// <summary>逐条打印每个请求（方法、路径、状态码、耗时、worldSeq）。</summary>
        private void LogRequest(string message)
        {
            if (!this._verbose) return;
            this.Log(message, LogLevel.Info);
        }

        /// <summary>控制台命令入口：afb verbose on|off|status。</summary>
        public string HandleCommand(string[] args)
        {
            string sub = args.Length > 0 ? args[0].Trim().ToLowerInvariant() : "status";

            switch (sub)
            {
                case "on":
                    this._verbose = true;
                    return "已开启逐条请求日志。";
                case "off":
                    this._verbose = false;
                    return "已关闭逐条请求日志（启动信息与错误仍会打印）。";
                case "status":
                    return $"逐条请求日志：{(this._verbose ? "开启" : "关闭")}；"
                         + $"端口 {this.Port}；已服务 {Interlocked.Read(ref this._requestsServed)} 个请求；"
                         + $"worldSeq {this._world.WorldSeq}；worldAdvancing {this._world.WorldIsAdvancing}；"
                         + $"令牌文件 {this._bridgeFilePath ?? "(未写入)"}";
                default:
                    return "用法：afb [verbose on|off|status]";
            }
        }
    }
}
