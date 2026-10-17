# run10（run B）验收判据：LLM 决策演进（会话内记忆 + 提示词反馈）

> 用户裁定：`User said (m12553)`「总之要让模型再玩这个游戏的时候具备决策演进的能力」、`User said (m12569)`「定好之后排上任务，不用开始，明天再做」。
> 诚实边界（**必须与结论一起写**）：本机制是「会话内记忆 + 提示词反馈」（每次调用留痕 + 夜间复盘 notes + 跨日教训库），**不是权重更新、不是在线训练**。没有下面的 A→B 对照证据，**不许**写"自我进化已实现"。

## 0. 设定（**2026-10-17 修订：A/B 都改到 0.7.32 同一构建**）

> ⚠️ **本节已过时**：现行 A/B = **0.7.35 上的 A′/B′**（`logs\longrun-runA2-0735.jsonl` / `…runB2-0735.jsonl`，task-113 rev11）。下面 0.7.32 的具体路径/文件名只作历史记录；**§1 的五条判定与 §2 反混淆、§5 测量规则仍然有效**。
- **run A = 累积轮 = `logs\longrun-runA.jsonl`**（**0.7.32**、5 天、`--days 5 --max-minutes 240 --max-days 12`）：跑完后把 `…-runA-lessons.json` **原样拷**成 `…-runB-lessons.json`（记拷贝时刻 + 两侧 SHA256）。
- **A 的初始教训库允许"继承历史"**（本轮裁定）：可以把 run9d（0.7.31）的 `logs\longrun-3day-llm-run9d-lessons.json`（3712 B / SHA256 `2C4BA15FB…`，以实际台账为准）**原样复制**为 A 的初始库，理由 = 教训库本来就是跨日/跨轮持久的知识；**代价与纪律**：①A 与 B 必须是**同一份 0.7.32 构建**（sidecar 四要素逐字对齐，只有 journal 路径不同）；②复制时刻 + 两侧 SHA256 双向记账并写进 `docs\_runB-evidence.md` §1；③报告里如实写"库里有几条来自 run9d、几条是 A 自己新产出的"；④若用户要求"从零积累"，则 A 必须自己在 0.7.32 上跑到库非空（L0 只认"库非空"，不区分来源，但来源必须公开）。
- **run B = 对照轮 = `logs\longrun-runB.jsonl`**（同 0.7.32、同 5 天、同存档线的下一段）：同一 Mod、同一 brain，**唯一差异 = 注入的教训/笔记/决策史**（路径由 `--journal` 自动推导，没有新增开关）；两份 sidecar 的 `argv` 必须逐字对齐（除 journal 路径）。
- **不参与 A→B 对照的历史轮**：run9（`lessons.total=0`）、run9b（落盘 5/5 但买死锁/空转未修）、run9c（含 summer 20 "0 动作自称 VERIFIED"假达标日）、**run9d（0.7.31；尾部 0/5，两条结构性病灶由 task-157/158 修）** —— 它们只作诊断/素材，**不得**当 run A 的对照臂。
- run B 起跑前必须先从 run A 的账本+教训库导出「待验证教训清单」（`tools/compare-runs.py` 的 lessons 段 + `criteria` 段），**先写下预测再跑**（避免事后挑证据）。

## 1. 五条判定（全部要有原文读数）
| # | 判据 | 证据来源 | 通过条件 |
|---|---|---|---|
| **L0** | **run A 真有教训可注入**（前置，不满足则整条对照作废） | run A 的 `<journal>-lessons.json` 与 journal `lessons` 事件 | `lessons.total >= 1` 且至少 1 条 `count >= 1`；`lessons.total == 0` ⇒ **直接写"run A 未产出教训，A→B 对照作废"**，不许拿"无教训"当"没有演进需求" |
| L1 | **教训确实被注入** | `<runB>-llm.jsonl` 的 prompt 原文 + journal `lessons`（`kept`/`loaded`） | run A 教训库中至少 **1 条**出现在 run B 某次真实调用（role=user）的 prompt 里；且 `kept>=1` |
| L2 | **同形态不再出现** | 两侧 journal 的失败/取消事件按 `(kind, scope)` 聚合 | 该教训对应的形态在 run B 的**出现次数严格小于** run A（或为 0）；`scope` 必须可比（同名田区/同类事件） |
| L3 | **决策可见地受影响** | `<runB>-llm.jsonl` 的 raw/`accepted` 意图 与 journal `decision`/`intent_verdict` | 至少 **1 条** run B 边界决策的 `intents` 或 `reason` 明确体现该教训（例：run A 反复 `cancel` 的意图在 run B 主动避开/换序），或守卫因教训改变了任务序 |
| L4 | **无回归** | `tools/verify-run3.py` + `tools/analyze-longrun.py` + `scratch/run9-lead-check.py` 原文 | run B 尾部窗口 VERIFIED 天数 **≥** run A；且无新增硬失败类别 |
| L5 | **诚实审计** | `tools/compare-runs.py` 输出 + `docs/_run10-evidence.md` | 逐条列出"注入了什么/出现几次/结局如何"；**L0–L3 任一不成立 ⇒ 结论写"不足以判定自我进化"**，不许含糊 |

