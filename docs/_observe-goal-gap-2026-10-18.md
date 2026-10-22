# product-observer 缺口清单（目标 vs 现状）

日期：2026-10-18  
角色：product-observer（旁观者，仅写 `docs/_observe-*.md`、`scratch/`，只读生产代码与账本）

> 本文是**可执行缺口清单**。每条均给出：现有证据（文件:行号 或 账本字段）、为什么是缺口、建议卡面（谁写什么）、可验证判据（独立观测差分）、依赖与风险。缺失一律写【缺失】/【无法判定】，不允许猜。
>
> 路径约定：Mod 源文件（`ClumpMeta.cs` / `WorldSnapshot.cs` / `Contracts.cs` / `UseToolSkill.cs` / `FarmScan.cs`）真实路径均为 `mod/AgentFarm.Bridge/<文件名>`；`fields.py` / `farmwork.py` / `planner.py` / `longrun.py` 均在 `brain/agentfarm/` 下；账本在 `logs/`。

**背景事实（Lead 2026-10-18 同步，供本审计引用）**：0.7.48 已冻结 = 提交 `e2b69d9`（前置代码 `d9f7032`）；本批**只补** `slot_relief` 的 `clear_gate` 分支 `reached=False`（只读字段奇偶，非行为变更），dll 与 0.7.47 **逐字节相同**（293888B，C9B3BD6C…）。**A9/B9 尚未起跑**（等 T5 放行 + T6 analyzer 收口）。⇒ 本文所有"路径缺失/口径缺失"结论针对的仍是**冻结前**的 `brain/agentfarm/*`（0.7.47 逻辑），A9/B9 尚未产生新证据。

## 0. 总结（先看这三点最关键）

- **A. 设计口径缺陷：ZONE_BLOCKER 仅覆盖 `weed/stone/twig/tree/bush`，排除 ResourceClump（`stump/log/boulder/rockPile/greenRain/clump`）**  
  证据：`brain/agentfarm/fields.py:54 BLOCKER_KINDS = frozenset({"weed","stone","twig","tree","bush"})`；`brain/agentfarm/fields.py:315`、`brain/agentfarm/fields.py:481` 只按此集合统计 `blockers`；`brain/agentfarm/farmwork.py:163 CLUMP_KINDS = ("clump","stump","log","boulder","rockPile","greenRain")`；Mod `mod/AgentFarm.Bridge/ClumpMeta.cs:14-16,38` 明确 `clumpKind = stump/log/boulder/...`（600=stump/axe≥1、602=log/axe≥2、672=boulder/pickaxe≥2）；`mod/AgentFarm.Bridge/WorldSnapshot.cs:460 t.ClumpKind = ClumpMeta.KindOf(index)`，`:473 ToolOk = ToolMeetsTarget(...)`。
- **B. 判据不存在：缺少「指定作业区（named zone/plot）被清空」的**zone-level **归零判定及「连续2天复核保持清空」的留存/对比工具**  
  证据：仓库中未检出 `zone_cleared|cleared_zone|zone_clear|保持清空|连续.*天` 相关实现（`brain/agentfarm/*.py`, `tools/*.py` grep 结果见上文）；现有判定基于 per-task `leftover`（`longrun.py:4954-5015,8768,8809,10620`）和 `no_unmet_stages`（`longrun.py:745,10524,10328`），**没有**按具名田区（`field_nw/ne/sw/se`）统计 blockers 归零并跨日保持清空的差分判据。
- **C. 经济闭环（种子 vs 工具升级）未纳入自动化任务**  
  证据：`brain/agentfarm/planner.py:101-114 TASK_KINDS` 仅12类，不含 `buy`、`sell`、`upgrade`、`mine`；`logs/longrun-runA8-0743.jsonl`：`tool_upgrade_skipped`（money 2767）、`no_seed_for_sale`、`seed_gate` 均存在但**无执行器调用器**将买种/铁匠铺升级转化为实际 `shop`/`tryToPurchaseItem` 调用路径（相关 caller 未在 grep 范围检出）；`docs/_upgrade-protocol.md` 定义了铜斧升级全链（§0-§9），但实现落地状态【无法判定】（未见 buy-ore/craft/smelt/upgrade 调用点）。

## 1. 指定作业区清空（goal1，首要）

