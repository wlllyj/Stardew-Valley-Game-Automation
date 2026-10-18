using System;

namespace AgentFarm.Bridge
{
    /// <summary>
    /// 【task-245】`ui.eventId` 的**纯逻辑**（不引用任何游戏类型 ⇒ 自检工程直接编译同一份源码跑行为断言）。
    ///
    /// 为什么单独抽出来：`WorldSnapshot.ReadUi()` 吃 `Game1.currentEvent`，在自检工程里跑不了；
    /// 而"有事件但 id 为空/读不到"与"没有事件"的区分是**判据**，必须能被行为断言钉住
    /// （task-182 GAP-1 的教训：判据留在吃游戏类型的类里就只能做源码文本断言，行为变异体逃逸）。
    /// </summary>
    internal static class EventRules
    {
        /// <summary>
        /// 把 `(eventUp, Game1.currentEvent?.id)` 归一成三态里的"可判定值"：
        ///   * `eventUp == false` ⇒ `null`（没有事件 ⇒ 不归因，哪怕传进来一个 id）；
        ///   * `eventUp == true` 且 id 为 null/空白 ⇒ `null`（有事件但**无法归因**，脑侧按"未知"处理）；
        ///   * 其余 ⇒ 去掉首尾空白的 id。
        ///
        /// 为什么不用空字符串表示"未知"：空串会被 JSON 读成"有值但为空"，
        /// 脑侧三态判定（有值 / null / 字段缺失）会多出第四个状态；统一用 null 才与
        /// `[JsonIgnore(Condition = JsonIgnoreCondition.Never)]` 的三态语义对齐。
        /// </summary>
        public static string IdFor(bool eventUp, string id)
        {
            if (!eventUp) return null;
            if (id == null) return null;
            string trimmed = id.Trim();
            return trimmed.Length == 0 ? null : trimmed;
        }
    }
}
