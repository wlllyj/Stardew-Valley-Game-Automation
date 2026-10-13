# analyze-longrun 口径卡（与 `tools\verify-run3.py` 的同口径约定）

适用：`tools\analyze-longrun.py`（task-60 之后）。裁定来源：Lead m02565 / m02395（commit `69513b8`），
验收标准见 `docs\_run6-criteria.md` §3.1。本文件只回答一件事：
**从这份报告里读出来的数字，和 `tools\verify-run3.py` 是同一口径吗？**

## 1. 决策 / LLM 两档（Lead m02565，两边**同名同义**）

| 键 | 定义 | 含义 | run2 | run5 |
|---|---|---|---|---|
| `decisions_llm` | `event=="decision"` 且 `llm == true` | **发起过**模型调用（含被拒/截断/兜底） | 7 | 33 |
| `decisions_llm_used` | 且 `source == "llm"` | 模型结果**真被采纳** | 6 | 33 |
| `decisions_llm_fallback` | 二者之差 | `deterministic_fallback`：模型答了没用 | 1 | 0 |
| `llm_by_source`（旧键） | `source=="llm"`（不看 `llm` 键） | 只用于四路对账 | 6 | 33 |
| `llm_disagree_lines`（旧键） | `bool(llm) != (source=="llm")` | 不一致的行逐行点名 | [17] | — |

**判据说"LLM 覆盖 / 覆盖率"一律指 `decisions_llm_used`** —— 否则兜底会把 run6 的覆盖率刷虚高。

run2 的 `decisions_llm=7` 里有 1 条是兜底：`logs\longrun-3day-llm-run2.jsonl:17` =
`llm=true` + `source=deterministic_fallback` + `fallback="llm_error:truncated: …"`。
头部渲染（已核对 run2/run5 原文）：

```
决策: 17 次（decisions_llm=7，其中模型产出 decisions_llm_used=6，兜底 decisions_llm_fallback=1 见 [17]）；…
决策: 114 次（decisions_llm=33，其中模型产出 decisions_llm_used=33，无兜底）；…
```

`decision` 只有 `source`/`llm`/`boundary`/`truncated`/`fallback` 五键，**没有 token/usage** ⇒
本工具不报 token 消耗（`tests\test_analyze_longrun.py::TestDecisionSourceAccounting` :546）。

## 2. 事件映射不许漂移（Lead m02395）

- brain 里 `_journal("<name>"` 的**每个**事件名都要在 `EVENT_BUCKETS` 里有桶；
  结构性事件 `day_start`/`day_end`/`finish` 记在 `STRUCTURAL_EVENTS` 白名单（不重复计数）。
- 账本里出现没桶的事件 ⇒ `report["unmapped_events"]`（名字 × 次数 + 行号）+ 头部
  「未映射事件（…绝不静默丢弃，先补 EVENT_BUCKETS 再读报告）」+ 建议 0a 排最前。
- 单测 `tests\test_analyze_longrun.py::TestEventMappingDrift` :856 直接对 **brain 源码**做机械核对
  ⇒ dev 一加新 `_journal` 名字，测试立刻红（写它时当场抓到 dev 新加的 `llm_trace_failed`）。
- run6 重点看的新事件**目前只计数、不分类**（等 run6 实际形态再定桶）：
  `goto_farm`、`stage_midway_leftover` —— run5 里分别是 5 与 7，此前被静默丢弃。

## 3. 与 `verify-run3.py` 的其余对齐 / 有意不同向

- 浇水证据四闸门**同向**：`checks.watered_outdoor` 缺失、`false`、`true + scope=="window" + tiles==0`、
  `true + final_water.dry>0`。
- `ended_reason` 以 `no_work` 开头且 `final_water.dry>0` ⇒ `missed:no_work_with_dry`（task-60），
  与它的 problem 同向；这类天的 `day_justified` 记 `day_justified_effective=false`。
- 跨日证据**有意不同向**：它把缺 `day_after` 记 problem（验收入口：缺失 ≠ 通过），
  本工具记 `undecidable`（行为分析口径）；两者都**不**把缺失当通过。
- `mod_version_mismatch`：它在验收里升为问题，本工具只记次数（分工见 `docs\_run6-criteria.md`）。
- **一眼相反时以 `verify-run3.py` 的 problem 为准，并停下报 Lead**（Lead m01934 规则）。

## 3.5 不可达（task-52，dev commit `294daea`）—— 环境挡路的第三种形态

- 三级留痕：`unreachable`（逐格：`tile`/`action`/`stage`/`zone`/`reason`/`note`）、
  `unreachable_stage`（阶段收尾：`stage`/`zone`/`tiles`/`in_leftover`/`coords`）、
  `unreachable_summary`（日级：`count`/`bound`/`attempted`/`exempted`/`raw_unmet`/`unmet`/`tiles`）。
- 政策口径（**两边同向**）：**不计当天硬失败**、当天记 blocked、**次日重试**；日级豁免上界
  `max(5, int(0.2×attempted_steps))`，豁免只扣 `no_unmet_stages` 的 leftover。
- 本工具归类：`unreachable`/`unreachable_stage` 进 **5 环境挡路（信息项）**，**不并进"该做没做"**；
  头部「不可达」行 + 建议 0e 报 次数/格数/`count`/`bound`/`attempted`/`exempt`。
- **账目差额口径不扩**：`missed:stage_account`（`failed_steps` vs `sum(stages[].failed)`）仍只认
  `env_block(+count)` + `inconclusive(+count)`，与 `tools\verify-run3.py:388-404` 逐字一致；
  `unreachable` **不算**进差额解释（不可达格被 exempt 后本就不该出现在 `stages[].failed` 里，
  真出现说明自述在重复计数 ⇒ 两边同向判红）。
- **硬闸门**：`checks.unreachable_within_bound == false` ⇒ 本工具 **0 类"必须人工介入（红）"**
  （`manual:check:unreachable_within_bound`），与 `tools\verify-run3.py:415-448` 的 problem 同向
  （豁免越界＝可能把真失败当"走不到"洗白）。
- 缺失这些字段（task-52 之前的旧账本）⇒ `unreachable_*` 计数为 0/`None`，**不判通过、也不凭空判红**。
- 单测：`tests\test_analyze_longrun.py::TestUnreachableAccounting`（5 条：桶/上界内信息项+解释差额/
  越界红/无计数解释仍红/缺字段不误报）。

## 4. 复核命令

```
python tools\analyze-longrun.py --journal logs\longrun-3day-llm-run5.jsonl
python tools\verify-run3.py      --journal logs\longrun-3day-llm-run5.jsonl
python -m unittest discover -s tests        # 当前 413 OK
```
