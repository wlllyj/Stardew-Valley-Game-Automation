# 目标1③ 铜斧升级链：铜锭来源缺口与可行路径策略（a9-goal12 · product-observer）

> 日期：2026-10-20（夜）；角色：product-observer（只分析、写文档，不改代码、不 commit）。
> 任务来源：team-lead 指派，盘点 Goal 1③「至少一次真实工具升级（铜斧：2000g + 5×(O)334 铜锭），钱与材料均来自合法玩法」的证据链缺口，给出路径建议与下一次真机探针（T-6b）计划。
> 配套证据：
> - `docs/_probe-save-state-2026-10-20.md`（T-6 只读探针，winter-26 存档）
> - `docs/_run10-material-scan.md`（task-209 Clint 货架真机扫描）
> - `docs/_run10-furnace-acquire.md`（task-226 买 1 铜矿解锁熔炉 真机 PASS）
> - `docs/_il-tool-upgrade.md`、`docs/_il-furnace-unlock.md`、`docs/_observe-goal12-2026-10-19.md`

---

## §0 先结论（三句话）

1. **「Clint 卖不卖矿/锭」这个 T-4 标【无法判定】的项，已经被历史真机证据坐实**：Clint 普通店卖 **铜矿 (O)378 75g / 煤 (O)382 150g / 铁矿 150g / 金矿 400g**，**不卖铜锭 (O)334**（`_run10-material-scan.md` §2④）。⇒ **选项 (c)「直接买铜锭」已被证伪**，选项 (a)「买铜矿→熔炼」是 viable 的。
2. **熔炉蓝图这道坎也已跨过**：task-226 证明「从 Clint 买 1 个铜矿就触发 Clint 送 Furnace 蓝图」（`_run10-furnace-acquire.md` PASS）。当前 winter-26 存档尚未触发（`<copperFound xsi:nil="true"/>`、craftingRecipes 无 Furnace、全地点无熔炉），但只要买 1 铜矿即可解锁。
3. **所以 Goal 1③ 并不可行性问题，而是一个「能力 + 钱」的门**：缺口 = ① 造熔炉/放大型件/投料冶炼的 routine（新能力，task-227 已在计划内）、② 缺口约 **3358g** 的现金（当前 2767g，全链路地板 6125g）。**风险旗标应按「待能力落地 + 待攒钱」而非「铜源不存在」来写。**

---

## §1 缺口陈述（Gap Statement）

**核心事实（T-6 只读探针，winter-26 存档，逐字节未改档）：**
- 背包 12 格全满（`free_slots=0`）；其中 `(O)378` **铜矿 ×1**（RAW ore），**(O)334 铜锭 ×0**——**一件铜锭都没有**（`_probe-save-state-2026-10-20.md` §3 slot7）。
- 五件工具（`Axe/Hoe/WateringCan/Pickaxe/Scythe`）`upgradeLevel` **全 0**（`§4`）；无任何在途升级（`toolBeingUpgraded=null`、`toolUpgradeDaysLeft=0`）。
- 钱 **2767g**（升级价 2000g，钱够；但材料 0）。
- farm-wide clump **0**（stumps/logs/boulders/rockPiles/greenRain 全 0），即**当前档没有一个 toolOk=false 的锚点格**（`§5`）；结构性论据：五个工具全 L0，按 `ClumpMeta.cs` 门槛（stump 斧≥1 / log 斧≥2 / boulder 镐≥2 / rockPile 镐≥3），**未来任何新刷出的 clump 都必然 toolOk=false** ⇒ 升级解锁的前提确实成立，只是当前没素材。

**升级配方硬约束（`brain/agentfarm/farmwork.py:423` + `_il-tool-upgrade.md` §2.3）：**
- `UPGRADE_TRADE_ITEMS = {0:"(O)334", 1:"(O)335", 2:"(O)336", 3:"(O)337"}`，`UPGRADE_TRADE_COUNTS = {0:5, …}`；铜斧（L0→1）需 **2000g + 5×(O)334 铜锭**。
- 价格表与锭表是**代码常量**（`GetToolUpgradeConventionalPrice` / `GetToolUpgradeConventionalTradeItem`），所有升级级别都要对应锭 ⇒ **不存在「不用锭」的替代升级路线**（详见 §3 选项 (d)）。

