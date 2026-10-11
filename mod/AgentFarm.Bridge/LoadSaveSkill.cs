using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Xna.Framework;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【里程碑 C】<c>load_save</c>：把游戏从**标题界面**带进一个存档。
    ///
    /// 请求：<c>{"skill":"load_save","args":{"save":"Wahaha_450799035","force":false},"timeout_ms":60000}</c>
    /// （<c>args.save</c> 可省 —— 省略时自动挑**最近写过**的存档。）
    ///
    /// ==================================================================
    ///  一、为什么必须有这个技能（它不是"方便"，是自主性的前提）
    /// ==================================================================
    /// 1. **换 Mod 必须重启游戏**（SMAPI 一旦加载 dll 就不再读盘），而重启后游戏停在标题界面。
    ///    标题界面上唯一的正常入口是"点 Continue" —— 那属于**伪造输入**，被本项目硬纪律①禁止。
    /// 2. 无人值守长跑（P3 要求连续 3 个游戏日 0 人工介入）必须能**自己从崩溃/重启里爬起来**；
    ///    停在标题界面而没人点鼠标，等于整条流水线死掉。
    ///
    /// ==================================================================
    ///  二、为什么这是"合法操作"而不是作弊（D4 自检）
    /// ==================================================================
    /// 我们调用的是**游戏自己的读档入口** <c>SaveGame.Load(存档名)</c>（IL 实证，见
    /// `docs/_il-savegame-load.md`）：它只是 `Game1.gameMode = 6`（加载态）+
    /// 把 <c>Game1.currentLoader = getLoadEnumerator(存档名)</c>，余下的进度推进**全由游戏自己的
    /// 主循环完成**（玩家点 Continue 走的是同一条路）。我们**没有**写任何世界状态、**没有**改角色
    /// 坐标/金钱/时间、**没有**伪造键鼠事件。读进来的存档就是磁盘上那个存档，原样。
    ///
    /// ==================================================================
    ///  三、判据（条目 013 的教训：不许"看起来在加载"就算成功）
    /// ==================================================================
    /// 唯一成功判据是**世界真的可读了**：<c>Context.IsWorldReady</c> 为真
    /// **且** <c>Game1.player != null</c> **且** <c>Game1.currentLocation != null</c>。
    /// 只要读档还没完成就每 tick 返回 null 继续等；等到超时如实报 <c>timeout</c>，
    /// 并把"已经发起了 Load / gameMode 是多少 / hasLoadedGame 是多少"写进 reason —— 不含糊。
    ///
    /// 【为什么先拒绝、要 force 才读】正在存档里跑的时候读档会**直接丢掉当前这一天的进度**
    /// （游戏只在睡觉时落盘）。这是破坏性副作用，必须由调用方显式声明（与 move_to 的 allow_bed 同一条纪律）。
    /// </summary>
    internal sealed class LoadSaveSkill
    {
        /// <summary>默认时间预算：读一张存档要几秒到几十秒，比普通技能宽得多。</summary>
        private const int DefaultTimeoutMs = 60000;

        /// <summary>上限：再长也不该超过 3 分钟，超过说明真出事了，如实报超时。</summary>
        private const int MaxTimeoutMs = 180000;

        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly int _timeoutMs;
        private readonly string _requestedSave;
        private readonly bool _force;

        private bool _started;
        private DateTime _startedAtUtc;
        private long _seqBefore;

        /// <summary>真正被发起读档的那个存档文件夹名。</summary>
        private string _saveFolder;

        public LoadSaveSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._world = world;
            this._monitor = monitor;
            this._requestedSave = req?.Args?.Save;
            this._force = req?.Args?.Force ?? false;
            this._timeoutMs = ClampBudget(req?.TimeoutMs);
        }

        /// <summary>
        /// 读档的时间预算（刻意**不用** <see cref="Skills.ClampTimeout"/>：那个上限 30 秒是给
        /// "走一格"定的，读档合法地会超过它）。
        /// 这里是**唯一**的口径来源：技能自己与 <see cref="BridgeHost"/> 的主线程等待都调它，
        /// 免得两边各算一个数、把 60 秒的读档在 30 秒处掐死。
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
                Ok = false,
                Status = status,
                Skill = "load_save",
                Reason = reason,
                Schema = Skills.ExecSchema,
                ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world?.WorldSeq,
                Save = this._saveFolder,
            };

        private ExecResponse Ok(long elapsedMs)
        {
            string loc = null;
            int[] tile = null;
            try
            {
                loc = Game1.currentLocation?.Name;
                tile = new[] { Game1.player.TilePoint.X, Game1.player.TilePoint.Y };
            }
            catch { }

            return new ExecResponse
            {
                Ok = true,
                Status = "ok",
                Skill = "load_save",
                Reason = $"已进入存档“{this._saveFolder}”（当前地点 {loc ?? "（读不到）"}"
                    + (tile != null ? $" ({tile[0]},{tile[1]})" : "") + "）",
                Schema = Skills.ExecSchema,
                ElapsedMs = elapsedMs,
                WorldSeqBefore = this._seqBefore,
                WorldSeqAfter = this._world?.WorldSeq,
                Save = this._saveFolder,
                ReachedLocation = loc,
                Tile = tile,
            };
        }

        /// <summary>每次被主线程调用：返回 null = 还在加载，返回非 null = 终态。</summary>
        public object Step()
        {
            try
            {
                if (!this._started) return this.Begin();

                // ---- 唯一成功判据：世界真的可读了 ----
                if (IsWorldUsable())
                    return this.Ok(this.Elapsed());

                if (this.Elapsed() >= this._timeoutMs)
                {
                    string mode = "?";
                    string loaded = "?";
                    try { mode = Game1.gameMode.ToString(); } catch { }
                    try { loaded = Game1.hasLoadedGame.ToString(); } catch { }

                    return this.Fail("timeout",
                        $"读档超时（{this._timeoutMs}ms）：已经发起 SaveGame.Load(\"{this._saveFolder}\")，"
                        + $"但世界仍不可读（gameMode={mode}、hasLoadedGame={loaded}、"
                        + $"player={(Game1.player == null ? "null" : "有")}、"
                        + $"location={(Game1.currentLocation == null ? "null" : "有")}）。"
                        + "注意 SaveGame.Load 对'文件不存在/损坏'**不会抛异常**，它会把错误状态交给加载界面"
                        + "（画面上会显示 Save could not be loaded）—— 所以这里超时基本等于"
                        + "『存档文件读不出来』或『加载卡在某个模态上』；请人工看一眼游戏画面。",
                        this.Elapsed());
                }

                return null;   // 继续等游戏自己把加载推进完
            }
            catch (Exception ex)
            {
                return this.Fail("error", "load_save 执行异常：" + ex.GetType().Name + ": " + ex.Message,
                    this._started ? this.Elapsed() : 0);
            }
        }

        private static bool IsWorldUsable()
        {
            try
            {
                return Context.IsWorldReady && Game1.player != null && Game1.currentLocation != null;
            }
            catch { return false; }
        }

        /// <summary>前置校验 + 选存档 + 真正发起读档。返回 null 表示已发起、需要后续 tick 推进。</summary>
        private object Begin()
        {
            this._started = true;
            this._startedAtUtc = DateTime.UtcNow;
            try { this._seqBefore = this._world?.WorldSeq ?? 0; } catch { }

            // ---- 前置校验 1：已经在存档里？默认拒绝（读档会丢掉当天进度）----
            if (IsWorldUsable() && !this._force)
            {
                string where = "?";
                try { where = $"{Game1.currentLocation?.Name} ({Game1.player.TilePoint.X},{Game1.player.TilePoint.Y})"; }
                catch { }

                return this.Fail("precondition_failed",
                    $"当前**已经在一个存档里**（{where}），拒绝读档：读档会直接丢掉当前这一天的进度"
                    + "（游戏只在睡觉时落盘）。若确实要丢掉它重新读档，请显式传 args.force=true。",
                    0);
            }

            // ---- 前置校验 2：挑存档 ----
            string savesRoot = null;
            try { savesRoot = Constants.SavesPath; } catch { }

            if (string.IsNullOrEmpty(savesRoot) || !Directory.Exists(savesRoot))
            {
                return this.Fail("precondition_failed",
                    "读不到存档目录（Constants.SavesPath 为空或不存在），无法读档", 0);
            }

            List<string> available = ListSaves(savesRoot);

            if (!string.IsNullOrEmpty(this._requestedSave))
            {
                // 若指定了存档名：先按游戏自己的判据确认它真的存在（`Saves\<名字>\<名字>`）。
                string wanted = this._requestedSave.Trim();
                string hit = null;
                foreach (string name in available)
                {
                    if (string.Equals(name, wanted, StringComparison.OrdinalIgnoreCase)) { hit = name; break; }
                }

                if (hit == null)
                {
                    return this.Fail("precondition_failed",
                        $"存档“{this._requestedSave}”不存在（{savesRoot} 下现有："
                        + (available.Count > 0 ? string.Join("、", available) : "（一个都没有）")
                        + $"。一个存档文件夹有效的判据是 Saves\\<名字>\\<名字> 这个文件存在 —— 与游戏自己的 TryReadSaveFile 一致）", 0);
                }

                this._saveFolder = hit;
            }
            else
            {
                this._saveFolder = NewestSave(savesRoot, available);
                if (this._saveFolder == null)
                {
                    return this.Fail("precondition_failed",
                        $"存档目录 {savesRoot} 下没有任何可用存档"
                        + "（判据与游戏一致：目录下要有 Saves\\<名字>\\<名字> 这个存档数据文件）", 0);
                }
            }

            // ---- 真正发起读档 ----
            // 先收起标题菜单：游戏自己的 LoadGameMenu 点下去之后也是立刻切到加载态，
            // 留着旧菜单会让它继续 tick 一帧（可能把 gameMode 改回去）。
            try { Game1.activeClickableMenu = null; } catch { }

            try
            {
                SaveGame.Load(this._saveFolder);
            }
            catch (Exception ex)
            {
                return this.Fail("error",
                    $"调用 SaveGame.Load(\"{this._saveFolder}\") 抛异常：" + ex.GetType().Name + ": " + ex.Message, 0);
            }

            this._monitor?.Log($"load_save：已发起读档 \"{this._saveFolder}\"", LogLevel.Info);
            return null;   // 交给后续 tick 等世界变可读
        }

        /// <summary>
        /// 列出存档目录下**看起来是有效存档**的文件夹。
        ///
        /// 【判据来自游戏自己】IL 实证（`docs/_il-savegame-load.md`）：`SaveGame.TryReadSaveFile(file, suffix, …)`
        /// 开头就是 `Path.Combine(GetSavesFolder(), file, file + suffix)` 再 `File.Exists(...)`。
        /// 也就是说：一个存档文件夹 &lt;名字&gt; 有效的判据是
        /// **`Saves\&lt;名字&gt;\&lt;名字&gt;` 这个文件存在**（另有 `&lt;名字&gt;_old` 兜底、
        /// `SaveGameInfo` 给读档菜单看）。这里就用同一条判据，而不是自己发明。
        /// </summary>
        private static List<string> ListSaves(string savesRoot)
        {
            var list = new List<string>();
            try
            {
                foreach (string dir in Directory.GetDirectories(savesRoot))
                {
                    string name = Path.GetFileName(dir);
                    if (string.IsNullOrEmpty(name)) continue;
                    if (name.StartsWith("_", StringComparison.Ordinal)) continue;   // _original 之类的备份
                    if (!File.Exists(Path.Combine(dir, name))) continue;            // 游戏自己的存在性判据
                    list.Add(name);
                }
            }
            catch (Exception ex)
            {
                throw new IOException("枚举存档目录失败：" + ex.Message);
            }
            return list;
        }

        /// <summary>
        /// 最近写过（优先看 <c>SaveGameInfo</c>，没有就看存档数据文件本身）的那个存档。
        /// </summary>
        private static string NewestSave(string savesRoot, List<string> available)
        {
            string best = null;
            DateTime bestAt = DateTime.MinValue;

            foreach (string name in available)
            {
                DateTime at;
                try
                {
                    string info = Path.Combine(savesRoot, name, "SaveGameInfo");
                    at = File.Exists(info)
                        ? File.GetLastWriteTimeUtc(info)
                        : File.GetLastWriteTimeUtc(Path.Combine(savesRoot, name, name));
                }
                catch { continue; }

                if (best == null || at > bestAt) { best = name; bestAt = at; }
            }

            return best;
        }
    }
}
