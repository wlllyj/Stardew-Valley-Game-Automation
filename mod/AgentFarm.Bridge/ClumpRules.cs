using System;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-182 必修 4（GAP-1）】`CropMeta.Ready()` 的**判据本身**抽成的纯函数：
    /// **不引用任何游戏类型**（没有 `Crop` / `HoeDirt` / `Netcode.*`），只吃普通值、吐普通值。
    ///
    /// 为什么非抽不可：`CropMeta.Ready()` 吃的是 `HoeDirt`/`Crop`，仓库里没有 C# 测试工程
    /// ⇒ 现有的"契约用例"只能做**源码文本存在性断言**。task-178 的对抗验收实测：
    /// 变异体 `m178b` 在游戏中转之后插一句 `return (null, null);`（fail-closed 过头），
    /// 5 条契约用例**全绿逃逸** —— 文本断言永远抓不到"行为变了"。
    ///
    /// 抽成纯函数后，最小 C# 自检工程 `mod/AgentFarm.Bridge.Tests` 可以**只编译这一个文件**
    /// （`<Compile Include="../AgentFarm.Bridge/ClumpRules.cs" />`，不引用游戏 DLL、不需要
    /// NuGet 包），直接对判据跑**行为断言**：`dotnet run` 退出码非 0 即红。
    ///
    /// 【口径不变】这里的每一条都与 `HoeDirt.readyForHarvest()` 的 IL 逐条等价
    /// （`scratch\_t176_ready.txt`）：`crop==null ⇒ false`；`fullyGrown && dayOfCurrentPhase>0 ⇒ false`；
    /// `currentPhase < phaseDays.Count-1 ⇒ false`；`dead ⇒ false`；`!forageCrop ⇒ true`；
    /// 否则 `whichForageCrop != "2"`。
    ///
    /// 【来源标记】`GameSaid != null` ⇒ `("game")`（真的问过游戏）；否则 `"fields"`；
    /// 判不了 ⇒ `(null, null)`，**绝不**用兜底猜冒充权威。
    /// </summary>
    internal static class ClumpRules
    {
        /// <summary>作物"现在能不能收"的纯判据（见类注释）。</summary>
        /// <param name="gameSaid">反射调用 `HoeDirt.readyForHarvest()` 的结果；拿不到传 <c>null</c>。</param>
        internal static (bool? Value, string Source) Ready(
            bool? gameSaid,
            bool? fullyGrown,
            int? dayOfCurrentPhase,
            int? currentPhase,
            int? phaseDaysCount,
            bool? dead,
            bool? forageCrop,
            string whichForageCrop)
        {
            // ① 游戏自己说了算（权威口径）。
            if (gameSaid.HasValue) return (gameSaid.Value, "game");

            // ② 兜底字段判据：**任一判据缺项 ⇒ 判不了**。
            //    【task-182 必修 3（NIT-1）】`whichForageCrop` 也必须进这道闸：
            //    旧代码在闸外读 `which`，闸里却用它比较 ⇒ `whichForageCrop` 读不到时会给出
            //    `(true, "fields")`，与"任一判据缺项 ⇒ null"的文档自相矛盾（task-178 抓到的 NIT-1）。
            if (fullyGrown == null || dayOfCurrentPhase == null || currentPhase == null
                || phaseDaysCount == null || dead == null || forageCrop == null)
                return (null, null);
            if (forageCrop.Value && whichForageCrop == null) return (null, null);

            if (fullyGrown.Value && dayOfCurrentPhase.Value > 0) return (false, "fields");   // 复收冷却
            if (currentPhase.Value < phaseDaysCount.Value - 1) return (false, "fields");     // 阶段没走完
            if (dead.Value) return (false, "fields");                                        // 枯死
            if (forageCrop.Value && string.Equals(whichForageCrop, "2", StringComparison.Ordinal))
                return (false, "fields");                                                    // 采集形态 2
            return (true, "fields");
        }

        /// <summary>
        /// 【task-188 必修 1】`acted` 的跨观测证据**判据本体**（纯函数，`interact` 与 `use_tool` 同源）。
        ///
        /// 四类证据，**格子级优先、全局面垫底**（与 `Skills.interact` 自 task-182 起的口径逐条一致）：
        ///   * `"tile"`       = 目标格 `TileSig`（格内逐字段签名）变了；
        ///   * `"ready"`      = 目标格 `ready` true→false，或 `readySource` 变化（再生作物唯一会动的那条）；
        ///   * `"readyCrops"` = 整场 `farm.readyCrops` 下降；
        ///   * `"inventory"`  = 背包逐 qid 栈数增加（**弱证据**：同 tick 别的系统也可能改背包 ⇒ 垫底）；
        ///   * 全不命中（含"快照拿不到"= null）⇒ <c>null</c> —— **fail-closed**：判不出来就不许算 acted。
        ///
        /// 参数用 `bool?`：`null` 表示"这条证据的观测拿不到"（例如 `TileSig` 快照失败、`readyCrops`
        /// 读不到时的 -1）⇒ 一律**不当命中**，绝不拿"没观测到"冒充"没变化"的反面。
        /// 为什么抽成纯函数：见类注释（task-182 GAP-1）；行为断言在 `mod/AgentFarm.Bridge.Tests`。
        /// </summary>
        internal static string ActedEvidence(
            bool? tileChanged,
            bool? readyFlipped,
            bool? readySourceChanged,
            bool? readyDropped,
            bool? inventoryGrew)
        {
            if (tileChanged == true) return "tile";
            if (readyFlipped == true || readySourceChanged == true) return "ready";
            if (readyDropped == true) return "readyCrops";
            if (inventoryGrew == true) return "inventory";
            return null;
        }

        /// <summary>【task-188 必修 1】`acted` 的唯一规则：**有证据才为 true**。
        /// 它替掉旧口径 `err == null`（只要没抛异常就算动手 ⇒ task-173 的"回执谎报"）。</summary>
        internal static bool Acted(string evidence) => !string.IsNullOrEmpty(evidence);
    }
}