**铜锭来源——当前 agent 能力下的真实可用面（已证/已否）：**
- 农场大障碍不打铜锭：`ResourceClump.performToolAction` 四分支只掉 `(O)709/(O)390/(O)386/(O)749/(O)292`，**绝不含 (O)334 铜锭，也不含 (O)378 铜矿**（`_il-tool-upgrade.md` §0 / `_observe-goal12-2026-10-19.md` §3.1，IL 实证）。⇒ 农场 clump 既给不了锭也给不了矿。
- 矿洞开采：脑内**无 mine 意图**（`planner.py` TASK_KINDS 无 mine），`deepestMineLevel=0` 从没下过矿 ⇒ 当前无采矿能力。
- Clint 买矿：✅ 有（75g/个），见 §0。
- Clint 买锭：❌ 无（已证伪）。
- 熔炼：需要 Furnace 配方（需要先「真收到 1 铜矿」触发事件 992553），当前存档没有该配方。

=> **缺口可精确表述为**：当前存档 **0 铜锭 + 0 熔炉配方 + 0 熔炉实物 + 无采矿能力**；唯一已被证可走的合法来源是「Clint 买铜矿 →（买 1 个解锁熔炉配方）→ 造熔炉 → 冶炼成锭」。这要求两项当前不存在的 agent 能力（造/放大型件 + 机器投料冶炼）和约 3358g 的现金补足。

---

## §2 选项评估（逐项定结论）

### (a) 买铜矿 (O)378 → 造熔炉 → 冶炼 5 锭（**推荐**）
- **可行性：已证可行（机制层）**。
  - Clint 卖铜矿 75g（`_run10-material-scan.md` §2④，task-209 真机）。
  - 买 1 个铜矿即触发 `Data/Events/Farm` 键 `992553` 次日 06:00–11:30 进 Farm 演 Clint 过场，给 Furnace 配方 + 任务 11（`_run10-furnace-acquire.md` task-226 PASS；`_il-furnace-unlock.md` §2）。
  - 熔炉配方 = `378 20 390 25/.../l 2/`（20 铜矿 + 25 石，石农场免费）。
  - 冶炼配方固定：5 铜矿 + 1 煤 → 1 铜锭（熔炉逐次烧，跨多个游戏内时段）。
- **成本（地板）**：5 锭需 25 矿 + 5 煤；熔炉需 20 矿（石免费）；共 **45 铜矿 + 5 煤 + 升级 2000g** = 45×75 + 5×150 + 2000 = **3375 + 750 + 2000 = 6125g**。
- **当前钱 2767g ⇒ 缺口约 3358g**，须靠 spring 种/收/出货攒出（合法玩法，非卡 bug）。
- **需要的新能力（真实缺口）**：① 打开 Clint 普通店买 Copper Ore/Coal 的 caller（已有 `buy` 技能可复用，但需确认货架条目命中）；② `craft()` 造 Furnace（task-227 计划内，已验证过 craft 通路）；③ 放置大型件（大件 placement skill，当前缺失）；④ 机器投料/收货（向熔炉投 5 矿 +1 煤、取回锭，当前无机器交互 skill）。即 `_run10-material-scan.md` §2④ 列的「4 类新能力」。
- **优点**：黄金成本低（仅 6125g，靠出货可补）、dev 增量可控（buy 已有，补 craft/place/smelt 三段）、完全合法（买矿+游戏原生事件给配方，非写档）。
- **缺点**：链路长（买矿→等次日配方→攒钱→买齐→造炉→冶炼多时段→升级→等 2 天取回），且背包 12 满须先腾格（铜矿可堆叠，约需 1–2 格）。

### (b) 矿洞挖铜节点 → 冶炼
- **可行性：机制可行，但 agent 能力缺口极大**。矿洞铜节点（1–39 层）出矿免费（不需花钱买矿），省下 45×75=3375g 矿钱，只剩 5 煤 + 2000g ≈ 2750g，现金上反而更宽松。
- **代价**：需要 mine 导航 + 采矿 + 战斗/避险能力，脑内 `planner.py` 无 mine 意图、`deepestMineLevel=0` 从没下过矿；这是一整个新子系统，工作量远超 (a) 的三段 routine。
- **结论**：不推荐作为首路径；仅当 (a) 的能力/现金门长期卡住时，作为「省现金」的备选评估。

### (c) 直接买铜锭 (O)334
- **已被证伪**：task-209 真机扫描 Clint 普通店 **不卖铜锭**（只卖矿与煤，`_run10-material-scan.md` §2④；`_il-furnace-unlock.md` §5 表「找 Clint 买铜锭：无」）。⇒ **此选项剔除**。

