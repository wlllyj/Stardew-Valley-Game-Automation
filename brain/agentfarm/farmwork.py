# -*- coding: utf-8 -*-
"""单次农活的**执行层**：把动作发出去、再重新观测，用差分判它到底成没成。

【为什么单独成文件，而不是继续用 `tools\\run-plot.py`】
`run-plot.py` 是"单块地跑一遍、打印一张成绩单"的验收工具（跑完就退出）。
长跑控制器要的是**能被反复调用的动作集合**：清障 / 锄地 / 播种 / 浇水 / 补水 / 收获 / 睡觉，
每一步都能单独记账、单独重试，而且**不许自己决定"接下来干什么"**——那是 `longrun.py` 的职责。
两者判据同源（都来自 `observe?detail=full` 的 `tiles[]` / `player` 差分）。

【铁律（与 run-plot.py 同源，也是本项目最高纪律）】
* **回执只是声明**：`use_tool` 回 `status=ok` 也不代表那一格变了；判据永远是重新观测的差分。
  反过来也成立：补水时回执可能报 `tool_ineffective`（Mod 的 can 判据是"目标格出现 HoeDirt 且 watered"，
  对着水面挥壶永远不满足），但只要 `player.wateringCan.waterLeft` 涨了，补水就是**真做成了**。
  两种方向都不许拿回执当结论 —— 只认观测。
* **没做成就是没做成**：`code="failed"` + `reason`，绝不含糊成"大致完成了"。
* **跳过 ≠ 失败**：草 / 树 / 机器这类"不该用锄头动"的格子记 `skipped` 并写明原因；
  它与"我试了但没做成"分开记 —— 前者不污染终态，后者必须让这一天 `needs_review`。
* **先判后动，判据写进 reason**：动手之前能用观测判出"这格现在干不了"（缺工具 / 有 feature
  或 objId 挡着 / 有作物）就**一次都不挥**，把是哪条判据拦下的写进 `reason`。
  挥了世界没变也只挥**一次**，并打 `proven_inert` 让 `longrun._mark_blocked` 当天封格
  —— 用户 m01758/m01804："工具等级不够要判断一下，不要白白浪费很多体力"。
  ⚠️ 观测里**没有斧/镐/锄的升级等级**（只有 `player.tools{}` 的"有没有"和 `wateringCan.upgradeLevel`），
  所以"等级不够"判不了；能判的只有"没这件工具"。见 `tool_missing_reason`。
* **全局缺料单独报**：种子 / 水用光时回 `no_seed` / `need_refill`，别让后面每一格去撞同一堵墙。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .bridge import BridgeClient, BridgeError

__all__ = [
    "DEBRIS_KINDS",
    "KIND_TOOL",
    "SKIP_KINDS",
    "STAGE_ACTION",
    "FarmWorker",
    "StageResult",
    "StepResult",
    "seed_items",
    "till_blocked_by",
    "tool_missing_reason",
    "tool_presence",
]

#: 需要"用工具清掉"的障碍（`use_tool(auto)` 会自己挑斧/镐/镰并失败换工具）。
DEBRIS_KINDS = ("weed", "twig", "stone")

#: 这些格子**不该用锄头动**（要么先砍/先敲，要么根本不是地）——跳过并写明原因。
SKIP_KINDS = {
    "tree": "树（先用斧头砍）",
    "fruitTree": "果树",
    "clump": "资源堆（先用镐敲）",
    "bush": "灌木",
    "object": "放置物/机器（不该动）",
}

#: 草：锄头锄不出耕地（真机实测跳过原因），但**该用镰刀割掉**——"清理农场障碍"包含它。
GRASS_KIND = "grass"

#: 规划层的任务类型 → 执行层的动作。
#: `plant_area` 走 `sow`（播种 + 立刻浇这一格），理由见 `FarmWorker.sow` 的 docstring。
STAGE_ACTION = {
    "clear_area": "clear",
    "till_area": "till",
    "plant_area": "sow",
    "water_area": "water",
    "harvest": "harvest",
}

#: 邻格顺序（上/下/右/左）：站到目标格四邻之一再动手。
NEIGHBORS = ((0, -1), (0, 1), (1, 0), (-1, 0))

#: 没写明的种子的兜底（真机背包里 472 是防风草种子；但代码**不硬编码**，只在挑种子时用它排序）。
DEFAULT_SEED_HINTS = ("seed", "种子")

#: 每种障碍"一次挥动该用哪件工具"（与 Mod `UseToolSkill.BuildPlan` 的种类首选**同源**；
#: 真机实证：杂草→锄头、树枝→斧头、石头→镐、草→镰刀）。`clear()` 用的就是这个映射。
KIND_TOOL = {"weed": "hoe", "twig": "axe", "stone": "pickaxe", GRASS_KIND: "scythe"}

#: `player.tools{}` 的布尔位 → 脑里的工具名（v0.7.x 起观测里就有，比翻背包名字准）。
#: ⚠️ 这里**没有 scythe 位**：Mod 的 `WorldSnapshot.ReadTools` 只把 `MeleeWeapon` 记进 `weapon`，
#: 而 1.6.15 的镰刀在真机快照里是 `(W)47`（见 `logs\\observe-farm-sample.json` 的 slot 4）
#: ⇒ 镰刀靠 `weapon` 位 **或** 背包里的 id 47/53、名字含 scythe/镰刀来认。
TOOL_FLAG = {"axe": "axe", "pickaxe": "pickaxe", "hoe": "hoe", "can": "wateringCan"}

#: 工具的物品判据：把 id/qualifiedId/名字**归一化**（小写、去空格/下划线、去 (T)/(W) 前缀）后
#: 精确比对 —— 不能用子串："pickaxe" 里含 "axe"，子串匹配会把镐误认成斧。
TOOL_IDS = {
    "axe": {"axe", "copperaxe", "steelaxe", "goldaxe", "iridiumaxe"},
    "pickaxe": {"pickaxe", "copperpickaxe", "steelpickaxe", "goldpickaxe", "iridiumpickaxe"},
    "hoe": {"hoe", "copperhoe", "steelhoe", "goldhoe", "iridiumhoe"},
    "can": {"wateringcan", "copperwateringcan", "steelwateringcan",
            "goldwateringcan", "iridiumwateringcan"},
}
SCYTHE_IDS = {"47", "53"}
SCYTHE_HINTS = ("scythe", "镰刀")


def _norm_item_text(value: Any) -> str:
    """把物品 id/qualifiedId/名字归一化：`(W)47`→`47`、`Watering Can`→`wateringcan`。"""
    text = str(value or "").strip().lower()
    for prefix in ("(t)", "(w)", "(o)", "(b)", "(f)"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.replace(" ", "").replace("_", "")


def _item_is_tool(item: dict[str, Any], want: str) -> bool:
    """背包里这一条是不是 `want` 那件工具（按 id/qualifiedId/名字精确比对，见 `TOOL_IDS`）。"""
    vals = {_norm_item_text(item.get(k)) for k in ("id", "qualifiedId", "name")}
    vals.discard("")
    if want == "scythe":
        return bool(vals & SCYTHE_IDS) or any(
            hint in v for v in vals for hint in SCYTHE_HINTS)
    return bool(vals & TOOL_IDS.get(want, set()))


def tool_presence(player: dict[str, Any]) -> dict[str, bool]:
    """从观测读"身上有哪些工具"：`{axe/pickaxe/hoe/can/scythe: bool}`。

    两个数据源（**"有"优先于"没有"**：任一源说有就是有）：
      * `player.tools{axe,pickaxe,hoe,wateringCan,weapon}` —— Mod 的权威位；
      * 背包 `inventory[]` 的 `isTool` 条目 —— 老 Mod / 缺 `tools` 位时的兜底（也是唯一能认出镰刀的源）。

    ⚠️ 读不到工具信息的键**不出现在结果里**（= 判不准，调用方必须放行，不能因为脑自己看不准就不干活）。
    """
    votes: dict[str, list[bool]] = {}
    tools = player.get("tools")
    if isinstance(tools, dict) and tools:
        for want, flag in TOOL_FLAG.items():
            if flag in tools:
                votes.setdefault(want, []).append(bool(tools.get(flag)))
        if "weapon" in tools:      # 镰刀在 1.6.15 是 MeleeWeapon(`(W)47`) ⇒ weapon 位也算一票
            votes.setdefault("scythe", []).append(bool(tools.get("weapon")))
    items = [it for it in (player.get("inventory") or []) if it.get("isTool")]
    if items:
        for want in ("axe", "pickaxe", "hoe", "can", "scythe"):
            votes.setdefault(want, []).append(any(_item_is_tool(it, want) for it in items))
    return {want: any(vs) for want, vs in votes.items()}


def tool_missing_reason(player: dict[str, Any], want: str) -> str:
    """脑准备发 `want` 这件工具 —— 它到底在不在身上？返回"缺工具"的人话；空串 = 在/判不了。

    【为什么要有这条前置判据】`use_tool` 里工具不在背包 ⇒ Mod 只会回 `precondition_failed`
    （`UseToolSkill.FindToolSlot`），一次挥动都不发生、观测不变；脑若照旧记 failed，
    就是拿"回执无关"当"白试"，外加拿路走过去。用户 m01758/m01804 要的正是这条。

    * `want="auto"`：只要身上**有任何一件工具**就算可用（Mod 的 auto 会按种类依次换工具试，
      脑无法在此穷举"哪件一定清得掉"）；一件都没有才是真干不了。
    * 判不准（观测里没有工具/背包信息）⇒ 返回空串放行：宁可多挥一次，也不能整天不动手。
    """
    want = str(want or "")
    if not want:
        return ""
    pres = tool_presence(player)
    if want == "auto":
        if not pres:
            return ""
        if any(pres.values()):
            return ""
        return "背包里一件工具都没有（auto 无从下手）"
    if pres.get(want, True):     # 判不准（键不存在）或有 ⇒ 放行
        return ""
    return f"背包里没有「{want}」这件工具（这一格只能用 {want} 处理）"


def till_blocked_by(tv: dict[str, Any] | None, player: dict[str, Any] | None = None) -> str:
    """这一格有没有挡着开垦的东西？空串 = 干净可锄。

    真机实证（`logs\\longrun-3day-run1.jsonl`）：Mod 的 `tillable[]` 把"有未知地形特征"的格子
    也算成可锄（真机 `(73,25)/(74,25)/(73,26)/(74,26)` 四格 kind=未知），锄头挥了 16 下都没出 dirt，
    白烧 60+ 体力。所以开垦目标以**观测**为准：干净（没有 feature/objId/作物）才去锄。

    判据顺序（全部来自观测，动手之前）：
      1. `kind == dirt` ⇒ 已经是耕地（不算挡着）；
      2. 有作物 ⇒ 不能锄；
      3. 有 `feature`（地形特征名，例：`Stone`/`Grass`/`Flooring`）；
      4. `objId` 存在且 != `-1`（放置物/掉落物挡着）；
      5. 干净格子但**背包里没有锄头** ⇒ 挥了只会拿到 `precondition_failed`（前置判据，省一次白试）。

    `player=None` 时跳过第 5 条（只按观测判，老调用点/单测不用改）。
    """
    if not tv:
        return ""
    kind = str(tv.get("kind") or "")
    if kind == "dirt":
        return ""
    if tv.get("crop"):
        return "有作物"
    # Mod 对没有具体地形的格子回 kind="unknown"（真机就是那几个"未知"格）⇒ 日志里说人话
    label = "未知" if kind in ("", "unknown") else kind
    feature = str(tv.get("feature") or "")
    obj = str(tv.get("objId") or "")
    if feature:
        return f"{label}（{feature}）"
    if obj and obj != "-1":
        return label
    if player is not None:
        miss = tool_missing_reason(player, "hoe")
        if miss:
            return miss
    return ""


def _work_context(obs: dict[str, Any]) -> str:
    """失败现场的一行诊断（写进 `reason`/journal 供复核）：等级 / 体力 / 身上工具。"""
    player = obs.get("player") or {}
    bits: list[str] = []
    level = player.get("farmingLevel")
    if isinstance(level, int):
        bits.append(f"farmingLevel={level}")
    try:
        bits.append(f"体力={float(player.get('stamina') or 0.0):g}")
    except (TypeError, ValueError):  # pragma: no cover - 观测残缺时不该让动作崩
        pass
    have = "、".join(k for k, v in sorted(tool_presence(player).items()) if v) or "未知"
    bits.append(f"身上工具={have}")
    return "（" + "，".join(bits) + "）"


@dataclass
class StepResult:
    """一次动作的差分结论。所有字段都是**可落盘**的纯数据。"""

    action: str
    tile: tuple[int, int] | None = None
    ok: bool = False
    code: str = "ok"          # ok / already / skipped / failed / no_seed / need_refill / no_target
    reason: str = ""          # 人话：为什么是这个结论（**含判据**）
    receipt: str = ""         # 回执摘要（**只是诊断**，不作为证据）
    before: Any = None        # 动作前的观测要点（差分左半）
    after: Any = None         # 动作后的观测要点（差分右半）
    #: **这一格今天已被观测证明干不动**：缺工具 / 有 feature 或 objId 挡着 / 挥了世界没变。
    #: `longrun._mark_blocked` 据此把该格记进当天的 `blocked`（同一格最多白试一次）。
    proven_inert: bool = False

    @property
    def skipped(self) -> bool:
        return self.code == "skipped"

    @property
    def failed(self) -> bool:
        return self.code == "failed"

    @property
    def attempted(self) -> bool:
        """这一格的动作**被发起过**没（纯"跳过"= 没发起，不算白试）。"""
        return self.code != "skipped" or self.proven_inert

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"action": self.action, "ok": self.ok, "code": self.code}
        if self.tile is not None:
            d["tile"] = [int(self.tile[0]), int(self.tile[1])]
        if self.reason:
            d["reason"] = self.reason
        if self.receipt:
            d["receipt"] = self.receipt
        if self.before is not None:
            d["before"] = self.before
        if self.after is not None:
            d["after"] = self.after
        if self.proven_inert:
            d["proven_inert"] = True
        return d


@dataclass
class StageResult:
    """一个阶段（如"把这块地的杂草清掉"）在一串格子上的结果。"""

    stage: str
    tiles: list[tuple[int, int]] = field(default_factory=list)
    steps: list[StepResult] = field(default_factory=list)
    stopped: str = ""        # "" / "stamina" / "budget" / "no_seed" / "need_refill" / "world"
    stopped_reason: str = ""

    @property
    def attempted(self) -> list[StepResult]:
        return [s for s in self.steps if not s.skipped]

    @property
    def ok_count(self) -> int:
        return sum(1 for s in self.steps if s.ok)

    @property
    def already_count(self) -> int:
        return sum(1 for s in self.steps if s.code == "already")

    @property
    def skipped_count(self) -> int:
        return sum(1 for s in self.steps if s.skipped)

    @property
    def failed_steps(self) -> list[StepResult]:
        return [s for s in self.steps if s.failed]

    @property
    def progress(self) -> bool:
        return self.ok_count > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "tiles": [[int(x), int(y)] for x, y in self.tiles],
            "ok": self.ok_count,
            "already": self.already_count,
            "skipped": self.skipped_count,
            "failed": len(self.failed_steps),
            "stopped": self.stopped,
            "stopped_reason": self.stopped_reason,
            "steps": [s.as_dict() for s in self.steps],
        }


def seed_items(player: dict[str, Any]) -> list[tuple[str, str, int]]:
    """背包里**还能用**的种子：(id, 名字, 总堆叠)，按堆叠从多到少。

    判据是**名字里有 seed/种子**，不是硬编码 ItemId —— 换作物品种/换存档都不用改代码。
    ⚠️ 堆叠 0 的条目不算"有种子"：背包里留着一条空记录（真机上物品用尽时格子会消失，
    但快照可能刚好抓到 0）如果算成"有种子"，上层就不会去买，随后每一格播种都拿到
    `no_seed`、世界毫无变化 —— 一天就这样空转成 stuck（单测 `test_buys_seeds_when_run_out` 实证）。
    """
    out: list[tuple[str, str, int]] = []
    for it in player.get("inventory") or []:
        if it.get("isTool"):
            continue
        name = str(it.get("name") or "")
        if not any(h in name.lower() or h in name for h in DEFAULT_SEED_HINTS):
            continue
        sid = str(it.get("id") or "")
        if not sid:
            continue
        stack = int(it.get("stack") or 0)
        if stack <= 0:
            continue
        out.append((sid, name, stack))
    out.sort(key=lambda t: (-t[2], t[0]))
    return out


class FarmWorker:
    """一格一动的执行器。**不做策略**：给它格子，它做完并如实报告。"""

    def __init__(
        self,
        client: BridgeClient,
        *,
        seed: str | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        self.c = client
        self.seed = seed            # None = 每次播种时按背包里堆叠最多的种子现挑
        self.log = log
        self.steps: list[StepResult] = []      # 全程流水（journal 用）
        self.walk_steps = 0

    # ------------------------------------------------------------------ 观测
    def snap(self) -> dict[str, Any]:
        return self.c.observe("full")

    @staticmethod
    def tiles_of(obs: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
        rows = (obs.get("location") or {}).get("tiles") or []
        out: dict[tuple[int, int], dict[str, Any]] = {}
        for t in rows:
            xy = t.get("tile") or []
            if len(xy) >= 2:
                out[(int(xy[0]), int(xy[1]))] = t
        return out

    @staticmethod
    def tillable_of(obs: dict[str, Any]) -> set[tuple[int, int]]:
        return {tuple(int(v) for v in c) for c in ((obs.get("location") or {}).get("tillable") or [])}

    @staticmethod
    def refill_of(obs: dict[str, Any]) -> list[tuple[int, int]]:
        loc = obs.get("location") or {}
        return [(int(v[0]), int(v[1])) for v in (loc.get("refillTiles") or []) if len(v) >= 2]

    @staticmethod
    def furniture_of(obs: dict[str, Any]) -> list[dict[str, Any]]:
        return list((obs.get("location") or {}).get("furniture") or [])

    @staticmethod
    def player_of(obs: dict[str, Any]) -> dict[str, Any]:
        return obs.get("player") or {}

    @staticmethod
    def clock_of(obs: dict[str, Any]) -> dict[str, Any]:
        return obs.get("clock") or {}

    @staticmethod
    def location_of(obs: dict[str, Any]) -> dict[str, Any]:
        return obs.get("location") or {}

    @staticmethod
    def player_tile(obs: dict[str, Any]) -> tuple[int, int]:
        xy = (obs.get("player") or {}).get("tile") or [0, 0]
        return (int(xy[0]), int(xy[1]))

    @staticmethod
    def day_key(obs: dict[str, Any]) -> tuple[int, str, int]:
        c = obs.get("clock") or {}
        return (int(c.get("year") or 0), str(c.get("season") or ""), int(c.get("day") or 0))

    @staticmethod
    def time_of_day(obs: dict[str, Any]) -> int:
        return int((obs.get("clock") or {}).get("timeOfDay") or 0)

    @staticmethod
    def weather(obs: dict[str, Any]) -> str:
        return str((obs.get("clock") or {}).get("weather") or "")

    @staticmethod
    def stamina(obs: dict[str, Any]) -> float:
        return float((obs.get("player") or {}).get("stamina") or 0.0)

    @staticmethod
    def money(obs: dict[str, Any]) -> int:
        return int((obs.get("player") or {}).get("money") or 0)

    @staticmethod
    def is_in_bed(obs: dict[str, Any]) -> bool:
        return bool((obs.get("player") or {}).get("isInBed"))

    @staticmethod
    def can_state(obs: dict[str, Any]) -> dict[str, Any]:
        return (obs.get("player") or {}).get("wateringCan") or {}

    def water_left(self, obs: dict[str, Any]) -> int | None:
        """壶里还剩几格水；`bottomless`（无尽之壶）返回 None 表示"永远够用"。"""
        can = self.can_state(obs)
        if not can.get("present"):
            return None if can.get("bottomless") else 0
        if can.get("bottomless"):
            return None
        return int(can.get("waterLeft") or 0)

    # 观测要点（差分左/右半——只记"变化了没"需要的字段，别把整个快照写进日志）
    @staticmethod
    def tile_essence(tv: dict[str, Any] | None) -> dict[str, Any] | None:
        if tv is None:
            return None
        keys = ("kind", "tool", "feature", "crop", "ripe", "watered", "plantable", "standable",
                "objId", "actionable")
        return {k: tv.get(k) for k in keys if k in tv}

    def tile_view(self, obs: dict[str, Any], tile: tuple[int, int]) -> dict[str, Any] | None:
        return self.tiles_of(obs).get(tile)

    # ------------------------------------------------------------------ 走位
    def stand_next_to(self, tile: tuple[int, int], *, timeout_ms: int = 15000) -> bool:
        """站到目标格的四邻之一（先挑"观测说能站"的、再挑近的），返回是否到位。"""
        obs = self.snap()
        pt = self.player_tile(obs)
        tiles = self.tiles_of(obs)
        cands = [(tile[0] + dx, tile[1] + dy) for dx, dy in NEIGHBORS]
        if pt in cands:
            return True
        # 排序：观测明确说 standable 的最优先；没观测到的其次；明确不可站的最后。再近的优先。
        def rank(t: tuple[int, int]) -> tuple[int, int]:
            tv = tiles.get(t)
            if tv is None:
                return (1, abs(t[0] - pt[0]) + abs(t[1] - pt[1]))
            return (0 if tv.get("standable") else 2, abs(t[0] - pt[0]) + abs(t[1] - pt[1]))

        for t in sorted(cands, key=rank):
            try:
                self.c.move_to(t[0], t[1], timeout_ms=timeout_ms)
                self.walk_steps += 1
                return True
            except BridgeError:
                continue
        return False

    def move_to(self, tile: tuple[int, int], *, timeout_ms: int = 15000) -> StepResult:
        r = StepResult(action="move", tile=tile)
        try:
            self.c.move_to(tile[0], tile[1], timeout_ms=timeout_ms)
            self.walk_steps += 1
        except BridgeError as exc:
            r.code, r.reason, r.receipt = "failed", "走不过去", _receipt(exc)
            return r
        obs = self.snap()
        now = self.player_tile(obs)
        if now != tile:
            r.code, r.reason = "failed", f"回执说到了，但观测显示人在 {now}"
            return r
        r.ok = True
        return r

    def ensure_location(self, name: str, *, tile: tuple[int, int] | None = None,
                        timeout_ms: int = 30000) -> StepResult:
        r = StepResult(action="move_to_location", tile=tile)
        obs = self.snap()
        if str((obs.get("location") or {}).get("name") or "") == name:
            r.ok, r.code, r.reason = True, "already", f"已经在 {name}"
            return r
        try:
            self.c.move_to_location(name, tile=tile, timeout_ms=timeout_ms)
        except BridgeError as exc:
            r.code, r.reason, r.receipt = "failed", f"去 {name} 失败", _receipt(exc)
            return r
        obs = self.snap()
        now = str((obs.get("location") or {}).get("name") or "")
        if now != name:
            r.code, r.reason = "failed", f"回执说到了，但观测显示还在 {now}"
            return r
        r.ok = True
        return r

    # ------------------------------------------------------------- 单格：清障
    def clear(self, tile: tuple[int, int], *, cut_grass: bool = True) -> StepResult:
        """清掉这一格的障碍。**先判后动**：判据说现在干不了就一次都不挥。

        顺序：观测 kind →
          * 树/果树/资源堆/灌木/放置物：`skipped`（不该用锄头/镰刀动，写清原因）；
          * 有作物 / 缺这类障碍要用的工具：`skipped`（**不动手**，判据写进 `reason`）；
          * weed/twig/stone：`use_tool(auto)` 清（Mod 自己挑斧/镐/锄、失败换工具），
            判据 = 该格 kind 不再属于 DEBRIS_KINDS；
          * grass：`use_tool(scythe)` 割（**有作物绝不动手**——镰刀会连作物一起割掉），
            判据 = 该格 kind **不再是 grass**。

        【为什么只挥一次】Mod 的 `use_tool(auto)` 在**一次调用里**就会按种类换工具重试；
        脑再补一刀是纯粹的浪费 —— 真机 run1 的 (58,21)/(56,21) 两格各被连挥两下、世界纹丝不动。
        挥完还是一样 ⇒ 如实记 `skipped` + `proven_inert`（`longrun._mark_blocked` 当天封格）。

        【grass 的判据与限制】"割草成功"只认**观测前后差分**：`kind` 离开 grass 才算成。
        而观测口径**分不清"草"与"草下面的东西"**：`tiles[]` 是 `objects` + `terrainFeatures`
        两份记录按离玩家距离排序后的清单，`kind=grass` 只说明"这一格有 `Grass` 地形特征"，
        不保证没有别的层（脑侧 `tiles_of` 按格取最后一条，同格多条记录只留一条）。

        所以"挥了镰刀还是 grass"按 `tools\\run-plot.py` 的既有口径记 **skipped 而不是 failed**
        —— "草不该用锄头锄"是跳过，不是我们做失败了。真机 run1 那两格走的就是这条路：
        快照里镰刀**在背包里**（`logs\\observe-farm-sample.json` slot 4 = `(W)47` Scythe）
        ⇒ 不是"缺工具"，是挥了没变；根因（Mod 侧镰刀判据 / 站位）由分析侧另案钉。
        """
        r = StepResult(action="clear", tile=tile)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.before = self.tile_essence(tv)
        kind = str((tv or {}).get("kind") or "")

        if (tv or {}).get("crop"):
            r.code, r.reason = "skipped", "这一格有作物，清障会伤到它"
            return r
        if kind in SKIP_KINDS:
            r.code, r.reason = "skipped", SKIP_KINDS[kind]
            return r

        want_grass = kind == GRASS_KIND
        if kind not in DEBRIS_KINDS and not want_grass:
            r.ok, r.code = True, "already"
            r.reason = f"没有需要清的障碍（kind={kind or '未知'}）"
            return r
        if want_grass and not cut_grass:
            r.code, r.reason = "skipped", "调用方要求不割草（镰刀会连作物一起割）"
            r.proven_inert = True
            return r

        # ---- 先判后动：判据全部来自观测，动手之前就能拦下 ----
        want = KIND_TOOL.get(kind, "auto")
        miss = tool_missing_reason(self.player_of(obs), want)
        if miss:
            r.code = "skipped"
            r.proven_inert = True
            r.reason = f"判据说这格现在清不掉 ⇒ 不动手：{miss}；{_work_context(obs)}"
            return r
        if not self.stand_next_to(tile):
            r.code, r.reason = "failed", "四邻都站不过去"
            return r

        tool = "scythe" if want_grass else "auto"
        try:
            self.c.use_tool(tile, tool=tool, timeout_ms=15000)
        except BridgeError as exc:
            r.receipt = _receipt(exc)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.after = self.tile_essence(tv)
        kind_now = str((tv or {}).get("kind") or "")
        gone = (kind_now not in DEBRIS_KINDS) if not want_grass else (kind_now != GRASS_KIND)
        if gone:
            r.ok = True
            r.reason = f"已清掉（kind {kind or '未知'} → {kind_now or '未知'}）"
            return r
        # 挥了一次、世界没变 ⇒ 这一格今天已被证明干不动：记 skipped（不是 failed，
        # 见上面的 grass 限制），并打 proven_inert 让上层当天封格（第 3 次绝不会再发起）。
        r.code = "skipped"
        r.proven_inert = True
        r.reason = (f"挥了一次（{tool}）这格还是 {kind_now or '未知'}"
                    f"⇒ 判据「kind 离开 {kind or '未知'}」未满足；{_work_context(obs)}")
        return r

    # ------------------------------------------------------------- 单格：锄地
    def till(self, tile: tuple[int, int]) -> StepResult:
        """锄地。判据 = 该格 `kind` 变成 `dirt`（`plantable` 是加分项，不是判据）。

        **先判后动**：`till_blocked_by` 的判据（有作物 / 有 feature / 有 objId / 没锄头）命中时
        一次都不挥，把是哪条判据拦下的写进 `reason` —— 真机 (73,25) 一带就是"Mod 说可锄、
        观测里有未知地形特征"，锄 16 下白烧 60+ 体力（用户 m01804）。
        """
        r = StepResult(action="till", tile=tile)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.before = self.tile_essence(tv)
        kind = str((tv or {}).get("kind") or "")

        if kind == "dirt":
            r.ok, r.code, r.reason = True, "already", "已经是耕地"
            return r
        if (tv or {}).get("crop"):
            r.code, r.reason = "skipped", "这一格有作物，不能再锄"
            return r
        if kind in SKIP_KINDS:
            r.code, r.reason = "skipped", SKIP_KINDS[kind]
            return r
        if kind == GRASS_KIND:
            r.code, r.reason = "skipped", "草（先用镰刀割掉；锄头锄不出耕地）"
            return r
        if tv is None and tile not in self.tillable_of(obs):
            r.code, r.reason = "skipped", "游戏不认为这格可锄（无 Diggable 属性）"
            return r
        if kind in DEBRIS_KINDS:
            r.code, r.reason = "skipped", f"还有障碍（{kind}），先清障"
            return r
        why = till_blocked_by(tv, self.player_of(obs))
        if why:
            r.code = "skipped"
            r.proven_inert = True
            r.reason = f"判据说这格现在锄不了 ⇒ 不动手：{why}"
            return r
        if not self.stand_next_to(tile):
            r.code, r.reason = "failed", "四邻都站不过去"
            return r

        try:
            self.c.use_tool(tile, tool="hoe", timeout_ms=15000)
        except BridgeError as exc:
            r.receipt = _receipt(exc)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.after = self.tile_essence(tv)
        if (tv or {}).get("kind") == "dirt":
            r.ok = True
            r.reason = "锄出耕地（kind → dirt）"
            return r
        r.code = "failed"
        r.reason = f"锄完不是 dirt（kind={str((tv or {}).get('kind') or '未知')}）；{_work_context(obs)}"
        return r

    # ------------------------------------------------------------- 单格：播种
    def plant(self, tile: tuple[int, int], *, seed: str | None = None) -> StepResult:
        """播种。判据 = 该格 `crop` 非空。

        种子选择：显式给的 > 构造时给的 > 背包里堆叠最多的那种（`seed_items`）。
        没种子时回 `no_seed`（**全局缺料**，调用方该去补货，而不是逐格重试）。
        """
        r = StepResult(action="plant", tile=tile)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.before = self.tile_essence(tv)
        if (tv or {}).get("crop"):
            r.ok, r.code, r.reason = True, "already", f"已经有作物（crop={tv.get('crop')}）"
            return r
        if str((tv or {}).get("kind") or "") != "dirt":
            r.code, r.reason = "skipped", f"不是耕地（kind={str((tv or {}).get('kind') or '未知')}）"
            return r

        items = seed_items(self.player_of(obs))
        if not items:
            r.code, r.reason = "no_seed", "背包里没有种子"
            return r
        sid = seed or self.seed or items[0][0]
        have = sum(n for i, _nm, n in items if i == sid)
        if have <= 0:
            r.code, r.reason = "no_seed", f"背包里没有种子 {sid}（现有：{items}）"
            return r

        if not self.stand_next_to(tile):
            r.code, r.reason = "failed", "四邻都站不过去"
            return r
        try:
            self.c.plant(sid, tile, timeout_ms=20000)
        except BridgeError as exc:
            r.receipt = _receipt(exc)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        after = self.tile_essence(tv)
        left = sum(n for i, _nm, n in seed_items(self.player_of(obs)) if i == sid)
        r.after = {"tile": after, "seed_stack": left}
        if (tv or {}).get("crop"):
            r.ok = True
            r.reason = f"已种下 {sid}（crop={tv.get('crop')}，种子 {have}→{left}）"
            return r
        if left <= 0:
            r.code, r.reason = "no_seed", f"种子 {sid} 用光且这一格没长出作物"
            return r
        r.code = "failed"
        r.reason = f"种完这一格没有 crop（种子 {have}→{left}）"
        return r

    # ------------------------------------------------------------- 单格：播种+浇水
    def sow(self, tile: tuple[int, int], *, seed: str | None = None) -> StepResult:
        """播完**立刻浇这一格**（用户 m01847："种一个浇水一下"）。

        真机理由：站着的位置本来就是播种的位置，紧接着浇水不用多走路；等一批种完再统一回来浇，
        就要把整片地再走一遍（时间和体力都更贵），而且"种了却没浇"是当天不可补的损失。
        判据 = `crop` 出现**且** `watered` 为 true；只成了一半时（壶空了）如实记
        `need_refill`，但播种成果写进 `after`，上层补水后只需回来浇水。
        """
        pr = self.plant(tile, seed=seed)
        if not pr.ok:
            return pr
        wr = self.water(tile)
        seed_stack = None
        if isinstance(pr.after, dict):
            seed_stack = pr.after.get("seed_stack")
        if wr.ok:
            pr.reason = f"{pr.reason}；紧接着浇水：{wr.reason}"
            pr.after = {"tile": wr.after, "seed_stack": seed_stack}
            return pr
        pr.ok = False
        pr.code = "need_refill" if wr.code == "need_refill" else "failed"
        pr.reason = f"{pr.reason}；但浇水没成：{wr.reason}"
        pr.after = {"tile": wr.after, "seed_stack": seed_stack}
        return pr

    # ------------------------------------------------------------- 单格：浇水
    def water(self, tile: tuple[int, int]) -> StepResult:
        """浇水。判据 = 该格 `watered` 变 true。

        壶空了（且不是无尽之壶）→ `need_refill`：这是**前置条件问题**，
        调用方该先去补水再回来，而不是把这一格记成"浇不动"。
        """
        r = StepResult(action="water", tile=tile)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.before = self.tile_essence(tv)
        if not (tv or {}).get("crop"):
            r.code, r.reason = "skipped", "这一格没有作物"
            return r
        if (tv or {}).get("watered"):
            r.ok, r.code, r.reason = True, "already", "今天已经浇过了"
            return r
        left = self.water_left(obs)
        r.before = {"tile": r.before, "waterLeft": left}
        if left is not None and left <= 0:
            r.code, r.reason = "need_refill", "壶里没水了（先补水）"
            return r

        if not self.stand_next_to(tile):
            r.code, r.reason = "failed", "四邻都站不过去"
            return r
        try:
            self.c.use_tool(tile, tool="can", timeout_ms=15000)
        except BridgeError as exc:
            r.receipt = _receipt(exc)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        left_after = self.water_left(obs)
        r.after = {"tile": self.tile_essence(tv), "waterLeft": left_after}
        if (tv or {}).get("watered"):
            r.ok = True
            r.reason = f"已浇（水 {left}→{left_after}）"
            return r
        # 回执报错但水确实少了 ⇒ 这一格其实浇上了（世界在前、回执在后）
        if left is not None and left_after is not None and left_after < left and tv is not None:
            r.code = "failed"
            r.reason = f"水少了（{left}→{left_after}）但该格 watered 仍为 false"
            return r
        r.code = "failed"
        r.reason = f"浇完 watered 仍为 false（水 {left}→{left_after}）"
        return r

    # ------------------------------------------------------------- 单格：收获
    def harvest(self, tile: tuple[int, int]) -> StepResult:
        """收获成熟作物：走游戏自己的 `checkAction`（`interact`），判据 = 该格作物没了。

        ⚠️ 这条路的真机证据还薄（本轮 3 日连跑里作物尚未成熟），所以失败时**如实记失败**，
        不假装收过。
        """
        r = StepResult(action="harvest", tile=tile)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.before = self.tile_essence(tv)
        if not (tv or {}).get("crop"):
            r.code, r.reason = "skipped", "这一格没有作物"
            return r
        if not (tv or {}).get("ripe"):
            r.code, r.reason = "skipped", "还没成熟"
            return r
        if not self.stand_next_to(tile):
            r.code, r.reason = "failed", "四邻都站不过去"
            return r
        try:
            self.c.interact(tile, timeout_ms=8000)
        except BridgeError as exc:
            r.receipt = _receipt(exc)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.after = self.tile_essence(tv)
        if not (tv or {}).get("crop"):
            r.ok = True
            r.reason = "作物已收走（crop 变空）"
            return r
        r.code = "failed"
        r.reason = "交互后作物还在（可能没摘到）"
        return r

    # ------------------------------------------------------------- 补水
    def refill_can(self, *, timeout_ms: int = 15000) -> StepResult:
        """走到最近的可补水格旁边、挥壶补水。判据 = `waterLeft` 变大（**不是**回执）。

        判据为什么不能是回执：Mod 的 can 判据是"目标格出现 HoeDirt 且 watered"，
        对着水面挥壶永远不满足 ⇒ 回执多半是 `tool_ineffective`；但水**确实**补上了。
        这里只认 `player.wateringCan.waterLeft` 的前后差。
        """
        r = StepResult(action="refill")
        obs = self.snap()
        before = self.can_state(obs)
        r.before = {"waterLeft": self.water_left(obs), "location": (obs.get("location") or {}).get("name")}
        if not before.get("present"):
            r.code, r.reason = "failed", "背包里没有浇水壶"
            return r
        if before.get("bottomless"):
            r.ok, r.code, r.reason = True, "already", "无尽之壶，不需要补水"
            return r

        spots = self.refill_of(obs)
        if not spots:
            r.code, r.reason = "no_target", "本次观测里没有可补水的格子（refillTiles 为空）"
            return r
        pt = self.player_tile(obs)
        spots = sorted(spots, key=lambda t: abs(t[0] - pt[0]) + abs(t[1] - pt[1]))
        tried = 0
        for spot in spots[:6]:
            if not self.stand_next_to(spot):
                continue
            tried += 1
            try:
                self.c.use_tool(spot, tool="can", timeout_ms=timeout_ms)
            except BridgeError as exc:
                r.receipt = _receipt(exc)      # 预期多半是 tool_ineffective：判据看水位
            obs = self.snap()
            left_after = self.water_left(obs)
            r.after = {"waterLeft": left_after}
            if left_after is None or (r.before["waterLeft"] is not None and left_after > r.before["waterLeft"]):
                r.ok = True
                r.reason = f"补水成功（waterLeft {r.before['waterLeft']} → {left_after}）"
                return r
        r.code = "failed"
        r.reason = f"试了 {tried} 个补水点，水位没涨（{r.before.get('waterLeft')} → {r.after.get('waterLeft') if r.after else '?'}）"
        return r

    # ------------------------------------------------------------- 睡觉（跨日唯一正路）
    def bed_tile(self, obs: dict[str, Any]) -> tuple[int, int] | None:
        for f in self.furniture_of(obs):
            if f.get("isBed"):
                xy = f.get("tile") or []
                if len(xy) >= 2:
                    return (int(xy[0]), int(xy[1]))
        return None

    def sleep(self, *, home: str = "FarmHouse", timeout_ms: int = 180000) -> StepResult:
        """睡觉跨日：回家 → （必要时）对床 `interact` 引出游戏自己的提问 → `sleep` 应答。

        【为什么必须由脑主动做】真机发现：世界加载状态下**时间照走**，闲置到 02:00 游戏会
        自动 pass-out 睡觉 —— 那是"没人管"的结果，不是自动化。主动睡觉才是跨日正路，
        也只有它能在验收里区分"我们睡了"和"我们被系统睡了"。
        """
        r = StepResult(action="sleep")
        obs = self.snap()
        day_before = self.day_key(obs)
        r.before = {"day": list(day_before), "timeOfDay": self.time_of_day(obs),
                    "stamina": self.stamina(obs)}
        loc = str((obs.get("location") or {}).get("name") or "")
        if loc != home:
            mv = self.ensure_location(home, timeout_ms=30000)
            if not mv.ok:
                r.code, r.reason, r.receipt = "failed", f"回不了 {home}：{mv.reason}", mv.receipt
                return r
            obs = self.snap()

        bed = self.bed_tile(obs)
        if bed is not None and not self.is_in_bed(obs):
            # 对床按"用"键会把游戏自己的 `Go to sleep for the night?` 引出来，
            # 之后 `sleep` 技能就能用游戏的口径应答（`answerDialogueAction("Sleep_Yes")`）。
            if self.stand_next_to(bed):
                try:
                    self.c.interact(bed, timeout_ms=8000)
                except BridgeError as exc:
                    r.receipt = _receipt(exc)
                obs = self.snap()
            else:
                r.reason = "床边站不过去（继续直接尝试 sleep）"

        try:
            self.c.sleep(timeout_ms=timeout_ms)
        except BridgeError as exc:
            r.code, r.reason, r.receipt = "failed", "睡觉请求失败", _receipt(exc)
            return r

        obs = self.snap()
        day_after = self.day_key(obs)
        r.after = {"day": list(day_after), "timeOfDay": self.time_of_day(obs),
                   "stamina": self.stamina(obs)}
        if day_after != day_before:
            r.ok = True
            r.reason = (f"已跨日：{day_before[1]} {day_before[2]}日 → {day_after[1]} {day_after[2]}日"
                        f"（体力 {r.before['stamina']:g} → {self.stamina(obs):g}）")
            return r
        r.code = "failed"
        r.reason = f"日期没变（还是 {day_after[1]} {day_after[2]}日，timeOfDay={self.time_of_day(obs)}）"
        return r

    # ------------------------------------------------------------- 买种子
    def buy(self, item: str, count: int = 10, *, shop: str = "SeedShop",
            timeout_ms: int = 25000) -> StepResult:
        """买种子。判据 = 钱减少 **且** 背包里该物品变多（回执里游戏返回值不是成败，见开发日志 023）。"""
        r = StepResult(action="buy")
        obs = self.snap()
        money_before = self.money(obs)
        have_before = _count_item(self.player_of(obs), item)
        r.before = {"money": money_before, "item": have_before}
        try:
            self.c.buy(item, count, shop=shop, timeout_ms=timeout_ms)
        except BridgeError as exc:
            r.receipt = _receipt(exc)
        obs = self.snap()
        money_after = self.money(obs)
        have_after = _count_item(self.player_of(obs), item)
        r.after = {"money": money_after, "item": have_after}
        if have_after > have_before and money_after < money_before:
            r.ok = True
            r.reason = (f"买到 {have_after - have_before} 个 {item}（钱 {money_before}→{money_after}）")
            return r
        r.code = "failed"
        r.reason = (f"没成交：物品 {have_before}→{have_after}，钱 {money_before}→{money_after}"
                    + (f"；回执={r.receipt}" if r.receipt else ""))
        return r

    def load_save(self, save: str | None = None) -> StepResult:
        r = StepResult(action="load_save")
        try:
            self.c.load_save(save) if save else self.c.load_save()
        except BridgeError as exc:
            r.code, r.reason, r.receipt = "failed", "读档失败", _receipt(exc)
            return r
        obs = self.snap()
        if not obs.get("hasSaveLoaded"):
            r.code, r.reason = "failed", "读档回执 ok，但观测 hasSaveLoaded 仍为 false"
            return r
        r.ok = True
        r.reason = f"已读档（{self.location_of(obs).get('name')} {self.player_tile(obs)}）"
        return r

    # ------------------------------------------------------------------ 阶段
    def run_stage(
        self,
        stage: str,
        tiles: list[tuple[int, int]],
        *,
        min_stamina: float = 12.0,
        max_steps: int = 200,
    ) -> StageResult:
        """把 `stage` 依次施加到 `tiles` 上，带体力闸门与"全局缺料"提前退出。

        体力闸门：`till`/`clear`/`water` 都吃体力，体力见底时**停下并如实说停在哪**
        （`stopped="stamina"`）—— 让上层决定是去睡还是换轻活，而不是让每一格都失败一遍。
        """
        action = STAGE_ACTION.get(stage, stage)
        res = StageResult(stage=stage, tiles=list(tiles))
        for i, tile in enumerate(tiles):
            if i >= max_steps:
                res.stopped, res.stopped_reason = "budget", f"达到本阶段格数上限 {max_steps}"
                break
            obs = self.snap()
            stam = self.stamina(obs)
            if action in ("clear", "till", "water", "harvest", "sow") and stam < min_stamina:
                res.stopped, res.stopped_reason = "stamina", f"体力 {stam:g} < {min_stamina:g}"
                break

            if action == "clear":
                st = self.clear(tile)
            elif action == "till":
                st = self.till(tile)
            elif action == "plant":
                st = self.plant(tile)
            elif action == "sow":
                st = self.sow(tile)
            elif action == "water":
                st = self.water(tile)
            elif action == "harvest":
                st = self.harvest(tile)
            else:  # pragma: no cover - 上层不该传未知阶段
                st = StepResult(action=action, tile=tile, code="failed", reason=f"未知阶段 {stage}")

            self.steps.append(st)
            res.steps.append(st)
            if st.code in ("no_seed", "need_refill"):
                res.stopped, res.stopped_reason = st.code, st.reason
                break
        return res


def _receipt(exc: BaseException) -> str:
    """回执摘要：`status: 文本`（**只是诊断**，不作为证据）。"""
    status = getattr(exc, "status", None) or type(exc).__name__
    return f"{status}: {str(exc)[:200]}"


def _count_item(player: dict[str, Any], item: str) -> int:
    want = str(item)
    total = 0
    for it in player.get("inventory") or []:
        if str(it.get("id")) == want or str(it.get("qualifiedId") or "") == want:
            total += int(it.get("stack") or 0)
    return total
