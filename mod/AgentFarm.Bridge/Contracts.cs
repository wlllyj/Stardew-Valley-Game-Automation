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
    internal static class Json
    {
        /// <summary>统一的序列化设置：camelCase 策略（与外部“脑”的约定）+ 不转义中文。</summary>
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
    //  /v1/observe  —— agentfarm-world/1
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
        [JsonPropertyName("weather")] public string Weather { get; set; }
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
        [JsonPropertyName("isFarm")] public bool IsFarm { get; set; }
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
        [JsonPropertyName("activeMenu")] public string ActiveMenu { get; set; }
        [JsonPropertyName("isModal")] public bool IsModal { get; set; }
        [JsonPropertyName("eventUp")] public bool EventUp { get; set; }
        [JsonPropertyName("dialogsOnScreen")] public int DialogsOnScreen { get; set; }
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

    /// <summary>执行结果。除 ok 外，所有可空字段在不适用的技能上不输出。</summary>
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
