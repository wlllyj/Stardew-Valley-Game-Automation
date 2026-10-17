using System;
using System.Collections.Generic;

namespace AgentFarm.Bridge
{
    /// <summary>背包一行（供 <see cref="MachineRules.FindObjectSlot"/> 判定；纯数据，零游戏类型）。</summary>
    internal sealed class ObjectSlotInput
    {
        public int Index;
        public string QualifiedId;
        public string ItemId;
        public string Name;
        public int Stack;
        public int MaxStack;
        public bool IsObject;
    }

    /// <summary>
    /// 【task-210】机器链的**纯规则**（配方名解析、背包找物、机器动作分类、证据优先级）。
    ///
    /// 为什么单独成文件（与 `ClumpRules` / `TileListRules` 同一套纪律）：
    ///   `craft_item` / `place_object` / `machine` 三个技能吃 `Game1`/`CraftingRecipe`/`Object`，
    ///   仓库里没有能引用游戏程序集的测试工程 ⇒ 判据只写在技能里就只能做文本级断言、变异体逃得掉。
    ///   把"分辨率/分类/证据"抽成零依赖纯函数，`AgentFarm.Bridge.Tests` 可以直接跑**行为**断言。
    ///
    /// 状态码（与 Python 侧 `farmwork` 逐字一致，卡面 task-210）：
    ///   craft：`recipe_unknown` / `no_materials` / `no_slot`
    ///   place：`no_object` / `tile_occupied` / `placement_failed` / `placement_failed_consumed`
    ///   machine：`no_machine` / `not_ready` / `already_full` / `no_slot`
    /// </summary>
    internal static class MachineRules
    {
        public const string StatusOk = "ok";
        public const string StatusRecipeUnknown = "recipe_unknown";
        public const string StatusNoMaterials = "no_materials";
        public const string StatusNoSlot = "no_slot";
        public const string StatusNoObject = "no_object";
        public const string StatusTileOccupied = "tile_occupied";
        public const string StatusPlaceFailed = "placement_failed";
        public const string StatusPlaceFailedConsumed = "placement_failed_consumed";
        public const string StatusNoMachine = "no_machine";
        public const string StatusNotReady = "not_ready";
        public const string StatusAlreadyFull = "already_full";
        public const string StatusNothingHeld = "nothing_held";
        public const string StatusNotConsumed = "not_consumed";

        /// <summary>
        /// 在**已学会的配方键**里找目标配方名。返回规范键；找不到 / 歧义 ⇒ 空串（调用方 fail-closed）。
        ///
        /// 三级：①精确（Ordinal）唯一 ②忽略大小写唯一 ③否则空串。
        /// **不做模糊猜测**（例如拿 "(BC)114" 去猜 "Furnace"）：配方名必须是玩家字典里的键，
        /// 否则报 `recipe_unknown` 并把已学会的键列进 reason 供人工核对。
        /// </summary>
        public static string ResolveRecipeKey(IEnumerable<string> learnedKeys, string wanted)
        {
            if (learnedKeys == null || string.IsNullOrWhiteSpace(wanted)) return "";
            string want = wanted.Trim();
            var exact = new List<string>();
            var ignoreCase = new List<string>();
            foreach (string key in learnedKeys)
            {
                if (key == null) continue;
                if (string.Equals(key, want, StringComparison.Ordinal)) exact.Add(key);
                else if (string.Equals(key, want, StringComparison.OrdinalIgnoreCase)) ignoreCase.Add(key);
            }
            if (exact.Count == 1) return exact[0];
            if (exact.Count > 1) return "";
            return ignoreCase.Count == 1 ? ignoreCase[0] : "";
        }

        /// <summary>
        /// 在背包里找一件可放置物：①精确 qualifiedId ②精确 ItemId ③名字子串（忽略大小写）。
        /// 找不到 ⇒ -1（**不返回"第一个 Object"**：那会拿错东西，放置不可逆）。
        /// </summary>
        public static int FindObjectSlot(IReadOnlyList<ObjectSlotInput> slots, string wanted)
        {
            if (slots == null || string.IsNullOrWhiteSpace(wanted)) return -1;
            string want = wanted.Trim();
            foreach (ObjectSlotInput s in slots)
            {
                if (s == null || !s.IsObject) continue;
                if (string.Equals(s.QualifiedId, want, StringComparison.OrdinalIgnoreCase)) return s.Index;
            }
            foreach (ObjectSlotInput s in slots)
            {
                if (s == null || !s.IsObject) continue;
                if (string.Equals(s.ItemId, want, StringComparison.OrdinalIgnoreCase)) return s.Index;
            }
            foreach (ObjectSlotInput s in slots)
            {
                if (s == null || !s.IsObject || string.IsNullOrEmpty(s.Name)) continue;
                if (s.Name.IndexOf(want, StringComparison.OrdinalIgnoreCase) >= 0) return s.Index;
            }
            return -1;
        }

        /// <summary>能不能再放一件进背包（同 qid 且没满叠也算）：与 `addItemToInventoryBool` 的常识口径一致。</summary>
        public static bool HasRoom(IReadOnlyList<ObjectSlotInput> slots, string qualifiedId, int stackToAdd)
        {
            if (slots == null) return false;
            foreach (ObjectSlotInput s in slots)
            {
                if (s == null) return true;                       // 空格
                if (stackToAdd > 0 && !string.IsNullOrEmpty(qualifiedId)
                    && string.Equals(s.QualifiedId, qualifiedId, StringComparison.OrdinalIgnoreCase)
                    && s.MaxStack > 0 && s.Stack + stackToAdd <= s.MaxStack) return true;
            }
            return false;
        }

        /// <summary>投料分类：不是机器 ⇒ `no_machine`；机器里已有东西且不允许再装 ⇒ `already_full`。</summary>
        public static string ClassifyFeed(bool isMachine, bool heldFull)
            => !isMachine ? StatusNoMachine : (heldFull ? StatusAlreadyFull : StatusOk);

        /// <summary>取货分类：不是机器 ⇒ `no_machine`；没好 ⇒ `not_ready`。</summary>
        public static string ClassifyCollect(bool isMachine, bool readyForHarvest)
            => !isMachine ? StatusNoMachine : (readyForHarvest ? StatusOk : StatusNotReady);

        /// <summary>
        /// 机器动作的证据来源（优先级：机器状态 > 就绪翻转 > 背包差分）。
        /// 全不命中 ⇒ null（**不许**凭"回执/返回值"自称成功）。
        /// </summary>
        public static string Evidence(bool heldChanged, bool readyFlipped, bool inventoryChanged)
        {
            if (heldChanged) return "heldObject";
            if (readyFlipped) return "ready";
            if (inventoryChanged) return "inventory";
            return null;
        }

        public static bool Acted(string evidence) => !string.IsNullOrEmpty(evidence);
    }
}
