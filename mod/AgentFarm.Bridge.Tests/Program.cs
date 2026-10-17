using System;
using System.Collections.Generic;
using AgentFarm.Bridge;

namespace AgentFarm.Bridge.Tests
{
    /// <summary>
    /// task-182 必修 4（GAP-1）：`ClumpRules.Ready` 的**行为**断言（不是源码文本断言）。
    ///
    /// 覆盖的口径 = `HoeDirt.readyForHarvest()` 的 IL 逐条等价（`scratch\_t176_ready.txt`）：
    ///   * 游戏说了算（`gameSaid != null` ⇒ 来源 `"game"`，且**优先于**字段判据）；
    ///   * 兜底字段判据的四类假阳性（复收冷却 / 阶段没走完 / 枯死 / 采集形态 2）；
    ///   * 任一判据字段缺项 ⇒ `(null, null)`（fail-closed）；
    ///   * **NIT-1**：`forageCrop == true` 而 `whichForageCrop` 读不到 ⇒ `(null, null)`。
    ///
    /// 关键：**最后一条**（`FieldsPathStillWorksAfterGameBranch`）就是 task-178 的 `m178b`
    /// （在游戏分支之后插 `return (null, null);`）的杀手 —— 它走 `gameSaid = null` 的兜底路径，
    /// 期望 `(true, "fields")`；任何让兜底路径提前返回 null 的变异都会让它红。
    /// </summary>
    internal static class Program
    {
        private static int _failed;
        private static int _total;

        private static void Check(string name, bool ok, string detail)
        {
            _total++;
            if (ok)
            {
                Console.WriteLine("  ok  " + name);
                return;
            }
            _failed++;
            Console.WriteLine("FAIL  " + name + "  -> " + detail);
        }

        private static void Expect(string name, (bool? Value, string Source) actual, bool? value, string source)
        {
            bool ok = actual.Value == value && string.Equals(actual.Source ?? "<null>", source ?? "<null>", StringComparison.Ordinal);
            Check(name, ok, $"期望 ({value?.ToString() ?? "null"}, {source ?? "null"})，实得 ({actual.Value?.ToString() ?? "null"}, {actual.Source ?? "null"})");
        }

