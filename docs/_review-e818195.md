# task-44 独立验收：`e818195`（0.7.24 = task-43 长路径续跳 + task-42 出货闭环）

* 验收人：deputy-lead（只读，未碰游戏/桥，未改任何源码/测试/工具）
* 判定：**PASS-WITH-NITS**（无必修项；NIT-1 建议装机前顺手补，其余留档）
* 对象：`e818195`「0.7.24: task-43 长路径跳预算/续跳 + task-42 出货闭环(ship)」，14 files +1376/−48

---

## §1 对象与惯例读数（全部我亲跑）

| 项 | 读数 |
| --- | --- |
| HEAD | `e818195`（父 `a80d3ec`，其上 `f19f592`/`96cb43c`） |
| 工作树 | `git status --short` **空**；`git diff --numstat HEAD` 空 |
| `git show --stat e818195` | bridge.py +34 / farmwork.py +288 / longrun.py +61 / planner.py +18 / docs/_release-0.7.24.md +20 / Contracts.cs +55 / MoveToLocationSkill.cs +98 / **ShipSkill.cs +237（新）** / Skills.cs +21 / StepMover.cs +102 / WorldSnapshot.cs +60 / test_farmwork.py +310 / test_longrun.py +101 / test_planner.py +19 |
| 越界（对象侧） | 在 `e818195` 上 **无** bump（`:4 "Version": "0.7.23"`；`bridge.py:39 MOD_VERSION_EXPECTED = "0.7.23"`）、无 `docs/00-开发日志.md`、无 `logs/`、无装机痕迹 ⇒ task-44 对象本身干净 |
| 验收期间并行变更（复核后立即记录） | Lead 在 20:00:58 落了 **`ff25ee7`**（`manifest.json` 0.7.23→**0.7.24**、`bridge.py:39` 同步 0.7.24 + 注释）与 **`e8d7fa2`**（docs 条目 043 / 装机 / run5 派单）。`git diff e818195 HEAD -- brain/agentfarm/bridge.py` **只有 6 行**（`MOD_VERSION_EXPECTED` 常量与注释），行为代码零变化 ⇒ 本报告全部语义结论不受影响；唯一变化是 bridge.py 哈希由 `185A20369926` → `2F169379F998`（其余 12 个文件哈希不变） |
| `py_compile -W error::SyntaxWarning`（7 个 py） | exit 0 |
| 全量单测 | **Ran 346 tests in 2.491s / OK** |
| `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` | **0 警告 / 0 错误**（1.18s） |
| SHA256 前 12 | bridge.py `185A20369926`、farmwork.py `C0D9C5F83AA2`、longrun.py `8024851052D0`、planner.py `F0E91E8FE56D`、Contracts.cs `26662DC8E203`、MoveToLocationSkill.cs `C802857C0A95`、ShipSkill.cs `19A6832E906D`、Skills.cs `53CF5FEAA658`、StepMover.cs `49AF0B5EAA1F`、WorldSnapshot.cs `62843DC84820`、test_farmwork.py `0282AEF2E392`、test_longrun.py `655A87EF5877`、test_planner.py `5E0B9FAACF95` |

**我做的基线口径更正（NIT-5，非缺陷）**：卡面写「基线 335 + 11 新用例」。我按提交前后逐文件数 `def test_`：
`e818195^` = test_farmwork 49 + test_longrun 82 + test_planner 57 = **188**，`e818195` = 62 + 85 + 59 = **206** ⇒ **+18 条、0 条删除/改名**（`git show e818195 -- tests/... | Select-String '^[+-]\s+def test_'`：+18 / −0）。
335 是"只加了 task-43 那 7 条"的中间态；正确口径是 **328（= task-41 验收读数）+ 18 = 346**。

---

## §2 task-43（长路径跳预算 / 续跳）逐条对账

