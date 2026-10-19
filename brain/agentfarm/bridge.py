"""桥接客户端：与游戏内 Mod 的本地 HTTP 服务通信。

设计约束（见 docs/03-桥接协议.md）：

1. **只用标准库**（urllib / json / pathlib），零第三方依赖。
   脑是整个无人值守系统里最不该"因为装不上包而跑不起来"的部分。
2. **失败必须显式**：所有异常路径都抛 `BridgeError`（带机器可读的 `status`），
   绝不返回"看起来像成功"的空结果。旧方案最大的教训就是失败被静默吞掉
   （见 docs/_legacy-audit.md §3.2）。

协议契约由 docs/03-桥接协议.md 唯一定义；本文件是它的 Python 侧实现。
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---- 契约常量（改这里必须同步 docs/03-桥接协议.md 并升版本号） ----
SCHEMA_BRIDGE = "agentfarm-bridge/1"
SCHEMA_WORLD = "agentfarm-world/6"   # v5：新增 location.doors[]（仅 detail=full）；
                                     #     v4：新增 location.furniture[]（仅 detail=full），
                                     #     修掉 move_to 的家具误判（改问游戏 isPassable）。
                                     # v3：player.isInBed、game.paused / game.shouldTimePass、
                                     #     dismiss_modal 改 answerDialogue + closeDialogue、
                                     #     worldResumed / status=world_stuck。见 docs/03-桥接协议.md
SCHEMA_WORLD_LEGACY = ("agentfarm-world/5", "agentfarm-world/4", "agentfarm-world/3")
# 升级窗口期间的兼容口径：Mod 的 dll 被游戏锁住、必须重启游戏才能换版本，
# 所以"脑已经改了、游戏里还是上一版 Mod"是**正常会发生的中间态**。
# 对上一版 schema：**接受 + 大声警告一次**（新字段不可用），绝不静默吞掉。
SCHEMA_EXEC = "agentfarm-exec/2"     # v2：新增 worldResumed
MOD_VERSION_EXPECTED = "0.7.49"   # v0.7.49：P0 判据批——指定作业区「大障碍」口径修正（D1）+ 经济派发真值修正（D2）
                                  # ①D1（阻断级，目标1 ②的生死线）：`fields.py` 的 `ZONE_BLOCKER_KINDS`
                                  #   原并入的是 `clumpKind` 的**子类型值**（stump/log/boulder/rockPile/
                                  #   greenRain），而 Mod 给 tile 的 `kind` 恰是**字面量 `"clump"`**
                                  #   （`WorldSnapshot.cs:807`；`Contracts.cs:590` 列 clump、`:598` 只有
                                  #   `kind=="clump"` 才填 clump* 元数据；`ClumpMeta.cs:38-73` 的 `KindOf`
                                  #   永不返回 "clump"）⇒ 三处判定点（`fields.py:344 zones_from_observe` /
                                  #   `:386 zone_blockers_total` / `:529 plot_in_zone`）**永不命中大障碍**，
                                  #   区内只剩树桩/圆木/巨石也报 blockers=0（**假清空**），
                                  #   `tools/verify-zone-retention.py` 会对"桩一直没清"的两次观测输出
                                  #   `PASS (retained clear)` / exit 0（observer 实测）；
                                  #   修法：`ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS | {CLUMP_KIND})`
                                  #   （`CLUMP_KIND="clump"`），另设 `CLUMP_SUBKINDS` 仅作可读原因、
                                  #   不再混进 kind 口径；`clumpKind=="unknown"` **仍计 blocker**；
                                  # ②D2：`longrun.py` 的 `buy` 分派原为 `changed = self._preconditions(obs, rep)`
                                  #   （拿观测 dict 当真值）⇒ **每条 buy 恒 `executed_steps=1` + `acted`**
                                  #   （假装下单）、`{"unknown_evidence":1}` 成死代码；改
                                  #   `bool(self._preconditions_apply(obs, rep))`；
                                  # ③测试 +11 条（fields +8 / longrun +3），全量 `Ran 1405 / OK`；
                                  #   变异 4/4 killed（`git archive` 冻结树逐条复跑、Lead 独立复跑）；
                                  # ④`upgrade_tool` 工具硬编码 `"axe"`（对应目标1 ③铜斧链），留痕
                                  #   `tool="axe"` / `tool_hardcoded=True`，本批不做通用化；
                                  # ⑤本批无 Mod 代码变更：dll 与 0.7.47/0.7.48 逐字节相同（293888B/`C9B3BD6C…`）。
                                  # --- 历史 ---
                                  # v0.7.48：A9 门禁批快修——slot_relief 字段奇偶补齐（clear_gate 补 reached）
                                  # ①唯一改动：`_note_clear_area_bag_gate` 的 `slot_relief` 记录补
                                  #   `reached=False`（语义：clear_gate 是"今天不再新开 clear_area"的闸，
                                  #   不是"腾到目标水位" ⇒ 绝不谎报达标，与压力通道同口径）；由此
                                  #   demand/demand_basis/target_free/reached 齐平 task-237 字段集，
                                  #   analyze-longrun / verify-run3 与探针 smoke-0741/0742 不再 rc=1；
                                  # ②同类奇偶缺口排查：AST 扫 `longrun.py` 全部 `_journal` 调用点逐事件归类，
                                  #   除 slot_relief 外无"声明统一必带字段集却个别写入点缺项"的事件；
                                  # ③本批无 Mod 代码变更：dll 与 0.7.47 逐字节相同（293888B/`C9B3BD6C…`）；
                                  # checks 10 键语义与 `no_unmet_stages`/护栏 B 公式不变。
                                  # --- 历史 ---
                                  # v0.7.47：A9 门禁批快修——背包升级对话购买默认关闭（入口未取证，opt-in）
                                  # ①`backpack_upgrade_enabled` 默认 False：不发任何 goto SeedShop /
                                  #   talk / buy 请求，只留只读 `buy{status:skipped,code:disabled}` 与
                                  #   `day_end.backpack_upgrade_skip="disabled"`，不写 checks、不加 notes；
                                  # ②显式开启：`run-longrun.py --enable-backpack-upgrade` 或
                                  #   `AGENTFARM_ENABLE_BACKPACK_UPGRADE=1/true/yes/on`；开启后与 0.7.46 一致
                                  #   （gate capacity==12 且 money>=2000 / 每天 ≤2 次失败 / ≤90s /
                                  #   钱−2000 且容量 12→24 双差分）；
                                  # ③关闭原因（task-34 真机探针 4524665）：进 SeedShop 触发过场事件
                                  #   3102768（先清 26 次 advance），相邻 talk Pierre 只回
                                  #   activeMenuText="Sigh..."（非提问、无选项）；SeedShop 货架 20 条无背包
                                  #   条目；Town 事件 15389722 仍 5 进 4 卡死（唯一恢复 load_save(force)）
                                  #   ⇒ 对话入口【无法判定】，机制确认后再开（并入 task-14 升级路径评估）；
                                  # ④本批无 Mod 代码变更：dll 与 0.7.46 逐字节相同（293888B/`C9B3BD6C…`）；
                                  # checks 10 键语义与 `no_unmet_stages`/护栏 B 公式不变。
                                  # --- 历史 ---
                                  # v0.7.46：A9 门禁批——真机冒烟（0.7.45 smoke）暴露的四形态 + 背包升级入口
                                  # ①售材纪律（task-28）：`SURPLUS_MATERIAL_IDS` 收窄为 {92 Sap,766 Slime}，
                                  #   建材/锭类（388 Wood/390 Stone/330 Clay/771 Fiber/382 Coal/378 Copper/
                                  #   380 Iron/384 Gold/386 Iridium/909 Radioactive）永不卖；作物/晶石仍可卖；
                                  #   `SELLABLE_SURPLUS_IDS` fail-closed，保留规则不变；
                                  # ②inventory_blocked 证据门槛（task-28）：四门槛（free_slots==0 /
                                  #   relief_exhausted 由卖单规则算出 / pending_executable==0 /
                                  #   pending_malformed==0）全过才认诚实收工；`stuck:` 永不认；
                                  #   满包清障有界 `CLEAR_LOOT_LOSS_MAX_STEPS=5`（结构性封顶、留痕
                                  #   `slot_relief{trigger:"clear_gate"}`）；`day_end` 新字段 `relief_exhausted`/
                                  #   `bag_evidence{…loot_lost_steps/loot_lost_limit}`；
                                  # ③回片区预算（task-26）：`resume_walks` 只数走成、`resume_walk_attempts`
                                  #   另计（2×上限）；`resume_exhausted` 仅 `pending_executable==0` 时认，
                                  #   否则写 `resume_budget_exhausted:`（不进白名单，day_justified=false）；
                                  # ④挡死格证据口径（task-27）：目标池前置过滤 `_known_enclosed`
                                  #   （四邻全观测、无一可站、无可清障够得着）＋执行层 `_observed_foothold`
                                  #   （观测到落脚点才算"本该可达"），无证据的归 encircled 不进 unreachable；
                                  #   判死格仍进 assigned_undone（不洗成没活）；`unreachable_within_bound`
                                  #   公式与 20% 未动；新 stage 字段 encircled_attempted/prefiltered；
                                  #   `day_end`/`no_progress_burst` 增 `pending_executable_tiles[:8]`/
                                  #   `pending_stalled_tiles[:8]`；
                                  # ⑤Mod talk 原语（task-33，Mod）：`talk {"npc":"Pierre"}` 按名找角色 →
                                  #   相邻校验（不满足回 `not_adjacent`+npcTile）→ 调游戏 `NPC.checkAction`；
                                  #   禁合成键鼠、禁改 Money/Items/MaxItems；
                                  # ⑥背包升级对话购买（task-25）：`talk Pierre` → `dismiss_modal{answerText:
                                  #   "Purchase"}` → 双差分（钱−2000 且 inventoryCount 12→24）才算成功；
                                  #   每天 ≤2 次失败、流程 ≤90s、Town 事件卡死 `event_hang` + load_save 自愈；
                                  #   journal 复用 `buy`（source=backpack_dialogue）无新事件名；
                                  # checks 10 键语义与 `no_unmet_stages`/护栏 B 公式不变。
                                  # --- 历史 ---
                                  # v0.7.45：诚实收工判据 + 背包满留痕/腾格 + 残缺 tile fail-closed
                                  # （0.7.44 真机冒烟 FAIL 暴露：冬26/27 诚实收工日被守卫累积账本误判）——
                                  # ①诚实收工判据（task-15）：`_pending_work()` 剔 `resume_stall_tiles`/
                                  #   `encircled_day`，原始账本口径另存 `_ledger_pending()`；`_pending_snapshot`
                                  #   六口径并列（ledger/guard/stalled/blocked/executable/unobserved；
                                  #   不变式 ledger==guard+blocked、guard==executable+unobserved+malformed）；
                                  #   观测缺失 ⇒ executable=guard（fail-closed）；`is_justified_end` 增证据门槛：
                                  #   `resume_exhausted` 仅 `pending_executable==0` 才认，`stuck:` 永不认；
                                  #   burst/换片上限改走 `_resume_exhausted` 诚实收工（不再写 `stuck:`）；
                                  #   sleep_guard 的 no_work 分支遇只剩挡死格拒绝白拿；`day_end` 新字段
                                  #   `pending_ledger/pending_guard/pending_stalled/pending_executable/
                                  #   pending_blocked/pending_unobserved/pending_malformed` +
                                  #   `stage_midway_leftover`（早轮 leftover 不被末轮 0 遮蔽）；
                                  # ②背包满（task-16）：每次观测算 `free_slots = inventoryCount −
                                  #   len(inventory[])`（容量≠件数）；`free_slots==0` 压力通道走既有
                                  #   slot_relief（白名单/建造预留/每 qid 下限；工具/武器/种子/建材/锭类永不卖；
                                  #   卖走 `Farm.shipItem`/`sell` + 钱/背包行数双差分）；`clear()` 满包掉落留
                                  #   `loot_lost`（只 info，不判失败）；买种前先腾格、腾不出诚实不买；
                                  #   `day_end` 新字段 `free_slots_*`/`loot_lost_*`；
                                  # ③残缺 tile fail-closed（task-22）：观测 `tiles[]` 里出现但缺 kind/crop
                                  #   （且不在 tillable[]）的残缺记录单列 `malformed`，`is_justified_end` 在
                                  #   任何收工理由之前一票否决 `day_justified`（缺失≠通过）；不变式
                                  #   guard==executable+unobserved+malformed；`day_end.pending_malformed`；
                                  #   checks 10 键语义不变、无新增 journal 事件名。
                                  # --- 历史 ---
                                  # v0.7.44：两条收工/分配死循环修复 + 收工口径（A8 臂 12 天暴露）——
                                  # ①回片区拿不出目标不许判 stuck（task-4）：`_leftover` 按片区归属
                                  #   （`leftover_area`）替代全场 tmap；`resume_stall_tiles` 记停滞邻域；
                                  #   `_resume_switch_or_exhaust` 三档：换另一片账本待做格 → 当前观测
                                  #   `frontier_clear` 清一格 → `resume_exhausted:` 诚实收工
                                  #   （`day_justified=false`，不再写 `stuck:回片区…`）；journal 新字段
                                  #   `plot_exhausted{source,from_area,to_area,stalled_tiles,switches,…}`、
                                  #   `no_progress_burst{exhausted,…}`、`resume_walk{switched}`；
                                  # ②挡死格当天不再重分配（task-5）：`_dead_tile_set()` = blocked ∪
                                  #   encircled_day，阶段目标池/片区有活判据/回片区挑格全部扣掉；`leftover`
                                  #   拆 `leftover_executable/leftover_blocked`；同格重分无产出有界
                                  #   `MAX_ALLOC_NO_PROGRESS=3`（`blocked{action:"stage_realloc",
                                  #   alloc_no_progress,limit}`）；`day_end` 新字段
                                  #   `plot_pending_executable/plot_pending_blocked`；
                                  # ③收工口径（task-6）：`checks.slept_by_us` 取 `rep.slept_ok` 真值
                                  #   （`day_end.slept_ok`，不再用 `ended_by==sleep` 冒充「我们睡的」）；
                                  #   `deferred_by_budget` 改日终按浇水证据落账，浇水达标日压制为
                                  #   `stamina_budget.deferred_by_budget_suppressed` ⇒「只因预算延后」
                                  #   与「户外浇水达标」永不同真；
                                  # ④同形态入口统一（task-11）：`review_only_fallback` /
                                  #   `guard_leftover` 触顶或只剩挡死格时统一走换片/诚实收工，删除
                                  #   `_no_progress_stop`，不再写 `stuck:`（无新事件名/字段）。
                                  # --- 历史 ---
                                  # v0.7.43：事件有界等待 + 清障逐格证据口径（0.7.42 八步冒烟抓出的两条）——
                                  # ①事件有界等待（task-245）：Mod `UiView.eventId`（三态：真值 /
                                  #   null=读不到 / 缺失=旧 Mod）+ `EventRules.IdFor`（1.6.15 走
                                  #   static `Game1.CurrentEvent`）；脑侧 `eventUp` 且无对话盒 ⇒
                                  #   有界等待 4×15s（journal `event_wait{tries,limit,eventId,
                                  #   eventUp,hasDialogue,worldSeq,waitSeconds}`），超时才
                                  #   `event_blocked`（带 eventId/eventWaitTries/eventWaitSeconds）；
                                  #   有提问/职业选择立刻硬停，绝不 dismiss/替游戏选；
                                  # ②清障逐格证据（task-242）：`clear_area` 的 `ok` 只计真变化步，
                                  #   `already` 步单列（`stage.already_tiles/already_cause`），
                                  #   `ok == attempted_ok == ok_tiles` 三口径对齐（修 0.7.42 冒烟
                                  #   步 5 抓出的「75 次尝试 / 62 格实清」13 步差额）。
                                  # v0.7.42：冬季可验证性 + 清障吞吐批次（0.7.41 七步冒烟抓出的两条
                                  # A″ 门禁级缺陷）——
                                  # ①种子季节闸门（task-240）：Mod `PlayerView.seeds[]`
                                  #   `{id,name,stack,seasons,plantableNow}`（三态可辨）+ `SeedRules`
                                  #   纯函数 + `Data/Crops` 取季节；脑侧 `plantable_seeds` /
                                  #   `seed_season_state` / `has_seed_metadata`；`_seed_outlook`
                                  #   首值改「当季可种」；全隔季 ⇒ 诚实 `no_work`；farm 级
                                  #   「该去种」只在人不在农场或**窗口真有 plantable 目标**时出现；
                                  #   `plant_area` 零目标补 `evidence.why="seed_out_of_season"`；
                                  # ②清障吞吐（task-241）：树/石/枝 `tool_ineffective` 有界补请求
                                  #   `TREE_SWING_CALLS=3`（kind 变即停）+ `tool_ineffective_bound`
                                  #   证据；清障预算改体力驱动 `MAX_TREES_PER_DAY=20` /
                                  #   `_tree_budget_room`（conservative 0、绝不为砍树漏浇）+
                                  #   `deferred_by_budget{task:"clear_area_tree"}`。
                                  # --- 历史 ---
                                  # v0.7.41：全脑侧修复批次（0.7.40 七步冒烟抓出的三处真缺陷；
                                  # Mod 无代码变更，dll 与 0.7.40 同源重建）——
                                  # ①末次跨日落盘守卫（task-236）：跑尾声 `ui.isModal` ⇒ ≤3 次
                                  #   `dismiss_modal`（`modal_dismissed{kind:"cleanup"}`）/
                                  #   `cleanup_blocked` + `finish.cleanup_modal_stuck`；`eventUp`、
                                  #   职业弹窗、存档菜单收尾也绝不关；工具侧 `verify-run3 --smapi`
                                  #   六串判据计数（L16 插件行只进原始计数）全等 + 末次 NewDay 行号
                                  #   早于末次 Save called；
                                  # ②需求驱动腾格（task-237）：`_harvest_demand`（窗口 ready /
                                  #   readyTiles / farm.readyCrops，封顶 12，缺失 ⇒ 保守 3 +
                                  #   demand_basis）⇒ `target_free=min(SLOT_RESERVE+demand,12)`；
                                  #   提前到所有阶段前、6 轮/10 叠、优先卖当天收获产物、卖前清模态；
                                  #   修红线漏洞：多叠同 qid 逐个扣减（卖完仍 ≥K）；
                                  # ③§8 意图对账兜底（task-238）：`executed_steps==0 && reasons=={}`
                                  #   按当天 `ended_by` 回填闭合原因码（`why="finalize_fallback"`），
                                  #   只补原因码、不改步数/判定。
                                  # --- 历史 ---
                                  # v0.7.40：全脑侧修复批次（Mod 无代码变更，dll 与 0.7.39 同源重建）——
                                  # ①非片区意图（ship/sell/sleep/review/recover_stamina/
                                  #   wait_for_save）失败不许裸用 `no_target`，证据不可用 ⇒
                                  #   `unknown_evidence` + `unknown_why`（non_plot_task/no_plot/
                                  #   obs_unavailable）；ship 失败带自有证据包（task-233）；
                                  # ②空格压力通道：`slot_relief` 在 `free_slots <= SLOT_RESERVE` 时
                                  #   按三档已知表（作物余量→材料→矿/晶洞）卖一叠腾格；`NEVER_SELL`
                                  #   + 表外 fail-closed + 每 qid 留 K=10；`SLOT_RELIEF_RESERVES`
                                  #   对建造材料覆盖保留量（铜矿 25 / 石头 30 / 煤 5）且**永不整叠
                                  #   卖空**；只走 `worker.sell()` + 卖前后钱/背包行数双差分，
                                  #   腾不出如实 `inventory_blocked`（task-232）。
                                  # --- 历史 ---
                                  # v0.7.39：能力覆盖与"意图对账"批次 —— Mod 侧
                                  # ①`debug_dump` 支持 1.6 强类型资产（`trigger_actions`/`objects`/
                                  #   `big_craftables`/`machines`，逐表 fail-closed + `type`/`error` +
                                  #   `matchMode=value_substring`），并暴露 `knownCraftingRecipes`
                                  #   三态（task-222）；
                                  # ②新技能 `advance_dialogue`：**只推进非提问对话**，提问/职业选择
                                  #   fail-closed、永不替游戏选（task-228）；
                                  # ③新技能 `craft_item`/`place_object`/`machine` + 逐格机器状态与
                                  #   `location.objectList`（≤64、(y,x) 排序、截断、三态）（task-210）；
                                  # ④`FarmView.clumps` 等五类障碍计数同源补齐 + `SkillCatalog` 单一
                                  #   数据源、C# 自检 85 断言（task-230/216）。
                                  # 脑侧：树纳入清障 + 护栏 A/B（task-218）；意图-执行对账 + gaps 旁车
                                  # （task-219/230）；事件受控推进守卫（task-228）。
                                  # --- 历史 ---
                                  # v0.7.38：0.7.37 白名单事故 + F3 取回死锁的补救批次 —— Mod 侧
                                  # ①新增 `SkillCatalog.cs` 单一数据源：`Skills.Create` 的每个 case 名
                                  #   必须登记，`BridgeHost` 的 known 判定与 `IsLongTaskSkill` 语义
                                  #   全部从这张表派生（0.7.37 装机版漏登记 7 个新技能 ⇒ 全回
                                  #   `unknown_skill` 的**永久护栏**）（task-216）；
                                  # ②C# 自检 +7 断言：Catalog 与 `Skills.Create` 的 case 集合**双向相等**、
                                  #   `ToolUpgradeRules.Select` 的「同 kind + tier==tierBefore+1」与
                                  #   「多命中必须拒绝」（task-216 GAP-2）。
                                  # 脑侧同批（非 Mod）：`_tool_upgrade_due` 的「紧急农活」闸门**只拦 upgrade**、
                                  # `pickup` 一律放行（F3 取回死锁）；`due=False` 的等待日必留
                                  # `tool_upgrade_skipped{reason:"wait"|"need_slot"}`；B1e（只扣钱等级 0→0）
                                  # /B2b（取回后背包没工具）不得判 ok（task-216）。
                                  # --- 历史 ---
                                  # v0.7.37：A′ 叫停后的 P0 收口批次 —— Mod 侧
                                  # ①`FarmView.readyTiles[]`（熟作物坐标，与 `readyCrops` 同源同扫描、
                                  #   上限 64、按 (y,x)、`readyTilesTruncated`）（task-199）；
                                  # ②`upgrade_tool`/`pickup_tool` 技能（铁匠铺 `ClintUpgrade` 闭环，
                                  #   买前自检 `toolBeingUpgraded==null && daysLeft==0 && !readOnly`，
                                  #   取回需 ≥1 空格）（task-205）；
                                  # ③`dismiss_modal` 显式应答 `answerIndex`/`answerText`（互斥、fail-closed、
                                  #   绝不回退自动 Yes）（task-208）；
                                  # ④内省面 `debug_dump`（7 张数据表）+ `add_missed_recipes`
                                  #   （反射 `Farmer.AddMissedMailAndRecipes()`，前后差分）（task-213）。
                                  # 脑侧同批：`no_slot` 阻塞类 + `slot_relief` 收敛 + 诚实
                                  # `inventory_blocked`（task-198）；`ready_far` 走位族（task-199）；
                                  # 工具升级策略（task-205）；analyzer 收 4 新事件（task-207）。
# v0.7.36：收获证据面收口（task-186/188/189）——Mod 侧
                                  # ①`use_tool`（含镰刀类作物）回执补 `acted` + `actedEvidence`，
                                  #   与 `interact` 同一套跨观测证据口径、**fail-closed**（证据不可得 ⇒
                                  #   `acted=false`，不允许 true）；②该证据提取抽成共享方法，
                                  #   `mod/AgentFarm.Bridge.Tests` 增加 use_tool 三态行为断言（26 断言）；
                                  # ③`use_tool` 失败文案不再把原物渲染成空（task-188 = R1/R4）。
                                  # 脑侧同批（非 Mod）：task-186 收获缺格不得当成功 + loot 对账 +
                                  # sell 白名单收窄；task-189 loot 记账 = 逐 qid 背包差 + 有界确认轮
                                  # （`LOOT_CONFIRM_TRIES=2 × 0.35s`）；task-192 释放认输区时同步扣减
                                  # 当天 `day_end.scope_shed*`（日终末态）+ 累计量 `shed_ever` 持久化。
                                  # v0.7.35（历史）：再生作物收获的因果链修正（task-177 真机）——
                                  # ①`Skills.interact` 的 `acted` 改由**跨观测证据**推导（TileSig /
                                  #   目标格 `ready` true→false / `farm.readyCrops` 下降 / 背包逐 qid
                                  #   栈数增加），全不命中才 `false`；②`ExecResponse.actedEvidence`
                                  #   明写证据来源；③`CropMeta` 把 `forageCrop && whichForageCrop==null`
                                  #   判成"判不了"；④新增零依赖 C# 自检工程 `mod/AgentFarm.Bridge.Tests`。
                                  # 脑侧同批（非 Mod）：task-181 harvest 观测差分四择一 + 逐 qid loot；
                                  # task-168 规模取舍 `reduce_scope`（认输区仍留在会计里、当天不 VERIFIED）。
                                  # v0.7.34（历史）：harvest 三处 Mod 硬缺陷（task-173 真机事故）——
                                  # ①`harvestMethod` 正解 = public 无参 `Crop.GetHarvestMethod()`
                                  #   （1.6.15 根本没有 `Crop.HarvestMethod` 字段）；键**无条件输出**
                                  #   （`JsonIgnoreCondition.Never`，读不到写 null）；
                                  # ②新增 `tiles[].readySource ∈ {"game","fields",null}`
                                  #   （反射成功 / 与 `HoeDirt.readyForHarvest()` IL 逐条等价的字段路径 / 判不了）；
                                  # ③`interact` 的 `acted` 改由目标格可观测签名（`TileSig`）前后差分推导，
                                  #   格没变 ⇒ `acted=false` + `status="no_action"`（回执不许自述成功）
                                  # v0.7.33：harvest 判据纠正（run A/B 第一病灶）—— Mod `CropMeta` 反射游戏 `HoeDirt.readyForHarvest()` 为权威（缺项 ⇒ null）、`TileView` 9 个形态字段 + `FarmView.readyCrops` + `ExecResponse.acted`、`tiles[].tool` 改按 `ready` 判浇水、`interact` 未动手 ⇒ `no_action`、镰刀类走工具路径；脑侧 `farmwork.tile_ready`（fail-closed）+ `harvest_gave_up` 同格上限（不进 `checks`、不扣 `_leftover`）
                                 # v0.7.32：run9d 诊断后的目标 2 解药 —— ①`water_far` 够不着的活苗
                                 # 先**有界开路**再回浇（清出的路 ≠ 浇过的水）；②单日**体力预算**
                                 # （`water_reserve = 活苗×2+12`、`capacity`）与规模控制，预算不足
                                 # 只延后 clear/till/plant 且延后格**不再算「还有活」**；
                                 # ③Mod 障碍物/工具等级元数据（`clumpTarget{tool,minLevel}`/`toolOk`）
                                 # + 脑侧工具不够格不空挥；阶段体力实测留痕（`stamina_calibration`）。
                                 # v0.7.31：run9c 诊断后的口径修复 —— ①播种分配额 = 手上种子数
                                 # （`plant_area` 上限 `min(per_stage_tiles, seeds_total)`，
                                 #   买不到种子 **不算** 今天该做的活做完）；
                                 # ②浇水阶段壶空先补水再续做（阶段内 ≤2 次，把分下去的格做完；
                                 #   补水不可能才如实 `stopped="need_refill"`）；
                                 # ③雨日 0 动作 fail-open 修法（农场级工作理由
                                 #   `hoeDirt`/`emptyDirt` fail-closed + 日初 `goto_farm` 被
                                 #   `ui_modal` 挡住后清模态**真重试一次** +
                                 #   `checks.zero_action_evidenced`：0 动作日没有独立证据不许 VERIFIED）。
                                 # v0.7.30：run9b 复盘四件事 —— ①water_far 壶空先补水再重试
                                 # （当天 ≤2 次）+ **逐格判据**（只看该格是否还在
                                 #   `farm.dryTiles`/`watered`，不许用别格浇水的全局差值顶替）；
                                 # ②resume 空转有界（`_resume_plot`/`review_only_fallback`
                                 #   回来时清任务级 `no_target`，work_spot/resume 计入 burst ≤5）；
                                 # ③"今天没做完"账实相符（阶段级 `assigned_undone` vs 片区级
                                 #   `plot_pending`，诚实上限留 `deferred_tiles` 不计 unmet）；
                                 # ④演进素材质量（复盘调用进 trace `kind="review"`、复盘提示词
                                 #   接地 19 字段、lesson 的 hint 与 evidence 矛盾 ⇒ `hint_dropped`）。
                                 # v0.7.27：经济闭环第一步（卖盈余材料换种子钱，K=10 保底 + 三闸门）
                                 # + 枯死作物不再浇水（Mod 把"干"拆成活苗 `dryCrops`/`dryTiles`
                                 # 与死苗 `dryDeadCrops`；脑侧 `water()` 遇死苗 `skipped`、
                                 # `clear_dead` 提到浇水之前、认输格不再当"有活"）。
                                 # v0.7.26：当季种子（BuySkill 在售清单 + 脑按货架挑） + 枯死作物开路
                                 # + stuck 日有界翻篇 + 豁免上界基数 bound_basis（剔除 encircled）
                                 # （`<journal>-llm.jsonl` + decision 行 llm_trace/llm_trace_hash）。
                                 # v0.7.23：睡觉跨日打通 —— SleepSkill 应答后**同一 tick 关框**
                                 # （原先只 answerDialogue 跑回调、DialogueBox 不收 ⇒ Game1.newDay
                                 # 已置位但提问框挂着、newDaySync 永远等不到保存）；成功判据改成
                                 # "日期前进 且 newDay 归位"；furniture[].bedCells（床的
                                 # TouchAction="Sleep" 触发格，逐帧在 x/x+1 翻转）；门格不再当 A* 目标
                                 # （door_push 候选提到该边最前）。
                                 # v0.7.22：UseToolSkill 对近战武器改走 Farmer.BeginUsingTool()
                                 # （镰刀真挥）+ Done() 增 Grass 判据；sleep 拼不出 Sleep_Yes
                                 # 前缀立刻 sleep_no_question（不再白等 180s）；farm.dryCrops；
                                 # ui.professionsToChoose；模态守卫（职业非空停下等人）；
                                 # brain 侧 busy→环境挡路、stale→无结论。
                                 # v0.7.21：观测里补 player.wateringCan{present,waterLeft,max,
                                 # bottomless,upgradeLevel}（水在 WateringCan 上、不在 inventory）
                                 # 与 location.refillTiles[]（判据=游戏自己的
                                 # CanRefillWateringCanOnTile，扫全图、最多 24）——"连续 3 日浇水"
                                 # 必须能看见"还剩几格水"、"去哪儿补水"；
                                 # v0.7.20：新增 sleep（跨日唯一正路）与 buy（用游戏自己的
                                 # tryToPurchaseItem + addItemToInventoryBool 买种子）；
                                 # v0.7.19：修"播种不扣种子"（placementAction 不扣物品，
                                 # 补调 Farmer.reduceActiveItemByOne；见 manifest 与开发日志条目 024）；
                                 # v0.7.18：先判后动 + tillable[]；
                                 # v0.7.1：interact（调游戏自己的 checkAction）；v0.7.0：quit_game + world/5
                                 # 与“目标=当前所在格直接 ok”。v0.5.0：每帧强制
                                 # pauseWhenOutOfFocus=false（IL 定因：Game1._update
                                 # IL_0444-IL_0480 那道门），health 新增
                                 # game.pauseWhenOutOfFocus / game.oofFixCount 两个证据字段

# 已知基线：环境实测快照 docs/02-环境实测快照.md
BASELINE_GAME_VERSION = "1.6.15"
BASELINE_SMAPI_VERSION = "4.5.2"

# 覆盖 bridge.json 位置的环境变量（测试与多实例调试用）
ENV_BRIDGE_JSON = "AGENTFARM_BRIDGE_JSON"

# 只警告一次的去重集合（同一进程里同一条警告不刷屏）
_warned_once: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key not in _warned_once:
        _warned_once.add(key)
        print(f"[agentfarm] 警告：{message}", file=sys.stderr)


class BridgeError(Exception):
    """桥接层的一切失败。`status` 与协议 §3 的状态码一一对应。"""

    def __init__(
        self,
        reason: str,
        status: str = "error",
        http_status: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.http_status = http_status
        self.payload = payload or {}

    def __str__(self) -> str:  # pragma: no cover - 仅用于打印
        extra = f" (HTTP {self.http_status})" if self.http_status else ""
        return f"[{self.status}]{extra} {self.reason}"


@dataclass(frozen=True)
class BridgeFileAudit:
    """`bridge.json` 的**只读**字段识别审计（真机双向取证用；不改变任何解析语义）。

    `recognized` = `(协议里的字段名, 文件里实际的键名)`，按协议顺序；
    `ignored` = 文件里有、但解析器不认识的键（原样，文件顺序）。
    两者合起来就是文件里的全部键 ⇒ 真机上一次就能看清"pid 到底写在哪个键里"。
    """

    recognized: tuple[tuple[str, str], ...] = ()
    ignored: tuple[str, ...] = ()


@dataclass(frozen=True)
class BridgeInfo:
    """`bridge.json` 的内容：Mod 告诉脑"我在哪个端口、口令是什么"。

    `notes`：读取时的**非致命**说明（字段名拼写与协议不一致、`pid` 读不出来等）。
    它不是错误——文件仍然可用；只是提醒调用方"这一项的标准写法没对上，别拿它当硬判据"。
    `audit`：只读的字段识别清单（见 `BridgeFileAudit`），供真机双向取证。
    """

    schema: str
    port: int
    token: str
    pid: int | None
    mod_version: str
    game_version: str
    smapi_version: str
    started_at: str
    path: Path
    notes: tuple[str, ...] = ()
    audit: BridgeFileAudit = BridgeFileAudit()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def default_bridge_json_path() -> Path:
    """`%APPDATA%\\StardewValley\\AgentFarm\\bridge.json`（协议 §2）。"""
    override = os.environ.get(ENV_BRIDGE_JSON)
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if not appdata:
        # 非 Windows 或环境异常：退回用户目录，便于在别的机器上做纯 mock 测试
        return Path.home() / ".stardew" / "AgentFarm" / "bridge.json"
    return Path(appdata) / "StardewValley" / "AgentFarm" / "bridge.json"


def pid_alive(pid: int | None) -> bool | None:
    """检查进程是否还活着。返回 `None` = **不知道**（`pid` 缺失/为 `None`，或当前平台不支持）。

    ⚠️ **调用方不得把 `None` 当成 `False`**：`None` 只说明"无法判断"，**不说明进程不存在**。
    正确的判据是 `is True` / `is False` 分别处理——`None` 时只能改用别的证据（HTTP 探测、
    进程名轮询）。把 `None` 当"已退出"会让一次正常的运行被误判成陈旧文件（或反过来漏掉强杀）。

    ⚠️ Windows 上**绝不能**用 `os.kill(pid, 0)` 做存在性检查 —— 在 Windows 上
    它不是"发信号 0"，而是会走到 `TerminateProcess`，**真的把目标进程杀掉**。
    这里用 `OpenProcess(SYNCHRONIZE)` + `WaitForSingleObject(0)`：只查询、不触碰。

    【为什么需要它】实测（2026-10-11）游戏正常退出后 `bridge.json` 仍留在磁盘上。
    脑不能假定 Mod 一定守约清理，必须自己判断"这个文件是不是上一局的遗物"。
    """
    if pid is None or os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    SYNCHRONIZE = 0x00100000
    WAIT_TIMEOUT = 0x00000102
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        return False                      # 打不开 = 进程不存在（或权限不足，保守当死）
    try:
        return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


# 表示"文件里没有这个键"（与"键在、值是 null"区分开）
_MISSING = object()

# 容错读取的**非致命**字段（协议里的字段名）。`schema`/`port`/`token` 不在此列：
# 它们是"能不能连上"的硬前提，拼错就该明确失败，而不是被容错掩盖。
TOLERANT_FIELDS = ("pid", "modVersion", "gameVersion", "smapiVersion", "startedAt")


def _norm_field_name(name: str) -> str:
    """字段名归一：小写 + 去掉下划线（`modVersion`/`mod_version`/`ModVersion` → `modversion`）。"""
    return name.lower().replace("_", "")


def _find_key(raw: dict[str, Any], canonical: str) -> str | None:
    """找出 `canonical` 字段在文件里实际的键名；没有则 `None`。

    查找优先级：**精确**（协议写法）> 大小写/下划线变体（`Pid`、`mod_version`、`ModVersion`）。
    ⚠️ 只对 `TOLERANT_FIELDS` 用；`schema`/`port`/`token` 仍走精确键名。
    """
    if canonical in raw:
        return canonical
    target = _norm_field_name(canonical)
    for key in raw:
        if isinstance(key, str) and _norm_field_name(key) == target:
            return key
    return None


def _get_field(raw: dict[str, Any], canonical: str) -> tuple[Any, str | None]:
    """容错取字段值，返回 `(值, 文件里实际的键名)`；文件里没有则 `(_MISSING, None)`。

    为什么要容错：Mod 侧写出的键名是固定的 `pid`/`modVersion`…（`BridgeHost.cs` 里每个属性都有
    显式 `[JsonPropertyName]`），但**旧版 Mod、人工手写的文件、或换了序列化策略的文件**可能写成
    `Pid`/`mod_version`。此时 `raw.get("pid")` 会**静默返回 None**（不报错、不警告），而
    `pid_alive(None)` 只回答"不知道"——上层若把 `None` 当成"进程已死"就会误判。
    """
    key = _find_key(raw, canonical)
    if key is None:
        return _MISSING, None
    return raw[key], key


def _collect_fields(raw: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, str]], list[str]]:
    """读取全部协议字段，返回 `(值表, recognized, notes)`。

    **只读**：不做 schema/port/token 校验、不抛异常、不改任何东西。
    `schema`/`port`/`token` 用**精确键名**（语义与以前逐字一致）；`TOLERANT_FIELDS` 走
    `_find_key` 容错，并把"文件里实际的键名"记进 `recognized`、拼写漂移记进 `notes`。
    """
    values: dict[str, Any] = {}
    recognized: list[tuple[str, str]] = []
    notes: list[str] = []

    def take(canonical: str, *, tolerant: bool) -> None:
        if tolerant:
            value, found = _get_field(raw, canonical)
        else:
            found = canonical if canonical in raw else None
            value = raw[canonical] if found is not None else _MISSING
        if found is not None:
            recognized.append((canonical, found))
            if found != canonical:
                notes.append(
                    f"bridge.json 用 {found!r} 而不是协议里的 {canonical!r}"
                    f"（已按大小写/下划线不敏感读出）"
                )
        values[canonical] = value

    for strict_field in ("schema", "port", "token"):
        take(strict_field, tolerant=False)
    for field in TOLERANT_FIELDS:
        take(field, tolerant=True)
    return values, recognized, notes


def _parse_pid(value: Any) -> int | None:
    """把 `pid` 字段转成正整数；转不了返回 `None`（**不抛异常**）。

    能接受：`24444`、`"24444"`、`" 24444 "`、`24444.0`（JSON 里写成浮点的整数值）。
    不接受：`true`/`false`（bool 是 int 的子类，但它不是 pid）、`"abc"`、`0`、负数、非整数浮点。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not value.is_integer():
            return None
        parsed = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not (text.isdigit() or (text[:1] in "+-" and text[1:].isdigit())):
            return None
        parsed = int(text)
    else:
        return None
    return parsed if parsed > 0 else None


