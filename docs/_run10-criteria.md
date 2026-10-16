# run10（run B）验收判据：LLM 决策演进（会话内记忆 + 提示词反馈）

> 用户裁定：`User said (m12553)`「总之要让模型再玩这个游戏的时候具备决策演进的能力」、`User said (m12569)`「定好之后排上任务，不用开始，明天再做」。
> 诚实边界（**必须与结论一起写**）：本机制是「会话内记忆 + 提示词反馈」（每次调用留痕 + 夜间复盘 notes + 跨日教训库），**不是权重更新、不是在线训练**。没有下面的 A→B 对照证据，**不许**写"自我进化已实现"。

## 0. 设定
- **run9 = run A**（`logs/longrun-3day-llm-run9.jsonl`，只积累：写 `review_llm` notes 与 `<journal>-lessons.json`）。
- **run10 = run B**（`logs/longrun-3day-llm-run10.jsonl`）：**同一存档线的下一段**（run A 收工后的世界继续），同一 Mod（`0.7.28`）、同一 brain 代码，**唯一差异 = 注入的教训/笔记/决策史**（路径由 `--journal` 自动推导，没有新增开关）。
- run B 起跑前必须先从 run A 的账本+教训库导出「待验证教训清单」（`tools/compare-runs.py` 的 §lessons 段），**先写下预测再跑**（避免事后挑证据）。

## 1. 五条判定（全部要有原文读数）
| # | 判据 | 证据来源 | 通过条件 |
|---|---|---|---|
| L1 | **教训确实被注入** | `<run10>-llm.jsonl` 的 prompt 原文 + journal `lessons`（`kept`/`loaded`） | run A 教训库中至少 **1 条**出现在 run B 某次真实调用（role=user）的 prompt 里；且 `kept>=1` |
| L2 | **同形态不再出现** | 两侧 journal 的失败/取消事件按 `(kind, scope)` 聚合 | 该教训对应的形态在 run B 的**出现次数严格小于** run A（或为 0）；`scope` 必须可比（同名田区/同类事件） |
| L3 | **决策可见地受影响** | `<run10>-llm.jsonl` 的 raw/`accepted` 意图 与 journal `decision`/`intent_verdict` | 至少 **1 条** run B 边界决策的 `intents` 或 `reason` 明确体现该教训（例：run A 反复 `cancel` 的意图在 run B 主动避开/换序），或守卫因教训改变了任务序 |
| L4 | **无回归** | `tools/verify-run3.py` + `tools/analyze-longrun.py` 原文 | run B 尾部窗口 VERIFIED 天数 **≥** run A；且无新增硬失败类别 |
| L5 | **诚实审计** | `tools/compare-runs.py` 输出 + `docs/_run10-evidence.md` | 逐条列出"注入了什么/出现几次/结局如何"；**L1–L3 任一不成立 ⇒ 结论写"不足以判定自我进化"**，不许含糊 |

## 2. 反混淆（先说清，再跑）
1. **世界可比性**：run A 与 run B 的世界状态不同（这正是"继续玩"的语义）。若 run A 的教训来自**一次性**条件（例：某格当天够不着、某种天气），run B 不复现**不构成学习证据** —— 必须能找到"run B 面对同类可复现形态时行为不同"的证据，否则 L2/L3 记为【无法判定】。
2. **守恒前提**：run B 期间 Mod/brain 不许改（四要素 sidecar 必须对齐），否则对照失效。
3. **LLM 非确定性**：同一 prompt 不同采样可能给出不同意图。L3 只认"提示词里有该教训 **且** 该次决策的理由/意图与它相关"，**不认**"碰巧做对了"。必要时跑两次同形态对照并如实报告抖动。
4. **长度/预算**：教训注入 ≤3 条、notes ≤3 条、decision 史 ≤5 条（`Brief` 口径），预算挤干时按 核心 > 教训 > 决策史 > 笔记 丢弃 —— run B 的证据里要写清"这次到底注入了哪几条"。

## 3. 交付物
- `docs/_run10-evidence.md`：§1 起跑四要素（必须与 run9 同 Mod/同 brain，只有 journal 不同）；§2 两侧工具原文（`verify-run3` 的 `verdict` + `strict_verdict` 两行、`analyze-longrun --window` 默认口径）；§3 外部证据（存档 size/mtime、SMAPI 窗口冻结、`NewJourney`/`Save` 配对）；§4 **L1–L5 逐条**（附 `tools/compare-runs.py` 原文）；§5 反混淆与盲区；§6 结论（**要么给出可复核的 A→B 对照，要么写"不足以判定自我进化"**）。
- `tools/compare-runs.py` 的原文输出（含 lessons/hints/decision 三段）。

## 4. 与主目标的关系
- P3 ⑥ 主目标仍以 **run9/run10 的尾部连续 3 个游戏日 VERIFIED + 四腿 + 经济闭环** 为准；演进只是附加能力，**不得**用"学到教训"替代达标判定。
- 若 run9 达标而 run10 因世界条件退化而未达标，按 L4 如实记录，不掩盖、不重跑刷分（重跑必须写明是第几次、为什么）。