| 卡面 rev3 要求 | 实现 | 行号 | 结论 |
| --- | --- | --- | --- |
| 跳预算 `clamp(4000+500×剩余, 8000, 门30000/普通20000)` | `HopBaseMs=4000`/`HopMsPerStep=500`/`HopTimeoutMs=8000`(下限)/`WalkHopMaxMs=20000`/`DoorHopMaxMs=30000` + `HopBudget()` | `mod/AgentFarm.Bridge/MoveToLocationSkill.cs` | ✅ |
| **不超整体剩余** | `HopBudget` 内 `if (want > remaining) want = remaining;` 再抬到 `TimeoutMinMs` | 同上 | ✅ |
| 收尾跳同款预算 | `Begin()` Running 后 `want = HopBudget(mover.PathSteps, remaining, doorHop); mover.RaiseBudget(want); _hopBudgetMs = want; _hopSteps = mover.PathSteps;` | 同上 | ✅ |
| `ClampTimeoutFor` 对 `move_to_location` 走 60000 | `Skills.cs:88-89 case "move_to_location": return MoveToLocationSkill.ClampBudget(timeoutMs);`，`MoveToLocationSkill.MaxTimeoutMs = 60000` | `mod/AgentFarm.Bridge/Skills.cs:77-89` | ✅ |
| `StepMover.Tick` 顺序 = 进展证据 → 超时续跳 → 模态 → 卡死 | ①`:282-283` `if (movedPixels \|\| movedTile) _stuckFrames=0 else ++` ②诊断刷新 ③`:306-309` 续跳 ④模态 ⑤`:326-330` 卡死 | `mod/AgentFarm.Bridge/StepMover.cs` | ✅ **顺序逐条一致** |
| `StuckFrames 90→180`（~3s） | `:92 public const int StuckFrames = 180;` | 同上 | ✅ |
| 续跳有界 | `:103 ExtensionMs=8000`、`:106 MaxBudgetExtensions=8`、`:156-158 RaiseBudget` 只增不减、`:306` 要求 `_stuckFrames==0` 才续 | 同上 | ✅ 最多 8 次 × 8s ⇒ 有界 |
| 脑侧两段式**只重试一次** | `farmwork.ensure_location`：`move_to(side, timeout_ms=30000)` 成功后 `retry_ms=max(15000, timeout_ms//2)` 再 `move_to_location(...)` 一次 | `brain/agentfarm/farmwork.py`（`_neighbour_to_walk`/`_location_failed`/`ensure_location`） | ✅ 探针 D1 `n_calls=2`、`timeouts=[60000, 30000]` |
| 脑侧解析 Mod 回执 | `_WARP_SOURCE_RE`/`_REMAINING_STEPS_RE`/`_warp_source_of`/`_remaining_steps_of` | 同上 | ✅ 有专门用例 `test_receipt_parsers_read_the_real_machine_wording` |
| 卡面"没实现"项 | 无 | — | ✅ 全部落地 |
| 卡面"多做" | `bridge.py:620 move_to_location(timeout_ms=60000)` 默认值、失败 reason 带 Mod 原文 + 脑侧现场（都是本卡必需） | — | ✅ 未发现无关改动 |

**注意（NIT-4）**：Mod 侧（`StepMover`/`MoveToLocationSkill`/`ShipSkill`）**没有 C# 测试工程**，作者在类 docstring 里自认"由 build + 真机验收"。⇒ 装机后必须用真机确认回执措辞与新解析器一致（`单跳预算 …ms，剩余 N 步未走完`）。

---

## §3 task-42（经济闭环 `sell`/出货箱）逐条对账

