# 0.7.28 发布 / 验收计划（run9）

> 起草：2026-10-15 22:35（Lead）。状态：**未冻结**（等 task-102 交付 + task-103 对抗验收 PASS）。
> 上游：`docs/_release-0.7.27.md`（0.7.27 已装机并跑出 run8，证据见 `docs/_run8-evidence.md`、开发日志条目 053）。

## 1. 本版内容（卡片即权威）

| 卡 | owner | 内容 | 状态 |
|---|---|---|---|
| **task-102** | dev-coder | **A 经济闭环空格死锁**（`no_space` 独立结果 + 当天 ≤3 次；`seeds_total==0 && money>=seed_price && free_slots==0` ⇒ 整叠卖一叠盈余材料腾格，白名单、不碰种子/工具/武器/建材；buy 前清残留模态；优先当季在售买得起的种子）+ **B 早睡防线**（钱够买不到/农场有干作物时 `sleep_guard` 不许放行；不许 0 动作收工；`goto_farm` 遇模态先清一次再重试） | in_progress |
| **task-103** | deputy-lead | 对 task-102 的独立对抗验收（空格死锁复现 FAIL→PASS、腾格卖出不得碰种子/工具/K、跨天重试有界性、`no_space` 谎报成功、睡前后模态 fail-closed） | pending（`blocked_by task-102`） |
| **task-101** | 待派 | 0.7.28 候选 NIT：`_farm_totals` 类型校验（`"abc"` 会抛 `ValueError` 穿出整天）、窗口全死苗的 `watered_outdoor` 字段级收口、`-1` 自相矛盾、夹具 `farm_scan()` 死苗口径 | pending |

**可选并入**：task-101 是否随本版一起冻结由 Lead 在 task-102 验收后决定（若并入，需先派 owner 并过独立对抗验收或至少逐条复现）。

## 2. 冻结与装机九步（Lead 独占，链式，不许并行）

1. `team_task_get task-102` 确认已 completed；`task-103` PASS 或 PASS-WITH-NITS（无必修）。
2. 确认 `tools/_note-0728.txt` 存在且**首串是 `v0.7.28`**（列本版卡片）。
3. `python tools/_bump-mod-version.py 0.7.28 --note-file tools\_note-0728.txt`（⚠️ cp1252 下末句 print 会 `UnicodeEncodeError` 且退出码 1，但**版本已写盘** ⇒ 一律用 `json.load` 核对 `manifest.json` 的 `Version`）。
4. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.28"`。
5. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ 0 警告 0 错误；记下 `AgentFarm.Bridge.dll` / `manifest.json` 的 B 与 mtime。
6. `git add -A` → 提交（**先提交再 check-release**：它要求工作树干净，未跟踪 `scratch/*.py` 也算脏）。
7. `python tools\check-release.py --expect 0.7.28` ⇒ 须全绿（含全量单测 `Ran N tests / OK`）。
8. `python tools\deploy-mod.py --no-quit` ⇒ 装机 + 读档；记下桥 `modVersion=0.7.28 port=17890`。
9. `python tools\preflight.py --expect 0.7.28 --save-baseline logs\run9-baseline.json` ⇒ 四绿（版本/已读档/在户外农场/无阻断模态）。

## 3. 起跑（machine-runner，task-89 家族）

```
python tools\start-detached-longrun.py ^
  --journal logs\longrun-3day-llm-run9.jsonl ^
  --expect-version 0.7.28
```
- 起跑前 `python scratch\run8-snapshot.py --tag start --expected-mod-version 0.7.28`（脚本沿用，输出 `scratch/run9-external-snapshots.jsonl`；PID 候选 `logs/run9.pid`）。
- 结束后立刻 `--tag end`，**先别退游戏**（Lead 要 live observe 对账），再写 `docs/_run9-evidence.md`。
- 现场政策不变：`ui.eventUp=true` ⇒ **立即停手等人**（task-41）；不替游戏做选择。

## 4. run9 验收判据（继承 0.7.27 + 本轮新增四条）

继承：尾部窗口 N=3 全 VERIFIED（`tools/verify-run3.py`，并**并列严格整本第二判决**）；四腿覆盖（clear/till/plant/water 至少各有成功步）；`watered_outdoor` 只在 farm 证据可用时算数；`no_work` ⇒ `final_water.dry==0`；`dry_dead` 不得污染浇水判据；跨日 `day_after` 恰 +1；SMAPI 外部证据（`NewDay` / `before save` / `SaveGame.Save() called.`）。

**本轮新增（run8 病灶的对偶判据）**：
- **N1 每天必须有农场动作**：任何 `ended_by=="sleep"` 的日子，`ok_steps >= 1`（0 动作收工 ⇒ 必须记 `slept_without_work` 且 `verified=false`）。
- **N2 经济闭环四步留痕**：`sell`/`surplus_sell`（卖出）→ 次日 `day_start.money` 增加（到账）→ `buy` 成功（当季种子）→ `sow`/`plant_area` 至少 1 格成功；四步缺一即在该日 evidence 里点名。
- **N3 无空格死锁**：同一天 `buy` 尝试 ≤3、`no_inventory_space` 后不再重试；若因背包满，必须出现 `surplus_sell{why:"need_slot"}`。
- **N4 跨日与落盘**：每个 `day_after` 恰 +1；落盘缺口必须能用"日终菜单链（`ShippingMenu`/`SaveGameMenu`）"解释，否则记红。
- **N5 死苗证据不许"真空通过"**：run8 全程 `farm.deadCrops=0`/`dryDeadCrops=0`/`day_end.dead_crops=0` ⇒ task-84 的死苗路径在真机上**仍是真空未验**（见 `docs/_run8-evidence.md` §4.3 ③）。run9 若同样没有死苗，evidence **必须明写"本轮无死苗 ⇒ 该判据真空，不算通过也不算失败"**；想真正验到它需要跨换季（下一次换季 = 秋1日，距今约 15 游戏日）或另设针对性场景 —— 记为后续 run 的必验项。

## 5. 与 run8 的对比基线

| 项 | run8（0.7.27） | run9 期望 |
|---|---|---|
| 尾部连续 VERIFIED | **0/3** | **3/3** |
| 自主卖出 | ✅ 1 次（Fiber 174 ⇒ 钱 14→188） | ✅ 至少 1 次 |
| 自主购买 | ❌ 26 次尝试 0 成交（`no_inventory_space`×25） | ✅ 至少 1 次成交（当季种子） |
| 自主播种 | ❌ 0 格 | ✅ ≥1 格 |
| 0 动作收工 | ❌ day 12（8 秒就睡） | ✅ 0 次 |
| 假 VERIFIED | ✅ 0 次（fail-closed 生效） | ✅ 0 次 |

## 6. 遗留（不进本版）

- task-83 rev2（田块规整：坐标级留痕 `sow_step`/`till_step` + `plant_layout.tiles` 坐标 + 五指标）—— 需要 run9 的数据才有意义。
- task-82/58/59（LLM 反馈/自省：决策→结果 join + `<journal>-lessons.json`）、task-14（逐帧 warp 活锁）、task-18（职业选择耕种优先）、task-53（农场级待清/待垦计数）、task-98。
- Mod `ShipSkill` 只能整叠出货 ⇒ 每 id 保留 K=10 做不到（详见条目 053 待决②）。
