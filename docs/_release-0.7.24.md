# 0.7.24 发布计划（草稿 · Lead 独占）

> 目的：把 **P3 ⑥ 的最后一块拼图**补上 —— **经济闭环**（收成 → 出货箱换钱 → 买种子 → 再种）。
> 现状（2026-10-13 夜）：run3 暴露的"睡醒在屋里"真 bug 已修（`cc2988e`，321 OK），run4 正在跑；
> 但存档只剩 **14g / 0 种子**，所以"播种"这一环在真机上**没有目标可打**（task-9 口径：没种子不盲目开垦）。
> 0.7.24 就是让脑能自己把钱挣回来。

## 1. 冻结判据（与 0.7.22/0.7.23 同口径）

1. 没有人在改 `mod/` 或 `brain/` 源码（`git status --short` 对这两个目录干净）。
2. `dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警告 / 0 错误**。
3. 全量 `python -m unittest discover -s tests` ⇒ **OK**（基线 **321**，只许升不许降）。
4. deputy-lead 对每张卡的完整验收 = **PASS**（或 PASS-WITH-NITS 且无必修）。
5. `python tools\check-release.py --expect 0.7.24` 四项全绿（**先提交再 check** —— 这是 0.7.23 踩过的坑）。

## 2. 装机内容（候选，按可行性排序）

### 必装：task-24 出货箱卖货闭环（`docs\_il-sell-path.md` 的**路 B**）
- **Mod**：
  - `FarmView` 加 `shippingBin[]`（`{slot, id, name, stack}`，数据源 `Farm.getShippingBin(player)` / `lastItemShipped`）—— 出货当天**唯一的可判定证据**（钱要次日才到账）。
  - 新技能 `ship`（`Skills.Create` 的 switch + `KnownSkills` + `BridgeHost.IsLongTaskSkill`）：入参复用 `ExecArgs.Item`（+ 可选 `slot`）；执行 = 取 `Game1.player.Items[slot]` **那个实例**（绝不用 `getOne()` 副本）→ `Game1.getFarm().shipItem(instance, Game1.player)` → 回执写清"整叠出货 / id / 名称 / 堆叠 / 是否 `showShipment`"。
- **brain**：`farmwork.ship(item_id, *, slot=None) -> StepResult`（判据 = 背包该格 stack 减少/消失 **且** `farm.shippingBin[]` 出现该物；`money` 当天不变属预期，reason 写明"次日 NewDay 结算"）；策略层白名单纯函数（**不出**工具/武器/种子/建材；**可出**收获物与明确重复的无用品）+ 单测；接入 `longrun.py` 的 review/收工前。
- **三条 IL 硬约束（违反会复制/丢失物品）**：①必须传背包里的实例（`Items.IndexOf` 是引用相等）；②整叠出货；③非 `Object`（工具/武器）出货 = 0 钱 + 物品消失 ⇒ 白名单必须挡。
- **绝不自己写 `player.Money += …`**（v0.7.17 同类事故）。

### 可选（赶得上就并，赶不上留 0.7.25）
- **task-14**：`ensure_location` 逐帧 warp 活锁的修复（planner-dev task-27 已交付 `docs\_il-warp-loop.md`，方向是"传送期间摘掉 `PathFindController`"）。它影响 run3/run4 里"第一次回家失败"的概率，**不影响 3 天连绿本身**。
- **task-17**：`world_stuck` 自愈（脑侧为主）。
- **task-20**：工具等级可观测（`axeLevel/pickaxeLevel/hoeLevel`）+ `ResourceClump` 的 `toolRequired/toolLevelRequired`，让"等级不够不白挥"有真凭据。
- **不并入**：task-18（职业选择自动化，需要不可逆操作的真机验证）、task-13（防御性加固）、task-26/29/30（已落地）。

## 3. 发布流程（13 步，沿用 0.7.23）

1. 写 `tools\_note-0724.txt`（manifest 说明，中文单行由 `tools\_bump-mod-version.py` 定点插入）。
2. `python tools\_bump-mod-version.py 0.7.24 --note-file tools\_note-0724.txt`。
3. 改 `brain\agentfarm\bridge.py:39 MOD_VERSION_EXPECTED = "0.7.24"`（注释列本版内容）。
4. `dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ 0/0。
5. **先 `git commit` 再** `python tools\check-release.py --expect 0.7.24`（否则"未提交"报红）。
6. `python tools\deploy-mod.py`（Lead 独占；装机 → 优雅退出 → 启动 → health → `load_save`）。
7. `python tools\preflight.py --expect 0.7.24 --save-baseline logs\run5-baseline.json` ⇒ 必须 **exit 0**。
8. `python -m agentfarm goto Farm`（读档后在室内，先走到农场）。
9. machine-runner 起跑：`python -u tools\run-longrun.py --days 3 --size 5 --max-minutes 150 --max-days 9 --journal logs\longrun-3day-llm-run5.jsonl`。
10. 跑完 `python tools\verify-run3.py --journal <同一本>` + `python tools\analyze-longrun.py --journal <同一本>` 双复核。
11. `python scratch\run3-lead-check.py --journal <同一本>`（存档 mtime/size、SMAPI NewDay/SaveGame、`day_after` 链）+ `docs\_run5-evidence.md`。
12. `python tools\stop-game.py`（m02833）。
13. `docs\00-开发日志.md` 落条目 + 提交。

