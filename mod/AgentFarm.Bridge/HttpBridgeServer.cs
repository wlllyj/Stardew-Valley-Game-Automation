using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace AgentFarm.Bridge
{
    /// <summary>一次 HTTP 请求（已解析）。</summary>
    internal sealed class HttpRequest
    {
        public string Method;
        public string Path;                                   // 已解码，不含查询串
        public string RawTarget;
        public Dictionary<string, string> Query = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, string> Headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        public string Body = "";

        public string Query1(string key) => this.Query.TryGetValue(key, out string v) ? v : null;
    }

    internal sealed class HttpResponse
    {
        public int StatusCode = 200;
        public string ReasonPhrase = "OK";
        public string Json = "{}";
        /// <summary>鉴权等失败时用的纯文本响应（不是 JSON 时置 false）。</summary>
        public bool IsJson = true;

        public static HttpResponse Json200(string json) => new HttpResponse { StatusCode = 200, ReasonPhrase = "OK", Json = json };
        public static HttpResponse JsonError(int code, string phrase, string reason)
            => new HttpResponse
            {
                StatusCode = code,
                ReasonPhrase = phrase,
                Json = Json.Serialize(new ErrorResponse { Ok = false, Status = StatusForCode(code), Reason = reason }),
            };

        private static string StatusForCode(int code)
        {
            switch (code)
            {
                case 400: return "bad_request";
                case 401: return "unauthorized";
                case 404: return "not_found";
                case 405: return "method_not_allowed";
                case 413: return "payload_too_large";
                case 500: return "error";
                case 504: return "timeout";
                default: return "error";
            }
        }
    }

    /// <summary>
    /// 极简 HTTP/1.1 服务器（手写，不用 HttpListener）。
    ///
    /// 【为什么不用 HttpListener】
    /// Windows 上 HttpListener 绑 URL 前缀需要 URL ACL 或管理员权限，
    /// 无人值守部署时会变成“有时能起、有时起不来”的玄学故障。
    /// TcpListener 绑 127.0.0.1 不需要任何特权，行为完全确定。
    ///
    /// 【支持范围】GET / POST + JSON；请求行 + 请求头 + 按 Content-Length 读正文；
    /// 响应统一带 Content-Type / Content-Length / Connection: close。
    /// 不支持 chunked、keep-alive、分块上传 —— 本项目的“脑”只用最朴素的 http.client。
    /// </summary>
    internal sealed class HttpBridgeServer : IDisposable
    {
        private const int HeaderByteLimit = 32 * 1024;
        private const int BodyByteLimit = 1024 * 1024;
        private const int IoTimeoutMs = 15000;

        private readonly Action<string, StardewModdingAPI.LogLevel> _log;
        private readonly Func<HttpRequest, HttpResponse> _handler;
        private readonly int _workerCount;

        private TcpListener _listener;
        private Thread[] _workers;
        private volatile bool _stopping;

        /// <summary>实际绑定到的端口。</summary>
        public int Port { get; private set; }

        /// <summary>已服务的请求数（含失败）。</summary>
        public long RequestsServed;

        public HttpBridgeServer(int port, int workerCount, Func<HttpRequest, HttpResponse> handler, Action<string, StardewModdingAPI.LogLevel> log)
        {
            this.Port = port;
            this._workerCount = workerCount;
            this._handler = handler;
            this._log = log;
        }

        /// <summary>启动监听。返回是否成功。</summary>
        public bool Start()
        {
            try
            {
                var listener = new TcpListener(IPAddress.Loopback, this.Port);
                // TcpListener.Start 在端口被占用时抛 SocketException。
                listener.Start(64);
                this._listener = listener;

                var endpoint = (IPEndPoint)listener.LocalEndpoint;
                this.Port = endpoint.Port;   // Port 传 0 时这里拿到系统分配的空闲端口

                this._workers = new Thread[this._workerCount];
                for (int i = 0; i < this._workers.Length; i++)
                {
                    var t = new Thread(this.AcceptLoop)
                    {
                        IsBackground = true,
                        Name = "AgentFarm.Bridge.HttpWorker" + i,
                    };
                    this._workers[i] = t;
                    t.Start();
                }

                return true;
            }
            catch (Exception ex)
            {
                this._log($"HTTP 监听启动失败（端口 {this.Port}）：{ex.Message}", StardewModdingAPI.LogLevel.Error);
                return false;
            }
        }

        public void Stop()
        {
            this._stopping = true;
            try { this._listener?.Stop(); } catch { }
        }

        public void Dispose() => this.Stop();

        // ==================================================================
        //  接受连接
        // ==================================================================

        private void AcceptLoop()
        {
            while (!this._stopping)
            {
                TcpClient client = null;
                try
                {
                    client = this._listener.AcceptTcpClient();
                }
                catch (Exception)
                {
                    // Stop() 会让 AcceptTcpClient 抛异常；正常退出路径。
                    if (this._stopping) return;
                    Thread.Sleep(50);
                    continue;
                }

                // 每个连接同步处理完再接受下一个 —— 请求量极小（每秒几次），
                // 这样实现最简单，也不会出现并发访问共享状态的坑。
                try
                {
                    client.ReceiveTimeout = IoTimeoutMs;
                    client.SendTimeout = IoTimeoutMs;
                    this.HandleConnection(client);
                }
                catch (Exception ex)
                {
                    this._log($"处理连接时异常（已忽略，不影响游戏）：{ex.GetType().Name}: {ex.Message}", StardewModdingAPI.LogLevel.Trace);
                }
                finally
                {
                    try { client.Close(); } catch { }
                }
            }
        }

        private void HandleConnection(TcpClient client)
        {
            Interlocked.Increment(ref this.RequestsServed);

            using NetworkStream stream = client.GetStream();
            HttpRequest req = this.ReadRequest(stream);
            if (req == null)
            {
                // 连请求行都没读到（端口探测/空连接）——安静关闭。
                return;
            }

            HttpResponse res;
            try
            {
                res = this._handler(req);
            }
            catch (Exception ex)
            {
                // handler 内部已经做了兜底，这里是最后一道保险。
                res = HttpResponse.JsonError(500, "Internal Server Error", "服务端异常：" + Summarize(ex));
            }

            this.WriteResponse(stream, res);
        }

        // ==================================================================
        //  读取请求
        // ==================================================================

        private HttpRequest ReadRequest(NetworkStream stream)
        {
            // ---- 逐字节读，直到 \r\n\r\n（限制总长度）----
            var head = new MemoryStream();
            int matched = 0;   // 已连续匹配 "\r\n\r\n" 的字节数
            int b;
            while (matched < 4)
            {
                b = stream.ReadByte();
                if (b < 0) return null;                 // 连接提前关闭
                head.WriteByte((byte)b);
                if (head.Length > HeaderByteLimit) return null;

                switch (matched)
                {
                    case 0: matched = (b == '\r') ? 1 : 0; break;
                    case 1: matched = (b == '\n') ? 2 : (b == '\r' ? 1 : 0); break;
                    case 2: matched = (b == '\r') ? 3 : 0; break;
                    case 3: matched = (b == '\n') ? 4 : 0; break;
                }
            }

            string headText = Encoding.UTF8.GetString(head.ToArray());
            string[] lines = headText.Split(new[] { "\r\n" }, StringSplitOptions.None);
            if (lines.Length == 0 || string.IsNullOrWhiteSpace(lines[0])) return null;

            string[] parts = lines[0].Split(' ');
            if (parts.Length < 3) return null;

            var req = new HttpRequest
            {
                Method = parts[0].Trim().ToUpperInvariant(),
                RawTarget = parts[1],
            };

            // 目标拆成 path + query
            string target = req.RawTarget;
            int q = target.IndexOf('?');
            string rawPath = q >= 0 ? target.Substring(0, q) : target;
            string rawQuery = q >= 0 ? target.Substring(q + 1) : "";
            req.Path = Decode(rawPath);
            foreach (string pair in rawQuery.Split('&'))
            {
                if (pair.Length == 0) continue;
                int eq = pair.IndexOf('=');
                string k = eq >= 0 ? pair.Substring(0, eq) : pair;
                string v = eq >= 0 ? pair.Substring(eq + 1) : "";
                if (k.Length > 0) req.Query[Decode(k)] = Decode(v);
            }

            // 请求头
            for (int i = 1; i < lines.Length; i++)
            {
                string line = lines[i];
                if (line.Length == 0) continue;
                int colon = line.IndexOf(':');
                if (colon <= 0) continue;
                string k = line.Substring(0, colon).Trim();
                string v = line.Substring(colon + 1).Trim();
                req.Headers[k] = v;
            }

            // 正文（按 Content-Length）
            int contentLength = 0;
            if (req.Headers.TryGetValue("Content-Length", out string cl) &&
                int.TryParse(cl, NumberStyles.Integer, CultureInfo.InvariantCulture, out int parsed))
            {
                contentLength = parsed;
            }

            if (contentLength > 0)
            {
                if (contentLength > BodyByteLimit) contentLength = BodyByteLimit;
                var buf = new byte[contentLength];
                int read = 0;
                while (read < contentLength)
                {
                    int n = stream.Read(buf, read, contentLength - read);
                    if (n <= 0) break;
                    read += n;
                }
                req.Body = Encoding.UTF8.GetString(buf, 0, read);
            }

            return req;
        }

        private static string Decode(string s)
        {
            try { return Uri.UnescapeDataString(s.Replace("+", " ")); }
            catch { return s; }
        }

        private static string Summarize(Exception ex) => ex.GetType().Name + ": " + ex.Message;

        // ==================================================================
        //  写回响应
        // ==================================================================

        private void WriteResponse(NetworkStream stream, HttpResponse res)
        {
            try
            {
                byte[] body = Encoding.UTF8.GetBytes(res.IsJson ? res.Json : res.Json);
                var sb = new StringBuilder(256);
                sb.Append("HTTP/1.1 ").Append(res.StatusCode).Append(' ').Append(res.ReasonPhrase).Append("\r\n");
                sb.Append("Content-Type: ").Append(res.IsJson ? "application/json; charset=utf-8" : "text/plain; charset=utf-8").Append("\r\n");
                sb.Append("Content-Length: ").Append(body.Length).Append("\r\n");
                sb.Append("Cache-Control: no-store\r\n");
                sb.Append("Connection: close\r\n");
                sb.Append("\r\n");

                byte[] head = Encoding.ASCII.GetBytes(sb.ToString());
                stream.Write(head, 0, head.Length);
                stream.Write(body, 0, body.Length);
                stream.Flush();
            }
            catch (Exception)
            {
                // 对端已经断开（例如脑侧先超时关连接）——正常现象，安静收场。
            }
        }
    }
}
