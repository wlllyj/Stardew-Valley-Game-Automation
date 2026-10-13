using System.Text.Json;
using System.Text.Json.Serialization;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 线协议契约（JSON DTO）。
    ///
    /// 【为什么全部显式写死属性名】
    /// 架构文档 §3.2 D5 的教训是“schema 声明了却从不校验 / C# 写 /1 而 Python 写 /2”。
    /// 所以这里的每一个字段名都用 [JsonPropertyName] 逐字钉死，**不依赖命名策略的推理**，
    /// 让 C# 侧与 Python 侧不可能悄悄错位。字段名与《01-架构设计.md》§6 / 里程碑 A 契约逐字一致。
    ///
    /// 【为什么统一用 WhenWritingNull】
    /// 快照在“未加载存档”时要返回“其余段为 null”的形态；用 null 忽略策略可以让
    /// DTO 只写一份声明就同时满足“完整”与“缺段”两种形状。
    /// </summary>
    internal static class JsonDefaults
    {
        /// <summary>
        /// 统一的序列化设置：camelCase 策略（与外部“脑”的约定）+ 不转义中文。
        ///
        /// 【为什么是 public】让 tools/JsonContractCheck 能**复用同一份设置**跑字段名自检，
        /// 避免“自检用了另一份设置所以永远通过”的假验证。
        /// </summary>
        public static readonly JsonSerializerOptions Options = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            WriteIndented = false,
        };

        public static string Serialize<T>(T value) => JsonSerializer.Serialize(value, Options);
    }

    // ==================================================================
    //  /v1/health
    // ==================================================================

    internal sealed class HealthResponse
    {
        [JsonPropertyName("ok")] public bool Ok { get; set; }
        [JsonPropertyName("status")] public string Status { get; set; }
        [JsonPropertyName("schema")] public string Schema { get; set; }
        [JsonPropertyName("modVersion")] public string ModVersion { get; set; }
        [JsonPropertyName("game")] public HealthGame Game { get; set; }
        [JsonPropertyName("runtime")] public HealthRuntime Runtime { get; set; }
        [JsonPropertyName("server")] public HealthServer Server { get; set; }
    }

    internal sealed class HealthGame
    {
        [JsonPropertyName("version")] public string Version { get; set; }
        [JsonPropertyName("smapi")] public string Smapi { get; set; }

        /// <summary>
        /// 游戏窗口是否在前台（<c>Game1.game1.IsActive</c>）。注意：它**只说明焦点状态**，
        /// 不直接决定世界走不走 —— 真正的门是 <c>Game1._update</c> IL_0444–IL_0480：
        /// 窗口不活跃 **且** <see cref="PauseWhenOutOfFocus"/> 为 true 时直接 ret，
        /// 于是 UpdateGameClock / UpdateLocations（含 PathFindController）整段被跳过。
        /// Mod 每帧把该选项关掉（见 BridgeHost.EnforceNoPauseOnFocusLoss），
        /// 所以正常运行时"失焦"不该再让世界停摆；一旦停了，先看下面两个字段。
        /// </summary>
        [JsonPropertyName("windowActive")] public bool WindowActive { get; set; }

        /// <summary>
        /// 游戏选项 <c>Options.pauseWhenOutOfFocus</c> 的**当前实际值**（不是我们期望的值）。
        /// true 表示这一帧世界会被冻结在失焦状态；正常运行应为 false。
        /// </summary>
        [JsonPropertyName("pauseWhenOutOfFocus")] public bool PauseWhenOutOfFocus { get; set; }

        /// <summary>
        /// Mod 本局把 <c>pauseWhenOutOfFocus</c> 从 true 扳回 false 的次数。
        /// &gt;0 就是"这个选项被读档/回标题换掉过"的**直接证据**；它长期为 0 说明没人改它。
        /// </summary>
        [JsonPropertyName("oofFixCount")] public long OofFixCount { get; set; }
    }

    internal sealed class HealthRuntime
    {
        [JsonPropertyName("ticks")] public long Ticks { get; set; }
        [JsonPropertyName("uptimeSeconds")] public double UptimeSeconds { get; set; }
        [JsonPropertyName("worldSeq")] public long WorldSeq { get; set; }
        [JsonPropertyName("hasSaveLoaded")] public bool HasSaveLoaded { get; set; }
        [JsonPropertyName("onTitleScreen")] public bool OnTitleScreen { get; set; }
    }

    internal sealed class HealthServer
    {
        [JsonPropertyName("port")] public int Port { get; set; }
        [JsonPropertyName("requestsServed")] public long RequestsServed { get; set; }
    }

    // ==================================================================
    //  /v1/observe  —— agentfarm-world/5
    // ==================================================================

    internal sealed class WorldSnapshot
    {
        [JsonPropertyName("ok")] public bool Ok { get; set; }
        [JsonPropertyName("status")] public string Status { get; set; }
        [JsonPropertyName("schema")] public string Schema { get; set; }
        [JsonPropertyName("worldSeq")] public long WorldSeq { get; set; }
        [JsonPropertyName("generatedAt")] public string GeneratedAt { get; set; }
        [JsonPropertyName("hasSaveLoaded")] public bool HasSaveLoaded { get; set; }
        [JsonPropertyName("clock")] public ClockView Clock { get; set; }
        [JsonPropertyName("player")] public PlayerView Player { get; set; }
        [JsonPropertyName("location")] public LocationView Location { get; set; }
        [JsonPropertyName("farm")] public FarmView Farm { get; set; }
        [JsonPropertyName("ui")] public UiView Ui { get; set; }
        [JsonPropertyName("liveness")] public LivenessView Liveness { get; set; }

        /// <summary>v3 新增：游戏级暂停/时间状态（诊断“看起来正常但世界停摆”用）。</summary>
        [JsonPropertyName("game")] public GameStateView Game { get; set; }

        /// <summary>
        /// v0.7.24 新增：出货箱内容（task-42）。`shipItem` 的**唯一客观判据**：
        /// 钱要等下一次 `NewDay` 才结算，在那之前只能看"东西真的进箱了没有"。
        /// </summary>
        [JsonPropertyName("shippingBin")] public ShippingBinView ShippingBin { get; set; }
    }

    internal sealed class ClockView
    {
        [JsonPropertyName("year")] public int Year { get; set; }
        [JsonPropertyName("season")] public string Season { get; set; }
        [JsonPropertyName("day")] public int Day { get; set; }
        [JsonPropertyName("timeOfDay")] public int TimeOfDay { get; set; }

        /// <summary>
        /// 当前地点的天气，取值恒为 rain / snow / lightning / debris / sunny 之一（不再可能为空串）。
        /// 判定顺序见 WorldObserver.DescribeWeather 的注释。
        /// </summary>
        [JsonPropertyName("weather")] public string Weather { get; set; }

        /// <summary>农场（Farm）的天气。人在镇上/矿洞时也能知道“农场在下雨吗”，用于规划浇水。</summary>
        [JsonPropertyName("weatherOnFarm")] public string WeatherOnFarm { get; set; }
    }

    internal sealed class PlayerView
    {
        [JsonPropertyName("name")] public string Name { get; set; }
        [JsonPropertyName("location")] public string Location { get; set; }
        [JsonPropertyName("tile")] public int[] Tile { get; set; }
        [JsonPropertyName("facing")] public int Facing { get; set; }
        [JsonPropertyName("stamina")] public float Stamina { get; set; }
        [JsonPropertyName("maxStamina")] public float MaxStamina { get; set; }
        [JsonPropertyName("health")] public int Health { get; set; }
        [JsonPropertyName("maxHealth")] public int MaxHealth { get; set; }
        [JsonPropertyName("money")] public int Money { get; set; }
        [JsonPropertyName("farmingLevel")] public int FarmingLevel { get; set; }
        [JsonPropertyName("inventoryCount")] public int InventoryCount { get; set; }

        /// <summary>
        /// 玩家当前是否可以移动（<c>Game1.player.CanMove</c>）。
        /// 真机教训：窗口失焦且 <c>pauseWhenOutOfFocus=true</c> 时，<c>Game1._update</c> 提前 ret，
        /// `UpdateLocations → Farmer.Update → PathFindController.update` 全被跳过，角色一格不动
        /// （实测失焦 0/3 位移 vs 抢焦点后每次 3 格位移）。v0.5.0 起 Mod 每帧关掉该选项，
        /// 让"失焦"不再等于"角色不动"；这个字段继续保留，用来区分"人能不能动"。
        /// </summary>
        [JsonPropertyName("canMove")] public bool CanMove { get; set; }

        /// <summary>身上是否挂着寻路控制器（<c>player.controller != null</c>）。诊断“动作做了一半”用。</summary>
        [JsonPropertyName("hasController")] public bool HasController { get; set; }

        /// <summary>
        /// v3 新增：玩家是否“在床上”（<c>Game1.player.isInBed.Value</c>）。
        /// 睡觉流程会把人置为 isInBed 且 CanMove=false、时间冻结，靠这个字段才能区分
        /// “睡觉/过场流程中”与“模态挡路”。
        /// </summary>
        [JsonPropertyName("isInBed")] public bool IsInBed { get; set; }

        [JsonPropertyName("tools")] public ToolsView Tools { get; set; }

        /// <summary>
        /// **v0.7.21 新增**：浇水壶的水量（`WateringCan.WaterLeft` / `waterCanMax`）。
        ///
        /// 【为什么必须有】长跑循环要"连续 N 个游戏日浇水"，而**水壶会空**：基础壶 40 格，
        /// 30 多格作物浇一天就没了，壶空的第二天 `use_tool(can)` 会一直 `tool_ineffective`。
        /// 脑必须先知道"还剩几格水"才能在浇干前去补水（见 `LocationView.RefillTiles`）。
        /// </summary>
        [JsonPropertyName("wateringCan")] public WateringCanView WateringCan { get; set; }

        /// <summary>
        /// **背包清单（仅 `detail=full`）**：播种/收获/吃东西都要先知道"我有什么"。
        /// 此前快照只有 `inventoryCount`，脑根本不知道手里有没有防风草种子（P3 步骤④的硬缺口）。
        /// </summary>
        [JsonPropertyName("inventory")] public ItemView[] Inventory { get; set; }
    }

    /// <summary>
    /// 游戏级状态（v3 新增）。
    ///
    /// 【为什么需要】本次事故的真机现场是“画面正常、模态没了、canMove=false、时钟冻死”，
    /// 而 v2 快照里没有任何字段能说明“游戏是否认为自己处于暂停/冻结状态”，只能靠猜。
    /// 这两个字段把“游戏自己怎么看时间”直接摊开：
    ///   * `paused`：`Game1.paused`；
    ///   * `shouldTimePass`：`Game1.shouldTimePass()`（无参重载）。
    /// IL 实证：`shouldTimePass` 里有 `if (!player.CanMove &amp;&amp; !player.UsingTool) return player.forceTimePass;`
    /// —— 也就是说 **CanMove=false 会让时间停止推进**，这正是那次“时钟停在 640”的机制。
    /// </summary>
    internal sealed class GameStateView
    {
        [JsonPropertyName("paused")] public bool Paused { get; set; }
        [JsonPropertyName("shouldTimePass")] public bool ShouldTimePass { get; set; }
    }

    internal sealed class ToolsView
    {
        [JsonPropertyName("hoe")] public bool Hoe { get; set; }
        [JsonPropertyName("axe")] public bool Axe { get; set; }
        [JsonPropertyName("pickaxe")] public bool Pickaxe { get; set; }
        [JsonPropertyName("wateringCan")] public bool WateringCan { get; set; }
        [JsonPropertyName("fishingRod")] public bool FishingRod { get; set; }
        [JsonPropertyName("weapon")] public bool Weapon { get; set; }
    }

    internal sealed class LocationView
    {
        [JsonPropertyName("name")] public string Name { get; set; }

        /// <summary>
        /// ⚠️ 语义陷阱：这是 SMAPI 的 <c>GameLocation.IsFarm</c>，它对 <c>Farm</c> **和** <c>FarmHouse</c>
        /// 都返回 true（1.6 起农舍也属于“farm 类型”地点）。
        /// 因此它**不能**用来回答“我是不是站在露天农场上”。要那个语义请用 isOutdoorFarm。
        /// </summary>
        [JsonPropertyName("isFarm")] public bool IsFarm { get; set; }

        /// <summary>
        /// 露天农场（地点名恰好是 "Farm"）。与 isFarm 的区别：本字段在 FarmHouse / 温室 / 地窖里都是 false。
        /// </summary>
        [JsonPropertyName("isOutdoorFarm")] public bool IsOutdoorFarm { get; set; }

        [JsonPropertyName("isFarmhouse")] public bool IsFarmhouse { get; set; }
        [JsonPropertyName("isOutdoors")] public bool IsOutdoors { get; set; }
        [JsonPropertyName("objects")] public int Objects { get; set; }
        [JsonPropertyName("debris")] public int Debris { get; set; }
        [JsonPropertyName("terrainFeatures")] public int TerrainFeatures { get; set; }
        [JsonPropertyName("characters")] public int Characters { get; set; }

        /// <summary>
        /// **v4 新增，仅 `detail=full` 时出现**（`summary` 必须为 null → 字段缺失）。
        ///
        /// 当前地点每一件家具的清单，专供诊断"到底哪件家具覆盖了哪一格"：
        /// 迭代 4 之前只能靠**网格扫描猜**（在屋里逐格 move_to 看哪格被拒），
        /// 既慢又容易得出错误结论（v3 就是这样把 13 格误判成"有家具"的）。
        /// 有了这份清单，`tile` / `bbox` / `passable` / `ground` 摆在一起看，
        /// 一眼就能看出"是哪块大地毯盖住了这格、它其实可以踩"。
        /// </summary>
        [JsonPropertyName("furniture")] public FurnitureView[] Furniture { get; set; }

        /// <summary>
        /// **v0.6.2 新增，仅 `detail=full` 时出现**（`summary` 必须为 null → 字段缺失）。
        ///
        /// 当前地点的**门**清单（`GameLocation.doors`：门格 → 门类型）。
        ///
        /// 【为什么必须有】`GameLocation.isCollidingWithDoors` 的 IL 实证：它遍历的是
        /// **`this.doors`**，用玩家像素矩形**四个角**所在格去比对，命中才 `getWarpFromDoor` 拿 Warp。
        /// ⇒ **门的权威格子在这张字典里**，`Building.getPointForHumanDoor()` 只是其中一条解析路径。
        /// 跨地点图必须同时用这两者；诊断"为什么门没触发"也必须先看这份清单。
        /// </summary>
        [JsonPropertyName("doors")] public DoorView[] Doors { get; set; }

        /// <summary>
        /// **v0.7.18 新增（仅 `detail=full`）**：当前地点里**能锄出耕地**的空格（近处优先，最多 200 个）。
        ///
        /// 【为什么需要（用户 m01668 提的）】P3 要"开垦 N 格"，而在此之前脑只能**瞎试空格**
        /// （验收脚本就是这么干的：挨个 `use_tool(hoe)`，不可锄的要白挥 6 次才报 `tool_ineffective`）。
        /// 判据照抄游戏自己的 `Hoe.DoFunction`（IL_0165–IL_01A7）：没有地形特征、没有放置物、不是水面、
        /// 且 `Back` 图层上有 `Diggable` 属性 ⇒ 见 `StepMover.Tillable`。
        /// </summary>
        [JsonPropertyName("tillable")] public int[][] Tillable { get; set; }

        /// <summary>
        /// **v0.7.4 新增（`agentfarm-world/6`），仅 `detail=full` 时出现**。
        ///
        /// **逐格清单**：这一格上有什么、该用什么工具、现在能不能站人。
        ///
        /// 【为什么必须有（P3 的头号缺口）】在此之前 `objects` / `terrainFeatures` **只有计数**
        /// （`weeds=456, stones=247` 之类），脑**看不见"哪一格上是什么"** ⇒ 规划层只能猜格子，
        /// 正是旧项目"照着 LLM 给的坐标乱走"的病根。有了 `tiles[]`，脑才能自己挑"要清的那一格"。
        ///
        /// 判据全部问游戏：`Object.IsWeeds()/IsTwig()/IsBreakableStone()`、
        /// `terrainFeatures` 的具体类型（`Grass/Tree/FruitTree/ResourceClump/HoeDirt/Bush`）、
        /// 可站性用 `StepMover.Standable`（与 `move_to` 同一套判据）。
        /// **上限 400 格**，超出时 `tilesTruncated=true`（payload 必须有界）。
        /// </summary>
        [JsonPropertyName("tiles")] public TileView[] Tiles { get; set; }

        /// <summary>`tiles[]` 是否因为超过上限被截断（null/false = 完整）。</summary>
        [JsonPropertyName("tilesTruncated")] public bool? TilesTruncated { get; set; }

        /// <summary>
        /// **v0.7.21 新增（仅 `detail=full`）**：当前地点里**能给浇水壶补水**的格子（近处优先，最多 24 个）。
        ///
        /// 【判据是游戏自己的】逐格调 `GameLocation.CanRefillWateringCanOnTile(x, y)`
        /// （api-probe 实证 public；`logs\api-water-members.txt`）——包括水面、水槽，也包括
        /// 农场小屋里的水槽这类"看起来不像是水"的格子，**不硬编码坐标、也不猜地形**。
        /// 长跑循环里壶水量低于阈值时，脑走到最近一格补水再继续浇。
        /// </summary>
        [JsonPropertyName("refillTiles")] public int[][] RefillTiles { get; set; }

        /// <summary>`refillTiles[]` 是否因为超过上限被截断（null/false = 完整）。</summary>
        [JsonPropertyName("refillTilesTruncated")] public bool? RefillTilesTruncated { get; set; }
    }

    /// <summary>浇水壶视图（快照 v0.7.21 新增）。见 <see cref="PlayerView.WateringCan"/>。</summary>
    internal sealed class WateringCanView
    {
        /// <summary>背包里到底有没有浇水壶。</summary>
        [JsonPropertyName("present")] public bool Present { get; set; }

        /// <summary>`WateringCan.WaterLeft`：还能浇几格（0 = 空了，必须先补水）。</summary>
        [JsonPropertyName("waterLeft")] public int WaterLeft { get; set; }

        /// <summary>`WateringCan.waterCanMax`：当前升级等级下的容量上限。</summary>
        [JsonPropertyName("max")] public int Max { get; set; }

        /// <summary>`Farmer.hasWateringCanEnchantment`：无尽之壶（附魔）时为 true，永远不用补水。</summary>
        [JsonPropertyName("bottomless")] public bool Bottomless { get; set; }

        /// <summary>`WateringCan.UpgradeLevel`：壶的升级等级（诊断用）。</summary>
        [JsonPropertyName("upgradeLevel")] public int UpgradeLevel { get; set; }
    }

    /// <summary>背包里一件物品的视图（快照 v0.7.9 新增，仅 `detail=full`）。</summary>
    internal sealed class ItemView
    {
        /// <summary>背包槽位下标（`select_item` 就用它设 `CurrentToolIndex`）。</summary>
        [JsonPropertyName("slot")] public int Slot { get; set; }

        /// <summary>`Item.ItemId`（例：防风草种子 `472`、锄头 `Hoe`）。</summary>
        [JsonPropertyName("id")] public string Id { get; set; }

        /// <summary>`Item.QualifiedItemId`（带类型前缀的全局 id，例：`(O)472`）。</summary>
        [JsonPropertyName("qualifiedId")] public string QualifiedId { get; set; }

        /// <summary>可读名（`DisplayName`，失败退回 `Name`）。</summary>
        [JsonPropertyName("name")] public string Name { get; set; }

        /// <summary>堆叠数量。</summary>
        [JsonPropertyName("stack")] public int Stack { get; set; }

        /// <summary>是不是工具（`Tool` 子类）。</summary>
        [JsonPropertyName("isTool")] public bool IsTool { get; set; }
    }

    /// <summary>
    /// 出货箱视图（task-42 新增，快照 v0.7.24）。
    ///
    /// 【为什么必须新增它 —— docs/_il-sell-path.md §6 U1】
    /// `Farm.shipItem` 是把物品**搬进箱子**，钱要等**下一次 `NewDay`** 才结算
    /// （`_newDayAfterFade` 里 `player.Money = player.Money + total`）。
    /// 在那之前，唯一的"东西真的进箱了"的证据就是箱子的内容 ⇒ 没有这个字段，
    /// 脑侧“卖出成功”的判据就只能看回执（回执不算证据）。
    ///
    /// 【为什么不是塞进 `farm`】`FarmView` 读的是后台扫描线程的缓存（可能过期/跨线程），
    /// 而箱子是**主线程当帧**的真值，所以放在快照顶层由 `WorldSnapshot.Read()` 现读。
    /// </summary>
    internal sealed class ShippingBinView
    {
        /// <summary>箱子对象是否拿得到（`Farm.getShippingBin(player)` 非 null）。</summary>
        [JsonPropertyName("present")] public bool Present { get; set; }

        /// <summary>箱子里**非空**物品件数。</summary>
        [JsonPropertyName("count")] public int Count { get; set; }

        /// <summary>箱内物品（槽位/ qualifiedId / 数量；只报非空的）。</summary>
        [JsonPropertyName("items")] public ItemView[] Items { get; set; }

        /// <summary>`Farm.lastItemShipped` 的 qualifiedId（没有则是空串）。</summary>
        [JsonPropertyName("lastItemShipped")] public string LastItemShipped { get; set; }

        /// <summary>该存档是否用独立钱包（决定箱子是玩家个人箱还是共享箱）。</summary>
        [JsonPropertyName("separateWallets")] public bool SeparateWallets { get; set; }
    }

    /// <summary>单格清单项（快照 v0.7.4 / `agentfarm-world/6` 新增，仅 `detail=full`）。</summary>
    internal sealed class TileView
    {
        /// <summary>格坐标 `[x, y]`。</summary>
        [JsonPropertyName("tile")] public int[] Tile { get; set; }

        /// <summary>
        /// `weed`（杂草）/ `twig`（树枝）/ `stone`（可敲石头）/ `object`（其它放置物，如机器、箱子、掉落物）/
        /// `tree`（树）/ `fruitTree`（果树）/ `clump`（资源堆）/ `grass`（草）/ `dirt`（耕地）/
        /// `bush`（灌木）/ `unknown`。
        /// </summary>
        [JsonPropertyName("kind")] public string Kind { get; set; }

        /// <summary>要清掉/处理这一格该用哪个工具：`scythe` / `axe` / `pickaxe` / `hoe` / `can` / `none`。</summary>
        [JsonPropertyName("tool")] public string Tool { get; set; }

        /// <summary>select_item 专用：要找的物品（ItemId / QualifiedItemId / 名字，大小写不敏感）。</summary>
        [JsonPropertyName("item")] public string Item { get; set; }

        /// <summary>plant 专用：要种下的种子 ItemId（例 472 = 防风草种子）。</summary>
        [JsonPropertyName("seed")] public string Seed { get; set; }

        /// <summary>`objects` 里那一项的 `ItemId`（没有则为 null）。</summary>
        [JsonPropertyName("objId")] public string ObjId { get; set; }

        /// <summary>`terrainFeatures` 里那一项的类型名（没有则为 null）。</summary>
        [JsonPropertyName("feature")] public string Feature { get; set; }

        /// <summary>
        /// 这一格**自己**能不能站人（与 `move_to` 同一套判据，`allow_bed=true`）。
        /// ⚠️ 有杂草/石头/树枝的格子**必然**是 false（那正是"要清掉的东西"），
        /// 所以规划不能只看它 —— 判断"够不够得着"要用 <see cref="Actionable"/>。
        /// </summary>
        [JsonPropertyName("standable")] public bool Standable { get; set; }

        /// <summary>
        /// 这一格**够不够得着**（能不能站到旁边/站上去对它动手）＝ 自身可站 **或** 四邻有一格可站。
        /// 这是规划层真正要用的那个判据（锄地/播种/砍草都是"对着某一格动手"）。
        /// 首版只算了 `Standable`，真机一看 400 格全是 `reachable=false`（因为格子上都有东西）——
        /// 语义错了，故拆成 standable + actionable 两个字段。
        /// </summary>
        [JsonPropertyName("actionable")] public bool Actionable { get; set; }

        /// <summary>作物：`Crop.indexOfHarvest`（成熟后收获物的 id）；没有作物则 null。</summary>
        [JsonPropertyName("crop")] public string Crop { get; set; }

        /// <summary>作物是否已成熟可收（`Crop.fullyGrown`）。</summary>
        [JsonPropertyName("ripe")] public bool Ripe { get; set; }

        /// <summary>作物是否已枯死（`Crop.dead`）。</summary>
        [JsonPropertyName("dead")] public bool Dead { get; set; }

        /// <summary>耕地是否已浇水（`HoeDirt.isWatered()`）。</summary>
        [JsonPropertyName("watered")] public bool Watered { get; set; }

        /// <summary>
        /// 这一格现在**能不能播种** ＝ 是耕地（`HoeDirt`）且上面没有作物。
        /// 规划层"开垦 → 播种"就靠它（`kind=dirt` + `plantable=true` + `watered=false` ⇒ 该下种子）。
        /// </summary>
        [JsonPropertyName("plantable")] public bool Plantable { get; set; }
    }

    /// <summary>单个门的诊断视图（快照 v0.6.2 新增，仅 `detail=full`）。</summary>
    internal sealed class DoorView
    {
        /// <summary>门格 `[x, y]`（世界格坐标）——玩家像素矩形的**角**落到这一格才会触发。</summary>
        [JsonPropertyName("tile")] public int[] Tile { get; set; }

        /// <summary>门类型字符串（`GameLocation.doors` 的值，例如 <c>"Farmhouse"</c>）。</summary>
        [JsonPropertyName("type")] public string Type { get; set; }
    }

    /// <summary>
    /// 单件家具的诊断视图（快照 v4 新增，仅 `detail=full`）。
    ///
    /// 字段口径：
    ///   * `tile`   —— `Furniture.TileLocation`（家具原点所在格，世界格坐标）；
    ///   * `bbox`   —— `Furniture.GetBoundingBox()` 的像素矩形 `[x, y, w, h]`（**世界像素**，
    ///                 多格家具的宽高按格数放大，例：2x2 的床就是 128x128）；
    ///   * `passable` —— **游戏自己的** `f.isPassable()`。这才是"能不能踩上去"的权威答案；
    ///   * `ground`   —— `f.isGroundFurniture()`（地面类家具，如地毯）。⚠️ 1.6.15 上它**是方法**，
    ///                 当属性写会 CS0428（编译期实证）；
    ///   * `blocking` —— 本桥的最终判定（与 `Skills.SafeStandable` 同口径）：
    ///                 `isBed || !passable`。**`isBed` 单独列出来**是因为床是特例：
    ///                 它可踩（`passable` 可能为 true）但会触发睡觉确认框冻结世界时间，故显式拒绝；
    ///   * `type` / `name` —— 类名（如 `BedFurniture` / `Furniture`）与可读名。
    ///     `name` 取 `DisplayName`（失败则退回 `Name`，再失败为 null）；
    ///   * `bedCells` —— **仅 `isBed`**：睡觉触发格候选（`TouchAction == "Sleep"`），
    ///     见属性注释；非床为 null。踩 <see cref="Tile"/> 或 `interact(床)` 都不会引出睡觉提问。
    /// </summary>
    internal sealed class FurnitureView    {
        [JsonPropertyName("tile")] public int[] Tile { get; set; }
        [JsonPropertyName("bbox")] public int[] Bbox { get; set; }
        [JsonPropertyName("passable")] public bool Passable { get; set; }
        [JsonPropertyName("ground")] public bool Ground { get; set; }
        [JsonPropertyName("isBed")] public bool IsBed { get; set; }

        /// <summary>本桥的阻挡判定（`isBed || !passable`），与 move_to 的前置检查同口径。</summary>
        [JsonPropertyName("blocking")] public bool Blocking { get; set; }

        [JsonPropertyName("type")] public string Type { get; set; }
        [JsonPropertyName("name")] public string Name { get; set; }

        /// <summary>
        /// `isBed` 家具的**睡觉触发格**（1.6.15 里 `TouchAction == "Sleep"` 的那格；
        /// 依据 `docs/_il-bed-interaction.md` §2.2/§2.6）。
        ///
        /// 【为什么单独给这一项】真机实测（`logs\probe-bed-recipe-run1.log`）：睡觉提问**只能**由玩家踩到
        /// 这格引出（`GameLocation.UpdateWhenCurrentLocation → performTouchAction("Sleep")`），
        /// 而它不是 <see cref="Tile"/>（床原点，本存档 (9,8) —— 踩它什么都不会发生，`interact` 也是静默 no-op）。
        /// 触发格由 `bedTileOffset ∈ {0,1}` 决定且**逐帧可能翻转**（`BedFurniture.UpdateBedTile`），
        /// 所以这里给的是**候选集合**（最多两格），由脑侧现算/逐个试。
        ///
        /// * 正常路径：用游戏自己的 `doesTileHaveProperty(x, y, "TouchAction", "Back") == "Sleep"`
        ///   在床 bbox 里现算（权威，不受 offset 翻转影响）；
        /// * 读不到/空表：非床家具为 `null`；床保留 `null` 时脑侧退回 `[[x, y+1], [x+1, y+1]]` 两个候选槽位。
        /// </summary>
        [JsonPropertyName("bedCells")] public int[][] BedCells { get; set; }
    }

    internal sealed class FarmView
    {
        [JsonPropertyName("loaded")] public bool Loaded { get; set; }
        [JsonPropertyName("hoeDirt")] public int HoeDirt { get; set; }
        [JsonPropertyName("emptyDirt")] public int EmptyDirt { get; set; }
        [JsonPropertyName("crops")] public int Crops { get; set; }
        [JsonPropertyName("ripeCrops")] public int RipeCrops { get; set; }
        /// <summary>
        /// ⚠️ **这不是"今天还没浇水的作物格数"**：它数的是 `HoeDirt.needsWatering()`
        /// （只读 `CropData.NeedsWatering`、**完全不看是否已经浇过水**，IL 定案见 `docs\_analyze-farmcounts.md`），
        /// 所以一整天几乎不变（run2 实测 31→32）。要判"今天的作物浇完了没有"必须用 <see cref="DryCrops"/>。
        /// </summary>
        [JsonPropertyName("unwateredCrops")] public int UnwateredCrops { get; set; }

        /// <summary>
        /// **有作物且当前没有浇水**的耕地格数（farm-wide 真值：判据 = `HoeDirt.crop != null &amp;&amp; !HoeDirt.isWatered()`，
        /// 与逐格 `tiles[].watered` 是同一个 `isWatered()`）。`dryCrops == 0` 才等于"今天所有作物都浇过了"。
        /// 只在 <see cref="Complete"/> == true（整场 Farm 分帧扫描跑完）时可信。
        /// </summary>
        [JsonPropertyName("dryCrops")] public int DryCrops { get; set; }
        [JsonPropertyName("weeds")] public int Weeds { get; set; }
        [JsonPropertyName("stones")] public int Stones { get; set; }
        [JsonPropertyName("twigs")] public int Twigs { get; set; }
        [JsonPropertyName("trees")] public int Trees { get; set; }
        [JsonPropertyName("grass")] public int Grass { get; set; }
        [JsonPropertyName("sprinklers")] public int Sprinklers { get; set; }
        [JsonPropertyName("machinesTotal")] public int MachinesTotal { get; set; }
        [JsonPropertyName("machinesReady")] public int MachinesReady { get; set; }
        [JsonPropertyName("animals")] public int Animals { get; set; }

        /// <summary>统计是否已经跑完一整轮（分帧累计）。summary 也带这个字段，方便“脑”判断数字新不新。</summary>
        [JsonPropertyName("complete")] public bool Complete { get; set; }

        /// <summary>该轮统计开始时的 worldSeq。complete=false 时这些数字是上一轮的值。</summary>
        [JsonPropertyName("scanSeq")] public long ScanSeq { get; set; }

        /// <summary>仅 detail=full|tiles 时出现。TODO(P2)：实现分区域地块导出（当前为占位空数组）。</summary>
        [JsonPropertyName("tiles")] public object[] Tiles { get; set; }
    }

    internal sealed class UiView
    {
        /// <summary>当前 <c>Game1.activeClickableMenu</c> 的类型名；没有菜单时为 null。</summary>
        [JsonPropertyName("activeMenu")] public string ActiveMenu { get; set; }

        [JsonPropertyName("isModal")] public bool IsModal { get; set; }
        [JsonPropertyName("eventUp")] public bool EventUp { get; set; }

        /// <summary>
        /// <c>Game1.onScreenMenus.Count</c>。
        /// ⚠️ 这**不是**“对话框数量”：onScreenMenus 是常驻 HUD（时钟、体力条、金钱、任务提示等），
        /// 实测恒为 4。v1 的 dialogsOnScreen 字段名误导过“脑”，v2 已改名。
        /// </summary>
        [JsonPropertyName("onScreenMenus")] public int OnScreenMenus { get; set; }

        /// <summary>
        /// 模态里能读到的文字：
        ///   * DialogueBox 打开 → <c>getCurrentString()</c>（例："go to sleep for the night?"）；
        ///   * 其它菜单打开   → 该菜单的类型名（例："GameMenu"）；
        ///   * 没有菜单       → null（按全局约定，该字段会被省略）。
        /// </summary>
        [JsonPropertyName("activeMenuText")] public string ActiveMenuText { get; set; }

        /// <summary>对话框选项文本（<c>responses[i].responseText</c>）。没有对话框时为空数组。</summary>
        [JsonPropertyName("dialogueResponses")] public string[] DialogueResponses { get; set; }

        /// <summary>当前对话框是不是“提问”（需要玩家选 Yes/No 之类）。</summary>
        [JsonPropertyName("dialogueIsQuestion")] public bool DialogueIsQuestion { get; set; }

        /// <summary>
        /// `LevelUpMenu` 的职业候选 id（索引 0 = 左框、索引 1 = 右框；公式与 id 表见
        /// `docs\_il-profession.md` §2/§3）。**只在当前菜单是 `LevelUpMenu` 且反射读成功时出现**：
        ///   * **空数组** ⇒ 普通升级弹窗（这一级没有职业可选）⇒ 脑可以放心 dismiss；
        ///   * **非空**   ⇒ 职业选择弹窗：`exitThisMenu()` 会永久丢掉这次选择（不可逆）
        ///                  ⇒ 脑**必须不 dismiss**，记证 + 当天停下等人（user 已拍板 Tiller/Artisan 路线）；
        ///   * **字段缺失** ⇒ 读不到候选（旧 Mod 或字段改名）⇒ 脑按“未知”处理，一样不 dismiss（fail-safe）。
        /// </summary>
        [JsonPropertyName("professionsToChoose")] public int[] ProfessionsToChoose { get; set; }
    }

    internal sealed class LivenessView
    {
        [JsonPropertyName("worldAdvancing")] public bool WorldAdvancing { get; set; }
        [JsonPropertyName("secondsSinceClockMoved")] public double SecondsSinceClockMoved { get; set; }
    }

    // ==================================================================
    //  POST /v1/exec
    // ==================================================================

    /// <summary>执行请求正文。</summary>
    internal sealed class ExecRequest
    {
        [JsonPropertyName("skill")] public string Skill { get; set; }
        [JsonPropertyName("args")] public ExecArgs Args { get; set; }
        [JsonPropertyName("timeout_ms")] public int? TimeoutMs { get; set; }
        [JsonPropertyName("based_on_seq")] public long? BasedOnSeq { get; set; }
    }

    internal sealed class ExecArgs
    {
        /// <summary>move_to / move_to_location 的目标格 [x, y]。</summary>
        [JsonPropertyName("tile")] public int[] Tile { get; set; }

        /// <summary>
        /// <c>move_to_location</c> 专用：目标**地点名**（如 <c>"Farm"</c>）。
        ///
        /// 【硬约束】这个字符串只用来**在游戏真值里查表**（<c>Game1.locations[i].Name</c> 与各条 warp 的
        /// <c>TargetName</c>），大小写不敏感匹配后取图上的规范名。
        /// 它**绝不会**用来拼坐标、查表下标或硬编码路线 —— 路线一律由地点图上的 BFS 得出（§5.2.1）。
        /// </summary>
        [JsonPropertyName("location")] public string Location { get; set; }

        /// <summary>
        /// move_to 专用：是否**显式放行床格**（默认 <c>false</c>）。
        ///
        /// 【为什么要默认拦、又要能放行】床（<see cref="StardewValley.Objects.BedFurniture"/>）
        /// 可以踩，但踩上去会弹 "Go to sleep for the night?"，答错/半途关闭会把世界卡住
        /// （条目 013 的真实事故）。无人值守时这属于**破坏性副作用**，必须默认拦住；
        /// 但测试 <c>dismiss_modal</c> 时需要**故意**走到床上把弹窗引出来，所以留一个显式开关。
        /// 放行是**调用方主动声明**的，成功回执的 reason 里会写明"本次放了床"以便事后审计。
        /// </summary>
        [JsonPropertyName("allow_bed")] public bool AllowBed { get; set; }

        /// <summary>
        /// <c>use_tool</c> 专用：要用哪把工具（<c>axe</c> / <c>pickaxe</c> / <c>hoe</c> / <c>can</c> /
        /// <c>scythe</c> / <c>auto</c>）。
        ///
        /// 省略或 <c>auto</c> 时由 Mod 按目标格上的东西自动挑（树枝→斧、可敲石头→镐、杂草/草→镰刀、
        /// 空耕地→锄、有作物的耕地→水壶），并在回执里**报出真实用的那件物品名**。
        /// **不允许**脑用工具名去猜 ItemId —— 一切以回执报出的实际物品为准（真机可审计）。
        /// </summary>
        [JsonPropertyName("tool")] public string Tool { get; set; }

        /// <summary>select_item 专用：要找的物品（ItemId / QualifiedItemId / 名字，大小写不敏感）。</summary>
        [JsonPropertyName("item")] public string Item { get; set; }

        /// <summary>plant 专用：要种下的种子 ItemId（例 472 = 防风草种子）。</summary>
        [JsonPropertyName("seed")] public string Seed { get; set; }

        /// <summary>
        /// <c>load_save</c> 专用：要读的**存档文件夹名**（例如 <c>"Wahaha_450799035"</c>）。
        ///
        /// 省略时由 Mod 自己挑**最近写过**的存档（见 <see cref="LoadSaveSkill"/>）。
        /// 名字只在 <c>Constants.SavesPath</c> 下做**存在性校验**，不参与拼路径之外的任何逻辑。
        /// </summary>
        [JsonPropertyName("save")] public string Save { get; set; }

        /// <summary>
        /// <c>load_save</c> 专用：当前**已经**在存档里时，是否仍然强行读档（默认 <c>false</c>）。
        ///
        /// 读档会直接丢掉当天进度（游戏只在睡觉时落盘），属于破坏性副作用，
        /// 所以与 <c>move_to</c> 的 <c>allow_bed</c> 同一条纪律：必须调用方显式声明。
        /// </summary>
        [JsonPropertyName("force")] public bool Force { get; set; }

        /// <summary>
        /// <c>buy</c> 专用：想买几个（默认 1）。这是**请求量**，不是承诺量：
        /// Mod 会用「钱够几个 / 库存剩几个 / 单个堆叠上限」把它夹小，再由游戏自己的购买函数
        /// 做最终裁决（钱不够时游戏会整体拒绝，不会扣一半）。回执里报出**实际成交数**。
        /// </summary>
        [JsonPropertyName("count")] public int? Count { get; set; }

        /// <summary>
        /// <c>buy</c> 专用：商店 id（默认 <c>"SeedShop"</c> = 皮埃尔杂货店，卖防风草种子等）。
        /// 与 <c>args.location</c> 同一条纪律：这个字符串只交给游戏自己的
        /// <c>Utility.TryOpenShopMenu(shopId, ...)</c> 去查 <c>Data/Shops</c>，Mod 不解析它。
        /// </summary>
        [JsonPropertyName("shop")] public string Shop { get; set; }

        /// <summary>
        /// <c>sell</c> 专用：要出货的**背包槽位下标**（task-42）。
        ///
        /// 【为什么必须给槽位而不是物品名】`Farm.shipItem(item, who)` 内部的
        /// `Farmer.removeItemFromInventory` 用的是 `Items.IndexOf(which)`（**引用相等**）⇒
        /// 必须把**背包里那个实例**交出去；脑侧只报"要卖什么名字"，Mod 就必须反过来在背包里
        /// 找"第一件同名的"——那可能不是脑想卖的那一件（品质/堆叠不同）。槽位是唯一无歧义的指认。
        /// </summary>
        [JsonPropertyName("slot")] public int? Slot { get; set; }

        /// <summary>
        /// <c>sell</c> 专用：**白名单**（`QualifiedItemId`，如 `(O)24`、`(O)472`）。
        ///
        /// 【纪律】只做**允许列表**，绝不做"除了工具都能卖"的黑名单：脑侧只把
        /// `harvest()` 当天亲眼见过"进了背包"的 qualifiedId 放进来；空数组 = 一件都不许卖
        /// （Mod 直接拒绝），避免"上游 bug 把种子/工具卖了"。
        /// </summary>
        [JsonPropertyName("sellWhitelist")] public string[] SellWhitelist { get; set; }
    }

    /// <summary>
    /// 执行结果。除 ok 外，所有可空字段在不适用的技能上不输出。
    ///
    /// 【全局约定 v2】值为 <c>null</c> 的字段会被序列化时**省略**（JsonIgnoreCondition.WhenWritingNull），
    /// 因此 Python 侧必须按“字段可能缺失”解析，不能假设字段一定存在。
    /// </summary>
    internal sealed class ExecResponse
    {
        [JsonPropertyName("ok")] public bool Ok { get; set; }
        [JsonPropertyName("status")] public string Status { get; set; }
        [JsonPropertyName("skill")] public string Skill { get; set; }
        [JsonPropertyName("reason")] public string Reason { get; set; }
        [JsonPropertyName("schema")] public string Schema { get; set; }
        [JsonPropertyName("elapsedMs")] public long? ElapsedMs { get; set; }
        [JsonPropertyName("worldSeqBefore")] public long? WorldSeqBefore { get; set; }
        [JsonPropertyName("worldSeqAfter")] public long? WorldSeqAfter { get; set; }

        /// <summary>
        /// 本次动作**是否顺带打开了模态**（默认 false；只有 move_to 会置 true）。
        /// 真机场景：走到床边会“成功到达”，但同时弹出 “go to sleep for the night?” 对话框，
        /// 整个世界时间随之冻结。脑必须知道“到达了，但副作用是弹窗”，否则会以为一切正常。
        /// </summary>
        [JsonPropertyName("uiOpened")] public bool UiOpened { get; set; }

        /// <summary>若 uiOpened=true，这里是模态里的文字（同 ui.activeMenuText 的口径）。</summary>
        [JsonPropertyName("activeMenuText")] public string ActiveMenuText { get; set; }

        /// <summary>
        /// v2（exec schema）新增，**dismiss_modal 专用**，默认 `true`：
        /// 关掉模态之后世界是否真的恢复可控 —— 同一 tick 内 `player.CanMove==true`
        /// **且** `Context.IsPlayerFree==true`。
        ///
        /// 【为什么必须区分“菜单关了”与“世界恢复了”】真机事故：dismiss_modal 报“已关闭对话框”，
        /// 随后时钟冻死、角色永久不能动（`exitThisMenu()` 不复位 `player.CanMove`，
        /// 而 `shouldTimePass()` 在 CanMove=false 时恒为 false）。
        /// 因此 `worldResumed=false` 时 `ok` 也是 `false`、`status="world_stuck"`，
        /// 脑必须据此升级处理（重启游戏），**不得**当成普通成功。
        /// 其它技能恒为 `true`（本字段对它们无意义，可忽略）。
        /// </summary>
        [JsonPropertyName("worldResumed")] public bool WorldResumed { get; set; } = true;

        // ------------------------------------------------------------------
        //  里程碑 B（move_to_location）新增：成功/失败都给的“可审计行程单”
        //
        //  全局约定不变：值为 null 时字段被**省略**，所以别的技能的回执形状完全不变。
        // ------------------------------------------------------------------

        /// <summary>
        /// 实际走过的地点序列（含起点），例如 <c>["FarmHouse","Farm"]</c>。
        /// 只记**观测到的事实**（<c>Game1.currentLocation.Name</c> 的变化），不记计划。
        /// </summary>
        [JsonPropertyName("path")] public string[] Path { get; set; }

        /// <summary>每一跳的明细。失败时也会给出已经走过的跳，便于脑看到“走到哪一步断的”。</summary>
        [JsonPropertyName("hops")] public HopView[] Hops { get; set; }

        /// <summary>回执落账那一刻**真实观测到**的地点名（<c>Game1.currentLocation.Name</c>）。</summary>
        [JsonPropertyName("reachedLocation")] public string ReachedLocation { get; set; }

        /// <summary>
        /// <c>load_save</c> 专用：真正被读进来的**存档文件夹名**（失败时也给，便于审计）。
        /// 【可选字段】null 时序列化省略，因此老客户端读到的响应形状不变。
        /// </summary>
        [JsonPropertyName("save")] public string Save { get; set; }

        /// <summary>
        /// <c>load_save</c> 专用：读档完成后玩家所在格 [x, y]。
        /// 【可选字段】null 时序列化省略。
        /// </summary>
        [JsonPropertyName("tile")] public int[] Tile { get; set; }
    }

    /// <summary>
    /// <c>move_to_location</c> 的一跳明细。
    ///
    /// 【为什么 to 与 arrivedAt 要分开】<c>to</c> 是**地图上写的**（warp 的 <c>TargetName</c>），
    /// <c>arrivedAt</c> 是**实际观测到的**（<c>Game1.currentLocation.Name</c>）。
    /// 两者不一致时 <c>result="mismatch"</c> —— 这是给脑审计用的：
    /// 本实现从不拿"地图上写的目标"冒充"到了"，判据只有后者。
    /// </summary>
    internal sealed class HopView
    {
        /// <summary>这一跳从哪个地点出发（出发时的观测值）。</summary>
        [JsonPropertyName("from")] public string From { get; set; }

        /// <summary>这一跳打算去哪（warp 的 <c>TargetName</c>）。</summary>
        [JsonPropertyName("to")] public string To { get; set; }

        /// <summary>实际观测到的落地地点名；失败时为出发地点。</summary>
        [JsonPropertyName("arrivedAt")] public string ArrivedAt { get; set; }

        /// <summary>计划使用的 warp **源格**（本地点内，warp 的 X/Y）。</summary>
        [JsonPropertyName("sourceTile")] public int[] SourceTile { get; set; }

        /// <summary>地图上写的**落点格**（目标地点内，warp 的 TargetX/TargetY；仅供参考）。</summary>
        [JsonPropertyName("landingTile")] public int[] LandingTile { get; set; }

        /// <summary>实际最后走向的那个候选格（源格/穿过格/邻格），用于复盘“到底试了哪一格”。</summary>
        [JsonPropertyName("usedTile")] public int[] UsedSourceTile { get; set; }

        /// <summary>这一跳花了多少毫秒。</summary>
        [JsonPropertyName("ms")] public long Ms { get; set; }

        /// <summary>ok / mismatch / hop_failed / blocked / timeout / unreachable / ui_modal / error。</summary>
        [JsonPropertyName("result")] public string Result { get; set; }

        /// <summary>失败或 mismatch 时的可操作说明。</summary>
        [JsonPropertyName("detail")] public string Detail { get; set; }
    }

    // ==================================================================
    //  通用错误
    // ==================================================================

    internal sealed class ErrorResponse
    {
        [JsonPropertyName("ok")] public bool Ok { get; set; }
        [JsonPropertyName("status")] public string Status { get; set; }
        [JsonPropertyName("reason")] public string Reason { get; set; }
    }
}