| 卡面要求 | 实现（我独立 grep/read） | 结论 |
| --- | --- | --- |
| **零 `Money` 写入** | `mod/AgentFarm.Bridge/ShipSkill.cs` 全文只有 `:177` 与 `:206` 两处**读** `Game1.player.Money`；无 `Money +=`/`Money =` | ✅（与 Lead 的 `git grep` 一致） |
| 只调 public `Farm.shipItem(Items[slot] 那个实例, player)` | `:114 Item item = items[slot];` → `:185 farm.shipItem(item, Game1.player);`（docstring 说明"引用相等"必须用槽位） | ✅ |
| 白名单空 ⇒ 一件不卖 | Mod：`:122 allow == null \|\| allow.Length == 0 ⇒ not_whitelisted`；脑：`sellable_slots` 白名单空 ⇒ `[]`、`sell_loot` 直接返回空列表 | ✅ 探针 B1：`sell_calls=[]`、`bin=[]` |
| 拒绝链 | `no_save`(:94)/`bad_args`(:103,:110)/`empty_slot`(:116)/`not_whitelisted`(:122,:138)/`not_sellable`(:145)/`quest_item`(:152)/`big_craftable`(:159)/`empty_stack`(:164) | ✅ |
| **判据 = 槽位空 + 箱件数变化** | 实现只用**槽位空**：`:196 slotEmpty`，`:213-220` 不空 ⇒ `Fail("sell_no_effect")`；箱件数只在 `:211` 的 reason 里 | ⚠ **NIT-1（弱一档）** |
| 脑侧不吃回执 | `farmwork.sell()` 判据 `:1346 if (not still) and n_after < n_before:`，失败 `:1358-1362` 带 Mod status；白名单跟随剩余量 `:1351-1356` | ✅ 探针 A |
| `sell_loot` 有界 | `:1365-1380`：`max_items=24`、每件重新 observe、**第一件失败即停**、空手不产生动作 | ✅ |
| 钱当天不变是正常 | 脑 `sell()` reason/`_ship_loot` note 都写"钱要等下一次 NewDay 才由游戏结算" | ✅ |

**NIT-1（建议装机前补一行）**：`mod/AgentFarm.Bridge/ShipSkill.cs` 已观测 `before/after` 的箱件数（`:211` 写进 reason），但**没参与判据**。卡面 rev3 明确要求"槽位空 **+ 箱件数变化**"。风险：`shipItem` 把槽位清空却没真进箱（游戏侧异常）会被记成 ok。建议把 `afterBin != beforeBin` 也纳入成功条件（或至少在 reason 里断言变化数 > 0）。

---

## §4 脑侧契约 + `tools/verify-run3.py` 逐字段对账

* 字段链（逐段核对无漂移）：`Contracts.cs` 顶层 `shippingBin{present,count,items,lastItemShipped,separateWallets}` + `ExecArgs.slot` + `ExecArgs.sellWhitelist` → `WorldSnapshot.ReadShippingBin()`（**主线程现读** `Game1.getFarm().getShippingBin(player)`，不进后台 FarmView 缓存）→ `brain/agentfarm/bridge.py:809 sell(slot,*,whitelist,timeout_ms=8000)` → `farmwork.sell/sell_loot` → `longrun._plot_brief` 注入 `Brief.sellable` → `longrun._ship_loot` journal `sell{ok,code,slot,qid,stack,before,after,reason,receipt}` / `sell_failed{reason,code}` → `planner.deterministic_plan` 出 `ship` 意图。✅
* planner 排序 `unwatered(water_area) → ripe(harvest) → sellable>0(ship) → blockers(clear) → till → plant` ✅ 与卡面"干作物仍优先"一致（用例 `test_dry_crops_still_outrank_shipping`）。
* **工具对账结论（NIT-3）**：`tools/verify-run3.py` 对 `sell|ship|shippingBin` **零命中**；`tools/analyze-longrun.py` 的 `sell|ship` 只命中 `:777` 一句无关 IL 注释 ⇒ 两个工具**都不读**出货字段。因此**不存在字段漂移**（工具不解析也就不会误判），但代价是：**经济闭环对账本检查器完全不可见**（`sell`/`sell_failed` 不进任何判据，也不进 analyzer 的桶统计）。按 v3 limits 文档的口径这是"未覆盖面"，建议在 `docs/_verify-run3-limits.md` 补一行；真机验收要靠 `shippingBin.count`/money 的**独立观测**（不是账本自述）。

---

## §5 对抗抽检（我自己跑的，未复用作者断言）

### 5.1 探针 `scratch/_t44_probe.py`（exit 0；原始输出存档 `scratch/_t44_probe_out.txt`）

