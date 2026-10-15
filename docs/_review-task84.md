# task-84 对抗性独立验收：死苗不浇水（0.7.27）

**判定：FAIL**

一句话：卡面主攻题"把活苗说成死苗（⇒ 活苗 dry 被排除 ⇒ `watered_outdoor=true` ⇒ `no_work` 不再判红）能不能把红变绿"——
在 **farm 证据不可用**（`farm.complete != true`，或旧 Mod 没有 `farm.dryCrops`，或 `deadCrops`/`dryDeadCrops` 缺失）的配置下
**拦不住**：脑侧自认 VERIFIED，`tools/verify-run3.py` 也返回 **exit 0 / VERIFIED**（只记 info）。
更强的反例是 **C8b：完全不需要任何谎报**——一株真·没浇的活苗只要落在观测窗口之外、且当天最后一张快照的 farm 证据不可用，
同样得到 `no_work` + `watered_outdoor=true` + `verified=true`，工具放行。
**归因实验**证明这条 fail-open **早于 task-84**（在 `a29b170`＝脑侧改动前的树上逐字相同），因此它不是 dev-coder 的回归；
但按 Lead 的明示规则"拦不住就是真缺陷，直接 FAIL"，本卡判 FAIL。
task-84 自身的四根支柱（Mod 拆分 / 死苗不浇水 / 政策序 / 三口径一致性）**全部 PASS**（§3）。

---

## §1 判定与依据摘要

| 问题（卡面） | 结论 | 证据 |
|---|---|---|
| ①活苗说成死苗 ⇒ `watered_outdoor` 变 true ⇒ 红变绿？ | **配置相关**：farm 证据可用时**拦得住**；farm 证据不可用时**拦不住**（脑+工具都放行） | C6a / C6b / C6c / C6d |
| ②真死苗当活苗 ⇒ 会不会去浇死苗？ | **不会**（post 树：`skipped`、零请求、世界不变、不吃配额）；改动真实生效（pre 树会真浇掉一格水） | C4（`_t92_water.py`） |
| ③口径一致性（缺失≠0、`gave_up_dry` 不 VERIFIED、`_far_dry_all_given_up` 边界） | **达标** | §3-B4/B5 |
| ④工具侧对齐（`dry_dead` 缺失⇒info、`dry_dead>0`+`no_work`⇒problem、`gave_up_dry`⇒info） | **达标**（F2 判红、F3 记 info） | F1/F2/F3 |
| ⑤新洞 | **一条真 fail-open（早于本卡）** + 4 条 NIT | §4 / §5 / §6 |

被判 FAIL 的**不是** task-84 的代码，而是"0.7.27 的浇水证据链在 farm 证据不可用时仍能被判达标"这一状态：
它正好落在卡面主攻题上（活苗 dry 被排除、`no_work` 不再判红），且是唯一一次真机 run8 会被它白烧/白过的路径。

---

## §2 范围与读数

**被验对象（按交付顺序）**

| 提交 | 范围 | 规模 |
|---|---|---|
| `a29b170` | `mod/AgentFarm.Bridge/{Contracts.cs, FarmScan.cs, WorldSnapshot.cs}` | +45 / −13 |
| `3b00761` | `brain/agentfarm/{farmwork.py, longrun.py, planner.py}` + `tests/{test_farmwork.py, test_longrun.py, test_planner.py}` | +415 / −43 |
| `e23481e` | `brain/agentfarm/bridge.py` + `mod/AgentFarm.Bridge/manifest.json`（0.7.27 冻结） | +6 / −1、+4 / −2 |
| `fdb87d8` | `tools/verify-run3.py` + `tests/test_verify_run3.py` | +38 / +32 |

**越界检查**：`git show --name-only a29b170 3b00761 | Select-String "manifest|bridge\.py|^logs/|00-开发日志|^tools/"` **零命中**
⇒ Mod 侧与脑侧分开提交、dev-coder 未 bump、未碰 `logs/`、未碰 `tools/`。

