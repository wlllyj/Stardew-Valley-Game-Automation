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
    "ENV_BLOCK_STATUSES",
    "INCONCLUSIVE_STATUSES",
    "KIND_TOOL",
    "MAX_CLEAR_SWINGS",
    "SKIP_KINDS",
    "STAGE_ACTION",
    "TILE_INERT_STATUSES",
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

#: `clear()` 一次最多连挥几刀。普通镰刀一刀只把 `Grass.numberOfWeeds` 减 1（金镰刀减 2），
#: 而 `Grass.TryDropItemsOnCut` 只有在 `numberOfWeeds <= 0` 时才返回 true 并移除特征
#: ⇒ 一格 grass 最多要 4 刀（IL 级证据见 `docs/_analyze-longrun-run1.md`）。
MAX_CLEAR_SWINGS = 4

#: `use_tool` 回执里代表"**这一格本身**挥不动"的状态码（Mod 已换遍工具 / 前置条件不成立）
#: ⇒ 再重发同样的请求不会变，直接按"今天干不动"封格。
TILE_INERT_STATUSES = ("tool_ineffective", "precondition_failed")

#: `use_tool` 回执里代表"**现在整个环境**不让动手"的状态码 ⇒ 记 failed 但**不封格**（下轮还能试）。
#: `world_fading` = 屏幕渐黑/过场（Mod 侧 `fadeToBlack`/`nonWarpFade`，见 `UseToolSkill.Swing()` 的门卫）。
#: `busy` = `MainThreadDispatcher.RejectBusy()`（mod/AgentFarm.Bridge/MainThreadDispatcher.cs:159-169）
#:   在"已有技能正在执行"时**零成本快速拒绝**：任何 skill 都会拿到它（含 `use_tool`）。
#:   它不是这一格的属性、也不是我们的错，下一秒队列空了就能成 ⇒ 必须算环境挡路。
#:   真机触发时序很现实：run2 有两次 180s 客户端超时（Mod 还在跑长技能），期间任何新 exec 都回 busy。
#: 这些码**全桥通用**（不止 `clear()`）：`MoveToLocationSkill`/`PlantSkill`/`StepMover` 都会回
#: `no_save`/`ui_modal` ⇒ 分类必须按 `exc.status` 统一做，见 `_classify_status`。
ENV_BLOCK_STATUSES = ("no_save", "ui_modal", "world_fading", "busy")

#: `use_tool` 回执里代表"请求发出去了、但**没拿到世界的结论**"的状态码（task-22）：
#: `timeout` = 墙钟超时（可能一次都没挥出去）、`error` = Mod 侧异常/`ok=false` 却没给码。
#: `stale` = `BridgeHost.cs:538-553`：调用方传的 `based_on_seq` 比 `Skills.StaleSeqThreshold` 旧
#:   （协议上任何 skill 都可能，目前只有 `move_to*` 会带这个参数）⇒ 这是**我们自己传参错了**，
#:   必须可见、必须占配额（连续 stale 应被限流成 `capped`、当天 needs_review），不能被当成
#:   环境抖动无限免费重试。
#: 这类**既不能**宣布"这一格干不动"（不许封格），**也不能**当没发生（它真烧了墙钟）
#: ⇒ 记 failed + `inconclusive`：`longrun._mark_blocked` 跳过它，`_count_attempts` 仍计配额。
#: ⚠️ 只有 `timeout`/`error`/`stale` 算"没结论"（Lead m01763 + task-28 N4-1）：回执 `ok` /
#: 缺 status / Mod 的结论类码都是**真实回应**，世界没变就是"这一刀白挥"，走结论路径。
#: ⚠️ 与 `TILE_INERT_STATUSES`/`ENV_BLOCK_STATUSES` **互斥**，三者并集覆盖的是
#: **"bridge 层可能回给 brain 的通用码 + `use_tool` 自己的码"**（单测
#: `test_status_classes_cover_mod_codes_are_disjoint` 钉住）；其它 skill 专属的码
#: （如 `sleep_no_question`）**有意**落进兜底桶，由各自的调用点按语义处理。
INCONCLUSIVE_STATUSES = frozenset({"timeout", "error", "stale"})

