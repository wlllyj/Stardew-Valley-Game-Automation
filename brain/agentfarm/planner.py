# -*- coding: utf-8 -*-
"""P3 第⑤步 · 边界决策层（慢脑出"任务意图"，不出坐标）。

本模块是 P3 规划层的**上半截**：

    observe(full) → 【本模块】选任务意图 → 技能层按当下世界状态算坐标+动作序列
                  → 每步 observe 复核 → 记账（VERIFIED / needs_review）

下半截（把任务意图翻译成 `move_to` / `use_tool` / `select_item` / `plant` 的具体参数）
属于技能层，**本模块一行坐标都不算**。

【五条铁律】（违反即返工，见 docs/01-架构设计.md §5.2.1 / §5.4 / §5.5）

1. **LLM 只出任务意图，绝不出坐标/动作序列。**
   旧项目的病根就是"照着 LLM 给的坐标乱走"（硬编码 `(64,15)` 泄漏进 prompt）。
   本模块的 schema 只允许 4 个字段 `{task, area_hint, reason, expected_evidence}`，
   其中 `area_hint` 只允许**已观测真值的引用**（`tillable[0:9]` / `tiles.plantable` /
   `anchor:player` / `near:player` / `inventory.seeds`）；任何形如 `[56,19]` / `(56,19)` /
   `56,19` / `x=56` / `tile 56 19` 的文本都会被 `find_coordinate_like()` 抓出来并**整条拒收**。
2. **坐标与动作序列由技能层按当下 observe 世界状态计算**（P1 核心决策）。
   即使 LLM 给了合法引用，也只是"去哪片区域"的意图，落到哪一格由技能层现场判。
3. **LLM 只在边界出现**：换任务类型 / 异常恢复 / 跨日复盘。
   非边界一律走 `deterministic_plan()`（纯代码），LLM 调用次数 == 边界次数。
4. **LLM 不可用要确定性降级**：`LlmError`、畸形 JSON、含坐标、引用不存在的锚点……
   一律退回 `deterministic_plan()`，并把原因记进 `PlannerDecision.fallback_reason`。**绝不崩**。
5. **终态只有 VERIFIED / needs_review**：`classify_outcome()` / `TaskOutcome.terminal`。
   没验证通过就是 needs_review（"未完成不许报成功"），`skipped=True` 也是 needs_review
   （"跳过 ≠ 完成"，技能层的 `skip` 返回不代表这件事做完了）。

【如何使用 LLM seam（为什么不能直接 `from .llm import chat` 用）】
`llm.chat()` 一旦被调用就会真的联网（用户 m01184 明确要求：大模型开始介入前必须先告知）。
所以本模块把它藏在可注入的 seam `llm_chat` 后面：

    planner = BoundaryPlanner(llm_chat=fake_chat)   # 测试：假实现，绝不联网
    planner = BoundaryPlanner(llm_enabled=False)    # 真机默认：边界也不调 LLM，只跑代码策略
    planner = BoundaryPlanner()                     # 默认实现 = default_llm_chat（**唯一**会联网的那条路）

`default_llm_chat()` 内部才 `from .llm import chat`（延迟导入，模块导入本身不发请求），
CLI 侧对应开关 `python -m agentfarm plan --boundary-llm`，**默认关闭**。

【确定性降级 ≠ 什么都不做】
`deterministic_plan()` 是一条完整的纯代码策略（清障 → 开垦 → 播种 → 浇水 → 复盘），
LLM 挂掉时它照常给出可执行的任务意图，所以"降级"只是少了慢脑的全局权衡，不是停机。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

__all__ = [
    # 任务类型 / 边界
    "TASK_KINDS", "BOUNDARY_NEW_DAY", "BOUNDARY_RECOVERY", "BOUNDARY_TASK_CHANGE",
    "BOUNDARIES",
    # 决策来源
    "SOURCE_DETERMINISTIC", "SOURCE_LLM", "SOURCE_DETERMINISTIC_FALLBACK",
    # 终态
    "TERMINAL_VERIFIED", "TERMINAL_NEEDS_REVIEW", "TERMINAL_STATES",
    "classify_outcome", "TaskOutcome",
    # 数据
    "OBSTACLE_KINDS", "DEFERRED_KINDS", "capability_gaps", "Brief", "TaskIntent", "PlannerState", "PlannerDecision",
    # 校验
    "INTENT_FIELDS", "allowed_area_hints", "find_coordinate_like", "validate_intent",
    "parse_intents", "extract_json",
    # 策略与调用
    "deterministic_plan", "PROMPT_BRIEF_MAX_CHARS", "build_messages", "default_llm_chat",
    "LLM_TRACE_MAX_PROMPT_CHARS",
    # 【task-58】决策史（会话内记忆；不是权重更新，见 `Brief.recent_decisions`）
    "DECISIONS_KEPT", "DECISIONS_MAX_CHARS", "decision_line",
    # 【task-59】收工复盘（night 边界一次独立调用；只落 journal + 次日 `recent_notes`）
    "REVIEW_MAX_TOKENS", "REVIEW_RETRY_MAX_TOKENS", "REVIEW_NOTES_MAX", "REVIEW_NOTES_MAX_CHARS",
    "NOTES_SECTION_MAX_CHARS", "REVIEW_SYSTEM_PROMPT", "parse_review_notes", "build_review_messages",
    # 【task-136】复盘接地（当天诚实事实）+ 复盘调用留痕（`kind:"review"`）
    "REVIEW_FACT_KEYS", "render_review_facts",
    # 【task-82】跨日教训库（客观事实由代码写、hint 只许 LLM 写；只喂提示词，不参与判定）
    "LESSONS_MAX", "LESSONS_INJECT_MAX", "LESSONS_INJECT_CHARS", "LESSONS_SECTION_MAX_CHARS",
    "LESSON_SEVERITY", "LESSON_TEXT_MAX_CHARS", "LESSONS_REJECT_REASONS_MAX",
    "LESSON_SRC", "LESSON_COUNT_MAX", "UNTRUSTED_LESSON_PREFIX",
    "HINT_UNVERIFIED_PREFIX", "hint_contradicts_evidence",
    "make_lesson", "prune_lessons", "render_lessons",
    "load_lessons_file", "save_lessons_file",
    # 【task-168】规模取舍的跨日持久层（`<journal>-scope.json`）
    "SCOPE_SCHEMA", "load_scope_file", "save_scope_file",
    # 【task-219】能力缺口清单（`<journal>-gaps.json`；只提示、不进判定）
    "GAPS_SCHEMA", "GAPS_MAX_ITEMS", "GAPS_SAMPLE_TILES", "GAPS_INJECT_MAX",
    "GAPS_SECTION_MAX_CHARS", "GAPS_TEXT_MAX_CHARS", "load_gaps_file", "save_gaps_file",
    "BoundaryPlanner", "PLAN_SCHEMA_EXAMPLE",
]

# --------------------------------------------------------------------------------------
# 任务类型（schema 的 task 取值域）
# --------------------------------------------------------------------------------------
#
# 全是**领域级意图**，没有一个是"动作"。技能层负责把意图展开成动作序列，
# 并在展开前按当下 observe 复核（affordance 校验）。
TASK_KINDS: tuple[str, ...] = (
    "clear_area",       # 清理障碍（杂草/树枝/石头/树/灌木）
    "till_area",        # 锄地开垦
    "plant_area",       # 播种
    "water_area",       # 浇水
    "harvest",          # 收获成熟作物
    "reduce_scope",     # 【task-168】规模取舍：主动认输一个田区（今天不做它，如实不 VERIFIED）
    "clear_dead",       # 清掉枯死作物（只清 crop.dead，活苗绝不碰；task-51）
    "ship",             # 出货（把今天亲手收获的东西放进农场出货箱，task-42）
    "recover_stamina",  # 体力恢复（进食/睡觉）
    "sleep",            # 收工过夜（跨日）
    "wait_for_save",    # 存档没加载，先读档
    "review",           # 复盘/无事可做（慢脑边界最常见的结论）
)

# --------------------------------------------------------------------------------------
# 边界（慢脑唤醒点）
# --------------------------------------------------------------------------------------
BOUNDARY_NEW_DAY = "new_day"          # 跨日复盘：day_key 变了
BOUNDARY_RECOVERY = "recovery"        # 异常恢复：连续失败计数上升
BOUNDARY_TASK_CHANGE = "task_kind_change"  # 换任务类型：确定性策略给出的 kind 变了

BOUNDARIES: tuple[str, ...] = (BOUNDARY_NEW_DAY, BOUNDARY_RECOVERY, BOUNDARY_TASK_CHANGE)

BOUNDARY_LABELS: dict[str, str] = {
    BOUNDARY_NEW_DAY: "跨日复盘（新的一天）",
    BOUNDARY_RECOVERY: "异常恢复（连续失败上升）",
    BOUNDARY_TASK_CHANGE: "换任务类型",
}

# 决策来源（记账用）：谁最终拍板 + 有没有真的调 LLM
SOURCE_DETERMINISTIC = "deterministic"                 # 非边界，纯代码
SOURCE_LLM = "llm"                                     # 边界且 LLM 输出通过校验
SOURCE_DETERMINISTIC_FALLBACK = "deterministic_fallback"  # 边界但 LLM 不可用/被拒 → 降级

# --------------------------------------------------------------------------------------
# 终态（仅两个，见 §5.4）
# --------------------------------------------------------------------------------------
TERMINAL_VERIFIED = "VERIFIED"
TERMINAL_NEEDS_REVIEW = "needs_review"
TERMINAL_STATES: tuple[str, ...] = (TERMINAL_VERIFIED, TERMINAL_NEEDS_REVIEW)

# --------------------------------------------------------------------------------------
# 校验：schema / 引用合法性 / 坐标拒收
# --------------------------------------------------------------------------------------

#: schema 允许的字段（多一个不行，少一个不行）—— 这就是"LLM 不许出坐标"的第一道墙：
#: 没有 `tile` / `x` / `y` / `actions` 这些字段可以放坐标。
INTENT_FIELDS: tuple[str, ...] = ("task", "area_hint", "reason", "expected_evidence")

#: area_hint 允许的"已观测真值引用"（`prefix` 或 `prefix.字段`，可带 `[起:止]` 切片）。
#: 这些名字必须真的出现在简报里（防幻觉，见 `validate_intent` 的 allowed_anchors 校验）。
#:
#: ⚠️ `current_location` 是**真机跑出来的补漏**（2026-10-11，logs/plan-llm-manual-2.log）：
#: 系统提示词把 `current_location` 列为合法 area_hint，但校验器只把它当**锚点**
#: （`_BASE_ANCHORS` 里是 `anchor:current_location`），没把它当**引用前缀**。
#: 于是模型老实按提示词写 `{"area_hint": "current_location"}` 时被判
#: `unknown_reference:'current_location'`，整条拒收、白烧一次重问（第二次还被 max_tokens 截断），
#: 最后降级到确定性策略。**提示词允许的写法，校验器必须原样接受**——否则等于在惩罚听话的模型。
AREA_REF_PREFIXES: tuple[str, ...] = (
    "tillable", "tiles", "inventory", "farm", "player", "nearby", "current_location",
)

#: 相对锚点：`anchor:<name>` / `near:<name>`，name 必须在简报里出现过。
AREA_ANCHOR_RE = re.compile(r"^(?:anchor|near):([a-z][a-z0-9_]*)$")

#: `tillable` / `tillable[0:9]` / `tiles.plantable` / `farm.weeds` 这类
_AREA_REF_RE = re.compile(
    r"^(?P<prefix>[a-z][a-z0-9_]*)(?:\.(?P<field>[a-z][a-z0-9_]*))?(?:\[(?P<start>\d+)(?::(?P<end>\d+))?\])?$"
)

#: 坐标形状。**宁可严格**：只要看起来像"一对数字/一个带 x= 的赋值"，就拒收整条意图。
#: 注意 `tillable[0:9]` 不会被误伤（切片用冒号、且只有一个数字），这是刻意的。
_COORD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[\[\(]\s*-?\d{1,3}\s*,\s*-?\d{1,3}\s*[\]\)]"),   # [56,19] / (56, 19)
    re.compile(r"\b-?\d{1,3}\s*,\s*-?\d{1,3}\b"),                  # 56,19
    re.compile(r"\b[xX]\s*=\s*-?\d"),                              # x=56
    re.compile(r"\b[yY]\s*=\s*-?\d"),                              # y=19
    re.compile(r"\b(?:tile|格|坐标)\s*[\[\(]?\s*-?\d{1,3}\s*[,\s]\s*-?\d{1,3}", re.I),  # tile 56 19 / 格 56 19
)

#: 意图里 `area_hint` 用的锚点名必须来自这里（简报里真实存在的东西）
_BASE_ANCHORS: tuple[str, ...] = ("player", "current_location")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def find_coordinate_like(text: Any) -> str | None:
    """在任意文本里找"像格坐标"的片段；找到就返回命中的原文，否则 None。

    【为什么要这么狠】LLM 一旦开始给坐标，规划层就会从"看世界做决策"退化成
    "照着坐标盲走"——那正是旧项目的病根（硬编码 (64,15) 泄漏进 prompt）。
    所以这里不做"看起来像不像真坐标"的语义判断，只做形状判断：形状像就拒收。
    """
    if not isinstance(text, str):
        return None
    for pattern in _COORD_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def _slug(value: Any) -> str:
    return _SLUG_RE.sub("_", str(value or "").lower()).strip("_")


def farm_areas(observe: Mapping[str, Any], *, split: int = 2) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """从快照算出**具名田区**：返回 `(田区名, 人类可读行)`，算不出来就给两个空元组。

    给"直接从快照建简报"的调用方用（`tools\\plan-llm-manual.py`、`agentfarm plan`）——
    长跑控制器自己有作业区上下文，走 `longrun._plot_brief`，不用这个。
    `fields` 延迟导入：田区是**动态真值**，与 planner 的导入期无关。
    """
    try:
        from . import fields as fields_mod
        zones = fields_mod.zones_from_observe(observe, split=split)
    except Exception:
        return (), ()
    if not zones:
        return (), ()
    names = tuple(str(getattr(z, "name", "")) for z in zones)
    try:
        lines = tuple(fields_mod.zone_brief_lines(zones))
    except Exception:
        lines = ()
    return names, lines


def allowed_area_hints(brief: "Brief") -> tuple[str, ...]:
    """简报允许被引用的锚点（`anchor:xxx` 的 xxx 取值域），按固定顺序返回。

    具名田区（`field_nw`）也算锚点：模型既可以直接写 `field_nw`（当引用前缀，
    见 `validate_intent` 的 `allowed_refs`），也可以写 `anchor:field_nw`。
    两条写法都接受 —— **提示词允许的写法，校验器必须原样接受**。
    """
    names = list(_BASE_ANCHORS)
    for extra in list(brief.anchors) + list(brief.areas):
        if extra and extra not in names:
            names.append(extra)
    return tuple(names)


def validate_intent(
    intent: "TaskIntent",
    *,
    allowed_anchors: Iterable[str],
    allowed_refs: Iterable[str] = (),
) -> list[str]:
    """校验单条意图，返回问题列表（空 = 合法）。

    校验链（对应 §5.5）：schema → 引用字段必须真实存在（防幻觉）→ 无坐标。
    任何一条不过，调用方就必须**整条拒收**（而不是"部分采用"）。

    `allowed_refs` 是"这一轮额外允许的引用名"（目前只有具名田区 `field_*`）；
    它是**动态真值**（由 `fields.zones_from_observe` 现场算出），不能硬编码进
    `AREA_REF_PREFIXES` —— 田区名字随农场地形变，写死就等于让模型猜。
    """
    problems: list[str] = []
    anchors = {str(a) for a in allowed_anchors}
    refs = {str(r) for r in allowed_refs}

    if intent.task not in TASK_KINDS:
        problems.append(f"unknown_task:{intent.task!r}（不在 {list(TASK_KINDS)}）")

    # area_hint 只能是"已观测真值的引用/相对锚点"
    hint = intent.area_hint
    if not hint:
        problems.append("missing_area_hint")
    elif find_coordinate_like(hint):
        problems.append(f"coordinate_in_intent:area_hint={hint!r}")
    else:
        anchor = AREA_ANCHOR_RE.match(hint)
        ref = _AREA_REF_RE.match(hint)
        if anchor:
            if anchor.group(1) not in anchors:
                problems.append(f"unknown_anchor:{anchor.group(1)!r}（简报里没有这个锚点）")
        elif ref:
            if ref.group("prefix") not in AREA_REF_PREFIXES and ref.group("prefix") not in refs:
                problems.append(
                    f"unknown_reference:{hint!r}（允许的引用前缀 {list(AREA_REF_PREFIXES)}"
                    f"{'，或具名田区 ' + str(sorted(refs)) if refs else ''}）"
                )
        else:
            problems.append(f"unparsable_area_hint:{hint!r}（只允许已观测真值的引用或 anchor:/near:）")

    for name, value in (("reason", intent.reason), ("expected_evidence", intent.expected_evidence)):
        hit = find_coordinate_like(value)
        if hit:
            problems.append(f"coordinate_in_intent:{name}={hit!r}")

    if not intent.reason:
        problems.append("missing_reason")
    if not intent.expected_evidence:
        problems.append("missing_expected_evidence")

    return problems


#: 给 LLM 的 schema 示例（只出现引用，不出现任何坐标）
PLAN_SCHEMA_EXAMPLE = """{"tasks": [
  {"task": "till_area", "area_hint": "tillable[0:9]",
   "reason": "地块还有空格未开垦", "expected_evidence": "location.tiles[].kind 中 dirt 数量上升"},
  {"task": "plant_area", "area_hint": "tiles.plantable",
   "reason": "已有耕地且背包里有种子", "expected_evidence": "出现的 crop 数量上升"}
]}"""


def extract_json(raw: str) -> Any:
    """从 LLM 原始文本里把 JSON 抠出来。剥 ```json 围栏；再不行就截取首个 `{`/`[` 到末个 `}`/`]`。

    这层只负责"能不能拿到 JSON 对象"，语义校验交给 `parse_intents`。
    """
    if not isinstance(raw, str):
        raise ValueError("LLM 输出不是文本")
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    end = max(text.rfind("}"), text.rfind("]"))
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("LLM 输出里找不到 JSON")


def parse_intents(
    raw: Any,
    *,
    allowed_anchors: Iterable[str],
    allowed_refs: Iterable[str] = (),
) -> tuple[list["TaskIntent"], list[str]]:
    """解析并校验 LLM 输出 → `(合法意图, 问题列表)`。

    * 合法意图非空 ⇒ 问题列表为空（全有或全无，不做"部分采用"）。
    * 任何一条不过 ⇒ 返回 `([], 全部问题)`，调用方走重问/降级。
    """
    anchors = tuple(allowed_anchors)
    refs = tuple(allowed_refs)
    try:
        payload = extract_json(raw)
    except Exception as exc:  # noqa: BLE001 - 畸形输出一律走降级，不崩
        return [], [f"unparsable_json:{type(exc).__name__}: {exc}"]

    items: Sequence[Any]
    if isinstance(payload, Mapping):
        items = payload.get("tasks") or payload.get("intents") or [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        return [], [f"unexpected_json_root:{type(payload).__name__}"]

    if not items:
        return [], ["empty_tasks"]

    intents: list[TaskIntent] = []
    problems: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            problems.append(f"task[{index}]_not_an_object:{type(item).__name__}")
            continue
        extra = sorted(set(item) - set(INTENT_FIELDS))
        if extra:
            problems.append(f"task[{index}]_extra_fields:{extra}")
        missing = sorted(set(INTENT_FIELDS) - set(item))
        if missing:
            problems.append(f"task[{index}]_missing_fields:{missing}")
        if extra or missing:
            continue
        try:
            candidate = TaskIntent(
                task=str(item["task"]),
                area_hint=str(item["area_hint"]),
                reason=str(item["reason"]),
                expected_evidence=str(item["expected_evidence"]),
            )
        except Exception as exc:  # noqa: BLE001
            problems.append(f"task[{index}]_unbuildable:{type(exc).__name__}: {exc}")
            continue
        found = validate_intent(candidate, allowed_anchors=anchors, allowed_refs=refs)
        if found:
            problems.extend(f"task[{index}]: {p}" for p in found)
        else:
            intents.append(candidate)

    if problems:
        return [], problems
    return intents, []


# --------------------------------------------------------------------------------------
# 情境简报（Brief）
# --------------------------------------------------------------------------------------
#: 简报文本上限（§5.5 要求 ≤2 KB；超了截断，宁缺勿滥）
PROMPT_BRIEF_MAX_CHARS = 2048

#: 【task-56】决策留痕里 `prompt` 字段的上限：超过就截断，并把 `prompt_truncated` 置真。
#: 留痕是给人事后复盘用的，一句 prompt 写进 JSONL 前必须有个硬上限（否则一行能到几百 KB）。
LLM_TRACE_MAX_PROMPT_CHARS = 8000

#: 【task-58】决策史保留的条数（卡面：最近 **3–5** 条边界决策）。
DECISIONS_KEPT = 5
#: 【task-58】决策史这一节在提示词里的硬上限（卡面：≤300 字符）。
#: 超长时**从最旧的一条开始丢**；整节挤不下（简报本体已吃满 `PROMPT_BRIEF_MAX_CHARS`）
#: 就整节丢掉 —— 决策史是**最先被裁**的东西（原有简报字段一个都不许被它挤掉）。
DECISIONS_MAX_CHARS = 300
#: 【task-58】单条决策史的上限（"结局 + 意图 + 校验 + 为什么"要紧凑，一行说完）。
#: **记忆**本身保留 `DECISIONS_KEPT=5` 条，提示词里只呈现塞得下的那些 ——
#: 卡面要求的是"条数 3–5"与"整节 ≤300"两条同时成立。
#: 【task-82】补 join 摘要后字段变多（`terminal`/`leftover`/`unreachable`/`refused`/
#: `where`），140 会把后两个数字与 `why` 一起截掉 ⇒ 提到 200：一节仍放得下 1–2 条
#: （跟"最近发生了什么"比，"记得很多天"更不值钱）。
DECISION_LINE_MAX_CHARS = 200

#: 【task-59】收工复盘（night 边界）的**独立调用**预算：只写 1–3 条笔记，所以给它单独一个
#: 小 `max_tokens`——**绝不挪用主决策的 16384**（那是给"长期推理 + 补问"留的）。
#: 【task-121】原值 512 实测太小：run9（真机）`review_llm_failed`
#: `llm_error:truncated: 回答被 max_tokens 截断且内容为空（推理占用了约 512 个 token）`
#: —— deepseek-flash 是推理模型，512 全被推理吃掉、正文为空 ⇒ 复盘**每次都失败**、
#: `recent_notes` 永远空 ⇒ 教训库 `hint` 永远空 ⇒ 「决策演进」的 L1 不可能成立。
#: 提到 4096（仍远小于主决策的 16384，够 1–3 条短笔记），并配一次"加倍自愈"重试。
REVIEW_MAX_TOKENS = 4096
#: 【task-121】被 `truncated` 截断时的**自愈重试**预算（2 倍），且整次复盘最多重试 1 次。
REVIEW_RETRY_MAX_TOKENS = 8192
#: 【task-59】复盘笔记条数上限（卡面 1–3 条；超出就截断并记 `truncated`）。
REVIEW_NOTES_MAX = 3
#: 【task-59】复盘笔记**合计**字符上限（卡面"合计 ≤200 token"的保守字符代理：中文≈1 token/字）。
REVIEW_NOTES_MAX_CHARS = 200
#: 【task-59】次日简报里 `recent_notes` 这一节的硬上限。与决策史同口径：**最先被裁**。
NOTES_SECTION_MAX_CHARS = 200

#: 【task-219】能力缺口清单（`<journal>-gaps.json`）：按 `(capability|kind, tool, reason)`
#: 聚合"想干却没能力/被挡"的证据（用户 m18972：不执行的策略必须记录、能找到问题）。
#: 三条硬纪律（`docs/_run10-criteria.md` §8.3 + 0.7.39 P0-4）：
#:  * brain 只写**本 run** 的聚合文件；跨 run 聚合由 analyzer 只读做（`logs/gaps-registry.json`）；
#:  * 只作**提示**（`Brief.recent_gaps`），**不进 `checks`、不做豁免、不改 `_leftover`**；
#:  * 缺口**绝不**自动转成教训库条目（教训只从客观账本事实来）。
GAPS_SCHEMA = "agentfarm-gaps/1"
GAPS_MAX_ITEMS = 50
GAPS_SAMPLE_TILES = 5
GAPS_INJECT_MAX = 3
GAPS_SECTION_MAX_CHARS = 200
#: 单条缺口文本上限（`"{count} 次「{kind}」因{reason}没做成（需要 {tool}）"` 的保守上限）。
GAPS_TEXT_MAX_CHARS = 80

#: 【task-82】跨日教训库（`<journal>-lessons.json`）：客观事实由代码从账本写，
#: `hint` **只允许**来自 LLM（收工复盘的笔记），拿不到就留空、绝不自己编。
#: 上限 20 条，按 `(trusted, last_seq, severity, count)` 从新到旧淘汰（**可信组永远在前**）；
#: 次日注入 ≤3 条、≤200 字符。
#: ⚠️ 与决策史/复盘笔记同一条诚实边界：只影响**提示词文本**，绝不参与任何判定。
LESSONS_MAX = 20
LESSONS_INJECT_MAX = 3
LESSONS_INJECT_CHARS = 200
LESSONS_SECTION_MAX_CHARS = 200
#: 教训的严重度（越大越先保留）：同一批淘汰时"走不到/干不动"比"没做成"更值得留。
LESSON_SEVERITY: dict[str, int] = {
    "unreachable": 3,
    "encircled": 3,
    "tool_refused": 3,
    "dead_crops_blocking": 3,
    "far_dry_given_up": 2,
    "no_inventory_space": 2,
    "slept_without_work": 2,
    # 【task-122】"一天以 `stuck` 收尾、还有 leftover"是最典型的退化形态（run9 第一天就是它，
    # 而当时 8 种 kind 一条都生成不出来 ⇒ run A 攒不到教训）；"换了很多片地都找不到活"同理。
    "stuck_with_leftover": 2,
    "plot_exhausted": 2,
    "stage_incomplete": 1,
}
LESSON_SEVERITY_DEFAULT = 1
#: 【task-114 F1】从磁盘读回来的教训**只认自己写出去的 schema**：单条文本字段上限
#: （载入时截断）与一次最多记几条拒收原因。
#: 信任边界：`*-lessons.json` 是"自己写、自己读"的文件 —— 一旦被人（或别的进程）改过，
#: 里面的自由文本会**原样进提示词**，所以载入按最坏情况处理：未知 kind、结构不符、
#: 超长文本、多行注入、`severity` 被抬高、坐标样式，全部洗掉或整条丢弃。
LESSON_TEXT_MAX_CHARS = 160
LESSONS_REJECT_REASONS_MAX = 6
#: 【task-118 A】来源标记：**只有本机制自己**（`make_lesson()`）写出去的条目才带
#: `src == LESSON_SRC`。这是"这条教训是账本产物"的唯一凭据 —— 载入时缺这个标记（含旧格式
#: 文件与外部改写的文件）一律按**不可信**处理：仍然可见（填补空位、兼容旧库），但
#: **不参与 20 名额抢占**、注入行上会被显式标成外部条目、回写时**绝不**被重新盖戳写回。
LESSON_SRC = "agentfarm"
#: 不可信条目的 `count` 上界（task-118 A.2）：`prune_lessons` 的第四排序键是 `count`，
#: 不钳的话外部能靠 `count=10**9` 在同类合并/排序里抬位。
LESSON_COUNT_MAX = 10 ** 6
#: 【task-118 B】不可信条目在提示词里的显式前缀：让模型知道自己读到的不是账本产物。
UNTRUSTED_LESSON_PREFIX = "[外部条目·未验证] "

#: 【task-59】复盘专用 system 提示词。和主决策提示词完全分开：它**不做决策**，
#: 只让模型对着当天简报写 1–3 条给明天的短笔记（禁坐标、禁长篇行动计划）。
REVIEW_SYSTEM_PROMPT = (
    "你是《星露谷物语》农场的收工复盘助手。只做一件事：看完当天情境简报，写 1–3 条"
    "**给明天的自己**的短笔记。\n"
    "铁律：\n"
    "1. 只输出 JSON，格式必须是 {\"notes\": [\"…\", \"…\"]}，不要任何多余文字。\n"
    "2. 每条 ≤60 个汉字，全部合计 ≤200 字符；最多 3 条。\n"
    "3. **禁止出现坐标或数字化的格子位置**（不许写 (12,30)、不许写“第 12 列第 30 行”）；"
    "要指地点就写方向或田区名（如 field_nw、西北那片地）。\n"
    "4. 只依据简报里已有的事实，不要臆造；不要写行动计划清单，只写“明天要注意什么”。\n"
)


def parse_review_notes(
    raw: Any,
    *,
    max_notes: int = REVIEW_NOTES_MAX,
    max_chars: int = REVIEW_NOTES_MAX_CHARS,
) -> tuple[list[str], list[str], bool]:
    """【task-59】把复盘输出解析成 `(notes, rejected, truncated)` —— **绝不抛异常**。

    * 只认 `{"notes": [...]}`（或裸数组 / 裸字符串）；解析不出来 ⇒ `rejected` 里记原因；
    * 含坐标样式数字的条目**丢弃**并记 `rejected`（沿用 `find_coordinate_like`，
      与决策侧同一套判据 —— 坐标只允许由代码算）；
    * 超过 `max_notes` 条 ⇒ 只留前 `max_notes` 条；
    * 合计超过 `max_chars` ⇒ 截断最后一条能放下的部分（放不下一整条就整条丢），记 `truncated`。
    """
    rejected: list[str] = []
    try:
        data = extract_json(raw)
    except Exception:  # noqa: BLE001 - 复盘输出什么样都可能，绝不能把主循环炸掉
        return [], [f"review_not_json:{str(raw)[:120]}"], False
    if isinstance(data, Mapping):
        data = data.get("notes")
    if isinstance(data, str):
        data = [data]
    if not isinstance(data, (list, tuple)):
        return [], [f"review_schema:{type(data).__name__}"], False

    truncated = False
    kept_raw: list[str] = []
    for item in data:
        text = str(item or "").strip()
        if not text:
            continue
        if find_coordinate_like(text):
            rejected.append(f"review_coordinates:{text[:80]}")
            continue
        kept_raw.append(text)
    if len(kept_raw) > int(max_notes):
        kept_raw = kept_raw[: int(max_notes)]
        truncated = True

    notes: list[str] = []
    total = 0
    for text in kept_raw:
        if total + len(text) <= int(max_chars):
            notes.append(text)
            total += len(text)
            continue
        room = int(max_chars) - total
        if room > 0:
            notes.append(text[:room])
        truncated = True
        break
    return notes, rejected, truncated


def build_review_messages(
    brief: "Brief",
    *,
    max_chars: int = PROMPT_BRIEF_MAX_CHARS,
) -> list[dict[str, str]]:
    """【task-59】复盘这一次调用的消息：system = `REVIEW_SYSTEM_PROMPT`，user = 当天简报。

    【task-136 B】user 段在简报**之后**再接一段「当天事实（账本）」—— 那些是账本里
    客观记下来的收尾事实（`ended_by`/`failed`/`deferred`/`given_up`/干作物…），缺失的
    字段渲染成「未观测到」。为什么必须接：run9b 的复盘模型只看到乐观的派生摘要，于是
    写出「作物全已浇水且无成熟」这种与账本（`gave_up=3`）直接矛盾的 hint。
    """
    user = "今天的情境简报（仅含已观测真值）：\n" \
           + brief.situation_text()[: int(max_chars) or PROMPT_BRIEF_MAX_CHARS]
    facts = str(getattr(brief, "review_facts", "") or "")
    if facts:
        user += "\n\n" + facts
    return [
        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


#: 【task-136 B】复盘提示词里「当天事实」的键与中文标签（顺序即渲染顺序）。
#: 值取不到 ⇒ 渲染「未观测到」，**绝不当 0**（"没观测到"和"就是 0"是两件事）。
REVIEW_FACT_KEYS: tuple[tuple[str, str], ...] = (
    ("day_key", "日期"),
    ("ended_by", "当天怎么收的尾"),
    ("ended_reason", "收尾原因"),
    ("ok_steps", "做成的步数"),
    ("failed_steps", "失败的步数"),
    ("deferred_tiles", "诚实上限留下的片区待办格数"),
    ("plot_pending", "片区待做格数（含干不动/走不到的）"),
    ("unreachable", "走不到的格数"),
    ("refused", "被游戏拒绝的格数"),
    ("given_up", "当天放弃的窗口外干作物格数"),
    ("given_up_cause", "放弃原因"),
    ("dry", "农场口径没浇的活作物格数"),
    ("dry_scope", "上面这个数的口径"),
    ("crops", "农场口径作物数"),
    ("ripe", "成熟作物数"),
    ("money", "钱"),
    ("seeds", "背包里的种子数"),
    ("water_far_not_on_farm", "窗口外浇水是否因人不在农场而没做"),
    ("refills_today", "当天补水次数"),
)


def render_review_facts(facts: Mapping[str, Any] | None) -> str:
    """【task-136 B】把当天事实拍成复盘提示词里的一段（**绝不抛**、缺失写「未观测到」）。

    只渲染 `REVIEW_FACT_KEYS` 里列到的键；`None`/空串 ⇒ 「未观测到」。
    数值 0 是**有效事实**（"确实一格都没剩"），照实写 `0`，不许被当成缺失。
    """
    data = facts if isinstance(facts, Mapping) else {}
    lines = ["当天事实（账本，客观记录；缺失的写「未观测到」）:"]
    for key, label in REVIEW_FACT_KEYS:
        value = data.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            text = "未观测到"
        elif isinstance(value, bool):
            text = "是" if value else "否"
        elif isinstance(value, (tuple, list)):
            text = "[" + ", ".join(str(v) for v in value) + "]"
        else:
            text = str(value)
        lines.append(f"- {label}（{key}）={text}")
    return "\n".join(lines)


def _strip_coordinates(text: Any) -> str:
    """把坐标样式的片段洗成「某格」（教训里**绝不许**出现坐标）。"""
    out = str(text or "")
    for _ in range(4):
        hit = find_coordinate_like(out)
        if not hit:
            break
        out = out.replace(hit, "某格")
    return out


#: 【task-136 C】`hint` 在提示词里必须带的标注：它是**模型自述**，不是账本事实。
HINT_UNVERIFIED_PREFIX = "[模型自述·未验证] "

#: 账本里代表"还有没做的事"的字段名（`evidence`/`symptom` 里形如 `leftover=9`）。
_PROBLEM_FACT_KEYS: tuple[str, ...] = (
    "leftover", "failed", "failed_steps", "deferred", "deferred_tiles", "plot_pending",
    "gave_up", "dry", "dry_dead", "dead_crops", "unreachable", "refused", "plot_exhausted",
)

#: `hint` 里代表"没事了/全做完了"的措辞（与上面的正数事实同时出现 ⇒ 判定为矛盾）。
_HINT_ALL_CLEAR_MARKERS: tuple[str, ...] = (
    "全都", "全部", "全已", "都已", "都浇", "已浇", "浇过", "没有问题", "无问题",
    "一切正常", "无事可做", "没有可做", "没有什么可做", "都没有", "不缺", "不需要",
    "已完成", "已做完", "干净了",
)


def hint_contradicts_evidence(symptom: str, evidence: str, hint: str) -> bool:
    """【task-136 C】`hint` 是否与账本事实**直接矛盾**（矛盾就必须丢弃，绝不许进提示词）。

    判据刻意保守、只看两件事同时成立：
      ① `symptom`/`evidence` 里出现某个"还有没做的事"的字段且值为**正数**
         （`leftover=9`、`gave_up=3`、`dry=2`、`failed=1`、`deferred_tiles=4`…）；
      ② `hint` 里出现"全都做完了/全浇过了/没有问题"这类措辞。
    run9b 的实例：`evidence="gave_up=3 dry_dead=0"` + hint「作物全已浇水且无成熟」⇒ 丢弃。
    宁可少留一句模型自述，也不许把"我干完了"写进下一轮/下一批的提示词。
    """
    text = f"{symptom or ''}\n{evidence or ''}"
    positive = False
    for key in _PROBLEM_FACT_KEYS:
        if re.search(rf"{re.escape(key)}\s*[=:：]\s*[1-9]\d*", text):
            positive = True
            break
    if not positive:
        return False
    claim = str(hint or "")
    return any(marker in claim for marker in _HINT_ALL_CLEAR_MARKERS)


def _day_key_values(day_key: Any) -> list[Any]:
    """`day_key`（可能是 tuple/list/标量）拍成 JSON 友好的列表；坏输入 ⇒ `[]`。"""
    if day_key is None:
        return []
    try:
        return [int(v) if str(v).isdigit() else str(v) for v in day_key]
    except TypeError:
        return [str(day_key)]


def make_lesson(
    *,
    kind: str,
    scope: str = "",
    symptom: str,
    evidence: str = "",
    day_key: Any = None,
    day_seq: int = 0,
    hint: str = "",
    severity: int | None = None,
) -> dict[str, Any]:
    """造一条**客观**教训（task-82）。

    客观字段（`kind`/`scope`/`symptom`/`evidence`/`first_day`/`last_day`/`count`）由代码
    从当天账本搬；`hint` **只允许**来自 LLM（收工复盘的笔记），拿不到就留空 ——
    绝不自己编。`symptom`/`evidence`/`hint` 里的坐标样式数字会被洗成「某格」。

    同一个 `id`（`kind|scope`）在多天出现时由 `prune_lessons()` 合并（`count` 累加）。

    【task-118 A.1】写出去的每条都带 `src = LESSON_SRC`（`"agentfarm"`）—— 这是
    "本机制自产"的唯一凭据：载入侧据此区分可信/不可信，回写侧据此过滤。

    【task-136 C】`hint` 与 `symptom`/`evidence` **矛盾**（账本说还有 leftover/gave_up/dry…，
    hint 却说"全都做完了"）⇒ 该 `hint` 直接丢弃（留空），其余字段照旧保留。
    调用方（长跑控制器）用"传进去的 hint 非空、出来是空"来数 `hint_dropped` 并记 journal。
    """
    scope_text = str(scope or "")
    day_values = _day_key_values(day_key)
    hint_text = _strip_coordinates(hint)
    if hint_text and hint_contradicts_evidence(symptom, evidence, hint_text):
        hint_text = ""
    return {
        "id": f"{kind}|{scope_text}",
        "kind": str(kind),
        "scope": scope_text,
        "symptom": _strip_coordinates(symptom),
        "evidence": _strip_coordinates(evidence),
        "hint": hint_text,
        "count": 1,
        "first_day": list(day_values),
        "last_day": list(day_values),
        "last_seq": int(day_seq),
        "severity": int(LESSON_SEVERITY.get(str(kind), LESSON_SEVERITY_DEFAULT)
                        if severity is None else severity),
        "src": LESSON_SRC,
    }


def prune_lessons(
    lessons: Iterable[Mapping[str, Any]] | None,
    *,
    max_lessons: int = LESSONS_MAX,
) -> list[dict[str, Any]]:
    """合并同类教训并淘汰到 `max_lessons` 条 —— **纯函数、绝不抛**。

    * 合并键 = `id`（`kind|scope`）：`count` 累加、`last_day`/`last_seq`/`evidence`
      取最新那次、`severity` 取历次最大、`hint` 取第一个非空（**只来自 LLM**）；
    * 排序 = **`(trusted, last_seq, severity, count)`** 从大到小（task-118 A.3）：
      `trusted` = 条目带 `src == LESSON_SRC`。**可信组永远在前** ⇒ 20 条可信时外部伪造
      条目一个名额也拿不到，只能在可信条目不足 20 时填补空位（旧格式文件即此情形）；
    * 合并的可信性取**最保守**：只有参与的每一条都带 `src` 才保留 `src`，否则去掉标记
      （伪造条目无法靠与真教训"同类合并"沾上可信身份）；
    * 非法条目（不是映射 / 没有 `id`）直接跳过，坏输入当空库。
    """
    merged: dict[str, dict[str, Any]] = {}
    for raw in lessons or ():
        if not isinstance(raw, Mapping) or not raw.get("id"):
            continue
        lid = str(raw["id"])
        item = dict(raw)
        item.setdefault("count", 1)
        cur = merged.get(lid)
        if cur is None:
            merged[lid] = item
            continue
        cur["count"] = int(cur.get("count") or 1) + int(item.get("count") or 1)
        cur["severity"] = max(int(cur.get("severity") or LESSON_SEVERITY_DEFAULT),
                              int(item.get("severity") or LESSON_SEVERITY_DEFAULT))
        if int(item.get("last_seq") or 0) >= int(cur.get("last_seq") or 0):
            cur["last_seq"] = item.get("last_seq") or cur.get("last_seq")
            cur["last_day"] = item.get("last_day") or cur.get("last_day")
            cur["evidence"] = item.get("evidence") or cur.get("evidence")
            cur["symptom"] = item.get("symptom") or cur.get("symptom")
        if not cur.get("hint") and item.get("hint"):
            cur["hint"] = item["hint"]
        if cur.get("src") != LESSON_SRC or item.get("src") != LESSON_SRC:
            cur.pop("src", None)
    ranked = sorted(
        merged.values(),
        key=lambda it: (_is_trusted_lesson(it),
                        int(it.get("last_seq") or 0), int(it.get("severity") or LESSON_SEVERITY_DEFAULT),
                        int(it.get("count") or 1)),
        reverse=True,
    )
    return [dict(it) for it in ranked[: max(0, int(max_lessons))]]


def _is_trusted_lesson(item: Mapping[str, Any]) -> int:
    """条目是不是"本机制自产"（task-118 A）：只有带 `src == LESSON_SRC` 的算可信。

    返回 `0/1` 而不是 `bool`：它直接进 `sorted()` 的排序键；显式用整数更不容易被后续
    改动弄坏（`bool` 在元组排序里也能用，但没法一眼看出这是"可信优先级"）。
    """
    return 1 if item.get("src") == LESSON_SRC else 0


def render_lessons(
    lessons: Iterable[Mapping[str, Any]] | None,
    *,
    max_items: int = LESSONS_INJECT_MAX,
    max_chars: int = LESSONS_INJECT_CHARS,
) -> str:
    """把教训库拍成简报里的一节（`lessons（…）:` + 每条一行）；空 ⇒ `""`（不出现空节）。

    只取前 `max_items` 条、总长 ≤ `max_chars`；`hint` 非空时附在行尾（它来自 LLM）。
    渲染前再洗一遍坐标 —— 双保险。

    【task-118 B】不可信条目（`src` 不是 `LESSON_SRC`）除了排在可信条目之后，行首还会带
    `UNTRUSTED_LESSON_PREFIX`，让模型知道这条不是账本产物。
    """
    picked = prune_lessons(lessons)[: max(0, int(max_items))]
    if not picked:
        return ""
    head = "lessons（从过去几天的账本里总结的教训，只作参考）:"
    text = head
    for it in picked:
        symptom = str(it.get("symptom") or "").strip()
        if not symptom:
            continue
        mark = "" if _is_trusted_lesson(it) else UNTRUSTED_LESSON_PREFIX
        line = f"- {mark}{symptom}"
        evidence = str(it.get("evidence") or "").strip()
        if evidence:
            line += f"｜{evidence}"
        hint = str(it.get("hint") or "").strip()
        if hint:
            # 【task-136 C】模型自述必须带标注（证据行在前、hint 在后），
            # 否则下一轮/下一批会把它当成账本事实读。
            line += f"｜{HINT_UNVERIFIED_PREFIX}{hint}"
        item = f"\n{_strip_coordinates(line)}"
        if len(text) + len(item) > max(0, int(max_chars)):
            break
        text += item
    return text if text != head else ""


def _clean_lesson_text(value: Any, *, field: str, notes: list[str]) -> str | None:
    """洗一个教训文本字段：单行、限长、无坐标。类型不对 ⇒ `None`（整条丢）。

    **折叠换行是多行注入的第一道闸**：`render_lessons()` 把每条教训渲染成一行，
    如果文本里带着换行，外部改过的文件就能伪造出"额外的教训行/系统指令行"。
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        notes.append(f"bad_text:{field}")
        return None
    text = _strip_coordinates(" ".join(value.split()))
    if len(text) > LESSON_TEXT_MAX_CHARS:
        text = text[:LESSON_TEXT_MAX_CHARS]
        notes.append(f"truncated:{field}")
    return text


def _sanitize_lesson(raw: Any, *, notes: list[str]) -> dict[str, Any] | None:
    """把**从磁盘读回**的一条教训校验成自己的 schema；不合格 ⇒ `None`（丢）。

    【task-114 F1】信任边界见 `LESSON_TEXT_MAX_CHARS` 的注释。逐条要求：
    `kind` 必须是已知 kind、`id` 必须等于 `f"{kind}|{scope}"`、`count`/`last_seq`
    必须是真整数（`bool` 不算）、三个文本字段必须是字符串且限长 + 折叠换行 + 洗坐标、
    `symptom` 不能为空，`severity` **一律由 kind 重算**（文件里那个数不可信 ⇒ 否则
    外部能把任意一条抬到最高优先级、把真教训挤出 20 条上限）。

    【task-118 A.2】`src != LESSON_SRC`（含缺失、旧格式文件）⇒ 条目标 `untrusted=True`
    （不是丢弃：仍可见、能填补空位，但不抢 20 名额、渲染时带外部前缀、回写时不持久化）。
    不可信条目的 `count` 这里就钳到 `LESSON_COUNT_MAX`；`last_seq` 需要跨条目比较
    （`≤ max(可信 last_seq) + 1`），所以由 `load_lessons_file()` 统一钳。
    """
    if not isinstance(raw, Mapping):
        notes.append("not_a_mapping")
        return None
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in LESSON_SEVERITY:
        notes.append("unknown_kind")
        return None
    scope = raw.get("scope")
    if scope is None:
        scope = ""
    if not isinstance(scope, str):
        notes.append("bad_scope")
        return None
    if str(raw.get("id") or "") != f"{kind}|{scope}":
        notes.append("id_mismatch")
        return None
    symptom = _clean_lesson_text(raw.get("symptom"), field="symptom", notes=notes)
    evidence = _clean_lesson_text(raw.get("evidence"), field="evidence", notes=notes)
    hint = _clean_lesson_text(raw.get("hint"), field="hint", notes=notes)
    if symptom is None or evidence is None or hint is None:
        return None
    if not symptom:
        notes.append("empty_symptom")
        return None
    count = raw.get("count", 1)
    last_seq = raw.get("last_seq", 0)
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        notes.append("bad_count")
        return None
    if not isinstance(last_seq, int) or isinstance(last_seq, bool):
        notes.append("bad_seq")
        return None
    trusted = raw.get("src") == LESSON_SRC
    if not trusted:
        count = min(count, LESSON_COUNT_MAX)
    first_day = _day_key_values(raw.get("first_day"))
    last_day = _day_key_values(raw.get("last_day")) or list(first_day)
    return {
        "id": f"{kind}|{scope}",
        "kind": kind,
        "scope": scope,
        "symptom": symptom,
        "evidence": evidence,
        "hint": hint,
        "count": count,
        "first_day": first_day,
        "last_day": last_day,
        "last_seq": last_seq,
        "severity": int(LESSON_SEVERITY.get(kind, LESSON_SEVERITY_DEFAULT)),
        "src": LESSON_SRC if trusted else "",
        "untrusted": (not trusted),
    }


def load_lessons_file(path: Any,
                      *, report: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], str]:
    """读跨日教训库（task-82）。**绝不抛**：成功 ⇒ `(lessons, "")`；缺文件 ⇒ `([], "")`；
    读不了/不是 JSON/结构不对 ⇒ `([], 原因串)`（调用方记一笔 journal 后照常跑）。

    【task-114 F1】读回来的每条都过 `_sanitize_lesson()`（只认自己的 schema）。
    传了 `report` 字典时回填 `{"dropped": 丢了几条, "reasons": [原因…]}`，调用方据此记
    `lessons_rejected` —— **不静默**是这条修法的另一半：丢了多少、为什么丢，账本里要看得到。
    """
    if report is not None:
        report["dropped"] = 0
        report["reasons"] = []
    try:
        p = Path(path)
    except Exception as exc:  # noqa: BLE001
        return [], f"bad_path:{type(exc).__name__}"
    if not p.exists():
        return [], ""
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [], f"read_failed:{type(exc).__name__}: {exc}"
    if isinstance(raw, Mapping):
        raw = raw.get("lessons")
    if not isinstance(raw, list):
        return [], "not_a_list"
    kept: list[dict[str, Any]] = []
    dropped = 0
    reasons: list[str] = []
    for item in raw:
        notes: list[str] = []
        clean = _sanitize_lesson(item, notes=notes)
        if clean is None:
            dropped += 1
        else:
            kept.append(clean)
        for why in notes:
            if why.startswith("truncated:") and clean is not None:
                reasons.append(why)          # 截断不算丢条，只如实记一笔
            elif clean is None:
                reasons.append(why)
    # 【task-118 A.2】不可信条目的 `last_seq` 钳到 `max(可信 last_seq) + 1`：
    # 结构性防止"外部写一个 999999 就排到注入列表首位"。整库都不可信（旧格式）时
    # 上界取 1 ⇒ 仍然可见、但永远排不到可信条目前面。
    trusted_seq = [int(it.get("last_seq") or 0) for it in kept if _is_trusted_lesson(it)]
    ceiling = (max(trusted_seq) + 1) if trusted_seq else 1
    untrusted = 0
    for it in kept:
        if _is_trusted_lesson(it):
            continue
        untrusted += 1
        if int(it.get("last_seq") or 0) > ceiling:
            it["last_seq"] = ceiling
            it["untrusted"] = True
            reasons.append("clamped:last_seq")
    if report is not None:
        report["dropped"] = dropped
        report["reasons"] = reasons[:LESSONS_REJECT_REASONS_MAX]
        report["untrusted"] = untrusted
    return prune_lessons(kept), ""


def save_lessons_file(path: Any, lessons: Iterable[Mapping[str, Any]] | None,
                      *, report: dict[str, Any] | None = None) -> str:
    """写跨日教训库（task-82）。**绝不抛**：成功 ⇒ `""`，失败 ⇒ 原因串。

    先写临时文件再 `replace` ⇒ 中途崩掉不会留下半截 JSON（"文件损坏"面里最讨厌的一种）。

    【task-118 A.4 防洗白】只持久化 `src == LESSON_SRC` 的条目：外部改写过（或旧格式）的
    条目这一轮也许被读到、也许在内存里还在（用于填位展示），但**绝不**因为"被我们读过一次"
    就被重新盖戳写回文件。传了 `report` 时回填 `{"written": 写了几条, "skipped": 跳了几条}`。
    """
    items: list[dict[str, Any]] = [dict(it) for it in (lessons or ()) if isinstance(it, Mapping)]
    kept = [it for it in items if it.get("src") == LESSON_SRC]
    if report is not None:
        report["written"] = len(kept)
        report["skipped"] = len(items) - len(kept)
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        payload = {"lessons": kept}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    except Exception as exc:  # noqa: BLE001
        return f"write_failed:{type(exc).__name__}: {exc}"
    return ""


def _sanitize_gap(item: Any, notes: list[str]) -> dict[str, Any] | None:
    """【task-219】把磁盘上的一条缺口记录过一遍自己的 schema；不合 ⇒ None（丢）。"""
    if not isinstance(item, Mapping):
        notes.append("not_a_mapping")
        return None
    kind = str(item.get("kind") or "").strip()[:GAPS_TEXT_MAX_CHARS // 2]
    tool = str(item.get("tool") or "").strip()[:24]
    reason = str(item.get("reason") or "").strip()[:40]
    if not kind or not reason:
        notes.append("missing_kind_or_reason")
        return None
    try:
        count = int(item.get("count") or 0)
    except Exception:  # noqa: BLE001
        notes.append("bad_count")
        return None
    if count < 1:
        notes.append("bad_count")
        return None
    sample: list[list[int]] = []
    raw_tiles = item.get("sample_tiles")
    if isinstance(raw_tiles, list):
        for pair in raw_tiles[:GAPS_SAMPLE_TILES]:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                try:
                    sample.append([int(pair[0]), int(pair[1])])
                except Exception:  # noqa: BLE001
                    continue
    return {
        "kind": kind,
        "tool": tool,
        "reason": reason,
        "count": count,
        "first_seen": str(item.get("first_seen") or "")[:40],
        "last_seen": str(item.get("last_seen") or "")[:40],
        "sample_tiles": sample,
        "src": LESSON_SRC if item.get("src") == LESSON_SRC else "",
    }


def _archive_bad_gaps_file(path: Path, *, report: dict[str, Any] | None = None) -> str:
    """【task-230 P0-4.4】把坏掉的 `<journal>-gaps.json` 改名成 `<name>.bad.<ts>`。

    为什么必须归档而不是静默丢弃：坏文件是**事故证据**（并发写/磁盘/被外部改），
    静默丢会让"为什么缺口永远不累积"永远查不出来。归档**不覆盖**原文件内容，
    只把它挪开，下一次写盘会在原路径重建（新 run 从空开始，符合"run 边界不继承"）。

    返回归档后的路径字符串；失败返回 `""`（并把失败原因写进 `report["archive_failed"]`，
    绝不抛 —— 与整个 gaps 层"不影响判定"的纪律一致）。
    """
    try:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        dest = path.with_name(f"{path.name}.bad.{stamp}")
        path.replace(dest)
        if report is not None:
            report["archived_to"] = str(dest)
        return str(dest)
    except Exception as exc:  # noqa: BLE001 - 归档失败也不许影响主流程
        if report is not None:
            report["archive_failed"] = f"{type(exc).__name__}: {exc}"
        return ""


def load_gaps_file(path: Any,
                   *, report: dict[str, Any] | None = None) -> tuple[dict[str, dict[str, Any]], str]:
    """读本 run 的能力缺口清单（task-219/230，`<journal>-gaps.json`）。**绝不抛**。

    返回 `{(kind, tool, reason): {...}}`；缺文件 ⇒ `({}, "")`；坏 JSON / schema 不符 /
    条目类型错 ⇒ **整份丢弃**并把原因回填 `report["reason"]`（调用方记一笔 journal 后照常跑）。
    【task-230 P0-4.4】坏 JSON / 坏 schema 还会**归档成 `<name>.bad.<ts>`**
    （`report["archived_to"]` 报给调用方记 journal），绝不静默覆盖或删除。
    与教训库同一条信任边界：磁盘文件**绝不许决定任何判定**，只用来填提示词。
    """
    if report is not None:
        report["dropped"] = 0
        report["reasons"] = []
    try:
        p = Path(path)
    except Exception as exc:  # noqa: BLE001
        return {}, f"bad_path:{type(exc).__name__}"
    if not p.exists():
        return {}, ""
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        archived = _archive_bad_gaps_file(p, report=report)
        tail = f"（已归档到 {archived}）" if archived else "（归档失败，文件保留原样）"
        return {}, f"read_failed:{type(exc).__name__}: {exc}{tail}"
    if not isinstance(raw, Mapping) or raw.get("schema") != GAPS_SCHEMA:
        archived = _archive_bad_gaps_file(p, report=report)
        tail = f"（已归档到 {archived}）" if archived else "（归档失败，文件保留原样）"
        return {}, f"bad_schema{tail}"
    items = raw.get("gaps")
    if not isinstance(items, list):
        archived = _archive_bad_gaps_file(p, report=report)
        tail = f"（已归档到 {archived}）" if archived else "（归档失败，文件保留原样）"
        return {}, f"not_a_list{tail}"
    out: dict[str, dict[str, Any]] = {}
    dropped = 0
    reasons: list[str] = []
    for item in items:
        notes: list[str] = []
        clean = _sanitize_gap(item, notes)
        if clean is None:
            dropped += 1
            reasons.extend(notes)
            continue
        key = f"{clean['kind']}|{clean['tool']}|{clean['reason']}"
        out[key] = clean
    if report is not None:
        report["dropped"] = dropped
        report["reasons"] = reasons[:6]
    if not out:
        return {}, ""
    return out, ""


def save_gaps_file(path: Any, gaps: Any, *, report: dict[str, Any] | None = None) -> str:
    """写本 run 的能力缺口清单（task-219）。**绝不抛**：成功 ⇒ `""`，失败 ⇒ 原因串。

    先写临时文件再 `replace`（与教训库/认输记录同一纪律：中途崩掉不留半截 JSON）。
    只持久化 `src == LESSON_SRC` 的条目（外部改写过的条目绝不因为"被读过一次"就回写）。
    """
    items: list[dict[str, Any]] = []
    if isinstance(gaps, Mapping):
        raw = gaps.values()
    else:
        raw = gaps or ()
    for it in raw:
        if isinstance(it, dict):
            items.append(dict(it))
    kept = [it for it in items if it.get("src") == LESSON_SRC]
    kept.sort(key=lambda it: (-int(it.get("count") or 0),
                              str(it.get("last_seen") or ""), str(it.get("kind") or "")))
    kept = kept[:GAPS_MAX_ITEMS]
    if report is not None:
        report["written"] = len(kept)
        report["skipped"] = len(items) - len(kept)
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        payload = {"schema": GAPS_SCHEMA, "gaps": kept}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    except Exception as exc:  # noqa: BLE001
        return f"write_failed:{type(exc).__name__}: {exc}"
    return ""


SCOPE_SCHEMA = "agentfarm-scope/1"


def load_scope_file(path: Any,
                    *, report: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """读跨日"规模取舍"记录（task-168，`<journal>-scope.json`）。**绝不抛**。

    返回 `{zone: {"since_day", "tiles", "live_crops_at_shed", "reason"}}`；缺文件 ⇒ `{}`；
    schema 不符 / JSON 坏 / 条目字段类型错 ⇒ **整份丢弃**并把原因回填 `report["reason"]`
    （调用方记 `scope_rejected` 后照常跑）。

    【task-192】可选的 `shed_ever`（本 run **曾经**认输过的每区格数）不随返回值走，而是回填
    `report["shed_ever"]`：释放会把区从 `zones` 里摘掉，只看 `zones` 的话"认输→释放→再认输"
    就能绕过累计 34% 上界 ⇒ 这一份累计量必须单独持久化。它不合法时**整份拒收**（`bad_shed_ever`），
    与其它字段同一纪律；旧文件没这个键 ⇒ `report["shed_ever"]` 为 `{}`，调用方按当前认输集兜底。

    【信任边界（照 `load_lessons_file`）】这是磁盘上的外部文件：**绝不让它决定判定**。
    只用来"跨日记住今天主动放弃了哪个区"，任何一处不合 schema 就整份不认 —— 宁可当天重新
    评估（可能又认输一次、如实留痕），也不拿一个可疑文件当免罚依据。
    """
    if report is not None:
        report["reason"] = ""
        report["zones"] = 0
    try:
        p = Path(path)
    except Exception as exc:  # noqa: BLE001
        if report is not None:
            report["reason"] = f"bad_path:{type(exc).__name__}"
        return {}
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        if report is not None:
            report["reason"] = f"read_failed:{type(exc).__name__}: {exc}"
        return {}
    if not isinstance(raw, Mapping) or raw.get("schema") != SCOPE_SCHEMA:
        if report is not None:
            report["reason"] = "bad_schema"
        return {}
    zones = raw.get("zones")
    if not isinstance(zones, Mapping):
        if report is not None:
            report["reason"] = "zones_not_mapping"
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, item in zones.items():
        if not isinstance(name, str) or not name or not isinstance(item, Mapping):
            if report is not None:
                report["reason"] = "bad_entry"
            return {}
        tiles = item.get("tiles")
        live = item.get("live_crops_at_shed")
        reason = item.get("reason")
        if not isinstance(tiles, int) or isinstance(tiles, bool) or tiles < 0:
            if report is not None:
                report["reason"] = "bad_tiles"
            return {}
        if not (live is None or (isinstance(live, int) and not isinstance(live, bool))):
            if report is not None:
                report["reason"] = "bad_live_crops"
            return {}
        if not isinstance(reason, str) or not reason:
            if report is not None:
                report["reason"] = "bad_reason"
            return {}
        # 【task-168 F-X1】格清单（可选但**必须**在时合法）：重启后靠它把
        # `shed_zone_tiles` 灌回来，否则"整 run 累计 ≤34%"的上界一重启就归零。
        raw_list = item.get("tile_list")
        tile_list: list[tuple[int, int]] = []
        if raw_list is not None:
            if not isinstance(raw_list, (list, tuple)):
                if report is not None:
                    report["reason"] = "bad_tile_list"
                return {}
            for pair in raw_list:
                if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                        or isinstance(pair[0], bool) or isinstance(pair[1], bool)
                        or not isinstance(pair[0], int) or not isinstance(pair[1], int)):
                    if report is not None:
                        report["reason"] = "bad_tile_pair"
                    return {}
                tile_list.append((int(pair[0]), int(pair[1])))
        out[name] = {"since_day": item.get("since_day"), "tiles": tiles,
                     "live_crops_at_shed": live, "reason": reason,
                     "tile_list": tuple(tile_list)}
    ever_raw = raw.get("shed_ever")
    if ever_raw is not None:
        if not isinstance(ever_raw, Mapping):
            if report is not None:
                report["reason"] = "bad_shed_ever"
            return {}
        for name, count in ever_raw.items():
            if (not isinstance(name, str) or not name
                    or not isinstance(count, int) or isinstance(count, bool) or count < 0):
                if report is not None:
                    report["reason"] = "bad_shed_ever"
                return {}
    if report is not None:
        report["zones"] = len(out)
        report["shed_ever"] = dict(ever_raw) if isinstance(ever_raw, Mapping) else {}
    return out


def save_scope_file(path: Any, zones: Mapping[str, Mapping[str, Any]], *,
                    journal_stem: str = "", report: dict[str, Any] | None = None,
                    ever: Mapping[str, Any] | None = None) -> str:
    """原子写规模取舍记录（task-168）。**绝不抛**：成功 ⇒ `""`，失败 ⇒ 原因串。

    先写 `.tmp` 再 `replace`（与 `save_lessons_file` 同一纪律）：中途崩掉不会留下半截 JSON
    —— 半截文件下次会被 `load_scope_file` 整份拒收，等于把"主动放弃"的记忆静默清空。

    `ever`（【task-192】本 run 曾经认输过的每区格数）随文件一起落盘：释放会把区从 `zones`
    里摘掉，但累计 34% 上界必须记住它，否则"认输 → 释放 → 再认输"就能无限认输。
    """
    payload: dict[str, Any] = {"schema": SCOPE_SCHEMA, "journal": str(journal_stem or "")}
    clean: dict[str, dict[str, Any]] = {}
    for name, item in (zones or {}).items():
        if not isinstance(name, str) or not name or not isinstance(item, Mapping):
            continue
        clean[name] = {
            "since_day": item.get("since_day"),
            "tiles": int(item.get("tiles") or 0),
            "live_crops_at_shed": item.get("live_crops_at_shed"),
            "reason": str(item.get("reason") or ""),
            "tile_list": [[int(t[0]), int(t[1])] for t in (item.get("tile_list") or ())
                          if isinstance(t, (list, tuple)) and len(t) == 2],
        }
    payload["zones"] = clean
    ever_clean: dict[str, int] = {}
    for name, count in (ever or {}).items():
        try:
            n = int(count)
        except Exception:  # noqa: BLE001 - 坏条目就丢掉这一条，不影响落盘
            continue
        if isinstance(name, str) and name and n >= 0:
            ever_clean[name] = n
    payload["shed_ever"] = ever_clean
    if report is not None:
        report["written"] = len(clean)
        report["ever"] = len(ever_clean)
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    except Exception as exc:  # noqa: BLE001
        return f"write_failed:{type(exc).__name__}: {exc}"
    return ""


def decision_line(
    *,
    day_key: Any = None,
    boundary: str = "",
    intents: Iterable[Any] = (),
    verdict_counts: Mapping[str, int] | None = None,
    outcome: str = "",
    ended_by: str = "",
    ended_reason: str = "",
    terminal: Mapping[str, int] | None = None,
    leftover: int | None = None,
    unreachable: int | None = None,
    refused: int | None = None,
    where: str = "",
    max_chars: int = DECISION_LINE_MAX_CHARS,
) -> str:
    """把一条边界决策拍成**一行、无坐标**的决策史（task-58 / task-82 补 join）。

    只搬运上层已经算好的东西：意图（`task` + 可选 `area_hint`）、校验关口的
    `keep/unknown/cancel` 计数、当天的结局（`VERIFIED`/`needs_review`）与收尾原因；
    task-82 再补上"决策→结果"的 join 摘要：当天的 `terminal` 计数、`leftover` /
    `unreachable` / `refused` 数量、以及**具名田区**（`where`，如 `field_ne`）。
    **这里不观测、不判断、也不许出现坐标** —— 它是"给模型看的战绩摘要"，
    不是新的真值来源；`where` 也会再洗一遍坐标。
    """
    tasks: list[str] = []
    for it in intents or ():
        task = str(getattr(it, "task", "") or "")
        if not task:
            continue
        hint = str(getattr(it, "area_hint", "") or "")
        tasks.append(f"{task}@{hint}" if hint else task)
    counts = dict(verdict_counts or {})
    vtxt = "/".join(f"{k}{int(counts.get(k) or 0)}"
                    for k in ("keep", "unknown", "cancel") if int(counts.get(k) or 0))
    day = ""
    if day_key:
        try:
            day = f"{day_key[1]} {day_key[2]}"
        except Exception:  # pragma: no cover - day_key 形态异常时退化成空
            day = str(day_key)
    parts = [
        f"{day} {boundary}".strip(),
        "intents=[" + ",".join(tasks) + "]" if tasks else "intents=[]",
        f"verdicts={vtxt}" if vtxt else "",
    ]
    # 【task-82】决策→结果的 join 摘要（每一条都是上层从账本里数出来的，这里只排版）。
    # `terminal` 在场时不再单列 `outcome=`（同一件事，前者更细）。
    term = {str(k): int(v or 0) for k, v in (terminal or {}).items() if int(v or 0)}
    if term:
        parts.append("terminal=" + "/".join(f"{k}{v}" for k, v in sorted(term.items())))
    elif outcome:
        parts.append(f"outcome={outcome}")
    nums = [f"{name}={int(val)}" for name, val in
            (("leftover", leftover), ("unreachable", unreachable), ("refused", refused))
            if val]
    if nums:
        parts.append(" ".join(nums))
    area = _strip_coordinates(str(where or "")).strip()
    if area:
        parts.append(f"where={area}")
    reason = " ".join(str(ended_reason or "").split())
    # 【task-58】`ended_reason` 来自执行层，某些诚实文案里**点名过坐标**（如"坐标都够不着
    # （如 [12,30]）"）。决策史是要回填进提示词的 ⇒ 坐标一律洗成"某格"（prompt 契约：
    # 坐标只由代码算，绝不进提示词；见 `Brief` 的模块文档与 `find_coordinate_like`）。
    for _ in range(8):
        hit = find_coordinate_like(reason)
        if not hit:
            break
        reason = reason.replace(hit, "某格")
    # 先给"为什么"留位置：它比 `ended_by` 信息量大，被末尾截断掉最不划算。
    reason = reason[:40]
    if ended_by:
        parts.append(f"ended_by={ended_by}")
    if reason:
        parts.append(f"why={reason}")
    return " ".join(p for p in parts if p)[: int(max_chars)]


#: 需要清掉的障碍种类（`tiles[].kind`）
OBSTACLE_KINDS: tuple[str, ...] = ("weed", "twig", "stone", "tree", "fruitTree", "clump", "grass", "bush")

#: 【task-218 护栏 A】`OBSTACLE_KINDS` 里**显式说明性跳过**的种类 → 理由 + 缺什么能力。
#:
#: 结构性护栏（`tests/` 里的意图-执行对账用例）会遍历 `OBSTACLE_KINDS ∪ CLUMP_KINDS`：
#: 每一类要么能被 `farmwork.clear()` 真的产出可执行目标，要么必须登记在这里 ——
#: 登记了还要在简报里如实说"暂时清不了 + 原因"。**绝不允许静默跳过**
#: （旧实现把 `tree` 放在 `farmwork.SKIP_KINDS` 里，LLM 看到"树算阻塞"、它也确实输出
#: `clear_area`，实现层却悄悄跳过 ⇒ 十几年轮没人砍树，用户 m18938/m18962 因此发问）。
DEFERRED_KINDS: dict[str, str] = {
    "fruitTree": "果树不当障碍处理（砍掉会毁掉果树产出；需要玩家确认才动）",
    "bush": "灌木暂不当障碍清理（会掉浆果，留给余力多清阶段）",
}


def capability_gaps(
    *,
    obstacle_kinds: Iterable[str] = OBSTACLE_KINDS,
    clearable_kinds: Iterable[str] | None = None,
    deferred_kinds: Iterable[str] | None = None,
    not_clearable_kinds: Iterable[str] | None = None,
) -> list[str]:
    """【task-218 护栏 A / 0.7.39 P0-2】列出"意图层说要清、实现层却没人认领"的 kind。

    判据（每一类必须落进三桶之一，**绝不允许静默跳过**）：

    * `clearable_kinds` —— 实现层真能产出可执行目标（`farmwork.clear()` 会挥）；
    * `deferred_kinds` —— 明确"暂不支持"，且简报会如实公告"<kind> 存在但暂不支持清理（原因）"；
    * `not_clearable_kinds` —— 设计上就不该动（放置物/机器等）。

    返回的 kind 名单就是缺口；测试里"故意漏登记某 kind"必须让这份名单非空。
    """
    clearable = set(clearable_kinds if clearable_kinds is not None else ())
    deferred = set(deferred_kinds if deferred_kinds is not None else DEFERRED_KINDS)
    not_clearable = set(not_clearable_kinds if not_clearable_kinds is not None else ())
    gaps: list[str] = []
    for kind in obstacle_kinds:
        if kind in clearable or kind in deferred or kind in not_clearable:
            continue
        gaps.append(str(kind))
    return sorted(gaps)

_EMPTY_COUNTS: dict[str, int] = {
    "weeds": 0, "twigs": 0, "stones": 0, "trees": 0, "grass": 0, "bush": 0,
    # 【task-218 / 0.7.39 P0-1】旧口径把 tree/fruitTree/clump 全塞进 `trees`，
    # 于是"树多到挡种植"和"果树/树桩"在简报里是一个数字 ⇒ 模型无法分辨该不该砍。
    # 拆成独立桶（观测 `farm` 段没有这些计数时保持 0，不猜）。
    "fruit_trees": 0, "clumps": 0,
    "blockers": 0, "dirt": 0, "plantable": 0, "crops": 0, "ripe": 0, "dead": 0,
    "unwatered_crops": 0, "wet_crops": 0, "tillable": 0,
}

_SEED_HINTS: tuple[str, ...] = ("seed", "种子")


def _is_seed_item(item: Mapping[str, Any]) -> bool:
    """背包里这件东西像不像种子。名字里带 seed / 种子 就算（不硬编码 ItemId）。"""
    if item.get("isTool"):
        return False
    name = str(item.get("name") or "").lower()
    return any(hint in name for hint in _SEED_HINTS)


@dataclass(frozen=True)
class Brief:
    """给慢脑看的**情境简报**——只有"已观测真值"，**一个坐标都不许有**。

    【为什么刻意不放玩家坐标】`player.tile` 是坐标，放进来就等于给 LLM 示范"坐标是可以出现的"；
    技能层要用坐标会自己去 observe 拿，简报不需要。
    """

    location: str = ""
    is_farm: bool = False
    has_save: bool = False
    day_key: tuple[int, str, int] | None = None
    stamina: float | None = None
    max_stamina: float | None = None
    counts: Mapping[str, int] = field(default_factory=dict)
    seed_ids: tuple[str, ...] = ()
    seed_count: int = 0
    inventory_size: int = 0
    tiles_present: bool = False
    anchors: frozenset[str] = frozenset(_BASE_ANCHORS)
    consecutive_failures: int = 0
    last_failure: str = ""
    target_tiles: int = 9
    #: 钱与当前时间 —— 用户 2026-10-11 的要求："还有钱，不是应该买点种子继续种吗"。
    #: 不给这两个数，慢脑根本看不出"再种一轮划不划算"（原来的简报里它们不存在）。
    money: int | None = None
    time_of_day: int | None = None
    #: 具名田区（`field_nw` 这种）：让慢脑能说"去西北那块地"，而**不是**说坐标。
    #: 名字由 `fields.zones_from_observe()` 给（那是唯一真源，planner 不认识坐标）。
    areas: tuple[str, ...] = ()
    #: 每个田区一行人间可读摘要（可锄/待清理/已有作物/待浇水/远近），同样**不含坐标**。
    area_lines: tuple[str, ...] = ()
    #: 【task-42】背包里**今天亲手收获、可以出货**的件数。它**不是**从观测推出来的：
    #: 白名单在 `FarmWorker.harvested` 里（"哪一件是我们自己收进背包的"只有执行层知道），
    #: 长跑控制器把它**注入**进来。所以这个数在直接调 `from_observe()` 的场合恒为 0。
    sellable: int = 0
    #: 【task-58】最近几次边界决策的**一行式战绩**（`decision_line()` 造，**无坐标**）。
    #: 由长跑控制器用**会话内记忆 + 当天账本**维护（重启后允许为空 ⇒ 这一节就不出现）。
    #: ⚠️ 诚实边界：这是「会话内记忆 + 提示词反馈」，**不是**权重更新 / 在线训练 ——
    #: 模型不会因此"学会"，只是这一次会话里能看见自己最近做了什么、结果如何。
    recent_decisions: tuple[str, ...] = ()
    #: 【task-59】昨晚收工复盘留给今天的 1–3 条短笔记（`BoundaryPlanner.review()` 产出，
    #: **无坐标**）。由长跑控制器在夜里回填、次日注入；复盘失败 ⇒ 空（不拿旧笔记冒充昨晚的）。
    #: ⚠️ 与决策史同一条诚实边界：只影响**提示词文本**，绝不参与任何判定。
    recent_notes: tuple[str, ...] = ()
    #: 【task-82】跨日教训库注入的文本节（`render_lessons()` 已渲染好、≤`LESSONS_INJECT_CHARS`）。
    #: 由长跑控制器从 `<journal>-lessons.json` 读取后注入；空 ⇒ 这一节不出现。
    #: ⚠️ 与决策史/复盘笔记同一条诚实边界：只影响**提示词文本**，绝不参与任何判定。
    recent_lessons: str = ""
    #: 【task-219】能力缺口提示（"此前 N 次「树」因工具等级不够没做成（需要斧头等级 2）"）。
    #: 由长跑控制器从 `<journal>-gaps.json` 读出来渲染后注入（≤`GAPS_INJECT_MAX` 条 /
    #: ≤`GAPS_SECTION_MAX_CHARS` 字符）；空 ⇒ 这一节不出现。
    #: ⚠️ 只作**提示**：不进 `checks`、不做豁免、不改 `_leftover`；也**绝不**自动转成教训库条目。
    recent_gaps: tuple[str, ...] = ()
    #: 【task-136 B】复盘提示词专用的「当天事实（账本）」文本（`render_review_facts()` 渲染）。
    #: **只在 `build_review_messages()` 里用**：决策提示词不含它（决策看的是当下的简报）。
    #: 空 ⇒ 复盘 user 段只有简报（旧行为，向后兼容）。
    review_facts: str = ""
    #: 【task-168】工作量缺口（**进提示词**，让慢脑自己看见"今天的活超过一天的体力"）。
    #: 三个都可以是 `None` = **【未观测到】**（farm 计数不可用 / 窗口看不到农场）—— 绝不许当 0：
    #: 0 是"没事"的意思，None 是"不知道"，混起来就会拿未知当绿灯（task-96/99 的老教训）。
    #: 由长跑控制器 `_plot_brief()` 用 `replace(...)` 注入；`from_observe()` **不算**（planner 不依赖
    #: `farmwork` 的体力常量，只认控制器给的真值）。
    live_crops: int | None = None          # 全农场活苗（`farm.crops` 同口径）
    water_capacity: int | None = None      # 一整管体力最多浇几格
    water_deficit: int | None = None       # `max(0, live_crops - water_capacity)`
    #: 【task-168】各田区的（未浇活苗格数, 该区格数）——确定性"认输哪一个区"的代理指标。
    #: 同样由控制器注入；直接调 `from_observe()` 时恒空 ⇒ 不提议认输（fail-closed）。
    area_facts: tuple[tuple[str, int, int], ...] = ()
    #: 【task-218 护栏 A】当前观测里**存在但暂不支持清理**的障碍种类（`DEFERRED_KINDS` 的键）。
    #: 由 `from_observe()` 从 `tiles[].kind` 算出（`tiles` 缺失时恒空，因为 summary 快照分不清
    #: 果树/灌木）。它进简报核心字段 ⇒ 模型能看见"这棵树/灌木我知道，但今天清不了（原因）"，
    #: 而不是以为"没有障碍"或反复输出清不掉的任务。
    deferred_kinds: tuple[str, ...] = ()

    # ---- 派生量（确定性策略用） ----
    @property
    def blockers(self) -> int:
        return int(self.counts.get("blockers", 0))

    @property
    def tillable(self) -> int:
        return int(self.counts.get("tillable", 0))

    @property
    def unprepared(self) -> int:
        """还没开垦的地（已有耕地 + 已种作物都算已准备）。"""
        return max(0, int(self.target_tiles) - int(self.counts.get("dirt", 0)) - int(self.counts.get("crops", 0)))

    @property
    def has_seeds(self) -> bool:
        return self.seed_count > 0 or bool(self.seed_ids)

    # ---- 文本化（进 prompt，且必须 ≤2 KB） ----
    def base_lines(self) -> list[str]:
        """简报本体（不含决策史）：这些字段**一个都不许被决策史挤掉**。"""
        lines = [
            f"location={self.location or 'unknown'} is_farm={self.is_farm}",
            f"has_save={self.has_save} day_key={self.day_key}",
            f"stamina={self.stamina}/{self.max_stamina}",
            f"money={self.money} time_of_day={self.time_of_day}",
            f"counts={json.dumps(dict(sorted(self.counts.items())), ensure_ascii=False)}",
            f"tiles_present={self.tiles_present} target_tiles={self.target_tiles}",
            f"inventory_items={self.inventory_size} seeds={list(self.seed_ids)} seed_count={self.seed_count}",
            f"recent_failures={self.consecutive_failures} last_failure={self.last_failure or '-'}",
        ]
        if self.areas:
            # 田区摘要放在中段：既让模型有"方向"可选，又不至于被末尾截断吃掉
            lines.append(f"areas={list(self.areas)}")
            lines.extend(f"- {line}" for line in self.area_lines)
        # 【task-168】工作量缺口 —— 属**核心事实**（不是可选节）：模型必须能看出"今天浇不完"。
        # 三个数任一拿不到就照实写「未观测到」，**绝不许**用 0 冒充（0 = 没事，None = 不知道）。
        if self.live_crops is None or self.water_capacity is None or self.water_deficit is None:
            lines.append("water_budget: live_crops=未观测到 water_capacity=未观测到 water_deficit=未观测到")
        else:
            lines.append(f"water_budget: live_crops={self.live_crops} "
                         f"water_capacity={self.water_capacity} water_deficit={self.water_deficit}")
        # 【task-218 护栏 A】暂不支持清理的种类必须在**核心字段**里如实出现（不是可选节）：
        # 模型据此知道"这格我看见了，但今天动不了 + 为什么"，而不是以为没活或反复提清不掉的任务。
        for kind in self.deferred_kinds:
            lines.append(f"{kind} 存在但暂不支持清理（{DEFERRED_KINDS.get(kind, '原因未登记')}）")
        return lines

    def decisions_text(self) -> str:
        """决策史一节（【task-58】，≤ `DECISIONS_MAX_CHARS`）；空 ⇒ 返回空串（不出现空节）。

        从**最新**往回收，保证最近的那条一定在；塞不下的老条目先丢。
        """
        if not self.recent_decisions:
            return ""
        head = "recent_decisions（你自己最近的边界决策与结局）:"
        text = head
        for line in reversed(tuple(self.recent_decisions)):
            item = f"\n- {line}"
            if len(text) + len(item) > DECISIONS_MAX_CHARS:
                break
            text += item
        # 连一条都放不下：宁可整节不出现，也不发一个只有标题的空节
        return text if text != head else ""

    def lessons_section(self) -> str:
        """【task-82】跨日教训一节（≤ `LESSONS_SECTION_MAX_CHARS`）；空 ⇒ 空串（不出现空节）。"""
        text = str(self.recent_lessons or "")
        if not text:
            return ""
        return text[:LESSONS_SECTION_MAX_CHARS]

    def notes_text(self) -> str:
        """【task-59】复盘笔记一节（≤ `NOTES_SECTION_MAX_CHARS`）；空 ⇒ 空串（不出现空节）。"""
        if not self.recent_notes:
            return ""
        head = "recent_notes（你自己昨晚收工时的复盘笔记）:"
        text = head
        for note in tuple(self.recent_notes):
            item = f"\n- {note}"
            if len(text) + len(item) > NOTES_SECTION_MAX_CHARS:
                break
            text += item
        return text if text != head else ""

    def gaps_text(self) -> str:
        """【task-219】能力缺口一节（≤ `GAPS_SECTION_MAX_CHARS`）；空 ⇒ 空串（不出现空节）。

        **只作提示**：让慢脑知道"这类活之前反复做不成、缺什么能力"，别再把同一条注定
        失败的任务提一整天。它不进 `checks`、不做豁免、不改 `_leftover`。
        """
        if not self.recent_gaps:
            return ""
        head = "recent_gaps（之前反复没做成的能力缺口）:"
        text = head
        for line in tuple(self.recent_gaps)[:GAPS_INJECT_MAX]:
            item = f"\n- {str(line)[:GAPS_TEXT_MAX_CHARS]}"
            if len(text) + len(item) > GAPS_SECTION_MAX_CHARS:
                break
            text += item
        return text if text != head else ""

    def situation_text(self) -> str:
        """简报全文（进 prompt）【task-58/59/82/219】裁切优先级：

        1. 先保证本体（`base_lines()`）完整；
        2. 可选节只在**本体之后**还有余量时追加，且各自有硬上限
           （教训 `LESSONS_SECTION_MAX_CHARS`、复盘笔记 `NOTES_SECTION_MAX_CHARS`、
           决策史 `DECISIONS_MAX_CHARS`、能力缺口 `GAPS_SECTION_MAX_CHARS`）；
        3. 【task-114 F2，Lead m10474 裁定】保护优先级 = **核心字段 > 教训库 > 决策史 > 复盘笔记**
           （追加顺序即 `(lessons, decisions, notes, gaps)`）：余量不够时先丢能力缺口（task-219
           把它排在**最后**：它只是"提示"，丢了不影响当天判定与安全），再丢复盘笔记、再丢决策史、
           最后才丢教训库；核心字段一个都不许被挤掉（可选节**要么整节进、要么不进**：塞不满余量就丢它，并连同更低优先级的节一起丢，不切半节）。理由：教训是从多天账本攒出来的
           （稀缺、跨日），决策史只覆盖最近几次边界决策，复盘笔记是当晚一次性的、丢了明天还能再写。
        """
        base = "\n".join(self.base_lines())
        tail = ""
        for block in (self.lessons_section(), self.decisions_text(),
                      self.notes_text(), self.gaps_text()):
            if not block:
                continue
            room = PROMPT_BRIEF_MAX_CHARS - len(base) - len(tail) - 1
            if room < len(block):
                # 【task-114 F2】高优先级的节**整节放不下** ⇒ 低优先级的一律不加
                # （不切半节：半截的 `where=…` 行比没有更糟，也让"谁被丢了"一眼可查）。
                break
            tail += f"\n{block}"
        return f"{base}{tail}"[:PROMPT_BRIEF_MAX_CHARS]

    @classmethod
    def from_observe(
        cls,
        observe: Mapping[str, Any],
        *,
        consecutive_failures: int = 0,
        last_failure: str = "",
        target_tiles: int = 9,
        areas: Iterable[str] = (),
        area_lines: Iterable[str] = (),
        sellable: int = 0,
    ) -> "Brief":
        """从 `detail=full` 快照生成简报。

        计数口径：优先用 `location.tiles[]` 的**逐格真值**（P3 头号缺口就是它），
        `tiles` 缺失（summary 快照）时退回 `farm` 段的整场计数，并置 `tiles_present=False`
        让上层知道"这份简报粒度高不了"。

        `areas`/`area_lines` 是具名田区（`farm_areas(observe)` 现算；长跑控制器自己塞）。
        不传就是"这轮没有具名田区"，提示词里会写明、模型也就不会去引用它。
        """
        observe = observe or {}
        location = observe.get("location") or {}
        player = observe.get("player") or {}
        farm = observe.get("farm") or {}

        counts = dict(_EMPTY_COUNTS)
        tiles = location.get("tiles") or []
        tiles_present = bool(tiles)
        kind_key = {
            "weed": "weeds", "twig": "twigs", "stone": "stones", "tree": "trees",
            "fruitTree": "fruit_trees", "grass": "grass", "bush": "bush",
        }
        # 【task-218 / 0.7.39 P0-1】clump 一族（Mod 会按 parentSheetIndex 报具体 kind）
        # 单列一桶，且**它们是障碍** ⇒ 计入 `blockers`（旧口径只认 kind=="clump"，漏了桩/巨石）。
        clump_kinds = ("clump", "stump", "log", "boulder", "rockPile", "greenRain")
        if tiles_present:
            for tile in tiles:
                if not isinstance(tile, Mapping):
                    continue
                kind = tile.get("kind")
                if kind in clump_kinds:
                    counts["clumps"] += 1
                    counts["blockers"] += 1
                else:
                    key = kind_key.get(kind)
                    if key:
                        counts[key] += 1
                    if kind in OBSTACLE_KINDS:
                        counts["blockers"] += 1
                if kind == "dirt":
                    counts["dirt"] += 1
                if tile.get("plantable"):
                    counts["plantable"] += 1
                crop = tile.get("crop")
                if crop:
                    counts["crops"] += 1
                    # 【task-170】"成熟"用**游戏口径** `ready`（Mod：反射 `HoeDirt.readyForHarvest()`），
                    # 不用裸 `ripe`（`fullyGrown`）：复收冷却/阶段没走完/枯死/采集形态 2 的格
                    # 游戏不给收，旧口径会把它们算成熟 ⇒ 策略层也追着摘不到的作物跑。
                    # fail-closed：缺 `ready` 字段（旧 Mod）⇒ 不算成熟（不生成 harvest 意图）。
                    if tile.get("ready") is True:
                        counts["ripe"] += 1
                    if tile.get("dead"):
                        counts["dead"] += 1
                    if tile.get("watered"):
                        counts["wet_crops"] += 1
                    elif not tile.get("dead"):
                        # 【task-84】枯死作物**不算"该浇水"**（用户 m11003：死苗还在被浇）。
                        # 它们单独进 `counts["dead"]`，去处是 `clear_dead`。若不在这里剔除，
                        # `deterministic_plan` 会先给出 `water_area` ⇒ 脑去浇一株没救的苗，
                        # run7 的 `[12,30]` 就是这么被追了一整天。
                        counts["unwatered_crops"] += 1
        else:
            # summary 快照的退回口径：农场段的整场计数（粒度粗，但方向不会错）
            counts["weeds"] = int(farm.get("weeds") or 0)
            counts["stones"] = int(farm.get("stones") or 0)
            counts["twigs"] = int(farm.get("twigs") or 0)
            counts["trees"] = int(farm.get("trees") or 0)
            counts["fruit_trees"] = int(farm.get("fruitTrees") or 0)
            counts["clumps"] = int(farm.get("clumps") or 0)
            counts["blockers"] = (counts["weeds"] + counts["stones"] + counts["twigs"]
                                  + counts["trees"] + counts["fruit_trees"] + counts["clumps"])
            counts["dirt"] = int(farm.get("hoeDirt") or 0)
            counts["crops"] = int(farm.get("crops") or 0)

        tillable = location.get("tillable") or []
        counts["tillable"] = len(tillable)

        inventory = player.get("inventory") or []
        seed_ids: list[str] = []
        seed_count = 0
        for item in inventory:
            if not isinstance(item, Mapping) or not _is_seed_item(item):
                continue
            seed_count += int(item.get("stack") or 0)
            item_id = str(item.get("id") or item.get("qualifiedId") or item.get("name") or "")
            if item_id and item_id not in seed_ids:
                seed_ids.append(item_id)

        anchors = set(_BASE_ANCHORS)
        if location.get("isOutdoorFarm"):
            anchors.add("farm")
        for door in location.get("doors") or []:
            if isinstance(door, Mapping):
                slug = _slug(door.get("type"))
                if slug:
                    anchors.add(slug if slug.endswith("door") else f"{slug}_door")

        day_key = None
        clock = observe.get("clock") or {}
        try:
            if clock.get("year") is not None and clock.get("season") and clock.get("day") is not None:
                day_key = (int(clock["year"]), str(clock["season"]), int(clock["day"]))
        except (TypeError, ValueError):
            day_key = None

        stamina = player.get("stamina")
        max_stamina = player.get("maxStamina")
        # 【task-218 护栏 A / 0.7.39 P0-2⑤】"暂不支持清理"的种类必须**如实公告**，
        # 绝不静默跳过：
        #   * 逐格观测里出现了哪类 ⇒ 只公告哪类（精确）；
        #   * `tiles` 缺失（summary 快照）或**被截断** ⇒ 我们看不见全部窗口 ⇒
        #     fail-closed 公告**全部**已知不可清类（宁可多说一句，也不许让模型以为"没这种活"）。
        deferred: list[str] = []
        if tiles_present:
            present_kinds = {str(t.get("kind") or "") for t in tiles if isinstance(t, Mapping)}
            deferred = [k for k in DEFERRED_KINDS if k in present_kinds]
        if not tiles_present or location.get("tilesTruncated"):
            deferred = list(DEFERRED_KINDS)
        return cls(
            location=str(location.get("name") or ""),
            is_farm=bool(location.get("isOutdoorFarm")),
            has_save=bool(observe.get("hasSaveLoaded")),
            day_key=day_key,
            stamina=float(stamina) if isinstance(stamina, (int, float)) else None,
            max_stamina=float(max_stamina) if isinstance(max_stamina, (int, float)) else None,
            counts=counts,
            seed_ids=tuple(seed_ids),
            seed_count=seed_count,
            inventory_size=len(inventory),
            tiles_present=tiles_present,
            anchors=frozenset(anchors),
            consecutive_failures=int(consecutive_failures or 0),
            last_failure=str(last_failure or ""),
            target_tiles=int(target_tiles or 9),
            money=int(player["money"]) if isinstance(player.get("money"), (int, float)) else None,
            time_of_day=int(clock["timeOfDay"]) if isinstance(clock.get("timeOfDay"), (int, float)) else None,
            areas=tuple(str(a) for a in areas if a),
            area_lines=tuple(str(a) for a in area_lines if a),
            sellable=int(sellable or 0),
            deferred_kinds=tuple(deferred),
        )


# --------------------------------------------------------------------------------------
# 意图 / 状态 / 决策
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class TaskIntent:
    """一条任务意图。**没有坐标、没有动作序列**——展开是技能层的事。"""

    task: str
    area_hint: str
    reason: str = ""
    expected_evidence: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "task": self.task,
            "area_hint": self.area_hint,
            "reason": self.reason,
            "expected_evidence": self.expected_evidence,
        }

    def to_line(self) -> str:
        return f"{self.task} @ {self.area_hint} —— {self.reason}（期望证据：{self.expected_evidence}）"


@dataclass
class PlannerState:
    """跨调用保持的边界状态机状态（**可变**，由 `decide()` 推进）。

    三个字段就是三类边界的判据来源：
      * `day_key` —— 变了 ⇒ 跨日复盘；
      * `last_seen_failures` —— 上升 ⇒ 异常恢复；
      * `last_task_kind` —— **确定性策略**（代码策略的"当前阶段"）变了 ⇒ 换任务类型。
    另有 `llm_calls` 计数器，方便"LLM 调用次数 == 边界次数"这条硬指标被直接断言。

    ⚠️ `last_task_kind` 跟踪的是**代码策略的阶段**，不是 LLM 这次挑了什么。
    否则 LLM 在边界上挑了 `review`、下一步代码策略说 `clear_area`，
    两者永远不相等 ⇒ 每一步都判成"换任务类型"⇒ 每一步都喊慢脑，边界就废了。
    LLM 这次挑了什么记在 `last_decision_kind`，仅作记账/观测用。
    """

    day_key: tuple[int, str, int] | None = None
    last_task_kind: str | None = None
    last_decision_kind: str | None = None
    last_seen_failures: int = 0
    last_boundary: str | None = None
    llm_calls: int = 0
    decisions: int = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "day_key": self.day_key,
            "last_task_kind": self.last_task_kind,
            "last_decision_kind": self.last_decision_kind,
            "last_seen_failures": self.last_seen_failures,
            "last_boundary": self.last_boundary,
            "llm_calls": self.llm_calls,
            "decisions": self.decisions,
        }


@dataclass(frozen=True)
class PlannerDecision:
    """一次 `decide()` 的结果（记账用，可 JSON 化写进开发日志/报告）。"""

    boundary: str | None
    intents: tuple[TaskIntent, ...]
    source: str
    llm_called: bool = False
    fallback_reason: str | None = None
    problems: tuple[str, ...] = ()
    prompt_chars: int = 0
    attempts: int = 0
    rejection: str | None = None
    #: 这次降级**是不是因为回答被 `max_tokens` 截断**（`LlmError:truncated`）。
    #: 单独留一个布尔位，是为了让长跑的 journal 能一眼区分"网络/校验失败"和"提示词太长、
    #: 该调大 token 预算"——后者是配置问题，重试多少次都一样（task-9）。
    truncated: bool = False
    #: 【task-56 决策留痕】真实 LLM 调用的 trace 文件路径 + 该决策最后一条 trace 行的
    #: sha256 前 12 位（`decision` journal 只加这两个字段）。确定性决策 / 没配 trace 时为 ""。
    llm_trace: str = ""
    llm_trace_hash: str = ""
    #: 【task-56】写 trace 失败的原因（成功/未配置时为空）。**失败绝不影响决策**：
    #: 控制器看到它就记一条 `llm_trace_failed` journal，决策本身照常返回。
    llm_trace_error: str = ""

    @property
    def task_kind(self) -> str | None:
        return self.intents[0].task if self.intents else None

    @property
    def degraded(self) -> bool:
        return self.source == SOURCE_DETERMINISTIC_FALLBACK

    # 终态：**决策本身不产生终态**，终端状态归 `classify_outcome()` / `TaskOutcome`。
    # 这里只保留一个"这次决策没崩、有可执行意图"的健康信号，绝不冒充任务完成。
    @property
    def executable(self) -> bool:
        return bool(self.intents)

    def as_dict(self) -> dict[str, Any]:
        return {
            "boundary": self.boundary,
            "source": self.source,
            "llm_called": self.llm_called,
            "fallback_reason": self.fallback_reason,
            "truncated": self.truncated,
            "problems": list(self.problems),
            "prompt_chars": self.prompt_chars,
            "attempts": self.attempts,
            "tasks": [i.as_dict() for i in self.intents],
        }


# --------------------------------------------------------------------------------------
# 终态分类（§5.4：只有 VERIFIED / needs_review）
# --------------------------------------------------------------------------------------
def classify_outcome(
    *,
    postcondition_met: bool,
    skipped: bool = False,
    progress: bool = False,
    error: str | None = None,
) -> str:
    """把一次任务执行结果归到两个终态之一。

    * 后置条件**确实**成立（技能层用 observe 复核过）⇒ `VERIFIED`；
    * 其余一切（被拒/异常/跳步/只推进了进度）⇒ `needs_review`。

    刻意**不**提供第三个"部分完成"状态：需要人看的一律是 needs_review，
    这样"未完成不许报成功""跳过 ≠ 完成"就由类型系统兜住了。
    """
    if postcondition_met and not skipped and not error:
        return TERMINAL_VERIFIED
    # needs_review 的成因（skipped/progress/error）由调用方写进 TaskOutcome.reason；
    # 状态本身刻意只有两个值，防止"部分完成"这种可以冒充成功的第三态漏进来。
    return TERMINAL_NEEDS_REVIEW


@dataclass(frozen=True)
class TaskOutcome:
    """一次任务的执行记账 → 终态。"""

    kind: str
    postcondition_met: bool = False
    skipped: bool = False
    progress: bool = False
    reason: str = ""
    error: str | None = None
    evidence: tuple[str, ...] = ()

    @property
    def terminal(self) -> str:
        return classify_outcome(
            postcondition_met=self.postcondition_met,
            skipped=self.skipped,
            progress=self.progress,
            error=self.error,
        )

    @property
    def verified(self) -> bool:
        return self.terminal == TERMINAL_VERIFIED

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "terminal": self.terminal,
            "postcondition_met": self.postcondition_met,
            "skipped": self.skipped,
            "progress": self.progress,
            "reason": self.reason,
            "error": self.error,
            "evidence": list(self.evidence),
        }


# --------------------------------------------------------------------------------------
# 确定性策略（LLM 的降级底座）
# --------------------------------------------------------------------------------------
def deterministic_plan(brief: Brief) -> tuple[TaskIntent, ...]:
    """纯代码策略：**永远给出可执行的下一步**，不依赖任何网络。

    顺序按"当天不做就永久亏"排：读档 → 体力 → **浇水 → 收获 → 清死苗 → 出货** → 清障 → 开垦 → 播种 → 复盘。
    浇水排在清障/开垦前面是用户 m01770/m01774 的实证要求：作物当天不浇就不长，而清障/开垦
    任何一天都能做；先前把清障/开垦排在前面，真机跑出"体力耗在开垦上、作物没浇完就睡了"。
    每条的 `area_hint` 都是已观测真值的引用（`near:player` / `tillable[0:9]` / `tiles.plantable`），
    落到哪一格由技能层现场判。
    """
    if not brief.has_save:
        return (TaskIntent(
            "wait_for_save", "anchor:current_location",
            "存档没加载，先 load_save 把世界弄回已知状态",
            "observe.hasSaveLoaded 变为 true",
        ),)

    if brief.stamina is not None and brief.stamina <= 0:
        return (TaskIntent(
            "recover_stamina", "anchor:player",
            f"体力只剩 {brief.stamina:g}，再动手也挥不动工具",
            "player.stamina 上升",
        ),)

    if int(brief.counts.get("ripe", 0)) > 0:
        return (TaskIntent(
            "harvest", "tiles.ripe",
            f"有 {brief.counts.get('ripe', 0)} 格作物成熟了，先收掉腾地",
            "location.tiles[].ripe 的格子数量下降",
        ),)

    # 【task-168】规模取舍：今天的活（活苗 × 浇水成本）超过一天的体力 ⇒ **主动认输**最不划算的
    # 一个田区，把体力留给其余田区。确定性代理 = 未浇活苗最多 → 区小 → 名字典序（可复现，无随机）。
    # 只在 `water_deficit` 是**可用的 int > 0** 且至少 2 个田区时才提议：`None`（farm 计数不可用）/
    # `0`（浇得完）/ 单区 ⇒ **一律不提议**（fail-closed，拿不到真值就不许拿"未知"当免罚依据）。
    if (brief.water_deficit is not None and brief.water_deficit > 0
            and len(brief.area_facts) >= 2):
        name, dry, _tiles = max(brief.area_facts, key=lambda kv: (kv[1], -kv[2], kv[0]))
        if dry > 0:
            return (TaskIntent(
                "reduce_scope", name,
                f"今天有 {brief.water_deficit} 格活苗浇不完（最多浇 {brief.water_capacity} 格）；"
                f"先保其余田区，{name} 今天主动不做",
                "该田区不再做目标、守卫不再为它报『还有活』；日终 scope_shed 如实留痕",
            ),)

    # 【task-51 / task-84 位置调整】清掉**枯死**作物，排在**浇水之前**。
    # 位置理由（Lead task-84 卡面建议序 `harvest → clear_dead → water_area → ship → …`）：
    # 死苗占着耕地、挡着 till（`till_blocked_by` 见 crop 就拒），浇水对它是**纯浪费**
    # （用户 m11003："植物过了时间死了变成枯草，还是继续浇水"）；先清掉，当天的浇水
    # 目标集合才只剩"活苗"（`counts["unwatered_crops"]` 也已剔除死苗）。
    # 计数只认观测窗口里 `dead=true` 的格子（Mod 的 farm 级 `deadCrops` 是**农场全量**、
    # 没有坐标 ⇒ 不能拿它当目标；窗口外的死苗由 `clear_dead_scope` journal 留痕）。
    if int(brief.counts.get("dead", 0)) > 0:
        return (TaskIntent(
            "clear_dead", "tiles.dead",
            f"有 {brief.counts.get('dead', 0)} 格枯死作物占着耕地，先清掉才能重种",
            "location.tiles[] 里 dead=true 的作物格数量下降",
        ),)

    if int(brief.counts.get("unwatered_crops", 0)) > 0:
        return (TaskIntent(
            "water_area", "tiles.unwatered_crops",
            f"有 {brief.counts.get('unwatered_crops', 0)} 格作物还没浇水（当天不浇就补不回来）",
            "location.tiles[].watered=true 的作物数量上升",
        ),)

    # 【task-42】收获之后立刻出货（用户 m08335："怎么到现在一分钱也没挣到呀"）。
    # 位置按"当天不做就永久亏"排：钱要**下一次 NewDay** 才结算，越早进箱越早到账；
    # 而清障/开垦/播种任何一天都能做。`sellable` 是执行层注入的白名单件数（不是观测推出来的），
    # 为 0 时这一条根本不会出现 ⇒ 不会凭空下令卖东西。
    if int(brief.sellable) > 0:
        return (TaskIntent(
            "ship", "anchor:current_location",
            f"背包里有 {brief.sellable} 件今天亲手收获、可以出货的东西（卖了才有钱买种子）",
            "shippingBin.count 上升、背包里对应物品减少（钱要下一次 NewDay 才变）",
        ),)

    if brief.blockers > 0:
        return (TaskIntent(
            "clear_area", "near:player",
            f"玩家周围还有 {brief.blockers} 处障碍，先清出能开垦的地",
            "location.tiles[].kind 中 weed/twig/stone/tree 的数量下降",
        ),)

    if brief.unprepared > 0 and brief.tillable > 0:
        return (TaskIntent(
            "till_area", "tillable[0:9]",
            f"目标 {brief.target_tiles} 格里还差 {brief.unprepared} 格没开垦，可锄空格有 {brief.tillable} 个",
            "location.tiles[].kind 中 dirt 数量上升",
        ),)

    if int(brief.counts.get("plantable", 0)) > 0:
        seed_note = f"背包里有 {brief.seed_count} 颗种子" if brief.has_seeds else "⚠️ 背包里没有种子（预计技能层会 precondition_failed ⇒ 触发异常恢复边界）"
        return (TaskIntent(
            "plant_area", "tiles.plantable",
            f"有 {brief.counts.get('plantable', 0)} 格耕地空着；{seed_note}",
            "location.tiles[].crop 非空的格子数量上升",
        ),)

    return (TaskIntent(
        "review", "anchor:current_location",
        f"没有可推进的农务（目标 {brief.target_tiles} 格，当前耕地 {brief.counts.get('dirt', 0)} + 作物 {brief.counts.get('crops', 0)}）",
        "location.tiles[] 的计数在下一次 observe 里保持不变",
    ),)


# --------------------------------------------------------------------------------------
# prompt 构造（≤2 KB，且**不含任何坐标**）
# --------------------------------------------------------------------------------------
SYSTEM_PROMPT = """你是星露谷农务的**任务意图**规划器。你只能输出任务意图，不能输出坐标，也不能输出动作序列。

硬性规则：
1. 只输出 JSON，形如 {"tasks": [{"task": ..., "area_hint": ..., "reason": ..., "expected_evidence": ...}]}。
2. 每条必须**恰好**有这四个字段，不能多也不能少。
3. `task` 只能取：__KINDS__。
4. `area_hint` 只能是下面三类之一（别的写法一律拒收）：
   - 已观测真值的引用：__PREFIXES__（可写成 `前缀.字段`，也可带 `[起:止]` 切片，例如 `tillable[0:9]`）；
   - 相对锚点：__ANCHORS__（写成 `anchor:名字` 或 `near:名字`）；
   - **具名田区**：__AREAS__ —— 这是本农场当下真实存在的田区名，**可以直接写田区名**
     （如 `field_nw`）或 `anchor:field_nw`。想指定"今天去哪片地"就用这一类。
     没列出来的名字不存在，写了会被拒收。
5. **任何格坐标都不许出现**（包括把两个数字用方括号、圆括号或逗号拼在一起，
   包括 `x=` / `y=` 这种赋值，也包括"坐标/格"后面跟数字）。`reason` 与
   `expected_evidence` 里同样不许出现坐标——要用"某字段的计数上升/下降"这种可观测证据来表达。
6. 坐标、走位、动作序列由技能层按当下世界状态计算，你不需要也不许提供。
7. 最多给 3 条任务，按优先级排列。

示例（注意：示例里没有任何坐标）：
__SCHEMA__"""


def build_messages(
    brief: Brief,
    *,
    boundary: str | None = None,
    problems: Sequence[str] | None = None,
    max_chars: int = PROMPT_BRIEF_MAX_CHARS,
) -> list[dict[str, str]]:
    """拼 LLM 消息：system 讲铁律+schema，user 放 ≤2 KB 的情境简报。

    模板用 `__TOKEN__` 占位而不是 `str.format`：提示词正文里本来就有 JSON 花括号，
    用 format 会撞成 KeyError（踩过）。

    ⚠️ 提示词里列的**引用前缀**与**相对锚点**必须与校验器一一对应，且都来自真源：
    前缀取自 `AREA_REF_PREFIXES`、锚点取自 `allowed_area_hints(brief)`。
    分开列是为了让模型看得懂（`anchor:player` 和 `player` 是两种写法），
    而不是像以前那样混在一句"允许的引用之一"里——那样模型会写出校验器不认的
    `{"area_hint": "current_location"}`，被拒收后重问，白烧一次配额
    （真机复现：logs/plan-llm-manual-2.log）。
    """
    system = (
        SYSTEM_PROMPT
        .replace("__KINDS__", ", ".join(TASK_KINDS))
        .replace("__PREFIXES__", ", ".join(AREA_REF_PREFIXES))
        .replace("__ANCHORS__", ", ".join(allowed_area_hints(brief)))
        .replace("__AREAS__", ", ".join(brief.areas) if brief.areas else "（本轮没有具名田区）")
        .replace("__SCHEMA__", PLAN_SCHEMA_EXAMPLE)
    )
    lines = [f"唤醒边界：{boundary or '（无）'}"]
    lines.append("情境简报（仅含已观测真值）：")
    lines.append(brief.situation_text()[: int(max_chars) or PROMPT_BRIEF_MAX_CHARS])
    if problems:
        lines.append("上一次输出被拒收，原因：")
        lines.extend(f"- {p}" for p in problems)
        lines.append("请只修这些原因，重新输出 JSON。")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(lines)}]


def default_llm_chat(messages: Sequence[Mapping[str, str]], **kwargs: Any) -> Any:
    """**唯一**会真的联网的那条路（延迟导入 `llm.chat`，模块导入本身不发请求）。

    用户 m01184：大模型开始介入前要先告知。因此真机/CLI 侧的默认是
    `BoundaryPlanner(llm_enabled=False)`（`python -m agentfarm plan` 不带 `--boundary-llm`）；
    只有显式打开开关、或测试注入假实现之外的场景才会走到这里。
    """
    from .llm import chat  # 延迟导入：只在这里碰网络依赖

    return chat(list(messages), **kwargs)


#: LLM seam 的签名：`(messages, *, model, max_tokens, temperature) -> LlmResult`
ChatFn = Callable[..., Any]

#: 默认重问次数：失败后**重问 1 次**（§5.5），再失败就降级
DEFAULT_MAX_LLM_ATTEMPTS = 2


def _usage_dict(value: Any) -> dict[str, int | None]:
    """【task-56】把 `llm.Usage`（或任何同名字段的映射）拍成留痕口径 `{prompt,completion,total}`。

    **取不到的写 `None`**（卡面要求 null），绝不臆造 0 —— 留痕只负责如实记录，
    也绝不因为读不到用量影响决策。
    """
    if value is None:
        return {"prompt": None, "completion": None, "total": None}

    def pick(*names: str) -> int | None:
        for name in names:
            num = getattr(value, name, None)
            if num is None and isinstance(value, Mapping):
                num = value.get(name)
            if isinstance(num, (int, float)):
                return int(num)
        return None

    return {
        "prompt": pick("prompt_tokens", "prompt"),
        "completion": pick("completion_tokens", "completion"),
        "total": pick("total_tokens", "total"),
    }


class BoundaryPlanner:
    """边界决策状态机 + LLM 适配 seam + 输出校验 + 确定性降级。

    用法（每步 observe 后调一次）：

        planner = BoundaryPlanner(llm_enabled=False)   # 真机默认：不碰 LLM
        state = PlannerState()
        decision = planner.decide(state, brief)         # brief = Brief.from_observe(obs_full)
        for intent in decision.intents: 技能层展开(intent)  # 坐标在这里才算

    生命周期：`state` 由调用方持有；`decide()` 只在**边界**才可能调 LLM，
    非边界纯代码；LLM 任何失败都退回 `deterministic_plan()`，永不抛给主循环。
    """

    def __init__(
        self,
        *,
        llm_chat: ChatFn | None = None,
        llm_enabled: bool = True,
        model: str | None = None,
        # 默认给足：deepseek-flash 是推理模型，实测同一个提示词的思考量在 263～381+ token 之间浮动，
        # 而"上次输出被拒收"的补问会让思考更长。1024 的旧默认值在真机上被截断过
        # （logs/plan-llm-manual-2.log：content 为空、finish_reason=length），白烧一次配额；
        # 4096 也在真机上被吃光过（logs/plan-llm-manual-5.log：简报里带 4 个具名田区、31 格待浇作物时
        # 推理占满 4096、content 为空 ⇒ LlmError:truncated ⇒ 降级成纯代码策略）；
        # 8192 在 run2 真机上**仍然**被吃光过一次（task-9 的 journal 里那次 `deterministic_fallback`）。
        # 值必须与 `llm.DEFAULT_MAX_TOKENS` 一致（有单测钉住），这里写字面量是为了保持
        # "planner 不在导入期碰 llm 模块"的设计（见模块 docstring：网络依赖延迟导入）。
        max_tokens: int = 16384,
        temperature: float | None = 0.0,
        max_llm_attempts: int = DEFAULT_MAX_LLM_ATTEMPTS,
        brief_max_chars: int = PROMPT_BRIEF_MAX_CHARS,
        # 【task-59】收工复盘的独立 token 预算（【task-121】4096，被截断时自愈重试到 8192）。
        # **刻意与 `max_tokens` 分开**：复盘只写 1–3 条短笔记，挪用主决策的 16384 是纯浪费
        # （也不利于把它的失败隔离掉）。
        review_max_tokens: int = REVIEW_MAX_TOKENS,
        # 【task-56】决策留痕文件：**由控制器按 journal 路径推导后传进来**，planner 绝不自己
        # 猜路径（真机是 `<journal 去掉 .jsonl>-llm.jsonl`）。None = 不留痕（单测/`agentfarm plan`
        # 这类一次性调用不需要文件）。
        llm_trace_path: str | Path | None = None,
    ) -> None:
        # 只有"没注入"时才落到默认实现；注入了假实现就绝不会碰 llm.chat
        self.llm_chat: ChatFn = llm_chat or default_llm_chat
        self.llm_enabled = bool(llm_enabled)
        self.model = model
        self.max_tokens = int(max_tokens)
        self.temperature = temperature
        self.max_llm_attempts = max(1, int(max_llm_attempts))
        self.brief_max_chars = int(brief_max_chars)
        self.review_max_tokens = max(1, int(review_max_tokens))
        # 本次 decide 里真实发生的 seam 调用次数（进入 _ask 即 +1，抛异常也算"调了一次"）
        self._calls_seen = 0
        # 【task-56】留痕落点 + 上一次 `_ask` 的元数据（raw/usage/finish_reason/duration_ms）。
        # 后者在 `_ask` 抛异常时也要有值，所以先置空、`_ask` 每次覆盖。
        self.llm_trace_path: Path | None = Path(llm_trace_path) if llm_trace_path else None
        self._last_ask_meta: dict[str, Any] = {}

    def set_trace_path(self, path: str | Path | None) -> None:
        """【task-56】控制器在拿到 journal 路径后回填留痕文件（planner 不知道 journal 在哪）。"""
        self.llm_trace_path = Path(path) if path else None

    # ---- 收工复盘（task-59） ----
    def review(self, brief: Brief) -> dict[str, Any]:
        """【task-59】夜里收工前**一次独立**的复盘调用：只产出 1–3 条次日可见的短笔记。

        与 `decide()` 的关系：完全独立。它**不读也不写** `PlannerState`（不推进边界状态机、
        不碰 `last_boundary`/`last_task_kind`/`day_key`/`llm_calls`），所以复盘发生与否、
        成功与否，都不可能改变下一次决策的边界判定。返回值只被调用方写进 journal
        `review_llm` 与次日 `Brief.recent_notes`。

        【task-121】截断自愈：推理模型的 token 可能全花在思考上、`content` 为空
        （`llm.py` 这时抛 `LlmError(status="truncated")`）。收到这种失败时**用 2 倍预算
        重试一次**（上限 `REVIEW_RETRY_MAX_TOKENS`），仍失败才放弃 —— 保持"失败无害"。

        【task-136 A】真实调用（`called=True`）也会写一行留痕到 `<journal>-llm.jsonl`，
        带 `kind="review"`，字段与决策行同构（`prompt`/`raw`/`usage`/`finish_reason`/
        `duration_ms`/`attempts`/`rejected`/`truncated`）。失败**绝不外抛**：留痕写不进去
        只放到返回值的 `trace_error` 里。

        失败**绝不外抛**（卡面第 3 条：失败无害）：禁用 ⇒ `ok=False, called=False,
        reason="llm_disabled"`；超时/异常 ⇒ `reason` 是 `_describe_failure()` 的原文；
        JSON 非法 ⇒ `reason="review_no_notes"`；成功但一条都没留下 ⇒ 同前。
        返回字典：`{ok, called, reason, notes, text, rejected, truncated, usage, duration_ms,
        model, attempts, max_tokens}`（`attempts` = 实际发了几次请求，`max_tokens` = 最后一次
        用的预算 —— 事后能一眼看出"是不是预算不够"）。
        """
        res = self._review_call(brief)
        if res.get("called"):
            err = self._write_review_trace(res)
            if err:
                res["trace_error"] = err
        return res

    def _write_review_trace(self, res: Mapping[str, Any]) -> str:
        """【task-136 A】把复盘那次真实调用写成一行 trace（`kind="review"`）。

        返回 `""` 表示成功或"没有落点"；写盘失败返回原因串（**绝不影响复盘结果**）。
        """
        prompt = str(res.get("prompt") or "")
        record: dict[str, Any] = {
            "t": round(time.time(), 3),
            "kind": "review",          # 与决策行的 `kind="decision"` 区分（缺省字段名不变）
            "boundary": None,
            "model": str(res.get("model") or self.model or ""),
            "prompt_chars": len(prompt),
            "prompt": prompt[:LLM_TRACE_MAX_PROMPT_CHARS],
            "prompt_truncated": len(prompt) > LLM_TRACE_MAX_PROMPT_CHARS,
            "raw": str(res.get("raw") or ""),
            "usage": dict(res.get("usage") or {"prompt": None, "completion": None, "total": None}),
            "finish_reason": str(res.get("finish_reason") or ""),
            "duration_ms": int(res.get("duration_ms") or 0),
            "attempts": int(res.get("attempts") or 0),
            "rejected": [str(x) for x in (res.get("rejected") or [])],
            "accepted": [],
            "fallback": False,
            "truncated": bool(res.get("truncated")),
            "ok": bool(res.get("ok")),
            "notes": [str(n) for n in (res.get("notes") or [])],
            "max_tokens": int(res.get("max_tokens") or 0),
        }
        _path, _hash, error = self._write_traces([record])
        return error

    def _review_call(self, brief: Brief) -> dict[str, Any]:
        prompt = ""
        messages: list[dict[str, str]] = []
        empty = {"ok": False, "called": False, "reason": "llm_disabled", "notes": [], "text": "",
                 "rejected": [], "truncated": False, "usage": {"prompt": None, "completion": None, "total": None},
                 "duration_ms": 0, "model": str(self.model or ""), "attempts": 0,
                 "max_tokens": int(self.review_max_tokens), "prompt": "", "raw": "",
                 "finish_reason": ""}
        if not self.llm_enabled:
            return empty

        messages = build_review_messages(brief, max_chars=self.brief_max_chars)
        # 【task-136 A】留痕要的是"模型当时看到的那段 user 文本"（system + 简报 + 当天事实）。
        prompt = "\n\n".join(str(m.get("content") or "") for m in messages)
        # 【task-121】预算阶梯：首答被截断（推理吃光 token、正文为空）⇒ 加倍重试一次。
        budgets = [int(self.review_max_tokens)]
        retry_budget = min(max(1, budgets[0] * 2), int(REVIEW_RETRY_MAX_TOKENS))
        if retry_budget > budgets[0]:
            budgets.append(retry_budget)
        started_all = time.monotonic()
        attempts = 0
        used_budget = budgets[0]
        for budget in budgets:
            attempts += 1
            used_budget = budget
            kwargs: dict[str, Any] = {"model": self.model, "max_tokens": budget,
                                      "temperature": self.temperature}
            started = time.monotonic()
            try:
                result = self.llm_chat(messages, **kwargs)
            except BaseException as exc:  # noqa: BLE001 - 复盘任何失败都不许影响睡觉/跨日
                reason = self._describe_failure(exc)
                if getattr(exc, "status", "") == "truncated" and budget is not budgets[-1]:
                    continue          # 预算被推理吃光 ⇒ 换更大预算再来一次
                return {"ok": False, "called": True, "reason": reason, "notes": [],
                        "text": "", "rejected": [], "truncated": False,
                        "usage": {"prompt": None, "completion": None, "total": None},
                        "duration_ms": int((time.monotonic() - started_all) * 1000),
                        "model": str(self.model or ""), "attempts": attempts,
                        "max_tokens": used_budget, "prompt": prompt, "raw": "",
                        "finish_reason": "", "error_status": str(getattr(exc, "status", "") or "")}
            duration_ms = int((time.monotonic() - started) * 1000)
            content = result if isinstance(result, str) else getattr(result, "content", None)
            usage = _usage_dict(getattr(result, "usage", None))
            model = str(getattr(result, "model", "") or self.model or "")
            finish_reason = str(getattr(result, "finish_reason", "") or "")
            duration_ms = duration_ms or int(getattr(result, "elapsed_ms", 0) or 0)
            if content is None:
                return {"ok": False, "called": True, "reason": "llm_result_without_content", "notes": [],
                        "text": "", "rejected": [], "truncated": False, "usage": usage,
                        "duration_ms": duration_ms, "model": model, "attempts": attempts,
                        "max_tokens": used_budget, "prompt": prompt, "raw": "",
                        "finish_reason": finish_reason}
            notes, rejected, truncated = parse_review_notes(content)
            return {
                "ok": bool(notes),
                "called": True,
                "reason": "" if notes else "review_no_notes",
                "notes": notes,
                "text": "；".join(notes),
                "rejected": rejected,
                "truncated": truncated,
                "usage": usage,
                "duration_ms": duration_ms,
                "model": model,
                "attempts": attempts,
                "max_tokens": used_budget,
                "prompt": prompt,
                "raw": str(content),
                "finish_reason": finish_reason,
            }
        # 理论到不了这里（budgets 至少一个元素且每个分支都返回）；保险起见给失败态。
        return dict(empty, called=True, attempts=attempts, max_tokens=used_budget, prompt=prompt)

    # ---- 边界判定 ----
    def detect_boundary(self, state: PlannerState, brief: Brief) -> str | None:
        """返回本次是否处于边界（`None` = 常规区间，纯代码）。"""
        if state.day_key is not None and brief.day_key is not None and brief.day_key != state.day_key:
            return BOUNDARY_NEW_DAY
        if int(brief.consecutive_failures) > int(state.last_seen_failures):
            return BOUNDARY_RECOVERY
        planned = deterministic_plan(brief)
        kind = planned[0].task if planned else None
        if state.last_task_kind is not None and kind is not None and kind != state.last_task_kind:
            return BOUNDARY_TASK_CHANGE
        return None

    # ---- 主入口 ----
    def decide(self, state: PlannerState, brief: Brief) -> PlannerDecision:
        """一次决策。返回值**一定**带可执行意图（除非降级底座也空，实际不会）。"""
        boundary = self.detect_boundary(state, brief)
        fallback = deterministic_plan(brief)
        regime_kind = fallback[0].task if fallback else None
        self._calls_seen = 0
        state.decisions += 1
        prompt_chars = 0
        attempts = 0
        rejection: str | None = None
        problems: tuple[str, ...] = ()

        if boundary is None:
            decision = PlannerDecision(
                boundary=None, intents=fallback, source=SOURCE_DETERMINISTIC,
                llm_called=False, fallback_reason=None,
            )
            self._advance(state, brief, boundary=None, regime_kind=regime_kind, chosen_kind=decision.task_kind)
            return decision

        if not self.llm_enabled:
            decision = PlannerDecision(
                boundary=boundary, intents=fallback, source=SOURCE_DETERMINISTIC_FALLBACK,
                llm_called=False, fallback_reason="llm_disabled",
            )
            self._advance(state, brief, boundary=boundary, regime_kind=regime_kind, chosen_kind=decision.task_kind)
            return decision

        # 【task-56】留痕：每次**真实** LLM 调用攒一条记录，决策定稿后一次性落盘
        # （这样 `fallback` 反映的是"这次决策最终有没有降级"，而不是每条各猜各的）。
        traces: list[dict[str, Any]] = []
        refused: list[str] = []
        for attempt in range(1, self.max_llm_attempts + 1):
            messages = build_messages(brief, boundary=boundary, problems=refused or None, max_chars=self.brief_max_chars)
            user_text = messages[-1]["content"]
            prompt_chars = max(prompt_chars, len(user_text))
            try:
                intents, found = self._ask(messages, allowed_anchors=allowed_area_hints(brief),
                                           allowed_refs=brief.areas)
            except Exception as exc:  # noqa: BLE001 - LlmError / 任何异常都降级，不崩
                attempts = attempt
                rejection = self._describe_failure(exc)
                traces.append(self._trace_record(boundary, user_text, attempt,
                                                 accepted_intents=(), rejected=[rejection]))
                break
            attempts = attempt
            traces.append(self._trace_record(boundary, user_text, attempt,
                                             accepted_intents=intents, rejected=list(found)))
            if intents:
                decision = PlannerDecision(
                    boundary=boundary, intents=tuple(intents), source=SOURCE_LLM,
                    llm_called=True, fallback_reason=None, problems=(), prompt_chars=prompt_chars,
                    attempts=attempt,
                )
                decision = self._stamp_trace(decision, traces)
                self._advance(state, brief, boundary=boundary, regime_kind=regime_kind, chosen_kind=decision.task_kind)
                return decision
            refused = list(found)
            rejection = "; ".join(found)[:500] or "rejected_unknown"

        decision = PlannerDecision(
            boundary=boundary, intents=fallback, source=SOURCE_DETERMINISTIC_FALLBACK,
            llm_called=attempts > 0, fallback_reason=rejection,
            problems=tuple(refused), prompt_chars=prompt_chars, attempts=attempts,
            rejection=rejection,
            truncated=bool(rejection and "truncated" in rejection),
        )
        decision = self._stamp_trace(decision, traces)
        self._advance(state, brief, boundary=boundary, regime_kind=regime_kind, chosen_kind=decision.task_kind)
        return decision

    # ---- 内部 ----
    def _trace_record(
        self,
        boundary: str | None,
        user_text: str,
        attempt: int,
        *,
        accepted_intents: Sequence[TaskIntent],
        rejected: Sequence[str],
    ) -> dict[str, Any]:
        """【task-56】攒一条待落盘的留痕记录（真实 LLM 调用的现场）。

        字段与卡面逐字对齐：`t / boundary / model / prompt_chars / prompt（>8000 截断 +
        prompt_truncated）/ raw / usage（`{prompt,completion,total}`，取不到写 null）/
        finish_reason / duration_ms / attempts / rejected（被拒收的原因数组）/
        accepted（本次真正采用的意图数组）/ fallback（是否降级 + 原因）`。
        `fallback` 先占位，`_stamp_trace()` 按最终决策统一改写。

        ⚠️ `t` 是**墙钟 unix 秒**（`time.time()`），与 journal 里那个**相对起跑的秒**
        不同源，两者**不可直接相减**；跨文件关联一律用 `llm_trace_hash`（journal
        `decision` 行里的那个 12 位 sha256）当键（Lead m05169 裁定①）。
        """
        meta = dict(self._last_ask_meta)
        prompt = str(user_text or "")
        return {
            "t": round(time.time(), 3),
            # 【task-136 A】同一份 trace 文件里现在有两种行：决策（decision）与收工复盘（review）。
            # 新增字段，**不动**既有字段名 ⇒ 现有读法（compare-runs/analyze-longrun/测试）不破；
            # 旧行没有 `kind`，按"决策"处理即可（向后兼容）。
            "kind": "decision",
            "boundary": boundary,
            "model": str(meta.get("model") or self.model or ""),
            "prompt_chars": len(prompt),
            "prompt": prompt[:LLM_TRACE_MAX_PROMPT_CHARS],
            "prompt_truncated": len(prompt) > LLM_TRACE_MAX_PROMPT_CHARS,
            "raw": str(meta.get("raw") or ""),
            "usage": dict(meta.get("usage") or {"prompt": None, "completion": None, "total": None}),
            "finish_reason": str(meta.get("finish_reason") or ""),
            "duration_ms": int(meta.get("duration_ms") or 0),
            "attempts": int(attempt),
            "rejected": [str(x) for x in rejected],
            "accepted": [i.as_dict() for i in accepted_intents],
            "fallback": False,
        }

    def _stamp_trace(self, decision: PlannerDecision, traces: list[dict[str, Any]]) -> PlannerDecision:
        """【task-56】把本次决策攒下的 trace 落盘，并把路径/哈希/失败原因挂到 decision 上。

        写盘失败**绝不影响决策**：错误只放在 `decision.llm_trace_error` 里，由控制器记一条
        `llm_trace_failed` journal。确定性决策（`traces` 为空）不写任何文件。
        `fallback` 写"是否降级 + 原因"：没降级是 `False`，降级则是可读的原因串。
        """
        if not traces:
            return decision
        degraded = decision.source != SOURCE_LLM
        fallback_value: Any = False
        if degraded:
            reason = str(decision.fallback_reason or "").strip()
            fallback_value = f"{decision.source}: {reason}" if reason else decision.source
        for record in traces:
            record["fallback"] = fallback_value
        path_text, last_hash, error = self._write_traces(traces)
        # `PlannerDecision` 是 frozen dataclass ⇒ 用 `replace()` 派生新对象（不许原地改）。
        return replace(decision, llm_trace=path_text, llm_trace_hash=last_hash, llm_trace_error=error)

    def _write_traces(self, traces: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
        """追加写 trace（一行一次真实调用）。返回 `(路径, 最后一行 sha256 前 12 位, 失败原因)`。"""
        path = self.llm_trace_path
        if path is None:
            return "", "", ""
        last_hash = ""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                for record in traces:
                    line = json.dumps(dict(record), ensure_ascii=False, default=str)
                    fh.write(line + "\n")
                    last_hash = hashlib.sha256(line.encode("utf-8")).hexdigest()[:12]
        except Exception as exc:  # noqa: BLE001 - 留痕失败绝不许影响决策
            return str(path), last_hash, f"{type(exc).__name__}: {exc}"[:300]
        return str(path), last_hash, ""

    def _ask(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        allowed_anchors: Sequence[str],
        allowed_refs: Sequence[str] = (),
    ) -> tuple[list[TaskIntent], list[str]]:
        """调一次 seam（**进入即计数**，抛异常也算"真的调了一次"），再解析校验。

        【task-56】顺带把这次调用的元数据（`raw/usage/finish_reason/duration_ms`）记进
        `self._last_ask_meta` —— 抛异常时也先记再抛，留痕才不会漏掉失败的那次。
        """
        chat = self.llm_chat
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature}
        self._calls_seen += 1
        started = time.monotonic()
        try:
            result = chat(messages, **kwargs)
        except BaseException:
            self._last_ask_meta = {
                "model": self.model, "raw": "", "usage": {}, "finish_reason": "",
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
            raise
        duration_ms = int((time.monotonic() - started) * 1000)
        content = result if isinstance(result, str) else getattr(result, "content", None)
        self._last_ask_meta = {
            "model": str(getattr(result, "model", "") or self.model or ""),
            "raw": "" if content is None else str(content),
            "usage": _usage_dict(getattr(result, "usage", None)),
            "finish_reason": str(getattr(result, "finish_reason", "") or ""),
            "duration_ms": duration_ms or int(getattr(result, "elapsed_ms", 0) or 0),
        }
        if content is None:
            return [], [f"llm_result_without_content:{type(result).__name__}"]
        return parse_intents(content, allowed_anchors=allowed_anchors, allowed_refs=allowed_refs)

    def _describe_failure(self, exc: BaseException) -> str:
        status = getattr(exc, "status", None)
        reason = getattr(exc, "reason", None)
        if status or reason:
            return f"llm_error:{status or 'unknown'}: {reason or exc}"[:500]
        return f"llm_exception:{type(exc).__name__}: {exc}"[:500]

    def _advance(
        self,
        state: PlannerState,
        brief: Brief,
        *,
        boundary: str | None,
        regime_kind: str | None,
        chosen_kind: str | None,
    ) -> None:
        """推进状态机（**每个 decide 出口都必须调一次**，否则边界判据会漂）。"""
        state.llm_calls += self._calls_seen
        state.last_seen_failures = int(brief.consecutive_failures)
        if brief.day_key is not None:
            state.day_key = brief.day_key
        if regime_kind is not None:
            state.last_task_kind = regime_kind
        if chosen_kind is not None:
            state.last_decision_kind = chosen_kind
        if boundary is not None:
            state.last_boundary = boundary
