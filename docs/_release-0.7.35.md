# 0.7.35 发布计划 — 再生作物收获真相（task-181/182）+ 规模取舍（task-168）+ 护栏加固（task-180）

> 立卡时间：2026-10-17（Lead）。来源：task-177 真机复测（`docs\_run10-harvest-verify-0734.md`，machine-runner `f851423`）。

## 0. 为什么有这一版

task-177 在 0.7.34 上对固定样本 `(60,29)` 复测，**排掉了三个混杂**（背包满 = 已排除且是直接原因；`harvestMethod` 缺键 = 已排除；`readyCrops` 没收窄 = 已查清是游戏口径不是 fail-open），同时钉死一条**反向不一致**：

- **世界真的收获成功了**：`readyCrops 102→101`、窗口 `ready==true 86→85`、背包 `(O)270 +1`、该格 `ready true→false`、`worldSeq 60→61`（`crop` 未消失 = `regrowsAfterHarvest=true` 的正常形态）。
- **但脑侧报 `code=failed`、Mod 报 `status="no_action"`**：
  - 脑侧成功判据 = "该格 `crop` 消失" ⇒ 对**再生作物**系统性假阴性 ⇒ **这就是 run A/B「同日同格 284 次 0 成功」的根因**；
  - Mod 的 `acted` 只比格子内 6 个字段，再生作物收后一项不变 ⇒ 把成功报成没动手。
- 附带两条：**loot 记账粒度**（对照格一镰刀连带收 4 格 `+4 Wheat / +2 Hay`，脑侧却说"背包没有新增物品"）、**`player.inventoryCount` 是容量字段**（腾空一格后仍读 12 ⇒ 判"满没满"必须数 `inventory[]` 行数）。

⇒ 0.7.34 **不能**进 A′/B′ 复跑；先修这两条，再并入 task-168（规模取舍）与护栏加固，冻结 0.7.35。

## 1. 本批卡片（入版范围）

| 卡 | 所有者 | 内容 | 依赖 |
|---|---|---|---|
| **task-181**（P0） | dev-coder | brain：`harvest()` 成功判据**四择一**（`crop` 消失 / `ready` 翻转 / 该 qid 背包 +N / `readyCrops` 下降）+ loot 按**逐 qid 背包 diff** 记账 + 背包满用 `inventory[]` 行数；单测 ≥6、变异 ≥3 | — |
| **task-182**（P0） | dev-coder | Mod：`acted` 扩到**跨观测证据**（背包 qid diff / `ready` 翻转 / `readyCrops` 下降 / 原 `TileSig`）+ 新增 `actedEvidence`；CropMeta NIT-1（`which == null` 进 gate）；**GAP-1** 行为化回归（m178b 必须被杀死） | — |
| **task-180** | dev-coder | GAP-2 文档更正（变异⇒用例映射写实测）+ NIT-2 docstring（门/入口 `interact` 的 `acted` 局限） | task-177 ✅ |
| **task-168** | dev-coder | `reduce_scope`（规模取舍）：`Brief` 三字段 + `base_lines()` 预算行 + `deterministic_plan` 新任务 + `<journal>-scope.json` 持久层 + longrun 13 处；**不拔苗**、田区粒度、粘但可释放、conservative 不认输、`scope_shed` 只 info | 设计稿 `docs\_design-task168-scope-shed.md` §7 附录 A |
| **task-183** | deputy-lead | task-181/182 **独立对抗验收**（≥6 条作弊通道 + 自建变异 + "0.7.35 能否冻结"） | 181, 182 |
| **task-184** | machine-runner | 0.7.35 同格复测 `(60,29)`：**脑侧 `ok` + Mod `acted=true/actedEvidence` + 世界证据三者一致** + Scythe 对照格多格 loot 记账 | 183 |
| task-113（改） | machine-runner | **A′/B′ 复跑**（run A = 0.7.35 上的首跑；run B = 拷教训库后的第二跑）⇒ L0–L5 | 184 + 冻结装机 |

**不入本版**：task-175（`harvest_gave_up` 窗口依赖收紧）、task-174（账本 farm 白名单补 `ripeCrops`/`readyCrops`）、目标 1 的经济/工具链（task-141/142/151/152/155）⇒ 0.7.36+。

## 2. 冻结九步（Lead 独占，链条冻结后一次做完）

1. `tools\_note-0735.txt` 首串必须是 `v0.7.35`（列本版 Mod 侧改动：task-182 + task-180）。
2. `python tools\_bump-mod-version.py 0.7.35 --note-file tools\_note-0735.txt` ⇒ `manifest 0.7.34 → 0.7.35`（用 `json.load` 复核）。
3. `brain/agentfarm/bridge.py` 的 `MOD_VERSION_EXPECTED = "0.7.35"`（注释补 v0.7.35 条目，历史保留）。
4. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警 0 错**；记 dll / manifest 字节数。
5. `git add -A` + 冻结提交（工作树必须干净，否则 `check-release` 会红）。
6. `python tools\check-release.py --expect 0.7.35` ⇒ **六项全绿**（含全量单测、dll 不比源码旧、工作树干净）。
7. `python tools\deploy-mod.py --no-quit` ⇒ `0.7.34 → 0.7.35`，桥 `modVersion=0.7.35`，自动读档。
8. `python -m agentfarm goto Farm`（`PYTHONPATH=<repo>\brain`）⇒ `preflight --expect 0.7.35 --save-baseline logs\run10c-baseline.json` 四项全绿。
9. 把**五文件指纹 + argv + 现场读数**发 machine-runner，GO **task-184**。