#: `sleep` 回执里"游戏自己**没有**弹出睡觉提问"的状态码：Mod 拼不出 `Sleep` 前缀的应答键时
#: **秒级**报它（不会再白等 3 分钟）。判据与 IL 定案见 `docs/_il-sleep-path.md`。
SLEEP_NO_QUESTION = "sleep_no_question"

#: `sleep` 失败时值得原样透传进 `code` 的状态码（其余一律折成 `"failed"`，
#: 免得把 Mod 的任意 status 当成脑侧语义写进 journal）。
SLEEP_FAIL_CODES = (
    SLEEP_NO_QUESTION, "timeout", "no_save", "ui_modal", "world_fading",
    "precondition_failed", "error",
)

#: 睡觉提问的文本线索：只用来把"开着的提问"分类成 sleep/other（**写诊断用**），
#: 不据此发送、也不据此拒绝任何请求（真值判定只认 `ui.dialogueIsQuestion` + Mod 回执）。
SLEEP_QUESTION_HINTS = ("sleep", "睡觉", "上床", "就寝", "bed")

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
    #: **环境挡路**（`no_save`/`ui_modal`/`world_fading`，task-22）：不是"这一格干不动"
    #: ⇒ `longrun._mark_blocked` 不封格、`_count_attempts` **不占当天配额**（下轮还能试）。
    env_block: bool = False
    #: **没有结论**（`timeout`/`error`/任何没见过的码，task-22）：不许封格，但**仍占配额**
    #: —— 它真烧了墙钟；持续如此就该被限流成 `capped`，当天如实 `needs_review`。
    inconclusive: bool = False

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
        if self.env_block:
            d["env_block"] = True
        if self.inconclusive:
            d["inconclusive"] = True
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
    def env_block_count(self) -> int:
        """**环境挡路**的步数（渐黑/模态/没存档）：这些格子**不算**被证明干不动。"""
        return sum(1 for s in self.steps if s.env_block)

    @property
    def inconclusive_count(self) -> int:
        """**没拿到结论**的步数（超时/异常）：不许封格，但确实烧了墙钟 ⇒ 占本日配额。"""
        return sum(1 for s in self.steps if s.inconclusive)

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


def _classify_status(status: str) -> tuple[bool, bool]:
    """把 Mod 回执的 `status` 分成两类（**全桥通用**，task-22）：`(env_block, inconclusive)`。

    为什么必须集中在脑侧一处：这些码不是 `clear()` 专属 —— `move_to`/`move_to_location`/
    `sow`/`water`/`harvest`/`refill` 都会遇到渐黑（`world_fading`）和模态（`ui_modal`），
    而 `longrun._count_attempts` **不带动作过滤** ⇒ 任何一次瞬时环境抖动都可能把该格推到
    `MAX_TILE_ATTEMPTS` → `capped` → `stage_exhausted` → 当天被杀。

    三分类（互斥；并集覆盖 **bridge 层通用码 + `use_tool` 的码**，其它 skill 专属码有意走兜底桶）：
      * `ENV_BLOCK_STATUSES`    ⇒ `(True, False)`：**环境挡路**——不是这一格的问题，下轮还能试
        （含 `busy`＝`MainThreadDispatcher.RejectBusy()`：任何 skill 都可能被"同一时刻只允许一个 exec"
        零成本拒绝；也含 `no_save`/`ui_modal`/`world_fading`）；
      * `INCONCLUSIVE_STATUSES` ⇒ `(False, True)`：**没结论**——`timeout`/`error`，以及 `stale`
        （我们自己传了过旧的 `based_on_seq` ⇒ 我们的错，必须可见、必须占配额）；
      * 其余一切（`TILE_INERT_STATUSES`、空串、`ok`、以及类别未枚举的新码）
        ⇒ `(False, False)`：**Mod 真的回应了**——世界没变就算"这一刀白挥"，归 task-7 的结论路径。

    防自旋（task-28 N4-1）：`env_block` 不占 `_count_attempts` 配额，所以**不能**只靠"不计配额"；
    持续 `busy` 的有界策略在 `longrun._count_attempts`（同格同日连续被挡超过 `MAX_ENV_ATTEMPTS`
    ⇒ 从下一次起按"没结论"占配额，最终 `capped` ⇒ 当天 needs_review）。

    裁定（Lead m01763）：`inconclusive` **只在"整轮一次真实请求都没发出去"时成立**。只要有一轮
    Mod 有回应（含"回执 ok 但观测没变"）并且达到了请求上限 ⇒ 仍按"挥满了没变"封格
    （`skipped` + `proven_inert`）：`proven_inert` 要说的是"这一格我确实动过、动完还是原样"，
    而 `inconclusive` 说的是"我没拿到证据"，两者混在一起会让 run3 把环境抖动当成地块不可动。
    """
    s = str(status or "")
    if s in ENV_BLOCK_STATUSES:
        return (True, False)
    if s in INCONCLUSIVE_STATUSES:
        return (False, True)
    return (False, False)