**快照**：`git archive --format=tar -o scratch\_t92_snap.tar e23481e` + `tar -xf -C scratch\_t92_snap`（338 文件）。
9 个目标文件 SHA256 与**工作树逐字一致**（也等于 HEAD 版本）：
`farmwork.py` 8B62190A…509C、`longrun.py` 420B1DE8…6083、`planner.py` 10048930…0502、
`Contracts.cs` 4D3B6F95…ED7F、`FarmScan.cs` F95AB56C…81D7、`WorldSnapshot.cs` A021F3B6…B185、
`test_farmwork.py` 04AC1FBD…A8C6、`test_longrun.py` ED1D5BC1…2C38、`test_planner.py` EFAEE19B…6569。
唯一差异是 `manifest.json` 的**纯 CRLF**（主树 21468 B / CRLF=10 vs 快照 21458 B / CRLF=0；`git diff HEAD --` 为空）。
版本两侧一致：`manifest.json:4 "Version": "0.7.27"`、`bridge.py:39 MOD_VERSION_EXPECTED = "0.7.27"`。

**工具 revision**：`tools/verify-run3.py` SHA256 = 512DD4E2…16FC（快照内与工作树**相同**，`fdb87d8` 是最后改它的提交）
⇒ 我的账本判决就是**当前工具**的判决。

**读数（e23481e 快照 / A 段）**
- `py_compile -W error::SyntaxWarning`（brain/agentfarm + tests 全量）⇒ **exit 0**
- `tests.test_farmwork tests.test_longrun tests.test_planner` ⇒ **Ran 316 tests / OK**
- 全量 `discover -s tests` ⇒ **Ran 572 tests / FAILED (failures=1)**，唯一红 =
  `tests/test_analyze_longrun.py::TestEventMappingDrift.test_event_buckets_cover_every_brain_journal_name`
  （brain 有 `dead_crops_summary`，analyzer 的 `EVENT_BUCKETS` 未跟）⇒ 即 Lead 已派的 **task-95**，不算本卡发现。
- 说明：验收期间 HEAD 已前进到 `244e456`（Lead/log-analyst 的 task-95 analyzer 提交），工作树另有
  ` M tools/analyze-longrun.py`（非我范围）；本卡结论只依赖 e23481e 快照 + 上述 SHA256。

**我的对抗脚本（写盘仅 scratch/）**：`scratch/_t92_adv.py`（C6a–C6d/C7/C8 + 账本级 F1–F3）、
`scratch/_t92_adv2.py`（C7b/C8b/C8c）、`scratch/_t92_attr.py`（pre/post 归因）、`scratch/_t92_water.py`（反向：死苗不浇）。
输出留档：`scratch/_t92_adv_out.txt`、`_t92_adv2_out.txt`、`_t92_attr_pre.txt`、`_t92_attr_snap.txt`、`_t92_water_snap.txt`、`_t92_water_pre.txt`。

---

## §3 逐条对卡

### A 段（范围 / 越界 / 读数 / 哈希）
✅ 逐条如 §2；`git status --short` 只显示我的 `?? scratch/_t92_*.py` 与别人的 ` M tools/analyze-longrun.py`。

### B 段 —— Mod 侧（`a29b170`）
- B1 ✅ `Contracts.cs`：`dryCrops` 文档收窄为"只算活苗"（`crop != null && !Crop.dead && !isWatered()`），并写明"死苗的干格数见 `DryDeadCrops`"；`dryTiles` 同步收窄。
- B2 ✅ `FarmScan.cs`：在 `!dirt.isWatered()` 分支里 `bool dead = (crop.dead != null && crop.dead.Value)`（try/catch 包裹）⇒ `if (dead) _acc.DryDeadCrops++; else { _acc.DryCrops++; _dryTiles.Add(...) }`——与 `Crops`/`RipeCrops` **同一次扫描**，`dryTiles` 只收活苗。
- B3 ✅ 新增 `[JsonPropertyName("dryDeadCrops")] public int DryDeadCrops`，doc 明写"旧 Mod 无此字段 ⇒ JSON null：脑侧不许把没这个字段当成 0；只在 `Complete == true` 时可信"。
- B4 ✅ `WorldSnapshot.cs`：`t.Tool = (t.Ripe || t.Dead) ? "none" : "can";`（死苗不再建议水壶）。