def _read_json_object(path: Path) -> dict[str, Any]:
    """读 `bridge.json` 并确保顶层是对象；失败一律抛**显式**的 `BridgeError`。"""
    if not path.exists():
        raise BridgeError(
            f"找不到 {path}。请确认：① 游戏已通过 SMAPI 启动；② 已加载存档；"
            f"③ Mod AgentFarm.Bridge 已安装并成功加载。",
            status="bridge_file_missing",
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BridgeError(f"{path} 不是合法 JSON：{exc}", status="bridge_file_invalid") from exc
    if not isinstance(raw, dict):
        # 顶层是数组/字符串时，旧写法会在 raw.get 上抛裸 AttributeError（不是 BridgeError）
        raise BridgeError(
            f"{path} 的顶层不是 JSON 对象，实际是 {type(raw).__name__}",
            status="bridge_file_invalid",
        )
    return raw


def inspect_bridge_json(path: Path | None = None) -> dict[str, Any]:
    """**只读取证钩子**：把"原始键名"与"解析结果"一次摆出来（真机双向取证用，task-13 要求）。

    给 machine-runner 的用法：对磁盘上那份 `bridge.json` 调一次，就能同时拿到
    "原始 pid 键 + 值"和"`load_bridge_info().pid`"两行读数，从而区分
    **Mod 写错键名** 与 **脑读错字段**。

    返回机器可读 dict（可直接 `json.dumps`）：`path`、`raw_keys`、`raw_pid_key`、
    `raw_pid_value`、`parsed_pid`、`recognized`、`ignored_keys`、`notes`。

    真机用法（起跑前各跑一次，就是那"两行读数"；`PYTHONPATH` 指向 `brain`）::

        python -c "import json;from agentfarm.bridge import inspect_bridge_json as i;print(json.dumps(i(),ensure_ascii=False))"
        python -c "from agentfarm.bridge import load_bridge_info as l;print(l().pid)"

    **不做 schema/port/token 校验、也不因它们不合法而抛异常**（真机排查要一次看全）；
    只有"文件不存在 / 不是合法 JSON / 顶层不是对象"才抛 `BridgeError`——那正是要报告的事实。
    """
    p = Path(path) if path is not None else default_bridge_json_path()
    raw = _read_json_object(p)
    values, recognized, notes = _collect_fields(raw)
    if values["pid"] is _MISSING or values["pid"] is None:
        notes.append("pid 缺失或为 null：pid_alive() 只会返回 None（不知道），不得当成“进程死了”")
    elif _parse_pid(values["pid"]) is None:
        notes.append(
            f"pid={values['pid']!r} 不是合法进程号：pid_alive() 只会返回 None（不知道），"
            f"不得当成“进程死了”"
        )
    used = {found for _, found in recognized}
    return {
        "path": str(p),
        "raw_keys": list(raw.keys()),
        "raw_pid_key": dict(recognized).get("pid"),
        "raw_pid_value": None if values["pid"] is _MISSING else values["pid"],
        "parsed_pid": _parse_pid(values["pid"]),
        "recognized": [[canonical, found] for canonical, found in recognized],
        "ignored_keys": [key for key in raw if key not in used],
        "notes": notes,
    }


def load_bridge_info(path: Path | None = None) -> BridgeInfo:
    """读取并校验 `bridge.json`（读文件 → `parse_bridge_info`）。

    文件不存在时给出**可操作**的提示（游戏没开？Mod 没装？），而不是一句 FileNotFoundError。
    字段容错口径见 `parse_bridge_info`；只读取证用 `inspect_bridge_json`。
    """
    p = Path(path) if path is not None else default_bridge_json_path()
    return parse_bridge_info(_read_json_object(p), path=p)


def parse_bridge_info(raw: dict[str, Any], *, path: Path | None = None) -> BridgeInfo:
    """从**已经读进来的 dict** 解析并校验 `bridge.json`（`load_bridge_info` 的主体）。

    单独暴露它有两个用途：① 真机排查可一次拿到"原始键名 + 解析结果"（见 `inspect_bridge_json`）；
    ② 单测能直接喂畸形 dict，不必每次落盘。

    字段容错口径（task-13）——**只对非致命字段**：
      * `pid` / `modVersion` / `gameVersion` / `smapiVersion` / `startedAt`
        按**大小写 + 下划线不敏感**读取（`Pid`、`mod_version`、`ModVersion` 都认），
        `pid` 还接受字符串数字（`"24444"`）；读不出来**不抛异常**，`pid` 记 `None`
        并把原因写进 `BridgeInfo.notes`（"存活判定不可用"，调用方不得据此断定进程不存在）。
      * `port` 仍接受字符串数字（`"17890"`），但**缺失/是垃圾**继续抛 `bridge_file_invalid`；
        `token` 缺失继续抛 `bridge_file_invalid`；`schema` 不符继续抛 `schema_mismatch`。
        这三个一个字的校验语义都不许放宽——它们是"能不能连上"的硬前提。
    """
    values, recognized, notes = _collect_fields(raw)

    schema_value = values["schema"]
    schema = "" if schema_value is _MISSING else str(schema_value)
    if schema != SCHEMA_BRIDGE:
        raise BridgeError(
            f"bridge.json 的 schema 是 {schema!r}，期望 {SCHEMA_BRIDGE!r}。"
            f"两侧协议版本不一致，拒绝继续（协议 §8）。",
            status="schema_mismatch",
        )
    if values["port"] is _MISSING or values["token"] is _MISSING:
        # 必须显式判缺失：`str(_MISSING)` 不会抛异常，会静默把哨兵对象当成 token
        missing = "/".join(name for name in ("port", "token") if values[name] is _MISSING)
        raise BridgeError(f"{path or 'bridge.json'} 缺少 port/token 字段：缺 {missing}",
                          status="bridge_file_invalid")
    try:
        port = int(values["port"])
        token = str(values["token"])
    except (TypeError, ValueError) as exc:
        raise BridgeError(f"{path or 'bridge.json'} 缺少 port/token 字段：{exc}",
                          status="bridge_file_invalid") from exc

    raw_pid = values["pid"]
    pid = _parse_pid(raw_pid)
    if pid is None:
        if raw_pid is _MISSING or raw_pid is None:
            notes.append(
                "bridge.json 里没有 pid：pid_alive() 只会返回 None（不知道进程是否存在），"
                "调用方不得据此断定游戏已退出"
            )
        else:
            notes.append(
                f"bridge.json 的 pid={raw_pid!r} 不是合法进程号，已按“未知”处理："
                f"pid_alive() 只会返回 None，调用方不得据此断定游戏已退出"
            )

    def text(field: str) -> str:
        value = values[field]
        return "" if value is _MISSING or value is None else str(value)

    used = {found for _, found in recognized}
    return BridgeInfo(
        schema=schema,
        port=port,
        token=token,
        pid=pid,
        mod_version=text("modVersion"),
        game_version=text("gameVersion"),
        smapi_version=text("smapiVersion"),
        started_at=text("startedAt"),
        path=Path(path) if path is not None else default_bridge_json_path(),
        notes=tuple(notes),
        audit=BridgeFileAudit(
            recognized=tuple(recognized),
            ignored=tuple(key for key in raw if key not in used),
        ),
    )


class BridgeClient:
    """薄 HTTP 客户端。每个方法只做一件事：发请求、解析、把失败变成 BridgeError。"""

    def __init__(self, info: BridgeInfo | None = None, timeout: float = 5.0) -> None:
        self.info = info if info is not None else load_bridge_info()
        self.timeout = timeout

    # ---------- 内部 ----------
    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        auth: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.info.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if auth:
            headers["X-Auth-Token"] = self.info.token

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
                http_status = resp.status
        except urllib.error.HTTPError as exc:
            # 4xx/5xx 也是协议的一部分（401 unauthorized / 404 not_found），要把 body 读出来
            payload = exc.read().decode("utf-8", errors="replace")
            http_status = exc.code
        except urllib.error.URLError as exc:
            raise BridgeError(
                f"连不上 {url}：{exc.reason}。Mod 可能已卸载、端口被占或进程已退出。",
                status="unreachable_bridge",
            ) from exc
        except TimeoutError as exc:
            raise BridgeError(f"请求 {path} 超时（>{timeout or self.timeout}s）", status="timeout") from exc
        except OSError as exc:
            # 实机踩到的坑：游戏进程抖动/退出时，socket 会被**强制重置**，
            # 抛出来的是裸 ConnectionResetError（http.client.RemoteDisconnected 也是它的子类），
            # 不属于 URLError，不捕就会让整个"脑"带 traceback 崩掉。
            raise BridgeError(
                f"与 Mod 的连接中断（{type(exc).__name__}: {exc}）。游戏可能正在退出或已崩溃。",
                status="connection_broken",
            ) from exc
        except http.client.HTTPException as exc:
            # 收到半截响应/非法状态行等：同样属于"对端不可信"，绝不让异常逃逸。
            raise BridgeError(f"与 Mod 的 HTTP 交互异常（{type(exc).__name__}: {exc}）",
                              status="bad_response") from exc

        try:
            result = json.loads(payload) if payload.strip() else {}
        except json.JSONDecodeError as exc:
            raise BridgeError(
                f"{path} 返回的不是 JSON（HTTP {http_status}）：{payload[:200]!r}",
                status="bad_response",
                http_status=http_status,
            ) from exc

        if not isinstance(result, dict):
            raise BridgeError(f"{path} 返回的 JSON 不是对象", status="bad_response", http_status=http_status)

        if not result.get("ok", False):
            raise BridgeError(
                str(result.get("reason") or result.get("status") or "未说明原因"),
                status=str(result.get("status", "error")),
                http_status=http_status,
                payload=result,
            )
        return result

    # ---------- 公开接口（协议 §4/§5/§6） ----------
    def health(self, *, timeout: float | None = None) -> dict[str, Any]:
        """协议 §4。不需要令牌。"""
        return self._request("GET", "/v1/health", auth=False, timeout=timeout)

    def observe(self, detail: str = "summary", *, timeout: float | None = None) -> dict[str, Any]:
        """协议 §5。`detail` 只能是 summary / full。"""
        if detail not in ("summary", "full"):
            raise ValueError(f"detail 只能是 summary 或 full，收到 {detail!r}")
        result = self._request("GET", f"/v1/observe?detail={detail}", timeout=timeout)
        schema = result.get("schema")
        if schema != SCHEMA_WORLD:
            if schema in SCHEMA_WORLD_LEGACY:
                _warn_once(
                    f"world-schema:{schema}",
                    f"Mod 返回旧快照 {schema!r}（期望 {SCHEMA_WORLD!r}）：游戏里装的 Mod 还是升级前的版本"
                    f"（期望 {MOD_VERSION_EXPECTED}），新字段（如 location.doors[] / location.furniture[]）不可用。"
                    f"重启游戏完成升级后本警告消失。",
                )
            else:
                raise BridgeError(
                    f"observe 返回 schema={schema!r}，期望 {SCHEMA_WORLD!r}（协议 §8）",
                    status="schema_mismatch",
                    payload=result,
                )
        return result

    def exec_skill(
        self,
        skill: str,
        args: dict[str, Any] | None = None,
        *,
        timeout_ms: int = 8000,
        based_on_seq: int | None = None,
        http_timeout: float | None = None,
    ) -> dict[str, Any]:
        """协议 §6。

        `http_timeout` 默认比 `timeout_ms` 多留 3 秒，避免"客户端先超时、
        服务端还在跑"造成两边认知不一致（旧协议没有这个区分）。
        """
        body: dict[str, Any] = {"skill": skill, "timeout_ms": int(timeout_ms)}
        if args:
            body["args"] = args
        if based_on_seq is not None:
            body["based_on_seq"] = int(based_on_seq)
        result = self._request(
            "POST",
            "/v1/exec",
            body,
            timeout=http_timeout if http_timeout is not None else (timeout_ms / 1000.0 + 3.0),
        )

        # exec 的 schema 校验采取"**存在才校验**"的宽松口径：
        # 实测 Mod 的部分响应分支（如未实现技能）不带 schema 字段，硬校验会把自己人打自己人
        # （正是旧项目缺陷 D5 的翻版）。字段缺失 = 容忍并继续；字段存在但不符 = 明确报错。
        schema = result.get("schema")
        if schema is not None and schema != SCHEMA_EXEC:
            raise BridgeError(
                f"exec 返回 schema={schema!r}，期望 {SCHEMA_EXEC!r}（协议 §8）",
                status="schema_mismatch",
                payload=result,
            )

        # world_stuck 是 ok=false + status=world_stuck，已在 _request 里转成 BridgeError。
        # 语义提醒：它表示"模态关了但世界没恢复"，脑**必须升级处理（重启游戏）**，
        # 绝不允许当普通失败重试。
        return result

    # 便捷封装：里程碑 A 的技能
    def noop(self) -> dict[str, Any]:
        return self.exec_skill("noop", timeout_ms=1000)

    def dismiss_modal(
        self,
        *,
        answer_index: int | None = None,
        answer_text: str | None = None,
        timeout_ms: int = 5000,
    ) -> dict[str, Any]:
        """关闭当前挡路的模态（dismiss_modal）。

        成功后请**务必检查 `worldResumed`**：它为 False 时说明模态关了但世界没恢复
        （`canMove=false`），此时状态是 `world_stuck`，脑需要重启游戏而不是继续排计划。

        ⚠️ 它**不是**"推进对话"：对 `DialogueBox` 它走 `closeDialogue()`（= `exitActiveMenu()`），
        会**跳过当前句的显示时机**、把事件停在半截（后续 `addCraftingRecipe` 之类仍会执行，
        但对话语义丢了）。事件对话的受控推进见 :meth:`advance_dialogue`（task-228）。

        【task-25 rev4 / 0.7.46】`answer_index` / `answer_text` 走 task-208 的**显式应答**
        通道（`DialogueBox` 提问时按给定选项替游戏调用 `answerDialogue(Response)`）。纪律：
          * `answer_text` 必须**唯一命中**一个选项（大小写不敏感、去空白后**精确**匹配）；
          * 命中 0 项 ⇒ Mod 回 `choice_not_found`；命中多项 ⇒ `choice_ambiguous`；
          * 脑**绝不许**"猜一个看起来像的选项"——不在观测 `dialogueResponses` 里的文本
            一律不发（背包装备固定用 `"Purchase"`，见协议 §8.4）。
        """
        args: dict[str, Any] = {}
        if answer_index is not None:
            args["answerIndex"] = int(answer_index)
        if answer_text is not None:
            args["answerText"] = str(answer_text)
        return self.exec_skill("dismiss_modal", args or None, timeout_ms=timeout_ms)

    def advance_dialogue(
        self,
        *,
        max_steps: int | None = None,
        timeout_ms: int = 60000,
    ) -> dict[str, Any]:
        """把**非提问**的事件对话受控推进（advance_dialogue，task-228）。

        为什么需要：事件脚本的非提问对话会停在第一句等点击 ⇒ `ui.eventUp=true` +
        `worldAdvancing=false`，无人值守时永久挂住（真机事故：Clint 送熔炉配方）。

        原语 = `DialogueBox.receiveLeftClick(0, 0, true)`（IL 实证：玩家真实点击走它，
        右键只是转发，动作键也映射成它）；**不是** `closeDialogue()`（跳句）。
        不会替游戏选选项：遇到提问/职业选择会 fail-closed 返回 `is_question` /
        `professions_pending`，一次都不点。

        `max_steps`：本次最多推进几步（Mod 默认 20、上限 60）。
        `timeout_ms`：默认 60000（每步要等 safetyTimer 750/550ms；事件 `pause` 会以
        3s 间隔重试，最多 3 次都没变化才 `advance_stalled`）。

        回执字段：`stepped`（推进步数）、`stalled`（最后一次点击有没有世界变化）、
        `before`/`after`（`eventUp`/`menuText`/`isQuestion` 快照）。
        判据只看观测差分；`stalled` 连续出现 ⇒ 脑侧停止推进、`event_blocked` 诚实收尾。
        """
        args: dict[str, Any] = {}
        if max_steps is not None:
            args["maxSteps"] = int(max_steps)
        return self.exec_skill("advance_dialogue", args or None, timeout_ms=timeout_ms)

    def move_to(
        self,
        x: int,
        y: int,
        *,
        timeout_ms: int = 8000,
        based_on_seq: int | None = None,
        allow_bed: bool = False,
    ) -> dict[str, Any]:
        """走到指定格（move_to）。

        `allow_bed=False`（默认）时，床格会被 Mod 拒绝——无人值守踩到床会触发
        `Go to sleep for the night?` 睡觉流程，是会改写游戏进程的破坏性副作用。
        只有**明确要复现睡觉弹窗来做 `dismiss_modal` 验证**时才传 `allow_bed=True`；
        它只解禁"床"这一项，其它不可踩家具照样拒绝。

        注意：该参数要求 Mod ≥ 0.5.1（协议 §6 `move_to.args.allow_bed`）。
        **低于 0.5.1 的 Mod 会静默忽略未知参数**——真机实测 v0.5.0 上 `allow_bed=True` 与不带
        该参数的请求返回**逐字相同**的 `precondition_failed: 目标格 (9,9) 有家具（床）`。
        所以"脑发了参数、体不认识"是这里最容易踩的坑：脑不能靠"我发了"就当"它生效了"，
        必须以回执（`reason` 里有没有 `allow_bed=true`）为准。
        """
        args: dict[str, Any] = {"tile": [int(x), int(y)]}
        if allow_bed:
            args["allow_bed"] = True
        return self.exec_skill("move_to", args, timeout_ms=timeout_ms, based_on_seq=based_on_seq)

    def move_to_location(
        self,
        location: str,
        *,
        tile: tuple[int, int] | None = None,
        timeout_ms: int = 60000,
        based_on_seq: int | None = None,
        allow_bed: bool = False,
    ) -> dict[str, Any]:
        """跨地点移动（move_to_location，Mod ≥ 0.6.0）。

        `location` 只用来**在游戏真值里查表**（`Game1.locations[i].Name` 与每条 warp 的
        `TargetName`，大小写不敏感）；路线一律由 Mod 侧按 warp 图 BFS 求出，脑**不需要**
        也不应该自己规划跨地点路线（架构 §5.2.1 禁止硬编码地名/坐标）。

        传送是**游戏自己**触发的：Mod 只把玩家走到 warp 源格，等
        `Game1.currentLocation.Name` 真的变了才算一跳成功。因此：
          * 成功回执带 `path`（地点序列）、`hops[]`（每跳的 from/to/arrivedAt/
            sourceTile/landingTile/usedTile/ms/result）、`reachedLocation`；
          * `hops[].result == "mismatch"` = warp 上写的目标与实际落地地点不一致（脑要审计）；
          * 失败回执**也**带 path/hops，用来判断"走到哪一步断的"。

        失败状态码：`precondition_failed`（地点不存在/坐标为负/目标格有阻挡家具）、
        `unreachable_no_route`（warp 图上无路）、`hop_failed`（走到触发格但没传送）、
        `unreachable`、`blocked`、`timeout`、`ui_modal`、`no_save`。

        【task-43】默认 `timeout_ms=60000`：run4 实证从田里回农舍 A* 真实路径 ≈88 步
        （被草/石/枝/树逼得绕路 3 倍，≈20–30s），30s 会被整体预算卡死。失败回执里会带
        `单跳预算 …ms，剩余 N 步未走完` 与 `warp 源格 (x,y)`，`farmwork.ensure_location`
        据此做**两段式**接近（先 `move_to` 到源格旁可站格，再只重试一次）。
        """
        args: dict[str, Any] = {"location": location}
        if tile is not None:
            args["tile"] = [int(tile[0]), int(tile[1])]
        if allow_bed:
            args["allow_bed"] = True
        return self.exec_skill("move_to_location", args, timeout_ms=timeout_ms, based_on_seq=based_on_seq)

    def load_save(
        self,
        save: str | None = None,
        *,
        force: bool = False,
        timeout_ms: int = 60000,
    ) -> dict[str, Any]:
        """从**标题界面**读档（load_save，Mod ≥ 0.6.0）。

        用途（自主性前提，不是便利功能）：
          * 换 Mod dll 必须重启游戏，重启后游戏停在标题界面；标题界面上唯一的正常入口是
            "点 Continue" —— 那属于**伪造输入**，被硬纪律①禁止；
          * 无人值守长跑必须能从崩溃/重启里自己爬起来。

        实现上调用的是**游戏自己的** `SaveGame.Load(存档名)`（与玩家点 Continue 同一条路），
        不写任何世界状态、不动角色坐标/金钱/时间。成功判据是"世界真的可读了"
        （`Context.IsWorldReady` 且 player/currentLocation 都读得到）。

        `save=None` 时由 Mod 自动挑**最近写过**的存档。
        ⚠️ 已经**在存档里**时默认拒绝（`precondition_failed`）：读档会直接丢掉当天进度
        （游戏只在睡觉时落盘）。确实要丢弃当前进度时传 `force=True`。

        成功回执含 `save`（存档文件夹名）、`reachedLocation`、`tile`。
        """
        args: dict[str, Any] = {}
        if save:
            args["save"] = save
        if force:
            args["force"] = True
        return self.exec_skill("load_save", args, timeout_ms=timeout_ms)

    def interact(self, tile: tuple[int, int] | None = None, *, timeout_ms: int = 5000) -> dict[str, Any]:
        """**用一下面前那一格**（interact，Mod ≥ 0.7.1）。

        实现上是调**游戏自己的动作入口** `GameLocation.checkAction(tile, viewport, player)`
        （api-probe 编译期实证 3 参重载存在）—— 与 `dismiss_modal` 调 `answerDialogue` 而不按确认键
        **同一条纪律**：不合成键鼠事件。

        【为什么进建筑必须用它】真机证据（2026-08-11 晚）：
          * `Farm` / `FarmHouse` 的 `location.doors` **都是空的** ⇒ `isCollidingWithDoors` 无从触发；
          * `GameLocation.checkAction` 的 IL 里遍历 `this.buildings`，调 `getPointForHumanDoor()` /
            `getWarpFromDoor(...)` / **`Building.doAction(Vector2, Farmer)`** ⇒ 进建筑是"动作"路径；
          * `door_push`（把"朝门走一步"喂给寻路器）只能把玩家推到墙前 3 像素，矩形角**永远进不了门格**。

        `tile=None` 时用"玩家当前面朝的那一格"（走到门口朝上时正好是门格）。
        回执里的 `reachedLocation` 是**动作发起时**的地点；门/建筑的传送由游戏自己发起、有淡出期，
        **必须以随后的 observe 为准**。
        """
        args: dict[str, Any] = {}
        if tile is not None:
            args["tile"] = [int(tile[0]), int(tile[1])]
        return self.exec_skill("interact", args, timeout_ms=timeout_ms)

    def talk(
        self,
        npc: str,
        *,
        npc_tile: tuple[int, int] | None = None,
        timeout_ms: int = 15000,
    ) -> dict[str, Any]:
        """和指定 NPC 对话（talk，0.7.46+ 的新原语，协议 §8.4）。

        实现上 Mod 只调**游戏自己的** `NPC.checkAction(Game1.player, Game1.currentLocation)`
        —— 不合成键鼠、不代选选项；问答留给 `dismiss_modal(answer_text=...)`。

        回执（与 `docs/_release-0.7.46.md` §8.4 对齐）：
          * `code=="ok" && applied` ⇒ 必须带 `activeMenu`（`DialogueBox`/`ShopMenu`）或
            `dialogueIsQuestion=true`；否则是**实现缺陷**，脑侧按 `not_supported` fail-closed；
          * `code=="not_adjacent"` ⇒ 带 `npcTile`/`distance`，脑自己 `move_to` 相邻格；
          * `code=="npc_not_found"` ⇒ 带 `available`（当前地点里的 NPC 名单）；
          * `code=="no_action"` / `not_supported` / `talk_error` ⇒ 不认任何经济结果，
            按失败码留痕（当天 ≤2 次，安全降级继续农务）。
        """
        args: dict[str, Any] = {"npc": str(npc)}
        if npc_tile is not None:
            args["npcTile"] = [int(npc_tile[0]), int(npc_tile[1])]
        return self.exec_skill("talk", args, timeout_ms=timeout_ms)

    def use_tool(
        self,
        tile: tuple[int, int] | None = None,
        *,
        tool: str | None = None,
        timeout_ms: int = 12000,
    ) -> dict[str, Any]:
        """**用工具对某一格动手**（use_tool，Mod ≥ 0.7.6）：砍树枝 / 敲石头 / 割草 / 锄地 / 浇水。

        `tool`：`axe` / `pickaxe` / `hoe` / `can` / `scythe` / `auto`（省略＝`auto`）。
        `auto` 由 Mod 按目标格上的东西挑（twig→axe、可破石头→pickaxe、weed|grass→scythe、
        空耕地→hoe、有作物的耕地→can），并在回执的 `reason` 里**报出真实用的那件物品名** ——
        所以脑必须读回执核对"它到底拿了什么工具"，不能假设。

        实现**故意不走** `Game1.pressUseToolButton()`：它对近战武器（镰刀）有一道"必须真有鼠标/
        手柄输入边沿"的门闸（`Game1.didPlayerJustLeftClick`，只认本帧刚按下的输入），桥驱动时恒为假
        ⇒ **镰刀一刀都挥不出去**（真机 run1：非 grass 7/7 全成功、grass 5/5 全失败）。
        Mod ≥ 0.7.22 改为照抄它在门闸**之后**的那段（`GetToolLocation` → `FacingDirection` →
        `lastClick` → `Farmer.BeginUsingTool()`），只把"人手鼠标的像素位置"换成**目标格中心**；
        拿不到 player/工具或抛异常时仍回退 `pressUseToolButton()`。选工具仍用 `CurrentToolIndex`。
        `Farmer.UseTool(...)` / `completeToolUse()` 在 1.6.15 **不存在**。
        纪律同 `interact`/`dismiss_modal`：不合成键鼠事件。

        ⚠️ **验收必须用 observe 的 `location.tiles[]` 差分**：回执只是声明，格子上东西没了才是证据。
        失败状态码：`precondition_failed`（没这类工具/有模态/这一格锄不了）、`tool_ineffective`
        （挥满 6 次目标格仍在，回执里带"起手=是/否"与"现在还是 <kind>"）、`timeout`、`no_save`、
        `world_fading`（屏幕渐黑/过场，Mod 侧 `fadeToBlack`/`nonWarpFade` —— **可重试**，脑记 failed
        但**不封格**，见 `farmwork.ENV_BLOCK_STATUSES`；0.7.22 之前不会出现这个码）。
        """
        args: dict[str, Any] = {}
        if tile is not None:
            args["tile"] = [int(tile[0]), int(tile[1])]
        if tool:
            args["tool"] = tool
        return self.exec_skill("use_tool", args, timeout_ms=timeout_ms)

    def select_item(self, item: str, *, timeout_ms: int = 5000) -> dict[str, Any]:
        """选中背包里的某件物品（`select_item`，Mod ≥ 0.7.9）。

        `item` 可以是 `ItemId`（例 `472`）、`QualifiedItemId`（`(O)472`）或物品名，大小写不敏感。
        实现是设 `Game1.player.CurrentToolIndex`（等价于玩家滚快捷栏），**并复核** `CurrentItem`
        真的是它 —— 不符时报 `select_failed`，绝不"我设了就当选中了"。
        回执 reason 给出槽位与物品名；拿不到时是 `precondition_failed` + 完整背包清单。
        """
        return self.exec_skill("select_item", {"item": item}, timeout_ms=timeout_ms)

    def plant(self, seed: str, tile: tuple[int, int], *, timeout_ms: int = 15000) -> dict[str, Any]:
        """把种子种进**已经锄好的耕地**（`plant`，Mod ≥ 0.7.9）。

        `seed`：种子 `ItemId`（例 `472` = 防风草种子）；`tile`：目标耕地格。
        前置条件是"该格是 `HoeDirt` 且没有作物"（不满足直接 `precondition_failed`，不瞎试）。
        实现走**游戏自己的使用键入口** `Game1.pressUseToolButton()`（最多 3 次）；
        探针证伪了 `Object.performUseAction` 的"对指定格使用"重载，也刻意不调 `HoeDirt.plant`
        （那是直接写世界状态）。
        ⚠️ **验收必须用 `tiles[]` 差分**：该格要真的出现 `crop`（回执只是声明）。
        """
        return self.exec_skill(
            "plant",
            {"seed": seed, "tile": [int(tile[0]), int(tile[1])]},
            timeout_ms=timeout_ms,
        )

    def sleep(self, *, timeout_ms: int = 180000) -> dict[str, Any]:
        """**睡到第二天**（`sleep`，Mod ≥ 0.7.20）—— 跨日的唯一正路（长跑循环的日终动作）。

        实现走**游戏自己让玩家点"是"的那条路**：`GameLocation.answerDialogueAction("Sleep_Yes", null)`
        → `startSleep()` → `doSleep()` → `Game1.NewDay(0f)`（IL 证据见 `docs\\_il-plant-consume.md`
        同级的 sleep 取证与 `logs\\il-sleep-entry-u8.txt`）。不是合成键鼠、也不是自己写 `Date`。

        ⚠️ **验收必须用 observe 差分**：`clock` 的 `(year, season, day)` 必须真的变大。
        回执 reason 里的"第 N 天"是 `Game1.Date.TotalDays`（春 1 日起 0 基），
        与 `clock.day`（月内日）**差 1**，别拿回执当日期证据。
        睡眠本身是异步协程：Mod 侧跨 tick 等到跨日完成才回执（实测 1.7s），所以 HTTP 要给足时间。
        """
        return self.exec_skill("sleep", timeout_ms=timeout_ms, http_timeout=timeout_ms / 1000.0 + 12.0)

    def buy(
        self,
        item: str,
        count: int = 1,
        *,
        shop: str = "SeedShop",
        timeout_ms: int = 25000,
    ) -> dict[str, Any]:
        """**买种子**（`buy`，Mod ≥ 0.7.20）。

        `item`：`ItemId`（`472`）/ `QualifiedItemId`（`(O)472`）/ 物品名，大小写不敏感；
        `count`：**想买几个**（请求量，不是承诺量）—— Mod 会按"钱够几个 / 库存 / 堆叠上限"夹小，
        最终由游戏自己的 `ShopMenu.tryToPurchaseItem(item, null, count, 0, 0)` 裁决；
        `shop`：`Data/Shops` 里的店铺 id（默认 `SeedShop` = 种子店）。

        ⚠️ 纪律同 `plant`：**回执只是声明**。验收要用 observe 差分看两件事——
        `player.money` 少了多少、`player.inventory[]` 里这件多了几个；
        回执里的"游戏返回值"**不是成败**（IL 证明它只表示"这行该撤了"）。
        失败状态码：`item_not_sold`（附货架清单）/ `cannot_afford` / `no_inventory_space` /
        `shop_unavailable` / `shop_timeout` / `purchase_no_effect` / `purchase_partial`。
        """
        return self.exec_skill(
            "buy",
            {"item": item, "count": int(count), "shop": shop},
            timeout_ms=timeout_ms,
        )

    def sell(
        self,
        slot: int,
        *,
        whitelist: list[str] | tuple[str, ...] | None = None,
        timeout_ms: int = 8000,
    ) -> dict[str, Any]:
        """**把背包某一格放进出货箱**（`sell`，Mod ≥ 0.7.24，task-42）。

        `slot`：背包槽位下标（**0 起**）—— 必须给槽位而不是物品名，因为游戏自己的
        `Farmer.removeItemFromInventory` 用**引用相等**找物品（`Items.IndexOf(which)`），
        只有槽位能无歧义指认"背包里那一件"（传副本会变成"原物不动、副本进箱"，次日多拿一份钱）。
        `whitelist`：**允许列表**（qualifiedId，如 `(O)24`）。**空 = 一件都不卖**：
        脑侧只把当天 `harvest()` 亲眼收获进背包的 qualifiedId 放进来，绝不做"除工具以外都能卖"的黑名单。

        ⚠️ **钱当天不会变**：`Farm.shipItem` 只把物品搬进箱子，钱由**下一次 `NewDay`** 结算
        （`Game1._newDayAfterFade`：`player.Money = player.Money + total`）。
        Mod 的判据是"那一格真的空了"，不是钱变了 —— **回执只是声明**，
        验收要用 observe 差分看 `shippingBin.count` / `shippingBin.items[]`（结算后再看 `player.money`）。
        失败状态码：`bad_args` / `empty_slot` / `not_whitelisted` / `not_sellable` / `quest_item` /
        `big_craftable` / `empty_stack` / `sell_no_effect` / `error`。
        """
        args: dict[str, Any] = {"slot": int(slot)}
        if whitelist:
            args["sellWhitelist"] = [str(x) for x in whitelist]
        return self.exec_skill("sell", args, timeout_ms=timeout_ms)

    def upgrade_tool(self, tool: str, *, timeout_ms: int = 60000) -> dict[str, Any]:
        """**在铁匠铺升级店买下某件工具的下一级**（`upgrade_tool`，Mod ≥ 0.7.38，task-205）。

        `tool`：工具种类 —— `axe` / `pickaxe` / `hoe` / `can` / `pan`（镰刀不能升级：游戏的
        `Tool.actionWhenPurchased` 只认这五类，见 `docs\\_il-tool-upgrade.md` §2.2）。

        Mod 侧的链路（全部是游戏自己的函数，`Utility.TryOpenShopMenu("ClintUpgrade","Clint",true)`
        → 等 `ShopMenu` → 在菜单实例的 `itemPriceAndStock` 里按 kind + tier==当前+1 **唯一**选条目
        → 自检钱/锭/`readOnly` → 反射 `tryToPurchaseItem(item, null, 1, 0, 0)`）。
        **买前必须由脑保证"没有在途升级"**（`toolBeingUpgraded == null`）：游戏的
        `actionWhenPurchased` 见"已在升级"直接返回 false **且不回滚** ⇒ 钱和 5 条锭当场白扣。

        ⚠️ **等级在买下时就换**：`player.toolBeingUpgraded` = 升级后的副本、`daysLeftForToolUpgrade = 2`、
        旧工具离包。取回是**另一件事**（`pickup_tool`）。所以升级期间 hoe/can 相关阶段必须暂停
        （脑侧 `farmwork.tool_being_upgraded()` / `tool_upgrade_days_left()`）。

        **判据是观测差分，回执只是声明**：`player.money` 少了多少、锭少了几个、
        `player.toolBeingUpgraded` 是否出现、`player.tools[].upgradeLevel` 是否变化。
        失败状态码：`already_upgrading` / `still_working` / `read_only` / `no_money` /
        `no_trade_item` / `tool_not_offered`（附在售表 `offers`）/ `shop_unavailable` /
        `purchase_no_effect` / `tool_missing` / `bad_args`。
        """
        return self.exec_skill(
            "upgrade_tool",
            {"tool": str(tool)},
            timeout_ms=timeout_ms,
            http_timeout=timeout_ms / 1000.0 + 12.0,
        )

    def pickup_tool(self, *, timeout_ms: int = 30000) -> dict[str, Any]:
        """**取回升级完成的工具**（`pickup_tool`，Mod ≥ 0.7.38，task-205）。

        前置（Mod 侧 fail-closed，脑侧也要先判）：
          * `player.toolBeingUpgraded != null`（没有在途 ⇒ `nothing_to_pickup`）；
          * `player.daysLeftForToolUpgrade <= 0`（还在做 ⇒ `still_working`）；
          * **背包 ≥1 空格**（`freeSpotsInInventory() <= 0` ⇒ 只会听到 Clint 的
            `Clint_NoInventorySpace`，工具拿不回来 ⇒ `no_slot`；不扣钱，但白跑）；
          * 人在 `Blacksmith` 店里（`GameLocation.blacksmith(...)` 只认当前地点的 Clint）。

        实现 = 调游戏自己的 `GameLocation.blacksmith(...)` 的 pickup 分支（不是对话，
        也不是 `answerDialogueAction`）。**判据是观测差分**：`toolBeingUpgraded` 清空 +
        背包里同种工具 +1（`inventoryAdded`）。
        """
        return self.exec_skill("pickup_tool", timeout_ms=timeout_ms)

    def debug_dump(
        self,
        table: str,
        *,
        key: str | None = None,
        limit: int | None = None,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        """**只读内省游戏自己加载的数据表**（`debug_dump`，Mod ≥ 0.7.39，task-213）。

        `table`：`crafting_recipes` / `cooking_recipes` / `trigger_actions` / `mail` /
        `machines` / `objects` / `big_craftables`（也接受别名与资产路径写法，
        归一在 Mod 侧 `DumpRules.NormalizeTable`；不认识的表 ⇒ `status="table_unknown"`）。
        `key`：可选的**键过滤** —— 给了它 ⇒ 只回 `matched`（`[key, value]` 对，精确优先、
        否则子串，`matchMode` 标注），`entries` 为空；不给 ⇒ 回前 `limit` 条 `entries`。
        `limit`：默认 200、上限 2000（Mod 侧钳制，**不许无界返回整张表**）。

        回执形状：`{ok, status, skill, table, count, truncated, entries, matched,
        matchMode, matchedCount, matchedTruncated, reason}` —— `entries`/`matched` 都是
        `[[key, valueString], ...]`，value 是 Mod 反射渲染的一行字符串（复杂对象带类型名与字段）。

        【为什么存在】Furnace 配方缺失卡住机器链，而 `Data/CraftingRecipes` 在打包 xnb 里
        仓库读不到 ⇒ 只能真机运行时内省（`docs\\_il-furnace-recipe.md`）。**只读**，不改世界。
        失败状态码：`table_unknown` / `load_failed`（异常原文在 reason）/ `error`。
        """
        args: dict[str, Any] = {"table": str(table)}
        if key is not None:
            args["key"] = str(key)
        if limit is not None:
            args["limit"] = int(limit)
        return self.exec_skill("debug_dump", args, timeout_ms=timeout_ms)

    def add_missed_recipes(self, *, timeout_ms: int = 30000) -> dict[str, Any]:
        """**调一次游戏自己的补发入口**（`add_missed_recipes`，Mod ≥ 0.7.39，task-213）。

        内部 = 反射调 `Farmer.AddMissedMailAndRecipes()`，**只调一次**（绝不循环）。
        回执给**前后差分**：`craftingRecipesAdded` / `cookingRecipesAdded` / `mailAdded`
        （排序后的新增键）+ `beforeCounts` / `afterCounts`（键：`crafting_recipes` /
        `cooking_recipes` / `mail`）。

        ⚠️ **它会写玩家字典**（这是游戏自己的补发逻辑）。所以：
          * 只在**真机取证/修复**时调用，不进常规日循环；
          * 空数组 = 调过了但一条都没加（**有效信息**，不是失败）；
          * 方法不存在 ⇒ `status="not_available"`（不猜替代、不自己写表）；
          * 抛异常 ⇒ `status="error"`，reason 注明"**可能已写了一半**"。
        """
        return self.exec_skill("add_missed_recipes", timeout_ms=timeout_ms)

    def quit_game(self, *, timeout_ms: int = 3000) -> dict[str, Any]:
        """让**游戏自己退出**（quit_game，Mod ≥ 0.7.0）。

        用游戏自己的退出标志 `Game1.quit`（api-probe 编译期实证可写）—— 等价于玩家点退出，
        既不伪造键鼠、也不写世界状态，更不是 `Stop-Process` 强杀。

        【为什么需要它】换 Mod dll 必须重启游戏，而重启后停在标题界面。
        "启动 + 自己读档" 已经自主（`load_save`），这一步把另一半补上：
        **发现问题需要关游戏时，脑自己把它关掉**（详见 `tools\\deploy-mod.py`）。

        ⚠️ **回执可能收不到**：置位后游戏会在随后的帧里退出，HTTP 连接可能被重置。
        因此本方法把 `connection_broken` / `bad_response` / `unreachable_bridge` / `timeout`
        一律折成 `{"status": "assumed_quitting"}` —— 那是**预期行为**，不是故障。
        调用方必须再以**进程是否真的消失**为准（`pid_alive(bridge_info.pid)` 或进程名轮询）。
        """
        try:
            return self.exec_skill("quit_game", timeout_ms=timeout_ms, http_timeout=6.0)
        except BridgeError as exc:
            if exc.status in ("connection_broken", "bad_response", "unreachable_bridge", "timeout"):
                return {
                    "ok": True,
                    "status": "assumed_quitting",
                    "reason": f"请求中断（{exc.status}）：游戏很可能已经在退出（以进程是否消失为准）",
                }
            raise