| 缺口 | 现有证据（文件:行号/账本字段） | 为什么是缺口 | 建议卡面（谁写什么） | 可验证判据（独立观测差分） | 依赖与风险 |
|---|---|---|---|---|---|
| 1.1 **zone blockers 定义遗漏 ResourceClump** | `fields.py:54 BLOCKER_KINDS`；`farmwork.py:163 CLUMP_KINDS`；`ClumpMeta.cs:14-16,38,49-101`（stump/log/boulder）；`WorldSnapshot.cs:460`；`UseToolSkill.cs:477`。 | 用户要求“该作业区内杂草/石头/枝/树/树桩/圆木/巨石全部清掉”。但 `Zone.blockers` 仅按 `{weed,stone,twig,tree,bush}` 统计（`fields.py:315,481`），**完全不统计 stump/log/boulder/rockPile/greenRain**。因此：①LLM 看见的 `zone_brief_lines` 待清理计数（`fields.py:336-340`）低估/漏报；②若作业区内仅剩 树桩/圆木/巨石，按现行 blocker 定义会被误判为“待清理 0”。 | **dev-coder（生产代码）**：将 CLUMP_KINDS 中需清理的项纳入 zone blocker 定义（建议新增 `ZONE_BLOCKER_KINDS = BLOCKER_KINDS ∪ {"stump","log","boulder","rockPile","greenRain"}`）或至少覆盖 `stump/log/boulder`，同步更新 `fields.py:_spellings?` 无需但需更新注释与统计。**log-analyst/deputy-lead**：新增统计口径对比（新旧 blockers 差异）。 | 独立观测：用 `observe?detail=full` 的 `tiles[].kind` 对指定 `field_nw/ne/sw/se`（或 LLM 选定 zone）逐格分类，**按新口径**统计 `blockers_zone`。判定：作业区内 `blockers_zone == 0` 且该区 `tiles[]` 中不存在 `stump/log/boulder/rockPile/greenRain`。对比：新旧 `blockers_zone` 差值=真实 clump 数。 | 影响 LLM 简报（zone_brief_lines）与 `plot_in_zone` 的 blocker 列表；需与 farmwork/longrun 的 CLUMP_KINDS 一致；**不能**把“暂时 toolOk==false 的 clump”（需≥1级斧/≥2级镐等）强行计入“必须今天清空”而无能效判据。需先核对 `ClumpMeta.ToolMeetsTarget` 与 `toolOk`（`WorldSnapshot.cs:473, ClumpMeta.cs:80-150`）。 |
| 1.2 **缺少「指定作业区清空」归零判据（zone-level）** | `fields.py: zones_from_observe/plot_in_zone`（具名区概念存在）；`longrun.py:8768 stage_no_target`、`longrun.py:8809 stage_exhausted`、`longrun.py:4954-5015 _leftover`、`longrun.py:10524 no_unmet_stages`。 | 现有“清空”是**任务级 leftover**（clear_area 整体窗口）而非**作业区级 blockers 归零**。树的 leftover 包含全窗口树（`longrun.py:4994-4996`：tree_ok 时 `out += tmap trees`）——这与“指定作业区清空”不对等。目标要求“指定田区/作业区清空”且有**独立观测差分**验收。 | **dev-coder**：新增 `zone_blockers_total(zone, obs)` 基于（1.1修订后的）ZONE_BLOCKER_KINDS，且**只统计该 zone 边界内**的 tile.kind。新增 `day_end.zone_clear[zone] = (blockers_total==0)` 字段并入日终 journal（只写观测事实）。 | 独立观测差分：`observe?detail=full` 前/后两次（或跨日退前退后存档比对）统计指定 zone 内各类 blocker（含clump）计数。**判定**：`zone.blockers_total == 0`。不允许用 `_leftover("clear_area")` 代替 zone-level 计数。 | 树目标在窗口全量（budget）与“作业区清空”存在语义冲突。建议**先限定“指定作业区清空”判定范围=该作业区（plot）内非树障碍 + 该作业区内 clump**，树的清理按预算单列（不强制要求“指定作业区内树全部砍光”），否则极易与树预算（`_tree_budget_room/_tree_budget_left`）冲突。需在卡面明确范围。 |
| 1.3 **缺少「连续2天复核保持清空」留存与对比** | 全仓 grep 未见 `zone_cleared` 跨日留存。`longrun.py` 日终结构有 `day_end.plots[]`（`longrun.py: approx plots filled`）但无“zone 清空状态”历史。 | 目标要求“连续 2 天复核保持清空”（外部世界差分：该区 blockers 归零，`observe?detail=full` 计数）。现有无跨日“保持清空”校验工具，也无“昨日清空→今日仍清空”的强制留存。 | **dev-coder**：新增 `state.zones_cleared_last[zone] = bool`（仅当昨日该区被判定 zone_clear=True 时保留）。新增 `tools/verify-zone-retention.py`（或整合进 `verify-run3.py`）：读取连续≥2日的 `observe?detail=full`（或 journal 日终 zone_clear）对比指定 zone 的 blocker 计数，要求两天**都**为 0 且 tiles 未回归阻塞类 kind。**machine-runner/observer**配合：产出跨日观测快照。 | 独立观测差分（**两侧工具同向**）：Day N 退前观测 S_N，Day N+1 起前观测 S_{N+1}，逐格比对指定 zone 内 blocker 集合（含clump）。判定：S_N.zone_blockers==0 且 S_{N+1}.zone_blockers==0。**绝不**用 journal 自述替代两次独立 `observe?detail=full`。 | 跨日落盘六串配对是既有纪律（A9/B9 条件）；需与“≥2份独立观测”口径（docs/_release-0.7.47.md §4）对齐。风险：tilesTruncated（`fields.py:28-30,407-413`）会导致 zone 统计不完整——验收必须检测 `tilesTruncated` 并标注【无法判定】而非 PASS。 |

## 2. 余力多清（goal1）