| 场景 | 实测原文（节选） | 结论 |
| --- | --- | --- |
| A 回执 ok 但世界一动不动（`sell_mode=no_effect`） | `ok=False code='failed' reason='出货没有生效（槽位 0 的 (O)24：背包 1→1，槽位仍有该物品）'`、`shipping_bin=0`、`harvested_after={'(O)24': 1}` | ✅ 回执不算成功 |
| B1 白名单空 | `sellable_slots=[] sell_loot=[] sell_calls=[] bin=[]` | ✅ 一件不出、**一次请求都不发** |
| B2 非白名单（镰刀 + 白名单 `["(O)24"]`） | `ok=False reason='…；Mod status=not_whitelisted'`、`receipt='not_whitelisted: [not_whitelisted] (W)47 不在白名单里'`、背包不动、`bin=[]` | ✅ |
| C1 收获且背包变多 | `harvested={'(O)24': 1}`、`reason='作物已收走（crop 变空）；进背包：{'(O)24': 1}'` | ✅ |
| C2 只摘下来、背包没多 | `harvested={}`、`reason='…；⚠ 背包没有新增物品（收货可能丢了，不能出货）'`、`sellable=[]` | ✅ 不凭空生成可卖物 |
| D1 两段式救回 | `ok=True`、`timeouts=[60000, 30000]`、`n_calls=2`、`moves=[[64,13]]`、`reason='已到 FarmHouse（两段式救回：…）'` | ✅ |
| D2 两次都失败 | `ok=False code='failed' inconclusive=True n_calls=2`、reason 含 `剩余 52 步未走完`/`Mod 报的 warp 源格 (64, 14)`/`脑侧现场：人在 (64, 13)（Farm）` | ✅ 有界且如实 |

### 5.2 我自写的变异矩阵 `scratch/_t44_falsify.py`（副本 `scratch/_t44_mut/agentfarm`，先预导入副本包绕开 `tests/test_farmwork.py:22` 的 `sys.path.insert(0, brain)` 劫持；每次打印 `USED_MODULE` 确认命中副本）

| mode | 注入的 bug | run | 红在哪条用例 | 结论 |
| --- | --- | --- | --- | --- |
| none | — | 13 | 0 | 对照 |
| m1 | `sell()` 判据恒真（只看回执） | 6 | `test_ok_receipt_without_world_change_is_never_ok`、`test_not_whitelisted_is_reported_with_status_and_receipt`、`test_sell_loot_stops_at_the_first_failure`（`24 != 1`） | ✅ 用例能证伪 |
| m2 | `_loot_delta` 里 `if d > 0` 改成恒真 | 6 | **0** | ⚠ 覆盖缺口（NIT-2） |
| m3 | 砍掉两段式接近 | 7 | `test_timeout_is_recovered_by_two_phase_approach`、`test_both_attempts_failing_is_bounded_and_honest` | ✅ |
| m4 | 脑侧默认预算退回 30000 | 7 | `test_default_request_budget_is_sixty_seconds`（`30000 != 60000`）、`test_timeout_is_recovered_by_two_phase_approach`（`[30000, 15000] != [60000, 30000]`） | ✅ |
| m5 | `sellable_slots` 不再按白名单过滤（工具也敢选） | 68 | **0** | ⚠ 覆盖缺口（NIT-2） |
| m6 | `_ship_loot` 恒 `return True` | 3 | `test_failed_ship_is_journalled_and_never_blocks_the_day` | ✅ |
| m7 | 丢掉 `sell_failed` 记账 | 3 | 同上（`0 != 1`） | ✅ |

变异只写 `scratch/_t44_mut/`，跑完 13 个在制文件字节未变（比对 SHA256）。

---

## §6 NIT 清单

