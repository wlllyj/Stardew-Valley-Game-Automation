# A9 vs B9 对照（目标2：5 天自主 + LLM 策略闭环）

> 目的：验证「跨天 lessons 注入能改进自主表现」这一自我进化假设。结论：**假设被证伪**（在代码缺陷未修前）。

## 1. 配置差异

| 项 | A9 | B9 |
|---|---|---|
| 冻结树 | `lead-0.7.50` @ `00f77df` | 同 A9 |
| lessons 注入 | 无（baseline） | 字节复制 A9 的 3 条 lessons |
| 启动器 | `scratch/_longrun_arm.py`（去代理直接 Popen） | 同 A9 |
| 输入存档 | winter26 | 同 A9 |

## 2. 结果对照

| 维度 | A9 | B9 |
|---|---|---|
| 实测天数 | 2（winter26→winter27） | 2（winter26→winter27） |
| winter26 | 干净 day_end / sleep（resume_budget_exhausted），verified=False | 同 A9 |
| winter27 | 死循环自停，无 day_end | 同 A9（lessons 未改 outcome） |
| finish | code=1 / needs_review / verified_streak=0 | 同 A9 |
| LLM 证据 | `decision`×35 + `review_llm`×1 | `decision`×30 + `intent_verdict`×30 + `review_llm`×1 + `lessons`×1 |

## 3. 结论

- 两者**同一失败模式**（冬季无活 stuck 自停），B9 未因 lessons 注入而改善。
- **A/B 教训对比假设被证伪**：在代码缺陷（无活优雅收工缺失）未修前，lessons 注入不能改变「无活自停」结果；因此「自我进化达成」的结论**不能成立**。
- 后续路径：先修「无活优雅 `no_work` 睡眠」缺陷（#17）→ 重冻 0.7.51 → 复跑 A9/B9 拿到 5 天 VERIFIED（#18）→ 再做 lessons 注入 A/B 对比（此时才具备可比性）。

## 4. 验证下一步（待 #17 修完复跑时核对）

- lessons 是否**真正注入次日 prompt**（而非仅落盘 lessons.json）：检查复跑日志中次日 `decision` 是否带 `lessons` 上下文。
- 跨天 A/B：A9（baseline，无 lessons）vs B9（有 lessons）复跑后，比较「同形态失败是否减少 / 决策是否反映教训」。无对比 = 不宣称「自我进化达成」。