| 缺口 | 现有证据（文件:行号/账本字段） | 为什么是缺口 | 建议卡面（谁写什么） | 可验证判据（独立观测差分） | 依赖与风险 |
|---|---|---|---|---|---|
| 2.1 **仅树有“余力多清”预算，其余清障无“核心完成后再清”策略** | `longrun.py:3429-3488 _stamina_budget`（water_reserve=live_crops×水+路径）；`longrun.py:3574-3600 _budget_defer_reason`（清/till/plant 有水债时优先浇水或停手）；`longrun.py:3715-3771 _tree_budget_left/_tree_budget_room`（discretionary = stamina−reserve，预算砍树数≤20）；`deferred_by_budget` 事件（A8 样例：砍树预算驱动）。 | 目标：“当天核心任务（浇水/收获/播种/清障/经济）完成后若还有体力剩余，就再清理一些（额外清理计入总量；但绝不为此漏浇，也不许透支次日浇水所需体力）”。现有：①**只有树**受“可支配体力”预算约束（tree_budget）；②非树清障（杂草/石头/枝/clump）在 stage 内按 `per_stage_tiles` 执行（`_stage_tiles:4766-4830`），**没有“核心全做完→进入 surplus 清障”标记与循环**。换言之：不是“核心做完再清”，而是“按阶段顺序、满足 gate 时执行”。 | **dev-coder**：新增 `surplus_mode`（bool）——当 `water_area/harvest/clear_dead/till_area/plant_area` 均无 `_leftover` 且 `assigned_unmet==0`（或按既有 `no_unmet_stages` 语义）时进入 surplus。surplus 清障**只针对指定作业区内**的 `ACTIONABLE_KINDS ∪ CLUMP_KINDS`（1.1后口径），且**继续强制** `water_reserve` 守护（stam > reserve 或无水债）。计入 `day_end.extra_cleared`（格数）并 journal。 | 独立观测差分：对比“核心任务结束时刻”（最后一项核心任务完成后）与日终的指定作业区 tile.kind 变化：新增清除的 blocker/clump 数 = `extra_cleared`。且日终 `stamina_budget.stamina >= water_reserve - ε`（或无 dry>0 且未透支水预备）。**不允许** surplus 导致今日浇水未完成（`crops_watered` 必须维持真值）。 | 与树预算不冲突：surplus 清障**不**改写 `_tree_budget_*`（树仍按树预算）。需与满包门槛（`CLEAR_LOOT_LOSS_MAX_STEPS`, `slot_relief`）协同（`longrun.py:4760-4780`）。风险：过早进入 surplus 会“抢”本该用于浇水的体力？现有水预备已强制（reserve）；但若进入时机错误，仍需测试。 |
| 2.2 **“不许透支次日浇水所需体力”守护仅部分覆盖** | `_stamina_budget` 用**今日** live_crops 计算 reserve；`capacity = (max_stamina − reserve − STAMINA_COST_TILL)/(SOW+WATER)` 限制今日播种量（`_stage_tiles:4847-4860`）；`plant_area` 若 dry>0 延后（`_budget_defer_reason:3584-3588`）；树预算用 discretionary = stam−reserve（`_tree_budget_room:3770`）。 | “次日浇水所需体力”在**完全休息（full restore）**的 Stardew 下，多数场景由“今日水债清零”（crops_watered）与“播种不超 capacity”间接保障。但用户原话明确列入目标。现有守护**未显式验证“次日最坏需水”**（如次日新出苗？或极端 dryCrops 增长）。此外 surplus 清障（2.1）若加入，必须**强制守护**：进入/执行 surplus 时需 `stam > reserve + 成本预估`，且不改写 reserve 计算。 | **dev-coder**：surplus 执行前强制 `check: discretionary_after >= cost_est`（按单格清障预估体力，保守值）。journal `surplus_check`（通过/拒绝+理由）。**log-analyst**：复核 A8/B9 日终 `stamina_budget` 与 `crops_watered` 一致性。 | 独立观测：日终存档比对（退前退后六串）确认 outdoor crops 均已浇水（`crops_watered` 真且 `farm.dryCrops==0` 或符合既有口径）。surplus 执行期间无“为清障放弃浇水”的证据（浇水队列未中断）。 | 现有 `capacity` 已避免“种太多明天浇不完”。树预算已用 reserve。新增 surplus 必须**不削弱**既有守护。保守预估（成本高估）以免假阳性“透支”。 |

## 3. 经济双头（种子 vs 工具升级）+ 铜斧升级链（goal1）

