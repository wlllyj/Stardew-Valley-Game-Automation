# 0.7.34 发布计划 — harvest 三处真相修正（task-176）+ 同格复测（task-177）

> 起因：task-173 在 **0.7.33** 上对固定样本 `(60,29)` 做定点 harvest = **FAIL**（`docs\_run10-harvest-verify.md`、`scratch\run10-tile6029-{before,after}.json`）。
> 证据链（全部为观测差分）：Mod 回执 `{acted:true, ok:true, status:"ok", skill:"interact", worldSeqBefore:51, worldSeqAfter:51}`，而 `farm.readyCrops 102→102`、`(60,29).crop "270"→"270"`、背包 **+0**、存档 `4310486 B / 2026-10-17 05:04:35.296` **逐字节未变**、SMAPI `NewDay 0→0 / save_called 0→0`。
> 三条线索：**缺陷 A**（`harvestMethod` 缺键 ⇒ `harvest_tool()` 恒 None ⇒ 只能 `interact`，而镰刀类作物 `interact` 永远摘不到）、**缺陷 B**（`ready` 的字段兜底 fail-open：`fullyGrown=false` 却 `ready=true` ⇒ `readyCrops == crops == 102`）、**混杂**（背包 12/12 全满，run8 `no_inventory_space` 同病灶）。

## 1. 本批卡片（入版范围）

| 卡 | 负责 | 内容 | 状态 |
|---|---|---|---|
| **task-176** | dev-coder | P0：三处真相修正 —— ①`harvestMethod` 正确来源（先 api-probe）+ **必须输出键**（拿不到写 null）②`Ready()` 反射不可用 ⇒ `null`（不许宽松字段兜底当 true）+ 新增 `readySource ∈ {"game","fields",null}` ③`acted` 由可独立观测的变化推导（拿不准 ⇒ `false` + `status="no_action"`） | in_progress |
| **task-177** | machine-runner | 0.7.34 上同格复测：字段核对 → 受制裁腾格 → 同格 `harvest` → （必要时）镰刀路径 → 对照格；交付 `docs\_run10b-harvest-verify.md` | pending（blocked_by task-176） |
| **task-178** | deputy-lead | task-176 的独立对抗验收（≥6 条作弊通道 + 自建变异 + 全量回归 + "0.7.34 能否冻结"结论） | pending（blocked_by task-176） |

**不入版（另排）**：task-174（`day_end.final.farm` 白名单补 `ripeCrops`/`readyCrops`）、task-175（`harvest_gave_up` 窗口依赖收紧路线）、task-168（`reduce_scope` 收缩策略，仍冻结设计稿）。

## 2. 冻结九步（Lead 独占执行，链条冻结后一次做完）

1. `tools\_note-0734.txt` 存在且**首串**为 `v0.7.34`，列出本批内容（task-176）。
2. `python tools\_bump-mod-version.py 0.7.34 --note-file tools\_note-0734.txt` ⇒ `mod\AgentFarm.Bridge\manifest.json` 的 `Version` 0.7.33→0.7.34、`Description` 头部插入 note。
3. `brain\agentfarm\bridge.py:39` 的 `MOD_VERSION_EXPECTED = "0.7.34"`（注释里补 v0.7.34 条目，历史条目保留）。
4. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警告 0 错误**；记录 dll 字节数。
5. `python -m unittest discover -s tests` ⇒ 必须 **"Ran N tests / OK"（0 红）**。
6. `git add -A` 后提交（冻结提交）——`tools\check-release.py` 把未跟踪的 `scratch/*.py` 也算脏。
7. `python tools\check-release.py --expect 0.7.34` ⇒ **六项全绿**（manifest==brain、版本==期望、dll 比源码新、`py_compile`、全量测试、工作树干净）。**顺序纪律：先提交再 check。**
8. `python tools\deploy-mod.py --no-quit` ⇒ 装机 0.7.33→0.7.34；`observe` 里 `modVersion=0.7.34`。
9. `python tools\preflight.py --expect 0.7.34 --save-baseline logs\run10-baseline.json`（若沿用旧基线名则写 `logs\run10b-baseline.json`）⇒ 四项全绿；随后给 machine-runner 发 GO（附五文件 SHA256 + argv 供逐字比对）。

## 3. 同格复测判据（task-177）

- 修复生效 = 下列任一：①`(60,29)` 的 `crop` 变空 / `ready` 转非 true ②背包 +N 或地面掉落可见 ③`farm.readyCrops` 减少 ④Mod 回执 `acted` 与 `worldSeq` 一致（且世界确有变化）。
- 混杂排除 = 第 2 步腾格后 `inventoryCount < 12` 再摘；若腾格后仍摘不到且步骤 4 的镰刀路径成功 ⇒ 定案为镰刀类作物 + `harvestMethod` 修复生效。
- 缺陷 B 验证 = `(60,28)` 这类"`fullyGrown=false` 却 `ready=true`"的格，修复后应为 `ready=false` 或 `null`，且**不再进收获目标池**。

## 4. 已知风险 / 未决

- `harvest_gave_up` 的窗口依赖部分豁免（task-175 NIT-1）**不在本批**；若复测期间观察到"放弃格离窗 + `farm.readyCrops>0` 仍 `verified=true`"，如实记录并报 Lead。
- 若 task-176 修复后 `readyCrops` 骤降为 0（反射失败导致全 null），那就是**从 fail-open 变成 fail-closed 过头**：脑侧会整天不摘 ⇒ 同样要报，不能静默接受（判据：`readySource=null` 的格占比 > 0 且当天 `farm.crops > 0` 时必须有 `harvest` 的【无法判定】记录）。
- `acted` 语义变化会影响 `use_tool`/`plant`/`interact` 三条既有路径 ⇒ 回归必须覆盖旧路径（`tests/test_farmwork.py`/`test_longrun.py` 全绿为硬要求）。

## 5. 执行记录（逐步追加）

- 待填。