def _mark_status(r: StepResult, status: str) -> None:
    """按 `status` 在 `StepResult` 上打 `env_block` / `inconclusive` 标记（就地，累加）。"""
    env, inconclusive = _classify_status(status)
    if env:
        r.env_block = True
    if inconclusive:
        r.inconclusive = True


def _exc_status(exc: BaseException) -> str:
    """从 `BridgeError` 里取机器可读的 `status`；**没带 status 的异常按 `error` 算**。

    为什么不是空串：空串在 `_classify_status` 里表示"回执 ok、这一刀真挥出去了"，
    而"网络/协议异常"恰恰是**最没有任何结论**的一种 ⇒ 必须归到 inconclusive。
    """
    return str(getattr(exc, "status", "") or "error")


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
    def ui_of(obs: dict[str, Any]) -> dict[str, Any]:
        """观测里的 `ui` 块（v3 起才有）。空字典 = 判不准（旧 Mod / 精简观测）。"""
        ui = obs.get("ui")
        return ui if isinstance(ui, dict) else {}

    @classmethod
    def question_state(cls, obs: dict[str, Any]) -> str:
        """开着的提问是哪一种：`"sleep"` / `"other"` / `"none"` / `"unknown"`。

        `"unknown"` = 这份观测没有 `ui` 块（判不准）。**只作诊断**：放不放行请求看
        `sleep_ready()`，而真值判定留给 Mod（它会秒级回 `sleep_no_question` 或超时）。
        """
        ui = cls.ui_of(obs)
        if not ui:
            return "unknown"
        if ui.get("dialogueIsQuestion") is not True:
            return "none"
        text = str(ui.get("activeMenuText") or "") + " " + " ".join(
            str(x) for x in (ui.get("dialogueResponses") or []))
        low = text.lower()
        return "sleep" if any(h in low for h in SLEEP_QUESTION_HINTS) else "other"

    @classmethod
    def question_open(cls, obs: dict[str, Any]) -> bool:
        return cls.ui_of(obs).get("dialogueIsQuestion") is True

    @classmethod
    def sleep_ready(cls, obs: dict[str, Any]) -> tuple[bool, str]:
        """现在能不能睡觉：(就绪?, 一句判据)。

        【判据（2026-10-13 IL 定案，`docs/_il-sleep-path.md` §5）】主判据是**游戏自己弹出了
        睡觉提问**；`isInBed` 只作交叉参考 —— 它只在"临时床"分支被置 true，而且 pass-out
        之后会残留 true（day 11 06:40 在 [9,9] 走动时还是 true）⇒ **不能单靠它**。
        """
        state = cls.question_state(obs)
        if state == "sleep":
            return True, "游戏自己弹出了睡觉提问"
        if state == "other":
            return True, "开着提问（文本没提到 sleep ⇒ 仍按「提问已弹出」放行，由 Mod 判定）"
        if cls.is_in_bed(obs):
            return True, "观测 isInBed=true（交叉参考；提问可能在 Mod 看来已开着）"
        if state == "unknown":
            return True, "这份观测没有 ui 块 ⇒ 判不准，直接交给 Mod 判定"
        return False, "没有睡觉提问、观测也不在床上"

    def _sleep_probe(self, obs: dict[str, Any]) -> dict[str, Any]:
        """睡觉前后的现场（task-6 §4 R1：journal 必须能看出"上没上床 / 提问开没开"）。"""
        ui = self.ui_of(obs)
        return {
            "day": list(self.day_key(obs)),
            "timeOfDay": self.time_of_day(obs),
            "stamina": self.stamina(obs),
            "isInBed": self.is_in_bed(obs),
            "question": self.question_state(obs),
            "activeMenu": ui.get("activeMenu"),
        }

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
            # 渐黑/模态/没存档/超时都是**环境或没结论**：不许让上层把这一步算成"这格走不动"。
            _mark_status(r, _exc_status(exc))
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
            _mark_status(r, _exc_status(exc))       # 环境挡路 / 没结论 ⇒ 不封格
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

        【为什么要连挥到上限】草是**多刀**地形特征：普通镰刀一刀只把 `Grass.numberOfWeeds` 减 1
        （金镰刀 2），只有减到 0 才移除特征（`MAX_CLEAR_SWINGS = 4`，IL 证据见
        `docs/_analyze-longrun-run1.md`）⇒ "挥一刀没变"**不等于**"干不动"。
        所以脑这一层带着新观测重试：**挥到 kind 变化为止，最多 4 刀**，
        只有挥满上限（或 Mod 自己回「工具全无效」`TILE_INERT_STATUSES`）才记
        `skipped` + `proven_inert` 封格。
        反过来，Mod 明确说"这格挥不动/工具全无效/前置不成立"时**立刻停手**——真机 run1 的
        (58,21)/(56,21) 就是各被连挥两下、世界纹丝不动，纯属白费体力。

        【Mod 侧也会重试】一次 `use_tool` 内部自己会挥到 `MaxSwings=6` 并按种类换工具，
        所以正常一格草**一次请求就割完**；脑只在请求没达成（超时/异常/回执 ok 但观测没变）时补刀。

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
        traces: list[str] = []
        statuses: list[str] = []    # 每次请求的 Mod status（进 after，供事后复核）
        conclusive = False          # Mod 说"这一格挥不动"（换遍工具/前置条件不成立）
        env_block = ""              # Mod 说"现在整个环境不让动手"
        swung = False               # 至少有一次请求**真的挥出去了**（回执 ok 但世界没变）
        for i in range(1, MAX_CLEAR_SWINGS + 1):
            status = ""
            try:
                res = self.c.use_tool(tile, tool=tool, timeout_ms=15000)
                r.receipt = _receipt_of(res)
                # 真桥对 `ok=false` 是**抛** BridgeError；但假桥/未来实现也可能**回**出来，
                # 所以两种都读：状态码决定"要不要再补刀"，不靠异常类型。
                if isinstance(res, dict):
                    status = str(res.get("status") or ("" if res.get("ok", True) else "error"))
            except BridgeError as exc:
                status = str(getattr(exc, "status", "") or "")
                r.receipt = _receipt(exc)
            if status:
                statuses.append(status)
            obs = self.snap()
            tv = self.tile_view(obs, tile)
            r.after = self.tile_essence(tv)
            kind_now = str((tv or {}).get("kind") or "")
            traces.append(f"第{i}次请求→{kind_now or '未知'}")
            gone = (kind_now not in DEBRIS_KINDS) if not want_grass else (kind_now != GRASS_KIND)
            if gone:
                r.ok = True
                if isinstance(r.after, dict):
                    r.after = {**r.after, "requests": i, "statuses": list(statuses)}
                r.reason = (f"已清掉（kind {kind or '未知'} → {kind_now or '未知'}；"
                            f"{'、'.join(traces)}）")
                return r
            if status in TILE_INERT_STATUSES:
                conclusive = True
                break
            env, inconclusive = _classify_status(status)
            if env:
                env_block = status
                break
            if inconclusive:
                # 没拿到结论（超时/异常/没见过的码）：既不能封格，也不算"挥过了" ⇒ 补下一次请求。
                continue
            swung = True            # 回执没报错而世界没变 ⇒ 这一刀是真白挥的

        if env_block:
            # 环境问题（没存档/模态/渐黑）不是"这一格干不动"：记 failed、**不封格**，下轮可以再试。
            r.code = "failed"
            r.env_block = True
            if isinstance(r.after, dict):
                r.after = {**r.after, "requests": i, "statuses": list(statuses)}
            r.reason = (f"第 {i} 次清障被环境挡住（{env_block}）⇒ 这一格不算被证明干不动；{r.receipt}")
            return r

        if statuses and not swung and not conclusive:
            # 整轮**一次结论都没拿到**（全是 timeout/error/没见过的码）：我们连"刀到底挥出去了没"
            # 都不知道 ⇒ 不许写成"连挥 N 刀还是 X"。记 failed + inconclusive：不封格，但占本日配额。
            r.code = "failed"
            r.inconclusive = True
            if isinstance(r.after, dict):
                r.after = {**r.after, "requests": i, "statuses": list(statuses)}
            r.reason = (f"连续 {len(statuses)} 次请求没有拿到结论（statuses={'、'.join(statuses)}）"
                        f"⇒ 这一格不算被证明干不动（kind 仍 {kind_now or '未知'}）；{r.receipt}")
            return r

        # 挥满上限（或 Mod 自己就回「工具全无效」）这格仍纹丝不动 ⇒ 这一格今天已被证明干不动：
        # 记 skipped（不是 failed，见上面的 grass 限制），并打 proven_inert 让上层当天封格。
        r.code = "skipped"
        r.proven_inert = True
        if isinstance(r.after, dict):
            r.after = {**r.after, "requests": i, "statuses": list(statuses)}
        why = "Mod 回「工具全无效」" if conclusive else f"连挥 {MAX_CLEAR_SWINGS} 刀"
        r.reason = (f"{why}（{tool}）这格还是 {kind_now or '未知'}"
                    f"⇒ 判据「kind 离开 {kind or '未知'}」未满足"
                    f"（{'、'.join(traces)}；回执 {r.receipt or '无'}）；{_work_context(obs)}")
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

        status = ""
        try:
            self.c.use_tool(tile, tool="hoe", timeout_ms=15000)
        except BridgeError as exc:
            status = _exc_status(exc)
            r.receipt = _receipt(exc)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.after = self.tile_essence(tv)
        if (tv or {}).get("kind") == "dirt":
            r.ok = True
            r.reason = "锄出耕地（kind → dirt）"
            return r
        r.code = "failed"
        # 环境挡路（渐黑/模态）⇒ failed 但**不封格、不占配额**；超时/异常 ⇒ 不封格但占配额。
        _mark_status(r, status)
        r.reason = (f"锄完不是 dirt（kind={str((tv or {}).get('kind') or '未知')}）"
                    f"{f'；Mod status={status}' if status else ''}；{_work_context(obs)}")
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
        status = ""
        try:
            self.c.plant(sid, tile, timeout_ms=20000)
        except BridgeError as exc:
            status = _exc_status(exc)
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
        _mark_status(r, status)     # 环境挡路 / 没结论 ⇒ 不封格（`sow` 会把这两个标记继承上去）
        r.reason = (f"种完这一格没有 crop（种子 {have}→{left}）"
                    f"{f'；Mod status={status}' if status else ''}")
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
        # 底层（`plant` / `water`）打过的 env/inconclusive 标记必须**继承上来**：否则渐黑挡住浇水
        # 这一层会把"环境挡路"当成"这格种不下去"，`longrun` 又会把它当成封格/计配额的证据（task-22）。
        pr.env_block = pr.env_block or wr.env_block
        pr.inconclusive = pr.inconclusive or wr.inconclusive
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
        status = ""
        try:
            self.c.use_tool(tile, tool="can", timeout_ms=15000)
        except BridgeError as exc:
            status = _exc_status(exc)
            r.receipt = _receipt(exc)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        left_after = self.water_left(obs)
        r.after = {"tile": self.tile_essence(tv), "waterLeft": left_after}
        if (tv or {}).get("watered"):
            r.ok = True
            r.reason = f"已浇（水 {left}→{left_after}）"
            return r
        # 环境挡路（渐黑/模态）/ 没结论 ⇒ 不封格（task-22：`_count_attempts` 不带动作过滤，
        # 所以浇水/收获/走路上的一次瞬时抖动同样不能吃掉当天配额）。
        _mark_status(r, status)
        # 回执报错但水确实少了 ⇒ 这一格其实浇上了（世界在前、回执在后）
        if left is not None and left_after is not None and left_after < left and tv is not None:
            r.code = "failed"
            r.reason = f"水少了（{left}→{left_after}）但该格 watered 仍为 false"
            return r
        r.code = "failed"
        r.reason = (f"浇完 watered 仍为 false（水 {left}→{left_after}）"
                    f"{f'；Mod status={status}' if status else ''}")
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
        status = ""
        try:
            self.c.interact(tile, timeout_ms=8000)
        except BridgeError as exc:
            status = _exc_status(exc)
            r.receipt = _receipt(exc)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.after = self.tile_essence(tv)
        if not (tv or {}).get("crop"):
            r.ok = True
            r.reason = "作物已收走（crop 变空）"
            return r
        r.code = "failed"
        _mark_status(r, status)     # 渐黑/模态 ⇒ 不封格、不占配额；超时 ⇒ 不封格但占配额
        r.reason = (f"交互后作物还在（可能没摘到）{f'；Mod status={status}' if status else ''}")
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
        last_status = ""
        for spot in spots[:6]:
            if not self.stand_next_to(spot):
                continue
            tried += 1
            try:
                self.c.use_tool(spot, tool="can", timeout_ms=timeout_ms)
            except BridgeError as exc:
                last_status = _exc_status(exc)
                r.receipt = _receipt(exc)      # 预期多半是 tool_ineffective：判据看水位
            obs = self.snap()
            left_after = self.water_left(obs)
            r.after = {"waterLeft": left_after}
            if left_after is None or (r.before["waterLeft"] is not None and left_after > r.before["waterLeft"]):
                r.ok = True
                r.reason = f"补水成功（waterLeft {r.before['waterLeft']} → {left_after}）"
                return r
        r.code = "failed"
        _mark_status(r, last_status)    # 渐黑/模态挡住补水 ⇒ 不封格、不占配额（task-22 §8）
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

    def sleep(self, *, home: str = "FarmHouse", timeout_ms: int = 15000) -> StepResult:
        """睡觉跨日：回家 → **踩到床格**引出游戏自己的提问 → 确认（提问/在床上）→ `sleep` 应答。

        【为什么必须由脑主动做】真机发现：世界加载状态下**时间照走**，闲置到 02:00 游戏会
        自动 pass-out 睡觉 —— 那是"没人管"的结果，不是自动化。主动睡觉才是跨日正路，
        也只有它能在验收里区分"我们睡了"和"我们被系统睡了"。

        【2026-10-13 改成"踩床"（`docs/_il-sleep-path.md`，task-8）】
        * `GameLocation.answerDialogueAction` 是**字面量分派**：只有 `"Sleep_Yes"` 会走到
          `startSleep()`，别的键**静默 no-op**（回执 ok 完全不代表游戏做了事）
          ⇒ 判据只能是观测差分。
        * 引出提问的正路是让游戏自己 `checkAction(bed)`：**踩到床格**
          （`move_to(bed, allow_bed=True)`）。旧实现 `stand_next_to(bed)` + `interact(bed)`
          在真机上**从未**把提问弹出来（run2 全日志 `answerDialogue(` 出现 0 次）。
        * 判据**不是** `isInBed`（见 `sleep_ready`）；提问没弹出来时 Mod 会**秒级**回
          `sleep_no_question`（携 `lastQuestionKey`/`isInBed`/`activeMenu` 诊断），所以这里
          不再白等 180s（Mod 侧跨日预算也从 120s 收到 15s）。
        """
        r = StepResult(action="sleep")
        obs = self.snap()
        day_before = self.day_key(obs)
        r.before = self._sleep_probe(obs)
        loc = str((obs.get("location") or {}).get("name") or "")
        if loc != home:
            mv = self.ensure_location(home, timeout_ms=30000)
            if not mv.ok:
                r.code, r.reason, r.receipt = "failed", f"回不了 {home}：{mv.reason}", mv.receipt
                return r
            obs = self.snap()

        # ① 用游戏自己的路径把睡觉提问引出来：**踩到床格**（allow_bed=True 才不会被 Mod 拒绝）
        diag: list[str] = []
        bed = self.bed_tile(obs)
        ready, why = self.sleep_ready(obs)
        if bed is not None and not ready:
            try:
                self.c.move_to(bed[0], bed[1], allow_bed=True, timeout_ms=10000)
                diag.append(f"已踩床格 {bed}（allow_bed=True，引出游戏自己的 checkAction）")
            except BridgeError as exc:
                diag.append(f"踩床格 {bed} 失败：{_receipt(exc)}")
            obs = self.snap()
            ready, why = self.sleep_ready(obs)
        if bed is not None and not ready:
            # 兜底：站床边 + interact（旧路径，真机没成功过，但便宜、且能给出更明确的原因）
            if self.stand_next_to(bed):
                try:
                    self.c.interact(bed, timeout_ms=8000)
                    diag.append("兜底 interact(床) 已发出")
                except BridgeError as exc:
                    diag.append(f"兜底 interact(床) 失败：{_receipt(exc)}")
                obs = self.snap()
                ready, why = self.sleep_ready(obs)
            else:
                diag.append("床边站不过去")
        # 判据没满足也**照发一次**：真值判定留给 Mod（它会秒级报 sleep_no_question），
        # 脑不能凭一个可能过时的快照替游戏决定"睡不了"。
        why = why if ready else f"{why} —— 仍请求一次，由 Mod 判定"

        try:
            res = self.c.sleep(timeout_ms=timeout_ms)
        except BridgeError as exc:
            raw = str(getattr(exc, "status", "") or "")
            status = raw or "failed"
            r.code = status if status in SLEEP_FAIL_CODES else "failed"
            # task-22：睡觉也可能撞上渐黑/模态/没存档（全桥通用码）——按同一口径打标，
            # 免得"任意 skill 的一次瞬时环境抖动"这句话在 sleep 上是假的。
            _mark_status(r, raw)
            r.receipt = _receipt_long(exc)
            r.reason = f"睡觉失败（{status}，脑侧判据：{why}）：{str(exc)[:300]}"
            if diag:
                r.reason += f"；脑侧现场：{'；'.join(diag)}"
            return r

        obs = self.snap()
        day_after = self.day_key(obs)
        r.after = self._sleep_probe(obs)
        r.receipt = _receipt_of(res)
        if day_after != day_before:
            r.ok = True
            r.reason = (f"已跨日：{day_before[1]} {day_before[2]}日 → {day_after[1]} {day_after[2]}日"
                        f"（体力 {r.before.get('stamina', 0):g} → {self.stamina(obs):g}）")
            if diag:
                r.reason += f"；{'；'.join(diag)}"
            return r
        r.code = "failed"
        r.reason = (f"日期没变（还是 {day_after[1]} {day_after[2]}日，timeOfDay={self.time_of_day(obs)}）"
                    f"；脑侧判据：{why}；脑侧现场：{'；'.join(diag) if diag else '—'}"
                    + (f"；Mod 回执：{r.receipt}" if r.receipt else ""))
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