| 缺口 | 现有证据（文件:行号/账本字段） | 为什么是缺口 | 建议卡面（谁写什么） | 可验证判据（独立观测差分） | 依赖与风险 |
|---|---|---|---|---|---|
| 3.1 **买种 caller 缺失（仅 gate 存在）** | `logs/longrun-runA8-0743.jsonl`: `seed_gate`, `no_seed_for_sale`, `seed_unavailable_today`；`brain/agentfarm/planner.py:101-114` 无 `buy`；grep 未见 `buySeed|Pierre|tryToBuy` 等买种调用。 | `seed_gate` 只做“能不能种”的门槛与日志（`seed_gate` 事件 money=2767），却**从未**真正发起买种。导致“经济再投资（买种子）”从未发生——与 A8 12天经济零变化（money 2767g 不变）相符。 | **dev-coder**：新增 `KIND_BUY_SEED`（或扩展现有 kind）并实现 `buy_seed` 执行器：优先**白名单**（当前季节可种且在清单内）→ 检查钱→调用游戏入口（ShopMenu/Mod 暴露的购买接口）→ 观测差分校验（money−price、inventoryCount 增量）。遵守“绝不自己写金钱”（AGENTS.md §5）。 | 独立观测差分：buy 前后 `observe?detail=full`（或存档六串）对比 `player.Money`（经游戏入口变动）、`player.Items` 种子叠加。要求 money 变动 = −price（精确到游戏货币口径），且未改动工具/武器/建材/锭类。白名单+建造预留+每 qid 保留下限（AGENTS.md §5）。 | 冬季多半“no_seed_for_sale”（A8 样例）——需按季节性处理。买种要考虑背包空位（player_free_slots）避免“no_inventory_space”。Pierre 对话/菜单可能跨天；需 fail-closed（未观测到变动→不记账）。 |
| 3.2 **工具升级（铁匠铺铜斧）caller 缺失** | `docs/_upgrade-protocol.md:§0-§9` 完整铜斧升级链（预算6275g：45铜矿×75+6煤×150+2000g升级）；`logs/... tool_upgrade_skipped {which:null,money:2767,...}`；`brain/agentfarm/planner.py` 无 `upgrade` kind；grep 未见 Clint/Blacksmith/upgrade 相关调用器。 | 目标“钱在‘种子’与‘工具升级’之间取得平衡，两头都要推进”。现有仅日志跳过，**从未**执行真实升级。且 winter 结构性买矿【无法判定】（Clint 是否卖 ore、脑内无矿洞腿）——但铜斧升级链本身的**执行路径**（买材/熔炼/升级菜单）在代码中【缺失】。 | **dev-coder**：新增 `KIND_UPGRADE_TOOL`（首版聚焦铜斧 Axe）。实现：①预算校验（money≥6275，≥2空位，toolBeingUpgraded==null，daysLeft==0，升级前 axe.level==0）；②按协议顺序买材（O)378×45、(O)382×6）→若需熔炼用 `Furnace` 路径（或按协议§5 smelt）→`Utility.TryOpenShopMenu("ClintUpgrade","Clint",true)` 并通过 `ShopMenu.tryToPurchaseItem` 完成升级；③升级后校验 `toolBeingUpgraded==(T)Axe, daysLeft==2`。**绝不**直接改 money/tool level。 | 独立观测差分（升级当天+升级后）：升级前后 `observe?detail=full` 对比 money（−2000g）、bars−5、背包物品；`Game1.player.toolBeingUpgraded` 与 `daysLeft`；升级完成后（2天后）具备升级后的 axe。**强制**用游戏入口（tryToPurchaseItem）验证。 | 冬季买矿 caller【缺失】（脑内无矿洞腿）是现实限制：铜矿/煤从 Clint 购买的可行性需真机验证（Clint 是否在冬季卖 ore）。若 Clint 不卖 ore，则“铜斧升级”在冬季**结构性不可达**——该结论必须标【无法判定】直至真机证实，不得臆测。熔炼需 furnace 放置/操作；路径复杂度高。 |
| 3.3 **“升级后能清掉此前 toolOk=false 的障碍”实测缺失** | `toolOk` 在 Mod：`WorldSnapshot.cs:473 ToolOk = ToolMeetsTarget(...)`, `Contracts.cs:632`；brain 用 `_tool_blocked_tv`（`longrun.py:207`）判定 toolOk!=True 为阻塞（`longrun.py:4801-4803,4985-4986,4827-4829`）；farmwork clear() 对 clump 用 `toolOk`（`farmwork.py:2410-2457`）。`docs/_tool-matrix.md` 明确 bush 需 axe>=1（铜斧）方可清。 | 目标要求升级后能清掉此前 `toolOk=false` 的障碍（验收项）。代码层面有 `toolOk` 判据，但**缺少“升级前 toolOk=false 的 tile → 升级后 use_tool 成功清除”的实测证据链**（obs diff）。A8 全程升级未发生。 | **machine-runner**：选定一处升级前 `observe?detail=full` 中 `toolOk==false` 的 clump/bush（符合铜斧升级后门槛），按 3.2 升级全链执行，升级完成后（≥2天）走到该 tile 用 `use_tool(axe)` 尝试清除，记录前后 tiles[].kind 变化。**log-analyst**：整理成 `docs/_run*-upgrade-toolOk-verify.md` 并附前后 obs diff。 | 独立观测差分：T1（升级前，toolOk==false）→ T2（升级后 axe.level>=1）用相同坐标 `use_tool`：T1.tile 存在且 toolOk==false；T2 执行后该 tile 从 tiles[] 中消失或 kind 变为 cleared（按 Mod 观测口径），且**无** `tool_ineffective`。对比两次 `observe?detail=full`。 | 需真机（machine-runner 独占）。tool_ineffective 口径：`bridge.py:1054`, `farmwork.py:3445,3475`, `longrun.py:8739,7944-7950`。升级需 2天等待（daysLeft==2）——跨日。 |

## 4. LLM 三能力（goal2）

