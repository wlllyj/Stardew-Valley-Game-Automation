# -*- coding: utf-8 -*-
"""长跑控制器：把"观测 → 决策 → 执行 → 验收"连成一个能连续跑好几个游戏日的循环。

【它在整个系统里的位置】
    fields.py   田区（"该去哪片地"）    —— 只报事实，不选动作
    planner.py  意图（"该做什么"）      —— 边界才问 LLM，其余走确定性策略
    farmwork.py 动作（"把这一格做掉"）  —— 发技能 + 观测差分
    longrun.py  日子（"今天干到什么时候、算不算数"）—— 本文件

【三条铁律（否则长跑会自己骗自己）】
1. **一天算不算数，只看观测**：`ended_by == "sleep"`（我们主动睡的，不是被系统 pass-out）
   + 当天没有 `failed` 步骤 + 睡前观测里 `unwatered_crops == 0`。回执不参与判定。
2. **"没事就睡"是不允许的**：只有三种情况放行睡觉 —— 到深夜（`sleep_at`）、体力见底、
   确实找不到任何能干的活（连买种子都做不了）。其余一律**否决并记账**（用户 2026-10-11 的原话：
   "体力还有这么多，田里还有很多需要清理的，直接睡觉不是浪费了吗"）。
3. **规划必须落到一片地上**：`planner.deterministic_plan` 的 `clear_area` 判据是"这块地方还有障碍"——
   如果喂给它**全农场**的计数（真机 245 个障碍），它会永远停在清障、永不进入开垦。
   所以本文件的每个决策都喂"**当天作业区（plot）的局部观测**"，只有"浇水/收获"这两件
   全局必须做完的事才用全量计数（`_plot_brief` 里就是干这个的）。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable

from .bridge import MOD_VERSION_EXPECTED, BridgeClient, BridgeError
from .farmwork import (STAGE_ACTION, FarmWorker, StageResult, StepResult, seed_items,
                       till_blocked_by)
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
    ended_by: str = ""            # sleep / pass_out / stuck / time_limit / budget / stop / bridge_down
    ended_reason: str = ""
    plots: list[dict[str, Any]] = field(default_factory=list)
    stages: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    final: dict[str, Any] = field(default_factory=dict)
    verified: bool = False

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
            "ok_steps": self.ok_steps,
            "skipped_steps": self.skipped_steps,
            "failed_steps": self.failed_steps,
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
        water_min_stamina: float = 1.0,
        plot_walk_timeout_ms: int = 20000,
        max_refills_per_day: int = 4,
        max_plots_per_day: int = 10,
        supervise_every: int = 20,
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
        # 浇水的体力闸门单独放低到 1 点：当天种下的作物"没浇"是不可补的损失，
        # 必须允许在体力见底前把最后几格浇完（m01847/m01774）。
        self.water_min_stamina = float(water_min_stamina)
        self.plot_walk_timeout_ms = int(plot_walk_timeout_ms)
        self.max_refills_per_day = int(max_refills_per_day)
        self.max_plots_per_day = int(max_plots_per_day)
        self.supervise_every = int(supervise_every)
        self.report_dir = Path(report_dir) if report_dir else None
        self.journal_path = Path(journal_path) if journal_path else None
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
        # 本日已经播报过"没种子也没钱 ⇒ 不再开垦"的任务（`till_area`/`plant_area`）。
        # 只在第一次撞到时说一句，别每轮刷屏（task-9：run2 白锄 60 格、体力 270→74）。
        self.seed_gate_noted: set[str] = set()
        # 本日"策略要了但一格目标都拿不出来"的任务。策略与执行层一旦不同口径，
        # 每轮空转一次、攒够 3 轮就判 stuck 报废整天；记下来当天不再要它。
        # **片区级**：`clear_area`/`till_area`/`plant_area` 只在作业区内看目标，换一片地就得忘掉。
        self.no_target: set[str] = set()
        # **全场级**：`water_area`/`harvest` 看的是整个农场（一天要把所有作物伺候完），
        # 它们没目标就是真没目标 —— 换片地也不该再问。
        self.no_target_global: set[str] = set()

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
        }

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
        """挑（或保持）当天的作业区；找不到有活的区就返回 None。"""
        if self.plot is not None and self._plot_has_work(obs, self.plot["tiles"]):
            return self.plot
        for cand in self._plot_candidates(obs):
            if not self._plot_has_work(obs, cand["tiles"]):
                continue
            if self.plots_today >= self.max_plots_per_day:
                rep.notes.append(f"今天已经开了 {self.plots_today} 片地，不再换区")
                return self.plot if (self.plot and self._plot_has_work(obs, self.plot["tiles"])) else None
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
        full = Brief.from_observe(obs, consecutive_failures=self.fail_streak,
                                  last_failure=self.last_failure, target_tiles=self.target_tiles_base)
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
        if task in ("clear_area", "till_area", "plant_area"):
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
        if task == "clear_area":
            return [t for t in local
                    if str((tmap.get(t) or {}).get("kind") or "") in ACTIONABLE_KINDS]
        if task == "till_area":
            return [t for t in local
                    if t in tillable and not _till_blocked_by(tmap.get(t))]
        if task == "plant_area":
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
        for cand in self._plot_candidates(obs):
            if self._plot_has_work(obs, cand["tiles"]):
                reasons.append(f"{cand.get('zone') or '附近'}还有地要清/开/种")
                break
        return reasons

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
                      steps: list[StepResult], rep: DayReport) -> None:
        """把"动了但世界没变"的格子记进 `self.blocked`：今天不再碰（一格最多白试一次）。

        只记 `till`/`clear`/`sow` 这类**主观能动**的动作。浇水失败不封格 —— "当天所有作物都浇过"
        是当天的验收条件，封掉就等于自欺（`_leftover` 仍会如实把它报出来，天不算数）。

        两种来源都要封：
        - `s.failed`：动作发了、体力花了、世界没变（旧口径）；
        - `s.proven_inert`（task-4 新增）：**动手前**判据就成立、压根没挥（缺工具 / 观测说这格
          今天动不了）。这种"zero-cost skip"同样是"今天别再碰它"的结论，但**不记 failed** ——
          真机 run1 的两个 grass 格就是这么被连挥两次、真花体力的（用户 m01804）。

        **但两类失败不许封格**（task-22，两者都靠 `FarmWorker` 打的显式标记）：
        - `s.env_block`（渐黑 / 模态 / 没存档）：环境挡路**不是**这一格的属性，世界好了这格还得做；
        - `s.inconclusive`（超时 / 异常 / 没见过的码）：连结论都没拿到，更没资格判它"干不动"。
          这两类如实卡在 `leftover` 里 ⇒ `met=False`、当天 needs_review。
        """
        before = self._tile_states(before_obs)
        after = self._tile_states(after_obs)
        marked = 0
        for s in steps:
            if not (s.failed or s.proven_inert) or not s.tile or s.action not in ("till", "clear", "sow"):
                continue
            if s.env_block or s.inconclusive:
                # 环境挡路 / 没结论 ≠ 这一格干不动：不封格（记进 env_fail/inconclusive_fail 汇总）。
                continue
            key = tuple(s.tile)
            if key in self.blocked or before.get(key) != after.get(key):
                continue
            self.blocked[key] = f"{s.action} 无效：{s.reason[:80]}"
            marked += 1
            self._journal("blocked", tile=list(key), action=s.action,
                          no_effect=bool(s.failed), reason=s.reason[:160])
        if marked:
            rep.notes.append(
                f"记下 {marked} 格「动了没用」的地，今天不再碰（共 {len(self.blocked)} 格）")

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
        """
        for s in steps:
            if not s.tile or not (s.failed or s.proven_inert):
                continue
            if s.env_block:
                continue
            key = tuple(s.tile)
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
                self._journal("seed_gate", stage=task, seeds=seeds, money=money,
                              seed_price=self.seed_price, zone=self.zone_name)
        wmin = self.water_min_stamina if task == "water_area" else self.min_stamina
        while True:
            attempts += 1
            snap = self._snap()
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
            self._mark_blocked(snap, self._snap(), res.steps, rep)
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
        failed = [s for s in all_steps if s.failed]
        skipped = [s for s in all_steps if s.skipped]
        oks = [s for s in all_steps if s.ok]
        inert = [s for s in all_steps if s.proven_inert]
        env_fail = [s for s in all_steps if s.env_block]
        inconclusive = [s for s in all_steps if s.inconclusive]
        rep.stages.append({
            "stage": task, "tiles": 0 if not all_steps else len({s.tile for s in all_steps if s.tile}),
            "ok": len(oks), "skipped": len(skipped), "failed": len(failed),
            "proven_inert": len(inert),
            "env_block": len(env_fail), "inconclusive": len(inconclusive),
            "stopped": stopped, "leftover": len(leftover),
        })
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
                          note="连续请求没拿到结论（超时/异常/未知码）⇒ 不封格，但占本日尝试配额")
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
        if inert:
            reason_bits.append(f"其中 {len(inert)} 格当场判据成立「干不动」已封到当天结束")
        if env_fail:
            reason_bits.append(f"其中 {len(env_fail)} 格被环境挡住（渐黑/模态，不封格也不占配额）")
        if inconclusive:
            reason_bits.append(f"其中 {len(inconclusive)} 格没拿到结论（超时/异常，占配额但不封格）")
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
            if task in STAGE_ACTION:
                acted = self._run_stage_intent(intent, obs, plot, rep) or acted
                obs = self._snap()
                continue
            self._journal("intent_unknown", task=task)
            rep.notes.append(f"未知意图 {task}（跳过）")
        return acted

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

    # ------------------------------------------------------------------ 一天
    def _run_day(self) -> DayReport:
        obs = self._snap()
        rep = DayReport(day_key=FarmWorker.day_key(obs), started_at=self.now() - self.started)
        self.days.append(rep)
        self.plot = None
        self.zone_name = ""
        self.plots_today = 0
        self.refills_today = 0
        self.idle_rounds = 0
        self.blocked = {}
        self.tile_attempts = {}
        self.seed_gate_noted = set()
        self.no_target = set()
        self.no_target_global = set()
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

        last_obs = obs
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

            allow, code, text = self.sleep_guard(obs)
            if allow:
                rep.ended_by, rep.ended_reason = self._do_sleep(obs, rep, f"{code}:{text}")
                break

            self._preconditions(obs, rep)
            plot = self._ensure_plot(obs, rep)
            if plot is None:
                # 没有作业区（区里没活），但守卫说还有活 —— 把话说清楚再睡，别假装干完了
                rep.notes.append("找不到有活的作业区：" + "；".join(self.work_reasons(obs)))
                rep.ended_by, rep.ended_reason = self._do_sleep(obs, rep, "no_plot")
                break

            brief = self._plot_brief(obs, plot)
            decision = self.planner.decide(self.state, brief)
            self._journal("decision", day=list(rep.day_key), boundary=decision.boundary,
                          source=decision.source, llm=decision.llm_called,
                          intents=[i.as_dict() for i in decision.intents],
                          problems=list(decision.problems), fallback=decision.fallback_reason,
                          # 单独一个布尔位：截断是**配置问题**（该调大 token 预算），
                          # 和网络/校验失败混在一个字符串里事后分不清（task-9）。
                          truncated=bool(getattr(decision, "truncated", False)),
                          zone=self.zone_name)
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
                    recovered += 1
                    self._journal("plot_exhausted", recovered=recovered, zone=self.zone_name,
                                  note=f"这一片没目标了，但守卫仍要求干活（{text}）⇒ 换一片地")
                    if recovered > self.max_plots_per_day:
                        rep.notes.append(f"换过 {recovered} 片地都拿不出目标")
                        rep.ended_by, rep.ended_reason = self._do_sleep(
                            obs, rep, f"no_work:换过 {recovered} 片地都没有目标")
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
                    rep.ended_by, rep.ended_reason = "stuck", (
                        f"连续 {self.idle_rounds} 轮世界没有任何变化（最后意图："
                        f"{[i.task for i in decision.intents]}；策略说有进展：{acted}）")
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
        rep.checks = {
            "slept_by_us": rep.ended_by == "sleep",
            "no_hard_failures": rep.failed_steps == 0,
            "crops_watered": int(rep.final.get("unwatered_crops") or 0) == 0,
            "day_justified": (rep.ended_reason.split(":", 1)[0] in ("night", "stamina", "no_work", "no_plot")
                              if rep.ended_by == "sleep" else False),
        }
        rep.verified = all(rep.checks.values())
        self._say(
            f"[day] {rep.day_text} 结束：{rep.ended_by}"
            + (f"（{rep.ended_reason}）" if rep.ended_reason else "")
            + f" 阶段 {rep.stages_seen or '无'} 做成 {rep.ok_steps} 跳过 {rep.skipped_steps} 失败 {rep.failed_steps}"
            + f" → {'VERIFIED' if rep.verified else 'needs_review'} {rep.checks}"
        )
        self._journal("day_end", **rep.as_dict())
        # 记下"这一天结束时游戏处在哪一天"：总控用它判断游戏日有没有真的往前走
        try:
            self._last_day_key = tuple(FarmWorker.day_key(last_obs))
        except Exception:  # pragma: no cover
            self._last_day_key = None
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
            if rep.ended_by in ("bridge_down", "stop"):
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
        self.summary = {
            "code": code,
            "verified_streak": streak,
            "target_days": self.target_days,
            "days": [d.as_dict() for d in self.days],
            "actions": self._actions,
            "minutes": round(self._elapsed_minutes(), 2),
            "stages_seen": sorted({s for d in self.days for s in d.stages_seen}),
            "journal": str(self.journal_path) if self.journal_path else "",
            **({"prepare_error": self.summary["prepare_error"]} if self.summary.get("prepare_error") else {}),
        }
        self._journal("finish", code=code, verified_streak=streak, actions=self._actions,
                      minutes=round(self._elapsed_minutes(), 2), stages_seen=self.summary["stages_seen"])
        if self._jf is not None:
            try:
                self._jf.close()
            except Exception:  # pragma: no cover
                pass
            self._jf = None
        verdict_text = "VERIFIED" if code == 0 else ("起不来" if code == 2 else "needs_review")
        self._say(f"[run] {verdict_text}：尾部连续 {streak}/{self.target_days} 天 "
                  f"（共 {len(self.days)} 天，{self._actions} 个动作，{self.summary['minutes']} 分钟）"
                  + (f"；准备失败：{self.summary['prepare_error']}" if self.summary.get("prepare_error") else ""))
        return code
