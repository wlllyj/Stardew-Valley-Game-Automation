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

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .bridge import BridgeClient, BridgeError

__all__ = [
    "DEAD_TOOL_CANDIDATES",
    "DEBRIS_KINDS",
    "ENV_BLOCK_STATUSES",
    "INCONCLUSIVE_STATUSES",
    "KIND_TOOL",
    "MAX_CLEAR_SWINGS",
    "MAX_DEAD_SWINGS",
    "SEED_KEEP_FACTOR",
    "SEED_NAME_HINTS",
    "SKIP_KINDS",
    "STAGE_ACTION",
    "TILE_INERT_STATUSES",
    "UNREACHABLE_CODE",
    "UNREACHABLE_HINTS",
    "UNREACHABLE_STATUSES",
    "FarmWorker",
    "StageResult",
    "StepResult",
    "farm_dry_tiles",
    "farm_dead_crops",
    "is_seed_offer",
    "is_unreachable",
    "pick_seed_offer",
    "seed_items",
    "seed_offers_from",
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

#: 【task-52】**没有落脚点 / 寻路到不了**这一类失败的专属 `code`：与 `failed`/`env_block`/
#: `inconclusive` 并列，`StepResult.failed` 对它为 **False**。
#: 真机依据（run5 summer 1，`logs\longrun-3day-llm-run5.jsonl` t=809.5/917.59）：那天做成 109 步、
#: `final_water.dry=0`、`no_unmet_stages=true`，却因为 8 格 `clear` 全报「四邻都站不过去」
#: ⇒ `checks.no_hard_failures=false` ⇒ `verified=false`。那 8 格是**客观世界约束**
#: （四周都不可站立），不是"循环坏了"的证据 —— 把它算成当天硬失败会让高产的一天永远拿不到
#: `verified`。**但它也不是成功**：`longrun` 当天把它记进 `blocked`（当天不再白试、次日清空重试），
#: 并单独计数 + 逐格坐标进 journal；日级豁免有上界（见 `longrun` 的 `unreachable_within_bound`），
#: 且**全部目标不可达 + 0 成功动作仍然判不达标**。
UNREACHABLE_CODE = "unreachable"

#: Mod 侧表示"走不到/没算出路径"的 status（`MoveToLocationSkill`/`StepMover`/`Skills` 的
#: `unreachable`）。脑侧解析回执原文时也用同一组关键字（`UNREACHABLE_HINTS`）。
UNREACHABLE_STATUSES = ("unreachable",)

#: 回执/reason 里出现这些字样 ⇒ 归到 `UNREACHABLE_CODE`（与 `tools\verify-run3.py` 的自算关键字
#: **同一组**，Lead m04925 钉死；改这里必须同步改那边）。
UNREACHABLE_HINTS = ("四邻都站不过去", "寻路无法到达", "无法到达", "A* 未算出路径", "unreachable")

#: `sleep` 回执里"游戏自己**没有**弹出睡觉提问"的状态码：Mod 拼不出 `Sleep` 前缀的应答键时
#: **秒级**报它（不会再白等 3 分钟）。判据与 IL 定案见 `docs/_il-sleep-path.md`。
SLEEP_NO_QUESTION = "sleep_no_question"

#: `sleep` 失败时值得原样透传进 `code` 的状态码（其余一律折成 `"failed"`，
#: 免得把 Mod 的任意 status 当成脑侧语义写进 journal）。
SLEEP_FAIL_CODES = (
    SLEEP_NO_QUESTION, "timeout", "no_save", "ui_modal", "world_fading",
    "precondition_failed", "error",
)

#: 桥**自身**不可用（连不上 / 连接被重置 / 回执不是合法 JSON / 协议不匹配 / 读不到 `bridge.json`）
#: —— 这些不是"游戏侧的业务失败"，而是"脑现在没法跟游戏说话"。
#: NIT-3：`sleep()` 里命中它们统一报 `bridge_down`，与 `longrun` 的 `ended_by` 词表
#: （`bridge_down`）以及 `bridge.py` 里 `quit_game` 的同一组码对齐；`timeout`/`stale`
#: **不在此列**（那是"可能要重试"的环境抖动，别混成桥掉线）。
BRIDGE_DOWN_STATUSES = (
    "unreachable_bridge", "connection_broken", "bad_response",
    "bridge_file_missing", "bridge_file_invalid", "schema_mismatch",
)

#: 睡觉提问的文本线索：只用来把"开着的提问"分类成 sleep/other（**写诊断用**），
#: 不据此发送、也不据此拒绝任何请求（真值判定只认 `ui.dialogueIsQuestion` + Mod 回执）。
SLEEP_QUESTION_HINTS = ("sleep", "睡觉", "上床", "就寝", "bed")

#: 床**触发格**的兜底槽位（相对床原点的偏移）：真实触发格在床原点那一行的**下一行**
#: （`tile_y == tileLocation.Y + 1`），`tile_x == tileLocation.X + bedTileOffset` 而
#: `bedTileOffset ∈ {0, 1}` 会**逐帧翻转** ⇒ 候选就是 `(x+0, y+1)` 与 `(x+1, y+1)`。
#: 依据 `docs/_il-bed-interaction.md` §2.2/§2.6。**只是兜底**：桥给了 `furniture[].bedCells`
#: （用游戏自己的 `doesTileHaveProperty(..., "TouchAction", "Back") == "Sleep"` 现算）时一律优先用它。
BED_CELL_FALLBACK = ((0, 1), (1, 1))

#: 规划层的任务类型 → 执行层的动作。
#: `plant_area` 走 `sow`（播种 + 立刻浇这一格），理由见 `FarmWorker.sow` 的 docstring。
#: `clear_dead` 走 `clear_dead`（只清**枯死**作物，活苗不碰；task-51）。
STAGE_ACTION = {
    "clear_area": "clear",
    "till_area": "till",
    "plant_area": "sow",
    "water_area": "water",
    "harvest": "harvest",
    "clear_dead": "clear_dead",
}

#: 【task-51】清枯死作物最多连发几次请求。`destroyCrop(true)` 在**第一次命中**就发生
#: （IL 见 `clear_dead` 的 docstring），第 2 次只用来兜"第一次没拿到结论"（超时/环境抖动）。
MAX_DEAD_SWINGS = 2

#: 【task-51】清枯死作物的工具候选顺序（IL 定案：镰刀与锄头都能 `destroyCrop`）。
#: 首选镰刀：与割草同路、不会把耕地锄掉；背包里只有锄头时退锄头。
#: `tool_missing_reason` 判不准（观测里没有工具/背包信息）时返回空串 ⇒ 放行，宁可多挥一次。
DEAD_TOOL_CANDIDATES = ("scythe", "hoe")

#: 邻格顺序（上/下/右/左）：站到目标格四邻之一再动手。
NEIGHBORS = ((0, -1), (0, 1), (1, 0), (-1, 0))

#: 【task-68】能靠"开路"对付的邻格类（清得掉的障碍）。树/树桩/大石/灌木/放置物**不碰**：
#: 砍树砸石要斧镐等级、还可能连带伤到别的层 ⇒ 它们堵住的格归 `encircled` 单独一类。
FRONTIER_KINDS = ("weed", "twig", "stone", GRASS_KIND)

#: 【task-68】为某一格"开路"最多花几次动作（清邻格）。到上限还没通 ⇒ 承认"开了也不通"（有界）。
MAX_OPEN_ACTIONS = 4

#: 【task-68】目标格**被不可清障物围住**（2 层内找不到"可站 + 可清"的突破口）：
#: 既不是"走不到"（那是地形/寻路问题），也不是"干不动"（那是世界拒绝）。
#: 它**不进** `unreachable` 计数与豁免分子、当天**不封格**（次日/开路后可能变可达），
#: 只单独计数 + 逐格 `encircled` journal —— 这样"整片被围住"不会把合法豁免顶出上界
#: （run6：42 格里多数是这种，却被记成 `走不到` ⇒ `unreachable_within_bound=false` 假红）。
ENCIRCLED_CODE = "encircled"

#: 【task-43】从 `move_to_location` 的失败回执里取"warp 源格 (x,y)"与"剩余 N 步"。
#: 真机原文（run4，`docs/_run4-evidence.md` §153）：
#: `第 1 跳失败（timeout）：走向 Farm → FarmHouse 的 warp 源格 (64,14) 超时（单跳预算 8000ms 或整体剩余时间用尽）`
#: 以及 StepMover 的 `超时（8000ms，剩余 58 步未走完），已停止寻路`。
#: 用来做**两段式**接近：先 `move_to` 到源格旁边的可站格，再重发一次 `move_to_location`。
_WARP_SOURCE_RE = re.compile(r"warp\s*源格\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)")
_REMAINING_STEPS_RE = re.compile(r"剩余\s*(\d+)\s*步")

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
    #: 【task-63】Mod 回执里的 `status` 原文（只诊断/留痕用：`tool_refused` journal 要带它，
    #: 让人能一眼看到"是游戏拒绝（`tool_ineffective`）而不是我挥了没效果"）。
    status: str = ""
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
    #: 【task-63】**游戏拒绝了这个工具对这一格动手**（`tool_ineffective`/`precondition_failed`）：
    #: 它是"世界给的前置事实"，不是"我试了没做成" ⇒ 记 `skipped` + `proven_inert`（当天封格、
    #: 次日重试），**不算硬失败**；但日级另有**有界**豁免（`refused_bound`），防"游戏全拒绝"
    #: 换一个 verified。与 task-52 的 `unreachable` 是**两套独立计数**、互不覆盖。
    refused: bool = False
    #: 【task-67】`buy` 回执带回来的**结构化货架清单**（`availableItems`，成功与失败都有）：
    #: 脑据此挑"当季、买得起"的种子，不再硬编码物品 id（run6：夏季硬买春季 `472` ⇒ 每天白试 6 次）。
    #: 只落盘成纯数据（`[{"id","name","price"}, …]`），解析容错在 `seed_offers_from()`。
    available: list[dict[str, Any]] = field(default_factory=list)
    #: 【task-68】**真的站到了目标格旁边**（站位成功）才为真。日级 `unreachable_bound` 的分母
    #: 用它而不是"发起过动作的格"：压根没走到跟前的格子（run6 那 42 格）不该抬高豁免上界，
    #: 否则"整片被围住"时合法豁免反而被自己的分母顶出去（`unreachable_within_bound` 假红）。
    stood: bool = False
    #: 【task-68】为够到 `tile` 而**先清掉的邻格**（`[{"neighbour":[x,y],"kind":…,"result":…}]`）。
    #: 单独一个字段（不塞 `after`）：`after` 是逐格观测要点、会在动作循环里被覆盖，
    #: 开路证据必须留到最后 ⇒ `as_dict()` 里叫 `clear_neighbor`，`longrun` 汇总成 journal。
    opened: list[dict[str, Any]] = field(default_factory=list)

    @property
    def skipped(self) -> bool:
        return self.code == "skipped"

    @property
    def failed(self) -> bool:
        """**真失败**：动作发了、世界没按后置条件变。

        ⚠️ `unreachable`（task-52：四邻都站不过去 / 寻路到不了）与 `encircled`（task-68：
        被不可清障物围住）**都不是** `failed` —— 那是客观世界约束，日级另有有界豁免与逐格留痕。
        """
        return self.code == "failed"

    @property
    def unreachable(self) -> bool:
        """【task-52】没有落脚点 / 寻路到不了 ⇒ 当天不再白试、次日重试、单独计数（不算硬失败）。"""
        return self.code == UNREACHABLE_CODE

    @property
    def encircled(self) -> bool:
        """【task-68】被不可清障物围住（2 层内无"可站+可清"突破口）⇒ 不算硬失败、不封格。"""
        return self.code == ENCIRCLED_CODE

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
        if self.status:
            d["status"] = self.status
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
        if self.unreachable:
            d["unreachable"] = True
        if self.encircled:
            d["encircled"] = True
        if self.stood:
            d["stood"] = True
        if self.opened:
            d["clear_neighbor"] = self.opened
        if self.refused:
            d["refused"] = True
        if self.available:
            d["available"] = self.available
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
    def unreachable_steps(self) -> list[StepResult]:
        """【task-52】没有落脚点 / 寻路到不了的步（**不算 `failed_steps`**）。"""
        return [s for s in self.steps if s.unreachable]

    @property
    def unreachable_count(self) -> int:
        return len(self.unreachable_steps)

    @property
    def refused_steps(self) -> list[StepResult]:
        """【task-63】被游戏拒绝的步（`skipped`+`proven_inert`，**不算 `failed_steps`**）。"""
        return [s for s in self.steps if s.refused]

    @property
    def refused_count(self) -> int:
        return len(self.refused_steps)

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
            "unreachable": self.unreachable_count,
            "refused": self.refused_count,
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


def is_unreachable(status: str, text: str = "") -> bool:
    """【task-52】这一次失败是不是"走不到"（没有落脚点 / 寻路到不了）。

    两个来源都要认：①Mod 的机器可读 `status`（`UNREACHABLE_STATUSES`）；
    ②回执/reason 原文里的关键字（`UNREACHABLE_HINTS`，与 `tools\\verify-run3.py` 的自算
    关键字**同一组** —— 真机 run5 那 8 格就是脑侧 `stand_next_to` 直接判的"四邻都站不过去"，
    根本没走到 Mod 那一步，只能靠原文认）。

    归类后由调用点把 `StepResult.code` 写成 `UNREACHABLE_CODE`：`failed` 对它为 False。
    """
    s = str(status or "").strip().lower()
    if s in UNREACHABLE_STATUSES:
        return True
    blob = str(text or "")
    return any(h.lower() in blob.lower() for h in UNREACHABLE_HINTS)


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


def farm_dry_tiles(obs: dict[str, Any]) -> tuple[list[tuple[int, int]], str]:
    """Mod 报的"有作物且没浇"的格子坐标（`farm.dryTiles`，task-50）。

    返回 `(格坐标列表, 状态)`，状态只有三种：

    * `"ok"` —— 坐标可信且**没有**被上限截断；
    * `"truncated"` —— 超过 Mod 的 64 条上限被截断（`dryTilesTruncated=true`）：
      坐标可用，但**不许多浇、也不许当成"全部"**（总数以 `farm.dryCrops` 为准）；
    * `"unavailable"` —— 旧 Mod 没有这个字段，或 `farm` 证据不可信
      （`complete != true` / `loaded == false`）：**绝不许据此判"没有干格"**。

    为什么需要它（run5 三天全挂的形态）：脑侧的观测只有玩家周围最近的 400 格
    （`location.tilesTruncated=true`），农场另一头那 1 格干作物既看不到、也没坐标
    ⇒ `work_reasons()` 拿不出目标 ⇒ `no_work` 收工 ⇒ `day_justified=true`，
    只有 `watered_outdoor` 把 `verified` 拽下来。Mod 侧与 `dryCrops` 严格同一次扫描口径
    （死苗也算"干"，刻意不过滤）。
    """
    farm = obs.get("farm") or {}
    if farm.get("loaded") is False or farm.get("complete") is not True:
        return [], "unavailable"
    raw = farm.get("dryTiles")
    if raw is None:
        return [], "unavailable"
    out: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for item in raw:
        try:
            t = (int(item[0]), int(item[1]))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out, ("truncated" if farm.get("dryTilesTruncated") else "ok")


def farm_dead_crops(obs: dict[str, Any]) -> tuple[int, str]:
    """Mod 报的"枯死作物格数"（`farm.deadCrops`，task-51）。

    返回 `(格数, 状态)`：

    * `"ok"` —— `farm.deadCrops` 可信（`complete == true` 且 `loaded != false`）；
    * `"unavailable"` —— 旧 Mod 没有这个字段，或 `farm` 证据不可信 ⇒ 格数回 **0**，
      但调用方**绝不**能把 0 当成"农场里没有枯死作物"（那只是"不知道"）。

    为什么是计数而不是坐标：清死苗是一次性动作，逐格坐标走玩家窗口 `tiles[].dead`
    （`longrun._stage_tiles("clear_dead")` 就用它）。这个 farm 级计数用来**如实记录**
    "窗口清完了、农场里还剩多少"（journal `clear_dead_scope`）—— 免得把"看不见"说成"没有了"
    （与 task-50 的 `dryTiles` 同一条纪律，只是死苗暂时没给坐标）。
    """
    farm = obs.get("farm") or {}
    if farm.get("loaded") is False or farm.get("complete") is not True:
        return 0, "unavailable"
    raw = farm.get("deadCrops")
    if raw is None:
        return 0, "unavailable"
    try:
        return max(0, int(raw)), "ok"
    except (TypeError, ValueError):
        return 0, "unavailable"


# ======================================================================
#  买种子的选品（task-67）
# ======================================================================

#: 名字里带这些子串的货架条目算"种子"（Mod 的 `DisplayName` 是英文 `… Seeds`，
#: 中文环境是「…种子」）。**只看游戏自己报的名字**，不猜 `Data/Crops`（脑看不到）。
SEED_NAME_HINTS = ("seed", "seeds", "种子")

#: 「留够 K 包的钱」：单价 ≤ 钱 / K 才算买得起（K=10）。这样买完种子还剩钱买别的/应急。
SEED_KEEP_FACTOR = 10


def seed_offers_from(res: dict[str, Any] | None) -> list[dict[str, Any]]:
    """从 `buy` 回执里取出**结构化货架清单**（`availableItems`，task-67）。

    容错：旧键 `available` 也认；脏条目（缺 id / 价格不是整数）跳过；价格缺省按 0。
    返回 `[{"id": "(O)472", "name": "Parsnip Seeds", "price": 20}, …]`（顺序照回执）。
    """
    if not isinstance(res, dict):
        return []
    rows = res.get("availableItems")
    if rows is None:
        rows = res.get("available")
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        iid = str(row.get("id") or "").strip()
        if not iid:
            continue
        try:
            price = int(row.get("price") or 0)
        except (TypeError, ValueError):
            price = 0
        out.append({"id": iid, "name": str(row.get("name") or ""), "price": price})
    return out


def is_seed_offer(offer: dict[str, Any] | None) -> bool:
    """货架条目是不是"种子"（按名字；大小写不敏感，中英都认）。"""
    if not isinstance(offer, dict):
        return False
    name = str(offer.get("name") or "")
    low = name.lower()
    return any(hint in low for hint in SEED_NAME_HINTS)


def pick_seed_offer(
    offers: list[dict[str, Any]],
    money: int,
    *,
    keep_factor: int = SEED_KEEP_FACTOR,
) -> tuple[dict[str, Any] | None, str]:
    """在货架清单里挑"最便宜、且买得起"的种子。返回 `(选中项, 代码)`。

    代码三种（与 `longrun` 的 journal 同名）：

    * `"ok"` —— 选中了，`pick["id"]` 就是要下单的 `QualifiedItemId`；
    * `"no_seed_for_sale"` —— 货架上**一条种子都没有**（run6 的夏季：只有当季种子，
      而脑硬编码的春季 `472` 不在架上）；
    * `"cannot_afford"` —— 有种子，但按"留够 `keep_factor` 包"的口径**买不起**
      （`price > money / keep_factor`），或有种子的价格不可用（≤0）。

    为什么要"留够 K 包"而不是"买得起一个就买"：run6 那 956g 全砸进种子，
    之后连应急的余地都没有；而锄地/浇水每格都要体力与时间，钱是唯一的缓冲。
    """
    seeds = [o for o in (offers or []) if is_seed_offer(o)]
    if not seeds:
        return None, "no_seed_for_sale"
    budget = int(money // int(keep_factor)) if int(keep_factor) > 0 else int(money)
    afford = [o for o in seeds if 0 < int(o.get("price") or 0) <= budget]
    if not afford:
        return None, "cannot_afford"
    pick = min(afford, key=lambda o: (int(o.get("price") or 0), str(o.get("id") or "")))
    return pick, "ok"


class FarmWorker:
    """一格一动的执行器。**不做策略**：给它格子，它做完并如实报告。"""

    def __init__(
        self,
        client: BridgeClient,
        *,
        seed: str | None = None,
        log: Callable[[str], None] = print,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        self.c = client
        self.seed = seed            # None = 每次播种时按背包里堆叠最多的种子现挑
        self.log = log
        self.pause = pause          # 可注入的等待函数（单测里换成 no-op，绝不真睡）
        self.steps: list[StepResult] = []      # 全程流水（journal 用）
        self.walk_steps = 0
        # 【task-42 出货白名单】今天**亲眼**看到"收获后进了背包"的 qualifiedId → 件数。
        # 只有这里出现过的东西才允许出货（`sell` 的 `whitelist` 就来自它）：铁律是"只走白名单、
        # 绝不做'除工具以外都能卖'的黑名单"——黑名单一旦上游有 bug，种子/工具/任务物品都会被卖掉。
        # `reset_harvested()` 由长跑控制器在每天开始时调用。
        self.harvested: dict[str, int] = {}
        # 【task-68】正在"为某一格开路"（清它的邻格）时为真：**只允许一层开路** ——
        # 清邻格时若那个邻格自己也站不到，就直接判 `unreachable`，不再为它继续开路的开路
        # （否则"清障→站不到→再清障"会指数级展开，跟有界性要求冲突）。
        self._opening = False

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
    # ------------------------------------- 【task-68】先开路，再判"走不到"
    @staticmethod
    def _standable_near(obs: dict[str, Any], tile: tuple[int, int]) -> bool:
        """这一格的四邻里有没有落脚点（观测说能站；**没观测到也算**——交给 Mod 去试）。"""
        tiles = FarmWorker.tiles_of(obs)
        for dx, dy in NEIGHBORS:
            tv = tiles.get((tile[0] + dx, tile[1] + dy))
            if tv is None or tv.get("standable"):
                return True
        return False

    def _openable_neighbours(self, obs: dict[str, Any], tile: tuple[int, int],
                             *, skip: set[tuple[int, int]] | None = None
                             ) -> list[tuple[tuple[int, int], str]]:
        """能当"开路"对象的邻格：**可清障类** + 它自己有落脚点（允许递归 1 层）。

        树/树桩/大石一类（`FRONTIER_KINDS` 之外）不碰：砍树砸石要斧镐等级、还可能连带伤到别的层。
        """
        skip = skip or set()
        tiles = FarmWorker.tiles_of(obs)
        pt = self.player_tile(obs) or (0, 0)
        out: list[tuple[tuple[int, int], str]] = []
        for dx, dy in NEIGHBORS:
            n = (tile[0] + dx, tile[1] + dy)
            if n in skip:
                continue
            tv = tiles.get(n) or {}
            kind = str(tv.get("kind") or "")
            if kind not in FRONTIER_KINDS:
                continue
            if tv.get("crop"):
                continue          # 邻格上有作物 ⇒ 清障会伤到它（`clear()` 也会拒）
            if not self._standable_near(obs, n):
                continue          # 邻格自己也够不着 ⇒ 清了也白清
            out.append((n, kind))
        out.sort(key=lambda it: (abs(it[0][0] - pt[0]) + abs(it[0][1] - pt[1]), it[0][1], it[0][0]))
        return out

    def open_way(self, tile: tuple[int, int]) -> tuple[str, list[dict[str, Any]], list[str]]:
        """【task-68】判"走不到"之前**先开路**：清掉挡住 `tile` 落脚点的邻格，再重试站过去。

        返回 `(code, cleared, notes)`：

        * `"ok"` —— 现在站得到 `tile` 旁边了（清掉了邻格，或本来就站得到）；
        * `"encircled"` —— 四邻里没有"可清 + 自己够得着"的突破口 ⇒ 归 `encircled`；
        * `"exhausted"` —— 有可清的，清了 `MAX_OPEN_ACTIONS` 次还不通 ⇒ 归 `unreachable`（**有界**）。

        `cleared` 是可落盘的逐条证据（`[{"neighbour":[x,y],"kind":…,"result":…}]`），进
        `StepResult.after["clear_neighbor"]` ⇒ longrun 记 `clear_neighbor` journal。
        开路动作本身也走 `clear()`（同一套先判后动/工具体检/回执口径），不做第二套。
        """
        cleared: list[dict[str, Any]] = []
        notes: list[str] = []
        skip: set[tuple[int, int]] = set()
        for _i in range(MAX_OPEN_ACTIONS):
            obs = self.snap()
            if self.stand_next_to(tile):
                return "ok", cleared, notes
            cands = self._openable_neighbours(obs, tile, skip=skip)
            if not cands:
                # 没有"可清 + 够得着"的邻格：还要分两种 ——
                #   * 四邻**连落脚点都没有**（树/桩/大石一类）⇒ `encircled`（被围住，不封格、不计不可达）；
                #   * 四邻**有落脚点**（只是寻路/站位失败）⇒ `exhausted` ⇒ 按 `unreachable` 处理
                #     （task-52 口径不变：这是"走不到"，不是"被围住"）。
                if not self._standable_near(obs, tile):
                    return "encircled", cleared, notes
                return "exhausted", cleared, notes
            n, kind = cands[0]
            st = self.clear(n)
            result = st.code or ("ok" if st.ok else "failed")
            cleared.append({"neighbour": [int(n[0]), int(n[1])], "kind": kind, "result": result})
            notes.append(f"为 {list(tile)} 开路：清邻格 {list(n)}（{kind}）⇒ {result}")
            if not st.ok:
                skip.add(n)       # 这一格自己也清不了 ⇒ 换一个，别在同一格死磕
        if self.stand_next_to(tile):
            return "ok", cleared, notes
        return "exhausted", cleared, notes

    def _ensure_reachable(self, tile: tuple[int, int], r: StepResult) -> bool:
        """站到 `tile` 旁；站不到就**先开路**（task-68）。成功置 `r.stood=True` 并返回 True；
        失败时把 `r` 写成 `unreachable`/`encircled` 并返回 False（调用方直接 `return r`）。
        """
        if self.stand_next_to(tile):
            r.stood = True
            return True
        if self._opening:
            # 只允许一层：正在为别人开路时，这一格站不到就直接算走不到（防递归爆炸）。
            r.code, r.reason = UNREACHABLE_CODE, "四邻都站不过去（开路只做一层：这一格是开路的邻格）"
            return False
        self._opening = True
        try:
            code, cleared, notes = self.open_way(tile)
        finally:
            self._opening = False
        if cleared:
            # 单独存字段（不塞 `after`）：`after` 在动作循环里会被逐格观测覆盖，开路证据要留住。
            r.opened = list(cleared)
        if code == "ok":
            r.stood = True
            return True
        if code == "encircled":
            r.code = ENCIRCLED_CODE
            r.reason = ("四邻被不可清障物占住（树/桩/大石一类；2 层内没有「可站+可清」的突破口）"
                        "⇒ 归 encircled：不算「走不到」、不封格，次日/开路后可能变可达")
            return False
        r.code = UNREACHABLE_CODE
        r.reason = (f"四邻都站不过去（已为开路清 {len(cleared)} 格邻格仍不通，"
                    f"上限 {MAX_OPEN_ACTIONS} 次）")
        return False

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

    # ------------------------------------------- 跨地点（task-43：失败后两段式接近）
    @staticmethod
    def _warp_source_of(text: str) -> tuple[int, int] | None:
        """从 Mod 失败回执里取"warp 源格 (x,y)"（原文见 `_WARP_SOURCE_RE` 的注释）。"""
        m = _WARP_SOURCE_RE.search(str(text or ""))
        return (int(m.group(1)), int(m.group(2))) if m else None

    @staticmethod
    def _remaining_steps_of(text: str) -> int | None:
        """从 Mod 失败回执里取"剩余 N 步"（`超时（8000ms，剩余 58 步未走完）`）。"""
        m = _REMAINING_STEPS_RE.search(str(text or ""))
        return int(m.group(1)) if m else None

    @classmethod
    def _neighbour_to_walk(cls, obs: dict[str, Any], tile: tuple[int, int]) -> tuple[int, int] | None:
        """门/warp 源格旁边**能站**的一格：先信观测 `standable`，观测没覆盖就交给 Mod 去试。

        观测窗口只覆盖玩家周围（半径见 `OBSERVE_REACH`），而源格可能在窗口边缘之外 ⇒
        "观测里没有这一格"不等于"不能站"（能不能站只有游戏的地图知道）。四邻**全被观测
        明确标成不可站**时才返回 None（那种情况下不该硬走，如实报）。
        """
        tiles = cls.tiles_of(obs)
        ranked: list[tuple[int, tuple[int, int]]] = []
        for dx, dy in NEIGHBORS:
            t = (int(tile[0]) + dx, int(tile[1]) + dy)
            tv = tiles.get(t)
            if tv is None:
                ranked.append((1, t))                  # 观测没覆盖 ⇒ 交给 Mod 去试
            elif tv.get("standable") is True:
                ranked.append((0, t))                  # 观测明说能站 ⇒ 首选
            else:
                ranked.append((2, t))                  # 观测说不能站 ⇒ 最后考虑
        if not ranked or ranked[0][0] == 2:
            return None
        ranked.sort(key=lambda item: item[0])
        return ranked[0][1]

    def _location_failed(self, r: StepResult, name: str, exc: Exception,
                         src: tuple[int, int] | None, steps: int | None,
                         diag: list[str]) -> None:
        """如实落账：Mod 原文 + `warp 源格` + `剩余 N 步` + 脑侧现场（人在哪）+ 两段式做过什么。"""
        why = str(exc)[:300]
        r.code = "failed"
        r.receipt = _receipt(exc) if isinstance(exc, BridgeError) else ""
        try:
            obs = self.snap()
            where = f"{self.player_tile(obs)}（{str((obs.get('location') or {}).get('name') or '?')}）"
        except BridgeError as exc2:
            where = f"读不到（失败后再观测也失败：{str(exc2)[:120]}）"
        bits = [f"去 {name} 失败：{why}" if why else f"去 {name} 失败（Mod 没给原因）"]
        if src is not None:
            bits.append(f"Mod 报的 warp 源格 {src}")
        if steps is not None:
            bits.append(f"剩余 {steps} 步未走完")
        bits.append(f"脑侧现场：人在 {where}")
        if diag:
            bits.append("；".join(diag))
        r.reason = "；".join(bits)
        _mark_status(r, _exc_status(exc))               # 环境挡路 / 没结论 ⇒ 不封格

    def ensure_location(self, name: str, *, tile: tuple[int, int] | None = None,
                        timeout_ms: int = 60000) -> StepResult:
        """走到另一个地点；**失败后做一次两段式重试**（task-43）。

        run4 的致命卡点：从田里 `Farm [47,29]` 回农舍，A* 真实路径 ≈88 步（被草/石/枝/树逼得
        绕路 3 倍），而 Mod 每跳只有 8s ⇒ 门口那一跳必然 `timeout`，两次睡觉都是 `sleep_failed`。
        现在：①`timeout_ms` 默认 **60000**（Mod 侧 `move_to_location` 上限同步放宽到 60000）；
        ②失败回执里 Mod 会报出"走向 X → Y 的 warp 源格 (a,b) 超时（单跳预算 …ms，剩余 N 步未走完）"，
        脑侧据此**先走到源格旁边的可站格**，再**只重试一次** `move_to_location`（上限 1 次，防自旋）。
        Mod 侧同时改成"有进展就续跳"，所以单跳不再因为"路径长"而假超时。
        """
        r = StepResult(action="move_to_location", tile=tile)
        obs = self.snap()
        if str((obs.get("location") or {}).get("name") or "") == name:
            r.ok, r.code, r.reason = True, "already", f"已经在 {name}"
            return r
        diag: list[str] = []
        try:
            self.c.move_to_location(name, tile=tile, timeout_ms=timeout_ms)
        except BridgeError as exc:
            src = self._warp_source_of(str(exc))
            steps = self._remaining_steps_of(str(exc))
            if src is not None:
                try:
                    side = self._neighbour_to_walk(self.snap(), src)
                except BridgeError as exc_obs:
                    side = None
                    diag.append(f"失败后观测也失败，没法找源格邻居：{str(exc_obs)[:120]}")
                if side is None:
                    diag.append(f"Mod 报的 warp 源格 {src} 四邻没有可站格，没法两段式接近")
                else:
                    try:
                        mv = self.move_to(side, timeout_ms=30000)
                        diag.append(f"两段式：先 move_to({side[0]},{side[1]})→"
                                    f"{'ok' if mv.ok else (mv.code or 'failed')}")
                        if mv.ok:
                            retry_ms = max(15000, int(timeout_ms) // 2)
                            self.c.move_to_location(name, tile=tile, timeout_ms=retry_ms)
                            diag.append(f"两段式：重发 move_to_location（预算 {retry_ms}ms）")
                    except BridgeError as exc2:
                        diag.append(f"两段式重试仍失败：{str(exc2)[:200]}")
                        self._location_failed(r, name, exc, src, steps, diag)
                        return r
            else:
                diag.append("回执里没有 warp 源格，没法两段式接近")
            try:
                obs = self.snap()
            except BridgeError as exc_obs:
                diag.append(f"失败后再观测也失败：{str(exc_obs)[:120]}")
                obs = None
            now = str(((obs or {}).get("location") or {}).get("name") or "")
            if now == name:
                r.ok = True
                r.reason = f"已到 {name}（两段式救回：{'；'.join(diag)}）"
                return r
            self._location_failed(r, name, exc, src, steps, diag)
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
        # 【task-68】站不到旁边 ⇒ **先看四邻能不能开路**（清掉 weeds/stone/twig/grass 再重试）；
        # 开路后仍站不到 ⇒ 被不可清障物围住记 `encircled`、清了上限还不通记 `unreachable`
        # （task-52：不是 `failed`，当天不白试、次日重试，日级各有有界豁免）。
        if not self._ensure_reachable(tile, r):
            return r

        tool = "scythe" if want_grass else "auto"
        traces: list[str] = []
        statuses: list[str] = []    # 每次请求的 Mod status（进 after，供事后复核）
        conclusive = False          # Mod 说"这一格挥不动"（换遍工具/前置条件不成立）
        env_block = ""              # Mod 说"现在整个环境不让动手"
        unreach = ""                # 【task-52】Mod 说"这一格走不到"（A* 没算出路径）
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
            # 【task-52】"走不到"要单独成类：它不是"这一格干不动"（世界可能变好），
            # 更不是"这一刀白挥"（我们根本没挥出去）—— Mod 连落脚点都没找到。
            if is_unreachable(status, r.receipt):
                unreach = status
                break
            env, inconclusive = _classify_status(status)
            if env:
                env_block = status
                break
            if inconclusive:
                # 没拿到结论（超时/异常/没见过的码）：既不能封格，也不算"挥过了" ⇒ 补下一次请求。
                continue
            swung = True            # 回执没报错而世界没变 ⇒ 这一刀是真白挥的

        if unreach:
            # 【task-52】寻路到不了：专属 `unreachable`（`failed` 为 False）。**不封格到明天**——
            # `longrun` 只把它记进当天的 `blocked`（当天别重复白试、次日自动重试），
            # 并在日级按有界口径决定要不要影响 `verified`（逐格坐标进 journal）。
            r.code = UNREACHABLE_CODE
            if isinstance(r.after, dict):
                r.after = {**r.after, "requests": i, "statuses": list(statuses)}
            r.reason = (f"第 {i} 次请求回「走不到」（{unreach}）：Mod 没找到落脚点/没算出路径 ⇒ "
                        f"不算清障失败，也不算这一格干不动；{r.receipt}")
            return r

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

    # ------------------------------------------------------------- 单格：清枯死作物
    def clear_dead(self, tile: tuple[int, int]) -> StepResult:
        """清掉一格**枯死**作物（task-51）。**活苗绝不碰**。

        判据：动手前 = 该格 `crop` 存在且 `dead` 为真；动手后 = 该格 `crop` 消失。

        真机依据（`scratch\\_lead_crop_audit.py`，summer 2）：窗口 400 格里 24 个作物有 23 个
        `dead=True`（例 `[72,26] crop=24 dead=True watered=True kind=dirt`），唯一活苗 `[73,37]`。
        死苗占着耕地 ⇒ `till_blocked_by` 见到 crop 就拒（"有作物"）⇒ 不清就永远种不上。

        工具（IL 定案，`scratch\\il-dead-hoedirt.txt`）：`HoeDirt.performToolAction` 里
        `isinst Hoe` 走 `hitWithHoe → destroyCrop(true)`；镰刀路末尾 `IL_021D-023E`
        `if (crop != null && crop.dead.Value) destroyCrop(true)` ⇒ 普通镰刀(66)与锄头都能清。
        所以按 `DEAD_TOOL_CANDIDATES` 先镰刀后锄头；两者都判"没有"⇒ 一次都不挥（`skipped`+封格）。

        收尾口径与 `clear()` 一致：Mod 说"挥不动"/挥满上限 ⇒ `skipped` + `proven_inert`
        （当天封这一格、次日重试）；走不到 ⇒ task-52 的 `unreachable`；环境挡路 / 没结论
        ⇒ `failed` + `env_block`/`inconclusive`（**不封格**，下轮再试）。
        """
        r = StepResult(action="clear_dead", tile=tile)
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.before = self.tile_essence(tv)
        kind = str((tv or {}).get("kind") or "")

        if not (tv or {}).get("crop"):
            r.ok, r.code = True, "already"
            r.reason = f"这一格没有作物（kind={kind or '未知'}），不用清"
            return r
        if not (tv or {}).get("dead"):
            r.code = "skipped"
            r.reason = "这一格是活苗 —— 清死苗动作绝不碰它"
            return r

        # ---- 先判后动：工具不在身上就别挥（`clear()` 同款判据）----
        tool, miss = "", ""
        for want in DEAD_TOOL_CANDIDATES:
            why = tool_missing_reason(self.player_of(obs), want)
            if not why:
                tool = want
                break
            miss = miss or why
        if not tool:
            r.code = "skipped"
            r.proven_inert = True
            r.reason = f"判据说这格现在清不掉 ⇒ 不动手：{miss}；{_work_context(obs)}"
            return r
        if not self._ensure_reachable(tile, r):
            return r

        traces: list[str] = []
        statuses: list[str] = []
        conclusive = False
        env_block = ""
        unreach = ""
        swung = False
        for i in range(1, MAX_DEAD_SWINGS + 1):
            status = ""
            try:
                res = self.c.use_tool(tile, tool=tool, timeout_ms=15000)
                r.receipt = _receipt_of(res)
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
            has_crop = bool((tv or {}).get("crop"))
            state = "无作物" if not has_crop else ("枯死" if (tv or {}).get("dead") else "活苗")
            traces.append(f"第{i}次请求→{state}")
            if not has_crop:
                r.ok = True
                r.code = ""
                if isinstance(r.after, dict):
                    r.after = {**r.after, "requests": i, "statuses": list(statuses)}
                r.reason = (f"已清掉枯死作物（kind {kind or '未知'} → {kind_now or '未知'}；"
                            f"{'、'.join(traces)}）")
                return r
            if status in TILE_INERT_STATUSES:
                conclusive = True
                break
            if is_unreachable(status, r.receipt):
                unreach = status
                break
            env, inconclusive = _classify_status(status)
            if env:
                env_block = status
                break
            if inconclusive:
                continue
            swung = True

        if unreach:
            r.code = UNREACHABLE_CODE
            if isinstance(r.after, dict):
                r.after = {**r.after, "requests": i, "statuses": list(statuses)}
            r.reason = (f"第 {i} 次请求回「走不到」（{unreach}）：Mod 没找到落脚点/没算出路径 ⇒ "
                        f"不算清死苗失败，也不算这一格干不动；{r.receipt}")
            return r

        if env_block:
            r.code = "failed"
            r.env_block = True
            if isinstance(r.after, dict):
                r.after = {**r.after, "requests": i, "statuses": list(statuses)}
            r.reason = (f"第 {i} 次清死苗被环境挡住（{env_block}）⇒ 这一格不算被证明干不动；{r.receipt}")
            return r

        if statuses and not swung and not conclusive:
            r.code = "failed"
            r.inconclusive = True
            if isinstance(r.after, dict):
                r.after = {**r.after, "requests": i, "statuses": list(statuses)}
            r.reason = (f"连续 {len(statuses)} 次请求没有拿到结论（statuses={'、'.join(statuses)}）"
                        f"⇒ 这一格不算被证明干不动（枯死作物仍在）；{r.receipt}")
            return r

        r.code = "skipped"
        r.proven_inert = True
        if isinstance(r.after, dict):
            r.after = {**r.after, "requests": i, "statuses": list(statuses)}
        why = "Mod 回「工具全无效」" if conclusive else f"连挥 {MAX_DEAD_SWINGS} 次"
        r.reason = (f"{why}（{tool}）这格枯死作物还在"
                    f"⇒ 判据「crop 消失」未满足（{'、'.join(traces)}；回执 {r.receipt or '无'}）；"
                    f"{_work_context(obs)}")
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
        # 【task-68】站不到旁边 ⇒ **先看四邻能不能开路**（清掉 weeds/stone/twig/grass 再重试）；
        # 开路后仍站不到 ⇒ 被不可清障物围住记 `encircled`、清了上限还不通记 `unreachable`
        # （task-52：不是 `failed`，当天不白试、次日重试，日级各有有界豁免）。
        if not self._ensure_reachable(tile, r):
            return r

        status = ""
        try:
            self.c.use_tool(tile, tool="hoe", timeout_ms=15000)
        except BridgeError as exc:
            status = _exc_status(exc)
            r.receipt = _receipt(exc)
        r.status = status
        obs = self.snap()
        tv = self.tile_view(obs, tile)
        r.after = self.tile_essence(tv)
        if (tv or {}).get("kind") == "dirt":
            r.ok = True
            r.reason = "锄出耕地（kind → dirt）"
            return r
        if is_unreachable(status, r.receipt):
            # 【task-52】走不到 ⇒ `unreachable`（不是 failed）：当天不重复白试、次日重试。
            r.code = UNREACHABLE_CODE
            r.reason = (f"锄地请求回「走不到」（{status}）：没有落脚点/没算出路径 ⇒ 不算硬失败；"
                        f"kind={str((tv or {}).get('kind') or '未知')}；{r.receipt}")
            return r
        if status in TILE_INERT_STATUSES:
            # 【task-63】游戏**拒绝**了这个工具对这一格动手（`tool_ineffective`= 挥满
            # `MaxSwings` 仍 `BeginUsingTool` 恒 false；`precondition_failed`= 工具/前置不满足）：
            # 这是"世界给的前置事实"，不是"我试了没做成" ⇒ 记 `skipped` + `proven_inert`
            # （当天封格、次日重试），**不算硬失败**。`longrun` 另按 `refused_bound` 有界豁免 +
            # 逐格 journal `tool_refused`，防"游戏全拒绝"换一个 verified。
            #
            # ⚠️ 与下面那条**必须分开**：Mod 回执 `ok`（status 为空/`ok`）但格子没变 = 真"挥了
            # 没效果"，仍记 `failed`（本分支要求 `status ∈ TILE_INERT_STATUSES`）。
            r.code = "skipped"
            r.proven_inert = True
            r.refused = True
            r.reason = (f"游戏判定这格锄不动（Mod status={status}）⇒ 不是硬失败；"
                        f"kind={str((tv or {}).get('kind') or '未知')}；{r.receipt}")
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

        # 【task-68】站不到旁边 ⇒ **先看四邻能不能开路**（清掉 weeds/stone/twig/grass 再重试）；
        # 开路后仍站不到 ⇒ 被不可清障物围住记 `encircled`、清了上限还不通记 `unreachable`
        # （task-52：不是 `failed`，当天不白试、次日重试，日级各有有界豁免）。
        if not self._ensure_reachable(tile, r):
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
        if is_unreachable(status, r.receipt):
            # 【task-52】走不到 ⇒ `unreachable`（不是 failed）：当天不重复白试、次日重试。
            r.code = UNREACHABLE_CODE
            r.reason = (f"播种请求回「走不到」（{status}）：没有落脚点/没算出路径 ⇒ 不算硬失败；"
                        f"种子 {have}→{left}；{r.receipt}")
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

        # 【task-68】站不到旁边 ⇒ **先看四邻能不能开路**（清掉 weeds/stone/twig/grass 再重试）；
        # 开路后仍站不到 ⇒ 被不可清障物围住记 `encircled`、清了上限还不通记 `unreachable`
        # （task-52：不是 `failed`，当天不白试、次日重试，日级各有有界豁免）。
        if not self._ensure_reachable(tile, r):
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
        if is_unreachable(status, r.receipt):
            # 【task-52】走不到 ⇒ `unreachable`（不是 failed）：当天不重复白试、次日重试。
            r.code = UNREACHABLE_CODE
            r.reason = (f"浇水请求回「走不到」（{status}）：没有落脚点/没算出路径 ⇒ 不算硬失败；"
                        f"水 {left}→{left_after}；{r.receipt}")
            return r
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
        inv_before = self._inventory_counts(self.player_of(obs))
        if not (tv or {}).get("crop"):
            r.code, r.reason = "skipped", "这一格没有作物"
            return r
        if not (tv or {}).get("ripe"):
            r.code, r.reason = "skipped", "还没成熟"
            return r
        # 【task-68】站不到旁边 ⇒ **先看四邻能不能开路**（清掉 weeds/stone/twig/grass 再重试）；
        # 开路后仍站不到 ⇒ 被不可清障物围住记 `encircled`、清了上限还不通记 `unreachable`
        # （task-52：不是 `failed`，当天不白试、次日重试，日级各有有界豁免）。
        if not self._ensure_reachable(tile, r):
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
            # 【task-42】判据之外再记一件事：**背包真的多了什么**。出货白名单只认这份差分
            # （回执不算证据），所以"收成了但没进背包"必须如实写出来 —— 否则出货那一步
            # 会去卖一件根本没进过背包的东西。
            gained = self._loot_delta(inv_before, self._inventory_counts(self.player_of(obs)))
            for qid, n in gained.items():
                self.harvested[qid] = self.harvested.get(qid, 0) + int(n)
            if gained:
                r.after = {**(r.after or {}), "harvested": gained}
                r.reason = f"作物已收走（crop 变空）；进背包：{gained}"
            else:
                r.reason = "作物已收走（crop 变空）；⚠ 背包没有新增物品（收货可能丢了，不能出货）"
            r.ok = True
            return r
        r.code = "failed"
        _mark_status(r, status)     # 渐黑/模态 ⇒ 不封格、不占配额；超时 ⇒ 不封格但占配额
        if is_unreachable(status, r.receipt):
            # 【task-52】走不到 ⇒ `unreachable`（不是 failed）：当天不重复白试、次日重试。
            r.code = UNREACHABLE_CODE
            r.reason = (f"收获请求回「走不到」（{status}）：没有落脚点/没算出路径 ⇒ 不算硬失败；"
                        f"作物还在；{r.receipt}")
            return r
        r.reason = (f"交互后作物还在（可能没摘到）{f'；Mod status={status}' if status else ''}")
        return r

    # ------------------------------------------------------------- task-42：出货（卖出）
    @staticmethod
    def _slot_of(item: dict[str, Any]) -> int | None:
        """物品视图的槽位（**0 是合法槽位**，所以不能用 `or -1` 那种写法）。"""
        try:
            return int(item.get("slot"))
        except (TypeError, ValueError, AttributeError):
            return None

    @staticmethod
    def _inventory_counts(player: dict[str, Any]) -> dict[str, int]:
        """背包按 qualifiedId 汇总件数（缺口/新增都用它算差分）。"""
        out: dict[str, int] = {}
        for it in player.get("inventory") or []:
            if not isinstance(it, dict):
                continue
            qid = str(it.get("qualifiedId") or it.get("id") or it.get("name") or "")
            if not qid:
                continue
            out[qid] = out.get(qid, 0) + int(it.get("stack") or 0)
        return out

    @classmethod
    def _loot_delta(cls, before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
        """收获前后背包差分：只报**变多**的 qualifiedId —— 这就是出货白名单的唯一真源。"""
        out: dict[str, int] = {}
        for qid, n in (after or {}).items():
            d = int(n) - int((before or {}).get(qid, 0))
            if d > 0:
                out[qid] = d
        return out

    def reset_harvested(self) -> None:
        """每天开始时清空白名单（昨天的收获不该今天再卖一遍）。"""
        self.harvested = {}

    def sellable_slots(self, obs: dict[str, Any]) -> list[int]:
        """背包里**今天亲手收获、还有剩**的槽位（升序）。

        判据 = 该格物品的 qualifiedId 在白名单里。**不接受**任何"除了工具都能卖"的推断：
        白名单空 ⇒ 一格都不出。
        """
        qids = {str(q) for q in (self.harvested or {}) if q}
        if not qids:
            return []
        out: list[int] = []
        for it in self.player_of(obs).get("inventory") or []:
            if not isinstance(it, dict):
                continue
            qid = str(it.get("qualifiedId") or it.get("id") or "")
            if qid not in qids:
                continue
            if int(it.get("stack") or 0) <= 0:
                continue
            slot = self._slot_of(it)
            if slot is None:
                continue
            out.append(slot)
        return sorted(out)

    def sell(self, slot: int, *, whitelist: list[str] | None = None,
             timeout_ms: int = 8000) -> StepResult:
        """把背包某一格放进出货箱（`sell`，Mod ≥ 0.7.24）。判据 = **观测差分**。

        为什么判据不是钱：`Farm.shipItem(item, who)` 只把物品搬进箱子，钱由**下一次 `NewDay`**
        结算（`player.Money = player.Money + total`）。所以本方法：
        ① 只看"那一格真的空了 + 该 qualifiedId 总数下降"；② **绝不写 `Money +=`**（铁律）。

        为什么必须给**槽位**：Mod 侧取的是 `Game1.player.Items[slot]` 那个实例，因为游戏自己的
        `removeItemFromInventory` 用**引用相等**找物品；传副本会变成"原物不动、副本进箱"。
        """
        r = StepResult(action="sell")
        obs = self.snap()
        player = self.player_of(obs)
        allow = [str(x) for x in (whitelist if whitelist is not None else sorted(self.harvested))]
        item: dict[str, Any] | None = None
        for it in player.get("inventory") or []:
            if not isinstance(it, dict):
                continue
            if self._slot_of(it) == int(slot):
                item = it
                break
        qid = str((item or {}).get("qualifiedId") or (item or {}).get("id") or "")
        counts_before = self._inventory_counts(player)
        n_before = int(counts_before.get(qid, 0))
        r.before = {"slot": int(slot), "qid": qid, "name": str((item or {}).get("name") or ""),
                    "stack": int((item or {}).get("stack") or 0), "count": n_before,
                    "money": self.money(obs), "whitelist": allow}
        if item is None:
            r.code, r.reason = "empty_slot", f"背包槽位 {slot} 是空的"
            return r
        status = ""
        try:
            self.c.sell(slot, whitelist=allow, timeout_ms=timeout_ms)
        except BridgeError as exc:
            status = _exc_status(exc)
            r.receipt = _receipt(exc)
        obs = self.snap()
        player = self.player_of(obs)
        counts_after = self._inventory_counts(player)
        n_after = int(counts_after.get(qid, 0))
        still = any(
            isinstance(it, dict)
            and str(it.get("qualifiedId") or it.get("id") or "") == qid
            and self._slot_of(it) == int(slot)
            for it in player.get("inventory") or []
        )
        bin_items = ((obs.get("shippingBin") or {}).get("items") or [])
        r.after = {"slot": int(slot), "qid": qid, "count": n_after, "money": self.money(obs),
                   "shipping_bin": len(bin_items)}
        if (not still) and n_after < n_before:
            r.ok = True
            r.reason = (f"已出货槽位 {slot} 的 {qid}（背包 {n_before}→{n_after}，"
                        f"出货箱 {len(bin_items)} 件）；钱要等下一次 NewDay 才由游戏结算"
                        f"（当前 {self.money(obs)}g）")
            # 白名单跟随实际剩余量：出掉多少就减多少，出光即移除（防止明天再卖一件不存在的东西）
            if qid:
                if n_after > 0:
                    self.harvested[qid] = n_after
                else:
                    self.harvested.pop(qid, None)
            return r
        r.code = "failed"
        _mark_status(r, status)     # 渐黑/模态 ⇒ 不封格、不占配额；超时 ⇒ 不封格但占配额
        r.reason = (f"出货没有生效（槽位 {slot} 的 {qid}：背包 {n_before}→{n_after}，"
                    f"槽位{'仍有该物品' if still else '已空'}"
                    f"{f'；Mod status={status}' if status else ''}）")
        return r

    def sell_loot(self, *, timeout_ms: int = 8000, max_items: int = 24) -> list[StepResult]:
        """把今天收获的东西按白名单出一遍（**有界**：最多 `max_items` 格）。

        每出一件都重新 observe（槽位会变），第一件失败就停手 —— 失败原因如实带回去，
        由上层决定要不要记 needs_review。空手时直接返回空列表（不产生任何动作）。
        """
        out: list[StepResult] = []
        for _ in range(max(0, int(max_items))):
            slots = self.sellable_slots(self.snap())
            if not slots:
                break
            st = self.sell(slots[0], timeout_ms=timeout_ms)
            out.append(st)
            if not st.ok:
                break
        return out

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

    @staticmethod
    def bed_cells(obs: dict[str, Any]) -> list[tuple[int, int]]:
        """床的**睡觉触发格**候选（踩上去游戏才会弹出睡觉提问）；观测里没有床 ⇒ `[]`。

        判据**只认两处**（`docs/_il-bed-interaction.md` §2.2/§2.6）：
        * 优先 `furniture[].bedCells` —— 桥用游戏自己的
          `doesTileHaveProperty(x, y, "TouchAction", "Back") == "Sleep"` 现算，权威，
          且不受 `bedTileOffset` 逐帧翻转影响；
        * 缺失/空表 ⇒ 退回床原点的两个兜底槽位 `BED_CELL_FALLBACK`（`(x, y+1)` / `(x+1, y+1)`）。

        **绝不硬编码 (9,9)/(10,9)**：换个存档、换张床、甚至同一张床不同帧都可能不是那两格。
        """
        cells: list[tuple[int, int]] = []

        def _add(xy: Any) -> bool:
            if not isinstance(xy, (list, tuple)) or len(xy) < 2:
                return False
            try:
                cell = (int(xy[0]), int(xy[1]))
            except (TypeError, ValueError):
                return False
            if cell in cells:
                return False
            cells.append(cell)
            return True

        for f in FarmWorker.furniture_of(obs):
            if not f.get("isBed"):
                continue
            got = False
            raw = f.get("bedCells")
            if isinstance(raw, (list, tuple)):
                for c in raw:
                    if _add(c):
                        got = True
            if got:
                continue
            base = f.get("tile")
            if not isinstance(base, (list, tuple)) or len(base) < 2:
                continue
            try:
                bx, by = int(base[0]), int(base[1])
            except (TypeError, ValueError):
                continue
            for dx, dy in BED_CELL_FALLBACK:
                _add((bx + dx, by + dy))
        return cells

    def _cell_order(self, cells: list[tuple[int, int]], obs: dict[str, Any]) -> list[tuple[int, int]]:
        """把触发格候选按"离玩家近"排序（不改变集合，只决定先试哪一格）。"""
        pt = self.player_tile(obs) or (0, 0)
        return sorted(cells, key=lambda t: abs(t[0] - pt[0]) + abs(t[1] - pt[1]))

    def _walk_off(self, avoid: set[tuple[int, int]], obs: dict[str, Any],
                  *, timeout_ms: int = 8000) -> tuple[bool, str]:
        """**先走离床格一步**，再去踩触发格。

        【为什么必须多这一步】游戏只认"**移动中**踩到触发格"：`performTouchAction` 的 `"Sleep"` 分支
        有一道 `if (!Game1.player.hasMoved) skip`（`Farmer.hasMoved` 只在 `MovePositionImpl` 里置位）。
        人已经站在触发格上时再 `move_to` 同一格是空操作 ⇒ 提问永远不弹（真机配方：先走 (8,9) 再踩 (10,9)）。

        挑"四邻里不在 `avoid` 内、且观测说能站"的格子（观测没提到的排最后，交给 Mod 自己拒绝）。
        """
        pt = self.player_tile(obs)
        if pt is None:
            return False, "读不到玩家所在格，没法先走离床格"
        tiles = self.tiles_of(obs)
        cands = [t for t in ((pt[0] + dx, pt[1] + dy) for dx, dy in NEIGHBORS) if t not in avoid]
        if not cands:
            return False, f"四邻全在床格 {sorted(avoid)} 里，没法「先动过」"

        def rank(t: tuple[int, int]) -> tuple[int, int]:
            tv = tiles.get(t)
            if tv is None:
                return (1, 0)                       # 观测没这一格：让 Mod 自己判
            return (0 if tv.get("standable") else 2, 0)

        tried: list[str] = []
        for t in sorted(cands, key=rank):
            try:
                self.c.move_to(t[0], t[1], timeout_ms=timeout_ms)
                self.walk_steps += 1
                return True, f"已先走离床格一步到 {t}（满足 Farmer.hasMoved 前置）"
            except BridgeError as exc:
                tried.append(f"{t}:{_exc_status(exc) or 'failed'}")
        return False, f"床边没有可站的非床格（试过 {'、'.join(tried)}）"

    def _step_onto(self, cell: tuple[int, int], *, timeout_ms: int = 10000) -> tuple[bool, str]:
        """踩上睡觉触发格。

        **`ui_modal` 回执是命中信号，不是失败**（task-33 真机定案）：踩中触发格的同一帧，游戏自己把
        `Go to sleep for the night?` 弹出来 ⇒ 世界被冻结 ⇒ `move_to` 必然以 `ui_modal` 收场。
        把它当失败重试会永远走不到"应答"那一步。
        """
        try:
            self.c.move_to(cell[0], cell[1], allow_bed=True, timeout_ms=timeout_ms)
            self.walk_steps += 1
            return True, f"已踩触发格 {cell}（回执 ok；若提问还没弹，下面会再等一次观测）"
        except BridgeError as exc:
            status = _exc_status(exc)
            if status == "ui_modal":
                self.walk_steps += 1
                return True, (f"已踩触发格 {cell}：回执 ui_modal = **命中信号**"
                              "（睡觉提问被自己弹出来了，世界冻结是预期行为）")
            return False, f"踩触发格 {cell} 失败：{_receipt(exc)}"

    def _await_question(self, obs: dict[str, Any], *, rounds: int = 4,
                        step_s: float = 0.3) -> tuple[bool, str, dict[str, Any]]:
        """踩上触发格之后再等几帧观测：提问是**下一帧**由 `performTouchAction` 弹出来的。

        返回 `(ready, why, obs)`；`rounds=0` 或已 ready 时不等待（单测里 `pause` 是 no-op）。
        """
        ready, why = self.sleep_ready(obs)
        for _ in range(max(0, int(rounds))):
            if ready:
                break
            self.pause(step_s)
            obs = self.snap()
            ready, why = self.sleep_ready(obs)
        return ready, why, obs

    def _dismiss_question(self) -> str:
        """**兜底关框**：Mod 的 `SleepSkill` 已在同一 tick 关框，这里是它没做到时的最后一道。

        真机定案：答 Yes 之后 `Game1.newDay` 已经置位，日期不动只是因为提问框还挂着
        ⇒ 关框后 ~3s 当天落地。没有 `dismiss_modal`（旧桥/假件）就如实说明，绝不抛。
        """
        fn = getattr(self.c, "dismiss_modal", None)
        if fn is None:
            return "桥客户端没有 dismiss_modal（跳过兜底关框）"
        try:
            res = fn(timeout_ms=5000)
        except BridgeError as exc:
            return f"兜底关框失败：{_receipt(exc)}"
        except Exception as exc:                     # noqa: BLE001 - 关框失败不能拖垮睡觉
            return f"兜底关框异常：{type(exc).__name__}: {exc}"
        if isinstance(res, dict):
            reason = str(res.get("reason") or "")
            return f"兜底关框：{reason[:200] if reason else res.get('status') or 'ok'}"
        return "兜底关框：已发出"

    def _await_day_change(self, day_before: tuple, obs: dict[str, Any], *,
                          rounds: int = 12, step_s: float = 0.5) -> dict[str, Any]:
        """关框之后再等日期前进（**绝不重发 sleep**；重发会把已置位的 newDay 流程搅乱）。

        真机 ~3s 落地；这里给 ~6s（`rounds × step_s`）。Mod 的 `sleep` 调用本身已经阻塞等到
        `Date.TotalDays` 前进或超时，所以这条循环主要是"Mod 回 timeout 但我们刚关完框"的补救。
        """
        for _ in range(max(0, int(rounds))):
            if self.day_key(obs) != day_before:
                return obs
            self.pause(step_s)
            obs = self.snap()
        return obs

    def sleep(self, *, home: str = "FarmHouse", timeout_ms: int = 15000) -> StepResult:
        """睡觉跨日：回家 → 走到床边 → 先走离床一步 → **踩睡觉触发格** → 提问开才 `sleep` 应答。

        【为什么必须由脑主动做】真机发现：世界加载状态下**时间照走**，闲置到 02:00 游戏会
        自动 pass-out 睡觉 —— 那是"没人管"的结果，不是自动化。主动睡觉才是跨日正路，
        也只有它能在验收里区分"我们睡了"和"我们被系统睡了"。

        【2026-10-13 改成"踩床"（`docs/_il-sleep-path.md`，task-8）】
        * `GameLocation.answerDialogueAction` 是**字面量分派**：只有 `"Sleep_Yes"` 会走到
          `startSleep()`，别的键**静默 no-op**（回执 ok 完全不代表游戏做了事）
          ⇒ 判据只能是观测差分。
        * 引出提问的**唯一**正路是踩到床的 `TouchAction == "Sleep"` **触发格**
          （`GameLocation.UpdateWhenCurrentLocation → performTouchAction`）。旧实现
          `stand_next_to(bed)` + `interact(bed)` 已被真机彻底否掉：对 6 个床占位格逐个
          `interact`（=游戏 `checkAction`）全部返回 False、`dialogueIsQuestion` 恒 false
          —— 它是**静默 no-op**，不是"差一点"（task-33 施工单第 1 条 / task-31 §2.5）。
        * 触发格不硬编码：优先桥的 `furniture[].bedCells`，缺失退回 `BED_CELL_FALLBACK`
          （`(x, y+1)` / `(x+1, y+1)`）；踩中时 `move_to` 回 `ui_modal` 是**命中信号**。
        * 游戏还要求这一帧"真的移动过"（`Farmer.hasMoved`）⇒ 站在触发格上要先**走离**一步再踩。
        * 判据**不是** `isInBed`（见 `sleep_ready`）；提问没弹出来时 Mod 会**秒级**回
          `sleep_no_question`（携 `lastQuestionKey`/`isInBed`/`activeMenu` 诊断），所以这里
          不再白等 180s（Mod 侧跨日预算也从 120s 收到 15s）。
        * 答 Yes 之后 **Mod 在同一 tick 关框**（`answerDialogue()` 本身不关框，这是 run2 卡住的真因）；
          Mod 回 `timeout` 时脑侧再 `dismiss_modal()` 兜底 + 等日期前进，**绝不重发 `sleep`**。

        【NIT-3（deputy-lead 验收）：桥中途沉默不许 traceback 穿出】本函数只做两件事：
        * 把整段流程交给 `_sleep_impl()`；
        * 任何 `BridgeError`（以及观测解析之类的意外异常）都转成**有界**的 `StepResult`：
          `ok=False`、`code=<桥的 status，缺省 "bridge_down">`，reason 带
          `day_before`/`time_before`/`isInBed`/最后一步；**若异常发生在跨日之后**（观测显示
          `day_key` 已变）仍按成功返回，reason 注明"跨日已发生，之后桥失败"。
        这样 run3 里桥掉线也不会以 traceback 结束本轮 —— 日报照旧落盘，证据不断。
        """
        r = StepResult(action="sleep")
        state: dict[str, Any] = {"day_before": None, "stage": "开始", "diag": []}
        try:
            return self._sleep_impl(r, home=home, timeout_ms=timeout_ms, state=state)
        except BridgeError as exc:
            return self._sleep_bridge_fail(r, exc, state)
        except Exception as exc:                   # noqa: BLE001 - 观测解析等意外同样不许穿出
            return self._sleep_bridge_fail(r, exc, state, fallback_status="bridge_down")

    def _sleep_impl(self, r: StepResult, *, home: str, timeout_ms: int,
                    state: dict[str, Any]) -> StepResult:
        """`sleep()` 的主体；异常一律由外层 wrapper 的 `_sleep_bridge_fail()` 收口。"""
        obs = self.snap()
        day_before = self.day_key(obs)
        state["day_before"] = day_before
        state["stage"] = "已取到初始观测"
        r.before = self._sleep_probe(obs)
        loc = str((obs.get("location") or {}).get("name") or "")
        if loc != home:
            state["stage"] = f"去 {home}（ensure_location）"
            mv = self.ensure_location(home, timeout_ms=30000)
            if not mv.ok:
                r.code, r.reason, r.receipt = "failed", f"回不了 {home}：{mv.reason}", mv.receipt
                return r
            obs = self.snap()

        # ① 用游戏自己的路径把睡觉提问引出来：走到床边 → 先动一步 → 踩触发格。
        diag = state["diag"]
        cells = self.bed_cells(obs)
        if not cells:
            diag.append("观测里没有 isBed 家具（furniture[].bedCells / tile 都读不到）")
        ready, why = self.sleep_ready(obs)
        if cells and not ready:
            state["stage"] = "床边：先走离一步再踩触发格"
            avoid = set(cells)
            if self.player_tile(obs) in avoid:
                _moved, note = self._walk_off(avoid, obs)
                diag.append(note)
                obs = self.snap()
            for cell in self._cell_order(cells, obs):
                _hit, note = self._step_onto(cell)
                diag.append(note)
                obs = self.snap()
                ready, why, obs = self._await_question(obs)
                if ready:
                    break
        if not ready:
            # 走到床边、踩过触发格仍然没有提问 ⇒ **立即**如实失败（绝不白等）：
            # 真机上这时再发应答就是静默 no-op；Mod 侧同样会秒级回 sleep_no_question。
            state["stage"] = "没有引出睡觉提问"
            r.code = SLEEP_NO_QUESTION
            r.reason = (f"没有引出睡觉提问 ⇒ 判据说现在睡不了：{why}"
                        f"；触发格候选 {cells or '—'}"
                        f"；脑侧现场：{'；'.join(diag) if diag else '—'}"
                        f"；观测：{self._sleep_probe(obs)}")
            return r

        state["stage"] = "已引出提问，正在发 sleep 应答"
        try:
            res = self.c.sleep(timeout_ms=timeout_ms)
        except BridgeError as exc:
            raw = str(getattr(exc, "status", "") or "")
            if not raw or raw == "bridge_down" or raw in BRIDGE_DOWN_STATUSES:
                # NIT-3：这不是"游戏/Mod 的业务失败"，而是桥本身没了 ⇒ 交给外层统一收口
                # （有界返回 + "请按桥掉线处理"），不走"兜底关框"这种同样需要桥的补救。
                raise
            status = raw
            r.code = status if status in SLEEP_FAIL_CODES else "failed"
            # task-22：睡觉也可能撞上渐黑/模态/没存档（全桥通用码）——按同一口径打标，
            # 免得"任意 skill 的一次瞬时环境抖动"这句话在 sleep 上是假的。
            _mark_status(r, raw)
            r.receipt = _receipt_long(exc)
            r.reason = f"睡觉失败（{status}，脑侧判据：{why}）：{str(exc)[:300]}"
            # ② 兜底关框 + 等日期（**不重发 sleep**）：Mod 回 timeout 时，真因多半就是
            # "答了 Yes、`Game1.newDay` 已置位、但提问框还挂着" ⇒ 关框 ~3s 就能当天落地。
            diag.append(self._dismiss_question())
            state["stage"] = "sleep 回失败，正在兜底关框/等日期"
            obs = self._await_day_change(day_before, self.snap())
            day_after = self.day_key(obs)
            r.after = self._sleep_probe(obs)
            if day_after != day_before:
                r.ok = True
                r.code = ""
                r.env_block = False
                r.inconclusive = False
                r.reason = (f"已跨日（Mod 回执={status}，跨日由**关框兜底**促成）："
                            f"{day_before[1]} {day_before[2]}日 → {day_after[1]} {day_after[2]}日"
                            f"；脑侧现场：{'；'.join(diag)}")
                return r
            r.reason += f"；脑侧现场：{'；'.join(diag)}"
            return r

        state["stage"] = "sleep 回执已到，正在等日期前进"
        obs = self._await_day_change(day_before, self.snap())
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

    def _sleep_bridge_fail(self, r: StepResult, exc: BaseException, state: dict[str, Any],
                           *, fallback_status: str = "") -> StepResult:
        """把"睡觉过程中桥失败"收成**有界**的 `StepResult`（NIT-3 / deputy-lead task-33 验收）。

        两条硬规则：
        1. **绝不抛**：回到调用方时永远是一个 `StepResult`（`ok=False`、`code=<status 或 bridge_down>`），
           reason 里留下 `day_before`/最后一步/脑侧现场，`after` 里留下 `stage`；
        2. **不许吞掉"日期真的变了"**：桥是在跨日**之后**才死的 ⇒ 仍按成功返回
           （判据是观测差分，不是桥还活着）。
        """
        status = _exc_status(exc) if isinstance(exc, BridgeError) else ""
        if status in BRIDGE_DOWN_STATUSES:
            status = "bridge_down"                 # 桥自己没了 ⇒ 统一码，别让 run3 只看到 connection_broken
        status = status or fallback_status or "bridge_down"
        day_before = state.get("day_before")
        stage = str(state.get("stage") or "未知")
        diag = "；".join(state.get("diag") or []) or "—"
        try:
            obs = self.snap()
            day_after = self.day_key(obs)
            if day_before is not None and day_after != day_before:
                r.ok = True
                r.code = ""
                r.env_block = False
                r.inconclusive = False
                r.after = {**self._sleep_probe(obs), "stage": stage}
                r.reason = (f"已跨日（{day_before[1]} {day_before[2]}日 → "
                            f"{day_after[1]} {day_after[2]}日），之后桥失败：{status}: {str(exc)[:200]}"
                            f"；最后一步={stage}；脑侧现场：{diag}")
                return r
            r.after = {**self._sleep_probe(obs), "stage": stage}
        except Exception as exc2:                  # noqa: BLE001 - 连观测都拿不到 ⇒ 只能报桥掉线
            diag = f"{diag}；失败后再观测也失败：{type(exc2).__name__}: {exc2}"
            r.after = {"day_before": list(day_before) if day_before else None, "stage": stage}
        r.ok = False
        r.code = status
        _mark_status(r, status)                    # 环境类（no_save/ui_modal/world_fading/busy）照旧打标
        r.receipt = _receipt_long(exc) if isinstance(exc, BridgeError) else ""
        r.reason = (f"睡觉过程中桥失败：{status}: {str(exc)[:200]}"
                    f"（跨日未完成，请按桥掉线处理）；最后一步={stage}；脑侧现场：{diag}"
                    + ("" if isinstance(exc, BridgeError) else f"；异常类型={type(exc).__name__}"))
        return r

    # ------------------------------------------------------------- 买种子
    def buy(self, item: str, count: int = 10, *, shop: str = "SeedShop",
            timeout_ms: int = 25000) -> StepResult:
        """买种子。判据 = 钱减少 **且** 背包里该物品变多（回执里游戏返回值不是成败，见开发日志 023）。

        【task-67】无论成败，回执里的**货架清单**都要带回来（`r.available`）：
        `item_not_sold` 时它是脑唯一能"改买当季种子"的信息（run6 每天靠字符串猜货架、白试 6 次）。
        """
        r = StepResult(action="buy")
        obs = self.snap()
        money_before = self.money(obs)
        have_before = _count_item(self.player_of(obs), item)
        r.before = {"money": money_before, "item": have_before}
        try:
            res = self.c.buy(item, count, shop=shop, timeout_ms=timeout_ms)
        except BridgeError as exc:
            r.receipt = _receipt(exc)
            # 失败回执原文在 `exc.payload`（`bridge.py::_request`）⇒ 一样能读货架。
            r.available = seed_offers_from(getattr(exc, "payload", None))
        else:
            # 旧桥（0.7.24 及之前）返回 None ⇒ `seed_offers_from` 给空表，语义 = "没有清单"。
            r.available = seed_offers_from(res if isinstance(res, dict) else None)
        obs = self.snap()
        money_after = self.money(obs)
        have_after = _count_item(self.player_of(obs), item)
        r.after = {"money": money_after, "item": have_after}
        if r.available:
            r.after["available"] = len(r.available)
        if have_after > have_before and money_after < money_before:
            r.ok = True
            r.reason = (f"买到 {have_after - have_before} 个 {item}（钱 {money_before}→{money_after}"
                        f"；货架 {len(r.available)} 条）")
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
            if action in ("clear", "clear_dead", "till", "water", "harvest", "sow") and stam < min_stamina:
                res.stopped, res.stopped_reason = "stamina", f"体力 {stam:g} < {min_stamina:g}"
                break

            if action == "clear":
                st = self.clear(tile)
            elif action == "clear_dead":
                st = self.clear_dead(tile)
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