| 缺口 | 现有证据（文件:行号/账本字段） | 为什么是缺口 | 建议卡面（谁写什么） | 可验证判据（独立观测差分） | 依赖与风险 |
|---|---|---|---|---|---|
| 4.1 **策略生成（边界决策给出意图+具名田区，代码落坐标）—【已实现，仅剩简报信息缺陷】** | **prompt 在 planner.py，不在 llm.py**（`brain/agentfarm/llm.py:174 chat / 237 _parse_result` 只是 HTTP 客户端，无 zone 字样；grep `zone|area|field_nw` in llm.py = 0 命中）。实现证据：`planner.py:149 INTENT_FIELDS = ("task","area_hint","reason","expected_evidence")`；`planner.py:2109-2115` system prompt 示例 + “`area_hint` …**不要坐标**”；`planner.py:2141-2152` `__AREAS__`←`brief.areas`、`__ANCHORS__`←`allowed_area_hints(brief)`；`planner.py:230-255 allowed_area_hints`（只放 `field_*`）；`planner.py:266-285 validate_intent`（`missing_area_hint`/`coordinate_in_intent`/`unparsable_area_hint`）；`planner.py:2457 _ask(..., allowed_anchors=allowed_area_hints(brief))`；`planner.py:209-230 _area_hints` 用 `fields_mod.zone_brief_lines(zones)`；`longrun.py:4387-4388` `area_lines = fields_mod.zone_brief_lines(zones)`。fields.py:2-8,21-24,234-238,333-349,352-382（具名 id、无坐标、`resolve_zone` 解析、失败退回 `choose_zone`）。 | 目标要求“策略生成（边界决策给出意图+具名田区，代码落坐标）”。**结论：机制已实现且双向约束**（prompt 给具名区、禁止坐标、解析端拒坐标、失败退回确定性选区）。**剩余缺口不在机制而在信息**：喂给 LLM 的 `zone_brief_lines` 只报 `blockers`（=BLOCKER_KINDS，漏 clump，见 1.1），且**不含容量/当季性/工具等级**（条目087“不是笨是瞎”的根因之一）。 | **dev-coder**：修 1.1（clump 计数进 zone 简报）+ 在 `zone_brief_lines`（`fields.py:329-340`）补“当季可种 / axe 等级 / 该区可开垦量”等事实（**只加事实，不加指令、不改判据**）。**log-analyst**：抽样 `*-llm.jsonl` 决策 5 条核对 prompt 含具名区清单且响应 100% 落到具名 zone 或记录退回原因。 | 证据链：决策 prompt 含 `field_nw/ne/sw/se` 具名清单 + 明确“不要坐标”；响应经 `validate_intent`→`resolve_zone` 命中具名 zone，`plot_in_zone` 产出 anchor（代码落坐标）。抽样≥5 条：0 次 `coordinate_in_intent`，退回 `choose_zone` 时 journal 有原因。 | 机制已就绪，改动应限于简报信息补充（低风险）。禁止在 prompt 里放坐标示例（`fields.py:17-22` 原则）。 |
| 4.2 **结果校验（当天结果与判据对照，含 CHECK 失败/收尾原因）** | `longrun.py:4230-4331 _review_facts/_review_before_sleep`（复盘笔记）；`longrun.py:4722-4727 lessons` journal；`verify-run3.py` 日终校验（`checks` 字段）；`day_end` 含 `checks{...}`、`ended_by`、`ended_reason`、`stages[]`、`unmet*`。 | 目标“结果校验（当天结果与判据对照，含 CHECK 失败/收尾原因）”。现有：`day_end.checks` 覆盖多项（slept_by_us/no_blocking_modal/no_hard_failures/unreachable_within_bound/refused_within_bound/no_unmet_stages/crops_watered/watered_outdoor/day_justified/zero_action_evidenced）且 `ended_reason` 写明原因（如 A8 样例 stuck 原因）。但**是否“与判据对照”全量体现到 LLM review 的输入**？review_llm 仅注入 `recent_notes`（`longrun.py:4540`）和简报，未强制列出每项 CHECK 失败清单。 | **dev-coder**：在 review_llm 请求中追加**判据对照清单**（逐项列出 checks 键值+失败原因：unmet_leftover、unreachable_in_last、refused_in_last、encircled_in_last、midway_leftover_today、blocker_drop 等）。**log-analyst**：抽样 review_llm 的 prompt，确认包含 `checks` 全量及“收尾原因”（ended_by+ended_reason）。 | 证据：`*-llm.jsonl` 中 `kind="review"` 的 prompt 含“判据对照：...”小节，列出失败的 CHECK 项（>=1项时全列）。且 review 输出的 `notes` 中至少引用关键失败项之一（如 stuck_with_leftover、no_unmet_stages false）。**不允许**只写“体力不足”这类模糊结论而无具体判据名。 | review_llm 不参与判定（AGENTS.md/注释多处强调）——只做“人类可读复盘”，但目标要求“结果校验...有可核对证据”。补充到 prompt 而**不改判定逻辑**是合规的（只读式注入）。 |
| 4.3 **据结果优化下一次策略（lessons.json 注入 + run A vs run B L0–L5 对照）** | `planner.py:455-1005`（LESSONS_* 常量、prune_lessons/render_lessons/load_lessons_file/save_lessons_file）；`longrun.py:4567-4727`（_lessons_load/_lessons_from_day/_lessons_flush，注入 `recent_lessons=render_lessons(...)` 到规划 prompt）；`docs/_review-llmfeedback.md`（task-58/59/82 审查，指出 boundedness/source trust 待闭环）；`tools/compare-runs.py:246-564`（L0-L5 定义完整）。 | 目标“据结果优化下一次策略（跨日教训库 `lessons.json` 注入下一轮提示词，并以 run A vs run B 对照 L0–L5 证明‘同形态减少 + 决策理由体现该教训’）”。**现有已全量实现注入通路**（render_lessons 注入到决策 prompt，`recent_lessons` 通过 longrun→planner 传递）。但 `docs/_review-llmfeedback.md` 判定 FAIL（boundedness + source trust 两项未满足）——意味着注入虽存在，却**未达“可验收”的健壮性**。另外“决策理由体现该教训”（L3 influence evidence）需实测对照。 | **dev-coder**：按 `docs/_review-llmfeedback.md §4-§5` 修复 F1（source trust：lesson 必须来自 agentfarm 事实源，拒绝外部篡改条目；`load_lessons_file` 加强校验）和 F2（trim order：按卡面“lessons trimmed first”修复优先级）。**log-analyst**：用 `tools/compare-runs.py` 对 run A（无库）vs run B（带库）做 L0–L5，对照“同形态减少”（L2）和“决策理由体现该教训”（L3：`decision_mentions>0`）。产出 `docs/_compare-A-vs-B-<ts>.md`。 | L0–L5 全绿（或按 criteria 定义达标）：L0 lessons≥1且count>=1；L1 注入生效（run B prompt 含 `lessons(` 段）；L2 comparable signals 中同形态 improved 全部 true；L4 无回归（tail VERIFIED 不下降）；**L3** 有 influence_evidence（decision_mentions>0）且能溯源到注入的 lesson id/scope。且 run B 决策理由需能追溯到对应 lesson（抽样决策文本含 lesson 要点）。 | `lessons.json` 只喂提示词、不参与判定（设计原则）——须保持该边界。boundedness：LESSONS_INJECT_MAX=3、LESSONS_INJECT_CHARS=200（`planner.py:456-458`）极小，易稀释“据结果优化”。需接受现有限额但在对照中**实证**注入确有影响（L3），而非靠“灌字”达标。 |

