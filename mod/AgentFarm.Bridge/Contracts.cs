using System.Collections.Generic;
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

        // ---- 【task-155】工具升级在途状态（升级链 task-142 的前置/判据）----

        /// <summary>
        /// `Farmer.toolBeingUpgraded.Value`（正在 Clint 那里升级的工具）。`null` = 没有在途。
        /// IL 实证：`Netcode.NetRef`1[StardewValley.Tool]`（`scratch/il-155-upg2.txt`）；
        /// 买下升级时被置为该工具的副本、`daysLeftForToolUpgrade = 2`，取回时清 null。
        /// </summary>
        [JsonPropertyName("toolBeingUpgraded")] public ToolItemView ToolBeingUpgraded { get; set; }

        /// <summary>`Farmer.daysLeftForToolUpgrade.Value`（`NetInt`）。`null` = 读不到。</summary>
        [JsonPropertyName("toolUpgradeDaysLeft")] public int? ToolUpgradeDaysLeft { get; set; }

        /// <summary>
        /// `Farmer.hasReceivedToolUpgradeMessageYet`（`bool` 公共字段）：工具升级好了的提示是否已弹过。
        /// `null` = 读不到。
        /// </summary>
        [JsonPropertyName("toolUpgradeNotice")] public bool? ToolUpgradeNotice { get; set; }
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

    /// <summary>【task-155】`ResourceClump` 的目标工具与最低等级（`clumpTarget`）。</summary>
    internal sealed class ClumpTargetView
    {
        /// <summary>`axe` 或 `pickaxe`。</summary>
        [JsonPropertyName("tool")] public string Tool { get; set; }

        /// <summary>最低 `UpgradeLevel`；`0` = 已证无门槛。</summary>
        [JsonPropertyName("minLevel")] public int? MinLevel { get; set; }
    }

    /// <summary>
    /// 【task-155】背包里的一件工具（`tools[]` 的元素）。用来回答"我手上这把是几级"。
    /// 语义：字段缺失/`null` = 读不到（`upgradeLevel` 是 `int`，读不到时该件工具**不出现**在数组里）。
    /// </summary>
    internal sealed class ToolItemView
    {
        [JsonPropertyName("id")] public string Id { get; set; }

        [JsonPropertyName("name")] public string Name { get; set; }

        /// <summary>`axe` / `pickaxe` / `hoe` / `can` / `fishingRod` / `pan` / `other`。</summary>
        [JsonPropertyName("kind")] public string Kind { get; set; }

        /// <summary>`Tool.UpgradeLevel`（0 = 初始）。</summary>
        [JsonPropertyName("upgradeLevel")] public int UpgradeLevel { get; set; }

        [JsonPropertyName("indexOfMenuItemView")] public int? IndexOfMenuItemView { get; set; }

        [JsonPropertyName("isEquipped")] public bool IsEquipped { get; set; }

        [JsonPropertyName("stack")] public int Stack { get; set; }
    }

    internal sealed class ToolsView
    {
        [JsonPropertyName("hoe")] public bool Hoe { get; set; }
        [JsonPropertyName("axe")] public bool Axe { get; set; }
        [JsonPropertyName("pickaxe")] public bool Pickaxe { get; set; }
        [JsonPropertyName("wateringCan")] public bool WateringCan { get; set; }
        [JsonPropertyName("fishingRod")] public bool FishingRod { get; set; }
        [JsonPropertyName("weapon")] public bool Weapon { get; set; }

        /// <summary>
        /// 【task-155】背包里**每件工具**的明细（含 `upgradeLevel`）。原来的 6 个 bool 原样保留，
        /// 只加不改 —— 老读法不破；"有没有这把工具"由"它在不在数组里"承担。
        /// </summary>
        [JsonPropertyName("tools")] public List<ToolItemView> Tools { get; set; } = new List<ToolItemView>();
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

        /// <summary>
        /// **task-210 新增（仅 `detail=full`）**：`location.objects` 的**逐条台账**（机器/放置物）。
        ///
        /// 为什么必须有：在此之前 `objects` **只有计数**，脑无法回答"哪一格是熔炉、里面有没有货、
        /// 还有几分钟"——机器链（放置/投料/取货）一步都走不了。
        ///
        /// 口径：只含 `objects`（不含 terrainFeatures）；按 **(y, x) 升序**；上限 **64** 条；
        /// 超出置 `objectListTruncated=true`（**计数仍以 `objects` 为准**，台账只是"看得见的那部分"）。
        /// 三态可辨：字段缺键（旧 Mod / summary）≠ `null`（读不到）≠ `[]`（确实没有放置物）。
        /// </summary>
        [JsonPropertyName("objectList")] public ObjectEntryView[] ObjectList { get; set; }

        /// <summary>`objectList[]` 是否被截断（null/false = 完整；读不到时也为 true）。</summary>
        [JsonPropertyName("objectListTruncated")] public bool? ObjectListTruncated { get; set; }
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

    /// <summary>
    /// 【task-210】机器里正在处理/已产出的物品（`Object.heldObject.Value` 的视图）。
    ///
    /// 只回答"是什么、几个"；**坐标在外层行对象上**（本结构不重复带坐标，避免两份坐标漂移）。
    /// 三态可辨：字段缺键（旧 Mod / 非机器）、`null`（机器但当前空手 = 没有 held）、有值。
    /// </summary>
    internal sealed class HeldObjectView
    {
        /// <summary>`Item.QualifiedItemId`（例 `(O)334` 铜锭）。读不到 ⇒ null。</summary>
        [JsonPropertyName("id")] public string Id { get; set; }

        /// <summary>`Item.DisplayName`（诊断用）。读不到 ⇒ null。</summary>
        [JsonPropertyName("name")] public string Name { get; set; }

        /// <summary>`Item.Stack`。读不到 ⇒ null（**不许写 0**）。</summary>
        [JsonPropertyName("stack")] public int? Stack { get; set; }
    }

    /// <summary>
    /// 【task-210】`location.objects` 的**逐条台账行**（仅 `detail=full`，见 `location.objectList`）。
    ///
    /// 与 `tiles[]` 的分工（两张表可以不一致，别混用）：
    ///   * `tiles[]` = **作战视图**：按离玩家距离排序、上限 400、objects + terrainFeatures 混在一起；
    ///   * `objectList[]` = **台账**：只含 `objects`，按 (y, x) 排序、上限 64、带机器状态。
    /// 机器链（craft 后放置、投料、取货）挑格子用台账；清理/开垦/种植仍看 `tiles[]`。
    /// </summary>
    internal sealed class ObjectEntryView
    {
        /// <summary>格坐标 `[x, y]`（按 (y, x) 升序排列）。</summary>
        [JsonPropertyName("tile")] public int[] Tile { get; set; }

        /// <summary>`Item.ItemId`（例 `114`；机器/箱子等）。读不到 ⇒ null。</summary>
        [JsonPropertyName("objId")] public string ObjId { get; set; }

        /// <summary>`Item.DisplayName`（诊断用）。读不到 ⇒ null。</summary>
        [JsonPropertyName("name")] public string Name { get; set; }

        /// <summary>`Object.bigCraftable.Value`（大件 = 放下去的家具/机器）。读不到 ⇒ null。</summary>
        [JsonPropertyName("bigCraftable")] public bool? BigCraftable { get; set; }

        /// <summary>机器里当前的东西（空 ⇒ 字段缺键或 null，见 <see cref="HeldObjectView"/>）。</summary>
        [JsonPropertyName("heldObject")] public HeldObjectView HeldObject { get; set; }

        /// <summary>
        /// `Object.readyForHarvest.Value`（`NetBool` 字段，不是方法）。
        /// **null = 判不了 / 不是机器**；`false` 是"确实是机器但没好"。
        /// </summary>
        [JsonPropertyName("readyForHarvest")] public bool? ReadyForHarvest { get; set; }

        /// <summary>
        /// `Object.MinutesUntilReady`（游戏自己的"还要几分钟"）。读不到 / 非机器 ⇒ null。
        /// ⚠️ 数值只是**游戏内分钟**，不等于墙钟；机器时间只在游戏时间推进时走。
        /// </summary>
        [JsonPropertyName("minutesUntilReady")] public int? MinutesUntilReady { get; set; }
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

        // ---- 【task-155】ResourceClump（大障碍）结构化元数据（只有 `kind="clump"` 时才填）----

        /// <summary>
        /// `ResourceClump.parentSheetIndex.Value`（600 树桩 / 602 大木头 / 672 巨石 / 148、622 石堆 /
        /// 752+ 绿雨那支）。读不到 ⇒ `null`（**不许写 0**）。
        /// </summary>
        [JsonPropertyName("clumpIndex")] public int? ClumpIndex { get; set; }

        /// <summary>`ResourceClump.width.Value`（占几格宽）。读不到 ⇒ `null`。</summary>
        [JsonPropertyName("clumpWidth")] public int? ClumpWidth { get; set; }

        /// <summary>`ResourceClump.height.Value`（占几格高）。读不到 ⇒ `null`。</summary>
        [JsonPropertyName("clumpHeight")] public int? ClumpHeight { get; set; }

        /// <summary>`ResourceClump.health.Value`（当前血量，诊断/进度用）。读不到 ⇒ `null`。</summary>
        [JsonPropertyName("clumpHealth")] public float? ClumpHealth { get; set; }

        /// <summary>
        /// 障碍种类：`stump` / `log` / `boulder` / `rockPile` / `greenRain` / `unknown`。
        /// `unknown` **必须显式出现**（未知索引绝不许静默并进 `stones`）。
        /// </summary>
        [JsonPropertyName("clumpKind")] public string ClumpKind { get; set; }

        /// <summary>
        /// 清掉这一格需要什么工具与最低等级（由 `clumpIndex` 推导，见 `ClumpMeta`）。
        /// `null` = 判不了（未知索引）⇒ 调用方**不许猜**（禁默认斧头/默认 0）。
        /// `minLevel == 0` = 已证**无等级门槛**（与 `null` 语义不同）。
        /// </summary>
        [JsonPropertyName("clumpTarget")] public ClumpTargetView ClumpTarget { get; set; }

        /// <summary>
        /// 当前玩家手上这把工具的 `UpgradeLevel` 是否 ≥ `clumpTarget.minLevel`。
        /// `null` = **判不了**（没有该工具 / 等级读不到 / `clumpTarget` 未知）；与 `false` 语义不同。
        /// </summary>
        [JsonPropertyName("toolOk")] public bool? ToolOk { get; set; }

        /// <summary>select_item 专用：要找的物品（ItemId / QualifiedItemId / 名字，大小写不敏感）。</summary>
        [JsonPropertyName("item")] public string Item { get; set; }

        /// <summary>plant 专用：要种下的种子 ItemId（例 472 = 防风草种子）。</summary>
        [JsonPropertyName("seed")] public string Seed { get; set; }

        /// <summary>`objects` 里那一项的 `ItemId`（没有则为 null）。</summary>
        [JsonPropertyName("objId")] public string ObjId { get; set; }

        // ---- 【task-210】机器状态（只有 `kind="object"` 且该格是机器时才填）----
        //
        //  数据面全部问游戏自己（`Object.GetMachineData()` 判"是不是机器"然后读
        //  `heldObject`/`readyForHarvest`/`MinutesUntilReady`），不硬编码任何 id/分钟数。
        //  非机器（箱子/杂草/石头…）三个字段都保持 null ⇒ 脑不会把箱子当熔炉。

        /// <summary>
        /// 机器里当前的东西（`Object.heldObject.Value`）。**null = 没有 / 不是机器**（见 `HeldObjectView`）。
        /// </summary>
        [JsonPropertyName("heldObject")] public HeldObjectView HeldObject { get; set; }

        /// <summary>
        /// `Object.readyForHarvest.Value`（**NetBool 字段**，不是方法；task-211 IL 定案）。
        /// **null = 判不了 / 不是机器**；`false` = 确实是机器但还没好。
        /// </summary>
        [JsonPropertyName("readyForHarvest")] public bool? ReadyForHarvest { get; set; }

        /// <summary>`Object.MinutesUntilReady`（游戏内分钟；只在游戏时间推进时走）。null = 判不了 / 非机器。</summary>
        [JsonPropertyName("minutesUntilReady")] public int? MinutesUntilReady { get; set; }

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

        // ------------------------------------------------------------------
        //  【task-170】作物"能不能收"的游戏口径 + 子形态判别量
        //
        //  run A/B 事故：旧 `ripe` = 裸 `Crop.fullyGrown`，而游戏给收的判据是
        //  `HoeDirt.readyForHarvest()` ⇒ `(60,29)` 跨 8 个游戏日恒 `ripe=true`、284 次尝试 0 成功。
        //  `ripe` **保留原义**（历史字段，勿当判据）；`ready` 才是权威口径，
        //  判不了时是 **null（不是 false）**。
        // ------------------------------------------------------------------

        /// <summary>
        /// 【task-170】**游戏口径**的"现在可收"= `HoeDirt.readyForHarvest()`
        /// （等价实现见 `CropMeta.Ready`）。没有作物 / 不是耕地 / 判据缺项 ⇒ **null（判不了）**。
        /// 脑侧只许用它选收获目标（fail-closed：null ⇒ 不摘）。
        /// </summary>
        [JsonPropertyName("ready")] public bool? Ready { get; set; }

        /// <summary>
        /// 【task-176】**这个 `ready` 是谁给的**：`"game"` = 真的调用了游戏自己的
        /// `HoeDirt.readyForHarvest()`；`"fields"` = 反射不可用、退回**与该方法 IL 逐条等价**的
        /// 字段判据；`null` = 判不了（此时 `ready` 也是 null）。
        ///
        /// 为什么要落账：task-173 在真机上看到 `readyCrops == crops == 102`，但**分不清**
        /// 那是"游戏真说全都能收"还是"我们的兜底判据把不能收的也判成能收" —— 没有来源标记，
        /// 这条缺陷永远定不了案。**键必须总是输出**（null 也输出），所以显式关掉全局的
        /// `WhenWritingNull`（见文件头 `DefaultIgnoreCondition`）。
        /// </summary>
        [JsonPropertyName("readySource")]
        [JsonIgnore(Condition = JsonIgnoreCondition.Never)]
        public string ReadySource { get; set; }

        /// <summary>裸 `Crop.fullyGrown`（历史字段；**不要**拿它当"可收"判据）。</summary>
        [JsonPropertyName("fullyGrown")] public bool? FullyGrown { get; set; }

        /// <summary>
        /// `Crop.GetHarvestMethod().ToString()`：`"Grab"` / `"Scythe"` / 其它；判不了 ⇒ **null**。
        ///
        /// 【task-176 必修 ①】入口是**公开方法 `Crop.GetHarvestMethod()`**（api-probe IL：
        /// `GetData()` 为 null ⇒ `0`(Grab)，否则 `CropData.HarvestMethod`；调用者 =
        /// `HoeDirt.performUseAction`/`performToolAction`）—— 旧实现按**字段名**读，1.6.15 上
        /// 根本没这个字段 ⇒ 恒 null ⇒ `Scythe` 类作物被当成 `Grab` 走 `interact` ⇒ **永远摘不到**。
        /// `Scythe` ⇒ 只能走**工具路径**（`interact` 永远摘不到）。
        /// **键必须总是输出**（null 也输出，缺键 ≠ null —— 真机事故正是被"缺键"掩盖的）。
        /// </summary>
        [JsonPropertyName("harvestMethod")]
        [JsonIgnore(Condition = JsonIgnoreCondition.Never)]
        public string HarvestMethod { get; set; }

        /// <summary>`Crop.currentPhase`（没有作物 / 读不到 ⇒ null）。</summary>
        [JsonPropertyName("currentPhase")] public int? CurrentPhase { get; set; }

        /// <summary>`Crop.phaseDays.Count`（没有作物 / 读不到 ⇒ null）。</summary>
        [JsonPropertyName("phaseDays")] public int? PhaseDays { get; set; }

        /// <summary>`Crop.dayOfCurrentPhase`（复收冷却期 &gt; 0；没有作物 / 读不到 ⇒ null）。</summary>
        [JsonPropertyName("dayOfCurrentPhase")] public int? DayOfCurrentPhase { get; set; }

        /// <summary>`Crop.forageCrop`（采集作物；没有作物 / 读不到 ⇒ null）。</summary>
        [JsonPropertyName("forageCrop")] public bool? ForageCrop { get; set; }

        /// <summary>`Crop.whichForageCrop`（采集作物形态 `"2"` 游戏不给收；读不到 ⇒ null）。</summary>
        [JsonPropertyName("whichForageCrop")] public string WhichForageCrop { get; set; }

        /// <summary>`Crop.RegrowsAfterHarvest()`（复收作物；读不到 ⇒ null）。</summary>
        [JsonPropertyName("regrowsAfterHarvest")] public bool? RegrowsAfterHarvest { get; set; }

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
        /// 【task-170】**游戏口径**的可收作物格数（`HoeDirt.readyForHarvest()`，等价实现
        /// `CropMeta.Ready`），与逐格 `tiles[].ready` 同源。`ripeCrops`（裸 `Crop.fullyGrown`）
        /// 保留作历史字段 —— run A/B 284 次 0 成功就是拿它当"可收"判据的后果。
        /// </summary>
        [JsonPropertyName("readyCrops")] public int ReadyCrops { get; set; }

        /// <summary>
        /// **枯死作物格数**（farm-wide 真值，与 <see cref="Crops"/>/<see cref="RipeCrops"/> **同一次扫描口径**：
        /// `HoeDirt.crop != null &amp;&amp; Crop.dead.Value`）。枯死苗占着耕地、挡着 `till`（脑侧
        /// `till_blocked_by` 见到 crop 就拒），必须先清掉才能重种（task-51）。
        ///
        /// 【为什么是计数而不是坐标】与 <see cref="DryCrops"/>/<see cref="DryTiles"/> 不同：清死苗是
        /// **一次性**动作，脑侧先用计数决定"今天要不要开 `clear_dead` 阶段"，逐格坐标仍走
        /// 玩家窗口 `location.tiles[].dead`（Mod 侧 `ReadTile` 早就在给）。若将来出现"窗口外还有死苗"
        /// 导致清不完，再按 task-50 的 dryTiles 模式补坐标（本卡不做）。
        ///
        /// ⚠️ 旧 Mod 无此字段 ⇒ JSON 里为 null：脑侧**不许把"没这个字段"当成 0**（那是"不知道"）。
        /// 只在 <see cref="Complete"/> == true（整场 Farm 分帧扫描跑完）时可信。
        /// </summary>
        [JsonPropertyName("deadCrops")] public int DeadCrops { get; set; }
        /// <summary>
        /// ⚠️ **这不是"今天还没浇水的作物格数"**：它数的是 `HoeDirt.needsWatering()`
        /// （只读 `CropData.NeedsWatering`、**完全不看是否已经浇过水**，IL 定案见 `docs\_analyze-farmcounts.md`），
        /// 所以一整天几乎不变（run2 实测 31→32）。要判"今天的作物浇完了没有"必须用 <see cref="DryCrops"/>。
        /// </summary>
        [JsonPropertyName("unwateredCrops")] public int UnwateredCrops { get; set; }

        /// <summary>
        /// **有活苗且当前没有浇水**的耕地格数（farm-wide 真值：判据 =
        /// `HoeDirt.crop != null &amp;&amp; !Crop.dead &amp;&amp; !HoeDirt.isWatered()`，
        /// 与逐格 `tiles[].watered` 是同一个 `isWatered()`）。`dryCrops == 0` 才等于"今天所有活苗都浇过了"。
        ///
        /// 【task-84 收窄】枯死作物**不再计入本字段**（它们不需要浇水，用户 m11003：死苗还在被浇）。
        /// 死苗的干格数见 <see cref="DryDeadCrops"/>。这条收窄同时修掉了 run7 的一个死锁：
        /// `tools/verify-run3.py` 的闸门"`ended_reason` 以 `no_work` 开头 ⇒ `final_water.dry` 必须为 0"
        /// 在死苗清完之前**永远不可能满足**（旧口径把死苗混进"该浇水"），导致 summer 3/5/6 三天损失。
        /// 只在 <see cref="Complete"/> == true（整场 Farm 分帧扫描跑完）时可信。
        /// </summary>
        [JsonPropertyName("dryCrops")] public int DryCrops { get; set; }

        /// <summary>
        /// **干作物格的坐标**（`[[x, y], …]`）。坐标是**农场地图格坐标**，与 <see cref="DryCrops"/>
        /// 同一次扫描口径（**只含活苗**：`HoeDirt.crop != null &amp;&amp; !Crop.dead &amp;&amp; !HoeDirt.isWatered()`）。
        ///
        /// 【为什么需要】脑侧能看到的只有玩家周围最近的 400 格（`location.tiles[]`，
        /// 且带 `tilesTruncated=true`），农场另一头那 1 格干作物既看不到也没坐标
        /// ⇒ run5 三天 `final_water.dry` 恒为 1、`watered_outdoor=false`（task-50）。
        ///
        /// 【task-84 收窄】死苗坐标**不再出现在这里**（旧口径 task-50 曾刻意"死苗也算"，run7 证明那会让
        /// 脑整天追一个不该浇的格）。死苗只给计数 <see cref="DryDeadCrops"/>，逐格死苗仍走玩家窗口
        /// `location.tiles[].dead`；要不要清死苗走 task-51 的 `clear_dead`。
        ///
        /// 排序：先 `y` 再 `x`（确定性，便于测试与人工核对）。
        /// 上限 <see cref="FarmScanCache.DryTilesMax"/> = 64 条；超出时坐标列表截断并置
        /// <see cref="DryTilesTruncated"/> = true（**计数仍以 <see cref="DryCrops"/> 为准**）。
        /// 只在 <see cref="Complete"/> == true（整场 Farm 跑完一轮）时可信；旧 Mod 无此字段 ⇒ null。
        /// </summary>
        [JsonPropertyName("dryTiles")] public int[][] DryTiles { get; set; }

        /// <summary>
        /// **枯死作物且没有浇水的耕地格数**（farm-wide，判据 =
        /// `HoeDirt.crop != null &amp;&amp; Crop.dead &amp;&amp; !HoeDirt.isWatered()`）。task-84 新增。
        ///
        /// 【为什么单独给】死苗**不需要浇水**（`HoeDirt.performToolAction` 里死苗只有镰刀/锄头能清），
        /// 但它们会和活苗一样"干着"。只给计数、不给坐标，理由同 <see cref="DeadCrops"/>：
        /// 逐格死苗走玩家窗口 `tiles[].dead`，清不完的根治属"农场级坐标"家族。
        ///
        /// ⚠️ 旧 Mod 无此字段 ⇒ JSON 里为 null：脑侧**不许把"没这个字段"当成 0**（那是"不知道"）。
        /// 只在 <see cref="Complete"/> == true 时可信。
        /// </summary>
        [JsonPropertyName("dryDeadCrops")] public int DryDeadCrops { get; set; }

        /// <summary>
        /// <see cref="DryTiles"/> 是否因超过 64 条上限被截断。
        /// **null = 旧 Mod 没有这个字段**（脑侧此时不许把"没给坐标"当成"没有干格"）。
        /// </summary>
        [JsonPropertyName("dryTilesTruncated")] public bool? DryTilesTruncated { get; set; }

        /// <summary>
        /// **可收熟作物格的坐标**（`[[x, y], …]`）。坐标是**农场地图格坐标**，与 <see cref="ReadyCrops"/>
        /// **同一次全场扫描、同一个 `scanSeq`、同一判据**（`CropMeta.Ready`，与逐格
        /// `location.tiles[].ready` / `tiles[].readySource` 完全同源）。
        ///
        /// 【为什么需要】`readyCrops` 是农场级**计数**，而脑侧目标池来自玩家周围 400 格窗口
        /// （`location.tiles[]`，`tilesTruncated=true`）⇒ 窗口外的熟作物既看不到也没坐标，
        /// 守卫却拿 `readyCrops > 窗口熟格数` 当"还有活" ⇒ run A′ fall 13 一整天换片地空转、
        /// 最后 `stuck:同一秒连发 5 次换片都没有目标`（task-199）。
        /// 这是 task-50 给干作物补 `dryTiles` 的**同一族缺口**的补齐。
        ///
        /// 排序：先 `y` 再 `x`（与 <see cref="DryTiles"/> 一致、确定性、便于测试与人工核对）。
        /// 上限 <see cref="FarmScanCache.ReadyTilesMax"/> = 64 条；超出时坐标截断并置
        /// <see cref="ReadyTilesTruncated"/> = true（**计数仍以 <see cref="ReadyCrops"/> 为准**）。
        /// **三态可辨**：字段缺失（旧 Mod）/ `null`（本轮扫描失败）/ 空数组（真的没有熟作物格）——
        /// 所以这里用 `JsonIgnoreCondition.Never` 强制写出 `null`（全局默认是 WhenWritingNull）。
        /// 只在 <see cref="Complete"/> == true 时可信。
        /// </summary>
        [JsonPropertyName("readyTiles")]
        [JsonIgnore(Condition = JsonIgnoreCondition.Never)]
        public int[][] ReadyTiles { get; set; }

        /// <summary>
        /// <see cref="ReadyTiles"/> 是否因超过 64 条上限被截断。
        /// **null = 旧 Mod 没有这个字段**（脑侧此时不许把"没给坐标"当成"没有熟作物"）。
        /// </summary>
        [JsonPropertyName("readyTilesTruncated")] public bool? ReadyTilesTruncated { get; set; }

        [JsonPropertyName("weeds")] public int Weeds { get; set; }

        /// <summary>
        /// 普通石头（`Object` 的 `IsBreakableStone()` / `StoneIds`）。
        ///
        /// 【task-155 语义收窄】**不再包含 `ResourceClump`**：树桩/大木头/巨石/石堆/绿雨那支
        /// 以前被算进这里，导致"清空农场"的分母混淆。收窄后 `ResourceClump` 走下面分 kind 的计数。
        /// ⚠️ 与旧账本对账时 `stones` 会**变小**（树桩/大木头被移走）；不留旧别名。
        /// </summary>
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

        // ---- 【task-155】ResourceClump 按 kind 分流计数（与 `dryTiles` 同一次扫描、同一个 `scanSeq`）----

        /// <summary>`ResourceClump.parentSheetIndex == 600`（树桩，斧 ≥1）。</summary>
        [JsonPropertyName("stumps")] public int Stumps { get; set; }

        /// <summary>`== 602`（大木头，斧 ≥2）。</summary>
        [JsonPropertyName("logs")] public int Logs { get; set; }

        /// <summary>`== 672`（巨石，镐 ≥2）。</summary>
        [JsonPropertyName("boulders")] public int Boulders { get; set; }

        /// <summary>`== 148 || == 622`（石堆，镐 ≥3）。</summary>
        [JsonPropertyName("rockPiles")] public int RockPiles { get; set; }

        /// <summary>`>= 752`（绿雨那支，无等级门槛；精确索引集合未定，见 task-155 设计 §7-U3）。</summary>
        [JsonPropertyName("greenRain")] public int GreenRain { get; set; }

        /// <summary>上面五类之和 + 未归类（`clumpsUnclassified`）。</summary>
        [JsonPropertyName("clumpsTotal")] public int ClumpsTotal { get; set; }

        /// <summary>
        /// **显式"未归类"**：`ResourceClump` 存在但 `parentSheetIndex` 读不到或不在已知表里。
        /// 绝不静默并进 <see cref="Stones"/> —— 这就是 task-151/156 要的那 2 个残差。
        /// </summary>
        [JsonPropertyName("clumpsUnclassified")] public int ClumpsUnclassified { get; set; }

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

        /// <summary>
        /// <c>dismiss_modal</c> 专用（task-208）：要应答的选项**0 基下标**（对应 `ui.dialogueResponses[]`
        /// 的顺序）。与 <see cref="AnswerText"/> 互斥。
        ///
        /// 【纪律】两个都不给 ⇒ **完全保持旧行为**（自动挑否/最后一项），一行不许改；
        /// 给了但指错 ⇒ 必须失败（`choice_not_found` / `choice_ambiguous` / `no_question`），
        /// **绝不许悄悄退回自动挑 Yes** —— 那等于替人做了不可逆决定（铁匠铺升级、职业选择都是这类）。
        /// 命中后仍只走游戏自己的 `answerDialogue(Response)`（见 `ModalDismiss.AnswerWith`），
        /// 禁止注入确认键（Enter/Space 经 `Options.actionButton` 会变成点 (0,0)，睡觉链踩过）。
        /// </summary>
        [JsonPropertyName("answerIndex")] public int? AnswerIndex { get; set; }

        /// <summary>
        /// <c>dismiss_modal</c> 专用（task-208）：按**文本子串**匹配要应答的选项
        /// （大小写不敏感；**唯一命中**才算成功，多命中 ⇒ `choice_ambiguous`）。
        /// 先看 `responseText`（给玩家看的文字），再看 `responseKey`（程序化 ID）。
        /// 与 <see cref="AnswerIndex"/> 互斥；失败语义同上（fail-closed，不许退回自动挑）。
        /// </summary>
        [JsonPropertyName("answerText")] public string AnswerText { get; set; }

        // ------------------------------------------------------------------
        //  0.7.39（task-213）新增：`debug_dump` 的只读内省参数
        //
        //  为什么需要：Furnace 配方缺失卡住了整条机器链，而 `Data/CraftingRecipes`
        //  与 `Data/TriggerActions` 都在打包 xnb 里、在仓库里读不到 ⇒ 只能由 Mod 在
        //  **真机运行时**把游戏自己加载的表读出来。参数只有三个，且全部只读。
        // ------------------------------------------------------------------

        /// <summary>
        /// <c>debug_dump</c> 专用：要读的**表名**（见 <see cref="DumpRules.Tables"/>：
        /// <c>crafting_recipes</c> / <c>cooking_recipes</c> / <c>trigger_actions</c> /
        /// <c>mail</c> / <c>machines</c> / <c>objects</c> / <c>big_craftables</c>）。
        ///
        /// 【纪律】表名先经 <see cref="DumpRules.NormalizeTable"/> 归一；不认识的表 ⇒
        /// `status="table_unknown"` 并列出支持的表，**绝不**猜一个相近的表去读。
        /// </summary>
        [JsonPropertyName("table")] public string Table { get; set; }

        /// <summary>
        /// <c>debug_dump</c> 专用：可选**键过滤**。给了它 ⇒ 只回 `matched`（精确/子串两桶，
        /// 精确优先），`entries` 为空；不给 ⇒ 回前 `limit` 条 `entries`。
        /// 例：`key="Furnace"` 查 <c>crafting_recipes</c> 里的熔炉配方。
        /// </summary>
        [JsonPropertyName("key")] public string Key { get; set; }

        /// <summary>
        /// <c>debug_dump</c> 专用：最多回多少条（默认 200、上限 2000、下限 1）。
        /// 【硬要求】不许无界返回 —— 表可能有几千条，回执会撑爆 HTTP。
        /// </summary>
        [JsonPropertyName("limit")] public int? Limit { get; set; }

        // ---- 【task-210】机器链的额外参数（`item` 复用上面的通用字段）----

        /// <summary>
        /// <c>machine</c> 专用动作：`"feed"`（把 <see cref="Item"/> 投进 <see cref="Tile"/> 的机器）
        /// 或 `"collect"`（取机器的产物）。缺省/其它值 ⇒ `bad_args`（fail-closed，不许猜动作）。
        /// </summary>
        [JsonPropertyName("action")] public string Action { get; set; }
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

        /// <summary>
        /// 【task-170】技能自己报的"**是否真的做成了**"（机器可读；不适用时 null）。
        ///
        /// `interact` 专用：游戏 `checkAction` 的返回值就是"这一格有没有可执行动作"，
        /// 旧实现只看有没有抛异常（`Ok = err == null`）⇒ **游戏拒绝也报 ok**、`acted` 只写在 reason
        /// 文本里（run A/B 的"回执谎报"第三次）。现在 `acted == false` ⇒ `ok=false` + `status="no_action"`，
        /// 脑不必再靠 reason 猜。
        /// </summary>
        [JsonPropertyName("acted")] public bool? Acted { get; set; }

        /// <summary>
        /// 【task-182 必修 2】`acted` 的**证据来源**（机器可读；不适用/没命中时 null）。
        ///
        /// 取值：`"tile"` = 目标格逐字段签名（`TileSig`）变了；`"ready"` = 目标格 `ready` 由
        /// true 变 false（或 `readySource` 变化）—— 再生作物收后只有这一条会动；
        /// `"readyCrops"` = 整场 `readyCrops` 下降；`"inventory"` = 背包逐 qid 栈数有增加。
        ///
        /// 【为什么要落来源】task-177 的事故：再生作物真的收成了，Mod 却报 `acted=false`；
        /// 脑侧只能靠自己的观测差分去猜。有了这个字段，脑（task-181）与 analyzer 都能直接
        /// 对账"这一次 acted 是谁给的证据"，而不是被回执拖死。
        ///
        /// 【弱证据声明】`"inventory"` 是**全局面**证据：同一 tick 里别的系统也可能改背包，
        /// 因此判定顺序把它们分开——格子级证据（`tile`/`ready`/`readyCrops`）优先，
        /// 只有它们都不动、而背包确实长了，才记 `"inventory"`。reason 里同时写清来源。
        /// </summary>
        [JsonPropertyName("actedEvidence")] public string ActedEvidence { get; set; }

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

        // ------------------------------------------------------------------
        //  0.7.26（task-67）新增：`buy` 的"可审计货架"
        //
        //  run6 真机事故：脑把种子品种硬编码成 `472`（防风草种子，**春季**作物），
        //  夏季商店不卖 ⇒ 每天白试 6 次、`item_not_sold`，播种腿永远走不通。
        //  脑看不到 `Data/Crops`，唯一的事实来源就是**开店那一刻的货架**——
        //  所以回执必须把它结构化地带回来（成功与失败都带）。
        // ------------------------------------------------------------------

        /// <summary>
        /// <c>buy</c> 专用：开店那一刻货架上的在售清单（**按价格升序，最多 30 条**）。
        /// 成功与失败都带；`id` 是 <c>QualifiedItemId</c>（如 <c>(O)472</c>），脑直接拿它下单。
        /// 【可选字段】null 时序列化省略 ⇒ 其它技能回执形状不变。
        /// </summary>
        [JsonPropertyName("availableItems")] public ShopItemView[] AvailableItems { get; set; }

        // ------------------------------------------------------------------
        //  0.7.29（task-129）新增：`dismiss_modal` 走"出货 → 日切保存 → 换天"链时的回执
        //
        //  run9 事故：对 `ShippingMenu` 用了 `exitThisMenu()` ⇒ `outro` 永假 ⇒ 永不建
        //  `SaveGameMenu` ⇒ 日推进、盘不落（4 NewDay / 0 save，整跑作废）。
        //  现在这两类菜单走跨 tick 的 wait-only 路径，下面三个字段把"怎么推的、等了多久、
        //  菜单到底有没有消失"如实带回给脑（回执只是声明，判据仍是观测差分）。
        // ------------------------------------------------------------------

        /// <summary>
        /// <c>dismiss_modal</c> 专用：实际走的路径 ——
        /// <c>"ok_clicked"</c>（反射私有 `ShippingMenu.okClicked()`）、
        /// <c>"click_ok_button"</c>（兜底点 `okButton` 中心）、
        /// <c>"reflection_failed"</c>（两条路都没走通）、
        /// <c>"wait_only"</c>（存档菜单只等不关）、<c>"(未动手)"</c>。
        /// 【可选字段】null 时序列化省略 ⇒ 其它技能回执形状不变。
        /// </summary>
        [JsonPropertyName("dismissPath")] public string DismissPath { get; set; }

        /// <summary><c>dismiss_modal</c> 专用：这一跳实际等了多久（毫秒）。【可选字段】</summary>
        [JsonPropertyName("waitedMs")] public long? WaitedMs { get; set; }

        /// <summary>
        /// <c>dismiss_modal</c> 专用：收尾那一刻菜单**是否真的不在了**（观测事实，不是计划）。
        /// 非终态（还在等）时不写。【可选字段】null 时序列化省略。
        /// </summary>
        [JsonPropertyName("menuGone")] public bool? MenuGone { get; set; }

        /// <summary>
        /// <c>dismiss_modal</c> 专用（task-208）：**实际选中项**的文本（审计用）。
        /// 旧行为（自动挑否）也会填；没有选中任何选项（无对话 / 非对话模态 / fail-closed）时为 null。
        /// 【可选字段】null 时序列化省略 ⇒ 其它技能回执形状不变。
        /// </summary>
        [JsonPropertyName("chosenAnswer")] public string ChosenAnswer { get; set; }

        // ------------------------------------------------------------------
        //  0.7.38（task-205）新增：铁匠铺升级/取回的回执
        //
        //  依据 `docs/_il-tool-upgrade.md`（task-204）。脑侧必须能对账四件事：
        //    * 买的是哪件工具、买前/买后等级（升级**在买下时**就换，不是取回时）；
        //    * 条目自己的价格与材料（名义价 ≠ 实扣价，所以还要 moneyBefore/After 对账）；
        //    * 在途升级状态（`toolBeingUpgraded` + `daysLeft`）—— 脑据此暂停 hoe/can 相关阶段；
        //    * 整张在售表（`offers`），失败时脑能看清"到底有没有这件工具的条目"。
        // ------------------------------------------------------------------

        /// <summary><c>upgrade_tool</c> / <c>pickup_tool</c> 专用：工具种类（axe/pickaxe/hoe/can/pan）。【可选字段】</summary>
        [JsonPropertyName("tool")] public string Tool { get; set; }

        /// <summary><c>upgrade_tool</c> 专用：买之前的 <c>Tool.UpgradeLevel</c>。【可选字段】</summary>
        [JsonPropertyName("tierBefore")] public int? TierBefore { get; set; }

        /// <summary><c>upgrade_tool</c> / <c>pickup_tool</c> 专用：动作后的等级（观测值）。【可选字段】</summary>
        [JsonPropertyName("tierAfter")] public int? TierAfter { get; set; }

        /// <summary><c>upgrade_tool</c> 专用：条目自己的价格（游戏货架价，不是脑硬编码）。【可选字段】</summary>
        [JsonPropertyName("price")] public int? Price { get; set; }

        /// <summary><c>upgrade_tool</c> 专用：材料 <c>QualifiedItemId</c>（如 <c>(O)334</c> 铜锭）。【可选字段】</summary>
        [JsonPropertyName("tradeItem")] public string TradeItem { get; set; }

        /// <summary><c>upgrade_tool</c> 专用：材料数量。【可选字段】</summary>
        [JsonPropertyName("tradeCount")] public int? TradeCount { get; set; }

        /// <summary><c>upgrade_tool</c> 专用：买之前 / 之后的钱（观测真值，用于"钱差 == 价格"对账）。【可选字段】</summary>
        [JsonPropertyName("moneyBefore")] public int? MoneyBefore { get; set; }
        [JsonPropertyName("moneyAfter")] public int? MoneyAfter { get; set; }

        /// <summary>
        /// <c>upgrade_tool</c> / <c>pickup_tool</c> 专用：在途升级的工具名
        /// （<c>player.toolBeingUpgraded</c>；为 null ⇒ 没有在途）。【可选字段】
        /// </summary>
        [JsonPropertyName("toolBeingUpgraded")] public string ToolBeingUpgraded { get; set; }

        /// <summary>
        /// <c>upgrade_tool</c> / <c>pickup_tool</c> 专用：<c>player.daysLeftForToolUpgrade</c>
        /// （0 = 做完了、可取回；2 = 刚买下）。【可选字段】
        /// </summary>
        [JsonPropertyName("daysLeft")] public int? DaysLeft { get; set; }

        /// <summary><c>pickup_tool</c> 专用：背包里同种工具数量变化（取回成功 ⇒ +1）。【可选字段】</summary>
        [JsonPropertyName("inventoryAdded")] public int? InventoryAdded { get; set; }

        /// <summary>
        /// <c>upgrade_tool</c> 专用：开店那一刻 `ClintUpgrade` 的在售条目（全部工具条目）。
        /// 失败时也给 ⇒ 脑能看清"这件工具到底在不在售"，而不是靠猜。【可选字段】
        /// </summary>
        [JsonPropertyName("offers")] public UpgradeOfferView[] Offers { get; set; }

        // ------------------------------------------------------------------
        //  0.7.39（task-213）新增：`debug_dump` / `add_missed_recipes` 的回执
        //
        //  【形状约定】`entries`/`matched` 都是 `[key, value]` 的**二维字符串数组**，
        //  不是对象数组 —— 这样 Python 侧无需按动态键解析，且顺序稳定（按 key Ordinal 排序）。
        //  【全局约定不变】这些字段不适用时保持 null ⇒ 序列化省略 ⇒ 其它技能回执形状不变。
        // ------------------------------------------------------------------

        /// <summary>
        /// <c>debug_dump</c> 专用：实际读的表（**归一后的规范名**，不是请求里的原文）。
        /// 【可选字段】null 时序列化省略 ⇒ 其它技能回执形状不变。
        /// </summary>
        [JsonPropertyName("table")] public string Table { get; set; }

        /// <summary><c>debug_dump</c> 专用：该表的总条数（不受 limit 影响）。【可选字段】</summary>
        [JsonPropertyName("count")] public int? Count { get; set; }

        /// <summary><c>debug_dump</c> 专用：<c>entries</c> 是否被截断（总条数 &gt; 返回条数）。【可选字段】</summary>
        [JsonPropertyName("truncated")] public bool? Truncated { get; set; }

        /// <summary>
        /// <c>debug_dump</c> 专用：前 `limit` 条（不给 key 时）—— 每项 `[key, valueString]`。
        /// 给了 key 时本字段为空数组（只回 <see cref="Matched"/>）。【可选字段】
        /// </summary>
        [JsonPropertyName("entries")] public string[][] Entries { get; set; }

        /// <summary>
        /// <c>debug_dump</c> 专用：给了 key 时的命中项（每项 `[key, valueString]`）。
        /// 没给 key 时为 null（序列化省略）。【可选字段】
        /// </summary>
        [JsonPropertyName("matched")] public string[][] Matched { get; set; }

        /// <summary>
        /// <c>debug_dump</c> 专用：key 匹配方式 —— <c>"exact"</c>（忽略大小写的精确命中优先）/
        /// <c>"substring"</c>（子串命中）/ <c>"none"</c>（没命中）。没给 key 时为 null。【可选字段】
        /// </summary>
        [JsonPropertyName("matchMode")] public string MatchMode { get; set; }

        /// <summary><c>debug_dump</c> 专用：key 命中的总条数（截断前）。【可选字段】</summary>
        [JsonPropertyName("matchedCount")] public int? MatchedCount { get; set; }

        /// <summary><c>debug_dump</c> 专用：<c>matched</c> 是否被截断。【可选字段】</summary>
        [JsonPropertyName("matchedTruncated")] public bool? MatchedTruncated { get; set; }

        /// <summary>
        /// <c>add_missed_recipes</c> 专用：补发**新增**的 crafting 配方键（排序后的差集）。
        /// 空数组 = 调过了但一条都没加（这是**有效信息**，不是失败）。【可选字段】
        /// </summary>
        [JsonPropertyName("craftingRecipesAdded")] public string[] CraftingRecipesAdded { get; set; }

        /// <summary><c>add_missed_recipes</c> 专用：补发新增的 cooking 配方键。【可选字段】</summary>
        [JsonPropertyName("cookingRecipesAdded")] public string[] CookingRecipesAdded { get; set; }

        /// <summary><c>add_missed_recipes</c> 专用：补发新增的邮件键（`mailReceived` 差集）。【可选字段】</summary>
        [JsonPropertyName("mailAdded")] public string[] MailAdded { get; set; }

        /// <summary>
        /// <c>add_missed_recipes</c> 专用：调用**前**三类集合的计数
        /// （键：<c>crafting_recipes</c>/<c>cooking_recipes</c>/<c>mail</c>）。【可选字段】
        /// </summary>
        [JsonPropertyName("beforeCounts")] public Dictionary<string, int> BeforeCounts { get; set; }

        /// <summary><c>add_missed_recipes</c> 专用：调用**后**三类集合的计数。【可选字段】</summary>
        [JsonPropertyName("afterCounts")] public Dictionary<string, int> AfterCounts { get; set; }

        // ---- 【task-210】机器链回执（craft_item / place_object / machine）----
        //
        //  全部是**观测到的真值**，不是参数回显；判据在脑侧一律走观测差分，
        //  这些字段只是让账本可审计（"到底造了什么、放在哪、投了什么、机器里现在是什么"）。

        /// <summary><c>craft_item</c> 专用：实际命中的**已学会配方键**（规范大小写）。【可选字段】</summary>
        [JsonPropertyName("recipe")] public string Recipe { get; set; }

        /// <summary><c>craft_item</c> 专用：造出来的物品 qualifiedId（例 `(BC)114`）。【可选字段】</summary>
        [JsonPropertyName("craftedQid")] public string CraftedQid { get; set; }

        /// <summary><c>place_object</c> 专用：放下去的物体 qualifiedId。【可选字段】</summary>
        [JsonPropertyName("objectQid")] public string ObjectQid { get; set; }

        /// <summary><c>place_object</c> 专用：观测到"目标格上真的出现了这个物体"。【可选字段】</summary>
        [JsonPropertyName("placed")] public bool? Placed { get; set; }

        /// <summary><c>place_object</c> 专用：观测到"背包里那件恰好 −1"（游戏入口扣的，不是我们扣的）。【可选字段】</summary>
        [JsonPropertyName("consumed")] public bool? Consumed { get; set; }

        /// <summary><c>machine</c> 专用：`"feed"` / `"collect"`（回显本次动作，供账本）。【可选字段】</summary>
        [JsonPropertyName("machineAction")] public string MachineAction { get; set; }

        /// <summary><c>machine</c> 专用：动作**之后**机器里的东西（空 ⇒ null）。【可选字段】</summary>
        [JsonPropertyName("heldObject")] public HeldObjectView HeldObject { get; set; }

        /// <summary><c>machine</c> 专用：动作之后 `readyForHarvest.Value`。【可选字段】</summary>
        [JsonPropertyName("machineReady")] public bool? MachineReady { get; set; }

        /// <summary><c>machine</c> 专用：动作之后 `MinutesUntilReady`。【可选字段】</summary>
        [JsonPropertyName("minutesUntilReady")] public int? MinutesUntilReady { get; set; }
    }

    /// <summary>
    /// `ClintUpgrade` 在售表里的一条工具升级条目（协议 0.7.38 / task-205）。
    /// 全部字段都是**游戏真值**（`ShopMenu.itemPriceAndStock` 的条目），不解析、不猜。
    /// </summary>
    internal sealed class UpgradeOfferView
    {
        /// <summary>`QualifiedItemId`（如 `(T)UpgradeAxe` 之类的游戏条目 id）。</summary>
        [JsonPropertyName("id")] public string Id { get; set; }

        /// <summary>展示名。</summary>
        [JsonPropertyName("name")] public string Name { get; set; }

        /// <summary>工具种类（axe/pickaxe/hoe/can/pan/…）。</summary>
        [JsonPropertyName("kind")] public string Kind { get; set; }

        /// <summary>条目上的 <c>Tool.UpgradeLevel</c>（语义未定 ⇒ 脑/Mod 都不硬信，靠价格+材料兜底匹配）。</summary>
        [JsonPropertyName("tier")] public int Tier { get; set; }

        /// <summary>价格（g）。</summary>
        [JsonPropertyName("price")] public int Price { get; set; }

        /// <summary>材料 `QualifiedItemId`（可能为 null = 不收材料）。</summary>
        [JsonPropertyName("tradeItem")] public string TradeItem { get; set; }

        /// <summary>材料数量（不收材料时为 null）。</summary>
        [JsonPropertyName("tradeCount")] public int? TradeCount { get; set; }

        /// <summary>库存（游戏给的剩余量）。</summary>
        [JsonPropertyName("stock")] public int Stock { get; set; }
    }

    /// <summary>
    /// <c>buy</c> 回执里的一条货架条目（协议 0.7.26 / task-67）。
    /// 只报观测到的事实：游戏自己的 <c>ShopMenu.itemPriceAndStock</c>。
    /// </summary>
    internal sealed class ShopItemView
    {
        /// <summary><c>QualifiedItemId</c>（如 <c>(O)472</c>）；买的时候用它，比名字稳。</summary>
        [JsonPropertyName("id")] public string Id { get; set; }

        /// <summary>展示名（`Seeds` / 本地化名），脑据此筛"这是不是种子"。</summary>
        [JsonPropertyName("name")] public string Name { get; set; }

        /// <summary>单价（游戏货架价）。</summary>
        [JsonPropertyName("price")] public int Price { get; set; }
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