### (d) 放宽「铜斧」字面目标 / 找无锭替代升级
- **不可行，须明确写死**：`UPGRADE_TRADE_ITEMS` 中**所有**升级级别（铜/铁/金/铱）都要求对应锭（`(O)334/335/336/337`），锭表是代码常量、数据驱动、不可绕过（`_il-tool-upgrade.md` §2.3）。**不存在「不用锭」的真实工具升级**。⇒ 任何「真实工具升级」都绕不开「合法搞到某类锭」，铜锭只是第一级。放宽字面「铜斧」只能改成「第一级可达成的最便宜真实升级（仍是铜级，因为 L0→1 就是铜）」，并不能消除锭依赖。

---

## §3 推荐路径（Recommended Path）

**选 (a)：Clint 买铜矿 → 解锁熔炉配方 → 造熔炉 → 冶炼 5 铜锭 → 铜斧升级 → 2 天后取回。**

**理由（按「合法玩法 + 最小新能力」裁定）：**
1. 唯一已被真机双向证实的合法铜源：Clint 卖矿（task-209）+ 买 1 矿即送熔炉（task-226）。(c) 被证伪、(b) 工程量大、(d) 物理上不可能。
2. 新能力增量最小且已有载体：`buy` 技能现成；`craft()` 已在 task-227 计划并验证过；仅缺「放大型件」与「机器投料/收货」两段 routine，属中体量、低风险的 Mod skill 工作。
3. 现金门（≈3358g）靠春季种收出货即可补足，是「玩法内」收入，不触碰任何判据红线。

**落地顺序（给实现侧 task-227 的对账，非本文档职责）：**
1. 买 1 铜矿 → 次日进 Farm 触发事件拿 Furnace 配方（task-226 已验证机制；当前存档首次做即可解锁）。
2. 春季起通过种/收/出货把现金从 2767g 攒到 ≥6125g（同时顺势腾出背包格）。
3. 买齐 45 铜矿 + 5 煤（可分批，铜矿堆叠占格少）。
4. craft Furnace（20 矿 + 25 石）→ 放置 → 投料冶炼 5 锭（跨多时段）。
5. Clint 升级店买铜斧（2000g + 5 锭，`_il-tool-upgrade.md` §3 的 `upgrade_tool` skill 已就绪）。
6. 2 天后进店取回（axe.level 0→1），随后 farm 新刷出的 stump(600) 等 clump 由 toolOk=false 转 true ⇒ 目标1③「升级后能清掉此前 toolOk=false 的障碍」闭环。

---

## §4 T-6b 真机探针计划（machine-runner）

> T-4 在 `_observe-goal12-2026-10-19.md` P0-3 把「Clint 售矿【无法判定】」列为缺口。该缺口已被 task-209 / task-226 坐实，**故 T-6b 不是「发现」，而是「对当前 live 存档的确认 + 能力缺口盘点」**。仍要求真机只读执行（不买、不造、不改档）。

**(i) Clint 货架目录核对（确认 live，复 task-209）**
- 方法：进 Town → 走到 Blacksmith 柜台前 → 用 `Utility.TryOpenShopMenu("Clint","Clint",true)`（public，见 `_il-tool-upgrade.md` §1.2/§3.0）或只读 `ShopBuilder.GetShopStock("Clint")` → 打印全部 `itemId / name / price`。
- 记录：**是否含 `(O)378` 铜矿（预期 75g）、`(O)382` 煤（150g）、`(O)334` 铜锭（预期：无）**。
- 判据：与 `_run10-material-scan.md` §2④ 一致即 PASS；若 Clint 竟出现 (O)334，则选项 (c) 复活、全链路现金门骤降——须立即上报 lead。

**(ii) 熔炉状态核对（当前存档是否已有配方/实物）**
- 读 `player.craftingRecipes` 是否含 `"Furnace"`（预期：**无**，因 `<copperFound xsi:nil="true"/>`、未买过矿）；读 `Stats.copperFound`（预期 0/未设）、三个 mail 集合是否含 `copperFound`（预期 无）。
- 全场扫 `location.objects` 是否已有 `(BC)13` Furnace 实物（预期：**无**）。
- 判据：三项全「无」= 当前存档处于「熔炉未解锁」态，首次买 1 矿即可解锁（task-226 机制在同年同档已证，本次只确认未触发）。

**(iii) 能力缺口盘点（若 (a) 为主路径，列出缺哪几段 routine）**
- 由于 (a) 已被选为主路径，(iii) 的「only-if 采矿」分支**不触发**；改为盘点造/放/冶炼缺口：
  - 是否有「造大型件 craft + 放置」skill（预期：craft 有载体、placement 缺）；
  - 是否有「机器投料/收货（熔炉烧矿）」skill（预期：缺，见 `_run10-material-scan.md` §2④「投料/收货 无机器交互 skill」）；
  - 是否有「开 Clint 普通店买矿/煤」的 caller（预期：buy 技能可复用，需确认货架条目命中）。