## 5. 连续5日 VERIFIED + 验收口径（goal2）

| 缺口 | 现有证据（文件:行号/账本字段） | 为什么是缺口 | 建议卡面（谁写什么） | 可验证判据（独立观测差分） | 依赖与风险 |
|---|---|---|---|---|---|
| 5.1 **`no_work` VERIFIED 白拿风险（口径需严格）** | `tools/verify-run3.py:31,33,1019,1288,1302,1468,1543`（要求 tail VERIFIED ≥ days；对 stuck/justified 等有处理）；`docs/_release-0.7.47.md §4,§7`；A8 样例：7天全是 `no_work` 早收工（条目087）。`longrun.py:5535-5544`（sleep_guard：work_reasons() 空时倾向 `no_work`）。 | 目标“连续 5 个游戏日全自主 + 大模型策略闭环”。现有口径下“早早没活→`no_work`→`verified=true`”可能构成“白拿”。条目087 明确指出 A8 的 VERIFIED 多为 `no_work`。A9/B9 要给出**真证据**（非纯空场景）。 | **deputy-lead+log-analyst**：复核 `verify-run3.py` 对 `no_work` 的计入规则：是否要求**实质工作**或至少“有意图→被执行/部分执行”的证据。建议新增“实质性工作日”过滤：若全天 `actions==0` 且 `work_reasons()` 全空且**从未**进入任何 clear/till/plant/water/harvest 阶段且 `plots[]` 全无改动→标注“空日”（empty_day）但**不计入‘全自主实质日’**，单列统计。 | **双轨统计**：①`tail VERIFIED`（现有口径）②`tail VERIFIED ∩ non_empty`（≥1次实质性 tile 变动：kind 消失/变为 dirt/watered/crop 长成等，且有 stage 执行记录）。连续5日验收需**至少**满足②，或 Lead 明确豁免理由并附独立 obs diff。两侧工具（verify-run3 + analyze-longrun）同向。 | 不能一刀否定 `no_work`（冬季确实无活是客观场景）。但要防止“策略闭环”在空场景下“达标”。建议用**世界变化**（存档 diff：tiles[] 变动集合非空）而非“自述”判定“实质工作”。 |
| 5.2 **“≥2份独立观测 + 每次跨日落盘六串配对”口径落地** | `docs/_release-0.7.47.md §4` 明确 A9/B9 条件（restore baseline→guardian→detached，verify-run3 --days 5 --smapi + analyze-longrun + compare-runs L0–L5 + 三个 checker）；跨日落盘六串配对是既定纪律。 | 要求有“可核对证据”。需确保每个游戏日都产出≥2份独立观测（避免单次 obs 失真），且跨日存档对比全量落盘。现有工具链（verify-run3/analyze-longrun/compare-runs）是否强制校验“观测份数≥2”【缺失】？需核对。 | **machine-runner**：严格按 A9/B9 流程：每日结束前后各做 `observe?detail=full` ≥1次（共≥2），并落盘到 `scratch/` 或按既定命名。**log-analyst**：在 `verify-run3.py` 增加 `obs_count_per_day>=2` 校验（若<2→在 summary 中标注【无法判定】并不计入严格口径）。 | 独立观测差分：逐日检查 `docs/_smoke-*.md` 或 evidence 中 obs 快照清单（文件名+mtime+size+SHA256）。跨日六串配对：退前/退后存档文件四件（size/mtime/SHA256）逐字节比对（机器纪律）+ `bridge.json` 已删 + 17890 无 LISTENING。全部满足才算“严守口径”。 | tilesTruncated（`fields.py:28-30`）导致观测不完整。若任一 obs 出现 `tilesTruncated==true` 且覆盖范围不足以判定 zone blockers，**必须**标【无法判定】而非推断。 |
| 5.3 **A9/B9 能否给出真证据（冬季场景）** | `docs/_release-0.7.47.md §4,§7`；`docs/00-开发日志.md:092`（0.7.48 快修 slot_relief 字段补齐后直接做 A9）；`verify-run3.py` 与 `analyze-longrun.py` 现有判据。 | 条目087：目标1 在冬季结构性不可达（无矿洞腿/无买矿 caller）。但 A9/B9 仍按“连续5日 VERIFIED”走。需预判冬季下“真证据”的定义：若全是空日（5.1②失败）→结论应是“场景限制导致无法达成‘实质全自主’”，而非强行达标。 | **product-observer（本卡）**：在本缺口清单中**显式标注冬季风险**（Clint 买矿可行性【无法判定】、种子可得性低、upgrade 路径依赖买矿）。**lead**据实定验收口径（实质日≥N 天 vs 纯尾5天全空）。 | 预验收：跑前先看 A9 warmup（冬季26/27/28）首日观测：`farm.crops/live_crops`、可种清单、Clint 菜单（是否有 ore）、背包空位。若首日即“空日”且三天全空→预判“连续5实质日”极可能失败，需**如实上报**而非改判据。 | 不改判据（AGENTS.md 禁止）。只收窄“达标”定义到“有真证据”的子集。 |