| # | 现象 | 位置 | 建议 | 阻塞装机？ |
| --- | --- | --- | --- | --- |
| NIT-1 | 出货判据只有"槽位空"，缺卡面要求的"箱件数变化"（箱件数只进 reason） | `mod/AgentFarm.Bridge/ShipSkill.cs:196`/`:211`/`:213-220` | 把 `afterBin != beforeBin` 纳入成功条件（一行） | 否（建议补） |
| NIT-2 | 两条属性无测试能证伪：`_loot_delta` 的 `d > 0` 过滤；`sellable_slots` **内层白名单过滤**（白名单非空但背包里混着工具/种子时只应选出白名单槽位） | `brain/agentfarm/farmwork.py:1258-1266`、`:1272-1294` | 补 1 条"混合背包只选出白名单槽位"用例（m5 的后果链：工具在 slot 0 ⇒ Mod `not_whitelisted` ⇒ `sell_loot` 第一件失败即停 ⇒ 合法收获永远出不了货） | 否 |
| NIT-3 | 经济闭环对 `tools/verify-run3.py`/`analyze-longrun.py` 完全不可见（零命中） | `tools/` | 在 `docs/_verify-run3-limits.md` 记"未覆盖面"；真机验收用独立观测的 `shippingBin.count`/money | 否 |
| NIT-4 | Mod 侧新增逻辑无自动化回归（无 C# 测试工程），`build + 真机` 是唯一防线 | `mod/AgentFarm.Bridge/*.cs` | 装机后用真机确认 `单跳预算 …ms，剩余 N 步未走完` 措辞与 `_REMAINING_STEPS_RE` 一致 | 否（装机后必做） |
| NIT-5 | 基线口径：真实基线 **328**、新增 **+18**（不是 335/+11） | 本报告 §1 | 同步 task-44 卡面与发布说明 | 否 |

---

## §7 越界与纪律

* 我未改 `brain/`、`mod/`、`tests/`、`tools/`、`docs/00-开发日志.md`，未 bump，未 deploy；写盘只有 `docs/_review-e818195.md` 与 `scratch/_t44_*`。
* 未碰游戏/桥（未 observe/未 quit/未 load_save）。machine-runner 侧活动不涉及本次验收。
* 14 个提交文件全部能映射到 task-43/task-42 或其测试/发布说明，未发现无关改动。

## §8 结论

**PASS-WITH-NITS，无必修项。**
task-43 的跳预算/续跳/有界性与卡面 rev3 逐条一致（Mod 侧 `StepMover.Tick` 顺序、`StuckFrames=180`、`ExtensionMs×8`、`HopBudget` 不超整体剩余；脑侧两段式只重试一次且有界记账）；task-42 的铁律（零 `Money` 写入、只调 `shipItem(Items[slot] 实例, player)`、白名单空一件不卖、不吃回执）全部成立，我用 7 个对抗场景 + 8 个变异独立复现；脑侧契约与 `verify-run3.py` 无字段漂移（该工具根本不读出货字段）。
NIT-1（判据缺"箱件数变化"）建议装机前顺手补；NIT-2 是两条无人证伪的属性，建议补 1 条混合背包用例。⇒ 可以装机跑真机验收。

---

## §9 Lead 裁定（验收后，记录用）

* **NIT-1 + NIT-2 → task-46**（`blocked_by: task-45`，run5 跑完才准动工——run5 正在用冻结版跑，改 `brain/` 会让证据版本说不清）。
  NIT-1 修法由 Lead 定为**脑侧**：`farmwork.sell()` 的 `ok` 判据加"`shippingBin.count` 增加"，`count` 没变 ⇒ 不算成功（`ShipSkill` 不判自己成功，不懂 `mod/`）—— 与 v0.7.17"回执说成功而世界没变"同类。
* **NIT-5 采纳**：基线口径写 `328 + 18 = 346`（`e818195^` 188 → HEAD 206，`def test_` +18 / 0 删除），日志改正，不写"335 + 11"。
* **NIT-3 / NIT-4 记为已知局限**；NIT-4（装机后真机确认新超时措辞）由 task-45 的真机验收覆盖。
* 0.7.24 已冻结（`ff25ee7`）并装机成功（`modVersion=0.7.24`）；machine-runner 按 task-45 做真机验收 + run5。

