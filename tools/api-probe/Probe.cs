using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;

namespace ApiProbe
{
    /// <summary>
    /// 第 19 轮：**继续"读清单"而不是"猜名字"。**
    ///
    /// 第 17/18 轮已经因为"猜名字"浪费了两轮编译（`Furniture.performAction`、
    /// `BedFurniture.IsPlayerBed`、`Farmer.startSleep/startSleeping`、`sleep` 全不存在）。
    /// 第 18 轮改成"列出成员清单"后一次就定案了睡觉流程，这一轮把同样的办法用在
    /// **买种子（ShopMenu / Utility）/ 跨日（Game1.newDay / WorldDate）/ 吃东西** 上。
    ///
    /// 用法（不需要游戏在跑；会自动从游戏目录解析 `Stardew Valley.dll`，见 Program.cs）：
    ///   tools\api-probe\bin\Release\net6.0\ApiProbe.exe
    /// 输出：logs\api-shop-members.txt（UTF-8 显式写出，不用 PowerShell 的 `&gt;`）
    /// </summary>
    public static class Probe
    {
        public static void DumpMembers()
        {
            var asm = typeof(StardewValley.Game1).Assembly;
            var lines = new List<string>();

            void Section(string title, Type t, string[] keywords)
            {
                lines.Add("");
                lines.Add("=== " + title + " : " + (t?.FullName ?? "(null)") + " ===");
                lines.Add("  关键词: " + string.Join(", ", keywords));
                if (t == null) return;

                lines.Add("-- 字段/属性 --");
                foreach (var f in t.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
                                  .Where(f => Hit(f.Name, keywords)).OrderBy(f => f.Name))
                    lines.Add($"  F {VisF(f)} {f.FieldType.Name} {f.Name}");
                foreach (var p in t.GetProperties(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
                                  .Where(p => Hit(p.Name, keywords)).OrderBy(p => p.Name))
                    lines.Add($"  P {p.PropertyType.Name} {p.Name}");

                lines.Add("-- 方法 --");
                foreach (var m in t.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
                                  .Where(m => Hit(m.Name, keywords)).OrderBy(m => m.Name))
                    lines.Add($"  M {VisM(m)} {m.ReturnType.Name} {m.Name}({string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name + " " + p.Name))})");

                lines.Add("-- 构造函数 --");
                foreach (var c in t.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                    lines.Add($"  C {VisM(c)} .ctor({string.Join(", ", c.GetParameters().Select(p => p.ParameterType.Name + " " + p.Name))})");
            }

            static bool Hit(string n, string[] keys) =>
                keys.Any(k => n.IndexOf(k, StringComparison.OrdinalIgnoreCase) >= 0);

            static string VisM(MethodBase m) =>
                m.IsPublic ? "public" : m.IsFamily ? "protected" : m.IsAssembly ? "internal" : "private";
            static string VisF(FieldInfo f) =>
                f.IsPublic ? "public" : f.IsFamily ? "protected" : f.IsAssembly ? "internal" : "private";

            // ---- 买种子：ShopMenu 的一切"买"入口 ----
            Section("StardewValley.Menus.ShopMenu", asm.GetType("StardewValley.Menus.ShopMenu"),
                new[] { "buy", "purchase", "price", "stock", "money", "currency", "charge", "hold", "salable", "item" });

            // ---- 开店入口 ----
            Section("StardewValley.Utility", typeof(StardewValley.Utility),
                new[] { "shop" });

            // ---- 跨日：Game1 的 newDay / Date / pauseTime ----
            Section("StardewValley.Game1", typeof(StardewValley.Game1),
                new[] { "newDay", "Date", "timeOfDay", "pauseTime", "gameMode", "fade" });

            // ---- 日期本身的读数（SleepSkill 判"跨日成功"要用） ----
            Section("StardewValley.WorldDate", asm.GetType("StardewValley.WorldDate"),
                new[] { "day", "season", "year", "total", "date", "time" });

            // ---- 吃东西回体力 ----
            Section("StardewValley.Farmer", typeof(StardewValley.Farmer),
                new[] { "eat", "stamina", "money", "energy" });

            // ---- ItemStockInformation（商品条目长什么样） ----
            Section("StardewValley.ItemStockInformation", asm.GetType("StardewValley.ItemStockInformation"),
                new[] { "price", "stock", "trade", "currency", "limit", "quality" });

            // ---- GameLocation：睡觉问句的应答入口 ----
            Section("StardewValley.GameLocation", typeof(StardewValley.GameLocation),
                new[] { "sleep", "lastQuestionKey", "answerDialogue", "afterQuestion" });

            // ---- NewDaySynchronizer：跨日存档握手（诊断用：readyForSave / hasSaved 是方法还是属性） ----
            Section("StardewValley.NewDaySynchronizer", asm.GetType("StardewValley.NewDaySynchronizer"),
                new[] { "save", "ready", "day", "sync", "host", "player" });

            // ---- 第 21 轮：**浇水壶会空** —— 长跑循环连浇 3 天必须能补水 ----
            // 问的是"水源怎么判定"：GameLocation 上有没有 waterTiles / isWaterTile / Water 属性查询，
            // 以及 WateringCan 的水量字段名（水量要能读出来才知道该不该去补水）。
            Section("StardewValley.GameLocation (water)", typeof(StardewValley.GameLocation),
                new[] { "water", "refill", "isWater", "Fish" });

            Section("StardewValley.Tools.WateringCan", asm.GetType("StardewValley.Tools.WateringCan"),
                new[] { "water", "refill", "empty", "level", "capacity", "uses" });

            Section("StardewValley.Tools.Tool", asm.GetType("StardewValley.Tools.Tool"),
                new[] { "water", "refill", "uses", "level" });

            Section("StardewValley.Farmer (tool)", typeof(StardewValley.Farmer),
                new[] { "water", "CurrentTool", "ToolIndex", "Items" });

            System.IO.File.WriteAllLines(
                System.IO.Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..",
                                       "logs", "api-water-members.txt"),
                lines, new System.Text.UTF8Encoding(false));
            Console.WriteLine("wrote logs/api-water-members.txt (" + lines.Count + " lines)");
        }
    }
}