### L1 的测量口径（**2026-10-17 事故后固化，必须双信号上报**）
- 量 L1 的工具是 `tools\compare-runs.py`。它的"取教训文本"口径**必须与 brain 落盘字段一致**：brain 写的是 `id/symptom/evidence/hint/count`，所以取文本按「`hint` → `lesson/text/summary/note/why/reason/symptom`」；**曾因只认 `lesson/text/...` 而退化成"把字段拼成长串" ⇒ 假报 `0/6`（"教训根本没送到"）**，而同一份留痕直查是 47/47 条决策提示词都含教训节 —— 教训：**工具自己数错的方向是"看起来没注入"，会直接把 A/B 对照判死**。
- 因此 L1 报告**必须同时给三个值**：`lessons_total` / `lessons_hits` / `lesson_section_present`（教训节抬头 `从过去几天的账本里总结的教训`）。命中 0 但节在 ⇒ 报**「比对口径警告」**（先查字段名/裁切），**不许**写"教训根本没送到"；节与逐条都没出现，才是真没送到。
- `lesson_hits` 是**子串命中**（注入后被预算裁掉的部分算未见）：run A/B 首选口径实测为 **4/6**（命中的 4 条 `hint` 整段逐字；未中的 2 条只 5 字符前缀偶然重合 ⇒ 疑"按形态按需筛选"，要单独核对渲染选择规则，不能算作"少注入"）。L3 的同指涉词表用 `lesson_full_text()`（症状+证据+自述），**不要**拿它做子串比对（会重演同一个事故）。

## 2. 反混淆（先说清，再跑）
1. **世界可比性**：run A 与 run B 的世界状态不同（这正是"继续玩"的语义）。若 run A 的教训来自**一次性**条件（例：某格当天够不着、某种天气），run B 不复现**不构成学习证据** —— 必须能找到"run B 面对同类可复现形态时行为不同"的证据，否则 L2/L3 记为【无法判定】。
2. **守恒前提**：run B 期间 Mod/brain 不许改（四要素 sidecar 必须对齐），否则对照失效。
3. **LLM 非确定性**：同一 prompt 不同采样可能给出不同意图。L3 只认"提示词里有该教训 **且** 该次决策的理由/意图与它相关"，**不认**"碰巧做对了"。必要时跑两次同形态对照并如实报告抖动。
4. **长度/预算**：教训注入 ≤3 条、notes ≤3 条、decision 史 ≤5 条（`Brief` 口径），预算挤干时按 核心 > 教训 > 决策史 > 笔记 丢弃 —— run B 的证据里要写清"这次到底注入了哪几条"。

## 3. 交付物
- `docs/_run10-evidence.md`：§1 起跑四要素（必须与 run A 同 Mod/同 brain，只有 journal 不同）；§2 两侧工具原文（`verify-run3` 的 `verdict` + `strict_verdict` 两行、`analyze-longrun --window` 默认口径）；§3 外部证据（存档 size/mtime、SMAPI 窗口冻结、`NewJourney`/`Save` 配对）；§4 **L1–L5 逐条**（附 `tools/compare-runs.py` 原文）；§5 反混淆与盲区；§6 结论（**要么给出可复核的 A→B 对照，要么写"不足以判定自我进化"**）。
- `tools/compare-runs.py` 的原文输出（含 lessons/hints/decision 三段）。

## 4. 与主目标的关系
- 主目标（用户 2026-10-17 改定**目标 2**）以 **run A（0.7.32，5 天）的小尾巴连续 5 个游戏日 VERIFIED + 四腿 + 经济闭环** 为准；历史轮只作诊断：run9（0/3）、run9b（首个整天全绿但尾部 0/3）、run9c（诊断性 3/3，含假达标日）、run9d（0/5，落盘 8/8 但两条结构性病灶 ⇒ task-157/158 修）。演进（L0–L5）是**同一目标里的能力项**，仍**不得**用"学到教训"替代达标判定，也不得用达标替代演进证据。
- 若 run A 达标而 run B 因世界条件退化而未达标，按 L4 如实记录，不掩盖、不重跑刷分（重跑必须写明是第几次、为什么）。

## 5. 测量规则（**2026-10-17 task-184 真机复测后固化**）
> 现行 A/B 已改到 **0.7.35 上的 A′/B′**（`logs\longrun-runA2-0735.jsonl` / `…runB2-0735.jsonl`，见 task-113 rev11）；上文 §0 的 0.7.32 行只作历史。**L0–L5 的判定逻辑不变**，但下面两条测量规则**必须遵守**：

1. **`worldSeq` 不是成功信号（R3）**：真机实测 `interact` 路径收获成功时 `worldSeq 60→60`（**不推进**；Mod 回执也如实写 60→60），而 `use_tool` 一次挥动 `65→67`。⇒ **任何判据都不许拿 `worldSeq` 前进当"动作成功"的证据**。成功证据只认这四类：①目标格 `ready` 由 `true→false`（或 `readySource` 变化）；②背包**逐 qid 计数**增加（对得上 `affected_tiles` 的 gained）；③`farm.readyCrops` 下降；④对照观测的 `TileSig` 变化。**失败的判据也不许用 `worldSeq` 未动**（否则会把失败判成功或反之）。
2. **回执 `ok` 仍不等于世界变了**（族里第三次教训）：`interact`/`use_tool` 都必须以「跨观测证据」为准（task-182 的 `acted`/`actedEvidence`，Mod 侧 `use_tool` 见 task-188 补齐）。报告中若出现「回执 ok 但世界未变」必须单列，不许并进成功计数。
3. **落盘/跨日口径**：跨日 ≠ 落盘（有 `displayedShippedItems` 时 `ShippingMenu` 会推迟 `SaveGameMenu`）；六串配对（`Synchronizing 'NewDay'` / `before save` / `SaveGame.Save() called` / `Saving without compression` / `completed` / `after save, starting <day>`）**必须成组出现**，缺组即如实写【无法判定】，不许按"存档 mtime 没变"直接判失败或通过。