        private static int Main()
        {
            Console.WriteLine("ClumpRules.Ready 行为断言（task-182 GAP-1）");

            // ---- 游戏口径优先 -------------------------------------------------
            Expect("game_said_true_wins", ClumpRules.Ready(true, false, 0, 0, 1, false, false, null), true, "game");
            Expect("game_said_false_wins_even_if_fields_say_ready",
                   ClumpRules.Ready(false, true, 0, 5, 6, false, false, null), false, "game");

            // ---- 兜底字段判据（gameSaid = null）--------------------------------
            var ready = (bool?)true;
            var no = (bool?)false;
            Expect("fields_path_ready", ClumpRules.Ready(null, ready, 0, 5, 6, no, no, null), true, "fields");
            Expect("fields_path_regrow_cooldown", ClumpRules.Ready(null, ready, 1, 5, 6, no, no, null), false, "fields");
            Expect("fields_path_phase_incomplete", ClumpRules.Ready(null, no, 0, 4, 6, no, no, null), false, "fields");
            Expect("fields_path_dead", ClumpRules.Ready(null, ready, 0, 5, 6, true, no, null), false, "fields");
            Expect("fields_path_forage_form_2", ClumpRules.Ready(null, ready, 0, 5, 6, no, true, "2"), false, "fields");
            Expect("fields_path_forage_form_1", ClumpRules.Ready(null, ready, 0, 5, 6, no, true, "1"), true, "fields");
            Expect("fields_path_not_forage_ignores_which", ClumpRules.Ready(null, ready, 0, 5, 6, no, no, "2"), true, "fields");

            // ---- 缺项 ⇒ 判不了（fail-closed）----------------------------------
            Expect("missing_fully_grown", ClumpRules.Ready(null, null, 0, 5, 6, no, no, null), null, null);
            Expect("missing_day_of_phase", ClumpRules.Ready(null, ready, null, 5, 6, no, no, null), null, null);
            Expect("missing_current_phase", ClumpRules.Ready(null, ready, 0, null, 6, no, no, null), null, null);
            Expect("missing_phase_days", ClumpRules.Ready(null, ready, 0, 5, null, no, no, null), null, null);
            Expect("missing_dead", ClumpRules.Ready(null, ready, 0, 5, 6, null, no, null), null, null);
            Expect("missing_forage_flag", ClumpRules.Ready(null, ready, 0, 5, 6, no, null, null), null, null);
            // NIT-1：forageCrop 为真但 whichForageCrop 读不到 ⇒ 判不了（旧代码会错给 (true,"fields")）
            Expect("nit1_forage_without_which_is_unknown", ClumpRules.Ready(null, ready, 0, 5, 6, no, true, null), null, null);

            // ---- 变异杀手：游戏分支之后不许提前兜底（m178b 形态）----------------
            // gameSaid = null 时必须**继续走**字段判据；插 `return (null,null);` 的变异会在这里红。
            bool okFallback = ClumpRules.Ready(null, ready, 0, 5, 6, no, no, null) == (true, "fields");
            Check("fields_path_still_works_after_the_game_branch", okFallback,
                  "兜底路径被提前 return 短路了（m178b 形态：fail-closed 过头）");

            // ---- task-188 必修 1：`acted` 的跨观测证据判据（与 Skills.ActedEvidenceOf 同源）------
            // ① 世界真的变了 ⇒ 有证据（acted=true）且证据名非空；
            Check("t188_world_change_yields_evidence",
                  ClumpRules.Acted(ClumpRules.ActedEvidence(true, null, null, null, null)),
                  "有世界变化却判成没动手（会把成功误报成 acted=false）");
            Check("t188_evidence_name_is_tile",
                  ClumpRules.ActedEvidence(true, false, false, false, false) == "tile",
                  "tile 证据没落名");
            // ② 全不命中 ⇒ 没证据（acted=false，fail-closed）；
            Check("t188_no_change_yields_no_evidence",
                  !ClumpRules.Acted(ClumpRules.ActedEvidence(false, false, false, false, false)),
                  "什么都没变却给了证据（假 acted ⇒ task-173 的谎报形态）");
            // ③ 证据拿不到（快照失败 = null）⇒ 也不许算 acted（判不出来 ≠ true）；
            Check("t188_unknown_snapshots_are_not_acted",
                  !ClumpRules.Acted(ClumpRules.ActedEvidence(null, null, null, null, null)),
                  "快照拿不到却算 acted=true");
            // 优先级：格子级 > ready > readyCrops > inventory（全命中取最强者）
            Check("t188_priority_tile_first",
                  ClumpRules.ActedEvidence(true, true, true, true, true) == "tile",
                  "优先级错：应取 tile");
            Check("t188_priority_ready_over_readyCrops",
                  ClumpRules.ActedEvidence(false, true, false, true, true) == "ready",
                  "优先级错：应取 ready");
            Check("t188_priority_readyCrops_over_inventory",
                  ClumpRules.ActedEvidence(false, false, false, true, true) == "readyCrops",
                  "优先级错：应取 readyCrops");
            Check("t188_inventory_is_the_last_resort",
                  ClumpRules.ActedEvidence(false, false, false, false, true) == "inventory",
                  "inventory 弱证据没兜住");
            // readySource 变化单独也算格子级 ready 证据（再生作物唯一会动的那条）
            Check("t188_ready_source_change_is_ready_evidence",
                  ClumpRules.ActedEvidence(false, false, true, false, false) == "ready",
                  "readySource 变化没算证据");

            // 【task-199】`farm.readyTiles` 的坐标列表规则（排序 / 截断 / fail-closed）。
            // 与 `readyCrops` 同源同扫描由 FarmScan 的同一分支保证（Python 侧文本契约断言），
            // 这里断言的是**纯规则行为**（变异打在这几条上会红）。
            var tiles = new List<int[]> { new[] { 5, 10 }, new[] { 61, 9 }, new[] { 60, 10 } };
            TileListRules.OrderAndTruncate(tiles, 64, out int[][] ordered, out bool truncated);
            Check("t199_sorted_by_y_then_x",
                  ordered.Length == 3 && ordered[0][0] == 61 && ordered[0][1] == 9
                  && ordered[1][0] == 5 && ordered[1][1] == 10
                  && ordered[2][0] == 60 && ordered[2][1] == 10,
                  "排序错：应先 y 再 x（升序）");
            TileListRules.OrderAndTruncate(tiles, 2, out int[][] capped, out bool cappedFlag);
            Check("t199_truncated_flag_when_over_limit",
                  capped.Length == 2 && cappedFlag,
                  "超过上限没截断或截断标志没置");
            TileListRules.OrderAndTruncate(tiles, 64, out int[][] full, out bool fullFlag);
            Check("t199_not_truncated_when_within_limit", full.Length == 3 && !fullFlag,
                  "没超上限却置了 truncated");
            TileListRules.OrderAndTruncate(null, 64, out int[][] none, out bool noneFlag);
            Check("t199_null_source_is_fail_closed",
                  none.Length == 0 && noneFlag, "null 源必须空数组 + truncated=true（不确定就说不确定）");
            var dirty = new List<int[]> { new[] { 1, 2 }, new int[] { }, null, new[] { 3 } };
            TileListRules.OrderAndTruncate(dirty, 64, out int[][] clean, out bool cleanFlag);
            Check("t199_malformed_items_are_skipped",
                  clean.Length == 1 && clean[0][0] == 1 && clean[0][1] == 2 && !cleanFlag,
                  "残缺坐标没被跳过");

            // 【task-208】显式应答选择规则（`AnswerRules`，纯逻辑行为断言）。
            // 铁匠铺升级要"选第几个/选哪一句"，指错了必须失败 —— 绝不许悄悄退回自动挑 Yes。
            string[] answerTexts = { "Yes", "No", "Upgrade" };
            string[] answerKeys = { "yes", "no", "upgrade" };

            AnswerRules.AnswerPick byIndex = AnswerRules.Pick(2, null, answerTexts, answerKeys);
            Check("t208_index_hit", byIndex.Status == AnswerRules.StatusFound && byIndex.Index == 2,
                  "index 2 did not resolve to the third option");

            AnswerRules.AnswerPick byText = AnswerRules.Pick(null, "UPGR", answerTexts, answerKeys);
            Check("t208_text_hit_is_case_insensitive_substring",
                  byText.Status == AnswerRules.StatusFound && byText.Index == 2,
                  "case-insensitive substring match failed");

            AnswerRules.AnswerPick missing = AnswerRules.Pick(null, "sell", answerTexts, answerKeys);
            Check("t208_missing_text_fails_closed",
                  missing.Status == AnswerRules.StatusNotFound && missing.Index == -1
                  && missing.Note != null && missing.Note.Contains("Upgrade"),
                  "unknown text must fail with choice_not_found and list the options (no fallback)");

            AnswerRules.AnswerPick ambiguous = AnswerRules.Pick(null, "e", answerTexts, answerKeys);
            Check("t208_ambiguous_text_fails_closed",
                  ambiguous.Status == AnswerRules.StatusAmbiguous && ambiguous.Index == -1,
                  "multiple matches must fail with choice_ambiguous");

            AnswerRules.AnswerPick autoPick = AnswerRules.Pick(null, null, answerTexts, answerKeys);
            Check("t208_no_explicit_args_keeps_old_behavior",
                  autoPick.Status == AnswerRules.StatusAuto && autoPick.Index == -1,
                  "no args must yield auto (old behaviour), not a guessed option");

            AnswerRules.AnswerPick both = AnswerRules.Pick(1, "No", answerTexts, answerKeys);
            Check("t208_index_and_text_are_mutually_exclusive",
                  both.Status == AnswerRules.StatusAmbiguous && both.Index == -1,
                  "index + text together must be rejected");

            AnswerRules.AnswerPick noQuestion = AnswerRules.Pick(0, null, new string[0], new string[0]);
            Check("t208_no_options_is_no_question",
                  noQuestion.Status == AnswerRules.StatusNoQuestion && noQuestion.Index == -1,
                  "empty responses must fail with no_question");

            // ---------------- task-205：铁匠铺升级链判据（ToolUpgradeRules，纯函数） ----------------
            // 依据 docs/_il-tool-upgrade.md（task-204）。这些是**行为**断言：
            // 买错条目/漏堵"已在升级"/漏堵 readOnly 都是真机白扣钱（钱+5 条锭当场扣掉、工具不升级）。
            var offers = new List<UpgradeOfferInput>
            {
                new UpgradeOfferInput("(T)CopperAxe", "Copper Axe", "axe", 1, 2000, "(O)334", 5, 0),
                new UpgradeOfferInput("(T)CopperHoe", "Copper Hoe", "hoe", 1, 2000, "(O)334", 5, 0),
            };

            UpgradePickResult axePick = ToolUpgradeRules.Select(offers, "axe", 0);
            Check("t205_unique_offer_is_selected",
                  axePick.Index == 0 && axePick.Status == ToolUpgradeRules.StatusOk,
                  "kind=axe, tier 0→1 应唯一选中第一条");

            UpgradePickResult wrongTier = ToolUpgradeRules.Select(offers, "axe", 1);
            Check("t205_wrong_tier_fails_closed",
                  wrongTier.Index == -1 && wrongTier.Status == ToolUpgradeRules.StatusToolNotOffered
                  && wrongTier.Note.Contains("在售"),
                  "tier 1→2 不该命中 tier==1 的条目；失败 reason 要列在售表");

            var duplicate = new List<UpgradeOfferInput> { offers[0], offers[0] };
            UpgradePickResult dupPick = ToolUpgradeRules.Select(duplicate, "axe", 0);
            Check("t205_duplicate_offers_fail_closed",
                  dupPick.Index == -1 && dupPick.Status == ToolUpgradeRules.StatusToolNotOffered,
                  "同 kind 同 tier 两条 ⇒ 不唯一 ⇒ 必须 fail-closed（不许猜）");

            Check("t205_already_upgrading_blocks",
                  ToolUpgradeRules.Precheck(
                      new UpgradePrecheck(true, 0, 5, false, 99999, 2000, 99, 5), false)
                  == ToolUpgradeRules.StatusAlreadyUpgrading,
                  "toolBeingUpgraded != null ⇒ 买会白扣钱锭 ⇒ 必须堵");

            Check("t205_still_working_blocks",
                  ToolUpgradeRules.Precheck(
                      new UpgradePrecheck(false, 2, 5, false, 99999, 2000, 99, 5), false)
                  == ToolUpgradeRules.StatusStillWorking,
                  "daysLeft > 0 ⇒ 还在升级，不能买");

            Check("t205_read_only_blocks",
                  ToolUpgradeRules.Precheck(
                      new UpgradePrecheck(false, 0, 5, true, 99999, 2000, 99, 5), false)
                  == ToolUpgradeRules.StatusReadOnly,
                  "电话查价店 readOnly=true ⇒ 只扣钱不升级 ⇒ 必须堵");

            Check("t205_no_money_blocks",
                  ToolUpgradeRules.Precheck(
                      new UpgradePrecheck(false, 0, 5, false, 100, 2000, 99, 5), false)
                  == ToolUpgradeRules.StatusNoMoney,
                  "钱 < 条目价 ⇒ no_money（别让别人替你猜价格）");

            Check("t205_no_trade_item_blocks",
                  ToolUpgradeRules.Precheck(
                      new UpgradePrecheck(false, 0, 5, false, 99999, 2000, 2, 5), false)
                  == ToolUpgradeRules.StatusNoTradeItem,
                  "锭不够（2 < 5）⇒ no_trade_item");

            Check("t205_ok_when_everything_sufficient",
                  ToolUpgradeRules.Precheck(
                      new UpgradePrecheck(false, 0, 5, false, 2000, 2000, 5, 5), false) == "",
                  "钱恰好够 + 材料恰好够 + 无在途 + 非 readOnly ⇒ 放行");

            Check("t205_pickup_requires_free_slot",
                  ToolUpgradeRules.Precheck(
                      new UpgradePrecheck(false, 0, 0, false, 0, 0, 0, 0), true)
                  == ToolUpgradeRules.StatusNoSlot,
                  "取回必须 ≥1 空格（blacksmith() 的 pickup 分支 freeSpotsInInventory() <= 0 ⇒ 拿不到）");

            Check("t205_evidence_priority",
                  ToolUpgradeRules.Evidence(true, true, true, true) == ToolUpgradeRules.EvidenceToolBeingUpgraded
                  && ToolUpgradeRules.Evidence(false, true, true, true) == ToolUpgradeRules.EvidenceTradeItem
                  && ToolUpgradeRules.Evidence(false, false, true, true) == ToolUpgradeRules.EvidenceMoney
                  && ToolUpgradeRules.Evidence(false, false, false, true) == ToolUpgradeRules.EvidenceInventory
                  && ToolUpgradeRules.Evidence(false, false, false, false) == null
                  && !ToolUpgradeRules.Acted(null),
                  "证据优先级：在途 > 材料 > 钱 > 背包；全不命中 ⇒ null（必须判 acted=false）");

            Check("t205_kind_normalization",
                  ToolUpgradeRules.NormalizeKind("WateringCan") == "can"
                  && ToolUpgradeRules.SameKind("wateringcan", "can"),
                  "wateringcan/watering_can 归一化成 can");

            // ==============================================================
            //  task-213：Mod 内省面（Furnace 配方取证通道）的纯规则行为断言
            // ==============================================================
            Console.WriteLine("DumpRules 行为断言（task-213）");

            Check("t213_table_normalization",
                  DumpRules.NormalizeTable("CraftingRecipes") == "crafting_recipes"
                  && DumpRules.NormalizeTable("Data/CraftingRecipes") == "crafting_recipes"
                  && DumpRules.NormalizeTable("  CRAFTING-RECIPES ") == "crafting_recipes"
                  && DumpRules.NormalizeTable("triggeractions") == "trigger_actions"
                  && DumpRules.NormalizeTable("BigCraftables") == "big_craftables"
                  && DumpRules.NormalizeTable("no_such_table") == "",
                  "表名归一：别名/大小写/连字符/资产路径都归一；不认识 ⇒ 空串（fail-closed，禁止猜表）");

            Check("t213_limit_clamped",
                  DumpRules.ClampLimit(null) == DumpRules.LimitDefault
                  && DumpRules.ClampLimit(0) == 1
                  && DumpRules.ClampLimit(-5) == 1
                  && DumpRules.ClampLimit(50) == 50
                  && DumpRules.ClampLimit(5000) == DumpRules.LimitMax,
                  "limit 钳制：null⇒200、<1⇒1、>2000⇒2000（不许无界返回整张表）");

            Check("t213_match_kind",
                  DumpRules.MatchKind("Furnace", "furnace") == 1
                  && DumpRules.MatchKind("Furnace", "FURN") == 2
                  && DumpRules.MatchKind("Furnace", "Charcoal") == 0,
                  "key 匹配：精确（忽略大小写）优先于子串；不中 ⇒ 0");

            List<string> added = DumpRules.DiffAdded(
                new[] { "Wood", "Stone", "Furnace" },
                new[] { "Stone", "Furnace", "Charcoal Kiln", "Bee House" });
            Check("t213_diff_added_sorted",
                  added.Count == 2 && added[0] == "Bee House" && added[1] == "Charcoal Kiln",
                  "差集只给新增项并按序数排序（before 里已有的 Furnace 不算新增）");

            string described = DumpRules.Describe(new Dictionary<string, int> { ["a"] = 1, ["b"] = 2 });
            string describedLong = DumpRules.Describe(new string('x', 50), 10);
            Check("t213_describe_and_truncate",
                  described.Contains("a=1") && described.Contains("b=2")
                  && describedLong.StartsWith("xxxxxxxxxx") && describedLong.Contains("truncated")
                  && DumpRules.Describe(null) == "null",
                  "值渲染：字典 ⇒ {k=v}；超长截断并标注原长；null ⇒ \"null\"（不许抛）");

            // ==============================================================
            //  task-210：机器链契约（objects 台账的排序/截断/三态）纯规则断言
            // ==============================================================
            Console.WriteLine("TileListRules 台账断言（task-210）");

            var unsorted = new List<int[]>
            {
                new[] { 3, 2 }, new[] { 1, 5 }, new[] { 1, 2 }, new[] { 7, 1 },
            };
            bool truncatedSorted;
            int[] sortedIndices = TileListRules.OrderAndTruncateIndices(unsorted, 64, out truncatedSorted);
            Check("t210_object_list_indices_sorted_y_then_x",
                  sortedIndices.Length == 4 && !truncatedSorted
                  && sortedIndices[0] == 3 && sortedIndices[1] == 2
                  && sortedIndices[2] == 0 && sortedIndices[3] == 1,
                  "台账顺序：先 y 再 x（下标映射回原列表，行对象不会错位）");

            bool truncatedStrict;
            int[] cappedIndices = TileListRules.OrderAndTruncateIndices(unsorted, 2, out truncatedStrict);
            bool truncatedLoose;
            int[] allIndices = TileListRules.OrderAndTruncateIndices(unsorted, 4, out truncatedLoose);
            Check("t210_object_list_indices_truncated",
                  cappedIndices.Length == 2 && truncatedStrict
                  && allIndices.Length == 4 && !truncatedLoose,
                  "台账上限：超过 max 只留前 max 条并置 truncated（未超 ⇒ truncated=false）");

            bool truncatedNull;
            int[] nullIndices = TileListRules.OrderAndTruncateIndices(null, 64, out truncatedNull);
            Check("t210_object_list_null_is_fail_closed",
                  nullIndices.Length == 0 && truncatedNull,
                  "source == null ⇒ 空 + truncated=true（\"没拿到\"≠\"没有放置物\"，三态可辨）");

            var malformed = new List<int[]>
            {
                new[] { 5, 5 }, null, new[] { 9 }, new[] { 6, 4 },
            };
            bool truncatedMalformed;
            int[] malformedIndices = TileListRules.OrderAndTruncateIndices(malformed, 64, out truncatedMalformed);
            Check("t210_object_list_skips_malformed",
                  malformedIndices.Length == 2 && !truncatedMalformed
                  && malformedIndices[0] == 3 && malformedIndices[1] == 0,
                  "残缺条目（null / 长度<2）跳过，只遍历合法行（下标仍指原列表）");

            bool truncatedZero;
            int[] zeroIndices = TileListRules.OrderAndTruncateIndices(unsorted, 0, out truncatedZero);
            Check("t210_object_list_max_zero_gives_nothing",
                  zeroIndices.Length == 0 && truncatedZero,
                  "max<=0 ⇒ 一条不给且如实置 truncated（不许悄悄返回全部）");

            // ==============================================================
            //  task-210：机器链的纯规则断言（配方解析 / 背包找物 / 机器分类 / 证据优先级）
            // ==============================================================
            Console.WriteLine("MachineRules 机器链断言（task-210）");

            string recipeExact = MachineRules.ResolveRecipeKey(new[] { "Furnace", "Chest", "Torch" }, "Furnace");
            string recipeCase = MachineRules.ResolveRecipeKey(new[] { "Furnace" }, "furnace");
            string recipeUnknown = MachineRules.ResolveRecipeKey(new[] { "Furnace" }, "NotARecipe");
            string recipeAmbiguous = MachineRules.ResolveRecipeKey(new[] { "Furnace", "furnace" }, "FURNACE");
            string recipeFuzzyForbidden = MachineRules.ResolveRecipeKey(new[] { "Furnace" }, "Furn");
            Check("t210_recipe_resolution",
                  recipeExact == "Furnace" && recipeCase == "Furnace"
                  && recipeUnknown == "" && recipeAmbiguous == "" && recipeFuzzyForbidden == "",
                  "配方名解析：精确 > 忽略大小写 > 找不到/歧义 ⇒ 空串（不做模糊猜测，fail-closed）");

            var bag = new List<ObjectSlotInput>
            {
                new ObjectSlotInput { Index = 0, QualifiedId = "(O)378", ItemId = "378", Name = "Copper Ore", Stack = 12, MaxStack = 999, IsObject = true },
                new ObjectSlotInput { Index = 1, QualifiedId = "(BC)114", ItemId = "114", Name = "Furnace", Stack = 1, MaxStack = 999, IsObject = true },
                new ObjectSlotInput { Index = 2, QualifiedId = "(T)Axe", ItemId = "Axe", Name = "Axe", Stack = 1, IsObject = false },
            };
            int slotQid = MachineRules.FindObjectSlot(bag, "(BC)114");
            int slotItemId = MachineRules.FindObjectSlot(bag, "378");
            int slotName = MachineRules.FindObjectSlot(bag, "furn");
            int slotMissing = MachineRules.FindObjectSlot(bag, "(O)999");
            int slotTool = MachineRules.FindObjectSlot(bag, "Axe");
            Check("t210_find_object_slot",
                  slotQid == 1 && slotItemId == 0 && slotName == 1 && slotMissing == -1 && slotTool == -1,
                  "背包找物：qualifiedId > ItemId > 名字子串（忽略大小写）；找不到 ⇒ -1；工具类不算 Object");

            string feedOk = MachineRules.ClassifyFeed(true, false);
            string feedFull = MachineRules.ClassifyFeed(true, true);
            string feedNotMachine = MachineRules.ClassifyFeed(false, false);
            string collectOk = MachineRules.ClassifyCollect(true, true);
            string collectNotReady = MachineRules.ClassifyCollect(true, false);
            Check("t210_machine_classification",
                  feedOk == "ok" && feedFull == "already_full" && feedNotMachine == "no_machine"
                  && collectOk == "ok" && collectNotReady == "not_ready",
                  "机器分类：投料前查已满、取货前查就绪；非机器一律 no_machine（都不白白调 checkAction）");

            string evHeld = MachineRules.Evidence(true, true, true);
            string evReady = MachineRules.Evidence(false, true, true);
            string evInv = MachineRules.Evidence(false, false, true);
            string evNone = MachineRules.Evidence(false, false, false);
            Check("t210_machine_evidence_priority",
                  evHeld == "heldObject" && evReady == "ready" && evInv == "inventory" && evNone == null
                  && MachineRules.Acted(evHeld) && !MachineRules.Acted(evNone),
                  "证据优先级 heldObject > ready > inventory；全不命中 ⇒ null（绝不凭返回值自称成功）");

            Check("t210_has_room",
                  MachineRules.HasRoom(bag, "(O)378", 3)                 // 同 qid 叠未满
                  && !MachineRules.HasRoom(new List<ObjectSlotInput> { bag[0] }, "(O)378", 990)  // 叠会溢出
                  && MachineRules.HasRoom(new List<ObjectSlotInput> { bag[0], null }, "(O)378", 500), // 有空格
                  "能不能放：同 qid 叠有余量或有空格 ⇒ true；叠会溢出且无空格 ⇒ false");

            Console.WriteLine(_failed == 0
                ? $"OK {_total} 断言全部通过"
                : $"FAILED {_failed} 条断言不通过（共 {_total} 条）");
            return _failed == 0 ? 0 : 1;
        }
    }
}