### B 段 —— 脑侧（`3b00761`）
- B5 ✅ `farmwork.farm_dry_dead_crops(obs) -> (int, str)`：`loaded is False` / `complete is not True` / `raw is None` / 非整数 ⇒ `(0, "unavailable")`；我的直测三态：
  `无 farm 块 ⇒ (0,'unavailable')`、`complete=false ⇒ (0,'unavailable')`、`缺 dryDeadCrops ⇒ (0,'unavailable')`、`有值 3 ⇒ (3,'ok')`。
- B6 ✅ **反向（真死苗不浇）**：真 `FarmWorker.water(死苗格)` ⇒ `code='skipped'`、`failed=False`、`attempted=False`、`skipped=True`、**世界不变、水 40→40（一个请求都没发）**、reason `这一格的作物已经枯死 ⇒ 不浇水（该走 clear_dead 清掉）`；活苗仍 `code='ok'`、`已浇（水 40→39）`。
  同一脚本在 **pre 树 `a29b170`** 上：死苗 ⇒ `code='ok'`、`已浇（水 40→39）`、水 40→39 ⇒ **改动真实生效**（不是"本来就跳过"）。
- B7 ✅ `_stage_tiles("water_area")` 与 `_leftover("water_area")` 都排除 `dead`；`_work_spot_plot` 把 dead 也算作业区容器（C7 里当天阶段是 `clear_dead`，`water_area` 不再出现）。
- B8 ✅ `planner.py`：`Brief.counts` 的 `elif not tile.get("dead"): counts["unwatered_crops"] += 1`；`deterministic_plan` 顺序 harvest → clear_dead → water_area（作者用例 + 316 OK 覆盖）。

### B 段 —— 守卫 / 口径一致性
- B9 ✅ `_water_evidence` 窗口分支 `dry_t = [t for t in crops_t if not win[t].get("watered") and not win[t].get("dead")]`；farm note 明写"0.7.27 起只算活苗"。
- B10 ✅ `gave_up_dry` **不在** `JUSTIFIED_END_REASONS=("night","stamina","no_work")` ⇒ `day_justified=False`；`far_dry_tries/far_dry_given_up/far_dry_unavailable_noted` 每天重置。
- B11 ✅ `_far_dry_all_given_up`：窗口外干格全部认输才 True（`status=="unavailable" or not outside ⇒ False`）。
- B12 ✅ 日账本：`dead_crops/dead_crops_status/dry_dead/dry_dead_status/gave_up_tiles` 进 `day_end`；`dead_crops_summary` journal 每天一条。**但**见 §6（这些字段不参与"没活可做"的判定本身）。

### C 段 —— 对抗（≥4 条，实际 12 条，逐条读数见 §4）
- C6（活苗说成死苗）**未全拦住** ⇒ 本卡判 FAIL 的直接依据。
- C7（死苗混进 `no_work`）：活苗都浇好、窗口里还剩**没浇的死苗** ⇒ 工具判红（新闸门），**脑侧仍自认 VERIFIED**（NIT-1 的放宽形态 C7b 连工具也放行）。
- C8（够不着的干活苗）：**未拦住**（C8b/C8c，且无需谎报）。
- C9（旧 Mod 缺 `dryDeadCrops`）：脑侧如实 `unavailable`、工具记 info（**不判 0**）✅；但同一配置叠加"干作物在窗口外"⇒ C8c 洗白。

---

## §4 对抗矩阵（全部为真代码 + 真 `tools/verify-run3.py`，工具判决用当天真账本喂 `report()`）

世界 = `tests/test_longrun.py:FakeWorld`（25 格微农场）；`T92_ROOT` 指向 `scratch\_t92_snap`（post）或 `scratch\_t92_pre`（= `a29b170`，脑侧改动前）。

