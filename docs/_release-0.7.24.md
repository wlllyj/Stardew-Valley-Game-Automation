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
