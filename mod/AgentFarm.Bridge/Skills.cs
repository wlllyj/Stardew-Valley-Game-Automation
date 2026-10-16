using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Objects;
using StardewValley.Pathfinding;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 技能层（架构 §5.3）。目前实现五个：
    ///   * <c>noop</c>             —— 立刻返回 ok，用于验证通信链路，完全不碰游戏；
    ///   * <c>move_to</c>          —— 用游戏自带 <see cref="PathFindController"/> 把玩家走到 args.tile（同一地点内）；
    ///   * <c>move_to_location</c> —— 【里程碑 B】跨地点移动：按**游戏真值的 warp 图**做 BFS 求路由，
    ///                                每一跳都"走到 warp 源格 → 等游戏真的把玩家传送过去"，
    ///                                成功判据是 <c>Game1.currentLocation.Name</c> 真的变了（见 <see cref="MoveToLocationSkill"/>）；
    ///   * <c>load_save</c>        —— 【里程碑 C】从标题界面读档（换 Mod 必须重启游戏，
    ///                                重启后没人点 Continue，而"点 Continue"属于伪造输入）。
    ///                                见 <see cref="LoadSaveSkill"/>；
    ///   * <c>dismiss_modal</c>    —— 关掉菜单/对话并把世界恢复回来。
    ///
    /// 【跨 tick 推进】move_to / move_to_location / load_save 的 Handler 在“还没走完”时返回 null，
    /// 由 MainThreadDispatcher 下个 tick 继续调用；返回非 null 即为终态。
    /// 这样既不卡帧，又不会把玩家丢在控制器里。
    ///
    /// 【里程碑 B 抽取】原先写在 <see cref="MoveToSkill"/> 里的移动状态机已经抽到
    /// <see cref="StepMover"/>，让 move_to 与 move_to_location 共用**同一套**移动/超时/卡死/模态判据。
    /// 抽取的硬约束是「move_to 的对线行为逐字不变」，因此所有失败文案都带技能名前缀，
    /// move_to 传 "move_to" 时拼出来的句子与抽取前逐字节相同。
    /// </summary>
    internal static class Skills
    {
        public const int TimeoutMinMs = 500;
        public const int TimeoutMaxMs = 30000;
        public const int TimeoutDefaultMs = 8000;

        /// <summary>
        /// exec 响应协议版本。
        ///
        /// v1 → v2（修复迭代 3）：新增 `worldResumed`（dismiss_modal 专用）。
        /// 依据 docs/03-桥接协议.md §8「任何一侧改字段必须 +1 版本号」，
        /// 并与 Python 侧同步（否则就是旧方案缺陷 D5“C# 写 /1 而 Python 写 /2”的翻版）。
        ///
        /// ⚠️ 里程碑 B 给 ExecResponse 加了**可选新字段**（path / hops / reachedLocation），
        ///    按协议「null 字段序列化时省略」的约定，老客户端读到的响应形状不变，
        ///    因此这里**不动** schema 版本号（版本号统一由主代理决定）。
        /// </summary>
        public const string ExecSchema = "agentfarm-exec/2";

        /// <summary>
        /// based_on_seq 的“陈旧”阈值（架构 §5.3 时效拒绝）。
        ///
        /// 口径说明：worldSeq 会因为**玩家每跨一格**而 +1（指纹含玩家坐标），
        /// 所以“正常走一段路”本身就会让 seq 涨几十。阈值取得太小会误杀正常请求。
        /// 取 300：约等于 300 格位移或 50 分钟游戏内时间的变化量，
        /// 超出这个量级说明“脑”依据的快照已经明显过期，拒绝执行并要求重新观测。
        /// </summary>
        public const int StaleSeqThreshold = 300;

        public static int ClampTimeout(int? timeoutMs)
        {
            int v = timeoutMs ?? TimeoutDefaultMs;
            if (v < TimeoutMinMs) v = TimeoutMinMs;
            if (v > TimeoutMaxMs) v = TimeoutMaxMs;
            return v;
        }

        /// <summary>
        /// 按技能取时间预算。<c>load_save</c> 走它自己的口径（读盘合法地慢，上限也更大），
        /// 其余技能一律 <see cref="ClampTimeout"/>。
        ///
        /// 【为什么必须统一在这里】技能自己的超时判据与 <see cref="BridgeHost"/> 里
        /// "主线程等待多久"是**两个**数；各写一份就会出现"技能以为有 60 秒、
        /// 调度器 30 秒就把 null 交回网络线程"的半途而废（条目 013 那类）。
        /// </summary>
        public static int ClampTimeoutFor(string skill, int? timeoutMs)
        {
            switch (skill)
            {
                // 读盘合法地慢（上限 180 秒）
                case "load_save":
                    return LoadSaveSkill.ClampBudget(timeoutMs);
                // 跨日 = 淡黑 + 存档 + 换天，合法地比"走一格"慢得多（上限 300 秒）
                case "sleep":
                    return SleepSkill.ClampBudget(timeoutMs);
                // 长距离多跳（走几十步再进建筑）：30s 装不下，task-43 放宽到 60s
                case "move_to_location":
                    return MoveToLocationSkill.ClampBudget(timeoutMs);
                // 【task-129】出货日跨日：出货菜单 → 日切保存 → 换天，合法地要十几秒，
                // 默认 8s 会把"游戏正在存档"判成超时（上限 120s）
                case "dismiss_modal":
                    return ShippingMenuDismissSkill.ClampBudget(timeoutMs);
                default:
                    return ClampTimeout(timeoutMs);
            }
        }

        /// <summary>
        /// 构造一个技能执行器。返回的委托每次被主线程调用：
        /// 返回非 null = 终态（交付网络线程）；返回 null = 还没走完。
        /// </summary>
        public static Func<object> Create(string skill, ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            switch (skill)
            {
                case "noop":
                    return () => new ExecResponse
                    {
                        Ok = true,
                        Status = "ok",
                        Skill = "noop",
                        Reason = "",
                        Schema = ExecSchema,
                        WorldSeqBefore = world.WorldSeq,
                        WorldSeqAfter = world.WorldSeq,
                        ElapsedMs = 0,
                    };

                case "move_to":
                    return new MoveToSkill(req, world, monitor).Step;

                // 【P3 步骤③】用工具对某一格动手（砍树枝/敲石头/割草/锄地/浇水）。
                // 跨 tick 长任务：挥动 → 等 player.UsingTool 落回 false → 看目标格清没清 → 没清再挥。
                // ⇒ BridgeHost 的 isLongTask 判据必须包含它（见 BridgeHost.IsLongTaskSkill）。
                case "use_tool":
                    return new UseToolSkill(req, world, monitor).Step;

                // 【P3 步骤④】选物品（短任务）与播种（跨 tick 长任务，BridgeHost.IsLongTaskSkill 也要加）
                case "select_item":
                    return new SelectItemSkill(req, world, monitor).Step;

                case "plant":
                    return new PlantSkill(req, world, monitor).Step;

                // 【里程碑 B】跨地点移动。与 move_to 一样是跨 tick 长任务（用 StepMover 推进每一跳），
                // 所以 BridgeHost 里的 isLongTask 判据也必须包含它（见 BridgeHost.ServeExec）。
                case "move_to_location":
                    return new MoveToLocationSkill(req, world, monitor).Step;

                // 【里程碑 C】从标题界面读档（自主性前提：换 Mod 要重启，重启后没人点 Continue）。
                // 同样是跨 tick 长任务（每 tick 等世界变可读），所以 BridgeHost 的 isLongTask 判据必须包含它。
                case "load_save":
                    return new LoadSaveSkill(req, world, monitor).Step;

                // 【里程碑 C-2】让游戏**自己退出**。
                // 无人值守闭环的最后一块：换 Mod dll 必须重启游戏，而"关游戏"以前只能靠人
                // （或用 Stop-Process 强杀）。这里用游戏自己的退出标志 `Game1.quit`
                // （api-probe 编译期实证：可写 bool），等价于玩家点了退出，不伪造键鼠、不写世界状态。
                //
                // ⚠️ 回执可能**送不到**：置位后游戏会在随后的帧里退出，HTTP 线程可能来不及把响应写完。
                //    调用方（tools\deploy-mod.py）必须把"连接被重置"当成"大概正在退出"，
                //    再以**进程是否真的消失**为准，而不是以回执为准。
                case "quit_game":
                    return () =>
                    {
                        bool ok = false;
                        string why = null;
                        try { Game1.quit = true; ok = true; }
                        catch (Exception ex) { why = ex.GetType().Name + ": " + ex.Message; }

                        return new ExecResponse
                        {
                            Ok = ok,
                            Status = ok ? "ok" : "error",
                            Skill = "quit_game",
                            Schema = ExecSchema,
                            Reason = ok
                                ? "已置 Game1.quit=true：游戏会在随后几帧内自行退出（本回执可能因此收不到，以进程是否消失为准）"
                                : "置 Game1.quit=true 失败：" + why,
                            ElapsedMs = 0,
                            WorldSeqBefore = world.WorldSeq,
                            WorldSeqAfter = world.WorldSeq,
                        };
                    };

                // 【里程碑 C-3】`interact`：**用一下面前那一格**（调游戏自己的动作入口 `checkAction`）。
                //
                // 【为什么必须走"动作"而不是"碰撞"（2026-10-11 真机证据）】进农舍进不去，查到：
                //   * `Farm` 与 `FarmHouse` 的 `location.doors` **都是空的** ⇒ `isCollidingWithDoors` 无从触发；
                //   * `GameLocation.checkAction` 的 IL 里遍历 `this.buildings`，调
                //     `getPointForHumanDoor()` / `getWarpFromDoor(...)` / `Building.doAction(Vector2, Farmer)`
                //     ⇒ **进入建筑是"动作"路径**；
                //   * 真机 `door_push`：朝门推 60 帧，玩家像素只从 (4096,976) 到 (4096,963)（位移 0,-13，被墙挡住），
                //     矩形四角始终进不了门格 (64,14) ⇒ 碰撞式触发根本没有机会发生。
                //
                // 【纪律】与 `dismiss_modal` 用 `answerDialogue`、不按确认键**同一条**：
                // 调游戏自己的处理函数，**不合成键鼠事件**。所以这不是"伪造输入"。
                // 目标格：`args.tile` 优先；省略时用"玩家当前面朝的那一格"（玩家走到门口朝上时就是门格）。
                //
                // 【NIT-2（task-180 记录在案的局限）】`acted` 的四路证据里，格子级那两路都建立在
                // `TileSig`/`ready` 上；而 **门/入口类传送**（`checkAction` → `warp`/`doAction`）
                // 只把玩家挪走，目标格本身的签名与 `ready` 都可能不变 ⇒ 这类动作可能落
                // `acted=false` / `status="no_action"`（下面 reason 里"以 observe 到的地点为准"这句
                // 因此对门格是不成立的）。**今天无害**：`interact` 目前唯一调用点是脑侧 `harvest()`，
                // 它只对作物格用；将来若要拿 `interact` 开门/进建筑，必须先给门格补一路证据
                // （例如玩家 tile/location 变化），否则会被误判成"没动手"。
                case "interact":
                    return () =>
                    {
                        Farmer who = Game1.player;
                        if (who == null || Game1.currentLocation == null)
                        {
                            return new ExecResponse
                            {
                                Ok = false, Status = "no_save", Skill = "interact",
                                Reason = "尚未加载存档，无法执行 interact",
                                Schema = ExecSchema,
                            };
                        }

                        int tx, ty;
                        int[] want = req?.Args?.Tile;
                        if (want != null && want.Length >= 2)
                        {
                            tx = want[0]; ty = want[1];
                        }
                        else
                        {
                            tx = who.TilePoint.X; ty = who.TilePoint.Y;
                            switch (who.FacingDirection)
                            {
                                case 0: ty--; break;      // 上
                                case 1: tx++; break;      // 右
                                case 2: ty++; break;      // 下
                                default: tx--; break;     // 左
                            }
                        }

                        bool handled = false;
                        string err = null;
                        // 【task-176 必修 ③ + task-182 必修 1/2】`acted` **不许自述成功**：
                        // `checkAction` 的返回值只是"这一格被认领了"，真没真做事必须以**跨观测证据**为准。
                        //   * task-173 事故：回执 `{acted:true, ok:true}` 但世界逐字节没变；
                        //   * task-177 反向事故：再生作物**真的收成了**，可格子内那 6 个字段
                        //     （watered/crop/phase/grown/dead/...）一项都不变 ⇒ 只比 TileSig 会把
                        //     **成功**报成 `no_action`。
                        // 现在按"格子级优先、全局面垫底"取证据：
                        //   ① `TileSig` 变（老判据，保留）；
                        //   ② 目标格 `ready` true→false 或 `readySource` 变化（再生作物的关键证据）；
                        //   ③ 整场 `readyCrops` 下降；
                        //   ④ 背包逐 qid 栈数增加（**弱证据**：同一 tick 别的系统也可能改背包 ⇒ 垫底）。
                        string sigBefore = TileSig(tx, ty);
                        (bool? readyBefore, string readySourceBefore) = TileReady(tx, ty);
                        int readyCropsBefore = ReadyCropCount();
                        Dictionary<string, int> invBefore = InventoryStacks();
                        try
                        {
                            handled = Game1.currentLocation.checkAction(
                                new xTile.Dimensions.Location(tx, ty), Game1.viewport, who);
                        }
                        catch (Exception ex) { err = ex.GetType().Name + ": " + ex.Message; }
                        string sigAfter = TileSig(tx, ty);
                        (bool? readyAfter, string readySourceAfter) = TileReady(tx, ty);
                        int readyCropsAfter = ReadyCropCount();
                        Dictionary<string, int> invAfter = InventoryStacks();

                        bool tileChanged = sigBefore != null && sigAfter != null
                                           && !string.Equals(sigBefore, sigAfter, StringComparison.Ordinal);
                        bool readyFlipped = readyBefore == true && readyAfter != true;
                        bool readySourceChanged = readySourceBefore != null && readySourceAfter != null
                                                  && !string.Equals(readySourceBefore, readySourceAfter, StringComparison.Ordinal);
                        bool readyDropped = readyCropsBefore >= 0 && readyCropsAfter >= 0
                                            && readyCropsAfter < readyCropsBefore;
                        bool inventoryGrew = InventoryGrew(invBefore, invAfter);

                        string evidence = null;
                        if (tileChanged) evidence = "tile";
                        else if (readyFlipped || readySourceChanged) evidence = "ready";
                        else if (readyDropped) evidence = "readyCrops";
                        else if (inventoryGrew) evidence = "inventory";

                        // 拿不准（快照失败）⇒ 不算证据；全都不命中 ⇒ false + no_action
                        // （宁可让人来核，也不许自述成功）。
                        bool acted = err == null && evidence != null;
                        string probeText =
                            $"tile[{sigBefore ?? "快照失败"} → {sigAfter ?? "快照失败"}]；"
                            + $"ready[{readyBefore?.ToString() ?? "?"} → {readyAfter?.ToString() ?? "?"}"
                            + $"，readySource[{readySourceBefore ?? "?"} → {readySourceAfter ?? "?"}]；"
                            + $"readyCrops[{readyCropsBefore} → {readyCropsAfter}]；"
                            + $"inventoryGrew={inventoryGrew}";

                        return new ExecResponse
                        {
                            Ok = err == null && acted,
                            Status = err == null ? (acted ? "ok" : "no_action") : "error",
                            Skill = "interact",
                            Schema = ExecSchema,
                            Acted = acted,
                            ActedEvidence = evidence,
                            Reason = err == null
                                ? (acted
                                    ? $"已在 ({tx},{ty}) 调游戏自己的 checkAction，且**观测到世界变了**"
                                      + $"（证据来源 `{evidence}`；checkAction 返回 {handled}）。{probeText}。"
                                      + "若这一格是门/建筑入口，传送由游戏自己发起（有淡出期，**以 observe 到的地点为准**）"
                                    : $"({tx},{ty}) 这一格**没有任何跨观测证据**"
                                      + $"（checkAction 返回 {handled}）。{probeText}。"
                                      + "`acted=false`、`status=\"no_action\"`、回执如实 failed；"
                                      + "请用 observe 复核这一格的真实状态（镰刀类作物必须走 use_tool，不是 interact）。")
                                : "checkAction 抛异常：" + err,
                            ElapsedMs = 0,
                            WorldSeqBefore = world.WorldSeq,
                            WorldSeqAfter = world.WorldSeq,
                            ReachedLocation = StepMover.CurrentLocationName(),
                        };
                    };

                case "dismiss_modal":
                    // 【task-129】出货菜单 / 存档菜单**绝不能**单 tick `exitThisMenu()`：
                    // 出货日的日切保存入口在 `ShippingMenu` 自己内部（点 OK 才建 SaveGameMenu），
                    // 硬关会让 `outro` 永假 ⇒ 日推进、盘不落（run9 四天 0 次 save，整跑作废）。
                    // 这两类改走跨 tick 的 wait-only 技能（反射 okClicked() / 点 okButton，然后只等）；
                    // 其它模态仍走原来的单 tick `ModalDismiss.Dismiss()`。
                    // ⇒ 同时必须把 "dismiss_modal" 加进 BridgeHost.IsLongTaskSkill。
                    if (ShippingMenuDismissSkill.Applies())
                        return new ShippingMenuDismissSkill(req, world, monitor).Step;

                    // 单 tick 完成的短任务：不返回 null，所以不会被当成跨 tick 长任务。
                    return () =>
                    {
                        ModalDismissResult r = ModalDismiss.Dismiss();
                        return new ExecResponse
                        {
                            // 注意：Ok 与 Status 都由 ModalDismiss 定；世界没恢复时它是
                            // ok=false + status="world_stuck"，绝不当成普通成功。
                            Ok = r.Ok,
                            Status = r.Status,
                            Skill = "dismiss_modal",
                            Reason = r.Reason,
                            Schema = ExecSchema,
                            WorldResumed = r.WorldResumed,
                            ElapsedMs = 0,
                        };
                    };

                // 【P3 步骤⑤/⑥】`sleep`：**睡到第二天早上** —— 无人值守连续多日的唯一正路。
                //
                // 【为什么"跨日"必须走睡觉，而不能用 quit_game + load_save】
                // 游戏**只在睡觉时落盘**（`SaveGame` 的调用方清单里没有别的入口）。
                // quit_game + load_save 读回来还是同一天的早上，日期/体力/作物/天气都不会前进，
                // 那是**假跨日**（详见 SleepSkill 类注释里的 IL 证据链）。
                //
                // 跨 tick 长任务：这一 tick 把"睡觉"发起出去（应答游戏自己的提问 / 走
                // `answerDialogueAction("Sleep_Yes")`），随后每 tick 看 `Game1.Date.TotalDays`
                // 有没有变大；变大才算成功。⇒ BridgeHost.IsLongTaskSkill 必须包含 "sleep"。
                case "sleep":
                    return new SleepSkill(req, world, monitor).Step;

                // 【P3 步骤⑤/⑥】`buy`：**花钱买种子**（"还有钱就该补货，而不是一有空就睡" —— 用户 m00707）。
                //
                // 【纪律】钱与物品数量只能由**游戏自己**动：开店 → 反射调游戏自己的
                // `ShopMenu.tryToPurchaseItem(item, null, count, 0, 0)`（它内部含 readOnly 检查、
                // 钱够不够的裁决、`chargePlayer` 扣钱、库存记账、`onPurchase` 回调）→ 用游戏自己在关店
                // 收尾时用的那**同一句** `Game1.player.addItemToInventoryBool(held, false)` 收货。
                // Mod **绝不**自己写 `Money -= price`（那是 v0.7.17"种子不扣"事故的同类）。
                // 详见 BuySkill 类注释里的 IL 证据链（logs/il-shop-buy-u8.txt）。
                //
                // ⚠️ 游戏那个函数的返回值**不是成败**（"库存归零"时它返回 true，"正常卖出"却返回 false），
                // 所以判据一律是**观测差分**（钱少了多少 + 背包多了几个）。
                // 跨 tick：菜单还没挂上时会 return null 等 → BridgeHost.IsLongTaskSkill 必须包含 "buy"。
                case "buy":
                    return new BuySkill(req, world, monitor).Step;

                // 【task-42】`sell`：把**白名单内**的一格背包物品放进**出货箱**（用户 m08335：一分钱也没挣到）。
                //
                // 【纪律】与 buy 同一条：**绝不自己写 `Money +=`**。只调游戏自己的
                // `Farm.shipItem(item, Game1.player)`；钱由**下一次 NewDay** 结算
                // （`Game1._newDayAfterFade` 里 `player.Money = player.Money + total`）。
                // 所以判据不是钱变了（当天根本不变），而是"那件东西真的离开背包了"。
                // 详细 IL 证据链与三个坑（引用相等 / 整叠出货 / Halt 副作用）见 ShipSkill 类注释，
                // 以及 docs/_il-sell-path.md。
                //
                // 单 tick 同步技能：不加入 BridgeHost.IsLongTaskSkill。
                case "sell":
                    return new ShipSkill(req, world, monitor).Step;

                default:
                    // 未实现的技能：合法请求但还没有实现（区别于 unknown_skill）。
                    return () => new ExecResponse
                    {
                        Ok = false,
                        Status = "not_implemented",
                        Skill = skill,
                        Reason = $"技能“{skill}”尚未实现（已实现：noop、move_to、move_to_location、"
                               + "dismiss_modal、load_save、quit_game、interact、use_tool、select_item、plant、sleep、buy、sell）",
                    };
            }
        }

        /// <summary>
        /// 【task-176 必修 ③】目标格的**可观测签名**（`interact` 前后各取一次做对比）。
        ///
        /// 为什么要它：`checkAction` 的返回值只说明"这一格被认领了"，不能证明游戏真做了事。
        /// task-173 真机事故 = 回执 `acted:true` 但 `worldSeq` 不动、作物还在、背包 +0、存档未变。
        /// 所以 `acted` 必须以"本调用内这一格真的变了"为准。
        ///
        /// 签名覆盖：地面物体（`QualifiedItemId`+`Stack`）、地形特征类型、`HoeDirt` 的浇水态与
        /// 作物（`indexOfHarvest`/`currentPhase`/`fullyGrown`/`dead`）、`Action` 属性、门。
        /// **取不到 ⇒ null**（调用方据此判"拿不准"，不许当"没变"以外的任何结论）。
        /// </summary>
        private static string TileSig(int x, int y)
        {
            try
            {
                GameLocation loc = Game1.currentLocation;
                if (loc == null) return null;
                var v = new Vector2(x, y);
                var sb = new System.Text.StringBuilder();

                StardewValley.Object o;
                if (loc.objects != null && loc.objects.TryGetValue(v, out o) && o != null)
                    sb.Append("obj:").Append(o.QualifiedItemId ?? o.ItemId).Append('x').Append(o.Stack);

                StardewValley.TerrainFeatures.TerrainFeature tf;
                if (loc.terrainFeatures != null && loc.terrainFeatures.TryGetValue(v, out tf) && tf != null)
                {
                    sb.Append("|tf:").Append(tf.GetType().Name);
                    var hd = tf as StardewValley.TerrainFeatures.HoeDirt;
                    if (hd != null)
                    {
                        try { sb.Append(":watered=").Append(hd.state != null && hd.state.Value == 1); } catch { }
                        var c = hd.crop;
                        if (c != null)
                        {
                            try { sb.Append(":crop=").Append(c.indexOfHarvest != null ? c.indexOfHarvest.Value : -1); } catch { }
                            try { sb.Append(":phase=").Append(c.currentPhase != null ? c.currentPhase.Value : -1); } catch { }
                            try { sb.Append(":grown=").Append(c.fullyGrown != null && c.fullyGrown.Value); } catch { }
                            try { sb.Append(":dead=").Append(c.dead != null && c.dead.Value); } catch { }
                        }
                    }
                }

                try
                {
                    if (loc.doesTileHaveProperty(x, y, "Action", "Back") != null) sb.Append("|action");
                    if (loc.doesTileHaveProperty(x, y, "TouchAction", "Back") != null) sb.Append("|touch");
                }
                catch { }
                try { if (loc.doors != null && loc.doors.ContainsKey(new Point(x, y))) sb.Append("|door"); } catch { }

                return sb.ToString();
            }
            catch { return null; }
        }

        /// <summary>【task-182 必修 1】目标格"现在能不能收"（游戏口径）与来源；不是作物格/读不到 ⇒ (null, null)。
        /// 为什么单独要它：再生作物收成后 `TileSig` 的 6 个字段一项都不变（作物对象保留、阶段重置），
        /// 只有 `ready` 会 true→false ⇒ 这一条是再生作物**唯一**的格子级证据。</summary>
        private static (bool? Ready, string Source) TileReady(int x, int y)
        {
            try
            {
                GameLocation loc = Game1.currentLocation;
                if (loc?.terrainFeatures == null) return (null, null);
                StardewValley.TerrainFeatures.TerrainFeature tf;
                if (!loc.terrainFeatures.TryGetValue(new Vector2(x, y), out tf)) return (null, null);
                var hd = tf as StardewValley.TerrainFeatures.HoeDirt;
                if (hd?.crop == null) return (null, null);
                return CropMeta.Ready(hd, hd.crop);
            }
            catch { return (null, null); }
        }

        /// <summary>【task-182 必修 1】整场"现在可收"的作物格数（与 `FarmScan` 同判据、同一次遍历口径）。
        /// 读不到 ⇒ **-1**（不是 0 —— 0 是"真的没有可收的"这个事实）。</summary>
        private static int ReadyCropCount()
        {
            try
            {
                Farm farm = Game1.getFarm();
                if (farm?.terrainFeatures == null) return -1;
                int n = 0;
                // `SerializableDictionary` 的枚举入口是 `Pairs`（与 `FarmScan.cs` 同款写法）。
                foreach (var pair in farm.terrainFeatures.Pairs)
                {
                    var hd = pair.Value as StardewValley.TerrainFeatures.HoeDirt;
                    if (hd?.crop == null) continue;
                    if (CropMeta.Ready(hd, hd.crop).Value == true) n++;
                }
                return n;
            }
            catch { return -1; }
        }

        /// <summary>【task-182 必修 1】背包逐 qid 栈数快照（弱证据的来源；取不到 ⇒ 空字典）。</summary>
        private static Dictionary<string, int> InventoryStacks()
        {
            var map = new Dictionary<string, int>(StringComparer.Ordinal);
            try
            {
                Farmer who = Game1.player;
                if (who?.Items == null) return map;
                foreach (Item it in who.Items)
                {
                    if (it == null) continue;
                    string qid = it.QualifiedItemId ?? it.ItemId ?? "";
                    if (qid.Length == 0) continue;
                    int cur;
                    map.TryGetValue(qid, out cur);
                    map[qid] = cur + Math.Max(0, it.Stack);
                }
            }
            catch { }
            return map;
        }

        /// <summary>任一 qid 的栈数比动作前多 ⇒ true（真值来源，绝不由"游戏返回值"推）。</summary>
        private static bool InventoryGrew(Dictionary<string, int> before, Dictionary<string, int> after)
        {
            foreach (var pair in after)
            {
                int was;
                if (!before.TryGetValue(pair.Key, out was)) was = 0;
                if (pair.Value > was) return true;
            }
            return false;
        }

        /// <summary>已知技能名（用于区分 unknown_skill 与 not_implemented）。</summary>
        private static readonly HashSet<string> KnownSkills = new HashSet<string>(StringComparer.Ordinal)
        {
            // 已实现
            "noop", "move_to", "dismiss_modal", "move_to_location", "load_save", "quit_game", "interact", "use_tool",
            "select_item", "plant", "sleep", "buy", "sell",
            // 架构 §5.3 规划中（返回 not_implemented，便于“脑”一次性看清缺口）
            "exit_building", "harvest",
            "pickup_debris", "collect_machine", "refill_watering_can", "talk",
        };

        public static bool IsKnownSkill(string skill) => skill != null && KnownSkills.Contains(skill);

        // ==================================================================
        //  move_to（当前地点内走一格）
        // ==================================================================

        /// <summary>
        /// 移动状态机已抽到 <see cref="StepMover"/>；本类只负责**前置校验 + 回执组装**。
        /// 前置校验的顺序、每一条 reason 文案都是 v0.5.1 真机对线过的，不要改动顺序：
        /// “已在该格”必须排在家具判据之前（FarmHouse 出生点 (9,9) 被床的包围盒覆盖），
        /// “家具”必须排在“不可通行”之前（否则家具分支变死代码）。
        /// </summary>
        private sealed class MoveToSkill
        {
            private readonly WorldObserver _world;
            private readonly IMonitor _monitor;
            private readonly int _timeoutMs;
            private readonly Point _target;
            private readonly bool _allowBed;

            private bool _started;
            private DateTime _startedAtUtc;
            private long _seqBefore;
            private StepMover _mover;

            public MoveToSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
            {
                this._world = world;
                this._monitor = monitor;
                this._timeoutMs = ClampTimeout(req?.TimeoutMs);

                int[] tile = req?.Args?.Tile;
                this._target = (tile != null && tile.Length >= 2)
                    ? new Point(tile[0], tile[1])
                    : new Point(int.MinValue, int.MinValue);
                this._allowBed = req?.Args?.AllowBed ?? false;
            }

            private ExecResponse Fail(string status, string reason, long elapsedMs)
                => new ExecResponse
                {
                    Ok = false,
                    Status = status,
                    Skill = "move_to",
                    Reason = reason,
                    ElapsedMs = elapsedMs,
                    WorldSeqBefore = this._seqBefore,
                    WorldSeqAfter = this._world.WorldSeq,
                };

            private ExecResponse Ok(long elapsedMs, string reason = null)
            {
                var r = new ExecResponse
                {
                    Ok = true,
                    Status = "ok",
                    Skill = "move_to",
                    Reason = reason ?? (this._allowBed
                        ? "allow_bed=true：本次调用显式放行了床格（目标若为床会触发睡觉弹窗）"
                        : ""),
                    ElapsedMs = elapsedMs,
                    WorldSeqBefore = this._seqBefore,
                    WorldSeqAfter = this._world.WorldSeq,
                };

                // ---- 到达后的副作用：是否顺手弹出了模态 ----
                //
                // 真机实测：走到床边会“成功到达”，但同时触发 "go to sleep for the night?" 对话框，
                // 整个世界时间随之冻结。v1 在这种情况下只回一个 ok，脑会以为一切正常，
                // 于是继续下发下一步 —— 而所有动作都会因为模态挡路而失败。
                // 这里把“到达 + 弹窗”如实报回去，脑再决定是否调 dismiss_modal。
                try
                {
                    r.UiOpened = Game1.activeClickableMenu != null;
                    if (r.UiOpened) r.ActiveMenuText = UiRead.ActiveMenuText();
                }
                catch { }

                return r;
            }

            /// <summary>每次被主线程调用：返回 null = 还在走，返回非 null = 终态。</summary>
            public object Step()
            {
                try
                {
                    if (!_started) return this.Begin();

                    long elapsed = (long)(DateTime.UtcNow - _startedAtUtc).TotalMilliseconds;

                    if (this._mover == null)
                        return this.Fail("error", "move_to 执行异常：移动状态机未初始化", elapsed);

                    MoveOutcome o = this._mover.Tick(elapsed);

                    switch (o.Kind)
                    {
                        case MoveStopKind.Running: return null;
                        case MoveStopKind.Arrived: return this.Ok(elapsed);
                        default: return this.Fail(o.Status, o.Reason, elapsed);
                    }
                }
                catch (Exception ex)
                {
                    // 技能内部异常：保证把玩家**彻底**停下来（控制器 + 残留移动方向），
                    // 再把异常摘要交回网络线程。
                    // 【为什么不能只清 controller】见 StepMover.SettleFrames 的注释：
                    // 只清控制器会把行走方向留在身上，角色会继续走到撞墙。
                    try { StepMover.HaltPlayer(); } catch { }
                    return this.Fail("error", "move_to 执行异常：" + ex.GetType().Name + ": " + ex.Message,
                        this._started ? (long)(DateTime.UtcNow - _startedAtUtc).TotalMilliseconds : 0);
                }
            }

            /// <summary>前置校验 + 发起寻路。返回 null 表示已经发起、需要后续 tick 推进。</summary>
            private object Begin()
            {
                _started = true;
                _startedAtUtc = DateTime.UtcNow;
                _seqBefore = _world.WorldSeq;

                // ---- 前置校验 ----
                if (!Context.IsWorldReady || Game1.player == null || Game1.currentLocation == null)
                    return this.Fail("no_save", "尚未加载存档，无法执行 move_to", 0);

                if (_target.X == int.MinValue || _target.Y == int.MinValue)
                    return this.Fail("precondition_failed", "缺少参数 args.tile（期望 [x, y] 两个整数）", 0);

                // 已经在目标格上：直接成功，**不要**再去问"这格能不能站"。
                // 【为什么必须排在家具判据之前】FarmHouse 的玩家出生点 (9,9) **正好被床的包围盒
                // 覆盖**（床 bbox [576,512,128,192] = 像素 x 9..11 / y 8..11），于是出现过荒谬结论：
                // "移动到我自己站的这一格" → `precondition_failed: 目标格有家具（床）`。
                // 玩家此刻站在这里，本身就是"可站"的最强证据。
                if (Game1.player.TilePoint == _target)
                    return this.Ok(0, $"已在该格 {FormatTile(_target)}（无需移动）");

                if (StepMover.UiBlocked())
                    return this.Fail("ui_modal",
                        "当前有菜单/对话/过场打开，无法移动（请先关闭模态）。"
                        + "⚠ 若脑侧**刚刚踩上床的睡觉触发格**（`TouchAction=\"Sleep\"`），"
                        + "这个 ui_modal 是**命中信号**（提问框被自己弹出来了），不是失败："
                        + "应答之后同一 tick 就会关框（SleepSkill），脑侧不要据此重试 move_to",
                        0);

                if (_target.X < 0 || _target.Y < 0)
                    return this.Fail("precondition_failed", $"目标格 {FormatTile(_target)} 坐标为负数，非法", 0);

                // 目标必须在当前地点内。
                //
                // 【why：尺寸来源】不再用 Map.DisplayWidth / DisplayHeight（个别地点会抛异常），
                // 权威来源是 xTile 图层（StepMover.SizeFromLayers，单位就是格）。
                //
                // 【文案在 v0.6.0 改过：尾缀 "跨地点移动尚未实现" → "跨地点移动请用 move_to_location"】
                // 里程碑 B 抽取时的硬约束是"move_to 的对线行为逐字不变"，但那条约束的目的是
                // **防止抽取本身引入行为差异**，不是把一句已经变成假话的文案永久冻住：
                // 里程碑 B 已经交付了 move_to_location，再说"尚未实现"会误导脑去放弃跨地点。
                // 判定逻辑一字未动，改的只是 reason 尾缀。
                int maxX = int.MaxValue, maxY = int.MaxValue;
                try
                {
                    StepMover.SizeFromLayers(Game1.currentLocation, out maxX, out maxY);
                }
                catch { maxX = int.MaxValue; maxY = int.MaxValue; }

                if (maxX > 0 && maxY > 0 && (_target.X >= maxX || _target.Y >= maxY))
                {
                    return this.Fail("precondition_failed",
                        $"目标格 {FormatTile(_target)} 不在当前地点 {Game1.currentLocation.Name} 内（该地点尺寸 {maxX}x{maxY}）；"
                        + "跨地点移动请用 move_to_location（move_to 只在当前地点内走）",
                        0);
                }

                // ---- 家具优先于“不可通行” ----
                //
                // 顺序很重要（修复迭代 3 的真机 bug）：StepMover.Standable 发现**阻挡家具**时返回 false
                // 并输出家具引用，所以旧写法先判 `!standable` 会把家具分支变成**死代码**。
                // 必须**先判家具**，这样真机上才能看到“该格有家具（床）”这种可操作的信息。
                bool standable = StepMover.Standable(Game1.currentLocation, _target, this._allowBed, out Furniture blocking);

                if (blocking != null)
                {
                    // 家具单独报 precondition_failed：这不是“走不到”，而是“这个格子本来就不该被当成落脚点”。
                    //
                    // 【说明】只有"踩不上去的家具"或床才进来；可踩的地毯等一律放行（详见 StepMover.Standable）。
                    // 【文案】床的那一支不能把整句解释塞进 kind，否则会变成
                    // `有家具（床/家具（床是特例：…）），…` —— 括号套括号、还重复"家具"。
                    // 原因类别只留一个短词，解释另起一句。
                    bool isBed = blocking is StardewValley.Objects.BedFurniture;
                    string kind = isBed ? "床" : blocking.GetType().Name;
                    string why = isBed
                        ? "；床可以踩，但踩上去会触发睡觉确认框（确认框开着时世界时间冻结），所以默认拒绝。"
                          + "若**故意**要引出这个弹窗（例如测试 dismiss_modal），请传 args.allow_bed=true"
                        : "";
                    return this.Fail("precondition_failed",
                        $"目标格 {FormatTile(_target)} 有家具（{kind}），不能作为落脚点；请改选旁边的空地板格{why}", 0);
                }

                if (!standable)
                {
                    return this.Fail("unreachable",
                        $"目标格 {FormatTile(_target)} 不可通行（被建筑/水面/障碍占据），无法走上去", 0);
                }

                // ---- 发起寻路（清残留控制器 → A* 无解立即放弃 → 交后续 tick 推进）----
                var mover = new StepMover(Game1.currentLocation, _target, this._timeoutMs, "move_to");
                MoveOutcome o = mover.Begin();

                if (o.Kind != MoveStopKind.Running)
                    return this.Fail(o.Status, o.Reason, 0);

                this._mover = mover;
                return null;   // 交给后续 tick 推进
            }

            private static string FormatTile(Point p) => StepMover.FormatTile(p);
        }
    }
}
