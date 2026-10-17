using System;
using System.Collections.Generic;
using StardewModdingAPI;
using StardewValley;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-210】`craft_item`：用**游戏自己的制作原语**造一件东西（熔炉 = `(BC)114` 是第一个用例）。
    ///
    /// ==================================================================
    /// 【为什么不走制作菜单】`Menus.CraftingPage.clickCraftingRecipe`（private）是"先扣材料、产物挂在
    /// 光标上"；自动化一旦在中途被打断，材料就白扣。task-211 的 IL 定案给的原语链更安全：
    ///
    ///   1. `new CraftingRecipe(recipeKey)`                          （public ctor，从 Data\CraftingRecipes 解析）
    ///   2. `doesFarmerHaveIngredientsInInventory(null)`             （public，游戏自己判材料够不够）
    ///   3. `createItem()`                                           （public，**只造**，不进背包、不扣材料）
    ///   4. 先自检背包放得下（**这一步在扣材料之前**，堵住"扣了材料放不进背包"）
    ///   5. `consumeIngredients(null)`                               （public void，**这一步才扣材料**）
    ///   6. `Farmer.addItemToInventoryBool(crafted, false)`          （public，进背包）
    ///
    /// 【纪律】**绝不手写 `addItem` / 手写扣材料**（0.7.19 播种事故的同类教训）：
    /// 扣料与造物都由游戏方法完成；我们只做"前置自检 + 调用 + 观测"。
    ///
    /// 【判据在脑侧】本技能回执只如实报"命中了哪个配方键、造出了什么 qid"；
    /// 脑侧用**观测差分**（`inventory[]` 逐 qid 增加 / 材料逐 qid 减少）判成功，
    /// 不信本回执的 `ok`。
    ///
    /// 【fail-closed】`recipe_unknown`（没学会 / 解析失败）/ `no_materials` / `no_slot`
    /// （背包放不下 ⇒ **材料一枚都不扣**）。
    ///
    /// 【单 tick 同步技能】不加入 `BridgeHost.IsLongTaskSkill`（没有菜单/没有等待）。
    /// ==================================================================
    /// </summary>
    internal sealed class CraftSkill
    {
        private readonly ExecRequest _req;
        private readonly WorldObserver _world;
        private readonly IMonitor _monitor;

        private bool _started;
        private bool _done;
        private DateTime _startedAtUtc;
        private long _seqBefore;

        public CraftSkill(ExecRequest req, WorldObserver world, IMonitor monitor)
        {
            this._req = req;
            this._world = world;
            this._monitor = monitor;
        }

        private long Elapsed() => this._started ? (long)(DateTime.UtcNow - this._startedAtUtc).TotalMilliseconds : 0;

        private ExecResponse Fail(string status, string reason)
            => new ExecResponse
            {
                Ok = false, Status = status, Skill = "craft_item", Reason = reason,
                Schema = Skills.ExecSchema, ElapsedMs = this.Elapsed(),
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
            };

        /// <summary>把背包扫成纯数据行（供 `MachineRules.HasRoom` 判定；读不到的槽当空处理）。</summary>
        private static List<ObjectSlotInput> SnapshotSlots()
        {
            var slots = new List<ObjectSlotInput>();
            try
            {
                var items = Game1.player?.Items;
                if (items == null) return slots;
                for (int i = 0; i < items.Count; i++)
                {
                    Item it = items[i];
                    if (it == null) { slots.Add(null); continue; }
                    var row = new ObjectSlotInput
                    {
                        Index = i,
                        IsObject = it is StardewValley.Object,
                        Stack = 0,
                        MaxStack = 0,
                    };
                    try { row.QualifiedId = it.QualifiedItemId; } catch { }
                    try { row.ItemId = it.ItemId; } catch { }
                    try { row.Name = it.DisplayName; } catch { }
                    try { row.Stack = it.Stack; } catch { }
                    try { row.MaxStack = it.maximumStackSize(); } catch { }
                    slots.Add(row);
                }
            }
            catch { }
            return slots;
        }

        public object Step()
        {
            if (this._done)
                return this.Fail("error", "craft_item 是一次性单 tick 技能：同一请求不许重复执行");
            this._done = true;

            if (!Context.IsWorldReady || Game1.player == null)
                return this.Fail("no_save", "尚未加载存档，无法制作");

            this._started = true;
            this._startedAtUtc = DateTime.UtcNow;
            this._seqBefore = this._world?.WorldSeq ?? 0;

            // ---- 参数：配方名必须是已学会的键（不做 id 猜测）----
            string wanted = this._req?.Args?.Item;
            if (string.IsNullOrWhiteSpace(wanted))
                return this.Fail(MachineRules.StatusRecipeUnknown,
                    "缺少参数 args.item（配方名，例 \"Furnace\"；必须是已学会的配方键）");

            List<string> learned = null;
            try { learned = new List<string>(Game1.player.craftingRecipes.Keys); } catch { }
            if (learned == null)
                return this.Fail(MachineRules.StatusRecipeUnknown,
                    "读不到 player.craftingRecipes（无法确认配方是否已学会，fail-closed 不做）");

            string key = MachineRules.ResolveRecipeKey(learned, wanted);
            if (key.Length == 0)
            {
                var sample = learned.GetRange(0, Math.Min(learned.Count, 20));
                return this.Fail(MachineRules.StatusRecipeUnknown,
                    $"没有学会配方「{wanted}」（已学会 {learned.Count} 条，样本：{string.Join("、", sample)}）。"
                    + "配方名必须是 player.craftingRecipes 里的键；本技能不做 id/别名猜测");
            }

            // ---- 游戏自己的制作原语 ----
            CraftingRecipe recipe;
            try { recipe = new CraftingRecipe(key); }
            catch (Exception ex)
            {
                return this.Fail(MachineRules.StatusRecipeUnknown,
                    $"游戏解析配方「{key}」失败：{ex.GetType().Name}: {ex.Message}");
            }
            if (recipe == null)
                return this.Fail(MachineRules.StatusRecipeUnknown, $"游戏解析配方「{key}」返回 null");

            bool hasMaterials;
            try { hasMaterials = recipe.doesFarmerHaveIngredientsInInventory(null); }
            catch (Exception ex)
            {
                return this.Fail(MachineRules.StatusRecipeUnknown,
                    $"判定材料失败（游戏方法抛异常）：{ex.GetType().Name}: {ex.Message}");
            }
            if (!hasMaterials)
                return this.Fail(MachineRules.StatusNoMaterials,
                    $"材料不够：配方「{key}」的 doesFarmerHaveIngredientsInInventory 返回 false"
                    + "（材料清单以游戏数据为准，本技能不硬编码；先补材料再试）");

            Item crafted;
            try { crafted = recipe.createItem(); }
            catch (Exception ex)
            {
                return this.Fail(MachineRules.StatusRecipeUnknown,
                    $"createItem 抛异常：{ex.GetType().Name}: {ex.Message}");
            }
            if (crafted == null)
                return this.Fail(MachineRules.StatusRecipeUnknown, $"配方「{key}」的 createItem 返回 null");

            // ---- 先自检背包放得下（**在扣材料之前**；否则会出现"扣了材料放不进背包"）----
            var slotsBefore = SnapshotSlots();
            string craftedQid = "";
            try { craftedQid = crafted.QualifiedItemId ?? ""; } catch { }
            int craftedStack = 1;
            try { craftedStack = Math.Max(1, crafted.Stack); } catch { }
            if (!MachineRules.HasRoom(slotsBefore, craftedQid, craftedStack))
            {
                return this.Fail(MachineRules.StatusNoSlot,
                    $"背包放不下「{key}」的产物（{craftedQid}）⇒ 先腾格；**材料一枚没扣**"
                    + "（自检在 consumeIngredients 之前）");
            }

            // ---- 扣材料（游戏方法）→ 进背包（游戏方法）----
            try { recipe.consumeIngredients(null); }
            catch (Exception ex)
            {
                return this.Fail("error",
                    $"consumeIngredients 抛异常（材料可能扣了一半，请用 observe 复核）："
                    + $"{ex.GetType().Name}: {ex.Message}");
            }

            bool added;
            try { added = Game1.player.addItemToInventoryBool(crafted, false); }
            catch (Exception ex)
            {
                return this.Fail("error",
                    $"addItemToInventoryBool 抛异常（材料已扣、产物可能没进背包，请复核）："
                    + $"{ex.GetType().Name}: {ex.Message}");
            }
            if (!added)
            {
                return this.Fail(MachineRules.StatusNoSlot,
                    $"材料已扣但产物没进背包（addItemToInventoryBool=false）⇒ 请复核背包；"
                    + "本技能**不会**再补扣或补造");
            }

            this._monitor?.Log($"[craft_item] 配方「{key}」→ {craftedQid} ×{craftedStack}（材料由游戏扣）");
            return new ExecResponse
            {
                Ok = true, Status = MachineRules.StatusOk, Skill = "craft_item",
                Reason = $"已用游戏自己的制作原语造出「{key}」→ {craftedQid} ×{craftedStack}"
                         + "（材料由 doesFarmerHaveIngredientsInInventory/consumeIngredients 判定与扣除）",
                Schema = Skills.ExecSchema, ElapsedMs = this.Elapsed(),
                WorldSeqBefore = this._seqBefore, WorldSeqAfter = this._world?.WorldSeq,
                ReachedLocation = StepMover.CurrentLocationName(),
                Recipe = key, CraftedQid = craftedQid,
            };
        }
    }
}