## 6. 你自己的新发现（重要度排序）

| 序号 | 缺口描述 | 现有证据（文件:行号） | 为什么是新发现 | 建议卡面 | 可验证判据 |
|---|---|---|---|---|---|
| N1（最高） | **zone blocker 口径与用户清空清单完全错位**：用户列“树桩/圆木/巨石”却 fields.BLOCKER_KINDS 未涵盖 clump。 | `fields.py:54,315,481` vs `farmwork.py:163` vs `ClumpMeta.cs:14-16` | 既有文档（_tool-matrix.md）关注 toolOk 能力，但**从未**将“zone 清空判据”与“用户验收清单”做对齐。1.1-1.2 源自此错位。 | **dev-coder**：修订 BLOCKER_KINDS→ZONE_BLOCKER_KINDS（含clump）并同步 zone_brief_lines 注释“待清理”含义；新增 zone-level 归零判据（1.2）。 | 新旧口径下同一观测的 `blockers_zone` 差异=clump 数，且修订后 clump 出现时能被正确计入。 |
| N2 | **“指定作业区清空”与树预算（全窗口）冲突**：clear_area 的树 leftover 包含全窗口树（`longrun.py:4994-4996`），而目标要求“指定作业区清空”。 | `longrun.py:4731-4830,4954-5015,3715-3771` | 若强行要求“指定作业区内树全清”，将与 `tree_budget_room`（按可支配体力封顶）直接冲突。需在范围上澄清：**非树障碍+clump 限定在作业区内归零；树清理由预算单列**。 | **product-observer+dev-coder**：在卡面（1.2）明确“清空范围”（exclude out-of-plot trees from ‘zone cleared’ criterion）。 | zone_clear 判定时**不**将 plot 外树计入 blockers_zone；`_leftover("clear_area")` 树项仍按现有预算语义单独统计。 |
| N3 | **经济从未真正执行（仅 gate/log）**：buy_seed/upgrade_tool 全无 caller。 | `TASK_KINDS`（101-114）无 buy/upgrade；`seed_gate/no_seed_for_sale/tool_upgrade_skipped` 全是日志。 | A8“经济零变化”（money 2767g 全程不变）早有迹象（条目087§1.5），但此前未聚焦到“**执行路径完全缺失**”。 | **dev-coder**：新增两类 kind+执行器（3.1-3.2），首版**可观测差分强制校验**（money/inventory 变动必须来自游戏入口）。 | 每次 buy/upgrade 都产出**前后 obs diff**（money±、物品增减）并 journal `economy_action`，且 diff 可溯源到 ShopMenu 行为。 |
| N4 | **lessons 注入健壮性未达验收（boundedness+source trust）仍是 FAIL** | `docs/_review-llmfeedback.md §3-§5`（F1/F2）；`planner.py:924-983 load_lessons_file`, `planner.py:923-925 vs 929` trim order存疑。 | goal2 明确要求“lessons.json 注入下一轮提示词”且“run A vs run B L0–L5 对照”。若注入通路不健壮（可注入未受信任条目、trim 顺序与文档冲突），对照结论无说服力。 | **dev-coder**：修复 source trust（校验 src==agentfarm、id 格式、kind/scope 合法）+ trim order（按卡面“lessons trimmed first”）；**log-analyst**：实做 A vs B 对照并产出 L3 证据。 | `load_lessons_file` 拒绝外部条目时 journal `lessons_rejected`（含 reasons/untrusted）；compare-runs L3 输出 `decision_mentions>0` 的 influence 列表（含 lesson_id、scope、count）。 |
| N5（最低但需关注） | **“实质全自主”口径模糊（no_work 白拿）** | `verify-run3.py` 对 verified 计入；A8 全 no_work VERIFIED。 | goal2 要“连续5个游戏日全自主”。若冬季全空也算“全自主”达标，是否符合预期需明确定义。**不改判据**前提下，建议**双轨统计**（5.1）。 | **deputy-lead+lead**：商定验收口径（strict: non_empty ≥5 连续）。本 observer 仅列事实与建议，不改判据。 | `day_end.actions>0` 或 tiles[] 世界变动非空 或进入≥1个实质 stage（clear/till/plant/water/harvest）任意一项。 |