| 编号 | 构造（**谎报？**） | 脑侧结果 | 工具结果 | 判定 |
|---|---|---|---|---|
| **C6a** | 活苗谎报 `dead=true`；farm **真值** `complete=true, dryCrops=1, dryDeadCrops=0` | `ended_by=stuck`、`watered_outdoor=false`、`verified=false`；守卫原文`农场口径还有 1 格干作物，但 farm.dryTiles 不可用（旧 Mod / farm 证据不可信）⇒ 不许判「没活」，先回农场再判` | `ok=False / needs_review`（`checks.watered_outdoor=false`、`ended_by=stuck`、`verified=false`） | **拦得住** |
| **C6b** | 活苗谎报 dead **且** farm 也伪造 `dryCrops=0, dryDeadCrops=1` | `no_work`、`watered_outdoor=true`、`verified=true`、`dry_dead=1` | `ok=False / needs_review`：`[spring 6] ended_reason 以 no_work 开头，但 day_end.dry_dead=1（还有枯死作物没清却判"今天没活"…）` | **新闸门拦得住** |
| **C6c** | 活苗谎报 dead；farm `complete=false`（证据不可用） | `no_work`、`watered_outdoor=true`、`verified=true`；`final_water={scope:"window", tiles:1, crops:0, dry:0}` | **`ok=True / VERIFIED`**，problems 空 | **拦不住 ⇒ FAIL 依据** |
| **C6d** | 同上但**完全没有 farm 块**（旧 Mod 形态） | 同 C6c | **`ok=True / VERIFIED`** | **拦不住** |
| **C7** | 窗口里一株**没浇的死苗** + 活苗都浇好；farm `dryCrops=0, dryDeadCrops=1` | `no_work`、`verified=true`、`dry_dead=1` | `ok=False / needs_review`（同上 dry_dead 闸门） | 工具拦住、脑侧仍自认达标 |
| **C7b** | 窗口里一株**浇过水的死苗**（`dry_dead=0`，死苗还杵在地里）+ 活苗都浇好 | `no_work`、`verified=true`、`dead_crops=1` | **`ok=True / VERIFIED`**（连 info 都没有） | NIT-1 |
| **C8 / C8b / C8c** | **不谎报**：真·没浇的活苗在观测窗口之外；窗口只剩 1 格空耕地；farm 证据不可用（`complete=false` / 无 farm 块） | `no_work`、`watered_outdoor=true`、`verified=true` | **`ok=True / VERIFIED`**，info 里只有`当天 0 个阶段且自称 VERIFIED，但有"无活可做"证据 ⇒ 接受` | **拦不住（核心 fail-open）** |
| **C8（初版）** | 同上但窗口被藏成 0 格 | `watered_outdoor=false`（空窗口守卫） | `needs_review` | 空窗口那条守住了 |
| **F1** | 账本级：`dry_dead=0` + `dead_crops=1` + `watered_outdoor=true` + `final_water={scope:"window", tiles:30, crops:0, dry:0}` + `no_work` | — | **`ok=True / VERIFIED`** | 账本盲区（工具拿不到"活/死"真值） |
| **F2** | 同 F1 但 `dry_dead=1` | — | `ok=False / needs_review`（dry_dead 闸门） | 闸门本身有效 |
| **F3** | 旧账本：完全没有 `dry_dead`/`dead_crops` | — | `ok=True / VERIFIED` + info`账本没写 dry_dead（task-84 之前的旧账本）⇒ 死苗口径无法判定` | 与卡面一致（缺失≠判红，但"缺失≠通过"由 info 承担） |
| **C4** | 反向：真死苗 | post：`skipped`、零请求、水不变；pre：`ok`、真浇掉 1 格 | — | **改动生效** |

**归因（pre/post 逐字对比）**：`scratch/_t92_attr.py` 在同一世界（C8b/C8c/C6c）上跑
`scratch\_t92_pre`（= `a29b170`，**脑侧改动前**）与 `scratch\_t92_snap`（= `e23481e`）：
`ended_by / ended_reason / verified / checks / final_water / ok_steps / failed_steps` 与工具判决（`ok=True / VERIFIED`）
**逐字相同** ⇒ 这条 fail-open **早于 task-84**，不是本卡引入的回归。

---

## §5 NIT 表