def _receipt_long(exc: BaseException, limit: int = 300) -> str:
    """回执原文（带 status，最多 300 字）。

    `sleep` 失败时必须能一眼看出是哪一类：`sleep_no_question`（游戏没弹提问）/
    `timeout`（发送了但日期没动）/ `no_save`（存档没加载）。Mod 的 reason 里自带
    `Diagnose()` 现场（isInBed/newDay/activeMenu/dialogueUp/canMove/gameMode/timeOfDay
    /newDaySync.*），截 300 字足够把根因带进 journal（task-8 D / task-6 §4 R1）。
    """
    status = getattr(exc, "status", None) or type(exc).__name__
    return f"{status}: {str(exc)[:limit]}"


def _receipt_of(res: dict[str, Any] | None) -> str:
    """成功回执摘要：`status: 文本`（**只是诊断**，不作为证据）。

    要的是把 Mod 的 `reason`（它现在会如实报"起手=是/否""现在还是 grass"）带进 journal，
    方便事后判断"到底挥出去了没有"，而不是只留一个 ok。
    """
    if not res:
        return ""
    return f"{res.get('status') or 'ok'}: {str(res.get('reason') or '')[:200]}"



def _count_item(player: dict[str, Any], item: str) -> int:
    want = str(item)
    total = 0
    for it in player.get("inventory") or []:
        if str(it.get("id")) == want or str(it.get("qualifiedId") or "") == want:
            total += int(it.get("stack") or 0)
    return total
