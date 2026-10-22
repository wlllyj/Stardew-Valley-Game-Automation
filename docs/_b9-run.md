# B9 实测结论（0.7.50 冻结树 + A9 lessons 字节复制）

> 阶段：Phase 4（A/B 对照复跑）。本文件补录 runner-a9b9 标记 completed 却未落盘的 B9 结论。

## 1. 启动与输入

| 项 | 值 |
|---|---|
| 冻结树 | `lead-0.7.50` @ `00f77df`（含 task-241 季节感知买种 + 590f154 §5 违纪修复） |
| 启动器 | `scratch/_longrun_arm.py`（直接 Popen `run-longrun.py`，去代理 `HTTP_PROXY/HTTPS_PROXY`，置 `NO_PROXY=127.0.0.1,localhost`，规避 502 代理 127.0.0.1:17890） |
| 输入存档 | 与 A9 相同（winter26 起） |
| lessons 注入 | `logs/longrun-runB9-0750-lessons.json` **字节复制** A9 的 3 条：`slept_without_work\|day`、`encircled\|clear_area`、`plot_exhausted\|plot` |

## 2. 实测天数：2 天（winter26 → winter27）

### winter26（day 1）— 干净 day_end
- 时序：`day_start`@0.12 → … → `sleep`@106.21 → `day_end`@106.26
- `ended_by=sleep`，`ended_reason=resume_budget_exhausted`
  （回片区走路 10/10 成功、11/20 尝试、换片 4/10 次；账本仍有 35 可执行余格 ⇒ 当天不 VERIFIED）
- `verified=False`、`day_justified=False`（35 格未做）、`slept_ok=True`（真跨日 winter26→winter27）
- 做成 12 阶段、跳过 0、失败 0

### winter27（day 2）— 死循环自停，**无 day_end**
- 时序：`day_start`@106.3 → `goto_farm`×2（106.41 / 121.43）
- 进入死循环：`resume_reevaluate → resume_walk → decision(LLM) → intent_verdict cancel（"本片看得见却没有可动目标"） → resume_reevaluate → plot_exhausted`
- **在 `plot_exhausted`@137.8 被外部杀掉，无 `day_end` / 无 `sleep`**
- 守卫日志（`longrun-runB9-0750-guardian.log`）：`brain pid=7288 alive=True`，但 journal 停在 `plot_exhausted@137.8`，`age` 涨到 470.6s（约 8 分钟）不前进 ⇒ 符合"LLM 重试挂起 / 循环不 journal"形态
- 当日 **0 农场动作**（一上来就卡在 cancel/walk 循环，未触发任何可执行动作）

## 3. LLM 三能力证据（logs/longrun-runB9-0750-llm.jsonl）

| 能力 | 事件 | 计数 |
|---|---|---|
| 策略生成 | `decision` | ×30（边界决策 + 具名田区 + 任务意图） |
| 结果校验 | `intent_verdict` | ×30 |
| 日终复盘 | `review_llm` | ×1 |
| 策略优化 | `lessons` | ×1（跨天教训产出） |

→ LLM 闭环"活着"，但**策略无法扭转代码缺陷导致的无活自停**。

## 4. 结论

- **B9 未达标 Goal 2**：仅 2 天，无 5 天 VERIFIED，与 A9 同一冬季 stuck 自停形态。
- **A9→B9 lessons 注入假设证伪**：字节复制 A9 的 3 条 lessons 后，winter27 仍陷入同一死循环，outcome 未变。说明该失败模式是**代码缺陷（无活优雅收工缺失）**，非策略/教训缺口。
- **根因（已锁定）**：冬季/满包无活 → 代理在「LLM 重决策 + 走路」间无限循环；现有逃生口（`_guard_walk_streak≥10`、`plot_exhausted_burst`、`recovered>max`）要么太慢（LLM 重试挂起前到不了），要么即使触发也走 `_do_sleep(require_work=True)`（longrun.py:4321 / 10229）→ 0 农场动作时拒绝睡眠 → 返回 `slept_without_work` → 游戏日不跨 → 无干净 `day_end` → 自停。

## 5. 下一步

1. 修代码：无活连续 N 轮 → 诚实 `no_work` 睡眠（`require_work=False`）而非 stuck 自停（见工单 #17 / dev-coder-no-work-sleep）。
2. 重冻 0.7.51 + 复跑 A9/B9，拿 5 天 VERIFIED 后再做有意义的 lessons A/B 对比（工单 #18）。