| # | 现象 | 行号/证据 | 建议 | 阻塞 run8？ |
|---|---|---|---|---|
| NIT-1 | 窗口里"浇过水的死苗"（`dry_dead=0`）仍杵在地里，当天却判 `no_work` + VERIFIED；工具也放行 | C7b（§4） | `work_reasons()`/`sleep_guard` 把"窗口里还有 `dead` 格"也算有活（或至少在 `dead_crops>0` 且未清时不许 `no_work`） | 否 |
| NIT-2 | 工具只堵 `scope=="window"` 且 `tiles==0`（B4b）；`tiles>0, crops==0` 的 window 证据被当作有效 | F1/C6c/C8b | window 口径加"`crops==0` 且当天 farm 证据不可用 ⇒ 不算浇水证据" | 否（但见 §6） |
| NIT-3 | C6a 守卫文案写死"旧 Mod / farm 证据不可信"，实际触发是 `farm.dryTiles` 缺失（也可能是瞬时 `complete=false`） | C6a | 文案按实际字段缺失分支 | 否 |
| NIT-4 | `dead_crops/dry_dead` 只进账本与工具闸门，**不参与**"今天有没有活"的判定（B12） | C7b | 见 NIT-1 | 否 |
| NIT-5 | 工具对 `dead_crops>0` 的 VERIFIED 日只记 info`弱日`（C6b/C7） | §4 | 可接受（已有 dry_dead 硬闸门） | 否 |

---

## §6 开放盲区与建议（不代改）

**B23（本次新发现，真 fail-open）**：*farm 证据不可用 + 干作物不在观测窗口内 ⇒ 脑与工具都判达标*。
- 触发：当天最后一张户外快照的 `farm.complete != true`（FarmScan 一轮扫描未完成的瞬时状态），或旧 Mod 没有 `farm.dryCrops`；
  同时真正需要浇水的活苗落在 400 格观测窗口之外（`WorldSnapshot.cs` 只收 `objects`+`terrainFeatures` 并按距离取最近 400 格）。
- 链路：`work_reasons()`/`sleep_guard` 在 **人在农场** 时 `_farm_scope_work` 返回 None ⇒ 拿不到 `dry_f` ⇒ 不产生"还有干作物"的理由 ⇒ `no_work`；
  而 `_water_evidence` 退回窗口口径，窗口里 `crops==0` ⇒ `dry=0` ⇒ `watered_outdoor=true`。
  `farm_evidence_unavailable` 的 fail-closed 只在 **`farm_work is None and not self._is_farm(obs)`**（人不在农场）时触发 ⇒ 洞就在这。
- 后果：run8 可能在一株活苗真的没浇的情况下"一路 VERIFIED"（真机里正是 run7 那颗 `[12,30]` 的位置形态）。
- 建议修法（最小）：把 farm 证据 fail-closed 扩到"人在农场"情形——`longrun.py` 在 `farm.complete != true`（或 `dryCrops is None`）
  时也不许出 `no_work`（`sleep_guard` 返回 `keep_working`/诚实 `stuck` + journal），或者在 `_water_evidence` 的 window 分支
  要求"窗口里至少看得见一株作物（`crops>0`）"才允许 `dry==0 ⇒ True`。
- **归因**：`a29b170`（脑侧改动前）逐字相同 ⇒ 老洞；task-84 只是让它更容易撞上（`dryCrops` 收窄后"死苗"不再进 dry）。

**仍开放（非本卡）**：`(b)` 账本层"真失败改分类"不可判（task-72 留档）、B10（外部证据全是自述）、B11（窗口 `tilesTruncated` 未看）。

---

## §7 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"
$env:T92_ROOT = (Resolve-Path .\scratch\_t92_snap).Path          # post（0.7.27 冻结）
& $py scratch\_t92_adv.py        # C6a–C6d / C7 / C8 + F1–F3
& $py scratch\_t92_adv2.py       # C7b / C8b / C8c
& $py scratch\_t92_water.py      # 反向：死苗不浇（post 全绿；pre 会变红）
$env:T92_ROOT = (Resolve-Path .\scratch\_t92_pre).Path           # pre（a29b170，归因）
& $py scratch\_t92_attr.py
```

（`scratch\_t92_snap` / `scratch\_t92_pre` 由 `git archive e23481e` / `git archive a29b170` 展开；`T92_ROOT` 同时决定
`brain/`、`tests/`、`tools/verify-run3.py` 取自哪棵树。）