## 7. 建议优先级（执行顺序）

按“阻塞验收”降序：

1. **P0**：1.1（ZONE_BLOCKER 含 clump）+ 1.2（zone-level 清空判据）——直接关系“指定作业区清空”验收口径。若不修订，验收极易“按旧口径PASS”却违背用户清单。
2. **P0**：1.3（连续2天复核保持清空）——目标明文要求，且需跨日对比工具。
3. **P0**：5.1+5.2（实质日口径与观测≥2份）——关系“连续5日 VERIFIED”的**真证据**，尤其 A9/B9 冬季场景。
4. **P1**：3.1+3.2（经济双头执行路径）——目标1核心“种子 vs 工具升级”平衡。首版聚焦铜斧（已有码农民），但冬季买矿可行性【无法判定】需真机。
5. **P1**：4.1-4.3（LLM 三能力）——goal2 核心。注入通路已存在，但健壮性（N4）和 L3 对照要闭环。
6. **P2**：2.1-2.2（余力多清）——锦上添花。树预算已部分覆盖“保留浇水体力”，但“核心完成后再清”未显式实现。
7. **P2**：3.3（升级后 toolOk 失效障碍清除实测）——需真机验证（machine-runner）。

## 8. 已知限制（如实）

- **tilesTruncated**：`fields.py:28-30,407-413`。当 `location.tilesTruncated==true` 或 `tillable[]>=TILLABLE_CAP` 时，zone 统计**不完整**。任何 zone_clear 判定都**必须**检测并在结论中标注【无法判定】。
- **树预算 vs 作业区清空**：`longrun.py:4994-4996` 树包含全窗口。建议**不**将 out-of-plot 树纳入“指定作业区清空”归零判据（N2）。
- **冬季结构性限制**：Clint 是否卖 ore（铜矿/煤）【无法判定】；无矿洞腿；种子可得性低。铜斧升级全链（3.2）在冬季可能**结构性不可达**——验收时不得臆测，须真机观测证实。
- **lessons 渠道极小**：`LESSONS_INJECT_MAX=3, LESSONS_INJECT_CHARS=200`（`planner.py:456-458`）。L3“决策理由体现该教训”需在此限制下实证（4.3）。
- **review 不参与判定**：`review_llm` 纯复盘（多处注释）。4.2 建议**仅改 prompt 注入**，绝不改判定逻辑，符合既有设计。
- **经济强制游戏入口**：买种/升级**一律**走游戏入口（ShopMenu.tryToPurchaseItem 等），**绝不**直接改 `Game1.player.Money`（AGENTS.md §5）。前后 obs diff 是必需的独立证据。

## 9. 建议卡面模板（最小可执行）

建议每条 P0 用如下模板：

```
【卡名】<简短，如 zone-clump-blockers>
【责任人】dev-coder（必要时 deputy-lead/log-analyst/machine-runner 配合）
【范围】只改 brain/agentfarm/fields.py + （如需）longrun.py 日终；不改任务板、deploy、判据外逻辑（除新增只读统计）
【验收】
- 单元：py_compile -W error::SyntaxWarning 通过；定向单测（若相关）通过
- 观测差分：指定 zone 两次 observe?detail=full 对比 blockers（含clump）归零
- 证据：文件:行号 + 命令输出 + obs diff
【禁止】git commit --amend；git add -A；直接改金钱；改既有 checks 真值
```

## 附录：核查命令（本次已用）

- `grep toolOk|tool_ineffective`（brain+mod）
- `grep TASK_KINDS`（planner.py:101-114）
- `grep BLOCKER_KINDS`（fields.py 全量；仅 fields.py 使用）
- `grep CLUMP_KINDS`（farmwork.py）
- `grep zone_cleared|cleared_zone|保持清空|连续.*天`（全仓）
- `grep lessons`（longrun.py/planner.py）
- `grep L0|L1|L2|L3|L4|L5`（tools/compare-runs.py）
- `grep leftover/_stage_tiles/_tree_budget`（longrun.py 关键段）
- `read fields.py, planner.py TASK_KINDS, longrun.py _stage_tiles/_leftover/_stamina_budget/_budget_defer_reason`
- `grep zone|field_nw|area|坐标 in brain/agentfarm/llm.py`（0 命中 → prompt 不在 llm.py，在 planner.py:2109-2152）
- `grep zone_brief_lines|area_hint|choose_zone|具名|田区 in brain/agentfarm/*.py`（确认签名与调用点）
- `read planner.py:149,209-285,2109-2152`（INTENT_FIELDS / validate_intent / system prompt 模板）
- `Get-ChildItem -Recurse -Filter *.cs`（核实 mod 真实路径为 `mod\AgentFarm.Bridge\*.cs`，非 `mod\StardewBot\`）

> **结论**：现状与目标存在多处**口径缺口**（尤其 zone blocker 定义、zone-level 归零判据、连续2天复核、经济双头执行路径），而非“纯实现遗漏”。建议先落 P0 四项（1.1-1.3,5.1-5.2）再做 A9/B9，以免用“旧口径”达成新目标。
