# -*- coding: utf-8 -*-
"""长跑控制器：把"观测 → 决策 → 执行 → 验收"连成一个能连续跑好几个游戏日的循环。

【它在整个系统里的位置】
    fields.py   田区（"该去哪片地"）    —— 只报事实，不选动作
    planner.py  意图（"该做什么"）      —— 边界才问 LLM，其余走确定性策略
    farmwork.py 动作（"把这一格做掉"）  —— 发技能 + 观测差分
    longrun.py  日子（"今天干到什么时候、算不算数"）—— 本文件

【三条铁律（否则长跑会自己骗自己）】
1. **一天算不算数，只看观测**：`ended_by == "sleep"`（我们主动睡的，不是被系统 pass-out）
   + 当天没有 `failed` 步骤 + **日级浇水证据通过**（task-19：`checks.watered_outdoor` —— 只有
   `farm.complete==true` 时的 `farm.dryCrops==0`，或当天最后一张户外农场快照里逐格
   `watered==false` 的作物数为 0，才算证据；窗口口径的 `unwatered_crops` 是**旁证**，
   它读 ≤400 格的玩家窗口、在 FarmHouse 里恒 0 —— run2 的 `checks.crops_watered=true` 就是这么
   白过的）。回执不参与判定。
2. **"没事就睡"是不允许的**：只有三种情况放行睡觉 —— 到深夜（`sleep_at`）、体力见底、
   确实找不到任何能干的活（连买种子都做不了）。其余一律**否决并记账**（用户 2026-10-11 的原话：
   "体力还有这么多，田里还有很多需要清理的，直接睡觉不是浪费了吗"）。
3. **规划必须落到一片地上**：`planner.deterministic_plan` 的 `clear_area` 判据是"这块地方还有障碍"——
   如果喂给它**全农场**的计数（真机 245 个障碍），它会永远停在清障、永不进入开垦。
   所以本文件的每个决策都喂"**当天作业区（plot）的局部观测**"，只有"浇水/收获"这两件
   全局必须做完的事才用全量计数（`_plot_brief` 里就是干这个的）。

【已知局限（task-15 §③；写在这里而不是写成断言）】
- **种子闸门的时间成本**：`_preconditions` 在**每个决策之前**跑 ⇒ 正常路径是"**先买再动**"
  （种子为 0 且钱够就 `worker.buy(shop=…)`），不会进了作业区才发现没种子。唯一的墙钟成本是
  那一趟买种子的路（Mod 的 `BuySkill` 自己负责寻路/传送）——**本仓库没有实测数字，不编**：
  它只在"种子 0 且钱够"时发生，一天最多一次、`buy_count` 粒；若这趟没成（店没开/太晚/钱不够），
  当天后续由 `seed_gate`（journal 带 `in_plot`）收场：`in_plot=true` 表示"人已经在田里才发现
  没种子"，那是最贵的路径（白走一趟 + 游戏内时间已经花掉）。这条局限由 Lead 记在开发日志里，
  run3 之后再谈优化；`distance_to_shop` 这类拿不到的数字，一律写"未定"，不猜。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable

from .bridge import MOD_VERSION_EXPECTED, BridgeClient, BridgeError
from .farmwork import (ENV_BLOCK_STATUSES, STAGE_ACTION, FarmWorker, StageResult, StepResult,
                       farm_dead_crops, farm_dry_tiles, seed_items, till_blocked_by)
from .planner import (BoundaryPlanner, Brief, PlannerState, TaskIntent, TaskOutcome,
                      deterministic_plan)

try:  # 田区规划是**可选**依赖：拿不到就退回"玩家周围窗口"，不让长跑起不来
    from . import fields as fields_mod
except Exception:  # pragma: no cover - 只在环境残缺时走到
    fields_mod = None  # type: ignore[assignment]

try:  # watchdog 同样可选（P2 的监督循环，旧账 §5.4：现在把它合进长跑里）
    from .watchdog import LEVEL_STOP, assess, verdict, write_stop_report
except Exception:  # pragma: no cover
    LEVEL_STOP, assess, verdict, write_stop_report = (  # type: ignore[assignment]
        "stop", None, None, None,
    )

__all__ = ["DayReport", "LongRun", "plot_observe"]

#: 用锄头/镰刀**真的清得掉**的障碍。树/果树/资源堆/灌木不在里面：
#: `farmwork.SKIP_KINDS` 会跳过它们（"先用斧头砍"），把它们算成"活"会让这一天永远做不完。
ACTIONABLE_KINDS = ("weed", "twig", "stone", "grass")

#: 看**全场**目标的任务（浇水/收获要伺候所有作物）；其余阶段只看**作业区**。
#: 这个区分决定"没目标"这笔账当天会不会因为换了一片地而作废。
WIDE_TASKS = ("water_area", "harvest")

#: 同一格一天内最多被**发起**几次动作。第 3 次一律不发（用户 m01804："不要白白浪费很多体力"）。
#: 主闸是 `blocked`（第一次"挥了没变/缺工具"就当天封格）；这个上限是**兜底不变量**：
#: 任何一条没被 `blocked` 覆盖的失败路径（例如世界变了但没做成）也不许把同一格磨到天亮。
MAX_TILE_ATTEMPTS = 2

#: 【task-28 防自旋】同一格同一天**连续被环境挡住**（`env_block`：`busy`/`ui_modal`/`no_save`/
#: `world_fading`）超过这个次数以后，就**不再免费**：从下一次起按"没结论"占 `MAX_TILE_ATTEMPTS`
#: 配额。理由：`env_block` 不占配额是刻意的（环境抖动不该封格），但"Mod 一直回 busy"这种
#: **持续**状态如果没有上限，`_stage_tiles` 每轮都会把同一格选出来 ⇒ 一天在同一个格上无限打转。
#: 取 2（而不是 1）是为了给**真实**的瞬时抖动留余量：渐黑/模态通常一次就过去了；连续 3 次以上
#: 还挡着的，判定为"今天这个世界不适合干这格"，让它如实落到 `capped`/`needs_review`。
MAX_ENV_ATTEMPTS = 2

#: 【task-50】同一格"窗口外干作物"一天最多试几次（一次 = 走过去 + 浇一下）。
#:
#: 为什么要这个上限：`farm.dryTiles` 里的格子可能**根本走不到**（农场另一头、
#: 被建筑/水塘隔开），而 `farm.dryCrops > 0` 又不允许判 `no_work`（run5 三天就是这么
#: 全挂的）⇒ 没有上限就会"走过去-失败-再走过去"打到天亮。
#: 取 2 与 `MAX_TILE_ATTEMPTS` 同口径：第一次多半是寻路的一次性抖动，第二次还不行就
#: 认账（当天以 `stuck:` 收尾并点名坐标，而不是洗成"没活"）。
FAR_DRY_MAX_TRIES = 2

#: 【task-11 模态守卫】**只等、绝不 dismiss** 的模态：新一天的自动存档。
#: 真机实测（Lead 2026-10-11 22:2x）：`SaveGameMenu` 自己约 30s 走完 ⇒ `isModal=false`、
#: `worldAdvancing=true`、存档 mtime/size 更新；dismiss 可能**打断存档**，所以只轮询不关。
MODAL_WAIT_ONLY = ("SaveGameMenu", "NewDaySavingMenu")

#: 等待型模态的自走完上限（秒）。真机约 30s，给 3 倍余量；超时就如实停下等人（见下文）。
MODAL_WAIT_TIMEOUT_S = 90.0

#: 一次日循环里最多关几个模态：多个技能同时升级会**连出** `LevelUpMenu`（实测可连出多个）。
MODAL_MAX_DISMISS = 10

#: 挡住当天、必须人来处理的模态（职业选择等不可逆操作）对应的 `ended_by`。
#: 它同时让 `slept_by_us=false` ⇒ 当天**不判 VERIFIED**（宁可停下等人，也不静默丢档）。
ENDED_BY_MODAL = "blocked_modal"

#: 【task-41】`ui.eventUp == true`（游戏事件/剧情对话挂住）对应的 `ended_by`。
#: 真机证据（2026-10-13 19:16–19:19，run4 起跑前）：农场里的流浪宠物认养事件让
#: `eventUp=true` + `DialogueBox`「Hello Jay!」+ `worldAdvancing=false` **135 秒零推进**；
#: 而 Mod 用游戏自己的 `closeDialogue()` 去关第一句时，事件反而把它算作“这句说完了”而
#: **推进**到下一句；若事件里带 `Yes/No`，`ModalDismiss` 的选否口径还会替玩家**默认选“否”**。
#: 两条都不可逆、账本也看不出来 ⇒ 政策改成：**事件一律视为阻断模态，一次都不动手**。
ENDED_BY_EVENT = "blocked_event"

#: 两个“阻断型”收尾：都要人来处理 ⇒ 当天 `slept_by_us=false`、`no_blocking_modal=false`
#: ⇒ `verified=false`，且 `run()` 当场早退（同一天再跑一遍没有意义）。
BLOCKING_ENDS = (ENDED_BY_MODAL, ENDED_BY_EVENT)


def _dist(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _till_blocked_by(tv: dict[str, Any] | None, player: dict[str, Any] | None = None) -> str:
    """兼容别名：判据本体已挪到 `farmwork.till_blocked_by`（与它守着的 `till()` 放一起）。

    【为什么要挪】清障/锄地的"这格现在干不了"判据以前散在 longrun（`_till_blocked_by`）和
    farmwork（`clear()`/`till()` 里的 kind 分支）两处，各写一套；现在统一到动作旁边，
    `_stage_tiles`/`_leftover`/`_plot_has_work` 与 `till()` 用**同一个函数**，口径不会漂。
    这个别名保留给历史调用点与单测（`tests\\test_longrun.py` 直接 import 它）。
    """
    return till_blocked_by(tv, player)


def statuses_of(step: StepResult) -> list[str]:
    """抽出这一步涉及的 Mod status（**只用于 journal 汇总，不做任何判据**）。

    三个来源，按可靠性排序：
    1. `after["statuses"]` —— `FarmWorker.clear()` 会把整轮收到的每个非空 status 收集进这里；
    2. `reason` 里的 `Mod status=x`（`till`/`plant`/`water`/`harvest`/`refill` 会附加）；
    3. 回执前缀 `status: 文本`（`_receipt(exc)` 的格式；拿不到 status 的异常按 `error`）。

    task-22：journal 里要能一眼看出"这一次到底是渐黑、模态，还是超时"，而不是只有一个 failed。
    """
    out: list[str] = []
    after = step.after if isinstance(step.after, dict) else {}
    raw = after.get("statuses") if isinstance(after, dict) else None
    if isinstance(raw, (list, tuple)):
        out.extend(str(x) for x in raw if x)
    reason = step.reason or ""
    i = reason.find("status=")
    while i >= 0:
        tail = reason[i + len("status="):]
        j = 0
        while j < len(tail) and (tail[j].isalnum() or tail[j] == "_"):
            j += 1
        if j:
            out.append(tail[:j])
        i = reason.find("status=", i + 1)
    head = (step.receipt or "").split(":", 1)[0].strip()
    if head and len(head) <= 32 and " " not in head:
        out.append(head)
    uniq: list[str] = []
    for s in out:
        if s and s not in uniq:
            uniq.append(s)
    return uniq


def is_env_blocked(step: StepResult) -> bool:
    """这一步是不是**环境挡路**（渐黑 / 模态 / 没存档 / Mod 忙）？

    task-15 §④：环境类失败是"世界当时不让我动手"，**不是"这活没干成"** —— 它不该让整天
    needs_review，而应该先收掉挡路的东西再重试同一批格子。

    判据**只有一份**：`farmwork.ENV_BLOCK_STATUSES`（task-28 起含 `busy`）。首选
    `StepResult.env_block`（`farmwork._mark_status` 正是按那份常量打上的标记）；对没带标记
    但 code 全落在那份常量里的步（手写的假步/旧路径）再兜一层状态码判据。
    **绝不在 longrun 里另抄一份状态码字符串**（两处口径必然漂移）。
    """
    if step.env_block:
        return True
    codes = statuses_of(step)
    return bool(codes) and all(c in ENV_BLOCK_STATUSES for c in codes)


#: 【task-32】"这一天可以收工"的**正当理由**（`ended_reason` 冒号前的前缀）。
#: 只有三种：夜里到点 / 体力见底 / 确实没活。**`no_plot` 不在里面**：作业区配额到顶是
#: 我们自己给自己设的软上限，被它憋停不等于"没活可做"（0.7.22 真机彩排：第 1 天 09:40、
#: 体力 144.7/270 就 `no_plot` 回家睡，`work_reasons` 还在喊"还有地要清/开/种"）。
#: `no_plot` 只允许作为"没睡成的说明"，不许据此判 `verified`（用户 m02532/m00707）。
JUSTIFIED_END_REASONS = ("night", "stamina", "no_work")


def is_justified_end(ended_by: str, ended_reason: str) -> bool:
    """这一天是不是以**正当理由**收工（`day_justified` 的判据，task-32）。

    口径与旧实现逐字一致（`ended_reason.split(":", 1)[0] in 白名单`），只是把白名单提成
    模块常量 `JUSTIFIED_END_REASONS` 并抽成函数：一是单测可以直接钉死"`no_plot` 不在里面"，
    二是别处（`_finish`/日报/工具）不会各抄一份前缀表。
    """
    if ended_by != "sleep":
        return False
    return str(ended_reason or "").split(":", 1)[0] in JUSTIFIED_END_REASONS


#: "上一天未知"的哨兵日键：用来把**一天的第一次决策**顶到 `new_day` 边界上
#: （`detect_boundary` 只在两边都非空且不相等时才判跨日，所以放 None 是没用的）。
_DAY_START_SENTINEL: tuple[int, str, int] = (-1, "longrun-day-start", -1)


def plot_observe(obs: dict[str, Any], tiles: Iterable[tuple[int, int]], *,
                 skip: Iterable[tuple[int, int]] = ()) -> dict[str, Any]:
    """把观测**裁剪到这片地**：`planner` 只看得到作业区里的格子。

    顺手丢掉"我们动不了"的障碍格（树/果树/资源堆/灌木/放置物）：
    `Brief` 会把它们算成 `blockers`，于是策略会一直喊"去清障"、而执行层每次只能回 `skipped`。

    `skip` 是**今天已被证明干不动**的格子（`LongRun.blocked`）。必须一起丢掉，否则会出现
    真机 run1 那段空转：执行层已经把那两格 grass 封了（`_stage_tiles` 拿不出目标），
    简报里 `blockers` 仍是 2 ⇒ 策略每轮喊一次 `clear_area` ⇒ `stage_no_target` / idle 轮，
    白耗两轮才走到"今天没有可做的目标"（run1 journal t=70.7/71.3 两条）。
    """
    keep = set(tiles)
    drop = set(skip)
    loc = dict(obs.get("location") or {})
    rows = []
    for t in loc.get("tiles") or []:
        xy = t.get("tile") or []
        if len(xy) < 2:
            continue
        key = (int(xy[0]), int(xy[1]))
        if key not in keep or key in drop:
            continue
        if not t.get("crop") and str(t.get("kind") or "") not in ACTIONABLE_KINDS + ("dirt",):
            # 树/放置物等：既不进 blockers 计数，也不进 plantable 计数
            continue
        rows.append(t)
    loc["tiles"] = rows
    loc["tillable"] = [c for c in (loc.get("tillable") or [])
                       if tuple(int(v) for v in c) in keep
                       and tuple(int(v) for v in c) not in drop]
    loc["tilesTruncated"] = False
    out = dict(obs)
    out["location"] = loc
    return out


#: 边界决策给慢脑的 token 上限。用户 2026-10-11 拍板"大模型改成长跑默认开启"，
#: 而真机上 4096 被推理吃光过一次（`logs/plan-llm-manual-5.log`：简报带具名田区的那版
#: 直接 `LlmError:truncated`、content 为空 ⇒ 降级成纯代码策略，等于白开）；
#: run2 真机上 **8192 还是被吃光过一次**（journal 里那次 `deterministic_fallback`，
#: 原文见 task-9）⇒ 提到 16384。与 `planner.BoundaryPlanner(max_tokens=…)` 的默认值、
#: `llm.DEFAULT_MAX_TOKENS` 三者一致（有单测钉住）。
DEFAULT_LLM_MAX_TOKENS = 16384

#: 观测的"看得见"半径（曼哈顿距离的保守估计）。`tiles[]` 上限 400、`tillable[]` 近处优先，
#: 两者都**以玩家为中心**：离得远的作业区在观测里就是一片空白。所以"观测里没目标"这句话，
#: 只有在作业区离玩家足够近时才可信；远了必须走过去再看（用户 m02591 的校验机制的判据之一）。
OBSERVE_REACH = 14


@dataclass
class DayReport:
    """一个游戏日的成绩单。所有字段都是纯数据，能直接落 JSONL。"""

    day_key: tuple[int, str, int]
    started_at: float
    ended_by: str = ""            # sleep / pass_out / stuck / time_limit / budget / stop / bridge_down / blocked_modal
    ended_reason: str = ""
    plots: list[dict[str, Any]] = field(default_factory=list)
    stages: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    final: dict[str, Any] = field(default_factory=dict)
    #: task-19：**浇水证据**（`{t, location, tiles, crops, dry, scope}`），`scope ∈ {"farm","window"}`。
    #: `tiles/crops/dry` 是**所用那套口径下**的读数（farm 口径注明来自 `farm.dryCrops`）。
    #: 为什么不塞进 `final`：`final` 的 `crops`/`unwatered_crops` 是**窗口口径**（≤400 格、以玩家为中心），
    #: 在室内（FarmHouse）恒为 0 —— run2 的 `checks.crops_watered=true` 就是这么白过的；两套仪器
    #: 绝不能混在同一列（log-analyst `docs\_analyze-farmcounts.md`，run2 的 31→8→21→32）。
    final_water: dict[str, Any] = field(default_factory=dict)
    #: task-38：**睡成功后重新观测到的游戏日**（`[year, season, day]`）。`final` 是睡前快照，
    #: 跨日证据必须靠这一条（`tools\verify-run3.py` 优先读它，其次才退回 `final`）；
    #: 只在 `ended_by=="sleep"` 且睡后观测成功时非空 —— 它是**观测**，不是回执。
    day_after: list[Any] | None = None
    verified: bool = False
    #: 【task-52】当天判为"走不到"（四邻都站不过去 / 寻路到不了）的**格数**与**逐格坐标**。
    #: 字段名与 `tools\verify-run3.py` 的交叉核对口径逐字对齐（Lead m04925）：
    #: `day_end.unreachable`（int）+ `day_end.unreachable_tiles`（`[[x,y],…]`）。
    #: `unreachable_bound` = `max(5, floor(0.2 × attempted))`，`unreachable_exempt` = 真正从
    #: `no_unmet_stages` 里扣掉的格数（≤ bound，且只扣还留在 leftover 里的不可达格）。
    unreachable: int = 0
    unreachable_tiles: list[Any] = field(default_factory=list)
    unreachable_bound: int = 0
    unreachable_exempt: int = 0

    @property
    def failed_steps(self) -> int:
        return sum(int(s.get("failed") or 0) for s in self.stages)

    @property
    def ok_steps(self) -> int:
        return sum(int(s.get("ok") or 0) for s in self.stages)

    @property
    def skipped_steps(self) -> int:
        return sum(int(s.get("skipped") or 0) for s in self.stages)

    @property
    def stages_seen(self) -> list[str]:
        return sorted({str(s.get("stage")) for s in self.stages})

    @property
    def day_text(self) -> str:
        y, season, d = self.day_key
        return f"{y}年 {season} {d}日"

    def as_dict(self) -> dict[str, Any]:
        return {
            "day": list(self.day_key),
            "day_text": self.day_text,
            "started_at": round(self.started_at, 3),
            "ended_by": self.ended_by,
            "ended_reason": self.ended_reason,
            "verified": self.verified,
            "checks": dict(self.checks),
            "plots": list(self.plots),
            "stages": list(self.stages),
            "outcomes": list(self.outcomes),
            "notes": list(self.notes),
            "final": dict(self.final),
            # task-19：浇水证据单独一条，`tools\verify-run3.py` 靠 `day_end.final_water` 复核
            # 证据来自哪张快照（并与 `checks.watered_outdoor` 互检，盲区 B4）。
            "final_water": dict(self.final_water),
            # task-38：睡后观测到的游戏日（跨日证据；`final` 是睡前快照，不能当跨日证据）
            "day_after": list(self.day_after) if self.day_after else None,
            "ok_steps": self.ok_steps,
            "skipped_steps": self.skipped_steps,
            "failed_steps": self.failed_steps,
            # 【task-52】不可达：计数 + 逐格坐标 + 界与实扣（`tools\verify-run3.py` 交叉核对用）
            "unreachable": self.unreachable,
            "unreachable_tiles": [list(t) for t in self.unreachable_tiles],
            "unreachable_bound": self.unreachable_bound,
            "unreachable_exempt": self.unreachable_exempt,
        }


class LongRun:
    """连续多日无人值守的农务循环。"""

    def __init__(
        self,
        client_factory: Callable[[], BridgeClient] = BridgeClient,
        *,
        worker_factory: Callable[[BridgeClient], FarmWorker] | None = None,
        planner: BoundaryPlanner | None = None,
        target_days: int = 3,
        max_days: int | None = None,
        plot_size: int = 5,
        zone_prefer: str = "most_tillable",
        zone_split: int = 2,
        llm_enabled: bool = True,
        llm_chat: Callable[..., str] | None = None,
        llm_max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
        farm: str = "Farm",
        home: str = "FarmHouse",
        seed: str | None = None,
        buy_item: str = "472",
        seed_price: int = 20,
        buy_count: int = 10,
        allow_buy: bool = True,
        shop: str = "SeedShop",
        min_stamina: float = 12.0,
        sleep_at: int = 2200,
        max_minutes: float = 60.0,
        max_steps: int = 1500,
        per_stage_tiles: int = 12,
        water_stage_tiles: int = 60,
        max_stage_rounds: int = 6,
        max_env_retries: int = 2,
        sell_timeout_ms: int = 8000,
        water_min_stamina: float = 1.0,
        plot_walk_timeout_ms: int = 20000,
        max_refills_per_day: int = 4,
        max_plots_per_day: int = 10,
        supervise_every: int = 20,
        modal_wait_timeout_s: float = MODAL_WAIT_TIMEOUT_S,
        modal_max_dismiss: int = MODAL_MAX_DISMISS,
        report_dir: str | Path | None = None,
        journal_path: str | Path | None = None,
        log: Callable[[str], None] = print,
        now: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client_factory = client_factory
        self.worker_factory = worker_factory or (lambda c: FarmWorker(c, seed=seed, log=log))
        self.planner = planner or BoundaryPlanner(
            llm_enabled=llm_enabled, llm_chat=llm_chat, max_tokens=llm_max_tokens
        )
        self.llm_enabled = bool(llm_enabled)
        # 生效的预算（可能来自 `--max-tokens`）：播报与 journal 必须报**实际值**，
        # 否则"用户调了 4096、日志里写着 16384"，出事后复盘会被自己的日志骗。
        self.llm_max_tokens = int(llm_max_tokens)
        self.state = PlannerState()

        self.target_days = int(target_days)
        # 硬上限：一天没达标就得重来（尾部连续才算数），但不能无限重来 ——
        # 真机上"没睡成"时游戏日根本不往前走，重复下去永远凑不出连续达标。
        self.max_days = int(max_days) if max_days else max(self.target_days * 2, self.target_days + 2)
        self.plot_size = int(plot_size)
        self.target_tiles_base = self.plot_size * self.plot_size
        self.zone_prefer = zone_prefer
        self.zone_split = int(zone_split)
        self.farm = farm
        self.home = home
        self.buy_item = buy_item
        self.seed_price = int(seed_price)
        self.buy_count = int(buy_count)
        self.allow_buy = bool(allow_buy)
        self.shop = shop
        self.min_stamina = float(min_stamina)
        self.sleep_at = int(sleep_at)
        self.max_minutes = float(max_minutes)
        self.max_steps = int(max_steps)
        self.per_stage_tiles = int(per_stage_tiles)
        self.water_stage_tiles = int(water_stage_tiles)
        # 本阶段格数上限（`per_stage_tiles`）撞到后**接着跑**，直到没有目标为止 ——
        # 否则"一次只浇 12 格"会天天留下没浇的作物（真机 m01770 就是这么发生的）。
        self.max_stage_rounds = int(max_stage_rounds)
        # task-15 §④：一轮 `run_stage` 里出现**环境挡路**（渐黑/模态/没存档/Mod 忙）时，先收掉
        # 挡路的模态再重跑**同一批格子**，最多重试这么多轮。上限取 2：一次瞬时渐黑/一个弹窗
        # 收掉后就会成功；同一批格子连挡 3 轮说明世界真的坏了（模态关不掉、Mod 一直 busy），
        # 此时如实留给 `leftover` ⇒ `no_unmet_stages=False` ⇒ 当天 needs_review。
        # 置 0 可关掉重试（单测与排障用）。
        self.max_env_retries = int(max_env_retries)
        # task-42 出货（`sell`）的 HTTP 超时：单 tick 同步技能（Mod 一次调用即完成），
        # 不需要像 `sleep`/`buy` 那样等菜单；给 8s 足够（可注入，便于单测把假桥拖慢的场景收紧）。
        self.sell_timeout_ms = int(sell_timeout_ms)
        # 浇水的体力闸门单独放低到 1 点：当天种下的作物"没浇"是不可补的损失，
        # 必须允许在体力见底前把最后几格浇完（m01847/m01774）。
        self.water_min_stamina = float(water_min_stamina)
        self.plot_walk_timeout_ms = int(plot_walk_timeout_ms)
        self.max_refills_per_day = int(max_refills_per_day)
        self.max_plots_per_day = int(max_plots_per_day)
        self.supervise_every = int(supervise_every)
        # task-11 模态守卫：等待型模态的墙钟上限、一次最多关几个模态（可注入，便于单测）。
        self.modal_wait_timeout_s = float(modal_wait_timeout_s)
        self.modal_max_dismiss = int(modal_max_dismiss)
        self.report_dir = Path(report_dir) if report_dir else None
        self.journal_path = Path(journal_path) if journal_path else None
        # 【task-56】决策留痕落点 = 与 journal 同前缀的 `<stem>-llm.jsonl`（planner 不知道 journal
        # 在哪，所以由控制器推导后回填；planner 不支持回填就退化成"不留痕"，绝不影响决策）。
        self.llm_trace_path = self._derive_llm_trace_path(self.journal_path)
        trace_setter = getattr(self.planner, "set_trace_path", None)
        if callable(trace_setter):
            trace_setter(self.llm_trace_path)
        self.log = log
        self.now = now
        self.sleep_fn = sleep_fn

        self.client: BridgeClient | None = None
        self.worker: FarmWorker | None = None
        self.started = 0.0
        self.days: list[DayReport] = []
        self.entries: list[dict[str, Any]] = []
        self.aborted = False
        self.summary: dict[str, Any] = {}
        self._jf: Any = None
        self._actions = 0

        # 当日状态
        self.plot: dict[str, Any] | None = None
        self.zone_name = ""
        self.plots_today = 0
        # 【task-32】当天是否已经播报过 `plots_capped`（作业区软上限触顶）。一天只记一次。
        self.plots_capped_noted = False
        # 【task-41 NIT-2】当天是否已经播报过 `farm_evidence_unavailable`（室内 + farm 证据不可用
        # ⇒ fail-closed，绝不放行 `no_work`）。一天只记一次，免得每轮刷同一条 journal。
        self.farm_evidence_noted = False
        self.refills_today = 0
        self.idle_rounds = 0
        self.fail_streak = 0
        self.last_failure = ""
        self.pending_zone_hint = ""
        self._last_day_key: tuple[Any, ...] | None = None
        # 本日"动了没用"的格子 → 说明。一格最多白试一次（真机 16 下无效挥锄的教训）。
        self.blocked: dict[tuple[int, int], str] = {}
        # 本日每格"发起过几次有代价的动作"（`MAX_TILE_ATTEMPTS` 兜底）。
        # `blocked` 是"判据证明干不动"，这里是**不变量**：哪怕判据漏了某种情况，
        # 同一格一天也不会被发起第 3 次（用户 m01804 要的"不要白白浪费体力"）。
        self.tile_attempts: dict[tuple[int, int], int] = {}
        # 本日每格"连续被环境挡住"的次数（task-28 防自旋）：超过 `MAX_ENV_ATTEMPTS` 后
        # 不再免费，改为占 `tile_attempts` 配额 ⇒ 持续 `busy` 时请求次数有界、当天 needs_review。
        # ⚠️ 键是**格子**，不是"格子+动作"：同一格上 `clear_area` 与 `water_area`（或 `till_area`）
        # 共用同一条 streak。这是有意为之（`_stage_tiles`/`_count_attempts` 的记账都是按格的几何
        # 口径，用户 m01804 要的"不要在同一格上白耗体力"也是按格说的），代价是"同一格先被渐黑挡一次、
        # 后来浇水又被模态挡一次"会比按动作分账更早开始吃配额 —— 偏保守，可以接受。
        self.env_streak: dict[tuple[int, int], int] = {}
        # 已经为哪些格写过 `env_spin_capped`（同格只报一次，别每轮刷屏）。
        self.env_spin_noted: set[tuple[int, int]] = set()
        # 本日已经播报过"没种子也没钱 ⇒ 不再开垦"的任务（`till_area`/`plant_area`）。
        # 只在第一次撞到时说一句，别每轮刷屏（task-9：run2 白锄 60 格、体力 270→74）。
        self.seed_gate_noted: set[str] = set()
        # 【task-51】本日是否已经播报过 `clear_dead` 的"看得见多少 / 农场口径还剩多少"。
        self.dead_scope_noted: set[str] = set()
        # 本日"策略要了但一格目标都拿不出来"的任务。策略与执行层一旦不同口径，
        # 每轮空转一次、攒够 3 轮就判 stuck 报废整天；记下来当天不再要它。
        # **片区级**：`clear_area`/`till_area`/`plant_area` 只在作业区内看目标，换一片地就得忘掉。
        self.no_target: set[str] = set()
        # **全场级**：`water_area`/`harvest` 看的是整个农场（一天要把所有作物伺候完），
        # 它们没目标就是真没目标 —— 换片地也不该再问。
        self.no_target_global: set[str] = set()
        # 【task-49】今天**已经见过、但还没做完**的格子（`_step_stage` 每轮的 `leftover`，排除已封格）。
        # 为什么必须记：观测是**以玩家为中心**的窗口（真机 `tiles[]` 上限 400、近处优先），
        # 人一换到别的片地，原来那片地的格子就"看不见"了 ⇒ `work_reasons`/`_plot_candidates`
        # 全判没活。run5 第 1 天就是这么在中途以 `no_work` 去睡的（field_nw 还有 9 格未开垦，
        # 而人已经在 field_se，体力还剩 62.3）。这份记账让守卫知道"别处还有没做完的"，
        # 并让 `_resume_plot` 把人带回去再看一次（`resume_walks` 有上界，见 `_run_day`）。
        self.leftover_targets: set[tuple[int, int]] = set()
        # 【task-52】当天累计的"走不到"格子（四邻都站不过去 / 寻路到不了）。为什么需要**累计**：
        # 这些格一记进 `self.blocked`，后续轮次的 `_stage_tiles` 就把它们剔掉了 ⇒ 只看当轮
        # `all_steps` 会看不到它们，而它们仍留在 `_leftover` 里（`_leftover` 刻意不排除 blocked）。
        # 日级 `no_unmet_stages` 的有界豁免与账本 `unreachable` 都靠这份集合。
        # **不跨日**：`_run_day` 每天清空 ⇒ 次日自动重试（不许像 `proven_inert` 那样永久封格）。
        self.unreachable_day: set[tuple[int, int]] = set()
        # 本日"为了看没做完的格子而往回走"的次数上限（防"来回跑"把一天走光）。
        self.resume_walks = 0
        # 【task-50】窗口外干作物（Mod 的 `farm.dryTiles`）：每格试了几次、哪些已经认输。
        # run5 三天 `farm.dryCrops` 恒剩 1、而每个作业区 `leftover=0` —— 那 1 格在玩家 400 格
        # 观测窗口之外，脑侧连坐标都没有，只能 `no_work` 收工（`day_justified=true` 白拿）。
        self.far_dry_tries: dict[tuple[int, int], int] = {}
        self.far_dry_given_up: set[tuple[int, int]] = set()
        # 本日是否已经播报过"旧 Mod 没给 dryTiles 坐标"（一天只提醒一次，不刷屏）。
        self.far_dry_unavailable_noted = False

    # ------------------------------------------------------------------ 小工具
    def _mark_no_target(self, task: str) -> None:
        """记下"这个任务今天一格目标都拿不出来"，按作用域分账（见 `WIDE_TASKS`）。"""
        if task in WIDE_TASKS:
            self.no_target_global.add(task)
        else:
            self.no_target.add(task)

    def _say(self, line: str) -> None:
        try:
            self.log(line)
        except Exception:  # pragma: no cover - 日志不该拖垮长跑
            pass

    def _journal(self, event: str, **fields: Any) -> dict[str, Any]:
        rec: dict[str, Any] = {"event": event, "t": round(self.now() - self.started, 2) if self.started else 0.0}
        rec.update(fields)
        self.entries.append(rec)
        if self._jf is not None:
            try:
                self._jf.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                self._jf.flush()
            except Exception:  # pragma: no cover
                pass
        return rec

    def _snap(self) -> dict[str, Any]:
        assert self.worker is not None
        return self.worker.snap()

    @staticmethod
    def _derive_llm_trace_path(journal_path: Path | None) -> Path | None:
        """【task-56】`logs/run6.jsonl` ⇒ `logs/run6-llm.jsonl`（日记旁边放决策留痕）。

        journal 为 None 时不落痕（一次性 `agentfarm plan` 之类不需要文件）。
        """
        if journal_path is None:
            return None
        suffix = journal_path.suffix or ".jsonl"
        stem = journal_path.name[: -len(journal_path.suffix)] if journal_path.suffix else journal_path.name
        return journal_path.with_name(f"{stem}-llm{suffix}")

    def _elapsed_minutes(self) -> float:
        return (self.now() - self.started) / 60.0

    def _budget_exhausted(self) -> bool:
        if self.max_minutes > 0 and self._elapsed_minutes() >= self.max_minutes:
            return True
        return self.max_steps > 0 and self._actions >= self.max_steps

    @staticmethod
    def _fingerprint(obs: dict[str, Any]) -> tuple[Any, ...]:
        """世界指纹：只装"干农活会改变的东西"。用来判断一轮下来**到底有没有进展**。

        为什么不看回执、也不看意图：`acted` 是"策略说它想做点什么"，而这里问的是
        "世界的差分动了没有" —— 与整个项目的验收纪律同一个口径。任何"回执说成功、
        世界没变"的空转都会因此被记成无进展，三次就如实停下（stuck）。
        """
        p = FarmWorker.player_of(obs)
        tiles = FarmWorker.tiles_of(obs)
        return (
            tuple(sorted((t, str(v.get("kind") or ""), str(v.get("crop") or ""),
                          bool(v.get("watered")), bool(v.get("ripe"))) for t, v in tiles.items())),
            tuple(sorted(FarmWorker.tillable_of(obs))),
            p.get("money"),
            (p.get("wateringCan") or {}).get("waterLeft"),
            tuple(sorted(seed_items(p))),
        )

    def _is_farm(self, obs: dict[str, Any]) -> bool:
        return bool((obs.get("location") or {}).get("isOutdoorFarm"))

    def _ensure_on_farm(self, obs: dict[str, Any], rep: DayReport) -> dict[str, Any]:
        """【run3 真 bug】当天开工前把人带回户外农场；失败**不吞**（notes + journal）。

        睡醒默认在 FarmHouse（室内），而所有作业判据（`work_reasons`/`_ensure_plot`/
        `_stage_tiles`）都只看**玩家窗口**：室内窗口 `crops=0` ⇒ 会判成"没活"⇒ 连睡好几天，
        账本里 `ended_reason` 是 `no_work` 而 `final_water` 还是 `dry=33/33`（自相矛盾）。
        回不去时**不假装成功**：如实记 notes，当天由守卫/策略层按"不在农场"处理。
        """
        if self._is_farm(obs):
            return obs
        assert self.worker is not None
        st = self.worker.ensure_location(self.farm)
        self._actions += 1
        self._journal("goto_farm", ok=st.ok, code=st.code, reason=st.reason,
                      where="day_start", before=st.before, after=st.after, receipt=st.receipt)
        if not st.ok:
            rep.notes.append(f"回不去 {self.farm}：{st.reason}")
            self._say(f"  × 回 {self.farm} 失败：{st.reason}")
            return obs
        self._say(f"  · 回到 {self.farm}：{st.reason}")
        try:
            return self._snap()
        except BridgeError as exc:
            rep.notes.append(f"回到 {self.farm} 之后观测失败：{exc}")
            return obs

    def _farm_totals(self, obs: dict[str, Any]) -> tuple[int, int] | None:
        """`farm` 块的全农场读数 `(dryCrops, ripeCrops)`；`None` = 证据不可用。

        【task-49】与 `_farm_scope_work` 的区别只有一条：**人在农场里也算证据**。
        run5 第 1 天的真实病灶之一就是这里：人站在 field_se（`isOutdoorFarm=true`），
        `_farm_scope_work` 直接返回 `None` ⇒ `farm.dryCrops=1`（全农场还有 1 格干作物）
        被丢掉；而玩家窗口（半径 ~14）没盖到那一格 ⇒ `work_reasons` 空 ⇒ 守卫放行
        `no_work` 去睡觉（体力还剩 62.3）。农场级读数与窗口读数是**互补**的：
        窗口管"眼前这片的细节"，farm 块管"全农场还有没有没伺候完的作物"。

        字段口径（`mod\\AgentFarm.Bridge\\Contracts.cs` 的 `FarmView`）：`dryCrops` 才是干格数；
        `unwateredCrops` 数的是 `NeedsWatering`（run3 里整天 32→32）⇒ 不能当判据。
        """
        farm = obs.get("farm") or {}
        if farm.get("complete") is not True or farm.get("loaded") is False:
            return None                     # 旧 Mod / 未加载（全 0）⇒ 不算证据
        dry = farm.get("dryCrops")
        ripe = farm.get("ripeCrops")
        if dry is None and ripe is None:
            return None
        return (int(dry or 0), int(ripe or 0))

    def _farm_scope_work(self, obs: dict[str, Any]) -> tuple[int, int] | None:
        """`farm` 块的"还有活"读数 `(dry, ripe)`；`None` = 此刻不是可用证据。

        只有在**人不在户外农场**时才有意义：此刻窗口观测只覆盖室内（`crops=0`），用它判
        "有没有活"必然误判。字段口径按 `mod\\AgentFarm.Bridge\\Contracts.cs` 的 `FarmView`：
        **`dryCrops` 才是"干着的作物格数"**，`unwateredCrops` 数的是 `NeedsWatering` 的作物
        （run3 里它整天 32→32，不能拿来判"今天浇完没有"）。

        【task-49】人在农场里时用 `_farm_totals`（同一个 farm 块，只是不因位置而丢弃）。
        """
        if self._is_farm(obs):
            return None
        return self._farm_totals(obs)

    # --------------------------------------------------- task-50：窗口外的干作物
    @staticmethod
    def _far_dry_outside(obs: dict[str, Any]) -> tuple[list[tuple[int, int]], str]:
        """Mod 报了坐标、但**不在玩家观测窗口里**的干作物格（含已经认输的）。

        与 `_far_dry_tiles` 的区别：这里**不过滤** `far_dry_given_up`。为什么要留着认输的格子：
        当天最后以 `stuck:` 收尾时，`ended_reason` 必须**点名坐标**（task-50 硬要求：
        "干格不可达 ⇒ `ended_reason` 以 `stuck:` 开头且含坐标"），所以报告口径与行动口径要分开。
        """
        tiles, status = farm_dry_tiles(obs)
        if status == "unavailable":
            return [], status
        visible = FarmWorker.tiles_of(obs)
        return [t for t in tiles if t not in visible], status

    def _far_dry_tiles(self, obs: dict[str, Any]) -> tuple[list[tuple[int, int]], str]:
        """**玩家窗口之外、今天还没认输**的干作物格（task-50，= 行动口径）。

        返回 `(还没认输的格, 状态)`，状态来自 `farmwork.farm_dry_tiles`：
        `"ok"` / `"truncated"` / `"unavailable"`。

        为什么需要它：`farm.dryCrops > 0` 时守卫**不许**判 `no_work`（run5 三天全挂的形态），
        但那一格常常不在玩家周围 400 格窗口里 ⇒ 光知道"还有 1 格干"没法行动。
        Mod 的 `farm.dryTiles` 给了坐标，脑侧据此走过去，走进去之后该格自然进窗口，
        再由 `FarmWorker.water()` 用观测差分判成交。

        已经认输的格子（`far_dry_given_up`）不再返回 —— 防"走不到就无限重试"；
        报告/收尾要坐标时用 `_far_dry_outside`（含认输的）。
        状态 `"unavailable"`（旧 Mod / farm 证据不可信）时返回空列表，调用方**绝不许**
        把它当成"没有干格"。
        """
        outside, status = self._far_dry_outside(obs)
        if status == "unavailable":
            return [], status
        return [t for t in outside if t not in self.far_dry_given_up], status

    def _far_dry_where(self, obs: dict[str, Any]) -> str:
        """收尾/守卫文案里的"窗口外那几格在哪"（含坐标；认输的也点名，标"够不着"）。"""
        outside, status = self._far_dry_outside(obs)
        if status == "unavailable" or not outside:
            return ""
        given = [t for t in outside if t in self.far_dry_given_up]
        mark = ""
        if given and len(given) == len(outside):
            mark = f"；已试 {FAR_DRY_MAX_TRIES} 次都够不着，当天不再重试"
        elif given:
            mark = "；其中一部分已试过够不着"
        return (f"，其中 {len(outside)} 格在玩家窗口之外（Mod 报的坐标 "
                f"{[list(t) for t in outside[:3]]}{mark}）")

    def _far_dry_reason(self, obs: dict[str, Any], dry_f: int) -> str:
        """窗口外干作物的"还有活"理由（带坐标；给守卫/`work_reasons` 共用，避免口径漂移）。"""
        far, status = self._far_dry_tiles(obs)
        where = self._far_dry_where(obs)
        if far:
            return f"农场口径还有 {dry_f} 格干作物{where} ⇒ 先走过去浇"
        if status == "unavailable":
            return (f"农场口径还有 {dry_f} 格干作物，但 farm.dryTiles 不可用（旧 Mod / "
                    "farm 证据不可信）⇒ 不许判「没活」，先回农场再判")
        if where:
            return f"农场口径还有 {dry_f} 格干作物{where} ⇒ 想浇但走不到（不再重试）"
        return f"农场口径还有 {dry_f} 格干作物（窗口里看不到坐标）"

    def _water_far_dry(self, obs: dict[str, Any], rep: DayReport) -> bool:
        """走过去浇一格"窗口外"的干作物（task-50）。返回 `True` = 本轮真动了一次手。

        有界性：每格一天最多 `FAR_DRY_MAX_TRIES` 次（走过 + 浇水算一次）；两次都不成
        就进 `far_dry_given_up`，当天不再试它 —— 于是 `_far_dry_tiles` 会变空、守卫
        仍因 `farm.dryCrops > 0` 不放行 ⇒ `_run_day` 以 `stuck:` 收尾并点名坐标
        （**绝不**是 `no_work`）。
        """
        assert self.worker is not None
        far, status = self._far_dry_tiles(obs)
        if not far:
            if status == "unavailable" and not self.far_dry_unavailable_noted:
                farm = obs.get("farm") or {}
                self.far_dry_unavailable_noted = True
                self._journal("water_far_unavailable", complete=farm.get("complete"),
                              loaded=farm.get("loaded"), dryCrops=farm.get("dryCrops"),
                              note="farm 说还有干作物，但没有 dryTiles 坐标（旧 Mod / 证据不可信）"
                                   "⇒ 不判「没活」，按有活继续干（当天会以 stuck 如实收尾）")
            return False
        pt = FarmWorker.player_tile(obs) or far[0]
        tile = min(far, key=lambda t: (_dist(t, pt), t[1], t[0]))
        tries = int(self.far_dry_tries.get(tile, 0)) + 1
        self.far_dry_tries[tile] = tries
        self._actions += 1
        before_farm = obs.get("farm") or {}
        before_dry = int(before_farm.get("dryCrops") or 0)

        walked, walk_note = True, ""
        try:
            walked = bool(self.worker.stand_next_to(tile, timeout_ms=30000))
        except BridgeError as exc:
            walked, walk_note = False, f"走过去失败：{exc}"
        except Exception as exc:                      # pragma: no cover - 假 worker 的意外
            walked, walk_note = False, f"走过去异常：{type(exc).__name__}: {exc}"

        st: StepResult | None = None
        err = ""
        if walked:
            try:
                st = self.worker.water(tile)
            except BridgeError as exc:
                err = str(exc)
            except Exception as exc:                  # pragma: no cover
                err = f"{type(exc).__name__}: {exc}"

        after_obs = obs
        try:
            after_obs = self._snap()
        except BridgeError:
            pass
        after_tv = (FarmWorker.tiles_of(after_obs) or {}).get(tuple(tile)) or {}
        after_farm = after_obs.get("farm") or {}
        after_dry = int(after_farm.get("dryCrops") or 0)
        watered = bool(after_tv.get("watered"))
        # 判据**只看观测差分**（task-50 卡面：该格 `watered==true`，或 `farm.dryCrops` 下降）。
        # 回执 `st.ok=True` **不算证据** —— run1/run2 都栽在"回执 ok、世界没变"上；
        # 实测（`scratch\\_t50_probe.py` 场景④）：把回执算进来的话，"回执说浇了、壶没动、
        # 世界没变"会被记成浇成功，当天还白拿 `verified`。
        ok = watered or (before_dry > 0 and 0 <= after_dry < before_dry)
        code = (st.code if st is not None else ("unreachable" if not walked else "error"))
        receipt_ok = bool(st.ok) if st is not None else None

        if not ok and tries >= FAR_DRY_MAX_TRIES:
            self.far_dry_given_up.add(tile)
        self._journal("water_far", tile=list(tile), ok=ok, code=code, try_=tries,
                      limit=FAR_DRY_MAX_TRIES, walked=bool(walked), watered=watered,
                      dry_before=before_dry, dry_after=after_dry, status=status,
                      receipt_ok=receipt_ok,
                      reason=(st.reason if st is not None else (walk_note or err)),
                      receipt=(st.receipt if st is not None else err),
                      given_up=bool(tile in self.far_dry_given_up),
                      note="窗口外干作物：Mod 的 farm.dryTiles 给了坐标 ⇒ 走过去浇"
                           "（farm.dryCrops>0 时不许 no_work 收工；判据=该格 watered 或 dryCrops 下降）")
        if ok:
            rep.notes.append(f"浇了窗口外那格干作物 {list(tile)}（第 {tries} 次尝试；"
                             f"farm.dryCrops {before_dry}→{after_dry}）")
            self._say(f"  · 浇窗口外干作物 {list(tile)}：{code}")
        else:
            rep.notes.append(f"窗口外干作物 {list(tile)} 没浇成（第 {tries}/{FAR_DRY_MAX_TRIES} 次）："
                             f"{walk_note or err or (st.reason if st is not None else code)}"
                             + ("；不再试这一格" if tile in self.far_dry_given_up else ""))
        return True

    @staticmethod
    def _essence(obs: dict[str, Any]) -> dict[str, Any]:
        """观测要点（差分/成绩单用）：只留"够判断"的字段，别把整个快照塞进日志。"""
        loc = obs.get("location") or {}
        p = obs.get("player") or {}
        c = obs.get("clock") or {}
        tiles = FarmWorker.tiles_of(obs)
        crops = [t for t, v in tiles.items() if v.get("crop")]
        return {
            "day": [c.get("year"), c.get("season"), c.get("day")],
            "timeOfDay": c.get("timeOfDay"),
            "location": loc.get("name"),
            "tile": list(p.get("tile") or []),
            "stamina": p.get("stamina"),
            "money": p.get("money"),
            "isInBed": p.get("isInBed"),
            "crops": len(crops),
            "unwatered_crops": len([t for t in crops if not tiles[t].get("watered")]),
            "ripe": len([t for t in crops if tiles[t].get("ripe")]),
            "tillable": len(loc.get("tillable") or []),
            "waterLeft": (p.get("wateringCan") or {}).get("waterLeft"),
            "seeds": [list(x) for x in seed_items(p)],
            # task-19：上面 `crops`/`unwatered_crops` 是**窗口口径**（≤400 格、以玩家为中心；在室内恒 0），
            # 这里逐字标注，并把 `farm.*` 读数整体放进**独立命名空间** —— 两套仪器不混列。
            "counts_scope": "window",
            "farm": {k: (obs.get("farm") or {}).get(k)
                     for k in ("loaded", "complete", "crops", "dryCrops", "unwateredCrops", "hoeDirt")},
        }

    # ------------------------------------------------------------ 浇水证据（task-19）
    def _water_evidence(self, obs: dict[str, Any], *, outdoor_obs: dict[str, Any] | None = None,
                        outdoor_t: float = 0.0, outdoor_name: str | None = None
                        ) -> tuple[bool, dict[str, Any]]:
        """日级浇水证据：真值只有 `farm.dryCrops`（全农场）或**最后一个户外快照**的逐格 `watered`。

        背景（log-analyst `docs\\_analyze-farmcounts.md`，IL 定案）：窗口 `location.tiles[]`（≤400 格、
        按离玩家距离截断）在**室内恒 0**，run2 的 `checks.crops_watered=true` 就是这么白过的；而
        `farm.unwateredCrops` 用的是 `HoeDirt.needsWatering()`（只看 `CropData.NeedsWatering`、完全不看
        浇水状态），也不是干格数。真值只有两处：`farm.dryCrops`（= 全农场 `crop != null &&
        !HoeDirt.isWatered()`，task-23/0.7.22 加）和逐格 `tiles[].watered`（`HoeDirt.isWatered()`）。

        口径选择（逐字对齐 `tools\\verify-run3.py` 的闸门，字段名不许改）：
        * `farm.complete == true` 且 `farm.loaded != false` 且 `farm.dryCrops` 存在 ⇒ **farm 口径**：
          `watered_outdoor = (dryCrops == 0)`；`tiles` 记 `farm.hoeDirt`（该次全农场扫描清点到的耕地格数）、
          `crops` 记 `farm.crops`（两键都是 >0 的可查读数，便于 Lead 手工复核）。
          `complete == false`（扫描没走完）或**旧 Mod 没有 `dryCrops` 字段**时**不得**把 0 当
          "没有作物/没有干格" ⇒ 一律退回窗口口径（卡面 §4）。
        * 否则用**当天最后一个 `location.isOutdoorFarm == true`** 的快照逐格统计（`scope="window"`，
          `tiles` = 该窗口覆盖的格数）；一天都没有户外快照且 farm 口径不可用 ⇒ `watered_outdoor=False`
          + `note` 说明（**禁止默认 true**，卡面 §5④）—— 如实判"没证据 ⇒ 不算浇过"。

        ⚠️ 本函数**永远返回 bool**（`tools\verify-run3.py` 把"缺字段"直接当问题），拿不到证据时给
        `False` 而不是省略字段。
        """
        t_now = round(float(self.now() - self.started), 3)
        loc_now = str((obs.get("location") or {}).get("name") or "")
        farm = obs.get("farm") or {}
        if (farm.get("complete") is True and farm.get("loaded") is not False
                and farm.get("dryCrops") is not None):
            dry = int(farm.get("dryCrops") or 0)
            crops = int(farm.get("crops") or 0)
            tiles = int(farm.get("hoeDirt") or 0)
            info: dict[str, Any] = {
                "t": t_now,
                "location": outdoor_name or "Farm",
                "tiles": tiles,
                "crops": crops,
                "dry": dry,
                "scope": "farm",
                "note": ("farm 口径：dry 来自 farm.dryCrops（全农场 crop!=null && !HoeDirt.isWatered()），"
                         f"tiles=farm.hoeDirt={tiles}、crops=farm.crops={crops}；"
                         f"farm.unwateredCrops={farm.get('unwateredCrops')} 不是干格数、不参与判定"),
            }
            if crops == 0:
                info["note"] += "；本日 farm 口径 0 作物（无作物可浇，dry 恒 0）"
            return dry == 0, info
        if outdoor_obs is None:
            info = {
                "t": t_now, "location": loc_now, "tiles": 0, "crops": 0, "dry": None,
                "scope": "window",
                "note": ("当天没有任何 location.isOutdoorFarm==true 的快照，且 farm 口径不可用"
                         f"（complete={farm.get('complete')!r}/loaded={farm.get('loaded')!r}/"
                         f"dryCrops={farm.get('dryCrops')!r}）⇒ 没有逐格浇水证据，如实判 False"
                         "（禁止默认 true）"),
            }
            return False, info
        win = FarmWorker.tiles_of(outdoor_obs)
        crops_t = [t for t, v in win.items() if v.get("crop")]
        dry_t = [t for t in crops_t if not win[t].get("watered")]
        info = {
            "t": round(float(outdoor_t), 3),
            "location": outdoor_name or str((outdoor_obs.get("location") or {}).get("name") or ""),
            "tiles": len(win), "crops": len(crops_t), "dry": len(dry_t), "scope": "window",
            "note": (f"window 口径：用当天最后一张户外快照（覆盖 {len(win)} 格、其中作物 {len(crops_t)} 格）"
                     "逐格 watered 判据；farm.complete==false 或旧 Mod 没有 farm.dryCrops 时才走这条"),
        }
        if not win:
            # NIT-1（deputy-lead `docs\_review-task19.md`）：空窗口下 `len(dry_t) == 0` **恒真**，
            # 与上面那句 note 自相矛盾 ⇒ 必须在这里就把结论钉成 False，不许"0 格也自称浇过"。
            info["note"] += ("；本天没有任何户外窗口观测格（覆盖 0 格）⇒ 不能据此自称浇过"
                             "（空窗口下逐格判据恒真，故如实判 False）")
            return False, info
        return len(dry_t) == 0, info

    # ------------------------------------------------------------------ 选地
    def _zones(self, obs: dict[str, Any]) -> list[Any]:
        if fields_mod is None or not self._is_farm(obs):
            return []
        try:
            return list(fields_mod.zones_from_observe(obs, split=self.zone_split))
        except Exception as exc:  # pragma: no cover - fields 坏掉不该拖垮长跑
            self._journal("zones_failed", error=f"{type(exc).__name__}: {exc}")
            return []

    def _ordered_zones(self, zones: list[Any]) -> list[Any]:
        """田区尝试顺序：LLM 指定的 → 代码偏好（可锄最多/最近）→ 其余按名字。

        `pick_plot` 的教训（用户 2026-10-11："纯靠人的位置然后开垦，是不是不太好"）：
        绝不能只按"离玩家最近"取窗口，否则地块会跟着角色漂移。
        """
        ordered: list[Any] = []
        if self.pending_zone_hint and fields_mod is not None:
            z = None
            try:
                z = fields_mod.resolve_zone(self.pending_zone_hint, zones)
            except Exception:
                z = None
            if z is not None:
                ordered.append(z)
                self.pending_zone_hint = ""
        try:
            pref = fields_mod.choose_zone(zones, prefer=self.zone_prefer) if fields_mod else None
        except Exception:
            pref = None
        if pref is not None and pref not in ordered:
            ordered.append(pref)
        for z in sorted(zones, key=lambda z: str(getattr(z, "name", ""))):
            if z not in ordered:
                ordered.append(z)
        return ordered

    def _plot_candidates(self, obs: dict[str, Any]) -> list[dict[str, Any]]:
        """按顺序给出"可能的作业区"，每个都是 `{zone, anchor, tiles, note}`。"""
        out: list[dict[str, Any]] = []
        zones = self._zones(obs)
        for z in self._ordered_zones(zones):
            try:
                p = fields_mod.plot_in_zone(z, obs, size=self.plot_size)
            except Exception:
                continue
            tiles = [tuple(int(v) for v in t) for t in (p.get("tiles") or [])]
            if not tiles:
                continue
            out.append({
                "zone": str(getattr(z, "name", "")),
                "label": str(getattr(z, "label", "")),
                "anchor": list(p.get("anchor") or []),
                "tiles": tiles,
                "note": str(p.get("note") or ""),
            })
        if out:
            return out
        near = self._near_player_plot(obs)
        return [near] if near else []

    def _near_player_plot(self, obs: dict[str, Any], radius: int = 4) -> dict[str, Any] | None:
        """没有田区信息（室内 / fields 缺失）时的兜底：玩家周围 (2r+1)² 窗口。"""
        pt = FarmWorker.player_tile(obs)
        tiles = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        keep: list[tuple[int, int]] = []
        for x in range(pt[0] - radius, pt[0] + radius + 1):
            for y in range(pt[1] - radius, pt[1] + radius + 1):
                t = (x, y)
                tv = tiles.get(t)
                if tv is not None or t in tillable:
                    keep.append(t)
        if not keep:
            return None
        return {
            "zone": "",
            "label": "",
            "anchor": [pt[0], pt[1]],
            "tiles": keep,
            "note": f"没有田区信息：以玩家 {pt} 为中心的 {2 * radius + 1}×{2 * radius + 1} 窗口",
        }

    def _seed_outlook(self, obs: dict[str, Any]) -> tuple[int, int, bool]:
        """(种子总数, 钱, 还能不能搞到种子)。"""
        player = FarmWorker.player_of(obs)
        seeds = sum(n for _i, _nm, n in seed_items(player))
        money = FarmWorker.money(obs)
        can = seeds > 0 or (self.allow_buy and money >= self.seed_price)
        return seeds, money, can

    def _plot_has_work(self, obs: dict[str, Any], tiles: Iterable[tuple[int, int]]) -> bool:
        tmap = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        _seeds, _money, can_plant = self._seed_outlook(obs)
        for t in tiles:
            if t in self.blocked:
                continue  # 今天已经证明"动了没用"
            tv = tmap.get(t)
            if tv is None:
                # 没动过的格子在 tiles[] 里根本不存在，只能靠 tillable[] 认。
                # 但**没种子又买不起**时锄地是纯烧体力（`_plot_brief` 的 broken 分支就是这么判的）：
                # 这里必须同口径，否则"守卫说还有活 / 策略说没事可做"会把一天耗成 stuck。
                if t in tillable and can_plant:
                    return True
                continue
            if tv.get("crop"):
                if not tv.get("watered") or tv.get("ripe"):
                    return True
                # 【task-51】枯死作物**也是活**：它占着耕地、挡着 `till`（`till_blocked_by` 见 crop 就拒），
                # 不清掉就永远开不了这一格。run5 真机夏季 2 日：窗口 24 个作物里 23 个 `dead=True`
                # ⇒ 这一趟一直返回 False ⇒ 作业区被判"没活"⇒ 一整天零动作。
                if tv.get("dead"):
                    return True
                continue
            kind = str(tv.get("kind") or "")
            if kind in ACTIONABLE_KINDS:
                return True
            if t in tillable and can_plant and not _till_blocked_by(tv):
                return True
            if kind == "dirt" and can_plant:
                return True
        return False

    def _ensure_plot(self, obs: dict[str, Any], rep: DayReport) -> dict[str, Any] | None:
        """挑（或保持）当天的作业区；找不到有活的区就返回 None。

        【task-32 软上限】`max_plots_per_day` 到顶后**只限制"换到新的作业区"这件事被计入
        `plots_today` / `rep.plots`**，绝不因此结束一天：只要还有区拿得出目标（`_plot_has_work`），
        就把那个区当作当前作业区接着干，并当天记一次 `plots_capped`（纯信息项，不改 VERIFIED）。

        理由（0.7.22 真机彩排 `logs\\longrun-rehearsal-0.7.22.jsonl`）：第 1 天 09:40、体力 144.7/270
        在 `plots_today >= 10` 时这里返回 None ⇒ 调用方 `_do_sleep(..., "no_plot")` ⇒ 被自己的
        配额憋停，而 `day_justified` 还接受 `no_plot` ⇒ 洗成 VERIFIED。用户 m02532/m00707
        抱怨的"还有体力、时间还早就准备睡觉"就是这一形态。
        """
        if self.plot is not None and self._plot_has_work(obs, self.plot["tiles"]):
            return self.plot
        for cand in self._plot_candidates(obs):
            if not self._plot_has_work(obs, cand["tiles"]):
                continue
            if self.plots_today >= self.max_plots_per_day:
                self.plot = cand
                self.zone_name = str(cand.get("zone") or "")
                if not self.plots_capped_noted:
                    note = (f"已开满 {self.plots_today} 片地（上限 {self.max_plots_per_day}），"
                            f"不再累计新作业区：直接在有活的「{self.zone_name or '窗口'}」继续做")
                    self.plots_capped_noted = True
                    rep.notes.append(note)
                    self._journal("plots_capped", plots_today=self.plots_today,
                                  limit=self.max_plots_per_day, zone=self.zone_name,
                                  tiles=len(cand["tiles"]), note=note)
                return self.plot
            self.plot = cand
            self.zone_name = str(cand.get("zone") or "")
            self.plots_today += 1
            rep.plots.append({
                "zone": cand.get("zone"), "anchor": cand.get("anchor"),
                "tiles": len(cand["tiles"]), "note": cand.get("note"),
            })
            self._say(f"  · 作业区 {cand.get('zone') or '窗口'} 锚点 {cand.get('anchor')}（{len(cand['tiles'])} 格）")
            self._journal("plot", zone=cand.get("zone"), anchor=cand.get("anchor"),
                          tiles=len(cand["tiles"]), note=cand.get("note"))
            return self.plot
        self.plot = None
        self.zone_name = ""
        return None

    def _work_spot_plot(self, obs: dict[str, Any]) -> dict[str, Any] | None:
        """【task-32 兜底】没有任何田区拿得出目标，但守卫说"还有活"时的**收尾作业区**。

        活 = 没浇水的 / 熟了的作物。这些格子可能落在 `fields` 切不出来的区里（或区全被判成
        "没活"），但守卫（`work_reasons`）已经把它们算成必须干完的活 —— 那就直接把**活所在的
        格子**当作业区交给策略/执行层（浇水/收获本来就是 `WIDE_TASKS`，按全场取目标），
        而不是用 `no_plot` 收工。这个容器**不计入** `plots_today`：它不是"新开一片地"。

        没有任何这样的格子 ⇒ 返回 None，调用方按"真没活"处理（守卫此刻不可能同时说要干活，
        真出现这种自相矛盾时按 `stuck` 如实收尾，不洗成 `no_work`）。
        """
        tmap = FarmWorker.tiles_of(obs)
        tiles = [t for t, v in tmap.items()
                 if v.get("crop") and (not v.get("watered") or v.get("ripe"))]
        if not tiles:
            return None
        pt = FarmWorker.player_tile(obs)
        return {
            "zone": "",
            "label": "",
            "anchor": [pt[0], pt[1]] if pt else list(tiles[0]),
            "tiles": tiles,
            "note": f"没有作业区但有 {len(tiles)} 格作物待浇/待收（收尾活，不计入换区配额）",
        }

    def _resume_plot(self, obs: dict[str, Any]) -> dict[str, Any] | None:
        """【task-49】把今天**已经见过、还没做完**的格子当作业区，回去把它做完。

        为什么需要它：观测是**以玩家为中心**的窗口，人一换片地，原来那片地的格子就不在
        `tiles[]`/`tillable[]` 里了 ⇒ `_plot_candidates`/`_plot_has_work` 都看不见它们。
        run5 第 1 天：field_nw 还剩 9 格未开垦，人在 field_se ⇒ 没有任何候选区拿得出目标 ⇒
        `no_work` 去睡（体力还剩 62.3）。

        容器里的格子全部来自 `self.leftover_targets`（`_step_stage` 每轮如实记下的 `leftover`，
        排除已封格），**不计入 `plots_today`**；调用方拿它去 `_walk_into_plot` 把人带回那片地，
        让人自己的传感器重新看见那些格子。上界由 `_run_day` 的 `self.resume_walks` 把关。
        """
        pending = self._pending_work()
        if not pending:
            return None
        pt = FarmWorker.player_tile(obs)
        tiles = sorted(pending, key=lambda t: (_dist(t, pt), t[1], t[0]))[:25]
        return {
            "zone": "",
            "label": "",
            "anchor": [tiles[0][0], tiles[0][1]],
            "tiles": tiles,
            "note": f"今天还有 {len(tiles)} 格没做完（跨片地，玩家窗口看不见）：回去接着做",
        }

    # ------------------------------------------------------------------ 简报
    def _plot_brief(self, obs: dict[str, Any], plot: dict[str, Any]) -> Brief:
        """当天作业区的局部简报：清障/开垦/播种按**区**计数，浇水/收获按**全场**计数。

        为什么浇水必须全局：一天的验收要求"所有作物都浇过"，只浇作业区里的作物会漏。
        为什么开垦要按区：全场 245 个障碍会让策略永远停在"清障"（见模块 docstring 铁律 3）。
        """
        tiles = [tuple(t) for t in plot["tiles"]]
        # `skip=self.blocked`：今天已证明干不动的格子**不能**再算进 blockers/tillable，
        # 否则"执行层拿不出目标、策略还在喊去干"⇒ 每轮空转（真机 run1 的两格 grass）。
        local_obs = plot_observe(obs, tiles, skip=self.blocked)
        sellable = 0
        try:
            if self.worker is not None:
                sellable = len(self.worker.sellable_slots(obs))
        except Exception:
            sellable = 0
        full = Brief.from_observe(obs, consecutive_failures=self.fail_streak,
                                  last_failure=self.last_failure, target_tiles=self.target_tiles_base,
                                  sellable=sellable)
        local = Brief.from_observe(local_obs, consecutive_failures=self.fail_streak,
                                   last_failure=self.last_failure, target_tiles=self.target_tiles_base)

        tmap = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        seeds, money, can_plant = self._seed_outlook(obs)
        usable = 0
        planted = 0
        for t in tiles:
            tv = tmap.get(t) or {}
            if tv.get("crop"):
                planted += 1
                usable += 1
            elif t in tillable:
                usable += 1
            elif str(tv.get("kind") or "") == "dirt":
                usable += 1
        # 没种子又买不起：这一片就只伺候"已经种下的"，别再锄新地烧体力
        broken = seeds <= 0 and not can_plant
        if broken:
            planted = sum(1 for t in tiles if (tmap.get(t) or {}).get("crop"))
            usable = max(planted, 0)
        capacity = max(1, min(usable, planted + seeds))

        counts = dict(local.counts)
        # `planner.Brief.unprepared = target - dirt - crops`，而 Mod 的 `tiles[]` 里**有作物的格子
        # kind 也是 "dirt"**（真机证据：feature=HoeDirt 且 crop=24）⇒ 不减掉就会把作物格算两遍，
        # `unprepared` 提前归零、永不进入开垦，随后被守卫判成"还有活"→ 一整天耗成 stuck。
        # planner 的 docstring 写的是"已有耕地 + 已种作物都算已准备"，所以这里给它的 dirt 是**空地**。
        counts["dirt"] = max(0, int(counts.get("dirt", 0)) - int(local.counts.get("crops", 0)))
        counts["unwatered_crops"] = int(full.counts.get("unwatered_crops", 0))
        counts["ripe"] = int(full.counts.get("ripe", 0))
        # 【task-51】枯死作物也按**全场（窗口）**计数：按区计数会让"这一片没死苗"压住
        # 策略，而隔壁片地正躺着 20 格枯死苗。`planner.deterministic_plan` 据此插 `clear_dead`。
        counts["dead"] = int(full.counts.get("dead", 0))
        if broken:
            counts["plantable"] = 0
        # 具名田区进简报：模型可以拿它当 `area_hint` 说"今天去哪片地"（方向由模型给、坐标由代码落）。
        # 田区名随农场地形变，所以是**动态真值**（`allowed_refs`），不写死进 `AREA_REF_PREFIXES`。
        areas: tuple[str, ...] = ()
        area_lines: tuple[str, ...] = ()
        if fields_mod is not None:
            zones = self._zones(obs)
            if zones:
                areas = tuple(z.name for z in zones)
                try:
                    area_lines = tuple(fields_mod.zone_brief_lines(zones))
                except Exception:  # pragma: no cover - 田区简报不该影响主流程
                    area_lines = ()
        return replace(
            local,
            counts=counts,
            seed_ids=full.seed_ids,
            seed_count=full.seed_count,
            inventory_size=full.inventory_size,
            target_tiles=capacity,
            areas=areas,
            area_lines=area_lines,
            # 【task-42】出货白名单件数来自执行层（`FarmWorker.harvested`），
            # 而它挂在 `full` 上 ⇒ 必须显式搬过来，否则 `ship` 意图永远不会出现。
            sellable=full.sellable,
        )

    def _stage_tiles(self, task: str, obs: dict[str, Any], plot: dict[str, Any]) -> list[tuple[int, int]]:
        """这一阶段要动的格子（已排序、已限数）。

        * `clear_area` / `till_area` / `plant_area`：**作业区内**；
        * `water_area` / `harvest`：**全场**（一天的验收要求把所有作物伺候完）。
        """
        tmap = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        pt = FarmWorker.player_tile(obs)
        local = [tuple(t) for t in plot["tiles"]]
        pool: list[tuple[int, int]]
        limit = self.per_stage_tiles

        if task == "water_area":
            pool = [t for t, v in tmap.items() if v.get("crop") and not v.get("watered")]
            limit = self.water_stage_tiles
        elif task == "harvest":
            pool = [t for t, v in tmap.items() if v.get("crop") and v.get("ripe")]
        elif task == "clear_dead":
            # 【task-51】枯死作物**按窗口取**（与 harvest 同口径）：死苗是农场卫生问题，
            # 一个作业区里往往散着十几格（真机窗口 23 格），按区取会把它们拖到明天。
            # 只认观测里 `dead` 为真的格子 ⇒ 活苗永远进不了这个池子。
            # 局限（如实记录）：窗口（`OBSERVE_REACH` 半径）外的死苗**没有坐标**，
            # Mod 只给计数（`farm.deadCrops`）⇒ 本卡清不到，由 `clear_dead_scope` journal 留痕。
            pool = [t for t, v in tmap.items() if v.get("crop") and v.get("dead")]
        elif task == "clear_area":
            pool = [t for t in local if str((tmap.get(t) or {}).get("kind") or "") in ACTIONABLE_KINDS]
        elif task == "till_area":
            # 以**观测**为准判"能不能锄"：Mod 的 `tillable[]` 会含"有未知特征"的假阳性格
            # （真机 (73,25) 一带，锄 16 下白烧 60+ 体力，用户 m01804）。
            pool = [t for t in local
                    if t in tillable and not _till_blocked_by(tmap.get(t))]
        elif task == "plant_area":
            pool = [t for t in local
                    if str((tmap.get(t) or {}).get("kind") or "") == "dirt" and not (tmap.get(t) or {}).get("crop")]
        else:
            pool = []
        if task in ("till_area", "plant_area"):
            # **没种子又买不起 ⇒ 今天不开垦**，与 `_plot_has_work`/`_plot_brief` 的 `can_plant`
            # 门槛**同口径**（这一层是执行层，三道口径必须一致，否则又是"守卫说有活、执行层
            # 拿不出目标"的空转）。run2 真机证据：`plant_area` 因 `no_seed` 停下之后，`till` 阶段
            # 照样把可锄格锄开（`hoeDirt` 35→92、其中 `emptyDirt=60` 一直空着），白烧体力 270→74。
            # 锄了种不下去 = 纯烧体力；播种同理（`sow` 一定会 `no_seed`）。
            _seeds, _money, can_plant = self._seed_outlook(obs)
            if not can_plant:
                pool = []
        if task in ("clear_area", "clear_dead", "till_area", "plant_area"):
            # 今天已经证明"动了没用"的格子不再碰（一格最多白试一次）；
            # 再叠一道"同一格一天最多发起 MAX_TILE_ATTEMPTS 次"的兜底不变量。
            pool = [t for t in pool
                    if t not in self.blocked
                    and self.tile_attempts.get(t, 0) < MAX_TILE_ATTEMPTS]
        pool = sorted(set(pool), key=lambda t: (_dist(t, pt), t[1], t[0]))
        return pool[:limit]

    def _leftover(self, task: str, obs: dict[str, Any], plot: dict[str, Any]) -> list[tuple[int, int]]:
        """后置条件复核：这一阶段**该做完的事**，现在还剩几格没做。

        ⚠️ 这里**刻意不排除 `self.blocked`**（"今天已经证明干不动"的格子）：`blocked` 只用来
        决定**还要不要再试**（`_stage_tiles` 会把它剔掉），**绝不能用来判定成功** —— 否则
        "动了没用"的格子会被从剩余集合里抹掉 ⇒ `met=true` ⇒ 硬失败被洗成 VERIFIED
        （真机 run2 第 1 天：`no_hard_failures=false`，阶段级却报 ok；task-3 §4 指出过同一处）。
        剩下的格子里哪些"已判定干不动"，由 `_step_stage` 在 reason 里**单独报数**，不混进判据。
        """
        tmap = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        local = [tuple(t) for t in plot["tiles"]]
        if task == "water_area":
            return [t for t, v in tmap.items() if v.get("crop") and not v.get("watered")]
        if task == "harvest":
            return [t for t, v in tmap.items() if v.get("crop") and v.get("ripe")]
        if task == "clear_dead":
            # 【task-51】与 `_stage_tiles` 同口径、**刻意不排除 `self.blocked`**（task-9 铁律）：
            # 窗口里还有枯死作物 ⇒ 这一阶段就没做完（清不掉的那些由 `_step_stage` 单独报数）。
            return [t for t, v in tmap.items() if v.get("crop") and v.get("dead")]
        if task == "clear_area":
            return [t for t in local
                    if str((tmap.get(t) or {}).get("kind") or "") in ACTIONABLE_KINDS]
        if task == "till_area":
            # task-15 §②（修法 A）：**种子闸门必须与 `_stage_tiles` 同口径**。
            # 没种子又买不起时，锄地是纯烧体力（`_stage_tiles` 已经把目标掐成空），
            # 后置条件复核若还报"还剩 N 格"，就会造出一轮"0 目标、leftover>0"的假剩余：
            # run3 开局（14g、种完 0 种子）会被自己判死。留 `met=False`（没有进展）即可，
            # 但**不制造剩余**。注意这与 `stage_exhausted` 的 leftover>0 语义不同：
            # 那条是"该做的没做成"（task-9 条款①），这里只是"本来就不该做"。
            if not self._seed_outlook(obs)[2]:
                return []
            return [t for t in local
                    if t in tillable and not _till_blocked_by(tmap.get(t))]
        if task == "plant_area":
            if not self._seed_outlook(obs)[2]:
                return []  # 同上：没种子可播 ⇒ 没有"该播而没播"的剩余
            return [t for t in local
                    if str((tmap.get(t) or {}).get("kind") or "") == "dirt"
                    and not (tmap.get(t) or {}).get("crop")]
        return []

    # ------------------------------------------------------------------ 睡觉判据
    def work_reasons(self, obs: dict[str, Any]) -> list[str]:
        """"还有活可做"的理由（空 = 真的没活了）。"""
        reasons: list[str] = []
        tmap = FarmWorker.tiles_of(obs)
        unwatered = [t for t, v in tmap.items() if v.get("crop") and not v.get("watered")]
        if unwatered:
            reasons.append(f"有 {len(unwatered)} 格作物没浇水")
        ripe = [t for t, v in tmap.items() if v.get("crop") and v.get("ripe")]
        if ripe:
            reasons.append(f"有 {len(ripe)} 格作物熟了")
        seeds, money, can_plant = self._seed_outlook(obs)
        if seeds <= 0 and can_plant:
            reasons.append(f"没种子但钱够（{money}g ≥ {self.seed_price}g），该去买")
        # 【run3 真 bug B】人不在农场时，窗口观测只覆盖室内 ⇒ 上面两条必然为空。
        # 真值在 `farm` 块（`complete=true` 时 `dryCrops`/`ripeCrops` 是全农场口径）：
        # 有干作物/熟作物就是"还有活"，而且第一件事是**先回农场**（见 `_ensure_on_farm`）。
        farm_work = self._farm_scope_work(obs)
        if farm_work is not None:
            dry, ripe = farm_work
            if dry > 0:
                reasons.append(f"人不在农场，但 farm 口径还有 {dry} 格干作物（先回去浇）")
            if ripe > 0:
                reasons.append(f"人不在农场，但 farm 口径还有 {ripe} 格熟作物（先回去收）")
        elif not self._is_farm(obs):
            # 【task-41 NIT-2，Lead rev4 §10 硬要求】人在室内、而 `farm` 证据不可用
            # （`complete` 不为 true / `loaded` 为 false）⇒ 这条理由**必须出现在这里**：
            # `_run_day` 里 `why = ("no_work" if not reasons else "stuck:守卫说还有活（…）")`
            # ⇒ 理由缺失就会落回 `no_work`，run3 连睡 4 天的路径原地复活。
            reasons.append(self._farm_evidence_reason(obs))
        # 【task-49】人在农场里时也要看全农场读数：窗口只有半径 ~14，农场另一头的干作物
        # 在窗口里根本不存在。run5 第 1 天 `farm.dryCrops=1` 就是这么被丢掉的。
        totals = self._farm_totals(obs)
        if self._is_farm(obs) and totals is not None:
            dry_f, ripe_f = totals
            if dry_f > len(unwatered):
                # 【task-50】干作物常常在玩家 400 格窗口之外 ⇒ 理由里带上 Mod 报的坐标，
                # 否则"还有 1 格干"既没法行动、也没法在收尾时点名（run5 三天全挂的形态）。
                reasons.append(self._far_dry_reason(obs, dry_f))
            if ripe_f > len(ripe):
                reasons.append(f"农场口径还有 {ripe_f} 格熟作物（当前窗口只看到 {len(ripe)} 格）")
        # 【task-49】今天**已经见过、但还没做完**的格子（`_step_stage` 的 `leftover`）。
        # 换到别的片地之后，那些格子不在玩家窗口里 ⇒ 必须靠这份记账才知道"还有活"，
        # 否则就是 run5 的 `no_work` 早睡。已封格（`tool_ineffective` 一类）**不算** ——
        # 那正是"这一格今天真干不动"的结论（反向用例：全部 leftover 都封了 ⇒ 允许 `no_work`）。
        pending = self._pending_work()
        if pending:
            reasons.append(f"今天早些时候还有 {len(pending)} 格没做完（跨片地，最近的是 "
                           f"{list(min(pending, key=lambda t: _dist(t, FarmWorker.player_tile(obs))))}）")
        for cand in self._plot_candidates(obs):
            if self._plot_has_work(obs, cand["tiles"]):
                reasons.append(f"{cand.get('zone') or '附近'}还有地要清/开/种")
                break
        return reasons

    def _pending_work(self) -> list[tuple[int, int]]:
        """今天"见过但还没做完、且今天没被证明干不动"的格子（task-49）。

        判据与 `_stage_tiles` 的排除项一致：**已封格不算**（`self.blocked` 是
        "判据证明这一格今天干不动"）。`tile_attempts` 到顶的格子仍然算 —— 它们是
        "今天试过但没做成"的真目标，允许守卫因此不判 `no_work`（当天会如实 `stuck`/
        needs_review，而不是洗成"没活"）。
        """
        return sorted(t for t in self.leftover_targets if t not in self.blocked)

    def _farm_evidence_reason(self, obs: dict[str, Any]) -> str:
        """室内 + `farm` 证据不可用时的"还有活"理由（task-41 NIT-2，fail-closed）。

        为什么这算"还有活"：**不知道**地里干没干 ⇒ 绝不许据此判"没活可做"（run3 连睡 4 天就是这么来的）。
        有界性**不靠** `idle_rounds`（它只在走完 `_execute` 且世界指纹没变时才涨）：`_run_day` 的
        `spot = _work_spot_plot(...) or _near_player_plot(...)` 为 `None` 那条**单次分支**会直接
        `<ended_by>="stuck"` + `break`，一天只走一次、不空转。
        journal `farm_evidence_unavailable` 每天最多一条（`self.farm_evidence_noted`）。
        """
        farm = obs.get("farm") or {}
        loc = str((obs.get("location") or {}).get("name") or "?")
        if not self.farm_evidence_noted:
            self._journal("farm_evidence_unavailable", complete=farm.get("complete"),
                          loaded=farm.get("loaded"), location=loc,
                          note="人在室内但 farm 证据不可用（complete/loaded）⇒ 不许判 no_work；"
                               "先回农场再判，当天拿不出目标则以 stuck 如实收尾（一天只走一次，不空转）")
            self.farm_evidence_noted = True
        return (f"人在室内（{loc}）且 farm 证据不可用（farm.complete={farm.get('complete')!r}/"
                f"loaded={farm.get('loaded')!r}）⇒ farm 口径不算证据，先回农场再判有没有活")

    def _can_water(self, obs: dict[str, Any]) -> tuple[bool, str]:
        """还能不能继续浇：有壶，且壶里有水（或能去补水 / 无尽壶）。

        照抄 `farmwork.FarmWorker.water_left` 的语义，但用**静态**读法（假 worker 没有 `water_left`）。
        """
        can = FarmWorker.can_state(obs)
        if not can.get("present") and not can.get("bottomless"):
            return False, "没有浇水壶"
        if can.get("bottomless"):
            return True, "水壶水量无限"
        left = int(can.get("waterLeft") or 0)
        if left > 0:
            return True, f"壶里还有 {left} 格水"
        refill = FarmWorker.refill_of(obs)
        if refill:
            return True, f"能去补水（{len(refill)} 个补水点）"
        return False, "壶空了，也没有补水点"

    def sleep_guard(self, obs: dict[str, Any]) -> tuple[bool, str, str]:
        """能不能睡：(放行?, 代码, 人话)。代码会写进当天 checks 里的 `day_justified`。

        放行只有四种：到深夜 / 没水可浇且体力见底 / 确实没活 / 连水都浇不了。**当天的水没浇完
        一律先浇**（用户 m01774："每天都要浇水吧，除了雨天"；m01770："后面体力不够咋办"）——
        作物当天没浇，第二天补不回来；而浇水每格只要 1 点体力，比锄地便宜得多。
        """
        tod = FarmWorker.time_of_day(obs)
        stam = FarmWorker.stamina(obs)
        if tod >= self.sleep_at or tod < 600:
            return True, "night", f"时间 {tod} 已经到夜里（≥{self.sleep_at}）"
        tmap = FarmWorker.tiles_of(obs)
        unwatered = [t for t, v in tmap.items() if v.get("crop") and not v.get("watered")]
        if unwatered:
            can, why = self._can_water(obs)
            if can and tod < 2500 and stam >= self.water_min_stamina:
                return False, "keep_working", (
                    f"还有 {len(unwatered)} 格作物没浇水（{why}），先把水浇完"
                )
        if stam < self.min_stamina:
            return True, "stamina", f"体力 {stam:g} < {self.min_stamina:g}"
        # 【run3 真 bug C】"没活"这条放行理由**必须在户外农场观测上成立**：人在室内
        # （睡醒在 FarmHouse）时窗口 `crops=0`，而 `farm` 口径可能还有一堆干作物 ——
        # 此时一律否决（先回农场），绝不允许把"人没到地里"当成"地里没活"。
        farm_work = self._farm_scope_work(obs)
        if farm_work is not None and (farm_work[0] > 0 or farm_work[1] > 0):
            loc = str((obs.get("location") or {}).get("name") or "?")
            return False, "keep_working", (
                f"人在室内（{loc}）、farm 口径还有 {farm_work[0]} 格干作物 / "
                f"{farm_work[1]} 格熟作物，先回农场再说"
            )
        if farm_work is None and not self._is_farm(obs):
            # 【task-41 NIT-2】证据不可用 ⇒ fail-closed：**绝不**退回窗口口径放行 `no_work`
            # （run3 那 4 天连睡就是这么来的）。理由与 `work_reasons` 共用一份实现，避免口径漂移。
            return False, "keep_working", self._farm_evidence_reason(obs)
        # 【task-49】人在农场里、全农场读数说还有干/熟作物，而玩家窗口没盖到 ⇒ 必须继续干；
        # 有水（壶里 / 能走到补水点 / 无尽壶）就去浇；**确实打不到水**才允许睡，而且这里
        # 绝不能返回 `no_work`（"想浇但无水"和"没活可做"是两件事；run5 第 1 天 `dry=1` 却
        # 以 `no_work` 收场、还白拿一个 `day_justified=true`，就是这条缺失造成的）。
        totals = self._farm_totals(obs)
        if self._is_farm(obs) and totals is not None:
            dry_f, ripe_f = totals
            if ripe_f > 0:
                return False, "keep_working", (
                    f"农场口径还有 {ripe_f} 格熟作物（当前窗口没盖到，别处还有活），先去收")
            if dry_f > 0:
                can, why = self._can_water(obs)
                # 【task-50】那一格干作物常常在玩家窗口之外：把 Mod 报的坐标写进理由，
                # 这样"当天以 stuck 收尾"时 `ended_reason` 能点名到底哪一格没浇成。
                where = self._far_dry_where(obs)
                if can and tod < 2500 and stam >= self.water_min_stamina:
                    return False, "keep_working", (
                        f"农场口径还有 {dry_f} 格干作物{where}（{why}），先把水浇完再谈收工")
                if not can:
                    return True, "no_water", (
                        f"农场口径还有 {dry_f} 格干作物{where}，但{why}（想浇但无水；"
                        "这不是「没活可做」，当天按 needs_review 如实收尾）")
        reasons = self.work_reasons(obs)
        if not reasons:
            return True, "no_work", "确实找不到可做的活（地里的活干完了、也没法/没必要买种子）"
        return False, "keep_working", "；".join(reasons)

    # ------------------------------------------------------------------ 前置条件
    def _preconditions(self, obs: dict[str, Any], rep: DayReport) -> None:
        """种子没了就买。买不成**如实记账**，不让后面每一格去撞同一堵墙。"""
        player = FarmWorker.player_of(obs)
        seeds_total = sum(n for _i, _nm, n in seed_items(player))
        if seeds_total > 0:
            return
        assert self.worker is not None
        money = FarmWorker.money(obs)
        if not self.allow_buy:
            rep.notes.append("没种子（本轮禁止买种子）")
            return
        if money < self.seed_price:
            rep.notes.append(f"没种子且钱不够（{money}g < {self.seed_price}g），只能干等/清障开垦")
            return
        st = self.worker.buy(self.buy_item, self.buy_count, shop=self.shop)
        self._actions += 1
        rep.notes.append(f"补种子：{st.reason}")
        self._say(f"  · 补种子：{st.reason}")
        self._journal("buy", ok=st.ok, code=st.code, reason=st.reason,
                      before=st.before, after=st.after, receipt=st.receipt)

    # ------------------------------------------------------------------ 睡觉
    def _do_sleep(self, obs: dict[str, Any], rep: DayReport, why: str) -> tuple[str, str]:
        assert self.worker is not None
        rep.final = self._essence(obs)          # ← 睡前观测：一天的验收就拿它当差分右端
        st = self.worker.sleep(home=self.home)
        self._actions += 1
        # 【task-8 D】receipt 必须进 journal：sleep 的失败原因全在 Mod 回执原文里
        # （`sleep_no_question` 带 lastQuestionKey/isInBed/activeMenu 诊断，`timeout` 带
        # newDaySync 现场）。旧实现只记 reason ⇒ run2 的 journal 里只剩一句"睡觉请求失败"。
        self._journal("sleep", ok=st.ok, code=st.code, reason=st.reason,
                      before=st.before, after=st.after, receipt=st.receipt)
        if st.ok:
            self._say(f"  · 睡觉：{st.reason}（{why}）")
            rep.notes.append(f"主动睡觉：{why}；{st.reason}")
            return "sleep", why
        rep.notes.append(f"睡觉失败：{st.reason}（{why}）")
        return "sleep_failed", st.reason

    # ------------------------------------------------------------------ 执行
    def _run_stage_intent(self, intent: TaskIntent, obs: dict[str, Any], plot: dict[str, Any],
                          rep: DayReport) -> bool:
        """执行一个阶段意图：发动作 → 差分复核 → 记账。返回"今天有没有真的推进"。"""
        task = intent.task
        outcome = self._step_stage(task, obs, plot, rep)
        rep.outcomes.append(outcome.as_dict())
        self._journal("outcome", kind=task, terminal=outcome.terminal,
                      postcondition_met=outcome.postcondition_met, reason=outcome.reason,
                      detail=outcome.evidence)
        if outcome.error:
            self.fail_streak += 1
            self.last_failure = f"{task}: {outcome.error}"
            rep.notes.append(f"{task} 失败：{outcome.error}")
        else:
            self.fail_streak = 0
        return outcome.postcondition_met or outcome.progress

    @staticmethod
    def _tile_states(obs: dict[str, Any]) -> dict[tuple[int, int], tuple[Any, ...]]:
        """每格的关键状态：用来判"我动了这一格，世界到底变了没"。"""
        out: dict[tuple[int, int], tuple[Any, ...]] = {}
        for v in (FarmWorker.tiles_of(obs) or {}).values():
            t = tuple(v.get("tile") or ())
            if len(t) == 2:
                out[t] = (v.get("kind"), v.get("crop"), v.get("watered"), v.get("ripe"),
                          v.get("plantable"))
        return out

    def _mark_blocked(self, before_obs: dict[str, Any], after_obs: dict[str, Any],
                      steps: list[StepResult], rep: DayReport, *, stage: str = "") -> None:
        """把"动了但世界没变"的格子记进 `self.blocked`：今天不再碰（一格最多白试一次）。

        只记 `till`/`clear`/`sow` 这类**主观能动**的动作。浇水失败不封格 —— "当天所有作物都浇过"
        是当天的验收条件，封掉就等于自欺（`_leftover` 仍会如实把它报出来，天不算数）。

        两种来源都要封：
        - `s.failed`：动作发了、体力花了、世界没变（旧口径）；
        - `s.proven_inert`（task-4 新增）：**动手前**判据就成立、压根没挥（缺工具 / 观测说这格
          今天动不了）。这种"zero-cost skip"同样是"今天别再碰它"的结论，但**不记 failed** ——
          真机 run1 的两个 grass 格就是这么被连挥两次、真花体力的（用户 m01804）。

        **但两类失败不许封格**（task-22，两者都靠 `FarmWorker` 打的显式标记）：
        - `s.env_block`（渐黑 / 模态 / 没存档 / Mod 忙）：环境挡路**不是**这一格的属性，世界好了这格还得做；
        - `s.inconclusive`（超时 / `stale`）：连结论都没拿到，更没资格判它"干不动"。
          注意口径（task-22 裁定 A，见 `farmwork._classify_status`）：只有"整轮一次真实回应都没拿到"
          才算 `inconclusive`；**未枚举的状态码按"Mod 真的回应过"处理**（走结论路径 —— Mod 回话了、
          世界没变），不许塞进这个桶里当成"没拿到证据"。
          这两类如实卡在 `leftover` 里 ⇒ `met=False`、当天 needs_review。
        """
        before = self._tile_states(before_obs)
        after = self._tile_states(after_obs)
        marked = 0
        unreach_marked = 0
        for s in steps:
            if not s.tile:
                continue
            if not s.unreachable:
                # 旧口径不动：只有 `till`/`clear`/`sow` 这类**主观能动**的动作才记「动了没用」。
                if not (s.failed or s.proven_inert) or s.action not in ("till", "clear", "sow"):
                    continue
            if s.env_block or s.inconclusive:
                # 环境挡路 / 没结论 ≠ 这一格干不动：不封格（记进 env_fail/inconclusive_fail 汇总）。
                continue
            key = tuple(s.tile)
            if key in self.blocked:
                continue
            if s.unreachable:
                # 【task-52】"走不到"也是**当天**别再白试（否则每一轮策略都重新要同一格、
                # 每次都白花一次寻路/观察）；但它**不是**"这格干不动"（世界可能变好），
                # 所以：① 只进当天的 `blocked`（`_run_day` 每天清空 ⇒ 次日自动重试）；
                # ② reason 原样保留（含「四邻都站不过去」或 Mod 的 A* 原文）；
                # ③ 逐格发 journal（`tools\verify-run3.py` 靠它自算/交叉核对）。
                self.blocked[key] = f"{s.action} 走不到：{s.reason[:80]}"
                self.unreachable_day.add(key)
                unreach_marked += 1
                self._journal("unreachable", tile=list(key), action=s.action, stage=stage,
                              zone=self.zone_name, reason=s.reason[:200],
                              note="四邻都站不过去/寻路到不了 ⇒ 当天不再白试（次日会重试）；"
                                   "不算硬失败，日级另有有界豁免")
                continue
            if before.get(key) != after.get(key):
                continue
            self.blocked[key] = f"{s.action} 无效：{s.reason[:80]}"
            marked += 1
            self._journal("blocked", tile=list(key), action=s.action,
                          no_effect=bool(s.failed), reason=s.reason[:160])
        if marked:
            rep.notes.append(
                f"记下 {marked} 格「动了没用」的地，今天不再碰（共 {len(self.blocked)} 格）")
        if unreach_marked:
            rep.notes.append(
                f"记下 {unreach_marked} 格「走不到」的地，今天不再白试（次日重试；不算硬失败）")

    def _count_attempts(self, steps: list[StepResult]) -> None:
        """统计"每格今天**白试**过几次"（`MAX_TILE_ATTEMPTS` 兜底不变量）。

        只数**没做成**的发起（`failed` / `proven_inert`）：纯 `skipped` 没花体力；而做成了的
        （或只是种子/水不够这种资源问题）更不该占配额 —— 同一格一天"清障 → 锄地 → 播种"
        是三次**正常**动作，按发起次数封格会把好格子一起封掉（单测
        `test_single_day_verified_and_world_changed` 当场抓到：25 格里 5 格永远种不下去）。

        **`env_block` 不占配额**（task-22 §4.7）：本函数**不带动作过滤**，浇水/收获/补水/走路
        上的任何失败都会落到这里 —— 一次瞬时渐黑或模态（`timeout`/`no_save`/`ui_modal`/
        `world_fading` 是全桥通用 status）本该是可重试的环境抖动，却会把该格推到
        `MAX_TILE_ATTEMPTS` → `capped` → `stage_exhausted`，当天被杀。

        **`inconclusive` 仍计配额**：它不是"环境挡路"而是"连结论都没拿到"；持续如此应当被限流
        成 `capped`，让当天如实落进 needs_review，而不是无限重试磨到天亮。

        **防自旋（task-28 N4-1）**：`env_block` 不占配额 ⇒ 若 Mod 持续回 `busy`（run2 真机就有
        "180s 客户端超时期间任何 exec 都被 `RejectBusy` 快速拒绝"这种时序），`_stage_tiles` 每轮
        都会把同一格重新选出来，一天就耗在同一格上。所以这里按格记 `env_streak`：
        连续被挡**超过** `MAX_ENV_ATTEMPTS` 次之后，第 N+1 次起照样占 `tile_attempts` 配额
        ⇒ 很快到 `MAX_TILE_ATTEMPTS` ⇒ 该格不再进目标、当天 `verified=False`（`capped` ⇒
        `needs_review`），但**始终不写 `blocked`、不写 `proven_inert`**（环境挡路永远不等于
        "这一格干不动"）。成功一次即清零。
        """
        # 先清掉"这一轮真做成了"的格的连续被挡计数（成功即断链，下一格重新从 1 数起）。
        for s in steps:
            if s.ok and s.tile:
                self.env_streak.pop(tuple(s.tile), None)
        for s in steps:
            if not s.tile or not (s.failed or s.proven_inert):
                continue
            key = tuple(s.tile)
            if s.env_block:
                streak = self.env_streak.get(key, 0) + 1
                self.env_streak[key] = streak
                if streak <= MAX_ENV_ATTEMPTS:
                    continue
                if key not in self.env_spin_noted:
                    self.env_spin_noted.add(key)
                    self._journal("env_spin_capped", tile=list(key), streak=streak,
                                  limit=MAX_ENV_ATTEMPTS,
                                  note="同一格连续被环境挡住超过上限 ⇒ 不再免费：按「没结论」"
                                       "占本日尝试配额（不封格；持续如此会如实 capped/needs_review）")
                self.tile_attempts[key] = self.tile_attempts.get(key, 0) + 1
                continue
            self.tile_attempts[key] = self.tile_attempts.get(key, 0) + 1

    def _walk_into_plot(self, obs: dict[str, Any], plot: dict[str, Any]) -> bool:
        """走进作业区（站到区内某一格的旁边）。用来补偿"观测以玩家为中心"这件事。

        不是"跟着人找地"（用户 m00601 反对的那种漂移）：**地是策略/田区层选定的**，
        这里只是把人带过去，让传感器看得见它。
        """
        assert self.worker is not None
        pt = FarmWorker.player_tile(obs)
        tiles = sorted((tuple(t) for t in plot.get("tiles") or []),
                       key=lambda t: (_dist(t, pt), t[1], t[0]))
        for tile in tiles[:3]:
            try:
                if self.worker.stand_next_to(tile, timeout_ms=self.plot_walk_timeout_ms):
                    return True
            except BridgeError:
                return False
        return False

    def _step_stage(self, task: str, obs: dict[str, Any], plot: dict[str, Any],
                    rep: DayReport) -> TaskOutcome:
        assert self.worker is not None
        all_steps: list[StepResult] = []
        stopped = ""
        attempts = 0
        walked = False
        # **没种子又买不起 ⇒ 今天不碰开垦/播种**（执行层的第三道同口径，见 `_stage_tiles`）。
        # 先在这里说一句人话 + 记 journal，再去跑（跑起来会"一格目标都没有"，但那是空转的表现，
        # 不是原因）。只播报一次，别每轮刷屏。
        if task in ("till_area", "plant_area") and task not in self.seed_gate_noted:
            seeds, money, can_plant = self._seed_outlook(obs)
            if not can_plant:
                self.seed_gate_noted.add(task)
                note = (f"没种子也没钱（种子 {seeds} 粒、钱 {money}g < 单价 {self.seed_price}g）"
                        f"⇒ 今天不再开垦/播种：{task} 没有目标（锄了也种不下去 = 纯烧体力）")
                rep.notes.append(note)
                self._say(f"  · {note}")
                # task-15 §③：`in_plot` = 撞上这道闸门时**人是不是已经在作业区里**。
                # 在田里才发现"没种子也没钱"是最贵的一种（白走一趟 + 游戏内时间已经过去），
                # 而在田外撞上则只是"今天这活不存在"。真机上这条字段用来核对
                # "买种子的时机够不够早"（`_preconditions` 是每个决策之前跑，够早；
                # 唯一的墙钟成本是走到 SeedShop 的那段路，见模块 docstring 的已知局限）。
                pt = FarmWorker.player_tile(obs)
                in_plot = pt is not None and tuple(pt) in {tuple(t) for t in plot["tiles"]}
                self._journal("seed_gate", stage=task, seeds=seeds, money=money,
                              seed_price=self.seed_price, zone=self.zone_name, in_plot=in_plot)
        # 【task-51】清死苗阶段：把"窗口里看得见几格"与"农场口径总共还剩几格"一起记下来。
        # 为什么必须有：窗口（`OBSERVE_REACH` 半径）外的死苗**没有坐标**（Mod 只给
        # `farm.deadCrops` 计数）⇒ 本卡清不到；但绝不许把"看不见"说成"没有了"。
        # `farm_status="unavailable"` = 旧 Mod 没这个字段/farm 证据不可信（计数不可当 0）。
        if task == "clear_dead" and task not in self.dead_scope_noted:
            self.dead_scope_noted.add(task)
            in_view = sum(1 for _tv in FarmWorker.tiles_of(obs).values()
                          if _tv.get("crop") and _tv.get("dead"))
            farm_dead, farm_status = farm_dead_crops(obs)
            self._journal("clear_dead_scope", in_view=in_view, farm=farm_dead,
                          farm_status=farm_status,
                          note=("窗口内可见的枯死作物格数 vs Mod 农场口径（farm.deadCrops）："
                                "窗口外的死苗没有坐标，本卡清不到，只做留痕"))
        wmin = self.water_min_stamina if task == "water_area" else self.min_stamina
        # task-15 §④：环境挡路（渐黑/模态/没存档/Mod 忙）**不是"这活没干成"**。遇到时先把
        # 挡路的模态收掉（`_clear_modals`），再**重跑同一批格子**（`forced`），最多
        # `max_env_retries` 轮。`env_retries` 是重试计数；`forced` 非空表示下一轮必须跑
        # 这一批格子（而不是重算 `_stage_tiles` —— 那会在环境抖动时换一批、把"重试"变成"扩大"）。
        env_retries = 0
        forced: list[tuple[int, int]] | None = None
        while True:
            if forced is None:
                attempts += 1
            snap = self._snap()
            if forced is not None:
                tiles = list(forced)
                forced = None
            else:
                tiles = self._stage_tiles(task, snap, plot)
            if not tiles and not walked:
                # 观测是**以玩家为中心**的：`tiles[]` 上限 400 且近处优先，`tillable[]` 同理。
                # 站在别处问"这片地还有可锄的吗"，答案会是 0 —— 真机证据：浇完水站在田区另一头，
                # `till_area` 得到 0 格、`no_target` 记账、策略被清空、然后掉头回家睡觉
                # （用户 m02532 当场抓到的现象）。所以目标为空时先**走进作业区**再重新看一次。
                walked = True
                if self._walk_into_plot(snap, plot):
                    self._actions += 1
                    self._journal("plot_walk", stage=task, zone=self.zone_name,
                                  note="目标为空 ⇒ 先走进作业区，再重新观测一次")
                    continue
            if not tiles:
                break
            res: StageResult = self.worker.run_stage(
                task, tiles, min_stamina=wmin, max_steps=self.per_stage_tiles)
            all_steps.extend(res.steps)
            self._actions += len(res.steps)
            # **每轮就封格 + 记发起次数**（不是等阶段跑完）：
            # 撞到 `budget` 会 continue 再跑一轮，而 `_stage_tiles` 是每轮现算的 ——
            # 若等到阶段结束才 `_mark_blocked`，同一格注定干不动的格子会在后续每一轮
            # 被重新选中再白试一次（run1 的两格 grass 就是这么被连挥的）。
            self._count_attempts(res.steps)
            self._mark_blocked(snap, self._snap(), res.steps, rep, stage=task)
            # task-15 §④：本轮有**环境挡路**的失败步 ⇒ 先收模态、再重跑同一批格子。
            # 判据只有一份（`is_env_blocked` → `farmwork.ENV_BLOCK_STATUSES`），不另抄状态码。
            env_round = [s for s in res.steps if is_env_blocked(s)]
            if env_round and env_retries < self.max_env_retries:
                env_retries += 1
                pre = self._snap()
                modal_now = (pre.get("ui") or {}).get("activeMenu")
                _obs2, modal_blocked = self._clear_modals(pre, rep)
                self._journal(
                    "env_retry", stage=task, zone=self.zone_name, round=env_retries,
                    limit=self.max_env_retries, tiles=len(tiles),
                    targets=[list(t) for t in tiles[:6]],
                    modal=modal_now,
                    statuses=sorted({x for s in env_round for x in statuses_of(s)}),
                    note="环境挡路（渐黑/模态/没存档/Mod 忙）不是「这活没干成」⇒ 先收掉挡路模态，"
                         "再重跑同一批格子；事后做成就没有硬失败")
                if modal_blocked:
                    # 模态关不掉（职业选择弹窗等）/ 游戏事件挂住（task-41）⇒ 当天到此为止：
                    # `rep.ended_by` 已被设成 `blocked_modal` 或 `blocked_event`，
                    # `_run_day` 会在 `_execute` 之后立刻收工。
                    stopped = rep.ended_by or ENDED_BY_MODAL
                    break
                forced = tiles
                continue
            if res.stopped == "need_refill" and attempts <= 2 and self.refills_today < self.max_refills_per_day:
                rf = self.worker.refill_can()
                self.refills_today += 1
                self._actions += 1
                rep.notes.append(f"补水：{rf.reason}")
                self._journal("refill", ok=rf.ok, reason=rf.reason, before=rf.before, after=rf.after)
                if rf.ok:
                    continue
            if res.stopped == "budget" and attempts < self.max_stage_rounds:
                # 撞到"每次只做 N 格"的上限：还有目标就接着跑完（真机 m01770：浇水只做 12 格、
                # 剩下 19 格没浇就天黑了）。
                continue
            stopped = res.stopped
            break

        fresh = self._snap()
        # `_mark_blocked` 已改为**每轮**在循环内调用（见上），这里不再补一次：
        # 循环外的 `obs` 是阶段开始时的快照，用它当"动手前"会把中间几轮的变化算错。
        leftover = self._leftover(task, fresh, plot)
        # "还可能再试"的剩余：既没被封格、也没到本日尝试上限。
        retryable = [t for t in leftover
                     if t not in self.blocked and self.tile_attempts.get(t, 0) < MAX_TILE_ATTEMPTS]
        doomed = [t for t in leftover if t in self.blocked]
        capped = [t for t in leftover
                  if t not in self.blocked and self.tile_attempts.get(t, 0) >= MAX_TILE_ATTEMPTS]
        # ⚠️ 后置条件必须**先有目标**才算成立：`_stage_tiles` 返回空（这一阶段没有该动的格子）时
        # `leftover` 也是空，"空集 ⇒ 成立"会变成假进展 —— 策略层要是反复要同一件没目标的事，
        # 这一天就会空转到天亮。所以恒等于 False，只当作"没事可做"。
        # 另一条（task-9）：`leftover` **含被封格的格子**，所以"只剩干不动的格子"时 met=False ——
        # 封格只免掉重试，不许把失败洗成成功。
        met = bool(all_steps) and not leftover
        failed_any = [s for s in all_steps if s.failed]
        # task-15 §④ 要求 2：日级硬失败只数**目标尚未完成**的失败。一次渐黑/一个弹窗之后
        # 重试做成的格子不算硬失败（`leftover` 里没有它 = 目标已达成）；`tile is None` 的步
        # （阶段级失败、没有具体格子）照旧算失败。
        left_set = {tuple(t) for t in leftover}
        failed = [s for s in failed_any if s.tile is None or tuple(s.tile) in left_set]
        # 【task-49】把"今天见过、还没做完"的格子记进 `leftover_targets`（排除已封格）：
        # 换到别的片地之后玩家窗口看不见它们，守卫与 `_resume_plot` 只能靠这份记账。
        # 同一步里做成的格子要**划掉**（否则"做完的格子"会一直把我们往回拽）。
        for s in all_steps:
            if s.ok and s.tile:
                self.leftover_targets.discard(tuple(s.tile))
        for t in leftover:
            tt = tuple(t)
            if tt in self.blocked:
                continue                    # 判据证明这一格今天干不动 ⇒ 不算"还有活"
            self.leftover_targets.add(tt)
        skipped = [s for s in all_steps if s.skipped]
        oks = [s for s in all_steps if s.ok]
        inert = [s for s in all_steps if s.proven_inert]
        env_fail = [s for s in all_steps if s.env_block]
        inconclusive = [s for s in all_steps if s.inconclusive]
        # 【task-52】"走不到"（没有落脚点/寻路到不了）：**不算失败**，单独计数 + 逐格留痕。
        # `unreachable_in_leftover` 是"这些格里有多少还留在后置条件的剩余集合里" —— 日级
        # `no_unmet_stages` 的有界豁免要靠它（只豁免真正走不到的那些格，不是整段 leftover）。
        # 用**当天累计**的不可达集合（`self.unreachable_day`）而不是本轮的 `all_steps`：
        # 真机 run5 的形态是"先有一轮试了 8 格全走不到（记进当天 blocked），其后每一轮
        # `_stage_tiles` 都把这 8 格剔掉 ⇒ 后续轮次的 `all_steps` 为空、leftover 仍是那 8 格"
        # —— 只看本轮的话，最后一条记录的 `unreachable_leftover` 会变成 0，豁免就失效了。
        unreach_steps = [s for s in all_steps if s.unreachable]
        unreach_tiles = sorted({tuple(s.tile) for s in unreach_steps if s.tile})
        unreach_in_left = min(len(leftover),
                              len([t for t in self.unreachable_day if t in left_set]))
        attempted_steps = sum(1 for s in all_steps if s.attempted)
        rep.stages.append({
            "stage": task, "tiles": 0 if not all_steps else len({s.tile for s in all_steps if s.tile}),
            "ok": len(oks), "skipped": len(skipped), "failed": len(failed),
            "failed_any": len(failed_any),
            "proven_inert": len(inert),
            "env_block": len(env_fail), "inconclusive": len(inconclusive),
            # 【task-52】账本字段名与 `tools\verify-run3.py` 的自算口径**逐字对齐**（Lead m04925）：
            # `stages[i].unreachable`（int）+ `stages[i].unreachable_tiles`（[[x,y],…]）。
            "unreachable": len(unreach_tiles),
            "unreachable_tiles": [list(t) for t in unreach_tiles],
            "unreachable_leftover": unreach_in_left,
            "attempted": attempted_steps,
            "stopped": stopped, "leftover": len(leftover),
        })
        if unreach_steps:
            self._journal("unreachable_stage", stage=task, zone=self.zone_name,
                          tiles=len(unreach_tiles), in_leftover=unreach_in_left,
                          coords=[list(t) for t in unreach_tiles[:12]],
                          note="走不到（没有落脚点/寻路到不了）⇒ 不算硬失败；"
                               "日级豁免有上界，逐格坐标见 unreachable 事件")
        # task-22：环境挡路 / 没拿到结论都要**单独留痕**（它们不进 `blocked`，也不该藏在 failed 里）。
        # 每阶段最多两条，带 statuses 与格数；事后看 journal 就能分清"这格真干不动"和"世界当时在忙"。
        if env_fail:
            self._journal("env_fail", stage=task, zone=self.zone_name,
                          tiles=len({tuple(s.tile) for s in env_fail if s.tile}),
                          statuses=sorted({x for s in env_fail for x in statuses_of(s)}),
                          note="环境挡路（渐黑/模态/没存档）⇒ 不算干不动：不封格、不占本日尝试配额")
        if inconclusive:
            self._journal("inconclusive_fail", stage=task, zone=self.zone_name,
                          tiles=len({tuple(s.tile) for s in inconclusive if s.tile}),
                          statuses=sorted({x for s in inconclusive for x in statuses_of(s)}),
                          note="连续请求没拿到结论（超时/stale）⇒ 不封格，但占本日尝试配额")
        if not all_steps and not met:
            self._journal("stage_no_target", stage=task, leftover=len(leftover), zone=self.zone_name)
        error = None
        if failed and not met:
            error = f"{len(failed)} 格没做成（例：{failed[0].tile} {failed[0].reason}）"
        if not met and not retryable:
            # 剩下的格子**一个都不值得再试**（要么已判定干不动、要么到本日尝试上限）⇒ 今天不再要它。
            # ⚠️ 这不是"成功"：`met` 仍是 False，阶段终态照旧由 `classify_outcome` 判 needs_review。
            # 记账的意义是**不再空转** —— 否则策略每轮重新要一次、每轮零目标，攒够 3 轮判 stuck、
            # 整天报废（真机 run1 的两格 grass 就是这么把一天耗掉的）。
            self._mark_no_target(task)
            self._journal("stage_exhausted", stage=task, leftover=len(leftover),
                          doomed=len(doomed), capped=len(capped),
                          tiles=[list(t) for t in leftover[:6]], zone=self.zone_name)
        reason_bits = [f"作业区 {self.zone_name or '窗口'}",
                       f"目标 {len(all_steps)} 步：做成 {len(oks)}、跳过 {len(skipped)}、失败 {len(failed)}"]
        if len(failed_any) > len(failed):
            reason_bits.append(
                f"另有 {len(failed_any) - len(failed)} 次环境挡路已重试做成（不计硬失败）")
        if inert:
            reason_bits.append(f"其中 {len(inert)} 格当场判据成立「干不动」已封到当天结束")
        if env_fail:
            reason_bits.append(
                f"其中 {len(env_fail)} 格被环境挡住（渐黑/模态/没存档/Mod 忙，不封格；"
                f"重试后仍没做成才留在剩余里）")
        if inconclusive:
            reason_bits.append(f"其中 {len(inconclusive)} 格没拿到结论（超时/stale，占配额但不封格）")
        if unreach_steps:
            reason_bits.append(
                f"其中 {len(unreach_tiles)} 格走不到（四邻都站不过去/寻路到不了，不算硬失败；"
                f"当天不再白试、次日重试）")
        if stopped:
            reason_bits.append(f"提前停：{stopped}")
        if met:
            reason_bits.append("后置条件成立")
        elif leftover:
            extra = ""
            if doomed:
                detail = "、".join(f"{t} {self.blocked.get(t, '')}".strip() for t in doomed[:3])
                extra = f"，其中 {len(doomed)} 格已判定干不动：{detail}"
            elif capped:
                extra = f"，其中 {len(capped)} 格已到本日尝试上限"
            reason_bits.append(f"后置条件未成立（还剩 {len(leftover)} 格{extra}）")
        else:
            # 一格目标都没有 ⇒ 绝不能写"未成立（还剩 0 格）"（读起来自相矛盾）
            reason_bits.append("后置条件未成立（这一阶段一格目标都没有）")
        return TaskOutcome(
            kind=task,
            postcondition_met=met,
            skipped=bool(skipped) and not oks and not failed and not met,
            progress=bool(oks) and not met,
            reason="；".join(reason_bits),
            error=error,
            evidence=tuple(
                f"{s.tile}: {s.reason}" for s in (failed or skipped)[:3]
            ),
        )

    def _verify_intents(self, intents: list[TaskIntent], obs: dict[str, Any],
                        plot: dict[str, Any]) -> tuple[list[TaskIntent], list[dict[str, Any]]]:
        """**对策略/大模型的决定做校验**（用户 m02591 要的那道关）。

        > 大模型做的决定，没有校验机制，应该有个校验，是继续做还是取消换别的任务，
        > 否则就会出现啥也没做就要睡觉了。

        每条意图在**动手之前**先过一遍，三态：

        * `keep`    —— 观测里看得见可动的格子 ⇒ 照做；
        * `unknown` —— 作业区离玩家太远（> `OBSERVE_REACH`）：观测**以玩家为中心**，看不见不等于
          没有 ⇒ 也算继续，交给 `_step_stage` 先走过去再看一眼（`plot_walk`）；
        * `cancel`  —— 就在眼前、却一格目标都拿不出来 ⇒ 取消这条意图，今天不再要它（`no_target`）。

        ⚠️ `cancel` **不等于"今天收工"**：它只说明**这一片地**对它没活了。全部被取消时
        `_run_day` 会去问 `sleep_guard` —— 守卫说还有活就换一片地接着干，绝不直接睡觉。
        """
        anchor = plot.get("anchor") or ()
        pt = FarmWorker.player_tile(obs)
        walk_dist = _dist((int(anchor[0]), int(anchor[1])), pt) if anchor else 0
        far = bool(anchor) and walk_dist > OBSERVE_REACH
        kept: list[TaskIntent] = []
        verdicts: list[dict[str, Any]] = []
        for intent in intents:
            task = str(getattr(intent, "task", ""))
            if task not in STAGE_ACTION:
                kept.append(intent)          # review / sleep 之类不按"有没有目标格"判
                continue
            tiles = [] if far else self._stage_tiles(task, obs, plot)
            if tiles:
                kept.append(intent)
                verdicts.append({"task": task, "verdict": "keep", "targets": len(tiles)})
            elif far:
                kept.append(intent)
                verdicts.append({"task": task, "verdict": "unknown",
                                 "reason": f"作业区离玩家 {walk_dist} 格，观测看不见，先走过去再看"})
            else:
                verdicts.append({"task": task, "verdict": "cancel",
                                 "reason": f"「{self.zone_name or '当前作业区'}」看得见却没有一格可动目标"})
        return kept, verdicts

    def _fallback_decision(self, brief: Brief, rep: DayReport) -> Any:
        """**换任务**（用户 m02591："是继续做还是取消换别的任务"）。

        策略层（大模型）给的意图被校验全部取消/过滤掉时，不等于"今天收工"，也不该原地空转：
        先用**简报上的确定性策略**重新挑一件当天真能做的事。确定性策略是纯代码、从当前观测算出来的，
        它只会要"计数大于 0"的事 —— 相当于"把模型的方向换成一件落得到地上的事"。
        """
        blocked = self.no_target | self.no_target_global
        intents = [i for i in deterministic_plan(brief) if i.task not in blocked]
        if intents:
            note = (f"策略意图全被取消 ⇒ 换任务（确定性策略）：{[i.task for i in intents]}"
                    f"；今天不再要 {sorted(blocked) or '无'}")
            rep.notes.append(note)
            self._say(f"  · 校验后改用确定性策略：{[i.task for i in intents]}")
            self._journal("policy_fallback", intents=[i.task for i in intents],
                          blocked=sorted(blocked))
        return SimpleNamespace(intents=intents)

    def _apply_policy(self, decision: Any, obs: dict[str, Any]) -> tuple[Any, str]:
        """在策略给出的意图上叠一层**代码政策**：当天不做就补不回来的活排最前。

        大模型（或确定性策略）给的是**方向**；这一层管的是**不可退让的硬约束**，两者是互补的：
        模型可以决定"今天往哪片地使劲"，但不能决定"今天不浇水"。

        同时把**今天已被证明一格目标都拿不出来**的任务剔掉（`self.no_target`）——策略与执行层
        一旦不同口径（例如策略说"还有草要清"而 `_stage_tiles` 一格都拿不出来），每轮空转一次，
        攒够 3 轮就判 stuck 报废整天。剔干净之后若一个意图都不剩，`_run_day` 会如实收工。
        """
        raw = list(decision.intents)
        notes: list[str] = []
        blocked = self.no_target | self.no_target_global
        kept = [i for i in raw if i.task not in blocked]
        dropped = sorted({i.task for i in raw if i.task in blocked})
        if dropped:
            notes.append(f"今天不再要已证明没目标的任务 {dropped}")
        intents, pnotes = self._policy_intents(kept, obs)
        notes.extend(pnotes)
        if [i.task for i in intents] == [i.task for i in raw] and not notes:
            return decision, ""
        return SimpleNamespace(intents=intents), "；".join(notes)

    def _policy_intents(self, intents: list[TaskIntent],
                        obs: dict[str, Any]) -> tuple[list[TaskIntent], list[str]]:
        tmap = FarmWorker.tiles_of(obs)
        unwatered = [t for t, v in tmap.items() if v.get("crop") and not v.get("watered")]
        ripe = [t for t, v in tmap.items() if v.get("crop") and v.get("ripe")]
        must: list[TaskIntent] = []
        notes: list[str] = []
        if unwatered:
            must.append(TaskIntent(
                "water_area", "",
                f"政策：{len(unwatered)} 格作物没浇水，当天不浇就补不回来", ()))
        if ripe:
            must.append(TaskIntent(
                "harvest", "", f"政策：{len(ripe)} 格作物熟了，先收掉腾地", ()))
        if not must:
            return list(intents), notes
        out = list(must)
        for it in intents:
            if any(it.task == m.task for m in must):
                continue
            out.append(it)
        before = [i.task for i in intents]
        after = [i.task for i in out]
        if before != after:
            notes.append(f"政策把 {[m.task for m in must]} 提到最前（原顺序 {before}）")
        return out, notes

    def _execute(self, decision: Any, obs: dict[str, Any], plot: dict[str, Any],
                 rep: DayReport) -> bool:
        acted = False
        assert self.worker is not None
        for intent in decision.intents:
            task = intent.task
            hint = str(intent.area_hint or "")
            # LLM 给了具名田区 ⇒ 下一片地就往那儿去（"方向由大模型给，坐标由代码落"）
            if fields_mod is not None and hint:
                try:
                    if fields_mod.resolve_zone(hint, self._zones(obs)) is not None:
                        self.pending_zone_hint = hint
                except Exception:
                    pass

            if task == "review":
                self._review(obs, rep)
                continue
            if task in ("sleep", "recover_stamina"):
                allow, code, text = self.sleep_guard(obs)
                if not allow:
                    rep.notes.append(f"否决 {task}：{text}")
                    self._journal("intent_vetoed", task=task, reason=text)
                    self._say(f"  · 否决 {task}：{text}")
                    continue
                rep.ended_by, rep.ended_reason = self._do_sleep(obs, rep, f"{code}:{text}")
                return True
            if task == "wait_for_save":
                st = self.worker.load_save()
                self._actions += 1
                rep.notes.append(f"读档：{st.reason}")
                self._journal("load_save", ok=st.ok, reason=st.reason)
                acted = acted or st.ok
                continue
            if task == "ship":
                acted = self._ship_loot(obs, rep) or acted
                obs = self._snap()
                continue
            if task in STAGE_ACTION:
                acted = self._run_stage_intent(intent, obs, plot, rep) or acted
                obs = self._snap()
                continue
            self._journal("intent_unknown", task=task)
            rep.notes.append(f"未知意图 {task}（跳过）")
        return acted

    def _ship_loot(self, obs: dict[str, Any], rep: DayReport) -> bool:
        """【task-42】把今天亲手收获的东西按白名单放进出货箱（`ship` 意图的执行体）。

        三条纪律，全部来自 `docs/_il-sell-path.md` 与用户 m08335：

        * **白名单空 ⇒ 一步不动**：`worker.sell_loot()` 自己会返回空列表，绝不"看到背包里有东西就卖"；
        * **绝不写 `Money +=`**：钱只由游戏下一次 `NewDay` 结算（`player.Money = player.Money + total`），
          所以这一步的判据是"背包那格真的空了 + 出货箱件数变了"，钱当天不变是**正常**的；
        * 每一件都 journal 一条 `sell`（`before`/`after` 全是观测真值），失败如实带 reason 回去。
        """
        assert self.worker is not None
        steps = self.worker.sell_loot(timeout_ms=self.sell_timeout_ms)
        if not steps:
            return False
        for st in steps:
            before = st.before if isinstance(st.before, dict) else {}
            self._journal("sell", ok=st.ok, code=st.code,
                          slot=before.get("slot"), qid=before.get("qid"),
                          stack=before.get("stack"), before=st.before, after=st.after,
                          reason=st.reason, receipt=st.receipt)
        self._actions += len(steps)
        good = [s for s in steps if s.ok]
        bad = [s for s in steps if not s.ok]
        if good:
            total = sum(int((s.before or {}).get("stack") or 0) for s in good)
            note = f"出货 {len(good)} 件（{total} 个）进箱；钱要等下一次 NewDay 才由游戏结算"
            rep.notes.append(note)
            self._say(f"  · {note}")
        if bad:
            rep.notes.append(f"出货失败：{bad[0].reason}")
            self._say(f"  × 出货失败：{bad[0].reason}")
            self._journal("sell_failed", reason=bad[0].reason, code=bad[0].code)
        return bool(good)

    def _review(self, obs: dict[str, Any], rep: DayReport) -> None:
        """任务后复盘（用户 m00707 要的"干完一段就让大模型看看对不对、接下来干什么"）。

        LLM 关着的时候，这一步是**代码的复盘**：把资源、地里剩余、今天做过什么摊开写清楚，
        既进 journal 也进人看的日志 —— 这样"为什么睡/为什么接着干"永远有账可查。
        """
        ess = self._essence(obs)
        reasons = self.work_reasons(obs)
        line = (f"  ~ 复盘：{rep.day_text} 体力 {ess['stamina']}/{FarmWorker.player_of(obs).get('maxStamina')}"
                f"、钱 {ess['money']}g、作物 {ess['crops']}（未浇 {ess['unwatered_crops']}）、"
                f"今天阶段 {rep.stages_seen or '无'}")
        self._say(line)
        rep.notes.append("复盘：" + (("还有活可做 —— " + "；".join(reasons)) if reasons else "确实没活了"))
        self._journal("review", stamina=ess["stamina"], money=ess["money"], crops=ess["crops"],
                      unwatered=ess["unwatered_crops"], stages=rep.stages_seen,
                      work_reasons=reasons)

    # ------------------------------------------------------------------ 体检
    def _supervise(self) -> str:
        if assess is None or self.client is None:
            return ""
        try:
            health = self.client.health()
            obs = self._snap()
        except BridgeError as exc:
            return f"桥不可达：{exc}"
        findings = assess(health, obs, mod_version_expected=MOD_VERSION_EXPECTED)
        if verdict(findings) == LEVEL_STOP:
            stop = [f for f in findings if f.level == LEVEL_STOP]
            note = "longrun 长跑体检不通过"
            try:
                if write_stop_report is not None:
                    write_stop_report(findings, health=health, observe=obs,
                                      directory=self.report_dir, note=note)
            except Exception:  # pragma: no cover
                pass
            self._journal("watchdog_stop", codes=[f.code for f in stop],
                          messages=[f.message for f in stop])
            return "watchdog：" + "；".join(f"{f.code} {f.message}" for f in stop)
        return ""

    # ------------------------------------------------------------------ 模态守卫（task-11）
    @staticmethod
    def _modal_info(obs: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        """从观测里读“当前挡路的模态”：返回 `(isModal, activeMenu, ui)`。"""
        ui = obs.get("ui") or {}
        return bool(ui.get("isModal")), str(ui.get("activeMenu") or ""), ui

    def _wait_modal_gone(self, menu: str, obs: dict[str, Any]) -> tuple[dict[str, Any], bool, float]:
        """**只等不关**：轮询 `ui.isModal`，直到这个模态自己消失（或超时 / 换成了别的模态）。

        返回 `(最新 obs, 是否已经消失, 等了多久秒)`。`gone=False` 只表示“等超时了”，
        调用方必须据此停下等人 —— 超时的存档模态**绝不能**靠 dismiss 收场。
        """
        start = self.now()
        limit = max(0.0, float(self.modal_wait_timeout_s))
        self._journal("modal_wait_start", menu=menu, limit_s=limit,
                      note="只等不关（新一天自动存档；dismiss 可能打断存档）")
        while True:
            self.sleep_fn(1.0)
            try:
                obs = self._snap()
            except BridgeError as exc:
                self._journal("modal_wait_error", menu=menu, reason=str(exc))
                return obs, False, self.now() - start
            is_modal, now_menu, _ui = self._modal_info(obs)
            waited = self.now() - start
            if not is_modal:
                self._journal("modal_gone", menu=menu, waited_s=round(waited, 1))
                return obs, True, waited
            if now_menu and now_menu != menu:
                # 模态换人了（例：存档刚走完、紧接着弹出升级菜单）⇒ 交给外层重新分派，不算超时
                self._journal("modal_switched", was=menu, now=now_menu, waited_s=round(waited, 1))
                return obs, True, waited
            if waited >= limit:
                self._journal("modal_timeout", menu=menu, waited_s=round(waited, 1), limit_s=limit,
                              note="只等不关的模态超时（没敢 dismiss）⇒ 当天如实停下等人")
                return obs, False, waited

    def _dismiss_modal_once(self, menu: str, ui: dict[str, Any], *, kind: str) -> dict[str, Any]:
        """关一次模态并重新观测（回执原文进 journal；世界是否真变了解除由后续观测回答）。"""
        assert self.client is not None
        menu_text = str(ui.get("activeMenuText") or "")
        receipt = self.client.dismiss_modal()
        self._actions += 1
        self._journal("modal_dismissed", kind=kind, menu=menu, menuText=menu_text,
                      receipt=receipt,
                      note=("提问走 dismiss_modal 的选否口径（项目硬规则：永不注入确认键）"
                            if kind == "question" else None))
        self._say(f"  · 关掉挡路模态 {menu or '?'}（{kind}）"
                  f"{'：' + menu_text if menu_text and menu_text != menu else ''}")
        return self._snap()

    def _clear_modals(self, obs: dict[str, Any], rep: DayReport) -> tuple[dict[str, Any], bool]:
        """日循环每一步之前的**模态守卫**：把挡路的模态按三种处置清掉（task-11）。

        返回 `(最新 obs, 是否必须停下来等人)`；第二种情况同时把 `rep.ended_by` 置成
        `"blocked_modal"`（⇒ `slept_by_us=false` ⇒ 当天**不判 VERIFIED**）。

        三种处置（判据只看观测，不看回执）：
          * **游戏事件（硬停，task-41）**：`ui.eventUp == true` ⇒ **一次都不动手**。关框会替游戏
            推进剧情（实测：`closeDialogue()` 让事件把第一句算作"说完了"）、事件里的 `Yes/No`
            还会被默认选"否"，两条都不可逆 ⇒ `ended_by="blocked_event"`、停下等人（详见
            `_event_blocked`）。
          * **wait-only**：`SaveGameMenu`/`NewDaySavingMenu` —— 新一天的自动存档，**绝不 dismiss**
            （可能打断存档），轮询到它自己消失；超时记 `modal_timeout` 并停下等人。
          * **dismiss**：普通 `LevelUpMenu`（`professionsToChoose` 为空数组=这一级没有职业可选）、
            `GameMenu`、`DialogueBox`/提问、以及未知模态 ⇒ `dismiss_modal()`（Mod 侧对提问一律
            走“选否”），journal 记 `modal_dismissed`（menu 名 + 回执）。
          * **职业选择（不可逆，绝不动手）**：`LevelUpMenu` 且 `professionsToChoose` **非空**，
            或该字段**缺失**（旧 Mod / 反射失败 = 未知）⇒ 只记录 + 停下等人。
            依据 `docs\\_il-profession.md`：`exitThisMenu()` → `cleanupBeforeExit()` →
            `RemoveLevelFromLevelList()` ⇒ 永久丢掉那次 Tiller/Artisan 选择（用户已拍板职业路线）。

        【为什么每步之前都要查】`LevelUpMenu`/存档模态会让 `player.freezePause=100`、时钟不走，
        整个长跑会静默卡死（用户真机看到过）；而且升级弹窗会**连出**多个，所以要循环到干净为止。
        """
        rounds = 0
        while rounds < self.modal_max_dismiss:
            is_modal, menu, ui = self._modal_info(obs)
            if not is_modal:
                return obs, False

            # ⓪ **游戏事件**（`ui.eventUp == true`）：一律硬停，绝不代游戏做决定（task-41）。
            # 放在最前面：事件往往就是个 `DialogueBox`，先判提问/普通对话框就会把它关掉。
            if ui.get("eventUp") is True:
                return self._event_blocked(obs, rep)

            # ① 提问（DialogueBox 开着提问时 isModal 为真）：走 Mod 的“选否”口径，绝不注入确认键
            if ui.get("dialogueIsQuestion") or ui.get("dialogueResponses"):
                try:
                    obs = self._dismiss_modal_once(menu, ui, kind="question")
                except BridgeError as exc:
                    return self._modal_blocked(obs, rep, f"关不掉提问模态 {menu}：{exc}")
                rounds += 1
                continue

            # ② 等待型（新一天的自动存档）：只等不关
            if menu in MODAL_WAIT_ONLY:
                obs, gone, waited = self._wait_modal_gone(menu, obs)
                if gone:
                    rounds += 1
                    continue
                rep.notes.append(f"{menu} 等了 {waited:.0f}s 仍不消失（存档/跨日模态，不敢关）")
                return self._modal_blocked(
                    obs, rep, f"{menu}：等了 {waited:.0f}s 仍不消失（可能存档没落盘）")

            if menu == "LevelUpMenu":
                ids = ui.get("professionsToChoose", None)
                if ids is None:
                    # 旧 Mod 或反射失败 ⇒ 按“未知”处理：不拿不确定性去赌不可逆操作
                    self._journal("levelup_profession_unknown", menu=menu, menuText=ui.get("activeMenuText"),
                                  note="观测里没有 professionsToChoose（旧 Mod / 反射失败）⇒ 未知："
                                       "绝不 dismiss（关掉会永久丢职业选择）")
                    rep.notes.append("LevelUpMenu 读不到 professionsToChoose ⇒ 按未知处理，不 dismiss，停下等人")
                    return self._modal_blocked(obs, rep, "LevelUpMenu：读不到职业候选（字段缺失，未知）")
                if len(ids) > 0:
                    self._journal("levelup_profession_pending", menu=menu, ids=list(ids),
                                  menuText=ui.get("activeMenuText"),
                                  note="职业选择弹窗（不可逆）：dismiss = 永久丢档 ⇒ 只记录、停下等人来选")
                    rep.notes.append(f"职业选择弹窗挡路（候选 {list(ids)}）⇒ 停下等人来选，不静默丢档")
                    return self._modal_blocked(obs, rep, f"职业选择弹窗（候选 {list(ids)}）等人处理")
                kind = "levelup"          # 空数组 = 普通升级弹窗，可以关
            else:
                kind = "menu"             # GameMenu / 未知模态

            try:
                obs = self._dismiss_modal_once(menu, ui, kind=kind)
            except BridgeError as exc:
                return self._modal_blocked(obs, rep, f"关不掉模态 {menu}：{exc}")
            rounds += 1

        # 循环到上限还有模态：不硬关，如实停下等人（连出十几个模态本身就不正常）
        is_modal, menu, _ui = self._modal_info(obs)
        if is_modal:
            self._journal("modal_loop_capped", menu=menu, rounds=rounds,
                          note=f"连关 {rounds} 个模态后还有模态 ⇒ 停下等人")
            return self._modal_blocked(obs, rep, f"连关 {rounds} 个模态后仍被 {menu} 挡着")
        return obs, False

    def _modal_blocked(self, obs: dict[str, Any], rep: DayReport, reason: str
                       ) -> tuple[dict[str, Any], bool]:
        """把“必须人来处理”的模态写成当天的收尾：`blocked_modal` + 不判 VERIFIED。"""
        rep.ended_by = ENDED_BY_MODAL
        rep.ended_reason = reason
        rep.notes.append(f"被模态挡住，停下等人：{reason}")
        self._journal("modal_blocked", menu=(obs.get("ui") or {}).get("activeMenu"),
                      reason=reason, note="不可逆/不敢关的模态 ⇒ 当天不判 VERIFIED，等人工处理")
        self._say(f"× 被模态挡住，停下等人：{reason}")
        return obs, True

    def _event_blocked(self, obs: dict[str, Any], rep: DayReport) -> tuple[dict[str, Any], bool]:
        """游戏事件挂住（`ui.eventUp=true`）：**绝不代游戏做决定** ⇒ 当天停下等人（task-41）。

        为什么连“关一下框”都不许（真机，2026-10-13 19:19，run4 起跑前）：
          * 事件的第一句被 `closeDialogue()` 关掉后，游戏把它算作“这句说完了”而**推进**剧情
            （`"Hello Jay!"` → 流浪宠物台词）—— 关框＝替游戏做决定，且不可逆；
          * 事件里出现 `Yes/No` 时，`ModalDismiss` 的选否口径会替玩家**默认选“否”**（事件分支被悄悄改掉）；
          * 账本对此一无所知 ⇒ 无人值守的验收可能悄悄改存档剧情状态。

        所以这里的收尾与“职业选择”同款：`ended_by="blocked_event"` ⇒ `checks.no_blocking_modal=False`
        ⇒ 当天 `verified=False`，并由 `run()` 早退等人处理。**不 dismiss / 不 sleep / 不 load_save。**
        """
        ui = obs.get("ui") or {}
        menu = str(ui.get("activeMenu") or "")
        text = str(ui.get("activeMenuText") or "")
        tile = FarmWorker.player_tile(obs)
        self._journal("event_blocked",
                      activeMenu=ui.get("activeMenu"), activeMenuText=ui.get("activeMenuText"),
                      dialogueIsQuestion=ui.get("dialogueIsQuestion"),
                      dialogueResponses=list(ui.get("dialogueResponses") or []),
                      tile=list(tile) if tile else None,
                      timeOfDay=FarmWorker.time_of_day(obs),
                      worldSeq=obs.get("worldSeq"),
                      note="游戏事件挂住（ui.eventUp=true）：关框会替游戏推进剧情/默认选否 ⇒ "
                           "不 dismiss / 不 sleep / 不 load_save，当天不判 VERIFIED，等人处理")
        rep.ended_by = ENDED_BY_EVENT
        rep.ended_reason = (f"游戏事件挂住（eventUp=true）：{menu or '?'}"
                            + (f"「{text}」" if text else ""))
        rep.notes.append("游戏事件挂住（eventUp），按政策停下等人：不 dismiss / 不 sleep / 不 load_save")
        self._say(f"× 游戏事件挂住（eventUp）⇒ 停下等人：{menu or '?'}"
                  + (f"「{text}」" if text else ""))
        return obs, True

    # ------------------------------------------------------------------ 一天
    def _run_day(self) -> DayReport:
        obs = self._snap()
        rep = DayReport(day_key=FarmWorker.day_key(obs), started_at=self.now() - self.started)
        self.days.append(rep)
        self.plot = None
        self.zone_name = ""
        self.plots_today = 0
        self.plots_capped_noted = False
        self.farm_evidence_noted = False
        self.refills_today = 0
        self.idle_rounds = 0
        self.blocked = {}
        self.tile_attempts = {}
        self.env_streak = {}
        self.env_spin_noted = set()
        self.seed_gate_noted = set()
        self.dead_scope_noted = set()
        self.no_target = set()
        self.no_target_global = set()
        # 【task-49】跨片地的"今天还没做完"记账 + 回头看的次数上限，每天清零。
        self.leftover_targets = set()
        self.unreachable_day = set()
        self.resume_walks = 0
        # 【task-50】窗口外干作物的重试记账，每天清零（第二天壶/世界都变了，重新判）。
        self.far_dry_tries = {}
        self.far_dry_given_up = set()
        self.far_dry_unavailable_noted = False
        # 【task-42】新的一天 ⇒ 清空出货白名单：昨天收获的东西昨天该出就出了，
        # 今天再拿白名单去卖会变成"卖一件不存在的东西"（`sellable_slots` 找不到就不动，但语义要干净）。
        if self.worker is not None:
            try:
                self.worker.reset_harvested()
            except Exception:
                pass
        recovered = 0            # 今天"换了一片地"的次数（本片拿不出目标时）
        # **一天的第一次决策必须是"跨日边界"**（用户 m01860：该由大模型先判断今天做什么）。
        # `detect_boundary` 判 new_day 的依据是"state 里的 day_key 与当前简报不同"，而且**两边都得
        # 非空**才比 —— 所以这里不能置 None，要放一个与真实日期必然不等的哨兵值。
        # 这一天之后的决策都不再是边界（0 次调用），除非失败计数上升或阶段切换。
        self.state.day_key = _DAY_START_SENTINEL
        ess = self._essence(obs)
        self._say(f"[day] {rep.day_text} 开始：{ess['location']} 体力 {ess['stamina']} 钱 {ess['money']}g "
                  f"作物 {ess['crops']}（未浇 {ess['unwatered_crops']}）天气 {FarmWorker.weather(obs)}")
        self._journal("day_start", day=list(rep.day_key), timeOfDay=ess["timeOfDay"],
                      stamina=ess["stamina"], money=ess["money"], crops=ess["crops"],
                      unwatered=ess["unwatered_crops"], location=ess["location"],
                      weather=FarmWorker.weather(obs))

        # 【run3 真 bug：醒在屋里就再也不去农场】`_prepare()` 只在 `run()` 启动时回农场一次，
        # 之后每个游戏日都在 FarmHouse 醒来（run3：`final.location='FarmHouse'`、`tile=[9,9]`、
        # `isInBed=true`、`timeOfDay=600`），整天拿**室内窗口**当观测 ⇒ `work_reasons`/
        # `_ensure_plot` 全判"没活" ⇒ 连睡 4 天，`final_water` farm 口径还是 `dry=33/33`。
        # 所以每天第一张观测之后、进主循环之前必须先回农场；失败**不吞**（notes + journal）。
        obs = self._ensure_on_farm(obs, rep)

        last_obs = obs
        # task-19：当天**最后一个户外农场快照**（窗口口径浇水证据的来源）。日终再问必然是室内的
        # （`isOutdoorFarm=false`、窗口 crops 恒 0）⇒ 必须边走边记，否则「睡前有没有没浇的作物」
        # 这件事永远白过。
        outdoor_obs = obs if self._is_farm(obs) else None
        outdoor_t = 0.0
        outdoor_name = (str((obs.get("location") or {}).get("name") or "")
                        if outdoor_obs is not None else None)
        while True:
            if self._budget_exhausted():
                rep.ended_by, rep.ended_reason = "budget", (
                    f"到预算上限（{self._elapsed_minutes():.1f} 分钟 / {self._actions} 个动作）")
                break
            try:
                obs = self._snap()
                last_obs = obs
            except BridgeError as exc:
                rep.ended_by, rep.ended_reason = "bridge_down", str(exc)
                break
            if FarmWorker.day_key(obs) != rep.day_key:
                rep.ended_by, rep.ended_reason = "pass_out", "日期自己变了（游戏自动跨日或外部读档）"
                break

            # task-19：边走边记"最后一张户外快照"（窗口口径浇水证据的取样点）。
            if self._is_farm(obs):
                outdoor_obs = obs
                outdoor_t = self.now() - self.started
                outdoor_name = str((obs.get("location") or {}).get("name") or "")

            # **模态守卫**（task-11）：`LevelUpMenu`/存档模态会把时间冻住（`player.freezePause=100`），
            # 不先清掉的话后面所有技能都会被 `ui_modal` 拒绝、整天静默卡死。清到干净才谈决策。
            obs, modal_blocked = self._clear_modals(obs, rep)
            if modal_blocked:
                break

            allow, code, text = self.sleep_guard(obs)
            if allow:
                rep.ended_by, rep.ended_reason = self._do_sleep(obs, rep, f"{code}:{text}")
                break

            self._preconditions(obs, rep)
            # 【task-50】窗口外那 1 格干作物（run5 三天 `farm.dryCrops` 恒剩 1 的病灶）：
            # Mod 的 `farm.dryTiles` 给了坐标 ⇒ **走过去浇**，别因为它不在窗口里就判 `no_work`。
            # 每格每天最多 `FAR_DRY_MAX_TRIES` 次；两次都不成会进"认输"集合，之后
            # `_far_dry_tiles` 变空 ⇒ 守卫仍因 `farm.dryCrops>0` 不放行 ⇒ 当天以
            # `stuck:` 收尾并点名坐标（绝不洗成 `no_work`）。
            if self._water_far_dry(obs, rep):
                continue
            plot = self._ensure_plot(obs, rep)
            if plot is None:
                # 【task-32】没有田区拿得出目标，但**守卫刚刚说还有活**（否则 line 上方的
                # `sleep_guard` 早就放行了）⇒ 不许用 `no_plot` 收工（它已不在
                # `day_justified` 白名单里）。把"活所在的格子"（待浇/待收的作物）当收尾
                # 作业区，让策略/执行层把当天该干的干完；真一格都拿不出来时按 `stuck`
                # 如实收尾（**不洗成** `no_work`），且这条路径只有一次、不空转。
                # 【task-49】再补一道 `_resume_plot`：今天早些时候见过、还没做完的格子
                # （可能整片都在玩家窗口之外，例如 run5 的 field_nw）。
                work_spot = self._work_spot_plot(obs)
                picked = work_spot if work_spot is not None else self._resume_plot(obs)
                spot = picked or self._near_player_plot(obs)
                if spot is None:
                    reasons = self.work_reasons(obs)
                    rep.notes.append("找不到有活的作业区："
                                     + ("；".join(reasons) or "（守卫也说没活）"))
                    why = ("no_work" if not reasons else
                           "stuck:守卫说还有活（" + "；".join(reasons)
                           + "）但没有任何作业区拿得出目标")
                    rep.ended_by, rep.ended_reason = self._do_sleep(obs, rep, why)
                    break
                plot = spot
                self._journal("work_spot", zone=self.zone_name, tiles=len(plot["tiles"]),
                              note=plot.get("note"))
                # 【task-49】`_resume_plot` 给的是**别处**的格子（玩家窗口看不到）⇒ 先走回去，
                # 让传感器重新看见它们再谈策略。上界 `resume_walks < max_plots_per_day`
                # （与"换片地"同一个量级）；走不动就落回正常判定，不空转。
                if work_spot is None and picked is plot and self.resume_walks < self.max_plots_per_day:
                    self.resume_walks += 1
                    walked = self._walk_into_plot(obs, plot)
                    self._journal("resume_walk", zone=self.zone_name, tiles=len(plot["tiles"]),
                                  walked=bool(walked), attempt=self.resume_walks,
                                  note="回到今天还没做完的格子旁边（玩家窗口看不见它们）")
                    if walked:
                        self._actions += 1
                        rep.notes.append(
                            f"回到没做完的 {len(plot['tiles'])} 格旁边再看一次"
                            f"（resume_walk {self.resume_walks}/{self.max_plots_per_day}）")
                        continue

            brief = self._plot_brief(obs, plot)
            decision = self.planner.decide(self.state, brief)
            self._journal("decision", day=list(rep.day_key), boundary=decision.boundary,
                          source=decision.source, llm=decision.llm_called,
                          intents=[i.as_dict() for i in decision.intents],
                          problems=list(decision.problems), fallback=decision.fallback_reason,
                          # 单独一个布尔位：截断是**配置问题**（该调大 token 预算），
                          # 和网络/校验失败混在一个字符串里事后分不清（task-9）。
                          truncated=bool(getattr(decision, "truncated", False)),
                          # 【task-56】决策留痕：真实 LLM 调用的 trace 文件 + 该决策最后一行
                          # 的 sha256 前 12 位（确定性决策是空串；既有字段语义一字未动）。
                          llm_trace=getattr(decision, "llm_trace", "") or "",
                          llm_trace_hash=getattr(decision, "llm_trace_hash", "") or "",
                          zone=self.zone_name)
            # 【task-56】留痕写盘失败**不影响决策**，但要留下账：否则"用户以为有留痕、其实没有"。
            trace_error = getattr(decision, "llm_trace_error", "") or ""
            if trace_error:
                self._journal("llm_trace_failed", reason=trace_error,
                              path=getattr(decision, "llm_trace", "") or str(self.llm_trace_path or ""),
                              boundary=decision.boundary, zone=self.zone_name)
            decision, policy_note = self._apply_policy(decision, obs)
            if policy_note:
                self._journal("policy", note=policy_note,
                              intents=[i.task for i in decision.intents])
            # **校验关口**（用户 m02591）：能继续就继续，做不了就取消，全取消才谈收工
            kept, verdicts = self._verify_intents(decision.intents, obs, plot)
            if verdicts:
                self._journal("intent_verdict", zone=self.zone_name, verdicts=verdicts)
            canceled = [v for v in verdicts if v["verdict"] == "cancel"]
            if canceled:
                for v in canceled:
                    self._mark_no_target(str(v["task"]))
                rep.notes.append("校验取消：" + "、".join(
                    f"{v['task']}（{v.get('reason', '')}）" for v in canceled))
                self._say("  · 校验取消 " + "、".join(f"{v['task']}" for v in canceled)
                          + "：本片看得见却没有可动目标")
            if len(kept) != len(decision.intents):
                decision = SimpleNamespace(intents=kept)
            if not decision.intents:
                # ①**换任务**（用户 m02591 的"取消换别的任务"）：模型要的事一件都落不到地上时，
                #   用简报上的确定性策略重新挑一件当天真能做的事，而不是原地空转或掉头睡觉。
                decision = self._fallback_decision(brief, rep)
            if not decision.intents:
                # ②确定性策略也挑不出事来。⚠️ 这**不等于"今天没活了"**（用户 m02532 当场抓到：
                #   体力 204/270、才 19:40，却掉头回家准备睡觉）。能不能收工只有 `sleep_guard`
                #   说了算：守卫不放行就说明别处还有活 ⇒ 忘掉本片的记账、换一片地接着干。
                allow, code, text = self.sleep_guard(obs)
                if not allow:
                    # 【task-49 主修】守卫说还有活，而**本片**拿不出意图 ⇒ 先用"今天还没做完的
                    #   格子"（可能整片都在玩家窗口之外）回头看一眼，而不是直接换片地/攒 recovered。
                    #   run5 第 1 天：field_nw 还剩 9 格未开垦，人站在 field_se 就以为"没活"。
                    if self._pending_work() and self.resume_walks < self.max_plots_per_day:
                        resume = self._resume_plot(obs)
                        if resume is not None:
                            self.resume_walks += 1
                            walked = self._walk_into_plot(obs, resume)
                            self._journal("resume_walk", zone=self.zone_name,
                                          tiles=len(resume["tiles"]), walked=bool(walked),
                                          attempt=self.resume_walks,
                                          note="守卫说还有活但本片没意图 ⇒ 回去看今天没做完的格子")
                            if walked:
                                self._actions += 1
                                rep.notes.append(
                                    f"守卫说还有活（{text}）⇒ 回到没做完的 "
                                    f"{len(resume['tiles'])} 格旁边再看一次"
                                    f"（resume_walk {self.resume_walks}/{self.max_plots_per_day}）")
                                self.plot = resume
                                self.zone_name = ""
                                self.idle_rounds = 0
                                continue
                    recovered += 1
                    self._journal("plot_exhausted", recovered=recovered, zone=self.zone_name,
                                  note=f"这一片没目标了，但守卫仍要求干活（{text}）⇒ 换一片地")
                    if recovered > self.max_plots_per_day:
                        rep.notes.append(f"换过 {recovered} 片地都拿不出目标")
                        # ⚠️ 守卫**说还有活**却找不到任何目标 ⇒ 这是 `stuck`，不是"今天没活"：
                        #    写成 `no_work` 会白拿 `day_justified=true` 并把病灶洗白（task-49）。
                        rep.ended_by, rep.ended_reason = self._do_sleep(
                            obs, rep, f"stuck:换过 {recovered} 片地都没有目标（守卫仍说还有活：{text}）")
                        break
                    rep.notes.append(f"「{self.zone_name or '当前作业区'}」没目标了，但{text} ⇒ 换一片地继续")
                    self.no_target.clear()     # "本片没目标"是**片区级**记账，换片就得清
                    self.plot = None
                    self.zone_name = ""
                    self.idle_rounds = 0
                    continue
                note = f"今天确实没有可做的目标（{policy_note or '策略没给出意图'}；守卫放行：{code}）"
                rep.notes.append(note)
                self._journal("no_intents", zone=self.zone_name, note=note)
                rep.ended_by, rep.ended_reason = self._do_sleep(obs, rep, "no_work")
                break
            acted = self._execute(decision, obs, plot, rep)
            if rep.ended_by:
                break
            after = self._snap()
            changed = self._fingerprint(after) != self._fingerprint(obs)
            obs = after
            if acted and changed:
                self.idle_rounds = 0
            elif changed:
                # 意图没落地（比如被否决），但世界确实变了 —— 也算有进展
                self.idle_rounds = 0
            else:
                self.idle_rounds += 1
                self._journal("idle", rounds=self.idle_rounds, zone=self.zone_name,
                              intents=[i.task for i in decision.intents], acted=acted)
                if self.idle_rounds >= 3:
                    # 【task-50】文案里补上"守卫为什么还说要干活"的**活证据**（含窗口外
                    # 干作物的坐标）。决策逻辑一个字没动，只是让 `ended_reason` 能点名到底
                    # 卡在哪一格 —— 卡面硬要求"干格不可达 ⇒ 当天 `stuck:` 且含坐标"。
                    still = self.work_reasons(obs)
                    why = ("；守卫仍说还有活：" + "；".join(still)) if still else ""
                    rep.ended_by, rep.ended_reason = "stuck", (
                        f"stuck:连续 {self.idle_rounds} 轮世界没有任何变化（最后意图："
                        f"{[i.task for i in decision.intents]}；策略说有进展：{acted}）{why}")
                    break
                self.sleep_fn(0.5)
            if self.supervise_every and self._actions and self._actions % self.supervise_every == 0:
                stop = self._supervise()
                if stop:
                    rep.ended_by, rep.ended_reason = "stop", stop
                    self.aborted = True
                    break

        if not rep.final:
            rep.final = self._essence(last_obs)
        # task-15 §②：阶段后置条件纳入日级验收 —— **只统计"有目标的阶段"**（`tiles > 0` 的 stage 条目）。
        # 理由：`OBSERVE_REACH`（以玩家为中心、400 格上限）会让远处作业区先来一轮"0 目标"的阶段；
        # 那种 leftover 是"这一阶段没该动的格子"，不是"该做的没做完"（`_leftover` 现在也按
        # `_stage_tiles` 的同一道种子闸门口径把它记成 0），绝不能把 run3 开局判死。
        # ⚠️ `stage_exhausted` 的 `leftover>0` 是**设计语义**（task-9 条款①：封格不免成功），
        # 那些阶段有目标（`tiles>0`）⇒ 会被这条判死，正是要的效果。
        # ⚠️ 口径（task-15 实测修正）：**按阶段种类取当天最后一次记录**再求和，而不是把所有
        # 有目标阶段的 leftover 直接相加。实测（`scratch\probe_task15.py`，默认世界一天）：
        # `plant_area` 会因为"钱只够买一批种子"先停一次（`stopped='no_seed'`、leftover 5/1），
        # 随后买到种子又把同一批格子做完了 —— 直接相加会把"当天确实做完、世界完全达标"的
        # 一天判成 needs_review（既有用例 `test_single_day_verified_and_world_changed` 因此
        # 多跑一天）。阶段后置条件是**日级**的：同一阶段种类当天跑多轮时，以最后一轮为准。
        # 已知局限（记录在案）：同一天同一阶段种类跨多片地时，前一片地未解决、后一片地干净
        # 会互相遮蔽 —— 遮蔽现在**留痕**（下面的 `stage_midway_leftover`），交给复核。
        # **权威定义**（Lead m02561 裁定 1；`tools\verify-run3.py` 的自算口径已对齐成同一句）：
        #   「当天**每个阶段种类的最后一条记录**里 leftover 之和为 0」
        last_by_stage: dict[str, dict] = {}
        for s in rep.stages:
            last_by_stage[str(s.get("stage") or "")] = s
        # 【task-52】不可达豁免（Lead m04621/m04925 钉死口径）：
        #   * 上界 = `max(5, floor(0.2 × 当天 attempted 步数))`；`unreachable` 计数在这个界内
        #     才不影响 `verified`，超了照实 needs_review（`unreachable_within_bound` 判据）；
        #   * **同一豁免也要作用到 `no_unmet_stages`**：把已判"走不到"、且还留在 leftover 里的
        #     格子从日级剩余里扣掉（否则 run5 那种"最后一个阶段轮次刚好以不可达格子收尾"会把
        #     高产的一天判死）。扣的是**逐格坐标可查**的：每个不可达格都有 `unreachable` journal
        #     （`_mark_blocked`）+ 阶段级 `unreachable_stage`/账本 `unreachable_tiles`。
        #   * 防洗白：**全部目标不可达且当天 0 成功动作** ⇒ `no_unmet_stages` 仍为 False
        #     （下面的 `made_any_progress` 合取项），不许靠豁免把真空日洗成达标。
        attempted_steps = sum(int(s.get("attempted") or 0) for s in rep.stages)
        unreachable_bound = max(5, int(0.2 * attempted_steps))
        unreach_day: set[tuple[int, int]] = set(self.unreachable_day)
        for s in rep.stages:
            for t in (s.get("unreachable_tiles") or []):
                try:
                    unreach_day.add((int(t[0]), int(t[1])))
                except (TypeError, ValueError, IndexError):
                    continue
        rep.unreachable = len(unreach_day)
        rep.unreachable_tiles = [list(t) for t in sorted(unreach_day)]
        rep.unreachable_bound = unreachable_bound
        raw_unmet = sum(int(s.get("leftover") or 0) for s in last_by_stage.values()
                        if int(s.get("tiles") or 0) > 0)
        unreach_in_last = sum(int(s.get("unreachable_leftover") or 0) for s in last_by_stage.values()
                              if int(s.get("tiles") or 0) > 0)
        unreachable_exempt = min(unreachable_bound, unreach_in_last)
        rep.unreachable_exempt = unreachable_exempt
        unmet_leftover = max(0, raw_unmet - unreachable_exempt)
        made_any_progress = rep.ok_steps > 0
        if unreach_day:
            self._journal("unreachable_summary", count=len(unreach_day), bound=unreachable_bound,
                          attempted=attempted_steps, exempted=unreachable_exempt,
                          raw_unmet=raw_unmet, unmet=unmet_leftover,
                          tiles=[list(t) for t in sorted(unreach_day)[:12]],
                          note="不可达豁免：界内不影响 verified；扣掉的格子在 leftover 里逐格可见")
        # 遮蔽可见性（Lead m02561 裁定 1）：同一阶段种类当天**更早**记录 leftover>0、**最后一条**
        # leftover==0 ⇒ "前一片地没做完、后一片地干净"的遮蔽发生了。**纯信息项**：不改 VERIFIED、
        # 不改退出码，只发 journal + 进 notes，让 run3 事后能人工复核。
        midway: dict[str, dict] = {}
        for i, s in enumerate(rep.stages):
            name = str(s.get("stage") or "")
            if int(s.get("tiles") or 0) <= 0 or int(s.get("leftover") or 0) <= 0:
                continue
            midway[name] = {"stage": name, "tiles": int(s.get("tiles") or 0),
                            "leftover": int(s.get("leftover") or 0), "round": i + 1}
        for name, mid in midway.items():
            last = last_by_stage.get(name)
            if last is None or int(last.get("leftover") or 0) != 0:
                continue
            self._journal("stage_midway_leftover", **mid,
                          note=("同一阶段种类当天更早一轮还剩格子、最后一轮 leftover==0 ⇒ 日级判定取"
                                "最后一轮；若那批格子属于另一片地则存在遮蔽，请人工复核 `stage_exhausted`"))
            rep.notes.append(
                f"阶段 {name} 中途剩 {mid['leftover']}/{mid['tiles']} 格、当天最后一轮已归零"
                f"（stage_midway_leftover，当天第 {mid['round']} 条阶段记录）")
        # task-19：日级浇水证据。**唯一证据**是 `checks.watered_outdoor`（farm.dryCrops 或当天最后一个
        # 户外快照逐格 watered）；窗口口径的 `crops_watered` 保留但只作旁证（室内恒 0，会白过）。
        watered_outdoor, water_info = self._water_evidence(
            last_obs, outdoor_obs=outdoor_obs, outdoor_t=outdoor_t, outdoor_name=outdoor_name)
        rep.final_water = water_info
        if not watered_outdoor:
            rep.notes.append(
                "浇水证据不足/未浇完：" + str(water_info.get("note") or "")
                + f"（scope={water_info.get('scope')}、tiles={water_info.get('tiles')}、"
                  f"crops={water_info.get('crops')}、dry={water_info.get('dry')}）")
        rep.checks = {
            "slept_by_us": rep.ended_by == "sleep",
            # task-11：被不可逆/不敢关的模态挡住（职业选择、存档超时）时，这一天**不算数**。
            # 用户 m03224 拍板了职业路线：宁可停下等人，也不静默丢档。
            "no_blocking_modal": rep.ended_by not in BLOCKING_ENDS,
            "no_hard_failures": rep.failed_steps == 0,
            # 【task-52】"走不到"本身不算硬失败，但**有上界**：超过 `max(5, 20%×attempted)`
            # 就不是"个别格子客观走不到"，而是"今天大片目标够不着" ⇒ 照实 needs_review。
            "unreachable_within_bound": rep.unreachable <= unreachable_bound,
            # task-52 防洗白：豁免只对"走不到"的格子生效，且**全部不可达 + 0 成功动作**时
            # 不许靠豁免把 `no_unmet_stages` 洗成 True（真空日必须仍判不达标）。
            "no_unmet_stages": unmet_leftover == 0 and (made_any_progress or unreachable_exempt == 0),
            "crops_watered": int(rep.final.get("unwatered_crops") or 0) == 0,
            # task-19：**唯一**浇水证据（卡面 §1；`tools\verify-run3.py` 缺这条即问题）。
            # 窗口口径的 `crops_watered` 只作旁证：它读的是 `_essence` 的窗口计数，在室内恒 0。
            "watered_outdoor": bool(watered_outdoor),
            # 【task-32】白名单里**没有** `no_plot`：作业区配额到顶是我们自己设的软上限，
            # 被它憋停不等于"没活可做"，不许据此判 VERIFIED（判据见 `is_justified_end`）。
            "day_justified": is_justified_end(rep.ended_by, rep.ended_reason),
        }
        rep.verified = all(rep.checks.values())
        self._say(
            f"[day] {rep.day_text} 结束：{rep.ended_by}"
            + (f"（{rep.ended_reason}）" if rep.ended_reason else "")
            + f" 阶段 {rep.stages_seen or '无'} 做成 {rep.ok_steps} 跳过 {rep.skipped_steps} 失败 {rep.failed_steps}"
            + f" 未完成阶段剩 {unmet_leftover} 格（no_unmet_stages={unmet_leftover == 0}）"
            + (f" 走不到 {rep.unreachable} 格（豁免界 {unreachable_bound}、实扣 {unreachable_exempt}）"
               if rep.unreachable else "")
            + f" 浇水 {water_info.get('scope')} 口径 干 {water_info.get('dry')}/{water_info.get('crops')}"
            + f"（watered_outdoor={watered_outdoor}）"
            + f" → {'VERIFIED' if rep.verified else 'needs_review'} {rep.checks}"
        )
        # 记下"这一天结束时游戏处在哪一天"：总控用它判断游戏日有没有真的往前走。
        # 【task-38 真机教训（0.7.23 彩排 2026-10-13）】`last_obs` 常常是**睡前**那一张快照
        # （`rep.final` 就是特意冻结的睡前证据）⇒ 睡成功之后必须重新取一次观测，否则
        # `_last_day_key` 还停在旧的一天：总控看到"上一天报告结束在 17 日 / 这一天也结束在 17 日"
        # 就误判"游戏日没有前进"当场停 —— `--days 1` 靠 streak 侥幸仍返 0，`--days 3` 会在第 1 天
        # 就退出并判 1（run3 会白烧）。彩排日志里那行 `× 游戏日没有前进（sleep：night:…）`
        # 就是它，而同一份回执明写"已跨日：spring 17日 → spring 18日"。
        # 同一张"睡后快照"还要**落进账本**（`day_after`）：`rep.final` 是睡前观测，
        # `tools\verify-run3.py` 靠 `final.day != day_start.day` 判跨日 ⇒ 真账本永远判不出跨日
        # （之前只被"睡觉失败的日子整段跳过浇水检查"这层遮住没暴露）。这是**观测**不是回执。
        try:
            key_obs = last_obs
            if rep.ended_by == "sleep":
                try:
                    fresh = self._snap()
                except BridgeError as exc:  # pragma: no cover - 仅诊断
                    self._journal("day_key_resnap_failed", error=str(exc))
                    fresh = None
                if fresh is not None:
                    key_obs = fresh
                    rep.day_after = [int(v) if str(v).isdigit() else str(v)
                                     for v in FarmWorker.day_key(fresh)]
            self._last_day_key = tuple(FarmWorker.day_key(key_obs))
        except Exception:  # pragma: no cover
            self._last_day_key = None
        self._journal("day_end", **rep.as_dict())
        return rep

    # ------------------------------------------------------------------ 总控
    def _verified_streak(self) -> int:
        n = 0
        for d in reversed(self.days):
            if d.verified:
                n += 1
            else:
                break
        return n

    def _prepare(self) -> bool:
        assert self.client is not None and self.worker is not None
        try:
            health = self.client.health()
        except BridgeError as exc:
            self._journal("bridge_unavailable", reason=str(exc))
            self._say(f"× 桥不可达：{exc}")
            return False
        got = str(health.get("modVersion") or "")
        if got and got != MOD_VERSION_EXPECTED:
            msg = (f"游戏里的 Mod 是 {got}，脑期望 {MOD_VERSION_EXPECTED}："
                   f"新字段（wateringCan/refillTiles）会缺失，拒绝开跑")
            self._journal("mod_version_mismatch", got=got, expected=MOD_VERSION_EXPECTED)
            self._say("× " + msg)
            self.summary["prepare_error"] = msg
            return False
        obs = self._snap()
        if not obs.get("hasSaveLoaded"):
            st = self.worker.load_save()
            self._journal("load_save", ok=st.ok, reason=st.reason)
            if not st.ok:
                self._say(f"× 读档失败：{st.reason}")
                self.summary["prepare_error"] = f"读档失败：{st.reason}"
                return False
            obs = self._snap()
        if not self._is_farm(obs):
            st = self.worker.ensure_location(self.farm)
            self._journal("goto_farm", ok=st.ok, reason=st.reason)
            if not st.ok:
                self._say(f"× 去 {self.farm} 失败：{st.reason}")
                self.summary["prepare_error"] = f"去 {self.farm} 失败：{st.reason}"
                return False
            obs = self._snap()
        ess = self._essence(obs)
        self._say(f"[prep] Mod {got or MOD_VERSION_EXPECTED} 就绪；{ess['location']} {ess['tile']}；"
                  f"体力 {ess['stamina']} 钱 {ess['money']}g 作物 {ess['crops']}"
                  f"（未浇 {ess['unwatered_crops']}）种子 {ess['seeds']}")
        return True

    def run(self) -> int:
        """跑到"尾部连续 target_days 天 VERIFIED"为止。返回 0=达标，1=没达标，2=起不来。"""
        self.started = self.now()
        # 用户 m01184 的硬要求："大模型开始介入的时候告诉我一下"。所以开启状态必须在
        # 长跑一开始就**显式播报**（含 0 次调用的情形：非边界不问），不能悄悄联网。
        if self.llm_enabled:
            self._say("★ 边界决策的大模型已开启（慢脑）：每天的第一次决策、以及每次"
                      "「失败计数上升 / 代码策略阶段切换」都会问一次 —— 大模型只给方向"
                      "（任务意图 + 具名田区），格坐标与动作序列由代码按当下观测落。"
                      f"非边界不问（token 上限 {self.llm_max_tokens}）。")
            self._journal("llm_on", max_tokens=self.llm_max_tokens,
                          # 【task-56】留痕文件路径也记在这里：事后想核对"决策到底问了什么"
                          # 就能直接从 journal 找到旁边那个 -llm.jsonl。
                          llm_trace=str(self.llm_trace_path or ""),
                          note="每天首次决策 + 阶段切换/失败上升时才联网")
        else:
            self._say("i 边界决策的大模型已关闭：全程走确定性策略（代码政策：浇水优先、"
                      "种一个浇一个、无效格当天不再碰）。")
        if self.journal_path is not None:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            self._jf = open(self.journal_path, "a", encoding="utf-8")
        try:
            self.client = self.client_factory()
        except BridgeError as exc:
            self._journal("bridge_unavailable", reason=str(exc))
            self._say(f"× 桥不可达：{exc}")
            self.summary["prepare_error"] = str(exc)
            return self._finish(2)
        self.worker = self.worker_factory(self.client)
        if not self._prepare():
            return self._finish(2)
        while not self.aborted and self._verified_streak() < self.target_days:
            if self._budget_exhausted():
                self._journal("budget_exhausted", minutes=round(self._elapsed_minutes(), 1),
                              actions=self._actions)
                break
            if len(self.days) >= self.max_days:
                self._journal("day_cap", days=len(self.days), max_days=self.max_days)
                self._say(f"× 试了 {len(self.days)} 个游戏日仍未凑出连续 {self.target_days} 天，停下")
                break
            prev_key = self._last_day_key
            rep = self._run_day()
            if rep.ended_by in ("bridge_down", "stop", *BLOCKING_ENDS):
                # `blocked_modal`（职业选择 / 存档模态超时）/ `blocked_event`（游戏事件挂住）
                # 都要**人来处理**：再跑一遍同一天没有意义，只会把同一条 journal 又写一次。
                self._say(f"× 停下：{rep.ended_by} {rep.ended_reason}")
                break
            if prev_key is not None and self._last_day_key == prev_key:
                # 关键：游戏日根本没往前走（没睡成 / 卡住）⇒ 再跑一遍还是同一天。
                # 必须在这里停：否则"尾部连续 N 天"这个条件永远不可能满足，循环会一直转下去。
                self._journal("no_day_progress", day=list(prev_key), ended_by=rep.ended_by,
                              reason=rep.ended_reason)
                self._say(f"× 游戏日没有前进（{rep.ended_by}：{rep.ended_reason}），停下")
                break
        code = 0 if self._verified_streak() >= self.target_days else 1
        return self._finish(code)

    def _finish(self, code: int) -> int:
        streak = self._verified_streak()
        # task-15 §②：汇总行也要能一眼看到"有没有哪天留下了没做完的阶段"（`checks["no_unmet_stages"]`）。
        unmet_days = [d.day_text for d in self.days if not d.checks.get("no_unmet_stages", True)]
        self.summary = {
            "code": code,
            "verified_streak": streak,
            "target_days": self.target_days,
            "days": [d.as_dict() for d in self.days],
            "actions": self._actions,
            "minutes": round(self._elapsed_minutes(), 2),
            "stages_seen": sorted({s for d in self.days for s in d.stages_seen}),
            "no_unmet_stages": not unmet_days,
            "unmet_days": unmet_days,
            "journal": str(self.journal_path) if self.journal_path else "",
            **({"prepare_error": self.summary["prepare_error"]} if self.summary.get("prepare_error") else {}),
        }
        self._journal("finish", code=code, verified_streak=streak, actions=self._actions,
                      minutes=round(self._elapsed_minutes(), 2), stages_seen=self.summary["stages_seen"],
                      no_unmet_stages=not unmet_days, unmet_days=unmet_days)
        if self._jf is not None:
            try:
                self._jf.close()
            except Exception:  # pragma: no cover
                pass
            self._jf = None
        verdict_text = "VERIFIED" if code == 0 else ("起不来" if code == 2 else "needs_review")
        self._say(f"[run] {verdict_text}：尾部连续 {streak}/{self.target_days} 天 "
                  f"（共 {len(self.days)} 天，{self._actions} 个动作，{self.summary['minutes']} 分钟）"
                  + f"；no_unmet_stages={not unmet_days}"
                  + (f"（有未完成阶段的天：{'、'.join(unmet_days)}）" if unmet_days else "")
                  + (f"；准备失败：{self.summary['prepare_error']}" if self.summary.get("prepare_error") else ""))
        return code
