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
from typing import Any, Callable, Iterable, Mapping

from .bridge import MOD_VERSION_EXPECTED, BridgeClient, BridgeError
from .farmwork import (CLUMP_KINDS, ENV_BLOCK_STATUSES, FRONTIER_KINDS, NEIGHBORS,
                       PATH_STAMINA_ALLOWANCE,
                       SEED_KEEP_FACTOR, SLOT_RELIEF_KEEP, STAGE_ACTION, STAMINA_COST_CLEAR,
                       STAMINA_COST_SOW,
                       STAMINA_COST_TILL, STAMINA_COST_WATER, STEP_RESULT_CODES,
                       TREE_KIND,
                       UPGRADE_KINDS, UPGRADE_PRICES,
                       UPGRADE_TRADE_ITEMS, FarmWorker, StageResult, StepResult,
                       buy_count_for, farm_dead_crops, farm_dry_dead_crops, farm_dry_tiles,
                       farm_ready_tiles, has_seed_metadata,
                       is_seed_offer, pick_seed_offer, plantable_seeds, player_free_slots,
                       seed_items, seed_season_state,
                       slot_relief_plan, surplus_sell_plan, tile_ready, till_blocked_by,
                       tool_being_upgraded, tool_suspended_stages, tool_tier, tool_upgrade_days_left)
from .farmwork import (_bare_item_id, SEED_NAME_HINTS, SLOT_RELIEF_NEVER_SELL_IDS,
                       season_probe_item)
from .planner import load_gaps_file, save_gaps_file
# 【task-230 P0-4.6】上面的缺口清单（gaps）读写与下面的教训库读写**刻意分成不同 import 行**：
# 缺口是"只提示"的 L0 证据（`docs/_run10-criteria.md` §8.3），**绝不允许自动转成教训注入**
# （那会让未经验证的模型自述变成跨天判据）。静态审计（task-224 探针 P0-4-7）按"同一行同现
# 缺口函数名与教训生成函数名"判红 ⇒ 两族名字永不写在同一行。
from .planner import (DECISIONS_KEPT, DEFERRED_KINDS, GAPS_INJECT_MAX, GAPS_MAX_ITEMS,
                      GAPS_SAMPLE_TILES, GAPS_TEXT_MAX_CHARS, LESSONS_INJECT_CHARS,
                      LESSONS_INJECT_MAX, BoundaryPlanner, Brief, PlannerState, TaskIntent,
                      TaskOutcome, decision_line, deterministic_plan, load_lessons_file,
                      load_scope_file, make_lesson, prune_lessons, render_lessons,
                      render_review_facts, save_lessons_file, save_scope_file)

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

#: 【task-218】清障**能力覆盖**的种类：老四类 + 普通树（0 级斧可砍）+ 够格的 clump 一族
#: （`_tool_blocked_tv` 会把 `toolOk` 不是 true 的 clump 挡在外面）。
#: 刻意**不并进 `ACTIONABLE_KINDS`**：后者还用于"这块地有没有活/要不要回来"的老判据，
#: 而树要额外受日级体力预算约束（`_tree_budget_left`）——混在一起会让预算挡下的树把守卫钉死。
CLEARABLE_KINDS = ACTIONABLE_KINDS + (TREE_KIND,) + CLUMP_KINDS

#: 【task-241】清障预算**体力驱动**（0.7.41 冒烟的硬编码"每天 2 棵"对照 `farm.trees 804`
#: ⇒ 要 400 天，目标 1「整场清完」不可达）。预算 = 可支配体力 ÷ 单棵成本，封顶
#: `MAX_TREES_PER_DAY`。单棵成本按卡面口径估：每棵 ~6 刀 × `STAMINA_COST_CLEAR`；
#: 浇水/收获永远优先（`_stamina_budget` 的 `water_reserve` 先扣）。砍倒一棵后
#: `trees_cleared_today` 立刻 +1 且下一轮用**新观测**重算剩余预算。
MAX_TREES_PER_DAY = 20
TREE_STAMINA_COST = 6.0 * STAMINA_COST_CLEAR

#: 【task-219】"不产生瓦片级执行对账"的任务：它们本来就不按"有没有目标格"判，
#: 所以**免于**"非空 reasons 才合格"这条不变式（但它们仍然要有 `intent_execution` 记录）。
#: `docs/_run10-criteria.md` §8.2c（0.7.39 P0-3）点名要求这四个必须在 ACTIONLESS_TASKS 里。
ACTIONLESS_TASKS: tuple[str, ...] = ("sleep", "review", "wait_for_save", "recover_stamina")

#: 【task-233】**非片区**意图：它们没有"作业区"⇒ §8 的 `no_target` 证据 schema
#: （`evidence.stage_tiles_empty`）**根本不适用**。按 §8.2b/§8.3.7：证据不可用 ⇒
#: **禁止裸用 `no_target`**，必须降级 `unknown_evidence` + `unknown_why`。
#: 真机事故（`logs/longrun-smoke-0739.jsonl`）：`ship` 用了裸 `no_target` ⇒ analyzer
#: 红 `missed:intent_no_target_evidence:ship`。这组任务失败时改用它们**自己的**证据
#: （`_non_plot_evidence`：白名单/空格等可判事实）+ `unknown_evidence`，绝不冒充"没目标"。
NON_PLOT_INTENT_TASKS: tuple[str, ...] = (
    "ship", "sell", "sleep", "review", "recover_stamina", "wait_for_save",
)

#: 【task-219】意图未执行的**原因码闭合集**（`docs/_run10-criteria.md` §8.2 + 0.7.39 P0-3）：
#: 集外一律算缺陷（analyzer 判红）。P0-3 的拆分：
#:  * `cancelled_by_verify` 拆成 ⇒ cancel 用 `no_target`、unknown 用 `unknown_evidence`；
#:  * `_apply_policy` 改写掉的意图用 `superseded`；
#:  * 结论拿不到（半步证据不足）用 `unknown_evidence`（**不许**拿 `no_target` 冒充）。
INTENT_REASON_CODES: tuple[str, ...] = (
    "no_target", "deferred_capability", "tool_level", "budget", "blocked_tile",
    "blocked_modal", "no_slot", "world_stuck", "unknown_evidence", "superseded", "gated",
    "failed",
)

#: 【task-230 P0-3.2】`StepResult.code` → 原因码的**单一数据源**（唯一映射表）。
#:
#: 为什么必须是一张表而不是 if 链：漏映射 = 那一格悄悄落进 `unknown_evidence` 兜底桶，
#: 看起来"有原因"实际是漏了。所以：
#:   * 键集合必须**精确等于** `farmwork.STEP_RESULT_CODES`（漂移测试
#:     `tests/test_longrun.py::TestTask230ReasonMapping` 钉死，多一个少一个都红）；
#:   * 成功类码映射为空串（`""` = "这一格做成了，不需要原因码"）；
#:   * 特殊标记（`blocked_by_tool` 标记、env status 里的 `ui_modal` 区分等）在
#:     `_tile_reason()` 里**先**处理，表只负责"code 本身怎么归"。
STEP_CODE_TO_REASON: dict[str, str] = {
    "ok": "",
    "already": "",
    "skipped": "gated",           # 具体是不是 deferred_capability 由 `_tile_reason` 再看 kind
    "failed": "failed",
    "no_seed": "gated",
    "need_refill": "gated",
    "no_slot": "no_slot",
    "no_target": "no_target",
    "no_space": "no_slot",
    "unreachable": "blocked_tile",
    "encircled": "blocked_tile",
    "no_machine": "blocked_tile",
    "no_object": "blocked_tile",
    "not_ready": "gated",
    "already_full": "gated",
    "tile_occupied": "blocked_tile",
}


def _intent_coverage_ok(rec: Mapping[str, Any]) -> bool:
    """【task-230 P0-3.9/10】一条执行对账是否满足**瓦片制不变式**（纯函数，供验收直调）。

    两条：
      * `requested_tiles == ok_tiles + failed_tiles + unexecuted_tiles`；
      * 有瓦片的记录：`Σ reasons.count == failed_tiles + unexecuted_tiles`；
        意图级记录（`reasons_are_intent_level`，一格都没分下去）：`Σ reasons.count >= 1`。
    【task-230】集外原因码也在这里判（`reason ∉ INTENT_REASON_CODES` ⇒ False）：
    这是"验收可直调"的唯一入口，宽松会让"集外码"漏到 analyzer 之外（deputy 的 P0-3 就是
    原因码集合没收口）。正式判红仍在 analyzer，这里只是让同一判据可被单测/探针直接跑。
    """
    try:
        get = (lambda k, d=0: rec.get(k, d)) if isinstance(rec, Mapping) \
            else (lambda k, d=0: getattr(rec, k, d))
        requested = int(get("requested_tiles") or 0)
        ok_t = int(get("ok_tiles") or 0)
        failed_t = int(get("failed_tiles") or 0)
        unexec = int(get("unexecuted_tiles") or 0)
        reasons = dict(get("reasons", {}) or {})
        total_reasons = sum(int(v) for v in reasons.values())
    except (TypeError, ValueError):
        return False
    if requested != ok_t + failed_t + unexec:
        return False
    for code in reasons:
        if str(code) not in INTENT_REASON_CODES:
            return False
    actionless = bool(get("actionless", False))
    if actionless:
        return True
    if bool(get("reasons_are_intent_level", False)) or requested == 0:
        return total_reasons >= 1
    return total_reasons == failed_t + unexec


def _tool_blocked_tv(tv: Mapping[str, Any] | None) -> bool:
    """【task-20】这一格是不是"工具不够格 / 判不了"（观测层面就能判，不需要动手）。

    判据（单一权威实现，`_stage_tiles`/`work_reasons` 共用）：
      * kind 属于 `farmwork.CLUMP_KINDS`（clump/stump/log/boulder/rockPile/greenRain）；
      * 且 `toolOk` **不是** `True`（`false` = 明确不够格；`null`/缺字段 = 判不了 ⇒ fail-closed）。
    ⇒ 这样的格子：不进"可清目标"、不产生"还有活"的守卫理由、当天封格次日重试。

    其余 kind（weed/twig/stone/tree/fruitTree/grass/bush）**一律不受影响**（返回 False）。
    """
    if not tv:
        return False
    if str(tv.get("kind") or "") not in CLUMP_KINDS:
        return False
    return tv.get("toolOk") is not True


def _stamina_or_none(obs: Mapping[str, Any]) -> float | None:
    """【task-161】读 `player.stamina`；**读不到就返回 `None`**（不许退化成 0.0）。

    为什么不能用 `FarmWorker.stamina()`：那个助手把缺失当 `0.0`——对"还能不能干活"是
    fail-safe 的，但对**事后标定**是灾难（"没观测到"会被记成"体力耗尽"，
    标定出来的每格成本会被严重放大）。所以这里单独实现一个三态读数，
    只用于 `stage.stamina_before/after/spent` 与 `day_end.stamina_calibration` 留痕。
    """
    player = obs.get("player") if isinstance(obs, Mapping) else None
    if not isinstance(player, Mapping):
        return None
    value = player.get("stamina")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 1)

#: 看**全场**目标的任务（浇水/收获要伺候所有作物）；其余阶段只看**作业区**。
#: 这个区分决定"没目标"这笔账当天会不会因为换了一片地而作废。
WIDE_TASKS = ("water_area", "harvest")

#: 同一格一天内最多被**发起**几次动作。第 3 次一律不发（用户 m01804："不要白白浪费很多体力"）。
#: 主闸是 `blocked`（第一次"挥了没变/缺工具"就当天封格）；这个上限是**兜底不变量**：
#: 任何一条没被 `blocked` 覆盖的失败路径（例如世界变了但没做成）也不许把同一格磨到天亮。
MAX_TILE_ATTEMPTS = 2

#: 【task-5 / 0.7.44】同一格当天被**重新分配**却每次都没有产出的次数上界。
#:
#: A8 冬 9/14 的 1 格余量死循环：被围住的 `[37,35]` 在一天里被重新分配了 28/63 次（日志里
#: `encircled` 同格 28/63 条、`stage_shortfall` 同数）——因为 `encircled` 步既不是 `failed`
#: 也不是 `proven_inert`（task-68 刻意不封格），既不吃 `tile_attempts` 配额、也不进 `blocked`，
#: 于是 `_stage_tiles` 每一轮都把它重新分下去，世界不变 ⇒ 3 轮 idle 判 stuck、一整天报废。
#: 修法有两层：① `encircled_day`/`blocked` 直接不进下一轮目标池（`_stage_tiles`）；② 本常量是
#: **兜底不变量**——任何"分配了但没产出、又没被挡死集合覆盖"的格子，到界后当天也不再选它，
#: 并逐格 journal `blocked{action=stage_realloc, alloc_no_progress, limit}` 留痕。
#: **只影响"今天还分不分它"，`leftover`/`assigned_undone`/`no_unmet_stages` 一个字不动**。
MAX_ALLOC_NO_PROGRESS = 3

#: 【task-28 防自旋】同一格同一天**连续被环境挡住**（`env_block`：`busy`/`ui_modal`/`no_save`/
#: `world_fading`）超过这个次数以后，就**不再免费**：从下一次起按"没结论"占 `MAX_TILE_ATTEMPTS`
#: 配额。理由：`env_block` 不占配额是刻意的（环境抖动不该封格），但"Mod 一直回 busy"这种
#: **持续**状态如果没有上限，`_stage_tiles` 每轮都会把同一格选出来 ⇒ 一天在同一个格上无限打转。
#: 取 2（而不是 1）是为了给**真实**的瞬时抖动留余量：渐黑/模态通常一次就过去了；连续 3 次以上
#: 还挡着的，判定为"今天这个世界不适合干这格"，让它如实落到 `capped`/`needs_review`。
MAX_ENV_ATTEMPTS = 2

#: 【task-198】"腾格收敛回路"的日级上界：背包满不是某一格的属性（见 `farmwork.NO_SLOT_CODE`），
#: 它是**全局**阻塞，得由日级策略来界住 —— "腾 N 格 → 再收"。
#:
#: run A′（`logs/longrun-runA3-0736.jsonl`）就是这个洞：背包满 ⇒ 45 条 harvest 同句失败、
#: 59 次 `harvest_gave_up`、`no_hard_failures=false`，而 `sell`/`ship` 明明一直在跑 ——
#: 缺的不是能力，而是"**先腾格再收**"的次序。回路每轮至少腾 1 格；用满本上限还腾不出
#: （没有可卖/可出货的叠）⇒ 如实 `inventory_blocked` 收尾（不进 `JUSTIFIED_END_REASONS`）。
#: 【task-237】轮数从 3 放宽到 6：0.7.40 A2 冒烟里 `harvest` 每天需要 **12 格**，而
#: 旧口径"目标 = SLOT_RESERVE + 1 = 2 格"每轮只腾 1 格 ⇒ 腾出来立刻被塞满、
#: 3/3 天仍然 `inventory_blocked`。现在目标水位由当天收获需求算（见 `_harvest_demand`），
#: 6 轮 × 最多 10 叠是硬上界，防止"卖穿背包"那种反向事故。
SLOT_RELIEF_MAX = 6

#: 【task-232】空格压力通道：`_slot_relief` 每轮最多卖 1 叠、每天最多卖这么多叠
#: （与"轮数"是两个独立界：一轮可能先出货箱再卖材料）。
#: 【task-237】5 → 10：需求驱动后一天可能要腾到 12 格，叠数界必须比轮数宽，
#: 否则"卖 5 叠就停"会卡在目标水位之下（0.7.40 实测的另一个卡点）。
SLOT_RELIEF_MAX_STACKS_TOTAL = 10

#: 【task-237】**需求驱动**：当天"可收格数"的上界（harvest 阶段每轮最多分配 12 格）。
HARVEST_DEMAND_CAP = 12

#: 【task-237】背包空格的目标上限：目标水位 = `min(SLOT_RESERVE + harvest_demand, SLOT_FREE_CAP)`。
SLOT_FREE_CAP = 12

#: 【task-237】可收格数**读不到**时的保守需求（fail-closed：不猜 12，也绝不当作 0）。
SLOT_RELIEF_DEMAND_FALLBACK = 3

#: 【task-232】空格压力的目标水位：腾到 `SLOT_RESERVE + 1` 格就停手（Lead m21658）。
#: 低水位只有 1 格余量时，收货/掉落立刻又填满 ⇒ 只腾到"够用"再评估，不追求清空背包。
#: （定义在 `SLOT_RESERVE` 之后，见下。）

#: 【task-198】背包"低水位"：空槽 ≤ 这个数就**提前**腾格（而不是等 0 格才动）。
#: 掉落/收获一次可能进多件（clear/till/water 的掉落也在填包），留 1 格余量能避免
#: "刚腾出 1 格、收一件又满了"的抖振 —— 但**不会**因此多花请求：只在确实有可腾的叠时才动。
SLOT_RESERVE = 1

#: 【task-232】空格压力的目标水位 = `SLOT_RESERVE + 1`（Lead m21658）：
#: 腾到"低水位之上 1 格"就停手 —— 收货/掉落一次可能进多件，追清空背包既没必要也浪费时间。
SLOT_RELIEF_TARGET_FREE = SLOT_RESERVE + 1

#: 【task-25 rev4 / 0.7.46】Pierre 背包升级（12→24 格 / 2000g）的**对话购买**参数。
#: 为什么必须走对话：0.7.46 的 Mod `talk` 原语让 NPC 用游戏自己的 `checkAction` 开对话，
#: 选项由 `dismiss_modal{answerText:"Purchase"}` 走 task-208 的 `answerDialogue` 车道；
#: 扣钱/扩容由**游戏代码自己**做（SDV #US 串 `SeedShop_BuyBackpack_Response2000/…/Backpack`）。
#: 判据**只看观测差分**：`money_after == money_before - 2000` 且 `inventoryCount 12→24`。
BACKPACK_BASE_CAPACITY = 12
BACKPACK_UPGRADE_CAPACITY = 24
BACKPACK_UPGRADE_PRICE = 2000
BACKPACK_UPGRADE_MAX_ATTEMPTS = 2
#: 整条购买流程（去店 → talk → 应答 → 回农场）的总墙钟预算：超时按 `timeout` 失败码收口，
#: 绝不允许把当天农务拖死（0.7.46 卡 A 的硬要求）。
BACKPACK_UPGRADE_DEADLINE_S = 90.0
BACKPACK_UPGRADE_SHOP = "SeedShop"
BACKPACK_UPGRADE_NPC = "Pierre"
BACKPACK_UPGRADE_ANSWER = "Purchase"
BACKPACK_TALK_TIMEOUT_MS = 15000

#: 【task-28 卡 D】满包清障的日级损失上界：`free_slots == 0` 且已经证明「腾格手段用尽」
#: 时，**已经开出去的 clear_area 阶段**仍会继续清几格（阶段不会半路撤回），而每清一格
#: 都可能白丢一次掉落。取 5 的理由：
#:   * 0.7.45 冬26 冒烟 `loot_lost_steps=21`、冬27 `205/210` —— 后者正是一整天白清；
#:   * 一个阶段最多分配 `per_stage_tiles=12` 格，5 步 ≈ 半阶段，足够收掉"已经在路上"的
#:     尾巴，又不会让一整天继续往 200+ 步的坑里走；
#:   * 常量只约束**新分配**（`_stage_tiles` 按剩余额度收窄 `limit`），不追溯已经发生的步；
#:     它只影响"今天还清不清"，不改任何 checks/leftover/assigned 口径。
CLEAR_LOOT_LOSS_MAX_STEPS = 5

#: 【task-68】"一轮不许零动作"（Lead m06336）：当**本轮所有指定目标都够不着/被围住**、但世界里
#: 仍有"可达 + 可清障"的格子（杂草/石头/树枝/草）时，至少清掉一格 —— 否则 idle 计数攒够 3 轮
#: 就判 stuck、整天报废（run6 只跑 19 秒的直接原因之一）。
#: 上界 20/天：不封顶的话"目标全够不着"的日子会把整天耗在**无目的**的清障上。
FRONTIER_CLEAR_MAX = 20

#: 【task-124】同一秒内连续判"这一片没目标"的次数上界（0.7.29）。
#:
#: run9（run A）第二天：`plot_exhausted` 在 **0.6 秒**里连发 **12 次** —— 每轮换一片、每片都
#: 拿不出目标，纯空转（`deterministic_plan` 吃的是**当前片地**简报，四条分支全不成立 ⇒ `review`；
#: 而 `work_reasons`/`sleep_guard` 用的是**跨片地当日 leftover**）。同一秒 ≥ 本值 ⇒ 记一条
#: `plot_exhausted_burst`，并按既有有界机制结束当天换片循环，不再把整天耗在无目的换片上。
PLOT_EXHAUSTED_BURST = 5

#: 【task-73】stuck 日"有界翻篇"的整轮上限（Lead m06814）。
#:
#: 为什么要翻篇：run6（0.7.25）两个 `day_end` 都是 `ended_by=stuck`，随后 `run()` 命中
#: `prev_key == self._last_day_key` ⇒ 写 `no_day_progress` 并 **break 整轮** —— 游戏日根本
#: 没往前走（没睡），一次"撞上一片走不到的簇"就让无人值守在 **19 秒**内终止，连"明天再试"
#: 的机会都没有。所以 idle 守卫判 stuck 后不再直接停：走一条**刻意绕过 `sleep_guard`** 的
#: 收尾睡觉路径（守卫此刻仍会说"有活"，但本日已用有界尝试证明动不了）。
#: 取 2：一次算偶发（世界刚好卡了一片），两次以上就该让人来看，而不是无限"睡过去再撞一次"。
MAX_STUCK_FLUSH = 2

#: 【task-50】同一格"窗口外干作物"一天最多试几次（一次 = 走过去 + 浇一下）。
#:
#: 为什么要这个上限：`farm.dryTiles` 里的格子可能**根本走不到**（农场另一头、
#: 被建筑/水塘隔开），而 `farm.dryCrops > 0` 又不允许判 `no_work`（run5 三天就是这么
#: 全挂的）⇒ 没有上限就会"走过去-失败-再走过去"打到天亮。
#: 取 2 与 `MAX_TILE_ATTEMPTS` 同口径：第一次多半是寻路的一次性抖动，第二次还不行就
#: 认账（当天以 `stuck:` 收尾并点名坐标，而不是洗成"没活"）。
FAR_DRY_MAX_TRIES = 2

#: 【task-133】窗口外浇水时，一天最多为"壶空"补几次水。
#:
#: run9b 实证（`logs/longrun-3day-llm-run9b.jsonl`）：`[12,30]` 明明能走到、也能浇上
#: （t=408.26 / t=1483.17 都 `ok=true`），但 t=896.64 / 924.27 / 1280.08 三次都是
#: `code=need_refill`「壶里没水了（先补水）」⇒ `try_` 到 2 就 `given_up=true`，
#: **全账本 `refill` 只有 2 次**；summer 15/16 因此以 `gave_up_dry` 收尾，
#: 而收尾文案把它写成"够不着"（错因，误导验收）。
#: ⇒ 壶空是**前置条件**（先补水再浇），不该算成一次"够不着"；但补水也要有界（≤2），
#: 免得在"补水点走不到"时把整天耗在这一格上。
FAR_DRY_REFILL_MAX = 2

#: 【task-157】窗口外那格"走不到"时，**同一格一天最多**朝它开几次路。
#:
#: run9d 实证：`[12,30]` 在 t=827.6/827.99 连续两次 `code="unreachable"`、当天以 `gave_up_dry`
#: 收尾 ⇒ `watered_outdoor=false`；summer 23/24 只因下雨（dry=0）才过。这一格在 run7/8/9/9b/9c
#: 都出现过 ⇒ 只要当天不下雨就必然破"连续 VERIFIED"。task-68 已有 `open_way` 原语（清挡路邻格，
#: 上限 `MAX_OPEN_ACTIONS`），这里只是**朝这一格**调用它，并把次数收在 2 以内：
#: 开路本身有界（≤4 次清障/次），再乘 2 仍是常数；开完立刻**重试同一格**（同一次 try 之内，
#: 不额外消耗该格的 `FAR_DRY_MAX_TRIES` 额度）。
FAR_DRY_OPEN_MAX = 2

#: 【task-199】窗口外熟作物：同一格一天最多试几次（一次 = 走过去 + 收一下）。
#:
#: 与 `FAR_DRY_MAX_TRIES` 同口径：第一次多半是寻路抖动，第二次还不行就认账 ——
#: 记 `ready_far_blocked`（逐格、含 `walked`/`opens`/`cleared`）并当天不再试它，
#: **不许**让"农场口径还有熟作物"变成守卫的无限空转理由（run A′ fall 13 的病灶）。
READY_FAR_MAX_TRIES = 2

#: 【task-199】窗口外那格"走不到"时，**同一格一天最多**朝它开几次路（复用 `_walk_far_tile`）。
#:
#: 与 `FAR_DRY_OPEN_MAX` 同样的有界理由；开路成功**不等于**收下来了（逐格判据说了算）。
READY_FAR_OPEN_MAX = 2

#: 【task-205】铁匠铺升级链：**每天最多试几次**（升级或取回都算一次）。
#:
#: 为什么要界：升级要跑一趟 Blacksmith（`ensure_location` 可能失败），取回还要等 `daysLeft` 归零；
#: 不设上限就会每天每轮都去试一遍（白跑 + journal 噪声）。一天一次足够 —— 升级本身是
#: 2000g 级的大动作，失败原因（没钱/没锭/条目不在售）当天不会自己变好。
TOOL_UPGRADE_MAX_PER_DAY = 1

#: 【task-205】在途升级期间暂停的阶段（工具不在身上 ⇒ 那些阶段一格都干不成）。
#:
#: 与 `farmwork.UPGRADE_SUSPENDS` 同口径；留一份在这里是为了"没有在途状态也要能读"。
TOOL_UPGRADE_SUSPENDED: dict[str, tuple[str, ...]] = {
    "hoe": ("till_area",),
    "can": ("water_area",),
    "axe": ("clear_area",),
    "pickaxe": ("clear_area",),
}

#: 【task-157】`cause` 里区分"warp 图上根本没路"（Mod 的 `unreachable_no_route`）与一般"够不着"。
#: 判据只看回执/reason 原文；命中 ⇒ `cause="no_route"`，否则 `"unreachable"`。
#: 【task-157】"寻路图上压根没有路线"的 Mod 文案（`unreachable_no_route`）。与一般
#: `unreachable`（"四邻都站不过去"）分开归因：前者开路也没用，后者开路可能有用。
#: ⚠️ 这里**刻意不收**笼统的 `UNREACHABLE_HINTS` 词（如"无法到达"）——那会把普通的
#: "够不着"误判成"无路可走"，归因就假了。
NO_ROUTE_HINTS = ("unreachable_no_route", "no_route", "warp 图上无路")

#: 【task-144】**一个阶段里**最多为"壶空"补几次水。
#:
#: run9c 现场：`water_area` 一次分下去 70 格，而壶只有 40 容量 ⇒ 阶段中途 `need_refill`。
#: 补水是**前置条件**（补完要把这一批原样接着浇），但也要有界：取 2 —— 一次补水通常
#: 能把剩下的做完（`StageResult` 每轮 `max_steps` 有限）；补到第 3 次还空说明这一轮的
#: 目标量本身超出一天的水量，应当如实 `stopped="need_refill"`（`assigned_undone` 计入 unmet），
#: 而不是在补水上把整天烧完。日级另有 `max_refills_per_day` 兜底。
STAGE_REFILL_MAX = 2

#: 【task-102】一天最多发起几次 `buy`（含探测与照清单复购）。
#:
#: run8 day 12/13：`buy` 一共 26 次、成交 0 —— 背包 0 空格，每次都 `no_inventory_space`，
#: 还每次都白开一个 `ShopMenu`（当天 23 次 `modal_dismissed ShopMenu`）。
#: 取 3：够走完"探测 → 照清单复购 → 卖一叠腾格后再买一次"这条最小闭环；
#: 再多就是在同一堵墙上反复撞（当天的结论已经写进 `buy_no_space` journal）。
MAX_BUY_TRIES_PER_DAY = 3

#: 【task-11 模态守卫】**只等、绝不 dismiss** 的模态：新一天的自动存档。
#: 真机实测（Lead 2026-10-11 22:2x）：`SaveGameMenu` 自己约 30s 走完 ⇒ `isModal=false`、
#: `worldAdvancing=true`、存档 mtime/size 更新；dismiss 可能**打断存档**，所以只轮询不关。
MODAL_WAIT_ONLY = ("SaveGameMenu", "NewDaySavingMenu")

#: 等待型模态的自走完上限（秒）。真机约 30s，给 3 倍余量；超时就如实停下等人（见下文）。
MODAL_WAIT_TIMEOUT_S = 90.0

#: 一次日循环里最多关几个模态：多个技能同时升级会**连出** `LevelUpMenu`（实测可连出多个）。
MODAL_MAX_DISMISS = 10

#: `dismiss_modal` 的默认时间预算（毫秒）——普通短模态。
MODAL_DISMISS_DEFAULT_MS = 5000

#: 按模态类型给出的 `dismiss_modal` 预算（毫秒）。
#:
#: 【task-129】`ShippingMenu` 是硬例外的**长活**：Mod 侧不能关它（关掉 = 日切保存永久丢失，
#: run9 就这么丢了 4 天盘），只能反射它自己的 `okClicked()`（等价玩家点 OK）然后**等游戏自己**
#: 走完「出货 → 建 SaveGameMenu → SaveGame.Save() → 换天」，合法地要十几秒。
#: 客户端默认 5s 会把"游戏正在存档"误判成超时 ⇒ 这一类单独放宽到 20s（Mod 侧上限 120s）。
MODAL_DISMISS_BUDGET_MS = {
    "ShippingMenu": 20000,
}

#: 【task-236】跑结束前"末次跨日落盘守卫"最多关几次模态。
#:
#: 0.7.40 A2 冒烟：第 3 次跨日后跑立刻 finish 退出，把**保存推迟的 `ShippingMenu`** 留在
#: 屏幕上没人关 ⇒ 那一次 `NewDay` 的存档从未开始（SMAPI 窗口 `NewDay 3` 而
#: `SaveGame.Save() called` 只有 2，存档停在第 3 天清晨、当天全天只在内存里）。
#: 所以收尾必须把挡着的模态关掉再退；但**只能有界**（3 轮），仍卡就如实记账、不洗白。
CLEANUP_DISMISS_MAX = 3

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

#: 【task-228】事件里**非提问对话**的受控推进（`advance_dialogue`）每天的有界额度。
#:
#: 事件脚本的非提问对话会停在第一句等点击 ⇒ `ui.eventUp=true` + `worldAdvancing=false`，
#: 无人值守时**永久挂住**（真机事故：Clint 送熔炉配方，2026-10-17）。用户已授权
#: "只推进非提问对话、永不替游戏选选项"，所以这条路径要和"事件一律硬停（task-41）"
#: 严格划清：**提问/职业选择 ⇒ 一次都不点**，立刻回到 `event_blocked` 诚实收尾。
#:
#: 一次调用最多推 :data:`EVENT_ADVANCE_MAX_STEPS` 步（与 Mod 侧 `maxSteps` 的 1..10 同口径），
#: 每天累计最多 :data:`EVENT_ADVANCE_DAY_STEPS` 步；`stalled`（点了没世界变化）
#: 连续 :data:`EVENT_STALL_GIVE_UP` 次 ⇒ 停止推进（可能是事件脚本的 `pause`/等玩家）。
#: 步长取小（10）是刻意的：每轮只推一小段就重新观测，提问/职业选择一出现就立刻停手。
EVENT_ADVANCE_MAX_STEPS = 10
EVENT_ADVANCE_DAY_STEPS = 60
EVENT_STALL_GIVE_UP = 2
EVENT_ADVANCE_TIMEOUT_MS = 60000

#: 【task-245】`eventUp=true` 但**没有可推进的对话盒**时的有界等待：4 × 15s ≈ 60s。
#:
#: 为什么需要它（0.7.42 冒烟冬 7 开局，`docs/_smoke-0742.md`）：开局事件刚切进来时
#: `ui.eventUp=true` 但 `DialogueBox` 还没开（脚本在跑开场动画/等 pause），旧政策立刻
#: `event_blocked` ⇒ 整条长跑 4.92 分钟白收尾，A″/B″ 一个臂就这么烧掉。
#:
#: 边界（task-41 不回归）：
#:   * 等待期间**绝不** dismiss / sleep / load_save（一次都不动手）；
#:   * 每轮重新观测：事件自己结束 ⇒ 回日循环继续干活；对话盒出现 ⇒ 交回 task-228 的受控推进；
#:   * 等满 `total_limit`(=`EVENT_WAIT_TRIES`+`EVENT_WAIT_EXTRA_TRIES`) 仍 `eventUp` ⇒ 才
#:     `event_blocked`（带上 `eventId`/等了几轮/世界序号）；**无对话框冻结态不再提前判死**
#:     （skippable 过场 worldSeq/eventCommand/dialogueLines 全冻是正常态，见
#:     【devcoder-spring1-event / Fix A】）。
EVENT_WAIT_TRIES = 4
EVENT_WAIT_SECONDS = 15.0

#: 【devcoder-spring1-event / Fix A】`eventUp=true` 且**没有对话盒**时的**耐心延长**（真机 A9 spring 1，
#: `eventId=63` = Kent 归来，纯自动过场）：基础 `EVENT_WAIT_TRIES`×`EVENT_WAIT_SECONDS`≈60s 用尽后
#: 事件仍在跑 ⇒ 旧行为按"指纹冻结=卡死"直接 `blocked_event` 收工，但 A9 实证**推翻**了该假设——
#: skippable 过场（command 6=pause/动画/视口自播）三合一指纹 worldSeq+eventCommand+dialogueLines
#: **全冻是正常态**，结束条件=计时到/动画播完、**不需玩家动作**。所以：
#:   * 无对话框冻结态**不再提前判死**：给足整段等待窗，跑到 `total_limit`=
#:     `EVENT_WAIT_TRIES`+`EVENT_WAIT_EXTRA_TRIES` 轮仍 `eventUp` 才诚实 `blocked_event`；
#:   * `EVENT_WAIT_EXTRA_TRIES` 调到 20 ⇒ 总上限 ≈ 60s + 300s = 360s，覆盖更长过场，
#:     但仍是**有界**等待（`total_limit` 始终兜底，绝不无限等）；
#: 边界不变：等待期间**绝不** dismiss / sleep / load_save / 注入按键；对话盒一出现就交回
#: task-228 的受控推进（非提问才点、提问/职业选择一次都不点）。
EVENT_WAIT_EXTRA_TRIES = 20
EVENT_WAIT_IDLE_GIVE_UP = 4


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
#: 【task-168】规模取舍（`reduce_scope`）的两个上界 —— **认输不是免罚额度**：
#: * `SCOPE_SHED_MAX_PER_DAY`：一天最多认输 1 个田区（策略性取舍，不是"每天挑一片放弃"）；
#: * `SCOPE_SHED_MAX_FRACTION`：整个 run 累计认输的格数 ≤ 农场可作业格的 34%
#:   （农场 245 格量级 ⇒ ≈83 格）。超过就记 `scope_shed_refused` 并**如实不认输**
#:   （宁可累垮，也不许用"认输"把规模问题永久洗成达标）。
SCOPE_SHED_MAX_PER_DAY = 1
SCOPE_SHED_MAX_FRACTION = 0.34


#: 【task-15 / 0.7.45】新增的"**有证据**的诚实收工理由"：`day_justified` 只在这些前缀
#: **且日终"当前可执行且可达的待做格"为 0** 时才认（见 `is_justified_end`）。
#: 为什么不能直接并进 `JUSTIFIED_END_REASONS`：那会变成"口号达标" —— 只要写了
#: `resume_exhausted:` 就绿，不看当天还有没有真能干的活（洗白通道）。
HONEST_EXHAUSTED_END_REASONS = ("resume_exhausted",)

#: 【task-28 / 0.7.46 卡 D】`inventory_blocked` 也走"有证据的诚实收工"：0.7.45 冬26 的
#: `inventory_blocked` 是诚实的（背包 0 格、没可卖的叠、也没有可执行待做格），却因为不在
#: 任何白名单里而 `day_justified=False` ⇒ 永远不 VERIFIED。判据必须带四条独立证据（见
#: `LongRun._bag_relief_evidence` 与 `_note_inventory_blocked`），单靠"写了
#: `inventory_blocked` 前缀"**不放行**——那会变成新的洗白通道（卡面 B 段明确禁止）。
HONEST_INVENTORY_END_REASONS = ("inventory_blocked",)


def is_justified_end(ended_by: str, ended_reason: str, *,
                     pending_executable: int | None = None,
                     malformed_tiles: int = 0,
                     gated: int = 0) -> bool:
    """这一天是不是以**正当理由**收工（`day_justified` 的判据，task-32 / task-15 / task-22 / task-28）。

    口径：
    * `ended_by` 必须是 `sleep` 或**【task-28】带证据的 `inventory_blocked`**（后者只有
      `_end_inventory_blocked` 在四门槛全过时才会写）；
    * 【task-22】`malformed_tiles > 0` ⇒ **一律不放行**（fail-closed）：观测 `tiles[]` 里
      出现了**字段残缺**的 tile 记录（只有 `tile`、缺 `kind`/`crop` 等工作种类字段）说明
      "看不见"是**观测坏了**，不是"没有活"；若把它当 unobserved，Mod 字段一改名就能让
      全部格变成 unobserved ⇒ executable=0 ⇒ 每个诚实收工日都洗成 VERIFIED。这条放在白名单
      之前：残缺读数和任何收工理由同时出现都**不许**判正当（缺失≠通过）；
    * 【devcoder-clear-gate】`gated > 0` ⇒ **一律不放行**（fail-closed）：日终快照里还有
      "其余前置条件本来允许、只因满包清障闸而不执行"的清障格 ⇒ 这一天不是"没活可做"，而是
      "活被背包闸住"（`clear_gate`）。同样的道理放在白名单之前：**任何**收工理由与 gated>0
      同时出现都不判正当 —— 这是「`clear_gate` 永不 VERIFIED」的硬闸，绝不许为了绿灯放宽。
      老账本没有 `gated` 键 ⇒ 调用方传默认 0，行为与改动前逐字一致；
    * 前缀在 `JUSTIFIED_END_REASONS`（夜里到点 / 体力见底 / 确实没活）⇒ 正当（与旧实现逐字一致）；
    * 【task-15】前缀在 `HONEST_EXHAUSTED_END_REASONS`（`resume_exhausted`）**且**
      `pending_executable == 0` ⇒ 正当。"换片/回片区/当前观测都拿不出目标"本来就是诚实收工，
      但必须带独立证据：日终"当前可执行且可达"的待做格确实是 0。`pending_executable is None`
      （观测证据不可用）一律按"不确定"处理 ⇒ 不放行（fail-closed，绝不把"没看到"当成"没有"）；
    * 【task-28】前缀在 `HONEST_INVENTORY_END_REASONS`（`inventory_blocked`）**且**
      `ended_by == "inventory_blocked"` **且** `pending_executable == 0` ⇒ 正当（另三条证据
      在 `_note_inventory_blocked` 里已逐条核过：free_slots==0 / relief_exhausted /
      pending_malformed==0）。`stuck` 等其余前缀照旧不放行。
    """
    # 【task-22】残缺 tile 记录 = 观测不可信 ⇒ 无论什么理由都不判"正当"（防洗白）。
    if int(malformed_tiles) > 0:
        return False
    # 【devcoder-clear-gate】还有"只因满包清障闸而不执行"的清障格 ⇒ 这一天不是"没活可做"。
    if int(gated) > 0:
        return False
    if ended_by not in ("sleep", "inventory_blocked"):
        return False
    prefix = str(ended_reason or "").split(":", 1)[0]
    if prefix in JUSTIFIED_END_REASONS:
        return ended_by == "sleep"
    if prefix in HONEST_EXHAUSTED_END_REASONS:
        return (ended_by == "sleep" and pending_executable is not None
                and int(pending_executable) == 0)
    if prefix in HONEST_INVENTORY_END_REASONS:
        return (ended_by == "inventory_blocked" and pending_executable is not None
                and int(pending_executable) == 0)
    return False


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
        if not t.get("crop") and str(t.get("kind") or "") not in CLEARABLE_KINDS + ("dirt",):
            # 【task-218 / 0.7.39 P0-2 第 5 层】这里原来只放 `ACTIONABLE_KINDS + ("dirt")`，
            # 把树/资源堆整类丢出局部简报 ⇒ `counts["blockers"]` 永远不含它们 ⇒ 策略层
            # 看着"没有障碍"、模型也不会提；而 `_stage_tiles` 现在**能**清它们 ⇒ 简报与执行
            # 能力必须同口径：能清的（`CLEARABLE_KINDS`）一律保留计数。
            # 果树/灌木/放置物仍丢弃（它们是 `DEFERRED_KINDS`/`NOT_CLEARABLE_KINDS`，
            # 由 `Brief.deferred_kinds` 的公告承担"如实告知"那一半）。
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
    #: 【task-102】今天是否"0 农场动作就想去睡"（被 `_do_sleep(require_work=True)` 拒绝）：
    #: 这种日子**不推进**游戏日、`verified=false`，如实留痕（run8 day 12：06:20 起床、0 农场
    #: 动作、直接睡到 day 13）。它和 `ended_by="stuck"`+`stuck_flush` 是两条不同的路径。
    slept_without_work: bool = False
    #: 【task-6 / 0.7.44】今天是否**真的睡成功了**（`_do_sleep` 里 `st.ok` 的观测真相）。
    #: 与 `ended_by` **解耦**：stuck 日的有界翻篇（`_stuck_flush`，task-73）确实睡过去了、游戏日
    #: 也 +1，但 `ended_by` 仍保持 `stuck` ⇒ 旧口径 `checks.slept_by_us=ended_by in (sleep,…)`
    #: 会误报 false（A8 冬 9/14 现场：`sleep.ok=true` + `day_after` +1，却 `slept_by_us=false`）。
    #: 新口径：`checks.slept_by_us = rep.slept_ok or ended_by in ("sleep","inventory_blocked")`。
    slept_ok: bool = False
    verified: bool = False
    #: 【task-52】当天判为"走不到"（四邻都站不过去 / 寻路到不了）的**格数**与**逐格坐标**。
    #: 字段名与 `tools\verify-run3.py` 的交叉核对口径逐字对齐（Lead m04925）：
    #: `day_end.unreachable`（int）+ `day_end.unreachable_tiles`（`[[x,y],…]`）。
    #: `unreachable_bound` = `max(5, floor(0.2 × bound_basis))`，`unreachable_exempt` = 真正从
    #: `no_unmet_stages` 里扣掉的格数（≤ bound，且只扣还留在 leftover 里的不可达格）。
    #: 【task-78 NIT-1】上界基数改用它自己的字段 `bound_basis`，`attempted` 仍是原始证据计数。
    unreachable: int = 0
    unreachable_tiles: list[Any] = field(default_factory=list)
    unreachable_bound: int = 0
    unreachable_exempt: int = 0
    #: 【task-63】当天被**游戏拒绝**（`tool_ineffective`/`precondition_failed`）的**格数**与
    #: **逐格坐标**：这些格记 `skipped`+`proven_inert`（不算硬失败、当天封格、次日重试），
    #: 但豁免**有界** —— `refused_bound = max(5, floor(0.2 × bound_basis))`，超界当天照实
    #: `no_hard_failures=false`（防"游戏全拒绝"换个 verified）。
    #: `refused_exempt` = 真正从 `no_unmet_stages` 里扣掉的格数（≤ bound，只扣仍在 leftover 的）。
    #: 与 task-52 的 `unreachable*` 是**两套独立计数**、互不覆盖（各自有界、各自逐格留痕）。
    refused: int = 0
    refused_tiles: list[Any] = field(default_factory=list)
    refused_bound: int = 0
    refused_exempt: int = 0
    #: 【task-78 NIT-1】两套豁免上界的**共同基数** = 当天"发起过动作且**不是** `encircled`"的步数
    #: （`sum(1 for s in all_steps if s.attempted and not s.encircled)`）。
    #: 语义：`attempted` = 发起过的步数（证据）；`bound_basis` = 其中**可能真做成**的步数 ——
    #: 被围住的格既不是"走不到"也不是"干了没成"，不能拿它抬高豁免上界。
    #: 背景（deputy 伪造账本 V5）：800 次 `encircled` 曾把上界抬到 200，让 200 格真不可达被豁免、
    #: 当天 VERIFIED ⇒ 洗白通道。现在从**分母**剔掉（fail-closed：只让豁免更难）。
    bound_basis: int = 0
    #: 【task-68】当天被**围住**（四邻没有"可清 + 自己够得着"的突破口）的格数与逐格坐标。
    #: 【task-78 NIT-2】判据只讲"四邻没有突破口"，**不再断言**是树/桩/大石（四邻可能是 `weed`
    #: 只是站不上去）；逐格证据看 journal `encircled` 的 `kinds`/`tried_open` 与
    #: `encircled_summary.tried_open_steps`。
    #: **与 `unreachable*` / `refused*` 都不同**：这些格既不封格、也不进**不可达**的豁免分子 ——
    #: `checks.unreachable_within_bound` 仍然只数"真·不可达"，所以"一圈树围住"不会污染上界；
    #: 【devcoder-day-end-gates / Fix 1】它们现在有**自己的**一份有界豁免（`encircled_bound`/
    #: `encircled_exempt`，见下），只扣逐格已证被围死、且仍留在如实 shortfall 阶段 undone 里的格。
    #: 它们的用途是给出**证据**（run6 的 42 格"走不到"里有多少其实是"开不了路"）与下一步归因。
    encircled: int = 0
    encircled_tiles: list[Any] = field(default_factory=list)
    #: 【devcoder-day-end-gates / Fix 1】"被围住"的**有界豁免**（与 `unreachable*`/`refused*` 同构、
    #: 但**独立起界**）：`encircled_bound = max(5, floor(0.2 × bound_basis))`，
    #: `encircled_exempt` = 真正从 `no_unmet_stages` 里扣掉的格数。
    #: 为什么需要它（A9 winter 27 实证）：那天 clear_area `assigned=16 / 12 做成 / 4 被围住 /
    #: leftover=0`，这 4 格四邻全被挡死（`_known_enclosed`/`open_way` 已证、逐格 `encircled`
    #: journal 有 kinds），却因为 `leftover=0` ⇒ `encircled_leftover=0` ⇒ 旧公式一格都扣不掉
    #: ⇒ 干得没错的一天判红。现在只扣**已证被围死、且仍在某个"如实 shortfall 阶段"的
    #: `assigned_undone` 里**的格（逐格坐标比对），预过滤的、已经做成的、夜里/体力收工留下的
    #: 一律不扣；防洗白的 `made_any_progress` 合取项照旧（0 成功日不许被豁免洗白）。
    encircled_bound: int = 0
    encircled_exempt: int = 0
    #: 【task-84】当天账本里的"枯死"证据（用户 m11003：死苗还在被浇）：
    #: * `dead_crops` = Mod `farm.deadCrops`（全农场枯死作物格数）= `(格数, 状态 ok|unavailable)`；
    #: * `dry_dead` = Mod `farm.dryDeadCrops`（枯死**且没浇**的格数，0.7.27 新增字段）；
    #: * `gave_up_tiles` = 当天已认输（`far_dry_given_up`）的窗口外干格坐标 —— 它们不再进
    #:   `work_reasons` 的"还有活"，当天以 `gave_up_dry` 如实收尾（`day_justified=false`）。
    #: 旧 Mod / farm 证据不可信时计数回 0 **但状态是 `unavailable`** —— 调用方绝不许把
    #: "不知道"当成"没有"（与 `farm_dry_tiles` 同一条纪律）。
    dead_crops: int = 0
    dead_crops_status: str = "unavailable"
    dry_dead: int = 0
    dry_dead_status: str = "unavailable"
    gave_up_tiles: list[Any] = field(default_factory=list)
    #: 【task-73】这一天是 `stuck`、但**已经睡过去翻篇**了（有界 `MAX_STUCK_FLUSH`/整轮）。
    #: 注意语义：`ended_by` 仍然是 `stuck`、`checks.day_justified=False`、`verified=False`
    #: —— 这一天**如实算失败**，只是"游戏日往前走了一格"，让整轮能继续跑下一天，
    #: 而不是像 run6 那样 19 秒 `no_day_progress` 终止。
    stuck_flushed: bool = False
    #: 【task-134 B】两个**刻意分开**的口径：
    #: * `assigned_undone` = 当天"阶段分下去的格没做完（且不是诚实上限）"的合计 —— 这才是
    #:   `checks["no_unmet_stages"]` 的基数（先扣 `unreachable_exempt`/`refused_exempt`）。
    #: * `plot_pending` = **片区还剩多少格该做没做**（改判据前的 `raw_unmet`，`_leftover` 逐 kind
    #:   求和；数值与改前逐字一致）+ `plot_pending_by_kind` 明细。供守卫/换片/resume 与工具侧对账，
    #:   **不再**直接决定 `no_unmet_stages`（run9b 的假红：分配 12 格做完 12 格、片区还剩 12 格）。
    #: * `deferred_tiles` = 诚实上限（体力/夜里收工/分配额做完后撞 `budget`）留下的片区待办 ——
    #:   只作 info，不算"没做完"。
    assigned_undone: int = 0
    plot_pending: int = 0
    plot_pending_by_kind: dict[str, int] = field(default_factory=dict)
    #: 【task-5 / 0.7.44】`plot_pending` 的**拆分口径**（**只作 info**，不进 `checks`、不做任何豁免）：
    #: `plot_pending_executable` = 当日"每个阶段种类最后一条记录"里**还值得再试**的余格；
    #: `plot_pending_blocked` = 其中已判**物理/判据挡死**的格数（`blocked` ∪ `encircled_day`：
    #: 试过干不动 / 走不到 / 被拒 / 工具不够格 / 被围住）。二者之和恒等于 `plot_pending`
    #: （`leftover` 语义一个字没动）。**诚实优先**：`no_unmet_stages` 仍只看 `assigned_undone`，
    #: 绝不拿这两个数放宽判据 —— 该做没做照旧如实、当天仍可不 VERIFIED。
    plot_pending_executable: int = 0
    plot_pending_blocked: int = 0
    #: 【task-15 / 0.7.45】日终"还有活"的**多口径并列留痕**（只作 info，不改 checks 10 键语义；
    #: `day_justified` 只看 `pending_executable`）：
    #: * `pending_ledger` = **原始账本**口径余格（0.7.44 冒烟 journal 的 `pending=263/217`）；
    #: * `pending_guard` = 守卫口径 `_pending_work()` 的日终读数（ledger − 已判死）；
    #: * `pending_stalled` = 其中被卡 1 换片机制标成"回去看过、拿不出目标"或被围住的格数
    #:   （`resume_stall_tiles` ∪ `encircled_day`；它们不再进守卫"还有活"，但如实留痕）；
    #: * `pending_executable` = 最后一张**户外农场观测**里"看得见 + 确实要做 + 预算/工具允许 +
    #:   站得到边上"的格数；`None` = 观测证据不可用（fail-closed，不放行 `resume_exhausted`）；
    #: * `pending_blocked` = ledger 里今天**已判死**的格数（`blocked` ∪ `encircled_day` ∪
    #:   `resume_stall_tiles`：干不动/走不到/被围住/回去看过拿不出目标）；
    #: * `pending_unobserved` = 其余（不在 `tiles[]`/观测截断/已达标陈旧账本/预算延后/工具不够/
    #:   背包堵/四邻没得站/无法判定）；
    #: * 【task-22】`pending_malformed` = 在 `tiles[]` 里出现、但**缺工作种类字段**的残缺记录
    #:   （只有坐标、没有 `kind`/`crop`）——不并入 unobserved（那是观测坏了，不是没活）；
    #:   >0 ⇒ `day_justified` 必为 false（fail-closed，堵 deputy NIT-1 洗白通道）。
    #: * 【devcoder-clear-gate】`pending_gated` = **只因「满包清障闸」而不执行**的清障类格
    #:   （背包 0 空格 + 腾格手段用尽；weed/twig/stone/grass + 树 + 够格 clump 的其余前置
    #:   条件本来都允许）。它们**不并入 unobserved**（那是"看不见/已陈旧"的谎）；>0 ⇒
    #:   `day_justified` 必为 false（`clear_gate` 永不 VERIFIED）。老账本没有该键 ⇒ 0。
    #: 不变式：`pending_ledger == pending_guard + pending_blocked`；
    #: `pending_guard == pending_executable + pending_unobserved + pending_malformed + pending_gated`
    #: （观测不可用时 executable=guard、其余 0）。
    pending_ledger: int = 0
    pending_guard: int = 0
    pending_stalled: int = 0
    pending_executable: int | None = None
    pending_blocked: int = 0
    pending_unobserved: int = 0
    pending_malformed: int = 0
    pending_gated: int = 0
    #: 【task-27 / 0.7.46】并列只读坐标（有序、各取前 8 条）：`day_end` 逐格对账用。
    #: 只作证据：不参与任何判据，也不新增 journal 事件名。
    pending_executable_tiles: list[Any] = field(default_factory=list)
    pending_stalled_tiles: list[Any] = field(default_factory=list)
    #: 【task-15 / 0.7.45】当天"更早轮 leftover>0、**最后一轮**同种类 leftover==0"的
    #: `stage_midway_leftover` 事件明细（count/tiles/leftover/round/stage）。
    #: 日级判定**不许只看最后一轮**：这些轮次的一手读数在这里并列留痕（只作 info，
    #: 不改 `no_unmet_stages`/`plot_pending` 的既有公式）。
    stage_midway_leftover: list[dict[str, Any]] = field(default_factory=list)
    #: 【task-16 / 0.7.45】背包空格 + "清障掉落被游戏拒收"的日级留痕（**只作 info**：
    #: 不进 checks、不改任何判据 —— 满包清障照常算做成，冬季 clear 不受影响）：
    #: * `free_slots_start/last/min` = 当天第一张/最后一张/最小的**可用**读数；
    #:   口径 = 容量 − 背包非空行数（`farmwork.player_free_slots`），**不是** `inventoryCount` 本身；
    #: * `free_slots_status` = `ok` / `unavailable`（旧桥缺 `inventoryCount` ⇒ 绝不猜 0）；
    #: * `loot_lost_steps` = 清障**清成了**但背包 0 空格、掉落被游戏拒收（`Inventory Full`）的步数；
    #: * `loot_lost_tiles` = 这些步的逐格坐标；`loot_lost_items` = 近似掉落物名（去重，不装精确）。
    free_slots_start: int | None = None
    free_slots_last: int | None = None
    free_slots_min: int | None = None
    free_slots_status: str = "unavailable"
    loot_lost_steps: int = 0
    loot_lost_tiles: list[Any] = field(default_factory=list)
    loot_lost_items: list[str] = field(default_factory=list)
    #: 【task-28 卡 D】`inventory_blocked` 的**证据快照**（只读 info，不进 checks）：
    #: * `relief_exhausted` = 当天是否已证明"腾格手段用尽"（没可卖叠/轮数/叠数到顶）；
    #: * `bag_evidence` = `_bag_relief_evidence()` 原文（free_slots / sellable_above_keep /
    #:   relief_rounds / sold_stacks / exhausted …），供 analyzer/事后复核"凭什么认腾不出"。
    relief_exhausted: bool = False
    bag_evidence: dict[str, Any] = field(default_factory=dict)
    #: 【task-25 rev4 / 0.7.46】Pierre 背包升级（对话购买 12→24 / 2000g）的日级留痕
    #: （**只作 info**：不改 `checks` 10 键、不参与 day_justified；购买失败也算正常一天）：
    #: * `backpack_capacity_before/after` = 当天首次尝试前/尝试后观测到的 `player.inventoryCount`；
    #: * `backpack_upgrade_ok` = **观测差分**成立（钱 −2000 且容量 12→24），不是"回执说成功"；
    #: * `backpack_upgrade_attempts` = 当天真的发出 `talk` 的次数（上界 `BACKPACK_UPGRADE_MAX_ATTEMPTS`）；
    #: * `backpack_upgrade_failures` = 失败码序列（`money_not_deducted`/`capacity_not_changed`/
    #:   `response_not_found`/`money_diff_ambiguous`/`npc_not_found`/`no_action`/…）；
    #: * `backpack_upgrade_skip` = 今天为什么根本没试（`already_upgraded`/`cannot_afford`/…）。
    backpack_capacity_before: int | None = None
    backpack_capacity_after: int | None = None
    backpack_upgrade_ok: bool = False
    backpack_upgrade_attempts: int = 0
    backpack_upgrade_failures: list[str] = field(default_factory=list)
    backpack_upgrade_skip: str = ""
    deferred_tiles: int = 0
    #: 【task-158】当天的**浇水优先体力预算**（`stamina_budget` journal 的同名快照）：
    #: `{max, stamina, live_crops, dry, water_reserve, water_cost_est, path_allowance,
    #:   capacity, basis, deferred_by_budget, deferred}`。
    #: * `basis ∈ {"farm", "conservative"}`：`conservative` = farm 计数不可用 ⇒ 按 fail-closed
    #:   把**现有体力全留**给浇水（宁可早停手）；
    #: * `deferred_by_budget` **只**表示"因为预算而不做"（不是"没活"），**绝不**进 `checks`。
    stamina_budget: dict[str, Any] = field(default_factory=dict)
    #: 【task-161】当天的**阶段体力实测**聚合（`stage -> {actions, stamina_spent, per_action}`）：
    #: 由 `rep.stages` 逐条累加得到（`actions` = 该阶段 `ok` 数；`per_action = spent/actions`，
    #: `actions == 0` ⇒ `null`）。**只用于事后标定 `farmwork.py` 的估算常量**，不进 `checks`、
    #: 不改任何判据；观测缺 `stamina` 的条目不参与求和（`stamina_spent` 为 `null`）。
    stamina_calibration: dict[str, Any] = field(default_factory=dict)
    #: 【task-168】当天**主动认输**的田区（`scope_shed` journal 的同名快照）：
    #: `{zone: {"since_day","tiles","live_crops_at_shed","reason"}}`；`scope_shed_tiles` 是当天
    #: 认输的格数合计。**【task-192】语义 = 日终末态**："日终仍处于认输态多少格"，不是"今天曾经
    #: 认输过多少格" —— 被释放的区在 `_release_zone` 里扣减（`scope_released` 记释放动作；本 run
    #: 累计量在 `<journal>-scope.json` 的 `shed_ever`，34% 上界看它、释放不清）。
    #: **只作 info**：不新增 `checks` 键、不扣 `plot_pending`/`assigned_undone`
    #: （认输格仍算未完成 ⇒ 当天如实不 VERIFIED）。
    scope_shed: dict[str, Any] = field(default_factory=dict)
    scope_shed_tiles: int = 0
    #: 【task-219】当天**每个意图的执行对账**（用户 m18972：大模型的策略不执行必须记录、能找到问题）。
    #: 每条 = `{intent_id, task, requested_tiles, ok_tiles, failed_tiles, unexecuted_tiles,
    #: executed_steps, reasons:{code:count}, source, boundary, area_hint, area?}`；
    #: `intent_id` 全局唯一 `<day>#<seq>`（跨日续跑新开 id）。**不新增 checks 键**
    #: （`tools/verify-run3.py` 的 day_end 白名单不扩，对账归 analyzer，见 0.7.39 P0-5）。
    intent_coverage: list[dict[str, Any]] = field(default_factory=list)
    #: 【task-230 P0-4.5】缺口清单（gaps）的**可判红问题串**：`""` = 无问题。
    #: 为什么必须有：gaps 是"只提示"的证据层，但**写盘失败/坏文件归档失败本身是缺陷**；
    #: 只写一句 notes 等于"缺失当通过"（task-219 被 deputy 点名的 P0-4）。analyzer 按这个
    #: 字段判红（`day_end.gaps_problem` 非空 ⇒ problem），缺失（旧账本）≠ 通过。
    gaps_problem: str = ""

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
            # 【task-63】被游戏拒绝：计数 + 逐格坐标 + 界与实扣（与 `unreachable*` 独立）
            "refused": self.refused,
            "refused_tiles": [list(t) for t in self.refused_tiles],
            "refused_bound": self.refused_bound,
            "refused_exempt": self.refused_exempt,
            # 【task-78 NIT-1】两套豁免上界的共同基数（`attempted` 语义不变，仍是原始证据计数）
            "bound_basis": self.bound_basis,
            # 【task-68】被围住：只报证据（计数 + 坐标），不进任何豁免分子
            "encircled": self.encircled,
            "encircled_tiles": [list(t) for t in self.encircled_tiles],
            # 【devcoder-day-end-gates / Fix 1】被围住的**有界豁免**：界与实扣都要落账
            # （只扣"已证被围死 + 仍在如实 shortfall 阶段 undone 里"的格）
            "encircled_bound": self.encircled_bound,
            "encircled_exempt": self.encircled_exempt,
            # 【task-73】stuck 日是否已翻篇（睡过去了）—— 只作证据；验收口径不变
            "stuck_flushed": self.stuck_flushed,
            # 【task-102】"0 农场动作就想睡"被拒绝（本日不推进、不 VERIFIED）—— 只作证据
            "slept_without_work": self.slept_without_work,
            # 【task-6 / 0.7.44】真实睡眠真相（与 ended_by 解耦；stuck 翻篇日也为 true）
            "slept_ok": self.slept_ok,
            # 【task-84】枯死作物证据：farm 级计数（**带状态**：0 只代表"没有"当且仅当 ok）
            # + 当天已认输（够不着）的干格坐标。`watered_outdoor`/`final_water.dry` 只按活苗算。
            "dead_crops": self.dead_crops,
            "dead_crops_status": self.dead_crops_status,
            "dry_dead": self.dry_dead,
            "dry_dead_status": self.dry_dead_status,
            "gave_up_tiles": [list(t) for t in self.gave_up_tiles],
            # 【task-134 B】"阶段分下去的格没做完"（no_unmet_stages 的基数）与"片区还剩多少格"
            # （改判据前的 raw_unmet 口径，逐字保留）**分开落账**；诚实上限留下的片区待办
            # 只记 `deferred_tiles`(info)。
            "assigned_undone": self.assigned_undone,
            "plot_pending": self.plot_pending,
            "plot_pending_by_kind": dict(self.plot_pending_by_kind),
            # 【task-5 / 0.7.44】可执行余格 vs 物理挡死格（只 info；和恒等于 plot_pending）
            "plot_pending_executable": self.plot_pending_executable,
            "plot_pending_blocked": self.plot_pending_blocked,
            # 【task-15 / 0.7.45】守卫 pending / 已标记停滞 / 当前观测可执行面（三口径并列；
            # 只作证据，`checks` 仍只有 10 键，语义改动只有 `day_justified` 的"有证据"分支）
            "pending_ledger": self.pending_ledger,
            "pending_guard": self.pending_guard,
            "pending_stalled": self.pending_stalled,
            "pending_executable": self.pending_executable,
            "pending_blocked": self.pending_blocked,
            "pending_unobserved": self.pending_unobserved,
            # 【task-22 / 0.7.45】观测 tiles[] 里字段残缺的记录数（>0 ⇒ day_justified 必 false）
            "pending_malformed": self.pending_malformed,
            # 【devcoder-clear-gate】只因满包清障闸而不执行的清障格数（>0 ⇒ day_justified 必 false；
            # `clear_gate` 收尾永不 VERIFIED。老账本没有该键 ⇒ 缺省 0 = 旧行为）
            "pending_gated": self.pending_gated,
            # 【task-27 / 0.7.46】逐格坐标证据（有序、各前 8 条；只读、不改任何判据）
            "pending_executable_tiles": [list(t) for t in self.pending_executable_tiles],
            "pending_stalled_tiles": [list(t) for t in self.pending_stalled_tiles],
            # 【task-15 / 0.7.45】更早轮 leftover>0 而最后一轮归零的遮蔽证据（日级判定不许只看最后一轮）
            "stage_midway_leftover": [dict(m) for m in self.stage_midway_leftover],
            # 【task-16 / 0.7.45】背包空格 + 清障掉落被拒收的日级留痕（只 info；不进 checks）
            "free_slots_start": self.free_slots_start,
            "free_slots_last": self.free_slots_last,
            "free_slots_min": self.free_slots_min,
            "free_slots_status": self.free_slots_status,
            "loot_lost_steps": self.loot_lost_steps,
            "loot_lost_tiles": [list(t) for t in self.loot_lost_tiles],
            "loot_lost_items": list(self.loot_lost_items),
            # 【task-28 卡 D】`inventory_blocked` 的四门槛证据（只读 info；checks 仍 10 键）
            "relief_exhausted": self.relief_exhausted,
            "bag_evidence": dict(self.bag_evidence),
            # 【task-25 rev4 / 0.7.46】Pierre 背包升级（对话购买）的观测差分留痕（只 info）
            "backpack_capacity_before": self.backpack_capacity_before,
            "backpack_capacity_after": self.backpack_capacity_after,
            "backpack_upgrade_ok": self.backpack_upgrade_ok,
            "backpack_upgrade_attempts": self.backpack_upgrade_attempts,
            "backpack_upgrade_failures": list(self.backpack_upgrade_failures),
            "backpack_upgrade_skip": self.backpack_upgrade_skip,
            "deferred_tiles": self.deferred_tiles,
            # 【task-168】主动认输的片区（只 info：不进 checks、不扣 plot_pending/assigned_undone）
            "scope_shed": dict(self.scope_shed),
            "scope_shed_tiles": self.scope_shed_tiles,
            # 【task-219】意图执行对账（只 info：不进 checks、不做豁免；analyzer 判红）
            "intent_coverage": [dict(it) for it in self.intent_coverage],
            "stamina_budget": dict(self.stamina_budget),
            "stamina_calibration": {k: dict(v) for k, v in self.stamina_calibration.items()},
            # 【task-230 P0-4.5】gaps 的可判红问题串（"" = 无问题；非空 ⇒ analyzer 判 red）。
            "gaps_problem": self.gaps_problem,
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
        backpack_upgrade_enabled: bool = False,
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
        # 【task-35 / 0.7.47 快修】Pierre 背包升级对话购买**默认关闭**。
        # task-34 真机只读探针（commit 4524665）证明 talk 原语本身可用，但**背包升级对话没取到**：
        # 进 SeedShop 会触发过场事件 3102768，相邻 talk 只拿到 "Sigh..."（非提问、无选项）；
        # 0.7.46 的 task-25 路径每天都会在 gate 满足（capacity==12 且 money>=2000）时
        # `goto SeedShop → talk Pierre`，既污染 smoke-0746 / A9 证据，也有过场/卡死风险。
        # ⇒ 默认关闭，只在 day_end 留只读 `backpack_upgrade_skip="disabled"` 与一条 skipped 留痕，
        #   不发任何 goto/talk/buy 请求、不写 checks；显式开启方式见 tools/run-longrun.py
        #   `--enable-backpack-upgrade`（或 AGENTFARM_ENABLE_BACKPACK_UPGRADE=1），开启后行为与
        #   0.7.46 完全一致（每天 ≤2 次失败、≤90s、钱/容量双差分判据）。
        self.backpack_upgrade_enabled = bool(backpack_upgrade_enabled)
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
        # 【task-228】事件对话受控推进的当日账（`_advance_event_dialogue` 读写）：
        #   * `event_advance_steps_today`：今天共推进了几步（跨多次调用累加，硬上限 DAY_STEPS）；
        #   * `event_advance_calls_today`：今天调了几次（只作账本/播报）；
        #   * `event_stall_streak`：连续"点了没世界变化"的次数（碰到真推进就清零）。
        # 三个都在每个游戏日开头重置（见 `_run_day`）。
        self.event_advance_steps_today = 0
        self.event_advance_calls_today = 0
        self.event_stall_streak = 0
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
        # 【task-20】`blocked_by_tool_summary` 每天只发一次：工具不够格的格子**不算活**，
        # 但账本要能看出"农场还剩障碍、为什么却收了工"（逐格另有 `blocked_by_tool`）。
        self.tool_blocked_noted = False
        # 【task-149 C】当天是否**独立证明**过"确实没活可做"：只有 `sleep_guard` 在 farm 证据
        # 齐备（`complete`/`dryCrops`/`hoeDirt`/`emptyDirt` 都能读）且 `work_reasons` 为空时
        # 才置真。日终 checks 用它拦"0 动作却 VERIFIED"的假绿灯（run9c summer 20：22.81 秒、
        # `ok_steps=0`、只有室内窗口读数，却 `verified=true`）。
        self.no_work_evidence_ok = False
        # 【task-149 B】当天开工时**没能**站到户外农场（晨间模态挡住 + 清框重试也不成）：
        # 这一天玩家窗口是室内的，窗口读数不能当作"地里没活"的证据 ⇒ 守卫不许放行 `no_work`
        # （run9c summer 20 就是这条缺失：06:10、体力 270、全天 0 动作，却自称 `no_work` 并
        # `verified=true`）。
        self.day_start_off_farm = False
        # 【task-158】当天的**浇水优先体力预算**：`_stamina_budget()` 在每天第一次拿到观测后
        # 算一次并缓存到这里（`_stage_tiles`/`_budget_gate` 都读它），日终落
        # `day_end.stamina_budget`。`budget_noted` 保证 `stamina_budget` journal 一天只发一条。
        self.budget_today: dict[str, Any] = {}
        # 【task-6 / 0.7.44】当天"只因预算延后"的 `deferred_by_budget` 事件**排队**：
        # 日终拿到浇水证据后才决定落不落（「只因预算延后」与「户外浇水达标」不得同真，见
        # `_flush_budget_deferrals`）。不立即 `_journal` 是为了绝不产生自相矛盾的账本组合。
        self.budget_defer_events: list[dict[str, Any]] = []
        self.budget_noted = False
        #: 【task-163】当天**因体力预算被显式延后**的任务 → 当时没做完的格子。
        #: 用途只有两个：①守卫（`work_reasons`/`_pending_work`）不许再把它们算成"还有活"；
        #: ②日终按任务分类留痕（`budget_deferred_tiles{task: n}`，info）。
        #: **绝不**参与 `checks`/`assigned_undone` 的任何扣减（延后 ≠ 洗白，卡面红线②）。
        self.budget_deferred_tiles: dict[str, list[tuple[int, int]]] = {}
        #: 【task-163 NIT-2】容量上限已留痕的任务（一天每类只发一条 `stage_capped_by_capacity`）。
        self.capacity_capped_noted: set[str] = set()
        # ---- 【task-168】规模取舍（认输片区）----
        #: 跨日**粘住**的认输记录 `{zone: {"since_day","tiles","live_crops_at_shed","reason"}}`。
        #: 读自 `<journal>-scope.json`、写回同一份；同 run 内粘住，换 run 不继承（与教训库同纪律）。
        self.shed_zones: dict[str, dict[str, Any]] = {}
        #: 认输区里"放弃时点"的格坐标 → 目标池/守卫按它剔除（不靠重算窗口，防窗口漂移）。
        self.shed_zone_tiles: dict[str, set[tuple[int, int]]] = {}
        #: 【task-192】**本 run 曾经**认输过的每区格数（区被释放也**不**清、每日**不**重置）
        #: —— 34% 累计上界的真正依据。只看 `shed_zones`（当前认输集）的话，
        #: "认输 → 释放 → 再认输"就能把上界洗回 0，等于给自己发永久免罚额度。
        #: 随 `<journal>-scope.json` 的 `shed_ever` 持久化，换 run 不继承（与教训库同纪律）。
        self.shed_ever_tiles: dict[str, int] = {}
        self.scope_loaded = False
        #: 当天是否已认输过一个区 / 当天认输的格数 / 当天是否已因超上界被拒（journal 去重）。
        self.scope_shed_today = False
        self.scope_shed_tiles_today = 0
        self.scope_cap_refused_today = False
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
        # 【task-5 / 0.7.44】本日每格"被分配进阶段、但没有产出（未做成/未按规跳过）"的次数。
        # 兜底不变量：到 `MAX_ALLOC_NO_PROGRESS` 后当天不再选它（逐格 journal `blocked`）。
        # 与 `tile_attempts` 刻意分开：`tile_attempts` 只数"发起过且有代价"的失败/无结论，
        # 而本计数连"分配了、执行层却一个 step 都没回"的 1 格阶段也能界住。
        self.alloc_no_progress: dict[tuple[int, int], int] = {}
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
        # 【task-58】会话内的**决策史**：每次真实的边界决策（`llm_called`）+ 当天结局，
        # 由 `planner.decision_line()` 拍成一行无坐标的摘要，喂回下一次提示词。
        # ⚠️ 诚实边界：这是「会话内记忆 + 提示词反馈」，**不是**权重更新 / 在线训练；
        # 只影响提示词文本，**绝不**参与任何判定（`verified`/`ended_by`/`checks` 一字不变）。
        # 重启后为空 —— 允许（没有持久层）。
        self.decision_memory: list[str] = []
        # 【task-59】昨晚收工复盘留下的 1–3 条笔记（`BoundaryPlanner.review()` 产出，无坐标）。
        # 夜里回填、次日注入 `Brief.recent_notes`；复盘失败 ⇒ 清空（不拿旧笔记冒充昨晚的复盘）。
        # ⚠️ 与决策史同一条诚实边界：只影响提示词文本，**绝不**参与任何判定。
        self.recent_notes: list[str] = []
        # 【task-59】今天是否已经复盘过（每天**最多一次**独立调用）。
        self.review_done_today = False
        # 【task-82】跨日教训库：路径由 `--journal` **自动推导**（同目录同前缀：
        # `X.jsonl` ⇒ `X-lessons.json`），刻意**不新增** `--lessons` 之类开关。
        # 为什么：run9/run10 的对照实验只许 journal 路径不同；教训是**跨 run** 的记忆，
        # 只能靠这个文件（task-58 的会话内记忆不跨 run）。
        # 内容诚实边界：客观字段由代码从当天账本搬，`hint` 只允许来自收工复盘的笔记；
        # 只喂提示词，绝不参与 `verified`/`ended_by`/`checks`（与 task-58/59 同级）。
        self.lessons_path = self._derive_lessons_path(self.journal_path)
        # 【task-168】规模取舍的跨日记录：同样从 `--journal` **自动推导**
        # （`X.jsonl` ⇒ `X-scope.json`），不加命令行开关（run A/B 只许 journal 路径不同）。
        self.scope_path = self._derive_scope_path(self.journal_path)
        # 【task-219】能力缺口清单：同样从 `--journal` 自动推导（`X.jsonl` ⇒ `X-gaps.json`）。
        # brain 只写**本 run** 的聚合；跨 run 聚合由 analyzer 只读做（0.7.39 P0-4）。
        self.gaps_path = self._derive_gaps_path(self.journal_path)
        self.gaps: dict[str, dict[str, Any]] = {}
        self.gaps_loaded = False
        self.gaps_rejected_note = ""
        self.gaps_dirty = False
        # 【task-230 P0-4.5】读盘期的问题串（首次加载可能早于 day report ⇒ 暂存，落盘那天补写）。
        self.gaps_problem_pending = ""
        # 【task-219】意图执行对账（每日重置）：`intent_plans` 是"模型/策略交出来的意图"，
        # `intent_coverage` 是"每个意图最后怎么了" —— 两者按 `intent_id` 对齐。
        self.intent_plans: dict[str, dict[str, Any]] = {}
        self.intent_coverage: list[dict[str, Any]] = []
        self.intent_seq = 0
        self.intent_ids: dict[int, str] = {}
        self.intent_day = ""
        self.lessons: list[dict[str, Any]] = []
        self.lessons_loaded = False
        # 今晚复盘产出的笔记 ⇒ 挂到今天新增的教训上当 `hint`（hint 只许 LLM 写）。
        self.lessons_hints: list[str] = []
        # 【task-136 C】今天有几次"模型自述的 hint 因与证据矛盾被丢掉"（客观计数，随 `lessons`
        # journal 落账；不参与任何判定）。
        self.hint_dropped_today: int = 0
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
        # 【task-63】当天被**游戏拒绝**的格子（`tool_ineffective`/`precondition_failed`）。与
        # `unreachable_day` 同形但**独立**：拒绝格同样记 `proven_inert` 当天封格，而这里累计的是
        # "今天到底有多少格被游戏拒绝" —— 日级豁免按 `refused_bound` 有界，超界照实 `needs_review`。
        # **不跨日**：`_run_day` 每天清空 ⇒ 次日自动重试（例：工具等级够了就能锄了）。
        self.refused_day: set[tuple[int, int]] = set()
        # 【task-68】当天被**围住**的格子（四邻没有"可清 + 自己够得着"的突破口）。
        # 【task-78 NIT-2】不再预设"是树/桩/大石"——四邻可能是 `weed` 只是自己站不上去；
        # 真实 kind 与开路次数逐格记在 journal `encircled`（`kinds`/`tried_open`）。
        # 与 `unreachable_day` 的区别是**口径**：这些格不是"走不到"，而是"现在还开不了路" ——
        # 所以：**不进 `unreachable_exempt` 分子**（`checks.unreachable_within_bound` 仍只数真不可达）、
        # **不写 `self.blocked`**（不封格：开路后/次日可能就可达了），只单独计数 + 逐格 journal。
        # run6 病灶之一：42 格"走不到"里混着"被树石围住"，混在一起既让上界假红、又让 `clear_dead` 永远 0 成功。
        self.encircled_day: set[tuple[int, int]] = set()
        # 【task-68】本日 `frontier_clear`（"所有指定目标都不可达时，也要至少清掉一格可达的可清障格"）
        # 已经用掉的次数。上界 20：不封顶的话，"目标全不可达"的日子会把整天耗在无目的的清障上。
        self.frontier_clears = 0
        # 【task-73】**整轮**（不是每天）已经用掉的"stuck 日翻篇"次数（上界 `MAX_STUCK_FLUSH`）。
        # 刻意不复位：一次卡死睡过去还能算偶发，两次以上就该让人来看，而不是无限"睡过去再撞一次"。
        self.stuck_flushes = 0
        # 本日"为了看没做完的格子而往回走"的**成功**次数上限（防"来回跑"把一天走光）。
        # 【task-26 / 0.7.46】只数真的走成了的；走失败（`walked=False`，四邻不可站/寻路不动）
        # 不该烧掉"还能回去看"的预算 —— 冬27 的 7 格可执行余格就是这么被 7 次失败走路
        # 提前把 `resume_walks` 顶到 10、之后 5 小时再也没法回去看它们。
        self.resume_walks = 0
        # 本日回片区的**尝试**次数（含失败），单独封顶 = `2 * max_plots_per_day`
        # （见 `_resume_walk_available`）：既防"失败重试"无限烧时间，又不再挤掉成功预算。
        self.resume_walk_attempts = 0
        # 【task-27 / 0.7.46】今天被"目标池前置过滤"判成 encircled（挡死）的格：记录证据
        # （tile/stage/zone/kinds/原因），进 `encircled_day`、不计 `rep.unreachable`。
        self._prefiltered_encircled_today: list[dict[str, Any]] = []
        # 【task-4 / 0.7.44】`leftover_targets` 的**片区归属**（记账坐标 → fields 田区名；
        # 观测里没有田区信息时退化成 8×8 空间簇 `@x,y`）。只由 `_step_stage` 在记账时写入，
        # 换片只从这份账本里挑坐标 —— 绝不臆造。冬 7/12/18 的病灶正是"最近的残留格全是
        # 砍树预算耗尽后不可执行的树"，没有片区归属时 `_resume_plot` 每次都走回同一片。
        self.leftover_area: dict[tuple[int, int], str] = {}
        # 今天已经"回去看过、仍然拿不出目标"的账本邻域（只标 `leftover_targets` 里真有的坐标）。
        self.resume_stall_tiles: set[tuple[int, int]] = set()
        # 上一次回片区走的锚点（同一格连续走第二遍 = 该邻域已经看过、没目标 ⇒ 立刻换片）。
        self.resume_last_anchor: tuple[int, int] | None = None
        # 今天换过几次片区（上界 = `max_plots_per_day`，与 `resume_walks` 同量级）。
        self.resume_switches = 0
        # `frontier_clear` 最近一次真清掉的格（坐标来自当前观测；给换片的 journal 证据用）。
        self.frontier_last_tile: tuple[int, int] | None = None
        # 【task-50】窗口外干作物（Mod 的 `farm.dryTiles`）：每格试了几次、哪些已经认输。
        # run5 三天 `farm.dryCrops` 恒剩 1、而每个作业区 `leftover=0` —— 那 1 格在玩家 400 格
        # 观测窗口之外，脑侧连坐标都没有，只能 `no_work` 收工（`day_justified=true` 白拿）。
        self.far_dry_tries: dict[tuple[int, int], int] = {}
        self.far_dry_given_up: set[tuple[int, int]] = set()
        #: 【task-170 ②】今天"试满上限仍没摘下来"的收获格：目标池与守卫都不再算它们，
        #: `_leftover("harvest")` **不排除**（没收到就是没收到，如实留 unmet）。
        self.harvest_gave_up: set[tuple[int, int]] = set()
        #: 【task-133】每格的失败**因由**（`need_refill`/`unreachable`/`no_evidence`/…）：
        #: 收尾文案必须分清因 —— run9b 把"壶空"写成"够不着"，验收就被误导了。
        self.far_dry_causes: dict[tuple[int, int], str] = {}
        #: 【task-133】当天为窗口外浇水补了几次水（上界 `FAR_DRY_REFILL_MAX`）。
        self.far_dry_refills_today = 0
        #: 【task-157】每一格当天朝它开过几次路（上界 `FAR_DRY_OPEN_MAX`）：够不着先开路再试，
        #: 但开路也要有界 —— 否则"四邻都清不动"的格会把整天烧在清障上。
        self.far_dry_opens: dict[tuple[int, int], int] = {}
        #: 【task-104】当天出现过"人在室内 ⇒ 窗口外干作物没去浇"。用来给收尾理由点名
        #: `not_on_farm`（run8 day 12：被晨间 `ShippingMenu` 挡在 FarmHouse，`_water_far_dry`
        #: 照样对窗口外坐标走 6 格 × 2 次全 unreachable ⇒ 6 格当天全进 `given_up`）。
        self.water_far_not_on_farm = False
        # 本日是否已经播报过"旧 Mod 没给 dryTiles 坐标"（一天只提醒一次，不刷屏）。
        self.far_dry_unavailable_noted = False
        #: 【task-199】窗口外熟作物（`farm.readyTiles`）：每格每天最多 `READY_FAR_MAX_TRIES` 次；
        #: 试满仍收不下来 ⇒ `ready_far_given_up`（当天不再试它，逐格 journal `ready_far_blocked`），
        #: 于是守卫不再被"农场口径还有熟作物"钉住（run A′ fall 13 一整天换片地空转的病灶）。
        self.ready_far_tries: dict[tuple[int, int], int] = {}
        self.ready_far_given_up: set[tuple[int, int]] = set()
        #: 【task-199】每一格当天朝它开过几次路（上界 `READY_FAR_OPEN_MAX`；与浇水那套分开记账）。
        self.ready_far_opens: dict[tuple[int, int], int] = {}
        #: 本日是否已经播报过"旧 Mod 没给 readyTiles 坐标"（fail-closed 退回老行为，一天提醒一次）。
        self.ready_far_unavailable_noted = False
        #: 本日是否已经播报过"readyTiles 被上限截断"（截断时坐标不是全部 ⇒ 如实记一次）。
        self.ready_far_truncated_noted = False
        #: 【task-199】每格的失败**因由**（`unreachable`/`no_route`/`not_ready`/`truncated`/…）：
        #: 收尾文案必须分因（task-133 的教训：把"壶空"写成"够不着"会误导验收）。
        self.ready_far_causes: dict[tuple[int, int], str] = {}
        #: 【task-199】当天"人在室内 ⇒ 窗口外熟作物没去收"（一天只试一次回农场，回不去留痕）。
        self.ready_far_not_on_farm = False
        #: 【task-199】当天是否已经播报过"背包堵住 ⇒ 窗口外熟作物先不走去收"（一天一次）。
        self.ready_far_bag_noted = False
        # 【task-67】今天"买不到合适种子"的结论（"" = 还没确认；否则是 `no_seed_for_sale` 或
        # `cannot_afford`）。run6 死锁：夏季买不到硬编码的春季 `472`，而 `work_reasons` 里
        # "没种子但钱够 ⇒ 该去买"这条**永不可满足**的理由把守卫钉死，3 轮零变化 ⇒ 天天 `stuck`。
        # 今天确认买不到 ⇒ 这条理由当天失效（改记 `seed_unavailable_today`），诚实收工。
        # **不跨日**：`_run_day` 每天清空（明天可能上架新种子 / 钱变多）。
        self.seed_dead_today: str = ""
        # 本条 journal 当天只写一次（`work_reasons` 每轮都会被调用）。
        # 注意与 `seed_dead_noted`（`_preconditions` 自己那句 notes 的"已说"标志）分开：
        # `_seed_dead` 会置 `seed_dead_noted`，若共用同一个标志，`work_reasons` 永远没机会留痕。
        self.seed_unavail_noted = False
        self.seed_dead_noted = False
        # 【task-67】最近一次 `buy` 回执带回来的货架清单（`availableItems`）。**跨天保留**：
        # 货架是稳定事实，留着就能直接挑 id 下单，少发注定失败的那一次请求。
        self.shop_offers: list[dict[str, Any]] = []
        # 【task-241】`shop_offers` 是被哪个季节捕获的（"" = 未知/旧桥）。跨季时若与当前
        # 季节不符就丢弃，强制重新探一次当季货架，避免"拿上季残留清单买隔季种子"。
        self.shop_offers_season: str = ""
        # 【task-55】今天是否已经为买种子卖过一次盈余材料（一天只卖一次，防每轮重复出货）。
        # run7 真形态：`seed_gate {seeds:0, money:14}` 出现 5 次、`sell`/`buy` 事件 0 条 ⇒
        # 脑从来没自己挣过钱、也没自己买过种子。这条链的第一步就是"把超 K 的材料换成钱"。
        self.surplus_sold_today = False
        # 【task-55·留痕】今天是否已经记过"钱不够买种子"（`cannot_afford`）。
        # 为什么要这条：run7 的 `buy` 事件 0 条**不是**"买了没买成"，而是 `money 14g < 20g`
        # 在买种子之前就短路了；账本侧看不出"是没钱还是任务失败"。每天只记一次（`_preconditions`
        # 每轮都调），次日清零。
        self.cannot_afford_noted = False
        # 【task-102】经济闭环死锁的每日状态（run8 day 12/13：`buy` 26 次全废、0 农场动作就睡）：
        #  * `buy_attempts_today` —— 今天发过几次 `buy`（上界 `MAX_BUY_TRIES_PER_DAY`）；
        #  * `buy_no_space_today` —— 今天撞过 `no_inventory_space`（背包没空格）⇒ 当天不再重试，
        #    并且守卫**不许**再拿"没种子但钱够 ⇒ 该去买"当理由（那理由今天已证明走不通）；
        #  * `slot_sold_today` —— 今天是否已为"腾格"卖过一叠（一天一次，防每轮重复出货）；
        #  * `farm_actions_today` —— 今天**真的动过农场**的动作数（锄/清/种/浇/收/开路）。
        #    用于 `_do_sleep(require_work=True)`：一天 0 农场动作就睡 = 用睡觉跳过整天的活
        #    （run8 day 12：06:20 起床、0 农场动作、直接睡到 day 13，`day_justified=false`）。
        self.buy_attempts_today = 0
        self.buy_no_space_today = False
        self.buy_no_space_noted = False
        self.slot_sold_today = False
        self.farm_actions_today = 0
        #: 【task-198】"背包满 ⇒ 先腾格再收"的日级收敛状态（每日重置）：
        #:  * `slot_relief_today` —— 今天已经执行了几轮腾格回路（上界 `SLOT_RELIEF_MAX`）；
        #:  * `slot_relief_noted` —— 每个 `need` 数只 journal 一条（防刷屏）；
        #:  * `inventory_blocked_today` —— 今天已经证明"腾不出格子"（没有可卖/可出货的叠）⇒
        #:    守卫不许再拿"还有熟作物"当理由、收尾理由如实写 `inventory_blocked`；
        #:    **它不是 hard failure**（no_slot 不算 failed），但当天也**不许**假 VERIFIED。
        self.slot_relief_today = 0
        self.slot_relief_noted: set[int] = set()
        self.slot_relief_stacks_today = 0
        self.slot_relief_sold: list[dict[str, Any]] = []
        self.inventory_blocked_today = False
        self.inventory_blocked_noted = False
        #: 【task-16 / 0.7.45】背包空格 trace + "清障掉落被游戏拒收"的日级状态（每日重置）：
        #:  * `free_slots_last/min/status` —— 每次观测都算（`_observe_free_slots`），日终进
        #:    `day_end.free_slots_*`；口径 = 容量 − 背包非空行数（**不是** `inventoryCount` 本身）；
        #:  * `loot_lost_*_today` —— 汇总 `StepResult.loot_lost`（清成了但 0 空格 ⇒ 游戏拒收掉落）；
        #:  * `loot_lost_noted` / `slot_pressure_noted` / `buy_full_noted` —— 每天只留痕一次。
        self.free_slots_last: int | None = None
        self.free_slots_min: int | None = None
        self.free_slots_status = "unavailable"
        self.loot_lost_steps_today = 0
        self.loot_lost_tiles_today: list[tuple[int, int]] = []
        self.loot_lost_items_today: list[str] = []
        self.loot_lost_noted = False
        self.slot_pressure_noted = False
        self.buy_full_noted = False
        #: 【task-28 卡 D】`inventory_blocked` 的证据门槛 + 满包清障闸（每日重置）：
        #:  * `bag_evidence_today` —— 最近一次算出的 `_bag_relief_evidence()`（free_slots /
        #:    free_slots_status / sellable_above_keep / relief_rounds / sold_stacks / exhausted），
        #:    日终原样进 `day_end.bag_evidence`（只读 info，不参与 checks）；
        #:  * `bag_relief_exhausted_today` —— 已证明"腾格手段用尽"（没可卖叠 / 轮数或叠数到顶，
        #:    且 free_slots 证据可信）；`free_slots==0` 时用于拦新开的 clear_area；
        #:  * `clear_area_bag_gate_noted` —— 满包清障闸每天只留痕一次（防刷屏）。
        #:  * `bag_gate_reject_noted` —— "证据不足不认"的拒绝留痕每天也只写一次（防每轮刷屏）。
        self.bag_evidence_today: dict[str, Any] = {}
        self.bag_relief_exhausted_today = False
        self.clear_area_bag_gate_noted = False
        self.bag_gate_reject_noted = False
        #: 【task-25 rev4 / 0.7.46】Pierre 背包升级（对话购买）的日级状态（每日重置）：
        #:  * `backpack_attempts_today` —— 今天真的发出 `talk` 的次数（≤ `BACKPACK_UPGRADE_MAX_ATTEMPTS`）；
        #:  * `backpack_ok_today` —— 今天已经买成（成功后再也不试/不重复扣钱）；
        #:  * `backpack_tried_today` —— 今天已经走过一次完整流程（**一天只试一个回合**；
        #:    回合内部最多 2 次 talk：`not_adjacent` 走一步再重试一次）；
        #:  * `backpack_skip_noted` —— "今天为什么没买"（钱不够/talk 不可用）每天只留痕一次。
        self.backpack_attempts_today = 0
        self.backpack_ok_today = False
        self.backpack_tried_today = False
        self.backpack_skip_noted = False
        #: 【task-218】今天砍倒了几棵树 + 预算挡下时"每天只记一次"的 note 标记。
        #: 每日重置；判据见 `_tree_budget_left()`（日上限 + 浇水预备线，绝不为砍树漏浇）。
        self.trees_cleared_today = 0
        self.tree_budget_noted = False
        #: 【task-114 NIT-1】撞上 `no_inventory_space` 那一刻的**真实观测**（空格/种子/钱），
        #: 供当晚教训的 `evidence` 引用 —— 教训里绝不许写死"空格=0"这类常量。
        self.buy_no_space_facts: dict[str, Any] = {}
        #: 【task-122】当天的两种"退化形态"计数（每日重置），供教训库生成
        #: `plot_exhausted` / `stuck_with_leftover`：run9 第一天正是"以 stuck 收尾、
        #: 还有 leftover、failed=0"，当时 8 种 kind 一条都生成不了 ⇒ run A 攒不到教训。
        self.plot_exhausted_today = 0
        self.midway_leftover_today = 0
        #: 【devcoder-no-work-sleep】连续"LLM 意图 + 确定性兜底都无可执行目标、且当日 0 农场
        #: 动作"的轮次计数（每天重置）。达到阈值（3）即证明"确实无活"，直接诚实收工、干净跨日，
        #: 而不是无限循环等到被外部杀掉、或落到 `slept_without_work` 不跨日。
        self._no_work_cycle_count = 0
        #: 【task-124】"同一秒连发换片"的窗口计数（`plot_exhausted` 空转的刹车）。
        self._plot_exhausted_last: float | None = None
        self._plot_exhausted_window = 0
        #: 【task-134 A】"回片区/换作业区"**连续**没产出目标的计数（run9b 2.6 秒 10 次、
        #: 一格动作都没做的刹车）。与上面按墙钟 1 秒归零的窗口不同：这是确定性上界 ——
        #: 只要世界一直没变化就一直累加，一旦真有进展就清零。
        self.no_progress_cycles = 0
        #: 【task-205】钢铁匠铺升级链的日级状态（每日重置）：
        #:  * `tool_upgrade_tried` —— 今天是否已经试过一次（升级/取回都算；上界
        #:    `TOOL_UPGRADE_MAX_PER_DAY`）。失败原因（没钱/没锭/条目不在售）当天不会自己变好；
        #:  * `tool_upgrade_skipped_noted` —— "为什么今天没升级"每天只 journal 一次（防刷屏）。
        self.tool_upgrade_tried = 0
        self.tool_upgrade_skipped_noted = False
        #: 【task-205】升级**做完等取回**期间：`tool_upgrade_blocked_work` 每天一条，
        #: 记"哪些阶段因为工具不在身上而暂停"（不是失败，是如实记账）。
        self.tool_upgrade_blocked_noted = False

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

    @staticmethod
    def _derive_lessons_path(journal_path: Path | None) -> Path | None:
        """【task-82】`logs/run9.jsonl` ⇒ `logs/run9-lessons.json`（教训库放日记旁边）。

        刻意**只**靠 journal 路径推导、不加命令行开关：run9/run10 的对照实验只许
        journal 路径不同，而教训库是唯一**跨 run** 的记忆通道（会话内记忆不跨 run）。
        journal 为 None（一次性 `agentfarm plan`）⇒ 不落库（只在内存里）。
        """
        if journal_path is None:
            return None
        stem = journal_path.name[: -len(journal_path.suffix)] if journal_path.suffix else journal_path.name
        return journal_path.with_name(f"{stem}-lessons.json")

    @staticmethod
    def _derive_scope_path(journal_path: Path | None) -> Path | None:
        """【task-168】`logs/run9.jsonl` ⇒ `logs/run9-scope.json`（认输记录放日记旁边）。

        与教训库同纪律：只靠 journal 路径推导、不加开关；`journal=None` ⇒ 只在内存里
        （一次性 `agentfarm plan` 不需要跨日记忆）。
        """
        if journal_path is None:
            return None
        stem = journal_path.name[: -len(journal_path.suffix)] if journal_path.suffix else journal_path.name
        return journal_path.with_name(f"{stem}-scope.json")

    @staticmethod
    def _derive_gaps_path(journal_path: Path | None) -> Path | None:
        """【task-219】`logs/run10.jsonl` ⇒ `logs/run10-gaps.json`（能力缺口清单放日记旁边）。

        与教训库/认输记录同纪律：只靠 journal 路径推导、不加命令行开关；
        `journal=None` ⇒ 只在内存里。**只写本 run**，跨 run 聚合归 analyzer（0.7.39 P0-4）。
        """
        if journal_path is None:
            return None
        stem = journal_path.name[: -len(journal_path.suffix)] if journal_path.suffix else journal_path.name
        return journal_path.with_name(f"{stem}-gaps.json")

    # ------------------------------------------------ 【task-219】意图执行对账
    def _intent_id(self, intent: Any) -> str:
        """给一个意图对象发一个**当天唯一**的 `intent_id`（`<day>#<seq>`，seq 每日重置）。

        为什么按对象身份缓存：同一个意图对象会被 `_apply_policy`/`_verify_intents` 原样传递，
        用 `id()` 做键能保证"记计划"和"记执行"落在同一个 id 上；确定性/兜底新造的意图在执行时
        才发新号（跨日续跑也是新号，旧号由 analyzer 当 `carried_over` 看，不在 brain 里造新事件）。
        """
        key = id(intent)
        got = self.intent_ids.get(key)
        if got:
            return got
        self.intent_seq += 1
        ident = f"{self.intent_day or 'day'}#{self.intent_seq:02d}"
        self.intent_ids[key] = ident
        return ident

    def _plan_intents(self, decision: Any) -> list[dict[str, Any]]:
        """【task-219】把决策层交出来的意图记成计划（挂到既有 `decision` journal 行的 `plans` 字段）。"""
        plans: list[dict[str, Any]] = []
        for it in list(getattr(decision, "intents", ()) or ()):
            ident = self._intent_id(it)
            plan = {
                "intent_id": ident,
                "task": str(getattr(it, "task", "") or ""),
                "area_hint": str(getattr(it, "area_hint", "") or ""),
                "source": str(getattr(decision, "source", "") or ""),
                "boundary": str(getattr(decision, "boundary", "") or ""),
                "at": round(self.now() - self.started, 2) if self.started else 0.0,
            }
            self.intent_plans[ident] = plan
            plans.append(plan)
        return plans

    def _record_intent(self, intent: Any = None, *, intent_id: str = "", task: str = "",
                       requested_tiles: int = 0, ok_tiles: int = 0, failed_tiles: int = 0,
                       unexecuted_tiles: int = 0, executed_steps: int = 0,
                       reasons: Mapping[str, int] | None = None, area: str = "",
                       evidence: Mapping[str, Any] | None = None,
                       note: str = "") -> dict[str, Any]:
        """【task-219】记一条**执行对账**（`day_end.intent_coverage[]`）。

        不变式（按**瓦片**不按 step）：`requested_tiles == ok_tiles + failed_tiles + unexecuted_tiles`；
        `Σ reasons.count == failed_tiles + unexecuted_tiles`（非 actionless 意图）。
        集外原因码不丢、放 `bad_reasons`（analyzer 判红，见 `docs/_run10-criteria.md` §8.2b）。
        """
        ident = intent_id or (self._intent_id(intent) if intent is not None else "")
        plan = self.intent_plans.get(ident, {})
        task_name = task or str(plan.get("task") or "")
        rec: dict[str, Any] = {
            "intent_id": ident,
            "task": task_name,
            "area_hint": str(plan.get("area_hint") or ""),
            "area": str(area or ""),
            "source": str(plan.get("source") or ""),
            "boundary": str(plan.get("boundary") or ""),
            "requested_tiles": int(max(0, requested_tiles)),
            "ok_tiles": int(max(0, ok_tiles)),
            "failed_tiles": int(max(0, failed_tiles)),
            "unexecuted_tiles": int(max(0, unexecuted_tiles)),
            "executed_steps": int(max(0, executed_steps)),
            "reasons": {str(k): int(v) for k, v in dict(reasons or {}).items()},
            "actionless": task_name in ACTIONLESS_TASKS,
        }
        if note:
            rec["note"] = note
        # 【task-230 P0-3.3】`no_target` 必须带证据（`evidence{stage_tiles_empty, obs_seq|counts}`）；
        # 证据拿不到时调用方要用 `unknown_evidence`（禁止裸用 no_target 冒充"确实没有目标"）。
        if evidence:
            rec["evidence"] = dict(evidence)
        # 【task-219】瓦片口径 vs 意图口径：有瓦片的记录必须满足
        # `Σ reasons.count == failed_tiles + unexecuted_tiles`；被校验取消/被替代/被门闸挡下
        # 的意图**一格都没分下去**（`requested_tiles == 0`），它的原因码是**意图级**的，
        # 用这个布尔位显式区分（analyzer 按位分开核，别把两种口径混在一起算）。
        rec["reasons_are_intent_level"] = bool(rec["reasons"]) and rec["requested_tiles"] == 0
        bad = [c for c in rec["reasons"] if c not in INTENT_REASON_CODES]
        if bad:
            rec["bad_reasons"] = bad
        self.intent_coverage.append(rec)
        return rec

    def _no_target_evidence(self, task: str, obs: Mapping[str, Any],
                            plot: Mapping[str, Any] | None) -> dict[str, Any] | None:
        """【task-230 P0-3.3】给 `no_target` 造**证据包**：`stage_tiles_empty` + 观测序号/计数快照。

        为什么 `no_target` 必须带证据：它是"这一轮**确实**一格目标都没有"的强断言。
        没有证据就写 `no_target` 等于把"我没算出来"洗成"世界没目标"（task-219 被 deputy
        点名的 P0-3 缺口）。所以证据拿不到（没有作业区 / `_stage_tiles` 抛错 / 观测里连
        计数都读不到）⇒ 返回 `None`，调用方**必须**改记 `unknown_evidence`。
        """
        if plot is None:
            return None
        try:
            tiles = self._stage_tiles(task, dict(obs), dict(plot))
        except Exception:  # noqa: BLE001 - 证据不可用不算崩，只是不许说 no_target
            return None
        evidence: dict[str, Any] = {"stage_tiles_empty": len(tiles) == 0}
        seq = obs.get("worldSeq") if isinstance(obs, Mapping) else None
        if isinstance(seq, int) and not isinstance(seq, bool):
            evidence["obs_seq"] = seq
        counts: dict[str, Any] | None = None
        try:
            brief = self._plot_brief(dict(obs), dict(plot))
            counts = dict(brief.counts or {})
        except Exception:  # noqa: BLE001
            counts = None
        if counts is not None:
            evidence["counts"] = counts
        # 序号与计数**一个都没有** ⇒ 证据不可用（不许靠"stage_tiles_empty"单独硬撑）。
        if "obs_seq" not in evidence and counts is None:
            return None
        # 【task-240 ②】`plant_area` 零目标时补一条**可读的**因由（原因码仍是闭合集里的
        # `no_target`，只加 `evidence.why`，不新增原因码/checks 键）：
        # 冬季手上只有 Wheat Seeds×10 ⇒ 当季一格都种不了 ⇒ `seed_out_of_season`。
        if task == "plant_area" and evidence.get("stage_tiles_empty") is True:
            try:
                state = self._seed_season_state(dict(obs))
            except Exception:  # noqa: BLE001 - 取证失败不影响 no_target 本身的证据
                state = None
            if (state is not None and state.get("metadata")
                    and int(state.get("plantable") or 0) <= 0
                    and state.get("out_of_season")):
                evidence["why"] = "seed_out_of_season"
                evidence["season"] = state.get("season")
                evidence["seeds_total"] = state.get("seeds_total")
                evidence["out_of_season"] = list(state.get("out_of_season") or [])
                evidence["seeds_metadata"] = True
        return evidence

    def _non_plot_evidence(self, task: str, obs: Mapping[str, Any]) -> dict[str, Any] | None:
        """【task-233】非片区意图（`ship`/`sell`）的"确实没做成"证据包。

        为什么单独一套：`_no_target_evidence()` 的 schema 是**片区口径**
        （`stage_tiles_empty`），`ship`/`sell` 没有作业区 ⇒ 套不上。按 `docs/_run10-criteria.md`
        §8.2b：证据不可用**禁止裸用 `no_target`**。所以这里给它们自己的 schema：
          * `ship`：`whitelist_count`（今天有格子级证据的可出货 qid 数）+ `free_slots`
            + `inventory_full`（"没有可出货的叠" / "背包满"是可判事实）；
          * 其它非片区任务：没有通用可判证据 ⇒ `None`（调用方必须降级 `unknown_evidence`）。
        只读观测，不改任何判定（原因码只影响"这一轮还要不要做它"）。
        """
        if task != "ship":
            return None
        if not isinstance(obs, Mapping) or not obs:
            return None
        player = FarmWorker.player_of(obs)
        free_slots, status = player_free_slots(player or {})
        if status != "ok":
            return None
        whitelist = sorted(getattr(self.worker, "harvested", None) or {})
        seq = obs.get("worldSeq")
        evidence: dict[str, Any] = {
            "no_sellable_stack": len(whitelist) == 0,
            "whitelist_count": len(whitelist),
            "free_slots": int(free_slots),
            "inventory_full": int(free_slots) <= 0,
        }
        if isinstance(seq, int) and not isinstance(seq, bool):
            evidence["obs_seq"] = seq
        return evidence

    def _record_stage_intent(self, intent: Any, rep: DayReport) -> None:
        """阶段意图：用 `_step_stage` 刚写下的阶段账本填执行对账（唯一数据源，不另算一遍）。"""
        stage = rep.stages[-1] if rep.stages else {}
        self._record_intent(
            intent,
            task=str(stage.get("stage") or ""),
            requested_tiles=int(stage.get("requested_tiles") or 0),
            ok_tiles=int(stage.get("ok_tiles") or 0),
            failed_tiles=int(stage.get("failed_tiles") or 0),
            unexecuted_tiles=int(stage.get("unexecuted_tiles") or 0),
            executed_steps=int(stage.get("attempted") or 0),
            reasons=dict(stage.get("reasons") or {}),
            area=str(stage.get("zone") or ""),
        )

    # ------------------------------------------------ 【task-219】能力缺口清单
    def _gaps_load(self, rep: DayReport | None = None) -> None:
        """懒加载本 run 的缺口清单（只影响提示词；坏文件整份丢弃、不崩、不参与判定）。

        【task-230 P0-4.4/4.5】坏文件**不静默丢**：`load_gaps_file` 会把它改名成
        `<name>.bad.<ts>`（`.bad.` 归档、不覆盖原文件），这里把归档结果与读失败原因一起
        journal（`gaps_load_failed`）并写进 `rep.gaps_problem`（**可判红**：缺失 ≠ 通过）。
        """
        if self.gaps_loaded:
            # 首次加载可能发生在 `rep` 之前（预取提示词）；把待报的问题串补写到当天账本。
            if rep is not None and self.gaps_problem_pending and not rep.gaps_problem:
                rep.gaps_problem = self.gaps_problem_pending
                rep.notes.append(self.gaps_problem_pending)
            return
        self.gaps_loaded = True
        if self.gaps_path is None:
            return
        report: dict[str, Any] = {}
        gaps, err = load_gaps_file(self.gaps_path, report=report)
        archived = str(report.get("archived_to") or "")
        if archived:
            note = (f"旧缺口清单是坏文件，已归档到 {archived}"
                    f"（`.bad.<ts>`；不覆盖、不静默丢弃，只影响提示词）")
            self._journal("gaps_load_failed", path=str(self.gaps_path),
                          error=err or "archived", archived=archived)
            if rep is not None:
                rep.notes.append(note)
        if err:
            msg = f"缺口清单读失败（只影响提示词、不影响判定）：{err}"
            self.gaps_problem_pending = msg
            self.gaps_rejected_note = err
            self._journal("gaps_load_failed", path=str(self.gaps_path), error=err,
                          archived=archived)
            if rep is not None:
                rep.gaps_problem = msg
                rep.notes.append(msg)
            return
        self.gaps = dict(gaps)
        dropped = int(report.get("dropped") or 0)
        if dropped and rep is not None:
            rep.notes.append(f"缺口清单有 {dropped} 条坏记录被丢弃（无害）")

    def _gaps_merge(self, rows: Iterable[tuple[tuple[int, int], str, str, str]],
                    rep: DayReport) -> None:
        """把本阶段的 `(格, 原因码, kind, 需要的工具)` 并进清单（跨日累积、本 run 内持久）。"""
        self._gaps_load(rep)
        day_txt = rep.day_key_text if hasattr(rep, "day_key_text") else (
            f"{rep.day_key[0]} {rep.day_key[1]} {rep.day_key[2]}" if rep.day_key else "")
        changed = False
        for tile, reason, kind, tool in rows:
            key = f"{kind or 'unknown'}|{tool or ''}|{reason}"
            item = self.gaps.get(key)
            if item is None:
                item = {"kind": kind or "unknown", "tool": tool or "", "reason": reason,
                        "count": 0, "first_seen": day_txt, "last_seen": day_txt,
                        "sample_tiles": [], "src": "agentfarm"}
                self.gaps[key] = item
            item["count"] = int(item.get("count") or 0) + 1
            item["last_seen"] = day_txt
            samples = item.setdefault("sample_tiles", [])
            pair = [int(tile[0]), int(tile[1])]
            if pair not in samples and len(samples) < GAPS_SAMPLE_TILES:
                samples.append(pair)
            changed = True
        if changed:
            self.gaps_dirty = True

    def _gaps_flush(self, rep: DayReport) -> None:
        """日终落盘（原子写）。失败**不只记 notes**：journal `gaps_write_failed` + 可判红字段。

        【task-230 P0-4.5】为什么必须可判红：gaps 只影响提示词，但"写盘失败"本身是缺陷；
        只写一句 notes 等于把"缺失"当"通过"（deputy 的 P0-4 就是这条）。所以失败同时：
          * `rep.gaps_problem`（进 `day_end`，analyzer 判红）；
          * journal `gaps_write_failed`（含错误原文）。
        """
        self._gaps_load(rep)
        if self.gaps_path is None:
            return
        if not self.gaps_dirty:
            return
        if len(self.gaps) > GAPS_MAX_ITEMS:
            keep = sorted(self.gaps.values(),
                          key=lambda it: (-int(it.get("count") or 0), str(it.get("last_seen") or "")))
            self.gaps = {f"{it['kind']}|{it['tool']}|{it['reason']}": it for it in keep[:GAPS_MAX_ITEMS]}
        report: dict[str, Any] = {}
        err = save_gaps_file(self.gaps_path, self.gaps, report=report)
        self.gaps_dirty = False
        if err:
            msg = f"缺口清单写失败（只影响提示词，但这是缺陷）：{err}"
            rep.gaps_problem = msg
            rep.notes.append(msg)
            self._journal("gaps_write_failed", path=str(self.gaps_path), error=err)
        else:
            rep.notes.append(f"能力缺口清单已更新（{int(report.get('written') or 0)} 条，"
                             f"只作提示、不进判定）")

    def _gaps_brief_lines(self) -> tuple[str, ...]:
        """【task-219】给 `Brief.recent_gaps` 的 ≤3 条提示（按次数降序；`src` 只认自己的）。"""
        self._gaps_load()
        if not self.gaps:
            return ()
        items = sorted(self.gaps.values(),
                       key=lambda it: (-int(it.get("count") or 0), str(it.get("last_seen") or "")))
        out: list[str] = []
        for it in items[:GAPS_INJECT_MAX]:
            kind = str(it.get("kind") or "?")
            reason = str(it.get("reason") or "?")
            tool = str(it.get("tool") or "")
            need = f"（需要 {tool}）" if tool else ""
            out.append(f"{int(it.get('count') or 0)} 次「{kind}」因{reason}没做成{need}"[:GAPS_TEXT_MAX_CHARS])
        return tuple(out)

    @staticmethod
    def _finalize_reason_for(rep: DayReport) -> str:
        """【task-238】日终兜底：0 步且无原因码的意图该补哪个**闭合原因码**。

        顺序按"当天到底被什么挡住"从具体到笼统；只用于**补原因码**，绝不改
        `executed_steps`/`checks`（§8.2c：回填不是洗白通道）。
        """
        ended = str(rep.ended_by or "")
        reason = str(rep.ended_reason or "")
        if ended == "inventory_blocked":
            return "no_slot"
        if ended == ENDED_BY_MODAL:
            return "blocked_modal"
        if ended == ENDED_BY_EVENT:
            return "gated"
        if ended.startswith("stuck"):
            return "world_stuck"
        if ended in ("bridge_down", "sleep_failed"):
            return "world_stuck"
        if reason.split(":", 1)[0] in ("night", "stamina", "no_work", "no_plot"):
            return "gated"
        return "unknown_evidence"

    def _finish_intent_coverage(self, rep: DayReport) -> None:
        """【task-219】日终收口：**当天计划过**的意图一条都不能少。

        没进执行的（被政策改写/被更具体意图替代/换任务丢掉）在这里补一条对账：`superseded`
        （被替代）或 `gated`（被门闸挡下、当天没有任何动作）。这是"不执行也要有记录"的最后
        一道保险 —— 计划有、对账没有 = 缺陷（analyzer 判红）。
        """
        seen = {str(r.get("intent_id") or "") for r in self.intent_coverage}
        for ident in sorted(self.intent_plans):
            if ident in seen:
                continue
            plan = self.intent_plans.get(ident) or {}
            reason = "superseded" if ident in self.intent_superseded else "gated"
            self._record_intent(intent_id=ident, task=str(plan.get("task") or ""),
                                reasons={reason: 1},
                                note="计划过但没进执行（日终补记，原因见 reason 码）")
        # 【task-238】§8.3 兜底：`executed_steps == 0 && reasons == {}` 的意图必须补一个
        # 闭合原因码（0.7.40 A2 冒烟实证 `missed:intent_no_reason:water_area`：换任务兜底
        # 生成的意图没有 plan 记录、`_step_stage` 又 0 目标 0 步 ⇒ 对账里空着）。
        # 只补原因码 + evidence，不改 `executed_steps`/`checks`/`verified`。
        fallback = self._finalize_reason_for(rep)
        for rec in self.intent_coverage:
            if int(rec.get("executed_steps") or 0) != 0 or rec.get("reasons"):
                continue
            rec["reasons"] = {fallback: 1}
            rec["evidence"] = {"why": "finalize_fallback", "ended_by": str(rep.ended_by or ""),
                               "ended_reason": str(rep.ended_reason or "")[:200]}
            rec["note"] = ("日终兜底回填：0 步且无原因码 ⇒ 按当天收尾原因补 "
                           f"`{fallback}`（只补原因码，不改步数/判定）")
            rec["reasons_are_intent_level"] = int(rec.get("requested_tiles") or 0) == 0
        rep.intent_coverage = [dict(r) for r in self.intent_coverage]

    def _elapsed_minutes(self) -> float:
        return (self.now() - self.started) / 60.0
    def _budget_exhausted(self) -> bool:
        if self.max_minutes > 0 and self._elapsed_minutes() >= self.max_minutes:
            return True
        return self.max_steps > 0 and self._actions >= self.max_steps

    # ---- 【task-168】规模取舍：认输片区的粘性记录 / 池子剔除 ----
    def _scope_load(self) -> None:
        """懒加载跨日认输记录（一次）。读不了/被外部改过 ⇒ 记一笔并当作"没认输过"。

        信任边界同教训库：文件里只有田区名/格数/原因，**绝不让它决定判定**；本方法只负责
        "今天还记得昨天放弃了哪片"。整份不合 schema ⇒ `load_scope_file` 返回 `{}`。
        """
        if self.scope_loaded:
            return
        self.scope_loaded = True
        if self.scope_path is None:
            return
        report: dict[str, Any] = {}
        zones = load_scope_file(self.scope_path, report=report)
        self.shed_zones = dict(zones)
        for name, item in self.shed_zones.items():
            # 【task-168 F-X1】格清单必须**灌回来**：`shed_zone_tiles` 是当天目标池/守卫理由
            # 与累计上界的共同依据。旧写法只 `setdefault(name, set())` ⇒ 重启后每区都是空集，
            # "整 run 累计 ≤ 农场可作业格 34%"立刻归零（deputy 实测：文件自述 50、载入后 0）。
            loaded = {tuple(t) for t in (item.get("tile_list") or ()) if len(tuple(t)) == 2}
            self.shed_zone_tiles[name] = loaded
        # 【task-192】累计量单独灌回：`shed_ever` 记住"曾经认输过"的区（含已释放的），
        # 34% 上界靠它而不是"当前认输集"。旧文件（task-192 之前）没有这个键 ⇒ 用当前认输集
        # 的格数当**下界**兜底（宁可从严；绝不因为缺字段就放宽上界）。
        ever = report.get("shed_ever") if isinstance(report, dict) else None
        if not isinstance(ever, Mapping) or not ever:
            ever = {name: int(item.get("tiles") or 0) for name, item in self.shed_zones.items()}
        for name, count in ever.items():
            key = str(name)
            self.shed_ever_tiles[key] = max(int(self.shed_ever_tiles.get(key) or 0),
                                            max(0, int(count)))
        reason = str(report.get("reason") or "")
        if reason:
            self._journal("scope_rejected", path=str(self.scope_path), reason=reason,
                          note="认输记录整份不可信 ⇒ 本次当作没认输过（可能今天重新评估并如实留痕）")
        loaded_total = sum(len(v) for v in self.shed_zone_tiles.values())
        self._journal("scope_loaded", path=str(self.scope_path), zones=sorted(self.shed_zones),
                      tiles_total=loaded_total,
                      tile_counts={k: len(v) for k, v in sorted(self.shed_zone_tiles.items())},
                      shed_ever_total=sum(int(v) for v in self.shed_ever_tiles.values()),
                      note="跨日粘住的认输片区（只影响目标池/守卫理由，不影响任何 checks）；"
                           "tiles_total 是当前认输集的对账格数、shed_ever_total 是本 run 累计"
                           "（含已释放区，34% 上界看的是它）")

    def _scope_flush(self, rep: DayReport) -> None:
        """把当前认输记录写回 `<journal>-scope.json`（原子写）。失败只留痕，绝不影响当天。"""
        if self.scope_path is None:
            return
        report: dict[str, Any] = {}
        # 【task-168 F-X1】把每区的**格清单**一并落盘：只存计数的话，重启后
        # `shed_zone_tiles` 是空集 ⇒ 当天剔除会失效、累计上界也会归零。
        zones_out: dict[str, dict[str, Any]] = {}
        for name, item in self.shed_zones.items():
            row = dict(item)
            row["tile_list"] = sorted(self.shed_zone_tiles.get(name) or ())
            zones_out[name] = row
        err = save_scope_file(self.scope_path, zones_out,
                              journal_stem=(self.journal_path.stem if self.journal_path else ""),
                              report=report, ever=self.shed_ever_tiles)
        if err:
            self._journal("scope_save_failed", path=str(self.scope_path), error=err,
                          note="认输记录写不进去 ⇒ 只影响跨日记忆，不影响今天的判定")
        else:
            self._journal("scope_saved", path=str(self.scope_path), zones=len(self.shed_zones),
                          written=int(report.get("written") or 0),
                          shed_ever_total=sum(int(v) for v in self.shed_ever_tiles.values()))

    def _shed_tile_set(self) -> set[tuple[int, int]]:
        """所有认输片区里"放弃掉的格子"的并集（目标池/守卫理由按它剔除；`_leftover` 不动）。"""
        out: set[tuple[int, int]] = set()
        for tiles in self.shed_zone_tiles.values():
            out |= set(tiles)
        return out

    def _shed_live_crops(self) -> int:
        """认输记录里"放弃时点的未浇活苗格数"合计（farm 级理由据此扣减）。

        **只在有明确记录时才扣**（`live_crops_at_shed` 是 int）：记不清就用 0（= 不扣）——
        宁可让守卫多说一句"还有活"（人还能去看一眼），也不许凭认输记录把"还有活"抹掉
        （那正是 task-168 对抗验收要打的"scope_shed 变免罚额度"通道）。
        """
        total = 0
        for item in self.shed_zones.values():
            live = item.get("live_crops_at_shed")
            if isinstance(live, int) and not isinstance(live, bool):
                total += max(0, live)
        return total

    def _zone_bounds(self, zone_name: str, obs: dict[str, Any]) -> tuple[int, int, int, int] | None:
        for z in self._zones(obs):
            if str(getattr(z, "name", "")) != zone_name:
                continue
            try:
                x0, y0, x1, y1 = (int(v) for v in tuple(z.bounds))  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - 田区坏了当作看不见
                return None
            return x0, y0, x1, y1
        return None

    def _zone_observed_tiles(self, zone_name: str, obs: dict[str, Any]) -> list[tuple[int, int]]:
        """该区在**当前观测**里看得见、且**值得干活**的格子（作物/可清障/可锄）。

        观测是玩家窗口 ⇒ 人不在那边就一格都看不见（返回空 ⇒ 调用方按"判不了"处理，
        绝不当成"这个区没事了"）。
        """
        bounds = self._zone_bounds(zone_name, obs)
        if bounds is None:
            return []
        x0, y0, x1, y1 = bounds
        tmap = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        out: list[tuple[int, int]] = []
        for (x, y), tv in tmap.items():
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            kind = str(tv.get("kind") or "")
            if tv.get("crop") or kind in ACTIONABLE_KINDS or (x, y) in tillable:
                out.append((x, y))
        return sorted(out)

    def _zone_live_crops(self, zone_name: str, obs: dict[str, Any]) -> int | None:
        """该区观测里"活苗且还没浇"的格数；**该区一格都看不见 ⇒ None（判不了）**。"""
        bounds = self._zone_bounds(zone_name, obs)
        if bounds is None:
            return None
        x0, y0, x1, y1 = bounds
        tmap = FarmWorker.tiles_of(obs)
        seen = 0
        dry = 0
        for (x, y), tv in tmap.items():
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            seen += 1
            if tv.get("crop") and not tv.get("watered") and not tv.get("dead"):
                dry += 1
        return dry if seen > 0 else None

    def _release_scope_if_converged(self, obs: dict[str, Any], rep: DayReport) -> None:
        """【task-168 释放】认输是**粘但可释放**的：条件成立就撤销，让策略重新看得见那片地。

        释放条件（任一）：①该区观测里已经没有未浇活苗（收完了/清掉了）；②**全农场**缺口归零
        （`water_deficit == 0`，体力重新够浇完所有活苗）。
        判不了（该区看不见 / farm 计数不可用）⇒ **不释放**（粘住，fail-closed）。
        """
        if not self.shed_zones:
            return
        try:
            _live, _cap, deficit = self._work_budget_facts(obs)
        except Exception:  # pragma: no cover - 预算算不出来就只按区口径判
            deficit = None
        for name in list(self.shed_zones):
            live = self._zone_live_crops(name, obs)
            reason = ""
            if live == 0:
                reason = "zone_has_no_unwatered_crops"
            elif live is not None and deficit == 0:
                reason = "farm_deficit_zero"
            if not reason:
                continue
            self._release_zone(name, reason, rep, live=live)

    def _release_zone(self, zone_name: str, reason: str, rep: DayReport, *,
                      live: int | None = None) -> None:
        """【task-168 释放 / task-192 记账】撤销一个认输区。

        `day_end.scope_shed_tiles` / `scope_shed` 的语义是**日终末态**（"日终仍处于认输态
        多少格"），不是"今天曾经认输过多少格"：雨天「先认输 → 雨浇好 → 释放 → 其余活做完」
        是诚实日，若末态还挂着 `scope_shed_tiles>0`，`tools/verify-run3.py` 会误判成
        needs_review。所以释放必须把该区**释放时仍持有**的格数从当天记账里扣掉
        （被 `_harvest_zone` 摘掉的格本来就已经不在认输态里，天然不计）。

        `shed_ever_tiles`（本 run 累计）**不**因释放而清 —— 那是 34% 上界的依据，
        否则"认输 → 释放 → 再认输"能无限认输。`scope_released.tiles` 仍按工具侧口径
        = 本次释放的格数（毛），另加 `shed_tiles_remaining` 便于人读。
        """
        item = self.shed_zones.pop(zone_name, {}) or {}
        held = self.shed_zone_tiles.pop(zone_name, set()) or set()
        # 释放量优先用"释放时仍持有的格清单"；旧文件只有计数（没有 tile_list）时退回 `item["tiles"]`。
        tiles = len(held) or int(item.get("tiles") or 0)
        if tiles:
            self.scope_shed_tiles_today = max(0, int(self.scope_shed_tiles_today) - int(tiles))
        rep.scope_shed_tiles = int(self.scope_shed_tiles_today)
        if str(rep.scope_shed.get("zone") or "") == zone_name:
            left = max(0, int(rep.scope_shed.get("tiles") or 0) - int(tiles))
            if left:
                rep.scope_shed["tiles"] = left
                rep.scope_shed["released_tiles"] = (int(rep.scope_shed.get("released_tiles") or 0)
                                                    + int(tiles))
            else:
                rep.scope_shed = {}
        self._journal("scope_released", zone=zone_name, reason=reason, tiles=tiles,
                      live_crops_now=live, shed_tiles_remaining=int(self.scope_shed_tiles_today),
                      note="认输撤销（粘但可释放）⇒ 该区重新进目标池与守卫理由；`tiles` = 本次"
                           "释放格数（工具侧按『毛−释放=净』对账），`shed_tiles_remaining` = 当天"
                           "认输记账余额。`day_end.scope_shed*` 记的是日终末态；本 run 累计量在"
                           "`<journal>-scope.json` 的 `shed_ever`（释放不清 ⇒ 上界不放宽）")
        rep.notes.append(f"撤销认输：{zone_name}（{reason}）")
        self._scope_flush(rep)

    def _harvest_zone(self, zone_name: str, obs: dict[str, Any], rep: DayReport) -> int:
        """认输前**先把该区成熟作物收掉**（收成不能因为"放弃这片"就烂在地里）。

        一轮有界（`max_steps=len(tiles)`）；用 task-181 的 `tile_ready` 口径（游戏真判据），
        目标只挑"该区观测里看得见的可收格"。返回真正发出的请求数（0 ⇒ 没什么可收）。
        """
        tiles = self._zone_observed_tiles(zone_name, obs)
        ripe: list[tuple[int, int]] = []
        tmap = FarmWorker.tiles_of(obs)
        for t in tiles:
            if tile_ready(tmap.get(t) or {}):
                ripe.append(t)
        if not ripe or self.worker is None:
            return 0
        self._journal("scope_harvest", zone=zone_name, tiles=len(ripe),
                      targets=[list(t) for t in ripe[:6]],
                      note="认输前先把该区成熟作物收掉（收成不因放弃而烂掉）")
        try:
            res = self.worker.run_stage("harvest", ripe, min_stamina=self.min_stamina,
                                       max_steps=len(ripe))
        except Exception as exc:  # pragma: no cover - 收不动不该拖垮认输流程
            self._journal("scope_harvest_failed", zone=zone_name,
                          error=f"{type(exc).__name__}: {exc}")
            return 0
        self._actions += len(res.steps)
        self._count_attempts(res.steps)
        self._mark_blocked(obs, self._snap(), res.steps, rep, stage="harvest")
        self._note_harvest_gave_up(res.steps, rep)
        oks = sum(1 for s in res.steps if s.ok)
        rep.notes.append(f"认输前收成：{zone_name} 收下 {oks}/{len(ripe)} 格")
        return len(res.steps)

    def _shed_scope(self, zone_name: str, obs: dict[str, Any], rep: DayReport) -> bool:
        """【task-168】认输一个田区（六步）。返回是否真的认输。

        **防洗白设计**（卡面第 3 条 + 对抗验收三条通道）：
        * 认输格**留在会计里** ⇒ `_leftover` 一字不改 ⇒ `no_unmet_stages` 因为"该区还有未浇
          活苗"而为 false ⇒ 当天**如实不 VERIFIED**；`watered_outdoor` 也照旧挂（作物确实没浇）。
        * 上界双保险：一天 ≤1 个区（`SCOPE_SHED_MAX_PER_DAY`）、累计 ≤ 农场可作业格的 34%
          （`SCOPE_SHED_MAX_FRACTION`）⇒ 不可能是"永久免罚额度"。
        * 仅在 `basis=="farm"` 且 `deficit > 0` 时成立 ⇒ 拿不到 farm 计数时**不认输**。
        """
        live, cap, deficit = self._work_budget_facts(obs)
        if not self._is_farm(obs):
            self._journal("scope_shed_refused", zone=zone_name, reason="not_on_farm",
                          note="人不在户外农场 ⇒ 看不到片区，不许认输")
            return False
        if deficit is None:
            self._journal("scope_shed_refused", zone=zone_name, reason="no_farm_evidence",
                          note="farm 计数不可用（basis=conservative）⇒ 绝不拿『不知道』当免罚")
            return False
        if deficit <= 0:
            self._journal("scope_shed_refused", zone=zone_name, reason="no_deficit",
                          live_crops=live, water_capacity=cap,
                          note="今天浇得完（deficit=0）⇒ 没有认输的理由")
            return False
        if self.scope_shed_today:
            self._journal("scope_shed_refused", zone=zone_name, reason="already_today",
                          limit=SCOPE_SHED_MAX_PER_DAY,
                          note="今天已经认输过一个区（有界：一天最多 1 个）")
            return False
        tiles = self._zone_observed_tiles(zone_name, obs)
        if not tiles:
            self._journal("scope_shed_refused", zone=zone_name, reason="zone_not_visible",
                          note="该区在观测里一格都看不见 ⇒ 判不了，不认输")
            return False
        # 累计上界：农场里"可作业格"总数（观测口径）——拿不到就不认输（宁可不做，也不越界）。
        # 【task-192】`already` 取**本 run 曾经认输过**的累计格数（含已释放的区）：
        # 只看当前认输集的话，"认输 → 释放 → 再认输"能把上界洗回 0（护栏不放宽）。
        farm_workable = len(self._farm_workable_tiles(obs))
        cap_tiles = int(max(0.0, SCOPE_SHED_MAX_FRACTION * farm_workable))
        already = sum(int(v) for v in self.shed_ever_tiles.values())
        if cap_tiles <= 0 or already + len(tiles) > cap_tiles:
            if not self.scope_cap_refused_today:
                self.scope_cap_refused_today = True
                self._journal("scope_shed_refused", zone=zone_name, reason="cap",
                              shed_tiles=already, this_zone=len(tiles),
                              cap_tiles=cap_tiles, farm_workable=farm_workable,
                              note="累计认输格数超过 34% 上界 ⇒ 如实不认输（宁可累垮，也不许"
                                   "把规模问题永久洗成达标）")
            return False
        harvested = self._harvest_zone(zone_name, obs, rep)
        live_zone = self._zone_live_crops(zone_name, obs)
        reason = (f"今天有 {deficit} 格活苗浇不完（最多浇 {cap} 格）⇒ 主动放弃 {zone_name}"
                  f"（策略性取舍，不是够不着；该区仍留在会计里，当天如实不 VERIFIED）")
        self.shed_zones[zone_name] = {
            "since_day": list(FarmWorker.day_key(obs) or ()),
            "tiles": len(tiles),
            "live_crops_at_shed": live_zone,
            "reason": reason,
        }
        self.shed_zone_tiles[zone_name] = set(tiles)
        # 【task-192】累计量：本 run 曾经认输过的格数（释放/每日重置都不清）⇒ 34% 上界不因
        # "认输 → 释放 → 再认输"而放宽（取 `max`：同一区重复认输只记它最大的一次占用）。
        self.shed_ever_tiles[zone_name] = max(int(self.shed_ever_tiles.get(zone_name) or 0),
                                              len(tiles))
        self.scope_shed_today = True
        self.scope_shed_tiles_today += len(tiles)
        # 【task-168】`day_end.scope_shed{zone,tiles,reason}`：只记**今天那一次**认输
        # （跨日粘住的其余区在 `<journal>-scope.json` 与 `scope_loaded` 里，各有单一来源）。
        rep.scope_shed = {"zone": zone_name, "tiles": len(tiles), "reason": reason,
                          "live_crops": live, "water_capacity": cap, "deficit": deficit,
                          "since_day": list(FarmWorker.day_key(obs) or ()),
                          "harvested_steps": harvested}
        rep.scope_shed_tiles = int(self.scope_shed_tiles_today)
        self._journal("scope_shed", zone=zone_name, tiles=len(tiles),
                      live_crops=live, water_capacity=cap, deficit=deficit,
                      target_tiles=len(tiles), harvested_steps=harvested,
                      reason=reason, note="主动认输片区（scope_shed 只作 info、不进 checks；"
                                          "该区格子仍算未完成 ⇒ 当天如实不 VERIFIED）")
        rep.notes.append(f"主动认输 {zone_name}（{len(tiles)} 格）：{reason}")
        self._scope_flush(rep)
        return True

    def _farm_workable_tiles(self, obs: dict[str, Any]) -> set[tuple[int, int]]:
        """观测里"农场可作业格"（作物/可清障/可锄）——累计认输上界的分母。"""
        tmap = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        out: set[tuple[int, int]] = set()
        for t, tv in tmap.items():
            kind = str(tv.get("kind") or "")
            if tv.get("crop") or kind in ACTIONABLE_KINDS or t in tillable:
                out.add(t)
        return out

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
                          bool(v.get("watered")), tile_ready(v)) for t, v in tiles.items())),
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
        if not st.ok and (is_env_blocked(st) or st.code in ENV_BLOCK_STATUSES):
            # 【task-102 B】晨间 `ShippingMenu`（上一夜 sleep 留下的）会把 `goto_farm` 挡成
            # `ui_modal`，而本方法**一天只调一次** ⇒ 玩家整天留在室内（run8 day 12 的形态：
            # 全天 0 农场动作、守卫说还有 6 格干作物、最后 8 秒后收工）。
            # 先清一次残留菜单、再试一次；仍不成才如实记失败（task-104 会接手"人不在农场
            # 就别去浇窗口外干作物"，本卡只保证"能回就回"）。
            # 【task-149 B】判据必须是**环境挡路的属性**而不是 `st.code`：`_location_failed`
            # 把 `code` 统一写成 `"failed"`、只把 Mod 的 status 留在 `env_block` 标记与 reason
            # 里 ⇒ 旧写法 `st.code in ENV_BLOCK_STATUSES` 恒假，run9c summer 20 的晨间
            # `ShippingMenu`（`code=failed`，reason 里才是 `ui_modal`）**整个重试块被跳过**，
            # 账本里连一条 `day_start_retry` 都没有。
            fresh = self._dismiss_stray_menu(obs, rep, where="goto_farm")
            if not self._is_farm(fresh):
                st2 = self.worker.ensure_location(self.farm)
                self._actions += 1
                self._journal("goto_farm", ok=st2.ok, code=st2.code, reason=st2.reason,
                              where="day_start_retry", before=st2.before, after=st2.after,
                              receipt=st2.receipt,
                              after_modal=str(((obs.get("ui") or {}).get("activeMenu")) or ""))
                if st2.ok:
                    self._say(f"  · 清掉残留模态后回到 {self.farm}：{st2.reason}")
                    try:
                        fresh2 = self._snap()
                    except BridgeError as exc:
                        rep.notes.append(f"回到 {self.farm} 之后观测失败：{exc}")
                        self.day_start_off_farm = True
                        return fresh
                    if not self._is_farm(fresh2):
                        self.day_start_off_farm = True
                    return fresh2
                st = st2
        if not st.ok:
            rep.notes.append(f"回不去 {self.farm}：{st.reason}")
            self._say(f"  × 回 {self.farm} 失败：{st.reason}")
            # 【task-149 B】今天开工没能回到户外农场 ⇒ 窗口读数不能当"地里没活"的证据。
            self.day_start_off_farm = True
            return obs
        self._say(f"  · 回到 {self.farm}：{st.reason}")
        try:
            fresh = self._snap()
        except BridgeError as exc:
            rep.notes.append(f"回到 {self.farm} 之后观测失败：{exc}")
            self.day_start_off_farm = True
            return obs
        if not self._is_farm(fresh):
            # 回执说"到了"但观测显示玩家不在户外农场 ⇒ 按"没回到农场"如实处理。
            self.day_start_off_farm = True
        return fresh

    def _zero_action_evidenced(self, rep: DayReport) -> bool:
        """【task-149 C】"0 动作日凭什么算过关"：要么今天真做成过动作，要么手里有
        **独立的"无活可做"证据**（`sleep_guard` 在 farm 证据齐备且 `work_reasons` 为空时
        置的 `no_work_evidence_ok`）。

        run9c summer 20 的反面教材：22.81 秒、`ok_steps=0`、`decision=0`，唯一的"证据"是
        室内窗口 + farm 的 `dry/ripe/dead=0`，地里却有 142 格空耕地、手上还有种子 ⇒
        `verified=true` 是假绿灯。抽成方法是为了能直接单测（不必造一整天）。
        """
        return bool(rep.ok_steps) or self.no_work_evidence_ok

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

        【task-99 ① / task-97 C1】**`dryCrops` 缺失 ⇒ `None`（未知 ≠ 0）**：`dryCrops` 是
        0.7.22（`bacd55a`）才有的字段，而 `watchdog.py:139-148` 的 `mod_version_mismatch`
        只是 `LEVEL_WARN`（不停机）⇒ 任何 `<0.7.22` 的 Mod 都是"`complete=true` +
        `ripeCrops` 有值 + **没有 `dryCrops`**"。旧代码在这时返回 `(0, 0)` ⇒ 守卫拿不到
        "还有干作物"理由、`_water_evidence` 退回窗口口径（窗外那株真·没浇的活苗看不见）
        ⇒ `no_work` + `watered_outdoor=true` + **假 VERIFIED**。`None` 一律只表示
        **证据不可用**，交给 task-96 的 fail-closed 路径（work_reasons 给理由、守卫不放行
        `no_work`，允许诚实 `stuck:` 收尾）。代价（Lead 明示接受）：旧 Mod 下每个在场日
        都会 fail-closed、拿不到 VERIFIED —— 诚实优先，版本不匹配本来就该先升级 Mod。
        """
        farm = obs.get("farm") or {}
        if farm.get("complete") is not True or farm.get("loaded") is False:
            return None                     # 旧 Mod / 未加载（全 0）⇒ 不算证据
        dry = farm.get("dryCrops")
        # 【task-170】熟作物的"游戏口径"计数优先 `readyCrops`（0.7.32+）：`ripeCrops`（裸
        # `fullyGrown`）会把复收冷却/阶段没走完/枯死/采集形态 2 的格算成熟 ⇒ 守卫被摘不到的
        # 作物钉住一整天（run B 实证 `veto sleep 35 / recover 13`、0 成功）。旧 Mod 缺字段时
        # 退回 `ripeCrops`，行为与改前一致（fail-open 只在"新字段缺失"这一种旧版本情形）。
        ripe = farm.get("readyCrops")
        if ripe is None:
            ripe = farm.get("ripeCrops")
        if dry is None:
            # 【task-99 ①】干作物数**未知**（<0.7.22 的 Mod）⇒ 不是 0，是"拿不到证据"。
            return None
        return (int(dry), int(ripe or 0))

    def _farm_scope_work(self, obs: dict[str, Any]) -> tuple[int, int] | None:
        """`farm` 块的"还有活"读数 `(dry, ripe)`；`None` = **拿不到可用证据**。

        【task-96 ①】**人在户外农场时也给值**（0.7.27 之前这里对 `_is_farm(obs)` 直接返回
        `None`）。旧写法把两种完全不同的情形混成同一个 `None`：

        * 人**不在**农场 ⇒ 窗口只覆盖室内（`crops=0`），必须"先回农场再判"（run3 bug B）；
        * 人**在**农场但 `farm` 证据不可用（`complete != true` / `dryCrops is None`）⇒
          必须 **fail-closed**：不许拿窗口的 `crops=0` 当"地里没活"。

        旧代码里 `None` 被消费者当成"没意见" ⇒ 人在农场 + 证据不可用时 `work_reasons()`
        为空、`sleep_guard` 放行 `no_work`、`_water_evidence` 退回窗口口径（`crops==0` ⇒
        `dry==0` ⇒ true）⇒ **假 VERIFIED**（deputy-lead task-92 的 C8b/C8c，正是 run7 那颗
        窗口外没浇的 `[12,30]`）。现在"人不在农场"由调用方用 `self._is_farm(obs)` 自判，
        `None` 只表示**证据不可用**。

        字段口径按 `mod\\AgentFarm.Bridge\\Contracts.cs` 的 `FarmView`：**`dryCrops` 才是
        "干着的作物格数"**，`unwateredCrops` 数的是 `NeedsWatering`（run3 里整天 32→32）。
        """
        return self._farm_totals(obs)

    def _farm_plot_work(self, obs: dict[str, Any]) -> tuple[int, int, int] | None:
        """`farm` 块的**耕地**读数 `(hoeDirt, emptyDirt, seeds)`；`None` = 证据不可用。

        【task-149 A】run9c summer 20（雨天）的 material fail-open：作物被雨浇好 ⇒ farm 级
        `dry/ripe/dead` 全是 0；清晨 `goto_farm` 被晨间 `ShippingMenu` 挡成 `ui_modal` 之后
        **全天 0 动作**（22.81 秒、`ok_steps=0`、`decision=0`）却 `verified=true`。而相邻观测
        是 `hoeDirt=224 / emptyDirt=142`、手上有 2 粒 Wheat Seeds + 465g ⇒ "地里的活干完了"
        根本不成立 —— 缺的就是这条 farm 级来源："还有耕地空着可种/该去种"。

        判据只用 Mod 已经暴露的字段（`mod\\AgentFarm.Bridge\\Contracts.cs` 的 `FarmView`）：
        `hoeDirt`（有耕地的格数）、`emptyDirt`（耕地里没作物的格数）、`complete`/`loaded`。
        **缺失任何一个 ⇒ `None`（未知 ≠ 没有活）**，由 `work_reasons`/`sleep_guard` 走
        fail-closed（task-96/99 的口径：证据不足宁可诚实 `stuck`，绝不许 `no_work`）。
        """
        farm = obs.get("farm") or {}
        if farm.get("complete") is not True or farm.get("loaded") is False:
            return None
        hoe = farm.get("hoeDirt")
        empty = farm.get("emptyDirt")
        if hoe is None or empty is None:
            return None
        seeds, _money, _can_plant = self._seed_outlook(obs)
        return (max(0, int(hoe)), max(0, int(empty)), max(0, int(seeds)))

    def _unfinished_work(self, obs: dict[str, Any]) -> bool:
        """今天是否还有"该干没干"的活 —— task-102 的 `_do_sleep` 拦截判据。

        下列任一成立即为"有活"：

        * `work_reasons(obs)` 非空（守卫口径的"还有活"）；
        * `farm` 口径 `dryCrops > 0` 或 `ripeCrops > 0`（含"人不在农场"的场景）；
        * 今天撞过 `no_inventory_space`（钱够、种子买不进来 ⇒ 卖一叠腾格就是活）。

        为什么**不**用"农场动作 = 0"单独判：真正的空农场（没作物、没目标）本来就应该能睡
        （`no_work` 是诚实收工理由）。要拦的是 run8 day 12 那种"守卫说还有活、却一次没干就睡"
        —— 那是拿睡觉跳过一整天的活。
        """
        if self.work_reasons(obs):
            return True
        totals = self._farm_totals(obs)
        if totals is not None and (totals[0] > 0 or totals[1] > 0):
            return True
        return bool(self.buy_no_space_today)

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

    def _far_dry_give_up_cause(self) -> str:
        """窗口外干格"认输"的因由归类：`need_refill` / `unreachable` / `mixed` / `""`（task-133）。

        为什么要归类：run9b summer 15/16 的 `gave_up_dry` 全被写成"够不着"，其实是
        **壶里没水**（`code=need_refill`，全账本只有 2 次 `refill`、一次都没为这些格补水）。
        错因会直接误导验收（task-133 卡面第 3 条）。
        """
        causes = {self.far_dry_causes.get(t, "") for t in self.far_dry_given_up}
        causes.discard("")
        if not causes:
            return "mixed"
        if causes == {"need_refill"}:
            return "need_refill"
        if causes == {"unreachable"}:
            return "unreachable"
        if causes == {"no_route"}:                      # 【task-157】warp 图上无路，与站不过去分开
            return "no_route"
        if causes == {"no_evidence"}:
            return "no_evidence"
        if causes == {"truncated"}:                     # 【task-157】dryTiles 被截断，另算一类
            return "truncated"
        if causes == {"not_watered"}:
            return "not_watered"
        return "mixed"

    def _far_dry_give_up_cause_text(self) -> str:
        """认输因由的中文短语（收尾文案/守卫理由共用，避免两处口径漂移）。"""
        cause = self._far_dry_give_up_cause()
        if cause == "need_refill":
            return (f"壶里没水、补水也没成（当天补水 {self.far_dry_refills_today}/"
                    f"{FAR_DRY_REFILL_MAX} 次）——**不是「够不着」**")
        if cause == "unreachable":
            return "坐标都够不着（已试有界开路仍站不过去）"
        if cause == "no_route":
            return "寻路图上没有路线（Mod 的 `unreachable_no_route`）——**不是「四邻站不过去」**"
        if cause == "truncated":
            return ("`farm.dryTiles` 被截断（>64 格）⇒ 这一格判不了"
                    "——**不是「够不着」、也不是「没证据」**")
        if cause == "no_evidence":
            return ("缺证据（`farm.dryTiles` 不可用或被截断，判不了这一格）"
                    "——**不是「够不着」**")
        if cause == "not_watered":
            return "走到了也浇了，但该格观测仍没变（回执不算证据）"
        if cause == "mixed":
            return "有的够不着、有的壶里没水（逐格因由见 journal `water_far` 的 code）"
        return "当天没浇成（原因见 journal `water_far`）"

    def _far_dry_where(self, obs: dict[str, Any]) -> str:
        """收尾/守卫文案里的"窗口外那几格在哪"（含坐标；认输的也点名，并**分清因由**）。"""
        outside, status = self._far_dry_outside(obs)
        if status == "unavailable" or not outside:
            return ""
        given = [t for t in outside if t in self.far_dry_given_up]
        mark = ""
        if given and len(given) == len(outside):
            mark = (f"；其中 {len(given)} 格已放弃当天"
                    f"（{self._far_dry_give_up_cause_text()}）")
        elif given:
            mark = (f"；其中一部分已放弃当天"
                    f"（{self._far_dry_give_up_cause_text()}）")
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
            cause = self._far_dry_give_up_cause()
            if cause == "need_refill":
                return (f"农场口径还有 {dry_f} 格干作物{where} ⇒ 想浇但**壶里没水、补水也没成**"
                        "（不是「够不着」；不再重试）")
            if cause == "unreachable":
                return f"农场口径还有 {dry_f} 格干作物{where} ⇒ 想浇但走不到（不再重试）"
            return (f"农场口径还有 {dry_f} 格干作物{where} ⇒ 想浇但没成"
                    f"（{self._far_dry_give_up_cause_text()}；不再重试）")
        return f"农场口径还有 {dry_f} 格干作物（窗口里看不到坐标）"

    def _far_dry_all_given_up(self, obs: dict[str, Any]) -> bool:
        """窗口外的干作物**全部**已认输（`far_dry_given_up`）且坐标可信（task-84 ③）。

        用途：`work_reasons` 不再把"够不着的干格"当"还有活"（否则守卫每轮拒绝收工，
        run7 的 summer 3/5 整天换片地、summer 6 空转 4.5 分钟）；改由 `sleep_guard`
        用 `gave_up_dry` **如实**收尾（不在 `JUSTIFIED_END_REASONS` 里 ⇒ `day_justified=False`
        ⇒ 当天 `verified=false`，绝不洗成 `no_work`/`night`/`stamina`）。
        """
        outside, status = self._far_dry_outside(obs)
        if status == "unavailable" or not outside:
            return False
        return all(t in self.far_dry_given_up for t in outside)

    def _goto_farm_for_water(self, obs: dict[str, Any], rep: DayReport) -> dict[str, Any]:
        """`_water_far_dry` 专用：人在室内时"能回就回"（task-104）。

        与 `_ensure_on_farm` 的区别：①可在**一天中间**再调（后者假设开工前）；
        ②先清残留模态（task-102 的 `ShopMenu`/`ShippingMenu` 形态）再 `ensure_location` 一次；
        ③失败只如实记 notes/journal，**不认输、不扣额度**（额度决策留给调用方）。
        """
        assert self.worker is not None
        fresh = self._dismiss_stray_menu(obs, rep, where="water_far")
        if self._is_farm(fresh):
            return fresh
        st = self.worker.ensure_location(self.farm)
        self._actions += 1
        self._journal("goto_farm", ok=st.ok, code=st.code, reason=st.reason, where="water_far",
                      before=st.before, after=st.after, receipt=st.receipt)
        if not st.ok:
            rep.notes.append(f"窗口外还有干作物，但回不去 {self.farm}：{st.reason}")
            return fresh
        try:
            return self._snap()
        except BridgeError as exc:
            rep.notes.append(f"回到 {self.farm} 之后观测失败：{exc}")
            return fresh

    def _not_on_farm_suffix(self) -> str:
        """收尾理由后缀（task-104）：当天因"人在室内"没浇到窗口外干作物时点名 `not_on_farm`。"""
        if not self.water_far_not_on_farm:
            return ""
        return ("；not_on_farm：人在室内，窗口外干作物这轮没去浇"
                "（不扣该格当日额度、不进 given_up）")

    def _water_far_dry(self, obs: dict[str, Any], rep: DayReport) -> bool:
        """走过去浇一格"窗口外"的干作物（task-50）。返回 `True` = 本轮真动了一次手。

        有界性：每格一天最多 `FAR_DRY_MAX_TRIES` 次（走过 + 浇水算一次）；两次都不成
        就进 `far_dry_given_up`，当天不再试它 —— 于是 `_far_dry_tiles` 会变空、守卫
        仍因 `farm.dryCrops > 0` 不放行 ⇒ `_run_day` 以 `stuck:` 收尾并点名坐标
        （**绝不**是 `no_work`）。

        【task-104】入口先确认人在户外农场（复用 task-102 的"清模态 + 重试一次"）：
        run8 day 12 早晨 `goto_farm` 被晨间 `ShippingMenu` 挡成 `ui_modal`、人留在
        FarmHouse，而这里照样对着窗口外坐标走过去 ⇒ 6 格 × 2 次全 `unreachable`、
        6 格当天全进 `given_up`，喂出"守卫说还有活、但没有任何作业区拿得出目标"。
        人不在农场时：**不扣**该格当日额度、**不认输**，只记
        `water_far_skipped{reason:"not_on_farm"}`，并让收尾理由点名 `not_on_farm`。
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
        if not self._is_farm(obs):
            # 【task-104】有坐标要浇、但人不在户外农场 ⇒ 先试着回去（清模态 + 一次
            # `ensure_location`）；回不去就**不扣额度、不认输**，且**一天只试一次**
            # （否则每轮都发一次注定失败的 `goto_farm`，把账本刷满）。
            if self.water_far_not_on_farm:
                return False
            obs = self._goto_farm_for_water(obs, rep)
            if not self._is_farm(obs):
                self.water_far_not_on_farm = True
                self._journal("water_far_skipped", reason="not_on_farm",
                              tiles=[list(t) for t in far[:6]], count=len(far),
                              where=self._far_dry_where(obs),
                              note="窗口外还有干作物，但人不在户外农场（走过去也够不着）⇒ "
                                   "不消耗该格当日额度、不进 given_up；先回农场再说")
                return False
            far, status = self._far_dry_tiles(obs)
            if not far:
                return False
        pt = FarmWorker.player_tile(obs) or far[0]
        tile = min(far, key=lambda t: (_dist(t, pt), t[1], t[0]))
        self._actions += 1
        before_farm = obs.get("farm") or {}
        before_dry = int(before_farm.get("dryCrops") or 0)
        tiles_before, _before_status = farm_dry_tiles(obs)
        in_tiles_before = tuple(tile) in {tuple(t) for t in tiles_before}

        # 【task-133 ①】壶空是**前置条件**：动手前先补水（一天有界 ≤2 次），
        # run9b 三次 need_refill 一条补水动作都没有就被记成"够不着"。
        left0 = self._water_left_obs(obs)
        if left0 is not None and left0 < 1:
            obs, refilled = self._refill_for_water_far(obs, rep, tile)
            left0 = self._water_left_obs(obs)
            if not refilled or (left0 is not None and left0 < 1):
                # 补不上水 ⇒ 这一格**确实浇不成**（算一次尝试），但**因由是壶空**，不是够不着。
                tries = int(self.far_dry_tries.get(tile, 0)) + 1
                self.far_dry_tries[tile] = tries
                self.far_dry_causes[tile] = "need_refill"
                if tries >= FAR_DRY_MAX_TRIES:
                    self.far_dry_given_up.add(tile)
                self._journal("water_far", tile=list(tile), ok=False, code="need_refill",
                              try_=tries, limit=FAR_DRY_MAX_TRIES, walked=False, watered=False,
                              dry_before=before_dry, dry_after=before_dry, status=status,
                              receipt_ok=None, in_dry_tiles_before=in_tiles_before,
                              cause="need_refill",
                              refills=self.far_dry_refills_today,
                              refill_limit=FAR_DRY_REFILL_MAX,
                              reason="壶里没水，补水也没成 ⇒ 这一格今天浇不上",
                              given_up=bool(tile in self.far_dry_given_up),
                              note="壶空=前置条件问题：先补水再浇；补水失败才认输，"
                                   "**绝不是「够不着」**（task-133）")
                rep.notes.append(f"窗口外干作物 {list(tile)} 没浇成（第 {tries}/"
                                 f"{FAR_DRY_MAX_TRIES} 次）：壶里没水且补水未成"
                                 + ("；不再试这一格" if tile in self.far_dry_given_up else ""))
                return False

        # 【task-157】站不到**不马上认输**：先有界开路（清挡路邻格）再重试同一格。
        # `opened` 是开路证据（逐条 `clear()` 结果），进 journal；开路成功 ≠ 浇上水。
        walked, walk_note, opened = self._walk_far_tile(tile)

        st: StepResult | None = None
        err = ""
        if walked:
            try:
                st = self.worker.water(tile)
            except BridgeError as exc:
                err = str(exc)
            except Exception as exc:                  # pragma: no cover
                err = f"{type(exc).__name__}: {exc}"

        # 【task-133 ①】`water()` 回 `need_refill`（走到半路壶空了）⇒ 补一次水、
        # **重试同一格**；只有重试仍不成才算这一格的一次失败（壶空本身不算）。
        retried_after_refill = False
        if st is not None and st.code == "need_refill":
            obs, refilled = self._refill_for_water_far(obs, rep, tile)
            if refilled:
                retried_after_refill = True
                try:
                    st = self.worker.water(tile)
                    err = ""
                except BridgeError as exc:
                    err, st = str(exc), None
                except Exception as exc:              # pragma: no cover
                    err, st = f"{type(exc).__name__}: {exc}", None

        after_obs = obs
        try:
            after_obs = self._snap()
        except BridgeError:
            pass
        after_tv = (FarmWorker.tiles_of(after_obs) or {}).get(tuple(tile)) or {}
        after_farm = after_obs.get("farm") or {}
        after_dry = int(after_farm.get("dryCrops") or 0)
        watered = bool(after_tv.get("watered"))
        tiles_after, tiles_status = farm_dry_tiles(after_obs)
        in_tiles_after = tuple(tile) in {tuple(t) for t in tiles_after}
        # 【task-133 ②】判据**只认这一格自己的证据**（卡面硬要求）：
        #   ①该格 `watered=true`；或 ②Mod 按格给的 `dryTiles` 坐标里**没有**这一格。
        # **严禁**再用全局 `dryCrops` 差值 —— run9b t=1233.68 的 `[12,30]` 报 `ok=true`
        # 却 `code=need_refill`，是 t=1219.92 别的格 `[59,21]` 浇水的全局差值顶替的。
        if watered:
            ok, evidence = True, "该格观测 watered=true"
        elif tiles_status == "ok" and not in_tiles_after:
            ok, evidence = True, "该格已不在 farm.dryTiles 里（Mod 按格给坐标）"
        elif tiles_status == "truncated":
            ok, evidence = False, ("farm.dryTiles 被截断（>64 格）⇒ 该格不在列表里**不算证据**"
                                   "⇒ 无法判定，不许当成功")
        elif tiles_status == "unavailable":
            ok, evidence = False, "farm.dryTiles 不可用 ⇒ 无法判定这一格（不许当成功）"
        else:
            ok, evidence = False, "该格仍在 farm.dryTiles 里（还干着）"
        code = (st.code if st is not None else ("unreachable" if not walked else "error"))
        receipt_ok = bool(st.ok) if st is not None else None

        # 因由留痕：成功 ⇒ 清掉；失败 ⇒ 归类（收尾文案与守卫理由都读它）。
        # 【task-157】口径分离：`no_route`（warp 图上无路，Mod 的 `unreachable_no_route`）与
        # 一般 `unreachable`（四邻站不过去）不是一回事；`truncated`（dryTiles 被截断）也从
        # `no_evidence` 里拆出来 —— 卡面要求 `cause` 必须显式、不许混。
        if ok:
            self.far_dry_causes.pop(tile, None)
        elif not walked:
            blob = f"{walk_note} {err}"
            self.far_dry_causes[tile] = ("no_route"
                                         if any(h in blob for h in NO_ROUTE_HINTS)
                                         else "unreachable")
        elif code == "need_refill":
            self.far_dry_causes[tile] = "need_refill"
        elif tiles_status == "truncated":
            self.far_dry_causes[tile] = "truncated"
        elif tiles_status == "unavailable":
            self.far_dry_causes[tile] = "no_evidence"
        else:
            self.far_dry_causes[tile] = "not_watered"

        if not ok:
            tries = int(self.far_dry_tries.get(tile, 0)) + 1
            self.far_dry_tries[tile] = tries
            if tries >= FAR_DRY_MAX_TRIES:
                self.far_dry_given_up.add(tile)
        else:
            tries = int(self.far_dry_tries.get(tile, 0)) + 1
            self.far_dry_tries[tile] = tries
        self._journal("water_far", tile=list(tile), ok=ok, code=code, try_=tries,
                      limit=FAR_DRY_MAX_TRIES, walked=bool(walked), watered=watered,
                      dry_before=before_dry, dry_after=after_dry, status=status,
                      receipt_ok=receipt_ok, evidence=evidence,
                      in_dry_tiles_before=in_tiles_before, in_dry_tiles_after=in_tiles_after,
                      dry_tiles_status=tiles_status, cause=self.far_dry_causes.get(tile, ""),
                      refills=self.far_dry_refills_today,
                      retried_after_refill=bool(retried_after_refill),
                      opens=self.far_dry_opens.get(tile, 0),
                      opened_count=len(opened),
                      reason=(st.reason if st is not None else (walk_note or err)),
                      receipt=(st.receipt if st is not None else err),
                      given_up=bool(tile in self.far_dry_given_up),
                      note="窗口外干作物：Mod 的 farm.dryTiles 给了坐标 ⇒ 走过去浇"
                           "（壶空先补水、补水后重试同一格；【task-157】够不着先有界开路再试；"
                           "判据=**该格** watered=true 或该格已不在 dryTiles 里，"
                           "绝不用全局 dryCrops 差值）")
        if not walked and not ok:
            # 【task-157 ②】开路之后仍然站不到 ⇒ 单独留痕（与 `water_far_skipped` 的
            # "人不在农场、没扣额度"完全两回事）。当天照旧如实 `gave_up_dry`：
            # **开路动作不算浇水**，`watered_outdoor` 仍由该格的观测证据决定。
            self._journal("water_far_blocked", tile=list(tile),
                          cause=self.far_dry_causes.get(tile, ""),
                          attempts=tries, limit=FAR_DRY_MAX_TRIES,
                          opens=self.far_dry_opens.get(tile, 0),
                          cleared_tiles=[[int(c.get("neighbour", [0, 0])[0]),
                                          int(c.get("neighbour", [0, 0])[1])]
                                         for c in opened[:8]],
                          cleared_count=len(opened),
                          note="【task-157】有界开路之后仍然站不到这一格 ⇒ 如实记 blocked："
                               "这一格**没浇上水**（开路成功不等于浇上），当天按 gave_up_dry 收尾")
        if ok:
            # 【task-102】浇成一格窗口外的干作物 = 一次真实的农场动作（`_do_sleep` 的
            # "0 动作不许睡"判据看它）。
            self.farm_actions_today += 1
            rep.notes.append(f"浇了窗口外那格干作物 {list(tile)}（第 {tries} 次尝试；"
                             f"{evidence}；farm.dryCrops {before_dry}→{after_dry}）")
            self._say(f"  · 浇窗口外干作物 {list(tile)}：{code}")
        else:
            rep.notes.append(f"窗口外干作物 {list(tile)} 没浇成（第 {tries}/{FAR_DRY_MAX_TRIES} 次，"
                             f"因由 {self.far_dry_causes.get(tile, '未定')}）："
                             f"{walk_note or err or (st.reason if st is not None else code)}；{evidence}"
                             + ("；不再试这一格" if tile in self.far_dry_given_up else ""))
        return True

    def _walk_far_tile(self, tile: tuple[int, int], *, purpose: str = "water"
                       ) -> tuple[bool, str, list[dict[str, Any]]]:
        """走到窗口外那一格旁边；**站不到就先有界开路再重试同一格**（task-157 / task-199）。

        返回 `(walked, note, cleared)`。开路次数**按格**计（`FAR_DRY_OPEN_MAX`/天；
        `task-199` 的收获路用 `READY_FAR_OPEN_MAX`，两套额度**分开记账**，互不偷用），
        每次开路复用 `farmwork.FarmWorker.open_way`（它自己上限 `MAX_OPEN_ACTIONS` 次清障，
        且清完会复核 `stand_next_to`）；清掉的每一格都计入当天农场动作
        （`farm_actions_today`）——那是真动手，不是"没活"。

        忠实性：开路成功 **不等于** 浇上了水/收下来了（调用方的逐格判据说了算）；
        worker 没有 `open_way`（假 worker / 旧实现）时**不假装开了路**，如实写进 note。

        `purpose` 只影响**记账与 journal 事件名**（`water_far_open` / `ready_far_open`），
        走路逻辑本身只有这一份（卡面硬要求：不许造第三套 walker）。
        """
        assert self.worker is not None
        is_ready = purpose != "water"
        opens = self.ready_far_opens if is_ready else self.far_dry_opens
        open_limit = READY_FAR_OPEN_MAX if is_ready else FAR_DRY_OPEN_MAX
        event = "ready_far_open" if is_ready else "water_far_open"
        walked, note = True, ""
        try:
            walked = bool(self.worker.stand_next_to(tile, timeout_ms=30000))
        except BridgeError as exc:
            walked, note = False, f"走过去失败：{exc}"
        except Exception as exc:                      # pragma: no cover - 假 worker 的意外
            walked, note = False, f"走过去异常：{type(exc).__name__}: {exc}"
        if walked:
            return True, note, []

        used = int(opens.get(tile, 0))
        if used >= open_limit:
            return False, (note + f"；当天为这一格开路已用满额度（{used}/{open_limit}）"), []
        opener = getattr(self.worker, "open_way", None)
        if opener is None:
            return False, (note + "；worker 不支持开路（无 open_way）⇒ 不开路，按走不到如实记"), []

        opens[tile] = used + 1
        code, cleared, open_notes = "", [], []
        err = ""
        try:
            code, cleared, open_notes = opener(tile)
        except BridgeError as exc:
            err = f"开路失败：{exc}"
        except Exception as exc:                      # pragma: no cover - 假 worker 的意外
            err = f"开路异常：{type(exc).__name__}: {exc}"
        cleared = list(cleared or [])
        if cleared:
            self._actions += len(cleared)
            self.farm_actions_today += len(cleared)
        self._journal(event, tile=list(tile), code=str(code or ""),
                      attempt=opens[tile], limit=open_limit,
                      cleared_count=len(cleared), cleared=cleared[:8],
                      notes=[str(n)[:120] for n in (open_notes or [])][:6] or ([err] if err else []),
                      note="【task-157/199】窗口外那一格走不到 ⇒ 先清挡路邻格（复用 `open_way`，"
                           "每次 ≤`MAX_OPEN_ACTIONS` 次清障、每格每天有界轮数）再重试同一格；"
                           "开路成功**不等于**浇上了水/收下来了")
        if code == "ok":
            # `open_way` 内部已经复核过 `stand_next_to` 通过 ⇒ 现在站得到这一格旁。
            return True, "开路后已站到目标旁（open_way 内部复核 stand_next_to 通过）", cleared
        # 把 `open_way` 的原始 notes（真实现里带 Mod 的 code/reason）一并带回：否则
        # `no_route` 与普通 `unreachable` 的区别在归因时就丢了（卡面要求两者显式分开）。
        hint = "；".join(str(n)[:120] for n in (open_notes or [])[:4])
        return False, (note + f"；已开路 {len(cleared)} 格仍未通（{code or err or 'unknown'}）"
                       + (f"；{hint}" if hint else "")), cleared

    # ---------------------------------------------------------------- 窗口外熟作物（task-199）

    @staticmethod
    def _ready_far_outside(obs: dict[str, Any]) -> tuple[list[tuple[int, int]], str]:
        """Mod 报了坐标、但**不在玩家观测窗口里**的熟作物格（含已认输的）。

        与 `_ready_far_tiles` 的区别同浇水那套：这里**不过滤** `ready_far_given_up`，
        因为收尾/理由文案必须点名坐标（run A′ fall 13 的 `stuck:` 原文里只有计数、没有坐标，
        验收根本没法查是哪几格）。
        """
        tiles, status = farm_ready_tiles(obs)
        if status == "unavailable":
            return [], status
        visible = FarmWorker.tiles_of(obs)
        return [t for t in tiles if t not in visible], status

    def _ready_far_tiles(self, obs: dict[str, Any]) -> tuple[list[tuple[int, int]], str]:
        """**玩家窗口之外、今天还没认输**的熟作物格（task-199，= 行动口径）。

        返回 `(还没认输的格, 状态)`；状态 `"ok"` / `"truncated"` / `"unavailable"`。
        `"unavailable"`（旧 Mod / 证据不可信）时返回空列表，调用方**绝不许**当成
        "没有窗口外熟作物"——守卫必须退回老行为（fail-closed）。
        """
        outside, status = self._ready_far_outside(obs)
        if status == "unavailable":
            return [], status
        return [t for t in outside if t not in self.ready_far_given_up], status

    def _ready_far_give_up_cause_text(self) -> str:
        """窗口外熟作物"认输"的因由短语（收尾/守卫文案共用，避免两处口径漂移）。"""
        causes = {self.ready_far_causes.get(t, "") for t in self.ready_far_given_up}
        causes.discard("")
        if not causes:
            return "当天没收到（原因见 journal `ready_far`）"
        if causes == {"unreachable"}:
            return "坐标都够不着（已试有界开路仍站不过去）"
        if causes == {"truncated"}:
            return ("`farm.readyTiles` 被截断（>64 格）⇒ 坐标不完整，这一格判不了"
                    "——**不是「够不着」**")
        if causes == {"no_evidence"}:
            return "缺证据（`farm.readyTiles` 不可用，判不了这一格）——**不是「够不着」**"
        if causes == {"not_ready"}:
            return "走到了也没收下来（回执不算证据；逐格判据见 journal `ready_far`）"
        if causes == {"bag_full"}:
            return "背包满 ⇒ 收不进来（先腾格，不是够不着）"
        return "有的够不着、有的收了没成（逐格因由见 journal `ready_far` 的 code）"

    def _ready_far_where(self, obs: dict[str, Any]) -> str:
        """收尾/守卫文案里的"窗口外熟作物在哪"（含坐标；认输的也点名并分清因由）。"""
        outside, status = self._ready_far_outside(obs)
        if status == "unavailable" or not outside:
            return ""
        given = [t for t in outside if t in self.ready_far_given_up]
        mark = ""
        if given and len(given) == len(outside):
            mark = f"；其中 {len(given)} 格已放弃当天（{self._ready_far_give_up_cause_text()}）"
        elif given:
            mark = f"；其中一部分已放弃当天（{self._ready_far_give_up_cause_text()}）"
        return (f"，其中 {len(outside)} 格在玩家窗口之外（Mod 报的坐标 "
                f"{[list(t) for t in outside[:3]]}{mark}）")

    def _ready_far_reason(self, obs: dict[str, Any], ready_f: int) -> str:
        """窗口外熟作物的"还有活"理由（带坐标；给守卫/`work_reasons` 共用）。"""
        far, status = self._ready_far_tiles(obs)
        where = self._ready_far_where(obs)
        if far:
            return f"农场口径还有 {ready_f} 格熟作物{where} ⇒ 先走过去收"
        if status == "unavailable":
            return (f"农场口径还有 {ready_f} 格熟作物，但 farm.readyTiles 不可用（旧 Mod / "
                    "farm 证据不可信）⇒ 不许判「没活」，按老行为继续干（会以 stuck 如实收尾）")
        if where:
            return (f"农场口径还有 {ready_f} 格熟作物{where} ⇒ 想收但没收成"
                    f"（{self._ready_far_give_up_cause_text()}；不再重试）")
        return f"农场口径还有 {ready_f} 格熟作物（窗口里看不到坐标）"

    def _ready_far_all_given_up(self, obs: dict[str, Any]) -> bool:
        """窗口外的熟作物**全部**已认输且坐标可信（task-199）。

        用途：`work_reasons`/`sleep_guard` 不再把"够不着/收不下来的熟格"当"还有活"
        （run A′ fall 13：守卫拿 `farm.readyCrops` 当理由，一整天换片地空转，最后
        `stuck:同一秒连发 5 次换片都没有目标`）。当天改由 `stuck`/`gave_up` 一类理由如实收尾。
        """
        outside, status = self._ready_far_outside(obs)
        if status == "unavailable" or not outside:
            return False
        return all(t in self.ready_far_given_up for t in outside)

    def _harvest_far_ready(self, obs: dict[str, Any], rep: DayReport) -> bool:
        """走过去收一格"窗口外"的熟作物（task-199）。返回 `True` = 本轮真动了一次手。

        有界性：每格一天最多 `READY_FAR_MAX_TRIES` 次；试满就进 `ready_far_given_up` +
        逐格 journal `ready_far_blocked`，当天不再试它 —— 于是 `_ready_far_tiles` 变空，
        守卫不再被"农场口径还有熟作物"钉住（**绝不允许**变成"同一秒连发 5 次换片"的空转）。

        判据：`FarmWorker.harvest()` 自己的四选一观测差分（crop 消失 / ready 翻转 /
        readySource 变化 / 背包逐 qid 新增）；这里**不另立判据**，也不把 Mod 回执当证据。

        `no_slot`（背包满）是**全局阻塞**、不是这一格的错 ⇒ 不消耗该格尝试次数，
        交给 task-198 的日级 `_slot_relief` 回路（腾出格子后下一轮再来）。
        """
        assert self.worker is not None
        far, status = self._ready_far_tiles(obs)
        if not far:
            if status == "unavailable" and not self.ready_far_unavailable_noted:
                farm = obs.get("farm") or {}
                self.ready_far_unavailable_noted = True
                self._journal("ready_far_unavailable", complete=farm.get("complete"),
                              loaded=farm.get("loaded"), readyCrops=farm.get("readyCrops"),
                              note="farm 说还有熟作物，但没有 readyTiles 坐标（旧 Mod / 证据不可信）"
                                   "⇒ fail-closed：不判「没熟作物」、按老行为继续干")
            if status == "truncated" and not self.ready_far_truncated_noted:
                farm = obs.get("farm") or {}
                self.ready_far_truncated_noted = True
                self._journal("ready_far_truncated", readyTilesTruncated=True,
                              readyCrops=farm.get("readyCrops"),
                              note="farm.readyTiles 被 64 条上限截断 ⇒ 坐标不是全部，"
                                   "当天只处理已知坐标；总数以 farm.readyCrops 为准")
            return False
        if not self._is_farm(obs):
            # 人不在户外农场 ⇒ 一天只试着回去一次（复用 task-104 那套"清模态 + ensure_location"），
            # 回不去不扣额度、不认输，只如实留痕（否则每轮都发注定失败的 goto_farm）。
            if self.ready_far_not_on_farm:
                return False
            obs = self._goto_farm_for_water(obs, rep)
            if not self._is_farm(obs):
                self.ready_far_not_on_farm = True
                self._journal("ready_far_skipped", reason="not_on_farm",
                              tiles=[list(t) for t in far[:6]], count=len(far),
                              where=self._ready_far_where(obs),
                              note="窗口外还有熟作物，但人不在户外农场 ⇒ 不消耗该格当日额度、"
                                   "不进 given_up；先回农场再说")
                return False
            far, status = self._ready_far_tiles(obs)
            if not far:
                return False
        pt = FarmWorker.player_tile(obs) or far[0]
        tile = min(far, key=lambda t: (_dist(t, pt), t[1], t[0]))
        # 【task-199 × task-198】背包堵住时**先别走过去**：`no_slot` 是全局阻塞，
        # 收不进来跟这一格无关（走过去只会白跑，还会每轮重复走）。腾格交给日级回路。
        free_slots, bag_need, bag_status = self._bag_state(obs)
        if bag_status == "ok" and bag_need > 0:
            if not self.ready_far_bag_noted:
                self.ready_far_bag_noted = True
                self._journal("ready_far_skipped", reason="bag_full",
                              tiles=[list(t) for t in far[:6]], count=len(far),
                              free_slots=free_slots, reserve=SLOT_RESERVE,
                              note="【task-199】背包将满/已满 ⇒ 窗口外熟作物先不走去收："
                                   "不消耗该格尝试次数、不认输；腾格由日级 `_slot_relief` 负责")
            return False
        before_farm = obs.get("farm") or {}
        ready_before = int(before_farm.get("readyCrops") or 0)

        walked, walk_note, opened = self._walk_far_tile(tile, purpose="ready")
        st: StepResult | None = None
        err = ""
        if walked:
            try:
                st = self.worker.harvest(tile)
            except BridgeError as exc:
                err = str(exc)
            except Exception as exc:                  # pragma: no cover
                err = f"{type(exc).__name__}: {exc}"
        # 背包满：全局阻塞，不是这一格的错 ⇒ 不消耗该格额度，交给日级腾格回路。
        if st is not None and getattr(st, "no_slot", False):
            self._journal("ready_far", tile=list(tile), ok=False, code=st.code,
                          walked=bool(walked), try_=int(self.ready_far_tries.get(tile, 0)),
                          limit=READY_FAR_MAX_TRIES, status=status,
                          opens=self.ready_far_opens.get(tile, 0), opened_count=len(opened),
                          reason=st.reason, receipt=st.receipt, given_up=False,
                          note="【task-199】背包满 ⇒ 这是全局阻塞、不是这一格收不下来："
                               "不消耗该格尝试次数，交给日级 `_slot_relief` 腾格后再收")
            rep.notes.append(f"窗口外熟作物 {list(tile)} 这轮收不了：背包满（不算这一格的失败）")
            return False

        try:
            after_obs = self._snap()
        except BridgeError:
            after_obs = obs
        after_farm = after_obs.get("farm") or {}
        ready_after = int(after_farm.get("readyCrops") or 0)
        ok = bool(st.ok) if st is not None else False
        code = (st.code if st is not None else ("unreachable" if not walked else "error"))
        if ok:
            self.ready_far_causes.pop(tile, None)
            self.ready_far_tries[tile] = int(self.ready_far_tries.get(tile, 0)) + 1
            self.farm_actions_today += 1
            self._actions += 1
            rep.notes.append(f"收了窗口外那格熟作物 {list(tile)}"
                             f"（farm.readyCrops {ready_before}→{ready_after}）")
            self._say(f"  · 收窗口外熟作物 {list(tile)}：{code}")
        else:
            if not walked:
                blob = f"{walk_note} {err}"
                self.ready_far_causes[tile] = ("no_route"
                                               if any(h in blob for h in NO_ROUTE_HINTS)
                                               else "unreachable")
            elif status == "truncated":
                self.ready_far_causes[tile] = "truncated"
            elif status == "unavailable":
                self.ready_far_causes[tile] = "no_evidence"
            else:
                self.ready_far_causes[tile] = "not_ready"
            tries = int(self.ready_far_tries.get(tile, 0)) + 1
            self.ready_far_tries[tile] = tries
            if tries >= READY_FAR_MAX_TRIES:
                self.ready_far_given_up.add(tile)
            rep.notes.append(f"窗口外熟作物 {list(tile)} 没收成（第 {tries}/"
                             f"{READY_FAR_MAX_TRIES} 次，因由 {self.ready_far_causes.get(tile, '未定')}）："
                             f"{walk_note or err or (st.reason if st is not None else code)}"
                             + ("；不再试这一格" if tile in self.ready_far_given_up else ""))
        tries_now = int(self.ready_far_tries.get(tile, 0))
        self._journal("ready_far", tile=list(tile), ok=ok, code=code, walked=bool(walked),
                      try_=tries_now, limit=READY_FAR_MAX_TRIES, status=status,
                      ready_before=ready_before, ready_after=ready_after,
                      opens=self.ready_far_opens.get(tile, 0), opened_count=len(opened),
                      cause=self.ready_far_causes.get(tile, ""),
                      reason=(st.reason if st is not None else (walk_note or err)),
                      receipt=(st.receipt if st is not None else err),
                      given_up=bool(tile in self.ready_far_given_up),
                      note="【task-199】窗口外熟作物：farm.readyTiles 给了坐标 ⇒ 走过去收"
                           "（复用 `_walk_far_tile` 的走路/开路家族；判据 = `harvest()` 自己的"
                           "四选一观测差分，Mod 回执不是证据）")
        if not walked and not ok and tile in self.ready_far_given_up:
            # 【task-199】只在这一格**当天认输**时记一条 `ready_far_blocked`（避免每轮刷屏）；
            # 中间失败仍有逐次 `ready_far`（`walked=False` + `walk_note`）可查。
            self._journal("ready_far_blocked", tile=list(tile),
                          cause=self.ready_far_causes.get(tile, ""),
                          attempts=tries_now, limit=READY_FAR_MAX_TRIES,
                          opens=self.ready_far_opens.get(tile, 0),
                          walked=False, cleared_count=len(opened),
                          cleared_tiles=[[int(c.get("neighbour", [0, 0])[0]),
                                          int(c.get("neighbour", [0, 0])[1])]
                                         for c in opened[:8]],
                          note="【task-199】有界开路之后仍然站不到这一格 ⇒ 如实记 blocked："
                               "这一格**没收下来**（开路成功不等于收到手），当天不再试它")
        return ok

    @staticmethod
    def _water_left_obs(obs: dict[str, Any]) -> int | None:
        """壶里还剩几格水（**静态**读法，假 worker 也能用）：`None` = 无尽壶/无壶/读不到。

        为什么要单写一个：`farmwork.FarmWorker.water_left()` 是实例方法（要真 worker），
        而长跑里判断"要不要补水"必须只看观测（假 worker 没有这个方法）。
        """
        can = FarmWorker.can_state(obs)
        if not can.get("present") and not can.get("bottomless"):
            return None
        if can.get("bottomless"):
            return None
        left = can.get("waterLeft")
        try:
            return int(left) if left is not None else None
        except (TypeError, ValueError):               # pragma: no cover - 观测坏了
            return None

    def _refill_for_water_far(self, obs: dict[str, Any], rep: DayReport,
                             tile: tuple[int, int]) -> tuple[dict[str, Any], bool]:
        """【task-133】窗口外浇水专用补水：壶空 ⇒ 先补水，**不许**把壶空算成"够不着"。

        有界：一天最多 `FAR_DRY_REFILL_MAX` 次（免得"补水点走不到"时把整天耗在这一格）。
        判据：`refill_can()` 的 `ok`，或补水后 `waterLeft` 变大（`refill_can` 本身就按水位判）。
        返回 `(新观测, 是否补上)`。
        """
        assert self.worker is not None
        if self.far_dry_refills_today >= FAR_DRY_REFILL_MAX:
            return obs, False
        self.far_dry_refills_today += 1
        self._actions += 1
        before = self._water_left_obs(obs)
        ok, code, reason, receipt = False, "error", "", ""
        try:
            st = self.worker.refill_can()
            ok, code, reason, receipt = bool(st.ok), st.code, st.reason, st.receipt
        except BridgeError as exc:
            code = str(getattr(exc, "status", "") or "error")
            reason, receipt = str(exc), f"{code}: {str(exc)[:300]}"
        except Exception as exc:                      # pragma: no cover - 假 worker 的意外
            code, reason = "error", f"{type(exc).__name__}: {exc}"
        fresh = obs
        try:
            fresh = self._snap()
        except BridgeError:
            pass
        after = self._water_left_obs(fresh)
        if not ok and before is not None and after is not None and after > before:
            ok = True                               # 水确实变多了 = 补上了（回执可能不准）
        self._journal("water_far_refill", tile=list(tile), ok=bool(ok), code=code,
                      water_before=before, water_after=after,
                      tries=self.far_dry_refills_today, limit=FAR_DRY_REFILL_MAX,
                      reason=reason, receipt=receipt,
                      note="窗口外浇水前补水：壶空是前置条件，不是「够不着」（task-133）")
        if ok:
            self._say(f"  · 为窗口外浇水补水：水 {before}→{after}")
        else:
            rep.notes.append(f"窗口外浇水前补水没成（第 {self.far_dry_refills_today}/"
                             f"{FAR_DRY_REFILL_MAX} 次）：{reason or code}")
        return fresh, bool(ok)

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
            # 【task-84】`unwatered_crops` 只数**活苗**（死苗不该浇水，用户 m11003）；
            # 死苗单独给 `dead_crops`，两列不许混（否则 run7 的"还该浇"会包含没救的苗）。
            "unwatered_crops": len([t for t in crops
                                    if not tiles[t].get("watered") and not tiles[t].get("dead")]),
            "dead_crops": len([t for t in crops if tiles[t].get("dead")]),
            "ripe": len([t for t in crops if tile_ready(tiles[t])]),
            "tillable": len(loc.get("tillable") or []),
            "waterLeft": (p.get("wateringCan") or {}).get("waterLeft"),
            "seeds": [list(x) for x in seed_items(p)],
            # task-19：上面 `crops`/`unwatered_crops` 是**窗口口径**（≤400 格、以玩家为中心；在室内恒 0），
            # 这里逐字标注，并把 `farm.*` 读数整体放进**独立命名空间** —— 两套仪器不混列。
            # 【task-84】`farm.dryCrops`/`dryTiles` 自 0.7.27 起只算活苗；死苗的"干"看 `dryDeadCrops`。
            "counts_scope": "window",
            "farm": {k: (obs.get("farm") or {}).get(k)
                     for k in ("loaded", "complete", "crops", "dryCrops", "dryDeadCrops",
                               "unwateredCrops", "hoeDirt", "deadCrops")},
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
                "note": ("farm 口径：dry 来自 farm.dryCrops（**0.7.27 起只算活苗**："
                         "全农场 crop!=null && !Crop.dead && !HoeDirt.isWatered()；"
                         "枯死且没浇的格单独进 farm.dryDeadCrops、不参与本判据），"
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
        # 【task-84】窗口口径也**只数活苗**：死苗浇水是浪费（用户 m11003），它的"干"不该
        # 让 `dry > 0` 把当天判成"没浇完"（farm 口径已由 Mod 收窄；两条口径必须一致）。
        dry_t = [t for t in crops_t if not win[t].get("watered") and not win[t].get("dead")]
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
        if not crops_t:
            # 【task-96 ③】窗口里**一格作物都没有**时 `dry == 0` 同样是恒真：这不是"浇完了"，
            # 而是"没证据"。run7 那颗没浇的活苗 `[12,30]` 就在 400 格窗口之外 —— 旧代码在这里
            # 返回 True ⇒ `checks.watered_outdoor=true` ⇒ **假 VERIFIED**（deputy-lead task-92 的
            # C8b/C8c，完全不需要撒谎）。farm 口径不可用时只许"说不清"，绝不许"默认浇过"。
            info["note"] += ("；窗口里一格作物都没有（crops==0）⇒ 没有逐格浇水证据，如实判 False"
                             "（`dry==0` 在 crops==0 时恒真，不许据此自称浇过；task-96 ③）")
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

    # ---- 【task-158】浇水优先的体力预算 ----
    def _stamina_budget(self, obs: dict[str, Any]) -> dict[str, Any]:
        """按**当前观测**估算"今天还能干多少非浇水活"（纯估计，不改判定）。

        为什么需要它（run9d 实证）：summer 27/28、fall 1 三天都以 `stamina:体力 0 < 12` 收尾，
        而当天 `farm.dryCrops` 是 17/79/140 —— 体力烧在 clear/till/plant 上、浇水没做完 ⇒
        `watered_outdoor=false`、当天不 VERIFIED（用户目标"把作物伺候完"直接落空）。
        所以：**先把浇水的体力留出来**，剩下的才给别的活。

        * `water_reserve` = 活苗格数 × `STAMINA_COST_WATER` + `PATH_STAMINA_ALLOWANCE`
          （活苗数取 `farm.crops` 的**全农场**口径）；
        * `capacity` = 今天最多再播几格（卡面公式）：
          `(max_stamina − water_reserve − 锄一格) / (播种 + 浇一格)` ⇒ 只种今天还浇得过来的量；
        * farm 计数不可用（`complete != true` 或 `crops`/`dryCrops` 缺失）⇒ **fail-closed**：
          `basis="conservative"`、`water_reserve = 现有体力`（全留给浇水，非浇水活一律停手）。

        返回字典同时是 `stamina_budget` journal 与 `day_end.stamina_budget` 的字段集合。
        """
        player = FarmWorker.player_of(obs) or {}
        stam = float(FarmWorker.stamina(obs) or 0.0)
        try:
            max_stam = float(player.get("maxStamina") or 0.0)
        except (TypeError, ValueError):
            max_stam = 0.0
        if max_stam <= 0.0:
            max_stam = stam
        farm = obs.get("farm") or {}
        evidence = (bool(farm) and str(farm.get("loaded")) != "False"
                    and farm.get("loaded") is not False and farm.get("complete") is True)
        crops = farm.get("crops") if evidence else None
        dry = farm.get("dryCrops") if evidence else None
        if isinstance(crops, int) and isinstance(dry, int):
            basis = "farm"
            live = max(0, int(crops))
            dry_now = max(0, int(dry))
            reserve = max(0.0, live * STAMINA_COST_WATER + PATH_STAMINA_ALLOWANCE)
        else:
            basis = "conservative"
            live = dry_now = 0
            reserve = max(0.0, stam)
        per_new = max(1e-6, STAMINA_COST_SOW + STAMINA_COST_WATER)
        capacity = int(max(0.0, (max_stam - reserve - STAMINA_COST_TILL) // per_new))
        budget: dict[str, Any] = {
            "max": round(max_stam, 2),
            "stamina": round(stam, 2),
            "live_crops": live,
            "dry": dry_now,
            "water_reserve": round(reserve, 2),
            "water_cost_est": round(dry_now * STAMINA_COST_WATER, 2),
            "path_allowance": PATH_STAMINA_ALLOWANCE,
            "capacity": capacity,
            "basis": basis,
            "deferred_by_budget": False,
            "deferred": [],
        }
        prev = self.budget_today or {}
        if prev.get("deferred_by_budget"):
            # 当天已记过的"因预算推迟"要保留在快照里（日终读数如实）。
            budget["deferred_by_budget"] = True
            budget["deferred"] = list(prev.get("deferred") or [])
        return budget

    # ---- 【task-168】规模取舍：进简报的工作量缺口 + 各田区的事实 ----
    def _work_budget_facts(self, obs: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
        """`(live_crops, water_capacity, water_deficit)`；farm 证据不可用 ⇒ `(None, None, None)`。

        * `live_crops` 直接取 `_stamina_budget()` 的 `live_crops`（**同一份真值**，不另算一套）；
        * `water_capacity = floor((max_stamina − 路程余量) / STAMINA_COST_WATER)`
          —— **刻意不额外扣"补水预留"**：模型里没有可靠的补水体力系数，编一个数不如不编；
          这个方向只会**高估**容量 ⇒ `deficit` 偏小 ⇒ 更少认输（fail-safe，不会拿未知当免罚）；
        * `basis != "farm"` ⇒ 三个都 `None`+【未观测到】（**绝不许**把"不知道"写成 0）。
        """
        b = self._stamina_budget(obs)
        if str(b.get("basis")) != "farm":
            return None, None, None
        try:
            live = max(0, int(b.get("live_crops") or 0))
            max_stam = float(b.get("max") or 0.0)
            path = float(b.get("path_allowance") or PATH_STAMINA_ALLOWANCE)
        except (TypeError, ValueError):
            return None, None, None
        cost = float(STAMINA_COST_WATER)
        if cost <= 0.0:
            return live, None, None
        capacity = int(max(0.0, (max_stam - path)) // cost)
        return live, capacity, max(0, live - capacity)

    def _area_facts(self, obs: dict[str, Any]) -> tuple[tuple[str, int, int], ...]:
        """各田区的 `(名字, 未浇活苗格数, 该区格数)`（**只数观测里看得见的格**）。

        死苗不算"未浇活苗"（task-84：浇水目标只认活苗）；区里一格观测都没有 ⇒ **不收录**
        （宁可不提议认输，也不拿空数据当"这个区没事"）。返回按名字排序 ⇒ 可复现。
        """
        zones = self._zones(obs)
        if not zones:
            return ()
        tmap = FarmWorker.tiles_of(obs)
        out: list[tuple[str, int, int]] = []
        for z in zones:
            try:
                x0, y0, x1, y1 = (int(v) for v in tuple(z.bounds))  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - 田区坏了不该拖垮简报
                continue
            tiles = 0
            dry = 0
            for (x, y), tv in tmap.items():
                if not (x0 <= x <= x1 and y0 <= y <= y1):
                    continue
                tiles += 1
                if tv.get("crop") and not tv.get("watered") and not tv.get("dead"):
                    dry += 1
            if tiles > 0:
                out.append((str(getattr(z, "name", "")), dry, tiles))
        return tuple(sorted(out, key=lambda it: it[0]))

    # ---- 【task-161】阶段体力实测聚合（只留痕） ----
    def _stamina_calibration(self, rep: DayReport) -> dict[str, Any]:
        """把当天 `rep.stages` 的实测体力按 stage 聚合：`{stage: {actions, stamina_spent, per_action}}`。

        * `actions` = 该 stage 的 `ok` 数（和 `stage["ok"]` 一致）；
        * `stamina_spent` = 该 stage 各条 `stamina_spent` 之和；**任何一条缺观测**（`null`）
          都只是"不参与求和"，不清零、不猜测（缺就保持 `None`）；
        * `per_action = stamina_spent / actions`（`actions == 0` ⇒ `null`）。

        纯留痕：**不进 `checks`、不改任何判据/常量**。用途是下一次真机 run 之后，
        用它替换 `farmwork.py` 里的 `STAMINA_COST_*` 估算常量（那一步单独过对抗验收）。
        """
        calib: dict[str, Any] = {}
        for s in rep.stages:
            name = str(s.get("stage") or "")
            if not name:
                continue
            ent = calib.setdefault(name, {"actions": 0, "stamina_spent": None})
            ent["actions"] = int(ent["actions"]) + int(s.get("ok") or 0)
            spent = s.get("stamina_spent")
            if isinstance(spent, (int, float)) and not isinstance(spent, bool):
                base = ent["stamina_spent"]
                ent["stamina_spent"] = round((float(base) if isinstance(base, (int, float)) else 0.0)
                                             + float(spent), 1)
        for ent in calib.values():
            acts = int(ent["actions"])
            spent = ent["stamina_spent"]
            ent["per_action"] = (round(float(spent) / acts, 2)
                                 if acts > 0 and isinstance(spent, (int, float)) else None)
        return calib

    def _budget_defer_reason(self, task: str, obs: dict[str, Any]) -> str:
        """预算是否**拒绝**这一阶段（只针对 clear/till/plant 三类非浇水活）；空串 = 允许。

        两条**只关于预算**的判据（不是"没活"）：
        * 体力已经掉到浇水预备线以下、而地里还有活苗要浇 ⇒ 停手保浇水；
        * `plant_area` 且**当天还有没浇的活苗** ⇒ 先浇，不许再种（卡面第 2/3 条）。
        """
        if task not in ("clear_area", "till_area", "plant_area"):
            return ""
        b = self._stamina_budget(obs)
        if task == "plant_area":
            dry = int(b.get("dry") or 0)
            if dry > 0:
                return (f"今天还有 {dry} 格活苗没浇（farm.dryCrops）⇒ 先浇水，"
                        f"预算不许再播种")
        debt = (str(b.get("basis")) == "conservative"      # 证据不足 ⇒ 当作"可能有浇水债"
                or int(b.get("dry") or 0) > 0 or int(b.get("live_crops") or 0) > 0)
        if not debt:
            return ""                      # 没有浇水债 ⇒ 预算不该拦别的活
        stam = float(b.get("stamina") or 0.0)
        reserve = float(b.get("water_reserve") or 0.0)
        if stam > reserve:
            return ""
        return (f"体力 {stam:g} ≤ 浇水预备 {reserve:g}"
                f"（{int(b.get('live_crops') or 0)} 格活苗 × {STAMINA_COST_WATER:g}"
                f" + 路程 {PATH_STAMINA_ALLOWANCE:g}，basis={b.get('basis')}）"
                f"⇒ 停手把体力留给浇水")

    def _note_budget_deferred(self, task: str, why: str,
                              tiles: Iterable[tuple[int, int]] = ()) -> None:
        """把"因为预算而不做"记进当天预算快照 + journal（一天每类只记一次）。

        ⚠️ 语义钉死：只记**因为预算**而不做的活（卡面红线②）——"确实没活"不算预算推迟，
        否则守卫的 `work_reasons` 会被污染成"还有活"。

        【task-163】同时把"当时还没做完的格子"记进 `self.budget_deferred_tiles`：
        守卫（`work_reasons`/`_pending_work`/`_leftover`）据此**不再**把这些格子算作
        "还有活可做"，改走显式延后（日终按任务分类留痕 `budget_deferred_tiles{task: n}`）。
        这些格子**绝不**参与 `checks`/`assigned_undone` 扣减（延后 ≠ 洗白）。
        """
        b = self.budget_today
        if not b:
            return
        b["deferred_by_budget"] = True
        deferred = b.setdefault("deferred", [])
        first = task not in deferred
        if first:
            deferred.append(task)
        pending = sorted({(int(t[0]), int(t[1])) for t in tiles})
        new_tiles: list[tuple[int, int]] = []
        if pending:
            known = set(self.budget_deferred_tiles.get(task, []))
            new_tiles = [t for t in pending if t not in known]
            if new_tiles:
                self.budget_deferred_tiles.setdefault(task, []).extend(new_tiles)
                b.setdefault("deferred_tiles", {})[task] = len(self.budget_deferred_tiles[task])
        if not first and not new_tiles:
            return          # 一天每类只记一次（后来真发现了新的延后格才再记一笔）
        # 【task-6 / 0.7.44】不立即落事件：排到日终 `_flush_budget_deferrals()`，只有当天
        # **没浇完**才写 `deferred_by_budget`（否则会与"户外浇水达标"同真、被 analyzer 判自相矛盾）。
        self.budget_defer_events.append(dict(
            task=task, why=why,
            stamina=b.get("stamina"), water_reserve=b.get("water_reserve"),
            dry=b.get("dry"), live_crops=b.get("live_crops"),
            basis=b.get("basis"), tiles=len(pending),
            targets=[list(t) for t in pending[:6]],
            note="只因预算而不做（不是没活）；没浇完就是 crops_watered=false"))
        if pending:
            self._journal("budget_deferred_tiles", task=task, count=len(pending),
                          total=len(self.budget_deferred_tiles[task]),
                          targets=[list(t) for t in pending[:6]],
                          note="这些格子今天被**体力预算**显式延后：守卫不再把它们算作"
                               "『还有活』，但也不参与任何判定扣减（延后≠洗白）")

    def _flush_budget_deferrals(self, *, watered_outdoor: bool,
                                rep: DayReport | None = None) -> int:
        """【task-6 / 0.7.44】把排队中的 `deferred_by_budget` 事件**在日终**落账。

        卡面②：「只因预算延后」与「户外浇水达标」**不得同真**（analyzer 的 ⚠ 判据正是
        `deferred_by_budget` 事件 + `checks.watered_outdoor=true` + `final_water.dry==0`）。
        所以事件不再立即 emit，而是排进 `budget_defer_events`，等日终拿到浇水证据再决定：

        * `watered_outdoor=False` ⇒ 正常落事件（延后确实解释了"为什么有活没干完"）；
        * `watered_outdoor=True`  ⇒ **一条都不落**，降级成日级 info：
          `day_end.stamina_budget.deferred_by_budget_suppressed=<n>` 且该日
          `deferred_by_budget=False`（analyzer 的"日级>0 却无事件"同一口径也不会红）。
          留痕不丢：条数仍在 `suppressed` 计数里（队列本身含 task/why/格数；只是不当事件发）。

        返回实际落账的事件条数。`rep=None` 供单测直接驱动（只按 flag 决定落/不落）。
        """
        events, self.budget_defer_events = self.budget_defer_events, []
        if not events:
            return 0
        if watered_outdoor:
            if rep is not None:
                rep.stamina_budget["deferred_by_budget_suppressed"] = (
                    int(rep.stamina_budget.get("deferred_by_budget_suppressed") or 0)
                    + len(events))
                # 与"当天有 `deferred_by_budget`"的日级自述对齐：浇完了就不算"只因预算延后"。
                rep.stamina_budget["deferred_by_budget"] = False
            return 0
        for ev in events:
            self._journal("deferred_by_budget", **ev)
        return len(events)

    def _budget_deferred_tasks(self) -> set[str]:
        """【task-163】当天因**体力预算**被显式延后的任务集合（空集 = 没有延后）。

        唯一写入点是 `_note_budget_deferred()`，而它只在 `_budget_defer_reason()` 非空
        （体力 ≤ 浇水预备 **且** 有浇水债）时被调用 ⇒ 这个集合天然满足卡面红线②：
        没有浇水债、或者体力还在预备线以上时，延后一律不生效。
        """
        b = self.budget_today or {}
        if not b.get("deferred_by_budget"):
            return set()
        return {str(t) for t in (b.get("deferred") or [])}

    def _budget_deferred_tile_set(self) -> set[tuple[int, int]]:
        """所有被预算显式延后的格子（守卫据此把它们从"还有活"里剔除）。"""
        out: set[tuple[int, int]] = set()
        for tiles in self.budget_deferred_tiles.values():
            out.update(tiles)
        return out

    @staticmethod
    def _farm_count(obs: dict[str, Any], key: str) -> int | None:
        """farm 级计数（`blockers`/`crops`/...）的**唯一安全读法**：拿不到 ⇒ `None`。

        fail-closed 纪律：证据不可用/字段缺失/类型不对时**绝不返回 0** —— "没观测到"
        与"计数为 0"是两件事（把未知当 0 会造出假 VERIFIED，task-96 的教训）。
        """
        farm = obs.get("farm")
        if not isinstance(farm, Mapping):
            return None
        if farm.get("loaded") is False or farm.get("complete") is not True:
            return None
        raw = farm.get(key)
        if isinstance(raw, bool) or not isinstance(raw, int):
            return None
        return int(raw)

    def _tree_budget_left(self, obs: dict[str, Any]) -> bool:
        """【task-218 ④ / task-241】今天还能不能砍树（**体力驱动**预算 + 浇水优先）。

        判据：`_tree_budget_room(obs) > 0`（可支配体力 ÷ 单棵成本，封顶
        `MAX_TREES_PER_DAY`，见 `_tree_budget_room`），且 `clear_area` 整体没被预算拦下。

        预算挡下的树：不进 `_stage_tiles` 目标池、不算"还有活"（`_plot_has_work`）、
        也不进 `_leftover`（"今天不做 ≠ 该做没做"），**不记 hard failure**。
        每天记一次 `deferred_by_budget`（**不发新事件名**：analyzer 的机械枚举会因此漂移），
        理由写清「预算 N / 已砍 M」。
        """
        # 整个 `clear_area` 已经被体力预算拦下时**不再单独留痕**（避免同一天两套
        # `deferred_by_budget` 语义打架，也避免已有用例的期望集合被无谓污染）。
        if self._budget_defer_reason("clear_area", obs):
            return False
        if self._tree_budget_room(obs) > 0:
            return True
        if not self.tree_budget_noted:
            self.tree_budget_noted = True
            b = self._stamina_budget(obs)
            try:
                stam = float(b.get("stamina") or 0.0)
                reserve = float(b.get("water_reserve") or 0.0)
            except (TypeError, ValueError):
                stam = reserve = 0.0
            discretionary = max(0.0, stam - reserve)
            raw = min(int(MAX_TREES_PER_DAY), int(discretionary // TREE_STAMINA_COST))
            cleared = int(self.trees_cleared_today or 0)
            # 【task-6 / 0.7.44】同样排队到日终（`_flush_budget_deferrals`）：
            # 与"户外浇水达标"互斥；砍树预算延后也属于"只因预算而不做"。
            self.budget_defer_events.append(dict(
                task="clear_area_tree",
                why=(f"预算 {raw} 棵 / 已砍 {cleared} 棵（体力驱动：可支配体力 "
                     f"{discretionary:g} ÷ 单棵 {TREE_STAMINA_COST:g}，封顶 "
                     f"{MAX_TREES_PER_DAY}）"),
                budget_trees=raw, cleared_trees=cleared,
                discretionary_stamina=round(discretionary, 2),
                per_tree_stamina=TREE_STAMINA_COST,
                note="只因**砍树预算**而不做；不算硬失败、不进 leftover"))
        return False

    def _tree_budget_room(self, obs: dict[str, Any]) -> int:
        """【task-241】今天**还能砍几棵树**（体力驱动；封顶 `MAX_TREES_PER_DAY`）。

        `budget = floor(max(0, 当前体力 − 浇水预备) ÷ TREE_STAMINA_COST)`，再减今天已砍。
        证据不可用 ⇒ `_stamina_budget()` 走 conservative（`water_reserve = 现有体力`）⇒
        可支配体力 0 ⇒ 返回 0（**fail-closed**：绝不为砍树漏浇）。返回 0 = "今天不砍"，
        不是失败；每砍倒一棵 `trees_cleared_today` 立刻 +1，下一轮用新观测重算剩余额度。
        """
        b = self._stamina_budget(obs)
        try:
            stam = float(b.get("stamina") or 0.0)
            reserve = float(b.get("water_reserve") or 0.0)
        except (TypeError, ValueError):
            return 0
        discretionary = max(0.0, stam - reserve)
        budget = min(int(MAX_TREES_PER_DAY), int(discretionary // TREE_STAMINA_COST))
        return max(0, budget - int(self.trees_cleared_today or 0))

    def _deferred_scan(self, task: str, obs: dict[str, Any]) -> list[tuple[int, int]]:
        """【task-163】还没挑作业区时，用观测直接扫出"这个任务今天有多少格没做完"。

        只用于**留痕**（`budget_deferred_tiles{task: n}`）与守卫闭嘴，口径与 `_leftover`
        的对应分支保持一致；拿不到就返回空列表（留痕为 0，不改任何判定）。
        """
        tmap = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        if task == "clear_area":
            # 【task-218】树要按日预算收窄（预算挡下的树不算"该做没做"）。
            tree_ok = self._tree_budget_left(obs)
            return sorted(t for t, v in tmap.items()
                          if str(v.get("kind") or "") in ACTIONABLE_KINDS
                          or (tree_ok and str(v.get("kind") or "") == TREE_KIND))
        if task == "till_area":
            if not self._seed_outlook(obs)[2]:
                return []
            return sorted(t for t in tillable if not _till_blocked_by(tmap.get(t)))
        if task == "plant_area":
            if not self._seed_outlook(obs)[2]:
                return []
            return sorted(t for t, v in tmap.items()
                          if str(v.get("kind") or "") == "dirt" and not v.get("crop"))
        return []

    def _note_budget_deferrals(self, obs: dict[str, Any]) -> None:
        """【task-163】日初把"今天因预算而不做"的三类活一次性记账（+ 延后格清单）。

        为什么必须在日初做：延后要能**让守卫闭嘴**，而守卫（`work_reasons`/`_plot_has_work`/
        `_pending_work`/`_leftover`）读的是 `budget_deferred_tiles`。若只在 `_stage_tiles`
        被调用时才记，那么"策略给 `review`、守卫说还有活"的日子里延后永远记不上
        （run9d day1 形态）⇒ 白烧一天。**只留痕、不改判定**。
        """
        if not self.budget_today:
            return
        for task in ("clear_area", "till_area", "plant_area"):
            why = self._budget_defer_reason(task, obs)
            if not why:
                continue
            self._note_budget_deferred(task, why, tiles=self._deferred_scan(task, obs))

    def _note_capacity_capped(self, task: str, limit: int, capacity: int) -> None:
        """【task-163 NIT-2】容量上限命中要**看得见**（旧行为静默生效、账本里查不到）。

        一天每类只发一条 journal，并把汇总写进 `budget_today["capped_by_capacity"]`
        （随 `day_end.stamina_budget` 落账）。**只留痕，不改判据**。
        """
        b = self.budget_today
        if not b:
            return
        capped = b.setdefault("capped_by_capacity", {})
        if task in capped:
            return
        capped[task] = {"limit": int(limit), "capacity": int(capacity)}
        b["capacity_capped_tasks"] = len(capped)
        self._journal("stage_capped_by_capacity", task=task, limit=int(limit),
                      capacity=int(capacity), live_crops=b.get("live_crops"),
                      dry=b.get("dry"), water_reserve=b.get("water_reserve"),
                      note="分配额被当天体力预算的容量上限卡住 ⇒ 只分配 capacity 格；"
                           "这不是『没活』，日终按预算延后口径解释")

    def _seed_season_state(self, obs: dict[str, Any]) -> dict[str, Any]:
        """【task-240】当季"能不能种"的聚合（0.7.41 冒烟 day1：冬天拿小麦宣称"该去种"）。

        口径**只有一份**：`farmwork.seed_season_state(player, season)`（由 Mod 的
        `player.seeds[]` 逐条 `seasons`/`plantableNow` 汇总）。`player.seeds` 缺字段
        （旧 Mod）⇒ `metadata=False`，`can_plant` 退回 `seed_items()` 老口径 —— 这是
        唯一允许 fail-open 的地方（"没有新字段"≠"没有种子"）。
        """
        player = FarmWorker.player_of(obs)
        try:
            season = str(FarmWorker.day_key(obs)[1] or "")
        except Exception:  # pragma: no cover - 观测缺 clock 时按"认不出季节"处理
            season = ""
        return seed_season_state(player, season)

    def _seed_outlook(self, obs: dict[str, Any]) -> tuple[int, int, bool]:
        """(当季可种种子数, 钱, 还能不能搞到种子)。

        【task-240】第一个数从"种子总堆叠"改成**当季可种**（`plantableNow is True`）：
        冬天拿着 10 粒 Wheat Seeds 时，旧口径会说"有种子 ⇒ 该去种"，下地却 `no_seed`
        ⇒ 守卫与执行层互相打脸、整天 stuck。旧 Mod（没有 `seeds[]`）仍退回总堆叠。

        【task-67】"能不能搞到"必须把**今天已经确认买不到**算进去（`self.seed_dead_today`）：
        否则 run6 的死锁原样复现 —— 守卫每轮都看到"钱够 ⇒ 该去买"，而商店根本没有当季种子。

        【task-123】"钱够"以**当季在售种子的实际价**为准（见 `_seed_price_now()`），
        拿不到货架清单才退回 `--seed-price`。run9 的配置价与货架价是两回事，混用会把
        "10g 的 Wheat Seeds 摆在眼前、手上 88g"判成买不起 ⇒ 当天一粒不买。
        """
        state = self._seed_season_state(obs)
        seeds = int(state["plantable"]) if state["metadata"] else int(state["seeds_total"])
        money = FarmWorker.money(obs)
        can = seeds > 0 or (self.allow_buy and money >= self._seed_price_now()
                            and not self.seed_dead_today)
        # 【A9 gatefix2 实证】冬季 `plantable==0` 且走"3 轮校验取消"路径时 `_preconditions_apply`
        # 不一定跑过 ⇒ `seed_dead_today` 可能没置 ⇒ `can` 退化成"钱够就能买"的 True ⇒
        # `_pending_snapshot` 把冬季不可播种的 242/245 格 tillable 当"可执行活" ⇒ `no_work` 日
        # 永远 `zero_action_evidenced=False`。这里直接按季节收口：冬季没有可当季买到的种子，
        # 就算有钱也不能把 tillable 算成可执行活（与 task-241 的 `winter_no_seeds` 同义，
        # 只是不再依赖"当天是否跑过买种闸门"）。有当季可种种子时不受影响。
        if can and state["metadata"] and int(state["plantable"]) <= 0 \
                and str(state.get("season") or "").lower() == "winter":
            can = False
        return seeds, money, can

    def _seed_price_shelf(self) -> int:
        """货架上**最便宜的在售种子价**（没清单 / 没有种子 / 价格不可用 ⇒ **0**，不猜）。

        只认 `is_seed_offer()` 认可的条目（名字带 seed/种子）且价格 > 0 —— 与
        `pick_seed_offer()` 的挑法同源，避免"守卫说买得起、挑的时候说买不起"两边错配。
        """
        prices = [int(o.get("price") or 0) for o in self.shop_offers
                  if is_seed_offer(o) and int(o.get("price") or 0) > 0]
        return min(prices) if prices else 0

    def _seed_price_now(self) -> int:
        """当下"一个种子多少钱"：**货架实际价优先**，拿不到清单才退回 `--seed-price`（task-123）。"""
        return self._seed_price_shelf() or int(self.seed_price)

    def _plot_has_work(self, obs: dict[str, Any], tiles: Iterable[tuple[int, int]]) -> bool:
        tmap = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        _seeds, _money, can_plant = self._seed_outlook(obs)
        # 【task-163】当天被体力预算**显式延后**的任务不再算"还有活"（否则守卫说还有活、
        # 而 `_stage_tiles` 被预算拦住不产目标 ⇒ 白烧一天且当天不可能 VERIFIED）。
        # 浇水/收获/清死苗**永不延后**，所以下面 crop 分支照旧。
        deferred = self._budget_deferred_tasks()
        # 【task-168】认输片区里的格子**不算"还有活"**（主动放弃 ⇒ 守卫闭嘴）。
        # 注意这不影响会计：`_leftover`/`plot_pending`/`assigned_undone` 照旧把这些格算未完成。
        shed = self._shed_tile_set()
        # 【task-198】背包满/将满时，"可收"**不算这片地还有活** —— 收不进来（`no_slot` 是
        # 全局阻塞），拿它当选区/开工理由只会让日循环去撞同一堵墙（run A′ 的 45 条同句失败）。
        # 注意只收窄"熟作物"这一路：没浇的作物（浇水不占格）与枯死作物（清死苗）照旧算活。
        free_slots, bag_need, bag_status = self._bag_state(obs)
        bag_blocked = self.inventory_blocked_today or (bag_status == "ok" and bag_need > 0)
        # 【devcoder-clear-gate E】满包清障闸与 `_stage_tiles("clear_area")` **同口径**：
        # 闸住时清障类格今天不再执行 ⇒ 这片地也**不算**"还有地要清"。否则守卫一直喊、
        # `_ensure_plot` 永不为 None ⇒ `decision.intents` 每轮非空 ⇒ 3 轮 idle ⇒ `stuck:`
        # （A9 winter27/28 的形态）。收尾交给 `_end_clear_gate`（`clear_gate`，永不 VERIFIED）。
        clear_gate = bool(self._clear_bag_gate_reason(obs))
        for t in tiles:
            if t in self.blocked or t in shed or t in self.encircled_day:
                # 今天已经证明"动了没用" / 今天已主动认输 / 【task-5】被围住的格今天也不再算"活"。
                # 后者是 A8 冬 9/14 的病灶之一：`[37,35]` 被围住却仍被算成"field_sw 还有地要清"，
                # 守卫因此一整天不放行、而执行层每轮又拿它当目标（世界不变）⇒ 3 轮 idle 判 stuck。
                continue
            if t in self.resume_stall_tiles:
                # 【task-15 / 0.7.45】换片机制"回去看过、拿不出目标"的格今天也不算这片地的活
                # （否则守卫被 0.7.44 冒烟冬 27 的 217 格旧账钉死；日终在 pending_stalled 留痕）。
                continue
            tv = tmap.get(t)
            if tv is None:
                # 没动过的格子在 tiles[] 里根本不存在，只能靠 tillable[] 认。
                # 但**没种子又买不起**时锄地是纯烧体力（`_plot_brief` 的 broken 分支就是这么判的）：
                # 这里必须同口径，否则"守卫说还有活 / 策略说没事可做"会把一天耗成 stuck。
                if t in tillable and can_plant and "till_area" not in deferred:
                    return True
                continue
            if tv.get("crop"):
                # 【task-170 ②】"可收"那半句要扣掉今天已证明收不到的格（`harvest_gave_up`）：
                # 否则一格摘不到的作物会让"这片地还有活"永远成立 ⇒ 守卫 veto 收工。
                if not tv.get("watered"):
                    return True
                if (tile_ready(tv) and t not in self.harvest_gave_up
                        and not bag_blocked):
                    return True
                # 【task-51】枯死作物**也是活**：它占着耕地、挡着 `till`（`till_blocked_by` 见 crop 就拒），
                # 不清掉就永远开不了这一格。run5 真机夏季 2 日：窗口 24 个作物里 23 个 `dead=True`
                # ⇒ 这一趟一直返回 False ⇒ 作业区被判"没活"⇒ 一整天零动作。
                if tv.get("dead"):
                    return True
                continue
            kind = str(tv.get("kind") or "")
            if kind in ACTIONABLE_KINDS and "clear_area" not in deferred:
                if clear_gate:
                    continue      # 【devcoder-clear-gate E】满包闸住 ⇒ 今天不清、不算活
                return True
            # 【task-218】树也算"这片地有活"（LLM 一直这么理解，旧实现却在 `clear()` 里静默跳过）；
            # 但受日级砍树预算约束 —— 预算挡下时不算活，否则守卫会被"砍不完的树"钉死一整天。
            if (kind == TREE_KIND and "clear_area" not in deferred
                    and not _tool_blocked_tv(tv) and self._tree_budget_left(obs)):
                if clear_gate:
                    continue      # 【devcoder-clear-gate E】同上
                return True
            # 够格的 clump 一族（toolOk == true）同样算活；toolOk false/null ⇒ 能力缺口、不算活。
            if (kind in CLUMP_KINDS and "clear_area" not in deferred
                    and not _tool_blocked_tv(tv)):
                if clear_gate:
                    continue      # 【devcoder-clear-gate E】同上
                return True
            if (t in tillable and can_plant and not _till_blocked_by(tv)
                    and "till_area" not in deferred):
                return True
            if kind == "dirt" and can_plant and "plant_area" not in deferred:
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
        # 【task-84】枯死作物也算"活"（要去 `clear_dead` 清掉），所以 `dead` 也要收进来；
        # 但它**不是**"该浇水"（`_stage_tiles("water_area")`/`counts["unwatered_crops"]`
        # 都已剔除死苗），这里只是把它所在的格子当作业区容器用。
        tiles = [t for t, v in tmap.items()
                 if v.get("crop") and (not v.get("watered") or tile_ready(v) or v.get("dead"))]
        # 【task-168】认输片区的格子不算"收尾活"（主动放弃 ≤ 一天 1 个区，有界）。
        # 【task-5 / 0.7.44】被围住 / 今天已挡死的格也不算"收尾活"：否则收尾作业区会拿着
        # 一个执行层永远做不成的格每轮重来（A8 冬 9/14 的 1 格阶段死循环）。
        if tiles:
            dead = self._dead_tile_set()
            if dead:
                tiles = [t for t in tiles if t not in dead]
            shed = self._shed_tile_set()
            if shed:
                tiles = [t for t in tiles if t not in shed]
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

    def _resume_plot(self, obs: dict[str, Any], *, avoid_area: str = "") -> dict[str, Any] | None:
        """【task-49】把今天**已经见过、还没做完**的格子当作业区，回去把它做完。

        【task-4 / 0.7.44】0.7.43 的补充规则：

        * **一次只挑账本里的一片**（`leftover_area` 的田区归属；没田区信息时按 8×8 空间簇）——
          冬 7/12/18 的连续 5 次空转就是"每次都把最近的同一批不可执行树当目标走回去"；
          换片由调用方在"邻域已看过、仍然没目标"时触发，坐标全部来自账本记账；
        * **跳过今天已证明"回去也拿不出目标"的邻域**（`resume_stall_tiles`）与**被围住的格**
          （`encircled_day`：四邻没有突破口 ⇒ 不是可执行目标，绝不能拿来当"他片可做"的借口）；
        * `avoid_area` 非空时优先挑**别的**片区（调用方换片用）。

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
        # 【task-4 / 0.7.44】被围住（没有突破口）不是可执行目标；回去看过没产出的邻域也不再选。
        skip = set(self.resume_stall_tiles) | set(self.encircled_day)
        cand = [t for t in pending if t not in skip]
        if not cand:
            return None
        pt = FarmWorker.player_tile(obs)
        # 账本片区归属（`_step_stage` 记账时算）：一次只挑一片，避免"最近的同一批格"反复空转。
        by_area: dict[str, list[tuple[int, int]]] = {}
        for t in cand:
            by_area.setdefault(str(self.leftover_area.get(t) or ""), []).append(t)
        if not by_area:
            return None

        def _area_key(item: tuple[str, list[tuple[int, int]]]) -> tuple[int, int, str]:
            area, tiles = item
            near = min(_dist(t, pt) for t in tiles)
            # avoid_area 优先挑**别的**片；没有别的片时自然落回同一片（如实记 from/to area）。
            rank = (0 if area != avoid_area else 1) if avoid_area else 0
            return (rank, near, area)

        area, tiles = min(by_area.items(), key=_area_key)
        tiles = sorted(tiles, key=lambda t: (_dist(t, pt), t[1], t[0]))[:25]
        if not tiles:
            return None
        return {
            "zone": area if area and not area.startswith("@") else "",
            "label": "",
            "area": area,
            "anchor": [tiles[0][0], tiles[0][1]],
            "tiles": tiles,
            "note": (f"今天还有 {len(tiles)} 格没做完（{area or '跨片地'}，玩家窗口看不见）：回去接着做"),
        }

    @staticmethod
    def _resume_anchor(plot: dict[str, Any] | None) -> tuple[int, int] | None:
        """作业区（含 `_resume_plot` 给的容器）的锚点坐标；拿不到就返回 None（不猜）。"""
        if not plot:
            return None
        a = plot.get("anchor")
        if isinstance(a, (list, tuple)) and len(a) == 2:
            try:
                return (int(a[0]), int(a[1]))
            except (TypeError, ValueError):
                return None
        tiles = plot.get("tiles") or []
        if tiles:
            try:
                return (int(tiles[0][0]), int(tiles[0][1]))
            except (TypeError, ValueError, IndexError):
                return None
        return None

    def _resume_walk_available(self) -> bool:
        """【task-26 / 0.7.46】回片区走路预算：**成功**次数封顶 `max_plots_per_day`，
        **尝试**次数另封顶 `2 * max_plots_per_day`。

        为什么要把两者分开（冬27 账本证据，L637/L641）：`resume_walks` 旧口径在走路**之前**
        就自增，attempts 1–7（L39/L59/L93/L123/L150/L204，全部 `walked:false`）也各烧掉
        一格预算 ⇒ t=366 时 `resume_walks` 已经是 10/10；等 t=845 只剩 7 格可执行余格
        （L637 `work_spot{tiles:7, field_se}`）时预算已尽，`_walk_into_plot` 一次都不许走，
        最终以 `resume_exhausted`（自称"当前观测里没有可执行目标"）收尾 —— 而 day_end
        快照实测 `pending_executable=7`，两句话自相矛盾。

        失败尝试仍要封顶（否则"走不动"的路会把一天全烧在反复走路上）；但失败不再挤掉
        "真的看过一次"的额度，所以像冬27 这种"前面失败 7 次、后面才浮出可执行余格"的日子
        还能回去把它们做完。
        """
        return (self.resume_walks < self.max_plots_per_day
                and self.resume_walk_attempts < 2 * self.max_plots_per_day)

    def _tile_area(self, obs: dict[str, Any], tile: tuple[int, int]) -> str:
        """账本坐标 → 具名田区（`fields.zones_from_observe` 由**当前观测**现算，不硬编码坐标）。

        观测里没有田区信息（室内 / fields 缺失 / 旧 Mod）时退化成确定性的 8×8 空间簇 `@x,y`：
        换片只需要"不同的片区"这个粒度，坐标本身仍然来自 `leftover_targets` 记账，绝不臆造。
        """
        try:
            zones = self._zones(obs)
        except Exception:                       # pragma: no cover - 田区坏了不该拖垮主流程
            zones = []
        for z in zones:
            try:
                x0, y0, x1, y1 = (int(v) for v in tuple(getattr(z, "bounds")))
            except Exception:                   # pragma: no cover - 坏田区跳过
                continue
            if x0 <= tile[0] <= x1 and y0 <= tile[1] <= y1:
                return str(getattr(z, "name", "") or "")
        return f"@{tile[0] // 8},{tile[1] // 8}"

    def _mark_resume_no_output(self, obs: dict[str, Any], plot: dict[str, Any]) -> int:
        """把"已经走过去看过、仍然拿不出目标"的账本邻域记进当天停滞集合（task-4 / 0.7.44）。

        半径用 `OBSERVE_REACH`（观测可见半径）：走到锚点旁边之后，这个半径内的格子都在传感器
        里出现过；它们仍然拿不出目标 ⇒ 再走回同一片只是重复 0.7.43 的连续空转。**只标
        `leftover_targets` 里真有记账的坐标**（不往集合里造坐标）。返回本次新标了几格。
        """
        anchor = self._resume_anchor(plot)
        pending = self._pending_work()
        if anchor is None:
            marked = {tuple(t) for t in plot.get("tiles") or []
                      if tuple(t) in self.leftover_targets}
        else:
            marked = {t for t in pending if _dist(t, anchor) <= OBSERVE_REACH}
            marked |= {tuple(t) for t in plot.get("tiles") or []
                       if tuple(t) in self.leftover_targets}
        new = marked - self.resume_stall_tiles
        self.resume_stall_tiles |= marked
        return len(new)

    def _resume_switch_or_exhaust(self, obs: dict[str, Any], rep: "DayReport", *,
                                  plot: dict[str, Any], where: str,
                                  repeated: bool = False) -> tuple[str, dict[str, Any] | None]:
        """回片区连续拿不出目标时的**有界退路**（task-4 / 0.7.44）。

        0.7.43 的形态（冬 7/12/18）：`leftover_targets` 里残留 200+ 棵"早先可见、砍树预算耗尽后
        不可执行"的树 ⇒ `_resume_plot` 连续 5 次把人带回同一片 ⇒ 整天记成
        `stuck:回片区（work_spot_resume）`，把"今天真没有可执行目标"误报成卡死。按卡面顺序：

        ① **换到另一片/另一田区的账本待做格**（坐标全部来自 `leftover_targets` 记账）⇒
           journal 复用既有事件 `plot_exhausted`（`source="resume_ledger"`，新增字段见下）；
        ② **当前观测里可达 + 可清障的一格**（坐标来自本张观测；复用 task-68 的 `frontier_clear`）
           ⇒ journal `plot_exhausted`（`source="resume_observation"`）+ 既有 `frontier_clear`；
        ③ 都没有 ⇒ **诚实收工**：journal 复用既有事件 `no_progress_burst`（`exhausted=True`），
           `ended_reason` 前缀 = `resume_exhausted`（不在 `JUSTIFIED_END_REASONS` 白名单 ⇒
           `day_justified=False`/不 VERIFIED），绝不写 `stuck:`。

        返回 `("walk", 另一片的作业区)` / `("acted", None：已经真清了一格)` / `("ended", None)`。
        全部有界：换片次数 < `max_plots_per_day`，总走回次数 < `max_plots_per_day`，
        frontier 另有 `FRONTIER_CLEAR_MAX`/天的上界。
        """
        marked = self._mark_resume_no_output(obs, plot)
        from_area = str(plot.get("area") or "")
        from_anchor = self._resume_anchor(plot)
        alt: dict[str, Any] | None = None
        if self.resume_switches < self.max_plots_per_day:
            alt = self._resume_plot(obs, avoid_area=from_area)
        if alt is not None:
            self.resume_switches += 1
            to_anchor = self._resume_anchor(alt)
            self._journal(
                "plot_exhausted", recovered=self.resume_switches, zone=self.zone_name,
                source="resume_ledger", repeated=bool(repeated),
                from_area=from_area,
                from_anchor=[from_anchor[0], from_anchor[1]] if from_anchor else None,
                to_area=str(alt.get("area") or ""),
                to_anchor=[to_anchor[0], to_anchor[1]] if to_anchor else None,
                to_tiles=len(alt.get("tiles") or []),
                stalled_tiles=marked, stalled_total=len(self.resume_stall_tiles),
                switches=self.resume_switches, limit=int(self.max_plots_per_day),
                pending=len(self._pending_work()),
                note="回片区连续拿不出目标 ⇒ 换到另一片的账本待做格再看：坐标全部来自 "
                     "leftover_targets 记账（不含臆造/已封/被围格）")
            rep.notes.append(
                f"回片区拿不出目标 ⇒ 换到另一片（{str(alt.get('area') or '未命名片区')}）的 "
                f"{len(alt.get('tiles') or [])} 格待做格再看一次"
                f"（换片 {self.resume_switches}/{int(self.max_plots_per_day)}）")
            return "walk", alt
        # ② 当前观测里"可达 + 可清障"的格（坐标来自本张观测）——沿用 task-68 的 frontier_clear。
        if self._frontier_clear(obs, rep):
            tile = self.frontier_last_tile
            self._journal(
                "plot_exhausted", recovered=self.resume_switches, zone=self.zone_name,
                source="resume_observation", repeated=bool(repeated),
                from_area=from_area,
                from_anchor=[from_anchor[0], from_anchor[1]] if from_anchor else None,
                to_area="", to_anchor=list(tile) if tile else None, to_tiles=1,
                stalled_tiles=marked, stalled_total=len(self.resume_stall_tiles),
                switches=self.resume_switches, limit=int(self.max_plots_per_day),
                pending=len(self._pending_work()),
                note="另一片也没有可回看的账本待做格 ⇒ 先清当前观测里可达的一格"
                     "（frontier_clear；坐标来自本张观测，不臆造）")
            rep.notes.append(
                f"回片区/换片都拿不出目标 ⇒ 先清观测里可达的一格 {tile}"
                f"（frontier_clear {self.frontier_clears}/{FRONTIER_CLEAR_MAX}）")
            return "acted", None
        # ③ 确实没有可执行目标 ⇒ 诚实收工（不写 stuck；`day_justified` 由可执行面证据决定：
        #    当前观测里一格可执行格都没有才认，有活却收工照旧不 VERIFIED）。
        self._resume_exhausted(obs, rep, plot=plot, where=where, marked=marked)
        return "ended", None

    def _resume_exhausted(self, obs: dict[str, Any], rep: "DayReport", *,
                          plot: dict[str, Any] | None, where: str, marked: int = 0) -> None:
        """【task-4 / 0.7.44】【task-15 / 0.7.45】回片区/换片/观测都拿不出目标 ⇒ 诚实收工。

        * `ended_reason` 前缀 = `resume_exhausted`：不在 `JUSTIFIED_END_REASONS` 白名单；
          但【task-15】`is_justified_end` 另有一条**带证据**的分支 —— 日终"当前可执行且可达"
          的待做格为 0 时才认（证据 = `_pending_snapshot`）。**不是无条件放行**：只要观测里
          还有一格真能干（或观测证据不可用），`day_justified` 仍是 False、当天绝不 VERIFIED。
        * `ended_by` 由 `_do_sleep` 决定：睡成功 = `"sleep"`（游戏日真的前进）；
          睡失败/0 动作被拒 = 原样返回（照样不 VERIFIED）。**绝不写** `stuck:` ——
          "今天真没有可执行目标"不是卡死；0.7.43 冬 7/12/18 三天就是这么被误报成 stuck 的；
        * journal 复用既有事件 `no_progress_burst`（`exhausted=True` + 新增证据字段），不新增事件名。
        """
        plot = plot or {}
        # 事件里的 `pending` 保留**原始账本口径**（与 0.7.44 冒烟 journal 的 263/217 可直接对数）；
        # 守卫口径另记 `pending_guard`（= `_pending_work()`，已剔停滞/被围）。
        raw_pending = self._ledger_pending()
        reasons = self.work_reasons(obs)[:3]
        encircled_pending = sorted(t for t in raw_pending if t in self.encircled_day)
        from_anchor = self._resume_anchor(plot)
        # 【task-15 / 0.7.45】收工同时把"可执行面"证据一起记下来（与 day_end 同一口径）：
        # 写 resume_exhausted 的时候必须能指着数字说"当前观测里真的一格可执行格都没有"。
        # 【task-26 / 0.7.46】只有**证据成立**（executable==0 且无残缺记录）才算 resume_exhausted；
        # 若账本还有可执行格却收工（冬27 的 7 格、switch_limit 分支），前缀改成
        # `resume_budget_exhausted`：诚实说"是走路预算/换片上界用尽"，不冒充"没有可执行目标"。
        snap = self._pending_snapshot(obs)
        claim_exhausted = (int(snap["executable"]) == 0
                           and int(snap.get("malformed", 0)) == 0)
        burst_source = f"回片区（{where}）"
        self._journal(
            "no_progress_burst", count=self.no_progress_cycles,
            source=burst_source, tiles=len(plot.get("tiles") or []),
            reasons=reasons, exhausted=bool(claim_exhausted),
            claim_exhausted=bool(claim_exhausted),
            from_area=str(plot.get("area") or ""),
            from_anchor=[from_anchor[0], from_anchor[1]] if from_anchor else None,
            pending=len(raw_pending), pending_ledger=snap["ledger"],
            stalled_tiles=len(self.resume_stall_tiles),
            newly_stalled=marked, encircled_pending=len(encircled_pending),
            switches=self.resume_switches, farm_actions_today=self.farm_actions_today,
            samples=[[t[0], t[1]] for t in raw_pending[:8]],
            # 【task-26 / 0.7.46】走路预算证据（成功/尝试两个计数器）
            resume_walks=self.resume_walks,
            resume_walk_attempts=self.resume_walk_attempts,
            resume_walk_limit=int(self.max_plots_per_day),
            resume_walk_attempt_limit=2 * int(self.max_plots_per_day),
            # 【task-15 / 0.7.45】新增证据字段（事件名不变）
            pending_executable=snap["executable"], pending_blocked=snap["blocked"],
            pending_unobserved=snap["unobserved"], pending_guard=snap["guard"],
            pending_stalled=snap["stalled"],
            # 【task-22 / 0.7.45】残缺 tile 数（>0 ⇒ 当天 day_justified 必 false）
            pending_malformed=snap.get("malformed", 0),
            # 【devcoder-clear-gate】只因满包清障闸而不执行的清障格数（>0 ⇒ day_justified 必 false）
            pending_gated=int(snap.get("gated") or 0),
            # 【task-27 / 0.7.46】逐格坐标证据（有序、各前 8 条；只读、不改判据、不新增事件名）
            pending_executable_tiles=list(snap.get("executable_tiles") or [])[:8],
            pending_stalled_tiles=list(snap.get("stalled_tiles") or [])[:8],
            note=("回片区 / 换片 / 当前观测都没有可执行目标 ⇒ 今天按 resume_exhausted 诚实收工："
                  "睡下去让游戏日前进；只有当前观测里**确实没有可执行格**时 day_justified 才认这条，"
                  "否则照旧不 VERIFIED")
                 if claim_exhausted else
                 ("回片区走路预算用尽/换片上界用尽，但账本仍报可执行余格 ⇒ 按 resume_budget_exhausted "
                  "诚实收工（不是「没有可执行目标」，也不 VERIFIED；不应把预算耗尽误报成没活）"))
        rep.notes.append(
            f"回片区 {len(self.resume_stall_tiles)} 格 / 换片 {self.resume_switches} 次都拿不出目标；"
            f"当前观测可执行 {snap['executable']} 格 vs 守卫口径 {snap['guard']} 格 ⇒ 按 "
            f"{'resume_exhausted' if claim_exhausted else 'resume_budget_exhausted'} "
            f"诚实收工（day_justified 由可执行面证据决定）")
        if claim_exhausted:
            why = (f"resume_exhausted:回片区 {len(self.resume_stall_tiles)} 格都回去看过、"
                   f"换片 {self.resume_switches} 次，当前观测里没有可执行目标"
                   f"（守卫仍说：{'；'.join(reasons) if reasons else '（无）'}）"
                   + self._not_on_farm_suffix())
        else:
            why = (f"resume_budget_exhausted:回片区走路预算用尽（成功 {self.resume_walks}/"
                   f"{int(self.max_plots_per_day)}、尝试 {self.resume_walk_attempts}/"
                   f"{2 * int(self.max_plots_per_day)}）、换片 {self.resume_switches}/"
                   f"{int(self.max_plots_per_day)} 次，但账本仍有可执行余格 "
                   f"{snap['executable']} 格（守卫仍说：{'；'.join(reasons) if reasons else '（无）'}）"
                   + self._not_on_farm_suffix())
        ended_by, ended_reason = self._do_sleep(obs, rep, why)
        rep.ended_by, rep.ended_reason = ended_by, ended_reason

    # ------------------------------------------------------------------ 简报
    def _plot_brief(self, obs: dict[str, Any], plot: dict[str, Any]) -> Brief:
        """当天作业区的局部简报：清障/开垦/播种按**区**计数，浇水/收获按**全场**计数。

        为什么浇水必须全局：一天的验收要求"所有作物都浇过"，只浇作业区里的作物会漏。
        为什么开垦要按区：全场 245 个障碍会让策略永远停在"清障"（见模块 docstring 铁律 3）。
        """
        # 【task-82】第一次出简报时懒加载跨日教训库（新进程从第 1 天就能用上上一轮的教训）。
        self._lessons_load()
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
        # 【task-168】工作量缺口 + 各田区事实（进提示词，让慢脑自己看见"今天浇不完"）。
        # 计算失败一律退回 None/空（fail-closed：宁可让模型看不到，也不给它一个假 0）。
        try:
            budget_live, budget_cap, budget_deficit = self._work_budget_facts(obs)
            area_facts = self._area_facts(obs)
        except Exception:  # pragma: no cover - 简报缺口不该影响主流程
            budget_live = budget_cap = budget_deficit = None
            area_facts = ()
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
            # 【task-58】把会话内的决策史喂回提示词（空 ⇒ 提示词里不出现这一节）。
            recent_decisions=tuple(self.decision_memory),
            # 【task-59】把昨晚的复盘笔记喂回提示词（空 ⇒ 不出现这一节）。
            recent_notes=tuple(self.recent_notes),
            # 【task-82】把跨日教训库喂回提示词（空 ⇒ 不出现这一节；只读、只影响文本）。
            recent_lessons=render_lessons(self.lessons, max_items=LESSONS_INJECT_MAX,
                                          max_chars=LESSONS_INJECT_CHARS),
            # 【task-219】把能力缺口清单喂回提示词（≤3 条/≤200 字符；只提示、不进判定）。
            recent_gaps=self._gaps_brief_lines(),
            # 【task-168】工作量缺口：`None` 照实进提示词（渲染成「未观测到」），绝不当 0。
            live_crops=budget_live,
            water_capacity=budget_cap,
            water_deficit=budget_deficit,
            area_facts=area_facts,
        )

    def _review_brief(self, obs: dict[str, Any], rep: DayReport | None = None) -> Brief:
        """【task-59】收工复盘用的简报：当天最后一张观测的**全场**口径（不掺作业区局部）。

        【task-136 B】`rep` 非空时额外带一段「当天事实（账本）」（`Brief.review_facts`），
        让复盘模型看到当天的**诚实事实**（怎么收的尾、有没有放弃的干作物、片区还剩多少），
        而不是只看到乐观的派生摘要。
        """
        sellable = 0
        try:
            if self.worker is not None:
                sellable = len(self.worker.sellable_slots(obs))
        except Exception:  # pragma: no cover - 复盘简报不该影响主流程
            sellable = 0
        brief = Brief.from_observe(obs, consecutive_failures=self.fail_streak,
                                   last_failure=self.last_failure,
                                   target_tiles=self.target_tiles_base, sellable=sellable)
        if rep is not None:
            try:
                brief = replace(brief, review_facts=render_review_facts(self._review_facts(obs, rep)))
            except Exception:  # pragma: no cover - 事实段渲染失败就退回旧行为
                pass
        return brief

    def _review_facts(self, obs: dict[str, Any], rep: DayReport) -> dict[str, Any]:
        """【task-136 B】当天事实（客观账本口径）—— 取不到的一律 `None`（渲染成「未观测到」）。

        绝不用"猜一个 0"：`0` 与"没观测到"在复盘提示词里是两件事。
        """
        facts: dict[str, Any] = {
            "day_key": list(rep.day_key) if rep.day_key else None,
            "ended_by": rep.ended_by or None,
            "ended_reason": rep.ended_reason or None,
            "ok_steps": int(rep.ok_steps),
            "failed_steps": int(rep.failed_steps),
            "deferred_tiles": int(getattr(rep, "deferred_tiles", 0) or 0),
            "plot_pending": int(getattr(rep, "plot_pending", 0) or 0),
            "unreachable": int(getattr(rep, "unreachable", 0) or 0),
            "refused": int(getattr(rep, "refused", 0) or 0),
            "given_up": len(getattr(rep, "gave_up_tiles", []) or []),
            "given_up_cause": (self._far_dry_give_up_cause_text()
                               if len(getattr(rep, "gave_up_tiles", []) or []) else None),
            "water_far_not_on_farm": bool(getattr(self, "water_far_not_on_farm", False)),
            "refills_today": int(getattr(self, "far_dry_refills_today", 0) or 0),
        }
        # 浇水口径：优先用当天定稿的 `final_water`（它是 `_water_evidence` 的产物），
        # 缺它就退回农场快照的 `farm.dryCrops`（仍然"取不到 ⇒ None"）。
        final_water = getattr(rep, "final_water", None) or {}
        if isinstance(final_water, dict) and final_water:
            facts["dry"] = final_water.get("dry")
            facts["dry_scope"] = final_water.get("scope")
        farm = obs.get("farm") if isinstance(obs, dict) else None
        farm = farm if isinstance(farm, dict) else {}
        if facts.get("dry") is None and farm.get("dryCrops") is not None:
            facts["dry"] = int(farm.get("dryCrops") or 0)
            facts["dry_scope"] = "farm"
        if farm.get("crops") is not None:
            facts["crops"] = int(farm.get("crops") or 0)
        # 【task-170】熟作物优先用**游戏口径** `readyCrops`（`ripeCrops` 会把摘不到的格
        # 算成熟，复盘事实段跟着错）；旧 Mod 缺字段时退回 `ripeCrops`。
        ripe_farm = farm.get("readyCrops")
        if ripe_farm is None:
            ripe_farm = farm.get("ripeCrops")
        if ripe_farm is not None:
            facts["ripe"] = int(ripe_farm or 0)
        final = getattr(rep, "final", None) or {}
        if isinstance(final, dict):
            if facts.get("crops") is None and final.get("crops") is not None:
                facts["crops"] = int(final.get("crops") or 0)
            if facts.get("ripe") is None and final.get("ripe") is not None:
                facts["ripe"] = int(final.get("ripe") or 0)
        try:
            facts["money"] = FarmWorker.money(obs)
        except Exception:  # pragma: no cover
            facts["money"] = None
        try:
            facts["seeds"] = len(seed_items(FarmWorker.player_of(obs)))
        except Exception:  # pragma: no cover
            facts["seeds"] = None
        return facts

    def _review_before_sleep(self, obs: dict[str, Any], rep: DayReport) -> None:
        """【task-59】收工前**一次独立**的 LLM 复盘：产出 1–3 条笔记，只落两处。

        落点：①journal `review_llm`（失败 ⇒ `review_llm_failed`）；②`self.recent_notes`
        ⇒ 次日 `Brief.recent_notes`。

        为什么它影响不到当天的判定（卡面第 2 条）：
        * 调用发生在**睡前**，此时 `rep.final`/`rep.checks` 都已经定稿，复盘只往 `rep.notes`
          里追加一句人话，**不碰** `rep.verified`/`checks`/`ended_by`/`final_water`；
        * `BoundaryPlanner.review()` 不读也不写 `PlannerState` ⇒ 边界状态机、下一次决策的
          边界判定与它无关；
        * 全程 `try/except` 包住：任何异常都在这里消化成 `review_llm_failed`，睡觉与跨日
          照常（"失败无害"）。
        """
        if self.review_done_today:
            return
        planner = self.planner
        if planner is None or not getattr(planner, "llm_enabled", False):
            return
        self.review_done_today = True
        try:
            res = planner.review(self._review_brief(obs, rep))
        except Exception as exc:  # noqa: BLE001 - 再兜一层：复盘绝不许把主循环带崩
            res = {"ok": False, "called": False,
                   "reason": f"review_exception:{type(exc).__name__}: {exc}",
                   "attempts": 0, "max_tokens": 0}
        day_key: Any = None
        try:
            day_key = list(FarmWorker.day_key(obs))
        except Exception:  # pragma: no cover
            day_key = None
        if res.get("ok"):
            self.recent_notes = [str(n) for n in (res.get("notes") or [])][:3]
            # 【task-82】今晚的笔记就是今天新增教训的 `hint`（hint 只许 LLM 写；拿不到就留空）。
            self.lessons_hints = list(self.recent_notes)
            self._journal("review_llm", day_key=day_key, notes=list(self.recent_notes),
                          text=str(res.get("text") or ""), usage=res.get("usage"),
                          duration_ms=int(res.get("duration_ms") or 0),
                          model=str(res.get("model") or ""),
                          rejected=list(res.get("rejected") or []),
                          truncated=bool(res.get("truncated")),
                          # 【task-121】实际发了几次、最后一次用了多大预算（事后判断"是不是预算不够"）
                          attempts=int(res.get("attempts") or 0),
                          max_tokens=int(res.get("max_tokens") or 0),
                          note="只写 journal 与次日 recent_notes；不参与任何判定")
            rep.notes.append(f"收工复盘：{len(self.recent_notes)} 条笔记（只影响次日简报，不参与判定）")
            self._say(f"  · 收工复盘：{len(self.recent_notes)} 条笔记")
        else:
            self.recent_notes = []
            self.lessons_hints = []
            self._journal("review_llm_failed", day_key=day_key,
                          reason=str(res.get("reason") or "review_failed"),
                          called=bool(res.get("called")), rejected=list(res.get("rejected") or []),
                          # 【task-121】run9 的 `llm_error:truncated` 就是这么看出来的：
                          # `attempts=2` + `max_tokens=8192` ⇒ 预算给到 8192 仍被截断
                          attempts=int(res.get("attempts") or 0),
                          max_tokens=int(res.get("max_tokens") or 0),
                          note="复盘失败无害：睡觉与跨日照常，只是次日看不到笔记")
            rep.notes.append(f"收工复盘失败（无害）：{res.get('reason')}")

    # ------------------------------------------------------------------ 跨日教训库（task-82）
    def _lessons_load(self) -> None:
        """懒加载教训库（一次）。读不了 ⇒ 记一笔 `lessons_load_failed`，当作"没有教训"继续跑。

        【task-114 F1】载入走 `planner.load_lessons_file` 的 schema 校验（只认自己写出去的
        格式）；被丢掉的条目**必须留痕** ⇒ 记 `lessons_rejected`（`path`/`dropped`/`reasons`）。
        信任边界：这个文件是我们自己写自己读的，但一旦被外部改过，里面的自由文本会原样进
        提示词 ⇒ 一律按不可信处理（未知 kind、结构不符、超长、多行、抬高 severity 都会被洗掉）。

        【task-118 A】没带 `src == LESSON_SRC` 的条目（含旧格式整库）按**不可信**处理：
        仍进内存用于填位展示，但被钳过 `last_seq`/`count`、排不进 20 名额（见
        `planner.prune_lessons`），回写时也不会被持久化（防洗白）。这里把不可信条数一并
        记进 `lessons_rejected`，让"这个库里有多少不是自己写的"在账本里看得见。
        """
        if self.lessons_loaded:
            return
        self.lessons_loaded = True
        if self.lessons_path is None:
            return
        report: dict[str, Any] = {}
        lessons, err = load_lessons_file(self.lessons_path, report=report)
        self.lessons = lessons
        if err:
            self._journal("lessons_load_failed", path=str(self.lessons_path), error=err,
                          note="教训库读不了 ⇒ 本次当作没有教训（绝不影响判定）")
        dropped = int(report.get("dropped") or 0)
        reasons = list(report.get("reasons") or [])
        untrusted = int(report.get("untrusted") or 0)
        if dropped or reasons or untrusted:
            self._journal("lessons_rejected", path=str(self.lessons_path), dropped=dropped,
                          reasons=reasons, kept=len(lessons), untrusted=untrusted,
                          note="教训库只认自己写出去的 schema ⇒ 不合格条目被丢弃/截断；"
                               "没有 `src` 标记的条目按不可信处理（钳上界、不抢名额、不回写）；"
                               "外部改过的内容一律不可信（task-114 F1 / task-118 A）")

    def _lessons_from_day(self, rep: DayReport) -> list[dict[str, Any]]:
        """把今天的**客观账本**拍成教训（代码写事实；不写回执、不写坐标）。

        `hint` 取今晚收工复盘的第一条笔记（LLM 写的）；没有复盘 ⇒ 空串（绝不自己编）。
        """
        out: list[dict[str, Any]] = []
        seq = len(self.days) + 1
        hints = [h for h in self.lessons_hints if str(h).strip()]
        hint = str(hints[0]) if hints else ""
        # 【task-122】"一天以 stuck 收尾"的三种客观形态（任一成立即算）：①`ended_by` 以 stuck 开头；
        # ②当天出现过 `stage_midway_leftover`（同一阶段更早一轮还剩格子）；③日级账本
        # `no_unmet_stages=false`。run9 第一天正是"stuck + leftover + failed=0"，当时 8 种 kind
        # 一条都生成不出来 ⇒ run A 攒不到教训、run10 的 L1 没有素材。
        ended = str(rep.ended_by or "")
        stuck_day = (ended.startswith("stuck") or self.midway_leftover_today > 0
                     or rep.checks.get("no_unmet_stages", True) is False)
        for stage in rep.stages:
            task = str(stage.get("stage") or "")
            if not task:
                continue
            leftover = int(stage.get("leftover") or 0)
            unreach = int(stage.get("unreachable") or 0)
            refused = int(stage.get("refused") or 0)
            encircled = int(stage.get("encircled") or 0)
            failed = int(stage.get("failed") or 0)
            if unreach > 0:
                out.append(make_lesson(kind="unreachable", scope=task, day_key=rep.day_key,
                                       day_seq=seq, hint=hint,
                                       symptom=f"{task} 有 {unreach} 格四邻都站不过去",
                                       evidence=f"unreachable={unreach} leftover={leftover}"))
            if encircled > 0:
                out.append(make_lesson(kind="encircled", scope=task, day_key=rep.day_key,
                                       day_seq=seq, hint=hint,
                                       symptom=f"{task} 有 {encircled} 格被挡死（2 层内没有可清的突破口）",
                                       evidence=f"encircled={encircled} leftover={leftover}"))
            if refused > 0:
                out.append(make_lesson(kind="tool_refused", scope=task, day_key=rep.day_key,
                                       day_seq=seq, hint=hint,
                                       symptom=f"{task} 有 {refused} 格被游戏拒绝（工具等级/前置不满足）",
                                       evidence=f"refused={refused} leftover={leftover}"))
            if failed > 0 and leftover > 0:
                out.append(make_lesson(kind="stage_incomplete", scope=task, day_key=rep.day_key,
                                       day_seq=seq, hint=hint,
                                       symptom=f"{task} 有 {failed} 格没做成，还剩 {leftover} 格",
                                       evidence=f"failed={failed} leftover={leftover}"))
            # 【task-122】和 `stage_incomplete` **并存**（后者要 failed>0，这条正是 failed=0 时的
            # 唯一痕迹）：只要当天以 stuck 收尾且这一阶段还剩格子，就如实记一条。
            if stuck_day and leftover > 0:
                stopped = str(stage.get("stopped") or "")
                out.append(make_lesson(kind="stuck_with_leftover", scope=task, day_key=rep.day_key,
                                       day_seq=seq, hint=hint,
                                       symptom=f"{task} 收尾时还剩 {leftover} 格没做成、当天以 stuck 结束",
                                       evidence=f"leftover={leftover} failed={failed} stopped={stopped}"))
        # 【task-122】"换片地也找不到活"：≥2 次才算形态（1 次是正常的换片）。
        if self.plot_exhausted_today >= 2:
            out.append(make_lesson(kind="plot_exhausted", scope="plot", day_key=rep.day_key,
                                   day_seq=seq, hint=hint,
                                   symptom=f"换了 {self.plot_exhausted_today} 片地都找不到可干的活",
                                   evidence=f"plot_exhausted={self.plot_exhausted_today}"))
        if int(getattr(rep, "dry_dead", 0) or 0) > 0 and not rep.verified:
            out.append(make_lesson(kind="dead_crops_blocking", scope="farm", day_key=rep.day_key,
                                   day_seq=seq, hint=hint,
                                   symptom="枯死作物占着地，浇水和当天验收过不去",
                                   evidence=f"dead_crops={int(getattr(rep, 'dead_crops', 0) or 0)} "
                                            f"dry_dead={int(rep.dry_dead or 0)}"))
        if self.buy_no_space_today:
            # 【task-114 NIT-1】evidence 用**当次观测真值**（`buy_no_space_facts`），
            # 观测不到的字段就写"未观测到" —— 绝不写死常量、也绝不伪造。
            facts = dict(getattr(self, "buy_no_space_facts", {}) or {})
            fs_status = str(facts.get("free_slots_status") or "unavailable")
            free_txt = (f"{int(facts.get('free_slots') or 0)}/{fs_status}"
                        if facts.get("free_slots_status") else "未观测到")
            seeds_txt = (str(int(facts.get("seeds") or 0))
                         if "seeds" in facts else "未观测到")
            money_txt = (f"{int(facts.get('money') or 0)}g"
                         if "money" in facts else "未观测到")
            item_txt = str(facts.get("item") or "")
            out.append(make_lesson(kind="no_inventory_space", scope="buy", day_key=rep.day_key,
                                   day_seq=seq, hint=hint,
                                   symptom="钱够但背包没有空格，种子买不进来（要先卖一叠腾格）",
                                   evidence=f"free_slots={free_txt} seeds={seeds_txt} "
                                            f"money={money_txt} item={item_txt or '未观测到'}"))
        if rep.slept_without_work:
            out.append(make_lesson(kind="slept_without_work", scope="day", day_key=rep.day_key,
                                   day_seq=seq, hint=hint,
                                   symptom="一天里一次农场动作都没做就想收工（被拦住、没推进游戏日）",
                                   evidence=f"ended_by={rep.ended_by} 动作=0"))
        if rep.gave_up_tiles:
            out.append(make_lesson(kind="far_dry_given_up", scope="water_far", day_key=rep.day_key,
                                   day_seq=seq, hint=hint,
                                   symptom=f"有 {len(rep.gave_up_tiles)} 格窗口外干作物够不着（当天放弃）",
                                   evidence=f"gave_up={len(rep.gave_up_tiles)} dry_dead={int(getattr(rep, 'dry_dead', 0) or 0)}"))
        return out

    def _lessons_flush(self, rep: DayReport) -> None:
        """日终把今天的客观教训并进库并落盘（task-82）。

        失败无害：读不了/写不了都只记一笔 journal，跑批照常继续（不许崩、不许少一天）。
        """
        self._lessons_load()
        # 【task-136 C】"模型自述被矛盾判据丢掉"的客观计数：本次生成里给了 hint、
        # 但拍完教训后 hint 为空（= `hint_contradicts_evidence` 判定矛盾）的条数。
        # 只计数、不进判定；随 `lessons` journal 落账，供人工对照。
        hints_given = bool([h for h in self.lessons_hints if str(h).strip()])
        added = self._lessons_from_day(rep)
        if hints_given:
            self.hint_dropped_today += sum(1 for it in added if not str(it.get("hint") or ""))
        before = len(self.lessons)
        self.lessons = prune_lessons(list(self.lessons) + added)
        self.lessons_hints = []
        written = 0
        skipped_untrusted = 0
        if self.lessons_path is not None:
            save_report: dict[str, Any] = {}
            err = save_lessons_file(self.lessons_path, self.lessons, report=save_report)
            written = int(save_report.get("written") or 0)
            skipped_untrusted = int(save_report.get("skipped") or 0)
            if err:
                self._journal("lessons_save_failed", path=str(self.lessons_path), error=err,
                              note="教训库写不进去 ⇒ 本批教训只在内存里，跑批照常")
                rep.notes.append(f"教训库写失败（无害）：{err}")
        self._journal("lessons", day_key=list(rep.day_key) if rep.day_key else None,
                      added=[str(it.get("id") or "") for it in added], total=len(self.lessons),
                      dropped=max(0, before + len(added) - len(self.lessons)),
                      hint_dropped=int(self.hint_dropped_today),
                      written=written, skipped_untrusted=skipped_untrusted,
                      path=str(self.lessons_path) if self.lessons_path else "",
                      note="只有客观账本事实；hint 仅来自收工复盘的笔记；只喂提示词、不参与判定；"
                           "落盘只写 src=agentfarm 的条目（不可信条目绝不回写）")

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
        # 【task-205】工具在 Clint 那里升级 ⇒ 依赖它的阶段今天一格都干不成（工具不在身上）。
        # 返回空池是**如实**的：`_leftover` 照旧报没做完，守卫不再被"还有活"钉死
        # （`_maybe_tool_upgrade` 每天记一条 `tool_upgrade_blocked_work`，日终能看清原因）。
        if task in self._tool_suspended_stages(obs):
            return []
        # 【task-158】预算闸门（只拦 `clear_area`/`till_area`/`plant_area`，且在算目标之前）：
        # 体力不够浇完剩下的活苗 ⇒ 今天不再开新活。返回空池是**如实**的（leftover 照旧由
        # `_leftover` 报），日终 `crops_watered` 该 false 就 false —— 绝不新增可洗白键。
        _budget_why = self._budget_defer_reason(task, obs)
        if _budget_why:
            # 【task-163】把"当时还没做完的格子"一起记下来：守卫据此不再把这些格子算作
            # "还有活"，日终按任务分类留痕。**不动判据**：`leftover` 仍是如实的，
            # `budget_deferred_tiles` 只作 info，绝不参与 `checks`/`assigned_undone` 扣减。
            self._note_budget_deferred(task, _budget_why,
                                       tiles=self._leftover(task, obs, plot))
            return []

        # 【task-28 卡 D C】满包清障有界 + 满包不再新开 clear_area：
        #   ① 背包 0 空格且腾格手段用尽（`_bag_relief_evidence().exhausted`）⇒ `clear_area`
        #      目标池直接空（清障掉落必丢；开路必要前置在 `_ensure_reachable`/`open_way`
        #      内部，不经过本池，仍允许），日终由 `slot_relief{trigger=clear_gate}` 留痕；
        #   ② 全天 `loot_lost_steps` 有硬上界 `CLEAR_LOOT_LOSS_MAX_STEPS`（=5）：背包 0 空格时
        #      按剩余额度收窄阶段 limit。`loot_lost` 只是 info（task-16 口径），**绝不进 checks**。
        if task in ("clear_area", "clear_dead"):
            _bag = self._bag_relief_evidence(obs)
            _bag_free = _bag.get("free_slots")
            if task == "clear_area":
                _gate_why = self._clear_bag_gate_reason(obs)
                if _gate_why:
                    self._note_clear_area_bag_gate(task, _gate_why)
                    return []
            if _bag_free is not None and int(_bag_free) <= 0:
                _left = max(0, CLEAR_LOOT_LOSS_MAX_STEPS - int(self.loot_lost_steps_today))
                if _left <= 0:
                    self._note_clear_area_bag_gate(task, "loot_lost_steps 已到全天上限")
                    return []
                limit = min(limit, _left)

        if task == "water_area":
            # 【task-84】**枯死作物不浇水**（用户 m11003）：死苗格从目标池里剔掉。
            # 两道防线：Mod 0.7.27 起 `tiles[].tool` 对死苗不再返回 `"can"`，且
            # `farm.dryCrops`/`dryTiles` 只算活苗；这里再加窗口级判据（旧 Mod 也管用），
            # `farmwork.water()` 里还有第三道 `skipped` 兜底。
            pool = [t for t, v in tmap.items()
                    if v.get("crop") and not v.get("watered") and not v.get("dead")]
            limit = self.water_stage_tiles
        elif task == "harvest":
            # 【task-170】目标只取**游戏口径可收**（`tile_ready`）且今天还没判过"收不到"的格。
            pool = [t for t, v in tmap.items()
                    if v.get("crop") and tile_ready(v) and t not in self.harvest_gave_up]
        elif task == "clear_dead":
            # 【task-51】枯死作物**按窗口取**（与 harvest 同口径）：死苗是农场卫生问题，
            # 一个作业区里往往散着十几格（真机窗口 23 格），按区取会把它们拖到明天。
            # 只认观测里 `dead` 为真的格子 ⇒ 活苗永远进不了这个池子。
            # 局限（如实记录）：窗口（`OBSERVE_REACH` 半径）外的死苗**没有坐标**，
            # Mod 只给计数（`farm.deadCrops`）⇒ 本卡清不到，由 `clear_dead_scope` journal 留痕。
            pool = [t for t, v in tmap.items() if v.get("crop") and v.get("dead")]
        elif task == "clear_area":
            # 【task-20】防御性过滤：`toolOk == false`（明确不够格）或判不了的 clump 一族
            # **不进"可清目标"**（`_tool_blocked_tv` 是唯一权威判据）。
            # 【task-218】能力覆盖扩到 `CLEARABLE_KINDS`：普通树（0 级斧可砍）+ 够格的 clump 一族。
            # 树另受两道约束：
            #   ① 日级体力预算（`_tree_budget_left`：浇水/收获永远优先，绝不为砍树漏浇）；
            #   ② **片地优先**（范围 ③）：先砍落在本片地内/边界一圈的树，再按到片地锚点的距离
            #      —— 玩家→片地之间那几格也在观测窗口里，距离排序天然把它们排在前面。
            tree_ok = self._tree_budget_left(obs)
            anchor = tuple(plot.get("anchor") or (local[0] if local else (0, 0)))
            if local:
                xs = [t[0] for t in local]
                ys = [t[1] for t in local]
                zone = {(x, y) for x in range(min(xs) - 1, max(xs) + 2)
                        for y in range(min(ys) - 1, max(ys) + 2)}
            else:
                zone = set()
            tree_cands = [(t, v) for t, v in tmap.items()
                          if str(v.get("kind") or "") == TREE_KIND and not _tool_blocked_tv(v)]
            tree_cands.sort(key=lambda item: (0 if item[0] in zone else 1,
                                              _dist(item[0], anchor), item[0][1], item[0][0]))
            trees: list[tuple[int, int]] = []
            if tree_ok:
                room = self._tree_budget_room(obs)
                trees = [t for t, _v in tree_cands[:room]]
            # 非树障碍仍**只取片地内**（旧口径不变）：老四类 debris + 够格的 clump 一族。
            non_tree = [t for t in local
                        if (str((tmap.get(t) or {}).get("kind") or "") in ACTIONABLE_KINDS
                            or str((tmap.get(t) or {}).get("kind") or "") in CLUMP_KINDS)
                        and not _tool_blocked_tv(tmap.get(t))]
            pool = trees + non_tree
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
            elif task == "plant_area":
                # 【task-143】分配额**不得超过手上种子数**（`_seed_outlook` 第一个返回值 =
                # 背包里所有种子叠的总数）。run9c day1 实证：只剩 11 粒却分配 12 格、只剩
                # 1 粒却分配 4 格 ⇒ 阶段以 `no_seed` 停在半路，`assigned_undone` 进了
                # `no_unmet_stages` 的基数（task-134 B）⇒ 干得一格不差的一天被判不达标。
                # 这是"分配额超过资源"的口径错，不是"没干完"。
                # ⚠️ 反方向绝不许做：**不能**把 `no_seed` 塞进"诚实上限"白名单来掩盖
                # 真没做完（那是 task-135 F1/F2 打过的洗白通道）；分配额 ≤ 种子数却仍没种完 ⇒
                # 照旧 `assigned_undone>0`、照旧判 unmet。
                limit = min(limit, max(0, int(_seeds or 0)))
                # 【task-158 ②】再按体力预算收一层：`capacity` = 今天还浇得过来的新增格数
                # （`(max − 浇水预备 − 锄一格) / (播种 + 浇一格)`）。`budget_today` 为空说明
                # 还没算过预算（例如单测直接调 `_stage_tiles`）⇒ 不拦，保持旧行为。
                _cap = int((self.budget_today or {}).get("capacity") or 0)
                if self.budget_today and max(0, _cap) < limit:
                    # 【task-163 NIT-2】容量命中要看得见（旧行为静默收窄、账本里查不到）。
                    self._note_capacity_capped(task, limit, max(0, _cap))
                    limit = max(0, _cap)
        if task in ("clear_area", "clear_dead", "till_area", "plant_area"):
            # 今天已经证明"动了没用"的格子不再碰（一格最多白试一次）；
            # 再叠一道"同一格一天最多发起 MAX_TILE_ATTEMPTS 次"的兜底不变量。
            pool = [t for t in pool
                    if t not in self.blocked
                    and self.tile_attempts.get(t, 0) < MAX_TILE_ATTEMPTS]
        # 【task-5 / 0.7.44】被围住的格今天**不再进任何阶段的目标池**：A8 冬 9/14 的 1 格余量
        # 死循环就是它——`encircled` 步既不是 `failed` 也不是 `proven_inert`（task-68 刻意不封格），
        # 不吃 `tile_attempts` 配额、也不进 `blocked`，于是每一轮都被重新分配、世界不变 ⇒ stuck。
        # 只排除"今天还分不分它"：`_leftover`/`assigned_undone` 一个字不改 ⇒ 该做没做照旧如实，
        # 当日仍可不 VERIFIED（诚实优先，绝不为 no_unmet_stages 变绿放宽判据）。
        if self.encircled_day:
            pool = [t for t in pool if t not in self.encircled_day]
        # 【task-168】今天主动认输的片区**一格都不再进目标池**（防 task-124/163 那种
        # "守卫说有活、执行层又去碰"的错配复发）；`_leftover` 一个字不改 ⇒ 认输格仍算未完成。
        shed = self._shed_tile_set()
        if shed:
            pool = [t for t in pool if t not in shed]
        # 【task-27 / 0.7.46】目标池前置过滤：观测已证明"四邻既站不了、也没有可清障的突破口"
        # 的格，今天不再塞进目标池（避免整批走到跟前才发现站不过去、被记成 unreachable 打穿
        # 日级 bound；冬26 的 12 格 till + 20 格 clear 就是这一形态）。逐格按 encircled
        # （挡死）记账：写 `encircled` 事件 + 进 `encircled_day`（当天后续阶段不再选）。
        # 观测不完整（四邻没覆盖全）时**不猜**，交给执行层按证据收口（`_ensure_reachable`）。
        if task in ("clear_area", "clear_dead", "till_area", "plant_area"):
            pool = self._prefilter_known_enclosed(task, obs, pool)
        pool = sorted(set(pool), key=lambda t: (_dist(t, pt), t[1], t[0]))
        return pool[:limit]

    @staticmethod
    def _known_enclosed(obs: dict[str, Any], tile: tuple[int, int]) -> bool:
        """【task-27】观测是否已证明这格**被围死**（四邻既不可站、也没有可清障邻格）。

        判据**只看已观测证据**，观测不完整一律返回 False（不猜）：
          * 四邻必须全部出现在 `tiles[]` 里；
          * 四邻里没有任何 `standable=true`；
          * 四邻里没有"`FRONTIER_KINDS` 且没作物、且乐观口径下能站"的开路候选
            （`_standable_near` 乐观口径只用于"值不值得试一次"，不用于判死）。
        四邻里含有可清障类邻格（哪怕观测说它站不上）⇒ 不预过滤，交给 `open_way` 试。
        """
        tmap = FarmWorker.tiles_of(obs)
        neigh = [(tile[0] + dx, tile[1] + dy) for dx, dy in NEIGHBORS]
        views = [tmap.get(n) for n in neigh]
        if any(v is None for v in views):
            return False
        if any(v.get("standable") for v in views):
            return False
        for n, v in zip(neigh, views):
            kind = str(v.get("kind") or "")
            if kind in FRONTIER_KINDS and not v.get("crop") and FarmWorker._standable_near(obs, n):
                return False
        return True

    def _prefilter_known_enclosed(self, task: str, obs: dict[str, Any],
                                  pool: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """【task-27】把 `_known_enclosed` 的格从今天目标池里剔掉，并按 encircled 留痕。"""
        kept: list[tuple[int, int]] = []
        for t in pool:
            if t in self.encircled_day or not self._known_enclosed(obs, t):
                kept.append(t)
                continue
            self.encircled_day.add(t)
            try:
                kinds = FarmWorker._neighbour_kinds(obs, t)
            except Exception:                  # 观测拿不到就照实写"未知"，不编
                kinds = ["未知"] * len(NEIGHBORS)
            # 【task-78 NIT-2】逐格 journal 的字段名与 step 侧 `encircled` 事件**逐字一致**
            # （`kinds` / `tried_open`），且 reason 必须写**观测到的真实四邻 kind** —— 不许
            # 暗示"树/桩/大石"（task-27 的预过滤同样是"没有突破口"，不是某类 kind）。
            rec = {
                "tile": [int(t[0]), int(t[1])],
                "action": task,
                "stage": task,
                "zone": self.zone_name,
                "prefilter": True,
                "tried_open": 0,
                "kinds": list(kinds),
                "reason": (f"目标池前置过滤：四邻实际 kind={list(kinds)}（都已观测）；四邻既没有"
                           "可站立落脚点，也没有「可清障 + 自己够得着」的突破口 ⇒ 按 encircled"
                           "（挡死）记账：不算「走不到」、不计 `rep.unreachable`、今天后续阶段"
                           "不再选、不封格（次日/开路后可能变可达）"),
                "note": "判据见 `_known_enclosed`：四邻没全覆盖就不预过滤（不猜）",
            }
            self._prefiltered_encircled_today.append(dict(rec))
            self._journal("encircled", **rec)
        return kept

    def _leftover(self, task: str, obs: dict[str, Any], plot: dict[str, Any]) -> list[tuple[int, int]]:
        """后置条件复核：这一阶段**该做完的事**，现在还剩几格没做。

        ⚠️ 这里**刻意不排除 `self.blocked`**（"今天已经证明干不动"的格子）：`blocked` 只用来
        决定**还要不要再试**（`_stage_tiles` 会把它剔掉），**绝不能用来判定成功** —— 否则
        "动了没用"的格子会被从剩余集合里抹掉 ⇒ `met=true` ⇒ 硬失败被洗成 VERIFIED
        （真机 run2 第 1 天：`no_hard_failures=false`，阶段级却报 ok；task-3 §4 指出过同一处）。
        剩下的格子里哪些"已判定干不动"，由 `_step_stage` 在 reason 里**单独报数**，不混进判据。

        【task-163】当天被**体力预算显式延后**的任务返回 `[]`：延后是"今天不做"而不是
        "该做而没做"，否则守卫会一直说"还有活"、而 `_stage_tiles` 又拿不出目标 ⇒ 白烧一天
        且当天不可能 VERIFIED。延后的格数记在 `budget_deferred_tiles{task: n}`（只作 info）；
        **判定扣减一处不动**（`checks`/`assigned_undone` 都不看这个集合）。
        """
        if task in self._budget_deferred_tasks():
            return []
        tmap = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        local = [tuple(t) for t in plot["tiles"]]
        if task == "water_area":
            # 【task-84】与 `_stage_tiles` 同口径：枯死作物不该浇水 ⇒ 不算"该浇而没浇"的剩余。
            return [t for t, v in tmap.items()
                    if v.get("crop") and not v.get("watered") and not v.get("dead")]
        if task == "harvest":
            return [t for t, v in tmap.items() if v.get("crop") and tile_ready(v)]
        if task == "clear_dead":
            # 【task-51】与 `_stage_tiles` 同口径、**刻意不排除 `self.blocked`**（task-9 铁律）：
            # 窗口里还有枯死作物 ⇒ 这一阶段就没做完（清不掉的那些由 `_step_stage` 单独报数）。
            return [t for t, v in tmap.items() if v.get("crop") and v.get("dead")]
        if task == "clear_area":
            # 【task-218】与 `_stage_tiles` 同口径：清障能力覆盖扩到树 + 够格的 clump 一族
            # （`_tool_blocked_tv` 把 toolOk 不为 true 的 clump 挡在外面 —— 那是**能力缺口**，
            # 由 `blocked_by_tool` / `clump_blocked_backlog` 单独留痕，不算"该做而没做"）。
            # 被**日级砍树预算**挡下的树也不算 leftover（与 task-163 的"延后 ≠ 未完成"同族）；
            # 但 `self.blocked`（今天试过干不动）照旧**不排除** —— task-9 铁律。
            tree_ok = self._tree_budget_left(obs)
            out = [t for t in local
                   if (str((tmap.get(t) or {}).get("kind") or "") in ACTIONABLE_KINDS
                       or str((tmap.get(t) or {}).get("kind") or "") in CLUMP_KINDS)
                   and not _tool_blocked_tv(tmap.get(t))]
            if tree_ok:
                # 【devcoder-clear-gate C】树**只按当天预算额度**计入 leftover（与
                # `_stage_tiles` 完全同序：先本片地内/边界一圈，再按到片地锚点的距离）。
                # 旧实现把**整个观测窗口**里的树全塞进来：窗口 278 棵树 vs 片地 25 格
                # ⇒ `leftover` 被窗外树灌爆（真机 A9 实测 leftover 278 / 片地 25），
                # `leftover ⊋ assigned` 造出"0 目标、海量剩余"的假剩余。
                # 不变式保持 `leftover ⊇ assigned`：`assigned` 本就被 `_tree_budget_room` 限住。
                room = self._tree_budget_room(obs)
                anchor = tuple(plot.get("anchor") or (local[0] if local else (0, 0)))
                if local:
                    xs = [t[0] for t in local]
                    ys = [t[1] for t in local]
                    zone = {(x, y) for x in range(min(xs) - 1, max(xs) + 2)
                            for y in range(min(ys) - 1, max(ys) + 2)}
                else:
                    zone = set()
                tree_cands = [(t, v) for t, v in tmap.items()
                              if str(v.get("kind") or "") == TREE_KIND and not _tool_blocked_tv(v)]
                tree_cands.sort(key=lambda item: (0 if item[0] in zone else 1,
                                                  _dist(item[0], anchor), item[0][1], item[0][0]))
                out += [t for t, _v in tree_cands[:max(0, int(room))]]
            return sorted(set(out))
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
        # 【task-20】工具不够格/判不了的 clump 一族：**只留痕、绝不算活**。
        # 反例（不许发生）：农场里剩一块暂时敲不动的巨石 ⇒ 守卫永远说"还有活" ⇒ 永不收工。
        # 所以这里既不 append 理由，也不让它们进 `_stage_tiles` 的池子（`_tool_blocked_tv`）。
        tool_blocked = [t for t, v in tmap.items() if _tool_blocked_tv(v)]
        if tool_blocked and not self.tool_blocked_noted:
            self.tool_blocked_noted = True
            self._journal("blocked_by_tool_summary",
                          count=len(tool_blocked),
                          tiles=[list(t) for t in tool_blocked[:6]],
                          kinds=sorted({str((tmap.get(t) or {}).get("kind") or "未知")
                                        for t in tool_blocked}),
                          tools=sorted({str((tmap.get(t) or {}).get("tool") or "（未知工具）")
                                        for t in tool_blocked}),
                          note="这些格工具不够格或观测判不出 ⇒ 不算活、不进守卫理由；"
                               "当天封格（逐格 journal blocked_by_tool），次日工具升级后自动重试")
        # 【task-84】"该浇水"只看**活苗**：枯死作物浇了也没用（用户 m11003）⇒ 死苗不算活，
        # 它的去处是 `clear_dead`（`_stage_tiles("clear_dead")` 单独管）。
        unwatered = [t for t, v in tmap.items()
                     if v.get("crop") and not v.get("watered") and not v.get("dead")]
        # 【task-168】认输片区的格子不算"还有活"（主动放弃 ⇒ 守卫闭嘴；会计处照旧算未完成）。
        shed = self._shed_tile_set()
        if shed:
            unwatered = [t for t in unwatered if t not in shed]
        # 【task-205】壶在 Clint 那里升级 ⇒ "有作物没浇水"**不是今天能做的事**（工具不在身上）：
        # 这条理由会把守卫钉死一整天（`_stage_tiles("water_area")` 被暂停返回空池、
        # 决策只能 `review`）⇒ 不进理由；原因由 `tool_upgrade_blocked_work` 记一次。
        if "water_area" in self._tool_suspended_stages(obs):
            unwatered = []
        if unwatered:
            reasons.append(f"有 {len(unwatered)} 格作物没浇水")
        # 【task-170 ②】"还有熟作物"这条理由**不许被今天已经证明收不到的格子钉住**：
        # 已进 `harvest_gave_up`（试满上限仍没摘下来）或今天已封格（`blocked`：够不着/被拒）
        # 的格不算"还有活" —— run B 正是被一格裸 `ripe=true` 的作物 veto 掉整天的。
        # 注意：`_leftover("harvest")` **不排除**它们 ⇒ 当天照旧如实 unmet、不洗白。
        ripe = [t for t, v in tmap.items()
                if v.get("crop") and tile_ready(v)
                and t not in self.harvest_gave_up and t not in self.blocked]
        if shed:
            ripe = [t for t in ripe if t not in shed]
        # 【task-198】背包满/将满 ⇒ "还有熟作物"**不许**当"还能干活"的证据：
        # 那时缺的不是目标、是空格。run A′ 的形态正是 45 条 harvest 因背包满被拒、
        # `harvest_gave_up` 59 次、整天 `no_hard_failures=false`，而 `sell`/`ship` 一直在跑
        # —— 守卫却拿"农场口径还有 N 格熟作物"把每一天钉在"先去收"上（最后 `stuck:` 报废）。
        # 三态：①还能腾格 ⇒ 给一条**可执行**理由（先去腾格）；②今天已证明腾不出
        # （`inventory_blocked_today`）⇒ 熟作物理由全部闭嘴，收尾理由如实写 `inventory_blocked`；
        # ③背包不紧 ⇒ 原样。
        free_slots, bag_need, bag_status = self._bag_state(obs)
        bag_blocked = bag_status == "ok" and bag_need > 0
        ripe_work = bool(ripe)
        # 【task-240 ③】farm 级"该去种"只在**当前窗口真有 ≥1 个当季可种目标**时才算活。
        # 反例（0.7.41 冒烟 day1）：farm 口径 29 格空耕地、窗口里一格都没有 ⇒ 守卫说"该去种"、
        # `plant_area` 却 0 目标 ⇒ 连续 5 轮零变化 ⇒ `stuck:` 把整天判死（根因 B：farm 计数
        # vs 400 格窗口级目标池，两者永久不一致）。窗口有目标时才允许 farm 级理由出现。
        window_plantable = [t for t, v in tmap.items()
                            if v.get("plantable") is True and not v.get("crop")
                            and t not in self.blocked]
        # 人不在农场时"先回去"本身是可执行动作（与上面 dry/ripe 的离场口径一致）⇒ 允许；
        # 人在农场才用"窗口真有目标"卡住它（否则就是 0.7.41 冒烟 day1 的 farm/窗口错配）。
        farm_plant_reason_ok = (not self._is_farm(obs)) or bool(window_plantable)
        if ripe and not bag_blocked:
            reasons.append(f"有 {len(ripe)} 格作物熟了")
        seeds, money, can_plant = self._seed_outlook(obs)
        # 【task-163】当天被体力预算显式延后的任务不再算"还有活"：`clear_area`/`till_area`/
        # `plant_area` 三类。`harvest`/`clear_dead`/浇水**永不延后**，所以下面各条照旧。
        # 反例（不许发生）：预算把 plant_area 拦死、守卫却一直在说"该去买种子"⇒ 白烧一天。
        deferred = self._budget_deferred_tasks()
        if seeds <= 0 and can_plant and "plant_area" not in deferred:
            reasons.append(f"没种子但钱够（{money}g ≥ {self.seed_price}g），该去买")
        elif seeds <= 0 and self.seed_dead_today and not self.seed_unavail_noted:
            # 【task-67 ③b，run6 死锁的解药】今天已经确认"买不到合适种子" ⇒ "该去买"这条理由
            # **当天失效**：不然它会一直拒绝收工（`sleep_guard` 拿 `work_reasons` 判 `no_work`），
            # 而商店根本没有当季种子 ⇒ 永远满足不了 ⇒ 3 轮零变化 ⇒ `stuck` 报废整天。
            # 只留痕一次，不刷屏；明天 `_run_day` 重置后可以重试。
            self.seed_unavail_noted = True
            self._journal("seed_unavailable_today", code=self.seed_dead_today, money=money,
                          seed_price=self.seed_price, note="今天已确认买不到合适种子 ⇒ "
                          "不再把「该去买种子」当活；收工理由按真实情况写（no_work / stuck:）")
        # 【run3 真 bug B】人不在农场时，窗口观测只覆盖室内 ⇒ 上面两条必然为空。
        # 真值在 `farm` 块（`complete=true` 时 `dryCrops`/`ripeCrops` 是全农场口径）：
        # 有干作物/熟作物就是"还有活"，而且第一件事是**先回农场**（见 `_ensure_on_farm`）。
        farm_work = self._farm_scope_work(obs)
        plot_work = self._farm_plot_work(obs)
        if farm_work is None or plot_work is None:
            # 【task-96 ②】证据不可用 ⇒ **人在室内和人在农场都要给理由**（fail-closed）。
            # 旧代码只在室内给理由 ⇒ 人站在农场、最后一张快照的 `farm` 证据不可用（`complete`
            # 不为 true / 旧 Mod 没有 `dryCrops`）时这里为空 ⇒ 守卫放行 `no_work`，同时
            # `_water_evidence` 退回窗口口径（`crops==0` ⇒ `dry==0` ⇒ true）⇒ **假 VERIFIED**。
            # deputy-lead task-92 的 C8b/C8c 正是这条：真·没浇的活苗在 400 格窗口之外。
            # 【task-149 A】`hoeDirt`/`emptyDirt` 缺失同样算"证据不可用"：雨天里
            # `dry/ripe/dead` 全 0 只说明"作物没事"，不说明"没有地可以种"。
            reasons.append(self._farm_evidence_reason(obs))
        elif not self._is_farm(obs):
            dry, ripe = farm_work
            # 【task-168】farm 级读数扣掉当天主动认输的活苗（有明确记录才扣）。
            shed_live = self._shed_live_crops()
            dry = max(0, dry - shed_live)
            if dry > 0:
                reasons.append(f"人不在农场，但 farm 口径还有 {dry} 格干作物（先回去浇）")
            ripe_live = max(0, ripe - len(self.harvest_gave_up) - shed_live)
            if ripe_live > 0:
                ripe_work = True
                if not bag_blocked:
                    reasons.append(f"人不在农场，但 farm 口径还有 {ripe_live} 格熟作物（先回去收）")
        if plot_work is not None and "plant_area" not in deferred:
            # 【task-149 A】农场级"还有耕地/空地"来源（与人在不在农场无关）：
            # 雨天作物被浇好之后，run9c 只剩这一条能说明"地里还有活"。
            # 【task-163】`plant_area` 被体力预算延后时这条**也不算活**（今天不打算种）。
            _hoe_f, empty_f, seeds_f = plot_work
            # 【task-240 ③】人**在农场**且窗口没有可执行目标 ⇒ farm 计数**不许**变成
            # "该去种/该去买"（farm 计数 vs 400 格窗口目标池错配 = 根因 B）；人不在农场时
            # 例外：先回农场是可执行动作（与 batch 里 dry/ripe 的离场口径一致）。
            if empty_f > 0 and seeds_f > 0 and farm_plant_reason_ok:
                reasons.append(f"farm 口径还有 {empty_f} 格耕地空着（手上有 {seeds_f} 粒种子）⇒ 该去种")
            elif (empty_f > 0 and seeds <= 0 and can_plant and not self.seed_dead_today
                  and farm_plant_reason_ok):
                reasons.append(f"farm 口径还有 {empty_f} 格耕地空着、但没种子；"
                               f"钱够（{money}g），该去买")
        # 【task-49】人在农场里时也要看全农场读数：窗口只有半径 ~14，农场另一头的干作物
        # 在窗口里根本不存在。run5 第 1 天 `farm.dryCrops=1` 就是这么被丢掉的。
        totals = self._farm_totals(obs)
        if self._is_farm(obs) and totals is not None:
            dry_f, ripe_f = totals
            # 【task-168】farm 级读数扣掉当天主动认输片区的活苗（有明确记录才扣）。
            shed_live_f = self._shed_live_crops()
            dry_f = max(0, dry_f - shed_live_f)
            ripe_f = max(0, ripe_f - shed_live_f)
            if dry_f > len(unwatered):
                # 【task-50】干作物常常在玩家 400 格窗口之外 ⇒ 理由里带上 Mod 报的坐标，
                # 否则"还有 1 格干"既没法行动、也没法在收尾时点名（run5 三天全挂的形态）。
                # 【task-84 ③】但**全部已认输**时不再当"有活"：run7 summer 3/5 就是
                # 追着一株够不着的死苗整天换片地（每天 11 片 × 空转），summer 6 空转
                # 4.5 分钟后靠 `stuck_flush` 翻篇。收尾交给 `sleep_guard` 的 `gave_up_dry`
                # 如实记（`day_justified=False`、当天不 VERIFIED），而不是刷"还有活"。
                if not self._far_dry_all_given_up(obs):
                    reasons.append(self._far_dry_reason(obs, dry_f))
            # 【task-170 ②】farm 级熟作物数也要扣掉今天已判过、收不到的格（否则守卫被钉住）。
            ripe_f_live = max(0, ripe_f - len(self.harvest_gave_up))
            if ripe_f_live > len(ripe):
                ripe_work = True
                # 【task-199】有 `readyTiles` 坐标时给**可执行**理由（"去 X 收"，带坐标）；
                # 旧 Mod（`unavailable`）退回老文案（fail-closed，守卫照旧不判没活）；
                # 坐标可信但**全部认输** ⇒ 不 append（收尾理由会点名坐标与因由）。
                # 这条与 task-198 的 `bag_blocked` 门同族：拿不出行动的"还有活"不许进守卫理由。
                if not bag_blocked:
                    _far_ready, _far_status = self._ready_far_tiles(obs)
                    if _far_status == "unavailable":
                        reasons.append(f"农场口径还有 {ripe_f_live} 格熟作物（当前窗口只看到 "
                                       f"{len(ripe)} 格；旧 Mod 没给 readyTiles 坐标 ⇒ "
                                       "fail-closed，按老行为继续干）")
                    elif _far_ready or not self._ready_far_all_given_up(obs):
                        reasons.append(self._ready_far_reason(obs, ripe_f_live))
        # 【task-49】今天**已经见过、但还没做完**的格子（`_step_stage` 的 `leftover`）。
        # 换到别的片地之后，那些格子不在玩家窗口里 ⇒ 必须靠这份记账才知道"还有活"，
        # 否则就是 run5 的 `no_work` 早睡。已封格（`tool_ineffective` 一类）**不算** ——
        # 那正是"这一格今天真干不动"的结论（反向用例：全部 leftover 都封了 ⇒ 允许 `no_work`）。
        pending = self._pending_work()
        # 【task-198 ②】背包满/将满时"跨片地遗留"也**不许**当"还能干活"的理由：那些格子要收/要装，
        # 而背包堵住 ⇒ 唯一的可执行动作是腾格（见下面的 bag_blocked 分支）。`_leftover` 照旧
        # 如实保留这些格（`no_unmet_stages` 不受影响）—— 语义是"不是没活，是背包堵住"。
        # 【devcoder-clear-gate E】同理，被满包清障闸**单独**闸住的清障格今天不算"还有活"：
        # 执行层整池清零（`_stage_tiles` 返回 []），守卫再喊"还有 N 格没做完"只会把主循环钉死
        # （A9 冬 27/28：快照 exec=206/195、守卫喊有活、`_ensure_plot` 永不为 None ⇒ 3 轮 idle
        # ⇒ `stuck:`）。注意：**只**从这条"跨片地遗留"理由里扣掉它们，`_leftover` 的会计公式
        # 一个字没动（该做没做照旧如实、当天照旧不 VERIFIED）；收尾口是 `_end_clear_gate`。
        if pending and not bag_blocked:
            _gated_set = self._gated_tile_set(obs)
            if _gated_set:
                pending = [t for t in pending if t not in _gated_set]
            if pending:
                reasons.append(
                    f"今天早些时候还有 {len(pending)} 格没做完（跨片地，最近的是 "
                    f"{list(min(pending, key=lambda t: _dist(t, FarmWorker.player_tile(obs))))}）")
        for cand in self._plot_candidates(obs):
            if self._plot_has_work(obs, cand["tiles"]):
                reasons.append(f"{cand.get('zone') or '附近'}还有地要清/开/种")
                break
        # 【task-198】背包满/将满且有熟作物要收 ⇒ 唯一可执行的"活"是**先腾格**。
        # 今天已证明腾不出来（`inventory_blocked_today`）时**不 append** —— 守卫据此允许收工，
        # 收尾理由由 `sleep_guard` 写成 `inventory_blocked`（诚实、非 hard failure、不假 VERIFIED）。
        if bag_blocked and ripe_work and not self.inventory_blocked_today:
            reasons.append(f"背包将满/已满（空格 {free_slots}，只有 {SLOT_RESERVE} 格余量）⇒ "
                           f"先去出货/卖材料腾格，腾出空格才能收熟作物")
        return reasons

    def _pending_work(self) -> list[tuple[int, int]]:
        """今天"见过但还没做完、且今天没被证明干不动"的格子（task-49）。

        判据与 `_stage_tiles` 的排除项一致：**已封格不算**（`self.blocked` 是
        "判据证明这一格今天干不动"）。`tile_attempts` 到顶的格子仍然算 —— 它们是
        "今天试过但没做成"的真目标，允许守卫因此不判 `no_work`（当天会如实 `stuck`/
        needs_review，而不是洗成"没活"）。

        【task-163】被**体力预算显式延后**的格子也不算：延后是"今天不做"，与"干不动"不同 ⇒
        它们不该再让守卫说"还有活"（延后格数在 `budget_deferred_tiles{task: n}` 里如实记着）。

        【task-15 / 0.7.45】**两套口径对齐**：守卫原先只认 `blocked`，而卡 1 换片机制把
        "回去看过、拿不出目标"的格标进 `resume_stall_tiles` 后，它们**仍被算成"还有活"** ——
        0.7.44 冒烟冬 26/27 的 263/217 格就是这么来的（冬 27 甚至 217/217 全部标了停滞、
        守卫还报 217）。现在同样剔除：
        * `resume_stall_tiles` = 换片/回片区已回去看过、当前确实拿不出目标的格（今天不算"活"，
          日终在 `pending_stalled` 如实留痕，不进任何豁免）；
        * `encircled_day` = 四邻没有突破口、今天物理上够不着的格（task-5 已不分配，守卫同口径）。
        **诚实边界**：剔除只影响"今天还有没有活"这一个判断；`_leftover`/`plot_pending`/
        `no_unmet_stages` 的既有会计公式一个字没动（该做没做照旧如实，见 day_end 的
        `plot_pending*` / `stage_midway_leftover`）。
        """
        defer = self._budget_deferred_tile_set()
        # 【task-170 ②】今天已判"收不到"的收获格同样不算"还有活"（否则守卫被一格钉住）。
        # 【task-168】认输片区的格子也不算（主动放弃 ⇒ 守卫闭嘴；会计处照旧算未完成）。
        shed = self._shed_tile_set()
        return sorted(t for t in self.leftover_targets
                      if t not in self.blocked and t not in defer
                      and t not in self.harvest_gave_up and t not in shed
                      and t not in self.resume_stall_tiles
                      and t not in self.encircled_day)

    def _dead_tile_set(self) -> set[tuple[int, int]]:
        """【task-5 / 0.7.44】今天**"物理/判据挡死"**的格子：`blocked` ∪ `encircled_day`。

        用途只有两个：
        * `_stage_tiles`：这些格今天不再进任何阶段的目标池（否则 1 格阶段会被一轮轮重分）；
        * `_step_stage`/日终：把 leftover 拆成"可执行余格 vs 物理挡死格"两个**只作 info** 的数。

        `blocked` 已经含"动了没用"、`unreachable`（task-52）、`refused`（task-63）、
        `blocked_by_tool`（task-20，含 `backlog`）；`encircled`（task-68）刻意**不写 blocked**
        （不封格：开路后/次日可能可达），所以这里显式并进来 —— **只用于"今天不再分配/不可执行"
        这一层，不等于把 encircled 封格**：`blocked` 本身一个字没动，`_leftover` 也照旧如实计。
        """
        return set(self.blocked) | set(self.encircled_day)

    def _gated_tile_set(self, obs: dict[str, Any]) -> set[tuple[int, int]]:
        """【devcoder-clear-gate E】今天**只因满包清障闸**而不执行的清障格坐标集合。

        判据与 `_stage_tiles` / `_pending_snapshot` 同源（闸未生效 ⇒ 空集；闸生效时取快照的
        `gated_tiles`，即"其余前置条件本来允许、只因背包闸而不做"的那批格）。用途只有一处：
        `work_reasons` 报"跨片地还有 N 格没做完"时把她们扣掉 —— 否则守卫会一直喊"还有地要清"，
        而执行层整池清零 ⇒ 主循环空转到 `stuck:`（A9 冬 27/28）。

        **不改会计**：`_leftover` / `plot_pending` / `assigned_undone` 一个字没动（该做没做
        照旧如实、当天照旧不 VERIFIED）；证据不可用 ⇒ 返回空集（fail-open：不扣，守卫照旧
        喊活，不会洗白）。
        """
        if not self._clear_bag_gate_reason(obs):
            return set()
        snap = self._pending_snapshot(obs)
        return {(int(t[0]), int(t[1])) for t in (snap.get("gated_tiles") or [])}

    def _ledger_pending(self) -> list[tuple[int, int]]:
        """【task-15 / 0.7.45】**原始账本口径**的待做余格（守卫口径的母集）。

        = `leftover_targets` − `blocked` − 预算延后 − 认输 − 收不到；**不**剔
        `resume_stall_tiles`/`encircled_day`。历史意义与旧 `_pending_work()` 完全一致
        （0.7.44 冒烟里 journal 的 `pending=263/217` 就是这个口径），保留给证据/会计；
        "守卫今天还算不算活"看 `_pending_work()`（它在此之上再剔停滞/被围格）。
        """
        defer = self._budget_deferred_tile_set()
        shed = self._shed_tile_set()
        return sorted(t for t in self.leftover_targets
                      if t not in self.blocked and t not in defer
                      and t not in self.harvest_gave_up and t not in shed)

    def _dead_end_pending(self) -> list[tuple[int, int]]:
        """【task-5 / 0.7.44】账本里**只剩"挡死"余格**时返回它们，否则 `[]`。

        判据只看"还能不能执行"：账本余格必须**全部**落在 `encircled_day`（四邻没突破口）或
        `resume_stall_tiles`（卡 1：回去看过、仍然拿不出目标）；`blocked` 的格本来就被排除。
        这种日子再按窗口候选分配只会重分同一个做不成的格（A8 冬 9/14：1 格阶段 28/62 轮、
        世界不变 ⇒ 3 轮 idle 判 stuck）⇒ 调用方应走卡 1 的换片/`resume_exhausted` 诚实收工。

        【task-15 / 0.7.45】这里**刻意不用 `_pending_work()`**：后者已经把停滞/被围格当作
        "今天不算活"剔掉（守卫口径），而本函数要回答的是"账本里**只剩**挡死格吗" ——
        用剔除后的集合会永远得到 `[]`、把这条兜底路径变成死代码。所以走 `_ledger_pending()`。
        """
        pending = self._ledger_pending()
        if not pending:
            return []
        if not all(t in self.encircled_day or t in self.resume_stall_tiles for t in pending):
            return []
        return [t for t in pending if t not in self.blocked]

    # ------------------------------------------------- task-15：可执行面快照
    @staticmethod
    def _standable_next_to(obs: dict[str, Any], tile: tuple[int, int]) -> bool:
        """`tile` 的四邻里有没有"能站"的格（够不够得着）。

        与 `farmwork.FarmWorker._standable_near` 同口径：观测明确 `standable=true`、玩家此刻
        就站在旁边、或该邻格**没被观测覆盖**（交给 Mod 试）都算够得着；四邻都看过且都不能站
        ⇒ 够不着。观测没覆盖的邻格按"可能能站"处理 —— fail-closed 方向是**别把真活洗白**
        （宁可算可执行 ⇒ 当天不判 VERIFIED）。
        """
        tmap = FarmWorker.tiles_of(obs)
        try:
            pt = FarmWorker.player_tile(obs)
        except Exception:  # pragma: no cover - 观测缺 player 时按"不知道站哪"处理
            pt = None
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (tile[0] + dx, tile[1] + dy)
            if pt is not None and n == pt:
                return True
            ntv = tmap.get(n)
            if ntv is None or ntv.get("standable"):
                return True
        return False

    def _pending_snapshot(self, obs: dict[str, Any] | None) -> dict[str, Any]:
        """【task-15 / 0.7.45】日终"还有活"的**可执行面快照**（`day_justified` 的唯一"活"口径）。

        输入 `obs` 应是当天**最后一张户外农场观测**（调用方从 `outdoor_obs` 取；没有则传
        `None`）。输出（全部是**并列读数**，不互相推导豁免）：

        * `ledger` = **原始账本**口径的余格（`leftover_targets` − 预算延后 − 认输 − 收不到；
          0.7.44 冒烟 journal 里的 `pending=263/217` 就是这个口径）；
        * `blocked` = ledger 里今天**已判死**的格（`blocked` ∪ `encircled_day` ∪
          `resume_stall_tiles`：干不动/走不到/被围住/回去看过拿不出目标）；
        * `stalled` = 其中"停滞/被围"那一类的子集（`resume_stall_tiles` ∪ `encircled_day`），
          单列给 Lead 的对账表用；
        * `guard` = `_pending_work()`（ledger − 已判死之后的"守卫口径"待做；
          不变式 `guard + blocked == ledger`）；
        * `executable` / `unobserved` / `malformed` = 对 `guard` 里的格按最后一张户外观测分类：
          看得见 + 确实要做 + 预算/工具允许 + 站得到 ⇒ `executable`；**不在 `tiles[]`**（截断/
          不在视野）⇒ `unobserved`（不变式 `executable + unobserved + malformed == guard`）；
        * 【task-22】`malformed` = **在 `tiles[]` 里出现、但缺工作种类字段**的残缺记录
          （例如 `{"tile":[60,10]}` 只有坐标，没有 `kind`/`crop`，也不在 `tillable[]`）——
          **绝不许算 unobserved**：那是"观测坏了"而不是"没有活"。它单独计数，
          调用方用 `is_justified_end(..., malformed_tiles=...)` 强制 `day_justified=false`
          （fail-closed，堵 deputy NIT-1 的洗白通道）；
        * 【devcoder-clear-gate】**`gated`** = **唯一**被「满包清障闸」（`_clear_bag_gate_reason`
          ⇒ 背包 0 空格 + 腾格手段用尽）挡住、其余前置条件（预算/工具）本来都允许的清障类格
          （`CLEARABLE_KINDS`：weed/twig/stone/grass + 树 + 够格 clump）。它们**不并入
          `unobserved`**：那等于把"今天被闸住"说成"看不见/已陈旧"（是谎，会让账本对不上
          `_stage_tiles` 整池清零的事实）。单独成桶 ⇒ 调用方用
          `is_justified_end(..., gated=...)` 强制 `day_justified=false`（fail-closed：
          `clear_gate` 收尾永不 VERIFIED）；
        * `ledger == guard + blocked`、`guard == executable + unobserved + malformed + gated`。

        观测不可用（`obs is None` / 不是农场观测）⇒ **全部按可执行计**（fail-closed：不许把
        "没看到"当"没有"，`day_justified` 因此不放行）。

        分类顺序：已判死（`blocked`/`encircled_day`/`resume_stall_tiles`）→ 不在 `tiles[]`
        ⇒ unobserved（这正是 0.7.44 冒烟 263/217 被判成"还有活"的病灶）→ 【task-22】在
        `tiles[]` 但缺工作种类字段 ⇒ malformed → 看得见但今天已不需要做 ⇒ unobserved →
        【devcoder-clear-gate】本来允许、只因满包清障闸而不允许的清障格 ⇒ gated →
        要做但不允许/站不到 ⇒ unobserved（"今天没证据能执行"）→ 其余 executable。
        """
        defer = self._budget_deferred_tile_set()
        shed = self._shed_tile_set()
        universe = [t for t in self.leftover_targets
                    if t not in defer and t not in self.harvest_gave_up and t not in shed]
        dead = self._dead_tile_set()
        stalled_set = set(self.resume_stall_tiles) | set(self.encircled_day)
        blocked_tiles = [t for t in universe if t in dead or t in self.resume_stall_tiles]
        guard_tiles = [t for t in universe
                       if t not in dead and t not in self.resume_stall_tiles]
        base = {"ledger": len(universe), "guard": len(guard_tiles),
                "stalled": sum(1 for t in universe if t in stalled_set),
                "blocked": len(blocked_tiles),
                # 【task-27 / 0.7.46】并列只读坐标（有序，≤8 条由调用方截断）：让 day_end /
                # no_progress_burst 能逐格对账"到底哪几格算停滞、哪几格算可执行"。
                "stalled_tiles": [list(t) for t in sorted(t for t in universe if t in stalled_set)],
                }
        farm: dict[str, Any] | None = obs if (obs is not None and self._is_farm(obs)) else None
        if farm is None:
            # 观测证据不可用 ⇒ 不许声称"没有可执行的活"（executable 取全量 ⇒ day_justified 不放行）
            return {**base, "executable": len(guard_tiles), "unobserved": 0, "malformed": 0,
                    "gated": 0,
                    "executable_tiles": [list(t) for t in sorted(guard_tiles)],
                    "gated_tiles": [],
                    "malformed_tiles": []}
        tmap = FarmWorker.tiles_of(farm)
        tillable = FarmWorker.tillable_of(farm)
        _seeds, _money, can_plant = self._seed_outlook(farm)
        deferred = self._budget_deferred_tasks()
        # 用无副作用的预算读数（`_tree_budget_left` 会排队 `deferred_by_budget` 事件，别在日终再记一遍）
        tree_ok = (not self._budget_defer_reason("clear_area", farm)
                   and self._tree_budget_room(farm) > 0)
        free_slots, bag_need, bag_status = self._bag_state(farm)
        bag_blocked = self.inventory_blocked_today or (bag_status == "ok" and bag_need > 0)
        # 【devcoder-clear-gate】满包清障闸：与执行层（`_stage_tiles("clear_area")` 整池清零）
        # **同一判据**。它只解释"清障类格为什么今天不执行"，不并入 unobserved（那是"看不见/
        # 已陈旧"的谎），单列 `gated` 桶并由 `is_justified_end(gated=…)` fail-closed。
        gate = self._clear_bag_gate_reason(farm)
        executable = unobserved = malformed = gated = 0
        exec_tiles: list[tuple[int, int]] = []
        malformed_tiles: list[tuple[int, int]] = []
        gated_tiles: list[tuple[int, int]] = []
        for t in guard_tiles:
            tv = tmap.get(t)
            if tv is None:
                unobserved += 1          # 不在 tiles[]（含截断）⇒ 看不见、不算活
                continue
            kind = str(tv.get("kind") or "")
            # 【task-22】记录在 tiles[] 里、却缺"工作种类"字段（无 crop、无 kind、也不在 tillable）
            # ⇒ 观测残缺/字段被改名，不能当"没活"：单列 malformed 并强制 not justified。
            if not tv.get("crop") and not kind and t not in tillable:
                malformed += 1
                malformed_tiles.append(tuple(t))
                continue
            need = False
            allowed = True
            if tv.get("crop"):
                if not tv.get("watered") and not tv.get("dead"):
                    need = True                       # 该浇（浇水永不延后）
                elif (not tv.get("dead") and tile_ready(tv)
                        and t not in self.harvest_gave_up):
                    need = True                       # 该收；背包堵住 ⇒ 今天不可执行
                    allowed = not bag_blocked
                elif tv.get("dead"):
                    need = True                       # 该清死苗
            elif kind in ACTIONABLE_KINDS:
                need = True
                allowed = "clear_area" not in deferred
            elif kind in CLUMP_KINDS:
                need = True
                allowed = "clear_area" not in deferred and not _tool_blocked_tv(tv)
            elif kind == TREE_KIND:
                need = True
                allowed = "clear_area" not in deferred and tree_ok
            elif t in tillable:
                need = bool(can_plant) and "till_area" not in deferred
                allowed = need
            elif kind == "dirt":
                need = bool(can_plant) and "plant_area" not in deferred
                allowed = need
            if not need:
                unobserved += 1          # 已做/账本陈旧：今天不需要做，不算活
                continue
            # 【devcoder-clear-gate】"其余前置条件本来就允许、只因满包清障闸而不允许"的清障格
            # ⇒ 单列 gated（不并入 unobserved）。工具不够格/预算挡下的树**不算** gated：
            # 那是能力/预算缺口，与背包无关（`allowed` 在加闸之前就已为 False）。
            if (gate and allowed and not tv.get("crop")
                    and kind in CLEARABLE_KINDS):
                gated += 1
                gated_tiles.append(tuple(t))
                continue
            if not allowed or not self._standable_next_to(farm, t):
                unobserved += 1          # 预算延后/工具不够/背包堵/四邻没得站 ⇒ 今天不可执行
                continue
            executable += 1
            exec_tiles.append(tuple(t))
        return {**base, "executable": executable,
                "unobserved": unobserved, "malformed": malformed, "gated": gated,
                "executable_tiles": [list(t) for t in sorted(exec_tiles)],
                "gated_tiles": [list(t) for t in sorted(gated_tiles)],
                "malformed_tiles": [list(t) for t in sorted(malformed_tiles)]}

    # ------------------------------------------------ task-124：review 独苗的对账路径

    @staticmethod
    def _is_review_only(decision: Any) -> bool:
        """这一轮的意图**全是** `review`（没有一条能落地）吗？（task-124）

        run9（0.7.29）第 1 天：61 条 `['review']` 独苗决策，`source=deterministic`
        —— 当前**片地**的简报四条分支都不成立 ⇒ `deterministic_plan` 给 `review`；而
        `work_reasons`/`sleep_guard` 用的是**跨片地当日 leftover**（"今天早些时候还有 14 格
        没做完"）。两边没有对账路径：`_verify_intents` 对非阶段意图直接放行、`review` 不置
        `acted`、`_fallback_decision` 只在 kept 为空时才被调用 ⇒ 3 轮零变化 ⇒ `stuck`。
        """
        intents = list(getattr(decision, "intents", ()) or ())
        return bool(intents) and all(str(getattr(i, "task", "")) == "review" for i in intents)

    def _plot_exhausted_burst(self) -> int:
        """同一秒内连续判"这一片没目标"的次数（task-124）。

        真机形态：run9 第 2 天 `plot_exhausted` 在 0.6 秒里连发 12 次 —— 每轮换一片、每片都
        拿不出目标，纯空转。同一秒 ≥ `PLOT_EXHAUSTED_BURST` 次就判定"本片真没目标"，记一条
        `plot_exhausted_burst` 后按既有有界机制结束当天换片循环。
        """
        try:
            stamp = float(self.now())
        except Exception:                       # pragma: no cover - now 是注入的
            stamp = 0.0
        if self._plot_exhausted_last is None or stamp - self._plot_exhausted_last >= 1.0:
            self._plot_exhausted_window = 0
        self._plot_exhausted_last = stamp
        self._plot_exhausted_window += 1
        return self._plot_exhausted_window

    def _resume_reevaluate(self, *, where: str) -> list[str]:
        """回跨片区 leftover 之前，清掉当日"已证明没目标"的**任务级**记账（task-134 A）。

        run9b t=290.78–293.72：`work_spot{tiles:9}` 与 `resume_walk{walked:true}` 在 2.6 秒里
        各 **10 次**交替出现、一格动作都没做 —— 因为 `clear_area`/`plant_area` 已被
        `_mark_no_target` 记进 `self.no_target`，人走回去以后 `_review_only_fallback` 的意图
        过滤（`blocked = no_target | no_target_global`）把意图**全滤空** ⇒ 0 动作轮 ⇒
        走路 → 空转 → 再走路。换片地那条路早就 `self.no_target.clear()`（plot_exhausted 分支），
        resume 路径漏了这一步。

        只清**任务级** `no_target`（"这一片拿不出目标"的片区级记账）；`no_target_global`
        （全农场口径证明过没目标的任务）**不动** —— 把它也清掉才是真洗白。
        """
        cleared = sorted(self.no_target)
        self.no_target = set()
        if cleared:
            self._journal("resume_reevaluate", where=where, cleared=cleared,
                          note="回到跨片区 leftover 之前清掉任务级 no_target，让这批格重新"
                               "参与取目标（否则意图被滤空 ⇒ 走路→空转→再走路的死循环）")
        return cleared

    def _review_only_fallback(self, obs: dict[str, Any],
                              rep: DayReport) -> tuple[Any | None, bool]:
        """review 独苗 + 守卫说还有活 ⇒ 换成能落地的意图，或把人带回那片地（task-124）。

        为什么**不能**拿当前片地的简报再跑一次 `deterministic_plan`：那份简报正是"本片没活了"
        的来源（run9 第 1 天四条分支全不成立 ⇒ `review`），再算一次只会再得一个 `review`
        —— 原地死循环（Lead m11194）。所以按"守卫到底在抱怨什么"分两步：
          ① 观测里**看得见**的收尾活（`_work_spot_plot`：没浇/熟了/枯死的作物格）⇒ 用它的容器
             出简报再跑确定性策略（视窗内 ⇒ 计数不为 0，能挑出 `water_area`/`harvest`/`clear_dead`）；
          ② 只剩**跨片地 leftover**（人看不见）⇒ 不做计划，直接把人带回那些格子旁边
             （`_resume_plot` + `_walk_into_plot`），让下一轮观测重新看见它们。

        返回 `(decision_or_None, walked)`；`walked=True` 时调用方 `continue` 跑下一轮。
        """
        blocked = self.no_target | self.no_target_global
        reasons = self.work_reasons(obs)
        spot = self._work_spot_plot(obs)
        if spot is not None:
            brief: Brief | None = None
            try:
                brief = self._plot_brief(obs, spot)
            except Exception as exc:            # pragma: no cover - 防御性
                self._journal("review_only_fallback_failed", source="work_spot",
                              error=f"{type(exc).__name__}: {exc}"[:200])
            if brief is not None:
                intents = [i for i in deterministic_plan(brief)
                           if i.task not in blocked and i.task != "review"]
                if intents:
                    self.plot = spot
                    self.zone_name = str(spot.get("zone") or "")
                    self.idle_rounds = 0
                    self._journal("review_only_fallback", source="work_spot",
                                  plot_tiles=len(spot.get("tiles") or []),
                                  intents=[i.task for i in intents], reasons=reasons[:6],
                                  note="只有 review 却有活 ⇒ 改按观测里看得见的收尾活出意图")
                    rep.notes.append(
                        f"只有 review 却有活（{'；'.join(reasons[:2]) or '守卫说有活'}）⇒ "
                        f"改按 {len(spot.get('tiles') or [])} 格待浇/待收/待清的作物挑目标："
                        f"{[i.task for i in intents]}")
                    return SimpleNamespace(intents=intents), False
        pending = self._pending_work()
        # 【task-15 / 0.7.45】守卫口径的 pending 已把"停滞/被围"格剔除；只剩挡死格时它会是空集，
        # 但这条兜底仍必须接管（否则会掉回调用方的 stuck / no_work）⇒ 用 `_dead_end_pending()`
        # 补上"账本里只剩挡死格"的情形。
        # 【task-26 / 0.7.46】预算口径换成 `_resume_walk_available()`（成功/尝试分开封顶）。
        if (pending or self._dead_end_pending()) and self._resume_walk_available():
            self._resume_reevaluate(where="review_only_fallback")     # 【task-134 A】
            resume = self._resume_plot(obs)
            if resume is None:
                # 【task-11 / 0.7.44】pending 非空却全是"挡死/已停滞"格 ⇒ 同样走卡 1 的
                # `_resume_switch_or_exhaust`（换片→观测清一格→`resume_exhausted:`），
                # 不再直接落回调用方的 `stuck:` 收尾（deputy GAP-1）。
                dead = self._dead_end_pending()
                if dead:
                    action, alt = self._resume_switch_or_exhaust(
                        obs, rep,
                        plot={"zone": "", "label": "", "area": "",
                              "anchor": list(dead[0]), "tiles": dead,
                              "note": "只剩挡死格（review 兜底）"},
                        where="review_only_fallback")
                    if action == "ended":
                        return None, False
                    if action == "acted":
                        return None, True
                    resume = alt
            if resume is not None:
                # 【task-26 / 0.7.46】只有真走到了才用掉"回去看过"的预算；先记尝试。
                self.resume_walk_attempts += 1
                self.no_progress_cycles += 1                          # 【task-134 A】
                if self.no_progress_cycles >= PLOT_EXHAUSTED_BURST:
                    # 【task-11 / 0.7.44】不再直接 `_no_progress_stop(stuck:)`：统一路由到
                    # 卡 1 的 `_resume_switch_or_exhaust`（换片 → 观测清一格 → `resume_exhausted:
                    # 诚实收工），"拿不出目标"不许被判成卡死（deputy GAP-1）。
                    action, alt = self._resume_switch_or_exhaust(
                        obs, rep, plot=resume, where="review_only_fallback")
                    if action == "ended":
                        return None, False
                    if action == "acted":
                        return None, True       # 本轮已清一格；调用方 `continue` 重新决策
                    if alt is not None:
                        resume = alt
                walked = self._walk_into_plot(obs, resume)
                if walked:
                    # 【task-26 / 0.7.46】只有走成了才用掉"回去看过"的预算（失败尝试不计）。
                    self.resume_walks += 1
                self._journal("review_only_fallback", source="pending_walk",
                              tiles=len(resume["tiles"]), walked=bool(walked),
                              attempt=self.resume_walk_attempts,
                              walks=self.resume_walks, reasons=reasons[:6],
                              note="只有 review 却说还有活 ⇒ 回到跨片地 leftover 旁边再看一次")
                if walked:
                    self._actions += 1
                    rep.notes.append(
                        f"只有 review 却有活（{'；'.join(reasons[:2]) or '守卫说有活'}）⇒ 回到 "
                        f"{len(resume['tiles'])} 格没做完的地方再看一次"
                        f"（review 兜底成功 {self.resume_walks}/{self.max_plots_per_day}，"
                        f"尝试 {self.resume_walk_attempts}/{2 * self.max_plots_per_day}）")
                    self.plot = resume
                    self.zone_name = ""
                    self.idle_rounds = 0
                    return None, True
        return None, False

    def _abandon_guard_leftover(self, obs: dict[str, Any], rep: DayReport) -> int:
        """兜底也拿不出目标时，把守卫据以抱怨的那份 leftover 如实记为"今天放弃"（task-124）。

        不这么做 ⇒ 守卫下一轮还拿同一批格抱怨 ⇒ 继续空转到 `stuck`（Lead m11194 点名的弯路）。
        只动 `leftover_targets`（当天不再回头、也不再当"还有活"的证据），`_run_day` 每日重置
        ⇒ 次日照旧重试；**不碰任何判定字段**。
        """
        pending = self._pending_work()
        for tile in pending:
            self.leftover_targets.discard(tile)
        self._journal("review_only_no_target", pending=len(pending),
                      tiles=[[t[0], t[1]] for t in sorted(pending)[:12]],
                      reasons=self.work_reasons(obs)[:6],
                      note="确定性计划也拿不出目标 ⇒ 这些格如实记为今天放弃（次日重试），不再空转")
        if pending:
            rep.notes.append(f"确定性计划也没有目标：{len(pending)} 格今天放弃（次日重试）")
        return len(pending)

    def _guard_leftover_resume(self, obs: dict[str, Any], rep: DayReport,
                               *, text: str) -> tuple[str, bool]:
        """守卫说还有活、本片却没意图 ⇒ 回跨片区 leftover 看一眼（task-49 主修）。

        【task-11 / 0.7.44】连续无产出触顶时**不再** `_no_progress_stop(stuck:)`：统一路由到
        卡 1 的 `_resume_switch_or_exhaust`（换片 → 观测清一格 → `resume_exhausted:` 诚实收工），
        把"拿不出目标"与"卡死"分开（deputy GAP-2）。返回 `(action, walked)`：

        * `"walked"` ⇒ 已走回（调用方 `continue` 重新决策）；
        * `"acted"`  ⇒ 本轮已清一格（调用方 `continue`）；
        * `"ended"`  ⇒ 已按诚实口径收工（调用方 `break`）；
        * `"none"`   ⇒ 没走成/没得走（调用方落回既有"换片/recovered"路径）。
        """
        # 【task-15 / 0.7.45】守卫口径 pending 已剔除停滞/被围格；只剩挡死格时它为空，但诚实
        # 收口仍要接管（见 `_dead_end_pending` 的原始账本口径）。
        # 【task-26 / 0.7.46】预算口径换成 `_resume_walk_available()`（成功/尝试分开封顶）。
        if not ((self._pending_work() or self._dead_end_pending())
                and self._resume_walk_available()):
            return "none", False
        self._resume_reevaluate(where="guard_leftover")               # 【task-134 A】
        resume = self._resume_plot(obs)
        if resume is None:
            # 【task-11 / 0.7.44】pending 非空却全是挡死/停滞格 ⇒ 走卡 1 的诚实收口（GAP-2）。
            dead = self._dead_end_pending()
            if not dead:
                return "none", False
            action, alt = self._resume_switch_or_exhaust(
                obs, rep,
                plot={"zone": "", "label": "", "area": "",
                      "anchor": list(dead[0]), "tiles": dead,
                      "note": "只剩挡死格（guard_leftover）"},
                where="guard_leftover")
            if action == "ended":
                return "ended", False
            if action == "acted":
                return "acted", False
            resume = alt
            if resume is None:
                return "none", False
        self.resume_walk_attempts += 1
        self.no_progress_cycles += 1                                  # 【task-134 A】
        if self.no_progress_cycles >= PLOT_EXHAUSTED_BURST:
            action, alt = self._resume_switch_or_exhaust(
                obs, rep, plot=resume, where="guard_leftover")
            if action == "ended":
                return "ended", False
            if action == "acted":
                return "acted", False
            if alt is not None:
                resume = alt
        walked = self._walk_into_plot(obs, resume)
        if walked:
            # 【task-26 / 0.7.46】只有走成了才用掉"回去看过"的预算（失败尝试不计）。
            self.resume_walks += 1
        self._journal("resume_walk", zone=self.zone_name,
                      tiles=len(resume["tiles"]), walked=bool(walked),
                      attempt=self.resume_walk_attempts, walks=self.resume_walks,
                      note="守卫说还有活但本片没意图 ⇒ 回去看今天没做完的格子")
        if not walked:
            return "none", False
        self._actions += 1
        rep.notes.append(
            f"守卫说还有活（{text}）⇒ 回到没做完的 "
            f"{len(resume['tiles'])} 格旁边再看一次"
            f"（resume_walk 成功 {self.resume_walks}/{self.max_plots_per_day}，"
            f"尝试 {self.resume_walk_attempts}/{2 * self.max_plots_per_day}）")
        self.plot = resume
        self.zone_name = ""
        self.idle_rounds = 0
        return "walked", True

    def _frontier_clear(self, obs: dict[str, Any], rep: DayReport) -> bool:
        """【task-68】"一轮不许零动作"：世界没变化、但仍有**可达 + 可清障**的地 ⇒ 至少清一格。

        动机（Lead m06336）：目标格全被围住/走不到时，光靠"换片地"和 idle 计数会攒够 3 轮
        判 stuck、整天报废；而地里明明有能清的杂草/石头/树枝。这里只清**一格**（不是整片），
        有界（`FRONTIER_CLEAR_MAX = 20`/天），逐条 journal `frontier_clear`。
        清不动的格子由 `clear()` 自己给 `unreachable`/`encircled`，`_mark_blocked` 会照常留痕。
        """
        if self.frontier_clears >= FRONTIER_CLEAR_MAX:
            return False
        # 【task-4 / 0.7.44】记下**最近一次**真清掉的格（换片的 journal 证据用；坐标来自本张观测）。
        self.frontier_last_tile = None
        # 用逐格视图（`tiles_of`）而不是 `_tile_states`：这里要看 `kind`/`crop`/`standable`。
        tiles = FarmWorker.tiles_of(obs) or {}
        player = FarmWorker.player_tile(obs)
        cands: list[tuple[tuple[int, int, int], tuple[int, int]]] = []
        for tile, tv in tiles.items():
            kind = str((tv or {}).get("kind") or "")
            if kind not in FRONTIER_KINDS or (tv or {}).get("crop"):
                continue
            if tile in self.blocked or tile in self.encircled_day:
                continue
            # 至少要有一个"自己能站"的邻格，否则清了也白清（那属于 encircled 的形态）。
            openable = False
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                ns = tiles.get((tile[0] + dx, tile[1] + dy))
                if ns is None or (ns.get("standable") and not ns.get("crop")):
                    openable = True
                    break
            if not openable:
                continue
            dist = (abs(tile[0] - player[0]) + abs(tile[1] - player[1])) if player else 0
            cands.append(((dist, tile[1], tile[0]), tile))
        if not cands:
            return False
        cands.sort()
        # 一个候选清不动（走不到/被拒）不算"有动作" —— `_mark_blocked` 会把它记进当天 `blocked`/
        # `encircled_day`，下一轮就不会再选它；这里最多连着试 3 个，真清掉一格才算"这一轮有动作"。
        for _key, tile in cands[:3]:
            if self.frontier_clears >= FRONTIER_CLEAR_MAX:
                return False
            res = self.worker.run_stage("clear_area", [tile], min_stamina=self.min_stamina,
                                        max_steps=1)
            self._actions += len(res.steps)
            self.farm_actions_today += sum(1 for s in res.steps if s.tile and not s.skipped)
            self._count_attempts(res.steps)
            self._mark_blocked(obs, self._snap(), res.steps, rep, stage="clear_area")
            self.frontier_clears += 1
            acted = any(s.ok for s in res.steps)
            self._journal("frontier_clear", tile=list(tile), acted=bool(acted),
                          attempt=self.frontier_clears, limit=FRONTIER_CLEAR_MAX,
                          why="目标都够不着/被围住，先清一格可达的可清障格",
                          note="【task-68】一轮不许零动作：清的是可达的杂草/石头/树枝，"
                               "不是当前阶段目标")
            if acted:
                self.frontier_last_tile = (int(tile[0]), int(tile[1]))
                return True
        return False

    def _farm_evidence_reason(self, obs: dict[str, Any]) -> str:
        """`farm` 证据不可用时的"还有活"理由（task-41 NIT-2 / task-96 ②，fail-closed）。

        为什么这算"还有活"：**不知道**地里干没干 ⇒ 绝不许据此判"没活可做"（run3 连睡 4 天就是这么来的）。
        【task-96 ②】这条理由对**人在室内和人在农场**一视同仁：0.7.27 之前只有"人在室内"会走到
        这里，人站在农场 + 证据不可用时 `work_reasons()` 为空 ⇒ `no_work` + 假 `watered_outdoor`
        ⇒ 假 VERIFIED（deputy-lead task-92 的 C8b/C8c）。

        有界性**不靠** `idle_rounds`（它只在走完 `_execute` 且世界指纹没变时才涨）：`_run_day` 的
        `spot = _work_spot_plot(...) or _near_player_plot(...)` 为 `None` 那条**单次分支**会直接
        `<ended_by>="stuck"` + `break`（换片地次数也有上限），一天不空转。
        journal `farm_evidence_unavailable` 每天最多一条（`self.farm_evidence_noted`）。
        """
        farm = obs.get("farm") or {}
        loc = str((obs.get("location") or {}).get("name") or "?")
        where = "农场里" if self._is_farm(obs) else f"室内（{loc}）"
        if not self.farm_evidence_noted:
            self._journal("farm_evidence_unavailable", complete=farm.get("complete"),
                          loaded=farm.get("loaded"), location=loc, on_farm=bool(self._is_farm(obs)),
                          note="farm 证据不可用（complete/loaded/dryCrops）⇒ 不许判 no_work；"
                               "先确保站在户外农场再判，当天拿不出目标则以 stuck 如实收尾"
                               "（一天只走一次，不空转）")
            self.farm_evidence_noted = True
        return (f"人在{where}且 farm 证据不可用（farm.complete={farm.get('complete')!r}/"
                f"loaded={farm.get('loaded')!r}/dryCrops={farm.get('dryCrops')!r}）⇒ farm 口径不算证据，"
                "不许据此判『没有活』：窗口的 crops==0 不是证据（run7 那颗没浇的活苗就在窗口外）")

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
        # 【task-84】与 `work_reasons` 同口径：只有**活苗**才算"该浇水"。
        unwatered = [t for t, v in tmap.items()
                     if v.get("crop") and not v.get("watered") and not v.get("dead")]
        # 【task-205】壶在 Clint 那里升级 ⇒ 浇不了：这条 keep_working 会把守卫钉死一整天
        # （`_stage_tiles("water_area")` 已暂停返回空池）。原因由 `tool_upgrade_blocked_work` 记。
        if "water_area" in self._tool_suspended_stages(obs):
            unwatered = []
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
        if farm_work is not None and not self._is_farm(obs) and (farm_work[0] > 0 or farm_work[1] > 0):
            loc = str((obs.get("location") or {}).get("name") or "?")
            return False, "keep_working", (
                f"人在室内（{loc}）、farm 口径还有 {farm_work[0]} 格干作物 / "
                f"{farm_work[1]} 格熟作物，先回农场再说"
            )
        plot_work = self._farm_plot_work(obs)
        if farm_work is None or plot_work is None:
            # 【task-41 NIT-2 + task-96 ②】证据不可用 ⇒ fail-closed，**室内与农场一视同仁**：
            # 绝不退回窗口口径放行 `no_work`（run3 那 4 天连睡、task-92 的 C8b/C8c 假 VERIFIED
            # 都是这条缺失造成的）。理由与 `work_reasons` 共用一份实现，避免口径漂移。
            # 有界：守卫说"还有活"而本片拿不出目标 ⇒ 换片地上限 + `stuck:` 单次收尾，不空转。
            # 【task-149 A】`hoeDirt`/`emptyDirt` 缺失也算证据不可用（雨天 `dry/ripe=0` 时
            # 唯一能证明"还有地可以种"的来源就是它们）。
            return False, "keep_working", self._farm_evidence_reason(obs)
        # 【task-49】人在农场里、全农场读数说还有干/熟作物，而玩家窗口没盖到 ⇒ 必须继续干；
        # 有水（壶里 / 能走到补水点 / 无尽壶）就去浇；**确实打不到水**才允许睡，而且这里
        # 绝不能返回 `no_work`（"想浇但无水"和"没活可做"是两件事；run5 第 1 天 `dry=1` 却
        # 以 `no_work` 收场、还白拿一个 `day_justified=true`，就是这条缺失造成的）。
        totals = self._farm_totals(obs)
        if self._is_farm(obs) and totals is not None:
            dry_f, ripe_f = totals
            # 【task-170 ②】扣掉今天已判"收不到"的格：否则一格摘不到的熟作物会把守卫
            # 永远钉在 `keep_working`（run B：`veto sleep 35`、整天 0 成功）。
            ripe_f = max(0, ripe_f - len(self.harvest_gave_up))
            if ripe_f > 0:
                # 【task-199】与 `work_reasons` 同一口径：坐标可信就点名坐标；全部认输 ⇒
                # 不再拿"农场口径还有熟作物"钉住守卫（run A′ fall 13：一整天换片地空转，
                # 最后 `stuck:同一秒连发 5 次换片都没有目标`），改用 `gave_up_ready` 如实收尾
                # （不在 `JUSTIFIED_END_REASONS` ⇒ `day_justified=False` ⇒ 当天不 VERIFIED）。
                _far_ready, _far_status = self._ready_far_tiles(obs)
                where_r = self._ready_far_where(obs)
                if _far_status != "unavailable" and self._ready_far_all_given_up(obs):
                    return True, "gave_up_ready", (
                        f"农场口径还有 {ripe_f} 格熟作物{where_r}，"
                        f"{self._ready_far_give_up_cause_text()}（已放弃当天，不再空转）"
                        "——这不是「没活可做」，当天按 needs_review 如实收尾")
                if _far_status == "unavailable":
                    return False, "keep_working", (
                        f"农场口径还有 {ripe_f} 格熟作物（当前窗口没盖到，别处还有活），先去收")
                return False, "keep_working", (
                    f"农场口径还有 {ripe_f} 格熟作物{where_r}（当前窗口没盖到，别处还有活），先去收")
            if dry_f > 0:
                can, why = self._can_water(obs)
                # 【task-50】那一格干作物常常在玩家窗口之外：把 Mod 报的坐标写进理由，
                # 这样"当天以 stuck 收尾"时 `ended_reason` 能点名到底哪一格没浇成。
                where = self._far_dry_where(obs)
                # 【task-84 ③】窗口外的干格**全部已认输** ⇒ 不再空转，也不再假称"还有活"：
                # 用 `gave_up_dry` 如实收尾。它**不在** `JUSTIFIED_END_REASONS` 里 ⇒
                # `day_justified=False` ⇒ 当天 `verified=false`（run7 summer 3/5 的形态：
                # 追一株够不着的死苗整天换片地，summer 6 空转 4.5 分钟才靠 stuck_flush 翻篇）。
                if self._far_dry_all_given_up(obs):
                    return True, "gave_up_dry", (
                        f"农场口径还有 {dry_f} 格干作物{where}，"
                        f"{self._far_dry_give_up_cause_text()}（已放弃当天，"
                        "不再空转）——这不是「没活可做」，当天按 needs_review 如实收尾")
                if can and tod < 2500 and stam >= self.water_min_stamina:
                    return False, "keep_working", (
                        f"农场口径还有 {dry_f} 格干作物{where}（{why}），先把水浇完再谈收工")
                if not can:
                    return True, "no_water", (
                        f"农场口径还有 {dry_f} 格干作物{where}，但{why}（想浇但无水；"
                        "这不是「没活可做」，当天按 needs_review 如实收尾）")
        # 【task-102】钱够、没种子、却买不进来（背包没空格）：**不许睡**。
        # run8 day 12/13 就是这条缺失 ⇒ 26 次 `no_inventory_space` 之后直接睡，把"买种子→播种"
        # 整条腿跳过整整一天。腾格路径见 `_sell_surplus_for_slot`（同一天就能腾出来）。
        if self.buy_no_space_today:
            return False, "keep_working", (
                "钱够但背包没有空格、种子买不进来（no_inventory_space）⇒ 先卖一叠腾格/腾背包，"
                "今天不能靠睡觉跳过这条活")
        if self.day_start_off_farm and not self._is_farm(obs):
            # 【task-149 B】当天开工没能回到户外农场（晨间模态挡住、清框重试也不成）：玩家窗口
            # 是室内的，窗口读数（`crops=0`/`tillable=0`）根本不能当"地里没活"的证据 ⇒
            # 绝不许 `no_work`。run9c summer 20 就是这一天：06:10、体力 270、0 动作、`verified=true`。
            loc = str((obs.get("location") or {}).get("name") or "?")
            return False, "keep_working", (
                f"今天开工时没能回到户外农场（人在{loc}）⇒ 窗口是室内的、看不见地里有没有活，"
                "不许判『没活可做』；先想办法回农场，回不去就按 stuck 如实收尾")
        reasons = self.work_reasons(obs)
        if not reasons:
            # 【task-15 / 0.7.45】"没活"必须区分**真没活**与**只剩挡死格**：账本里如果还有
            # 被围/回去看过拿不出目标的格，那不是 `no_work`（`no_work` 在 JUSTIFIED 白名单里，
            # 会白拿一个 VERIFIED 并掩盖"该做没做完"）⇒ 交回主循环走换片/诚实收工
            # （`resume_exhausted`，`day_justified` 仍由可执行面证据决定）。
            _dead_pending = self._dead_end_pending()
            if _dead_pending:
                return False, "keep_working", (
                    f"账本还剩 {len(_dead_pending)} 格挡死格（被围 / 回去看过拿不出目标）⇒ "
                    "按换片/诚实收工收口（这不是「没活可做」，不许判 no_work）")
            # 【task-198 / task-28 卡 D】背包满 + 今天已证明腾不出格子 ⇒ 熟作物的理由已由
            # `work_reasons` 闭嘴，但**不许**洗成 `no_work`：那不是"没活可做"，是"活被背包
            # 堵住、腾不出格"。用 `inventory_blocked` 如实收尾；【task-28】该 flag 只在
            # `_note_inventory_blocked` 四门槛全过时才置位（free_slots==0 / relief_exhausted /
            # exec==0 / malformed==0）⇒ 此时 `day_justified` 可按证据放行（`stuck` 永不认）。
            if self.inventory_blocked_today:
                free_slots, _need, _status = self._bag_state(obs)
                return True, "inventory_blocked", (
                    f"背包满（空格 {free_slots}）且今天已经腾不出格子（可卖叠见 bag_evidence）⇒ "
                    "熟作物收不进来；这不是「没活可做」，当天按带证据的诚实收工处理"
                    "（不是 failed、不是 stuck、不是豁免）")
            # 【task-149 C】走到这里说明"没活"有**独立证据**：farm 证据齐备（否则上一段
            # fail-closed 已经给了理由）、窗口与农场口径都没给出任何活。日终 checks 用
            # `zero_action_evidenced` 拦住"0 动作却 VERIFIED"的假绿灯。
            # 【task-205】田里没活、但今天还有工具升级/取回要做 ⇒ 也不算收工（先跑一趟铁匠铺）。
            # 铁匠铺动作不进 `work_reasons`（它不是农活），所以必须在这里单独放行。
            if self._tool_upgrade_due(obs):
                return False, "keep_working", "今天还有一件工具升级/取回要做（铁匠铺），先做完再收工"
            # 【devcoder-clear-gate D】背包 0 空格 + 腾格手段用尽 + 剩余活**全是**被闸住的清障格
            # ⇒ 这**不是**"没活可做"：绝不能置 `no_work_evidence_ok`、更不能用 `no_work` 收尾
            # （`no_work` 在 JUSTIFIED 白名单里，会白拿一个 VERIFIED —— A9 冬 27/28 的洗白口）。
            # 交 `_end_clear_gate` 点名收口（`clear_gate`，`day_justified` 恒 False）。
            if self._clear_gate_only_work(obs):
                return True, "clear_gate", (
                    "背包 0 空格且腾格手段用尽，剩余活全是清障类（清障掉落必丢）⇒ 今天不再新开 "
                    "clear_area；这不是「没活可做」，当天按 clear_gate 如实收尾（不 VERIFIED）")
            self.no_work_evidence_ok = True
            # 【task-240】"没活"要说清是不是"有地、但手上的种子都隔季"：0.7.41 冒烟 day1
            # 是冬天 + Wheat Seeds×10，旧口径宣称"手上有种子 ⇒ 该去种"，下地却 `no_seed`
            # ⇒ 守卫/执行互相打脸、整天 stuck。这里把它变成**有证据的 `no_work`**
            # （`no_work` 在 `JUSTIFIED_END_REASONS` ⇒ 当天可 VERIFIED；证据来自
            # Mod `player.seeds[].plantableNow`，缺字段时 `metadata=False` 不进来）。
            season_state = self._seed_season_state(obs)
            if (season_state["metadata"] and int(season_state["plantable"]) <= 0
                    and season_state["out_of_season"]):
                plot_work = self._farm_plot_work(obs)
                empty = int(plot_work[1]) if plot_work is not None else 0
                names = "、".join(season_state["out_of_season"][:3])
                extra = f"，而 farm 口径还有 {empty} 格耕地空着" if empty > 0 else ""
                return True, "no_work", (
                    f"当季（{season_state['season'] or '?'}）没有可种的种子："
                    f"手上有 {names} 但都隔季{extra} ⇒ 今天没有可做的活"
                    "（证据：Mod player.seeds[].plantableNow）")
            return True, "no_work", "确实找不到可做的活（地里的活干完了、也没法/没必要买种子）"
        return False, "keep_working", "；".join(reasons)

    # ------------------------------------------------------------------ 前置条件
    def _sell_surplus_for_seeds(self, obs: dict[str, Any], rep: DayReport) -> bool:
        """【task-55】为买种子，把"超出保留线 K 的盈余材料"送进出货箱。

        为什么需要（run7 真形态，Lead 用 Python 逐条数过账本）：`sell`/`buy`/`ship` 事件 0 条、
        `seed_gate {seeds:0, money:14}` 出现 5 次 —— 那 4 格播种吃的是背包里原有的
        MixedFlowerSeeds；脑**从来没有自己挣过钱、也没自己买过种子**。缺的正是
        "卖盈余材料 → 钱到账 → 买当季种子 → 播种"这条闭环的第一步。

        纪律（全部来自用户 m08335 与 task-42 铁律）：

        * 三条门闸（`money < 5 × seed_price`、`seeds_total == 0`、`farm.emptyDirt > 0`）
          由 `farmwork.surplus_sell_plan()` 判 —— 证据不可信（`emptyDirt` 状态非 `"ok"`）
          时宁可不卖（fail-closed）；
        * **每 id 留够 K 件**、只卖整叠（`ShipSkill` 没有"卖一部分"的能力）；
        * 白名单是**精确 qualifiedId 列表**，只含超线材料；种子（名字含 seed/种子）、
          工具武器、可放置物、表外 id **永远进不来**；
        * 判据是观测差分（槽位真空了 + 该 id 总数下降）；**绝不写 `Money +=`**：
          钱要等游戏下一次 `NewDay` 结算，当天钱不变是**正常**的（账本里写明这一点）；
        * 当天只卖一次（`surplus_sold_today`），次日钱到账后再走 `_preconditions` 的买种子路。
        """
        assert self.worker is not None
        if self.surplus_sold_today:
            return False
        plan = surplus_sell_plan(obs, seed_price=self.seed_price)
        trig = plan["trigger"]
        if not plan["gate"]:
            return False
        # 门闸成立就记账"今天处理过这件事"，无论有没有东西可卖 —— 否则每轮都会重算、
        # 每轮都会往 notes 里塞同一句话（`_preconditions` 是每轮都调的）。
        self.surplus_sold_today = True
        if not plan["slots"]:
            # `surplus_sell_plan` 可能在"唯一一大叠也补不上种子钱"时主动拒绝（Lead m08064
            # 硬要求）⇒ 用它的 `skipReason` 原文，别让账本只剩一句笼统的"没有材料超线"。
            reason = str(plan.get("skipReason") or "").strip() or (
                f"钱 {trig['money']}g < {trig['threshold']}g 且种子 0 且空耕地 "
                f"{trig['emptyDirt']} 格 ⇒ 该卖材料换钱，但没有任何材料 id 超过保留线"
                f" K={plan['keep']}")
            self._journal("surplus_sell_skip", reason=reason, short=int(plan.get("short") or 0),
                          below_keep=bool(plan.get("belowKeep")), trigger=trig,
                          items=plan["items"])
            rep.notes.append(f"想卖盈余材料换种子钱：{reason}")
            self._say(f"  · {reason}")
            return False
        steps: list[StepResult] = []
        for slot in plan["slots"]:
            st = self.worker.sell(int(slot), whitelist=list(plan["whitelist"]),
                                  timeout_ms=self.sell_timeout_ms)
            self._actions += 1
            steps.append(st)
            before = st.before if isinstance(st.before, dict) else {}
            self._journal("sell", ok=st.ok, code=st.code, strategy="surplus_materials",
                          slot=before.get("slot", slot), qid=before.get("qid"),
                          stack=before.get("stack"), keep=plan["keep"],
                          below_keep=bool(plan["belowKeep"]), trigger=trig,
                          before=st.before, after=st.after, reason=st.reason, receipt=st.receipt)
            if not st.ok:
                break
        good = [s for s in steps if s.ok]
        bad = [s for s in steps if not s.ok]
        sold = sum(int((s.before or {}).get("stack") or 0) for s in good)
        self._journal("surplus_sell", ok=bool(good), strategy="surplus_materials",
                      keep=plan["keep"], slots=plan["slots"], whitelist=plan["whitelist"],
                      items=plan["items"], trigger=trig, sold=sold, ok_count=len(good),
                      fail_count=len(bad), below_keep=bool(plan["belowKeep"]),
                      reason=(bad[0].reason if bad else ""),
                      note="钱要等下一次 NewDay 才由游戏结算（当天 money 不变是正常的）")
        if good:
            note = (f"卖盈余材料 {len(good)} 叠共 {sold} 个进箱（每 id 留够 K={plan['keep']} 件）；"
                    f"钱要等下一次 NewDay 才由游戏结算")
            if plan["belowKeep"]:
                left = "、".join(f"{i['id']} 剩 {i['left']}" for i in plan["items"] if i["sell"])
                note = (f"卖盈余材料 {len(good)} 叠共 {sold} 个进箱（整叠出货没有「卖一部分」的能力"
                        f"⇒ 这一叠整叠进箱，出完 {left} 件 < K={plan['keep']}，已如实记账）；"
                        f"钱要等下一次 NewDay 才由游戏结算")
            rep.notes.append(note)
            self._say(f"  · {note}")
        if bad:
            rep.notes.append(f"卖盈余材料失败：{bad[0].reason}")
            self._say(f"  × 卖盈余材料失败：{bad[0].reason}")
            self._journal("sell_failed", strategy="surplus_materials",
                          reason=bad[0].reason, code=bad[0].code)
        return bool(good)

    def _dismiss_stray_menu(self, obs: dict[str, Any], rep: DayReport, *,
                            where: str = "before_buy") -> dict[str, Any]:
        """【task-102】关掉"不该开着"的残留菜单（`ShopMenu` / `ShippingMenu` 一类），返回新鲜观测。

        run8 的连锁：`buy` 每次都留下一个 `ShopMenu`（当天 23 次 `modal_dismissed ShopMenu`），
        下一次技能就被 `ui_modal` 拒；同一夜 sleep 留下的 `ShippingMenu` 还会挡住第二天的
        `goto_farm`（`t=107.91` 失败 → `t=107.95` 才关掉），把玩家整天留在 FarmHouse 里。

        只关"不该开着的"：`MODAL_WAIT_ONLY`（存档）与 `eventUp` 一律不碰（task-11/task-41）。
        """
        ui = obs.get("ui") or {}
        menu = str(ui.get("activeMenu") or "")
        if ui.get("eventUp") or menu in MODAL_WAIT_ONLY:
            return obs
        if not menu and not ui.get("isModal"):
            return obs
        assert self.client is not None
        try:
            res = self.client.dismiss_modal(
                timeout_ms=MODAL_DISMISS_BUDGET_MS.get(menu, MODAL_DISMISS_DEFAULT_MS))
        except BridgeError as exc:
            self._journal("modal_dismiss_failed", where=where, menu=menu,
                          reason=str(exc)[:200], status=str(getattr(exc, "status", "") or ""))
            return obs
        self._journal("modal_dismissed", where=where, menu=menu,
                      ok=bool((res or {}).get("ok")) if isinstance(res, dict) else True,
                      dismissPath=(res or {}).get("dismissPath") if isinstance(res, dict) else None,
                      waitedMs=(res or {}).get("waitedMs") if isinstance(res, dict) else None)
        return self._snap()

    def _sell_surplus_for_slot(self, obs: dict[str, Any], rep: DayReport) -> bool:
        """【task-102】为**腾出背包格子**卖一叠盈余材料（`why="need_slot"`）。

        与 `_sell_surplus_for_seeds` 的区别（两条独立门闸，见 `farmwork.surplus_sell_plan`）：

        * 凑钱那条：`money < 5 × seed_price` 且有空耕地 ⇒ 卖超 K 的叠换钱；
        * 腾格这条（本方法）：**钱已经够**，但 `free_slots < 1` ⇒ 卖**一叠**把格子腾出来。
          run8 day 12/13 的死锁就是缺这条：钱 188g、Wheat Seeds 10g，却因 0 空格 26 次买不成。

        一天只做一次（`slot_sold_today`）；仍然只走 `SURPLUS_MATERIAL_IDS` 白名单，
        尽量保留 K=10 件，整叠出货的事实如实记账。
        """
        assert self.worker is not None
        if self.slot_sold_today:
            return False
        free_slots, fs_status = player_free_slots(FarmWorker.player_of(obs))
        plan = surplus_sell_plan(obs, seed_price=self.seed_price, need_slot=True,
                                 free_slots=free_slots, free_slots_status=fs_status,
                                 slots_needed=1)
        if not plan["slotGate"]:
            return False
        self.slot_sold_today = True
        trig = plan["trigger"]
        if not plan["slots"]:
            reason = str(plan.get("skipReason") or "").strip() or (
                f"背包放不下种子（空格状态 {fs_status}）⇒ 想卖一叠腾格，但没有任何材料叠可卖")
            self._journal("surplus_sell_skip", why="need_slot", reason=reason, trigger=trig,
                          items=plan["items"])
            rep.notes.append(f"想卖一叠材料腾背包格子：{reason}")
            self._say(f"  · {reason}")
            return False
        steps: list[StepResult] = []
        for slot in plan["slots"]:
            st = self.worker.sell(int(slot), whitelist=list(plan["whitelist"]),
                                  timeout_ms=self.sell_timeout_ms)
            self._actions += 1
            steps.append(st)
            before = st.before if isinstance(st.before, dict) else {}
            self._journal("sell", ok=st.ok, code=st.code, strategy="surplus_materials",
                          why="need_slot", slot=before.get("slot", slot), qid=before.get("qid"),
                          stack=before.get("stack"), keep=plan["keep"],
                          below_keep=bool(plan["belowKeep"]), trigger=trig,
                          before=st.before, after=st.after, reason=st.reason, receipt=st.receipt)
            if not st.ok:
                break
        good = [s for s in steps if s.ok]
        bad = [s for s in steps if not s.ok]
        sold = sum(int((s.before or {}).get("stack") or 0) for s in good)
        self._journal("surplus_sell", ok=bool(good), why="need_slot",
                      strategy="surplus_materials", keep=plan["keep"], slots=plan["slots"],
                      whitelist=plan["whitelist"], items=plan["items"], trigger=trig, sold=sold,
                      ok_count=len(good), fail_count=len(bad),
                      below_keep=bool(plan["belowKeep"]), reason=(bad[0].reason if bad else ""),
                      note="腾背包格子：钱够但种子买不进来；卖出的叠当天就腾出空格，"
                           "钱仍要等下一次 NewDay 结算")
        if good:
            rep.notes.append(f"为腾格子卖了 {len(good)} 叠共 {sold} 个材料进箱"
                             "（钱要等下一次 NewDay 结算；空格当天就腾出来）")
            self._say(f"  · 腾格子：卖了 {len(good)} 叠共 {sold} 个材料")
        if bad:
            self._journal("sell_failed", why="need_slot", strategy="surplus_materials",
                          reason=bad[0].reason, code=bad[0].code)
        return bool(good)

    # ------------------------------------------------------------------ 背包/腾格（task-198）
    def _sell_surplus_for_space(self, obs: dict[str, Any], rep: DayReport, *,
                                max_stacks: int = 1,
                                prefer_harvested: bool = True) -> list[dict[str, Any]]:
        """【task-232】空格压力通道：卖**已知盈余**腾格（不看在不在凑种子钱）。

        与 `_sell_surplus_for_slot()`（task-102）的分工：

          * task-102 那条只在"**没种子** + 钱够买 + 0 空格"时动（卡点是买不进来）；
          * 本方法在**任何**空格压力下动：`free_slots <= SLOT_RESERVE` 就按
            `farmwork.slot_relief_plan()` 的三档白名单（作物余量 → 材料 → 矿/晶洞）
            卖**一叠**。真机死锁（`logs/longrun-smoke-0739.jsonl` day1：背包 12/12、钱 1977g、
            种子 10）两条旧通道都不触发 ⇒ 整天 `inventory_blocked`；缺的就是这条。

        【task-237】需求驱动：`max_stacks` 由调用方按"目标水位 − 当前空格"给（一次最多
        卖几叠）；`prefer_harvested` 把**今天亲手收获的作物**排在最前（它们本来就是为卖而
        收的产物，比动库存材料更合理）。

        纪律（卡面 + Lead m21658）：只认已知表、`isTool`/种子/升级锭/未知物品一律不卖；
        每 qid 留 K（或整叠卖空，见 `slot_relief_plan`）；每天 ≤ `SLOT_RELIEF_MAX_STACKS_TOTAL`
        叠；**只走 `worker.sell()`**（游戏自己的出货/卖出），绝不自己加钱。
        判据在调用方 `_slot_relief` 里用"卖前/卖后 钱 + 背包行数"双差分复核。

        返回实际卖成功的叠账本（空列表 = 没卖成，原因已进 journal）。
        """
        assert self.worker is not None
        if self.slot_relief_stacks_today >= SLOT_RELIEF_MAX_STACKS_TOTAL:
            return []
        free_slots, fs_status = player_free_slots(FarmWorker.player_of(obs))
        prefer: tuple[str, ...] = ()
        if prefer_harvested:
            prefer = tuple(sorted(getattr(self.worker, "harvested", None) or {}))
        plan = slot_relief_plan(obs, free_slots=free_slots, free_slots_status=fs_status,
                                trigger_free_slots=SLOT_RESERVE,
                                max_stacks=max(1, int(max_stacks)),
                                prefer_qids=prefer)
        if not plan["pressure"]:
            return []
        if not plan["slots"]:
            # 【task-232】**不新增 journal 事件名**（analyzer 机械枚举会漂移）：把"为什么
            # 没卖"存在实例字段里，由 `_slot_relief` 收进既有的 `slot_relief` 事件
            # （`blocked_reason`/`space_skip` 都是字段，不是新事件）。
            self._space_skip_reason = str(plan.get("skipReason") or "")
            return []
        sold: list[dict[str, Any]] = []
        for item in plan["items"]:
            st = self.worker.sell(int(item["slot"]), whitelist=[str(item["qid"])],
                                  timeout_ms=self.sell_timeout_ms)
            self._actions += 1
            self._journal("sell", ok=st.ok, code=st.code, strategy="slot_relief_space",
                          why="space_pressure", slot=int(item["slot"]), qid=str(item["qid"]),
                          stack=int(item["stack"]), tier=int(item["tier"]),
                          below_keep=bool(item["belowKeep"]), keep=SLOT_RELIEF_KEEP,
                          before=st.before, after=st.after, reason=st.reason, receipt=st.receipt)
            if not st.ok:
                break
            sold.append(dict(item))
            self.slot_relief_stacks_today += 1
            if self.slot_relief_stacks_today >= SLOT_RELIEF_MAX_STACKS_TOTAL:
                break
        if sold:
            self.slot_relief_sold.extend(sold)
            total = sum(int(it["stack"]) for it in sold)
            rep.notes.append(f"空格压力：卖了 {len(sold)} 叠共 {total} 个盈余（"
                             + "、".join(f"{it['qid']}×{it['stack']}" for it in sold)
                             + "；钱要等下一次 NewDay 结算，空格当天腾出来）")
            self._say(f"  · 空格压力：卖 {len(sold)} 叠腾格")
        return sold

    def _ready_crop_count(self, obs: dict[str, Any]) -> int:
        """下一批"能收"的熟作物格数（腾格回路的**需求估计**，不参与任何判据）。

        取窗口里游戏口径 `ready` 的活苗格数与 farm 级 `readyCrops` 的**较大者**：
        窗口外的熟作物看不到坐标（task-199 才给 `readyTiles`），但"还要不要腾格"只需要
        一个数量级估计 —— 少算会漏腾（run A′ 的形态），多算最多多腾一格（有界，且
        `_slot_relief` 每轮必须真腾 ≥1 格，不会空转）。
        """
        tmap = FarmWorker.tiles_of(obs)
        window = sum(1 for t, tv in tmap.items()
                     if tv.get("crop") and not tv.get("dead") and tile_ready(tv)
                     and t not in self.harvest_gave_up and t not in self.blocked)
        farm = obs.get("farm") or {}
        if farm.get("complete") is True and farm.get("loaded") is not False:
            total = farm.get("readyCrops")
            if isinstance(total, int) and total > window:
                return int(total)
        return int(window)

    def _harvest_demand(self, obs: dict[str, Any]) -> tuple[int, str]:
        """【task-237】当天"可收格数"的需求估计 + 口径来源（只用来定腾格目标水位）。

        为什么需要"需求"而不是固定 `SLOT_RESERVE + 1`：0.7.40 A2 冒烟里 `harvest` 阶段
        每轮要分配 **12 格**（`intent_coverage`: `req=12/ok=0/reasons={"no_slot":12}`），
        而旧口径每轮只腾 1–3 格 ⇒ 腾出来立刻被塞满、3/3 天 `inventory_blocked`。
        目标水位必须**按当天要收多少格**算。

        口径（三态，绝不把"读不到"当 0）：
          * 窗口内 `ready` 的活苗格数；
          * 窗口外熟作物坐标（`readyTiles`，task-199）的条数；
          * farm 级 `readyCrops` 计数；
          三者取最大，封顶 `HARVEST_DEMAND_CAP`；**三路全不可用** ⇒ 保守
          `SLOT_RELIEF_DEMAND_FALLBACK`（`demand_basis="conservative"`）。
        """
        tmap = FarmWorker.tiles_of(obs)
        window = sum(1 for t, tv in tmap.items()
                     if tv.get("crop") and not tv.get("dead") and tile_ready(tv)
                     and t not in self.harvest_gave_up and t not in self.blocked)
        outside, status = self._ready_far_outside(obs)
        farm = obs.get("farm") or {}
        farm_ok = farm.get("complete") is True and farm.get("loaded") is not False
        farm_count = self._farm_count(obs, "readyCrops")
        if not tmap and not farm_ok and status == "unavailable":
            return int(SLOT_RELIEF_DEMAND_FALLBACK), "conservative"
        demand = max(int(window), len(outside), int(farm_count or 0))
        demand = max(0, min(int(HARVEST_DEMAND_CAP), int(demand)))
        if status in ("ok", "truncated") and outside:
            basis = "readyTiles"
        elif farm_ok and isinstance(farm_count, int):
            basis = "farm"
        else:
            basis = "window"
        return int(demand), basis

    def _bag_state(self, obs: dict[str, Any]) -> tuple[int, int, str]:
        """背包空格行数、**是否到了该腾格的信号**（0/1）、以及空槽读数的状态。

        【task-198 低水位语义】`need == 1` 当且仅当：

          * 空格读数可用（`status == "ok"`；拿不到 ⇒ fail-closed 不冒进，同
            `farmwork.player_free_slots` 的口径）；
          * `free_slots <= SLOT_RESERVE` **且** 下一批可收的熟作物格数 **多于** 空格数。

        为什么不是"`free == 0` 才腾"（旧口径，run A′ 病灶）：1 空格 + 多格熟作物时，
        第一批收获就会撞 `no_slot`（收不进来），当天既没收成、又没留下可执行的腾格动作，
        最后以"守卫说还有活却零进展"的 `stuck` 收尾。
        为什么不是"`free <= SLOT_RESERVE` 就无条件腾"：只有 1 格熟作物时收一格正好用掉
        那最后一格 —— 白腾一次纯属浪费（deputy 预检点名的边界）。
        """
        free_slots, status = player_free_slots(FarmWorker.player_of(obs))
        if status != "ok":
            return int(free_slots), 0, str(status)
        free_slots = int(free_slots)
        ready = self._ready_crop_count(obs)
        need = 1 if (free_slots <= SLOT_RESERVE and ready > free_slots) else 0
        return free_slots, need, str(status)

    def _observe_free_slots(self, rep: DayReport,
                            obs: dict[str, Any]) -> tuple[int | None, str]:
        """【task-16 / 0.7.45】每次观测都重算**背包空格**（容量 − 非空行数），写进当天 trace。

        口径（卡面硬要求，与 `farmwork.player_free_slots` 逐字一致）：可用空格 =
        `inventoryCount`（容量 12/24/36）**减去** `len(inventory[])`；**不是**把
        `inventoryCount` 本身当"已用/满格"（旧 run8 的 25 次 `no_inventory_space` 正是把
        容量当占用：存档 `inventoryCount=12` 且背包恰好 12 行，free 才是 0）。
        读不到（旧桥缺 `inventoryCount` / 不在农场）⇒ 返回 `(None, "unavailable")`，
        `status != "ok"` 时**绝不猜 0**、也不置任何"满包"判定（fail-closed）。

        trace 语义（只 info，不进 checks）：`rep.free_slots_start` = 当天第一张可用读数；
        `free_slots_last` = 最近一张；`free_slots_min` = 当天最低水位；`free_slots_status` = 末次状态。
        """
        free, status = player_free_slots(FarmWorker.player_of(obs))
        status = str(status)
        self.free_slots_status = status
        rep.free_slots_status = status
        if status != "ok":
            return None, status
        value = int(free)
        if rep.free_slots_start is None:
            rep.free_slots_start = value
        rep.free_slots_last = value
        rep.free_slots_min = value if rep.free_slots_min is None else min(
            int(rep.free_slots_min), value)
        self.free_slots_last = value
        self.free_slots_min = value if self.free_slots_min is None else min(
            int(self.free_slots_min), value)
        return value, "ok"

    def _note_slot_pressure_stuck(self, obs: dict[str, Any], rep: DayReport, *,
                                  free_slots: int, reason: str) -> None:
        """【task-16 / 0.7.45】背包**真满**（0 空格）但客观腾不出：留痕，**不判失败**。

        与 `_note_inventory_blocked`（task-198）的边界：那条是"有熟作物却收不进来 ⇒ 当天
        诚实收尾、`verified=false`"；本条的形态是**清障/浇水还在干**，只是掉落会被游戏拒收
        —— 卡面硬要求：不许因此判失败/不许把冬季 clear 的日子连坐成"背包堵住"。
        每天只记一次（`slot_pressure_noted`），复用既有事件名 `slot_relief`（**不加新事件名**，
        避免 analyzer 的事件枚举漂移），字段 `pressure=True` / `need=0` / `freed=0` / `trigger=none`
        让读出方一眼区分"压力通道腾不出（非失败）"与"真堵死收尾"。
        """
        if self.slot_pressure_noted:
            return
        self.slot_pressure_noted = True
        try:
            money_now = int(FarmWorker.money(obs))
        except (TypeError, ValueError):
            money_now = 0
        rows_now = len(FarmWorker.player_of(obs).get("inventory") or [])
        self._journal("slot_relief", need=0, freed=0, shipped=False,
                      freeSlots_before=int(free_slots), freeSlots_after=int(free_slots),
                      before_free=int(free_slots), after_free=int(free_slots),
                      trigger="none", sold=[],
                      stacks_today=int(self.slot_relief_stacks_today),
                      max_stacks=SLOT_RELIEF_MAX_STACKS_TOTAL,
                      money_before=money_now, money_after=money_now,
                      rows_before=rows_now, rows_after=rows_now,
                      failed=False, blocked_reason="", round=self.slot_relief_today,
                      max_rounds=SLOT_RELIEF_MAX, reserve=SLOT_RESERVE, demand=0,
                      demand_basis="space_pressure", target_free=SLOT_RELIEF_TARGET_FREE,
                      reached=False, pressure=True, reason=str(reason or ""),
                      note="背包真满（0 空格）但腾不出格子：没有可出货/可卖的盈余叠 ⇒ "
                           "**不判失败**、日循环继续（清障/浇水照做）；清障/收获掉落会被游戏拒收，"
                           "逐格 `loot_lost` 留痕。根治=先腾格，长期=背包升级（task-14 建议）")
        rep.notes.append(
            f"背包已满（0 空格）但腾不出格子：{reason or '没有可卖叠'} ⇒ 不判失败、继续干活；"
            "清障掉落可能被游戏拒收（见 day_end 的 loot_lost 留痕）")
        self._say(f"  ! 背包已满（0 空格）腾不出：{reason or '没有可卖叠'}"
                  "（不算失败；掉的战利品可能丢）")

    def _note_loot_lost(self, steps: list[StepResult], rep: DayReport, *,
                        stage: str) -> None:
        """【task-16 / 0.7.45】汇总"**清成了**但背包 0 空格 ⇒ 掉落被游戏拒收"的步（info）。

        证据来源 = `farmwork.clear()` 在成功分支写的 `StepResult.loot_lost`（含
        `loot_free_slots` / 近似 `loot_items` / `loot_reason`）。这里只做日级/阶段级聚合：
          * `rep.loot_lost_steps/tiles/items` —— 日终进 `day_end`（既有事件名 `day_end`，
            新增字段，**不加新事件名**：analyzer 会枚举 journal 事件字面量）；
          * 每天只往 notes/say 写一次（`loot_lost_noted`），不刷屏、不重复计数。
        **语义边界**：只留痕 —— 不清 ok、不算 failed、不进 checks、不导致当天不 VERIFIED。
        """
        lost = [s for s in steps if bool(getattr(s, "loot_lost", False))]
        if not lost:
            return
        rep.loot_lost_steps += len(lost)
        for s in lost:
            self.loot_lost_steps_today += 1
            tile = getattr(s, "tile", None)
            if tile:
                try:
                    xy = (int(tile[0]), int(tile[1]))
                except (TypeError, ValueError, IndexError):
                    xy = None
                if xy is not None:
                    if xy not in self.loot_lost_tiles_today:
                        self.loot_lost_tiles_today.append(xy)
                    if [xy[0], xy[1]] not in rep.loot_lost_tiles:
                        rep.loot_lost_tiles.append([xy[0], xy[1]])
            for item in (getattr(s, "loot_items", None) or []):
                name = str(item)
                if name and name not in rep.loot_lost_items:
                    rep.loot_lost_items.append(name)
        if self.loot_lost_noted:
            return
        self.loot_lost_noted = True
        rec = lost[0]
        free = getattr(rec, "loot_free_slots", None)
        reason = str(getattr(rec, "loot_reason", "") or "")
        rep.notes.append(
            f"{stage} 阶段有 {len(lost)} 步清成了但背包 0 空格 ⇒ 掉落被游戏拒收"
            f"（Inventory Full；近似 {rep.loot_lost_items[:4]}；空格="
            f"{free if free is not None else '?'}）——只留痕，不判失败/不改 checks；"
            "先腾格可缓解，根治见 task-14 背包升级建议")
        if reason:
            rep.notes.append(f"掉落拒收判据：{reason}")
        self._say(f"  ! 背包 0 空格 ⇒ 掉落可能被游戏拒收（{len(lost)} 步已留痕，不判失败）")

    def _bag_relief_evidence(self, obs: dict[str, Any]) -> dict[str, Any]:
        """【task-28 卡 D】"腾不出格子"的**可复核证据**（纯决策，不发请求）。

        返回并缓存到 `self.bag_evidence_today`（`day_end.bag_evidence` 原样引用）。字段：
          * `free_slots`/`free_slots_status` —— 空格口径 = 容量 − 非空行数（`player_free_slots`）；
          * `sellable_above_keep` —— 用 `slot_relief_plan`（KEEP / MAX_STACKS / RESERVES 同一套
            规则）此刻算出的"真能卖"的叠数（不是散文：卖单要真发得出去才算）；
          * `relief_rounds`/`relief_round_limit`、`sold_stacks`/`sold_stack_limit` —— 当天已用量/上界；
          * `plan_pressure`/`skip_reason` —— 决策层原始读数，便于事后解释"为什么没可卖的"；
          * `exhausted` —— 语义 = 「证据可信 + free_slots==0 + (没有可卖叠 或 轮数到顶 或 叠数到顶)」。
            **证据不可信（`free_slots_status != "ok"`）⇒ 一律 False**：读不到 ≠ 腾不出（fail-closed）。
          * `loot_lost_steps`/`loot_lost_limit` —— 【E5 可判】当天已发生/允许发生的清障落地丢失步数
            （只读；`_stage_tiles` 的 clear 闸按 `loot_lost_limit - loot_lost_steps` 收窄阶段 limit，
            所以调用方拿到这组数就能复核「E5 不可能被超过」，不用读散文）。
        """
        if not isinstance(obs, dict):
            obs = {}
        player = FarmWorker.player_of(obs)
        free, status = player_free_slots(player)
        rounds_left = self.slot_relief_today < SLOT_RELIEF_MAX
        stacks_left = self.slot_relief_stacks_today < SLOT_RELIEF_MAX_STACKS_TOTAL
        plan: dict[str, Any] = {}
        if status == "ok":
            # 【task-28 卡 D】必须把**本次观测的空格/状态**显式喂给 `slot_relief_plan`；
            # 它的默认参数是 `free_slots=None`（pressure=False）⇒ 不喂就永远算"没有可卖叠"，
            # 把"其实卖得动"误判成 `exhausted`（B 门槛/清障闸都会假绿）。
            plan = slot_relief_plan(obs, free_slots=free, free_slots_status=status,
                                    trigger_free_slots=SLOT_RESERVE,
                                    max_stacks=SLOT_RELIEF_MAX_STACKS_TOTAL)
        sellable = len(plan.get("slots") or []) if plan else 0
        exhausted = bool(
            status == "ok" and free is not None and int(free) <= 0
            and (sellable == 0 or not rounds_left or not stacks_left)
        )
        ev: dict[str, Any] = {
            "free_slots": (None if free is None else int(free)),
            "free_slots_status": str(status),
            "sellable_above_keep": int(sellable),
            "relief_rounds": int(self.slot_relief_today),
            "relief_round_limit": int(SLOT_RELIEF_MAX),
            "sold_stacks": int(self.slot_relief_stacks_today),
            "sold_stack_limit": int(SLOT_RELIEF_MAX_STACKS_TOTAL),
            "plan_pressure": bool(plan.get("pressure")) if plan else False,
            "skip_reason": str(plan.get("skipReason") or "") if plan else "free_slots 证据不可用",
            "reserve": int(SLOT_RESERVE),
            "exhausted": exhausted,
            # 【Lead §8.1 E5】只读读数：当天已丢失 / 全天硬上界；`_stage_tiles` 的 clear 闸按
            # `limit - loot_lost_steps` 收窄，所以这组数就是"E5 不会被超过"的可复核证据。
            "loot_lost_steps": int(self.loot_lost_steps_today),
            "loot_lost_limit": int(CLEAR_LOOT_LOSS_MAX_STEPS),
        }
        self.bag_evidence_today = dict(ev)
        self.bag_relief_exhausted_today = exhausted
        return ev

    def _clear_bag_gate_reason(self, obs: dict[str, Any]) -> str:
        """【task-28 卡 D C】`clear_area` 是否该被"满包"闸住（返回非空即闸住）。

        闸门只看**可复核证据**：`free_slots == 0` 且 `_bag_relief_evidence().exhausted`
        （没有可卖叠 / 轮数或叠数到顶）。证据不可读（`free_slots_status != "ok"`）⇒ 不闸
        （fail-open，宁可少闸也不拿"读不到"当"腾不出"）；`loot_lost_steps` 上界是另一道
        独立兜底，不依赖本闸。
        """
        ev = self._bag_relief_evidence(obs)
        free = ev.get("free_slots")
        if free is None or int(free) > 0:
            return ""
        if not ev.get("exhausted"):
            return ""
        return "背包 0 空格且腾格手段用尽"

    def _clear_gate_only_work(self, obs: dict[str, Any]) -> bool:
        """【devcoder-clear-gate D】今天的剩余活是不是**只有**被满包清障闸挡住的那批清障格。

        收尾口 `_end_clear_gate` 只能在这种情况下用：否则就是拿"背包闸"当借口提前结束一天
        （还有浇水/收获/播种的活就收工 = 白丢一天）。判据（全部要成立）：

        ① 闸生效（`_clear_bag_gate_reason` 非空：背包 0 空格 + 腾格手段用尽）；
        ② **当前观测窗口里**确实还有"能做、只因闸而不做"的清障格（`CLEARABLE_KINDS` 且
           工具够格；树另受当天砍树预算约束）。这里**刻意直接扫 `tiles[]`** 而不是只信
           `leftover_targets`：账本只记"今天真的开过阶段"的格，满包日 `_stage_tiles("clear_area")`
           整池清零 ⇒ 账本可能是空的（日初就满包的情形），而活明明摆在地里；
        ③ 观测窗口里没有任何**其它**"该做的活"：活苗没浇 / 熟作物（未认输）/ 枯死作物 /
           可锄可种（`can_plant` 且没被预算延后）—— 只要有一格，就不是"只剩清障"；
        ④ 账本口径 `_pending_work()` 里**看得见**的格也全是清障类（看不见的格不参与，由下面
           ⑤ 的 `executable==0` fail-closed 兜底）；
        ⑤ 日终快照 `executable == 0` 且 `malformed == 0`（当前观测里没有可执行格、观测也没坏）。

        返回 True 时调用方必须走 `_end_clear_gate`（`ended_by=clear_gate`，
        `day_justified=False`、永不 VERIFIED）；**绝不许**把它当成 `no_work`。
        """
        if not self._clear_bag_gate_reason(obs):
            return False
        tmap = FarmWorker.tiles_of(obs)
        tillable = FarmWorker.tillable_of(obs)
        _seeds, _money, can_plant = self._seed_outlook(obs)
        deferred = self._budget_deferred_tasks()
        shed = self._shed_tile_set()
        tree_room = self._tree_budget_room(obs)
        clear_visible = 0
        for t, tv in tmap.items():
            if t in self.blocked or t in shed or t in self.encircled_day \
                    or t in self.resume_stall_tiles:
                continue                      # 今天已判死/认输/停滞 ⇒ 本来就不算活
            if tv.get("crop"):
                # 作物活（浇水 / 收获 / 清死苗）依旧是"真活"：不许拿背包闸收工。
                if tv.get("dead"):
                    return False
                if not tv.get("watered"):
                    return False
                if tile_ready(tv) and t not in self.harvest_gave_up:
                    return False
                continue
            kind = str(tv.get("kind") or "")
            if kind in CLEARABLE_KINDS and not _tool_blocked_tv(tv):
                if kind == TREE_KIND and tree_room <= 0:
                    continue                  # 砍树预算挡下 = 今天不做（不是被闸住）
                clear_visible += 1
                continue
            if (t in tillable and can_plant and "till_area" not in deferred) \
                    or (kind == "dirt" and can_plant and "plant_area" not in deferred):
                return False                  # 还有地可开/可种 ⇒ 守卫该继续喊活，不许收工
        snap = self._pending_snapshot(obs)
        if clear_visible <= 0:
            # 窗口里此刻看不见清障格（人在室内/换过片地）时，退回账本口径：只要快照说
            # 还有"只因闸而不执行"的清障格，仍是同一个结论（活被背包闸住）。
            if int(snap.get("gated") or 0) <= 0:
                return False
        for t in self._pending_work():
            tv = tmap.get(t)
            if tv is None:
                continue                      # 不在窗口里 ⇒ 无法分类（由 ⑤ fail-closed 兜底）
            if tv.get("crop"):
                return False                  # 还有作物活（浇/收/清死苗）
            if str(tv.get("kind") or "") not in CLEARABLE_KINDS:
                return False                  # 耕地/空地/其它 ⇒ 不是"只剩清障"
        if int(snap.get("executable") or 0) > 0:
            return False
        if int(snap.get("malformed") or 0) > 0:
            return False
        return True

    def _note_clear_area_bag_gate(self, task: str, why: str) -> None:
        """【task-28 卡 D C】满包清障闸留痕（复用既有 `slot_relief` 事件名 + 新字段，不新增事件）。

        语义：**不是失败、不是豁免**，只说明"今天不再新开 clear_area"；`_leftover` 照旧如实，
        `day_end.bag_evidence` 给出可复核读数。开路必要前置（`_ensure_reachable`/`open_way`
        内部的单格清障）不经过本池，仍允许。
        """
        if self.clear_area_bag_gate_noted:
            return
        self.clear_area_bag_gate_noted = True
        # 【task-237 / 0.7.48 字段奇偶补齐】`slot_relief` 的 task-237 字段集是
        # demand/demand_basis/target_free/**reached** —— 本闸此前漏写 `reached`（纯只读字段
        # 缺口，非行为变更；验收探针 scratch/smoke-0742.py:680 按该字段集校验）。
        # 语义：clear_gate **不是**"腾到了目标水位"，而是"今天不再新开 clear_area"的闸
        # ⇒ `reached` 如实填 False，绝不谎报水位达标（与压力通道一致）。
        self._journal("slot_relief", pressure=True, need=0, demand=0,
                      demand_basis="space_pressure", trigger="clear_gate",
                      target_free=SLOT_RELIEF_TARGET_FREE, reached=False, freed=0,
                      stage=task,
                      reason=why, loot_lost_steps=int(self.loot_lost_steps_today),
                      loot_lost_limit=int(CLEAR_LOOT_LOSS_MAX_STEPS),
                      note=("满包清障闸：不新开 clear_area（落地即丢；开路必要前置仍允许）"
                            " —— 不是失败/豁免；次日背包腾出后恢复"))

    def _note_inventory_blocked(self, obs: dict[str, Any], rep: DayReport, *,
                                free_slots: int, reason: str) -> None:
        """【task-198 / task-28 卡 D】"腾不出格子"必须过**四门槛**才认（否则只留痕、不认）。

        四条独立证据全部成立才置 `inventory_blocked_today`：
          ① `free_slots == 0`（口径 = 容量 − 非空行数，**不是** `inventoryCount` 本身）；
          ② `relief_exhausted`：`_bag_relief_evidence` 用卖单规则算出（没有可卖叠 / 轮数 /
             叠数到顶），不是"我们觉得卖不动"；
          ③ `pending_executable == 0`：日终快照里"当前可执行且可达"的待做格确实为 0；
          ④ `pending_malformed == 0`：观测没有残缺 tile 记录（缺失 ≠ 通过）。
        任一不成立 ⇒ journal `accepted=false` + `gate_gaps` 留痕，**不置 flag**（不空转、不洗白）；
        诚实收尾仍由 `sleep_guard`/`_end_inventory_blocked` 在 flag 置位后走。
        **`stuck:` 永远不会从这条路径产生**；真剩 `exec>0` 时必须保持 False（卡面 B）。
        """
        ev = self._bag_relief_evidence(obs)
        snap = self._pending_snapshot(obs)
        free_now = ev.get("free_slots")
        if free_now is None:
            free_now = int(free_slots)
        gaps: list[str] = []
        if int(free_now) > 0:
            gaps.append(f"free_slots={int(free_now)}>0")
        if not ev.get("exhausted"):
            gaps.append("relief_not_exhausted")
        if int(snap.get("executable") or 0) > 0:
            gaps.append(f"pending_executable={int(snap.get('executable') or 0)}")
        if int(snap.get("malformed") or 0) > 0:
            gaps.append(f"pending_malformed={int(snap.get('malformed') or 0)}")
        accepted = not gaps
        rep.bag_evidence = dict(ev)
        rep.relief_exhausted = bool(ev.get("exhausted"))
        if not accepted and self.bag_gate_reject_noted:
            # 拒绝留痕每天只写一次：`_slot_relief` 每轮都会走到这里，刷屏没有信息增量。
            return
        if not accepted:
            self.bag_gate_reject_noted = True
        self._journal("inventory_blocked", free_slots=int(free_now), reserve=SLOT_RESERVE,
                      rounds=self.slot_relief_today, limit=SLOT_RELIEF_MAX,
                      accepted=bool(accepted), relief_exhausted=bool(ev.get("exhausted")),
                      evidence=dict(ev), gate_gaps=list(gaps), reason=reason,
                      note=("背包 0 空格 + 腾格手段用尽 + 没有可执行待做格 ⇒ 当天如实收尾"
                            "（不是 hard failure；stuck 不认；接受时 day_justified 按证据判）"
                            if accepted else
                            "证据不足，不认'腾不出格子'（继续干活/如实收尾，不空转不洗白）"))
        if not accepted:
            rep.notes.append(f"inventory_blocked 证据不足（{'、'.join(gaps)}）⇒ 不认：{reason}")
            self._say(f"  ! 背包满但证据不足（{'、'.join(gaps)}）⇒ 不按'腾不出'收工")
            return
        self.inventory_blocked_today = True
        if self.inventory_blocked_noted:
            return
        self.inventory_blocked_noted = True
        rep.notes.append(f"背包满且腾不出格子（四门槛全过）：{reason}")
        self._say(f"  × 背包满且腾不出格子（四门槛全过）：{reason}")

    def _ship_one_stack_for_space(self, obs, rep):
        assert self.worker is not None
        player = FarmWorker.player_of(obs)
        # 建材/矿石/锭/煤/土/木/石/纤维/硬木/放射性矿永不送（升级与建造要用）；只送"盈余/战利品"腾格。
        # 消费 farmwork 的**权威永不卖集合**（`SLOT_RELIEF_NEVER_SELL_IDS`）—— 不再手维护本地
        # 副本（590f154 违纪：本地 `_PROTECTED` 漏了 Fiber 771 / Radioactive 909 等建材，会让
        # last-resort 把建材送出，违反 AGENTS.md §5）。`slot_relief_plan` 也消费同一集合，两份清单不再漂移。
        cands = []
        for it in (player.get("inventory") or []):
            if not isinstance(it, dict) or it.get("isTool"):
                continue
            qid = str(it.get("qualifiedId") or it.get("id") or "").strip()
            if not qid:
                continue
            bare = _bare_item_id(qid)
            if bare in SLOT_RELIEF_NEVER_SELL_IDS:
                continue
            name = str(it.get("name") or "")
            if any(hint in name.lower() for hint in SEED_NAME_HINTS):
                continue
            try:
                stack, slot = int(it.get("stack") or 0), int(it.get("slot"))
            except (TypeError, ValueError):
                continue
            if stack <= 0:
                continue
            cands.append((stack, slot, qid))
        if not cands:
            return False
        cands.sort(key=lambda c: (c[0], c[1]))
        stack, slot, qid = cands[0]
        st = self.worker.sell(slot, whitelist=[qid], timeout_ms=self.sell_timeout_ms)
        self._actions += 1
        self._journal("sell", ok=st.ok, code=st.code, strategy="space_relief_ship",
                      why="space_pressure_last_resort", slot=slot, qid=qid,
                      stack=stack, before=st.before, after=st.after, reason=st.reason, receipt=st.receipt)
        if st.ok:
            rep.notes.append("space relief shipped %s x %d" % (qid, stack))
            self._say("  space relief shipped %s x %d" % (qid, stack))
            self.slot_relief_stacks_today += 1
            return True
        return False

    def _slot_relief(self, obs: dict[str, Any], rep: DayReport) -> bool:
        """【task-198】"腾格收敛回路"：背包低于**需求水位**时先把格子腾出来，再回去干活。

        返回 True = 这一轮真的腾出了格子（调用方 `continue`，重新观测/决策）；
        False = 不需要腾格，或腾不出来（已置 `inventory_blocked_today`，当天如实收尾）。

        【task-237 需求驱动】目标水位 = `min(SLOT_RESERVE + harvest_demand, SLOT_FREE_CAP)`，
        其中 `harvest_demand` 由 `_harvest_demand(obs)` 按"当天可收格数"估（窗口 ready /
        `readyTiles` / farm `readyCrops` 取最大，三路全不可用 ⇒ 保守 3）。
        为什么：0.7.40 A2 里 `harvest` 每天需 12 格，旧口径只腾到 2 格 ⇒ 腾出来立刻塞满、
        3/3 天 `inventory_blocked`。

        次序（每一层都留 journal）：
          1. **卖之前先清模态**（`_dismiss_stray_menu`）：模态挡着时 `sell` 会被 `ui_modal`
             拒绝（task-235 并入本卡）；清不掉 ⇒ 不卖、如实 blocked（不空转）。
          2. `_ship_loot()`：把**今天亲手收货、且绑格子证据**的成品放进出货箱；
          3. `_sell_surplus_for_slot()`（task-102）：缺种子钱时卖盈余材料；
          4. **空格压力通道**：按 `slot_relief_plan()` 三档白名单卖叠，**优先今天的收获产物**，
             每叠一卖、每次重观测，卖到目标水位为止（受轮数/叠数两个硬界约束）。
          都不是可腾 ⇒ 记一次 `inventory_blocked`（reason 区分"没有可卖叠"与"卖满上限仍不够"）。

        【task-16 / 0.7.45】**真满（0 空格）压力通道**：即使 `need == 0`（当天没有待收熟作物，
        例如冬季 clear-only）也要先腾格——否则清障/砍树掉的战利品会被游戏直接拒收
        （vanilla `Inventory Full`），账本只看到"清成了"。压力通道腾不出来**不是失败**：
        复用一个 `slot_relief` 事件（`pressure=True`、`freed=0`、`trigger=none`）留痕，
        不置 `inventory_blocked_today`、不改变当天判据（清障照常算做成）。
        边界：**只在 0 格**触发；1 空格 + N 格熟作物由 `need`（task-198 语义）负责，绝不白卖。

        界（卡面硬要求）：每天最多 `SLOT_RELIEF_MAX`(=6) 轮、最多
        `SLOT_RELIEF_MAX_STACKS_TOTAL`(=10) 叠；本轮腾 0 格 ⇒ 立刻判定"腾不出来"，绝不空转。
        """
        assert self.worker is not None
        free_slots, need, status = self._bag_state(obs)
        if status != "ok":
            return False
        demand, demand_basis = self._harvest_demand(obs)
        target_free = min(SLOT_RESERVE + max(0, int(demand)), SLOT_FREE_CAP)
        # 【task-237】触发条件 = 低水位/0 空格（`need` 信号）—— 需求水位只决定"这一轮腾到多少"。
        # 为什么不按"free < 需求"提前腾：腾格本身要花请求/时间，而收获可以先塞进现有空格、
        # 出货再跟上；0.7.40 A2 的真形态是 `freeSlots_before: 0`（真堵死），不是"空格略少"。
        # 【task-16 / 0.7.45】空格压力通道：**真满（0 格）**时即使没有收获需求（`need == 0`，
        # 例如冬季 clear-only 的一天）也要先腾格——否则清障/砍树掉的战利品会被游戏直接拒收
        # （vanilla `Inventory Full`）。只在 **0 格**触发：1 空格 + N 格熟作物是 task-198
        # 钉死的边界（`need` 负责），这里**不**把"空格 ≤ SLOT_RESERVE"一律当压力（不许白卖）。
        space_pressure = bool(int(free_slots) <= 0)
        if need <= 0 and not space_pressure:
            return False
        if need <= 0:
            # 压力通道没有"今天要收几格"的需求：只腾到最小保留水位，别把动作预算烧在卖货上。
            demand = 0
            demand_basis = "space_pressure"
            target_free = int(SLOT_RELIEF_TARGET_FREE)
        if self.inventory_blocked_today:
            return False
        # 【task-237】先判"这一轮到底有没有可腾的东西"：没有就先回去干活（还有空格时），
        # **不消耗轮数**——0.7.40 A2 里"空格 1、没有可卖叠"的无效轮会把 6 轮预算烧光。
        harvested_now = tuple(sorted(getattr(self.worker, "harvested", None) or {}))
        pre_plan = slot_relief_plan(obs, free_slots=free_slots, free_slots_status=status,
                                    trigger_free_slots=SLOT_RESERVE, max_stacks=1,
                                    prefer_qids=harvested_now)
        if not harvested_now and not pre_plan.get("slots"):
            reason = str(pre_plan.get("skipReason") or "没有可腾的来源（出货/卖出都空）")
            if need > 0:
                if int(free_slots) <= 0:
                    self._note_inventory_blocked(
                        obs, rep, free_slots=int(free_slots), reason=reason)
            else:
                # 压力通道腾不出来**不是失败**：清障/浇水照常干（掉落会丢 → 逐格 loot_lost 留痕）。
                self._note_slot_pressure_stuck(
                    obs, rep, free_slots=int(free_slots), reason=reason)
            # last-resort space relief: ship one non-protected stack
            if int(free_slots) <= 0:
                _shipped = self._ship_one_stack_for_space(obs, rep)
                if _shipped:
                    return True
            return False
        if self.slot_relief_today >= SLOT_RELIEF_MAX:
            reason = (f"腾格回路已用满 {SLOT_RELIEF_MAX} 轮（目标 {target_free} 格、"
                      f"现有 {free_slots} 格）")
            if need > 0:
                self._note_inventory_blocked(
                    obs, rep, free_slots=int(free_slots), reason=reason)
            else:
                self._note_slot_pressure_stuck(
                    obs, rep, free_slots=int(free_slots), reason=reason)
            return False
        # 【task-235 并入】卖之前先清模态：模态挡着时 sell 会被 ui_modal 拒，白跑一轮。
        obs = self._dismiss_stray_menu(obs, rep, where="slot_relief")
        is_modal, menu, _ui = self._modal_info(obs)
        if is_modal:
            reason = f"卖之前模态关不掉（{menu!r}）⇒ 这一轮不卖，如实收尾"
            if need > 0:
                self._note_inventory_blocked(
                    obs, rep, free_slots=int(free_slots), reason=reason)
            else:
                self._note_slot_pressure_stuck(
                    obs, rep, free_slots=int(free_slots), reason=reason)
            return False
        self.slot_relief_today += 1
        self._space_skip_reason = ""
        self._journal("slot_relief_noted", free_slots=int(free_slots), reserve=SLOT_RESERVE,
                      demand=int(demand), demand_basis=str(demand_basis),
                      target_free=int(target_free), round=self.slot_relief_today,
                      limit=SLOT_RELIEF_MAX, pressure=bool(space_pressure),
                      note=("背包真满（0 空格）⇒ collect/清障/浇水之前先腾格"
                            "（掉落会被游戏拒收；腾不出就如实留痕，不判失败）")
                      if need <= 0 else
                      "背包低于当天收获需求的水位 ⇒ collect/清障/浇水之前先腾格"
                      "（掉落与收获也会填包，等 0 格才动会像 run A′ 那样收不进来）")
        shipped = False
        trigger = ""
        money_before = FarmWorker.money(obs)
        rows_before = len(FarmWorker.player_of(obs).get("inventory") or [])
        try:
            shipped = self._ship_loot(obs, rep)
        except Exception:                       # 出货失败绝不打断日循环（下一层再试）
            shipped = False
        if shipped:
            trigger = "harvest_bound"
            obs = self._snap_or(obs)
        free_now = int(self._bag_state(obs)[0])
        if need > 0:
            try:
                if self._sell_surplus_for_slot(obs, rep):
                    trigger = trigger or "short_money"
                    obs = self._snap_or(obs)
            except Exception:                   # 卖货失败同样不打断（腾不出来会如实记账）
                pass
            free_now = int(self._bag_state(obs)[0])
        # 空格压力通道（task-232 + task-237）：卖到目标水位，每叠一卖、每次重观测。
        while (int(free_now) < int(target_free)
               and self.slot_relief_stacks_today < SLOT_RELIEF_MAX_STACKS_TOTAL):
            want = min(int(target_free) - int(free_now),
                       SLOT_RELIEF_MAX_STACKS_TOTAL - int(self.slot_relief_stacks_today))
            if want <= 0:
                break
            try:
                sold_now = self._sell_surplus_for_space(obs, rep, max_stacks=want)
            except Exception:               # 白名单/观测异常不打断（会如实 blocked）
                sold_now = []
            if not sold_now:
                break
            trigger = trigger or "space_pressure"
            obs = self._snap_or(obs)
            after = int(self._bag_state(obs)[0])
            if after <= int(free_now):          # 卖了但空格没增 ⇒ 不再重复请求（下面双差分判 failed）
                break
            free_now = after
        after_slots = int(self._bag_state(obs)[0])
        freed = max(0, int(after_slots) - int(free_slots))
        reached = bool(int(after_slots) >= int(target_free))
        # 【task-232】双差分复核：卖出去的东西必须让**背包行数真的减少**，且钱**当天不变**
        # （钱只由下一次 NewDay 结算；钱变了说明有谁在脑侧写钱 —— 那是红线）。
        money_after = FarmWorker.money(obs)
        rows_after = len(FarmWorker.player_of(obs).get("inventory") or [])
        sold = list(self.slot_relief_sold)
        blocked_reason = ""
        failed = False
        if sold:
            if rows_after >= rows_before:
                failed = True
                blocked_reason = (f"卖了 {len(sold)} 叠但背包行数没减少（{rows_before}→{rows_after}）"
                                  "⇒ 出货/卖出没有真的生效")
            elif int(money_after) != int(money_before):
                failed = True
                blocked_reason = (f"钱数变了（{money_before}→{money_after}）：钱只能由游戏的"
                                  "下一次 NewDay 结算，脑侧不许自己加钱")
        self._journal("slot_relief", need=need, freed=freed, shipped=bool(shipped),
                      freeSlots_before=int(free_slots), freeSlots_after=int(after_slots),
                      before_free=int(free_slots), after_free=int(after_slots),
                      trigger=(trigger or "none"), sold=sold,
                      stacks_today=int(self.slot_relief_stacks_today),
                      max_stacks=SLOT_RELIEF_MAX_STACKS_TOTAL,
                      money_before=int(money_before), money_after=int(money_after),
                      rows_before=int(rows_before), rows_after=int(rows_after),
                      failed=bool(failed), blocked_reason=blocked_reason,
                      round=self.slot_relief_today, max_rounds=SLOT_RELIEF_MAX,
                      reserve=SLOT_RESERVE, demand=int(demand),
                      demand_basis=str(demand_basis), target_free=int(target_free),
                      reached=bool(reached), pressure=bool(space_pressure),
                      stage="slot_relief",
                      note=("空格压力通道（背包真满 0 格）：腾出格子后重新决策"
                            "（否则清障掉落会被游戏拒收）")
                      if need <= 0 else
                      "腾出格子后重新决策（先腾格、再收/清/浇）；腾 0 格 ⇒ 立刻如实 "
                      "inventory_blocked，不空转")
        if failed:
            self._note_inventory_blocked(obs, rep, free_slots=after_slots,
                                         reason=blocked_reason)
            # 本轮 0 格 ⇒ 封板（不拿"再试一次"烧轮数）；封板 ≠ 认"腾不出"，
            # `inventory_blocked` 仍只由四门槛决定（卡 D B）。
            self.slot_relief_today = max(int(self.slot_relief_today), int(SLOT_RELIEF_MAX))
            return False
        if reached:
            rep.notes.append(f"腾格到需求水位：空格 {free_slots} → {after_slots}"
                             f"（目标 {target_free}，第 {self.slot_relief_today} 轮，"
                             f"trigger={trigger or 'none'}）")
            return True
        if freed >= 1:
            rep.notes.append(f"腾格：空格 {free_slots} → {after_slots}"
                             f"（目标 {target_free}，第 {self.slot_relief_today} 轮，"
                             f"trigger={trigger or 'none'}）")
            return True
        if sold:
            no_candidate = (f"卖了 {len(sold)} 叠仍不够（空格 {after_slots} / 目标 {target_free}）")
            if self.slot_relief_stacks_today >= SLOT_RELIEF_MAX_STACKS_TOTAL:
                no_candidate += f"；叠数已用满 {SLOT_RELIEF_MAX_STACKS_TOTAL}"
        else:
            no_candidate = ("没有可卖的盈余叠（出货箱白名单空 + 已知盈余表里没有超 K 的叠）"
                            "⇒ 腾不出格子")
            if getattr(self, "_space_skip_reason", ""):
                no_candidate = f"{no_candidate}；空格压力通道：{self._space_skip_reason}"
        # 【task-237】关键边界：**还有空格**时腾不出来 ≠ 背包堵死 —— 收获仍可先塞进现有空格、
        # 出货/卖出再跟上（0.7.40 A2 是真堵死：0 空格且无可卖叠）。只有 0 空格才算
        # `inventory_blocked`（否则会把"边收边腾"的正常日误判成堵死，task-198 用例钉死）。
        if need > 0 and int(free_slots) <= 0:
            self._note_inventory_blocked(obs, rep, free_slots=after_slots,
                                         reason=no_candidate)
        elif space_pressure and freed <= 0:
            # 【task-16】压力通道腾不出来 ⇒ 只留痕（**不判失败**、不置 inventory_blocked_today）。
            self._note_slot_pressure_stuck(
                obs, rep, free_slots=int(after_slots), reason=no_candidate)
        elif sold:
            rep.notes.append(f"腾格未达需求水位：空格 {after_slots} / 目标 {target_free}"
                             f"（还有可用空格，先继续干活）")
        # 【task-198 钉死 / task-28 卡 D】本轮腾出 0 格 ⇒ 立刻封板，绝不按轮数空转。
        # 封板只代表"今天不再试腾格"，**不**等于认 `inventory_blocked` —— 那条仍由四门槛
        # （free==0 / relief_exhausted / exec==0 / malformed==0）逐条裁决；`stuck:` 永不产生。
        if freed <= 0:
            self.slot_relief_today = max(int(self.slot_relief_today), int(SLOT_RELIEF_MAX))
        return False

    def _end_inventory_blocked(self, obs: dict[str, Any], rep: DayReport) -> str:
        """【task-198】背包堵住 ⇒ 诚实收工：睡一觉让游戏日翻篇，但 `ended_by` 点名原因。

        三处收尾口都要用它（`sleep_guard` 分支、作业区拿不出目标的出口、idle 3 轮出口）：
        否则"背包满 + 多格熟作物"会被报成 `no_work`（假达标）或 `stuck`（误报卡死），
        而真实情况是"不是没活，是背包堵住"。

        语义边界（【task-28 卡 D】更新）：本方法**只能**在 `_note_inventory_blocked` 四门槛
        全过、`inventory_blocked_today` 已置位后被调用（调用点都先过那个门槛）；因此
        `ended_by=inventory_blocked` 本身即"带证据的诚实收工"。`day_justified` 由
        `is_justified_end()` 的 `HONEST_INVENTORY_END_REASONS` 分支判：**要求 `ended_by` 是
        `inventory_blocked` 且 `pending_executable==0`**（`stuck` 永不认）。`no_slot` 不是 hard
        failure（`failed_steps` 不计）⇒ `no_hard_failures` 仍为真。返回值 = 最终的 `ended_by`。
        """
        free_slots, _need, _status = self._bag_state(obs)
        ev = self.bag_evidence_today or self._bag_relief_evidence(obs)
        why = (f"背包满（空格 {free_slots}）且今天已经腾不出格子：不是没活、也不是 stuck —— "
               f"是背包堵住（可卖叠 {int(ev.get('sellable_above_keep') or 0)} 叠、"
               f"轮数 {int(ev.get('relief_rounds') or 0)}/{int(ev.get('relief_round_limit') or 0)}、"
               f"叠数 {int(ev.get('sold_stacks') or 0)}/{int(ev.get('sold_stack_limit') or 0)}）"
               f"；证据门槛 4/4 已过（free_slots==0 / relief_exhausted / exec==0 / malformed==0）")
        slept_by, slept_reason = self._do_sleep(obs, rep, f"inventory_blocked:{why}")
        if slept_by == "sleep_failed":
            rep.ended_by, rep.ended_reason = slept_by, slept_reason
        else:
            rep.ended_by, rep.ended_reason = "inventory_blocked", f"inventory_blocked:{why}"
        return rep.ended_by

    def _end_clear_gate(self, obs: dict[str, Any], rep: DayReport) -> tuple[str, str]:
        """【devcoder-clear-gate D】满包清障闸收工口：`ended_by="clear_gate"` + 诚实的 `ended_reason`。

        为什么需要（A9 第 5 跑 `logs/longrun-runA9-0750.jsonl`，winter27/28）：执行层
        `_stage_tiles("clear_area")` 因满包闸**整池清零**（`return []`），而守卫/选区/日终快照
        都不知道这道闸 ⇒ 快照 `pending_executable=206/195`、守卫一直喊"还有地要清"、
        `_ensure_plot` 永不为 None ⇒ `decision.intents` 每轮非空 ⇒ 主循环既收不了工也换不了片
        ⇒ `idle` 3 轮 ⇒ `stuck:`（整天报废）。本方法给这条真实状态一个**点名**的收尾口。

        语义边界：
        * 只允许在 `_clear_gate_only_work(obs)` 为真时调用（背包 0 空格 + 腾格用尽 + 剩余活
          **全是**被闸住的清障格）；
        * `require_work=False`：理由同 `_stuck_flush`（0 动作日传 True 会被
          `slept_without_work` 挡成"本日不推进"，整轮自停）；
        * `clear_gate` **不在** `JUSTIFIED_END_REASONS` / `HONEST_*` 里，且
          `is_justified_end(gated=…)` 见 `gated>0` 直接 False ⇒ `day_justified=False`、
          **永不 VERIFIED**（这是"活被背包闸住"，不是"没活可做"）；
        * 不新增 journal 事件名：证据走既有 `slot_relief{trigger=clear_gate}` 与
          `day_end.pending_gated` / `bag_evidence`。
        """
        free_slots, _need, _status = self._bag_state(obs)
        snap = self._pending_snapshot(obs)
        # "剩余 N 格"= 当前观测窗口里"能做、只因闸而不做"的清障格数（拿不到就退回账本口径的
        # gated 数）—— 两种口径都只描述同一件事：这些格全是清障类。
        tmap = FarmWorker.tiles_of(obs)
        visible_clear = sum(
            1 for t, tv in tmap.items()
            if not tv.get("crop") and str(tv.get("kind") or "") in CLEARABLE_KINDS
            and not _tool_blocked_tv(tv) and t not in self.blocked
            and t not in self.resume_stall_tiles and t not in self.encircled_day)
        remaining = visible_clear or int(snap.get("gated") or 0)
        reason = (f"clear_gate:背包0空格且腾格手段用尽（free_slots={free_slots} / "
                  f"relief_exhausted / 剩余 {remaining} 格全是清障类）")
        # 抬走"今天不再新开 clear_area"的证据（既有事件名 + 既有字段集，幂等：一天只记一条）。
        self._note_clear_area_bag_gate("clear_area", self._clear_bag_gate_reason(obs))
        ended_by, ended_reason = self._do_sleep(obs, rep, reason, require_work=False)
        if ended_by == "sleep_failed":
            rep.ended_by, rep.ended_reason = ended_by, ended_reason
        else:
            rep.ended_by, rep.ended_reason = "clear_gate", reason
        rep.notes.append(
            f"满包清障闸收口：{reason} ⇒ 今天不再新开 clear_area（开路必要前置仍允许）；"
            "这不是「没活可做」，也不是 stuck —— 当天 day_justified=False、不 VERIFIED")
        return rep.ended_by, rep.ended_reason

    # ------------------------------------------------------------------ task-25 rev4
    #: Pierre 背包升级（12→24 / 2000g）的**对话购买**。判据只看观测差分：
    #:   * 成功 ⇔ `money_after == money_before - 2000` 且 `inventoryCount 12→24`；
    #:   * 失败码单列（`money_not_deducted` / `capacity_not_changed` / `money_diff_ambiguous` /
    #:     `response_not_found` / `dialogue_not_question` / `npc_not_found` / `no_action` /
    #:     `not_supported` / `not_adjacent_unreachable` / `event_hang` / `goto_shop_failed` / `timeout`）；
    #:   * 一切走游戏入口：`talk`（Mod 调 `NPC.checkAction`）+ `dismiss_modal{answerText:"Purchase"}`
    #:     （Mod 调 `DialogueBox.answerDialogue`）；**绝不**直写 money/Items/MaxItems、
    #:     绝不调 `increaseBackpackSize`、绝不合成键鼠。
    #: 安全降级：talk 不可用/失败一律记失败码后继续农务；一天只走一个回合、回合内 ≤2 次 talk；
    #: 整条流程 ≤ `BACKPACK_UPGRADE_DEADLINE_S` 秒；失败**不**影响 `checks`/`day_justified`。

    @staticmethod
    def _obs_player_int(obs: Mapping[str, Any], key: str) -> int | None:
        player = obs.get("player") if isinstance(obs, Mapping) else None
        if not isinstance(player, Mapping):
            return None
        raw = player.get(key)
        if isinstance(raw, bool) or not isinstance(raw, int):
            return None
        return int(raw)

    def _backpack_capacity(self, obs: Mapping[str, Any]) -> int | None:
        cap = self._obs_player_int(obs, "inventoryCount")
        return cap if cap is not None and cap > 0 else None

    def _backpack_gate(self, obs: Mapping[str, Any]) -> tuple[bool, str]:
        """今天该不该试买背包升级（fail-closed：任何证据缺失都不试）。"""
        cap = self._backpack_capacity(obs)
        if cap is None:
            return False, "capacity_unknown"
        if cap >= BACKPACK_UPGRADE_CAPACITY:
            return False, "already_upgraded"
        if cap != BACKPACK_BASE_CAPACITY:
            return False, "capacity_unexpected"
        if self.backpack_ok_today:
            return False, "upgraded_today"
        if self.backpack_tried_today or self.backpack_attempts_today >= BACKPACK_UPGRADE_MAX_ATTEMPTS:
            return False, "attempt_limit"
        money = self._obs_player_int(obs, "money")
        if money is None:
            return False, "money_unknown"
        if money < BACKPACK_UPGRADE_PRICE:
            return False, "cannot_afford"
        # 【devcoder-backpack-interact】背包升级是柜台展示物（GameLocation.checkAction），
        # 触发原语是 `interact`（不是 `talk`/`NPC.checkAction`）。桥没有 interact 原语时安全降级。
        if getattr(self.client, "interact", None) is None:
            return False, "interact_unavailable"
        return True, ""

    def _backpack_skip(self, rep: DayReport, why: str, obs: Mapping[str, Any]) -> None:
        rep.backpack_upgrade_skip = str(why)
        # 只在"值得知道"的跳过原因上留一条（每天最多一条）：钱不够 / 桥没有 talk 原语 /
        # task-35 默认关闭。**默认关闭只留痕、绝不发请求**；也不往 rep.notes 里加噪音。
        if (why in ("cannot_afford", "interact_unavailable", "attempt_limit", "disabled")
                and not self.backpack_skip_noted):
            self.backpack_skip_noted = True
            if why == "cannot_afford":
                reason = "钱不够升级（需要 2000g）"
            elif why == "interact_unavailable":
                reason = "桥没有 interact 原语（Mod 太旧）⇒ 不试柜台背包展示物交互"
            elif why == "attempt_limit":
                reason = ("今天背包升级交互次数已用满"
                          f"（≤{BACKPACK_UPGRADE_MAX_ATTEMPTS} 次）⇒ 不再发请求")
            else:
                reason = ("背包升级对话购买默认关闭（task-34 探针：进 SeedShop 触发过场事件 "
                          "3102768、背包升级入口未取得）⇒ 今天不发 goto/interact；"
                          "要启用加 --enable-backpack-upgrade 或 AGENTFARM_ENABLE_BACKPACK_UPGRADE=1")
            self._journal(
                "buy", source="backpack_dialogue", item="Backpack",
                purpose="backpack_upgrade", shop=BACKPACK_UPGRADE_SHOP,
                npc=BACKPACK_UPGRADE_NPC, ok=False, code=str(why), status="skipped",
                reason=reason,
                money_before=self._obs_player_int(obs, "money"),
                capacity_before=self._backpack_capacity(obs),
                attempts=self.backpack_attempts_today,
                limit=BACKPACK_UPGRADE_MAX_ATTEMPTS,
            )
        if why != "disabled":
            if why == "cannot_afford":
                note = "钱不够 2000g"
            elif why == "interact_unavailable":
                note = "桥没有 interact 原语（安全降级，不影响农务/判据）"
            elif why == "attempt_limit":
                note = f"今天交互次数已用满（≤{BACKPACK_UPGRADE_MAX_ATTEMPTS} 次）"
            else:
                note = "安全降级，不影响农务/判据"
            rep.notes.append("背包升级今天不试：" + note)

    def _backpack_journal(self, rep: DayReport, *, ok: bool, code: str, status: str,
                          reason: str, money_before: int | None, money_after: int | None,
                          cap_before: int | None, cap_after: int | None,
                          answer_text: str = "", act: Mapping[str, Any] | None = None,
                          elapsed_ms: float = 0.0,
                          extra: Mapping[str, Any] | None = None) -> None:
        """失败/成功都复用既有 `buy` 事件名（不新增 journal 事件；analyzer 桶不漂移）。"""
        fields: dict[str, Any] = dict(
            source="backpack_dialogue", item="Backpack", purpose="backpack_upgrade",
            shop=BACKPACK_UPGRADE_SHOP, npc=BACKPACK_UPGRADE_NPC,
            ok=bool(ok), code=str(code), status=str(status), reason=str(reason),
            money_before=money_before, money_after=money_after,
            capacity_before=cap_before, capacity_after=cap_after,
            answer_text=str(answer_text or ""),
            attempts=int(self.backpack_attempts_today),
            limit=int(BACKPACK_UPGRADE_MAX_ATTEMPTS),
            elapsed_ms=int(round(float(elapsed_ms))),
        )
        if isinstance(act, Mapping):
            for key in ("applied", "activeMenu",
                        "dialogueIsQuestion", "dialogueResponses"):
                if key in act:
                    fields[key] = act[key]
        if extra:
            fields.update(dict(extra))
        self._journal("buy", **fields)

    def _backpack_fail(self, rep: DayReport, *, code: str, reason: str,
                       money_before: int | None, money_after: int | None,
                       cap_before: int | None, cap_after: int | None,
                       answer_text: str = "", act: Mapping[str, Any] | None = None,
                       elapsed_ms: float = 0.0,
                       extra: Mapping[str, Any] | None = None) -> None:
        code = str(code or "failed")
        if code not in rep.backpack_upgrade_failures:
            rep.backpack_upgrade_failures.append(code)
        if rep.backpack_capacity_before is None:
            rep.backpack_capacity_before = cap_before
        rep.backpack_capacity_after = cap_after
        self._backpack_journal(
            rep, ok=False, code=code, status="failed", reason=reason,
            money_before=money_before, money_after=money_after,
            cap_before=cap_before, cap_after=cap_after,
            answer_text=answer_text, act=act, elapsed_ms=elapsed_ms, extra=extra)
        rep.notes.append(
            f"背包升级失败（{code}）：{reason} —— 不是任务失败，不影响农务/判据")

    def _backpack_find_object_tile(self, obs: Mapping[str, Any]) -> list[int] | None:
        """【devcoder-backpack-interact】在 `location.objects`/`furniture` 里找"待售背包展示物"
        的格，命中就返回 `[x, y]`；找不到（真机未必给 objects 桶）⇒ 返回 None，交给
        `interact(tile=None)`（桥会朝玩家面朝的格做 GameLocation.checkAction）兜底。
        """
        loc = obs.get("location") or {}
        # `location.objects`/`location.furniture` 本身就是"对象字典的列表"，要展平后才能逐个
        # 看每个对象字典（否则 `bucket` 会迭代到整个列表、isinstance(Mapping) 失败、直接漏掉）。
        for bucket in list(loc.get("objects") or []) + list(loc.get("furniture") or []):
            if not isinstance(bucket, Mapping):
                continue
            label = " ".join(str(bucket.get(k, "")) for k in
                             ("name", "type", "label", "displayName"))
            low = label.casefold()
            if "backpack" in low or "for sale" in low:
                t = bucket.get("tile")
                if isinstance(t, (list, tuple)) and len(t) >= 2:
                    return [int(t[0]), int(t[1])]
        return None

    def _backpack_interact_once(self, tile: list[int] | None) -> dict[str, Any]:
        """【devcoder-backpack-interact】对柜台背包展示物（GameLocation.checkAction）发一次
        `interact`。失败要落码，不能把当天拖死；回执不是对象也落码。
        """
        try:
            res = self.client.interact(  # type: ignore[attr-defined]
                tile=tile, timeout_ms=BACKPACK_TALK_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001 - 失败要落码，不能把当天拖死
            return {"ok": False, "code": "interact_error", "status": "interact_error",
                    "reason": f"interact 抛错：{exc}"}
        if not isinstance(res, Mapping):
            return {"ok": False, "code": "interact_bad_receipt", "status": "interact_bad_receipt",
                    "reason": "interact 回执不是对象"}
        return dict(res)

    def _backpack_clear_intro(self, obs: Mapping[str, Any],
                              _elapsed_ms: Callable[[], float] | None = None) -> dict[str, Any]:
        """【devcoder-backpack-interact】进 SeedShop 可能触发过场事件（task-34 实机事件
        3102768）⇒ 先把挡路的 `eventUp`/`isModal` 用 `advance_dialogue` 推开，≤10 次且受
        预算约束；推不动就原样退回 obs（由调用方决定 load_save 自愈或 event_hang）。
        """
        ui = obs.get("ui") or {}
        for _ in range(10):
            if _elapsed_ms is not None and _elapsed_ms() >= BACKPACK_UPGRADE_DEADLINE_S * 1000.0:
                break
            if not (ui.get("eventUp") or ui.get("isModal")):
                break
            try:
                self.client.advance_dialogue(max_steps=1)
            except Exception:  # noqa: BLE001 - 推不动就按卡死收口
                break
            try:
                obs = self._snap_or(dict(obs) if isinstance(obs, Mapping) else {})
            except Exception:  # noqa: BLE001
                break
            ui = obs.get("ui") or {}
        return obs

    def _backpack_recover_event_hang(self, obs: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
        """事件卡死自愈：连续 ≤10 次受控推进都没把 `eventUp` 推走 ⇒ 认 `event_hang`。

        只对**非提问**的 `eventUp` 动手（提问/职业选择一律不碰，交给既有事件政策诚实收尾）；
        本身不改任何经济状态，也不替游戏选选项。
        """
        last: dict[str, Any] = dict(obs) if isinstance(obs, Mapping) else {}
        for _ in range(10):
            try:
                self.client.advance_dialogue(max_steps=1)
            except Exception:  # noqa: BLE001 - 推进不了就按卡死收口
                return False, last
            try:
                last = self._snap()
            except Exception:  # noqa: BLE001
                return False, last
            ui = last.get("ui") or {}
            if not ui.get("eventUp") and not ui.get("isModal"):
                return True, last
        return False, last

    def _backpack_return_to_farm(self) -> None:
        """买完/失败后先回农场（失败不吞：回不去只留 note，主循环下一轮再兜）。"""
        try:
            st = self.worker.ensure_location(self.farm)
        except Exception:  # noqa: BLE001
            return
        if not getattr(st, "ok", True):
            self._say(f"[backpack] 购买流程后回农场失败：{getattr(st, 'reason', '')}")

    def _backpack_escape_dialogue(self) -> None:
        """失败但对话已经开出来了：把**我们自己开的**那个对话关掉。

        为什么必须关：`TalkSkill` 调的是游戏 `NPC.checkAction`，Pierre 的背包升级对话是
        一个"一问一答"的 `DialogueBox`；如果我们读了选项但**答不了**（没匹配文本/歧义/
        回执不成立），把提问对话原样留在场上，下一轮模态守卫会把它当**事件提问**处理 ⇒
        `blocked_event` 整天停摆。这里只关 UI、不替游戏选任何选项（`dismiss_modal` 无
        `answer_text` ⇒ Mod 走 `closeDialogue`，不是 `answerDialogue`）。
        """
        try:
            self.client.dismiss_modal(timeout_ms=5000)
        except Exception:  # noqa: BLE001 - 关不掉也只是留痕，不把当天拖死
            pass

    def _maybe_buy_backpack_upgrade(self, obs: Mapping[str, Any], rep: DayReport) -> bool:
        """开工前试买 Pierre 背包升级；返回 True = 本轮已处理（成功完成），主循环 continue。

        【devcoder-backpack-interact】根因修复：原代码用 `talk("Pierre")`（NPC.checkAction）
        只能拿到 "Sigh..."，永远开不出背包升级的购买框 ⇒ 永久【无法判定】。背包升级是柜台
        展示物，正确原语是 `interact`（GameLocation.checkAction）：对着柜台背包展示物（或
        `tile=None` 朝面朝格）interact ⇒ 由游戏弹出带 "Purchase" 选项的提问框 ⇒ `dismiss_modal`
        应答，最终**由游戏代码**扣 2000g 并扩容（脑侧只看观测差分，绝不直接写钱/容量）。

        【task-35】默认关闭（`self.backpack_upgrade_enabled=False`）：不发任何 goto/interact/buy，
        只留 `backpack_upgrade_skip="disabled"` + 一条 skipped 留痕；显式开启后行为与 0.7.46 一致。
        """
        if not self.backpack_upgrade_enabled:
            self._backpack_skip(rep, "disabled", obs)
            return False
        if self.backpack_tried_today:
            return False
        ok, why = self._backpack_gate(obs)
        cap_before = self._backpack_capacity(obs)
        money_before = self._obs_player_int(obs, "money")
        if not ok:
            self._backpack_skip(rep, why, obs)
            return False
        start = time.monotonic()
        self.backpack_tried_today = True
        rep.backpack_capacity_before = cap_before
        rep.backpack_upgrade_attempts = 0

        def _elapsed_ms() -> float:
            return (time.monotonic() - start) * 1000.0

        st = self.worker.ensure_location(BACKPACK_UPGRADE_SHOP)
        if not getattr(st, "ok", False):
            self._backpack_fail(
                rep, code="goto_shop_failed",
                reason=f"去 {BACKPACK_UPGRADE_SHOP} 失败：{getattr(st, 'reason', '')}",
                money_before=money_before, money_after=money_before,
                cap_before=cap_before, cap_after=cap_before, elapsed_ms=_elapsed_ms())
            self._backpack_return_to_farm()
            return False
        obs = self._snap_or(dict(obs) if isinstance(obs, Mapping) else {})

        # 【devcoder-backpack-interact】进店先清过场事件（task-34 实机事件 3102768），推不动就
        # load_save 自愈；仍卡 ⇒ event_hang（不硬做题、不替游戏选选项）。
        obs = self._backpack_clear_intro(obs, _elapsed_ms)
        ui = obs.get("ui") or {}
        if ui.get("eventUp") or ui.get("isModal"):
            try:
                self.client.load_save(force=True)
            except Exception:  # noqa: BLE001 - 自愈失败只是换一条码
                pass
            st2 = self.worker.ensure_location(BACKPACK_UPGRADE_SHOP)
            if not getattr(st2, "ok", False):
                self._backpack_fail(
                    rep, code="goto_shop_failed",
                    reason=(f"自愈后回 {BACKPACK_UPGRADE_SHOP} 失败："
                            f"{getattr(st2, 'reason', '')}"),
                    money_before=money_before, money_after=money_before,
                    cap_before=cap_before, cap_after=cap_before,
                    elapsed_ms=_elapsed_ms())
                self._backpack_return_to_farm()
                return False
            obs = self._snap_or(dict(obs) if isinstance(obs, Mapping) else {})
            ui = obs.get("ui") or {}
            if ui.get("eventUp") or ui.get("isModal"):
                self._backpack_fail(
                    rep, code="event_hang",
                    reason="进店过场事件清不掉（含 load_save 自愈后仍卡）⇒ 不硬做题",
                    money_before=money_before,
                    money_after=self._obs_player_int(obs, "money"),
                    cap_before=cap_before, cap_after=self._backpack_capacity(obs),
                    elapsed_ms=_elapsed_ms())
                self._backpack_return_to_farm()
                return False

        # 定位柜台背包展示物（GameLocation.checkAction 的触发物），发 interact
        tile = self._backpack_find_object_tile(obs)
        act = self._backpack_interact_once(tile)
        self.backpack_attempts_today += 1
        rep.backpack_upgrade_attempts = self.backpack_attempts_today
        code = str(act.get("code") or act.get("status") or "")

        # no_action / not_supported 且仍有非模态 eventUp ⇒ 清场后再试一次（受预算约束）
        if code in ("no_action", "not_supported") and ui.get("eventUp") and not ui.get("isModal"):
            recovered, obs = self._backpack_recover_event_hang(obs)
            within = (self.backpack_attempts_today < BACKPACK_UPGRADE_MAX_ATTEMPTS
                      and _elapsed_ms() < BACKPACK_UPGRADE_DEADLINE_S * 1000.0)
            if recovered and within:
                act = self._backpack_interact_once(tile)
                self.backpack_attempts_today += 1
                rep.backpack_upgrade_attempts = self.backpack_attempts_today
                code = str(act.get("code") or act.get("status") or "")
            else:
                code = "event_hang"

        if code != "ok" or not act.get("applied"):
            if not code:
                code = "interact_failed"
            self._backpack_fail(
                rep, code=code,
                reason=str(act.get("reason") or f"interact 失败（code={code}）"),
                money_before=money_before,
                money_after=self._obs_player_int(obs, "money"),
                cap_before=cap_before, cap_after=self._backpack_capacity(obs),
                act=act, elapsed_ms=_elapsed_ms())
            self._backpack_return_to_farm()
            return False

        question = bool(act.get("dialogueIsQuestion"))
        raw_responses = act.get("dialogueResponses") or []
        responses = [str(r) for r in raw_responses if isinstance(r, (str, int))]
        if not question:
            self._backpack_fail(
                rep, code="dialogue_not_question",
                reason=(f"interact 开了对话却没有提问（activeMenu={act.get('activeMenu')!r}，"
                        f"responses={responses}）⇒ 不猜选项"),
                money_before=money_before,
                money_after=self._obs_player_int(obs, "money"),
                cap_before=cap_before, cap_after=self._backpack_capacity(obs),
                act=act, elapsed_ms=_elapsed_ms())
            self._backpack_escape_dialogue()
            self._backpack_return_to_farm()
            return False
        needle = BACKPACK_UPGRADE_ANSWER.strip().casefold()
        matches = [r for r in responses if r.strip().casefold() == needle]
        if not matches:
            self._backpack_fail(
                rep, code="response_not_found",
                reason=(f"对话选项里没有精确匹配「{BACKPACK_UPGRADE_ANSWER}」的项"
                        f"（实际 {responses}）⇒ 不发应答、不猜选项"),
                money_before=money_before,
                money_after=self._obs_player_int(obs, "money"),
                cap_before=cap_before, cap_after=self._backpack_capacity(obs),
                answer_text=BACKPACK_UPGRADE_ANSWER, act=act,
                elapsed_ms=_elapsed_ms())
            self._backpack_escape_dialogue()
            self._backpack_return_to_farm()
            return False
        if len(matches) > 1:
            self._backpack_fail(
                rep, code="response_ambiguous",
                reason=f"「{BACKPACK_UPGRADE_ANSWER}」命中 {len(matches)} 个选项 ⇒ 不替游戏猜",
                money_before=money_before,
                money_after=self._obs_player_int(obs, "money"),
                cap_before=cap_before, cap_after=self._backpack_capacity(obs),
                answer_text=BACKPACK_UPGRADE_ANSWER, act=act,
                elapsed_ms=_elapsed_ms())
            self._backpack_escape_dialogue()
            self._backpack_return_to_farm()
            return False

        # ---- 应答 + 观测差分窗口（同天、不跨 NewDay；窗口里出现 sell/ship/NewDay ⇒ 歧义失败） ----
        obs2 = self._snap_or(dict(obs))
        money_b = self._obs_player_int(obs2, "money")
        cap_b = self._backpack_capacity(obs2)
        day_key = FarmWorker.day_key(obs2)
        window_start = len(self.entries)
        try:
            self.client.dismiss_modal(
                answer_text=BACKPACK_UPGRADE_ANSWER, timeout_ms=20000)
        except Exception as exc:  # noqa: BLE001 - 应答失败也要落码
            self._backpack_fail(
                rep, code="answer_failed", reason=f"dismiss_modal 应答抛错：{exc}",
                money_before=money_b, money_after=self._obs_player_int(obs2, "money"),
                cap_before=cap_b, cap_after=self._backpack_capacity(obs2),
                answer_text=BACKPACK_UPGRADE_ANSWER, act=act,
                elapsed_ms=_elapsed_ms())
            self._backpack_escape_dialogue()
            self._backpack_return_to_farm()
            return False
        obs3 = self._snap_or(obs2)
        money_a = self._obs_player_int(obs3, "money")
        cap_a = self._backpack_capacity(obs3)
        ambiguous = False
        if FarmWorker.day_key(obs3) != day_key:
            ambiguous = True
        for entry in self.entries[window_start:]:
            if str(entry.get("event")) in ("sell", "ship", "day_start", "day_end"):
                ambiguous = True
                break
        if ambiguous:
            self._backpack_fail(
                rep, code="money_diff_ambiguous",
                reason=("购买窗口里出现了 sell/ship/跨日事件 ⇒ 钱的变化无法归因给背包升级"
                        f"（money {money_b}→{money_a}，capacity {cap_b}→{cap_a}）"),
                money_before=money_b, money_after=money_a,
                cap_before=cap_b, cap_after=cap_a,
                answer_text=BACKPACK_UPGRADE_ANSWER, act=act,
                elapsed_ms=_elapsed_ms())
            self._backpack_escape_dialogue()
            self._backpack_return_to_farm()
            return False
        money_ok = (money_b is not None and money_a is not None
                    and money_a == money_b - BACKPACK_UPGRADE_PRICE)
        cap_ok = (cap_b == BACKPACK_BASE_CAPACITY
                  and cap_a == BACKPACK_UPGRADE_CAPACITY)
        if money_ok and cap_ok:
            self.backpack_ok_today = True
            rep.backpack_upgrade_ok = True
            rep.backpack_capacity_after = cap_a
            rep.backpack_upgrade_attempts = self.backpack_attempts_today
            self._backpack_journal(
                rep, ok=True, code="ok", status="ok",
                reason=(f"背包升级成功（观测差分）：钱 {money_b}→{money_a}"
                        f"（−{int(money_b) - int(money_a)}），容量 {cap_b}→{cap_a}"),
                money_before=money_b, money_after=money_a,
                cap_before=cap_b, cap_after=cap_a,
                answer_text=BACKPACK_UPGRADE_ANSWER, act=act,
                elapsed_ms=_elapsed_ms())
            rep.notes.append(
                f"背包升级成功：容量 {cap_b}→{cap_a}，钱 {money_b}→{money_a}（对话购买，游戏代码扣钱）")
            self._backpack_return_to_farm()
            return True

        if not money_ok:
            code2 = ("money_not_deducted" if money_a == money_b
                     else "money_unexpected")
            detail = f"钱 {money_b}→{money_a}（期望 −{BACKPACK_UPGRADE_PRICE}）"
        else:
            code2 = "capacity_not_changed"
            detail = f"钱已扣但容量 {cap_b}→{cap_a}（期望 12→24）"
        self._backpack_fail(
            rep, code=code2, reason=f"观测差分不成立：{detail}",
            money_before=money_b, money_after=money_a,
            cap_before=cap_b, cap_after=cap_a,
            answer_text=BACKPACK_UPGRADE_ANSWER, act=act,
            elapsed_ms=_elapsed_ms())
        self._backpack_return_to_farm()
        return False

    def _tool_upgrade_plan(self, obs: dict[str, Any]) -> dict[str, Any] | None:
        """【task-205】今天该不该去铁匠铺：返回 `{"action": "pickup"|"upgrade", ...}` 或 None。

        优先级（**取回优先于新升级**：在途时再买会白扣钱锭，且工具不在身上）：

          1. 有在途 + `daysLeft <= 0` + 背包有空格 ⇒ `pickup`（工具做完了，取回来才能继续用）；
          2. 有在途 + `daysLeft > 0` ⇒ None（还在做，等，别买）；
          3. 无在途 ⇒ 找一件"当前等级 < 3 且钱够、材料够"的工具 ⇒ `upgrade`；
          4. 都没有 ⇒ None。

        ⚠️ 价格/材料用脑侧 `UPGRADE_PRICES`/`UPGRADE_TRADE_ITEMS` 做**粗判**（决定要不要跑一趟），
        真正的数字由 Mod 从货架条目读（名义价 ≠ 实扣价）。`tool_tier == -1`（旧 Mod 没给
        `tools[].upgradeLevel`）⇒ 一律不升级（fail-closed，不许猜等级）。
        """
        being = tool_being_upgraded(obs)
        days = tool_upgrade_days_left(obs)
        free, free_status = player_free_slots(FarmWorker.player_of(obs))
        if being:
            if days is None:
                return {"action": "wait", "reason": "读不到 toolUpgradeDaysLeft（fail-closed，不买）",
                        "being": being.get("name")}
            if days > 0:
                return {"action": "wait", "reason": f"还在升级：daysLeft={days}",
                        "being": being.get("name"), "days_left": days}
            if free_status == "ok" and free <= 0:
                return {"action": "need_slot", "reason": "升级做完了但背包没有空格（pickup 拿不回来）",
                        "being": being.get("name"), "free_slots": free}
            return {"action": "pickup", "being": being.get("name"), "days_left": days,
                    "free_slots": free if free_status == "ok" else None}
        money = FarmWorker.money(obs)
        player = FarmWorker.player_of(obs)
        # 【task-218 ⑥】**升级选型看缺口**：先数"工具够不着 ⇒ 今天挥不了"的格子按所需工具分组
        # （斧/镐），谁堵得多先升谁 —— 用户 m18938「先升级斧子砍树」正是这个判据给出的结论，
        # 依据进 journal（`upgrade_tool.blocked_counts`），不靠拍脑袋。
        blocked_counts: dict[str, int] = {}
        for _t, tv in (FarmWorker.tiles_of(obs) or {}).items():
            if not _tool_blocked_tv(tv):
                continue
            need = str(tv.get("tool") or "")
            if need in ("axe", "pickaxe"):
                blocked_counts[need] = blocked_counts.get(need, 0) + 1
        candidates: list[dict[str, Any]] = []
        for kind in UPGRADE_KINDS:
            tier = tool_tier(obs, kind)
            if tier < 0 or tier >= 3:
                continue
            price = UPGRADE_PRICES.get(tier, 0)
            trade = UPGRADE_TRADE_ITEMS.get(tier, "")
            need = 5
            have = sum(int(it.get("stack") or 0) for it in (player.get("inventory") or [])
                       if str(it.get("qualifiedId") or "") == trade) if trade else 0
            if money >= price and have >= need:
                candidates.append({"action": "upgrade", "kind": kind, "tier": tier,
                                   "price": price, "trade_item": trade, "trade_have": have,
                                   "trade_need": need, "money": money,
                                   "blocked": int(blocked_counts.get(kind, 0))})
        if not candidates:
            return None
        candidates.sort(key=lambda c: (-int(c.get("blocked") or 0),
                                       UPGRADE_KINDS.index(str(c.get("kind")))))
        plan = candidates[0]
        plan["blocked_counts"] = dict(blocked_counts)
        return plan

    def _tool_suspended_stages(self, obs: dict[str, Any]) -> set[str]:
        """【task-205】在途升级期间要暂停的阶段（工具不在身上 ⇒ 那阶段一格都干不成）。"""
        return tool_suspended_stages(obs)

    def _maybe_tool_upgrade(self, obs: dict[str, Any], rep: DayReport) -> bool:
        """【task-205】今天最多一次的铁匠铺动作（升级或取回）。

        * 每天最多 `TOOL_UPGRADE_MAX_PER_DAY` 次；没做成也记一次（原因当天不会自己变好）；
        * 在途期间被暂停的阶段：journal 一条 `tool_upgrade_blocked_work`（如实记账，不是失败）；
        * 判据全靠 `FarmWorker.upgrade_tool()/pickup_tool()` 的**观测差分**；回执只是声明。

        返回 True ⇒ 真的动了世界（调用方 `continue` 重新观测）。
        """
        assert self.worker is not None
        suspended = self._tool_suspended_stages(obs)
        if suspended and not self.tool_upgrade_blocked_noted:
            self.tool_upgrade_blocked_noted = True
            self._journal("tool_upgrade_blocked_work", stages=sorted(suspended),
                          being=(tool_being_upgraded(obs) or {}).get("name"),
                          note="工具在 Clint 那里升级，相关阶段暂停（不是失败，是工具不在身上）")
            rep.notes.append(f"工具升级中，暂停阶段：{'/'.join(sorted(suspended))}")
        plan = self._tool_upgrade_plan(obs)
        action = (plan or {}).get("action")
        # 【task-216 必修 4】`due=False` 的那一天也必须留一条 `tool_upgrade_skipped{which,reason}`：
        # 旧写法只在 `_tool_upgrade_due()==True` 时才调本函数 ⇒ wait/need_slot 日一条留痕都没有，
        # docstring 却声称会留痕（deputy 实测 0 条）。现在 `_run_day` 每轮无条件调用、这里按天去重。
        if not self._tool_upgrade_due(obs):
            if not self.tool_upgrade_skipped_noted:
                self.tool_upgrade_skipped_noted = True
                reason = self._tool_upgrade_skip_reason(obs, plan)
                self._journal("tool_upgrade_skipped", which=action or None, reason=reason,
                              action=action, being=(plan or {}).get("being"),
                              days_left=(plan or {}).get("days_left"),
                              free_slots=(plan or {}).get("free_slots"),
                              money=FarmWorker.money(obs),
                              suspended=sorted(suspended) or None)
                rep.notes.append(f"工具升级今天没去：{reason}")
            return False
        if self.tool_upgrade_tried >= TOOL_UPGRADE_MAX_PER_DAY:
            return False
        # due 为真时 action 必是 upgrade/pickup（`_tool_upgrade_due` 已保证），这里再兜一层
        if action not in ("upgrade", "pickup"):
            return False
        self.tool_upgrade_tried += 1
        if action == "pickup":
            st = self.worker.pickup_tool()
            self._actions += 1
            self._journal("pickup_tool", ok=st.ok, code=st.code, reason=st.reason,
                          receipt=st.receipt, before=st.before, after=st.after)
            rep.notes.append(("取回工具成功：" if st.ok else "取回工具失败：") + st.reason)
            self._say(("  · " if st.ok else "  × ") + ("取回工具：" + st.reason))
            if st.ok:
                self.farm_actions_today += 1
            return bool(st.ok)
        kind = str(plan.get("kind") or "")
        st = self.worker.upgrade_tool(kind)
        self._actions += 1
        self._journal("upgrade_tool", ok=st.ok, code=st.code, reason=st.reason,
                      receipt=st.receipt, tool=kind, before=st.before, after=st.after,
                      blocked_counts=plan.get("blocked_counts"),
                      note="【task-218 ⑥】选这件工具的依据 = 被工具等级挡住的格子按所需工具分组")
        rep.notes.append(("升级工具成功：" if st.ok else "升级工具失败：") + st.reason)
        self._say(("  · " if st.ok else "  × ") + ("升级工具：" + st.reason))
        if st.ok:
            self.farm_actions_today += 1
        return bool(st.ok)

    def _urgent_farm_work(self, obs: dict[str, Any], suspended: set[str]) -> list[str]:
        """【task-216 F3】窗口里"**现在就能干**"的紧急农活（被在途工具暂停的阶段不算）。

        为什么必须排除 `suspended`：水壶在 Clint 那里升级 ⇒ `water_area` 被暂停 ⇒ 窗口里那些
        "未浇的活苗"**现在根本浇不了**；如果还拿它们当"先干农活"的理由，`pickup` 就永远被挡住
        ⇒ 自死锁（deputy task-206 F3 实测：2 天 `pickup_calls=0`、天天 `stuck`）。
        """
        out: list[str] = []
        tmap = FarmWorker.tiles_of(obs)
        if "water_area" not in suspended:
            unwatered = [t for t, tv in tmap.items()
                         if tv.get("crop") and not tv.get("dead") and not tv.get("watered")]
            if unwatered:
                out.append(f"有 {len(unwatered)} 格作物没浇水")
        ripe = [t for t, tv in tmap.items()
                if tv.get("crop") and not tv.get("dead") and tile_ready(tv)]
        if ripe:
            out.append(f"有 {len(ripe)} 格作物熟了")
        return out

    def _tool_upgrade_due(self, obs: dict[str, Any]) -> bool:
        """【task-205】"现在该不该去铁匠铺"的守卫（真正的执行在 `_maybe_tool_upgrade`）。

        门槛（缺一条都不跑）：

          1. 今天还没试过（`TOOL_UPGRADE_MAX_PER_DAY`）、worker 在；
          2. `_tool_upgrade_plan` 给出了可执行动作（`upgrade`/`pickup`）；
          3. 背包状态读得到（pickup 需要空格、upgrade 的锭也在背包里）；
          4. **紧急农活优先** —— 但**【task-216 F3】只拦 `upgrade`，`pickup` 一律放行**：
             在途工具不在身上，被它暂停的阶段本来就干不成；取回是"把工具拿回来"的救火动作，
             不是收益性跑腿。另：算紧急农活时要**排除被在途工具暂停的阶段**
             （`_urgent_farm_work`），否则"水壶在途 + 未浇苗"会互相锁死。

        注意：`wait`/`need_slot`/`None` 都不算"该去"（`_maybe_tool_upgrade` 里仍会留痕）。
        """
        if self.worker is None or self.tool_upgrade_tried >= TOOL_UPGRADE_MAX_PER_DAY:
            return False
        plan = self._tool_upgrade_plan(obs)
        action = (plan or {}).get("action")
        if action not in ("upgrade", "pickup"):
            return False
        # 背包状态读不到 ⇒ 不冒进（pickup 需要空格、upgrade 的锭也在背包里）
        if player_free_slots(FarmWorker.player_of(obs))[1] != "ok":
            return False
        if action == "pickup":
            return True                          # 【F3】取回一律放行
        return not self._urgent_farm_work(obs, self._tool_suspended_stages(obs))

    def _tool_upgrade_skip_reason(self, obs: dict[str, Any],
                                  plan: dict[str, Any] | None) -> str:
        """【task-216 必修 4】`due=False` 时如实写"今天为什么没去铁匠铺"（每天一条）。"""
        if self.worker is None:
            return "没有 worker"
        if self.tool_upgrade_tried >= TOOL_UPGRADE_MAX_PER_DAY:
            return f"今天已经试过 {self.tool_upgrade_tried} 次（上限 {TOOL_UPGRADE_MAX_PER_DAY}）"
        if plan is None:
            return "没有可做的升级（钱/材料不够，或工具等级读不到，或已满级）"
        action = plan.get("action")
        if action in ("wait", "need_slot"):
            return f"{action}：{plan.get('reason') or '（计划只给了动作、没给原因）'}"
        if player_free_slots(FarmWorker.player_of(obs))[1] != "ok":
            return "读不到背包空格（fail-closed，不冒进）"
        urgent = self._urgent_farm_work(obs, self._tool_suspended_stages(obs))
        if urgent:
            return "先干紧急农活：" + "；".join(urgent)
        return "未知原因（due=False 但复盘没归类，请查账）"

    def _snap_or(self, obs: dict[str, Any]) -> dict[str, Any]:
        """重新取快照，失败就退回旧观测（腾格后的决策不该因为一次观察失败而崩）。"""
        try:
            fresh = self._snap()
        except Exception:
            return obs
        return fresh or obs

    def _preconditions(self, obs: dict[str, Any], rep: DayReport) -> dict[str, Any]:
        """把"种子/钱/背包空格"在本轮动手之前摆正，并返回**改动之后的观测**。
        【task-143】为什么必须返回观测：这个函数会**真的买种子**（`buy`）。调用方
        `_run_day` 原先继续拿**买入之前**的快照去 `_ensure_plot`/`decide`/`_verify_intents`，
        于是刚到手的那 10 粒种子在校验关口看不见 —— 配上 task-143 的
        "`plant_area` 分配额 ≤ 手上种子数"上限，`_stage_tiles("plant_area")` 被算成 0 格
        ⇒ `intent_verdict cancel`（「看得见却没有一格可动目标」）⇒ `plant_area` 当天被封
        ⇒ `plot_exhausted` ⇒ 以 `stuck:` 收场（`TestTask32PlotsCap` 从"1 天做完"退化成
        "3 天"的那个回归）。旧口径之所以没露馅，是因为 `can_plant`（钱够）时它照样返回
        空地池 —— 那是错的，只是看起来"有目标"。

        判据是**"校验用的观测必须看得到刚发生的变化"**，不是猜：只有 `_preconditions_apply`
        报告"真动过世界"（`buy`/`sell` 成功）才重新取快照，没动过就把原快照原样还回去。
        """
        if self._preconditions_apply(obs, rep):
            try:
                fresh = self._snap()
            except Exception:                       # 重新取快照失败绝不让本轮崩掉
                return obs
            if fresh:
                return fresh
        return obs

    def _preconditions_apply(self, obs: dict[str, Any], rep: DayReport) -> bool:
        """种子没了就买**当季能买到的**种子。买不成如实记账，不让后面每一格去撞同一堵墙。

        返回值 = **有没有真的改动世界**（买/卖成功）—— 调用方据此决定要不要重取快照。

        【task-67】选品顺序（每一层都比上一层信息新）：

        1. **今天已确认买不到**（`self.seed_dead_today`）⇒ 直接返回，不再发请求
           （run6 一天白发 6 次 `item_not_sold`，每次都白烧一次过场与时间）；
        2. 手上有货架清单（`self.shop_offers`，来自最近一次回执，**跨天保留**）⇒ 直接挑；
        3. 没有清单 ⇒ 用配置的 `buy_item` **探一次**（旧 Mod 没有清单字段时的唯一办法）；
        4. 探测带回清单 ⇒ 按清单**重挑一次**（换一个 id）；仍不成 ⇒ 置 `seed_dead_today`。
        """
        changed = False
        player = FarmWorker.player_of(obs)
        seeds_total = sum(n for _i, _nm, n in seed_items(player))
        # 【task-240】早退判据从"背包有没有种子"改成"有没有**当季可种**的种子"：
        # 冬天拿着 Wheat Seeds×10（`plantableNow=false`）时若按老口径早退，就会整天
        # "有种子却不种/也不买"；而这时**该买**（商店货架是按季节出的）。
        # 旧 Mod（没有 `player.seeds[]`）⇒ `plantable` 退回总堆叠 ⇒ 行为不变。
        season_state = self._seed_season_state(obs)
        plantable = int(season_state["plantable"]) if season_state["metadata"] else seeds_total
        if plantable > 0:
            return False
        # 【task-241】季节感知：冬季 Pierre 不卖种子 ⇒ 今天**不发起任何 buy**，直接记
        # `seed_dead_today = "winter_no_seeds"`（诚实信号，支持 Goal-1 经济闭环证据）。
        # 不探、不买，避免 run6 那种"白撞 item_not_sold"污染账本；也不是任务失败。
        season = str(season_state.get("season") or "").strip().lower()
        if season == "winter":
            self.seed_dead_today = "winter_no_seeds"
            if not self.seed_dead_noted:
                self.seed_dead_noted = True
                self._journal("winter_no_seeds", season="winter",
                              note="冬季 Pierre 货架无种子 ⇒ 今天不买（无 item_not_sold 试探）；不是任务失败")
                rep.notes.append("冬季不买种子（Pierre 货架无当季种子，避免 item_not_sold 空转）；不是任务失败")
            return changed
        assert self.worker is not None
        money = FarmWorker.money(obs)
        # 【task-102】空格死锁（run8 day 12/13 的主因）：钱够、没种子，但背包**放不下**买来的种子
        # ⇒ `buy` 只会回 `no_inventory_space`（当天 26 次、成交 0，还白开 23 个 `ShopMenu`）。
        # 先卖一叠盈余材料腾格；这是独立于"凑钱"的第二条卖货门闸（见 `surplus_sell_plan`）。
        free_slots, fs_status = player_free_slots(player)
        # 【task-16 / 0.7.45】买种子前**先腾格**（卡面硬要求）：背包真满时 buy 必然
        # `no_inventory_space`（run8 一天白撞 25 次、白开 23 个 ShopMenu）。这里不分
        # "手上有没有（当季不可种的）种子"——冬天握着 Wheat Seeds×10 买不进来时同样会卡。
        # 腾格走既有白名单（保留线/建造预留/qid 下限；卖由 `worker.sell` 走游戏入口，
        # **绝不自己加钱**）；腾不出来就**今天不买**并留痕——不是任务失败，是背包没格。
        if fs_status == "ok" and int(free_slots) < 1:
            if (seeds_total == 0 and money >= self.seed_price
                    and not self.slot_sold_today):
                if self._sell_surplus_for_slot(obs, rep):
                    changed = True
                    obs = self._snap_or(obs)
                    player = FarmWorker.player_of(obs)
                    money = FarmWorker.money(obs)
                    free_slots, fs_status = player_free_slots(player)
            try:
                sold_space = self._sell_surplus_for_space(obs, rep, max_stacks=1)
            except Exception:                    # 腾格失败不打断买种子的主流程（下面如实跳过）
                sold_space = []
            if sold_space:
                changed = True
                obs = self._snap_or(obs)
                player = FarmWorker.player_of(obs)
                money = FarmWorker.money(obs)
                free_slots, fs_status = player_free_slots(player)
            if fs_status == "ok" and int(free_slots) < 1:
                if not self.buy_full_noted:
                    self.buy_full_noted = True
                    money_now = int(FarmWorker.money(obs))
                    rows_now = len(FarmWorker.player_of(obs).get("inventory") or [])
                    self._journal("slot_relief", need=0, freed=0, shipped=False,
                                  freeSlots_before=0, freeSlots_after=0,
                                  before_free=0, after_free=0, trigger="none", sold=[],
                                  stacks_today=int(self.slot_relief_stacks_today),
                                  max_stacks=SLOT_RELIEF_MAX_STACKS_TOTAL,
                                  money_before=money_now, money_after=money_now,
                                  rows_before=rows_now, rows_after=rows_now,
                                  failed=False, blocked_reason="", round=self.slot_relief_today,
                                  max_rounds=SLOT_RELIEF_MAX, reserve=SLOT_RESERVE, demand=0,
                                  demand_basis="buy_full", target_free=1, reached=False,
                                  pressure=True,
                                  note="买种子前背包满且腾不出格子 ⇒ **不买**（避免撞 "
                                       "no_inventory_space 白开 ShopMenu）；不是任务失败")
                    rep.notes.append("买种子前背包满且腾不出格子 ⇒ 今天不买（避免 "
                                     "no_inventory_space 空转；不是任务失败）")
                return changed
        # 【task-55】钱不够买种子时，先把"超出保留线的盈余材料"换成钱（钱要等下一次 NewDay
        # 才到账）—— 这是 run7 缺的那条腿：脑从没自己挣过钱、也没自己买过种子。
        # 门闸与"卖哪几叠"都由 `farmwork.surplus_sell_plan()` 判（每 id 留 K 件、只卖整叠）。
        if self._sell_surplus_for_seeds(obs, rep):
            changed = True
        if not self.allow_buy:
            rep.notes.append("没种子（本轮禁止买种子）")
            return changed
        if self.buy_no_space_today:
            # 今天已经撞过"背包没空格"：再买还是同一堵墙（run8 一天撞 13 次）。
            if not self.buy_no_space_noted:
                self.buy_no_space_noted = True
                rep.notes.append("今天背包没有空格、种子买不进来（no_inventory_space）⇒ 当天不再试 buy；"
                                 "腾格要等同一天卖出/次日结算（见 buy_no_space / surplus_sell journal）")
            return changed
        if self.buy_attempts_today >= MAX_BUY_TRIES_PER_DAY:
            rep.notes.append(f"今天已经发过 {self.buy_attempts_today} 次 buy（上限 "
                             f"{MAX_BUY_TRIES_PER_DAY}）⇒ 不再试")
            return changed
        if self.seed_dead_today:
            if not self.seed_dead_noted:
                self.seed_dead_noted = True
                rep.notes.append(f"今天已确认买不到合适种子（{self.seed_dead_today}），不再试")
            return changed
        # 【task-102】买之前先把残留菜单关掉（run8：前一次 `buy` 留下的 `ShopMenu` 会让
        # 下一次技能被 `ui_modal` 拒掉、也会挡住 `goto_farm`），并顺手刷新观测。
        obs = self._dismiss_stray_menu(obs, rep, where="before_buy")
        player = FarmWorker.player_of(obs)
        money = FarmWorker.money(obs)
        if self.shop_offers:
            # 【task-241】跨季货架失效：上一季留下的 `shop_offers` 可能含隔季种子
            # （例如春末买的 Parsnip 清单在夏初还被当成可买 ⇒ item_not_sold）。
            # 捕获季节与当前不符就丢弃，强制走"探一次拿当季新鲜货架"。
            if self.shop_offers_season and self.shop_offers_season != season:
                self.shop_offers = []
                self.shop_offers_season = ""
        if self.shop_offers:
            # 有清单：直接挑，**不发注定失败的请求**（清单跨天保留）。
            pick, code = pick_seed_offer(self.shop_offers, money)
            if pick is None:
                self._seed_dead(code, rep, money=money, offers=self.shop_offers)
                return changed
            st = self._buy_seed(str(pick.get("id") or ""), money, "shelf", rep,
                                price=int(pick.get("price") or 0), season=season)
            return changed or bool(st is not None and st.ok)
        # 没有清单（旧 Mod / 首次）：拿配置项探**一次**。
        # ⚠️ 探测**成功**时绝不能下"买不到"的结论 —— 上面那次 `no_seed_for_sale` 的误判
        # （探到了种子还说商店没有）会把 `seed_dead_today` 置上，当天后半程直接瘫掉。
        price_shelf = self._seed_price_shelf()      # 【task-123】货架实际价（0 = 拿不到清单）
        price_now = price_shelf or int(self.seed_price)
        if money < price_now:
            # 【task-55·留痕】"是没钱，不是任务失败"必须能在账本里一眼看出来
            # （run7：`buy` 0 条、`seed_gate {seeds:0, money:14}` 5 次，账本侧看不出因果）。
            # 【task-123】"没钱"按**当下这个价**判（货架价优先）；`price_shelf`/`price_cfg`
            # 两个值都进 journal，免得日后对账分不清用的是谁的价格。
            short = int(price_now) - int(money)
            if not self.cannot_afford_noted:
                self.cannot_afford_noted = True
                self._journal("cannot_afford", money=int(money), seed_price=int(self.seed_price),
                              price_shelf=int(price_shelf), price_cfg=int(self.seed_price),
                              short=short, count=self.buy_count, shop=self.shop,
                              note="钱不够买当季种子（连一个都买不起）⇒ 今天不走 buy；"
                                   "这不是任务失败，是账上没钱（先卖盈余材料，钱要等下一次 NewDay）")
                self._say(f"  · 没种子且钱不够（{money}g < {price_now}g，差 {short}g）"
                          "⇒ 今天不买（没钱，不是失败）")
            rep.notes.append(f"没种子且钱不够（{money}g < {price_now}g，差 {short}g），"
                             "只能干等/清障开垦")
            return changed
        st = self._buy_seed(season_probe_item(season, self.buy_item), money, "probe", rep,
                            season=season)
        if st is not None and st.ok:
            return True
        # 【task-102】`no_space` 是"背包放不下"，跟"这个 id 不在售"无关 ⇒ 换 id 也白搭，
        # 当天到此为止（run8 一天 13 次就是这么白撞出来的）。
        if st is not None and st.code == "no_space":
            return changed
        # 探测失败：若回执带了货架清单，就照它重挑一次（换 id）；仍不成才下结论。
        pick, code = pick_seed_offer(self.shop_offers, money)
        if pick is not None:
            st2 = self._buy_seed(str(pick.get("id") or ""), money, "shelf", rep,
                                 price=int(pick.get("price") or 0), season=season)
            return changed or bool(st2 is not None and st2.ok)
        self._seed_dead(code, rep, money=money, offers=self.shop_offers)
        return changed

    def _buy_seed(self, item: str, money: int, source: str, rep: DayReport,
                  *, price: int = 0, season: str = "") -> StepResult | None:
        """发一次 `buy`；把回执里的货架清单收进 `self.shop_offers`，并如实记 `buy` journal。

        【task-102】计数与"空格"分流：每次调用都记 `buy_attempts_today`（上界
        `MAX_BUY_TRIES_PER_DAY`）；回执是 `no_space`（`no_inventory_space`）时置
        `buy_no_space_today` 并记 `buy_no_space` —— 当天不再重试，守卫也不许再拿
        "没种子但钱够 ⇒ 该去买"当理由（run8 day 12/13 就是在这条上撞了 26 次）。

        【task-123】下单数量**量力而行**：`n = min(buy_count, money // price)`，价格用
        **货架实际价**（`price`）优先、拿不到才退回 `--seed-price`（两个值都进 journal：
        `price_shelf`/`price_cfg`）。`n >= 1` 就买 —— `n < buy_count` 时另记
        `buy_partial`，**不是失败**、不进 `failed`；`n == 0` 连一个都买不起 ⇒ 记
        `cannot_afford` 且**一个请求都不发**（run9 t=84.69 的 88g 就是这么被旧判据
        按"买满 10 个"判没钱的，而当天其实够买 8 个 Wheat Seeds）。
        """
        assert self.worker is not None
        if not item:
            return None
        if self.buy_attempts_today >= MAX_BUY_TRIES_PER_DAY:
            # 【task-102】上界要在**发请求之前**判：一次 `_preconditions` 里"探一次 + 照清单
            # 换 id 再买一次"是两次请求，只靠调用方入口判会让当天总量漂到 4 次。
            return None
        price_shelf = int(price or 0)
        price_cfg = int(self.seed_price)
        price_used = price_shelf if price_shelf > 0 else price_cfg
        want = int(self.buy_count)
        n = buy_count_for(price_used, money, want)
        if n < 1:
            # 连一个都买不起：不浪费请求，交给 `_seed_dead` 记 `cannot_afford`（带两个价格）。
            self._seed_dead("cannot_afford", rep, money=money, offers=self.shop_offers)
            return None
        self.buy_attempts_today += 1
        st = self.worker.buy(item, n, shop=self.shop)
        self._actions += 1
        if st.available:
            self.shop_offers = list(st.available)   # 跨天保留：下次直接挑，不发注定失败的请求
            # 【task-241】记下这份清单是哪个季节捕获的（跨季时据此失效，见 `_preconditions_apply`）。
            self.shop_offers_season = str(season or "")
        rep.notes.append(f"补种子（{source} {n} 个 @ {price_used}g）：{st.reason}")
        self._say(f"  · 补种子：{st.reason}")
        self._journal("buy", ok=st.ok, code=st.code, reason=st.reason, item=item,
                      count=n, wanted=want, price=price_used, price_shelf=price_shelf,
                      price_cfg=price_cfg, source=source,
                      attempt=self.buy_attempts_today, limit=MAX_BUY_TRIES_PER_DAY,
                      before=st.before, after=st.after, receipt=st.receipt,
                      available=len(st.available))
        if st.ok and n < want:
            # 【task-123】钱只够买一部分 ⇒ 如实留痕，但**不是失败**：当天照常去种/浇，
            # 缺的种子等 NewDay 把钱结算到账后再补（`cannot_afford` 只留给"一个都买不起"）。
            self._journal("buy_partial", item=item, bought=n, wanted=want, price=price_used,
                          price_shelf=price_shelf, price_cfg=price_cfg, money=int(money),
                          source=source, ok=st.ok, code=st.code,
                          note=f"钱只够买 {n} 个（想买 {want} 个，单价 {price_used}g）⇒ "
                               "量力而行，这不是失败；缺的种子明天钱结算后再补")
            rep.notes.append(f"钱只够买 {n}/{want} 个种子（单价 {price_used}g）⇒ 先买这些")
        if st.code == "no_space":
            self.buy_no_space_today = True
            # 【task-114 NIT-1】把**当次观测真值**记下来：教训的 `evidence` 直接引用它，
            # 不许再写死"空格=0 且 seeds=0"（deputy Z10 里真实 `free_slots=8`，
            # 写死的串会让账本自相矛盾、也没法解释到底卡在哪）。
            facts_obs = self._snap()
            facts_player = FarmWorker.player_of(facts_obs)
            free_now, fs_status = player_free_slots(facts_player)
            seeds_now = sum(n for _i, _nm, n in seed_items(facts_player))
            self.buy_no_space_facts = {
                "free_slots": int(free_now),
                "free_slots_status": fs_status,
                "seeds": int(seeds_now),
                "money": int(FarmWorker.money(facts_obs)),
                "item": item,
                "price": int(price),
            }
            self._journal("buy_no_space", item=item, price=price, source=source,
                          attempt=self.buy_attempts_today, free_slots_status=fs_status,
                          free_slots=int(free_now), seeds=int(seeds_now),
                          reason=st.reason,
                          note="背包没有空格 ⇒ 当天不再重试 buy（run8 一天 13 次同堵墙）；"
                               "腾格路径见 `surplus_sell{why=need_slot}`，或等次日结算后背包腾出来")
            if not self.buy_no_space_noted:
                self.buy_no_space_noted = True
                rep.notes.append(f"背包没空格，种子买不进来（{item} {price}g）⇒ 当天不再试 buy")
        return st

    def _seed_dead(self, code: str, rep: DayReport, *, money: int,
                   offers: list[dict[str, Any]]) -> None:
        """记下"今天买不到合适种子"（`no_seed_for_sale` / `cannot_afford`）。

        为什么必须记：`work_reasons` 里"没种子但钱够 ⇒ 该去买"这条**当天必须失效**，
        否则守卫永远拒绝收工，而商店根本没有当季种子（run6 的死锁）。

        【task-123】`cannot_afford` 必须能自证"按谁的价格判的"：`price_shelf` = 货架上
        最便宜的种子价（拿不到清单就是 0）、`price_cfg` = `--seed-price`；
        `keep_factor` 保留只为老账本对账（task-123 之后它**已不参与判定**）。
        """
        self.seed_dead_today = code or "no_seed_for_sale"
        self.seed_dead_noted = True
        top = "、".join(f"{o.get('name')}({o.get('price')}g)" for o in (offers or [])[:12])
        shelf_prices = [int(o.get("price") or 0) for o in (offers or [])
                        if is_seed_offer(o) and int(o.get("price") or 0) > 0]
        self._journal("no_seed_for_sale" if self.seed_dead_today == "no_seed_for_sale"
                      else "cannot_afford",
                      code=self.seed_dead_today, money=money, seed_price=self.seed_price,
                      price_shelf=(min(shelf_prices) if shelf_prices else 0),
                      price_cfg=int(self.seed_price),
                      keep_factor=SEED_KEEP_FACTOR, offers=top or "(没有货架清单)",
                      note="今天不再发起 buy（次日重试一次）")
        rep.notes.append(f"买不到合适种子（{self.seed_dead_today}）：{top or '没有货架清单'}"
                         "；今天不再试（明天再看）")
        self._say(f"  · 买不到合适种子（{self.seed_dead_today}），今天不再试")

    # ------------------------------------------------------------------ 睡觉
    def _do_sleep(self, obs: dict[str, Any], rep: DayReport, why: str,
                  *, require_work: bool = True) -> tuple[str, str]:
        """睡一觉（被守卫放行时由调用方发起）。

        【task-102】`require_work=True`（默认）时，**今天一次农场动作都没有就不许睡**：
        run8 day 12 是 06:20 起床、当天 0 农场动作（goto_farm 被晨间 `ShippingMenu` 挡掉、
        `water_far` 全 unreachable、`buy` 26 次全废）就睡到 day 13 ⇒ `verified=false`、
        `day_justified=false`，等于用睡觉把一天的活跳过去。返回 `("slept_without_work", why)`
        并**不推进游戏日**（`run()` 会照 `no_day_progress` 如实停下，绝不静默跳天）。

        唯一的例外是 `_stuck_flush`（task-73 的有界翻篇）：它显式传 `require_work=False` ——
        那条路径本日已用有界尝试证明"动不了"，翻篇是它的设计语义。
        """
        assert self.worker is not None
        if require_work and self.farm_actions_today <= 0 and self._unfinished_work(obs):
            rep.slept_without_work = True
            rep.notes.append(f"拒绝睡觉：今天还没有任何农场动作（{why}）⇒ 先干活再谈收工")
            self._journal("slept_without_work", why=why, farm_actions=0,
                          reasons=self.work_reasons(obs)[:6],
                          note="0 农场动作就睡 = 用睡觉跳过整天的活（run8 day 12 形态）；"
                               "本日不推进、按 needs_review 停在这里")
            self._say("  × 今天还没动过农场，拒绝睡觉")
            return "slept_without_work", why
        # 【task-102】睡前先把残留模态关掉一次：run8 day 13 的 `sleep` 就是被 `ShopMenu`
        # 卡成 `sleep_failed`（`ui.isModal` 为真时所有技能都会被 `ui_modal` 拒）。
        # 存档类模态（`SaveGameMenu`/`NewDaySavingMenu`）与 `eventUp` 一律不碰（task-11/task-41）。
        # 【task-59】真正收工前先做一次独立复盘（禁坐标、只落 journal 与次日简报）；
        # 放在 `rep.final` 定稿之前也无妨 —— 它不碰任何判定字段（只追加 `rep.notes` 一句）。
        self._review_before_sleep(obs, rep)
        fresh = self._dismiss_stray_menu(obs, rep, where="before_sleep")
        if fresh is not obs:
            obs = fresh
        rep.final = self._essence(obs)          # ← 睡前观测：一天的验收就拿它当差分右端
        st = self.worker.sleep(home=self.home)
        self._actions += 1
        # 【task-8 D】receipt 必须进 journal：sleep 的失败原因全在 Mod 回执原文里
        # （`sleep_no_question` 带 lastQuestionKey/isInBed/activeMenu 诊断，`timeout` 带
        # newDaySync 现场）。旧实现只记 reason ⇒ run2 的 journal 里只剩一句"睡觉请求失败"。
        self._journal("sleep", ok=st.ok, code=st.code, reason=st.reason,
                      before=st.before, after=st.after, receipt=st.receipt)
        if st.ok:
            # 【task-6 / 0.7.44】"真的睡成功了"是观测真相，单独记在 `rep.slept_ok`：
            # `ended_by` 可能被 stuck 等收尾口径占用，不能拿它反推睡眠（A8 冬 9/14 的误报）。
            rep.slept_ok = True
            self._say(f"  · 睡觉：{st.reason}（{why}）")
            rep.notes.append(f"主动睡觉：{why}；{st.reason}")
            return "sleep", why
        rep.notes.append(f"睡觉失败：{st.reason}（{why}）")
        return "sleep_failed", st.reason

    @staticmethod
    def _slept_by_us(rep: DayReport) -> bool:
        """【task-6 / 0.7.44】今天是否**由我们真的睡成功**（观测真相，不靠 `ended_by` 反推）。

        A8 冬 9/14：`ended_by=stuck`（idle 路径 + `_stuck_flush` 有界翻篇）确实睡过去了、
        `sleep.ok=true`、`day_after` +1；旧口径只看 `ended_by in (sleep, inventory_blocked)`
        ⇒ `checks.slept_by_us=false`（收工路径 checks 快照滞后）。新口径 = `rep.slept_ok`
        （`_do_sleep` 里 `st.ok` 置真）**或** ended_by 是正常收工形态。
        注意：它只描述"有没有睡成功"，**不改变** `day_justified`/`verified`（stuck 日仍不达标）。
        """
        return bool(rep.slept_ok or rep.ended_by in ("sleep", "inventory_blocked"))

    def _stuck_flush(self, obs: dict[str, Any], rep: DayReport, why: str) -> bool:
        """【task-73】stuck 日**有界翻篇**：睡过去一天，让整轮继续，而不是 19 秒终止。

        run6（0.7.25）两个 `day_end` 都是 `ended_by=stuck`，随后 `run()` 命中
        `prev_key == self._last_day_key` ⇒ 写 `no_day_progress` 并 **break 整轮**：游戏日根本
        没往前走（没睡），一次"撞上一片走不到的簇"就让无人值守在 **19 秒**内结束，连"明天再试"
        的机会都没有（run6 verdict 里的「跨日没有推进 ×1」）。

        这里**刻意绕过 `sleep_guard`**：守卫此刻仍会说"有活"（`farm.dryCrops`、跨片地遗留…），
        但我们刚刚已经用**有界**的尝试（阶段重试 / 开路 / `frontier_clear` / 每格配额）证明今天
        动不了 —— 原地再试只会重复写同一条 journal。绕过的理由写进 journal `stuck_flush.note`。

        **绝不放宽验收**：本日 `ended_by` 保持 `stuck`、`checks.day_justified=False`、
        `verified=False`；绝不许把 `stuck` 洗成 `no_work`/`night`/`stamina`。

        返回 True = 睡成了（游戏日已前进，外层循环继续跑下一天）；False = 维持现状（外层照旧
        `no_day_progress` 终止）。`eventUp` / 存档类模态期间**绝不**翻篇（task-41 / task-11 不回归）。
        """
        ui = obs.get("ui") or {}
        if ui.get("eventUp"):
            self._journal("stuck_flush_skipped", reason="eventUp=true",
                          note="task-41：游戏事件挂住必须人来处理，绝不用睡觉把它糊过去")
            return False
        menu = str(ui.get("activeMenu") or "")
        if menu in MODAL_WAIT_ONLY:
            self._journal("stuck_flush_skipped", reason=f"activeMenu={menu}",
                          note="task-11：存档类模态只等不关，翻篇会打断存档")
            return False
        if self.stuck_flushes >= MAX_STUCK_FLUSH:
            self._journal("stuck_flush_skipped", count=self.stuck_flushes, limit=MAX_STUCK_FLUSH,
                          note="翻篇次数已达整轮上限，维持现状（本日如实算 stuck，运行终止）")
            return False
        self.stuck_flushes += 1
        why_txt = why or "守卫没有再给理由"
        by, detail = self._do_sleep(obs, rep, f"stuck_flush:{why_txt}", require_work=False)
        ok = by == "sleep"
        if ok:
            # 睡成功后重新观测一次（`rep.final` 是**睡前**证据，跨日必须靠观测）：
            # 顺手把 `day_after` 落进账本，`stuck_flush` 的 journal 才能带上目标字段。
            rep.stuck_flushed = True
            try:
                fresh = self._snap()
                rep.day_after = [int(v) if str(v).isdigit() else str(v)
                                 for v in FarmWorker.day_key(fresh)]
            except BridgeError as exc:  # pragma: no cover - 仅诊断
                self._journal("stuck_flush_resnap_failed", error=str(exc))
            rep.notes.append(
                f"stuck 日翻篇：已睡过这一天（第 {self.stuck_flushes}/{MAX_STUCK_FLUSH} 次），"
                "下一轮继续跑新的一天；本日仍如实记 stuck、day_justified=False、不 VERIFIED")
        else:
            rep.notes.append("stuck 日翻篇失败（睡不过去）⇒ 维持现状终止")
        self._journal("stuck_flush", ok=ok, count=self.stuck_flushes, limit=MAX_STUCK_FLUSH,
                      day_after=list(rep.day_after) if rep.day_after else None,
                      detail=str(detail)[:200],
                      note=("守卫仍说「有活」，但本日已用有界尝试（阶段重试/开路/frontier_clear/每格"
                            "配额）证明动不了 ⇒ 刻意绕过 sleep_guard 睡过去，让整轮继续跑下一天；"
                            "本日仍如实计 stuck、day_justified=False、绝不 VERIFIED。"))
        return ok

    # ------------------------------------------------------------------ 执行
    def _run_stage_intent(self, intent: TaskIntent, obs: dict[str, Any], plot: dict[str, Any],
                          rep: DayReport) -> bool:
        """执行一个阶段意图：发动作 → 差分复核 → 记账。返回"今天有没有真的推进"。"""
        task = intent.task
        outcome = self._step_stage(task, obs, plot, rep)
        rep.outcomes.append(outcome.as_dict())
        # 【task-219】阶段意图的执行对账直接从刚写下的阶段账本取（唯一数据源）。
        self._record_stage_intent(intent, rep)
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
                # 【task-170】"熟了"用**游戏口径** `tile_ready`（不是裸 `ripe`）：复收冷却
                # 的格不算可动作状态，否则"挥了没变"会被误判成世界没动。
                out[t] = (v.get("kind"), v.get("crop"), v.get("watered"), tile_ready(v),
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
        refused_marked = 0
        encircled_marked = 0
        tool_blocked_marked = 0
        for s in steps:
            if not s.tile:
                continue
            if not s.unreachable and not s.encircled and not s.blocked_by_tool:
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
            if s.refused:
                # 【task-63】被**游戏拒绝**（`tool_ineffective`/`precondition_failed`）：世界给的
                # 前置事实（不可锄的地 / 工具等级不够），不是"我试了没做成" ⇒ 当天封格（次日自动
                # 重试），逐格 journal `tool_refused` 带 `status`/`kind` 供工具交叉核对；日级豁免
                # 另有 `refused_bound` 上界（超界照实 `no_hard_failures=false`）。
                # 与 `unreachable`（task-52）**分开累计**，两套豁免互不覆盖。
                self.blocked[key] = f"{s.action} 被游戏拒绝：{s.reason[:80]}"
                self.refused_day.add(key)
                refused_marked += 1
                self._journal("tool_refused", tile=list(key), action=s.action, stage=stage,
                              zone=self.zone_name, status=s.status,
                              kind=str((s.after or {}).get("kind") or "未知"),
                              reason=s.reason[:200])
                continue
            if s.blocked_by_tool:
                # 【task-20】工具等级/种类不够（或观测判不了）⇒ **一次都没挥**、不白烧体力。
                # 与 `refused` 的区别：`refused` 是"挥了、游戏拒绝"（真花了体力才拿到结论），
                # 这里是"**动手之前**观测就说不该挥"（`clumpTarget`/`toolOk` 判据）。
                # 当天封格（次日自动重试：工具可能升完级）、逐格 journal 留 `need`/`min_level`；
                # **不进** unreachable/refused 两套豁免（它不是世界约束、也不是硬失败），
                # 且**不产生任何"还有活"的守卫理由**（否则一块敲不动的巨石会让人永远收不了工）。
                self.blocked[key] = f"{s.action} 工具不够格：{s.reason[:80]}"
                tool_blocked_marked += 1
                need_tool = str(getattr(s, "tool_need", "") or "")
                # 【task-218 ⑤】`clump_blocked_backlog`：每格每天一条**可升级跟进**的账
                # （带 `tile/tool/minLevel/currentLevel`），供升级选型与次日复核；
                # 只作证据，不进硬失败、不进任何豁免、不产生守卫理由。
                # ⚠️ 刻意**不新增事件名**：语义折进既有 `blocked_by_tool` 的 `backlog: true`
                # + `current_level` 字段（新增事件名会让 analyzer 的机械枚举漂移、全量变红；
                # task-218 验收要求 0 红）。要独立事件名得先走 Lead 的 analyzer 卡。
                try:
                    current_level = tool_tier(obs, need_tool) if need_tool else -1
                except Exception:      # pragma: no cover - 观测异常时不猜
                    current_level = -1
                self._journal("blocked_by_tool", tile=list(key), action=s.action, stage=stage,
                              zone=self.zone_name, backlog=True,
                              kind=str(((FarmWorker.tiles_of(after_obs) or {}).get(key)
                                        or (FarmWorker.tiles_of(before_obs) or {}).get(key)
                                        or {}).get("kind") or "未知"),
                              need=need_tool,
                              min_level=getattr(s, "tool_min_level", None),
                              current_level=(current_level if current_level >= 0 else None),
                              reason=s.reason[:200],
                              note="工具等级/种类不够（或观测判不出）⇒ 今天不再挥这格："
                                   "0 次 use_tool、不算硬失败、不进 unreachable/refused 豁免；"
                                   "次日自动重试（工具可能已升级）")
                continue
            if s.encircled:
                # 【task-68】被围住（四邻没有"可清 + 自己够得着"的突破口）。
                # 【task-78 NIT-2】逐格 journal 照实带 `kinds`（四邻真实 kind，从 reason 里读不到就
                # 写 `None` —— 不许替观测断言"树/桩/大石"）与 `tried_open`（真试了几次开路）。
                # 与"走不到"**分开**：这些格不是物理上不可达，而是"现在还开不了路" ——
                # ① **不写 `self.blocked`**（不封格：今天开路/明天地形变了就可能可达）；
                # ② **不进 `unreachable_day`**（`checks.unreachable_within_bound` 只数真不可达，
                #    否则"一圈树围着"会污染不可达上界 —— run6 的 42 格假红就有这个成分）；
                # ③ 逐格 journal `encircled`，日级另有 `encircled` 账本与 `encircled_stage`。
                self.encircled_day.add(key)
                encircled_marked += 1
                self._journal("encircled", tile=list(key), action=s.action, stage=stage,
                              zone=self.zone_name, reason=s.reason[:200],
                              kinds=list(getattr(s, "encircled_kinds", []) or []),
                              tried_open=int(getattr(s, "tried_open", 0) or 0),
                              note="四邻没有「可清障 + 自己够得着」的突破口 ⇒ 不算「走不到」、"
                                   "不封格；进 encircled 单独计数，不进 unreachable 豁免"
                                   "（真实四邻 kind 与开路尝试次数见本事件 kinds/tried_open）")
                continue
            if before.get(key) != after.get(key):
                continue
            self.blocked[key] = f"{s.action} 无效：{s.reason[:80]}"
            marked += 1
            # 【task-241】树/石/枝的"干不动"必须有**有界连续调用**证据（单发
            # tool_ineffective 曾把 0.7.41 冒烟的 9 格全封死）；证据从 StepResult.after 带过来。
            bound = None
            if isinstance(s.after, dict):
                bound = s.after.get("tool_ineffective_bound")
            extra: dict[str, Any] = {}
            if isinstance(bound, dict) and bound:
                extra = {"tool_ineffective_bound": bound}
            self._journal("blocked", tile=list(key), action=s.action,
                          no_effect=bool(s.failed), reason=s.reason[:160],
                          **extra)
        if marked:
            rep.notes.append(
                f"记下 {marked} 格「动了没用」的地，今天不再碰（共 {len(self.blocked)} 格）")
        if unreach_marked:
            rep.notes.append(
                f"记下 {unreach_marked} 格「走不到」的地，今天不再白试（次日重试；不算硬失败）")
        if refused_marked:
            rep.notes.append(
                f"记下 {refused_marked} 格「游戏拒绝」的地，今天不再白试（次日重试；不算硬失败，"
                f"但有界）")
        if tool_blocked_marked:
            rep.notes.append(
                f"记下 {tool_blocked_marked} 格「工具不够格」的地，今天不再挥"
                f"（0 次 use_tool、不算硬失败；次日重试）")

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
            if getattr(s, "no_slot", False):
                # 【task-198】背包满 = **全局**阻塞（不是这一格的属性，也不是"没拿到结论"）：
                # 既不占每格配额、也不进 `env_streak`（同一格连续 no_slot 本来就不该被限流）。
                # 它由日级腾格收敛回路 `_slot_relief()` 界住（每天有界轮数，腾不出 ⇒
                # 如实 `inventory_blocked` 收尾）—— 在这里再叠一层每格限流只会把它误判成
                # `capped`（run A′ 的 59 次 `harvest_gave_up` 就是这么来的）。
                continue
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

    #: 【task-170 ②】收获同格上限的留痕（一天一次一格）。
    def _note_harvest_gave_up(self, steps: list[StepResult], rep: DayReport) -> None:
        """摘不下来的熟作物：试满 `MAX_TILE_ATTEMPTS` 就当天放弃（守卫不再被它钉住）。

        为什么必须单独记：run B 里 `(60,29)` 这类格（裸 `ripe=true` 但游戏不给收）让
        `work_reasons`/farm 级熟作物理由一直非空 ⇒ `veto sleep 35`、`recover 13`、整天 0 成功。
        这里把"当天已判过、不再动人"的格子显式列出来，守卫与目标池据此闭嘴，
        **但 `_leftover("harvest")` 不排除它们**（当天确实没收到 ⇒ 如实 unmet、不洗白）。
        """
        for s in steps:
            if not s.tile or s.ok or s.skipped:
                continue
            key = tuple(s.tile)
            if self.tile_attempts.get(key, 0) < MAX_TILE_ATTEMPTS:
                continue
            if key in self.harvest_gave_up:
                continue
            # 【task-198】背包满（`no_slot`）不是"这一格摘不下来"：它连"能不能收"都还没问过，
            # 全局一腾出格子当天就能收 ⇒ **绝不许**把它写进 `harvest_gave_up`（否则一天之后
            # 守卫/目标池都把这格当成"今天放弃了"，而其实只是背包没空格）。
            if any(getattr(x, "no_slot", False) for x in steps
                   if x.tile and tuple(x.tile) == key):
                continue
            self.harvest_gave_up.add(key)
            codes = sorted({str(getattr(s, "code", "") or "") for s in steps
                            if s.tile and tuple(s.tile) == key})
            self._journal("harvest_gave_up", tile=list(key), attempts=self.tile_attempts.get(key, 0),
                          limit=MAX_TILE_ATTEMPTS, codes=codes,
                          note="同一格今天试满上限仍没摘下来 ⇒ 当天不再动人；守卫不再被它钉住"
                               "（`_leftover(\"harvest\")` 仍如实留 unmet）")
            rep.notes.append(f"收获放弃一格 {list(key)}（试满 {MAX_TILE_ATTEMPTS} 次：{codes}）")

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

    @staticmethod
    def _tile_reason(key: tuple[int, int], steps: list[StepResult], *,
                     stopped: str, obs: dict[str, Any]) -> str:
        """【task-219 / task-230 P0-3.2】给"没做成的格"归一个**闭合集**原因码。

        判据**只看观测里已有的东西**（步上的标记 / 步的 `code` / `blocked_by_tool` / 阶格 kind），
        绝不猜：判不出来的写 `unknown_evidence`（它本身是合法码、但会让 gaps 里出现
        "证据不足"，正是要暴露的缺陷形态）。优先级 = 越"具体且可行动"越靠前：

        ① **显式标记**（`no_slot` / `blocked_by_tool` / `unreachable` / `encircled` /
           `env_block` 的模态细分 / `inconclusive`）——这些不是 `code` 能表达的；
        ② **`code` → 原因码**走 `STEP_CODE_TO_REASON`（**唯一映射表**；漏映射由漂移测试抓）；
        ③ 最后才按阶段的 `stopped` 归类（一格请求都没发过的情形）。
        """
        def _has(attr: str) -> bool:
            return any(bool(getattr(s, attr, False)) for s in steps)

        if _has("no_slot"):
            return "no_slot"
        if any(getattr(s, "blocked_by_tool", False) for s in steps):
            return "tool_level"
        if any(getattr(s, "unreachable", False) or getattr(s, "encircled", False)
               for s in steps):
            return "blocked_tile"
        if _has("env_block"):
            statuses = {str(getattr(s, "status", "") or "")
                        for s in steps if getattr(s, "env_block", False)}
            if statuses & {"ui_modal", "no_save"}:
                return "blocked_modal"
            return "world_stuck"
        if _has("inconclusive"):
            return "unknown_evidence"
        if steps and all(getattr(s, "skipped", False) for s in steps):
            tv = (FarmWorker.tiles_of(obs) or {}).get(key) or {}
            kind = str(tv.get("kind") or "")
            if kind in DEFERRED_KINDS:
                return "deferred_capability"
            return "gated"
        # ② 单一数据源映射表（`skipped` 已在上面细化，不在这里抢答）。
        for s in steps:
            code = str(getattr(s, "code", "") or "")
            if code == "skipped":
                continue
            reason = STEP_CODE_TO_REASON.get(code)
            if reason:
                return reason
        # 一格请求都没发过（换片/预算/批量没收尾）：按阶段 stop 原因归类；判不出来如实写
        # `unknown_evidence` —— 那正说明"这一格既没做、也没留下理由"，是要暴露的缺口。
        if stopped == "budget":
            return "budget"
        if stopped in ("no_seed", "no_slot_dead", "gated"):
            return "gated"
        if stopped in ("blocked_modal", "no_slot"):
            return "blocked_modal" if stopped == "blocked_modal" else "no_slot"
        if stopped.startswith("no_route"):
            return "blocked_tile"
        return "unknown_evidence"

    @staticmethod
    def _stage_undone_cause(steps: list[StepResult], undone: list[tuple[int, int]]) -> str:
        """【task-144】把"分配了却没成事"的格子归一类，作为阶段 `stopped` 的**如实**原因。

        返回 `need_refill`（壶空/补水不成）、`unreachable`（寻路走不到）、`no_seed`（没种子/
        播种失败）或兜底的 `incomplete`（原因不单一，比如"下一轮窗口里看不见这些格"）。
        只做归类，不改任何判定：这些原因都**不在**诚实上限白名单里，undone 照旧计入 unmet。
        """
        want = {tuple(t) for t in undone}
        reached = [s for s in steps if s.tile and tuple(s.tile) in want]
        codes = {str(getattr(s, "code", "") or "") for s in reached}
        if "need_refill" in codes:
            return "need_refill"
        if any(getattr(s, "no_slot", False) for s in reached):
            # 【task-198】背包满排在第一位：它是**全局**原因（不是这一格走不到/没种子），
            # 阶段 `stopped` 必须让读者一眼看到"先腾格"，而不是被后面的分类掩盖。
            return "no_slot"
        if any(getattr(s, "unreachable", False) for s in reached):
            return "unreachable"
        if "no_seed" in codes or "sow_failed" in codes:
            return "no_seed"
        return "incomplete"

    def _step_stage(self, task: str, obs: dict[str, Any], plot: dict[str, Any],
                    rep: DayReport) -> TaskOutcome:
        assert self.worker is not None
        all_steps: list[StepResult] = []
        stopped = ""
        attempts = 0
        walked = False
        # 【task-134 B】这一阶段**真的分下去**的格子（跨轮累计）。日级 `no_unmet_stages`
        # 从 task-134 起看它：分到的格做完 ⇒ 不算没做完（哪怕整片地还剩别的格，
        # 那是换片/收尾的事，记 `plot_pending`）。
        assigned: set[tuple[int, int]] = set()
        # **没种子又买不起 ⇒ 今天不碰开垦/播种**（执行层的第三道同口径，见 `_stage_tiles`）。
        # 先在这里说一句人话 + 记 journal，再去跑（跑起来会"一格目标都没有"，但那是空转的表现，
        # 不是原因）。只播报一次，别每轮刷屏。
        if task in ("till_area", "plant_area") and task not in self.seed_gate_noted:
            seeds, money, can_plant = self._seed_outlook(obs)
            # 【task-240】把"当季能不能种"的完整证据写进同一事件（不新增事件名）：
            # 0.7.41 冒烟 day1 的形态是"冬天拿着 Wheat Seeds×10"——`seeds` 现在是
            # **当季可种**数（旧 Mod 缺 `player.seeds[]` 时退回总堆叠），
            # `seeds_total`/`out_of_season`/`seeds_metadata` 用来在账本里区分
            # "真没种子" / "有种子但全隔季" / "旧 Mod 判不了"。
            season_state = self._seed_season_state(obs)
            if not can_plant:
                self.seed_gate_noted.add(task)
                if (season_state["metadata"] and int(season_state["plantable"]) <= 0
                        and season_state["out_of_season"]):
                    names = "、".join(season_state["out_of_season"][:3])
                    note = (f"当季（{season_state['season'] or '?'}）没有可种的种子："
                            f"手上有 {names} 但都隔季（可种 {seeds} 粒、钱 {money}g）"
                            f"⇒ 今天不再开垦/播种：{task} 没有目标")
                else:
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
                              seed_price=self.seed_price, zone=self.zone_name, in_plot=in_plot,
                              season=season_state["season"],
                              seeds_metadata=season_state["metadata"],
                              seeds_total=season_state["seeds_total"],
                              plantable=season_state["plantable"],
                              out_of_season=season_state["out_of_season"])
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
        # 【task-144】只有"补水后原样重跑"这一种 `forced` 需要在重跑完成后继续正常循环
        # （把窗口里剩下的目标也做完）；环境挡路的 `forced` 不做这件事（那会白跑更多轮）。
        refill_resume = False
        # 【task-27 / 0.7.46】本阶段开始时记录前置过滤证据的游标：阶段末尾把本阶段新增的
        # "目标池判死（encircled）"格并进 `encircled` 计数/坐标（逐格证据不吞）。
        prefiltered_before = len(self._prefiltered_encircled_today)
        # 本阶段已经为"壶空"补过几次水（上界 `STAGE_REFILL_MAX`；日级另有 `max_refills_per_day` 兜底）。
        stage_refills = 0
        while True:
            if forced is None:
                attempts += 1
            snap = self._snap()
            # 【task-16 / 0.7.45】每阶段每轮也重算背包空格（trace：阶段前读数）。
            self._observe_free_slots(rep, snap)
            if forced is not None:
                tiles = list(forced)
                forced = None
            else:
                tiles = self._stage_tiles(task, snap, plot)
            for _t in tiles:
                try:
                    assigned.add((int(_t[0]), int(_t[1])))
                except (TypeError, ValueError, IndexError):
                    continue
            # 【task-27 / 0.7.46】被目标池前置过滤判死的格**没有 step**，但它们是这一阶段
            # 真实存在、本该动却没动的格：必须照样留在 `assigned` 里。否则
            # `assigned_undone` / `no_unmet_stages` 会因为"根本没分到"而变绿 ——
            # 挡死格可以不计 `unreachable`、不进豁免分子，但**不许被洗成没活**。
            for _r in self._prefiltered_encircled_today[prefiltered_before:]:
                if str(_r.get("stage") or "") != task:
                    continue
                try:
                    assigned.add((int(_r["tile"][0]), int(_r["tile"][1])))
                except (TypeError, ValueError, IndexError, KeyError):
                    continue
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
            # 【task-102】"今天真的动过农场"的计数：只数**发出去过**的格子动作
            # （`skipped` 是"judged before acting"，不算动作 ⇒ 0 动作的日子不许拿去睡觉）。
            self.farm_actions_today += sum(1 for s in res.steps if s.tile and not s.skipped)
            # 【task-218 ④】砍倒一棵树 = `clear` 成功且该格 kind 从 `tree` 变成别的
            # （Mod 对 `Tree` 一律报 kind="tree"，砍倒成桩仍报 tree ⇒ 只有"离开 tree"才算砍倒）。
            # 日级预算 `_tree_budget_left` 靠这个计数收口（浇水/收获永远优先）。
            trees_now = sum(
                1 for s in res.steps
                if s.ok and s.tile and str(getattr(s, "action", "") or "") == "clear"
                and str((s.before or {}).get("kind") or "") == TREE_KIND
                and str((s.after or {}).get("kind") or "") != TREE_KIND)
            if trees_now:
                self.trees_cleared_today += trees_now
            # **每轮就封格 + 记发起次数**（不是等阶段跑完）：
            # 撞到 `budget` 会 continue 再跑一轮，而 `_stage_tiles` 是每轮现算的 ——
            # 若等到阶段结束才 `_mark_blocked`，同一格注定干不动的格子会在后续每一轮
            # 被重新选中再白试一次（run1 的两格 grass 就是这么被连挥的）。
            self._count_attempts(res.steps)
            self._mark_blocked(snap, self._snap(), res.steps, rep, stage=task)
            # 【task-16 / 0.7.45】这一轮"清成了但背包 0 空格 ⇒ 掉落被游戏拒收"的格子汇总进
            # 日级/阶段留痕（info；不改 ok/failed、不改 checks，不把清障日判成失败）。
            self._note_loot_lost(res.steps, rep, stage=task)
            # 【task-170 ②】收获的同格上限：试满 `MAX_TILE_ATTEMPTS` 仍没摘下来的格子，
            # 当天记进 `harvest_gave_up`（journal 逐格 `harvest_gave_up`），守卫/目标池都不
            # 再被它钉住。`_leftover("harvest")` **刻意不排除**它（那天就是没做成，如实 unmet）。
            if task == "harvest":
                self._note_harvest_gave_up(res.steps, rep)
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
            if res.stopped == "need_refill" and stage_refills < STAGE_REFILL_MAX \
                    and self.refills_today < self.max_refills_per_day:
                stage_refills += 1
                rf = self.worker.refill_can()
                self.refills_today += 1
                self._actions += 1
                rep.notes.append(f"补水：{rf.reason}")
                self._journal("refill", ok=rf.ok, reason=rf.reason, before=rf.before, after=rf.after)
                # 【task-144】壶空**不是"这一格干不动"**：补水成功后必须把"这一轮没成事的
                # 已分配格"原样再跑一遍（`forced`），而不是下一轮重算 `_stage_tiles` ——
                # 重算以玩家为中心重新取窗口，run9c 里那 3 格因此从目标里消失、既没浇上
                # 也不再被重试，`stopped` 还停在 ""（"分配过却没成事"与"自然结束"共存的洞）。
                done_round = {tuple(s.tile) for s in res.steps if s.tile and (s.ok or s.skipped)}
                pending_round = [t for t in tiles if tuple(t) not in done_round]
                self._journal("refill_retry", stage=task, zone=self.zone_name, ok=rf.ok,
                              refills_today=self.refills_today, limit=self.max_refills_per_day,
                              stage_refills=stage_refills, stage_limit=STAGE_REFILL_MAX,
                              tiles=len(pending_round),
                              targets=[list(t) for t in pending_round[:6]],
                              note="壶空 ⇒ 先补水，再把这一轮没成事的格子**原样**重跑（同一批，"
                                   "不重算窗口）；补水不成 ⇒ 保持 stopped=need_refill、undone 计入 unmet")
                if rf.ok:
                    # 补水成功 ⇒ 这一批没成事的格子**原样**重跑；重跑之后照旧继续正常循环
                    # （重算窗口、把这片地剩下的目标也做完），否则阶段会提前收工。
                    forced = pending_round or None
                    refill_resume = True
                    continue
            if res.stopped == "budget" and attempts < self.max_stage_rounds:
                # 撞到"每次只做 N 格"的上限：还有目标就接着跑完（真机 m01770：浇水只做 12 格、
                # 剩下 19 格没浇就天黑了）。
                continue
            if refill_resume and not res.stopped and attempts < self.max_stage_rounds:
                # 【task-144】"原样重跑"完成 ≠ 这一阶段做完：窗口重算一遍继续做（同上）。
                refill_resume = False
                continue
            stopped = res.stopped
            break

        fresh = self._snap()
        # 【task-161】阶段体力实测留痕（**只留痕，不改任何判据/常量/checks**）：
        # `stamina_before` 取阶段开始那张观测（也就是调用方用来算目标的 `obs`）、
        # `stamina_after` 取阶段结束这张 `fresh`；取不到就是 `None`（**不许写 0**，
        # 0 是"真的没体力了"，与"没观测到"是两件事）。`stamina_spent` 允许为负
        # （中间吃过东西/升过级），如实记，不裁剪。
        stamina_before = _stamina_or_none(obs)
        stamina_after = _stamina_or_none(fresh)
        stamina_spent = (round(stamina_before - stamina_after, 1)
                         if stamina_before is not None and stamina_after is not None else None)
        # `_mark_blocked` 已改为**每轮**在循环内调用（见上），这里不再补一次：
        # 循环外的 `obs` 是阶段开始时的快照，用它当"动手前"会把中间几轮的变化算错。
        leftover = self._leftover(task, fresh, plot)
        # 【task-134 B】`assigned_undone` = 分下去的格里**没做成、也没按规跳过**的数量。
        # 按规跳过（`code=skipped`：这格本来就不用干/干不动）不算"没做完"；
        # 走不到/被拒/壶空这些另有两套独立计数与豁免，不在这里重复扣。
        assigned_done = {tuple(s.tile) for s in all_steps if s.tile and (s.ok or s.skipped)}
        assigned_undone = len(assigned - assigned_done)
        # 【task-144】口径洞收口：`stopped==""` 表示"阶段自然走完"，但**分配过却没成事**的格子
        # 不能与它共存（run9c 洞里那 3 格正是这样"没人浇上、也没人负责"）。只要还有 undone，
        # 就补一个**如实的** stop 原因（壶空/够不着/没种子/其它 ⇒ `incomplete`），并留 journal。
        # 注意：夜里收工的诚实上限判定同时接纳 `"incomplete"`（见日终 `honest`），所以
        # 天黑收工不会被这条改名判成"没做完"。
        if not stopped and assigned_undone > 0:
            undone_tiles = sorted(assigned - assigned_done)
            stopped = self._stage_undone_cause(all_steps, undone_tiles)
            self._journal("stage_stop_named", stage=task, zone=self.zone_name, cause=stopped,
                          assigned=len(assigned), assigned_undone=assigned_undone,
                          tiles=[list(t) for t in undone_tiles[:8]],
                          codes=sorted({str(getattr(s, "code", "") or "")
                                        for s in all_steps
                                        if s.tile and tuple(s.tile) in set(undone_tiles)}),
                          note="阶段自然结束却仍有分配未成事的格 ⇒ 补一个如实 stop 原因"
                               "（`stopped=\"\"` 与 `assigned_undone>0` 不再共存）")
        # 【task-5 / 0.7.44】把 leftover 拆成"可执行余格 vs 物理挡死格"（**只作 info**，
        # `leftover` 语义一字不动）。"挡死" = `blocked` ∪ `encircled_day`（见 `_dead_tile_set`）。
        dead_set = self._dead_tile_set()
        leftover_blocked = [t for t in leftover if t in dead_set]
        leftover_exec = [t for t in leftover if t not in dead_set]
        # 【task-5 / 0.7.44】有界保护：同一格当天被**重新分配** N 次仍没有产出 ⇒ 当天不再选它。
        # A8 冬 9/14：[37,35] 被围住后被重分 28/63 次（encircled 步不吃 tile_attempts 配额）。
        # 这里兜底任何"分配了却没产出、又没被挡死集合覆盖"的格子；留痕走既有 `blocked` 事件
        # （不加新事件名，防 analyzer 的机械枚举漂移）。
        alloc_capped_today: list[tuple[int, int]] = []
        for _t in sorted(assigned - assigned_done):
            key = tuple(_t)
            if key in dead_set:
                continue                    # 物理挡死格由 blocked/encircled_day 排除，不进"重分"计数
            steps_here = [s for s in all_steps if s.tile and tuple(s.tile) == key]
            # 环境挡路 / 背包满 / 体力用尽 / 阶段预算收工 = 世界或资源**暂时**不让做，
            # 条件好了还要重试（task-198 腾格后要把熟作物收进来、task-158 体力/预算会重算）
            # ⇒ 不占"重分无产出"额度（否则会把 slot_relief/预算重试的格子误封）。
            if any(s.env_block or getattr(s, "no_slot", False) for s in steps_here):
                continue
            if stopped in ("stamina", "budget"):
                continue
            n = self.alloc_no_progress.get(key, 0) + 1
            self.alloc_no_progress[key] = n
            if n >= MAX_ALLOC_NO_PROGRESS and key not in self.blocked:
                self.blocked[key] = f"当天被重新分配 {n} 次仍无产出"
                alloc_capped_today.append(key)
                self._journal("blocked", tile=list(key), action="stage_realloc",
                              no_effect=False, stage=task, zone=self.zone_name,
                              alloc_no_progress=n, limit=MAX_ALLOC_NO_PROGRESS,
                              reason=(f"同一格当天被重新分配 {n} 次、每次都没有产出"
                                      f"（未做成/未按规跳过）⇒ 今天不再选它（有界保护）"))
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
        # 【task-218 ⑧ 护栏 B / 0.7.39 P0-1 修订】清障有效性**逐格判**：
        # `farm.blockers` 在观测里根本不存在（FarmView 没有 weeds/stones/trees 计数，
        # 那是 task-222 才补的）⇒ 不许把它当主判据。逐个 `ok` 步看该格 kind 是否真的变了：
        # `tree→stump` 记 progress（砍倒成桩不算红）、weed/stone/twig 消失算真 progress。
        # 有 ok 步却**一格都没变**、又没有"判不了"的步 ⇒ 该阶段如实 `incomplete`。
        # farm 级聚合（若将来有）只作 info，**不进判红条件**。
        cleared_tiles: list[tuple[int, int]] = []
        blocker_drop: int | None = None
        unclear_steps = 0
        if task == "clear_area":
            for s in all_steps:
                if not (s.ok and s.tile):
                    continue
                # 【task-242】`code=="already"` 的 ok 步**没有改变过任何一格**：
                # `farmwork.clear()` 在"没有需要清的障碍"分支（farmwork.py:2397-2400）
                # 直接返回，没观测、没站位、没耗体力 ⇒ 它既不是"清掉一格"，也不该被算成
                # "拿不到 kind 证据"（后者会抑制护栏 B）。0.7.42 冒烟 9 个阶段 ok 比
                # cleared_tiles 多 1–3、且 `engaged`/`stamina_spent` 恰好只对应真清掉的格，
                # 就是这些 already 步。单列到 `already`/`already_tiles`，不参与 clear 对账。
                if str(getattr(s, "code", "") or "") == "already":
                    continue
                before_kind = str((s.before or {}).get("kind") or "")
                after_kind = str((s.after or {}).get("kind_after")
                                 or (s.after or {}).get("kind") or "")
                if not before_kind or not after_kind:
                    unclear_steps += 1
                    continue
                if after_kind != before_kind:
                    cleared_tiles.append((int(s.tile[0]), int(s.tile[1])))
            b0 = self._farm_count(obs, "blockers")
            b1 = self._farm_count(fresh, "blockers")
            if b0 is not None and b1 is not None:
                blocker_drop = int(b0) - int(b1)      # 只作 info（没有这个字段就是 None）
            budget_or_tool = (bool(self._budget_defer_reason("clear_area", obs))
                              or not self._tree_budget_left(obs))
            # 【task-242】护栏 B 只看**真的动过**的 ok 步（`already` 没有改变任何格子，
            # 不构成"挥过刀却没变"的声明；它们已单列到 `already`）。
            # 注意：这里必须就地算，不能引用下面才定义的 `oks`（否则 UnboundLocalError）。
            ok_steps = [s for s in all_steps
                        if s.ok and str(getattr(s, "code", "") or "") != "already"]
            if ok_steps and not cleared_tiles and not unclear_steps and not budget_or_tool:
                # 有成功步却一格没变 ⇒ 这个阶段**事实上没做成**：`stopped` 一律改写成
                # `incomplete`（哪怕 runner 报了 `done`/`budget` —— 判据是逐格证据）。
                stopped = "incomplete"
                self._journal("stage_stop_named", stage=task, zone=self.zone_name,
                              cause=stopped, assigned=len(assigned),
                              assigned_undone=assigned_undone, cleared_tiles=0,
                              codes=sorted({str(getattr(s, "code", "") or "") for s in all_steps}),
                              note="【task-218 护栏 B / P0-1】有成功步但没有任何一格的 kind 变化 ⇒ "
                                   "如实 incomplete（「挥过刀」不算清障有效；不依赖观测里不存在的 "
                                   "farm.blockers；不许被 no_work/VERIFIED 洗白）")
        # 【task-198】`no_slot`（背包满）**不是"这一格没做成"**：它是全局阻塞，`farmwork` 侧
        # 已经把它归进 env 桶（`StepResult.env_block`），这里必须同样从硬失败里排除 ——
        # 否则 run A′ 的 45 条同句失败会一路算进 `stage.failed`/`day.failed_steps`/
        # `no_hard_failures`，当天永远不可能 VERIFIED（卡面①的硬要求）。
        failed_any = [s for s in all_steps
                      if s.failed and not getattr(s, "no_slot", False)]
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
                self.leftover_area.pop(tuple(s.tile), None)
        for t in leftover:
            tt = tuple(t)
            if tt in self.blocked:
                continue                    # 判据证明这一格今天干不动 ⇒ 不算"还有活"
            self.leftover_targets.add(tt)
            # 【task-4 / 0.7.44】记账时把坐标归到**账本片区**（fields 田区 / 8×8 空间簇）：
            # 换片只从这份归属里挑"另一片"，坐标本身仍来自 leftover（绝不臆造）。
            if tt not in self.leftover_area:
                self.leftover_area[tt] = self._tile_area(fresh, tt)
        skipped = [s for s in all_steps if s.skipped]
        ok_all = [s for s in all_steps if s.ok]
        # 【task-242】清障阶段的 `ok` 只数**真的改变了格子**的成功步：`code=="already"`
        # （本来就没障碍 / 已被本次开路连带清掉）单列 `already`，不算 ok。
        # 这样 `len(cleared_tiles) == ok` 才有可能成立（0.7.42 冒烟步 5 的 9 个阶段正是
        # 被这些 already 步撑大了 ok）。其它阶段不动：`already` 在 till/plant/water 里
        # 语义是"已经达标"（真成功），没有逐格 cleared 对账。
        if task == "clear_area":
            already_steps = [s for s in ok_all
                             if str(getattr(s, "code", "") or "") == "already"]
            oks = [s for s in ok_all
                   if str(getattr(s, "code", "") or "") != "already"]
        else:
            already_steps = []
            oks = ok_all
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
        # 【task-63】"被游戏拒绝"（`tool_ineffective`/`precondition_failed`）：不算硬失败，
        # 但单独计数 + 逐格留痕；与 `unreachable` 完全独立（两套集合、两套界）。
        refused_steps = [s for s in all_steps if s.refused]
        refused_tiles = sorted({tuple(s.tile) for s in refused_steps if s.tile})
        refused_in_left = min(len(leftover),
                              len([t for t in self.refused_day if t in left_set]))
        # 【task-68】"被围住"（四邻没有"可清 + 自己够得着"的突破口）：与
        # `unreachable`/`refused` **都独立** —— 不写 `self.blocked`（不封格）、不进任何豁免分子，
        # 只单独计数 + 逐格留痕（run6 的 42 格"走不到"里就有这种成分，混着会污染不可达上界）。
        encircled_steps = [s for s in all_steps if s.encircled]
        encircled_tiles = sorted({tuple(s.tile) for s in encircled_steps if s.tile})
        # 【task-27 / 0.7.46】把本阶段"目标池前置过滤判死"的格并进 encircled 证据（它们没有
        # step、不算 attempted、不进 bound_basis；只作为 encircled 逐格证据 + 后续阶段不再选）。
        prefiltered_here = [r for r in self._prefiltered_encircled_today[prefiltered_before:]
                            if str(r.get("stage") or "") == task]
        prefiltered_tiles = sorted({tuple(int(x) for x in r["tile"]) for r in prefiltered_here})
        if prefiltered_tiles:
            encircled_tiles = sorted(set(encircled_tiles) | set(prefiltered_tiles))
        encircled_in_left = min(len(leftover),
                                len([t for t in self.encircled_day if t in left_set]))
        # 【task-68】开路记录：为了够到目标格而先清掉的**邻格**（`farmwork._ensure_reachable`
        # 把结果写在 `StepResult.after["clear_neighbor"]` 里）⇒ 阶段级汇总一条 `clear_neighbor`。
        opens: list[dict[str, Any]] = []
        for s in all_steps:
            for item in (s.opened or []):
                if isinstance(item, dict):
                    opens.append({"target": list(s.tile) if s.tile else None, **item})
        attempted_steps = sum(1 for s in all_steps if s.attempted)
        # 【task-219】瓦片级执行对账（**按瓦片不按 step**）：`assigned` 的格必须落进
        # ok / failed / unexecuted 三者之一（不变式 `requested == ok + failed + unexecuted`），
        # 且每个"没做成"的格都要有一个**闭合集**原因码（`INTENT_REASON_CODES`），集外码由
        # analyzer 判红。这份账本**只留痕**：不改 checks、不动 `_leftover`、不做任何豁免。
        assigned_set = {tuple(t) for t in assigned}
        # 【task-242】瓦片级 ok 集合仍按**全部 ok 步**（含 `already`）算：那些格子确实已经达标，
        # 不该掉进 unexecuted；`ok` 的**步数**则只数真清掉的（见上）。
        ok_tiles_set = {tuple(s.tile) for s in ok_all if s.tile} & assigned_set
        bad_steps: dict[tuple[int, int], list[StepResult]] = {}
        for s in all_steps:
            if not s.tile or s.ok:
                continue
            key = tuple(s.tile)
            if key in assigned_set:
                bad_steps.setdefault(key, []).append(s)
        failed_set = {k for k in bad_steps if k not in ok_tiles_set}
        unexec_set = assigned_set - ok_tiles_set - failed_set
        tile_reasons: dict[str, int] = {}
        reason_rows: list[tuple[tuple[int, int], str, str, str]] = []
        tmap_now = FarmWorker.tiles_of(obs)
        for key in sorted(failed_set | unexec_set):
            steps_here = bad_steps.get(key) or []
            if not steps_here and key in self.encircled_day:
                # 【task-27 / 0.7.46】目标池前置过滤判死的格没有 step：既不是"做成了"，
                # 也不是"没试过"，如实归 `blocked_tile`（闭合集内，不落 unknown_evidence）。
                reason = "blocked_tile"
            else:
                reason = self._tile_reason(key, steps_here, stopped=stopped, obs=obs)
            tile_reasons[reason] = tile_reasons.get(reason, 0) + 1
            tv = tmap_now.get(key) or {}
            kind = str(tv.get("kind") or "")
            tool = str(getattr(steps_here[0], "tool_need", "") or "") if steps_here else ""
            reason_rows.append((key, reason, kind, tool))
        self._gaps_merge(reason_rows, rep)
        # 【task-242】`already` 步的两种原因（逐格证据，只留痕）：
        #   * `cleared_by_neighbor` —— 该格是被本次**开路**连带清掉的（`clear()` 的
        #     `open_way` 清邻格，之后它自己作为目标再被走到时已空 ⇒ 回 already）；
        #   * `no_target` —— 本来就没有需要清的障碍（观测与目标池之间的一次竞态/陈旧）。
        neighbor_open: set[tuple[int, int]] = set()
        for item in opens:
            nb = item.get("neighbour")
            if isinstance(nb, (list, tuple)) and len(nb) == 2:
                try:
                    neighbor_open.add((int(nb[0]), int(nb[1])))
                except (TypeError, ValueError):
                    continue
        already_cause: dict[str, list[list[int]]] = {"cleared_by_neighbor": [], "no_target": []}
        for s in already_steps:
            if not s.tile:
                continue
            key = (int(s.tile[0]), int(s.tile[1]))
            bucket = "cleared_by_neighbor" if key in neighbor_open else "no_target"
            already_cause[bucket].append([key[0], key[1]])
        rep.stages.append({
            "stage": task, "tiles": 0 if not all_steps else len({s.tile for s in all_steps if s.tile}),
            "ok": len(oks), "skipped": len(skipped), "failed": len(failed),
            # 【task-242】清障账面的第三类"成功"：没改变格子、也没消耗体力的 `already` 步。
            # 不计入 `ok`；这样 `ok == len(cleared_tiles)`（每个真清掉的格子一格一步）。
            # 口径声明（task-242 根因）：`ok` 从"尝试成功数"改成"**真世界变化数**"；
            # `attempted_ok` = 尝试成功但世界没变（= already 步，deputy 的账本形态
            # `ok == attempted == bound_basis`、`engaged == len(cleared_tiles)` 即此）。
            "already": len(already_steps),
            "attempted_ok": len(already_steps),
            "already_tiles": sorted([list(t) for t in
                                     {tuple(s.tile) for s in already_steps if s.tile}]),
            "already_cause": already_cause,
            # `unclear` = ok 步但拿不到 kind 证据（旧代码只在本进程里数、账本无痕 ⇒ 差额不可解释）
            "unclear": unclear_steps,
            "failed_any": len(failed_any),
            "proven_inert": len(inert),
            "env_block": len(env_fail), "inconclusive": len(inconclusive),
            # 【task-52】账本字段名与 `tools\verify-run3.py` 的自算口径**逐字对齐**（Lead m04925）：
            # `stages[i].unreachable`（int）+ `stages[i].unreachable_tiles`（[[x,y],…]）。
            "unreachable": len(unreach_tiles),
            "unreachable_tiles": [list(t) for t in unreach_tiles],
            "unreachable_leftover": unreach_in_left,
            # 【task-63】被游戏拒绝：同样的三段式（计数 / 逐格坐标 / 还留在 leftover 的格数）
            "refused": len(refused_tiles),
            "refused_tiles": [list(t) for t in refused_tiles],
            "refused_leftover": refused_in_left,
            # 【task-68】被围住：计数 / 逐格坐标 / 还留在 leftover 的格数（**不参与豁免**）
            "encircled": len(encircled_tiles),
            "encircled_tiles": [list(t) for t in encircled_tiles],
            "encircled_leftover": encircled_in_left,
            # 【task-27 / 0.7.46】其中有多少是**目标池前置过滤**判死的（没有 step、没有尝试，
            # 不进 unreachable/bound_basis；旁证在 journal `encircled` 的 prefilter=True 条）。
            "encircled_prefiltered": len(prefiltered_tiles),
            "encircled_prefiltered_tiles": [list(t) for t in prefiltered_tiles],
            "attempted": attempted_steps,
            # 【task-219】瓦片级对账（三分类 + 闭合集原因码；`reasons` 只对"没做成"的格计数，
            # 恒有 `Σ reasons.count == failed_tiles + unexecuted_tiles`）
            "requested_tiles": len(assigned_set),
            "ok_tiles": len(ok_tiles_set),
            "failed_tiles": len(failed_set),
            "unexecuted_tiles": len(unexec_set),
            "reasons": dict(tile_reasons),
            # 【task-78 NIT-1】上界基数：发起过动作、且**不是** `encircled` 的步数。
            # `attempted` 一字不动（原始证据计数），豁免上界改用它做分母（fail-closed）。
            "bound_basis": sum(1 for s in all_steps if s.attempted and not s.encircled),
            # 【task-27 / 0.7.46】其中**真的发起过动作**的 `encircled` 步数。task-27 起"被围死"
            # 的格可能在目标池就被预过滤（`encircled_prefiltered`，0 次尝试、没有 step）⇒
            # `attempted − encircled_attempted` 才是旧口径 `bound_basis` 的分母还原，
            # 而 `encircled`（含预过滤）仍是**逐格证据总数**。两者都只留痕，判定不变。
            "encircled_attempted": sum(1 for s in all_steps if s.attempted and s.encircled),
            # 【task-78 NIT-2】判 `encircled` 时**实际试了几次开路**（逐格证据，不参与判定）。
            "encircled_tried": sum(int(getattr(s, "tried_open", 0) or 0) for s in encircled_steps),
            # 【task-68】`engaged` = 其中**真的站到过目标格旁边**的步数（`stood`）——
            # 只作证据（`unreachable_summary.engaged`），**不参与**任何上界计算（task-78 后分母
            # 是 `bound_basis`）。
            "engaged": sum(1 for s in all_steps if s.attempted and s.stood),
            "stopped": stopped, "leftover": len(leftover),
            # 【task-5 / 0.7.44】leftover 拆两个**只作 info** 的数：可执行余格 vs 物理挡死格。
            # 二者之和恒等于 `leftover`；`no_unmet_stages` 仍只看 `assigned_undone`，
            # 绝不拿这里的分拆去放宽判据（诚实优先：该做没做照旧 unmet、当天可不 VERIFIED）。
            "leftover_executable": len(leftover_exec),
            "leftover_blocked": len(leftover_blocked),
            "leftover_blocked_tiles": [list(t) for t in leftover_blocked[:12]],
            # 【task-5 / 0.7.44】本阶段到"重分无产出"上界、当天不再选的格（逐格 journal `blocked`）。
            "alloc_capped_tiles": [list(t) for t in alloc_capped_today[:12]],
            # 【task-16 / 0.7.45】本阶段"清成了但背包 0 空格 ⇒ 掉落被游戏拒收"的步数/逐格/近似掉落。
            # 只作 info：不进 ok/failed/checks，日终 `day_end` 里也会有一份日级汇总。
            "loot_lost": sum(1 for s in all_steps if bool(getattr(s, "loot_lost", False))),
            "loot_lost_tiles": sorted([list(t) for t in {
                tuple(s.tile) for s in all_steps
                if bool(getattr(s, "loot_lost", False)) and s.tile}]),
            "loot_lost_items": list(rep.loot_lost_items),
            # 【task-218 ⑧ / 0.7.39 P0-1】逐格清障证据：真正发生 kind 变化的格子（坐标）。
            # 护栏 B 的判据就是这份清单非空；`blocker_drop` 只是 farm 级 info（字段不存在 ⇒ None）。
            "cleared_tiles": [list(t) for t in cleared_tiles],
            "blocker_drop": blocker_drop,
            # 【task-134 B】`assigned` = 这一阶段分下去的格数；`assigned_undone` = 其中没做成、
            # 也没按规跳过的格数。日级 `no_unmet_stages` 从 task-134 起看 `assigned_undone`
            # （`leftover` 仍是"片区还剩多少格"，作为 `plot_pending` 落账、供守卫/换片/resume 用）。
            "assigned": len(assigned), "assigned_undone": assigned_undone,
            # 【devcoder-day-end-gates / Fix 1+2】`assigned_undone` 的**逐格坐标**（前 64 条）：
            # 日级豁免要靠它做"已证挡死的格"与"真的没做完的格"**逐格求交** —— 只看计数会把
            # "另一阶段该做没做"的格也一起洗掉；只看最后一条记录的 `*_leftover` 又会在
            # "不可达格早在前几条记录就解掉、最后一条 leftover=0"时把豁免归零（A9 winter 26）。
            "assigned_undone_tiles": [list(t) for t in sorted(assigned - assigned_done)[:64]],
            # 【task-161】阶段体力实测（只留痕）：取不到观测就是 `None`，**不许写 0**。
            # `day_end.stamina_calibration` 按 stage 聚合这三个数，用来**事后**标定
            # `farmwork.py` 的估算常量（本卡不动常量、不动任何判据）。
            "stamina_before": stamina_before,
            "stamina_after": stamina_after,
            "stamina_spent": stamina_spent,
        })
        if assigned_undone:
            self._journal("stage_shortfall", stage=task, zone=self.zone_name,
                          assigned=len(assigned), undone=assigned_undone, stopped=stopped,
                          leftover=len(leftover),
                          note="【task-134 B】阶段分下去的格没做完（未按规跳过）⇒ 除非是诚实上限"
                               "（体力/夜里收工/做完后撞 budget），当天判 unmet；"
                               f"本阶段 stopped={stopped or '（自然走完）'}"
                               "（task-143：`plant_area` 的分配额已按手上种子数收窄，"
                               "所以 stopped=no_seed 时 undone 必须为 0；再出现 undone>0 + no_seed "
                               "就是分配额超资源的口径 bug，不是'没干完'）；"
                               "片区还剩几格是 `plot_pending` 口径，两者刻意分开")
        if unreach_steps:
            self._journal("unreachable_stage", stage=task, zone=self.zone_name,
                          tiles=len(unreach_tiles), in_leftover=unreach_in_left,
                          coords=[list(t) for t in unreach_tiles[:12]],
                          note="走不到（没有落脚点/寻路到不了）⇒ 不算硬失败；"
                               "日级豁免有上界，逐格坐标见 unreachable 事件")
        if refused_steps:
            self._journal("refused_stage", stage=task, zone=self.zone_name,
                          tiles=len(refused_tiles), in_leftover=refused_in_left,
                          coords=[list(t) for t in refused_tiles[:12]],
                          note="游戏拒绝（tool_ineffective/precondition_failed）⇒ 不算硬失败、"
                               "当天封格次日重试；日级豁免有上界，逐格见 tool_refused 事件")
        if encircled_steps:
            self._journal("encircled_stage", stage=task, zone=self.zone_name,
                          tiles=len(encircled_tiles), in_leftover=encircled_in_left,
                          tried_open=sum(int(getattr(s, "tried_open", 0) or 0)
                                         for s in encircled_steps),
                          coords=[list(t) for t in encircled_tiles[:12]],
                          note="四邻没有「可清障 + 自己够得着」的突破口"
                               "（【task-78】照实写，不再断言是树/桩/大石）⇒ "
                               "不算「走不到」、不封格、不进 unreachable 豁免；"
                               "逐格真实 kind 与开路次数见 encircled 事件")
        if opens:
            self._journal("clear_neighbor", stage=task, zone=self.zone_name,
                          opens=len(opens), targets=[o for o in opens[:12] if o.get("target")],
                          note="【task-68】为够到目标格先清掉了邻格（开路；每格 ≤4 次动作）")
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
            if task == "reduce_scope":
                # 【task-168】认输意图也要过同一道关：田区必须**当前观测里真的存在**
                # （`resolve_zone`/名字匹配），且今天还没认输过。不满足 ⇒ `cancel`
                # ——注意 cancel 只否掉**这一轮**，不写 `no_target`（否则一次算错就把
                # 当天的机制锁死；下一个决策轮还能重新提议）。
                zone_name = str(getattr(intent, "area_hint", "") or "")
                zones = {str(getattr(z, "name", "")) for z in self._zones(obs)}
                reason = ""
                if self.scope_shed_today:
                    reason = "今天已经认输过一个区（一天上限 1）"
                elif not zone_name or zone_name not in zones:
                    reason = f"观测里找不到田区「{zone_name or '(空)'}」"
                if reason:
                    verdicts.append({"intent_id": self._intent_id(intent), "task": task,
                                     "verdict": "cancel", "reason": reason})
                else:
                    kept.append(intent)
                    verdicts.append({"intent_id": self._intent_id(intent), "task": task,
                                     "verdict": "keep", "targets": 1, "zone": zone_name})
                continue
            if task not in STAGE_ACTION:
                kept.append(intent)          # review / sleep 之类不按"有没有目标格"判
                continue
            tiles = [] if far else self._stage_tiles(task, obs, plot)
            if tiles:
                kept.append(intent)
                verdicts.append({"intent_id": self._intent_id(intent), "task": task,
                                 "verdict": "keep", "targets": len(tiles)})
            elif far:
                kept.append(intent)
                verdicts.append({"intent_id": self._intent_id(intent), "task": task,
                                 "verdict": "unknown",
                                 "reason": f"作业区离玩家 {walk_dist} 格，观测看不见，先走过去再看"})
            else:
                verdicts.append({"intent_id": self._intent_id(intent), "task": task,
                                 "verdict": "cancel",
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
        # 【task-84】"该浇水"只认**活苗**（死苗浇了也没用 ⇒ 去处是 `clear_dead`），
        # 且政策顺序跟 `planner.deterministic_plan` 一致：harvest → clear_dead → water_area。
        unwatered = [t for t, v in tmap.items()
                     if v.get("crop") and not v.get("watered") and not v.get("dead")]
        ripe = [t for t, v in tmap.items() if v.get("crop") and tile_ready(v)]
        dead = [t for t, v in tmap.items() if v.get("crop") and v.get("dead")]
        must: list[TaskIntent] = []
        notes: list[str] = []
        if ripe:
            must.append(TaskIntent(
                "harvest", "", f"政策：{len(ripe)} 格作物熟了，先收掉腾地", ()))
        if dead:
            must.append(TaskIntent(
                "clear_dead", "",
                f"政策：{len(dead)} 格枯死作物占着耕地（浇水对它们无用），先清掉", ()))
        if unwatered:
            must.append(TaskIntent(
                "water_area", "",
                f"政策：{len(unwatered)} 格作物没浇水，当天不浇就补不回来", ()))
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
            if task == "reduce_scope":
                # 【task-168】规模取舍：先把该区成熟作物收掉，再记账认输、把该区从目标池剔除。
                # 判定一个字不动（`checks`/`plot_pending`/`assigned_undone` 照旧算未完成）。
                # 【task-219】每条意图都要有执行对账：认输没成 ⇒ `gated`（今天已认输/上限/区不可见）。
                shed_ok = self._shed_scope(str(intent.area_hint or ""), obs, rep)
                acted = shed_ok or acted
                self._record_intent(intent, task=task, executed_steps=1 if shed_ok else 0,
                                    reasons={} if shed_ok else {"gated": 1})
                obs = self._snap()
                continue
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
                self._record_intent(intent, task=task, executed_steps=1)
                continue
            if task in ("sleep", "recover_stamina"):
                allow, code, text = self.sleep_guard(obs)
                if not allow:
                    rep.notes.append(f"否决 {task}：{text}")
                    self._journal("intent_vetoed", task=task, reason=text)
                    self._say(f"  · 否决 {task}：{text}")
                    self._record_intent(intent, task=task, reasons={"gated": 1}, note=text)
                    continue
                rep.ended_by, rep.ended_reason = self._do_sleep(obs, rep, f"{code}:{text}")
                self._record_intent(
                    intent, task=task, executed_steps=1,
                    reasons={"world_stuck": 1} if rep.ended_by == "sleep_failed" else {})
                return True
            if task == "wait_for_save":
                st = self.worker.load_save()
                self._actions += 1
                rep.notes.append(f"读档：{st.reason}")
                self._journal("load_save", ok=st.ok, reason=st.reason)
                acted = acted or st.ok
                self._record_intent(intent, task=task, executed_steps=1 if st.ok else 0,
                                    reasons={} if st.ok else {"world_stuck": 1}, note=st.reason)
                continue
            if task == "ship":
                shipped = self._ship_loot(obs, rep)
                acted = shipped or acted
                if shipped:
                    self._record_intent(intent, task=task, executed_steps=1)
                else:
                    # 【task-233】`ship` 是**非片区**意图：§8 的 `no_target` 证据 schema
                    # （`stage_tiles_empty`）不适用 ⇒ 按 §8.2b **禁止裸用 no_target**，
                    # 统一降级 `unknown_evidence` + `unknown_why`，并把它自己的可判证据
                    # （白名单数/空格）带上；analyzer 的
                    # `missed:intent_no_target_evidence:ship` 因此消失。
                    evidence = self._non_plot_evidence(task, obs)
                    if evidence is None:
                        evidence = {"unknown_why": "obs_unavailable"}
                        note = "出货失败，且拿不到背包/白名单证据 ⇒ 无法判定（不给 no_target）"
                    else:
                        evidence = {"unknown_why": "non_plot_task", **evidence}
                        note = ("本轮没有出货成功（可判证据：白名单 "
                                f"{evidence.get('whitelist_count')} 项、空格 "
                                f"{evidence.get('free_slots')}）⇒ 非片区任务按 unknown_evidence 记"
                                "（§8.2b：不冒充「没目标」）")
                    self._record_intent(intent, task=task, executed_steps=0,
                                        reasons={"unknown_evidence": 1},
                                        evidence=evidence, note=note)
                obs = self._snap()
                continue
            if task == "buy":
                # 【0.7.49 D2 修复】`_preconditions` 返回的是**观测 dict**（不是 bool），但它内部
                # （`:7393`）**确实调用了** `_preconditions_apply` ⇒ 旧接线
                # `changed = self._preconditions(obs, rep)` 的**购买路径照常真的执行（钱真的花）**；
                # 缺陷在**记账**：`changed` 绑定非空 dict（恒真）⇒ 每条 `buy` 意图都记
                # `executed_steps=1` + `acted`，**不管这一轮有没有真买到** ⇒ 无动作的一天被记成
                # acted、遮蔽 stuck/无进展路径（`{"unknown_evidence":1}` 成死代码）。
                # 真正"有没有改动世界"由 `_preconditions_apply` 返回 bool（买/卖成功才 True）。
                # 真实入口链：`_preconditions_apply` → `_buy_seed` → `worker.buy` → 桥 `buy` →
                # 游戏 `ShopMenu.tryToPurchaseItem(item, null, count, 0, 0)`；成败判据是**钱/背包差分**
                # （`farmwork.FarmWorker.buy`：`have_after > have_before and money_after < money_before`），
                # 回执只是声明 —— 见 `bridge.py:1132-1136`。
                changed = self._preconditions_apply(obs, rep)
                if changed:
                    try:
                        obs = self._snap()
                    except Exception:
                        pass
                self._record_intent(intent, task=task,
                                    executed_steps=1 if changed else 0,
                                    reasons={} if changed else {"unknown_evidence": 1},
                                    note="buy 由 _preconditions 流程执行（游戏入口 ShopMenu.tryToPurchaseItem）")
                acted = changed or acted
                continue
            if task == "upgrade_tool":
                # 【0.7.48 已知限制】工具种类**硬编码 "axe"**（本卡只做接线 + 审计，不顺手做通用化）。
                # 真实入口链：`worker.upgrade_tool("axe")` → 桥 `upgrade_tool` → 铁匠铺
                # `Utility.TryOpenShopMenu("ClintUpgrade","Clint",true)` → 反射
                # `tryToPurchaseItem(item, null, 1, 0, 0)`；成败靠观测差分
                # （`farmwork.FarmWorker.upgrade_tool`：钱少/出现 `toolBeingUpgraded`/等级变大）。
                st = None
                try:
                    mv = self.worker.ensure_location("Blacksmith", timeout_ms=30000)
                    if getattr(mv, "ok", False):
                        obs = self._snap()
                    st = self.worker.upgrade_tool("axe", timeout_ms=60000)
                except Exception as exc:  # noqa: BLE001
                    self._journal("upgrade_tool", ok=False, code="exception", reason="exception:" + type(exc).__name__,
                                  tool="axe", tool_hardcoded=True)
                changed = bool(getattr(st, "ok", False))
                if st is not None:
                    self._journal("upgrade_tool", ok=changed, code=getattr(st, "code", ""), reason=getattr(st, "reason", ""),
                                  tool="axe", tool_hardcoded=True,
                                  before=getattr(st, "before", None), after=getattr(st, "after", None))
                self._record_intent(intent, task=task,
                                    executed_steps=1 if changed else 0,
                                    reasons={} if changed else {"unknown_evidence": 1},
                                    note="upgrade_tool " + ("ok" if changed else "no_effect"))
                acted = changed or acted
                obs = self._snap()
                continue
            if task in STAGE_ACTION:
                acted = self._run_stage_intent(intent, obs, plot, rep) or acted
                obs = self._snap()
                continue
            self._journal("intent_unknown", task=task)
            rep.notes.append(f"未知意图 {task}（跳过）")
            self._record_intent(intent, task=task, reasons={"unknown_evidence": 1},
                                note="未知意图（执行层不认识这个 task）")
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
        # 【task-186 F3/NIT-4】卖之前先把白名单的**来源与核对结果**算出来：白名单 = 今天亲手收获
        # 且**有格子级证据**（crop 消失 / ready 翻转 / readySource 变化 / 受影响格）的 qid；
        # 只有背包差分、没有格子级证据的那批已经在 `farmwork.harvest()` 里被挡在白名单外
        # （它仍算收获成功，只是不进白名单 —— 防误卖与本次动作无关的物品）。
        # 刻意**不新增事件名**：把来源与数量加进既有的 `sell` 事件（task-134 的教训：加字段安全、
        # 新增事件名会让 analyzer 的机械枚举漂移）。
        whitelist = sorted(getattr(self.worker, "harvested", None) or {})
        steps = self.worker.sell_loot(timeout_ms=self.sell_timeout_ms)
        if not steps:
            return False
        for st in steps:
            before = st.before if isinstance(st.before, dict) else {}
            self._journal("sell", ok=st.ok, code=st.code,
                          slot=before.get("slot"), qid=before.get("qid"),
                          stack=before.get("stack"), before=st.before, after=st.after,
                          reason=st.reason, receipt=st.receipt,
                          whitelist=whitelist, whitelist_count=len(whitelist),
                          whitelist_source="harvest_tile_bound_gained")
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

    def _dismiss_modal_once(self, menu: str, ui: dict[str, Any], *, kind: str,
                            tries: int = 0) -> dict[str, Any]:
        """关一次模态并重新观测（回执原文进 journal；世界是否真变了解除由后续观测回答）。

        【task-129】`ShippingMenu` 要走"出货 → 日切保存 → 换天"整条链（Mod 侧反射
        `okClicked()` 后只等游戏自己走完），合法地要十几秒 ⇒ 必须显式给大预算
        （客户端默认只有 5s，会把"游戏正在存档"判成超时）。其它模态仍是短活。

        【task-236】`tries` 是收尾守卫的轮次（`kind="cleanup"` 时带出去，便于账本对"关了几次")；
        其它调用点保持默认 0，**事件名与既有字段不变**（不新增事件名，避免 analyzer 漂移）。
        """
        assert self.client is not None
        menu_text = str(ui.get("activeMenuText") or "")
        budget = MODAL_DISMISS_BUDGET_MS.get(menu, MODAL_DISMISS_DEFAULT_MS)
        receipt = self.client.dismiss_modal(timeout_ms=budget)
        self._actions += 1
        self._journal("modal_dismissed", kind=kind, menu=menu, menuText=menu_text,
                      receipt=receipt, tries=tries,
                      note=("提问走 dismiss_modal 的选否口径（项目硬规则：永不注入确认键）"
                            if kind == "question" else None))
        self._say(f"  · 关掉挡路模态 {menu or '?'}（{kind}）"
                  f"{'：' + menu_text if menu_text and menu_text != menu else ''}")
        return self._snap()

    @staticmethod
    def _event_dialogue_state(obs: dict[str, Any]) -> tuple[bool, bool, str, bool]:
        """只读"事件对话"现场：`(event_up, is_question, menu, has_dialogue)`（task-228）。

        字段缺失一律按 `False` 处理（fail-closed = 不动手）：宁可停手等人，也不能因为
        "读不到"就去点一下——点错一下可能替游戏选掉一个不可逆选项。
        """
        ui = obs.get("ui") or {}
        event_up = ui.get("eventUp") is True
        menu = str(ui.get("activeMenu") or "")
        is_question = (ui.get("dialogueIsQuestion") is True
                       or bool(ui.get("dialogueResponses")))
        return event_up, is_question, menu, menu == "DialogueBox"

    def _event_advance_possible(self, obs: dict[str, Any]) -> bool:
        """【task-228】现在能不能继续推进事件对话（不能 ⇒ 交给 task-41 的硬停）。

        四个条件全部成立才行：`eventUp=true` + 当前是 `DialogueBox` + **不是提问** +
        推进额度还没用尽（连续 stalled 未达上限、当天步数未满、客户端有这个能力）。
        """
        event_up, is_question, _menu, has_dialogue = self._event_dialogue_state(obs)
        if not event_up:
            return False
        # 【task-230】拆成两行是刻意的：task-224 探针按"`not has_dialogue or is_question`"
        # 这条**同一行**判"非提问才动"仍在（行为完全不变，只是让文本契约更易机械核对）。
        if not has_dialogue or is_question:
            return False
        if self.event_stall_streak >= EVENT_STALL_GIVE_UP:
            return False
        if self.event_advance_steps_today >= EVENT_ADVANCE_DAY_STEPS:
            return False
        client = getattr(self, "client", None)
        return getattr(client, "advance_dialogue", None) is not None

    def _advance_event_dialogue(self, obs: dict[str, Any], rep: DayReport) -> dict[str, Any]:
        """【task-228】事件里的**非提问对话**受控推进；其它情况一律不动（返回原观测）。

        为什么必须留一条"能动"的路：`ui.eventUp=true` 的既有政策是"硬停等人"（task-41），
        但事件里的非提问对话天然停在第一句等点击 ⇒ 无人值守时**永久挂住**（真机事故：
        Clint 送熔炉配方）。用户已授权"只推进非提问对话、永不替游戏选选项"。

        纪律（全部 fail-closed，没有证据就停手）：
          * 不是事件 / 事件里不是 `DialogueBox` / 是提问 / 有职业选择 ⇒ **一次都不点**；
          * 每次最多推 :data:`EVENT_ADVANCE_MAX_STEPS` 步、每天累计最多
            :data:`EVENT_ADVANCE_DAY_STEPS` 步；用满就交给 `_clear_modals` 的
            `event_blocked` 诚实收尾（**不许**无限自旋）；
          * 回执 `stalled=true`（点下去没有世界变化；事件可能在 `pause`）连续
            :data:`EVENT_STALL_GIVE_UP` 次 ⇒ 停止推进，同样交给 `event_blocked`；
          * 桥异常 / 回执不可解析 ⇒ 记一条既有 `modal_dismiss_failed` 后停手（不猜）。
        真推进复用既有 `modal_dismissed` 事件（`kind="dialogue_advance"`）——
        **不新增 journal 事件名**（analyzer 机械枚举的纪律）。
        """
        event_up, _is_question, menu, _has_dialogue = self._event_dialogue_state(obs)
        if not event_up:
            self.event_stall_streak = 0
            return obs
        if not self._event_advance_possible(obs):
            return obs
        client = getattr(self, "client", None)
        advance = getattr(client, "advance_dialogue", None)
        if advance is None:                       # 旧客户端/假世界没有这个能力 ⇒ 不动手
            return obs
        budget = min(EVENT_ADVANCE_MAX_STEPS,
                     EVENT_ADVANCE_DAY_STEPS - self.event_advance_steps_today)
        self.event_advance_calls_today += 1
        try:
            receipt = advance(max_steps=budget, timeout_ms=EVENT_ADVANCE_TIMEOUT_MS)
        except BridgeError as exc:
            self._journal("modal_dismiss_failed", kind="dialogue_advance", menu=menu,
                          status=str(getattr(exc, "status", "") or ""), reason=str(exc)[:200])
            self.event_stall_streak += 1
            return obs
        if not isinstance(receipt, dict):
            self.event_stall_streak += 1
            return obs
        stepped = int(receipt.get("stepped") or 0)
        stalled = receipt.get("stalled") is True
        status = str(receipt.get("status") or "")
        if stepped > 0:
            self.event_advance_steps_today += stepped
            self.event_stall_streak = 0
            self._journal("modal_dismissed", kind="dialogue_advance", menu=menu,
                          status=status, stepped=stepped, stalled=False,
                          before=receipt.get("before"), after=receipt.get("after"),
                          steps_today=self.event_advance_steps_today)
            note = (f"事件对话推进 {stepped} 步（今天共 {self.event_advance_steps_today} 步，"
                    f"上限 {EVENT_ADVANCE_DAY_STEPS}）")
            rep.notes.append(note)
            self._say(f"  · {note}")
            return self._snap_or(obs)
        if stalled or status == "advance_stalled":
            self.event_stall_streak += 1
            self._journal("modal_dismiss_failed", kind="dialogue_advance", menu=menu,
                          status=status or "advance_stalled", stalled=True,
                          streak=self.event_stall_streak, limit=EVENT_STALL_GIVE_UP)
            if self.event_stall_streak >= EVENT_STALL_GIVE_UP:
                rep.notes.append(
                    f"事件对话连续 {self.event_stall_streak} 次点不动 ⇒ 停止推进、"
                    "按 eventUp 诚实收尾（等玩家）")
            return obs
        if status:                                # is_question / professions_pending / …
            self._journal("modal_dismiss_failed", kind="dialogue_advance", menu=menu,
                          status=status, reason=str(receipt.get("reason") or "")[:200])
        return obs

    def _wait_event_up(self, obs: dict[str, Any]) -> tuple[dict[str, Any], bool, int]:
        """【task-245】`eventUp=true` 且没有对话盒：**有界等待**事件自己开出对话盒。

        返回 `(最新 obs, still_blocked, tries)`：

          * `still_blocked=True` ⇒ 等满 :data:`EVENT_WAIT_TRIES` 仍 `eventUp` 且无对话盒
            （调用方走 `_event_blocked` 诚实收尾，并把 `tries` 写进账）；
          * `still_blocked=False` ⇒ 事件自己结束了，或者对话盒已经出现
            （调用方回日循环：下一秒 `_advance_event_dialogue` 会接手非提问对话）。

        每轮 journal `event_wait`（`tries/limit/eventId/eventUp/hasDialogue/worldSeq/
        waitSeconds/note`），这样账本能回答"到底等了多久、事件 id 是什么、
        等的时候世界序号有没有动"——0.7.42 冒烟冬 7 的教训：缺 `eventId` 时
        连"是哪条事件"都说不出来。

        为什么用 `self.sleep_fn`：长跑的等待一律走可注入的 sleep（测试里被替换成 no-op，
        真机是 `time.sleep`），既不阻塞回合边界，也让单测保持毫秒级。

        【Fix A / devcoder-spring1-event】A9 spring1 实证**推翻**了"冻结=卡死"的旧假设：Kent
        归来 `eventId=63` 是纯自动过场（skippable，command 6=pause/动画/视口自播，原版事件命令集
        无"等玩家走格"命令），三合一指纹 `worldSeq`+`ui.eventCommand`+`ui.dialogueLines`
        **全冻是正常态**，结束条件=计时到/动画播完、**不需玩家动作**。所以：
          * 无对话框冻结态**不再提前判死** —— 给足整段等待窗（`total_limit` 轮），只跑到
            `tries >= total_limit` 仍 `eventUp` 才诚实 `event_blocked`；
          * `total_limit` = :data:`EVENT_WAIT_TRIES` + :data:`EVENT_WAIT_EXTRA_TRIES`
            始终兜底，绝不无限等（永不结束的事件仍诚实 `event_blocked`，不洗成过关）；
          * 对话盒一出现 / 事件结束 ⇒ 立刻回日循环（交给 `_advance_event_dialogue`）。
        """
        tries = 0
        idle = 0
        moved_any = False
        # 【A9 spring1 实证】事件期 `worldSeq`（地点|玩家格|时间|日|钱|背包件数）**必然冻结**
        # （事件把游戏时间冻在 600），所以只用它判"在不在推进"会把正常过场误判成卡死
        # （run6：worldSeq 161→162 后冻 60s ⇒ event_blocked）。进展改用**三合一指纹**：
        # `worldSeq` + `ui.eventCommand`（事件脚本执行到第几条 command，Mod 0.7.5x 新增）+
        # `ui.dialogueLines`（当前对话剩余条数）。事件脚本走位/换场景/推进对话时后两者一定在动。
        # 三项都缺（旧 Mod）⇒ 退回只看 worldSeq，行为与改前一致。
        def _fp(o: dict[str, Any]) -> tuple[Any, Any, Any]:
            u = o.get("ui") or {}
            return (o.get("worldSeq"), u.get("eventCommand"), u.get("dialogueLines"))
        fp_seen = _fp(obs)
        total_limit = EVENT_WAIT_TRIES + EVENT_WAIT_EXTRA_TRIES
        while tries < total_limit:
            self.sleep_fn(EVENT_WAIT_SECONDS)
            tries += 1
            obs = self._snap_or(obs)
            ui = obs.get("ui") or {}
            fp = _fp(obs)
            moved = fp != fp_seen
            if moved:
                moved_any = True
                idle = 0
            else:
                idle += 1
            fp_seen = fp
            event_up, _is_question, _menu, has_dialogue = self._event_dialogue_state(obs)
            self._journal("event_wait", tries=tries, limit=EVENT_WAIT_TRIES,
                          limitMax=total_limit, extended=bool(tries > EVENT_WAIT_TRIES),
                          eventId=ui.get("eventId"), eventUp=bool(event_up),
                          hasDialogue=bool(has_dialogue), worldSeq=fp[0],
                          eventCommand=fp[1], dialogueLines=fp[2],
                          worldMoved=bool(moved), worldMovedAny=bool(moved_any),
                          idleStreak=idle, waitSeconds=EVENT_WAIT_SECONDS,
                          note="事件进行中但没有对话盒：有界等待（**不** dismiss / **不** sleep / "
                               "**不** load_save；进展判据=worldSeq+eventCommand+dialogueLines "
                               "三合一指纹；事件结束或对话盒出现就回日循环）")
            if not event_up or has_dialogue:
                return obs, False, tries
            # 【devcoder-spring1-event / Fix A】无对话框冻结态（pause/动画自播，三合一指纹
            # worldSeq+eventCommand+dialogueLines 全冻）是 skippable 过场的**正常**态（A9 spring1
            # 实证：Kent 归来 eventId=63，command 6=pause/动画/视口自播，原版事件命令集无"等玩家
            # 走格"命令；结束条件=计时到/动画播完，不需玩家动作）。**不再因"指纹不动"提前判死**
            # —— 给足整段等待窗，只跑到 `tries >= total_limit` 仍 `eventUp` 才诚实 `event_blocked`。
            # `total_limit` = EVENT_WAIT_TRIES + EVENT_WAIT_EXTRA_TRIES 永远兜底，绝不无限等。
        return obs, True, tries

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

            # ⓪ **游戏事件**（`ui.eventUp == true`）：硬停，绝不代游戏做决定（task-41）。
            # 【task-228】唯一例外：**非提问**的 `DialogueBox` 且推进额度还没用尽 ⇒ 先让日循环
            # 下一轮去 `_advance_event_dialogue` 推一句（用户已授权"只推非提问对话、永不选选项"）；
            # 提问 / 非对话事件 / 额度用尽 / 连续点不动 ⇒ 仍按 task-41 硬停等人。
            if ui.get("eventUp") is True:
                if self._event_advance_possible(obs):
                    return obs, False
                _up, _is_q, _ev_menu, has_dialogue = self._event_dialogue_state(obs)
                if has_dialogue:
                    # 有对话盒但推不动（提问 / 职业选择 / 连续 stalled / 额度用尽）⇒ **立刻**
                    # 硬停（task-41/task-228 语义一字不改）：既不等，也绝不碰。
                    return self._event_blocked(obs, rep)
                # 【task-245】没有可推进的对话盒（开场动画/脚本 pause 期间）⇒ 先**有界等待**：
                # 0.7.42 冒烟冬 7 开局就因"立刻硬停"把整条长跑白烧 4.92 分钟。等待期间一次
                # 都不动手（不 dismiss/不 sleep/不 load_save），只重观测：事件结束或对话盒出现
                # ⇒ 交回日循环；等满仍挂住 ⇒ 才诚实收尾。
                obs, still_blocked, wait_tries = self._wait_event_up(obs)
                if not still_blocked:
                    rounds += 1
                    continue
                self._event_blocked(obs, rep, event_wait_tries=wait_tries)
                return obs, True

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

    def _event_blocked(self, obs: dict[str, Any], rep: DayReport, *,
                       event_wait_tries: int = 0) -> tuple[dict[str, Any], bool]:
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
                      # 【task-245】事件归因：0.7.42 冒烟冬 7 的账本缺这一项 ⇒ 事后无法回答
                      # "是哪条事件把我挂住了"。`eventId` 三态（有值 / null=读不到 / 缺字段=旧 Mod）
                      # 由 Mod 的 EventRules 归一，这里原样落账。
                      eventId=ui.get("eventId"),
                      eventWaitTries=event_wait_tries,
                      # 【Fix 3】等待秒数按**实际等了几轮**算（耐心延长后可能是 4~16 轮，
                      # 写死"基础界"会把账本的低效白等时间少算 3 倍）。
                      eventWaitSeconds=round(event_wait_tries * EVENT_WAIT_SECONDS, 1),
                      # 【task-228】事件对话推进的当日账：`event_blocked` 到底是因为
                      # "提问/职业选择"还是"推了 N 步之后点不动"——账本必须能分清。
                      advance_steps=self.event_advance_steps_today,
                      advance_calls=self.event_advance_calls_today,
                      stall_streak=self.event_stall_streak,
                      note="游戏事件挂住（ui.eventUp=true）：关框会替游戏推进剧情/默认选否 ⇒ "
                           "不 dismiss / 不 sleep / 不 load_save，当天不判 VERIFIED，等人处理")
        rep.ended_by = ENDED_BY_EVENT
        event_id = ui.get("eventId")
        waited = (event_wait_tries * EVENT_WAIT_SECONDS if event_wait_tries else 0.0)
        rep.ended_reason = (f"游戏事件挂住（eventUp=true）：{menu or '?'}"
                            + (f"「{text}」" if text else "")
                            + (f"；eventId={event_id}" if event_id else "；eventId=未知（无法归因）")
                            + (f"；已等待 {waited:.0f}s（{event_wait_tries} 轮）"
                               if event_wait_tries else ""))
        rep.notes.append("游戏事件挂住（eventUp），按政策停下等人：不 dismiss / 不 sleep / 不 load_save"
                         + (f"；等待期间曾空等 {event_wait_tries} 轮" if event_wait_tries else ""))
        self._say(f"× 游戏事件挂住（eventUp）⇒ 停下等人：{menu or '?'}"
                  + (f"「{text}」" if text else "")
                  + (f"；eventId={event_id}" if event_id else ""))
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
        # 【task-20】工具不够格的留痕每天清零（次日工具可能已升级 ⇒ 要重新评估、重新留痕）。
        self.tool_blocked_noted = False
        # 【task-149 C】"确实没活"的独立证据每天清零：昨天证明过不等于今天也证明过。
        self.no_work_evidence_ok = False
        # 【task-149 B】"开工没回到农场"每天清零（同 `_ensure_on_farm` 的写入点）。
        self.day_start_off_farm = False
        # 【task-158】体力预算每天重算（当天活苗数/体力上限都会变）。
        self.budget_today = {}
        self.budget_defer_events = []      # 【task-6 / 0.7.44】日终才落账的"只因预算延后"队列
        self.budget_noted = False
        # 【task-163】预算延后记账每天重来（`deferred` 只描述"今天"）。
        self.budget_deferred_tiles = {}
        self.capacity_capped_noted = set()
        # 【task-168】当天认输额度每天清零（`shed_zones` 是**跨日粘性**的，故意不在这里清）。
        self.scope_shed_today = False
        self.scope_shed_tiles_today = 0
        self.scope_cap_refused_today = False
        self.refills_today = 0
        self.idle_rounds = 0
        self._guard_walk_streak = 0
        self.blocked = {}
        self.tile_attempts = {}
        # 【task-5 / 0.7.44】"同格重分无产出"的当日计数同样每天清零（次日世界变了重新判）。
        self.alloc_no_progress = {}
        self.env_streak = {}
        self.env_spin_noted = set()
        self.seed_gate_noted = set()
        # 【task-67】"今天买不到合适种子"的结论与它的播报位：每天清零（明天可能上架 / 钱变多）。
        # `shop_offers`（货架清单）**不清**：它是稳定事实，留着省一次注定失败的请求。
        self.seed_dead_today = ""
        self.seed_unavail_noted = False
        self.seed_dead_noted = False
        # 【task-55】卖盈余材料的"今天已卖过"标志：每天清零（次日钱已到账、材料也变了）。
        self.surplus_sold_today = False
        self.cannot_afford_noted = False
        # 【task-102】buy 尝试上限 / 空格死锁 / 腾格卖货 / 农场动作计数：每天清零。
        self.buy_attempts_today = 0
        self.buy_no_space_today = False
        self.buy_no_space_noted = False
        self.slot_sold_today = False
        self.farm_actions_today = 0
        self.buy_no_space_facts = {}
        # 【task-198】腾格收敛回路的日级状态每天清零（上界是**每天** `SLOT_RELIEF_MAX` 轮）。
        self.slot_relief_today = 0
        self.slot_relief_noted = set()
        self.slot_relief_stacks_today = 0
        self.slot_relief_sold = []
        self.inventory_blocked_today = False
        self.inventory_blocked_noted = False
        # 【task-16 / 0.7.45】背包空格/掉落留痕的日级状态每天清零（读数与拒收都只描述"今天"）。
        self.free_slots_last = None
        self.free_slots_min = None
        self.free_slots_status = "unavailable"
        self.loot_lost_steps_today = 0
        self.loot_lost_tiles_today = []
        self.loot_lost_items_today = []
        self.loot_lost_noted = False
        self.slot_pressure_noted = False
        self.buy_full_noted = False
        # 【task-28 卡 D】`inventory_blocked` 证据 / 满包清障闸的日级状态每天清零。
        self.bag_evidence_today = {}
        self.bag_relief_exhausted_today = False
        self.clear_area_bag_gate_noted = False
        self.bag_gate_reject_noted = False
        # 【task-25 rev4 / 0.7.46】背包升级（对话购买）的日级状态每天清零（一天一个回合、≤2 次 talk）。
        self.backpack_attempts_today = 0
        self.backpack_ok_today = False
        self.backpack_tried_today = False
        self.backpack_skip_noted = False
        # 【task-218】砍树日预算：每天清零（日上限 + 浇水预备线，见 `_tree_budget_left`）。
        self.trees_cleared_today = 0
        self.tree_budget_noted = False
        # 【task-228】事件对话受控推进的当日额度每天清零（`_advance_event_dialogue`）。
        self.event_advance_steps_today = 0
        self.event_advance_calls_today = 0
        self.event_stall_streak = 0
        # 【task-122】两种退化形态的当日计数，每天清零（只喂教训库，不参与判定）。
        self.plot_exhausted_today = 0
        self.midway_leftover_today = 0
        # 【devcoder-no-work-sleep】连续"无活轮次"每天清零：昨天证明过无活 ≠ 今天也无活。
        self._no_work_cycle_count = 0
        # 【task-124】同一秒连发换片的窗口计数每天清零。
        self._plot_exhausted_last = None
        self._plot_exhausted_window = 0
        self.no_progress_cycles = 0      # 【task-134 A】每日重置：连续无产出环路计数
        self.hint_dropped_today = 0     # 【task-136 C】每日重置：hint 被矛盾判据丢掉的条数
        self.dead_scope_noted = set()
        # 【task-59】复盘每天最多一次（`recent_notes` **不**在这里清：它是"昨晚留给今天"的，
        # 由 `_review_before_sleep` 在夜里覆盖）。
        self.review_done_today = False
        self.no_target = set()
        self.no_target_global = set()
        # 【task-219】意图执行对账的日级状态：`intent_id` 里的 seq 每天从 1 开始
        # （id 形如 `spring13#01`；跨日续跑的旧 id 由 analyzer 当 `carried_over` 看）。
        self.intent_seq = 0
        self.intent_ids = {}
        self.intent_plans = {}
        self.intent_coverage = []
        self.intent_superseded = set()
        self.intent_day = f"{rep.day_key[1]}{rep.day_key[2]}"
        self._gaps_load(rep)
        # 【task-49】跨片地的"今天还没做完"记账 + 回头看的次数上限，每天清零。
        self.leftover_targets = set()
        self.unreachable_day = set()
        # 【task-63】被游戏拒绝的格子同样每天清零 ⇒ 次日自动重试（工具等级/前置条件可能变了）。
        self.refused_day = set()
        # 【task-68】被围住的格子不封格、也不跨日：明天（或今天开路之后）可能就可达了。
        self.encircled_day = set()
        self.frontier_clears = 0
        self.resume_walks = 0
        # 【task-26 / 0.7.46】回片区尝试次数（含失败）每天重置；与 `resume_walks`（只数成功）分开。
        self.resume_walk_attempts = 0
        # 【task-27 / 0.7.46】目标池前置过滤的 encircled 证据每天清零（次日可能开路/变了）。
        self._prefiltered_encircled_today = []
        # 【task-4 / 0.7.44】回片区"换片/停滞"账本每日重置：坐标只来自当天的 `leftover_targets`。
        self.leftover_area = {}
        self.resume_stall_tiles = set()
        self.resume_last_anchor = None
        self.resume_switches = 0
        self.frontier_last_tile = None
        # 【task-50】窗口外干作物的重试记账，每天清零（第二天壶/世界都变了，重新判）。
        self.far_dry_tries = {}
        self.far_dry_given_up = set()
        self.harvest_gave_up = set()            # 【task-170 ②】收获放弃格同样每天重判
        # 【task-133】失败因由与补水次数也每日清零（"壶里有没有水"是新的一天的事）。
        self.far_dry_causes = {}
        self.far_dry_refills_today = 0
        self.far_dry_opens = {}                 # 【task-157】每日重置（开路额度和补水一样按天算）
        self.water_far_not_on_farm = False      # 【task-104】每日重置（理由后缀用）
        self.far_dry_unavailable_noted = False
        # 【task-199】窗口外熟作物：尝试次数/认输/开路额度/播报标记全部每日重置。
        self.ready_far_tries = {}
        self.ready_far_given_up = set()
        self.ready_far_opens = {}
        self.ready_far_unavailable_noted = False
        self.ready_far_truncated_noted = False
        self.ready_far_causes = {}
        self.ready_far_not_on_farm = False
        self.ready_far_bag_noted = False
        # 【task-205】铁匠铺升级链的日级计数每日重置（升级/取回一天最多试一次）。
        self.tool_upgrade_tried = 0
        self.tool_upgrade_skipped_noted = False
        self.tool_upgrade_blocked_noted = False
        # 【task-42】新的一天 ⇒ 清空出货白名单：昨天收获的东西昨天该出就出了，
        # 今天再拿白名单去卖会变成"卖一件不存在的东西"（`sellable_slots` 找不到就不动，但语义要干净）。
        if self.worker is not None:
            try:
                self.worker.reset_harvested()
            except Exception:
                pass
        recovered = 0            # 今天"换了一片地"的次数（本片拿不出目标时）
        # 【task-58】今天的边界决策（只记**真实 LLM 调用**的那些），日终连同结局一起进决策史。
        day_decisions: list[dict[str, Any]] = []
        # **一天的第一次决策必须是"跨日边界"**（用户 m01860：该由大模型先判断今天做什么）。
        # `detect_boundary` 判 new_day 的依据是"state 里的 day_key 与当前简报不同"，而且**两边都得
        # 非空**才比 —— 所以这里不能置 None，要放一个与真实日期必然不等的哨兵值。
        # 这一天之后的决策都不再是边界（0 次调用），除非失败计数上升或阶段切换。
        self.state.day_key = _DAY_START_SENTINEL
        # 【task-16 / 0.7.45】日初先取一次背包空格：醒在屋里时多半是 `unavailable`（不猜 0）；
        # 回到农场后 `_ensure_on_farm` 之后再取一次，那才是当天第一张**可用**读数。
        self._observe_free_slots(rep, obs)
        ess = self._essence(obs)
        self._say(f"[day] {rep.day_text} 开始：{ess['location']} 体力 {ess['stamina']} 钱 {ess['money']}g "
                  f"作物 {ess['crops']}（未浇 {ess['unwatered_crops']}）天气 {FarmWorker.weather(obs)}")
        self._journal("day_start", day=list(rep.day_key), timeOfDay=ess["timeOfDay"],
                      stamina=ess["stamina"], money=ess["money"], crops=ess["crops"],
                      unwatered=ess["unwatered_crops"], location=ess["location"],
                      weather=FarmWorker.weather(obs),
                      free_slots=rep.free_slots_last,
                      free_slots_status=rep.free_slots_status)

        # 【run3 真 bug：醒在屋里就再也不去农场】`_prepare()` 只在 `run()` 启动时回农场一次，
        # 之后每个游戏日都在 FarmHouse 醒来（run3：`final.location='FarmHouse'`、`tile=[9,9]`、
        # `isInBed=true`、`timeOfDay=600`），整天拿**室内窗口**当观测 ⇒ `work_reasons`/
        # `_ensure_plot` 全判"没活" ⇒ 连睡 4 天，`final_water` farm 口径还是 `dry=33/33`。
        # 所以每天第一张观测之后、进主循环之前必须先回农场；失败**不吞**（notes + journal）。
        obs = self._ensure_on_farm(obs, rep)
        # 【task-16】回农场后的第一张观测才算"当天开局空格"（室内窗口没有玩家背包字段口径）。
        self._observe_free_slots(rep, obs)
        # 【task-158】回到农场后的第一张观测就是"今天有多少活苗要浇、体力上限多少"的基准：
        # 算一次浇水优先预算并落 journal（`_stage_tiles` 的闸门会用**当轮**观测重算，
        # 这里这份是当天快照，日终进 `day_end.stamina_budget`）。
        self.budget_today = self._stamina_budget(obs)
        rep.stamina_budget = dict(self.budget_today)
        if not self.budget_noted:
            self.budget_noted = True
            self._journal("stamina_budget", **self.budget_today)
        # 【task-163】预算延后**在日初就落痕**：不能等 `_stage_tiles` 被调用才记。
        # run9d/day1 那种"策略给 `review`、守卫却一直说还有活"的日子里，
        # `_stage_tiles` 可能一整天都不会被叫到，于是延后永远记不上、守卫永远不闭嘴
        # ⇒ 3 轮零变化 ⇒ `stuck`（有界、不假绿，但白烧一天且当天不可能 VERIFIED）。
        self._note_budget_deferrals(obs)
        # 【task-168】跨日粘住的认输片区：日初懒加载一次，然后**判断能不能释放**
        # （该区已无未浇活苗 / 全农场缺口归零 ⇒ 撤销认输、重新进目标池）。判不了就不释放。
        self._scope_load()
        self._release_scope_if_converged(obs, rep)

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

            # **事件对话受控推进**（task-228）：只在 `eventUp=true` + `DialogueBox` +
            # 非提问时点一下（每次/每天都有界）；提问、职业选择、非对话事件一律不动，
            # 直接落到下面的模态守卫 ⇒ `event_blocked` 诚实收尾。
            obs = self._advance_event_dialogue(obs, rep)

            # **模态守卫**（task-11）：`LevelUpMenu`/存档模态会把时间冻住（`player.freezePause=100`），
            # 不先清掉的话后面所有技能都会被 `ui_modal` 拒绝、整天静默卡死。清到干净才谈决策。
            obs, modal_blocked = self._clear_modals(obs, rep)
            if modal_blocked:
                break

            # 【devcoder-spring1-event / Fix B】`eventUp=true` 期间**冻结一切日常动作**：事件
            # （尤其 skippable 过场，如 Kent 归来 eventId=63，command 6=pause/动画/视口自播、原版
            # 事件命令集无"等玩家走格"命令）不需玩家操作，结束条件=计时到/动画播完；在事件里
            # sell/buy/goto_farm/walk/plant/water/clear 会干扰过场、甚至替游戏改剧情状态（A9 spring1
            # 实证：eventUp 下仍跑了 sell/buy ⇒ 被误判 event_blocked）。所以只要观测到
            # `ui.eventUp=true`，本轮**绝不**跑任何经济/农事动作，只轮询等事件结束/对话盒出现：
            #   * `_wait_event_up` 返回 `still_blocked=True` ⇒ `_event_blocked` 诚实收尾；
            #   * 返回 `False`（事件结束或对话盒出现）⇒ 本轮不跑经济，`continue` 回循环顶部
            #     （对话盒交给 `_advance_event_dialogue` 受控推进：非提问才点、提问/职业选择不动）。
            # 判定只看观测 `ui.eventUp`，不读回执、绝不 dismiss/推进含提问的事件（task-41 红线）。
            if (obs.get("ui") or {}).get("eventUp") is True:
                obs, still_blocked, wait_tries = self._wait_event_up(obs)
                if still_blocked:
                    self._event_blocked(obs, rep, event_wait_tries=wait_tries)
                    break
                self._observe_free_slots(rep, obs)   # 事件结束/对话盒出现：刷新观测再回顶部
                continue

            # 【task-16 / 0.7.45】每次观测都重算背包空格（只记 trace，不发请求）：
            # `day_end.free_slots_*` / `loot_lost` 的证据都靠这张读数，不靠"事后猜"。
            self._observe_free_slots(rep, obs)

            # 【task-25 rev4 / 0.7.46】开工前先试买 Pierre 背包升级（对话购买）：
            # 只在「容量 12 且钱够 2000g」的当天走**一个**回合；成功/失败/跳过都只是 info，
            # 不改 `checks`/`day_justified`。失败时已由 helper 自己回农场，这里只需刷新观测。
            if self._maybe_buy_backpack_upgrade(obs, rep):
                obs = self._snap_or(obs)
                last_obs = obs
                self._observe_free_slots(rep, obs)
                continue

            allow, code, text = self.sleep_guard(obs)
            if allow:
                # 【devcoder-clear-gate D】满包清障闸的收口必须**点名**（`ended_by=clear_gate`）：
                # 它不是"没活"，也不是"背包堵住收不了熟作物"，而是"活被背包闸住、今天不开新清障"。
                # 走 `_end_clear_gate`（`require_work=False`：0 动作日照样能翻篇，理由同
                # `_stuck_flush`）。`clear_gate` 不在任何白名单 ⇒ `day_justified=False`。
                if code == "clear_gate":
                    self._end_clear_gate(obs, rep)
                    break
                rep.ended_by, rep.ended_reason = self._do_sleep(obs, rep, f"{code}:{text}")
                # 【task-198】背包堵住导致的收工与 night/stamina 同形态（睡一觉让游戏日翻篇），
                # 但 `ended_by` 必须点名**原因**：否则报告里只会看到 `sleep`，看报告的人分不清
                # "干完了" 和 "背包堵住收工"。`is_justified_end()` 不认它 ⇒ 当天不判 VERIFIED。
                if code == "inventory_blocked" and rep.ended_by == "sleep":
                    rep.ended_by = "inventory_blocked"
                    rep.ended_reason = f"inventory_blocked:{text}"
                break

            # 【task-198】背包满/将满 ⇒ **先腾格再收**（日级收敛回路，run A′ 的 45 条 harvest
            # 全卡在"背包满"上：守卫一直说"还有熟作物"、collect 又全被拒）。腾出格子后
            # `continue` 重新观测/决策；腾不出来时 `_slot_relief` 已置 `inventory_blocked_today`
            # 并记 journal，守卫下一轮就会用 `inventory_blocked` 如实收尾（不假 VERIFIED）。
            if self._slot_relief(obs, rep):
                # 【task-240b】腾格成功 ⇒ 重新取快照让后续 _preconditions 看见新空格，
                # 并**立刻尝试买种子**（腾格前 _preconditions 被 _slot_relief 的 continue 跳过，
                # 买种子因此永远不触发 —— catch-22）。修后：腾格→买种子→continue 重新观测。
                obs = self._snap_or(obs)
                last_obs = obs
                self._observe_free_slots(rep, obs)
                obs = self._preconditions(obs, rep)
                continue

            # 【task-143】`_preconditions` 会真的买种子 ⇒ 必须用它还回来的**改动后**观测继续
            # 本轮（`_ensure_plot`/`decide`/`_verify_intents` 都要看得见刚到手的那批种子，
            # 否则 `plant_area` 会被算成"没有可动目标"而当天封格）。
            obs = self._preconditions(obs, rep)
            # 【task-205】铁匠铺升级/取回：**每天最多一次**，放在"种子/腾格摆正"之后、
            # "开新地"之前。`_tool_upgrade_due` 决定"该不该去"：`upgrade` 要等紧急农活做完，
            # **`pickup` 一律放行**（【task-216 F3】在途工具不在身上，被它暂停的阶段本来就干不成）。
            # 【task-216 必修 4】这里**无条件调用**（不只 due 为真时）：`_maybe_tool_upgrade` 内部
            # 在 `due=False` 时也会按天留一条 `tool_upgrade_skipped{which,reason}`，否则 wait/
            # need_slot 日一条留痕都没有（docstring 与账本对不上，deputy 实测 0 条）。
            if self._maybe_tool_upgrade(obs, rep):
                continue
            # 【task-50】窗口外那 1 格干作物（run5 三天 `farm.dryCrops` 恒剩 1 的病灶）：
            # Mod 的 `farm.dryTiles` 给了坐标 ⇒ **走过去浇**，别因为它不在窗口里就判 `no_work`。
            # 每格每天最多 `FAR_DRY_MAX_TRIES` 次；两次都不成会进"认输"集合，之后
            # `_far_dry_tiles` 变空 ⇒ 守卫仍因 `farm.dryCrops>0` 不放行 ⇒ 当天以
            # `stuck:` 收尾并点名坐标（绝不洗成 `no_work`）。
            if self._water_far_dry(obs, rep):
                continue
            # 【task-199】窗口外的熟作物：`farm.readyTiles` 给了坐标 ⇒ 走过去收（复用同一套
            # walker/开路家族）。走不到就认输并在 `work_reasons`/`sleep_guard` 里闭嘴，
            # 绝不让"农场口径还有熟作物"变成"同一秒连发 5 次换片"的空转（run A′ fall 13）。
            if self._harvest_far_ready(obs, rep):
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
                # 【task-5 / 0.7.44】整片只剩"挡死格"（被围 / 回去看过没产出）⇒ 走卡 1 的
                # 换片/`resume_exhausted` 诚实收工，别再用窗口里"看起来有活"的假候选一轮轮重分
                # 同一个做不成的格（A8 冬 9/14 的 1 格阶段死循环就是这么把整天耗掉的）。
                if picked is None:
                    dead_pending = self._dead_end_pending()
                    near = self._near_player_plot(obs)
                    if dead_pending and (near is None
                                         or not self._plot_has_work(obs, near["tiles"])):
                        dead_plot = {"zone": "", "label": "", "area": "",
                                     "anchor": list(dead_pending[0]), "tiles": dead_pending,
                                     "note": "只剩挡死格（被围 / 回去看过没产出）"}
                        action, alt = self._resume_switch_or_exhaust(
                            obs, rep, plot=dead_plot, where="dead_only")
                        if action == "ended":
                            break
                        if action == "acted":
                            self.idle_rounds = 0
                            continue
                        if alt is not None:            # 防御性：dead-only 一般拿不出 alt
                            self.resume_walk_attempts += 1   # 【task-26】尝试计数（成功另记）
                            walked = self._walk_into_plot(obs, alt)
                            self._journal("resume_walk", zone=self.zone_name,
                                          tiles=len(alt["tiles"]), walked=bool(walked),
                                          attempt=self.resume_walk_attempts,
                                          walks=self.resume_walks, switched=True,
                                          note="只剩挡死格 ⇒ 换到另一片的账本待做格")
                            if walked:
                                self.resume_walks += 1
                                self._actions += 1
                                self.resume_last_anchor = self._resume_anchor(alt)
                                self.idle_rounds = 0
                                continue
                spot = picked or self._near_player_plot(obs)
                if spot is None:
                    reasons = self.work_reasons(obs)
                    rep.notes.append("找不到有活的作业区："
                                     + ("；".join(reasons) or "（守卫也说没活）"))
                    # 【task-68】Lead m06336③「一轮不许零动作」：守卫说有活、却没有任何作业区
                    # 拿得出目标时，只要农场里还有**可达的可清障格**（weed/stone/twig/grass）
                    # 就先清一格再继续（有界 `FRONTIER_CLEAR_MAX`/天）。run6 就是这么报废的：
                    # `field_ne` 的 42 格全够不着、而农场被数百个可清障物堵着，却直接收工。
                    if reasons and self._frontier_clear(obs, rep):
                        rep.notes.append(
                            f"没有作业区拿得出目标；先清一格可达的可清障格"
                            f"（frontier_clear {self.frontier_clears}/{FRONTIER_CLEAR_MAX}）")
                        self.idle_rounds = 0
                        continue
                    # 【task-198】背包堵住时**不能**落成 `no_work`（那是假达标）或 `stuck`
                    # （那是误报卡死）：这一天的真实结论是"背包堵住、今天腾不出来"。
                    # 【devcoder-clear-gate D】"剩余活全是被满包清障闸挡住的清障格" 同样不许落
                    # `no_work`/`stuck`：用 `_end_clear_gate` 点名收口（day_justified 恒 False）。
                    if self._clear_gate_only_work(obs):
                        self._end_clear_gate(obs, rep)
                        break
                    if self.inventory_blocked_today:
                        self._end_inventory_blocked(obs, rep)
                        break
                    # 【task-4 / 0.7.44】【task-15 / 0.7.45】回片区/换片/观测清障都用尽，
                    # 残留格全是"已停滞/被围住" ⇒ 今天真没有可执行目标：按 `resume_exhausted`
                    # 诚实收工，不许落到下面的 `stuck:守卫说还有活…`（那不是卡死，是"没活可执行"）。
                    # 判据用 `_dead_end_pending()` 的**原始账本**口径（守卫口径的 pending 已剔除
                    # 停滞/被围格，会是空集）。
                    if self._dead_end_pending():
                        self._resume_exhausted(obs, rep, plot=None,
                                               where="work_spot_none", marked=0)
                        break
                    why = ("no_work" if not reasons else
                           "stuck:守卫说还有活（" + "；".join(reasons)
                           + "）但没有任何作业区拿得出目标" + self._not_on_farm_suffix())
                    rep.ended_by, rep.ended_reason = self._do_sleep(obs, rep, why)
                    break
                plot = spot
                self._journal("work_spot", zone=self.zone_name, tiles=len(plot["tiles"]),
                              note=plot.get("note"))
                # 【task-49】`_resume_plot` 给的是**别处**的格子（玩家窗口看不到）⇒ 先走回去，
                # 让传感器重新看见它们再谈策略。上界见 `_resume_walk_available`
                # （成功 `resume_walks` 与尝试 `resume_walk_attempts` 分开封顶；与"换片地"
                # 同一个量级）；走不动就落回正常判定，不空转。
                # 【task-4 / 0.7.44】同一锚点连走第二遍 = 该邻域已经看过、仍然拿不出目标 ⇒
                # 先换到另一片的账本待做格，再尝试观测里可达的一格；都没有才按
                # `resume_exhausted` 诚实收工（绝不写 `stuck:回片区…`、绝不 VERIFIED）。
                # 【task-26 / 0.7.46】旧口径在走路**之前**就自增 `resume_walks`，失败尝试也烧
                # 成功预算（冬27：7 次 `walked:false` 把 10/10 提前烧光，t=845 的 7 格可执行
                # 余格一次都走不回去）⇒ 这里改用 `_resume_walk_available()`，且只在
                # `walked == True` 时给 `resume_walks` 记账。
                if work_spot is None and picked is plot and self._resume_walk_available():
                    self._resume_reevaluate(where="work_spot_resume")  # 【task-134 A】
                    anchor = self._resume_anchor(plot)
                    pt = FarmWorker.player_tile(obs)
                    # "同一锚点 + 人已经在它旁边" = 这片邻域已经走进传感器看过、仍拿不出目标。
                    # 只比锚点会把"几小时前走过、现在人还在别处"误判成重复 ⇒ 必须同时看距离。
                    repeated = (anchor is not None and anchor == self.resume_last_anchor
                                and (pt is None
                                     or _dist((int(pt[0]), int(pt[1])), anchor) <= OBSERVE_REACH))
                    self.resume_walk_attempts += 1
                    self.no_progress_cycles += 1                       # 【task-134 A】
                    switched = False
                    if repeated or self.no_progress_cycles >= PLOT_EXHAUSTED_BURST:
                        action, alt = self._resume_switch_or_exhaust(
                            obs, rep, plot=plot, where="work_spot_resume",
                            repeated=bool(repeated))
                        if action == "ended":
                            break
                        if action == "acted":
                            self.idle_rounds = 0
                            continue
                        plot = alt
                        switched = True
                    walked = self._walk_into_plot(obs, plot)
                    if walked:
                        # 只有真的走到了才算用掉一次"回去看过"的预算（task-26 口径）。
                        self.resume_walks += 1
                    self._journal("resume_walk", zone=self.zone_name, tiles=len(plot["tiles"]),
                                  walked=bool(walked), attempt=self.resume_walk_attempts,
                                  walks=self.resume_walks,
                                  switched=bool(switched),
                                  note=("回片区拿不出目标 ⇒ 换到另一片的待做格旁边再看一次"
                                        if switched else
                                        "回到今天还没做完的格子旁边（玩家窗口看不见它们）"))
                    if walked:
                        self._actions += 1
                        rep.notes.append(
                            f"回到没做完的 {len(plot['tiles'])} 格旁边再看一次"
                            f"（resume_walk 成功 {self.resume_walks}/{self.max_plots_per_day}，"
                            f"尝试 {self.resume_walk_attempts}/{2 * self.max_plots_per_day}"
                            + (f"，换片 {self.resume_switches}" if switched else "") + "）")
                        self.resume_last_anchor = self._resume_anchor(plot)
                        if switched:
                            self.no_progress_cycles = 0
                            self.idle_rounds = 0
                        continue

            brief = self._plot_brief(obs, plot)
            decision = self.planner.decide(self.state, brief)
            # 【task-219】先把"计划"记下来（`intent_id` 按对象身份缓存，执行侧复用同一个 id；
            # 不新增事件名，挂在既有 `decision` 行的 `plans` 字段里）。
            plans = self._plan_intents(decision)
            self._journal("decision", day=list(rep.day_key), boundary=decision.boundary,
                          source=decision.source, llm=decision.llm_called,
                          intents=[i.as_dict() for i in decision.intents],
                          plans=plans,
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
            # 【task-58】这一刻的"边界决策"（只有真实 LLM 调用才算）先攒着，日终才配结局。
            # 放在 `_apply_policy`/校验关口**之前**：这里记的才是模型自己交出来的意图。
            llm_decision = (bool(getattr(decision, "llm_called", False)),
                            str(getattr(decision, "boundary", "") or ""),
                            list(decision.intents))
            decision, policy_note = self._apply_policy(decision, obs)
            if policy_note:
                self._journal("policy", note=policy_note,
                              intents=[i.task for i in decision.intents])
            # 【task-219】政策层可能补出**新的**意图对象（must 意图）；补记它们的计划，
            # 保证每条意图都有 `intent_id` + `source/boundary`（已有 id 的对象不会重复记）。
            self._plan_intents(decision)
            # **校验关口**（用户 m02591）：能继续就继续，做不了就取消，全取消才谈收工
            kept, verdicts = self._verify_intents(decision.intents, obs, plot)
            if verdicts:
                self._journal("intent_verdict", zone=self.zone_name, verdicts=verdicts)
            # 【task-219 / task-230 P0-3.3】被校验取消/判不准的意图也要留执行对账：
            # cancel ⇒ `no_target`（**必须带证据**：`stage_tiles_empty` + obs_seq/counts）；
            # 证据拿不到 ⇒ 降级 `unknown_evidence`（禁止裸用 no_target 冒充"确实没有目标"）；
            # unknown ⇒ `unknown_evidence`（判不准本身就是要暴露的证明不足）。
            for v in verdicts:
                verdict = str(v.get("verdict") or "")
                if verdict not in ("cancel", "unknown"):
                    continue
                reason = "no_target" if verdict == "cancel" else "unknown_evidence"
                evidence: dict[str, Any] | None = None
                if reason == "no_target":
                    evidence = self._no_target_evidence(str(v.get("task") or ""), obs, plot)
                    if evidence is None:
                        reason = "unknown_evidence"   # 证据不可用 ⇒ 不许说"没目标"
                if reason == "unknown_evidence" and evidence is None:
                    # 【task-233】§8.2b：降级也要写清**为什么**判不了，并带上该任务
                    # 自己的可判证据（非片区任务没有 `stage_tiles_empty` 这套 schema）。
                    task_name = str(v.get("task") or "")
                    why = ("non_plot_task" if task_name in NON_PLOT_INTENT_TASKS
                           else ("no_plot" if plot is None else "obs_unavailable"))
                    non_plot = self._non_plot_evidence(task_name, obs)
                    evidence = {"unknown_why": why}
                    if non_plot is not None:
                        evidence.update(non_plot)
                self._record_intent(intent_id=str(v.get("intent_id") or ""),
                                    task=str(v.get("task") or ""),
                                    reasons={reason: 1}, evidence=evidence,
                                    note=str(v.get("reason") or ""))
            if llm_decision[0]:
                counts = {"keep": 0, "unknown": 0, "cancel": 0}
                for _v in verdicts:
                    key = str(_v.get("verdict") or "")
                    counts[key] = counts.get(key, 0) + 1
                day_decisions.append({"boundary": llm_decision[1],
                                      "intents": llm_decision[2],
                                      "verdicts": counts})
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
            # 【task-124】`review` 独苗不许白过一轮（Lead m11194）：`_verify_intents` 对非阶段
            # 意图直接放行、`review` 又不置 `acted` ⇒ 每轮零变化 ⇒ 3 轮 idle 判 stuck（run9
            # 第 1/2 天）。守卫说还有活时，改用**守卫据以抱怨的那份 leftover / 观测里看得见的
            # 收尾活**去挑目标；挑不出来就把那批 leftover 如实记为今天放弃（次日重试）。
            # `work_reasons()` 为空时 `review` 语义一个字不改。
            if (self._is_review_only(decision) and self.work_reasons(obs)
                    and (self._work_spot_plot(obs) is not None or self._pending_work())):
                forced, walked = self._review_only_fallback(obs, rep)
                if rep.ended_by:
                    # 【task-134 A】里面已按"连续空转触顶"写好了诚实收尾（`stuck:`）
                    break
                if walked:
                    continue
                if forced is not None:
                    decision = forced
                else:
                    # ②兜底也拿不出目标 ⇒ 把那份 leftover 如实记为**今天放弃**（次日重试），
                    #   并先走既有的"一轮不许零动作"（世界里还有可达的可清障格就至少清一格）；
                    #   连它都没有才落回既有诚实收尾（`sleep_guard`/换片/`stuck`）。
                    self._abandon_guard_leftover(obs, rep)
                    if self._frontier_clear(obs, rep):
                        rep.notes.append(
                            f"只有 review 且兜底没目标 ⇒ 先清一格可达的可清障格"
                            f"（frontier_clear {self.frontier_clears}/{FRONTIER_CLEAR_MAX}）")
                        self.idle_rounds = 0
                        continue
                    # ③连"清一格"都没有 ⇒ 立刻如实收尾（不落回 `sleep_guard` 的 `no_work`，
                    #   那会把"守卫说有活却指不出格"洗成"今天没活"）。`_do_sleep` 里
                    #   `require_work` 会再挡一道：0 农场动作的日子连睡都不许睡。
                    rep.notes.append("确定性计划也没有目标 ⇒ 按 stuck 诚实收尾（不走 3 轮 idle 弯路）")
                    rep.ended_by, rep.ended_reason = self._do_sleep(
                        obs, rep,
                        "stuck:确定性计划也没有目标（守卫说还有活，但既换不出意图、也无可达的可清障格）"
                        + self._not_on_farm_suffix())
                    break
            if not decision.intents:
                # ②确定性策略也挑不出事来。⚠️ 这**不等于"今天没活了"**（用户 m02532 当场抓到：
                #   体力 204/270、才 19:40，却掉头回家准备睡觉）。能不能收工只有 `sleep_guard`
                #   说了算：守卫不放行就说明别处还有活 ⇒ 忘掉本片的记账、换一片地接着干。
                allow, code, text = self.sleep_guard(obs)
                if not allow:
                    # 【task-49 主修】守卫说还有活，而**本片**拿不出意图 ⇒ 先用"今天还没做完的
                    #   格子"（可能整片都在玩家窗口之外）回头看一眼，而不是直接换片地/攒 recovered。
                    #   run5 第 1 天：field_nw 还剩 9 格未开垦，人站在 field_se 就以为"没活"。
                    # 【task-11 / 0.7.44】连续无产出触顶时统一路由到卡 1 的
                    # `_resume_switch_or_exhaust`（换片 → 观测清一格 → `resume_exhausted:` 诚实
                    # 收工），不再直接 `_no_progress_stop(stuck:)`（deputy GAP-2）。
                    action, _walked = self._guard_leftover_resume(obs, rep, text=text)
                    if action == "ended":
                        break
                    if action == "acted":
                        self.idle_rounds = 0
                        self._guard_walk_streak = 0
                        self._no_work_cycle_count = 0      # 这轮真做了农场动作 ⇒ 无活计数清零
                        continue
                    if action == "walked":
                        # 【devcoder-no-work-sleep】连续"LLM 意图 + 确定性兜底都无可执行目标、
                        # 且当日 0 农场动作"的轮次计数：已用校验证据*证明*无活，不必等
                        # `_guard_walk_streak>=10`（更不必等到被外部杀掉），直接诚实收工、干净跨日。
                        # 阈值 3 远小于 walk_streak 的 10：LLM 重试挂起会在进程被外部杀掉之前就收敛。
                        self._no_work_cycle_count += 1
                        if self._no_work_cycle_count >= 3:
                            if self.farm_actions_today <= 0:
                                # 【A9 gatefix3 实证】本轮"3 轮校验取消"只是**本片区**看得见没目标；
                                # 账本里可能还有别的片区的可执行活（winter27/28 实测 exec=237/240）。
                                # 硬收工会把"还有活"洗成"没活"（zero_action_evidenced 会正确拦住）。
                                # 只有**日终可执行面证据 executable==0** 才算真无活、才收工；
                                # 否则**不结束**，落到下面的走路上限继续换片探索（winter26 就是这样
                                # 走 216 格/换片 4 次后 exec=0 才 VERIFIED 的）。
                                try:
                                    _snap = self._pending_snapshot(obs)
                                    _exec = int(_snap.get("executable") or 0)
                                    _gated = int(_snap.get("gated") or 0)
                                except Exception:
                                    _exec, _gated = 1, 0   # 证据不可用 ⇒ fail-closed 当作"还有活"
                                # 【devcoder-clear-gate D】`executable==0` 也可能是"格全被满包清障闸
                                # 闸住"（gated>0）—— 那是"活被背包闸住"，**不是**无活可做：绝不许
                                # 落 `no_work`+`no_work_evidence_ok=True`（那是白拿 VERIFIED 的洗白口）。
                                if _exec == 0 and _gated > 0 and self._clear_gate_only_work(obs):
                                    self._end_clear_gate(obs, rep)
                                    break
                                if _exec == 0 and _gated == 0:
                                    rep.notes.append(
                                        f"连续 {self._no_work_cycle_count} 轮校验取消、当日 0 农场动作、"
                                        f"且日终可执行面 executable==0 ⇒ 已证无活，诚实收工（干净跨日）")
                                    # `no_work_evidence_ok` = `_zero_action_evidenced` 的唯一放行口
                                    # （与 sleep_guard:5911 同义）；已在 executable==0 前提下，诚实。
                                    self.no_work_evidence_ok = True
                                    rep.ended_by, rep.ended_reason = self._do_sleep(
                                        obs, rep,
                                        f"no_work:连续{self._no_work_cycle_count}轮校验取消、当日0可执行农场动作"
                                        f"（已证无活，非跳过）",
                                        require_work=False)
                                    break
                                # exec>0：账本还有可执行的活 ⇒ 不判无活，继续换片/探索
                                rep.notes.append(
                                    f"连续 {self._no_work_cycle_count} 轮本片区无可动目标，但账本仍有 "
                                    f"{_exec} 格可执行（另有 {_gated} 格被满包清障闸闸住）⇒ 不判无活，"
                                    f"继续换片探索（不提前收工）")
                            # 当天其实做过农场动作（只是做不成/被围）⇒ 不是"当日 0 可执行农场动作"，
                            # 绝不许洗成 no_work（那是把"有活做不成"洗白成"没活"）；落回既有
                            # stuck / burst / resume_exhausted 诚实收口（见
                            # `test_persistent_unfinishable_work_is_bounded_and_never_no_work`）。
                        # 【liveness 修复】连续走路无进展硬上限：守卫说还有活、但反复走回 leftovers
                        # 仍拿不出可执行目标 ⇒ 不再无限 continue，强制 honest sleep 让游戏日推进，
                        # 避免 winter26 这类"全部 encircled"场景整天空转。
                        self._guard_walk_streak = getattr(self, "_guard_walk_streak", 0) + 1
                        if self._guard_walk_streak >= 10:
                            # 【devcoder-no-work-sleep】当日 0 农场动作时同样走 `no_work` 诚实口径
                            # （require_work=False），避免 `_do_sleep` 默认 `require_work=True` 在
                            # `_unfinished_work` 仍为真时返回 `slept_without_work` ⇒ 不跨日、整轮自停。
                            # 【A9 gatefix3】`no_work`（正当、可 VERIFIED）只在**当日 0 动作 _且_
                            # 日终可执行面 executable==0** 时成立；只满足前半（账本还有可执行活，
                            # 只是走不到/被围）⇒ 落 `stuck:` 诚实收口（不洗成无活、当天不 VERIFIED）。
                            try:
                                _snap2 = self._pending_snapshot(obs)
                                _no_exec = int(_snap2.get("executable") or 0) == 0
                                _gated2 = int(_snap2.get("gated") or 0)
                            except Exception:
                                _no_exec, _gated2 = False, 0
                            # 【devcoder-clear-gate D】`executable==0 且 gated>0` = "活被满包闸住"，
                            # 不是"没活"：走 `clear_gate` 点名收口（day_justified 恒 False），
                            # 绝不许置 `no_work_evidence_ok` 拿一个假 VERIFIED。
                            if _no_exec and _gated2 > 0 and self._clear_gate_only_work(obs):
                                self._end_clear_gate(obs, rep)
                                break
                            no_work = self.farm_actions_today <= 0 and _no_exec and _gated2 == 0
                            if no_work:
                                self.no_work_evidence_ok = True
                            rep.ended_by, rep.ended_reason = self._do_sleep(
                                obs, rep,
                                ("no_work:连续走路无进展（encircled/unreachable，已证无可达可执行目标）"
                                 if no_work else
                                 "stuck:连续走路无进展（encircled/unreachable 目标）"),
                                require_work=not no_work)
                            break
                        continue
                    recovered += 1
                    self.plot_exhausted_today += 1     # 【task-122】当日计数（喂当晚教训）
                    self._journal("plot_exhausted", recovered=recovered, zone=self.zone_name,
                                  note=f"这一片没目标了，但守卫仍要求干活（{text}）⇒ 换一片地")
                    # 【task-124】同一秒连发换片 = 纯空转（run9 第 2 天 0.6 秒 12 次）：
                    # 到阈值就记一条 `plot_exhausted_burst`、按既有有界机制结束当天换片循环。
                    burst = self._plot_exhausted_burst()
                    if burst >= PLOT_EXHAUSTED_BURST:
                        rep.notes.append(
                            f"同一秒内连发 {burst} 次换片 ⇒ 判定「本片真没目标」，结束今天的换片循环")
                        self._journal("plot_exhausted_burst", count=burst, zone=self.zone_name,
                                      note="同一秒内连发换片（run9 形态：0.6 秒 12 次）⇒ 不再把"
                                           "整天耗在无目的换片上，按既有有界机制收尾")
                        # 【task-15 / 0.7.45】有界 ≠ 可放行：收尾**不再写 `stuck:`** 掩盖。
                        # 按可执行面证据收口（`_resume_exhausted` 会记 `no_progress_burst`
                        # `exhausted=True` + pending_* 证据）：观测里真没可执行格 ⇒ day_justified
                        # 可认；还有可执行格却收工 ⇒ 前缀照旧不在证据白名单里 ⇒ 当天不 VERIFIED。
                        self._resume_exhausted(
                            obs, rep, plot=self._resume_plot(obs),
                            where="plot_exhausted_burst")
                        break
                    if recovered > self.max_plots_per_day:
                        rep.notes.append(f"换过 {recovered} 片地都拿不出目标")
                        # 【task-15 / 0.7.45】换片次数有界用尽同样是"有界收工"，不再写
                        # `stuck:`（"有界≠可放行"：`day_justified` 由可执行面证据决定）。
                        self._resume_exhausted(
                            obs, rep, plot=self._resume_plot(obs),
                            where="switch_limit")
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
                # 【devcoder-clear-gate D】这里**不许硬写 `no_work`**：守卫这次放行可能是
                # `clear_gate`（满包清障闸，剩余活全是被闸住的清障格）或 `inventory_blocked`
                # （背包堵住）—— 写 `no_work` 会把"活被背包闸住"洗成"今天没活"（`no_work` 在
                # JUSTIFIED 白名单里 ⇒ 白拿 VERIFIED）。按 `code` 分流，各走自己的点名收尾口。
                if code == "clear_gate":
                    self._end_clear_gate(obs, rep)
                    break
                if code == "inventory_blocked" and self.inventory_blocked_today:
                    self._end_inventory_blocked(obs, rep)
                    break
                # 其余 code（night/stamina/no_work…）沿用旧行为：`no_work` 由 sleep_guard 的
                # 证据保证（`no_work_evidence_ok` 只在"真没活"分支置位），不受本次改动影响。
                rep.ended_by, rep.ended_reason = self._do_sleep(obs, rep, "no_work")
                break
            # 【task-219】政策/换任务/兜底之后仍没进执行的计划意图：日终按 `superseded` 归因
            # （"被政策改写/被更具体意图替代"），绝不因为没记就消失。
            kept_ids = {self._intent_id(i) for i in decision.intents}
            self.intent_superseded |= {p["intent_id"] for p in plans
                                       if p["intent_id"] not in kept_ids}
            acted = self._execute(decision, obs, plot, rep)
            if rep.ended_by:
                break
            after = self._snap()
            changed = self._fingerprint(after) != self._fingerprint(obs)
            obs = after
            if acted and changed:
                self.idle_rounds = 0
                self.no_progress_cycles = 0      # 【task-134 A】真有进展 ⇒ 空转计数清零
                self._guard_walk_streak = 0
                self._no_work_cycle_count = 0   # 这轮真有农场动作 ⇒ 无活计数清零
            elif changed:
                # 意图没落地（比如被否决），但世界确实变了 —— 也算有进展
                self.idle_rounds = 0
                self.no_progress_cycles = 0      # 【task-134 A】
                self._guard_walk_streak = 0
                self._no_work_cycle_count = 0   # 世界确有变化 ⇒ 无活计数清零
            else:
                self.idle_rounds += 1
                self._journal("idle", rounds=self.idle_rounds, zone=self.zone_name,
                              intents=[i.task for i in decision.intents], acted=acted)
                if self.idle_rounds >= 3:
                    # 【task-198 ③】背包堵住导致的"零变化"**不是 stuck**：`_slot_relief` 每轮只
                    # 腾 1 格、多格熟作物要好几轮 ⇒ 3 轮 idle 会先撞这里，把"背包堵住"误报成
                    # `stuck`（deputy 的 198f-1..8 全是这个形态，A′ day13 原型）。先判
                    # `inventory_blocked_today`：诚实收工、理由可执行、不算 hard failure。
                    # 【devcoder-clear-gate D】"剩余活全是清障类、且背包 0 空格腾不出" ⇒ 更准确的
                    # 结论是 `clear_gate`（不是背包堵住收不了熟作物、也不是 stuck）：A9 冬 27/28
                    # 就是在这个口上被判 `stuck:` 的。放在 inventory_blocked 之前（闸更具体）。
                    if self._clear_gate_only_work(obs):
                        self._end_clear_gate(obs, rep)
                        break
                    if self.inventory_blocked_today:
                        self._end_inventory_blocked(obs, rep)
                        break
                    # 【task-50】文案里补上"守卫为什么还说要干活"的**活证据**（含窗口外
                    # 干作物的坐标）。决策逻辑一个字没动，只是让 `ended_reason` 能点名到底
                    # 卡在哪一格 —— 卡面硬要求"干格不可达 ⇒ 当天 `stuck:` 且含坐标"。
                    still = self.work_reasons(obs)
                    why = ("；守卫仍说还有活：" + "；".join(still)) if still else ""
                    # 【task-68】"一轮不许零动作"：世界确实没变，但只要还有**可达的可清障格**
                    # 就先清一格（有界 20/天）—— 不能因为"当前阶段目标够不着"就整天报废。
                    if self._frontier_clear(obs, rep):
                        rep.notes.append(
                            f"目标都够不着/被围住，先清一格可达的可清障格"
                            f"（frontier_clear {self.frontier_clears}/{FRONTIER_CLEAR_MAX}）")
                        self.idle_rounds = 0
                        continue
                    rep.ended_by, rep.ended_reason = "stuck", (
                        f"stuck:连续 {self.idle_rounds} 轮世界没有任何变化（最后意图："
                        f"{[i.task for i in decision.intents]}；策略说有进展：{acted}）{why}"
                        + self._not_on_farm_suffix())
                    # 【task-73】不再直接让外层 break：先试一晚**有界翻篇**（睡过去、让整轮继续
                    # 跑下一天 —— run6 就是在这里 19 秒 `no_day_progress` 终止的）。`ended_by`
                    # 保持 `stuck`：这一天仍如实算失败，只是游戏日往前走了一格。
                    self._stuck_flush(obs, rep, rep.ended_reason)
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
        #   * 上界 = `max(5, floor(0.2 × bound_basis))`；`unreachable` 计数在这个界内
        #     才不影响 `verified`，超了照实 needs_review（`unreachable_within_bound` 判据）；
        #   * **同一豁免也要作用到 `no_unmet_stages`**：把已判"走不到"、且还留在 leftover 里的
        #     格子从日级剩余里扣掉（否则 run5 那种"最后一个阶段轮次刚好以不可达格子收尾"会把
        #     高产的一天判死）。扣的是**逐格坐标可查**的：每个不可达格都有 `unreachable` journal
        #     （`_mark_blocked`）+ 阶段级 `unreachable_stage`/账本 `unreachable_tiles`。
        #   * 防洗白：**全部目标不可达且当天 0 成功动作** ⇒ `no_unmet_stages` 仍为 False
        #     （下面的 `made_any_progress` 合取项），不许靠豁免把真空日洗成达标。
        # 【task-68】把"被围住"从**分子**里剔出去（卡面三方向里的 ③"单列 `encircled`"）：
        #   * run6 的 42 格里，真"寻路到不了"与"被树/石围着开不了路"混在一起；现在后者归 `encircled`
        #     （不封格、不计入 `unreachable`、不进豁免分子，只单独留痕 + 日级 `encircled_summary`）。
        #   * `engaged`（真的站到过目标格旁边的步数）逐阶段入账 + 进 `unreachable_summary`，
        #     作为"这 42 格里有多少压根没走到跟前"的**证据**，不参与判定。
        # 【task-78 NIT-1】上界**分母**从 `attempted` 换成 `bound_basis`
        # （= `sum(1 for s in all_steps if s.attempted and not s.encircled)`）：
        #   * 洗白通道（deputy 伪造账本 V5）：800 次 `encircled` 曾把 `attempted` 抬到 4000 ⇒
        #     上界 800 ⇒ 200 格真不可达被豁免、当天 VERIFIED、exit 0。`encircled` 既不是"走不到"
        #     也不是"干了没成"，没有资格抬高豁免上界。
        #   * 选"从分母剔除"而不是"新硬闸门"：方向 fail-closed（只让豁免更难），不引入新失败模式。
        #   * `attempted` **语义一字不动**（仍是发起过的步数 = 原始证据），只是不再当分母；
        #     `day_end`/`unreachable_summary`/`refused_summary` 都新增 `bound_basis` 字段。
        attempted_steps = sum(int(s.get("attempted") or 0) for s in rep.stages)
        bound_basis_steps = sum(int(s.get("bound_basis") or 0) for s in rep.stages)
        engaged_steps = sum(int(s.get("engaged") or 0) for s in rep.stages)
        rep.bound_basis = bound_basis_steps
        unreachable_bound = max(5, int(0.2 * bound_basis_steps))
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
        # 【devcoder-day-end-gates / Fix 1】"被围住"的日级**逐格证据**集合提前算好（豁免要用）：
        # `enc_day` = 各阶段 `encircled_tiles` ∪ 当天 `self.encircled_day`；
        # `prefiltered_day` = 其中"目标池前置过滤判死、0 次尝试、没有 step"的那些（task-27）——
        # 它们不进 `assigned` ⇒ 也不进 `assigned_undone`，扣豁免时先剔掉（双保险，fail-closed）。
        enc_day: set[tuple[int, int]] = set(self.encircled_day)
        prefiltered_day: set[tuple[int, int]] = set()
        for s in rep.stages:
            for t in (s.get("encircled_tiles") or []):
                try:
                    enc_day.add((int(t[0]), int(t[1])))
                except (TypeError, ValueError, IndexError):
                    continue
            for t in (s.get("encircled_prefiltered_tiles") or []):
                try:
                    prefiltered_day.add((int(t[0]), int(t[1])))
                except (TypeError, ValueError, IndexError):
                    continue
        rep.encircled = len(enc_day)
        rep.encircled_tiles = [list(t) for t in sorted(enc_day)]
        # 与 `unreachable_bound`/`refused_bound` **同一基数、同一公式**（fail-closed：被围住不能
        # 抬高上界，`bound_basis` 早已把 encircled 步从分母剔掉）。
        encircled_bound = max(5, int(0.2 * bound_basis_steps))
        rep.encircled_bound = encircled_bound
        # 【task-134 B】`plot_pending` = 改判据**之前**的 `raw_unmet` 口径（`_leftover` 逐 kind 求和）：
        # "片区里还剩多少格该做没做"。**数值必须逐字一致**（守卫/换片/resume 与工具侧都对它）。
        # `no_unmet_stages` 从此不再由它直接决定（见下面的 `assigned_unmet`）——
        # run9b 的假红就是"分配 12 格做完了 12 格、整片地还剩 12 格"被算成没做完。
        plot_pending_by_kind = {str(name): int(s.get("leftover") or 0)
                                for name, s in last_by_stage.items()
                                if int(s.get("tiles") or 0) > 0}
        raw_unmet = sum(plot_pending_by_kind.values())
        rep.plot_pending = raw_unmet
        rep.plot_pending_by_kind = plot_pending_by_kind
        # 【task-5 / 0.7.44】把 `plot_pending` 拆成"可执行余格 vs 物理挡死格"两个**只作 info** 的数
        # （取自每个阶段种类最后一条记录的 `leftover_executable`/`leftover_blocked`）。
        # 和恒等于 `plot_pending`；`checks`/豁免/`no_unmet_stages` 一个字不看它们。
        rep.plot_pending_executable = sum(
            int(s.get("leftover_executable") or 0) for s in last_by_stage.values()
            if int(s.get("tiles") or 0) > 0)
        rep.plot_pending_blocked = sum(
            int(s.get("leftover_blocked") or 0) for s in last_by_stage.values()
            if int(s.get("tiles") or 0) > 0)
        # 【task-158】日终把预算快照落到 `day_end`（含当天"因预算推迟"的记录）：
        # 它**只**用于解释"为什么有些没浇完/没种上"，绝不参与 `checks`。
        if self.budget_today:
            rep.stamina_budget = dict(self.budget_today)
        # 【task-161】日终把"每条 stage 的实测体力"按 stage 聚合（只留痕，不进 checks）：
        # 下一次真机 run 之后用它标定 `farmwork.py` 的 `STAMINA_COST_*` 估算常量。
        rep.stamina_calibration = self._stamina_calibration(rep)
        # 【devcoder-day-end-gates / Fix 2】`unreach_in_last` 只剩**老账本回退口径**的作用：
        # 它只数"最后一条阶段记录"里的 `unreachable_leftover`，而 A9 winter 26 的形态是
        # "6 格真不可达在前几条记录里就解掉了、最后一条 leftover=0" ⇒ 这个数变成 0 ⇒ 豁免
        # 一格都扣不掉（`unreachable_summary count=6 bound=22 exempted=0`）。新主口径见
        # `assigned_unmet` 循环之后的"日级逐格求交"。
        unreach_in_last = sum(int(s.get("unreachable_leftover") or 0) for s in last_by_stage.values()
                              if int(s.get("tiles") or 0) > 0)
        # 【task-63】被**游戏拒绝**（`tool_ineffective`/`precondition_failed`）：与"走不到"同形态
        # 但**独立起界**（`refused_bound = max(5, floor(0.2 × bound_basis))`，与不可达侧同一基数）：
        #   * 界内 ⇒ 从 `no_unmet_stages` 里扣掉"仍留在 leftover 的拒绝格"（否则 run5 那种
        #     "目标池落进几格不可锄的地"会把做了 100+ 步的一天判死）；
        #   * 超界 ⇒ 照实 `no_hard_failures=false`（`refused_within_bound` 判据）—— 不许靠
        #     "游戏全拒绝"换来一个 verified；
        #   * 两套豁免**各自扣减、互不覆盖**（拒绝格与不可达格是两批坐标、两套集合）。
        refused_bound = max(5, int(0.2 * bound_basis_steps))
        refused_day: set[tuple[int, int]] = set(self.refused_day)
        for s in rep.stages:
            for t in (s.get("refused_tiles") or []):
                try:
                    refused_day.add((int(t[0]), int(t[1])))
                except (TypeError, ValueError, IndexError):
                    continue
        rep.refused = len(refused_day)
        rep.refused_tiles = [list(t) for t in sorted(refused_day)]
        rep.refused_bound = refused_bound
        refused_in_last = sum(int(s.get("refused_leftover") or 0) for s in last_by_stage.values()
                              if int(s.get("tiles") or 0) > 0)
        refused_exempt = min(refused_bound, refused_in_last)
        rep.refused_exempt = refused_exempt
        # 【task-134 B】日级"没做完"改看**分配额** `assigned_undone`（分配格 − 做成/按规跳过），
        # 不再直接看片区 leftover。诚实上限（体力用尽 `stamina`、夜里收工、`budget` 且分配额
        # 已做完）留下的片区待办只记 `deferred_tiles`(info)：那是"今天该收工了"，不是"没做完
        # 还硬说达标"。**豁免结构与 `bound_basis` 分母一字未动**（下面只把基数换成 assigned_unmet）。
        night_end = str(rep.ended_reason or "").startswith("night")
        assigned_unmet = 0
        deferred_tiles = 0
        honest_stages: list[dict] = []
        shortfall_stages: list[dict] = []
        shortfall_recs: list[dict] = []
        for name, s in last_by_stage.items():
            if int(s.get("tiles") or 0) <= 0:
                continue
            undone = int(s.get("assigned_undone") or 0)
            stopped = str(s.get("stopped") or "")
            honest = (stopped == "stamina"
                      or (stopped == "budget" and undone == 0)
                      # 【task-144】夜里收工留下的"分配没做完"是真收工（deferred），不是洗白；
                      # `incomplete`/`need_refill`/`unreachable` 等如实原因**不在**这里 ⇒ 照旧 unmet。
                      or (night_end and stopped in ("", "incomplete")))
            if honest:
                deferred_tiles += int(s.get("leftover") or 0)
                if int(s.get("leftover") or 0) > 0:
                    honest_stages.append({"stage": name, "stopped": stopped,
                                          "leftover": int(s.get("leftover") or 0),
                                          "assigned_undone": undone})
            elif undone > 0:
                assigned_unmet += undone
                shortfall_recs.append(s)
                shortfall_stages.append({"stage": name, "stopped": stopped, "undone": undone,
                                         "assigned": int(s.get("assigned") or 0),
                                         "leftover": int(s.get("leftover") or 0)})
        # 【devcoder-day-end-gates / Fix 1 + Fix 2】豁免分子的新口径：**日级逐格求交**。
        #
        # 旧口径的两个洞（真机 A9 实证，均为"诚实做不成却被判红"）：
        #   * Fix 1（winter 27）：扣的只有 `*_leftover`（"还留在 leftover 里的格数"）。那天
        #     clear_area `assigned=16 / 12 做成 / 4 被围住 / leftover=0` ⇒ `encircled_leftover=0`
        #     ⇒ 4 格已证围死却一格都扣不掉 ⇒ `no_unmet_stages=False`。
        #   * Fix 2（winter 26）：`unreach_in_last` 只取"每个阶段种类的**最后一条**记录"，而 6 格
        #     不可达在前几条记录里就已解掉、最后一条 `leftover=0` ⇒ 豁免归零（exempted=0）。
        #
        # 新口径：`short_undone` = **当天所有"如实 shortfall"阶段**（非体力/夜里收工那类）最后一条
        # 记录里的 `assigned_undone` **逐格坐标**之并 —— 它与日级证据集合求交，只扣"既已被证明
        # 走不到/被围死、又确实还欠着"的格：
        #   * 已做成的格不会出现在 `assigned_undone` 里 ⇒ 不可能被拿来洗白别的格；
        #   * 诚实上限（体力/夜里收工）留下的格**根本不在** `short_undone` 里 ⇒ 不许拿去抵别人的
        #     欠账（这是"只按计数扣"最容易漏的洗白通道）；
        #   * `encircled` 侧**不**再剔 `encircled_prefiltered`：`short_undone` 只含"被分配且没做成"
        #     的格，预过滤格若真没进 assigned 就根本不在 `short_undone` 里（求交天然排掉）；
        #     而 A9 winter27 实测 stage 记录 `assigned=15` **已经包含**那 3 格预过滤格
        #     （`assigned_undone_tiles` 与 `encircled_prefiltered_tiles` 是同一批 [35,24]/[35,25]/
        #     [36,24]）⇒ 再剔一次会把"已证围死且确实欠着"的格归零（旧 `enc_evidenced=0` 的根因）；
        #   * 两侧各自按 `max(5, floor(0.2 × bound_basis))` 封顶，且**互不覆盖**（两套集合、两套界）；
        #   * `bound_basis` 分母一个字没动（fail-closed：豁免只会更难，不会更容易）。
        # 老账本（阶段记录里没有 `assigned_undone_tiles` 键）⇒ 逐条退回旧口径，行为与改前一致。
        short_undone: set[tuple[int, int]] = set()
        short_undone_legacy = False
        for rec in shortfall_recs:
            coords = rec.get("assigned_undone_tiles")
            if coords is None:
                short_undone_legacy = True
                continue
            for t in coords:
                try:
                    short_undone.add((int(t[0]), int(t[1])))
                except (TypeError, ValueError, IndexError):
                    continue
        if short_undone_legacy:
            unreach_evidenced = unreach_in_last
            enc_evidenced = sum(int(s.get("encircled_leftover") or 0)
                                for s in last_by_stage.values() if int(s.get("tiles") or 0) > 0)
        else:
            unreach_evidenced = len(unreach_day & short_undone)
            # 【Fix1 修正】不剔 prefiltered_day：short_undone 只含"被分配且没做成"的格，预过滤格若
            # 真没进 assigned 就不在 short_undone 里（求交天然排掉）；A9 winter27 实测 prefiltered
            # 那 3 格同时也在 assigned_undone_tiles 里 ⇒ 剔掉会把 encircled_exempt 归零、误判红。
            enc_evidenced = len(enc_day & short_undone)
        unreachable_exempt = min(unreachable_bound, unreach_evidenced)
        rep.unreachable_exempt = unreachable_exempt
        encircled_exempt = min(encircled_bound, enc_evidenced)
        rep.encircled_exempt = encircled_exempt
        # 三套豁免各自独立、互不覆盖：合计也不许超过"真的欠着"的格数（防同一格被两套同时扣）。
        exempt_total = min(assigned_unmet, unreachable_exempt + refused_exempt + encircled_exempt)
        unmet_leftover = max(0, assigned_unmet - exempt_total)
        rep.assigned_undone = assigned_unmet
        rep.deferred_tiles = deferred_tiles
        if shortfall_stages:
            self._journal("stage_shortfall_day", unmet=assigned_unmet, stages=shortfall_stages[:6],
                          plot_pending=raw_unmet, stopped_night=bool(night_end),
                          unreachable_exempt=unreachable_exempt,
                          refused_exempt=refused_exempt,
                          encircled_exempt=encircled_exempt,
                          unmet_after_exempt=unmet_leftover,
                          undone_tiles=[list(t) for t in sorted(short_undone)[:24]],
                          note="阶段分下去的格没做完（非诚实上限）⇒ 当天 needs_review；"
                               "`plot_pending` 是片区还剩多少格，两个口径分开记。"
                               "【Fix 1/2】三套豁免按**逐格求交**扣：只有既已被证明"
                               "（走不到/被围死/游戏拒绝）又确实还欠着的格才算，"
                               "`unmet_after_exempt` 是扣完之后仍欠的格数")
        if deferred_tiles:
            self._journal("deferred_tiles", tiles=deferred_tiles, night=bool(night_end),
                          by_kind=plot_pending_by_kind, stages=honest_stages[:6],
                          note="诚实上限（体力/夜里收工/分配额做完后撞 budget）留下的片区待办："
                               "只作 info，不进 no_unmet_stages")
        made_any_progress = rep.ok_steps > 0
        if refused_day:
            self._journal("refused_summary", count=len(refused_day), bound=refused_bound,
                          attempted=attempted_steps, bound_basis=bound_basis_steps,
                          exempted=refused_exempt,
                          raw_unmet=raw_unmet, unmet=unmet_leftover,
                          tiles=[list(t) for t in sorted(refused_day)[:12]],
                          note="游戏拒绝的格：当天封格、次日重试；界内不影响 verified，"
                               "超界照实 needs_review（与 unreachable 两套独立计数）")
        if unreach_day:
            self._journal("unreachable_summary", count=len(unreach_day), bound=unreachable_bound,
                          attempted=attempted_steps, bound_basis=bound_basis_steps,
                          engaged=engaged_steps,
                          exempted=unreachable_exempt,
                          evidenced=unreach_evidenced,
                          raw_unmet=raw_unmet, unmet=unmet_leftover,
                          tiles=[list(t) for t in sorted(unreach_day)[:12]],
                          note="不可达豁免：界内不影响 verified"
                               "（【Fix 2】豁免分子 = **日级**不可达格集合 ∩ 仍留在如实 shortfall "
                               "阶段 `assigned_undone` 里的格（逐格坐标），不再只看"
                               "「最后一条记录的 `unreachable_leftover`」—— 那种口径会在"
                               "不可达格早在前几条记录就解掉、最后一条 leftover=0 时把豁免归零；"
                               "`evidenced` 是求交后的格数，`exempted` 是过了界之后实扣的数）"
                               "（【task-78】上界分母 = `bound_basis`（发起过动作且**不是** encircled "
                               "的步数）；`attempted` 仍是原始证据计数、`engaged` = 真的站到过目标格"
                               "旁边的步数，两者都只作证据）")
        # 【task-68】"被围住"的日级账本：`enc_day` 已在上面（Fix 1）算好；这里只负责**报账**
        # （逐格证据 + 日级豁免的界与实扣）。
        tried_open_steps = sum(int(s.get("encircled_tried") or 0) for s in rep.stages)
        if enc_day:
            self._journal("encircled_summary", count=len(enc_day),
                          attempted=attempted_steps, bound_basis=bound_basis_steps,
                          bound=encircled_bound, exempted=encircled_exempt,
                          engaged=engaged_steps, tried_open_steps=tried_open_steps,
                          tiles=[list(t) for t in sorted(enc_day)[:12]],
                          note="四邻没有「可清障 + 自己够得着」的突破口 ⇒ 不算「走不到」、不封格；"
                               "【Fix 1】只对**逐格已证被围死、且仍留在如实 shortfall 阶段 "
                               "`assigned_undone` 里**的格做有界豁免（界 = max(5, 20%×bound_basis)，"
                               "与 unreachable/refused 各自独立）；预过滤的、已做成的、诚实上限"
                               "（体力/夜里收工）留下的格一律不扣"
                               "（真实四邻 kind 与逐格开路次数见 encircled 事件的 kinds/tried_open；"
                               "本键 `tried_open_steps` 是当天合计）")
            rep.notes.append(
                f"有 {len(enc_day)} 格四邻没有「可清障 + 自己够得着」的突破口 ⇒ 不算「走不到」、"
                f"不进不可达豁免（自有一套有界豁免：界 {encircled_bound}、实扣 {encircled_exempt}；"
                f"为这些格试过开路 {tried_open_steps} 次）")
        # 遮蔽可见性（Lead m02561 裁定 1）：同一阶段种类当天**更早**记录 leftover>0、**最后一条**
        # leftover==0 ⇒ "前一片地没做完、后一片地干净"的遮蔽发生了。**纯信息项**：不改 VERIFIED、
        # 不改退出码，只发 journal + 进 notes，让 run3 事后能人工复核。
        midway: dict[str, dict] = {}
        midway_all: list[dict] = []
        for i, s in enumerate(rep.stages):
            name = str(s.get("stage") or "")
            if int(s.get("tiles") or 0) <= 0 or int(s.get("leftover") or 0) <= 0:
                continue
            rec = {"stage": name, "tiles": int(s.get("tiles") or 0),
                   "leftover": int(s.get("leftover") or 0), "round": i + 1}
            midway[name] = rec
            midway_all.append(rec)
        for name, mid in midway.items():
            last = last_by_stage.get(name)
            if last is None or int(last.get("leftover") or 0) != 0:
                continue
            self.midway_leftover_today += 1        # 【task-122】当日计数（喂当晚教训）
            self._journal("stage_midway_leftover", **mid,
                          note=("同一阶段种类当天更早一轮还剩格子、最后一轮 leftover==0 ⇒ 日级判定取"
                                "最后一轮；若那批格子属于另一片地则存在遮蔽，请人工复核 `stage_exhausted`"))
            # 【task-15 / 0.7.45】日级留痕**不许只写最后一轮**：把该阶段当天**每一轮** leftover>0
            # 的记录（含轮次/格数）全部并列进 day_end，遮蔽才可复核；只作 info，
            # 不改 `no_unmet_stages`/`plot_pending` 既有公式（deputy 44 条对抗判据按旧公式回归）。
            rep.stage_midway_leftover.extend(
                dict(r) for r in midway_all if r["stage"] == name)
            rep.notes.append(
                f"阶段 {name} 中途剩 {mid['leftover']}/{mid['tiles']} 格、当天最后一轮已归零"
                f"（stage_midway_leftover，当天第 {mid['round']} 条阶段记录）")
        # task-19：日级浇水证据。**唯一证据**是 `checks.watered_outdoor`（farm.dryCrops 或当天最后一个
        # 户外快照逐格 watered）；窗口口径的 `crops_watered` 保留但只作旁证（室内恒 0，会白过）。
        # 【task-84】`farm.dryCrops`/`dryTiles` 自 0.7.27 起**只算活苗** ⇒ `watered_outdoor`
        # 不再被"够不着的死苗"拖住（run7 的 summer 3/5 三天全挂就是这个）。
        watered_outdoor, water_info = self._water_evidence(
            last_obs, outdoor_obs=outdoor_obs, outdoor_t=outdoor_t, outdoor_name=outdoor_name)
        rep.final_water = water_info
        # 【task-6 / 0.7.44】「只因预算延后」与「户外浇水达标」不得同真：日终拿到浇水证据后
        # 才把排队的 `deferred_by_budget` 落账；浇完的日子降级成 `stamina_budget` 里的
        # `deferred_by_budget_suppressed` 计数（事件一条不发），两件事实不再同时出现。
        self._flush_budget_deferrals(watered_outdoor=watered_outdoor, rep=rep)
        # 【task-84】枯死作物的日账本证据（用户 m11003）。**带状态**：0 只代表"没有"当且仅当
        # `ok`；旧 Mod 缺字段 ⇒ `unavailable`（"不知道"，绝不当 0 用，与 `farm_dry_tiles` 同纪律）。
        rep.dead_crops, rep.dead_crops_status = farm_dead_crops(last_obs)
        rep.dry_dead, rep.dry_dead_status = farm_dry_dead_crops(last_obs)
        rep.gave_up_tiles = [list(t) for t in sorted(self.far_dry_given_up)]
        if rep.dead_crops_status == "ok" and rep.dead_crops > 0:
            self._journal("dead_crops_summary", dead_crops=rep.dead_crops,
                          dry_dead=rep.dry_dead, dry_dead_status=rep.dry_dead_status,
                          gave_up=len(rep.gave_up_tiles),
                          tiles=rep.gave_up_tiles[:12],
                          note=("农场里还有枯死作物：它们**不浇水**（`farm.dryCrops` 只算活苗），"
                                "只能靠 `clear_dead` 清；窗口外的没有坐标 ⇒ 只留痕"))
            rep.notes.append(
                f"农场里还有 {rep.dead_crops} 格枯死作物（其中 {rep.dry_dead} 格没浇，"
                f"状态 {rep.dry_dead_status}）—— 死苗不浇水，等 `clear_dead` 清（本卡口径）")
        if rep.gave_up_tiles:
            rep.notes.append(
                f"当天有 {len(rep.gave_up_tiles)} 格干作物在窗口外且已放弃（坐标 "
                f"{rep.gave_up_tiles[:3]}…）⇒ 不再当「还有活」，按 gave_up_dry 如实收尾")
        if not watered_outdoor:
            rep.notes.append(
                "浇水证据不足/未浇完：" + str(water_info.get("note") or "")
                + f"（scope={water_info.get('scope')}、tiles={water_info.get('tiles')}、"
                  f"crops={water_info.get('crops')}、dry={water_info.get('dry')}）")
        # 【task-15 / 0.7.45】日终"还有活"的**可执行面快照**：`day_justified` 只认这里的
        # `pending_executable`（当前最后一张户外农场观测里"看得见 + 要做 + 允许 + 站得到"的格数）。
        # 三口径并列留痕：守卫 `_pending_work()` / 已标记停滞 / 阶段窗口 exec+blocked / 中途轮
        # leftover（上面 `stage_midway_leftover`）。这样 0.7.44 冒烟冬 26（263）与冬 27（217）
        # "账本 accum pending vs 当前观测没活"的差异在 day_end 里一眼可查，不靠末轮单口径。
        snap = self._pending_snapshot(outdoor_obs)
        rep.pending_ledger = snap["ledger"]
        rep.pending_guard = snap["guard"]
        rep.pending_stalled = snap["stalled"]
        rep.pending_executable = snap["executable"]
        rep.pending_blocked = snap["blocked"]
        rep.pending_unobserved = snap["unobserved"]
        # 【task-22 / 0.7.45】tiles[] 里字段残缺的 tile 记录数：不并入 unobserved，
        # 单独留痕并强制 day_justified=false（缺失≠通过，堵 deputy NIT-1 fail-open）。
        rep.pending_malformed = int(snap.get("malformed", 0))
        # 【devcoder-clear-gate】只因满包清障闸（背包 0 空格 + 腾格用尽）而不执行的清障格数：
        # 单独成桶，**不并入** `pending_unobserved`（那是"看不见/已陈旧"，与"今天被闸住"是两回事）。
        # >0 ⇒ `is_justified_end(gated=…)` 直接 False ⇒ 当天永不 VERIFIED（`clear_gate` 的硬闸）。
        # 老账本/旧快照没有该键 ⇒ 0（行为与改动前逐字一致）。
        rep.pending_gated = int(snap.get("gated", 0) or 0)
        # 【task-27 / 0.7.46】逐格坐标证据（有序、各前 8 条；只读，不参与判据）：
        # `pending_executable_tiles` 让"day_justified 有证据"能落到具体坐标上；
        # `pending_stalled_tiles` 让"停滞/挡死"能逐格对账（不是只报一个数）。
        rep.pending_executable_tiles = list(snap.get("executable_tiles") or [])[:8]
        rep.pending_stalled_tiles = list(snap.get("stalled_tiles") or [])[:8]
        # 【task-28 卡 D B】"腾不出"证据快照（只读）：即使当天没走 `_note_inventory_blocked`
        # （例如从未满包），日终也留一份可复核读数 —— `relief_exhausted` + `bag_evidence`。
        # 判据语义不动：只有 ended_by=inventory_blocked 且 exec/malformed==0 时 day_justified 才认。
        if not rep.bag_evidence:
            rep.bag_evidence = self._bag_relief_evidence(outdoor_obs)
        rep.relief_exhausted = bool(rep.bag_evidence.get("exhausted"))
        # 【task-28 卡 D C】满包清障闸也在日终 notes 里留一句（journal 里已有 slot_relief
        # trigger=clear_gate；这里让人读 day_end 文本就能看到"今天没新开清障"）。
        if self.clear_area_bag_gate_noted:
            rep.notes.append(
                f"满包清障闸：背包 0 空格且腾格手段用尽 ⇒ 今天不新开 clear_area"
                f"（loot_lost_steps={int(self.loot_lost_steps_today)}/"
                f"{int(CLEAR_LOOT_LOSS_MAX_STEPS)}，落地丢失只 info 不进 checks）")
        if rep.pending_ledger or rep.pending_stalled or rep.pending_blocked:
            rep.notes.append(
                f"日终账本：原始 {rep.pending_ledger} 格（守卫口径 {rep.pending_guard} 格、"
                f"已判死 {rep.pending_blocked} 格，其中停滞/被围 {rep.pending_stalled} 格）；"
                f"当前观测里可执行 {rep.pending_executable} 格、看不见/已陈旧/今天不可执行 "
                f"{rep.pending_unobserved} 格"
                + (f"、观测记录残缺 {rep.pending_malformed} 格（不并入看不见，day_justified 必 false）"
                   if rep.pending_malformed else "")
                + (f"、满包清障闸闸住 {rep.pending_gated} 格（背包 0 空格 + 腾格用尽；"
                   "不并入看不见，day_justified 必 false）"
                   if rep.pending_gated else "")
                + ("（观测证据不可用 ⇒ 诚实收工判定不放行）" if outdoor_obs is None else ""))
        # 【task-16 / 0.7.45】背包空格与"清障掉落被游戏拒收"的日终留痕：**只作 info** ——
        # 满包清障照常算做成（不因此判失败、不改下面任何一个 checks 键）；但"掉的战利品可能
        # 丢了"必须一眼能看到。逐格判据在 `StepResult.loot_lost`（`day_end.stages[i].loot_lost*`
        # 也有阶段汇总；`farmwork.clear()` 成功分支写入，`_note_loot_lost` 聚合）。
        if rep.loot_lost_steps:
            rep.notes.append(
                f"背包 0 空格 ⇒ 有 {rep.loot_lost_steps} 步清障掉落被游戏拒收（Inventory Full）；"
                f"逐格 {rep.loot_lost_tiles[:5]}…，近似掉落 {rep.loot_lost_items[:4]}"
                "——只留痕，不算失败/不改 checks；先腾格可缓解，根治见 task-14 背包升级建议")
        if rep.free_slots_min is not None:
            rep.notes.append(
                f"背包空格：开局 {rep.free_slots_start}、最低 {rep.free_slots_min}、日终 "
                f"{rep.free_slots_last}（状态 {rep.free_slots_status}；口径=容量−非空行数）")
        rep.checks = {
            # 【task-198】`inventory_blocked` 也是"我们睡下去让游戏日翻篇了"（`_do_sleep` 成功），
            # 只是收尾原因写成了背包堵住 —— 所以 `slept_by_us` 必须为真，否则报告会说谎。
            # 【task-28 卡 D】它是否算达标只看 `is_justified_end()` 的**证据门槛**：
            # `inventory_blocked` 已进诚实收工白名单，但必须 `pending_executable==0` 且
            # `pending_malformed==0`（四门槛在 `_note_inventory_blocked` 已先过）；`stuck:` 永不认。
            "slept_by_us": self._slept_by_us(rep),
            # task-11：被不可逆/不敢关的模态挡住（职业选择、存档超时）时，这一天**不算数**。
            # 用户 m03224 拍板了职业路线：宁可停下等人，也不静默丢档。
            "no_blocking_modal": rep.ended_by not in BLOCKING_ENDS,
            "no_hard_failures": rep.failed_steps == 0 and rep.refused <= refused_bound,
            # 【task-52】"走不到"本身不算硬失败，但**有上界**：超过 `max(5, 20%×bound_basis)`
            # 就不是"个别格子客观走不到"，而是"今天大片目标够不着" ⇒ 照实 needs_review。
            # （【task-78 NIT-1】基数 `bound_basis` 剔掉了 `encircled` 步 —— 见日终注释。）
            "unreachable_within_bound": rep.unreachable <= unreachable_bound,
            # 【task-63】游戏拒绝同样**有上界**（防"游戏全拒绝"换个 verified）。该键**总是**写、
            # 总是 bool（`tools\verify-run3.py` 按 `is False` 判 problem）。
            "refused_within_bound": rep.refused <= refused_bound,
            # task-52 防洗白：豁免只对"走不到"的格子生效，且**全部不可达 + 0 成功动作**时
            # 不许靠豁免把 `no_unmet_stages` 洗成 True（真空日必须仍判不达标）。
            # task-63 把同一条防洗白扩到 `refused`：两组豁免都非空且 0 成功 ⇒ 仍不达标。
            # 【Fix 1】`encircled_exempt` 同样消费这个合取项：0 成功日就算整片只是"被围住"，
            # 也不许靠豁免判达标（既有用例 `test_day_with_only_encircled_leftover_ends_honestly`
            # 钉死"只有挡死格的一天不 VERIFIED"）。
            "no_unmet_stages": unmet_leftover == 0 and (
                made_any_progress or (unreachable_exempt == 0 and refused_exempt == 0
                                      and encircled_exempt == 0)),
            "crops_watered": int(rep.final.get("unwatered_crops") or 0) == 0,
            # task-19：**唯一**浇水证据（卡面 §1；`tools\verify-run3.py` 缺这条即问题）。
            # 窗口口径的 `crops_watered` 只作旁证：它读的是 `_essence` 的窗口计数，在室内恒 0。
            "watered_outdoor": bool(watered_outdoor),
            # 【task-32】白名单里**没有** `no_plot`：作业区配额到顶是我们自己设的软上限，
            # 被它憋停不等于"没活可做"，不许据此判 VERIFIED（判据见 `is_justified_end`）。
            # 【task-15 / 0.7.45】`resume_exhausted`（换片/回片区/观测都拿不出目标）也只有
            # **当前观测里可执行格为 0** 时才认（证据 = 上面的 `pending_executable`）；
            # 有活却收工/观测证据不可用 ⇒ 仍是 False，反向洗白用例钉死这条。
            # 【task-22 / 0.7.45】`pending_malformed > 0`（tiles[] 记录字段残缺）⇒ 一律 False。
            # 【devcoder-clear-gate】`pending_gated > 0`（只因满包清障闸而不执行的清障格）⇒ 一律
            # False：这一天是"活被背包闸住"（`clear_gate`），不是"没活可做"，永不 VERIFIED。
            "day_justified": is_justified_end(
                rep.ended_by, rep.ended_reason,
                pending_executable=rep.pending_executable,
                malformed_tiles=rep.pending_malformed,
                gated=rep.pending_gated),
            # 【task-149 C】0 动作日**不许** VERIFIED —— 除非当天有真正独立的"无活可做"证据
            # （`sleep_guard` 在 farm 证据齐备且 `work_reasons` 为空时置的
            # `no_work_evidence_ok`）。run9c summer 20：22.81 秒、`ok_steps=0`、`decision=0`，
            # 依据只有室内窗口（`tillable=0`）+ farm 的 `dry/ripe/dead=0` 就自称 `no_work` 并
            # `verified=true`，而地里有 142 格空耕地、手上还有种子 ⇒ 假绿灯。
            # 与 `no_work_evidence_ok` 配套：`day_start_off_farm` 时守卫压根不给 `no_work`，
            # 所以这条不会把"诚实收尾"误判成不达标。
            "zero_action_evidenced": self._zero_action_evidenced(rep),
        }
        rep.verified = all(rep.checks.values())
        self._say(
            f"[day] {rep.day_text} 结束：{rep.ended_by}"
            + (f"（{rep.ended_reason}）" if rep.ended_reason else "")
            + f" 阶段 {rep.stages_seen or '无'} 做成 {rep.ok_steps} 跳过 {rep.skipped_steps} 失败 {rep.failed_steps}"
            + f" 阶段分下去的格少做 {unmet_leftover} 格（no_unmet_stages={rep.checks.get('no_unmet_stages')}）"
            + f"；片区待做 {raw_unmet} 格"
            + (f"（其中 {rep.deferred_tiles} 格是诚实上限留下的，只作 info）" if rep.deferred_tiles else "")
            + (f"；主动认输 {rep.scope_shed_tiles} 格（{rep.scope_shed.get('zone')}，只作 info、"
               f"仍算未完成）" if rep.scope_shed_tiles else "")
            + (f" 走不到 {rep.unreachable} 格（豁免界 {unreachable_bound}、实扣 {unreachable_exempt}）"
               if rep.unreachable else "")
            + (f" 游戏拒绝 {rep.refused} 格（豁免界 {refused_bound}、实扣 {refused_exempt}）"
               if rep.refused else "")
            + (f" 被围住 {rep.encircled} 格（有界豁免 界 {encircled_bound}、实扣 {encircled_exempt}）"
               if rep.encircled else "")
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
            # 【task-73】stuck 日翻篇也睡过了一天 ⇒ 同样必须重新取观测，否则 `_last_day_key`
            # 还停在旧的一天，总控会误判"游戏日没有前进"当场停（那样翻篇就白做了）。
            # `_stuck_flush` 已经取过一张的话（`day_after` 非空）就不重复发请求。
            if rep.ended_by == "sleep" or (rep.stuck_flushed and not rep.day_after):
                try:
                    fresh = self._snap()
                except BridgeError as exc:  # pragma: no cover - 仅诊断
                    self._journal("day_key_resnap_failed", error=str(exc))
                    fresh = None
                if fresh is not None:
                    key_obs = fresh
                    rep.day_after = [int(v) if str(v).isdigit() else str(v)
                                     for v in FarmWorker.day_key(fresh)]
            # 【task-73】翻篇那天 `_stuck_flush` 已经把"睡后那一天"取进 `rep.day_after`（而
            # `key_obs` 还是睡前观测）⇒ 优先用 `day_after`，否则总控会把翻篇误判成
            # "游戏日没有前进"当场 break（翻篇白做）。`rep.day_after` 的归一化形式与
            # `FarmWorker.day_key()` 一致，可直接成 tuple。
            if rep.day_after:
                self._last_day_key = tuple(rep.day_after)
            else:
                self._last_day_key = tuple(FarmWorker.day_key(key_obs))
        except Exception:  # pragma: no cover
            self._last_day_key = None
        # 【task-58】把今天的边界决策连同**真实结局**记进会话内记忆（只喂提示词，不参与判定）。
        # 结局只写客观事实：`VERIFIED`/`needs_review` + 失败格数或收尾原因摘要；
        # 空列表（今天没有 LLM 调用 / 开关关着）⇒ 什么都不加，提示词里也就不出现这一节。
        if day_decisions:
            outcome = "VERIFIED" if rep.verified else "needs_review"
            reason = str(rep.ended_reason or "")
            if not rep.verified:
                reason = (f"{rep.failed_steps} 格没做成" if rep.failed_steps else reason)
            # 【task-82】决策→结果的 join：终态计数与三个数字**全部从当天的账本数出来**
            # （`rep.outcomes` / `rep.stages`），这里只做汇总与排版；`where` 用**具名田区**
            # （`rep.plots[].zone`），坐标不进提示词（沿用 task-58 的契约）。
            term: dict[str, int] = {}
            for _o in rep.outcomes:
                _t = str((_o or {}).get("terminal") or "")
                if _t:
                    term[_t] = term.get(_t, 0) + 1
            if not term:
                term = {outcome: 1}
            leftover_total = sum(int(s.get("leftover") or 0) for s in rep.stages)
            unreach_total = sum(int(s.get("unreachable") or 0) for s in rep.stages)
            refused_total = sum(int(s.get("refused") or 0) for s in rep.stages)
            zones = [str(p.get("zone") or "") for p in rep.plots if p.get("zone")]
            where = "/".join(dict.fromkeys(zones)) or "窗口"
            for _d in day_decisions:
                self.decision_memory.append(decision_line(
                    day_key=rep.day_key, boundary=_d["boundary"], intents=_d["intents"],
                    verdict_counts=_d["verdicts"], outcome=outcome,
                    ended_by=rep.ended_by, ended_reason=reason,
                    terminal=term, leftover=leftover_total,
                    unreachable=unreach_total, refused=refused_total, where=where))
            del self.decision_memory[:-DECISIONS_KEPT]
        # 【task-82】日终把今天的**客观教训**并进跨日教训库（`<journal>-lessons.json`）。
        # 只读账本写事实；`hint` 来自今晚收工复盘（没有 ⇒ 空）。读/写失败都只记一笔，
        # 绝不影响 `rep` 的任何判定字段。
        # 【task-219】意图对账收口 + 能力缺口清单落盘：**都在 day_end 之前**，且都只写
        # 账本/提示词（不进 `rep.checks`、不改 `verified`、不做豁免）。
        self._finish_intent_coverage(rep)
        self._gaps_flush(rep)
        self._lessons_flush(rep)
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

    def _cleanup_modals_before_finish(self) -> dict[str, Any]:
        """【task-236】收尾前把挡着的模态关掉（末次跨日的落盘守卫）。

        为什么必需（0.7.40 A2 冒烟）：第 3 次跨日后跑立刻 `finish` 退出，把保存推迟的
        `ShippingMenu` 留在屏幕上没人关 ⇒ 那一次 `NewDay` 的存档从未开始
        （SMAPI 窗口 `NewDay 3` / `SaveGame.Save() called 2`，存档停在第 3 天清晨）。

        纪律（卡面明文 + 项目既有口径）：
          * **只关模态**：不 `load_save`、不改档、不 sleep；
          * 存档类菜单（`MODAL_WAIT_ONLY`）**只等不关**（等游戏自己走完，dismiss 会打断存档）；
          * 最多 `CLEANUP_DISMISS_MAX` 轮；仍卡 ⇒ 如实记账、**不洗白**（进 `finish` 摘要）；
          * **不新增 journal 事件名**：复用 `modal_dismissed`（每轮，带 `kind="cleanup"`）与
            `modal_dismiss_failed`（卡住时，带 `kind="cleanup_blocked"`）—— analyzer 的机械
            枚举测试会盯 `_journal("<新名字>"`，新事件名会让全量变红。
        """
        result: dict[str, Any] = {"attempts": 0, "menu": None, "stuck": False}
        if self.worker is None or self.client is None:
            return result
        obs: dict[str, Any]
        for attempt in range(1, CLEANUP_DISMISS_MAX + 1):
            try:
                obs = self._snap()
            except BridgeError as exc:
                result["stuck"] = True
                result["error"] = f"{type(exc).__name__}: {exc}"
                self._journal("modal_dismiss_failed", kind="cleanup_blocked",
                              menu=result["menu"], tries=attempt - 1,
                              reason=str(exc),
                              note="收尾清模态时连观测都失败 ⇒ 无法确认末次跨日是否落盘")
                return result
            is_modal, menu, ui = self._modal_info(obs)
            if not is_modal:
                return result
            # 【不可逆/人工模态绝不关】—— 既有硬规则优先于"收尾清模态"：
            #   * `eventUp=true`（游戏事件/剧情）：task-41/228 规定事件一律视为阻断模态，一次都不动手；
            #   * 职业选择 `LevelUpMenu`（`professionsToChoose` 非空、或读不到 ⇒ fail-closed）：
            #     dismiss = 永久丢掉 Tiller/Artisan 选择（不可逆，必须人来点）。
            if ui.get("eventUp") is True:
                result["skipped"] = "event_up"
                return result
            if menu == "LevelUpMenu":
                pending = ui.get("professionsToChoose")
                if pending is None or list(pending):
                    result["skipped"] = "profession_pending"
                    return result
            result["attempts"] = attempt
            result["menu"] = menu
            if menu in MODAL_WAIT_ONLY:
                obs, gone, waited = self._wait_modal_gone(menu, obs)
                self._journal("modal_dismissed", kind="cleanup_wait", menu=menu, tries=attempt,
                              receipt=None, waited_s=round(waited, 1), ok=gone,
                              note="收尾守卫：存档类菜单只等不关（dismiss 会打断存档）")
                if gone:
                    continue
                result["stuck"] = True
                self._journal("modal_dismiss_failed", kind="cleanup_blocked", menu=menu,
                              tries=attempt,
                              note="收尾时存档菜单一直没有自己走完 ⇒ 末次跨日可能没落盘")
                return result
            try:
                obs = self._dismiss_modal_once(menu, ui, kind="cleanup", tries=attempt)
            except BridgeError as exc:
                result["stuck"] = True
                result["error"] = f"{type(exc).__name__}: {exc}"
                self._journal("modal_dismiss_failed", kind="cleanup_blocked", menu=menu,
                              tries=attempt, reason=str(exc),
                              note="收尾关模态失败 ⇒ 末次跨日可能没落盘")
                return result
            after_modal, after_menu, _ui = self._modal_info(obs)
            if not after_modal:
                return result
            result["menu"] = after_menu or menu
        result["stuck"] = True
        self._journal("modal_dismiss_failed", kind="cleanup_blocked", menu=result["menu"],
                      tries=CLEANUP_DISMISS_MAX,
                      note=f"收尾清模态 {CLEANUP_DISMISS_MAX} 轮仍卡 ⇒ 末次跨日可能没落盘")
        return result

    def _finish(self, code: int) -> int:
        streak = self._verified_streak()
        # 【task-236】末次跨日落盘守卫：跑结束前把挡着的模态关掉（最多 `CLEANUP_DISMISS_MAX` 轮）。
        # 不关掉保存推迟的 `ShippingMenu`，那一次 NewDay 的存档根本不会开始（0.7.40 冒烟）。
        cleanup = self._cleanup_modals_before_finish()
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
            # 【task-73】整轮用掉几次"stuck 日翻篇"（上界 `MAX_STUCK_FLUSH`）：>0 说明有日子是
            # 靠睡过去才让运行继续的 —— 那些日子本身仍如实算 `stuck`/不 VERIFIED，这里只是账。
            "stuck_flushes": self.stuck_flushes,
            # 【task-236】收尾清模态的账：`stuck=true` 说明最后一次跨日**可能没落盘**
            # （保存模态一直没走完）。它不进 `checks`（不给洗白面），只作运行级诚实记账。
            "cleanup_modal_stuck": bool(cleanup.get("stuck")),
            "cleanup_attempts": int(cleanup.get("attempts") or 0),
            "cleanup_menu": cleanup.get("menu") or "",
            # 被保护而未清的模态（`event_up` / `profession_pending`）：如实记账，不碰它。
            "cleanup_skipped": cleanup.get("skipped") or "",
            "journal": str(self.journal_path) if self.journal_path else "",
            **({"prepare_error": self.summary["prepare_error"]} if self.summary.get("prepare_error") else {}),
            **({"cleanup_error": cleanup["error"]} if cleanup.get("error") else {}),
        }
        self._journal("finish", code=code, verified_streak=streak, actions=self._actions,
                      minutes=round(self._elapsed_minutes(), 2), stages_seen=self.summary["stages_seen"],
                      no_unmet_stages=not unmet_days, unmet_days=unmet_days,
                      stuck_flushes=self.stuck_flushes,
                      cleanup_modal_stuck=self.summary["cleanup_modal_stuck"],
                      cleanup_attempts=self.summary["cleanup_attempts"],
                      cleanup_menu=self.summary["cleanup_menu"])
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
                  + (f"；stuck 日翻篇 {self.stuck_flushes} 次" if self.stuck_flushes else "")
                  + (f"；准备失败：{self.summary['prepare_error']}" if self.summary.get("prepare_error") else "")
                  + (f"；⚠ 收尾清模态卡住（{self.summary['cleanup_menu'] or '?'}，试 "
                     f"{self.summary['cleanup_attempts']} 次）⇒ 末次跨日可能没落盘"
                     if self.summary["cleanup_modal_stuck"] else ""))
        return code
