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
        /// 游戏窗口是否在前台（<c>Game1.game1.IsActive</c>）。
        /// 真机诊断：失焦时世界时钟照常推进，但 PathFindController 不驱动角色
        /// （失焦 10/10 失败、回到前台 5/5 成功）。把它暴露出来，脑才能一眼区分
        /// “寻路失败”与“窗口没在前台”。
        /// </summary>
        [JsonPropertyName("windowActive")] public bool WindowActive { get; set; }
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
    //  /v1/observe  —— agentfarm-world/2
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
        /// 真机教训：游戏窗口失焦时世界时钟照常推进，但 PathFindController 不驱动角色
        /// （10/10 失败；切回前台 5/5 成功）。把“人能不能动”变成脑看得见的字段，别再靠猜。
        /// </summary>
        [JsonPropertyName("canMove")] public bool CanMove { get; set; }

        /// <summary>身上是否挂着寻路控制器（<c>player.controller != null</c>）。诊断“动作做了一半”用。</summary>
        [JsonPropertyName("hasController")] public bool HasController { get; set; }

        [JsonPropertyName("tools")] public ToolsView Tools { get; set; }
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
    }

    internal sealed class FarmView
    {
        [JsonPropertyName("loaded")] public bool Loaded { get; set; }
        [JsonPropertyName("hoeDirt")] public int HoeDirt { get; set; }
        [JsonPropertyName("emptyDirt")] public int EmptyDirt { get; set; }
        [JsonPropertyName("crops")] public int Crops { get; set; }
        [JsonPropertyName("ripeCrops")] public int RipeCrops { get; set; }
        [JsonPropertyName("unwateredCrops")] public int UnwateredCrops { get; set; }
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
        /// <summary>move_to 的目标格 [x, y]。</summary>
        [JsonPropertyName("tile")] public int[] Tile { get; set; }
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
