using System;
using System.Collections.Generic;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-33】`talk` 原语：找到同地点 NPC → 相邻校验 → 调游戏自己的
    /// `NPC.checkAction(Farmer who, GameLocation l)`，把"这次对话有没有被游戏认领、
    /// 开出了什么 UI"如实带回给脑。
    ///
    /// 【为什么需要它（真机 + IL 证据，见 docs/_release-0.7.46.md §7.3）】
    /// 背包升级不在 SeedShop 货架，机制是 Pierre 的**对话式购买**
    /// （DLL #US 串：`SeedShop_BuyBackpack_Response2000/…_ResponseNo/…_Question24/…_Question36`
    /// + 响应键 `Purchase`；扣钱与 `increaseBackpackSize` 都由游戏本体执行）。
    /// 但 0.7.45 及以前的技能表里**没有 talk**：`interact` 走的是 `GameLocation.checkAction`
    /// （格子动作），柜台/人物都触发不到 NPC 对话（task-32 实测 6 条通道全败）。
    ///
    /// 【红线条（契约 §8.4 冻结）】本技能**只**调 `NPC.checkAction`：
    ///   * 不写 `Money` / `Items` / `MaxItems`，不调 `increaseBackpackSize`；
    ///   * 不合成键盘/鼠标事件（这是调游戏自己的入口，不是伪造输入）；
    ///   * 不伪造对话/选择：选选项留给 `dismiss_modal{answerText|answerIndex}`。
    ///
    /// 【回执（全可选字段，null 省略）】
    ///   `{ok, applied, code, npc, npcTile, distance, available(仅 npc_not_found),
    ///     activeMenu, dialogueIsQuestion, dialogueResponses}`
    ///   `code=="ok" && applied==true` **必须**同时有 `activeMenu` 或 `dialogueIsQuestion`，
    ///   否则分类为 `not_supported`（实现缺陷，fail-closed，不许当成功）。
    ///
    /// 【单 tick】`checkAction` 同步返回，打开对话是它的副作用 ⇒ 不加入
    /// `BridgeHost.IsLongTaskSkill`（与 `interact` 同类的单 tick 技能）。
    /// </summary>
    internal sealed class TalkSkill
    {
        private const string SkillName = "talk";
        private const int MaxAvailableNames = 30;

        private readonly ExecRequest _req;
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;
        private readonly DateTime _startedUtc = DateTime.UtcNow;

        public TalkSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            _req = req;
            _world = world;
            _monitor = monitor;
        }

        public Func<ExecResponse> Step => this.Run;

        private long Elapsed()
        {
            return (long)(DateTime.UtcNow - _startedUtc).TotalMilliseconds;
        }

        private ExecResponse Run()
        {
            Farmer who = Game1.player;
            GameLocation loc = Game1.currentLocation;
            if (who == null || loc == null)
            {
                return this.Fail("no_save",
                    "尚未加载存档，无法执行 talk（找不到 Game1.player / Game1.currentLocation）");
            }

            string want = TalkRules.Normalize(_req?.Args?.Npc);
            int[] wantTile = _req?.Args?.NpcTile;

            List<NPC> characters = new List<NPC>();
            try
            {
                if (loc.characters != null)
                {
                    foreach (NPC npc in loc.characters)
                    {
                        if (npc != null) characters.Add(npc);
                    }
                }
            }
            catch (Exception ex)
            {
                _monitor?.Log($"talk：读取 characters 失败（按空清单处理）：{ex.GetType().Name}: {ex.Message}");
            }

            NPC found = FindNpc(loc, characters, want, wantTile);
            if (found == null)
            {
                var available = new List<string>();
                foreach (NPC npc in characters)
                {
                    string label = TalkRules.Normalize(npc.displayName);
                    if (label.Length == 0) label = TalkRules.Normalize(npc.Name);
                    if (label.Length == 0) continue;
                    if (!available.Contains(label)) available.Add(label);
                    if (available.Count >= MaxAvailableNames) break;
                }
                return new ExecResponse
                {
                    Ok = false,
                    Status = TalkRules.CodeNpcNotFound,
                    Code = TalkRules.CodeNpcNotFound,
                    Skill = SkillName,
                    Schema = Skills.ExecSchema,
                    Npc = want,
                    Available = available.Count > 0 ? available.ToArray() : new string[0],
                    Reason = $"当前地点（{SafeLocationName()}）里没有名字命中 \"{want}\" 的 NPC"
                             + $"（按内部名/显示名大小写不敏感匹配；可选 NPC {available.Count} 个）",
                    ElapsedMs = this.Elapsed(),
                    WorldSeqBefore = _world?.WorldSeq,
                    WorldSeqAfter = _world?.WorldSeq,
                    ReachedLocation = StepMover.CurrentLocationName(),
                };
            }

            int nx = found.TilePoint.X;
            int ny = found.TilePoint.Y;
            int px = who.TilePoint.X;
            int py = who.TilePoint.Y;
            int dx = nx - px;
            int dy = ny - py;
            int distance = TalkRules.ChebyshevDistance(dx, dy);
            bool adjacent = TalkRules.IsAdjacent(dx, dy);
            string npcName = TalkRules.Normalize(found.Name);
            if (npcName.Length == 0) npcName = want;

            if (!adjacent)
            {
                return new ExecResponse
                {
                    Ok = false,
                    Status = TalkRules.CodeNotAdjacent,
                    Code = TalkRules.CodeNotAdjacent,
                    Skill = SkillName,
                    Schema = Skills.ExecSchema,
                    Applied = false,
                    Npc = npcName,
                    NpcTile = new[] { nx, ny },
                    Distance = distance,
                    Reason = $"NPC「{npcName}」在 [{nx},{ny}]，玩家在 [{px},{py}]，"
                             + $"切比雪夫距离 {distance} > 1 ⇒ 不相邻，不能调 checkAction"
                             + "（脑应先 `move_to` 相邻格再 talk；本技能不代走）",
                    ElapsedMs = this.Elapsed(),
                    WorldSeqBefore = _world?.WorldSeq,
                    WorldSeqAfter = _world?.WorldSeq,
                    ReachedLocation = StepMover.CurrentLocationName(),
                };
            }

            bool applied = false;
            string err = null;
            try
            {
                // 【唯一入口】游戏自己的 NPC 交互处理函数（不伪造键鼠、不写钱/背包）。
                applied = found.checkAction(who, loc);
            }
            catch (Exception ex)
            {
                err = ex.GetType().Name + ": " + ex.Message;
            }

            string activeMenu = null;
            try { activeMenu = Game1.activeClickableMenu?.GetType().Name; } catch { }
            bool isQuestion = UiRead.DialogueIsQuestion();
            string[] responses = UiRead.DialogueResponseTexts();

            string code = err == null
                ? TalkRules.DecideCode(true, true, applied, activeMenu, isQuestion)
                : TalkRules.CodeNoAction;
            bool ok = err == null && TalkRules.IsOkCode(code);

            string reason;
            if (err != null)
            {
                reason = $"调用 NPC.checkAction 抛异常：{err}（fail-closed：applied=false、code=no_action）";
            }
            else if (ok)
            {
                reason = $"已对「{npcName}」([{nx},{ny}]) 调游戏自己的 checkAction（返回 {applied}），"
                         + $"并观测到 UI 证据：activeMenu={(activeMenu ?? "null")}、"
                         + $"dialogueIsQuestion={isQuestion}、responses={responses.Length} 项。"
                         + "本技能只负责把对话开出来；选选项请用 dismiss_modal 的 answerText/answerIndex（不代答）。";
            }
            else if (code == TalkRules.CodeNotSupported)
            {
                reason = $"checkAction 返回 applied=true，但既没有 activeMenu 也没有提问对话框"
                         + $"（activeMenu={(activeMenu ?? "null")}，dialogueIsQuestion={isQuestion}）"
                         + "⇒ 回执不可信，按实现缺陷记 not_supported（fail-closed，不当成功）。";
            }
            else
            {
                reason = $"游戏 checkAction 返回 false（applied=false）⇒ 这次没有可执行的对话动作"
                         + $"（activeMenu={(activeMenu ?? "null")}，dialogueIsQuestion={isQuestion}）；"
                         + "code=no_action。可用 observe 复核 NPC/UI 状态后再决定。";
            }

            return new ExecResponse
            {
                Ok = ok,
                Status = code,
                Code = code,
                Skill = SkillName,
                Schema = Skills.ExecSchema,
                Applied = applied,
                Npc = npcName,
                NpcTile = new[] { nx, ny },
                Distance = distance,
                ActiveMenu = activeMenu,
                ActiveMenuText = UiRead.ActiveMenuText(),
                DialogueIsQuestion = isQuestion,
                DialogueResponses = responses,
                Reason = reason,
                ElapsedMs = this.Elapsed(),
                WorldSeqBefore = _world?.WorldSeq,
                WorldSeqAfter = _world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };
        }

        private static NPC FindNpc(GameLocation loc, List<NPC> characters, string want, int[] wantTile)
        {
            if (want.Length == 0) return null;

            // ① 游戏自己的按名查找（内部名精确；拿不到就走 ② 的全量匹配）。
            try
            {
                NPC byName = loc.getCharacterFromName(want);
                if (byName != null && TileMatches(byName, wantTile)) return byName;
                if (byName != null && wantTile == null) return byName;
            }
            catch { }

            // ② 全量匹配：内部名或显示名任一相等；给了 npcTile 时优先同格的那一个。
            NPC fallback = null;
            foreach (NPC npc in characters)
            {
                if (!TalkRules.NameMatches(want, npc.Name, npc.displayName)) continue;
                if (wantTile != null && TileMatches(npc, wantTile)) return npc;
                if (fallback == null) fallback = npc;
            }
            return fallback;
        }

        private static bool TileMatches(NPC npc, int[] wantTile)
        {
            if (wantTile == null || wantTile.Length < 2) return false;
            return npc.TilePoint.X == wantTile[0] && npc.TilePoint.Y == wantTile[1];
        }

        private static string SafeLocationName()
        {
            try { return Game1.currentLocation?.Name ?? "?"; } catch { return "?"; }
        }

        private ExecResponse Fail(string code, string reason)
        {
            return new ExecResponse
            {
                Ok = false,
                Status = code,
                Code = code,
                Skill = SkillName,
                Schema = Skills.ExecSchema,
                Reason = reason,
                ElapsedMs = this.Elapsed(),
                WorldSeqBefore = _world?.WorldSeq,
                WorldSeqAfter = _world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };
        }
    }
}
