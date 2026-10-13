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

import json
import re
from dataclasses import dataclass, field, replace
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
    "OBSTACLE_KINDS", "Brief", "TaskIntent", "PlannerState", "PlannerDecision",
    # 校验
    "INTENT_FIELDS", "allowed_area_hints", "find_coordinate_like", "validate_intent",
    "parse_intents", "extract_json",
    # 策略与调用
    "deterministic_plan", "PROMPT_BRIEF_MAX_CHARS", "build_messages", "default_llm_chat",
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

#: 需要清掉的障碍种类（`tiles[].kind`）
OBSTACLE_KINDS: tuple[str, ...] = ("weed", "twig", "stone", "tree", "fruitTree", "clump", "grass", "bush")

_EMPTY_COUNTS: dict[str, int] = {
    "weeds": 0, "twigs": 0, "stones": 0, "trees": 0, "grass": 0, "bush": 0,
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
    def situation_text(self) -> str:
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
        text = "\n".join(lines)
        return text[:PROMPT_BRIEF_MAX_CHARS]

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
            "fruitTree": "trees", "clump": "trees", "grass": "grass", "bush": "bush",
        }
        if tiles_present:
            for tile in tiles:
                if not isinstance(tile, Mapping):
                    continue
                kind = tile.get("kind")
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
                    if tile.get("ripe"):
                        counts["ripe"] += 1
                    if tile.get("dead"):
                        counts["dead"] += 1
                    if tile.get("watered"):
                        counts["wet_crops"] += 1
                    else:
                        counts["unwatered_crops"] += 1
        else:
            # summary 快照的退回口径：农场段的整场计数（粒度粗，但方向不会错）
            counts["weeds"] = int(farm.get("weeds") or 0)
            counts["stones"] = int(farm.get("stones") or 0)
            counts["twigs"] = int(farm.get("twigs") or 0)
            counts["trees"] = int(farm.get("trees") or 0)
            counts["blockers"] = counts["weeds"] + counts["stones"] + counts["twigs"] + counts["trees"]
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

    顺序按"当天不做就永久亏"排：读档 → 体力 → **浇水 → 收获** → 清障 → 开垦 → 播种 → 复盘。
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

    if int(brief.counts.get("unwatered_crops", 0)) > 0:
        return (TaskIntent(
            "water_area", "tiles.unwatered_crops",
            f"有 {brief.counts.get('unwatered_crops', 0)} 格作物还没浇水（当天不浇就补不回来）",
            "location.tiles[].watered=true 的作物数量上升",
        ),)

    if int(brief.counts.get("ripe", 0)) > 0:
        return (TaskIntent(
            "harvest", "tiles.ripe",
            f"有 {brief.counts.get('ripe', 0)} 格作物成熟了，先收掉腾地",
            "location.tiles[].ripe 的格子数量下降",
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
    ) -> None:
        # 只有"没注入"时才落到默认实现；注入了假实现就绝不会碰 llm.chat
        self.llm_chat: ChatFn = llm_chat or default_llm_chat
        self.llm_enabled = bool(llm_enabled)
        self.model = model
        self.max_tokens = int(max_tokens)
        self.temperature = temperature
        self.max_llm_attempts = max(1, int(max_llm_attempts))
        self.brief_max_chars = int(brief_max_chars)
        # 本次 decide 里真实发生的 seam 调用次数（进入 _ask 即 +1，抛异常也算"调了一次"）
        self._calls_seen = 0

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
                break
            attempts = attempt
            if intents:
                decision = PlannerDecision(
                    boundary=boundary, intents=tuple(intents), source=SOURCE_LLM,
                    llm_called=True, fallback_reason=None, problems=(), prompt_chars=prompt_chars,
                    attempts=attempt,
                )
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
        self._advance(state, brief, boundary=boundary, regime_kind=regime_kind, chosen_kind=decision.task_kind)
        return decision

    # ---- 内部 ----
    def _ask(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        allowed_anchors: Sequence[str],
        allowed_refs: Sequence[str] = (),
    ) -> tuple[list[TaskIntent], list[str]]:
        """调一次 seam（**进入即计数**，抛异常也算"真的调了一次"），再解析校验。"""
        chat = self.llm_chat
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature}
        self._calls_seen += 1
        result = chat(messages, **kwargs)
        content = result if isinstance(result, str) else getattr(result, "content", None)
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