## 3. 判据（task-184 与 A′/B′）

- **同格复测（task-184）**：脑侧 `ok` **且** Mod `acted=true`/`actedEvidence` 非空 **且** 世界证据至少一条（`ready` 翻转 / 背包该 qid +N / `readyCrops` 下降 / `crop` 消失）⇒ **三者一致**才算通过；出现"世界变了但脑侧 failed"或"脑侧 ok 但世界没变"= **FAIL** + 最小复现。
- **A′/B′**：仍用 `tools\run-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12`；run A = 首跑，run B = 把 A 的 `<journal>-lessons.json` **字节拷贝**后起跑（两跑同构建、argv 只差 `--journal`）；判据 = `tools\verify-run3.py` + `tools\analyze-longrun.py` + `scratch\run9-lead-check.py` 三向 + L0–L5（`tools\compare-runs.py`，L1 用 `hint`/`symptom` 口径 + `lesson_section_present` 双信号）。
- **目标 2 的验收**：连续 5 个游戏日 VERIFIED + 每日 ≥2 份独立观测 + 落盘五/六串配对 + L0–L5 对照；`history_problems` 只是呈现，**尾部窗口**必须零问题。

## 4. 已知风险 / 未决

- **`readyCrops == crops` 仍成立**（102）：这是**游戏口径**（对照格一镰刀真收 4 个 Wheat 证明那些格真可收），不是 Mod fail-open ⇒ 本版**不动**目标池收窄，靠 `harvest_gave_up` 兜底；若 A′/B′ 里出现"整天盯住一格"，再评估。
- **成功判据放宽后的假绿风险**：`ready` 翻转 / 背包 +N / `readyCrops` 下降任一命中即成功 ⇒ 必须防"背包 +N 来自别的动作"。task-181 要求 diff 必须**动作前后**取，且 task-183 有专门作弊通道实测。
- **`acted` 扩权后**：Mod 现在也看全局量 ⇒ 要防"世界变了但与本次动作无关"（例如同 tick 其他系统变化）。要求 `actedEvidence` 如实落来源，脑侧仍以**观测差分**为准。
- **task-168 是行为变更**：`reduce_scope` 会让某些天主动认输（`scope_shed` 只 info、当天如实不 VERIFIED）⇒ A′/B′ 的 `verified_streak` 可能受它影响；判据文档已写明"延后/认输 ≠ 还有活"。
- 时间预算：本版含 4 张实现卡 + 1 张对抗验收 + 1 张真机 + 2 次 5 天长跑，属于本轮最长的一条链。

## 5. 执行记录（逐步追加）

### 5.1 冻结（2026-10-17）

- note：`tools\_note-0735.txt`（首串 `v0.7.35`；含 task-182 的 Mod 三条 + task-181 脑侧 + task-168 规模取舍）。
- `python tools\_bump-mod-version.py 0.7.35 --note-file tools\_note-0735.txt` ⇒ manifest `0.7.34 → 0.7.35`。
- `brain/agentfarm/bridge.py:39` ⇒ `MOD_VERSION_EXPECTED = "0.7.35"`（注释补 v0.7.35 四条；v0.7.34 及更早标为历史）。
- `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警告 0 错误**；dll **199168 B** / manifest **51090 B**。
- 冻结提交 **`630e594`**；`python tools\check-release.py --expect 0.7.35` ⇒ **六项全绿**（`Ran 945 tests / OK`、工作树干净）。
- 本批还含 Lead 侧工具改动：`tools\verify-run3.py` 补 `scope_shed` 口径核对（账本 `scope_shed_tiles` vs journal `scope_shed` 逐条对账；「认输却自称 VERIFIED」= 硬矛盾；`scope_shed` 快照缺失 ⇒ problem）+ 4 条单测（`Ran 69 tests / OK`），旧账本矩阵 rc 不变。

### 5.2 装机与基线（2026-10-17）

- `python tools\deploy-mod.py --no-quit` ⇒ **0.7.34 → 0.7.35**（dll 199168 / manifest 51090），桥 `modVersion=0.7.35 port=17890`，自动读档 `Wahaha_450799035`（FarmHouse (9,9)）。
- `python -m agentfarm goto Farm` ⇒ ok，`hop1 source=[3,12] landing=[64,15]` **7623ms**。
- `python tools\preflight.py --expect 0.7.35 --save-baseline logs\run10c-baseline.json` ⇒ **✅ 可以起跑**。
- 基线读数：第1年 **秋12日 06:00 rain** / `Farm(64,15)` / 体力 **247.2/270** / 钱 **0g** / 种子 `Wheat Seeds ×1` / `crops 102` / `unwateredCrops 2` / `dryCrops 0` / `farmScanSeq 9` / `waterLeft 27` / `tillableCount 120` / `tileCount 400 truncated` / 无模态 / `worldAdvancing true`。**无操作员预置**。
- 五文件指纹（A′ 起跑前锚）：`longrun.py D5F8F98D16AC8451…`、`farmwork.py E89DBB3C78DFFF12…`、`bridge.py 3FAEBC363BF92D4E…`、`dll 5925F3660AB5613E…`、`manifest 24877328542B956C…`。

### 5.3 放行（2026-10-17）

- **task-184**（0.7.35 同格复测 `(60,29)` + Scythe 对照格多格 loot）已派 machine-runner（rev3, in_progress）。
- 后续链：task-184 PASS ⇒ **task-113 A′/B′**（5 日长跑 ×2、字节拷贝教训库、argv 只差 `--journal`）⇒ 三向验收 + L0–L5。