## 4. run5 的验收口径（比 run4 **多两条**）

- 同 run4：尾部连续 3 天 `ended_by=="sleep"` 且 `verified==true`、`checks.day_justified==true`、0 掉线/崩溃、exit 0；每天 `day_end.final.location == "Farm"`。
- **新增 ①经济闭环可核查**：至少一次 `ship` 成功（背包 stack 减少 + `farm.shippingBin[]` 增加），且**次日** `money` 增量 == 该物 `sellToStorePrice(-1) × stack`（两个快照的 `day`/`timeOfDay` 都要贴）。
- **新增 ②四步全链**：至少一天里同时出现 `clear_area`（清障 ok>0）、`till_area`（开垦 ok>0）、`plant_area`（播种 ok>0，`crop` 出现）、`water_area`（浇水 ok>0）—— 这才是 P3 ⑥ 原话的"清障→开垦→播种→浇水"。

## 5. 回退

- 装机旧文件留 `.bak-<ts>`（`tools\deploy-mod.py` 自带）；`manifest.json` 与 `bridge.py:39` 必须成对回退。
- 存档不参与回退（`save-backups/` 有备份）；**不许重启续跑**，失败就另起 run6 并说明。

## 6. 执行记录（dev-coder，2026-10-13 夜；装机章由 Lead 写）

### 6.1 task-43 长路径跳预算（run4 唯一硬卡点：田里回不到屋门口）
- **Mod**：`MoveToLocationSkill.cs` —— 跳预算公式 `Clamp(4000 + 500×剩余步数, 8000, 门 30000 / 普通 20000)`，且**不超过整体剩余时间**；`Begin()` 用 A* 真实剩余步数重算并 `RaiseBudget`（发出去之后才知道步数，所以只能"先给下限、随后抬高"）；`ClampBudget` 上限 **60000**；超时文案带「单跳预算 Nms / 剩余 N 步」便于事后对账。
- **Mod**：`StepMover.cs` —— `RaiseBudget`；`StuckFrames` 90 → **180**（≈3s）；`Tick` 判定顺序改为「进展证据 → 超时+**续跳** → 模态 → 卡死」：只要玩家格变了或像素位移 >4f 就清零卡死帧，超时可续（`ExtensionMs = 8000`，最多 8 次）⇒ **有进展就绝不算失败**，只有真正 ~3s 不动才 `blocked`。
- **Mod**：`Skills.cs` —— `ClampTimeoutFor` 对 `move_to_location` 走 `MoveToLocationSkill.ClampBudget`（否则内部仍被 30s 卡住，传 60000 无效）。
- **brain**：`farmwork.ensure_location` 默认 `timeout_ms=60000` + **两段式**（解析回执里的 `warp 源格 (a,b)` 与 `剩余 N 步` → 先 `move_to` 到源格的可站四邻 → 只重试一次）；`bridge.move_to_location` 默认 60000。
- **单测**：`tests/test_farmwork.py::TestTask43LongPathRecovery`（7 条：两段式救回 / 默认 60000 / 两次都超时有界且如实 / 无源格不硬猜 / 四邻优先级 / 全堵则放弃 / 回执逐字解析）。
- **读数**：`dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo` ⇒ **0 警告 0 错误**；全量 `unittest discover -s tests` ⇒ **346 OK**。
- **已知缺口（装机前请知悉）**：仓库**没有 C# 测试工程**（只有 `AgentFarm.Bridge.csproj` 与 `scratch/`、`tools/` 探针工程）⇒ 卡面 §5 里"预算数值/续跳"三条无法用单测覆盖，只能靠 build + 真机三连命令验收；脑侧契约（回执解析、默认 60000、有界两次）已用 Python 用例钉死。真机验收建议照 Lead 的三连：`goto Farm` → `move 47 29 --timeout-ms 30000` → `goto FarmHouse`（应 20–30s 内 ok）。