- 输出：一份「缺失 routine 清单」供 dev-coder（task-227）对账。

**(iv) 现金/背包前置确认**
- 记录 live `player.money`（预期 2767g）、`free_slots`（预期 0，须先腾格）、`farm`石材可得性（stone 农场随处可得，熔炉 25 石无忧）。
- 判据：money 距 6125g 缺口 ≈3358g，须在春委内由出货补足——探针只记录起点，不代攒。

**探针产物**：`scratch/_t6b_clint_and_furnace.json`（货架原文 + craftingRecipes + copperFound + 缺失 routine 清单 + money/free_slots），不 git commit（按 Lead 收口规程）。

---

## §5 风险旗标（Risk Flag）

**原假设（T-4）的极端风险「Clint 既不卖矿也不卖锭且无采矿能力 ⇒ Goal 1③ 字面不可行」——已被历史证据推翻**：Clint 确卖铜矿（task-209）、买 1 矿确解锁熔炉（task-226）。故 Goal 1③ **并非不可行**。

**真实风险收敛为两点（均可在「不求助用户」前提下消解）：**
1. **能力门**：造/放大型件 + 机器投料冶炼 三段 routine 尚未实现（task-227 计划内但未落地）。若 task-227 长期不排期，则 (a) 链路卡在「有矿无炉/有炉无烧」。
2. **现金门**：当前 2767g，全链路地板 6125g，缺口 ≈3358g，须春季种收出货补足；若春季经济再投资被 task-240b / 背包死锁（E2）再次卡住，则现金到位延迟。

**按 standing 指令「完全不用我介入」——不向用户提问**，给出如下建议（请 lead 裁定）：

- **建议一（主）**：按 §3 推进 (a)，把 task-227 的「craft/place/smelt 三段 routine」排入实现，并让春季长跑自然攒够 ≈3358g 缺口；T-6b 探针（§4）只做确认与缺口盘点。
- **建议二（安全网 / fallback，PENDING T-6b 实证，非立即执行）**：若 T-6b 复测出现**任何与 task-209/226 相悖的反常**（如 Clint 货架突变不卖矿、或买矿不再解锁熔炉），则 lead **可**将字面「铜斧」放宽口径为「第一级可达成的最便宜真实工具升级（仍须某类锭，无法去锭化）」，并以「合法搞到该类锭」为验收锚点——但目标1③「升级后清掉 toolOk=false 障碍」的验收实质不变。此放宽**仅在证据反转时启用**，当前证据下**不启用**。
- **明确排除**：任何「直接写 craftingRecipes / 直接写锭进背包」的捷径都属造假，与本项目「观测差分、不造假」验收路线冲突，**不在建议内**。

---

## §6 与既有证据/任务的对账（避免重复造轮子）

- T-4 `_observe-goal12-2026-10-19.md` P0-3「Clint 售矿【无法判定】」→ **本文以 task-209 坐实，标记为已解**。
- U1「铜锭来源无路径」→ 本文判定为「路径存在 = (a)，缺口在能力+现金」，非「无路径」。
- U2「toolOk=false 锚点格零实证」→ 当前 winter-26 档 0 clump（T-6 §5）；结构性论据成立，待春季 farm 刷出 clump 后由 `blocked_by_tool` 事件锚定（非本档阻塞）。
- task-227（铜斧全链路）已存在于 `_release-0.7.39.md` / `_review-0.7.39.md` 计划，本文 (a) 与之完全同向，仅补全「可行性已证 + 现金缺口量化 + T-6b 确认探针」。
- `_upgrade-protocol.md` §2 旧预算 6275g（买 45 矿+6 煤）与本文 6125g（5 煤）量级一致，旧稿「Clint 是否卖矿未证」的前提已被 task-209 推翻，协议可按本文结论改写。

---

## §7 已知限制（如实）

- 本文综合「T-6 只读探针 + task-209/226 历史真机 + IL 取证」；未在本档重跑买矿/造炉（observer 纪律 + 不求助用户）。
- 冶炼的「跨时段投料/收货」时序细节、放置大型件的落点选择，属 task-227 实现层，本文只列缺口不展开。
- 现金缺口 3358g 假设「45 矿 + 5 煤 + 2000g」全买；若 agent 改用 (b) 采矿免费得矿，则现金门降到 ≈2750g，但工程门骤增——此权衡见 §2(b)，不纳入主路径。
- 背包 12 满（`free_slots=0`）是买矿/收货的前置阻塞，须与 task-240b / E2 死锁修复协同解决。
