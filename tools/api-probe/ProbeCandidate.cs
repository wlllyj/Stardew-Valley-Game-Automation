using System;
using StardewModdingAPI;
using StardewValley;
using SObject = StardewValley.Object;

namespace ApiProbe
{
    /// <summary>
    /// 真机测试暴露的问题所需的 API（2026-10-11 实测）。
    ///
    /// 背景：桥 Mod 的农场统计把 weeds/twigs 记成 0（怀疑拿 ItemId 字符串比较），
    /// 天气返回空串，对话框只说得出类名。
    ///
    /// ❌ 已证伪（保留结论，勿再尝试）：
    ///   * `Object.IsWeeds` 当**属性**用 —— CS0428，它是方法，要写 `IsWeeds()`
    ///   * `Object.IsStone`          —— CS1061，不存在（用 `IsBreakableStone()`）
    ///   * `Game1.weather`           —— CS0117，不存在（用下面的 IsRainingHere 等）
    ///   * `Constants.GameVersion`   —— CS0117，不存在（虽然 SMAPI 的 XML 里写着有）
    ///   * `DialogueBox.dialogue`    —— CS1061，不存在（用 `getCurrentString()` / `dialogues`）
    ///   * `Dialogue.getCurrentString()` —— CS1061，只有 DialogueBox 上有
    ///   * `GameLocation.furniture.Pairs` —— CS1061，它是 `NetCollection&lt;Furniture&gt;`，直接遍历
    ///   * `DialogueBox.responses.Count`  —— 它是 `Response[]`，用 `.Length`
    /// </summary>
    public static class ProbeCandidate
    {
        // ---- 杂草/树枝/石头：正确判定（方法，不是属性）----
        public static bool Weeds(SObject o) => o.IsWeeds();
        public static bool Twig(SObject o) => o.IsTwig();
        public static bool Stone(SObject o) => o.IsBreakableStone();
        public static string ItemId(SObject o) => o.ItemId;
        public static string QualifiedItemId(SObject o) => o.QualifiedItemId;
        public static string TypeDefinitionId(SObject o) => o.TypeDefinitionId;
        public static int ParentSheetIndex(SObject o) => o.ParentSheetIndex;

        // ---- 天气：1.6.15 的正确读法 ----
        public static string WeatherHere() => Game1.IsRainingHere(Game1.currentLocation) ? "rain" : "sun";
        public static bool IsSnowingHere() => Game1.IsSnowingHere(Game1.currentLocation);
        public static bool IsLightningHere() => Game1.IsLightningHere(Game1.currentLocation);
        public static bool IsDebrisHere() => Game1.IsDebrisWeatherHere(Game1.currentLocation);
        public static bool IsRainingFarm() => Game1.IsRainingHere(Game1.getFarm());
        public static string WeatherForTomorrow() => Game1.weatherForTomorrow;
        public static object NetWorldState() => Game1.netWorldState.Value;

        // ---- 对话框：文本与选项（无人值守必须能读懂它才能关掉它）----
        public static string DialogueText() => (Game1.activeClickableMenu as StardewValley.Menus.DialogueBox)?.getCurrentString() ?? "";
        public static int DialogueResponseCount() => (Game1.activeClickableMenu as StardewValley.Menus.DialogueBox)?.responses?.Length ?? 0;
        public static string DialogueResponseText(int i)
        {
            var box = Game1.activeClickableMenu as StardewValley.Menus.DialogueBox;
            if (box?.responses == null || i >= box.responses.Length) return "";
            return box.responses[i].responseText ?? "";
        }
        public static string DialogueResponseKey(int i)
        {
            var box = Game1.activeClickableMenu as StardewValley.Menus.DialogueBox;
            if (box?.responses == null || i >= box.responses.Length) return "";
            return box.responses[i].responseKey ?? "";
        }
        public static int DialogueSelected() => (Game1.activeClickableMenu as StardewValley.Menus.DialogueBox)?.selectedResponse ?? -1;
        public static bool DialogueIsQuestion() => (Game1.activeClickableMenu as StardewValley.Menus.DialogueBox)?.isQuestion ?? false;
        public static object DialogueList() => (Game1.activeClickableMenu as StardewValley.Menus.DialogueBox)?.dialogues;
        public static object CharacterDialogue() => (Game1.activeClickableMenu as StardewValley.Menus.DialogueBox)?.characterDialogue;
        public static void CloseMenu() => Game1.activeClickableMenu?.exitThisMenu();

        // ---- 家具：`furniture` 是 NetCollection，直接遍历（没有 .Pairs）----
        public static int FurnitureCount(GameLocation loc) => loc?.furniture?.Count ?? 0;
        public static string FirstFurnitureType(GameLocation loc)
        {
            if (loc?.furniture == null) return "";
            foreach (var f in loc.furniture) return f?.GetType().Name ?? "";
            return "";
        }
        public static bool IsBedType(object f) => f is StardewValley.Objects.BedFurniture;

        // ---- 界面：onScreenMenus 就是常驻 HUD（所以数值恒为 4 左右，别当成对话框）----
        public static int OnScreenMenus() => Game1.onScreenMenus?.Count ?? 0;
        public static string FirstOnScreenMenu() => Game1.onScreenMenus != null && Game1.onScreenMenus.Count > 0
            ? Game1.onScreenMenus[0].GetType().Name : "";

        // ---- 移动相关状态：失焦时角色不动，需要这些字段诊断 ----
        public static bool GameWindowActive() => Game1.game1.IsActive;
        public static bool PlayerCanMove() => Game1.player != null && Game1.player.CanMove;
        public static bool HasController() => Game1.player?.controller != null;
        public static bool FadeToBlack() => Game1.fadeToBlack;
    }
}