### 6.2 task-42 经济闭环（收成 → 出货箱 → 次日到账）
- **Mod**：新增 `ShipSkill.cs`（单 tick 同步技能，**不加入** `BridgeHost.IsLongTaskSkill`）：入参 `slot` + `sellWhitelist`（**白名单为空 ⇒ 一件不卖**）；只调 **public** 的 `Farm.shipItem(item, Game1.player)`，传的是 `Game1.player.Items[slot]` **那个实例**（`removeItemFromInventory` 用引用相等，传 `getOne()` 副本会变成"原物不动、副本进箱"次日多拿一份钱）；判据 = `Items[slot] == null` 且箱子件数/lastItemShipped 变化；**绝不碰 `player.Money`**。
- **Mod**：`Contracts.cs` 新增顶层 `ShippingBinView{present,count,items,lastItemShipped,separateWallets}` + `ExecArgs.slot/sellWhitelist`；`WorldSnapshot.cs` 新增 `ReadShippingBin()`（主线程当帧真值），**刻意不塞进 `FarmView`**（那个读后台扫描线程缓存，会陈旧）。
- **brain**：`bridge.sell(slot, whitelist=…)`；`farmwork` 新增 `harvested` 白名单（`harvest()` 按**背包差分**记账：只摘下来而背包没多 ⇒ 不进白名单）、`sellable_slots()`/`sell()`/`sell_loot()`（判据 = 槽位不再有该物 + 该 qualifiedId 总数下降；钱当天不变属**预期**）；`planner`：`Brief.sellable`（不是观测推出来的，由控制器注入）+ `TASK_KINDS` 加 `ship`，确定性顺序变为 `wait_for_save → 体力 → water → harvest → **ship** → clear/till/plant → review`；`longrun`：`_plot_brief` 注入 sellable、`_execute` 接 `ship` → `_ship_loot`（journal `sell`/`sell_failed`，note 写明"钱要等下一次 NewDay"）、日重置 `reset_harvested()`。
- **单测**：`tests/test_farmwork.py::TestTask42Sell`（6 条）、`tests/test_longrun.py::TestTask42Ship`（3 条）、`tests/test_planner.py` 两条（ship 优先于开垦/播种、干作物仍优先于 ship）。
- 全仓 `git grep -rn "Money +="`：**只有注释与文档命中，没有任何一处写入**。
- **与 §2 的差异（如实说明）**：§2 设想复用 `ExecArgs.Item` 传物品 id；实际改成 `slot` + 白名单 —— 因为 `removeItemFromInventory` 是引用相等，按 id 反而容易复制物品。另外 `shippingBin` 放在 `WorldSnapshot` 顶层而非 `FarmView`（见上）。
- **P3 装机后建议核三条**：①`farm.shippingBin.count` 差分与 `player.inventory[].slot` 变空；②**次日** `money` 增量 == 该物 `sellToStorePrice(-1) × stack`（两个快照的 `day`/`timeOfDay` 都要贴）；③白名单负例：工具/种子槽必须回 `not_whitelisted`（用 `--whitelist` 只给收获物）。
